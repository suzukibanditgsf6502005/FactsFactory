# Progress Log

> Append-only. Newest entries at the top.
> Format: ## YYYY-MM-DD — short title

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
