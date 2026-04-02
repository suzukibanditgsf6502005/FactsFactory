# Current Task

> Last updated: 2026-04-03
> This file describes what is being worked on right now and what comes next.
> Update this file at the start and end of every session.

---

## Current Objective

**Phase:** Text spine implemented — all 4 research/script modules functional; orchestrator available.

**Immediate goal:** Run the full spine end-to-end with a real API key and validate output quality.
Then decide image generation provider to unblock `scene_image_generator.py`.

---

## What Is Being Worked On RIGHT NOW

Text spine implemented. Awaiting: (1) .env setup, (2) end-to-end live test.

---

## Active System State

| Component | Version | Status |
|---|---|---|
| topic_selector.py | v1 | ✅ functional — needs .env + live test |
| fact_research.py | v1 | ✅ functional — needs .env + live test |
| script_generator.py | v1 | ✅ functional — needs .env + live test |
| storyboard_generator.py | v1 | ✅ functional — needs .env + live test |
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

1. **Set up .env** — copy from PawFactory: `cp /home/ai-machine/source/PawFactory/.env .env`
2. **Live end-to-end test**:
   ```bash
   source venv/bin/activate
   python scripts/run_spine.py --category animal_facts --dry-run   # dry run first
   python scripts/run_spine.py --category animal_facts             # save artifacts
   ```
3. **Review outputs** — check topic, facts, script, storyboard quality; iterate prompts if needed
4. **Decide image generation provider** — options: DALL-E 3, Flux (fal.ai/Replicate), Ideogram
   (do not integrate until provider chosen and approved by human)
5. **Implement `scene_image_generator.py`** — once provider approved
6. **Wire voiceover + video_editor** to accept scene sequence input
7. **End-to-end media test** — topic → facts → script → stills → voice → video → QC → queue
