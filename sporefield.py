#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""SPOREFIELD - stop the sporeworm before it reaches the roots.

A glowing night meadow seen from above. A long sporeworm winds down through a field of toadstools, turning at
every cap and every edge. You are a small beetle at the bottom of the meadow and you spit sap upward: every hit
splits the worm in two and the hit segment turns into a toadstool. Jitterlegs hop through your corner, plumbugs
fall and leave caps behind, gloam moths poison the caps they brush, puffballs shed spores and burrowgrubs pop out
of the ground. Glowing seeds give short powers: double sap, piercing sap, slow time, bombs and a shell.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
"""
import math
import random
import sys
import time

from arcadekit import (AUTO_LABEL, PAUSE_LINES, AutoMode, Canvas, HeldKeys, KeyTerminal, clamp, footer, load_scores,
                       mix, overlay, shade, shared_key, submit, title_screen)
from arcadesound import Sound

GAME = "sporefield"
GW, GH = 30, 32          # the meadow in cells
ZONE = 26                # rows ZONE .. GH-1: the beetle's corner (the roots)
DT = 1 / 60              # fixed simulation step
EXTRA_LIFE = 12000

DIFFS = [
    dict(name="Easy", lives=4, speed=0.82, spawn=1.35, caps=30, desc="a calm meadow, 4 lives"),
    dict(name="Normal", lives=3, speed=1.0, spawn=1.0, caps=36, desc="the worm means it"),
    dict(name="Hard", lives=3, speed=1.22, spawn=0.72, caps=44, desc="fast, crowded, hungry"),
]

# one palette per wave: the night changes colour as the worms keep coming
PALETTES = [
    dict(name="Moonmoss", ground=(12, 22, 22), ground2=(16, 30, 27), moss=(26, 48, 36), dew=(70, 130, 104),
         zone=(22, 30, 50), cap=(232, 84, 72), spot=(255, 226, 206), stem=(214, 204, 176), worm=(126, 214, 92),
         worm2=(84, 168, 70), head=(250, 222, 84), poison=(186, 92, 255)),
    dict(name="Emberleaf", ground=(26, 15, 12), ground2=(34, 21, 15), moss=(58, 34, 18), dew=(140, 92, 44),
         zone=(40, 20, 30), cap=(250, 172, 60), spot=(255, 240, 200), stem=(230, 214, 180), worm=(224, 92, 72),
         worm2=(172, 62, 52), head=(255, 236, 140), poison=(110, 240, 210)),
    dict(name="Frostfern", ground=(10, 18, 30), ground2=(14, 24, 40), moss=(24, 40, 64), dew=(100, 150, 200),
         zone=(18, 22, 54), cap=(120, 200, 255), spot=(240, 250, 255), stem=(200, 214, 232), worm=(206, 236, 250),
         worm2=(150, 188, 226), head=(255, 140, 196), poison=(255, 120, 80)),
    dict(name="Duskbloom", ground=(24, 12, 28), ground2=(32, 16, 38), moss=(52, 26, 60), dew=(140, 84, 160),
         zone=(30, 14, 50), cap=(255, 110, 180), spot=(255, 232, 245), stem=(230, 200, 220), worm=(150, 230, 120),
         worm2=(100, 180, 90), head=(255, 204, 90), poison=(90, 200, 255)),
    dict(name="Glowshade", ground=(6, 20, 16), ground2=(8, 28, 22), moss=(14, 48, 32), dew=(60, 170, 116),
         zone=(10, 26, 40), cap=(190, 255, 110), spot=(240, 255, 220), stem=(200, 230, 200), worm=(255, 132, 80),
         worm2=(208, 92, 60), head=(255, 240, 120), poison=(255, 90, 200)),
    dict(name="Amberroot", ground=(22, 20, 10), ground2=(30, 27, 14), moss=(52, 46, 20), dew=(140, 128, 60),
         zone=(32, 24, 36), cap=(206, 122, 255), spot=(250, 232, 255), stem=(226, 214, 190), worm=(250, 200, 60),
         worm2=(208, 150, 40), head=(255, 110, 90), poison=(90, 255, 200)),
    dict(name="Tidepool", ground=(8, 20, 26), ground2=(10, 28, 34), moss=(16, 46, 54), dew=(70, 166, 176),
         zone=(14, 22, 46), cap=(255, 140, 110), spot=(255, 235, 220), stem=(220, 220, 200), worm=(100, 230, 220),
         worm2=(60, 170, 170), head=(255, 230, 110), poison=(200, 110, 255)),
    dict(name="Ashlight", ground=(18, 18, 22), ground2=(24, 24, 30), moss=(40, 40, 48), dew=(120, 120, 140),
         zone=(24, 20, 40), cap=(240, 232, 214), spot=(255, 96, 86), stem=(200, 196, 186), worm=(255, 100, 140),
         worm2=(200, 70, 110), head=(140, 240, 255), poison=(170, 255, 80)),
]

SHELL = (255, 200, 70)         # the beetle: gold shell, dark head, green sap
SHELL_D = (176, 118, 36)
SHELL_L = (255, 238, 160)
BEETLE_HEAD = (110, 70, 44)
SAP = (190, 255, 120)
PIERCE_C = (120, 240, 255)
BOMB_C = (255, 150, 50)
HUD_BG = (12, 14, 24)
HUD_LABEL = (130, 140, 170)
HUD_VALUE = (238, 240, 248)
GOLD = (250, 214, 120)

# powers carried by the glowing seeds: (name, colour, seconds; bombs count charges)
POWERS = {
    "double": ("DOUBLE", (150, 255, 110), 12.0),
    "pierce": ("PIERCE", (110, 236, 255), 12.0),
    "slow": ("SLOW", (150, 160, 255), 8.0),
    "bomb": ("BOMBS", (255, 160, 60), 4),
    "shell": ("SHELL", (255, 226, 110), 20.0),
}
CRITTERS = ("jitterleg", "plumbug", "gloammoth", "puffball", "burrowgrub")
SPAWN_EVERY = {"jitterleg": (4, 8), "plumbug": (2, 4), "gloammoth": (11, 18), "puffball": (14, 22),
               "burrowgrub": (9, 16)}
CRITTER_SCORE = {"plumbug": 200, "gloammoth": 1000, "puffball": 400, "burrowgrub": 500}
CRITTER_HP = {"jitterleg": 1, "plumbug": 2, "gloammoth": 1, "puffball": 3, "burrowgrub": 1}
CRITTER_BOX = {"jitterleg": (0.8, 0.45), "plumbug": (0.45, 0.45), "gloammoth": (0.9, 0.45),
               "puffball": (1.0, 0.9), "burrowgrub": (0.45, 0.45)}

SND = Sound(GAME, {
    "shot": [dict(w="square", f=1568, f2=988, d=0.03, v=0.13, duty=0.25)],
    "bombshot": [dict(w="square", f=392, f2=784, d=0.07, v=0.24, duty=0.5)],
    "cap": [dict(w="noise", f=1900, f2=700, d=0.025, v=0.12), dict(w="tri", f=247, d=0.03, v=0.16, at=0)],
    "cappop": [dict(w="noise", f=2600, f2=500, d=0.07, v=0.22), dict(w="tri", f=349, f2=175, d=0.08, v=0.28, at=0)],
    "segment": [dict(w="tri", f=784, f2=392, d=0.06, v=0.36), dict(w="noise", f=3200, f2=900, d=0.04, v=0.1, at=0)],
    "head": [dict(w="square", f=698, d=0.035, v=0.26, duty=0.25), dict(w="square", f=1047, d=0.035, v=0.26, duty=0.25),
             dict(w="tri", f=1397, d=0.12, v=0.36)],
    "spider": [dict(w="square", f=f, d=0.028, v=0.12, duty=0.125) for f in (932, 698, 1047, 740, 1175)],
    "critter": [dict(w="noise", f=4200, f2=300, d=0.15, v=0.3),
                dict(w="square", f=587, f2=147, d=0.16, v=0.22, duty=0.25, at=0)],
    "bigcritter": [dict(w="square", f=523, d=0.05, v=0.26, duty=0.25), dict(w="square", f=784, d=0.05, v=0.26, duty=0.25),
                   dict(w="tri", f=1568, f2=1046, d=0.2, v=0.34, vib=(10, 0.3)),
                   dict(w="noise", f=5000, f2=500, d=0.2, v=0.14, at=0)],
    "moth": [dict(w="sine", f=1180, f2=1560, d=0.22, v=0.14, vib=(16, 0.9), r="lin")],
    "plumbug": [dict(w="tri", f=1320, f2=330, d=0.28, v=0.18, r="lin")],
    "puff": [dict(w="noise", f=700, f2=250, d=0.14, v=0.12, r="lin")],
    "grub": [dict(w="noise", f=110, d=0.3, v=0.28, r="lin"), dict(w="tri", f=82, f2=55, d=0.3, v=0.3, at=0)],
    "seed": [dict(w="sine", f=1760, d=0.05, v=0.2), dict(w="sine", f=2349, d=0.09, v=0.2)],
    "power": [dict(w="tri", f=f, d=0.045, v=0.34) for f in (523, 659, 784, 1047)] +
             [dict(w="square", f=1319, d=0.16, v=0.24, duty=0.125, vib=(9, 0.25), r="lin")],
    "bomb": [dict(w="noise", f=1400, f2=60, d=0.4, v=0.5, r="lin"), dict(w="square", f=110, f2=40, d=0.35, v=0.3, at=0)],
    "shellhit": [dict(w="tri", f=1047, f2=262, d=0.18, v=0.4), dict(w="noise", f=3000, d=0.08, v=0.15, at=0)],
    "death": [dict(w="square", f=880, f2=440, d=0.09, v=0.3, duty=0.25), dict(w="square", f=660, f2=330, d=0.09, v=0.3, duty=0.25),
              dict(w="square", f=440, f2=110, d=0.35, v=0.32, duty=0.25, vib=(12, 0.6)),
              dict(w="noise", f=2000, f2=80, d=0.6, v=0.3, at=0.05, r="lin")],
    "wave": [dict(w="square", f=f, d=0.06, v=0.26, duty=0.25) for f in (392, 523, 659, 784)] +
            [dict(w="tri", f=1047, d=0.12, v=0.36), dict(w="tri", f=784, d=0.06, v=0.3), dict(w="tri", f=1047, d=0.3, v=0.38, vib=(6, 0.2))],
    "extra": [dict(w="square", f=f, d=0.07, v=0.24, duty=0.125) for f in (1047, 1319, 1568, 2093, 1568, 2093)],
    "tick": [dict(w="tri", f=1397, d=0.022, v=0.2)],
    "autofire": [dict(w="tri", f=880, d=0.03, v=0.2), dict(w="tri", f=1175, d=0.04, v=0.2)],
    "menu": [dict(w="tri", f=660, d=0.025, v=0.2)],
    "start": [dict(w="square", f=523, d=0.05, v=0.28, duty=0.25), dict(w="square", f=698, d=0.05, v=0.28, duty=0.25),
              dict(w="square", f=1047, d=0.14, v=0.3, duty=0.25)],
    "pause": [dict(w="tri", f=523, f2=392, d=0.07, v=0.22)],
    "sound_on": [dict(w="tri", f=440, d=0.06, v=0.35), dict(w="tri", f=880, d=0.12, v=0.35)],
    "over": [dict(w="tri", f=440, d=0.15, v=0.38), dict(w="tri", f=392, d=0.15, v=0.38), dict(w="tri", f=330, d=0.15, v=0.38),
             dict(w="tri", f=262, f2=196, d=0.6, v=0.4, r="lin")],
})


def help_lines(kitty=True):
    return [
        "SPOREFIELD - keys",
        "",
        "Arrows / WASD        move (diagonals too)",
        "Space                spit sap - hold it to keep firing",
        "F                    auto-fire on / off" + ("" if kitty else " (handy here)"),
        "",
        "Every hit splits the sporeworm; the hit segment",
        "becomes a toadstool. Heads 100, segments 10.",
        "Toadstools take four hits. Glowing seeds give",
        "double sap, piercing sap, slow time, bombs or a",
        "shell. Extra beetle every %d points." % EXTRA_LIFE,
        "",
        "Esc / P              pause menu (Q quit, M sound)",
        "?                    this help",
        "",
        "Auto mode: the game plays itself (Space pause,",
        "+/- speed, Esc stop) on the difficulty chosen last.",
    ]


def sgn(v):
    return 1 if v > 0 else -1 if v < 0 else 0


# =============================================================================================
# The meadow
# =============================================================================================
class Chain:
    """One piece of sporeworm. segs: [x, y, prev_x, prev_y]; the first one is the head, the rest follow it."""
    __slots__ = ("segs", "dx", "vdir", "dive", "iv", "t")

    def __init__(self, segs, dx, vdir, dive, iv, t=0.0):
        self.segs, self.dx, self.vdir, self.dive, self.iv, self.t = segs, dx, vdir, dive, iv, t


class Critter:
    __slots__ = ("kind", "x", "y", "vx", "vy", "y0", "hp", "t", "tt", "phase", "flash", "cell")

    def __init__(self, kind, x, y, vx=0.0, vy=0.0):
        self.kind, self.x, self.y, self.vx, self.vy = kind, x, y, vx, vy
        self.y0 = y
        self.hp = CRITTER_HP[kind]
        self.t = 0.0           # age
        self.tt = 0.0          # a kind's own timer
        self.phase = ""
        self.flash = 0.0
        self.cell = None


class Game:
    def __init__(self, diff=1, demo=False, seed=None):
        self.rng = random.Random(seed)
        self.diff = diff
        self.D = DIFFS[diff]
        self.demo = demo
        self.lives = self.D["lives"]
        self.score = 0
        self.next_life = EXTRA_LIFE
        self.wave = 1
        self.t = 0.0
        self.acc = 0.0
        self.caps = {}          # (x, y) -> [hp 1..4, poisoned]
        self.capver = 0
        self.flash = {}         # (x, y) -> until
        self.chains = []
        self.bullets = []       # [x, y, kind, hits left]
        self.critters = []
        self.seeds = []         # [x, y, kind, landed_at or None]
        self.parts = []         # [x, y, vx, vy, life, max life, colour]
        self.pops = []          # [x, y, text, until, colour]
        self.px, self.py = GW / 2, GH - 1.5
        self.power = {}         # name -> until
        self.bombs = 0
        self.shell = False
        self.invuln = 0.0
        self.cool = 0.0
        self.autofire = False
        self.inp = (0, 0, False)
        self.tap = False
        self.state = "play"
        self.st = 0.0
        self.restore_q = []
        self.banner = None      # (text, until)
        self.shake = 0.0
        self.paused = self.help = False
        self.segmap = None
        self.timers = {k: self.rng.uniform(*SPAWN_EVERY[k]) * self.D["spawn"] for k in CRITTERS}
        self.stats = {}
        self.seed_meadow()
        self.start_wave()

    # --- small helpers ---------------------------------------------------------------------------------
    def sfx(self, name, vol=1.0, gap=0.04):
        if not self.demo:
            SND.play(name, vol, gap)

    def count(self, key, n=1):
        self.stats[key] = self.stats.get(key, 0) + n

    @property
    def pal(self):
        return PALETTES[(self.wave - 1) % len(PALETTES)]

    def add(self, pts, x=None, y=None, color=None):
        self.score += pts
        if x is not None:
            self.pops.append([x, y, "%d" % pts, self.t + 0.8, color or (255, 255, 230)])
        while self.score >= self.next_life:
            self.next_life += EXTRA_LIFE
            self.lives += 1
            self.sfx("extra")
            self.banner = ("EXTRA BEETLE!", self.t + 1.6)
            self.count("extra_life")

    def burst(self, x, y, color, n=10, speed=6.0, life=0.5):
        rnd = self.rng
        for _ in range(n):
            a = rnd.uniform(0, math.tau)
            s = rnd.uniform(0.3, 1.0) * speed
            lf = rnd.uniform(0.5, 1.0) * life
            self.parts.append([x, y, math.cos(a) * s, math.sin(a) * s, lf, lf, color])
        if len(self.parts) > 500:
            del self.parts[:len(self.parts) - 500]

    def setcap(self, x, y, hp=4, poison=False):
        if 0 <= x < GW and 0 <= y < GH:
            self.caps[(x, y)] = [hp, poison]
            self.capver += 1
            return True
        return False

    def seed_meadow(self):
        rnd = self.rng
        n = 0
        while n < self.D["caps"]:
            x, y = rnd.randrange(GW), rnd.randrange(1, GH - 1)
            if y >= ZONE and rnd.random() < 0.7:
                continue
            if (x, y) not in self.caps:
                self.setcap(x, y, 4)
                n += 1

    def worm_iv(self):
        return max(0.042, 0.108 / self.D["speed"] / (1 + 0.05 * (self.wave - 1)))

    def start_wave(self):
        rnd = self.rng
        total = min(17, 10 + self.wave)
        heads = min(self.wave // 2, 6)          # extra lone heads: 1 from wave 2, 2 from wave 4, ... 6 from 12
        iv = self.worm_iv()
        self.chains = []
        x = rnd.randrange(4, GW - 4)
        n = total - heads
        self.chains.append(Chain([[x, -1 - i, x, -1 - i] for i in range(n)], rnd.choice((-1, 1)), 1, False, iv))
        for h in range(heads):
            hx = rnd.randrange(GW)
            hy = -1 - rnd.randrange(0, 8)
            self.chains.append(Chain([[hx, hy, hx, hy]], rnd.choice((-1, 1)), 1, False, iv * 0.92))
        self.zone_reached = False
        self.trickle_left = 3 + self.wave // 2
        self.trickle_t = 0.0
        self.segmap = None
        self.banner = ("WAVE %d  -  %s" % (self.wave, self.pal["name"].upper()), self.t + 2.0)

    def segments(self):
        """(centre x, centre y, chain, index) of every segment, smoothly between its last two cells."""
        out = []
        for ch in self.chains:
            f = clamp(ch.t / ch.iv, 0.0, 1.0)
            for i, s in enumerate(ch.segs):
                out.append((s[2] + (s[0] - s[2]) * f + 0.5, s[3] + (s[1] - s[3]) * f + 0.5, ch, i))
        return out

    # --- the worm ----------------------------------------------------------------------------------------
    def head_next(self, ch):
        x, y = ch.segs[0][0], ch.segs[0][1]
        if y < 0:                               # still coming in from above the meadow
            return x, y + 1
        if ch.dive:
            if y < GH - 1:
                return x, y + 1
            ch.dive = False
            ch.vdir = -1
        nx = x + ch.dx
        cap = self.caps.get((nx, y))
        if 0 <= nx < GW and cap is None:
            return nx, y
        if cap is not None and cap[1]:          # a poisoned cap: straight down to the roots
            ch.dive = True
            self.count("dive")
        ch.dx = -ch.dx
        ny = y + ch.vdir
        if ny > GH - 1:
            ch.vdir = -1
            ny = y - 1
        elif ch.vdir < 0 and ny < ZONE:
            ch.vdir = 1
            ny = y + 1
        return x, ny

    def step_chain(self, ch):
        nx, ny = self.head_next(ch)
        segs = ch.segs
        for i in range(len(segs) - 1, 0, -1):
            s, a = segs[i], segs[i - 1]
            s[2], s[3] = s[0], s[1]
            s[0], s[1] = a[0], a[1]
        h = segs[0]
        h[2], h[3] = h[0], h[1]
        h[0], h[1] = nx, ny
        if ny >= ZONE:
            self.zone_reached = True
        self.segmap = None

    def seg_at(self):
        if self.segmap is None:
            m = {}
            for ch in self.chains:
                for i, s in enumerate(ch.segs):
                    m[(s[0], s[1])] = (ch, i)
            self.segmap = m
        return self.segmap

    def kill_segment(self, ch, i):
        """Split the chain at segment i; the segment becomes a toadstool."""
        seg = ch.segs[i]
        x, y = seg[0], seg[1]
        f = clamp(ch.t / ch.iv, 0.0, 1.0)
        cx, cy = seg[2] + (x - seg[2]) * f + 0.5, seg[3] + (y - seg[3]) * f + 0.5
        pal = self.pal
        if i == 0:
            self.add(100, cx, cy - 0.6, pal["head"])
            self.sfx("head")
            self.burst(cx, cy, pal["head"], 14, 7.0)
            self.count("heads")
        else:
            self.add(10)
            self.sfx("segment", gap=0.02)
            self.burst(cx, cy, pal["worm"], 8, 5.0)
            self.count("segments")
        if 0 <= x < GW and 0 <= y < GH and (x, y) not in self.caps:
            self.setcap(x, y, 4)
            self.count("caps_made")
        if ch in self.chains:
            self.chains.remove(ch)
        a, b = ch.segs[:i], ch.segs[i + 1:]
        if a:
            self.chains.append(Chain(a, ch.dx, ch.vdir, ch.dive, ch.iv, ch.t))
        if b:
            d = sgn(x - b[0][0]) or ch.dx
            self.chains.append(Chain(b, d, ch.vdir, False, ch.iv, ch.t))
        if a and b:
            self.count("splits")
        self.segmap = None

    # --- creatures ----------------------------------------------------------------------------------------
    def spawn(self, kind):
        rnd = self.rng
        sp = self.D["speed"] * (1 + 0.04 * min(self.wave, 10))
        if kind == "jitterleg":
            left = rnd.random() < 0.5
            c = Critter(kind, -1.0 if left else GW + 1.0, rnd.uniform(ZONE - 1, GH - 1),
                        (1 if left else -1) * rnd.uniform(3.5, 5.0) * sp, rnd.choice((-1, 1)) * 7.0)
            self.sfx("spider", 0.7)
        elif kind == "plumbug":
            c = Critter(kind, rnd.randrange(GW) + 0.5, -0.5, 0.0, rnd.uniform(9, 12) * sp)
            c.cell = -1
            self.sfx("plumbug", 0.7)
        elif kind == "gloammoth":
            left = rnd.random() < 0.5
            c = Critter(kind, -1.5 if left else GW + 1.5, rnd.randrange(3, ZONE - 5) + 0.5,
                        (1 if left else -1) * rnd.uniform(5.5, 7.0) * sp)
            self.sfx("moth", 0.8)
        elif kind == "puffball":
            left = rnd.random() < 0.5
            c = Critter(kind, -1.5 if left else GW + 1.5, rnd.uniform(4, ZONE - 9),
                        (1 if left else -1) * rnd.uniform(1.6, 2.2) * sp)
            c.tt = 0.8
            self.sfx("puff")
        else:  # burrowgrub
            for _ in range(20):
                x, y = rnd.randrange(GW), rnd.randrange(ZONE, GH)
                if abs(x + 0.5 - self.px) + abs(y + 0.5 - self.py) > 5 and (x, y) not in self.caps:
                    break
            c = Critter(kind, x + 0.5, y + 0.5)
            c.phase, c.tt = "rumble", 1.1
            self.sfx("grub", 0.8)
        self.critters.append(c)
        self.count("spawn_" + kind)
        return c

    def update_spawns(self, dt):
        if self.state != "play":
            return
        k = self.D["spawn"]
        have = {c.kind for c in self.critters}
        rnd = self.rng
        tm = self.timers
        for kind in CRITTERS:
            if kind in have:
                continue
            if kind == "gloammoth" and self.wave < 2 or kind == "puffball" and self.wave < 3:
                continue
            if kind == "plumbug":
                low = sum(1 for (x, y) in self.caps if y >= ZONE - 5)
                if low >= min(10, 4 + self.wave // 2):
                    continue
            tm[kind] -= dt
            if tm[kind] <= 0:
                self.spawn(kind)
                tm[kind] = rnd.uniform(*SPAWN_EVERY[kind]) * k

    def hurt_critter(self, c, dmg=1):
        c.hp -= dmg
        c.flash = 0.12
        if c.hp > 0:
            if c.kind == "plumbug":
                c.vy *= 2.2
            self.sfx("cap")
            return False
        self.critters.remove(c)
        if c.kind == "jitterleg":
            d = math.hypot(c.x - self.px, c.y - self.py)
            pts = 900 if d < 3 else 600 if d < 6 else 300
        else:
            pts = CRITTER_SCORE[c.kind]
        self.add(pts, c.x, c.y - 0.8, (255, 236, 150))
        self.sfx("bigcritter" if pts >= 600 else "critter")
        col = {"jitterleg": (240, 80, 140), "plumbug": (255, 160, 50), "gloammoth": (170, 230, 255),
               "puffball": (210, 230, 160), "burrowgrub": (240, 220, 190)}[c.kind]
        self.burst(c.x, c.y, col, 18, 8.0, 0.7)
        self.count("kill_" + c.kind)
        chance = {"gloammoth": 0.7, "puffball": 0.6}.get(c.kind, 0.4)
        if self.rng.random() < chance:
            self.drop_seed(c.x, c.y)
        return True

    def drop_seed(self, x, y, kind=None):
        kind = kind or self.rng.choice(list(POWERS))
        self.seeds.append([clamp(x, 0.5, GW - 0.5), clamp(y, 0.5, GH - 0.6), kind, None])
        self.sfx("seed")

    def give(self, kind):
        name, col, dur = POWERS[kind]
        if kind == "bomb":
            self.bombs += dur
        elif kind == "shell":
            self.shell = True
            self.power["shell"] = self.t + dur
        else:
            self.power[kind] = self.t + dur
        self.sfx("power")
        self.pops.append([self.px, self.py - 1.2, name, self.t + 1.0, col])
        self.burst(self.px, self.py, col, 16, 6.0)
        self.count("power_" + kind)

    def active(self, kind):
        return self.power.get(kind, 0) > self.t

    def update_critters(self, dt):
        rnd = self.rng
        for c in list(self.critters):
            c.t += dt
            c.flash = max(0.0, c.flash - dt)
            k = c.kind
            gone = False
            if k == "jitterleg":
                c.x += c.vx * dt
                c.y += c.vy * dt
                if c.y < ZONE - 2:
                    c.y, c.vy = ZONE - 2, abs(c.vy)
                elif c.y > GH - 0.5:
                    c.y, c.vy = GH - 0.5, -abs(c.vy)
                c.tt -= dt
                if c.tt <= 0:
                    c.tt = rnd.uniform(0.2, 0.6)
                    c.vy = rnd.choice((-1, 1)) * rnd.uniform(5, 10)
                cell = (int(c.x), int(c.y))
                if cell != c.cell:
                    c.cell = cell
                    if cell in self.caps and rnd.random() < 0.6:
                        del self.caps[cell]
                        self.capver += 1
                        self.burst(cell[0] + 0.5, cell[1] + 0.5, self.pal["cap"], 5, 3.0)
                        self.count("eaten")
                gone = c.x < -2.5 or c.x > GW + 2.5
            elif k == "plumbug":
                c.y += c.vy * dt
                r = int(c.y)
                if r != c.cell:
                    c.cell = r
                    if 1 <= r < GH - 2 and (int(c.x), r) not in self.caps and rnd.random() < 0.3:
                        self.setcap(int(c.x), r, 4)
                        self.count("plumbug_caps")
                gone = c.y > GH + 1
            elif k == "gloammoth":
                c.x += c.vx * dt
                c.y = c.y0 + math.sin(c.t * 4.5) * 0.45
                r = int(c.y)
                for xx in (int(c.x - 0.6), int(c.x + 0.6)):
                    cap = self.caps.get((xx, r))
                    if cap and not cap[1]:
                        cap[1] = True
                        self.capver += 1
                        self.count("poisoned")
                gone = c.x < -3 or c.x > GW + 3
            elif k == "puffball":
                c.x += c.vx * dt
                c.y0 = min(ZONE - 6.0, c.y0 + 0.25 * dt)
                c.y = c.y0 + math.sin(c.t * 1.3) * 1.4
                c.tt -= dt
                if c.tt <= 0 and 0 <= c.x < GW:
                    c.tt = rnd.uniform(0.9, 1.4)
                    x, y = int(c.x) + rnd.randint(-2, 2), int(c.y) + rnd.randint(-1, 2)
                    if 1 <= y < ZONE and 0 <= x < GW and (x, y) not in self.caps:
                        self.setcap(x, y, 4)
                        self.count("spores")
                        self.burst(x + 0.5, y + 0.5, (200, 230, 150), 6, 2.5, 0.6)
                        self.sfx("puff", 0.5, 0.2)
                gone = c.x < -3 or c.x > GW + 3
            else:  # burrowgrub
                c.tt -= dt
                if c.phase == "rumble":
                    if rnd.random() < 0.3:
                        self.parts.append([c.x + rnd.uniform(-0.6, 0.6), c.y + 0.3, rnd.uniform(-1, 1), -rnd.uniform(1, 3),
                                           0.4, 0.4, shade(self.pal["moss"], 2.2)])
                    if c.tt <= 0:
                        c.phase, c.tt = "out", 2.6
                        self.burst(c.x, c.y, shade(self.pal["moss"], 2.5), 10, 4.0)
                elif c.phase == "out":
                    dx, dy = self.px - c.x, self.py - c.y
                    d = math.hypot(dx, dy) or 1
                    sp = 3.4 * self.D["speed"]
                    nx, ny = c.x + dx / d * sp * dt, c.y + dy / d * sp * 0.6 * dt
                    if (int(nx), int(ny)) not in self.caps:
                        c.x, c.y = clamp(nx, 0.5, GW - 0.5), clamp(ny, ZONE + 0.5, GH - 0.5)
                    if c.tt <= 0:
                        c.phase, c.tt = "dig", 0.5
                elif c.tt <= 0:
                    cell = (int(c.x), int(c.y))
                    if cell not in self.caps and abs(c.x - self.px) + abs(c.y - self.py) > 1.5:
                        self.setcap(cell[0], cell[1], 3)   # a little mound where it went down
                    gone = True
            if gone and c in self.critters:
                self.critters.remove(c)

    # --- the beetle ----------------------------------------------------------------------------------------
    def blocked(self, x, y, ox, oy):
        """Would the beetle at (x, y) touch a cap it does not already touch at (ox, oy)?"""
        def cells(a, b):
            return {(int(a + dx), int(b + dy)) for dx in (-0.38, 0.38) for dy in (-0.38, 0.38)}
        old = cells(ox, oy)
        return any(c in self.caps and c not in old for c in cells(x, y))

    def update_player(self, dt):
        dx, dy, fire = self.inp
        sp = 12.0
        if dx and dy:
            sp *= 0.7071
        x0, y0 = self.px, self.py
        nx = clamp(self.px + dx * sp * dt, 0.5, GW - 0.5)
        if not self.blocked(nx, self.py, x0, y0):
            self.px = nx
        ny = clamp(self.py + dy * sp * dt, ZONE + 0.5, GH - 0.5)
        if not self.blocked(self.px, ny, x0, y0):
            self.py = ny
        self.cool -= dt
        want = fire or self.autofire or self.tap
        if want and self.cool <= 0 and not self.bullets:
            self.tap = False
            self.cool = 0.05
            y = self.py - 0.5
            if self.bombs > 0:
                self.bombs -= 1
                self.bullets.append([self.px, y, "bomb", 1])
                self.sfx("bombshot")
            else:
                kind = "pierce" if self.active("pierce") else "sap"
                hits = 5 if kind == "pierce" else 1
                if self.active("double"):
                    self.bullets.append([clamp(self.px - 0.45, 0.05, GW - 0.05), y, kind, hits])
                    self.bullets.append([clamp(self.px + 0.45, 0.05, GW - 0.05), y, kind, hits])
                else:
                    self.bullets.append([self.px, y, kind, hits])
                self.sfx("shot", gap=0.05)
            self.count("shots")

    def update_bullets(self, dt):
        for b in list(self.bullets):
            speed = 34.0 if b[2] == "bomb" else 56.0
            dist = speed * dt
            n = max(1, int(math.ceil(dist / 0.4)))
            for _ in range(n):
                b[1] -= dist / n
                if b[1] < 0:
                    self.bullets.remove(b)
                    break
                if self.bullet_hit(b):
                    if b in self.bullets:
                        self.bullets.remove(b)
                    break

    def bullet_hit(self, b):
        """Check one bullet position; returns True when the bullet is used up."""
        x, y = b[0], b[1]
        cell = (int(x), int(y))
        hit = None
        m = self.seg_at()
        if cell in m:
            hit = ("seg", m[cell])
        else:
            for c in self.critters:
                if c.kind == "burrowgrub" and c.phase != "out":
                    continue
                hw, hh = CRITTER_BOX[c.kind]
                if abs(x - c.x) < hw + 0.15 and abs(y - c.y) < hh + 0.3:
                    hit = ("crit", c)
                    break
            if hit is None and cell in self.caps:
                hit = ("cap", cell)
        if hit is None:
            return False
        if b[2] == "bomb":
            self.explode(x, y)
            return True
        what, obj = hit
        if what == "seg":
            ch, i = obj
            self.kill_segment(ch, i)
        elif what == "crit":
            self.hurt_critter(obj)
        else:
            self.hit_cap(cell)
        b[3] -= 1
        if b[2] == "pierce" and b[3] > 0:
            if what == "crit" and obj in self.critters:
                b[1] = obj.y - CRITTER_BOX[obj.kind][1] - 0.35   # carry on past it
            return False
        return True

    def hit_cap(self, cell, dmg=1):
        cap = self.caps.get(cell)
        if not cap:
            return
        cap[0] -= dmg
        self.capver += 1
        self.flash[cell] = self.t + 0.08
        if cap[0] <= 0:
            del self.caps[cell]
            self.add(5 if cap[1] else 1)
            self.sfx("cappop", gap=0.03)
            self.burst(cell[0] + 0.5, cell[1] + 0.5, self.pal["poison"] if cap[1] else self.pal["cap"], 8, 4.0)
            self.count("caps_cleared")
        else:
            self.sfx("cap", gap=0.03)
            self.burst(cell[0] + 0.5, cell[1] + 0.9, self.pal["stem"], 2, 2.0, 0.3)

    def explode(self, x, y, r=2.7):
        self.sfx("bomb")
        self.shake = 0.25
        self.count("bombs")
        for _ in range(60):
            hit = next(((ch, i) for sx, sy, ch, i in self.segments() if math.hypot(sx - x, sy - y) < r), None)
            if not hit:
                break
            self.kill_segment(*hit)
        for cell in [c for c in self.caps if math.hypot(c[0] + 0.5 - x, c[1] + 0.5 - y) < r]:
            self.hit_cap(cell, 4)
        for c in list(self.critters):
            if math.hypot(c.x - x, c.y - y) < r + 0.5 and c in self.critters:
                self.hurt_critter(c, 9)
        self.burst(x, y, BOMB_C, 40, 10.0, 0.7)
        self.burst(x, y, (255, 240, 180), 20, 5.0, 0.5)

    def update_seeds(self, dt):
        for s in list(self.seeds):
            if s[3] is None:
                s[1] += 7.0 * dt
                if s[1] >= GH - 0.6:
                    s[1] = GH - 0.6
                    s[3] = self.t
            elif self.t - s[3] > 7.0:
                self.seeds.remove(s)
                continue
            if abs(s[0] - self.px) < 0.9 and abs(s[1] - self.py) < 0.9:
                self.seeds.remove(s)
                self.give(s[2])

    def check_player(self):
        if self.invuln > 0:
            return
        x, y = self.px, self.py
        for sx, sy, ch, i in self.segments():
            if abs(sx - x) < 0.72 and abs(sy - y) < 0.72:
                return self.player_hit()
        for c in self.critters:
            if c.kind == "burrowgrub" and c.phase != "out":
                continue
            hw, hh = CRITTER_BOX[c.kind]
            if abs(c.x - x) < hw + 0.3 and abs(c.y - y) < hh + 0.3:
                return self.player_hit(c)

    def player_hit(self, critter=None):
        if self.shell:
            self.shell = False
            self.power.pop("shell", None)
            self.invuln = 1.6
            self.sfx("shellhit")
            self.burst(self.px, self.py, POWERS["shell"][1], 24, 7.0)
            self.count("shell_saves")
            return
        self.lives -= 1
        self.state, self.st = "dying", 0.0
        self.sfx("death")
        self.burst(self.px, self.py, SHELL, 40, 9.0, 0.9)
        self.burst(self.px, self.py, SAP, 20, 5.0, 0.7)
        self.bullets = []
        self.power = {}
        self.bombs = 0
        self.count("deaths")

    def respawn(self):
        self.chains, self.critters, self.seeds, self.bullets = [], [], [], []
        self.px, self.py = GW / 2, GH - 1.5
        self.invuln = 2.0
        self.state = "play"
        self.start_wave()

    # --- time ------------------------------------------------------------------------------------------------
    def update(self, dt):
        if self.paused:
            return
        self.acc += min(dt, 0.1)
        while self.acc >= DT:
            self.acc -= DT
            self.step(DT)

    def step(self, dt):
        self.t += dt
        for p in self.parts:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[2] *= 0.94
            p[3] *= 0.94
            p[4] -= dt
        self.parts = [p for p in self.parts if p[4] > 0]
        if self.pops and self.pops[0][3] < self.t:
            self.pops = [p for p in self.pops if p[3] > self.t]
        self.shake = max(0.0, self.shake - dt)
        if self.state == "over":
            return
        if self.state == "dying":
            self.st += dt
            if self.st >= 1.4:
                self.state, self.st = "restore", 0.0
                self.chains, self.critters, self.bullets = [], [], []
                self.restore_q = sorted((c for c, v in self.caps.items() if v[0] < 4 or v[1]),
                                        key=lambda c: (c[1], c[0]))
            return
        if self.state == "restore":
            self.st += dt
            while self.st >= 0.06:
                self.st -= 0.06
                if not self.restore_q:
                    if self.lives <= 0:
                        self.state = "over"
                    else:
                        self.respawn()
                    return
                cell = self.restore_q.pop(0)
                if cell in self.caps:
                    self.caps[cell] = [4, False]
                    self.capver += 1
                    self.add(5, cell[0] + 0.5, cell[1] - 0.3, (220, 255, 200))
                    self.burst(cell[0] + 0.5, cell[1] + 0.5, (230, 255, 210), 5, 2.5, 0.4)
                    self.sfx("tick", gap=0.03)
                    self.count("restored")
            return
        self.invuln = max(0.0, self.invuln - dt)
        wdt = dt * (0.45 if self.active("slow") else 1.0)
        self.update_player(dt)
        self.update_bullets(dt)
        for ch in list(self.chains):
            ch.t += wdt
            while ch.t >= ch.iv and ch in self.chains:
                ch.t -= ch.iv
                self.step_chain(ch)
        self.update_critters(wdt)
        self.update_seeds(dt)
        self.update_spawns(wdt)
        if self.zone_reached and self.trickle_left > 0 and self.chains:
            self.trickle_t += wdt
            if self.trickle_t >= max(2.5, 6.0 - self.wave * 0.3):
                self.trickle_t = 0.0
                self.trickle_left -= 1
                left = self.rng.random() < 0.5
                x = 0 if left else GW - 1
                y = self.rng.randrange(ZONE, GH)
                if abs(y + 0.5 - self.py) < 1.5 and abs(x + 0.5 - self.px) < 3:
                    y = ZONE if self.py > ZONE + 3 else GH - 1
                self.chains.append(Chain([[x, y, x, y]], 1 if left else -1, self.rng.choice((-1, 1)), False,
                                         self.worm_iv() * 0.85))
                self.segmap = None
                self.count("trickle")
        if self.shell and not self.active("shell"):
            self.shell = False
        self.check_player()
        if self.state == "play" and not self.chains:
            self.count("waves")
            self.sfx("wave")
            self.add(250 * self.wave)
            self.wave += 1
            self.start_wave()


# =============================================================================================
# The autopilot (title screen, launcher preview and the selftest)
# =============================================================================================
def bot_input(g):
    if g.state != "play":
        return (0, 0, False)
    x, y = g.px, g.py
    segs = g.segments()
    rx = ry = 0.0
    for sx, sy, ch, i in segs:
        d = math.hypot(sx - x, sy - y)
        if d < 3.6:
            w = (3.6 - d) / 3.6
            rx += (x - sx) / (d + 0.01) * w * 2
            ry += (y - sy) / (d + 0.01) * w * 2
    for c in g.critters:
        if c.kind == "burrowgrub" and c.phase == "rumble":
            continue
        d = math.hypot(c.x - x, c.y - y)
        if d < 4.0:
            w = (4.0 - d) / 4.0
            rx += (x - c.x) / (d + 0.01) * w * 2.5
            ry += (y - c.y) / (d + 0.01) * w * 2.5
    if abs(rx) + abs(ry) > 0.5:
        dx = sgn(rx) if abs(rx) > 0.25 else 0
        dy = sgn(ry) if abs(ry) > 0.25 else 0
        if x < 1.2 and dx < 0 or x > GW - 1.2 and dx > 0:
            dx = 0
        return (dx, dy, True)
    tx, ty = x, GH - 1.5
    seed = next((s for s in g.seeds if s[3] is not None and abs(s[0] - x) < 8), None)
    if seed:
        tx, ty = seed[0], seed[1]
    elif segs:
        low = max(segs, key=lambda s: s[1] + (4 if s[3] == 0 else 0))
        tx = low[0]
    elif g.critters:
        tx = g.critters[0].x
    dx = sgn(tx - x) if abs(tx - x) > 0.3 else 0
    dy = sgn(ty - y) if abs(ty - y) > 0.4 else 0
    return (dx, dy, True)


def predict_head(g, ch, n):
    """Where a chain's head will be after n more steps (the worm's turning rules, without changing anything)."""
    x, y = ch.segs[0][0], ch.segs[0][1]
    dx, vdir, dive = ch.dx, ch.vdir, ch.dive
    for _ in range(n):
        if y < 0:
            y += 1
            continue
        if dive:
            if y < GH - 1:
                y += 1
                continue
            dive, vdir = False, -1
        nx = x + dx
        cap = g.caps.get((nx, y))
        if 0 <= nx < GW and cap is None:
            x = nx
            continue
        if cap is not None and cap[1]:
            dive = True
        dx = -dx
        ny = y + vdir
        if ny > GH - 1:
            vdir, ny = -1, y - 1
        elif vdir < 0 and ny < ZONE:
            vdir, ny = 1, y + 1
        y = ny
    return x, y


def pilot_input(g):
    """Auto mode's beetle: dodge like the title autopilot, but aim. The target is the worm piece that is lowest
    (heads first, they lead the worm into the corner) and the beetle leads its shot: it moves under the cell
    where that head will be when the sap gets there. Seeds lying close by are picked up when it is calm."""
    if g.state != "play":
        return (0, 0, False)
    x, y = g.px, g.py
    dodge = bot_input(g)
    segs = g.segments()
    near = any(math.hypot(sx - x, sy - y) < 3.6 for sx, sy, _, _ in segs) or any(
        math.hypot(c.x - x, c.y - y) < 4.0 for c in g.critters if not (c.kind == "burrowgrub" and c.phase == "rumble"))
    if near:
        return dodge
    tx, ty = x, GH - 1.5
    seed = next((s for s in g.seeds if s[3] is not None and abs(s[0] - x) < 6), None)
    if seed and not any(sy > ZONE - 3 for sx, sy, _, _ in segs):
        tx, ty = seed[0], seed[1]
    elif g.chains:
        ch = max(g.chains, key=lambda c: c.segs[0][1] + 3 * (c.segs[0][1] >= ZONE) + 0.05 * len(c.segs))
        hx, hy = ch.segs[0][0], ch.segs[0][1]
        flight = max(0.0, (y - hy - 0.5)) / 56.0 + 0.05
        steps = int((flight + max(0.0, abs(hx + 0.5 - x) - 0.5) / 12.0) / ch.iv * (0.45 if g.active("slow") else 1.0))
        ax, ay = predict_head(g, ch, steps)
        tx = ax + 0.5
        if ay >= ZONE and ay > y - 2.5:       # it is coming along the bottom row: keep out of its way, above it
            ty = ZONE + 0.5
    elif g.critters:
        tx = g.critters[0].x
    dx = sgn(tx - x) if abs(tx - x) > 0.3 else 0
    dy = sgn(ty - y) if abs(ty - y) > 0.4 else 0
    return (dx, dy, True)


class Pilot:
    """Auto mode's player: pilot_input, looked at again only every THINK seconds (a human's reaction time);
    in between the beetle keeps doing what it did."""
    THINK = 0.12

    def __init__(self):
        self.t = self.next = 0.0
        self.inp = (0, 0, False)

    def __call__(self, g, dt):
        self.t += dt
        if self.t >= self.next:
            self.next = self.t + self.THINK
            self.inp = pilot_input(g)
        return self.inp


# =============================================================================================
# Drawing
# =============================================================================================
_SPR = {}


def sprite(key, w, h, fn):
    """A small picture w x h pixels from fn(u, v) -> colour or None, with u, v running -1..1 over the box."""
    s = _SPR.get(key)
    if s is None:
        s = []
        for j in range(h):
            v = (j + 0.5) / h * 2 - 1
            for i in range(w):
                c = fn((i + 0.5) / w * 2 - 1, v)
                if c is not None:
                    s.append((i, j, c))
        _SPR[key] = s
    return s


def blit(cv, spr, x, y, clip):
    x0, y0, x1, y1 = clip
    px = cv.px
    for i, j, c in spr:
        xx, yy = x + i, y + j
        if x0 <= xx < x1 and y0 <= yy < y1:
            px[yy][xx] = c


def cap_sprite(K, hp, poison, pal, pi, tint=None):
    key = ("cap", K, hp, poison, pi, tint)
    base = tint or (pal["poison"] if poison else pal["cap"])
    dmg = (4 - hp) * 0.12
    top = mix(base, pal["ground"], dmg)
    stem, spot = pal["stem"], pal["spot"] if not poison else shade(pal["poison"], 1.5)
    if K == 1:
        return sprite(key, 1, 1, lambda u, v: top)
    if K == 2:
        def fn2(u, v):
            if v < 0:
                if hp == 1 and u > 0:
                    return None
                return shade(top, 1.15) if u < 0 else top
            if hp == 4 or (hp == 3 and u < 0):
                return stem if u < 0 else shade(stem, 0.75)
            return None
        return sprite(key, 2, 2, fn2)
    if K == 3:   # hand-drawn at this size: a formula gives crosses
        rows_ = {4: ("LLC", "CCD", ".Ss"), 3: (".L.", "LCD", ".S."), 2: ("...", "LCD", ".S."), 1: ("...", ".C.", ".S.")}[hp]
        cmap = {"L": shade(top, 1.3), "C": top, "D": shade(top, 0.7), "S": stem, "s": shade(stem, 0.72)}
        spr = [(i, j, cmap[ch]) for j, r in enumerate(rows_) for i, ch in enumerate(r) if ch != "."]
        _SPR[key] = spr
        return spr
    s = (0.55, 0.7, 0.85, 1.0)[hp - 1]

    def fn(u, v):
        rx, ry = 1.0 * s, 0.85 * s
        cy = -0.1
        if v <= cy + 0.22 * s and (u / rx) ** 2 + ((v - cy) / ry) ** 2 <= 1.0:
            if v > cy + 0.08 * s:
                return shade(top, 0.62)                       # the gills under the brim
            for sx, sy, sr in ((-0.4, -0.4, 0.17), (0.32, -0.5, 0.14), (0.05, -0.22, 0.12)):
                if (u - sx * s) ** 2 + (v - sy * s) ** 2 < (sr * s + 0.02) ** 2 and K >= 4:
                    return spot
            l = -(u * 0.5 + (v - cy) * 0.8)
            return shade(top, 1.0 + l * 0.35)
        if abs(u) <= 0.26 * s + 0.06 and cy < v <= cy + 1.05 * s:
            return stem if u < 0.05 else shade(stem, 0.72)
        return None
    return sprite(key, K, K, fn)


def seg_sprite(K, kind, pal, pi, face=1, odd=0):
    key = ("seg", K, kind, pi, face, odd)
    body = pal["head"] if kind == "head" else (pal["worm2"] if odd else pal["worm"])
    eye = (20, 16, 24)

    def fn(u, v):
        r2 = u * u + v * v
        if r2 > (0.85 if K == 3 else 0.98):
            return None
        if kind == "head":
            if (u - 0.45 * face) ** 2 + (v + 0.35) ** 2 < 0.09:
                return eye
            if K >= 4 and (u - 0.85 * face) ** 2 + (v - 0.3) ** 2 < 0.06:
                return shade(body, 0.5)                       # mandible
        if K >= 3 and (u + 0.35) ** 2 + (v + 0.4) ** 2 < 0.05:
            return mix(body, (255, 255, 255), 0.6)            # glow dot
        l = -(u + v) * 0.22
        c = shade(body, 1.0 + l)
        return shade(c, 0.72) if r2 > 0.62 and K >= 3 else c
    return sprite(key, K, K, fn)


def beetle_size(K):
    """The beetle is drawn a little larger than one cell, so it stands out among the caps."""
    return K if K < 2 else K + 1 if K < 5 else K + 2


def beetle_sprite(K, flash=False):
    key = ("beetle", K, flash)
    B = beetle_size(K)
    sh, sd, sl = (SHELL, SHELL_D, SHELL_L) if not flash else ((255, 255, 255), (220, 220, 220), (255, 255, 255))
    if K == 1:
        return sprite(key, 1, 1, lambda u, v: sl)
    if K == 2:
        return sprite(key, 3, 3, lambda u, v: (SAP if abs(u) < 0.3 else None) if v < -0.5 else
                      (sl if u < -0.3 else sh if u < 0.3 else sd) if v < 0.4 else (sd if abs(u) > 0.3 else None))

    def fn(u, v):
        if abs(u) <= 1.0 / B + 0.01 and v < -0.6:
            return SAP                                        # the sap nozzle
        if v < -0.4 and abs(u) < 0.42:
            return BEETLE_HEAD
        if K >= 4 and abs(u) > 0.78 and (abs(v + 0.05) < 0.12 or abs(v - 0.5) < 0.12):
            return BEETLE_HEAD                                # legs
        if (u / 0.8) ** 2 + ((v - 0.15) / 0.82) ** 2 <= 1.0:
            if abs(u) < 0.09 and K >= 4:
                return sd
            l = -(u * 0.6 + v * 0.4)
            return shade(sh, 1.0 + l * 0.3) if l < 0.35 else sl
        return None
    return sprite(key, B, B, fn)


def critter_sprite(K, kind, frame, flash=False):
    key = ("crit", K, kind, frame, flash)
    W = (2, 1)
    if kind in ("jitterleg", "gloammoth"):
        W = (2, 1)
    elif kind == "puffball":
        W = (2, 2)
    else:
        W = (1, 1)
    w, h = W[0] * K, W[1] * K
    if flash:
        base = sprite(("crit", K, kind, frame, False), w, h, critter_fn(K, kind, frame))
        out = [(i, j, (255, 255, 255)) for i, j, c in base]
        _SPR[key] = out
        return out
    return sprite(key, w, h, critter_fn(K, kind, frame))


def critter_fn(K, kind, frame):
    if kind == "jitterleg":
        body, dark, eye = (226, 64, 128), (120, 26, 70), (255, 240, 120)

        def fn(u, v):
            if (u / 0.55) ** 2 + (v / 0.9) ** 2 <= 1:
                if K >= 3 and abs(u) < 0.3 and abs(u) > 0.08 and v < -0.2:
                    return eye
                return shade(body, 1.15 - (v + 1) * 0.15)
            au = abs(u)
            if 0.5 < au < 1.0 and K >= 2:
                seg = int((au - 0.5) * 6)
                target = (0.65 if (seg + frame) % 2 else -0.65)
                if abs(v - target) < (0.34 if K < 4 else 0.22):
                    return dark
            return None
        return fn
    if kind == "plumbug":
        body, stripe = (250, 150, 40), (110, 50, 20)

        def fn(u, v):
            if (u / 0.75) ** 2 + ((v - 0.1) / 0.9) ** 2 <= 1 or (v < -0.3 and abs(u) < 0.75 * (v + 1.1)):
                if K >= 3 and int((v + 1) * 2.5) % 2 == 1:
                    return stripe
                return shade(body, 1.1 - v * 0.15)
            return None
        return fn
    if kind == "gloammoth":
        wing, core = (160, 228, 255), (240, 250, 255)

        def fn(u, v):
            if abs(u) < 0.14 and abs(v) < 0.9:
                return core
            span = 0.95 if frame else 0.6
            au = abs(u)
            if au < span and (abs(v) < 0.85 - au * 0.5 if frame else abs(v + 0.2) < 0.9 - au * 0.6):
                return mix(wing, (90, 120, 255), au * 0.6) if K >= 3 else wing
            return None
        return fn
    if kind == "puffball":
        cloud, dot = (214, 206, 176), (150, 220, 110)

        def fn(u, v):
            r = 0.82 + 0.1 * math.sin(math.atan2(v, u) * 5 + frame * 1.2)
            if u * u + v * v <= r * r:
                if K >= 2 and ((u * 3 + 7) % 1.0 < 0.3) and ((v * 3 + 7) % 1.0 < 0.3):
                    return dot
                return shade(cloud, 1.1 - (u + v) * 0.12)
            return None
        return fn
    # burrowgrub
    pale, mouth = (240, 222, 190), (220, 90, 110)

    def fn(u, v):
        if (u / 0.8) ** 2 + (v / 0.95) ** 2 <= 1:
            if v < -0.45 and abs(u) < 0.3:
                return mouth
            return shade(pale, 0.82) if K >= 3 and int((v + 1) * 2.5) % 2 else pale
        return None
    return fn


def seed_sprite(K, kind, bright):
    key = ("seed", K, kind, bright)
    col = POWERS[kind][1]
    c = col if bright else shade(col, 0.6)
    if K <= 2:
        return sprite(key, K, K, lambda u, v: c if K == 1 or u * u + v * v < 0.6 else None)

    def fn(u, v):
        if (u / 0.6) ** 2 + ((v - 0.15) / 0.75) ** 2 <= 1 or (v < -0.3 and abs(u) < 0.5 * (v + 1.0)):
            return mix(c, (255, 255, 255), 0.5) if (u + 0.2) ** 2 + (v + 0.1) ** 2 < 0.06 else c
        return None
    return sprite(key, K, K, fn)


_BG = {}
_LAYER = {}


def layout(cols, rows, hud, foot):
    top = 1 if hud else 0
    bot = 1 if foot else 0
    PH = (rows - top - bot) * 2
    K = max(1, min(PH // GH, (cols - 2) // GW))
    fw, fh = GW * K, GH * K
    ox = (cols - fw) // 2
    oy = top * 2 + (PH - fh) // 2
    if fh > PH:                       # too small (a preview): keep the beetle's corner in view
        oy = top * 2 + PH - fh
    return K, ox, oy, fw, fh


def background(cols, rows, K, ox, oy, pi):
    key = (cols, rows, K, ox, oy, pi)
    bg = _BG.get(key)
    if bg is not None:
        return bg
    if len(_BG) > 12:
        _BG.clear()
    pal = PALETTES[pi]
    rnd = random.Random(pi * 7919 + K)
    W, H = cols, rows * 2
    otop, obot = shade(pal["ground"], 0.35), shade(pal["ground"], 0.7)
    px = [[mix(otop, obot, y / max(1, H - 1))] * W for y in range(H)]
    # grass blades in the dark around the meadow
    fw, fh = GW * K, GH * K
    for _ in range(W // 2):
        x = rnd.randrange(W)
        if ox - 2 <= x < ox + fw + 2:
            continue
        hgt = rnd.randint(3, max(4, H // 4))
        c = mix(otop, pal["moss"], rnd.uniform(0.4, 1.0))
        for j in range(hgt):
            yy = H - 1 - j
            xx = x + int(math.sin(j * 0.25 + x) * 1.2 * j / hgt)
            if 0 <= xx < W and 0 <= yy < H:
                px[yy][xx] = mix(c, otop, j / hgt * 0.6)
    # the meadow itself: mottled ground, moss patches, dew sparkles
    g1, g2, moss, dew = pal["ground"], pal["ground2"], pal["moss"], pal["dew"]
    field = [[g1 if rnd.random() < 0.65 else g2 for _ in range(fw)] for _ in range(fh)]
    for _ in range(GW * GH // 7):
        cx, cy = rnd.uniform(0, fw), rnd.uniform(0, fh)
        r = rnd.uniform(0.5, 1.6) * K
        c = mix(g2, moss, rnd.uniform(0.4, 1.0))
        for yy in range(max(0, int(cy - r)), min(fh, int(cy + r) + 1)):
            for xx in range(max(0, int(cx - r)), min(fw, int(cx + r) + 1)):
                if (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r and rnd.random() < 0.85:
                    field[yy][xx] = c
    for _ in range(GW * GH * K * K // 40):
        field[rnd.randrange(fh)][rnd.randrange(fw)] = mix(moss, dew, rnd.uniform(0.3, 0.8))
    zy = ZONE * K
    for yy in range(zy, fh):                  # the beetle's corner: a cooler tint
        field[yy] = [mix(c, pal["zone"], 0.45) for c in field[yy]]
    if K >= 2:
        for xx in range(0, fw, 2):
            field[zy][xx] = mix(field[zy][xx], dew, 0.45)
    for yy in range(fh):
        y = oy + yy
        if 0 <= y < H:
            row = px[y]
            a, b = max(0, ox), min(W, ox + fw)
            if b > a:
                row[a:b] = field[yy][a - ox:b - ox]
    edge = mix(moss, dew, 0.35)
    for y in range(max(0, oy - 1), min(H, oy + fh + 1)):
        for x in (ox - 1, ox + fw):
            if 0 <= x < W:
                px[y][x] = edge if (y // 2) % 3 else shade(edge, 1.3)
    for x in range(max(0, ox - 1), min(W, ox + fw + 1)):
        for y in (oy - 1, oy + fh):
            if 0 <= y < H:
                px[y][x] = edge
    _BG[key] = px
    return px


def field_layer(g, cols, rows, K, ox, oy):
    """Background plus all toadstools, rebuilt only when a cap changes."""
    pi = (g.wave - 1) % len(PALETTES)
    key = (cols, rows, K, ox, oy, pi)
    lay = _LAYER.get("v")
    if lay is not None and lay[0] == key and lay[1] == g.capver:
        return lay[2]
    bg = background(cols, rows, K, ox, oy, pi)
    px = [row[:] for row in bg]
    cv = Canvas.__new__(Canvas)
    cv.W, cv.H, cv.px = cols, rows * 2, px
    clip = (max(0, ox), max(0, oy), min(cols, ox + GW * K), min(rows * 2, oy + GH * K))
    pal = g.pal
    for (x, y), (hp, poison) in g.caps.items():
        blit(cv, cap_sprite(K, hp, poison, pal, pi), ox + x * K, oy + y * K, clip)
    _LAYER["v"] = (key, g.capver, px)
    return px


def render(g, cols, rows, hud=True, foot=True, kitty=True):
    K, ox, oy, fw, fh = layout(cols, rows, hud, foot)
    if g.shake > 0:
        ox += int(g.rng.choice((-1, 1)) * (1 if g.shake < 0.15 else 2))
    cv = Canvas.__new__(Canvas)
    cv.cols, cv.rows, cv.W, cv.H = cols, rows, cols, rows * 2
    cv.text = {}
    cv.px = [row[:] for row in field_layer(g, cols, rows, K, ox, oy)]
    pal = g.pal
    pi = (g.wave - 1) % len(PALETTES)
    clip = (max(0, ox), max(0, oy), min(cols, ox + fw), min(rows * 2, oy + fh))
    t = g.t
    # fireflies drifting over the meadow
    rnd = random.Random(3)
    for i in range(10):
        fx = (rnd.uniform(0, GW) + math.sin(t * 0.3 + i) * 3) % GW
        fy = (rnd.uniform(0, ZONE) + math.cos(t * 0.23 + i * 2) * 2) % GH
        a = 0.5 + 0.5 * math.sin(t * 2.0 + i * 1.7)
        if a > 0.3:
            x, y = int(ox + fx * K), int(oy + fy * K)
            if clip[0] <= x < clip[2] and clip[1] <= y < clip[3]:
                cv.px[y][x] = mix(cv.px[y][x], (240, 255, 170), a)
    # poisoned caps pulse, hit caps flash
    pulse = 0.5 + 0.5 * math.sin(t * 6)
    if pulse > 0.6:
        bright = mix(pal["poison"], (255, 255, 255), 0.35)
        for (x, y), (hp, poison) in g.caps.items():
            if poison:
                blit(cv, cap_sprite(K, hp, True, pal, pi, bright), ox + x * K, oy + y * K, clip)
    for cell, until in list(g.flash.items()):
        if until < t:
            del g.flash[cell]
        elif cell in g.caps:
            blit(cv, cap_sprite(K, g.caps[cell][0], False, pal, pi, (255, 255, 255)), ox + cell[0] * K,
                 oy + cell[1] * K, clip)
    # burrowgrubs rumbling under the soil
    for c in g.critters:
        if c.kind == "burrowgrub" and c.phase in ("rumble", "dig"):
            cx, cy = int(ox + c.x * K), int(oy + c.y * K)
            dark = shade(pal["ground"], 0.4)
            r = max(1, K)
            for a in range(6):
                ang = a * 1.05 + (t * 7 if c.phase == "rumble" else 0)
                for d in range(r):
                    x, y = int(cx + math.cos(ang) * d), int(cy + math.sin(ang) * d)
                    if clip[0] <= x < clip[2] and clip[1] <= y < clip[3]:
                        cv.px[y][x] = dark
    # seeds
    for s in g.seeds:
        blink = s[3] is not None and t - s[3] > 5.0 and int(t * 8) % 2
        if blink:
            continue
        bright = int(t * 5) % 2 == 0
        blit(cv, seed_sprite(K, s[2], bright), int(ox + (s[0] - 0.5) * K), int(oy + (s[1] - 0.5) * K), clip)
    # the sporeworm, wiggling
    for ch in g.chains:
        f = clamp(ch.t / ch.iv, 0.0, 1.0)
        for i in range(len(ch.segs) - 1, -1, -1):
            s = ch.segs[i]
            x = s[2] + (s[0] - s[2]) * f
            y = s[3] + (s[1] - s[3]) * f
            wig = math.sin(t * 9 + i * 1.3) * 0.22 * K if K >= 3 else 0
            if i == 0:
                face = ch.dx if s[0] == s[2] else sgn(s[0] - s[2])
                spr = seg_sprite(K, "head", pal, pi, face or 1)
            else:
                spr = seg_sprite(K, "body", pal, pi, 1, i % 2)
            blit(cv, spr, int(round(ox + x * K)), int(round(oy + y * K + wig)), clip)
    # creatures
    frame = int(t * 10) % 2
    for c in g.critters:
        if c.kind == "burrowgrub" and c.phase != "out":
            continue
        w, h = {"jitterleg": (2, 1), "gloammoth": (2, 1), "puffball": (2, 2)}.get(c.kind, (1, 1))
        hop = -abs(math.sin(c.t * 9)) * 0.35 * K if c.kind == "burrowgrub" else 0
        spr = critter_sprite(K, c.kind, frame, c.flash > 0)
        blit(cv, spr, int(round(ox + (c.x - w / 2) * K)), int(round(oy + (c.y - h / 2) * K + hop)), clip)
    # sap
    for b in g.bullets:
        x, y = int(ox + b[0] * K), int(oy + b[1] * K)
        if b[2] == "bomb":
            c = BOMB_C if int(t * 16) % 2 else (255, 230, 150)
            n = max(1, K // 2 + 1)
            cv.rect(x - n // 2, y - n // 2, n, n, c)
            continue
        col = PIERCE_C if b[2] == "pierce" else SAP
        ln = max(1, K) + (K if b[2] == "pierce" else 0)
        for j in range(ln + K):
            yy = y + j
            if clip[0] <= x < clip[2] and clip[1] <= yy < clip[3]:
                cv.px[yy][x] = col if j < ln else mix(cv.px[yy][x], col, 0.4)
    # the beetle
    if g.state == "play" and not (g.invuln > 0 and int(t * 12) % 2):
        B = beetle_size(K)
        bx, by = int(round(ox + g.px * K - B / 2)), int(round(oy + g.py * K - B / 2))
        blit(cv, beetle_sprite(K), bx, by, clip)
        if g.shell:
            c = POWERS["shell"][1]
            r = K * 0.85 + 0.6
            for a in range(16):
                ang = a / 16 * math.tau + t * 3
                x, y = int(bx + B / 2 + math.cos(ang) * r), int(by + B / 2 + math.sin(ang) * r)
                if clip[0] <= x < clip[2] and clip[1] <= y < clip[3] and a % 2 == 0:
                    cv.px[y][x] = c
    # particles
    ps = max(1, K // 2)
    for x, y, vx, vy, life, ml, c in g.parts:
        a = life / ml
        xx, yy = int(ox + x * K), int(oy + y * K)
        if clip[0] <= xx < clip[2] and clip[1] <= yy < clip[3]:
            if ps == 1:
                cv.px[yy][xx] = mix(cv.px[yy][xx], c, min(1.0, a * 1.4))
            else:
                cv.rect(xx, yy, ps, ps, mix(cv.px[yy][xx], c, min(1.0, a * 1.4)))
    # score pops
    for x, y, txt, until, c in g.pops[-6:]:
        rise = (0.8 - (until - t)) * 1.2
        col = int(ox + x * K) - len(txt) // 2
        row = int(oy + (y - rise) * K) // 2
        if (hud and row < 1) or row < 0:
            continue
        col = clamp(col, max(0, ox), max(0, ox + fw - len(txt)))
        cv.put(col, row, txt, c)
    if g.banner and g.banner[1] > t and hud:
        cv.center(max(1, (oy + (ZONE - 8) * K) // 2), "  %s  " % g.banner[0], (14, 14, 20), mix(pal["head"], (255, 255, 255), 0.3))
    if hud:
        draw_hud(cv, g)
    if foot:
        auto = "on" if g.autofire else "off"
        footer(cv, "arrows move   Space fire   F auto-fire: %s   Esc pause   ? help" % auto)
    if g.paused:
        overlay(cv, help_lines(kitty) if g.help else PAUSE_LINES + ["", SND.label()])
    return cv


def draw_hud(cv, g):
    cols = cv.cols
    cv.rect(0, 0, cols, 2, HUD_BG)
    rec = load_scores().get(GAME, {}).get(g.D["name"]) if not g.demo else None
    hi = max(rec or 0, g.score)
    parts = [("SCORE ", "%d" % g.score, GOLD), ("  HI ", "%d" % hi, HUD_VALUE),
             ("  WAVE ", "%d %s" % (g.wave, g.pal["name"]), HUD_VALUE)]
    x = 1
    for lab, val, c in parts:
        if x + len(lab) + len(val) > cols - 14:
            break
        cv.put(x, 0, lab, HUD_LABEL)
        cv.put(x + len(lab), 0, val, c)
        x += len(lab) + len(val)
    # active powers
    pw = []
    for k in ("double", "pierce", "slow", "shell"):
        if g.active(k):
            pw.append(("%s %d" % (POWERS[k][0], math.ceil(g.power[k] - g.t)), POWERS[k][1]))
    if g.bombs:
        pw.append(("BOMBS %d" % g.bombs, POWERS["bomb"][1]))
    if g.autofire:
        pw.append(("AUTO", (170, 180, 210)))
    x += 2
    for txt, c in pw:
        if x + len(txt) + 2 > cols - 12:
            break
        cv.put(x, 0, txt, c)
        x += len(txt) + 2
    # lives as little beetles (pixels in row 0), then the number
    n = max(0, g.lives - 1)
    show = min(n, 5)
    lx = cols - 2 - show * 3 - (3 if n > 5 else 0)
    for i in range(show):
        bx = lx + i * 3
        cv.set(bx, 0, SHELL_L)
        cv.set(bx + 1, 0, SAP)
        cv.set(bx, 1, SHELL)
        cv.set(bx + 1, 1, SHELL_D)
    if n > 5:
        cv.put(cols - 4, 0, "+%d" % (n - 5), SHELL)


def render_over(g, cv, record, auto=False):
    lines = ["THE ROOTS ARE LOST", "", "score %d" % g.score, "wave  %d   (%s)" % (g.wave, g.D["name"])]
    if record:
        lines += ["", "** NEW RECORD **"]
    lines += ["", "auto mode: a new round starts" if auto else "Enter: again   Esc / Q: menu"]
    w = max(len(l) for l in lines) + 4
    x, y = max(0, (cv.cols - w) // 2), max(0, cv.rows // 2 - len(lines) // 2 - 1)
    edge = GOLD if record else (200, 90, 140)
    cv.frame(x - 1, y * 2 - 1, w + 2, (len(lines) + 2) * 2 + 2, edge)
    cv.box(x, y, [l.center(w - 4) for l in lines], (240, 240, 246), (24, 20, 40))


class TitleDemo:
    """An autopiloted beetle in the meadow, behind the title screen and in the launcher preview."""

    def __init__(self):
        self.new()

    def new(self):
        self.g = Game(1, demo=True)
        self.g.lives = 2

    def scene(self, cols, rows, dt):
        g = self.g
        g.inp = bot_input(g)
        g.update(min(dt, 0.1))
        if g.state == "over" or g.t > 150:
            self.new()
        return render(g, cols, rows, hud=False, foot=False)


class AutoRun:
    """Auto mode: the real game on the chosen difficulty (real waves, lives, creatures and sound), played by a
    Pilot. After a game over the result stays for a few seconds, then a new round starts. No score is kept."""
    OVER_SHOW = 3.0

    def __init__(self, diff, sound=True, seed=None):
        self.diff, self.sound, self.seed = diff, sound, seed
        self.auto = AutoMode()
        self.rounds = 0
        self.new()

    def new(self):
        self.rounds += 1
        self.g = Game(self.diff, demo=not self.sound, seed=None if self.seed is None else self.seed + self.rounds)
        self.pilot = Pilot()
        self.over_t = 0.0

    def key(self, k):
        a = self.auto.key(k)
        if a == "sound" and SND.toggle():
            SND.play("sound_on")
        return a

    def frame(self, dt, cols, rows, draw=True):
        g = self.g
        if g.state == "over":
            if not (self.auto.paused or self.auto.help):
                self.over_t += dt
            if self.over_t >= self.OVER_SHOW:
                self.new()
                g = self.g
        else:
            for _ in range(self.auto.steps(dt, DT)):
                g.inp = self.pilot(g, DT)
                g.step(DT)
                if g.state == "over":
                    if self.sound:
                        SND.play("over")
                    break
        if not draw:
            return None
        cv = render(g, cols, rows)
        if g.state == "over":
            render_over(g, cv, False, auto=True)
        self.auto.banner(cv, extra="%s  round %d" % (g.D["name"], self.rounds))
        return cv


def run_auto(term, diff):
    """Auto mode until the viewer stops it (Esc / Q)."""
    run = AutoRun(diff)
    last = time.time()
    while True:
        now = time.time()
        dt, last = min(0.1, now - last), now
        for k in term.keys(0):
            if run.key(k) == "stop":
                return
        cols, rows = term.size()
        if cols < 60 or rows < 22:
            too_small(term)
            time.sleep(0.2)
            continue
        term.write(run.frame(dt, cols, rows).emit())
        time.sleep(max(0.0, 1 / 30 - (time.time() - now)))


def render_menu(demo, cols, rows, sel, dt, kitty, help_=False, diff=None):
    cv = demo.scene(cols, rows, dt)
    rec = load_scores().get(GAME, {})
    diff = sel if sel < len(DIFFS) else (1 if diff is None else diff)
    name = DIFFS[diff]["name"]
    best = "best %s: %d" % (name, rec[name]) if name in rec else None
    items = ["%-7s %s" % (d["name"], d["desc"]) for d in DIFFS] + [AUTO_LABEL]
    extra = ["", "Keys: %s" % ("held keys (kitty protocol)" if kitty else "classic mode - F: auto-fire")]
    if sel == len(DIFFS):
        extra = ["", "the game plays itself on %s" % name]
    title_screen(cv, "SPOREFIELD", "stop the sporeworm before it reaches the roots", items, sel, best, extra=extra,
                 keys="Up/Down difficulty   Enter start   M %s   ? help   Esc back" % SND.label().lower(),
                 help_lines=help_lines(kitty), show_help=help_, dim=0.45)
    return cv


# =============================================================================================
# Main loop
# =============================================================================================
def too_small(term):
    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (60x22).")


def play(term, diff):
    """One game. Returns when the player goes back to the menu."""
    while True:
        g = Game(diff)
        held = HeldKeys(term.kitty)
        last = time.time()
        record = None
        over_at = 0.0
        back = again = False
        while not (back or again):
            now = time.time()
            for name, kind in term.events(0):
                held.feed(name, kind, now)
                if kind != "press":
                    continue
                if g.state == "over":
                    if name in ("q", "esc"):
                        back = True
                    elif record is not None and name in ("enter", " ") and time.time() - over_at > 1.0:
                        again = True
                    continue
                a = shared_key(name, g.paused)
                if a == "pause":
                    g.paused = True
                    SND.play("pause")
                elif a == "resume":
                    g.paused = g.help = False
                    held.clear()
                elif a == "quit":
                    back = True
                elif a == "help":
                    g.help = not g.help
                    g.paused = True
                elif a == "sound":
                    if SND.toggle():
                        SND.play("sound_on")
                elif a is None and name == "f":
                    g.autofire = not g.autofire
                    SND.play("autofire")
            held.tick(now)
            hits = held.take_hits()
            if " " in hits and not g.paused:
                g.tap = True
            dx = int(held.down("right", "d")) - int(held.down("left", "a"))
            dy = int(held.down("down", "s")) - int(held.down("up", "w"))
            g.inp = (dx, dy, held.down(" "))
            g.update(now - last)
            last = now
            if g.state == "over" and record is None:
                SND.play("over")
                record = submit(GAME, g.D["name"], g.score)
                over_at = time.time()
            cols, rows = term.size()
            if cols < 60 or rows < 22:
                too_small(term)
                g.paused = g.paused or g.state == "play"
                time.sleep(0.2)
                last = time.time()
                continue
            cv = render(g, cols, rows, kitty=term.kitty)
            if g.state == "over":
                render_over(g, cv, record)
            term.write(cv.emit())
            time.sleep(max(0.0, 1 / 30 - (time.time() - now)))
        if back:
            return


def main():
    with KeyTerminal() as term:
        demo = TitleDemo()
        sel, help_ = 1, False
        diff = 1                    # the difficulty chosen last (auto mode plays on it)
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
            term.write(render_menu(demo, cols, rows, sel, min(0.1, now - last), term.kitty, help_, diff).emit())
            last = now
            go = False
            for k in term.keys(max(0.0, 1 / 30 - (time.time() - now))):
                if help_:
                    help_ = False
                    continue
                if k == "?":
                    help_ = True
                elif k in ("q", "esc"):
                    return
                elif k in ("up", "w"):
                    sel = (sel - 1) % (len(DIFFS) + 1)
                    SND.play("menu")
                elif k in ("down", "s"):
                    sel = (sel + 1) % (len(DIFFS) + 1)
                    SND.play("menu")
                elif k == "m":
                    if SND.toggle():
                        SND.play("sound_on")
                elif k in ("enter", " "):
                    SND.play("start")
                    go = True
            if sel < len(DIFFS):
                diff = sel
            if go:
                if sel == len(DIFFS):
                    run_auto(term, diff)
                else:
                    play(term, sel)
                last = time.time()


# =============================================================================================
# Selftest: python3 sporefield.py --selftest
# =============================================================================================
def selftest():
    t0 = time.time()
    # splitting: the hit segment becomes a toadstool, the worm falls apart into two chains
    g = Game(1, seed=1)
    g.caps.clear()
    g.chains = [Chain([[10 - i, 5, 10 - i, 5] for i in range(8)], 1, 1, False, 0.1)]
    g.kill_segment(g.chains[0], 3)
    assert (7, 5) in g.caps, "the hit segment did not become a toadstool"
    assert sorted(len(c.segs) for c in g.chains) == [3, 4], "split gave %s" % [len(c.segs) for c in g.chains]
    tail = next(c for c in g.chains if len(c.segs) == 4)
    assert tail.segs[0][0] == 6 and tail.dx == 1, "the new head goes the wrong way"
    g.step_chain(tail)                   # the new head bumps into the new cap and turns down
    assert tail.segs[0][1] == 6 and tail.dx == -1, "the new head did not turn at the cap"
    g.kill_segment(next(c for c in g.chains if len(c.segs) == 3), 0)
    assert any(len(c.segs) == 2 for c in g.chains) and g.stats["heads"] == 1
    # an edge turns the worm, a poisoned cap sends it straight down to the roots
    g = Game(1, seed=2)
    g.caps.clear()
    ch = Chain([[GW - 1, 3, GW - 1, 3]], 1, 1, False, 0.1)
    g.chains = [ch]
    g.step_chain(ch)
    assert (ch.segs[0][0], ch.segs[0][1], ch.dx) == (GW - 1, 4, -1), "no turn at the edge"
    g.setcap(GW - 2, 4, 4, True)
    g.step_chain(ch)
    assert ch.dive, "a poisoned cap did not make the worm dive"
    for _ in range(GH):
        g.step_chain(ch)
    assert ch.segs[0][1] >= ZONE and not ch.dive, "the dive did not end at the bottom"
    # in the bottom zone the worm stays there
    for _ in range(400):
        g.step_chain(ch)
        assert ZONE <= ch.segs[0][1] < GH, "the worm left the bottom zone"
    # whole games with the autopilot: every creature, every power, several waves
    stats = {}
    steps = 0
    sizes = [(60, 22), (70, 22), (120, 40), (200, 60)]
    rtimes = {s: [] for s in sizes}
    for run in range(2):
        g = Game(run + 1, seed=10 + run)
        g.lives = 99
        forced = 0
        sim = 0.0
        while sim < 420 and (g.wave < 6 or not g.stats.get("kill_plumbug")):
            g.inp = bot_input(g)
            g.step(DT)
            sim += DT
            steps += 1
            if steps % 240 == 0 and g.state == "play":
                g.spawn(CRITTERS[forced % len(CRITTERS)])
                forced += 1
            if steps % 400 == 0 and g.state == "play":
                g.give(list(POWERS)[(steps // 400) % len(POWERS)])
            if steps % 900 == 0 and g.state == "play":
                g.drop_seed(g.px, ZONE + 0.5)
            for chn in g.chains:
                assert len(chn.segs) >= 1
                for s in chn.segs:
                    assert 0 <= s[0] < GW and -40 <= s[1] < GH, "segment out of bounds: %s" % s
            for (x, y), (hp, p) in g.caps.items():
                assert 0 <= x < GW and 0 <= y < GH and 1 <= hp <= 4, "bad cap"
            assert 0.5 <= g.px <= GW - 0.5 and ZONE + 0.5 <= g.py <= GH - 0.5, "the beetle left its corner"
            if steps % 150 == 0:
                s = sizes[(steps // 150) % len(sizes)]
                a = time.time()
                cv = render(g, *s)
                cv.emit(True)
                rtimes[s].append(time.time() - a)
                assert len(cv.px) == s[1] * 2 and all(len(r) == s[0] for r in cv.px), "canvas size"
        for k, v in g.stats.items():
            stats[k] = stats.get(k, 0) + v
        print("run %d (%s): wave %d after %.0f s, score %d, deaths %d" %
              (run + 1, g.D["name"], g.wave, sim, g.score, g.stats.get("deaths", 0)))
        assert g.wave >= 3, "the autopilot did not get past wave 2"
    for k in CRITTERS:
        assert stats.get("spawn_" + k), "%s never appeared" % k
        assert stats.get("kill_" + k), "%s was never shot" % k
    for k in POWERS:
        assert stats.get("power_" + k), "power %s never used" % k
    for k in ("splits", "caps_made", "heads", "segments", "bombs", "caps_cleared", "poisoned", "trickle"):
        assert stats.get(k), "never happened: %s" % k
    # losing a life: damaged and poisoned caps come back one by one
    g = Game(1, seed=5)
    g.lives = 2
    cells = list(g.caps)[:6]
    for c in cells[:3]:
        g.caps[c][0] = 2
    for c in cells[3:]:
        g.caps[c][1] = True
    g.player_hit()
    sc = g.score
    for _ in range(int(4 / DT)):
        g.step(DT)
    assert all(g.caps[c] == [4, False] for c in cells if c in g.caps), "caps not restored"
    assert g.score >= sc + 30 and g.state == "play" and g.lives == 1, "restore bonus / respawn"
    g.lives = 1
    g.player_hit()
    for _ in range(int(4 / DT)):
        g.step(DT)
    assert g.state == "over", "no game over with no lives left"
    # extra life
    g = Game(1, seed=6)
    l0 = g.lives
    g.add(EXTRA_LIFE)
    assert g.lives == l0 + 1
    # title demo and launcher preview, menus
    d = TitleDemo()
    for i in range(240):
        d.scene(*[(60, 22), (34, 9), (24, 7), (120, 40)][i % 4], 1 / 30)
    for s in sizes:
        render_menu(d, s[0], s[1], 1, 1 / 30, True, help_=False).emit(True)
        render_menu(d, s[0], s[1], 0, 1 / 30, False, help_=True).emit(True)
        g = Game(1, seed=3)
        g.paused = True
        render(g, *s).emit(False)
        g.state = "over"
        cv = render(g, *s)
        render_over(g, cv, True)
        cv.emit(True)
    for s in sizes:
        if rtimes[s]:
            print("render+emit %3dx%-3d  %5.1f ms  (%d frames)" % (s[0], s[1], 1000 * sum(rtimes[s]) / len(rtimes[s]),
                                                                    len(rtimes[s])))
    # auto mode: the real game (no extra lives, no help) at x8; pause, speed and stop work; no score is kept
    submitted = []
    real_submit = globals()["submit"]
    globals()["submit"] = lambda *a, **k: submitted.append(a)
    try:
        run = AutoRun(1, sound=False, seed=21)
        assert run.g.lives == DIFFS[1]["lives"] and run.g.invuln == 0.0
        run.key(" ")
        snap = (run.g.t, run.g.score)
        for _ in range(30):
            run.frame(1 / 30, 70, 22, draw=False)
        assert (run.g.t, run.g.score) == snap, "auto mode ran on while paused"
        run.key(" ")
        for _ in range(5):
            run.key("+")
        assert run.auto.speed == 8.0
        auto_secs, results = 40, []
        for i in range(auto_secs * 30):
            g0 = run.g
            run.frame(1 / 30, 70 + i % 3 * 25, 22 + i % 2 * 10, draw=i % 20 == 0)
            if run.g is not g0:
                results.append((g0.wave, g0.score))
        results.append((run.g.wave, run.g.score))
        assert run.key("esc") == "stop"
        assert not submitted, "auto mode submitted a score"
    finally:
        globals()["submit"] = real_submit
    print("auto mode %d s at x8 (Normal): %d round(s), (wave, score) %s, nothing recorded" % (auto_secs, run.rounds, results))
    # simulation speed
    g = Game(2, seed=9)
    g.lives = 99
    a = time.time()
    for _ in range(3000):
        g.inp = bot_input(g)
        g.step(DT)
    print("simulation: %.3f ms per step" % ((time.time() - a) / 3000 * 1000))
    print("stats: " + ", ".join("%s %d" % kv for kv in sorted(stats.items())))
    print("selftest ok: %d steps in %.1f s" % (steps, time.time() - t0))


def screenshot(cols=100, rows=32):
    """README picture: real play on Normal (seed 23) by the auto-mode pilot, 230 s in, wave 7 (Tidepool): a worm
    winding down through the caps, critters about, the beetle firing from the roots, HUD and footer. Silent (a demo
    game never plays sound or touches the score file). The meadow is 32 cells tall, so it needs 34 rows to be
    drawn at two pixels per cell; below that it shrinks to one, which is too small for a picture."""
    rows = max(rows, 34)
    g = Game(1, demo=True, seed=23)
    pilot = Pilot()
    for _ in range(int(round(230.0 / DT))):
        g.inp = pilot(g, DT)
        g.step(DT)
    return render(g, cols, rows)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
