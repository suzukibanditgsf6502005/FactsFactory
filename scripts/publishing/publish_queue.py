#!/usr/bin/env python3
"""
publish_queue.py — PawFactory publishing queue manager

Manages the review → approval → publishing workflow for produced shorts.

Queue states (overall item):
  pending_review  — produced, awaiting human decision
  approved        — human approved; ready to publish or schedule
  rejected        — human rejected; will not publish
  deferred        — skip for now; revisit later
  published       — live on at least one platform (per-platform details below)
  failed          — all enabled platform uploads failed

Per-platform states (youtube / tiktok sub-objects):
  pending         — not yet attempted
  scheduled       — API call made; will go live at scheduled_time automatically
  published       — live now
  draft_uploaded  — in TikTok Creator Inbox (UPLOAD_TO_CREATOR_INBOX mode); manual finalize needed
  failed          — upload attempt failed
  skipped         — credentials not configured; platform disabled

Usage:
  python scripts/publishing/publish_queue.py --list
  python scripts/publishing/publish_queue.py --show 31xxxx
  python scripts/publishing/publish_queue.py --approve 31xxxx
  python scripts/publishing/publish_queue.py --reject 31xxxx [--reason "text"]
  python scripts/publishing/publish_queue.py --defer 31xxxx
  python scripts/publishing/publish_queue.py --schedule 31xxxx --youtube "2026-04-03T18:00:00"
  python scripts/publishing/publish_queue.py --schedule 31xxxx --youtube "..." --tiktok "..."
  python scripts/publishing/publish_queue.py --publish-ready [--dry-run]
  python scripts/publishing/publish_queue.py --enqueue 31xxxx
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:          # Python < 3.9 — pip install tzdata backports.zoneinfo
    from backports.zoneinfo import ZoneInfo

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich import box

load_dotenv()
console = Console()

QUEUE_DIR_DEFAULT = "logs/publish_queue"

# ── Slot allocator ────────────────────────────────────────────────────────────
#
# Fixed daily publish schedule.  YouTube scheduling is the source of truth.
# TikTok stores the same desired time regardless of post mode (the TikTok
# publisher ignores it automatically in UPLOAD_TO_CREATOR_INBOX mode).

PUBLISH_TZ    = ZoneInfo("America/New_York")
PUBLISH_SLOTS = [(12, 30), (16, 30), (20, 30)]   # (hour, minute) in ET
SLOT_MIN_AHEAD_MINS = 20   # a slot must be at least this many minutes from now
TIKTOK_OFFSET_HOURS = 2    # TikTok desired time = YouTube slot + this offset


def _occupied_youtube_slots(items: list[dict]) -> list[datetime]:
    """
    Return all YouTube scheduled_times from active (non-rejected/non-failed) items,
    converted to ET, sorted ascending.
    """
    slots = []
    for item in items:
        if item["state"] in ("rejected", "failed"):
            continue
        yt_sched = item["youtube"].get("scheduled_time")
        if yt_sched:
            try:
                dt = _parse_datetime(yt_sched).astimezone(PUBLISH_TZ)
                slots.append(dt)
            except (ValueError, Exception):
                pass
    slots.sort()
    return slots


def _next_slot_after(pivot: datetime | None) -> datetime:
    """
    Return the earliest fixed slot that is strictly after `pivot` AND at least
    SLOT_MIN_AHEAD_MINS from now.

    If pivot is None, find the earliest slot at least SLOT_MIN_AHEAD_MINS from now.
    """
    now     = datetime.now(PUBLISH_TZ)
    min_dt  = now + timedelta(minutes=SLOT_MIN_AHEAD_MINS)

    if pivot is None:
        earliest = min_dt
    else:
        pivot_et = pivot.astimezone(PUBLISH_TZ)
        # Must be strictly after pivot AND after the minimum-from-now guard
        earliest = max(pivot_et, min_dt)

    # Walk forward through days until a slot is found
    check_date = earliest.date()
    for _ in range(21):   # safety: at most 3 weeks forward
        for h, m in PUBLISH_SLOTS:
            slot_dt = datetime(
                check_date.year, check_date.month, check_date.day,
                h, m, 0, tzinfo=PUBLISH_TZ,
            )
            if slot_dt > earliest:
                return slot_dt
        check_date += timedelta(days=1)

    raise RuntimeError("Could not find an available slot within 21 days — check PUBLISH_SLOTS config")


def assign_next_slot(all_items: list[dict]) -> datetime:
    """
    Return the next available YouTube publish slot, taking into account all
    already-assigned slots across the queue.  Logs the reasoning so operators
    can see why a particular slot was chosen.
    """
    occupied = _occupied_youtube_slots(all_items)
    pivot    = occupied[-1] if occupied else None

    if pivot:
        console.print(
            f"  [dim]Last occupied slot: {pivot.strftime('%a %Y-%m-%d %H:%M %Z')}  "
            f"({len(occupied)} slot(s) already assigned)[/dim]"
        )
    else:
        console.print("  [dim]No slots currently assigned — searching from now[/dim]")

    slot = _next_slot_after(pivot)
    console.print(
        f"  [dim]Auto-assigned slot: {slot.strftime('%a %Y-%m-%d %H:%M %Z')}[/dim]"
    )
    return slot


# ── Queue item helpers ────────────────────────────────────────────────────────

def _queue_dir() -> Path:
    d = Path(os.getenv("LOG_DIR", "logs")) / "publish_queue"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _queue_path(video_id: str) -> Path:
    return _queue_dir() / f"{video_id}.json"


def _load_item(video_id: str) -> dict | None:
    p = _queue_path(video_id)
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)


def _save_item(item: dict):
    p = _queue_path(item["video_id"])
    with open(p, "w") as f:
        json.dump(item, f, indent=2, ensure_ascii=False)


def _all_items() -> list[dict]:
    items = []
    for p in sorted(_queue_dir().glob("*.json")):
        with open(p) as f:
            items.append(json.load(f))
    return items


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _platform_stub() -> dict:
    return {
        "scheduled_time": None,
        "video_id": None,
        "url": None,
        "published_at": None,
        "status": "pending",
        "error": None,
    }


def _tiktok_stub() -> dict:
    return {
        "scheduled_time": None,
        "publish_id": None,
        "url": None,
        "published_at": None,
        "status": "pending",
        "mode": None,
        "error": None,
    }


# ── Enqueue ───────────────────────────────────────────────────────────────────

def enqueue(video_id: str, force: bool = False) -> dict | None:
    """
    Add a produced short to the review queue.
    Reads output/{id}_final.mp4, output/{id}_metadata.json, logs/qc/{id}_qc.json.
    Returns the created/updated queue item, or None if video file is missing.
    """
    existing = _load_item(video_id)
    if existing and not force:
        console.print(f"[yellow]{video_id} already in queue (state: {existing['state']}). Use --force to re-enqueue.[/yellow]")
        return existing

    output_dir = Path(os.getenv("OUTPUT_DIR", "output"))
    log_dir    = Path(os.getenv("LOG_DIR", "logs"))

    video_path    = output_dir / f"{video_id}_final.mp4"
    metadata_path = output_dir / f"{video_id}_metadata.json"
    qc_path       = log_dir / "qc" / f"{video_id}_qc.json"

    if not video_path.exists():
        console.print(f"[red]ERROR: Video file not found: {video_path}[/red]")
        return None

    # Load metadata for title preview
    title = video_id
    if metadata_path.exists():
        with open(metadata_path) as f:
            meta = json.load(f)
        title = meta.get("title", video_id)

    # Load QC result
    qc_score   = None
    qc_verdict = None
    if qc_path.exists():
        with open(qc_path) as f:
            qc = json.load(f)
        qc_score   = qc.get("weighted_score")
        qc_verdict = qc.get("verdict")

    state = "pending_review"

    item = {
        "video_id":      video_id,
        "state":         state,
        "video_path":    str(video_path),
        "metadata_path": str(metadata_path) if metadata_path.exists() else None,
        "qc_path":       str(qc_path) if qc_path.exists() else None,
        "qc_score":      qc_score,
        "qc_verdict":    qc_verdict,
        "title":         title,
        "queued_at":     _now_iso(),
        "reviewed_at":   None,
        "rejection_reason": None,
        "youtube": _platform_stub(),
        "tiktok":  _tiktok_stub(),
    }

    _save_item(item)
    console.print(f"[green]✓ Enqueued {video_id} → pending_review[/green]  QC: {qc_verdict or 'not run'} ({qc_score or '—'})")
    return item


# ── State transitions ─────────────────────────────────────────────────────────

def approve(video_id: str) -> bool:
    item = _load_item(video_id)
    if not item:
        console.print(f"[red]{video_id} not found in queue. Run --enqueue first.[/red]")
        return False
    if item["state"] in ("published", "scheduled"):
        console.print(f"[yellow]{video_id} is already {item['state']} — cannot re-approve.[/yellow]")
        return False
    item["state"]            = "approved"
    item["reviewed_at"]      = _now_iso()
    item["rejection_reason"] = None

    # Auto-assign next available publish slot unless one is already set manually
    if not item["youtube"].get("scheduled_time"):
        all_items = _all_items()
        # Include the current item (with updated state) so its slot is not re-used
        all_items = [i if i["video_id"] != video_id else item for i in all_items]
        slot = assign_next_slot(all_items)
        item["youtube"]["scheduled_time"] = slot.isoformat()

        # TikTok: store desired time (TIKTOK_OFFSET_HOURS after YouTube slot).
        # In DIRECT_POST mode the publisher will schedule at this time.
        # In UPLOAD_TO_CREATOR_INBOX mode it's stored as metadata only.
        if not item["tiktok"].get("scheduled_time"):
            ttk_slot = slot + timedelta(hours=TIKTOK_OFFSET_HOURS)
            item["tiktok"]["scheduled_time"] = ttk_slot.isoformat()
            mode = os.getenv("TIKTOK_POST_MODE", "UPLOAD_TO_CREATOR_INBOX")
            ttk_note = "desired time stored" if mode == "UPLOAD_TO_CREATOR_INBOX" else "scheduled"
            console.print(
                f"  [dim]TikTok {ttk_note}: "
                f"{ttk_slot.astimezone(PUBLISH_TZ).strftime('%a %Y-%m-%d %H:%M %Z')}[/dim]"
            )
    else:
        console.print(
            f"  [dim]YouTube slot already set: "
            f"{_parse_datetime(item['youtube']['scheduled_time']).astimezone(PUBLISH_TZ).strftime('%a %Y-%m-%d %H:%M %Z')}"
            f"  (keeping)[/dim]"
        )

    _save_item(item)
    console.print(f"[green]✓ {video_id} approved[/green]")
    return True


def reject(video_id: str, reason: str = "") -> bool:
    item = _load_item(video_id)
    if not item:
        console.print(f"[red]{video_id} not found in queue.[/red]")
        return False
    if item["state"] == "published":
        console.print(f"[yellow]{video_id} is already published — cannot reject.[/yellow]")
        return False
    item["state"]            = "rejected"
    item["reviewed_at"]      = _now_iso()
    item["rejection_reason"] = reason or None
    _save_item(item)
    console.print(f"[dim]✗ {video_id} rejected{' — ' + reason if reason else ''}[/dim]")
    return True


def defer(video_id: str) -> bool:
    item = _load_item(video_id)
    if not item:
        console.print(f"[red]{video_id} not found in queue.[/red]")
        return False
    item["state"]       = "deferred"
    item["reviewed_at"] = _now_iso()
    _save_item(item)
    console.print(f"[yellow]→ {video_id} deferred[/yellow]")
    return True


def schedule(video_id: str, youtube_time: str | None = None, tiktok_time: str | None = None) -> bool:
    """
    Set scheduled publish times for one or both platforms.
    Times are ISO 8601 strings (local or with timezone offset).
    The item must be in 'approved', 'pending_review', or 'deferred' state.
    After scheduling, state becomes 'approved' (execution happens on --publish-ready).
    """
    item = _load_item(video_id)
    if not item:
        console.print(f"[red]{video_id} not found in queue.[/red]")
        return False

    if item["state"] in ("rejected", "published"):
        console.print(f"[yellow]{video_id} is {item['state']} — cannot schedule.[/yellow]")
        return False

    if youtube_time:
        # Parse and normalise to UTC ISO 8601
        try:
            dt = _parse_datetime(youtube_time)
        except ValueError as e:
            console.print(f"[red]Invalid --youtube time: {e}[/red]")
            return False
        item["youtube"]["scheduled_time"] = dt.isoformat()
        console.print(f"  YouTube scheduled: {dt.isoformat()}")

    if tiktok_time:
        try:
            dt = _parse_datetime(tiktok_time)
        except ValueError as e:
            console.print(f"[red]Invalid --tiktok time: {e}[/red]")
            return False
        item["tiktok"]["scheduled_time"] = dt.isoformat()
        console.print(f"  TikTok scheduled: {dt.isoformat()}")

    # Auto-approve if still in pending/deferred
    if item["state"] in ("pending_review", "deferred"):
        item["state"] = "approved"
        item["reviewed_at"] = _now_iso()
        console.print(f"  [dim](state promoted to approved)[/dim]")

    _save_item(item)
    console.print(f"[green]✓ {video_id} schedule set[/green]")
    return True


def _parse_datetime(s: str) -> datetime:
    """Parse an ISO 8601 string to an aware datetime (UTC)."""
    # Try with timezone info first
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {s!r}. Use ISO 8601, e.g. 2026-04-03T18:00:00")


# ── Publishing execution ──────────────────────────────────────────────────────

def publish_ready(dry_run: bool = False) -> int:
    """
    Execute platform API calls for all items in 'approved' state.
    Items with platform.status = 'pending' get uploaded.
    Returns count of successfully published items.
    """
    import importlib.util, sys as _sys
    _here = Path(__file__).resolve().parent
    _root = _here.parent.parent
    if str(_root) not in _sys.path:
        _sys.path.insert(0, str(_root))
    from scripts.publishing.youtube_uploader import YouTubeUploader, YOUTUBE_AVAILABLE
    from scripts.publishing.tiktok_publisher  import TikTokPublisher, TIKTOK_AVAILABLE

    all_queue = _all_items()
    items = [i for i in all_queue if i["state"] in ("approved", "scheduled")]

    if not items:
        console.print("[yellow]No approved items in queue.[/yellow]")
        return 0

    console.print(f"[cyan]Publishing {len(items)} approved item(s){'  [DRY RUN]' if dry_run else ''}...[/cyan]")

    if dry_run:
        # ── Slot summary header ───────────────────────────────────────────────
        console.print(f"[dim]Timezone: {PUBLISH_TZ.key}  |  Slots: "
                      f"{', '.join(f'{h:02d}:{m:02d}' for h, m in PUBLISH_SLOTS)} ET[/dim]")
        occupied = _occupied_youtube_slots(all_queue)
        if occupied:
            console.print("[dim]Occupied YouTube slots:[/dim]")
            id_by_slot = {}
            for qi in all_queue:
                yt_t = qi["youtube"].get("scheduled_time")
                if yt_t:
                    try:
                        dt_key = _parse_datetime(yt_t).astimezone(PUBLISH_TZ).isoformat()
                        id_by_slot[dt_key] = qi["video_id"]
                    except Exception:
                        pass
            for slot_dt in occupied:
                vid = id_by_slot.get(slot_dt.isoformat(), "?")
                console.print(
                    f"  [dim]{slot_dt.strftime('%a %Y-%m-%d %H:%M %Z')}  ← {vid}[/dim]"
                )
        else:
            console.print("[dim]No YouTube slots currently assigned.[/dim]")
        console.print()

    yt  = YouTubeUploader()  if YOUTUBE_AVAILABLE else None
    ttk = TikTokPublisher()

    published = 0

    for item in items:
        vid_id = item["video_id"]
        console.print(f"[bold]→ {vid_id}[/bold]  {item['title'][:60]}")

        video_path = Path(item["video_path"])
        if not video_path.exists():
            console.print(f"  [red]✗ Video file missing: {video_path}[/red]")
            item["state"] = "failed"
            _save_item(item)
            continue

        # Load full metadata
        metadata = {}
        if item.get("metadata_path") and Path(item["metadata_path"]).exists():
            with open(item["metadata_path"]) as f:
                metadata = json.load(f)

        any_success = False

        # ── YouTube ──────────────────────────────────────────────────────────
        # Guard: skip if already uploaded (video_id set means it was uploaded,
        # even if status was left as "pending" due to manual queue edits).
        if item["youtube"].get("video_id") and item["youtube"]["status"] == "pending":
            item["youtube"]["status"] = "published"
            if not dry_run:
                _save_item(item)
            console.print(f"  YouTube: [dim]already uploaded ({item['youtube']['video_id']}) — skipped[/dim]")
        elif item["youtube"]["status"] == "pending":
            if dry_run:
                cred_ok = YOUTUBE_AVAILABLE and yt is not None and yt.is_configured()
                title_preview = metadata.get("title", vid_id)[:46]
                yt_sched_raw = item["youtube"].get("scheduled_time")
                if yt_sched_raw:
                    try:
                        yt_dt_et = _parse_datetime(yt_sched_raw).astimezone(PUBLISH_TZ)
                        sched_label = f" @ {yt_dt_et.strftime('%a %Y-%m-%d %H:%M %Z')} (auto-slot)"
                    except Exception:
                        sched_label = f" @ {yt_sched_raw}"
                else:
                    sched_label = " [immediately — no slot assigned]"
                cred_label = "" if cred_ok else "  [dim](no credentials)[/dim]"
                console.print(f"  YouTube: [dim]would upload '{title_preview}'{sched_label}[/dim]{cred_label}")
            elif not YOUTUBE_AVAILABLE:
                item["youtube"]["status"] = "skipped"
                item["youtube"]["error"]  = "google-api-python-client not installed"
                console.print("  YouTube: [dim]skipped (library not available)[/dim]")
            elif yt is None or not yt.is_configured():
                item["youtube"]["status"] = "skipped"
                item["youtube"]["error"]  = "YOUTUBE_CLIENT_SECRETS not configured"
                console.print("  YouTube: [dim]skipped (credentials not configured)[/dim]")
            else:
                yt_result = _upload_youtube(yt, item, metadata, video_path)
                item["youtube"].update(yt_result)
                if yt_result["status"] in ("published", "scheduled"):
                    any_success = True
                    console.print(f"  YouTube: [green]✓ {yt_result['status']}[/green]  {yt_result.get('url', '')}")
                else:
                    console.print(f"  YouTube: [red]✗ failed — {yt_result.get('error', 'unknown')}[/red]")

        # ── TikTok ───────────────────────────────────────────────────────────
        # Guard: skip if already uploaded (publish_id set).
        if item["tiktok"].get("publish_id") and item["tiktok"]["status"] == "pending":
            item["tiktok"]["status"] = "published"
            if not dry_run:
                _save_item(item)
            console.print(f"  TikTok:  [dim]already uploaded ({item['tiktok']['publish_id']}) — skipped[/dim]")
        elif item["tiktok"]["status"] == "pending":
            if dry_run:
                mode = os.getenv("TIKTOK_POST_MODE", "UPLOAD_TO_CREATOR_INBOX")
                ttk_sched_raw = item["tiktok"].get("scheduled_time")
                if ttk_sched_raw:
                    try:
                        ttk_dt_et = _parse_datetime(ttk_sched_raw).astimezone(PUBLISH_TZ)
                        ttk_time_str = ttk_dt_et.strftime("%a %Y-%m-%d %H:%M %Z")
                    except Exception:
                        ttk_time_str = ttk_sched_raw
                    if mode == "UPLOAD_TO_CREATOR_INBOX":
                        sched_label = f" @ {ttk_time_str} (desired — stored, not scheduled; finalize in TikTok Studio)"
                    else:
                        sched_label = f" @ {ttk_time_str} (scheduled)"
                else:
                    sched_label = ""
                cred_label = "" if ttk.is_configured() else "  [dim](no credentials)[/dim]"
                console.print(f"  TikTok:  [dim]would upload (mode: {mode}){sched_label}[/dim]{cred_label}")
            elif not ttk.is_configured():
                item["tiktok"]["status"] = "skipped"
                item["tiktok"]["error"]  = "TIKTOK_ACCESS_TOKEN not configured"
                console.print("  TikTok:  [dim]skipped (credentials not configured)[/dim]")
            else:
                ttk_result = _upload_tiktok(ttk, item, metadata, video_path)
                item["tiktok"].update(ttk_result)
                if ttk_result["status"] in ("published", "scheduled", "draft_uploaded"):
                    any_success = True
                    status_label = {
                        "published":      "[green]✓ published[/green]",
                        "scheduled":      "[green]✓ scheduled[/green]",
                        "draft_uploaded": "[yellow]→ draft uploaded (manual finalize needed)[/yellow]",
                    }.get(ttk_result["status"], ttk_result["status"])
                    console.print(f"  TikTok:  {status_label}")
                else:
                    console.print(f"  TikTok:  [red]✗ failed — {ttk_result.get('error', 'unknown')}[/red]")

        # Update overall state and persist (only in live mode)
        if not dry_run:
            yt_s  = item["youtube"]["status"]
            ttk_s = item["tiktok"]["status"]

            active_statuses = {yt_s, ttk_s} - {"skipped"}
            if not active_statuses:
                # All platforms skipped — nothing changed
                pass
            elif active_statuses <= {"published", "scheduled", "draft_uploaded", "skipped"}:
                item["state"] = "published"
                published += 1
            elif all(s == "failed" for s in active_statuses):
                item["state"] = "failed"
            else:
                # Mixed: at least one succeeded
                item["state"] = "published"
                published += 1

            _save_item(item)
        console.print()

    if not dry_run:
        console.print(f"[green]Done — {published}/{len(items)} published[/green]")
    return published


def _upload_youtube(yt, item: dict, metadata: dict, video_path: Path) -> dict:
    """Call the YouTube uploader and return a status dict."""
    result = {"status": "failed", "video_id": None, "url": None,
              "published_at": None, "error": None}
    try:
        sched_time = None
        if item["youtube"].get("scheduled_time"):
            sched_time = _parse_datetime(item["youtube"]["scheduled_time"])

        yt_result = yt.upload(
            video_path   = str(video_path),
            title        = metadata.get("title", item["title"]),
            description  = metadata.get("description", ""),
            tags         = metadata.get("tags", []),
            category_id  = metadata.get("category_id", "15"),
            scheduled_time = sched_time,
        )

        result["video_id"]     = yt_result.get("video_id")
        result["url"]          = yt_result.get("url")
        result["published_at"] = _now_iso()
        result["status"]       = "scheduled" if sched_time else "published"

    except Exception as e:
        result["error"] = str(e)
    return result


def _upload_tiktok(ttk, item: dict, metadata: dict, video_path: Path) -> dict:
    """Call the TikTok publisher and return a status dict."""
    result = {"status": "failed", "publish_id": None, "url": None,
              "published_at": None, "mode": None, "error": None}
    try:
        sched_time = None
        if item["tiktok"].get("scheduled_time"):
            sched_time = _parse_datetime(item["tiktok"]["scheduled_time"])

        ttk_result = ttk.upload(
            video_path     = str(video_path),
            title          = metadata.get("title", item["title"]),
            scheduled_time = sched_time,
        )

        result["publish_id"]   = ttk_result.get("publish_id")
        result["url"]          = ttk_result.get("url")
        result["published_at"] = _now_iso()
        result["mode"]         = ttk_result.get("mode")
        result["status"]       = ttk_result.get("status", "failed")

    except Exception as e:
        result["error"] = str(e)
    return result


# ── Display ───────────────────────────────────────────────────────────────────

STATE_STYLE = {
    "pending_review": "yellow",
    "approved":       "cyan",
    "rejected":       "dim",
    "deferred":       "dim",
    "scheduled":      "blue",
    "published":      "green",
    "failed":         "red",
}

PLATFORM_STYLE = {
    "pending":        "dim",
    "scheduled":      "blue",
    "published":      "green",
    "draft_uploaded": "yellow",
    "failed":         "red",
    "skipped":        "dim",
}


def cmd_list(state_filter: str | None = None):
    items = _all_items()
    if not items:
        console.print("[dim]Queue is empty.[/dim]")
        return

    if state_filter:
        items = [i for i in items if i["state"] == state_filter]
        if not items:
            console.print(f"[dim]No items with state '{state_filter}'.[/dim]")
            return
    else:
        # Hide rejected items by default — use --state rejected to see them
        items = [i for i in items if i["state"] != "rejected"]

    # Column widths
    W_ID    = 10
    W_STATE = 16
    W_QC    = 9
    W_YT    = 16
    W_TTK   = 16
    W_TITLE = 46

    def _row(vid_id, state, qc, yt, ttk, title):
        return (
            f"{vid_id:<{W_ID}}  {state:<{W_STATE}}  {qc:<{W_QC}}"
            f"  {yt:<{W_YT}}  {ttk:<{W_TTK}}  {title:<{W_TITLE}}"
        )

    header = _row("ID", "State", "QC", "YouTube", "TikTok", "Title")
    print(header)
    print("─" * len(header))

    for item in items:
        state      = item["state"]
        qc_verdict = item.get("qc_verdict") or "—"
        qc_score   = item.get("qc_score")
        qc_plain   = f"{qc_verdict[:4]} {qc_score:.1f}" if qc_score else qc_verdict[:4]

        yt_s  = item["youtube"]["status"]
        ttk_s = item["tiktok"]["status"]

        yt_label = yt_s
        yt_sched_raw = item["youtube"].get("scheduled_time")
        if yt_sched_raw:
            try:
                yt_et = _parse_datetime(yt_sched_raw).astimezone(PUBLISH_TZ)
                yt_label = yt_et.strftime("%-m/%-d %H:%M ET")
            except Exception:
                yt_label = "sched " + yt_sched_raw[5:16]

        ttk_label = ttk_s
        ttk_sched_raw = item["tiktok"].get("scheduled_time")
        if ttk_s == "draft_uploaded":
            ttk_label = "draft→manual"
        elif ttk_sched_raw:
            try:
                ttk_et = _parse_datetime(ttk_sched_raw).astimezone(PUBLISH_TZ)
                ttk_label = ttk_et.strftime("%-m/%-d %H:%M ET")
            except Exception:
                ttk_label = "sched " + ttk_sched_raw[5:16]

        title_short = item["title"][:W_TITLE - 1] + ("…" if len(item["title"]) >= W_TITLE else "")

        print(_row(item["video_id"], state, qc_plain, yt_label, ttk_label, title_short))

    print(f"\n{len(items)} item(s) total")


def cmd_show(video_id: str):
    item = _load_item(video_id)
    if not item:
        console.print(f"[red]{video_id} not found in queue.[/red]")
        return

    from rich.panel import Panel
    from rich.text  import Text

    lines = [
        f"[bold]Video ID:[/bold]  {item['video_id']}",
        f"[bold]State:[/bold]     [{STATE_STYLE.get(item['state'], '')}]{item['state']}[/]",
        f"[bold]Title:[/bold]     {item['title']}",
        f"",
        f"[bold]QC Verdict:[/bold] {item.get('qc_verdict') or '(not run)'}  score: {item.get('qc_score') or '—'}",
        f"[bold]Video:[/bold]     {item['video_path']}",
        f"[bold]Metadata:[/bold]  {item.get('metadata_path') or '(missing)'}",
        f"",
        f"[bold]Queued:[/bold]    {item['queued_at']}",
        f"[bold]Reviewed:[/bold]  {item.get('reviewed_at') or '—'}",
    ]

    if item.get("rejection_reason"):
        lines.append(f"[bold]Rejection:[/bold] {item['rejection_reason']}")

    yt = item["youtube"]
    lines += [
        f"",
        f"[bold]YouTube[/bold]",
        f"  status:    [{PLATFORM_STYLE.get(yt['status'], '')}]{yt['status']}[/]",
    ]
    if yt.get("scheduled_time"):
        lines.append(f"  scheduled: {yt['scheduled_time']}")
    if yt.get("video_id"):
        lines.append(f"  video_id:  {yt['video_id']}")
    if yt.get("url"):
        lines.append(f"  url:       {yt['url']}")
    if yt.get("error"):
        lines.append(f"  [red]error:     {yt['error']}[/red]")

    ttk = item["tiktok"]
    lines += [
        f"",
        f"[bold]TikTok[/bold]",
        f"  status:    [{PLATFORM_STYLE.get(ttk['status'], '')}]{ttk['status']}[/]",
    ]
    if ttk.get("mode"):
        lines.append(f"  mode:      {ttk['mode']}")
    if ttk.get("scheduled_time"):
        lines.append(f"  scheduled: {ttk['scheduled_time']}")
    if ttk.get("publish_id"):
        lines.append(f"  pub_id:    {ttk['publish_id']}")
    if ttk.get("url"):
        lines.append(f"  url:       {ttk['url']}")
    if ttk.get("error"):
        lines.append(f"  [red]error:     {ttk['error']}[/red]")

    console.print(Panel("\n".join(lines), title=video_id, border_style="cyan"))


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="PawFactory Publish Queue Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  --list
  --list --state pending_review
  --show 31xxxx
  --enqueue 31xxxx
  --approve 31xxxx
  --reject 31xxxx --reason "shaky footage"
  --defer 31xxxx
  --schedule 31xxxx --youtube "2026-04-03T18:00:00"
  --schedule 31xxxx --youtube "2026-04-03T18:00:00" --tiktok "2026-04-03T20:00:00"
  --publish-ready
  --publish-ready --dry-run
""",
    )

    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--list",          action="store_true", help="List queue items")
    action.add_argument("--show",          metavar="VIDEO_ID",  help="Show full item details")
    action.add_argument("--enqueue",       metavar="VIDEO_ID",  help="Add produced short to queue")
    action.add_argument("--approve",       metavar="VIDEO_ID",  help="Approve item for publishing")
    action.add_argument("--reject",        metavar="VIDEO_ID",  help="Reject item")
    action.add_argument("--defer",         metavar="VIDEO_ID",  help="Defer item (skip for now)")
    action.add_argument("--schedule",      metavar="VIDEO_ID",  help="Set scheduled publish time(s)")
    action.add_argument("--publish-ready", action="store_true", help="Execute API calls for approved items")

    parser.add_argument("--state",   help="Filter --list by state")
    parser.add_argument("--reason",  default="",  help="Rejection reason (used with --reject)")
    parser.add_argument("--youtube", default=None, help="YouTube scheduled time (ISO 8601)")
    parser.add_argument("--tiktok",  default=None, help="TikTok scheduled time (ISO 8601)")
    parser.add_argument("--dry-run", action="store_true", help="Preview --publish-ready without calling APIs")
    parser.add_argument("--force",   action="store_true", help="Force re-enqueue even if already in queue")

    args = parser.parse_args()

    if args.list:
        cmd_list(state_filter=args.state)

    elif args.show:
        cmd_show(args.show)

    elif args.enqueue:
        enqueue(args.enqueue, force=args.force)

    elif args.approve:
        ok = approve(args.approve)
        sys.exit(0 if ok else 1)

    elif args.reject:
        ok = reject(args.reject, reason=args.reason)
        sys.exit(0 if ok else 1)

    elif args.defer:
        ok = defer(args.defer)
        sys.exit(0 if ok else 1)

    elif args.schedule:
        if not args.youtube and not args.tiktok:
            console.print("[red]--schedule requires --youtube and/or --tiktok time.[/red]")
            sys.exit(1)
        ok = schedule(args.schedule, youtube_time=args.youtube, tiktok_time=args.tiktok)
        sys.exit(0 if ok else 1)

    elif args.publish_ready:
        count = publish_ready(dry_run=args.dry_run)
        sys.exit(0 if count >= 0 else 1)


if __name__ == "__main__":
    main()
