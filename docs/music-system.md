# Music System

> Documents the background music selection and mixing system.
> Code: `scripts/production/music_mixer.py`
> Library: `assets/music/`
> History: `logs/music_history.json`

---

## Overview

Background music is mixed under the voiceover at 8% volume with 2-second fades in and out. The system selects a category and specific track based on the video's emotional arc.

---

## Category Model

7 categories designed for short-form animal rescue content:

| Category | Use when | Energy |
|---|---|---|
| `dramatic` | Danger phase, escalating stakes, before rescue | High |
| `uplifting` | Successful rescue, warm resolution, safe + healed | Medium |
| `ambient` | Calm nature, quiet recovery, observational footage | Low |
| `tense` | Immediate crisis, countdown, time-pressure rescue | Very high |
| `hopeful` | Turning point — rescue underway, hope emerging | Medium |
| `epic` | Grand scale: elephants, whales, large wilderness | High |
| `sad_resolve` | Bittersweet/partial recovery, hard-fought survival | Low-medium |

---

## Library Location

```
assets/music/
  catalog.json          ← track metadata (see below)
  dramatic/
    dramatic_01.mp3     ← Five Armies style, 144s
  uplifting/
    uplifting_01.mp3    ← Inspired style, 286s
  ambient/
    ambient_01.mp3      ← Invariance style, 217s
  tense/
    tense_02.mp3 … tense_06.mp3   ← 5 Epidemic Sound tracks
  hopeful/
    hopeful_02.mp3 … hopeful_06.mp3  ← 5 Epidemic Sound tracks
  epic/
    epic_02.mp3 … epic_04.mp3     ← 3 Epidemic Sound tracks
  sad_resolve/
    sad_resolve_02.mp3 … sad_resolve_04.mp3  ← 3 Epidemic Sound tracks
```

### Current track counts (post wave-1 ingest, 2026-04-01)

| Category | Tracks | Target | Status |
|---|---|---|---|
| dramatic | 8 | 10 | ⚠ needs 2 more |
| uplifting | 6 | 10 | ⚠ needs 4 more |
| ambient | 6 | 10 | ⚠ needs 4 more |
| tense | 5 | 10 | ⚠ needs 5 more |
| hopeful | 5 | 10 | ⚠ needs 5 more |
| epic | 3 | 10 | ⚠ needs 7 more |
| sad_resolve | 3 | 10 | ⚠ needs 7 more |
| **Total** | **36** | **70** | **34 tracks needed** |

All categories now have tracks. The fallback chain is only needed for very heavy repetition with small libraries. Variety is now practical for weekly production volumes.

---

## How to Add New Tracks

### Automated (recommended): Epidemic Sound ingestion

```bash
# See what candidates exist for a category (dry-run)
python scripts/tools/epidemic_ingest.py --category dramatic --list

# Download N tracks for a specific category
python scripts/tools/epidemic_ingest.py --category dramatic --count 5

# Fill all empty/under-stocked categories (3 tracks each)
python scripts/tools/epidemic_ingest.py --all --count 3

# Check current status
python scripts/tools/epidemic_ingest.py --status
```

Requires `EPIDEMIC_API_KEY` in `.env` (JWT bearer token). The script:
1. Searches Epidemic Sound by category-tuned query + mood/BPM filters
2. Downloads full-quality MP3 to `assets/music/{category}/{category}_{NN}.mp3`
3. Adds an entry to `assets/music/catalog.json` automatically
4. Skips tracks already in the catalog (idempotent)

### Manual

1. Drop the MP3 file into `assets/music/{category}/` using the naming convention: `{category}_{NN}.mp3`
   - Example: `assets/music/dramatic/dramatic_02.mp3`
2. Add an entry to `assets/music/catalog.json` under the matching category in the `tracks` array
3. That's it — the system scans the directory at runtime, no code change needed

**Naming convention:** `{category}_{NN}.mp3` where NN is zero-padded (01, 02, ..., 10, 11...). The `_01` slot is reserved for the original Kevin MacLeod tracks. Epidemic Sound tracks start at `_02`.

---

## Selection Logic

### 1. Category selection (Claude Haiku)
Claude Haiku reads the `emotional_arc` field from `logs/hooks/{video_id}.json` and picks one of the 7 categories. Falls back to keyword classifier if API is unavailable.

### 2. Track selection (recency-aware)
Within the selected category:

```
1. Load all MP3s from assets/music/{category}/ 
2. Load last RECENCY_WINDOW (5) selections from logs/music_history.json
3. Prefer tracks NOT in the recent set (fresh pool)
4. If all tracks are recent, use all (can't avoid recency)
5. Hard rule: never use the exact same track as the previous selection (if alternatives exist)
6. Random choice from eligible pool
```

With 10 tracks per category and RECENCY_WINDOW=5: you get 5 fresh choices every time.

### 3. Fallback chain
If the selected category has no tracks, walk this chain:

```
tense       → dramatic
hopeful     → uplifting
epic        → dramatic
sad_resolve → ambient
dramatic    → ambient  (last resort)
uplifting   → ambient  (last resort)
ambient     → (terminal — always has tracks)
```

The fallback is logged in `music_history.json` as `"fallback_used": true`.

---

## History File

`logs/music_history.json` — append-only list capped at 500 entries:

```json
[
  {
    "timestamp": "2026-04-01T17:12:54+00:00",
    "video_id": "31qgcpec",
    "requested_cat": "dramatic",
    "resolved_cat": "dramatic",
    "track": "assets/music/dramatic/dramatic_01.mp3",
    "fallback_used": false
  }
]
```

---

## Track Metadata (catalog.json)

`assets/music/catalog.json` stores lightweight metadata for each track:

```json
{
  "file": "dramatic_01.mp3",
  "energy": "high",
  "mood": ["tense", "building", "urgent"],
  "duration_s": 144,
  "source": "original library",
  "notes": "Five Armies style — orchestral build"
}
```

Fields: `file`, `energy` (high/medium/low), `mood` (tags), `duration_s`, `source`, `notes`.

This file is for human reference and future tooling — the selection system does NOT read it at runtime. It exists to track licensing, energy levels, and expansion notes.

---

## CLI Usage

```bash
# Normal operation (reads hook JSON, uses Claude for category)
python scripts/production/music_mixer.py --video-id abc123

# Force a specific category
python scripts/production/music_mixer.py --video-id abc123 --force-category dramatic

# List current library track counts
python scripts/production/music_mixer.py --video-id dummy --list-library
```

---

## Mixing Parameters

| Parameter | Value |
|---|---|
| Music volume | 8% (0.08) |
| Fade in | 2 seconds |
| Fade out | 2 seconds (before voiceover end) |
| Loop behavior | Music loops if shorter than voiceover |
| Output | `inbox/{video_id}_voice_music.mp3` |

---

## What Needs to Be Done

The 4 empty categories (`tense`, `hopeful`, `epic`, `sad_resolve`) and the 3 under-stocked categories (`dramatic`, `uplifting`, `ambient`) need 67 more royalty-free tracks to reach the 10-per-category target.

Until tracks are added, the fallback chain ensures production continues:
- `tense` and `epic` content gets `dramatic` music
- `hopeful` content gets `uplifting` music
- `sad_resolve` content gets `ambient` music

This is acceptable short-term but not ideal — the wrong category can weaken emotional impact.

**Priority for expansion:** `dramatic` → `uplifting` → `tense` → `epic`

Sources to consider: Pixabay Music, Free Music Archive, YouTube Audio Library (check license for commercial use).
