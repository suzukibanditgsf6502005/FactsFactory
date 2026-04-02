#!/usr/bin/env python3
"""
run_pipeline.py — PawFactory full pipeline orchestrator
Runs the complete pipeline: download → hook → voice → video → metadata
Usage:
  python scripts/run_pipeline.py
  python scripts/run_pipeline.py --candidates logs/candidates_20250325.json --top-n 2
  python scripts/run_pipeline.py --video-id "abc123" --url "URL" --description "DESC"
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

load_dotenv()
console = Console()

# ── Duration policy constants ────────────────────────────────────────────────
# These mirror the values in video_editor.py. Do not loop video — ever.
MIN_SOURCE_DURATION    = 20.0   # reject clips shorter than this (seconds)
DURATION_SAFETY_MARGIN = 2.0    # audio must fit at least this many seconds before clip end
TARGET_DURATION_FACTOR = 0.85   # initial script budget = clip_duration * this
TARGET_DURATION_MIN    = 20     # floor for target narration (seconds)
TARGET_DURATION_MAX    = 55     # ceiling for target narration (seconds)


def _ffprobe_duration(file_path: str) -> float | None:
    """Return duration of a media file in seconds, or None on failure."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        str(file_path),
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


def _get_clip_duration(vid_id: str) -> float | None:
    """Return duration of the best available clip for vid_id.

    Prefers the smart-clipped version (inbox/{id}_clip.mp4) so the narration
    budget is calculated against the actual segment that will be published,
    not the full raw source.
    """
    inbox = Path(os.getenv("INBOX_DIR", "inbox"))
    clip = inbox / f"{vid_id}_clip.mp4"
    if clip.exists():
        return _ffprobe_duration(str(clip))
    for ext in ("mp4", "webm", "mkv", "mov"):
        p = inbox / f"{vid_id}.{ext}"
        if p.exists():
            return _ffprobe_duration(str(p))
    return None


def _get_audio_duration(vid_id: str) -> float | None:
    inbox = Path(os.getenv("INBOX_DIR", "inbox"))
    p = inbox / f"{vid_id}_voice.mp3"
    return _ffprobe_duration(str(p)) if p.exists() else None


def _log_rejection(vid_id: str, reason: str):
    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    msg = f"[pipeline] {datetime.now().isoformat()} — {vid_id}: REJECTED — {reason}"
    with open(log_dir / "errors.log", "a") as f:
        f.write(msg + "\n")
    console.print(f"[red]✗ REJECTED: {vid_id} — {reason}[/red]")


def _cleanup_rejected(vid_id: str, stage: str, reason: str):
    """
    Remove publishable artifacts from output/ for a rejected video and write
    a lightweight rejection record to logs/rejections/{vid_id}.json.

    Keeps inbox/ source files (raw downloads) so the seen-filter still works
    and re-download is not needed if the item is reprocessed.
    """
    output_dir = Path(os.getenv("OUTPUT_DIR", "output"))
    log_dir = Path(os.getenv("LOG_DIR", "logs"))

    removed = []
    # Remove publishable output artifacts
    for name in (f"{vid_id}_final.mp4", f"{vid_id}_metadata.json"):
        p = output_dir / name
        if p.exists():
            p.unlink()
            removed.append(name)

    # Remove smart clip so it gets regenerated fresh on reprocess
    inbox_dir = Path(os.getenv("INBOX_DIR", "inbox"))
    smart_clip = inbox_dir / f"{vid_id}_clip.mp4"
    if smart_clip.exists():
        smart_clip.unlink()
        removed.append(f"inbox/{vid_id}_clip.mp4")

    # Remove caption caches so they are rebuilt from the current voice on reprocess.
    # Leaving stale .ass files causes caption-voice desync when voice is regenerated.
    captions_dir = log_dir / "captions"
    for name in (f"{vid_id}.ass", f"{vid_id}_voice.srt"):
        p = captions_dir / name
        if p.exists():
            p.unlink()
            removed.append(f"captions/{name}")

    # Write rejection record
    rejections_dir = log_dir / "rejections"
    rejections_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "video_id": vid_id,
        "rejected_at": datetime.now().isoformat(),
        "stage": stage,
        "reason": reason,
        "output_files_removed": removed,
    }
    with open(rejections_dir / f"{vid_id}.json", "w") as f:
        json.dump(record, f, indent=2)

    if removed:
        console.print(f"  [dim]Cleaned output/: {', '.join(removed)}[/dim]")


def run_step(step_name, cmd):
    console.print(f"\n[bold cyan]→ {step_name}[/bold cyan]")
    result = subprocess.run(
        [sys.executable] + cmd,
        capture_output=False,  # show output live
    )
    if result.returncode != 0:
        console.print(f"[red]✗ Step failed: {step_name}[/red]")
        return False
    return True


def process_candidate(candidate):
    vid_id      = candidate["id"]
    url         = candidate["video_url"]
    description = candidate["title"]
    source      = candidate.get("source", "reddit")

    console.print(Panel(
        f"[bold]ID:[/bold] {vid_id}\n"
        f"[bold]Title:[/bold] {description[:80]}\n"
        f"[bold]Viral score:[/bold] {candidate.get('viral_score', '?')}\n"
        f"[bold]Source:[/bold] {source}",
        title=f"Processing: {vid_id}",
        border_style="cyan",
    ))

    # ── Step 1: Download ──────────────────────────────────────────────────────
    if not run_step("Download video", [
        "scripts/sourcing/downloader.py",
        "--url", url,
        "--id", vid_id,
    ]):
        log_error(vid_id, "Download video")
        return False

    # ── Step 1b: Smart clipping — select best segment from source ───────────
    # Scores candidate windows with Claude Vision and extracts the best one
    # to inbox/{id}_clip.mp4. Downstream steps (visual_sampler, video_editor)
    # use the clip automatically. Non-fatal: if it fails, the full source is used.
    clip_path = Path(os.getenv("INBOX_DIR", "inbox")) / f"{vid_id}_clip.mp4"
    if not clip_path.exists():
        if not run_step("Smart clipping", [
            "scripts/production/smart_clipper.py",
            "--video-id", vid_id,
        ]):
            console.print(f"  [yellow]Smart clipping failed — full source will be used[/yellow]")
    else:
        console.print(f"  [dim]Smart clip already exists — skipping[/dim]")

    # ── Duration gate: measure clip, reject if too short ─────────────────────
    clip_duration = _get_clip_duration(vid_id)
    if clip_duration is None:
        _log_rejection(vid_id, "could not measure source clip duration after download")
        return False

    console.print(f"  [dim]Source clip: {clip_duration:.1f}s[/dim]")

    if clip_duration < MIN_SOURCE_DURATION:
        reason = (
            f"source clip too short ({clip_duration:.1f}s < {MIN_SOURCE_DURATION}s minimum). "
            "Use a longer clip or find a different source."
        )
        _log_rejection(vid_id, reason)
        _cleanup_rejected(vid_id, "duration_gate", reason)
        return False

    # Compute narration budget: clip * 0.85, clamped to [TARGET_DURATION_MIN, TARGET_DURATION_MAX]
    target_duration = int(clip_duration * TARGET_DURATION_FACTOR)
    target_duration = max(TARGET_DURATION_MIN, min(TARGET_DURATION_MAX, target_duration))
    console.print(f"  [dim]Narration budget: {target_duration}s (clip {clip_duration:.1f}s × {TARGET_DURATION_FACTOR})[/dim]")

    # ── Step 1c: Smart visual sampling + grounding summary ──────────────────
    # Extracts representative frames and generates a factual visual summary.
    # This summary is passed to hook_generator to prevent hallucinated details.
    #
    # Invalidation: if the source video (or clip) is newer than the existing
    # summary, the summary is stale — regenerate it.
    log_dir_vs = Path(os.getenv("LOG_DIR", "logs"))
    visual_summary_path = log_dir_vs / "visuals" / f"{vid_id}_summary.json"
    _source_for_mtime = clip_path if clip_path.exists() else next(
        (Path(os.getenv("INBOX_DIR", "inbox")) / f"{vid_id}.{ext}"
         for ext in ("mp4", "webm", "mkv", "mov")
         if (Path(os.getenv("INBOX_DIR", "inbox")) / f"{vid_id}.{ext}").exists()),
        None,
    )
    _summary_stale = (
        visual_summary_path.exists()
        and _source_for_mtime is not None
        and _source_for_mtime.stat().st_mtime > visual_summary_path.stat().st_mtime
    )
    if _summary_stale:
        console.print(
            f"  [yellow]Visual summary stale (source newer) — regenerating[/yellow]"
        )
        visual_summary_path.unlink()

    if not visual_summary_path.exists():
        if not run_step("Visual sampling", [
            "scripts/production/visual_sampler.py",
            "--video-id", vid_id,
        ]):
            # Non-fatal: hook generation falls back to description-only grounding
            console.print(f"  [yellow]Visual sampling failed — hook will use description-only grounding[/yellow]")
    else:
        console.print(f"  [dim]Visual summary up-to-date — skipping re-sample[/dim]")

    # ── Step 2: Generate hook + script (grounded by visual summary) ──────────
    if not run_step("Generate hook + script", [
        "scripts/production/hook_generator.py",
        "--video-id", vid_id,
        "--description", description,
        "--source", source,
        "--duration", str(target_duration),
    ]):
        log_error(vid_id, "Generate hook + script")
        return False

    # ── Step 3: Generate voiceover ────────────────────────────────────────────
    # Invalidation: if hook JSON is newer than the cached voice, the voice was
    # generated from a different (older) script. Delete voice + music so they
    # are rebuilt from the current hook.
    _inbox = Path(os.getenv("INBOX_DIR", "inbox"))
    _log   = Path(os.getenv("LOG_DIR",   "logs"))
    _hook_path  = _log  / "hooks" / f"{vid_id}.json"
    _voice_path = _inbox / f"{vid_id}_voice.mp3"
    _music_path = _inbox / f"{vid_id}_voice_music.mp3"
    if _hook_path.exists() and _voice_path.exists():
        if _hook_path.stat().st_mtime > _voice_path.stat().st_mtime:
            console.print(
                f"  [yellow]Hook is newer than cached voice — invalidating voice + music[/yellow]"
            )
            _voice_path.unlink(missing_ok=True)
            _music_path.unlink(missing_ok=True)

    if not run_step("Generate voiceover", [
        "scripts/production/voiceover.py",
        "--video-id", vid_id,
    ]):
        log_error(vid_id, "Generate voiceover")
        return False

    # ── Duration fit check: does audio fit within clip? ───────────────────────
    # If not, run one script shortening pass + regenerate voiceover.
    audio_duration = _get_audio_duration(vid_id)
    if audio_duration is not None:
        budget = clip_duration - DURATION_SAFETY_MARGIN
        if audio_duration > budget:
            console.print(
                f"  [yellow]Audio ({audio_duration:.1f}s) exceeds clip budget "
                f"({budget:.1f}s = {clip_duration:.1f}s − {DURATION_SAFETY_MARGIN}s margin) "
                f"— running script shortening pass[/yellow]"
            )
            max_narration = int(budget)

            if not run_step("Shorten script", [
                "scripts/production/hook_generator.py",
                "--shorten",
                "--video-id", vid_id,
                "--max-duration", str(max_narration),
            ]):
                reason = "script shortening failed"
                _log_rejection(vid_id, reason)
                _cleanup_rejected(vid_id, "script_shortening", reason)
                return False

            # Delete stale voiceover so it regenerates from shortened script
            inbox = Path(os.getenv("INBOX_DIR", "inbox"))
            stale_voice = inbox / f"{vid_id}_voice.mp3"
            stale_voice.unlink(missing_ok=True)
            stale_music  = inbox / f"{vid_id}_voice_music.mp3"
            stale_music.unlink(missing_ok=True)

            if not run_step("Regenerate voiceover (after shortening)", [
                "scripts/production/voiceover.py",
                "--video-id", vid_id,
            ]):
                log_error(vid_id, "Regenerate voiceover (after shortening)")
                return False

            # Final duration check — reject if still overrunning
            audio_duration = _get_audio_duration(vid_id)
            if audio_duration is not None and audio_duration > budget:
                reason = (
                    f"audio ({audio_duration:.1f}s) still exceeds clip budget "
                    f"({budget:.1f}s) after shortening pass. Clip is not viable."
                )
                _log_rejection(vid_id, reason)
                _cleanup_rejected(vid_id, "duration_overrun", reason)
                return False

    # ── Step 4: Mix background music ─────────────────────────────────────────
    if not run_step("Mix background music", [
        "scripts/production/music_mixer.py",
        "--video-id", vid_id,
    ]):
        log_error(vid_id, "Mix background music")
        return False

    # ── Step 5: Assemble video (no looping) ───────────────────────────────────
    if not run_step("Assemble video", [
        "scripts/production/video_editor.py",
        "--video-id", vid_id,
    ]):
        log_error(vid_id, "Assemble video")
        return False

    # ── Step 6: Generate metadata ─────────────────────────────────────────────
    if not run_step("Generate metadata", [
        "scripts/publishing/metadata_gen.py",
        "--video-id", vid_id,
    ]):
        log_error(vid_id, "Generate metadata")
        return False

    # ── Step 7: Quality check ─────────────────────────────────────────────────
    # Invalidation: delete any prior QC JSON before running so a partial or
    # failed previous run cannot leave stale data that gates this run.
    # The QC result is only trusted if the step exits 0.
    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    qc_path = log_dir / "qc" / f"{vid_id}_qc.json"
    qc_path.unlink(missing_ok=True)

    qc_step_ok = run_step("Quality check", [
        "scripts/production/quality_check.py",
        "--video-id", vid_id,
    ])
    if not qc_step_ok:
        log_error(vid_id, "Quality check")
        console.print(
            f"  [yellow]QC step failed (non-zero exit) — no stale data read. "
            f"Video enqueued for human review.[/yellow]"
        )

    # Read QC verdict only if the step succeeded and wrote a fresh result.
    qc_verdict = None
    if qc_step_ok and qc_path.exists():
        with open(qc_path) as _f:
            qc_result = json.load(_f)
        qc_verdict = qc_result.get("verdict")
        qc_score   = qc_result.get("weighted_score", "?")
        if qc_verdict == "FAIL":
            console.print(f"\n[red]✗ QC FAIL ({qc_score}/10) — {vid_id}[/red]")
            console.print(f"  [dim]Hard-fail dimension: {qc_result.get('hard_fail_dim', '—')}[/dim]")
            console.print(f"  [dim]Issues: {'; '.join(qc_result.get('issues', [])[:2])}[/dim]")
            reason = f"QC FAIL score={qc_score} dim={qc_result.get('hard_fail_dim')}"
            _log_rejection(vid_id, reason)
            _cleanup_rejected(vid_id, "qc_fail", reason)
            # Enqueue with FAIL verdict so human can inspect/override
            _enqueue_candidate(vid_id, description)
            return False
        else:
            console.print(f"  [green]QC PASS ({qc_score}/10)[/green]")
    else:
        console.print(f"  [yellow]QC result unavailable — skipping gate[/yellow]")

    # Mark as processed
    log_processed(vid_id, description)

    # ── Step 8: Enqueue for review / publishing ───────────────────────────────
    _enqueue_candidate(vid_id, description)

    console.print(f"\n[bold green]✓ {vid_id} complete → queued for review[/bold green]")
    console.print(f"  [dim]Review: python scripts/publishing/publish_queue.py --show {vid_id}[/dim]")
    return True


def _enqueue_candidate(video_id: str, title: str):
    """Add a produced short to the publish queue (silently ignore errors)."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from scripts.publishing.publish_queue import enqueue
        enqueue(video_id)
    except Exception as e:
        console.print(f"  [dim]Note: could not auto-enqueue {video_id}: {e}[/dim]")


def log_error(video_id, step):
    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(log_dir / "errors.log", "a") as f:
        f.write(f"[pipeline] {datetime.now().isoformat()} — {video_id} failed at: {step}\n")


def log_processed(video_id, title):
    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    processed_path = log_dir / "processed.json"

    existing = []
    if processed_path.exists():
        with open(processed_path) as f:
            existing = json.load(f)

    existing.append({
        "id": video_id,
        "title": title,
        "processed_at": datetime.now().isoformat(),
        "status": "ready_for_upload",
    })

    with open(processed_path, "w") as f:
        json.dump(existing, f, indent=2)


def get_already_processed():
    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    processed_path = log_dir / "processed.json"
    if not processed_path.exists():
        return set()
    with open(processed_path) as f:
        data = json.load(f)
    return {item["id"] for item in data}


def main():
    parser = argparse.ArgumentParser(description="PawFactory Pipeline Orchestrator")
    parser.add_argument("--candidates", default=None,
                        help="Candidates JSON file (default: latest in logs/)")
    parser.add_argument("--top-n", type=int, default=2,
                        help="Process top N candidates (default: 2)")
    parser.add_argument("--video-id", help="Single video ID")
    parser.add_argument("--url", help="Single video URL")
    parser.add_argument("--description", help="Single video description")
    parser.add_argument("--skip-processed", action="store_true", default=True,
                        help="Skip already processed IDs (default: True)")
    args = parser.parse_args()

    console.print(Panel(
        "PawFactory Production Pipeline",
        border_style="green",
        subtitle=datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))

    # Single video mode
    if args.video_id and args.url:
        candidate = {
            "id": args.video_id,
            "video_url": args.url,
            "title": args.description or args.video_id,
            "source": "manual",
            "viral_score": "manual",
        }
        process_candidate(candidate)
        return

    # Batch mode — find candidates file
    log_dir = Path(os.getenv("LOG_DIR", "logs"))

    if args.candidates:
        candidates_path = Path(args.candidates)
    else:
        # Find latest candidates file
        files = sorted(log_dir.glob("candidates_*.json"), reverse=True)
        if not files:
            console.print("[red]ERROR: No candidates file found. Run reddit_scraper.py first.[/red]")
            sys.exit(1)
        candidates_path = files[0]
        console.print(f"[dim]Using: {candidates_path.name}[/dim]")

    with open(candidates_path) as f:
        candidates = json.load(f)

    if not candidates:
        console.print("[yellow]No candidates found in file.[/yellow]")
        sys.exit(0)

    # Filter already processed
    already_done = get_already_processed() if args.skip_processed else set()
    to_process = [c for c in candidates if c["id"] not in already_done]

    if not to_process:
        console.print("[yellow]All candidates already processed.[/yellow]")
        sys.exit(0)

    top = to_process[:args.top_n]
    console.print(f"[cyan]Processing {len(top)} candidates (skipping {len(already_done)} already done)[/cyan]")

    success = 0
    failed = 0
    for c in top:
        ok = process_candidate(c)
        if ok:
            success += 1
        else:
            failed += 1
            if failed >= 3:
                console.print("[red]3 consecutive failures — stopping pipeline. Check logs/errors.log[/red]")
                break

    console.print(Panel(
        f"[green]✓ Success: {success}[/green]  [red]✗ Failed: {failed}[/red]\n"
        f"Ready for upload in: output/",
        title="Pipeline complete",
        border_style="green" if failed == 0 else "yellow",
    ))


if __name__ == "__main__":
    main()
