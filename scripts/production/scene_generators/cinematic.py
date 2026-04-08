#!/usr/bin/env python3
"""
cinematic.py — CinematicSceneGenerator

Generates high-quality video scenes via AI video generation APIs.

Priority order:
  1. Veo (Google DeepMind) — via Vertex AI / Gemini API  [scaffold — API in preview]
  2. Runway Gen-3 Alpha — via Runway ML API               [scaffold — requires RUNWAY_API_KEY]
  3. Fallback: FLUX still images + Ken Burns animation    [always works — uses fal.ai]

Set RUNWAY_API_KEY in .env to enable Runway generation.
Veo API is not yet publicly available; the scaffold is ready for when it opens.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from scripts.production.scene_generators.base import SceneGenerator

# Cinematic prompt suffix (photorealistic, dramatic, documentary)
CINEMATIC_PROMPT_SUFFIX = (
    ", ultra-realistic cinematic photography, dramatic lighting, "
    "shallow depth of field, anamorphic lens, film grain, "
    "nature documentary style, National Geographic quality, "
    "portrait orientation 9:16, no text, no watermarks"
)

W, H = 1080, 1920
FPS = 30


class CinematicSceneGenerator(SceneGenerator):
    """
    Cinematic scene generator with tiered provider fallback:
      Veo → Runway → FLUX stills + Ken Burns
    """

    def __init__(self, prefer_video: bool = True):
        """
        Args:
            prefer_video: If True, try Veo/Runway first. If False, skip to FLUX fallback.
        """
        self._prefer_video = prefer_video

    @property
    def style_name(self) -> str:
        return "cinematic"

    def generate_scenes(
        self,
        storyboard: dict,
        video_id: str,
        voice_duration: float | None = None,
    ) -> list[Path]:
        """
        Generate cinematic clips. Tries Veo → Runway → FLUX+Ken Burns.
        Returns list of mp4 clip paths.
        """
        scenes = storyboard["scenes"]
        anim_dir = Path(f"inbox/{video_id}/animated")
        anim_dir.mkdir(parents=True, exist_ok=True)

        # Determine provider
        if self._prefer_video:
            provider = _detect_video_provider()
        else:
            provider = "flux"

        print(f"[cinematic] Provider: {provider}", flush=True)
        print(f"[cinematic] Generating {len(scenes)} scenes...", flush=True)

        if provider == "runway":
            clips = _generate_runway(scenes, anim_dir, video_id, storyboard, voice_duration)
        elif provider == "veo":
            clips = _generate_veo(scenes, anim_dir, video_id, storyboard, voice_duration)
        else:
            # Fallback: FLUX images + Ken Burns (always works)
            clips = _generate_flux_fallback(storyboard, video_id, voice_duration)

        return clips


# ── Provider detection ────────────────────────────────────────────────────────

def _detect_video_provider() -> str:
    """Return which video provider to use based on available API keys."""
    if os.getenv("RUNWAY_API_KEY"):
        return "runway"
    if os.getenv("GOOGLE_API_KEY") or os.getenv("VERTEX_PROJECT_ID"):
        return "veo"
    return "flux"


# ── Veo scaffold (Google DeepMind) ────────────────────────────────────────────

def _generate_veo(
    scenes: list[dict],
    anim_dir: Path,
    video_id: str,
    storyboard: dict,
    voice_duration: float | None,
) -> list[Path]:
    """
    Veo text-to-video generation via Google Vertex AI.

    SCAFFOLD: Veo API is in private preview as of 2026-04.
    This implements the expected API shape based on Google's documentation.
    When Veo API becomes generally available, replace the stub below with
    the real vertexai.preview.vision_models.VideoGenerationModel call.

    Required env vars:
      GOOGLE_API_KEY or (VERTEX_PROJECT_ID + VERTEX_LOCATION)
    """
    print("[cinematic/veo] Veo API scaffold — not yet publicly available", flush=True)
    print("[cinematic/veo] Falling back to FLUX stills + Ken Burns", flush=True)

    # TODO: When Veo API is available:
    # from google.cloud import aiplatform
    # from vertexai.preview.vision_models import VideoGenerationModel
    # model = VideoGenerationModel.from_pretrained("veo-2.0-generate-001")
    # for scene in scenes:
    #     response = model.generate_video(
    #         prompt=scene["image_prompt"] + CINEMATIC_PROMPT_SUFFIX,
    #         duration_seconds=scene["estimated_duration_seconds"],
    #         aspect_ratio="9:16",
    #     )
    #     response.videos[0].save(anim_dir / f"scene_{scene['scene_index']:03d}.mp4")

    return _generate_flux_fallback(storyboard, video_id, voice_duration)


# ── Runway scaffold ───────────────────────────────────────────────────────────

def _generate_runway(
    scenes: list[dict],
    anim_dir: Path,
    video_id: str,
    storyboard: dict,
    voice_duration: float | None,
) -> list[Path]:
    """
    Runway Gen-3 Alpha Turbo text-to-video generation.

    Requires: RUNWAY_API_KEY in .env
    Install:  pip install runwayml

    API docs: https://docs.runwayml.com/
    Cost:     ~$0.05/second of video (~$0.15–0.30/scene)
    """
    try:
        import runwayml  # noqa: F401
    except ImportError:
        print("[cinematic/runway] runwayml SDK not installed → pip install runwayml", flush=True)
        print("[cinematic/runway] Falling back to FLUX stills + Ken Burns", flush=True)
        return _generate_flux_fallback(storyboard, video_id, voice_duration)

    api_key = os.getenv("RUNWAY_API_KEY", "")
    if not api_key:
        print("[cinematic/runway] RUNWAY_API_KEY not set — falling back to FLUX", flush=True)
        return _generate_flux_fallback(storyboard, video_id, voice_duration)

    clips = []
    client = runwayml.RunwayML(api_key=api_key)

    for scene in scenes:
        idx = scene["scene_index"]
        out_path = anim_dir / f"scene_{idx:03d}.mp4"
        prompt = scene["image_prompt"] + CINEMATIC_PROMPT_SUFFIX

        # Runway supports 5s or 10s clips; clamp scene duration to nearest
        duration_s = min(10, max(5, int(round(scene["estimated_duration_seconds"]))))

        print(f"  [runway] Scene {idx} ({duration_s}s)...", flush=True)
        try:
            task = client.image_to_video.create(
                model="gen3a_turbo",
                prompt_text=prompt,
                duration=duration_s,
                ratio="720:1280",   # closest 9:16 Runway supports
            )
            # Poll until complete
            task_id = task.id
            for _ in range(60):  # 10-minute timeout
                time.sleep(10)
                task = client.tasks.retrieve(task_id)
                if task.status == "SUCCEEDED":
                    break
                if task.status == "FAILED":
                    raise RuntimeError(f"Runway task {task_id} failed: {task.failure}")

            if task.status != "SUCCEEDED":
                raise RuntimeError(f"Runway task {task_id} timed out")

            # Download the video
            import urllib.request
            urllib.request.urlretrieve(task.output[0], out_path)

            # Resize to 1080x1920 if needed
            _resize_to_portrait(out_path)
            clips.append(out_path)
            print(f"  [runway] Scene {idx} done → {out_path.name}", flush=True)

        except Exception as e:
            print(f"  [WARN] Runway scene {idx} failed: {e} — using FLUX fallback", flush=True)
            # Generate just this scene via FLUX
            from scripts.production.scene_image_generator import generate_scene_images
            from scripts.production.scene_animator import animate_scenes
            _patch_scene_for_cinematic(scene)
            generate_scene_images(
                storyboard={"scenes": [scene], "topic": storyboard["topic"], "total_scenes": 1},
                video_id=video_id,
                provider="fal",
            )
            sub_clips = animate_scenes(
                video_id=video_id,
                storyboard={"scenes": [scene], "total_scenes": 1},
                voice_duration=None,
            )
            clips.extend(sub_clips)

    return clips


# ── FLUX fallback ─────────────────────────────────────────────────────────────

def _generate_flux_fallback(
    storyboard: dict,
    video_id: str,
    voice_duration: float | None,
) -> list[Path]:
    """
    Fallback: generate cinematic-style still images via FLUX, then Ken Burns.
    Always works when FAL_API_KEY is set.
    """
    from scripts.production.scene_image_generator import generate_scene_images
    from scripts.production.scene_animator import animate_scenes
    import copy

    patched = copy.deepcopy(storyboard)
    for scene in patched["scenes"]:
        _patch_scene_for_cinematic(scene)

    print("[cinematic/flux] Generating cinematic stills via fal.ai...", flush=True)
    generate_scene_images(
        storyboard=patched,
        video_id=video_id,
        provider="fal",
    )

    print("[cinematic/flux] Animating with Ken Burns...", flush=True)
    return animate_scenes(
        video_id=video_id,
        storyboard=storyboard,
        voice_duration=voice_duration,
    )


def _patch_scene_for_cinematic(scene: dict) -> None:
    """Mutate scene image_prompt in-place to cinematic style."""
    prompt = scene.get("image_prompt", "")
    # Remove generic suffixes, inject cinematic suffix
    for strip in [
        ", portrait orientation 9:16, photorealistic wildlife photography, cinematic lighting, high detail, no text, no watermarks",
    ]:
        prompt = prompt.replace(strip, "")
    scene["image_prompt"] = prompt.rstrip(", ") + CINEMATIC_PROMPT_SUFFIX


# ── Utility ───────────────────────────────────────────────────────────────────

def _resize_to_portrait(video_path: Path) -> None:
    """Re-encode video to 1080x1920 if not already that resolution."""
    import tempfile, shutil
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
        tmp = tf.name

    result = subprocess.run([
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-r", str(FPS), "-an", tmp,
    ], capture_output=True, text=True)

    if result.returncode == 0:
        shutil.move(tmp, video_path)
    else:
        Path(tmp).unlink(missing_ok=True)
