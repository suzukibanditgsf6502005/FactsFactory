#!/usr/bin/env python3
"""
topic_selector.py — FactsFactory topic picker

Generates 5 candidate topics for a given category, scores them, and randomly
selects from the top-3 to ensure diversity across consecutive runs.

Usage:
  python scripts/research/topic_selector.py --category animal_facts
  python scripts/research/topic_selector.py --category weird_biology --dry-run
  python scripts/research/topic_selector.py --category animal_facts --output logs/topics/my_topic.json
"""

import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

CATEGORIES = [
    "animal_facts",
    "weird_biology",
    "history",
    "science",
    "space",
    "engineering",
    "psychology",
    "records",
]

# Category descriptions injected into the prompt so the model understands what to generate
CATEGORY_DESCRIPTIONS = {
    "animal_facts": (
        "Surprising, specific facts about animal biology, behavior, or abilities. "
        "Focus on counterintuitive things most people don't know about common or fascinating animals. "
        "Examples: mantis shrimp vision, tardigrade survival, pistol shrimp sonic shockwave."
    ),
    "weird_biology": (
        "The most disturbing, bizarre, or alien biological phenomena across all life forms — "
        "parasites, evolutionary extremes, body horror facts, organisms that defy normal logic. "
        "NOT general animal facts — must be specifically strange, gross, or existentially unsettling. "
        "Examples: Toxoplasma hijacking human brains, zombie ant fungus, immortal jellyfish, "
        "tardigrades surviving space, bdelloid rotifers with no males for 50 million years."
    ),
    "history": (
        "Specific historical events, decisions, or coincidences that shaped the world "
        "in ways most people never learned. Avoid well-known facts. "
        "Examples: the Oxford comma trial, the nurse who saved Hitler's life, "
        "the 1962 Soviet officer who prevented nuclear war."
    ),
    "science": (
        "Counterintuitive scientific discoveries, physics paradoxes, or chemistry facts "
        "that challenge everyday assumptions. "
        "Examples: glass is a supercooled liquid myth debunked, hot water freezing faster than cold."
    ),
    "space": (
        "Mind-bending scale, discovery, or physics facts about space. "
        "Perspective-shifting and awe-inspiring. "
        "Examples: a day on Venus is longer than its year, neutron star density comparisons."
    ),
    "engineering": (
        "Human engineering achievements that seem impossible or reveal hidden complexity. "
        "Examples: the GPS relativistic correction, the bridge that sings, the rounding error that crashed a rocket."
    ),
    "psychology": (
        "Cognitive biases, behavioral science findings, or perception facts that "
        "reveal something surprising about how the human mind works. "
        "Must feel personally relevant — the viewer should see themselves in it."
    ),
    "records": (
        "Extreme records and superlatives that are genuinely surprising and "
        "raise an obvious 'how is that even possible?' response. "
        "Examples: longest recorded echo, loudest animal relative to body size."
    ),
}

HAIKU_MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You are a YouTube Shorts topic strategist for a facts channel.
Your job is to identify topics that will perform well as 25–45 second educational shorts.

Scoring criteria:
- surprise_score: Is the fact genuinely counterintuitive or mind-blowing to a general audience?
- visual_score: Can this be shown compellingly with AI-generated still images?
- appeal_score: Will a broad, non-specialist audience find this interesting?
- hook_score: How naturally punchy is the one-sentence hook angle?

Important: score honestly. Most topics score 6–8. Reserve 9–10 for truly exceptional picks.
All five candidates must be on DIFFERENT subjects — no two from the same animal or event.

You must return ONLY valid JSON. No markdown, no explanation, no code fences."""

USER_PROMPT_TEMPLATE = """Generate exactly 5 candidate topics for the category: {category}

Category description:
{category_description}

Each candidate must be on a DIFFERENT subject. No two candidates about the same animal, event, or concept.

For each candidate assign a score from 1–10:
- surprise_score, visual_score, appeal_score, hook_score
- overall_score = average of the four (to one decimal place)

Return ONLY valid JSON in this exact structure:
{{
  "category": "{category}",
  "candidates": [
    {{
      "topic": "One specific, concrete topic sentence — a fact, not a theme",
      "hook_angle": "Opening line for the hook (max 12 words, strong verb, no 'Did you know')",
      "rationale": "1-2 sentences: why this specific fact works for a 35-second Short",
      "surprise_score": 8,
      "visual_score": 7,
      "appeal_score": 9,
      "hook_score": 8,
      "overall_score": 8.0
    }}
  ]
}}

Rules:
- Topics must be SPECIFIC facts, not vague themes
- All 5 candidates must be about completely different subjects
- Do NOT include a top_pick_index — the caller will select randomly from top candidates
- Rank candidates by overall_score descending"""


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
    prompt = USER_PROMPT_TEMPLATE.format(
        category=category,
        category_description=CATEGORY_DESCRIPTIONS.get(category, f"Interesting facts about {category}"),
    )

    print(f"[topic_selector] Generating candidates for category: {category}", flush=True)

    message = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text
    data = _parse_json_response(raw)

    if "candidates" not in data or not data["candidates"]:
        raise ValueError("Response missing 'candidates' list")

    candidates = data["candidates"]
    for i, c in enumerate(candidates):
        for field in ("topic", "hook_angle", "rationale", "overall_score"):
            if field not in c:
                raise ValueError(f"Candidate #{i} missing required field: {field}")

    # Sort descending by overall_score, then randomly pick from the top 3
    candidates_sorted = sorted(candidates, key=lambda c: c["overall_score"], reverse=True)
    top_score = candidates_sorted[0]["overall_score"]
    # Eligible = any candidate within 0.75 of the top score, up to 3
    eligible = [c for c in candidates_sorted if c["overall_score"] >= top_score - 0.75][:3]
    chosen = random.choice(eligible)

    result = {
        "topic": chosen["topic"],
        "hook_angle": chosen["hook_angle"],
        "rationale": chosen["rationale"],
        "estimated_engagement": "high" if chosen["overall_score"] >= 7.5 else "medium",
        "overall_score": chosen["overall_score"],
        "category": category,
        "candidates": candidates_sorted,
        "chosen_index": candidates_sorted.index(chosen),
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
    print(f"[topic_selector] Score: {result['overall_score']} (chosen #{result['chosen_index']+1} of {len(result['candidates'])})", flush=True)


if __name__ == "__main__":
    main()
