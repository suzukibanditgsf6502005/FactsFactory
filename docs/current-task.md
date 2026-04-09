# Current Task

> Last updated: 2026-04-09
> This file describes what is being worked on right now and what comes next.
> Update this file at the start and end of every session.

---

## Current Objective

**Phase:** 2-phase pipeline implemented. All docs updated to reflect current architecture.

**System is ready for production batch runs.**

---

## What Is Being Worked On RIGHT NOW

Nothing active. Ready for validation batch.

---

## Active System State

| Component | Version | Status |
|---|---|---|
| topic_selector.py | v2 | ✅ validated |
| fact_research.py | v1 | ✅ validated |
| script_generator.py | v2 | ✅ validated |
| storyboard_generator.py | v2 | ✅ infographic/comic prompts + structured fields |
| scene_generators/base.py | v1 | ✅ abstract base |
| scene_generators/motion.py | v1 | ⚠️ DISABLED — on disk, unreachable from pipeline |
| scene_generators/cartoon.py | v2 | ✅ infographic path + legacy fallback |
| scene_generators/cinematic.py | v2 | ✅ hybrid Veo ingest + fallback |
| scene_generators/__init__.py | v2 | ✅ STYLES = [cinematic, cartoon] |
| main.py | v4 | ✅ 2-phase: --spine-only, --render-only, full pipeline |
| scene_image_generator.py | v2 | ✅ _build_scene_prompt() |
| scene_animator.py | v1 | ✅ functional |
| assemble_video.py | v1 | ✅ functional |
| ass_captions.py | v3+ | ✅ functional |
| voiceover.py | inherited | ✅ functional (ElevenLabs, voice Lily) |
| music_mixer.py | inherited | ✅ functional |
| quality_check.py | v2 inherited | ✅ functional |
| metadata_gen.py | inherited | ✅ functional |
| publish_queue.py | inherited | ✅ functional |
| youtube_uploader.py | inherited | ✅ built — needs OAuth2 credentials |

---

## Constraints

- Do NOT upload to any platform without human approval
- Do NOT spend > $5 API credits in a single session
- All pipeline steps must be idempotent (re-running is always safe)
- Never commit `.env`, `inbox/`, `output/`, `logs/`, music MP3s

---

## Next Steps (in order)

1. **Run cartoon validation** — `python main.py --style cartoon --category weird_biology`
   - Evaluate infographic prompt quality vs. old single-subject frames
2. **Test 2-phase workflow**:
   - `python main.py --spine-only --category animal_facts`
   - Place 2–3 test Veo clips in the veo/ folder
   - `python main.py --render-only --style all --video-id <id> --script-file ... --storyboard-file ...`
3. **YouTube OAuth2 setup** — `python scripts/publishing/youtube_uploader.py --auth`
4. **Wire Runway API** — add RUNWAY_API_KEY for automatic Runway cinematic generation
5. **Wire Veo API** — when Google makes Veo publicly available via API
6. **Re-enable motion** — when style is ready to return to public pipeline
