#!/usr/bin/env python3
"""
topic_selector.py — FactsFactory topic picker

Generates 5 candidate topics for a given category, scores them, returns the top pick.

Usage:
  python scripts/research/topic_selector.py --category animal_facts
  python scripts/research/topic_selector.py --category animal_facts --dry-run
  python scripts/research/topic_selector.py --category animal_facts --output logs/topics/my_topic.json
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

CATEGORIES = [
    "animal_facts",
    "history",
    "science",
    "space",
    "engineering",
    "psychology",
    "records",
]

HAIKU_MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You are a YouTube Shorts topic strategist for a facts channel.
Your job is to identify topics that will perform well as 25–45 second educational shorts.

Scoring criteria:
- Surprise factor: Is the fact genuinely counterintuitive or mind-blowing?
- Visual potential: Can this be shown compellingly with AI-generated images?
- Broad appeal: Will a general audience (not enthusiasts) find this interesting?
- Hook strength: Does this have an obvious, punchy hook angle?
- Short-form fit: Can this be explained clearly in 30–40 seconds?

You must return ONLY valid JSON. No markdown, no explanation, no code fences."""

USER_PROMPT_TEMPLATE = """Generate exactly 5 candidate topics for the category: {category}

For each candidate, assign a score from 1–10 across these dimensions:
- surprise_score: How counterintuitive or unexpected is this?
- visual_score: How well can this be shown with still images?
- appeal_score: How broadly appealing is this to a general audience?
- hook_score: How strong is the natural hook angle?

Overall score = average of all four.

Return ONLY valid JSON in this exact structure:
{{
  "category": "{category}",
  "candidates": [
    {{
      "topic": "One clear, specific topic sentence (not vague)",
      "hook_angle": "Opening question or statement for the hook (max 15 words)",
      "rationale": "1-2 sentences why this works for Shorts",
      "surprise_score": 8,
      "visual_score": 7,
      "appeal_score": 9,
      "hook_score": 8,
      "overall_score": 8.0
    }}
  ],
  "top_pick_index": 0
}}

Rules:
- Topics must be specific facts, not vague themes ("The mantis shrimp has 16 color receptors" not "mantis shrimp are interesting")
- Each topic must be distinct — no overlapping subjects
- Rank candidates by overall_score descending
- top_pick_index points to the highest-scored candidate"""


def _parse_json_response(raw: str) -> dict:
    """Strip markdown fences and parse JSON."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
    return json.loads(raw)


def _make_log_path(category: str) -> Path:
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = category.replace("_", "-")
    log_dir = Path("logs/topics")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"{date_str}_{slug}.json"


def select_topic(category: str) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY missing in .env", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    prompt = USER_PROMPT_TEMPLATE.format(category=category)

    print(f"[topic_selector] Generating candidates for category: {category}", flush=True)

    message = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text
    data = _parse_json_response(raw)

    # Validate required fields
    if "candidates" not in data or not data["candidates"]:
        raise ValueError("Response missing 'candidates' list")
    if "top_pick_index" not in data:
        raise ValueError("Response missing 'top_pick_index'")

    top = data["candidates"][data["top_pick_index"]]
    for field in ("topic", "hook_angle", "rationale", "overall_score"):
        if field not in top:
            raise ValueError(f"Top candidate missing required field: {field}")

    result = {
        "topic": top["topic"],
        "hook_angle": top["hook_angle"],
        "rationale": top["rationale"],
        "estimated_engagement": "high" if top["overall_score"] >= 7.5 else "medium",
        "overall_score": top["overall_score"],
        "category": category,
        "candidates": data["candidates"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": HAIKU_MODEL,
    }

    return result


def main():
    parser = argparse.ArgumentParser(description="Select a fact topic for a YouTube Short")
    parser.add_argument("--category", choices=CATEGORIES, default="animal_facts",
                        help="Content category (default: animal_facts)")
    parser.add_argument("--output", help="Output JSON path (default: logs/topics/TIMESTAMP_category.json)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print result to stdout without saving to disk")
    args = parser.parse_args()

    try:
        result = select_topic(args.category)
    except json.JSONDecodeError as e:
        print(f"ERROR: Claude returned invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)
    except (ValueError, KeyError) as e:
        print(f"ERROR: Unexpected response structure: {e}", file=sys.stderr)
        sys.exit(1)
    except anthropic.APIError as e:
        print(f"ERROR: Anthropic API error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print(json.dumps(result, indent=2))
        print(f"\n[topic_selector] DRY RUN — topic: {result['topic']}", flush=True)
        return

    out_path = Path(args.output) if args.output else _make_log_path(args.category)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2))
    print(f"[topic_selector] Saved: {out_path}", flush=True)
    print(f"[topic_selector] Topic: {result['topic']}", flush=True)
    print(f"[topic_selector] Score: {result['overall_score']}", flush=True)


if __name__ == "__main__":
    main()
