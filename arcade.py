#!/usr/bin/env python3
"""ASCII ARCADE - a little collection of games for the terminal.

Pick a game with the arrow keys and press Enter; when it ends you are back here.
Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
"""
import math
import os
import random
import subprocess
import sys
import time

import depthwell
from arcadekit import Canvas, Terminal, draw_title, load_scores, mix, overlay, shade, title_width

HERE = os.path.dirname(os.path.abspath(__file__))

GAMES = [
    dict(file="hoverdrift.py", name="HOVERDRIFT", tag="glide over endless voxel worlds",
         info=["Four vehicles, six worlds: meadows, ice, desert,", "a volcano planet, Planet Xeno, a crystal moon.",
               "Six weapons; shoot balloons, drones and towers."],
         keys="arrows steer   V vehicle   L world   Space fire", size=(40, 12)),
    dict(file="emberfall.py", name="EMBERFALL", tag="a party role-playing adventure",
         info=["Create a hero, gather companions in a tavern,", "fight turn by turn with d20 rules and descend",
               "beneath a mountain where something is waking."],
         keys="arrows move   walk into things   f attack   ? help", size=(100, 30)),
    dict(file="blockfire.py", name="BLOCKFIRE", tag="first-person arena shooter",
         info=["The arena is sealed and the combat bots keep", "coming in waves: drones, sentinels, brutes.",
               "Textured 3D, lit floors, pixel-art robots."],
         keys="W/S move   A/D strafe   arrows turn   Space fire", size=(60, 18)),
    dict(file="deepcall.py", name="DEEPCALL", tag="a submarine alone in the dark",
         info=["Only your sonar shows the trench - and every", "ping can be heard. Find air, salvage and the",
               "Source at the bottom. Keep the deep quiet."],
         keys="arrows steer   Space ping   F focus   L lamp   E flare", size=(60, 20), score="deepcall"),
    dict(file="stackfall.py", name="STACKFALL", tag="falling blocks, ten wide, twenty deep",
         info=["Turn and drop seven kinds of pieces, fill rows", "to melt them away. Marathon, Sprint (40 rows)",
               "and Rising, where rubble pushes up from below."],
         keys="arrows move   Up turn   Space slam   C hold", size=(40, 20), score="stackfall"),
    dict(file="depthwell.py", name="DEPTHWELL", tag="falling blocks in three dimensions",
         info=["Look down into a well and sink cube pieces.", "Turn them about all three axes, fill whole",
               "floor layers. Four well sizes, three piece sets."],
         keys="arrows move   Q/A W/S E/D turn   Space drop", size=(70, 24), score="depthwell"),
]
HELP = [
    "ASCII ARCADE - keys",
    "",
    "Up / Down            choose a game",
    "Enter / Space        play",
    "Esc / Q              quit",
    "",
    "The same in every game:",
    "Esc / P              pause / game menu (Q there: quit)",
    "?                    help with all of the game's keys",
    "Enter / Space        confirm",
    "Arrows / WASD        move, choose",
]
ACCENT = [(236, 84, 84), (244, 150, 56), (236, 212, 70), (130, 214, 76), (56, 200, 160), (60, 170, 236),
          (100, 110, 240), (170, 96, 236), (226, 90, 200)]


# --- little moving previews, one per game ---------------------------------------------------------------
def thumb_hover(cv, x, y, w, h, t):
    for yy in range(h):
        k = yy / h
        if k < 0.55:
            c = mix((58, 116, 204), (178, 210, 238), k / 0.55)
        else:
            c = mix((60, 150, 70), (30, 90, 40), (k - 0.55) / 0.45)
        cv.rect(x, y + yy, w, 1, c)
    for xx in range(w):  # two mountain ranges scrolling past
        a = (xx + t * 6) * 0.11
        m = h * (0.38 + 0.08 * math.sin(a) + 0.05 * math.sin(a * 2.7 + 1))
        cv.rect(x + xx, y + int(m), 1, int(h * 0.55 - m) + 1, (110, 120, 150))
        b = (xx + t * 14) * 0.07
        m2 = h * (0.5 + 0.06 * math.sin(b * 1.3) + 0.04 * math.sin(b * 3.1))
        cv.rect(x + xx, y + int(m2), 1, int(h * 0.62 - m2) + 1, (70, 120, 70))
    sx, sy = x + w * 0.75, y + h * 0.18
    for yy in range(-3, 4):
        for xx in range(-3, 4):
            if xx * xx + yy * yy <= 9:
                cv.set(sx + xx, sy + yy, (255, 246, 210))
    cx, cy = x + w // 2 + int(math.sin(t * 0.8) * w * 0.1), y + int(h * 0.74 + math.sin(t * 2) * 1)
    cv.rect(cx - 5, cy, 11, 2, (214, 64, 52))
    cv.rect(cx - 3, cy - 1, 7, 1, (196, 202, 214))
    cv.rect(cx - 1, cy - 2, 3, 1, (90, 176, 226))
    cv.rect(cx - 6, cy + 2, 13, 1, (62, 64, 76))
    cv.set(cx - 4, cy + 3, (150, 220, 255) if int(t * 10) % 2 else (210, 245, 255))
    cv.set(cx + 4, cy + 3, (150, 220, 255) if int(t * 10) % 2 else (210, 245, 255))


def thumb_ember(cv, x, y, w, h, t):
    for yy in range(h):
        cv.rect(x, y + yy, w, 1, mix((10, 6, 12), (40, 14, 10), yy / h))
    # a mountain with a glowing heart
    for xx in range(w):
        d = abs(xx - w / 2) / (w / 2)
        top = int(h * (0.3 + 0.55 * d))
        cv.rect(x + xx, y + top, 1, h - top, (28, 20, 24))
    rnd = random.Random(int(t * 12))
    for i in range(40):  # flames
        fx = x + w / 2 + rnd.gauss(0, w * 0.08)
        fy = y + h * 0.82 - rnd.random() ** 2 * h * 0.45
        hot = 1 - (y + h * 0.82 - fy) / (h * 0.45)
        cv.set(fx, fy, mix((255, 230, 140), (200, 40, 20), 1 - hot))
    cv.rect(x + int(w * 0.12), y + int(h * 0.66), 3, 6, (90, 70, 60))  # a tiny hero with a torch
    cv.set(x + int(w * 0.12) + 1, y + int(h * 0.62), (255, 180, 80) if int(t * 8) % 2 else (255, 230, 140))


def thumb_stack(cv, x, y, w, h, t):
    cv.rect(x, y, w, h, (14, 15, 26))
    k = max(2, min(w // 10, h // 14))
    bw = 10 * k
    ox = x + (w - bw) // 2
    rnd = random.Random(5)
    cols = ACCENT
    rows = h // k
    for r in range(rows - 5, rows):
        for c in range(10):
            if rnd.random() < 0.8 and c != 7:
                col = rnd.choice(cols)
                cv.rect(ox + c * k, y + r * k, k, k, shade(col, 0.6))
                cv.rect(ox + c * k, y + r * k, k - 1, k - 1, col)
    fall = int(t * 4) % max(1, rows - 6)
    for dx, dy in ((0, 0), (1, 0), (2, 0), (1, 1)):
        cv.rect(ox + (3 + dx) * k, y + (fall + dy) * k, k - 1, k - 1, (206, 92, 206))
    cv.frame(ox - 1, y, bw + 2, h, (64, 72, 112))


def thumb_depth(cv, x, y, w, h, t):
    cv.rect(x, y, w, h, (6, 6, 14))
    g = depthwell.Well((4, 4, 8), depthwell.FLAT)
    rnd = random.Random(2)
    for z in range(5, 8):
        for yy in range(4):
            for xx in range(4):
                g.cell[z][yy][xx] = rnd.random() < 0.9 - (7 - z) * 0.25
    v = depthwell.View(g, x + w / 2, y + h / 2, min(w, h) - 2)
    depthwell.draw_well(cv, v)
    depthwell.draw_cubes(cv, v)
    pz = int(t * 1.5) % 5
    depthwell.wire(cv, v, [(1, 1, pz), (2, 1, pz), (1, 2, pz)], (240, 246, 255))


_BF = []


def thumb_block(cv, x, y, w, h, t):
    """A live look around the BLOCKFIRE arena."""
    if not _BF:
        import blockfire
        blockfire.BEST_FILE = os.devnull
        g = blockfire.Game(seed=1)
        _BF.append(blockfire.Renderer(g))
    r = _BF[0]
    buf = r.scene(w, h, cam=(8.0 - math.cos(t * 0.08) * 6, 19.5, math.sin(t * 0.3) * 0.16))
    for yy in range(h):
        if 0 <= y + yy < cv.H:
            cv.px[y + yy][x:x + w] = buf[yy][:max(0, min(w, cv.W - x))]


_DC = []


def thumb_deep(cv, x, y, w, h, t):
    """DEEPCALL's title cave, pinged every few seconds, squeezed into the preview box."""
    if not _DC:
        import deepcall
        _DC.append(deepcall.TitleDemo())
        _DC.append(t)
    demo = _DC[0]
    dt = min(0.1, max(0.0, t - _DC[1]))
    _DC[1] = t
    import deepcall
    d = demo.d
    if d.t - demo.last > 3.0:
        demo.last = d.t
        d.power = 100
        d.ping(False)
    saved = (d.x, d.y, d.oxygen, d.hull)
    d.update(dt)
    d.x, d.y, d.oxygen, d.hull = saved
    d.vx = d.vy = d.noise = 0.0
    d.over = False
    d.msgs = []
    sub = deepcall.render(d, w, (h + 1) // 2, title_mode=True)
    for yy in range(h):
        if 0 <= y + yy < cv.H:
            cv.px[y + yy][x:x + w] = sub.px[yy][:max(0, min(w, cv.W - x))]


THUMBS = {"deepcall.py": thumb_deep, "hoverdrift.py": thumb_hover, "emberfall.py": thumb_ember, "stackfall.py": thumb_stack,
          "depthwell.py": thumb_depth, "blockfire.py": thumb_block}


def record_line(g):
    if "score" not in g:
        return ""
    rec = load_scores().get(g["score"], {})
    if not rec:
        return "no records yet"
    parts = []
    for mode, v in sorted(rec.items()):
        parts.append("%s %s" % (mode, ("%d:%05.2f" % (v // 60, v % 60)) if mode == "Sprint" else v))
    return "best: " + ",  ".join(parts[:3])


def render(cols, rows, sel, t, note, help_=False):
    cv = Canvas(cols, rows)
    cv.vgradient((8, 6, 18), (24, 10, 30))
    rnd = random.Random(11)
    for i in range(90):  # drifting stars
        sx = (rnd.uniform(0, cols) + t * rnd.uniform(1, 4)) % cols
        sy = rnd.uniform(0, cv.H)
        cv.set(sx, sy, mix((60, 60, 90), (220, 220, 255), rnd.random() * (0.6 + 0.4 * math.sin(t * 2 + i))))
    k = 3
    while k > 1 and title_width("ASCII ARCADE", k) > cols - 4:
        k -= 1
    tw = title_width("ASCII ARCADE", k)
    wave = [ACCENT[(i + int(t * 3)) % len(ACCENT)] for i in range(12)]
    draw_title(cv, "ASCII ARCADE", (cols - tw) // 2, 3, k, wave)
    top = (3 + 5 * k) // 2 + 2
    cv.center(top, "a little game collection for your terminal", (180, 180, 204))
    # list on the left, preview and details on the right
    lw = 40
    tw2 = min(60, cols - lw - 8)
    lx = max(2, (cols - lw - tw2 - 4) // 2)
    rx = lx + lw + 4
    ly = top + 3
    # tighter list on small windows: names with taglines and gaps, then without gaps, then names only
    step = next((k for k in (3, 2) if ly + k * len(GAMES) < rows - 1), 1)
    for i, g in enumerate(GAMES):
        r = ly + i * step
        if i == sel:
            cv.put(lx, r, (" > %s" % g["name"]).ljust(lw), (14, 14, 20), ACCENT[(i * 2 + 2) % len(ACCENT)])
            if step > 1:
                cv.put(lx, r + 1, ("   " + g["tag"]).ljust(lw)[:lw], (230, 230, 240), (30, 26, 52))
        else:
            cv.put(lx, r, ("   %s" % g["name"]).ljust(lw), (220, 220, 232), (20, 18, 36))
            if step > 1:
                cv.put(lx, r + 1, ("   " + g["tag"]).ljust(lw)[:lw], (140, 140, 166), (20, 18, 36))
    g = GAMES[sel]
    th = max(8, min(2 * (rows - ly - 9), 30))
    if tw2 >= 20:
        THUMBS[g["file"]](cv, rx, ly * 2, tw2, th, t)
        cv.frame(rx - 1, ly * 2 - 1, tw2 + 2, th + 2, (90, 90, 140))
        r = ly + th // 2 + 2
        for j, line in enumerate(g["info"]):
            cv.put(rx, r + j, line[:tw2], (220, 220, 232))
        cv.put(rx, r + 4, g["keys"][:tw2], (150, 154, 184))
        rec = record_line(g)
        if rec:
            cv.put(rx, r + 6, rec[:tw2], (236, 212, 70))
        mc, mr = g["size"]
        if cols < mc or rows < mr:
            cv.put(rx, r + 7, ("needs a %dx%d window (now %dx%d)" % (mc, mr, cols, rows))[:tw2], (255, 120, 100))
    if note:
        cv.center(rows - 3, " %s " % note, (14, 14, 20), (255, 150, 100))
    cv.put(0, rows - 1, " Up/Down choose   Enter play   ? help   Esc quit ".ljust(cols)[:cols], (150, 154, 184), (12, 10, 22))
    if help_:
        overlay(cv, HELP)
    return cv


def menu(sel, note):
    with Terminal() as term:
        t0 = time.time()
        help_ = False
        while True:
            cols, rows = term.size()
            if cols < 60 or rows < 20:
                term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (60x20).")
                term.keys(0.3)
                continue
            term.write(render(cols, rows, sel, time.time() - t0, note, help_).emit())
            for k in term.keys(1 / 20):
                note = ""
                if help_:            # any key closes the help
                    help_ = False
                    continue
                if k == "?":
                    help_ = True
                elif k in ("q", "esc"):
                    return None
                if k in ("up", "w", "k"):
                    sel = (sel - 1) % len(GAMES)
                elif k in ("down", "s", "j", "tab"):
                    sel = (sel + 1) % len(GAMES)
                elif k in ("1", "2", "3", "4", "5", "6"):
                    sel = min(len(GAMES) - 1, int(k) - 1)
                elif k in ("enter", " "):
                    return sel


def main():
    sel, note = 0, ""
    while True:
        sel = menu(sel, note)
        if sel is None:
            return
        g = GAMES[sel]
        t = time.time()
        code = subprocess.call([sys.executable, os.path.join(HERE, g["file"])], cwd=HERE)
        note = "" if code == 0 or time.time() - t > 3 else "%s ended unexpectedly (exit code %d)" % (g["name"], code)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
