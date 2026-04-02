# Resume Handoff

> This is the MOST IMPORTANT doc for session continuity.
> Read this first when starting a new session. Update it before ending any session.
> Another AI must be able to resume work from this file alone.

---

## System State — 2026-04-03 (bootstrap)

### Completed

| Item | Detail |
|---|---|
| Bootstrap | FactsFactory created from sanitized PawFactory snapshot (commit ea76e33) |
| GitHub repo | Created and pushed at github.com/suzukibanditgsf6502005/FactsFactory |
| Architecture pivot | Docs, CLAUDE.md, README renamed and pivoted to FactsFactory / facts shorts |
| Inherited modules | voiceover, music_mixer, video_editor, ass_captions, quality_check, metadata_gen, publish_queue, youtube_uploader, tiktok_publisher — all functional from PawFactory |
| Legacy modules | reddit_scraper, downloader, hook_generator, smart_clipper, visual_sampler, run_pipeline — preserved, marked as LEGACY, not core FactsFactory path |
| Scaffold modules | topic_selector, fact_research, script_generator, storyboard_generator, scene_image_generator, scene_animator — created with documented responsibilities |
| .gitignore | Updated: music MP3s excluded, pytest/mypy/ruff caches excluded |
| Docs | current-task, resume-handoff, progress-log, status-report all updated for FactsFactory |

### In Progress

Nothing actively in progress. Bootstrap complete.

### What Remains (ordered priority)

1. **Implement `topic_selector.py`** — Claude Haiku: category → top topic pick with rationale
2. **Implement `fact_research.py`** — Claude Sonnet: topic → 8–12 verified facts, ordered by impact
3. **Implement `script_generator.py`** — Claude Sonnet: facts → full narration script (hook + body + CTA)
4. **Implement `storyboard_generator.py`** — script → scene breakdown with image prompts
5. **Decide and integrate image generation provider** (pending human approval of provider + cost)
6. **Implement `scene_image_generator.py`** — generate stills per scene
7. **Implement `scene_animator.py`** — Ken Burns motion on stills
8. **Adapt `video_editor.py`** — accept scene sequence instead of single-clip input
9. **End-to-end test** — topic → facts → script → voice → video → QC → queue
10. **YouTube OAuth2 setup** — `python scripts/publishing/youtube_uploader.py --auth`

### Blockers

None. Bootstrap complete. Next session can start implementation.

---

## Exact Next Action

```bash
cd /home/ai-machine/source/FactsFactory
source venv/bin/activate

# Implement topic_selector.py
# See scripts/research/topic_selector.py — scaffold has documented interface
# Then implement fact_research.py using the same pattern
```

Or if continuing publishing setup (YouTube OAuth2):
```bash
python scripts/publishing/youtube_uploader.py --auth
python scripts/publishing/publish_queue.py --list
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
