# Progress Log

> Append-only. Newest entries at the top.
> Format: ## YYYY-MM-DD — short title

---

## 2026-04-03 — Text spine validation pass: 10 runs, critical issues fixed

**What was done:**
- Copied .env from PawFactory; confirmed ANTHROPIC_API_KEY present
- Added `weird_biology` to CATEGORIES in topic_selector.py, run_spine.py, script_generator.py
- Ran 6 pre-fix batches (animal_facts × 5, weird_biology × 1) — identified critical issues
- Identified and fixed 3 issues:
  1. Topic diversity: selector was deterministic → always octopus (fixed: random top-3 pick)
  2. Category context: weird_biology produced animal_facts topics (fixed: CATEGORY_DESCRIPTIONS)
  3. Word count drift: 107–125w vs 96w target (fixed: HARD LIMIT instruction + max_words)
- Ran 4 post-fix validation runs (animal_facts × 2, weird_biology × 2)
- Post-fix quality: 3 distinct topics, 95–110 words, Shorts-native hooks, strong scripts
- Remaining minor issues documented: repeated closing phrase, storyboard duration gap, image prompt specificity
- Wrote validation summary: logs/validation/spine_validation_20260403.md
- Updated docs: current-task, resume-handoff, progress-log, status-report

**Files changed:**
- scripts/research/topic_selector.py (v1 → v2): category descriptions + random top-3
- scripts/production/script_generator.py (v1 → v2): hard word count limit + cleaner prompt
- scripts/run_spine.py: weird_biology added to CATEGORIES
- docs/current-task.md, docs/resume-handoff.md, docs/progress-log.md, docs/status-report.md
- logs/validation/spine_validation_20260403.md (new)

**Next step:** Human decides image generation provider; implement scene_image_generator.py

---

## 2026-04-03 — Text spine implemented: topic → research → script → storyboard

**What was done:**
- Implemented `scripts/research/topic_selector.py` (v1)
  - Model: claude-haiku-4-5-20251001
  - Generates 5 scored candidates, returns top pick
  - Output: logs/topics/TIMESTAMP_category.json
- Implemented `scripts/research/fact_research.py` (v1)
  - Model: claude-sonnet-4-6
  - 8–10 facts ordered by impact, strict JSON with validation
  - Output: logs/research/TIMESTAMP_slug.json
- Implemented `scripts/production/script_generator.py` (v1)
  - Model: claude-sonnet-4-6
  - hook + narration + CTA + 4 title_variants + emotional_angle
  - Word count recomputed from actual full_script for accuracy
  - Output: logs/scripts/TIMESTAMP_slug.json
- Implemented `scripts/production/storyboard_generator.py` (v1)
  - Model: claude-haiku-4-5-20251001
  - 7–9 scenes: scene_goal, narration_segment, visual_description, image_prompt, motion
  - Scene durations validated + auto-corrected
  - Output: logs/storyboards/TIMESTAMP_slug.json
- Created `scripts/run_spine.py` — orchestrator for the full chain
  - --dry-run: no files written, all output to stdout
  - --topic-file / --research-file / --script-file: resume from any stage
  - --target-duration: controls script length
- Created venv at FactsFactory/venv, installed anthropic + python-dotenv
- All CLIs verified with --help
- Updated docs: current-task, resume-handoff, progress-log

**Files changed:**
- scripts/research/topic_selector.py (scaffold → v1)
- scripts/research/fact_research.py (scaffold → v1)
- scripts/production/script_generator.py (scaffold → v1)
- scripts/production/storyboard_generator.py (scaffold → v1)
- scripts/run_spine.py (new)
- docs/current-task.md, docs/resume-handoff.md, docs/progress-log.md

**Blocker:** .env not copied to FactsFactory — live API test not yet run.

**Next step:** Copy .env, run `python scripts/run_spine.py --category animal_facts --dry-run`

---

## 2026-04-03 — Bootstrap: FactsFactory created from PawFactory

**What was done:**
- Created FactsFactory at `/home/ai-machine/source/FactsFactory`
- rsync from PawFactory (local, commit ea76e33) with exclusions:
  `.git`, `.env`, `venv/`, `inbox/`, `output/`, `logs/`, `__pycache__/`, `.pytest_cache/`,
  `.mypy_cache/`, `.ruff_cache/`, `.idea/`, `.vscode/`, `.claude/`, all music MP3s
- Assets preserved: `assets/music/catalog.json`, `assets/fonts/Anton-Regular.ttf`
- All scripts preserved: production, publishing, sourcing (legacy), tools
- `.gitignore` updated: added pytest/mypy/ruff caches, music MP3s
- README.md rewritten for FactsFactory: script-first, AI visuals, facts niche
- CLAUDE.md rewritten for FactsFactory: new pipeline flow, legacy module labeling
- docs/current-task.md: reset to FactsFactory bootstrap state
- docs/resume-handoff.md: full FactsFactory handoff document
- docs/progress-log.md: this file (created fresh)
- docs/status-report.md: reset for FactsFactory
- Scaffold modules created:
  - `scripts/research/topic_selector.py`
  - `scripts/research/fact_research.py`
  - `scripts/production/script_generator.py`
  - `scripts/production/storyboard_generator.py`
  - `scripts/production/scene_image_generator.py`
  - `scripts/production/scene_animator.py`
- Git initialized, initial commit pushed to GitHub

**Files modified:**
- README.md, CLAUDE.md, .gitignore
- docs/current-task.md, docs/resume-handoff.md, docs/progress-log.md, docs/status-report.md
- scripts/research/ (new directory + 2 scaffold files)
- scripts/production/script_generator.py, storyboard_generator.py, scene_image_generator.py, scene_animator.py (new scaffolds)

**What worked:** rsync clean copy, git init, GitHub repo creation via API

**Next step:** Implement topic_selector.py → fact_research.py → script_generator.py
