#!/usr/bin/env python3
"""
storyboard_generator.py — FactsFactory scene breakdown

Takes a script JSON (from script_generator.py) and produces a 7–9 scene storyboard
with image prompts, motion hints, and narration segments per scene.

Usage:
  python scripts/production/storyboard_generator.py --script-file logs/scripts/20260403_mantis-shrimp.json
  python scripts/production/storyboard_generator.py --script-file logs/scripts/... --dry-run
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

HAIKU_MODEL = "claude-haiku-4-5-20251001"

MOTION_TYPES = ["static", "slow_zoom_in", "slow_zoom_out", "pan_left", "pan_right"]
VALID_LAYOUT_HINTS = {"split", "overlay", "callout", "cross_section", "before_after", "process_flow"}

SYSTEM_PROMPT = """You are a storyboard artist for a YouTube Shorts facts channel.
You break narration scripts into visual scenes for AI image generation.

Your scenes are designed for INFOGRAPHIC/COMIC-STYLE visual storytelling — dense, educational frames
with multiple elements per scene. Think educational explainer comics, textbook diagrams, and
illustrated fact cards — not photographs.

Each scene needs:
1. A narration segment (exact words from the script for that scene)
2. A scene goal (what this scene must achieve for the viewer)
3. A visual description (what should appear on screen — multiple visual elements)
4. An image prompt (detailed, infographic/comic-style AI generation prompt)
5. Structured visual fields: main_subject, supporting_elements, layout_hint, labels_and_callouts
6. A motion type (how the camera will move on the still image)

Image prompt rules:
- Write as if prompting Flux or DALL-E for an educational infographic or comic panel
- Include MULTIPLE visual elements in ONE frame — not a single subject on a blank background
- Describe: main subject + 2–4 supporting elements + visual layout + diagram style
- Add: arrows, callout boxes, labeled areas, cross-sections, comparison panels, process flows
- Style: flat illustration / educational infographic / comic-book explainer, bold outlines, vibrant colors
- Format: portrait orientation 9:16, no watermarks
- Avoid: photorealism, wildlife photography, single-subject isolation, empty negative space
- Short text labels in the image are OK and encouraged (keep them to 1–3 words each)
- Every frame should look like a page from an educational comic or illustrated facts card

Layout hint types:
- split: two or more side-by-side panels (comparison, before/after)
- overlay: smaller diagram/icon overlaid on the main subject
- callout: labeled arrows pointing to key parts of the main subject
- cross_section: interior cutaway view of the main subject
- before_after: left/right contrast showing change over time
- process_flow: step-by-step visual sequence within the frame

Motion types:
- slow_zoom_in: camera gradually moves closer (wonder, intensity)
- slow_zoom_out: camera pulls back (scale reveal, context)
- pan_left / pan_right: lateral pan (movement, exploration)
- static: no motion (impact moment, payoff)

Scene duration guidelines:
- Hook scene: 3–5 seconds
- Fact scenes: 4–6 seconds each
- Payoff/CTA scene: 3–4 seconds

You must return ONLY valid JSON. No markdown, no explanation, no code fences."""

USER_PROMPT_TEMPLATE = """Create a 7–9 scene storyboard for this YouTube Shorts script.

Topic: {topic}
Emotional angle: {emotional_angle}
Total estimated duration: {estimated_duration_seconds} seconds
Full script:
---
{full_script}
---

Return ONLY valid JSON in this exact structure:
{{
  "topic": "{topic}",
  "total_scenes": 7,
  "total_estimated_duration_seconds": {estimated_duration_seconds},
  "scenes": [
    {{
      "scene_index": 0,
      "scene_goal": "What this scene must accomplish for the viewer (1 sentence)",
      "narration_segment": "Exact words from the script that play during this scene",
      "estimated_duration_seconds": 4.0,
      "visual_description": "Multiple visual elements visible in this educational comic frame",
      "image_prompt": "Dense infographic/comic-style educational scene: [main subject + 2-4 supporting elements], [layout type], [labels and callouts], flat illustration style, bold outlines, vibrant colors, arrows, callout boxes, labeled areas, portrait 9:16, no watermarks",
      "main_subject": "The primary visual focus of this scene (e.g. 'mantis shrimp claw', 'brain diagram')",
      "supporting_elements": [
        "first supporting visual element",
        "second supporting visual element",
        "third supporting visual element"
      ],
      "layout_hint": "callout",
      "labels_and_callouts": ["short label 1", "short label 2"],
      "motion": "slow_zoom_in"
    }}
  ]
}}

Rules:
- total_scenes must match the actual length of the scenes array (7, 8, or 9 scenes)
- Scene 0 is always the hook — use the hook lines from the script
- Last scene is always the payoff + CTA
- narration_segment for all scenes combined must cover the entire full_script with no gaps
- estimated_duration_seconds per scene: derived from word count of narration_segment ÷ 2.75
- Sum of all scene durations should approximately equal total_estimated_duration_seconds
- motion must be one of: static, slow_zoom_in, slow_zoom_out, pan_left, pan_right
- layout_hint must be one of: split, overlay, callout, cross_section, before_after, process_flow
- supporting_elements must be a list of 2 to 4 strings
- labels_and_callouts is optional — omit or set to [] if not applicable
- image_prompt must describe a DENSE multi-element infographic/comic frame, not a single subject"""


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
    log_dir = Path("logs/storyboards")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"{date_str}_{slug}.json"


def _validate_scenes(scenes: list) -> None:
    required = ("scene_index", "scene_goal", "narration_segment",
                 "estimated_duration_seconds", "visual_description", "image_prompt", "motion")
    valid_motions = set(MOTION_TYPES)
    for i, scene in enumerate(scenes):
        for field in required:
            if field not in scene:
                raise ValueError(f"Scene {i} missing field: {field}")
        if scene["motion"] not in valid_motions:
            raise ValueError(f"Scene {i} has invalid motion '{scene['motion']}' — must be one of {MOTION_TYPES}")
        if scene["scene_index"] != i:
            scene["scene_index"] = i  # auto-correct
        # Validate new structured fields when present
        if "supporting_elements" in scene:
            se = scene["supporting_elements"]
            if not isinstance(se, list) or not (2 <= len(se) <= 4):
                raise ValueError(
                    f"Scene {i} supporting_elements must be a list of 2–4 items, got: {se!r}"
                )
        if "layout_hint" in scene:
            if scene["layout_hint"] not in VALID_LAYOUT_HINTS:
                raise ValueError(
                    f"Scene {i} has invalid layout_hint '{scene['layout_hint']}' — "
                    f"must be one of {sorted(VALID_LAYOUT_HINTS)}"
                )


def generate_storyboard(script: dict) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY missing in .env", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    prompt = USER_PROMPT_TEMPLATE.format(
        topic=script["topic"],
        emotional_angle=script.get("emotional_angle", "wonder"),
        estimated_duration_seconds=script.get("estimated_duration_seconds", 35),
        full_script=script["full_script"],
    )

    print(f"[storyboard_generator] Building storyboard for: {script['topic'][:60]}...", flush=True)

    message = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=3000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text
    data = _parse_json_response(raw)

    # Validate top-level fields
    for field in ("topic", "total_scenes", "scenes", "total_estimated_duration_seconds"):
        if field not in data:
            raise ValueError(f"Response missing required field: {field}")
    if not isinstance(data["scenes"], list) or len(data["scenes"]) < 1:
        raise ValueError("'scenes' must be a non-empty list")

    _validate_scenes(data["scenes"])

    # Normalize counts
    data["total_scenes"] = len(data["scenes"])
    data["total_estimated_duration_seconds"] = round(
        sum(s["estimated_duration_seconds"] for s in data["scenes"]), 1
    )
    data["generated_at"] = datetime.now(timezone.utc).isoformat()
    data["model"] = HAIKU_MODEL

    return data


def main():
    parser = argparse.ArgumentParser(description="Generate storyboard from narration script")
    parser.add_argument("--script-file", required=True,
                        help="Path to script JSON from script_generator.py")
    parser.add_argument("--output", help="Output JSON path")
    parser.add_argument("--dry-run", action="store_true", help="Print result without saving")
    args = parser.parse_args()

    script_path = Path(args.script_file)
    if not script_path.exists():
        print(f"ERROR: script file not found: {script_path}", file=sys.stderr)
        sys.exit(1)

    script = json.loads(script_path.read_text())

    try:
        result = generate_storyboard(script)
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
        print(f"\n[storyboard_generator] DRY RUN — {result['total_scenes']} scenes, "
              f"~{result['total_estimated_duration_seconds']}s", flush=True)
        return

    out_path = Path(args.output) if args.output else _make_log_path(script["topic"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2))
    print(f"[storyboard_generator] Saved: {out_path}", flush=True)
    print(f"[storyboard_generator] {result['total_scenes']} scenes, "
          f"~{result['total_estimated_duration_seconds']}s total", flush=True)
    for s in result["scenes"]:
        print(f"  Scene {s['scene_index']}: [{s['motion']:14s}] {s['narration_segment'][:50]}...", flush=True)


if __name__ == "__main__":
    main()
