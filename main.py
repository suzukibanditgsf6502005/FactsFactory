#!/usr/bin/env python3
"""
main.py — FactsFactory production pipeline

Two-phase workflow (recommended for Veo ingest):

  Phase 1 — Spine only (topic → script → storyboard, no media):
    python main.py --spine-only --category science
    → saves script + storyboard, prints video_id

  Phase 2 — Render only (scene gen + voice + assembly):
    python main.py --render-only --style all \\
      --video-id <video_id> \\
      --script-file logs/scripts/TIMESTAMP_topic.json \\
      --storyboard-file logs/storyboards/TIMESTAMP_topic.json

Full pipeline (spine + render in one step):
    python main.py --style cartoon --category science
    python main.py --style cinematic --category weird_biology
    python main.py --style all --category animal_facts

Styles:
  cinematic  — hybrid: manual Veo clips (inbox/<id>_cinematic/veo/) + FLUX fallback
  cartoon    — infographic/comic AI images + Ken Burns animation  (primary style)
  all        — generate cinematic + cartoon from the same script + voiceover

Note: motion style is temporarily disabled.

Manual Veo ingest workflow:
  1. python main.py --spine-only --category science
     → note the video_id printed at the end

  2. Generate Veo clips externally, place them:
       inbox/<video_id>_cinematic/veo/scene_000.mp4
       inbox/<video_id>_cinematic/veo/scene_002.mp4
     (optional manifest.json in that folder for explicit mapping)

  3. python main.py --render-only --style all \\
       --video-id <video_id> \\
       --script-file logs/scripts/TIMESTAMP_topic.json \\
       --storyboard-file logs/storyboards/TIMESTAMP_topic.json

     Result: cinematic uses Veo clips where present, FLUX for the rest.
             cartoon runs full infographic/comic generation.

Output:
  output/{video_id}_cinematic.mp4
  output/{video_id}_cartoon.mp4
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_base_video_id(topic: str) -> str:
    """Return a base video ID (no style suffix) from a topic string."""
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = topic[:28].lower().replace(" ", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    return f"{date_str}_{slug}"


def _write_hook_compat(video_id: str, script_data: dict) -> Path:
    """
    Write logs/hooks/{video_id}.json in PawFactory-compatible format.
    voiceover.py reads this when called via CLI; generate_voiceover() takes
    text directly so this is reference-only.
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


# ── Per-style scene generation + assembly ────────────────────────────────────

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
            video_id=base_video_id,   # shared across styles — same script, same audio
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
        assembled.unlink(missing_ok=True)
    else:
        shutil.move(str(assembled), final_path)

    size_mb = final_path.stat().st_size / (1024 * 1024)
    print(f"\n✓ [{style}] Done: {final_path.name} ({size_mb:.1f} MB)", flush=True)
    return final_path


# ── Render phase (shared by full pipeline and render-only) ───────────────────

def _run_render(
    storyboard: dict,
    script_data: dict,
    base_video_id: str,
    styles_to_run: list[str],
    add_music: bool,
    add_captions: bool,
    dry_run: bool,
) -> dict[str, Path]:
    """
    Run scene generation + voiceover + assembly + captions for all requested styles.
    Returns dict mapping style → output Path.
    """
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "pFZP5JQG7iQjIQuC4Bku")
    inbox_dir = Path("inbox")
    inbox_dir.mkdir(exist_ok=True)

    # ── Voiceover (shared — generated once across all styles) ─────────────────
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

    return results


# ── Public pipeline entry points ─────────────────────────────────────────────

def run_spine_only(
    category: str = "animal_facts",
    topic_file: str | None = None,
    research_file: str | None = None,
    script_file: str | None = None,
    target_duration: int = 35,
) -> dict:
    """
    Phase 1 only: run the text spine (topic → research → script → storyboard).
    Saves all artifacts to logs/. Prints the base video_id for use in Phase 2.
    Returns the spine result dict.
    """
    sep = "═" * 60
    print(f"\n{sep}", flush=True)
    print("  FactsFactory — SPINE ONLY", flush=True)
    print(sep, flush=True)

    spine = run_spine(
        category=category,
        topic_file=topic_file,
        research_file=research_file,
        script_file=script_file,
        target_duration=target_duration,
        dry_run=False,
    )

    script_data = spine["script"]
    base_video_id = _make_base_video_id(script_data["topic"])

    print(f"\n{'═' * 60}", flush=True)
    print("SPINE GENERATED", flush=True)
    print(f"  Topic:          {script_data['topic']}", flush=True)
    print(f"  Script:         {script_data['word_count']} words, "
          f"~{script_data['estimated_duration_seconds']}s", flush=True)
    print(f"  video_id:       {base_video_id}", flush=True)
    print(f"  script_file:    {spine['script_file']}", flush=True)
    print(f"  storyboard_file:{spine['storyboard_file']}", flush=True)
    print(f"\nNext steps:", flush=True)
    print(f"  1. (Optional) Generate Veo clips and place in:", flush=True)
    print(f"       inbox/{base_video_id}_cinematic/veo/scene_000.mp4", flush=True)
    print(f"  2. Run render phase:", flush=True)
    print(f"       python main.py --render-only --style all \\", flush=True)
    print(f"         --video-id {base_video_id} \\", flush=True)
    print(f"         --script-file {spine['script_file']} \\", flush=True)
    print(f"         --storyboard-file {spine['storyboard_file']}", flush=True)

    spine["base_video_id"] = base_video_id
    return spine


def run_render_only(
    style: str,
    video_id: str,
    script_file: str,
    storyboard_file: str,
    add_music: bool = True,
    add_captions: bool = True,
) -> dict[str, Path]:
    """
    Phase 2 only: skip spine, load existing script + storyboard, run full media pipeline.

    Cinematic style will automatically check inbox/<video_id>_cinematic/veo/ for
    manually provided Veo clips and use them in place of fallback generation.

    Returns dict mapping style → output Path.
    """
    sep = "═" * 60
    print(f"\n{sep}", flush=True)
    print(f"  FactsFactory — RENDER ONLY (style: {style})", flush=True)
    print(sep, flush=True)

    # Load spine artifacts
    sp = Path(script_file)
    sb = Path(storyboard_file)

    if not sp.exists():
        print(f"ERROR: script file not found: {sp}", file=sys.stderr)
        sys.exit(1)
    if not sb.exists():
        print(f"ERROR: storyboard file not found: {sb}", file=sys.stderr)
        sys.exit(1)

    script_data = json.loads(sp.read_text())
    storyboard = json.loads(sb.read_text())

    print(f"\n── Reusing existing spine ──", flush=True)
    print(f"  Loaded script from:     {sp}", flush=True)
    print(f"  Loaded storyboard from: {sb}", flush=True)
    print(f"  video_id:               {video_id}", flush=True)
    print(f"  topic:                  {script_data['topic']}", flush=True)

    styles_to_run = STYLES if style == "all" else [style]

    results = _run_render(
        storyboard=storyboard,
        script_data=script_data,
        base_video_id=video_id,
        styles_to_run=styles_to_run,
        add_music=add_music,
        add_captions=add_captions,
        dry_run=False,
    )

    # Summary
    print(f"\n{'═' * 60}", flush=True)
    print("RENDER COMPLETE", flush=True)
    print(f"  Topic:  {script_data['topic']}", flush=True)
    for s, path in results.items():
        size = path.stat().st_size / (1024 * 1024)
        print(f"  {s:12s} → {path.name} ({size:.1f} MB)", flush=True)

    return results


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
    video_id: str | None = None,
) -> dict[str, Path]:
    """
    Full pipeline: spine + render in one step.

    Args:
        style:     "cinematic" | "cartoon" | "all"
        video_id:  Override auto-generated base video ID. Use to resume a run
                   and pick up Veo clips from inbox/<video_id>_cinematic/veo/.
    Returns:
        Dict mapping style → output Path.
    """
    sep = "═" * 60
    print(f"\n{sep}", flush=True)
    print(f"  FactsFactory — style: {style}", flush=True)
    print(sep, flush=True)

    styles_to_run = STYLES if style == "all" else [style]

    # ── Text spine ────────────────────────────────────────────────────────────
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

    # Base ID (without style suffix) — shared voice + captions across styles
    if video_id:
        base_video_id = video_id
        print(f"  Using provided video_id: {base_video_id}", flush=True)
    else:
        base_video_id = _make_base_video_id(script_data["topic"])

    # ── Render ────────────────────────────────────────────────────────────────
    results = _run_render(
        storyboard=storyboard,
        script_data=script_data,
        base_video_id=base_video_id,
        styles_to_run=styles_to_run,
        add_music=add_music,
        add_captions=add_captions,
        dry_run=dry_run,
    )

    # Summary
    print(f"\n{'═' * 60}", flush=True)
    print("PIPELINE COMPLETE", flush=True)
    print(f"  Topic:  {script_data['topic']}", flush=True)
    print(f"  Script: {script_data['word_count']} words, ~{script_data['estimated_duration_seconds']}s", flush=True)
    for s, path in results.items():
        size = path.stat().st_size / (1024 * 1024)
        print(f"  {s:12s} → {path.name} ({size:.1f} MB)", flush=True)

    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="FactsFactory — AI Shorts pipeline (2-phase or full)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:

  Spine only (Phase 1 — generate script + storyboard, no media):
    python main.py --spine-only --category science
    python main.py --spine-only --category animal_facts --target-duration 40

  Render only (Phase 2 — media from existing spine):
    python main.py --render-only --style all \\
      --video-id 20260409_mantis-shrimp \\
      --script-file logs/scripts/20260409_123456_mantis-shrimp.json \\
      --storyboard-file logs/storyboards/20260409_123456_mantis-shrimp.json

  Full pipeline (spine + render):
    python main.py --style cartoon --category weird_biology
    python main.py --style cinematic --category animal_facts
    python main.py --style all --no-music
    python main.py --style cartoon --script-file logs/scripts/20260403_wasp.json --dry-run

Note: motion style is temporarily disabled.
        """,
    )

    # ── Mode flags ────────────────────────────────────────────────────────────
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--spine-only",
        action="store_true",
        help="Phase 1: run spine only (topic → script → storyboard). No media generated.",
    )
    mode.add_argument(
        "--render-only",
        action="store_true",
        help=(
            "Phase 2: skip spine, render from existing files. "
            "Requires --style, --video-id, --script-file, --storyboard-file."
        ),
    )

    # ── Style ─────────────────────────────────────────────────────────────────
    parser.add_argument(
        "--style",
        choices=STYLES + ["all"],
        default=None,
        help=(
            "Visual style: cinematic | cartoon | all. "
            "Required unless --spine-only. "
            "'all' generates cinematic + cartoon from the same voiceover."
        ),
    )

    # ── Spine inputs ──────────────────────────────────────────────────────────
    parser.add_argument(
        "--category",
        choices=CATEGORIES,
        default="animal_facts",
        help="Content category for topic selection (default: animal_facts)",
    )
    parser.add_argument("--topic-file",       help="Resume from saved topic JSON")
    parser.add_argument("--research-file",    help="Resume from saved research JSON")
    parser.add_argument("--script-file",      help="Resume from saved script JSON (or provide to render-only)")
    parser.add_argument("--storyboard-file",  help="Path to storyboard JSON (required for --render-only)")
    parser.add_argument(
        "--target-duration",
        type=int,
        default=35,
        help="Target narration length in seconds (default: 35)",
    )

    # ── Render controls ───────────────────────────────────────────────────────
    parser.add_argument(
        "--video-id",
        help=(
            "Base video ID (without style suffix). "
            "Required for --render-only. "
            "For full pipeline: overrides auto-generated ID to resume a run "
            "or pick up manual Veo clips from inbox/<video_id>_cinematic/veo/."
        ),
    )
    parser.add_argument("--no-music",    action="store_true", help="Skip background music")
    parser.add_argument("--no-captions", action="store_true", help="Skip caption burning")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Full pipeline only: run spine, print outputs, skip all media generation.",
    )

    args = parser.parse_args()

    # ── Validate mode-specific requirements ───────────────────────────────────
    if args.spine_only:
        if args.style is not None:
            parser.error("--style is not used with --spine-only")
        if args.render_only:
            parser.error("--spine-only and --render-only are mutually exclusive")

        run_spine_only(
            category=args.category,
            topic_file=args.topic_file,
            research_file=args.research_file,
            script_file=args.script_file,
            target_duration=args.target_duration,
        )

    elif args.render_only:
        missing = []
        if not args.style:
            missing.append("--style")
        if not args.video_id:
            missing.append("--video-id")
        if not args.script_file:
            missing.append("--script-file")
        if not args.storyboard_file:
            missing.append("--storyboard-file")
        if missing:
            parser.error(f"--render-only requires: {', '.join(missing)}")

        run_render_only(
            style=args.style,
            video_id=args.video_id,
            script_file=args.script_file,
            storyboard_file=args.storyboard_file,
            add_music=not args.no_music,
            add_captions=not args.no_captions,
        )

    else:
        # Full pipeline mode
        if not args.style:
            parser.error("--style is required (choose from: cinematic, cartoon, all)")

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
            video_id=args.video_id,
        )


if __name__ == "__main__":
    main()
