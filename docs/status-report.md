# FactsFactory Status Report

> Last updated: 2026-04-03
> For session continuity, read `docs/resume-handoff.md` first.

---

## Current State — 2026-04-03

- **Phase:** Bootstrap complete
- **Shorts produced:** 0 (pipeline not yet end-to-end)
- **Pipeline status:** Inherited production modules functional; new research/script modules scaffolded only
- **Publishing system:** Inherited from PawFactory — awaiting credential configuration

---

## Module Status

### New FactsFactory Modules (scaffold — not yet functional)

| Module | Status | Notes |
|---|---|---|
| `scripts/research/topic_selector.py` | SCAFFOLD | Interface documented; Claude Haiku call not yet wired |
| `scripts/research/fact_research.py` | SCAFFOLD | Interface documented; Claude Sonnet call not yet wired |
| `scripts/production/script_generator.py` | SCAFFOLD | Interface documented; not yet wired |
| `scripts/production/storyboard_generator.py` | SCAFFOLD | Interface documented; not yet wired |
| `scripts/production/scene_image_generator.py` | SCAFFOLD | Provider TBD; not yet wired |
| `scripts/production/scene_animator.py` | SCAFFOLD | ffmpeg Ken Burns approach documented; not yet wired |

### Inherited Functional Modules

| Module | Status | Notes |
|---|---|---|
| `voiceover.py` | ✅ functional | ElevenLabs, voice Lily — inherited from PawFactory |
| `music_mixer.py` | ✅ functional | 7 categories, 36-track catalog — inherited |
| `video_editor.py` | ✅ functional | ffmpeg crop/mux/captions/trim — inherited |
| `ass_captions.py` | ✅ functional | v3.1.1, 4-tier emphasis — inherited |
| `quality_check.py` | ✅ functional | v2, Claude Vision QC — inherited |
| `metadata_gen.py` | ✅ functional | YouTube metadata gen — inherited |
| `publish_queue.py` | ✅ functional | Review queue — inherited |
| `youtube_uploader.py` | ✅ built | Needs OAuth2 credentials — inherited |
| `tiktok_publisher.py` | ✅ built | App review pending — inherited |

### Legacy Modules (from PawFactory — functional but not FactsFactory core path)

| Module | Status | Notes |
|---|---|---|
| `reddit_scraper.py` | LEGACY | PawFactory footage sourcing |
| `downloader.py` | LEGACY | yt-dlp downloader |
| `hook_generator.py` | LEGACY | PawFactory hook gen — reference for script_generator |
| `smart_clipper.py` | LEGACY | PawFactory clip selector |
| `visual_sampler.py` | LEGACY | PawFactory visual grounding |
| `run_pipeline.py` | LEGACY | PawFactory orchestrator |

---

## Architecture Decisions

| Decision | Detail |
|---|---|
| Script-first, no scraping | FactsFactory core pivot: AI generates all content |
| English-first | All content in English; no localization complexity |
| Inherited production modules | voiceover, captions, music, QC, publishing — proven in PawFactory |
| Music MP3s not in git | Licensed tracks (Epidemic Sound, 176MB) — gitignored |
| Image gen provider | TBD — requires human approval before integration |
| Voice: Lily (inherited) | `pFZP5JQG7iQjIQuC4Bku`, ElevenLabs — validated |
| Font: Anton-Regular | High-contrast, bold caption font — inherited |

---

## Next Steps

1. Implement `topic_selector.py` (Claude Haiku)
2. Implement `fact_research.py` (Claude Sonnet)
3. Implement `script_generator.py` (Claude Sonnet)
4. Implement `storyboard_generator.py` (Claude Haiku)
5. Choose image generation provider — present options to human with cost comparison
6. Implement `scene_image_generator.py` once provider approved
7. End-to-end pipeline test

---

## API Tests — 2026-04-03 (inherited from PawFactory, not yet re-validated in FactsFactory)

| Service | Status | Notes |
|---|---|---|
| Anthropic API | ✅ (inherited) | Keys carried in .env — not yet re-tested in FactsFactory |
| ElevenLabs API | ✅ (inherited) | Voice: Lily — not yet re-tested |
| YouTube Data API | ✅ built | Needs OAuth2 credentials configured |
| TikTok API | ✅ built | App review pending |
