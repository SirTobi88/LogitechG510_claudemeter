"""Maps a usage payload dict to 4 G510 LCD text lines.

Pure function, no SDK/hardware dependency -- easy to unit test on its own.
Payload fields as returned by claude_api.poll_api():
s = session %, sr = session reset (min), w = weekly %, wr = weekly reset (min),
st = status string, ok = success flag.
"""

from __future__ import annotations


def _fmt_reset(minutes: int) -> str:
    """Compact reset countdown that always fits the 20-char line budget."""
    if minutes < 60:
        return f"{minutes}m"
    if minutes < 1440:
        return f"{minutes // 60}h{minutes % 60:02d}"
    return f"{minutes // 1440}d{(minutes % 1440) // 60}h"


def render_lines(payload: dict | None) -> list[str]:
    if payload is None:
        return ["Claude Usage", "", "No data yet", ""]

    if not payload.get("ok", False):
        return ["Claude Usage", "", "No data", "run claude login"]

    s = payload.get("s", 0)
    sr = payload.get("sr", 0)
    w = payload.get("w", 0)
    wr = payload.get("wr", 0)
    status = payload.get("st", "")

    return [
        "Claude Usage",
        f"Sess {s:>3}%  rst {_fmt_reset(sr)}",
        f"Week {w:>3}%  rst {_fmt_reset(wr)}",
        status[:20],
    ]
