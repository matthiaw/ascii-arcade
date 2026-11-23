#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""GLIMMER - a will-o'-wisp in a hedge maze at night.

You are Glimmer, a glowing wisp drifting through a night garden's hedge labyrinth. Gather every light mote.
Four sun blossoms per maze turn the shadow spirits pale and fleeing for a while: catch them for 200, 400, 800
and 1600, and their eyes drift back to the burrow in the middle. Murk chases you straight on, Nettle cuts you
off ahead, Hollow flanks you with Murk's help and Sorrel is shy. Eight hand-made mazes, some with one-way hedge
gates, drifting fog or no light but your own.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
"""
import math
import random
import sys
import time
from collections import deque

from arcadekit import (AUTO_LABEL, PAUSE_LINES, AutoMode, Canvas, Terminal, clamp, footer, load_scores, mix, overlay,
                       shade, shared_key, submit, title_screen)
from arcadesound import Sound

GAME = "glimmer"
MW, MH = 27, 21                 # maze size in tiles; every maze is mirrored about the middle column
DIRS = ((0, -1), (-1, 0), (0, 1), (1, 0))      # up, left, down, right (also the tie-break order)
OPP = (2, 3, 0, 1)
KEYDIR = {"up": 0, "w": 0, "left": 1, "a": 1, "down": 2, "s": 2, "right": 3, "d": 3}
GATES = {"^": 0, "<": 1, "v": 2, ">": 3}       # one-way hedge gates: passable only in that direction
MIRROR = {"<": ">", ">": "<"}

# Legend: # hedge   . light mote   o sun blossom   (space) open path   t tunnel (spirits slow down)
#         - burrow door   B burrow   P where Glimmer starts   % where the night treats appear   ^ < v > gates
# Each maze is written as its left half plus the middle column; the right half is the mirror image.
MAZES = (
    ('Moonlit Lawn', (
        '##############',
        '#.....#......#',
        '#o###.#.####.#',
        '#.###.#.####.#',
        '#.............',
        '#.###.#.###.##',
        '#.....#...#...',
        '#####.###.#.##',
        '#####.###     ',
        '#####.### ###-',
        'tttt .    #BBB',
        '#####.### #BBB',
        '#####.### ####',
        '#........    %',
        '#.###.#.####.#',
        '#o..#.#......P',
        '###.#.#.###.##',
        '#...#...#.....',
        '#.###.###.###.',
        '#.............',
        '##############',
    )),
    ('Rose Arbour', (
        '##############',
        '#o.....#......',
        '#.##.#.#.###.#',
        '#.##.#.#.###.#',
        '#.............',
        '#.##.###.#^###',
        '#....#...#..##',
        '####v#.####.##',
        '####.#.##     ',
        '####.#... ###-',
        'tttt.#### #BBB',
        '####.#### #BBB',
        '####.#### ####',
        '#.......     %',
        '#.##.#.###.#.#',
        '#o...#.....#.P',
        '#.##...#.#.###',
        '#.##.#...#.###',
        '#.##.#.#.#.###',
        '#.............',
        '##############',
    )),
    ('Fog Hollow', (
        '##############',
        '#.............',
        '#.##.#.###.##.',
        '#o##.#.###.##.',
        '#....#........',
        '####.#.##.####',
        '####...#....##',
        '#...#.##.##.##',
        '#.#.#.##.     ',
        '#.#...### ###-',
        '#.###.### #BBB',
        '#...#.### #BBB',
        '###.#.### ####',
        'tt..#........%',
        '###.#.####.##.',
        '#o....#......P',
        '#.###.#.####.#',
        '#...#...#....#',
        '#.#.#.#.#.##.#',
        '#............#',
        '##############',
    )),
    ('Lantern Dark', (
        '##############',
        '#...#.........',
        '#o#.#.#.#####.',
        '#.#...#.......',
        '#.#####.###.##',
        '#.......#.....',
        '####.##.#.###.',
        '####.##.#.###.',
        '####.##.#     ',
        '####.##.# ###-',
        'ttt..##.  #BBB',
        '####.##.# #BBB',
        '####.##.# ####',
        '#........    %',
        '#.###.##.#.#.#',
        '#o.##........P',
        '##.##.###.##.#',
        '#............#',
        '#.##.###.##.##',
        '#.............',
        '##############',
    )),
    ('Willow Walk', (
        '##############',
        '#.............',
        '#.###.#####.#.',
        '#o###.#####.#.',
        '#.............',
        '###.#.###.###.',
        'tt..#...#.....',
        '###.#.#.#.####',
        '#...#.#.#     ',
        '#.###.#.# ###-',
        '#.....#.# #BBB',
        '#####.#.# #BBB',
        '#####.#.# ####',
        'tt....#......%',
        '###.#.###.###.',
        '#o..#...#....P',
        '#.#.###.#.##.#',
        '#.#.....#..#.#',
        '#.####.###.#.#',
        '#............#',
        '##############',
    )),
    ('Briar Knot', (
        '##############',
        '#.....#......#',
        '#.###.#.####.#',
        '#o#...#....#.#',
        '#.#.####.#.#..',
        '#.#......#.##.',
        '#.####.#.#....',
        '#......#.#.###',
        '###.##.#.     ',
        '###.##.## ###-',
        'tt..##.## #BBB',
        '###.##.## #BBB',
        '###.##.## ####',
        '#......>.    %',
        '#.####.#.###.#',
        '#o.....#...#.P',
        '#.###.##.#.#.#',
        '#...#....#...#',
        '#.#.#.####.#.#',
        '#............#',
        '##############',
    )),
    ('Starless Court', (
        '##############',
        '#o......#.....',
        '#.#####.#.###.',
        '#.#...#...#...',
        '#.#.#.#####.##',
        '#...#.......##',
        '###.#.#.###.##',
        '#...#.#.###.##',
        '#.###.#.#     ',
        '#.###.#.# ###-',
        'tt###...  #BBB',
        '#.###.#.# #BBB',
        '#.###.#.# ####',
        '#.....#.#    %',
        '#.#.###.#.##.#',
        '#o#.....#.#..P',
        '#.#.###.#.#.##',
        '#...#...#...##',
        '#.###.#.###.##',
        '#.....#.......',
        '##############',
    )),
    ('Midnight Bloom', (
        '##############',
        '#.............',
        '#.#.###.#####.',
        '#o#.###.#####.',
        '#.............',
        '#.#.#.###.##.#',
        '#.#.#...#..#.#',
        '#.#.###.##.#.#',
        '#...#.....    ',
        '###.#.### ###-',
        'tt..#.### #BBB',
        '###.#.### #BBB',
        '#...#.... ####',
        '#.###.#.#    %',
        '#.....#.###.#.',
        '#o###.#...#..P',
        '#.###.###.##.#',
        '#.###...#....#',
        '#.#####.#.##.#',
        '#.............',
        '##############',
    )),
)
STYLE = {   # hedge colour, path colour, a flower / thorn speck in the hedges, features
    "Moonlit Lawn": dict(hedge=(38, 108, 66), ground=(16, 22, 32), speck=None, feat=()),
    "Rose Arbour": dict(hedge=(44, 98, 58), ground=(22, 16, 28), speck=(236, 110, 150), feat=("gates",)),
    "Fog Hollow": dict(hedge=(46, 96, 92), ground=(16, 20, 28), speck=None, feat=("fog",)),
    "Lantern Dark": dict(hedge=(42, 100, 62), ground=(12, 14, 22), speck=(250, 210, 120), feat=("dark",)),
    "Willow Walk": dict(hedge=(70, 120, 58), ground=(14, 22, 28), speck=None, feat=("two tunnels",)),
    "Briar Knot": dict(hedge=(84, 82, 48), ground=(22, 16, 18), speck=(140, 60, 50), feat=("gates", "fog")),
    "Starless Court": dict(hedge=(52, 72, 116), ground=(10, 10, 22), speck=(190, 200, 255), feat=("dark",)),
    "Midnight Bloom": dict(hedge=(36, 98, 92), ground=(12, 14, 30), speck=(220, 230, 255), feat=()),
}
FEAT_TEXT = {"gates": "one-way hedge gates", "fog": "drifting fog", "dark": "no light but your own",
             "two tunnels": "two tunnels"}

SPIRITS = (   # name, colour, scatter corner (a tile outside the maze), what it does
    ("Murk", (164, 96, 248), (MW - 3, -4), "chases you straight on"),
    ("Nettle", (156, 222, 62), (2, -4), "cuts you off ahead"),
    ("Hollow", (82, 152, 242), (MW, MH + 1), "flanks you with Murk"),
    ("Sorrel", (242, 98, 152), (-1, MH + 1), "shy: keeps its distance"),
)
PALE = (196, 210, 240)          # a frightened spirit
PALE2 = (120, 124, 168)         # ... flickering back to its own colour
TREATS = (   # name, points, little drawing as circles: (dx, dy, r in tile units, colour)
    ("dewdrop", 100, ((0, 0.12, 0.34, (150, 210, 255)), (0, -0.18, 0.18, (150, 210, 255)),
                      (-0.1, 0.02, 0.1, (240, 250, 255)))),
    ("moon pear", 300, ((0, 0.14, 0.36, (236, 226, 140)), (0, -0.18, 0.22, (236, 226, 140)),
                        (0.06, -0.42, 0.08, (120, 90, 50)), (-0.12, 0.06, 0.1, (255, 252, 210)))),
    ("star nut", 500, ((0, 0.04, 0.4, (150, 98, 56)), (0, 0.04, 0.2, (255, 214, 90)),
                       (0, 0.04, 0.08, (255, 250, 210)))),
    ("glow berries", 700, ((-0.2, 0.14, 0.24, (200, 70, 170)), (0.2, 0.14, 0.24, (200, 70, 170)),
                           (0, -0.16, 0.24, (230, 96, 200)), (-0.04, -0.22, 0.08, (255, 210, 250)))),
    ("owl feather", 1000, ((-0.24, 0.24, 0.16, (200, 190, 170)), (-0.08, 0.08, 0.2, (226, 216, 196)),
                           (0.1, -0.1, 0.2, (236, 228, 210)), (0.26, -0.26, 0.14, (250, 246, 236)))),
    ("lantern seed", 2000, ((0, 0.06, 0.4, (240, 130, 50)), (0, 0.06, 0.24, (255, 200, 90)),
                            (0, 0.06, 0.1, (255, 250, 220)), (0, -0.42, 0.08, (90, 70, 60)))),
    ("comet plum", 3000, ((0.06, 0.08, 0.36, (120, 70, 200)), (-0.3, -0.24, 0.12, (220, 230, 255)),
                          (-0.14, -0.08, 0.1, (250, 250, 255)))),
    ("silver acorn", 5000, ((0, 0.14, 0.32, (200, 206, 220)), (0, -0.2, 0.3, (130, 120, 110)),
                            (0, -0.42, 0.08, (110, 90, 70)), (-0.1, 0.08, 0.1, (250, 252, 255)))),
)
MOTE = (252, 236, 168)
BLOSSOM = ((255, 214, 90), (255, 150, 60))
WISP_CORE, WISP_RIM = (255, 252, 226), (255, 200, 92)
WARM = (255, 214, 140)
FOG = (124, 128, 156)
HUD_BG = (10, 10, 22)
SCORE_C = (250, 214, 120)
EXTRA_AT = 10000

SND = Sound(GAME, {
    # the motes chime in two alternating notes, soft: they happen all the time
    "mote_a": [dict(w="sine", f=1175, f2=1480, d=0.05, v=0.2)],
    "mote_b": [dict(w="sine", f=1480, f2=1175, d=0.05, v=0.18)],
    "blossom": [dict(w="tri", f=392, f2=784, d=0.12, v=0.36), dict(w="tri", f=784, f2=1568, d=0.2, v=0.32),
                dict(w="sine", f=2093, d=0.24, v=0.14, at=0.1, vib=(9, 0.4))],
    # the night's breathing: a low hum that climbs as the maze empties, a flutter while the spirits are pale
    "hum0": [dict(w="sine", f=165, f2=196, d=0.3, v=0.1, r="lin"),
             dict(w="sine", f=196, f2=165, d=0.3, v=0.1, r="lin")],
    "hum1": [dict(w="sine", f=196, f2=233, d=0.26, v=0.1, r="lin"),
             dict(w="sine", f=233, f2=196, d=0.26, v=0.1, r="lin")],
    "hum2": [dict(w="sine", f=233, f2=277, d=0.22, v=0.11, r="lin"),
             dict(w="sine", f=277, f2=233, d=0.22, v=0.11, r="lin")],
    "flutter": [dict(w="tri", f=330, f2=247, d=0.16, v=0.14, vib=(16, 0.9))],
    "eyes": [dict(w="square", f=1568, d=0.025, v=0.07, duty=0.25), dict(w="square", f=2349, d=0.03, v=0.07, duty=0.25)],
    "catch": [dict(w="saw", f=220, f2=1760, d=0.13, v=0.28), dict(w="tri", f=1760, f2=880, d=0.12, v=0.3),
              dict(w="noise", f=5000, f2=1500, d=0.12, v=0.08, at=0)],
    "death": [dict(w="tri", f=988, f2=880, d=0.12, v=0.38), dict(w="tri", f=880, f2=659, d=0.14, v=0.38),
              dict(w="tri", f=740, f2=440, d=0.18, v=0.38), dict(w="tri", f=523, f2=98, d=0.7, v=0.4, vib=(10, 0.6), r="lin"),
              dict(w="noise", f=3000, f2=200, d=0.5, v=0.1, at=0.5)],
    "treat_up": [dict(w="sine", f=1568, d=0.06, v=0.18), dict(w="sine", f=2093, d=0.12, v=0.18)],
    "treat": [dict(w="tri", f=f, d=0.05, v=0.32) for f in (1047, 1319, 1568, 2093)] +
             [dict(w="sine", f=2637, d=0.16, v=0.14, vib=(8, 0.3))],
    "clear": [dict(w="tri", f=f, d=0.07, v=0.34) for f in (659, 784, 988, 1175, 988, 1175, 1319)] +
             [dict(w="tri", f=1568, d=0.4, v=0.36, vib=(6, 0.25), r="lin")],
    "extra": [dict(w="square", f=f, d=0.07, v=0.26, duty=0.25) for f in (784, 988, 1175, 1568)] +
             [dict(w="tri", f=1568, d=0.3, v=0.36, vib=(7, 0.3)), dict(w="tri", f=1976, d=0.3, v=0.2, at=0.28)],
    # a little night tune when a game starts, a shorter one for every new maze
    "start": [dict(w="tri", f=f, d=d, v=0.36) for f, d in ((659, 0.13), (784, 0.13), (988, 0.13), (880, 0.26), (784, 0.13),
                                                            (659, 0.13), (587, 0.13), (659, 0.4))] +
             [dict(w="sine", f=f, d=0.5, v=0.2, at=a) for f, a in ((165, 0), (147, 0.52), (131, 1.04))],
    "maze": [dict(w="tri", f=f, d=0.1, v=0.32) for f in (784, 988, 880, 1175)] + [dict(w="tri", f=1319, d=0.3, v=0.32)],
    "interlude": [dict(w="tri", f=f, d=0.16, v=0.3) for f in (523, 659, 784, 659, 587, 698, 880, 698)] +
                 [dict(w="tri", f=784, d=0.5, v=0.32, vib=(5, 0.2), r="lin")],
    "over": [dict(w="tri", f=659, d=0.18, v=0.36), dict(w="tri", f=587, d=0.18, v=0.36), dict(w="tri", f=523, d=0.18, v=0.36),
             dict(w="tri", f=440, f2=330, d=0.7, v=0.38, r="lin")],
    "menu": [dict(w="tri", f=660, d=0.025, v=0.2)],
    "go": [dict(w="tri", f=784, d=0.05, v=0.3), dict(w="tri", f=1175, d=0.12, v=0.3)],
    "pause": [dict(w="tri", f=523, f2=392, d=0.07, v=0.22)],
    "sound_on": [dict(w="tri", f=440, d=0.06, v=0.35), dict(w="tri", f=880, d=0.12, v=0.35)],
})
HELP = [
    "GLIMMER - keys",
    "",
    "Arrows  (W A S D)      move; a turn pressed early",
    "                       waits until the path opens",
    "",
    "Gather every light mote. A sun blossom turns the",
    "spirits pale: catch them for 200, 400, 800, 1600.",
    "Night treats appear twice per maze. An extra wisp",
    "at 10000 points. Murk chases, Nettle cuts you off,",
    "Hollow flanks with Murk, Sorrel is shy. Spirits",
    "are slow in the tunnels.",
    "",
    "Esc / P                pause menu (Q quit, M sound)",
    "?                      this help",
    "",
    "Auto mode: the game plays itself (Space pause,",
    "+/- speed, Esc stop)",
]


# =============================================================================================
# Mazes
# =============================================================================================
class Maze:
    def __init__(self, idx):
        self.idx = idx % len(MAZES)
        self.name, half = MAZES[self.idx]
        st = STYLE[self.name]
        self.hedge, self.ground, self.speck, self.feat = st["hedge"], st["ground"], st["speck"], st["feat"]
        self.g = [r + "".join(MIRROR.get(c, c) for c in reversed(r[:-1])) for r in half]
        self.W, self.H = len(self.g[0]), len(self.g)
        self.motes, self.power, self.slow, self.gate = set(), set(), set(), {}
        self.door = self.start = self.treat = None
        for y, row in enumerate(self.g):
            for x, c in enumerate(row):
                if c == ".":
                    self.motes.add((x, y))
                elif c == "o":
                    self.power.add((x, y))
                elif c == "t":
                    self.slow.add((x, y))
                elif c in GATES:
                    self.gate[(x, y)] = GATES[c]
                elif c == "-":
                    self.door = (x, y)
                elif c == "P":
                    self.start = (x, y)
                elif c == "%":
                    self.treat = (x, y)
        self.wall = [[c in "#-B" for c in row] for row in self.g]
        self.tiles = [(x, y) for y in range(self.H) for x in range(self.W) if not self.wall[y][x]]
        dc, dr = self.door if self.door else (MW // 2, MH // 2)
        self.home = (dc, dr - 1)               # the tile in front of the burrow door
        self.slot_y = dr + 1.5                 # where spirits float inside the burrow
        self.to_home = self.distances(self.home)

    def can(self, x, y, d):
        """May something on tile (x, y) step one tile in direction d?"""
        g = self.gate.get((x, y))
        if g is not None and g != d:
            return False
        dx, dy = DIRS[d]
        nx, ny = (x + dx) % self.W, y + dy
        if not 0 <= ny < self.H or self.wall[ny][nx]:
            return False
        g = self.gate.get((nx, ny))
        return g is None or g == d

    def step(self, x, y, d):
        return (x + DIRS[d][0]) % self.W, y + DIRS[d][1]

    def distances(self, goal, reverse=True):
        """Steps from every tile to goal (reverse=True) or from goal to every tile, honouring the gates."""
        dist = {goal: 0}
        q = deque([goal])
        while q:
            p = q.popleft()
            for d in range(4):
                if reverse:   # which tile q can step in direction d onto p?
                    qx, qy = (p[0] - DIRS[d][0]) % self.W, p[1] - DIRS[d][1]
                    if 0 <= qy < self.H and not self.wall[qy][qx] and (qx, qy) not in dist and self.can(qx, qy, d):
                        dist[(qx, qy)] = dist[p] + 1
                        q.append((qx, qy))
                elif self.can(p[0], p[1], d):
                    n = self.step(p[0], p[1], d)
                    if n not in dist:
                        dist[n] = dist[p] + 1
                        q.append(n)
        return dist


def validate(m):
    """Every rule a maze must keep. Returns a list of problems (empty: fine)."""
    errs = []
    if m.H != MH or any(len(r) != MW for r in m.g):
        errs.append("size is not %dx%d" % (MW, MH))
        return errs
    for y, row in enumerate(m.g):
        for x, c in enumerate(row):
            if MIRROR.get(c, c) != m.g[y][MW - 1 - x]:
                errs.append("not symmetric at %d,%d" % (x, y))
            if c not in "#.o t-BP%^<v>":
                errs.append("unknown tile %r at %d,%d" % (c, x, y))
    for x in range(MW):
        if not m.wall[0][x] or not m.wall[MH - 1][x]:
            errs.append("open edge at column %d" % x)
    tunnels = [y for y in range(MH) if not m.wall[y][0]]
    for y in range(MH):
        if m.wall[y][0] != m.wall[y][MW - 1]:
            errs.append("tunnel row %d open on one side only" % y)
    if not tunnels:
        errs.append("no tunnel")
    for y in tunnels:
        if (0, y) not in m.slow:
            errs.append("tunnel row %d has no slow tiles" % y)
    if len(m.power) != 4:
        errs.append("%d sun blossoms instead of 4" % len(m.power))
    if not m.door or not m.start or not m.treat:
        errs.append("door, start or treat spot missing")
        return errs
    dc, dr = m.door
    if dc != MW // 2 or m.wall[dr - 1][dc] or m.g[dr + 1][dc] != "B" or m.g[dr + 2][dc] != "B":
        errs.append("the burrow needs open path above its door and two rows of burrow below")
    for dx in (-2, 2):
        if m.g[dr + 1][dc + dx] != "B":
            errs.append("the burrow is too narrow for three spirits")
    for (x, y) in m.tiles:   # no dead ends: spirits never have to turn round
        n = sum(1 for dx, dy in DIRS if 0 <= y + dy < MH and not m.wall[y + dy][(x + dx) % MW])
        if n < 2:
            errs.append("dead end at %d,%d" % (x, y))
    fwd = m.distances(m.start, reverse=False)
    back = m.distances(m.start, reverse=True)
    for t in m.tiles:
        if t not in fwd:
            errs.append("tile %d,%d can not be reached" % t)
        elif t not in back:
            errs.append("tile %d,%d is a trap (no way back)" % t)
    if len(m.to_home) != len(m.tiles):
        errs.append("eyes can not get home from every tile")
    return errs


def params(level):
    """Speeds (tiles per second) and timings of a level: everything gets quicker, the blossoms shorter."""
    k = min(level - 1, 12)
    f = max(0.35, 1 - 0.09 * k)
    if level == 1:
        sched = (7, 20, 7, 20, 5, 20, 5)
    elif level < 5:
        sched = (7, 20, 7, 20, 5, 40, 2)
    elif level < 7:          # a step between: the long chases come in two mazes later
        sched = (6, 20, 6, 20, 5, 50, 1)
    else:
        sched = (5, 20, 5, 20, 4, 60, 1)
    pspeed = 6.4 + 0.2 * k
    return dict(pspeed=pspeed, gspeed=min(5.9 + 0.26 * k, 0.96 * pspeed),   # never faster than the wisp
                fright=(6.0, 5.0, 4.5, 4.0, 3.5, 3.0, 2.6, 2.3, 2.0, 1.8, 1.5, 1.2, 1.0)[k],
                sched=sched, release=(0.0, 1.0 * f, 4.0 * f, 7.5 * f), idle=max(2.5, 4.5 - 0.2 * k),
                treat=TREATS[min(level - 1, len(TREATS) - 1)])


# =============================================================================================
# Things that move through the maze
# =============================================================================================
class Mover:
    def __init__(self, x, y, d):
        self.x, self.y, self.d = float(x), float(y), d

    def tile(self):
        return int(round(self.x)) % MW, int(round(self.y))

    def on_center(self):
        return abs(self.x - round(self.x)) < 1e-6 and abs(self.y - round(self.y)) < 1e-6


def advance(m, dist, maze, choose):
    """Move m by dist tiles along its direction. At every tile centre choose(tx, ty) may turn it or stop it
    (m.d = None). Wraps through the tunnels."""
    W = maze.W
    for _ in range(16):
        if dist <= 1e-9:
            return
        if m.on_center():
            m.x, m.y = float(round(m.x)), float(round(m.y))
            tx, ty = m.tile()
            choose(tx, ty)
            if m.d is None or not maze.can(tx, ty, m.d):
                m.d = None
                return
            rem = 1.0
        else:
            if m.d is None:
                return
            dx, dy = DIRS[m.d]
            if dx:                 # keep to the middle of the corridor
                m.y = float(round(m.y))
            else:
                m.x = float(round(m.x))
            p = m.x if dx else m.y
            rem = (math.ceil(p) - p) if (dx or dy) > 0 else (p - math.floor(p))
            if rem <= 1e-9:
                rem = 1.0
        step = min(dist, rem)
        dx, dy = DIRS[m.d]
        m.x += dx * step
        m.y += dy * step
        dist -= step
        if m.x < -0.5:
            m.x += W
        elif m.x >= W - 0.5:
            m.x -= W


def try_reverse(m, maze):
    """Turn round on the spot if no one-way gate forbids it."""
    if m.d is None:
        return False
    nd = OPP[m.d]
    if m.on_center():
        tx, ty = m.tile()
        if maze.can(tx, ty, nd):
            m.d = nd
            return True
        return False
    dx, dy = DIRS[m.d]
    if dx:
        a = math.ceil(m.x) if dx > 0 else math.floor(m.x)
        tiles = ((a % MW, int(round(m.y))), ((a - dx) % MW, int(round(m.y))))
    else:
        a = math.ceil(m.y) if dy > 0 else math.floor(m.y)
        tiles = ((int(round(m.x)) % MW, a), (int(round(m.x)) % MW, a - dy))
    for t in tiles:
        g = maze.gate.get(t)
        if g is not None and g != nd:
            return False
    m.d = nd
    return True


class Wisp(Mover):
    def __init__(self, maze):
        sx, sy = maze.start
        d = 1 if maze.can(sx, sy, 1) else 3
        Mover.__init__(self, sx, sy, d)
        self.want = None
        self.face = d
        self.trail = deque(maxlen=6)
        self.trail_t = 0.0

    def steer(self, maze):
        """Apply the remembered turn now if it can be: turning round any time, a corner when close to it."""
        w = self.want
        if w is None or self.d is None or w == self.d:
            return
        if w == OPP[self.d]:
            try_reverse(self, maze)
            return
        cx, cy = round(self.x), round(self.y)
        if abs(self.x - cx) + abs(self.y - cy) <= 0.42 and maze.can(int(cx) % MW, int(cy), w):
            self.x, self.y, self.d = float(cx), float(cy), w
            if self.x < -0.5:
                self.x += MW
            elif self.x >= MW - 0.5:
                self.x -= MW

    def choose(self, maze):
        def at(tx, ty):
            if self.want is not None and maze.can(tx, ty, self.want):
                self.d = self.want
            elif self.d is not None and maze.can(tx, ty, self.d):
                pass
            else:
                if self.d is not None:
                    self.face = self.d
                self.d = None
        return at


class Spirit(Mover):
    def __init__(self, i, maze):
        self.i = i
        self.name, self.color, self.corner, self.role = SPIRITS[i]
        Mover.__init__(self, 0, 0, 1)
        self.reset(maze)

    def reset(self, maze, release=0.0):
        dc, dr = maze.door
        if self.i == 0:
            self.x, self.y, self.state, self.d = float(dc), float(dr - 1), "roam", 1
        else:
            self.x, self.y = float(dc + (0, 0, -2, 2)[self.i]), maze.slot_y
            self.state, self.d = "house", 0
        self.fright = False
        self.rev = False
        self.release = release
        self.look = self.d
        self.phase = self.i * 1.7


# =============================================================================================
# A game
# =============================================================================================
class Game:
    def __init__(self, start=0, auto=False, sound=True, seed=None):
        self.start_idx = start
        self.auto = auto
        self.pilot = None            # auto mode: a Pilot (human eyes and reaction time); None: the title autopilot
        self.sound = sound
        self.rnd = random.Random(seed)
        self.score = 0
        self.lives = 3
        self.level = 0
        self.extra_given = False
        self.paused = self.help = False
        self.t = 0.0
        self.particles = []
        self.pops = []
        self.stats = dict(motes=0, blossoms=0, spirits=0, treats=0, deaths=0, cleared=0)
        self.best = 0 if auto else (load_scores().get(GAME, {}).get("score") or 0)
        self.next_level(first=True)

    def snd(self, name, **kw):
        if self.sound:
            SND.play(name, **kw)

    # --- set-up --------------------------------------------------------------------------------
    def next_level(self, first=False):
        self.level += 1
        self.maze = Maze(self.start_idx + self.level - 1)
        self.P = params(self.level)
        self.motes = set(self.maze.motes)
        self.power = set(self.maze.power)
        self.total = len(self.motes) + len(self.power)
        self.eaten = 0
        self.treat_shown = 0
        self.mode_i, self.mode_t = 0, self.P["sched"][0]
        self.play_t = 0.0
        self.fog = []
        if "fog" in self.maze.feat:
            r = self.rnd
            self.fog = [[r.uniform(0, MW), r.uniform(2, MH - 2), r.uniform(3.2, 4.6), r.choice((-1, 1)) * r.uniform(0.6, 1.2),
                         r.uniform(0, 6)] for _ in range(4)]
        self.reset_positions(first=True)
        self.state, self.state_t = "ready", 2.6 if first else 2.0
        self.snd("start" if first else "maze")

    def reset_positions(self, first=False):
        m = self.maze
        self.wisp = Wisp(m)
        rel = self.P["release"] if first else tuple(r * 0.6 for r in self.P["release"])
        self.spirits = [Spirit(i, m) for i in range(4)]
        for s in self.spirits:
            s.release = self.play_t + rel[s.i]
        self.fright_t = 0.0
        self.chain = 0
        self.treat = None            # (until, kind)
        self.last_eat = self.play_t
        self.hum_t = 0.0
        self.freeze_pop = None

    def mode(self):
        return "scatter" if self.mode_i % 2 == 0 and self.mode_i < len(self.P["sched"]) else "chase"

    # --- input -----------------------------------------------------------------------------------
    def key(self, k):
        if k in KEYDIR and self.state in ("ready", "play", "freeze"):
            self.wisp.want = KEYDIR[k]

    # --- time ------------------------------------------------------------------------------------
    def update(self, dt):
        if self.paused or self.state == "over":
            return
        n = max(1, int(math.ceil(dt / (1 / 60))))
        for _ in range(n):
            self.step(dt / n)

    def step(self, dt):
        self.t += dt
        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += p[6] * dt
            p[4] -= dt
        self.particles = [p for p in self.particles if p[4] > 0]
        self.pops = [p for p in self.pops if p[3] > self.t]
        for f in self.fog:
            f[0] += f[3] * dt * 0.5
            f[4] += dt
            if f[0] < -f[2] - 1:
                f[0] = MW + f[2]
            elif f[0] > MW + f[2] + 1:
                f[0] = -f[2]
        w = self.wisp
        if self.state in ("play", "ready", "freeze") and self.rnd.random() < dt * 5:   # the wisp sheds sparks
            r = self.rnd
            self.particles.append([w.x + r.uniform(-0.3, 0.3), w.y + r.uniform(-0.2, 0.3), r.uniform(-0.3, 0.3),
                                   r.uniform(-1.2, -0.5), 0.5, 0.5, 0.0, r.choice((WISP_RIM, (255, 236, 160)))])
        w.trail_t += dt
        if w.trail_t > 0.035:
            w.trail_t = 0.0
            w.trail.append((w.x, w.y))
        self.state_t -= dt
        st = self.state
        if st == "ready":
            if self.auto:
                self.wisp.want = self.pilot(self, dt) if self.pilot else bot_want(self)
            if self.state_t <= 0:
                self.state = "play"
        elif st == "freeze":
            if self.state_t <= 0:
                self.state = "play"
                self.freeze_pop = None
        elif st == "dying":
            if self.state_t + dt > 1.4 >= self.state_t:     # the wisp comes apart
                self.burst(w.x, w.y, 26, (WISP_RIM, WISP_CORE, (255, 240, 170)), speed=3.2, up=-1.2, life=1.2)
            if self.state_t <= 0:
                self.lives -= 1
                if self.lives <= 0:
                    self.state = "over"
                    self.snd("over")
                else:
                    self.reset_positions()
                    self.state, self.state_t = "ready", 1.8
        elif st == "clear":
            if self.state_t <= 0:
                self.stats["cleared"] += 1
                if self.level % 3 == 0:
                    self.state, self.state_t = "interlude", 7.0
                    self.snd("interlude")
                else:
                    self.next_level()
        elif st == "interlude":
            if self.state_t <= 0:
                self.next_level()
        elif st == "play":
            self.play(dt)

    def add(self, pts):
        self.score += pts
        if not self.extra_given and self.score >= EXTRA_AT:
            self.extra_given = True
            self.lives += 1
            self.snd("extra")
            self.pops.append(["EXTRA WISP!", self.wisp.x, self.wisp.y - 1.5, self.t + 2.0, (255, 236, 150)])

    def burst(self, x, y, n, colors, speed=2.0, up=0.0, life=0.6):
        r = self.rnd
        for _ in range(n):
            a = r.uniform(0, 2 * math.pi)
            v = r.uniform(0.3, 1.0) * speed
            l = r.uniform(0.5, 1.0) * life
            self.particles.append([x, y, math.cos(a) * v, math.sin(a) * v + up, l, l, -0.6 if up else 0.0, r.choice(colors)])

    def play(self, dt):
        m, P, w = self.maze, self.P, self.wisp
        self.play_t += dt
        if self.auto:
            w.want = self.pilot(self, dt) if self.pilot else bot_want(self)
        # spirit moods: scatter / chase on a timer that stops while they are pale
        if self.fright_t > 0:
            self.fright_t -= dt
            if self.fright_t <= 0:
                for s in self.spirits:
                    s.fright = False
        elif self.mode_i < len(P["sched"]):
            self.mode_t -= dt
            if self.mode_t <= 0:
                self.mode_i += 1
                self.mode_t = P["sched"][self.mode_i] if self.mode_i < len(P["sched"]) else 1e9
                for s in self.spirits:
                    if s.state == "roam":
                        s.rev = True
        # the wisp
        speed = P["pspeed"] * (1.08 if self.fright_t > 0 else 1.0)
        w.steer(m)
        advance(w, speed * dt, m, w.choose(m))
        if w.d is not None:
            w.face = w.d
        t = w.tile()
        if t in self.motes:
            self.motes.discard(t)
            self.eaten += 1
            self.stats["motes"] += 1
            self.add(10)
            self.last_eat = self.play_t
            self.waka = not getattr(self, "waka", False)
            self.snd("mote_a" if self.waka else "mote_b", gap=0.03)
            if self.rnd.random() < 0.5:
                self.burst(t[0], t[1], 2, (MOTE, (255, 255, 230)), speed=1.6, life=0.35)
        elif t in self.power:
            self.power.discard(t)
            self.eaten += 1
            self.stats["blossoms"] += 1
            self.add(50)
            self.last_eat = self.play_t
            self.snd("blossom")
            self.burst(t[0], t[1], 14, BLOSSOM + ((255, 250, 210),), speed=3.0, life=0.6)
            self.fright_t = P["fright"]
            self.chain = 0
            for s in self.spirits:
                if s.state == "roam":
                    s.rev = True
                if s.state != "eyes" and s.state != "enter" and P["fright"] > 0:
                    s.fright = True
        if self.treat_shown < 2 and self.eaten >= (70, 170)[self.treat_shown]:
            self.treat_shown += 1
            self.treat = (self.play_t + 9.5, P["treat"])
            self.snd("treat_up")
        if self.treat:
            if self.play_t > self.treat[0]:
                self.treat = None
            elif t == m.treat:
                name, pts, _ = self.treat[1]
                self.add(pts)
                self.stats["treats"] += 1
                self.snd("treat")
                self.pops.append(["%d" % pts, m.treat[0], m.treat[1], self.t + 1.6, (255, 200, 240)])
                self.burst(m.treat[0], m.treat[1], 12, ((255, 200, 240), (255, 255, 255)), speed=2.4)
                self.treat = None
        # the spirits
        waiting = [s for s in self.spirits if s.state == "house" and s.release > self.play_t]
        if waiting and self.play_t - self.last_eat > P["idle"]:
            waiting[0].release = self.play_t
            self.last_eat = self.play_t
        for s in self.spirits:
            self.move_spirit(s, dt)
        # touching
        for s in self.spirits:
            if s.state not in ("roam", "eyes"):
                continue
            dx = abs(s.x - w.x)
            dx = min(dx, MW - dx)
            if dx * dx + (s.y - w.y) ** 2 > 0.36:
                continue
            if s.state == "roam" and s.fright:
                pts = 200 * 2 ** min(self.chain, 3)
                self.chain += 1
                self.add(pts)
                self.stats["spirits"] += 1
                s.state, s.fright = "eyes", False
                self.snd("catch")
                self.burst(s.x, s.y, 16, (s.color, PALE, (255, 255, 255)), speed=3.0)
                self.freeze_pop = (s, "%d" % pts)
                self.pops.append(["%d" % pts, s.x, s.y, self.t + 1.2, (160, 230, 255)])
                self.state, self.state_t = "freeze", 0.55
                return
            if s.state == "roam":
                self.state, self.state_t = "dying", 2.0
                self.stats["deaths"] += 1
                self.snd("death")
                return
        if not self.motes and not self.power:
            self.state, self.state_t = "clear", 2.2
            self.snd("clear")
            return
        # the background hum
        self.hum_t -= dt
        if self.hum_t <= 0:
            if any(s.state == "eyes" for s in self.spirits):
                self.snd("eyes", gap=0.1)
                self.hum_t = 0.22
            elif self.fright_t > 0:
                self.snd("flutter", gap=0.1)
                self.hum_t = 0.34
            else:
                left = (len(self.motes) + len(self.power)) / max(1, self.total)
                self.snd("hum%d" % (0 if left > 0.6 else 1 if left > 0.25 else 2), gap=0.1)
                self.hum_t = 0.62

    # --- spirits -------------------------------------------------------------------------------
    def target(self, s):
        w = self.wisp
        wx, wy = w.tile()
        if self.mode() == "scatter":
            return s.corner
        face = w.d if w.d is not None else w.face
        fx, fy = DIRS[face]
        if s.i == 0:
            return wx, wy
        if s.i == 1:
            return wx + 4 * fx, wy + 4 * fy
        if s.i == 2:
            mx, my = self.spirits[0].tile()
            ax, ay = wx + 2 * fx, wy + 2 * fy
            return 2 * ax - mx, 2 * ay - my
        sx, sy = s.tile()
        dx = min(abs(sx - wx), MW - abs(sx - wx))
        return (wx, wy) if dx * dx + (sy - wy) ** 2 > 64 else s.corner

    def chooser(self, s):
        m = self.maze

        def at(tx, ty):
            if s.state == "eyes" and (tx, ty) == m.home:
                s.state = "enter"
                s.d = None
                return
            opts = [d for d in range(4) if s.d is not None and d != OPP[s.d] and m.can(tx, ty, d)]
            if not opts:
                opts = [d for d in range(4) if m.can(tx, ty, d)]
            if not opts:
                s.d = None
                return
            if s.state == "eyes":
                dist = m.to_home
                s.d = min(opts, key=lambda d: dist.get(m.step(tx, ty, d), 999))
            elif s.fright:
                s.d = self.rnd.choice(opts)
            else:
                gx, gy = self.target(s)
                best = None
                for d in opts:
                    nx, ny = tx + DIRS[d][0], ty + DIRS[d][1]
                    v = (nx - gx) ** 2 + (ny - gy) ** 2
                    if best is None or v < best[0]:
                        best = (v, d)
                s.d = best[1]
        return at

    def spirit_speed(self, s):
        P = self.P
        if s.state == "eyes":
            return 13.0
        if s.tile() in self.maze.slow:
            return P["gspeed"] * 0.45
        if s.fright:
            return P["gspeed"] * 0.55
        v = P["gspeed"]
        if s.i == 0:
            left = len(self.motes) + len(self.power)
            v *= 1.1 if left <= 12 else 1.05 if left <= 28 else 1.0
        return v

    def move_spirit(self, s, dt):
        m = self.maze
        dc, dr = m.door
        s.phase += dt
        if s.state == "house":
            s.y = m.slot_y + 0.28 * math.sin(s.phase * 5.0)
            s.look = 0 if math.cos(s.phase * 5.0) > 0 else 2
            if self.play_t >= s.release:
                s.state = "leave"
        elif s.state == "leave":
            v = 3.0 * dt
            if abs(s.x - dc) > 1e-6:
                s.look = 3 if dc > s.x else 1
                s.x += clamp(dc - s.x, -v, v)
                s.y += clamp(m.slot_y - s.y, -v, v)
            else:
                s.look = 0
                s.y -= v
                if s.y <= dr - 1:
                    s.x, s.y, s.state = float(dc), float(dr - 1), "roam"
                    s.d = 1 if s.i % 2 == 0 else 3
                    s.rev = False
        elif s.state == "enter":
            s.look = 2
            s.y += 7.0 * dt
            if s.y >= m.slot_y:
                s.y = m.slot_y
                s.state = "house"
                s.fright = False
                s.release = self.play_t + 0.35
        else:
            if s.rev:
                s.rev = False
                try_reverse(s, m)
            if s.d is None:
                s.d = 1
            advance(s, self.spirit_speed(s) * dt, m, self.chooser(s))
            if s.d is not None:
                s.look = s.d


def bot_want(g, spirits=None, R=2, ahead=3, path=False, flee=False):
    """The autopilot (title screen, self-test and auto mode): the nearest mote, blossom, treat or pale spirit by
    a path that keeps away from the spirits; when cornered, the way that gains the most distance.
    spirits: the spirits as the player sees them (auto mode's Pilot); None: all of them, exactly."""
    m, w = g.maze, g.wisp
    start = w.tile()
    if spirits is None:
        spirits = g.spirits
    danger = set()
    hunt = set()
    for s in spirits:
        tx, ty = s.tile()
        if s.state == "roam" and s.fright and g.fright_t > 0.8:
            hunt.add((tx, ty))
        elif s.state in ("roam", "leave"):
            if path:        # every tile the spirit can reach within R steps (it can not turn round)
                ring = [((tx, ty), s.d)]
                danger.add((tx, ty))
                for _ in range(R):
                    nxt = []
                    for (px, py), pd in ring:
                        for d in range(4):
                            if (pd is None or d != OPP[pd]) and m.can(px, py, d):
                                n = m.step(px, py, d)
                                danger.add(n)
                                nxt.append((n, d))
                    ring = nxt
            else:
                for dy in range(-R, R + 1):
                    for dx in range(-R + abs(dy), R + 1 - abs(dy)):
                        danger.add(((tx + dx) % MW, ty + dy))
            if s.d is not None:
                for k in range(1, ahead + 1):
                    danger.add(((tx + DIRS[s.d][0] * k) % MW, ty + DIRS[s.d][1] * k))
    danger.discard(start)
    goals = g.motes | g.power | hunt
    if g.treat:
        goals = goals | {m.treat}
    prev = {start: None}
    q = deque([start])
    found = None
    while q:
        p = q.popleft()
        if p != start and p in goals:
            found = p
            break
        for d in range(4):
            if m.can(p[0], p[1], d):
                n = m.step(p[0], p[1], d)
                if n not in prev and n not in danger:
                    prev[n] = (p, d)
                    q.append(n)
    if found:
        p = found
        while prev[p][0] != start:
            p = prev[p][0]
        return prev[p][1]
    best = None
    if flee:      # cornered: the way with the most room away from the spirits (not into a pocket)
        for d in range(4):
            if not m.can(start[0], start[1], d):
                continue
            n0 = m.step(start[0], start[1], d)
            seen = {start, n0}
            q = deque([n0])
            room = 0 if n0 in danger else 1
            while q and room < 80:
                p = q.popleft()
                for d2 in range(4):
                    if m.can(p[0], p[1], d2):
                        n = m.step(p[0], p[1], d2)
                        if n not in seen and n not in danger:
                            seen.add(n)
                            q.append(n)
                            room += 1
            if n0 in danger:
                room = -1 - min([min(abs(n0[0] - s.x), MW - abs(n0[0] - s.x)) + abs(n0[1] - s.y) for s in spirits
                                 if s.state == "roam" and not s.fright] or [99]) * -1 - 100
            if best is None or room > best[0]:
                best = (room, d)
        return best[1] if best else w.want
    for d in range(4):
        if not m.can(start[0], start[1], d):
            continue
        nx, ny = m.step(start[0], start[1], d)
        far = min([min(abs(nx - s.x), MW - abs(nx - s.x)) + abs(ny - s.y) for s in spirits
                   if s.state == "roam" and not s.fright] or [99])
        if best is None or far > best[0]:
            best = (far, d)
    return best[1] if best else w.want


def fog_at(g, x, y):
    """How thick the drifting fog is on a tile (0..0.9), as draw_fog paints it (without the clearing round the wisp)."""
    a = 0.0
    for f in g.fog:
        d = math.hypot(x - f[0], y - f[1] - 0.8 * math.sin(f[4] * 0.6)) / f[2]
        if d < 1:
            b = 1 - d
            a = max(a, b * b * (3 - 2 * b) * 0.9)
    return a


class Seen:
    """A spirit as the auto-mode player saw it at one moment."""
    __slots__ = ("x", "y", "d", "state", "fright")

    def __init__(self, s):
        self.x, self.y, self.d, self.state, self.fright = s.x, s.y, s.d, s.state, s.fright

    def tile(self):
        return int(round(self.x)) % MW, int(round(self.y))


class Pilot:
    """Auto mode's player: the autopilot's route finding with a human's limits. It reacts to what it saw
    REACT seconds ago, thinks again only every THINK seconds (now and then it hesitates a little longer), and
    sees only what is visible: in the dark mazes the spirits inside its own light, in the fog not the ones
    hidden in a thick bank (a spirit it lost sight of is remembered where it was last seen for a moment)."""
    REACT, THINK, HESITATE, MEMORY = 0.15, 0.08, 0.03, 1.2

    def __init__(self, seed=None):
        self.rnd = random.Random(seed)
        self.t = 0.0
        self.hist = deque()
        self.next = 0.0
        self.want = None
        self.last = {}                 # spirit index -> (Seen, when) of the last sighting

    def visible(self, g, i, s):
        if s.state not in ("roam", "leave"):
            return True
        w = g.wisp
        dx = abs(s.x - w.x)
        dist = math.hypot(min(dx, MW - dx), s.y - w.y)
        if "dark" in g.maze.feat and dist > 5.6 + (1.6 if g.fright_t > 0 else 0.0) - 0.6:
            return False
        if g.fog and dist > 2.6 and fog_at(g, s.x, s.y) > 0.55:
            return False
        return True

    def __call__(self, g, dt):
        self.t += dt
        if g.state != "play":
            self.hist.clear()
            self.last.clear()
        self.hist.append((self.t, [Seen(s) for s in g.spirits]))
        while len(self.hist) > 1 and self.hist[1][0] <= self.t - self.REACT:
            self.hist.popleft()
        if self.t >= self.next or self.want is None:
            self.next = self.t + (0.3 if self.rnd.random() < self.HESITATE else self.THINK)
            seen = []
            for i, s in enumerate(self.hist[0][1]):
                if self.visible(g, i, s):
                    self.last[i] = (s, self.t)
                    seen.append(s)
                elif i in self.last and self.t - self.last[i][1] < self.MEMORY:
                    seen.append(self.last[i][0])
            self.want = bot_want(g, seen, R=3, ahead=2, path=True, flee=True)
        return self.want


# =============================================================================================
# Drawing
# =============================================================================================
def layout(cols, rows, hud=True):
    """Tile size and where the maze sits: as big as the window allows, a HUD row on top, a footer if it fits."""
    PW, PH = cols, rows * 2
    top = 2 if hud else 0
    T = max(1, min(PW // MW, (PH - top) // MH))
    foot = hud and PH - top - MH * T >= 4
    avail = PH - top - (2 if foot else 0)
    ox = (PW - MW * T) // 2
    oy = top + max(0, (avail - MH * T) // 2)
    if hud and oy % 2 and oy - 1 >= top:     # keep tile rows on whole text rows where possible
        oy -= 1
    return T, ox, oy, foot


def hsh(x, y, s=0):
    n = (x * 374761393 + y * 668265263 + s * 1442695041) & 0xffffffff
    n = ((n ^ (n >> 13)) * 1274126177) & 0xffffffff
    return ((n ^ (n >> 16)) & 0xffff) / 65535.0


def sky(W, H, seed):
    rows = [[mix((6, 8, 20), (16, 10, 28), y / max(1, H - 1))] * W for y in range(H)]
    r = random.Random(seed)
    for _ in range(W * H // 70):
        x, y = r.randrange(W), r.randrange(H)
        rows[y][x] = mix(rows[y][x], (200, 210, 255), r.uniform(0.15, 0.6))
    return rows


def leaves(x, y, n):
    """Big hedges: clumps of leaves three pixels across, each lit from the top left (n: the pixel's own noise)."""
    lr = y // 3
    lx = (x + (lr % 2) * 1.5 + 0.5) % 3 - 1.5
    ly = y % 3 - 1.0
    leaf = 0.3 if lx + ly < -1.2 else -0.26 if lx + ly > 1.4 else 0.0
    return 0.55 * hsh(int(x + (lr % 2) * 1.5) // 3, lr, 5) + 0.45 * n + leaf


_LAYERS = {}


def layers(m, cols, rows, T, ox, oy):
    """The maze drawn once per maze and window size, three ways: as it is (base), fully lit by the wisp
    (lit; the glow blends between the two) and with white hedges (flash, for a cleared maze)."""
    key = (m.idx, cols, rows, T, ox, oy)
    got = _LAYERS.get(key)
    if got:
        return got
    if len(_LAYERS) > 12:
        _LAYERS.clear()
    W, H = cols, rows * 2
    base = sky(W, H, m.idx * 7 + 1)
    lit = [r[:] for r in base]
    flash = [r[:] for r in base]
    dark = "dark" in m.feat
    hedge, ground, speck, wall = m.hedge, m.ground, m.speck, m.wall

    def is_wall(tx, ty):
        return not (0 <= tx < MW and 0 <= ty < MH) or wall[ty][tx]

    def hedge_at(tx, ty):
        return 0 <= tx < MW and 0 <= ty < MH and m.g[ty][tx] == "#"

    def inner(tx, ty, sx, sy):
        """Big tiles: does the path tile (tx, ty) carry a rounded inner hedge corner towards (sx, sy)? It does where
        hedges close in on two sides and across the corner (a concave corner of the maze walls)."""
        return (T >= 5 and 0 <= tx < MW and 0 <= ty < MH and m.g[ty][tx] in ".o P%" and hedge_at(tx + sx, ty)
                and hedge_at(tx, ty + sy) and hedge_at(tx + sx, ty + sy))

    ri = T * 0.6                      # radius of the inner corners, the same as the outer ones

    def fillet(xx, yy, sx, sy):
        """How much of pixel (xx, yy) of a path tile the inner corner towards (sx, sy) fills with hedge, and the
        distance from the arc's centre."""
        ux, uy = xx + 0.5 - (T / 2 + sx * (T / 2 - ri)), yy + 0.5 - (T / 2 + sy * (T / 2 - ri))
        if ux * sx <= 0 or uy * sy <= 0:
            return 0.0, 0.0
        d = math.hypot(ux, uy)
        return clamp(d - ri + 0.5, 0.0, 1.0), d

    for ty in range(MH):
        for tx in range(MW):
            c = m.g[ty][tx]
            x0, y0 = ox + tx * T, oy + ty * T
            up, down = is_wall(tx, ty - 1), is_wall(tx, ty + 1)
            left, right = is_wall(tx - 1, ty), is_wall(tx + 1, ty)
            # big tiles: the hedges get rounded outer corners (a topiary, not a stack of boxes)
            rc = T * 0.6 if c == "#" and T >= 5 else 0
            corners = [] if not rc else [(cx_, cy_, sx_, sy_) for cx_, cy_, sx_, sy_, open_ in (
                (rc, rc, -1, -1, not up and not left), (T - rc, rc, 1, -1, not up and not right),
                (rc, T - rc, -1, 1, not down and not left), (T - rc, T - rc, 1, 1, not down and not right)) if open_]
            # rounded inner corners: a path tile gets a fillet of hedge in each concave corner ...
            fillets = [] if c == "#" or T < 5 else [(sx_, sy_) for sx_ in (-1, 1) for sy_ in (-1, 1)
                                                   if inner(tx, ty, sx_, sy_)]
            # ... and the hedge tiles beside it drop their straight rim where the fillet takes over
            calm = [] if c != "#" or T < 5 else [(sx_, sy_, ax_) for sx_, sy_, ax_ in (
                (-1, -1, "x"), (1, -1, "x"), (-1, 1, "x"), (1, 1, "x"),
                (-1, -1, "y"), (1, -1, "y"), (-1, 1, "y"), (1, 1, "y"))
                if (ax_ == "x" and inner(tx, ty + sy_, sx_, -sy_)) or (ax_ == "y" and inner(tx + sx_, ty, -sx_, sy_))]
            for yy in range(T):
                y = y0 + yy
                if not 0 <= y < H:
                    continue
                brow, lrow, frow = base[y], lit[y], flash[y]
                for xx in range(T):
                    x = x0 + xx
                    if not 0 <= x < W:
                        continue
                    n = hsh(x, y)
                    if c == "#":
                        if T >= 5:      # big tiles: clumps of leaves, each lit from the top left
                            n = leaves(x, y, n)
                        col = shade(hedge, 0.74 + 0.5 * n)
                        if speck and hsh(x, y, 3) < 0.05:
                            col = mix(col, speck, 0.8)
                        flat = False
                        for sx_, sy_, ax_ in calm:     # this rim pixel lies under a neighbour's inner fillet
                            if ax_ == "x":   # the path is above / below (sy_), the fillet in its corner on side sx_
                                if yy == (0 if sy_ < 0 else T - 1) and fillet(xx, T - 1 if sy_ < 0 else 0, sx_, -sy_)[0] >= 0.5:
                                    flat = True
                            elif xx == (0 if sx_ < 0 else T - 1) and fillet(T - 1 if sx_ < 0 else 0, yy, -sx_, sy_)[0] >= 0.5:
                                flat = True
                        if flat:
                            pass
                        elif yy == 0 and not up:
                            col = shade(col, 1.45)
                        elif yy == T - 1 and not down:
                            col = shade(col, 0.55)
                        elif T >= 3 and xx == 0 and not left:
                            col = shade(col, 1.18)
                        elif T >= 3 and xx == T - 1 and not right:
                            col = shade(col, 0.78)
                        if corners:
                            for ccx, ccy, csx, csy in corners:
                                ux, uy = xx + 0.5 - ccx, yy + 0.5 - ccy
                                if ux * csx > 0 and uy * csy > 0:
                                    d = math.hypot(ux, uy)
                                    if d > rc - 1.1:      # the rim follows the curve, lit on top, shaded below
                                        col = shade(shade(hedge, 0.74 + 0.5 * n), 1.45 if csy < 0 else 0.55)
                                    cover = clamp(rc - d + 0.5, 0.0, 1.0)
                                    if cover < 1:
                                        col = mix(shade(ground, 0.86 + 0.28 * n), col, cover)
                                    break
                        fl = mix(col, (214, 232, 255), 0.7)
                    elif c == "B":
                        col = fl = shade((30, 18, 36), 0.85 + 0.3 * n)
                    else:
                        col = shade(ground, 0.86 + 0.28 * n)
                        for csx, csy in fillets:
                            cover, d = fillet(xx, yy, csx, csy)
                            if cover > 0:                # in the corner, beyond the arc: hedge
                                nn = leaves(x, y, n)     # the same leaf clumps as the hedge tiles
                                hc = shade(hedge, 0.74 + 0.5 * nn)
                                if speck and hsh(x, y, 3) < 0.05:
                                    hc = mix(hc, speck, 0.8)
                                if d < ri + 1.1:         # the rim follows the curve, as on the outer corners:
                                    hc = shade(shade(hedge, 0.74 + 0.5 * max(nn, 0.5)), 1.45 if csy > 0 else 0.55)
                                    #   lit where the hedge is below, and kept out of the leaves' shadows so it reads
                                col = mix(col, hc, cover)
                        if c == "t":
                            col = shade(col, 0.6)
                        elif c == "-" and yy < max(1, T // 3):
                            col = (230, 164, 200) if xx % 3 != 2 or T < 4 else (180, 120, 160)
                        elif c in GATES:   # a chevron of thorn-roses pointing the one allowed way
                            gd = GATES[c]
                            a = (xx, yy, T - 1 - xx, T - 1 - yy)[(3, 2, 1, 0)[gd]]
                            p = abs((yy if gd in (1, 3) else xx) - (T - 1) / 2)
                            dd = (T - 1) - a - int(round(p - 0.01))
                            if dd == 0 or (T >= 5 and dd == 1):
                                col = (236, 112, 166)
                        fl = col
                    brow[x] = shade(col, 0.17) if dark else col
                    lrow[x] = mix(shade(col, 1.9), WARM, 0.2)
                    frow[x] = fl
    got = (base, lit, flash)
    _LAYERS[key] = got
    return got


_GLOW = {}


def glow_table(R):
    R = round(R, 1)
    t = _GLOW.get(R)
    if t is None:
        t = []
        r = int(R) + 1
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                w = 1 - math.hypot(dx, dy) / R
                if w > 0.02:
                    t.append((dx, dy, w ** 1.3))
        _GLOW[R] = t
    return t


def apply_glow(px, base, lit, ix, iy, table, k, x0, y0, x1, y1):
    """Blend from the base layer towards the lit one around (ix, iy): the wisp's light on hedges and path."""
    for dx, dy, w in table:
        x, y = ix + dx, iy + dy
        if x0 <= x < x1 and y0 <= y < y1:
            b, l = base[y][x], lit[y][x]
            ww = w * k
            px[y][x] = (b[0] + int((l[0] - b[0]) * ww), b[1] + int((l[1] - b[1]) * ww), b[2] + int((l[2] - b[2]) * ww))


def disc(cv, cx, cy, r, c, edge=0.0, clip=None):
    """A filled circle; edge > 0 adds a soft rim that fades into what is underneath."""
    x0, y0, x1, y1 = clip or (0, 0, cv.W, cv.H)
    R = r + edge
    px = cv.px
    for y in range(max(y0, int(cy - R - 1)), min(y1, int(cy + R + 2))):
        dy = y + 0.5 - cy
        row = px[y]
        for x in range(max(x0, int(cx - R - 1)), min(x1, int(cx + R + 2))):
            dx = x + 0.5 - cx
            d = math.sqrt(dx * dx + dy * dy)
            if d <= r:
                row[x] = c
            elif d < R:
                row[x] = mix(row[x], c, (R - d) / edge * 0.85)


def draw_wisp(cv, cx, cy, size, t, scale=1.0, clip=None):
    rc = max(0.85, size * 0.44) * scale * (1 + 0.07 * math.sin(t * 13))
    if rc <= 0.05:
        return
    disc(cv, cx, cy, rc, WISP_RIM, edge=max(0.9, size * 0.22) * scale, clip=clip)
    disc(cv, cx, cy, max(0.72 * min(1, scale * 1.5), rc * 0.6), WISP_CORE, clip=clip)


_MASK = {}


def spirit_mask(S, ph):
    """A shadow spirit's outline: a swaying flame-tip head over a round body with a ragged hem."""
    key = (S, ph)
    got = _MASK.get(key)
    if got:
        return got
    if S <= 2:
        rows = ["##", "##"][:S]
    elif S == 3:
        rows = [".#.", "###", "#.#" if ph % 2 else "###"]
    elif S == 4:
        rows = [".#..", "####", "####", "#.#." if ph % 2 else ".#.#"][:4]
        rows[0] = (".#..", "..#.", ".#..", ".##.")[ph]
    else:
        sway = (-0.3, 0.0, 0.3, 0.0)[ph]

        def ins(i, u, v):
            body = u * u + ((v - 0.16) / 0.86) ** 2 <= 0.74
            tip = v <= -0.2 and abs(u - sway * (-0.2 - v)) <= (v + 1.1) * 0.8
            return (body or tip) and not ((i + ph) % 2 == 0 and v > 0.6)     # the ragged hem

        rows = []
        cover = {} if S >= 16 else None       # very big spirits: anti-aliased outline (4x4 samples a pixel)
        for j in range(S):
            v = (j + 0.5) / S * 2 - 1
            row = ""
            for i in range(S):
                u = (i + 0.5) / S * 2 - 1
                inside_ = ins(i, u, v)
                row += "#" if inside_ else "."
                if cover is not None:
                    k = sum(ins(i, (i + (a + 0.5) / 4) / S * 2 - 1, (j + (b + 0.5) / 4) / S * 2 - 1)
                            for a in range(4) for b in range(4)) / 16
                    if 0 < k < 1:
                        cover[i, j] = k
            rows.append(row)
    pts = [(i, j) for j, r in enumerate(rows) for i, ch in enumerate(r) if ch == "#"]
    if S >= 16:
        pts += [p for p in cover if p not in set(pts)]
    else:
        cover = None
    got = (pts, {(i, j) for j, r in enumerate(rows) for i, ch in enumerate(r) if ch == "#"}, cover or {})
    _MASK[key] = got
    return got


def draw_spirit(cv, cx, cy, S, color, look, ph, mode="normal", vis=1.0, clip=None, ground=(10, 10, 20)):
    """mode: normal, pale, pale2 (flicker), eyes (only the eyes, on their way home)."""
    x0c, y0c, x1c, y1c = clip or (0, 0, cv.W, cv.H)
    left, top = int(round(cx - S / 2)), int(round(cy - S / 2))
    pts, inside, cover = spirit_mask(S, ph % 4)
    px = cv.px
    if mode != "eyes":
        body = PALE if mode == "pale" else PALE2 if mode == "pale2" else color
        for i, j in pts:
            x, y = left + i, top + j
            if x0c <= x < x1c and y0c <= y < y1c:
                k = 1.22 - 0.5 * j / S
                if (i - 1, j) not in inside or (i + 1, j) not in inside or (i, j + 1) not in inside:
                    k *= 0.78
                c = shade(body, k)
                if vis < 1:
                    c = mix(ground, c, vis)
                a = cover.get((i, j), 1.0) if cover else 1.0
                px[y][x] = c if a >= 1 else mix(px[y][x], c, a)
    dx, dy = DIRS[look if look is not None else 2]
    scared = mode in ("pale", "pale2")
    white = (246, 246, 255) if not scared else (60, 54, 96)
    pupil = (30, 30, 70)
    if vis < 1 and mode != "eyes":
        white = mix((90, 90, 120), white, max(0.35, vis))
    eyes = []
    if S <= 2:
        eyes = [((0 if dx < 0 else S - 1), 0, white)]
    elif S == 3:
        ex, ey = 1 + dx, 1 + dy
        if (ex, ey) not in inside:
            ex, ey = 1, 1
        eyes = [(ex, ey, white)]
    elif S == 4:
        ey = 1
        eyes = [(clamp(1 + dx, 0, 3), ey, white), (clamp(2 + dx, 0, 3), ey, white)]
    else:
        ew = S // 6 if S >= 16 else 2 if S >= 8 else 1      # very big spirits (the interlude): bigger eyes
        eh = ew
        ey = int(S * 0.52) - eh // 2 + (dy if ew == 1 else 0)
        for exc in (S * 0.32, S * 0.68):
            ex = int(exc - ew / 2 + 0.5) + (dx if ew == 1 else 0)
            for a in range(ew):
                for b in range(eh):
                    eyes.append((ex + a, ey + b, white))
            if ew == 2 and not scared:
                ppx = ex + (1 if dx > 0 else 0 if dx < 0 else (1 if exc > S / 2 else 0))
                ppy = ey + (1 if dy >= 0 else 0)
                eyes.append((ppx, ppy, pupil))
            elif ew > 2 and not scared:     # a pupil half the eye's size, looking the way the spirit goes
                pw = ew // 2
                ppx = ex + (ew - pw if dx > 0 else 0 if dx < 0 else (ew - pw if exc > S / 2 else 0))
                ppy = ey + (eh - pw if dy >= 0 else 0)
                for a in range(pw):
                    for b in range(pw):
                        eyes.append((ppx + a, ppy + b, pupil))
        if scared and S >= 8:   # a wobbly mouth
            my = int(S * 0.72)
            th = 1 if S < 16 else S // 12
            for i in range(int(S * 0.25) + 1, int(S * 0.75)):
                for k in range(th):
                    eyes.append((i, my + ((i // th) % 2) * th + k, (60, 54, 96)))
    for i, j, c in eyes:
        x, y = left + i, top + j
        if x0c <= x < x1c and y0c <= y < y1c:
            px[y][x] = c


def draw_treat(cv, cx, cy, T, kind, t, clip=None):
    bob = math.sin(t * 4) * T * 0.06
    s = T * 1.15
    for dx, dy, r, c in kind[2]:
        disc(cv, cx + dx * s, cy + dy * s + bob, max(0.6, r * s), c, clip=clip)


_FOGPIX = {}


def draw_fog(cv, g, T, ox, oy, clip):
    """Fog density is worked out per tile, then spread smoothly over the pixels (bilinear between tile centres)."""
    D = [[0.0] * (MW + 2) for _ in range(MH + 2)]        # padded by one tile on every side
    for f in g.fog:
        fx, fy, fr = f[0], f[1] + 0.8 * math.sin(f[4] * 0.6), f[2]
        for ty in range(max(0, int(fy - fr)), min(MH, int(fy + fr) + 2)):
            row = D[ty + 1]
            for tx in range(max(0, int(fx - fr)), min(MW, int(fx + fr) + 2)):
                d = math.hypot(tx - fx, ty - fy) / fr
                if d < 1:
                    a = 1 - d
                    a = a * a * (3 - 2 * a) * 0.9
                    if a > row[tx + 1]:
                        row[tx + 1] = a
    w = g.wisp
    for ty in range(max(0, int(w.y) - 4), min(MH, int(w.y) + 5)):
        for tx in range(int(w.x) - 4, int(w.x) + 5):
            if 0 <= tx < MW:
                D[ty + 1][tx + 1] *= clamp((math.hypot(tx - w.x, ty - w.y) - 0.8) / 2.4, 0.0, 1.0)
    offs = _FOGPIX.get(T)
    if offs is None:   # per pixel of a tile: which tile centres around it, and how much of each
        offs = []
        for yy in range(T):
            v = (yy + 0.5) / T - 0.5
            dj, wv = (-1, 1 + v) if v < 0 else (0, v)
            for xx in range(T):
                u = (xx + 0.5) / T - 0.5
                di, wu = (-1, 1 + u) if u < 0 else (0, u)
                offs.append((xx, yy, di, dj, (1 - wu) * (1 - wv), wu * (1 - wv), (1 - wu) * wv, wu * wv))
        _FOGPIX[T] = offs
    px = cv.px
    fr_, fg_, fb_ = FOG
    cx0, cy0, cx1, cy1 = clip
    for ty in range(MH):
        r0, r1, r2 = D[ty], D[ty + 1], D[ty + 2]
        for tx in range(MW):
            if max(r0[tx], r0[tx + 1], r0[tx + 2], r1[tx], r1[tx + 1], r1[tx + 2], r2[tx], r2[tx + 1], r2[tx + 2]) < 0.03:
                continue
            x0, y0 = ox + tx * T, oy + ty * T
            for xx, yy, di, dj, a00, a10, a01, a11 in offs:
                x, y = x0 + xx, y0 + yy
                if cx0 <= x < cx1 and cy0 <= y < cy1:
                    i, j = tx + 1 + di, ty + 1 + dj
                    b = D[j][i] * a00 + D[j][i + 1] * a10 + D[j + 1][i] * a01 + D[j + 1][i + 1] * a11
                    if b > 0.02:
                        c = px[y][x]
                        px[y][x] = (c[0] + int((fr_ - c[0]) * b), c[1] + int((fg_ - c[1]) * b), c[2] + int((fb_ - c[2]) * b))


def sprite_size(T):
    return 2 if T <= 1 else int(T * 1.3) + 1


def render(g, cols, rows, hud=True):
    if g.state == "interlude":
        return render_interlude(g, cols, rows)
    T, ox, oy, foot = layout(cols, rows, hud)
    m = g.maze
    base, lit, flash = layers(m, cols, rows, T, ox, oy)
    cv = Canvas(cols, rows)
    st = g.state
    flashing = st == "clear" and g.state_t < 1.8 and int(g.state_t / 0.2) % 2 == 0
    src = flash if flashing else base
    cv.px = [row[:] for row in src]
    W, H = cv.W, cv.H
    clip = (max(0, ox), max(0, oy), min(W, ox + MW * T), min(H, oy + MH * T))
    w = g.wisp
    wcx, wcy = ox + (w.x + 0.5) * T, oy + (w.y + 0.5) * T
    dark = "dark" in m.feat and not flashing
    R = (5.6 if "dark" in m.feat else 3.2) + (1.6 if g.fright_t > 0 else 0.0)
    k = 0.9 + 0.1 * math.sin(g.t * 11) * math.sin(g.t * 3.7)
    if st == "dying":
        k *= clamp((g.state_t - 0.6) / 1.4, 0, 1)
    elif st == "clear":
        R += 3 * (2.2 - g.state_t)
    elif st == "over":
        k = 0.0
    if not flashing and k > 0:
        apply_glow(cv.px, src, lit, int(wcx), int(wcy), glow_table(R * T + 1), k, *clip)

    def vis(x, y):
        if not dark:
            return 1.0
        dx = abs(x - w.x)
        dx = min(dx, MW - dx)
        return clamp((R - math.hypot(dx, y - w.y)) / (R * 0.5), 0.0, 1.0) * (k if st == "dying" else 1.0)

    dground = shade(m.ground, 0.17)
    # light motes and sun blossoms
    ms = 1 if T < 5 else 2
    mo = (T - ms) // 2
    mote = MOTE if T > 1 else mix(m.ground, MOTE, 0.5)     # tiny previews: motes fill whole tiles, keep them soft
    for (x, y) in g.motes:
        v = vis(x, y)
        if v > 0:
            c = mote if v >= 1 else mix(dground, mote, v)
            if T >= 6:      # big tiles: a round, softly edged mote instead of a square
                disc(cv, ox + (x + 0.5) * T, oy + (y + 0.5) * T, T * 0.13, c, edge=0.9, clip=clip)
            else:
                cv.rect(ox + x * T + mo, oy + y * T + mo, ms, ms, c)
    pulse = 0.5 + 0.5 * math.sin(g.t * 6)
    for (x, y) in g.power:
        v = vis(x, y)
        if dark:
            v = max(v, 0.25)                    # the blossoms glow faintly even in the dark
        c = mix(BLOSSOM[1], BLOSSOM[0], pulse)
        if v < 1:
            c = mix(dground, c, v)
        cx, cy = ox + (x + 0.5) * T, oy + (y + 0.5) * T
        if T <= 2:
            cv.rect(ox + x * T, oy + y * T, T, T, c)
        elif T == 3:
            for ddx, ddy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                cv.set(cx + ddx, cy + ddy, c if ddx or ddy else (255, 250, 220))
        else:
            r = T * (0.2 + 0.05 * pulse)
            for a in range(5):
                ang = g.t * 0.8 + a * 2 * math.pi / 5
                disc(cv, cx + math.cos(ang) * r, cy + math.sin(ang) * r, T * 0.17, c, clip=clip)
            disc(cv, cx, cy, T * 0.16, mix((255, 250, 220), c, 0.3 * (1 - v)), clip=clip)
    if g.treat and st in ("play", "freeze", "ready"):
        tx, ty = m.treat
        v = vis(tx, ty)
        if v > 0.2:
            draw_treat(cv, ox + (tx + 0.5) * T, oy + (ty + 0.5) * T, T, g.treat[1], g.t, clip)
    # the spirits
    S = sprite_size(T)
    hide = st in ("clear", "over") or (st == "dying" and g.state_t < 1.6)
    if not hide:
        for s in g.spirits:
            if st == "freeze" and g.freeze_pop and s is g.freeze_pop[0]:
                continue
            if s.state == "eyes" or s.state == "enter":
                mode = "eyes"
            elif s.fright:
                ft = g.fright_t
                mode = "pale2" if ft < 1.8 and int(ft / 0.2) % 2 == 0 else "pale"
            else:
                mode = "normal"
            sx, sy = ox + (s.x + 0.5) * T, oy + (s.y + 0.5) * T
            ph = int(g.t * 6 + s.i) % 4
            if s.state == "house" or s.state == "leave" or s.state == "enter":
                v = 1.0 if not dark else max(0.0, vis(s.x, s.y))
                draw_spirit(cv, sx, sy, S, s.color, s.look, ph, mode, vis=v, clip=clip, ground=dground)
            else:
                v = vis(s.x, s.y)
                draw_spirit(cv, sx, sy, S, s.color, s.look, ph, mode, vis=v, clip=clip, ground=dground)
                if sx > clip[2] - T or sx < clip[0] + T:      # half way through a tunnel: show both ends
                    sx2 = sx - MW * T if sx > clip[2] - T else sx + MW * T
                    draw_spirit(cv, sx2, sy, S, s.color, s.look, ph, mode, vis=v, clip=clip, ground=dground)
    # the wisp: a fading trail, then the flame
    if st != "over":
        scale = 1.0
        if st == "dying":
            e = 2.0 - g.state_t
            scale = 0.0 if e > 0.6 else (1 - e / 0.6) * (0.6 + 0.4 * abs(math.sin(e * 30)))
        elif st == "clear":
            scale = 1.0 + 0.25 * math.sin(g.t * 9)
        if T >= 3 and st == "play":
            n = len(w.trail)
            for i, (x, y) in enumerate(w.trail):
                a = (i + 1) / (n + 1) * 0.55
                px_, py_ = int(ox + (x + 0.5) * T), int(oy + (y + 0.5) * T)
                if clip[0] <= px_ < clip[2] and clip[1] <= py_ < clip[3]:
                    cv.px[py_][px_] = mix(cv.px[py_][px_], WISP_RIM, a)
        if scale > 0:
            draw_wisp(cv, wcx, wcy, T, g.t, scale, clip)
    # sparks
    for x, y, vx, vy, life, mx, _, c in g.particles:
        a = life / mx
        px_, py_ = int(ox + (x + 0.5) * T), int(oy + (y + 0.5) * T)
        if clip[0] <= px_ < clip[2] and clip[1] <= py_ < clip[3]:
            cv.px[py_][px_] = mix(cv.px[py_][px_], c, min(1.0, a * 1.4))
    # drifting fog: thick away from the wisp, thinning right around it
    if g.fog and not flashing:
        draw_fog(cv, g, T, ox, oy, clip)
    # text
    for txt, x, y, until, c in g.pops:
        col = int(ox + (x + 0.5) * T - len(txt) / 2)
        row = int(oy + (y + 0.5) * T) // 2
        cv.put(max(0, min(cols - len(txt), col)), row, txt, c, (12, 12, 24))
    mcol0, mwid = max(0, ox), min(cols, MW * T)
    if st == "ready":
        cv.center(int(oy + (m.home[1] + 0.5) * T) // 2, m.name, (200, 220, 255), (12, 12, 24), mcol0, mwid)
        cv.center(int(oy + (m.treat[1] + 0.5) * T) // 2, "READY", SCORE_C, (12, 12, 24), mcol0, mwid)
    if hud:
        cv.rect(0, 0, W, 2, HUD_BG)
        best = max(g.best, g.score)
        parts = [" SCORE %d" % g.score, "HI %d" % best]
        feat = ", ".join(FEAT_TEXT[f] for f in m.feat)
        for lv in ("LEVEL %d  %s%s" % (g.level, m.name, ("  - " + feat) if feat and st == "ready" else ""),
                   "LEVEL %d  %s" % (g.level, m.name), "LEVEL %d" % g.level):
            line = "   ".join(parts + [lv])
            if len(line) + 3 * 5 + 2 <= cols:
                break
        cv.put(0, 0, line, (220, 220, 236))
        cv.put(0, 0, parts[0], SCORE_C)
        reserve = g.lives - (0 if st == "over" else 1)
        for i in range(min(5, max(0, reserve))):
            x = W - 3 - i * 3
            cv.rect(x, 0, 2, 2, WISP_RIM)
            cv.set(x, 0, WISP_CORE)
    if foot:
        footer(cv, "arrows move   Esc / P pause   ? help")
    if g.paused:
        overlay(cv, HELP if g.help else PAUSE_LINES + ["", SND.label()])
    return cv


_LAWN = {}


def interlude_lawn(cv, m, lane, S, band):
    """The interlude's lawn in a big window: the hedge bands with the maze's leaf clumps and rim light (lit along
    the top, shaded along the bottom) and a bushy, softly edged outline; the lawn between them as in the maze.
    Drawn once per maze style and window size, then copied."""
    key = (m.idx, cv.W, cv.H)
    got = _LAWN.get(key)
    if got is None:
        if len(_LAWN) > 8:
            _LAWN.clear()
        got = _LAWN[key] = [r[:] for r in cv.px]
        _lawn(got, cv.W, cv.H, m, lane, S, band)
    cv.px = [r[:] for r in got]


def _lawn(px, W, H, m, lane, S, band):
    hedge, ground, speck = m.hedge, m.ground, m.speck
    for y in range(max(0, lane - S), min(H, lane + S)):
        px[y] = [shade(ground, 0.86 + 0.28 * hsh(x, y)) for x in range(W)]
    for top, bot in ((lane - S - band, lane - S), (lane + S, lane + S + band)):
        for x in range(W):
            # the outline bulges a little with the leaf clumps, so the band reads as a hedge, not a stripe
            bump = 0.9 * (0.5 + 0.5 * math.sin(x * 0.55 + hsh(x // 5, top, 9) * 3)) * min(1.0, band / 8)
            t, b = top - bump, bot + bump * 0.6
            for y in range(max(0, int(t) - 1), min(H, int(b) + 2)):
                cover = clamp(min(y + 1 - t, b - y), 0.0, 1.0)
                if cover <= 0:
                    continue
                n = leaves(x, y, hsh(x, y))
                c = shade(hedge, 0.74 + 0.5 * n)
                if speck and hsh(x, y, 3) < 0.05:
                    c = mix(c, speck, 0.8)
                if y < t + 1.6:
                    c = shade(shade(hedge, 0.74 + 0.5 * max(n, 0.5)), 1.45)
                elif y > b - 1.6:
                    c = shade(c, 0.55)
                px[y][x] = c if cover >= 1 else mix(px[y][x], c, cover)


def lawn_glow(cv, cx, cy, R, k, y0, y1):
    """The wisp's warm light on the lawn and the hedges around it (the maze's glow, worked out on the spot)."""
    if R < 1:
        return
    px, W = cv.px, cv.W
    for y in range(max(0, int(cy - R), y0), min(cv.H, int(cy + R) + 1, y1)):
        dy = y + 0.5 - cy
        row = px[y]
        for x in range(max(0, int(cx - R)), min(W, int(cx + R) + 1)):
            dx = x + 0.5 - cx
            d = math.sqrt(dx * dx + dy * dy)
            if d < R:
                w = (1 - d / R) ** 1.3 * k
                c = row[x]
                row[x] = mix(c, mix(shade(c, 1.9), WARM, 0.2), w)


def ground_shadow(cv, cx, cy, rx, ry):
    """A soft oval shadow on the ground."""
    px = cv.px
    for y in range(max(0, int(cy - ry - 2)), min(cv.H, int(cy + ry + 2))):
        v = (y + 0.5 - cy) / (ry + 1)
        row = px[y]
        for x in range(max(0, int(cx - rx - 2)), min(cv.W, int(cx + rx + 2))):
            u = (x + 0.5 - cx) / (rx + 1)
            d = u * u + v * v
            if d < 1:
                row[x] = mix(row[x], (4, 4, 10), 0.55 * (1 - d))


def render_interlude(g, cols, rows):
    """Every third maze: a short scene in the moonlight. The spirits chase Glimmer across the lawn, then
    a sun blossom opens and the chase runs the other way."""
    m = g.maze
    cv = Canvas(cols, rows)
    cv.px = sky(cols, rows * 2, 99)
    W, H = cv.W, cv.H
    S = max(3, min(W // 10, H // 5))
    fine = S > 14              # big windows: the scene keeps its size and gets the maze's finer drawing
    lane = H // 2
    band = max(2, S // 2)
    e = 7.0 - g.state_t
    ph = int(e * 6) % 4
    if not fine:
        for y0 in (lane - S - band, lane + S):
            for y in range(y0, y0 + band):
                for x in range(W):
                    if 0 <= y < H:
                        cv.px[y][x] = shade(m.hedge, 0.7 + 0.5 * hsh(x, y))
        for y in range(lane - S, lane + S):
            if 0 <= y < H:
                cv.px[y] = [shade(m.ground, 0.9 + 0.2 * hsh(x, y)) for x in range(W)]
    else:
        interlude_lawn(cv, m, lane, S, band)
        # where the wisp is, it lights the lawn and the hedges, as in the maze
        if e < 3.4:
            gx, gs = W + S - e * (W + 5 * S) / 3.2, 1.0
        elif e < 4.0:
            gx, gs = S, (e - 3.4) / 0.6
        else:
            gx, gs = -S + (e - 4.0) / 3.0 * (W + 6 * S), 1.0 + 0.3 * (e - 4.0) / 3.0
        lawn_glow(cv, gx, lane, S * 3.2 * gs, 0.6 + 0.08 * math.sin(e * 11), lane - S - band, lane + S + band)

    def shadow(x):             # a soft shadow on the lawn under a spirit (big windows)
        if fine:
            ground_shadow(cv, x, lane + S * 0.56, S * 0.42, S * 0.1)

    if e < 3.4:
        wx = W + S - e * (W + 5 * S) / 3.2
        draw_wisp(cv, wx, lane, S * 0.8, e)
        for n, i in enumerate((0, 1)):
            shadow(wx + (2.0 + 1.5 * n) * S)
            draw_spirit(cv, wx + (2.0 + 1.5 * n) * S, lane, S, SPIRITS[i][1], 1, ph + n)
    elif e < 4.0:
        u = (e - 3.4) / 0.6
        for a in range(5):
            ang = e * 2 + a * 2 * math.pi / 5
            disc(cv, S + math.cos(ang) * S * 0.6 * u, lane + math.sin(ang) * S * 0.6 * u, S * 0.4 * u + 0.6, BLOSSOM[0],
                 edge=1.0 if fine else 0.0)
        disc(cv, S, lane, S * 0.3 * u + 0.6, (255, 250, 220), edge=1.0 if fine else 0.0)
    else:
        u = (e - 4.0) / 3.0
        wx = -S + u * (W + 6 * S)
        draw_wisp(cv, wx, lane, S * (0.8 + 0.3 * u), e)
        for n in range(2):
            sx = wx + (2.6 + 1.6 * n) * S * (1 - 0.35 * u) + u * S
            shadow(sx)
            draw_spirit(cv, sx, lane, S, SPIRITS[n][1], 3, ph + n, "pale2" if int(e * 5) % 2 else "pale")
    cv.center(max(0, (lane - S - band) // 2 - 2), "  ~ interlude ~  ", (230, 220, 255), HUD_BG)
    cv.center(min(rows - 1, (lane + S + band) // 2 + 2), "  maze %d cleared: the night grows deeper  " % g.level,
              (190, 196, 224), HUD_BG)
    if g.paused:
        overlay(cv, HELP if g.help else PAUSE_LINES + ["", SND.label()])
    return cv


def render_over(g, cv, record, auto=False):
    lines = ["GAME OVER", "", "score %d" % g.score, "level %d   (%s)" % (g.level, g.maze.name)]
    if record:
        lines += ["", "** NEW RECORD **"]
    lines += ["", "auto mode: a new round starts" if auto else "Enter: again   Esc / Q: menu"]
    w = max(len(l) for l in lines) + 4
    x, y = max(0, (cv.cols - w) // 2), max(0, cv.rows // 2 - len(lines) // 2 - 1)
    cv.frame(x - 1, y * 2 - 1, w + 2, (len(lines) + 2) * 2 + 2, SCORE_C if record else (200, 120, 90))
    cv.box(x, y, [l.center(w - 4) for l in lines], (240, 240, 246), (24, 22, 44))


class TitleDemo:
    """An autopiloted round behind the title screen (and in the launcher preview), without sound."""

    def __init__(self, maze=None):
        self.k = random.randrange(len(MAZES)) if maze is None else maze
        self.new()

    def new(self):
        self.g = Game(start=self.k, auto=True, sound=False, seed=self.k)
        self.k = (self.k + 1) % len(MAZES)
        self.age = 0.0

    def scene(self, cols, rows, dt):
        g = self.g
        g.update(min(0.1, max(0.0, dt)))
        self.age += dt
        if g.state == "over" or g.level > 1 or self.age > 150:
            self.new()
        return render(self.g, cols, rows, hud=False)


class AutoRun:
    """Auto mode: the real game (real levels, HUD, sound and lives) played by a Pilot. After a game over the
    result stays for a few seconds, then a new round starts from the same maze. Scores are never recorded."""
    STEP = 1 / 60
    OVER_SHOW = 3.0

    def __init__(self, start, sound=True, seed=None):
        self.start, self.sound, self.seed = start, sound, seed
        self.auto = AutoMode()
        self.rounds = 0
        self.new()

    def new(self):
        self.rounds += 1
        seed = None if self.seed is None else self.seed + self.rounds
        self.g = Game(self.start, auto=True, sound=self.sound, seed=seed)
        self.g.pilot = Pilot(seed)
        self.g.best = load_scores().get(GAME, {}).get("score") or 0     # shown, never written
        self.over_t = 0.0

    def key(self, k):
        """'stop' when the viewer ends auto mode."""
        a = self.auto.key(k)
        if a == "sound" and SND.toggle():
            SND.play("sound_on")
        return a

    def frame(self, dt, cols, rows, draw=True):
        g = self.g
        if g.state == "over":
            self.over_t += self.auto.scale(dt) / max(1.0, self.auto.speed)     # real seconds, unless paused
            if self.over_t >= self.OVER_SHOW:
                self.new()
                g = self.g
        else:
            for _ in range(self.auto.steps(dt, self.STEP)):
                g.step(self.STEP)
                if g.state == "over":
                    break
        if not draw:
            return None
        cv = render(g, cols, rows)
        if g.state == "over":
            render_over(g, cv, False, auto=True)
        self.auto.banner(cv, extra="round %d" % self.rounds)
        return cv


def render_menu(demo, cols, rows, dt, start, help_=False, sel=0):
    cv = demo.scene(cols, rows, dt)
    rec = load_scores().get(GAME, {})
    best = None
    if rec.get("score"):
        best = "best score %d   furthest level %d" % (rec.get("score", 0), rec.get("level", 1))
    name = MAZES[start][0]
    feat = ", ".join(FEAT_TEXT[f] for f in STYLE[name]["feat"]) or "a quiet lawn"
    title_screen(cv, "GLIMMER", "a will-o'-wisp in a hedge maze at night", ["Play", AUTO_LABEL], sel, best,
                 extra=["", "start maze  < %d %s >" % (start + 1, name), "             %s" % feat],
                 keys="Up/Down choose   Left/Right maze   Enter start   M %s   ? help   Esc back" % SND.label().lower(),
                 help_lines=HELP, show_help=help_, dim=0.45)
    return cv


# =============================================================================================
# Main loop
# =============================================================================================
def main():
    with Terminal() as term:
        demo = TitleDemo()
        start = 0
        sel = 0
        help_ = False
        while True:
            # title
            last = time.time()
            go = False
            while not go:
                now = time.time()
                dt, last = min(0.1, now - last), now
                cols, rows = term.size()
                term.write(render_menu(demo, cols, rows, dt, start, help_, sel).emit())
                for k in term.keys(1 / 30):
                    if help_:            # any key closes the help
                        help_ = False
                        continue
                    if k == "?":
                        help_ = True
                    elif k in ("q", "esc"):
                        return
                    elif k in ("up", "w", "down", "s"):
                        sel = 1 - sel
                        SND.play("menu")
                    elif k in ("left", "a"):
                        start = (start - 1) % len(MAZES)
                        SND.play("menu")
                    elif k in ("right", "d"):
                        start = (start + 1) % len(MAZES)
                        SND.play("menu")
                    elif k == "m":
                        if SND.toggle():
                            SND.play("sound_on")
                    elif k in ("enter", " "):
                        SND.play("go")
                        go = True
            if sel == 1:
                run_auto(term, start)
                continue
            # play
            while True:
                g = Game(start)
                last = time.time()
                record = None
                back = again = False
                while True:
                    now = time.time()
                    g.update(min(0.1, now - last))
                    last = now
                    for k in term.keys(0):
                        if g.state == "over":
                            if k in ("q", "esc"):
                                back = True
                            elif record is not None and k in ("enter", " "):
                                again = True
                            continue
                        a = shared_key(k, g.paused)
                        if a == "pause":
                            g.paused = True
                            SND.play("pause")
                        elif a == "resume":
                            g.paused = g.help = False
                        elif a == "quit":
                            back = True
                        elif a == "help":
                            g.help = not g.help
                            g.paused = True
                        elif a == "sound":
                            if SND.toggle():
                                SND.play("sound_on")
                        elif a is None:
                            if g.state == "interlude" and k in ("enter", " "):
                                g.state_t = 0.0          # skip the interlude
                            g.key(k)
                    if back or again:
                        break
                    if g.state == "over" and record is None:
                        record = submit(GAME, "score", g.score)
                        submit(GAME, "level", g.level)
                    cols, rows = term.size()
                    if cols < 60 or rows < 22:
                        term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (60x22).")
                        time.sleep(0.2)
                        continue
                    cv = render(g, cols, rows)
                    if g.state == "over":
                        render_over(g, cv, record)
                    term.write(cv.emit())
                    time.sleep(max(0, 1 / 30 - (time.time() - now)))
                if back:
                    break


def run_auto(term, start):
    """Auto mode until the viewer stops it (Esc / Q)."""
    run = AutoRun(start)
    last = time.time()
    while True:
        now = time.time()
        dt, last = min(0.1, now - last), now
        for k in term.keys(0):
            if run.key(k) == "stop":
                return
        cols, rows = term.size()
        if cols < 60 or rows < 22:
            term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (60x22).")
            time.sleep(0.2)
            continue
        term.write(run.frame(dt, cols, rows).emit())
        time.sleep(max(0, 1 / 30 - (time.time() - now)))


# =============================================================================================
# Self-test: python3 glimmer.py --selftest
# =============================================================================================
def selftest():
    t0 = time.time()
    # every maze keeps the rules: symmetric, closed, tunnels on both sides, no dead ends, every mote reachable
    motes = []
    for i in range(len(MAZES)):
        m = Maze(i)
        errs = validate(m)
        assert not errs, "%s: %s" % (m.name, "; ".join(errs[:5]))
        motes.append(len(m.motes))
    assert len(MAZES) >= 8
    assert any(Maze(i).gate for i in range(len(MAZES))), "no maze has gates"
    assert any("dark" in Maze(i).feat for i in range(len(MAZES))) and any("fog" in Maze(i).feat for i in range(len(MAZES)))
    # a remembered turn: press Up in a corridor, the wisp turns at the first opening
    g = Game(0, sound=False, seed=1)
    g.state = "play"
    w = g.wisp
    w.x, w.y, w.d = 7.0, 19.0, 3
    g.key("up")
    for _ in range(40):
        g.step(1 / 60)
        if w.d == 0:
            break
    assert w.d == 0 and g.maze.can(int(round(w.x)), 19, 0), "the buffered turn was not taken"
    # turning round mid-tile, and the tunnel wraps
    g = Game(0, sound=False, seed=2)
    g.state = "play"
    g.spirits = []
    w = g.wisp
    w.x, w.y, w.d = 1.3, 10.0, 1
    w.want = 1
    for _ in range(30):
        g.step(1 / 60)
    assert w.x > 20, "the tunnel did not wrap (x=%.2f)" % w.x
    w.want = 3
    x0 = w.x
    g.step(1 / 60)
    assert w.d == 3 and w.x > x0, "turning round failed"
    # one-way gates hold: the Briar Knot gate only lets you pass towards the middle
    m = Maze(5)
    (gx, gy), gd = next(iter(m.gate.items()))
    assert m.can(gx - DIRS[gd][0], gy - DIRS[gd][1], gd) and not m.can(gx + DIRS[gd][0], gy + DIRS[gd][1], OPP[gd])
    # a sun blossom, then a caught spirit
    g = Game(0, sound=False, seed=3)
    g.state = "play"
    w = g.wisp
    px, py = sorted(g.power)[0]
    w.x, w.y, w.d = float(px), float(py) - 0.5, 2
    for _ in range(20):
        g.step(1 / 60)
    assert g.fright_t > 0 and g.stats["blossoms"] == 1, "the blossom did nothing"
    s = g.spirits[0]
    assert s.fright
    s.x, s.y = float(round(w.x)), float(round(w.y))
    sc = g.score
    g.step(1 / 60)
    assert s.state == "eyes" and g.score >= sc + 200 and g.state == "freeze", "catching a pale spirit failed"
    for _ in range(600):
        g.step(1 / 60)
        if s.state == "roam":
            break
    assert s.state in ("leave", "roam", "house") and not s.fright, "the eyes did not get home (%s)" % s.state
    # touching a spirit that is not pale costs a wisp
    g = Game(0, sound=False, seed=4)
    g.state = "play"
    s = g.spirits[0]
    s.x, s.y = g.wisp.x, g.wisp.y
    g.step(1 / 60)
    assert g.state == "dying"
    for _ in range(200):
        g.step(1 / 60)
    assert g.lives == 2 and g.state in ("ready", "play")
    # the autopilot plays several mazes with the spirits on (unlimited wisps for the test)
    t1 = time.time()
    g = Game(0, auto=True, sound=False, seed=5)
    g.lives = 999
    seen_states = set()
    steps = 0
    while g.stats["cleared"] < 4 and steps < 30 * 900:
        g.update(1 / 30)
        seen_states.add(g.state)
        steps += 1
    st = g.stats
    assert st["cleared"] >= 4, "the bot cleared only %d mazes (%s)" % (st["cleared"], st)
    assert st["blossoms"] >= 4 and st["motes"] > 600, st
    assert "interlude" in seen_states, "no interlude after the third maze"
    bot_time = time.time() - t1
    # frames at many sizes and in every state
    t2 = time.time()
    frames = 0
    for cols, rows in ((60, 22), (70, 22), (120, 40), (200, 60)):
        for idx in range(len(MAZES)):
            g = Game(idx, sound=False, seed=idx)
            g.best = 12345
            for _ in range(20):
                g.update(1 / 30)
            render(g, cols, rows).emit(True)
            g.state = "play"
            g.auto = True
            for _ in range(45):
                g.update(1 / 30)
            g.fright_t = 1.0
            g.spirits[1].fright = True
            g.spirits[2].state = "eyes"
            g.treat = (g.play_t + 5, g.P["treat"])
            render(g, cols, rows).emit(idx % 2 == 0)
            frames += 2
        for state, tt in (("dying", 1.9), ("dying", 1.0), ("clear", 1.5), ("clear", 1.3), ("interlude", 5.0),
                          ("interlude", 3.7), ("interlude", 1.0), ("over", 0.0)):
            g.state, g.state_t = state, tt
            cv = render(g, cols, rows)
            if state == "over":
                render_over(g, cv, True)
            cv.emit(True)
            frames += 1
        g.state = "play"
        g.paused = True
        render(g, cols, rows).emit(True)
        g.help = True
        render(g, cols, rows).emit(False)
        demo = TitleDemo(3)
        for i in range(30):
            render_menu(demo, cols, rows, 0.1, i % len(MAZES), help_=i == 29).emit(True)
        frames += 32
    for cols, rows in ((36, 9), (44, 12), (27, 11), (20, 6)):   # launcher previews and silly sizes
        demo = TitleDemo(1)
        for _ in range(10):
            demo.scene(cols, rows, 0.1).emit(True)
    for S in range(1, 16):   # every sprite size draws
        cv = Canvas(20, 10)
        for mode in ("normal", "pale", "pale2", "eyes"):
            draw_spirit(cv, 10, 10, S, (200, 100, 100), S % 4, S, mode)
    render_time = time.time() - t2
    # how long a frame takes
    timing = []
    for cols, rows in ((70, 22), (120, 40), (200, 60)):
        g = Game(2, auto=True, sound=False, seed=9)
        g.best = 0
        for _ in range(120):
            g.update(1 / 30)
        render(g, cols, rows)
        t = time.perf_counter()
        for _ in range(15):
            g.update(1 / 30)
            render(g, cols, rows).emit(True)
        timing.append("%dx%d %.1f ms" % (cols, rows, (time.perf_counter() - t) / 15 * 1000))
    # auto mode: the real game (3 wisps, no help) at x8 for a while; pause, speed and stop work; no score is kept
    t3 = time.time()
    submitted = []
    real_submit = globals()["submit"]
    globals()["submit"] = lambda *a, **k: submitted.append(a)
    try:
        run = AutoRun(0, sound=False, seed=11)
        assert run.g.lives == 3 and run.g.pilot is not None
        run.key(" ")
        lv = (run.g.level, run.g.score, run.g.wisp.x)
        for _ in range(30):
            run.frame(1 / 30, 70, 22, draw=False)
        assert (run.g.level, run.g.score, run.g.wisp.x) == lv, "auto mode ran on while paused"
        run.key(" ")
        for _ in range(5):
            run.key("+")
        assert run.auto.speed == 8.0
        auto_secs, auto_levels, auto_scores = 40, [], []
        for i in range(auto_secs * 30):
            g0 = run.g
            cv = run.frame(1 / 30, 70 + i % 3 * 25, 22 + i % 2 * 10, draw=i % 20 == 0)
            if run.g is not g0:
                auto_levels.append(g0.level)
                auto_scores.append(g0.score)
        auto_levels.append(run.g.level)
        auto_scores.append(run.g.score)
        assert run.key("esc") == "stop"
        assert not submitted, "auto mode submitted a score"
    finally:
        globals()["submit"] = real_submit
    auto_time = time.time() - t3
    print("Self-test ok: %d mazes valid (%s motes each, symmetric, no dead ends, every tile reachable both ways); "
          "buffered turns, reversing, tunnel wrap, gates, blossom, catching and dying work; the autopilot cleared "
          "%d mazes in %.0f s of play (%d motes, %d blossoms, %d spirits caught, %d treats, %d wisps lost) in %.1fs; "
          "%d frames rendered in %.1fs; frame incl. update: %s; auto mode %d s at x8: %d round(s), levels %s, "
          "scores %s, nothing recorded (%.1fs) (total %.1fs)"
          % (len(MAZES), "/".join(map(str, motes)), st["cleared"], steps / 30, st["motes"], st["blossoms"],
             st["spirits"], st["treats"], st["deaths"], bot_time, frames, render_time, ", ".join(timing),
             auto_secs, run.rounds, auto_levels, auto_scores, auto_time, time.time() - t0))


def screenshot(cols=100, rows=32, maze=0, seed=1, secs=26.0):
    """README picture: real play (the auto-mode Pilot) with a fixed seed, at a good moment, HUD and all.
    Moonlit Lawn, seed 1, 26 s in: all four spirits roaming in colour, a fresh +100, a third of the lawn eaten. The maze is
    27x21 tiles, one pixel row short of 3-pixel tiles at 32 rows, so the frame is drawn one text row
    taller and the empty last row (and the outer hedge's bottom pixel line) is cut off."""
    g = Game(maze, auto=True, sound=False, seed=seed)
    g.pilot = Pilot(seed)
    for _ in range(int(secs * 60)):
        g.step(1 / 60)
    T = layout(cols, rows)[0]
    extra = 1 if layout(cols, rows + 1)[0] > T else 0
    cv = render(g, cols, rows + extra)
    if extra:
        out = Canvas(cols, rows)
        out.px = cv.px[:rows * 2]
        out.text = {k: v for k, v in cv.text.items() if k[1] < rows}
        cv = out
    return cv


def dump(idx=0, cols=70, rows=22, secs=3.0):
    """--dump [maze] [cols] [rows] [seconds]: print one frame of the autopilot as plain text (for checking)."""
    g = Game(idx, auto=True, sound=False, seed=1)
    g.best = 0
    for _ in range(int(secs * 30)):
        g.update(1 / 30)
    sys.stdout.write(render(g, cols, rows).emit(True) + "\x1b[0m\n")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--dump" in sys.argv:
        a = [float(x) for x in sys.argv[sys.argv.index("--dump") + 1:]]
        dump(*([int(v) for v in a[:3]] + a[3:4]))
    else:
        main()
