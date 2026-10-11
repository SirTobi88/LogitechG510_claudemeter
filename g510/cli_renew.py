"""Let the Claude CLI renew an expired OAuth token.

The daemon never refreshes the token itself: that would race Claude Code's own
rotation (two refreshers, one refresh token). But the token usually only goes
stale because no Claude Code has run for a while, and Claude Code renews it
whenever it starts and finds it expired. So on a 401 the daemon runs the CLI
once with the smallest request it accepts and then reads the token again.

Only `claude login` helps when the sign-in itself has expired; the cooldown
keeps that case from starting a CLI on every poll.
Set G510_NO_CLI_RENEW=1 to turn this off.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

COOLDOWN = 15 * 60  # seconds between attempts
TIMEOUT = 120
# Haiku, no tools, no MCP servers, nothing saved, no hooks: the run must not
# show up anywhere as the user working. Not --bare: that skips OAuth, which is
# the whole point of the run.
ARGS = [
    "-p", "Reply with OK.",
    "--model", "haiku",
    "--tools", "",
    "--strict-mcp-config",
    "--no-session-persistence",
    "--settings", '{"disableAllHooks": true}',
]
# Belt and braces for a CLI that would ignore disableAllHooks: our own hook
# (claude_state.py) and Clawdmeter's both stand down when they see these.
SKIP_HOOK_ENV = {"G510_SKIP_HOOK": "1", "CLAWDMETER_SKIP_HOOK": "1"}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_last_attempt: float | None = None


def find_cli() -> list[str] | None:
    """Command that starts the Claude CLI: PATH, then the native installer's
    ~/.local/bin. An npm install is a batch shim (claude.cmd); cmd.exe would
    mangle the JSON --settings and the empty --tools argument, so run the
    package's cli.js with node directly, as the shim does."""
    found = shutil.which("claude")
    path = Path(found) if found else Path.home() / ".local" / "bin" / "claude.exe"
    if not path.is_file():
        return None
    if path.suffix.lower() == ".exe":
        return [str(path)]
    script = path.parent / "node_modules" / "@anthropic-ai" / "claude-code" / "cli.js"
    node = path.parent / "node.exe"
    node_cmd = str(node) if node.is_file() else shutil.which("node")
    if script.is_file() and node_cmd:
        return [node_cmd, str(script)]
    return None


def _kill_tree(proc: asyncio.subprocess.Process) -> None:
    """proc.kill() would end the CLI only, not what it started."""
    try:
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
            capture_output=True, timeout=10, creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        pass
    if proc.returncode is None:
        try:
            proc.kill()
        except ProcessLookupError:
            pass


async def renew(log: Callable[[str], None]) -> bool:
    """Run the CLI once. True when it exited cleanly; the caller then reads
    the token again."""
    global _last_attempt
    if os.environ.get("G510_NO_CLI_RENEW"):
        return False
    now = time.monotonic()
    if _last_attempt is not None and now - _last_attempt < COOLDOWN:
        return False
    _last_attempt = now

    cmd = find_cli()
    if not cmd:
        log("Token expired and no claude CLI found to renew it")
        return False
    log("Token expired; letting the Claude CLI renew it (one short `claude -p`)")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, *ARGS,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            cwd=tempfile.gettempdir(),
            env={**os.environ, **SKIP_HOOK_ENV},
            creationflags=NO_WINDOW,
        )
    except OSError as e:
        log(f"Could not start the Claude CLI: {e}")
        return False
    try:
        _, err = await asyncio.wait_for(proc.communicate(), TIMEOUT)
    except asyncio.TimeoutError:
        log(f"Claude CLI did not finish within {TIMEOUT}s; ended it")
        return False
    finally:
        # Timeout or Ctrl+C: never leave the CLI behind.
        if proc.returncode is None:
            _kill_tree(proc)
    if proc.returncode != 0:
        lines = err.decode("utf-8", "replace").strip().splitlines()
        log(f"Claude CLI exited {proc.returncode}: {lines[-1][:200] if lines else ''}")
        return False
    return True
