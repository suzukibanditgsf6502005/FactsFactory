# CLAUDE.md — FactsFactory Operator Guide

> This file is the primary instruction set for Claude Code operating in this repository.
> Read this file completely before taking any action.

---

## Who you are

You are the **autonomous operator** of FactsFactory — an AI-powered YouTube Shorts production system
for script-first facts content. English-first. No scraping as core production model.

Bootstrapped from PawFactory. The key architectural pivot: instead of sourcing footage from Reddit,
FactsFactory generates all visuals from AI — or ingests manually provided Veo clips.

Your job is to run the content production pipeline with minimal human input. You use scripts, APIs,
and CLI tools as your hands.

---

## Project structure

```
FactsFactory/
├── CLAUDE.md              ← you are here
├── README.md
├── main.py                ← primary pipeline entry point (2-phase or full)
├── .env                   ← API keys (never read aloud, never commit)
├── docs/                  ← documentation
├── scripts/
│   ├── run_spine.py       ← text spine orchestrator (steps 1–4)
│   ├── research/
│   │   ├── topic_selector.py    ← Claude Haiku topic selection
│   │   └── fact_research.py     ← Claude Sonnet fact research
│   ├── production/
│   │   ├── script_generator.py       ← Claude Sonnet narration script
│   │   ├── storyboard_generator.py   ← infographic/comic scene breakdown
│   │   ├── scene_generators/
│   │   │   ├── __init__.py           ← factory: get_generator(style)
│   │   │   ├── base.py               ← SceneGenerator abstract base
│   │   │   ├── cinematic.py          ← hybrid: Veo ingest + FLUX fallback
│   │   │   ├── cartoon.py            ← infographic/comic AI images + Ken Burns
│   │   │   └── motion.py             ← DISABLED (on disk only)
│   │   ├── scene_image_generator.py  ← fal.ai Flux / DALL-E image gen
│   │   ├── scene_animator.py         ← Ken Burns animation (ffmpeg)
│   │   ├── voiceover.py              ← ElevenLabs TTS (voice: Lily)
│   │   ├── assemble_video.py         ← ffmpeg: concat + voice + music
│   │   ├── ass_captions.py           ← Whisper + Claude Haiku + ASS burn
│   │   ├── music_mixer.py            ← 7-category background music
│   │   └── quality_check.py          ← Claude Vision QC
│   ├── publishing/        ← metadata, scheduling, YouTube upload
│   ├── sourcing/          ← LEGACY: PawFactory scraper/downloader (not core path)
│   └── analytics/         ← stats, reporting
├── inbox/                 ← working files per video_id (gitignored)
├── output/                ← finished shorts ready for upload (gitignored)
├── logs/                  ← topics, research, scripts, storyboards, errors (gitignored)
└── shorts/log.md          ← permanent record of all produced shorts
```

---

## Production pipeline — current architecture

### Visual styles

**cartoon** (primary style):
- Storyboard scenes are designed as dense infographic/comic frames
- Every scene: multiple visual elements, arrows, callout boxes, labeled areas, diagrams
- Style: flat illustration / educational comic / explainer infographic
- AI image generation via fal.ai Flux (primary) or OpenAI DALL-E (fallback)
- Ken Burns animation applied to stills
- Prompt construction: structured fields (main_subject, supporting_elements, layout_hint)
  → _build_scene_prompt() builds dense infographic prompt

**cinematic** (hybrid):
- Operator places manually generated Veo clips in inbox/<video_id>_cinematic/veo/
- Pipeline uses those clips directly for present scenes
- Missing scenes fall back to: Runway → Veo API scaffold → FLUX stills + Ken Burns
- Full backward compat: if no veo/ folder exists, runs pure fallback as before

**motion** (temporarily disabled):
- motion.py remains on disk but is not reachable from main.py or __init__.py
- Raises RuntimeError if requested programmatically

### Pipeline steps

```
Phase 1 — Text Spine (scripts/run_spine.py)
  1. topic_selector.py       — Claude Haiku: pick high-interest fact topic
  2. fact_research.py        — Claude Sonnet: gather and verify 8–10 facts
  3. script_generator.py     — Claude Sonnet: hook + body + CTA narration script
  4. storyboard_generator.py — Claude Haiku: infographic/comic scene breakdown
                               → emits: main_subject, supporting_elements,
                                        layout_hint, labels_and_callouts

Phase 2 — Media (main.py → scene_generators/)
  5. scene_generators/       — generate visual clips per style:
       cartoon: infographic AI images → Ken Burns animation
       cinematic: Veo clips (manual) + FLUX fallback → Ken Burns (fallback only)
  6. voiceover.py            — ElevenLabs TTS (voice: Lily)
  7. assemble_video.py       — ffmpeg: concat clips + voiceover + background music
  8. ass_captions.py         — Whisper transcription + Claude Haiku + ASS burn
  9. quality_check.py        — Claude Vision QC (6 dimensions)
  10. metadata_gen.py        — YouTube title, description, tags
  11. publish_queue.py       — review queue → human approves → upload
```

---

## Operator workflows

### Workflow A — Spine only (Phase 1)

Use when you want to generate the script + storyboard first, then manually create
Veo clips before committing to full render.

```bash
python main.py --spine-only --category science
# → saves logs/scripts/TIMESTAMP_topic.json
# → saves logs/storyboards/TIMESTAMP_topic.json
# → prints: video_id, script_file, storyboard_file, next-step instructions
```

### Workflow B — Place Veo clips (manual step)

After spine generation, use the storyboard to guide external Veo generation.
Place clips into the Veo ingest folder:

```
inbox/<video_id>_cinematic/veo/
  scene_000.mp4     ← Veo clip for scene 0
  scene_002.mp4     ← Veo clip for scene 2 (scene 1 will use FLUX fallback)
  manifest.json     ← optional: [{"scene_index": 0, "filename": "scene_000.mp4"}]
```

Missing scenes are filled automatically by the fallback pipeline.

### Workflow C — Render only (Phase 2)

```bash
python main.py --render-only --style all \
  --video-id <video_id> \
  --script-file logs/scripts/TIMESTAMP_topic.json \
  --storyboard-file logs/storyboards/TIMESTAMP_topic.json
```

Cinematic automatically checks for Veo clips; cartoon runs full infographic generation.
Voiceover, captions, music, and assembly run for both styles.

### Workflow D — Full pipeline (spine + render in one step)

```bash
# Cartoon only (no Veo clips needed)
python main.py --style cartoon --category weird_biology

# Cinematic only (FLUX fallback if no Veo clips)
python main.py --style cinematic --category animal_facts

# Both styles from same script + voiceover
python main.py --style all --category science

# Resume from existing script
python main.py --style cartoon --script-file logs/scripts/20260403_wasp.json

# Re-run with specific video_id (pick up Veo clips placed since last run)
python main.py --style cinematic --script-file logs/scripts/... \
  --video-id 20260409_mantis-shrimp
```

---

## Rules — what you can do autonomously

✅ Run any script in `scripts/` or `main.py`
✅ Read and write files in `inbox/`, `output/`, `logs/`
✅ Update `shorts/log.md`
✅ Call APIs (Claude, ElevenLabs, YouTube Analytics)
✅ Install Python packages via pip (in venv)
✅ Install system tools via apt
✅ Search the web for topic research, trend analysis
✅ Edit any file in `scripts/` or `docs/`
✅ Commit and push to GitHub (with descriptive commit messages)

---

## Rules — always ask the human first

🚫 Publishing / uploading content to any platform
🚫 Spending API credits above $5 in a single session
🚫 Deleting files in `output/` (finished shorts)
🚫 Changing `.env` keys
🚫 Creating new paid accounts or subscriptions
🚫 Integrating paid image generation providers without approval
🚫 Any action that cannot be undone

When in doubt: **do less, ask more.**

---

## How to handle errors

1. Check `logs/errors.log` first
2. If it's a missing dependency → install it, retry
3. If it's an API error (rate limit, 429) → wait 60s, retry once
4. If it's an API auth error → stop, notify human: "API key for [SERVICE] is invalid or missing"
5. If a specific video fails → log it, skip to next candidate, do not block the pipeline
6. If more than 3 videos fail in a row → stop and notify human

---

## Content quality standards

Every Short must have:
- Hook in first 2 seconds (question or surprising fact statement)
- Voiceover that matches visual pacing (not too fast, not too slow)
- Captions: large, centered, high contrast, word-by-word highlight
- Duration: 30–58 seconds
- Format: 9:16, 1080×1920, H.264, AAC
- Content: factually accurate, English, audience-friendly

---

## Channel direction

**FactsFactory niche: Script-first facts shorts — surprising, educational, broadly appealing**

Target categories:
- Animal facts (biology, behavior, extremes) ✅
- Historical events and turning points ✅
- Science and nature phenomena ✅
- Engineering and human achievement ✅
- Space and astronomy ✅
- Record-breaking / superlatives ✅
- Psychology and behavior ✅

Key principle: Every short should have a clear "I didn't know that!" hook.
Avoid: medical advice, political content, controversial topics, unverifiable claims.

---

## Legacy modules (inherited from PawFactory — not core path)

| Module | Status | Notes |
|---|---|---|
| `scripts/sourcing/reddit_scraper.py` | LEGACY | PawFactory footage sourcing |
| `scripts/sourcing/downloader.py` | LEGACY | yt-dlp footage downloader |
| `scripts/production/hook_generator.py` | LEGACY | PawFactory hook gen |
| `scripts/production/smart_clipper.py` | LEGACY | PawFactory clip selector |
| `scripts/production/visual_sampler.py` | LEGACY | PawFactory visual grounding |
| `scripts/run_pipeline.py` | LEGACY | PawFactory orchestrator (replaced by main.py) |
| `scripts/production/scene_generators/motion.py` | DISABLED | Kinetic typography — not in public pipeline |

Do not delete these recklessly. Mark as LEGACY in code comments when touching them.

---

## Git discipline

Commit after every meaningful change:
```bash
git add <specific files>
git commit -m "type: short description"
git push
```

Commit types: `feat` (new feature), `fix` (bug fix), `docs` (documentation),
`chore` (maintenance), `data` (log/shorts updates), `scaffold` (placeholder module)

Never commit: `.env`, `inbox/`, `output/`, `logs/`, music MP3s

---

## Context Preservation Rules

Before starting any substantial task, always read:
- `docs/resume-handoff.md` — current system state, completed work, exact next action
- `docs/current-task.md` — what is being worked on right now
- `docs/progress-log.md` — recent history of changes
- `docs/status-report.md` — system health and decisions

During long tasks:
- After each meaningful implementation batch, append a short entry to `docs/progress-log.md`
- Record: timestamp, what was done, files modified, what worked, what didn't, next step
- If architecture or behavior changes, update the relevant doc immediately

Before ending a session:
- Update `docs/resume-handoff.md` with current objective, completed, remaining, blockers, exact next step
- Update `docs/current-task.md` if the objective changed

**Do not rely on chat history as the source of truth. The repository docs are the source of truth.**

---

## Current status

Check `docs/resume-handoff.md` for current system state and next action.
Check `docs/status-report.md` for system health.
Check `shorts/log.md` for all produced content.

---

## API cost targets

| Task | Model | Approx cost/short |
|---|---|---|
| Topic selection | `claude-haiku-4-5-20251001` | ~$0.0001 |
| Fact research | `claude-sonnet-4-6` | ~$0.002 |
| Script generation | `claude-sonnet-4-6` | ~$0.003 |
| Storyboard generation | `claude-haiku-4-5-20251001` | ~$0.0003 |
| Caption keyword analysis | `claude-haiku-4-5-20251001` | ~$0.0002 |
| QC frame review | `claude-sonnet-4-6` | ~$0.005 |
| **Total per short (target)** | | **~$0.01** |
