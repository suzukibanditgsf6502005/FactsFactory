# Current Task

> Last updated: 2026-04-03
> This file describes what is being worked on right now and what comes next.
> Update this file at the start and end of every session.

---

## Current Objective

**Phase:** Text spine validated — 10 runs across animal_facts + weird_biology; critical issues fixed; spine ready for image generation.

**Immediate goal:** Choose image generation provider (Flux/DALL-E 3/Ideogram) and implement `scene_image_generator.py`.

---

## What Is Being Worked On RIGHT NOW

Nothing active. Validation complete. Waiting for human decision on image generation provider.

---

## Active System State

| Component | Version | Status |
|---|---|---|
| topic_selector.py | v2 | ✅ validated — diversity fix, category descriptions |
| fact_research.py | v1 | ✅ validated — facts accurate, well-structured |
| script_generator.py | v2 | ✅ validated — hooks strong, duration mostly on target |
| storyboard_generator.py | v1 | ✅ validated — 7–9 scenes, image prompts usable |
| scene_image_generator.py | scaffold | ⚠️ scaffold only — not functional |
| scene_animator.py | scaffold | ⚠️ scaffold only — not functional |
| voiceover.py | inherited | ✅ functional (from PawFactory) |
| music_mixer.py | inherited | ✅ functional (from PawFactory) |
| video_editor.py | inherited | ✅ functional (from PawFactory) |
| ass_captions.py | v3.1.1 inherited | ✅ functional (from PawFactory) |
| quality_check.py | v2 inherited | ✅ functional (from PawFactory) |
| metadata_gen.py | inherited | ✅ functional (from PawFactory) |
| publish_queue.py | inherited | ✅ functional (from PawFactory) |
| youtube_uploader.py | inherited | ✅ built — needs OAuth2 credentials |
| reddit_scraper.py | LEGACY | ⚠️ functional but not core FactsFactory path |
| downloader.py | LEGACY | ⚠️ functional but not core FactsFactory path |

---

## Constraints

- Do NOT upload to any platform without human approval
- Do NOT spend > $5 API credits in a single session
- All pipeline steps must be idempotent (re-running is always safe)
- Never commit `.env`, `inbox/`, `output/`, `logs/`, music MP3s

---

## Next Steps (in order)

1. **Human: choose image generation provider:**
   - Flux via fal.ai: ~$0.003–0.008/image, fast, good quality, 8 images/short = ~$0.024–0.064
   - DALL-E 3: ~$0.040/image, 8 images/short = ~$0.32 — higher cost, strong prompt adherence
   - Ideogram: ~$0.08/image, strong text rendering (not needed for facts), 8 images/short = ~$0.64
   - **Recommendation: Flux via fal.ai** — best cost/quality for photorealistic animal imagery
2. **Fix storyboard image prompt quality** — add visual descriptions of organisms alongside Latin names
3. **Implement `scene_image_generator.py`** — once provider approved
4. **Fix repeated closing phrases** — "Biology is darker than horror fiction" used twice; add variation
5. **Implement `scene_animator.py`** — Ken Burns via ffmpeg zoompan
6. **Adapt `video_editor.py`** — accept animated scene sequence + voiceover → assembled short
7. **End-to-end media test** — topic → stills → voice → video → QC → queue
