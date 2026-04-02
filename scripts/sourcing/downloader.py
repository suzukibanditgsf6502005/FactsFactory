#!/usr/bin/env python3
"""
downloader.py — PawFactory video downloader
Downloads video from URL using yt-dlp.
Usage:
  python scripts/sourcing/downloader.py --url "URL" --id "abc123"
  python scripts/sourcing/downloader.py --from-candidates logs/candidates_20250325.json --top-n 2
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
console = Console()


def download_video(url, video_id, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    out_template = str(output_dir / f"{video_id}.%(ext)s")

    # Check if already downloaded
    existing = list(output_dir.glob(f"{video_id}.*"))
    if existing:
        console.print(f"[yellow]Already downloaded: {existing[0].name}[/yellow]")
        return str(existing[0])

    cmd = [
        "yt-dlp",
        "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "--merge-output-format", "mp4",
        "--output", out_template,
        "--no-playlist",
        "--retries", "3",
        "--fragment-retries", "3",
        "--no-warnings",
        url,
    ]

    console.print(f"[cyan]Downloading {video_id}...[/cyan]")
    console.print(f"  URL: {url[:80]}{'...' if len(url) > 80 else ''}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        error_msg = result.stderr.strip()
        console.print(f"[red]✗ Download failed for {video_id}:[/red]")
        console.print(f"  {error_msg[:200]}")

        # Log error
        log_dir = Path(os.getenv("LOG_DIR", "logs"))
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / "errors.log", "a") as f:
            f.write(f"[downloader] {video_id}: {error_msg}\n")

        return None

    # Find the downloaded file
    downloaded = list(output_dir.glob(f"{video_id}.*"))
    if not downloaded:
        console.print(f"[red]✗ File not found after download for {video_id}[/red]")
        return None

    file_path = str(downloaded[0])
    file_size = os.path.getsize(file_path) / (1024 * 1024)
    console.print(f"[green]✓ Downloaded: {downloaded[0].name} ({file_size:.1f} MB)[/green]")
    return file_path


def main():
    parser = argparse.ArgumentParser(description="PawFactory Video Downloader")
    parser.add_argument("--url", help="Video URL to download")
    parser.add_argument("--id", dest="video_id", help="Video ID (used for filename)")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: inbox/)")
    parser.add_argument("--from-candidates", help="JSON candidates file to batch download")
    parser.add_argument("--top-n", type=int, default=2,
                        help="How many top candidates to download (default: 2)")
    args = parser.parse_args()

    output_dir = args.output_dir or os.getenv("INBOX_DIR", "inbox")

    if args.from_candidates:
        with open(args.from_candidates, "r") as f:
            candidates = json.load(f)

        top = candidates[:args.top_n]
        console.print(f"[cyan]Downloading top {len(top)} candidates...[/cyan]")

        results = []
        for c in top:
            path = download_video(c["video_url"], c["id"], output_dir)
            results.append({
                "id": c["id"],
                "title": c["title"],
                "file": path,
                "source": c["source"],
                "author": c.get("author", "unknown"),
                "viral_score": c["viral_score"],
            })

        # Save download manifest
        log_dir = Path(os.getenv("LOG_DIR", "logs"))
        log_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = log_dir / "downloaded.json"

        existing_manifest = []
        if manifest_path.exists():
            with open(manifest_path) as f:
                existing_manifest = json.load(f)

        # Merge, avoid duplicates
        existing_ids = {r["id"] for r in existing_manifest}
        for r in results:
            if r["id"] not in existing_ids:
                existing_manifest.append(r)

        with open(manifest_path, "w") as f:
            json.dump(existing_manifest, f, indent=2)

        successful = [r for r in results if r["file"]]
        console.print(f"\n[green]✓ Downloaded {len(successful)}/{len(top)} videos[/green]")

    elif args.url and args.video_id:
        path = download_video(args.url, args.video_id, output_dir)
        if not path:
            sys.exit(1)
    else:
        console.print("[red]ERROR: Provide --url + --id, or --from-candidates[/red]")
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
