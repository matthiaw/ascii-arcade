#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""HEATHSHOT - a shooting gallery on the heath, for letting off steam.

Puffwings - round, fluffy, slightly smug birds - cross the heath at three distances: the far ones are tiny and
worth the most. Eight shells in the gun, reload with a right click (or just keep clicking). Hits in quick
succession build a combo. Puffwings peek over the stone wall, a golden one darts past now and then, a balloon
drifts over with a pilot in its basket, and the windmill's sails ring when hit. Leave the sheep alone.

Point with the mouse and click, or steer the sight with the arrow keys and press Space. Move the sight to the
edge of the screen and the view pans along the heath.

Modes: 90 Seconds (score against the clock) and Zen (no clock, no score, just shooting).

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
Run:        python3 heathshot.py
Self-test:  python3 heathshot.py --selftest
"""
import math
import random
import sys
import time

from arcadekit import (AUTO_LABEL, PAUSE_LINES, AutoMode, Canvas, MouseTerminal, clamp, footer, load_scores, mix,
                       overlay, shade, shared_key, submit, title_screen)
from arcadesound import Sound

GAME = "heathshot"
MODES = [("90 Seconds", "score against the clock"), ("Zen", "no clock, just shooting (no record kept)")]
ROUND = 90.0
MAG = 8                    # shells in the gun
RELOAD = 0.55              # seconds
LF = (0.32, 0.62, 1.0)     # parallax of the far, middle and near layer
WORLD = 1.9                # the heath is this many screens wide
COMBO_GAP = 1.4            # seconds between hits that still count as a combo
VALUE = (25, 10, 5)        # a puffwing far, middle, near
PEEK, GOLD, BALLOON, SHEEP = 15, 100, 50, -25
PUFF_COLS = [(250, 150, 182), (130, 196, 250), (140, 222, 176), (250, 222, 110), (198, 160, 240), (252, 168, 96)]
GOLD_C = (255, 214, 70)
SKIES = [  # top, horizon, sun, far hills, heather, grass
    dict(name="morning", top=(96, 160, 232), hor=(236, 222, 210), sun=(255, 248, 220), far=(140, 156, 196),
         heath=(150, 96, 150), grass=(110, 170, 80), cloud=(255, 255, 255)),
    dict(name="afternoon", top=(70, 132, 222), hor=(196, 224, 246), sun=(255, 252, 236), far=(120, 150, 186),
         heath=(136, 88, 144), grass=(104, 166, 74), cloud=(250, 252, 255)),
    dict(name="evening", top=(66, 54, 128), hor=(252, 166, 110), sun=(255, 220, 150), far=(112, 84, 132),
         heath=(118, 66, 118), grass=(96, 132, 70), cloud=(255, 200, 186)),
]
WALL, WALL_D = (150, 144, 136), (104, 98, 94)
HUD_BG, HUD_FG = (16, 14, 26), (226, 226, 236)
SND = Sound(GAME, {
    "shot": [dict(w="noise", f=3200, f2=300, d=0.16, v=0.5), dict(w="sine", f=170, f2=55, d=0.14, v=0.55, at=0)],
    "dry": [dict(w="square", f=1800, d=0.012, v=0.18, duty=0.2)],
    "reload": [dict(w="noise", f=2600, f2=1200, d=0.05, v=0.3), dict(w="square", f=330, d=0.03, v=0.2, duty=0.3, at=0),
               dict(w="noise", f=3000, f2=1500, d=0.05, v=0.34, at=0.32),
               dict(w="square", f=440, d=0.03, v=0.22, duty=0.3, at=0.32)],
    "poof": [dict(w="noise", f=6000, f2=1500, d=0.16, v=0.32), dict(w="tri", f=700, f2=1300, d=0.1, v=0.3, at=0.02)],
    "poof_far": [dict(w="noise", f=7000, f2=2500, d=0.1, v=0.24), dict(w="tri", f=1200, f2=2000, d=0.08, v=0.26, at=0.01)],
    "squawk": [dict(w="square", f=900, f2=520, d=0.12, v=0.2, duty=0.3, vib=(30, 1.0))],
    "gold": [dict(w="tri", f=f, d=0.06, v=0.32) for f in (1047, 1319, 1568, 2093)] +
            [dict(w="sine", f=2637, d=0.4, v=0.2, vib=(9, 0.2), r="lin")],
    "baa": [dict(w="saw", f=260, f2=236, d=0.42, v=0.26, vib=(7, 0.7), r="lin")],
    "pop": [dict(w="noise", f=5000, f2=400, d=0.3, v=0.55), dict(w="sine", f=400, f2=90, d=0.2, v=0.4, at=0)],
    "tink": [dict(w="tri", f=2400, d=0.18, v=0.25), dict(w="tri", f=3600, d=0.12, v=0.12, at=0)],
    "thock": [dict(w="noise", f=900, f2=200, d=0.06, v=0.3), dict(w="tri", f=180, f2=120, d=0.05, v=0.25, at=0)],
    "combo": [dict(w="square", f=784, d=0.04, v=0.2, duty=0.25), dict(w="square", f=1175, d=0.08, v=0.2, duty=0.25)],
    "tick": [dict(w="tri", f=1568, d=0.03, v=0.18)],
    "over": [dict(w="square", f=f, d=0.09, v=0.26, duty=0.25) for f in (523, 659, 784)] +
            [dict(w="tri", f=1047, d=0.45, v=0.4, vib=(6, 0.25), r="lin")],
    "menu": [dict(w="tri", f=660, d=0.025, v=0.2)],
    "start": [dict(w="noise", f=3200, f2=300, d=0.16, v=0.4), dict(w="square", f=523, d=0.06, v=0.3, duty=0.25, at=0.15),
              dict(w="square", f=784, d=0.14, v=0.3, duty=0.25)],
    "pause": [dict(w="tri", f=523, f2=392, d=0.07, v=0.22)],
    "sound_on": [dict(w="tri", f=440, d=0.06, v=0.35), dict(w="tri", f=880, d=0.12, v=0.35)],
})
HELP = [
    "HEATHSHOT - keys",
    "",
    "Mouse                 aim",
    "Left click            fire (empty gun: reloads)",
    "Right click / R       reload",
    "Arrows / WASD         move the sight",
    "Space / Enter         fire",
    "Sight at the edge     the view pans (also Q / E, wheel)",
    "Esc / P               pause     ? help",
    "",
    "Far puffwings 25, middle 10, near 5, peekers 15,",
    "golden 100, the balloon 50. Sheep: -25.",
    "Quick hits build a combo (up to x4).",
    "Zen: no clock; the score counts but no record is kept.",
]


def wave(u, parts):
    return sum(a * math.sin(6.2832 * f * u + p) for f, a, p in parts)


FAR_W = ((2.3, 0.05, 1.0), (5.1, 0.025, 2.0), (11.0, 0.008, 0.4))
MID_W = ((3.1, 0.03, 0.3), (8.3, 0.015, 1.0), (17.0, 0.005, 2.2))
WALL_TOP, WALL_BOT = 0.80, 0.90


def hsh(x, y):
    return ((x * 73856093) ^ (y * 19349663)) & 0xffff


class Target:
    """Anything that can be shot: kind puff, gold, peek, balloon or sheep, at depth d (0 far .. 2 near).
    x is a fraction of its layer's width, y a fraction of the screen height, r a fraction of the height."""

    def __init__(self, kind, d, x, y, vx, r, color, rnd):
        self.kind, self.d, self.x, self.y0, self.vx, self.r, self.color = kind, d, x, y, vx, r, color
        self.y = y
        self.t = 0.0
        self.phase = rnd.uniform(0, 6.28)
        self.amp = rnd.uniform(0.01, 0.04)
        self.freq = rnd.uniform(1.2, 2.6)
        self.state = "fly"
        self.vy = 0.0
        self.hp = 3 if kind == "balloon" else 1
        self.flash = 0.0
        self.p = 0.0               # peekers: how far up (0..1); sheep: walk timer
        self.life = rnd.uniform(1.0, 1.8)

    @property
    def face(self):
        return 1 if self.vx >= 0 else -1


class Game:
    def __init__(self, mode="90 Seconds", seed=None, demo=False, W=100, H=58):
        self.mode, self.demo = mode, demo
        self.zen = mode == "Zen"
        self.rnd = random.Random(seed)
        self.sky = self.rnd.choice(SKIES)
        self.W, self.H = W, H
        self.scroll = self.rnd.uniform(0.3, 0.7)        # 0..1 of the panning range
        self.cx, self.cy = 0.5, 0.45                    # the sight (fractions of the screen)
        self.t = 0.0
        self.left = ROUND
        self.ammo, self.reloading = MAG, 0.0
        self.score = self.hits = self.shots = 0
        self.shown = 0.0
        self.chain, self.chain_t, self.best_chain = 0, -9.0, 0
        self.golds = self.sheep_hit = 0
        self.targets, self.parts, self.pops, self.holes = [], [], [], []
        self.flash = 0.0
        self.kick = 0.0
        self.mill_a, self.mill_spin = 0.0, 0.9
        self.next_peek, self.next_gold, self.next_balloon = 3.0, self.rnd.uniform(14, 24), self.rnd.uniform(18, 30)
        self.next_spawn = 0.0
        self.over = self.paused = self.help = False
        self.last_tick = 99
        self.clouds = [[self.rnd.random(), self.rnd.uniform(0.05, 0.3), self.rnd.uniform(0.05, 0.11)]
                       for _ in range(5)]
        for _ in range(2):
            self.add_sheep()
        for _ in range(4):
            self.spawn_puff(anywhere=True)

    # --- geometry --------------------------------------------------------------------------------
    def resize(self, W, H):
        self.W, self.H = max(10, W), max(10, H)

    @property
    def WW(self):
        return int(self.W * WORLD)

    def lw(self, d):
        return self.W + (self.WW - self.W) * LF[d]

    def scroll_px(self):
        return self.scroll * (self.WW - self.W)

    def sx(self, x, d):
        return x * self.lw(d) - self.scroll_px() * LF[d]

    def ux(self, sx, d):
        return (sx + self.scroll_px() * LF[d]) / self.lw(d)

    def mid_ground(self, u):
        return 0.64 + wave(u, MID_W)

    def sfx(self, name, vol=1.0):
        if not self.demo:
            SND.play(name, vol=vol)

    # --- spawning --------------------------------------------------------------------------------
    def progress(self):
        return 0.0 if self.zen else clamp(1 - self.left / ROUND, 0, 1)

    def spawn_puff(self, anywhere=False, d=None, kind="puff"):
        rnd = self.rnd
        if d is None:
            d = rnd.choices((0, 1, 2), (0.36, 0.36, 0.28))[0]
        side = rnd.choice((-1, 1))
        speed = (rnd.uniform(0.035, 0.06), rnd.uniform(0.06, 0.095), rnd.uniform(0.09, 0.14))[d]
        speed *= 1 + 0.45 * self.progress()
        r = (0.027, 0.05, 0.07)[d] * rnd.uniform(0.9, 1.1)
        y = rnd.uniform((0.1, 0.12, 0.12)[d], (0.42, 0.5, 0.58)[d])
        x = rnd.uniform(0.05, 0.95) if anywhere else (-0.04 if side > 0 else 1.04)
        color = GOLD_C if kind == "gold" else rnd.choice(PUFF_COLS)
        if kind == "gold":
            speed *= 1.7
        t = Target(kind, d, x, y, speed * side, r, color, rnd)
        self.targets.append(t)
        return t

    def add_sheep(self):
        rnd = self.rnd
        t = Target("sheep", 1, rnd.uniform(0.1, 0.9), 0, rnd.choice((-1, 1)) * 0.006, 0.034, (244, 242, 236), rnd)
        t.p = rnd.uniform(1, 4)
        self.targets.append(t)

    def spawn_peek(self):
        rnd = self.rnd
        u = self.ux(rnd.uniform(0.1, 0.9) * self.W, 2)       # somewhere on the screen right now
        t = Target("peek", 2, u, WALL_TOP, 0, 0.06, rnd.choice(PUFF_COLS), rnd)
        t.vx = rnd.choice((-1e-6, 1e-6))
        self.targets.append(t)

    def spawn_balloon(self):
        rnd = self.rnd
        side = rnd.choice((-1, 1))
        t = Target("balloon", 1, -0.05 if side > 0 else 1.05, rnd.uniform(0.12, 0.2), side * 0.022, 0.075,
                   rnd.choice(((236, 80, 80), (80, 150, 236), (240, 180, 60))), rnd)
        t.amp = 0.01
        self.targets.append(t)

    def want(self):
        return 9 if self.zen else int(4 + 6 * self.progress())

    # --- the gun ---------------------------------------------------------------------------------
    def reload(self):
        if self.reloading <= 0 and self.ammo < MAG:
            self.reloading = RELOAD
            self.sfx("reload")

    def fire(self):
        """One shot at the sight. Returns what was hit (a Target, 'mill', 'wall' or None)."""
        if self.over or self.paused:
            return None
        if self.reloading > 0:
            self.sfx("dry")
            return None
        if self.ammo <= 0:
            self.reload()
            return None
        self.ammo -= 1
        self.shots += 1
        self.flash = 0.08
        self.kick = 0.06
        self.sfx("shot", 0.8)
        px, py = self.cx * self.W, self.cy * self.H
        hit = self.hit_test(px, py)
        if isinstance(hit, Target):
            self.shoot(hit, px, py)
        elif hit == "mill":
            self.mill_spin = min(9.0, self.mill_spin + 3.5)
            self.sfx("tink")
            self.popup(self.ux(px, 1), py / self.H, 1, "ting!", (230, 230, 250))
        elif hit == "wall":
            self.holes.append((self.ux(px, 2), py / self.H))
            self.holes = self.holes[-60:]
            self.sfx("thock", 0.7)
            for _ in range(5):
                self.part(self.ux(px, 2), py / self.H, 2, mix(WALL, (60, 56, 52), 0.5), "dust")
        if self.ammo == 0 and not self.demo:
            pass
        return hit

    def hit_test(self, px, py):
        H = self.H
        order = sorted((t for t in self.targets if t.state in ("fly", "peek") or (t.kind == "sheep" and t.state == "fly")),
                       key=lambda t: -t.d)
        for t in order:
            if self.inside(t, px, py):
                return t
        if py / H >= WALL_TOP or self.tree_hit(px, py):
            return "wall"
        mx, my, L = self.mill_geom()
        for k in range(4):
            a = self.mill_a + k * math.pi / 2
            ex, ey = mx + math.cos(a) * L, my + math.sin(a) * L
            if seg_dist(px, py, mx, my, ex, ey) < 1.6:
                return "mill"
        return None

    def inside(self, t, px, py):
        H = self.H
        x, y = self.sx(t.x, t.d), t.y * H
        r = t.r * H
        if t.kind == "balloon":
            return (px - x) ** 2 + (py - y) ** 2 <= (r + 0.8) ** 2 or (abs(px - x) <= r * 0.4 and y + r <= py <= y + r * 1.9)
        if t.kind == "peek":
            if py > WALL_TOP * H:
                return False
            y = WALL_TOP * H + r * 2.1 * (1 - t.p) - r * 0.9
        if t.kind == "sheep":
            y = self.mid_ground(t.x) * H - r * 0.9
            return ((px - x) / (r * 1.4 + 0.8)) ** 2 + ((py - y) / (r + 0.8)) ** 2 <= 1
        return ((px - x) / (r * 1.15 + 0.9)) ** 2 + ((py - y) / (r + 0.9)) ** 2 <= 1

    def tree_hit(self, px, py):
        tx, ty, tr, trunk = self.tree_geom()
        return (px - tx) ** 2 + ((py - ty) * 1.1) ** 2 <= tr * tr or (abs(px - tx) <= trunk and py >= ty)

    def tree_geom(self):
        H = self.H
        return self.sx(0.1, 2), H * 0.42, H * 0.2, max(1.5, H * 0.035)

    def mill_geom(self):
        H = self.H
        u = 0.47
        return self.sx(u, 1), (self.mid_ground(u) - 0.2) * H, H * 0.13

    def shoot(self, t, px, py):
        if t.kind == "sheep":
            t.state = "flee"
            t.vx = (0.08 if px < self.sx(t.x, 1) else -0.08)
            self.sheep_hit += 1
            self.add_score(SHEEP, t, (236, 90, 80), combo=False)
            self.chain = 0
            self.sfx("baa")
            return
        if t.kind == "balloon":
            t.hp -= 1
            t.flash = 0.12
            if t.hp > 0:
                self.sfx("thock")
                return
            t.state = "fall"
            t.vy = 0.0
            self.sfx("pop")
            for _ in range(36):
                self.part(t.x, t.y, t.d, self.rnd.choice(PUFF_COLS + [t.color]), "confetti", 0.6)
            self.add_score(BALLOON, t, GOLD_C)
            return
        self.hits += 1
        now = self.t
        self.chain = self.chain + 1 if now - self.chain_t <= COMBO_GAP else 1
        self.chain_t = now
        self.best_chain = max(self.best_chain, self.chain)
        if t.kind == "gold":
            self.golds += 1
            self.sfx("gold")
            for _ in range(24):
                self.part(t.x, t.y, t.d, (255, 250, 200), "spark", 0.5)
        else:
            self.sfx("poof" if t.d else "poof_far")
            if self.rnd.random() < 0.3 and t.d:
                self.sfx("squawk", 0.7)
        n = (10, 18, 28)[t.d]
        for _ in range(n):
            self.part(t.x, t.y if t.kind != "peek" else WALL_TOP - t.r * (2 * t.p - 0.6), t.d,
                      mix(t.color, (255, 255, 255), self.rnd.uniform(0, 0.5)), "feather")
        value = GOLD if t.kind == "gold" else PEEK if t.kind == "peek" else VALUE[t.d]
        self.add_score(value, t, GOLD_C if t.kind == "gold" else (255, 255, 255))
        if t.kind == "peek":
            t.state = "gone"
        elif t.d == 0:
            t.state = "gone"
        else:
            t.state = "fall"
            t.vy = -0.15
        self.kick = 0.1

    def mult(self):
        return min(4, 1 + (self.chain - 1) // 3) if self.chain else 1

    def add_score(self, value, t, color, combo=True):
        m = self.mult() if combo and value > 0 else 1
        self.score = max(0, self.score + value * m)
        if combo and m > 1 and self.chain % 3 == 1:
            self.sfx("combo", 0.6)
        txt = "%+d" % (value * m)
        if m > 1:
            txt += " x%d" % m
        y = t.y if t.kind not in ("peek", "sheep") else (WALL_TOP - 0.1 if t.kind == "peek" else self.mid_ground(t.x) - 0.08)
        self.popup(t.x, y - t.r - 0.03, t.d, txt, color)

    def popup(self, x, y, d, txt, color):
        self.pops.append([x, y, d, txt, color, self.t + 0.9])
        self.pops = self.pops[-8:]

    def part(self, x, y, d, color, kind, spread=1.0):
        rnd = self.rnd
        a = rnd.uniform(0, 6.28)
        sp = rnd.uniform(0.05, 0.25) * spread * (0.6 + 0.4 * d)
        vy = math.sin(a) * sp - (0.12 if kind == "confetti" else 0.04)
        life = {"feather": rnd.uniform(1.6, 2.8), "spark": rnd.uniform(0.3, 0.7), "dust": rnd.uniform(0.3, 0.6),
                "confetti": rnd.uniform(1.5, 2.5)}[kind]
        lw = self.lw(d) / max(1, self.H)
        self.parts.append([x, y, math.cos(a) * sp / lw, vy, life, life, color, d, kind, rnd.uniform(0, 6.28)])
        if len(self.parts) > 500:
            del self.parts[:len(self.parts) - 500]

    # --- the clock -------------------------------------------------------------------------------
    def update(self, dt):
        if self.paused or self.over:
            return
        self.t += dt
        if not self.zen:
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
        if self.reloading > 0:
            self.reloading -= dt
            if self.reloading <= 0:
                self.ammo = MAG
        self.flash = max(0.0, self.flash - dt)
        self.kick = max(0.0, self.kick - dt)
        gap = self.score - self.shown                      # the big score counts up (or down) to the real one
        self.shown = self.score if abs(gap) < 0.5 else self.shown + gap * min(1.0, dt * 7) + (1 if gap > 0 else -1) * dt * 20
        # panning: the sight at the edge drags the view along
        edge = 0.07
        if self.cx < edge:
            self.pan(-(edge - self.cx) / edge * dt * 0.55)
        elif self.cx > 1 - edge:
            self.pan((self.cx - (1 - edge)) / edge * dt * 0.55)
        self.mill_a += self.mill_spin * dt
        self.mill_spin += (0.9 - self.mill_spin) * min(1.0, dt * 0.5)
        for c in self.clouds:
            c[0] = (c[0] + dt * 0.004) % 1.2
        # spawns
        self.next_spawn -= dt
        flying = sum(1 for t in self.targets if t.kind == "puff" and t.state == "fly")
        if flying < self.want() and self.next_spawn <= 0:
            self.spawn_puff()
            self.next_spawn = self.rnd.uniform(0.3, 1.0) * (1.2 - 0.6 * self.progress())
        self.next_peek -= dt
        if self.next_peek <= 0:
            self.spawn_peek()
            self.next_peek = self.rnd.uniform(2.5, 5.5)
        self.next_gold -= dt
        if self.next_gold <= 0:
            self.spawn_puff(d=self.rnd.choice((0, 1)), kind="gold")
            self.next_gold = self.rnd.uniform(18, 28)
        self.next_balloon -= dt
        if self.next_balloon <= 0 and not any(t.kind == "balloon" for t in self.targets):
            self.spawn_balloon()
            self.next_balloon = self.rnd.uniform(28, 40)
        if sum(1 for t in self.targets if t.kind == "sheep") < 2:
            self.add_sheep()
        # movement
        for t in self.targets:
            t.t += dt
            t.flash = max(0.0, t.flash - dt)
            if t.kind == "sheep":
                if t.state == "flee":
                    t.x += t.vx * dt
                    if t.x < -0.05 or t.x > 1.05:
                        t.state = "gone"
                    continue
                t.p -= dt
                if t.p <= 0:
                    t.p = self.rnd.uniform(1.5, 5)
                    t.vx = self.rnd.choice((0, 0, -0.006, 0.006))
                t.x = clamp(t.x + t.vx * dt, 0.03, 0.97)
            elif t.kind == "peek":
                t.life -= dt
                t.p = clamp(t.p + (dt * 4 if t.life > 0 else -dt * 4), 0, 1)
                if t.life < -0.3:
                    t.state = "gone"
                elif t.state == "fly":
                    t.state = "peek"
            elif t.state == "fly":
                t.x += t.vx * dt
                t.y = t.y0 + t.amp * math.sin(t.phase + t.t * t.freq)
                if t.x < -0.08 or t.x > 1.08:
                    t.state = "gone"
                if t.kind == "gold" and self.rnd.random() < dt * 14:
                    self.part(t.x, t.y, t.d, (255, 240, 170), "spark", 0.3)
            elif t.state == "fall":
                t.vy += dt * (1.6 if t.kind != "balloon" else 1.0)
                t.y += t.vy * dt
                t.x += t.vx * dt * 0.3
                if t.y > 1.15:
                    t.state = "gone"
        self.targets = [t for t in self.targets if t.state != "gone"]
        for p in self.parts:
            p[4] -= dt
            if p[8] == "feather":
                p[3] = min(p[3] + dt * 0.12, 0.05)
                p[2] *= 1 - dt * 1.8
                p[0] += (p[2] + math.sin(p[9] + p[4] * 4) * 0.004) * dt
            elif p[8] == "confetti":
                p[3] = min(p[3] + dt * 0.5, 0.12)
                p[2] *= 1 - dt * 1.2
                p[0] += (p[2] + math.sin(p[9] + p[4] * 6) * 0.003) * dt
            else:
                p[2] *= 1 - dt * 4
                p[3] *= 1 - dt * 4
                p[0] += p[2] * dt
            p[1] += p[3] * dt
        self.parts = [p for p in self.parts if p[4] > 0]
        self.pops = [p for p in self.pops if p[5] > self.t]

    def pan(self, ds):
        self.scroll = clamp(self.scroll + ds, 0.0, 1.0)

    def aim(self, cx, cy):
        self.cx, self.cy = clamp(cx, 0.0, 0.999), clamp(cy, 0.0, 0.999)


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    k = clamp(((px - ax) * dx + (py - ay) * dy) / L, 0, 1) if L else 0
    return math.hypot(px - ax - k * dx, py - ay - k * dy)


# =============================================================================================
# The bot: plays auto mode and the title scene
# =============================================================================================
class Bot:
    def __init__(self, rnd=None, skill=1.0):
        self.rnd = rnd or random.Random()
        self.skill = skill
        self.target = None
        self.wait = 0.0
        self.wob = (0.0, 0.0)

    def update(self, g, dt):
        if g.over:
            return
        if g.ammo == 0 and g.reloading <= 0:
            g.reload()
        self.wait -= dt
        t = self.target
        if t is None or t not in g.targets or t.state not in ("fly", "peek") or t.kind == "sheep":
            t = self.target = self.pick(g)
            self.wob = (self.rnd.uniform(-1, 1), self.rnd.uniform(-1, 1))
        if t is None:                         # nothing on screen: pan towards the busier side
            side = sum((1 if g.sx(o.x, o.d) > g.W / 2 else -1) for o in g.targets if o.kind == "puff")
            g.aim(g.cx + (0.5 - g.cx) * dt * 3, g.cy)
            g.pan(dt * 0.25 * (1 if side >= 0 else -1))
            return
        x, y = self.aim_point(g, t)
        tx, ty = x / g.W, y / g.H
        tx += self.wob[0] * 0.01 / self.skill
        ty += self.wob[1] * 0.01 / self.skill
        dx, dy = tx - g.cx, ty - g.cy
        dist = math.hypot(dx * g.W, dy * g.H)
        step = min(1.0, dt * 7 * self.skill)
        g.aim(g.cx + dx * step, g.cy + dy * step)
        if dist < max(1.0, t.r * g.H * 0.8) and self.wait <= 0 and g.reloading <= 0:
            g.fire()
            self.wait = self.rnd.uniform(0.12, 0.35) / self.skill
            self.wob = (self.rnd.uniform(-1, 1), self.rnd.uniform(-1, 1))
        # keep the view centred on the action without scrolling the sight off
        if tx < 0.15:
            g.pan(-dt * 0.3)
        elif tx > 0.85:
            g.pan(dt * 0.3)

    def aim_point(self, g, t):
        H = g.H
        if t.kind == "peek":
            return g.sx(t.x, 2), WALL_TOP * H - t.r * H * (2.1 * t.p - 0.9) - 0.5
        lead = 0.12
        return g.sx(t.x + t.vx * lead, t.d), (t.y0 + t.amp * math.sin(t.phase + (t.t + lead) * t.freq)) * H

    def pick(self, g):
        best, bv = None, 0
        for t in g.targets:
            if t.kind == "sheep" or t.state not in ("fly", "peek"):
                continue
            if t.kind == "peek" and t.p < 0.6:
                continue
            x = g.sx(t.x, t.d)
            if not 2 <= x <= g.W - 2:
                continue
            v = {"gold": 100, "balloon": 30, "peek": 15}.get(t.kind, VALUE[t.d])
            d = math.hypot(x - g.cx * g.W, t.y * g.H - g.cy * g.H) / g.W
            score = v / (0.15 + d) * (0.6 if t.d == 0 else 1)
            if score > bv:
                best, bv = t, score
        return best


# =============================================================================================
# Drawing
# =============================================================================================
_SKY = {}


def sky_rows(sky, H):
    key = (sky["name"], H)
    if key not in _SKY:
        _SKY[key] = [mix(sky["top"], sky["hor"], clamp(y / (H * 0.62), 0, 1) ** 1.3) for y in range(H)]
    return _SKY[key]


def ellipse(cv, x, y, rx, ry, c, clip=None):
    y0, y1 = int(y - ry), int(y + ry) + 1
    for yy in range(max(0, y0), min(cv.H if clip is None else clip, y1 + 1)):
        dy = (yy + 0.5 - y) / max(0.5, ry)
        if abs(dy) > 1:
            continue
        w = rx * math.sqrt(1 - dy * dy)
        a, b = int(round(x - w)), int(round(x + w))
        if b <= a and rx >= 0.5:
            b = a + 1
        a, b = max(0, a), min(cv.W, b)
        if b > a:
            cv.px[yy][a:b] = [c] * (b - a)


def draw_puff(cv, x, y, r, c, t, face, dazed=False, clip=None):
    """A puffwing: a round ball of feathers with a beak, flapping wings and a tuft."""
    if r < 1.3:                                        # far away: a blob with a wing flick
        cv.rect(int(x) - 1, int(y), 2, 1, c)
        cv.set(int(x) - (1 if int(t * 8) % 2 else 0), int(y) - 1, shade(c, 0.8))
        cv.set(int(x) + face, int(y), (250, 160, 60))
        return
    flap = math.sin(t * 16)
    wing = shade(c, 0.78)
    for s in (-1, 1):                                  # wings behind the body
        wx = x - s * r * 0.95
        wy = y - r * 0.1 - flap * r * 0.6 * (0 if dazed else 1)
        ellipse(cv, wx, wy, r * 0.55, r * 0.35, wing, clip)
    ellipse(cv, x, y, r * 1.15, r, c, clip)
    ellipse(cv, x + face * r * 0.15, y + r * 0.35, r * 0.7, r * 0.5, mix(c, (255, 255, 255), 0.45), clip)
    if r >= 2.5:
        cv.set(x - face * r * 0.2, y - r * 1.05, shade(c, 0.7))
        cv.set(x - face * r * 0.05, y - r * 1.25, shade(c, 0.7))
    ex, ey = x + face * r * 0.45, y - r * 0.3
    beak = (250, 160, 60)
    if clip is None or ey < clip:
        if dazed:
            cv.set(ex, ey, (40, 30, 40))
            cv.set(ex + 1, ey - 1, (40, 30, 40))
            cv.set(ex - 1, ey + 1, (40, 30, 40))
        elif r >= 3:
            cv.rect(int(ex), int(ey) - 1, 2, 2, (255, 255, 255))
            cv.set(ex + (1 if face > 0 else 0), ey, (20, 20, 30))
        else:
            cv.set(ex, ey, (20, 20, 30))
    bx = x + face * r * 1.1
    cv.set(bx, y, beak)
    if r >= 3:
        cv.set(bx + face, y, beak)
        cv.set(bx, y + 1, shade(beak, 0.8))


def draw_sheep(cv, x, gy, r, t, flee):
    H = r
    bob = abs(math.sin(t * 14)) * r * 0.25 if flee else 0
    y = gy - r * 0.9 - bob
    for s in (-0.7, 0.5):                              # legs
        cv.rect(int(x + s * r), int(y + r * 0.6), 1, max(1, int(r * 0.5 + 1)), (50, 46, 50))
    wool = (240, 238, 232)
    ellipse(cv, x, y, H * 1.4, H, wool)
    for k in range(5):
        cv.set(x - H + k * H * 0.5, y - H * 0.9, (255, 255, 255))
    face = 1 if flee <= 0 else -1
    hx = x + face * H * 1.4
    ellipse(cv, hx, y - H * 0.3, H * 0.5, H * 0.45, (60, 54, 58))
    cv.set(hx + face * H * 0.15, y - H * 0.4, (240, 240, 240))


def draw_balloon(cv, x, y, r, c, flash, falling):
    if not falling:
        for yy in range(int(y - r), int(y + r) + 1):
            dy = (yy + 0.5 - y) / r
            if abs(dy) > 1:
                continue
            w = r * math.sqrt(1 - dy * dy) * (1 - 0.25 * max(0, dy))
            a, b = int(round(x - w)), int(round(x + w))
            for xx in range(a, b):
                stripe = int((xx - x) / max(1.0, r * 0.45) + 10) % 2
                col = (255, 255, 255) if flash > 0 else (c if stripe else mix(c, (255, 250, 230), 0.6))
                cv.set(xx, yy, shade(col, 1.08 - 0.25 * (xx - a) / max(1, b - a)))
        cv.line(x - r * 0.6, y + r * 0.7, x - r * 0.25, y + r * 1.4, (90, 70, 50))
        cv.line(x + r * 0.6, y + r * 0.7, x + r * 0.25, y + r * 1.4, (90, 70, 50))
    bw = max(2, int(r * 0.6))
    cv.rect(int(x - bw / 2), int(y + r * 1.4), bw, max(2, int(r * 0.45)), (150, 100, 60))
    draw_puff(cv, x, y + r * 1.25, max(1.4, r * 0.28), (250, 150, 182), 0, 1, dazed=falling)


def draw_mill(cv, g):
    mx, my, L = g.mill_geom()
    H = g.H
    gy = g.mid_ground(0.47) * H
    tw = H * 0.05
    cv.poly([(mx - tw * 0.6, my), (mx + tw * 0.6, my), (mx + tw, gy + 1), (mx - tw, gy + 1)], (232, 222, 204))
    cv.poly([(mx - tw * 0.75, my + 1), (mx, my - tw * 0.8), (mx + tw * 0.75, my + 1)], (150, 70, 60))
    cv.rect(int(mx - 1), int(gy - tw * 0.9), 2, int(tw * 0.9) + 1, (110, 80, 60))
    for k in range(4):
        a = g.mill_a + k * math.pi / 2
        ex, ey = mx + math.cos(a) * L, my + math.sin(a) * L
        cv.line(mx, my, ex, ey, (96, 70, 52))
        nx, ny = -math.sin(a), math.cos(a)
        for j in (1, 2):
            o = j * max(0.7, L * 0.07)
            cv.line(mx + math.cos(a) * L * 0.25 + nx * o, my + math.sin(a) * L * 0.25 + ny * o, ex + nx * o, ey + ny * o,
                    (244, 238, 226) if j == 1 else (214, 206, 192))
    cv.set(mx, my, (60, 44, 34))


def render_scene(g, cols, rows, play_rows):
    """The heath with everything on it (no HUD). play_rows: the text rows the scene fills."""
    cv = Canvas(cols, rows)
    W, H = cols, play_rows * 2
    g.resize(W, H)
    sky = g.sky
    px = cv.px
    shake = int(round(math.sin(g.t * 90) * 1.2)) if g.kick > 0.05 else 0
    for y, c in enumerate(sky_rows(sky, H)):
        px[y] = [c] * W
    # sun and clouds
    sxp = W * 0.72 - g.scroll_px() * 0.08
    ellipse(cv, sxp, H * 0.16, H * 0.07, H * 0.07, sky["sun"])
    for cxf, cyf, cr in g.clouds:
        x = (cxf - 0.1) * g.lw(0) * 1.2 - g.scroll_px() * 0.15
        r = cr * H
        for k, (ox, oy, s) in enumerate(((0, 0, 1.0), (-0.9, 0.3, 0.7), (0.9, 0.25, 0.75), (0.3, -0.35, 0.65))):
            ellipse(cv, x + ox * r, cyf * H + oy * r, r * s * 1.3, r * s * 0.6, mix(sky["cloud"], sky["hor"], 0.15 * k))
    far, heath, grass = sky["far"], sky["heath"], sky["grass"]
    sp = g.scroll_px()
    lw0, lw1, lw2 = g.lw(0), g.lw(1), g.lw(2)
    wt, wb = int(WALL_TOP * H), int(WALL_BOT * H)
    course = max(2, int(H * 0.034))
    stone = max(4, int(H * 0.09))
    hor = sky["hor"]
    for x in range(W):
        u0 = (x + sp * LF[0]) / lw0
        u1 = (x + sp * LF[1]) / lw1
        xw1 = int(x + sp * LF[1])
        xw2 = int(x + sp * LF[2])
        fy = int(H * (0.47 + wave(u0, FAR_W)))
        my = int(H * g.mid_ground(u1))
        for y in range(max(0, fy), min(my, wt)):
            k = (y - fy) / max(1, H * 0.25)
            px[y][x] = mix(mix(far, hor, 0.35), far, clamp(k, 0, 1)) if y > fy else mix(far, (255, 255, 255), 0.25)
        for y in range(max(0, my), wt):
            k = clamp((y - my) / max(1, H * 0.16), 0, 1)
            c = mix(mix(heath, (200, 150, 200), 0.2), shade(heath, 0.7), k) if y > my else mix(heath, (210, 170, 200), 0.4)
            h = hsh(xw1, y)
            if h % 11 == 0:
                c = mix(c, (236, 150, 220), 0.55)
            elif h % 13 == 0:
                c = mix(c, (90, 130, 70), 0.5)
            px[y][x] = c
        for y in range(wt, min(wb, H)):
            row = (y - wt) // course
            off = (row * stone // 2 + xw2) % stone
            c = WALL if row % 2 == 0 else mix(WALL, (170, 160, 146), 0.5)
            c = shade(c, 0.9 + 0.12 * ((hsh(xw2 // stone + row * 7, row) % 5) / 4))
            if (y - wt) % course == 0 or off == 0:
                c = WALL_D
            if y == wt:
                c = mix(WALL, (220, 214, 200), 0.6)
            px[y][x] = c
        for y in range(wb, H):
            k = (y - wb) / max(1, H - wb)
            c = mix(grass, shade(grass, 0.65), k)
            if hsh(xw2, y) % 5 == 0:
                c = shade(c, 1.15)
            px[y][x] = c
        if wb < H and hsh(xw2, 3) % 3 == 0:
            px[wb][x] = mix(grass, (200, 230, 140), 0.5)
    # far puffwings, the windmill, sheep, the balloon, middle puffwings
    for t in g.targets:
        if t.d == 0:
            draw_target(cv, g, t)
    draw_mill(cv, g)
    for t in g.targets:
        if t.d == 1:
            draw_target(cv, g, t)
    # the near layer: peekers behind the wall top, the tree and its holes, near puffwings
    for t in g.targets:
        if t.kind == "peek":
            draw_target(cv, g, t)
    tx, ty, tr, trunk = g.tree_geom()
    if -tr < tx < W + tr:
        cv.rect(int(tx - trunk), int(ty), int(trunk * 2) + 1, wt - int(ty) + 2, (96, 66, 44))
        cv.rect(int(tx - trunk), int(ty), 1, wt - int(ty) + 2, (70, 48, 34))
        leaf = (62, 118, 62) if sky["name"] != "evening" else (54, 92, 60)
        for k, (ox, oy, s) in enumerate(((0, 0, 1.0), (-0.55, 0.25, 0.7), (0.6, 0.2, 0.72), (0.1, -0.45, 0.7))):
            ellipse(cv, tx + ox * tr, ty + oy * tr, tr * s, tr * s * 0.85, shade(leaf, 0.85 + 0.1 * k))
        for y in range(int(ty - tr), int(ty + tr)):
            for x in range(int(tx - tr), int(tx + tr)):
                if 0 <= x < W and 0 <= y < H and hsh(int(x + sp), y) % 9 == 0 and px[y][x][1] < 140:
                    px[y][x] = shade(px[y][x], 1.3)
    for hx, hy in g.holes:
        x = g.sx(hx, 2)
        cv.set(x, hy * H, (34, 28, 26))
    for t in g.targets:
        if t.d == 2 and t.kind != "peek":
            draw_target(cv, g, t)
    for p in g.parts:
        x, y = g.sx(p[0], p[7]), p[1] * H
        fade = clamp(p[4] / p[5] * 2, 0, 1)
        c = p[6]
        if p[8] == "feather":
            cv.set(x, y, mix(px[int(clamp(y, 0, H - 1))][int(clamp(x, 0, W - 1))], c, fade))
            if p[7] == 2 and int(p[9] + p[4] * 5) % 2:
                cv.set(x + 1, y, mix(px[int(clamp(y, 0, H - 1))][int(clamp(x + 1, 0, W - 1))], shade(c, 0.85), fade))
        else:
            cv.set(x, y, c if fade > 0.5 else mix(px[int(clamp(y, 0, H - 1))][int(clamp(x, 0, W - 1))], c, fade * 2))
    if shake:
        for y in range(H):
            row = px[y]
            px[y] = row[shake:] + row[:shake] if shake > 0 else row[shake:] + row[:shake]
    for x, y, d, txt, c, until in g.pops:
        rise = (until - g.t)
        col = int(g.sx(x, d)) - len(txt) // 2
        row = int((y * H - (0.9 - rise) * 6) // 2)
        if 0 <= row < play_rows:
            cv.put(max(0, min(cols - len(txt), col)), row, txt, c, None)
    return cv


def draw_target(cv, g, t):
    H = g.H
    x = g.sx(t.x, t.d)
    r = t.r * H
    if x < -r * 3 or x > g.W + r * 3:
        return
    if t.kind == "sheep":
        draw_sheep(cv, x, g.mid_ground(t.x) * H, r, t.t, t.vx if t.state == "flee" else 0)
    elif t.kind == "balloon":
        draw_balloon(cv, x, t.y * H, r, t.color, t.flash, t.state == "fall")
    elif t.kind == "peek":
        y = WALL_TOP * H + r * 2.1 * (1 - t.p) - r * 0.9
        draw_puff(cv, x, y, r, t.color, t.t * 0.3, 1 if int(t.t * 1.5) % 2 else -1, clip=int(WALL_TOP * H))
    else:
        c = t.color
        if t.kind == "gold":
            c = mix(GOLD_C, (255, 255, 230), 0.5 + 0.5 * math.sin(t.t * 12))
        draw_puff(cv, x, t.y * H, r, c, t.t + t.phase, t.face, dazed=t.state == "fall")


def draw_sight(cv, g):
    x, y = int(g.cx * g.W), int(g.cy * g.H)
    c = (255, 255, 255) if g.reloading <= 0 else (150, 150, 160)
    red = (240, 60, 60)
    gap, arm = 2, 3
    if g.flash > 0:
        ellipse(cv, x + 0.5, y + 0.5, 3, 2.5, (255, 240, 180))
    for k in range(gap, gap + arm):
        for dx, dy in ((k, 0), (-k, 0), (0, k), (0, -k)):
            cv.set(x + dx, y + dy, c)
    cv.set(x, y, red)


DIGITS = {"0": "111101101101111", "1": "010110010010111", "2": "111001111100111", "3": "111001111001111",
          "4": "101101111001001", "5": "111100111001111", "6": "111100111101111", "7": "111001010010010",
          "8": "111101111101111", "9": "111101111001111"}


def draw_score(cv, g):
    """The score in big digits, top right, counting up to the real value; it glows while it climbs."""
    txt = str(int(round(g.shown)))
    k = 2 if g.H >= 96 else 1
    w = len(txt) * 4 * k - k
    x0, y0 = g.W - w - 3, 2
    cv.rect(x0 - 2, y0 - 1, w + 4, 5 * k + 3, (22, 18, 34))           # a small dark board behind it
    cv.frame(x0 - 2, y0 - 1, w + 4, 5 * k + 3, (90, 70, 110))
    rising = g.score - g.shown > 0.5
    col = mix((255, 214, 110), (255, 255, 255), 0.6) if rising else (255, 214, 110)
    for off, c in (((0, 0), col),):
        for i, ch in enumerate(txt):
            bits = DIGITS[ch]
            for j, b in enumerate(bits):
                if b == "1":
                    cv.rect(x0 + (i * 4 + j % 3) * k + off[0], y0 + (j // 3) * k + off[1], k, k, c)


def render(g, cols, rows, hud=True):
    play = rows - 1 if hud else rows
    cv = render_scene(g, cols, rows, play)
    draw_sight(cv, g)
    if hud:
        draw_score(cv, g)
        draw_hud(cv, g)
    if g.paused:
        overlay(cv, HELP if g.help else PAUSE_LINES + ["", SND.label()])
    return cv


def fmt(t):
    return "%d:%02d" % (int(t) // 60, int(t) % 60)


def draw_hud(cv, g):
    r = cv.rows - 1
    cv.put(0, r, " " * cv.cols, HUD_FG, HUD_BG)
    left = " SCORE %d %s" % (g.score, "  zen " if g.zen else "")
    cv.put(0, r, left, (16, 14, 20), (236, 200, 120) if not g.zen else (160, 210, 170))
    x = len(left) + 2
    if g.chain >= 2 and g.t - g.chain_t <= COMBO_GAP:
        s = "combo %d  x%d " % (g.chain, g.mult())
        cv.put(x, r, s, (255, 220, 120), HUD_BG)
    if not g.zen:
        s = " %s " % fmt(math.ceil(g.left))
        c = (255, 110, 100) if g.left <= 10 and int(g.t * 4) % 2 else HUD_FG
        cv.put((cv.cols - len(s)) // 2, r, s, c, HUD_BG)
    if g.reloading > 0:
        s = "reloading" + "." * (1 + int(g.t * 8) % 3)
        cv.put(cv.cols - 21, r, s.ljust(10), (200, 200, 210), HUD_BG)
    elif g.ammo == 0:
        cv.put(cv.cols - 23, r, "right click / R", (255, 140, 120), HUD_BG)
    shells = "".join("▮" if i < g.ammo else "▯" for i in range(MAG))
    for i, ch in enumerate(shells):
        cv.put(cv.cols - MAG - 1 + i, r, ch, (240, 190, 70) if ch == "▮" else (90, 88, 104), HUD_BG)


def render_over(g, cv, record, auto=False):
    acc = 100 * g.hits / g.shots if g.shots else 0
    lines = ["TIME!", "", "score       %d" % g.score, "hits        %d of %d shots (%d%%)" % (g.hits, g.shots, acc),
             "best combo  %d" % g.best_chain]
    if g.golds:
        lines.append("golden      %d" % g.golds)
    if g.sheep_hit:
        lines.append("sheep       %d (they forgive you)" % g.sheep_hit)
    if record:
        lines += ["", "** NEW RECORD **"]
    lines += ["", "auto mode: a new round starts" if auto else "Enter: again   Esc / Q: menu"]
    w = max(len(l) for l in lines) + 4
    x, y = max(0, (cv.cols - w) // 2), max(0, cv.rows // 2 - len(lines) // 2 - 1)
    cv.frame(x - 1, y * 2 - 1, w + 2, (len(lines) + 2) * 2 + 2, (236, 200, 120) if record else (196, 96, 170))
    cv.box(x, y, [l.ljust(w - 4) if i else l.center(w - 4) for i, l in enumerate(lines)], (240, 240, 246), (24, 22, 44))


# =============================================================================================
# Title, auto mode, play
# =============================================================================================
class TitleDemo:
    """The bot shooting on the heath, behind the title screen and in the launcher preview."""

    def __init__(self):
        self.k = 0
        self.new()

    def new(self):
        self.g = Game("Zen", seed=40 + self.k, demo=True)
        self.g.sky = SKIES[self.k % len(SKIES)]
        self.bot = Bot(random.Random(self.k), skill=0.8)
        self.k += 1

    def scene(self, cols, rows, dt):
        g = self.g
        dt = min(dt, 0.1)
        self.bot.update(g, dt)
        g.update(dt)
        if g.t > 40:
            self.new()
        return render(g, cols, rows, hud=False)


def render_menu(demo, cols, rows, sel, dt, help_=False, mode=0):
    cv = demo.scene(cols, rows, dt)
    rec = load_scores().get(GAME, {}).get("90 Seconds")
    best = None if rec is None else "best 90 Seconds: %d" % rec
    items = ["%-11s %s" % m for m in MODES] + ["%-11s watch it play %s" % (AUTO_LABEL, MODES[mode][0])]
    title_screen(cv, "HEATHSHOT", "a shooting gallery on the heath", items, sel, best,
                 extra=["", "mouse: aim and click    keys: arrows + Space"],
                 keys="Up/Down choose   Enter start   M %s   ? help   Esc back" % SND.label().lower(),
                 help_lines=HELP, show_help=help_)
    return cv


def too_small(term):
    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (60x22).")


def apply_mouse(term, g, cols, rows):
    """Mouse reports -> the sight, shots, reloads, panning. Returns True when something was fired."""
    take = getattr(term, "take_mouse", None)
    if not take:
        return False
    play = rows - 1
    for kind, col, row in take():
        if row >= play and kind == "move":
            continue
        g.aim((col + 0.5) / cols, min(play * 2 - 1, row * 2 + 1) / (play * 2))
        if kind == "left":
            g.fire()
        elif kind in ("right", "middle"):
            g.reload()
        elif kind == "wheelup":
            g.pan(-0.05)
        elif kind == "wheeldown":
            g.pan(0.05)
    return True


def game_key(g, k):
    step = 0.03
    if k in ("left", "a"):
        g.aim(g.cx - step, g.cy)
    elif k in ("right", "d"):
        g.aim(g.cx + step, g.cy)
    elif k in ("up", "w"):
        g.aim(g.cx, g.cy - step * 1.6)
    elif k in ("down", "s"):
        g.aim(g.cx, g.cy + step * 1.6)
    elif k in (" ", "enter", "f"):
        g.fire()
    elif k == "r":
        g.reload()
    elif k == "q":
        g.pan(-0.08)
    elif k == "e":
        g.pan(0.08)


def run_auto(term, mode):
    auto = AutoMode()
    while True:
        g = Game(MODES[mode][0], demo=False)
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
                bot.update(g, sim / n)
                g.update(sim / n)
            if g.zen and g.t > 120:
                break
            if g.over and over_at is None:
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
            cv = render(g, cols, rows)
            if g.over:
                render_over(g, cv, None, auto=True)
            auto.banner(cv, extra=MODES[mode][0])
            term.write(cv.emit())
            time.sleep(max(0, 1 / 50 - (time.time() - now)))


def play(term, mode):
    while True:
        g = Game(MODES[mode][0])
        last = time.time()
        record = None
        again = False
        while True:
            now = time.time()
            cols, rows = term.size()
            g.update(min(0.1, now - last))
            last = now
            if not g.paused and not g.over:
                apply_mouse(term, g, cols, rows)
            elif getattr(term, "take_mouse", None):
                for kind, _, _ in term.take_mouse():
                    if g.over and record is not None and kind == "left":
                        again = True
            for k in term.keys(0):
                if g.over:
                    if k in ("q", "esc"):
                        return
                    if record is not None and k in ("enter", " "):
                        again = True
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
            if again:
                break
            if g.over and record is None:
                record = submit(GAME, g.mode, g.score) if g.score > 0 else False
                g.over_t = now
            if g.over and now - getattr(g, "over_t", now) < 0.6:
                record = record                  # a short beat before Enter counts (no accidental restart)
            if cols < 60 or rows < 22:
                too_small(term)
                time.sleep(0.2)
                continue
            cv = render(g, cols, rows)
            if g.over:
                render_over(g, cv, record)
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
# Self-test:  python3 heathshot.py --selftest
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
        g = Game("90 Seconds", seed=11)
        g.sky = SKIES[2]
        bot = Bot(random.Random(3))
        for _ in range(int(31 / (1 / 60))):
            bot.update(g, 1 / 60)
            g.update(1 / 60)
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
    # a shot at a near puffwing hits it, scores, and costs a shell
    g = Game("90 Seconds", seed=1, W=100, H=60)
    g.targets = [t for t in g.targets if t.kind == "sheep"]
    t = g.spawn_puff(d=2)
    t.x, t.y0, t.y, t.amp = g.ux(50, 2), 0.3, 0.3, 0
    g.aim(0.505, 0.3)
    assert g.fire() is t and g.score == VALUE[2] and g.ammo == MAG - 1 and t.state == "fall"
    # the far ones are worth more; combos multiply
    g.chain = 3
    g.chain_t = g.t
    f = g.spawn_puff(d=0)
    f.x, f.y0, f.y, f.amp = g.ux(30, 0), 0.2, 0.2, 0
    g.aim(30.5 / 100, 0.2)
    assert g.fire() is f and g.chain == 4 and g.score == VALUE[2] + VALUE[0] * 2, g.score
    # sheep cost points; the empty gun reloads on the next click
    s = next(t for t in g.targets if t.kind == "sheep")
    s.x = g.ux(70, 1)
    gy = g.mid_ground(s.x) * 60 - s.r * 60 * 0.9
    g.aim(70.5 / 100, gy / 60)
    before = g.score
    assert g.fire() is s and g.score == before + SHEEP and s.state == "flee"
    g.ammo = 0
    g.fire()
    assert g.reloading > 0
    g.update(RELOAD + 0.01)
    assert g.ammo == MAG
    # the wall takes holes, the balloon takes three hits
    g.aim(0.5, 0.85)
    assert g.fire() == "wall" and g.holes
    g.update(1.0)
    b = g.spawn_balloon() or g.targets[-1]
    b.x, b.y0, b.y, b.amp = g.ux(40, 1), 0.2, 0.2, 0
    for k in range(3):
        g.reloading = 0
        g.aim(40.5 / 100, 0.2)
        assert g.fire() is b
    assert b.state == "fall"
    # panning at the edge, the clock
    g.aim(0.0, 0.5)
    s0 = g.scroll
    g.update(0.5)
    assert g.scroll < s0 or g.scroll == 0
    g.left = 0.05
    g.update(0.1)
    assert g.over
    # the bot plays a whole round and hits things
    g = Game("90 Seconds", seed=5, demo=True)
    bot = Bot(random.Random(5))
    while not g.over:
        bot.update(g, 1 / 30)
        g.update(1 / 30)
        if int(g.t * 30) % 300 == 0:
            render(g, 100, 32).emit()
    assert g.hits >= 30 and g.score > 300, "the bot hit %d (%d points)" % (g.hits, g.score)
    cv = render(g, 100, 32)
    render_over(g, cv, True)
    cv.emit()
    # mouse reports reach the game
    g = Game("Zen", seed=2)
    term = FakeTerm([], [(0, ("move", 30, 10)), (0, ("left", 30, 10)), (0, ("right", 30, 10))])
    apply_mouse(term, g, 100, 32)
    assert abs(g.cx - 0.305) < 1e-6 and g.shots == 1 and g.reloading > 0
    # the arcadekit mouse parser
    mt = arcadekit.MouseTerminal()
    mt.mouse = []
    keys = mt.parse("\x1b[<35;12;5M\x1b[<0;12;5Mx\x1b[<0;12;5m\x1b[<2;3;4M\x1b[<64;1;1M\x1b[A")
    assert keys == ["x", "up"], keys
    assert mt.take_mouse() == [("move", 11, 4), ("left", 11, 4), ("up", 11, 4), ("right", 2, 3), ("wheelup", 0, 0)]
    # the big score counts up to the real one; Zen counts too
    g = Game("Zen", seed=3, W=100, H=60)
    g.score = 120
    for _ in range(120):
        g.update(1 / 60)
    assert g.shown == 120
    t = g.spawn_puff(d=2)
    t.x, t.y0, t.y, t.amp = g.ux(50, 2), 0.3, 0.3, 0
    g.aim(0.505, 0.3)
    assert g.fire() is t and g.score == 120 + VALUE[2]
    draw_score(render(g, 100, 32), g)
    # every size, the title, auto mode
    for cols, rows in ((60, 22), (100, 32), (180, 50)):
        d = TitleDemo()
        for i in range(30):
            d.scene(cols, rows, 0.1)
        for sel in range(3):
            render_menu(d, cols, rows, sel, 0.05, sel == 2, 0).emit()
    TitleDemo().scene(20, 8, 0.1)
    term = FakeTerm([(0.1, "+"), (0.2, "+"), (0.5, " "), (0.6, "?"), (0.7, "x"), (0.8, " "), (1.2, "esc")])
    run_auto(term, 0)
    assert term.frames > 5 and not term.script
    assert not os.path.exists(tmp), "auto mode wrote a score"
    print("Self-test ok: hits and values, combo, sheep, reload, wall, balloon, panning, clock, a bot round, "
          "mouse, title at three sizes, auto mode (%.1fs)" % (time.time() - t0))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
