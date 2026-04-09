# FactsFactory

AI-powered YouTube Shorts production system for script-first facts content.
English-first. Minimal human input. Operated primarily by Claude Code.

Bootstrapped from PawFactory (animal rescue shorts pipeline).

---

## What It Does

FactsFactory turns a topic category into a finished, captioned YouTube Short — entirely through AI,
with optional manual Veo clip injection for the cinematic style.

1. **Selects topics** — Claude Haiku picks high-interest fact topics by category
2. **Researches facts** — Claude Sonnet gathers 8–10 verified, compelling facts
3. **Generates scripts** — Claude Sonnet writes a hook-first narration script
4. **Produces storyboards** — scene-by-scene breakdown designed for dense infographic/comic frames
5. **Generates visuals** — style-specific AI image generation or Veo clip ingest
6. **Animates scenes** — Ken Burns motion on stills (cartoon + cinematic fallback)
7. **Produces a finished Short** — ElevenLabs voiceover + word-by-word captions + music
8. **QC gates** — Claude Vision scores the output
9. **Queues for review** — human approves, pipeline uploads to YouTube

---

## Visual Styles

### cartoon (primary style)
- Dense infographic / educational comic frames
- Every scene: multiple visual elements, arrows, callouts, labeled diagrams
- AI image generation (fal.ai Flux primary, DALL-E fallback) + Ken Burns animation
- Best for: complex biology, diagrams, process explanations, comparisons

### cinematic (hybrid)
- Manual Veo clips + AI fallback in one pass
- Operator places `.mp4` clips in `inbox/<video_id>_cinematic/veo/`
- Present clips used directly; missing scenes generate via FLUX + Ken Burns
- Best for: dramatic nature footage, high-motion content, cinematic reveals

### motion (temporarily disabled)
- Kinetic typography via ffmpeg — no image generation required
- On disk (`motion.py`) but not accessible from the public pipeline

---

## Two-Phase Workflow (recommended for Veo)

### Phase 1 — Spine only

Generate the script and storyboard. No API image costs.

```bash
python main.py --spine-only --category science
```

Output:
- `logs/scripts/TIMESTAMP_topic.json`
- `logs/storyboards/TIMESTAMP_topic.json`
- Prints: video_id, file paths, next-step command

### Manual Veo step (optional)

Use the storyboard to guide external Veo generation.
Place clips into the ingest folder:

```
inbox/<video_id>_cinematic/veo/
  scene_000.mp4
  scene_002.mp4
  manifest.json   ← optional explicit mapping
```

### Phase 2 — Render only

```bash
python main.py --render-only --style all \
  --video-id <video_id> \
  --script-file logs/scripts/TIMESTAMP_topic.json \
  --storyboard-file logs/storyboards/TIMESTAMP_topic.json
```

Result:
- `output/<video_id>_cartoon.mp4` — infographic/comic style, full pipeline
- `output/<video_id>_cinematic.mp4` — Veo clips where present + FLUX fallback

---

## Full Pipeline (one step)

```bash
# Cartoon (recommended — no Veo clips needed)
python main.py --style cartoon --category weird_biology

# Cinematic with FLUX fallback
python main.py --style cinematic --category animal_facts

# Both styles from one script + voiceover
python main.py --style all --category science

# Resume from existing script
python main.py --style cartoon --script-file logs/scripts/20260403_wasp.json

# Re-run cinematic with Veo clips placed since last run
python main.py --style cinematic --script-file logs/scripts/... \
  --video-id 20260409_mantis-shrimp
```

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

Run your first spine:

```bash
python main.py --spine-only --category animal_facts
```

---

## Repository Layout

```
main.py                              ← pipeline entry point (2-phase or full)
scripts/
  run_spine.py                       ← text spine orchestrator (steps 1–4)
  research/
    topic_selector.py                ← Claude Haiku topic selection
    fact_research.py                 ← Claude Sonnet fact research
  production/
    script_generator.py              ← Claude Sonnet narration script
    storyboard_generator.py          ← infographic/comic scene breakdown
    scene_generators/
      __init__.py                    ← factory: get_generator(style)
      base.py                        ← SceneGenerator abstract base
      cinematic.py                   ← hybrid: Veo ingest + FLUX fallback
      cartoon.py                     ← infographic/comic AI images + Ken Burns
      motion.py                      ← DISABLED (kinetic typography)
    scene_image_generator.py         ← fal.ai Flux / DALL-E image gen
    scene_animator.py                ← Ken Burns animation (ffmpeg)
    voiceover.py                     ← ElevenLabs TTS (voice: Lily)
    assemble_video.py                ← ffmpeg: concat + voice + music
    ass_captions.py                  ← Whisper + Claude Haiku + ASS burn
    music_mixer.py                   ← 7-category background music selection
    quality_check.py                 ← Claude Vision QC (6 dimensions)
    hook_generator.py                ← LEGACY: PawFactory (reference only)
    smart_clipper.py                 ← LEGACY: PawFactory (reference only)
    visual_sampler.py                ← LEGACY: PawFactory (reference only)
  publishing/
    metadata_gen.py                  ← YouTube title, description, tags
    publish_queue.py                 ← human review queue
    youtube_uploader.py              ← YouTube Data API v3 (needs OAuth2)
  sourcing/
    reddit_scraper.py                ← LEGACY: PawFactory (not core path)
    downloader.py                    ← LEGACY: PawFactory (not core path)
  run_pipeline.py                    ← LEGACY: PawFactory orchestrator

inbox/                               ← working files per video_id (gitignored)
  <video_id>_cinematic/
    veo/                             ← place manual Veo clips here
    animated/                        ← merged clips (Veo + fallback)
    scenes/                          ← FLUX still images (fallback only)
output/                              ← finished mp4 shorts (gitignored)
logs/                                ← topics, research, scripts, storyboards (gitignored)
assets/music/                        ← background music (7 categories)
assets/fonts/                        ← Anton-Regular.ttf
docs/                                ← documentation
shorts/log.md                        ← permanent record of all produced content
```

---

## Required API Keys (.env)

| Variable | Service | Required |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude — scripts, storyboard, QC, captions | ✅ |
| `ELEVENLABS_API_KEY` | Voiceover (voice Lily) | ✅ |
| `ELEVENLABS_VOICE_ID` | Currently `pFZP5JQG7iQjIQuC4Bku` | ✅ |
| `FAL_API_KEY` | fal.ai Flux image generation | ✅ |
| `OPENAI_API_KEY` | DALL-E fallback | optional |
| `RUNWAY_API_KEY` | Runway Gen-3 cinematic generation | optional |
| `GOOGLE_API_KEY` | Veo API (scaffold — not yet public) | optional |
| `YOUTUBE_CLIENT_SECRETS` | OAuth2 JSON for YouTube upload | optional |

---

## Key Rules

- Script-first: no scraping as production path
- English-first: all content in English
- Never publish without human approval
- Never spend > $5 API credits in a single session
- Never commit `.env`, `inbox/`, `output/`, `logs/`, music MP3s

---

## Full Documentation

| Doc | Contents |
|---|---|
| `CLAUDE.md` | Operator guide — workflows, rules, architecture |
| `docs/resume-handoff.md` | Current system state, completed work, next action |
| `docs/current-task.md` | Active objective and immediate next steps |
| `docs/progress-log.md` | Append-only history of changes |
| `docs/status-report.md` | System health and module status |
