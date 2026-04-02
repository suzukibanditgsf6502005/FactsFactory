#!/usr/bin/env python3
"""
script_generator.py — FactsFactory narration script writer

Takes a research JSON (from fact_research.py) and produces a complete narration
script for a 25–45 second YouTube Short.

Usage:
  python scripts/production/script_generator.py --research-file logs/research/20260403_mantis-shrimp.json
  python scripts/production/script_generator.py --research-file logs/research/20260403_mantis-shrimp.json --dry-run
  python scripts/production/script_generator.py --research-file ... --target-duration 35
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

SONNET_MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are a YouTube Shorts scriptwriter for a facts channel.
Your scripts are punchy, surprising, and educational. Every word earns its place.

Script structure (strict):
1. Hook (first 3–4 seconds): A question or surprising statement that creates immediate intrigue.
   - Must reference the hook_fact from the research brief
   - No "Today we're looking at...", no "Did you know that..." openers
   - Examples: "This animal can punch faster than a bullet." / "For 600 million years, this creature has barely changed."
2. Narration (main body): Deliver 5–7 facts in order, building toward the most mind-blowing
   - Paced for spoken delivery — short sentences, natural rhythm
   - Use "..." for natural pauses where breath is needed
   - Build from surprising → more surprising → most surprising
3. Payoff + CTA (final 3 seconds): Land the emotional payoff, then a natural follow CTA
   - CTA must feel organic, not forced: "Follow if that blew your mind." / "More wild facts daily."

Word count targets for narration duration:
- 25s target: ~65 words
- 30s target: ~80 words
- 35s target: ~95 words
- 40s target: ~110 words
- 45s target: ~125 words

Rules:
- English only
- Ground script strictly in provided facts — no invented details
- Never use passive voice for the hook
- Title variants must use curiosity-gap or emotion-led angles — no "10 facts about X"
- Return ONLY valid JSON. No markdown, no explanation, no code fences."""

USER_PROMPT_TEMPLATE = """Write a YouTube Shorts narration script from this factual research brief.

Topic: {topic}
Category: {category}
Hook angle: {hook_angle}
Hook fact (must open the script): {hook_fact}
Target duration: {target_duration} seconds (~{target_words} words total)
Emotional angle to pursue: {emotional_angle_hint}

Factual brief:
{factual_brief}

Facts to draw from (use 5–7, ordered by impact):
{facts_text}

Return ONLY valid JSON in this exact structure:
{{
  "topic": "{topic}",
  "hook": "Opening line(s) — first 3–4 seconds of spoken audio",
  "narration": "Main body narration — everything after the hook and before the CTA",
  "cta": "Final 1-sentence call to action",
  "full_script": "hook + narration + cta combined, ready for TTS. Use '...' for pauses.",
  "title_variants": [
    "Title option 1 — curiosity gap",
    "Title option 2 — emotion-led",
    "Title option 3 — outcome/payoff",
    "Title option 4 — question format"
  ],
  "emotional_angle": "wonder|surprise|awe|admiration|humor|disbelief",
  "estimated_duration_seconds": 35,
  "word_count": 95
}}

Validation checklist (apply before returning):
- word_count matches actual word count of full_script
- estimated_duration_seconds = word_count / 2.75 (rounded to nearest integer)
- full_script = hook + " " + narration + " " + cta
- All facts in script are sourced from the provided facts list"""


def _parse_json_response(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
    return json.loads(raw)


def _make_log_path(topic: str) -> Path:
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = topic[:40].lower().replace(" ", "-").replace("/", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    log_dir = Path("logs/scripts")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"{date_str}_{slug}.json"


def _target_words(duration: int) -> int:
    # Approximate: ~2.75 words/second for measured TTS delivery
    return round(duration * 2.75)


def _emotional_angle_hint(category: str, hook_angle: str) -> str:
    hints = {
        "animal_facts": "wonder and disbelief — nature is stranger than fiction",
        "history": "surprise and inevitability — you won't believe this happened",
        "science": "awe — the universe is more complex than we imagined",
        "space": "awe and smallness — perspective-shifting scale",
        "engineering": "admiration — human ingenuity at its peak",
        "psychology": "self-recognition — this is about you too",
        "records": "disbelief and curiosity — how is this even possible",
    }
    return hints.get(category, "surprise and curiosity")


def generate_script(research: dict, target_duration: int = 35) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY missing in .env", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    facts_sorted = sorted(research.get("facts", []), key=lambda f: f.get("order", 99))
    facts_text = "\n".join(
        f"  {i+1}. [{f['impact'].upper()}] {f['fact']}"
        for i, f in enumerate(facts_sorted)
    )

    prompt = USER_PROMPT_TEMPLATE.format(
        topic=research["topic"],
        category=research.get("category", "animal_facts"),
        hook_angle=research.get("hook_angle", ""),
        hook_fact=research["hook_fact"],
        target_duration=target_duration,
        target_words=_target_words(target_duration),
        emotional_angle_hint=_emotional_angle_hint(research.get("category", ""), research.get("hook_angle", "")),
        factual_brief=research["factual_brief"],
        facts_text=facts_text,
    )

    print(f"[script_generator] Writing script for: {research['topic'][:60]}...", flush=True)

    message = client.messages.create(
        model=SONNET_MODEL,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text
    data = _parse_json_response(raw)

    # Validate required fields
    for field in ("topic", "hook", "narration", "cta", "full_script", "title_variants",
                  "emotional_angle", "estimated_duration_seconds", "word_count"):
        if field not in data:
            raise ValueError(f"Response missing required field: {field}")
    if not isinstance(data["title_variants"], list) or len(data["title_variants"]) < 2:
        raise ValueError("'title_variants' must have at least 2 options")

    # Recompute word count and duration from actual full_script for accuracy
    actual_words = len(data["full_script"].split())
    data["word_count"] = actual_words
    data["estimated_duration_seconds"] = round(actual_words / 2.75)
    data["generated_at"] = datetime.now(timezone.utc).isoformat()
    data["model"] = SONNET_MODEL

    return data


def main():
    parser = argparse.ArgumentParser(description="Generate narration script from research brief")
    parser.add_argument("--research-file", required=True,
                        help="Path to research JSON from fact_research.py")
    parser.add_argument("--target-duration", type=int, default=35,
                        help="Target narration duration in seconds (default: 35)")
    parser.add_argument("--output", help="Output JSON path")
    parser.add_argument("--dry-run", action="store_true", help="Print result without saving")
    args = parser.parse_args()

    research_path = Path(args.research_file)
    if not research_path.exists():
        print(f"ERROR: research file not found: {research_path}", file=sys.stderr)
        sys.exit(1)

    research = json.loads(research_path.read_text())

    try:
        result = generate_script(research, target_duration=args.target_duration)
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
        print(f"\n[script_generator] DRY RUN — {result['word_count']} words, "
              f"~{result['estimated_duration_seconds']}s", flush=True)
        return

    out_path = Path(args.output) if args.output else _make_log_path(research["topic"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2))
    print(f"[script_generator] Saved: {out_path}", flush=True)
    print(f"[script_generator] {result['word_count']} words, ~{result['estimated_duration_seconds']}s", flush=True)
    print(f"[script_generator] Hook: {result['hook'][:80]}...", flush=True)


if __name__ == "__main__":
    main()
