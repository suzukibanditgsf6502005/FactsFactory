#!/usr/bin/env python3
"""
metadata_gen.py — PawFactory metadata generator
Builds upload-ready metadata JSON from hook data.
Usage:
  python scripts/publishing/metadata_gen.py --video-id "abc123"
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
console = Console()

DESCRIPTION_TEMPLATE = """{description}

🐾 Credit: {credit}

Follow for daily animal stories 🦁🐻🦅
{hashtags}"""

# ── URL stripping — same logic as youtube_uploader.py ─────────────────────────
_URL_RE = re.compile(
    r"https?://\S+"
    r"|www\.\S+"
    r"|\b(?:youtube\.com|youtu\.be|tiktok\.com|instagram\.com"
    r"|reddit\.com|x\.com|twitter\.com)\S*",
    re.IGNORECASE,
)


def _strip_urls(text: str) -> str:
    cleaned = _URL_RE.sub("", text)
    lines = cleaned.splitlines()
    result: list[str] = []
    prev_blank = False
    for line in lines:
        line = line.rstrip()
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue
        result.append(line)
        prev_blank = is_blank
    return "\n".join(result).strip()


def build_metadata(video_id, hook_data, source_credit="Unknown source"):
    title_variants = hook_data.get("title_variants", [])
    primary_title = title_variants[0] if title_variants else f"Animal Rescue — {video_id}"

    hashtags_list = hook_data.get("hashtags", [
        "#AnimalRescue", "#SaveAnimals", "#Shorts", "#Wildlife", "#Animals"
    ])
    hashtags_str = " ".join(hashtags_list)

    base_desc = hook_data.get("description", "An incredible animal rescue story.")
    base_desc = base_desc.replace("[CREDIT]", source_credit)

    full_description = _strip_urls(DESCRIPTION_TEMPLATE.format(
        description=base_desc,
        credit=source_credit,
        hashtags=hashtags_str,
    ))

    output_dir = Path(os.getenv("OUTPUT_DIR", "output"))
    video_file = output_dir / f"{video_id}_final.mp4"

    metadata = {
        "video_id": video_id,
        "file": str(video_file),
        "file_exists": video_file.exists(),
        "title": primary_title,
        "title_variants": title_variants,
        "description": full_description,
        "hashtags": hashtags_list,
        "category": "Pets & Animals",
        "category_id": "15",  # YouTube category ID for Pets & Animals
        "tags": [h.replace("#", "") for h in hashtags_list],
        "language": "en",
        "made_for_kids": False,
        "platform_notes": {
            "youtube": {
                "type": "short",
                "schedule": "post immediately",
                "thumbnail": "auto-generated from video",
            },
            "tiktok": {
                "schedule": "post 2h after YouTube",
                "note": "upload manually — TikTok API requires verification",
            },
            "instagram": {
                "type": "reel",
                "schedule": "post 3h after YouTube",
            },
        },
        "source_credit": source_credit,
        "content_type": hook_data.get("content_type", "rescue"),
        "animal": hook_data.get("animal", "unknown"),
        "emotional_arc": hook_data.get("emotional_arc", ""),
        "cta": hook_data.get("cta", ""),
        "produced_at": datetime.now(timezone.utc).isoformat(),
    }

    return metadata


def main():
    parser = argparse.ArgumentParser(description="PawFactory Metadata Generator")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--hook-json", default=None)
    parser.add_argument("--credit", default=None, help="Source credit string")
    parser.add_argument("--output", default=None, help="Output JSON path")
    args = parser.parse_args()

    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    output_dir = Path(os.getenv("OUTPUT_DIR", "output"))

    # Load hook data
    hook_path = Path(args.hook_json) if args.hook_json else log_dir / "hooks" / f"{args.video_id}.json"
    if not hook_path.exists():
        console.print(f"[red]ERROR: Hook file not found: {hook_path}[/red]")
        sys.exit(1)

    with open(hook_path) as f:
        hook_data = json.load(f)

    # Resolve credit from downloaded manifest if not provided
    credit = args.credit
    if not credit:
        manifest_path = log_dir / "downloaded.json"
        if manifest_path.exists():
            with open(manifest_path) as f:
                downloads = json.load(f)
            for d in downloads:
                if d["id"] == args.video_id:
                    author = d.get("author", "unknown")
                    source = d.get("source", "reddit")
                    credit = f"u/{author} on {source}"
                    break
        if not credit:
            credit = "Original creator"

    metadata = build_metadata(args.video_id, hook_data, credit)

    # Save
    out_path = Path(args.output) if args.output else output_dir / f"{args.video_id}_metadata.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    # Display summary
    console.print(f"\n[bold green]Metadata ready for {args.video_id}:[/bold green]")
    console.print(f"  Title:  {metadata['title']}")
    console.print(f"  Animal: {metadata['animal']}")
    console.print(f"  Type:   {metadata['content_type']}")
    console.print(f"  File:   {metadata['file']} {'[green]✓[/green]' if metadata['file_exists'] else '[red]✗ not found[/red]'}")
    console.print(f"\n[green]✓ Saved to {out_path}[/green]")

    if not metadata["file_exists"]:
        console.print("[yellow]  WARNING: Video file not found — run video_editor.py first[/yellow]")


if __name__ == "__main__":
    main()
