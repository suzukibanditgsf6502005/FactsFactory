#!/usr/bin/env python3
"""
music_mixer.py — PawFactory background music layer v2
Selects a music track based on the video's emotional arc (Claude Haiku),
then mixes it under the ElevenLabs voiceover at 8% volume with 2s fades.

Category model (7 categories, 10+ tracks target per category):
  dramatic    — tense, building; danger phase
  uplifting   — warm, hopeful; successful rescue
  ambient     — calm, atmospheric; recovery/nature
  tense       — high-stakes immediate danger
  hopeful     — gentle optimism, mid-rescue turning point
  epic        — grand scale, large wildlife, cinematic
  sad_resolve — bittersweet resolution, hard-fought survival

Track selection:
  - Scans assets/music/{category}/ for MP3 files at runtime
  - Avoids exact track repeat from previous selection
  - Avoids tracks used in the last RECENCY_WINDOW selections if alternatives exist
  - Falls back to a related category if selected category has no tracks
  - Logs every selection to logs/music_history.json

Usage:
  python scripts/production/music_mixer.py --video-id "31s3wpyo"
  python scripts/production/music_mixer.py --video-id "31s3wpyo" --force-category dramatic
"""

import argparse
import json
import os
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
console = Console()

# ── Paths ──────────────────────────────────────────────────────────────────────
MUSIC_DIR    = Path("assets/music")
LOG_DIR      = Path(os.getenv("LOG_DIR", "logs"))
HISTORY_FILE = LOG_DIR / "music_history.json"

# ── Category model ─────────────────────────────────────────────────────────────
ALL_CATEGORIES = [
    "dramatic",
    "uplifting",
    "ambient",
    "tense",
    "hopeful",
    "epic",
    "sad_resolve",
]

# Fallback chain: when a category has no tracks, try this next.
# Chain terminates at ambient (always has at least one track).
FALLBACK_CATEGORY: dict[str, str | None] = {
    "tense":       "dramatic",   # similar energy, darker
    "hopeful":     "uplifting",  # similar warmth
    "epic":        "dramatic",   # similar scope
    "sad_resolve": "ambient",    # similar quietness
    "dramatic":    "ambient",    # last resort before ambient
    "uplifting":   "ambient",    # last resort before ambient
    "ambient":     None,         # terminal — always has tracks
}

# How many recent selections to check when preferring non-recent tracks.
# With 10+ tracks per category this avoids hearing the same track twice in 5 videos.
RECENCY_WINDOW = 5

# Max number of history entries to keep (prevents unbounded file growth)
MAX_HISTORY = 500

# ── Keyword fallback for local classification (no API) ─────────────────────────
_DRAMATIC_WORDS  = {"danger", "desperate", "dying", "trapped", "risk", "threat",
                    "seconds", "drowning", "entangled", "fear", "death", "critical",
                    "urgent", "collapse", "sinking"}
_UPLIFTING_WORDS = {"hope", "relief", "saved", "rescue", "freedom", "joy",
                    "safe", "survive", "triumph", "love", "reunite", "heal",
                    "celebrate", "thriving", "recovered"}
_TENSE_WORDS     = {"seconds", "countdown", "imminent", "last chance", "barely",
                    "almost", "critical", "immediate", "fleeting"}
_EPIC_WORDS      = {"elephant", "whale", "herd", "massive", "grand", "wilderness",
                    "mountain", "ocean", "hundreds", "thousands", "vast"}
_HOPEFUL_WORDS   = {"turning point", "beginning", "slowly", "first sign", "glimpse",
                    "starting to", "emerging"}
_SAD_RESOLVE_WORDS = {"long road", "rehabilitation", "difficult journey", "bittersweet",
                      "partial", "still recovering", "months later"}


def _local_classify(emotional_arc: str) -> str:
    """Keyword-based fallback classification. Returns one of ALL_CATEGORIES."""
    text = emotional_arc.lower()
    scores: dict[str, int] = {cat: 0 for cat in ALL_CATEGORIES}

    for w in _DRAMATIC_WORDS:
        if w in text: scores["dramatic"] += 2
    for w in _UPLIFTING_WORDS:
        if w in text: scores["uplifting"] += 2
    for w in _TENSE_WORDS:
        if w in text: scores["tense"] += 3     # strong signal
    for w in _EPIC_WORDS:
        if w in text: scores["epic"] += 2
    for w in _HOPEFUL_WORDS:
        if w in text: scores["hopeful"] += 2
    for w in _SAD_RESOLVE_WORDS:
        if w in text: scores["sad_resolve"] += 3

    best = max(scores, key=lambda c: scores[c])
    if scores[best] == 0:
        return "ambient"   # no signal — default neutral
    return best


# ── Track discovery ────────────────────────────────────────────────────────────

def discover_tracks(category: str) -> list[str]:
    """
    Return sorted list of MP3 file paths in assets/music/{category}/.
    Returns empty list if the category directory doesn't exist or has no MP3s.
    """
    cat_dir = MUSIC_DIR / category
    if not cat_dir.is_dir():
        return []
    return sorted(str(p) for p in cat_dir.glob("*.mp3"))


def category_track_counts() -> dict[str, int]:
    """Return {category: track_count} for all known categories."""
    return {cat: len(discover_tracks(cat)) for cat in ALL_CATEGORIES}


# ── History I/O ────────────────────────────────────────────────────────────────

def _load_history() -> list[dict]:
    """Load selection history from logs/music_history.json. Returns [] on missing/corrupt."""
    if not HISTORY_FILE.exists():
        return []
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_history(entry: dict, history: list[dict]) -> None:
    """Append entry to history and write to disk, capping at MAX_HISTORY entries."""
    history.append(entry)
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


# ── Track selection ────────────────────────────────────────────────────────────

def _pick_track(category: str, history: list[dict]) -> tuple[str, str, bool]:
    """
    Pick a track within a category, respecting recency rules.

    Returns (resolved_category, track_path, fallback_used).

    Selection rules (in order):
    1. Hard rule: never repeat the exact last track used globally.
    2. Soft rule: prefer tracks not used in the last RECENCY_WINDOW selections.
    3. If all tracks in the category are recent, pick any except the last one.
    4. If category has no tracks, walk the FALLBACK_CATEGORY chain.
    """
    resolved_category = category
    fallback_used = False

    # Walk fallback chain until we find a category with tracks
    for _ in range(len(ALL_CATEGORIES) + 1):
        tracks = discover_tracks(resolved_category)
        if tracks:
            break
        next_cat = FALLBACK_CATEGORY.get(resolved_category)
        if next_cat is None:
            # No tracks anywhere — should never happen in production
            raise RuntimeError(
                f"No music tracks found in any category (started at '{category}'). "
                "Add MP3 files to assets/music/ subdirectories."
            )
        console.print(
            f"  [yellow]Category '{resolved_category}' has no tracks — "
            f"falling back to '{next_cat}'[/yellow]"
        )
        resolved_category = next_cat
        fallback_used = resolved_category != category

    # Recent track set (file paths, last RECENCY_WINDOW selections)
    recent_tracks = {
        entry["track"]
        for entry in history[-RECENCY_WINDOW:]
        if entry.get("track")
    }

    # Hard rule: the very last track globally
    last_track = history[-1].get("track") if history else None

    # Prefer non-recent tracks
    fresh = [t for t in tracks if t not in recent_tracks]
    pool = fresh if fresh else list(tracks)  # all tracks if all are recent

    # Hard rule: exclude the last track if there's at least one alternative
    if last_track and last_track in pool and len(pool) > 1:
        pool = [t for t in pool if t != last_track]

    chosen = random.choice(pool)
    return resolved_category, chosen, fallback_used


# ── Category selection (Claude Haiku) ─────────────────────────────────────────

def select_category(emotional_arc: str) -> str:
    """
    Use Claude Haiku to pick the best music category for this emotional arc.
    Falls back to local keyword classifier if API unavailable or returns unexpected value.
    Returns one of ALL_CATEGORIES.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("  [dim]No ANTHROPIC_API_KEY — using keyword classifier[/dim]")
        return _local_classify(emotional_arc)

    categories_list = ", ".join(ALL_CATEGORIES)
    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=15,
            messages=[{
                "role": "user",
                "content": (
                    f"Background music category for a wildlife rescue Short with this emotional arc:\n"
                    f'"{emotional_arc}"\n\n'
                    f"Categories: {categories_list}\n\n"
                    f"dramatic = tense danger phase\n"
                    f"uplifting = warm successful rescue\n"
                    f"ambient = calm nature/recovery\n"
                    f"tense = immediate crisis, countdown\n"
                    f"hopeful = turning point, hope emerging\n"
                    f"epic = grand scale, large wildlife\n"
                    f"sad_resolve = bittersweet/hard-fought survival\n\n"
                    f"Reply with ONLY the single best category name from the list above."
                ),
            }],
        )
        choice = msg.content[0].text.strip().lower().replace("-", "_")
        if choice in ALL_CATEGORIES:
            return choice
        # Partial match (e.g. "sad resolve" → "sad_resolve")
        for cat in ALL_CATEGORIES:
            if cat in choice:
                return cat
        console.print(f"  [dim]Claude returned unexpected category '{choice}' — using keywords[/dim]")
        return _local_classify(emotional_arc)

    except Exception as e:
        console.print(f"  [yellow]Claude category selection failed ({e}) — using keywords[/yellow]")
        return _local_classify(emotional_arc)


# ── Mix ────────────────────────────────────────────────────────────────────────

def mix_music(
    voiceover_path: str,
    video_id: str,
    track_name: str | None = None,   # legacy: accepts category name
) -> str | None:
    """
    Mix background music under voiceover at 8% volume with 2s fade in/out.
    Returns path to output audio file (inbox/VIDEO_ID_voice_music.mp3), or None on failure.

    track_name (optional): force a specific category (used by --force-category CLI arg).
    """
    inbox_dir = Path(os.getenv("INBOX_DIR", "inbox"))
    out_path  = inbox_dir / f"{video_id}_voice_music.mp3"

    if out_path.exists():
        console.print(f"  [yellow]Music mix already exists: {out_path.name}[/yellow]")
        return str(out_path)

    history = _load_history()

    # ── Category selection ────────────────────────────────────────────────────
    if track_name:
        # --force-category: use exactly this category
        category = track_name if track_name in ALL_CATEGORIES else "ambient"
    else:
        log_dir   = Path(os.getenv("LOG_DIR", "logs"))
        hook_path = log_dir / "hooks" / f"{video_id}.json"
        if hook_path.exists():
            with open(hook_path, encoding="utf-8") as f:
                hook_data = json.load(f)
            emotional_arc = hook_data.get("emotional_arc", "")
            console.print(f"  Emotional arc: {emotional_arc[:90]}")
            category = select_category(emotional_arc)
        else:
            console.print(f"  [dim]No hook JSON found — defaulting to ambient[/dim]")
            category = "ambient"

    console.print(f"  [green]✓ Claude selected track: {category}[/green]")

    # ── Track selection (multi-track, recency-aware) ──────────────────────────
    try:
        resolved_category, music_file_path, fallback_used = _pick_track(category, history)
    except RuntimeError as e:
        console.print(f"  [red]✗ {e}[/red]")
        return None

    if resolved_category != category:
        console.print(
            f"  [yellow]Using '{resolved_category}' tracks "
            f"('{category}' category has no tracks yet)[/yellow]"
        )

    track_basename = Path(music_file_path).name
    console.print(f"  [cyan]Mixing music ({resolved_category}/{track_basename}) into voiceover...[/cyan]")

    # ── ffmpeg mix ────────────────────────────────────────────────────────────
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", str(voiceover_path)],
        capture_output=True, text=True,
    )
    vo_duration = 0.0
    if probe.returncode == 0:
        for stream in json.loads(probe.stdout).get("streams", []):
            if stream.get("codec_type") == "audio":
                vo_duration = float(stream.get("duration", 0))
                break

    fade_out_start = max(0.0, vo_duration - 2.0)

    music_filter = (
        f"[1:a]aloop=loop=-1:size=2e+09,atrim=duration={vo_duration},"
        f"afade=t=in:st=0:d=2,afade=t=out:st={fade_out_start:.2f}:d=2,"
        f"volume=0.08[music];"
        f"[0:a]volume=1.0[vo];"
        f"[vo][music]amix=inputs=2:duration=first[out]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(voiceover_path),
        "-i", str(music_file_path),
        "-filter_complex", music_filter,
        "-map", "[out]",
        "-c:a", "libmp3lame", "-q:a", "4",
        str(out_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        console.print(f"  [red]✗ Music mix failed: {result.stderr[-300:]}[/red]")
        return None

    # ── Log selection to history ──────────────────────────────────────────────
    _save_history({
        "timestamp":       datetime.now(timezone.utc).isoformat(),
        "video_id":        video_id,
        "requested_cat":   category,
        "resolved_cat":    resolved_category,
        "track":           music_file_path,
        "fallback_used":   fallback_used,
    }, history)

    size_kb = out_path.stat().st_size / 1024
    console.print(
        f"  [green]✓ Music mixed: {out_path.name} ({size_kb:.0f} KB) — "
        f"{resolved_category}/{track_basename}[/green]"
    )
    return str(out_path)


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="PawFactory Music Mixer v2")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--force-category", "--force-track",
                        choices=ALL_CATEGORIES,
                        dest="force_category",
                        help="Override Claude category selection")
    parser.add_argument("--voiceover", default=None, help="Path to voiceover MP3")
    parser.add_argument("--list-library", action="store_true",
                        help="Print current track counts per category and exit")
    args = parser.parse_args()

    if args.list_library:
        counts = category_track_counts()
        total = sum(counts.values())
        console.print("\n[bold]Music library:[/bold]")
        for cat in ALL_CATEGORIES:
            n = counts[cat]
            status = "[green]✓[/green]" if n >= 10 else f"[yellow]{n}/10[/yellow]"
            console.print(f"  {cat:<14} {n} track(s)  {status}")
        console.print(f"\n  Total: {total} tracks across {len(ALL_CATEGORIES)} categories")
        return

    inbox_dir = Path(os.getenv("INBOX_DIR", "inbox"))
    voiceover = args.voiceover or str(inbox_dir / f"{args.video_id}_voice.mp3")

    if not Path(voiceover).exists():
        console.print(f"[red]ERROR: Voiceover not found: {voiceover}[/red]")
        sys.exit(1)

    result = mix_music(voiceover, args.video_id, track_name=args.force_category)
    if not result:
        sys.exit(1)


if __name__ == "__main__":
    main()
