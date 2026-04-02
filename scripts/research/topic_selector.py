"""
topic_selector.py — SCAFFOLD

Selects a high-interest fact topic for a YouTube Shorts script.

Intended interface:
    python scripts/research/topic_selector.py [--category CATEGORY] [--count N]

Arguments:
    --category  One of: animals, history, science, space, engineering, psychology, records
                Default: randomly chosen from all categories
    --count     Number of candidate topics to generate before picking the top one (default: 5)
    --output    Path to write selected topic JSON (default: logs/topics/YYYYMMDD_topic.json)
    --dry-run   Print selected topic without writing to disk

Output format (JSON):
    {
        "topic": "The mantis shrimp can see 16 types of color",
        "category": "animals",
        "hook_angle": "What if I told you there's an animal that can see colors you can't even imagine?",
        "estimated_engagement": "high",
        "rationale": "Counterintuitive biology fact with strong visual potential and broad appeal",
        "candidates": [...]
    }

Implementation notes:
    - Use claude-haiku-4-5-20251001 for cost efficiency (topic selection is low-stakes)
    - Generate N candidates, score by: surprise factor, visual potential, broad appeal
    - Return top-scored candidate
    - Write output to logs/topics/{date}_topic.json
    - Artifact used by: fact_research.py

TODO: Implement this module.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


CATEGORIES = [
    "animals",
    "history",
    "science",
    "space",
    "engineering",
    "psychology",
    "records",
]


def main():
    parser = argparse.ArgumentParser(description="Select a fact topic for a YouTube Short")
    parser.add_argument("--category", choices=CATEGORIES, help="Content category")
    parser.add_argument("--count", type=int, default=5, help="Number of candidates to generate")
    parser.add_argument("--output", help="Output JSON path")
    parser.add_argument("--dry-run", action="store_true", help="Print result without saving")
    args = parser.parse_args()

    # TODO: Implement Claude Haiku call to generate and score topic candidates
    print("ERROR: topic_selector.py is not yet implemented (scaffold only)", file=sys.stderr)
    print("See module docstring for intended interface and output format.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
