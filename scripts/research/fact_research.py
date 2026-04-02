"""
fact_research.py — SCAFFOLD

Researches and structures verified facts for a given topic.

Intended interface:
    python scripts/research/fact_research.py --topic "The mantis shrimp can see 16 types of color"
    python scripts/research/fact_research.py --topic-file logs/topics/YYYYMMDD_topic.json

Arguments:
    --topic         Topic string directly
    --topic-file    Path to topic JSON from topic_selector.py
    --output        Path to write facts JSON (default: logs/facts/YYYYMMDD_{slug}.json)
    --dry-run       Print facts without writing to disk

Output format (JSON):
    {
        "topic": "The mantis shrimp can see 16 types of color",
        "category": "animals",
        "facts": [
            {
                "fact": "Mantis shrimp have 16 types of photoreceptors; humans have 3.",
                "impact": "high",
                "order": 1,
                "visual_description": "Close-up of mantis shrimp eye with color spectrum overlay"
            },
            ...
        ],
        "hook_fact": "Mantis shrimp have 16 types of photoreceptors; humans have 3.",
        "cta_angle": "Follow for more wild animal facts",
        "fact_count": 8
    }

Implementation notes:
    - Use claude-sonnet-4-6 for quality (facts need accuracy and impact)
    - Generate 8–12 facts ordered by surprise/impact (most surprising first)
    - First fact should be the strongest hook (already surfaced as hook_fact)
    - Avoid medical advice, political framing, unverifiable claims
    - Prompt Claude to self-verify: "Is this widely accepted as factual?"
    - Write output to logs/facts/{date}_{slug}.json
    - Artifact used by: script_generator.py

TODO: Implement this module.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Research facts for a YouTube Short topic")
    parser.add_argument("--topic", help="Topic string")
    parser.add_argument("--topic-file", help="Path to topic JSON from topic_selector.py")
    parser.add_argument("--output", help="Output JSON path")
    parser.add_argument("--dry-run", action="store_true", help="Print result without saving")
    args = parser.parse_args()

    if not args.topic and not args.topic_file:
        print("ERROR: Provide --topic or --topic-file", file=sys.stderr)
        sys.exit(1)

    # TODO: Implement Claude Sonnet call to research and structure facts
    print("ERROR: fact_research.py is not yet implemented (scaffold only)", file=sys.stderr)
    print("See module docstring for intended interface and output format.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
