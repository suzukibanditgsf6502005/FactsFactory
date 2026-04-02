# Resume Handoff

> This is the MOST IMPORTANT doc for session continuity.
> Read this first when starting a new session. Update it before ending any session.
> Another AI must be able to resume work from this file alone.

---

## System State — 2026-04-03 (text spine implemented)

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
| JSON contracts | All 4 modules have documented input/output schemas |
| CLIs | All 4 modules have working argparse CLIs |
| venv | Created at FactsFactory/venv with anthropic + python-dotenv |

### In Progress

.env not yet set up in FactsFactory. Live API test not yet run.

### What Remains (ordered priority)

1. **Set up .env** — `cp /home/ai-machine/source/PawFactory/.env .env`
2. **Live end-to-end test** — `python scripts/run_spine.py --category animal_facts --dry-run`
3. **Review + iterate prompts** — check topic/fact/script/storyboard quality after first live run
4. **Decide image generation provider** — present options to human (DALL-E 3, Flux, Ideogram)
5. **Implement `scene_image_generator.py`** — once provider approved
6. **Implement `scene_animator.py`** — Ken Burns via ffmpeg zoompan (documented in scaffold)
7. **Adapt `video_editor.py`** — accept animated scene sequence instead of single-clip input
8. **End-to-end media test** — topic → stills → voice → video → QC → queue
9. **YouTube OAuth2 setup** — `python scripts/publishing/youtube_uploader.py --auth`

### Blockers

`.env` not copied to FactsFactory. All text modules are ready; API cannot be called until .env exists.

---

## Exact Next Action

```bash
cd /home/ai-machine/source/FactsFactory

# 1. Set up environment
cp /home/ai-machine/source/PawFactory/.env .env
source venv/bin/activate

# 2. Dry run first (no API calls to image gen; text spine only)
python scripts/run_spine.py --category animal_facts --dry-run

# 3. Full run (saves artifacts to logs/)
python scripts/run_spine.py --category animal_facts

# 4. Inspect outputs
cat logs/topics/*.json | python3 -m json.tool | head -30
cat logs/scripts/*.json | python3 -m json.tool | grep -A3 '"hook"'
cat logs/storyboards/*.json | python3 -m json.tool | grep '"narration_segment"'

# 5. Re-run from a saved stage (skip re-generating if happy with topic/research)
python scripts/run_spine.py --research-file logs/research/TIMESTAMP_slug.json
python scripts/run_spine.py --script-file logs/scripts/TIMESTAMP_slug.json
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
