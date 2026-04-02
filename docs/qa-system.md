# QA System

> Documents the quality control system as of 2026-04-01.
> Code: `scripts/production/quality_check.py`

---

## Overview

QC is a multi-provider visual evaluation system. It extracts 5 frames from the finished Short
and evaluates them across 6 weighted dimensions using a pluggable AI provider (Claude or OpenAI).

**QC is not run automatically by the pipeline.** It must be triggered manually after `video_editor.py` completes:

```bash
# Auto-select provider (prefers Claude)
python scripts/production/quality_check.py --video-id "ID"

# Force a specific provider
python scripts/production/quality_check.py --video-id "ID" --provider openai
```

---

## Provider Architecture

### BaseQAProvider (ABC)

```python
class BaseQAProvider(ABC):
    @abstractmethod
    def evaluate(self, frame_paths: list[str], context: dict) -> dict:
        # Returns: scores, issues, recommendations, summary, raw_response
```

### ClaudeQAProvider

- Model: `claude-sonnet-4-6`
- API key: `ANTHROPIC_API_KEY`
- Prompt returns structured JSON (no regex parsing)
- Requires: `pip install anthropic`

### OpenAIQAProvider (optional)

- Model: `gpt-4o` (default) — overridable via `OPENAI_QA_MODEL` env var
- API key: `OPENAI_API_KEY`
- Same JSON prompt and response format as Claude provider
- Requires: `pip install openai` (already in requirements.txt) + `OPENAI_API_KEY` in `.env`
- `max_completion_tokens` used instead of `max_tokens` (required by gpt-5+ models)

**Model selection note:** `gpt-5.4` was tested on 2026-04-01 and found to be more lenient than `gpt-4o`.
It incorrectly passed the robot/wrong-niche video (31s88nkp) at 6.31, which `gpt-4o` correctly FAILed
at 5.59. `gpt-4o` remains the recommended OpenAI model for QC gating. To test `gpt-5.4`:
`OPENAI_QA_MODEL=gpt-5.4 python scripts/production/quality_check.py --video-id ID --provider openai`

### Auto-selection logic

```
preferred="claude" (or None)
  → ANTHROPIC_API_KEY present?  → ClaudeQAProvider
  → else OPENAI_API_KEY present? → OpenAIQAProvider (fallback, prints warning)
  → else → RuntimeError

preferred="openai"
  → OpenAIQAProvider (raises if key absent)
```

---

## Scoring System

### 6 Evaluation Dimensions

| Dimension | Weight | What it measures |
|---|---|---|
| `caption_readability` | 1.5 | Captions large, high-contrast, not covering subject |
| `hook_strength` | 1.4 | Frame 1 (0%) — tension, clear subject, scroll-stopping |
| `viral_potential` | 1.4 | Overall emotional pull, pacing, visual interest |
| `framing` | 1.2 | Main subject well-composed, not cut off |
| `visual_clarity` | 1.0 | Footage sharpness, lighting, no artifacts |
| `highlight_quality` | 0.7 | Caption styling consistency — NOT yellow-word frequency (transient, frame-unreliable) |

Each dimension scored 1–10 by the AI provider.

### Verdict Calculation

**Weighted average:**
```
weighted_score = Σ(score[dim] × weight[dim]) / Σ(weight[dim])
```

**Verdict rules (applied in order):**
1. **Hard fail:** any single dimension ≤ 3 → `FAIL` (even if weighted average ≥ 6.0)
2. **Pass:** weighted_score ≥ 6.0 → `PASS`
3. **Fail:** weighted_score < 6.0 → `FAIL`

Thresholds:
- `PASS_THRESHOLD = 6.0`
- `HARD_FAIL_THRESHOLD = 3`

---

## How It Works

### Step 1: Frame Extraction

```python
# Timestamps: 0%, 25%, 50%, 75%, 95% of video duration
percentages = [0.0, 0.25, 0.50, 0.75, 0.95]
```

Each frame extracted as JPEG (q:v=3, high quality) to `logs/frames/ID_frame_N.jpg`.

### Step 2: Context Loading

Reads `logs/hooks/ID.json` (if present) to supply the AI provider with:
- `title` — the generated Short title
- `script_excerpt` — first 300 chars of `full_script`

This context enables more precise hook_strength and viral_potential scoring.

### Step 3: Provider Evaluation

Provider receives: frame images + context dict.

Prompt requests structured JSON response:
```json
{
  "scores": {
    "caption_readability": 8,
    "hook_strength": 7,
    "framing": 9,
    "visual_clarity": 8,
    "highlight_quality": 6,
    "viral_potential": 7
  },
  "issues": ["Caption overlaps subject at 50% mark"],
  "recommendations": ["Raise MarginV by 20px to clear subject"],
  "summary": "Strong hook and framing; minor caption overlap in mid-video."
}
```

### Step 4: Verdict + Report

```
QC Report — 31qgcpec
  Verdict:        PASS
  Weighted score: 7.61 / 10.00  (pass ≥ 6.0)
  Provider:       claude

  Dimension scores:
  caption_readability    8 ████████░░  ×1.5
  hook_strength          7 ███████░░░  ×1.4
  framing                9 █████████░  ×1.2
  visual_clarity         8 ████████░░  ×1.0
  highlight_quality      6 ██████░░░░  ×1.0
  viral_potential        7 ███████░░░  ×1.4
```

### Step 5: Save Result

Output to `logs/qc/ID_qc.json`:
```json
{
  "video_id": "ID",
  "timestamp": "2026-04-01 14:32",
  "provider": "claude",
  "verdict": "PASS",
  "weighted_score": 7.61,
  "hard_fail_dim": null,
  "scores": { ... },
  "issues": [],
  "recommendations": [],
  "summary": "...",
  "frames_checked": 5,
  "raw_response": "..."
}
```

---

## What It Evaluates vs. What It Ignores

| Evaluates | Ignores |
|---|---|
| Caption readability, size, position | Raw script quality |
| Hook visual strength (frame 1) | Audio sync issues |
| Subject framing (9:16 composition) | Shaky footage (no motion analysis) |
| Visual clarity, lighting | Music selection |
| Caption highlight effectiveness | Source attribution |
| Overall viral potential | |

---

## Historical QC Results

### v1 Binary QC (pre-scoring)

| Video ID | Verdict | Notes |
|---|---|---|
| 31qgcpec | PASS | Elephant, clean framing |
| 31s85gwk | PASS | Turtles, clean |
| 31s88nkp | FAIL | Wrong niche (robot), source has burned-in text |
| 31s3wpyo | PASS | Whale shark, captions top |
| 31qkwmtd | PASS | Magpie |
| 31s0v018 | PASS | Flood cats |

### v2 Validation Run — 2026-04-01 (4 shorts, 2 providers)

**Claude provider (`claude-sonnet-4-6`):**

| Video ID | Verdict | Score | cr  | hk  | fr  | vc  | hi  | vp  | Hard fail dim |
|---|---|---|---|---|---|---|---|---|---|
| 31qgcpec | FAIL | 5.24 | 5 | 5 | 5 | 6 | 3 | 7 | — |
| 31s85gwk | FAIL | 5.92 | 6 | 6 | 6 | 7 | 3 | 7 | — |
| 31s3wpyo_v2¹ | FAIL | 4.63 | 5 | 5 | 4 | 5 | 2 | 6 | — |
| 31s88nkp | FAIL | 4.72 | 6 | 3 | 4 | 4 | 5 | 6 | hook_strength |

**OpenAI provider (`gpt-4o`):**

| Video ID | Verdict | Score | cr  | hk  | fr  | vc  | hi  | vp  |
|---|---|---|---|---|---|---|---|---|
| 31qgcpec | PASS | 7.55 | 8 | 7 | 8 | 7 | 7 | 8 |
| 31s85gwk | PASS | 8.55 | 9 | 8 | 9 | 8 | 8 | 9 |
| 31s3wpyo_v2¹ | PASS | 7.11 | 7 | 8 | 7 | 6 | 6 | 8 |
| 31s88nkp | FAIL | 5.59 | 5 | 7 | 6 | 5 | 4 | 6 |

*(cr=caption_readability, hk=hook_strength, fr=framing, vc=visual_clarity, hi=highlight_quality, vp=viral_potential)*

¹ `31s3wpyo_v2` is an ASS v3 caption test file, not the production Submagic-captioned version.

**Validation round 3 — gpt-5.4 comparison (2026-04-01):**

| Video ID | Claude | gpt-4o (old) | gpt-5.4 (new) | Ground truth |
|---|---|---|---|---|
| 31qgcpec | PASS 6.33 | PASS 7.55 | PASS 8.06 | PASS ✅ |
| 31s85gwk | PASS 7.39 | PASS 8.55 | PASS 8.69 | PASS ✅ |
| 31s3wpyo_v2 | PASS 6.22 | PASS 7.11 | PASS 7.56 | PASS ✅ |
| 31s88nkp | FAIL 5.40 | FAIL 5.59 | **PASS 6.31** | FAIL ✅/❌ |

`gpt-5.4` falsely passes the robot video. Agreement with ground truth: Claude 4/4, gpt-4o 4/4, gpt-5.4 3/4.

**gpt-5.4 characteristics vs gpt-4o:**
- More lenient: scores 0.4–0.5 points higher on average across all dimensions
- More specific issues/recommendations on animal shorts (marginally better feedback quality)
- But too lenient to gate reliably — misses the wrong-niche FAIL
- Uses `max_completion_tokens` instead of `max_tokens` (API breaking change for gpt-5+ models; fixed)

**Decision:** `gpt-4o` remains the default OpenAI model. `gpt-5.4` is NOT recommended for QC gating.
Override with `OPENAI_QA_MODEL=gpt-5.4` if you want to use it for feedback quality only (not gating).

---

**Validation round 1 (pre-refinement):** Claude FAILed all 4 shorts including known-good animal rescues. `highlight_quality` scored 2–3 ("no yellow visible") causing false hard-fails.

**Validation round 2 (post-refinement):** System prompt updated with ASS caption context; `highlight_quality` description reworded to clarify frame limitations; weight reduced 1.0→0.7. Results:
- Claude correctly PASSes all 3 animal rescue shorts (6.22–7.39) and FAILs the robot (5.26)
- Verdict agreement with ground truth: **4/4**
- `highlight_quality` Claude scores improved from 2–3 to 6–7 after prompt clarification

**Provider comparison (post-refinement):**
- Claude: animal shorts 6.22–7.39 (PASS), robot 5.26 (FAIL). Good separation, actionable specific feedback.
- OpenAI: animal shorts 7.11–8.55 (PASS), robot 5.59 (FAIL). More lenient; feedback generic but directionally correct.
- **Calibration status:** Thresholds appear correct after prompt refinement. Both providers agree on verdicts. Collect 10+ production runs before further threshold adjustment.

**Recommended workflow:**
- Use Claude as primary provider for actionable, specific feedback
- Run OpenAI as secondary only when a FAIL needs a second opinion before discarding content
- After 10+ production runs: review score distribution and adjust `PASS_THRESHOLD` only if clearly warranted

---

## Calibration Notes

### `highlight_quality` — hard-fail exempt + reduced weight + frame-aware prompt

Static frames rarely capture highlighted words because word highlights are transient (per-word, 200–600 ms each). Claude's original prompt interpreted absence of yellow in a frame as "highlight system broken."

**Fixes applied (2026-04-01):**
- `highlight_quality` added to `HARD_FAIL_EXEMPT` — cannot trigger a hard fail alone
- Weight reduced 1.0→0.7 — reduces drag when scored low, reflects frame-evaluation unreliability
- System prompt updated with explicit ASS caption context — Claude now understands transient highlights
- Dimension description reworded to judge caption styling consistency, not yellow-word frequency
- Result: Claude `highlight_quality` scores improved 2–3→6–7 on same videos; verdict improved FAIL→PASS

### Provider-specific thresholds (future work)

Claude and OpenAI score at very different scales (~2.4 point gap on animal content). Future improvement: per-provider threshold configuration (e.g., Claude threshold 5.5, OpenAI threshold 7.0).

### QC JSON single-file per video

`logs/qc/ID_qc.json` is overwritten on each run, regardless of provider. Running both providers sequentially on the same video loses the first result. Known limitation — not yet fixed.

---

## Adding OpenAI Provider

1. Add `OPENAI_API_KEY=sk-...` to `.env`
2. `openai` is already in `requirements.txt` — install with: `pip install openai`
3. Run: `python scripts/production/quality_check.py --video-id "ID" --provider openai`

No code changes needed — `OpenAIQAProvider` is already implemented.

**When to use OpenAI:** As a second opinion on borderline Claude FAILs. OpenAI is more lenient but may catch issues Claude misses in certain contexts (bright/saturated footage, heavy text overlays).

---

## Limitations

| Limitation | Impact |
|---|---|
| No audio analysis | Can't catch voiceover sync issues |
| No motion analysis | Can't catch shaky footage |
| 5 frames only | May miss transient issues (e.g., a 1s caption overlap) |
| `highlight_quality` unreliable for static frames | Fixed: exempt from hard-fail; still in weighted score |
| Provider JSON parse failure | Falls back to 5/10 across all dimensions (neutral) |
| JSON overwritten per run | Running both providers loses first result |
| Not integrated into pipeline | Manual step — easy to forget |
| Thresholds not yet calibrated | Need 10+ runs before adjusting PASS_THRESHOLD |

---

## File Locations

| File | Path |
|---|---|
| QC script | `scripts/production/quality_check.py` |
| QC results | `logs/qc/ID_qc.json` |
| Frame images | `logs/frames/ID_frame_N.jpg` |
