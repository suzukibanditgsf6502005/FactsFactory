"""
scene_generators — FactsFactory visual style backends.

Usage:
    from scripts.production.scene_generators import get_generator

    gen = get_generator("cartoon")
    clips = gen.generate_scenes(storyboard, video_id, voice_duration=48.4)

Note: motion style is temporarily disabled from the public pipeline.
motion.py remains on disk but is not importable from here.
"""

from scripts.production.scene_generators.base import SceneGenerator
from scripts.production.scene_generators.cinematic import CinematicSceneGenerator
from scripts.production.scene_generators.cartoon import CartoonSceneGenerator

STYLES = ["cinematic", "cartoon"]


def get_generator(style: str) -> SceneGenerator:
    """
    Factory function — returns the SceneGenerator for the given style.

    Args:
        style: "cinematic" | "cartoon"

    Raises:
        RuntimeError: if motion is requested (temporarily disabled)
        ValueError: if style is not one of the supported values
    """
    if style == "cinematic":
        return CinematicSceneGenerator()
    if style == "cartoon":
        return CartoonSceneGenerator()
    if style == "motion":
        raise RuntimeError(
            "Motion style is temporarily disabled from the public pipeline. "
            "Use --style cinematic or --style cartoon instead."
        )
    raise ValueError(f"Unknown style: {style!r}. Choose from: {STYLES}")


__all__ = [
    "SceneGenerator",
    "CinematicSceneGenerator",
    "CartoonSceneGenerator",
    "get_generator",
    "STYLES",
]
