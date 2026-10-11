#!/usr/bin/env python3
"""Render the README's LCD previews into docs/ with the daemon's own code.

  python g510/preview.py

Needs the official Clawd art (see clawd_art.py). The pictures contain that
art, so they are Anthropic's and not covered by this repository's license.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

import clawd_art
from claude_state import LABELS
from render import render_lines

OUT = Path(__file__).resolve().parent.parent / "docs"
SCALE, BORDER = 3, 6
INK, GLASS = (32, 32, 32), (200, 204, 196)
SAMPLE = {"ok": True, "s": 45, "sr": 120, "w": 28, "wr": 7200, "st": "allowed"}


def lcd_image(bitmap: bytes) -> Image.Image:
    mask = Image.frombytes("L", (clawd_art.LCD_W, clawd_art.LCD_H), bitmap)
    screen = Image.new("RGB", mask.size, GLASS)
    screen.paste(INK, (0, 0), mask)
    w, h = mask.width * SCALE, mask.height * SCALE
    framed = Image.new("RGB", (w + 2 * BORDER, h + 2 * BORDER), GLASS)
    framed.paste(screen.resize((w, h), Image.NEAREST), (BORDER, BORDER))
    return framed


def main() -> None:
    art = clawd_art.load(print)
    if art is None:
        sys.exit(1)
    OUT.mkdir(exist_ok=True)
    for name, state, payload in [
        ("idle", None, SAMPLE),
        ("working", "working", SAMPLE),
        ("needs", "needs", SAMPLE),
        ("done", "done", SAMPLE),
        ("limit", "limit", {**SAMPLE, "s": 100, "st": "rejected"}),
    ]:
        lines = render_lines(payload, LABELS.get(state), compact=True)
        frames = [art.frame(state, i) for i in range(art.frame_count(state))]
        images = [lcd_image(art.compose(lines, image)) for image, _ in frames]
        if len(images) == 1:
            path = OUT / f"lcd-{name}.png"
            images[0].save(path)
        else:
            path = OUT / f"lcd-{name}.gif"
            images[0].save(path, save_all=True, append_images=images[1:],
                            duration=[ms for _, ms in frames], loop=0, optimize=True)
        print(path)


if __name__ == "__main__":
    main()
