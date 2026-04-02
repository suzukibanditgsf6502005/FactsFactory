#!/usr/bin/env python3
"""
epidemic_ingest.py — Epidemic Sound track ingestion for PawFactory music library

Searches Epidemic Sound by category, downloads full-quality MP3s to
assets/music/{category}/, and updates assets/music/catalog.json.

Usage:
  # Search and list candidates (dry-run, no downloads)
  python scripts/tools/epidemic_ingest.py --category dramatic --list

  # Download N tracks for a category
  python scripts/tools/epidemic_ingest.py --category dramatic --count 5

  # Download tracks for all categories (fills empty ones first)
  python scripts/tools/epidemic_ingest.py --all --count 3

  # Check current library status
  python scripts/tools/epidemic_ingest.py --status
"""

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

# Make sure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.production.epidemic_client import make_client
from scripts.production.music_mixer import category_track_counts, ALL_CATEGORIES

import subprocess

MUSIC_DIR  = Path("assets/music")
CATALOG    = MUSIC_DIR / "catalog.json"
console    = Console()


def _probe_duration(path: Path) -> float:
    """Return audio duration in seconds via ffprobe. Returns 0.0 on failure."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(path)],
            capture_output=True, text=True, timeout=10,
        )
        for stream in json.loads(r.stdout).get("streams", []):
            if stream.get("codec_type") == "audio":
                return round(float(stream.get("duration", 0)), 1)
    except Exception:
        pass
    return 0.0

# ── Category → search parameters ───────────────────────────────────────────────
# Each entry: (search_topic, mood_slugs, bpm_min, bpm_max)
# mood_slugs are Epidemic Sound tag slugs — used as secondary filter
CATEGORY_SEARCH: dict[str, dict] = {
    "dramatic": {
        "topic": "dramatic cinematic orchestral danger tension",
        "mood_slugs": ["dark", "tense", "dramatic", "suspense", "build"],
        "bpm_min": 80, "bpm_max": 160,
    },
    "uplifting": {
        "topic": "uplifting warm hopeful rescue triumph emotional",
        "mood_slugs": ["happy", "uplifting", "inspiring", "emotional", "hopeful"],
        "bpm_min": 70, "bpm_max": 140,
    },
    "ambient": {
        "topic": "ambient nature calm peaceful atmospheric",
        "mood_slugs": ["ambient", "calm", "peaceful", "meditative", "relaxed"],
        "bpm_min": None, "bpm_max": 90,
    },
    "tense": {
        "topic": "tense urgent countdown crisis immediate danger",
        "mood_slugs": ["tense", "suspense", "dark", "aggressive", "dramatic"],
        "bpm_min": 100, "bpm_max": 180,
    },
    "hopeful": {
        "topic": "hopeful optimistic gentle turning point rescue",
        "mood_slugs": ["hopeful", "uplifting", "positive", "sentimental", "emotional"],
        "bpm_min": 60, "bpm_max": 120,
    },
    "epic": {
        "topic": "epic cinematic grand scale wilderness adventure majestic",
        "mood_slugs": ["epic", "dramatic", "majestic", "powerful", "inspirational"],
        "bpm_min": 80, "bpm_max": 160,
    },
    "sad_resolve": {
        "topic": "bittersweet melancholic resolve survival emotional journey",
        "mood_slugs": ["sad", "melancholic", "sentimental", "emotional", "reflective"],
        "bpm_min": None, "bpm_max": 100,
    },
}

# ── Catalog I/O ─────────────────────────────────────────────────────────────────

def load_catalog() -> dict:
    if CATALOG.exists():
        with open(CATALOG, encoding="utf-8") as f:
            return json.load(f)
    return {"tracks": {cat: [] for cat in ALL_CATEGORIES}}


def save_catalog(catalog: dict):
    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CATALOG, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2)


def catalog_entry(track: dict, category: str, filename: str) -> dict:
    duration_s = track["duration_ms"] / 1000
    energy_map = {
        "dramatic": "high", "tense": "high", "epic": "high",
        "uplifting": "medium", "hopeful": "medium",
        "ambient": "low", "sad_resolve": "low",
    }
    return {
        "file": filename,
        "epidemic_id": track["id"],
        "title": track["title"],
        "bpm": track["bpm"],
        "energy": energy_map.get(category, "medium"),
        "mood": track["tags"][:5],
        "duration_s": round(duration_s, 1),   # may be 0 if API omits; corrected post-download by _fix_duration_from_file
        "source": "epidemic_sound",
        "notes": f"Epidemic Sound: {track['title']}",
    }


def already_ingested(track_id: str, catalog: dict) -> bool:
    for entries in catalog.get("tracks", {}).values():
        for e in entries:
            if e.get("epidemic_id") == track_id:
                return True
    return False


# ── Next filename helper ────────────────────────────────────────────────────────

def next_filename(category: str) -> str:
    cat_dir = MUSIC_DIR / category
    cat_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(cat_dir.glob(f"{category}_*.mp3"))
    if not existing:
        return f"{category}_02.mp3"  # _01 reserved for original Kevin MacLeod tracks
    last = existing[-1].stem  # e.g. "dramatic_03"
    num = int(last.split("_")[-1]) + 1
    return f"{category}_{num:02d}.mp3"


# ── Commands ────────────────────────────────────────────────────────────────────

def cmd_status():
    counts = category_track_counts()
    catalog = load_catalog()
    catalog_counts = {cat: len(catalog.get("tracks", {}).get(cat, [])) for cat in ALL_CATEGORIES}

    table = Table(title="Music Library Status")
    table.add_column("Category", style="cyan")
    table.add_column("Files on disk", justify="center")
    table.add_column("In catalog", justify="center")
    table.add_column("Target", justify="center")
    table.add_column("Need", justify="center")
    for cat in ALL_CATEGORIES:
        n = counts[cat]
        c = catalog_counts[cat]
        need = max(0, 10 - n)
        style = "green" if n >= 10 else ("yellow" if n > 0 else "red")
        table.add_row(cat, f"[{style}]{n}[/{style}]", str(c), "10", str(need))
    console.print(table)


def cmd_list(category: str, count: int):
    params = CATEGORY_SEARCH[category]
    console.print(f"\n[bold]Searching Epidemic Sound: {category}[/bold]")
    console.print(f"  topic: {params['topic']}")

    client = make_client()
    tracks = client.search_tracks(
        topic=params["topic"],
        count=count,
        mood_slugs=params.get("mood_slugs"),
        bpm_min=params.get("bpm_min"),
        bpm_max=params.get("bpm_max"),
    )
    catalog = load_catalog()
    table = Table(title=f"Epidemic Sound results — {category}")
    table.add_column("Title", style="cyan", max_width=40)
    table.add_column("BPM", justify="center")
    table.add_column("Duration", justify="center")
    table.add_column("Tags")
    table.add_column("In catalog?", justify="center")
    for t in tracks:
        dur = f"{t['duration_ms']/1000:.0f}s"
        tags = ", ".join(t["tags"][:4])
        ingested = "✓" if already_ingested(t["id"], catalog) else "—"
        table.add_row(t["title"], str(t["bpm"]), dur, tags, ingested)
    console.print(table)
    console.print(f"\n{len(tracks)} results")


def cmd_download(category: str, count: int):
    if category not in CATEGORY_SEARCH:
        console.print(f"[red]Unknown category: {category}[/red]")
        sys.exit(1)

    params = CATEGORY_SEARCH[category]
    console.print(f"\n[bold]Ingesting tracks: {category}[/bold]")

    client = make_client()
    # Fetch more candidates than needed to allow skipping duplicates
    tracks = client.search_tracks(
        topic=params["topic"],
        count=count * 3,
        mood_slugs=params.get("mood_slugs"),
        bpm_min=params.get("bpm_min"),
        bpm_max=params.get("bpm_max"),
    )

    catalog = load_catalog()
    if category not in catalog.setdefault("tracks", {}):
        catalog["tracks"][category] = []

    downloaded = 0
    for track in tracks:
        if downloaded >= count:
            break
        if already_ingested(track["id"], catalog):
            console.print(f"  [dim]Skip (already in catalog): {track['title']}[/dim]")
            continue

        filename = next_filename(category)
        dest = MUSIC_DIR / category / filename
        console.print(f"  Downloading: {track['title']} → {filename} ({track['duration_ms']/1000:.0f}s, {track['bpm']} BPM)")

        try:
            client.download_track(track["id"], dest)
            size_kb = dest.stat().st_size / 1024
            console.print(f"  [green]✓ {filename} ({size_kb:.0f} KB)[/green]")
        except Exception as e:
            console.print(f"  [red]✗ Download failed: {e}[/red]")
            if dest.exists():
                dest.unlink()
            continue

        entry = catalog_entry(track, category, filename)
        # API sometimes returns 0 for durationInMilliseconds — probe actual file
        if entry["duration_s"] == 0.0:
            entry["duration_s"] = _probe_duration(dest)
        catalog["tracks"][category].append(entry)
        save_catalog(catalog)
        downloaded += 1

    console.print(f"\n[green]✓ Downloaded {downloaded}/{count} tracks for '{category}'[/green]")


def cmd_all(count_per_category: int):
    counts = category_track_counts()
    # Process emptiest categories first
    ordered = sorted(ALL_CATEGORIES, key=lambda c: counts[c])
    for cat in ordered:
        need = max(0, 10 - counts[cat])
        if need == 0:
            console.print(f"  [dim]{cat}: already at target (10)[/dim]")
            continue
        actual_count = min(count_per_category, need)
        cmd_download(cat, actual_count)


# ── CLI ─────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Epidemic Sound track ingestion")
    parser.add_argument("--category", choices=ALL_CATEGORIES, help="Category to ingest")
    parser.add_argument("--count", type=int, default=5, help="Number of tracks to download (default: 5)")
    parser.add_argument("--list", action="store_true", help="List candidates without downloading")
    parser.add_argument("--all", action="store_true", dest="all_cats", help="Download for all categories")
    parser.add_argument("--status", action="store_true", help="Show library status and exit")
    args = parser.parse_args()

    if args.status:
        cmd_status()
        return

    if args.all_cats:
        cmd_all(args.count)
        return

    if not args.category:
        parser.print_help()
        sys.exit(1)

    if args.list:
        cmd_list(args.category, args.count * 2)
    else:
        cmd_download(args.category, args.count)


if __name__ == "__main__":
    main()
