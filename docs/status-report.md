# FactsFactory Status Report

> Last updated: 2026-04-09
> For session continuity, read `docs/resume-handoff.md` first.

---

## Current State — 2026-04-09

- **Phase:** 2-phase pipeline complete. All docs updated. System ready for production batch.
- **Shorts produced:** 1 captioned short (wasp-test-001), 1 motion test (motion-test-001)
- **Pipeline status:** Cinematic (hybrid Veo+fallback) + cartoon (infographic/comic) both functional.
  Motion temporarily disabled.
- **Publishing system:** Inherited from PawFactory — awaiting OAuth2 credentials.

---

## Module Status

### Core Pipeline Modules

| Module | Version | Status | Notes |
|---|---|---|---|
| `main.py` | v4 | ✅ UPDATED | 2-phase: `--spine-only`, `--render-only`, full pipeline; `--storyboard-file` added |
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
| `scene_generators/cartoon.py` | v2 | ✅ UPDATED | Infographic/comic path for structured scenes; legacy suffix fallback |
| `scene_generators/cinematic.py` | v2 | ✅ UPDATED | `_load_veo_clips()` + per-scene fallback; Runway/Veo/FLUX chain |
| `scene_generators/__init__.py` | v2 | ✅ UPDATED | `STYLES = [cinematic, cartoon]`; motion raises RuntimeError |

### Media Production Modules

| Module | Version | Status | Notes |
|---|---|---|---|
| `scene_image_generator.py` | v2 | ✅ UPDATED | `_build_scene_prompt()` — infographic from structured fields; fallback to `image_prompt` |
| `scene_animator.py` | v1 | ✅ FUNCTIONAL | Ken Burns; pan bug fixed |
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
| Anthropic (Claude) | ✅ Active | Topic, research, script, storyboard, captions, QC |
| ElevenLabs | ✅ Active | Voice Lily |
| fal.ai | ✅ Active | Flux image generation |
| OpenAI | ✅ Active | DALL-E fallback |
| Runway ML | ⚠️ Not configured | Add RUNWAY_API_KEY for automatic cinematic video gen |
| Google Veo | ⚠️ Scaffold | Not yet publicly available via API |
| YouTube | ⚠️ Needs OAuth2 | Credentials needed for upload |

---

## Output Produced

| File | Style | Duration | Notes |
|---|---|---|---|
| `output/wasp-test-001_captioned.mp4` | cartoon (cinematic prompts, pre-pivot) | 48.4s | First full short |
| `output/motion-test-001_final.mp4` | motion | 48.4s | Motion style test |

---

## Known Limitations

| Issue | Severity | Notes |
|---|---|---|
| Cinematic style = FLUX stills | Medium | Until Runway/Veo API keys are configured or Veo clips placed manually |
| scene_animator upscale 8000px | Low | Slow but working; optimize later if needed |
| ass_captions keyword sets | Low | Scoring originally tuned for PawFactory rescue content |
| Motion style disabled | Low | motion.py on disk; re-enable when production-ready |
| Short text labels in AI images | Low | 1–3 words requested; may render poorly in generated images |
| Hybrid cinematic clip timing | Low | Veo clip duration is fixed; fallback uses storyboard estimates |

---

## Operator Workflow Summary

```
Workflow A (spine only):
  python main.py --spine-only --category science

Workflow B (manual Veo — optional):
  Place clips: inbox/<video_id>_cinematic/veo/scene_000.mp4

Workflow C (render only):
  python main.py --render-only --style all \
    --video-id <id> --script-file <path> --storyboard-file <path>

Workflow D (full pipeline):
  python main.py --style cartoon --category weird_biology
  python main.py --style all --category science
```
