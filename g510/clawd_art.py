"""Anthropic's official Clawd animations on the G510's monochrome LCD.

The art is Anthropic's and is not part of this repository. It is read at
runtime from $G510_CLAWD_DIR, or from a Clawdmeter checkout next to the g510
folder (Clawdmeter/research/clawd-official, gitignored). Without the files, or
without Pillow, load() returns None and the daemon keeps the plain text display.

The official core files draw Clawd on a 55x37 cell stage (2750x1850 px, 50 px
per cell, every animation at the same idle position). Clawd is drawn in 2x2
cell blocks, so scaling by 1.5 keeps the art crisp (3x3 px blocks, 36x24 px in
all). A cell is lit when it is opaque and not dark: the eyes are transparent
holes in the GIFs and near-black in the PNG.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

LCD_W, LCD_H = 160, 43
STAGE_W, STAGE_H = 55, 37
# Stage cells shown: every column the animations reach; rows from just
# below the top of the highest jump. Both start on Clawd's block grid.
STAGE_X0, STAGE_X1 = 5, 45
STAGE_Y0 = 7
ART_W, ART_H = (STAGE_X1 - STAGE_X0) * 3 // 2, (STAGE_H - STAGE_Y0) * 3 // 2
ART_X, ART_Y = LCD_W - ART_W, LCD_H - ART_H  # bottom right, top clipped
TEXT_X, TEXT_Y, LINE_H = 1, 2, 14  # three lines of the 6x11 bitmap font
STILL_MS = 1000  # how often to look again while a still picture is shown

# claude_state's states (plus "limit" and None for idle) to official files
FILES = {
    None: "Clawd-Still.png",
    "limit": "Clawd-Still.png",
    "needs": "Clawd-Pointing.gif",
    "working": "Clawd-CrabWalking.gif",
    "done": "Clawd-JumpingHappy.gif",
}


def art_dir() -> Path:
    env = os.environ.get("G510_CLAWD_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "Clawdmeter" / "research" / "clawd-official"


class ClawdArt:
    def __init__(self, frames: dict, font) -> None:
        self._frames = frames  # state -> [(1-bit stage image, ms)]
        self._font = font

    def _animation(self, state: str | None) -> list:
        return self._frames.get(state) or self._frames[None]

    def frame_count(self, state: str | None) -> int:
        return len(self._animation(state))

    def frame(self, state: str | None, index: int):
        """(image, ms) for frame `index` of the state's animation, looping."""
        frames = self._animation(state)
        return frames[index % len(frames)]

    def compose(self, lines: list[str], art) -> bytes:
        """160x43 bitmap, one byte per pixel (255 = lit), for LogiLcdMonoSetBackground."""
        from PIL import Image, ImageDraw

        screen = Image.new("L", (LCD_W, LCD_H), 0)
        draw = ImageDraw.Draw(screen)
        for i, line in enumerate(lines[:3]):
            draw.text((TEXT_X, TEXT_Y + i * LINE_H), line, fill=255, font=self._font)
        screen.paste(255, (ART_X, ART_Y), art)
        return screen.tobytes()


def _to_stage(frame):
    """One RGBA frame of the official art to a 1-bit ART_W x ART_H mask."""
    from PIL import Image

    # NEAREST samples each cell's center, so this is one value per cell.
    stage = frame.convert("RGBA").resize((STAGE_W, STAGE_H), Image.NEAREST)
    cells = stage.crop((STAGE_X0, STAGE_Y0, STAGE_X1, STAGE_H))
    opaque = cells.getchannel("A").point(lambda a: 255 if a > 128 else 0)
    bright = cells.convert("L").point(lambda v: 255 if v > 60 else 0)
    lit = Image.new("1", cells.size, 0)
    lit.paste(1, (0, 0), Image.composite(bright, Image.new("L", cells.size, 0), opaque))
    return lit.resize((ART_W, ART_H), Image.NEAREST)


def load(log: Callable[[str], None]) -> ClawdArt | None:
    try:
        from PIL import Image, ImageFont, ImageSequence
    except ImportError:
        log("Pillow not installed; no Clawd animation (pip install pillow)")
        return None
    folder = art_dir()
    frames = {}
    for state, name in FILES.items():
        try:
            with Image.open(folder / name) as im:
                frames[state] = [
                    (_to_stage(f), f.info.get("duration") or STILL_MS)
                    for f in ImageSequence.Iterator(im)
                ]
        except OSError as e:
            log(f"Clawd art not found ({e}); showing text only. "
                f"Set G510_CLAWD_DIR to the folder with the official Clawd files.")
            return None
    log(f"Clawd art loaded from {folder}")
    return ClawdArt(frames, ImageFont.load_default_imagefont())
