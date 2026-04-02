#!/usr/bin/env python3
"""
reddit_scraper.py — PawFactory sourcing tool (RSS edition)
Finds viral animal rescue videos from Reddit via public RSS feeds.
No API key required.

Usage:
  python scripts/sourcing/reddit_scraper.py
  python scripts/sourcing/reddit_scraper.py --test
  python scripts/sourcing/reddit_scraper.py --subreddits AnimalsBeingBros,aww --limit 20
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import requests
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

load_dotenv()
console = Console()

RSS_FEEDS = {
    # primary high-rescue-content subs
    "AnimalsBeingBros": "https://www.reddit.com/r/AnimalsBeingBros/hot.rss",
    "MadeMeSmile":      "https://www.reddit.com/r/MadeMeSmile/hot.rss",
    "HumansBeingBros":  "https://www.reddit.com/r/HumansBeingBros/hot.rss",
    "aww":              "https://www.reddit.com/r/aww/hot.rss",
    "rarepuppers":      "https://www.reddit.com/r/rarepuppers/hot.rss",
    "Eyebleach":        "https://www.reddit.com/r/Eyebleach/hot.rss",
    "rescue":           "https://www.reddit.com/r/rescue/hot.rss",
    # additional rescue-focused subs for fresh daily supply
    "AnimalRescue":     "https://www.reddit.com/r/AnimalRescue/hot.rss",
    "rescuedogs":       "https://www.reddit.com/r/rescuedogs/hot.rss",
    "rescuecats":       "https://www.reddit.com/r/rescuecats/hot.rss",
    "wildlife":         "https://www.reddit.com/r/wildlife/hot.rss",
    "WildlifeRescue":   "https://www.reddit.com/r/WildlifeRescue/hot.rss",
    "whatsthisbird":    "https://www.reddit.com/r/whatsthisbird/hot.rss",
    # fresh/new feeds for primary subs — lower viral score but unseen posts
    "AnimalsBeingBros_new": "https://www.reddit.com/r/AnimalsBeingBros/new.rss",
    "HumansBeingBros_new":  "https://www.reddit.com/r/HumansBeingBros/new.rss",
}

# Reddit's top.rss?t=day often returns empty XML depending on time of day.
# hot.rss is reliably populated and still surfaces recent high-engagement posts.

# ── Candidate filter — signal sets + weighted scoring ─────────────────────────
#
# Replaces the old brittle RESCUE_KEYWORDS AND REQUIRED_ANIMAL_KEYWORDS AND-gate
# with a small weighted heuristic. Each signal set is scored independently so
# either set can be expanded without breaking the other.
#
# Scoring:
#   animal_score  = 2.0  if any ANIMAL_SIGNALS term appears in (title + summary)
#   rescue_score  = 2.0  if any RESCUE_SIGNALS term appears
#   danger_score  = 1.0  if any DANGER_SIGNALS term appears
#   sub_bonus     = SUBREDDIT_PRIORS[subreddit] × 0.5  (max 1.0)
#   total         = sum of all four
#
# RESCUE_SCORE_THRESHOLD = 3.0.  Minimum-passing combinations:
#   animal + rescue (4.0)          ← typical rescue post; always passes
#   animal + danger (3.0)          ← animal in burning/flooding/trapped context
#   rescue + danger (3.0)          ← "firefighters save from fire" (no explicit animal word)
#   animal + r/rescue prior (3.0)  ← dedicated rescue sub: any animal post qualifies
# animal + high-prior sub alone (2.5) does NOT pass — prevents cute-only false positives.
#
# A signal bonus (0–0.5) proportional to excess score above threshold is folded
# into viral_score so the strongest rescue candidates naturally surface first.
# The JSON output schema is unchanged.

ANIMAL_SIGNALS = frozenset({
    # specific animals
    "elephant", "lion", "lioness", "bear", "wolf", "eagle", "hawk", "owl",
    "parrot", "bird", "birds", "dog", "dogs", "cat", "cats", "kitty", "kitten",
    "canine", "feline", "pooch",
    "whale", "dolphin", "turtle", "tortoise", "snake", "fox", "deer",
    "horse", "tiger", "leopard", "cheetah", "gorilla", "monkey", "chimp",
    "seal", "otter", "penguin", "crocodile", "alligator", "giraffe",
    "hippo", "rhinoceros", "rhino",
    "puppy", "puppies", "kitten", "kittens", "cub", "cubs",
    "cow", "calf", "pig", "piglet", "goat", "sheep", "lamb",
    "rabbit", "bunny", "duck", "duckling", "chicken", "chick",
    "bat", "hedgehog", "squirrel", "raccoon", "possum", "opossum",
    "frog", "toad", "lizard", "gecko", "hamster", "ferret",
    "pelican", "crane", "heron", "swan", "geese", "goose", "pigeon",
    "pup", "pups", "foal", "fawn",
    # general terms
    "animal", "animals", "wildlife", "wild",
    # rescue-org contexts that imply animal subject
    "shelter", "sanctuary", "veterina", "rehabilit",
    # state terms that strongly imply animal + peril
    "stray", "orphan", "abandoned", "injured",
})

RESCUE_SIGNALS = frozenset({
    # rescue and save verbs (all conjugations)
    "rescue", "rescued", "rescuing",
    "save", "saved", "saving",
    "help", "helped", "helping",
    "freed", "freeing",
    "carried", "carrying",
    "revive", "revived", "reviving",
    "release", "released", "releasing",
    # care, treatment, and recovery verbs
    "nursing", "nursed",
    "treated", "treating", "treatment",
    "recovering", "recovered", "recovery",
    "heal", "healed", "healing",
    "rehabilit",
    "adopted", "adoption",
    # outcome and survival words
    "survived", "survive", "surviving",
    "alive",
    "breathing",
    "oxygen",
    "safe",
    "protected", "protecting",
    "reunited", "reunite", "reunion",
    # discovery / care context
    "found",
    # idioms and transformation terms
    "second chance",
    "transformation",
    "before and after",
    "new life",
    "thriving",
    # bond, loyalty, and gratitude
    "bond", "bonded", "bonding",
    "loyal", "loyalty",
    "grateful", "gratitude",
    "trusts", "trust",
    "friendship",
    # rehab and shelter contexts
    "foster", "fostered",
    "sanctuary",
    "shelter",
    "forever home",
})

DANGER_SIGNALS = frozenset({
    "fire", "burning", "burnt", "blaze",
    "flood", "flooding", "flooded",
    "trapped", "stuck",
    "drowning", "drown", "drowned",
    "hurt", "wounded", "wound",
    "emergency",
    "smoke",
    "collapse", "collapsed",
    "stranded",
    "dying",
    "danger", "dangerous",
    "crash", "accident",
    "entangled", "entangle",
})

EXCLUDE_SIGNALS = frozenset({
    "hunt", "hunting", "hunted",
    "kill", "killing",
    "zoo",
    "circus",
    "captiv",
})

# Reliability prior per subreddit: 2 = dedicated rescue, 1 = high rescue density.
# Multiplied by 0.5 to contribute to score (max +1.0).
SUBREDDIT_PRIORS: dict[str, float] = {
    "AnimalsBeingBros": 1,
    "MadeMeSmile":      0,
    "HumansBeingBros":  1,
    "aww":              0,
    "rarepuppers":      0,
    "Eyebleach":        0,
    "rescue":           2,
    # new subs
    "AnimalRescue":         2,
    "rescuedogs":           1,
    "rescuecats":           1,
    "wildlife":             1,
    "WildlifeRescue":       2,
    "whatsthisbird":        0,
    # "_new" keys inherit from their base sub
    "AnimalsBeingBros_new": 1,
    "HumansBeingBros_new":  1,
}

RESCUE_SCORE_THRESHOLD = 3.0

VIDEO_URL_PATTERNS = [
    r"https?://v\.redd\.it/[^\s\"'<>]+",
    r"https?://(?:www\.)?youtube\.com/watch\?[^\s\"'<>]+",
    r"https?://youtu\.be/[^\s\"'<>]+",
    r"https?://[^\s\"'<>]+\.mp4[^\s\"'<>]*",
    r"https?://[^\s\"'<>]+\.mov[^\s\"'<>]*",
    r"https?://[^\s\"'<>]+\.webm[^\s\"'<>]*",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def fetch_feed(subreddit, url):
    """Fetch and parse an RSS feed, return list of raw entries."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        return feed.entries
    except Exception as e:
        console.print(f"[yellow]WARNING: Failed to fetch r/{subreddit} RSS: {e}[/yellow]")
        return []


def extract_video_url(entry):
    """Search entry content and links for a video URL."""
    # Collect all text to search through
    blobs = [
        entry.get("link", ""),
        entry.get("summary", ""),
    ]
    for content in entry.get("content", []):
        blobs.append(content.get("value", ""))
    for enc in entry.get("enclosures", []):
        if "video" in enc.get("type", "") or any(
            enc.get("url", "").lower().endswith(ext) for ext in [".mp4", ".mov", ".webm"]
        ):
            return enc.get("url")

    # Check media_content (media:content tag)
    for media in entry.get("media_content", []):
        url = media.get("url", "")
        mtype = media.get("type", "")
        if "video" in mtype or any(url.lower().endswith(ext) for ext in [".mp4", ".mov", ".webm"]):
            return url

    full_text = " ".join(blobs)

    for pattern in VIDEO_URL_PATTERNS:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            return match.group(0)

    # Fallback: entry link itself if it looks like a video host
    link = entry.get("link", "")
    if any(host in link for host in ["v.redd.it", "youtube.com", "youtu.be"]):
        return link

    return None


def extract_comment_count(entry):
    """Try to extract comment count from entry tags."""
    # feedparser sometimes exposes slash:comments
    for tag in entry.get("tags", []):
        if "comment" in tag.get("label", "").lower():
            try:
                return int(tag.get("term", 0))
            except (ValueError, TypeError):
                pass
    return 0


def compute_viral_score(entry, comment_count):
    """Score based on recency and keyword strength (RSS has no upvote/comment counts)."""
    published = entry.get("published_parsed")
    if published:
        pub_ts = datetime(*published[:6], tzinfo=timezone.utc).timestamp()
        age_hours = (datetime.now(timezone.utc).timestamp() - pub_ts) / 3600
    else:
        age_hours = 12  # assume mid-range if unknown

    if age_hours < 6:
        recency = 2.0
    elif age_hours < 24:
        recency = 1.5
    elif age_hours < 72:
        recency = 1.0
    else:
        recency = 0.7

    # Reddit RSS doesn't expose upvote/comment counts.
    # Score = recency multiplier + bonus for comment count if available.
    base = recency
    if comment_count > 0:
        base += (comment_count / 50)

    return round(base, 2), round(age_hours, 1)


def score_rescue_content(title: str, summary: str = "", subreddit: str = "") -> float:
    """
    Return a rescue-signal score for a post.  Higher = stronger rescue candidate.
    Returns 0.0 immediately if any EXCLUDE_SIGNALS term is present.
    See the comment block above ANIMAL_SIGNALS for scoring details.

    Only the title is used for signal matching.  Reddit post titles are almost
    always self-descriptive, and summaries (post bodies) add noise — subreddit
    announcements, rules, and unrelated HTML content contain stray animal/rescue
    words that cause false positives when summary is included.
    """
    text = title.lower()   # title only — summary is noise-prone

    if any(kw in text for kw in EXCLUDE_SIGNALS):
        return 0.0

    animal = 2.0 if any(kw in text for kw in ANIMAL_SIGNALS) else 0.0
    rescue = 2.0 if any(kw in text for kw in RESCUE_SIGNALS) else 0.0
    danger = 1.0 if any(kw in text for kw in DANGER_SIGNALS) else 0.0
    prior  = SUBREDDIT_PRIORS.get(subreddit, 0) * 0.5

    return animal + rescue + danger + prior


def is_rescue_content(title: str, summary: str = "", subreddit: str = "") -> bool:
    """Return True if the post clears RESCUE_SCORE_THRESHOLD."""
    return score_rescue_content(title, summary, subreddit) >= RESCUE_SCORE_THRESHOLD


def entry_to_candidate(entry, subreddit, rescue_score: float = 0.0):
    title = entry.get("title", "")
    link = entry.get("link", "")
    summary = entry.get("summary", "")

    # entry id is typically a full URL; extract the post ID from it
    raw_id = entry.get("id", link)
    post_id_match = re.search(r"/comments/([a-z0-9]+)/", raw_id)
    post_id = post_id_match.group(1) if post_id_match else re.sub(r"[^a-z0-9]", "", raw_id)[-8:]

    comment_count = extract_comment_count(entry)
    viral_score, age_hours = compute_viral_score(entry, comment_count)

    # Fold rescue signal strength into viral_score as a small bonus (+0.0–+0.5).
    # Excess score above threshold (e.g. 4.0 − 2.5 = 1.5) is divided by 10 so
    # a perfect animal+rescue+danger hit adds at most +0.5. This keeps the schema
    # unchanged while naturally surfacing higher-confidence rescue posts.
    signal_bonus = round(min(0.5, max(0.0, rescue_score - RESCUE_SCORE_THRESHOLD) / 10.0), 2)
    viral_score  = round(viral_score + signal_bonus, 2)

    # video_url stores the Reddit post permalink — downloader.py passes this to
    # yt-dlp which extracts the actual video. Direct v.redd.it URLs return 403.
    return {
        "id": post_id,
        "title": title,
        "url": link,
        "video_url": link,  # post URL, not raw v.redd.it — yt-dlp handles extraction
        "score": None,           # not available in RSS
        "num_comments": comment_count,
        "age_hours": age_hours,
        "viral_score": viral_score,
        "source": f"reddit/r/{subreddit}",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


def scrape_feed(subreddit, url, limit):
    entries = fetch_feed(subreddit, url)
    candidates = []
    for entry in entries:
        title   = entry.get("title", "")
        summary = entry.get("summary", "")

        rscore = score_rescue_content(title, summary, subreddit)
        if rscore < RESCUE_SCORE_THRESHOLD:
            continue

        video_url = extract_video_url(entry)
        if not video_url:
            continue

        candidate = entry_to_candidate(entry, subreddit, rescue_score=rscore)
        candidates.append(candidate)

        if len(candidates) >= limit:
            break

    time.sleep(1)  # polite crawl rate
    return candidates


def run_test():
    """Fetch one feed and print first 3 entries (raw, no filtering)."""
    console.print("[cyan]Testing RSS fetch from r/AnimalsBeingBros...[/cyan]\n")
    url = RSS_FEEDS["AnimalsBeingBros"]
    entries = fetch_feed("AnimalsBeingBros", url)

    if not entries:
        console.print("[red]✗ No entries returned — check network or feed URL[/red]")
        return False

    console.print(f"[green]✓ Feed fetched: {len(entries)} entries total[/green]\n")

    for i, entry in enumerate(entries[:3]):
        title = entry.get("title", "(no title)")
        link = entry.get("link", "")
        video_url = extract_video_url(entry)
        comment_count = extract_comment_count(entry)

        console.print(f"[bold]Entry {i+1}:[/bold]")
        console.print(f"  Title:    {title[:80]}")
        console.print(f"  Link:     {link}")
        console.print(f"  Video:    {video_url or '[dim]none detected[/dim]'}")
        console.print(f"  Comments: {comment_count}")
        console.print()

    return True


def main():
    parser = argparse.ArgumentParser(description="PawFactory Reddit RSS Scraper")
    parser.add_argument(
        "--subreddits",
        default=",".join(RSS_FEEDS.keys()),
        help="Comma-separated subreddit names (must be in RSS_FEEDS dict)",
    )
    parser.add_argument(
        "--limit", type=int, default=10,
        help="Max candidates per subreddit (default: 10)",
    )
    parser.add_argument(
        "--min-viral", type=float, default=0.0,
        help="Minimum viral score threshold (default: 0.0)",
    )
    parser.add_argument(
        "--output-json", default=None,
        help="Output JSON file path (default: logs/candidates_YYYYMMDD.json)",
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Fetch one feed and print first 3 entries, then exit",
    )
    args = parser.parse_args()

    if args.test:
        success = run_test()
        sys.exit(0 if success else 1)

    subreddit_names = [s.strip() for s in args.subreddits.split(",")]
    all_candidates = []

    console.print(f"[cyan]Scraping {len(subreddit_names)} subreddits via RSS...[/cyan]")

    for name in subreddit_names:
        if name not in RSS_FEEDS:
            console.print(f"[yellow]WARNING: No RSS URL configured for r/{name} — skipping[/yellow]")
            continue
        console.print(f"  → r/{name}")
        results = scrape_feed(name, RSS_FEEDS[name], args.limit)
        console.print(f"    {len(results)} rescue video candidate(s) found")
        all_candidates.extend(results)

    # Seed seen_ids with posts already in the publish queue so they are never
    # re-suggested.  PawFactory IDs are "3" + reddit_post_id, so strip the
    # leading "3" to recover the original reddit ID.
    seen_ids: set[str] = set()
    queue_dir = Path(os.getenv("LOG_DIR", "logs")) / "publish_queue"
    if queue_dir.exists():
        for qf in queue_dir.glob("*.json"):
            try:
                with open(qf) as _qf:
                    qitem = json.load(_qf)
                vid = qitem.get("video_id", "")
                if vid:
                    # Store raw ID, "3" + raw ID, and stripped forms so all
                    # scraper ID formats are covered regardless of how the queue
                    # item was originally created (pre- vs post- "3x" convention).
                    seen_ids.add(vid)
                    seen_ids.add("3" + vid)
                    # also strip a leading "3" in case vid is already "3xxxxx"
                    if vid.startswith("3"):
                        seen_ids.add(vid[1:])
            except Exception:
                pass

    # Deduplicate by id and filter by viral score
    filtered = []
    for c in all_candidates:
        if c["id"] not in seen_ids and c["viral_score"] >= args.min_viral:
            seen_ids.add(c["id"])
            filtered.append(c)

    filtered.sort(key=lambda x: x["viral_score"], reverse=True)

    # Output path
    if args.output_json:
        out_path = Path(args.output_json)
    else:
        log_dir = Path(os.getenv("LOG_DIR", "logs"))
        log_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        out_path = log_dir / f"candidates_{date_str}.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(filtered, f, indent=2, ensure_ascii=False)

    # Display results table
    table = Table(title=f"Found {len(filtered)} rescue video candidates")
    table.add_column("ID", style="dim")
    table.add_column("Title", max_width=48)
    table.add_column("Comments", justify="right")
    table.add_column("Viral", justify="right", style="green")
    table.add_column("Age (h)", justify="right")
    table.add_column("Video URL", max_width=30, style="dim")
    table.add_column("Source")

    for c in filtered[:15]:
        table.add_row(
            c["id"],
            c["title"][:46] + ("…" if len(c["title"]) > 46 else ""),
            str(c["num_comments"]),
            str(c["viral_score"]),
            str(c["age_hours"]),
            (c["video_url"] or "—")[:28],
            c["source"],
        )

    console.print(table)
    console.print(f"\n[green]✓ Saved {len(filtered)} candidates to {out_path}[/green]")


if __name__ == "__main__":
    main()
