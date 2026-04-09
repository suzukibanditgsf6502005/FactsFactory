# Resume Handoff

> This is the MOST IMPORTANT doc for session continuity.
> Read this first when starting a new session. Update it before ending any session.
> Another AI must be able to resume work from this file alone.

---

## System State — 2026-04-09 (2-phase pipeline + full docs update)

### Completed

| Item | Detail |
|---|---|
| Bootstrap | FactsFactory created from sanitized PawFactory snapshot |
| GitHub repo | github.com/suzukibanditgsf6502005/FactsFactory |
| Text spine | topic_selector → fact_research → script_generator → storyboard_generator — validated |
| scene_image_generator.py v2 | fal.ai Flux primary, DALL-E fallback; _build_scene_prompt() |
| scene_animator.py | Ken Burns via ffmpeg zoompan (pan bug fixed) |
| assemble_video.py | concat + voiceover + music → final mp4 |
| ass_captions.py | Whisper + Claude Haiku + ASS burn (temp-file fix) |
| scene_generators/base.py | SceneGenerator abstract base class |
| scene_generators/cartoon.py v2 | infographic/comic path; legacy fallback for old storyboards |
| scene_generators/cinematic.py v2 | hybrid: _load_veo_clips() + per-scene fallback |
| scene_generators/__init__.py v2 | STYLES = [cinematic, cartoon]; motion raises RuntimeError |
| scene_generators/motion.py | DISABLED — on disk, unreachable |
| storyboard_generator.py v2 | infographic/comic prompts; structured fields (main_subject, supporting_elements, layout_hint, labels_and_callouts) |
| **main.py v4** | **2-phase: --spine-only, --render-only; _run_render() extracted; --storyboard-file added; _make_base_video_id()** |
| **CLAUDE.md** | **fully rewritten — current architecture, all 4 workflows, Veo ingest, style definitions** |
| **README.md** | **fully rewritten — current architecture, 2-phase workflow, styles, layout, API keys** |
| First short | output/wasp-test-001_captioned.mp4 (48.4s, with captions) |
| Motion test | output/motion-test-001_final.mp4 (kinetic typography, verified) |

### In Progress

Nothing. System ready for production batch.

### What Remains (ordered priority)

1. **Cartoon validation batch** — `python main.py --style cartoon --category weird_biology`
2. **2-phase workflow test** — spine-only → place Veo clips → render-only
3. **YouTube OAuth2 setup** — `python scripts/publishing/youtube_uploader.py --auth`
4. **Runway API wiring** — add RUNWAY_API_KEY for automatic Runway cinematic generation
5. **Veo API integration** — when Google opens Veo API publicly
6. **Re-enable motion** — when ready to return to public pipeline

### Blockers

None. All documented workflows are functional.

---

## Exact Next Action

```bash
cd /home/ai-machine/source/FactsFactory
source venv/bin/activate

# Validate cartoon infographic quality
python main.py --style cartoon --category weird_biology

# Test 2-phase workflow
python main.py --spine-only --category animal_facts
# → note video_id, script_file, storyboard_file from output

# (place optional Veo clips)
# mkdir -p inbox/<video_id>_cinematic/veo
# cp /path/to/clip.mp4 inbox/<video_id>_cinematic/veo/scene_000.mp4

python main.py --render-only --style all \
  --video-id <video_id> \
  --script-file logs/scripts/TIMESTAMP_topic.json \
  --storyboard-file logs/storyboards/TIMESTAMP_topic.json
```

---

## Pipeline Architecture

```
Phase 1 — Text Spine
  topic_selector → fact_research → script_generator → storyboard_generator
       [Claude Haiku]  [Claude Sonnet]  [Claude Sonnet]    [Claude Haiku]
                          (infographic/comic scene breakdown)

Phase 2 — Media
  storyboard ──┬──→ CartoonSceneGenerator
               │      infographic/comic AI images + Ken Burns
               │      fal.ai Flux → DALL-E fallback
               │
               └──→ CinematicSceneGenerator (hybrid)
                      _load_veo_clips() → copy Veo clips to animated/
                      fallback: Runway → Veo API → FLUX + Ken Burns
                             ↓
                    voiceover (ElevenLabs, shared across styles)
                             ↓
                    assemble_video (ffmpeg concat + voice + music)
                             ↓
                    ass_captions (Whisper + Claude Haiku + ASS burn)
                             ↓
                 output/{video_id}_cartoon.mp4
                 output/{video_id}_cinematic.mp4
```

## Entry Points

```bash
# Phase 1 only
python main.py --spine-only [--category X] [--script-file ...] [--target-duration N]

# Phase 2 only
python main.py --render-only --style <style|all> \
  --video-id <id> --script-file <path> --storyboard-file <path>

# Full pipeline (spine + render)
python main.py --style <style|all> [--category X] [--video-id <id>] [--dry-run]
```

## Veo Ingest Folder Convention

```
inbox/<video_id>_cinematic/
  veo/
    scene_000.mp4     ← manual Veo clip for scene 0
    scene_002.mp4     ← manual Veo clip for scene 2
    manifest.json     ← optional: [{"scene_index": 0, "filename": "scene_000.mp4"}]
  animated/           ← merged clips (Veo + fallback) — pipeline writes here
  scenes/             ← FLUX still images (fallback scenes only)
```

## Repository Layout (key files)

```
main.py                                    ← 2-phase pipeline entry point
scripts/
  run_spine.py                             ← text spine orchestrator
  research/
    topic_selector.py                      ← v2: Claude Haiku topic picker
    fact_research.py                       ← v1: Claude Sonnet fact gatherer
  production/
    script_generator.py                    ← v2: Claude Sonnet script writer
    storyboard_generator.py                ← v2: infographic/comic scene breakdown
    scene_generators/
      __init__.py                          ← factory: get_generator(style)
      base.py                              ← SceneGenerator ABC
      cinematic.py                         ← v2: hybrid Veo + FLUX fallback
      cartoon.py                           ← v2: infographic/comic + Ken Burns
      motion.py                            ← DISABLED (on disk)
    scene_image_generator.py               ← v2: _build_scene_prompt()
    scene_animator.py                      ← Ken Burns animator (ffmpeg)
    assemble_video.py                      ← concat + voice + music
    ass_captions.py                        ← Whisper + Claude + ASS burn
    voiceover.py                           ← ElevenLabs TTS (voice Lily)
    music_mixer.py                         ← 7-category track selection
    quality_check.py                       ← Claude Vision QC
  publishing/
    metadata_gen.py                        ← YouTube metadata gen
    publish_queue.py                       ← review queue
    youtube_uploader.py                    ← YouTube Data API v3 (needs OAuth2)
```

## Key Configuration

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API — script gen, storyboard, QC, captions |
| `ELEVENLABS_API_KEY` | ElevenLabs TTS |
| `ELEVENLABS_VOICE_ID` | Currently: `pFZP5JQG7iQjIQuC4Bku` (Lily) |
| `FAL_API_KEY` | fal.ai Flux image generation |
| `OPENAI_API_KEY` | DALL-E fallback (optional) |
| `RUNWAY_API_KEY` | Runway Gen-3 video generation (optional — cinematic style) |
| `GOOGLE_API_KEY` | Veo (scaffold — not yet available) |

## Decisions Already Made

| Decision | Rationale |
|---|---|
| Script-first, no scraping | FactsFactory core pivot |
| 2-phase pipeline (spine-only + render-only) | Enables manual Veo ingest between phases |
| Hybrid cinematic | Veo clips used where present; FLUX fills gaps |
| Cartoon = infographic/comic | Multi-element dense frames; more educational + scroll-stopping |
| Motion disabled from public pipeline | Quality not production-ready yet |
| Shared voiceover across styles | Same script → same voice → different visuals |
| Captions shared across styles | Same ASS file reused (same audio) |
| --storyboard-file arg added to main.py | Required for render-only mode |
