# Caption System

> Documents the current dual-pipeline caption system as of 2026-04-01.
> Code: `scripts/production/video_editor.py`, `scripts/production/ass_captions.py`

---

## Architecture Overview

```
video_editor.py (Step 3)
│
├── SUBMAGIC_API_KEY present?
│   ├── YES → _try_submagic() → upload to catbox.moe → POST /v1/projects → poll → download
│   │         └── success → output/ID_final.mp4 (caption_method="submagic")
│   │         └── failure → fall through to ASS
│   │
│   └── NO  → skip Submagic
│
└── ASS path → _apply_ass_captions()
    │   └── loads full_script from logs/hooks/ID.json (passed as script_text)
    │   └── ass_captions.generate_ass_captions(audio, dir, id, script_text) → Whisper + Claude Haiku → write .ass
    │   └── ass_captions.burn_ass_captions(video, ass, output) → ffmpeg -vf "ass=..."
    │         └── success → output/ID_final.mp4 (caption_method="ass")
    │         └── failure → output/ID_final.mp4 (caption_method="none", no captions)
```

The `submagic_captions.py` file exists but is **deprecated** — its logic was absorbed into `video_editor.py`. Do not call it directly.

---

## Primary Path: Submagic

**Script:** `video_editor.py:_try_submagic()`

**How it works:**
1. Upload `output/ID_mixed.mp4` to `litterbox.catbox.moe` (24h temp host)
2. POST `https://api.submagic.co/v1/projects` with `cleanAudio=False` (preserves ElevenLabs voiceover)
3. Poll `GET /v1/projects/{id}` every 10s, max 300s
4. When `status == "completed"`, download from `directUrl`
5. Write to `output/ID_final.mp4`

**Template:** `Sara` — centered, bold, word-highlighting captions.

**Key setting:** `cleanAudio=False` — Submagic does NOT replace audio with its own TTS. The ElevenLabs voiceover is preserved. This was verified via ffprobe.

**When it fails:** Network outage, catbox.moe upload error, Submagic API timeout (5min), no SUBMAGIC_API_KEY.

**Cost:** Consumes Submagic project minutes. Check account balance before long production runs.

---

## Fallback Path: ASS Captions v3

**Script:** `scripts/production/ass_captions.py`

**Entry points called from video_editor.py:**
- `generate_ass_captions(audio_path, output_dir, video_id, script_text=None)` → returns `.ass` file path
- `burn_ass_captions(video_path, ass_path, output_path)` → returns bool

**Key change in v3:** `video_editor.py:_apply_ass_captions()` now loads `full_script` from `logs/hooks/ID.json`
and passes it as `script_text`. This means Claude Haiku analyzes the actual narration script rather than
falling back to the Whisper transcript alone — producing more accurate emphasis.

**Can also be run standalone:**
```bash
python scripts/production/ass_captions.py \
  --audio inbox/ID_voice.mp3 \
  --video output/ID_mixed.mp4 \
  --video-id "ID" \
  --output-dir output/
```

---

### Step 1: Transcription (Whisper)

- Model: `whisper.load_model("small")`
- Mode: `word_timestamps=True`
- Each word gets exact `start`/`end` timestamps
- If `script_text` provided: analysis uses the actual script for keyword detection
- Whisper timestamps remain the timing source regardless

---

### Step 2: Script Analysis (Claude Haiku)

Model: `claude-haiku-4-5-20251001`

**v3 returns 8 categories (expanded from v2's 3):**
```json
{
  "key_words":      ["TRAPPED", "SAVED", "NEVER"],
  "danger_words":   ["DYING", "DROWNING", "TRAPPED"],
  "action_words":   ["GRABBED", "PULLED", "RELEASED"],
  "payoff_words":   ["SURVIVED", "SAFE", "FREE"],
  "turn_words":     ["BUT", "SUDDENLY", "THEN"],
  "cta_words":      ["FOLLOW", "SHARE"],
  "punchline_word": "SURVIVED",
  "hook_end_word":  "ALIVE"
}
```

All words returned uppercase. Empty arrays if category has no strong candidates.

---

### Step 3: 4-Tier Emphasis System

Words are scored 0–100, then mapped to one of 4 display tiers:

| Tier | Score | Scale | Color  | Border | Hold factor | Min duration |
|------|-------|-------|--------|--------|-------------|--------------|
| 0    | 0–17  | 100%  | White  | 4      | 1.00×       | 130 ms       |
| 1    | 18–41 | 110%  | White  | 4      | 1.05×       | 130 ms       |
| 2    | 42–67 | 122%  | Yellow | 4      | 1.25×       | 350 ms       |
| 3    | 68–100| 140%  | Yellow | 5      | 1.20×       | 350 ms + 0.50 s extra |

**Hook zone bonus:** Words in the hook zone (starts before 3.0s OR before the semantic `hook_end_word`)
receive an additional +12% on fscx/fscy if their base tier ≥ 1.

**Hook zone Tier 2 floor:** Words in DANGER_WORDS, ACTION_WORDS, or PAYOFF_WORDS that fall inside
the hook zone are guaranteed Tier 2 (yellow) regardless of score. This ensures the opening 3 seconds
has immediate visible yellow emphasis even when the API is unavailable.

**Scoring breakdown:**
- Claude categories: danger=55, payoff=45, action=38, key=32, turn=22, cta=18 pts
- Local fallback sets: DANGER=28, PAYOFF=22, ACTION=18, URGENCY=14, TENSION=8 pts
- Position multipliers: hook zone ×1.35, ending zone (last 10%) ×1.18
- Score capped at 100

**Function word grouping:** Articles and prepositions (a, an, the, is, was, in, of, etc.) are never
shown in isolation — they are always grouped with the next content word. This applies everywhere
including the hook zone (previously, hook zone was exempt, causing single-letter captions like "A").

---

### Step 4: Event Timeline (Two-Pass Builder)

**Pass 1:** Build events — assign tier, compute display duration, apply hold factor, group function words.

Min duration formula: `max(0.13s, len(text) * 0.055s)` — longer words get more time.

Punchline word: extra +0.50s hold regardless of tier.

**Pass 2:** Clip overlaps — if an event extends into the next event's start, clamp it:
`event["end"] = max(event["start"] + 0.13, next_start - 0.01)`

**Pass 3:** Format to ASS `Dialogue:` strings with inline override tags.

---

### Step 5: ASS File Generation

**ASS header:**
```
[Script Info]
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Style: Default,{font},82,&H00FFFFFF,...,-1,0,0,0,100,100,2,0,1,4,0,2,10,10,655,1
```

Key style parameters:
- `Fontsize=82` — large, readable at mobile screen size
- `Alignment=2` — bottom-center
- `MarginV=655` — positions text at ~66% from top on 1920px canvas
- `Outline=4`, `BorderStyle=1` — thick black outline, no background box
- `Spacing=2` — slight letter spacing

**Color encoding:** ASS uses BBGGRR order (not RRGGBB).
- White: `\c&HFFFFFF&`
- Yellow #FFD700: R=FF, G=D7, B=00 → `\c&H00D7FF&`

**Text display:** All words shown in UPPERCASE. Punctuation stripped.

**Font detection:** `fc-list` searched at runtime. Priority: Anton → Impact → Arial Black → Liberation Sans → DejaVu Sans. Anton font installed at `~/.local/share/fonts/` and committed to `assets/fonts/Anton-Regular.ttf`.

---

### Step 6: Burn into Video (ffmpeg)

```bash
ffmpeg -y -i video.mp4 -vf "ass=captions.ass" \
  -c:v libx264 -preset fast -crf 22 -c:a copy \
  -movflags +faststart output.mp4
```

ASS captions are rendered by libass (bundled with ffmpeg). No separate dependency needed.

**Cache:** `.ass` files cached in `logs/captions/ID.ass`. Re-running won't re-transcribe if file exists.

---

## Changelog

| Version | Changes |
|---------|---------|
| v3.1.1 (2026-04-01) | **Critical case-mismatch bug fix:** `_strip_punct()` returns UPPERCASE but all local frozensets (FUNCTION_WORDS, DANGER_WORDS, etc.) are lowercase. Fix: `clean.lower()` used for all local set lookups in `_score_word`, grouping condition, and hook-zone Tier 2 floor. All three broken behaviors now work: function-word grouping, local keyword scoring, hook-zone yellow floor. Validated on 3 fresh renders. |
| v3.1 (2026-04-01) | Function word grouping extended to hook zone (fixes isolated "A" captions); Tier 2 hold 1.12→1.25×; Tier 3 hold 1.00→1.20× + PUNCHLINE_EXTRA 0.30→0.50 s; TIER2_MIN_DURATION=0.35 s floor for yellow words; hook zone Tier 2 floor for DANGER/ACTION/PAYOFF words |
| v3.0 (2026-04-01) | 4-tier emphasis system; 8-category Claude analysis; hook zone semantic detection; function word grouping (outside hook only); two-pass overlap clipping; `script_text` passed from `video_editor.py` |
| v2 (2026-04-01) | Whisper word timestamps; Claude Haiku key_words/punchline/hook_words (3 categories); Anton font; initial word-by-word system |
| v1 | Whisper SRT; fixed 2-word blocks; no emphasis |

---

## Current Limitations

| Limitation | Severity | Notes |
|---|---|---|
| Submagic consumes project minutes | Medium | Monitor balance; ASS fallback is free |
| Whisper "small" model can mishear proper nouns | Low | 8-category analysis mitigates via script_text |
| ASS alignment can reset in some libass builds | Low | Resolved in v2+ by single-block tag format |
| No multi-language support | Low | English only, by design |
| catbox.moe 24h expiry | Low | Only affects re-downloading — Submagic already has the video |

---

## Testing ASS Captions Standalone

```bash
# Full test on existing video
python scripts/production/ass_captions.py \
  --audio inbox/31s3wpyo_voice.mp3 \
  --video output/31s3wpyo_nocaptions.mp4 \
  --video-id "31s3wpyo_v2" \
  --output-dir output/

# Check output
ffprobe -v quiet output/31s3wpyo_v2_final.mp4 -show_entries stream=duration
```

---

## File Locations

| File | Path |
|---|---|
| ASS module | `scripts/production/ass_captions.py` |
| Video editor (Submagic + routing) | `scripts/production/video_editor.py` |
| ASS cache files | `logs/captions/ID.ass` |
| Anton font | `assets/fonts/Anton-Regular.ttf` |
| System font install | `~/.local/share/fonts/Anton-Regular.ttf` |
