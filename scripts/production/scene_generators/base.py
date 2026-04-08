#!/usr/bin/env python3
"""
base.py — Abstract base class for FactsFactory scene generators.

Every visual style (cinematic, cartoon, motion) implements this interface.
generate_scenes() returns ordered mp4 clip paths — one per storyboard scene.
"""

from abc import ABC, abstractmethod
from pathlib import Path


class SceneGenerator(ABC):
    """
    Abstract base for all scene visual styles.

    Subclasses must implement:
      - style_name  (property) → str: "cinematic" | "cartoon" | "motion"
      - generate_scenes(storyboard, video_id, voice_duration) → list[Path]
    """

    @property
    @abstractmethod
    def style_name(self) -> str:
        """Identifier for this style: cinematic | cartoon | motion"""
        ...

    @abstractmethod
    def generate_scenes(
        self,
        storyboard: dict,
        video_id: str,
        voice_duration: float | None = None,
    ) -> list[Path]:
        """
        Generate one video clip per storyboard scene.

        Args:
            storyboard:     Output from storyboard_generator.py
            video_id:       Unique video identifier (used for file naming)
            voice_duration: Total TTS duration in seconds (for scene timing)

        Returns:
            Ordered list of mp4 clip Paths (one per scene, ready for concat).
            Clips are written to inbox/{video_id}/animated/
        """
        ...
