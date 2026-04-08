#!/usr/bin/env python3
"""
motion.py — MotionSceneGenerator

Generates high-retention kinetic typography clips — no image generation API needed.

Each scene:
  - Dark gradient background (unique color per scene)
  - Large bold text (Anton font) centered and faded in
  - Thin accent bar at top and bottom
  - Scales to voice_duration automatically

No external APIs required. Pure ffmpeg.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from scripts.production.scene_generators.base import SceneGenerator

# Dark background colors (cycling per scene)
BG_COLORS = [
    "0x0d1b2a",  # deep navy
    "0x1a0a2e",  # deep purple
    "0x0a1628",  # dark slate
    "0x1a0d00",  # dark amber
    "0x001a0a",  # dark forest
    "0x1a000d",  # dark crimson
    "0x111827",  # charcoal blue
    "0x0a1010",  # dark teal
]

# Accent bar colors (top/bottom strips)
ACCENT_COLORS = [
    "0xe63946",  # red
    "0xa8dadc",  # cyan
    "0xf4a261",  # orange
    "0x2a9d8f",  # teal
    "0xe9c46a",  # gold
    "0xe76f51",  # coral
    "0x90be6d",  # green
    "0x577590",  # slate
]

FPS = 30
W, H = 1080, 1920
FONT_PATH = str(Path(__file__).parent.parent.parent.parent / "assets" / "fonts" / "Anton-Regular.ttf")
ACCENT_BAR_H = 10
FONT_SIZE = 92
LINE_MAX_CHARS = 18    # characters per line before wrapping


class MotionSceneGenerator(SceneGenerator):
    """
    Kinetic typography scenes — word-by-word reveals on dark colored backgrounds.
    No image generation required.
    """

    @property
    def style_name(self) -> str:
        return "motion"

    def generate_scenes(
        self,
        storyboard: dict,
        video_id: str,
        voice_duration: float | None = None,
    ) -> list[Path]:
        """Generate one kinetic typography clip per scene."""

        scenes = storyboard["scenes"]
        anim_dir = Path(f"inbox/{video_id}/animated")
        anim_dir.mkdir(parents=True, exist_ok=True)

        # Compute scene durations (proportional to voice_duration)
        durations = _compute_durations(scenes, voice_duration)

        clips = []
        for scene, duration in zip(scenes, durations):
            idx = scene["scene_index"]
            narration = scene.get("narration_segment", scene.get("scene_goal", ""))
            bg = BG_COLORS[idx % len(BG_COLORS)]
            accent = ACCENT_COLORS[idx % len(ACCENT_COLORS)]
            out_path = anim_dir / f"scene_{idx:03d}.mp4"

            print(f"  [motion scene {idx}] {duration:.1f}s  → {out_path.name}", flush=True)
            try:
                _make_motion_clip(narration, duration, out_path, bg, accent)
                clips.append(out_path)
            except RuntimeError as e:
                print(f"  [WARN] Motion scene {idx} failed: {e}", file=sys.stderr)

        print(f"[motion] {len(clips)}/{len(scenes)} clips rendered", flush=True)
        return clips


def _compute_durations(scenes: list[dict], voice_duration: float | None) -> list[float]:
    """Proportionally scale scene durations to voice_duration."""
    raw = [max(2.0, s["estimated_duration_seconds"]) for s in scenes]
    if not voice_duration:
        return raw
    total = sum(raw)
    scale = voice_duration / total if total > 0 else 1.0
    scaled = [max(2.0, d * scale) for d in raw]
    # Correct rounding drift
    excess = sum(scaled) - voice_duration
    if excess > 0:
        for i in range(len(scaled) - 1, -1, -1):
            if scaled[i] > 3.0 and excess > 0:
                trim = min(excess, scaled[i] - 2.0)
                scaled[i] -= trim
                excess -= trim
    return scaled


def _wrap_text(text: str, max_chars: int = LINE_MAX_CHARS) -> str:
    """Wrap text into lines of at most max_chars characters."""
    words = text.split()
    lines, current = [], []
    for word in words:
        candidate = " ".join(current + [word])
        if len(candidate) > max_chars and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)


def _escape_drawtext(text: str) -> str:
    """Escape special characters for ffmpeg drawtext filter."""
    # Order matters: backslash first, then others
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "\u2019")   # replace curly apostrophe (safe in drawtext)
    text = text.replace(":", "\\:")
    text = text.replace("%", "\\%")
    return text


def _run(cmd: list, label: str) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg [{label}]: {result.stderr[-400:]}")


def _make_motion_clip(
    narration: str,
    duration: float,
    out_path: Path,
    bg_color: str,
    accent_color: str,
) -> None:
    """Render a single kinetic typography clip."""

    wrapped = _wrap_text(narration.strip().rstrip(".!?,"))
    escaped = _escape_drawtext(wrapped)

    # Write text to temp file (avoids shell escaping issues entirely)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as tf:
        tf.write(escaped)
        text_file = tf.name

    try:
        # Build filter:
        #   1. Accent bar top
        #   2. Accent bar bottom
        #   3. Centered text with fade-in and subtle scale
        fade_in = 0.18  # seconds
        vf = (
            # Top accent bar
            f"drawbox=x=0:y=0:w={W}:h={ACCENT_BAR_H}:color={accent_color}:t=fill,"
            # Bottom accent bar
            f"drawbox=x=0:y={H - ACCENT_BAR_H}:w={W}:h={ACCENT_BAR_H}:color={accent_color}:t=fill,"
            # Main text — black outline first (shadow effect via borderw)
            f"drawtext="
            f"fontfile={FONT_PATH}:"
            f"textfile={text_file}:"
            f"fontsize={FONT_SIZE}:"
            f"fontcolor=white:"
            f"borderw=5:"
            f"bordercolor=black@0.85:"
            f"line_spacing=14:"
            f"x=(w-text_w)/2:"
            f"y=(h-text_h)/2:"
            f"alpha='if(lt(t,{fade_in}),t/{fade_in},1)'"
        )

        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c={bg_color}:s={W}x{H}:r={FPS}",
            "-vf", vf,
            "-t", str(round(duration, 3)),
            "-c:v", "libx264",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-r", str(FPS),
            "-an",
            str(out_path),
        ]
        _run(cmd, out_path.stem)

    finally:
        Path(text_file).unlink(missing_ok=True)
