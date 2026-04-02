#!/usr/bin/env python3
"""
voiceover.py — PawFactory ElevenLabs voiceover generator
Converts script to MP3 using ElevenLabs API.
Usage:
  python scripts/production/voiceover.py --video-id "abc123"
  python scripts/production/voiceover.py --test
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
console = Console()

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def generate_voiceover(video_id, script_text, voice_id, output_dir):
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        console.print("[red]ERROR: ELEVENLABS_API_KEY missing in .env[/red]")
        sys.exit(1)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{video_id}_voice.mp3"

    if out_path.exists():
        console.print(f"[yellow]Voiceover already exists: {out_path.name}[/yellow]")
        return str(out_path)

    url = ELEVENLABS_API_URL.format(voice_id=voice_id)
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": script_text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.3,
            "use_speaker_boost": True,
        },
    }

    console.print(f"[cyan]Generating voiceover for {video_id}...[/cyan]")
    console.print(f"  Script length: {len(script_text)} chars")

    resp = requests.post(url, headers=headers, json=payload, timeout=60)

    if resp.status_code == 200:
        with open(out_path, "wb") as f:
            f.write(resp.content)
        size_kb = os.path.getsize(out_path) / 1024
        console.print(f"[green]✓ Voiceover saved: {out_path.name} ({size_kb:.0f} KB)[/green]")
        return str(out_path)
    else:
        error = resp.text[:300]
        console.print(f"[red]✗ ElevenLabs API error {resp.status_code}: {error}[/red]")

        log_dir = Path(os.getenv("LOG_DIR", "logs"))
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / "errors.log", "a") as f:
            f.write(f"[voiceover] {video_id}: HTTP {resp.status_code} — {error}\n")

        return None


def main():
    parser = argparse.ArgumentParser(description="PawFactory Voiceover Generator")
    parser.add_argument("--video-id", help="Video ID (looks up logs/hooks/VIDEO_ID.json)")
    parser.add_argument("--hook-json", help="Path to hook JSON file directly")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--voice-id", default=None, help="Override voice ID from .env")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    voice_id = args.voice_id or os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    output_dir = args.output_dir or os.getenv("INBOX_DIR", "inbox")

    if args.test:
        console.print("[cyan]Testing ElevenLabs API...[/cyan]")
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            console.print("[red]✗ ELEVENLABS_API_KEY not set[/red]")
            sys.exit(1)

        resp = requests.get(
            "https://api.elevenlabs.io/v1/user",
            headers={"xi-api-key": api_key},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            chars_used = data.get("subscription", {}).get("character_count", "?")
            chars_limit = data.get("subscription", {}).get("character_limit", "?")
            console.print(f"[green]✓ ElevenLabs connected. Chars used: {chars_used}/{chars_limit}[/green]")
        else:
            console.print(f"[red]✗ ElevenLabs test failed: {resp.status_code}[/red]")
            sys.exit(1)
        return

    # Resolve hook JSON path
    if args.hook_json:
        hook_path = Path(args.hook_json)
    elif args.video_id:
        log_dir = Path(os.getenv("LOG_DIR", "logs"))
        hook_path = log_dir / "hooks" / f"{args.video_id}.json"
    else:
        console.print("[red]ERROR: Provide --video-id or --hook-json[/red]")
        sys.exit(1)

    if not hook_path.exists():
        console.print(f"[red]ERROR: Hook file not found: {hook_path}[/red]")
        console.print("  Run hook_generator.py first.")
        sys.exit(1)

    with open(hook_path) as f:
        hook_data = json.load(f)

    video_id = hook_data.get("video_id", args.video_id or "unknown")
    script = hook_data.get("full_script") or (
        hook_data.get("hook", "") + " " + hook_data.get("narration", "")
    ).strip()

    if not script:
        console.print("[red]ERROR: No script found in hook JSON[/red]")
        sys.exit(1)

    path = generate_voiceover(video_id, script, voice_id, output_dir)
    if not path:
        sys.exit(1)


if __name__ == "__main__":
    main()
