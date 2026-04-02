"""
scene_animator.py — SCAFFOLD

Applies subtle motion (Ken Burns effect) to still scene images.
Produces one short video clip per scene, which video_editor.py stitches together.

Intended interface:
    python scripts/production/scene_animator.py --video-id ID
    python scripts/production/scene_animator.py --scenes-dir inbox/{id}/scenes/ --storyboard logs/storyboards/{id}_storyboard.json

Arguments:
    --video-id      Video ID (auto-resolves paths from logs/)
    --scenes-dir    Directory of scene PNG files from scene_image_generator.py
    --storyboard    Path to storyboard JSON (provides duration + motion hints per scene)
    --output-dir    Directory to save animated clips (default: inbox/{id}/animated/)
    --dry-run       Print plan without running ffmpeg

Output:
    inbox/{video_id}/animated/scene_000.mp4
    inbox/{video_id}/animated/scene_001.mp4
    ...

Implementation notes:
    - Use ffmpeg zoompan filter for Ken Burns (zoom in/out over duration)
    - Output resolution: 1080×1920 (9:16), H.264, 30fps
    - Duration per clip: from storyboard scene.duration_seconds
    - motion types (from storyboard):
        "static"        → no zoom, just static frame held for duration
        "slow_zoom_in"  → zoompan scale from 1.0 to 1.1 over duration
        "slow_zoom_out" → zoompan scale from 1.1 to 1.0 over duration
        "pan_left"      → pan from right to left
        "pan_right"     → pan from left to right
    - After animation, video_editor.py concatenates all clips and adds voiceover + captions
    - Output used by: video_editor.py (adapted to accept scene sequence)

ffmpeg zoompan example (slow_zoom_in, 5 seconds at 30fps):
    ffmpeg -loop 1 -i scene_000.png -vf
      "scale=8000:-1,zoompan=z='min(zoom+0.0015,1.1)':d=150:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920"
      -t 5 -pix_fmt yuv420p scene_000.mp4

TODO: Implement this module.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


MOTION_TYPES = ["static", "slow_zoom_in", "slow_zoom_out", "pan_left", "pan_right"]


def main():
    parser = argparse.ArgumentParser(description="Animate still scene images with Ken Burns effect")
    parser.add_argument("--video-id", help="Video ID")
    parser.add_argument("--scenes-dir", help="Directory of scene PNG files")
    parser.add_argument("--storyboard", help="Path to storyboard JSON")
    parser.add_argument("--output-dir", help="Directory for animated clips")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without running ffmpeg")
    args = parser.parse_args()

    # TODO: Implement ffmpeg zoompan animation per scene
    print("ERROR: scene_animator.py is not yet implemented (scaffold only)", file=sys.stderr)
    print("See module docstring for ffmpeg zoompan approach.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
