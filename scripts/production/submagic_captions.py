#!/usr/bin/env python3
"""
submagic_captions.py — PawFactory Submagic caption integration
Uploads a finished Short to Submagic API, polls for completion,
downloads the captioned video.

Usage:
  python scripts/production/submagic_captions.py --video-id "31qgcpec"
  python scripts/production/submagic_captions.py --test
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
console = Console()

API_BASE = "https://api.submagic.co/v1"
POLL_INTERVAL = 10   # seconds between status checks
POLL_TIMEOUT  = 300  # 5 minutes max


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _headers():
    api_key = os.getenv("SUBMAGIC_API_KEY")
    if not api_key:
        console.print("[red]ERROR: SUBMAGIC_API_KEY missing in .env[/red]")
        sys.exit(1)
    return {"x-api-key": api_key, "Content-Type": "application/json"}


def _log_error(msg):
    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(log_dir / "errors.log", "a") as f:
        f.write(f"[submagic] {msg}\n")


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

def create_project(video_url: str, title: str, template: str = "Sara") -> str | None:
    """POST /v1/projects — returns project_id on success."""
    payload = {
        "title": title[:100],
        "language": "en",
        "videoUrl": video_url,
        "template": template,
    }
    resp = requests.post(f"{API_BASE}/projects", headers=_headers(), json=payload, timeout=30)

    if resp.status_code == 201:
        project_id = resp.json().get("id")
        console.print(f"  [green]✓ Project created: {project_id}[/green]")
        return project_id
    else:
        msg = f"create_project HTTP {resp.status_code}: {resp.text[:300]}"
        console.print(f"[red]✗ {msg}[/red]")
        _log_error(msg)
        return None


def trigger_export(project_id: str) -> bool:
    """POST /v1/projects/{id}/export — kick off rendering."""
    payload = {"fps": 30, "width": 1080, "height": 1920}
    resp = requests.post(
        f"{API_BASE}/projects/{project_id}/export",
        headers=_headers(), json=payload, timeout=30,
    )
    if resp.status_code == 200:
        console.print(f"  [green]✓ Export triggered[/green]")
        return True
    else:
        msg = f"trigger_export HTTP {resp.status_code}: {resp.text[:300]}"
        console.print(f"[red]✗ {msg}[/red]")
        _log_error(msg)
        return False


def poll_project(project_id: str) -> dict | None:
    """GET /v1/projects/{id} — poll until completed/failed or timeout."""
    deadline = time.time() + POLL_TIMEOUT
    attempt = 0

    while time.time() < deadline:
        attempt += 1
        resp = requests.get(
            f"{API_BASE}/projects/{project_id}",
            headers=_headers(), timeout=30,
        )
        if resp.status_code != 200:
            msg = f"poll HTTP {resp.status_code}: {resp.text[:200]}"
            console.print(f"[red]✗ {msg}[/red]")
            _log_error(msg)
            return None

        data = resp.json()
        status = data.get("status", "unknown")
        console.print(f"  [dim]Status [{attempt}]: {status}[/dim]")

        if status == "completed":
            return data
        if status == "failed":
            _log_error(f"project {project_id} failed: {json.dumps(data)[:300]}")
            console.print(f"[red]✗ Submagic processing failed[/red]")
            return None

        time.sleep(POLL_INTERVAL)

    console.print(f"[red]✗ Timeout after {POLL_TIMEOUT}s waiting for {project_id}[/red]")
    _log_error(f"timeout waiting for project {project_id}")
    return None


def download_video(url: str, dest_path: Path) -> bool:
    """Stream download from url to dest_path."""
    resp = requests.get(url, stream=True, timeout=120)
    if resp.status_code != 200:
        _log_error(f"download HTTP {resp.status_code} from {url[:80]}")
        return False

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 64):
            f.write(chunk)

    size_mb = dest_path.stat().st_size / (1024 * 1024)
    console.print(f"  [green]✓ Downloaded: {dest_path.name} ({size_mb:.1f} MB)[/green]")
    return True


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def add_captions(video_path: str, video_id: str, style: str = "Sara") -> str | None:
    """
    Full flow: upload → export → poll → download.
    Returns path to captioned output file, or None on failure.
    """
    output_dir = Path(os.getenv("OUTPUT_DIR", "output"))
    out_path = output_dir / f"{video_id}_captioned.mp4"

    if out_path.exists():
        console.print(f"[yellow]Captioned video already exists: {out_path.name}[/yellow]")
        return str(out_path)

    console.print(f"[cyan]Submagic: adding captions to {video_id}...[/cyan]")
    console.print(f"  Style: {style}")

    # Submagic requires a publicly accessible URL — not a local file path.
    # The caller must supply a URL; for local files this step is skipped.
    video_path = str(video_path)
    if not (video_path.startswith("http://") or video_path.startswith("https://")):
        console.print("[red]ERROR: Submagic requires a public video URL, not a local path.[/red]")
        console.print("  Upload the file to a CDN/S3 first and pass the URL with --video-url.")
        _log_error(f"{video_id}: local file path passed — Submagic needs public URL")
        return None

    # 1. Create project
    project_id = create_project(video_path, video_id, template=style)
    if not project_id:
        return None

    # 2. Trigger export
    if not trigger_export(project_id):
        return None

    # 3. Poll for completion
    console.print(f"  [cyan]Polling for completion (up to {POLL_TIMEOUT}s)...[/cyan]")
    result = poll_project(project_id)
    if not result:
        return None

    # 4. Get download URL
    download_url = result.get("downloadUrl") or result.get("directUrl")
    if not download_url:
        msg = f"{video_id}: no downloadUrl in completed project response"
        console.print(f"[red]✗ {msg}[/red]")
        _log_error(msg)
        return None

    # 5. Download
    console.print(f"  [cyan]Downloading captioned video...[/cyan]")
    if not download_video(download_url, out_path):
        return None

    console.print(f"[green]✓ Submagic captions done: {out_path}[/green]")
    return str(out_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="PawFactory Submagic Caption Integration")
    parser.add_argument("--video-id", help="Video ID (looks up output/VIDEO_ID_final.mp4)")
    parser.add_argument("--video-url", help="Public URL of the video to caption")
    parser.add_argument("--style", default="Sara", help="Submagic template name (default: Sara)")
    parser.add_argument("--test", action="store_true", help="Test API key and list templates")
    args = parser.parse_args()

    if args.test:
        console.print("[cyan]Testing Submagic API connection...[/cyan]")
        resp = requests.get(
            f"{API_BASE}/templates",
            headers=_headers(), timeout=10,
        )
        if resp.status_code == 200:
            templates = resp.json()
            names = [t.get("name", "?") for t in (templates if isinstance(templates, list) else [])]
            console.print(f"[green]✓ Submagic API connected. Templates available: {len(names)}[/green]")
            if names:
                console.print(f"  Styles: {', '.join(names[:10])}{'...' if len(names) > 10 else ''}")
        else:
            console.print(f"[red]✗ Submagic API test failed: {resp.status_code} — {resp.text[:200]}[/red]")
            sys.exit(1)
        return

    if not args.video_id and not args.video_url:
        console.print("[red]ERROR: Provide --video-id or --video-url[/red]")
        parser.print_help()
        sys.exit(1)

    video_url = args.video_url
    video_id  = args.video_id or "unknown"

    if not video_url and args.video_id:
        # Local final video — inform the user it needs a public URL
        output_dir = Path(os.getenv("OUTPUT_DIR", "output"))
        local_path = output_dir / f"{args.video_id}_final.mp4"
        if not local_path.exists():
            console.print(f"[red]ERROR: {local_path} not found[/red]")
            sys.exit(1)
        console.print(f"[yellow]Note: Found local file {local_path.name}[/yellow]")
        console.print("  Submagic requires a public URL. Options:")
        console.print("  1. Upload to S3/GCS/Cloudflare R2 and pass --video-url")
        console.print("  2. Use a temporary upload service (e.g. transfer.sh)")
        console.print("\n  Quick upload via transfer.sh:")
        console.print(f"  curl --upload-file {local_path} https://transfer.sh/{local_path.name}")
        sys.exit(0)

    result = add_captions(video_url, video_id, style=args.style)
    if not result:
        sys.exit(1)


if __name__ == "__main__":
    main()
