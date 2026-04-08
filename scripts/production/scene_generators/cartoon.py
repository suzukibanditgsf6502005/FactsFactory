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

# Appended to every image prompt to shift style toward illustration/cartoon
CARTOON_PROMPT_SUFFIX = (
    ", flat illustration style, bold outlines, vibrant colors, "
    "clean 2D cartoon art, educational explainer style, "
    "portrait orientation 9:16, no text, no watermarks, no photorealism"
)


class CartoonSceneGenerator(SceneGenerator):
    """
    Generates cartoon-style scenes:
    1. AI image generation with flat/illustration prompts
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
        """Generate cartoon clips: AI images → Ken Burns animation."""

        # Patch image prompts to cartoon style
        patched_storyboard = _patch_prompts(storyboard, CARTOON_PROMPT_SUFFIX)

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


def _patch_prompts(storyboard: dict, suffix: str) -> dict:
    """
    Return a copy of the storyboard with cartoon suffix injected into each
    image_prompt, replacing the cinematic/photorealistic suffix if present.
    """
    import copy
    patched = copy.deepcopy(storyboard)
    for scene in patched["scenes"]:
        prompt = scene.get("image_prompt", "")
        # Strip common photorealistic suffixes from the storyboard generator
        for strip in [
            ", portrait orientation 9:16, photorealistic wildlife photography, cinematic lighting, high detail, no text, no watermarks",
            ", photorealistic", ", cinematic", "photorealistic",
        ]:
            prompt = prompt.replace(strip, "")
        scene["image_prompt"] = prompt.rstrip(", ") + suffix
    return patched
