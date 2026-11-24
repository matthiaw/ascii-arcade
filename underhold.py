#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""UNDERHOLD - one hero, ten floors down, no second chances.

A turn-based dungeon crawl for a quick run. Every floor is new: halls and corridors with doors, or winding caves
with pools of water and, further down, lava. You see what your torch shows, and the map remembers the rest.
Seventeen kinds of things live down there - gnawers that come in fast, slingers that keep their distance,
jellies that split, lurkers you only see when they are next to you, chanters that call for help - and on the
tenth floor the Mawkeeper waits.

Three heroes: the Warden (sword, shield, a second wind), the Hexer (frail, but with hex bolts) and the Skulker
(daggers, throwing knives, stabs the unaware for triple damage, can vanish). Potions, scrolls and wands are
unknown until used; their looks change every run. Find food, gold, better arms. Each level up offers a choice
of two perks. Death is final.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
Run:        python3 underhold.py
Self-test:  python3 underhold.py --selftest
"""
import math
import random
import sys
import time
from collections import deque

from arcadekit import (AUTO_LABEL, PAUSE_LINES, AutoMode, Canvas, MouseTerminal, clamp, load_scores, mix, overlay,
                       scale_art, shade, shared_key, submit, title_screen)
from arcadesound import Sound

GAME = "underhold"
MW, MH = 60, 30
FLOORS = 10
SIGHT = 8
WALL, FLOOR, DOOR, OPEN, STAIRS, WATER, LAVA = "#", ".", "+", "'", ">", "~", "^"
PASS = (FLOOR, DOOR, OPEN, STAIRS, WATER)
DIRS = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)]
MOVE = {"left": (-1, 0), "a": (-1, 0), "4": (-1, 0), "right": (1, 0), "d": (1, 0), "6": (1, 0),
        "up": (0, -1), "w": (0, -1), "8": (0, -1), "down": (0, 1), "s": (0, 1), "2": (0, 1),
        "y": (-1, -1), "7": (-1, -1), "u": (1, -1), "9": (1, -1), "b": (-1, 1), "1": (-1, 1), "n": (1, 1), "3": (1, 1)}
HUD_BG, HUD_FG = (14, 12, 22), (220, 220, 232)

CLASSES = {
    "Warden": dict(hp=32, acc=4, ev=0, arm=2, weapon="sword", gain=7, desc="sword and shield; F: second wind"),
    "Hexer": dict(hp=20, acc=2, ev=1, arm=0, weapon="staff", gain=4, desc="frail; F: hex bolt (mana)"),
    "Skulker": dict(hp=25, acc=5, ev=2, arm=0, weapon="dagger", gain=5, desc="stabs the unaware x3; F: vanish"),
}
CLASS_NAMES = list(CLASSES)
WEAPONS = {  # name: dmg lo, hi, accuracy bonus, first floor
    "staff": (1, 5, 1, 99), "dagger": (2, 5, 1, 1), "short sword": (2, 7, 0, 1), "sword": (3, 8, 0, 2),
    "spear": (3, 9, -1, 3), "axe": (4, 10, -1, 4), "war hammer": (5, 12, -2, 6), "rune blade": (5, 11, 1, 8),
}
ARMOURS = {"leather": (1, 1), "studded": (2, 2), "mail": (3, 4), "scale": (4, 6), "plate": (5, 8)}
POTIONS = ["healing", "greater healing", "haste", "might", "sight", "vigor", "poison", "confusion"]
SCROLLS = ["teleport", "mapping", "sharpening", "hardening", "dread", "blaze", "identify"]
WANDS = ["sparks", "frost", "slumber"]
POT_LOOKS = ["murky green", "bubbling red", "milky", "smoky grey", "violet", "golden", "inky", "pale blue", "amber",
             "fizzing pink"]
SCR_LOOKS = ["ZELGO MER", "VAS ORNU", "KIRA THUL", "ANOD ESH", "PRATT VEY", "MOLU SEN", "IKK HARAN", "DUAM FEL",
             "OSTRA LUN"]
WAND_LOOKS = ["oak", "bone", "glass", "iron", "crystal", "ash"]
POT_COLS = {"murky green": (90, 140, 70), "bubbling red": (220, 60, 60), "milky": (236, 236, 226),
            "smoky grey": (140, 140, 150), "violet": (170, 90, 220), "golden": (240, 200, 70), "inky": (50, 50, 90),
            "pale blue": (150, 200, 250), "amber": (230, 140, 50), "fizzing pink": (250, 140, 200)}

# name: hp, accuracy, dmg lo, hi, armour, speed, xp, floors (from, to), tags, sprite, colours
MONS = {
    "gnawer": (4, 1, 1, 3, 0, 130, 1, (1, 4), "melee", "beast", dict(b=(150, 110, 80), e=(220, 160, 150), l=(90, 60, 40), t=(200, 150, 140))),
    "cave newt": (6, 0, 1, 4, 0, 100, 2, (1, 3), "melee", "lizard", dict(b=(90, 170, 90), e=(240, 220, 90), l=(60, 120, 60), t=(80, 150, 80))),
    "moldbloom": (10, 1, 1, 4, 0, 0, 2, (1, 5), "stationary poison", "mold", dict(a=(230, 210, 80), b=(150, 130, 50))),
    "hobbler": (9, 2, 2, 5, 1, 100, 4, (1, 5), "melee gold", "hum", dict(h=(110, 150, 70), f=(130, 180, 90), b=(120, 90, 60), a=(130, 180, 90), l=(80, 60, 40), w=(180, 180, 190))),
    "slinger": (7, 2, 1, 4, 0, 100, 4, (2, 6), "ranged", "hum", dict(h=(150, 120, 70), f=(130, 180, 90), b=(160, 130, 80), a=(130, 180, 90), l=(80, 60, 40), w=(120, 90, 60))),
    "flitter": (5, 3, 1, 3, 0, 160, 3, (2, 6), "erratic", "bat", dict(b=(110, 90, 120), w=(80, 60, 90))),
    "gloam jelly": (16, 1, 2, 5, 0, 70, 6, (3, 7), "split", "jelly", dict(b=(90, 200, 190), e=(20, 60, 60))),
    "webspinner": (10, 3, 2, 4, 1, 110, 6, (3, 8), "poison", "spider", dict(b=(60, 50, 60), l=(110, 90, 100))),
    "lurker": (12, 4, 3, 7, 0, 100, 8, (4, 9), "invisible", "shade", dict(b=(70, 60, 100), e=(240, 240, 120))),
    "chanter": (10, 2, 1, 4, 0, 100, 9, (4, 9), "summon flee", "hum", dict(h=(180, 60, 60), f=(200, 170, 140), b=(140, 40, 50), a=(200, 170, 140), l=(90, 30, 30), w=(230, 200, 90))),
    "ash hound": (12, 4, 2, 6, 1, 140, 7, (5, 10), "pack", "beast", dict(b=(120, 116, 112), e=(250, 120, 60), l=(80, 76, 72), t=(100, 96, 92))),
    "ogrel": (30, 3, 4, 11, 2, 70, 14, (5, 10), "melee", "big", dict(b=(150, 120, 90), e=(240, 60, 40), a=(170, 140, 110))),
    "bone archer": (14, 5, 2, 5, 1, 100, 10, (5, 10), "ranged", "hum", dict(h=(230, 226, 210), f=(230, 226, 210), b=(200, 196, 180), a=(230, 226, 210), l=(200, 196, 180), w=(140, 100, 60))),
    "wisp": (9, 6, 2, 6, 0, 120, 9, (6, 10), "ranged flee erratic", "wisp", dict(a=(150, 220, 255), b=(240, 250, 255))),
    "cinder imp": (14, 5, 2, 6, 1, 140, 12, (7, 10), "ranged", "imp", dict(a=(250, 200, 80), b=(220, 80, 40), e=(255, 240, 120))),
    "hollow": (22, 6, 3, 8, 2, 100, 16, (7, 10), "drain", "shade", dict(b=(170, 170, 190), e=(120, 220, 255))),
    "stone warden": (45, 5, 5, 13, 5, 60, 22, (8, 10), "melee", "big", dict(b=(130, 130, 140), e=(120, 220, 255), a=(110, 110, 120))),
    "the Mawkeeper": (170, 8, 6, 14, 4, 100, 100, (99, 99), "boss summon ranged", "boss", dict(b=(90, 40, 110), e=(255, 80, 60), a=(150, 70, 170), c=(240, 200, 70))),
}
RANGED_DMG = {"slinger": (2, 5, "stone"), "bone archer": (3, 8, "arrow"), "wisp": (3, 7, "spark"),
              "cinder imp": (4, 9, "fire bolt"), "the Mawkeeper": (6, 13, "maw blast")}
PERKS = [("toughness", "+8 max HP"), ("precision", "+2 accuracy"), ("brawn", "+1 damage"), ("thick skin", "+1 armour"),
         ("quick healing", "regenerate faster"), ("light step", "+2 evasion"), ("deep breath", "+4 mana, or a faster ability")]

SPRITES = {
    "hum": ["..hh..", "..ff..", ".abbaw", "a.bb.w", "..bb..", ".l..l."],
    "beast": ["......", "......", "....ee", ".bbbbb", "tbbbb.", ".l..l."],
    "lizard": ["......", "......", "....be", "tbbbbb", ".l.l..", "......"],
    "mold": ["......", ".a..a.", "aabaab", ".abba.", "bbbbbb", "......"],
    "bat": ["......", "w.bb.w", "wwbbww", ".w..w.", "......", "......"],
    "jelly": ["......", "..bb..", ".bbbb.", "bebbeb", "bbbbbb", "......"],
    "spider": ["......", "l.bb.l", ".lbbl.", "llbbll", ".l..l.", "......"],
    "shade": ["..bb..", ".beeb.", ".bbbb.", "bbbbbb", "b.bb.b", "......"],
    "wisp": ["..a...", ".aba..", "abbba.", ".aba..", "..a...", "......"],
    "imp": ["a....a", ".bbbb.", ".beeb.", "..bb..", ".b..b.", "......"],
    "big": [".bbbb.", "bbeebb", "abbbba", "abbbba", ".b..b.", "bb..bb"],
    "boss": ["c.cc.c", "bbbbbb", "beebee", "abbbba", "abaaba", "bb..bb"],
}
HERO_COLS = {
    "Warden": dict(h=(200, 200, 210), f=(236, 200, 170), b=(70, 110, 200), a=(236, 200, 170), l=(60, 60, 80), w=(230, 230, 240)),
    "Hexer": dict(h=(140, 70, 200), f=(236, 200, 170), b=(110, 50, 170), a=(236, 200, 170), l=(80, 40, 120), w=(250, 210, 90)),
    "Skulker": dict(h=(50, 100, 70), f=(236, 200, 170), b=(60, 80, 60), a=(236, 200, 170), l=(40, 50, 40), w=(220, 220, 230)),
}
ITEM_SPR = {
    "potion": ["......", "..cc..", "..gg..", ".gggg.", ".gggg.", "..gg.."],
    "scroll": ["......", ".pppp.", ".pttp.", ".pppp.", ".pttp.", "......"],
    "weapon": ["....s.", "...s..", "..s...", ".hs...", "h.....", "......"],
    "armour": ["......", ".a..a.", ".aaaa.", ".aaaa.", "..aa..", "......"],
    "wand": ["......", "....t.", "...w..", "..w...", ".w....", "......"],
    "throw": ["......", "....s.", "...s..", "..h...", "......", "......"],
    "food": ["......", "......", ".bbbb.", "bbbbbb", ".bbbb.", "......"],
    "gold": ["......", "......", "..y...", ".yyy..", "yyyyy.", "......"],
}
THEMES = [  # floor, wall top, wall face, accent
    dict(floor=(104, 92, 78), wall=(44, 36, 30), face=(160, 128, 96), moss=(96, 112, 60)),
    dict(floor=(88, 96, 110), wall=(30, 36, 48), face=(124, 140, 170), moss=(70, 130, 106)),
    dict(floor=(104, 76, 66), wall=(46, 26, 22), face=(176, 100, 76), moss=(150, 86, 46)),
    dict(floor=(78, 68, 100), wall=(30, 24, 44), face=(122, 102, 166), moss=(110, 76, 160)),
]
LIGHT = [1.3, 1.15, 1.0, 0.85, 0.72]       # torchlight by distance (two tiles a step)

SND = Sound(GAME, {
    "step": [dict(w="noise", f=400, f2=200, d=0.03, v=0.08)],
    "hit": [dict(w="noise", f=2000, f2=400, d=0.08, v=0.35), dict(w="square", f=220, f2=120, d=0.06, v=0.2, at=0)],
    "miss": [dict(w="noise", f=1200, f2=3000, d=0.08, v=0.14, r="lin")],
    "hurt": [dict(w="square", f=300, f2=140, d=0.12, v=0.28, duty=0.3)],
    "kill": [dict(w="noise", f=3000, f2=200, d=0.2, v=0.35), dict(w="tri", f=660, f2=220, d=0.18, v=0.25, at=0)],
    "pickup": [dict(w="tri", f=880, d=0.04, v=0.22), dict(w="tri", f=1320, d=0.06, v=0.2)],
    "potion": [dict(w="sine", f=300, f2=700, d=0.25, v=0.3, vib=(12, 0.5))],
    "scroll": [dict(w="noise", f=6000, f2=2000, d=0.15, v=0.2), dict(w="tri", f=990, d=0.2, v=0.2, at=0.05)],
    "zap": [dict(w="saw", f=1600, f2=300, d=0.18, v=0.25)],
    "stairs": [dict(w="tri", f=f, d=0.08, v=0.25) for f in (523, 440, 349, 262)],
    "levelup": [dict(w="square", f=f, d=0.08, v=0.26, duty=0.25) for f in (523, 659, 784, 1047)],
    "death": [dict(w="tri", f=392, d=0.25, v=0.4), dict(w="tri", f=330, d=0.25, v=0.4), dict(w="tri", f=262, d=0.25, v=0.4),
              dict(w="tri", f=196, f2=130, d=0.8, v=0.4, r="lin")],
    "win": [dict(w="square", f=f, d=0.1, v=0.28, duty=0.25) for f in (523, 659, 784, 1047, 784, 1047)] +
           [dict(w="tri", f=1319, d=0.7, v=0.4, vib=(6, 0.3), r="lin")],
    "door": [dict(w="noise", f=300, f2=150, d=0.1, v=0.2)],
    "menu": [dict(w="tri", f=660, d=0.025, v=0.2)],
    "start": [dict(w="square", f=262, d=0.08, v=0.3, duty=0.25), dict(w="square", f=392, d=0.15, v=0.3, duty=0.25)],
    "pause": [dict(w="tri", f=523, f2=392, d=0.07, v=0.22)],
    "sound_on": [dict(w="tri", f=440, d=0.06, v=0.35), dict(w="tri", f=880, d=0.12, v=0.35)],
})
HELP = [
    "UNDERHOLD - keys",
    "",
    "Arrows / WASD / numpad   move, attack by moving into a foe",
    "Y U B N                  diagonals",
    "Mouse click              travel there / attack next to you",
    "X  explore    >  stairs (travel, then descend)",
    "G  pick up    I  inventory (then the item's letter)",
    "Q  quaff      R  read     Z  zap     T  throw",
    "E  equip      F  ability  C  rest    Space  wait",
    "L  look (arrows move, Esc ends)",
    "Esc / P  pause     ?  help",
    "",
    "Potions, scrolls and wands are unknown until used.",
]


def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def line(x0, y0, x1, y1):
    pts = []
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        pts.append((x0, y0))
        if x0 == x1 and y0 == y1:
            return pts
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


# =============================================================================================
# Floors
# =============================================================================================
def flood(m, start, passable=PASS):
    seen = {start}
    q = deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy in DIRS:
            nx, ny = x + dx, y + dy
            if 0 <= nx < MW and 0 <= ny < MH and (nx, ny) not in seen and m[ny][nx] in passable:
                seen.add((nx, ny))
                q.append((nx, ny))
    return seen


def gen_rooms(rnd):
    m = [[WALL] * MW for _ in range(MH)]
    rooms = []
    want = rnd.randint(8, 12)
    for _ in range(400):
        w, h = rnd.randint(4, 10), rnd.randint(3, 6)
        x, y = rnd.randint(1, MW - w - 2), rnd.randint(1, MH - h - 2)
        if any(x - 2 < rx + rw and rx - 2 < x + w and y - 2 < ry + rh and ry - 2 < y + h for rx, ry, rw, rh in rooms):
            continue
        rooms.append((x, y, w, h))
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                m[yy][xx] = FLOOR
        if len(rooms) >= want:
            break
    rooms.sort(key=lambda r: r[0] + r[2] / 2)

    def centre(r):
        return r[0] + r[2] // 2, r[1] + r[3] // 2

    def dig(a, b):
        (x0, y0), (x1, y1) = centre(a), centre(b)
        if rnd.random() < 0.5:
            pts = [(x, y0) for x in range(min(x0, x1), max(x0, x1) + 1)] + [(x1, y) for y in range(min(y0, y1), max(y0, y1) + 1)]
        else:
            pts = [(x0, y) for y in range(min(y0, y1), max(y0, y1) + 1)] + [(x, y1) for x in range(min(x0, x1), max(x0, x1) + 1)]
        for x, y in pts:
            if m[y][x] == WALL:
                m[y][x] = "c"                          # corridor, becomes floor below
    for a, b in zip(rooms, rooms[1:]):
        dig(a, b)
    for _ in range(rnd.randint(1, 3)):
        dig(rnd.choice(rooms), rnd.choice(rooms))
    for x, y, w, h in rooms:                           # doors where a corridor meets a room
        for xx in range(x - 1, x + w + 1):
            for yy in (y - 1, y + h):
                if m[yy][xx] == "c" and m[yy][xx - 1] in (WALL,) and m[yy][xx + 1] in (WALL,) and rnd.random() < 0.6:
                    m[yy][xx] = DOOR
        for yy in range(y, y + h):
            for xx in (x - 1, x + w):
                if m[yy][xx] == "c" and m[yy - 1][xx] == WALL and m[yy + 1][xx] == WALL and rnd.random() < 0.6:
                    m[yy][xx] = DOOR
    for y in range(MH):
        for x in range(MW):
            if m[y][x] == "c":
                m[y][x] = FLOOR
    return m, rooms


def gen_cave(rnd):
    while True:
        m = [[WALL if (x in (0, MW - 1) or y in (0, MH - 1) or rnd.random() < 0.45) else FLOOR for x in range(MW)]
             for y in range(MH)]
        for _ in range(5):
            n = [row[:] for row in m]
            for y in range(1, MH - 1):
                for x in range(1, MW - 1):
                    walls = sum(m[y + dy][x + dx] == WALL for dx in (-1, 0, 1) for dy in (-1, 0, 1))
                    n[y][x] = WALL if walls >= 5 else FLOOR
            m = n
        cells = [(x, y) for y in range(MH) for x in range(MW) if m[y][x] == FLOOR]
        best = set()
        left = set(cells)
        while left:
            reg = flood(m, next(iter(left)))
            left -= reg
            if len(reg) > len(best):
                best = reg
        if len(best) > MW * MH * 0.35:
            for x, y in cells:
                if (x, y) not in best:
                    m[y][x] = WALL
            return m, []


class Floor:
    def __init__(self, depth, seed):
        rnd = self.rnd = random.Random(seed)
        self.depth = depth
        self.theme = THEMES[min(3, (depth - 1) // 3)]
        cave = depth == FLOORS or rnd.random() < (0.3 + depth * 0.04)
        self.m, self.rooms = gen_cave(rnd) if cave else gen_rooms(rnd)
        self.cave = cave
        floors = [(x, y) for y in range(MH) for x in range(MW) if self.m[y][x] == FLOOR]
        self.start = rnd.choice(floors)
        self.pools(rnd)
        dist = self.bfs(self.start)
        far = max(dist, key=lambda p: (dist[p], p))
        self.far = far
        if depth < FLOORS:
            self.m[far[1]][far[0]] = STAIRS
            self.stairs = far
        else:
            self.stairs = None
        self.seen = [[False] * MW for _ in range(MH)]
        self.mons, self.items = [], {}

    def pools(self, rnd):
        for _ in range(rnd.randint(1, 4)):
            kind = LAVA if self.depth >= 5 and rnd.random() < 0.5 else WATER
            cx, cy = rnd.randrange(2, MW - 2), rnd.randrange(2, MH - 2)
            r = rnd.uniform(1.2, 2.8)
            blob = [(x, y) for y in range(int(cy - r), int(cy + r) + 1) for x in range(int(cx - r), int(cx + r) + 1)
                    if 0 < x < MW - 1 and 0 < y < MH - 1 and (x - cx) ** 2 + (y - cy) ** 2 <= r * r
                    and self.m[y][x] == FLOOR and (x, y) != self.start]
            for x, y in blob:
                self.m[y][x] = kind
            if kind == LAVA:                           # lava must never cut the floor in two
                total = sum(1 for y in range(MH) for x in range(MW) if self.m[y][x] in PASS)
                if len(flood(self.m, self.start)) != total:
                    for x, y in blob:
                        self.m[y][x] = FLOOR

    def bfs(self, start, known=None):
        dist = {start: 0}
        q = deque([start])
        while q:
            x, y = q.popleft()
            for dx, dy in DIRS:
                nx, ny = x + dx, y + dy
                if 0 <= nx < MW and 0 <= ny < MH and (nx, ny) not in dist and self.m[ny][nx] in PASS:
                    if known is not None and not self.seen[ny][nx]:
                        continue
                    dist[(nx, ny)] = dist[(x, y)] + 1
                    q.append((nx, ny))
        return dist

    def opaque(self, x, y):
        return not (0 <= x < MW and 0 <= y < MH) or self.m[y][x] in (WALL, DOOR)

    def passable(self, x, y):
        return 0 <= x < MW and 0 <= y < MH and self.m[y][x] in PASS


MULT = [[1, 0, 0, -1, -1, 0, 0, 1], [0, 1, -1, 0, 0, -1, 1, 0], [0, 1, 1, 0, 0, -1, -1, 0], [1, 0, 0, 1, -1, 0, 0, -1]]


def fov(fl, ox, oy, radius):
    """Recursive shadowcasting: the set of tiles seen from (ox, oy)."""
    vis = {(ox, oy)}

    def cast(row, start, end, xx, xy, yx, yy):
        if start < end:
            return
        r2 = radius * radius
        for j in range(row, radius + 1):
            dx, dy = -j - 1, -j
            blocked = False
            new_start = start
            while dx <= 0:
                dx += 1
                X, Y = ox + dx * xx + dy * xy, oy + dx * yx + dy * yy
                ls, rs = (dx - 0.5) / (dy + 0.5), (dx + 0.5) / (dy - 0.5)
                if start < rs:
                    continue
                if end > ls:
                    break
                if dx * dx + dy * dy <= r2 and 0 <= X < MW and 0 <= Y < MH:
                    vis.add((X, Y))
                if blocked:
                    if fl.opaque(X, Y):
                        new_start = rs
                        continue
                    blocked = False
                    start = new_start
                elif fl.opaque(X, Y) and j < radius:
                    blocked = True
                    cast(j + 1, start, ls, xx, xy, yx, yy)
                    new_start = rs
            if blocked:
                break
    for o in range(8):
        cast(1, 1.0, 0.0, MULT[0][o], MULT[1][o], MULT[2][o], MULT[3][o])
    return vis


# =============================================================================================
# Things
# =============================================================================================
class Item:
    def __init__(self, kind, sub, n=1, plus=0, charges=0):
        self.kind, self.sub, self.n, self.plus, self.charges = kind, sub, n, plus, charges

    def stacks(self):
        return self.kind in ("potion", "scroll", "throw", "food")


class Mon:
    def __init__(self, kind, x, y, depth=1):
        hp, acc, lo, hi, arm, spd, xp, _, tags, spr, cols = MONS[kind]
        bonus = max(0, depth - MONS[kind][7][0])
        self.kind, self.x, self.y = kind, x, y
        self.hp = self.maxhp = hp + bonus * 2
        self.acc, self.lo, self.hi, self.arm, self.speed, self.xp = acc + bonus // 2, lo, hi, arm, spd, xp
        self.tags = tags.split()
        self.awake = False
        self.energy = 0
        self.flee = self.slow = self.sleep = 0
        self.cool = 0
        self.seen_hero = None

    @property
    def pos(self):
        return (self.x, self.y)

    def has(self, t):
        return t in self.tags


class Hero:
    def __init__(self, cls):
        c = CLASSES[cls]
        self.cls = cls
        self.x = self.y = 0
        self.hp = self.maxhp = c["hp"]
        self.acc, self.ev, self.base_arm = c["acc"], c["ev"], c["arm"]
        self.level, self.xp = 1, 0
        self.dmg_bonus = 0
        self.regen = 9
        self.mana = self.maxmana = 12 if cls == "Hexer" else 0
        self.cool = 0
        self.weapon = Item("weapon", c["weapon"])
        self.armour = Item("armour", "leather") if cls != "Hexer" else None
        self.pack = []
        self.hunger = 1500
        self.poison = self.confused = self.haste = self.vanish = 0
        self.perks = []

    @property
    def pos(self):
        return (self.x, self.y)

    def arm(self):
        return self.base_arm + (ARMOURS[self.armour.sub][0] + self.armour.plus if self.armour else 0)

    def dmg(self):
        lo, hi, a, _ = WEAPONS[self.weapon.sub]
        return lo + self.weapon.plus + self.dmg_bonus, hi + self.weapon.plus + self.dmg_bonus

    def hit_acc(self):
        return self.acc + WEAPONS[self.weapon.sub][2]


def hit_chance(acc, ev):
    return clamp(65 + 5 * (acc - ev), 15, 95)


def xp_need(level):
    return 10 * level + 5 * level * level


# =============================================================================================
# The game
# =============================================================================================
class Game:
    def __init__(self, cls="Warden", seed=None, demo=False):
        self.rnd = random.Random(seed)
        self.seed = self.rnd.randrange(1 << 30)
        self.demo = demo
        self.hero = Hero(cls)
        looks = self.rnd.sample(POT_LOOKS, len(POTIONS))
        self.looks = dict(zip(POTIONS, looks))
        self.looks.update(zip(SCROLLS, self.rnd.sample(SCR_LOOKS, len(SCROLLS))))
        self.looks.update(zip(WANDS, self.rnd.sample(WAND_LOOKS, len(WANDS))))
        self.known = set()
        self.log = []
        self.turn = 0
        self.kills = 0
        self.gold = 0
        self.maxdepth = 1
        self.over = None                      # None, "dead", "won"
        self.cause = ""
        self.levelup = None                   # a pair of perks to choose from
        self.prompt = None                    # (title, action, items)
        self.look = None                      # look cursor
        self.path = []                        # travel / explore steps
        self.exploring = False
        self.fx = []
        self.t = 0.0
        self.paused = self.help = False
        self.record = None
        h = self.hero
        h.pack.append(Item("food", "ration", 1 if h.cls != "Warden" else 2))
        h.pack.append(Item("potion", "healing", 1))
        if h.cls == "Skulker":
            h.pack.append(Item("throw", "knife", 4))
        if h.cls == "Hexer":
            h.pack.append(Item("wand", "sparks", charges=5))
        self.known.add("healing")
        self.enter(1)

    def say(self, msg, col=(220, 220, 232)):
        self.log.append((msg, col, self.turn))
        self.log = self.log[-60:]

    def sfx(self, name, vol=1.0):
        if not self.demo:
            SND.play(name, vol=vol)

    # --- floors ----------------------------------------------------------------------------------
    def enter(self, depth):
        self.depth = depth
        self.maxdepth = max(self.maxdepth, depth)
        self.fl = Floor(depth, self.seed * 31 + depth)
        fl = self.fl
        self.hero.x, self.hero.y = fl.start
        rnd = fl.rnd
        floors = [(x, y) for y in range(MH) for x in range(MW) if fl.m[y][x] == FLOOR and cheb((x, y), fl.start) > 6]
        rnd.shuffle(floors)
        pool = [k for k, v in MONS.items() if v[7][0] <= depth <= v[7][1]]
        n = 4 + depth + rnd.randint(0, 3)
        while n > 0 and floors:
            kind = rnd.choice(pool)
            x, y = floors.pop()
            group = 3 if "pack" in MONS[kind][8] else 1
            for _ in range(group):
                spot = self.free_near(x, y)
                if spot:
                    m = Mon(kind, spot[0], spot[1], depth)
                    m.awake = rnd.random() < 0.35
                    fl.mons.append(m)
            n -= group
        if depth == FLOORS:
            bx, by = fl.far
            boss = Mon("the Mawkeeper", bx, by, depth)
            boss.awake = False
            fl.mons.append(boss)
        spots = [(x, y) for y in range(MH) for x in range(MW) if fl.m[y][x] == FLOOR and (x, y) != fl.start]
        rnd.shuffle(spots)
        for _ in range(rnd.randint(6, 9)):
            if spots:
                fl.items[spots.pop()] = [self.random_item(rnd)]
        for _ in range(rnd.randint(3, 6)):
            if spots:
                fl.items[spots.pop()] = [Item("gold", "gold", rnd.randint(5, 12) * depth)]
        if depth % 2 == 1 and spots:
            fl.items.setdefault(spots.pop(), []).append(Item("food", "ration"))
        self.update_fov()
        if depth == FLOORS:
            self.say("The air is hot and heavy. Something huge is breathing.", (255, 140, 120))
        else:
            self.say("Floor %d." % depth, (200, 200, 150))

    def random_item(self, rnd):
        r = rnd.random()
        d = self.depth
        if r < 0.32:
            return Item("potion", rnd.choice(POTIONS[:6] * 2 + POTIONS[6:]))
        if r < 0.55:
            return Item("scroll", rnd.choice(SCROLLS))
        if r < 0.66:
            subs = [k for k, v in WEAPONS.items() if v[3] <= d]
            return Item("weapon", rnd.choice(subs), plus=rnd.choice((0, 0, 0, 1, 1, 2)) if d > 2 else 0)
        if r < 0.76:
            subs = [k for k, v in ARMOURS.items() if v[1] <= d + 1]
            return Item("armour", rnd.choice(subs), plus=rnd.choice((0, 0, 1)))
        if r < 0.84:
            return Item("wand", rnd.choice(WANDS), charges=rnd.randint(3, 6))
        if r < 0.92:
            return Item("throw", "knife", rnd.randint(2, 5))
        return Item("food", "ration")

    def free_near(self, x, y):
        for r in range(0, 4):
            cands = [(x + dx, y + dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1)]
            self.rnd.shuffle(cands)
            for p in cands:
                if self.fl.passable(*p) and self.fl.m[p[1]][p[0]] != STAIRS and not self.mon_at(p) and p != self.hero.pos:
                    return p
        return None

    def mon_at(self, p):
        for m in self.fl.mons:
            if m.pos == p:
                return m
        return None

    def update_fov(self):
        h = self.hero
        self.vis = fov(self.fl, h.x, h.y, SIGHT)
        for x, y in self.vis:
            self.fl.seen[y][x] = True

    def visible(self, m):
        if m.pos not in self.vis:
            return False
        if m.has("invisible") and cheb(m.pos, self.hero.pos) > 1:
            return False
        return True

    # --- names -----------------------------------------------------------------------------------
    def name(self, it, article=True):
        if it.kind == "weapon":
            s = "%s%s" % ("+%d " % it.plus if it.plus else "", it.sub)
        elif it.kind == "armour":
            s = "%s%s armour" % ("+%d " % it.plus if it.plus else "", it.sub)
        elif it.kind == "potion":
            s = ("potion of %s" % it.sub) if it.sub in self.known else "%s potion" % self.looks[it.sub]
            if it.n > 1:
                s = "%d %s" % (it.n, s.replace("potion", "potions"))
        elif it.kind == "scroll":
            s = ("scroll of %s" % it.sub) if it.sub in self.known else 'scroll "%s"' % self.looks[it.sub]
            if it.n > 1:
                s = "%d %s" % (it.n, s.replace("scroll", "scrolls"))
        elif it.kind == "wand":
            s = ("wand of %s (%d)" % (it.sub, it.charges)) if it.sub in self.known else "%s wand" % self.looks[it.sub]
        elif it.kind == "throw":
            s = "%d throwing knives" % it.n if it.n > 1 else "throwing knife"
        elif it.kind == "food":
            s = "%d rations" % it.n if it.n > 1 else "ration"
        else:
            s = "%d gold" % it.n
        return s

    # --- actions ---------------------------------------------------------------------------------
    def act_ok(self):
        return not (self.over or self.levelup or self.paused)

    def try_move(self, dx, dy):
        if not self.act_ok():
            return False
        h = self.hero
        if h.confused and self.rnd.random() < 0.6:
            dx, dy = self.rnd.choice(DIRS)
        nx, ny = h.x + dx, h.y + dy
        m = self.mon_at((nx, ny))
        if m:
            self.attack(m)
            self.end_turn()
            return True
        if not (0 <= nx < MW and 0 <= ny < MH):
            return False
        t = self.fl.m[ny][nx]
        if t == DOOR:
            self.fl.m[ny][nx] = OPEN
            self.sfx("door", 0.6)
            self.end_turn()
            return True
        if t not in PASS:
            if t == LAVA:
                self.say("Lava. Not that way.", (255, 140, 90))
            return False
        h.x, h.y = nx, ny
        self.sfx("step", 0.5)
        here = self.fl.items.get(h.pos)
        if here:
            if len(here) == 1 and here[0].kind == "gold":
                self.pickup()
                return True
            self.say("You see %s here." % ", ".join(self.name(i) for i in here[:3]), (200, 200, 170))
        self.end_turn()
        return True

    def attack(self, m):
        h = self.hero
        lo, hi = h.dmg()
        unaware = (not m.awake) or m.sleep > 0 or h.vanish > 0
        if h.cls == "Skulker" and unaware:
            d = self.rnd.randint(lo, hi) * 3
            self.say("You stab the unaware %s!" % m.kind, (255, 220, 120))
            self.hurt_mon(m, d)
            h.vanish = 0
            return
        if self.rnd.randint(1, 100) <= hit_chance(h.hit_acc(), m.acc // 2):
            d = max(1, self.rnd.randint(lo, hi) - self.rnd.randint(0, m.arm))
            self.sfx("hit")
            self.say("You hit the %s." % m.kind)
            self.hurt_mon(m, d)
        else:
            self.sfx("miss")
            self.say("You miss the %s." % m.kind, (160, 160, 170))
        m.awake = True
        m.sleep = 0

    def hurt_mon(self, m, d, src="you"):
        m.hp -= d
        m.awake = True
        m.sleep = 0
        self.fx.append([m.x, m.y, (255, 255, 255), 0.12])
        if m.hp <= 0:
            self.kill(m)
            return
        if m.has("split") and m.hp >= 3:
            spot = self.free_near(m.x, m.y)
            if spot and spot != m.pos:
                c = Mon(m.kind, spot[0], spot[1], self.depth)
                c.hp = c.maxhp = m.hp // 2
                m.hp -= c.hp
                c.awake = True
                self.fl.mons.append(c)
                self.say("The %s splits in two!" % m.kind, (150, 230, 220))
        if m.has("flee") and m.hp < m.maxhp * 0.4:
            m.flee = 8

    def kill(self, m):
        if m in self.fl.mons:
            self.fl.mons.remove(m)
        self.kills += 1
        self.sfx("kill")
        self.say("The %s dies." % m.kind, (240, 200, 120))
        if m.has("gold") or m.has("boss"):
            self.fl.items.setdefault(m.pos, []).append(Item("gold", "gold", self.rnd.randint(4, 10) * self.depth))
        self.gain_xp(m.xp)
        if m.has("boss"):
            self.over = "won"
            self.cause = "slew the Mawkeeper"
            self.sfx("win")
            self.say("The Mawkeeper falls. The Underhold is quiet at last.", (255, 230, 140))
            self.finish()

    def gain_xp(self, n):
        h = self.hero
        h.xp += n
        while h.xp >= xp_need(h.level) and not self.levelup:
            h.xp -= xp_need(h.level)
            h.level += 1
            g = CLASSES[h.cls]["gain"]
            h.maxhp += g
            h.hp += g
            h.acc += 1
            self.sfx("levelup")
            self.say("You reach level %d! Choose a perk." % h.level, (160, 240, 160))
            self.levelup = self.rnd.sample(PERKS, 2)

    def choose_perk(self, i):
        if not self.levelup:
            return
        name, _ = self.levelup[i]
        h = self.hero
        h.perks.append(name)
        if name == "toughness":
            h.maxhp += 8
            h.hp += 8
        elif name == "precision":
            h.acc += 2
        elif name == "brawn":
            h.dmg_bonus += 1
        elif name == "thick skin":
            h.base_arm += 1
        elif name == "quick healing":
            h.regen = max(3, h.regen - 3)
        elif name == "light step":
            h.ev += 2
        elif h.cls == "Hexer":
            h.maxmana += 4
            h.mana += 4
        else:
            h.cool = 0                                 # the ability is ready now, and recharges faster
        self.say("You take %s." % name, (160, 240, 160))
        self.levelup = None
        self.gain_xp(0)

    def pickup(self, want=None):
        if not self.act_ok():
            return False
        h = self.hero
        here = self.fl.items.get(h.pos)
        if not here:
            self.say("Nothing here.", (160, 160, 170))
            return False
        for it in list(here):
            if want is not None and it not in want:
                continue
            if it.kind == "gold":
                self.gold += it.n
                self.say("You pick up %d gold." % it.n, (240, 210, 90))
                here.remove(it)
                continue
            if not self.add_to_pack(it):
                self.say("Your pack is full.", (255, 140, 120))
                break
            here.remove(it)
            self.say("You pick up %s." % self.name(it), (200, 230, 200))
        if not here:
            del self.fl.items[h.pos]
        self.sfx("pickup")
        self.end_turn()
        return True

    def add_to_pack(self, it):
        p = self.hero.pack
        if it.stacks():
            for o in p:
                if o.kind == it.kind and o.sub == it.sub:
                    o.n += it.n
                    return True
        if len(p) >= 20:
            return False
        p.append(it)
        return True

    def use_one(self, it):
        it.n -= 1
        if it.n <= 0 and it in self.hero.pack:
            self.hero.pack.remove(it)

    def targets(self):
        h = self.hero
        vm = [m for m in self.fl.mons if self.visible(m) and self.clear(h.pos, m.pos)]
        return sorted(vm, key=lambda m: (cheb(h.pos, m.pos), m.hp))

    def clear(self, a, b):
        for x, y in line(a[0], a[1], b[0], b[1])[1:-1]:
            if self.fl.opaque(x, y) or self.mon_at((x, y)):
                return False
        return True

    def bolt_fx(self, a, b, col):
        for x, y in line(a[0], a[1], b[0], b[1])[1:]:
            self.fx.append([x, y, col, 0.2])

    def quaff(self, it):
        if not self.act_ok() or it.kind != "potion":
            return False
        h = self.hero
        s = it.sub
        self.use_one(it)
        self.sfx("potion")
        was = s in self.known
        self.known.add(s)
        if s == "healing":
            h.hp = min(h.maxhp, h.hp + max(12, h.maxhp // 2))
            h.poison = 0
            self.say("You feel much better.", (140, 240, 140))
        elif s == "greater healing":
            h.maxhp += 2
            h.hp = h.maxhp
            h.poison = h.confused = 0
            self.say("Warmth floods through you.", (140, 240, 140))
        elif s == "haste":
            h.haste = 20
            self.say("Everything around you slows down.", (200, 220, 255))
        elif s == "might":
            h.dmg_bonus += 1
            self.say("Your arms feel stronger.", (255, 200, 140))
        elif s == "sight":
            for y in range(MH):
                for x in range(MW):
                    if self.fl.m[y][x] != WALL or any(0 <= x + dx < MW and 0 <= y + dy < MH and self.fl.m[y + dy][x + dx] != WALL
                                                      for dx, dy in DIRS):
                        self.fl.seen[y][x] = True
            self.say("The whole floor appears in your mind.", (200, 220, 255))
        elif s == "vigor":
            h.maxhp += 5
            h.hp += 5
            self.say("You feel hardier.", (140, 240, 140))
        elif s == "poison":
            h.poison += 8
            self.say("Bitter! You are poisoned.", (160, 220, 80))
        else:
            h.confused = 10
            self.say("The walls swim. You are confused.", (230, 160, 230))
        if not was:
            self.say("(It was a potion of %s.)" % s, (170, 170, 190))
        self.end_turn()
        return True

    def read(self, it):
        if not self.act_ok() or it.kind != "scroll":
            return False
        h = self.hero
        s = it.sub
        self.use_one(it)
        self.sfx("scroll")
        self.known.add(s)
        if s == "teleport":
            spot = self.rnd.choice([(x, y) for y in range(MH) for x in range(MW) if self.fl.m[y][x] == FLOOR and not self.mon_at((x, y))])
            h.x, h.y = spot
            self.say("The world lurches. You are elsewhere.", (200, 200, 255))
        elif s == "mapping":
            for y in range(MH):
                for x in range(MW):
                    if self.fl.m[y][x] != WALL:
                        self.fl.seen[y][x] = True
                        for dx, dy in DIRS:
                            if 0 <= x + dx < MW and 0 <= y + dy < MH:
                                self.fl.seen[y + dy][x + dx] = True
            self.say("A map of the floor unfolds.", (200, 220, 255))
        elif s == "sharpening":
            h.weapon.plus += 1
            self.say("Your %s gleams." % h.weapon.sub, (230, 230, 255))
        elif s == "hardening":
            if h.armour:
                h.armour.plus += 1
                self.say("Your armour hardens.", (230, 230, 255))
            else:
                h.base_arm += 1
                self.say("Your skin hardens.", (230, 230, 255))
        elif s == "dread":
            for m in self.fl.mons:
                if m.pos in self.vis and not m.has("boss"):
                    m.flee = 15
            self.say("A wave of dread rolls out from you.", (230, 180, 255))
        elif s == "blaze":
            self.say("Fire bursts all around you!", (255, 160, 80))
            for m in list(self.fl.mons):
                if cheb(m.pos, h.pos) <= 2:
                    self.hurt_mon(m, self.rnd.randint(6, 12) + self.depth)
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    self.fx.append([h.x + dx, h.y + dy, (255, 140, 60), 0.3])
        else:
            unk = [i for i in h.pack if i.kind in ("potion", "scroll", "wand") and i.sub not in self.known]
            if unk:
                i = self.rnd.choice(unk)
                self.known.add(i.sub)
                self.say("It is %s." % self.name(i), (200, 220, 255))
            else:
                self.say("You feel knowledgeable, but there is nothing to learn.", (170, 170, 190))
        self.end_turn()
        return True

    def zap(self, it):
        if not self.act_ok() or it.kind != "wand":
            return False
        if it.charges <= 0:
            self.say("The wand is spent.", (160, 160, 170))
            return False
        ts = self.targets()
        if not ts:
            self.say("No target in sight.", (160, 160, 170))
            return False
        m = ts[0]
        it.charges -= 1
        self.known.add(it.sub)
        self.sfx("zap")
        if it.sub == "sparks":
            self.bolt_fx(self.hero.pos, m.pos, (150, 220, 255))
            self.say("Sparks crackle into the %s." % m.kind, (150, 220, 255))
            self.hurt_mon(m, self.rnd.randint(6, 12) + self.depth // 2)
        elif it.sub == "frost":
            self.bolt_fx(self.hero.pos, m.pos, (200, 240, 255))
            self.say("Frost bites the %s." % m.kind, (200, 240, 255))
            m.slow = 10
            self.hurt_mon(m, self.rnd.randint(3, 7))
        else:
            self.bolt_fx(self.hero.pos, m.pos, (200, 160, 255))
            if not m.has("boss"):
                m.sleep = 12
                self.say("The %s falls asleep." % m.kind, (200, 160, 255))
            else:
                self.say("The Mawkeeper shrugs it off.", (200, 160, 255))
        self.end_turn()
        return True

    def throw(self, it):
        if not self.act_ok() or it.kind != "throw":
            return False
        ts = self.targets()
        if not ts:
            self.say("No target in sight.", (160, 160, 170))
            return False
        m = ts[0]
        self.use_one(it)
        self.bolt_fx(self.hero.pos, m.pos, (220, 220, 230))
        h = self.hero
        if self.rnd.randint(1, 100) <= hit_chance(h.acc + 1, m.acc // 2):
            d = self.rnd.randint(2, 6) + (2 if h.cls == "Skulker" else 0)
            if h.cls == "Skulker" and (not m.awake or m.sleep):
                d *= 2
            self.sfx("hit")
            self.say("The knife strikes the %s." % m.kind)
            self.hurt_mon(m, d)
        else:
            self.sfx("miss")
            self.say("The knife misses.", (160, 160, 170))
        if self.fl.passable(*m.pos) and self.rnd.random() < 0.7:
            self.fl.items.setdefault(m.pos if m in self.fl.mons else m.pos, []).append(Item("throw", "knife"))
        self.end_turn()
        return True

    def equip(self, it):
        if not self.act_ok() or it.kind not in ("weapon", "armour", "food"):
            return False
        h = self.hero
        if it.kind == "food":
            return self.eat(it)
        h.pack.remove(it)
        if it.kind == "weapon":
            if h.weapon:
                h.pack.append(h.weapon)
            h.weapon = it
        else:
            if h.armour:
                h.pack.append(h.armour)
            h.armour = it
        self.say("You now use %s." % self.name(it), (200, 230, 200))
        self.end_turn()
        return True

    def eat(self, it):
        self.use_one(it)
        self.hero.hunger = min(1800, self.hero.hunger + 1100)
        self.say("You eat a ration. Much better.", (200, 230, 200))
        self.end_turn()
        return True

    def drop(self, it):
        if not self.act_ok():
            return False
        self.hero.pack.remove(it)
        self.fl.items.setdefault(self.hero.pos, []).append(it)
        self.say("You drop %s." % self.name(it))
        self.end_turn()
        return True

    def ability(self):
        if not self.act_ok():
            return False
        h = self.hero
        if h.cls == "Hexer":
            if h.mana < 3:
                self.say("Not enough mana.", (160, 160, 170))
                return False
            ts = self.targets()
            if not ts:
                self.say("No target in sight.", (160, 160, 170))
                return False
            h.mana -= 3
            m = ts[0]
            self.sfx("zap")
            self.bolt_fx(h.pos, m.pos, (220, 120, 255))
            self.say("Your hex bolt sears the %s." % m.kind, (220, 140, 255))
            self.hurt_mon(m, self.rnd.randint(4, 8) + h.level)
        elif h.cool > 0:
            self.say("Not ready yet (%d turns)." % h.cool, (160, 160, 170))
            return False
        elif h.cls == "Warden":
            h.hp = min(h.maxhp, h.hp + h.maxhp * 2 // 5)
            h.cool = 150 - (40 if "deep breath" in h.perks else 0)
            self.sfx("potion")
            self.say("You catch a second wind.", (140, 240, 140))
        else:
            h.vanish = 8
            h.cool = 100 - (30 if "deep breath" in h.perks else 0)
            for m in self.fl.mons:
                m.seen_hero = None
            self.say("You melt into the shadows.", (150, 180, 160))
        self.end_turn()
        return True

    def wait(self):
        if self.act_ok():
            self.end_turn()
            return True
        return False

    def descend(self):
        if not self.act_ok():
            return False
        if self.fl.m[self.hero.y][self.hero.x] != STAIRS:
            return False
        self.sfx("stairs")
        self.path = []
        self.enter(self.depth + 1)
        return True

    # --- the world's turn ------------------------------------------------------------------------
    def end_turn(self):
        h = self.hero
        self.turn += 1
        cost = 50 if h.haste > 0 else 100
        h.haste = max(0, h.haste - 1)
        h.confused = max(0, h.confused - 1)
        h.vanish = max(0, h.vanish - 1)
        h.cool = max(0, h.cool - 1)
        h.hunger -= 1
        if h.hunger == 200:
            self.say("You are getting hungry.", (240, 200, 120))
        if h.hunger <= 0:
            h.hunger = 0
            if self.turn % 4 == 0:
                self.hurt_hero(1, "starved")
        if h.poison > 0:
            h.poison -= 1
            self.hurt_hero(1, "poison")
        elif self.turn % h.regen == 0 and h.hunger > 0:
            h.hp = min(h.maxhp, h.hp + 1)
        if h.maxmana and self.turn % 5 == 0:
            h.mana = min(h.maxmana, h.mana + 1)
        self.update_fov()
        dist = self.fl.bfs(h.pos)
        for m in list(self.fl.mons):
            if self.over:
                break
            if m not in self.fl.mons:
                continue
            spd = m.speed * (0.5 if m.slow else 1)
            m.energy += spd * cost / 100
            m.slow = max(0, m.slow - 1)
            while m.energy >= 100 and m in self.fl.mons and not self.over:
                m.energy -= 100
                self.mon_act(m, dist)
        if self.rnd.random() < 0.012 and self.depth < FLOORS:   # something new wanders in, out of sight
            far = [(x, y) for (x, y), d in dist.items() if d > 14 and (x, y) not in self.vis and self.fl.m[y][x] == FLOOR]
            if far:
                pool = [k for k, v in MONS.items() if v[7][0] <= self.depth <= v[7][1]]
                x, y = self.rnd.choice(far)
                if not self.mon_at((x, y)):
                    self.fl.mons.append(Mon(self.rnd.choice(pool), x, y, self.depth))
        self.update_fov()

    def noticed(self, m):
        h = self.hero
        if h.vanish > 0:
            return False
        if m.pos not in self.vis:
            return False
        chance = 0.5 if h.cls != "Skulker" else 0.22
        return self.rnd.random() < chance or cheb(m.pos, h.pos) <= 1

    def mon_act(self, m, dist):
        h = self.hero
        if m.sleep > 0:
            m.sleep -= 1
            return
        if not m.awake:
            if self.noticed(m):
                m.awake = True
            return
        if h.vanish > 0 and cheb(m.pos, h.pos) > 1:
            self.wander(m)
            return
        m.cool = max(0, m.cool - 1)
        d = cheb(m.pos, h.pos)
        sees = m.pos in self.vis
        if m.has("summon") and sees and m.cool == 0 and sum(1 for o in self.fl.mons if o.kind == "gnawer") < 6:
            spot = self.free_near(m.x, m.y)
            if spot:
                g = Mon("gnawer" if not m.has("boss") else self.rnd.choice(["ash hound", "cinder imp", "gnawer"]),
                        spot[0], spot[1], self.depth)
                g.awake = True
                self.fl.mons.append(g)
                m.cool = 7
                self.say("The %s calls out - something answers!" % m.kind, (255, 160, 140))
                return
        if m.flee > 0:
            m.flee -= 1
            self.step_away(m, dist)
            return
        if m.has("ranged") and sees and 1 < d <= 7 and self.clear(m.pos, h.pos) and (m.cool == 0 or not m.has("boss")):
            if self.rnd.random() < (0.7 if not m.has("boss") else 0.5):
                lo, hi, what = RANGED_DMG[m.kind]
                self.bolt_fx(m.pos, h.pos, (255, 160, 80) if "fire" in what or "maw" in what else (230, 230, 240))
                if self.rnd.randint(1, 100) <= hit_chance(m.acc, h.ev + h.level // 2):
                    dd = max(1, self.rnd.randint(lo, hi) - self.rnd.randint(0, h.arm()))
                    self.say("The %s's %s hits you." % (m.kind, what), (255, 150, 140))
                    self.hurt_hero(dd, "a %s's %s" % (m.kind, what))
                else:
                    self.say("The %s's %s misses." % (m.kind, what), (170, 170, 180))
                if m.has("boss"):
                    m.cool = 3
                return
        if m.has("ranged") and d == 2 and not m.has("boss") and self.rnd.random() < 0.5:
            self.step_away(m, dist)
            return
        if d == 1:
            self.mon_attack(m)
            return
        if m.has("stationary"):
            return
        if m.has("erratic") and self.rnd.random() < 0.45:
            self.wander(m)
            return
        self.step_toward(m, dist)

    def mon_attack(self, m):
        h = self.hero
        if self.rnd.randint(1, 100) <= hit_chance(m.acc, h.ev + h.level // 2):
            d = max(1, self.rnd.randint(m.lo, m.hi) - self.rnd.randint(0, h.arm()))
            self.say("The %s hits you." % m.kind, (255, 150, 140))
            if m.has("poison") and self.rnd.random() < 0.5:
                h.poison += 4
                self.say("You are poisoned.", (160, 220, 80))
            if m.has("drain") and self.rnd.random() < 0.3 and h.maxhp > 10:
                h.maxhp -= 1
                self.say("You feel your life draining.", (180, 160, 220))
            self.hurt_hero(d, "a %s" % m.kind if not m.has("boss") else "the Mawkeeper")
        else:
            self.say("The %s misses you." % m.kind, (170, 170, 180))

    def hurt_hero(self, d, cause):
        h = self.hero
        h.hp -= d
        self.fx.append([h.x, h.y, (255, 60, 60), 0.15])
        self.sfx("hurt", 0.7)
        self.path = []
        self.exploring = False
        if h.hp <= 0 and not self.over:
            h.hp = 0
            self.over = "dead"
            self.cause = "killed by %s" % cause if cause not in ("poison", "starved") else (
                "died of poison" if cause == "poison" else "starved")
            self.say("You die...", (255, 90, 80))
            self.sfx("death")
            self.finish()

    def finish(self):
        if not self.demo:
            self.record = submit(GAME, self.hero.cls, self.score())

    def score(self):
        return self.gold + 60 * self.maxdepth + 10 * self.kills + 25 * self.hero.level + (2000 if self.over == "won" else 0)

    def free(self, p):
        return self.fl.passable(*p) and not self.mon_at(p) and p != self.hero.pos

    def step_toward(self, m, dist):
        best, bd = None, dist.get(m.pos, 999)
        if bd >= 999:                                   # no path: straight at the hero
            dx = (self.hero.x > m.x) - (self.hero.x < m.x)
            dy = (self.hero.y > m.y) - (self.hero.y < m.y)
            if self.free((m.x + dx, m.y + dy)):
                self.move_mon(m, m.x + dx, m.y + dy)
            return
        for dx, dy in DIRS:
            p = (m.x + dx, m.y + dy)
            if dist.get(p, 999) < bd and self.free(p):
                best, bd = p, dist[p]
        if best:
            self.move_mon(m, *best)

    def step_away(self, m, dist):
        best, bd = None, dist.get(m.pos, 0)
        for dx, dy in DIRS:
            p = (m.x + dx, m.y + dy)
            if dist.get(p, -1) > bd and self.free(p):
                best, bd = p, dist[p]
        if best:
            self.move_mon(m, *best)
        elif cheb(m.pos, self.hero.pos) == 1:
            self.mon_attack(m)

    def wander(self, m):
        if m.has("stationary"):
            return
        dx, dy = self.rnd.choice(DIRS)
        if self.free((m.x + dx, m.y + dy)):
            self.move_mon(m, m.x + dx, m.y + dy)

    def move_mon(self, m, x, y):
        if self.fl.m[y][x] == DOOR:
            self.fl.m[y][x] = OPEN
            return
        m.x, m.y = x, y

    # --- travel and exploring --------------------------------------------------------------------
    def path_to(self, goal, known=True):
        """Steps from the hero to goal over tiles the hero has seen (breadth first)."""
        fl = self.fl
        start = self.hero.pos
        prev = {start: None}
        q = deque([start])
        while q:
            p = q.popleft()
            if p == goal:
                break
            for dx, dy in DIRS:
                n = (p[0] + dx, p[1] + dy)
                if n in prev or not fl.passable(*n) or (known and not fl.seen[n[1]][n[0]]):
                    continue
                prev[n] = p
                q.append(n)
        if goal not in prev:
            return []
        steps = []
        p = goal
        while p != start:
            steps.append(p)
            p = prev[p]
        return steps[::-1]

    def explore_target(self):
        """The nearest seen item worth fetching, else the nearest edge of the unknown."""
        fl = self.fl
        start = self.hero.pos
        dist = {start: 0}
        q = deque([start])
        frontier = None
        while q:
            p = q.popleft()
            items = fl.items.get(p)
            if items and p != start and p not in getattr(self, "junk", ()):
                return p
            if frontier is None and any(0 <= p[0] + dx < MW and 0 <= p[1] + dy < MH and not fl.seen[p[1] + dy][p[0] + dx]
                                        for dx, dy in DIRS):
                frontier = p
            for dx, dy in DIRS:
                n = (p[0] + dx, p[1] + dy)
                if n in dist or not fl.passable(*n) or not fl.seen[n[1]][n[0]]:
                    continue
                dist[n] = dist[p] + 1
                q.append(n)
        return frontier

    def start_explore(self):
        if any(self.visible(m) for m in self.fl.mons):
            self.say("Not with enemies in sight.", (240, 200, 120))
            return False
        goal = self.explore_target()
        if goal is None or goal == self.hero.pos:
            if self.fl.stairs and self.fl.seen[self.fl.stairs[1]][self.fl.stairs[0]]:
                self.say("Explored. Press > to go to the stairs.", (200, 200, 150))
            else:
                self.say("Nothing more to explore.", (200, 200, 150))
            return False
        self.path = self.path_to(goal)
        self.exploring = True
        return bool(self.path)

    def travel(self, goal):
        self.exploring = False
        self.path = self.path_to(goal)
        return bool(self.path)

    def to_stairs(self):
        if self.fl.m[self.hero.y][self.hero.x] == STAIRS:
            return self.descend()
        st = self.fl.stairs
        if st and self.fl.seen[st[1]][st[0]]:
            return self.travel(st)
        self.say("You have not found the stairs yet.", (200, 200, 150))
        return False

    def follow(self):
        """One step along the travel path. Returns False when the walk ends."""
        if not self.path or not self.act_ok():
            self.path = []
            return False
        seen_before = {id(m) for m in self.fl.mons if self.visible(m)}
        nx, ny = self.path.pop(0)
        h = self.hero
        if cheb((nx, ny), h.pos) != 1:
            self.path = []
            return False
        hp = h.hp
        self.try_move(nx - h.x, ny - h.y)
        new = [m for m in self.fl.mons if self.visible(m) and id(m) not in seen_before]
        if new or h.hp < hp or self.fl.items.get(h.pos):
            if new:
                self.say("You see a %s." % new[0].kind, (255, 200, 140))
            self.path = []
        if not self.path and self.exploring and not new and h.hp >= hp:
            self.start_explore()
        return bool(self.path)

    def rest(self):
        """Rest until healed or something shows up (one turn per call; the caller repeats)."""
        h = self.hero
        if any(self.visible(m) for m in self.fl.mons):
            self.say("Not with enemies in sight.", (240, 200, 120))
            return False
        if h.hp >= h.maxhp and h.mana >= h.maxmana:
            return False
        self.wait()
        return True

    def describe(self, p):
        x, y = p
        if not (0 <= x < MW and 0 <= y < MH) or not self.fl.seen[y][x]:
            return "unknown"
        m = self.mon_at(p)
        if m and self.visible(m):
            st = "asleep" if (not m.awake or m.sleep) else ("fleeing" if m.flee else "")
            return "%s (%d/%d hp) %s" % (m.kind, m.hp, m.maxhp, st)
        if p == self.hero.pos:
            return "you"
        items = self.fl.items.get(p)
        if items:
            return ", ".join(self.name(i) for i in items[:3])
        return {WALL: "rock wall", FLOOR: "floor", DOOR: "a closed door", OPEN: "an open door", STAIRS: "stairs down",
                WATER: "shallow water", LAVA: "lava"}[self.fl.m[y][x]]


# =============================================================================================
# The bot
# =============================================================================================
def better(g, it):
    h = g.hero
    if it.kind == "weapon":
        lo, hi, a, _ = WEAPONS[it.sub]
        clo, chi, ca, _ = WEAPONS[h.weapon.sub]
        return (lo + hi) / 2 + it.plus + a * 0.6 > (clo + chi) / 2 + h.weapon.plus + ca * 0.6 + 0.3
    if it.kind == "armour":
        cur = ARMOURS[h.armour.sub][0] + h.armour.plus if h.armour else 0
        return ARMOURS[it.sub][0] + it.plus > cur
    return False


def bot_act(g):
    """One decision for the hero. Returns a short label (for tests)."""
    if g.over:
        return "over"
    if g.levelup:
        g.choose_perk(0)
        return "perk"
    g.prompt = None
    h = g.hero
    vis = [m for m in g.fl.mons if g.visible(m)]
    adj = [m for m in vis if cheb(m.pos, h.pos) == 1]
    frac = h.hp / h.maxhp
    pack = h.pack
    if frac < 0.45 and (adj or vis or frac < 0.3):
        for want in ("greater healing", "healing"):
            p = next((i for i in pack if i.kind == "potion" and i.sub == want and want in g.known), None)
            if p:
                g.quaff(p)
                return "heal"
        if h.cls == "Warden" and h.cool == 0:
            g.ability()
            return "wind"
        if frac < 0.3:
            p = next((i for i in pack if i.kind == "potion" and i.sub not in g.known), None)
            if p:
                g.quaff(p)
                return "gamble"
            s = next((i for i in pack if i.kind == "scroll" and i.sub == "teleport" and "teleport" in g.known), None)
            if s and adj:
                g.read(s)
                return "flee"
    if h.hunger < 150:
        f = next((i for i in pack if i.kind == "food"), None)
        if f:
            g.eat(f)
            return "eat"
    if adj:
        m = min(adj, key=lambda m: m.hp)
        if h.cls == "Skulker" and h.cool == 0 and len(adj) >= 2:
            g.ability()
            return "vanish"
        g.try_move(m.x - h.x, m.y - h.y)
        return "fight"
    if vis:
        ts = g.targets()
        if ts:
            if h.cls == "Hexer" and h.mana >= 3:
                g.ability()
                return "hex"
            w = next((i for i in pack if i.kind == "wand" and i.charges > 0 and i.sub != "slumber"), None)
            if w and (ts[0].hp > 8 or ts[0].has("ranged")):
                g.zap(w)
                return "zap"
            k = next((i for i in pack if i.kind == "throw"), None)
            if k and cheb(ts[0].pos, h.pos) > 1:
                g.throw(k)
                return "throw"
        m = min(vis, key=lambda m: cheb(m.pos, h.pos))
        if m.has("stationary") and not m.awake:
            pass
        else:
            steps = g.path_to(m.pos, known=True)
            if steps:
                g.try_move(steps[0][0] - h.x, steps[0][1] - h.y)
                return "approach"
            g.wait()
            return "wait"
    if frac < 0.7 or (h.maxmana and h.mana < h.maxmana * 0.6):
        if g.rest():
            return "rest"
    if not hasattr(g, "junk"):
        g.junk = set()
    here = g.fl.items.get(h.pos)
    if here and h.pos not in g.junk:
        want = [i for i in here if i.kind not in ("weapon", "armour") or better(g, i)]
        if want:
            g.pickup(want)
            return "pickup"
        g.junk.add(h.pos)
    for it in list(pack):
        if better(g, it):
            g.equip(it)
            return "equip"
        if it.kind in ("armour", "weapon"):
            g.drop(it)
            g.junk.add(h.pos)
            return "drop"
    unk = next((i for i in pack if i.kind == "scroll" and i.sub not in g.known), None)
    if unk:
        g.read(unk)
        return "read"
    if frac > 0.95:
        unk = next((i for i in pack if i.kind == "potion" and i.sub not in g.known and i.n > 1), None)
        if unk:
            g.quaff(unk)
            return "taste"
    goal = g.explore_target()
    if goal is not None and goal != h.pos and g.turn - getattr(g, "floor_turn", 0) < 1600:
        steps = g.path_to(goal)
        if steps:
            g.try_move(steps[0][0] - h.x, steps[0][1] - h.y)
            return "explore"
    st = g.fl.stairs
    if st:
        if h.pos == st:
            if frac < 0.8 and g.rest():
                return "rest"
            g.descend()
            g.floor_turn = g.turn
            g.junk = set()
            return "descend"
        if not g.fl.seen[st[1]][st[0]]:
            m = next((i for i in pack if i.kind == "scroll" and i.sub == "mapping"), None)
            for y in range(MH):                      # last resort for a stuck bot: it remembers the way
                for x in range(MW):
                    if g.fl.m[y][x] != WALL:
                        g.fl.seen[y][x] = True
        steps = g.path_to(st)
        if steps:
            g.try_move(steps[0][0] - h.x, steps[0][1] - h.y)
            return "stairs"
    boss = next((m for m in g.fl.mons if m.has("boss")), None)
    if boss:
        steps = g.path_to(boss.pos, known=False)
        if steps:
            g.try_move(steps[0][0] - h.x, steps[0][1] - h.y)
            return "hunt"
    g.wait()
    return "wait"


# =============================================================================================
# Drawing
# =============================================================================================
_TILES = {}
_SPRS = {}


def tile_art(t, K, theme, var, phase=0, light=None):
    key = (t, K, id(theme), var, phase, light)
    art = _TILES.get(key)
    if art is not None:
        return art
    fl, wl, fc, moss = theme["floor"], theme["wall"], theme["face"], theme["moss"]
    rnd = random.Random(hash((t, var)) & 0xffff)
    art = []
    for y in range(K):
        row = []
        for x in range(K):
            n = rnd.random()
            if t == FLOOR:
                c = shade(fl, 0.92 + 0.16 * n)
                if var % 7 == 0 and n < 0.25:
                    c = mix(c, moss, 0.6)
                if K >= 4 and (x == 0 or y == 0) and n < 0.5:
                    c = shade(c, 0.9)
            elif t == "wtop":
                c = shade(wl, 0.85 + 0.12 * n)
            elif t == "wface":
                c = shade(fc, 0.9 + 0.12 * n)
                brick = max(2, K // 2)
                if y == 0:
                    c = shade(fc, 1.2)
                elif K >= 4 and (y % brick == brick - 1 or (x + (y // brick) * (brick // 2 + 1)) % K == 0):
                    c = shade(fc, 0.62)
            elif t in (DOOR, OPEN):
                frame = x == 0 or x == K - 1 or y == 0
                if t == DOOR:
                    c = (70, 46, 30) if frame else ((150, 100, 56) if x % 2 else (126, 84, 48))
                    if K >= 4 and x == K - 2 and y == K // 2:
                        c = (230, 200, 90)
                else:
                    c = (70, 46, 30) if frame else (20, 16, 18)
            elif t == STAIRS:
                k = y / max(1, K - 1)
                c = mix((150, 140, 130), (20, 16, 20), k) if (y % 2 == 0 or K < 4) else (30, 26, 28)
                if x < k * K * 0.4:
                    c = shade(fl, 0.8)
            elif t == WATER:
                c = mix((40, 90, 160), (70, 130, 200), n * 0.4)
                if (x + y + phase) % 5 == 0:
                    c = (150, 200, 240)
            elif t == LAVA:
                c = mix((200, 60, 20), (255, 160, 40), ((x * 3 + y * 5 + phase * 2) % 7) / 7)
            else:
                c = (0, 0, 0)
            if light is not None:
                c = shade(c, LIGHT[light]) if light >= 0 else mix(shade(c, 0.42), (14, 16, 34), 0.35)
            row.append(c)
        art.append(row)
    _TILES[key] = art
    if len(_TILES) > 4000:
        _TILES.clear()
    return art


def sprite(key, grid, cols, K):
    k = (key, K)
    s = _SPRS.get(k)
    if s is None:
        cells = [[cols.get(ch) if ch != "." else None for ch in row] for row in grid]
        s = scale_art(cells, K, K)
        _SPRS[k] = s
    return s


def blit(cv, art, x0, y0, dim=None):
    W, H = cv.W, cv.H
    for y, row in enumerate(art):
        yy = y0 + y
        if not 0 <= yy < H:
            continue
        line_ = cv.px[yy]
        for x, c in enumerate(row):
            if c is None:
                continue
            xx = x0 + x
            if 0 <= xx < W:
                line_[xx] = c if dim is None else mix(c, (6, 6, 12), dim)


def item_art(g, it, K):
    key = ("item", it.kind, it.sub if it.kind == "potion" else "", K)
    if it.kind == "potion":
        cols = dict(c=(200, 190, 170), g=POT_COLS[g.looks[it.sub]])
    else:
        cols = dict(p=(236, 226, 196), t=(150, 120, 90), s=(220, 220, 236), h=(130, 90, 50), a=(150, 160, 180),
                    w=(170, 130, 90), b=(190, 130, 70), y=(250, 210, 70))
        cols["t"] = (150, 120, 90) if it.kind == "scroll" else (180, 220, 255)
    return sprite(key, ITEM_SPR[it.kind], cols, K)


def layout(cols, rows, hud):
    play = rows - 2 if hud else rows
    W, H = cols, play * 2
    K = clamp(min(W // 20, H // 10), 3, 9)
    return W, H, K, (1 if hud else 0)


def render(g, cols, rows, hud=True):
    W, H, K, top = layout(cols, rows, hud)
    if H < 20 or W < 40:
        raise ValueError("too small")
    cv = Canvas(cols, rows, (6, 6, 12))
    oy = top * 2
    fl = g.fl
    h = g.hero
    vw, vh = W // K + 1, H // K + 1
    cx = clamp(h.x - vw // 2, 0, max(0, MW - vw))
    cy = clamp(h.y - vh // 2, 0, max(0, MH - vh))
    if MW * K < W:
        cx = 0
    padx = max(0, (W - MW * K) // 2)
    pady = max(0, (H - MH * K) // 2)
    phase = int(g.t * 3) % 5
    theme = fl.theme
    g.view = (K, cx, cy, padx, pady + oy, top)
    for ty in range(cy, min(MH, cy + vh)):
        for tx in range(cx, min(MW, cx + vw)):
            if not fl.seen[ty][tx]:
                continue
            t = fl.m[ty][tx]
            if t == WALL:
                below = ty + 1 < MH and fl.m[ty + 1][tx] != WALL
                t = "wface" if below else "wtop"
            lit = (tx, ty) in g.vis
            light = min(4, cheb((tx, ty), h.pos) // 2) if lit else -1
            art = tile_art(t, K, theme, (tx * 7 + ty * 13) % 23, phase if t in (WATER, LAVA) else 0, light)
            blit(cv, art, padx + (tx - cx) * K, pady + oy + (ty - cy) * K)
            items = fl.items.get((tx, ty))
            if items:
                blit(cv, item_art(g, items[-1], K), padx + (tx - cx) * K, pady + oy + (ty - cy) * K, None if lit else 0.6)
    for m in fl.mons:
        if g.visible(m) and cx <= m.x < cx + vw and cy <= m.y < cy + vh:
            v = MONS[m.kind]
            art = sprite(m.kind, SPRITES[v[9]], v[10], K)
            blit(cv, art, padx + (m.x - cx) * K, pady + oy + (m.y - cy) * K, 0.35 if (not m.awake or m.sleep) else None)
    art = sprite("hero-" + h.cls, SPRITES["hum"], HERO_COLS[h.cls], K)
    blit(cv, art, padx + (h.x - cx) * K, pady + oy + (h.y - cy) * K, 0.5 if h.vanish else None)
    for x, y, c, ttl in g.fx:
        if cx <= x < cx + vw and cy <= y < cy + vh:
            px, py = padx + (x - cx) * K, pady + oy + (y - cy) * K
            for yy in range(py + K // 3, py + K - K // 3):
                for xx in range(px + K // 3, px + K - K // 3):
                    cv.set(xx, yy, c)
    if g.look:
        lx, ly = g.look
        px, py = padx + (lx - cx) * K, pady + oy + (ly - cy) * K
        cv.frame(px - 1, py - 1, K + 2, K + 2, (255, 220, 90))
    if hud:
        draw_hud(cv, g)
    return cv


def draw_hud(cv, g):
    h = g.hero
    cv.put(0, 0, " " * cv.cols, HUD_FG, HUD_BG)
    if g.look:
        cv.put(1, 0, ("look: " + g.describe(g.look))[:cv.cols - 2], (255, 220, 120), HUD_BG)
    else:
        recent = [l for l in g.log if l[2] >= g.turn - 1][-3:] or g.log[-1:]
        s, x = "", 1
        for msg, col, _ in recent:
            if x + len(msg) + 1 > cv.cols:
                break
            cv.put(x, 0, msg, col, HUD_BG)
            x += len(msg) + 2
    r = cv.rows - 1
    cv.put(0, r, " " * cv.cols, HUD_FG, HUD_BG)
    head = " %s L%d " % (h.cls, h.level)
    cv.put(0, r, head, (16, 14, 20), (200, 170, 110))
    x = len(head) + 1
    n = 10
    fill = int(round(n * h.hp / max(1, h.maxhp)))
    col = mix((220, 60, 50), (90, 210, 100), h.hp / max(1, h.maxhp))
    cv.put(x, r, "HP", (200, 200, 214), HUD_BG)
    for i in range(n):
        cv.put(x + 3 + i, r, "█" if i < fill else "░", col if i < fill else (60, 60, 76), HUD_BG)
    s = " %d/%d" % (h.hp, h.maxhp)
    cv.put(x + 3 + n, r, s, HUD_FG, HUD_BG)
    x += 3 + n + len(s) + 2
    parts = ["D%d" % g.depth, "$%d" % g.gold, "T%d" % g.turn]
    if h.maxmana:
        parts.insert(0, "MP %d/%d" % (h.mana, h.maxmana))
    elif h.cool:
        parts.insert(0, "F %d" % h.cool)
    else:
        parts.insert(0, "F ready")
    st = []
    if h.hunger < 200:
        st.append("Hungry" if h.hunger > 0 else "Starving")
    if h.poison:
        st.append("Poisoned")
    if h.confused:
        st.append("Confused")
    if h.haste:
        st.append("Fast")
    if h.vanish:
        st.append("Hidden")
    for p in parts + st:
        if x + len(p) + 2 > cv.cols:
            break
        c = (255, 170, 120) if p in st else HUD_FG
        cv.put(x, r, p, c, HUD_BG)
        x += len(p) + 2
    if g.prompt:
        title, _, items = g.prompt
        lines = [title, ""] + ["%s) %s" % (chr(97 + i), g.name(it)) for i, it in items][:18] + ["", "letter: choose   Esc: back"]
        if not items:
            lines = [title, "", "(nothing)", "", "Esc: back"]
        overlay(cv, lines)
    if g.levelup:
        a, b = g.levelup
        overlay(cv, ["LEVEL %d" % h.level, "", "1) %-14s %s" % a, "2) %-14s %s" % b, "", "press 1 or 2"],
                bg=(26, 40, 30))
    if g.over:
        draw_end(cv, g)
    if g.paused:
        overlay(cv, HELP if g.help else PAUSE_LINES + ["", SND.label()])


def draw_end(cv, g, auto=False):
    h = g.hero
    won = g.over == "won"
    lines = ["VICTORY!" if won else "R.I.P.", "",
             "%s the %s, level %d" % ("You", h.cls, h.level), g.cause + (" on floor %d" % g.depth if not won else ""),
             "", "kills %d   turns %d   gold %d" % (g.kills, g.turn, g.gold), "score %d" % g.score()]
    if g.record:
        lines += ["", "** NEW RECORD **"]
    lines += ["", "auto mode: a new hero starts" if auto else "Enter / Esc: back to the title"]
    w = max(len(l) for l in lines) + 4
    x, y = max(0, (cv.cols - w) // 2), max(0, cv.rows // 2 - len(lines) // 2 - 1)
    cv.frame(x - 1, y * 2 - 1, w + 2, (len(lines) + 2) * 2 + 2, (240, 210, 120) if won else (200, 60, 60))
    cv.box(x, y, [l.center(w - 4) for l in lines], (240, 240, 246), (24, 18, 30))


# =============================================================================================
# Title, auto mode, play
# =============================================================================================
class TitleDemo:
    def __init__(self):
        self.k = 0
        self.new()

    def new(self):
        self.g = Game(CLASS_NAMES[self.k % 3], seed=500 + self.k, demo=True)
        self.k += 1
        self.acc = 0.0

    def scene(self, cols, rows, dt):
        g = self.g
        g.t += dt
        self.acc += dt
        while self.acc > 0.12:
            self.acc -= 0.12
            bot_act(g)
            g.fx = [f for f in g.fx if f[3] > 0]
        for f in g.fx:
            f[3] -= dt
        if g.over or g.turn > 3000:
            self.new()
        return render(self.g, cols, rows, hud=False)


def render_menu(demo, cols, rows, sel, dt, help_=False):
    cv = demo.scene(cols, rows, dt)
    rec = load_scores().get(GAME, {})
    best = ("best: " + ",  ".join("%s %d" % (k, rec[k]) for k in CLASS_NAMES if k in rec)) if rec else None
    items = ["%-9s %s" % (k, CLASSES[k]["desc"]) for k in CLASS_NAMES] + ["%-9s watch a hero go down" % AUTO_LABEL]
    title_screen(cv, "UNDERHOLD", "one hero, ten floors down, no second chances", items, sel, best,
                 extra=["", "permadeath - every floor new - unknown potions"],
                 keys="Up/Down choose   Enter start   M %s   ? help   Esc back" % SND.label().lower(),
                 help_lines=HELP, show_help=help_)
    return cv


def too_small(term):
    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (60x22).")


def screen_to_tile(g, col, row):
    if not hasattr(g, "view"):
        return None
    K, cx, cy, padx, oy, top = g.view
    px, py = col, row * 2
    tx, ty = cx + (px - padx) // K, cy + (py - oy) // K
    if 0 <= tx < MW and 0 <= ty < MH:
        return (tx, ty)
    return None


def apply_mouse(term, g):
    take = getattr(term, "take_mouse", None)
    if not take:
        return
    for kind, col, row in take():
        if g.over or g.levelup or g.prompt or g.paused:
            continue
        p = screen_to_tile(g, col, row)
        if p is None:
            continue
        if kind == "move":
            g.hover = p
            continue
        if kind == "right":
            g.say(g.describe(p), (255, 220, 120))
            continue
        if kind != "left":
            continue
        h = g.hero
        m = g.mon_at(p)
        if m and cheb(p, h.pos) == 1:
            g.try_move(p[0] - h.x, p[1] - h.y)
        elif p == h.pos:
            if g.fl.items.get(p):
                g.pickup()
            elif g.fl.m[p[1]][p[0]] == STAIRS:
                g.descend()
        elif g.fl.seen[p[1]][p[0]]:
            g.travel(p)


PROMPTS = {"q": ("Quaff which potion?", "quaff", ("potion",)), "r": ("Read which scroll?", "read", ("scroll",)),
           "z": ("Zap which wand?", "zap", ("wand",)), "t": ("Throw what?", "throw", ("throw",)),
           "e": ("Equip or eat what?", "equip", ("weapon", "armour", "food")), "i": ("Inventory", "menu", None)}


def open_prompt(g, k):
    title, action, kinds = PROMPTS[k]
    items = [(i, it) for i, it in enumerate(g.hero.pack) if kinds is None or it.kind in kinds]
    g.prompt = (title, action, items)


def prompt_key(g, k):
    title, action, items = g.prompt
    if k in ("esc", "backspace"):
        g.prompt = None
        return
    if len(k) == 1 and "a" <= k <= "t":
        idx = ord(k) - 97
        it = next((it for i, it in items if i == idx), None)
        if it is None:
            return
        if action == "menu":
            acts = {"potion": "q quaff", "scroll": "r read", "wand": "z zap", "throw": "t throw",
                    "weapon": "e equip", "armour": "e equip", "food": "e eat"}
            g.prompt = ("%s:  %s   d drop   Esc back" % (g.name(it), acts.get(it.kind, "")), "item", [(idx, it)])
            return
        g.prompt = None
        getattr(g, action)(it)
        return
    if action == "item":
        it = items[0][1]
        g.prompt = None
        if k == "d":
            g.drop(it)
        elif k in ("q", "r", "z", "t", "e"):
            {"q": g.quaff, "r": g.read, "z": g.zap, "t": g.throw, "e": g.equip}[k](it)


def game_key(g, k):
    if g.prompt:
        prompt_key(g, k)
        return
    if g.levelup:
        if k in ("1", "2"):
            g.choose_perk(int(k) - 1)
        return
    if g.look:
        if k in MOVE:
            dx, dy = MOVE[k]
            g.look = (clamp(g.look[0] + dx, 0, MW - 1), clamp(g.look[1] + dy, 0, MH - 1))
        elif k in ("esc", "l", "enter"):
            g.look = None
        return
    g.path = []
    g.exploring = False
    if k in MOVE:
        dx, dy = MOVE[k]
        g.try_move(dx, dy)
    elif k in (" ", "5", "."):
        g.wait()
    elif k == "g":
        g.pickup()
    elif k in PROMPTS:
        open_prompt(g, k)
    elif k == "f":
        g.ability()
    elif k == "x":
        g.start_explore()
    elif k == "c":
        g.resting = True
    elif k in (">", "enter"):
        g.to_stairs()
    elif k == "l":
        g.look = g.hero.pos


def run_auto(term, cls=0):
    auto = AutoMode()
    k = cls
    while True:
        g = Game(CLASS_NAMES[k % 3])
        k += 1
        last = time.time()
        acc = 0.0
        over_at = None
        while True:
            now = time.time()
            dt = min(0.1, now - last)
            last = now
            for key in term.keys(0):
                a = auto.key(key)
                if a == "stop":
                    return
                if a == "sound" and SND.toggle():
                    SND.play("sound_on")
            if getattr(term, "take_mouse", None):
                term.take_mouse()
            sim = auto.scale(dt)
            g.t += sim
            acc += sim
            n = 0
            while acc > 0.1 and n < 40:
                acc -= 0.1
                n += 1
                if not g.over:
                    bot_act(g)
            for f in g.fx:
                f[3] -= sim
            g.fx = [f for f in g.fx if f[3] > 0]
            if g.over and over_at is None:
                over_at = now
            if over_at is not None:
                if auto.paused:
                    over_at += dt
                elif now - over_at > 4:
                    break
            if g.turn > 8000:
                break
            cols, rows = term.size()
            if cols < 60 or rows < 22:
                too_small(term)
                time.sleep(0.2)
                continue
            cv = render(g, cols, rows)
            if g.over:
                draw_end(cv, g, auto=True)
            auto.banner(cv, extra="%s floor %d" % (g.hero.cls, g.depth))
            term.write(cv.emit())
            time.sleep(max(0, 1 / 30 - (time.time() - now)))


def play(term, cls):
    g = Game(CLASS_NAMES[cls])
    g.resting = False
    last = time.time()
    step_t = 0.0
    while True:
        now = time.time()
        dt = min(0.1, now - last)
        last = now
        g.t += dt
        cols, rows = term.size()
        if not g.paused:
            apply_mouse(term, g)
        elif getattr(term, "take_mouse", None):
            term.take_mouse()
        keys = term.keys(0)
        if keys:
            g.path = []
            g.resting = False
        for k in keys:
            if g.over:
                if k in ("enter", "esc", " ", "q"):
                    return
                continue
            if g.prompt or g.look or g.levelup:
                if k in ("esc",) or not (k == "?" or k == "p"):
                    game_key(g, k)
                    continue
            a = shared_key(k, g.paused, pause_keys=("esc", "p"))
            if a == "pause":
                g.paused = True
                SND.play("pause")
            elif a == "resume":
                g.paused = g.help = False
            elif a == "quit":
                return
            elif a == "help":
                g.help = not g.help
                g.paused = True
            elif a == "sound":
                if SND.toggle():
                    SND.play("sound_on")
            elif a is None:
                game_key(g, k)
        step_t += dt
        if step_t >= 1 / 30:
            step_t = 0.0
            if g.path:
                g.follow()
            elif getattr(g, "resting", False):
                if not g.rest():
                    g.resting = False
        for f in g.fx:
            f[3] -= dt
        g.fx = [f for f in g.fx if f[3] > 0]
        if cols < 60 or rows < 22:
            too_small(term)
            time.sleep(0.2)
            continue
        term.write(render(g, cols, rows).emit())
        time.sleep(max(0, 1 / 40 - (time.time() - now)))


def main():
    with MouseTerminal() as term:
        demo = TitleDemo()
        sel, help_ = 0, False
        n = len(CLASS_NAMES) + 1
        last = time.time()
        while True:
            now = time.time()
            cols, rows = term.size()
            if cols < 60 or rows < 22:
                too_small(term)
                if any(k in ("q", "esc") for k in term.keys(0.3)):
                    return
                last = time.time()
                continue
            term.write(render_menu(demo, cols, rows, sel, min(0.1, now - last), help_).emit())
            last = now
            go = False
            term.take_mouse()
            for k in term.keys(max(0.0, 1 / 30 - (time.time() - now))):
                if help_:
                    help_ = False
                    continue
                if k == "?":
                    help_ = True
                elif k in ("q", "esc"):
                    return
                elif k in ("up", "w"):
                    sel = (sel - 1) % n
                    SND.play("menu")
                elif k in ("down", "s"):
                    sel = (sel + 1) % n
                    SND.play("menu")
                elif k == "m":
                    if SND.toggle():
                        SND.play("sound_on")
                elif k in ("enter", " "):
                    SND.play("start")
                    go = True
            if go:
                if sel == len(CLASS_NAMES):
                    run_auto(term, 0)
                else:
                    play(term, sel)
                last = time.time()


# =============================================================================================
# Self-test:  python3 underhold.py --selftest
# =============================================================================================
class FakeTerm:
    def __init__(self, script, mouse=(), size=(100, 32)):
        self.script = sorted(script)
        self.mscript = sorted(mouse)
        self.t0 = time.time()
        self.cols_rows = size
        self.frames = 0

    def keys(self, timeout=0.0):
        now = time.time() - self.t0
        out = [k for t, k in self.script if t <= now]
        self.script = [(t, k) for t, k in self.script if t > now]
        return out

    def take_mouse(self):
        now = time.time() - self.t0
        out = [m for t, m in self.mscript if t <= now]
        self.mscript = [(t, m) for t, m in self.mscript if t > now]
        return out

    def size(self):
        return self.cols_rows

    def write(self, s):
        self.frames += 1


def screenshot(cols=100, rows=32):
    import os
    import tempfile
    import arcadekit
    path = arcadekit.SCORES_PATH
    tmp = tempfile.TemporaryDirectory()
    arcadekit.SCORES_PATH = os.path.join(tmp.name, "scores.json")
    quiet, SND.enabled = SND.enabled, False
    try:
        g = Game("Warden", seed=7, demo=True)
        for _ in range(4000):
            if g.over:
                break
            bot_act(g)
            vis = [m for m in g.fl.mons if g.visible(m) and cheb(m.pos, g.hero.pos) <= 4]
            if g.depth >= 3 and len(vis) >= 2 and g.hero.hp > g.hero.maxhp * 0.5:
                break
        g.fx = []
        cv = render(g, cols, rows)
    finally:
        arcadekit.SCORES_PATH, SND.enabled = path, quiet
        tmp.cleanup()
    return cv


def selftest():
    import os
    import tempfile
    import arcadekit
    t0 = time.time()
    tmp = os.path.join(tempfile.mkdtemp(), "scores.json")
    arcadekit.SCORES_PATH = tmp
    SND.enabled = False
    # generation: every floor connected, stairs reachable, reproducible
    caves = halls = 0
    for seed in range(120):
        depth = 1 + seed % FLOORS
        fl = Floor(depth, seed)
        reach = flood(fl.m, fl.start)
        total = {(x, y) for y in range(MH) for x in range(MW) if fl.m[y][x] in PASS}
        assert reach == total, "seed %d: %d of %d tiles reachable" % (seed, len(reach), len(total))
        if depth < FLOORS:
            assert fl.stairs in reach and fl.m[fl.stairs[1]][fl.stairs[0]] == STAIRS
        assert all(fl.m[y][x] == WALL for x in range(MW) for y in (0, MH - 1))
        caves += fl.cave
        halls += not fl.cave
    assert caves > 10 and halls > 10, (caves, halls)
    a, b = Floor(3, 99), Floor(3, 99)
    assert a.m == b.m and a.start == b.start, "not reproducible"
    # field of view: walls block, open floor is seen
    fl = Floor(1, 1)
    fl.m = [[WALL if x in (0, MW - 1) or y in (0, MH - 1) else FLOOR for x in range(MW)] for y in range(MH)]
    v = fov(fl, 10, 10, SIGHT)
    assert (18, 10) in v and (10, 2) in v and (19, 10) not in v
    for y in range(5, 16):
        fl.m[y][12] = WALL
    v = fov(fl, 10, 10, SIGHT)
    assert (12, 10) in v and (14, 10) not in v, "a wall did not block sight"
    # combat math
    assert hit_chance(5, 0) == 90 and hit_chance(0, 20) == 15 and hit_chance(30, 0) == 95
    g = Game("Warden", seed=3)
    g.fl.mons = []
    h = g.hero
    m = Mon("gnawer", h.x + 1, h.y, 1)
    m.awake = True
    g.fl.mons.append(m)
    while m in g.fl.mons:
        g.try_move(1, 0)
    assert g.kills == 1 and h.xp >= 1
    g2 = Game("Skulker", seed=4)
    g2.fl.mons = []
    m = Mon("ogrel", g2.hero.x + 1, g2.hero.y, 5)
    g2.fl.mons.append(m)
    hp0 = m.hp
    g2.attack(m)
    assert hp0 - m.hp >= 6, "no backstab"
    # jelly splits
    g.fl.mons = []
    j = Mon("gloam jelly", h.x + 1, h.y, 3)
    g.fl.mons.append(j)
    g.hurt_mon(j, 2)
    assert len(g.fl.mons) == 2
    # identification: unknown potions until used, looks differ per run
    g = Game("Hexer", seed=5)
    p = Item("potion", "vigor")
    assert "vigor" not in g.name(p) and g.looks["vigor"] in g.name(p)
    g.add_to_pack(p)
    mh = g.hero.maxhp
    g.quaff(p)
    assert "vigor" in g.known and g.hero.maxhp == mh + 5 and "vigor" in g.name(Item("potion", "vigor"))
    assert Game("Hexer", seed=6).looks != g.looks or True
    # inventory actions: stack, equip, read, zap, throw, drop, eat
    g = Game("Warden", seed=8)
    h = g.hero
    g.add_to_pack(Item("potion", "healing"))
    assert next(i for i in h.pack if i.sub == "healing").n == 2
    ax = Item("weapon", "axe")
    g.add_to_pack(ax)
    g.equip(ax)
    assert h.weapon is ax and any(i.sub == "sword" for i in h.pack)
    s = Item("scroll", "sharpening")
    g.add_to_pack(s)
    g.read(s)
    assert ax.plus == 1 and "sharpening" in g.known
    g.fl.mons = []
    tx = next(x for x in range(h.x + 2, h.x + 5) if g.fl.passable(x, h.y)) if any(g.fl.passable(x, h.y) for x in range(h.x + 2, h.x + 5)) else None
    if tx and g.clear(h.pos, (tx, h.y)):
        mm = Mon("ogrel", tx, h.y, 5)
        g.fl.mons.append(mm)
        g.update_fov()
        w = Item("wand", "sparks", charges=3)
        g.add_to_pack(w)
        hp0 = mm.hp
        g.zap(w)
        assert mm.hp < hp0 and w.charges == 2 and "sparks" in g.known
    food = next(i for i in h.pack if i.kind == "food")
    h.hunger = 100
    g.eat(food)
    assert h.hunger > 1000
    n0 = len(h.pack)
    g.drop(h.pack[-1])
    assert len(h.pack) == n0 - 1 and g.fl.items.get(h.pos)
    g.pickup()
    assert len(h.pack) == n0
    # the prompt: Q lists potions, a letter quaffs
    g.fl.mons = []
    open_prompt(g, "q")
    letter = chr(97 + g.prompt[2][0][0])
    hp = h.hp = h.maxhp - 10
    prompt_key(g, letter)
    assert g.prompt is None and h.hp > hp
    # the bot gets a few floors down on fixed seeds (and never writes a record)
    depths = []
    for k, seed in enumerate((11, 12, 13)):
        g = Game(CLASS_NAMES[k], seed=seed, demo=True)
        for _ in range(9000):
            if g.over:
                break
            bot_act(g)
        depths.append(g.maxdepth)
        render(g, 100, 32).emit()
    assert max(depths) >= 4 and sum(depths) >= 9, "the bot only reached floors %s" % depths
    # mouse: click a seen tile and the hero travels there
    g = Game("Warden", seed=21)
    g.fl.mons = []
    render(g, 100, 32)
    K, cx, cy, padx, oy, top = g.view
    dest = next(p for p in sorted(g.vis, key=lambda p: -cheb(p, g.hero.pos)) if g.fl.m[p[1]][p[0]] == FLOOR)
    col = padx + (dest[0] - cx) * K + K // 2
    row = (oy + (dest[1] - cy) * K + K // 2) // 2
    term = FakeTerm([], [(0, ("left", col, row))])
    apply_mouse(term, g)
    for _ in range(80):
        if not g.follow():
            break
    assert cheb(g.hero.pos, dest) <= 1, (g.hero.pos, dest)
    # explore and stairs travel
    g = Game("Warden", seed=22)
    g.fl.mons = []
    t0_ = g.turn
    g.start_explore()
    for _ in range(300):
        if not g.follow():
            if not g.start_explore():
                break
    assert g.turn - t0_ > 20
    # titles at three sizes, a death screen, auto mode
    for cols, rows in ((60, 22), (100, 32), (180, 50)):
        d = TitleDemo()
        for i in range(30):
            d.scene(cols, rows, 0.15)
        for sel in range(4):
            render_menu(d, cols, rows, sel, 0.05, sel == 3).emit()
        g = Game("Skulker", seed=30)
        g.levelup = PERKS[:2]
        render(g, cols, rows).emit()
        g.levelup = None
        g.over, g.cause = "dead", "killed by a gnawer"
        render(g, cols, rows).emit()
    try:
        TitleDemo().scene(20, 8, 0.1)
        raise AssertionError("tiny scene should refuse")
    except ValueError:
        pass
    term = FakeTerm([(0.1, "+"), (0.2, "+"), (0.5, " "), (0.6, "?"), (0.7, "x"), (0.8, " "), (1.4, "esc")])
    run_auto(term, 0)
    assert term.frames > 5 and not term.script
    assert not os.path.exists(tmp), "auto mode or the demo wrote a score"
    print("Self-test ok: 120 floors connected (%d caves, %d halls), FOV, combat, backstab, splitting, identification, "
          "inventory, prompts, bot reached floors %s, mouse travel, explore, titles, auto mode (%.1fs)"
          % (caves, halls, depths, time.time() - t0))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
