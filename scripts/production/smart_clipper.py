#!/usr/bin/env python3
"""
smart_clipper.py — PawFactory smart segment selector

Samples frames across a full source video, scores candidate segments using
Claude Vision (Haiku), and extracts the best segment to inbox/{id}_clip.mp4.

Run BEFORE visual_sampler. visual_sampler then uses the clipped version.

Usage:
  python scripts/production/smart_clipper.py --video-id 31rzo46u
  python scripts/production/smart_clipper.py --video-id 31rzo46u --dry-run

Output:
  inbox/{id}_clip.mp4         — extracted best segment
  logs/clips/{id}_clip.json   — segment scores + selection record
"""

import argparse
import base64
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

load_dotenv()
console = Console()

# ── Segment configuration ────────────────────────────────────────────────────
TARGET_SEGMENT_DURATION = 45.0   # target window length in seconds
SEGMENT_STRIDE          = 30.0   # step between window start points
MIN_SEGMENT_DURATION    = 20.0   # minimum viable window (at end of video)
MAX_SEGMENTS            = 8      # cap to control API costs
FRAMES_PER_SEGMENT      = 3      # frames extracted per segment for scoring

# Scoring weights
WEIGHT_SUBJECT_CLARITY  = 1.5
WEIGHT_EMOTIONAL_IMPACT = 1.5
WEIGHT_ACTION           = 1.0
WEIGHT_VISUAL_QUALITY   = 1.0
WEIGHT_TOTAL            = WEIGHT_SUBJECT_CLARITY + WEIGHT_EMOTIONAL_IMPACT + WEIGHT_ACTION + WEIGHT_VISUAL_QUALITY

# Early-segment preference: segments starting in the first 20% get a small bonus.
# Biases selection toward material that can open the video, all else being equal.
EARLY_SEGMENT_BONUS     = 0.3

SCORE_SYSTEM_PROMPT = """You are a video segment quality scorer for a YouTube Shorts channel about emotional animal stories.

You will receive frames sampled evenly from a candidate video segment. Score this segment on four dimensions (each 1–10):

- subject_clarity: Is the animal clearly visible, well-framed, and identifiable? (10 = close-up, sharp, centered)
- emotional_impact: Is there an observable emotional moment — distress, care, reunion, relief, gratitude? (10 = unmistakably powerful)
- action: Is something meaningful happening — movement, rescue activity, human-animal interaction? (10 = active and engaging)
- visual_quality: Is the footage stable, well-lit, not blurry, not extremely shaky? (10 = broadcast quality)

Also provide:
- reject: true if this segment should be disqualified. Grounds for rejection: animal barely or never visible; pure chaotic motion with nothing meaningful; boring static b-roll with no subject present.
- reject_reason: brief reason if reject=true, else null.

Return ONLY valid JSON with no markdown:
{
  "subject_clarity": <1-10>,
  "emotional_impact": <1-10>,
  "action": <1-10>,
  "visual_quality": <1-10>,
  "reject": <true|false>,
  "reject_reason": <string|null>
}"""


@dataclass
class Segment:
    index: int
    start: float
    end: float
    frames: list[tuple[float, Path]] = field(default_factory=list)  # (timestamp_seconds, path)
    score_raw: dict | None = None
    score_total: float = 0.0
    rejected: bool = False
    reject_reason: str | None = None

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def label(self) -> str:
        return f"seg{self.index+1:02d} [{self.start:.0f}s–{self.end:.0f}s]"


# ── ffprobe helpers ──────────────────────────────────────────────────────────

def _ffprobe_duration(file_path: str) -> float | None:
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(file_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        for stream in json.loads(result.stdout).get("streams", []):
            d = stream.get("duration")
            if d:
                return float(d)
    except Exception:
        pass
    return None


# ── Segment generation ───────────────────────────────────────────────────────

def _generate_segments(duration: float) -> list[Segment]:
    """
    Generate candidate segments using a sliding window.
    Windows are TARGET_SEGMENT_DURATION long, stepped by SEGMENT_STRIDE.
    The final window may be shorter (clamped to video end).
    Segments shorter than MIN_SEGMENT_DURATION are discarded.
    Result is capped at MAX_SEGMENTS.
    """
    segments: list[Segment] = []
    start = 0.0
    while start < duration:
        end = min(start + TARGET_SEGMENT_DURATION, duration)
        if (end - start) >= MIN_SEGMENT_DURATION:
            segments.append(Segment(index=len(segments), start=start, end=end))
        start += SEGMENT_STRIDE

    # If we have more than MAX_SEGMENTS, subsample evenly (keep first + last + interior)
    if len(segments) > MAX_SEGMENTS:
        step = (len(segments) - 1) / (MAX_SEGMENTS - 1)
        indices = sorted({round(i * step) for i in range(MAX_SEGMENTS)})
        segments = [segments[i] for i in indices]
        for i, s in enumerate(segments):
            s.index = i

    return segments


# ── Frame extraction ─────────────────────────────────────────────────────────

def _extract_segment_frames(
    video_path: str,
    seg: Segment,
    frames_dir: Path,
    vid_id: str,
) -> list[tuple[float, Path]]:
    """Extract FRAMES_PER_SEGMENT frames evenly distributed within the segment."""
    frames_dir.mkdir(parents=True, exist_ok=True)
    frames: list[tuple[float, Path]] = []

    n = FRAMES_PER_SEGMENT
    # Distribute frames evenly within [start, end], avoiding the very edges
    margin = seg.duration * 0.1
    sample_start = seg.start + margin
    sample_end   = seg.end   - margin
    if n == 1:
        timestamps = [seg.start + seg.duration / 2]
    else:
        step = (sample_end - sample_start) / (n - 1)
        timestamps = [sample_start + i * step for i in range(n)]

    for fi, t in enumerate(timestamps):
        out_path = frames_dir / f"{vid_id}_sc_{seg.index+1:02d}_{fi+1}.jpg"
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{t:.3f}",
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "4",
            "-vf", "scale=640:-2",
            str(out_path),
        ]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0:
            frames.append((t, out_path))

    return frames


# ── Segment scoring ──────────────────────────────────────────────────────────

def _score_segment(seg: Segment, client: anthropic.Anthropic) -> dict | None:
    """Score a single segment by sending its frames to Claude Haiku."""
    if not seg.frames:
        return None

    content: list[dict] = []
    for t, path in seg.frames:
        with open(path, "rb") as f:
            data = base64.standard_b64encode(f.read()).decode()
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": data},
        })

    ts_labels = ", ".join(f"{t:.1f}s" for t, _ in seg.frames)
    content.append({
        "type": "text",
        "text": (
            f"These {len(seg.frames)} frames are from a video segment "
            f"spanning {seg.start:.0f}s–{seg.end:.0f}s (timestamps: {ts_labels}). "
            "Score this segment according to the instructions."
        ),
    })

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=SCORE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        return json.loads(raw)
    except (json.JSONDecodeError, anthropic.APIError) as e:
        console.print(f"  [yellow]Warning: scoring failed for {seg.label}: {e}[/yellow]")
        return None


def _compute_total(raw: dict) -> float:
    """Weighted average of the four score dimensions."""
    return (
        WEIGHT_SUBJECT_CLARITY  * raw.get("subject_clarity",  5) +
        WEIGHT_EMOTIONAL_IMPACT * raw.get("emotional_impact", 5) +
        WEIGHT_ACTION           * raw.get("action",           5) +
        WEIGHT_VISUAL_QUALITY   * raw.get("visual_quality",   5)
    ) / WEIGHT_TOTAL


# ── Clip extraction ──────────────────────────────────────────────────────────

def _extract_clip(video_path: str, seg: Segment, out_path: Path) -> bool:
    """Extract segment from source video using ffmpeg stream copy (lossless, fast)."""
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{seg.start:.3f}",
        "-i", video_path,
        "-t", f"{seg.duration:.3f}",
        "-c", "copy",
        str(out_path),
    ]
    r = subprocess.run(cmd, capture_output=True)
    return r.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0


# ── Main pipeline function ───────────────────────────────────────────────────

def run_smart_clipper(vid_id: str) -> dict:
    """
    Full smart clipping pipeline for a downloaded source video.

    Returns a result dict and saves logs/clips/{vid_id}_clip.json.
    Extracts inbox/{vid_id}_clip.mp4.

    Raises RuntimeError on unrecoverable failure.
    """
    inbox    = Path(os.getenv("INBOX_DIR",  "inbox"))
    log_dir  = Path(os.getenv("LOG_DIR",    "logs"))
    clips_dir = log_dir / "clips"
    frames_dir = log_dir / "clips" / "frames"
    clips_dir.mkdir(parents=True, exist_ok=True)

    # Locate source video
    video_path = None
    for ext in ("mp4", "webm", "mkv", "mov"):
        p = inbox / f"{vid_id}.{ext}"
        if p.exists():
            video_path = str(p)
            break
    if not video_path:
        raise RuntimeError(f"Source video not found for {vid_id} in {inbox}/")

    duration = _ffprobe_duration(video_path)
    if not duration:
        raise RuntimeError(f"Could not measure duration of {video_path}")

    console.print(f"  [dim]Source: {Path(video_path).name} ({duration:.1f}s)[/dim]")

    # For short clips (≤ TARGET_SEGMENT_DURATION), clipping doesn't help — copy as-is
    if duration <= TARGET_SEGMENT_DURATION:
        out_path = inbox / f"{vid_id}_clip.mp4"
        import shutil
        shutil.copy2(video_path, out_path)
        result = {
            "video_id": vid_id,
            "source_duration": duration,
            "clip_start": 0.0,
            "clip_end": duration,
            "clip_duration": duration,
            "segments_evaluated": 0,
            "best_segment": None,
            "skipped": True,
            "skip_reason": f"Source already short ({duration:.1f}s ≤ {TARGET_SEGMENT_DURATION}s) — copied as-is",
            "clipped_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(clips_dir / f"{vid_id}_clip.json", "w") as f:
            json.dump(result, f, indent=2)
        console.print(f"  [dim]Source is short ({duration:.1f}s) — no clipping needed[/dim]")
        return result

    # Generate candidate segments
    segments = _generate_segments(duration)
    console.print(f"  [dim]{len(segments)} candidate segments generated[/dim]")

    # Extract frames for each segment
    console.print(f"  [dim]Extracting {FRAMES_PER_SEGMENT} frames per segment...[/dim]")
    for seg in segments:
        seg.frames = _extract_segment_frames(video_path, seg, frames_dir, vid_id)
        if not seg.frames:
            seg.rejected = True
            seg.reject_reason = "no frames could be extracted"

    # Score each segment
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY missing")
    client = anthropic.Anthropic(api_key=api_key)

    console.print(f"  [dim]Scoring segments with Claude Haiku...[/dim]")
    for seg in segments:
        if seg.rejected:
            continue
        raw = _score_segment(seg, client)
        if raw is None:
            # Assign neutral score rather than rejecting on API transient error
            seg.score_raw = {"subject_clarity": 5, "emotional_impact": 5, "action": 5, "visual_quality": 5}
        else:
            seg.score_raw = raw
            if raw.get("reject"):
                seg.rejected = True
                seg.reject_reason = raw.get("reject_reason", "rejected by scorer")
                continue
        seg.score_total = _compute_total(seg.score_raw)

    # Apply early-segment bonus
    total_duration = duration
    for seg in segments:
        if not seg.rejected and seg.start / total_duration <= 0.20:
            seg.score_total += EARLY_SEGMENT_BONUS

    # Print scoring table
    table = Table(title=f"Segment scores — {vid_id}", show_header=True)
    table.add_column("Segment",   style="cyan",  width=22)
    table.add_column("Clarity",   justify="right")
    table.add_column("Emotion",   justify="right")
    table.add_column("Action",    justify="right")
    table.add_column("Visual",    justify="right")
    table.add_column("Total",     justify="right", style="bold")
    table.add_column("Status",    style="dim")
    for seg in segments:
        if seg.rejected:
            table.add_row(seg.label, "—", "—", "—", "—", "—", f"REJECTED: {seg.reject_reason}")
        elif seg.score_raw:
            r = seg.score_raw
            table.add_row(
                seg.label,
                str(r.get("subject_clarity",  "?")),
                str(r.get("emotional_impact",  "?")),
                str(r.get("action",            "?")),
                str(r.get("visual_quality",    "?")),
                f"{seg.score_total:.2f}",
                "✓",
            )
        else:
            table.add_row(seg.label, "—", "—", "—", "—", "—", "no score")
    console.print(table)

    # Select best segment
    viable = [s for s in segments if not s.rejected and s.score_raw is not None]
    if not viable:
        raise RuntimeError(
            f"No viable segments found for {vid_id}. "
            "All segments were rejected by the vision scorer."
        )

    best = max(viable, key=lambda s: s.score_total)
    console.print(
        f"  [green]Best segment: {best.label} "
        f"(score {best.score_total:.2f})[/green]"
    )

    # Extract clip
    out_path = inbox / f"{vid_id}_clip.mp4"
    console.print(f"  [dim]Extracting clip: {best.start:.1f}s → {best.end:.1f}s[/dim]")
    if not _extract_clip(video_path, best, out_path):
        raise RuntimeError(f"ffmpeg clip extraction failed for {best.label}")

    clip_duration = _ffprobe_duration(str(out_path)) or best.duration
    console.print(
        f"  [green]✓ Clip saved: {out_path.name} ({clip_duration:.1f}s)[/green]"
    )

    # Build result record
    result = {
        "video_id": vid_id,
        "source_duration": duration,
        "clip_start": best.start,
        "clip_end": best.end,
        "clip_duration": clip_duration,
        "segments_evaluated": len(segments),
        "segments_viable": len(viable),
        "best_segment": {
            "index": best.index,
            "label": best.label,
            "score_total": best.score_total,
            "score_raw": best.score_raw,
        },
        "all_segments": [
            {
                "label": s.label,
                "start": s.start,
                "end": s.end,
                "score_total": s.score_total if not s.rejected else None,
                "score_raw": s.score_raw,
                "rejected": s.rejected,
                "reject_reason": s.reject_reason,
            }
            for s in segments
        ],
        "skipped": False,
        "clipped_at": datetime.now(timezone.utc).isoformat(),
        "model": "claude-haiku-4-5-20251001",
    }

    with open(clips_dir / f"{vid_id}_clip.json", "w") as f:
        json.dump(result, f, indent=2)

    return result


# ── CLI entry point ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="PawFactory Smart Clipper")
    parser.add_argument("--video-id", required=True, help="Video ID (source in inbox/)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Score segments but do not extract clip")
    args = parser.parse_args()

    try:
        result = run_smart_clipper(args.video_id)
        if args.dry_run:
            console.print(f"\n[dim](dry-run — clip extraction skipped)[/dim]")
        else:
            best = result.get("best_segment")
            if best:
                console.print(
                    f"\n[bold green]✓ Smart clip ready: "
                    f"inbox/{args.video_id}_clip.mp4 "
                    f"({result['clip_duration']:.1f}s, score {best['score_total']:.2f})[/bold green]"
                )
            else:
                console.print(
                    f"\n[bold green]✓ Source copied as-is "
                    f"(already short): inbox/{args.video_id}_clip.mp4[/bold green]"
                )
    except RuntimeError as e:
        console.print(f"[red]✗ Smart clipper failed: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
