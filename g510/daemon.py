#!/usr/bin/env python3
"""Claude usage on the Logitech G510 LCD.

Polls the Anthropic API every POLL_INTERVAL seconds for the same
rate-limit utilization data and renders it
on the G510's built-in monochrome LCD via the Logitech LCD SDK (LGS).

Run in the foreground:  python g510/daemon.py
Stop with Ctrl+C -- this releases the LCD back to LGS cleanly.
"""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
import os
import sys
from pathlib import Path

from claude_api import AuthError, poll_api, read_token
from lcd_sdk import LcdSdkUnavailable, LogitechLcd
from render import render_lines

POLL_INTERVAL = 60
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


async def run() -> None:
    try:
        lcd = LogitechLcd("Claude Usage")
    except LcdSdkUnavailable as e:
        log.error(str(e))
        sys.exit(1)

    log.info("=== Claude Usage on G510 LCD ===")
    log.info(f"Poll interval: {POLL_INTERVAL}s")

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

            token = read_token()
            payload = None
            if not token:
                log.warning("No Claude Code token found; showing 'No data'")
                payload = {"ok": False}
            else:
                try:
                    payload = await poll_api(token)
                except AuthError:
                    log.warning("Token expired/invalid; run `claude login`")
                    payload = {"ok": False}
                if payload is None:
                    # Transient failure (network/DNS/timeout/5xx) -- keep last
                    # displayed values on screen, just log and retry next tick.
                    log.info("Transient API failure; leaving display unchanged")
                    await asyncio.sleep(POLL_INTERVAL)
                    continue

            lines = render_lines(payload)
            lcd.set_lines(lines)
            log.info(f"Updated: {lines}")
            await asyncio.sleep(POLL_INTERVAL)
    except (KeyboardInterrupt, asyncio.CancelledError):
        log.info("Stopping")
    finally:
        lcd.shutdown()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
