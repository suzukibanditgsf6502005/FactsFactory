#!/usr/bin/env python3
"""
youtube_uploader.py — PawFactory YouTube Data API v3 client

Uploads produced shorts to YouTube with metadata and optional scheduling.

OAuth2 setup (one-time):
  python scripts/publishing/youtube_uploader.py --auth

Usage (direct):
  python scripts/publishing/youtube_uploader.py --video-id 31xxxx
  python scripts/publishing/youtube_uploader.py --video-id 31xxxx --schedule "2026-04-03T18:00:00"

Credentials:
  YOUTUBE_CLIENT_SECRETS  — path to OAuth2 client_secrets.json from Google Cloud Console
                            (default: ~/.pawfactory_yt_secrets.json)
  YOUTUBE_TOKEN_FILE      — where to store the OAuth2 token (default: ~/.pawfactory_yt_token.json)

Setup:
  1. Go to https://console.cloud.google.com/apis/credentials
  2. Create an OAuth2 client (type: Desktop app)
  3. Enable YouTube Data API v3 in the project
  4. Download the JSON → save as ~/.pawfactory_yt_secrets.json
  5. Run: python scripts/publishing/youtube_uploader.py --auth
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
console = Console()

# ── Optional dependency guard ─────────────────────────────────────────────────
try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    import google.oauth2.credentials
    YOUTUBE_AVAILABLE = True
except ImportError:
    YOUTUBE_AVAILABLE = False

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

DEFAULT_SECRETS_PATH = Path.home() / ".pawfactory_yt_secrets.json"
DEFAULT_TOKEN_PATH   = Path.home() / ".pawfactory_yt_token.json"

# ── Language defaults ─────────────────────────────────────────────────────────
# defaultAudioLanguage  — spoken language of the video track (BCP-47)
# TEXT_LANGUAGE         — language of title + description (snippet.defaultLanguage)
AUDIO_LANGUAGE = "en-US"
TEXT_LANGUAGE  = "en-US"

# ── URL stripping ─────────────────────────────────────────────────────────────
# Pattern matches: http(s):// URLs, www. URLs, and bare known-platform domains.
# Applied to every description before it reaches the YouTube API.
_URL_RE = re.compile(
    r"https?://\S+"
    r"|www\.\S+"
    r"|\b(?:youtube\.com|youtu\.be|tiktok\.com|instagram\.com"
    r"|reddit\.com|x\.com|twitter\.com)\S*",
    re.IGNORECASE,
)


def _strip_urls(text: str) -> str:
    """
    Remove all URLs from a description string.
    Preserves plain-text credit lines (e.g. "Credit: Original creator").
    Collapses consecutive blank lines left after removal.
    """
    cleaned = _URL_RE.sub("", text)
    lines = cleaned.splitlines()
    result: list[str] = []
    prev_blank = False
    for line in lines:
        line = line.rstrip()
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue   # drop extra blank lines
        result.append(line)
        prev_blank = is_blank
    return "\n".join(result).strip()


def _secrets_path() -> Path:
    p = os.getenv("YOUTUBE_CLIENT_SECRETS", str(DEFAULT_SECRETS_PATH))
    return Path(p).expanduser()


def _token_path() -> Path:
    p = os.getenv("YOUTUBE_TOKEN_FILE", str(DEFAULT_TOKEN_PATH))
    return Path(p).expanduser()


class YouTubeUploader:
    def __init__(self):
        self._service = None

    def is_configured(self) -> bool:
        """Return True if client secrets file exists (required for OAuth)."""
        return _secrets_path().exists()

    def _get_credentials(self):
        """Load or refresh OAuth2 credentials. Raises if not authenticated."""
        if not YOUTUBE_AVAILABLE:
            raise RuntimeError("google-api-python-client not installed. Run: pip install google-api-python-client google-auth-oauthlib")

        creds = None
        token_p = _token_path()

        if token_p.exists():
            creds = google.oauth2.credentials.Credentials.from_authorized_user_file(
                str(token_p), SCOPES
            )

        if creds and creds.valid:
            return creds

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _save_token(creds)
            return creds

        raise RuntimeError(
            "YouTube credentials not found or expired.\n"
            "Run: python scripts/publishing/youtube_uploader.py --auth"
        )

    def _get_service(self):
        if self._service is None:
            creds = self._get_credentials()
            self._service = build("youtube", "v3", credentials=creds)
        return self._service

    def authenticate(self):
        """
        Launch the OAuth2 browser flow and save credentials.
        Run once to set up. Token auto-refreshes afterwards.
        """
        if not YOUTUBE_AVAILABLE:
            console.print("[red]Install dependencies first: pip install google-api-python-client google-auth-oauthlib[/red]")
            return False

        secrets_p = _secrets_path()
        if not secrets_p.exists():
            console.print(f"[red]Client secrets not found: {secrets_p}[/red]")
            console.print("[dim]Download from: https://console.cloud.google.com/apis/credentials[/dim]")
            console.print(f"[dim]Save to: {secrets_p}[/dim]")
            return False

        flow = InstalledAppFlow.from_client_secrets_file(str(secrets_p), SCOPES)

        # Use console (copy-paste) flow — works on headless servers and VMs.
        # The user visits the URL in any browser, grants access, pastes the code back.
        flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
        auth_url, _ = flow.authorization_url(prompt="consent")

        console.print("\n[bold]Open this URL in a browser:[/bold]\n")
        console.print(f"  {auth_url}\n")
        console.print("[dim]Sign in with the Google account that owns the YouTube channel.[/dim]")
        console.print("[dim]After granting access, Google will show a code — paste it below.[/dim]\n")

        code = input("Paste the authorization code: ").strip()
        if not code:
            console.print("[red]No code entered — auth cancelled.[/red]")
            return False

        flow.fetch_token(code=code)
        creds = flow.credentials
        _save_token(creds)
        console.print(f"[green]✓ YouTube authenticated. Token saved to {_token_path()}[/green]")
        return True

    def upload(
        self,
        video_path: str,
        title: str,
        description: str = "",
        tags: list[str] | None = None,
        category_id: str = "15",
        scheduled_time: datetime | None = None,
        made_for_kids: bool = False,
    ) -> dict:
        """
        Upload a video to YouTube.

        If scheduled_time is None → publishes immediately (public).
        If scheduled_time is set  → uploads as private, auto-publishes at that time.

        Returns: {"video_id": str, "url": str, "status": str}
        """
        service = self._get_service()

        # Determine privacy and scheduling
        if scheduled_time:
            # YouTube requires UTC ISO 8601 for publishAt
            if scheduled_time.tzinfo is None:
                scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)
            publish_at = scheduled_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            privacy = "private"  # YouTube publishes private+publishAt automatically
        else:
            publish_at = None
            privacy = "public"

        # Strip URLs from description before sending — never include links.
        clean_description = _strip_urls(description)

        body = {
            "snippet": {
                "title":                title[:100],            # YouTube title max 100 chars
                "description":          clean_description[:5000],
                "tags":                 (tags or [])[:500],
                "categoryId":           category_id,
                "defaultLanguage":      TEXT_LANGUAGE,          # title/description language
                "defaultAudioLanguage": AUDIO_LANGUAGE,         # spoken audio language
            },
            "status": {
                "privacyStatus": privacy,
                "madeForKids":   made_for_kids,
                "selfDeclaredMadeForKids": made_for_kids,
            },
        }

        if publish_at:
            body["status"]["publishAt"] = publish_at

        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=10 * 1024 * 1024,  # 10 MB chunks
        )

        console.print(f"  [dim]Uploading to YouTube ({Path(video_path).stat().st_size / 1024 / 1024:.1f} MB)...[/dim]")

        request = service.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                console.print(f"  [dim]  upload {pct}%...[/dim]", end="\r")

        video_id = response["id"]
        url = f"https://www.youtube.com/shorts/{video_id}"

        return {
            "video_id": video_id,
            "url":      url,
            "status":   "scheduled" if scheduled_time else "published",
        }


def _save_token(creds):
    token_p = _token_path()
    with open(token_p, "w") as f:
        f.write(creds.to_json())
    token_p.chmod(0o600)  # restrict permissions


# ── CLI entry point (standalone) ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="YouTube uploader — standalone mode")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--auth",     action="store_true", help="Authenticate (one-time setup)")
    action.add_argument("--video-id", help="Upload a specific produced short by ID")

    parser.add_argument("--schedule", default=None,
                        help="Schedule publish time (ISO 8601), e.g. 2026-04-03T18:00:00")
    parser.add_argument("--title",    default=None, help="Override title")
    args = parser.parse_args()

    uploader = YouTubeUploader()

    if args.auth:
        ok = uploader.authenticate()
        sys.exit(0 if ok else 1)

    # Upload mode
    if not YOUTUBE_AVAILABLE:
        console.print("[red]Install: pip install google-api-python-client google-auth-oauthlib[/red]")
        sys.exit(1)

    if not uploader.is_configured():
        console.print(f"[red]Client secrets not found: {_secrets_path()}[/red]")
        sys.exit(1)

    output_dir = Path(os.getenv("OUTPUT_DIR", "output"))
    log_dir    = Path(os.getenv("LOG_DIR", "logs"))
    vid_id     = args.video_id

    video_path    = output_dir / f"{vid_id}_final.mp4"
    metadata_path = output_dir / f"{vid_id}_metadata.json"

    if not video_path.exists():
        console.print(f"[red]Video not found: {video_path}[/red]")
        sys.exit(1)

    # Load metadata
    meta = {}
    if metadata_path.exists():
        with open(metadata_path) as f:
            meta = json.load(f)

    title       = args.title or meta.get("title", vid_id)
    description = meta.get("description", "")
    tags        = meta.get("tags", [])
    category_id = meta.get("category_id", "15")

    sched_time = None
    if args.schedule:
        from scripts.publishing.publish_queue import _parse_datetime
        sched_time = _parse_datetime(args.schedule)

    result = uploader.upload(
        video_path     = str(video_path),
        title          = title,
        description    = description,
        tags           = tags,
        category_id    = category_id,
        scheduled_time = sched_time,
    )

    console.print(f"\n[bold green]✓ YouTube upload complete[/bold green]")
    console.print(f"  Video ID: {result['video_id']}")
    console.print(f"  URL:      {result['url']}")
    console.print(f"  Status:   {result['status']}")


if __name__ == "__main__":
    main()
