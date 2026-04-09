# FactsFactory Status Report

> Last updated: 2026-04-09
> For session continuity, read `docs/resume-handoff.md` first.

---

## Current State — 2026-04-09

- **Phase:** Hybrid cinematic pipeline + cartoon infographic pivot — manual Veo clips supported; storyboard emits structured visual fields; cartoon uses dense multi-element prompts
- **Shorts produced:** 1 captioned short (wasp-test-001), 1 motion test (motion-test-001)
- **Pipeline status:** Cinematic (hybrid Veo+fallback) + cartoon functional. Motion temporarily disabled.
- **Publishing system:** Inherited from PawFactory — awaiting OAuth2 credentials

---

## Module Status

### Core Pipeline Modules

| Module | Version | Status | Notes |
|---|---|---|---|
| `main.py` | v3 | ✅ UPDATED | `--style cinematic\|cartoon\|all`; `--video-id` flag; motion removed |
| `scripts/research/topic_selector.py` | v2 | ✅ VALIDATED | Category descriptions; random top-3 diversity |
| `scripts/research/fact_research.py` | v1 | ✅ VALIDATED | 8–10 facts ordered by impact |
| `scripts/production/script_generator.py` | v2 | ✅ VALIDATED | Hard word count limit; Shorts hooks |
| `scripts/production/storyboard_generator.py` | v2 | ✅ UPDATED | Infographic/comic prompts; structured visual fields |
| `scripts/run_spine.py` | v1 | ✅ WORKING | Full orchestrator; resume from any stage |

### Scene Generator Package

| Module | Version | Status | Notes |
|---|---|---|---|
| `scene_generators/base.py` | v1 | ✅ | SceneGenerator ABC |
| `scene_generators/motion.py` | v1 | ⚠️ DISABLED | On disk only — removed from public pipeline |
| `scene_generators/cartoon.py` | v2 | ✅ UPDATED | Infographic/comic path for structured scenes; legacy fallback |
| `scene_generators/cinematic.py` | v2 | ✅ UPDATED | Hybrid: _load_veo_clips() + per-scene fallback; logs Veo vs. fallback counts |
| `scene_generators/__init__.py` | v2 | ✅ UPDATED | STYLES = [cinematic, cartoon]; motion raises RuntimeError |

### Media Production Modules

| Module | Version | Status | Notes |
|---|---|---|---|
| `scene_image_generator.py` | v2 | ✅ UPDATED | _build_scene_prompt() — infographic from structured fields; fallback to image_prompt |
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
| Motion style disabled | Low | motion.py on disk; needs re-enable when ready |
| Short text labels in AI images | Low | Labels requested in prompts may render poorly; kept short (1–3 words) |
| Hybrid cinematic clip timing | Low | Veo clips have natural duration; fallback clips use storyboard estimates; total timing determined by assemble_video |
