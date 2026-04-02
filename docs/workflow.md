# Production Workflow

> Step-by-step guide for producing one Short.
> Last updated: 2026-04-01
> For system state, see `docs/resume-handoff.md`.

---

## Automation Levels

| Level | Description | When |
|---|---|---|
| L1 — Manual | All steps triggered manually | Current phase |
| L2 — Semi-auto | Claude Code produces, human reviews each output | Month 1–2 |
| L3 — Auto | Claude Code produces full batch, human reviews output folder | Month 2–4 |
| L4 — Full auto | Claude Code produces and schedules, human monitors only | Month 4+ |

---

## Step 1 — Sourcing

Find 5–10 candidates per day, pick 1–2 best.

```bash
python scripts/sourcing/reddit_scraper.py
```

**Active subreddits:** AnimalsBeingBros, MadeMeSmile, HumansBeingBros, aww, rarepuppers, Eyebleach, rescue

**Output:** `logs/candidates_YYYYMMDD.json`

**Note:** `viral_score` is recency-based only (Reddit RSS has no upvote counts). Score reflects freshness, not actual virality. Filter threshold: any score > 0.

**Candidate JSON format:**
```json
{
  "id": "abc123",
  "title": "Stray dog saved from flooded river",
  "url": "https://reddit.com/r/aww/comments/abc123/...",
  "video_url": "https://reddit.com/r/aww/comments/abc123/...",
  "viral_score": 1.5,
  "age_hours": 8.8,
  "source": "reddit/r/aww"
}
```

**Note:** `video_url` stores the Reddit post URL (not `v.redd.it`) — yt-dlp extracts the actual video from the post page. Direct `v.redd.it` URLs return 403.

---

## Step 2 — Download

```bash
python scripts/sourcing/downloader.py --url "POST_URL" --id "abc123"
```

Uses yt-dlp internally. Output: `inbox/abc123.mp4`

---

## Step 3 — Generate Hook + Script

```bash
python scripts/production/hook_generator.py \
  --video-id "abc123" \
  --description "Stray dog rescued from flooded river by two men in a boat" \
  --duration 28 \
  --source "reddit/r/aww"
```

**`--duration` must be set from actual clip duration** (run pipeline uses `clip_duration * 0.85`). Do not leave at the default 45s for short clips — the script will be too long and TTS will overrun.

Calls Claude Sonnet. Output: `logs/hooks/abc123.json`

**Hook format enforced by prompt:** First sentence must state the danger explicitly. Examples:
- "This baby elephant is seconds from drowning."
- "She had 30 seconds to live."
- "Nobody thought he would make it out alive."

**Output JSON includes:** `hook`, `narration`, `full_script`, `title_variants` (5), `description`, `hashtags`, `cta`, `emotional_arc`, `animal`

**Shortening pass (if TTS overruns clip):**
```bash
python scripts/production/hook_generator.py \
  --shorten \
  --video-id "abc123" \
  --max-duration 26
```
Rewrites `full_script` in-place to fit `--max-duration` seconds. Preserves hook and payoff. Run pipeline does this automatically if needed.

---

## Step 4 — Voiceover

```bash
python scripts/production/voiceover.py --video-id "abc123"
```

Reads `logs/hooks/abc123.json`, sends `full_script` to ElevenLabs.

**Voice:** Lily (`pFZP5JQG7iQjIQuC4Bku`), model `eleven_multilingual_v2`, stability=0.5, similarity=0.75, style=0.3

Output: `inbox/abc123_voice.mp3`

---

## Step 5 — Assemble Video

```bash
python scripts/production/video_editor.py --video-id "abc123"
```

**Internal pipeline (in order):**

| Step | What happens |
|---|---|
| — | ~~Auto-loop~~ **REMOVED — looping is disabled** (see duration policy below) |
| 1 | **Duration gate:** if audio > clip − 2s → reject with logged reason (no looping) |
| 2 | **9:16 crop:** crop right 12% (watermark) + bottom 17% (source subs), zoom 1.3×, scale to 1080×1920 |
| 3 | **Music mix:** `music_mixer.py` selects one of 7 categories via Claude Haiku (`emotional_arc`), picks a non-recent track within the category, mixes at 8% volume with 2s fades → `inbox/abc123_voice_music.mp3`. See `docs/music-system.md`. |
| 3b | **Mux:** combine cropped video + voice+music audio (source audio muted) |
| 4 | **Captions:** Submagic primary → ASS v3 fallback → none |
| 5 | **Auto-trim:** if final video > audio + 2s → trim to audio + 0.5s (removes dead air) |

**Duration policy (NO LOOPING):**
- `MIN_SOURCE_DURATION = 20s` — clips below this are rejected in `run_pipeline.py` before any generation
- `DURATION_SAFETY_MARGIN = 2s` — audio must end at least 2s before clip ends
- `TARGET_DURATION_FACTOR = 0.85` — run pipeline sets narration target = `clip × 0.85`
- If TTS overruns after generation: one shortening pass (Claude rewrite) + re-generate TTS
- If still overruns: clip is rejected — find a different source

Output: `output/abc123_final.mp4`

**Temp files cleaned up:** `output/abc123_vertical.mp4`, `output/abc123_mixed.mp4`

**Idempotent:** if `output/abc123_final.mp4` already exists, step is skipped.

---

## Step 6 — Quality Check

```bash
python scripts/production/quality_check.py --video-id "abc123"
```

Claude Vision reviews 5 frames. Output: `logs/qc/abc123_qc.json`

See `docs/qa-system.md` for full details.

If verdict is FAIL: investigate before proceeding. Common causes:
- Wrong niche content (no animal, no rescue narrative)
- Source video had burned-in subtitles
- Captions covering main subject

---

## Step 7 — Generate Metadata

```bash
python scripts/publishing/metadata_gen.py --video-id "abc123"
```

Reads `logs/hooks/abc123.json`. Output: `output/abc123_metadata.json`

Contains: `title`, `title_variants` (5), `description`, `hashtags`, `cta`, `source_credit`

---

## Full Batch Pipeline

```bash
# Process top 2 candidates from today's scrape
python scripts/run_pipeline.py --top-n 2

# Process specific video
python scripts/run_pipeline.py \
  --video-id "abc123" \
  --url "REDDIT_POST_URL" \
  --description "TITLE FROM REDDIT"
```

`run_pipeline.py` runs steps 2–7 in sequence. Skips already-processed IDs (reads `logs/processed.json`).

---

## Step 8 — Review Queue + Publishing

After `run_pipeline.py` completes (QC PASS), each short is automatically placed in `logs/publish_queue/` as `pending_review`.

### Review the queue

```bash
python scripts/publishing/publish_queue.py --list
python scripts/publishing/publish_queue.py --show abc123
```

### Approve, reject, or defer

```bash
python scripts/publishing/publish_queue.py --approve abc123
python scripts/publishing/publish_queue.py --reject  abc123 --reason "shaky footage"
python scripts/publishing/publish_queue.py --defer   abc123
```

### Set publish schedule (optional)

```bash
# Schedule YouTube only (TikTok posts immediately or goes to drafts)
python scripts/publishing/publish_queue.py --schedule abc123 --youtube "2026-04-04T18:00:00"

# Schedule both platforms
python scripts/publishing/publish_queue.py --schedule abc123 \
  --youtube "2026-04-04T18:00:00" \
  --tiktok  "2026-04-04T20:00:00"
```

### Execute uploads

```bash
python scripts/publishing/publish_queue.py --publish-ready --dry-run  # preview
python scripts/publishing/publish_queue.py --publish-ready             # execute
```

**YouTube:** uploads with title, description, tags. If `--youtube` time was set, video uploads as private and auto-publishes at scheduled time. Otherwise published immediately.

**TikTok (default mode: `UPLOAD_TO_CREATOR_INBOX`):** video goes to TikTok Studio Drafts. Open TikTok Studio → Drafts → add caption/sounds → publish or schedule manually. Set `TIKTOK_POST_MODE=DIRECT_POST` in `.env` once you have ≥1000 followers for fully automated posting.

See `docs/publishing-system.md` for credential setup and full operator guide.

---

## Step 9 — Log

After upload, update `shorts/log.md`:

```markdown
| abc123 | 2026-04-01 | r/aww | YT | Title Here | — | — | uploaded |
```

---

## Step 10 — Analytics Feedback Loop

```bash
python scripts/analytics/stats_tracker.py
```

Runs daily at 22:00 (cron). Pulls YouTube Analytics API, updates `shorts/log.md`, generates `logs/weekly_report.md` every 7 days.

Use analytics to adjust `hook_generator.py` prompts: low CTR → sharper hook; early AVD drop → pacing issue.

---

## Error Handling

| Error type | Action |
|---|---|
| Missing dependency | Install via pip, retry |
| API rate limit (429) | Wait 60s, retry once |
| API auth error | Stop, notify human: "API key for [SERVICE] invalid or missing" |
| Single video failure | Log to `logs/errors.log`, skip, continue pipeline |
| 3+ consecutive failures | Stop, notify human |
| catbox.moe upload failure | Submagic skipped, falls back to ASS captions |
| v.redd.it 403 | Use post URL instead — yt-dlp handles extraction |

---

## Timing — One Short

| Step | Time (approx) |
|---|---|
| Sourcing | 1–2 min |
| Download | 30s–2 min |
| Hook generation | 15s |
| Voiceover | 20s |
| Music mix | 10s |
| Video assembly | 1–3 min (ffmpeg) |
| Submagic captions | 2–5 min (upload + processing) |
| QC | 30s |
| Metadata | 5s |
| **Total** | **~7–15 min** |
