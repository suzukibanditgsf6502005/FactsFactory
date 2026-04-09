# Resume Handoff

> This is the MOST IMPORTANT doc for session continuity.
> Read this first when starting a new session. Update it before ending any session.
> Another AI must be able to resume work from this file alone.

---

## System State — 2026-04-09 (hybrid cinematic pipeline + cartoon infographic pivot)

### Completed

| Item | Detail |
|---|---|
| Bootstrap | FactsFactory created from sanitized PawFactory snapshot |
| GitHub repo | github.com/suzukibanditgsf6502005/FactsFactory |
| Text spine | topic_selector → fact_research → script_generator → storyboard_generator — validated |
| scene_image_generator.py | fal.ai Flux primary, OpenAI DALL-E fallback |
| scene_animator.py | Ken Burns via ffmpeg zoompan (pan bug fixed — uses `on` variable) |
| assemble_video.py | concat + voiceover + music → final mp4 |
| ass_captions.py | Whisper + Claude Haiku + ASS burn (temp-file fix applied) |
| main.py | Full pipeline entry point with --style routing |
| scene_generators/base.py | SceneGenerator abstract base class |
| scene_generators/motion.py | Kinetic typography — ON DISK, TEMPORARILY DISABLED from public pipeline |
| scene_generators/cartoon.py | fal.ai/DALL-E images + Ken Burns animation |
| scene_generators/cinematic.py | Veo scaffold + Runway scaffold + FLUX fallback |
| First short | output/wasp-test-001_captioned.mp4 (zombie wasp, 48.4s, with captions) |
| Motion test | output/motion-test-001_final.mp4 (kinetic typography, verified) |
| **storyboard_generator.py v2** | **NEW: infographic/comic prompts; emits main_subject, supporting_elements, layout_hint, labels_and_callouts** |
| **scene_image_generator.py v2** | **NEW: _build_scene_prompt() — dense infographic prompt from structured fields; backward compat fallback** |
| **cartoon.py v2** | **NEW: uses infographic path for structured scenes; legacy suffix fallback for old storyboards** |
| **cinematic.py v2** | **NEW: hybrid pipeline — manual Veo clips + AI fallback per scene; _load_veo_clips()** |
| **__init__.py updated** | **NEW: motion removed from STYLES; raises RuntimeError if requested** |
| **main.py v3** | **NEW: --video-id flag; motion removed from CLI; --style all = cinematic + cartoon** |

### In Progress

Nothing. Hybrid cinematic + infographic cartoon pivot both complete.

### What Remains (ordered priority)

1. **Run cartoon validation batch** — `python main.py --style cartoon --category weird_biology`
2. **Evaluate infographic prompt quality** — compare dense multi-element frames vs. old single-subject
3. **Test hybrid cinematic** — place Veo clips in `inbox/<video_id>_cinematic/veo/`, re-run with `--video-id`
4. **YouTube OAuth2 setup** — `python scripts/publishing/youtube_uploader.py --auth`
5. **Runway API wiring** — add RUNWAY_API_KEY to .env for automatic Runway cinematic generation
6. **Veo API integration** — when Google opens Veo API publicly
7. **Re-enable motion** — when ready to return to public pipeline

### Blockers

None. Cinematic falls back to FLUX. Cartoon uses infographic path. Veo ingest is manual + optional.

---

## Exact Next Action

```bash
cd /home/ai-machine/source/FactsFactory
source venv/bin/activate

# Run a cartoon short — new infographic/comic prompts
python main.py --style cartoon --category weird_biology

# Run cinematic with FLUX fallback (note the video_id in output)
python main.py --style cinematic --script-file logs/scripts/TIMESTAMP_topic.json
# Note the base video_id printed at startup: e.g. 20260409_mantis-shrimp

# Place manual Veo clips (external generation):
#   inbox/20260409_mantis-shrimp_cinematic/veo/scene_000.mp4
#   inbox/20260409_mantis-shrimp_cinematic/veo/scene_002.mp4

# Re-run with --video-id to pick up Veo clips + fill rest with FLUX fallback
python main.py --style cinematic --script-file logs/scripts/TIMESTAMP_topic.json \
  --video-id 20260409_mantis-shrimp
```

## Manual Veo Ingest — Folder Convention

```
inbox/
  <video_id>_cinematic/
    veo/
      scene_000.mp4     ← manually generated Veo clip for scene 0
      scene_002.mp4     ← scene 2 (scene 1 will use fallback)
      manifest.json     ← optional: [{"scene_index": 0, "filename": "scene_000.mp4"}, ...]
    animated/           ← pipeline writes all clips here (Veo + fallback merged)
    scenes/             ← FLUX still images (fallback scenes only)
```

---

## Pipeline Architecture

```
topic_selector → fact_research → script_generator → storyboard_generator (v2: infographic fields)
                                                              ↓
                              ┌───────────────────────────────┴──────────────────┐
                              │                               │                   │
                     CinematicSceneGenerator       CartoonSceneGenerator      [motion — DISABLED]
                     (Veo → Runway → FLUX)         infographic/comic prompts
                     photorealistic path           + Ken Burns animation
                              │                               │
                              └───────────────────────────────┘
                                                              ↓
                                                    voiceover (ElevenLabs)
                                                              ↓
                                                    assemble_video (ffmpeg)
                                                              ↓
                                                    ass_captions (Whisper + Claude)
                                                              ↓
                                             output/{video_id}_{style}.mp4
```

## Entry Point

```
python main.py --style cinematic|cartoon|all [options]
# Note: motion is temporarily disabled
```

## Repository Layout (key files)

```
main.py                                    ← NEW: full pipeline entry point
scripts/
  run_spine.py                             ← text spine orchestrator
  research/
    topic_selector.py                      ← v2: Claude Haiku topic picker
    fact_research.py                       ← v1: Claude Sonnet fact gatherer
  production/
    script_generator.py                    ← v2: Claude Sonnet script writer
    storyboard_generator.py                ← v1: scene breakdown
    scene_generators/                      ← NEW package
      __init__.py                          ← factory: get_generator(style)
      base.py                              ← SceneGenerator ABC
      cinematic.py                         ← Veo + Runway + FLUX fallback
      cartoon.py                           ← FLUX/DALL-E + Ken Burns
      motion.py                            ← pure ffmpeg kinetic typography
    scene_image_generator.py               ← fal.ai / OpenAI image gen
    scene_animator.py                      ← Ken Burns animator (ffmpeg)
    assemble_video.py                      ← concat + voice + music
    ass_captions.py                        ← Whisper + Claude + ASS burn
    voiceover.py                           ← ElevenLabs TTS (voice Lily)
    music_mixer.py                         ← 7-category track selection
    quality_check.py                       ← Claude Vision QC (v2)
  publishing/
    metadata_gen.py                        ← YouTube metadata gen
    publish_queue.py                       ← review queue
    youtube_uploader.py                    ← YouTube Data API v3 (needs OAuth2)
```

## Key Configuration

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API — script gen, QC, captions |
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
| 3 visual styles via SceneGenerator | Extensible without touching existing code |
| Motion style as primary test path | No image API cost — fast iteration |
| Cinematic falls back to FLUX | Keeps pipeline working without video API keys |
| Shared voiceover across styles | Same script → same voice → different visuals |
| Captions shared across styles | Same ASS file reused (same audio) |
