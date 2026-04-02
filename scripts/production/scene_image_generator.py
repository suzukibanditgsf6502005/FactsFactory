"""
scene_image_generator.py — SCAFFOLD

Generates one still image per scene from storyboard image prompts.

Intended interface:
    python scripts/production/scene_image_generator.py --storyboard logs/storyboards/{id}_storyboard.json
    python scripts/production/scene_image_generator.py --video-id ID

Arguments:
    --storyboard    Path to storyboard JSON from storyboard_generator.py
    --video-id      Video ID (looks up logs/storyboards/{id}_storyboard.json automatically)
    --provider      Image generation provider: dalle3, flux, ideogram (default: TBD)
    --output-dir    Directory to save scene images (default: inbox/{id}/scenes/)
    --dry-run       Print prompts without generating images

Output:
    inbox/{video_id}/scenes/scene_000.png
    inbox/{video_id}/scenes/scene_001.png
    ...
    inbox/{video_id}/scenes/manifest.json   (maps scene_index → file path + metadata)

Implementation notes:
    - Provider is NOT yet chosen — do not wire a provider until human approves
    - DALL-E 3: ~$0.04/image at 1024×1024 standard quality
    - Flux (via Replicate or fal.ai): ~$0.003–$0.01/image
    - Ideogram: comparable to DALL-E 3, strong text rendering
    - All images should be generated at 1024×1792 (portrait 9:16) if provider supports it
    - Fallback: generate 1024×1024 and crop/fit in scene_animator.py
    - Output used by: scene_animator.py

TODO: Choose provider, get human approval, then implement.
"""

import argparse
import json
import os
import sys
from pathlib import Path


SUPPORTED_PROVIDERS = ["dalle3", "flux", "ideogram"]


def main():
    parser = argparse.ArgumentParser(description="Generate scene images from storyboard prompts")
    parser.add_argument("--storyboard", help="Path to storyboard JSON")
    parser.add_argument("--video-id", help="Video ID")
    parser.add_argument("--provider", choices=SUPPORTED_PROVIDERS, help="Image generation provider")
    parser.add_argument("--output-dir", help="Directory to save images")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts without generating")
    args = parser.parse_args()

    # TODO: Implement image generation — provider TBD, requires human approval
    print("ERROR: scene_image_generator.py is not yet implemented (scaffold only)", file=sys.stderr)
    print("Image generation provider not yet chosen. See module docstring for options.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
