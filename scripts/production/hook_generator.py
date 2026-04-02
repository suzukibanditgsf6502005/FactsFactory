#!/usr/bin/env python3
"""
hook_generator.py — PawFactory AI script writer
Calls Claude API to generate hook, narration, titles, description, hashtags.
Usage:
  python scripts/production/hook_generator.py --video-id "abc123" --description "Dog rescued from flood"
  python scripts/production/hook_generator.py --from-downloaded  (uses logs/downloaded.json)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
console = Console()

SYSTEM_PROMPT = """You are a YouTube Shorts scriptwriter for an emotional animal stories channel.
Your scripts are emotionally engaging, concise, and grounded in what is actually visible.

Content scope (all accepted):
- Animal rescue and saves
- Recovery, rehab, and second chances
- Animal reunions and homecomings
- Shelter and adoption stories
- Unexpected bonds between humans and animals
- Loyalty and gratitude stories
- Transformation arcs

Rules:
- English only
- No fluff, no filler words
- Hook must create immediate emotional tension or curiosity
- Narration must match the emotional arc of the actual story
- Titles must be curiosity-gap style, not clickbait
- Always end with a soft CTA that feels natural, not forced
- Hashtags must be a mix of high-volume and niche-specific

GROUNDING RULES — critical:
- Write ONLY based on what the visual summary describes as clearly visible
- Do NOT introduce medical details (severity, diagnoses, prognosis) unless the visual
  summary explicitly mentions them
- Do NOT use phrases like "hours to live", "critical condition", "circulation cut off",
  "covered in blood", "emergency surgery saved him" unless the visual summary supports it
- If the visual summary shows something ambiguous, describe it neutrally
- Keep hooks emotional and compelling, but grounded — emotional impact comes from the
  story arc, not from invented medical drama
- The YouTube description should be more conservative than the hook; describe what
  actually happens in the video"""

USER_PROMPT_TEMPLATE = """Write a complete YouTube Shorts script for this emotional animal story.

Video description: {description}
Estimated duration: {duration} seconds
Source: {source}

VISUAL GROUNDING (what is clearly visible in the video — base your script on this):
{visual_summary}

Return ONLY valid JSON, no markdown, no explanation:
{{
  "hook": "Opening 2-3 sentences spoken in first 3 seconds. Create immediate emotional tension or curiosity based on what is actually visible. One sentence = one punch. No invented medical drama — the emotional pull must come from the real situation as shown.",
  "narration": "Main narration for the rest of the video. Emotional, grounded in the visual summary, paced for {duration}s total. Include natural pauses with '...'",
  "full_script": "hook + narration combined, ready to send to voiceover API",
  "title_variants": [
    "Title option 1 — curiosity gap style",
    "Title option 2 — emotion-led",
    "Title option 3 — outcome-focused",
    "Title option 4 — question format",
    "Title option 5 — number/time hook"
  ],
  "description": "YouTube description, 3-4 sentences. Conservative and factual — describe what actually happens. Include credit placeholder [CREDIT]. End with CTA.",
  "hashtags": ["#AnimalRescue", "#SaveAnimals", "#Shorts", "#Wildlife", "#Animals", "niche1", "niche2", "niche3", "niche4", "niche5"],
  "cta": "Call to action spoken at end of video (1 sentence)",
  "content_type": "rescue|recovery|reunion|adoption|bond|loyalty|transformation|unexpected_hero",
  "animal": "primary animal in the video",
  "emotional_arc": "one sentence describing the emotional journey based on what is visible"
}}"""


def generate_hook(video_id, description, duration=45, source="unknown", visual_summary=None):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[red]ERROR: ANTHROPIC_API_KEY missing in .env[/red]")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    # Use visual summary for grounding if provided; otherwise use a neutral fallback
    summary_text = visual_summary or (
        "No visual summary available — use only the video description as context. "
        "Be conservative; do not invent medical or physical details not present in the description."
    )

    prompt = USER_PROMPT_TEMPLATE.format(
        description=description,
        duration=duration,
        source=source,
        visual_summary=summary_text,
    )

    console.print(f"[cyan]Generating hook for {video_id}...[/cyan]")

    try:
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        result = json.loads(raw)
        result["video_id"] = video_id
        result["description_input"] = description
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        result["model"] = "claude-sonnet-4-5"

        return result

    except json.JSONDecodeError as e:
        console.print(f"[red]ERROR: Failed to parse Claude response as JSON: {e}[/red]")
        console.print(f"Raw response: {raw[:300]}")
        return None
    except anthropic.APIError as e:
        console.print(f"[red]ERROR: Anthropic API error: {e}[/red]")
        return None


def shorten_script(hook_data: dict, max_seconds: int) -> dict | None:
    """
    Rewrite hook_data["full_script"] to fit within max_seconds.

    Preserves the hook (opening tension) and payoff (resolution).
    Removes secondary detail and filler. Returns updated hook_data dict
    with full_script, hook, and narration replaced. Returns None on failure.

    Approximate speaking rate for ElevenLabs Lily (dramatic, measured): 2.3 words/sec.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[red]ERROR: ANTHROPIC_API_KEY missing — cannot shorten script[/red]")
        return None

    current_script = hook_data.get("full_script", "").strip()
    if not current_script:
        console.print("[red]ERROR: No full_script in hook data[/red]")
        return None

    word_budget = int(max_seconds * 2.3)
    console.print(
        f"[cyan]Shortening script to fit {max_seconds}s "
        f"(~{word_budget} words at 2.3 w/s)...[/cyan]"
    )

    prompt = (
        f"Rewrite this animal rescue voiceover to fit within {max_seconds} seconds "
        f"(~{word_budget} words at 2.3 words/second for a dramatic narrator).\n\n"
        "Strict rules:\n"
        "- Keep the hook: the first 1–2 sentences must stay — they define the opening tension\n"
        "- Keep the payoff: the rescue must succeed, the resolution must be present\n"
        "- Cut secondary detail and filler first (background context, redundant descriptions)\n"
        "- Preserve the danger → action → relief emotional arc\n"
        "- Keep '...' pauses where they serve pacing\n"
        "- Do not introduce new information not in the original\n"
        "- Do not make it bland — emotional impact matters more than length\n\n"
        "Return ONLY valid JSON, no markdown, no explanation:\n"
        '{"hook": "opening sentences", "narration": "rest of script", '
        '"full_script": "hook + narration combined"}\n\n'
        f"Original script ({len(current_script.split())} words, "
        f"target ≤ {word_budget} words):\n{current_script}"
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        shortened = json.loads(raw)
    except json.JSONDecodeError as e:
        console.print(f"[red]ERROR: Failed to parse shortening response: {e}[/red]")
        return None
    except anthropic.APIError as e:
        console.print(f"[red]ERROR: Anthropic API error during shortening: {e}[/red]")
        return None

    updated = dict(hook_data)
    updated["hook"]        = shortened.get("hook",        hook_data.get("hook", ""))
    updated["narration"]   = shortened.get("narration",   hook_data.get("narration", ""))
    updated["full_script"] = shortened.get("full_script", "")
    updated["shortened_from_words"] = len(current_script.split())
    updated["shortened_to_words"]   = len(updated["full_script"].split())
    updated["shortened_max_seconds"] = max_seconds

    new_words = updated["shortened_to_words"]
    console.print(
        f"  [green]✓ Script shortened: {updated['shortened_from_words']} → "
        f"{new_words} words (target ≤ {word_budget})[/green]"
    )
    return updated


def save_hook(result, video_id):
    log_dir = Path(os.getenv("LOG_DIR", "logs")) / "hooks"
    log_dir.mkdir(parents=True, exist_ok=True)
    out_path = log_dir / f"{video_id}.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    return str(out_path)


def print_result(result):
    console.print("\n[bold green]Generated script:[/bold green]")
    console.print(f"  [bold]Hook:[/bold] {result.get('hook', '')}")
    console.print(f"  [bold]Animal:[/bold] {result.get('animal', '?')}")
    console.print(f"  [bold]Type:[/bold] {result.get('content_type', '?')}")
    console.print(f"\n  [bold]Top title:[/bold] {result.get('title_variants', ['?'])[0]}")
    console.print(f"  [bold]Hashtags:[/bold] {' '.join(result.get('hashtags', [])[:5])}...")


def main():
    parser = argparse.ArgumentParser(description="PawFactory Hook Generator")
    parser.add_argument("--video-id", help="Video ID")
    parser.add_argument("--description", help="Description of the video content")
    parser.add_argument("--duration", type=int, default=45, help="Target narration duration (seconds). Should equal clip_duration * 0.85.")
    parser.add_argument("--source", default="reddit", help="Content source")
    parser.add_argument("--visual-summary-file", default=None,
                        help="Path to visual summary JSON (logs/visuals/{id}_summary.json). "
                             "Auto-loaded if not specified and file exists.")
    parser.add_argument("--from-downloaded", action="store_true",
                        help="Process all videos in logs/downloaded.json that lack hooks")
    parser.add_argument("--shorten", action="store_true",
                        help="Shorten existing script for --video-id to fit --max-duration")
    parser.add_argument("--max-duration", type=int, default=None,
                        help="Hard maximum seconds for shortened script (used with --shorten)")
    parser.add_argument("--test", action="store_true", help="Test API connection only")
    args = parser.parse_args()

    if args.shorten:
        # Shorten an existing script to fit a tighter duration budget.
        # Usage: hook_generator.py --shorten --video-id ID --max-duration SECONDS
        if not args.video_id:
            console.print("[red]ERROR: --shorten requires --video-id[/red]")
            sys.exit(1)
        if not args.max_duration:
            console.print("[red]ERROR: --shorten requires --max-duration SECONDS[/red]")
            sys.exit(1)

        log_dir  = Path(os.getenv("LOG_DIR", "logs"))
        hook_path = log_dir / "hooks" / f"{args.video_id}.json"
        if not hook_path.exists():
            console.print(f"[red]ERROR: Hook file not found: {hook_path}[/red]")
            sys.exit(1)

        with open(hook_path) as f:
            hook_data = json.load(f)

        updated = shorten_script(hook_data, args.max_duration)
        if not updated:
            console.print("[red]✗ Script shortening failed[/red]")
            sys.exit(1)

        save_hook(updated, args.video_id)
        console.print(f"[green]✓ Shortened script saved to {hook_path}[/green]")
        return

    if args.test:
        console.print("[cyan]Testing Anthropic API connection...[/cyan]")
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        try:
            msg = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=20,
                messages=[{"role": "user", "content": "Say OK"}],
            )
            console.print(f"[green]✓ Anthropic API connected: {msg.content[0].text}[/green]")
        except Exception as e:
            console.print(f"[red]✗ Anthropic API failed: {e}[/red]")
            sys.exit(1)
        return

    if args.from_downloaded:
        manifest_path = Path(os.getenv("LOG_DIR", "logs")) / "downloaded.json"
        if not manifest_path.exists():
            console.print("[red]ERROR: logs/downloaded.json not found. Run downloader first.[/red]")
            sys.exit(1)

        with open(manifest_path) as f:
            downloads = json.load(f)

        hooks_dir = Path(os.getenv("LOG_DIR", "logs")) / "hooks"
        processed = 0

        for item in downloads:
            vid_id = item["id"]
            hook_path = hooks_dir / f"{vid_id}.json"

            if hook_path.exists():
                console.print(f"[dim]Skipping {vid_id} — hook already exists[/dim]")
                continue

            if not item.get("file"):
                console.print(f"[yellow]Skipping {vid_id} — no file downloaded[/yellow]")
                continue

            result = generate_hook(
                video_id=vid_id,
                description=item["title"],
                source=item.get("source", "reddit"),
            )

            if result:
                path = save_hook(result, vid_id)
                print_result(result)
                console.print(f"[green]✓ Saved to {path}[/green]\n")
                processed += 1

        console.print(f"\n[green]✓ Generated {processed} hooks[/green]")

    elif args.video_id and args.description:
        # Auto-load visual summary if available
        visual_summary = None
        vs_path = (
            Path(args.visual_summary_file) if args.visual_summary_file
            else Path(os.getenv("LOG_DIR", "logs")) / "visuals" / f"{args.video_id}_summary.json"
        )
        if vs_path.exists():
            with open(vs_path) as _f:
                vs_data = json.load(_f)
            visual_summary = vs_data.get("visual_summary")
            console.print(f"  [dim]Visual summary loaded from {vs_path.name}[/dim]")
        else:
            console.print(f"  [dim]No visual summary found — writing without grounding[/dim]")

        result = generate_hook(
            video_id=args.video_id,
            description=args.description,
            duration=args.duration,
            source=args.source,
            visual_summary=visual_summary,
        )

        if not result:
            sys.exit(1)

        path = save_hook(result, args.video_id)
        print_result(result)
        console.print(f"\n[green]✓ Saved to {path}[/green]")

    else:
        console.print("[red]ERROR: Provide --video-id + --description, or --from-downloaded[/red]")
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
