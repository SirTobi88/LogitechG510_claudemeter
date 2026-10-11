"""Maps a usage payload dict to G510 LCD text lines.

Pure function, no SDK/hardware dependency -- easy to unit test on its own.
Payload fields as returned by claude_api.poll_api():
s = session %, sr = session reset (min), w = weekly %, wr = weekly reset (min),
st = status string, ok = success flag.
The 4th line shows what Claude Code is doing (claude_state.LABELS) when the
hooks report something, else the rate-limit status.
"""

from __future__ import annotations


def _fmt_reset(minutes: int) -> str:
    """Compact reset countdown that always fits the 20-char line budget."""
    if minutes < 60:
        return f"{minutes}m"
    if minutes < 1440:
        return f"{minutes // 60}h{minutes % 60:02d}"
    return f"{minutes // 1440}d{(minutes % 1440) // 60}h"


def _status_line(status: str, activity: str | None) -> str:
    if status == "rejected":
        return "Limit reached"
    return activity or status


def render_lines(
    payload: dict | None, activity: str | None = None, compact: bool = False
) -> list[str]:
    """4 lines for the SDK's text mode, or with `compact` the 3 shorter lines
    (no title, no "rst", 16 chars) that fit beside the Clawd animation."""
    title = [] if compact else ["Claude Usage"]
    if payload is None:
        return title + ["", "No data yet", ""]

    if not payload.get("ok", False):
        return title + ["", "No data", "run claude login"]

    s = payload.get("s", 0)
    sr = payload.get("sr", 0)
    w = payload.get("w", 0)
    wr = payload.get("wr", 0)
    status = payload.get("st", "")
    rst, width = ("", 16) if compact else ("rst ", 20)

    return title + [
        f"Sess {s:>3}%  {rst}{_fmt_reset(sr)}",
        f"Week {w:>3}%  {rst}{_fmt_reset(wr)}",
        _status_line(status, activity)[:width],
    ]
