"""What Claude Code is doing right now, from its hooks, for the LCD's 4th line.

Stdlib only: Claude Code runs this file on every hook event, outside the venv.

  claude_state.py --install    register the hooks in Claude Code's settings.json
  claude_state.py --uninstall  remove them again (nothing else is touched)
  claude_state.py --status     print the current state
  claude_state.py --hook       what the hooks run: reads the event JSON from
                               stdin, writes one small file per session

The daemon folds those files into one state with current_state().

The state files live under the home directory, not %LOCALAPPDATA%: the Claude
desktop app is an MSIX package, and everything it starts (Claude Code, and
therefore this hook) gets its AppData writes redirected into the package's
private LocalCache, where the daemon would never see them.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

STATE_DIR = Path.home() / ".config" / "claude-g510" / "sessions"
HOOK_MARK = "claude_state.py"

HOOK_EVENTS = (
    "UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure",
    "PermissionRequest", "Notification", "Stop", "SessionEnd",
)
TOOL_EVENTS = ("PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionRequest")

NEEDS, WORKING, DONE = "needs", "working", "done"
LABELS = {NEEDS: "Needs you!", WORKING: "Working...", DONE: "Your turn"}
# Highest first: one session waiting on you beats five busy ones.
PRIORITY = (NEEDS, WORKING, DONE)
# How long a state holds without a newer event. Working needs a ceiling
# because an interrupted turn (Esc) fires no Stop hook.
STALE_AFTER = {NEEDS: 30 * 60, WORKING: 5 * 60, DONE: 3 * 60}
FORGET_AFTER = 6 * 3600


def settings_path() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(base) if base else Path.home() / ".claude") / "settings.json"


# ---- hook side ---------------------------------------------------------------


def state_for(event: dict) -> str | None:
    """State one hook event puts its session into; None keeps the old one."""
    name = event.get("hook_event_name") or ""
    if name in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure"):
        return WORKING
    if name == "PermissionRequest":
        # Fires as the dialog (or a question to you) opens; the desktop app's
        # permission_prompt Notification arrives seconds later.
        return NEEDS
    if name == "Stop":
        return DONE
    if name == "Notification":
        kind = (event.get("notification_type") or "").lower()
        msg = (event.get("message") or "").lower()
        if kind == "permission_prompt" or "permission" in msg:
            return NEEDS
        if kind == "idle_prompt" or "waiting for your input" in msg:
            return DONE
    return None


def handle_hook(raw: str, state_dir: Path = STATE_DIR, now: float | None = None) -> None:
    event = json.loads(raw)
    sid = "".join(c for c in str(event.get("session_id") or "") if c.isalnum() or c in "-_")
    if not sid:
        return
    path = state_dir / f"{sid}.json"
    if event.get("hook_event_name") == "SessionEnd":
        path.unlink(missing_ok=True)
        return
    state = state_for(event)
    if state is None:
        return
    state_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"state": state, "ts": time.time() if now is None else now}))
    os.replace(tmp, path)


# ---- daemon side -------------------------------------------------------------


def current_state(state_dir: Path = STATE_DIR, now: float | None = None) -> str | None:
    """The most urgent live state over all sessions, or None when idle."""
    now = time.time() if now is None else now
    best = None
    try:
        files = list(state_dir.glob("*.json"))
    except OSError:
        return None
    for f in files:
        try:
            data = json.loads(f.read_text())
            state, age = str(data["state"]), now - float(data["ts"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if age > FORGET_AFTER:
            f.unlink(missing_ok=True)
            continue
        if state not in PRIORITY or age >= STALE_AFTER[state]:
            continue
        if best is None or PRIORITY.index(state) < PRIORITY.index(best):
            best = state
    return best


# ---- settings.json -----------------------------------------------------------


def hook_command() -> str:
    """Claude Code starts the hook as its own process on every tool call, so
    use the base interpreter's pythonw.exe: python.exe would flash a console
    window each time, and a venv's pythonw is a stub that relaunches the
    console one. Forward slashes mean the same in cmd.exe and Git Bash."""
    pythonw = Path(sys.base_exec_prefix) / "pythonw.exe"
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{exe.as_posix()}" "{Path(__file__).resolve().as_posix()}" --hook'


def _is_ours(hook: object) -> bool:
    cmd = str(hook.get("command", "")) if isinstance(hook, dict) else ""
    return HOOK_MARK in cmd and "--hook" in cmd


def set_installed(on: bool, path: Path | None = None) -> Path:
    # UTF-8 explicitly: the locale code page would mangle non-ASCII settings.
    path = path or settings_path()
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        settings = {}
    hooks = settings.get("hooks") if isinstance(settings.get("hooks"), dict) else {}
    for ev in HOOK_EVENTS:
        groups = []
        for g in hooks.get(ev) or []:
            if not isinstance(g, dict):
                groups.append(g)
                continue
            kept = [h for h in g.get("hooks") or [] if not _is_ours(h)]
            if kept:
                groups.append({**g, "hooks": kept})
        if on:
            group = {"hooks": [{"type": "command", "command": hook_command(), "timeout": 5}]}
            groups.append({"matcher": "*", **group} if ev in TOOL_EVENTS else group)
        if groups:
            hooks[ev] = groups
        else:
            hooks.pop(ev, None)
    if hooks:
        settings["hooks"] = hooks
    else:
        settings.pop("hooks", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--hook":
        # Must never fail or slow down a Claude Code session.
        try:
            raw = sys.stdin.read()
            if not os.environ.get("G510_SKIP_HOOK"):
                handle_hook(raw)
        except Exception:
            pass
        sys.exit(0)
    if arg in ("--install", "--uninstall"):
        where = set_installed(arg == "--install")
        print(f"{'Installed' if arg == '--install' else 'Removed'} G510 hooks in {where}")
        sys.exit(0)
    if arg == "--status":
        print(current_state() or "idle")
        sys.exit(0)
    print("usage: claude_state.py --install | --uninstall | --status | --hook")
    sys.exit(2)
