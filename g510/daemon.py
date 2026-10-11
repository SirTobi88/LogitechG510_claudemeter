#!/usr/bin/env python3
"""Claude usage on the Logitech G510 LCD.

Polls the Anthropic API every POLL_INTERVAL seconds for the same
rate-limit utilization data and renders it
on the G510's built-in monochrome LCD via the Logitech LCD SDK (LGS).
Between polls it redraws so the status line, and the Clawd animation when
the official art is available (clawd_art.py), follow Claude Code's state
from its hooks (claude_state.py).

Run in the foreground:  python g510/daemon.py
Stop with Ctrl+C -- this releases the LCD back to LGS cleanly.
"""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
import os
import sys
import time
from pathlib import Path

import clawd_art
import cli_renew
from claude_api import AuthError, poll_api, read_token
from claude_state import LABELS, current_state
from lcd_sdk import LcdSdkUnavailable, LogitechLcd
from render import render_lines

POLL_INTERVAL = 60
TICK = 1  # redraw interval in text mode; animations use their frame times
STATE_INTERVAL = 0.5  # how often to read the hook state files
RETRY_INTERVAL = 5  # how often to retry while LGS/device is unavailable


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("g510.daemon")
    if logger.handlers:
        return logger
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    path = base / "ClaudeG510" / "g510.log"
    logger.setLevel(logging.INFO)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=512 * 1024, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S"))
        logger.addHandler(handler)
    except OSError:
        pass  # best-effort -- logging must never stop the daemon
    if sys.stderr is not None:  # None under pythonw.exe (autostart)
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", "%H:%M:%S"))
        logger.addHandler(console)
    return logger


log = _build_logger()


async def fetch_usage() -> dict | None:
    """Usage payload, {"ok": False} when there is no valid token, or None for
    a transient failure (keep showing the last values)."""
    token = read_token()
    if not token:
        log.warning("No Claude Code token found; showing 'No data'")
        return {"ok": False}
    try:
        return await poll_api(token)
    except AuthError as e:
        # A 403 is not an expired token; renewing would only bill a request.
        if e.status == 401 and await cli_renew.renew(log.info):
            token = read_token()
            if token:
                try:
                    return await poll_api(token)
                except AuthError:
                    pass
    log.warning("Token expired/invalid; run `claude login`")
    return {"ok": False}


async def poll_forever(usage: dict) -> None:
    """Keeps usage["payload"] current. A task of its own, so a slow request or
    a CLI renewal never stalls the animation."""
    while True:
        fresh = await fetch_usage()
        if fresh is None:
            # Transient failure (network/DNS/timeout/5xx) -- keep the last
            # values on screen and retry at the next poll.
            log.info("Transient API failure; leaving usage unchanged")
        else:
            usage["payload"] = fresh
        await asyncio.sleep(POLL_INTERVAL)


async def run() -> None:
    try:
        lcd = LogitechLcd("Claude Usage")
    except LcdSdkUnavailable as e:
        log.error(str(e))
        sys.exit(1)

    log.info("=== Claude Usage on G510 LCD ===")
    log.info(f"Poll interval: {POLL_INTERVAL}s")

    art = clawd_art.load(log.info)
    usage = {"payload": None}
    poller = asyncio.create_task(poll_forever(usage))
    state, state_read = None, None
    anim, frame_index = None, 0
    shown = None
    try:
        while True:
            if not lcd.is_connected():
                lcd.init()
                if not lcd.is_connected():
                    log.warning(
                        "G510 LCD not connected (is LGS running and the keyboard plugged in?)"
                    )
                    await asyncio.sleep(RETRY_INTERVAL)
                    continue
                log.info("Connected to G510 LCD")
                shown = None

            if state_read is None or time.monotonic() - state_read >= STATE_INTERVAL:
                state, state_read = current_state(), time.monotonic()
            payload = usage["payload"]
            lines = render_lines(payload, LABELS.get(state) if state else None)
            if lines != shown:
                log.info(f"Updated: {lines}")
                shown = lines

            if art is None:
                lcd.set_lines(lines)
                await asyncio.sleep(TICK)
                continue
            limit = bool(payload and payload.get("ok") and payload.get("st") == "rejected")
            wanted = "limit" if limit else state
            if wanted != anim:
                anim, frame_index = wanted, 0
            image, ms = art.frame(anim, frame_index)
            frame_index += 1
            compact = render_lines(payload, LABELS.get(state) if state else None, compact=True)
            lcd.set_bitmap(art.compose(compact, image))
            await asyncio.sleep(ms / 1000)
    except (KeyboardInterrupt, asyncio.CancelledError):
        log.info("Stopping")
    finally:
        poller.cancel()
        lcd.shutdown()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
