# Current Task

> Last updated: 2026-04-03
> This file describes what is being worked on right now and what comes next.
> Update this file at the start and end of every session.

---

## Current Objective

**Phase:** Bootstrap — repo created, architecture pivoted from PawFactory, scaffold modules in place.

**Immediate goal:** Implement `scripts/research/topic_selector.py` and `scripts/research/fact_research.py`
to create a working topic → facts pipeline. Then wire `scripts/production/script_generator.py`
to produce full narration scripts from researched facts.

---

## What Is Being Worked On RIGHT NOW

Bootstrap complete. Awaiting next implementation session.

---

## Active System State

| Component | Version | Status |
|---|---|---|
| topic_selector.py | scaffold | ⚠️ scaffold only — not functional |
| fact_research.py | scaffold | ⚠️ scaffold only — not functional |
| script_generator.py | scaffold | ⚠️ scaffold only — not functional |
| storyboard_generator.py | scaffold | ⚠️ scaffold only — not functional |
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

1. **Implement `topic_selector.py`** — Claude Haiku selects 5 candidate topics from a category,
   scores them by estimated engagement, returns top pick with rationale
2. **Implement `fact_research.py`** — Claude Sonnet researches 8–12 verified facts for the selected topic,
   structured in order of surprise/impact
3. **Implement `script_generator.py`** — Claude Sonnet writes full hook + body + CTA narration script
   (30–55 second target) grounded in fact_research output
4. **Implement `storyboard_generator.py`** — Claude breaks script into scenes with image prompts
5. **Decide image generation provider** — options: DALL-E 3, Stable Diffusion, Flux, Ideogram
   (do not integrate until provider is chosen and approved by human)
6. Wire voiceover + video_editor to accept scene-based input (rather than single-clip input)
7. End-to-end test: topic → script → voice → video → QC → queue
