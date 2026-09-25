"""Claude Code OAuth token lookup and rate-limit polling.

Claude Code keeps its login in `<config dir>/.credentials.json` (config dir is
`$CLAUDE_CONFIG_DIR` or `~/.claude`). A minimal 1-token request to the
Messages API returns the subscription utilization in `anthropic-ratelimit-
unified-*` response headers, which is all this module reads.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"
HEADER_PREFIX = "anthropic-ratelimit-unified-"


class AuthError(Exception):
    """The API rejected the token (401/403); the user must run `claude login`."""


def credentials_path() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(base) if base else Path.home() / ".claude") / ".credentials.json"


def _find_key(node: object, key: str) -> str | None:
    """Depth-first search for a non-empty string value under `key`."""
    if isinstance(node, dict):
        value = node.get(key)
        if isinstance(value, str) and value:
            return value
        for child in node.values():
            found = _find_key(child, key)
            if found:
                return found
    return None


def read_token() -> str | None:
    """Return the current access token, or None if it can't be read."""
    try:
        data = json.loads(credentials_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return _find_key(data, "accessToken")


def _percent(value: str | None) -> int:
    try:
        return round(float(value) * 100)
    except (TypeError, ValueError):
        return 0


def _minutes_until(epoch: str | None) -> int:
    try:
        return max(0, round((float(epoch) - time.time()) / 60))
    except (TypeError, ValueError):
        return 0


async def poll_api(token: str) -> dict | None:
    """Fetch current utilization.

    Returns a dict with s/sr (5h window %, minutes to reset), w/wr (7d window),
    st (status text) and ok. Returns None for transient problems (network
    error, 5xx, missing headers). Raises AuthError on 401/403.
    """
    request_headers = {
        "Authorization": f"Bearer {token}",
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "oauth-2025-04-20",
        "content-type": "application/json",
    }
    body = {"model": MODEL, "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(API_URL, headers=request_headers, json=body)
    except httpx.HTTPError:
        return None

    if resp.status_code in (401, 403):
        raise AuthError(resp.status_code)
    if resp.status_code >= 400:
        return None

    def h(name: str) -> str | None:
        return resp.headers.get(HEADER_PREFIX + name)

    if h("5h-utilization") is None:
        return None
    return {
        "s": _percent(h("5h-utilization")),
        "sr": _minutes_until(h("5h-reset")),
        "w": _percent(h("7d-utilization")),
        "wr": _minutes_until(h("7d-reset")),
        "st": h("5h-status") or "unknown",
        "ok": True,
    }
