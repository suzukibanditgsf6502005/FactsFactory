# Current Task

> Last updated: 2026-04-09
> This file describes what is being worked on right now and what comes next.
> Update this file at the start and end of every session.

---

## Current Objective

**Phase:** Hybrid cinematic pipeline implemented — manual Veo clips can be placed in `inbox/<video_id>_cinematic/veo/` and are automatically used in place of fallback generation. `--video-id` CLI flag added for ID reuse across runs.

**Immediate goal:** Run a cartoon validation batch (`--style cartoon`) to evaluate infographic prompt quality, then test hybrid cinematic by placing 2–3 Veo clips and re-running with `--video-id`.

---

## What Is Being Worked On RIGHT NOW

Nothing active. Hybrid cinematic pipeline + infographic cartoon pivot both complete.

---

## Active System State

| Component | Version | Status |
|---|---|---|
| topic_selector.py | v2 | ✅ validated |
| fact_research.py | v1 | ✅ validated |
| script_generator.py | v2 | ✅ validated |
| storyboard_generator.py | v2 | ✅ updated — infographic/comic prompts + structured fields |
| scene_generators/base.py | v1 | ✅ abstract base |
| scene_generators/motion.py | v1 | ⚠️ DISABLED — on disk, unreachable from pipeline |
| scene_generators/cartoon.py | v2 | ✅ updated — uses infographic path; legacy fallback for old storyboards |
| scene_generators/cinematic.py | v2 | ✅ updated — hybrid: manual Veo clips + AI fallback |
| main.py | v3 | ✅ updated — `--video-id` flag; motion removed from CLI |
| scene_image_generator.py | v2 | ✅ updated — _build_scene_prompt() replaces global suffix |
| scene_animator.py | v1 | ✅ functional (pan bug fixed) |
| assemble_video.py | v1 | ✅ functional |
| ass_captions.py | v3+ | ✅ functional (temp-file burn fix applied) |
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

1. **Run cartoon batch** — `python main.py --style cartoon --category weird_biology`
2. **Evaluate infographic prompt quality** — inspect outputs vs. old single-subject frames
3. **Test hybrid cinematic** — place 2–3 Veo clips in `inbox/<video_id>_cinematic/veo/`, re-run with `--video-id`
4. **YouTube OAuth2 setup** — `python scripts/publishing/youtube_uploader.py --auth`
5. **Wire Runway API** — add RUNWAY_API_KEY to .env for automatic Runway cinematic generation
6. **Wire Veo API** — when Google makes Veo publicly available via API
7. **Re-enable motion** — when motion style is ready to return to public pipeline
