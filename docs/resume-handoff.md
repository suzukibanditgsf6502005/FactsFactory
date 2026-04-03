# Resume Handoff

> This is the MOST IMPORTANT doc for session continuity.
> Read this first when starting a new session. Update it before ending any session.
> Another AI must be able to resume work from this file alone.

---

## System State — 2026-04-03 (text spine validated)

### Completed

| Item | Detail |
|---|---|
| Bootstrap | FactsFactory created from sanitized PawFactory snapshot (commit ea76e33) |
| GitHub repo | Created and pushed at github.com/suzukibanditgsf6502005/FactsFactory |
| Architecture pivot | Docs, CLAUDE.md, README renamed and pivoted to FactsFactory / facts shorts |
| Inherited modules | voiceover, music_mixer, video_editor, ass_captions, quality_check, metadata_gen, publish_queue, youtube_uploader, tiktok_publisher — all functional from PawFactory |
| Legacy modules | reddit_scraper, downloader, hook_generator, smart_clipper, visual_sampler, run_pipeline — preserved, marked as LEGACY |
| topic_selector.py | v1 — Claude Haiku, 5 candidates, scored, top pick returned as JSON |
| fact_research.py | v1 — Claude Sonnet, 8–10 facts ordered by impact, strict JSON |
| script_generator.py | v1 — Claude Sonnet, hook + narration + CTA + 4 title variants, ~35s target |
| storyboard_generator.py | v1 — Claude Haiku, 7–9 scenes with image prompts + motion hints |
| run_spine.py | v1 — orchestrator: full chain or resume from any stage, --dry-run mode |
| Validation pass | 10 runs (6 pre-fix, 4 post-fix): critical issues found and fixed |
| topic_selector.py | v2 — category descriptions added; random top-3 pick for diversity |
| script_generator.py | v2 — hard word count limit enforced; cleaner system prompt |
| weird_biology category | Added to all modules; produces correct disturbing/parasite content |
| Validation summary | logs/validation/spine_validation_20260403.md |

### In Progress

Waiting for human decision on image generation provider.

### What Remains (ordered priority)

1. **Human: choose image generation provider** (see cost breakdown in current-task.md)
   - Recommendation: Flux via fal.ai (~$0.003–0.008/image, ~$0.024–0.064/short)
2. **Fix storyboard image prompts** — add visual creature descriptions alongside Latin names
3. **Implement `scene_image_generator.py`** — once provider chosen
4. **Fix repeated closing phrases** — "Biology is darker than horror fiction" used twice in weird_biology
5. **Implement `scene_animator.py`** — Ken Burns via ffmpeg zoompan
6. **Adapt `video_editor.py`** — accept animated scene sequence + voiceover
7. **End-to-end media test** — topic → stills → voice → video → QC → queue
8. **YouTube OAuth2 setup** — `python scripts/publishing/youtube_uploader.py --auth`

### Blockers

None for text spine. Image generation blocked on human provider decision.

---

## Exact Next Action

**If implementing image generation (once provider chosen):**
```bash
cd /home/ai-machine/source/FactsFactory
source venv/bin/activate

# Generate fresh content for image testing
python scripts/run_spine.py --category animal_facts
# Then implement scene_image_generator.py for that storyboard
```

**If running more content for the text spine:**
```bash
source venv/bin/activate
python scripts/run_spine.py --category animal_facts
python scripts/run_spine.py --category weird_biology

# Inspect scripts quickly
for f in logs/scripts/*.json; do python3 -c "
import json; d=json.load(open('$f'))
print(d['topic'][:60], '|', d['word_count'], 'w', d['estimated_duration_seconds'], 's')
print('HOOK:', d['hook'][:80])
"; done
```

**Validation summary:**
```
logs/validation/spine_validation_20260403.md
```

---

## Repository Layout (key files)

```
scripts/
  research/
    topic_selector.py       — SCAFFOLD: Claude Haiku topic picker
    fact_research.py        — SCAFFOLD: Claude Sonnet fact gatherer
  production/
    script_generator.py     — SCAFFOLD: Claude Sonnet script writer
    storyboard_generator.py — SCAFFOLD: scene breakdown
    scene_image_generator.py — SCAFFOLD: AI still image generator
    scene_animator.py       — SCAFFOLD: Ken Burns animator
    voiceover.py            — FUNCTIONAL: ElevenLabs TTS (voice: Lily)
    music_mixer.py          — FUNCTIONAL: 7-category track selection
    video_editor.py         — FUNCTIONAL: ffmpeg assembly
    ass_captions.py         — FUNCTIONAL: 4-tier ASS captions (v3.1.1)
    quality_check.py        — FUNCTIONAL: Claude Vision QC (v2)
    hook_generator.py       — LEGACY: PawFactory hook gen
    smart_clipper.py        — LEGACY: PawFactory clip selector
    visual_sampler.py       — LEGACY: PawFactory visual grounding
  publishing/
    metadata_gen.py         — FUNCTIONAL: YouTube metadata
    publish_queue.py        — FUNCTIONAL: review queue
    youtube_uploader.py     — FUNCTIONAL: YouTube Data API v3 (needs OAuth2)
    tiktok_publisher.py     — FUNCTIONAL: TikTok API (app review pending)
  sourcing/
    reddit_scraper.py       — LEGACY: PawFactory scraper (not FactsFactory core)
    downloader.py           — LEGACY: PawFactory downloader
  run_pipeline.py           — LEGACY: PawFactory orchestrator

logs/                       — gitignored
inbox/                      — gitignored
output/                     — gitignored
assets/music/               — catalog.json + category folders (mp3s gitignored)
assets/fonts/               — Anton-Regular.ttf
docs/                       — full documentation
shorts/log.md               — permanent record of all produced content
```

---

## Key Configuration (from .env — never read aloud)

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API — script gen, QC, captions |
| `ELEVENLABS_API_KEY` | ElevenLabs TTS |
| `ELEVENLABS_VOICE_ID` | Currently: `pFZP5JQG7iQjIQuC4Bku` (Lily) |
| `SUBMAGIC_API_KEY` | Submagic captions (optional — ASS fallback if missing) |
| `YOUTUBE_CLIENT_SECRETS` | Path to OAuth2 JSON from Google Cloud Console |

---

## Decisions Already Made (do not re-debate)

| Decision | Rationale |
|---|---|
| Script-first, no scraping as core path | FactsFactory pivot: AI-generated content, not scraped footage |
| English-first | Broadest audience; no translation complexity |
| Inherited PawFactory production modules | Already validated; don't rewrite what works |
| Legacy sourcing modules preserved (not deleted) | May be useful for supplemental use; not worth deleting |
| Music MP3s excluded from git | Licensed tracks (Epidemic Sound); 176MB; not safe to commit |
| Image generation provider: TBD | Requires human approval of provider + cost model |
| Voice: Lily (inherited) | Already validated for emotional delivery |

---

## PawFactory Origin Notes

FactsFactory was bootstrapped from PawFactory commit `ea76e33` (2026-04-02).
PawFactory is at `/home/ai-machine/source/PawFactory` — treat as read-only reference.
Do not modify PawFactory.
