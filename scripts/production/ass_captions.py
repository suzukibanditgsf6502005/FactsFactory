#!/usr/bin/env python3
"""
ass_captions.py v3 — PawFactory viral caption system

Improvements over v2:
  - 4-tier emphasis system (0=neutral, 1=mild, 2=strong, 3=climax)
  - 8-category script analysis via Claude Haiku:
      danger, action, payoff, turn, cta, key, punchline, hook_end_word
  - Local keyword matching as baseline — works without API, boosts with it
  - Hook zone: time-based (first 3s) extended to semantic hook_end_word
  - Function-word grouping: articles/prepositions never shown in isolation
    (now applied inside hook zone too, fixing single-letter captions)
  - Word-length-aware minimum display duration; Tier ≥ 2 guaranteed ≥ 350 ms
  - Two-pass event generation: build → clip overlaps → format
  - End-of-video boost: final word always Tier ≥ 1 with extended hold
  - Hook zone Tier 2 floor for DANGER/ACTION/PAYOFF words (yellow from opening)
  - Tier 2 hold 1.25×, Tier 3 hold 1.20× + 0.50 s extra (was 1.12×/0×/0.30 s)
  - All tuning constants centralized at the top

Public API (unchanged from v2):
  generate_ass_captions(audio_path, output_dir, video_id, script_text="") -> str | None
  burn_ass_captions(video_path, ass_path, output_path) -> bool

Usage:
  python scripts/production/ass_captions.py \\
    --audio inbox/ID_voice.mp3 \\
    --video path/to/video.mp4 \\
    --video-id "ID" \\
    --output-dir output/
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
console = Console()

# ── Timing constants ───────────────────────────────────────────────────────────
MIN_WORD_DURATION  = 0.13    # absolute floor per event (130 ms)
MIN_CHAR_DURATION  = 0.055   # per character — longer text needs more time
TIER2_MIN_DURATION = 0.35    # yellow (Tier ≥ 2) words stay up at least 350 ms
                              # — makes them more likely to appear in sampled frames
PUNCHLINE_EXTRA    = 0.50    # extra seconds held on punchline/climax (additive)
HOOK_SECONDS       = 3.0     # words starting before this timestamp = hook zone
END_ZONE_RATIO     = 0.90    # word indices beyond this fraction = ending zone

# ── Emphasis tiers ─────────────────────────────────────────────────────────────
# fscx/fscy = scale %, color = "WHITE"|"YELLOW", bord = outline px, hold = multiplier
TIERS = {
    0: dict(fscx=100, fscy=100, color="WHITE",  bord=4, hold=1.00),   # neutral
    1: dict(fscx=110, fscy=110, color="WHITE",  bord=4, hold=1.05),   # mild
    2: dict(fscx=122, fscy=122, color="YELLOW", bord=4, hold=1.25),   # strong  (was 1.12)
    3: dict(fscx=140, fscy=140, color="YELLOW", bord=5, hold=1.20),   # climax  (was 1.00)
}
HOOK_SCALE_BONUS = 12  # extra scale % added to any tier ≥ 1 inside the hook zone

# ── ASS color codes (BBGGRR hex — no alpha byte) ──────────────────────────────
ASS_YELLOW = r"\c&H00D7FF&"   # #FFD700 in BBGGRR
ASS_WHITE  = r"\c&HFFFFFF&"

# ── Font detection chain ───────────────────────────────────────────────────────
FONT_CANDIDATES = [
    ("Anton",           "anton"),
    ("Impact",          "impact"),
    ("Arial Black",     "arial black"),
    ("Liberation Sans", "liberation sans"),
    ("DejaVu Sans",     "dejavu sans"),
]

# ── Local keyword sets (baseline emphasis + API boost) ────────────────────────
DANGER_WORDS = frozenset({
    "dying", "dies", "die", "dead", "death", "trapped", "trap", "stuck",
    "drowning", "drown", "drowned", "injured", "injury", "bleeding", "bleed",
    "starving", "starvation", "freezing", "frozen", "burning", "burned",
    "sinking", "sunk", "suffocating", "suffocate", "struggling", "struggle",
    "desperate", "helpless", "abandoned", "critical", "barely", "almost",
    "entangled", "tangled", "caught", "hurt", "pain", "wounds", "wounded",
    "maimed", "unconscious", "exhausted", "dehydrated", "terrified",
})

ACTION_WORDS = frozenset({
    "rescue", "rescued", "save", "saved", "saving", "free", "freed",
    "help", "helped", "helping", "pull", "pulled", "lift", "lifted",
    "carry", "carried", "rush", "rushed", "jump", "jumped", "grab",
    "grabbed", "dive", "dove", "catch", "caught", "climb", "climbed",
    "cut", "untangle", "untangled", "release", "released", "evacuate",
    "evacuated", "extract", "extracted", "fight", "fought", "protect",
    "protected", "intervened", "intervene",
})

PAYOFF_WORDS = frozenset({
    "survived", "survive", "safe", "safety", "alive", "free", "freedom",
    "home", "happy", "healed", "heal", "recovered", "recover", "released",
    "reunited", "reunite", "miracle", "miraculous", "finally", "success",
    "saved", "hope", "amazing", "incredible", "unbelievable", "transformed",
    "thriving", "healthy", "better", "forever", "loved", "family",
})

URGENCY_WORDS = frozenset({
    "now", "never", "only", "last", "final", "just", "barely", "almost",
    "suddenly", "immediately", "instantly", "no", "not", "nothing",
    "nobody", "anyone", "everyone", "always", "worst", "best", "first",
    "seconds", "minutes", "hours", "alone",
})

TENSION_WORDS = frozenset({
    "but", "until", "then", "suddenly", "except", "unless", "however",
    "wait", "unexpectedly", "despite", "though", "although", "yet",
    "still", "even", "before", "after", "when", "while",
})

# Words that must never display alone — always grouped with the next word
FUNCTION_WORDS = frozenset({
    "a", "an", "the", "is", "was", "are", "were", "at", "in", "on",
    "to", "of", "and", "or", "for", "with", "this", "that", "it",
    "he", "she", "they", "we", "you", "his", "her", "their", "its",
})


# ── Helpers ────────────────────────────────────────────────────────────────────

def _detect_font() -> str:
    result = subprocess.run(["fc-list"], capture_output=True, text=True)
    fc = result.stdout.lower()
    for display_name, search_str in FONT_CANDIDATES:
        if search_str in fc:
            console.print(f"  [dim]Caption font: {display_name}[/dim]")
            return display_name
    return "DejaVu Sans"


def _time_to_ass(seconds: float) -> str:
    """Convert float seconds to ASS timestamp H:MM:SS.cc"""
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = int(seconds % 60)
    cs = int(round((seconds % 1) * 100))
    if cs >= 100:
        s += 1
        cs = 0
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _strip_punct(word: str) -> str:
    """Strip leading/trailing punctuation and return UPPERCASE."""
    return word.strip(".,!?;:\"'—–-()[]{}").upper()


# ── Scoring & tier assignment ──────────────────────────────────────────────────

def _score_word(clean: str, analysis: dict, position_ratio: float) -> int:
    """
    Score a word 0–100 based on semantic category membership and script position.
    Higher score → higher visual emphasis tier.

    Signals (additive):
      - Claude analysis categories (primary, stronger weight)
      - Local keyword sets (baseline/reinforcement, works without API)
      - Position boost for hook zone (first 20%) and ending zone (last 10%)
    """
    score = 0
    # clean is UPPERCASE (from _strip_punct). Claude analysis sets are also uppercase.
    # Local keyword frozensets are lowercase, so compare via clean.lower().
    clean_lower = clean.lower()

    # Claude analysis categories — primary signals (uppercase frozensets)
    if clean in analysis.get("danger_set", frozenset()):   score += 55
    if clean in analysis.get("payoff_set", frozenset()):   score += 45
    if clean in analysis.get("action_set", frozenset()):   score += 38
    if clean in analysis.get("key_set",    frozenset()):   score += 32
    if clean in analysis.get("turn_set",   frozenset()):   score += 22
    if clean in analysis.get("cta_set",    frozenset()):   score += 18

    # Local keyword matching — fallback reinforcement (lowercase frozensets)
    if clean_lower in DANGER_WORDS:   score += 28
    if clean_lower in PAYOFF_WORDS:   score += 22
    if clean_lower in ACTION_WORDS:   score += 18
    if clean_lower in URGENCY_WORDS:  score += 14
    if clean_lower in TENSION_WORDS:  score +=  8

    # Position boost
    if position_ratio < 0.20:
        score = int(score * 1.35)   # hook zone amplifier
    elif position_ratio > END_ZONE_RATIO:
        score = int(score * 1.18)   # ending zone amplifier

    return min(score, 100)


def _score_to_tier(score: int) -> int:
    """Map raw score 0–100 to tier 0–3."""
    if score >= 68: return 3
    if score >= 42: return 2
    if score >= 18: return 1
    return 0


# ── ASS tag builder ────────────────────────────────────────────────────────────

def _make_ass_tags(tier: int, hook_bonus: bool = False) -> str:
    """Return ASS inline override tag block for the given tier."""
    t  = TIERS[tier]
    sx = t["fscx"] + (HOOK_SCALE_BONUS if hook_bonus and tier >= 1 else 0)
    sy = t["fscy"] + (HOOK_SCALE_BONUS if hook_bonus and tier >= 1 else 0)
    sx = min(sx, 155)
    sy = min(sy, 155)
    color = ASS_YELLOW if t["color"] == "YELLOW" else ASS_WHITE
    bord  = t["bord"]
    return rf"{{\fscx{sx}\fscy{sy}{color}\bord{bord}}}"


# ── Script analysis (Claude Haiku) ────────────────────────────────────────────

def _analyze_script(script_text: str) -> dict:
    """
    Call Claude Haiku for 8-category semantic script analysis.

    Returns a dict of frozensets (all empty on API failure — local matching still works):
      key_set, danger_set, action_set, payoff_set, turn_set, cta_set,
      punchline (str), hook_end (str)
    """
    _empty = {
        "key_set":    frozenset(),
        "danger_set": frozenset(),
        "action_set": frozenset(),
        "payoff_set": frozenset(),
        "turn_set":   frozenset(),
        "cta_set":    frozenset(),
        "punchline":  "",
        "hook_end":   "",
    }

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("  [dim]No ANTHROPIC_API_KEY — local keyword matching only[/dim]")
        return _empty

    prompt = (
        "Analyze this voiceover script for a viral animal rescue Short.\n"
        "Return ONLY valid JSON — no markdown, no code fences:\n"
        "{\n"
        '  "key_words":     ["WORD", ...],\n'
        '  "danger_words":  ["WORD", ...],\n'
        '  "action_words":  ["WORD", ...],\n'
        '  "payoff_words":  ["WORD", ...],\n'
        '  "turn_words":    ["WORD", ...],\n'
        '  "cta_words":     ["WORD", ...],\n'
        '  "punchline_word": "WORD",\n'
        '  "hook_end_word":  "WORD"\n'
        "}\n\n"
        "Rules (all words UPPERCASE, single token only):\n"
        "- key_words:    max 20% of word count — high emotional weight not in other lists\n"
        "- danger_words: physical threat/danger/injury (DROWNING, DYING, TRAPPED, BLEEDING...)\n"
        "- action_words: rescue action verbs (SAVED, PULLED, FREED, RUSHED, GRABBED...)\n"
        "- payoff_words: resolution/hope/safety (SURVIVED, SAFE, MIRACLE, FINALLY, FREE...)\n"
        "- turn_words:   emotional pivot words (BUT, THEN, UNTIL, SUDDENLY, EXCEPT, WAIT...)\n"
        "- cta_words:    CTA/engagement words (FOLLOW, SHARE, SUBSCRIBE, WATCH...)\n"
        "- punchline_word: single most climactic/impactful word in entire script\n"
        "- hook_end_word:  last word of the very first sentence\n"
        f"\nScript:\n{script_text}"
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.lower().startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        data = json.loads(raw)
        return {
            "key_set":    frozenset(_strip_punct(w) for w in data.get("key_words",    [])),
            "danger_set": frozenset(_strip_punct(w) for w in data.get("danger_words", [])),
            "action_set": frozenset(_strip_punct(w) for w in data.get("action_words", [])),
            "payoff_set": frozenset(_strip_punct(w) for w in data.get("payoff_words", [])),
            "turn_set":   frozenset(_strip_punct(w) for w in data.get("turn_words",   [])),
            "cta_set":    frozenset(_strip_punct(w) for w in data.get("cta_words",    [])),
            "punchline":  _strip_punct(data.get("punchline_word", "") or ""),
            "hook_end":   _strip_punct(data.get("hook_end_word",  "") or ""),
        }
    except Exception as e:
        console.print(f"  [yellow]Script analysis failed ({e}) — local matching only[/yellow]")
        return _empty


# ── Dialogue line builder (two-pass) ──────────────────────────────────────────

def _build_dialogue_lines(words: list, analysis: dict) -> list:
    """
    Convert transcribed words + analysis into ASS Dialogue event lines.

    Pass 1 — generate events:
      - Assigns each word a tier via score function
      - Groups function words with the next word outside hook zone
      - Applies timing: hold multiplier, char-length minimum, punchline extra
      - Boosts hook zone words in scale

    Pass 2 — clip overlaps:
      - Ensures no event end time crosses into the next event's start time

    Pass 3 — format:
      - Converts event dicts to ASS Dialogue strings

    Returns list of Dialogue line strings (no header).
    """
    n = len(words)
    if n == 0:
        return []

    # ── Find hook zone boundary ────────────────────────────────────────────────
    # Hook zone = all words starting before HOOK_SECONDS, extended to hook_end_word
    hook_end_idx = -1
    hook_end_word = analysis.get("hook_end", "")
    for i, w in enumerate(words):
        if w["start"] < HOOK_SECONDS:
            hook_end_idx = i
        if hook_end_word and _strip_punct(w["word"]) == hook_end_word:
            hook_end_idx = max(hook_end_idx, i)
            break  # first occurrence only

    # ── Assign tiers ──────────────────────────────────────────────────────────
    punchline_word = analysis.get("punchline", "")
    punchline_used = False
    tiers = []
    for i, w in enumerate(words):
        clean = _strip_punct(w["word"])
        pos   = i / max(n - 1, 1)
        if clean == punchline_word and punchline_word and not punchline_used:
            t = 3
            punchline_used = True
        else:
            score = _score_word(clean, analysis, pos)
            t = _score_to_tier(score)
            if i <= hook_end_idx:
                # Every hook word is at least Tier 1 (visible scale bump)
                t = max(t, 1)
                # Emotionally charged hook words get Tier 2 (yellow) floor
                # so the opening has immediate visible emphasis even without API
                if clean.lower() in DANGER_WORDS or clean.lower() in ACTION_WORDS or clean.lower() in PAYOFF_WORDS:
                    t = max(t, 2)
        tiers.append(t)

    # ── Pass 1: generate event dicts ──────────────────────────────────────────
    events = []
    i = 0
    while i < n:
        w     = words[i]
        tier  = tiers[i]
        clean = _strip_punct(w["word"])
        in_hook = (i <= hook_end_idx)
        is_last = (i == n - 1)

        # Function-word grouping: article/prep + next word shown together.
        # Applied everywhere (including hook zone) to prevent single-letter captions
        # like "A" appearing alone — which looks weak and confused static-frame QC.
        group = [i]
        if (
            clean.lower() in FUNCTION_WORDS
            and tier < 2
            and i + 1 < n
        ):
            nxt_w    = words[i + 1]
            nxt_tier = tiers[i + 1]
            gap      = nxt_w["start"] - w["end"]
            if nxt_tier < 2 and gap < 0.30:
                group.append(i + 1)

        # Display tier = highest tier in the group
        display_tier = max(tiers[k] for k in group)

        # Timing
        start   = words[group[0]]["start"]
        raw_end = words[group[-1]]["end"]

        text = " ".join(_strip_punct(words[k]["word"]) for k in group)

        # Minimum duration: max(base, per-char, yellow-word floor)
        char_min = len(text) * MIN_CHAR_DURATION
        min_dur  = max(MIN_WORD_DURATION, char_min)
        if display_tier >= 2:
            min_dur = max(min_dur, TIER2_MIN_DURATION)

        # Hold multiplier for tier
        hold_dur = (raw_end - start) * TIERS[display_tier]["hold"]

        # Punchline: additive extra hold
        if display_tier == 3:
            hold_dur += PUNCHLINE_EXTRA

        # End-of-video final-word boost
        if is_last or (len(group) > 1 and group[-1] == n - 1):
            hold_dur = max(hold_dur, 0.55)
            if display_tier < 1:
                display_tier = 1

        final_dur = max(hold_dur, min_dur)
        end = start + final_dur

        events.append({
            "start":      start,
            "end":        end,
            "text":       text,
            "tier":       display_tier,
            "hook_bonus": in_hook,
        })

        i += len(group)

    # ── Pass 2: clip overlaps ─────────────────────────────────────────────────
    for j in range(len(events) - 1):
        curr = events[j]
        nxt  = events[j + 1]
        if curr["end"] > nxt["start"]:
            # Preserve minimum duration, clip to just before next event
            clamped = max(curr["start"] + MIN_WORD_DURATION, nxt["start"] - 0.01)
            curr["end"] = clamped

    # ── Pass 3: format to ASS Dialogue strings ────────────────────────────────
    lines = []
    for ev in events:
        tags = _make_ass_tags(ev["tier"], hook_bonus=ev["hook_bonus"])
        lines.append(
            f"Dialogue: 0,{_time_to_ass(ev['start'])},{_time_to_ass(ev['end'])},"
            f"Default,,0,0,0,,{tags}{ev['text']}"
        )

    return lines


# ── ASS generation (public API) ────────────────────────────────────────────────

def generate_ass_captions(
    audio_path: str,
    output_dir: str,
    video_id: str,
    script_text: str = "",
) -> str | None:
    """
    Transcribe audio with Whisper, analyze with Claude Haiku, generate viral ASS file.
    Returns path to .ass file, or None on failure.
    Public API — signature unchanged from v2.
    """
    try:
        import whisper
    except ImportError:
        console.print("[red]Whisper not installed — run: pip install openai-whisper[/red]")
        return None

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ass_path = output_dir / f"{video_id}.ass"

    if ass_path.exists():
        if ass_path.stat().st_size > 100:
            console.print(f"  [dim]ASS captions already exist: {ass_path.name}[/dim]")
            return str(ass_path)
        # File is empty or truncated (e.g. from a prior crash) — regenerate.
        console.print(f"  [yellow]ASS cache is empty/truncated — regenerating[/yellow]")
        ass_path.unlink()

    # ── Transcribe ────────────────────────────────────────────────────────────
    console.print("  [cyan]Transcribing with Whisper (word timestamps)...[/cyan]")
    model  = whisper.load_model("small")
    result = model.transcribe(str(audio_path), word_timestamps=True)

    words = []
    whisper_parts = []
    for seg in result["segments"]:
        for w in seg.get("words", []):
            word = w.get("word", "").strip()
            if word:
                words.append({
                    "word":  word,
                    "start": float(w["start"]),
                    "end":   float(w["end"]),
                })
                whisper_parts.append(word)

    if not words:
        console.print("  [red]Whisper returned no word-level timestamps[/red]")
        return None

    console.print(f"  [dim]{len(words)} words transcribed[/dim]")

    # Use provided script text if available; Whisper text as fallback
    analysis_text = script_text.strip() or " ".join(whisper_parts)

    # ── Analyze with Claude ───────────────────────────────────────────────────
    console.print("  [cyan]Analyzing script with Claude Haiku (v3 schema)...[/cyan]")
    analysis = _analyze_script(analysis_text)

    highlighted = (
        analysis["danger_set"] | analysis["action_set"] |
        analysis["payoff_set"] | analysis["key_set"]
    )
    console.print(f"  [bold]Punchline:[/bold] {analysis['punchline'] or '(none)'}")
    console.print(f"  [bold]Hook ends at:[/bold] {analysis['hook_end'] or '(time-based, 3s)'}")
    console.print(f"  [bold]Highlighted words:[/bold] {len(highlighted)}")

    # ── Build ASS ─────────────────────────────────────────────────────────────
    font = _detect_font()
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "WrapStyle: 0\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font},82,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "-1,0,0,0,100,100,2,0,1,4,0,2,10,10,655,1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    )

    dialogue_lines = _build_dialogue_lines(words, analysis)
    all_lines = [header] + dialogue_lines

    ass_path.write_text("\n".join(all_lines) + "\n", encoding="utf-8")
    console.print(
        f"  [green]✓ ASS captions v3: {ass_path.name} "
        f"({len(words)} words → {len(dialogue_lines)} events)[/green]"
    )
    return str(ass_path)


# ── Video burn (public API) ────────────────────────────────────────────────────

def burn_ass_captions(video_path: str, ass_path: str, output_path: str) -> bool:
    """Burn ASS captions into video via ffmpeg. Returns True on success."""
    ass_escaped = str(ass_path).replace("\\", "/").replace(":", "\\:")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"ass={ass_escaped}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(output_path),
    ]
    console.print("  [cyan]Burning ASS captions into video...[/cyan]")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        console.print(f"  [red]✗ ffmpeg burn failed:[/red]\n  {result.stderr[-500:]}")
        return False
    return True


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="PawFactory Viral Caption System v3")
    parser.add_argument("--audio",      required=True,  help="Path to voiceover MP3")
    parser.add_argument("--video",      required=True,  help="Input video (no captions)")
    parser.add_argument("--video-id",   required=True,  help="ID for output filenames")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--script",     default="",     help="Script text for analysis (overrides hook JSON)")
    args = parser.parse_args()

    output_dir   = Path(args.output_dir)
    captions_dir = Path(os.getenv("LOG_DIR", "logs")) / "captions"

    # Load script from hook JSON if not explicitly provided
    script_text = args.script
    if not script_text:
        base_id   = args.video_id.split("_v")[0].split("_ass")[0]
        hook_path = Path(os.getenv("LOG_DIR", "logs")) / "hooks" / f"{base_id}.json"
        if hook_path.exists():
            try:
                hook_data   = json.loads(hook_path.read_text())
                script_text = hook_data.get("full_script", "")
                if script_text:
                    console.print(f"  [dim]Script loaded from {hook_path.name}[/dim]")
            except Exception:
                pass

    ass_path = generate_ass_captions(args.audio, str(captions_dir), args.video_id, script_text)
    if not ass_path:
        sys.exit(1)

    # Burn to a temp file then replace, in case input == output path
    import tempfile
    import shutil
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name
    final_out = output_dir / f"{args.video_id}_final.mp4"
    if not burn_ass_captions(args.video, ass_path, tmp_path):
        Path(tmp_path).unlink(missing_ok=True)
        sys.exit(1)

    shutil.move(tmp_path, final_out)
    size_mb = final_out.stat().st_size / (1024 * 1024)
    console.print(f"[green]✓ Done: {final_out.name} ({size_mb:.1f} MB)[/green]")


if __name__ == "__main__":
    main()
