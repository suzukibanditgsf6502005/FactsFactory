"""
scene_generators — FactsFactory visual style backends.

Usage:
    from scripts.production.scene_generators import get_generator

    gen = get_generator("motion")
    clips = gen.generate_scenes(storyboard, video_id, voice_duration=48.4)
"""

from scripts.production.scene_generators.base import SceneGenerator
from scripts.production.scene_generators.cinematic import CinematicSceneGenerator
from scripts.production.scene_generators.cartoon import CartoonSceneGenerator
from scripts.production.scene_generators.motion import MotionSceneGenerator

STYLES = ["cinematic", "cartoon", "motion"]


def get_generator(style: str) -> SceneGenerator:
    """
    Factory function — returns the SceneGenerator for the given style.

    Args:
        style: "cinematic" | "cartoon" | "motion"

    Raises:
        ValueError: if style is not one of the supported values
    """
    if style == "cinematic":
        return CinematicSceneGenerator()
    if style == "cartoon":
        return CartoonSceneGenerator()
    if style == "motion":
        return MotionSceneGenerator()
    raise ValueError(f"Unknown style: {style!r}. Choose from: {STYLES}")


__all__ = [
    "SceneGenerator",
    "CinematicSceneGenerator",
    "CartoonSceneGenerator",
    "MotionSceneGenerator",
    "get_generator",
    "STYLES",
]
