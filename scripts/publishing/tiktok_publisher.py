#!/usr/bin/env python3
"""
tiktok_publisher.py — PawFactory TikTok Content Posting API client

Uploads produced shorts to TikTok via the TikTok Content Posting API v2.

Two posting modes (set TIKTOK_POST_MODE in .env):
  DIRECT_POST           — posts directly to your TikTok feed (or at scheduled_time)
  UPLOAD_TO_CREATOR_INBOX — uploads to TikTok Studio drafts; you finalize publishing manually

Scheduling:
  DIRECT_POST supports scheduled_publish_time (15 min – 10 days in the future).
  UPLOAD_TO_CREATOR_INBOX does NOT support scheduling.

TikTok OAuth2 setup (one-time):
  python scripts/publishing/tiktok_publisher.py --auth

Credentials:
  TIKTOK_ACCESS_TOKEN    — User access token (required for upload)
  TIKTOK_CLIENT_KEY      — App client key (required for OAuth refresh)
  TIKTOK_CLIENT_SECRET   — App client secret (required for OAuth refresh)
  TIKTOK_POST_MODE       — DIRECT_POST or UPLOAD_TO_CREATOR_INBOX (default: DIRECT_POST)
  TIKTOK_PRIVACY         — PUBLIC_TO_EVERYONE, MUTUAL_FOLLOW_FRIENDS, or SELF_ONLY (default: PUBLIC_TO_EVERYONE)
  TIKTOK_TOKEN_FILE      — where to store/refresh tokens (default: ~/.pawfactory_tiktok_token.json)

Setup:
  1. Create a TikTok developer app at https://developers.tiktok.com
  2. Enable the "Content Posting API" and request scopes: video.publish, video.upload
  3. Complete app review (may take days–weeks for production accounts)
  4. Set TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET in .env
  5. Run: python scripts/publishing/tiktok_publisher.py --auth
     This launches a local OAuth flow and saves your access + refresh tokens.
  6. Test: python scripts/publishing/tiktok_publisher.py --test

Note on Direct Post vs Creator Inbox:
  - DIRECT_POST requires the account to have ≥1000 followers (TikTok policy).
  - UPLOAD_TO_CREATOR_INBOX works for any account and is the safe default.
  - Once video is in Creator Inbox, open TikTok Studio → Drafts → publish manually.

Usage (direct):
  python scripts/publishing/tiktok_publisher.py --video-id 31xxxx
  python scripts/publishing/tiktok_publisher.py --video-id 31xxxx --schedule "2026-04-03T20:00:00"
  python scripts/publishing/tiktok_publisher.py --video-id 31xxxx --mode UPLOAD_TO_CREATOR_INBOX
"""

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
console = Console()

TIKTOK_AVAILABLE = True  # uses requests, always available

INIT_URL   = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
TOKEN_URL  = "https://open.tiktokapis.com/v2/oauth/token/"
AUTH_URL   = "https://www.tiktok.com/v2/auth/authorize/"

CHUNK_SIZE     = 10 * 1024 * 1024   # 10 MB per chunk
POLL_INTERVAL  = 5                   # seconds between status polls
POLL_MAX_TRIES = 60                  # max ~5 minutes

DEFAULT_TOKEN_FILE = Path.home() / ".pawfactory_tiktok_token.json"


def _token_file() -> Path:
    return Path(os.getenv("TIKTOK_TOKEN_FILE", str(DEFAULT_TOKEN_FILE))).expanduser()


def _load_token() -> dict | None:
    f = _token_file()
    if f.exists():
        with open(f) as fp:
            return json.load(fp)
    return None


def _save_token(data: dict):
    f = _token_file()
    with open(f, "w") as fp:
        json.dump(data, fp, indent=2)
    f.chmod(0o600)


def _access_token() -> str | None:
    """
    Return the current TikTok access token.
    Priority: TIKTOK_ACCESS_TOKEN env var → token file.
    """
    t = os.getenv("TIKTOK_ACCESS_TOKEN", "")
    if t:
        return t
    tok = _load_token()
    if tok:
        return tok.get("access_token")
    return None


def _refresh_token_if_needed() -> str | None:
    """
    Attempt to refresh the access token using the stored refresh token.
    Returns the new access token on success, None on failure.
    """
    tok = _load_token()
    if not tok or not tok.get("refresh_token"):
        return None

    client_key    = os.getenv("TIKTOK_CLIENT_KEY", "")
    client_secret = os.getenv("TIKTOK_CLIENT_SECRET", "")

    if not client_key or not client_secret:
        return None

    resp = requests.post(TOKEN_URL, data={
        "client_key":    client_key,
        "client_secret": client_secret,
        "grant_type":    "refresh_token",
        "refresh_token": tok["refresh_token"],
    }, timeout=15)

    if resp.status_code == 200:
        new_tok = resp.json().get("data", {})
        tok["access_token"]  = new_tok.get("access_token", tok["access_token"])
        tok["refresh_token"] = new_tok.get("refresh_token", tok["refresh_token"])
        tok["expires_in"]    = new_tok.get("expires_in")
        tok["refreshed_at"]  = datetime.now(timezone.utc).isoformat()
        _save_token(tok)
        return tok["access_token"]

    return None


class TikTokPublisher:
    def is_configured(self) -> bool:
        """Return True if we have an access token."""
        return bool(_access_token())

    def upload(
        self,
        video_path: str,
        title: str,
        scheduled_time: datetime | None = None,
        post_mode: str | None = None,
        privacy: str | None = None,
    ) -> dict:
        """
        Upload a video to TikTok.

        post_mode:
          DIRECT_POST           — post directly (or schedule)
          UPLOAD_TO_CREATOR_INBOX — draft; finish manually in TikTok Studio

        Returns: {"status": str, "publish_id": str, "url": str, "mode": str}

        status values:
          published         — DIRECT_POST, immediate
          scheduled         — DIRECT_POST with future scheduled_time
          draft_uploaded    — UPLOAD_TO_CREATOR_INBOX
          failed            — something went wrong (check exception)
        """
        access_token = _access_token()
        if not access_token:
            raise RuntimeError("TIKTOK_ACCESS_TOKEN not set and no token file found. Run --auth first.")

        mode    = post_mode or os.getenv("TIKTOK_POST_MODE", "DIRECT_POST")
        privacy = privacy   or os.getenv("TIKTOK_PRIVACY",   "PUBLIC_TO_EVERYONE")

        # Scheduling only makes sense in DIRECT_POST mode
        if scheduled_time and mode != "DIRECT_POST":
            console.print("  [dim]Note: scheduling not available in UPLOAD_TO_CREATOR_INBOX mode — ignoring schedule[/dim]")
            scheduled_time = None

        video_size = Path(video_path).stat().st_size
        chunk_count = math.ceil(video_size / CHUNK_SIZE)

        # ── Step 1: Init upload ───────────────────────────────────────────────
        post_info: dict = {
            "title":           title[:2200],  # TikTok max 2200 chars
            "privacy_level":   privacy,
            "disable_duet":    False,
            "disable_comment": False,
            "disable_stitch":  False,
            "video_cover_timestamp_ms": 1000,
        }

        if scheduled_time and mode == "DIRECT_POST":
            if scheduled_time.tzinfo is None:
                scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)
            unix_ts = int(scheduled_time.timestamp())
            now_ts  = int(datetime.now(timezone.utc).timestamp())
            mins_ahead = (unix_ts - now_ts) // 60
            if mins_ahead < 15:
                raise ValueError(
                    f"TikTok scheduled_publish_time must be ≥15 min in the future "
                    f"(got {mins_ahead} min). Adjust --tiktok schedule time."
                )
            if mins_ahead > 10 * 24 * 60:
                raise ValueError("TikTok scheduled_publish_time must be ≤10 days in the future.")
            post_info["scheduled_publish_time"] = unix_ts

        source_info = {
            "source":            "FILE_UPLOAD",
            "video_size":        video_size,
            "chunk_size":        CHUNK_SIZE,
            "total_chunk_count": chunk_count,
        }

        init_body = {
            "post_info":   post_info,
            "source_info": source_info,
            "post_mode":   mode,
        }

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/json; charset=UTF-8",
        }

        console.print(f"  [dim]TikTok init upload ({video_size / 1024 / 1024:.1f} MB, {chunk_count} chunk(s), mode: {mode})...[/dim]")

        init_resp = requests.post(INIT_URL, json=init_body, headers=headers, timeout=30)

        if init_resp.status_code == 401:
            # Try token refresh once
            console.print("  [dim]Access token expired — attempting refresh...[/dim]")
            new_token = _refresh_token_if_needed()
            if new_token:
                headers["Authorization"] = f"Bearer {new_token}"
                init_resp = requests.post(INIT_URL, json=init_body, headers=headers, timeout=30)

        if init_resp.status_code != 200:
            raise RuntimeError(
                f"TikTok init failed ({init_resp.status_code}): {init_resp.text[:500]}"
            )

        init_data = init_resp.json()
        if init_data.get("error", {}).get("code") not in (None, "ok"):
            raise RuntimeError(f"TikTok init error: {init_data['error']}")

        data       = init_data["data"]
        publish_id = data["publish_id"]
        upload_url = data["upload_url"]

        console.print(f"  [dim]publish_id: {publish_id}[/dim]")

        # ── Step 2: Upload chunks ─────────────────────────────────────────────
        with open(video_path, "rb") as f:
            for chunk_idx in range(chunk_count):
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                start = chunk_idx * CHUNK_SIZE
                end   = start + len(chunk) - 1

                chunk_headers = {
                    "Content-Type":   "video/mp4",
                    "Content-Range":  f"bytes {start}-{end}/{video_size}",
                    "Content-Length": str(len(chunk)),
                }
                put_resp = requests.put(
                    upload_url, data=chunk, headers=chunk_headers, timeout=120
                )
                if put_resp.status_code not in (200, 206):
                    raise RuntimeError(
                        f"TikTok chunk {chunk_idx+1}/{chunk_count} upload failed "
                        f"({put_resp.status_code}): {put_resp.text[:200]}"
                    )
                console.print(
                    f"  [dim]  chunk {chunk_idx+1}/{chunk_count} uploaded[/dim]", end="\r"
                )

        console.print()

        # ── Step 3: Poll until complete ───────────────────────────────────────
        # For UPLOAD_TO_CREATOR_INBOX, the video goes to drafts — status ends at SEND_TO_USER_INBOX
        # For DIRECT_POST, status ends at PUBLISH_COMPLETE (or SCHEDULED)

        console.print("  [dim]Polling publish status...[/dim]")

        final_status = None
        for attempt in range(POLL_MAX_TRIES):
            time.sleep(POLL_INTERVAL)
            status_resp = requests.post(
                STATUS_URL,
                json={"publish_id": publish_id},
                headers=headers,
                timeout=15,
            )
            if status_resp.status_code != 200:
                continue

            status_data = status_resp.json().get("data", {})
            status      = status_data.get("status", "")
            console.print(f"  [dim]  status: {status}[/dim]", end="\r")

            if status in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
                final_status = status
                break
            elif status in ("FAILED",):
                raise RuntimeError(f"TikTok publish failed: {status_data}")
            # PROCESSING_DOWNLOAD, PROCESSING_UPLOAD, etc. → keep polling

        console.print()

        if not final_status:
            raise RuntimeError(f"TikTok publish timed out after {POLL_MAX_TRIES * POLL_INTERVAL}s")

        # Map TikTok status to our internal status
        if final_status == "SEND_TO_USER_INBOX":
            our_status = "draft_uploaded"
        elif "scheduled_publish_time" in post_info:
            our_status = "scheduled"
        else:
            our_status = "published"

        return {
            "status":     our_status,
            "publish_id": publish_id,
            "url":        None,  # TikTok doesn't return URL directly; visible in Creator Studio
            "mode":       mode,
        }

    def authenticate(self) -> bool:
        """
        Launch the TikTok OAuth2 flow in the browser.
        Requires TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET in .env.
        """
        client_key    = os.getenv("TIKTOK_CLIENT_KEY", "")
        client_secret = os.getenv("TIKTOK_CLIENT_SECRET", "")

        if not client_key or not client_secret:
            console.print("[red]Set TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET in .env first.[/red]")
            return False

        # Build the authorization URL
        import urllib.parse
        redirect_uri = "https://localhost:8080/callback"
        scope = "video.publish,video.upload"
        state = "pawfactory_auth"

        params = {
            "client_key":    client_key,
            "scope":         scope,
            "response_type": "code",
            "redirect_uri":  redirect_uri,
            "state":         state,
        }
        auth_url = AUTH_URL + "?" + urllib.parse.urlencode(params)

        console.print(f"\n[bold]Open this URL in your browser to authorize TikTok:[/bold]\n")
        console.print(f"[link]{auth_url}[/link]\n")
        console.print("[dim]After authorizing, copy the 'code' parameter from the redirect URL.[/dim]")

        code = input("\nPaste the authorization code here: ").strip()
        if not code:
            console.print("[red]No code provided.[/red]")
            return False

        # Exchange code for tokens
        resp = requests.post(TOKEN_URL, data={
            "client_key":    client_key,
            "client_secret": client_secret,
            "code":          code,
            "grant_type":    "authorization_code",
            "redirect_uri":  redirect_uri,
        }, timeout=15)

        if resp.status_code != 200:
            console.print(f"[red]Token exchange failed ({resp.status_code}): {resp.text[:200]}[/red]")
            return False

        tok_data = resp.json().get("data", {})
        if not tok_data.get("access_token"):
            console.print(f"[red]No access_token in response: {resp.json()}[/red]")
            return False

        _save_token({
            "access_token":  tok_data["access_token"],
            "refresh_token": tok_data.get("refresh_token"),
            "expires_in":    tok_data.get("expires_in"),
            "scope":         tok_data.get("scope"),
            "token_type":    tok_data.get("token_type"),
            "authed_at":     datetime.now(timezone.utc).isoformat(),
        })

        console.print(f"[green]✓ TikTok authenticated. Token saved to {_token_file()}[/green]")
        console.print(f"[dim]  Scopes: {tok_data.get('scope')}[/dim]")
        return True

    def test(self) -> bool:
        """Check that credentials are present (does not make an API call)."""
        tok = _access_token()
        if not tok:
            console.print("[red]✗ No TikTok access token configured.[/red]")
            console.print("[dim]  Set TIKTOK_ACCESS_TOKEN in .env or run --auth[/dim]")
            return False
        console.print(f"[green]✓ TikTok access token present (length {len(tok)})[/green]")
        console.print(f"[dim]  Mode: {os.getenv('TIKTOK_POST_MODE', 'DIRECT_POST')}[/dim]")
        console.print(f"[dim]  Privacy: {os.getenv('TIKTOK_PRIVACY', 'PUBLIC_TO_EVERYONE')}[/dim]")
        return True


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="TikTok publisher — standalone mode")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--auth",     action="store_true", help="Authenticate (one-time OAuth setup)")
    action.add_argument("--test",     action="store_true", help="Check credentials are configured")
    action.add_argument("--video-id", help="Upload a produced short by video ID")

    parser.add_argument("--schedule", default=None,
                        help="Schedule publish time (ISO 8601). Only for DIRECT_POST mode.")
    parser.add_argument("--mode",   default=None,
                        choices=["DIRECT_POST", "UPLOAD_TO_CREATOR_INBOX"],
                        help="Override TIKTOK_POST_MODE for this run")
    args = parser.parse_args()

    publisher = TikTokPublisher()

    if args.auth:
        ok = publisher.authenticate()
        sys.exit(0 if ok else 1)

    if args.test:
        ok = publisher.test()
        sys.exit(0 if ok else 1)

    # Upload mode
    if not publisher.is_configured():
        console.print("[red]TIKTOK_ACCESS_TOKEN not set. Run --auth first.[/red]")
        sys.exit(1)

    output_dir = Path(os.getenv("OUTPUT_DIR", "output"))
    log_dir    = Path(os.getenv("LOG_DIR", "logs"))
    vid_id     = args.video_id

    video_path    = output_dir / f"{vid_id}_final.mp4"
    metadata_path = output_dir / f"{vid_id}_metadata.json"

    if not video_path.exists():
        console.print(f"[red]Video not found: {video_path}[/red]")
        sys.exit(1)

    meta = {}
    if metadata_path.exists():
        with open(metadata_path) as f:
            meta = json.load(f)

    title = meta.get("title", vid_id)

    sched_time = None
    if args.schedule:
        from scripts.publishing.publish_queue import _parse_datetime
        sched_time = _parse_datetime(args.schedule)

    result = publisher.upload(
        video_path     = str(video_path),
        title          = title,
        scheduled_time = sched_time,
        post_mode      = args.mode,
    )

    console.print(f"\n[bold green]✓ TikTok upload complete[/bold green]")
    console.print(f"  Status:     {result['status']}")
    console.print(f"  Publish ID: {result['publish_id']}")
    console.print(f"  Mode:       {result['mode']}")
    if result["status"] == "draft_uploaded":
        console.print("[yellow]  → Open TikTok Studio → Drafts to finalize publishing[/yellow]")


if __name__ == "__main__":
    main()
