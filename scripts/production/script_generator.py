"""
script_generator.py — SCAFFOLD

Generates a full narration script for a YouTube Short from researched facts.

Intended interface:
    python scripts/production/script_generator.py --facts-file logs/facts/YYYYMMDD_slug.json
    python scripts/production/script_generator.py --topic "..." --facts "fact1|fact2|..."

Arguments:
    --facts-file    Path to facts JSON from fact_research.py
    --topic         Topic string (if not using facts-file)
    --facts         Pipe-separated fact strings (if not using facts-file)
    --target-duration  Target narration duration in seconds (default: 45)
    --output        Path to write script JSON (default: logs/scripts/YYYYMMDD_{slug}.json)
    --video-id      Video ID (used in output filename if provided)
    --dry-run       Print script without saving

Output format (JSON):
    {
        "video_id": "...",
        "topic": "...",
        "full_script": "What if I told you there's an animal that can see colors you can't even imagine?...",
        "hook": "What if I told you there's an animal that can see colors you can't even imagine?",
        "body": "The mantis shrimp has 16 types of photoreceptors. Humans have just 3...",
        "cta": "Follow for more wild animal facts.",
        "title": "This Animal Sees Colors You Can't Imagine",
        "hashtags": ["#facts", "#animals", "#science"],
        "estimated_duration_seconds": 43,
        "word_count": 120
    }

Implementation notes:
    - Use claude-sonnet-4-6 for script quality
    - Target 30–55 second narration (approximately 80–140 words at normal TTS pace)
    - Structure: hook (first 3s) → 5–8 fact beats → CTA
    - Hook must be a question or surprising statement — not "Today we're talking about..."
    - Grounded strictly in facts from fact_research.py — no hallucination
    - Output is used by: voiceover.py (full_script), metadata_gen.py (title, hashtags)
    - Replaces PawFactory's hook_generator.py for the FactsFactory pipeline

TODO: Implement this module.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Generate narration script for a YouTube Short")
    parser.add_argument("--facts-file", help="Path to facts JSON from fact_research.py")
    parser.add_argument("--topic", help="Topic string")
    parser.add_argument("--facts", help="Pipe-separated fact strings")
    parser.add_argument("--target-duration", type=int, default=45, help="Target duration in seconds")
    parser.add_argument("--output", help="Output JSON path")
    parser.add_argument("--video-id", help="Video ID for output filename")
    parser.add_argument("--dry-run", action="store_true", help="Print result without saving")
    args = parser.parse_args()

    # TODO: Implement Claude Sonnet call to write narration script
    print("ERROR: script_generator.py is not yet implemented (scaffold only)", file=sys.stderr)
    print("See module docstring for intended interface and output format.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
