# Resume Handoff

> This is the MOST IMPORTANT doc for session continuity.
> Read this first when starting a new session. Update it before ending any session.
> Another AI must be able to resume work from this file alone.

---

## System State — 2026-04-09 (multi-style pipeline complete)

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
| **main.py** | **NEW: Full pipeline entry point with --style routing** |
| **scene_generators/base.py** | **NEW: SceneGenerator abstract base class** |
| **scene_generators/motion.py** | **NEW: Kinetic typography — pure ffmpeg, no image API** |
| **scene_generators/cartoon.py** | **NEW: fal.ai/DALL-E images + Ken Burns animation** |
| **scene_generators/cinematic.py** | **NEW: Veo scaffold + Runway scaffold + FLUX fallback** |
| First short | output/wasp-test-001_captioned.mp4 (zombie wasp, 48.4s, with captions) |
| Motion test | output/motion-test-001_final.mp4 (kinetic typography, verified) |

### In Progress

Nothing. Ready for validation batch.

### What Remains (ordered priority)

1. **Run 2–3 motion shorts** — `python main.py --style motion --category animal_facts`
2. **Run 1–2 cartoon shorts** — `python main.py --style cartoon --category weird_biology`
3. **Evaluate and document quality** — logs/validation/
4. **YouTube OAuth2 setup** — `python scripts/publishing/youtube_uploader.py --auth`
5. **Runway API wiring** — add RUNWAY_API_KEY to .env for true cinematic style
6. **Veo integration** — when Google opens Veo API publicly

### Blockers

None. All 3 styles functional (cinematic falls back to FLUX if no video API keys).

---

## Exact Next Action

```bash
cd /home/ai-machine/source/FactsFactory
source venv/bin/activate

# Run a motion short (fast, no image API cost)
python main.py --style motion --category animal_facts

# Run a cartoon short
python main.py --style cartoon --category weird_biology

# Run all 3 styles from same script
python main.py --style all --category science
```

---

## Pipeline Architecture

```
topic_selector → fact_research → script_generator → storyboard_generator
                                                              ↓
                              ┌───────────────────────────────┴──────────────────────────┐
                              │                               │                           │
                     CinematicSceneGenerator       CartoonSceneGenerator      MotionSceneGenerator
                     (Veo → Runway → FLUX)         (FLUX/DALL-E + Ken Burns)  (ffmpeg kinetic text)
                              │                               │                           │
                              └───────────────────────────────┴──────────────────────────┘
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
python main.py --style cinematic|cartoon|motion|all [options]
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
