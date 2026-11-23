#!/usr/bin/env python3
"""Render README screenshots straight from the games' own canvases (no terminal needed).

    python3 scripts/screenshots.py            # writes docs/screenshots/*.png

Needs Pillow (pip install pillow) and a monospace font (Menlo on macOS, DejaVu Sans Mono elsewhere).
Each terminal cell becomes CW x CH image pixels: two square half-block pixels, or one character.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
os.environ.setdefault("COLORTERM", "truecolor")

import arcadekit  # noqa: E402

arcadekit.SOLID_PIXELS = False
OUT = os.path.join(HERE, "docs", "screenshots")
CW, CH = 10, 20
FONTS = ["/System/Library/Fonts/Menlo.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]


def font(size):
    for f in FONTS:
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


_FONTS = {}


def to_image(cv, CW=CW, CH=CH):
    size = CH * 4 // 5
    FONT = _FONTS.setdefault(size, font(size))
    img = Image.new("RGB", (cv.cols * CW, cv.rows * CH))
    d = ImageDraw.Draw(img)
    for y in range(cv.H):
        row = cv.px[y]
        for x in range(cv.W):
            d.rectangle([x * CW, y * CH // 2, x * CW + CW - 1, y * CH // 2 + CH // 2 - 1], fill=tuple(row[x]))
    for (x, j), (ch, fg, bg) in cv.text.items():
        if bg is None:
            bg = arcadekit.mix(cv.px[2 * j][x], cv.px[2 * j + 1][x], 0.5)
        d.rectangle([x * CW, j * CH, x * CW + CW - 1, j * CH + CH - 1], fill=tuple(bg))
        if ch == "▀":
            d.rectangle([x * CW, j * CH, x * CW + CW - 1, j * CH + CH // 2 - 1], fill=tuple(fg))
        elif ch == "▄":
            d.rectangle([x * CW, j * CH + CH // 2, x * CW + CW - 1, j * CH + CH - 1], fill=tuple(fg))
        elif ch == "█":
            d.rectangle([x * CW, j * CH, x * CW + CW - 1, j * CH + CH - 1], fill=tuple(fg))
        elif ch != " ":
            d.text((x * CW + CW // 2, j * CH + CH // 2), ch, fill=tuple(fg), font=FONT, anchor="mm")
    return img


def save(cv, name):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name + ".png")
    to_image(cv).save(path, optimize=True)
    print(path)


def start_gif(arcade, cols=100, rows=32, seconds=8.8, fps=10):
    """The start screen as an animated GIF: the previews running, the highlight walking along."""
    frames = []
    for i in range(int(seconds * fps)):
        t = 6.0 + i / fps
        img = to_image(arcade.render_start(cols, rows, t, int(t / 2.2) % len(arcade.GAMES)), 8, 16)
        frames.append(img.convert("P", palette=Image.ADAPTIVE, colors=255))
    path = os.path.join(OUT, "start.gif")
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=int(1000 / fps), loop=0, optimize=True)
    print(path)


def preview(arcade, g, cols, rows, seconds, dt=1 / 30):
    """The game's live preview from the launcher (its own demo), run for a while so the scene is in full swing."""
    cv = None
    for i in range(int(seconds / dt) + 1):
        cv = arcadekit.Canvas(cols, rows)
        arcade.THUMBS[g["file"]](cv, 0, 0, cols, rows * 2, i * dt)
    return cv


if __name__ == "__main__":
    which = sys.argv[1:]
    import arcade
    if not which or "start" in which:
        cv = None
        for i in range(200):                      # let the previews run for a while
            cv = arcade.render_start(120, 40, 6.0 + i / 30, 2)
        save(cv, "start")
    if not which or "gif" in which:
        start_gif(arcade)
    if not which or "menu" in which:
        save(arcade.render(120, 40, 0, 4.0, ""), "menu")
    for g in arcade.GAMES:
        mod = g["file"][:-3]
        if which and mod not in which:
            continue
        m = __import__(mod)
        if hasattr(m, "screenshot"):          # the game's own pick: real play with its HUD, at a good moment
            save(m.screenshot(100, 32), mod)
        else:
            save(preview(arcade, g, 80, 25, 12.0), mod)
