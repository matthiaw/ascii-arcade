#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""SCAFFOLD - climb the tower, dodge what the Wrecker throws.

Night shift on an unfinished skyscraper. A runaway demolition robot, the Wrecker, has taken the top of the
scaffold and hurls oil drums, gears, crates, hot rivets and counterweights down at the rigger who climbs up to
switch it off. Five kinds of stage - sloped girders, conveyor decks, lift shafts, a windy crane yard and the
breaker floor where its power is cut. After the fifth the Wrecker topples - and reboots the next night, faster.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
In terminals with the kitty keyboard protocol (kitty, WezTerm, Ghostty, recent iTerm2) keys are read with their
releases; elsewhere a key counts as held while the terminal repeats it.
"""
import math
import random
import sys
import time

from arcadekit import (PAUSE_LINES, Canvas, HeldKeys, KeyTerminal, clamp, footer, load_scores, mix, overlay, shade,
                       shared_key, submit, title_screen)
from arcadesound import Sound

GAME = "scaffold"
SW, SH = 28, 20                 # the stage in tiles; every tile is T x T pixels (T grows with the window)
DT = 1 / 60                     # physics step
WALK, CLIMB = 4.6, 2.6          # tiles per second
JUMP_V, GRAV = 9.0, 30.0        # a fixed arc: 1.35 tiles high, 0.6 s, about 2.8 tiles far
FALL_LIMIT = 2.1                # dropping further than this (from the highest point) is fatal
PH, PW = 1.45, 0.32             # player height, half width
EXTRA_LIFE = 10000
STAGE_NAMES = ["THE GIRDERS", "THE SORTING DECK", "THE LIFT SHAFTS", "THE CRANE YARD", "THE BREAKERS"]
STAGE_HINTS = ["climb to the kill switch", "ride the belts up to the kill switch", "ride the lifts up to the kill switch",
               "cross the gaps on the crane beams", "pull all six breakers"]
HAZ_SIZE = {"drum": (0.42, 0.84), "hot": (0.42, 0.84), "gear": (0.48, 0.96), "spark": (0.36, 0.74),
            "crate": (0.44, 0.86), "rivet": (0.3, 0.4), "weight": (0.46, 0.8)}
SMASH_PTS = {"drum": 300, "hot": 500, "crate": 300, "rivet": 300, "gear": 500, "spark": 500, "weight": 800}


# =============================================================================================
# Sound: a chiptune bank
# =============================================================================================
def _beat(f, bass):
    return [dict(w="square", f=f, d=0.05, v=0.15, duty=0.25), dict(w="tri", f=bass, d=0.1, v=0.32, at=0),
            dict(w="noise", f=7000, d=0.02, v=0.05, at=0)]


def _arp(fs, d=0.05, v=0.3, w="tri", last=0.18):
    out = [dict(w=w, f=f, d=d, v=v) for f in fs[:-1]]
    return out + [dict(w=w, f=fs[-1], d=last, v=v, vib=(7, 0.15))]


SND = Sound(GAME, {
    "step": [dict(w="tri", f=196, d=0.018, v=0.11)],
    "step2": [dict(w="tri", f=165, d=0.018, v=0.11)],
    "climb": [dict(w="square", f=330, d=0.022, v=0.08, duty=0.25)],
    "climb2": [dict(w="square", f=294, d=0.022, v=0.08, duty=0.25)],
    "jump": [dict(w="square", f=262, f2=523, d=0.09, v=0.2, duty=0.25), dict(w="tri", f=784, d=0.04, v=0.1)],
    "land": [dict(w="noise", f=500, f2=120, d=0.04, v=0.15)],
    "hop": [dict(w="tri", f=988, d=0.05, v=0.3), dict(w="tri", f=1319, d=0.1, v=0.3)],
    "hop2": [dict(w="tri", f=988, d=0.04, v=0.3), dict(w="tri", f=1319, d=0.04, v=0.3), dict(w="tri", f=1760, d=0.14, v=0.3)],
    "thud": [dict(w="noise", f=160, f2=60, d=0.12, v=0.2), dict(w="tri", f=82, f2=50, d=0.1, v=0.22, at=0)],
    "roll": [dict(w="noise", f=110, d=0.09, v=0.1, r="lin")],
    "grab": [dict(w="square", f=150, f2=210, d=0.08, v=0.13, duty=0.3)],
    "throw": [dict(w="saw", f=190, f2=85, d=0.14, v=0.22), dict(w="noise", f=900, f2=300, d=0.1, v=0.12, at=0)],
    "wild": [dict(w="square", f=440, f2=880, d=0.12, v=0.18, duty=0.25), dict(w="square", f=440, f2=880, d=0.12, v=0.18, duty=0.25)],
    "stomp": [dict(w="noise", f=260, f2=40, d=0.32, v=0.5), dict(w="tri", f=72, f2=38, d=0.3, v=0.45, at=0)],
    "smash": [dict(w="noise", f=2600, f2=200, d=0.14, v=0.4), dict(w="square", f=330, f2=110, d=0.1, v=0.22, duty=0.3, at=0),
              dict(w="tri", f=1568, d=0.06, v=0.18)],
    "w0": _beat(523, 131), "w1": _beat(392, 98), "w2": _beat(659, 131), "w3": _beat(494, 123),
    "wrench": _arp([523, 659, 784, 1047], 0.05, 0.26, "square", 0.12),
    "item": _arp([1047, 1319, 1568, 2093], 0.045, 0.28),
    "oneup": _arp([784, 988, 1175, 1568, 1175, 1568, 1976], 0.06, 0.3, "square", 0.3),
    "warn": [dict(w="square", f=1175, d=0.04, v=0.18), dict(w="square", f=1175, d=0.04, v=0.18, at=0.08)],
    "spark": [dict(w="noise", f=6000, f2=2500, d=0.16, v=0.13), dict(w="square", f=1400, f2=2200, d=0.1, v=0.09, duty=0.125, at=0)],
    "burn": [dict(w="noise", f=900, f2=200, d=0.3, v=0.2, r="lin"), dict(w="tri", f=110, f2=70, d=0.25, v=0.2, at=0)],
    "pull": [dict(w="tri", f=196, f2=98, d=0.08, v=0.35), dict(w="square", f=880, d=0.05, v=0.2, duty=0.25),
             dict(w="square", f=660, d=0.14, v=0.2, duty=0.25)],
    "zap": [dict(w="noise", f=8000, f2=3000, d=0.08, v=0.12), dict(w="square", f=120, d=0.08, v=0.08, duty=0.1, at=0)],
    "gust": [dict(w="noise", f=250, f2=900, d=0.7, v=0.12, r="lin")],
    "clang": [dict(w="square", f=740, f2=700, d=0.16, v=0.18, duty=0.4), dict(w="noise", f=3000, d=0.05, v=0.14, at=0)],
    "flip": [dict(w="square", f=600, d=0.04, v=0.14, duty=0.25), dict(w="square", f=450, d=0.06, v=0.14, duty=0.25)],
    "die": [dict(w="square", f=988, f2=880, d=0.08, v=0.25, duty=0.25), dict(w="square", f=784, f2=698, d=0.08, v=0.25, duty=0.25),
            dict(w="square", f=622, f2=554, d=0.08, v=0.25, duty=0.25), dict(w="tri", f=440, f2=110, d=0.5, v=0.38, r="lin"),
            dict(w="noise", f=400, f2=80, d=0.3, v=0.18, at=0.24)],
    "clear": [dict(w="square", f=f, d=0.08, v=0.24, duty=0.25) for f in (523, 659, 784, 659, 784)] +
             [dict(w="tri", f=1047, d=0.45, v=0.4, vib=(6, 0.2), r="lin"), dict(w="tri", f=523, d=0.45, v=0.25, at=0.4, r="lin")],
    "ending": [dict(w="square", f=f, d=0.1, v=0.24, duty=0.25) for f in (392, 523, 659, 784, 659, 784, 1047)] +
              [dict(w="tri", f=1047, d=0.7, v=0.4, vib=(6, 0.25), r="lin"), dict(w="tri", f=659, d=0.7, v=0.28, at=0.7, r="lin"),
               dict(w="tri", f=784, d=0.7, v=0.24, at=0.7, r="lin")],
    "crash": [dict(w="noise", f=1200, f2=40, d=0.9, v=0.6), dict(w="tri", f=90, f2=30, d=0.8, v=0.5, at=0)],
    "powerdown": [dict(w="saw", f=440, f2=40, d=1.0, v=0.25, r="lin")],
    "over": [dict(w="tri", f=392, d=0.18, v=0.4), dict(w="tri", f=349, d=0.18, v=0.4), dict(w="tri", f=311, d=0.18, v=0.4),
             dict(w="tri", f=262, f2=196, d=0.7, v=0.42, r="lin")],
    "menu": [dict(w="tri", f=660, d=0.025, v=0.2)],
    "start": [dict(w="square", f=392, d=0.05, v=0.28, duty=0.25), dict(w="square", f=523, d=0.05, v=0.28, duty=0.25),
              dict(w="square", f=784, d=0.14, v=0.3, duty=0.25)],
    "pause": [dict(w="tri", f=523, f2=392, d=0.07, v=0.22)],
    "sound_on": [dict(w="tri", f=440, d=0.06, v=0.35), dict(w="tri", f=880, d=0.12, v=0.35)],
})


def help_lines(kitty=True):
    mode = (["Your terminal reports key releases: you walk exactly as long",
             "as you hold a direction."] if kitty else
            ["Classic keys: a tap walks a little, holding walks on, the",
             "other direction turns at once."])
    return ["SCAFFOLD - keys", "",
            "Left / Right  (A / D)     walk",
            "Up / Down  (W / S)        climb a ladder (stand in front of it)",
            "Space / Z                 jump (a fixed arc - aim before you go)",
            "Esc / P                   pause menu (Q there: quit, M sound)",
            "?                         this help", ""] + mode + [
            "",
            "Jump drums, crates and sparks for points. Grab a hanging",
            "wrench to smash them for 8 seconds (no climbing meanwhile).",
            "Falls further than your jump are fatal. The bonus counts",
            "down; it is yours when you reach the kill switch.",
            "Extra rigger at %d points." % EXTRA_LIFE]


# =============================================================================================
# The stages: surfaces (girders, belts, live rails), ladders, lifts, crane beams, hooks
# =============================================================================================
class Seg:
    """A straight walkable surface from (x0, ya) to (x1, yb); y grows downwards."""
    __slots__ = ("x0", "x1", "ya", "yb", "kind", "belt", "flip", "phase", "rail", "idx", "down")

    def __init__(self, x0, ya, x1, yb, kind="girder", belt=0.0, flip=0.0, phase=0.0, rail=None):
        self.x0, self.ya, self.x1, self.yb = x0, ya, x1, yb
        self.kind, self.belt, self.flip, self.phase, self.rail = kind, belt, flip, phase, rail
        self.down = 1 if yb > ya + 0.05 else -1 if ya > yb + 0.05 else 0   # which way things roll

    def y(self, x):
        x = self.x0 if x < self.x0 else self.x1 if x > self.x1 else x
        return self.ya + (self.yb - self.ya) * (x - self.x0) / (self.x1 - self.x0)

    def speed(self, t):
        if not self.belt:
            return 0.0
        if not self.flip:
            return self.belt
        return self.belt if int((t + self.phase) // self.flip) % 2 == 0 else -self.belt

    def flip_warn(self, t):
        return self.flip and (t + self.phase) % self.flip > self.flip - 1.2

    def live(self, t):
        if not self.rail:
            return False
        period, on, ph = self.rail
        return (t + ph) % period < on

    def rail_warn(self, t):
        if not self.rail:
            return False
        period, on, ph = self.rail
        return (t + ph) % period > period - 0.7


class Ladder:
    __slots__ = ("x", "ytop", "ybot", "broken", "ybreak", "goal")

    def __init__(self, x, ytop, ybot, broken=False, goal=False):
        self.x, self.ytop, self.ybot, self.broken, self.goal = x, ytop, ybot, broken, goal
        self.ybreak = ytop + (ybot - ytop) * 0.5 if broken else ytop


class Lift:
    """A shaft of lift cars that keep moving one way (speed < 0: up) and wrap around."""

    def __init__(self, x0, x1, ytop, ybot, speed, n, phase=0.0):
        self.x0, self.x1, self.ytop, self.ybot, self.speed, self.n, self.phase = x0, x1, ytop, ybot, speed, n, phase

    def cars(self, t):
        L = self.ybot - self.ytop
        out = []
        for i in range(self.n):
            off = (abs(self.speed) * t + self.phase + i * L / self.n) % L
            y = self.ybot - off if self.speed < 0 else self.ytop + off
            out.append((i, self.x0, self.x1, y, 0.0, self.speed))
        return out


class Beam:
    """A steel beam a crane carries back and forth across a gap."""

    def __init__(self, cx, y, w, amp, om, ph=0.0):
        self.cx, self.y, self.w, self.amp, self.om, self.ph = cx, y, w, amp, om, ph
        self.x0, self.x1, self.ytop, self.ybot = cx - amp - w / 2, cx + amp + w / 2, y, y

    def cars(self, t):
        c = self.cx + self.amp * math.sin(self.om * t + self.ph)
        vx = self.amp * self.om * math.cos(self.om * t + self.ph)
        return [(0, c - self.w / 2, c + self.w / 2, self.y, vx, 0.0)]


class Hook:
    """A crane hook swinging on its chain."""

    def __init__(self, px, py, length, amp, om, ph=0.0):
        self.px, self.py, self.length, self.amp, self.om, self.ph = px, py, length, amp, om, ph

    def angle(self, t):
        return self.amp * math.sin(self.om * t + self.ph)

    def bob(self, t):
        a = self.angle(t)
        return self.px + self.length * math.sin(a), self.py + self.length * math.cos(a)


class Stage:
    def __init__(self, kind):
        self.kind = kind
        self.name, self.hint = STAGE_NAMES[kind], STAGE_HINTS[kind]
        self.segs, self.ladders, self.plats, self.hooks = [], [], [], []
        self.items, self.wrenches, self.breakers = [], [], []
        self.goal = None              # (x0, x1, y) of the kill-switch ledge
        self.switch_x = None
        self.start = (2.0, 19.5)
        self.robot = (4.0, 4.2, 1)
        self.furnace = None           # (x, y): drums rolling in feed the fire
        self.smelter = None           # (x0, x1, y): a pit things fall into
        self.chutes = []
        self.chute_zone = None        # (x0, x1, y): where counterweights crash through
        self.wind = False
        self.route = []
        self.robot_segs = set()

    # --- building ------------------------------------------------------------------------------
    def seg(self, x0, ya, x1, yb, **kw):
        s = Seg(x0, ya, x1, yb, **kw)
        s.idx = len(self.segs)
        self.segs.append(s)
        return s

    def ladder(self, x, top, bot, broken=False, goal=False):
        L = Ladder(x, top.y(x), bot.y(x), broken, goal)
        self.ladders.append(L)
        return L

    def item(self, kind, x, s):
        self.items.append(dict(kind=kind, x=x, y=s.y(x), taken=False))

    def wrench(self, x, s):
        self.wrenches.append(dict(x=x, y=s.y(x) - 1.62, floor=s.y(x), taken=False))

    # --- queries -------------------------------------------------------------------------------
    def support(self, x, y, t, tol=0.5, cars=True):
        """The surface under (x, y) within tol: (y, ref, vx, vy) or None. ref: ('s', i) or ('c', plat, car)."""
        best, bd = None, tol
        for s in self.segs:
            if s.x0 <= x <= s.x1:
                ys = s.y(x)
                d = abs(ys - y)
                if d <= bd:
                    best, bd = (ys, ("s", s.idx), 0.0, 0.0), d
        if cars:
            for pi, p in enumerate(self.plats):
                for ci, x0, x1, cy, vx, vy in p.cars(t):
                    if x0 <= x <= x1:
                        d = abs(cy - y)
                        if d < bd - 0.02 or best is None and d <= bd:      # a girder wins a tie
                            best, bd = (cy, ("c", pi, ci), vx, vy), d
        return best

    def land(self, x, y0, y1, t, cars=True, skip=None):
        """The first surface a falling thing crosses going from y0 down to y1 at x: (y, ref) or None."""
        best = None
        for s in self.segs:
            if s.x0 <= x <= s.x1 and s.idx != skip:
                ys = s.y(x)
                if y0 <= ys + 0.02 and y1 >= ys and (best is None or ys < best[0]):
                    best = (ys, ("s", s.idx))
        if cars:
            for pi, p in enumerate(self.plats):
                for ci, x0, x1, cy, vx, vy in p.cars(t):
                    if x0 <= x <= x1:
                        prev = cy - vy * DT
                        if y0 <= prev + 0.03 and y1 >= cy - 0.01 and (best is None or cy < best[0]):
                            best = (cy, ("c", pi, ci))
        return best

    def belt_at(self, ref, t):
        return self.segs[ref[1]].speed(t) if ref and ref[0] == "s" else 0.0

    def ladder_grab(self, x, y, dy):
        for L in self.ladders:
            if abs(x - L.x) > 0.42:
                continue
            if dy < 0 and L.ybreak < y - 0.1 and y <= L.ybot + 0.3:
                return L
            if dy > 0 and not L.broken and abs(y - L.ytop) < 0.3:
                return L
        return None


def stage_girders():
    st = Stage(0)
    F0 = st.seg(0, 19.5, 28, 19.0)
    F1 = st.seg(0, 16.0, 25, 16.8)
    F2 = st.seg(3, 13.4, 28, 12.6)
    F3 = st.seg(0, 9.6, 25, 10.4)
    F4 = st.seg(3, 7.2, 28, 6.4)
    F5 = st.seg(0, 4.2, 19, 4.2)
    G = st.seg(11.5, 1.8, 16.5, 1.8, kind="goal")
    st.ladder(21, F1, F0)
    st.ladder(9, F1, F0, broken=True)
    st.ladder(5, F2, F1)
    st.ladder(15, F2, F1, broken=True)
    st.ladder(19, F3, F2)
    st.ladder(9, F3, F2, broken=True)
    st.ladder(7, F4, F3)
    st.ladder(15, F4, F3, broken=True)
    st.ladder(17, F5, F4)
    st.ladder(10, F5, F4, broken=True)
    st.ladder(14, G, F5, goal=True)
    st.goal, st.switch_x = (11.5, 16.5, 1.8), 15.6
    st.start = (6.5, F0.y(6.5))
    st.robot = (4.4, 4.2, 1)
    st.furnace = (1.1, F0.y(1.1))
    st.item("toolbox", 24, F2)
    st.item("hat", 24, F4)
    st.item("lunch", 2.2, F1)
    st.wrench(12, F1)
    st.wrench(22, F3)
    st.route = [("up", 21), ("up", 5), ("up", 19), ("up", 7), ("up", 17), ("up", 14), ("go", 15.0)]
    return st


def stage_deck():
    st = Stage(1)
    st.seg(0, 19.5, 12.4, 19.5, kind="belt", belt=1.3)
    B0R = st.seg(15.6, 19.5, 28, 19.5, kind="belt", belt=-1.3)
    F1L = st.seg(0, 15.6, 11, 15.6, kind="belt", belt=1.2)
    F1R = st.seg(17, 15.6, 28, 15.6, kind="belt", belt=-1.2)
    F2 = st.seg(4, 11.6, 24, 11.6, kind="belt", belt=1.4, flip=7.0)
    F3L = st.seg(0, 7.6, 11, 7.6, kind="belt", belt=1.2)
    F3R = st.seg(17, 7.6, 28, 7.6, kind="belt", belt=-1.2)
    F4a = st.seg(0, 4.0, 9, 4.0)
    F4b = st.seg(10, 4.0, 18, 4.0)
    F4c = st.seg(19, 4.0, 28, 4.0)
    G = st.seg(22, 1.6, 27, 1.6, kind="goal")
    B0L = st.segs[0]
    st.ladder(3, F1L, B0L)
    st.ladder(25, F1R, B0R)
    st.ladder(7, F2, F1L)
    st.ladder(21, F2, F1R)
    st.ladder(8, F3L, F2)
    st.ladder(20, F3R, F2)
    st.ladder(2, F4a, F3L)
    st.ladder(26, F4c, F3R)
    st.ladder(24.5, G, F4c, goal=True)
    st.goal, st.switch_x = (22, 27, 1.6), 26.0
    st.start = (1.5, 19.5)
    st.robot = (14.0, F4b.y(14), 1)
    st.smelter = (12.4, 15.6, 19.5)
    st.chutes = [9.5, 18.5]
    st.item("toolbox", 26.6, F1R)
    st.item("lunch", 4.5, F3L)
    st.item("hat", 22, B0R)
    st.wrench(14, F2)
    st.wrench(22.5, F1R)
    st.route = [("up", 3), ("up", 7), ("up", 20), ("up", 26), ("up", 24.5), ("go", 25.4)]
    return st


def stage_lifts():
    st = Stage(2)
    L0 = st.seg(0, 19.5, 6.0, 19.5)
    M2 = st.seg(8.0, 10.0, 15.0, 10.0)
    R1 = st.seg(17.0, 13.5, 28, 13.5)
    R2 = st.seg(19, 9.0, 28, 9.0)
    T = st.seg(10, 4.2, 28, 4.2)
    G = st.seg(11, 1.8, 15.5, 1.8, kind="goal")
    st.plats.append(Lift(6.0, 8.0, 5.6, 20.6, -1.5, 3))
    st.plats.append(Lift(15.0, 17.0, 5.6, 20.6, 1.5, 3, phase=2.0))
    st.ladder(26, R2, R1)
    st.ladder(20.5, T, R2)
    st.ladder(13, G, T, goal=True)
    st.goal, st.switch_x = (11, 15.5, 1.8), 11.9
    st.start = (2.0, 19.5)
    st.robot = (25.6, 4.2, -1)
    st.chute_zone = (8.7, 10.3, 10.0)
    st.item("toolbox", 1.0, L0)
    st.item("lunch", 12.2, M2)
    st.item("hat", 24, R2)
    st.wrench(22, R1)
    st.route = [("go", 5.4), ("ride", 0, 5.4, 1, 10.0, 1), ("go", 14.4), ("ride", 1, 14.4, 1, 13.5, 1),
                ("up", 26), ("up", 20.5), ("up", 13), ("go", 12.4)]
    st.T = T
    return st


def stage_crane():
    st = Stage(3)
    st.seg(0, 19.5, 10, 19.5)
    st.seg(18, 19.5, 28, 19.5)
    F1a = st.seg(0, 15.4, 9, 15.7)
    F1b = st.seg(15, 15.7, 28, 15.4)
    F2 = st.seg(0, 11.3, 27, 11.7)
    F3 = st.seg(2, 7.6, 26, 7.3)
    F4 = st.seg(0, 4.0, 20, 4.0)
    G = st.seg(18.5, 1.8, 25, 1.8, kind="goal")
    st.plats.append(Beam(14.0, 19.5, 3.2, 2.65, 0.8))
    st.plats.append(Beam(12.0, 15.7, 3.0, 1.75, 0.9, 1.0))
    st.ladder(20, F1b, st.segs[1])
    st.ladder(3, F2, F1a)
    st.ladder(25, F3, F2)
    st.ladder(12, F4, F3)
    st.ladder(6, F4, F3, broken=True)
    st.ladder(19.3, G, F4, goal=True)
    st.hooks.append(Hook(10.0, 8.0, 2.85, 1.35, 1.9, 0.0))
    st.hooks.append(Hook(17.5, 8.0, 2.85, 1.35, 1.9, math.pi))
    st.goal, st.switch_x = (18.5, 25, 1.8), 23.6
    st.start = (2.0, 19.5)
    st.robot = (3.4, 4.0, 1)
    st.wind = True
    st.item("toolbox", 25, st.segs[1])
    st.item("hat", 22, F2)
    st.item("lunch", 21, F3)
    st.wrench(24, F1b)
    st.wrench(15.5, F3)
    st.route = [("go", 9.6), ("beam", 0, 10.0, 18.0, 1), ("up", 20), ("go", 15.4), ("beam", 1, 15.0, 9.0, -1),
                ("up", 3), ("up", 25), ("up", 12), ("up", 19.3), ("go", 21.5)]
    return st


def stage_breakers():
    st = Stage(4)
    F0 = st.seg(0, 19.5, 28, 19.5)
    a1 = st.seg(1, 15.5, 10, 15.5)
    r1 = st.seg(10, 15.5, 18, 15.5, kind="rail", rail=(3.6, 1.2, 0.0))
    c1 = st.seg(18, 15.5, 27, 15.5)
    a2 = st.seg(1, 11.5, 6, 11.5)
    st.seg(6, 11.5, 12, 11.5, kind="rail", rail=(3.6, 1.2, 1.2))
    m2 = st.seg(12, 11.5, 16, 11.5)
    st.seg(16, 11.5, 22, 11.5, kind="rail", rail=(3.6, 1.2, 2.4))
    e2 = st.seg(22, 11.5, 27, 11.5)
    a3 = st.seg(1, 7.5, 10, 7.5)
    r3 = st.seg(10, 7.5, 18, 7.5, kind="rail", rail=(3.2, 1.2, 0.6))
    c3 = st.seg(18, 7.5, 27, 7.5)
    top = st.seg(9, 4.0, 19, 4.0, kind="robot")
    st.robot_segs.add(top.idx)
    st.ladder(4, a1, F0)
    st.ladder(14, r1, F0)
    st.ladder(24, c1, F0)
    st.ladder(3, a2, a1)
    st.ladder(14, m2, r1)
    st.ladder(25, e2, c1)
    st.ladder(4, a3, a2)
    st.ladder(14, r3, m2)
    st.ladder(24, c3, e2)
    for s in (a1, c1, a2, e2, a3, c3):
        x = 1.6 if s.x0 < 5 else 26.4
        st.breakers.append(dict(x=x, y=s.y(x), pulled=False, t=0.0))
    st.start = (14.0, 19.5)
    st.robot = (14.0, 4.0, 1)
    st.item("toolbox", 26, F0)
    st.item("lunch", 14, m2)
    st.item("hat", 22, c3)
    st.wrench(20.5, c1)
    st.wrench(7, a3)
    st.route = [("up", 4), ("pull", 1.6), ("pull", 26.4), ("up", 25), ("pull", 26.4), ("pull", 1.6), ("up", 4),
                ("pull", 1.6), ("pull", 26.4)]
    return st


BUILDERS = [stage_girders, stage_deck, stage_lifts, stage_crane, stage_breakers]


def build_stage(kind):
    return BUILDERS[kind % len(BUILDERS)]()


# =============================================================================================
# The rigger
# =============================================================================================
class Player:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.vx = self.vy = 0.0
        self.mode = "walk"          # walk, air, climb
        self.face = 1
        self.lad = None
        self.peak = y
        self.jump_y = y
        self.jumping = False
        self.scored = []
        self.dist = 0.0
        self.anim = 0.0
        self.ref = None
        self.climb_dir = 0


def player_step(p, st, t, inp, wind, wrench):
    """One physics step of the rigger. inp = (dx, dy, jump). Returns a list of events."""
    dx, dy, jump = inp
    ev = []
    if p.mode == "walk":
        sup = st.support(p.x, p.y, t, 0.5)
        if sup is None:
            p.mode, p.vx, p.vy, p.peak, p.jump_y, p.jumping = "air", 0.0, 0.0, p.y, p.y, False
            return ev
        ys, ref, cvx, cvy = sup
        p.ref = ref
        carry = cvx + st.belt_at(ref, t) + wind
        if dx:
            p.face = dx
        if dy and not wrench:
            L = st.ladder_grab(p.x, p.y, dy)
            if L:
                p.mode, p.lad, p.x = "climb", L, L.x
                p.ref = None
                return ev
        if jump:
            p.mode, p.vy, p.vx = "air", -JUMP_V, dx * WALK + cvx + st.belt_at(ref, t) * 0.5
            p.peak = p.jump_y = p.y
            p.jumping, p.scored = True, []
            p.ref = None
            ev.append("jump")
            return ev
        nx = clamp(p.x + (dx * WALK + carry) * DT, PW + 0.05, SW - PW - 0.05)
        sup2 = st.support(nx, p.y + cvy * DT, t, 0.5)
        if sup2 is None and not dx and wind:      # standing still you brace against a gust at an edge
            nx = clamp(p.x + (carry - wind) * DT, PW + 0.05, SW - PW - 0.05)
            sup2 = st.support(nx, p.y + cvy * DT, t, 0.5)
        if sup2:
            p.dist += abs(nx - p.x) if dx else 0.0
            p.anim += abs(dx) * DT
            p.x, p.y, p.ref = nx, sup2[0], sup2[1]
        else:
            p.x = nx
            p.mode, p.vx, p.vy, p.peak, p.jump_y, p.jumping = "air", dx * WALK * 0.5 + carry, 0.0, p.y, p.y, False
            p.ref = None
        return ev
    if p.mode == "climb":
        L = p.lad
        p.climb_dir = dy
        if dy:
            p.y += dy * CLIMB * DT
            p.anim += DT
            p.dist += CLIMB * DT
        if p.y <= L.ybreak:
            p.y = L.ybreak
            if not L.broken:
                p.mode, p.lad = "walk", None
                sup = st.support(p.x, p.y, t, 0.3)
                if sup:
                    p.y = sup[0]
                ev.append("top")
        elif p.y >= L.ybot:
            p.y = L.ybot
            p.mode, p.lad = "walk", None
        return ev
    # in the air: the arc is fixed, only wind nudges it
    p.vy += GRAV * DT
    nx = p.x + (p.vx + wind * 0.6) * DT
    ny = p.y + p.vy * DT
    if nx < PW + 0.05 or nx > SW - PW - 0.05:
        nx = clamp(nx, PW + 0.05, SW - PW - 0.05)
        p.vx = -p.vx * 0.3
    if p.vy > 0:
        land = st.land(nx, p.y, ny, t)
        if land:
            p.x, p.y, p.ref = nx, land[0], land[1]
            p.mode = "walk"
            p.jumping = False
            ev.append("fall" if land[0] - p.peak > FALL_LIMIT else "land")
            return ev
    p.x, p.y = nx, ny
    p.peak = min(p.peak, ny)
    if ny > SH + 2:
        ev.append("fall")
    return ev


# =============================================================================================
# Hazards
# =============================================================================================
class Hz:
    __slots__ = ("kind", "x", "y", "vx", "vy", "mode", "dir", "lad", "last", "spin", "age", "alive", "ox", "oy",
                 "evx", "evy", "hop", "life", "ref")

    def __init__(self, kind, x, y, mode, dir_=1, vx=0.0, vy=0.0):
        self.kind, self.x, self.y, self.mode, self.dir = kind, x, y, mode, dir_
        self.vx, self.vy = vx, vy
        self.lad = None
        self.last = None
        self.spin = 0.0
        self.age = 0.0
        self.alive = True
        self.ox, self.oy = x, y
        self.evx = self.evy = 0.0
        self.hop = None
        self.life = 0.0
        self.ref = None

    def box(self):
        hw, h = HAZ_SIZE[self.kind]
        return self.x - hw, self.y - h, self.x + hw, self.y


def overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


# =============================================================================================
# The Wrecker
# =============================================================================================
class Robot:
    def __init__(self, x, y, face):
        self.x, self.y, self.face = x, y, face
        self.state, self.st_t = "idle", 0.0
        self.timer = 1.6
        self.throws = 0
        self.until_stomp = 3
        self.item = None
        self.eye = 0.0
        self.dy = 0.0           # leaving / falling offset
        self.vy = 0.0
        self.tilt = 0.0
        self.anim = 0.0

    def box(self):
        return self.x - 2.0, self.y + self.dy - 3.5, self.x + 2.0, self.y + self.dy


# =============================================================================================
# The game
# =============================================================================================
class Game:
    def __init__(self, stage=0, night=1, demo=False, hazards=True, seed=None):
        self.rng = random.Random(seed)
        self.demo, self.hazards = demo, hazards
        self.score, self.lives, self.night = 0, 3, night
        self.stage_i = stage
        self.extra_given = False
        self.fx, self.pops = [], []
        self.over = False
        self.paused = self.help = False
        self.shake = 0.0
        self.clock = 0.0
        self.jbuf = 0.0
        self.deaths = self.clears = 0
        self.jumped = self.smashed = 0
        self.thrown = 0
        self.cause = ""
        self.hi = 0 if demo else load_scores().get(GAME, {}).get("score", 0)
        self.st = None
        self.start_stage(fresh=True)

    # --- helpers ---------------------------------------------------------------------------------
    def snd(self, name, vol=1.0, gap=0.04):
        if not self.demo:
            SND.play(name, vol, gap)

    @property
    def speed(self):
        return min(1.75, 1.0 + 0.11 * (self.night - 1))

    def add(self, pts, x=None, y=None, col=(255, 236, 140)):
        self.score += pts
        if x is not None:
            self.pops.append([x, y, "%d" % pts, self.clock + 1.0, col])
        if not self.extra_given and self.score >= EXTRA_LIFE:
            self.extra_given = True
            self.lives += 1
            self.snd("oneup")
            self.pops.append([self.player.x, self.player.y - 2.4, "1UP", self.clock + 1.6, (140, 255, 160)])

    def burst(self, x, y, n, cols, spd=3.0, up=1.5, life=0.6, grav=12.0):
        r = self.rng
        for _ in range(n):
            a = r.uniform(0, math.tau)
            s = r.uniform(0.3, 1.0) * spd
            self.fx.append([x, y, math.cos(a) * s, math.sin(a) * s - up, r.uniform(0.5, 1.0) * life, r.choice(cols), grav])

    def start_stage(self, fresh=False):
        keep = None if fresh or self.st is None or self.st.kind != self.stage_i % 5 else self.st
        st = build_stage(self.stage_i)
        if keep is not None:                       # a retry keeps what was achieved (breakers, items)
            for a, b in zip(st.breakers, keep.breakers):
                a["pulled"] = b["pulled"]
            for a, b in zip(st.items, keep.items):
                a["taken"] = b["taken"]
        self.st = st
        self.t = 0.0
        self.player = Player(*st.start)
        self.hz = []
        self.robot = Robot(*st.robot)
        self.bonus = 4000 + 1000 * min(4, self.night)
        self.bonus_t = 0.0
        self.wrench_t = 0.0
        self.beat = 0
        self.beat_t = 0.0
        self.state, self.st_t = "intro", 0.0
        self.wind, self.wind_dir, self.wind_state, self.wind_t = 0.0, 1, "calm", 4.0
        self.belt_pos = [0.0] * len(st.segs)
        self.flip_seen = [0] * len(st.segs)
        self.robot.state, self.robot.st_t = "stomp", 0.0
        self.robot.timer = 1.4
        if self.hazards and st.kind == 2:          # live wires already crawl along the right-hand ledges
            for x, s in ((23.5, st.segs[2]), (26.5, st.segs[3])):
                self.hz.append(Hz("spark", x, s.y(x), "walk", -1))

    # --- input & time ----------------------------------------------------------------------------
    def update(self, dt, inp):
        """Advance by dt seconds. inp: (dx, dy, jump) or a callable returning it per physics step."""
        if self.paused or self.over:
            return
        self.acc = getattr(self, "acc", 0.0) + min(dt, 0.1)
        while self.acc >= DT:
            self.acc -= DT
            i = inp() if callable(inp) else inp
            if i[2]:
                self.jbuf = 0.13
            self.step((i[0], i[1], self.jbuf > 0))
            if callable(inp) is False:
                inp = (inp[0], inp[1], False)
            if self.over:
                break

    def step(self, inp):
        self.clock += DT
        self.jbuf = max(0.0, self.jbuf - DT)
        self.shake = max(0.0, self.shake - DT)
        self.update_fx()
        s = self.state
        if s == "intro":
            self.st_t += DT
            self.robot_step()
            if self.st_t > 1.7:
                self.state, self.st_t = "play", 0.0
        elif s == "play":
            self.play_step(inp)
        elif s == "dying":
            self.st_t += DT
            if self.st_t > 2.0:
                if not self.demo:
                    self.lives -= 1
                if self.lives <= 0:
                    self.state, self.over = "over", True
                    self.snd("over")
                else:
                    self.start_stage()
        elif s == "clear":
            self.st_t += DT
            r = self.robot
            if self.st_t > 0.8:            # the Wrecker leaps up out of sight
                r.vy -= 40 * DT
                r.dy += r.vy * DT
                r.state = "leave"
            if self.st_t > 3.4:
                self.stage_i += 1
                self.start_stage(fresh=True)
        elif s == "ending":
            self.ending_step()

    def update_fx(self):
        keep = []
        for f in self.fx:
            f[4] -= DT
            if f[4] > 0:
                f[0] += f[2] * DT
                f[1] += f[3] * DT
                f[3] += f[6] * DT
                keep.append(f)
        self.fx = keep[-260:]
        self.pops = [p for p in self.pops if p[3] > self.clock]

    def die(self, cause):
        if self.state != "play":
            return
        self.state, self.st_t, self.cause = "dying", 0.0, cause
        self.deaths += 1
        self.wrench_t = 0.0
        self.snd("die")
        p = self.player
        self.burst(p.x, p.y - 0.8, 18, [(255, 240, 160), (255, 160, 60), (255, 255, 255)], 4.0)
        if cause == "zap":
            self.burst(p.x, p.y - 0.7, 20, [(160, 230, 255), (255, 255, 255)], 5.0)

    def play_step(self, inp):
        st, p = self.st, self.player
        self.t += DT
        t = self.t
        # belts move (and flip, with a warning)
        for s in st.segs:
            if s.belt:
                self.belt_pos[s.idx] += s.speed(t) * DT
                if s.flip:
                    k = int((t + s.phase) // s.flip)
                    if k != self.flip_seen[s.idx]:
                        self.flip_seen[s.idx] = k
                        self.snd("flip")
        if st.wind:
            self.wind_step()
        # bonus timer
        self.bonus_t += DT
        if self.bonus_t >= 2.0:
            self.bonus_t -= 2.0
            self.bonus = max(0, self.bonus - 100)
            if 0 < self.bonus <= 1000:
                self.snd("warn")
            if self.bonus <= 0:
                self.die("time")
                return
        # the rigger
        wr = self.wrench_t > 0
        ev = player_step(p, st, t, inp, self.wind, wr)
        if "jump" in ev:
            self.jbuf = 0.0
            self.snd("jump")
        if "land" in ev:
            self.snd("land")
            self.burst(p.x, p.y, 4, [(150, 140, 130)], 1.5, 0.5, 0.3, 4)
        if "fall" in ev:
            sm = st.smelter
            self.die("smelt" if sm and sm[0] < p.x < sm[1] else "fall")
            return
        if p.mode == "walk" and p.dist > 0.55:
            p.dist = 0.0
            self.snd("step" if int(p.anim * 8) % 2 else "step2", gap=0.1)
        if p.mode == "climb" and p.dist > 0.45:
            p.dist = 0.0
            self.snd("climb" if int(p.y * 2) % 2 else "climb2", gap=0.1)
        # lift cars: riding into the pulley at the top is the end of you
        if p.mode == "walk" and p.ref and p.ref[0] == "c":
            pl = st.plats[p.ref[1]]
            if isinstance(pl, Lift) and pl.speed < 0 and p.y < pl.ytop + 0.55:
                self.die("crush")
                return
        # live rails
        if p.mode == "walk" and p.ref and p.ref[0] == "s" and st.segs[p.ref[1]].live(t):
            self.die("zap")
            return
        if self.clock % 0.25 < DT:
            for s in st.segs:
                if s.rail and s.live(t) and self.rng.random() < 0.7:
                    x = self.rng.uniform(s.x0, s.x1)
                    self.fx.append([x, s.y(x) - 0.1, self.rng.uniform(-2, 2), -self.rng.uniform(1, 4), 0.25,
                                    (180, 240, 255), 10])
        # the wrench
        if self.wrench_t > 0:
            self.wrench_t -= DT
            self.beat_t -= DT
            if self.beat_t <= 0:
                self.beat_t += 0.21
                self.snd("w%d" % (self.beat % 4), gap=0.0)
                self.beat += 1
            if self.wrench_t <= 0:
                self.wrench_t = 0.0
        if self.hazards:
            self.robot_step()
            self.hazards_step()
        for h in self.st.hooks:
            self.hook_step(h)
        if self.state != "play":
            return
        self.collide()
        if self.state != "play":
            return
        self.pickups()
        # reached the kill switch?
        g = st.goal
        if g and p.mode == "walk" and g[0] <= p.x <= g[1] and abs(p.y - g[2]) < 0.2:
            self.stage_clear()

    def wind_step(self):
        self.wind_t -= DT
        if self.wind_t <= 0:
            if self.wind_state == "calm":
                self.wind_state, self.wind_t = "warn", 1.1
                self.wind_dir = self.rng.choice((-1, 1))
            elif self.wind_state == "warn":
                self.wind_state, self.wind_t = "gust", 2.6
                self.snd("gust")
            else:
                self.wind_state, self.wind_t = "calm", self.rng.uniform(3.5, 6.5) / self.speed
        target = {"calm": 0.0, "warn": 0.25, "gust": 1.5 * min(1.3, self.speed)}[self.wind_state] * self.wind_dir
        self.wind += (target - self.wind) * min(1.0, DT * 3)
        if self.wind_state != "calm" and self.rng.random() < (0.25 if self.wind_state == "warn" else 0.8):
            x = 0.0 if self.wind_dir > 0 else SW
            self.fx.append([x, self.rng.uniform(0.5, SH - 0.5), self.wind_dir * self.rng.uniform(12, 20), 0.0,
                            SW / 14.0, (90, 100, 140) if self.wind_state == "warn" else (150, 165, 210), 0.0, "streak"])

    # --- the Wrecker ---------------------------------------------------------------------------------
    def robot_step(self):
        r, st = self.robot, self.st
        r.st_t += DT
        r.anim += DT
        p = self.player
        r.eye += (clamp((p.x - r.x) / 8, -1, 1) - r.eye) * min(1, DT * 4)
        if st.kind in (1, 4):
            r.face = 1 if p.x >= r.x else -1
        spd = self.speed * (1 + 0.06 * sum(b["pulled"] for b in st.breakers))
        if r.state == "idle":
            if self.state != "play":
                return
            r.timer -= DT
            if r.timer <= 0:
                if r.until_stomp <= 0:
                    r.state, r.st_t = "stomp", 0.0
                    r.until_stomp = self.rng.randint(3, 5)
                else:
                    r.item = self.choose_throw()
                    r.state, r.st_t = "grab", 0.0
                    self.snd("grab", 0.6)
        elif r.state == "grab":
            if r.st_t > 0.4 / spd:
                r.state, r.st_t = "hold", 0.0
                if r.item in ("gear", "sball"):
                    self.snd("wild", 0.7)
        elif r.state == "hold":
            if r.st_t > max(0.32, 0.55 / spd):
                r.state, r.st_t = "throw", 0.0
                self.throw(r.item)
        elif r.state == "throw":
            if r.st_t > 0.28:
                r.state, r.st_t = "idle", 0.0
                r.item = None
                r.until_stomp -= 1
                base = [2.3, 2.1, 2.0, 2.4, 2.2][st.kind]
                r.timer = self.rng.uniform(0.6, 1.3) * base / spd
        elif r.state == "stomp":
            for at in (0.22, 0.6):
                if r.st_t - DT < at <= r.st_t:
                    self.shake = 0.28
                    self.snd("stomp")
                    for sx in (-1.1, 1.1):
                        self.burst(r.x + sx, r.y, 6, [(140, 130, 120), (100, 96, 92)], 2.5, 1.0, 0.5, 6)
            if r.st_t > 0.85:
                r.state, r.st_t = "idle", 0.0
                r.timer = 0.5

    def choose_throw(self):
        k, r = self.st.kind, self.rng.random()
        if k == 0:
            return "gear" if r < 0.13 * min(1.6, self.speed) else "hot" if r < 0.32 else "drum"
        if k == 1:
            return "crate" if r < 0.55 else "rivet"
        if k == 2:
            return "weight"
        if k == 3:
            return "gear" if r < 0.15 else "drum"
        sparks = sum(1 for h in self.hz if h.kind == "spark")
        return "sball" if r < 0.4 and sparks < 4 else "gear"

    def throw(self, item):
        r, st, p = self.robot, self.st, self.player
        self.thrown += 1
        self.snd("throw")
        spd = self.speed
        if item in ("drum", "hot"):
            x = r.x + r.face * 2.7
            self.hz.append(Hz(item, x, st.support(x, r.y, self.t, 0.6)[0], "roll", r.face))
        elif item == "gear":
            vx = clamp((p.x - r.x) * 0.25, -3.0, 3.0) or r.face * 1.5
            self.hz.append(Hz("gear", r.x + (1.6 if vx > 0 else -1.6), r.y - 3.0, "wild", 1, vx * spd, -3.5))
        elif item == "sball":
            side = 1 if self.rng.random() < 0.5 else -1
            self.hz.append(Hz("spark", r.x + side * 2.2, r.y - 2.5, "fall", side, side * self.rng.uniform(1.5, 3.5), -4.0))
        elif item in ("crate", "rivet"):
            left = (p.x < 14) if self.rng.random() < 0.7 else (p.x >= 14)
            x = st.chutes[0] if left else st.chutes[1]
            self.hz.append(Hz(item, x, r.y - 0.4, "fall", 1, 0.0, 1.0))
        elif item == "weight":
            h = Hz("weight", r.x - 2.6, r.y, "hop", -1)
            h.hop = self.new_hop(h.x)
            self.hz.append(h)

    def new_hop(self, x):
        n = self.rng.uniform(2.2, 3.3)
        return [x, n, 0.72 / min(1.5, self.speed), 0.0]      # start x, length, duration, progress

    # --- hazards -------------------------------------------------------------------------------------
    def hazards_step(self):
        st, t, p = self.st, self.t, self.player
        spd = self.speed
        new = []
        for h in self.hz:
            h.ox, h.oy = h.x, h.y
            h.age += DT
            k = h.kind
            if k in ("drum", "hot"):
                self.drum_step(h, spd)
            elif k == "gear":
                h.vy += 16 * DT
                h.x += h.vx * DT
                ny = h.y + h.vy * DT
                if h.vy > 0:
                    land = st.land(h.x, h.y, ny, t, cars=False, skip=h.last)
                    if land:
                        ny = land[0]
                        h.last = land[1][1]
                        h.vy = -5.5
                        h.vx = (1 if p.x > h.x else -1) * self.rng.uniform(1.2, 2.6) * spd
                        self.snd("clang", 0.5, 0.1)
                        self.burst(h.x, ny, 4, [(200, 200, 210), (255, 220, 120)], 2.0, 1.0, 0.3)
                h.y = ny
                if h.x < 0.6 or h.x > SW - 0.6:
                    h.vx = -h.vx
                    h.x = clamp(h.x, 0.6, SW - 0.6)
                h.spin += DT * 8 * (1 if h.vx >= 0 else -1)
            elif k == "spark":
                self.spark_step(h, spd)
            elif k in ("crate", "rivet"):
                self.cargo_step(h, new)
            elif k == "weight":
                self.weight_step(h, spd)
            if h.x < -1.5 or h.x > SW + 1.5 or h.y > SH + 1.5:
                h.alive = False
            h.evx, h.evy = (h.x - h.ox) / DT, (h.y - h.oy) / DT
        self.hz = [h for h in self.hz if h.alive] + new

    def drum_step(self, h, spd):
        st, t, p = self.st, self.t, self.player
        h.spin += DT * 9 * h.dir
        if h.mode == "roll":
            sup = st.support(h.x, h.y, t, 0.4)
            if sup is None:
                h.mode, h.vx, h.vy = "fall", h.dir * 1.4, 0.0
                return
            ys, ref, cvx, cvy = sup
            seg = st.segs[ref[1]] if ref[0] == "s" else None
            if seg and seg.down:
                h.dir = seg.down
            v = h.dir * 3.6 * spd + cvx + (st.belt_at(ref, t)) + self.wind * 0.4
            nx = h.x + v * DT
            sup2 = st.support(nx, ys + cvy * DT, t, 0.4)
            if sup2 is None:
                h.x = nx
                h.mode, h.vx, h.vy = "fall", h.dir * 1.4 + cvx, 0.0
                return
            # down a ladder? more likely when the rigger is somewhere below
            for L in st.ladders:
                if (h.x - L.x) * (nx - L.x) <= 0 and abs(L.ytop - sup2[0]) < 0.35 and not L.goal:
                    chance = 0.15 + 0.05 * (self.night - 1)
                    if p.y > L.ytop + 0.8 and abs(p.x - L.x) < 5:
                        chance += 0.3
                    if self.rng.random() < chance:
                        h.mode, h.lad, h.x, h.y = "ladder", L, L.x, L.ytop
                        return
            h.x, h.y = nx, sup2[0]
            if st.furnace and abs(h.x - st.furnace[0]) < 0.9 and abs(h.y - st.furnace[1]) < 0.8:
                h.alive = False
                self.snd("burn", 0.6, 0.1)
                self.burst(st.furnace[0], st.furnace[1] - 1.6, 14, [(255, 200, 80), (255, 120, 40), (255, 250, 200)], 3.0, 3.0, 0.7, 5)
                sparks = sum(1 for o in self.hz if o.kind == "spark")
                if h.kind == "hot" and sparks < 4:
                    self.hz.append(Hz("spark", st.furnace[0] + 0.8, st.furnace[1] - 1.8, "fall", 1, 2.2, -5.0))
                    self.snd("spark")
        elif h.mode == "fall":
            h.vy += 22 * DT
            nx, ny = h.x + h.vx * DT, h.y + h.vy * DT
            land = st.land(nx, h.y, ny, t) if h.vy > 0 else None
            if land:
                h.x, h.y = nx, land[0]
                if h.vy > 7:
                    h.vy = -h.vy * 0.28
                    self.snd("thud", 0.5, 0.12)
                    self.burst(h.x, h.y, 3, [(150, 140, 130)], 1.5, 0.5, 0.3)
                else:
                    h.mode = "roll"
                    seg = st.segs[land[1][1]] if land[1][0] == "s" else None
                    if seg and seg.down:
                        h.dir = seg.down
                return
            h.x, h.y = nx, ny
        elif h.mode == "ladder":
            h.y += 3.0 * spd * DT
            if h.y >= h.lad.ybot:
                h.y = h.lad.ybot
                h.mode = "roll"
                sup = st.support(h.x, h.y, t, 0.3)
                seg = st.segs[sup[1][1]] if sup and sup[1][0] == "s" else None
                h.dir = seg.down if seg and seg.down else self.rng.choice((-1, 1))
                self.snd("thud", 0.4, 0.12)
        elif h.mode == "fly":        # knocked away by a crane hook
            h.vy += 22 * DT
            h.x += h.vx * DT
            h.y += h.vy * DT
            if h.vy > 0:
                h.mode = "fall"

    def spark_step(self, h, spd):
        st, t, p = self.st, self.t, self.player
        h.spin += DT
        if h.mode == "fall":
            h.vy += 20 * DT
            nx, ny = h.x + h.vx * DT, h.y + h.vy * DT
            if nx < 0.5 or nx > SW - 0.5:
                h.vx = -h.vx
                nx = clamp(nx, 0.5, SW - 0.5)
            land = st.land(nx, h.y, ny, t, cars=False) if h.vy > 0 else None
            if land and st.segs[land[1][1]].kind != "goal":
                h.x, h.y, h.mode = nx, land[0], "walk"
                h.dir = 1 if p.x > h.x else -1
                self.snd("spark", 0.5, 0.2)
                return
            h.x, h.y = nx, ny
        elif h.mode == "walk":
            r = self.rng
            if r.random() < DT * 0.35:
                h.dir = -h.dir
            if abs(p.y - h.y) < 0.6 and r.random() < DT * 0.7:
                h.dir = 1 if p.x > h.x else -1
            sup = st.support(h.x, h.y, t, 0.4, cars=False)
            belt = st.belt_at(sup[1], t) if sup else 0.0
            nx = h.x + (h.dir * 1.55 * spd + belt) * DT
            sup2 = st.support(nx, h.y, t, 0.4, cars=False)
            if sup2 is None or st.segs[sup2[1][1]].kind == "goal" or nx < 0.5 or nx > SW - 0.5:
                h.dir = -h.dir
                return
            for L in st.ladders:
                if (h.x - L.x) * (nx - L.x) <= 0 and not L.goal and not L.broken and r.random() < 0.45:
                    want_up = p.y < h.y - 0.5
                    if abs(L.ybot - sup2[0]) < 0.3 and (want_up or r.random() < 0.3):
                        h.mode, h.lad, h.x, h.dir = "climb", L, L.x, -1
                        return
                    if abs(L.ytop - sup2[0]) < 0.3 and (not want_up or r.random() < 0.3):
                        h.mode, h.lad, h.x, h.dir = "climb", L, L.x, 1
                        return
            h.x, h.y = nx, sup2[0]
            if st.smelter is None and st.furnace and h.x < st.furnace[0] + 1.2 and abs(h.y - st.furnace[1]) < 0.6:
                h.dir = 1
        elif h.mode == "climb":
            L = h.lad
            h.y += h.dir * 1.3 * spd * DT
            if h.y <= L.ytop or h.y >= L.ybot:
                h.y = clamp(h.y, L.ytop, L.ybot)
                h.mode = "walk"
                h.dir = 1 if p.x > h.x else -1

    def cargo_step(self, h, new):
        st, t = self.st, self.t
        if h.mode == "ride":
            sup = st.support(h.x, h.y, t, 0.3, cars=False)
            if sup is None:
                h.mode, h.vx, h.vy = "fall", 0.0, 0.0
                return
            v = st.belt_at(sup[1], t)
            if v == 0:
                h.life += DT
                if h.life > 1.5:
                    h.alive = False
                    self.burst(h.x, h.y - 0.4, 6, [(150, 110, 60), (120, 90, 50)], 2.0, 1.0, 0.4)
                return
            nx = h.x + v * DT
            sup2 = st.support(nx, h.y, t, 0.3, cars=False)
            h.x = nx
            if sup2 is None:
                h.mode, h.vx, h.vy = "fall", v * 0.9, 0.0
            else:
                h.y = sup2[0]
        else:
            h.vy += 22 * DT
            nx, ny = h.x + h.vx * DT, h.y + h.vy * DT
            land = st.land(nx, h.y, ny, t, cars=False) if h.vy > 0 else None
            if land:
                h.x, h.y = nx, land[0]
                if h.kind == "rivet" and h.vy > 6:
                    h.vy = -h.vy * 0.3
                else:
                    h.mode = "ride"
                    if h.vy > 6:
                        self.snd("thud", 0.4, 0.12)
                return
            h.x, h.y = nx, ny
            sm = st.smelter
            if sm and sm[0] < h.x < sm[1] and h.y > sm[2] + 0.3:
                h.alive = False
                self.snd("burn", 0.4, 0.15)
                self.burst(h.x, sm[2] + 0.2, 8, [(255, 200, 80), (255, 120, 40)], 2.5, 3.0, 0.6, 6)
                sparks = sum(1 for o in self.hz if o.kind == "spark")
                if h.kind == "rivet" and sparks < 4 and self.rng.random() < 0.5:
                    side = self.rng.choice((-1, 1))
                    new.append(Hz("spark", (sm[0] + sm[1]) / 2, sm[2], "fall", side, side * 2.4, -7.5))
                    self.snd("spark")

    def weight_step(self, h, spd):
        st = self.st
        if h.mode == "hop":
            x0, n, dur, u = h.hop
            u += DT / dur
            h.x = x0 + h.dir * n * min(1.0, u)
            floor = st.robot[1]
            h.y = floor - 4 * 2.25 * min(1.0, u) * (1 - min(1.0, u))
            if u >= 1.0:
                if st.support(h.x, floor, self.t, 0.3, cars=False) is None:
                    h.mode, h.vx, h.vy = "drop", h.dir * 0.5, 0.5
                else:
                    self.snd("thud", 0.4, 0.15)
                    self.burst(h.x, floor, 3, [(140, 130, 120)], 1.5, 0.5, 0.3)
                    h.hop = self.new_hop(h.x)
                    return
            h.hop[3] = u
        else:
            h.vy += 22 * DT
            h.x += h.vx * DT
            h.y += h.vy * DT

    def hook_step(self, hk):
        bx, by = hk.bob(self.t)
        vx = hk.length * math.cos(hk.angle(self.t)) * hk.amp * hk.om * math.cos(hk.om * self.t + hk.ph)
        for h in self.hz:
            if h.kind in ("drum", "hot") and h.mode == "roll" and abs(h.x - bx) < 0.9 and abs(h.y - 0.4 - by) < 0.9:
                h.mode, h.vx, h.vy = "fly", (4.0 if vx >= 0 else -4.0), -5.0
                self.snd("clang", 0.6, 0.1)

    # --- collisions, pickups ---------------------------------------------------------------------
    def pbox(self):
        p = self.player
        return p.x - PW, p.y - PH + 0.1, p.x + PW, p.y - 0.16      # boots may brush things

    def collide(self):
        p, st = self.player, self.st
        pb = self.pbox()
        if self.wrench_t > 0:      # the swinging wrench smashes what comes close
            hx = p.x + p.face * 0.55
            wb = (hx - 0.75, p.y - 2.3, hx + 0.75, p.y + 0.05)
            for h in self.hz:
                if h.alive and overlap(wb, h.box()):
                    h.alive = False
                    pts = SMASH_PTS[h.kind]
                    if pts < 800 and self.rng.random() < 0.15:
                        pts = 800
                    self.smashed += 1
                    self.add(pts, h.x, h.y - 1.2)
                    self.snd("smash")
                    self.burst(h.x, h.y - 0.4, 16, [(255, 255, 255), (255, 220, 120), (200, 200, 210)], 4.5)
            self.hz = [h for h in self.hz if h.alive]
        for h in self.hz:
            if overlap(pb, h.box()):
                self.die("hit")
                return
        for hk in st.hooks:
            bx, by = hk.bob(self.t)
            cx, cy = clamp(bx, pb[0], pb[2]), clamp(by, pb[1], pb[3])
            if (cx - bx) ** 2 + (cy - by) ** 2 < 0.5 ** 2:
                self.die("hit")
                return
        rb = self.robot.box()
        if overlap(pb, (rb[0] + 0.3, rb[1] + 0.3, rb[2] - 0.3, rb[3])):
            self.die("robot")
            return
        if st.furnace and p.mode == "walk" and p.x < st.furnace[0] + 1.0 and abs(p.y - st.furnace[1]) < 0.6:
            self.die("burn")
            return
        # jumped over something: points
        if p.mode == "air" and p.jumping:
            for h in self.hz:
                if h in p.scored or h.kind == "gear" and h.mode == "wild":
                    continue
                hw, hh = HAZ_SIZE[h.kind]
                if abs(h.x - p.x) < hw + 0.1 and p.y < h.y - hh + 0.05 and abs(h.y - p.jump_y) < 1.3:
                    p.scored.append(h)
                    n = len(p.scored)
                    pts = 100 if n == 1 else 200 if n == 2 else 500
                    self.jumped += 1
                    self.add(pts, h.x, h.y - 1.6)
                    self.snd("hop" if n == 1 else "hop2")

    def pickups(self):
        p, st = self.player, self.st
        pb = self.pbox()
        for it in st.items:
            if not it["taken"] and overlap(pb, (it["x"] - 0.45, it["y"] - 0.7, it["x"] + 0.45, it["y"])):
                it["taken"] = True
                pts = {"toolbox": 300, "hat": 500, "lunch": 800}[it["kind"]]
                self.add(pts, it["x"], it["y"] - 1.6, (140, 230, 255))
                self.snd("item")
                self.burst(it["x"], it["y"] - 0.4, 10, [(140, 230, 255), (255, 255, 255)], 3.0)
        for w in st.wrenches:
            if not w["taken"] and p.mode != "climb" and overlap(pb, (w["x"] - 0.4, w["y"] - 0.8, w["x"] + 0.4, w["y"])):
                w["taken"] = True
                self.wrench_t = max(5.0, 8.5 - 0.5 * (self.night - 1))
                self.beat_t = 0.0
                self.snd("wrench")
                self.burst(w["x"], w["y"] - 0.4, 12, [(230, 235, 245), (255, 255, 255)], 3.0)
        for b in st.breakers:
            if not b["pulled"] and abs(p.x - b["x"]) < 0.7 and abs(p.y - b["y"]) < 0.3:
                b["pulled"], b["t"] = True, self.clock
                self.add(500, b["x"], b["y"] - 2.4)
                self.snd("pull")
                self.shake = 0.15
                self.burst(b["x"], b["y"] - 1.3, 14, [(160, 230, 255), (255, 255, 255)], 4.0)
                n = sum(x["pulled"] for x in st.breakers)
                if n in (2, 4) and self.hazards:
                    side = 1 if b["x"] < 14 else -1
                    self.hz.append(Hz("spark", b["x"] + side * 0.6, b["y"] - 1.2, "fall", side, side * 2.0, -5.0))
                    self.snd("spark")
                if n == len(st.breakers):
                    self.stage_clear()

    # --- stage end ---------------------------------------------------------------------------------
    def stage_clear(self):
        self.clears += 1
        self.add(self.bonus, self.player.x, self.player.y - 2.2, (140, 255, 160))
        self.wrench_t = 0.0
        p = self.player
        self.burst(p.x, p.y - 1.0, 30, [(255, 240, 140), (140, 255, 160), (255, 255, 255)], 5.0)
        if self.st.kind == 4:
            self.state, self.st_t = "ending", 0.0
            self.snd("powerdown")
            self.robot.state = "off"
            self.hz = [h for h in self.hz if h.kind != "spark"]
        else:
            self.state, self.st_t = "clear", 0.0
            self.robot.state, self.robot.vy = "angry", 0.0
            self.snd("clear")

    def ending_step(self):
        self.st_t += DT
        r = self.robot
        s = self.st_t
        for h in self.hz:     # what is still flying finishes its way
            h.vy += 22 * DT
            h.y += h.vy * DT
        self.hz = [h for h in self.hz if h.y < SH + 2]
        if s < 1.6:
            if self.rng.random() < 0.3:
                self.burst(r.x + self.rng.uniform(-1.5, 1.5), r.y - self.rng.uniform(0.5, 3), 3,
                           [(160, 230, 255), (255, 255, 255)], 3.0)
        elif r.state != "crashed":
            if r.state != "fall":
                r.state = "fall"
                self.shake = 0.3
                self.snd("crash", 0.6)
            r.vy += 26 * DT
            r.dy += r.vy * DT
            r.tilt = min(1.0, r.tilt + DT * 0.8)
            if r.y + r.dy > SH + 4:
                r.state = "crashed"
                self.shake = 0.6
                self.snd("crash")
                self.snd("ending")
                for i in range(5):
                    self.burst(self.rng.uniform(8, 20), SH - 0.2, 10, [(150, 140, 130), (110, 100, 96), (255, 200, 120)],
                               5.0, 4.0, 1.2, 8)
        if s > 8.0:
            self.night += 1
            self.stage_i += 1
            self.start_stage(fresh=True)


# =============================================================================================
# The autopilot: follows each stage's route, jumps or waits when something is coming
# =============================================================================================
def hz_future(h, tau, g):
    """Where hazard h will roughly be in tau seconds."""
    if h.kind == "weight" and h.mode == "hop":
        x0, n, dur, u = h.hop
        u2 = u + tau / dur
        k = int(u2)
        uu = u2 - k
        x = x0 + h.dir * n * (k + uu)
        floor = g.st.robot[1]
        if g.st.support(x0 + h.dir * n * max(1, k), floor, g.t, 0.3, cars=False) is None and k >= 1:
            ft = (u2 - 1) * dur
            return x0 + h.dir * n, floor + 0.5 * ft + 11 * ft * ft
        return x, floor - 9.0 * uu * (1 - uu)
    if h.mode in ("fall", "wild", "drop", "fly"):
        g_ = 16 if h.kind == "gear" else 22
        return h.x + h.evx * tau, h.y + h.evy * tau + 0.5 * g_ * tau * tau
    return h.x + h.evx * tau, h.y + h.evy * tau


class Bot:
    def __init__(self, g, avoid=True, greedy=True):
        self.g, self.avoid, self.greedy = g, avoid, greedy
        self.reset()

    def reset(self):
        self.i = 0
        self.ph = 0
        self.y0 = None
        self.k = 0
        self.cache = (0, 0, False)
        self.fut = []
        self.stuck = 0.0

    def route_input(self):
        g = self.g
        p, st = g.player, g.st
        if self.i >= len(st.route):
            return 0, 0, False
        step = st.route[self.i]
        kind = step[0]
        if p.mode == "air":
            return 0, 0, False
        if kind == "go":
            if abs(p.x - step[1]) < 0.18:
                self.i += 1
                return 0, 0, False
            return (1 if step[1] > p.x else -1), 0, False
        if kind == "pull":
            b = min(st.breakers, key=lambda b: abs(b["x"] - step[1]) + abs(b["y"] - p.y) * 3)
            if b["pulled"]:
                self.i += 1
                return 0, 0, False
            return (1 if step[1] > p.x else -1), 0, False
        if kind == "up":
            if p.mode == "climb":
                return 0, -1, False
            if self.y0 is not None and p.y < self.y0 - 0.8:
                self.i += 1
                self.y0 = None
                return 0, 0, False
            if abs(p.x - step[1]) > 0.2:
                self.y0 = None
                return (1 if step[1] > p.x else -1), 0, False
            self.y0 = p.y if self.y0 is None else self.y0
            return 0, -1, False
        if kind == "ride":
            _, pi, xw, don, yexit, doff = step
            pl = st.plats[pi]
            on = p.ref is not None and p.ref[0] == "c" and p.ref[1] == pi
            if self.ph == 0:
                if abs(p.x - xw) > 0.15 and not on:
                    return (1 if xw > p.x else -1), 0, False
                if on:
                    self.ph = 1
                else:
                    for ci, x0, x1, cy, vx, vy in pl.cars(g.t):
                        if pl.speed < 0 and -0.05 < cy - p.y < 0.3 or pl.speed > 0 and -0.3 < cy - p.y < 0.05:
                            self.ph = 1
                    return 0, 0, False
            if self.ph == 1:
                if not on:
                    return don, 0, False
                self.ph = 2
            if self.ph == 2:
                if not on:
                    self.ph = 3
                else:
                    car = [c for c in pl.cars(g.t) if c[0] == p.ref[2]][0]
                    edge = car[2] if doff > 0 else car[1]
                    stand = edge - doff * 0.45
                    if abs(car[3] - yexit) < 0.16:
                        self.ph = 3
                        return doff, 0, False
                    if abs(p.x - stand) > 0.12:
                        return (1 if stand > p.x else -1), 0, False
                    return 0, 0, False
            if self.ph == 3:
                if p.ref and p.ref[0] == "s" and abs(p.y - yexit) < 0.2:
                    self.ph = 0
                    self.i += 1
                    return 0, 0, False
                return doff, 0, False
        if kind == "beam":
            _, pi, xe, xf, d = step
            pl = st.plats[pi]
            on = p.ref is not None and p.ref[0] == "c" and p.ref[1] == pi
            car = pl.cars(g.t)[0]
            if self.ph == 0:
                xw = xe - d * 0.45
                if not on and abs(p.x - xw) > 0.15:
                    return (1 if xw > p.x else -1), 0, False
                near = car[1] if d > 0 else car[2]
                far = car[2] if d > 0 else car[1]
                if on or (d * (xe - near) > 0.0 and d * (far - xe) > 1.2):
                    self.ph = 1
                return 0, 0, False
            if self.ph == 1:
                if not on:
                    return d, 0, False
                self.ph = 2
            if self.ph == 2:
                if not on:
                    self.ph = 3
                else:
                    far = car[2] if d > 0 else car[1]
                    if d * (far - xf) > 0.12:
                        self.ph = 3
                        return d, 0, False
                    stand = far - d * 0.5
                    if abs(p.x - stand) > 0.15:
                        return (1 if stand > p.x else -1), 0, False
                    return 0, 0, False
            if self.ph == 3:
                if p.ref and p.ref[0] == "s" and d * (p.x - xf) > 0.2:
                    self.ph = 0
                    self.i += 1
                    return 0, 0, False
                return d, 0, False
        return 0, 0, False

    def greedy_input(self, base):
        """Little detours: a wrench or a bonus item on the same girder close by."""
        g = self.g
        p, st = g.player, g.st
        if p.mode != "walk" or self.ph != 0 or base[1] != 0 and p.mode == "climb":
            return None
        if self.i < len(st.route) and st.route[self.i][0] in ("ride", "beam"):
            return None
        if g.wrench_t <= 0:
            for w in st.wrenches:
                if not w["taken"] and abs(w["floor"] - p.y) < 0.5 and abs(w["x"] - p.x) < 4.5:
                    if abs(w["x"] - p.x) < 0.2:
                        return 0, 0, True
                    return (1 if w["x"] > p.x else -1), 0, False
        for it in st.items:
            if not it["taken"] and abs(it["y"] - p.y) < 0.5 and abs(it["x"] - p.x) < 3.5:
                return (1 if it["x"] > p.x else -1), 0, False
        return None

    def hit_time(self, dx, dy, jump, horizon=0.9):
        """When the rigger would get hit doing this (None: safe). Thrown things are looked at 0.9 s ahead,
        swinging hooks 1.6 s (long enough to walk through one's reach), live rails the whole way across."""
        g = self.g
        p, st = g.player, g.st
        wr = g.wrench_t
        sup = st.support(p.x, p.y, g.t, 0.5)
        carry = (sup[2] + st.belt_at(sup[1], g.t) + g.wind) if sup and p.mode == "walk" else 0.0
        air = 2 * JUMP_V / GRAV

        def where(tau):
            if jump:
                x = p.x + (dx * WALK + carry) * tau
                y = min(p.y, p.y - JUMP_V * tau + 0.5 * GRAV * tau * tau)
            elif p.mode == "climb" or dy:
                x, y = p.x, p.y + dy * CLIMB * tau
                if p.lad:
                    y = clamp(y, p.lad.ybreak, p.lad.ybot)
            else:
                x, y = p.x + (dx * WALK + carry) * tau, p.y
            return clamp(x, PW, SW - PW), y

        zone = st.chute_zone
        far = 1.6 if st.hooks and not jump else horizon
        for j in range(1, int(far / 0.05) + 1):
            tau = j * 0.05
            x, y = where(tau)
            pb = (x - PW - 0.1, y - PH, x + PW + 0.1, y + 0.02)
            if tau <= horizon:
                for i, h in enumerate(g.hz):
                    if wr > tau + 0.2 and h.kind != "weight" and abs(h.x - x) < 2.0:
                        continue
                    fut = self.fut[i] if i < len(self.fut) else ()
                    hx, hy = fut[j - 1] if j - 1 < len(fut) else hz_future(h, tau, g)
                    hw, hh = HAZ_SIZE[h.kind]
                    if overlap(pb, (hx - hw, hy - hh, hx + hw, hy)):
                        return tau, h.mode in ("roll", "walk", "ride") and abs(h.y - p.y) < 0.6
                if zone and zone[0] - 0.4 < x < zone[1] + 0.4 and abs(y - zone[2]) < 0.5:
                    for h in g.hz:
                        if h.kind == "weight" and (h.mode == "drop" and h.y < zone[2] + 0.5 or
                                                   h.mode == "hop" and h.x < st.T.x0 + 3.5):
                            return tau, False
            for hk in st.hooks:
                bx, by = hk.bob(g.t + tau)
                cx, cy = clamp(bx, pb[0] - 0.15, pb[2] + 0.15), clamp(by, pb[1] - 0.15, pb[3])
                if (cx - bx) ** 2 + (cy - by) ** 2 < 0.55 ** 2:
                    return tau, False
            if dx and not jump and not dy and p.mode == "walk" and tau <= 0.12:   # walking off into a deep drop
                if st.support(x, y, g.t + tau, 0.6) is None and st.land(x, y, y + FALL_LIMIT - 0.2, g.t + tau) is None:
                    return tau, False
        if st.kind == 4 and p.mode == "walk":
            if jump:      # where it lands must not be live then
                x, _ = where(air)
                s = st.support(x, p.y, g.t, 0.6, cars=False)
                if s and st.segs[s[1][1]].rail and any(st.segs[s[1][1]].live(g.t + air + d) for d in (-0.1, 0.1, 0.4)):
                    return air, False
                return None
            for j in range(0, 46):         # live rails: look along the whole way across
                tau = j * 0.05
                x, _ = where(tau)
                s = st.support(x, p.y, g.t, 0.3, cars=False)
                if s is None:
                    break
                seg = st.segs[s[1][1]]
                if seg.rail:
                    if seg.live(g.t + tau) or seg.live(g.t + tau + 0.15):
                        return max(0.05, tau), False
                elif dx == 0:
                    break
        return None

    def __call__(self):
        g = self.g
        if g.state != "play":
            return 0, 0, False
        self.k += 1
        if self.k % 2 == 0:
            return self.cache
        base = self.route_input()
        if self.greedy:
            gi = self.greedy_input(base)
            if gi is not None:
                base = gi
        out = base
        stepping = self.i < len(g.st.route) and g.st.route[self.i][0] in ("ride", "beam") and self.ph in (1, 3)
        if self.avoid and g.player.mode in ("walk", "climb") and not stepping:
            self.predict()
            out = self.choose(base)
        self.cache = (out[0], out[1], False)
        return out

    def predict(self, n=18):
        """Where every hazard will be over the next n * 0.05 s: rolling off girder ends, landing, gears
        bouncing on each girder. Computed once per decision and shared by all candidate moves."""
        g = self.g
        st = g.st
        self.fut = []
        for h in g.hz:
            k, m = h.kind, h.mode
            seq = []
            if k == "gear" and m == "wild":
                x, y, vx, vy, last = h.x, h.y, h.vx, h.vy, h.last
                for j in range(n):
                    vy += 16 * 0.05
                    nx, ny = x + vx * 0.05, y + vy * 0.05
                    if vy > 0:
                        land = st.land(nx, y, ny, g.t, cars=False, skip=last)
                        if land:
                            ny, last, vy = land[0], land[1][1], -5.5
                    if nx < 0.6 or nx > SW - 0.6:
                        vx = -vx
                    x, y = nx, ny
                    seq.append((x, y))
            elif k in ("drum", "hot", "crate", "rivet") and m in ("roll", "ride", "fall") or k == "spark" and m == "fall":
                x, y, vx, vy = h.x, h.y, h.evx, h.evy
                rolling = m != "fall"
                for j in range(n):
                    if rolling:
                        nx = x + vx * 0.05
                        sup = st.support(nx, y, g.t, 0.4, cars=False)
                        if sup is None:
                            rolling, vy, vx = False, 0.0, vx * 0.4
                            x = nx
                        else:
                            x, y = nx, sup[0]
                    else:
                        vy += 22 * 0.05
                        nx, ny = x + vx * 0.05, y + vy * 0.05
                        land = st.land(nx, y, ny, g.t, cars=False) if vy > 0 else None
                        if land:
                            ny, vy, rolling = land[0], 0.0, True
                            seg = st.segs[land[1][1]]
                            if k in ("drum", "hot"):
                                vx = seg.down * 3.6 * g.speed if seg.down else vx
                            elif k in ("crate", "rivet"):
                                vx = seg.speed(g.t)
                            else:
                                vx = 0.0
                        x, y = nx, ny
                    seq.append((x, y))
            else:
                seq = [hz_future(h, (j + 1) * 0.05, g) for j in range(n)]
            self.fut.append(seq)

    def drum_for_ladder(self, L):
        """A drum rolling towards the top of ladder L (it may come down it)."""
        for h in self.g.hz:
            if h.kind in ("drum", "hot") and h.mode == "roll" and abs(h.y - L.ytop) < 0.6:
                d = L.x - h.x
                if abs(d) < 5.0 and d * h.evx > 0:
                    return True
            if h.mode == "ladder" and h.lad is L:
                return True
        return False

    def choose(self, base):
        g = self.g
        p, st = g.player, g.st
        dx, dy, jump = base
        if p.mode == "climb":
            ht = self.hit_time(0, dy, False, 0.6)
            if ht is None:
                return base
            back = -dy if dy else 1
            return (0, back, False) if self.hit_time(0, back, False, 0.6) is None else base
        if dy < 0 and g.wrench_t <= 0:       # about to climb: not while a drum heads for the top
            L = st.ladder_grab(p.x, p.y, dy)
            if L and self.drum_for_ladder(L):
                base = dx, dy, jump = 0, 0, False
        riding = p.ref is not None and p.ref[0] == "c" and isinstance(st.plats[p.ref[1]], Lift)
        if jump:
            return base
        walk = self.hit_time(dx, dy, False)
        if walk is None or walk[1] and walk[0] >= 0.42 and not riding:
            return base           # free, or something to jump that is still far enough off
        back = (-dx, 0, False) if dx else (1, 0, False)
        if walk[1]:      # something to jump over
            cands = [(dx, 0, True), (0, 0, False), back, (-back[0], 0, False), (0, 0, True), (-dx if dx else -1, 0, True)]
        else:            # a hook, a live rail, a falling thing: rather wait
            cands = [(0, 0, False), back, (-back[0], 0, False), (dx, 0, True), (0, 0, True), (-dx if dx else -1, 0, True)]
        if riding:      # never jump off a lift car or a beam
            cands = [c for c in cands if not c[2]]
        best, bt = None, walk[0]
        for c in cands:
            if c[2] and not self.landing_ok(c[0]):
                continue
            ht = self.hit_time(*c)
            if ht is None:
                return c
            if ht[0] > bt:
                best, bt = c, ht[0]
        return best or base

    def landing_ok(self, dx):
        """A jump here lands safely (no fall too far, no gap)."""
        g = self.g
        p, st = g.player, g.st
        x = clamp(p.x + dx * WALK * 2 * JUMP_V / GRAV, PW, SW - PW)
        s = st.support(x, p.y, g.t + 0.6, 0.9)
        return s is not None


# =============================================================================================
# Drawing
# =============================================================================================
def hsh(x, y, s=0):
    h = (x * 374761393 + y * 668265263 + s * 2147483647) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    return (h ^ (h >> 16)) & 0xFFFF


STEEL = (78, 112, 156)
STEEL_HI = (160, 196, 228)
STEEL_LO = (34, 48, 78)
STEEL_HOLE = (46, 64, 98)
LADDER = (236, 196, 70)
LADDER_DARK = (150, 118, 40)
BELT = (44, 44, 54)
BELT_HI = (122, 122, 136)
HUD_BG = (12, 10, 22)
HUD_FG = (210, 212, 232)
HUD_DIM = (140, 144, 178)
GOLD = (250, 214, 120)


class View:
    def __init__(self, cv, T, ox, oy):
        self.cv, self.T, self.ox, self.oy = cv, T, ox, oy

    def X(self, x):
        return self.ox + int(math.floor(x * self.T + 0.5))

    def Y(self, y):
        return self.oy + int(math.floor(y * self.T + 0.5))

    def r(self, x, y, w, h, c):
        x0, x1 = self.X(x), self.X(x + w)
        y0, y1 = self.Y(y), self.Y(y + h)
        if x1 <= x0:
            x1 = x0 + 1
        if y1 <= y0:
            y1 = y0 + 1
        self.cv.rect(x0, y0, x1 - x0, y1 - y0, c)

    def p(self, x, y, c):
        self.cv.set(self.ox + int(math.floor(x * self.T)), self.oy + int(math.floor(y * self.T)), c)

    def line(self, x0, y0, x1, y1, c):
        self.cv.line(self.ox + x0 * self.T, self.oy + y0 * self.T, self.ox + x1 * self.T, self.oy + y1 * self.T, c)

    def thick(self, x0, y0, x1, y1, w, c):
        """A thick line as a run of small squares."""
        n = max(1, int(math.hypot(x1 - x0, y1 - y0) * self.T))
        for i in range(n + 1):
            u = i / n
            self.r(x0 + (x1 - x0) * u - w / 2, y0 + (y1 - y0) * u - w / 2, w, w, c)

    def disc(self, cx, cy, rad, c):
        T = self.T
        r = rad * T
        y0, y1 = int(math.floor(self.oy + cy * T - r)), int(math.ceil(self.oy + cy * T + r))
        pcx, pcy = self.ox + cx * T, self.oy + cy * T
        for py in range(y0, y1 + 1):
            dy = py + 0.5 - pcy
            if abs(dy) > r:
                continue
            w = math.sqrt(r * r - dy * dy)
            a, b = int(math.floor(pcx - w + 0.5)), int(math.floor(pcx + w + 0.5))
            if b <= a:
                b = a + 1
            self.cv.rect(a, py, b - a, 1, c)


def layout(cols, rows, hud):
    top = 1 if hud else 0
    bot = 1 if hud else 0
    aw, ah = cols, (rows - top - bot) * 2
    T = max(1, min(aw // SW, ah // SH))
    ox = (cols - SW * T) // 2
    oy = top * 2 + (ah - SH * T) // 2
    return T, ox, oy


_CACHE = {}


def paint_backdrop(cv, kind, T, ox, oy):
    W, H = cv.W, cv.H
    top, mid, bot = (6, 8, 26), (26, 20, 54), (64, 34, 58)
    for y in range(H):
        u = y / max(1, H - 1)
        c = mix(top, mid, u / 0.6) if u < 0.6 else mix(mid, bot, (u - 0.6) / 0.4)
        cv.px[y] = [c] * W
    for i in range(W * H // 50):
        x, y = hsh(i, 1, kind) % W, hsh(i, 2, kind) % max(1, H * 2 // 3)
        b = 70 + hsh(i, 3, kind) % 150
        cv.px[y][x] = mix(cv.px[y][x], (b, b, min(255, b + 30)), 0.8)
    # the moon
    mr = max(2, H // 16)
    mx, my = int(W * 0.9), int(H * 0.42)
    for yy in range(-mr - 3, mr + 4):
        for xx in range(-mr - 3, mr + 4):
            d = math.hypot(xx, yy)
            x, y = mx + xx, my + yy
            if 0 <= x < W and 0 <= y < H:
                if d <= mr:
                    cut = math.hypot(xx + mr * 0.45, yy - mr * 0.2) < mr * 0.8
                    cv.px[y][x] = (176, 170, 150) if not cut else mix((176, 170, 150), cv.px[y][x], 0.8)
                elif d <= mr + 3:
                    cv.px[y][x] = mix(cv.px[y][x], (120, 110, 130), 0.25 * (mr + 3 - d) / 3)
    windows = []
    # two rows of city blocks with lit windows
    for layer, (col, hmin, hmax, lit) in enumerate((((26, 22, 52), 0.3, 0.62, 7), ((15, 13, 32), 0.16, 0.42, 4))):
        x, i = -hsh(layer, 9, kind) % 6, 0
        while x < W:
            w = 4 + hsh(i, layer, kind + 5) % max(5, W // 9)
            h = int(H * (hmin + (hmax - hmin) * (hsh(i, layer + 7, kind) % 100) / 100))
            y0 = H - h
            cv.rect(x, y0, w, h, col)
            if hsh(i, 33, layer) % 3 == 0 and w > 3 and 0 <= x + w // 2 < W and y0 >= 3:   # antenna, red light
                cv.rect(x + w // 2, y0 - 3, 1, 3, col)
                windows.append((x + w // 2, y0 - 3, (230, 60, 50), True))
            warm = hsh(i, 11, layer) % 2
            for wy in range(y0 + 2, H - 1, 3):
                for wx in range(x + 1, x + w - 1, 2):
                    if 0 <= wx < W and hsh(wx, wy, kind + layer) % lit == 0:
                        c = (236, 196, 110) if warm else (130, 196, 230)
                        c = mix(col, c, 0.55 if layer == 0 else 0.85)
                        cv.px[wy][wx] = c
                        windows.append((wx, wy, c, False))
            x += w + (hsh(i, 21, layer) % 3)
            i += 1
    for y in range(max(0, H - 6), H):             # sodium glow from the street
        a = (y - (H - 6)) / 6 * 0.35
        cv.px[y] = [mix(c, (120, 70, 40), a) for c in cv.px[y]]
    return windows


def draw_girder(v, s):
    T, cv = v.T, v.cv
    th = max(1, int(0.6 * T + 0.5))
    x0, x1 = v.X(s.x0), v.X(s.x1)
    if s.kind == "goal":
        hi, body, lo = (255, 226, 120), (220, 170, 40), (90, 66, 20)
    elif s.kind == "robot":
        hi, body, lo = (200, 170, 140), (120, 92, 70), (60, 44, 34)
    else:
        hi, body, lo = STEEL_HI, STEEL, STEEL_LO
    for px in range(max(0, x0), min(cv.W, x1)):
        xs = (px - v.ox + 0.5) / T
        top = v.Y(s.y(xs))
        for k in range(th):
            py = top + k
            if not 0 <= py < cv.H:
                continue
            if k == 0:
                c = hi
            elif k == th - 1 and th > 1:
                c = lo
            else:
                c = body
                if th == 3 and (px - x0) % 3 == 1:
                    c = STEEL_HOLE if s.kind not in ("goal", "robot") else shade(body, 0.7)
                elif th >= 4:
                    m = (px - x0) % (th - 1)
                    if m == k - 1 or (th - 1 - m) == k - 1:
                        c = STEEL_HOLE if s.kind not in ("goal", "robot") else shade(body, 0.7)
            if s.kind == "goal" and k > 0 and k < th - 1 and ((px - x0) // max(1, T // 2)) % 2:
                c = (40, 34, 30)
            cv.px[py][px] = c
    if th >= 3:   # rivets at the ends
        for xx in (s.x0 + 0.25, s.x1 - 0.3):
            v.p(xx, s.y(xx) + 0.25, (210, 225, 240))


def draw_ladder(v, L):
    T, cv = v.T, v.cv
    x0, x1 = v.X(L.x - 0.45), v.X(L.x + 0.45)
    if x1 - x0 < 2:
        x1 = x0 + 2
    gap = max(2, T // 2)

    def part(ya, yb):
        y0, y1 = v.Y(ya), v.Y(yb)
        for py in range(max(0, y0), min(cv.H, y1)):
            rung = (py - v.oy) % gap == 0
            if x1 - x0 <= 2:
                c = LADDER if rung else LADDER_DARK
                cv.rect(x0, py, x1 - x0, 1, c)
            else:
                cv.set(x0, py, LADDER_DARK)
                cv.set(x1 - 1, py, LADDER_DARK)
                if rung:
                    cv.rect(x0 + 1, py, x1 - x0 - 2, 1, LADDER)
    if L.broken:
        part(L.ytop, L.ytop + 0.45)
        part(L.ybreak, L.ybot)
    else:
        part(L.ytop, L.ybot)


def static_layer(st, cols, rows, hud):
    key = (st.kind, cols, rows, hud)
    c = _CACHE.get(key)
    if c:
        return c
    if len(_CACHE) > 24:
        _CACHE.clear()
    T, ox, oy = layout(cols, rows, hud)
    cv = Canvas(cols, rows)
    windows = paint_backdrop(cv, st.kind, T, ox, oy)
    v = View(cv, T, ox, oy)
    # the tower's own frame behind everything: columns and braces
    col, brace = (30, 36, 62), (26, 30, 54)
    cw = max(1, T // 3)
    xs = [0.3, 7.2, 14.0, 20.8, 27.7]
    for x in xs:
        cv.rect(v.X(x), v.Y(0), cw, SH * T, col)
    for i in range(len(xs) - 1):
        for y in range(0, SH, 4):
            a, b = (xs[i], y), (xs[i + 1], y + 4)
            if (i + y // 4) % 2:
                a, b = (xs[i], y + 4), (xs[i + 1], y)
            v.line(a[0], a[1], b[0], b[1], brace)
    k = st.kind
    if k == 3:     # the crane: a tower at the right and a jib along the top
        for y in range(0, SH * T, max(2, T)):
            cv.rect(v.X(26.6), v.Y(0) + y, max(2, T), 1, (60, 56, 40))
        cv.rect(v.X(26.4), v.Y(0), 1, SH * T, (80, 74, 50))
        cv.rect(v.X(27.6), v.Y(0), 1, SH * T, (80, 74, 50))
        v.r(0, 0.1, SW, 0.4, (120, 104, 50))
        for x in range(0, SW, 2):
            v.line(x, 0.1, x + 1, 0.5, (70, 62, 34))
    if k == 2:     # lift shafts: guide rails and pulley housings
        for pl in st.plats:
            for x in (pl.x0 - 0.12, pl.x1 + 0.02):
                v.r(x, pl.ytop - 0.2, 0.1, SH - pl.ytop + 0.2, (70, 76, 100))
            v.r(pl.x0 - 0.3, pl.ytop - 1.0, pl.x1 - pl.x0 + 0.6, 0.8, (64, 64, 80))
            v.r(pl.x0 - 0.3, pl.ytop - 1.0, pl.x1 - pl.x0 + 0.6, 0.15, (120, 120, 140))
            v.disc((pl.x0 + pl.x1) / 2, pl.ytop - 0.6, 0.3, (150, 150, 170))
        v.r(0, 4.6, 6.2, 0.25, (64, 64, 80))
        zx0, zx1, zy = st.chute_zone
        for i, x in enumerate(range(int(zx0 * T), int(zx1 * T))):
            cv.set(ox + x, v.Y(zy) + max(1, T // 2), (240, 200, 60) if (i // max(1, T // 2)) % 2 else (40, 34, 30))
    if k == 1:     # the smelter pit
        x0, x1, y = st.smelter
        v.r(x0, y + 0.1, x1 - x0, SH - y, (40, 24, 26))
        v.r(x0 - 0.2, y, 0.2, SH - y, (90, 70, 66))
        v.r(x1, y, 0.2, SH - y, (90, 70, 66))
        for x in st.chutes:
            v.r(x - 0.5, 4.0, 1.0, 0.25, (60, 50, 50))
    if st.furnace:   # a brick furnace that eats the drums
        fx, fy = st.furnace
        v.r(fx - 1.0, fy - 2.0, 2.1, 2.0, (110, 50, 40))
        for yy in range(int(2.0 * T)):
            for xx in range(int(2.1 * T)):
                bx = xx + (T // 2 if (yy // max(2, T // 2)) % 2 else 0)
                if yy % max(2, T // 2) == 0 or bx % max(3, T) == 0:
                    cv.set(v.X(fx - 1.0) + xx, v.Y(fy - 2.0) + yy, (70, 34, 30))
        v.r(fx - 0.2, fy - 2.9, 0.6, 1.0, (80, 44, 36))
    for s in st.segs:
        if s.kind not in ("belt", "rail") and s.idx not in st.robot_segs:
            draw_girder(v, s)
        elif s.kind == "rail":
            draw_girder(v, s)
    for L in st.ladders:
        draw_ladder(v, L)
    c = ([row[:] for row in cv.px], windows, T, ox, oy)
    _CACHE[key] = c
    return c


def draw_belt(v, s, pos, t):
    T = v.T
    th = max(2, int(0.6 * T + 0.5))
    y0 = v.Y(s.ya)
    x0, x1 = v.X(s.x0), v.X(s.x1)
    cv = v.cv
    period = max(3, T)
    shift = int(math.floor(pos * T))
    cleat = max(1, period // 3)
    for px in range(max(0, x0), min(cv.W, x1)):
        m = (px - shift) % period
        for k in range(th):
            py = y0 + k
            if 0 <= py < cv.H:
                if k == 0:
                    c = (206, 206, 214) if m < cleat else (104, 104, 118)
                elif k == th - 1:
                    c = (30, 30, 38) if m >= cleat else (70, 70, 84)
                else:
                    c = (62, 62, 74)
                cv.px[py][px] = c
    sp = s.speed(t)
    warn = s.flip_warn(t) and int(t * 6) % 2
    lamp = (250, 170, 40) if warn else (90, 230, 120)
    for x in (s.x0, s.x1 - 0.35):
        v.r(x, s.ya, 0.35, 0.6, (226, 186, 60))
        v.p(x + 0.1, s.ya + 0.25, (120, 96, 30))
    ax = s.x1 - 0.7 if sp > 0 else s.x0 + 0.4
    d = 1 if sp > 0 else -1
    if T >= 3:       # a little arrow lamp shows which way it runs
        v.r(ax, s.ya - 0.35, 0.3, 0.2, lamp)
        v.p(ax + (0.3 if d > 0 else -0.1), s.ya - 0.3, lamp)
    else:
        v.p(ax, s.ya - 0.5, lamp)


def draw_rail(v, s, t):
    live, warn = s.live(t), s.rail_warn(t)
    T = v.T
    y = s.ya
    c = (120, 220, 255) if live else (200, 120, 60) if warn and int(t * 10) % 2 else (150, 90, 50)
    v.r(s.x0, y - 0.02, s.x1 - s.x0, max(1.0 / T, 0.14), c)
    if live:
        rng = random.Random(int(t * 20) + s.idx * 99)
        for i in range(int((s.x1 - s.x0) * 1.2)):
            x = rng.uniform(s.x0, s.x1)
            h = rng.uniform(0.2, 0.9)
            v.line(x, y, x + rng.uniform(-0.3, 0.3), y - h, (200, 245, 255) if rng.random() < 0.5 else (110, 200, 255))


def drum_cols(hot, t, x):
    if hot:
        f = 0.5 + 0.5 * math.sin(t * 20 + x)
        return mix((230, 90, 30), (255, 160, 60), f), (255, 236, 140), (130, 40, 20)
    return (46, 132, 150), (170, 226, 230), (20, 60, 76)


def draw_drum(v, x, y, spin, hot, t):
    T = v.T
    body, band, rim = drum_cols(hot, t, x)
    if T <= 2:
        v.r(x - 0.5, y - 1.0, 1.0, 1.0, body)
        v.p(x - 0.5 + (0.5 if math.sin(spin) > 0 else 0), y - 1.0, band)
        return
    cy = y - 0.44
    v.disc(x, cy, 0.46, rim)
    v.disc(x, cy, 0.36, body)
    if T >= 5:
        v.disc(x, cy, 0.2, shade(body, 0.8))
    v.p(x + math.cos(spin) * 0.24, cy + math.sin(spin) * 0.24, band)
    v.p(x - math.cos(spin) * 0.24, cy - math.sin(spin) * 0.24, shade(band, 0.75))


def draw_drum_upright(v, x, y, hot, t):
    body, band, rim = drum_cols(hot, t, x)
    v.r(x - 0.4, y - 0.9, 0.8, 0.9, rim)
    v.r(x - 0.32, y - 0.9, 0.64, 0.9, body)
    v.r(x - 0.4, y - 0.66, 0.8, 0.1, band)
    v.r(x - 0.4, y - 0.3, 0.8, 0.1, band)
    v.r(x - 0.32, y - 0.9, 0.64, 0.08, shade(body, 1.3))


def draw_gear(v, x, y, spin, t):
    cy = y - 0.48
    T = v.T
    metal = (170, 172, 184)
    if T <= 2:
        v.r(x - 0.5, y - 1.0, 1.0, 1.0, metal)
        v.p(x, cy, (60, 60, 70))
        return
    v.disc(x, cy, 0.36, metal)
    for i in range(8):
        a = spin + i * math.pi / 4
        v.r(x + math.cos(a) * 0.42 - 0.08, cy + math.sin(a) * 0.42 - 0.08, 0.16, 0.16, metal)
    v.disc(x, cy, 0.14, (54, 56, 66))
    v.p(x - 0.2, cy - 0.2, (240, 240, 250))


def draw_spark(v, x, y, t, seed):
    T = v.T
    cy = y - 0.38
    fl = hsh(int(t * 30), seed) % 4
    if T <= 2:
        v.r(x - 0.5, y - 1.0, 1.0, 1.0, (120, 200, 255) if fl else (230, 250, 255))
        return
    v.disc(x, cy, 0.38 + 0.04 * fl, (60, 120, 230))
    v.disc(x, cy, 0.26, (150, 220, 255))
    v.disc(x, cy, 0.12, (250, 255, 255))
    rng = random.Random(int(t * 24) + seed)
    for _ in range(3):
        a = rng.uniform(0, math.tau)
        v.line(x + math.cos(a) * 0.3, cy + math.sin(a) * 0.3, x + math.cos(a) * 0.62, cy + math.sin(a) * 0.62,
               (200, 240, 255))
    if T >= 4:
        v.p(x - 0.14, cy - 0.06, (20, 30, 70))
        v.p(x + 0.1, cy - 0.06, (20, 30, 70))


def draw_crate(v, x, y):
    v.r(x - 0.44, y - 0.86, 0.88, 0.86, (110, 74, 40))
    v.r(x - 0.36, y - 0.78, 0.72, 0.7, (168, 118, 62))
    if v.T >= 4:
        v.line(x - 0.36, y - 0.78, x + 0.34, y - 0.1, (110, 74, 40))
        v.line(x + 0.34, y - 0.78, x - 0.36, y - 0.1, (110, 74, 40))


def draw_rivet(v, x, y, t):
    f = 0.5 + 0.5 * math.sin(t * 18 + x * 3)
    v.r(x - 0.3, y - 0.36, 0.6, 0.36, mix((220, 60, 30), (255, 140, 50), f))
    v.r(x - 0.12, y - 0.44, 0.24, 0.12, (255, 220, 120))


def draw_weight(v, x, y, floor):
    T = v.T
    if floor is not None and floor - y > 0.3:        # its shadow tells where it lands
        w = clamp(1.1 - (floor - y) * 0.2, 0.3, 1.0)
        v.r(x - w / 2, floor - 0.08, w, 0.1, (20, 16, 26))
    v.r(x - 0.46, y - 0.62, 0.92, 0.62, (58, 58, 70))
    v.r(x - 0.46, y - 0.4, 0.92, 0.14, (230, 190, 50))
    v.r(x - 0.2, y - 0.82, 0.4, 0.2, (90, 90, 104))
    if T >= 4:
        v.p(x - 0.36, y - 0.58, (120, 120, 140))


def draw_item(v, it, t):
    x, y, k = it["x"], it["y"], it["kind"]
    bob = 0.06 * math.sin(t * 3 + x)
    y += bob
    if k == "toolbox":
        v.r(x - 0.4, y - 0.5, 0.8, 0.5, (210, 50, 50))
        v.r(x - 0.4, y - 0.5, 0.8, 0.12, (255, 110, 100))
        v.r(x - 0.16, y - 0.68, 0.32, 0.14, (170, 170, 180))
    elif k == "hat":
        v.r(x - 0.42, y - 0.16, 0.84, 0.16, (230, 232, 240))
        v.r(x - 0.3, y - 0.5, 0.6, 0.36, (245, 246, 250))
        v.r(x - 0.06, y - 0.56, 0.12, 0.1, (200, 200, 210))
    else:
        v.r(x - 0.4, y - 0.52, 0.8, 0.52, (60, 120, 210))
        v.r(x - 0.4, y - 0.3, 0.8, 0.06, (40, 80, 160))
        v.r(x - 0.14, y - 0.66, 0.28, 0.14, (200, 200, 210))
    if int(t * 3 + x) % 5 == 0:
        v.p(x + 0.25, y - 0.45, (255, 255, 255))


def draw_wrench_icon(v, x, y, a, c=(214, 220, 232)):
    """A big wrench, centred at (x, y), turned by angle a."""
    ca, sa = math.cos(a), math.sin(a)
    v.thick(x - ca * 0.45, y - sa * 0.45, x + ca * 0.35, y + sa * 0.35, max(0.16, 1.0 / v.T), c)
    hx, hy = x + ca * 0.45, y + sa * 0.45
    v.r(hx - 0.17, hy - 0.17, 0.34, 0.34, c)
    v.p(hx + ca * 0.05, hy + sa * 0.05, (60, 64, 80))


def draw_switch(v, x, y, t, done=False):
    v.r(x - 0.08, y - 1.0, 0.16, 1.0, (120, 120, 130))
    v.r(x - 0.4, y - 1.5, 0.8, 0.6, (230, 190, 50))
    v.r(x - 0.4, y - 1.5, 0.8, 0.12, (255, 230, 120))
    on = int(t * 4) % 2
    v.r(x - 0.2, y - 1.8, 0.4, 0.3, (240, 60, 50) if not done else (90, 220, 120))
    if on and not done:
        v.p(x, y - 2.1, (255, 120, 100))
        v.p(x, y - 2.2, (255, 200, 180))


def draw_breaker(v, b, t):
    x, y = b["x"], b["y"]
    v.r(x - 0.4, y - 1.9, 0.8, 1.0, (90, 96, 110))
    v.r(x - 0.4, y - 1.9, 0.8, 0.12, (150, 156, 170))
    if b["pulled"]:
        v.r(x + 0.05, y - 1.25, 0.12, 0.42, (230, 230, 240))
        v.p(x - 0.22, y - 1.7, (90, 230, 120))
    else:
        v.r(x + 0.05, y - 2.15, 0.12, 0.42, (230, 230, 240))
        v.p(x - 0.22, y - 1.7, (255, 70, 60) if int(t * 3) % 2 else (150, 40, 40))
    # its cable runs up the wall
    c = (60, 70, 90) if b["pulled"] else (90, 200, 255) if int(t * 8 + x) % 4 else (180, 240, 255)
    v.r(x - 0.03, 0.0, 0.06, y - 1.9, c)


def draw_player(v, p, g, t):
    x, y, f = p.x, p.y, p.face
    T = v.T
    dead = g.state == "dying"
    wr = g.wrench_t > 0
    if wr and g.wrench_t < 2.0 and int(t * 10) % 2:
        wr_col = (255, 120, 80)
    else:
        wr_col = (214, 220, 232)
    hat, vest, legs, skin, boot = (250, 206, 40), (250, 128, 30), (48, 66, 128), (232, 182, 140), (70, 48, 34)
    if dead:
        k = g.st_t
        if k < 0.9:
            f = 1 if int(k * 12) % 2 else -1
        else:      # flat on the girder, hat rolled off
            v.r(x - 0.7, y - 0.3, 0.45, 0.3, legs)
            v.r(x - 0.25, y - 0.34, 0.55, 0.34, vest)
            v.r(x + 0.3, y - 0.28, 0.26, 0.26, skin)
            v.r(x + 0.85, y - 0.24, 0.42, 0.24, hat)
            if int(k * 4) % 2:
                v.p(x + 0.4, y - 0.7, (255, 255, 160))
                v.p(x + 0.1, y - 0.9, (255, 255, 160))
            return
    if T <= 2:
        v.r(x - 0.5, y - 1.5, 1.0, 0.5, hat)
        v.r(x - 0.5, y - 1.0, 1.0, 0.5, vest)
        v.r(x - 0.5, y - 0.5, 1.0, 0.5, legs)
        if wr:
            v.p(x + f * 0.9, y - (2.0 if int(t * 7) % 2 else 1.0), wr_col)
        return
    if p.mode == "climb":
        k = int(p.anim * 8) % 2
        v.r(x - 0.3, y - 0.6, 0.22, 0.42 + 0.1 * k, legs)
        v.r(x + 0.08, y - 0.6, 0.22, 0.52 - 0.1 * k, legs)
        v.r(x - 0.34, y - 1.12, 0.68, 0.54, vest)
        if T >= 5:
            v.line(x - 0.3, y - 1.1, x + 0.28, y - 0.62, (220, 230, 240))
            v.line(x + 0.28, y - 1.1, x - 0.3, y - 0.62, (220, 230, 240))
        v.r(x - 0.46, y - 1.5 + 0.12 * k, 0.14, 0.5, vest)
        v.r(x + 0.32, y - 1.38 - 0.12 * k, 0.14, 0.5, vest)
        v.r(x - 0.22, y - 1.36, 0.44, 0.26, (120, 80, 60))
        v.r(x - 0.3, y - 1.52, 0.6, 0.2, hat)
        return
    air = p.mode == "air"
    step = int(p.anim * 9) % 4 if not air else 0
    la = [0.0, 0.1, 0.0, -0.1][step]
    if air:
        v.r(x - 0.32, y - 0.75, 0.26, 0.36, legs)
        v.r(x + 0.06, y - 0.62, 0.26, 0.3, legs)
        v.r(x - 0.34, y - 0.45, 0.28, 0.14, boot)
        v.r(x + 0.08, y - 0.36, 0.28, 0.14, boot)
    else:
        v.r(x - 0.3 + la, y - 0.62, 0.24, 0.46, legs)
        v.r(x + 0.06 - la, y - 0.62, 0.24, 0.46, legs)
        v.r(x - 0.34 + la, y - 0.18, 0.3, 0.18, boot)
        v.r(x + 0.04 - la, y - 0.18, 0.3, 0.18, boot)
    v.r(x - 0.34, y - 1.12, 0.68, 0.52, vest)
    if T >= 5:
        v.r(x - 0.34, y - 0.88, 0.68, 0.07, (230, 236, 244))
    v.r(x - 0.22, y - 1.36, 0.44, 0.26, skin)
    if T >= 4:
        v.p(x + f * 0.1, y - 1.25, (40, 30, 30))
    v.r(x - 0.3, y - 1.54, 0.6, 0.2, hat)
    v.r(x + (0.1 if f > 0 else -0.4), y - 1.38, 0.3, 0.06, hat)
    v.p(x + f * 0.24, y - 1.48, (255, 255, 230))
    if wr:
        up = int(t * 7) % 2 == 0
        if up:
            v.r(x + f * 0.2 - 0.07, y - 1.6, 0.14, 0.5, skin)
            draw_wrench_icon(v, x + f * 0.32, y - 2.0, -math.pi / 2 + f * 0.4, wr_col)
        else:
            v.r(x + f * 0.2 - 0.07, y - 1.05, 0.14, 0.4, skin)
            draw_wrench_icon(v, x + f * 0.85, y - 0.85, 0.0 if f > 0 else math.pi, wr_col)
    else:
        swing = [0.0, 0.08, 0.0, -0.08][step]
        v.r(x + f * 0.28 - 0.07 + swing * f, y - 1.08, 0.14, 0.42, vest if T < 4 else (230, 110, 26))
        v.r(x + f * 0.28 - 0.07 + swing * f, y - 0.7, 0.14, 0.12, skin)
        # headlamp: a faint cone ahead
        if T >= 3 and not air:
            for i in range(1, 4):
                v.p(x + f * (0.35 + i * 0.3), y - 1.46 + i * 0.08, mix(v.cv.px[0][0], (255, 250, 200), 0.18))


def draw_robot(v, r, g, t):
    T = v.T
    x, y, f = r.x, r.y + r.dy, r.face
    st = r.state
    body, dark, stripe = (214, 160, 40), (120, 86, 24), (30, 26, 24)
    if st == "off" or st == "fall" or st == "crashed":
        body, dark = (150, 112, 40), (90, 66, 24)
    tilt = r.tilt
    # legs and feet (one lifts during a stomp)
    lift_l = lift_r = 0.0
    if st == "stomp":
        k = r.st_t
        lift_l = 0.6 * max(0.0, math.sin(min(1.0, k / 0.22) * math.pi)) if k < 0.22 else 0.0
        lift_r = 0.6 * max(0.0, math.sin(min(1.0, (k - 0.3) / 0.3) * math.pi)) if 0.3 < k < 0.6 else 0.0
    sh = int(math.sin(t * 7) * 1.5) / T if st == "angry" else 0.0
    x += sh + tilt * 1.2
    y += tilt * 0.6
    for lx, lift in ((-1.1, lift_l), (1.1, lift_r)):
        v.r(x + lx - 0.3, y - 1.1 - lift, 0.6, 0.9, (90, 90, 100))
        v.r(x + lx - 0.55, y - 0.35 - lift, 1.1, 0.35, (60, 60, 70))
        v.r(x + lx - 0.55, y - 0.35 - lift, 1.1, 0.1, (130, 130, 140))
    # body
    v.r(x - 2.0, y - 3.0, 4.0, 2.0, dark)
    v.r(x - 1.9, y - 2.95, 3.8, 1.85, body)
    for i in range(8):         # hazard stripes along the skirt
        sx = x - 1.9 + i * 0.475
        v.r(sx, y - 1.4, 0.24, 0.3, stripe)
    if T >= 4:
        v.r(x - 1.9, y - 2.95, 3.8, 0.1, (250, 210, 100))
        for sx in (-1.6, 1.4):
            v.p(x + sx, y - 2.7, (90, 64, 20))
    # dome, antenna
    v.r(x - 1.2, y - 3.55, 2.4, 0.6, (80, 80, 92))
    v.r(x - 1.2, y - 3.55, 2.4, 0.1, (140, 140, 156))
    v.r(x + 0.7, y - 4.2, 0.08 if T >= 4 else 0.3, 0.65, (110, 110, 120))
    blink = int(t * 3) % 2 and st not in ("off", "fall", "crashed")
    v.p(x + 0.72, y - 4.25, (255, 70, 60) if blink else (110, 30, 30))
    # the eye: amber, red when something nasty comes, it follows the rigger
    if st in ("off", "fall", "crashed"):
        eye = (60, 20, 20) if int(t * 9) % 3 or st != "off" else (200, 60, 40)
    elif r.item in ("gear", "sball") and st in ("hold", "grab"):
        eye = (255, 50, 40) if int(t * 12) % 2 else (255, 160, 60)
    elif st == "angry":
        eye = (255, 40, 30)
    else:
        eye = (255, 176, 40)
    v.disc(x, y - 2.3, 0.62, (24, 22, 28))
    v.disc(x + r.eye * 0.2, y - 2.3, 0.34, eye)
    if T >= 4:
        v.disc(x + r.eye * 0.28, y - 2.32, 0.12, (255, 240, 200))
    # arms
    sx_l, sx_r, sy = x - 2.0, x + 2.0, y - 2.6
    k = min(1.0, r.st_t / 0.25)
    if st == "grab":
        back = -f
        hands = {back: (x + back * 2.9, y - 0.9), -back: (x - back * 2.4, y - 1.5)}
    elif st == "hold":         # wound up: the load raised high beside it - the throw comes next
        wob = 0.08 * math.sin(t * 30)
        hands = {f: (x + f * 2.7, y - 3.4 + wob), -f: (x - f * 2.6, y - 2.0)}
    elif st == "throw":
        hands = {f: (x + f * (2.7 + 0.6 * k), y - 3.4 + 2.0 * k), -f: (x - f * 2.3, y - 1.6)}
    elif st in ("angry", "leave"):
        a = math.sin(t * 14)
        hands = {-1: (x - 2.4, y - 4.0 + a * 0.4), 1: (x + 2.4, y - 4.0 - a * 0.4)}
    elif st in ("fall", "crashed", "off"):
        hands = {-1: (x - 2.7, y - 1.0 + tilt), 1: (x + 2.6, y - 0.8 - tilt)}
    else:
        sway = math.sin(r.anim * 2.4) * 0.12
        hands = {-1: (x - 2.8, y - 1.3 + sway), 1: (x + 2.8, y - 1.3 - sway)}
    aw = max(0.34, 1.0 / T)
    for side, sxx in ((-1, sx_l), (1, sx_r)):
        hx, hy = hands[side]
        v.thick(sxx, sy, hx, hy, aw, (150, 152, 166))
        v.r(hx - 0.3, hy - 0.22, 0.6, 0.45, (84, 84, 96))
        v.r(hx - 0.3, hy - 0.22, 0.6, 0.12, (190, 190, 204))
        v.r(hx - 0.3, hy + 0.15, 0.18, 0.2, (84, 84, 96))
        v.r(hx + 0.12, hy + 0.15, 0.18, 0.2, (84, 84, 96))
    v.r(sx_l - 0.25, sy - 0.25, 0.5, 0.5, (150, 120, 40))
    v.r(sx_r - 0.25, sy - 0.25, 0.5, 0.5, (150, 120, 40))
    # what it holds
    if st in ("hold",) or (st == "grab" and r.st_t > 0.2):
        hx, hy = (hands[f][0] + f * 0.2, hands[f][1] - 0.35) if st == "hold" else hands[-f]
        it = r.item
        if it in ("drum", "hot"):
            draw_drum_upright(v, hx, hy + 0.5, it == "hot", t)
        elif it == "gear":
            draw_gear(v, hx, hy + 0.5, t * 4, t)
        elif it == "sball":
            draw_spark(v, hx, hy + 0.4, t, 7)
        elif it == "crate":
            draw_crate(v, hx, hy + 0.5)
        elif it == "rivet":
            draw_rivet(v, hx, hy + 0.3, t)
        elif it == "weight":
            draw_weight(v, hx, hy + 0.5, None)
    # exhaust puffs from its back pipe
    if st not in ("fall", "crashed") and T >= 3:
        px_ = x - f * 1.7
        v.r(px_ - 0.12, y - 3.6, 0.24, 0.6, (70, 70, 80))
        ph = (t * 1.3) % 1.0
        v.disc(px_ - f * 0.2 * ph, y - 3.8 - ph * 1.2, 0.15 + 0.2 * ph, mix((150, 150, 160), v.cv.px[0][0], ph * 0.8))


def draw_stockpile(v, st, t):
    k = st.kind
    rx, ry, f = st.robot
    bx = rx - f * 3.3
    if k in (0, 3):
        for dx, dy in ((-0.45, 0), (0.45, 0), (0.0, -0.9)):
            draw_drum_upright(v, bx + dx, ry + dy, False, t)
    elif k == 1:
        for dx in (-2.8, 2.8):
            draw_crate(v, rx + dx, ry)
    elif k == 2:
        draw_weight(v, rx + 2.3, ry, None)
    elif k == 4:
        for dx in (-3.0, 3.0):
            draw_gear(v, rx + dx, ry, t * 0.5, t)


def render(g, cols, rows, hud=True):
    st = g.st
    px_rows, windows, T, ox, oy = static_layer(st, cols, rows, hud)
    cv = Canvas(cols, rows)
    sh = 0
    if g.shake > 0:
        sh = (1 if int(g.clock * 40) % 2 else -1) * max(1, T // 3)
    if sh:
        H = len(px_rows)
        cv.px = [px_rows[clamp(y - sh, 0, H - 1)][:] for y in range(H)]
    else:
        cv.px = [r[:] for r in px_rows]
    v = View(cv, T, ox, oy + sh)
    t = g.t
    clock = g.clock
    # windows switch on and off now and then; the warning lights blink
    tick = int(clock * 0.7)
    for i, (wx, wy, c, red) in enumerate(windows):
        if red:
            if int(clock * 1.5 + i) % 3 == 0:
                cv.px[wy][wx] = (255, 90, 70)
        elif hsh(i, tick) % 41 == 0 and 0 <= wy < cv.H:
            cv.px[wy][wx] = mix(c, (10, 10, 20), 0.75)
    k = st.kind
    # moving and living parts of the structure
    for s in st.segs:
        if s.kind == "belt":
            draw_belt(v, s, g.belt_pos[s.idx], t)
        elif s.kind == "rail":
            draw_rail(v, s, t)
        elif s.idx in st.robot_segs:
            dy = g.robot.dy if g.state == "ending" and g.robot.state in ("fall", "crashed") else 0.0
            ss = Seg(s.x0, s.ya + dy, s.x1, s.yb + dy + g.robot.tilt * 1.5, kind="robot")
            draw_girder(v, ss)
    for pi, pl in enumerate(st.plats):
        for ci, x0, x1, cy, vx, vy in pl.cars(t):
            if isinstance(pl, Lift):
                if cy < pl.ytop - 0.1 or cy > SH:
                    continue
                v.line(x0 + 0.2, pl.ytop - 0.3, x0 + 0.2, cy, (120, 124, 140))
                v.line(x1 - 0.2, pl.ytop - 0.3, x1 - 0.2, cy, (120, 124, 140))
                v.r(x0, cy, x1 - x0, 0.35, (230, 130, 40))
                v.r(x0, cy, x1 - x0, 0.1, (255, 190, 100))
                arrow = (120, 255, 140) if pl.speed < 0 else (255, 120, 100)
                v.p((x0 + x1) / 2, cy + 0.18, arrow)
            else:
                cx = (x0 + x1) / 2
                top = max((sg.y(cx) + 0.6 for sg in st.segs if sg.x0 <= cx <= sg.x1 and sg.y(cx) < cy - 1), default=0.5)
                v.r(cx - 0.4, top - 0.3, 0.8, 0.3, (100, 92, 64))
                v.line(cx - 0.2, top, x0 + 0.3, cy, (96, 98, 116))
                v.line(cx + 0.2, top, x1 - 0.3, cy, (96, 98, 116))
                bs = Seg(x0, cy, x1, cy)
                draw_girder(v, bs)
                v.r(x0, cy, 0.12, 0.5, (240, 200, 60))
                v.r(x1 - 0.12, cy, 0.12, 0.5, (240, 200, 60))
    if st.smelter:      # molten metal bubbling in the pit
        x0, x1, y = st.smelter
        for i in range(int((x1 - x0) * T)):
            u = i / T
            h = 0.25 + 0.15 * math.sin(clock * 4 + u * 3)
            c = mix((255, 110, 30), (255, 220, 120), 0.5 + 0.5 * math.sin(clock * 7 + u * 5))
            cv.rect(v.X(x0) + i, v.Y(SH - h), 1, max(1, v.Y(SH) - v.Y(SH - h)), c)
        cv.rect(v.X(x0), v.Y(y + 0.2), max(1, v.X(x1) - v.X(x0)), 1, mix((60, 30, 26), (255, 120, 40), 0.3))
    if st.furnace:
        fx, fy = st.furnace
        fl = 0.5 + 0.5 * math.sin(clock * 13)
        v.r(fx + 0.15, fy - 1.2, 0.8, 1.0, mix((255, 120, 30), (255, 220, 100), fl))
        v.r(fx + 0.3, fy - 0.8, 0.5, 0.5, (255, 250, 200))
        for i in range(3):
            ph = (clock * 1.8 + i / 3) % 1.0
            v.p(fx + 0.1 + math.sin(clock * 3 + i * 2) * 0.3, fy - 2.9 - ph * 2.2, mix((255, 200, 80), (60, 40, 50), ph))
    if st.chute_zone:
        zx0, zx1, zy = st.chute_zone
        danger = any(h.kind == "weight" and (h.mode == "drop" or h.x < st.T.x0 + 3) for h in g.hz)
        c = (255, 60, 50) if danger and int(clock * 8) % 2 else (90, 30, 30)
        v.r((zx0 + zx1) / 2 - 0.15, zy - 2.3, 0.3, 0.3, c)
    for it in st.items:
        if not it["taken"]:
            draw_item(v, it, clock)
    for w in st.wrenches:
        if not w["taken"]:
            draw_wrench_icon(v, w["x"], w["y"] - 0.4, -0.8 + 0.25 * math.sin(clock * 2.5))
            if int(clock * 4 + w["x"]) % 6 == 0:
                v.p(w["x"] + 0.3, w["y"] - 0.75, (255, 255, 255))
    if st.switch_x is not None:
        draw_switch(v, st.switch_x, st.goal[2], clock, g.state == "clear")
    for b in st.breakers:
        draw_breaker(v, b, clock)
    for hk in st.hooks:
        bx, by = hk.bob(t)
        v.r(hk.px - 0.4, hk.py - 0.3, 0.8, 0.3, (90, 84, 60))
        v.line(hk.px, hk.py, bx, by - 0.4, (150, 150, 164))
        v.disc(bx, by, 0.55, (50, 46, 40))
        v.disc(bx, by, 0.46, (236, 192, 48))
        v.r(bx - 0.46, by - 0.08, 0.92, 0.16, (40, 34, 30))
        v.r(bx - 0.12, by + 0.3, 0.24, 0.3, (120, 120, 130))
    if st.robot is not None and not (g.state == "clear" and g.robot.dy < -8):
        if g.state not in ("ending",):
            draw_stockpile(v, st, clock)
        draw_robot(v, g.robot, g, clock)
    # hazards
    for i, h in enumerate(g.hz):
        k_ = h.kind
        if k_ in ("drum", "hot"):
            draw_drum(v, h.x, h.y, h.spin, k_ == "hot", clock)
        elif k_ == "gear":
            draw_gear(v, h.x, h.y, h.spin, clock)
        elif k_ == "spark":
            draw_spark(v, h.x, h.y, clock, i * 13 + 1)
        elif k_ == "crate":
            draw_crate(v, h.x, h.y)
        elif k_ == "rivet":
            draw_rivet(v, h.x, h.y, clock)
        elif k_ == "weight":
            floor = None
            if h.mode == "hop":
                floor = st.robot[1]
            draw_weight(v, h.x, h.y, floor)
    p = g.player
    draw_player(v, p, g, clock)
    # particles
    ps = max(1, T // 4)
    for f in g.fx:
        if len(f) > 7:      # wind streaks
            x0 = v.X(f[0])
            cv.rect(x0, v.Y(f[1]), max(2, T), 1, f[5])
        else:
            cv.rect(v.X(f[0]), v.Y(f[1]), ps, ps, f[5])
    # floating points
    for x, y, txt, until, col in g.pops:
        rise = (1.0 - (until - g.clock)) * 0.8
        c = v.X(x) - len(txt) // 2
        r = (v.Y(y - rise)) // 2
        if 0 <= r < rows:
            cv.put(clamp(c, 0, cols - len(txt)), r, txt, col)
    if hud:
        draw_hud(cv, g)
        footer(cv, "arrows walk / climb   Space jump   Esc pause   ? help")
    # banners
    if hud and g.state == "intro":
        lines = ["NIGHT %d  -  STAGE %d/5" % (g.night, g.stage_i % 5 + 1), "", st.name, "", st.hint]
        banner(cv, lines, (240, 200, 90))
    elif hud and g.state == "clear" and g.st_t > 0.3:
        banner(cv, ["STAGE CLEAR", "", "the Wrecker climbs higher..."], (140, 255, 160))
    elif hud and g.state == "ending" and g.st_t > 3.2:
        banner(cv, ["LIGHTS OUT, WRECKER!", "", "night %d survived" % g.night, "",
                    "...but it reboots. Night %d is coming." % (g.night + 1)], (255, 214, 110))
    elif hud and g.state == "dying" and g.st_t > 0.9:
        why = {"time": "the bonus ran out", "fall": "that was too far down", "crush": "the pulley got you",
               "zap": "the rail was live", "robot": "too close to the Wrecker", "burn": "the furnace is hot",
               "hit": "hit", "smelt": "into the smelter"}.get(g.cause, "")
        lives = g.lives - (0 if g.demo else 1)
        banner(cv, [why.upper(), "", ("%d rigger%s left" % (lives, "" if lives == 1 else "s")) if lives > 0 else "no riggers left"],
               (255, 120, 100))
    return cv


def banner(cv, lines, col):
    w = max(len(l) for l in lines) + 4
    x = max(0, (cv.cols - w) // 2)
    y = max(1, cv.rows // 2 - len(lines) // 2 - 1)
    cv.box(x, y, [l.center(w - 4) for l in lines], (240, 240, 246), (20, 18, 38))
    cv.put(x + 2 + (w - 4 - len(lines[0])) // 2, y + 1, lines[0], col, (20, 18, 38))


def draw_hud(cv, g):
    cols = cv.cols
    cv.put(0, 0, " " * cols, HUD_FG, HUD_BG)
    best = max(g.score, g.hi)
    st = g.st
    parts = [("SCORE ", HUD_DIM), ("%06d" % g.score, GOLD), ("  HI ", HUD_DIM), ("%06d" % best, HUD_FG),
             ("  L=", HUD_DIM), ("%d" % g.night, HUD_FG)]
    if cols >= 84:
        parts += [("  STAGE %d/5 " % (st.kind + 1), HUD_DIM), (st.name, HUD_FG)]
    elif cols >= 70:
        parts += [("  ST ", HUD_DIM), ("%d/5" % (st.kind + 1), HUD_FG)]
    x = 1
    for s, c in parts:
        cv.put(x, 0, s, c, HUD_BG)
        x += len(s)
    # right side: breakers, wrench, lives, bonus
    low = g.bonus <= 1000
    bon = " BONUS %4d " % g.bonus
    bc = (255, 255, 255) if not low or int(g.clock * 4) % 2 else (255, 120, 100)
    rx = cols - len(bon) - 1
    cv.put(rx, 0, bon, (16, 14, 20) if not low else bc, (240, 200, 90) if not low else (120, 30, 30))
    lives = max(0, g.lives - 1)       # the spare riggers, as little hard hats
    life = "\u25b2" * min(lives, 5) + ("+" if lives > 5 else "")
    rx -= len(life) + 1
    cv.put(rx, 0, life, (250, 206, 40), HUD_BG)
    if st.breakers:
        s = "BRK %d/%d " % (sum(b["pulled"] for b in st.breakers), len(st.breakers))
        rx -= len(s)
        if rx > x + 1:
            cv.put(rx, 0, s, (140, 220, 255), HUD_BG)
    if g.wrench_t > 0:
        s = "WRENCH %d " % math.ceil(g.wrench_t)
        rx -= len(s)
        if rx > x + 1:
            cv.put(rx, 0, s, (230, 235, 245) if g.wrench_t > 2 or int(g.clock * 8) % 2 else (255, 120, 80), HUD_BG)
    if st.wind and g.wind_state != "calm":
        s = ("<< WIND " if g.wind_dir < 0 else "WIND >> ")
        rx -= len(s)
        if rx > x + 1:
            cv.put(rx, 0, s, (170, 190, 240), HUD_BG)


def render_over(g, cv, record):
    lines = ["GAME OVER", "", "score  %d" % g.score, "night  %d   stage %d/5" % (g.night, g.stage_i % 5 + 1)]
    if record:
        lines += ["", "** NEW RECORD **"]
    lines += ["", "Enter: again   Esc / Q: menu"]
    w = max(len(l) for l in lines) + 4
    x, y = max(0, (cv.cols - w) // 2), max(0, cv.rows // 2 - len(lines) // 2 - 1)
    edge = GOLD if record else (200, 76, 86)
    cv.frame(x - 1, y * 2 - 1, w + 2, (len(lines) + 2) * 2 + 2, edge)
    cv.box(x, y, [l.center(w - 4) for l in lines], (240, 240, 246), (24, 22, 44))


# =============================================================================================
# Title demo, controls, menu, main loop
# =============================================================================================
class TitleDemo:
    """The autopilot climbing through the five stages behind the title screen (and in the launcher preview)."""

    def __init__(self, stage=0):
        self.k = stage
        self.new_run()

    def new_run(self):
        self.g = Game(self.k % 5, night=1, demo=True)
        self.bot = Bot(self.g)
        self.k += 1
        self.age = 0.0

    def scene(self, cols, rows, dt):
        g = self.g
        before = (g.stage_i, g.deaths)
        self.age += dt
        g.update(min(dt, 0.1), self.bot)
        if (g.stage_i, g.deaths) != before:
            self.bot.reset()
        if g.stage_i != self.k - 1 and g.state == "intro" or self.age > 75:
            self.new_run()
        return render(self.g, cols, rows, hud=False)


LEFT, RIGHT, UP, DOWN, JUMP = ("left", "a"), ("right", "d"), ("up", "w"), ("down", "s"), (" ", "z", "y")


class Controls:
    """Keys to (dx, dy, jump) via HeldKeys. Classic terminals: a direction counts as held while it repeats; the
    window that bridges the keyboard's initial repeat delay is learned from the first repeat."""

    def __init__(self, kitty):
        self.kitty = kitty
        self.held = HeldKeys(kitty, first=0.5, repeat=0.13)
        self.jedge = False
        self.last_jump = -9.0
        self.first = {}
        self.delay = 0.45

    def reset(self):
        self.held.clear()
        self.jedge = False
        self.first = {}

    def feed(self, name, kind, now):
        if name in JUMP:
            if kind == "press":
                if self.kitty or now - self.last_jump > 0.1:     # classic key repeat of a held jump key
                    self.jedge = True
                self.last_jump = now
            return
        if not self.kitty and kind == "press" and name in LEFT + RIGHT + UP + DOWN:
            held_now = self.held.until.get(name, 0) > now
            if held_now and name in self.first:
                gap = now - self.first.pop(name)
                if 0.12 < gap < 0.8:
                    self.delay = clamp(self.delay * 0.5 + gap * 0.5, 0.2, 0.6)
                    self.held.first = min(0.55, self.delay + 0.08)
            elif not held_now:
                self.first[name] = now
        self.held.feed(name, kind, now)

    def sample(self, now):
        self.held.tick(now)
        dx = (1 if self.held.down(*RIGHT) else 0) - (1 if self.held.down(*LEFT) else 0)
        dy = (1 if self.held.down(*DOWN) else 0) - (1 if self.held.down(*UP) else 0)
        j = self.jedge
        self.jedge = False
        self.held.take_hits()
        return dx, dy, j


def render_menu(demo, cols, rows, sel, stage, dt, help_, kitty):
    cv = demo.scene(cols, rows, dt)
    rec = load_scores().get(GAME, {})
    best = None
    if rec.get("score"):
        best = "best score %d   (reached night %d)" % (rec["score"], rec.get("night", 1))
    items = ["Start the night shift", "Stage select   < %d  %s >" % (stage + 1, STAGE_NAMES[stage])]
    extra = ["", "A runaway demolition robot holds the top of", "the tower. Climb up and switch it off.",
             "Keys: %s" % ("with releases (kitty protocol)" if kitty else "classic terminal mode")]
    title_screen(cv, "SCAFFOLD", "climb the tower, dodge what the Wrecker throws", items, sel, best, extra=extra,
                 keys="Up/Down choose   Left/Right stage   Enter start   M %s   ? help   Esc back" % SND.label().lower(),
                 help_lines=help_lines(kitty), show_help=help_, dim=0.4)
    return cv


def too_small(term):
    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (60x22).")


def play(term, ctl, stage):
    """One game. Returns 'again' or 'menu'."""
    g = Game(stage)
    ctl.reset()
    last = time.time()
    record = None
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
            a = shared_key(name, g.paused)
            if a == "pause":
                g.paused = True
                ctl.reset()
                SND.play("pause")
            elif a == "resume":
                g.paused = g.help = False
                ctl.reset()
                last = time.time()
            elif a == "quit":
                if not submitted and g.score:
                    submit(GAME, "score", g.score)
                    submit(GAME, "night", g.night)
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
            g.update(dt, ctl.sample(now))
        if g.over and not submitted:
            submitted = True
            record = submit(GAME, "score", g.score)
            submit(GAME, "night", g.night)
        cv = render(g, cols, rows)
        if g.paused:
            overlay(cv, help_lines(ctl.kitty) if g.help else PAUSE_LINES + ["", SND.label()])
        elif g.over:
            render_over(g, cv, record)
        term.write(cv.emit())
        time.sleep(max(0.0, 1 / 30 - (time.time() - now)))


def main():
    with KeyTerminal() as term:
        ctl = Controls(term.kitty)
        demo = TitleDemo()
        sel, stage, help_ = 0, 0, False
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
            term.write(render_menu(demo, cols, rows, sel, stage, min(0.1, now - last), help_, ctl.kitty).emit())
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
                elif k in ("up", "w", "down", "s", "tab"):
                    sel = 1 - sel
                    SND.play("menu")
                elif k in ("left", "a"):
                    stage = (stage - 1) % 5
                    sel = 1
                    SND.play("menu")
                elif k in ("right", "d"):
                    stage = (stage + 1) % 5
                    sel = 1
                    SND.play("menu")
                elif k == "m":
                    if SND.toggle():
                        SND.play("sound_on")
                elif k in ("enter", " "):
                    SND.play("start")
                    go = True
            if not go:
                continue
            while play(term, ctl, 0 if sel == 0 else stage) == "again":
                pass
            last = time.time()


# =============================================================================================
# Self-test
# =============================================================================================
def check_layout(st):
    """Static sanity: ladders join two surfaces, the start stands on something, the goal exists."""
    for L in st.ladders:
        top = st.support(L.x, L.ytop, 0.0, 0.05, cars=False)
        bot = st.support(L.x, L.ybot, 0.0, 0.05, cars=False)
        assert top and bot, "%s: ladder at x=%.1f does not join two girders" % (st.name, L.x)
        assert L.ybot - L.ytop > 1.5, "%s: ladder at x=%.1f too short" % (st.name, L.x)
    assert st.support(st.start[0], st.start[1], 0.0, 0.05) is not None, "%s: start in the air" % st.name
    assert st.goal or st.breakers, "%s: nothing to reach" % st.name
    assert st.route, "%s: no route" % st.name


def run_bot(kind, hazards, avoid, limit=180.0, seed=1):
    """Let the autopilot play stage `kind`. Returns (cleared, game time, game)."""
    g = Game(kind, seed=seed, hazards=hazards)
    g.lives = 99
    bot = Bot(g, avoid=avoid, greedy=hazards)
    deaths = 0
    t = 0.0
    while t < limit:
        g.update(1 / 30, bot)
        t += 1 / 30
        if g.deaths != deaths:
            deaths = g.deaths
        if g.state == "intro" and g.deaths and bot.i:
            bot.reset()
        if g.state in ("clear", "ending"):
            return True, t, g
    return False, t, g


def adv(g, secs, inp):
    """Advance a game by secs in frame-sized steps (a jump in inp is pressed once, at the start)."""
    n = max(1, int(round(secs * 30)))
    for i in range(n):
        g.update(1 / 30, inp if i == 0 else (inp[0], inp[1], False))


def selftest():
    t0 = time.time()
    global submit

    def no_scores(*a, **k):
        raise AssertionError("the self-test must not write scores")
    submit = no_scores
    random.seed(3)
    # 1. layouts
    for k in range(5):
        check_layout(build_stage(k))
    print("layouts: 5 stages, %d ladders, %d girders, %d lifts/beams, %d hooks, %d breakers" % (
        sum(len(build_stage(k).ladders) for k in range(5)), sum(len(build_stage(k).segs) for k in range(5)),
        sum(len(build_stage(k).plats) for k in range(5)), sum(len(build_stage(k).hooks) for k in range(5)),
        sum(len(build_stage(k).breakers) for k in range(5))))
    # 2. completable: the route autopilot reaches the goal with the real physics, nothing thrown
    for k in range(5):
        ok, tt, g = run_bot(k, hazards=False, avoid=True, limit=150)
        assert ok, "%s: the route does not reach the goal (stuck at x=%.1f y=%.1f, deaths %d)" % (
            STAGE_NAMES[k], g.player.x, g.player.y, g.deaths)
        assert g.deaths == 0, "%s: the route dies on the way (%s)" % (STAGE_NAMES[k], g.cause)
        print("route: %-17s reached in %5.1f s game time, bonus left %d" % (STAGE_NAMES[k], tt, g.bonus))
    # 3. with everything the Wrecker throws: the bot plays, dies, retries
    for k in range(5):
        cleared = 0
        stats = []
        for seed in (1, 2, 3):
            ok, tt, g = run_bot(k, hazards=True, avoid=True, limit=150, seed=seed)
            cleared += ok
            stats.append((g.thrown, g.deaths, g.jumped, g.smashed))
        thrown = sum(s[0] for s in stats)
        assert thrown > 0, "%s: nothing was thrown" % STAGE_NAMES[k]
        print("hazards: %-17s bot cleared %d/3 runs   thrown %3d  deaths %2d  jumped %2d  smashed %2d" % (
            STAGE_NAMES[k], cleared, thrown, sum(s[1] for s in stats), sum(s[2] for s in stats), sum(s[3] for s in stats)))
    # 4. the wrench smashes, a hit kills, lives run out, clears and the ending move on
    g = Game(0, seed=5)
    g.state = "play"
    p = g.player
    w = g.st.wrenches[0]
    p.x, p.y = w["x"], w["floor"]
    g.robot.timer = 99
    adv(g, 0.02, (0, 0, True))
    adv(g, 0.8, (0, 0, False))
    assert g.wrench_t > 0 and p.mode == "walk", "the wrench was not picked up by jumping"
    p.face = -1
    sc = g.score
    g.hz = [Hz("drum", p.x - 2.0, g.st.segs[1].y(p.x - 2.0), "roll", 1)]
    adv(g, 1.0, (0, 0, False))
    assert g.smashed == 1 and g.score > sc and g.state == "play", "the wrench did not smash the drum"
    p.mode = "walk"
    adv(g, 0.5, (0, -1, False))
    assert p.mode != "climb", "climbing with the wrench"
    g.wrench_t = 0
    g.hz.append(Hz("drum", p.x, p.y, "roll", -1))
    lives = g.lives
    adv(g, 0.1, (0, 0, False))
    assert g.state == "dying", "a drum on the rigger does not kill"
    adv(g, 2.5, (0, 0, False))
    assert g.lives == lives - 1 and g.state == "intro", "no respawn after a death"
    g.lives = 1
    g.state = "play"
    g.die("hit")
    adv(g, 2.5, (0, 0, False))
    assert g.over and g.state == "over", "no game over with the last life"
    # falling too far is fatal, a normal jump is not
    g = Game(0, seed=6, hazards=False)
    g.state = "play"
    adv(g, 0.02, (0, 0, True))
    adv(g, 1.0, (0, 0, False))
    assert g.state == "play" and g.player.mode == "walk", "a jump on the floor hurt"
    g.player.x, g.player.y = 24.5, g.st.segs[1].y(24.5)
    adv(g, 1.5, (1, 0, False))
    assert g.state in ("dying", "intro"), "walking off a girder end was not fatal"
    # the bonus timer
    g = Game(0, seed=7, hazards=False)
    g.state, g.bonus = "play", 100
    adv(g, 2.5, (0, 0, False))
    assert g.state == "dying" and g.cause == "time", "the bonus timer does not kill at zero"
    # extra life
    g = Game(0, seed=8, hazards=False)
    lives = g.lives
    g.add(EXTRA_LIFE)
    assert g.lives == lives + 1, "no extra life at %d" % EXTRA_LIFE
    # the last stage: pulling every breaker topples the Wrecker and starts night 2
    g = Game(4, seed=9, hazards=False)
    g.state = "play"
    for b in g.st.breakers:
        g.player.x, g.player.y = b["x"], b["y"]
        g.player.mode = "walk"
        adv(g, 0.05, (0, 0, False))
    assert g.state == "ending", "pulling all breakers does not end the night"
    adv(g, 9.0, (0, 0, False))
    assert g.night == 2 and g.st.kind == 0 and g.state == "intro", "no new night after the ending"
    print("rules: wrench smashes, no climbing with it, hits kill, long falls kill, bonus timer, game over, "
          "extra life, ending -> night 2")
    # 5. the controls: classic key repeat walks on, a tap stops soon, kitty releases stop at once
    c = Controls(False)
    c.feed("right", "press", 0.0)
    held = [c.sample(t)[0] for t in (0.1, 0.3, 0.42)]
    for i in range(10):
        c.feed("right", "press", 0.45 + i * 0.033)
    held.append(c.sample(0.7)[0])
    gone = c.sample(1.4)[0]
    assert held == [1, 1, 1, 1] and gone == 0, "classic controls: %s / %s" % (held, gone)
    c.feed(" ", "press", 2.0)
    c.feed(" ", "press", 2.03)
    assert c.sample(2.05)[2] and not c.sample(2.1)[2], "classic jump repeat counted twice"
    k = Controls(True)
    k.feed("left", "press", 0.0)
    a = k.sample(0.5)[0]
    k.feed("left", "release", 0.6)
    b = k.sample(0.61)[0]
    assert a == -1 and b == 0, "kitty controls"
    print("controls: classic repeat holds and stops, jump repeat ignored, kitty releases")
    # 6. rendering at every size, in every stage and state
    n = 0
    timing = []
    for cols, rows in ((60, 22), (70, 22), (120, 40), (200, 60)):
        tr = te = 0.0
        frames = 0
        for k in range(5):
            g = Game(k, seed=k, hazards=True)
            bot = Bot(g)
            for i in range(70):
                g.update(0.1, bot)
            for state in ("play", "intro", "dying", "clear"):
                if state != "play":
                    g.state, g.st_t = state, 1.0
                a = time.time()
                cv = render(g, cols, rows)
                b = time.time()
                cv.emit(True)
                c_ = time.time()
                tr += b - a
                te += c_ - b
                frames += 1
            g.paused = True
            overlay(cv, help_lines(True))
            cv.emit(True)
            n += frames
        g = Game(4, seed=1)
        g.state = "ending"
        for i in range(12):
            g.update(0.5, (0, 0, False))
            render(g, cols, rows).emit(True)
        g.over = True
        cv = render(g, cols, rows)
        render_over(g, cv, True)
        cv.emit(True)
        timing.append((cols, rows, tr / frames * 1000, te / frames * 1000))
    # title screen and launcher preview sizes
    d = TitleDemo()
    for cols, rows in ((60, 22), (120, 40), (24, 8), (40, 12), (60, 30)):
        render_menu(d, cols, rows, 0, 2, 0.05, False, True).emit(True) if rows >= 20 else d.scene(cols, rows, 0.05)
        n += 1
    for _ in range(300):
        d.scene(48, 14, 0.1)
    print("rendering: %d frames at 60x22, 70x22, 120x40, 200x60 (+ title, preview, overlays, ending)" % n)
    for cols, rows, r_, e_ in timing:
        print("  %3dx%-3d render %5.1f ms  emit %5.1f ms  = %5.1f ms per frame (%3.0f fps)" % (
            cols, rows, r_, e_, r_ + e_, 1000 / max(0.1, r_ + e_)))
    # 7. physics speed
    g = Game(0, seed=2)
    bot = Bot(g)
    a = time.time()
    steps = 0
    while steps < 3000:
        g.update(DT * 1.0001, bot)
        steps += 1
    print("simulation: %.0f us per physics step with hazards and autopilot" % ((time.time() - a) / steps * 1e6))
    print("Self-test ok (%.1f s)" % (time.time() - t0))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
