#!/usr/bin/env python3
"""
main.py — FactsFactory multi-style production pipeline

Runs the full short-form video pipeline from topic to finished mp4.

Styles:
  cinematic  — AI-generated video (Veo/Runway) or FLUX stills + Ken Burns
  cartoon    — Flat illustration AI images + Ken Burns animation
  motion     — Kinetic typography (no image generation required)
  all        — Generate all 3 styles from the same script + voiceover

Usage:
  python main.py --style cinematic
  python main.py --style motion
  python main.py --style cartoon
  python main.py --style all
  python main.py --style cinematic --category weird_biology
  python main.py --style motion --script-file logs/scripts/20260403_wasp.json
  python main.py --style all --no-music --no-captions
  python main.py --style motion --dry-run

Output:
  output/{video_id}_cinematic.mp4
  output/{video_id}_cartoon.mp4
  output/{video_id}_motion.mp4
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Project root on sys.path ──────────────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scripts.run_spine import run_spine
from scripts.production.voiceover import generate_voiceover
from scripts.production.assemble_video import assemble_video
from scripts.production.ass_captions import generate_ass_captions, burn_ass_captions
from scripts.production.scene_generators import get_generator, STYLES

CATEGORIES = [
    "animal_facts", "weird_biology", "history", "science", "space",
    "engineering", "psychology", "records",
]


def _make_video_id(topic: str, style: str) -> str:
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = topic[:28].lower().replace(" ", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    return f"{date_str}_{slug}_{style}"


def _write_hook_compat(video_id: str, script_data: dict) -> Path:
    """
    Write logs/hooks/{video_id}.json in PawFactory-compatible format.
    voiceover.py reads this file when called via CLI; generate_voiceover()
    takes the text directly so we only need this for reference.
    """
    hook_dir = Path(os.getenv("LOG_DIR", "logs")) / "hooks"
    hook_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hook_dir / f"{video_id}.json"
    hook_path.write_text(json.dumps({
        "video_id": video_id,
        "topic": script_data["topic"],
        "hook": script_data.get("hook", ""),
        "full_script": script_data["full_script"],
    }, indent=2))
    return hook_path


def _get_voice_duration(voice_path: Path) -> float:
    import subprocess
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(voice_path)],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip())


def _produce_one_style(
    style: str,
    storyboard: dict,
    script_data: dict,
    base_video_id: str,
    voice_path: Path,
    voice_duration: float,
    add_music: bool,
    add_captions: bool,
    output_dir: Path,
    dry_run: bool,
) -> Path | None:
    """Run scene generation + assembly + captions for one style. Returns output path."""

    sep = "─" * 60
    print(f"\n{sep}", flush=True)
    print(f"STYLE: {style.upper()}", flush=True)
    print(sep, flush=True)

    video_id = f"{base_video_id}_{style}"

    if dry_run:
        print(f"  [dry-run] Would generate {storyboard['total_scenes']} scenes as {style}", flush=True)
        print(f"  [dry-run] Output: output/{video_id}.mp4", flush=True)
        return None

    # Copy voice file so assemble_video can find it under this video_id
    inbox_voice = Path("inbox") / f"{video_id}_voice.mp3"
    if not inbox_voice.exists():
        shutil.copy2(voice_path, inbox_voice)

    # ── Scene generation (style-specific) ────────────────────────────────────
    generator = get_generator(style)
    clips = generator.generate_scenes(
        storyboard=storyboard,
        video_id=video_id,
        voice_duration=voice_duration,
    )

    if not clips:
        print(f"  [ERROR] No clips generated for style {style}", file=sys.stderr, flush=True)
        return None

    # ── Assembly: concat clips + voice + optional music ───────────────────────
    print(f"\n[{style}] Assembling video...", flush=True)
    raw_path = output_dir / f"{video_id}_raw.mp4"
    try:
        assembled = assemble_video(
            video_id=video_id,
            add_music=add_music,
        )
    except RuntimeError as e:
        print(f"  [ERROR] Assembly failed: {e}", file=sys.stderr, flush=True)
        return None

    # ── Captions ─────────────────────────────────────────────────────────────
    final_path = output_dir / f"{video_id}.mp4"

    if add_captions:
        print(f"[{style}] Adding captions...", flush=True)
        captions_dir = Path(os.getenv("LOG_DIR", "logs")) / "captions"
        ass_path = generate_ass_captions(
            audio_path=str(voice_path),
            output_dir=str(captions_dir),
            video_id=base_video_id,   # share captions across styles (same script)
            script_text=script_data["full_script"],
        )
        if ass_path:
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
                tmp_cap = tf.name
            ok = burn_ass_captions(str(assembled), ass_path, tmp_cap)
            if ok:
                shutil.move(tmp_cap, final_path)
            else:
                Path(tmp_cap).unlink(missing_ok=True)
                shutil.copy2(assembled, final_path)
        else:
            shutil.copy2(assembled, final_path)
        # Remove intermediate raw file
        assembled.unlink(missing_ok=True)
    else:
        shutil.move(str(assembled), final_path)

    size_mb = final_path.stat().st_size / (1024 * 1024)
    print(f"\n✓ [{style}] Done: {final_path.name} ({size_mb:.1f} MB)", flush=True)
    return final_path


def run(
    style: str,
    category: str = "animal_facts",
    topic_file: str | None = None,
    research_file: str | None = None,
    script_file: str | None = None,
    target_duration: int = 35,
    add_music: bool = True,
    add_captions: bool = True,
    dry_run: bool = False,
) -> dict[str, Path]:
    """
    Run the full FactsFactory pipeline.

    Args:
        style: "cinematic" | "cartoon" | "motion" | "all"
        ...all others match run_spine.py args...

    Returns:
        Dict mapping style → output Path
    """
    sep = "═" * 60
    print(f"\n{sep}", flush=True)
    print(f"  FactsFactory — style: {style}", flush=True)
    print(sep, flush=True)

    styles_to_run = STYLES if style == "all" else [style]

    # ── Text spine (shared across all styles) ─────────────────────────────────
    print("\n── Text Spine ──", flush=True)
    spine = run_spine(
        category=category,
        topic_file=topic_file,
        research_file=research_file,
        script_file=script_file,
        target_duration=target_duration,
        dry_run=dry_run,
    )

    if dry_run:
        print("\n[dry-run] Text spine complete. Skipping media generation.", flush=True)
        return {}

    storyboard = spine["storyboard"]
    script_data = spine["script"]

    # ── Voiceover (shared — generated once) ──────────────────────────────────
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "pFZP5JQG7iQjIQuC4Bku")
    inbox_dir = Path("inbox")
    inbox_dir.mkdir(exist_ok=True)

    # Base ID without style suffix (voice is shared)
    base_video_id = _make_video_id(script_data["topic"], styles_to_run[0])
    # Strip the style suffix from base_video_id for the voice file
    base_video_id = base_video_id.rsplit("_", 1)[0]

    print(f"\n── Voiceover (base id: {base_video_id}) ──", flush=True)
    voice_path = inbox_dir / f"{base_video_id}_voice.mp3"

    if not voice_path.exists():
        voice_result = generate_voiceover(
            video_id=base_video_id,
            script_text=script_data["full_script"],
            voice_id=voice_id,
            output_dir=str(inbox_dir),
        )
        if not voice_result:
            print("ERROR: Voiceover generation failed — aborting.", file=sys.stderr)
            sys.exit(1)
        voice_path = Path(voice_result)
    else:
        print(f"  Voiceover already exists: {voice_path.name}", flush=True)

    voice_duration = _get_voice_duration(voice_path)
    print(f"  Voice duration: {voice_duration:.2f}s", flush=True)

    # Write hook-compat JSON for reference
    _write_hook_compat(base_video_id, script_data)

    # ── Scene generation + assembly per style ─────────────────────────────────
    output_dir = Path(os.getenv("OUTPUT_DIR", "output"))
    output_dir.mkdir(exist_ok=True)

    results = {}
    for s in styles_to_run:
        out = _produce_one_style(
            style=s,
            storyboard=storyboard,
            script_data=script_data,
            base_video_id=base_video_id,
            voice_path=voice_path,
            voice_duration=voice_duration,
            add_music=add_music,
            add_captions=add_captions,
            output_dir=output_dir,
            dry_run=dry_run,
        )
        if out:
            results[s] = out

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'═' * 60}", flush=True)
    print("PIPELINE COMPLETE", flush=True)
    print(f"  Topic:  {script_data['topic']}", flush=True)
    print(f"  Script: {script_data['word_count']} words, ~{script_data['estimated_duration_seconds']}s", flush=True)
    for s, path in results.items():
        size = path.stat().st_size / (1024 * 1024)
        print(f"  {s:12s} → {path.name} ({size:.1f} MB)", flush=True)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="FactsFactory — multi-style AI Shorts pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --style motion
  python main.py --style cinematic --category weird_biology
  python main.py --style all --no-music
  python main.py --style cartoon --script-file logs/scripts/20260403_wasp.json
  python main.py --style motion --dry-run
        """,
    )

    parser.add_argument(
        "--style",
        choices=STYLES + ["all"],
        required=True,
        help="Visual style (or 'all' to generate all 3)",
    )
    parser.add_argument(
        "--category",
        choices=CATEGORIES,
        default="animal_facts",
        help="Content category for topic selection (default: animal_facts)",
    )
    parser.add_argument("--topic-file",    help="Resume from saved topic JSON")
    parser.add_argument("--research-file", help="Resume from saved research JSON")
    parser.add_argument("--script-file",   help="Resume from saved script JSON")
    parser.add_argument(
        "--target-duration",
        type=int,
        default=35,
        help="Target narration length in seconds (default: 35)",
    )
    parser.add_argument("--no-music",    action="store_true", help="Skip background music")
    parser.add_argument("--no-captions", action="store_true", help="Skip caption burning")
    parser.add_argument("--dry-run",     action="store_true", help="Text spine only — no media")

    args = parser.parse_args()

    run(
        style=args.style,
        category=args.category,
        topic_file=args.topic_file,
        research_file=args.research_file,
        script_file=args.script_file,
        target_duration=args.target_duration,
        add_music=not args.no_music,
        add_captions=not args.no_captions,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
