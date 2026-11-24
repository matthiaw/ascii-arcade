#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""BREAKROOM - an office full of things that had it coming.

A rage room in your terminal. Shelves of plates, mugs, vases and bottles, a desk with a monitor, a lamp and a
trophy, a printer on the floor, a clock and a motivational poster on the wall. Three tools: the hammer (quick
and precise), the bat (two hits' worth, and it sends things flying off the shelves) and the firecracker (a
fuse, a bang, and everything near it goes). Every shard falls and piles up on the floor. Stacks collapse when
the plate underneath goes, a monitor knocked off the desk breaks on the floor.

When the room is mostly rubble, a new delivery arrives. Free Smash has no clock: a stress bar goes down with
every smash. One Minute adds up the damage bill against the clock.

Point with the mouse and click (right click or the wheel changes the tool), or steer with the arrow keys and
press Space; 1 2 3 pick a tool.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
Run:        python3 breakroom.py
Self-test:  python3 breakroom.py --selftest
"""
import math
import random
import sys
import time

from arcadekit import (AUTO_LABEL, PAUSE_LINES, AutoMode, Canvas, MouseTerminal, clamp, load_scores, mix, overlay,
                       shade, shared_key, submit, title_screen)
from arcadesound import Sound

GAME = "breakroom"
MODES = [("Free Smash", "no clock; smash until the stress is gone"), ("One Minute", "the biggest damage bill in 60 s")]
MINUTE = 60.0
TOOLS = [  # name, damage, reach (px), knock (in heights / s), cooldown (s)
    ("Hammer", 1, 0.6, 0.0, 0.13),
    ("Bat", 2, 3.0, 1.6, 0.34),
    ("Firecracker", 3, 0.0, 2.2, 0.8),
]
GRAV = 2.4                 # heights / s^2
# kind: width and height (in screen heights), hit points, material, price
KINDS = {
    "plate": (0.15, 0.03, 1, "ceramic", 4),
    "mug": (0.075, 0.075, 1, "ceramic", 7),
    "vase": (0.085, 0.17, 2, "ceramic", 45),
    "bottle": (0.045, 0.15, 1, "glass", 9),
    "glass": (0.05, 0.1, 1, "glass", 6),
    "trophy": (0.065, 0.11, 2, "metal", 25),
    "plant": (0.11, 0.17, 2, "ceramic", 20),
    "monitor": (0.25, 0.22, 4, "electronic", 180),
    "keyboard": (0.17, 0.035, 2, "plastic", 30),
    "lamp": (0.1, 0.17, 2, "metal", 40),
    "printer": (0.24, 0.15, 6, "electronic", 260),
    "clock": (0.11, 0.11, 2, "glass", 35),
    "poster": (0.17, 0.13, 2, "glass", 60),
}
FRAGILE = ("ceramic", "glass")
COLORS = [(214, 72, 64), (64, 120, 214), (236, 186, 60), (90, 170, 110), (170, 100, 200), (240, 240, 236),
          (240, 130, 70)]
WALLPAPER = ((214, 206, 182), (198, 190, 168))
FLOOR = (118, 98, 82)
WOOD, WOOD_D = (150, 104, 66), (110, 74, 46)
HUD_BG, HUD_FG = (16, 14, 26), (226, 226, 236)
SND = Sound(GAME, {
    "thud": [dict(w="noise", f=700, f2=150, d=0.07, v=0.35), dict(w="tri", f=150, f2=90, d=0.06, v=0.35, at=0)],
    "whoosh": [dict(w="noise", f=1200, f2=3500, d=0.12, v=0.18, a=0.04, r="lin")],
    "ceramic": [dict(w="noise", f=5000, f2=900, d=0.3, v=0.5), dict(w="tri", f=1900, d=0.05, v=0.2, at=0.02),
                dict(w="tri", f=2600, d=0.04, v=0.16, at=0.08), dict(w="tri", f=1500, d=0.05, v=0.14, at=0.14)],
    "glass": [dict(w="noise", f=9000, f2=3000, d=0.35, v=0.45), dict(w="tri", f=3200, d=0.05, v=0.2, at=0.01),
              dict(w="tri", f=4100, d=0.05, v=0.18, at=0.06), dict(w="tri", f=3700, d=0.06, v=0.16, at=0.12),
              dict(w="tri", f=4600, d=0.08, v=0.12, at=0.2)],
    "metal": [dict(w="square", f=620, f2=560, d=0.35, v=0.2, duty=0.3, vib=(14, 0.3)),
              dict(w="tri", f=1480, d=0.3, v=0.16, at=0), dict(w="noise", f=2500, f2=500, d=0.08, v=0.3, at=0)],
    "plastic": [dict(w="noise", f=2200, f2=600, d=0.12, v=0.4), dict(w="square", f=300, f2=180, d=0.05, v=0.2, at=0)],
    "electronic": [dict(w="noise", f=3500, f2=200, d=0.5, v=0.55), dict(w="saw", f=880, f2=60, d=0.35, v=0.25, at=0),
                   dict(w="square", f=1500, f2=1400, d=0.08, v=0.14, duty=0.2, at=0.3)],
    "dent": [dict(w="square", f=330, f2=250, d=0.08, v=0.2, duty=0.3), dict(w="noise", f=1200, d=0.05, v=0.25, at=0)],
    "fuse": [dict(w="noise", f=6000, d=0.7, v=0.12, r="hold")],
    "boom": [dict(w="noise", f=1800, f2=60, d=0.8, v=0.8), dict(w="sine", f=90, f2=30, d=0.5, v=0.7, at=0)],
    "tool": [dict(w="tri", f=660, d=0.03, v=0.2), dict(w="tri", f=990, d=0.04, v=0.2)],
    "delivery": [dict(w="tri", f=1047, d=0.12, v=0.3), dict(w="tri", f=784, d=0.25, v=0.3)],
    "zen": [dict(w="sine", f=f, d=0.5, v=0.25, at=i * 0.12, r="lin") for i, f in enumerate((523, 659, 784, 1047))],
    "tick": [dict(w="tri", f=1568, d=0.03, v=0.18)],
    "over": [dict(w="square", f=f, d=0.09, v=0.26, duty=0.25) for f in (392, 523, 659)] +
            [dict(w="tri", f=784, d=0.45, v=0.4, vib=(6, 0.25), r="lin")],
    "menu": [dict(w="tri", f=660, d=0.025, v=0.2)],
    "start": [dict(w="noise", f=5000, f2=900, d=0.25, v=0.4), dict(w="tri", f=2600, d=0.05, v=0.2, at=0.03)],
    "pause": [dict(w="tri", f=523, f2=392, d=0.07, v=0.22)],
    "sound_on": [dict(w="tri", f=440, d=0.06, v=0.35), dict(w="tri", f=880, d=0.12, v=0.35)],
})
HELP = [
    "BREAKROOM - keys",
    "",
    "Mouse                 aim",
    "Left click            smash",
    "Right click / wheel   next tool",
    "Arrows / WASD         move the hand",
    "Space / Enter         smash",
    "1 2 3 / Tab           hammer, bat, firecracker",
    "N                     new delivery now",
    "Esc / P               pause     ? help",
    "",
    "Hammer: quick and precise.  Bat: hits twice as hard",
    "and knocks things off shelves.  Firecracker: a short",
    "fuse, then everything near it goes.",
]


# =============================================================================================
# The things: drawn from a shape function at any size
# =============================================================================================
def _hw(v, prof):
    """Half width at height v from a list of (v, half width) points."""
    for (v0, w0), (v1, w1) in zip(prof, prof[1:]):
        if v0 <= v <= v1:
            return w0 + (w1 - w0) * (v - v0) / max(1e-6, v1 - v0)
    return 0.0


def shape(kind, c, u, v):
    """Colour of the thing at (u, v) in 0..1 (v down), or None where it is not."""
    du = abs(u - 0.5)
    if kind == "plate":
        hw = 0.5 if v < 0.5 else 0.36
        if du > hw:
            return None
        return c if v < 0.34 and du > hw - 0.12 else (246, 244, 236) if v < 0.5 else (214, 210, 200)
    if kind == "mug":
        if u <= 0.74:
            if not 0.04 <= u or v < 0.06:
                return None
            if v < 0.16:
                return mix(c, (255, 255, 255), 0.35)
            return (250, 250, 246) if 0.42 < v < 0.56 else shade(c, 1.0 - 0.25 * u)
        d = math.hypot((u - 0.74) / 0.26, (v - 0.48) / 0.3)
        return shade(c, 0.8) if 0.45 <= d <= 1.0 else None
    if kind == "vase":
        hw = _hw(v, [(0, 0.24), (0.06, 0.24), (0.07, 0.15), (0.22, 0.15), (0.55, 0.48), (0.85, 0.4), (1, 0.26)])
        if du > hw:
            return None
        if 0.6 < v < 0.68:
            return shade(c, 0.6)
        if 0.38 < v < 0.84 and int(u * 9 + v * 9) % 3 == 0:
            return mix(c, (255, 250, 230), 0.5)
        return shade(c, 1.1 - 0.35 * (u - 0.5 + hw) / max(0.01, 2 * hw))
    if kind == "bottle":
        hw = _hw(v, [(0, 0.16), (0.36, 0.16), (0.5, 0.48), (1, 0.48)])
        if du > hw:
            return None
        if v < 0.08:
            return c
        g = (54, 140, 84)
        return mix(g, (200, 255, 210), 0.5) if 0.25 < u < 0.38 and v > 0.4 else shade(g, 1 - 0.3 * u)
    if kind == "glass":
        hw = _hw(v, [(0, 0.44), (0.3, 0.42), (0.5, 0.12), (0.52, 0.06), (0.86, 0.06), (0.9, 0.4), (1, 0.42)])
        if du > hw:
            return None
        if 0.2 < v < 0.46:
            return (170, 40, 60) if du < hw - 0.04 else (230, 240, 248)
        return (200, 226, 240) if du < hw - 0.06 or v > 0.5 else (240, 248, 255)
    if kind == "trophy":
        hw = _hw(v, [(0, 0.38), (0.45, 0.2), (0.55, 0.06), (0.75, 0.06), (0.8, 0.28), (1, 0.32)])
        hd = math.hypot((du - 0.38) / 0.12, (v - 0.22) / 0.14)
        if du > hw and not (0.6 < hd < 1.1 and v < 0.4):
            return None
        if v > 0.82:
            return (60, 46, 40)
        gold = (236, 186, 60)
        return mix(gold, (255, 250, 200), 0.6) if 0.3 < u < 0.4 and v < 0.4 else shade(gold, 1 - 0.3 * u)
    if kind == "plant":
        if v > 0.56:
            hw = _hw(v, [(0.56, 0.4), (0.64, 0.4), (0.65, 0.33), (1, 0.27)])
            if du > hw:
                return None
            return (196, 106, 64) if v < 0.65 else shade((176, 92, 56), 1 - 0.3 * u)
        for lx, ly, rx, ry in ((0.5, 0.3, 0.16, 0.3), (0.28, 0.38, 0.2, 0.12), (0.72, 0.36, 0.2, 0.12),
                               (0.36, 0.14, 0.12, 0.14), (0.64, 0.12, 0.12, 0.14)):
            if ((u - lx) / rx) ** 2 + ((v - ly) / ry) ** 2 <= 1:
                return (70, 150, 70) if int((u + v) * 12) % 3 else (110, 186, 90)
        return None
    if kind == "monitor":
        if v < 0.8:
            if 0.07 < u < 0.93 and 0.08 < v < 0.72:
                k = int((v - 0.08) / 0.64 * 7)
                if k in (1, 3, 4) and 0.15 < u < (0.85 if k != 3 else 0.6):
                    return (220, 228, 255)
                return (40, 72, 170)
            return (206, 202, 190) if v < 0.76 else (176, 172, 160)
        if v < 0.92:
            return (150, 146, 136) if 0.42 < u < 0.58 else None
        return (150, 146, 136) if 0.22 < u < 0.78 else None
    if kind == "keyboard":
        if v < 0.2:
            return None
        if 0.02 < u < 0.98 and v > 0.35 and int(u * 18) % 2 == 0:
            return (220, 220, 214)
        return (70, 72, 80)
    if kind == "lamp":
        if v > 0.9:
            return c if 0.2 < u < 0.8 else None
        if v > 0.38:
            return shade(c, 0.8) if abs(u - 0.5 - (v - 0.9) * 0.3) < 0.07 else None
        hw = _hw(v, [(0.02, 0.18), (0.36, 0.42)])
        if du <= hw and v >= 0.02:
            return shade(c, 1.1 - 0.3 * u)
        return None
    if kind == "printer":
        if v < 0.2:
            return (248, 248, 244) if 0.26 < u < 0.74 else None
        if v < 0.3:
            return (190, 190, 186) if 0.12 < u < 0.88 else None
        if 0.6 < v < 0.68 and 0.15 < u < 0.85:
            return (40, 40, 46)
        if 0.82 < u < 0.88 and 0.38 < v < 0.46:
            return (90, 240, 110)
        return shade((214, 214, 208), 1 - 0.15 * v)
    if kind == "clock":
        d = math.hypot(u - 0.5, v - 0.5)
        if d > 0.5:
            return None
        if d > 0.4:
            return (60, 60, 70)
        a1, a2 = -1.2, 0.9
        for a, L in ((a1, 0.22), (a2, 0.34)):
            px, py = math.cos(a), math.sin(a)
            t = (u - 0.5) * px + (v - 0.5) * py
            if 0 <= t <= L and abs((u - 0.5) * py - (v - 0.5) * px) < 0.05:
                return (30, 30, 36)
        return (246, 246, 240)
    if kind == "poster":
        if u < 0.07 or u > 0.93 or v < 0.08 or v > 0.92:
            return (80, 56, 40)
        if v > 0.75:
            return (30, 30, 40) if not (0.25 < u < 0.75 and 0.8 < v < 0.86) else (240, 230, 200)
        if abs(u - 0.5) * 1.3 < (v - 0.22) and v > 0.22:
            return (240, 240, 250) if v < 0.38 else (90, 96, 130)
        return mix((250, 170, 110), (90, 140, 220), v / 0.75)
    return c


_SPR = {}


def sprite(kind, w, h, c):
    key = (kind, w, h, c)
    s = _SPR.get(key)
    if s is None:
        s = [[shape(kind, c, (x + 0.5) / w, (y + 0.5) / h) for x in range(w)] for y in range(h)]
        if len(_SPR) > 600:
            _SPR.clear()
        _SPR[key] = s
    return s


class Thing:
    def __init__(self, kind, x, y, w, h, color, rnd):
        self.kind = kind
        self.x, self.y, self.w, self.h = float(x), float(y), w, h
        self.color = color
        _, _, self.hp, self.mat, self.price = KINDS[kind]
        self.maxhp = self.hp
        self.vx = self.vy = 0.0
        self.state = "rest"                # rest, fall, broken
        self.on = None                     # what it stands on: a surface (x0, x1, y), another Thing or "wall"
        self.gentle = False                # a fresh delivery: the first landing does not hurt
        self.flash = 0.0
        self.wob = 0.0
        self.cracks = []
        cx, cy = rnd.uniform(0.3, 0.7) * w, rnd.uniform(0.3, 0.7) * h
        for _ in range(3):
            a = rnd.uniform(0, 6.28)
            x0, y0 = cx, cy
            for _ in range(int(max(w, h) * 0.7)):
                a += rnd.uniform(-0.7, 0.7)
                x0 += math.cos(a)
                y0 += math.sin(a) * 0.8
                self.cracks.append((int(x0), int(y0)))
        rnd.shuffle(self.cracks)

    @property
    def cx(self):
        return self.x + self.w / 2

    @property
    def top(self):
        return self.y

    @property
    def bottom(self):
        return self.y + self.h

    def contains(self, px, py, pad=0.6):
        return self.x - pad <= px <= self.x + self.w + pad and self.y - pad <= py <= self.y + self.h + pad

    def dist(self, px, py):
        dx = max(self.x - px, 0, px - (self.x + self.w))
        dy = max(self.y - py, 0, py - (self.y + self.h))
        return math.hypot(dx, dy)


# =============================================================================================
# The room
# =============================================================================================
class Room:
    def __init__(self, mode="Free Smash", seed=None, demo=False, W=100, H=58):
        self.mode, self.demo = mode, demo
        self.timed = mode == "One Minute"
        self.rnd = random.Random(seed)
        self.t = 0.0
        self.left = MINUTE
        self.tool = 0
        self.cool = 0.0
        self.cx, self.cy = 0.5, 0.5
        self.bill = 0
        self.smashed = 0
        self.stress = 100.0
        self.zen_t = None
        self.things, self.shards, self.fx, self.pops, self.crackers = [], [], [], [], []
        self.debris = {}
        self.shake = 0.0
        self.swing = 0.0
        self.deliver_at = None
        self.deliveries = 0
        self.over = self.paused = self.help = False
        self.last_tick = 99
        self.W = self.H = 0
        self.resize(W, H)

    def sfx(self, name, vol=1.0):
        if not self.demo:
            SND.play(name, vol=vol)

    # --- layout ----------------------------------------------------------------------------------
    def resize(self, W, H):
        W, H = max(40, W), max(24, H)
        if (W, H) == (self.W, self.H):
            return
        self.W, self.H = W, H
        self.floor = int(H * 0.82)
        self.shelf_x = (int(W * 0.03), int(W * 0.33))
        self.shelves = [int(H * 0.33), int(H * 0.56)]
        self.desk = (int(W * 0.52), int(W * 0.95), int(H * 0.6))
        self.surfaces = [(self.shelf_x[0], self.shelf_x[1], y) for y in self.shelves]
        self.surfaces.append(self.desk)
        self.surfaces.append((0, W, self.floor))
        self.things, self.shards, self.crackers = [], [], []
        self.debris = {}
        self.stock()

    def size(self, kind):
        w, h = KINDS[kind][:2]
        return max(2, int(round(w * self.H))), max(2, int(round(h * self.H)))

    def place(self, kind, x, surf, color=None, on=None, drop=False):
        w, h = self.size(kind)
        base = surf[2] if on is None else on.top
        y = base - h
        t = Thing(kind, x, y, w, h, color or self.rnd.choice(COLORS), self.rnd)
        t.on = on if on is not None else surf
        if drop:                                         # a delivery falls in from above, straight to its place
            t.dest = (y, t.on)
            t.y = y - self.H * (drop if isinstance(drop, float) else self.rnd.uniform(0.6, 1.0))
            t.state, t.gentle, t.on = "fall", True, None
        self.things.append(t)
        return t

    def stock(self, drop=False):
        """Fill the shelves, the desk, the floor and the wall with things."""
        rnd = self.rnd
        H = self.H
        for si, sy in enumerate(self.shelves):
            x = self.shelf_x[0] + 2
            while True:
                kind = rnd.choice(["plates", "mug", "vase", "bottle", "glass", "trophy", "mug", "glass", "plant"]
                                  if si == 0 else ["plates", "plates", "vase", "bottle", "mug", "plant", "glass"])
                w, h = self.size("plate" if kind == "plates" else kind)
                if x + w > self.shelf_x[1] - 1:
                    break
                if h > sy - (self.shelves[si - 1] if si else 0) - 2:
                    continue
                surf = (self.shelf_x[0], self.shelf_x[1], sy)
                if kind == "plates":                     # a stack: each plate stands on the one below
                    c = rnd.choice(COLORS[:4])
                    below = None
                    fall = rnd.uniform(0.6, 1.0) if drop else False    # the whole stack drops together
                    for _ in range(rnd.randint(3, 6)):
                        below = self.place("plate", x, surf, c, on=below, drop=fall)
                else:
                    self.place(kind, x, surf, drop=drop)
                x += w + rnd.randint(1, 3)
        x0, x1, dy = self.desk
        mw, _ = self.size("monitor")
        mx = rnd.randint(x0 + 2, max(x0 + 2, x0 + (x1 - x0) // 2 - mw // 2))
        self.place("monitor", mx, self.desk, drop=drop)
        kw, _ = self.size("keyboard")
        rest = [k for k in ("lamp", "mug", "plant", "trophy", "glass", "keyboard") if rnd.random() < 0.75]
        x = mx + mw + 2
        for kind in rest:
            w, _ = self.size(kind)
            if x + w <= x1 - 1:
                self.place(kind, x, self.desk, drop=drop)
                x += w + rnd.randint(1, 3)
        lx = mx - 2
        for kind in ("mug", "bottle"):
            w, _ = self.size(kind)
            if lx - w >= x0 + 1 and rnd.random() < 0.7:
                lx -= w
                self.place(kind, lx, self.desk, drop=drop)
                lx -= 2
        fl = (0, self.W, self.floor)
        pw, _ = self.size("printer")
        self.place("printer", int(self.W * 0.355), fl, drop=drop)
        vx = int(self.W * 0.355) + pw + 3
        if vx + self.size("vase")[0] < x0:
            self.place(rnd.choice(("vase", "plant")), vx, fl, drop=drop)
        # the wall: a clock and a poster above the desk
        cw, ch = self.size("clock")
        c = self.place("clock", int(self.W * 0.42), (0, 0, int(H * 0.1) + ch))
        p = self.place("poster", int(x0 + (x1 - x0) * 0.55), (0, 0, int(H * 0.12) + self.size("poster")[1]))
        for t in (c, p):
            t.on = "wall"
            t.state = "rest"
            t.gentle = False
            if drop:
                t.y = t.y - 0                              # wall things are hung, not dropped
        self.stocked = sum(t.price for t in self.things)
        self.deliver_at = None

    def intact_value(self):
        return sum(t.price for t in self.things if t.state != "broken")

    def deliver(self):
        """A new delivery: rubble off the shelves and the desk, fresh things fall in from above."""
        self.things = [t for t in self.things if t.state != "broken"]
        for t in list(self.things):                       # survivors get cleared away too
            self.things.remove(t)
        self.debris = {k: v for k, v in self.debris.items() if k[1] >= self.floor - 1}
        if len(self.debris) > self.W * 6:
            self.debris = {}
        self.stock(drop=True)
        self.deliveries += 1
        self.sfx("delivery")
        self.popup(self.W / 2, self.H * 0.2, "NEW DELIVERY", (255, 230, 140))

    # --- tools -----------------------------------------------------------------------------------
    def set_tool(self, i):
        if i != self.tool:
            self.tool = i % len(TOOLS)
            self.sfx("tool", 0.6)

    def use(self):
        """Use the tool at the hand. Returns the number of things hit."""
        if self.over or self.paused or self.cool > 0:
            return 0
        name, dmg, reach, knock, cool = TOOLS[self.tool]
        self.cool = cool
        self.swing = 0.15
        px, py = self.cx * self.W, self.cy * self.H
        if name == "Firecracker":
            self.crackers.append([px, py, 0.75])
            self.sfx("fuse", 0.7)
            return 0
        if name == "Bat":
            self.sfx("whoosh", 0.7)
        hits = [t for t in self.things if t.state != "broken" and t.dist(px, py) <= reach]
        hits.sort(key=lambda t: t.dist(px, py))
        if name == "Hammer":
            hits = hits[:1]
        if not hits:
            if name == "Hammer":
                self.sfx("thud", 0.4)
            self.scatter(px, py, reach + 2, 0.5)
            return 0
        for t in hits:
            self.damage(t, dmg, px, py, knock)
        return len(hits)

    def damage(self, t, dmg, px, py, knock=0.0):
        t.hp -= dmg
        t.flash = 0.08
        t.wob = 0.25
        if t.hp <= 0:
            self.shatter(t, px, py, 1.0 + knock * 0.3)
            return True
        self.sfx("dent" if t.mat in ("metal", "electronic", "plastic") else "thud", 0.6)
        if knock:                                         # sent flying, away from the blow
            side = 1 if t.cx >= px else -1
            t.vx = side * knock * self.H * self.rnd.uniform(0.35, 0.6)
            t.vy = -knock * self.H * self.rnd.uniform(0.25, 0.4)
            t.state = "fall"
            t.on = None
            t.gentle = False
        for _ in range(3):
            self.add_shard(px, py, mix(t.color, (255, 255, 255), 0.4), self.rnd.uniform(-1, 1) * 10,
                           self.rnd.uniform(-20, -5), settle=False)
        return False

    def shatter(self, t, px, py, force=1.0):
        t.state = "broken"
        self.smashed += 1
        self.sfx(t.mat)
        spr = sprite(t.kind, t.w, t.h, t.color)
        pix = [(x, y, c) for y, row in enumerate(spr) for x, c in enumerate(row) if c is not None]
        keep = 160
        if len(pix) > keep:
            pix = self.rnd.sample(pix, keep)
        H = self.H
        for x, y, c in pix:
            wx, wy = t.x + x, t.y + y
            dx, dy = wx - px, wy - py
            d = math.hypot(dx, dy) + 0.5
            sp = self.rnd.uniform(0.15, 0.55) * H * force
            vx = dx / d * sp + t.vx * 0.5 + self.rnd.uniform(-4, 4)
            vy = dy / d * sp * 0.6 - self.rnd.uniform(0.1, 0.4) * H * force + t.vy * 0.3
            self.add_shard(wx, wy, c, vx, vy, settle=self.rnd.random() < 0.85)
        if t.mat == "electronic":
            for _ in range(18):
                self.fx.append([t.cx, t.y + t.h * 0.4, self.rnd.uniform(-30, 30), self.rnd.uniform(-40, -5),
                                self.rnd.uniform(0.2, 0.6), "spark"])
            for _ in range(8):
                self.fx.append([t.cx + self.rnd.uniform(-t.w / 3, t.w / 3), t.y + t.h * 0.5, self.rnd.uniform(-3, 3),
                                self.rnd.uniform(-10, -4), self.rnd.uniform(1.0, 2.0), "smoke"])
        self.bill += t.price
        if not self.timed and self.stress > 0:
            self.stress = max(0.0, self.stress - 32.0 * t.price / max(1, self.stocked))
            if self.stress == 0 and self.zen_t is None:
                self.zen_t = self.t
                self.sfx("zen")
        self.popup(t.cx, t.y - 1, "+%d €" % t.price if self.timed else "%d €" % t.price,
                   (255, 230, 140) if t.price >= 100 else (240, 240, 240))
        self.shake = max(self.shake, 0.06 + min(0.2, t.price / 1200))
        for o in self.things:                            # whatever stood on it falls
            if o.on is t:
                o.on = None
                o.state = "fall"

    def explode(self, x, y):
        H = self.H
        R = H * 0.2
        self.sfx("boom")
        self.shake = 0.3
        self.fx.append([x, y, 0, 0, 0.14, "flash"])
        for _ in range(26):
            a = self.rnd.uniform(0, 6.28)
            s = self.rnd.uniform(20, 70)
            self.fx.append([x, y, math.cos(a) * s, math.sin(a) * s, self.rnd.uniform(0.2, 0.5), "spark"])
        for t in list(self.things):
            if t.state == "broken":
                continue
            d = t.dist(x, y)
            if d <= R:
                self.damage(t, 3 if d < R * 0.5 else 2, x, y, TOOLS[2][3] * (1 - d / R * 0.5))
        self.scatter(x, y, R, 1.0)

    def scatter(self, x, y, R, force):
        """Rubble near a blow jumps up again."""
        moved = [(k, c) for k, c in self.debris.items() if (k[0] - x) ** 2 + (k[1] - y) ** 2 <= R * R]
        for (kx, ky), c in moved[:200]:
            del self.debris[(kx, ky)]
            dx, dy = kx - x, ky - y
            d = math.hypot(dx, dy) + 0.5
            sp = self.rnd.uniform(0.2, 0.6) * self.H * force
            self.add_shard(kx, ky - 1, c, dx / d * sp, -abs(dy / d * sp) - self.rnd.uniform(5, 20) * force)

    def add_shard(self, x, y, c, vx, vy, settle=True):
        self.shards.append([x, y, vx, vy, c, settle, 4.0])
        if len(self.shards) > 1400:
            del self.shards[:len(self.shards) - 1400]

    def popup(self, x, y, txt, c):
        self.pops.append([x, y, txt, c, self.t + 1.0])
        self.pops = self.pops[-8:]

    # --- physics ---------------------------------------------------------------------------------
    def solid(self, x, y):
        if y >= self.floor:
            return True
        if (x, y) in self.debris:
            return True
        for s in self.surfaces[:-1]:
            if y == s[2] and s[0] <= x < s[1]:
                return True
        return False

    def update(self, dt):
        if self.paused or self.over:
            return
        self.t += dt
        if self.timed:
            self.left -= dt
            sec = int(math.ceil(self.left))
            if sec <= 10 and sec != self.last_tick and self.left > 0:
                self.last_tick = sec
                self.sfx("tick", 0.6)
            if self.left <= 0:
                self.left = 0
                self.over = True
                self.sfx("over")
                return
        self.cool = max(0.0, self.cool - dt)
        self.swing = max(0.0, self.swing - dt)
        self.shake = max(0.0, self.shake - dt)
        for c in self.crackers:
            c[2] -= dt
            if self.rnd.random() < dt * 30:
                self.fx.append([c[0], c[1] - 1, self.rnd.uniform(-12, 12), self.rnd.uniform(-18, -4), 0.2, "spark"])
        for c in [c for c in self.crackers if c[2] <= 0]:
            self.crackers.remove(c)
            self.explode(c[0], c[1])
        self.update_things(dt)
        self.update_shards(dt)
        for f in self.fx:
            f[4] -= dt
            f[0] += f[2] * dt
            f[1] += f[3] * dt
            if f[5] == "spark":
                f[3] += 60 * dt
        self.fx = [f for f in self.fx if f[4] > 0]
        self.pops = [p for p in self.pops if p[4] > self.t]
        if self.deliver_at is None and self.intact_value() < self.stocked * 0.15 and not self.crackers:
            self.deliver_at = self.t + 1.6
        if self.deliver_at is not None and self.t >= self.deliver_at:
            self.deliver()

    def update_things(self, dt):
        H, g = self.H, GRAV * self.H
        for t in self.things:
            t.flash = max(0.0, t.flash - dt)
            t.wob = max(0.0, t.wob - dt)
            if t.state == "broken":
                continue
            if t.state == "rest":
                on = t.on
                if isinstance(on, Thing) and (on.state != "rest" or not on.x - 1 <= t.cx <= on.x + on.w + 1):
                    t.state, t.on = "fall", None
                elif isinstance(on, tuple) and not on[0] <= t.cx <= on[1]:
                    t.state, t.on = "fall", None
                continue
            if t.on == "wall":
                t.on = None
            if t.gentle:
                t.vy += g * dt
                t.y += t.vy * dt
                if t.y >= t.dest[0]:
                    on = t.dest[1]
                    t.y, t.vy, t.vx, t.gentle = t.dest[0], 0.0, 0.0, False
                    t.state = "rest"
                    t.on = on if not isinstance(on, Thing) or on.state == "rest" else None
                    if t.on is None:
                        t.state = "fall"
                continue
            t.vy += g * dt
            t.vx *= 1 - dt * 0.3
            ny = t.y + t.vy * dt
            t.x += t.vx * dt
            if t.x < 0:
                t.x, t.vx = 0, -t.vx * 0.4
            elif t.x + t.w > self.W:
                t.x, t.vx = self.W - t.w, -t.vx * 0.4
            land = None
            if t.vy > 0:
                for s in self.surfaces:
                    if s[0] <= t.cx <= s[1] and t.bottom <= s[2] + 0.01 and ny + t.h >= s[2]:
                        if land is None or s[2] < land[0]:
                            land = (s[2], s)
                for o in self.things:
                    if o is t or o.state != "rest":
                        continue
                    if o.x <= t.cx <= o.x + o.w and t.bottom <= o.top + 0.01 and ny + t.h >= o.top:
                        if land is None or o.top < land[0]:
                            land = (o.top, o)
            if land is None:
                t.y = ny
                if t.y > H * 1.5:
                    t.state = "broken"
                continue
            speed = t.vy
            t.y = land[0] - t.h
            if t.gentle:
                hurt = False
                t.gentle = False
            else:
                hurt = speed > H * (0.55 if t.mat in FRAGILE else 0.9)
            if hurt and isinstance(land[1], Thing):          # whatever it lands on gets hit too
                self.damage(land[1], 1, t.cx, land[0])
            if hurt:
                if t.mat in FRAGILE or speed > H * 1.6:
                    self.shatter(t, t.cx, t.bottom + 1, 0.6)
                    continue
                if self.damage(t, 2, t.cx, t.bottom + 1):
                    continue
                t.state = "rest"
            t.vx, t.vy = 0.0, 0.0
            t.state, t.on = "rest", land[1]
            if speed > H * 0.25 and not hurt:
                self.sfx("thud", 0.4)

    def update_shards(self, dt):
        g = GRAV * self.H
        keep = []
        debris = self.debris
        for s in self.shards:
            s[6] -= dt
            s[3] += g * dt
            s[2] *= 1 - dt * 0.4
            nx, ny = s[0] + s[2] * dt, s[1] + s[3] * dt
            steps = int(max(abs(nx - s[0]), abs(ny - s[1]))) + 1
            x, y = s[0], s[1]
            stopped = False
            for k in range(1, steps + 1):
                tx = s[0] + (nx - s[0]) * k / steps
                ty = s[1] + (ny - s[1]) * k / steps
                ix, iy = int(tx), int(ty)
                if ix < 0 or ix >= self.W:
                    s[2] = -s[2] * 0.4
                    nx = x
                    break
                if s[3] > 0 and self.solid(ix, iy):
                    if s[3] > self.H * 0.5 and s[6] > 1:          # a bounce, then it settles
                        s[3] = -s[3] * 0.28
                        s[2] *= 0.6
                        s[6] = 1.0
                        nx, ny = x, y
                        break
                    stopped = True
                    break
                if s[3] < 0 and iy >= 0 and self.solid(ix, iy):
                    s[3] = 0
                    nx, ny = x, y
                    break
                x, y = tx, ty
            if stopped:
                ix, iy = int(x), int(y)
                if s[5]:
                    for _ in range(6):                         # sand: slide down past the pile
                        if not self.solid(ix, iy + 1):
                            iy += 1
                        elif not self.solid(ix - 1, iy + 1) and ix > 0:
                            ix, iy = ix - 1, iy + 1
                        elif not self.solid(ix + 1, iy + 1) and ix < self.W - 1:
                            ix, iy = ix + 1, iy + 1
                        else:
                            break
                    if iy >= 0 and (ix, iy) not in debris:
                        debris[(ix, iy)] = s[4]
                continue
            s[0], s[1] = nx, ny
            if s[1] < self.H * 1.2 and s[6] > -2:
                keep.append(s)
        self.shards = keep

    def aim(self, cx, cy):
        self.cx, self.cy = clamp(cx, 0.0, 0.999), clamp(cy, 0.0, 0.999)


# =============================================================================================
# The bot: auto mode and the title scene
# =============================================================================================
class Bot:
    def __init__(self, rnd=None, speed=1.0):
        self.rnd = rnd or random.Random()
        self.speed = speed
        self.target = None
        self.wait = 0.0

    def update(self, r, dt):
        if r.over:
            return
        self.wait -= dt
        t = self.target
        if t is None or t.state == "broken" or t not in r.things:
            t = self.target = self.pick(r)
            if t is None:
                return
            big = t.kind in ("monitor", "printer", "lamp", "trophy", "plant")
            crowd = sum(1 for o in r.things if o.state == "rest" and o.dist(t.cx, t.y + t.h / 2) < r.H * 0.12)
            if crowd >= 4 and self.rnd.random() < 0.35:
                r.set_tool(2)
            else:
                r.set_tool(1 if big and self.rnd.random() < 0.7 else 0)
        tx = (t.cx + self.rnd.uniform(-0.3, 0.3)) / r.W
        ty = (t.y + t.h * 0.5) / r.H
        dx, dy = tx - r.cx, ty - r.cy
        step = min(1.0, dt * 9 * self.speed)
        r.aim(r.cx + dx * step, r.cy + dy * step)
        if math.hypot(dx * r.W, dy * r.H) < max(1.0, min(t.w, t.h) * 0.4) and self.wait <= 0 and r.cool <= 0:
            r.use()
            self.wait = self.rnd.uniform(0.08, 0.3) / self.speed
            if r.tool == 2:
                self.target = None

    def pick(self, r):
        live = [t for t in r.things if t.state == "rest" and 0 <= t.y]
        if not live:
            return None
        hx, hy = r.cx * r.W, r.cy * r.H
        live.sort(key=lambda t: math.hypot(t.cx - hx, t.y - hy) - t.price * 0.05 + self.rnd.uniform(0, 8))
        return live[0]


# =============================================================================================
# Drawing
# =============================================================================================
def draw_room(cv, r):
    W, H = r.W, r.H
    px = cv.px
    a, b = WALLPAPER
    stripe = max(3, W // 24)
    for y in range(r.floor):
        k = y / max(1, r.floor)
        row = [mix(a if (x // stripe) % 2 == 0 else b, (150, 140, 120), k * 0.35) for x in range(W)]
        px[y] = row
    for x in range(W):                                           # a window with blinds, left of the clock
        pass
    wx0, wx1, wy0, wy1 = int(W * 0.37), int(W * 0.5), int(H * 0.28), int(H * 0.56)
    cv.rect(wx0 - 1, wy0 - 1, wx1 - wx0 + 2, wy1 - wy0 + 2, (236, 232, 222))
    for y in range(wy0, wy1):
        c = mix((150, 196, 236), (220, 236, 250), (y - wy0) / max(1, wy1 - wy0))
        if (y - wy0) % 3 == 2:
            c = (236, 232, 222)
        cv.rect(wx0, y, wx1 - wx0, 1, c)
    cv.rect(r.shelf_x[0] - 1, int(H * 0.1), 1, r.floor - int(H * 0.1), WOOD_D)
    cv.rect(r.shelf_x[1], int(H * 0.1), 1, r.floor - int(H * 0.1), WOOD_D)
    for y in range(r.floor - 1, r.floor + 1):
        cv.rect(0, y, W, 1, (90, 70, 56))
    for y in range(r.floor + 1, H):
        k = (y - r.floor) / max(1, H - r.floor)
        plank = max(4, W // 10)
        off = ((y - r.floor) // 2) * plank // 3
        row = []
        for x in range(W):
            c = shade(FLOOR, 1.05 - 0.25 * k)
            if (x + off) % plank == 0:
                c = shade(c, 0.8)
            row.append(c)
        px[y] = row
    for s in r.surfaces[:-1]:
        cv.rect(s[0], s[2], s[1] - s[0], 1, WOOD)
        cv.rect(s[0], s[2] + 1, s[1] - s[0], 1, WOOD_D)
    x0, x1, dy = r.desk
    cv.rect(x0 + 1, dy + 2, 2, r.floor - dy - 2, WOOD_D)
    cv.rect(x1 - 3, dy + 2, 2, r.floor - dy - 2, WOOD_D)
    cv.rect(x0 + (x1 - x0) // 2, dy + 2, (x1 - x0) // 2 - 3, max(2, (r.floor - dy) // 2), shade(WOOD, 0.85))


def draw_thing(cv, t, dx=0):
    spr = sprite(t.kind, t.w, t.h, t.color)
    wob = int(round(math.sin(t.wob * 60))) if t.wob > 0 else 0
    x0, y0 = int(round(t.x)) + wob + dx, int(round(t.y))
    px, W, H = cv.px, cv.W, cv.H
    flash = t.flash > 0
    for y, row in enumerate(spr):
        yy = y0 + y
        if not 0 <= yy < H:
            continue
        line = px[yy]
        for x, c in enumerate(row):
            if c is not None:
                xx = x0 + x
                if 0 <= xx < W:
                    line[xx] = (255, 255, 255) if flash else c
    dmg = 1 - t.hp / t.maxhp
    if dmg > 0 and t.state != "broken":
        n = int(len(t.cracks) * dmg * 0.9)
        for cx, cy in t.cracks[:n]:
            if 0 <= cx < t.w and 0 <= cy < t.h and spr[cy][cx] is not None:
                cv.set(x0 + cx, y0 + cy, shade(spr[cy][cx], 0.45))


def draw_hand(cv, r):
    x, y = int(r.cx * r.W), int(r.cy * r.H)
    name = TOOLS[r.tool][0]
    sw = r.swing / 0.15 if r.swing > 0 else 0
    if name == "Hammer":
        a = -0.9 + 1.4 * (1 - sw) if sw else 0.5
        hx, hy = x + 3 * math.cos(a), y - 3 * math.sin(a) - 1
        cv.line(x + 1, y + 2, hx + 2, hy + 3, (150, 104, 66))
        cv.rect(int(hx), int(hy), 3, 2, (150, 150, 160))
    elif name == "Bat":
        a = 2.4 - 2.6 * (1 - sw) if sw else 1.0
        bx, by = x + 6 * math.cos(a), y - 6 * math.sin(a)
        cv.line(x, y + 1, bx, by, (196, 150, 96))
        cv.line(x + 1, y + 1, bx + 1, by, (176, 130, 80))
        if sw:
            for k in range(6):
                aa = a + k * 0.25
                cv.set(x + 7 * math.cos(aa), y - 7 * math.sin(aa), (255, 255, 255))
    else:
        cv.rect(x - 1, y - 1, 3, 2, (220, 50, 50))
        cv.set(x + 1, y - 2, (240, 220, 120))
    c = (255, 255, 255) if r.cool <= 0 else (150, 150, 160)
    for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3)):
        cv.set(x + dx, y + dy, c)
    cv.set(x, y, (240, 60, 60))


def render(r, cols, rows, hud=True):
    play = rows - 1 if hud else rows
    if cols < 40 or play * 2 < 24:
        raise ValueError("too small for the room")     # the launcher then draws it bigger and shrinks it
    cv = Canvas(cols, rows)
    r.resize(cols, play * 2)
    draw_room(cv, r)
    px = cv.px
    for t in r.things:
        if t.on == "wall" and t.state != "broken":
            draw_thing(cv, t)
    for t in r.things:
        if t.on != "wall" and t.state != "broken":
            draw_thing(cv, t)
    for (x, y), c in r.debris.items():
        if 0 <= x < r.W and 0 <= y < r.H:
            px[y][x] = c
    for s in r.shards:
        cv.set(s[0], s[1], s[4])
    for c in r.crackers:
        cv.rect(int(c[0]) - 1, int(c[1]) - 1, 3, 2, (220, 50, 50))
        if int(r.t * 20) % 2:
            cv.set(c[0] + 1, c[1] - 2, (255, 240, 160))
    for f in r.fx:
        if f[5] == "flash":
            R = r.H * 0.2 * (1 - f[4] / 0.14 * 0.5)
            for y in range(int(f[1] - R), int(f[1] + R)):
                for x in range(int(f[0] - R), int(f[0] + R)):
                    d = math.hypot(x - f[0], y - f[1])
                    if d < R and 0 <= x < r.W and 0 <= y < r.H:
                        px[y][x] = mix(px[y][x], (255, 240, 180), 0.8 * (1 - d / R))
        elif f[5] == "spark":
            cv.set(f[0], f[1], (255, 220, 120) if f[4] > 0.15 else (240, 140, 60))
        else:
            if 0 <= int(f[0]) < r.W and 0 <= int(f[1]) < r.H:
                cv.set(f[0], f[1], mix(px[int(f[1])][int(f[0])], (90, 90, 96), min(1.0, f[4])))
    if r.shake > 0:
        s = int(round(math.sin(r.t * 80) * (1 + 2 * min(1.0, r.shake * 5))))
        if s:
            for y in range(r.H):
                row = px[y]
                px[y] = row[s:] + row[:s]
    draw_hand(cv, r)
    for x, y, txt, c, until in r.pops:
        rise = 1.0 - (until - r.t)
        row = int((y - rise * 6) // 2)
        col = int(x) - len(txt) // 2
        if 0 <= row < play:
            cv.put(max(0, min(cols - len(txt), col)), row, txt, c, None)
    if hud:
        draw_hud(cv, r)
    if r.paused:
        overlay(cv, HELP if r.help else PAUSE_LINES + ["", SND.label()])
    return cv


def draw_hud(cv, r):
    row = cv.rows - 1
    cv.put(0, row, " " * cv.cols, HUD_FG, HUD_BG)
    left = " DAMAGE %s € " % "{:,}".format(r.bill).replace(",", ".")
    cv.put(0, row, left, (16, 14, 20), (255, 140, 110))
    x = len(left) + 1
    for i, (name, *_rest) in enumerate(TOOLS):
        s = " %d %s " % (i + 1, name if cv.cols >= 92 or i == r.tool else name[:3])
        on = i == r.tool
        cv.put(x, row, s, (16, 14, 20) if on else (170, 170, 190), (240, 210, 120) if on else HUD_BG)
        x += len(s) + 1
    if r.timed:
        s = " %d:%02d " % (int(math.ceil(r.left)) // 60, int(math.ceil(r.left)) % 60)
        c = (255, 110, 100) if r.left <= 10 and int(r.t * 4) % 2 else HUD_FG
        cv.put(cv.cols - len(s) - 1, row, s, c, HUD_BG)
    else:
        n = 12
        fill = int(round(n * r.stress / 100))
        label = " stress " if r.stress > 0 else " zen "
        bx = cv.cols - n - len(label) - 2
        if bx > x:
            cv.put(bx, row, label, (200, 200, 214), HUD_BG)
            col = mix((110, 210, 120), (240, 80, 70), r.stress / 100)
            for i in range(n):
                cv.put(bx + len(label) + i, row, "█" if i < fill else "░", col if i < fill else (70, 70, 86), HUD_BG)
    if r.zen_t is not None and r.t - r.zen_t < 5:
        msg = "  Stress: gone. Feeling better?  "
        cv.center(2, msg, (20, 20, 26), (160, 230, 170))


def render_over(r, cv, record, auto=False):
    lines = ["TIME!", "", "damage bill   %s €" % "{:,}".format(r.bill).replace(",", "."), "things broken %d" % r.smashed,
             "deliveries    %d" % r.deliveries]
    if record:
        lines += ["", "** NEW RECORD **"]
    lines += ["", "auto mode: a new round starts" if auto else "Enter: again   Esc / Q: menu"]
    w = max(len(l) for l in lines) + 4
    x, y = max(0, (cv.cols - w) // 2), max(0, cv.rows // 2 - len(lines) // 2 - 1)
    cv.frame(x - 1, y * 2 - 1, w + 2, (len(lines) + 2) * 2 + 2, (240, 210, 120) if record else (210, 40, 60))
    cv.box(x, y, [l.ljust(w - 4) if i else l.center(w - 4) for i, l in enumerate(lines)], (240, 240, 246), (24, 22, 44))


# =============================================================================================
# Title, auto mode, play
# =============================================================================================
class TitleDemo:
    def __init__(self):
        self.k = 0
        self.new()

    def new(self):
        self.r = Room("Free Smash", seed=70 + self.k, demo=True)
        self.bot = Bot(random.Random(self.k), speed=0.8)
        self.k += 1

    def scene(self, cols, rows, dt):
        dt = min(dt, 0.1)
        self.bot.update(self.r, dt)
        self.r.update(dt)
        if self.r.t > 60:
            self.new()
        return render(self.r, cols, rows, hud=False)


def render_menu(demo, cols, rows, sel, dt, help_=False, mode=0):
    cv = demo.scene(cols, rows, dt)
    rec = load_scores().get(GAME, {}).get("One Minute")
    best = None if rec is None else "best One Minute: %s €" % "{:,}".format(rec).replace(",", ".")
    items = ["%-11s %s" % m for m in MODES] + ["%-11s watch it play %s" % (AUTO_LABEL, MODES[mode][0])]
    title_screen(cv, "BREAKROOM", "an office full of things that had it coming", items, sel, best,
                 extra=["", "mouse: aim and click    keys: arrows + Space, 1 2 3"],
                 keys="Up/Down choose   Enter start   M %s   ? help   Esc back" % SND.label().lower(),
                 help_lines=HELP, show_help=help_)
    return cv


def too_small(term):
    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (60x22).")


def apply_mouse(term, r, cols, rows):
    take = getattr(term, "take_mouse", None)
    if not take:
        return
    play = rows - 1
    for kind, col, row in take():
        if row >= play and kind == "move":
            continue
        r.aim((col + 0.5) / cols, min(play * 2 - 1, row * 2 + 1) / (play * 2))
        if kind == "left":
            r.use()
        elif kind in ("right", "middle", "wheeldown"):
            r.set_tool(r.tool + 1)
        elif kind == "wheelup":
            r.set_tool(r.tool - 1)


def game_key(r, k):
    step = 0.03
    if k in ("left", "a"):
        r.aim(r.cx - step, r.cy)
    elif k in ("right", "d"):
        r.aim(r.cx + step, r.cy)
    elif k in ("up", "w"):
        r.aim(r.cx, r.cy - step * 1.6)
    elif k in ("down", "s"):
        r.aim(r.cx, r.cy + step * 1.6)
    elif k in (" ", "enter", "f"):
        r.use()
    elif k in ("1", "2", "3"):
        r.set_tool(int(k) - 1)
    elif k == "tab":
        r.set_tool(r.tool + 1)
    elif k == "n":
        r.deliver()


def run_auto(term, mode):
    auto = AutoMode()
    while True:
        r = Room(MODES[mode][0])
        bot = Bot()
        last = time.time()
        over_at = None
        while True:
            now = time.time()
            dt = min(0.1, now - last)
            last = now
            for k in term.keys(0):
                a = auto.key(k)
                if a == "stop":
                    return
                if a == "sound" and SND.toggle():
                    SND.play("sound_on")
            if getattr(term, "take_mouse", None):
                term.take_mouse()
            sim = auto.scale(dt)
            n = max(1, int(math.ceil(sim / (1 / 60)))) if sim else 0
            for _ in range(n):
                bot.update(r, sim / n)
                r.update(sim / n)
            if not r.timed and r.t > 150:
                break
            if r.over and over_at is None:
                over_at = now
            if over_at is not None:
                if auto.paused:
                    over_at += dt
                elif now - over_at > 4:
                    break
            cols, rows = term.size()
            if cols < 60 or rows < 22:
                too_small(term)
                time.sleep(0.2)
                continue
            cv = render(r, cols, rows)
            if r.over:
                render_over(r, cv, None, auto=True)
            auto.banner(cv, extra=MODES[mode][0])
            term.write(cv.emit())
            time.sleep(max(0, 1 / 50 - (time.time() - now)))


def play(term, mode):
    while True:
        r = Room(MODES[mode][0])
        last = time.time()
        record = None
        again = False
        while True:
            now = time.time()
            cols, rows = term.size()
            r.update(min(0.1, now - last))
            last = now
            if not r.paused and not r.over:
                apply_mouse(term, r, cols, rows)
            elif getattr(term, "take_mouse", None):
                term.take_mouse()
            for k in term.keys(0):
                if r.over:
                    if k in ("q", "esc"):
                        return
                    if k in ("enter", " "):
                        again = True
                    continue
                a = shared_key(k, r.paused)
                if a == "pause":
                    r.paused = True
                    SND.play("pause")
                elif a == "resume":
                    r.paused = r.help = False
                elif a == "quit":
                    return
                elif a == "help":
                    r.help = not r.help
                    r.paused = True
                elif a == "sound":
                    if SND.toggle():
                        SND.play("sound_on")
                elif a is None:
                    game_key(r, k)
            if again:
                break
            if r.over and record is None:
                record = submit(GAME, r.mode, r.bill) if r.bill > 0 else False
            if cols < 60 or rows < 22:
                too_small(term)
                time.sleep(0.2)
                continue
            cv = render(r, cols, rows)
            if r.over:
                render_over(r, cv, record)
            term.write(cv.emit())
            time.sleep(max(0, 1 / 50 - (time.time() - now)))


def main():
    with MouseTerminal() as term:
        demo = TitleDemo()
        sel, help_, mode = 0, False, 0
        n = len(MODES) + 1
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
            term.write(render_menu(demo, cols, rows, sel, min(0.1, now - last), help_, mode).emit())
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
            if sel < len(MODES):
                mode = sel
            if go:
                if sel == len(MODES):
                    run_auto(term, mode)
                else:
                    play(term, sel)
                last = time.time()


# =============================================================================================
# Self-test:  python3 breakroom.py --selftest
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
    quiet, SND.enabled = SND.enabled, False
    try:
        r = Room("Free Smash", seed=4, W=cols, H=(rows - 1) * 2)
        bot = Bot(random.Random(2))
        for _ in range(int(9 / (1 / 60))):
            bot.update(r, 1 / 60)
            r.update(1 / 60)
        cv = render(r, cols, rows)
    finally:
        SND.enabled = quiet
    return cv


def aim_at(r, t):
    r.aim((t.cx) / r.W, (t.y + t.h / 2) / r.H)


def selftest():
    import os
    import tempfile
    import arcadekit
    t0 = time.time()
    tmp = os.path.join(tempfile.mkdtemp(), "scores.json")
    arcadekit.SCORES_PATH = tmp
    SND.enabled = False
    r = Room("Free Smash", seed=1, W=100, H=60)
    kinds = {t.kind for t in r.things}
    assert {"monitor", "printer", "clock", "poster"} <= kinds, kinds
    # the hammer breaks a mug in one blow; its shards end up as rubble
    mug = next(t for t in r.things if t.kind in ("mug", "glass", "bottle") and t.on != "wall")
    aim_at(r, mug)
    assert r.use() == 1 and mug.state == "broken" and r.bill == mug.price and r.stress < 100
    for _ in range(240):
        r.update(1 / 60)
    assert len(r.debris) > 5, "no rubble"
    assert all(y < r.H for _, y in r.debris)
    # a stack of plates: the bottom one goes, the rest fall and break
    stack = [t for t in r.things if t.kind == "plate" and isinstance(t.on, tuple)]
    if stack:
        bottom = stack[0]
        above = [t for t in r.things if t.on is bottom]
        aim_at(r, bottom)
        r.cool = 0
        r.use()
        assert bottom.state == "broken" and all(t.state == "fall" for t in above)
    # the bat knocks the monitor off the desk; it breaks on the floor
    mon = next(t for t in r.things if t.kind == "monitor")
    r.things = [t for t in r.things if t is mon or t.on not in (r.desk, r.surfaces[-1])]
    mon.x = r.desk[0] + 1
    r.set_tool(1)
    r.cool = 0
    r.aim((mon.x + mon.w - 1) / r.W, (mon.y + mon.h / 2) / r.H)
    r.use()
    assert mon.hp == 2 and mon.state == "fall" and mon.vx < 0
    for _ in range(300):
        r.update(1 / 60)
        if mon.state != "fall":
            break
    assert mon.state == "broken", (mon.state, mon.hp)
    # the firecracker: a fuse, then a bang that breaks what is near
    r = Room("Free Smash", seed=1, W=100, H=60)
    r.set_tool(2)
    r.cool = 0
    pr = next(t for t in r.things if t.kind == "printer")
    aim_at(r, pr)
    r.use()
    assert r.crackers
    before = r.smashed
    for _ in range(60):
        r.update(1 / 60)
    assert not r.crackers and pr.hp < KINDS["printer"][2] and r.smashed >= before
    # a delivery refills the room; fresh things land unharmed
    r.deliver()
    for _ in range(240):
        r.update(1 / 60)
    live = [t for t in r.things if t.state != "broken"]
    assert len(live) >= 15 and all(t.state == "rest" for t in live), [(t.kind, t.state) for t in live if t.state != "rest"]
    # One Minute: the clock ends it
    r = Room("One Minute", seed=2)
    r.left = 0.05
    r.update(0.1)
    assert r.over
    # the bot smashes rooms and the stress goes
    r = Room("Free Smash", seed=3, demo=True)
    bot = Bot(random.Random(3))
    for i in range(int(90 * 30)):
        bot.update(r, 1 / 30)
        r.update(1 / 30)
        if i % 300 == 0:
            render(r, 100, 32).emit()
    assert r.smashed > 60 and r.deliveries >= 1 and r.stress < 50, (r.smashed, r.deliveries, r.stress)
    cv = render(r, 100, 32)
    render_over(r, cv, True)
    cv.emit()
    # mouse: aim, smash, change tool
    r = Room("Free Smash", seed=4)
    term = FakeTerm([], [(0, ("move", 10, 10)), (0, ("right", 10, 10)), (0, ("wheelup", 10, 10))])
    apply_mouse(term, r, 100, 32)
    assert r.tool == 0 and abs(r.cx - 0.105) < 1e-6
    # every size, the title, auto mode
    for cols, rows in ((60, 22), (100, 32), (180, 50)):
        d = TitleDemo()
        for i in range(40):
            d.scene(cols, rows, 0.1)
        for sel in range(3):
            render_menu(d, cols, rows, sel, 0.05, sel == 2, 1).emit()
    try:
        TitleDemo().scene(24, 8, 0.1)
        raise AssertionError("a tiny scene should refuse")
    except ValueError:
        pass
    term = FakeTerm([(0.1, "+"), (0.2, "+"), (0.5, " "), (0.6, "?"), (0.7, "x"), (0.8, " "), (1.2, "esc")])
    run_auto(term, 1)
    assert term.frames > 5 and not term.script
    assert not os.path.exists(tmp), "auto mode wrote a score"
    print("Self-test ok: hammer, rubble, plate stacks, bat knock-off, firecracker, delivery, clock, a bot session, "
          "mouse, title at three sizes, auto mode (%.1fs)" % (time.time() - t0))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
