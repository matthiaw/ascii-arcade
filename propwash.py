#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""PROPWASH - a vertical-scrolling shooter with propeller planes.

Fly the Kestrel, a lone propeller fighter, over six stages: a strait full of islands, a harbour town, the top of
the cloud deck, a desert, snowy mountains and a night storm at sea. Fighters dive in formations, bombers lumber
past, gunboats, tanks and flak guns fire from below. Shoot down a whole red squadron for a power-up, catch the
medals the ground targets leave (they climb in value as long as you miss none), pick up two wingmen, roll out of
trouble and keep a bomb for the worst moment. Every stage has a midboss and a boss built from parts that have to
be shot away one after the other.

Keys: arrows / WASD fly, Space / Z fire (F: auto-fire on / off), X / B bomb, C roll, Esc / P pause, ? help.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
Run:        python3 propwash.py
Self-test:  python3 propwash.py --selftest
"""
import math
import random
import sys
import time

from arcadekit import (AUTO_LABEL, PAUSE_LINES, AutoMode, Canvas, HeldKeys, KeyTerminal, clamp, cycle_view,
                       draw_title, load_scores, mix, overlay, scale_art, shade, shared_key, submit, title_screen,
                       title_width)
from arcadesound import Sound

GAME = "propwash"
DT = 1 / 60                  # fixed simulation step
FW, FH = 54, 64              # the logical play field (portrait); the window only changes how finely it is drawn
MIN_COLS, MIN_ROWS = 70, 22
PANELS = 30                  # columns kept for the two side panels together
TAU = math.pi * 2
DIFFS = ["easy", "normal", "hard"]
DIFF = {  # lives, bombs per life, enemy fire rate, bullet speed, enemy toughness
    "easy": dict(lives=5, bombs=3, fire=0.62, bspeed=0.82, hp=0.8),
    "normal": dict(lives=3, bombs=2, fire=1.0, bspeed=1.0, hp=1.0),
    "hard": dict(lives=3, bombs=2, fire=1.4, bspeed=1.16, hp=1.25),
}
P_SPEED = 40.0               # the Kestrel's top speed, field units per second
P_R = 1.1                    # its hit box: a small disc around the cockpit
FIRE_GAP = 0.085
SHOT_V = 120.0
ROLL_T, ROLL_CD = 0.6, 3.2   # a roll lasts this long, then needs this long to recharge
INVULN = 2.4                 # after a new plane arrives
LEN = 1500.0                 # stage length in ground units before the boss
MAX_POWER, MAX_BOMBS = 5, 6
MEDALS = (200, 400, 600, 800, 1000, 1500, 2000, 3000, 5000)
SHADOW = (8, 14, 28)
OUTLINE = (12, 10, 18)
WHITE = (255, 255, 255)

# =============================================================================================
# Pixel art. Lower-case letters are materials, shaded with the light from the top left (lit upper and left
# edges, a mid body, shadowed lower and right edges); upper case is the material forced into shadow; the
# others are fixed colours (glass, lights). '.' is transparent. Enemies fly downwards, their noses at the
# bottom; the Kestrel flies up. Every sprite gets a dark outline at drawing size.
# =============================================================================================
MAT = {"c": (92, 150, 214), "y": (240, 200, 64), "o": (128, 136, 74), "g": (150, 156, 170), "d": (84, 90, 108),
       "r": (212, 62, 54), "t": (58, 156, 146), "s": (196, 172, 112), "n": (150, 104, 66), "u": (64, 78, 126),
       "m": (74, 112, 66), "w": (230, 230, 236), "p": (168, 98, 200)}
FIX = {"k": (14, 12, 20), "x": (44, 44, 54), "e": (150, 214, 246), "h": (255, 255, 255), "q": (255, 70, 60),
       "f": (255, 170, 60)}
TONES = {k: (mix(c, (255, 250, 232), 0.42), c, mix(c, (20, 16, 34), 0.5)) for k, c in MAT.items()}


def tones(mat):
    if mat in TONES:
        return TONES[mat]
    c = FIX[mat]
    return mix(c, WHITE, 0.3), c, shade(c, 0.6)


class Spr:
    """A pixel-art sprite; shaded, scaled and outlined copies are cached as horizontal runs for fast drawing."""
    __slots__ = ("rows", "w", "h", "cache", "props")

    def __init__(self, rows, props=()):
        self.w = max(len(r) for r in rows)
        self.rows = [r.ljust(self.w, ".") for r in rows]
        self.h = len(rows)
        self.cache = {}
        self.props = props        # propellers: (x, y, width) in art pixels

    def colours(self, fv):
        grid = self.rows[::-1] if fv else self.rows
        w, h = self.w, self.h

        def op(x, y):
            return 1 if x < 0 or y < 0 or x >= w or y >= h or grid[y][x] == "." else 0
        cx, cy = max(1.0, (w - 1) / 2), max(1.0, (h - 1) / 2)
        out = []
        for y in range(h):
            row = []
            for x in range(w):
                ch = grid[y][x]
                if ch == ".":
                    row.append(None)
                elif ch in FIX:
                    row.append(FIX[ch])
                elif ch.isupper():
                    row.append(tones(ch.lower())[2])
                else:
                    k = op(x, y - 1) + op(x - 1, y) - op(x, y + 1) - op(x + 1, y)
                    k -= 0.4 * ((x - cx) / cx + (y - cy) / cy)
                    t = TONES[ch]
                    row.append(t[0] if k >= 1 else t[2] if k <= -1 else t[1])
            out.append(row)
        return out

    def runs(self, s, flash=False, sx=1.0, fv=False):
        key = (int(s * 16 + 0.5), flash, int(sx * 8 + 0.5), fv)
        r = self.cache.get(key)
        if r is None:
            r = self.cache[key] = self.build(key[0] / 16, flash, key[2] / 8, fv)
        return r

    def build(self, s, flash, sx, fv):
        ow, oh = max(1, int(self.w * s * sx + 0.5)), max(1, int(self.h * s + 0.5))
        src = self.colours(fv)
        if ow > self.w or oh > self.h:            # a big window: smoothed up instead of fat blocks
            src = scale_art(src, ow, oh)
        h, w = len(src), len(src[0])
        img = [[None] * (ow + 2) for _ in range(oh + 2)]
        for oy in range(oh):
            ya, yb = int(oy * h / oh), max(int(oy * h / oh) + 1, int((oy + 1) * h / oh))
            dst = img[oy + 1]
            for ox in range(ow):
                xa, xb = int(ox * w / ow), max(int(ox * w / ow) + 1, int((ox + 1) * w / ow))
                c = src[min(h - 1, (ya + yb) // 2)][min(w - 1, (xa + xb) // 2)]
                if c is None:          # shrunk: any body pixel in the block keeps the shape (thin wings, tails)
                    c = next((src[y][x] for y in range(ya, min(h, yb)) for x in range(xa, min(w, xb))
                              if src[y][x] is not None), None)
                if c is not None:
                    dst[ox + 1] = mix(c, WHITE, 0.6) if flash else c
        W, H = ow + 2, oh + 2
        for y in range(H):        # the outline: transparent pixels next to the body
            for x in range(W):
                if img[y][x] is None and (
                        (x > 0 and img[y][x - 1] not in (None, OUTLINE)) or
                        (x < W - 1 and img[y][x + 1] not in (None, OUTLINE)) or
                        (y > 0 and img[y - 1][x] not in (None, OUTLINE)) or
                        (y < H - 1 and img[y + 1][x] not in (None, OUTLINE))):
                    img[y][x] = OUTLINE
        out = []
        for oy in range(H):
            run_c, run_x = None, 0
            src_row = img[oy]
            for ox in range(W + 1):
                c = src_row[ox] if ox < W else None
                if c != run_c:
                    if run_c is not None:
                        out.append((oy, run_x, ox - run_x, [run_c] * (ox - run_x)))
                    run_c, run_x = c, ox
        return W, H, out


SPR = {
    "player": Spr([".......y.......",
                   "......yyy......",
                   "......ccc......",
                   "......cec......",
                   "......cEc......",
                   "..ccccccccccc..",
                   "ycccccccccccccy",
                   ".ccccccccccccc.",
                   "......ccc......",
                   "......ccc......",
                   "......ccc......",
                   "....ccccccc....",
                   ".......c......."], props=((7, -0.4, 7),)),
    "wing": Spr(["....y....",
                 "....c....",
                 "...cec...",
                 "ccccccccc",
                 ".ccccccc.",
                 "....c....",
                 "...ccc..."], props=((4, -0.4, 5),)),
    "dart": Spr(["...ooooo...",
                 ".....o.....",
                 ".....o.....",
                 "ooooooooooo",
                 "rooooooooor",
                 "....ooo....",
                 "....oeo....",
                 "....ooo....",
                 ".....r....."], props=((5, 9.4, 5),)),
    "gnat": Spr(["..ggg..",
                 "...g...",
                 "ggggggg",
                 ".ggggg.",
                 "..geg..",
                 "...r..."], props=((3, 6.4, 4),)),
    "swallow": Spr(["...ttt...",
                    "....t....",
                    "ttttttttt",
                    ".ttttttt.",
                    "...tet...",
                    "...ttt...",
                    "....t...."], props=((4, 7.4, 5),)),
    "red": Spr(["...rrr...",
                "....r....",
                "rrrrrrrrr",
                ".rrrrrrr.",
                "...rer...",
                "...rrr...",
                "....r...."], props=((4, 7.4, 5),)),
    "hornet": Spr(["....ddd....",
                   ".....d.....",
                   "..d..d..d..",
                   "ddddddddddd",
                   "rdddddddddr",
                   ".ddddddddd.",
                   "....ddd....",
                   "....ded....",
                   "....rrr....",
                   ".....r....."], props=((5, 10.4, 6),)),
    "bomber": Spr([".......ggggggg.......",
                   ".........ggg.........",
                   ".........ggg.........",
                   ".........ggg.........",
                   "....d....ggg....d....",
                   "...ddd...ggg...ddd...",
                   "ggggggggggggggggggggg",
                   "ggggggggggggggggggggg",
                   ".gggdddgggggggdddggg.",
                   "...ddd..ggggg..ddd...",
                   "...ddd..ggggg..ddd...",
                   "....r...geeeg...r....",
                   ".........geg.........",
                   "..........e.........."], props=((4, 12.4, 5), (16, 12.4, 5))),
    "boat": Spr(["....g....",
                 "...ggg...",
                 "..ggggg..",
                 ".ggnnngg.",
                 ".ggnnngg.",
                 "ggnnnnngg",
                 "ggnnnnngg",
                 "ggnnnnngg",
                 "ggdddddgg",
                 "ggdeeedgg",
                 "ggdddddgg",
                 "ggnnnnngg",
                 "ggnxxxngg",
                 "ggnxxxngg",
                 "ggnnnnngg",
                 "ggnnnnngg",
                 ".ggnnngg.",
                 ".ggggggg.",
                 "..ggggg.."]),
    "tank": Spr(["xx.....xx",
                 "xxsssssxx",
                 "xxsssssxx",
                 "xxsSSSsxx",
                 "xxsssssxx",
                 "xxsssssxx",
                 "xxsssssxx",
                 "xxsssssxx",
                 "xxsSSSsxx",
                 "xxsssssxx",
                 "xx.....xx"]),
}

# =============================================================================================
# Sound
# =============================================================================================
SND = Sound(GAME, {
    "shot": [dict(w="square", f=1500, f2=1000, d=0.022, v=0.07, duty=0.25)],
    "hit": [dict(w="noise", f=5000, f2=2500, d=0.02, v=0.1)],
    "clink": [dict(w="tri", f=1800, f2=1500, d=0.03, v=0.12)],
    "pop": [dict(w="noise", f=2200, f2=400, d=0.16, v=0.34), dict(w="square", f=220, f2=90, d=0.1, v=0.16, at=0)],
    "boom": [dict(w="noise", f=1400, f2=120, d=0.5, v=0.55, r="lin"),
             dict(w="square", f=110, f2=40, d=0.4, v=0.3, at=0, duty=0.3)],
    "bomb": [dict(w="noise", f=900, f2=60, d=1.1, v=0.6, r="lin"), dict(w="saw", f=80, f2=30, d=0.9, v=0.3, at=0)],
    "roll": [dict(w="noise", f=1200, f2=4000, d=0.18, v=0.18, r="lin")],
    "power": [dict(w="square", f=f, d=0.05, v=0.26, duty=0.25) for f in (523, 659, 784, 1047)],
    "medal": [dict(w="square", f=1319, d=0.04, v=0.22, duty=0.25), dict(w="square", f=1976, d=0.1, v=0.22,
                                                                          duty=0.25)],
    "life": [dict(w="tri", f=f, d=0.08, v=0.35) for f in (784, 988, 1175, 1568)],
    "die": [dict(w="noise", f=1800, f2=80, d=0.9, v=0.6, r="lin"), dict(w="square", f=440, f2=55, d=0.8, v=0.3,
                                                                         at=0)],
    "warning": [dict(w="square", f=f, d=0.22, v=0.3, duty=0.5) for f in (660, 440, 660, 440)],
    "phase": [dict(w="saw", f=300, f2=900, d=0.3, v=0.3)],
    "clear": [dict(w="square", f=f, d=0.1, v=0.28, duty=0.25) for f in (523, 659, 784, 659, 784, 1047)] +
             [dict(w="tri", f=1047, d=0.5, v=0.4, vib=(6, 0.25), r="lin")],
    "over": [dict(w="tri", f=392, d=0.2, v=0.35), dict(w="tri", f=330, d=0.2, v=0.35),
             dict(w="tri", f=262, d=0.5, v=0.35, r="lin")],
    "menu": [dict(w="tri", f=660, d=0.025, v=0.2)],
    "start": [dict(w="square", f=523, d=0.05, v=0.3, duty=0.25), dict(w="square", f=784, d=0.12, v=0.3, duty=0.25)],
    "pause": [dict(w="tri", f=523, f2=392, d=0.07, v=0.22)],
    "sound_on": [dict(w="tri", f=440, d=0.06, v=0.35), dict(w="tri", f=880, d=0.12, v=0.35)],
})


def help_lines(kitty=True):
    return [
        "PROPWASH - keys",
        "",
        "Arrows / WASD        fly",
        "Space / Z            fire (hold it)",
        "F                    auto-fire on / off (on at the start)",
        "X / B                bomb: wipes out the bullets, hits everything",
        "C                    roll: a moment untouchable, then it recharges",
        "Esc / P              pause     V view     ? help",
        "",
        "P raises the guns (five levels), B adds a bomb, W brings",
        "two wingmen (each takes one bullet for you), 1 a life.",
        "Ground targets leave medals: their value climbs while",
        "you catch every one. Down a whole red squadron for a P.",
        "Only the small glass cockpit can be hit.",
        "",
        "Keys: held keys are exact (kitty protocol)." if kitty else
        "Keys: classic terminal - held keys follow the key repeat.",
    ]


# =============================================================================================
# The ground: smooth noise, one landscape per stage
# =============================================================================================
class Noise:
    def __init__(self, seed, n=128):
        rnd = random.Random(seed)
        self.n = n
        self.v = [rnd.random() for _ in range(n * n)]

    def at(self, x, y):
        xi, yi = math.floor(x), math.floor(y)
        fx, fy = x - xi, y - yi
        fx = fx * fx * (3 - 2 * fx)
        fy = fy * fy * (3 - 2 * fy)
        n, v = self.n, self.v
        x0, y0 = xi % n, yi % n
        x1, y1 = (x0 + 1) % n, (y0 + 1) % n
        a, b, c, d = v[y0 * n + x0], v[y0 * n + x1], v[y1 * n + x0], v[y1 * n + x1]
        return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy

    def fbm(self, x, y, octaves=3):
        t, amp, norm = 0.0, 1.0, 0.0
        for _ in range(octaves):
            t += self.at(x, y) * amp
            norm += amp
            amp *= 0.5
            x, y = x * 2.03 + 17.1, y * 2.03 + 9.7
        return t / norm


def hash01(a, b):
    h = (a * 374761393 + b * 668265263) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return (h & 0xFFFF) / 65535.0


DEEP, MIDW, SHALLOW = (18, 52, 104), (30, 86, 150), (64, 168, 186)
SAND = (226, 206, 150)
ROOFS = [(176, 82, 60), (150, 70, 56), (120, 120, 130), (92, 104, 128), (190, 120, 76), (140, 96, 80)]
CROPS = [(150, 170, 70), (196, 176, 90), (110, 150, 64), (170, 140, 80), (90, 130, 70), (210, 196, 120)]


def lit(c, k, hi=(255, 250, 230), lo=(14, 20, 34), a=0.45, b=0.5):
    return mix(c, hi, k * a) if k > 0 else mix(c, lo, -k * b)


def water(N, gx, gy, h, night=False):
    deep, midw, shallow = ((8, 16, 34), (16, 34, 62), (34, 70, 96)) if night else (DEEP, MIDW, SHALLOW)
    c = mix(deep, midw, clamp((h - 0.28) / 0.3, 0, 1))
    if h > 0.555:
        c = mix(c, shallow, clamp((h - 0.555) / 0.045, 0, 1))
    w = N.at(gx / 7.0 + 50, gy / 2.6)                    # soft swell, no speckle (the glints sparkle)
    return mix(c, (150, 170, 200) if night else (190, 220, 240), clamp((w - 0.45) * 0.3, 0, 0.12))


def t_sea(N, gx, gy):
    h = N.fbm(gx / 26.0, gy / 26.0)
    if h < 0.6:
        return water(N, gx, gy, h)
    if h < 0.618:
        return mix(SAND, (196, 176, 120), N.at(gx * 0.7, gy * 0.7) * 0.6)
    k = clamp((h - N.fbm((gx - 1.3) / 26.0, (gy + 1.3) / 26.0)) * 55, -1, 1)
    f = N.at(gx / 2.2 + 9, gy / 2.2)
    c = mix((72, 140, 62), (40, 98, 48), clamp((h - 0.62) * 6, 0, 1))
    if f > 0.62:
        c = shade(c, 0.8)
    elif f < 0.25:
        c = mix(c, (110, 172, 80), 0.35)
    return lit(c, k)


def t_storm(N, gx, gy):
    h = N.fbm(gx / 26.0, gy / 26.0)
    if h < 0.665:
        c = water(N, gx, gy, min(h, 0.55), night=True)
        if h > 0.645:
            c = mix(c, (130, 146, 170), (h - 0.645) / 0.02 * 0.6)          # surf round the rocks
        return c
    k = clamp((h - N.fbm((gx - 1.3) / 26.0, (gy + 1.3) / 26.0)) * 60, -1, 1)
    return lit(mix((46, 48, 58), (30, 30, 38), N.at(gx / 1.8, gy / 1.8)), k, (150, 160, 190))


def shore_x(N, gy):
    sx = FW * 0.40 + 13 * (N.at(0.5, gy / 80.0) - 0.5) * 2 + 5 * (N.at(7.5, gy / 21.0) - 0.5)
    return sx - clamp((gy - (LEN - 80)) / 50.0, 0, 1) * 60          # open sea for the battleship at the end


def t_coast(N, gx, gy):
    sx = shore_x(N, gy)
    if gx > sx + 0.8:
        if gy % 46 < 2.4 and gx < sx + 13:                           # a pier
            return (150, 116, 80) if int(gx * 1.5) % 2 else (128, 98, 68)
        d = clamp(1 - (gx - sx) / 7.0, 0, 1)
        return water(N, gx, gy, 0.5 + d * 0.1)
    if gx > sx - 0.8:
        return (176, 170, 158)                                       # the quay
    if gy > 900:                                                     # farmland behind the town
        bx, by = math.floor((gx + 300) / 15.0), math.floor(gy / 11.0)
        lx, ly = gx + 300 - bx * 15, gy - by * 11
        if lx < 0.9 or ly < 0.9:
            return (70, 104, 56) if hash01(bx * 3, by) > 0.5 else (120, 110, 84)
        c = CROPS[int(hash01(bx, by) * len(CROPS)) % len(CROPS)]
        return shade(c, 0.88) if int(lx * 1.6) % 2 else c
    bx, by = math.floor((gx + 300) / 9.0), math.floor(gy / 8.0)
    lx, ly = gx + 300 - bx * 9, gy - by * 8
    if lx < 1.5 or ly < 1.5:
        return (96, 96, 102) if (lx < 0.25 or ly < 0.25) else (66, 66, 74)
    hv = hash01(bx, by)
    if hv < 0.14:
        f = N.at(gx / 1.6, gy / 1.6)
        return (52, 110, 54) if f > 0.55 else (84, 146, 70)
    roof = ROOFS[int(hv * 97) % len(ROOFS)]
    if lx < 2.1 or ly < 2.1 or lx > 8.4 or ly > 7.4:
        return shade(roof, 0.62)
    return mix(roof, (255, 240, 220), 0.22) if ly > 4.75 else shade(roof, 0.8)


def t_clouds(N, gx, gy):
    c = N.fbm(gx / 15.0, gy / 15.0, 4)
    sea = mix((40, 70, 112), (52, 90, 136), N.at(gx / 8.0, gy / 8.0))
    if c < 0.46:
        return sea
    k = clamp((c - N.fbm((gx - 1) / 15.0, (gy + 1) / 15.0, 4)) * 60, -1, 1)
    w = mix((206, 214, 232), (250, 251, 255), clamp((c - 0.46) * 6, 0, 1))
    w = mix(w, WHITE, k * 0.5) if k > 0 else mix(w, (150, 160, 192), -k * 0.6)
    if c < 0.49:
        w = mix(sea, w, (c - 0.46) / 0.03)
    return w


def road_x(gy):
    return FW * 0.5 + 13 * math.sin(gy / 95.0) + 5 * math.sin(gy / 31.0 + 1)


def t_desert(N, gx, gy):
    n = N.at(gx / 18.0, gy / 18.0)
    ph = gy * 0.42 + gx * 0.16 + n * 7
    c = mix((236, 202, 134), (190, 146, 90), 0.5 - 0.5 * math.sin(ph))
    m = N.fbm(gx / 17.0 + 40, gy / 17.0)
    if m > 0.63:
        k = clamp((m - N.fbm((gx - 1.2) / 17.0 + 40, (gy + 1.2) / 17.0)) * 70, -1, 1)
        rock = mix((176, 108, 72), (140, 84, 58), 0.5 + 0.5 * math.sin(m * 90))
        return lit(rock, k)
    if m > 0.61:
        return mix(c, (120, 80, 56), 0.6)
    rd = abs(gx - road_x(gy))
    if rd < 2.2:
        if rd < 0.3 and gy % 6 < 3:
            return (220, 210, 170)
        return (122, 104, 86) if rd < 1.8 else (150, 126, 96)
    return c


def t_snow(N, gx, gy):
    h = N.fbm(gx / 24.0, gy / 24.0, 4)
    k = clamp((h - N.fbm((gx - 1.2) / 24.0, (gy + 1.2) / 24.0, 4)) * 70, -1, 1)
    if h < 0.4:
        c = (170, 200, 228) if N.at(gx / 3.0, gy / 1.2) < 0.7 else (206, 224, 240)
        return c
    if h < 0.5:
        f = N.at(gx / 1.5, gy / 1.5)
        c = (36, 72, 58) if f > 0.52 else (220, 230, 240) if f < 0.18 else (60, 98, 76)
        return lit(c, k, a=0.3)
    return lit((234, 238, 248), k, (255, 255, 255), (120, 140, 186), 0.3, 0.6)


def ground_kind(si, N, gx, gy):
    land = STAGES[si]["land"]
    if land == "sea":
        return "land" if N.fbm(gx / 26.0, gy / 26.0) >= 0.62 else "water"
    if land == "storm":
        return "rock" if N.fbm(gx / 26.0, gy / 26.0) >= 0.64 else "water"
    if land == "coast":
        sx = shore_x(N, gy)
        return "land" if gx < sx - 2.5 else "water" if gx > sx + 2.5 else "shore"
    if land == "clouds":
        return "none"
    if land == "snow":
        return "ice" if N.fbm(gx / 24.0, gy / 24.0, 4) < 0.42 else "land"
    return "land"


STAGES = [
    dict(name="Saltmere Strait", land="sea", terrain=t_sea, speed=13.0, boss="gull", ground=("boat",),
         waves=(("vee", 3), ("line", 2), ("red", 2), ("hornets", 1), ("bomber", 1))),
    dict(name="Copperhaven", land="coast", terrain=t_coast, speed=13.0, boss="bulwark",
         ground=("boat", "tank", "flak"),
         waves=(("vee", 3), ("line", 2), ("red", 2), ("hornets", 2), ("bomber", 1), ("snake", 1))),
    dict(name="Above the Cloudline", land="clouds", terrain=t_clouds, speed=15.0, boss="motherwing", ground=(),
         waves=(("vee", 3), ("line", 2), ("red", 2), ("hornets", 2), ("bomber", 2), ("snake", 2), ("sneak", 1))),
    dict(name="Dunerest", land="desert", terrain=t_desert, speed=13.0, boss="sandholm", ground=("tank", "flak"),
         waves=(("vee", 3), ("line", 2), ("red", 2), ("hornets", 2), ("bomber", 1), ("sneak", 1))),
    dict(name="Hollowpeak", land="snow", terrain=t_snow, speed=13.0, boss="thunderhead", ground=("tank", "flak"),
         waves=(("vee", 3), ("line", 2), ("red", 2), ("hornets", 2), ("bomber", 2), ("snake", 1), ("sneak", 1))),
    dict(name="Stormwall", land="storm", terrain=t_storm, speed=14.0, boss="ascendant", ground=("boat",),
         waves=(("vee", 3), ("line", 2), ("red", 2), ("hornets", 3), ("bomber", 2), ("snake", 2), ("sneak", 2))),
]
_NOISE = {}


def stage_noise(si):
    if si not in _NOISE:
        _NOISE[si] = Noise(4242 + si * 977)
    return _NOISE[si]


# =============================================================================================
# Bosses: a body of shaded shapes and parts that are shot away phase by phase
# =============================================================================================
def R(x, y, w, h, mat):
    return ("poly", [(x, y), (x + w, y), (x + w, y + h), (x, y + h)], mat)


BOSSES = {
    "heavy": dict(name="HEAVY HAULER", air=True, ty=15, sway=12, shapes=[
        ("ell", 0, -10, 6.5, 1.8, "o"), ("ell", 0, 0, 3, 11, "o"), ("ell", 0, -2, 17, 3, "o"),
        ("ell", -6, 0, 1.5, 3.2, "d"), ("ell", 6, 0, 1.5, 3.2, "d"), ("ell", -12, 0, 1.4, 3, "d"),
        ("ell", 12, 0, 1.4, 3, "d"), ("ell", 0, 8, 1.6, 2, "e"),
        ("prop", -6, 3.6, 4), ("prop", 6, 3.6, 4), ("prop", -12, 3.4, 4), ("prop", 12, 3.4, 4)],
        parts=[(-6, 0, 2.4, 110, "engine", 0, (("aimed3", 1.7),)), (6, 0, 2.4, 110, "engine", 0, (("aimed3", 1.7),)),
               (0, 6, 2.6, 380, "core", 1, (("fan", 1.5), ("ring", 2.6)))]),
    "gull": dict(name="IRON GULL", air=True, ty=17, sway=10, shapes=[
        ("ell", 0, -14, 9, 2.2, "g"), ("ell", 0, 0, 4.2, 16, "g"), ("ell", 0, -2, 24, 3.6, "g"),
        ("ell", -21, 1, 1.4, 3, "d"), ("ell", 21, 1, 1.4, 3, "d"),
        ("ell", -8, 1, 2, 4.5, "d"), ("ell", 8, 1, 2, 4.5, "d"), ("ell", -15, 1, 2, 4.2, "d"),
        ("ell", 15, 1, 2, 4.2, "d"), ("ell", 0, 11, 2.2, 3, "e"),
        ("prop", -8, 5.6, 5), ("prop", 8, 5.6, 5), ("prop", -15, 5.4, 5), ("prop", 15, 5.4, 5)],
        parts=[(-15, 1, 2.6, 200, "engine", 0, (("fan", 2.2),)), (15, 1, 2.6, 200, "engine", 0, (("fan", 2.2),)),
               (-8, 1, 2.6, 220, "engine", 0, (("aimed3", 1.6),)), (8, 1, 2.6, 220, "engine", 0, (("aimed3", 1.6),)),
               (0, 9, 3.2, 900, "core", 1, (("spiral", 0.14), ("aimed3", 1.5)))]),
    "bulwark": dict(name="BULWARK", air=False, ty=24, sway=5, shapes=[
        ("poly", [(-7, 26), (7, 26), (8.5, -12), (0, -27), (-8.5, -12)], "g"),
        ("poly", [(-5, 24), (5, 24), (6, -11), (0, -22), (-6, -11)], "n"),
        R(-3.5, -6, 7, 10, "d"), ("ell", 0, 5.5, 1.8, 1.8, "x")],
        parts=[(0, -19, 2.8, 210, "turret", 0, (("aimed3", 1.5),)), (0, -12, 2.8, 210, "turret", 0, (("burst", 2.0),)),
               (0, 11, 2.8, 210, "turret", 0, (("burst", 2.1),)), (0, 17, 2.8, 210, "turret", 0, (("aimed3", 1.6),)),
               (-6, -2, 2.0, 130, "turret", 0, (("fan", 2.6),)), (6, -2, 2.0, 130, "turret", 0, (("fan", 2.6),)),
               (0, -1, 3.4, 1000, "core", 1, (("spiral", 0.13), ("shell", 2.2)))]),
    "motherwing": dict(name="MOTHERWING", air=True, ty=16, sway=8, shapes=[
        ("ell", 0, -15, 10, 2.4, "u"), ("ell", 0, 0, 3.6, 17, "u"), ("ell", 0, -3, 27, 4.4, "u"),
        ("ell", -7, -1, 1.9, 4.2, "d"), ("ell", 7, -1, 1.9, 4.2, "d"), ("ell", -14, -1, 1.9, 4.2, "d"),
        ("ell", 14, -1, 1.9, 4.2, "d"), ("ell", -21, -1, 1.8, 4, "d"), ("ell", 21, -1, 1.8, 4, "d"),
        ("ell", 0, 13, 2, 2.6, "e"), R(-2, 2, 4, 5, "x"),
        ("prop", -7, 3.4, 5), ("prop", 7, 3.4, 5), ("prop", -14, 3.4, 5), ("prop", 14, 3.4, 5),
        ("prop", -21, 3.2, 5), ("prop", 21, 3.2, 5)],
        parts=[(-21, -1, 2.4, 140, "engine", 0, (("aimed", 1.6),)), (21, -1, 2.4, 140, "engine", 0, (("aimed", 1.6),)),
               (-14, -1, 2.4, 150, "engine", 0, (("fan", 2.4),)), (14, -1, 2.4, 150, "engine", 0, (("fan", 2.4),)),
               (-7, -1, 2.4, 160, "engine", 0, (("aimed3", 1.9),)), (7, -1, 2.4, 160, "engine", 0, (("aimed3", 1.9),)),
               (0, 4.5, 2.4, 260, "hatch", 0, (("launch", 3.6),)),
               (0, 12, 3.0, 1000, "core", 1, (("ring", 1.1), ("aimed3", 1.3)))]),
    "sandholm": dict(name="SANDHOLM", air=False, ty=22, sway=6, shapes=[
        R(-16, -18, 6, 36, "x"), R(10, -18, 6, 36, "x"), R(-11, -16, 22, 32, "s"), R(-7, -14, 14, 6, "n"),
        R(-9, 9, 18, 5, "n")],
        parts=[(-8, -11, 2.4, 150, "turret", 0, (("burst", 1.9),)), (8, -11, 2.4, 150, "turret", 0, (("burst", 1.9),)),
               (-8, 11, 2.4, 150, "turret", 0, (("aimed3", 1.8),)), (8, 11, 2.4, 150, "turret", 0, (("aimed3", 1.8),)),
               (0, 2, 4.6, 600, "turret", 1, (("shell", 1.6), ("fan", 2.0))),
               (0, -11, 3.0, 700, "core", 2, (("spiral", 0.12), ("ring", 1.8)))]),
    "thunderhead": dict(name="THUNDERHEAD", air=True, ty=19, sway=9, shapes=[
        ("poly", [(-3, -13), (-10, -20), (-8, -9)], "r"), ("poly", [(3, -13), (10, -20), (8, -9)], "r"),
        ("ell", 0, 0, 9, 17, "g"), ("ell", -8, 4, 1.8, 3, "d"), ("ell", 8, 4, 1.8, 3, "d"),
        R(-3, 4, 6, 10, "d"), ("ell", 0, 13, 1.6, 1.4, "e"), ("prop", -8, 7.4, 4), ("prop", 8, 7.4, 4)],
        parts=[(-8, 4, 2.4, 200, "engine", 0, (("aimed3", 1.6),)), (8, 4, 2.4, 200, "engine", 0, (("aimed3", 1.6),)),
               (-6, -12, 2.2, 170, "turret", 0, (("curtain", 2.4),)), (6, -12, 2.2, 170, "turret", 0, (("burst", 2.2),)),
               (0, 9, 3.2, 1100, "core", 1, (("curtain", 1.5), ("spiral", 0.15)))]),
    "ascendant": dict(name="ASCENDANT", air=True, ty=17, sway=8, shapes=[
        ("poly", [(0, -6), (30, -15), (30, -9), (0, 13), (-30, -9), (-30, -15)], "d"),
        ("poly", [(-6, -11), (6, -11), (7, 8), (0, 16), (-7, 8)], "u"),
        ("ell", -10, -2, 2.2, 4, "x"), ("ell", 10, -2, 2.2, 4, "x"), ("ell", 0, 10, 1.8, 2.4, "e")],
        parts=[(-24, -11, 2.2, 180, "turret", 0, (("aimed3", 1.6),)), (24, -11, 2.2, 180, "turret", 0, (("aimed3", 1.6),)),
               (-16, -7, 2.2, 180, "turret", 0, (("burst", 1.9),)), (16, -7, 2.2, 180, "turret", 0, (("burst", 1.9),)),
               (-10, -2, 2.6, 260, "engine", 1, (("fan", 1.7), ("ring", 2.6))),
               (10, -2, 2.6, 260, "engine", 1, (("fan", 1.7), ("ring", 2.6))),
               (0, 6, 3.4, 1050, "core", 2, (("spiral", 0.11), ("aimed3", 1.4), ("shell", 2.8)))]),
}


class Part:
    __slots__ = ("dx", "dy", "r", "hp", "maxhp", "kind", "phase", "pats", "alive", "flash", "ang", "burst", "bt",
                 "bang")

    def __init__(self, dx, dy, r, hp, kind, phase, pats, rnd):
        self.dx, self.dy, self.r, self.hp, self.maxhp = dx, dy, r, hp, hp
        self.kind, self.phase = kind, phase
        self.pats = [[name, every, rnd.uniform(0.6, 1.0) * every + 0.8] for name, every in pats]
        self.alive = True
        self.flash = 0.0
        self.ang = rnd.uniform(0, TAU)
        self.burst, self.bt, self.bang = 0, 0.0, 0.0


class Boss:
    def __init__(self, key, g, mid=False):
        spec = BOSSES[key]
        self.key, self.spec, self.name, self.mid = key, spec, spec["name"], mid
        self.air = spec["air"]
        k = 0.7 * g.d["hp"] * (1 + 0.06 * g.si) * (0.9 if mid else 1.0)
        self.parts = [Part(dx, dy, r, hp * k, kind, ph, pats, g.rnd) for dx, dy, r, hp, kind, ph, pats in spec["parts"]]
        self.phase = 0
        self.last = max(p.phase for p in self.parts)
        self.shapes = spec["shapes"]
        self.solid = [s for s in self.shapes if s[0] != "prop"]
        xs, ys = [], []
        for s in self.solid:
            if s[0] == "ell":
                xs += [s[1] - s[3], s[1] + s[3]]
                ys += [s[2] - s[4], s[2] + s[4]]
            else:
                xs += [p[0] for p in s[1]]
                ys += [p[1] for p in s[1]]
        self.bx0, self.bx1, self.by0, self.by1 = min(xs), max(xs), min(ys), max(ys)
        self.x, self.y = FW / 2, -self.by1 - 4
        self.ty = max(spec["ty"], 3 - self.by0)            # the whole body on screen
        self.sway = spec["sway"]
        self.t = 0.0
        self.entering = True
        self.dying = 0.0
        self.dead = False
        self.leaving = False
        self.maxhp = sum(p.hp for p in self.parts)

    def hp(self):
        return sum(max(0.0, p.hp) for p in self.parts if p.alive)

    def inside(self, x, y):
        """A point on the body (shots stop there)?"""
        lx, ly = x - self.x, y - self.y
        if not (self.bx0 <= lx <= self.bx1 and self.by0 <= ly <= self.by1):
            return False
        for s in self.solid:
            if s[0] == "ell":
                if ((lx - s[1]) / s[3]) ** 2 + ((ly - s[2]) / s[4]) ** 2 <= 1:
                    return True
            elif point_in_poly(lx, ly, s[1]):
                return True
        return False


def point_in_poly(x, y, pts):
    inside = False
    n = len(pts)
    for i in range(n):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % n]
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            inside = not inside
    return inside


# =============================================================================================
# Things in the air and on the ground
# =============================================================================================
class Inp:
    __slots__ = ("dx", "dy", "fire", "bomb", "roll")

    def __init__(self, dx=0.0, dy=0.0, fire=False, bomb=False, roll=False):
        self.dx, self.dy, self.fire, self.bomb, self.roll = dx, dy, fire, bomb, roll


class Shot:
    __slots__ = ("x", "y", "vx", "vy", "dmg", "kind", "dead")

    def __init__(self, x, y, vx, vy, dmg=1.0, kind="bolt"):
        self.x, self.y, self.vx, self.vy, self.dmg, self.kind = x, y, vx, vy, dmg, kind
        self.dead = False


class Bullet:
    __slots__ = ("x", "y", "vx", "vy", "r", "kind", "t", "split", "dead")

    def __init__(self, x, y, vx, vy, r=1.0, kind="o", split=0.0):
        self.x, self.y, self.vx, self.vy, self.r, self.kind, self.split = x, y, vx, vy, r, kind, split
        self.t = 0.0
        self.dead = False


ESPEC = {  # sprite, hit points, radius, score, on the ground
    "dart": ("dart", 1, 4.0, 100, False),
    "gnat": ("gnat", 1, 3.0, 80, False),
    "swallow": ("swallow", 2, 3.6, 150, False),
    "hornet": ("hornet", 6, 4.4, 300, False),
    "bomber": ("bomber", 45, 8.5, 1500, False),
    "boat": ("boat", 24, 4.2, 800, True),
    "tank": ("tank", 14, 4.0, 500, True),
    "flak": (None, 16, 4.0, 600, True),
}


class Enemy:
    __slots__ = ("kind", "x", "y", "vx", "vy", "hp", "r", "score", "ground", "spr", "t", "st", "fire_t", "flash",
                 "dead", "gy", "vgy", "aim", "group", "up", "d", "mvx", "mvy")

    def __init__(self, g, kind, x, y, **d):
        spr, hp, r, score, ground = ESPEC[kind]
        self.kind, self.x, self.y = kind, x, y
        self.vx = self.vy = 0.0
        self.mvx = self.mvy = 0.0             # the movement actually made (paths set positions directly)
        self.hp = hp * (g.d["hp"] if hp > 2 else 1)
        self.r, self.score, self.ground = r, score, ground
        self.spr = SPR[spr] if spr else None
        self.t, self.st = 0.0, 0
        self.fire_t = g.rnd.uniform(0.6, 1.6)
        self.flash = 0.0
        self.dead = False
        self.gy = g.dist + FH - y if ground else 0.0
        self.vgy = 0.0
        self.aim = math.pi / 2
        self.group = d.pop("group", None)
        self.up = d.pop("up", False)
        self.d = d


class Item:
    __slots__ = ("kind", "x", "y", "t", "dead", "vx")

    def __init__(self, kind, x, y, vx=0.0):
        self.kind, self.x, self.y, self.vx = kind, x, y, vx
        self.t = 0.0
        self.dead = False


ITEM_C = {"P": (236, 90, 60), "B": (80, 190, 90), "W": (80, 150, 240), "1": (236, 110, 200), "M": (246, 200, 70)}


class Fx:
    __slots__ = ("x", "y", "vx", "vy", "t", "life", "kind", "r", "ground")

    def __init__(self, x, y, vx, vy, life, kind, r=1.0, ground=False):
        self.x, self.y, self.vx, self.vy, self.life, self.kind, self.r, self.ground = x, y, vx, vy, life, kind, r, ground
        self.t = 0.0


# =============================================================================================
# Waves
# =============================================================================================
def build_events(si):
    """The stage's schedule by distance: air waves, ground units, the midboss halfway and the boss at the end.
    The same for every run (hand-made feel); what exactly arrives is rolled when it spawns."""
    rnd = random.Random(1000 + si)
    st = STAGES[si]
    kinds = [k for k, w in st["waves"] for _ in range(w)]
    ev = []
    d = 36.0
    mid_done = False
    while d < LEN - 70:
        if not mid_done and d > LEN * 0.5:
            ev.append((LEN * 0.5, "mid"))
            d = LEN * 0.5 + 80
            mid_done = True
            continue
        ev.append((d, rnd.choice(kinds)))
        d += rnd.uniform(34, 50) * (1 - 0.03 * si)
    if st["ground"]:
        d = 70.0
        while d < LEN - 60:
            if abs(d - LEN * 0.5) > 40:
                ev.append((d, "ground"))
            d += rnd.uniform(48, 80)
    ev.append((LEN, "boss"))
    ev.sort(key=lambda e: e[0])
    return ev


# =============================================================================================
# The game
# =============================================================================================
class Game:
    def __init__(self, stage=0, diff="normal", seed=None, demo=False, god=False):
        self.rnd = random.Random(seed)
        self.diff, self.d = diff, DIFF[diff]
        self.di = DIFFS.index(diff)
        self.demo, self.god = demo, god
        self.score = 0
        self.lives = self.d["lives"]
        self.bombs = self.d["bombs"]
        self.power = 1
        self.wing = 0
        self.medal_i = 0
        self.next_life = 100000
        self.continues = 0
        self.paused = self.help = False
        self.autofire = True
        self.t = 0.0
        self.bg, self.bgkey, self.glints = {}, None, {}
        self.load_stage(stage)

    # --- set-up ---------------------------------------------------------------------------------
    def load_stage(self, si):
        self.si, self.st = si, STAGES[si]
        self.N = stage_noise(si)
        self.terrain = self.st["terrain"]
        self.events, self.ev_i = build_events(si), 0
        self.dist = 0.0
        self.spd = self.st["speed"]
        self.enemies, self.bullets, self.shots, self.items, self.fx = [], [], [], [], []
        self.scorches, self.clouds, self.popups, self.groups = [], [], [], {}
        self.boss = self.mid = None
        self.phase, self.phase_t, self.prev_phase = "intro", 0.0, "play"
        self.px, self.py = FW / 2, FH + 8
        self.alive, self.entering, self.respawn_t = True, True, 0.0
        self.inv = INVULN
        self.roll_t, self.roll_cd, self.fire_cd, self.rocket_cd = 0.0, 0.0, 0.0, 0.0
        self.bomb_t, self.bomb_x, self.bomb_y = 0.0, 0.0, 0.0
        self.wing_pos = [[self.px - 9, self.py + 3], [self.px + 9, self.py + 3]]
        self.kills = self.spawned = 0
        self.shake = self.flash = self.white = 0.0
        self.cloud_t = self.rnd.uniform(2, 6)
        self.bonus = None
        self.bg, self.bgkey, self.glints = {}, None, {}
        self.nshots = 0

    def sfx(self, name, vol=1.0):
        if not self.demo:
            SND.play(name, vol=vol)

    def popup(self, x, y, text, col=(255, 230, 150), life=0.9):
        self.popups.append([x, y, text, col, self.t + life])

    def add_score(self, n):
        if self.demo:
            return
        self.score += int(n)
        while self.score >= self.next_life:
            self.next_life += 200000
            self.lives += 1
            self.sfx("life")
            self.popup(self.px, self.py - 8, "1UP", (255, 150, 220), 1.4)

    # --- one step -------------------------------------------------------------------------------
    def step(self, inp):
        self.t += DT
        self.phase_t += DT
        if self.phase in ("over", "won"):
            self.update_fx()
            return
        slow = self.phase in ("warning", "boss", "clear")
        self.spd += ((self.st["speed"] * (0.35 if slow else 1.0)) - self.spd) * min(1.0, 1.5 * DT)
        self.dist += self.spd * DT
        self.spawn_events()
        self.update_player(inp)
        self.update_shots()
        self.update_enemies()
        for b in (self.mid, self.boss):
            if b:
                self.update_boss(b)
        self.update_bullets()
        self.update_items()
        self.update_fx()
        self.collide()
        self.update_phase()

    def spawn_events(self):
        while self.ev_i < len(self.events) and self.events[self.ev_i][0] <= self.dist:
            _, kind = self.events[self.ev_i]
            self.ev_i += 1
            if kind == "boss":
                self.phase, self.phase_t = "warning", 0.0
                self.sfx("warning")
            elif kind == "mid":
                self.mid = Boss("heavy", self, mid=True)
            elif kind == "ground":
                self.spawn_ground()
            elif self.phase == "intro" or (self.phase == "play" and self.mid is None):
                self.spawn_wave(kind)
        self.cloud_t -= DT
        if self.cloud_t <= 0:
            self.cloud_t = self.rnd.uniform(5, 11) * (0.6 if self.st["land"] == "clouds" else 1.0)
            self.add_cloud()

    def add_cloud(self):
        r = self.rnd
        high = r.random() < 0.3
        puffs = [(r.uniform(-9, 9), r.uniform(-5, 5), r.uniform(4, 8)) for _ in range(r.randint(4, 7))]
        self.clouds.append(dict(x=r.uniform(-6, FW + 6), y=-16.0, puffs=puffs, high=high,
                                k=1.7 if high else 1.25, a=0.36 if high else 0.78, mask=None))

    # --- enemies arrive -------------------------------------------------------------------------
    def add(self, e):
        self.enemies.append(e)
        self.spawned += 1
        return e

    def spawn_wave(self, kind):
        r = self.rnd
        if kind == "sneak" and self.di == 0:
            kind = "vee"
        if kind == "vee":
            cx = r.uniform(14, FW - 14)
            side = r.choice((-1, 1))
            for dx, dy in ((0, 0), (-5, -5), (5, -5), (-10, -10), (10, -10)):
                self.add(Enemy(self, "dart", cx + dx, -6 + dy, turn=r.uniform(24, 36), side=side if dx == 0 else
                               (1 if dx > 0 else -1)))
        elif kind == "line":
            side = r.choice((-1, 1))
            y0 = r.uniform(6, 20)
            for i in range(5):
                self.add(Enemy(self, "gnat", -6 - i * 7 if side > 0 else FW + 6 + i * 7, y0, dir=side, y0=y0,
                               x0=-6 - i * 7 if side > 0 else FW + 6 + i * 7, ph=i * 0.5))
        elif kind in ("red", "snake"):
            gid = len(self.groups) + 1
            n = 5 if kind == "red" else 6
            if kind == "red":
                self.groups[gid] = dict(left=n, failed=False)
            x0 = r.uniform(16, FW - 16)
            dr = r.choice((-1, 1))
            for i in range(n):
                e = self.add(Enemy(self, "swallow", x0, -10, group=gid if kind == "red" else None, x0=x0, dir=dr,
                                   delay=i * 0.3))
                if kind == "red":
                    e.spr = SPR["red"]
                e.y = -20
        elif kind == "hornets":
            n = 2 + (1 if self.si >= 2 and r.random() < 0.5 else 0)
            for i in range(n):
                x = FW * (i + 1) / (n + 1) + r.uniform(-3, 3)
                self.add(Enemy(self, "hornet", x, -8 - i * 4, stop=r.uniform(10, 24)))
        elif kind == "bomber":
            n = 2 if self.si >= 2 and r.random() < 0.5 else 1
            for i in range(n):
                x = r.uniform(14, FW - 14) if n == 1 else (FW * 0.3 if i == 0 else FW * 0.7)
                self.add(Enemy(self, "bomber", x, -10 - i * 10))
        elif kind == "sneak":
            side = 0 if self.px > FW / 2 else 1
            for i in range(3):
                x = (6 + i * 6) if side == 0 else (FW - 6 - i * 6)
                e = self.add(Enemy(self, "dart", x, FH + 8 + i * 6, up=True))
                e.vy = -46

    def spawn_ground(self):
        r = self.rnd
        gy = self.dist + FH + 6
        kinds = list(self.st["ground"])
        r.shuffle(kinds)
        for kind in kinds:
            need = "water" if kind == "boat" else "land"
            for _ in range(10):
                if kind == "tank" and self.st["land"] == "desert":
                    gx = road_x(gy) + r.uniform(-1, 1)
                else:
                    gx = r.uniform(6, FW - 6)
                if ground_kind(self.si, self.N, gx, gy) == need and \
                        ground_kind(self.si, self.N, gx, gy + (8 if kind == "boat" else -8)) == need:
                    break
            else:
                continue
            n = 1 if kind == "flak" else r.randint(1, 3 if kind == "tank" else 2)
            for i in range(n):
                y = -6 - i * (9 if kind == "tank" else 12)
                x = gx if kind == "tank" else clamp(gx + r.uniform(-8, 8) * (i > 0), 5, FW - 5)
                if kind == "tank" and self.st["land"] == "desert":
                    x = road_x(self.dist + FH - y)
                if i and ground_kind(self.si, self.N, x, self.dist + FH - y) != need:
                    continue
                e = self.add(Enemy(self, kind, x, y))
                e.vgy = {"boat": 4.0, "tank": -3.0, "flak": 0.0}[kind]
            return

    # --- the Kestrel ----------------------------------------------------------------------------
    def update_player(self, inp):
        if self.inv > 0:
            self.inv -= DT
        if self.roll_t > 0:
            self.roll_t -= DT
        if self.roll_cd > 0:
            self.roll_cd -= DT
        if self.bomb_t > 0:
            self.bomb_t -= DT
            if self.bomb_t > 0.7 and self.bullets:          # the blast keeps eating bullets for a moment
                self.cancel_bullets(10)
        self.fire_cd -= DT
        self.rocket_cd -= DT
        if not self.alive:
            self.respawn_t -= DT
            if self.respawn_t <= 0 and self.phase not in ("over", "won"):
                self.alive, self.entering = True, True
                self.px, self.py = FW / 2, FH + 8
                self.inv = INVULN
                self.bombs = max(self.bombs, self.d["bombs"])
            return
        if self.entering:
            self.py -= 34 * DT
            if self.py <= FH - 12:
                self.entering = False
            self.follow_wing()
            return
        if self.phase == "clear" and self.phase_t > 4.6:
            self.py -= 60 * DT                          # off to the next stage
            self.follow_wing()
            return
        dx, dy = inp.dx, inp.dy
        m = math.hypot(dx, dy)
        if m > 1:
            dx, dy = dx / m, dy / m
        self.px = clamp(self.px + dx * P_SPEED * DT, 3, FW - 3)
        self.py = clamp(self.py + dy * P_SPEED * DT, 7, FH - 7)
        if inp.roll and self.roll_cd <= 0 and self.roll_t <= 0:
            self.roll_t, self.roll_cd = ROLL_T, ROLL_CD
            self.sfx("roll")
        if inp.bomb and self.bombs > 0 and self.bomb_t <= 0 and self.phase != "clear":
            self.use_bomb()
        if inp.fire and self.fire_cd <= 0 and self.roll_t <= 0:
            self.fire()
        self.follow_wing()

    def follow_wing(self):
        for i, w in enumerate(self.wing_pos):
            tx, ty = self.px + (-11 if i == 0 else 11), self.py + 4
            k = min(1.0, 9 * DT)
            w[0] += (tx - w[0]) * k
            w[1] += (ty - w[1]) * k

    def fire(self):
        self.fire_cd = FIRE_GAP
        self.nshots += 1
        x, y, lv = self.px, self.py - 6, self.power
        add = self.shots.append
        add(Shot(x - 1.5, y, 0, -SHOT_V))
        add(Shot(x + 1.5, y, 0, -SHOT_V))
        if lv >= 2:
            add(Shot(x - 4, y + 2, 0, -SHOT_V))
            add(Shot(x + 4, y + 2, 0, -SHOT_V))
        if lv >= 3:
            for k in (-1, 1):
                a = 0.13 * k
                add(Shot(x + 2 * k, y + 1, math.sin(a) * SHOT_V, -math.cos(a) * SHOT_V))
        if lv >= 4:
            for k in (-1, 1):
                a = 0.26 * k
                add(Shot(x + 3 * k, y + 2, math.sin(a) * SHOT_V, -math.cos(a) * SHOT_V))
        if lv >= 5 and self.rocket_cd <= 0:
            self.rocket_cd = 0.45
            add(Shot(x - 6, y + 4, -6, -40, 4.0, "rocket"))
            add(Shot(x + 6, y + 4, 6, -40, 4.0, "rocket"))
        if self.nshots % 2 == 0:
            for i in range(self.wing):
                wx, wy = self.wing_pos[i]
                add(Shot(wx, wy - 3, 0, -SHOT_V, 1.0, "wing"))
        if self.nshots % 3 == 0:
            self.sfx("shot")

    def use_bomb(self):
        self.bombs -= 1
        self.bomb_t = 1.4
        self.bomb_x, self.bomb_y = self.px, self.py
        self.white = 0.35
        self.shake = 1.0
        self.sfx("bomb")
        self.cancel_bullets(10)
        for e in list(self.enemies):
            if -4 < e.y < FH + 4:
                self.damage(e, 60)
        for b in (self.mid, self.boss):
            if b and not b.entering and not b.dying:
                for p in b.parts:
                    if p.alive and p.phase == b.phase:
                        self.hit_part(b, p, 90)
        for i in range(14):
            a = i / 14 * TAU
            self.explode(clamp(self.px + math.cos(a) * 18, 2, FW - 2), clamp(self.py + math.sin(a) * 18 - 10, 2, FH - 2),
                         2.5)

    def cancel_bullets(self, points=0):
        for b in self.bullets:
            self.fx.append(Fx(b.x, b.y, 0, -6, 0.4, "spark"))
            if points:
                self.add_score(points)
        self.bullets = []

    def kill_player(self):
        if self.god or self.inv > 0 or self.roll_t > 0 or self.bomb_t > 0 or not self.alive or self.entering:
            return
        self.explode(self.px, self.py, 5)
        self.sfx("die")
        self.shake = 1.2
        if self.power > 1:
            self.items.append(Item("P", self.px, self.py, self.rnd.choice((-8, 8))))
        self.power = max(1, self.power - 1)
        self.wing = 0
        self.alive = False
        self.respawn_t = 1.6
        self.lives -= 1
        self.cancel_bullets()
        if self.lives < 0:
            self.lives = 0
            self.prev_phase = self.phase
            self.phase, self.phase_t = "over", 0.0
            self.sfx("over")

    # --- shots, enemies, bullets ----------------------------------------------------------------
    def update_shots(self):
        targets = None
        for s in self.shots:
            if s.kind == "rocket":
                if targets is None:
                    targets = [e for e in self.enemies if 0 < e.y < FH] + [
                        (b, p) for b in (self.mid, self.boss) if b and not b.entering
                        for p in b.parts if p.alive and p.phase == b.phase]
                best, bd = None, 1e9
                for t in targets:
                    tx, ty = (t[0].x + t[1].dx, t[0].y + t[1].dy) if isinstance(t, tuple) else (t.x, t.y)
                    d = (tx - s.x) ** 2 + (ty - s.y) ** 2
                    if ty < s.y and d < bd:
                        best, bd = (tx, ty), d
                if best:
                    a = math.atan2(best[1] - s.y, best[0] - s.x)
                    s.vx += math.cos(a) * 260 * DT
                    s.vy += math.sin(a) * 260 * DT
                s.vy -= 60 * DT
                v = math.hypot(s.vx, s.vy)
                if v > 95:
                    s.vx, s.vy = s.vx / v * 95, s.vy / v * 95
                if self.rnd.random() < 0.5:
                    self.fx.append(Fx(s.x, s.y + 1, 0, 4, 0.35, "smoke", 0.8))
            s.x += s.vx * DT
            s.y += s.vy * DT
            if s.y < -4 or s.x < -4 or s.x > FW + 4 or s.y > FH + 4:
                s.dead = True
        self.shots = [s for s in self.shots if not s.dead]

    def can_fire(self, e):
        return (self.alive and self.phase in ("play", "warning", "boss", "intro") and 2 < e.y < FH * 0.72
                and abs(e.y - self.py) > 9)

    def bspeed(self):
        return self.d["bspeed"] * (1 + 0.04 * self.si)

    def shoot(self, x, y, ang, v, r=1.0, kind="o", split=0.0):
        if len(self.bullets) > 280:
            return
        v *= self.bspeed()
        self.bullets.append(Bullet(x, y, math.cos(ang) * v, math.sin(ang) * v, r, kind, split))

    def aim(self, x, y):
        return math.atan2(self.py - y, self.px - x)

    def update_enemies(self):
        fr = self.d["fire"] * (1 + 0.07 * self.si)
        for e in self.enemies:
            if e.dead:
                continue
            e.t += DT
            if e.flash > 0:
                e.flash -= DT
            x0, y0 = e.x, e.y
            BEHAVE[e.kind](self, e, fr)
            if e.ground:
                e.y = self.dist + FH - e.gy
            e.mvx, e.mvy = (e.x - x0) / DT, (e.y - y0) / DT
            gone = e.y > FH + 16 or e.x < -24 or e.x > FW + 24 or (e.y < -30 and (e.up or e.t > 3))
            if gone and not e.dead:
                e.dead = True
                if e.group in self.groups:
                    self.groups[e.group]["failed"] = True
        self.enemies = [e for e in self.enemies if not e.dead]

    def update_bullets(self):
        out, cur = [], self.bullets
        self.bullets = []                          # shells that split add their bullets here
        for b in cur:
            b.t += DT
            b.x += b.vx * DT
            b.y += b.vy * DT
            if b.split and b.t >= b.split:
                for i in range(8):
                    a = i * TAU / 8 + 0.2
                    self.shoot(b.x, b.y, a, 19, 1.0, "p")
                continue
            if -5 < b.x < FW + 5 and -8 < b.y < FH + 5:
                out.append(b)
        self.bullets = out + self.bullets

    def damage(self, e, n):
        if e.dead:
            return
        e.hp -= n
        e.flash = 0.06
        if e.hp <= 0:
            self.destroy(e)

    def destroy(self, e):
        e.dead = True
        self.kills += 1
        self.add_score(e.score)
        big = e.kind in ("bomber", "boat")
        self.explode(e.x, e.y, 3.5 if big else 2.2 if e.ground else 1.6, ground=e.ground)
        self.sfx("boom" if big else "pop", 0.8)
        if big:
            self.shake = max(self.shake, 0.5)
        if e.ground:
            self.scorches.append([e.x, e.gy, e.r * 0.9])
            if len(self.scorches) > 40:
                self.scorches.pop(0)
            if self.rnd.random() < 0.45:
                self.items.append(Item("M", e.x, e.y))
            elif self.rnd.random() < 0.08:
                self.items.append(Item("B", e.x, e.y))
        if e.kind == "bomber" and self.rnd.random() < 0.6:
            self.items.append(Item("P" if self.rnd.random() < 0.7 else "B", e.x, e.y))
        if e.kind == "hornet" and self.rnd.random() < 0.05 and self.wing < 2:
            self.items.append(Item("W", e.x, e.y))
        if e.group in self.groups:
            gr = self.groups[e.group]
            gr["left"] -= 1
            if gr["left"] == 0 and not gr["failed"]:
                self.items.append(Item("P", e.x, e.y))
                self.popup(e.x, e.y - 4, "SQUADRON!", (255, 140, 120), 1.2)

    def hit_part(self, b, p, n):
        p.hp -= n
        p.flash = 0.06
        if p.hp <= 0 and p.alive:
            p.alive = False
            x, y = b.x + p.dx, b.y + p.dy
            self.explode(x, y, 3.0, ground=not b.air)
            self.add_score(2000 if p.kind != "core" else 0)
            self.sfx("boom")
            self.shake = max(self.shake, 0.6)

    def update_boss(self, b):
        b.t += DT
        for p in b.parts:
            if p.flash > 0:
                p.flash -= DT
        if b.dying:
            b.dying += DT
            if self.rnd.random() < 0.35:
                self.explode(b.x + self.rnd.uniform(b.bx0, b.bx1) * 0.8, b.y + self.rnd.uniform(b.by0, b.by1) * 0.8,
                             self.rnd.uniform(1.5, 3.5), ground=not b.air)
                self.sfx("pop", 0.6)
            if not b.air:
                b.y += self.spd * DT * 0.3
            if b.dying > (1.6 if b.mid else 2.6):
                b.dead = True
                self.explode(b.x, b.y, 7, ground=not b.air)
                self.sfx("boom")
                self.shake = 1.5
                self.white = 0.25
                if b.mid:
                    self.mid = None
                    self.items += [Item("P", b.x - 4, b.y), Item("B", b.x + 4, b.y)]
                    self.items.append(Item("W" if self.wing < 2 else "M", b.x, b.y + 4))
                    if self.si in (2, 4):
                        self.items.append(Item("1", b.x, b.y - 4))
                    self.add_score(10000)
                else:
                    self.boss = None
                    self.add_score(30000 * (1 + self.si * 0.5))
                    self.cancel_bullets()
                    self.phase, self.phase_t = "clear", 0.0
                    pct = int(100 * self.kills / max(1, self.spawned))
                    self.bonus = (pct, pct * 100 * (self.si + 1), self.bombs * 3000)
                    self.add_score(self.bonus[1] + self.bonus[2])
                    self.sfx("clear")
            return
        if b.entering:
            b.y += max(4.0, (b.ty - b.y) * 1.2) * DT
            if b.y >= b.ty - 0.3:
                b.entering = False
            return
        if b.leaving:
            b.y -= 14 * DT
            if b.y < -b.by1 - 6:
                b.dead = True
                self.mid = None
            return
        if b.mid and b.t > 34:
            b.leaving = True
            return
        b.x = FW / 2 + b.sway * math.sin(b.t * 0.45)
        b.y = b.ty + 2 * math.sin(b.t * 0.7)
        live = [p for p in b.parts if p.alive and p.phase == b.phase]
        if not live:
            if b.phase >= b.last:
                b.dying = DT
                self.cancel_bullets()
                return
            b.phase += 1
            self.sfx("phase")
            self.shake = max(self.shake, 0.6)
            return
        if not self.can_fire_boss():
            return
        rate = self.d["fire"] * (1 + 0.06 * self.si)
        for p in live:
            if p.burst > 0:
                p.bt -= DT
                if p.bt <= 0:
                    p.burst -= 1
                    p.bt = 0.1
                    self.shoot(b.x + p.dx, b.y + p.dy, p.bang, 33)
            for pat in p.pats:
                pat[2] -= DT * rate
                if pat[2] <= 0:
                    pat[2] = pat[1]
                    PATTERNS[pat[0]](self, b, p)
            if p.hp < p.maxhp * 0.4 and self.rnd.random() < 0.08:
                self.fx.append(Fx(b.x + p.dx, b.y + p.dy, self.rnd.uniform(-2, 2), -6, 0.9, "smoke", 1.4))

    def can_fire_boss(self):
        return self.alive and not self.entering and self.phase in ("play", "warning", "boss")

    def update_items(self):
        for it in self.items:
            it.t += DT
            it.y += (10 if it.kind == "M" else 8) * DT + (self.spd * DT * 0.3)
            it.x = clamp(it.x + (it.vx + 7 * math.sin(it.t * 2.2)) * DT, 3, FW - 3)
            it.vx *= 0.98
            if it.y > FH + 4:
                it.dead = True
                if it.kind == "M" and self.medal_i:
                    self.medal_i = 0
                    self.popup(it.x, FH - 4, "medal lost", (200, 180, 140))
        self.items = [it for it in self.items if not it.dead]

    def collect(self, it):
        it.dead = True
        k = it.kind
        if k == "P":
            if self.power < MAX_POWER:
                self.power += 1
                self.popup(it.x, it.y - 3, "POWER %d" % self.power, (255, 170, 120))
            else:
                self.add_score(3000)
                self.popup(it.x, it.y - 3, "3000")
            self.sfx("power")
        elif k == "B":
            self.bombs = min(MAX_BOMBS, self.bombs + 1)
            self.popup(it.x, it.y - 3, "BOMB", (150, 236, 150))
            self.sfx("power")
        elif k == "W":
            if self.wing < 2:
                self.wing = 2
                self.wing_pos = [[self.px - 9, self.py + 8], [self.px + 9, self.py + 8]]
                self.popup(it.x, it.y - 3, "WINGMEN", (150, 190, 255))
            else:
                self.add_score(2000)
            self.sfx("power")
        elif k == "1":
            self.lives += 1
            self.popup(it.x, it.y - 3, "1UP", (255, 150, 220))
            self.sfx("life")
        else:
            v = MEDALS[self.medal_i]
            self.add_score(v)
            self.popup(it.x, it.y - 3, str(v), (255, 220, 120))
            self.medal_i = min(len(MEDALS) - 1, self.medal_i + 1)
            self.sfx("medal")

    def explode(self, x, y, size, ground=False):
        r = self.rnd
        add = self.fx.append
        add(Fx(x, y, 0, 0, 0.12 + size * 0.03, "flash", size * 1.6, ground))
        for _ in range(int(3 + size * 2)):
            a, d = r.uniform(0, TAU), r.uniform(0, size * 0.9)
            add(Fx(x + math.cos(a) * d, y + math.sin(a) * d, math.cos(a) * size * 2, math.sin(a) * size * 2,
                   r.uniform(0.35, 0.6) + size * 0.05, "fire", r.uniform(0.6, 1.0) * (0.8 + size * 0.45), ground))
        for _ in range(int(2 + size * 1.5)):
            a = r.uniform(0, TAU)
            v = r.uniform(8, 22) * (0.6 + size * 0.2)
            add(Fx(x, y, math.cos(a) * v, math.sin(a) * v, r.uniform(0.3, 0.7), "spark", 1.0, ground))
        for _ in range(int(1 + size)):
            add(Fx(x + r.uniform(-size, size), y + r.uniform(-size, size), r.uniform(-2, 2), -3, r.uniform(0.8, 1.4),
                   "smoke", 1.0 + size * 0.5, ground))

    def update_fx(self):
        out = []
        scroll = self.spd * DT
        for f in self.fx:
            f.t += DT
            if f.t >= f.life:
                continue
            f.x += f.vx * DT
            f.y += f.vy * DT + (scroll if f.ground else 0)
            if f.kind == "spark":
                f.vx *= 0.94
                f.vy *= 0.94
            elif f.kind == "fire":
                f.vx *= 0.9
                f.vy *= 0.9
            out.append(f)
        self.fx = out[-420:]
        for c in self.clouds:
            c["y"] += self.spd * c["k"] * DT
        self.clouds = [c for c in self.clouds if c["y"] < FH + 20]
        self.popups = [p for p in self.popups if p[4] > self.t]
        self.shake = max(0.0, self.shake - DT * 2.2)
        self.white = max(0.0, self.white - DT)
        if self.st["land"] == "storm":
            self.flash = max(0.0, self.flash - DT * 2.5)
            if self.rnd.random() < DT / 5:
                self.flash = 1.0

    # --- collisions -----------------------------------------------------------------------------
    def collide(self):
        bosses = [b for b in (self.mid, self.boss) if b and not b.dying and not b.dead]
        for s in self.shots:
            for b in bosses:
                if b.entering or b.leaving:
                    continue
                for p in b.parts:              # only the open parts take hits; shots fly over the rest
                    if p.alive and p.phase == b.phase and \
                            (s.x - b.x - p.dx) ** 2 + (s.y - b.y - p.dy) ** 2 < (p.r + 0.8) ** 2:
                        self.hit_part(b, p, s.dmg)
                        s.dead = True
                        self.add_score(10)
                        if self.rnd.random() < 0.3:
                            self.fx.append(Fx(s.x, s.y, self.rnd.uniform(-10, 10), 8, 0.2, "spark", 1, not b.air))
                        break
                if s.dead:
                    break
            if s.dead:
                continue
            for e in self.enemies:
                if not e.dead and (s.x - e.x) ** 2 + (s.y - e.y) ** 2 < (e.r * 0.8 + 0.7) ** 2 and e.y > -2:
                    self.damage(e, s.dmg)
                    s.dead = True
                    self.add_score(5)
                    break
        self.shots = [s for s in self.shots if not s.dead]
        if self.wing and self.alive:
            for b in self.bullets:
                for i in range(self.wing):
                    wx, wy = self.wing_pos[i]
                    if (b.x - wx) ** 2 + (b.y - wy) ** 2 < (b.r + 2.2) ** 2:
                        b.dead = True
                        self.explode(wx, wy, 1.6)
                        self.sfx("pop")
                        self.wing -= 1
                        if i == 0 and self.wing:
                            self.wing_pos.reverse()
                        break
                if not self.wing:
                    break
            self.bullets = [b for b in self.bullets if not b.dead]
        if not self.alive or self.entering:
            return
        px, py = self.px, self.py - 1
        for it in self.items:
            if (it.x - self.px) ** 2 + (it.y - self.py) ** 2 < 30:
                self.collect(it)
        for b in self.bullets:
            if (b.x - px) ** 2 + (b.y - py) ** 2 < (b.r + P_R) ** 2:
                self.kill_player()
                return
        for e in self.enemies:
            if not e.ground and (e.x - px) ** 2 + (e.y - py) ** 2 < (e.r * 0.6 + 1.4) ** 2:
                self.damage(e, 10)
                self.kill_player()
                return
        for b in bosses:
            if b.air and b.inside(px, py) and not b.entering:
                self.kill_player()
                return

    # --- the course of a stage ------------------------------------------------------------------
    def update_phase(self):
        if self.phase == "intro" and self.phase_t > 2.6:
            self.phase, self.phase_t = "play", 0.0
        elif self.phase == "warning" and self.phase_t > 3.0 and self.boss is None and self.mid is None:
            self.boss = Boss(self.st["boss"], self)
            self.phase, self.phase_t = "boss", 0.0
        elif self.phase == "clear" and self.phase_t > 6.0:
            if self.si + 1 >= len(STAGES):
                self.phase, self.phase_t = "won", 0.0
            else:
                keep = (self.score, self.lives, self.bombs, self.power, self.wing, self.medal_i)
                self.load_stage(self.si + 1)
                self.score, self.lives, self.bombs, self.power, self.wing, self.medal_i = keep


# --- what the enemies do ----------------------------------------------------------------------
def b_dart(g, e, fr):
    d = e.d
    if e.up:
        e.y += e.vy * DT
        e.x += math.sin(e.t * 3) * 6 * DT
        return
    if e.st == 0:
        e.vy = 34
        if e.y < 26:
            e.vx = clamp(e.vx + clamp(g.px - e.x, -1, 1) * 16 * DT, -9, 9)
        if e.y > d.get("turn", 30):
            e.st = 1
        if not d.get("shot") and e.y > 12:
            d["shot"] = True
            if g.rnd.random() < 0.45 * fr and g.can_fire(e):
                g.shoot(e.x, e.y + 3, g.aim(e.x, e.y), 30)
    else:
        e.vx += d.get("side", 1) * 70 * DT
        e.vy = max(12.0, e.vy - 40 * DT)
    e.x += e.vx * DT
    e.y += e.vy * DT


def b_gnat(g, e, fr):
    d = e.d
    if d.get("drop"):
        e.vy = 30
        e.x += clamp(g.px - e.x, -1, 1) * 8 * DT
        e.y += e.vy * DT
        return
    e.x = d["x0"] + d["dir"] * 28 * e.t
    e.y = d["y0"] + 7 * math.sin(e.t * 3.2 + d["ph"]) + 4 * e.t
    if 4 < e.x < FW - 4 and not d.get("shot") and g.rnd.random() < 0.006 * fr:
        d["shot"] = True
        if g.can_fire(e):
            g.shoot(e.x, e.y + 2, g.aim(e.x, e.y), 28)


def b_swallow(g, e, fr):
    d = e.d
    tt = e.t - d["delay"]
    if tt < 0:
        e.y = -20
        return
    e.x = d["x0"] + d["dir"] * 15 * math.sin(tt * 2.0)
    e.y = -6 + 24 * tt
    if not d.get("shot") and e.y > 14 and g.rnd.random() < 0.01 * fr:
        d["shot"] = True
        if g.can_fire(e):
            g.shoot(e.x, e.y + 2, g.aim(e.x, e.y), 28)


def b_hornet(g, e, fr):
    d = e.d
    if e.st == 0:
        e.y += max(4.0, (d["stop"] - e.y) * 2.2) * DT
        if e.y >= d["stop"] - 0.5:
            e.st, e.t = 1, 0.0
    elif e.st == 1:
        e.x += math.sin(e.t * 1.4) * 6 * DT
        e.fire_t -= DT * fr
        if e.fire_t <= 0:
            e.fire_t = 1.5
            if g.can_fire(e):
                a = g.aim(e.x, e.y)
                for k in (-1, 0, 1) if g.di else (0,):
                    g.shoot(e.x, e.y + 4, a + k * 0.2, 27)
        if e.t > 4.2:
            e.st = 2
    else:
        e.vy += 30 * DT
        e.y += e.vy * DT


def b_bomber(g, e, fr):
    e.y += 7 * DT
    e.x += math.sin(e.t * 0.6) * 3 * DT
    e.fire_t -= DT * fr
    if e.fire_t <= 0:
        e.fire_t = 2.2
        if g.can_fire(e):
            n = 3 + 2 * (g.di == 2)
            a0 = g.aim(e.x, e.y)
            for i in range(n):
                g.shoot(e.x, e.y + 6, a0 + (i - (n - 1) / 2) * 0.22, 22, 1.2, "p")


def b_ground(g, e, fr):
    if e.vgy:
        nxt = ground_kind(g.si, g.N, e.x, e.gy + (6 if e.vgy > 0 else -6))
        if nxt != ("water" if e.kind == "boat" else "land") and not (e.kind == "tank" and nxt == "shore"):
            e.vgy = 0.0
        e.gy += e.vgy * DT
        if e.kind == "tank" and g.st["land"] == "desert":
            e.x = road_x(e.gy)
    e.aim = g.aim(e.x, e.y)
    e.fire_t -= DT * fr
    if e.fire_t <= 0:
        e.fire_t = {"boat": 2.4, "tank": 2.8, "flak": 3.0}[e.kind]
        if g.can_fire(e):
            x, y = e.x + math.cos(e.aim) * 3, e.y + math.sin(e.aim) * 3 - (3.5 if e.kind == "boat" else 0)
            if e.kind == "flak":
                for k in (-1, 0, 1):
                    g.shoot(x, y, e.aim + k * 0.16, 24)
            else:
                g.shoot(x, y, e.aim, 26 if e.kind == "boat" else 22, 1.2 if e.kind == "tank" else 1.0)


BEHAVE = {"dart": b_dart, "gnat": b_gnat, "swallow": b_swallow, "hornet": b_hornet, "bomber": b_bomber,
          "boat": b_ground, "tank": b_ground, "flak": b_ground}


# --- the bosses' bullet patterns ---------------------------------------------------------------
def _pos(b, p):
    return b.x + p.dx, b.y + p.dy


def pat_aimed(g, b, p):
    x, y = _pos(b, p)
    g.shoot(x, y, g.aim(x, y), 30)


def pat_aimed3(g, b, p):
    x, y = _pos(b, p)
    a = g.aim(x, y)
    for k in ((-1, 0, 1) if g.di < 2 else (-2, -1, 0, 1, 2)):
        g.shoot(x, y, a + k * 0.2, 28)


def pat_burst(g, b, p):
    x, y = _pos(b, p)
    p.burst, p.bt, p.bang = 3 + g.di, 0.0, g.aim(x, y)


def pat_fan(g, b, p):
    x, y = _pos(b, p)
    n = 5 + 2 * g.di
    for i in range(n):
        g.shoot(x, y, math.pi / 2 + (i - (n - 1) / 2) * 0.2, 23, 1.2, "p")


def pat_ring(g, b, p):
    x, y = _pos(b, p)
    n = 10 + 4 * g.di
    p.ang += 0.13
    for i in range(n):
        g.shoot(x, y, p.ang + i * TAU / n, 19, 1.2, "p")


def pat_spiral(g, b, p):
    x, y = _pos(b, p)
    arms = 2 + g.di // 2 + (1 if b.phase else 0)
    for k in range(arms):
        g.shoot(x, y, p.ang + k * TAU / arms, 21)
    p.ang += 0.27


def pat_shell(g, b, p):
    x, y = _pos(b, p)
    g.shoot(x, y, g.aim(x, y), 15, 2.0, "shell", 1.1)


def pat_curtain(g, b, p):
    x, y = _pos(b, p)
    for i in range(-3, 4):
        g.shoot(x + i * 2.6, y, math.pi / 2 + i * 0.05, 17, 1.0, "p")


def pat_launch(g, b, p):
    x, y = _pos(b, p)
    for k in (-1, 1):
        g.add(Enemy(g, "gnat", x + k * 3, y + 2, drop=True))


PATTERNS = {"aimed": pat_aimed, "aimed3": pat_aimed3, "burst": pat_burst, "fan": pat_fan, "ring": pat_ring,
            "spiral": pat_spiral, "shell": pat_shell, "curtain": pat_curtain, "launch": pat_launch}


# =============================================================================================
# Drawing
# =============================================================================================
class View:
    """World (field units) to screen pixels, with a clip rectangle."""

    def __init__(self, cv, s, ox, oy, x0, y0, x1, y1):
        self.cv, self.s, self.ox, self.oy = cv, s, ox, oy
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1

    def spr(self, spr, x, y, flash=False, sx=1.0, fv=False, shadow=0.0):
        W, H, runs = spr.runs(self.s, flash, sx, fv)
        bx = int(self.ox + x * self.s - W / 2 + 0.5)
        by = int(self.oy + y * self.s - H / 2 + 0.5)
        px, x0, x1, y0, y1 = self.cv.px, self.x0, self.x1, self.y0, self.y1
        for ry, rx, n, seg in runs:
            yy = by + ry
            if yy < y0 or yy >= y1:
                continue
            a, b = bx + rx, bx + rx + n
            if a < x0:
                seg = seg[x0 - a:]
                a = x0
            if b > x1:
                seg = seg[:len(seg) - (b - x1)]
                b = x1
            if b <= a:
                continue
            row = px[yy]
            if shadow:
                row[a:b] = [mix(q, SHADOW, shadow) for q in row[a:b]]
            else:
                row[a:b] = seg

    def span(self, y, a, b, c, k=None):
        a, b = max(self.x0, a), min(self.x1, b)
        if b <= a or y < self.y0 or y >= self.y1:
            return
        row = self.cv.px[y]
        if k is None:
            row[a:b] = [c] * (b - a)
        else:
            row[a:b] = [mix(q, c, k) for q in row[a:b]]

    def ell(self, cx, cy, rx, ry, c, k=None):
        s = self.s
        X, Y, RX, RY = self.ox + cx * s, self.oy + cy * s, max(0.5, rx * s), max(0.5, ry * s)
        for yy in range(max(self.y0, int(Y - RY)), min(self.y1, int(Y + RY) + 1)):
            dy = (yy + 0.5 - Y) / RY
            if dy * dy >= 1:
                continue
            w = RX * math.sqrt(1 - dy * dy)
            self.span(yy, int(X - w + 0.5), int(X + w + 0.5), c, k)

    def poly(self, pts, c, k=None):
        s = self.s
        P = [(self.ox + x * s, self.oy + y * s) for x, y in pts]
        ys = [p[1] for p in P]
        n = len(P)
        for yy in range(max(self.y0, int(min(ys))), min(self.y1, int(max(ys)) + 1)):
            yc = yy + 0.5
            xs = []
            for i in range(n):
                ax, ay = P[i]
                bx, by = P[(i + 1) % n]
                if (ay <= yc < by) or (by <= yc < ay):
                    xs.append(ax + (yc - ay) * (bx - ax) / (by - ay))
            xs.sort()
            for j in range(0, len(xs) - 1, 2):
                self.span(yy, int(xs[j] + 0.5), int(xs[j + 1] + 0.5), c, k)

    def dot(self, x, y, c, k=None):
        X, Y = int(self.ox + x * self.s), int(self.oy + y * self.s)
        if self.x0 <= X < self.x1 and self.y0 <= Y < self.y1:
            row = self.cv.px[Y]
            row[X] = c if k is None else mix(row[X], c, k)

    def hline(self, x0, x1, y, c, k=None):
        Y = int(self.oy + y * self.s)
        self.span(Y, int(self.ox + x0 * self.s + 0.5), max(int(self.ox + x0 * self.s + 0.5) + 1,
                                                          int(self.ox + x1 * self.s + 0.5)), c, k)

    def bar(self, x0, y0, x1, y1, w, c, k=None):
        """A thick line from (x0, y0) to (x1, y1), w field units wide (gun barrels)."""
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy) or 1
        nx, ny = -dy / L * w / 2, dx / L * w / 2
        if w * self.s < 1.2:
            n = max(1, int(L * self.s))
            for i in range(n + 1):
                self.dot(x0 + dx * i / n, y0 + dy * i / n, c, k)
            return
        self.poly([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)], c, k)


def field_geom(cols, rows, hud):
    H = rows * 2
    if hud:
        s = max(0.3, min(H / FH, (cols - PANELS) / FW))
        fw, fh = int(FW * s + 0.5), min(H, int(FH * s + 0.5))
        x0, y0 = (cols - fw) // 2, (H - fh) // 2
        return s, x0, y0, x0, y0, x0 + fw, y0 + fh
    s = max(H / FH, cols / (FW * 2.6))
    return s, cols / 2 - FW * s / 2, H - FH * s, 0, 0, cols, H


def draw_ground(g, v):
    """The landscape, row by row from a cache: only the rows that scroll in are worked out."""
    s, ox = v.s, v.ox
    key = (round(s, 5), round(ox, 3), v.x0, v.x1, g.si)
    if g.bgkey != key:
        g.bgkey, g.bg, g.glints = key, {}, {}
    cache, glints = g.bg, g.glints
    T, N = g.terrain, g.N
    base = (g.dist + FH) * s + v.oy
    px = v.cv.px
    xs = [(x + 0.5 - ox) / s for x in range(v.x0, v.x1)]
    lo = None
    for py in range(v.y0, v.y1):
        ri = int(math.floor(base - py))
        row = cache.get(ri)
        if row is None:
            gy = (ri + 0.5) / s
            row = [T(N, gx, gy) for gx in xs]
            cache[ri] = row
            gl = [i for i, c in enumerate(row) if c[2] > c[0] * 1.6 + 30 and hash01(ri, i + v.x0) < 0.012]
            if gl:
                glints[ri] = gl
        px[py][v.x0:v.x1] = row
        if lo is None:
            lo = ri
    if len(cache) > 3 * (v.y1 - v.y0) + 40 and lo is not None:
        bottom = int(math.floor(base - v.y1)) - 4
        for k in [k for k in cache if k < bottom or k > lo + 4]:
            del cache[k]
            glints.pop(k, None)
    t = g.t
    for py in range(v.y0, v.y1):
        gl = glints.get(int(math.floor(base - py)))
        if gl:
            row = px[py]
            for i in gl:
                k = 0.5 + 0.5 * math.sin(t * 5 + i * 1.7 + py)
                if k > 0.55:
                    x = v.x0 + i
                    row[x] = mix(row[x], (235, 245, 255), (k - 0.5) * 1.4)


def draw_clouds(g, v, high):
    s = v.s
    for c in g.clouds:
        if c["high"] != high:
            continue
        m = c["mask"]
        if m is None or m[0] != s:
            rows = []
            ps = c["puffs"]
            xa = min(p[0] - p[2] for p in ps)
            xb = max(p[0] + p[2] for p in ps)
            ya = min(p[1] - p[2] for p in ps)
            yb = max(p[1] + p[2] for p in ps)
            for yy in range(int(ya * s), int(yb * s) + 1):
                wy = yy / s
                line = []
                for xx in range(int(xa * s), int(xb * s) + 1):
                    wx = xx / s
                    a = 0.0
                    for qx, qy, qr in ps:
                        d = ((wx - qx) ** 2 + (wy - qy) ** 2) / (qr * qr)
                        if d < 1:
                            a = max(a, (1 - d) ** 0.6)
                    line.append(a)
                rows.append((yy, int(xa * s), line))
            m = c["mask"] = (s, rows)
        X, Y = int(v.ox + c["x"] * s), int(v.oy + c["y"] * s)
        amax = c["a"]
        for yy, x0, line in m[1]:
            Yr = Y + yy
            if Yr < v.y0 or Yr >= v.y1:
                continue
            row = v.cv.px[Yr]
            lite = (250, 251, 255) if yy < 0 else (214, 222, 238)
            for i, a in enumerate(line):
                if a > 0.02:
                    x = X + x0 + i
                    if v.x0 <= x < v.x1:
                        row[x] = mix(row[x], lite, a * amax)


def draw_props(v, spr, x, y, t, fv=False, sx=1.0):
    for ax, ay, w in spr.props:
        if fv:
            ay = spr.h - 1 - ay
        wx = x + (ax - (spr.w - 1) / 2) * sx
        wy = y + (ay - (spr.h - 1) / 2)
        ww = w * sx * (1.0 if int(t * 30) % 2 else 0.62)
        v.hline(wx - ww / 2, wx + ww / 2, wy, (226, 228, 236), 0.6)


def draw_turret(v, x, y, r, aim, mat="d", flash=False):
    lt, md, dk = tones(mat)
    v.bar(x, y, x + math.cos(aim) * r * 1.6, y + math.sin(aim) * r * 1.6, max(0.8, r * 0.35), OUTLINE)
    v.ell(x, y, r + 0.45, r + 0.45, OUTLINE)
    v.ell(x, y, r, r, dk)
    v.ell(x - r * 0.15, y - r * 0.15, r * 0.8, r * 0.8, md)
    v.ell(x - r * 0.35, y - r * 0.35, r * 0.3, r * 0.3, lt, 0.6)
    v.bar(x, y, x + math.cos(aim) * r * 1.5, y + math.sin(aim) * r * 1.5, max(0.5, r * 0.22), lt)
    if flash:
        v.ell(x, y, r, r, WHITE, 0.6)


def shape_pass(v, shapes, bx, by, what):
    for sh in shapes:
        if sh[0] == "prop":
            continue
        mat = sh[-1]
        lt, md, dk = tones(mat)
        if sh[0] == "ell":
            _, cx, cy, rx, ry, _ = sh
            cx, cy = bx + cx, by + cy
            if what == "shadow":
                v.ell(cx + 5, cy + 8, rx, ry, SHADOW, 0.42)
            elif what == "outline":
                pad = max(0.45, 1.0 / v.s)
                v.ell(cx, cy, rx + pad, ry + pad, OUTLINE)
            else:
                v.ell(cx, cy, rx, ry, dk)
                v.ell(cx - rx * 0.1, cy - ry * 0.1, rx * 0.86, ry * 0.86, md)
                v.ell(cx - rx * 0.38, cy - ry * 0.4, rx * 0.34, ry * 0.3, lt, 0.55)
        else:
            pts = sh[1]
            mx = sum(p[0] for p in pts) / len(pts)
            my = sum(p[1] for p in pts) / len(pts)
            if what == "shadow":
                v.poly([(bx + x + 5, by + y + 8) for x, y in pts], SHADOW, 0.42)
            elif what == "outline":
                pad = max(0.45, 1.0 / v.s)
                out = []
                for x, y in pts:
                    d = math.hypot(x - mx, y - my) or 1
                    out.append((bx + x + (x - mx) / d * pad, by + y + (y - my) / d * pad))
                v.poly(out, OUTLINE)
            else:
                ext = max(max(abs(x - mx) for x, _ in pts), max(abs(y - my) for _, y in pts))
                f = max(0.5, 1 - 1.1 / max(1.0, ext))
                v.poly([(bx + x, by + y) for x, y in pts], dk)
                v.poly([(bx + mx + (x - mx) * f - 0.4, by + my + (y - my) * f - 0.4) for x, y in pts], md)
                v.poly([(bx + mx + (x - mx) * f * 0.5 - ext * 0.25, by + my + (y - my) * f * 0.5 - ext * 0.25)
                        for x, y in pts], lt, 0.3)


def draw_boss(g, v, b):
    bx, by = b.x, b.y
    if b.dying and int(b.dying * 12) % 2:
        bx += 0.4
    if not b.air:                                         # a battleship's wake, a crawler's dust
        col = (230, 240, 250) if b.key == "bulwark" else (220, 190, 130)
        for i in range(4):
            k = (g.t * 1.2 + i / 4) % 1
            v.ell(bx, by + b.by1 + 1 + k * 10, 4 + k * 7, 1.4 + k * 1.2, col, 0.4 * (1 - k))
    shape_pass(v, b.shapes, bx, by, "outline")
    shape_pass(v, b.shapes, bx, by, "body")
    for sh in b.shapes:
        if sh[0] == "prop":
            ww = sh[3] * (1.0 if int(g.t * 30) % 2 else 0.6)
            v.hline(bx + sh[1] - ww / 2, bx + sh[1] + ww / 2, by + sh[2], (226, 228, 236), 0.55)
    for p in b.parts:
        x, y = bx + p.dx, by + p.dy
        if not p.alive:
            v.ell(x, y, p.r * 0.9, p.r * 0.8, (30, 24, 22))
            v.ell(x - 0.3, y - 0.3, p.r * 0.5, p.r * 0.4, (70, 40, 30))
            continue
        open_ = p.phase == b.phase and not b.entering
        if p.kind == "turret":
            draw_turret(v, x, y, p.r * 0.85, g.aim(x, y), "d", p.flash > 0)
        elif p.kind == "core":
            if open_:
                pulse = 0.5 + 0.5 * math.sin(g.t * 8)
                v.ell(x, y, p.r, p.r, OUTLINE)
                v.ell(x, y, p.r * 0.86, p.r * 0.86, mix((200, 40, 40), (255, 140, 60), pulse))
                v.ell(x - p.r * 0.2, y - p.r * 0.2, p.r * 0.36, p.r * 0.36, (255, 236, 200))
            else:
                v.ell(x, y, p.r * 0.9, p.r * 0.9, (60, 64, 80))
                v.ell(x - p.r * 0.2, y - p.r * 0.2, p.r * 0.5, p.r * 0.5, (96, 100, 120))
        elif p.kind == "hatch":
            v.poly([(x - 2, y - 2.4), (x + 2, y - 2.4), (x + 2, y + 2.4), (x - 2, y + 2.4)],
                   (30, 28, 40) if int(g.t * 3) % 2 else (60, 30, 30))
        elif open_ and p.hp < p.maxhp * 0.5 and int(g.t * 10) % 3 == 0:
            v.ell(x, y + 1, p.r * 0.5, p.r * 0.5, (255, 140, 60), 0.6)
        if p.flash > 0 and p.kind != "turret":
            v.ell(x, y, p.r, p.r, WHITE, 0.55)


def draw_flak(g, v, e):
    lt, md, dk = tones("n")
    v.ell(e.x, e.y, 4.2, 4.2, OUTLINE)
    v.ell(e.x, e.y, 3.8, 3.8, dk)
    v.ell(e.x - 0.4, e.y - 0.4, 3.3, 3.3, md)
    v.ell(e.x, e.y, 2.4, 2.4, (54, 50, 44))
    draw_turret(v, e.x, e.y, 1.7, e.aim, "o", e.flash > 0)


def bullet_px(v, b):
    s = v.s
    r = max(0.75, b.r * s * 1.05)
    X, Y = v.ox + b.x * s, v.oy + b.y * s
    if b.kind == "shell":
        rim, mid = (120, 30, 20), (255, 120, 40)
    elif b.kind == "p":
        rim, mid = (150, 30, 90), (255, 110, 190)
    else:
        rim, mid = (150, 60, 10), (255, 160, 60)
    px = v.cv.px
    for yy in range(int(Y - r), int(Y + r) + 1):
        if yy < v.y0 or yy >= v.y1:
            continue
        dy = (yy + 0.5 - Y) / r
        if dy * dy > 1:
            continue
        w = r * math.sqrt(1 - dy * dy)
        a, bb = max(v.x0, int(X - w + 0.5)), min(v.x1, int(X + w + 0.5))
        if bb <= a:
            a, bb = max(v.x0, int(X)), min(v.x1, int(X) + 1)
        row = px[yy]
        for x in range(a, bb):
            d = ((x + 0.5 - X) / r) ** 2 + dy * dy
            row[x] = (255, 252, 230) if d < 0.22 else mid if d < 0.62 else rim


def draw_fx(g, v, ground):
    for f in g.fx:
        if f.ground != ground:
            continue
        a = f.t / f.life
        if f.kind == "fire":
            r = f.r * (0.6 + a * 0.9)
            c = ((255, 250, 210) if a < 0.15 else mix((255, 220, 90), (240, 110, 40), (a - 0.15) / 0.3) if a < 0.45
                 else mix((240, 110, 40), (110, 40, 30), (a - 0.45) / 0.55))
            v.ell(f.x, f.y, r, r, c, None if a < 0.7 else 1 - (a - 0.7) / 0.3)
        elif f.kind == "smoke":
            r = f.r * (0.8 + a * 1.4)
            v.ell(f.x, f.y, r, r, (64, 62, 66), 0.45 * (1 - a))
        elif f.kind == "spark":
            v.dot(f.x, f.y, mix((255, 250, 200), (255, 120, 40), a))
        elif f.kind == "flash":
            v.ell(f.x, f.y, f.r * (0.6 + a), f.r * (0.6 + a), (255, 250, 230), 0.8 * (1 - a))


def draw_world(g, v):
    """Everything above the ground, bottom layer first."""
    for x, gy, r in g.scorches:
        y = g.dist + FH - gy
        if -r < y < FH + r:
            v.ell(x, y, r, r * 0.8, (20, 16, 14), 0.55)
    for e in g.enemies:                                  # ground units
        if not e.ground or e.y < -12:
            continue
        if e.kind == "boat":
            for i in range(4):
                k = ((g.t * 1.2 + i / 4) % 1)
                v.ell(e.x, e.y + 9 + k * 9, 2 + k * 3, 1 + k * 0.8, (230, 240, 250), 0.45 * (1 - k))
            v.spr(e.spr, e.x, e.y, e.flash > 0)
            draw_turret(v, e.x, e.y - 3.5, 1.6, e.aim, "g", e.flash > 0)
        elif e.kind == "tank":
            v.spr(e.spr, e.x, e.y, e.flash > 0)
            draw_turret(v, e.x, e.y, 2.1, e.aim, "s", e.flash > 0)
        else:
            draw_flak(g, v, e)
    if g.boss and not g.boss.air and not g.boss.dead:
        draw_boss(g, v, g.boss)
    draw_fx(g, v, True)
    draw_clouds(g, v, False)
    # shadows of everything in the air
    sh, so = 0.42, (4.5, 7.0)                           # shadow strength and offset (the sun from the top left)
    for b in (g.mid, g.boss):
        if b and b.air and not b.dead:
            shape_pass(v, b.shapes, b.x, b.y, "shadow")
    for e in g.enemies:
        if not e.ground and -10 < e.y < FH + 10:
            v.spr(e.spr, e.x + so[0], e.y + so[1], fv=e.up, shadow=sh)
    if g.alive:
        v.spr(SPR["player"], g.px + so[0], g.py + so[1], sx=roll_sx(g), shadow=sh)
        for i in range(g.wing):
            v.spr(SPR["wing"], g.wing_pos[i][0] + so[0], g.wing_pos[i][1] + so[1], shadow=sh)
    for b in (g.mid, g.boss):
        if b and b.air and not b.dead:
            draw_boss(g, v, b)
    for e in g.enemies:
        if not e.ground and -12 < e.y < FH + 12:
            v.spr(e.spr, e.x, e.y, e.flash > 0, fv=e.up)
            draw_props(v, e.spr, e.x, e.y, g.t + e.x, fv=e.up)
    for it in g.items:
        c = ITEM_C[it.kind]
        if it.kind == "M":
            w = 1.9 * abs(math.cos(it.t * 4)) + 0.4
            v.ell(it.x, it.y, w + 0.5, 2.4, OUTLINE)
            v.ell(it.x, it.y, w, 1.9, (200, 150, 40))
            v.ell(it.x - w * 0.2, it.y - 0.4, w * 0.6, 1.2, (255, 230, 120))
        else:
            v.ell(it.x, it.y, 2.9, 2.9, OUTLINE)
            v.ell(it.x, it.y, 2.5, 2.5, shade(c, 0.6))
            v.ell(it.x - 0.3, it.y - 0.3, 2.1, 2.1, c)
            v.ell(it.x - 0.9, it.y - 0.9, 0.8, 0.8, mix(c, WHITE, 0.6))
    for s in g.shots:
        if s.kind == "rocket":
            v.bar(s.x, s.y, s.x - s.vx * 0.03, s.y - s.vy * 0.03, 0.9, (200, 204, 214))
            v.dot(s.x - s.vx * 0.035, s.y - s.vy * 0.035, (255, 170, 60))
        else:
            c = (190, 230, 255) if s.kind == "wing" else (255, 240, 150)
            v.bar(s.x, s.y, s.x, s.y + 3, 0.7, c)
            v.dot(s.x, s.y, (255, 255, 240))
    if g.alive and not (g.inv > 0 and int(g.t * 12) % 2 and not g.entering):
        sx = roll_sx(g)
        v.spr(SPR["player"], g.px, g.py, sx=sx)
        draw_props(v, SPR["player"], g.px, g.py, g.t, sx=sx)
        for i in range(g.wing):
            wx, wy = g.wing_pos[i]
            v.spr(SPR["wing"], wx, wy)
            draw_props(v, SPR["wing"], wx, wy, g.t + i)
    draw_fx(g, v, False)
    if g.bomb_t > 0:
        a = 1 - g.bomb_t / 1.4
        r = 6 + a * 60
        for i in range(48):
            ang = i / 48 * TAU
            v.ell(g.bomb_x + math.cos(ang) * r, g.bomb_y + math.sin(ang) * r, 1.6, 1.6, (255, 200, 120), 0.7 * (1 - a))
    for b in g.bullets:
        bullet_px(v, b)
    draw_clouds(g, v, True)
    if g.st["land"] == "storm":
        draw_rain(g, v)
    k = max(g.white, g.flash * 0.35)
    if k > 0.01:
        for y in range(v.y0, v.y1):
            row = v.cv.px[y]
            row[v.x0:v.x1] = [mix(c, (230, 236, 255), k) for c in row[v.x0:v.x1]]


def roll_sx(g):
    if g.roll_t <= 0:
        return 1.0
    return max(0.15, abs(math.cos((1 - g.roll_t / ROLL_T) * math.pi * 2)))


def draw_rain(g, v):
    rnd = random.Random(int(g.t * 20))
    x0, x1 = (v.x0 - v.ox) / v.s, (v.x1 - v.ox) / v.s
    for _ in range(int((x1 - x0) * 0.5) + 6):
        x, y = rnd.uniform(x0, x1 + 4), rnd.uniform(0, FH)
        v.bar(x, y, x - 1.0, y + 3.0, 0.3, (170, 186, 220), 0.3)


# --- text on top: item letters, popups, banners, the panels -----------------------------------
def draw_text(g, cv, v, hud):
    if not hud:                       # the title scene and the launcher preview: pictures only
        return
    s = v.s
    fc0, fc1 = int(v.x0), int(v.x1)
    for it in g.items:
        if it.kind != "M":
            col, row = int(v.ox + it.x * s), int((v.oy + it.y * s) / 2)
            if fc0 <= col < fc1 and 0 <= row < cv.rows:
                cv.put(col, row, it.kind, (255, 255, 255), shade(ITEM_C[it.kind], 0.75))
    for x, y, text, c, _ in g.popups:
        col = int(v.ox + x * s) - len(text) // 2
        row = int((v.oy + y * s) / 2)
        col = clamp(col, fc0, max(fc0, fc1 - len(text)))
        if 0 <= row < cv.rows:
            cv.put(col, row, text, c)
    mid = (fc0 + fc1) // 2
    w = fc1 - fc0
    r0 = cv.rows // 2 - 3

    def center(row, text, fg, bg=(16, 16, 30)):
        text = text[:w]
        cv.put(mid - len(text) // 2, row, text, fg, bg)
    if g.phase == "intro" or (g.phase == "play" and g.phase_t < 0.5 and g.dist < 60):
        k = 1 if w >= title_width("STAGE 1", 1) + 2 else 0
        if k:
            t = "STAGE %d" % (g.si + 1)
            draw_title(cv, t, mid - title_width(t, 1) // 2, r0 * 2, 1, [(255, 226, 140), (236, 150, 70)])
            center(r0 + 4, " %s " % g.st["name"], (230, 230, 240))
        else:
            center(r0 + 1, " STAGE %d " % (g.si + 1), (255, 226, 140))
            center(r0 + 2, " %s " % g.st["name"], (230, 230, 240))
    elif g.phase == "warning" and int(g.phase_t * 3) % 2 == 0:
        center(r0 + 1, " W A R N I N G ", (255, 255, 255), (170, 30, 40))
        center(r0 + 3, " %s approaching " % BOSSES[g.st["boss"]]["name"], (255, 210, 200), (60, 16, 24))
    elif g.phase == "clear" and g.bonus and g.phase_t > 1.2:
        pct, b1, b2 = g.bonus
        lines = ["STAGE %d CLEAR" % (g.si + 1), "", "downed %3d%%  %6d" % (pct, b1), "bombs  x%d   %6d" % (g.bombs, b2)]
        for i, l in enumerate(lines):
            center(r0 + i, " %s " % l.center(20), (255, 236, 170) if i == 0 else (230, 230, 240))
    for b in (g.mid, g.boss):
        if b and not b.dead and not b.entering:
            frac = b.hp() / max(1, b.maxhp)
            y = v.y0 + 1
            n = int((v.x1 - v.x0 - 4) * frac)
            cv.rect(v.x0 + 2, y, v.x1 - v.x0 - 4, 1, (60, 20, 26))
            cv.rect(v.x0 + 2, y, n, 1, (236, 70, 60) if b is g.boss else (236, 160, 60))
            cv.put(v.x0 + 2, (y + 2) // 2 + 0, b.name[:w - 4], (255, 220, 200))
            break


PANEL_BG = (12, 12, 26)
DIM = (140, 146, 178)


def draw_panels(g, cv, v, best):
    cols = cv.cols
    H = cv.H
    edge = (40, 44, 70)
    for y in range(H):
        k = y / max(1, H - 1)
        c = mix((18, 18, 36), (8, 8, 18), k)
        row = cv.px[y]
        row[0:v.x0] = [c] * v.x0
        row[v.x1:cols] = [c] * (cols - v.x1)
        if 0 < v.x0:
            row[v.x0 - 1] = edge
        if v.x1 < cols:
            row[v.x1] = edge
    for y in range(0, v.y0):
        cv.px[y][v.x0:v.x1] = [(8, 8, 18)] * (v.x1 - v.x0)
    for y in range(v.y1, H):
        cv.px[y][v.x0:v.x1] = [(8, 8, 18)] * (v.x1 - v.x0)
    L = v.x0 - 1
    Rx = v.x1 + 2
    RW = cols - Rx - 1

    def lp(row, text, fg=(232, 232, 240)):
        cv.put(1, row, text[:max(0, L - 2)], fg)

    def rp(row, text, fg=(232, 232, 240)):
        cv.put(Rx, row, text[:max(0, RW)], fg)
    lp(1, "PROPWASH", (255, 210, 130))
    lp(3, "SCORE", DIM)
    lp(4, "%08d" % g.score)
    lp(6, "BEST", DIM)
    lp(7, "%08d" % max(best or 0, g.score), (240, 210, 120))
    lp(9, "STAGE %d" % (g.si + 1), DIM)
    lp(10, g.st["name"])
    lp(12, "MEDAL", DIM)
    lp(13, "%d" % MEDALS[g.medal_i], (255, 220, 120))
    if g.continues:
        lp(15, "continues %d" % g.continues, DIM)
    rp(1, "LIVES", DIM)
    rp(2, ("▲ " * min(g.lives, 6)).strip() + (" +%d" % (g.lives - 6) if g.lives > 6 else ""), (130, 190, 250))
    rp(4, "BOMBS", DIM)
    rp(5, ("● " * g.bombs).strip() or "-", (255, 170, 90))
    rp(7, "POWER", DIM)
    rp(8, "█" * g.power + "·" * (MAX_POWER - g.power), (255, 120, 90))
    rp(10, "ROLL  C", DIM)
    if g.roll_cd <= 0:
        rp(11, "ready", (140, 230, 150))
    else:
        n = int((1 - g.roll_cd / ROLL_CD) * 5)
        rp(11, "█" * n + "·" * (5 - n), (120, 140, 170))
    rp(13, "WINGMEN", DIM)
    rp(14, ("✈ " * g.wing).strip() or "-", (150, 190, 255))
    rp(16, "AUTO-FIRE  F", DIM)
    rp(17, "on" if g.autofire else "off", (140, 230, 150) if g.autofire
       else (200, 140, 140))
    if cv.rows > 20:
        lp(cv.rows - 2, g.diff, DIM)


def render(g, cols, rows, hud=True, best=None):
    cv = Canvas(cols, rows, (8, 8, 18))
    s, ox, oy, x0, y0, x1, y1 = field_geom(cols, rows, hud)
    v = View(cv, s, ox, oy, x0, y0, x1, y1)
    draw_ground(g, v)
    if g.shake > 0.05:                                   # the sprites shake, the ground stays (it is cached)
        k = g.shake * s * 1.2
        v.ox += int(g.rnd.uniform(-k, k))
        v.oy += int(g.rnd.uniform(-k, k))
    draw_world(g, v)
    v.ox, v.oy = ox, oy
    draw_text(g, cv, v, hud)
    if hud:
        draw_panels(g, cv, v, best)
    return cv


# =============================================================================================
# The pilot (auto mode, the title screen and the launcher preview)
# =============================================================================================
PLAN = ((0.06, 1.0), (0.14, 0.9), (0.24, 0.75), (0.36, 0.55), (0.5, 0.35))
DIRS = [(0.0, 0.0)] + [(math.cos(i * TAU / 16), math.sin(i * TAU / 16)) for i in range(16)] + \
       [(0.45 * math.cos(i * TAU / 8), 0.45 * math.sin(i * TAU / 8)) for i in range(8)]


class Pilot:
    def __init__(self, seed=0, every=1):
        self.rnd = random.Random(seed)
        self.every = every
        self.n = 0
        self.last = Inp(fire=True)

    def __call__(self, g):
        self.n += 1
        if self.n % self.every and not self.last.bomb and not self.last.roll:
            return self.last
        self.last = self.decide(g)
        return self.last

    def decide(self, g):
        if not g.alive or g.entering:
            return Inp(fire=True)
        px, py = g.px, g.py - 1
        th = []
        for b in g.bullets:
            if abs(b.x - px) < 24 and -26 < b.y - py < 16:
                th.append((b.x, b.y, b.vx, b.vy, b.r + P_R + 1.3))
        for e in g.enemies:
            if not e.ground and abs(e.x - px) < 26 and -30 < e.y - py < 20:
                th.append((e.x, e.y, e.mvx, e.mvy, e.r * 0.6 + 3.0))
        boss = next((b for b in (g.boss, g.mid) if b and not b.dead and not b.entering), None)
        # where to be: under the target, low on the screen, on top of an item worth having
        tx, ty = px, FH - 13
        if boss:
            live = [p for p in boss.parts if p.alive and p.phase == boss.phase]
            if live:
                p = min(live, key=lambda p: abs(boss.x + p.dx - px))
                tx = boss.x + p.dx
            if boss.air:
                ty = min(FH - 8, max(FH - 14, boss.y + boss.by1 + 16))
        else:
            air = [e for e in g.enemies if e.y < py - 8 and e.y > -2]
            if air:
                e = min(air, key=lambda e: abs(e.x - px) + (0 if not e.ground else 6))
                tx = e.x
        items = [it for it in g.items if it.y > 10 and (it.kind != "P" or g.power < MAX_POWER)]
        if items:
            it = min(items, key=lambda it: (it.x - px) ** 2 + (it.y - py) ** 2)
            tx, ty = it.x, max(it.y, FH * 0.45)
        best, bc, bdanger = (0.0, 0.0), 1e9, 0.0
        for dx, dy in DIRS:
            danger = 0.0
            for t, w in PLAN:
                qx = clamp(px + dx * P_SPEED * t, 3, FW - 3)
                qy = clamp(py + dy * P_SPEED * t, 6, FH - 8)
                for x, y, vx, vy, r in th:
                    ex, ey = x + vx * t - qx, y + vy * t - qy
                    d2 = ex * ex + ey * ey
                    if d2 < r * r:
                        danger += w * (3 + 8 * (1 - math.sqrt(d2) / r))
                if boss and boss.air and (boss.inside(qx, qy - 2) or qy < boss.y + boss.by1 + 2):
                    danger += w * 12
            qx = clamp(px + dx * P_SPEED * 0.3, 3, FW - 3)
            qy = clamp(py + dy * P_SPEED * 0.3, 6, FH - 8)
            cost = danger + 0.05 * abs(qx - tx) + 0.035 * abs(qy - ty)
            if qx < 6 or qx > FW - 6:
                cost += 0.6
            cost += self.rnd.random() * 0.02
            if cost < bc:
                best, bc, bdanger = (dx, dy), cost, danger
        roll = bdanger > 5 and g.roll_cd <= 0
        bomb = bdanger > 9 and not roll and g.roll_t <= 0 and g.bombs > 0 and g.bomb_t <= 0
        return Inp(best[0], best[1], True, bomb, roll)


# =============================================================================================
# Title, menus, the game loop
# =============================================================================================
class TitleDemo:
    """The Kestrel on autopilot through a stage (behind the title screen and in the launcher preview)."""

    def __init__(self, stage=None):
        self.k = random.randrange(len(STAGES)) if stage is None else stage
        self.new_run()

    def new_run(self):
        si = self.k % len(STAGES)
        self.k += 1
        g = self.g = Game(si, "normal", seed=self.k, demo=True, god=True)
        rnd = random.Random(self.k)
        g.power, g.wing = rnd.randint(2, 5), rnd.choice((0, 2, 2))
        g.dist = rnd.uniform(40, LEN * 0.4)
        while g.ev_i < len(g.events) and g.events[g.ev_i][0] <= g.dist:
            g.ev_i += 1
        g.phase, g.entering, g.py, g.inv = "play", False, FH - 13, 0.0
        g.phase_t = 5.0
        self.pilot = Pilot(self.k, every=2)
        self.t = self.acc = 0.0

    def scene(self, cols, rows, dt):
        g = self.g
        self.acc += min(0.1, max(0.0, dt))
        n = 0
        while self.acc >= DT and n < 6:
            g.step(self.pilot(g))
            self.acc -= DT
            n += 1
        self.t += dt
        cv = render(g, cols, rows, hud=False)
        if self.t > 26 or g.phase not in ("play", "intro"):
            self.new_run()
        return cv


def progress():
    rec = load_scores().get(GAME, {})
    return clamp(int(rec.get("unlocked", 1)), 1, len(STAGES)), rec


def too_small(term):
    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (%dx%d)." % (MIN_COLS, MIN_ROWS))


def render_title(demo, cols, rows, dt, sel, stage, diff, help_, kitty):
    cv = demo.scene(cols, rows, dt)
    unlocked, rec = progress()
    items = ["Play", "Stage       < %d  %s >" % (stage + 1, STAGES[stage]["name"]), "Difficulty  < %s >" % DIFFS[diff],
             AUTO_LABEL]
    extra = ["", "Six stages, six bosses, a midboss in each.", "Stages unlocked: %d of %d" % (unlocked, len(STAGES)),
             "Keys: %s" % ("with releases (kitty protocol)" if kitty else "classic terminal mode")]
    b = rec.get(DIFFS[diff])
    title_screen(cv, "PROPWASH", "a propeller fighter against a whole air fleet", items, sel,
                 "best (%s): %d" % (DIFFS[diff], b) if b else None, extra=extra,
                 keys="Up/Down choose   Left/Right change   Enter start   ? help   Esc quit",
                 help_lines=help_lines(kitty), show_help=help_, dim=0.4)
    return cv


def render_over(g, cv, record, won, auto=False):
    if won:
        lines = ["THE SKY IS CLEAR", "", "All six stages flown.", "score %08d" % g.score]
    else:
        lines = ["GAME OVER", "", "score %08d" % g.score, "reached stage %d  %s" % (g.si + 1, g.st["name"])]
    if g.continues:
        lines.append("continues used: %d" % g.continues)
    if record:
        lines += ["", "** NEW RECORD **"]
    if auto:
        lines += ["", "auto mode: a new round starts in a moment"]
    else:
        lines += ["", "Esc / Q: menu" if won else "Enter: continue (score resets)   Esc / Q: menu"]
    w = max(len(l) for l in lines) + 4
    x, y = max(0, (cv.cols - w) // 2), max(1, cv.rows // 2 - len(lines) // 2 - 1)
    edge = (250, 214, 120) if record else (110, 204, 160) if won else (200, 76, 86)
    cv.frame(x - 1, y * 2 - 1, w + 2, (len(lines) + 2) * 2 + 2, edge)
    cv.box(x, y, [l.center(w - 4) for l in lines], (240, 240, 246), (24, 22, 44))


def continue_game(g):
    g.continues += 1
    g.score = 0
    g.next_life = 100000
    g.lives = g.d["lives"]
    g.bombs = g.d["bombs"]
    g.phase, g.phase_t = g.prev_phase, 0.0
    g.alive, g.respawn_t = False, 0.2


def play(term, held, stage, diff):
    g = Game(stage, DIFFS[diff])
    acc = 0.0
    last = time.time()
    record = None
    unlocked, rec = progress()
    best = rec.get(DIFFS[diff], 0)
    while True:
        now = time.time()
        frame = min(0.1, now - last)
        last = now
        for name, kind in term.events(0):
            held.feed(name, kind, now)
        held.tick(now)
        bomb = roll = False
        for k in held.take_hits():
            if g.phase in ("over", "won"):
                if k in ("q", "esc"):
                    return
                if k in ("enter", " ") and g.phase == "over" and g.phase_t > 1.2:
                    continue_game(g)
                    record = None
                continue
            a = shared_key(k, g.paused)
            if a == "pause":
                g.paused = True
                SND.play("pause")
            elif a == "resume":
                g.paused = g.help = False
            elif a == "quit":
                if record is None and g.score:
                    submit(GAME, DIFFS[diff], g.score)
                return
            elif a == "help":
                g.help = not g.help
                g.paused = True
            elif a == "sound":
                if SND.toggle():
                    SND.play("sound_on")
            elif a is None:
                if k in ("x", "b"):
                    bomb = True
                elif k == "c":
                    roll = True
                elif k == "f":
                    g.autofire = not g.autofire
                    g.popup(g.px, g.py - 9, "auto-fire %s" % ("on" if g.autofire else "off"), (200, 230, 255))
        dx = (1 if held.down("right", "d") else 0) - (1 if held.down("left", "a") else 0)
        dy = (1 if held.down("down", "s") else 0) - (1 if held.down("up", "w") else 0)
        inp = Inp(dx, dy, g.autofire or held.down(" ", "z"), bomb, roll)
        if not g.paused:
            acc += frame
            n = 0
            while acc >= DT and n < 6:
                g.step(inp)
                inp.bomb = inp.roll = False
                acc -= DT
                n += 1
            if n == 6:
                acc = 0.0
        if g.si + 1 > unlocked:
            unlocked = g.si + 1
            submit(GAME, "unlocked", unlocked)
        if g.phase in ("over", "won") and record is None:
            record = submit(GAME, DIFFS[diff], g.score)
        cols, rows = term.size()
        if cols < MIN_COLS or rows < MIN_ROWS:
            too_small(term)
            time.sleep(0.2)
            last = time.time()
            continue
        cv = render(g, cols, rows, best=best)
        if g.phase in ("over", "won") and g.phase_t > 0.8:
            render_over(g, cv, record, g.phase == "won")
        elif g.paused:
            overlay(cv, help_lines(term.kitty) if g.help else PAUSE_LINES + ["", SND.label()])
        term.write(cv.emit())
        time.sleep(max(0.0, 1 / 60 - (time.time() - now)))


def render_auto(g, auto, cols, rows):
    """The real game screen one row shorter, with the auto-mode bar on the last row."""
    cv = render(g, cols, rows - 1, best=progress()[1].get(g.diff, 0))
    cv.rows, cv.H = rows, rows * 2
    cv.px += [[(8, 8, 18)] * cv.W for _ in range(2)]
    auto.banner(cv, extra="%s  stage %d" % (g.diff, g.si + 1))
    return cv


def play_auto(term, stage, diff, hook=None, clock=time.time, sleep=time.sleep):
    """Auto mode: the real game (same stage and difficulty, no invulnerability) flown by the pilot. After a game
    over or the last stage the result shows for three seconds, then a new round starts. Never records a score."""
    auto = AutoMode()
    rounds = 0

    def new_round():
        return Game(stage, DIFFS[diff]), Pilot(seed=rounds)
    g, pilot = new_round()
    last = clock()
    shown = 0.0
    while True:
        now = clock()
        frame = min(0.1, now - last)
        last = now
        for k, kind in term.events(0):
            if kind != "press":
                continue
            a = auto.key(k)
            if a == "stop":
                return rounds
            if a == "sound" and SND.toggle():
                SND.play("sound_on")
        for _ in range(auto.steps(frame, DT)):
            g.step(pilot(g))
        if hook is not None:
            hook(g)
        if g.phase in ("over", "won") and g.phase_t > 0.8:
            if auto.scale(frame) > 0:
                shown += frame
            if shown > 3.0:
                rounds += 1
                g, pilot = new_round()
                shown = 0.0
        cols, rows = term.size()
        if cols < MIN_COLS or rows < MIN_ROWS:
            too_small(term)
            sleep(0.2)
            last = clock()
            continue
        cv = render_auto(g, auto, cols, rows)
        if g.phase in ("over", "won") and g.phase_t > 0.8:
            render_over(g, cv, False, g.phase == "won", auto=True)
        term.write(cv.emit())
        sleep(max(0.0, 1 / 60 - (clock() - now)))


def main():
    with KeyTerminal() as term:
        held = HeldKeys(term.kitty)
        demo = TitleDemo()
        sel, diff, help_ = 0, 1, False
        unlocked, _ = progress()
        stage = 0
        last = time.time()
        while True:
            now = time.time()
            cols, rows = term.size()
            if cols < MIN_COLS or rows < MIN_ROWS:
                too_small(term)
                if any(k in ("q", "esc") for k, kind in term.events(0.3) if kind == "press"):
                    return
                last = time.time()
                continue
            cv = render_title(demo, cols, rows, min(0.1, now - last), sel, stage, diff, help_, term.kitty)
            last = now
            term.write(cv.emit())
            go = False
            for k, kind in term.events(max(0.0, 1 / 30 - (time.time() - now))):
                if kind != "press":
                    continue
                if help_:
                    help_ = False
                elif k == "?":
                    help_ = True
                elif k in ("q", "esc"):
                    return
                elif k in ("up", "w"):
                    sel = (sel - 1) % 4
                    SND.play("menu")
                elif k in ("down", "s", "tab"):
                    sel = (sel + 1) % 4
                    SND.play("menu")
                elif k in ("left", "a", "right", "d"):
                    dd = -1 if k in ("left", "a") else 1
                    unlocked, _ = progress()
                    if sel == 2:
                        diff = (diff + dd) % 3
                    else:
                        stage = (stage + dd) % unlocked
                    SND.play("menu")
                elif k == "m":
                    if SND.toggle():
                        SND.play("sound_on")
                elif k == "v":
                    cycle_view()
                elif k in ("enter", " "):
                    SND.play("start")
                    go = "auto" if sel == 3 else True
            if go == "auto":
                play_auto(term, stage, diff)
                held.clear()
                last = time.time()
            elif go:
                held.clear()
                play(term, held, stage, diff)
                held.clear()
                unlocked, _ = progress()
                stage = min(stage, unlocked - 1)
                last = time.time()


# =============================================================================================
# Self-test:  python3 propwash.py --selftest
# =============================================================================================
class FakeTerm:
    def __init__(self, script, size=(100, 32)):
        self.script = sorted(script)
        self.t0 = time.time()
        self.cols_rows = size
        self.frames = 0
        self.kitty = False

    def events(self, timeout=0.0):
        now = time.time() - self.t0
        out = [(k, "press") for t, k in self.script if t <= now]
        self.script = [(t, k) for t, k in self.script if t > now]
        return out

    def keys(self, timeout=0.0):
        return [k for k, _ in self.events(timeout)]

    def size(self):
        return self.cols_rows

    def write(self, s):
        self.frames += 1


def screenshot(cols=100, rows=32):
    quiet, SND.enabled = SND.enabled, False
    try:
        g = Game(0, "normal", seed=7, demo=True, god=True)
        g.power, g.wing = 4, 2
        g.dist = 380
        while g.ev_i < len(g.events) and g.events[g.ev_i][0] <= g.dist:
            g.ev_i += 1
        g.phase, g.entering, g.py, g.inv = "play", False, FH - 14, 0.0
        g.demo = False
        pilot = Pilot(3)
        for i in range(60 * 40):
            g.step(pilot(g))
            g.lives = 3
            if i > 600 and len(g.bullets) > 8 and len([e for e in g.enemies if 0 < e.y < FH]) > 4:
                break
        cv = render(g, cols, rows, best=250000)
    finally:
        SND.enabled = quiet
    return cv


def selftest():
    import os
    import tempfile
    import arcadekit
    t0 = time.time()
    tmp = os.path.join(tempfile.mkdtemp(), "scores.json")
    arcadekit.SCORES_PATH = tmp
    SND.enabled = False
    # sprites: symmetric art, every scale builds, the outline wraps the body
    for name, sp in SPR.items():
        for r in sp.rows:
            assert len(r) == sp.w, (name, r)
            assert r == r[::-1], ("not symmetric", name, r)
        for s in (0.3, 0.7, 1.0, 1.6, 2.6):
            for fv in (False, True):
                W, H, runs = sp.runs(s, False, 1.0, fv)
                assert W >= 3 and H >= 3 and runs
                assert all(seg[0] == OUTLINE for y, x, n, seg in runs if y == 0)
    # noise stays in range, every stage's landscape gives colours
    N = stage_noise(0)
    vals = [N.fbm(x * 0.37, y * 0.91) for x in range(60) for y in range(60)]
    assert 0 <= min(vals) and max(vals) <= 1
    for si, st in enumerate(STAGES):
        Ns = stage_noise(si)
        kinds = set()
        for gx in range(-20, FW + 20, 3):
            for gy in range(0, int(LEN), 37):
                c = st["terrain"](Ns, gx, gy)
                assert len(c) == 3 and all(0 <= v <= 255 for v in c), (si, c)
                kinds.add(ground_kind(si, Ns, gx, gy))
        for k in st["ground"]:
            assert ("water" if k == "boat" else "land") in kinds, (si, k, kinds)
        ev = build_events(si)
        assert ev[-1][1] == "boss" and sum(1 for e in ev if e[1] == "mid") == 1
        assert ev == build_events(si), "the schedule is not fixed"
    # the coast opens into sea for the battleship
    assert all(ground_kind(1, stage_noise(1), x, LEN + 20) == "water" for x in range(4, FW - 4, 4))
    # shots: the guns grow with the power level, wingmen fire too
    g = Game(0, "normal", seed=1)
    g.phase, g.entering, g.py = "play", False, FH - 12
    counts = []
    for lv in range(1, 6):
        g.power, g.shots, g.fire_cd, g.rocket_cd = lv, [], 0.0, 0.0
        g.fire()
        counts.append(len(g.shots))
    assert counts == sorted(counts) and counts[0] == 2 and counts[-1] >= 10, counts
    g.wing, g.shots, g.nshots = 2, [], 1
    g.fire()
    assert sum(1 for s in g.shots if s.kind == "wing") == 2
    # a bullet on the cockpit kills, the roll and the bomb protect
    g = Game(0, "normal", seed=2)
    g.phase, g.entering, g.inv, g.py = "play", False, 0.0, FH - 12
    lives = g.lives
    g.bullets = [Bullet(g.px, g.py - 1, 0, 0)]
    g.collide()
    assert g.lives == lives - 1 and not g.alive
    g = Game(0, "normal", seed=2)
    g.phase, g.entering, g.inv, g.py = "play", False, 0.0, FH - 12
    g.step(Inp(roll=True))
    g.bullets = [Bullet(g.px, g.py - 1, 0, 0)]
    g.collide()
    assert g.alive and g.lives == g.d["lives"], "a roll should dodge"
    g.roll_t = 0.0
    g.bullets = [Bullet(g.px + 3, g.py - 1, 0, 0)]
    g.collide()
    assert g.alive, "a bullet beside the cockpit must miss"
    g.enemies = [Enemy(g, "dart", 20, 20), Enemy(g, "bomber", 30, 15)]
    g.bullets = [Bullet(10 + i, 10, 0, 5) for i in range(30)]
    b0 = g.bombs
    g.step(Inp(bomb=True))
    assert g.bombs == b0 - 1 and not g.bullets and not any(e.kind == "dart" for e in g.enemies), "bomb"
    # wingmen take a bullet each
    g = Game(0, "normal", seed=3)
    g.phase, g.entering, g.inv = "play", False, 0.0
    g.wing = 2
    wx, wy = g.wing_pos[0]
    g.bullets = [Bullet(wx, wy, 0, 0)]
    g.collide()
    assert g.wing == 1 and g.alive
    # medals climb while caught and drop back when one falls past
    g = Game(0, "normal", seed=4)
    g.phase, g.entering = "play", False
    s0 = g.score
    for i in range(3):
        g.collect(Item("M", g.px, g.py))
    assert g.score - s0 == MEDALS[0] + MEDALS[1] + MEDALS[2] and g.medal_i == 3
    g.items = [Item("M", 20, FH + 3.9)]
    for _ in range(10):
        g.update_items()
    assert g.medal_i == 0
    # a whole red squadron gives a P, a broken one does not
    for spoil in (False, True):
        g = Game(0, "normal", seed=5)
        g.phase = "play"
        g.spawn_wave("red")
        reds = [e for e in g.enemies if e.group]
        assert len(reds) == 5
        if spoil:
            g.groups[reds[0].group]["failed"] = True
        for e in reds:
            g.destroy(e)
        ps = [it for it in g.items if it.kind == "P"]
        assert (len(ps) == 0) == spoil, (spoil, len(ps))
    # every boss: phases open one after the other, the core last, and the stage clears
    for si, st in enumerate(STAGES):
        g = Game(si, "normal", seed=6)
        g.phase, g.entering, g.inv = "boss", False, 99
        g.boss = b = Boss(st["boss"], g)
        b.entering = False
        b.y = b.ty
        order = []
        for _ in range(4000):
            live = [p for p in b.parts if p.alive and p.phase == b.phase]
            locked = [p for p in b.parts if p.alive and p.phase > b.phase]
            for p in locked:                      # shots on a locked part do nothing
                hp = p.hp
                g.shots = [Shot(b.x + p.dx, b.y + p.dy, 0, 0, 5)]
                g.collide()
                assert p.hp == hp
            if live:
                order.append(live[0].phase)
                g.shots = [Shot(b.x + live[0].dx, b.y + live[0].dy, 0, 0, 25)]
                g.collide()
            g.inv = 99
            g.step(Inp())
            if g.phase == "clear":
                break
        assert g.phase == "clear", (st["boss"], g.phase)
        assert order == sorted(order) and order[-1] == b.last
        assert g.boss is None and g.bonus
    # every boss can be beaten by real shooting from below (the pilot, untouchable, guns at level 4)
    boss_t = []
    for si, st in enumerate(STAGES):
        g = Game(si, "normal", seed=30 + si, god=True)
        g.power = 4
        g.dist = LEN - 1
        g.ev_i = len(g.events) - 1
        g.phase, g.entering, g.py = "play", False, FH - 13
        pilot = Pilot(si)
        for i in range(60 * 150):
            g.step(pilot(g))
            if g.phase == "clear":
                break
        assert g.phase == "clear", (st["boss"], g.boss and [(p.kind, int(p.hp)) for p in g.boss.parts])
        boss_t.append(int(i / 60))
    # the pilot survives a while on its own, and stages run with bosses and midbosses
    survived = []
    for si in range(len(STAGES)):
        g = Game(si, "normal", seed=10 + si)
        g.dist = LEN * 0.45
        while g.ev_i < len(g.events) and g.events[g.ev_i][0] <= g.dist:
            g.ev_i += 1
        pilot = Pilot(si)
        lost = 0
        for _ in range(60 * 30):
            lv = g.lives
            g.step(pilot(g))
            if g.lives < lv:
                lost += 1
            if g.phase == "over":
                break
        survived.append(lost)
        assert g.mid is not None or g.kills > 0
    assert sum(survived) <= len(STAGES) * 3, survived
    # a full stage flown in god mode reaches the boss and beats it
    g = Game(0, "normal", seed=20, god=True)
    g.power, g.wing = 5, 2
    pilot = Pilot(1)
    saw = set()
    for _ in range(60 * 260):
        g.step(pilot(g))
        saw.add(g.phase)
        if g.si == 1:
            break
    assert {"intro", "play", "warning", "boss", "clear"} <= saw and g.si == 1, saw
    # drawing at many sizes, title, auto mode and the play loop
    for cols, rows in ((70, 22), (100, 32), (180, 50), (250, 70)):
        g = Game(2, "hard", seed=3)
        for _ in range(200):
            g.step(Pilot(0)(g))
        g.boss = Boss("motherwing", g)
        g.items = [Item(k, 10 + i * 6, 30) for i, k in enumerate("PBW1M")]
        g.popup(20, 20, "1000")
        render(g, cols, rows).emit()
        g.paused = True
        render(g, cols, rows).emit()
        d = TitleDemo()
        for i in range(10):
            d.scene(cols, rows, 0.1)
        for sel in range(4):
            render_title(d, cols, rows, 0.05, sel, 0, 1, sel == 2, sel % 2 == 0).emit()
    for w, h in ((24, 8), (40, 12), (12, 5)):
        TitleDemo(1).scene(w, h, 0.1)
    term = FakeTerm([(0.1, "+"), (0.2, "+"), (0.4, " "), (0.5, "?"), (0.6, "x"), (0.7, " "), (1.0, "esc")])
    play_auto(term, 0, 1)
    assert term.frames > 5 and not term.script
    term = FakeTerm([(0.1, "d"), (0.2, "right"), (0.3, "c"), (0.4, "x"), (0.5, "f"), (0.6, "esc"), (0.8, "q")])
    play(term, HeldKeys(False), 0, 1)
    assert term.frames > 5
    rec = load_scores().get(GAME, {})
    assert set(rec) <= {"unlocked", "normal"}, rec
    print("Self-test ok: %d sprites at five scales, six landscapes, fixed schedules, guns %s, hit box, roll, bomb, "
          "wingmen, medals, red squadron, six bosses phase by phase, beaten in %s s, pilot losses %s, a full stage to its boss, "
          "drawing at four sizes, title, auto mode, play loop (%.1fs)"
          % (len(SPR), counts, boss_t, survived, time.time() - t0))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
