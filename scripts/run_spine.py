#!/usr/bin/env python3
"""
run_spine.py — FactsFactory text spine orchestrator

Chains the full text-only production spine:
  topic_selector → fact_research → script_generator → storyboard_generator

Usage:
  # Full run (saves all artifacts)
  python scripts/run_spine.py --category animal_facts

  # Dry run (prints all outputs, saves nothing)
  python scripts/run_spine.py --category animal_facts --dry-run

  # Resume from a saved topic
  python scripts/run_spine.py --topic-file logs/topics/20260403_animal-facts.json

  # Resume from saved research (skip topic + research)
  python scripts/run_spine.py --research-file logs/research/20260403_mantis-shrimp.json

  # Resume from saved script (just generate storyboard)
  python scripts/run_spine.py --script-file logs/scripts/20260403_mantis-shrimp.json

  # Control target duration
  python scripts/run_spine.py --category animal_facts --target-duration 40
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path for module imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.research.topic_selector import select_topic
from scripts.research.fact_research import research_topic
from scripts.production.script_generator import generate_script
from scripts.production.storyboard_generator import generate_storyboard

CATEGORIES = [
    "animal_facts", "weird_biology", "history", "science", "space",
    "engineering", "psychology", "records",
]


def _save(data: dict, subdir: str, slug: str) -> Path:
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_slug = slug[:40].lower().replace(" ", "-").replace("/", "-")
    clean_slug = "".join(c for c in clean_slug if c.isalnum() or c == "-")
    out_dir = Path(f"logs/{subdir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date_str}_{clean_slug}.json"
    out_path.write_text(json.dumps(data, indent=2))
    return out_path


def run_spine(
    category: str = "animal_facts",
    topic_file: str | None = None,
    research_file: str | None = None,
    script_file: str | None = None,
    target_duration: int = 35,
    dry_run: bool = False,
) -> dict:
    """
    Run the full text spine and return a summary dict with all artifact paths.
    In dry_run mode, no files are written; all outputs are printed to stdout.
    """
    separator = "─" * 60
    results = {}

    # ── STEP 1: Topic selection ──────────────────────────────────────────
    if script_file or research_file:
        print(f"\n{separator}")
        print("STEP 1: Topic selection — SKIPPED (using existing file)")
        topic_data = None  # will be populated from downstream file
    elif topic_file:
        print(f"\n{separator}")
        print("STEP 1: Topic selection — SKIPPED (using provided topic file)")
        tp = Path(topic_file)
        if not tp.exists():
            print(f"ERROR: topic file not found: {tp}", file=sys.stderr)
            sys.exit(1)
        topic_data = json.loads(tp.read_text())
        results["topic_file"] = str(tp)
        print(f"  Topic: {topic_data['topic']}")
    else:
        print(f"\n{separator}")
        print(f"STEP 1: Topic selection ({category})")
        topic_data = select_topic(category)
        if dry_run:
            print("\n── Topic Output ──")
            print(json.dumps(topic_data, indent=2))
            results["topic_file"] = "(dry run — not saved)"
        else:
            p = _save(topic_data, "topics", category)
            results["topic_file"] = str(p)
            print(f"  Saved: {p}")
        print(f"  Topic: {topic_data['topic']}")
        print(f"  Score: {topic_data['overall_score']}")

    # ── STEP 2: Fact research ─────────────────────────────────────────────
    if script_file:
        print(f"\n{separator}")
        print("STEP 2: Fact research — SKIPPED (using existing script file)")
        research_data = None
    elif research_file:
        print(f"\n{separator}")
        print("STEP 2: Fact research — SKIPPED (using provided research file)")
        rp = Path(research_file)
        if not rp.exists():
            print(f"ERROR: research file not found: {rp}", file=sys.stderr)
            sys.exit(1)
        research_data = json.loads(rp.read_text())
        results["research_file"] = str(rp)
        print(f"  Hook fact: {research_data['hook_fact'][:70]}...")
    else:
        print(f"\n{separator}")
        print("STEP 2: Fact research")
        research_data = research_topic(
            topic=topic_data["topic"],
            category=topic_data.get("category", category),
            hook_angle=topic_data.get("hook_angle", ""),
        )
        if dry_run:
            print("\n── Research Output ──")
            print(json.dumps(research_data, indent=2))
            results["research_file"] = "(dry run — not saved)"
        else:
            p = _save(research_data, "research", research_data["topic"])
            results["research_file"] = str(p)
            print(f"  Saved: {p}")
        print(f"  Facts: {research_data['fact_count']}")
        print(f"  Hook fact: {research_data['hook_fact'][:70]}...")

    # ── STEP 3: Script generation ─────────────────────────────────────────
    if script_file:
        print(f"\n{separator}")
        print("STEP 3: Script generation — SKIPPED (using provided script file)")
        sp = Path(script_file)
        if not sp.exists():
            print(f"ERROR: script file not found: {sp}", file=sys.stderr)
            sys.exit(1)
        script_data = json.loads(sp.read_text())
        results["script_file"] = str(sp)
        print(f"  Words: {script_data['word_count']}, ~{script_data['estimated_duration_seconds']}s")
    else:
        print(f"\n{separator}")
        print(f"STEP 3: Script generation (target: {target_duration}s)")
        script_data = generate_script(research_data, target_duration=target_duration)
        if dry_run:
            print("\n── Script Output ──")
            print(json.dumps(script_data, indent=2))
            results["script_file"] = "(dry run — not saved)"
        else:
            p = _save(script_data, "scripts", script_data["topic"])
            results["script_file"] = str(p)
            print(f"  Saved: {p}")
        print(f"  Words: {script_data['word_count']}, ~{script_data['estimated_duration_seconds']}s")
        print(f"  Hook: {script_data['hook'][:80]}...")
        print(f"  Titles: {script_data['title_variants'][0]}")

    # ── STEP 4: Storyboard ────────────────────────────────────────────────
    print(f"\n{separator}")
    print("STEP 4: Storyboard generation")
    storyboard_data = generate_storyboard(script_data)
    if dry_run:
        print("\n── Storyboard Output ──")
        print(json.dumps(storyboard_data, indent=2))
        results["storyboard_file"] = "(dry run — not saved)"
    else:
        p = _save(storyboard_data, "storyboards", storyboard_data["topic"])
        results["storyboard_file"] = str(p)
        print(f"  Saved: {p}")
    print(f"  Scenes: {storyboard_data['total_scenes']}, "
          f"~{storyboard_data['total_estimated_duration_seconds']}s total")

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n{separator}")
    print("SPINE COMPLETE")
    print(f"  Topic:       {script_data['topic']}")
    print(f"  Duration:    ~{storyboard_data['total_estimated_duration_seconds']}s")
    print(f"  Scenes:      {storyboard_data['total_scenes']}")
    print(f"  Full script: {script_data['full_script'][:100]}...")
    if not dry_run:
        print("\nArtifacts:")
        for k, v in results.items():
            print(f"  {k}: {v}")
    print(f"\nNext step: implement scene_image_generator.py to generate visuals")

    results["topic"] = script_data["topic"]
    results["storyboard"] = storyboard_data
    results["script"] = script_data
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Run the FactsFactory text spine: topic → research → script → storyboard"
    )
    parser.add_argument("--category", choices=CATEGORIES, default="animal_facts",
                        help="Content category (default: animal_facts)")
    parser.add_argument("--topic-file", help="Resume from saved topic JSON")
    parser.add_argument("--research-file", help="Resume from saved research JSON (skips topic + research)")
    parser.add_argument("--script-file", help="Resume from saved script JSON (generates storyboard only)")
    parser.add_argument("--target-duration", type=int, default=35,
                        help="Target narration duration in seconds (default: 35)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print all outputs to stdout without saving any files")
    args = parser.parse_args()

    run_spine(
        category=args.category,
        topic_file=args.topic_file,
        research_file=args.research_file,
        script_file=args.script_file,
        target_duration=args.target_duration,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
