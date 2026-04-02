#!/usr/bin/env python3
"""
quality_check.py — PawFactory multi-provider visual QC
Extracts 5 frames from a finished Short and evaluates them across 6 dimensions.

Usage:
  python scripts/production/quality_check.py --video-id "31qgcpec"
  python scripts/production/quality_check.py --video-id "31qgcpec" --provider openai
"""

import argparse
import base64
import importlib
import json
import os
import re
import subprocess
import sys
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
console = Console()

# ---------------------------------------------------------------------------
# Scoring configuration
# ---------------------------------------------------------------------------

SCORE_WEIGHTS = {
    "caption_readability": 1.5,
    "hook_strength":       1.4,
    "framing":             1.2,
    "visual_clarity":      1.0,
    "highlight_quality":   0.7,   # reduced: transient per-word highlights are rarely
                                  # visible in static frames — unreliable to judge this way
    "viral_potential":     1.4,
}

PASS_THRESHOLD       = 6.0   # weighted average ≥ 6.0 → PASS
HARD_FAIL_THRESHOLD  = 3     # any dimension ≤ 3 → automatic FAIL regardless of average

# Dimensions exempt from hard-fail triggering.
# highlight_quality is excluded because static frames rarely capture the exact
# moment a word is highlighted — a single unhighlighted frame cannot reliably
# indicate that the highlight feature is broken or absent. It still contributes
# to the weighted score.
HARD_FAIL_EXEMPT = frozenset({"highlight_quality"})

SCORE_DIMENSIONS = list(SCORE_WEIGHTS.keys())

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a senior QC reviewer for YouTube Shorts in the animal rescue niche. "
    "You evaluate short-form vertical video frames with precision and consistency. "
    "Always respond with valid JSON only — no prose, no markdown fences.\n\n"
    "Caption system context: this pipeline uses ASS word-by-word captions. "
    "Each word appears individually, timed to speech, with some words shown in yellow "
    "at larger scale for emphasis. Yellow highlights are transient — they are visible "
    "only during that specific word's display window (typically 0.2–0.6 seconds). "
    "It is completely normal and expected that most static frames will NOT show a "
    "yellow word. Do NOT interpret absence of yellow in a static frame as a caption "
    "system failure. Judge highlight_quality on overall caption appearance, consistency, "
    "and whether the styling looks intentional — not on whether yellow is currently visible."
)

USER_PROMPT_TEMPLATE = """Evaluate these {n} frames from a YouTube Short ({video_id}).
Context: {context}

Score each dimension 1–10. A score of 1 is catastrophic failure, 10 is perfect.

Dimensions to score:
- caption_readability: Are captions large, high-contrast, readable, not covering subject?
- hook_strength: Does frame 1 (0%) look like a strong hook — action, tension, clear subject?
- framing: Is the main subject well-framed, not cut off, good 9:16 composition?
- visual_clarity: Is the footage sharp, well-lit, without distracting artifacts?
- highlight_quality: Does the caption styling look intentional and effective — consistent size, readable font, clear contrast? Do not penalise for absence of yellow in a frame; per-word highlights are transient and rarely caught in still images. Only score low if captions look broken, misaligned, or completely unstyled.
- viral_potential: Overall short-form virality — emotional pull, pacing, visual interest?

Respond with ONLY this JSON structure:
{{
  "scores": {{
    "caption_readability": <1-10>,
    "hook_strength": <1-10>,
    "framing": <1-10>,
    "visual_clarity": <1-10>,
    "highlight_quality": <1-10>,
    "viral_potential": <1-10>
  }},
  "issues": ["<concise issue 1>", "<concise issue 2>"],
  "recommendations": ["<actionable fix 1>", "<actionable fix 2>"],
  "summary": "<one sentence overall assessment>"
}}

If there are no issues or recommendations, use empty arrays [].
Frame labels: {frame_labels}"""


# ---------------------------------------------------------------------------
# Provider base class
# ---------------------------------------------------------------------------

class BaseQAProvider(ABC):
    """Abstract base — any QA provider must implement evaluate()."""

    @abstractmethod
    def evaluate(self, frame_paths: list[str], context: dict) -> dict:
        """
        Evaluate video frames.

        Args:
            frame_paths: Ordered list of JPEG frame file paths (typically 5).
            context: Dict with keys: video_id, title, script_excerpt.

        Returns:
            Dict with keys: scores (dict), issues (list), recommendations (list),
            summary (str), raw_response (str).
        """

    def _encode_image(self, path: str) -> str:
        with open(path, "rb") as f:
            return base64.standard_b64encode(f.read()).decode("utf-8")

    def _parse_json_response(self, raw: str) -> dict:
        """Strip markdown fences if present, parse JSON."""
        text = raw.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text)

    def _validate_scores(self, scores: dict) -> dict:
        """Ensure all dimensions present and clamped to 1–10."""
        out = {}
        for dim in SCORE_DIMENSIONS:
            val = scores.get(dim, 5)
            try:
                out[dim] = max(1, min(10, int(val)))
            except (TypeError, ValueError):
                out[dim] = 5
        return out


# ---------------------------------------------------------------------------
# Claude provider
# ---------------------------------------------------------------------------

class ClaudeQAProvider(BaseQAProvider):
    MODEL = "claude-sonnet-4-6"
    MAX_TOKENS = 1024

    def __init__(self):
        import anthropic
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY missing")
        self.client = anthropic.Anthropic(api_key=api_key)

    def evaluate(self, frame_paths: list[str], context: dict) -> dict:
        video_id = context.get("video_id", "unknown")
        title    = context.get("title", "")
        script   = context.get("script_excerpt", "")
        ctx_str  = f'Title: "{title}"' + (f" | Script: {script[:120]}…" if script else "")

        frame_labels = ["0%", "25%", "50%", "75%", "95%"][: len(frame_paths)]

        prompt = USER_PROMPT_TEMPLATE.format(
            n=len(frame_paths),
            video_id=video_id,
            context=ctx_str,
            frame_labels=", ".join(frame_labels),
        )

        content = [{"type": "text", "text": prompt}]
        for i, fp in enumerate(frame_paths):
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": self._encode_image(fp),
                },
            })
            content.append({"type": "text", "text": f"Frame {i+1} ({frame_labels[i]})"})

        message = self.client.messages.create(
            model=self.MODEL,
            max_tokens=self.MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
        raw = message.content[0].text.strip()

        try:
            parsed = self._parse_json_response(raw)
        except (json.JSONDecodeError, ValueError):
            # Fallback: return neutral scores with the raw text as summary
            return {
                "scores": {d: 5 for d in SCORE_DIMENSIONS},
                "issues": ["Could not parse provider response"],
                "recommendations": ["Inspect raw_response manually"],
                "summary": "Parse error — manual review required",
                "raw_response": raw,
            }

        return {
            "scores":          self._validate_scores(parsed.get("scores", {})),
            "issues":          parsed.get("issues", []),
            "recommendations": parsed.get("recommendations", []),
            "summary":         parsed.get("summary", ""),
            "raw_response":    raw,
        }


# ---------------------------------------------------------------------------
# OpenAI provider (optional)
# ---------------------------------------------------------------------------

class OpenAIQAProvider(BaseQAProvider):
    # Default model. Override with env var OPENAI_QA_MODEL if needed.
    # gpt-5.4 was tested on 2026-04-01 and found to be more lenient than gpt-4o —
    # it incorrectly passed the robot video (wrong niche). Reverted to gpt-4o.
    MODEL = os.getenv("OPENAI_QA_MODEL", "gpt-4o")
    MAX_TOKENS = 1024

    def __init__(self):
        try:
            import openai
        except ImportError:
            raise RuntimeError("openai package not installed — run: pip install openai")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY missing")
        self.openai = openai
        self.client = openai.OpenAI(api_key=api_key)

    def evaluate(self, frame_paths: list[str], context: dict) -> dict:
        video_id = context.get("video_id", "unknown")
        title    = context.get("title", "")
        script   = context.get("script_excerpt", "")
        ctx_str  = f'Title: "{title}"' + (f" | Script: {script[:120]}…" if script else "")

        frame_labels = ["0%", "25%", "50%", "75%", "95%"][: len(frame_paths)]

        prompt = USER_PROMPT_TEMPLATE.format(
            n=len(frame_paths),
            video_id=video_id,
            context=ctx_str,
            frame_labels=", ".join(frame_labels),
        )

        messages_content = [{"type": "text", "text": prompt}]
        for i, fp in enumerate(frame_paths):
            messages_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{self._encode_image(fp)}",
                    "detail": "low",
                },
            })
            messages_content.append({"type": "text", "text": f"Frame {i+1} ({frame_labels[i]})"})

        response = self.client.chat.completions.create(
            model=self.MODEL,
            max_completion_tokens=self.MAX_TOKENS,  # gpt-5+ uses max_completion_tokens
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": messages_content},
            ],
        )
        raw = response.choices[0].message.content.strip()

        try:
            parsed = self._parse_json_response(raw)
        except (json.JSONDecodeError, ValueError):
            return {
                "scores": {d: 5 for d in SCORE_DIMENSIONS},
                "issues": ["Could not parse provider response"],
                "recommendations": ["Inspect raw_response manually"],
                "summary": "Parse error — manual review required",
                "raw_response": raw,
            }

        return {
            "scores":          self._validate_scores(parsed.get("scores", {})),
            "issues":          parsed.get("issues", []),
            "recommendations": parsed.get("recommendations", []),
            "summary":         parsed.get("summary", ""),
            "raw_response":    raw,
        }


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------

def _auto_select_provider(preferred: str | None = None) -> BaseQAProvider:
    """Return the best available provider. Claude is preferred."""
    if preferred == "openai":
        return OpenAIQAProvider()
    if preferred == "claude" or preferred is None:
        if os.getenv("ANTHROPIC_API_KEY"):
            return ClaudeQAProvider()
        # Fallback to OpenAI if Claude key absent
        if os.getenv("OPENAI_API_KEY"):
            console.print("[yellow]ANTHROPIC_API_KEY absent — falling back to OpenAI provider[/yellow]")
            return OpenAIQAProvider()
        raise RuntimeError("No QA provider available — set ANTHROPIC_API_KEY or OPENAI_API_KEY")
    raise ValueError(f"Unknown provider: {preferred!r}")


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _compute_weighted_score(scores: dict) -> float:
    total_weight = sum(SCORE_WEIGHTS[d] for d in SCORE_DIMENSIONS)
    weighted_sum = sum(scores.get(d, 5) * SCORE_WEIGHTS[d] for d in SCORE_DIMENSIONS)
    return round(weighted_sum / total_weight, 2)


def _compute_verdict(scores: dict, weighted: float) -> tuple[str, str | None]:
    """Return (verdict, hard_fail_dimension|None)."""
    for dim in SCORE_DIMENSIONS:
        if dim in HARD_FAIL_EXEMPT:
            continue
        if scores.get(dim, 5) <= HARD_FAIL_THRESHOLD:
            return "FAIL", dim
    if weighted >= PASS_THRESHOLD:
        return "PASS", None
    return "FAIL", None


# ---------------------------------------------------------------------------
# Frame extraction
# ---------------------------------------------------------------------------

def extract_frames(video_path, video_id, frames_dir, n=5):
    frames_dir = Path(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(video_path)],
        capture_output=True, text=True,
    )
    if probe.returncode != 0:
        console.print(f"[red]✗ ffprobe failed: {probe.stderr[:200]}[/red]")
        return []

    streams = json.loads(probe.stdout).get("streams", [])
    duration = None
    for s in streams:
        if s.get("codec_type") == "video":
            duration = float(s.get("duration", 0))
            break

    if not duration:
        console.print("[red]✗ Could not determine video duration[/red]")
        return []

    percentages = [0.0, 0.25, 0.50, 0.75, 0.95]
    frame_paths = []

    for i, pct in enumerate(percentages):
        ts = duration * pct
        out_path = frames_dir / f"{video_id}_frame_{i+1}.jpg"

        result = subprocess.run(
            ["ffmpeg", "-y", "-ss", str(ts), "-i", str(video_path),
             "-frames:v", "1", "-q:v", "3", str(out_path)],
            capture_output=True, text=True,
        )

        if result.returncode == 0 and out_path.exists():
            console.print(f"  [dim]Frame {i+1}: {pct*100:.0f}% ({ts:.1f}s) → {out_path.name}[/dim]")
            frame_paths.append(str(out_path))
        else:
            console.print(f"  [yellow]WARNING: Frame {i+1} extraction failed[/yellow]")

    return frame_paths


# ---------------------------------------------------------------------------
# Context loader
# ---------------------------------------------------------------------------

def _load_context(video_id: str) -> dict:
    """Load hook JSON for title + script excerpt (best-effort)."""
    log_dir  = Path(os.getenv("LOG_DIR", "logs"))
    hook_path = log_dir / "hooks" / f"{video_id}.json"
    if not hook_path.exists():
        return {"video_id": video_id, "title": "", "script_excerpt": ""}
    with open(hook_path, encoding="utf-8") as f:
        data = json.load(f)
    return {
        "video_id":       video_id,
        "title":          data.get("title", ""),
        "script_excerpt": data.get("full_script", "")[:300],
    }


# ---------------------------------------------------------------------------
# Main QC runner
# ---------------------------------------------------------------------------

def run_qc(video_id: str, video_path, provider_name: str | None = None) -> dict:
    log_dir    = Path(os.getenv("LOG_DIR", "logs"))
    frames_dir = log_dir / "frames"
    qc_dir     = log_dir / "qc"
    qc_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"[cyan]Extracting frames from {Path(video_path).name}...[/cyan]")
    frame_paths = extract_frames(video_path, video_id, frames_dir)

    if not frame_paths:
        console.print("[red]✗ No frames extracted — aborting QC[/red]")
        sys.exit(1)

    # Load context for richer evaluation
    context = _load_context(video_id)

    # Select provider
    try:
        provider = _auto_select_provider(provider_name)
        provider_label = type(provider).__name__.replace("QAProvider", "").lower()
    except RuntimeError as e:
        console.print(f"[red]ERROR: {e}[/red]")
        sys.exit(1)

    console.print(f"[cyan]Sending {len(frame_paths)} frames to {provider_label} provider...[/cyan]")

    evaluation = provider.evaluate(frame_paths, context)

    scores   = evaluation["scores"]
    weighted = _compute_weighted_score(scores)
    verdict, hard_fail_dim = _compute_verdict(scores, weighted)

    result = {
        "video_id":        video_id,
        "timestamp":       datetime.now().strftime("%Y-%m-%d %H:%M"),
        "provider":        provider_label,
        "verdict":         verdict,
        "weighted_score":  weighted,
        "hard_fail_dim":   hard_fail_dim,
        "scores":          scores,
        "issues":          evaluation.get("issues", []),
        "recommendations": evaluation.get("recommendations", []),
        "summary":         evaluation.get("summary", ""),
        "frames_checked":  len(frame_paths),
        "raw_response":    evaluation.get("raw_response", ""),
    }

    qc_path = qc_dir / f"{video_id}_qc.json"
    with open(qc_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # ── Print report ──────────────────────────────────────────────────────────
    verdict_color = "green" if verdict == "PASS" else "red"
    console.print(f"\n[bold]QC Report — {video_id}[/bold]")
    console.print(f"  Verdict:        [{verdict_color}]{verdict}[/{verdict_color}]")
    console.print(f"  Weighted score: {weighted:.2f} / 10.00  (pass ≥ {PASS_THRESHOLD})")
    console.print(f"  Provider:       {provider_label}")

    if hard_fail_dim:
        console.print(f"  [red]Hard fail: {hard_fail_dim} scored ≤ {HARD_FAIL_THRESHOLD}[/red]")

    console.print("\n  [bold]Dimension scores:[/bold]")
    for dim in SCORE_DIMENSIONS:
        score = scores.get(dim, "?")
        bar   = "█" * int(score) + "░" * (10 - int(score))
        color = "green" if score >= 7 else ("yellow" if score >= 5 else "red")
        weight_label = f"×{SCORE_WEIGHTS[dim]}"
        console.print(f"  {dim:<22} [{color}]{score:>2}[/{color}] {bar}  {weight_label}")

    if result["issues"]:
        console.print("\n  [bold]Issues:[/bold]")
        for issue in result["issues"]:
            console.print(f"    • {issue}")

    if result["recommendations"]:
        console.print("\n  [bold]Recommendations:[/bold]")
        for rec in result["recommendations"]:
            console.print(f"    → {rec}")

    if result["summary"]:
        console.print(f"\n  [dim]{result['summary']}[/dim]")

    console.print(f"\n[green]✓ QC result saved to {qc_path}[/green]")

    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="PawFactory multi-provider visual QC")
    parser.add_argument("--video-id",   required=True, help="Video ID to check")
    parser.add_argument("--video-file", default=None,  help="Override video file path")
    parser.add_argument(
        "--provider",
        default=None,
        choices=["claude", "openai"],
        help="QA provider (default: auto-select, prefers claude)",
    )
    args = parser.parse_args()

    output_dir = Path(os.getenv("OUTPUT_DIR", "output"))

    if args.video_file:
        video_path = Path(args.video_file)
    else:
        candidates = list(output_dir.glob(f"{args.video_id}_final.*"))
        video_path = candidates[0] if candidates else None

    if not video_path or not video_path.exists():
        console.print(f"[red]ERROR: Final video not found for {args.video_id} in {output_dir}[/red]")
        console.print("  Expected: output/{video_id}_final.mp4")
        sys.exit(1)

    run_qc(args.video_id, video_path, provider_name=args.provider)


if __name__ == "__main__":
    main()
