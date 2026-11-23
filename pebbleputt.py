#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""PEBBLEPUTT - minigolf on three odd little courses.

Putt a painted pebble round three courses of nine holes, seen from above: Willow Meadow (log rails, ponds, mill
sails, toadstool bumpers, rabbit burrows), Rimewater (ice that never lets go, snowdrifts, meltwater crevasses,
sliding ice gates, frost portals, ice ramps) and the Copperworks at night (steel plates, conveyor belts, gear
arms, pistons, pipes, spring bumpers and pools of glowing slag). Hills and slopes bend every putt; water costs a
stroke and puts the pebble back. Aim finely, set the power with the swing meter (or a preset), and sink the pebble
- it only drops when it is slow enough over the cup. Solo, or two to four players at one keyboard; scorecard with
par, birdies and bogeys; a best round for every course. The auto-mode caddie plans each putt by playing it through
the game's own physics.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
In terminals with the kitty keyboard protocol (kitty, WezTerm, Ghostty, recent iTerm2) Space can be held and
released to strike; everywhere else press Space twice (start the meter, strike).
Run:        python3 pebbleputt.py
Auto mode:  python3 pebbleputt.py --auto
Self-test:  python3 pebbleputt.py --selftest
"""
import heapq
import math
import random
import sys
import time

from arcadekit import (ACCENTS, AUTO_LABEL, PAUSE_LINES, AutoMode, Canvas, HeldKeys, KeyTerminal, clamp, load_scores,
                       mix, overlay, shade, shared_key, submit, title_screen)
from arcadesound import Sound

GAME = "pebbleputt"
NAME = "PEBBLEPUTT"
TAGLINE = "minigolf on three odd little courses"
ACCENTS.setdefault(NAME, ((255, 196, 150), (70, 185, 110)))
TAU = 2 * math.pi

# =============================================================================================
# World units: every hole is FW x FH, y grows downwards. The physics never depends on the window.
# =============================================================================================
FW, FH = 40.0, 24.0
BALL_R = 0.42
CUP_R = 0.7
WT = 0.27                      # half thickness of a rail
MT = 0.30                      # half thickness of a moving arm / gate
PORTAL_R = 0.72
DT = 1 / 60                    # physics tick
SUBD = 0.11                    # the pebble moves at most this far per sub-step (no tunnelling)
VMAX = 24.0                    # strike speed at 100 % power
VSINK = 4.0                    # faster than this the pebble lips out over the cup
VSTOP = 0.09
DRAG = 0.10                    # rolling drag on top of the surface friction (per second)
G_AIR = 30.0                   # gravity in flight (units / s^2)
JUMP_K = 0.5                   # take-off: vertical speed = JUMP_K x speed along the ramp
BUMP_KICK = 9.0
MAX_STROKES = 10               # after this many the pebble is picked up
SHOT_T = 30.0                  # a putt ends after this long, wherever the pebble is
SWING_T = 1.7                  # the swing meter goes 0 -> 100 % -> 0 in twice this
LEAD = 1.5                     # the caddie plans a putt for this far ahead (moving obstacles)
GRID = 4                       # surface cells per unit
OUT, BASE, SAND, WATER, ICE, JUMP, BELT = range(7)
WHITE = (255, 255, 255)

PLAYERS = [("CORAL", (255, 122, 92)), ("SKY", (86, 178, 255)), ("GOLD", (250, 206, 70)), ("PLUM", (196, 128, 255))]


# --- shape helpers for the course data -------------------------------------------------------------
def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def P(*pts):
    return ("p", list(pts))


def Rz(x0, y0, x1, y1):
    return ("p", rect(x0, y0, x1, y1))


def C(x, y, r):
    return ("c", x, y, r)


def arc(cx, cy, r, a0, a1, n):
    """Points on a circle from angle a0 to a1 (degrees, y down), n steps."""
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
            for i in range(n + 1)]


def arena(cx, cy, r, y0, y1, x_in, n=18):
    """A round room with an entrance corridor from the left between y0 and y1 (starting at x_in)."""
    a0 = 180 + math.degrees(math.asin((cy - y0) / r))
    a1 = 180 - math.degrees(math.asin((y1 - cy) / r)) + 360
    pts = arc(cx, cy, r, a0, a1, n)
    return [(x_in, y0)] + pts + [(x_in, y1)]


# =============================================================================================
# The courses. A hole: green (one or more polygons, their edges are rails), extra walls, blocks (solid
# polygons), posts and bumpers (x, y, r), zones painted in order (later ones win), rotors (cx, cy, length,
# arms, rad/s, inner radius), gates (x1, y1, x2, y2, dx, dy, period s, phase 0..1: the segment slides by
# (dx, dy) and back) and portals (x, y, exit x, exit y, exit heading in degrees or None: keep the heading).
# Zones: ("sand"|"water"|"ice"|"base", shape), ("slope", shape, ax, ay), ("hill"|"bowl", x, y, r, k),
# ("jump", shape, heading), ("belt", shape, ax, ay).
# =============================================================================================
def bridge(cx, cy, ang, r0, r1, hw):
    """A plank across a ring: a rectangle along the radius at ang degrees, from r0 to r1, half width hw."""
    a = math.radians(ang)
    ux, uy, px, py = math.cos(a), math.sin(a), -math.sin(a), math.cos(a)
    return ("p", [(cx + ux * r + px * w, cy + uy * r + py * w) for r, w in ((r0, -hw), (r1, -hw), (r1, hw), (r0, hw))])


def hole(name, par, tee, cup, green, **kw):
    d = dict(name=name, par=par, tee=tee, cup=cup, green=green if isinstance(green[0], list) else [green])
    for k in ("walls", "blocks", "posts", "bumpers", "zones", "rotors", "gates", "portals"):
        d[k] = kw.get(k, [])
    return d


MEADOW = [
    hole("Daisy Lane", 2, (6, 12), (30, 11), [(3, 10), (5, 8), (37, 8), (37, 16), (5, 16), (3, 14)],
         posts=[(19, 12, 1.0)], zones=[("sand", C(25, 14.6, 1.2)), ("sand", Rz(33.5, 8, 37, 16))]),
    hole("Crooked Fence", 2, (7, 6), (33, 17.5), [(3, 3), (11, 3), (11, 14), (37, 14), (37, 21), (7, 21), (3, 17)],
         posts=[(17, 19, 0.8)], zones=[("sand", C(25, 20, 1.4)), ("slope", Rz(3, 3, 11, 11), 0, 0.9)]),
    hole("Mill Sails", 3, (6, 12), (33, 12), rect(3, 7, 37, 17),
         walls=[(14, 7, 17.2, 10.6), (14, 17, 17.2, 13.4)], rotors=[(21, 12, 3.1, 4, 1.3, 0.6)],
         zones=[("sand", C(35, 8.6, 1.2)), ("sand", C(35, 15.4, 1.2))]),
    hole("Pond Hop", 2, (6, 10), (31, 9), rect(3, 4, 37, 20),
         zones=[("water", P((17, 4), (23.5, 4), (23.5, 14.2), (20.3, 15.4), (17, 14.2))),
                ("jump", Rz(11, 8.5, 14, 11.5), 0), ("slope", Rz(24, 15, 37, 20), 0, -0.8)],
         posts=[(29, 16.5, 0.7)]),
    hole("Rabbit Run", 3, (7.5, 5.5), (32.5, 6), [(3, 3), (12, 3), (12, 15), (28, 15), (28, 3), (37, 3), (37, 21), (3, 21)],
         portals=[(7.5, 12.5, 31, 17.5, 0)], bumpers=[(17, 18, 0.9), (23, 18, 0.9)],
         zones=[("sand", C(20, 20.3, 1.0))]),
    hole("Toadstool Ring", 2, (6, 12), (27, 12), [(3, 5), (31, 5), (37, 9), (37, 15), (31, 19), (3, 19)],
         bumpers=[(27 + 4.2 * math.cos(math.radians(a)), 12 + 4.2 * math.sin(math.radians(a)), 0.9)
                  for a in (0, 60, 120, 240, 300)],
         zones=[("hill", 27, 12, 2.7, 3.2)]),
    hole("Molehill", 2, (6, 18), (34, 6), [(3, 6), (6, 3), (37, 3), (37, 18), (34, 21), (3, 21)],
         zones=[("hill", 19, 12, 6.5, 6.0), ("sand", C(28, 4.4, 1.2)), ("sand", C(9, 9, 1.1))]),
    hole("Sluice Gate", 3, (7, 6.5), (33, 6.5), rect(3, 4, 37, 20),
         walls=[(20, 4, 20, 10.4), (20, 13.6, 20, 20)], gates=[(20, 10.4, 20, 13.6, 0, -3.2, 3.6, 0)],
         zones=[("slope", Rz(20, 4, 37, 15), 0, 0.8), ("water", P((25, 16), (37, 16), (37, 20), (25, 20))),
                ("sand", C(11, 16.5, 1.3))]),
    hole("Old Willow", 4, (6, 6), (6.5, 18), [(3, 3), (37, 3), (37, 21), (3, 21), (3, 15), (30, 15), (30, 9), (3, 9)],
         posts=[(17, 6, 1.1)], rotors=[(33.5, 12, 2.0, 3, -1.1, 0.5)],
         zones=[("water", C(19, 19.3, 2.0)), ("slope", Rz(3, 15, 24, 21), -0.9, 0), ("sand", C(25, 4.5, 1.2))]),
]

FROST = [
    hole("First Frost", 2, (6, 12), (32, 12), [(3, 9), (4, 8), (36, 8), (37, 9), (37, 15), (36, 16), (4, 16), (3, 15)],
         posts=[(19, 12, 0.8)], zones=[("ice", Rz(11, 8, 27, 16)), ("sand", Rz(35, 8, 37, 16))]),
    hole("Glacier Bend", 2, (6, 6), (32, 17), [(3, 3), (14, 3), (37, 14), (37, 21), (25, 21), (3, 11)],
         zones=[("ice", C(16, 8.5, 3.8)), ("water", C(21, 12.6, 1.8)), ("sand", C(35.2, 19.2, 1.4))]),
    hole("Crevasse Leap", 2, (6, 12), (31, 7), rect(3, 4, 37, 20),
         zones=[("water", Rz(18, 4, 22, 20)), ("ice", Rz(17.6, 17.4, 22.4, 20)), ("jump", Rz(12, 10, 15, 14), 0),
                ("sand", C(34, 15.5, 1.5))]),
    hole("Icicle Gallery", 2, (5.5, 12), (34, 12), rect(3, 3, 37, 21),
         posts=[(x, y, 0.65) for i, x in enumerate(range(10, 31, 5)) for y in ((7, 12, 17) if i % 2 == 0 else (9.5, 14.5))],
         zones=[("ice", Rz(3, 3, 37, 21)), ("base", C(34, 12, 1.9)), ("base", C(5.5, 12, 1.5))]),
    hole("Frost Gates", 2, (6, 12), (33, 9), rect(3, 6, 37, 18),
         gates=[(14, 6, 14, 12, 0, 6, 4.0, 0), (25, 6, 25, 12, 0, 6, 4.0, 0.5)], zones=[("ice", Rz(16, 6, 23, 18)), ("slope", Rz(27, 6, 37, 18), 0, 2.0)]),
    hole("Snow Globe", 2, (6, 12), (27.5, 15.5), arena(22, 12, 10, 9.5, 14.5, 3),
         bumpers=[(22 + 7 * math.cos(math.radians(a)), 12 + 7 * math.sin(math.radians(a)), 0.9) for a in (45, 135, 225, 315)],
         zones=[("ice", C(22, 12, 8.6)), ("base", C(22, 12, 5)), ("hill", 22, 12, 4.4, 3.2), ("base", C(27.5, 15.5, 1.6))]),
    hole("Avalanche", 3, (7, 18), (31, 6), rect(3, 3, 37, 21),
         posts=[(14, 13, 1.0), (24, 15, 1.1), (20, 10.5, 0.8)],
         zones=[("slope", Rz(3, 9, 37, 21), 0, 5.0), ("base", Rz(3, 3, 37, 9)), ("sand", Rz(3, 19.5, 37, 21)),
                ("base", C(7, 18, 1.2))]),
    hole("Twin Portals", 3, (5.5, 12), (34, 12), [rect(3, 8, 13, 16), rect(16, 3, 24, 21), rect(27, 8, 37, 16)],
         portals=[(11, 12, 20, 18.5, -90), (20, 5.5, 29.5, 12, 0)], gates=[(16, 12, 20, 12, 4, 0, 3.0, 0)],
         zones=[("ice", Rz(16, 3, 24, 21))]),
    hole("Rimewater Crown", 4, (6, 18), (32, 6),
         [(3, 3), (14, 3), (26, 15), (26, 3), (37, 3), (37, 21), (26, 21), (14, 9), (14, 21), (3, 21)],
         bumpers=[(8.5, 10, 0.9)], gates=[(20, 12, 20, 15, 0, -3, 3.4, 0)],
         zones=[("ice", P((14, 3), (26, 15), (26, 21), (14, 9))), ("slope", Rz(26, 9, 37, 21), 0, 1.6),
                ("water", C(31.5, 14, 1.6)), ("sand", C(29, 4.8, 1.0)), ("ice", Rz(3, 3, 14, 7))]),
]

COPPER = [
    hole("Rivet Row", 3, (6, 12), (31, 12), rect(3, 7, 37, 17), blocks=[rect(25.5, 10.6, 27.5, 13.4)],
         zones=[("belt", Rz(15, 7, 21, 17), 0, -4.5), ("sand", Rz(34, 7, 37, 17))]),
    hole("Gearwheel", 3, (5, 12), (35, 12),
         [(3, 9), (9, 9), (13, 4), (27, 4), (31, 9), (37, 9), (37, 15), (31, 15), (27, 20), (13, 20), (9, 15), (3, 15)],
         rotors=[(20, 12, 5.2, 3, 1.0, 1.0)], blocks=[rect(31.6, 10.9, 32.6, 13.1)], zones=[("sand", C(35.5, 14, 0.8))]),
    hole("Piston Alley", 2, (6, 12), (33, 12), rect(3, 8, 37, 16),
         gates=[(11, 8.35, 14, 8.35, 0, 5, 2.4, 0), (18, 15.65, 21, 15.65, 0, -5, 2.4, 0.33),
                (25, 8.35, 28, 8.35, 0, 5, 2.4, 0.66)], posts=[(30.5, 12, 0.8)], zones=[("sand", Rz(35, 8, 37, 16))]),
    hole("Slag Pit", 3, (6, 17), (33, 7), rect(3, 3, 37, 21),
         zones=[("water", Rz(12, 3, 28, 21)), ("base", P((12, 15), (28, 6), (28, 9.5), (12, 18.5))),
                ("sand", C(34, 17, 1.4))]),
    hole("Pipeworks", 2, (6, 12), (33, 8), [rect(3, 3, 17, 21), rect(23, 3, 37, 21)],
         portals=[(14, 5.5, 26, 6, 0), (14, 12, 26, 18, 0), (14, 18.5, 5.5, 5.5, 90)],
         bumpers=[(9.5, 8.5, 0.8), (9.5, 15.5, 0.8)], zones=[("sand", C(33, 15, 1.4))]),
    hole("Spring Hall", 2, (6, 12), (32, 12), [(3, 8), (7, 4), (37, 4), (37, 20), (7, 20), (3, 16)],
         bumpers=[(16, 8, 0.9), (16, 16, 0.9), (22, 12, 0.9), (28, 7.5, 0.9), (28, 16.5, 0.9)]),
    hole("Furnace Leap", 3, (6, 12), (34, 7), rect(3, 4, 37, 20),
         zones=[("water", Rz(17, 4, 24, 20)), ("jump", Rz(11, 9.5, 14, 14.5), 0), ("sand", Rz(25, 4, 30, 20))]),
    hole("Conveyor Loop", 2, (6, 12), (21, 12), rect(3, 3, 37, 21),
         blocks=[rect(17, 8.6, 25, 9.8), rect(17, 14.2, 25, 15.4), rect(17, 9.8, 18.2, 14.2)],
         zones=[("belt", Rz(8, 3, 37, 7), 4.5, 0), ("belt", Rz(33, 7, 37, 21), 0, 4.5), ("belt", Rz(8, 17, 33, 21), -4.5, 0),
                ("water", C(29, 18.5, 1.1))]),
    hole("The Crucible", 4, (6, 12), (22, 12), arena(22, 12, 10.5, 9.5, 14.5, 3, 22),
         rotors=[(22, 12, 4.2, 2, 0.9, 0.0, 1.9)],
         zones=[("water", C(22, 12, 7.6)), ("base", C(22, 12, 5.6)), ("base", bridge(22, 12, 135, 5, 8.4, 1.3)),
                ("base", bridge(22, 12, 315, 5, 8.4, 1.3))]),
]

COURSES = [
    dict(name="WILLOW MEADOW", short="Willow Meadow", key="meadow", holes=MEADOW, theme="meadow"),
    dict(name="RIMEWATER", short="Rimewater", key="rimewater", holes=FROST, theme="frost"),
    dict(name="THE COPPERWORKS", short="Copperworks", key="copperworks", holes=COPPER, theme="copper"),
]
TOUR = 3                                           # "course" 3: all 27 holes in a row
TOUR_KEY = "grand tour"

THEMES = {
    "meadow": dict(
        fair=((92, 172, 76), (80, 158, 66)), rough=(44, 92, 40), rough2=(56, 108, 46),
        rail=((196, 144, 88), (112, 72, 40)), block=((52, 110, 48), (30, 70, 32)),
        sand=(228, 206, 150), water=((40, 112, 186), (24, 70, 140)), ice=(170, 220, 240),
        post=(150, 146, 138), bumper=(222, 62, 58), portal=(70, 46, 30), slag=False, fric=4.2,
        accent=(150, 230, 120), names=("sand", "pond", "log rail", "toadstool", "rabbit burrow")),
    "frost": dict(
        fair=((214, 228, 242), (202, 218, 236)), rough=(54, 74, 116), rough2=(70, 94, 136),
        rail=((176, 226, 252), (84, 140, 200)), block=((150, 200, 236), (90, 140, 196)),
        sand=(246, 249, 255), water=((26, 64, 124), (12, 36, 80)), ice=(156, 214, 244),
        post=(96, 150, 214), bumper=(170, 122, 255), portal=(60, 120, 230), slag=False, fric=4.4,
        accent=(160, 220, 255), names=("snowdrift", "meltwater", "ice rail", "crystal", "frost portal")),
    "copper": dict(
        fair=((98, 106, 118), (90, 98, 110)), rough=(34, 24, 28), rough2=(46, 32, 34),
        rail=((222, 144, 82), (122, 64, 34)), block=((84, 78, 74), (52, 46, 44)),
        sand=(66, 60, 62), water=((255, 132, 36), (200, 50, 20)), ice=(150, 200, 220),
        post=(196, 170, 96), bumper=(236, 196, 80), portal=(40, 40, 46), slag=True, fric=3.8,
        accent=(255, 170, 100), names=("cinders", "slag", "copper rail", "spring", "pipe")),
}


# =============================================================================================
# Sound: soft wooden clicks, splashes, a little fanfare
# =============================================================================================
def _arp(fs, d=0.06, v=0.3, w="tri", last=0.22):
    return [dict(w=w, f=f, d=d, v=v) for f in fs[:-1]] + [dict(w=w, f=fs[-1], d=last, v=v, vib=(6, 0.15))]


SND = Sound(GAME, {
    "putt": [dict(w="tri", f=520, f2=380, d=0.05, v=0.34), dict(w="noise", f=3000, d=0.03, v=0.12, at=0)],
    "drive": [dict(w="tri", f=420, f2=260, d=0.07, v=0.4), dict(w="noise", f=2200, f2=800, d=0.06, v=0.2, at=0)],
    "wall": [dict(w="tri", f=300, f2=240, d=0.04, v=0.2), dict(w="noise", f=1800, d=0.02, v=0.08, at=0)],
    "post": [dict(w="tri", f=700, f2=620, d=0.05, v=0.18)],
    "bump": [dict(w="square", f=330, f2=720, d=0.07, v=0.2, duty=0.3), dict(w="tri", f=990, d=0.06, v=0.14, at=0.02)],
    "mover": [dict(w="square", f=180, f2=140, d=0.07, v=0.2, duty=0.4), dict(w="noise", f=1200, d=0.04, v=0.1, at=0)],
    "splash": [dict(w="noise", f=2500, f2=400, d=0.35, v=0.4), dict(w="sine", f=300, f2=120, d=0.25, v=0.2, at=0)],
    "sizzle": [dict(w="noise", f=6000, f2=1500, d=0.5, v=0.32), dict(w="saw", f=140, f2=70, d=0.3, v=0.12, at=0)],
    "sand": [dict(w="noise", f=900, f2=300, d=0.12, v=0.18)],
    "portal": [dict(w="sine", f=300, f2=1200, d=0.16, v=0.25), dict(w="sine", f=1200, f2=500, d=0.14, v=0.18)],
    "jump": [dict(w="tri", f=300, f2=900, d=0.14, v=0.25)],
    "land": [dict(w="tri", f=200, f2=120, d=0.06, v=0.3), dict(w="noise", f=900, d=0.04, v=0.12, at=0)],
    "lip": [dict(w="tri", f=880, f2=660, d=0.05, v=0.2), dict(w="tri", f=660, f2=990, d=0.05, v=0.18)],
    "sink": [dict(w="tri", f=196, f2=150, d=0.08, v=0.36), dict(w="tri", f=1175, d=0.06, v=0.24, at=0.12),
             dict(w="tri", f=1568, d=0.16, v=0.24)],
    "birdie": _arp([784, 988, 1175, 1568], 0.06, 0.28),
    "ace": _arp([523, 659, 784, 1047, 1319, 1568, 2093], 0.07, 0.3, "square", 0.4),
    "par": _arp([659, 784, 988], 0.07, 0.24),
    "bogey": [dict(w="tri", f=440, f2=415, d=0.12, v=0.24), dict(w="tri", f=349, f2=330, d=0.22, v=0.24)],
    "swing": [dict(w="sine", f=500, f2=900, d=0.06, v=0.12)],
    "tick": [dict(w="tri", f=1400, d=0.012, v=0.08)],
    "menu": [dict(w="tri", f=660, d=0.025, v=0.2)],
    "start": [dict(w="tri", f=523, d=0.06, v=0.3), dict(w="tri", f=784, d=0.06, v=0.3), dict(w="tri", f=1047, d=0.16, v=0.3)],
    "pause": [dict(w="tri", f=523, f2=392, d=0.07, v=0.22)],
    "round": [dict(w="tri", f=f, d=0.1, v=0.3) for f in (523, 659, 784, 1047, 784, 1047)] +
             [dict(w="tri", f=1319, d=0.6, v=0.32, vib=(6, 0.2), r="lin")],
    "sound_on": [dict(w="tri", f=440, d=0.06, v=0.35), dict(w="tri", f=880, d=0.12, v=0.35)],
})


def help_lines(kitty=True):
    swing = ("Space    hold, release to strike" if kitty else "Space    1st: swing meter, 2nd: strike")
    return ["PEBBLEPUTT - keys", "",
            "Left / Right   aim (tap 0.5 degrees, hold: faster)",
            "A / D          aim in 15 degree steps",
            "C              aim straight at the cup",
            "Up / Down      preset power      Enter  strike at it",
            swing,
            "X              cancel the swing   Tab  scorecard",
            "Esc / P        pause (Q quit, M sound)", "",
            "The dotted line shows only the start of the putt.",
            "The pebble drops only if it is slow over the cup.",
            "Water and slag: +1 stroke, back to the last spot.",
            "Slopes are shaded and marked with downhill arrows;",
            "ice keeps rolling, sand stops, ramps make it fly,",
            "burrows, portals and pipes carry it on. After %d" % MAX_STROKES,
            "strokes the pebble is picked up.", "",
            "Auto mode: Space pause, +/- speed, Esc stop."]


# =============================================================================================
# Geometry
# =============================================================================================
def in_poly(pts, x, y):
    inside = False
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def bbox(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def seg_dist2(x, y, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / l2))
    qx, qy = x1 + dx * t, y1 + dy * t
    return (x - qx) ** 2 + (y - qy) ** 2


class Shape:
    """A zone's area: a polygon or a circle, with a bounding box for quick rejection."""
    __slots__ = ("kind", "pts", "cx", "cy", "r", "box")

    def __init__(self, spec):
        self.kind = spec[0]
        if self.kind == "c":
            _, self.cx, self.cy, self.r = spec
            self.pts = None
            self.box = (self.cx - self.r, self.cy - self.r, self.cx + self.r, self.cy + self.r)
        else:
            self.pts = spec[1]
            self.box = bbox(self.pts)

    def has(self, x, y):
        b = self.box
        if x < b[0] or x > b[2] or y < b[1] or y > b[3]:
            return False
        if self.pts is None:
            return (x - self.cx) ** 2 + (y - self.cy) ** 2 <= self.r * self.r
        return in_poly(self.pts, x, y)


class Zone:
    __slots__ = ("t", "shape", "ax", "ay", "cx", "cy", "r", "k", "dirx", "diry")

    def __init__(self, z):
        self.t = z[0]
        self.ax = self.ay = 0.0
        self.dirx = self.diry = 0.0
        if self.t in ("hill", "bowl"):
            _, self.cx, self.cy, self.r, self.k = z
            self.shape = Shape(("c", self.cx, self.cy, self.r))
        else:
            self.shape = Shape(z[1])
            if self.t in ("slope", "belt"):
                self.ax, self.ay = z[2], z[3]
            elif self.t == "jump":
                a = math.radians(z[2])
                self.dirx, self.diry = math.cos(a), math.sin(a)
                self.ax, self.ay = -2.2 * self.dirx, -2.2 * self.diry      # the ramp rises: uphill along it


_HOLES = {}


def get_hole(ci, hi):
    h = _HOLES.get((ci, hi))
    if h is None:
        h = _HOLES[(ci, hi)] = Hole(ci, hi)
    return h


class Hole:
    """One hole, ready to play: rails, surfaces on a grid, a spatial hash for collisions, the movers."""

    def __init__(self, ci, hi):
        spec = COURSES[ci]["holes"][hi]
        self.ci, self.hi, self.spec = ci, hi, spec
        self.course = COURSES[ci]
        self.theme = THEMES[self.course["theme"]]
        self.name, self.par = spec["name"], spec["par"]
        self.tee, self.cup = tuple(map(float, spec["tee"])), tuple(map(float, spec["cup"]))
        self.greens = [[(float(x), float(y)) for x, y in g] for g in spec["green"]]
        self.gboxes = [bbox(g) for g in self.greens]
        self.blocks = [[(float(x), float(y)) for x, y in b] for b in spec["blocks"]]
        self.zones = [Zone(z) for z in spec["zones"]]
        f = self.theme["fric"]
        self.fric = (f, f, 15.0, f, 0.85, f * 0.9, f)
        segs = []
        for g in self.greens + self.blocks:
            for i in range(len(g)):
                (x1, y1), (x2, y2) = g[i], g[(i + 1) % len(g)]
                segs.append((x1, y1, x2, y2))
        segs += [tuple(map(float, w)) for w in spec["walls"]]
        self.rails = segs
        self.segs = []
        for x1, y1, x2, y2 in segs:
            dx, dy = x2 - x1, y2 - y1
            self.segs.append((x1, y1, dx, dy, dx * dx + dy * dy or 1e-9))
        self.circs = [(float(x), float(y), float(r), 0.55, False) for x, y, r in spec["posts"]] + \
                     [(float(x), float(y), float(r), 1.0, True) for x, y, r in spec["bumpers"]]
        self.rotors = [tuple(map(float, r)) + ((0.0,) if len(r) < 7 else ()) for r in spec["rotors"]]
        self.gates = [tuple(map(float, gg)) for gg in spec["gates"]]
        self.portals = [(float(p[0]), float(p[1]), float(p[2]), float(p[3]), p[4]) for p in spec["portals"]]
        self.has_movers = bool(self.rotors or self.gates)
        self._mov = {}
        self.build_grid()
        self.build_hash()
        self._nav = None

    # --- surfaces --------------------------------------------------------------------------------
    def on_green(self, x, y):
        for g, b in zip(self.greens, self.gboxes):
            if b[0] <= x <= b[2] and b[1] <= y <= b[3] and in_poly(g, x, y):
                for bl in self.blocks:
                    if in_poly(bl, x, y):
                        return False
                return True
        return False

    def surface(self, x, y):
        """(kind, ax, ay) exactly at a point: the surface and the push of slopes, hills and belts."""
        if not self.on_green(x, y):
            return OUT, 0.0, 0.0
        kind, ax, ay = BASE, 0.0, 0.0
        for z in self.zones:
            if not z.shape.has(x, y):
                continue
            t = z.t
            if t == "sand":
                kind = SAND
            elif t == "water":
                kind = WATER
            elif t == "ice":
                kind = ICE
            elif t == "base":
                kind, ax, ay = BASE, 0.0, 0.0
            elif t == "slope":
                ax += z.ax
                ay += z.ay
            elif t == "belt":
                kind = BELT
                ax += z.ax
                ay += z.ay
            elif t == "jump":
                kind = JUMP
                ax += z.ax
                ay += z.ay
            else:                                   # hill / bowl: a smooth bump, steepest half-way out
                dx, dy = x - z.cx, y - z.cy
                d = math.hypot(dx, dy)
                if d > 1e-6:
                    k = z.k * math.sin(math.pi * d / z.r) * (1 if t == "hill" else -1)
                    ax += k * dx / d
                    ay += k * dy / d
        return kind, ax, ay

    def height(self, x, y):
        """Height for the contour lines (only hills, bowls and slopes)."""
        h = 0.0
        for z in self.zones:
            if z.t in ("hill", "bowl") and z.shape.has(x, y):
                d = math.hypot(x - z.cx, y - z.cy)
                h += (1 if z.t == "hill" else -1) * z.k * z.r / math.pi * (1 + math.cos(math.pi * d / z.r))
            elif z.t == "slope" and z.shape.has(x, y):
                h -= z.ax * x + z.ay * y
        return h

    def build_grid(self):
        gw, gh = int(FW * GRID), int(FH * GRID)
        self.gw, self.gh = gw, gh
        kind = bytearray(gw * gh)
        ax, ay = [0.0] * (gw * gh), [0.0] * (gw * gh)
        for j in range(gh):
            y = (j + 0.5) / GRID
            for i in range(gw):
                k, a, b = self.surface((i + 0.5) / GRID, y)
                n = j * gw + i
                kind[n], ax[n], ay[n] = k, a, b
        self.gk, self.gax, self.gay = kind, ax, ay

    def cell(self, x, y):
        i, j = int(x * GRID), int(y * GRID)
        if i < 0 or j < 0 or i >= self.gw or j >= self.gh:
            return OUT, 0.0, 0.0
        n = j * self.gw + i
        return self.gk[n], self.gax[n], self.gay[n]

    def kind_at(self, x, y):
        i, j = int(x * GRID), int(y * GRID)
        if i < 0 or j < 0 or i >= self.gw or j >= self.gh:
            return OUT
        return self.gk[j * self.gw + i]

    # --- collisions ------------------------------------------------------------------------------
    HC = 2.0

    def build_hash(self):
        cw, ch = int(FW / self.HC), int(FH / self.HC)
        self.hw, self.hh = cw, ch
        reach = self.HC * 0.7072 + BALL_R + 0.5
        self.hseg = []
        self.hcirc = []
        for j in range(ch):
            for i in range(cw):
                cx, cy = (i + 0.5) * self.HC, (j + 0.5) * self.HC
                self.hseg.append(tuple(n for n, (x1, y1, x2, y2) in enumerate(self.rails)
                                       if seg_dist2(cx, cy, x1, y1, x2, y2) < (reach + WT) ** 2))
                self.hcirc.append(tuple(n for n, c in enumerate(self.circs)
                                        if (cx - c[0]) ** 2 + (cy - c[1]) ** 2 < (reach + c[2]) ** 2))

    def movers(self, tick):
        """The moving arms and gates at a tick: (x1, y1, x2, y2, kind, cx, cy, omega, vx, vy)."""
        m = self._mov.get(tick)
        if m is not None:
            return m
        if len(self._mov) > 6000:
            self._mov.clear()
        t = tick * DT
        out = []
        for cx, cy, L, arms, om, ph, r0 in self.rotors:
            for k in range(int(arms)):
                a = ph + om * t + k * TAU / arms
                c, s = math.cos(a), math.sin(a)
                out.append((cx + c * max(r0, 0.0), cy + s * max(r0, 0.0), cx + c * L, cy + s * L, 0, cx, cy, om, 0.0, 0.0))
        for x1, y1, x2, y2, ox, oy, per, ph in self.gates:
            u = TAU * (t / per + ph)
            f = (1 - math.cos(u)) / 2
            df = math.pi / per * math.sin(u)
            out.append((x1 + ox * f, y1 + oy * f, x2 + ox * f, y2 + oy * f, 1, 0.0, 0.0, 0.0, ox * df, oy * df))
        self._mov[tick] = out
        return out

    def jump_dir(self, x, y):
        for z in self.zones:
            if z.t == "jump" and z.shape.has(x, y):
                return z.dirx, z.diry
        for z in self.zones:
            if z.t == "jump":
                return z.dirx, z.diry
        return 1.0, 0.0

    # --- the caddie's map: how far every spot is from the cup, around rails and water ---------------
    NAV = 2                                  # cells per unit

    def nav(self):
        if self._nav is not None:
            return self._nav
        n = self.NAV
        w, h = int(FW * n), int(FH * n)
        cost = [0.0] * (w * h)
        clear = (BALL_R + WT - 0.05) ** 2
        for j in range(h):
            y = (j + 0.5) / n
            for i in range(w):
                x = (i + 0.5) / n
                k = self.kind_at(x, y)
                if k in (OUT, WATER):
                    continue
                hc = int(y / self.HC) * self.hw + int(x / self.HC)
                if any(seg_dist2(x, y, *self.rails[s]) < clear for s in self.hseg[hc]):
                    continue
                if any((x - self.circs[c][0]) ** 2 + (y - self.circs[c][1]) ** 2 < (BALL_R + self.circs[c][2] - 0.05) ** 2
                       for c in self.hcirc[hc]):
                    continue
                cost[j * w + i] = 3.0 if k == SAND else 1.0
        links = {}                           # from cell -> [(to cell, cost)] (portals, ramps)

        def cid(x, y):
            i, j = clamp(int(x * n), 0, w - 1), clamp(int(y * n), 0, h - 1)
            return j * w + i

        for px, py, ex, ey, ang in self.portals:
            dst = cid(ex, ey)
            if ang is not None:
                a = math.radians(ang)
                dst = cid(ex + math.cos(a) * 1.5, ey + math.sin(a) * 1.5)
            for dj in (-1, 0, 1):
                for di in (-1, 0, 1):
                    links.setdefault(cid(px + di * 0.5, py + dj * 0.5), []).append((dst, 0.5))
        for z in self.zones:
            if z.t != "jump":
                continue
            b = z.shape.box
            for j in range(int(b[1] * n), int(b[3] * n) + 1):
                for i in range(int(b[0] * n), int(b[2] * n) + 1):
                    x, y = (i + 0.5) / n, (j + 0.5) / n
                    if not z.shape.has(x, y):
                        continue
                    for dist in (9, 10, 11, 12):
                        lx, ly = x + z.dirx * dist, y + z.diry * dist
                        if 0 < lx < FW and 0 < ly < FH and cost[cid(lx, ly)] > 0:
                            links.setdefault(j * w + i, []).append((cid(lx, ly), 2.0))
                            break
        rev = {}
        for a, lst in links.items():
            for b, c in lst:
                rev.setdefault(b, []).append((a, c))
        INF = 1e9
        dist = [INF] * (w * h)
        start = cid(*self.cup)
        dist[start] = 0.0
        pq = [(0.0, start)]
        nb = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0), (-1, -1, 1.414), (1, -1, 1.414), (-1, 1, 1.414),
              (1, 1, 1.414)]
        while pq:
            d, c = heapq.heappop(pq)
            if d > dist[c]:
                continue
            ci, cj = c % w, c // w
            for di, dj, l in nb:
                i2, j2 = ci + di, cj + dj
                if 0 <= i2 < w and 0 <= j2 < h:
                    c2 = j2 * w + i2
                    k = cost[c2]
                    if k <= 0:
                        continue
                    if di and dj and (cost[cj * w + i2] <= 0 or cost[j2 * w + ci] <= 0):
                        continue
                    nd = d + l / n * max(k, cost[c] or 1.0)
                    if nd < dist[c2]:
                        dist[c2] = nd
                        heapq.heappush(pq, (nd, c2))
            for c2, l in rev.get(c, ()):
                nd = d + l
                if nd < dist[c2]:
                    dist[c2] = nd
                    heapq.heappush(pq, (nd, c2))
        self._nav = (w, h, dist)
        return self._nav

    def nav_dist(self, x, y):
        w, h, dist = self.nav()
        n = self.NAV
        i, j = int(x * n), int(y * n)
        best = 1e9
        for r in (0, 1, 2):
            for dj in range(-r, r + 1):
                for di in range(-r, r + 1):
                    i2, j2 = i + di, j + dj
                    if 0 <= i2 < w and 0 <= j2 < h:
                        d = dist[j2 * w + i2]
                        if d < 1e8:
                            best = min(best, d + math.hypot(di, dj) / n)
            if best < 1e8:
                return best
        return 99.0


# =============================================================================================
# The pebble and its physics (shared by the game and the caddie's planning, so a plan plays out exactly)
# =============================================================================================
MOVING, STOPPED, SUNK, SPLASH = range(4)


class Ball:
    __slots__ = ("x", "y", "vx", "vy", "z", "vz", "air", "kind", "cool", "tn", "t", "lip")

    def __init__(self, x, y, vx=0.0, vy=0.0):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.z = self.vz = 0.0
        self.air = False
        self.kind = BASE
        self.cool = 0.0
        self.tn = None
        self.t = 0.0
        self.lip = 0.0

    def copy(self):
        b = Ball(self.x, self.y, self.vx, self.vy)
        b.z, b.vz, b.air, b.kind, b.cool = self.z, self.vz, self.air, self.kind, self.cool
        return b


def step_ball(H, b, tick, ev=None):
    """One physics tick. Returns MOVING, STOPPED, SUNK or SPLASH; events go to ev (a list) when given."""
    movs = H.movers(tick) if H.has_movers else ()
    sp = math.hypot(b.vx, b.vy)
    n = int(sp * DT / SUBD) + 1
    h = DT / n
    fr = H.fric
    cx, cy = H.cup
    b.tn = None
    for _ in range(n):
        if b.air:
            b.z += b.vz * h
            b.vz -= G_AIR * h
            if b.z <= 0:
                b.z = b.vz = 0.0
                b.air = False
                b.vx *= 0.8
                b.vy *= 0.8
                if ev is not None:
                    ev.append(("land", b.x, b.y))
        else:
            kind, ax, ay = H.cell(b.x, b.y)
            if kind == WATER or kind == OUT:
                if ev is not None:
                    ev.append(("splash", b.x, b.y))
                return SPLASH
            if kind != b.kind:
                if b.kind == JUMP:
                    jx, jy = H.jump_dir(b.x - b.vx * h * 2, b.y - b.vy * h * 2)
                    along = b.vx * jx + b.vy * jy
                    if along > 3.5:
                        b.air = True
                        b.vz = JUMP_K * along
                        b.z = 0.001
                        if ev is not None:
                            ev.append(("jump", b.x, b.y))
                elif kind == SAND and ev is not None and sp > 2:
                    ev.append(("sand", b.x, b.y))
                b.kind = kind
            if not b.air:
                b.vx += ax * h
                b.vy += ay * h
                s = math.hypot(b.vx, b.vy)
                if s > 0:
                    dec = fr[kind] * h + DRAG * s * h
                    if dec >= s:
                        b.vx = b.vy = 0.0
                    else:
                        k = (s - dec) / s
                        b.vx *= k
                        b.vy *= k
        b.x += b.vx * h
        b.y += b.vy * h
        collide(H, b, movs, ev)
        if not b.air:
            if b.cool <= 0:
                for px, py, ex, ey, ang in H.portals:
                    if (b.x - px) ** 2 + (b.y - py) ** 2 < PORTAL_R * PORTAL_R:
                        s = max(math.hypot(b.vx, b.vy) * 0.85, 3.0)
                        if ang is None:
                            d = math.hypot(b.vx, b.vy) or 1.0
                            ux, uy = b.vx / d, b.vy / d
                        else:
                            ux, uy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
                        if ev is not None:
                            ev.append(("portal", px, py, ex, ey))
                        b.x, b.y = ex, ey
                        b.vx, b.vy = ux * s, uy * s
                        b.cool = 0.5
                        break
            dx, dy = b.x - cx, b.y - cy
            d2 = dx * dx + dy * dy
            if d2 < CUP_R * CUP_R:
                s = math.hypot(b.vx, b.vy)
                if s < VSINK * (1 - 0.45 * d2 / (CUP_R * CUP_R)):       # over the rim it has to be slower
                    b.x, b.y = cx, cy
                    if ev is not None:
                        ev.append(("sink", cx, cy))
                    return SUNK
                d = math.sqrt(d2) or 1e-6
                b.vx -= dx / d * 9.0 * h
                b.vy -= dy / d * 9.0 * h
                k = 1 - 0.8 * h
                b.vx *= k
                b.vy *= k
                if b.lip <= 0 and ev is not None:
                    ev.append(("lip", b.x, b.y))
                b.lip = 0.3
    b.cool -= DT
    b.lip -= DT
    b.t += DT
    s = math.hypot(b.vx, b.vy)
    if not b.air and (s < VSTOP or b.t > SHOT_T):
        kind, ax, ay = H.cell(b.x, b.y)
        if b.tn is not None:
            nx, ny = b.tn
            an = ax * nx + ay * ny
            if an < 0:
                ax, ay = ax - an * nx, ay - an * ny
        if math.hypot(ax, ay) <= fr[kind] or b.t > SHOT_T:
            if kind == WATER or kind == OUT:
                return SPLASH
            b.vx = b.vy = 0.0
            return STOPPED
    return MOVING


def collide(H, b, movs, ev):
    x, y = b.x, b.y
    vx, vy = b.vx, b.vy
    # moving arms and gates first: they push; the fixed rails come last so the pebble never ends up inside one
    rr = BALL_R + MT
    for x1, y1, x2, y2, kind, mcx, mcy, om, gvx, gvy in movs:
        dx, dy = x2 - x1, y2 - y1
        l2 = dx * dx + dy * dy or 1e-9
        t = ((x - x1) * dx + (y - y1) * dy) / l2
        if t < -0.5 or t > 1.5:
            continue
        tc = 0.0 if t < 0 else 1.0 if t > 1 else t
        qx, qy = x1 + dx * tc, y1 + dy * tc
        ex, ey = x - qx, y - qy
        d2 = ex * ex + ey * ey
        if d2 >= rr * rr:
            continue
        if kind == 0:
            mvx, mvy = -om * (qy - mcy), om * (qx - mcx)
        else:
            mvx, mvy = gvx, gvy
        d = math.sqrt(d2) or 1e-6
        nx, ny = ex / d, ey / d
        if kind == 1 and tc in (0.0, 1.0) and (mvx * dx + mvy * dy) * (1 if tc == 1.0 else -1) > 0:
            # the leading end of a sliding gate: it wedges the pebble aside instead of pinching it
            l = math.sqrt(l2)
            px_, py_ = -dy / l, dx / l
            side = 1 if (x - x1) * px_ + (y - y1) * py_ >= 0 else -1
            nx, ny = px_ * side, py_ * side
            off = (x - qx) * nx + (y - qy) * ny
            x += nx * (rr - off)
            y += ny * (rr - off)
        else:
            x, y = qx + nx * rr, qy + ny * rr
        rvx, rvy = vx - mvx, vy - mvy
        vn = rvx * nx + rvy * ny
        if vn < 0:
            vx -= 1.6 * vn * nx
            vy -= 1.6 * vn * ny
            if ev is not None and vn < -1:
                ev.append(("mover", x, y, -vn))
        b.tn = (nx, ny)
    hc = clamp(int(y / H.HC), 0, H.hh - 1) * H.hw + clamp(int(x / H.HC), 0, H.hw - 1)
    for ci in H.hcirc[hc]:
        ccx, ccy, cr, e, bumper = H.circs[ci]
        ex, ey = x - ccx, y - ccy
        rr = BALL_R + cr
        d2 = ex * ex + ey * ey
        if d2 < rr * rr:
            d = math.sqrt(d2) or 1e-6
            nx, ny = ex / d, ey / d
            x, y = ccx + nx * rr, ccy + ny * rr
            vn = vx * nx + vy * ny
            if vn < 0:
                if bumper:
                    out = max(-vn * e, BUMP_KICK)
                    vx += (out - vn) * nx
                    vy += (out - vn) * ny
                    if ev is not None:
                        ev.append(("bump", ccx, ccy, ci))
                else:
                    vx -= (1 + e) * vn * nx
                    vy -= (1 + e) * vn * ny
                    if ev is not None and vn < -1:
                        ev.append(("post", x, y, -vn))
            b.tn = (nx, ny)
    rr = BALL_R + WT
    rr2 = rr * rr
    segs = H.segs
    for si in H.hseg[hc]:
        x1, y1, dx, dy, l2 = segs[si]
        t = ((x - x1) * dx + (y - y1) * dy) / l2
        t = 0.0 if t < 0 else 1.0 if t > 1 else t
        qx, qy = x1 + dx * t, y1 + dy * t
        ex, ey = x - qx, y - qy
        d2 = ex * ex + ey * ey
        if d2 < rr2:
            d = math.sqrt(d2) or 1e-6
            nx, ny = ex / d, ey / d
            x, y = qx + nx * rr, qy + ny * rr
            vn = vx * nx + vy * ny
            if vn < 0:
                vx -= 1.72 * vn * nx
                vy -= 1.72 * vn * ny
                vx *= 0.97
                vy *= 0.97
                if ev is not None and vn < -0.8:
                    ev.append(("wall", x, y, -vn))
            b.tn = (nx, ny)
    b.x, b.y, b.vx, b.vy = x, y, vx, vy


def simulate(H, x, y, ang, power, tick, limit=SHOT_T):
    """Play a putt through to its end with the real physics: (result, ball, ticks)."""
    b = Ball(x, y, math.cos(ang) * VMAX * power, math.sin(ang) * VMAX * power)
    n = int(limit / DT)
    for i in range(n):
        r = step_ball(H, b, tick + i)
        if r != MOVING:
            return r, b, i + 1
    return STOPPED, b, n


def ray_clear(H, x0, y0, x1, y1, pad=BALL_R + WT):
    """True when a pebble rolling straight from (x0, y0) to (x1, y1) meets no rail, post or bumper."""
    d = math.hypot(x1 - x0, y1 - y0)
    n = max(1, int(d / 0.4))
    for i in range(1, n + 1):
        x, y = x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n
        hc = clamp(int(y / H.HC), 0, H.hh - 1) * H.hw + clamp(int(x / H.HC), 0, H.hw - 1)
        for si in H.hseg[hc]:
            if seg_dist2(x, y, *H.rails[si]) < (pad - 0.04) ** 2:
                return False
        for ci in H.hcirc[hc]:
            c = H.circs[ci]
            if (x - c[0]) ** 2 + (y - c[1]) ** 2 < (BALL_R + c[2]) ** 2:
                return False
    return True


def preview(H, x, y, ang, length):
    """The aim line: straight, folded off the fixed rails and posts, only length units long (no slopes shown)."""
    pts = [(x, y)]
    dx, dy = math.cos(ang), math.sin(ang)
    step = 0.15
    left = length
    b = Ball(x, y, dx, dy)
    while left > 0:
        b.x += b.vx * step
        b.y += b.vy * step
        bvx, bvy = b.vx, b.vy
        collide(H, b, (), None)
        s = math.hypot(b.vx, b.vy) or 1.0
        b.vx, b.vy = b.vx / s, b.vy / s
        if (b.vx, b.vy) != (bvx, bvy):
            pts.append((b.x, b.y))
        left -= step
    pts.append((b.x, b.y))
    return pts


# =============================================================================================
# The game: holes, turns, strokes, the scorecard
# =============================================================================================
RESULT = {-3: "ALBATROSS", -2: "EAGLE", -1: "BIRDIE", 0: "PAR", 1: "BOGEY", 2: "DOUBLE BOGEY", 3: "TRIPLE BOGEY"}


def result_name(strokes, par):
    if strokes == 1:
        return "HOLE IN ONE"
    d = strokes - par
    if d < -3:
        return "CONDOR"
    return RESULT.get(d, "+%d" % d)


class Player:
    def __init__(self, i, name, color, bot=False):
        self.i, self.name, self.color, self.bot = i, name, color, bot
        self.card = []
        self.preset = 0.45

    def total(self):
        return sum(s for s in self.card if s is not None)


class Particle:
    __slots__ = ("x", "y", "z", "vx", "vy", "vz", "t", "life", "c", "kind")

    def __init__(self, x, y, vx, vy, life, c, kind=0, z=0.0, vz=0.0):
        self.x, self.y, self.vx, self.vy, self.life, self.c, self.kind = x, y, vx, vy, life, c, kind
        self.z, self.vz = z, vz
        self.t = 0.0


class Game:
    def __init__(self, course=0, nplayers=1, bots=False, seed=None, quiet=False, demo=False, holes=None):
        self.course = course
        if holes is not None:
            self.holes = list(holes)
        elif course >= TOUR:
            self.holes = [(c, i) for c in range(3) for i in range(9)]
        else:
            self.holes = [(course, i) for i in range(9)]
        self.players = [Player(i, PLAYERS[i][0], PLAYERS[i][1], bot=bots) for i in range(nplayers)]
        for p in self.players:
            p.card = [None] * len(self.holes)
        self.solo = nplayers == 1
        self.quiet, self.demo = quiet, demo
        self.rnd = random.Random(seed)
        self.seed = seed
        self.bot = Bot(self, seed) if bots else None
        self.realtime = False
        self.tick = 0
        self.clock = 0.0
        self.acc = 0.0
        self.over = self.paused = self.help = False
        self.show_card = False
        self.parts = []
        self.floats = []
        self.flash = {}
        self.trail = []
        self.hole_i = -1
        self.order = list(range(nplayers))
        self.result, self.picked, self.last_power, self.bot_meter = "PAR", False, 0.0, None
        self.next_hole()

    # --- flow ------------------------------------------------------------------------------------
    @property
    def H(self):
        return self._H

    @property
    def cur(self):
        return self.players[self.order[min(self.turn, len(self.order) - 1)]]

    def snd(self, name, vol=1.0, gap=0.04):
        if not self.quiet:
            SND.play(name, vol, gap)

    def next_hole(self):
        if self.hole_i >= 0:          # honour: the best score on the last hole tees off first
            last, prev = self.hole_i, list(self.order)
            self.order.sort(key=lambda i: (self.players[i].card[last] or 99, prev.index(i)))
        self.hole_i += 1
        if self.hole_i >= len(self.holes):
            self.hole_i = len(self.holes) - 1
            self.over = True
            self.state, self.state_t = "over", 0.0
            self.snd("round")
            return
        self._H = get_hole(*self.holes[self.hole_i])
        self.turn = 0
        self.state, self.state_t = "intro", 0.0
        self.parts, self.floats, self.trail = [], [], []
        self.start_turn()

    def start_turn(self):
        H = self.H
        self.strokes = 0
        self.ball = Ball(*H.tee)
        self.spot = H.tee
        self.ready_aim()

    def ready_aim(self):
        H = self.H
        self.aim = math.atan2(H.cup[1] - self.ball.y, H.cup[0] - self.ball.x)
        self.swing = None
        self.plan = None
        self.trail = []

    def begin_aim(self):
        self.state, self.state_t = "aim", 0.0
        self.ready_aim()

    def finish_player(self, picked=False):
        p = self.cur
        p.card[self.hole_i] = self.strokes
        self.state, self.state_t = "sunk", 0.0
        self.picked = picked
        name = result_name(self.strokes, self.H.par)
        self.result = "PICKED UP" if picked else name
        d = self.strokes - self.H.par
        if picked:
            self.snd("bogey")
        elif self.strokes == 1:
            self.snd("ace")
            self.confetti(60)
        elif d < 0:
            self.snd("birdie")
            self.confetti(30)
        elif d == 0:
            self.snd("par")
        else:
            self.snd("bogey")

    def after_sunk(self):
        self.turn += 1
        if self.turn < len(self.players):
            self.start_turn()
            self.state, self.state_t = "intro", 0.0
        else:
            self.state, self.state_t = "card", 0.0

    def confetti(self, n):
        x, y = self.H.cup
        cols = [(255, 120, 90), (90, 180, 255), (250, 210, 80), (190, 130, 255), (120, 230, 130), WHITE]
        for _ in range(n):
            a = self.rnd.uniform(0, TAU)
            s = self.rnd.uniform(2, 9)
            self.parts.append(Particle(x, y, math.cos(a) * s, math.sin(a) * s, self.rnd.uniform(0.8, 1.8),
                                       self.rnd.choice(cols), 2, 0.2, self.rnd.uniform(4, 12)))

    def burst(self, x, y, n, cols, spd=4.0, life=0.6, kind=0, vz=(2, 6)):
        for _ in range(n):
            a = self.rnd.uniform(0, TAU)
            s = self.rnd.uniform(0.3, 1.0) * spd
            self.parts.append(Particle(x, y, math.cos(a) * s, math.sin(a) * s, self.rnd.uniform(0.5, 1.0) * life,
                                       self.rnd.choice(cols), kind, 0.0, self.rnd.uniform(*vz)))

    # --- the shot ------------------------------------------------------------------------------------
    def strike(self, ang, power):
        power = clamp(power, 0.02, 1.0)
        self.spot = (self.ball.x, self.ball.y)
        self.ball = Ball(self.ball.x, self.ball.y, math.cos(ang) * VMAX * power, math.sin(ang) * VMAX * power)
        self.aim = ang
        self.strokes += 1
        self.state, self.state_t = "roll", 0.0
        self.swing = None
        self.last_power = power
        self.snd("drive" if power > 0.6 else "putt", 0.6 + 0.4 * power)

    def meter(self):
        if self.swing is None:
            return None
        u = ((self.tick - self.swing) * DT / SWING_T) % 2.0
        return u if u <= 1 else 2 - u

    def human_input(self, inp):
        """Keys from Controls.sample (once per frame)."""
        if inp.get("card"):
            self.show_card = not self.show_card
        if self.state == "intro":
            if inp.get("space") or inp.get("enter"):
                self.state_t = 99
            return
        if self.state == "card":
            if inp.get("space") or inp.get("enter"):
                self.state_t = 99
            return
        if self.state != "aim" or self.cur.bot:
            return
        p = self.cur
        self.aim = (self.aim + math.radians(inp.get("turn", 0.0))) % TAU
        if inp.get("cup"):
            self.aim = math.atan2(self.H.cup[1] - self.ball.y, self.H.cup[0] - self.ball.x)
        p.preset = clamp(p.preset + inp.get("power", 0.0), 0.02, 1.0)
        if inp.get("cancel") and self.swing is not None:
            self.swing = None
            return
        if self.swing is None:
            if inp.get("enter"):
                self.strike(self.aim, p.preset)
            elif inp.get("space"):
                self.swing = self.tick
                self.snd("swing")
        else:
            if inp.get("space") or inp.get("enter") or inp.get("release"):
                self.strike(self.aim, max(0.02, self.meter()))

    # --- time ------------------------------------------------------------------------------------
    def think(self, budget):
        """The caddie plans (real-time loops call this every frame with a little time)."""
        if self.bot and self.state == "aim" and self.cur.bot and self.plan is not None and not self.bot.done:
            self.bot.work(budget)

    def update(self, dt, inp=None):
        if self.paused or self.over and self.state_t > 30:
            return
        if inp:
            self.human_input(inp)
        self.acc += min(dt, 0.25)
        n = 0
        while self.acc >= DT and n < 40:
            self.acc -= DT
            n += 1
            if not self.step():
                self.acc = 0.0
                break

    def step(self):
        """One tick. False when the clock is held (the caddie is still thinking about a timed putt)."""
        H = self.H
        if self.state == "aim" and self.cur.bot:
            if self.plan is None:
                self.plan = self.bot.begin(H, self.ball.x, self.ball.y, self.tick + int(LEAD / DT), self.aim)
            if not self.bot.done:
                if not self.realtime:
                    self.bot.work(None)
                elif self.tick >= self.bot.T:
                    return False
        self.tick += 1
        self.clock += DT
        self.state_t += DT
        self.fx_step()
        st = self.state
        if st == "intro":
            if self.state_t > 2.4:
                self.begin_aim()
        elif st == "aim":
            if self.cur.bot and self.bot.done:
                self.bot.steer()
                if self.tick >= self.bot.T:
                    a, pw = self.bot.shot
                    self.strike(a, pw)
        elif st == "roll":
            self.roll_step()
        elif st == "sunk":
            if self.state_t > 2.2:
                self.after_sunk()
        elif st == "splash":
            if self.state_t > 1.3:
                self.ball = Ball(*self.spot)
                if self.strokes >= MAX_STROKES:
                    self.finish_player(picked=True)
                else:
                    self.begin_aim()
        elif st == "card":
            if self.state_t > (3.0 if self.solo else 4.5):
                self.next_hole()
        return True

    def roll_step(self):
        H, b = self.H, self.ball
        ev = []
        r = step_ball(H, b, self.tick, ev)
        if b.air or math.hypot(b.vx, b.vy) > 1:
            if not self.trail or (self.trail[-1][0] - b.x) ** 2 + (self.trail[-1][1] - b.y) ** 2 > 0.04:
                self.trail.append((b.x, b.y, self.clock))
        self.trail = [t for t in self.trail if self.clock - t[2] < 0.6]
        th = H.theme
        for e in ev:
            k = e[0]
            if k == "wall":
                self.snd("wall", min(1.0, e[3] / 12), 0.05)
                if e[3] > 4:
                    self.burst(e[1], e[2], 3, [mix(th["rail"][0], WHITE, 0.4)], 2.0, 0.3, 0, (0.5, 2))
            elif k == "post":
                self.snd("post", min(1.0, e[3] / 10), 0.05)
            elif k == "bump":
                self.snd("bump", 0.8, 0.06)
                self.flash[e[3]] = self.clock
                self.burst(e[1], e[2], 8, [mix(th["bumper"], WHITE, 0.5), WHITE], 5.0, 0.4)
            elif k == "mover":
                self.snd("mover", min(1.0, e[3] / 8), 0.08)
            elif k == "sand":
                self.snd("sand", 0.8, 0.1)
                self.burst(e[1], e[2], 10, [th["sand"], shade(th["sand"], 0.8)], 2.5, 0.5, 0, (1, 4))
            elif k == "portal":
                self.snd("portal")
                self.burst(e[1], e[2], 10, [mix(th["portal"], WHITE, 0.6)], 3.0, 0.5)
                self.burst(e[3], e[4], 10, [mix(th["portal"], WHITE, 0.6)], 3.0, 0.5)
                self.trail = []
            elif k == "jump":
                self.snd("jump")
            elif k == "land":
                self.snd("land")
                self.burst(e[1], e[2], 6, [shade(th["fair"][0], 1.2)], 2.0, 0.35)
            elif k == "lip":
                self.snd("lip")
            elif k == "sink":
                self.snd("sink")
            elif k == "splash":
                if th["slag"]:
                    self.snd("sizzle")
                    self.burst(e[1], e[2], 22, [(255, 220, 120), (255, 140, 40), (120, 110, 110)], 3.5, 0.9, 1, (3, 9))
                else:
                    self.snd("splash")
                    self.burst(e[1], e[2], 22, [(220, 240, 255), (150, 200, 250), WHITE], 3.5, 0.8, 1, (4, 10))
        if r == SUNK:
            self.finish_player()
        elif r == SPLASH:
            self.strokes += 1
            self.state, self.state_t = "splash", 0.0
            self.floats.append([b.x, b.y - 1.2, "+1 stroke", 0.0, (255, 150, 130)])
        elif r == STOPPED:
            if self.strokes >= MAX_STROKES:
                self.finish_player(picked=True)
            else:
                self.begin_aim()

    def fx_step(self):
        keep = []
        for p in self.parts:
            p.t += DT
            if p.t >= p.life:
                continue
            p.x += p.vx * DT
            p.y += p.vy * DT
            p.z += p.vz * DT
            p.vz -= (6 if p.kind == 2 else 20) * DT
            if p.z < 0:
                p.z, p.vz = 0.0, 0.0
                p.vx *= 0.7
                p.vy *= 0.7
            keep.append(p)
        self.parts = keep[-400:]
        for f in self.floats:
            f[3] += DT
        self.floats = [f for f in self.floats if f[3] < 1.6]

    # --- numbers -----------------------------------------------------------------------------------
    def par_so_far(self, upto=None):
        upto = self.hole_i + 1 if upto is None else upto
        return sum(get_hole(*h).par for h in self.holes[:upto])

    def to_par(self, p):
        played = [(s, get_hole(*self.holes[i]).par) for i, s in enumerate(p.card) if s is not None]
        return sum(s - par for s, par in played)

    def standings(self):
        return sorted(self.players, key=lambda p: (p.total(), p.i))


# =============================================================================================
# The caddie: tries putts with the game's own physics (it sees the course like a player does) and picks one
# that leaves the pebble closest to the cup along the green. A small, seeded wobble keeps it human.
# =============================================================================================
class Bot:
    WOBBLE_A = math.radians(1.5)
    WOBBLE_P = 0.065

    def __init__(self, g, seed=None):
        self.g = g
        self.rnd = random.Random(seed if seed is not None else 0)
        self.done = True
        self.gen = None
        self.T = 0
        self.shot = None
        self.sims = 0

    def begin(self, H, x, y, T, aim0):
        self.H, self.x, self.y, self.T = H, x, y, T
        self.aim0 = aim0
        self.gen = self.plan()
        self.done = False
        self.shot = None
        self.sims = 0
        return True

    def work(self, budget):
        end = None if budget is None else time.perf_counter() + budget
        while not self.done:
            try:
                next(self.gen)
            except StopIteration:
                self.done = True
                break
            if end is not None and time.perf_counter() >= end:
                break

    def est(self, b):
        H = self.H
        d = H.nav_dist(b.x, b.y)
        if d < 0.5:
            v = 1.0
        else:
            v = 1.0 + min(3.0, (d - 0.5) / 13.0) + (0.12 if d > 2.5 else 0.0)
        k = H.kind_at(b.x, b.y)
        if k == SAND:
            v += 0.35
        elif k == ICE:
            v += 0.08
        return v

    def value(self, a, p):
        r, b, n = simulate(self.H, self.x, self.y, a, p, self.T)
        self.sims += 1
        if r == SUNK:
            return 0.0
        if r == SPLASH:
            return self.v0 + 1.25
        return self.est(b)

    def plan(self):
        H, x, y = self.H, self.x, self.y
        self.v0 = self.est(Ball(x, y))
        tried = {}

        def tryit(a, p):
            key = (round(a % TAU, 5), round(p, 4))
            if key not in tried:
                tried[key] = self.value(a % TAU, p)
            return tried[key]

        cx, cy = H.cup
        dcup = math.hypot(cx - x, cy - y)
        acup = math.atan2(cy - y, cx - x)
        f = H.fric[H.kind_at(x, y)]
        anav = self.path_angle()
        if H.has_movers:          # moving arms and gates: pick the best moment to strike first
            heads = [a for a in (anav, acup) if a is not None]
            best_t, best_v = self.T, 9.0
            T0 = self.T
            for off in (0, 30, 60, 90, 120):
                self.T = T0 + off
                v = min(self.value(a + math.radians(da), p) for a in heads for da in (-3, 0, 3)
                        for p in (0.3, 0.5, 0.7, 0.9))
                if v < best_v - 0.02:
                    best_t, best_v = self.T, v
                yield
            self.T = best_t
        # 1. straight at the cup, with the speed it takes (a little firmer, a little softer)
        if ray_clear(H, x, y, cx, cy):
            p0 = (math.sqrt(2 * f * dcup) + 1.2) / VMAX
            for da in (0.0, -0.6, 0.6, -1.2, 1.2):
                for k in (0.85, 0.95, 1.05, 1.15, 1.3, 1.5):
                    tryit(acup + math.radians(da), clamp(p0 * k, 0.03, 1.0))
            yield
        # 2. along the green's best path: towards the farthest point of it that can be seen
        if anav is not None:
            for da in (0, -2, 2, -4, 4):
                for p in (0.2, 0.3, 0.42, 0.55, 0.7, 0.85, 1.0):
                    tryit(anav + math.radians(da), p)
            yield
        # 3. a ring of angles at five powers
        n = 0
        for i in range(72):
            a = i * TAU / 72
            for p in (0.22, 0.4, 0.6, 0.8, 1.0):
                tryit(a, p)
                n += 1
            if i % 6 == 5:
                yield
        # 4. refine the best few
        for rnd_ in range(2):
            best = sorted(tried.items(), key=lambda kv: kv[1])[:6]
            for (a, p), v in best:
                if v == 0.0 and rnd_ == 1:
                    continue
                step = math.radians(1.2 if rnd_ == 0 else 0.5)
                for da in (-2, -1, 1, 2):
                    for k in (0.94, 1.0, 1.06):
                        tryit(a + da * step, clamp(p * k, 0.03, 1.0))
                for k in (0.9, 0.95, 1.05, 1.1):
                    tryit(a, clamp(p * k, 0.03, 1.0))
                yield
        # 5. robust: prefer a putt whose neighbours are good too
        best = sorted(tried.items(), key=lambda kv: kv[1])[:8]
        scored = []
        for (a, p), v in best:
            around = [tryit(a + math.radians(da), clamp(p * k, 0.03, 1.0))
                      for da, k in ((-1.6, 1.0), (1.6, 1.0), (0.0, 0.92), (0.0, 1.08), (-1.1, 0.95), (1.1, 1.05))]
            scored.append((0.3 * v + 0.7 * sum(around) / 6, a, p))
            yield
        scored.sort()
        _, a, p = scored[0]
        a += self.rnd.gauss(0, self.WOBBLE_A)
        p = clamp(p * (1 + self.rnd.gauss(0, self.WOBBLE_P)), 0.03, 1.0)
        self.shot = (a, p)
        self.best_v = scored[0][0]

    def path_angle(self):
        """Heading towards the farthest visible point on the descent of the distance map."""
        H = self.H
        w, h, dist = H.nav()
        n = H.NAV
        x, y = self.x, self.y
        i, j = int(x * n), int(y * n)
        best = None
        for _ in range(160):
            cur = dist[j * w + i] if 0 <= i < w and 0 <= j < h else 1e9
            nxt = None
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    i2, j2 = i + di, j + dj
                    if (di or dj) and 0 <= i2 < w and 0 <= j2 < h and dist[j2 * w + i2] < cur:
                        cur = dist[j2 * w + i2]
                        nxt = (i2, j2)
            if nxt is None:
                break
            i, j = nxt
            px, py = (i + 0.5) / n, (j + 0.5) / n
            if math.hypot(px - x, py - y) > 1.0 and ray_clear(H, x, y, px, py):
                best = (px, py)
        if best is None:
            return None
        return math.atan2(best[1] - y, best[0] - x)

    def steer(self):
        """While waiting for the planned moment: turn the aim line round and swing the meter, like a player."""
        g = self.g
        a, p = self.shot
        left = (self.T - g.tick) * DT
        k = clamp(1 - (left - 0.7) / max(0.1, LEAD - 0.9), 0, 1)
        da = (a - self.aim0 + math.pi) % TAU - math.pi
        g.aim = self.aim0 + da * (k * k * (3 - 2 * k))
        g.bot_meter = p * clamp(1 - left / 0.6, 0, 1) if left < 0.6 else None


# =============================================================================================
# Drawing. The course is painted once per hole and window size at screen resolution (a bigger window gets
# finer grass, sand grains, plate seams, contour lines and shadows); moving things go on top every frame.
# =============================================================================================
def hsh(x, y, s=0):
    h = (x * 374761393 + y * 668265263 + s * 2147483647) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    return (h ^ (h >> 16)) & 0xFFFF


HUD_BG = (14, 16, 24)
HUD_FG = (214, 218, 232)
HUD_DIM = (140, 146, 172)
GOLD = (250, 214, 120)
LIGHT = (-0.5, -0.56, 0.66)


def layout(cols, rows, hud=True):
    """(s, ox, oy): screen pixels per unit and the top-left pixel of the 40 x 24 course."""
    top = 1 if hud else 0
    ah = (rows - 2 * top) * 2
    s = max(0.2, min(cols / FW, ah / FH))
    ox = (cols - FW * s) / 2
    oy = top * 2 + (ah - FH * s) / 2
    return s, ox, oy


def blend(px, x, y, c, a, W, H):
    if 0 <= x < W and 0 <= y < H:
        row = px[y]
        row[x] = mix(row[x], c, a)


def lit_sphere(cv, cx, cy, rad, base, spec=0.8, dark=(10, 10, 18)):
    """A shaded ball at screen coordinates (light from the top left)."""
    W, H = cv.W, cv.H
    if rad < 0.75:
        x, y = int(cx), int(cy)
        if 0 <= x < W and 0 <= y < H:
            cv.px[y][x] = mix(base, WHITE, 0.25)
        return
    lo = mix(base, dark, 0.6)
    hi = mix(base, WHITE, 0.45)
    y0, y1 = max(0, int(math.floor(cy - rad))), min(H - 1, int(math.ceil(cy + rad)))
    x0, x1 = max(0, int(math.floor(cx - rad))), min(W - 1, int(math.ceil(cx + rad)))
    r2 = rad * rad
    for py in range(y0, y1 + 1):
        dy = (py + 0.5 - cy) / rad
        row = cv.px[py]
        for px in range(x0, x1 + 1):
            dx = (px + 0.5 - cx) / rad
            d = dx * dx + dy * dy
            if d > 1.0:
                continue
            nz = math.sqrt(1 - d)
            l = dx * LIGHT[0] + dy * LIGHT[1] + nz * LIGHT[2]
            if l < 0.3:
                c = mix(lo, base, max(0.0, (l + 0.4) / 0.7))
            elif l < 0.85:
                c = mix(base, hi, (l - 0.3) / 0.55)
            else:
                c = mix(hi, WHITE, (l - 0.85) / 0.15 * spec)
            row[px] = c


def capsule(cv, s, ox, oy, x1, y1, x2, y2, r, paint, mask=None):
    """Rasterise a thick segment (world units) and call paint(u across -1..1, a along in units, old colour)."""
    W, H = cv.W, cv.H
    X1, Y1, X2, Y2 = ox + x1 * s, oy + y1 * s, ox + x2 * s, oy + y2 * s
    R = r * s
    dx, dy = X2 - X1, Y2 - Y1
    L2 = dx * dx + dy * dy or 1e-9
    L = math.sqrt(L2)
    nx, ny = -dy / L, dx / L
    px0, px1 = max(0, int(min(X1, X2) - R - 1)), min(W - 1, int(max(X1, X2) + R + 1))
    py0, py1 = max(0, int(min(Y1, Y2) - R - 1)), min(H - 1, int(max(Y1, Y2) + R + 1))
    R2 = R * R
    for py in range(py0, py1 + 1):
        row = cv.px[py]
        fy = py + 0.5 - Y1
        for px in range(px0, px1 + 1):
            fx = px + 0.5 - X1
            t = (fx * dx + fy * dy) / L2
            tc = 0.0 if t < 0 else 1.0 if t > 1 else t
            ex, ey = fx - dx * tc, fy - dy * tc
            d2 = ex * ex + ey * ey
            if d2 > R2:
                continue
            if mask is not None:
                k = py * W + px
                if mask[k]:
                    continue
                mask[k] = 1
            u = (ex * nx + ey * ny) / R if R > 0 else 0.0
            if t < 0 or t > 1:          # round ends: across = the distance from the end
                u = math.copysign(math.sqrt(d2) / R, u) if R > 0 else 0.0
            row[px] = paint(u, tc * L / s, row[px], px, py)


def rail_painter(th, kind="rail"):
    hi, lo = th[kind]
    theme = [k for k, v in THEMES.items() if v is th][0]

    def paint(u, a, old, px, py):
        u = clamp(u, -1.0, 1.0)
        nz = math.sqrt(max(0.0, 1 - u * u))
        l = clamp(0.5 + 0.9 * (u * -0.6 + nz * 0.55) - 0.3, 0.0, 1.0)
        c = mix(lo, hi, l)
        if theme == "meadow":
            g = math.sin(a * 5.3 + u * 2.0 + (hsh(int(a * 3), 7) % 7)) * 0.07 + (hsh(px, py, 5) % 9 - 4) * 0.008
            c = shade(c, 1 + g)
            if abs(u) > 0.85:
                c = shade(c, 0.85)
        elif theme == "frost":
            if -0.7 < u < -0.3:
                c = mix(c, WHITE, 0.35)
            if hsh(px, py, 3) % 23 == 0:
                c = mix(c, WHITE, 0.6)
        else:
            if (a % 1.6) < 0.22 and abs(u) < 0.45:
                c = mix(c, (255, 226, 170), 0.55)
            c = shade(c, 1 + (hsh(px, py, 9) % 7 - 3) * 0.01)
        return c
    return paint


_BG = {}


def background(H, cols, rows, hud):
    key = (H.ci, H.hi, cols, rows, hud)
    bg = _BG.get(key)
    if bg is None:
        if len(_BG) > 8:
            _BG.clear()
        bg = _BG[key] = paint_course(H, cols, rows, hud)
    return bg


def paint_course(H, cols, rows, hud):
    s, ox, oy = layout(cols, rows, hud)
    th = H.theme
    theme = H.course["theme"]
    cv = Canvas(cols, rows)
    W, Hh = cv.W, cv.H
    px = cv.px
    water, belts = [], []
    fair_a, fair_b = th["fair"]
    rough, rough2 = th["rough"], th["rough2"]
    big = s >= 3.2
    inv = 1.0 / s
    gk, gw, gh = H.gk, H.gw, H.gh

    def kat(x, y):
        i, j = int(x * GRID), int(y * GRID)
        if i < 0 or j < 0 or i >= gw or j >= gh:
            return OUT
        return gk[j * gw + i]

    hills = any(z.t in ("hill", "bowl") for z in H.zones)
    for py in range(Hh):
        wy = (py + 0.5 - oy) * inv
        row = px[py]
        for pxx in range(W):
            wx = (pxx + 0.5 - ox) * inv
            if wx < 0 or wy < 0 or wx >= FW or wy >= FH:
                row[pxx] = mix(rough, (0, 0, 0), 0.55)
                continue
            i, j = int(wx * GRID), int(wy * GRID)
            n = j * gw + i
            k = gk[n]
            edge = (i == 0 or j == 0 or i == gw - 1 or j == gh - 1 or gk[n - 1] != k or gk[n + 1] != k or
                    gk[n - gw] != k or gk[n + gw] != k)
            if edge or (hills and (H.gax[n] or H.gay[n])):
                k, ax, ay = H.surface(wx, wy)
            else:
                ax, ay = H.gax[n], H.gay[n]
            hn = hsh(pxx, py, H.hi * 7 + H.ci)
            nz = (hn % 100) / 100.0
            if k == OUT:
                c = rough_px(theme, th, wx, wy, pxx, py, hn, nz, big)
            elif k == BASE or k == JUMP or k == BELT:
                if theme == "meadow":
                    c = fair_a if int((wx * 0.75 + wy * 0.66) / 2.3) % 2 else fair_b
                    if hn % 13 == 0:
                        c = shade(c, 0.9)
                    elif hn % 17 == 0:
                        c = shade(c, 1.08)
                    if big and hsh(pxx, py // 2, 3) % 11 == 0:
                        c = shade(c, 0.93)
                elif theme == "frost":
                    c = mix(fair_a, fair_b, 0.5 + 0.5 * math.sin(wx * 0.9 + math.sin(wy * 0.5) * 2.0))
                    if hn % 41 == 0:
                        c = WHITE
                    elif hn % 7 == 0:
                        c = shade(c, 0.97)
                else:
                    pi_, pj = int(wx / 5.0), int(wy / 4.0)
                    c = shade(fair_a if (pi_ + pj) % 2 else fair_b, 1 + (hsh(pi_, pj, 2) % 9 - 4) * 0.012)
                    c = shade(c, 1 + (hsh(py, pxx // 4, 4) % 5 - 2) * 0.012)
                    fx, fy = wx % 5.0, wy % 4.0
                    if fx < inv * 0.9 or fy < inv * 0.9:
                        c = shade(c, 0.66)
                    elif fx < inv * 1.9 or fy < inv * 1.9:
                        c = shade(c, 1.12)
                    elif big and min(abs(fx - 0.5), abs(fx - 4.5)) < 0.16 and min(abs(fy - 0.5), abs(fy - 3.5)) < 0.16:
                        c = (150, 156, 168)
                if k == JUMP:
                    jx, jy = H.jump_dir(wx, wy)
                    u = wx * jx + wy * jy
                    hi_, lo_ = th["rail"]
                    c = mix(lo_, hi_, 0.35 + 0.5 * ((u % 3.0) / 3.0))
                    if (u * 2.2) % 1.0 < 0.14:
                        c = shade(c, 0.72)
                elif k == BELT:
                    c = (46, 46, 52) if (wx * 0.0 + hn) % 3 else (52, 52, 58)
                    belts.append((py, pxx, c, wx, wy, ax, ay))
            elif k == SAND:
                sc = th["sand"]
                c = shade(sc, 1 + (hn % 9 - 4) * 0.025)
                if theme == "copper" and hn % 37 == 0:
                    c = (210, 96, 40)
                elif theme == "frost" and hn % 19 == 0:
                    c = WHITE
                if big and theme == "meadow" and math.sin(wx * 5 + wy * 1.5) > 0.82:
                    c = shade(c, 0.94)
                if kat(wx - 0.32, wy - 0.36) != SAND:
                    c = shade(c, 0.78 if theme != "frost" else 0.86)
                elif kat(wx + 0.3, wy + 0.34) != SAND:
                    c = shade(c, 1.07)
            elif k == WATER:
                deep, shal = th["water"][1], th["water"][0]
                near = sum(1 for ddx, ddy in ((-0.6, 0), (0.6, 0), (0, -0.6), (0, 0.6), (-1.2, 0), (1.2, 0), (0, -1.2), (0, 1.2))
                           if kat(wx + ddx, wy + ddy) != WATER)
                c = mix(deep, shal, min(1.0, near / 4))
                if kat(wx - 0.34, wy - 0.4) != WATER:
                    c = shade(c, 0.7) if not th["slag"] else mix(c, (60, 20, 10), 0.6)
                water.append((py, pxx, c, wx, wy))
            elif k == ICE:
                ic = th["ice"]
                c = mix(ic, WHITE, 0.15 + 0.12 * math.sin((wx - wy) * 0.6))
                if (wx * 0.8 - wy * 0.6) % 3.1 < 0.12 * (1 + inv):
                    c = mix(c, WHITE, 0.5)
                if hn % 53 == 0:
                    c = WHITE
                if kat(wx - 0.3, wy - 0.3) != ICE:
                    c = mix(c, WHITE, 0.45)
            else:
                c = (255, 0, 255)
            if (ax or ay) and k != OUT and k != WATER:
                lit = -(ax + ay) * 0.7071
                c = shade(c, clamp(1 + 0.05 * lit, 0.72, 1.28))
                if big and k != BELT:
                    if hills:
                        hgt = H.height(wx, wy)
                        if (hgt / 0.9) % 1.0 < 0.05 + inv * 0.25:
                            c = shade(c, 0.9)
                    if k != JUMP and chevron(wx, wy, ax, ay):
                        c = mix(c, WHITE, 0.16)
            row[pxx] = c
    # scenery off the course: bushes, trees, rocks, barrels (with shadows)
    paint_decor(cv, H, s, ox, oy, theme, th)
    # shadows of rails, blocks, posts and bumpers (down and to the right)
    mask = bytearray(W * Hh)
    sx, sy = 0.26, 0.34

    def shadow(u, a, old, px_, py_):
        return shade(old, 0.62)
    for x1, y1, x2, y2 in H.rails:
        capsule(cv, s, ox, oy, x1 + sx, y1 + sy, x2 + sx, y2 + sy, WT + 0.06, shadow, mask)
    for x, y, r, e, bump in H.circs:
        capsule(cv, s, ox, oy, x + sx * 1.3, y + sy * 1.3, x + sx * 1.3, y + sy * 1.3, r + 0.05, shadow, mask)
    # solid blocks
    for bl in H.blocks:
        hi_, lo_ = th["block"]
        bx0, by0, bx1, by1 = bbox(bl)
        for py in range(max(0, int(oy + by0 * s)), min(Hh, int(oy + by1 * s) + 1)):
            wy = (py + 0.5 - oy) * inv
            for pxx in range(max(0, int(ox + bx0 * s)), min(W, int(ox + bx1 * s) + 1)):
                wx = (pxx + 0.5 - ox) * inv
                if in_poly(bl, wx, wy):
                    hn = hsh(pxx, py, 11)
                    if theme == "meadow":
                        c = shade(mix(lo_, hi_, (hn % 100) / 100), 1.0)
                    elif theme == "copper":
                        c = (236, 190, 60) if int((wx + wy) * 1.4) % 2 else (40, 36, 34)
                        c = shade(c, 0.9 + (hn % 5) * 0.03)
                    else:
                        c = mix(hi_, lo_, (wy - by0) / max(0.1, by1 - by0))
                    px[py][pxx] = c
    # rails
    paint = rail_painter(th)
    for x1, y1, x2, y2 in H.rails:
        capsule(cv, s, ox, oy, x1, y1, x2, y2, WT, paint)
    # posts and bumpers
    for x, y, r, e, bump in H.circs:
        draw_post(cv, s, ox + x * s, oy + y * s, r * s, theme, th, bump)
    # the tee mat
    tx, ty = H.tee
    mc = {"meadow": (54, 120, 64), "frost": (120, 150, 190), "copper": (60, 64, 72)}[theme]
    for py in range(max(0, int(oy + (ty - 0.9) * s)), min(Hh, int(oy + (ty + 0.9) * s) + 1)):
        for pxx in range(max(0, int(ox + (tx - 0.9) * s)), min(W, int(ox + (tx + 0.9) * s) + 1)):
            wx, wy = (pxx + 0.5 - ox) * inv, (py + 0.5 - oy) * inv
            if abs(wx - tx) < 0.85 and abs(wy - ty) < 0.85:
                edge_ = abs(wx - tx) > 0.85 - inv * 1.1 or abs(wy - ty) > 0.85 - inv * 1.1
                px[py][pxx] = shade(mc, 1.2 if edge_ else 1.0 - 0.04 * (hsh(pxx, py) % 3))
    # the cup
    cx, cy = H.cup
    R = max(1.4, CUP_R * s)
    for py in range(max(0, int(oy + cy * s - R - 2)), min(Hh, int(oy + cy * s + R + 2))):
        for pxx in range(max(0, int(ox + cx * s - R - 2)), min(W, int(ox + cx * s + R + 2))):
            dx = (pxx + 0.5 - ox - cx * s) / R
            dy = (py + 0.5 - oy - cy * s) / R
            d = math.hypot(dx, dy)
            if d < 1.0:
                inner = clamp(0.5 + (dx + dy) * 0.5, 0, 1)
                c = mix((8, 8, 10), (46, 40, 36), inner * d)
                if d > 0.86:
                    c = mix(c, (220, 220, 214), 0.5 if dx + dy > 0 else 0.25)
                px[py][pxx] = c
            elif d < 1.0 + 1.2 / max(1.0, R):
                px[py][pxx] = shade(px[py][pxx], 1.18)
    # portals (the moving swirl comes on top every frame)
    for pxp, pyp, ex, ey, ang in H.portals:
        draw_portal_base(cv, s, ox + pxp * s, oy + pyp * s, PORTAL_R * s, theme, th)
        draw_portal_base(cv, s, ox + ex * s, oy + ey * s, PORTAL_R * s * 0.7, theme, th, exit_=True)
    return dict(px=[r[:] for r in px], water=water, belts=belts, s=s, ox=ox, oy=oy)


def chevron(wx, wy, ax, ay):
    """Little arrow heads pointing downhill on constant slopes."""
    m = math.hypot(ax, ay)
    if m < 0.5:
        return False
    ux, uy = ax / m, ay / m
    u = wx * ux + wy * uy
    v = -wx * uy + wy * ux
    cu, cv_ = u % 3.2 - 1.6, v % 3.2 - 1.6
    return abs(cv_) < 0.55 and abs(cu + abs(cv_) * 0.9 - 0.2) < 0.09


def rough_px(theme, th, wx, wy, px, py, hn, nz, big):
    rough, rough2 = th["rough"], th["rough2"]
    if theme == "meadow":
        c = mix(rough, rough2, 0.5 + 0.5 * math.sin(wx * 0.7 + math.sin(wy * 0.9) * 1.7))
        if hn % 9 == 0:
            c = shade(c, 0.85)
        elif hn % 11 == 0:
            c = shade(c, 1.15)
        if hn % 211 == 0:
            c = ((250, 240, 120), (255, 255, 255), (240, 140, 200), (170, 190, 255))[hn % 4]
        return c
    if theme == "frost":
        c = mix(rough, rough2, 0.5 + 0.5 * math.sin(wx * 0.5 + wy * 0.3 + math.sin(wx * 1.3) * 0.8))
        if hn % 97 == 0:
            c = (220, 236, 255)
        elif hn % 6 == 0:
            c = shade(c, 0.94)
        return c
    bx = wx + (0.5 if int(wy) % 2 else 0)
    c = rough if (int(bx) + int(wy)) % 3 else rough2
    c = shade(c, 1 + (hsh(int(bx), int(wy), 1) % 7 - 3) * 0.04)
    if bx % 1.0 < 0.08 or wy % 1.0 < 0.1:
        c = (20, 14, 16)
    if hn % 173 == 0:
        c = (200, 90, 40)
    return c


def paint_decor(cv, H, s, ox, oy, theme, th):
    rnd = random.Random(H.ci * 100 + H.hi)
    items = []
    gy = 0.0
    while gy < FH:
        gx = 0.0
        while gx < FW:
            x, y = gx + rnd.uniform(0.2, 2.0), gy + rnd.uniform(0.2, 2.0)
            r = rnd.uniform(0.6, 1.3)
            ok = all(H.kind_at(x + dx * r * 1.5, y + dy * r * 1.5) == OUT
                     for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (0.7, 0.7), (-0.7, 0.7), (0.7, -0.7), (-0.7, -0.7)))
            if ok and rnd.random() < 0.55:
                items.append((x, y, r, rnd.random()))
            gx += 2.4
        gy += 2.4
    px = cv.px
    W, Hh = cv.W, cv.H
    for x, y, r, q in items:          # shadows first
        X, Y, R = ox + (x + 0.35) * s, oy + (y + 0.45) * s, r * s
        for py in range(max(0, int(Y - R)), min(Hh, int(Y + R) + 1)):
            for pxx in range(max(0, int(X - R)), min(W, int(X + R) + 1)):
                if (pxx + 0.5 - X) ** 2 + (py + 0.5 - Y) ** 2 < R * R:
                    px[py][pxx] = shade(px[py][pxx], 0.7)
    for x, y, r, q in items:
        X, Y, R = ox + x * s, oy + y * s, r * s
        if theme == "meadow":
            if q < 0.6:          # a bush: a few lit lumps
                for k in range(3):
                    a = k * 2.1 + q * 5
                    lit_sphere(cv, X + math.cos(a) * R * 0.35, Y + math.sin(a) * R * 0.35, R * 0.62,
                               (60 + int(q * 40), 132, 52), 0.1)
                if R > 3 and q < 0.3:
                    for k in range(4):
                        cv.set(X + math.cos(k * 1.7) * R * 0.5, Y + math.sin(k * 1.7) * R * 0.5, (250, 120, 140))
            else:                # a stone
                lit_sphere(cv, X, Y, R * 0.55, (150, 146, 136), 0.3)
        elif theme == "frost":
            if q < 0.55:         # a snowy fir from above: a dark star with snow on its lit side
                n = 7
                for py in range(max(0, int(Y - R)), min(Hh, int(Y + R) + 1)):
                    for pxx in range(max(0, int(X - R)), min(W, int(X + R) + 1)):
                        dx, dy = pxx + 0.5 - X, py + 0.5 - Y
                        d = math.hypot(dx, dy) / R
                        a = math.atan2(dy, dx)
                        lim = 0.55 + 0.45 * abs(math.cos(a * n / 2 + q * 9))
                        if d < lim:
                            c = mix((22, 66, 60), (40, 100, 86), 1 - d)
                            if (dx + dy) < -R * 0.15 and hsh(pxx, py) % 3:
                                c = mix(c, (230, 240, 255), 0.7)
                            px[py][pxx] = c
            else:
                lit_sphere(cv, X, Y, R * 0.6, (120, 130, 150), 0.2)
                lit_sphere(cv, X - R * 0.15, Y - R * 0.2, R * 0.35, (236, 242, 255), 0.2)
        else:
            if q < 0.82:         # a barrel: rings seen from above
                lit_sphere(cv, X, Y, R * 0.6, (120, 70, 44), 0.2)
                for a10 in range(24):
                    a = a10 / 24 * TAU
                    cv.set(X + math.cos(a) * R * 0.45, Y + math.sin(a) * R * 0.45, (60, 40, 30))
            else:                # a lamp with a glow
                glow(cv, X, Y, R * 0.2, R * 1.4, (255, 170, 80), 0.35)
                lit_sphere(cv, X, Y, max(0.8, R * 0.25), (255, 220, 150), 0.6)


def glow(cv, cx, cy, r0, r1, c, k=0.5):
    W, H = cv.W, cv.H
    span = max(0.01, r1 - r0)
    for py in range(max(0, int(cy - r1)), min(H, int(cy + r1) + 1)):
        row = cv.px[py]
        dy = py + 0.5 - cy
        for px in range(max(0, int(cx - r1)), min(W, int(cx + r1) + 1)):
            d = math.sqrt((px + 0.5 - cx) ** 2 + dy * dy)
            if r0 < d < r1:
                a = 1 - (d - r0) / span
                row[px] = mix(row[px], c, a * a * k)


def draw_post(cv, s, X, Y, R, theme, th, bump, flash=0.0):
    if not bump:
        base = th["post"]
        if theme == "frost":
            lit_sphere(cv, X, Y, R, base, 0.9)
            if R > 3:
                for k in range(6):
                    a = k * TAU / 6
                    cv.line(X, Y, X + math.cos(a) * R * 0.8, Y + math.sin(a) * R * 0.8, mix(base, WHITE, 0.5))
        else:
            lit_sphere(cv, X, Y, R, base, 0.4)
        return
    base = mix(th["bumper"], WHITE, flash * 0.7)
    if theme == "meadow":      # a toadstool: red cap, white spots, a pale rim
        lit_sphere(cv, X, Y, R, base, 0.5)
        if R >= 2:
            for k in range(5):
                a = k * TAU / 5 + 0.3
                rr = R * (0.45 if k else 0.0)
                sx_, sy_ = X + math.cos(a) * rr, Y + math.sin(a) * rr
                if R >= 4:
                    lit_sphere(cv, sx_, sy_, R * 0.16, (250, 244, 236), 0.2)
                else:
                    cv.set(sx_, sy_, (250, 244, 236))
    elif theme == "frost":     # a crystal: facets
        W, H = cv.W, cv.H
        for py in range(max(0, int(Y - R)), min(H, int(Y + R) + 1)):
            for px in range(max(0, int(X - R)), min(W, int(X + R) + 1)):
                dx, dy = px + 0.5 - X, py + 0.5 - Y
                if abs(dx) + abs(dy) * 0.7 < R and abs(dx) * 0.7 + abs(dy) < R:
                    a = math.atan2(dy, dx)
                    f = int((a + math.pi) / (TAU / 6))
                    cv.px[py][px] = shade(base, (0.75, 1.25, 1.05, 0.85, 0.65, 0.95)[f % 6])
    else:                      # a spring: a brass ring round a dark coil
        lit_sphere(cv, X, Y, R, base, 0.6)
        if R >= 2:
            for k in range(int(R * 6)):
                a = k / (R * 6) * TAU
                for rr in (0.35, 0.6):
                    cv.set(X + math.cos(a) * R * rr, Y + math.sin(a) * R * rr, shade(base, 0.45))


def draw_portal_base(cv, s, X, Y, R, theme, th, exit_=False):
    base = th["portal"]
    W, H = cv.W, cv.H
    for py in range(max(0, int(Y - R - 2)), min(H, int(Y + R + 2))):
        for px in range(max(0, int(X - R - 2)), min(W, int(X + R + 2))):
            dx, dy = px + 0.5 - X, py + 0.5 - Y
            d = math.hypot(dx, dy) / max(0.5, R)
            if d < 1.0:
                if theme == "meadow":         # a burrow: dark hole in a ring of dug earth
                    c = mix((14, 10, 6), (40, 28, 18), d * d) if not exit_ else mix((40, 28, 18), (90, 66, 40), d)
                elif theme == "copper":       # a pipe mouth
                    c = mix((10, 10, 12), (30, 30, 34), d) if d < 0.75 else mix((170, 110, 60), (230, 160, 90), 0.5 - (dx + dy) / max(1, R) * 0.4)
                else:
                    c = mix((8, 20, 60), base, d * d)
                    if d > 0.8:
                        c = mix(c, (200, 236, 255), 0.6)
                cv.px[py][px] = c
            elif d < 1.35 and theme == "meadow" and not exit_:
                cv.px[py][px] = mix(cv.px[py][px], (110, 80, 46), 0.75 if (dx + dy) < 0 else 0.55)


# --- every frame ---------------------------------------------------------------------------------------
def render(g, cols, rows, hud=True):
    H = g.H
    bg = background(H, cols, rows, hud)
    s, ox, oy = bg["s"], bg["ox"], bg["oy"]
    cv = Canvas(cols, 1)
    cv.rows, cv.H = rows, rows * 2
    cv.px = [r[:] for r in bg["px"]]
    th = H.theme
    theme = H.course["theme"]
    t = g.clock
    W, Hh = cv.W, cv.H
    px = cv.px
    # water shimmer or glowing slag
    if th["slag"]:
        for py, pxx, c, wx, wy in bg["water"]:
            v = math.sin(wx * 1.1 + t * 0.6 + math.sin(wy * 0.9 - t * 0.4) * 1.8) + math.sin(wy * 1.7 + t * 0.3)
            if v > 1.1:
                px[py][pxx] = mix(c, (70, 30, 24), min(0.75, (v - 1.1) * 0.9))
            elif v < -1.2:
                px[py][pxx] = mix(c, (255, 236, 160), min(0.6, (-v - 1.2) * 0.9))
    else:
        for py, pxx, c, wx, wy in bg["water"]:
            v = math.sin(wx * 1.6 + t * 1.4 + math.sin(wy * 1.2 + t * 0.6) * 1.5) * math.sin(wy * 2.1 - t * 0.9)
            if v > 0.72:
                px[py][pxx] = mix(c, WHITE, min(0.55, (v - 0.72) * 2.0))
            elif v < -0.8:
                px[py][pxx] = shade(c, 0.88)
    for py, pxx, c, wx, wy, ax, ay in bg["belts"]:
        m = math.hypot(ax, ay) or 1.0
        ux, uy = ax / m, ay / m
        u = wx * ux + wy * uy - t * 1.6
        v = abs(-wx * uy + wy * ux) % 2.0 - 1.0
        if (u + abs(v) * 0.7) % 1.4 < 0.32:
            px[py][pxx] = (122, 118, 92)
    def X(x):
        return ox + x * s

    def Y(y):
        return oy + y * s
    # bumpers that were just hit flash
    for ci, when in list(g.flash.items()):
        k = 1 - (t - when) / 0.35
        if k <= 0:
            del g.flash[ci]
            continue
        x, y, r, e, bump = H.circs[ci]
        draw_post(cv, s, X(x), Y(y), r * s * (1 + 0.15 * k), theme, th, True, k)
        glow(cv, X(x), Y(y), r * s, r * s + 1.2 * s * k, mix(th["bumper"], WHITE, 0.5), 0.5 * k)
    # portals swirl
    for pxp, pyp, ex, ey, ang in H.portals:
        for k in range(6):
            a = t * 3 + k * TAU / 6
            rr = PORTAL_R * s * (0.55 + 0.2 * math.sin(t * 2 + k))
            blend(px, int(X(pxp) + math.cos(a) * rr), int(Y(pyp) + math.sin(a) * rr), mix(th["portal"], WHITE, 0.7), 0.8, W, Hh)
        if ang is not None and s >= 2.5:
            a = math.radians(ang)
            for k in range(3):
                d = (0.9 + k * 0.45 + (t * 1.5) % 0.45) * s
                blend(px, int(X(ex) + math.cos(a) * d), int(Y(ey) + math.sin(a) * d), WHITE, 0.6 - k * 0.15, W, Hh)
    # moving arms and gates, with their shadows
    if H.has_movers:
        movs = H.movers(g.tick)
        hi_, lo_ = th["rail"]
        mc = {"meadow": ((236, 226, 206), (150, 120, 90)), "frost": ((210, 240, 255), (110, 160, 220)),
              "copper": ((200, 204, 212), (90, 94, 104))}[theme]

        def shadow(u, a, old, px_, py_):
            return shade(old, 0.6)
        mask = bytearray(W * Hh)
        for m in movs:
            capsule(cv, s, ox, oy, m[0] + 0.3, m[1] + 0.4, m[2] + 0.3, m[3] + 0.4, MT, shadow, mask)

        def arm(u, a, old, px_, py_):
            u = clamp(u, -1, 1)
            nz = math.sqrt(max(0.0, 1 - u * u))
            l = clamp(0.2 + 0.9 * (-0.6 * u + 0.55 * nz), 0, 1)
            c = mix(mc[1], mc[0], l)
            if theme == "meadow" and (a % 0.9) < 0.12:
                c = shade(c, 0.8)
            if theme == "copper" and (a * 2) % 1.0 < 0.5 and abs(u) > 0.6:
                c = mix(c, (230, 190, 60), 0.5)
            return c
        for m in movs:
            capsule(cv, s, ox, oy, m[0], m[1], m[2], m[3], MT, arm)
        for cx, cy, L, arms, om, ph, r0 in H.rotors:
            if r0 < 0.5:
                lit_sphere(cv, X(cx), Y(cy), 0.6 * s, hi_, 0.6)
    # the flag
    draw_flag(cv, g, X, Y, s)
    # the aim line
    if g.state == "aim" and not g.over:
        draw_aim(cv, g, X, Y, s)
    # the trail and the pebble
    b = g.ball
    col = g.cur.color
    for tx, ty, tt in g.trail:
        k = 1 - (t - tt) / 0.6
        blend(px, int(X(tx)), int(Y(ty)), mix(col, WHITE, 0.5), 0.35 * k, W, Hh)
    if g.state not in ("card", "over") and not (g.state == "splash" and g.state_t > 0.05) and \
            not (g.state == "sunk" and g.state_t > 0.45):
        draw_ball(cv, g, b, X, Y, s, col)
    # particles
    psz = max(1, int(s / 3))
    for p in g.parts:
        k = 1 - p.t / p.life
        xx, yy = int(X(p.x)), int(Y(p.y - p.z * 0.6))
        if psz == 1:
            blend(px, xx, yy, p.c, 0.35 + 0.65 * k, W, Hh)
        else:
            for dy_ in range(psz):
                for dx_ in range(psz):
                    blend(px, xx + dx_, yy + dy_, p.c, 0.35 + 0.65 * k, W, Hh)
    if rows > 10:
        for x, y, txt, tt, c in g.floats:
            row = int(Y(y - tt * 0.8) // 2)
            if 0 < row < rows - 1:
                cv.put(int(X(x) - len(txt) / 2), row, txt, mix(c, (30, 30, 40), max(0.0, tt - 0.9)))
    if hud:
        draw_hud(cv, g)
        draw_banners(cv, g)
    return cv


def draw_flag(cv, g, X, Y, s):
    H = g.H
    cx, cy = H.cup
    W, Hh = cv.W, cv.H
    px = cv.px
    top = 2.6
    near = g.state in ("roll",) and math.hypot(g.ball.x - cx, g.ball.y - cy) < 3.5 or g.state == "sunk"
    if near:               # the flag is pulled out while the pebble comes in: only the cup shows
        return
    flagc = {"meadow": (250, 80, 70), "frost": (255, 140, 60), "copper": (90, 200, 255)}[H.course["theme"]]
    # shadow of the pole on the ground
    for i in range(int(top * s)):
        k = i / max(1, top * s)
        blend(px, int(X(cx) + i * 0.6), int(Y(cy) + i * 0.4), (0, 0, 0), 0.35 * (1 - k), W, Hh)
    x0, y0 = X(cx), Y(cy)
    for i in range(2 if s < 3 else 0, int(top * s) + 1):
        yy = int(y0 - i)
        if 0 <= yy < Hh and 0 <= int(x0) < W:
            px[yy][int(x0)] = (236, 236, 230) if i % 3 else (190, 190, 186)
    fw, fh = max(2, 1.5 * s), max(2, 0.9 * s)
    for j in range(int(fh)):
        for i in range(int(fw)):
            wave = math.sin(i / max(1, fw) * 3.0 - g.clock * 5) * fh * 0.15 * (i / max(1, fw))
            xx, yy = int(x0 + 1 + i), int(y0 - top * s + j + wave)
            if 0 <= xx < W and 0 <= yy < Hh:
                px[yy][xx] = shade(flagc, 1.05 - 0.25 * (j / max(1, fh)) + 0.1 * math.sin(i * 0.8 - g.clock * 5))


def draw_aim(cv, g, X, Y, s):
    b = g.ball
    m = g.meter()
    if g.cur.bot:
        m = getattr(g, "bot_meter", None)
    power = m if m is not None else g.cur.preset
    pts = preview(g.H, b.x, b.y, g.aim, 2.5 + 7.5 * power)
    col = mix(g.cur.color, WHITE, 0.55)
    W, Hh = cv.W, cv.H
    total = 0.0
    spacing = max(0.45, 1.6 / s)
    nxt = BALL_R + 0.5
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        while nxt <= total + L:
            f = (nxt - total) / L if L else 0
            k = 1 - nxt / (2.5 + 7.5 * power + 0.5)
            xx, yy = X(x0 + (x1 - x0) * f), Y(y0 + (y1 - y0) * f)
            blend(cv.px, int(xx), int(yy), col, 0.25 + 0.7 * k, W, Hh)
            if s >= 4.5:
                blend(cv.px, int(xx) + 1, int(yy), col, 0.25 + 0.5 * k, W, Hh)
            nxt += spacing
        total += L


def draw_ball(cv, g, b, X, Y, s, col):
    rad = BALL_R * s
    sink = g.state == "sunk"
    if sink:
        k = clamp(g.state_t / 0.45, 0, 1)
        rad *= 1 - 0.7 * k
        col = mix(col, (20, 20, 20), k)
    z = b.z
    if not sink:
        sxx, syy = X(b.x) + (0.12 + z * 0.45) * s, Y(b.y) + (0.16 + z * 0.55) * s
        rr = rad * (1 + z * 0.1)
        W, Hh = cv.W, cv.H
        for py in range(max(0, int(syy - rr - 1)), min(Hh, int(syy + rr + 2))):
            for pxx in range(max(0, int(sxx - rr - 1)), min(W, int(sxx + rr + 2))):
                d = math.hypot(pxx + 0.5 - sxx, py + 0.5 - syy)
                if d < rr:
                    cv.px[py][pxx] = shade(cv.px[py][pxx], 0.55 + 0.25 * clamp(z * 0.5, 0, 1))
    bx, by = X(b.x), Y(b.y - z * 0.9)
    r = max(1.1, rad * (1 + z * 0.12))
    lit_sphere(cv, bx, by, r, col, 0.9)
    if s < 2.6 and not sink:                 # small windows: a bright core so the pebble always reads
        xx, yy = int(bx), int(by)
        if 0 <= xx < cv.W and 0 <= yy < cv.H:
            cv.px[yy][xx] = mix(col, WHITE, 0.45)


# --- the text on top -------------------------------------------------------------------------------
def fmt_par(d):
    return "E" if d == 0 else "%+d" % d


RES_COL = {"HOLE IN ONE": (255, 236, 120), "CONDOR": (255, 236, 120), "ALBATROSS": (255, 236, 120),
           "EAGLE": (255, 210, 110), "BIRDIE": (140, 240, 140), "PAR": (220, 224, 236), "BOGEY": (255, 170, 120),
           "PICKED UP": (255, 120, 110)}


def score_col(strokes, par):
    if strokes is None:
        return HUD_DIM
    d = strokes - par
    if strokes == 1 or d <= -2:
        return (255, 222, 110)
    return (130, 236, 130) if d == -1 else (226, 228, 238) if d == 0 else (255, 170, 120) if d == 1 else (255, 116, 106)


def meter_colour(f):
    return mix((80, 210, 110), (250, 214, 80), f / 0.6) if f < 0.6 else mix((250, 214, 80), (240, 80, 60), (f - 0.6) / 0.4)


def draw_hud(cv, g):
    cols, rows = cv.cols, cv.rows
    H = g.H
    th = H.theme
    cv.put(0, 0, " " * cols, HUD_FG, HUD_BG)
    n = len(g.holes)
    parts = [(" HOLE ", HUD_DIM), ("%d" % (g.hole_i + 1), GOLD), ("/%d" % n, HUD_DIM), ("  PAR ", HUD_DIM),
             ("%d" % H.par, GOLD), ("  " + H.name.upper(), HUD_FG)]
    x = 0
    for s_, c in parts:
        cv.put(x, 0, s_, c, HUD_BG)
        x += len(s_)
    right = H.course["name"]
    if x + len(right) + 3 <= cols:
        cv.put(cols - len(right) - 1, 0, right, th["accent"], HUD_BG)
    # bottom: whose turn, the stroke, the power meter, the others' scores
    r = rows - 1
    cv.put(0, r, " " * cols, HUD_FG, HUD_BG)
    p = g.cur
    chip = " %s " % p.name
    cv.put(0, r, chip, (16, 16, 22), p.color)
    x = len(chip) + 1
    shot = g.strokes + (1 if g.state == "aim" else 0)
    st = "shot %d" % max(1, shot)
    cv.put(x, r, st, HUD_FG, HUD_BG)
    x += len(st) + 2
    pw = clamp(cols // 4, 10, 34)
    m = g.meter()
    if p.bot:
        m = getattr(g, "bot_meter", None)
    if x + pw + 8 <= cols:
        val = m if m is not None else p.preset
        fill = int(round(val * pw))
        pre = clamp(int(p.preset * pw - 0.5), 0, pw - 1)
        for i in range(pw):
            f = (i + 0.5) / pw
            bgc = meter_colour(f) if i < fill else (34, 36, 50)
            if m is None and i < fill:
                bgc = shade(bgc, 0.7)
            ch = "|" if (i == pre and m is not None and not p.bot) else " "
            cv.put(x + i, r, ch, WHITE, bgc)
        lab = "%3d%%" % round(val * 100)
        cv.put(x + pw + 1, r, lab, GOLD if m is not None else HUD_FG, HUD_BG)
        x += pw + 7
    # the others (party) or the round so far (solo)
    if g.solo:
        tag = "round %s" % fmt_par(g.to_par(p))
    else:
        tag = "  ".join("%s %s" % (q.name, fmt_par(g.to_par(q))) for q in g.players)
    if x + len(tag) + 1 > cols:
        tag = ""
    hint = ""
    if not p.bot and g.state == "aim" and not g.paused:
        hint = "Space swing   Enter strike   Tab card" if m is None else "Space strike   X cancel"
    if hint and x + len(hint) + len(tag) + 4 <= cols:
        cv.put(x, r, hint, HUD_DIM, HUD_BG)
    if tag:
        cv.put(cols - len(tag) - 1, r, tag, HUD_FG, HUD_BG)


def banner(cv, lines, col, cols_=None):
    w = max(len(l) for l in lines) + 4
    x = max(0, (cv.cols - w) // 2)
    y = max(1, cv.rows // 2 - len(lines) // 2 - 1)
    bgc = (18, 22, 34)
    cv.box(x, y, [l.center(w - 4) for l in lines], (236, 238, 246), bgc)
    cv.put(x + 2, y + 1, lines[0].center(w - 4), col, bgc)
    if cols_:
        for j, c in cols_.items():
            cv.put(x + 2, y + 1 + j, lines[j].center(w - 4), c, bgc)


def draw_banners(cv, g):
    H = g.H
    if g.over:
        return
    if g.show_card or g.state == "card":
        draw_card(cv, g)
        return
    if g.state == "intro" and g.state_t < 2.4:
        p = g.cur
        lines = ["HOLE %d  -  %s" % (g.hole_i % 9 + 1, H.name.upper()), "%s, par %d" % (H.course["short"], H.par), "",
                 ("%s to putt" % p.name) if not g.solo else "Space: go"]
        banner(cv, lines, H.theme["accent"], {3: p.color} if not g.solo else None)
    elif g.state == "sunk" and g.state_t > 0.4:
        col = RES_COL.get(g.result, (255, 150, 120))
        lines = [g.result, "%d stroke%s" % (g.strokes, "" if g.strokes == 1 else "s")]
        if not g.solo:
            lines.append(g.cur.name)
        banner(cv, lines, col, {2: g.cur.color} if not g.solo else None)
    elif g.state == "splash" and g.state_t > 0.3:
        banner(cv, ["SIZZLE!" if H.theme["slag"] else "SPLASH!", "+1 stroke, back to the last spot"], (140, 200, 255))


def card_lines(g, final=False):
    """The scorecard as rows of (text, colour) runs."""
    part = (g.hole_i // 9) if len(g.holes) > 9 else 0
    idx = list(range(part * 9, min(len(g.holes), part * 9 + 9)))
    holes = [get_hole(*g.holes[i]) for i in idx]
    name = holes[0].course["name"] if len(g.holes) >= 9 else "PRACTICE"
    w0 = 15
    head = [(name[:w0 - 1].ljust(w0), GOLD)] + [("%3d" % (i % 9 + 1), HUD_DIM) for i in idx] + [("   TOT  +/-", HUD_DIM)]
    pars = [("PAR".ljust(w0), HUD_DIM)] + [("%3d" % h.par, HUD_FG) for h in holes] + \
           [("%6d" % sum(h.par for h in holes), HUD_FG)]
    out = [head, pars]
    for p in (g.standings() if final else g.players):
        row = [(p.name.ljust(w0), p.color)]
        for i, h in zip(idx, holes):
            s = p.card[i]
            row.append(("%3s" % ("." if s is None else s), score_col(s, h.par)))
        tot = sum(p.card[i] for i in idx if p.card[i] is not None)
        row.append(("%6d" % tot, WHITE))
        row.append(("%5s" % fmt_par(g.to_par(p)), (200, 204, 220)))
        out.append(row)
    if len(g.holes) > 9:
        out.append([("", HUD_FG)])
        out.append([("TOUR  " + "   ".join("%s %d (%s)" % (p.name, p.total(), fmt_par(g.to_par(p))) for p in g.players),
                     HUD_DIM)])
    return out


def draw_runs(cv, rows_, title=None, foot=(), edge=GOLD):
    bgc = (16, 20, 32)
    lines = [[(title, edge)]] + [[("", HUD_FG)]] if title else []
    lines = lines + rows_ + ([[("", HUD_FG)]] + [[(f, HUD_DIM)] for f in foot] if foot else [])
    w = max(sum(len(t) for t, c in l) for l in lines) + 4
    x0 = max(0, (cv.cols - w) // 2)
    y0 = max(1, cv.rows // 2 - len(lines) // 2 - 1)
    cv.put(x0, y0, " " * w, HUD_FG, bgc)
    for j, l in enumerate(lines):
        yy = y0 + 1 + j
        cv.put(x0, yy, " " * w, HUD_FG, bgc)
        tw = sum(len(t) for t, c in l)
        x = x0 + 2 + ((w - 4 - tw) // 2 if len(l) == 1 else 0)
        for t, c in l:
            cv.put(x, yy, t, c, bgc)
            x += len(t)
    cv.put(x0, y0 + len(lines) + 1, " " * w, HUD_FG, bgc)
    cv.frame(x0 * 1 - 1, y0 * 2 - 1, w + 2, (len(lines) + 2) * 2 + 2, edge)


def draw_card(cv, g):
    foot = ["Tab: back to the hole"] if g.show_card else (["Enter: next hole"] if g.hole_i + 1 < len(g.holes) else [])
    draw_runs(cv, card_lines(g), "SCORECARD", foot)


def render_over(g, cv, records=(), auto=False):
    st = g.standings()
    par = g.par_so_far(len(g.holes))
    if g.solo:
        p = st[0]
        head = "ROUND COMPLETE  -  %d strokes (%s)" % (p.total(), fmt_par(p.total() - par))
    else:
        best = st[0].total()
        win = [p.name for p in st if p.total() == best]
        head = ("%s WINS" % win[0]) if len(win) == 1 else "A TIE: " + " & ".join(win)
        head += "  -  %d strokes" % best
    birdies = sum(1 for p in g.players for i, s in enumerate(p.card)
                  if s is not None and s < get_hole(*g.holes[i]).par)
    aces = sum(1 for p in g.players for s in p.card if s == 1)
    foot = ["%d birdie%s or better, %d hole%s in one" % (birdies, "" if birdies == 1 else "s", aces, "" if aces == 1 else "s")]
    for name in records:
        foot.append("** NEW COURSE RECORD: %s **" % name)
    foot.append("auto mode: a new round starts" if auto else "Enter: again   Esc / Q: menu")
    draw_runs(cv, card_lines(g, final=True), head, foot, GOLD if records else (120, 200, 140))


# =============================================================================================
# Title demo, controls, auto mode, menu, main loop
# =============================================================================================
DEMO_HOLES = [(0, 2), (2, 1), (1, 5), (0, 4), (2, 6), (1, 2), (0, 7), (2, 7), (1, 4), (0, 8), (2, 3), (1, 7),
              (0, 3), (2, 8), (1, 0), (0, 5), (2, 2), (1, 8), (0, 1), (2, 0), (1, 3), (0, 6), (2, 5), (1, 6), (0, 0),
              (2, 4), (1, 1)]


class TitleDemo:
    """The caddie playing one hole after another behind the title (and in the launcher preview)."""

    def __init__(self, k=0):
        self.k = k
        self.new_run()

    def new_run(self):
        h = DEMO_HOLES[self.k % len(DEMO_HOLES)]
        self.g = Game(holes=[h], bots=True, seed=self.k + 1, quiet=True, demo=True)
        self.g.realtime = True
        self.g.state, self.g.state_t = "aim", 0.0
        self.k += 1
        self.age = 0.0

    def scene(self, cols, rows, dt):
        g = self.g
        self.age += dt
        g.think(0.012)
        g.update(min(dt, 0.1))
        if g.state in ("card", "over") or g.over or self.age > 60:
            self.new_run()
        return render(self.g, cols, rows, hud=False)


TURN_L, TURN_R, PW_UP, PW_DN = ("left",), ("right",), ("up", "w"), ("down", "s")


class Controls:
    """Keys to one frame's input for Game.human_input: fine turning with acceleration while held, coarse steps,
    the preset power, the swing (press / press, or hold and release where the terminal reports releases)."""

    def __init__(self, kitty):
        self.kitty = kitty
        self.held = HeldKeys(kitty, first=0.5, repeat=0.13)
        self.reset()

    def reset(self):
        self.held.clear()
        self.since = {}
        self.taps = []
        self.space_t = None
        self.last_space = -9.0
        self.released = False

    def feed(self, name, kind, now):
        if kind == "release":
            if name == " " and self.space_t is not None and now - self.space_t >= 0.3:
                self.released = True
            if name == " ":
                self.space_t = None
            self.since.pop(name, None)
            self.held.feed(name, kind, now)
            return
        if name == " ":
            if kind == "press" and (self.kitty or now - self.last_space > 0.06):
                self.taps.append(" ")
                self.space_t = now
            self.last_space = now
            self.held.feed(name, kind, now)
            return
        was = self.held.down(name)
        if kind == "press" and not was:
            self.taps.append(name)
            self.since[name] = now
        elif kind == "press" and name not in self.since:
            self.since[name] = now
        self.held.feed(name, kind, now)

    def sample(self, now, dt):
        self.held.tick(now)
        turn = power = 0.0
        out = {}
        for k in self.taps:
            if k in TURN_L:
                turn -= 0.5
            elif k in TURN_R:
                turn += 0.5
            elif k == "a":
                turn -= 15
            elif k == "d":
                turn += 15
            elif k in PW_UP:
                power += 0.01
            elif k in PW_DN:
                power -= 0.01
            elif k == " ":
                out["space"] = True
            elif k == "enter":
                out["enter"] = True
            elif k == "c":
                out["cup"] = True
            elif k == "tab":
                out["card"] = True
            elif k in ("x", "backspace"):
                out["cancel"] = True
        self.taps = []
        for names, sign, kind in ((TURN_L, -1, "t"), (TURN_R, 1, "t"), (PW_UP, 1, "p"), (PW_DN, -1, "p")):
            if self.held.down(*names):
                t0 = min((self.since.get(n, now) for n in names), default=now)
                held = now - t0
                if held > 0.28:
                    if kind == "t":
                        turn += sign * min(110.0, 10 + 90 * (held - 0.28)) * dt
                    else:
                        power += sign * min(0.7, 0.08 + 0.5 * (held - 0.28)) * dt
            else:
                for n in names:
                    self.since.pop(n, None)
        out["turn"] = turn
        out["power"] = power
        if self.released:
            out["release"] = True
            self.released = False
        self.held.take_hits()
        return out


class AutoRun:
    """Auto mode: the real game on the chosen course, every pebble played by the caddie. After the round the
    scorecard stays for a few seconds, then a new round starts. Nothing is recorded."""
    OVER_SHOW = 6.0

    def __init__(self, course, nplayers=1, sound=True, seed=None):
        self.course, self.n, self.sound, self.seed = course, nplayers, sound, seed
        self.auto = AutoMode()
        self.rounds = 0
        self.new()

    def new(self):
        self.rounds += 1
        self.g = Game(self.course, self.n, bots=True, quiet=not self.sound,
                      seed=None if self.seed is None else self.seed + self.rounds)
        self.g.realtime = True
        self.over_t = 0.0

    def key(self, k):
        a = self.auto.key(k)
        if a == "sound" and SND.toggle():
            SND.play("sound_on")
        return a

    def frame(self, dt, cols, rows, draw=True, budget=0.012):
        g = self.g
        if g.over:
            if not (self.auto.paused or self.auto.help):
                self.over_t += dt
            if self.over_t >= self.OVER_SHOW:
                self.new()
                g = self.g
        else:
            sdt = self.auto.scale(dt)
            if sdt > 0:
                g.think(budget if budget is None else min(0.03, budget * max(1.0, self.auto.speed ** 0.5)))
                g.update(sdt)
        if not draw:
            return None
        cv = render(g, cols, rows)
        if g.over:
            render_over(g, cv, auto=True)
        self.auto.banner(cv, extra="round %d" % self.rounds)
        return cv


def too_small(term):
    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (60x22).")


def run_auto(term, course, n=1):
    run = AutoRun(course, n)
    last = time.time()
    while True:
        now = time.time()
        dt, last = min(0.1, now - last), now
        for k, kind in term.events(0):
            if kind == "press" and run.key(k) == "stop":
                return
        cols, rows = term.size()
        if cols < 60 or rows < 22:
            too_small(term)
            time.sleep(0.2)
            continue
        term.write(run.frame(dt, cols, rows).emit())
        time.sleep(max(0.0, 1 / 30 - (time.time() - now)))


def course_label(c):
    return "Grand Tour (27)" if c >= TOUR else COURSES[c]["short"]


def course_key(c):
    return TOUR_KEY if c >= TOUR else COURSES[c]["key"]


def menu_items(course, party):
    return ["Play solo", "Party        < %d players >" % party, "Course       < %s >" % course_label(course), AUTO_LABEL]


def render_menu(demo, cols, rows, sel, course, party, dt, help_, kitty):
    cv = demo.scene(cols, rows, dt)
    rec = load_scores().get(GAME, {})
    bits = ["%s %d" % (k, rec[k]) for k in ("meadow", "rimewater", "copperworks", TOUR_KEY) if k in rec]
    best = ("best rounds  " + "   ".join(bits)) if bits else None
    pars = "par %d" % sum(h["par"] for c in (range(3) if course >= TOUR else (course,)) for h in COURSES[c]["holes"])
    extra = ["", "Three courses of nine holes: rails, ponds, ice,", "belts, gear arms, portals.  %s: %s" % (
        course_label(course), pars), "Keys: %s" % ("with releases (kitty protocol)" if kitty else "classic terminal mode")]
    title_screen(cv, NAME, TAGLINE, menu_items(course, party), sel, best, extra=extra,
                 keys="Up/Down choose   Left/Right change   Enter start   M %s   ? help   Esc back" % SND.label().lower(),
                 help_lines=help_lines(kitty), show_help=help_, dim=0.45)
    return cv


def record(g):
    """Each player's round on a full course (never in auto mode). Returns the names with a new record."""
    if g.demo or any(p.bot for p in g.players) or any(s is None for p in g.players for s in p.card):
        return []
    key = course_key(g.course)
    return [p.name for p in g.players if submit(GAME, key, p.total(), lower_is_better=True)]


def play(term, ctl, course, n):
    g = Game(course, n)
    ctl.reset()
    last = time.time()
    recs = []
    submitted = False
    while True:
        now = time.time()
        dt = min(0.1, now - last)
        last = now
        for name, kind in term.events():
            if kind != "press":
                ctl.feed(name, kind, now)
                continue
            if g.over:
                if name in ("q", "esc"):
                    return "menu"
                if name in ("enter", " "):
                    SND.play("start")
                    return "again"
                continue
            if g.show_card and name in ("esc", "tab"):
                g.show_card = False
                continue
            a = shared_key(name, g.paused)
            if a == "pause":
                g.paused = True
                g.swing = None
                ctl.reset()
                SND.play("pause")
            elif a == "resume":
                g.paused = g.help = False
                ctl.reset()
                last = time.time()
            elif a == "quit":
                return "menu"
            elif a == "help":
                g.help = not g.help
                g.paused = True
                ctl.reset()
            elif a == "sound":
                if SND.toggle():
                    SND.play("sound_on")
            elif a is None:
                ctl.feed(name, kind, now)
        cols, rows = term.size()
        if cols < 60 or rows < 22:
            too_small(term)
            g.paused = g.paused or not g.over
            time.sleep(0.2)
            last = time.time()
            continue
        if not g.paused:
            g.update(dt, ctl.sample(now, dt))
        if g.over and not submitted:
            submitted = True
            recs = record(g)
        cv = render(g, cols, rows)
        if g.paused:
            overlay(cv, help_lines(ctl.kitty) if g.help else PAUSE_LINES + ["", SND.label()])
        elif g.over:
            render_over(g, cv, recs)
        term.write(cv.emit())
        time.sleep(max(0.0, 1 / 30 - (time.time() - now)))


def main():
    with KeyTerminal() as term:
        ctl = Controls(term.kitty)
        demo = TitleDemo()
        sel, course, party, help_ = 0, 0, 2, False
        last = time.time()
        while True:
            now = time.time()
            cols, rows = term.size()
            if cols < 60 or rows < 22:
                too_small(term)
                if any(k in ("q", "esc") for k, kind in term.events(0.3) if kind == "press"):
                    return
                last = time.time()
                continue
            term.write(render_menu(demo, cols, rows, sel, course, party, min(0.1, now - last), help_, ctl.kitty).emit())
            last = now
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
                elif k in ("down", "s", "tab"):
                    sel = (sel + 1) % 4
                    SND.play("menu")
                elif k in ("up", "w"):
                    sel = (sel - 1) % 4
                    SND.play("menu")
                elif k in ("left", "a", "right", "d"):
                    step = 1 if k in ("right", "d") else -1
                    if sel == 1:
                        party = (party - 2 + step) % 3 + 2
                    else:
                        course = (course + step) % 4
                    SND.play("menu")
                elif k == "m":
                    if SND.toggle():
                        SND.play("sound_on")
                elif k in ("enter", " "):
                    SND.play("start")
                    go = True
            if not go:
                continue
            if sel == 3:
                run_auto(term, course, 1)
                last = time.time()
                continue
            n = party if sel == 1 else 1
            while play(term, ctl, course, n) == "again":
                pass
            ctl.reset()
            last = time.time()


# =============================================================================================
# Self-test
# =============================================================================================
def play_bot(holes, n=1, seed=1, limit_s=900):
    """The caddie plays holes headless (deterministic). Returns the game."""
    g = Game(holes=holes, nplayers=n, bots=True, seed=seed, quiet=True)
    t = 0
    while not g.over and t < limit_s / DT:
        g.step()
        t += 1
    return g


def selftest():
    t0 = time.time()
    global submit

    def no_scores(*a, **k):
        raise AssertionError("the self-test must not write scores")
    submit = no_scores
    # 1. the courses: 27 holes, tee and cup on the green and clear, the cup reachable, movers inside the course
    assert len(COURSES) == 3 and all(len(c["holes"]) == 9 for c in COURSES)
    feats = {}
    for ci in range(3):
        for hi in range(9):
            H = get_hole(ci, hi)
            for what, (x, y) in (("tee", H.tee), ("cup", H.cup)):
                k = H.kind_at(x, y)
                assert k in (BASE, ICE), "%s: %s on surface %d" % (H.name, what, k)
                assert all(seg_dist2(x, y, *r) > (BALL_R + WT + 0.1) ** 2 for r in H.rails), "%s: %s at a rail" % (H.name, what)
            assert H.nav_dist(*H.tee) < 98, "%s: the cup cannot be reached from the tee" % H.name
            assert 2 <= H.par <= 4
            for m in H.movers(0) + H.movers(97):
                for x, y in ((m[0], m[1]), (m[2], m[3])):
                    assert 0 < x < FW and 0 < y < FH, H.name
            for px_, py_, ex, ey, ang in H.portals:
                assert H.kind_at(ex, ey) not in (OUT, WATER), "%s: a portal leads nowhere" % H.name
            for z in H.zones:
                feats[z.t] = feats.get(z.t, 0) + 1
            feats["rotor"] = feats.get("rotor", 0) + len(H.rotors)
            feats["gate"] = feats.get("gate", 0) + len(H.gates)
            feats["portal"] = feats.get("portal", 0) + len(H.portals)
            feats["bumper"] = feats.get("bumper", 0) + sum(1 for c in H.circs if c[4])
            feats["angled rails"] = feats.get("angled rails", 0) + sum(1 for x1, y1, x2, y2 in H.rails if x1 != x2 and y1 != y2)
    print("courses: 3 x 9 holes, par %s; %s" % ("/".join(str(sum(h["par"] for h in c["holes"])) for c in COURSES),
                                                ", ".join("%d %s" % (v, k) for k, v in sorted(feats.items()))))
    # 2. physics: full-power strikes in every direction never leave the green (no tunnelling through rails)
    rnd = random.Random(5)
    shots = esc = 0
    for ci in range(3):
        for hi in range(9):
            H = get_hole(ci, hi)
            for k in range(24):
                while True:
                    x, y = rnd.uniform(1, FW - 1), rnd.uniform(1, FH - 1)
                    if H.kind_at(x, y) not in (OUT, WATER) and ray_clear(H, x, y, x + 0.01, y):
                        break
                b = Ball(x, y, 0, 0)
                a = rnd.uniform(0, TAU)
                b.vx, b.vy = math.cos(a) * VMAX * 1.4, math.sin(a) * VMAX * 1.4
                for i in range(900):
                    r = step_ball(H, b, i * 7)
                    if not H.on_green(b.x, b.y):
                        esc += 1
                        break
                    if r != MOVING:
                        break
                shots += 1
    assert esc == 0, "%d of %d pebbles escaped through a rail" % (esc, shots)
    print("physics: %d strikes at 140%% power on all holes, none escaped through a rail" % shots)
    # the cup: slow enough drops, too fast lips out
    H = get_hole(0, 0)
    cx, cy = H.cup
    r, b, n = simulate(H, cx - 4, cy, 0.0, (math.sqrt(2 * H.fric[BASE] * 4) + 1.0) / VMAX, 0)
    assert r == SUNK, "a gentle putt did not drop"
    b = Ball(cx - 3, cy, 18.0, 0)
    for i in range(12):
        r = step_ball(H, b, i)
        assert r != SUNK, "a fast pebble dropped"
        if b.x > cx + 1.5:
            break
    print("cup: a gentle putt drops, a pebble at 18 units/s lips out")
    # water: a stroke penalty and back to the spot
    g = Game(holes=[(0, 3)], seed=1, quiet=True)
    g.begin_aim()
    g.strike(math.radians(-10), 0.62)
    for _ in range(600):
        g.step()
        if g.state != "roll":
            break
    assert g.state == "splash" and g.strokes == 2, "the pond did not cost a stroke (%s, %d)" % (g.state, g.strokes)
    for _ in range(100):
        g.step()
    assert g.state == "aim" and (g.ball.x, g.ball.y) == H.tee or (g.ball.x, g.ball.y) == get_hole(0, 3).tee
    # the ramp makes the pebble fly over the pond
    g = Game(holes=[(0, 3)], seed=1, quiet=True)
    g.begin_aim()
    g.strike(0.0, 1.0)
    flew = False
    for _ in range(900):
        g.step()
        flew = flew or g.ball.air
        if g.state != "roll":
            break
    assert flew and g.state != "splash", "the ramp did not carry the pebble over the pond"
    # portals, ice, sand, belts, bumpers
    H = get_hole(0, 4)
    r, b, n = simulate(H, 7.5, 8.0, math.radians(90), 0.3, 0)
    assert b.x > 28, "the burrow did not carry the pebble (%.1f, %.1f)" % (b.x, b.y)
    H = get_hole(1, 0)
    _, b1, _ = simulate(H, 12, 9.6, 0.0, 0.25, 0)
    H2 = get_hole(0, 0)
    _, b2, _ = simulate(H2, 8, 12, 0.0, 0.25, 0)
    assert b1.x - 12 > 2 * (b2.x - 8), "ice is not slippery"
    H = get_hole(2, 0)
    _, b, _ = simulate(H, 14, 14, 0.0, 0.4, 0)
    assert b.y < 13.5, "the belt did not push"
    H = get_hole(0, 5)
    bx, by, br = H.spec["bumpers"][0]
    b = Ball(bx - 2, by, 3.0, 0)
    for i in range(60):
        step_ball(H, b, i)
    assert b.vx < -3, "a bumper did not kick"
    # a slope too steep to rest on: the pebble rolls back
    H = get_hole(1, 6)
    _, b, _ = simulate(H, 20, 14, -math.pi / 2, 0.05, 0)
    assert b.y > 18, "the avalanche slope did not roll the pebble down"
    # the sliding gate pushes the pebble aside instead of letting it through
    print("rules: pond penalty and return, the ramp jump, burrow portal, ice, belts, bumpers, steep slopes")
    # 3. scoring and turns
    assert result_name(1, 3) == "HOLE IN ONE" and result_name(2, 3) == "BIRDIE" and result_name(5, 3) == "DOUBLE BOGEY"
    g = Game(0, 3, seed=2, quiet=True)
    g.players[0].card[0], g.players[1].card[0], g.players[2].card[0] = 4, 2, 3
    g.state = "card"
    g.next_hole()
    assert [g.players[i].name for i in g.order] == ["SKY", "GOLD", "CORAL"], "the honour order is wrong"
    g = Game(holes=[(1, 6)], seed=3, quiet=True)
    g.begin_aim()
    for _ in range(MAX_STROKES):
        if g.state != "aim":
            break
        g.strike(math.pi / 2, 0.03)
        for _ in range(600):
            g.step()
            if g.state != "roll":
                break
        for _ in range(100):
            if g.state == "aim":
                break
            g.step()
    assert g.cur.card[0] == MAX_STROKES or g.players[0].card[0] == MAX_STROKES, "no pick-up after %d strokes" % MAX_STROKES
    print("scoring: names, honour order, pick-up after %d strokes" % MAX_STROKES)
    # 4. the caddie plays every hole with the real physics
    tot_all = 0.0
    tsum = time.time()
    for ci in range(3):
        tot = par = 0
        line = []
        for hi in range(9):
            g = play_bot([(ci, hi)], 1, seed=ci * 9 + hi + 1)
            s = g.players[0].card[0]
            assert g.over and s is not None and s < MAX_STROKES, "%s: the caddie did not finish (%s)" % (g.H.name, s)
            tot += s
            par += g.H.par
            line.append(str(s))
        tot_all += tot
        print("caddie: %-15s %s = %d (par %d, %s)" % (COURSES[ci]["name"], " ".join(line), tot, par, fmt_par(tot - par)))
        assert abs(tot - par) <= 7, "the caddie is far from par on %s" % COURSES[ci]["name"]
    print("caddie: 27 holes in %.1f s" % (time.time() - tsum))
    # 5. controls
    c = Controls(False)
    c.feed("right", "press", 0.0)
    a = c.sample(0.01, 0.01)
    assert abs(a["turn"] - 0.5) < 1e-9
    for i in range(20):
        c.feed("right", "press", 0.5 + i * 0.033)
    b = c.sample(1.2, 0.033)
    assert b["turn"] > 0.5, "holding Right does not turn faster"
    c.feed(" ", "press", 2.0)
    assert c.sample(2.01, 0.01).get("space")
    c.feed(" ", "press", 2.03)              # a classic key repeat, not a second tap
    assert not c.sample(2.04, 0.01).get("space")
    k = Controls(True)
    k.feed(" ", "press", 0.0)
    k.sample(0.01, 0.01)
    k.feed(" ", "release", 0.8)
    assert k.sample(0.81, 0.01).get("release"), "kitty hold-and-release did not strike"
    g = Game(holes=[(0, 0)], seed=4, quiet=True)
    g.begin_aim()
    g.human_input({"space": True})
    for _ in range(int(SWING_T / 2 / DT)):
        g.step()
    g.human_input({"space": True})
    assert g.state == "roll" and 0.4 < g.last_power < 0.6, "the swing meter strike (%.2f)" % g.last_power
    print("controls: taps, held acceleration, classic repeat filter, kitty release, swing meter")
    # 6. rendering at every size
    timing = []
    nfr = 0
    for cols, rows in ((60, 22), (80, 24), (100, 32), (120, 40), (240, 70)):
        tr = te = 0.0
        frames = 0
        for ci, hi in ((0, 2), (0, 8), (1, 5), (1, 7), (2, 1), (2, 7), (2, 8), (0, 3)):
            g = play_bot([(ci, hi)], 2, seed=hi, limit_s=4)
            for st in ("aim", "roll", "sunk", "splash", "card"):
                g.state, g.state_t = st, 1.0
                background(g.H, cols, rows, True)
                a = time.time()
                cv = render(g, cols, rows)
                b_ = time.time()
                cv.emit(True)
                tr += b_ - a
                te += time.time() - b_
                frames += 1
            overlay(cv, help_lines(True))
            g.over = True
            render_over(g, cv, ["CORAL"])
            cv.emit(True)
        nfr += frames
        timing.append((cols, rows, tr / frames * 1000, te / frames * 1000))
    d = TitleDemo()
    for cols, rows in ((60, 22), (120, 40), (24, 8), (40, 12), (30, 9)):
        if rows >= 20:
            render_menu(d, cols, rows, 1, 3, 3, 0.05, False, True).emit(True)
        else:
            d.scene(cols, rows, 0.05).emit(True)
    for _ in range(150):
        d.scene(30, 9, 0.1)
    print("rendering: %d frames at 60x22 .. 240x70 (+ title, preview, overlays)" % nfr)
    for cols, rows, r_, e_ in timing:
        print("  %3dx%-3d render %5.1f ms  emit %5.1f ms  = %5.1f ms per frame" % (cols, rows, r_, e_, r_ + e_))
    # 7. auto mode: pause, speed, stop; nothing recorded
    run = AutoRun(0, 2, sound=False, seed=7)
    run.key(" ")
    snap = run.g.tick
    for _ in range(30):
        run.frame(1 / 30, 80, 24, draw=False)
    assert run.g.tick == snap, "auto mode ran on while paused"
    run.key(" ")
    for _ in range(5):
        run.key("+")
    assert run.auto.speed == 8.0
    for i in range(900):
        run.frame(1 / 30, 80 + i % 3 * 20, 24 + i % 2 * 8, draw=i % 60 == 0, budget=None)
    assert run.key("esc") == "stop"
    print("auto mode: 30 s at x8, %s hole %d, round %d, nothing recorded" % (
        COURSES[run.course]["short"], run.g.hole_i + 1, run.rounds))
    # 8. the screenshot is deterministic
    a, b = screenshot(80, 24), screenshot(80, 24)
    assert a.px == b.px and a.text == b.text, "the screenshot is not deterministic"
    print("screenshot: deterministic")
    print("Self-test ok (%.1f s)" % (time.time() - t0))


def screenshot(cols=100, rows=32):
    """README picture: real play by the caddie (seed 2) on Willow Meadow hole 3, Mill Sails, two players:
    SKY's pebble rolling past the mill sails after CORAL's turn. Quiet, no files written."""
    was, SND.enabled = getattr(SND, "enabled", None), False
    try:
        g = Game(0, 2, bots=True, seed=2, quiet=True)
        for _ in range(int(240 / DT)):
            g.step()
            if g.hole_i == 2 and g.turn == 1 and g.state == "roll" and g.state_t > 0.55:
                break
        return render(g, cols, rows)
    finally:
        if was is not None:
            SND.enabled = was


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--auto" in sys.argv:
        with KeyTerminal() as _term:
            run_auto(_term, 0, 1)
    else:
        main()
