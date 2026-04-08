#!/usr/bin/env python3
"""
assemble_video.py — FactsFactory video assembler

Concatenates animated scene clips, adds voiceover and optional background music,
produces a final 1080x1920 9:16 MP4 ready for QC and publishing.

Usage:
  python scripts/production/assemble_video.py --video-id wasp-test-001
  python scripts/production/assemble_video.py --video-id wasp-test-001 --no-music

Output:
  output/{video_id}_final.mp4
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _run(cmd: list, label: str) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed [{label}]:\n{result.stderr[-600:]}")
    return result


def _get_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip())


def assemble_video(
    video_id: str,
    add_music: bool = True,
    music_volume: float = 0.08,
) -> Path:
    """
    Concatenate animated clips + voiceover + optional music → final MP4.
    Returns path to output file.
    """
    anim_dir = Path(f"inbox/{video_id}/animated")
    inbox_dir = Path("inbox")
    output_dir = Path(os.getenv("OUTPUT_DIR", "output"))
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find animated clips in order
    clips = sorted(anim_dir.glob("scene_*.mp4"))
    if not clips:
        raise RuntimeError(f"No animated clips found in {anim_dir}")

    # Find voiceover
    voice_path = inbox_dir / f"{video_id}_voice.mp3"
    if not voice_path.exists():
        raise RuntimeError(f"Voiceover not found: {voice_path}")

    voice_duration = _get_duration(voice_path)
    print(f"[assemble_video] {len(clips)} clips, voice: {voice_duration:.2f}s", flush=True)

    final_path = output_dir / f"{video_id}_final.mp4"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Step 1: concatenate video clips (no audio)
        concat_file = tmp / "concat.txt"
        concat_file.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))

        silent_path = tmp / "silent.mp4"
        print("[assemble_video] Concatenating clips...", flush=True)
        _run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-r", "30",
            str(silent_path),
        ], "concat")

        # Step 2: mix voiceover (+ optional music)
        if add_music:
            music_catalog = Path("assets/music/catalog.json")
            music_track = _pick_music_track(music_catalog)
        else:
            music_track = None

        muxed_path = tmp / "muxed.mp4"

        if music_track and Path(music_track).exists():
            print(f"[assemble_video] Mixing music: {music_track}", flush=True)
            _run([
                "ffmpeg", "-y",
                "-i", str(silent_path),
                "-i", str(voice_path),
                "-i", music_track,
                "-filter_complex",
                f"[1:a]volume=1.0[voice];[2:a]volume={music_volume}[music];[voice][music]amix=inputs=2:duration=first[audio]",
                "-map", "0:v", "-map", "[audio]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                str(muxed_path),
            ], "mux+music")
        else:
            print("[assemble_video] Adding voiceover (no music)...", flush=True)
            _run([
                "ffmpeg", "-y",
                "-i", str(silent_path),
                "-i", str(voice_path),
                "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                str(muxed_path),
            ], "mux_voice")

        # Step 3: copy to output
        import shutil
        shutil.copy2(muxed_path, final_path)

    out_size = final_path.stat().st_size // (1024 * 1024)
    final_duration = _get_duration(final_path)
    print(f"[assemble_video] Final: {final_path} ({out_size}MB, {final_duration:.1f}s)", flush=True)
    return final_path


def _pick_music_track(catalog_path: Path) -> str | None:
    """Pick a background music track from the catalog. Returns file path or None."""
    if not catalog_path.exists():
        return None
    try:
        catalog = json.loads(catalog_path.read_text())
        # Prefer 'dramatic' or 'tense' for weird_biology content
        for category in ["dramatic", "tense", "hopeful"]:
            tracks = catalog.get(category, [])
            if tracks:
                # Return the first available track file
                for track in tracks:
                    path = track.get("file") or track.get("path", "")
                    if path and Path(path).exists():
                        return path
    except Exception:
        pass
    return None


def main():
    parser = argparse.ArgumentParser(description="Assemble final video from animated scenes + voiceover")
    parser.add_argument("--video-id", required=True, help="Video ID")
    parser.add_argument("--no-music", action="store_true", help="Skip background music")
    parser.add_argument("--music-volume", type=float, default=0.08,
                        help="Background music volume (0.0–1.0, default: 0.08)")
    args = parser.parse_args()

    try:
        out = assemble_video(
            video_id=args.video_id,
            add_music=not args.no_music,
            music_volume=args.music_volume,
        )
        print(f"[assemble_video] Done: {out}")
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
