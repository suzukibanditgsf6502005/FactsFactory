#!/usr/bin/env python3
"""
cartoon.py — CartoonSceneGenerator

Uses AI image generation (fal.ai Flux / OpenAI DALL-E) with a flat/illustrative
prompt style, then applies Ken Burns animation.

This is a thin wrapper over the existing scene_image_generator + scene_animator
modules, with cartoon-specific prompt overrides.
"""

import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from scripts.production.scene_generators.base import SceneGenerator
from scripts.production.scene_image_generator import generate_scene_images
from scripts.production.scene_animator import animate_scenes

# Applied to legacy image_prompt (scenes without structured infographic fields)
# to keep backward compatibility with older storyboard files.
CARTOON_LEGACY_SUFFIX = (
    ", flat illustration educational infographic style, bold outlines, vibrant colors, "
    "clean 2D comic art, educational explainer scene, multiple visual elements, "
    "portrait orientation 9:16, no watermarks, no photorealism"
)


class CartoonSceneGenerator(SceneGenerator):
    """
    Generates cartoon-style scenes:
    1. AI image generation — infographic/comic prompts for structured storyboards,
       legacy cartoon suffix for older storyboard files
    2. Ken Burns animation (zoom/pan on stills)
    """

    def __init__(self, provider: str = "auto"):
        """
        Args:
            provider: Image provider — "fal" | "openai" | "auto"
        """
        self._provider = provider

    @property
    def style_name(self) -> str:
        return "cartoon"

    def generate_scenes(
        self,
        storyboard: dict,
        video_id: str,
        voice_duration: float | None = None,
    ) -> list[Path]:
        """Generate cartoon clips: AI images → Ken Burns animation.

        For scenes with structured infographic fields (main_subject, supporting_elements,
        layout_hint), scene_image_generator builds a dense infographic/comic prompt via
        _build_scene_prompt — no suffix patching needed.

        For older scenes without those fields, falls back to legacy cartoon suffix on
        image_prompt to maintain backward compatibility.
        """
        patched_storyboard = _apply_cartoon_style(storyboard)

        print(f"[cartoon] Generating {storyboard['total_scenes']} images via {self._provider}...", flush=True)
        generate_scene_images(
            storyboard=patched_storyboard,
            video_id=video_id,
            provider=self._provider,
        )

        print(f"[cartoon] Animating scenes (Ken Burns)...", flush=True)
        clips = animate_scenes(
            video_id=video_id,
            storyboard=storyboard,
            voice_duration=voice_duration,
        )

        return clips


def _apply_cartoon_style(storyboard: dict) -> dict:
    """
    Return a patched copy of the storyboard ready for cartoon image generation.

    Scenes WITH structured infographic fields (main_subject, supporting_elements,
    layout_hint) are passed through unchanged — scene_image_generator._build_scene_prompt
    will compose the infographic/comic prompt from those fields.

    Scenes WITHOUT those fields (older storyboard files) get the cartoon suffix
    injected into image_prompt for backward compatibility.
    """
    import copy
    patched = copy.deepcopy(storyboard)
    for scene in patched["scenes"]:
        has_structured = (
            scene.get("main_subject")
            and scene.get("supporting_elements")
            and scene.get("layout_hint")
        )
        if not has_structured:
            # Legacy path: strip any photorealistic suffixes, inject cartoon style
            prompt = scene.get("image_prompt", "")
            for strip in [
                ", portrait orientation 9:16, photorealistic wildlife photography, cinematic lighting, high detail, no text, no watermarks",
                ", photorealistic", ", cinematic", "photorealistic",
            ]:
                prompt = prompt.replace(strip, "")
            scene["image_prompt"] = prompt.rstrip(", ") + CARTOON_LEGACY_SUFFIX
    return patched
