#!/usr/bin/env python3
"""
fact_research.py — FactsFactory fact researcher

Takes a topic (string or topic JSON) and produces a concise factual brief
with 8–10 facts ordered by surprise and impact.

Usage:
  python scripts/research/fact_research.py --topic "The mantis shrimp has 16 types of color receptors"
  python scripts/research/fact_research.py --topic-file logs/topics/20260403_animal-facts.json
  python scripts/research/fact_research.py --topic-file logs/topics/20260403_animal-facts.json --dry-run
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

SYSTEM_PROMPT = """You are a fact researcher for a YouTube Shorts educational channel.
Your job is to produce a concise, accurate factual brief that a scriptwriter can use
to write a 25–45 second narration.

Standards:
- Every fact must be widely accepted and verifiable (not disputed or fringe)
- No medical advice, political framing, or unverifiable claims
- Facts should be concrete and specific — avoid vague generalities
- Order facts by: most surprising first, then supporting context, then emotional payoff
- The hook fact should be the single most counterintuitive or jaw-dropping fact

You must return ONLY valid JSON. No markdown, no explanation, no code fences."""

USER_PROMPT_TEMPLATE = """Research this topic and produce a factual brief for a YouTube Shorts script.

Topic: {topic}
Category: {category}
Hook angle: {hook_angle}

Return ONLY valid JSON in this exact structure:
{{
  "topic": "{topic}",
  "category": "{category}",
  "factual_brief": "2-3 sentence summary of what makes this topic compelling and what the script should convey",
  "hook_fact": "The single most surprising or counterintuitive fact — this is the opener",
  "facts": [
    {{
      "fact": "A specific, concrete, verifiable fact statement",
      "impact": "high",
      "is_hook_candidate": true,
      "order": 1
    }}
  ],
  "safety_note": "Brief note on any accuracy caveats or things to avoid saying",
  "fact_count": 8
}}

Rules:
- Generate exactly 8–10 facts
- order field: 1 = most surprising (hook), increasing numbers = supporting/contextual
- impact: "high" for wow-factor facts, "medium" for supporting context
- is_hook_candidate: true only for facts strong enough to open the video
- fact_count must match the actual length of the facts array
- hook_fact must appear verbatim in the facts array at order 1
- Keep each fact statement under 30 words — tight and punchy"""


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
    log_dir = Path("logs/research")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"{date_str}_{slug}.json"


def research_topic(topic: str, category: str = "animal_facts", hook_angle: str = "") -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY missing in .env", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    prompt = USER_PROMPT_TEMPLATE.format(
        topic=topic,
        category=category,
        hook_angle=hook_angle or "not specified",
    )

    print(f"[fact_research] Researching: {topic[:60]}...", flush=True)

    message = client.messages.create(
        model=SONNET_MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text
    data = _parse_json_response(raw)

    # Validate
    for field in ("topic", "factual_brief", "hook_fact", "facts", "fact_count"):
        if field not in data:
            raise ValueError(f"Response missing required field: {field}")
    if not isinstance(data["facts"], list) or len(data["facts"]) < 1:
        raise ValueError("'facts' must be a non-empty list")
    for i, f in enumerate(data["facts"]):
        for req in ("fact", "impact", "is_hook_candidate", "order"):
            if req not in f:
                raise ValueError(f"Fact #{i} missing field: {req}")

    data["generated_at"] = datetime.now(timezone.utc).isoformat()
    data["model"] = SONNET_MODEL
    # Normalize fact_count to match actual array length
    data["fact_count"] = len(data["facts"])

    return data


def main():
    parser = argparse.ArgumentParser(description="Research facts for a YouTube Short topic")
    parser.add_argument("--topic", help="Topic string directly")
    parser.add_argument("--topic-file", help="Path to topic JSON from topic_selector.py")
    parser.add_argument("--output", help="Output JSON path")
    parser.add_argument("--dry-run", action="store_true", help="Print result without saving")
    args = parser.parse_args()

    if not args.topic and not args.topic_file:
        print("ERROR: Provide --topic or --topic-file", file=sys.stderr)
        sys.exit(1)

    topic = args.topic
    category = "animal_facts"
    hook_angle = ""

    if args.topic_file:
        topic_path = Path(args.topic_file)
        if not topic_path.exists():
            print(f"ERROR: topic file not found: {topic_path}", file=sys.stderr)
            sys.exit(1)
        topic_data = json.loads(topic_path.read_text())
        topic = topic_data["topic"]
        category = topic_data.get("category", "animal_facts")
        hook_angle = topic_data.get("hook_angle", "")

    try:
        result = research_topic(topic, category, hook_angle)
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
        print(f"\n[fact_research] DRY RUN — {result['fact_count']} facts for: {result['topic'][:60]}", flush=True)
        return

    out_path = Path(args.output) if args.output else _make_log_path(topic)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2))
    print(f"[fact_research] Saved: {out_path}", flush=True)
    print(f"[fact_research] {result['fact_count']} facts — hook: {result['hook_fact'][:60]}...", flush=True)


if __name__ == "__main__":
    main()
