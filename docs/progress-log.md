# Progress Log

> Append-only. Newest entries at the top.
> Format: ## YYYY-MM-DD — short title

---

## 2026-04-09 — Hybrid cinematic pipeline: manual Veo ingest + per-scene fallback

**What was done:**
- **cinematic.py v2**: Added `_load_veo_clips(video_id, scenes)` — checks `inbox/<video_id>/veo/` for manually placed scene clips. Supports `manifest.json` (explicit mapping) or filename inference (`scene_000.mp4`, etc.). Returns empty dict if folder absent (full backward compat). Rewrote `generate_scenes` with 3-step hybrid flow: (1) detect Veo clips and copy to `animated/`, (2) generate fallback only for missing scenes using existing Runway/Veo/FLUX chain, (3) collect all clips from `animated/` in scene order. Logs: "Found Veo clip for scene N", "Using fallback for scene N", "Total Veo scenes: N", "Total fallback scenes: M". When Veo clips exist, `voice_duration` scaling is skipped for fallback (prevents distributing full voice duration across only fallback scenes).
- **main.py v3**: Added `--video-id` CLI flag. When provided, used as `base_video_id` directly instead of auto-generating. Style suffix appended as normal (`--video-id 20260409_mantis-shrimp` → cinematic video_id `20260409_mantis-shrimp_cinematic`). Updated module docstring with full manual Veo ingest workflow. Updated `run()` signature with `video_id=None` param.
- Updated all 4 docs with Veo folder convention, hybrid pipeline description, and updated next steps.

**Files changed:**
- `scripts/production/scene_generators/cinematic.py` (v1 → v2)
- `main.py` (v2 → v3)
- `docs/current-task.md`, `docs/resume-handoff.md`, `docs/status-report.md`, `docs/progress-log.md`

**Veo folder convention:**
```
inbox/<video_id>_cinematic/veo/
  scene_000.mp4        ← manual Veo clip for scene 0
  scene_002.mp4        ← manual Veo clip for scene 2
  manifest.json        ← optional: [{"scene_index": 0, "filename": "scene_000.mp4"}]
```

**Next step:** `python main.py --style cartoon --category weird_biology` — cartoon infographic validation

---

## 2026-04-09 — Cartoon infographic/comic pivot + motion disabled

**What was done:**
- **storyboard_generator.py v2**: Rewrote SYSTEM_PROMPT and USER_PROMPT_TEMPLATE for infographic/comic-style visual storytelling. Scenes now emit 4 new structured fields: `main_subject` (string), `supporting_elements` (list 2–4), `layout_hint` (one of 6 allowed values), `labels_and_callouts` (optional list). Removed photorealism/wildlife instructions. Updated `_validate_scenes` to validate the new fields. Added `VALID_LAYOUT_HINTS` constant.
- **scene_image_generator.py v2**: Removed global `PROMPT_SUFFIX`. Added `_build_scene_prompt(scene)` — builds a dense infographic/comic prompt from structured fields when present; falls back to `scene["image_prompt"]` for older storyboard files (backward compat). Updated `generate_scene_images` to call `_build_scene_prompt` per scene. Removed `+ PROMPT_SUFFIX` from `_generate_fal` and `_generate_openai`.
- **cartoon.py v2**: Replaced `_patch_prompts` + flat suffix approach with `_apply_cartoon_style`. Scenes WITH structured fields are passed through — `_build_scene_prompt` handles them. Scenes WITHOUT structured fields get legacy cartoon suffix on `image_prompt` for backward compat. Ken Burns animation unchanged.
- **cinematic.py**: Updated `_patch_scene_for_cinematic` to also clear the 4 new structured fields after patching `image_prompt`, so `generate_scene_images` uses the cinematic photorealistic path rather than the infographic/comic path.
- **scene_generators/__init__.py**: Removed `MotionSceneGenerator` import. `STYLES = ["cinematic", "cartoon"]`. `get_generator("motion")` now raises `RuntimeError` with clear message instead of importing.
- **main.py v2**: Removed motion from module docstring, usage examples, and argparse epilog. `--style all` now means cinematic + cartoon. Help text updated.
- Updated all 4 docs: current-task.md, resume-handoff.md, status-report.md, progress-log.md.

**Files changed:**
- `scripts/production/storyboard_generator.py` (v1 → v2)
- `scripts/production/scene_image_generator.py` (v1 → v2)
- `scripts/production/scene_generators/cartoon.py` (v1 → v2)
- `scripts/production/scene_generators/cinematic.py` (patch)
- `scripts/production/scene_generators/__init__.py` (v1 → v2)
- `main.py` (v1 → v2)
- `docs/current-task.md`, `docs/resume-handoff.md`, `docs/status-report.md`, `docs/progress-log.md`

**Next step:** `python main.py --style cartoon --category weird_biology` — validate infographic prompt quality

---

## 2026-04-09 — Multi-style pipeline: cinematic / cartoon / motion + main.py

**What was done:**
- Created `scripts/production/scene_generators/` package with:
  - `base.py` — `SceneGenerator` abstract base class (generate_scenes interface)
  - `motion.py` — `MotionSceneGenerator`: kinetic typography via ffmpeg, no image API
  - `cartoon.py` — `CartoonSceneGenerator`: wraps scene_image_generator + scene_animator with flat illustration prompts
  - `cinematic.py` — `CinematicSceneGenerator`: Veo scaffold + Runway scaffold + FLUX fallback
  - `__init__.py` — `get_generator(style)` factory function
- Created `main.py` — full pipeline entry point:
  - `--style cinematic|cartoon|motion|all`
  - `--category`, `--target-duration`, `--no-music`, `--no-captions`, `--dry-run`
  - `--style all` generates all 3 styles from one voiceover + storyboard
  - Text spine shared across styles; voiceover generated once
- Fixed `ass_captions.py` bug: local `import os` inside function was shadowing module-level `os`, causing `UnboundLocalError` — replaced with `Path.unlink(missing_ok=True)`
- Tested motion generator end-to-end: 8/8 clips in ~3s, assembled, captioned OK
- Tested `--style all --dry-run`: all 3 style routes confirmed working
- Updated all docs: current-task.md, resume-handoff.md, status-report.md, progress-log.md

**Files changed:**
- `main.py` (new)
- `scripts/production/scene_generators/__init__.py` (new)
- `scripts/production/scene_generators/base.py` (new)
- `scripts/production/scene_generators/motion.py` (new)
- `scripts/production/scene_generators/cartoon.py` (new)
- `scripts/production/scene_generators/cinematic.py` (new)
- `scripts/production/ass_captions.py` (bug fix)
- `docs/current-task.md`, `docs/resume-handoff.md`, `docs/status-report.md`, `docs/progress-log.md`

**Next step:** Run real validation batch: `python main.py --style motion --category animal_facts`

---

## 2026-04-03 — First short produced: wasp-test-001 (zombie wasp, 48.4s)

**What was done:**
- Ran end-to-end: topic → research → script → storyboard → images → animate → assemble → captions
- Images: 8 scenes via fal.ai Flux (576×1024 JPEG, 81–137KB each)
- Animator: Ken Burns via ffmpeg zoompan — pan_right bug fixed (changed `t` → `on`, hardcoded 0.04762 constant)
- Assembly: 8 clips concatenated + ElevenLabs voiceover (48.43s)
- Captions: Whisper transcription + Claude Haiku analysis + ASS burn
- Output: output/wasp-test-001_captioned.mp4 (4MB, 48.4s, 1080×1920)
- Fixed ass_captions.py CLI to burn via temp file → prevents same-file input/output error

**Files changed:**
- scripts/production/scene_animator.py (pan_right/pan_left formula fix)
- scripts/production/ass_captions.py (temp-file burn fix)
- scripts/production/assemble_video.py (new)

**Next step:** Multi-style pipeline refactor

---

## 2026-04-03 — Env audit + scene_image_generator + scene_animator implemented

**What was done:**
- Audited .env and .env.example; normalized both for FactsFactory stack
- Implemented scene_image_generator.py (fal.ai Flux primary, DALL-E fallback)
- Improved storyboard image prompts (organism visual descriptions, CRITICAL note added)
- Implemented scene_animator.py (Ken Burns via ffmpeg zoompan)
- Generated first 8 test images (wasp-test-001) via fal.ai
- Generated voiceover via ElevenLabs (48.43s, voice Lily)

**Files changed:**
- scripts/production/scene_image_generator.py (scaffold → v1)
- scripts/production/scene_animator.py (scaffold → v1)
- scripts/production/storyboard_generator.py (prompt improvement)
- .env.example (rewritten for FactsFactory)

---

## 2026-04-03 — Text spine validation pass: 10 runs, critical issues fixed

**What was done:**
- Ran 10 validation runs across animal_facts + weird_biology
- Fixed 3 critical issues: topic diversity, category context, word count drift
- Wrote validation summary: logs/validation/spine_validation_20260403.md

**Files changed:**
- scripts/research/topic_selector.py (v1 → v2)
- scripts/production/script_generator.py (v1 → v2)
- scripts/run_spine.py (weird_biology added)
- docs/*

---

## 2026-04-03 — Text spine implemented: topic → research → script → storyboard

**What was done:**
- Implemented all 4 text spine modules from scaffold
- Created run_spine.py orchestrator with --dry-run and resume flags
- Verified end-to-end with live API calls

**Files changed:**
- scripts/research/topic_selector.py, fact_research.py (scaffold → v1)
- scripts/production/script_generator.py, storyboard_generator.py (scaffold → v1)
- scripts/run_spine.py (new)

---

## 2026-04-03 — Bootstrap: FactsFactory created from PawFactory

**What was done:**
- rsync from PawFactory, excluding .git/.env/venv/inbox/output/logs/music MP3s
- Rewrote README.md and CLAUDE.md for FactsFactory
- Created scaffold modules for research + production pipeline
- Git initialized, pushed to GitHub

**Files changed:** Full repository bootstrap
