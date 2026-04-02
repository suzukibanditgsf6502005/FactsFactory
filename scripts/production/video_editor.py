#!/usr/bin/env python3
"""
video_editor.py — PawFactory ffmpeg video assembler
Converts raw footage to 9:16 Short with voiceover and captions.
Caption pipeline: Submagic (primary) → Whisper/ffmpeg (fallback)
Usage:
  python scripts/production/video_editor.py --video-id "abc123"
  python scripts/production/video_editor.py --video-id "abc123" --no-captions
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
console = Console()

SUBMAGIC_API = "https://api.submagic.co/v1"
SUBMAGIC_TEMPLATE = "Sara"
SUBMAGIC_TIMEOUT = 300   # 5 minutes max polling

# ── Duration policy (NO LOOPING) ────────────────────────────────────────────
# Source video is a hard constraint. The narration must fit the clip.
# Clips that are too short to support any narration are rejected upstream
# (see run_pipeline.py). If audio still overruns at assembly time, reject here.
DURATION_POLICY_MARGIN = 2.0   # audio must end at least 2s before video ends
MIN_SOURCE_DURATION    = 20.0  # clips shorter than this are rejected (seconds)

# ── Zoom config ───────────────────────────────────────────────────────────────
# Disabled by default: auto-zoom degrades quality and cuts visual context.
# Set to True only if a specific clip has distant subjects that need pulling in.
ENABLE_AUTO_ZOOM = False
AUTO_ZOOM_FACTOR = 1.3


# ---------------------------------------------------------------------------
# ffmpeg helpers
# ---------------------------------------------------------------------------

def run_ffmpeg(cmd, step_name):
    console.print(f"  [dim]ffmpeg: {step_name}[/dim]")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        console.print(f"[red]✗ ffmpeg failed at {step_name}:[/red]")
        console.print(f"  {result.stderr[-500:]}")
        return False
    return True


def get_video_duration(video_path):
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(video_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    for stream in json.loads(result.stdout).get("streams", []):
        if stream.get("codec_type") == "video":
            return float(stream.get("duration", 0))
    return None


def get_audio_duration(audio_path):
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(audio_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    for stream in json.loads(result.stdout).get("streams", []):
        if stream.get("codec_type") == "audio":
            return float(stream.get("duration", 0))
    return None


def format_srt_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ---------------------------------------------------------------------------
# Submagic caption path
# ---------------------------------------------------------------------------

def _upload_to_catbox(file_path):
    """Upload file to litterbox.catbox.moe (24h). Returns public URL or None."""
    console.print("  [cyan]Uploading to catbox.moe...[/cyan]")
    result = subprocess.run(
        [
            "curl", "-s", "--max-time", "120",
            "-F", f"fileToUpload=@{file_path}",
            "-F", "reqtype=fileupload",
            "-F", "time=24h",
            "https://litterbox.catbox.moe/resources/internals/api.php",
        ],
        capture_output=True, text=True,
    )
    url = result.stdout.strip()
    if url.startswith("https://"):
        console.print(f"  [green]✓ Uploaded: {url}[/green]")
        return url
    console.print(f"  [yellow]catbox upload failed: {url[:100]}[/yellow]")
    return None


def _try_submagic(video_path, video_id, final_out):
    """
    Full Submagic flow: upload → create project → poll → download → final_out.
    Returns True on success, False on any failure.
    Original audio is preserved (cleanAudio=False, no TTS template used).
    """
    api_key = os.getenv("SUBMAGIC_API_KEY")
    if not api_key:
        return False

    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    # 1. Upload to catbox
    video_url = _upload_to_catbox(str(video_path))
    if not video_url:
        return False

    # 2. Create project — Sara template adds captions only, no TTS/voiceover
    console.print(f"  [cyan]Creating Submagic project (template: {SUBMAGIC_TEMPLATE})...[/cyan]")
    resp = requests.post(
        f"{SUBMAGIC_API}/projects",
        headers=headers,
        json={
            "title": video_id,
            "language": "en",
            "videoUrl": video_url,
            "cleanAudio": False,    # do not modify original audio
            "magicBrolls": False,   # no AI b-roll
            "magicZooms": False,    # no auto zooms
            "removeBadTakes": False,
        },
        timeout=30,
    )

    if resp.status_code != 201:
        console.print(f"  [yellow]Submagic create failed: {resp.status_code} — {resp.text[:200]}[/yellow]")
        return False

    project_id = resp.json().get("id")
    console.print(f"  [green]✓ Project created: {project_id}[/green]")

    # 3. Poll until completed or failed
    console.print(f"  [cyan]Polling (up to {SUBMAGIC_TIMEOUT}s)...[/cyan]")
    deadline = time.time() + SUBMAGIC_TIMEOUT
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        poll = requests.get(f"{SUBMAGIC_API}/projects/{project_id}", headers=headers, timeout=15)
        if poll.status_code != 200:
            console.print(f"  [yellow]Poll error {poll.status_code}[/yellow]")
            return False

        data = poll.json()
        status = data.get("status", "?")
        console.print(f"  [dim]  [{attempt}] {status}[/dim]")

        if status == "completed":
            download_url = data.get("directUrl") or data.get("downloadUrl")
            if not download_url:
                console.print("  [yellow]No download URL in response[/yellow]")
                return False
            # 4. Download
            console.print("  [cyan]Downloading from Submagic...[/cyan]")
            dl = requests.get(download_url, stream=True, timeout=120)
            if dl.status_code != 200:
                console.print(f"  [yellow]Download failed: {dl.status_code}[/yellow]")
                return False
            with open(final_out, "wb") as f:
                for chunk in dl.iter_content(chunk_size=65536):
                    f.write(chunk)
            size_mb = Path(final_out).stat().st_size / (1024 * 1024)
            console.print(f"  [green]✓ Submagic captions applied ({size_mb:.1f} MB)[/green]")
            return True

        if status == "failed":
            console.print("  [yellow]Submagic project failed[/yellow]")
            return False

        time.sleep(10)

    console.print(f"  [yellow]Submagic timeout after {SUBMAGIC_TIMEOUT}s[/yellow]")
    return False


# ---------------------------------------------------------------------------
# Whisper caption path (fallback)
# ---------------------------------------------------------------------------

def _whisper_captions(audio_path, captions_dir):
    """Transcribe audio with Whisper and write word-by-word SRT. Returns SRT path or None."""
    try:
        import whisper
    except ImportError:
        console.print("[yellow]Whisper not installed — skipping captions[/yellow]")
        return None

    captions_dir = Path(captions_dir)
    captions_dir.mkdir(parents=True, exist_ok=True)

    srt_path = captions_dir / f"{Path(audio_path).stem}.srt"
    if srt_path.exists():
        console.print(f"  [dim]Captions already exist: {srt_path.name}[/dim]")
        return str(srt_path)

    console.print("  [cyan]Transcribing with Whisper (word timestamps)...[/cyan]")
    model = whisper.load_model("small")
    result = model.transcribe(str(audio_path), word_timestamps=True)

    with open(srt_path, "w", encoding="utf-8") as f:
        i = 1
        for seg in result["segments"]:
            for word_data in seg.get("words", []):
                word = word_data["word"].strip()
                if not word:
                    continue
                # {\an8} forces top-center alignment in ffmpeg's subtitle renderer
                f.write(
                    f"{i}\n"
                    f"{format_srt_time(word_data['start'])} --> {format_srt_time(word_data['end'])}\n"
                    f"{{\\an8}}{word}\n\n"
                )
                i += 1

    console.print(f"  [green]✓ Whisper SRT saved: {srt_path.name}[/green]")
    return str(srt_path)


def _burn_srt(tmp_mixed, srt_path, final_out):
    """Burn SRT captions into tmp_mixed → final_out via ffmpeg. Returns True on success."""
    caption_style = (
        "FontName=Arial,FontSize=16,Bold=1,Alignment=8,"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "BorderStyle=1,Outline=3,Shadow=1,"
        "MarginV=60,MarginL=0,MarginR=0"
    )
    srt_escaped = str(srt_path).replace("\\", "/").replace(":", "\\:")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(tmp_mixed),
        "-vf", f"subtitles={srt_escaped}:force_style='{caption_style}'",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(final_out),
    ]
    return run_ffmpeg(cmd, "burn Whisper captions")


# ---------------------------------------------------------------------------
# ASS caption fallback
# ---------------------------------------------------------------------------

def _load_ass_module():
    """Load ass_captions.py via importlib (avoids package path issues)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ass_captions",
        Path(__file__).parent / "ass_captions.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _apply_ass_captions(video_path, audio_path, output_path, video_id):
    """
    Generate ASS captions from audio and burn into video_path → output_path.
    Returns caption method string on success ("ass"), None on failure.
    """
    try:
        mod = _load_ass_module()
    except Exception as e:
        console.print(f"  [yellow]Could not load ass_captions module: {e}[/yellow]")
        return None

    log_dir      = Path(os.getenv("LOG_DIR", "logs"))
    captions_dir = log_dir / "captions"

    # Load full_script from hook JSON so ASS analysis uses the actual narration
    # rather than falling back to the Whisper transcript alone.
    script_text = None
    hook_path = log_dir / "hooks" / f"{video_id}.json"
    if hook_path.exists():
        try:
            with open(hook_path, encoding="utf-8") as _f:
                _hook = json.load(_f)
            script_text = _hook.get("full_script") or _hook.get("narration") or None
        except Exception:
            pass  # non-fatal — ASS falls back to transcript-only analysis

    # ── Cache invalidation ────────────────────────────────────────────────────
    # generate_ass_captions() returns the cached .ass unconditionally if it
    # exists. We must clear both .ass and .srt together whenever regeneration
    # is needed, because they are derived from the same voice transcription.
    #
    # Regenerate if ANY of:
    #   1. Voice is newer than .ass  → voice was regenerated, timings are stale
    #   2. .ass exists but .srt is missing → incomplete cache, rebuild cleanly
    ass_cache = captions_dir / f"{video_id}.ass"
    srt_cache = captions_dir / f"{video_id}_voice.srt"

    def _clear_caption_cache(reason: str):
        ass_cache.unlink(missing_ok=True)
        srt_cache.unlink(missing_ok=True)
        console.print(f"  [yellow]Caption cache cleared ({reason})[/yellow]")

    if ass_cache.exists():
        if Path(audio_path).exists():
            if Path(audio_path).stat().st_mtime > ass_cache.stat().st_mtime:
                _clear_caption_cache("voice is newer than cached captions")
        if ass_cache.exists() and not srt_cache.exists():
            _clear_caption_cache(".ass exists but .srt is missing — incomplete cache")

    ass_path = mod.generate_ass_captions(str(audio_path), str(captions_dir), video_id, script_text)
    if not ass_path:
        return None

    if mod.burn_ass_captions(str(video_path), ass_path, str(output_path)):
        return "ass"
    return None


# ---------------------------------------------------------------------------
# Main assembly
# ---------------------------------------------------------------------------

def assemble_video(video_id, video_file, audio_file, output_dir, skip_captions=False):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    tmp_vertical = output_dir / f"{video_id}_vertical.mp4"
    tmp_mixed    = output_dir / f"{video_id}_mixed.mp4"
    final_out    = output_dir / f"{video_id}_final.mp4"

    if final_out.exists():
        console.print(f"[yellow]Final video already exists: {final_out.name}[/yellow]")
        return str(final_out)

    vid_duration   = get_video_duration(video_file)
    audio_duration = get_audio_duration(audio_file)
    if vid_duration and audio_duration:
        console.print(f"  Video: {vid_duration:.1f}s | Audio: {audio_duration:.1f}s")

    # ── Duration policy: NO LOOPING ───────────────────────────────────────────
    # Source video is a hard constraint. Reject if audio overruns the clip.
    # The pipeline (run_pipeline.py) is responsible for fitting narration to
    # clip length before reaching this step. If overrun still occurs here,
    # it means the shortening pass was skipped or failed — reject cleanly.
    if vid_duration and audio_duration:
        if audio_duration > vid_duration - DURATION_POLICY_MARGIN:
            reason = (
                f"audio ({audio_duration:.1f}s) exceeds clip budget "
                f"({vid_duration:.1f}s − {DURATION_POLICY_MARGIN}s margin = "
                f"{vid_duration - DURATION_POLICY_MARGIN:.1f}s allowed)"
            )
            console.print(f"[red]✗ Duration policy violation — {reason}[/red]")
            console.print("  Shorten the script or use a longer source clip. Looping is disabled.")
            log_dir = Path(os.getenv("LOG_DIR", "logs"))
            log_dir.mkdir(parents=True, exist_ok=True)
            with open(log_dir / "errors.log", "a") as _f:
                from datetime import datetime as _dt
                _f.write(f"[video_editor] {_dt.now().isoformat()} — {video_id}: REJECTED — {reason}\n")
            return None

    # ── Step 1: Convert to 9:16 vertical ─────────────────────────────────────
    console.print(f"[cyan]Assembling video for {video_id}...[/cyan]")

    # Crop right 12% (watermark) + bottom 17% (source subs), then scale to 9:16.
    # Zoom is off by default (ENABLE_AUTO_ZOOM=False) to preserve natural framing.
    if ENABLE_AUTO_ZOOM:
        vf_crop = (
            f"crop=iw*0.88:ih*0.83:iw*0.06:0,"
            f"scale=iw*{AUTO_ZOOM_FACTOR}:ih*{AUTO_ZOOM_FACTOR},"
            f"crop=iw/{AUTO_ZOOM_FACTOR}:ih/{AUTO_ZOOM_FACTOR},"
            f"scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920"
        )
    else:
        vf_crop = (
            "crop=iw*0.88:ih*0.83:iw*0.06:0,"
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920"
        )
    if not run_ffmpeg([
        "ffmpeg", "-y", "-i", str(video_file),
        "-vf", vf_crop,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(tmp_vertical),
    ], "convert to 9:16"):
        return None

    # ── Step 2: Add background music to voiceover, then mux with video ──────────
    # Original source audio is always muted (0.0) — wildlife content only.
    # Music mixer selects track based on emotional arc and blends at 8% volume.
    import importlib.util, sys as _sys
    _spec = importlib.util.spec_from_file_location(
        "music_mixer",
        Path(__file__).parent / "music_mixer.py",
    )
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    mix_music = _mod.mix_music
    music_audio = mix_music(str(audio_file), video_id)
    final_audio = music_audio if music_audio else str(audio_file)

    if not run_ffmpeg([
        "ffmpeg", "-y",
        "-i", str(tmp_vertical), "-i", final_audio,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
        "-shortest", str(tmp_mixed),
    ], "mux audio (voiceover + music, source muted)"):
        return None

    # ── Step 3: Captions ──────────────────────────────────────────────────────
    caption_method = "none"

    if skip_captions:
        tmp_mixed.rename(final_out)
        console.print("  [dim]Captions skipped (--no-captions)[/dim]")

    elif os.getenv("SUBMAGIC_API_KEY"):
        # Primary: Submagic — uploads tmp_mixed, gets back captioned video
        console.print("  [cyan]Trying Submagic captions...[/cyan]")
        try:
            ok = _try_submagic(tmp_mixed, video_id, final_out)
        except Exception as e:
            console.print(f"  [yellow]Submagic error: {e}[/yellow]")
            ok = False

        if ok:
            caption_method = "submagic"
            tmp_mixed.unlink(missing_ok=True)
        else:
            # Fallback: ASS captions (viral TikTok style)
            console.print("  [yellow]Submagic failed — falling back to ASS captions[/yellow]")
            caption_method = _apply_ass_captions(tmp_mixed, audio_file, final_out, video_id)
            if caption_method:
                tmp_mixed.unlink(missing_ok=True)
            else:
                tmp_mixed.rename(final_out)
                caption_method = "none"

    else:
        # No Submagic key — use ASS captions directly
        console.print("  [dim]No SUBMAGIC_API_KEY — using ASS captions[/dim]")
        caption_method = _apply_ass_captions(tmp_mixed, audio_file, final_out, video_id)
        if not caption_method:
            tmp_mixed.rename(final_out)
            caption_method = "none"

    tmp_vertical.unlink(missing_ok=True)

    # ── Step 4: Auto-trim to voiceover duration + 0.5s buffer ────────────────
    # Prevents dead air when source video or Submagic output is longer than audio.
    # Runs unconditionally — trim is independent of whether captions were applied.
    if final_out.exists():
        audio_dur = get_audio_duration(audio_file)
        video_dur = get_video_duration(final_out)
        if audio_dur and video_dur and (video_dur - audio_dur) > 2.0:
            trim_to = audio_dur + 0.5
            console.print(
                f"  [yellow]Dead air detected ({video_dur:.1f}s video vs {audio_dur:.1f}s audio) "
                f"— trimming to {trim_to:.1f}s[/yellow]"
            )
            tmp_trim = output_dir / f"{video_id}_trim.mp4"
            if run_ffmpeg([
                "ffmpeg", "-y",
                "-i", str(final_out),
                "-t", str(trim_to),
                "-c", "copy",
                str(tmp_trim),
            ], "auto-trim dead air"):
                final_out.unlink()
                tmp_trim.rename(final_out)

    if final_out.exists():
        size_mb = final_out.stat().st_size / (1024 * 1024)
        console.print(
            f"[green]✓ Final video: {final_out.name} ({size_mb:.1f} MB) "
            f"[captions: {caption_method}][/green]"
        )
        return str(final_out)

    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="PawFactory Video Editor")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--video-file", default=None)
    parser.add_argument("--audio-file", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--no-captions", action="store_true")
    args = parser.parse_args()

    inbox_dir  = Path(os.getenv("INBOX_DIR", "inbox"))
    output_dir = Path(args.output_dir or os.getenv("OUTPUT_DIR", "output"))
    vid_id     = args.video_id

    # Resolve video file — prefer smart clip if available
    if args.video_file:
        video_file = Path(args.video_file)
    else:
        clip = inbox_dir / f"{vid_id}_clip.mp4"
        if clip.exists():
            video_file = clip
        else:
            candidates = list(inbox_dir.glob(f"{vid_id}.*"))
            mp4s = [f for f in candidates if f.suffix == ".mp4"]
            video_file = mp4s[0] if mp4s else (candidates[0] if candidates else None)

    if not video_file or not video_file.exists():
        console.print(f"[red]ERROR: Video file not found for {vid_id} in {inbox_dir}[/red]")
        sys.exit(1)

    # Resolve audio file
    audio_file = Path(args.audio_file) if args.audio_file else inbox_dir / f"{vid_id}_voice.mp3"
    if not audio_file.exists():
        console.print(f"[red]ERROR: Audio file not found: {audio_file}[/red]")
        console.print("  Run voiceover.py first.")
        sys.exit(1)

    result = assemble_video(vid_id, video_file, audio_file, output_dir, skip_captions=args.no_captions)
    if not result:
        sys.exit(1)


if __name__ == "__main__":
    main()
