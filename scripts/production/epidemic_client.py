#!/usr/bin/env python3
"""
epidemic_client.py — Epidemic Sound MCP client for PawFactory

Wraps the Epidemic Sound MCP server at https://www.epidemicsound.com/a/mcp-service/mcp
Provides:
  - Session management (stateful MCP sessions)
  - Track search by text query
  - Track download via signed URL

Requires: EPIDEMIC_API_KEY in .env (JWT bearer token)
"""

import json
import os
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

MCP_URL = "https://www.epidemicsound.com/a/mcp-service/mcp"
MCP_TIMEOUT = 45  # seconds; searches can be slow


class EpidemicClient:
    """
    Stateful MCP session wrapper for Epidemic Sound.
    Automatically initializes on first use; session is reused until close().
    """

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.getenv("EPIDEMIC_API_KEY")
        if not self._api_key:
            raise RuntimeError("EPIDEMIC_API_KEY not set in environment")
        self._session_id: Optional[str] = None
        self._req_id = 0

    # ── Session lifecycle ───────────────────────────────────────────────────

    def _base_headers(self) -> dict:
        h = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            h["Mcp-Session-Id"] = self._session_id
        return h

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _post(self, payload: dict, timeout: int = MCP_TIMEOUT) -> list[dict]:
        """POST a JSON-RPC payload; stream SSE response; return list of parsed data objects."""
        r = requests.post(
            MCP_URL,
            headers=self._base_headers(),
            json=payload,
            timeout=timeout,
            stream=True,
        )
        r.raise_for_status()
        # Capture new session ID from any response that carries it
        new_sid = r.headers.get("Mcp-Session-Id")
        if new_sid:
            self._session_id = new_sid
        events = []
        for line in r.iter_lines(decode_unicode=True):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
        return events

    def initialize(self):
        """Send MCP initialize + initialized notification. Called automatically on first use."""
        events = self._post({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "pawfactory", "version": "1.0"},
            },
        })
        if not events or "result" not in events[0]:
            raise RuntimeError(f"MCP initialize failed: {events}")
        # Send the required notifications/initialized (no response expected)
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _ensure_session(self):
        if not self._session_id:
            self.initialize()

    # ── GraphQL execute ─────────────────────────────────────────────────────

    def graphql(self, query: str) -> dict:
        """
        Execute a raw GraphQL query via the MCP `execute` tool.
        Returns the `data` dict from the GraphQL response.
        """
        self._ensure_session()
        events = self._post({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": "execute", "arguments": {"query": query}},
        })
        if not events:
            raise RuntimeError("No response from MCP execute")
        result = events[0].get("result", {})
        if result.get("isError"):
            raise RuntimeError(f"GraphQL error: {result}")
        structured = result.get("structuredContent", {})
        if "data" in structured:
            return structured["data"]
        # Fallback: parse text content
        text_content = result.get("content", [{}])[0].get("text", "{}")
        return json.loads(text_content).get("data", {})

    # ── High-level search ────────────────────────────────────────────────────

    def search_tracks(
        self,
        topic: str,
        count: int = 10,
        mood_slugs: Optional[list[str]] = None,
        bpm_min: Optional[int] = None,
        bpm_max: Optional[int] = None,
    ) -> list[dict]:
        """
        Search for tracks by topic text.
        Returns list of dicts with keys: id, title, bpm, duration_ms, tags, lqmp3_url.

        mood_slugs:  e.g. ["dark", "tense", "suspense"] — filters by mood tag
        bpm_min/max: BPM range filter
        """
        # Build filter fragment
        # FilterStringValues uses { any: [...] } syntax
        # FilterMinMaxValues uses { min: N, max: N } syntax
        filters = []
        if mood_slugs:
            slugs_str = ", ".join(f'"{s}"' for s in mood_slugs)
            filters.append(f"moodSlugs: {{ any: [{slugs_str}] }}")
        bpm_parts = []
        if bpm_min is not None:
            bpm_parts.append(f"min: {bpm_min}")
        if bpm_max is not None:
            bpm_parts.append(f"max: {bpm_max}")
        if bpm_parts:
            filters.append(f"bpm: {{ {', '.join(bpm_parts)} }}")
        filter_clause = f"filter: {{ {' '.join(filters)} }}" if filters else ""

        query = f"""
        query {{
          recordings(
            query: {{ topic: "{topic}" }}
            {filter_clause}
            first: {count}
            sort: {{ by: RELEVANCE, order: DESCENDING }}
          ) {{
            nodes {{
              recording {{
                id title bpm
                stems {{ audioFile {{ lqmp3Url durationInMilliseconds }} }}
                tags {{ slug displayName }}
              }}
            }}
          }}
        }}
        """
        data = self.graphql(query)
        nodes = data.get("recordings", {}).get("nodes", [])
        results = []
        for node in nodes:
            rec = node.get("recording", {})
            # Pick the full-track stem (first stem)
            stems = rec.get("stems", [])
            first_stem = stems[0]["audioFile"] if stems else {}
            results.append({
                "id": rec.get("id"),
                "title": rec.get("title"),
                "bpm": rec.get("bpm"),
                "duration_ms": first_stem.get("durationInMilliseconds", 0),
                "tags": [t["slug"] for t in rec.get("tags", [])],
                "lqmp3_url": first_stem.get("lqmp3Url"),
            })
        return results

    # ── Download ─────────────────────────────────────────────────────────────

    def get_download_url(self, track_id: str) -> str:
        """
        Get a signed download URL for a track (full quality MP3).
        The URL is short-lived (expires in ~10 minutes).
        """
        self._ensure_session()
        events = self._post({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": "DownloadRecording",
                "arguments": {
                    "id": track_id,
                    "options": {"fileType": "MP3", "stemType": "FULL"},
                },
            },
        })
        if not events:
            raise RuntimeError("No response from DownloadRecording")
        result = events[0].get("result", {})
        if result.get("isError"):
            raise RuntimeError(f"DownloadRecording error: {result}")
        structured = result.get("structuredContent", {})
        url = structured.get("data", {}).get("recordingDownload", {}).get("assetUrl")
        if not url:
            # Fallback: parse text
            text = result.get("content", [{}])[0].get("text", "{}")
            url = json.loads(text).get("data", {}).get("recordingDownload", {}).get("assetUrl")
        if not url:
            raise RuntimeError(f"No assetUrl in response: {result}")
        return url

    def download_track(self, track_id: str, dest_path: str | Path) -> Path:
        """
        Download a track to dest_path. Returns the Path on success.
        Uses DownloadRecording for full-quality MP3.
        """
        url = self.get_download_url(track_id)
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        r = requests.get(url, stream=True, timeout=120)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
        return dest


# ── Convenience function ────────────────────────────────────────────────────────

def make_client() -> EpidemicClient:
    """Create and return a connected EpidemicClient. Raises if API key is missing."""
    return EpidemicClient()
