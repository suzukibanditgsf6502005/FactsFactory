# FactsFactory

AI-powered YouTube Shorts production system for script-first facts content.
English-first. No scraping dependency as core content source.
Operated primarily by Claude Code. Minimal human input required.

Bootstrapped from PawFactory (animal rescue shorts pipeline).

---

## What It Does

1. **Selects topics** — AI-driven topic selector picks high-interest fact categories
2. **Researches facts** — AI fact researcher gathers verified, interesting content
3. **Generates scripts** — Claude writes punchy, hook-driven narration scripts
4. **Produces storyboards** — scene-by-scene visual breakdown aligned to script
5. **Generates visuals** — AI-generated still images per scene (no footage required)
6. **Animates scenes** — subtle motion / Ken Burns on stills for visual interest
7. **Produces a finished Short** — voiceover (ElevenLabs) + captions + music + 9:16 output
8. **QC gates** — Claude Vision scores the output; hard-fails are rejected
9. **Queues for review** — human approves, pipeline uploads and schedules to YouTube

---

## Architecture Direction

FactsFactory is a **script-first** pipeline. Unlike PawFactory (which sources footage from Reddit),
FactsFactory generates all visual content from AI. The production flow is:

```
topic_selector  →  fact_research  →  script_generator  →  storyboard_generator
      →  scene_image_generator  →  scene_animator  →  voiceover  →  video_editor
      →  quality_check  →  publish_queue  →  YouTube
```

Inherited from PawFactory (reusable as-is or with minor adaptation):
- `voiceover.py` — ElevenLabs TTS
- `ass_captions.py` — 4-tier ASS captions
- `music_mixer.py` — 7-category background music
- `video_editor.py` — ffmpeg assembly pipeline
- `quality_check.py` — Claude Vision QC
- `metadata_gen.py` — YouTube metadata
- `publish_queue.py` — review queue
- `youtube_uploader.py` — YouTube Data API v3

---

## Quickstart

```bash
git clone https://github.com/suzukibanditgsf6502005/FactsFactory.git
cd FactsFactory
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in API keys
sudo apt install ffmpeg
```

---

## Repository Layout

```
scripts/
  research/
    topic_selector.py        — AI topic selection (SCAFFOLD)
    fact_research.py         — AI fact gathering (SCAFFOLD)
  production/
    script_generator.py      — Claude: hook + full narration script (SCAFFOLD)
    storyboard_generator.py  — scene breakdown from script (SCAFFOLD)
    scene_image_generator.py — AI still image per scene (SCAFFOLD)
    scene_animator.py        — Ken Burns / motion on stills (SCAFFOLD)
    voiceover.py             — ElevenLabs TTS (voice: Lily) [inherited]
    music_mixer.py           — Claude Haiku track selection [inherited]
    video_editor.py          — ffmpeg: 9:16 → mux → captions → trim [inherited]
    ass_captions.py          — Whisper + Claude Haiku + 4-tier ASS [inherited]
    quality_check.py         — Claude Vision QC, 6 dimensions [inherited]
    hook_generator.py        — LEGACY: PawFactory hook gen (kept for reference)
    smart_clipper.py         — LEGACY: PawFactory clip selector (kept for reference)
    visual_sampler.py        — LEGACY: PawFactory visual grounding (kept for reference)
  publishing/
    metadata_gen.py          — title, description, tags [inherited]
    publish_queue.py         — review queue [inherited]
    youtube_uploader.py      — YouTube Data API v3 [inherited]
    tiktok_publisher.py      — TikTok Content Posting API v2 [inherited]
  sourcing/
    reddit_scraper.py        — LEGACY: PawFactory scraper (kept, not core path)
    downloader.py            — LEGACY: PawFactory downloader (kept, not core path)
  run_pipeline.py            — LEGACY: PawFactory orchestrator (to be replaced)

logs/                        — gitignored
inbox/                       — gitignored
output/                      — gitignored
assets/music/                — background music library (7 categories)
assets/fonts/                — Anton-Regular.ttf
docs/                        — documentation
shorts/log.md                — permanent record of all produced content
```

---

## Key Rules

- Script-first: no scraping as production path (sourcing scripts are legacy)
- English-first: all content in English
- Never publish without human approval (`--approve` required)
- Never spend > $5 API credits in a single session
- Never commit `.env`, `inbox/`, `output/`, `logs/`, music MP3s

---

## Required API Keys (.env)

| Variable | Service |
|---|---|
| `ANTHROPIC_API_KEY` | Claude — scripts, QC, captions |
| `ELEVENLABS_API_KEY` | Voiceover (voice Lily) |
| `ELEVENLABS_VOICE_ID` | Currently `pFZP5JQG7iQjIQuC4Bku` |
| `SUBMAGIC_API_KEY` | Caption API (optional — ASS fallback if missing) |
| `YOUTUBE_CLIENT_SECRETS` | Path to OAuth2 JSON from Google Cloud Console |

---

## Full Documentation

| Doc | Contents |
|---|---|
| `docs/resume-handoff.md` | Current system state, completed work, next action |
| `docs/current-task.md` | Active objective and immediate next steps |
| `docs/progress-log.md` | Append-only history of changes |
| `docs/status-report.md` | System health and decisions |
| `docs/caption-system.md` | ASS caption pipeline (inherited from PawFactory) |
| `docs/qa-system.md` | QC scoring, thresholds, provider config |
| `docs/publishing-system.md` | Full publishing guide, OAuth2 setup |
| `docs/workflow.md` | Step-by-step production guide |
| `docs/tools.md` | API setup and costs |
