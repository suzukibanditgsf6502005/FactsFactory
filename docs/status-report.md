# FactsFactory Status Report

> Last updated: 2026-04-09
> For session continuity, read `docs/resume-handoff.md` first.

---

## Current State — 2026-04-09

- **Phase:** Multi-style pipeline complete — cinematic / cartoon / motion all routable via `main.py`
- **Shorts produced:** 1 captioned short (wasp-test-001), 1 motion test (motion-test-001)
- **Pipeline status:** Full end-to-end pipeline functional for all 3 styles
- **Publishing system:** Inherited from PawFactory — awaiting OAuth2 credentials

---

## Module Status

### Core Pipeline Modules

| Module | Version | Status | Notes |
|---|---|---|---|
| `main.py` | v1 | ✅ NEW | Full pipeline entry — `--style cinematic\|cartoon\|motion\|all` |
| `scripts/research/topic_selector.py` | v2 | ✅ VALIDATED | Category descriptions; random top-3 diversity |
| `scripts/research/fact_research.py` | v1 | ✅ VALIDATED | 8–10 facts ordered by impact |
| `scripts/production/script_generator.py` | v2 | ✅ VALIDATED | Hard word count limit; Shorts hooks |
| `scripts/production/storyboard_generator.py` | v1 | ✅ VALIDATED | 7–9 scenes; image prompts |
| `scripts/run_spine.py` | v1 | ✅ WORKING | Full orchestrator; resume from any stage |

### Scene Generator Package (NEW)

| Module | Version | Status | Notes |
|---|---|---|---|
| `scene_generators/base.py` | v1 | ✅ | SceneGenerator ABC |
| `scene_generators/motion.py` | v1 | ✅ TESTED | Kinetic typography — pure ffmpeg, no API cost |
| `scene_generators/cartoon.py` | v1 | ✅ | Wraps scene_image_generator + scene_animator |
| `scene_generators/cinematic.py` | v1 | ✅ scaffold | Veo + Runway scaffolds; FLUX fallback always works |

### Media Production Modules

| Module | Version | Status | Notes |
|---|---|---|---|
| `scene_image_generator.py` | v1 | ✅ FUNCTIONAL | fal.ai Flux primary, DALL-E fallback |
| `scene_animator.py` | v1 | ✅ FUNCTIONAL | Ken Burns; pan bug fixed (uses `on` variable) |
| `assemble_video.py` | v1 | ✅ FUNCTIONAL | concat + voiceover + music |
| `ass_captions.py` | v3+ | ✅ FUNCTIONAL | Whisper + Claude Haiku; temp-file burn fix |
| `voiceover.py` | inherited | ✅ FUNCTIONAL | ElevenLabs, voice Lily |
| `music_mixer.py` | inherited | ✅ FUNCTIONAL | 7 categories, 36-track catalog |

### Publishing Modules

| Module | Version | Status | Notes |
|---|---|---|---|
| `quality_check.py` | v2 inherited | ✅ FUNCTIONAL | Claude Vision QC |
| `metadata_gen.py` | inherited | ✅ FUNCTIONAL | YouTube metadata gen |
| `publish_queue.py` | inherited | ✅ FUNCTIONAL | Review queue |
| `youtube_uploader.py` | inherited | ✅ built | Needs OAuth2 credentials |

---

## API Key Status

| Service | Status | Notes |
|---|---|---|
| Anthropic (Claude) | ✅ Active | Topic, research, script, storyboard, captions |
| ElevenLabs | ✅ Active | Voice Lily |
| fal.ai | ✅ Active | Flux image generation |
| OpenAI | ✅ Active | DALL-E fallback |
| Runway ML | ⚠️ Not configured | Add RUNWAY_API_KEY for cinematic video generation |
| Google Veo | ⚠️ Scaffold | Not yet publicly available |
| YouTube | ⚠️ Needs OAuth2 | Credentials needed for upload |

---

## Output Produced

| File | Style | Duration | Notes |
|---|---|---|---|
| `output/wasp-test-001_captioned.mp4` | cartoon (cinematic prompts) | 48.4s | First full short, with captions |
| `output/motion-test-001_final.mp4` | motion | 48.4s | Motion style test, with captions |

---

## Known Limitations

| Issue | Severity | Notes |
|---|---|---|
| Cinematic style = FLUX stills | Medium | Looks like cartoon until Runway key configured |
| scene_animator upscale 8000px | Low | Slow but working; optimize later if needed |
| ass_captions keyword sets for rescue content | Low | Works for facts content, but scoring tuned for PawFactory |
| Storyboard prompts can drift fantastical | Medium | Being addressed by prompt improvements |
