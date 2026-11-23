#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""CLATTERBELL - a pinball parlour of three strange tables.

A silver ball, two flippers and three original tables: the Moonbell Belfry, where bronze bells ring under a
night of owls; the Lantern Reef, a sunken garden of glowing fish and clams; and the Comet Forge, a smithy
among the stars with a third flipper. Real ball physics on a tilted table (gravity, sub-stepped collisions,
moving flippers that never let the ball slip through), a plunger you pull as far as you like, pop bumpers,
slingshots, ramps, orbits, drop targets, rollover lanes, spinners, a kickback, a ball lock with three-ball
multiball and jackpots, four missions per table and a wizard mode, bonus multiplier, extra ball, ball save,
and a tilt that punishes rough nudging.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
In terminals with the kitty keyboard protocol (kitty, WezTerm, Ghostty, recent iTerm2) the flippers stay up
exactly as long as you hold the keys; elsewhere each key press flips for a moment and holding keeps it up.
"""
import math
import random
import sys
import time

from arcadekit import (ACCENTS, AUTO_LABEL, PAUSE_LINES, AutoMode, Canvas, HeldKeys, KeyTerminal, clamp, load_scores,
                       mix, overlay, shade, shared_key, submit, title_screen)
from arcadesound import Sound

GAME = "clatterbell"
NAME = "CLATTERBELL"
TAGLINE = "a pinball parlour of three strange tables"
ACCENTS.setdefault(NAME, ((255, 226, 140), (226, 92, 70)))

TW, TH = 20.0, 41.0             # the table in units (a unit is s x s screen pixels); the drain is below y = 41
PF_R = 18.5                     # right edge of the playfield (the shooter lane is from here to TW)
OL, OR = 2.5, 16.0              # inner walls of the left and right orbit lanes
R = 0.5                         # ball radius
G = 50.0                        # gravity along the tilted table, units / s^2
DT = 1 / 120                    # physics step
SUB = 0.2                       # neither ball nor flipper surface moves more than this per sub-step (no tunnelling)
VMAX = 120.0
W_UP, W_DOWN = 21.0, 15.0       # flipper angular speeds (rad / s)
PLUNGE_MIN, PLUNGE_MAX = 40.0, 76.0
PLUNGE_T = 1.1                  # seconds to pull the plunger all the way
PL_X, PL_Y = 19.25, 38.6        # plunger tip at rest
LANE_X = 19.25
SAVE_T = 10.0
BALLS = 3
WHITE = (255, 255, 255)


def mx(x):
    return PF_R - x


# =============================================================================================
# Sound: bells, springs and solenoids
# =============================================================================================
def _arp(fs, d=0.05, v=0.3, w="tri", last=0.18):
    out = [dict(w=w, f=f, d=d, v=v) for f in fs[:-1]]
    return out + [dict(w=w, f=fs[-1], d=last, v=v, vib=(7, 0.15))]


def _bell(f, v=0.3, d=0.5):
    return [dict(w="sine", f=f, d=d, v=v), dict(w="sine", f=f * 2.76, d=d * 0.5, v=v * 0.35, at=0),
            dict(w="tri", f=f * 5.4, d=0.05, v=v * 0.2, at=0)]


SND = Sound(GAME, {
    "flip": [dict(w="noise", f=1800, f2=400, d=0.035, v=0.2), dict(w="square", f=140, f2=90, d=0.04, v=0.12, at=0)],
    "bumper0": _bell(988, 0.28, 0.35), "bumper1": _bell(1175, 0.28, 0.35), "bumper2": _bell(1319, 0.28, 0.35),
    "bumper3": _bell(880, 0.28, 0.35),
    "sling": [dict(w="noise", f=3000, f2=800, d=0.05, v=0.22), dict(w="tri", f=440, f2=330, d=0.05, v=0.2, at=0)],
    "post": [dict(w="tri", f=520, d=0.03, v=0.12)],
    "wall": [dict(w="tri", f=260, d=0.02, v=0.08)],
    "lane": [dict(w="tri", f=1568, d=0.05, v=0.2), dict(w="tri", f=2093, d=0.08, v=0.2)],
    "lanes": _arp([1047, 1319, 1568, 2093, 2637], 0.05, 0.26),
    "drop": [dict(w="square", f=330, f2=200, d=0.06, v=0.2, duty=0.3), dict(w="noise", f=2500, d=0.04, v=0.12, at=0)],
    "bank": _arp([523, 659, 784, 1047], 0.06, 0.3, "square", 0.25),
    "reset": [dict(w="square", f=200, f2=260, d=0.08, v=0.16, duty=0.3)],
    "spin": [dict(w="square", f=2400, d=0.012, v=0.08, duty=0.2)],
    "orbit": [dict(w="saw", f=330, f2=990, d=0.22, v=0.14)],
    "ramp_up": [dict(w="tri", f=262, f2=784, d=0.3, v=0.2, curve="lin")],
    "ramp": _arp([784, 988, 1175], 0.05, 0.28, "tri", 0.2),
    "ramp_fail": [dict(w="tri", f=500, f2=260, d=0.15, v=0.16)],
    "scoop": [dict(w="sine", f=220, f2=110, d=0.18, v=0.32), dict(w="noise", f=900, d=0.06, v=0.14, at=0)],
    "eject": [dict(w="noise", f=1200, f2=300, d=0.08, v=0.3), dict(w="square", f=180, f2=90, d=0.08, v=0.2, at=0)],
    "kick": [dict(w="noise", f=1500, f2=200, d=0.12, v=0.36), dict(w="square", f=120, f2=60, d=0.12, v=0.24, at=0)],
    "plunge": [dict(w="noise", f=900, f2=2400, d=0.1, v=0.24), dict(w="tri", f=180, f2=420, d=0.1, v=0.18, at=0)],
    "pull": [dict(w="tri", f=140, f2=120, d=0.05, v=0.1)],
    "skill": _arp([1047, 1319, 1568, 2093, 1568, 2093, 2637], 0.05, 0.3, "square", 0.3),
    "lock": _bell(523, 0.4, 0.9) + [dict(w="tri", f=784, d=0.2, v=0.2, at=0.25)],
    "multi": [dict(w="square", f=f, d=0.08, v=0.26, duty=0.3) for f in (392, 523, 659, 784, 1047, 784, 1047)] +
             [dict(w="square", f=1319, d=0.5, v=0.3, vib=(6, 0.3))],
    "jackpot": _bell(1568, 0.36, 0.8) + [dict(w="square", f=f, d=0.07, v=0.24, duty=0.25, at=0.1 + i * 0.07)
                                        for i, f in enumerate((1047, 1319, 1568, 2093, 2637))],
    "mission": _arp([392, 523, 659, 784], 0.08, 0.3, "saw", 0.3),
    "mshot": [dict(w="square", f=880, d=0.05, v=0.22), dict(w="square", f=1320, d=0.12, v=0.22)],
    "mdone": [dict(w="tri", f=f, d=0.08, v=0.3) for f in (523, 659, 784, 1047, 1319)] +
             [dict(w="tri", f=1568, d=0.5, v=0.32, vib=(6, 0.2), r="lin")],
    "mfail": [dict(w="saw", f=392, f2=196, d=0.4, v=0.2)],
    "extra": _arp([1047, 1319, 1568, 2093, 1568, 2093], 0.06, 0.3, "square", 0.4),
    "save": [dict(w="tri", f=440, f2=880, d=0.12, v=0.28), dict(w="tri", f=880, d=0.12, v=0.24)],
    "nudge": [dict(w="noise", f=300, f2=80, d=0.1, v=0.3)],
    "warn": [dict(w="square", f=200, d=0.12, v=0.26, duty=0.4), dict(w="square", f=200, d=0.12, v=0.26, at=0.2)],
    "tilt": [dict(w="saw", f=160, f2=60, d=0.9, v=0.36, r="lin")],
    "drain": [dict(w="tri", f=660, f2=330, d=0.12, v=0.3), dict(w="tri", f=330, f2=110, d=0.35, v=0.32, r="lin")],
    "bonus": [dict(w="square", f=1568, d=0.02, v=0.1, duty=0.25)],
    "over": [dict(w="tri", f=523, d=0.18, v=0.36), dict(w="tri", f=466, d=0.18, v=0.36), dict(w="tri", f=392, d=0.18, v=0.36),
             dict(w="tri", f=330, f2=262, d=0.7, v=0.38, r="lin")],
    "search": [dict(w="square", f=150, d=0.05, v=0.16)],
    "menu": [dict(w="tri", f=660, d=0.025, v=0.2)],
    "start": _bell(784, 0.3, 0.4) + [dict(w="tri", f=1175, d=0.2, v=0.26, at=0.12)],
    "pause": [dict(w="tri", f=523, f2=392, d=0.07, v=0.22)],
    "sound_on": [dict(w="tri", f=440, d=0.06, v=0.35), dict(w="tri", f=880, d=0.12, v=0.35)],
})


# =============================================================================================
# The three tables: looks, names and missions
# =============================================================================================
THEMES = {
    "belfry": dict(
        name="MOONBELL BELFRY", short="BELFRY", story=["Bronze bells ring under a sky", "full of owls and an old moon."],
        field=((16, 18, 52), (40, 30, 82)), pattern="stars", wood=((70, 44, 30), (30, 18, 14)),
        plastic=(206, 156, 72), plastic2=(130, 82, 38), rubber=(238, 234, 222), metal=(176, 182, 204),
        bumper=(150, 98, 44), cap=(250, 208, 112), ramp=(255, 186, 96), lamp=(255, 196, 92), lamp2=(130, 190, 255),
        accent=(255, 214, 120), flip=(236, 226, 206), ballglow=(255, 220, 150),
        bumper_word="BELL", ramp_name="BELL ROPE", scoop_name="CRYPT", drop_name="CHIMES", spin_name="WEATHERVANE",
        multi="THIRTEEN BELLS", wizard="MIDNIGHT CHORUS",
        missions=[("TOLL THE HOUR", ("ramp",), 3), ("OWL ROUND", ("lorbit", "rorbit"), 4),
                  ("ROPE CLIMB", ("spin",), 30), ("BAT FLURRY", ("bumper",), 20)]),
    "reef": dict(
        name="LANTERN REEF", short="REEF", story=["A sunken garden of lantern fish,", "clams and slow green light."],
        field=((6, 40, 58), (8, 74, 84)), pattern="caustic", wood=((30, 52, 70), (10, 20, 30)),
        plastic=(240, 120, 140), plastic2=(140, 50, 80), rubber=(236, 240, 232), metal=(170, 200, 210),
        bumper=(170, 40, 110), cap=(255, 130, 200), ramp=(90, 230, 230), lamp=(110, 240, 230), lamp2=(255, 150, 200),
        accent=(120, 240, 220), flip=(236, 242, 236), ballglow=(160, 255, 240),
        bumper_word="ANEMONE", ramp_name="RIPTIDE", scoop_name="CLAM", drop_name="PEARLS", spin_name="PINWHEEL",
        multi="LANTERN TIDE", wizard="ABYSS GLOW",
        missions=[("SQUID CHASE", ("ramp",), 3), ("CURRENT RUN", ("lorbit", "rorbit"), 4),
                  ("PEARL DIVE", ("drop",), 6), ("SCHOOLING", ("bumper",), 20)]),
    "forge": dict(
        name="COMET FORGE", short="FORGE", story=["A smithy between the stars.", "Three flippers, one hot comet."],
        field=((30, 18, 20), (60, 26, 24)), pattern="cracks", wood=((50, 50, 58), (18, 18, 24)),
        plastic=(150, 160, 178), plastic2=(70, 76, 92), rubber=(240, 228, 210), metal=(200, 196, 190),
        bumper=(170, 60, 20), cap=(255, 160, 60), ramp=(255, 110, 70), lamp=(255, 150, 60), lamp2=(255, 230, 120),
        accent=(255, 160, 90), flip=(240, 232, 220), ballglow=(255, 190, 120),
        bumper_word="ANVIL", ramp_name="COMET RAMP", scoop_name="CRUCIBLE", drop_name="INGOTS", spin_name="BELLOWS",
        multi="METEOR SHOWER", wizard="SUPERNOVA",
        missions=[("STOKE THE FIRE", ("spin",), 30), ("TEMPER", ("ramp",), 3),
                  ("HAMMERFALL", ("drop",), 6), ("STARFIRE", ("lorbit",), 3)]),
}
ORDER = ["belfry", "reef", "forge"]
SHOTS = ("ramp", "lorbit", "rorbit", "scoop", "drop", "spin")
POINTS = dict(bumper=1000, sling=110, post=10, lane=2000, drop=5000, bank=50000, spin=300, orbit=20000, ramp=30000,
              scoop=15000, skill=250000, mshot=75000, mdone=500000, jackpot=1000000, super=3000000, wizard=1500000,
              kick=5000, lock=50000)


def help_lines(kitty=True):
    mode = (["Key releases are reported: a flipper stays up as long",
             "as you hold it, the plunger pulls while Space is held."] if kitty else
            ["Classic keys: a press flips for a moment, holding keeps",
             "it up; a tap on Space plunges at half strength."])
    return ["CLATTERBELL - keys", "",
            "Left / Z / A        left flipper",
            "Right / M / L / /   right flipper (and the upper one)",
            "Space / Down / S    pull the plunger, let go to launch",
            "Up / W / N          nudge (too often: TILT)",
            "Esc / P             pause (Q quit, M sound)   ? help", ""] + mode + [
            "",
            "Top lanes: bonus X (flippers move the lit lanes); plunge",
            "into the blinking lane for a SKILL SHOT. Drop targets",
            "light LOCK; two locks start 3-ball MULTIBALL, the ramp",
            "then scores the JACKPOT. Two orbits light a MISSION at",
            "the scoop, four missions the wizard mode. Three ramps",
            "light EXTRA BALL. The kickback guards the left outlane.",
            "Auto mode: Space pause, +/- speed, Esc stop."]


# =============================================================================================
# Table geometry: walls, posts, kickers, sensors, flippers
# =============================================================================================
class Seg:
    __slots__ = ("x1", "y1", "x2", "y2", "dx", "dy", "L", "nx", "ny", "kind", "e", "th", "id", "look", "circle",
                 "oneway")

    def __init__(self, a, b, kind="wall", e=0.3, th=0.12, id=None, look="metal", oneway=False):
        self.x1, self.y1 = a
        self.x2, self.y2 = b
        L = math.hypot(self.x2 - self.x1, self.y2 - self.y1)
        self.L = L
        self.dx, self.dy = (self.x2 - self.x1) / L, (self.y2 - self.y1) / L
        self.nx, self.ny = -self.dy, self.dx          # left-hand normal
        self.kind, self.e, self.th, self.id, self.look = kind, e, th, id, look
        self.circle = False
        self.oneway = oneway


class Circ:
    __slots__ = ("x", "y", "r", "kind", "e", "id", "look", "circle")

    def __init__(self, x, y, r, kind="post", e=0.6, id=None, look="post"):
        self.x, self.y, self.r = x, y, r
        self.kind, self.e, self.id, self.look = kind, e, id, look
        self.circle = True


class FlipDef:
    def __init__(self, x, y, L, r1, r2, rest, up, side, upper=False):
        self.x, self.y, self.L, self.r1, self.r2 = x, y, L, r1, r2
        self.rest, self.up = math.radians(rest), math.radians(up)
        self.side, self.upper = side, upper


class Table:
    """Everything that does not move (plus where the moving parts sit), built from code once per table."""

    def __init__(self, key):
        self.key = key
        self.th = THEMES[key]
        self.colliders = []
        self.sensors = []         # (x1, y1, x2, y2, name, dirx, diry): crossing in (dirx, diry) counts (0, 0: both)
        self.flips = []
        self.plastics = []        # (points, colour key) filled shapes under the walls
        self.lamps = {}           # name -> (x, y, shape, size, colour key, angle)
        self.drops = []           # Seg per drop target
        self.bumpers = []
        self.slings = []
        self.ramp = None
        self.scoop = None
        self.spinner = None
        self.kick = None
        self.guides = []          # decorative rails drawn over the field
        self.chassis(key)
        getattr(self, "build_" + key)()
        self.common_lamps()
        self.grid = {}
        for i, c in enumerate(self.colliders):
            if c.circle:
                x0, y0, x1, y1 = c.x - c.r, c.y - c.r, c.x + c.r, c.y + c.r
            else:
                x0, x1 = min(c.x1, c.x2) - c.th, max(c.x1, c.x2) + c.th
                y0, y1 = min(c.y1, c.y2) - c.th, max(c.y1, c.y2) + c.th
            m = R + 0.25
            for gy in range(int((y0 - m) // 2), int((y1 + m) // 2) + 1):
                for gx in range(int((x0 - m) // 2), int((x1 + m) // 2) + 1):
                    self.grid.setdefault((gx, gy), []).append(c)

    # --- builders ---------------------------------------------------------------------------------
    def seg(self, a, b, **k):
        s = Seg(a, b, **k)
        self.colliders.append(s)
        return s

    def chain(self, pts, **k):
        return [self.seg(pts[i], pts[i + 1], **k) for i in range(len(pts) - 1)]

    def post(self, x, y, r=0.3, kind="post", e=0.6, look="post", id=None):
        c = Circ(x, y, r, kind, e, id, look)
        self.colliders.append(c)
        return c

    def bumper(self, x, y, r=1.05):
        c = self.post(x, y, r, "bumper", 0.4, "bumper", id=len(self.bumpers))
        self.bumpers.append(c)
        return c

    def chassis(self, key):
        # the arch over the top, the outer walls, the shooter lane and its one-way gate
        n = 30
        arch = [(10 + 10 * math.cos(math.pi + math.pi * i / n), 10 + 10 * math.sin(math.pi + math.pi * i / n))
                for i in range(n + 1)]
        self.arch = arch
        self.chain(arch, e=0.25, look="rail")
        self.chain([(0, 10), (0, 15.5), (0.6, 19.0), (0, 23.0), (0, 41.6)], e=0.3, look="rail")
        self.seg((20, 10), (20, 41.6), look="rail")
        self.seg((PF_R, 41.6), (PF_R, 12.2), look="rail")
        g = self.seg((20, 11.0), (PF_R, 12.2), look="gate", oneway=True)    # left normal points up: blocks from above
        g.kind = "gate"
        if key != "forge":
            self.chain([(PF_R, 15.5), (PF_R - 0.6, 19.0), (PF_R, 23.0)], e=0.3, look="rail")
        # orbit lanes
        self.seg((OL, 9.0), (OL, 16.6), look="guide")
        if key != "forge":
            self.seg((OR, 9.0), (OR, 16.6), look="guide")
        self.sensors.append((0.05, 13.0, OL - 0.05, 13.0, "lorbit", 0, -1))
        if key != "forge":
            self.sensors.append((OR + 0.05, 13.0, PF_R - 0.05, 13.0, "rorbit", 0, -1))
        # top rollover lanes
        self.lane_x = []
        gx = (6.2, 8.5, 10.8, 13.1)
        for x in gx:
            self.seg((x, 3.9), (x, 6.2), look="pin", th=0.18, e=0.4)
        for i in range(3):
            a, b = gx[i] + 0.2, gx[i + 1] - 0.2
            self.sensors.append((a, 5.0, b, 5.0, "lane%d" % i, 0, 1))
            self.lane_x.append((gx[i] + gx[i + 1]) / 2)
            self.lamps["lane%d" % i] = ((gx[i] + gx[i + 1]) / 2, 7.0, "disc", 0.42, "lamp", 0)
        # lower field, left side, then mirrored
        for side in (1, -1):
            f = (lambda x: x) if side == 1 else mx
            p = lambda x, y: (f(x), y)
            # outlane / inlane separator
            self.chain([p(1.5, 26.0), p(1.5, 31.47), p(5.93, 34.24)], look="guide")
            self.post(f(1.5), 26.0, 0.25)
            # slingshot
            A, B, C = p(3.2, 27.0), p(3.2, 30.82), p(5.3, 32.13)
            self.seg(A, B, look="plastic", e=0.3)
            self.seg(B, C, look="plastic", e=0.3)
            sl = self.seg(A, C, kind="sling", e=0.55, look="rubber", id=len(self.slings))
            self.slings.append(sl)
            for q in (A, B, C):
                self.post(q[0], q[1], 0.3, look="post")
            self.plastics.append(([A, B, C], "plastic"))
            self.sensors.append((f(1.7), 28.0, f(3.1), 28.0, "inlane", 0, 1))
        self.flips.append(FlipDef(5.7, 34.6, 3.1, 0.55, 0.28, 30, -28, "L"))
        self.flips.append(FlipDef(mx(5.7), 34.6, 3.1, 0.55, 0.28, 150, 208, "R"))
        # kickback in the left outlane, outlane drains
        self.kick = (0.66, 30.6)
        self.sensors.append((0.05, 30.6, 1.5, 30.6, "kickback", 0, 1))
        self.sensors.append((0.05, 28.5, 1.5, 28.5, "outlane", 0, 1))
        self.sensors.append((mx(1.5), 28.5, mx(0.05), 28.5, "outlane", 0, 1))

    def common_lamps(self):
        cx = PF_R / 2
        self.lamps["shoot_again"] = (cx, 31.4, "disc", 0.55, "lamp2", 0)
        for i in range(5):
            self.lamps["bx%d" % (i + 2)] = (cx - 2.6 + i * 1.3, 28.8, "disc", 0.36, "lamp", 0)
        for i in range(4):
            self.lamps["m%d" % i] = (cx - 1.95 + i * 1.3, 26.4, "diamond", 0.5, "lamp2", 0)
        self.lamps["kick"] = (0.8, 33.2, "disc", 0.4, "lamp2", 0)
        self.lamps["lane_skill"] = (0, 0, "none", 0, "lamp", 0)

    def arrow(self, name, x, y, ang, size=0.8, col="lamp"):
        self.lamps[name] = (x, y, "arrow", size, col, ang)

    def lock_lamps(self, x, y):
        for i in range(3):
            self.lamps["lock%d" % i] = (x + i * 0.9, y, "disc", 0.34, "lamp2", 0)

    def make_ramp(self, back_a, back_b, path, vmin, exit_v, mouth):
        """back_a -> back_b is the ramp's entry line (its left normal faces the mouth); path is the ride."""
        s = self.seg(back_a, back_b, kind="ramp", e=0.25, look="ramp")
        d = [0.0]
        for i in range(1, len(path)):
            d.append(d[-1] + math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1]))
        self.ramp = dict(seg=s, path=path, dist=d, vmin=vmin, exit=exit_v, mouth=mouth)
        for a, b in mouth:
            self.seg(a, b, look="plastic")

    def make_scoop(self, x, y, ev):
        self.scoop = (x, y, ev[0], ev[1])

    def make_drops(self, a, b, n, normal_sign=1):
        (x1, y1), (x2, y2) = a, b
        for i in range(n):
            t0, t1 = (i + 0.08) / n, (i + 0.92) / n
            s = self.seg((x1 + (x2 - x1) * t0, y1 + (y2 - y1) * t0), (x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1),
                         kind="drop", e=0.35, th=0.22, look="drop", id=i)
            if normal_sign < 0:
                s.nx, s.ny = -s.nx, -s.ny
            self.drops.append(s)

    def make_spinner(self, x1, y1, x2, y2):
        self.spinner = (x1, y1, x2, y2)
        self.sensors.append((x1, y1, x2, y2, "spin", 0, 0))

    # --- the tables ------------------------------------------------------------------------------
    def build_belfry(self):
        for x, y in ((7.0, 10.2), (11.8, 10.2), (9.4, 13.6)):
            self.bumper(x, y)
        # the left ramp: its mouth is between the orbit wall and a guide, it rides over the field to the right inlane
        self.make_ramp((OL, 14.6), (5.0, 15.6),
                       [(3.75, 14.9), (3.8, 10.6), (4.6, 8.2), (6.4, 7.3), (12.4, 7.3), (14.4, 8.4), (15.0, 11.5),
                        (15.6, 18.0), (16.1, 24.6)], 26.0, (0.0, 12.0), [((5.0, 15.6), (5.0, 18.0))])
        self.post(5.0, 18.0, 0.25)
        self.arrow("ramp", 3.75, 19.0, -90)
        self.make_scoop(13.6, 16.8, (-6.4, 13.5))
        self.arrow("scoop", 12.9, 19.3, -70)
        self.lock_lamps(11.9, 21.4)
        self.make_drops((7.35, 19.2), (11.15, 20.0), 3)
        self.arrow("drop", 9.25, 21.6, -90, 0.7)
        self.make_spinner(OR + 0.05, 14.6, PF_R - 0.05, 14.6)
        self.arrow("lorbit", 1.3, 19.6, -100)
        self.arrow("rorbit", 17.0, 21.0, -80)

    def build_reef(self):
        for x, y in ((6.6, 10.4), (11.2, 9.6), (9.2, 13.8)):
            self.bumper(x, y)
        self.make_ramp((13.5, 15.6), (OR, 14.6),
                       [(14.75, 14.9), (14.7, 10.6), (13.9, 8.2), (12.1, 7.3), (6.1, 7.3), (4.1, 8.4), (3.5, 11.5),
                        (2.9, 18.0), (2.4, 24.6)], 26.0, (0.0, 12.0), [((13.5, 15.6), (13.5, 18.0))])
        self.post(13.5, 18.0, 0.25)
        self.arrow("ramp", 14.75, 19.0, -90)
        self.make_scoop(4.9, 16.8, (6.4, 13.5))
        self.arrow("scoop", 5.6, 19.3, -110)
        self.lock_lamps(4.2, 21.4)
        self.make_drops((11.4, 19.6), (14.2, 21.0), 3)
        self.arrow("drop", 12.2, 22.6, -63, 0.7)
        self.make_spinner(0.05, 14.6, OL - 0.05, 14.6)
        self.arrow("lorbit", 1.3, 19.6, -100)
        self.arrow("rorbit", 17.0, 21.0, -80)

    def build_forge(self):
        for x, y in ((6.4, 10.6), (12.2, 10.6), (9.3, 8.8)):
            self.bumper(x, y, 0.95)
        # centre ramp
        self.make_ramp((10.5, 16.6), (8.0, 17.4),
                       [(9.25, 16.6), (9.25, 13.0), (9.0, 7.4), (7.6, 5.2), (5.2, 5.0), (3.4, 7.0), (2.9, 11.0),
                        (2.7, 18.0), (2.4, 24.6)], 27.0, (0.0, 12.0), [((8.0, 17.4), (8.0, 19.4)), ((10.5, 16.6), (10.5, 19.4))])
        self.post(8.0, 19.4, 0.25)
        self.post(10.5, 19.4, 0.25)
        self.arrow("ramp", 9.25, 20.8, -90)
        self.make_scoop(14.9, 13.8, (-5.0, 13.0))
        self.arrow("scoop", 14.3, 16.2, -70)
        self.lock_lamps(3.9, 21.0)
        self.make_drops((12.9, 19.2), (15.7, 20.8), 3)
        self.arrow("drop", 13.5, 22.6, -60, 0.7)
        self.make_spinner(0.05, 14.6, OL - 0.05, 14.6)
        self.arrow("lorbit", 1.3, 19.6, -100)
        # the upper flipper on the right wall (this table has no right orbit lane: the ball comes down onto it)
        self.flips.append(FlipDef(17.55, 17.0, 2.5, 0.45, 0.24, 155, 200, "R", upper=True))
        self.seg((PF_R, 16.19), (17.41, 16.70), look="guide")      # leads the ball onto the bat
        self.chain([(PF_R, 18.6), (PF_R - 0.6, 21.2), (PF_R, 23.8)], e=0.3, look="rail")


_TABLES = {}


def table(key):
    t = _TABLES.get(key)
    if t is None:
        t = _TABLES[key] = Table(key)
    return t


# =============================================================================================
# Moving parts
# =============================================================================================
class Ball:
    __slots__ = ("x", "y", "vx", "vy", "state", "ride", "rv", "still", "trail", "hold", "age", "launched", "skill",
                 "first")

    def __init__(self, x, y, vx=0.0, vy=0.0, state="play"):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.state = state          # lane (shooter lane), play, ride (on the ramp), scoop (held), gone
        self.ride = 0.0
        self.rv = 0.0
        self.still = 0.0
        self.trail = []
        self.hold = 0.0
        self.age = 0.0
        self.launched = False
        self.skill = False
        self.first = None


class Flipper:
    def __init__(self, d):
        self.d = d
        self.x, self.y, self.L, self.r1, self.r2 = d.x, d.y, d.L, d.r1, d.r2
        self.ang = d.rest
        self.w = 0.0
        self.on = False
        self.set()

    def set(self):
        self.ca, self.sa = math.cos(self.ang), math.sin(self.ang)

    @property
    def raised(self):
        return abs(self.ang - self.d.up) < 0.05

    def tip(self, ang=None):
        a = self.ang if ang is None else ang
        return self.x + math.cos(a) * self.L, self.y + math.sin(a) * self.L

    def move(self, h):
        tgt = self.d.up if self.on else self.d.rest
        diff = tgt - self.ang
        if abs(diff) < 1e-9:
            self.w = 0.0
            return
        sp = (W_UP if self.on else W_DOWN) * h
        step = clamp(diff, -sp, sp)
        self.ang += step
        self.w = step / h
        self.set()

    def local(self, x, y):
        """(t along the bat 0..1, distance from its axis, signed side) of a point."""
        rx, ry = x - self.x, y - self.y
        t = rx * self.ca + ry * self.sa
        side = -rx * self.sa + ry * self.ca
        tt = clamp(t, 0.0, self.L)
        return tt / self.L, math.hypot(rx - self.ca * tt, ry - self.sa * tt), side


# =============================================================================================
# The game: physics and rules
# =============================================================================================
class Game:
    def __init__(self, key="belfry", seed=None, quiet=False, demo=False, balls=BALLS, sandbox=False):
        self.key = key
        self.t = table(key)
        self.th = self.t.th
        self.rnd = random.Random(seed)
        self.quiet = quiet or demo or sandbox
        self.demo, self.sandbox = demo, sandbox
        self.balls_total = balls
        self.hi = 0 if (demo or sandbox) else (load_scores().get(GAME, {}).get(key) or 0)
        self.over = self.paused = self.help = False
        self.clock = 0.0
        self.acc = 0.0
        self.score = 0
        self.ball_no = 1
        self.extra = 0            # extra balls earned and not yet played
        self.balls = []
        self.flippers = [Flipper(d) for d in self.t.flips]
        self.drops_up = [True] * len(self.t.drops)
        self.drop_reset = 0.0
        self.spin_a, self.spin_v, self.spin_half = 0.0, 0.0, 0
        self.pull = 0.0
        self.plunger_y = PL_Y
        self.plunger_kick = 0.0
        self.prev_inp = (False, False, False, None)
        self.parts = []
        self.msgs = []
        self.events = []          # (time, name) log of shots (the bot's practice uses it)
        self.flash = {}           # thing -> time it was last hit (for lighting)
        self.shake = 0.0
        self.shake_dir = (0.0, 0.0)
        self.tilt = 0.0
        self.warnings = 0
        self.tilted = False
        self.locked = 0           # balls held in the lock (they stay for the whole game)
        self.lock_lit = 0         # how many locks are lit
        self.kick_lit = True
        self.mission_lit = True
        self.mission = None       # [index, got, time left]
        self.missions_done = set()
        self.wizard = 0.0
        self.multiball = False
        self.jackpot_lit = False
        self.jackpot_value = POINTS["jackpot"]
        self.super_t = 0.0
        self.ramps = 0
        self.extra_lit = False
        self.extra_at = 3
        self.orbits = 0
        self.lanes = [False, False, False]
        self.bx = 1
        self.bonus = 0
        self.save_t = 0.0
        self.save_armed = True
        self.skill_lane = 1
        self.autoplunge = 0.0
        self.queue = 0            # balls still to be ejected from the scoop (multiball start)
        self.queue_t = 0.0
        self.pending = 0          # saved balls waiting for the shooter lane
        self.state, self.state_t = "play", 0.0
        self.bonus_show = None
        self.stats = dict(ramps=0, orbits=0, scoops=0, banks=0, missions=0, multiballs=0, jackpots=0, skill=0,
                          kicks=0, saves=0, tilts=0, spins=0, bumpers=0, extra=0, wizard=0, locks=0, searches=0)
        self.serve()

    # --- helpers ---------------------------------------------------------------------------------
    def snd(self, name, vol=1.0, gap=0.04):
        if not self.quiet:
            SND.play(name, vol, gap)

    def say(self, text, sub="", t=1.8, col=None, big=True):
        self.msgs.append([text, sub, t, col or self.th["accent"], big, t])
        if len(self.msgs) > 6:
            del self.msgs[0]

    def add(self, pts, bonus=0):
        if self.tilted or self.sandbox:
            return
        self.score += pts * (2 if self.wizard > 0 else 1)
        self.bonus += bonus

    def burst(self, x, y, n, cols, spd=8.0, life=0.5):
        r = self.rnd
        for _ in range(n):
            a = r.uniform(0, 2 * math.pi)
            v = r.uniform(0.3, 1.0) * spd
            self.parts.append([x, y, math.cos(a) * v, math.sin(a) * v, 0.0, life * r.uniform(0.6, 1.2), r.choice(cols)])
        if len(self.parts) > 300:
            del self.parts[:len(self.parts) - 300]

    def in_play(self):
        return [b for b in self.balls if b.state != "gone"]

    def serve(self, auto=False):
        b = Ball(LANE_X, PL_Y - R - 0.02, state="lane")
        self.balls.append(b)
        if auto:
            self.autoplunge = 0.7
        return b

    def mission_def(self, i):
        return self.th["missions"][i]

    def lit_shots(self):
        """The shots whose arrows are lit, with what they light for."""
        lit = {}
        if self.wizard > 0:
            for s in SHOTS:
                lit[s] = "wizard"
        if self.mission:
            for s in self.mission_def(self.mission[0])[1]:
                lit.setdefault(s, "mission")
        if self.jackpot_lit:
            lit["ramp"] = "jackpot"
        if self.super_t > 0:
            lit["scoop"] = "super"
        if self.lock_lit and "scoop" not in lit:
            lit["scoop"] = "lock"
        if self.mission_lit and not self.mission and "scoop" not in lit:
            lit["scoop"] = "mission"
        if self.extra_lit and "ramp" not in lit:
            lit["ramp"] = "extra"
        return lit

    # --- time ------------------------------------------------------------------------------------
    def update(self, dt, inp):
        """Advance by dt seconds. inp: (left, right, plunger, nudge) or a callable returning it per physics step."""
        if self.paused or self.over:
            return
        self.acc += min(dt, 0.1)
        first = True
        while self.acc >= DT:
            self.acc -= DT
            i = inp() if callable(inp) else (inp if first else (inp[0], inp[1], inp[2], None))
            first = False
            self.step(i)
            if self.over:
                break

    def step(self, inp):
        L, Rt, P, N = inp
        pl, pr, pp, _ = self.prev_inp
        self.prev_inp = inp
        self.clock += DT
        self.state_t += DT
        self.shake = max(0.0, self.shake - DT * 3)
        self.tilt = max(0.0, self.tilt - DT * 0.35)
        if self.state == "bonus":
            for f in self.flippers:
                f.on = False
                f.move(DT)
            self.bonus_step()
            self.fx_step()
            return
        if self.state == "over":
            self.fx_step()
            return
        # flippers (and the lane change they do)
        live = not self.tilted
        for f in self.flippers:
            on = live and (L if f.d.side == "L" else Rt)
            if on and not f.on:
                self.snd("flip", 0.6, 0.02)
            f.on = on
        if live and L and not pl:
            self.lane_change(-1)
        if live and Rt and not pr:
            self.lane_change(1)
        # plunger
        if self.autoplunge > 0:
            self.autoplunge -= DT
            if self.autoplunge <= 0:
                self.fire(0.86)
        elif P:
            if self.pull == 0:
                self.snd("pull", 0.6)
            self.pull = min(1.0, self.pull + DT / PLUNGE_T)
        elif self.pull > 0:
            self.fire(self.pull)
            self.pull = 0.0
        tgt = PL_Y + self.pull * 1.5
        if self.plunger_kick > 0:
            self.plunger_kick -= DT
            tgt = PL_Y - 0.3
        self.plunger_y += (tgt - self.plunger_y) * min(1.0, DT * (40 if self.plunger_kick > 0 else 12))
        if N and live:
            self.nudge(N)
        self.physics()
        self.rules_step()
        self.fx_step()

    def fx_step(self):
        for p in self.parts:
            p[0] += p[2] * DT
            p[1] += p[3] * DT
            p[3] += G * 0.4 * DT
            p[4] += DT
        self.parts = [p for p in self.parts if p[4] < p[5]]
        for m in self.msgs:
            m[2] -= DT
        self.msgs = [m for m in self.msgs if m[2] > 0]
        self.spin_a += self.spin_v * DT
        self.spin_v *= (1 - 1.6 * DT)
        if abs(self.spin_v) < 0.4:
            self.spin_v = 0.0
        half = int(self.spin_a / math.pi)
        if half != self.spin_half:
            n = abs(half - self.spin_half)
            self.spin_half = half
            for _ in range(min(n, 3)):
                self.spinner_turn()

    # --- input actions ---------------------------------------------------------------------------
    def lane_change(self, d):
        if any(b.state == "lane" and not b.launched for b in self.balls) and not any(
                b.state == "play" for b in self.balls):
            self.skill_lane = (self.skill_lane + d) % 3
            return
        self.lanes = self.lanes[-1:] + self.lanes[:-1] if d > 0 else self.lanes[1:] + self.lanes[:1]

    def fire(self, pull):
        """The plunger springs back: a ball resting on it flies up the shooter lane."""
        self.plunger_kick = 0.06
        fired = False
        for b in self.balls:
            if b.state == "lane" and b.x > PF_R and b.y > self.plunger_y - R - 0.45:
                v = PLUNGE_MIN + (PLUNGE_MAX - PLUNGE_MIN) * pull
                b.vy = -v * self.rnd.uniform(0.997, 1.003)
                b.vx = 0.0
                b.y = min(b.y, PL_Y - R - 0.02)
                fired = True
        if fired:
            self.snd("plunge")

    def nudge(self, d):
        dx, dy = {"up": (0.0, -1.0), "left": (-1.0, -0.3), "right": (1.0, -0.3)}.get(d, (0.0, -1.0))
        for b in self.balls:
            if b.state == "play":
                b.vx += dx * 9.0 + self.rnd.uniform(-1.5, 1.5)
                b.vy += dy * 11.0
        self.shake, self.shake_dir = 1.0, (-dx, -dy)
        self.tilt += 1.0
        self.snd("nudge")
        if self.tilt > 3.2:
            self.do_tilt()
        elif self.tilt > 2.0:
            self.warnings += 1
            self.say("DANGER", "tilt warning", 1.2, (255, 90, 70))
            self.snd("warn")

    def do_tilt(self):
        if self.tilted:
            return
        self.tilted = True
        self.stats["tilts"] += 1
        self.say("TILT", "ball lost", 3.0, (255, 60, 50))
        self.snd("tilt")
        self.save_t = 0.0
        self.mission = None
        for f in self.flippers:
            f.on = False

    # --- physics ---------------------------------------------------------------------------------
    def physics(self):
        balls = [b for b in self.balls if b.state in ("play", "lane")]
        for b in self.balls:
            if b.state == "ride":
                self.ride_step(b, DT)
        fast = 0.0
        for b in balls:
            fast = max(fast, abs(b.vx) + abs(b.vy) + G * DT)
        flip = max([abs(f.w) * f.L for f in self.flippers] + [W_UP * 3.1 if any(
            f.on != f.raised for f in self.flippers) else 0.0])
        n = max(1, int(math.ceil(max(fast, flip) * DT / SUB)))
        h = DT / n
        for _ in range(n):
            for f in self.flippers:
                f.move(h)
            for b in balls:
                if b.state not in ("play", "lane"):
                    continue
                ox, oy = b.x, b.y
                b.vy += G * h
                b.x += b.vx * h
                b.y += b.vy * h
                self.collide(b)
                for f in self.flippers:
                    self.collide_flipper(b, f)
                if b.state == "lane" or b.x > PF_R - 0.6:
                    self.collide_plunger(b)
                self.sense(b, ox, oy)
            if len(balls) > 1:
                self.collide_balls(balls)
        for b in balls:
            sp = math.hypot(b.vx, b.vy)
            if sp > VMAX:
                b.vx, b.vy = b.vx / sp * VMAX, b.vy / sp * VMAX
                sp = VMAX
            # rolling resistance
            k = 1 - 0.12 * DT
            b.vx *= k
            b.vy *= k
            b.age += DT
            b.trail.append((b.x, b.y))
            if len(b.trail) > 5:
                del b.trail[0]
            if b.state == "play":
                b.still = b.still + DT if sp < 1.2 else 0.0
                if b.still > 3.5 and not self.cradled(b):
                    self.ball_search(b)
                if self.t.scoop:
                    self.scoop_check(b, sp)
            if b.y > TH + 0.5 or b.x < -2 or b.x > TW + 2 or b.y < -3:
                self.drain(b)

    def cradled(self, b):
        for f in self.flippers:
            if f.on:
                t, d, side = f.local(b.x, b.y)
                if d < f.r1 + R + 0.6:
                    return True
        return False

    def ball_search(self, b):
        b.still = 0.0
        b.vx, b.vy = self.rnd.uniform(-8, 8), -self.rnd.uniform(14, 22)
        self.stats["searches"] += 1
        self.snd("search")

    def collide(self, b):
        cell = self.t.grid.get((int(b.x // 2), int(b.y // 2)))
        if not cell:
            return
        for c in cell:
            if c.kind == "drop" and not self.drops_up[c.id]:
                continue
            if c.circle:
                ex, ey = b.x - c.x, b.y - c.y
                rr = c.r + R
                d2 = ex * ex + ey * ey
                if d2 >= rr * rr:
                    continue
                d = math.sqrt(d2)
                if d < 1e-9:
                    nx, ny = 0.0, -1.0
                else:
                    nx, ny = ex / d, ey / d
            else:
                px, py = b.x - c.x1, b.y - c.y1
                t = px * c.dx + py * c.dy
                if t < 0:
                    t = 0.0
                elif t > c.L:
                    t = c.L
                ex, ey = px - c.dx * t, py - c.dy * t
                rr = c.th + R
                d2 = ex * ex + ey * ey
                if d2 >= rr * rr:
                    continue
                side = px * c.nx + py * c.ny
                if c.oneway and side < 0:
                    continue
                d = math.sqrt(d2)
                if d < 1e-9:
                    nx, ny = (c.nx, c.ny) if side >= 0 else (-c.nx, -c.ny)
                else:
                    nx, ny = ex / d, ey / d
            pen = rr - d
            b.x += nx * pen
            b.y += ny * pen
            vn = b.vx * nx + b.vy * ny
            if vn < 0:
                if self.impact(b, c, nx, ny, vn):
                    return

    def impact(self, b, c, nx, ny, vn):
        """The ball hits something with normal speed -vn. Returns True when the ball left the field (ramp)."""
        k = c.kind
        e = c.e if vn < -2.0 else 0.0
        b.vx -= (1 + e) * vn * nx
        b.vy -= (1 + e) * vn * ny
        tx, ty = -ny, nx
        vt = b.vx * tx + b.vy * ty
        fr = 0.015
        b.vx -= vt * tx * fr
        b.vy -= vt * ty * fr
        if k == "wall" or k == "gate":
            if vn < -12:
                self.snd("wall", min(1.0, -vn / 60), 0.05)
            return False
        if k == "post":
            if vn < -6:
                self.snd("post", min(1.0, -vn / 50), 0.05)
                self.add(POINTS["post"])
            return False
        live = not self.tilted
        if k == "bumper":
            if live:
                out = b.vx * nx + b.vy * ny          # the ring snaps down: the ball leaves at a set speed
                b.vx += nx * (21.0 - out)
                b.vy += ny * (21.0 - out)
                self.flash[("bumper", c.id)] = self.clock
                self.add(POINTS["bumper"], 100)
                self.stats["bumpers"] += 1
                self.snd("bumper%d" % (c.id % 4), 0.8, 0.03)
                self.burst(c.x + nx * c.r, c.y + ny * c.r, 6, [self.th["cap"], WHITE, self.th["lamp"]], 9, 0.35)
                self.shot("bumper")
            return False
        if k == "sling":
            if live and vn < -1.5 and self.clock - self.flash.get(("sling", c.id), -9) > 0.12:
                kx, ky = (c.nx, c.ny) if (nx * c.nx + ny * c.ny) > 0 else (-c.nx, -c.ny)
                out = b.vx * kx + b.vy * ky
                if out < 14.0:                        # the kicker throws the ball off at a set speed
                    b.vx += kx * (14.0 - out)
                    b.vy += ky * (14.0 - out)
                self.flash[("sling", c.id)] = self.clock
                self.add(POINTS["sling"], 20)
                self.snd("sling", 0.8)
                self.burst(b.x - nx * R, b.y - ny * R, 4, [WHITE, self.th["rubber"]], 6, 0.25)
            return False
        if k == "drop":
            front = (nx * c.nx + ny * c.ny) > 0.3
            if front and vn < -3.5 and self.drops_up[c.id]:
                self.drop_down(c.id)
            return False
        if k == "ramp":
            side = (b.x - c.x1) * c.nx + (b.y - c.y1) * c.ny
            sp = math.hypot(b.vx, b.vy)
            if side > 0:
                if sp >= self.t.ramp["vmin"] * 0.55 and -vn >= self.t.ramp["vmin"] * 0.45:
                    self.ramp_enter(b, sp)
                    return True
                if -vn > 6:
                    self.snd("ramp_fail", 0.6)
            return False
        return False

    def collide_flipper(self, b, f):
        rx, ry = b.x - f.x, b.y - f.y
        if rx * rx + ry * ry > (f.L + f.r1 + R + 0.3) ** 2:
            return
        ca, sa = f.ca, f.sa
        t = rx * ca + ry * sa
        if t < 0:
            t = 0.0
        elif t > f.L:
            t = f.L
        qx, qy = ca * t, sa * t
        ex, ey = rx - qx, ry - qy
        rad = f.r1 + (f.r2 - f.r1) * t / f.L
        rr = rad + R
        d2 = ex * ex + ey * ey
        if d2 >= rr * rr:
            return
        d = math.sqrt(d2)
        if d < 1e-9:
            nx, ny = sa, -ca
        else:
            nx, ny = ex / d, ey / d
        pen = rr - d
        b.x += nx * pen
        b.y += ny * pen
        cx, cy = qx + nx * rad, qy + ny * rad
        svx, svy = -f.w * cy, f.w * cx
        rvx, rvy = b.vx - svx, b.vy - svy
        vn = rvx * nx + rvy * ny
        if vn < 0:
            moving = abs(f.w) > 0.5
            e = 0.45 if moving else (0.22 if vn < -3.0 else 0.0)
            rvx -= (1 + e) * vn * nx
            rvy -= (1 + e) * vn * ny
            tx, ty = -ny, nx
            vt = rvx * tx + rvy * ty
            rvx -= vt * tx * 0.02
            rvy -= vt * ty * 0.02
            b.vx, b.vy = rvx + svx, rvy + svy

    def collide_plunger(self, b):
        if b.x < PF_R:
            return
        top = self.plunger_y
        if b.y + R > top:
            b.y = top - R
            if b.vy > 0:
                b.vy = -b.vy * 0.2 if b.vy > 4 else 0.0

    def collide_balls(self, balls):
        n = len(balls)
        for i in range(n):
            a = balls[i]
            for j in range(i + 1, n):
                c = balls[j]
                dx, dy = c.x - a.x, c.y - a.y
                d2 = dx * dx + dy * dy
                if d2 >= 4 * R * R or d2 < 1e-12:
                    continue
                d = math.sqrt(d2)
                nx, ny = dx / d, dy / d
                pen = (2 * R - d) / 2
                a.x -= nx * pen
                a.y -= ny * pen
                c.x += nx * pen
                c.y += ny * pen
                vn = (c.vx - a.vx) * nx + (c.vy - a.vy) * ny
                if vn < 0:
                    j_ = -vn * 0.95
                    a.vx -= nx * j_
                    a.vy -= ny * j_
                    c.vx += nx * j_
                    c.vy += ny * j_

    def sense(self, b, ox, oy):
        for (x1, y1, x2, y2, name, dx, dy) in self.t.sensors:
            # quick reject: both points far from the line's bounding box
            if (ox < x1 - 0.6 and b.x < x1 - 0.6) or (ox > x2 + 0.6 and b.x > x2 + 0.6):
                continue
            ly = y2 - y1
            lx = x2 - x1
            s0 = (ox - x1) * ly - (oy - y1) * lx
            s1 = (b.x - x1) * ly - (b.y - y1) * lx
            if (s0 < 0) == (s1 < 0):
                continue
            mvx, mvy = b.x - ox, b.y - oy
            den = mvx * ly - mvy * lx
            if abs(den) < 1e-12:
                continue
            u = ((x1 - ox) * ly - (y1 - oy) * lx) / den      # where along the move
            px, py = ox + mvx * u, oy + mvy * u
            w = ((px - x1) * lx + (py - y1) * ly) / max(1e-9, lx * lx + ly * ly)
            if not 0.0 <= w <= 1.0:
                continue
            if (dx or dy) and mvx * dx + mvy * dy <= 0:
                continue
            self.switch(name, b)

    def scoop_check(self, b, sp):
        x, y, _, _ = self.t.scoop
        if (b.x - x) ** 2 + (b.y - y) ** 2 < 0.36 and sp < 46 and b.state == "play":
            b.state = "scoop"
            b.x, b.y, b.vx, b.vy = x, y, 0.0, 0.0
            b.hold = 1.1
            self.snd("scoop")
            self.scoop_enter(b)

    def ramp_enter(self, b, sp):
        b.state = "ride"
        b.ride = 0.0
        b.rv = clamp(sp * 0.7, 26.0, 44.0)
        self.snd("ramp_up", 0.7)

    def ride_step(self, b, h):
        rp = self.t.ramp
        path, dist = rp["path"], rp["dist"]
        b.rv = max(20.0, b.rv - 6.0 * h)
        b.ride += b.rv * h
        if b.ride >= dist[-1]:
            b.state = "play"
            b.x, b.y = path[-1]
            b.vx, b.vy = rp["exit"]
            b.still = 0.0
            self.ramp_made(b)
            return
        i = 1
        while dist[i] < b.ride:
            i += 1
        k = (b.ride - dist[i - 1]) / max(1e-9, dist[i] - dist[i - 1])
        (ax, ay), (bx, by) = path[i - 1], path[i]
        b.x, b.y = ax + (bx - ax) * k, ay + (by - ay) * k
        b.trail.append((b.x, b.y))
        if len(b.trail) > 5:
            del b.trail[0]

    # --- switches and rules ----------------------------------------------------------------------
    def log(self, name):
        self.events.append((self.clock, name))
        if len(self.events) > 60:
            del self.events[0]

    def switch(self, name, b):
        if name.startswith("lane") and name[4:].isdigit():
            i = int(name[4:])
            self.log(name)
            if b.skill and not self.tilted:
                b.skill = False
                if i == self.skill_lane:
                    self.add(POINTS["skill"], 5000)
                    self.stats["skill"] += 1
                    self.say("SKILL SHOT", "%d" % POINTS["skill"], 2.2, WHITE)
                    self.snd("skill")
            if not self.tilted:
                self.add(POINTS["lane"], 1000)
                self.lanes[i] = True
                self.flash["lane%d" % i] = self.clock
                self.snd("lane", 0.6)
                if all(self.lanes):
                    self.lanes = [False] * 3
                    self.bx = min(6, self.bx + 1)
                    self.say("BONUS %dX" % self.bx, "lanes complete", 1.6)
                    self.snd("lanes")
                    if not self.kick_lit:
                        self.kick_lit = True
                        self.say("KICKBACK LIT", "", 1.4)
            return
        if name in ("lorbit", "rorbit"):
            self.log(name)
            if b.skill:
                b.skill = False
            if not self.tilted:
                self.add(POINTS["orbit"], 3000)
                self.stats["orbits"] += 1
                self.orbits += 1
                self.snd("orbit", 0.8)
                self.flash[name] = self.clock
                if not self.mission and not self.mission_lit and self.orbits % 2 == 0 and self.wizard <= 0:
                    self.mission_lit = True
                    self.say("MISSION LIT", "shoot the %s" % self.th["scoop_name"].lower(), 1.6)
                self.shot(name)
            return
        if name == "spin":
            sp = math.hypot(b.vx, b.vy)
            self.spin_v += (1 if b.vy < 0 else -1) * (2.0 + sp * 0.55)
            self.log("spin")
            return
        if name == "kickback":
            if self.kick_lit and not self.tilted and b.state == "play":
                self.kick_lit = False
                b.x, b.y = self.t.kick
                b.vx, b.vy = -0.3, -66.0
                self.stats["kicks"] += 1
                self.add(POINTS["kick"])
                self.say("KICKBACK", "", 1.2)
                self.snd("kick")
                self.shake = 0.4
                self.shake_dir = (0.0, 1.0)
                self.burst(b.x, b.y + 0.6, 10, [WHITE, self.th["lamp2"]], 12, 0.4)
            return
        if name == "inlane":
            self.add(5000, 1000)
            return
        if name == "outlane":
            self.add(10000, 0)
            return

    def spinner_turn(self):
        if self.tilted:
            return
        self.add(POINTS["spin"] * (3 if self.mission and "spin" in self.mission_def(self.mission[0])[1] else 1), 50)
        self.stats["spins"] += 1
        self.snd("spin", 0.5, 0.02)
        self.shot("spin")

    def drop_down(self, i):
        self.drops_up[i] = False
        self.add(POINTS["drop"], 2000)
        self.snd("drop")
        d = self.t.drops[i]
        self.burst((d.x1 + d.x2) / 2, (d.y1 + d.y2) / 2, 6, [self.th["plastic"], WHITE], 6, 0.35)
        self.log("drop")
        self.shot("drop")
        if not any(self.drops_up):
            self.stats["banks"] += 1
            self.add(POINTS["bank"], 10000)
            self.snd("bank")
            self.drop_reset = 1.6
            if not self.kick_lit:
                self.kick_lit = True
            if self.lock_lit + self.locked < 2:
                self.lock_lit += 1
                self.say("LOCK IS LIT", self.th["drop_name"].lower() + " down", 1.8)
            else:
                self.say(self.th["drop_name"], "%d" % POINTS["bank"], 1.4)

    def reset_drops(self):
        for i, d in enumerate(self.t.drops):
            if self.drops_up[i]:
                continue
            for b in self.balls:
                if b.state == "play":
                    px, py = b.x - d.x1, b.y - d.y1
                    t = clamp(px * d.dx + py * d.dy, 0, d.L)
                    if math.hypot(px - d.dx * t, py - d.dy * t) < R + d.th + 0.05:
                        return False        # a ball sits where the target would rise: try again later
        self.drops_up = [True] * len(self.t.drops)
        self.snd("reset", 0.6)
        return True

    def shot(self, name):
        """A shot counts towards the running mission / wizard mode."""
        if self.tilted:
            return
        if name in ("lorbit", "rorbit", "ramp", "scoop"):
            if self.wizard > 0:
                self.add(POINTS["wizard"], 0)
                self.say(self.th["wizard"], "%d" % (POINTS["wizard"] * 2), 1.2, WHITE)
                self.snd("jackpot", 0.7)
        m = self.mission
        if not m:
            return
        names, need = self.mission_def(m[0])[1], self.mission_def(m[0])[2]
        if name not in names:
            return
        m[1] += 1
        if name not in ("spin", "bumper"):
            self.add(POINTS["mshot"], 5000)
            self.snd("mshot")
            self.say(self.mission_def(m[0])[0], "%d / %d" % (m[1], need), 1.2)
        if m[1] >= need:
            self.mission_complete()

    def mission_complete(self):
        i = self.mission[0]
        self.missions_done.add(i)
        self.mission = None
        self.stats["missions"] += 1
        self.add(POINTS["mdone"] * (1 + len(self.missions_done)), 25000)
        self.say("MISSION DONE", self.mission_def(i)[0], 2.4, WHITE)
        self.snd("mdone")
        if len(self.missions_done) >= len(self.th["missions"]):
            self.missions_done = set()
            self.wizard = 40.0
            self.stats["wizard"] += 1
            self.say(self.th["wizard"], "every shot is lit", 3.0, WHITE)
            self.snd("multi")

    def start_mission(self):
        todo = [i for i in range(len(self.th["missions"])) if i not in self.missions_done]
        i = todo[0]
        self.mission = [i, 0, 45.0]
        self.mission_lit = False
        self.say(self.mission_def(i)[0], "%d shots in 45 s" % self.mission_def(i)[2] if self.mission_def(i)[2] < 10
                 else "%d in 45 s" % self.mission_def(i)[2], 2.4)
        self.snd("mission")

    def scoop_enter(self, b):
        self.log("scoop")
        self.stats["scoops"] += 1
        if self.tilted:
            return
        self.add(POINTS["scoop"], 3000)
        self.shot("scoop")
        if self.super_t > 0:
            self.super_t = 0.0
            self.add(POINTS["super"], 0)
            self.say("SUPER JACKPOT", "%d" % POINTS["super"], 2.6, WHITE)
            self.snd("jackpot")
            self.stats["jackpots"] += 1
        if self.lock_lit and not self.multiball:
            self.lock_lit -= 1
            self.locked += 1
            self.stats["locks"] += 1
            self.add(POINTS["lock"], 5000)
            self.snd("lock")
            if self.locked >= 2:
                self.start_multiball(b)
            else:
                self.say("BALL %d LOCKED" % self.locked, self.th["scoop_name"].lower(), 2.0)
                b.state = "gone"
                self.serve(auto=False)
            return
        if self.mission_lit and not self.mission and self.wizard <= 0:
            self.start_mission()
            b.hold = 1.8

    def start_multiball(self, b):
        self.locked = 0
        self.multiball = True
        self.jackpot_lit = True
        self.stats["multiballs"] += 1
        self.say(self.th["multi"], "MULTIBALL", 3.0, WHITE)
        self.snd("multi")
        self.queue = 1             # the other locked ball comes out of the scoop, a third one up the lane
        self.queue_t = 1.6
        self.pending += 1
        b.hold = 1.2
        self.save_t = max(self.save_t, 14.0)
        self.save_armed = False

    def ramp_made(self, b):
        self.log("ramp")
        self.stats["ramps"] += 1
        if self.tilted:
            return
        self.add(POINTS["ramp"], 5000)
        self.ramps += 1
        self.snd("ramp")
        self.flash["ramp"] = self.clock
        if b.skill:
            b.skill = False
        if self.jackpot_lit and self.multiball:
            self.add(self.jackpot_value)
            self.say("JACKPOT", "%d" % self.jackpot_value, 2.4, WHITE)
            self.snd("jackpot")
            self.stats["jackpots"] += 1
            self.jackpot_value += 500000
            self.super_t = 15.0
        elif self.extra_lit:
            self.extra_lit = False
            self.extra += 1
            self.stats["extra"] += 1
            self.say("EXTRA BALL", "shoot again", 2.6, WHITE)
            self.snd("extra")
        elif self.ramps >= self.extra_at:
            self.extra_lit = True
            self.extra_at += 8
            self.say("EXTRA BALL LIT", "shoot the %s" % self.th["ramp_name"].lower(), 1.8)
        self.shot("ramp")

    def rules_step(self):
        for b in self.balls:
            if b.state == "lane" and b.y < 11.6 and b.vy < 0 and not b.launched:
                b.launched = True
                b.skill = True
                b.first = self.clock
                if self.save_armed:
                    self.save_t = SAVE_T
                    self.save_armed = False
            if b.state in ("lane",) and b.x < PF_R - 0.2 and b.y < 13:
                b.state = "play"
            if b.state == "lane" and b.launched and b.y < 11.0:
                b.state = "play"
            if b.state == "play" and b.skill and b.first is not None and self.clock - b.first > 4.0:
                b.skill = False
            if b.state == "scoop":
                b.hold -= DT
                if b.hold <= 0:
                    self.eject(b)
        if self.pending and not any(b.state == "lane" for b in self.balls):
            self.pending -= 1
            self.serve(auto=True)
        if self.queue and not any(b.state == "scoop" for b in self.balls):
            self.queue_t -= DT
            if self.queue_t <= 0:
                self.queue -= 1
                self.queue_t = 1.0
                x, y, _, _ = self.t.scoop
                nb = Ball(x, y, state="scoop")
                nb.hold = 0.25
                self.balls.append(nb)
        if self.drop_reset > 0:
            self.drop_reset -= DT
            if self.drop_reset <= 0 and not self.reset_drops():
                self.drop_reset = 0.3
        if self.save_t > 0:
            self.save_t -= DT
        if self.super_t > 0:
            self.super_t -= DT
        if self.wizard > 0:
            self.wizard -= DT
            if self.wizard <= 0:
                self.say("WIZARD OVER", "", 1.5)
                self.mission_lit = True
        if self.mission:
            self.mission[2] -= DT
            if self.mission[2] <= 0:
                self.say("TIME UP", self.mission_def(self.mission[0])[0], 1.8, (255, 120, 100))
                self.snd("mfail")
                self.mission = None
        if self.multiball and len([b for b in self.balls if b.state in ("play", "ride", "scoop", "lane")]) + \
                self.queue + self.pending <= 1:
            self.multiball = False
            self.jackpot_lit = False
            self.super_t = 0.0
            self.say("MULTIBALL OVER", "", 1.4)
        self.balls = [b for b in self.balls if b.state != "gone"]

    def eject(self, b):
        x, y, vx, vy = self.t.scoop
        b.state = "play"
        b.x, b.y = x + vx * 0.06, y + vy * 0.06
        b.vx = vx * self.rnd.uniform(0.94, 1.06) + self.rnd.uniform(-0.6, 0.6)
        b.vy = vy * self.rnd.uniform(0.94, 1.06)
        b.still = 0.0
        self.snd("eject")
        self.flash["scoop"] = self.clock
        self.burst(x, y, 8, [self.th["lamp"], WHITE], 8, 0.4)

    def drain(self, b):
        b.state = "gone"
        self.balls = [c for c in self.balls if c is not b]
        if self.sandbox:
            return
        left = [c for c in self.balls if c.state in ("play", "ride", "scoop", "lane")]
        if self.save_t > 0 and not self.tilted:
            self.stats["saves"] += 1
            self.say("BALL SAVED", "", 1.8, WHITE)
            self.snd("save")
            self.pending += 1
            return
        if left or self.queue or self.pending:
            return
        self.snd("drain")
        self.end_ball()

    def end_ball(self):
        self.state, self.state_t = "bonus", 0.0
        self.mission = None
        self.multiball = self.jackpot_lit = False
        self.wizard = 0.0
        self.super_t = 0.0
        b = 0 if self.tilted else self.bonus
        self.bonus_show = [b, self.bx, 0]

    def bonus_step(self):
        b, x, shown = self.bonus_show
        if self.state_t > 0.6 and shown == 0:
            self.bonus_show[2] = 1
            self.snd("bonus")
        if self.state_t > 2.6:
            if not self.tilted:
                self.score += b * x
            self.bonus = 0
            self.bx = 1
            self.tilted = False
            self.tilt = 0.0
            self.warnings = 0
            self.lanes = [False] * 3
            if self.extra > 0:
                self.extra -= 1
                self.say("SHOOT AGAIN", "same player", 2.0, WHITE)
            else:
                self.ball_no += 1
            if self.ball_no > self.balls_total:
                self.state, self.over = "over", True
                self.snd("over")
                return
            self.state, self.state_t = "play", 0.0
            self.save_armed = True
            self.kick_lit = self.kick_lit or self.ball_no == 1
            self.mission_lit = not self.mission
            self.skill_lane = self.rnd.randrange(3)
            self.serve()


# =============================================================================================
# The autopilot: it sees what a player sees (the balls, the flippers, the lit lamps) and learned the
# table like a player does, by practice: which shot a cradled ball makes when it is let roll and flipped
# at each point of the bat, and which top lane each plunger pull reaches.
# =============================================================================================
AIM_TS = tuple(round(0.30 + 0.025 * i, 3) for i in range(28))
PULLS = tuple(round(0.40 + 0.02 * i, 2) for i in range(30))
# What practice() found (python3 clatterbell.py --practice prints it again; the self-test checks it still holds):
# per table and flipper, the shots a cradled ball makes when flipped at each point t of the bat; per pull, the lane.
CAL = {'belfry': {'L': {'drop': [0.325, 0.35, 0.375, 0.4, 0.475],
                         'scoop': [0.3, 0.625, 0.65, 0.675, 0.85],
                         'spin': [0.925]},
                   'R': {'drop': [0.325, 0.35, 0.375, 0.475],
                         'lorbit': [0.55, 0.8, 0.825, 0.85, 0.925, 0.975],
                         'ramp': [0.525, 0.7, 0.725, 0.95],
                         'scoop': [0.3]},
                   'plunge': {'lane0': [0.7, 0.76], 'lane1': [0.72], 'lane2': [0.66, 0.68]}},
        'forge': {'L': {'drop': [0.3, 0.45, 0.5, 0.525, 0.95, 0.975], 'scoop': [0.375], 'spin': [0.425]},
                  'R': {'ramp': [0.675, 0.875], 'scoop': [0.375, 0.4, 0.425, 0.45, 0.775], 'spin': [0.925]},
                  'plunge': {'lane0': [0.7, 0.76], 'lane1': [0.72], 'lane2': [0.66, 0.68]}},
        'reef': {'L': {'drop': [0.3, 0.375, 0.4, 0.425, 0.45, 0.475, 0.5, 0.525],
                       'ramp': [0.7, 0.725],
                       'rorbit': [0.925],
                       'scoop': [0.325]},
                 'R': {'scoop': [0.3, 0.6, 0.625, 0.65, 0.675, 0.725, 0.85, 0.875], 'spin': [0.35, 0.75, 0.775, 0.925]},
                 'plunge': {'lane0': [0.7, 0.76], 'lane1': [0.72], 'lane2': [0.66, 0.68]}}}


def _up_normal(f):
    n1 = (f.sa, -f.ca)
    return n1 if n1[1] < 0 else (-f.sa, f.ca)


def cradle_game(key, side, seed=0):
    """A practice table with one ball resting in the cradle of a raised flipper."""
    g = Game(key, seed=seed, sandbox=True)
    g.balls = []
    f = next(f for f in g.flippers if f.d.side == side and not f.d.upper)
    f.ang = f.d.up
    f.set()
    nx, ny = _up_normal(f)
    k = 0.55
    rad = f.r1 + (f.r2 - f.r1) * k
    b = Ball(f.x + f.ca * f.L * k + nx * (rad + R + 0.05), f.y + f.sa * f.L * k + ny * (rad + R + 0.05))
    g.balls.append(b)
    inp = (side == "L", side == "R", False, None)
    for _ in range(int(1.2 / DT)):
        g.step(inp)
    return g, f, b


def practice_shot(key, side, t_aim, seed=0):
    g, f, b = cradle_game(key, side, seed)
    held = (side == "L", side == "R", False, None)
    free = (False, False, False, None)
    t = 0.0
    while t < 0.8:                       # let it roll down the falling bat
        g.step(free)
        t += DT
        if not g.balls or b.state != "play":
            return "drain"
        if f.local(b.x, b.y)[0] >= t_aim:
            break
    start = g.clock
    for i in range(int(2.6 / DT)):
        g.step(held if i < int(0.3 / DT) else free)
        for tt, name in g.events:
            if tt >= start:
                return name
        if not g.balls:
            return "drain"
    return "none"


def practice_plunge(key, pull, seed=0):
    g = Game(key, seed=seed, sandbox=True)
    for _ in range(int(0.3 / DT)):
        g.step((False, False, False, None))
    g.fire(pull)
    for _ in range(int(3.0 / DT)):
        g.step((False, False, False, None))
        for tt, name in g.events:
            return name
    return "none"


def practice(key):
    """All the practice for one table (a few seconds of simulated play): {side: {shot: [t...]}, 'plunge': {...}}."""
    out = {}
    for side in ("L", "R"):
        shots = {}
        for t in AIM_TS:
            s = practice_shot(key, side, t)
            if s in SHOTS:
                shots.setdefault(s, []).append(t)
        out[side] = shots
    pl = {}
    for p in PULLS:
        s = practice_plunge(key, p)
        if s.startswith("lane") and s[4:].isdigit():
            pl.setdefault(s, []).append(p)
    out["plunge"] = pl
    return out


def best_of(ts):
    """The middle of the longest run of neighbouring practice points (the steadiest aim for a shot)."""
    runs, cur = [], [ts[0]]
    for a in ts[1:]:
        if a - cur[-1] < 0.03:
            cur.append(a)
        else:
            runs.append(cur)
            cur = [a]
    runs.append(cur)
    best = max(runs, key=len)
    return (best[0] + best[-1]) / 2


class Bot:
    """Plays like a careful player: flips when a ball comes into reach of a flipper; catches slow balls in a
    cradle, picks a lit shot (missions, lock, jackpot, extra ball), lets the ball roll and flips at the point it
    practised for that shot; plunges for the lit skill-shot lane; nudges now and then, never twice in a row."""

    def __init__(self, g, seed=None):
        self.g = g
        self.rnd = random.Random(seed)
        self.reset()

    def reset(self):
        self.hold = {"L": 0.0, "R": 0.0}
        self.cradle = None
        self.pull_to = None
        self.nudge_cd = 2.0
        self.skip = {}

    @property
    def cal(self):
        c = CAL.get(self.g.key)
        if c is None:
            c = CAL[self.g.key] = practice(self.g.key)
        return c

    def reach(self, f, b, look=0.07, when=False):
        """Will the ball come within reach of this flipper in the next moment? -> t along the bat or None
        (with when=True: (t, seconds until then))."""
        nx, ny = _up_normal(f)
        n = max(8, int(look / 0.01))
        for k in range(n):
            tau = look * k / (n - 1)
            x = b.x + b.vx * tau
            y = b.y + b.vy * tau + 0.5 * G * tau * tau
            t, d, side = f.local(x, y)
            above = (x - f.x) * nx + (y - f.y) * ny > -0.2
            rad = f.r1 + (f.r2 - f.r1) * t
            if above and d < rad + R + 0.3 and t > 0.12:
                return (t, tau) if when else t
        return None

    def choose(self, side):
        g, cal = self.g, self.cal.get(side, {})
        if not cal:
            return None, None
        lit = g.lit_shots()
        pri = {"jackpot": 0, "super": 0, "wizard": 1, "mission": 1, "lock": 2, "extra": 3}
        cands = sorted(((pri.get(why, 5), s) for s, why in lit.items() if s in cal), key=lambda p: p[0])
        if cands and self.rnd.random() < 0.85:
            best = [s for p, s in cands if p == cands[0][0]]
            shot = self.rnd.choice(best)
        else:
            shot = self.rnd.choice(sorted(cal))
        return shot, best_of(cal[shot]) + self.rnd.uniform(-0.01, 0.01)

    def __call__(self):
        g = self.g
        out = {"L": False, "R": False}
        P = False
        N = None
        self.nudge_cd -= DT
        live = [b for b in g.balls if b.state == "play"]
        # the plunger
        lane = [b for b in g.balls if b.state == "lane" and abs(b.vy) < 3.0 and b.y > PL_Y - 1.0]
        if lane and g.autoplunge <= 0:
            if self.pull_to is None:
                opts = self.cal.get("plunge", {}).get("lane%d" % g.skill_lane)
                self.pull_to = (best_of(opts) if opts and self.rnd.random() < 0.8 else self.rnd.uniform(0.75, 1.0))
            P = g.pull < self.pull_to
            if not P:
                self.pull_to = None
        else:
            self.pull_to = None
        # a cradled ball: let it roll, flip at the practised point
        cr = self.cradle
        if cr and (cr["ball"] not in live or len(live) > 1 and cr["phase"] == "catch"):
            cr = self.cradle = None
        if cr:
            b, f = cr["ball"], cr["f"]
            cr["t"] += DT
            sp = math.hypot(b.vx, b.vy)
            if cr["phase"] == "catch":
                out[f.d.side] = True
                tt, dd, _ = f.local(b.x, b.y)
                cr["away"] = cr.get("away", 0.0) + DT if dd > f.r1 + R + 2.5 else 0.0
                if cr["away"] > 0.3:
                    self.cradle = cr = None
                    out[f.d.side] = False
            if cr is None:
                pass
            elif cr["phase"] == "catch":
                cr["still"] = cr["still"] + DT if sp < 1.0 and f.raised else 0.0
                if cr["still"] > 0.35 + self.rnd.random() * 0.02:
                    shot, t = self.choose(f.d.side)
                    if shot is None:
                        self.cradle = None
                    else:
                        cr.update(phase="roll", shot=shot, aim=t, t=0.0)
                elif cr["t"] > 2.0:
                    self.cradle = None
            elif cr["phase"] == "roll":
                if f.local(b.x, b.y)[0] >= cr["aim"] or cr["t"] > 0.8:
                    cr.update(phase="shoot", t=0.0)
                    out[f.d.side] = True
            else:
                out[f.d.side] = True
                if cr["t"] > 0.3:
                    self.cradle = None
                    self.skip[id(b)] = g.clock + 0.4
        # everything else: flip at balls coming into reach; start a catch for slow singles
        for b in live:
            if self.cradle and self.cradle["ball"] is b and self.cradle["phase"] != "catch":
                continue
            if self.cradle is None and len(live) == 1 and b.vy > -2 and math.hypot(b.vx, b.vy) < 24 and \
                    self.skip.get(id(b), 0) < g.clock:
                for f in g.flippers:
                    if f.d.upper or not self.cal.get(f.d.side):
                        continue
                    w = self.reach(f, b, look=0.4, when=True)
                    if w and w[1] > 0.09 and self.rnd.random() < 0.9:
                        self.cradle = dict(ball=b, f=f, phase="catch", t=0.0, still=0.0)
                        out[f.d.side] = True
                        break
                    if w:
                        self.skip[id(b)] = g.clock + 0.5
                        break
            for f in g.flippers:
                side = f.d.side
                if self.cradle and self.cradle["ball"] is b and self.cradle["f"] is f:
                    continue
                t = self.reach(f, b)
                if t is None:
                    continue
                sp = math.hypot(b.vx, b.vy)
                if (t > 0.2 or sp > 10) and (sp > 4 or not f.raised):
                    self.hold[side] = max(self.hold[side], 0.2)
                    if self.cradle and self.cradle["ball"] is b:
                        self.cradle = None
        for side in ("L", "R"):
            if self.hold[side] > 0:
                self.hold[side] -= DT
                out[side] = True
        # a nudge when a ball heads for an outlane (rarely, and never close to a tilt)
        if self.nudge_cd <= 0 and not g.tilted:
            for b in live:
                if (b.x < 1.7 or b.x > PF_R - 1.7) and 21.5 < b.y < 26 and b.vy > 2:
                    if self.rnd.random() < 0.35:
                        N = "up"
                    self.nudge_cd = 5.0
                    break
        return out["L"], out["R"], P, N


# =============================================================================================
# Rendering: the table is seen from where the player stands, so its length is foreshortened (the picture is
# wider than the plan). Everything is drawn at screen resolution from the table's units: a bigger window
# gets a finer table (the same table, more detail).
# =============================================================================================
def hsh(x, y, s=0):
    h = (x * 374761393 + y * 668265263 + s * 2147483647) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    return (h ^ (h >> 16)) & 0xFFFF


PANEL_BG = (14, 11, 20)
TEXT = (226, 224, 236)
DIM = (140, 136, 166)
GOLD = (250, 214, 120)
DMD_ON = (255, 148, 44)
DMD_OFF = (44, 22, 10)
DMD_BG = (14, 8, 6)
TILT_VIEW = 1.65           # how much wider than the plan the tilted table looks (at most)
PANEL_MIN = 17             # columns kept for each side panel before the table may widen


def layout(cols, rows):
    """(sx, sy, ox, oy, rail): pixels per unit across and along the table, its top-left pixel, the rail width."""
    H = rows * 2
    sy = max(0.2, (H - 2) / TH)
    rail = max(1, int(round(sy * 0.6)))
    k = clamp((cols - 2 * PANEL_MIN - 2 * rail) / (TW * sy), 1.0, TILT_VIEW)
    if cols < 2 * PANEL_MIN + 10:
        k = clamp((cols - 2) / (TW * sy), 0.6, TILT_VIEW)
    sx = sy * k
    ox = int((cols - TW * sx) / 2)
    return sx, sy, ox, 1, rail


class View:
    def __init__(self, cv, sx, sy, ox, oy):
        self.cv, self.sx, self.sy, self.ox, self.oy = cv, sx, sy, ox, oy
        self.s = (sx + sy) / 2

    def X(self, x):
        return self.ox + x * self.sx

    def Y(self, y):
        return self.oy + y * self.sy

    def P(self, x, y):
        return self.ox + x * self.sx, self.oy + y * self.sy


def blend(cv, x, y, c, a):
    if 0 <= x < cv.W and 0 <= y < cv.H:
        row = cv.px[y]
        row[x] = mix(row[x], c, a)


def glow(cv, cx, cy, r0, r1, c, k=0.55, sq=1.0):
    """A soft halo from radius r0 out to r1 (screen pixels); sq < 1 squashes it vertically."""
    W, H = cv.W, cv.H
    y0, y1 = max(0, int(cy - r1 * sq)), min(H - 1, int(cy + r1 * sq))
    x0, x1 = max(0, int(cx - r1)), min(W - 1, int(cx + r1))
    span = max(0.01, r1 - r0)
    for py in range(y0, y1 + 1):
        row = cv.px[py]
        dy = (py + 0.5 - cy) / sq
        for px in range(x0, x1 + 1):
            d = math.sqrt((px + 0.5 - cx) ** 2 + dy * dy)
            if r0 < d < r1:
                a = (1 - (d - r0) / span)
                row[px] = mix(row[px], c, a * a * k)


def capsule(cv, x1, y1, x2, y2, r, col, hi=None, lo=None):
    """A thick line with round ends in screen pixels, shaded across its width (lit from the top left)."""
    W, H = cv.W, cv.H
    if r < 0.75:
        cv.line(x1, y1, x2, y2, col)
        return
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    hi = hi or mix(col, WHITE, 0.45)
    lo = lo or shade(col, 0.55)
    nx, ny = (-dy, dx) if L2 > 0 else (0.0, 1.0)
    nl = math.hypot(nx, ny) or 1.0
    nx, ny = nx / nl, ny / nl
    if nx + ny > 0:
        nx, ny = -nx, -ny                  # the normal that points to the light (top left)
    for py in range(max(0, int(min(y1, y2) - r - 1)), min(H, int(max(y1, y2) + r + 2))):
        row = cv.px[py]
        cy = py + 0.5
        for px in range(max(0, int(min(x1, x2) - r - 1)), min(W, int(max(x1, x2) + r + 2))):
            cx = px + 0.5
            if L2 > 0:
                t = ((cx - x1) * dx + (cy - y1) * dy) / L2
                t = 0.0 if t < 0 else 1.0 if t > 1 else t
            else:
                t = 0.0
            ex, ey = cx - (x1 + dx * t), cy - (y1 + dy * t)
            d = math.sqrt(ex * ex + ey * ey)
            if d > r + 0.5:
                continue
            side = (ex * nx + ey * ny) / max(0.01, r)
            c = mix(col, hi, side) if side > 0 else mix(col, lo, -side * 0.8)
            row[px] = c if d <= r - 0.5 else mix(row[px], c, r + 0.5 - d)


def ellipse(cv, cx, cy, rx, ry, c):
    if rx < 0.6 and ry < 0.6:
        cv.set(int(cx), int(cy), c)
        return
    rx, ry = max(rx, 0.5), max(ry, 0.5)
    for py in range(max(0, int(math.floor(cy - ry))), min(cv.H, int(math.ceil(cy + ry)) + 1)):
        dy = (py + 0.5 - cy) / ry
        if abs(dy) > 1:
            continue
        w = rx * math.sqrt(1 - dy * dy)
        a, b = max(0, int(math.floor(cx - w + 0.5))), min(cv.W, int(math.floor(cx + w + 0.5)))
        if b > a:
            cv.px[py][a:b] = [c] * (b - a)


def sphere(cv, cx, cy, rx, base, light=0.5, spec=0.9, ry=None):
    """A lit dome or ball (bumper caps, post tops, the ball itself), light from the top left."""
    ry = rx if ry is None else ry
    if rx < 0.9:
        cv.set(int(cx), int(cy), mix(base, WHITE, 0.3))
        return
    dark = mix(base, (8, 6, 14), 0.7)
    lite = mix(base, (255, 252, 240), light)
    for py in range(max(0, int(cy - ry - 1)), min(cv.H, int(cy + ry + 2))):
        v = (py + 0.5 - cy) / ry
        row = cv.px[py]
        for px in range(max(0, int(cx - rx - 1)), min(cv.W, int(cx + rx + 2))):
            u = (px + 0.5 - cx) / rx
            d2 = u * u + v * v
            if d2 > 1.0 + 1.0 / rx:
                continue
            nz = math.sqrt(max(0.0, 1 - d2))
            l = -0.45 * u - 0.55 * v + 0.7 * nz
            if l < 0.15:
                c = mix(dark, base, max(0.0, (l + 0.6) / 0.75))
            elif l < 0.82:
                c = mix(base, lite, (l - 0.15) / 0.67)
            else:
                c = mix(lite, WHITE, min(1.0, (l - 0.82) / 0.18 * spec))
            if d2 > 1.0:
                c = mix(row[px], c, max(0.0, 1 - (math.sqrt(d2) - 1) * rx))
            row[px] = c


def upoly(cv, v, pts, c):
    """A filled polygon given in table units."""
    cv.poly([v.P(x, y) for x, y in pts], c)

# --- the 3x5 dot-matrix font for the score display -------------------------------------------
DMD_FONT = {
    "0": "111101101101111", "1": "010110010010111", "2": "111001111100111", "3": "111001111001111",
    "4": "101101111001001", "5": "111100111001111", "6": "111100111101111", "7": "111001010010010",
    "8": "111101111101111", "9": "111101111001111", "A": "010101111101101", "B": "110101110101110",
    "C": "011100100100011", "D": "110101101101110", "E": "111100110100111", "F": "111100110100100",
    "G": "011100101101011", "H": "101101111101101", "I": "111010010010111", "J": "001001001101010",
    "K": "101101110101101", "L": "100100100100111", "M": "101111111101101", "N": "110101101101101",
    "O": "010101101101010", "P": "110101110100100", "Q": "010101101110011", "R": "110101110101101",
    "S": "011100010001110", "T": "111010010010010", "U": "101101101101111", "V": "101101101101010",
    "W": "101101111111101", "X": "101101010101101", "Y": "101101010010010", "Z": "111001010100111",
    " ": "000000000000000", "-": "000000111000000", "!": "010010010000010", ".": "000000000000010",
    ",": "000000000010100", "/": "001001010100100", ":": "000010000010000", "'": "010010000000000",
    "+": "000010111010000", "?": "110001010000010", "%": "101001010100101",
}


def dmd_width(text, k):
    return len(text) * 4 * k - k


def dmd_text(cv, x, y, text, k, on, off=None):
    """Text in the dot font: each font dot is a k x k cell (with a dark gap from k >= 3)."""
    for i, ch in enumerate(text.upper()):
        g = DMD_FONT.get(ch, DMD_FONT["?"])
        for j in range(15):
            gx, gy = j % 3, j // 3
            c = on if g[j] == "1" else off
            if c is None:
                continue
            bx, by = x + (i * 4 + gx) * k, y + gy * k
            if k >= 3:
                cv.rect(bx, by, k - 1, k - 1, c)
            else:
                cv.rect(bx, by, k, k, c)


def fmt(n):
    return "{:,}".format(n)


# --- the table background (cached per table and window size) --------------------------------
_BG = {}
_RAMP = {}



# --- the table background (cached per table and window size) --------------------------------
_BG = {}
_RAMP = {}


def field_color(th, u, v, x, y, s):
    """The painted playfield at unit position (u, v) (x, y: the screen pixel, for sparkle)."""
    top, bot = th["field"]
    c = mix(top, bot, clamp(v / TH, 0, 1))
    p = th["pattern"]
    lw = 0.06 + 0.5 / max(1.0, s)
    q = clamp((s - 0.8) / 2.2, 0.3, 1.0)        # small windows: a quieter pattern
    if p == "stars":
        # a pale moon behind the bumpers, rings of the bell's sound, stars, a bell painted low in the middle
        dm = math.hypot(u - 9.3, v - 11.5)
        if dm < 6.2:
            c = mix(c, (64, 62, 118), 0.55 * (1 - dm / 6.2) ** 0.5)
        if abs(dm - 8.2) < lw or abs(dm - 10.6) < lw * 0.8:
            c = mix(c, (96, 92, 170), 0.32 * q)
        hv = hsh(x, y, 3)
        if hv % 151 == 0:
            c = mix(c, (230, 230, 255), 0.7)
        elif hv % 37 == 0:
            c = mix(c, (150, 150, 210), 0.25)
        if 20.6 < v < 25.0:
            bw = 1.0 + (v - 20.6) * 0.32 + (0.6 if v > 24.2 else 0.0)
            if abs(u - 9.25) < bw:
                c = mix(c, (120, 86, 52), 0.38 if abs(u - 9.25) < bw - lw * 2 else 0.6)
    elif p == "caustic":
        w = math.sin(u * 1.3 + math.sin(v * 0.9) * 1.8) + math.sin(v * 1.1 - u * 0.5 + math.sin(u * 0.7))
        if w > 1.3:
            c = mix(c, (60, 170, 170), min(0.45, (w - 1.3) * 0.6) * q)
        if v > 30:
            c = mix(c, (150, 130, 90), min(0.55, (v - 30) / 10))
            if hsh(x, y, 5) % 13 == 0:
                c = mix(c, (200, 180, 130), 0.3)
        if hsh(x, y, 4) % 211 == 0:
            c = mix(c, (190, 255, 250), 0.5)
        # a big shell painted in the middle
        dm = math.hypot((u - 9.25) / 3.2, (v - 23.6) / 2.4)
        if dm < 1 and v < 25.2:
            ang = math.atan2(v - 25.2, u - 9.25)
            c = mix(c, (220, 120, 150), (0.14 + (0.14 if math.cos(ang * 14) > 0.6 else 0)) * q)
    elif p == "cracks":
        n = math.sin(u * 2.1 + math.sin(v * 1.7) * 2.2) * math.cos(v * 1.3 + math.sin(u * 1.1) * 1.9)
        if abs(n) < 0.07:
            c = mix(c, (255, 110, 40), 0.55 * (1 - abs(n) / 0.07) * q)
        elif abs(n) < 0.16:
            c = mix(c, (150, 40, 20), 0.35 * q)
        dm = math.hypot(u - 9.3, v - 10)
        if dm < 7:
            c = mix(c, (90, 40, 30), 0.4 * (1 - dm / 7))
        if hsh(x, y, 6) % 173 == 0:
            c = mix(c, (255, 210, 150), 0.6)
        # an anvil painted low in the middle
        if 22.4 < v < 25.2 and abs(u - 9.25) < (2.6 if v < 23.2 else 0.9 if v < 24.4 else 1.8):
            c = mix(c, (70, 70, 84), 0.55)
    return c


def lamp_pts(lp, grow=1.0):
    x, y, shape, size, _, ang = lp
    r = size * grow
    if shape == "diamond":
        return [(x, y - r), (x + r * 0.75, y), (x, y + r), (x - r * 0.75, y)]
    if shape == "arrow":
        a = math.radians(ang)
        ca, sa = math.cos(a), math.sin(a)
        px_, py_ = -sa, ca
        L = r * 1.35
        return [(x + ca * L, y + sa * L), (x - ca * L * 0.6 + px_ * r * 0.95, y - sa * L * 0.6 + py_ * r * 0.95),
                (x - ca * L * 0.6 - px_ * r * 0.95, y - sa * L * 0.6 - py_ * r * 0.95)]
    return None


def lamp_shape(cv, v, lp, col, lit, rim=None):
    """An insert in the playfield: a disc, a diamond or an arrow, drawn in table units."""
    x, y, shape, size, _, ang = lp
    cx, cy = v.P(x, y)
    rx, ry = size * v.sx, size * v.sy
    if rx < 1.3 or ry < 1.0:
        blend(cv, int(cx), int(cy), col, 0.95 if lit else 0.7)
        if shape == "arrow" and rx >= 0.9:
            a = math.radians(ang)
            blend(cv, int(cx + math.cos(a) * 1.2), int(cy + math.sin(a) * 1.2), col, 0.7 if lit else 0.45)
        return
    if shape == "disc":
        if rim:
            ellipse(cv, cx, cy, rx + 0.8, ry + 0.8, rim)
        ellipse(cv, cx, cy, rx, ry, col)
        if lit and rx >= 2:
            ellipse(cv, cx - rx * 0.25, cy - ry * 0.25, rx * 0.4, ry * 0.4, mix(col, WHITE, 0.6))
        return
    if rim:
        upoly(cv, v, lamp_pts(lp, 1.3), rim)
    upoly(cv, v, lamp_pts(lp), col)
    if lit:
        hx, hy = x, y
        pts = [(hx + (px - hx) * 0.45, hy + (py - hy) * 0.45) for px, py in lamp_pts(lp)]
        upoly(cv, v, pts, mix(col, WHITE, 0.5))


def wall_style(th, look, s):
    """(colour, radius in pixels) of a wall kind."""
    if look == "rail":
        return th["metal"], 0.2 * s
    if look == "guide":
        return mix(th["metal"], th["plastic"], 0.25), 0.15 * s
    if look == "plastic":
        return th["plastic2"], 0.14 * s
    if look == "rubber":
        return th["rubber"], 0.18 * s
    if look == "pin":
        return th["plastic"], 0.22 * s
    if look == "gate":
        return mix(th["metal"], WHITE, 0.3), 0.07 * s
    return th["metal"], 0.14 * s


def backdrop(key, cols, rows):
    k = (key, cols, rows)
    c = _BG.get(k)
    if c is not None:
        return c
    if len(_BG) > 8:
        _BG.clear()
    t = table(key)
    th = t.th
    sx, sy, ox, oy, rail = layout(cols, rows)
    cv = Canvas(cols, rows, PANEL_BG)
    v = View(cv, sx, sy, ox, oy)
    s = v.s
    W, H = cv.W, cv.H
    w0, w1 = th["wood"]
    tx1 = int(math.ceil(ox + TW * sx))
    # the cabinet around: dark wood with a soft grain
    for y in range(H):
        row = cv.px[y]
        for x in range(W):
            if ox - rail <= x < tx1 + rail:
                continue
            g = 0.5 + 0.5 * math.sin(x * 0.9 + math.sin(y * 0.13 + x * 0.05) * 2.5)
            row[x] = mix(mix(PANEL_BG, w1, 0.55), mix(w1, w0, 0.4), g * 0.25)
    # the playfield, the shooter lane and the corners behind the arch
    for py in range(max(0, oy), min(H, int(oy + TH * sy) + 1)):
        row = cv.px[py]
        vv = (py + 0.5 - oy) / sy
        for px in range(max(0, ox), min(W, tx1)):
            u = (px + 0.5 - ox) / sx
            if vv < 10 and math.hypot(u - 10, vv - 10) > 10:
                row[px] = mix(w1, w0, 0.3 + 0.3 * (hsh(px, py, 1) % 7) / 7)
            elif u > PF_R:
                row[px] = mix((24, 20, 26), w1, 0.4)
            else:
                row[px] = field_color(th, u, vv, px, py, s)
    # the cabinet rails left and right
    for k_ in range(rail):
        a = k_ / max(1, rail - 1) if rail > 1 else 0.5
        cv.rect(ox - rail + k_, 0, 1, H, mix(w0, (255, 230, 200), 0.25 * (1 - a)))
        cv.rect(tx1 + k_, 0, 1, H, mix(w0, (0, 0, 0), 0.3 + 0.3 * a))
    # inserts, dark until lit
    for name, lp in t.lamps.items():
        if lp[2] == "none":
            continue
        col = th[lp[4]]
        lamp_shape(cv, v, lp, mix(shade(col, 0.3), field_color(th, lp[0], lp[1], 0, 0, s), 0.4), False,
                   rim=shade(col, 0.16) if s >= 2.5 else None)
    # the slingshot plastics
    for pts, ck in t.plastics:
        upoly(cv, v, pts, shade(th[ck], 0.7))
        if s >= 2.2:
            cx = sum(p[0] for p in pts) / 3
            cy = sum(p[1] for p in pts) / 3
            upoly(cv, v, [(cx + (p[0] - cx) * 0.62, cy + (p[1] - cy) * 0.62) for p in pts], th[ck])
            upoly(cv, v, [(cx + (p[0] - cx) * 0.3, cy + (p[1] - cy) * 0.3 - 0.2) for p in pts], mix(th[ck], WHITE, 0.35))
    # the scoop: a dark hole in a metal ring
    if t.scoop:
        x, y = t.scoop[:2]
        cx, cy = v.P(x, y)
        ring = max(0.7, s * 0.16)
        ellipse(cv, cx, cy, 0.66 * sx + ring, 0.66 * sy + ring, th["metal"])
        ellipse(cv, cx, cy, 0.66 * sx, 0.66 * sy, (6, 4, 8))
        if s > 3:
            ellipse(cv, cx + 0.12 * sx, cy + 0.15 * sy, 0.4 * sx, 0.36 * sy, (20, 14, 22))
    # drop target slots
    for d in t.drops:
        capsule(cv, v.X(d.x1), v.Y(d.y1), v.X(d.x2), v.Y(d.y2), max(0.6, 0.15 * s), (8, 6, 10))
    # the spinner's posts
    if t.spinner:
        x1, y1, x2, y2 = t.spinner
        for xx in (x1, x2):
            ellipse(cv, v.X(xx), v.Y(y1), max(0.6, 0.15 * sx), max(0.6, 0.15 * sy), th["metal"])
    # the ramp's entrance: a lighter flap
    sg = t.ramp["seg"]
    upoly(cv, v, [(sg.x1, sg.y1), (sg.x2, sg.y2), (sg.x2, sg.y2 - 1.4), (sg.x1, sg.y1 - 1.4)],
          mix(th["ramp"], (20, 20, 30), 0.5))
    capsule(cv, v.X(sg.x1), v.Y(sg.y1), v.X(sg.x2), v.Y(sg.y2), max(0.6, 0.12 * s), mix(th["ramp"], WHITE, 0.3))
    # walls, guides, posts
    small = s < 2.2
    for c in t.colliders:
        if c.kind in ("bumper", "drop", "ramp"):
            continue
        if c.circle:
            cx, cy = v.P(c.x, c.y)
            ellipse(cv, cx, cy, c.r * sx + max(0.0, 0.06 * s), c.r * sy + max(0.0, 0.06 * s),
                    shade(th["rubber"], 0.75))
            if not small:
                sphere(cv, cx, cy - 0.12 * sy, max(0.6, c.r * sx * 0.62), th["metal"], 0.45, ry=max(0.6, c.r * sy * 0.62))
            continue
        col, r = wall_style(th, c.look, s)
        if small:
            col = mix(col, field_color(th, (c.x1 + c.x2) / 2, (c.y1 + c.y2) / 2, 0, 0, s),
                      0.2 if c.look in ("pin", "plastic") else 0.5)
            r = 0.5
        capsule(cv, v.X(c.x1), v.Y(c.y1), v.X(c.x2), v.Y(c.y2), r, col)
    # bumper skirts
    for b in t.bumpers:
        cx, cy = v.P(b.x, b.y)
        ellipse(cv, cx, cy, (b.r + 0.16) * sx, (b.r + 0.16) * sy, shade(th["bumper"], 0.4))
        ellipse(cv, cx, cy, (b.r + 0.02) * sx, (b.r + 0.02) * sy, th["bumper"])
        if s >= 3:
            ellipse(cv, cx, cy, (b.r - 0.15) * sx, (b.r - 0.15) * sy, shade(th["bumper"], 0.75))
    # the apron at the bottom with the table's name
    ay = 38.7
    for py in range(int(v.Y(ay)), min(H, int(oy + TH * sy) + 1)):
        row = cv.px[py]
        vv = (py + 0.5 - oy) / sy
        for px in range(max(0, int(v.X(0))), min(W, int(math.ceil(v.X(PF_R))))):
            row[px] = mix(mix(th["plastic2"], (10, 8, 12), 0.45), (0, 0, 0), clamp((vv - ay) / 3, 0, 0.5))
    capsule(cv, v.X(0), v.Y(ay), v.X(PF_R), v.Y(ay), max(0.5, 0.1 * s), mix(th["plastic"], WHITE, 0.2))
    name = th["short"]
    kk = 1
    if dmd_width(name, 1) < (PF_R * sx) * 0.6 and (TH - ay) * sy >= 8:
        dmd_text(cv, int(v.X(PF_R / 2) - dmd_width(name, kk) / 2), int(v.Y(ay) + (TH - ay) * sy / 2 - 2), name, kk,
                 mix(th["plastic"], WHITE, 0.2))
    # plunger housing
    cv.rect(int(v.X(PF_R)) + 1, int(v.Y(PL_Y + 1.9)), max(1, int(1.5 * sx) - 1), int(2.5 * sy) + 2, (30, 28, 34))
    out = [row[:] for row in cv.px]
    _BG[k] = out
    return out


def ramp_pixels(key, cols, rows):
    """The ramp: a clear plastic chute with two metal rails, as (x, y, colour, alpha) for blending."""
    k = (key, cols, rows)
    c = _RAMP.get(k)
    if c is not None:
        return c
    if len(_RAMP) > 8:
        _RAMP.clear()
    t = table(key)
    sx, sy, ox, oy, rail = layout(cols, rows)
    s = (sx + sy) / 2
    col = t.th["ramp"]
    rl = mix(mix(t.th["metal"], col, 0.45), WHITE, 0.25)
    path, dist = t.ramp["path"], t.ramp["dist"]
    half = 0.72
    ew = max(0.14, 0.8 / min(sx, sy))
    if s < 2.2:
        rl = mix(col, t.th["field"][0], 0.15)
    out = {}
    for i in range(len(path) - 1):
        (x1, y1), (x2, y2) = path[i], path[i + 1]
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        L = math.sqrt(L2)
        X0, X1 = ox + (min(x1, x2) - half) * sx - 1, ox + (max(x1, x2) + half) * sx + 2
        Y0, Y1 = oy + (min(y1, y2) - half) * sy - 1, oy + (max(y1, y2) + half) * sy + 2
        for py in range(int(Y0), int(Y1)):
            vv = (py + 0.5 - oy) / sy
            for px in range(int(X0), int(X1)):
                u = (px + 0.5 - ox) / sx
                tt = clamp(((u - x1) * dx + (vv - y1) * dy) / L2, 0, 1)
                d = math.hypot(u - x1 - dx * tt, vv - y1 - dy * tt)
                if d > half:
                    continue
                along = dist[i] + tt * L
                if d > half - ew:
                    cc, a = rl, 0.9 if s >= 2.2 else 0.5
                elif s >= 3 and along % 1.8 < 0.13:
                    cc, a = mix(col, WHITE, 0.3), 0.45
                else:
                    cc, a = col, (0.17 if s >= 2.2 else 0.1) + (0.1 if d > half - ew * 2.2 else 0.0)
                old = out.get((px, py))
                if old is None or a > old[1]:
                    out[(px, py)] = (cc, a)
    res = [(x, y, c_, a) for (x, y), (c_, a) in out.items()]
    _RAMP[k] = res
    return res


def lamp_states(g):
    """name -> 0..1 brightness of every insert (blinking ones flash)."""
    t = g.clock
    blink = 1.0 if int(t * 6) % 2 == 0 else 0.25
    fast = 1.0 if int(t * 12) % 2 == 0 else 0.2
    st = {}
    for i in range(3):
        st["lane%d" % i] = 1.0 if g.lanes[i] else 0.0
    if any(b.state == "lane" and not b.launched for b in g.balls) or any(b.skill for b in g.balls):
        st["lane%d" % g.skill_lane] = fast
    for n in range(2, 7):
        st["bx%d" % n] = 1.0 if g.bx >= n else 0.0
    for i in range(4):
        st["m%d" % i] = 1.0 if i in g.missions_done else 0.0
    if g.mission:
        st["m%d" % g.mission[0]] = blink
    st["kick"] = 1.0 if g.kick_lit else 0.0
    st["shoot_again"] = blink if g.save_t > 0 else (1.0 if g.extra else 0.0)
    for i in range(2):
        st["lock%d" % i] = 1.0 if g.locked > i else (blink if g.lock_lit and g.locked == i else 0.0)
    st["lock2"] = fast if g.multiball else 0.0
    lit = g.lit_shots()
    for s_ in ("ramp", "scoop", "drop", "lorbit", "rorbit"):
        why = lit.get(s_)
        st[s_] = 0.0 if why is None else fast if why in ("jackpot", "super", "wizard") else blink
    if "drop" not in lit and g.lock_lit + g.locked < 3:
        st["drop"] = 0.6
    if g.tilted:
        st = {k: 0.0 for k in st}
    return st


def draw_lamps(v, g):
    cv, s, th, t = v.cv, v.s, g.th, g.t
    for name, k in lamp_states(g).items():
        lp = t.lamps.get(name)
        if lp is None or k <= 0 or lp[2] == "none":
            continue
        col = th[lp[4]]
        c = mix(shade(col, 0.4), col, k)
        if s >= 2 and k > 0.5:
            r = lp[3] * v.sx
            glow(cv, v.X(lp[0]), v.Y(lp[1]), r * 0.5, r * 2.3 + 1, col, 0.35 * k, v.sy / v.sx)
        lamp_shape(cv, v, lp, c, k > 0.5)


def draw_bumpers(v, g):
    cv, s, th = v.cv, v.s, g.th
    for b in g.t.bumpers:
        f = max(0.0, 1 - (g.clock - g.flash.get(("bumper", b.id), -9)) / 0.15)
        cx, cy = v.P(b.x, b.y)
        if f > 0 and s >= 1.5:
            glow(cv, cx, cy, b.r * v.sx, b.r * v.sx * 2.2, th["cap"], 0.5 * f, v.sy / v.sx)
        if s >= 2.5:
            ellipse(cv, cx, cy, b.r * v.sx * 0.95, b.r * v.sy * 0.95, mix(shade(th["bumper"], 1.25), WHITE, 0.5 * f))
        cap = mix(th["cap"], WHITE, 0.55 * f)
        k = 0.74 - 0.06 * f
        sphere(cv, cx, cy - b.r * v.sy * 0.2, b.r * v.sx * k, cap, 0.45, ry=b.r * v.sy * k * 1.05)
        if s >= 3.2:
            ellipse(cv, cx, cy - b.r * v.sy * 0.2, b.r * v.sx * 0.26, b.r * v.sy * 0.26,
                    mix(shade(th["bumper"], 0.85), WHITE, 0.4 * f))


def draw_slings(v, g):
    cv, s, th = v.cv, v.s, g.th
    for sl in g.t.slings:
        f = max(0.0, 1 - (g.clock - g.flash.get(("sling", sl.id), -9)) / 0.14)
        if f <= 0:
            continue
        bx, by = sl.nx, sl.ny
        if (sl.x1 < PF_R / 2) != (bx > 0):
            bx, by = -bx, -by
        mx_, my_ = (sl.x1 + sl.x2) / 2 + bx * 0.3 * f, (sl.y1 + sl.y2) / 2 + by * 0.3 * f
        r = max(0.6, 0.2 * s)
        col = mix(th["rubber"], WHITE, f)
        capsule(cv, v.X(sl.x1), v.Y(sl.y1), v.X(mx_), v.Y(my_), r, col)
        capsule(cv, v.X(mx_), v.Y(my_), v.X(sl.x2), v.Y(sl.y2), r, col)
        if s >= 2:
            glow(cv, v.X(mx_), v.Y(my_), 0, s * 1.8, th["lamp"], 0.45 * f)


def draw_drops(v, g):
    cv, s, th = v.cv, v.s, g.th
    for i, d in enumerate(g.t.drops):
        if not g.drops_up[i]:
            continue
        # a little block standing up from its slot: the face towards the flippers is lit
        bx, by = -d.nx * 0.42, -d.ny * 0.42
        face = [(d.x1, d.y1), (d.x2, d.y2), (d.x2 + bx, d.y2 + by), (d.x1 + bx, d.y1 + by)]
        if s < 1.8:
            capsule(cv, v.X(d.x1), v.Y(d.y1), v.X(d.x2), v.Y(d.y2), 0.5, mix(th["plastic"], WHITE, 0.3))
            continue
        upoly(cv, v, face, shade(th["plastic"], 0.85))
        capsule(cv, v.X(d.x1), v.Y(d.y1), v.X(d.x2), v.Y(d.y2), max(0.6, 0.1 * s), mix(th["plastic"], WHITE, 0.45))
        if s >= 3:
            mx_, my_ = (d.x1 + d.x2) / 2 + bx * 0.5, (d.y1 + d.y2) / 2 + by * 0.5
            ellipse(cv, v.X(mx_), v.Y(my_), 0.17 * v.sx, 0.17 * v.sy, th["lamp2"])


def draw_spinner(v, g):
    t = g.t
    if not t.spinner:
        return
    cv, s, th = v.cv, v.s, g.th
    x1, y1, x2, y2 = t.spinner
    k = abs(math.cos(g.spin_a))
    h = max(0.5, 0.45 * v.sy * k)
    col = mix(th["metal"], WHITE, 0.4 * (1 - k) + (0.3 if g.spin_v else 0))
    X1, X2 = v.X(x1) + 0.5, v.X(x2) - 0.5
    Y = v.Y(y1)
    cv.rect(int(X1), int(Y - h), max(1, int(X2 - X1)), max(1, int(2 * h)), shade(col, 0.8))
    cv.rect(int(X1), int(Y - h), max(1, int(X2 - X1)), 1, col)
    capsule(cv, X1, Y, X2, Y, max(0.5, 0.06 * s), mix(th["metal"], WHITE, 0.5))


def draw_flipper(v, g, f):
    cv, th = v.cv, g.th
    sx, sy = v.sx, v.sy
    tx, ty = f.tip()
    body = th["flip"]
    rub = mix(th["lamp"], (200, 40, 40), 0.5)
    if v.s < 1.5:                       # small windows: the bats must stand out from the guides
        body = mix(body, rub, 0.6)
    edge = max(0.17, 0.75 / sy)
    px0, px1 = v.X(min(f.x, tx) - f.r1) - 1, v.X(max(f.x, tx) + f.r1) + 2
    py0, py1 = v.Y(min(f.y, ty) - f.r1) - 1, v.Y(max(f.y, ty) + f.r1) + 2
    ca, sa, L = f.ca, f.sa, f.L
    aa = 1.0 / sy
    for yy in range(max(0, int(py0)), min(cv.H, int(py1))):
        row = cv.px[yy]
        ry = (yy + 0.5 - v.oy) / sy - f.y
        for xx in range(max(0, int(px0)), min(cv.W, int(px1))):
            rx = (xx + 0.5 - v.ox) / sx - f.x
            t = clamp((rx * ca + ry * sa) / L, 0, 1)
            ex, ey = rx - ca * t * L, ry - sa * t * L
            d = math.sqrt(ex * ex + ey * ey)
            rad = f.r1 + (f.r2 - f.r1) * t
            if d > rad + aa * 0.5:
                continue
            up = -(ex * 0.45 + ey * 0.8) / max(0.2, rad)
            if d > rad - edge and v.s >= 1.5:
                c = mix(rub, WHITE, max(0.0, up) * 0.35)
            else:
                c = mix(body, WHITE, up * 0.5) if up > 0 else mix(body, (60, 50, 60), -up * 0.6)
            row[xx] = c if d <= rad - aa * 0.5 else mix(row[xx], c, clamp((rad + aa * 0.5 - d) / aa, 0, 1))
    if v.s >= 2:
        cx, cy = v.P(f.x, f.y)
        sphere(cv, cx, cy, max(0.6, f.r1 * sx * 0.36), th["metal"], 0.5, ry=max(0.6, f.r1 * sy * 0.36))


def draw_ball(v, g, b, riding=False):
    cv, s, th = v.cv, v.s, g.th
    cx, cy = v.P(b.x, b.y)
    rad = R * v.sx * 0.92 * (1.15 if riding else 1.0)
    if b.state == "scoop":
        rad *= 0.82
    if s >= 2 and b.state != "scoop":
        off = 0.5 if riding else 0.25
        ellipse(cv, cx + rad * off + 0.5, cy + rad * off * 0.8 + 0.5, rad * 0.95, rad * 0.75,
                mix(cv.px[clamp(int(cy), 0, cv.H - 1)][clamp(int(cx), 0, cv.W - 1)], (0, 0, 0), 0.55))
    sp = math.hypot(b.vx, b.vy)
    if sp > 25 and s >= 1.5:
        n = len(b.trail)
        for i, (tx, ty) in enumerate(b.trail[:-1]):
            k = (i + 1) / (n + 1)
            blend(cv, int(v.X(tx)), int(v.Y(ty)), th["ballglow"], 0.4 * k)
    if rad < 1.25:
        x, y = int(cx - 0.5), int(cy - 0.5)
        for dx, dy in ((-1, 0), (2, 0), (0, -1), (1, -1), (0, 2), (1, 2), (-1, 1), (2, 1)):
            blend(cv, x + dx, y + dy, th["ballglow"], 0.55 if v.s >= 1.4 else 0.3)
        cv.rect(x, y, 2, 2, (226, 230, 240))
        cv.set(x, y, WHITE)
        cv.set(x + 1, y + 1, (150, 156, 176))
        return
    if s >= 2.5:
        glow(cv, cx, cy, rad * 0.9, rad * 2.2, th["ballglow"], 0.22)
    sphere(cv, cx, cy, rad, (172, 178, 194), 0.6)
    if rad >= 2.5:   # the playfield mirrored in the lower half of the chrome
        for yy in range(max(0, int(cy + rad * 0.2)), min(cv.H, int(cy + rad * 0.8))):
            w = math.sqrt(max(0.0, rad * rad * 0.6 - (yy + 0.5 - cy) ** 2))
            for xx in range(max(0, int(cx - w)), min(cv.W, int(cx + w) + 1)):
                cv.px[yy][xx] = mix(cv.px[yy][xx], th["field"][1], 0.35)


def draw_plunger(v, g):
    cv, s, th = v.cv, v.s, g.th
    x = v.X(LANE_X)
    top = v.Y(g.plunger_y)
    bot = v.Y(TH)
    w = max(1.0, 0.55 * v.sx)
    n = max(3, int((bot - top) / max(1.5, v.sy * 0.35)))
    for i in range(n):
        y = top + 0.4 * v.sy + (bot - top - 0.4 * v.sy) * i / n
        cv.line(int(x - w), int(y), int(x + w), int(y + (bot - top) / n * 0.5), mix(th["metal"], (60, 60, 70), 0.3))
    cv.rect(int(x - w * 0.3), int(top), max(1, int(w * 0.6)), int(bot - top), shade(th["metal"], 0.6))
    cv.rect(int(x - w), int(top), max(1, int(2 * w)), max(1, int(0.35 * v.sy)), mix(th["metal"], WHITE, 0.3))


def render(g, cols, rows, panels=True):
    sx, sy, ox, oy, rail = layout(cols, rows)
    cv = Canvas(cols, 1)
    cv.rows, cv.H = rows, rows * 2
    cv.px = [r[:] for r in backdrop(g.key, cols, rows)]
    dx = dy = 0
    if g.shake > 0 and sy >= 1.5:
        dx = int(round(g.shake_dir[0] * g.shake * sx * 0.35))
        dy = int(round(g.shake_dir[1] * g.shake * sy * 0.35))
        if dx or dy:
            shift(cv, ox - rail, int(math.ceil(ox + TW * sx)) + rail, dx, dy)
    v = View(cv, sx, sy, ox + dx, oy + dy)
    draw_lamps(v, g)
    draw_bumpers(v, g)
    draw_slings(v, g)
    draw_drops(v, g)
    draw_spinner(v, g)
    draw_plunger(v, g)
    for f in g.flippers:
        draw_flipper(v, g, f)
    for b in g.balls:
        if b.state in ("play", "lane", "scoop"):
            draw_ball(v, g, b)
    for x, y, c, a in ramp_pixels(g.key, cols, rows):
        blend(cv, x + dx, y + dy, c, a)
    for b in g.balls:
        if b.state == "ride":
            draw_ball(v, g, b, riding=True)
    psz = 1 if v.s < 3 else 2
    for p in g.parts:
        k = 1 - p[4] / p[5]
        x, y = int(v.X(p[0])), int(v.Y(p[1]))
        if psz == 1:
            blend(cv, x, y, p[6], 0.4 + 0.6 * k)
        else:
            cv.rect(x, y, psz, psz, mix((20, 10, 20), p[6], 0.3 + 0.7 * k))
    if g.tilted:
        for y in range(0, cv.H):
            row = cv.px[y]
            for x in range(max(0, ox), min(cv.W, int(ox + TW * sx))):
                row[x] = shade(row[x], 0.6)
    if panels:
        draw_panels(cv, g, sx, ox, rail)
    return cv


def shift(cv, x0, x1, dx, dy):
    """Shake: move a vertical strip of the picture by (dx, dy) pixels."""
    x0, x1 = max(0, x0), min(cv.W, x1)
    rows = [cv.px[y][x0:x1] for y in range(cv.H)]
    for y in range(cv.H):
        src = rows[clamp(y - dy, 0, cv.H - 1)]
        if dx > 0:
            src = src[:1] * dx + src[:-dx]
        elif dx < 0:
            src = src[-dx:] + src[-1:] * (-dx)
        cv.px[y][x0:x1] = src

# --- the side panels: backglass with missions on the left, the score display on the right ---------
def draw_panels(cv, g, s, ox, rail):
    cols, rows = cv.cols, cv.rows
    th = g.th
    lw = max(0, ox - rail)                     # left panel columns
    rx = int(math.ceil(ox + TW * s)) + rail     # right panel first column
    rw = cols - rx
    acc = th["accent"]
    # --- right: the dot-matrix display ---
    if rw >= 12:
        x0, w = rx + 1, rw - 2
        msg = g.msgs[-1] if g.msgs else None
        big = None
        lines = []
        if g.state == "bonus" and g.bonus_show:
            b, x, _ = g.bonus_show
            big, lines = ("TILT" if g.tilted else "BONUS"), ["%s x %d" % (fmt(b), x), "= %s" % fmt(b * x)]
        elif g.over:
            big, lines = "GAME OVER", [fmt(g.score)]
        elif msg:
            big, lines = msg[0], [msg[1]] if msg[1] else []
        k = 2 if w * 1 >= dmd_width("8" * 11, 2) + 4 and rows >= 30 else 1
        dh_rows = 4 + (1 if k == 2 else 0) * 3
        if w >= dmd_width("8" * 9, 1) + 2 and rows >= 24:
            y0 = 2
            cv.rect(x0, y0, w, dh_rows * 2, DMD_BG)
            cv.frame(x0 - 1, y0 - 1, w + 2, dh_rows * 2 + 2, mix(acc, (40, 30, 30), 0.5))
            for yy in range(y0, y0 + dh_rows * 2):
                for xx in range(x0, x0 + w):
                    if (xx + yy) % 2 == 0:
                        cv.px[yy][xx] = DMD_OFF if k == 1 else mix(DMD_BG, DMD_OFF, 0.5)
            text = big or fmt(g.score)
            kk = k
            while kk > 1 and dmd_width(text, kk) > w - 2:
                kk -= 1
            if dmd_width(text, kk) > w - 2:
                text = text[:max(1, (w - 2) // 4)]
            col = DMD_ON if not big else mix(DMD_ON, WHITE, 0.25)
            dmd_text(cv, x0 + (w - dmd_width(text, kk)) // 2, y0 + 2, text, kk, col)
            sub = lines[0] if lines else ("BALL %d" % min(g.ball_no, g.balls_total) if not g.over else "")
            if g.state == "play" and not big and any(b.state == "lane" and not b.launched for b in g.balls):
                sub = "PULL THE PLUNGER"
            if sub:
                kk = 1
                sub = sub.upper()
                if dmd_width(sub, 1) > w - 2:
                    sub = sub[:(w - 1) // 4]
                dmd_text(cv, x0 + (w - dmd_width(sub, 1)) // 2, y0 + 2 + 5 * k + 3, sub, 1, shade(DMD_ON, 0.8))
            r = y0 // 2 + dh_rows + 1
        else:
            cv.put(rx, 0, " " * rw, DMD_ON, DMD_BG)
            text = big or fmt(g.score)
            cv.put(rx + max(0, (rw - len(text)) // 2), 0, text[:rw], DMD_ON, DMD_BG)
            sub = (lines[0] if lines else "")[:rw]
            cv.put(rx, 1, " " * rw, shade(DMD_ON, 0.7), DMD_BG)
            if sub:
                cv.put(rx + max(0, (rw - len(sub)) // 2), 1, sub, shade(DMD_ON, 0.8), DMD_BG)
            r = 3
        info = status_lines(g, rw - 3)
        gap = 2 if rows >= 56 else 1
        for text, col in info:
            if r >= rows - 1:
                break
            cv.put(rx + 2, r, text[:rw - 3], col)
            r += gap if text else 1
        keys = ["Z/Left  Right/M  flip", "Space  plunger", "Up  nudge   Esc  pause"] if rw >= 26 else \
            ["Z / M  flip", "Space plunge", "Up  nudge"] if rw >= 15 else []
        card = rules_card(g)
        if r + len(card) + len(keys) + 2 < rows - 1 and rw >= 30:
            r += 1
            for text, col in card:
                cv.put(rx + 2, r, text[:rw - 3], col)
                r += 1
        if rows - 1 > r:
            for i, kline in enumerate(keys):
                rr = rows - len(keys) + i - 1
                if rr > r:
                    cv.put(rx + 2, rr, kline[:rw - 3], shade(DIM, 0.8))
    # --- left: the backglass ---
    if lw >= 12:
        draw_backglass(cv, g, lw)


def rules_card(g):
    """The instruction card, like the one on a real apron."""
    th = g.th
    c1, c2 = shade(DIM, 1.1), shade(DIM, 0.85)
    return [("- HOW TO PLAY -", th["accent"]),
            ("top lanes   bonus X", c1),
            ("%-11s light lock" % th["drop_name"].lower(), c2),
            ("2 locks     multiball", c1),
            ("%-11s jackpot" % th["ramp_name"].lower(), c2),
            ("2 orbits    light mission", c1),
            ("%-11s mission, lock" % th["scoop_name"].lower(), c2),
            ("3 ramps     extra ball", c1),
            ("4 missions  wizard mode", c2)]


def status_lines(g, w):
    th = g.th
    out = []
    best = max(g.score, g.hi)
    if w >= 20:
        out.append(("SCORE %s" % fmt(g.score), GOLD))
        out.append(("HIGH  %s" % fmt(best), DIM))
    else:
        out.append(("HI %s" % fmt(best), DIM))
    out.append(("", DIM))
    out.append(("BALL %d/%d" % (min(g.ball_no, g.balls_total), g.balls_total) +
                ("  +%d" % g.extra if g.extra else ""), TEXT))
    out.append(("BONUS %dX  %s" % (g.bx, fmt(g.bonus)) if w >= 18 else "BONUS %dX" % g.bx, TEXT))
    locks = "o" * g.locked + "*" * g.lock_lit + "." * max(0, 2 - g.locked - g.lock_lit)
    out.append(("LOCK  %s" % locks + (("  multiball" if w >= 20 else " MB") if g.multiball else ""),
                th["lamp"] if g.lock_lit else TEXT))
    out.append(("KICKBACK %s" % ("lit" if g.kick_lit else "off"), th["lamp2"] if g.kick_lit else DIM))
    if g.extra_lit:
        out.append(("EXTRA BALL lit", WHITE))
    if g.save_t > 0:
        out.append(("BALL SAVE %d" % math.ceil(g.save_t), (150, 255, 170)))
    if g.jackpot_lit:
        out.append(("JACKPOT %s" % fmt(g.jackpot_value) if w >= 20 else "JP %s" % fmt(g.jackpot_value), WHITE))
    if g.super_t > 0:
        out.append(("SUPER at %s %d" % (th["scoop_name"].lower(), math.ceil(g.super_t)), WHITE))
    if g.tilted:
        out.append(("TILT", (255, 80, 70)))
    elif g.warnings:
        out.append(("tilt warnings %d" % g.warnings, (255, 140, 110)))
    return out


_GLASS = {}


def glass_art(key, w, h):
    """The backglass picture for a table (cached per size): a small painted scene."""
    k = (key, w, h)
    c = _GLASS.get(k)
    if c is not None:
        return c
    th = THEMES[key]
    img = [[(0, 0, 0)] * w for _ in range(h)]
    top, bot = th["field"]
    for y in range(h):
        for x in range(w):
            u, v_ = x / max(1, w - 1), y / max(1, h - 1)
            c = mix(shade(top, 0.8), shade(bot, 1.1), v_)
            if key == "belfry":
                dm = math.hypot((u - 0.7) * w, (v_ - 0.3) * h) / max(4, min(w, h) * 0.28)
                if dm < 1:
                    c = mix((240, 236, 200), (200, 190, 150), dm * dm)
                elif dm < 1.8:
                    c = mix(c, (120, 110, 160), (1.8 - dm) / 0.8 * 0.5)
                if hsh(x, y, 11) % 41 == 0:
                    c = mix(c, WHITE, 0.6)
                # the belfry: a tower with a bell
                bx = abs(u - 0.32) * w
                tw = w * 0.13
                ty0 = h * 0.38
                if bx < tw and y > ty0:
                    c = (32, 22, 30) if not (bx < tw * 0.6 and ty0 + h * 0.12 < y < ty0 + h * 0.3) else (14, 10, 18)
                    bw = tw * 0.5 * clamp((y - ty0 - h * 0.14) / (h * 0.14), 0.2, 1.0)
                    if bx < bw and ty0 + h * 0.12 < y < ty0 + h * 0.28:
                        c = mix((210, 160, 70), (120, 80, 30), bx / max(1, bw))
                if y > ty0 - (tw - bx) * 1.2 and bx < tw * 1.15 and y <= ty0:
                    c = (40, 26, 30)
                if y > h * 0.86:
                    c = mix((20, 14, 26), (8, 6, 12), (y - h * 0.86) / (h * 0.14))
            elif key == "reef":
                w1 = math.sin(u * 9 + math.sin(v_ * 7) * 2) + math.sin(v_ * 11 - u * 3)
                if w1 > 1.4:
                    c = mix(c, (80, 200, 200), 0.3)
                for i, (fx, fy, fc) in enumerate(((0.3, 0.35, (255, 170, 80)), (0.62, 0.55, (120, 255, 220)),
                                                  (0.45, 0.72, (255, 120, 180)))):
                    dx, dy = (u - fx) * w, (v_ - fy) * h
                    rr = max(2.0, min(w, h) * 0.09)
                    if (dx / (rr * 1.6)) ** 2 + (dy / rr) ** 2 < 1:
                        c = mix(fc, WHITE, 0.3 * max(0, -dy / rr))
                    elif -rr * 2.6 < dx < -rr * 1.4 and abs(dy) < (dx + rr * 2.6) * 0.6:
                        c = shade(fc, 0.8)
                    dg = math.hypot(dx, dy)
                    if rr < dg < rr * 2.6:
                        c = mix(c, fc, 0.12 * (1 - (dg - rr) / (rr * 1.6)))
                if v_ > 0.82:
                    c = mix((150, 120, 80), (90, 70, 50), (v_ - 0.82) / 0.18)
                    if hsh(x, y, 2) % 5 == 0:
                        c = mix(c, (200, 170, 120), 0.3)
                if v_ > 0.6 and abs(math.sin(u * 23 + v_ * 3)) < 0.18 and v_ > 0.82 - 0.25 * abs(math.sin(u * 7)):
                    c = (220, 80, 110)
            else:
                if hsh(x, y, 13) % 29 == 0:
                    c = mix(c, (255, 230, 200), 0.5)
                # the comet streaking down to the anvil
                cx_, cy_ = 0.72 * w, 0.25 * h
                dx, dy = x - cx_, y - cy_
                along = (dx * 0.8 + dy * 0.6)
                across = abs(-dx * 0.6 + dy * 0.8)
                if along < 0 and across < -along * 0.18 + 1.5:
                    c = mix(c, (255, 180, 80), clamp(1 + along / (w * 0.6), 0, 1) * 0.8)
                if dx * dx + dy * dy < max(2.0, w * 0.05) ** 2:
                    c = (255, 250, 220)
                ay = 0.68 * h
                if abs(u - 0.4) * w < w * 0.22 and ay < y < ay + h * 0.08:
                    c = (60, 60, 72) if y > ay + 1 else (150, 150, 170)
                if abs(u - 0.4) * w < w * 0.08 and ay + h * 0.08 <= y < ay + h * 0.2:
                    c = (44, 44, 54)
                if v_ > 0.88:
                    c = mix((80, 30, 20), (30, 10, 10), (v_ - 0.88) / 0.12)
            img[y][x] = c
    _GLASS[k] = img
    if len(_GLASS) > 12:
        _GLASS.clear()
    return img


def draw_backglass(cv, g, lw):
    th = g.th
    rows = cv.rows
    acc = th["accent"]
    gw = lw - 2
    gh = min(cv.H - 4, max(8, int(gw * 0.75)))
    if rows < 24:
        gh = min(gh, 10)
    art = glass_art(g.key, gw, gh)
    x0, y0 = 1, 2
    for j in range(gh):
        cv.px[y0 + j][x0:x0 + gw] = art[j]
    cv.frame(x0 - 1, y0 - 1, gw + 2, gh + 2, mix(acc, (60, 40, 30), 0.4))
    name = th["name"]
    nr = (y0 + gh) // 2 + 1
    cv.put(max(0, (lw - len(name)) // 2), nr, name[:lw], acc)
    r = nr + 2
    if r < rows - 2:
        cv.put(1, r, "MISSIONS"[:lw - 1], DIM)
        r += 1
    for i, (mname, shots, need) in enumerate(th["missions"]):
        if r >= rows - 1:
            break
        if g.mission and g.mission[0] == i:
            text = "> %s %d/%d %ds" % (mname, g.mission[1], need, math.ceil(g.mission[2]))
            col = WHITE if int(g.clock * 4) % 2 else acc
        elif i in g.missions_done:
            text = "+ %s" % mname
            col = acc
        else:
            text = "  %s" % mname
            col = DIM
        cv.put(1, r, text[:lw - 1], col)
        r += 1
    if r < rows - 1:
        wz = th["wizard"]
        if g.wizard > 0:
            cv.put(1, r, ("* %s %ds" % (wz, math.ceil(g.wizard)))[:lw - 1], WHITE)
        else:
            cv.put(1, r, ("  %s" % wz)[:lw - 1], shade(DIM, 0.7))
        r += 1
    if g.mission_lit and not g.mission and r < rows - 1:
        text = "MISSION lit at %s" % th["scoop_name"].lower()
        cv.put(1, r, (text if len(text) < lw else "MISSION LIT")[:lw - 1], th["lamp"])
        r += 1
    story = wrap(" ".join(th["story"]), lw - 2)
    if r + len(story) + 1 < rows - 1:
        for j, line in enumerate(story):
            cv.put(1, rows - 1 - len(story) + j - 1, line, shade(DIM, 0.8))


def wrap(text, w):
    out, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > w:
            out.append(line)
            line = word
        else:
            line = (line + " " + word).strip()
    if line:
        out.append(line)
    return out


def render_over(g, cv, record, auto=False):
    lines = ["GAME OVER", "", g.th["name"], "", "score  %s" % fmt(g.score)]
    st = g.stats
    lines.append("ramps %d  orbits %d  jackpots %d" % (st["ramps"], st["orbits"], st["jackpots"]))
    lines.append("missions %d  multiballs %d" % (st["missions"], st["multiballs"]))
    if record:
        lines += ["", "** NEW RECORD **"]
    lines += ["", "auto mode: a new game starts" if auto else "Enter: again   Esc / Q: menu"]
    w = max(len(l) for l in lines) + 4
    x, y = max(0, (cv.cols - w) // 2), max(0, cv.rows // 2 - len(lines) // 2 - 1)
    edge = GOLD if record else (200, 76, 86)
    cv.frame(x - 1, y * 2 - 1, w + 2, (len(lines) + 2) * 2 + 2, edge)
    cv.box(x, y, [l.center(w - 4) for l in lines], (240, 240, 246), (24, 22, 44))


# =============================================================================================
# Title demo, controls, menu, main loop
# =============================================================================================
class TitleDemo:
    """The autopilot playing each table in turn, behind the title (and in the launcher preview)."""

    def __init__(self, k=0):
        self.k = k
        self.new_run()

    def new_run(self):
        key = ORDER[self.k % len(ORDER)]
        self.g = Game(key, seed=self.k + 1, demo=True)
        self.bot = Bot(self.g, seed=self.k)
        self.k += 1
        self.age = 0.0

    def scene(self, cols, rows, dt):
        g = self.g
        self.age += dt
        g.update(min(dt, 0.1), self.bot)
        if g.over or self.age > 50:
            self.new_run()
        cv = render(self.g, cols, rows, panels=cols >= 40 and rows >= 12)
        cv.text = {}            # the panels' pictures stay, their words would clutter the title
        return cv


LEFT, RIGHT = ("left", "z", "a"), ("right", "m", "/", "l")
PLUNGE = (" ", "down", "s")
NUDGE = ("up", "w", "n")


class Controls:
    """Keys to (left flipper, right flipper, plunger held, nudge). Classic terminals: a press flips for a moment
    (the window is learned from the keyboard's repeat delay, so a held key stays up); a tap on the plunger pulls it
    for a while, holding pulls further."""

    def __init__(self, kitty):
        self.kitty = kitty
        self.held = HeldKeys(kitty, first=0.24, repeat=0.13)
        self.held.OPPOSITE = {}
        self.pl = HeldKeys(kitty, first=0.6, repeat=0.16)
        self.pl.OPPOSITE = {}
        self.first = {}
        self.delay = 0.3
        self.nudge = None

    def reset(self):
        self.held.clear()
        self.pl.clear()
        self.first = {}
        self.nudge = None

    def feed(self, name, kind, now):
        if name in NUDGE:
            if kind == "press":
                self.nudge = "up"
            return
        if name in PLUNGE:
            self.pl.feed(name, kind, now)
            return
        if name not in LEFT + RIGHT:
            return
        if not self.kitty and kind == "press":
            held_now = self.held.until.get(name, 0) > now
            if name in self.first and now - self.first[name] < 0.9:
                gap = now - self.first.pop(name)
                if 0.12 < gap < 0.8:
                    self.delay = clamp(self.delay * 0.5 + gap * 0.5, 0.2, 0.55)
                    self.held.first = min(0.6, self.delay + 0.06)
            elif not held_now:
                self.first[name] = now
        self.held.feed(name, kind, now)

    def sample(self, now):
        self.held.tick(now)
        self.pl.tick(now)
        n, self.nudge = self.nudge, None
        out = (self.held.down(*LEFT), self.held.down(*RIGHT), self.pl.down(*PLUNGE), n)
        self.held.take_hits()
        self.pl.take_hits()
        return out


class AutoRun:
    """Auto mode: the real game on the chosen table (three balls, sound), played by the autopilot. After a game
    over the result stays for a few seconds, then a new game starts. No score is kept."""
    OVER_SHOW = 4.0

    def __init__(self, key, sound=True, seed=None):
        self.tkey, self.sound, self.seed = key, sound, seed
        self.auto = AutoMode()
        self.rounds = 0
        self.new()

    def new(self):
        self.rounds += 1
        self.g = Game(self.tkey, quiet=not self.sound, seed=None if self.seed is None else self.seed + self.rounds)
        self.g.hi = load_scores().get(GAME, {}).get(self.tkey) or 0
        self.bot = Bot(self.g, seed=None if self.seed is None else self.seed * 3 + self.rounds)
        self.over_t = 0.0

    def key(self, k):
        a = self.auto.key(k)
        if a == "sound" and SND.toggle():
            SND.play("sound_on")
        return a

    def frame(self, dt, cols, rows, draw=True):
        g = self.g
        if g.over:
            if not (self.auto.paused or self.auto.help):
                self.over_t += dt
            if self.over_t >= self.OVER_SHOW:
                self.new()
                g = self.g
        else:
            for _ in range(self.auto.steps(dt, DT)):
                g.step(self.bot())
                if g.over:
                    break
        if not draw:
            return None
        cv = render(g, cols, rows)
        if g.over:
            render_over(g, cv, False, auto=True)
        self.auto.banner(cv, extra="game %d" % self.rounds)
        return cv


MIN_COLS, MIN_ROWS = 60, 22


def too_small(term):
    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (%dx%d)." % (MIN_COLS, MIN_ROWS))


def run_auto(term, key):
    """Auto mode until the viewer stops it (Esc / Q)."""
    run = AutoRun(key)
    last = time.time()
    while True:
        now = time.time()
        dt, last = min(0.1, now - last), now
        for k, kind in term.events(0):
            if kind == "press" and run.key(k) == "stop":
                return
        cols, rows = term.size()
        if cols < MIN_COLS or rows < MIN_ROWS:
            too_small(term)
            time.sleep(0.2)
            continue
        term.write(run.frame(dt, cols, rows).emit())
        time.sleep(max(0.0, 1 / 30 - (time.time() - now)))


def menu_items(ti):
    return ["Play", "Table   < %d %s >" % (ti + 1, THEMES[ORDER[ti]]["name"]), AUTO_LABEL]


def render_menu(demo, cols, rows, sel, ti, dt, help_, kitty):
    cv = demo.scene(cols, rows, dt)
    rec = load_scores().get(GAME, {})
    bits = ["%s %s" % (THEMES[k]["short"].lower(), fmt(rec[k])) for k in ORDER if rec.get(k)]
    best = ("best  " + "   ".join(bits)) if bits else None
    extra = ["", THEMES[ORDER[ti]]["story"][0], THEMES[ORDER[ti]]["story"][1],
             "Keys: %s" % ("with releases (kitty protocol)" if kitty else "classic terminal mode")]
    title_screen(cv, NAME, TAGLINE, menu_items(ti), sel, best, extra=extra,
                 keys="Up/Down choose   Left/Right table   Enter start   M %s   ? help   Esc back" % SND.label().lower(),
                 help_lines=help_lines(kitty), show_help=help_, dim=0.5)
    return cv


def record(g):
    return submit(GAME, g.key, g.score)


def play(term, ctl, key):
    """One game. Returns 'again' or 'menu'."""
    g = Game(key)
    ctl.reset()
    last = time.time()
    rec = None
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
                if name in ("enter",):
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
                    record(g)
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
        if cols < MIN_COLS or rows < MIN_ROWS:
            too_small(term)
            g.paused = g.paused or not g.over
            time.sleep(0.2)
            last = time.time()
            continue
        if not g.paused:
            g.update(dt, ctl.sample(now))
        if g.over and not submitted:
            submitted = True
            rec = record(g)
        cv = render(g, cols, rows)
        if g.paused:
            overlay(cv, help_lines(ctl.kitty) if g.help else PAUSE_LINES + ["", SND.label()])
        elif g.over:
            render_over(g, cv, rec)
        term.write(cv.emit())
        time.sleep(max(0.0, 1 / 60 - (time.time() - now)))


def main():
    with KeyTerminal() as term:
        ctl = Controls(term.kitty)
        demo = TitleDemo()
        sel, ti, help_ = 0, 0, False
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
            term.write(render_menu(demo, cols, rows, sel, ti, min(0.1, now - last), help_, ctl.kitty).emit())
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
                    sel = (sel + 1) % 3
                    SND.play("menu")
                elif k in ("up", "w"):
                    sel = (sel - 1) % 3
                    SND.play("menu")
                elif k in ("left", "a", "right", "d"):
                    ti = (ti + (1 if k in ("right", "d") else -1)) % len(ORDER)
                    sel = sel if sel != 0 else 1
                    SND.play("menu")
                elif k == "m":
                    if SND.toggle():
                        SND.play("sound_on")
                elif k in ("enter", " "):
                    SND.play("start")
                    go = True
            if not go:
                continue
            if sel == 2:
                run_auto(term, ORDER[ti])
                last = time.time()
                continue
            while play(term, ctl, ORDER[ti]) == "again":
                pass
            last = time.time()


# =============================================================================================
# Self-test
# =============================================================================================
def run_bot(key, limit=600.0, seed=1):
    """The autopilot plays one whole game. Returns the game."""
    g = Game(key, seed=seed, quiet=True)
    bot = Bot(g, seed=seed)
    t = 0.0
    while t < limit and not g.over:
        g.step(bot())
        t += DT
    return g


def selftest():
    t0 = time.time()
    global submit

    def no_scores(*a, **k):
        raise AssertionError("the self-test must not write scores")
    submit = no_scores
    random.seed(3)
    # 1. the tables: everything inside, every kind of part present
    for key in ORDER:
        t = table(key)
        kinds = {c.kind for c in t.colliders}
        names = {s_[4] for s_ in t.sensors}
        assert {"bumper", "sling", "drop", "ramp", "gate", "wall", "post"} <= kinds, (key, kinds)
        assert {"lane0", "lane1", "lane2", "lorbit", "spin", "kickback"} <= names, (key, names)
        assert t.scoop and t.ramp and len(t.drops) >= 3 and len(t.flips) >= 2
        for c in t.colliders:
            pts = [(c.x, c.y)] if c.circle else [(c.x1, c.y1), (c.x2, c.y2)]
            for x, y in pts:
                assert -0.01 <= x <= TW + 0.01 and -0.01 <= y <= TH + 1, (key, x, y)
        for m in t.th["missions"]:
            assert all(s_ in SHOTS + ("bumper",) for s_ in m[1]), m
    print("tables: %s - %s colliders, %d flippers on the forge" % (
        ", ".join(THEMES[k]["name"] for k in ORDER), "/".join(str(len(table(k).colliders)) for k in ORDER),
        len(table("forge").flips)))
    # 2. physics: fast balls never tunnel through walls or moving flippers, and never leave the table
    leaks = 0
    rnd = random.Random(5)
    n_ = 0
    for key in ORDER:
        for i in range(160):
            g = Game(key, seed=i, sandbox=True)
            g.balls = []
            a = rnd.uniform(0, 2 * math.pi)
            sp = rnd.uniform(40, VMAX)
            b = Ball(rnd.uniform(3, 15), rnd.uniform(9, 30), math.cos(a) * sp, math.sin(a) * sp)
            g.balls.append(b)
            flip = rnd.random() < 0.5
            for k in range(int(1.5 / DT)):
                g.step((flip and k % 40 < 20, flip and k % 40 >= 20, False, None))
                if b not in g.balls:
                    break
                n_ += 1
                inside = -0.05 <= b.x <= TW + 0.05 and b.y >= -0.05
                if b.y < 10:
                    inside = inside and math.hypot(b.x - 10, b.y - 10) <= 10 - R + 0.1
                if b.x > PF_R + 0.1 and b.y < 11:
                    pass
                if not inside:
                    leaks += 1
                    break
                for f in g.flippers:
                    t_, d, side = f.local(b.x, b.y)
                    rad = f.r1 + (f.r2 - f.r1) * t_
                    assert d > rad + R - 0.12, "%s: a ball sank into a flipper (%.2f)" % (key, d - rad - R)
    assert leaks == 0, "%d balls left the table" % leaks
    print("physics: 480 balls at 40-%d units/s with flapping flippers, %d steps checked, none tunnelled" % (
        VMAX, n_))
    # flipper strength: a cradled ball flipped from the tip reaches the top of the table
    for key in ORDER:
        for side in ("L", "R"):
            g, f, b = cradle_game(key, side)
            assert b.state == "play" and math.hypot(b.vx, b.vy) < 1.0, "%s %s: no cradle" % (key, side)
    # 3. nothing traps a ball: drop balls everywhere with no player and see them all reach the drain
    worst = 0.0
    for key in ORDER:
        for i in range(40):
            g = Game(key, seed=i, sandbox=True)
            g.balls = []
            while True:
                x, y = rnd.uniform(0.6, PF_R - 0.6), rnd.uniform(3, 33)
                if y < 10 and math.hypot(x - 10, y - 10) > 9.2:
                    continue
                ok = True
                for c in g.t.colliders:
                    if c.circle:
                        ok = ok and math.hypot(x - c.x, y - c.y) > c.r + R + 0.1
                    else:
                        px, py = x - c.x1, y - c.y1
                        tt = clamp(px * c.dx + py * c.dy, 0, c.L)
                        ok = ok and math.hypot(px - c.dx * tt, py - c.dy * tt) > c.th + R + 0.1
                if ok:
                    break
            b = Ball(x, y, rnd.uniform(-10, 10), rnd.uniform(-10, 10))
            g.balls.append(b)
            tt = 0.0
            while b in g.balls and tt < 60:
                g.step((False, False, False, None))
                tt += DT
                if b.state == "scoop":
                    b.hold = 0.0
            assert b not in g.balls, "%s: a ball dropped at %.1f, %.1f never drained (%.1f, %.1f, %s, %.1f %.1f)" % (
                key, x, y, b.x, b.y, b.state, b.vx, b.vy)
            worst = max(worst, tt)
    print("no traps: 120 balls dropped anywhere with the flippers down all drain (slowest %.1f s)" % worst)
    # 4. practice: every table offers every kind of shot to the autopilot
    for key in ORDER:
        cal = practice(key)
        assert cal == CAL[key], "%s: the practice results changed, run --practice and update CAL:\n%r" % (key, cal)
        got = set(cal["L"]) | set(cal["R"])
        need = {"ramp", "scoop", "drop"}
        assert need <= got, "%s: the flippers cannot make %s" % (key, need - got)
        assert len(cal["plunge"]) == 3, "%s: plunges reach only %s" % (key, sorted(cal["plunge"]))
        print("practice: %-15s left %s | right %s | skill lanes %s" % (
            THEMES[key]["name"], " ".join(sorted(cal["L"])), " ".join(sorted(cal["R"])),
            " ".join("%s@%.2f" % (k[4:], v[0]) for k, v in sorted(cal["plunge"].items()))))
    # 5. the rules
    g = Game("belfry", seed=1, quiet=True)
    g.balls = []
    b = Ball(9, 20)
    b.state = "play"
    g.balls.append(b)
    for i in range(3):
        g.switch("lane%d" % i, b)
    assert g.bx == 2 and not any(g.lanes), "lanes"
    g.lanes = [True, False, False]
    g.lane_change(1)
    assert g.lanes == [False, True, False]
    for i in range(len(g.t.drops)):
        g.drop_down(i)
    assert g.lock_lit == 1 and g.drop_reset > 0
    for _ in range(int(2.0 / DT)):
        b.x, b.y, b.vx, b.vy = 9.0, 26.0, 0.0, 0.0
        g.step((False, False, False, None))
    assert all(g.drops_up), "drop targets did not reset"
    # lock three balls -> multiball
    for n in range(2):
        g.lock_lit = 1
        bb = Ball(*g.t.scoop[:2])
        g.balls.append(bb)
        g.scoop_check(bb, 5.0)
    assert g.multiball and g.queue == 1 and g.pending == 1, "multiball did not start (%s, %s)" % (g.multiball, g.queue)
    for _ in range(int(5 / DT)):
        for bb in g.balls:
            if bb.state == "play" and bb.y > 30:
                bb.y, bb.vy = 20.0, -10.0
        g.step((False, False, False, None))
    assert len([bb for bb in g.balls if bb.state in ("play", "ride", "scoop")]) >= 3, "multiball has too few balls"
    sc = g.score
    bb = next(bb for bb in g.balls if bb.state == "play")
    g.ramp_made(bb)
    assert g.score - sc >= POINTS["jackpot"] and g.super_t > 0, "no jackpot"
    # missions: two orbits light one, the scoop starts it, three ramps finish it
    g = Game("belfry", seed=2, quiet=True)
    b = g.balls[0]
    b.state = "play"
    g.mission_lit = False
    g.switch("lorbit", b)
    g.switch("rorbit", b)
    assert g.mission_lit
    g.scoop_enter(b)
    assert g.mission and g.mission[0] == 0
    for _ in range(3):
        g.ramp_made(b)
    assert not g.mission and 0 in g.missions_done and g.extra_lit
    g.ramp_made(b)
    assert g.extra == 1, "extra ball"
    for i in (1, 2, 3):
        g.mission = [i, 0, 30.0]
        g.mission_complete()
    assert g.wizard > 0, "the wizard mode did not start"
    # kickback, ball save, tilt, bonus and the end of the game
    g = Game("reef", seed=3, quiet=True)
    b = g.balls[0]
    b.state = "play"
    b.x, b.y, b.vx, b.vy = 0.8, 29.0, 0.0, 20.0
    for _ in range(30):
        g.step((False, False, False, None))
    assert b.vy < 0 and not g.kick_lit and g.stats["kicks"] == 1, "kickback"
    g = Game("reef", seed=4, quiet=True)
    for _ in range(int(0.75 / DT)):
        g.step((False, False, True, None))
    for _ in range(int(1.0 / DT)):
        g.step((False, False, False, None))
    assert g.save_t > 0 and g.balls[0].launched, "the plunger did not launch"
    g.balls[0].x, g.balls[0].y = 9.25, 40.0
    g.balls[0].vy = 20
    for _ in range(int(0.5 / DT)):
        g.step((False, False, False, None))
    assert g.stats["saves"] == 1 and g.ball_no == 1 and g.balls, "ball save"
    g = Game("forge", seed=5, quiet=True)
    for _ in range(4):
        g.step((False, False, False, "up"))
    assert g.tilted and all(not f.on for f in g.flippers), "tilt"
    g.step((True, True, False, None))
    assert all(not f.on for f in g.flippers), "flippers work while tilted"
    g = Game("forge", seed=6, quiet=True)
    g.bonus = 10000
    g.bx = 3
    g.balls[0].state = "play"
    g.drain(g.balls[0])
    assert g.state == "bonus"
    sc = g.score
    for _ in range(int(3 / DT)):
        g.step((False, False, False, None))
    assert g.score == sc + 30000 and g.ball_no == 2 and g.balls, "bonus / next ball"
    g.ball_no = 3
    g.balls[0].state = "play"
    g.drain(g.balls[0])
    for _ in range(int(3 / DT)):
        g.step((False, False, False, None))
    assert g.over, "no game over after the last ball"
    # skill shot by plunge strength
    for key in ORDER:
        lane, pulls = sorted(CAL[key]["plunge"].items())[0]
        g = Game(key, seed=7, quiet=True)
        g.skill_lane = int(lane[4:])
        for _ in range(int(0.3 / DT)):
            g.step((False, False, False, None))
        g.fire(pulls[len(pulls) // 2])
        for _ in range(int(3 / DT)):
            g.step((False, False, False, None))
        assert g.stats["skill"] == 1, "%s: no skill shot" % key
    print("rules: lanes & bonus X, lane change, drop bank & reset, lock & multiball, jackpot, missions, extra ball, "
          "wizard mode, kickback, plunger & ball save, tilt, bonus count, game over, skill shots")
    # 6. the controls
    c = Controls(False)
    c.feed("z", "press", 0.0)
    a1 = c.sample(0.1)[0]
    a2 = c.sample(0.5)[0]
    c.feed("right", "press", 1.0)
    c.feed("z", "press", 1.0)
    both = c.sample(1.05)
    assert a1 and not a2 and both[0] and both[1], "classic flippers %s %s %s" % (a1, a2, both)
    c.feed(" ", "press", 2.0)
    assert c.sample(2.3)[2] and not c.sample(2.8)[2], "classic plunger"
    k = Controls(True)
    k.feed("left", "press", 0.0)
    a = k.sample(1.5)[0]
    k.feed("left", "release", 1.6)
    assert a and not k.sample(1.61)[0], "kitty flipper"
    k.feed("up", "press", 2.0)
    assert k.sample(2.01)[3] == "up" and k.sample(2.02)[3] is None, "nudge edge"
    print("controls: classic flips & plunger window, both flippers at once, kitty releases, nudge edge")
    # 7. whole games by the autopilot on every table
    mb = 0
    for key in ORDER:
        tot = {}
        scores = []
        secs = 0.0
        for seed in range(11, 17):
            g = run_bot(key, limit=1200, seed=seed)
            assert g.over, "%s: the game did not end in 1200 s" % key
            scores.append(g.score)
            secs += g.clock
            for k_, v_ in g.stats.items():
                tot[k_] = tot.get(k_, 0) + v_
        assert tot["ramps"] and tot["scoops"] and tot["banks"] and tot["locks"] and tot["missions"], "%s: %s" % (key, tot)
        mb += tot["multiballs"]
        print("games: %-15s 6 games, %3.0f s each, best %11s; ramps %d, orbits %d, banks %d, locks %d, missions %d, "
              "multiballs %d, jackpots %d, skill shots %d, kickbacks %d, saves %d, ball searches %d" % (
                  THEMES[key]["name"], secs / 6, fmt(max(scores)), tot["ramps"], tot["orbits"], tot["banks"],
                  tot["locks"], tot["missions"], tot["multiballs"], tot["jackpots"], tot["skill"], tot["kicks"],
                  tot["saves"], tot["searches"]))
    assert mb, "no multiball in 18 games"
    # 8. rendering at every size
    n = 0
    timing = []
    for cols, rows in ((60, 22), (80, 24), (100, 32), (120, 40), (240, 70)):
        tr = te = 0.0
        frames = 0
        for key in ORDER:
            g = Game(key, seed=3, quiet=True)
            bot = Bot(g, seed=3)
            for i in range(int(14 / DT)):
                g.step(bot())
            g.say("JACKPOT", "1,000,000")
            for state in range(4):
                if state == 1:
                    g.msgs = []
                if state == 2:
                    g.tilted = True
                if state == 3:
                    g.tilted = False
                    g.state, g.bonus_show = "bonus", [12000, 3, 1]
                a = time.time()
                cv = render(g, cols, rows)
                b = time.time()
                cv.emit(True)
                c_ = time.time()
                if state == 1:
                    tr += b - a
                    te += c_ - b
                    frames += 1
                n += 1
            overlay(cv, help_lines(True))
            g.over = True
            render_over(g, cv, True)
            cv.emit(True)
        timing.append((cols, rows, tr / frames * 1000, te / frames * 1000))
    d = TitleDemo()
    for cols, rows in ((60, 22), (120, 40), (24, 8), (40, 12), (60, 30)):
        render_menu(d, cols, rows, 0, 2, 0.05, False, True).emit(True) if rows >= 20 else d.scene(cols, rows, 0.05)
        n += 1
    for _ in range(200):
        d.scene(30, 9, 0.1)
    print("rendering: %d frames at 60x22, 80x24, 100x32, 120x40, 240x70 (+ title, preview, overlays)" % n)
    for cols, rows, r_, e_ in timing:
        print("  %3dx%-3d render %5.1f ms  emit %5.1f ms  = %5.1f ms per frame (%3.0f fps)" % (
            cols, rows, r_, e_, r_ + e_, 1000 / max(0.1, r_ + e_)))
    # 9. auto mode: the real game at x8; pause, speed and stop work; no score kept
    run = AutoRun("belfry", sound=False, seed=31)
    assert not run.g.demo
    run.key(" ")
    snap = (run.g.clock, run.g.score)
    for _ in range(30):
        run.frame(1 / 30, 70, 22, draw=False)
    assert (run.g.clock, run.g.score) == snap, "auto mode ran on while paused"
    run.key(" ")
    for _ in range(5):
        run.key("+")
    assert run.auto.speed == 8.0
    secs = 20
    for i in range(secs * 30):
        run.frame(1 / 30, 70 + i % 3 * 25, 22 + i % 2 * 10, draw=i % 30 == 0)
    assert run.key("esc") == "stop"
    print("auto mode: %d s at x8, game %d, ball %d, %s points, nothing recorded" % (
        secs, run.rounds, run.g.ball_no, fmt(run.g.score)))
    # 10. simulation speed
    g = Game("forge", seed=2, quiet=True)
    bot = Bot(g, seed=2)
    a = time.time()
    for _ in range(3000):
        g.step(bot())
    print("simulation: %.0f us per physics step (1/120 s) with the autopilot" % ((time.time() - a) / 3000 * 1e6))
    print("Self-test ok (%.1f s)" % (time.time() - t0))


def screenshot(cols=100, rows=32):
    """README picture: real play on the Moonbell Belfry by the auto-mode pilot (seed 3), 108 s in: three-ball
    multiball with one ball riding the bell-rope ramp for the jackpot. Quiet (no sound), no score written; the
    HIGH line shows this run instead of a local record."""
    g = Game("belfry", quiet=True, seed=3)
    g.hi = 0
    bot = Bot(g, seed=3)
    for _ in range(int(round(108.1 / DT))):
        g.step(bot())
    return render(g, cols, rows)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--practice" in sys.argv:
        print(repr({_k: practice(_k) for _k in ORDER}))
    elif "--auto" in sys.argv:
        with KeyTerminal() as _term:
            run_auto(_term, ORDER[0])
    else:
        main()
