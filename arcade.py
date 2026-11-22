#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""ASCII ARCADE - a little collection of games for the terminal.

Pick a game with the arrow keys and press Enter; when it ends you are back here.
Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
"""
import math
import os
import random
import subprocess
import sys
import textwrap
import time

import depthwell
from arcadesound import Sound
from arcadekit import (ACCENTS, COPYRIGHT, VERSION, Canvas, Terminal, draw_title, footer, load_scores, mix, overlay, shade,
                       title_width)

HERE = os.path.dirname(os.path.abspath(__file__))

SND = Sound("arcade", {
    "move": [dict(w="square", f=660, d=0.035, v=0.35, duty=0.25)],
    "start": [dict(w="square", f=523, d=0.07, v=0.45), dict(w="square", f=784, d=0.07, v=0.45),
              dict(w="square", f=1047, d=0.2, v=0.5, duty=0.25)],
    "sound_on": [dict(w="tri", f=440, d=0.07), dict(w="tri", f=880, d=0.14)],
    "back": [dict(w="tri", f=660, f2=330, d=0.16, v=0.45)],
})

GAMES = [
    dict(file="hoverdrift.py", name="HOVERDRIFT", tag="glide over endless voxel worlds",
         info=["Four vehicles, six worlds: meadows, ice, desert,", "a volcano planet, Planet Xeno, a crystal moon.",
               "Six weapons; shoot balloons, drones and towers."],
         keys="arrows steer   V vehicle   L world   Space fire", size=(40, 12)),
    dict(file="emberfall.py", name="EMBERFALL", tag="a party role-playing adventure",
         info=["Create a hero, gather companions in a tavern,", "fight turn by turn with d20 rules and descend",
               "beneath a mountain where something is waking."],
         keys="arrows move   walk into things   f attack   ? help", size=(70, 22)),
    dict(file="blockfire.py", name="BLOCKFIRE", tag="first-person arena shooter",
         info=["The arena is sealed and the combat bots keep", "coming in waves: drones, sentinels, brutes.",
               "Textured 3D, lit floors, pixel-art robots."],
         keys="W/S move   A/D strafe   arrows turn   Space fire", size=(60, 18)),
    dict(file="deepcall.py", name="DEEPCALL", tag="a submarine alone in the dark",
         info=["Only your sonar shows the trench - and every", "ping can be heard. Find air, salvage and the",
               "Source at the bottom. Keep the deep quiet."],
         keys="arrows steer   Space ping   F focus   L lamp   E flare", size=(60, 20), score="deepcall"),
    dict(file="lightkeeper.py", name="LIGHTKEEPER", tag="one beam, many ships, a long night",
         info=["Keep the lighthouse through a stormy night:", "light the ships past the reefs, sound the horn,",
               "send the rescue boat. Alone or as two keepers."],
         keys="arrows beam   Space horn   R oil   B boat", size=(70, 22), score="lightkeeper"),
    dict(file="skyshot.py", name="SKYSHOT", tag="an artillery duel on crumbling hills",
         info=["Turn-based cannon duel on ground that breaks", "apart: craters, sliding tanks, wind. Two players",
               "at one keyboard, or alone against the computer."],
         keys="Left/Right angle  Up/Down power  Tab shell  Space fire", size=(70, 22), score="skyshot"),
    dict(file="nightdrive.py", name="NIGHTDRIVE", tag="a race against the clock, after dark",
         info=["Night racing on a winding, hilly highway:", "neon city, coast, forest, desert, mountain",
               "pass and storm. Reach every checkpoint in time."],
         keys="arrows steer   Up gas   Down brake   Esc pause", size=(70, 22), score="nightdrive"),
    dict(file="orbital.py", name="ORBITAL", tag="a calm gravity puzzle among the planets",
         info=["Set angle and power, launch the probe and let", "the planets' gravity bend its path to the dock.",
               "Moons, asteroid belts, wormholes; fewer tries."],
         keys="arrows aim/power   Space launch   R retry   N/B level", size=(70, 22), score="orbital"),
    dict(file="leafling.py", name="LEAFLING", tag="a jump'n'run with a leaf for a hat",
         info=["Run, jump, glide on your leaf and wall-jump", "through a forest canopy, crystal caves, sky",
               "ruins and an autumn storm. Find the seeds."],
         keys="arrows run   Space jump / glide   Down drop", size=(70, 22), score="leafling"),
    dict(file="stackfall.py", name="STACKFALL", tag="falling blocks, ten wide, twenty deep",
         info=["Turn and drop seven kinds of pieces, fill rows", "to melt them away. Marathon, Sprint (40 rows)",
               "and Rising, where rubble pushes up from below."],
         keys="arrows move   Up turn   Space slam   C hold", size=(40, 20), score="stackfall"),
    dict(file="depthwell.py", name="DEPTHWELL", tag="falling blocks in three dimensions",
         info=["Look down into a well and sink cube pieces.", "Turn them about all three axes, fill whole",
               "floor layers. Four well sizes, three piece sets."],
         keys="arrows move   Q/A W/S E/D turn   Space drop", size=(70, 22), score="depthwell"),
]
GENRE = {"hoverdrift.py": "flight", "emberfall.py": "role-playing", "blockfire.py": "shooter", "deepcall.py": "exploration",
         "lightkeeper.py": "action", "skyshot.py": "artillery", "nightdrive.py": "racing", "orbital.py": "puzzle",
         "leafling.py": "platformer", "stackfall.py": "blocks", "depthwell.py": "3D blocks"}
HELP = [
    "ASCII ARCADE - keys",
    "",
    "Up / Down            choose a game",
    "1 - 9, 0             jump to a game (0 again: game 11)",
    "Enter / Space        play",
    "M                    sound on / off",
    "Esc / Q              quit",
    "",
    "The same in every game:",
    "Esc / P              pause / game menu (Q there: quit,",
    "                     M there: sound on / off)",
    "?                    help with all of the game's keys",
    "Enter / Space        confirm",
    "Arrows / WASD        move, choose",
    "",
    "ASCII ARCADE %s  %s" % (VERSION, COPYRIGHT),
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


_LK = []


def thumb_light(cv, x, y, w, h, t):
    """A little stretch of LIGHTKEEPER coast with the beam sweeping round."""
    import lightkeeper
    if not _LK or _LK[0].n.W != w:
        demo = lightkeeper.TitleDemo(w, (h + 1) // 2 + 1)
        _LK[:] = [demo, t]
    demo = _LK[0]
    n = demo.n
    dt = min(0.1, max(0.0, t - _LK[1]))
    _LK[1] = t
    n.spin, n.oil = 0.55, 100
    n.update(dt)
    n.msgs, n.lives, n.over, n.dawn = [], 3, False, False
    if n.t > n.length * 0.6:
        n.t = 10
        n.schedule = sorted(n.rnd.uniform(11, 40) for _ in range(4))
        n.ships = [s for s in n.ships if s.state == "sailing"]
    sub = lightkeeper.render(n, demo.p, w, (h + 1) // 2, title_mode=True)
    for yy in range(h):
        if 0 <= y + yy < cv.H:
            cv.px[y + yy][x:x + w] = sub.px[yy][:max(0, min(w, cv.W - x))]


def thumb_sky(cv, x, y, w, h, t):
    import skyshot
    skyshot.preview(cv, x, y, w, h, t)


_ND, _OR, _LF = [], [], []


def blit_scene(cv, x, y, w, h, sub):
    for yy in range(h):
        if 0 <= y + yy < cv.H:
            cv.px[y + yy][x:x + w] = sub.px[yy][:max(0, min(w, cv.W - x))]


def thumb_night(cv, x, y, w, h, t):
    """NIGHTDRIVE's autopilot on the road."""
    import nightdrive
    if not _ND:
        _ND[:] = [nightdrive.TitleDemo(), t]
    dt = min(0.1, max(0.0, t - _ND[1]))
    _ND[1] = t
    blit_scene(cv, x, y, w, h, _ND[0].scene(w, (h + 1) // 2, dt))


def thumb_orbital(cv, x, y, w, h, t):
    """A probe looping round ORBITAL's ringed planet."""
    import orbital
    if not _OR:
        _OR[:] = [orbital.TitleDemo(), t]
    dt = min(0.1, max(0.0, t - _OR[1]))
    _OR[1] = t
    blit_scene(cv, x, y, w, h, _OR[0].scene(w, (h + 1) // 2, dt))


def thumb_leaf(cv, x, y, w, h, t):
    """Leafling running and gliding through LEAFLING's four worlds."""
    import leafling
    if not _LF:
        _LF[:] = [leafling.TitleDemo(), t]
    dt = min(0.1, max(0.0, t - _LF[1]))
    _LF[1] = t
    blit_scene(cv, x, y, w, h, _LF[0].scene(w, (h + 1) // 2, dt))


THUMBS = {"nightdrive.py": thumb_night, "orbital.py": thumb_orbital, "leafling.py": thumb_leaf, "skyshot.py": thumb_sky, "lightkeeper.py": thumb_light, "deepcall.py": thumb_deep, "hoverdrift.py": thumb_hover, "emberfall.py": thumb_ember, "stackfall.py": thumb_stack,
          "depthwell.py": thumb_depth, "blockfire.py": thumb_block}


def record_line(g):
    if "score" not in g:
        return ""
    rec = load_scores().get(g["score"], {})
    if not rec:
        return "no records yet"
    if g["score"] == "leafling":
        done = sum(1 for k in rec if k.endswith(" time"))
        seeds = sum(bin(v).count("1") for k, v in rec.items() if k.endswith(" seeds"))
        return "best: %d of 12 levels done, %d of 36 seeds" % (done, seeds)
    parts = []
    for mode, v in sorted(rec.items()):
        parts.append("%s %s" % (mode, ("%d:%05.2f" % (v // 60, v % 60)) if mode == "Sprint" else v))
    return "best: " + ",  ".join(parts[:3])


LIST_BG = ((18, 16, 34), (24, 21, 44))      # alternating row bands keep entries apart without extra lines
DIM = (150, 150, 178)                        # secondary text: >= 4.5:1 on the list bands
BADGE_BG = (44, 40, 76)
PANEL, PANEL_FG = (16, 14, 30), (222, 222, 234)                         # backing for the details text, so stars never run through it


def badge(i):
    """The key that reaches game i: 1-9, then 0 for the tenth and 00 (0 pressed twice) for the eleventh."""
    return str(i + 1) if i < 9 else "0" if i == 9 else "00" if i == 10 else " "


def accent(g):
    top, bottom = ACCENTS.get(g["name"], ((240, 240, 250), (160, 160, 190)))
    return mix(top, bottom, 0.3)


def draw_logo(cv, cols, t):
    """ASCII ARCADE in block letters; on narrow windows the two words close up so the logo still fits."""
    wave = [ACCENT[(i + int(t * 3)) % len(ACCENT)] for i in range(12)]
    k = 3
    while k > 1 and title_width("ASCII ARCADE", k) > cols - 4:
        k -= 1
    if title_width("ASCII ARCADE", k) <= cols - 2:
        draw_title(cv, "ASCII ARCADE", (cols - title_width("ASCII ARCADE", k)) // 2, 3, k, wave)
    else:
        w1, w2, gap = title_width("ASCII", 1), title_width("ARCADE", 1), 2
        x = max(0, (cols - (w1 + gap + w2)) // 2)
        draw_title(cv, "ASCII", x, 3, 1, wave[:5])
        draw_title(cv, "ARCADE", x + w1 + gap, 3, 1, wave[6:])
    return k


def render(cols, rows, sel, t, note, help_=False):
    cv = Canvas(cols, rows)
    cv.vgradient((8, 6, 18), (24, 10, 30))
    rnd = random.Random(11)
    for i in range(90):  # drifting stars
        sx = (rnd.uniform(0, cols) + t * rnd.uniform(1, 4)) % cols
        sy = rnd.uniform(0, cv.H)
        cv.set(sx, sy, mix((60, 60, 90), (220, 220, 255), rnd.random() * (0.6 + 0.4 * math.sin(t * 2 + i))))
    k = draw_logo(cv, cols, t)
    top = (3 + 5 * k) // 2 + 2
    cv.center(top, "a little game collection for your terminal", (180, 180, 204))
    # list on the left, preview and details on the right
    lw = 46 if cols >= 116 else 40 if cols >= 96 else 34
    tw2 = min(60, cols - lw - 8)
    lx = max(2, (cols - lw - tw2 - 4) // 2)
    rx = lx + lw + 4
    ly = top + 3 if rows >= 30 else top + 2
    # tighter list on small windows: names with taglines and gaps, then without gaps, then names only
    step = next((k for k in (3, 2) if ly + k * len(GAMES) < rows - 1), 1)
    for i, g in enumerate(GAMES):
        r = ly + i * step
        on = i == sel
        acc = accent(g)
        band = acc if on else LIST_BG[i % 2]
        genre = GENRE.get(g["file"], "")
        b = badge(i)
        cv.put(lx, r, " " * lw, (14, 14, 20), band)
        cv.put(lx + 1, r, b.center(4), acc if on else (220, 220, 236), (14, 14, 22) if on else BADGE_BG)
        cv.put(lx + 6, r, g["name"], (14, 14, 20) if on else (236, 236, 246), band)
        if genre and lw - 6 - len(g["name"]) - len(genre) > 3:
            cv.put(lx + lw - len(genre) - 2, r, genre, shade(acc, 0.32) if on else DIM, band)
        if step > 1:
            tb = mix(LIST_BG[i % 2], acc, 0.18) if on else LIST_BG[i % 2]
            cv.put(lx, r + 1, " " * lw, (14, 14, 20), tb)
            cv.put(lx + 6, r + 1, g["tag"][:lw - 7], (240, 240, 248) if on else DIM, tb)
            if on:
                cv.put(lx, r + 1, " ", acc, acc)
        if step > 2 and i < len(GAMES) - 1:
            cv.put(lx, r + 2, " " * lw, (14, 14, 20), (14, 12, 28))
    g = GAMES[sel]
    acc = accent(g)
    list_bot = ly + len(GAMES) * step - (1 if step > 2 else 0)
    th = max(8, min(2 * (rows - ly - 11), 30, tw2 * 9 // 16 * 2 // 2))
    if tw2 >= 20:
        THUMBS[g["file"]](cv, rx, ly * 2, tw2, th, t)
        cv.frame(rx - 1, ly * 2 - 1, tw2 + 2, th + 2, shade(acc, 0.7))
        r = ly + th // 2 + 2
        bottom = max(list_bot, rows - 3)
        lines = []                                           # (text, fg, indent) in priority order of the space
        mc, mr = g["size"]
        name = g["name"]
        genre = GENRE.get(g["file"], "")
        lines.append(("%s%s" % (name, ("  -  " + genre) if genre and len(name) + len(genre) + 5 <= tw2 else ""), None))
        if cols < mc or rows < mr:
            warn = "needs a %dx%d window (now %dx%d)" % (mc, mr, cols, rows)
            if len(warn) > tw2:
                warn = "needs %dx%d (now %dx%d)" % (mc, mr, cols, rows)
            lines.append((warn[:tw2], (255, 130, 110)))
        info = textwrap.wrap(" ".join(g["info"]), tw2)
        keys = textwrap.wrap(g["keys"] if tw2 >= 44 else g["keys"].replace("   ", "  "), tw2 - 6)
        rec = record_line(g)
        room = bottom - r
        extra = len(keys) + 1 + (2 if rec else 0)
        if len(lines) + len(info) + extra > room:            # small window: shorter description first
            info = info[:max(1, room - len(lines) - extra)]
        lines += [(l, (222, 222, 234)) for l in info]
        lines.append(("", None))
        for j, l in enumerate(keys):
            lines.append((("keys  " if j == 0 else "      ") + l, "keys"))
        if rec:
            lines += [("", None), (rec[:tw2], (236, 212, 70))]
        shown = lines[:max(0, room + 1)]
        while shown and not shown[-1][0]:
            shown.pop()
        for j in range(len(shown) + 2):
            cv.put(rx - 1, r - 1 + j, " " * (tw2 + 2), PANEL_FG, PANEL)
        for j, (l, fg) in enumerate(shown):
            if j == 0:
                cv.put(rx, r, name, acc, PANEL)
                if len(l) > len(name):
                    cv.put(rx + len(name), r, l[len(name):], DIM, PANEL)
            elif fg == "keys":
                cv.put(rx, r + j, l[:6], DIM, PANEL)
                cv.put(rx + 6, r + j, l[6:], (206, 208, 230), PANEL)
            elif fg:
                cv.put(rx, r + j, l, fg, PANEL)
    if note:
        cv.center(rows - 3, " %s " % note, (14, 14, 20), (255, 150, 100))
    snd = SND.label().lower()
    if cols >= 96:
        footer(cv, "Up/Down choose   1-9 0 jump   Enter play   M %s   ? help   Esc quit" % snd)
    else:
        footer(cv, "Up/Down choose  Enter play  M %s  ? help  Esc quit" % snd.split(":")[0])
    sig = "v%s" % VERSION
    if cols >= 110:
        cv.put(16, rows - 1, sig, (110, 114, 144), (12, 10, 22))
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
                    SND.play("back")
                    return None
                elif k == "m":
                    if SND.toggle():
                        SND.play("sound_on")
                if k in ("up", "w", "k"):
                    sel = (sel - 1) % len(GAMES)
                    SND.play("move")
                elif k in ("down", "s", "j", "tab"):
                    sel = (sel + 1) % len(GAMES)
                    SND.play("move")
                elif k in tuple("123456789"):
                    sel = min(len(GAMES) - 1, int(k) - 1)
                    SND.play("move")
                elif k == "0" and len(GAMES) > 9:        # 0 reaches game 10; pressed again, the ones after it
                    sel = sel + 1 if 9 <= sel < len(GAMES) - 1 else 9
                    SND.play("move")
                elif k in ("enter", " "):
                    SND.play("start")
                    return sel


USAGE = """usage: arcade [GAME | --list | --version | --help]

Without arguments the ASCII ARCADE menu opens. With a game name that game starts straight away,
for example:  arcade stackfall
"""


def run_game(g):
    return subprocess.call([sys.executable, os.path.join(HERE, g["file"])], cwd=HERE)


def cli(args):
    """Command line: returns an exit code, or None to open the menu."""
    if not args:
        return None
    a = args[0].lower()
    if a in ("-h", "--help", "help"):
        print(USAGE)
    elif a in ("-v", "-V", "--version", "version"):
        print("ASCII ARCADE %s  %s" % (VERSION, COPYRIGHT))
    elif a in ("--list", "list"):
        for g in GAMES:
            print("%-12s %s" % (g["name"].lower(), g["tag"]))
    else:
        g = next((g for g in GAMES if g["name"].lower() == a or g["file"] == a), None)
        if g is None:
            print("unknown game %r - try: arcade --list" % args[0], file=sys.stderr)
            return 2
        return run_game(g)
    return 0


def main():
    sel, note = 0, ""
    while True:
        sel = menu(sel, note)
        if sel is None:
            return
        g = GAMES[sel]
        t = time.time()
        code = run_game(g)
        note = "" if code == 0 or time.time() - t > 3 else "%s ended unexpectedly (exit code %d)" % (g["name"], code)


if __name__ == "__main__":
    rc = cli(sys.argv[1:])
    if rc is not None:
        sys.exit(rc)
    try:
        main()
    except KeyboardInterrupt:
        pass
