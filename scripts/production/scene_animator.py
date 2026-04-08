#!/usr/bin/env python3
"""
scene_animator.py — FactsFactory scene animator

Converts still scene images into short video clips with Ken Burns / motion effects.
Each clip is timed to match its scene's narration duration.

Usage:
  python scripts/production/scene_animator.py --video-id wasp-test-001
  python scripts/production/scene_animator.py --video-id wasp-test-001 --storyboard logs/storyboards/...json
  python scripts/production/scene_animator.py --video-id wasp-test-001 --voice-duration 48.43

Motion types (from storyboard):
  static        — hold image, no movement
  slow_zoom_in  — gradual zoom in (1.0 → 1.1 scale)
  slow_zoom_out — gradual zoom out (1.1 → 1.0 scale)
  pan_right     — pan left to right
  pan_left      — pan right to left

Output per scene:
  inbox/{video_id}/animated/scene_000.mp4
  inbox/{video_id}/animated/scene_001.mp4
  ...
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


OUTPUT_RES = "1080x1920"
FPS = 30


def _run(cmd: list, label: str) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed [{label}]: {result.stderr[-400:]}")


def _animate_scene(
    image_path: Path,
    out_path: Path,
    duration: float,
    motion: str,
) -> None:
    """Convert one still image into a video clip with motion effect."""
    frames = max(1, int(duration * FPS))
    w, h = 1080, 1920

    if motion == "slow_zoom_in":
        # zoom from 1.0 → 1.1 over duration
        vf = (
            f"scale=8000:-1,"
            f"zoompan=z='min(zoom+0.0012,1.1)':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={FPS},"
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black"
        )
    elif motion == "slow_zoom_out":
        # zoom from 1.1 → 1.0 over duration
        vf = (
            f"scale=8000:-1,"
            f"zoompan=z='max(zoom-0.0012,1.0)':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={FPS},"
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black"
        )
    elif motion == "pan_right":
        # pan right: x sweeps 0 → iw*(1-1/1.05)=iw*0.04762 using output frame number 'on'
        step = max(1, frames - 1)
        vf = (
            f"scale=8000:-1,"
            f"zoompan=z=1.05:d={frames}:"
            f"x='on*iw*0.04762/{step}':y='0':"
            f"s={w}x{h}:fps={FPS},"
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black"
        )
    elif motion == "pan_left":
        # pan left: x sweeps iw*0.04762 → 0 using output frame number 'on'
        step = max(1, frames - 1)
        vf = (
            f"scale=8000:-1,"
            f"zoompan=z=1.05:d={frames}:"
            f"x='iw*0.04762*({step}-on)/{step}':y='0':"
            f"s={w}x{h}:fps={FPS},"
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black"
        )
    else:
        # static: no motion — simple scale + pad to 1080x1920
        vf = (
            f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},"
            f"setsar=1"
        )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-vf", vf,
        "-t", str(duration),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        "-an",
        str(out_path),
    ]
    _run(cmd, f"scene_{out_path.stem}")


def animate_scenes(
    video_id: str,
    storyboard: dict,
    voice_duration: float | None = None,
) -> list[Path]:
    """
    Animate all scenes for a video. Returns list of animated clip paths.

    voice_duration: total TTS duration in seconds. If provided, scene durations
                    are proportionally scaled to sum to voice_duration.
    """
    scenes_dir = Path(f"inbox/{video_id}/scenes")
    anim_dir = Path(f"inbox/{video_id}/animated")
    anim_dir.mkdir(parents=True, exist_ok=True)

    scenes = storyboard["scenes"]

    # Compute per-scene durations
    if voice_duration:
        # Distribute voice_duration proportionally to storyboard scene durations
        total_storyboard = sum(s["estimated_duration_seconds"] for s in scenes)
        scale = voice_duration / total_storyboard if total_storyboard > 0 else 1.0
        durations = [s["estimated_duration_seconds"] * scale for s in scenes]
        # Clamp: ensure no scene < 2s and sum = voice_duration exactly
        durations = [max(2.0, d) for d in durations]
        excess = sum(durations) - voice_duration
        if excess > 0:
            # Trim proportionally from scenes longer than 3s
            for i in range(len(durations) - 1, -1, -1):
                if durations[i] > 3.0 and excess > 0:
                    trim = min(excess, durations[i] - 3.0)
                    durations[i] -= trim
                    excess -= trim
    else:
        durations = [s["estimated_duration_seconds"] for s in scenes]

    animated_paths = []

    for scene, duration in zip(scenes, durations):
        idx = scene["scene_index"]
        motion = scene.get("motion", "static")
        img_path = scenes_dir / f"scene_{idx:03d}.png"

        # fal.ai returns JPEG even with .png extension — try both
        if not img_path.exists():
            jpg_path = scenes_dir / f"scene_{idx:03d}.jpg"
            if jpg_path.exists():
                img_path = jpg_path

        if not img_path.exists():
            print(f"  [WARN] Scene {idx}: image not found at {scenes_dir}/scene_{idx:03d}.*", file=sys.stderr)
            continue

        out_path = anim_dir / f"scene_{idx:03d}.mp4"
        print(f"  [scene {idx}] {motion:16s} {duration:.1f}s  → {out_path.name}", flush=True)

        try:
            _animate_scene(img_path, out_path, duration, motion)
            animated_paths.append(out_path)
        except RuntimeError as e:
            print(f"  [WARN] Scene {idx} animation failed: {e}", file=sys.stderr)

    print(f"[scene_animator] {len(animated_paths)}/{len(scenes)} scenes animated", flush=True)
    return animated_paths


def main():
    parser = argparse.ArgumentParser(description="Animate scene images into video clips")
    parser.add_argument("--video-id", required=True, help="Video ID")
    parser.add_argument("--storyboard", help="Path to storyboard JSON (default: auto-find in logs/)")
    parser.add_argument("--voice-duration", type=float,
                        help="TTS duration in seconds (used to scale scene timings)")
    args = parser.parse_args()

    if args.storyboard:
        storyboard_path = Path(args.storyboard)
    else:
        # Auto-find most recent storyboard
        storyboard_dir = Path("logs/storyboards")
        files = sorted(storyboard_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            print("ERROR: No storyboard files found in logs/storyboards/", file=sys.stderr)
            sys.exit(1)
        storyboard_path = files[0]
        print(f"[scene_animator] Using storyboard: {storyboard_path.name}", flush=True)

    if not storyboard_path.exists():
        print(f"ERROR: storyboard not found: {storyboard_path}", file=sys.stderr)
        sys.exit(1)

    storyboard = json.loads(storyboard_path.read_text())

    print(f"[scene_animator] video_id: {args.video_id}", flush=True)
    print(f"[scene_animator] {storyboard['total_scenes']} scenes, voice_duration: {args.voice_duration}s", flush=True)

    animated = animate_scenes(
        video_id=args.video_id,
        storyboard=storyboard,
        voice_duration=args.voice_duration,
    )

    if not animated:
        print("ERROR: No scenes were animated", file=sys.stderr)
        sys.exit(1)

    print(f"[scene_animator] Done. Clips in inbox/{args.video_id}/animated/")


if __name__ == "__main__":
    main()
