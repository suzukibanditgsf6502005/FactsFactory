# Publishing System

> Covers the review queue, approval flow, YouTube upload, and TikTok upload.
> Code: `scripts/publishing/`
> Queue: `logs/publish_queue/`

---

## Overview

After production + QC, each short enters a **publish queue** where it waits for human review. Once approved, the operator runs one command to upload and schedule to all configured platforms.

```
Production → QC gate → publish_queue (pending_review)
                              ↓
                         Human review
                         ↓          ↓
                      approve     reject / defer
                         ↓
                  Set schedule (optional)
                         ↓
             --publish-ready → YouTube + TikTok
```

---

## Queue States

| State | Meaning |
|---|---|
| `pending_review` | Produced and enqueued; awaiting human decision |
| `approved` | Human approved; ready to publish or schedule |
| `rejected` | Human rejected; will not be published |
| `deferred` | Skipped for now; revisit later |
| `published` | Live on at least one platform |
| `failed` | All configured platform uploads failed |

### Per-platform states (youtube / tiktok sub-objects)

| Status | Meaning |
|---|---|
| `pending` | Not yet attempted |
| `scheduled` | API call made; will go live at `scheduled_time` |
| `published` | Live now |
| `draft_uploaded` | TikTok Creator Inbox only; manual finalize needed |
| `failed` | Upload attempt failed |
| `skipped` | Credentials not configured |

---

## Daily Operator Flow

### 1. Produce shorts (pipeline auto-enqueues)

```bash
python scripts/run_pipeline.py --top-n 2
```

After QC PASS, each short is automatically added to the queue as `pending_review`.

### 2. Review queue

```bash
python scripts/publishing/publish_queue.py --list
python scripts/publishing/publish_queue.py --list --state pending_review
python scripts/publishing/publish_queue.py --show 31xxxx
```

### 3. Approve or reject

```bash
python scripts/publishing/publish_queue.py --approve 31xxxx
python scripts/publishing/publish_queue.py --reject  31xxxx --reason "shaky footage"
python scripts/publishing/publish_queue.py --defer   31xxxx
```

### 4. Set publish schedule (automatic — no manual entry needed)

When you `--approve` an item, the system automatically assigns the next available
slot from the fixed daily schedule below and stores it in the queue file.

**Fixed daily slots (America/New_York):** 12:30 · 16:30 · 20:30

The allocator:
1. Reads all existing YouTube scheduled times from the queue (excluding rejected/failed)
2. Finds the latest occupied slot
3. Assigns the first slot strictly after that (wraps to the next day after 20:30)

**TikTok desired time** is auto-set to `TIKTOK_OFFSET_HOURS` (2h) after the YouTube slot.
In `UPLOAD_TO_CREATOR_INBOX` mode it is stored as metadata — use it as a reminder
when finalizing in TikTok Studio. In `DIRECT_POST` mode it is actually scheduled.

### 4b. Manual schedule override (edge cases only)

```bash
# Override YouTube slot — include timezone offset for ET clarity
python scripts/publishing/publish_queue.py --schedule 31xxxx \
  --youtube "2026-04-05T20:30:00-04:00"

# Override both platforms
python scripts/publishing/publish_queue.py --schedule 31xxxx \
  --youtube "2026-04-05T20:30:00-04:00" \
  --tiktok  "2026-04-05T22:30:00-04:00"
```

> **Note:** naive datetimes without a timezone offset (e.g. `2026-04-05T20:30:00`)
> are treated as UTC. Include `-04:00` (EDT) or `-05:00` (EST) for ET times.

### 5. Preview what would be published

```bash
python scripts/publishing/publish_queue.py --publish-ready --dry-run
```

### 6. Execute uploads

```bash
python scripts/publishing/publish_queue.py --publish-ready
```

This uploads all `approved` items to configured platforms. Results are stored in each item's queue file.

---

## Slot Allocator

The slot allocator is a small helper inside `publish_queue.py` that eliminates
manual datetime entry for normal publishing.

### How it works

```
PUBLISH_SLOTS = [12:30, 16:30, 20:30]  ET (America/New_York)
SLOT_MIN_AHEAD_MINS = 20               minimum gap from now

On --approve:
  1. Read all youtube.scheduled_time from non-rejected/non-failed queue items
  2. Find the latest occupied slot (or "now" if none)
  3. Pick the first PUBLISH_SLOTS entry that is strictly after the pivot
     AND at least SLOT_MIN_AHEAD_MINS from now
  4. Write slot to youtube.scheduled_time (ISO 8601 with ET offset)
  5. Write slot + TIKTOK_OFFSET_HOURS to tiktok.scheduled_time
```

### Slot cascading example

```
Approve 31qgcpec  → Thu 2026-04-02 12:30 EDT  (first available after now)
Approve 31s85gwk  → Thu 2026-04-02 16:30 EDT  (next after 12:30)
Approve 31s3wpyo  → Thu 2026-04-02 20:30 EDT  (next after 16:30)
Approve 31s7uf6n  → Fri 2026-04-03 12:30 EDT  (day rollover after 20:30)
```

### Configuration

All slot constants live at the top of `scripts/publishing/publish_queue.py`:

```python
PUBLISH_TZ          = ZoneInfo("America/New_York")
PUBLISH_SLOTS       = [(12, 30), (16, 30), (20, 30)]
SLOT_MIN_AHEAD_MINS = 20
TIKTOK_OFFSET_HOURS = 2
```

To change the schedule (e.g. add a 09:00 slot), edit `PUBLISH_SLOTS` directly.

### --publish-ready --dry-run slot output

```
Timezone: America/New_York  |  Slots: 12:30, 16:30, 20:30 ET
Occupied YouTube slots:
  Thu 2026-04-02 12:30 EDT  ← 31qgcpec
  Thu 2026-04-02 16:30 EDT  ← 31s85gwk
  Thu 2026-04-02 20:30 EDT  ← 31s3wpyo
  Fri 2026-04-03 12:30 EDT  ← 31s7uf6n

→ 31qgcpec  Mother Elephant...
  YouTube: would upload '...' @ Thu 2026-04-02 12:30 EDT (auto-slot)
  TikTok:  would upload (mode: UPLOAD_TO_CREATOR_INBOX) @ Thu 2026-04-02 14:30 EDT
           (desired — stored, not scheduled; finalize in TikTok Studio)
```

---

## Queue Files

Each item is stored as a JSON file in `logs/publish_queue/{video_id}.json`:

```json
{
  "video_id": "31xxxx",
  "state": "approved",
  "video_path": "output/31xxxx_final.mp4",
  "metadata_path": "output/31xxxx_metadata.json",
  "qc_path": "logs/qc/31xxxx_qc.json",
  "qc_score": 8.1,
  "qc_verdict": "PASS",
  "title": "Mother Elephant Does The Unthinkable...",
  "queued_at": "2026-04-02T07:00:00+00:00",
  "reviewed_at": "2026-04-02T07:16:52+00:00",
  "rejection_reason": null,
  "youtube": {
    "scheduled_time": "2026-04-04T18:00:00+00:00",
    "video_id": null,
    "url": null,
    "published_at": null,
    "status": "pending",
    "error": null
  },
  "tiktok": {
    "scheduled_time": null,
    "publish_id": null,
    "url": null,
    "published_at": null,
    "status": "pending",
    "mode": null,
    "error": null
  }
}
```

Files are human-readable and editable directly if needed.

---

## YouTube Setup

YouTube uses OAuth2 (Desktop app flow). This is a one-time setup.

### Credentials needed

| Variable | Value |
|---|---|
| `YOUTUBE_CLIENT_SECRETS` | Path to client_secrets.json (default: `~/.pawfactory_yt_secrets.json`) |
| `YOUTUBE_TOKEN_FILE` | Where to store the OAuth token (default: `~/.pawfactory_yt_token.json`) |

### One-time setup

1. Go to [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials)
2. Create a project and enable the **YouTube Data API v3**
3. Create an OAuth2 client (type: **Desktop app**)
4. Download the `client_secrets.json` → save to `~/.pawfactory_yt_secrets.json`
5. Run the auth flow:

```bash
python scripts/publishing/youtube_uploader.py --auth
```

A browser window opens. Grant access. Token is saved to `~/.pawfactory_yt_token.json`. Token auto-refreshes — no need to repeat.

### What YouTube upload does

- Uploads the video with title, description, tags, category
- If `scheduled_time` is set: uploads as **private** with `publishAt` field → YouTube auto-publishes at that time
- If no `scheduled_time`: uploads as **public** immediately
- Stores `video_id` and URL in the queue item

---

## TikTok Setup

TikTok uses the **Content Posting API v2** with OAuth2 user tokens.

### Posting modes

| Mode | Behaviour | Account requirement |
|---|---|---|
| `DIRECT_POST` | Posts to feed directly (or at scheduled_time) | ≥1000 followers |
| `UPLOAD_TO_CREATOR_INBOX` | Sends to TikTok Studio Drafts; manual publish | Any account |

**Recommended default: `UPLOAD_TO_CREATOR_INBOX`** — works for new accounts, no follower minimum. Set `TIKTOK_POST_MODE=DIRECT_POST` once you have 1000+ followers.

### TikTok scheduling

- `DIRECT_POST` supports `scheduled_publish_time` (15 min – 10 days in the future)
- `UPLOAD_TO_CREATOR_INBOX` does **not** support scheduling — items land in drafts

### Credentials needed

| Variable | Value |
|---|---|
| `TIKTOK_CLIENT_KEY` | App client key from TikTok developer dashboard |
| `TIKTOK_CLIENT_SECRET` | App client secret |
| `TIKTOK_ACCESS_TOKEN` | User access token (set directly, or let `--auth` handle it) |
| `TIKTOK_TOKEN_FILE` | Where to store tokens (default: `~/.pawfactory_tiktok_token.json`) |
| `TIKTOK_POST_MODE` | `UPLOAD_TO_CREATOR_INBOX` or `DIRECT_POST` |
| `TIKTOK_PRIVACY` | `PUBLIC_TO_EVERYONE` / `MUTUAL_FOLLOW_FRIENDS` / `SELF_ONLY` |

### One-time setup

1. Create an app at [developers.tiktok.com](https://developers.tiktok.com)
2. Enable **Content Posting API**; request scopes: `video.publish`, `video.upload`
3. Submit app for review (may take days for production)
4. Set `TIKTOK_CLIENT_KEY` and `TIKTOK_CLIENT_SECRET` in `.env`
5. Run:

```bash
python scripts/publishing/tiktok_publisher.py --auth
```

6. Test credentials:

```bash
python scripts/publishing/tiktok_publisher.py --test
```

### What happens after TikTok upload

| Mode | Result | Next step |
|---|---|---|
| `DIRECT_POST` | Video posted to feed | Nothing — done |
| `DIRECT_POST` + schedule | Video queued to auto-post at time | Nothing — done |
| `UPLOAD_TO_CREATOR_INBOX` | Video in TikTok Studio Drafts | Open TikTok Studio → Drafts → pick caption, sounds, schedule |

Queue item status after upload:
- `published` — DIRECT_POST immediate
- `scheduled` — DIRECT_POST with future time
- `draft_uploaded` — UPLOAD_TO_CREATOR_INBOX (manual finalize needed)

---

## Manual Enqueue (for existing outputs)

If a short was produced before the queue system existed, add it manually:

```bash
python scripts/publishing/publish_queue.py --enqueue 31xxxx
```

This reads the existing `output/31xxxx_final.mp4`, `output/31xxxx_metadata.json`, and `logs/qc/31xxxx_qc.json`.

---

## What is automated vs manual

| Step | Automated | Manual |
|---|---|---|
| Enqueue after production | ✅ auto (run_pipeline.py) | — |
| Review / approve / reject | — | ✅ human |
| Set scheduled times | — | ✅ human |
| YouTube upload + scheduling | ✅ --publish-ready | — |
| TikTok upload (draft mode) | ✅ --publish-ready | Schedule in TikTok Studio |
| TikTok upload (direct mode) | ✅ --publish-ready | — |
| TikTok scheduling (direct) | ✅ via API | — |
| Update shorts/log.md | — | ✅ human (or future automation) |

---

## Scripts Reference

| Script | Purpose |
|---|---|
| `scripts/publishing/publish_queue.py` | Queue manager: list, approve, reject, schedule, publish |
| `scripts/publishing/youtube_uploader.py` | YouTube Data API v3 client + standalone upload CLI |
| `scripts/publishing/tiktok_publisher.py` | TikTok Content Posting API v2 client + standalone upload CLI |
| `scripts/publishing/metadata_gen.py` | Generates `output/{id}_metadata.json` (used by pipeline) |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `YouTube: skipped (credentials not configured)` | Run `python scripts/publishing/youtube_uploader.py --auth` |
| `TikTok: skipped (credentials not configured)` | Set `TIKTOK_ACCESS_TOKEN` in `.env` or run `--auth` |
| TikTok 401 on upload | Token expired — run `python scripts/publishing/tiktok_publisher.py --auth` again |
| YouTube token expired | Auto-refreshed; if fails, re-run `--auth` |
| Item stuck in `approved` after `--publish-ready` | Check `--show` for per-platform error field |
| Item shows `failed` | Check `error` field with `--show`; fix and re-run `--publish-ready` |
| TikTok `DIRECT_POST` rejected | Account has <1000 followers — switch to `UPLOAD_TO_CREATOR_INBOX` mode |
| TikTok scheduling time error | Must be 15 min – 10 days in the future |
| `already uploaded … — skipped` message | `video_id` / `publish_id` already set in queue but status was `pending` (manual edit inconsistency). The guardrail auto-corrects status to `published` and skips re-upload. |

---

## Duplicate-upload guardrail

`--publish-ready` will **never** upload a video that already has a platform ID recorded:

- YouTube: if `youtube.video_id` is non-null, upload is skipped and status is corrected to `published`
- TikTok: if `tiktok.publish_id` is non-null, upload is skipped and status is corrected to `published`

This prevents double-uploads after manual queue corrections or a partial run that wrote a `video_id` but crashed before updating `status`. To force a re-upload, clear `video_id` / `publish_id` and reset `status` to `pending` in the queue JSON directly.
