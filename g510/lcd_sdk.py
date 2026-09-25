"""ctypes bindings for the Logitech LCD SDK (LogitechLcd.dll).

The G510's monochrome LCD (160x43 px, 4 text lines of 20 chars) is only
reachable through Logitech Gaming Software (LGS) -- the newer G HUB does not
support the G510 at all. LGS does NOT add its SDK folder to the system PATH,
so the DLL has to be located explicitly under LGS's install directory
(observed: "C:\\Program Files\\Logitech Gaming Software\\SDK\\LCD\\x64\\" and
"...\\x86\\", one DLL per architecture -- pick the one matching this Python's
bitness).

Reference: Logitech LCD SDK docs (LogiLcd* functions), LOGI_LCD_MONO_WIDTH=160,
LOGI_LCD_MONO_HEIGHT=43.
"""

from __future__ import annotations

import ctypes
import os
import struct
import sys
from pathlib import Path

LOGI_LCD_TYPE_MONO = 0x00000001
LOGI_LCD_TYPE_COLOR = 0x00000002

LOGI_LCD_MONO_WIDTH = 160
LOGI_LCD_MONO_HEIGHT = 43
LOGI_LCD_MONO_BUTTON_0 = 0x00000001
LOGI_LCD_MONO_BUTTON_1 = 0x00000002
LOGI_LCD_MONO_BUTTON_2 = 0x00000004
LOGI_LCD_MONO_BUTTON_3 = 0x00000008

MONO_LINE_COUNT = 4
MONO_LINE_WIDTH = 20


class LcdSdkUnavailable(Exception):
    """Raised when LogitechLcd.dll cannot be loaded (LGS not installed)."""


def _candidate_dll_paths() -> list[Path]:
    """Where to look for LogitechLcd.dll, in order.

    1. Bare name -- works if it's ever on PATH after all.
    2. LGS's SDK folder for this interpreter's bitness (64-bit Python needs
       the x64 build, 32-bit Python needs x86 -- they are not interchangeable).
    3. The other bitness's folder, as a last resort (will fail to load with a
       clear "not a valid Win32 application" from ctypes if it's really a
       mismatch, which is still more informative than "file not found").
    """
    arch_dir = "x64" if struct.calcsize("P") * 8 == 64 else "x86"
    other_dir = "x86" if arch_dir == "x64" else "x64"
    program_files_dirs = {
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    }
    candidates = [Path("LogitechLcd.dll")]
    for base in program_files_dirs:
        for sub in (arch_dir, other_dir):
            candidates.append(
                Path(base) / "Logitech Gaming Software" / "SDK" / "LCD" / sub / "LogitechLcd.dll"
            )
    return candidates


class LogitechLcd:
    """Thin wrapper around LogitechLcd.dll's mono text API.

    Not a context manager on purpose: init()/shutdown() failures must be
    logged by the caller rather than silently swallowed, matching how the
    rest of the daemon treats a missing device as "not connected", not a
    crash.
    """

    def __init__(self, applet_name: str = "Claude Usage") -> None:
        if sys.platform != "win32":
            raise LcdSdkUnavailable("Logitech LCD SDK is Windows-only")
        self._dll = None
        errors: list[str] = []
        for path in _candidate_dll_paths():
            try:
                self._dll = ctypes.WinDLL(str(path))
                break
            except OSError as e:
                errors.append(f"{path}: {e}")
        if self._dll is None:
            hint = (
                "LogitechLcd.dll could not be loaded from PATH or the LGS SDK "
                "folder. Is Logitech Gaming Software (LGS) installed? Tried:\n  "
                + "\n  ".join(errors)
            )
            raise LcdSdkUnavailable(hint)
        self._applet_name = applet_name
        self._initialized = False

        self._dll.LogiLcdInit.argtypes = [ctypes.c_wchar_p, ctypes.c_int]
        self._dll.LogiLcdInit.restype = ctypes.c_bool
        self._dll.LogiLcdIsConnected.argtypes = [ctypes.c_int]
        self._dll.LogiLcdIsConnected.restype = ctypes.c_bool
        self._dll.LogiLcdMonoSetText.argtypes = [ctypes.c_int, ctypes.c_wchar_p]
        self._dll.LogiLcdMonoSetText.restype = ctypes.c_bool
        self._dll.LogiLcdUpdate.argtypes = []
        self._dll.LogiLcdUpdate.restype = None
        self._dll.LogiLcdShutdown.argtypes = []
        self._dll.LogiLcdShutdown.restype = None

    def init(self) -> bool:
        """Register with LGS as the active LCD applet. Idempotent."""
        self._initialized = bool(self._dll.LogiLcdInit(self._applet_name, LOGI_LCD_TYPE_MONO))
        return self._initialized

    def is_connected(self) -> bool:
        if not self._initialized:
            return False
        return bool(self._dll.LogiLcdIsConnected(LOGI_LCD_TYPE_MONO))

    def set_lines(self, lines: list[str]) -> bool:
        """Write up to 4 lines (truncated to 20 chars each) and push the update."""
        ok = True
        for i in range(MONO_LINE_COUNT):
            text = lines[i][:MONO_LINE_WIDTH] if i < len(lines) else ""
            ok = bool(self._dll.LogiLcdMonoSetText(i, text)) and ok
        self._dll.LogiLcdUpdate()
        return ok

    def shutdown(self) -> None:
        if self._initialized:
            self._dll.LogiLcdShutdown()
            self._initialized = False
