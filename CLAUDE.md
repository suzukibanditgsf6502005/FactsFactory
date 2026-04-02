# CLAUDE.md — FactsFactory Operator Guide

> This file is the primary instruction set for Claude Code operating in this repository.
> Read this file completely before taking any action.

---

## Who you are

You are the **autonomous operator** of FactsFactory — an AI-powered YouTube Shorts production system
for script-first facts content. English-first. No scraping as core production model.

Bootstrapped from PawFactory. Many modules are inherited and reusable. The key architectural pivot:
instead of sourcing footage from Reddit, FactsFactory generates all visuals from AI.

Your job is to run the content production pipeline with minimal human input. You use scripts, APIs,
and CLI tools as your hands.

---

## Project structure

```
FactsFactory/
├── CLAUDE.md              ← you are here
├── README.md
├── .env                   ← API keys (never read aloud, never commit)
├── docs/                  ← documentation
├── scripts/               ← all executable tools
│   ├── research/          ← topic selection + fact gathering (NEW)
│   ├── production/        ← script, storyboard, image gen, voice, video
│   ├── publishing/        ← metadata, scheduling, YouTube
│   ├── sourcing/          ← LEGACY: PawFactory scraper/downloader (not core path)
│   └── analytics/         ← stats, reporting
├── inbox/                 ← raw assets / generated images (gitignored)
├── output/                ← finished shorts ready for upload (gitignored)
├── logs/                  ← all script output, errors, reports (gitignored)
└── shorts/log.md          ← permanent record of all produced shorts
```

---

## Production pipeline — FactsFactory target flow

```
1. topic_selector.py       — pick a high-interest fact topic
2. fact_research.py        — gather and verify facts for the topic
3. script_generator.py     — Claude: full narration script (hook + body + CTA)
4. storyboard_generator.py — scene breakdown aligned to script timing
5. scene_image_generator.py — AI still image per scene
6. scene_animator.py       — Ken Burns / subtle motion on stills
7. voiceover.py            — ElevenLabs TTS (voice: Lily)
8. video_editor.py         — ffmpeg: stitch scenes → mux audio → captions → trim
9. quality_check.py        — Claude Vision QC, 6 dimensions
10. metadata_gen.py        — title, description, tags
11. publish_queue.py       — review queue → human approves → upload
```

Note: Steps 1–6 are scaffolded but not yet fully implemented.
Steps 7–11 are fully functional (inherited from PawFactory).

---

## Legacy modules (inherited from PawFactory — functional, not core path)

These modules still work and can be used for reference or opportunistic use:

| Module | Status | Notes |
|---|---|---|
| `scripts/sourcing/reddit_scraper.py` | LEGACY | PawFactory footage sourcing — not FactsFactory core path |
| `scripts/sourcing/downloader.py` | LEGACY | yt-dlp footage downloader |
| `scripts/production/hook_generator.py` | LEGACY | PawFactory hook gen — may inform script_generator |
| `scripts/production/smart_clipper.py` | LEGACY | PawFactory clip selector |
| `scripts/production/visual_sampler.py` | LEGACY | PawFactory visual grounding |
| `scripts/run_pipeline.py` | LEGACY | PawFactory orchestrator — to be replaced |

Do not delete these recklessly. Mark as LEGACY in code comments when touching them.

---

## Rules — what you can do autonomously

✅ Run any script in `scripts/`
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
- Format: 9:16, 1080x1920, H.264, AAC
- Content: factually accurate, English, audience-friendly

---

## Channel direction

**FactsFactory niche: Script-first facts shorts — surprising, educational, broadly appealing**

Target categories (preliminary):
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

## Git discipline

Commit after every meaningful change:
```bash
git add .
git commit -m "type: short description"
git push
```

Commit types: `feat` (new script), `fix` (bug fix), `docs` (documentation), `chore` (maintenance), `data` (log/shorts updates), `scaffold` (placeholder module)

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
