#!/usr/bin/env python3
"""
visual_sampler.py — PawFactory smart frame sampling + vision summary

Extracts representative frames from a source video and generates a
factual visual summary using Claude Vision. This summary grounds the
downstream hook/script/metadata generation to what is actually visible.

Usage:
  python scripts/production/visual_sampler.py --video-id 31rzo46u
  python scripts/production/visual_sampler.py --video-id 31rzo46u --frames 6

Output:
  logs/visuals/{video_id}_summary.json  — inspectable artifact
"""

import argparse
import base64
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
console = Console()

# Temporal positions as fractions of video duration.
# Covers: near-start (hook frame), early, mid-early, mid, late-mid, near-end (payoff).
DEFAULT_SAMPLE_POSITIONS = [0.02, 0.15, 0.30, 0.50, 0.70, 0.90]

VISION_SYSTEM_PROMPT = """You are a factual video content analyst for a YouTube Shorts channel about emotional animal stories.

Your job is to describe only what is clearly and unambiguously visible in a set of video frames.

Rules:
- Describe only what you can clearly see. Do not infer what might be happening off-screen.
- Do not infer medical severity unless it is obviously visible (e.g. a visibly open wound, blood).
- Do not use dramatic language such as "dying", "critical condition", "hours to live",
  "circulation cut off", "emergency" unless the visual unmistakably shows that state.
- If something is ambiguous or unclear, use neutral wording (e.g. "a dog lying on the ground"
  rather than "a dog in critical condition").
- Describe: setting, visible animals and humans, what actions are happening frame by frame,
  and the observable emotional tone if readable from body language or facial expressions.
- Keep the summary concise and factual — one short paragraph of 4–8 sentences.
- This summary will be used to write a voiceover script. Accuracy matters more than drama."""

VISION_USER_PROMPT = """Here are {n} frames sampled from a short video clip at positions: {positions}.

Describe what you can clearly observe across these frames as a factual visual summary.
What animals are present? What are the humans doing? What is the setting?
What progression of events is visible? What is the overall emotional tone?"""


def _ffprobe_duration(file_path: str) -> float | None:
    """Return duration of a media file in seconds, or None on failure."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", str(file_path),
    ]
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


def extract_frames(
    video_path: str,
    positions: list[float],
    output_dir: Path,
    vid_id: str,
) -> list[tuple[float, Path]]:
    """
    Extract one JPEG frame per fractional position in [0, 1].
    Returns list of (fraction, path) pairs for frames that succeeded.
    """
    duration = _ffprobe_duration(video_path)
    if not duration:
        raise RuntimeError(f"Could not measure duration of {video_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for i, frac in enumerate(positions):
        t = frac * duration
        out_path = output_dir / f"{vid_id}_vs_{i+1}.jpg"
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{t:.3f}",
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "3",
            "-vf", "scale=720:-2",
            str(out_path),
        ]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode == 0 and out_path.exists():
            frames.append((frac, out_path))
        else:
            console.print(f"  [dim]Warning: could not extract frame at {frac:.0%} ({t:.1f}s)[/dim]")
    return frames


def generate_visual_summary(frames: list[tuple[float, Path]]) -> str:
    """Send frames to Claude Vision (Haiku) and return factual summary string."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    client = anthropic.Anthropic(api_key=api_key)

    content: list[dict] = []
    positions_str = []
    for frac, path in frames:
        with open(path, "rb") as f:
            data = base64.standard_b64encode(f.read()).decode()
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": data},
        })
        positions_str.append(f"{frac:.0%}")

    content.append({
        "type": "text",
        "text": VISION_USER_PROMPT.format(n=len(frames), positions=", ".join(positions_str)),
    })

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        system=VISION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    return message.content[0].text.strip()


def run_visual_sampling(vid_id: str, n_frames: int = 6) -> dict:
    """
    Full visual sampling pipeline for a downloaded source video.

    Returns summary dict and saves it to logs/visuals/{vid_id}_summary.json.
    """
    inbox = Path(os.getenv("INBOX_DIR", "inbox"))
    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    frames_dir = log_dir / "visuals" / "frames"
    visuals_dir = log_dir / "visuals"

    # Find source video — prefer smart-clipped version if available
    video_path = None
    clip_path = inbox / f"{vid_id}_clip.mp4"
    if clip_path.exists():
        video_path = str(clip_path)
        console.print(f"  [dim]Using smart clip: {clip_path.name}[/dim]")
    else:
        for ext in ("mp4", "webm", "mkv", "mov"):
            p = inbox / f"{vid_id}.{ext}"
            if p.exists():
                video_path = str(p)
                break
    if not video_path:
        raise RuntimeError(f"Source video not found for {vid_id} in {inbox}/")

    # Choose sample positions
    n = max(2, min(n_frames, len(DEFAULT_SAMPLE_POSITIONS)))
    positions = DEFAULT_SAMPLE_POSITIONS[:n]

    console.print(f"  [dim]Sampling {n} frames for visual grounding...[/dim]")
    frames = extract_frames(video_path, positions, frames_dir, vid_id)

    if not frames:
        raise RuntimeError(f"No frames could be extracted from {video_path}")

    console.print(f"  [dim]Generating visual summary ({len(frames)} frames → Claude Haiku)...[/dim]")
    summary = generate_visual_summary(frames)

    result = {
        "video_id": vid_id,
        "visual_summary": summary,
        "frames_analyzed": len(frames),
        "sample_positions": [f"{f:.0%}" for f, _ in frames],
        "sampled_at": datetime.now(timezone.utc).isoformat(),
        "model": "claude-haiku-4-5-20251001",
    }

    visuals_dir.mkdir(parents=True, exist_ok=True)
    out_path = visuals_dir / f"{vid_id}_summary.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    return result


def main():
    parser = argparse.ArgumentParser(description="PawFactory smart frame sampler + vision summary")
    parser.add_argument("--video-id", required=True, help="Video ID (must be in inbox/)")
    parser.add_argument("--frames", type=int, default=6,
                        help="Number of frames to sample (2–6, default: 6)")
    args = parser.parse_args()

    try:
        result = run_visual_sampling(args.video_id, args.frames)
        console.print(f"\n[bold green]Visual summary for {args.video_id}:[/bold green]")
        console.print(f"  {result['visual_summary']}\n")
        console.print(f"[green]✓ Saved to logs/visuals/{args.video_id}_summary.json[/green]")
    except Exception as e:
        console.print(f"[red]✗ Visual sampling failed: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
