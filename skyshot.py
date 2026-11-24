#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""SKYSHOT - two cannons, one hill between them, and the wind never stops changing.

A turn-based artillery duel on destructible ground. Set the angle and the power, read the wind, fire.
Shells carve craters, the ground gives way, tanks slide into the holes. Four shells to choose from:
the plain shell, the heavy shell, the splitter that bursts in three at the top of its flight, and the
dirt ball that buries the other side under fresh earth. Best of three rounds, new land every round.

Two players at one keyboard (turns alternate), or one player against the computer (easy, normal, hard).

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
Run:        python3 skyshot.py
Self-test:  python3 skyshot.py --selftest
Benchmark:  python3 skyshot.py --bench
"""
import math
import random
import sys
import time
from collections import deque

from arcadekit import (AUTO_LABEL, AutoMode, Canvas, Terminal, clamp, load_scores, mix, overlay, shade, shared_key,
                       submit, title_screen)
from arcadesound import Sound

GAME = "skyshot"
G = 50.0                 # gravity, pixels / s^2
PH = 1 / 60              # fixed physics step
WIND_ACC = 1.1           # pixels / s^2 per wind point
DIFFS = ["easy", "normal", "hard"]
P_COLS = [(95, 180, 255), (255, 128, 80)]
HUD_BG = (12, 12, 20)
WEAPONS = [  # name, blast radius (px), damage, ammo per round (None = unlimited), kind
    ("Shell", 4.5, 34, None, "shell"),
    ("Heavy shell", 7.0, 50, 3, "shell"),
    ("Splitter", 4.0, 24, 2, "split"),
    ("Dirt ball", 6.5, 0, 2, "dirt"),
]
SND = Sound(GAME, {
    # aiming: tiny ticks while the barrel turns or the power changes
    "aim": [dict(w="tri", f=880, d=0.015, v=0.1)],
    "power": [dict(w="square", f=330, d=0.015, v=0.08, duty=0.25)],
    "weapon": [dict(w="tri", f=523, d=0.025, v=0.2), dict(w="tri", f=784, d=0.03, v=0.18)],
    "empty": [dict(w="square", f=147, d=0.08, v=0.2, duty=0.4)],
    # the cannon: a low thump with a puff of noise
    "fire": [dict(w="noise", f=1400, f2=200, d=0.18, v=0.42), dict(w="sine", f=150, f2=50, d=0.22, v=0.55, at=0)],
    "fire_heavy": [dict(w="noise", f=1000, f2=120, d=0.28, v=0.5), dict(w="sine", f=120, f2=38, d=0.32, v=0.62, at=0),
                   dict(w="square", f=80, f2=45, d=0.18, v=0.18, duty=0.3, at=0)],
    # a shell past the top of its arc: the classic falling whistle
    "whistle": [dict(w="sine", f=1900, f2=700, d=0.85, v=0.16, vib=(9, 0.15), r="lin")],
    "split": [dict(w="square", f=1200, f2=600, d=0.05, v=0.22, duty=0.25), dict(w="noise", f=4000, d=0.06, v=0.14, at=0)],
    # impacts, sized by the shell
    "boom_small": [dict(w="noise", f=2200, f2=150, d=0.35, v=0.5), dict(w="sine", f=110, f2=45, d=0.25, v=0.4, at=0)],
    "boom": [dict(w="noise", f=1800, f2=80, d=0.6, v=0.65), dict(w="sine", f=95, f2=35, d=0.4, v=0.5, at=0)],
    "boom_big": [dict(w="noise", f=1500, f2=50, d=0.95, v=0.8), dict(w="sine", f=80, f2=28, d=0.6, v=0.6, at=0),
                 dict(w="noise", f=200, f2=60, d=0.6, v=0.3, at=0.25, r="lin")],
    "splash": [dict(w="noise", f=5000, f2=900, d=0.4, v=0.36), dict(w="sine", f=500, f2=180, d=0.15, v=0.25, at=0)],
    "dirt": [dict(w="noise", f=400, f2=90, d=0.35, v=0.45, r="lin"), dict(w="tri", f=110, f2=70, d=0.2, v=0.35, at=0),
             dict(w="noise", f=900, f2=300, d=0.2, v=0.16, at=0.2)],
    "miss": [dict(w="sine", f=700, f2=350, d=0.25, v=0.16, r="lin")],
    # tanks
    "hit": [dict(w="square", f=740, f2=520, d=0.09, v=0.28, duty=0.3), dict(w="tri", f=1110, f2=880, d=0.18, v=0.22, at=0)],
    "destroyed": [dict(w="noise", f=2000, f2=40, d=1.15, v=0.85), dict(w="sine", f=70, f2=25, d=0.8, v=0.6, at=0),
                  dict(w="square", f=330, f2=60, d=0.5, v=0.16, duty=0.3, at=0.1)],
    "fall": [dict(w="tri", f=180, f2=70, d=0.18, v=0.45), dict(w="noise", f=600, f2=100, d=0.15, v=0.3, at=0.05)],
    "land": [dict(w="tri", f=120, f2=80, d=0.06, v=0.25)],
    # the match
    "turn": [dict(w="tri", f=587, d=0.06, v=0.24), dict(w="tri", f=880, d=0.1, v=0.22)],
    "wind": [dict(w="noise", f=260, f2=140, d=1.1, v=0.16, a=0.35, r="lin", vib=(3, 2.0))],
    "sudden": [dict(w="square", f=440, d=0.12, v=0.24, duty=0.25), dict(w="square", f=440, d=0.12, v=0.24, duty=0.25, at=0.2),
               dict(w="square", f=330, d=0.3, v=0.26, duty=0.25, at=0.4)],
    "round": [dict(w="square", f=392, d=0.08, v=0.28, duty=0.25), dict(w="square", f=523, d=0.08, v=0.28, duty=0.25),
              dict(w="square", f=659, d=0.08, v=0.28, duty=0.25), dict(w="tri", f=784, d=0.4, v=0.42, vib=(6, 0.2), r="lin")],
    "match_win": [dict(w="square", f=f, d=0.09, v=0.28, duty=0.25) for f in (523, 523, 523)] +
                 [dict(w="square", f=659, d=0.18, v=0.3, duty=0.25), dict(w="square", f=523, d=0.09, v=0.28, duty=0.25),
                  dict(w="tri", f=784, d=0.5, v=0.45, vib=(6, 0.25), r="lin"),
                  dict(w="tri", f=523, d=0.5, v=0.28, at=0.63, r="lin")],
    "match_lose": [dict(w="tri", f=392, d=0.2, v=0.38), dict(w="tri", f=370, d=0.2, v=0.38),
                   dict(w="tri", f=349, d=0.2, v=0.38), dict(w="tri", f=330, f2=262, d=0.55, v=0.4, vib=(5, 0.3), r="lin")],
    # menus
    "menu": [dict(w="tri", f=660, d=0.025, v=0.2)],
    "start": [dict(w="square", f=392, d=0.05, v=0.3, duty=0.25), dict(w="square", f=523, d=0.05, v=0.3, duty=0.25),
              dict(w="square", f=784, d=0.15, v=0.32, duty=0.25)],
    "pause": [dict(w="tri", f=523, f2=392, d=0.07, v=0.22)],
    "sound_on": [dict(w="tri", f=440, d=0.06, v=0.35), dict(w="tri", f=880, d=0.12, v=0.35)],
})
PALETTES = [
    dict(sky=((62, 120, 210), (182, 218, 246)), sun=(255, 250, 225), mount=((112, 142, 192), (148, 176, 214)),
         grass=(96, 186, 72), dirt=(152, 106, 62), deep=(92, 60, 38), rock=(112, 102, 98), water=(48, 118, 190),
         cloud=(250, 252, 255), stars=False),
    dict(sky=((56, 46, 118), (250, 152, 112)), sun=(255, 214, 150), mount=((92, 66, 118), (156, 98, 124)),
         grass=(122, 162, 62), dirt=(162, 102, 58), deep=(88, 54, 40), rock=(106, 86, 88), water=(84, 92, 162),
         cloud=(255, 204, 196), stars=False),
    dict(sky=((14, 18, 52), (84, 76, 146)), sun=(236, 236, 255), mount=((38, 42, 86), (58, 58, 108)),
         grass=(72, 146, 96), dirt=(124, 88, 62), deep=(70, 48, 42), rock=(86, 86, 104), water=(42, 72, 134),
         cloud=(150, 150, 196), stars=True),
    dict(sky=((88, 158, 226), (240, 218, 176)), sun=(255, 246, 214), mount=((190, 150, 124), (216, 182, 154)),
         grass=(206, 172, 92), dirt=(200, 146, 82), deep=(138, 90, 56), rock=(152, 112, 92), water=(56, 140, 172),
         cloud=(255, 250, 242), stars=False),
]
_nr = random.Random(7)
NOISE = bytes(_nr.randrange(4) for _ in range(4096))


# =============================================================================================
# The ground: one byte column per pixel column (0 air, 1 dirt, 2 rock, 3 new dirt, 4 scorched, 9 bedrock)
# =============================================================================================
class World:
    def __init__(self, W, H, seed):
        self.W, self.H = W, H
        self.rnd = rnd = random.Random(seed)
        self.pal = rnd.choice(PALETTES)
        self.vmax = math.sqrt(G * W * 1.35)
        self.wl = None
        self.cols = [bytearray(H) for _ in range(W)]
        self.top = [H] * W
        self.trows = [[None] * W for _ in range(H)]
        self.dirty = set()
        self.generate()
        self.build_tables()
        self.build_sky()
        for x in range(W):
            self.recolour(x)
        self.clouds = []
        for _ in range(max(3, W // 32)):
            self.clouds.append([rnd.uniform(0, W), rnd.uniform(3, H * 0.3), rnd.uniform(8, 18), rnd.uniform(2.5, 4.5),
                                rnd.uniform(0.45, 0.8)])

    def generate(self):
        W, H, rnd = self.W, self.H, self.rnd
        waves = [(f, a * H * rnd.uniform(0.7, 1.2), rnd.uniform(0, 6.283)) for f, a in
                 ((rnd.uniform(0.6, 1.4), 0.15), (rnd.uniform(1.6, 3.0), 0.08), (rnd.uniform(3.5, 6.0), 0.035),
                  (rnd.uniform(8, 13), 0.012))]
        base = H * rnd.uniform(0.56, 0.66)
        self.feature = feature = rnd.choice(["hill", "valley", "rolling", "hill", "valley"])
        h = []
        for x in range(W):
            u = x / W
            y = base + sum(a * math.sin(6.283 * f * u + p) for f, a, p in waves)
            if feature == "hill":
                y -= H * 0.24 * math.exp(-((u - 0.5) / 0.11) ** 2)
            elif feature == "valley":
                y += H * 0.17 * math.exp(-((u - 0.5) / 0.13) ** 2)
            h.append(clamp(y, H * 0.26, H - 6))
        xs = [int(W * rnd.uniform(0.08, 0.22)), int(W * rnd.uniform(0.78, 0.92))]
        for sx in xs:                                  # a small flat pad for each cannon
            pad = min(sum(h[sx - 4:sx + 5]) / 9, H * 0.8)
            for x in range(sx - 7, sx + 8):
                if 0 <= x < W:
                    t = clamp((abs(x - sx) - 4) / 3.5, 0, 1)
                    h[x] = pad * (1 - t) + h[x] * t
        self.spawns = xs
        if feature == "valley" or rnd.random() < 0.3:  # a lake in the low ground between them
            deep = max(h[x] for x in range(int(W * 0.3), int(W * 0.7)))
            low = max(max(h[x] for x in range(sx - 5, sx + 6)) for sx in xs)
            wl = int(deep - rnd.uniform(3, 7))
            if wl > low + 3 and deep - wl >= 2:
                self.wl = wl
        ph = rnd.uniform(0, 6.283)
        for x in range(W):
            col, t = self.cols[x], int(h[x])
            rd = int(t + H * 0.3 + 4 * math.sin(x * 0.11 + ph))
            for y in range(t, H):
                col[y] = 9 if y >= H - 2 else 2 if y >= rd else 1

    def build_tables(self):
        p, H = self.pal, self.H
        n = [0.9, 0.97, 1.03, 1.1]
        dirt = [[shade(mix(p["dirt"], p["deep"], min(1.0, d / 34)), k) for k in n] for d in range(48)]
        dirt[0] = [shade(mix(p["grass"], (255, 255, 230), 0.18), k) for k in n]
        dirt[1] = [shade(p["grass"], k) for k in n]
        dirt[2] = [shade(mix(p["grass"], p["dirt"], 0.6), k) for k in n]
        rock = [[shade(mix(mix(p["rock"], p["deep"], 0.3), p["deep"], 0.35 * (d % 7 == 0)), k * (1 - min(0.3, d / 120)))
                 for k in n]
                for d in range(48)]
        new = [[shade(mix((178, 128, 76), p["dirt"], min(1.0, d / 12)), k) for k in n] for d in range(48)]
        new[0] = [shade((196, 146, 92), k) for k in n]
        scorch = [[shade(mix((52, 40, 34), p["deep"], min(1.0, d / 3)), k) for k in n] for d in range(48)]
        bed = [[shade((44, 40, 46), k) for k in n] for _ in range(48)]
        self.tab = {1: dirt, 2: rock, 3: new, 4: scorch, 9: bed}
        w = p["water"]
        self.water = [mix(mix(w, (220, 240, 255), 0.35), shade(w, 0.45), min(1.0, d / 26)) for d in range(H + 1)]

    def build_sky(self):
        W, H, p, rnd = self.W, self.H, self.pal, self.rnd
        top, bot = p["sky"]
        sx, sy, sr = rnd.uniform(W * 0.25, W * 0.75), rnd.uniform(H * 0.1, H * 0.25), 3.2 + W / 90
        rows = []
        layers = []
        for k, (amp, base, freq) in enumerate(((H * 0.1, H * 0.42, 2.2), (H * 0.07, H * 0.52, 3.6))):
            ph1, ph2 = rnd.uniform(0, 6.283), rnd.uniform(0, 6.283)
            layers.append(([base - amp * (0.6 * math.sin(6.283 * freq * x / W + ph1) +
                                          0.4 * abs(math.sin(6.283 * freq * 2.3 * x / W + ph2))) for x in range(W)],
                           mix(p["mount"][k], mix(top, bot, 0.8), 0.35 - 0.2 * k)))
        for y in range(H):
            g = mix(top, bot, min(1.0, y / (H * 0.85)))
            row = [g] * W
            dy = y - sy
            if abs(dy) < sr * 3:
                for x in range(max(0, int(sx - sr * 3)), min(W, int(sx + sr * 3) + 1)):
                    d = math.hypot(x - sx, dy * 1.0)
                    if d < sr:
                        row[x] = p["sun"]
                    elif d < sr * 3:
                        row[x] = mix(p["sun"], g, 0.55 + 0.45 * (d - sr) / (sr * 2))
            if p["stars"] and y < H * 0.45:
                for x in range(W):
                    if NOISE[(x * 131 + y * 977) & 4095] == 0 and NOISE[(x * 17 + y * 3) & 4095] == 0 and \
                            (x * 7 + y * 11) % 5 == 0:
                        row[x] = mix(g, (255, 255, 255), 0.7)
            for ys, c in layers:
                for x in range(W):
                    if y >= ys[x]:
                        row[x] = mix(c, g, 0.1 * NOISE[(x * 29 + y * 61) & 4095] / 3)
            rows.append(row)
        self.sky = rows

    # -----------------------------------------------------------------------------------------
    def recolour(self, x):
        col, H = self.cols[x], self.H
        self.top[x] = H - len(col.lstrip(b"\0"))
        wl = self.wl if self.wl is not None else H + 1
        tr, tab, water = self.trows, self.tab, self.water
        run = -1
        for y in range(H):
            m = col[y]
            if not m:
                run = -1
                tr[y][x] = water[y - wl] if y >= wl else None
                continue
            run += 1
            tr[y][x] = tab[m][run if run < 48 else 47][NOISE[(x * 131 + y * 31) & 4095]]

    def first_solid(self, x, y0):
        if x < 0 or x >= self.W:
            return self.H
        if y0 < 0:
            y0 = 0
        col = self.cols[x]
        return self.H - len(col[y0:].lstrip(b"\0"))

    def carve(self, cx, cy, r):
        removed = 0
        r2, r3 = r * r, (r + 1.6) ** 2
        for x in range(int(cx - r - 2), int(cx + r + 3)):
            if not 0 <= x < self.W:
                continue
            col, dx = self.cols[x], x + 0.5 - cx
            for y in range(max(0, int(cy - r - 2)), min(self.H, int(cy + r + 3))):
                m = col[y]
                if m and m != 9:
                    d2 = dx * dx + (y + 0.5 - cy) ** 2
                    if d2 <= r2:
                        col[y] = 0
                        removed += 1
                    elif d2 <= r3:
                        col[y] = 4
            self.dirty.add(x)
            self.recolour(x)
        return removed

    def add_dirt(self, cx, cy, r):
        added = 0
        for x in range(int(cx - r - 1), int(cx + r + 2)):
            if not 0 <= x < self.W:
                continue
            col, dx = self.cols[x], x + 0.5 - cx
            for y in range(max(0, int(cy - r - 1)), min(self.H, int(cy + r + 2))):
                if not col[y] and dx * dx + (y + 0.5 - cy) ** 2 <= r * r:
                    col[y] = 3
                    added += 1
            self.dirty.add(x)
            self.recolour(x)
        return added

    def settle_step(self):
        """Loose earth falls one pixel per step; columns without gaps leave the dirty set."""
        done = []
        for x in self.dirty:
            col = self.cols[x]
            t = self.H - len(col.lstrip(b"\0"))
            if 0 not in col[t:]:
                done.append(x)
                continue
            for y in range(self.H - 2, t - 1, -1):
                if col[y] and not col[y + 1]:
                    col[y + 1] = col[y]
                    col[y] = 0
            self.recolour(x)
        for x in done:
            self.dirty.discard(x)

    def solid_count(self):
        return sum(len(c) - c.count(0) for c in self.cols)

    def probe(self, px, py, tanks, owner, safe):
        """What a shell at (px, py) touches: None, 'off', 'ground', 'water' or a tank."""
        if px < 0 or px >= self.W:
            return "off"
        if py < 0:
            return None
        yi = int(py)
        if yi >= self.H:
            return "ground"
        for t in tanks:
            if t.hp > 0 and abs(px - t.x - 0.5) < 3.6 and t.y - 4.3 <= py < t.y:
                if t.idx == owner and safe:
                    continue
                return t
        if self.cols[int(px)][yi]:
            return "ground"
        if self.wl is not None and yi >= self.wl:
            return "water"
        return None


# =============================================================================================
# Tanks and shells
# =============================================================================================
class Tank:
    def __init__(self, idx, x, y, colour):
        self.idx, self.x, self.y = idx, x, float(y)
        self.vy, self.fall0, self.hp = 0.0, None, 100
        self.angle, self.power = (52 if idx == 0 else 128), 60
        self.weapon = 0
        self.ammo = [w[3] for w in WEAPONS]
        self.colour = colour
        self.slides, self.slide_t = 0, 0.0
        self.shown = 100.0        # the HP bar drains towards hp, so a hit shows how much it took
        self.hit_t = 0.0          # a hit tank flashes white

    def centre(self):
        return self.x + 0.5, self.y - 2.0

    def muzzle(self):
        a = math.radians(self.angle)
        return self.x + 0.5 + math.cos(a) * 5.2, self.y - 3.5 - math.sin(a) * 5.2

    def in_box(self, px, py):
        return abs(px - self.x - 0.5) < 3.6 and self.y - 4.3 <= py < self.y

    def grounded(self, world):
        return world.first_solid(self.x, int(self.y)) <= int(self.y) or \
            min(world.first_solid(c, int(self.y)) for c in (self.x - 1, self.x, self.x + 1)) <= int(self.y)

    def physics(self, world):
        """One fixed step: fall when nothing holds the tracks, slide off steep edges. Returns a fall distance on landing."""
        yi = int(self.y)
        sup = min(world.first_solid(c, yi) for c in (self.x - 1, self.x, self.x + 1))
        if sup > yi:
            if self.fall0 is None:
                self.fall0 = self.y
            self.vy += G * PH
            self.y += self.vy * PH
            sup = min(world.first_solid(c, yi) for c in (self.x - 1, self.x, self.x + 1))
            if self.y >= sup:
                self.y = float(sup)
                self.vy = 0.0
                fall = self.y - self.fall0
                self.fall0 = None
                return fall
            return None
        self.vy = 0.0
        if self.fall0 is not None:
            fall = self.y - self.fall0
            self.fall0 = None
            return fall
        if self.slides < 30:                       # hanging on one column over a drop: slide down
            gl = world.first_solid(self.x - 1, yi) - yi
            gr = world.first_solid(self.x + 1, yi) - yi
            if (gl >= 3 or gr >= 3) and abs(gl - gr) >= 3:
                self.slide_t += PH
                if self.slide_t > 0.07:
                    self.slide_t = 0.0
                    nx = self.x + (1 if gr > gl else -1)
                    if 4 <= nx <= world.W - 5:
                        self.x = nx
                        self.slides += 1
        return None


class Shell:
    __slots__ = ("x", "y", "vx", "vy", "w", "owner", "safe", "age", "trail", "split")

    def __init__(self, x, y, vx, vy, w, owner):
        self.x, self.y, self.vx, self.vy, self.w, self.owner = x, y, vx, vy, w, owner
        self.safe, self.age, self.split = True, 0.0, False
        self.trail = deque(maxlen=18)


def fly(world, tanks, s, wind, dt=PH, exact=True):
    """Advance a shell one step. Returns None while it flies, else what it hit ('off', 'ground', 'water', a Tank)."""
    s.vx += wind * WIND_ACC * dt
    s.vy += G * dt
    x0, y0 = s.x, s.y
    nx, ny = x0 + s.vx * dt, y0 + s.vy * dt
    n = int(max(abs(nx - x0), abs(ny - y0))) + 1 if exact else 1
    own = tanks[s.owner]
    for i in range(1, n + 1):
        px, py = x0 + (nx - x0) * i / n, y0 + (ny - y0) * i / n
        hit = world.probe(px, py, tanks, s.owner, s.safe)
        if s.safe and not own.in_box(px, py):
            s.safe = False
        if hit is not None:
            s.x, s.y = px, py
            return hit
    s.x, s.y = nx, ny
    s.age += dt
    return None


def launch(world, tank, angle=None, power=None, w=0):
    a = math.radians(tank.angle if angle is None else angle)
    v = (tank.power if power is None else power) / 100 * world.vmax
    mx, my = tank.x + 0.5 + math.cos(a) * 5.2, tank.y - 3.5 - math.sin(a) * 5.2
    return Shell(mx, my, v * math.cos(a), -v * math.sin(a), w, tank.idx)


def simulate(world, tanks, tank, angle, power, wind, exact=True):
    s = launch(world, tank, angle, power)
    dt = PH if exact else PH * 2
    for _ in range(int(12 / dt)):
        hit = fly(world, tanks, s, wind, dt, exact)
        if hit is not None:
            return s.x, s.y, hit
    return s.x, s.y, "off"


# =============================================================================================
# The computer: tries a grid of shots in its head, refines the best ones, then misses a little on purpose
# =============================================================================================
ERR = {0: (6.5, 7.5), 1: (2.6, 3.0), 2: (0.55, 0.7)}   # angle / power spread per difficulty


def cpu_plan(world, tanks, me, wind, diff, rnd, shots=0):
    """A generator: yields while thinking, its last value is (angle, power, weapon)."""
    tgt = tanks[1 - me.idx]
    tx, ty = tgt.centre()
    mx, my = me.centre()
    right = tx > mx
    known = wind if diff > 0 else wind * rnd.uniform(0.2, 0.7)

    def score(res):
        ix, iy, hit = res
        if hit == "off":
            return 1e6 + abs(ix - tx)
        if hit is tgt:
            return 0.0
        if hit is me:
            return 1e5
        d = math.hypot(ix - tx, iy - ty)
        if math.hypot(ix - mx, iy - my) < 11:
            d += 300
        return d

    # The search runs over the elevation e (degrees above the horizon towards the target) so both sides think
    # alike: ties (several shots that all hit) go to the flatter shot for either tank. (It used to search the
    # raw barrel angle, which broke ties towards flat shots for the left tank but towards steep, wind-prone
    # lobs for the right one - the left tank won ~70% of the rounds between equal computers.)
    ang = (lambda e: e) if right else (lambda e: 180 - e)
    grid = []
    for e in range(16, 104, 5):
        for p in range(14, 101, 6):
            grid.append((score(simulate(world, tanks, me, ang(e), p, known, exact=False)), e, p))
        yield None
    grid.sort()
    best = grid[0]
    seen = set()
    for _, e0, p0 in grid[:3]:
        for e in range(e0 - 3, e0 + 4, 1):
            for p in range(p0 - 4, p0 + 5, 2):
                if (e, p) in seen or not 2 <= e <= 178 or not 5 <= p <= 100:
                    continue
                seen.add((e, p))
                s = score(simulate(world, tanks, me, ang(e), p, known))
                if s < best[0]:
                    best = (s, e, p)
        yield None
    miss, e, p = best
    a = ang(e)
    if miss > 0:                                  # fine power search for the best angle
        for dp in (-1, 1):
            q = p + dp
            if 5 <= q <= 100:
                s = score(simulate(world, tanks, me, a, q, known))
                if s < miss:
                    miss, p = s, q
    ea, ep = ERR[diff]
    k = max(0.55, 0.85 ** shots)                  # it learns a little with every shot this round
    a = clamp(a + rnd.gauss(0, ea * k), 1, 179)
    p = clamp(p + rnd.gauss(0, ep * k), 5, 100)
    w = 0
    if miss < 6 and me.ammo[1] and rnd.random() < (0.35, 0.6, 0.8)[diff]:
        w = 1
    elif miss < 16 and me.ammo[2] and rnd.random() < (0.45, 0.35, 0.2)[diff]:
        w = 2           # the splitter forgives a miss (it used to need 3 < miss, so it was never fired)
    elif diff > 0 and me.ammo[3] and miss < 8 and tgt.hp > 60 and rnd.random() < 0.08:
        w = 3
    yield (round(a), round(p), w)


# =============================================================================================
# A match: best of three rounds
# =============================================================================================
class Match:
    def __init__(self, W, H, mode="cpu", diff=1, seed=None, names=None, diffs=None):
        self.W, self.H = W, H
        self.mode, self.diff = mode, diff
        self.diffs = list(diffs) if diffs else [diff, diff]     # per tank (auto mode / balance runs can mix them)
        self.rnd = random.Random(seed)
        self.cpu = [mode in ("demo", "auto"), mode in ("cpu", "demo", "auto")]
        self.names = names or {"cpu": ["YOU", "COMPUTER"], "two": ["PLAYER 1", "PLAYER 2"],
                               "demo": ["BLUE", "RED"], "auto": ["BLUE", "RED"]}[mode]
        self.wins = [0, 0]
        self.round_no = 0
        self.starter = 0
        self.turns = 0
        self.t = 0.0
        self.paused = self.help = False
        self.winner = None
        self.fast = mode == "demo"
        self.quiet = mode == "demo"          # the computer duel behind the title makes no sound
        self.whistled = False
        self.new_round()

    def new_round(self):
        self.round_no += 1
        self.world = w = World(self.W, self.H, self.rnd.randrange(1 << 30))
        self.tanks = []
        for i, sx in enumerate(w.spawns):
            self.tanks.append(Tank(i, sx, w.first_solid(sx, 0), P_COLS[i]))
        self.turn = self.starter
        self.wind = self.rnd.randint(-6, 6)
        self.shells, self.parts, self.booms, self.floats = [], [], [], []
        self.flash = None
        self.msg, self.msg_t = "", 0.0
        self.round_turns = 0
        self.shots = [0, 0]
        self.mult = 1
        self.acc = 0.0
        self.round_winner = None
        self.last_path = [None, None]    # each player's previous shot, drawn faintly while they aim
        self.path, self.volley_hit = [], False
        self.begin_turn()

    def begin_turn(self):
        self.phase = "aim"
        self.aim_t = 0.0
        self.settle_t = 0.0
        self.plan = None
        self.target = None
        if self.cpu[self.turn]:
            t = self.tanks[self.turn]
            self.plan = cpu_plan(self.world, self.tanks, t, self.wind, self.diffs[self.turn], self.rnd,
                                 self.shots[self.turn])

    def sfx(self, name, vol=1.0, gap=0.04):
        if not self.quiet:
            SND.play(name, vol, gap)

    def say(self, s, ttl=2.5):
        self.msg, self.msg_t = s, ttl

    @property
    def active(self):
        return self.tanks[self.turn]

    # ----------------------------------------------------------------------------------------- input
    def key(self, k):
        if self.phase != "aim" or self.cpu[self.turn]:
            return
        t = self.active
        a0, p0, w0 = t.angle, t.power, t.weapon
        if k in ("left", "a"):
            t.angle = min(180, t.angle + 1)
        elif k in ("right", "d"):
            t.angle = max(0, t.angle - 1)
        elif k in ("up", "w"):
            t.power = min(100, t.power + 1)
        elif k in ("down", "s"):
            t.power = max(5, t.power - 1)
        elif k == "pgup":
            t.power = min(100, t.power + 10)
        elif k == "pgdn":
            t.power = max(5, t.power - 10)
        elif k in ("tab", "backtab"):
            step = 1 if k == "tab" else -1
            for _ in range(4):
                t.weapon = (t.weapon + step) % 4
                if t.ammo[t.weapon] is None or t.ammo[t.weapon] > 0:
                    break
        elif k in ("1", "2", "3", "4"):
            i = int(k) - 1
            if t.ammo[i] is None or t.ammo[i] > 0:
                t.weapon = i
            else:
                self.say("No %s left this round." % WEAPONS[i][0].lower(), 1.5)
                self.sfx("empty")
        elif k in (" ", "enter"):
            self.fire()
            return
        if t.angle != a0:
            self.sfx("aim", gap=0.05)
        elif t.power != p0:
            self.sfx("power", gap=0.05)
        elif t.weapon != w0:
            self.sfx("weapon")

    def fire(self):
        t = self.active
        if t.ammo[t.weapon] is not None:
            if t.ammo[t.weapon] <= 0:
                t.weapon = 0
            else:
                t.ammo[t.weapon] -= 1
        s = launch(self.world, t, w=t.weapon)
        self.shells = [s]
        self.whistled = False
        self.path, self.volley_hit = [(s.x, s.y)], False
        self.sfx("fire_heavy" if t.weapon == 1 else "fire")
        self.flash = [s.x, s.y, 0.14]
        r = self.rnd
        for _ in range(10):
            a = math.radians(t.angle + r.uniform(-25, 25))
            v = r.uniform(10, 34)
            self.parts.append([s.x, s.y, math.cos(a) * v, -math.sin(a) * v, 0.3, 0.3, (255, 230, 150), 0])
        for _ in range(5):
            self.parts.append([s.x, s.y, r.uniform(-4, 4), r.uniform(-8, -2), 1.1, 1.1, (200, 200, 205), 2])
        self.phase = "flight"
        self.shots[t.idx] += 1
        if t.ammo[t.weapon] == 0:
            t.weapon = 0

    # ----------------------------------------------------------------------------------------- simulation
    def update(self, dt, budget=None):
        if self.paused:
            return
        dt = min(dt, 0.1)
        self.t += dt
        if self.msg_t > 0:
            self.msg_t -= dt
        if self.phase == "aim" and self.plan is not None:
            t0 = time.perf_counter()
            while self.plan is not None:
                r = next(self.plan)
                if r is not None:
                    self.target, self.plan = r, None
                elif budget is not None and time.perf_counter() - t0 > budget:
                    break
        if self.phase in ("roundover", "matchover"):
            self.phase_t += dt
            if self.phase == "roundover" and self.phase_t > 3.2:
                self.next_round()
        self.acc += dt
        while self.acc >= PH:
            self.acc -= PH
            self.tick()

    def skip(self):
        if self.phase == "roundover" and self.phase_t > 0.6:
            self.next_round()

    def next_round(self):
        if max(self.wins) >= 2:
            self.phase, self.phase_t = "matchover", 0.0
            self.winner = 0 if self.wins[0] > self.wins[1] else 1
            self.sfx("match_lose" if self.mode == "cpu" and self.winner == 1 else "match_win")
        else:
            self.starter = 1 - self.round_winner      # the loser of a round opens the next one
            self.new_round()

    def tick(self):
        w = self.world
        for c in w.clouds:
            c[0] += (self.wind * 1.4 + 0.6) * PH
            if c[0] - c[2] > w.W:
                c[0] = -c[2]
            elif c[0] + c[2] < 0:
                c[0] = w.W + c[2]
        if self.phase == "aim":
            self.aim_t += PH
            if self.cpu[self.turn] and self.target is not None:
                t = self.active
                ta, tp, tw = self.target
                t.weapon = tw
                sa, sp = (3, 3) if self.fast else (2, 2)
                if t.angle != ta:
                    t.angle += clamp(ta - t.angle, -sa, sa)
                elif t.power != tp:
                    t.power += clamp(tp - t.power, -sp, sp)
                elif self.aim_t > (0.4 if self.fast else 1.0):
                    self.fire()
        elif self.phase == "flight":
            if self.shells and int(round(self.shells[0].age * 60)) % 3 == 0:
                self.path.append((self.shells[0].x, self.shells[0].y))
            for s in list(self.shells):
                s.trail.append((s.x, s.y))
                vy0 = s.vy
                hit = fly(w, self.tanks, s, self.wind)
                if hit is None and not self.whistled and vy0 < 0 <= s.vy:
                    self.whistled = True              # over the top of the arc: down it comes
                    self.sfx("whistle")
                if hit is None and WEAPONS[s.w][4] == "split" and not s.split and vy0 < 0 <= s.vy:
                    s.split = True
                    self.sfx("split")
                    sp = math.hypot(s.vx, s.vy) * 0.16 + 3
                    for d in (-1, 1):
                        f = Shell(s.x, s.y, s.vx + d * sp, s.vy - 2, s.w, s.owner)
                        f.split, f.safe = True, False
                        f.trail.extend(s.trail)
                        self.shells.append(f)
                    for _ in range(8):
                        self.parts.append([s.x, s.y, self.rnd.uniform(-20, 20), self.rnd.uniform(-20, 10), 0.3, 0.3,
                                           (255, 240, 170), 0])
                if hit is None:
                    continue
                self.shells.remove(s)
                if hit == "off":
                    if not self.shells and not self.volley_hit:
                        self.say("Wide - that one left the field.")
                        self.sfx("miss")
                    continue
                self.explode(s.x, s.y, s.w, s.owner, hit == "water", hit if isinstance(hit, Tank) else None)
            if not self.shells:
                self.phase = "settle"
                self.settle_t = 0.0
                self.last_path[self.turn] = self.path
        if w.dirty:
            w.settle_step()
        for t in self.tanks:
            fall = t.physics(w)
            if fall is not None and fall > 4.5:
                dmg = int(min(40, (fall - 4.5) * 2.2))
                if dmg > 0 and t.hp > 0:
                    self.hurt(t, dmg, "fall")
            elif fall is not None and fall > 1.5:
                self.sfx("land", gap=0.1)
        self.update_fx()
        if self.phase == "settle":
            self.settle_t += PH
            calm = not w.dirty and all(t.fall0 is None for t in self.tanks) and not self.booms
            if (calm and self.settle_t > (0.5 if self.fast else 0.8)) or self.settle_t > 8:
                self.end_turn()

    def hurt(self, t, dmg, why=""):
        dmg = int(dmg * self.mult)
        t.hp = max(0, t.hp - dmg)
        t.hit_t = 0.18
        cx, cy = t.centre()
        self.floats.append([cx, cy - 6, "-%d" % dmg, (255, 236, 120) if why != "fall" else (255, 190, 150), 1.8])
        if why == "fall":
            self.say("%s fell into the hole: %d damage." % (self.names[t.idx].capitalize(), dmg), 2.0)
        if t.hp <= 0:
            self.sfx("destroyed")
        else:
            self.sfx("fall" if why == "fall" else "hit", gap=0.08)
        if t.hp <= 0:
            self.booms.append([cx, cy, 6.5, 0.0])
            r = self.rnd
            for _ in range(36):
                a = r.uniform(0, 6.283)
                v = r.uniform(10, 50)
                self.parts.append([cx, cy, math.cos(a) * v, math.sin(a) * v - 20, 1.0, 1.0,
                                   r.choice([(255, 220, 120), (255, 140, 60), t.colour, (80, 80, 84)]), 1])

    def explode(self, x, y, widx, owner, water=False, direct=None):
        w, r = self.world, self.rnd
        name, rad, dmg, _, kind = WEAPONS[widx]
        self.volley_hit = True
        if self.path is not None:
            self.path.append((x, y))
        if kind == "dirt":
            self.sfx("dirt")
            w.add_dirt(x, y, rad)
            for _ in range(18):
                a = r.uniform(0, 6.283)
                self.parts.append([x, y, math.cos(a) * 25, math.sin(a) * 25 - 10, 0.5, 0.5, (180, 130, 80), 1])
            tgt = self.tanks[1 - owner]
            cx, cy = tgt.centre()
            if math.hypot(cx - x, cy - y) < rad + 3:
                self.say("Buried!", 2.0)
            return
        w.carve(x, y, rad)
        self.booms.append([x, y, rad, 0.0])
        if water:
            self.sfx("splash")
        else:
            self.sfx("boom_big" if rad >= 6 else "boom_small" if kind == "split" else "boom", gap=0.06)
        for _ in range(int(10 + rad * 4)):
            a = r.uniform(3.4, 6.0) if not water else r.uniform(4.2, 5.2)
            v = r.uniform(15, 55)
            c = r.choice([w.pal["dirt"], w.pal["deep"], (255, 200, 90), (255, 130, 50)]) if not water else \
                r.choice([(210, 235, 255), w.pal["water"]])
            self.parts.append([x, y, math.cos(a) * v, math.sin(a) * v, r.uniform(0.6, 1.2), 1.2, c, 1])
        for _ in range(int(rad * 1.5)):
            self.parts.append([x + r.uniform(-rad, rad) * 0.5, y + r.uniform(-rad, rad) * 0.5, r.uniform(-3, 3),
                               r.uniform(-9, -3), r.uniform(1.2, 2.2), 2.2, (120, 116, 112), 2])
        best = 0
        for t in self.tanks:
            if t.hp <= 0:
                continue
            cx, cy = t.centre()
            d = 0.0 if t is direct else math.hypot(cx - x, cy - y)
            reach = rad + 4.0
            if d < reach:
                n = max(3, int(round(dmg * (1 - 0.7 * d / reach))))
                if t.idx != owner:
                    best = max(best, n)
                self.hurt(t, n)
        if best >= dmg * 0.8:
            self.say("Direct hit!", 2.0)
        elif best > 0 and len(self.shells) == 0:
            self.say("Hit!", 1.5)
        elif water and best == 0:
            self.say("Splash.", 1.2)

    def update_fx(self):
        keep = []
        for p in self.parts:
            p[4] -= PH
            if p[4] <= 0:
                continue
            if p[7] == 1:
                p[3] += G * 1.2 * PH
            elif p[7] == 2:
                p[2] += self.wind * 0.6 * PH
            p[0] += p[2] * PH
            p[1] += p[3] * PH
            keep.append(p)
        self.parts = keep[-600:]
        for b in self.booms:
            b[3] += PH
        self.booms = [b for b in self.booms if b[3] < 0.38]
        for f in self.floats:
            f[1] -= 7 * PH
            f[4] -= PH
        self.floats = [f for f in self.floats if f[4] > 0]
        for t in self.tanks:
            if t.shown > t.hp:      # hold the lost chunk for a moment, then let it drain away
                t.shown = max(t.hp, t.shown - (0 if t.hit_t > 0 else 45 * PH))
            t.hit_t = max(0.0, t.hit_t - PH)
        if self.flash:
            self.flash[2] -= PH
            if self.flash[2] <= 0:
                self.flash = None

    def end_turn(self):
        alive = [t.hp > 0 for t in self.tanks]
        self.turns += 1
        self.round_turns += 1
        if not all(alive):
            if not any(alive):                       # both gone: the one who fired loses
                win = 1 - self.turn
            else:
                win = alive.index(True)
            self.round_winner = win
            self.wins[win] += 1
            self.phase, self.phase_t = "roundover", 0.0
            self.sfx("round")
            return
        self.turn = 1 - self.turn
        self.wind = int(clamp(round(self.wind * 0.35 + self.rnd.gauss(0, 5)), -10, 10))
        if self.round_turns == 30:
            self.mult = 2
            self.say("Sudden death: every hit counts double!", 3.5)
            self.sfx("sudden")
        elif self.round_turns == 50:
            self.mult = 4
            self.say("Sudden death: every hit counts four times!", 3.5)
            self.sfx("sudden")
        else:
            self.sfx("turn")
        if abs(self.wind) >= 6:                       # a strong wind is heard as well as seen
            self.sfx("wind", vol=0.5 + 0.05 * (abs(self.wind) - 6))
        self.begin_turn()


# =============================================================================================
# Drawing
# =============================================================================================
def bar(v, n=10):
    f = int(math.ceil(clamp(v, 0, 1) * n))
    return "█" * f + "░" * (n - f)


def wind_text(w):
    if w == 0:
        return "calm"
    n = 1 if abs(w) <= 3 else 2 if abs(w) <= 7 else 3
    return ("◀" * n + " %d" % abs(w)) if w < 0 else ("%d " % abs(w) + "▶" * n)


def wind_colour(w):
    return (200, 230, 255) if abs(w) <= 3 else (255, 230, 140) if abs(w) <= 7 else (255, 150, 120)


def wind_gauge(cv, col, row, w, n):
    """WIND  ····|▶▶▶·  6 : a centred scale, filled towards where the wind blows (n cells a side, 10 = full)."""
    bg = (16, 16, 28)
    wc = wind_colour(w)
    cells = int(math.ceil(abs(w) * n / 10))
    left = "".join("◀" if w < 0 and n - i <= cells else "·" for i in range(n))
    right = "".join("▶" if w > 0 and i < cells else "·" for i in range(n))
    num = "calm" if w == 0 else "%d" % abs(w)
    cv.put(col, row, " WIND ", (150, 156, 190), bg)
    x = col + 6
    for ch in left:
        cv.put(x, row, ch, wc if ch != "·" else (70, 74, 100), bg)
        x += 1
    cv.put(x, row, "|", (150, 156, 190), bg)
    x += 1
    for ch in right:
        cv.put(x, row, ch, wc if ch != "·" else (70, 74, 100), bg)
        x += 1
    cv.put(x, row, " %-4s" % num, wc, bg)


def wind_width(n):
    return 6 + 2 * n + 1 + 5


def draw_tank(px, t, W, H, now):
    x, y = t.x, int(t.y)
    alive = t.hp > 0
    c = t.colour if alive else (64, 60, 58)
    if t.hit_t > 0 and int(t.hit_t * 30) % 2 == 0:   # struck: a white flash
        c = (255, 255, 255)
    light, dark = shade(c, 1.22), shade(c, 0.7)

    def dot(xx, yy, col):
        if 0 <= xx < W and 0 <= yy < H:
            px[yy][xx] = col
    a = math.radians(t.angle if alive else (30 if t.idx == 0 else 150))
    ca, sa = math.cos(a), math.sin(a)
    for i in range(1, 6):
        dot(int(x + 0.5 + ca * i), int(y - 3.5 - sa * i), (222, 222, 230) if alive else (54, 52, 50))
    for dx in (-1, 0, 1):
        dot(x + dx, y - 4, light if dx == 0 else c)
    for dx in range(-2, 3):
        dot(x + dx, y - 3, light)
    for dx in range(-3, 4):
        dot(x + dx, y - 2, c if abs(dx) < 3 else dark)
    for dx in range(-3, 4):
        dot(x + dx, y - 1, (92, 92, 100) if (dx + x) % 2 else (38, 38, 44))


def render(m, cols, rows, title_mode=False):
    cv = Canvas(cols, rows, HUD_BG)
    w = m.world
    WH = min(w.H, cv.H)
    VW = min(w.W, cols)
    px = cv.px
    for y in range(WH):
        row = w.sky[y]
        px[y] = row[:cols] if w.W >= cols else row + [row[-1]] * (cols - w.W)
    now = m.t
    pal = w.pal
    for cx, cy, cw, ch, al in w.clouds:          # clouds drift with the wind
        for y in range(max(0, int(cy - ch)), min(WH, int(cy + ch) + 1)):
            row = px[y]
            dy = (y - cy) / ch
            for x in range(max(0, int(cx - cw)), min(VW, int(cx + cw) + 1)):
                dx = (x - cx) / cw
                d = dx * dx + dy * dy * (1.6 if dy > 0 else 1.0) - 0.18 * math.sin(x * 0.9 + cy)
                if d < 1:
                    row[x] = mix(row[x], pal["cloud"], al * min(1.0, (1 - d) * 2.2))
    ymin = min(min(w.top), w.wl if w.wl is not None else w.H)
    for y in range(max(0, ymin), WH):
        row = px[y]
        merged = [s if t is None else t for t, s in zip(w.trows[y], row)]
        if len(row) > len(merged):
            merged += row[len(merged):]
        px[y] = merged
    if w.wl is not None and w.wl < WH:              # a glint on the lake
        y, row, col0 = w.wl, px[w.wl], int(now * 3)
        for x in range(VW):
            if not w.cols[x][y] and (x + col0) % 9 == 0:
                row[x] = mix(row[x], (240, 250, 255), 0.6)
    for t in m.tanks:
        draw_tank(px, t, cols, WH, now)
    # aim indicator: a dotted line from the barrel, longer with more power
    t = m.active
    if m.phase == "aim" and t.hp > 0:
        last = m.last_path[m.turn]
        if last and not title_mode:     # your previous shot, faintly, with a cross where it ended
            for i, (x, y) in enumerate(last[:-1]):
                xi, yi = int(x), int(y)
                if i % 2 == 0 and 0 <= xi < cols and 0 <= yi < WH:
                    px[yi][xi] = mix(px[yi][xi], (255, 255, 255), 0.4)
            ex, ey = int(last[-1][0]), int(last[-1][1])
            for dx, dy in ((-1, -1), (1, 1), (-1, 1), (1, -1), (0, 0)):
                if 0 <= ex + dx < cols and 0 <= ey + dy < WH:
                    px[ey + dy][ex + dx] = mix(px[ey + dy][ex + dx], (255, 255, 255), 0.7)
        a = math.radians(t.angle)
        ca, sa = math.cos(a), math.sin(a)
        L = 6 + t.power * 0.16
        d = 7.0
        lc = shade(t.colour, 1.35)
        while d <= 7 + L:
            k = (d - 7) / max(1, L)
            xx, yy = int(t.x + 0.5 + ca * d), int(t.y - 3.5 - sa * d)
            if 0 <= xx < cols and 0 <= yy < WH:
                px[yy][xx] = mix(lc, (255, 255, 255), 0.5 * (1 - k)) if int(now * 6) % 2 or k < 0.9 else lc
                if yy + 1 < WH:          # a dark under-pixel keeps the dots readable on bright sky
                    px[yy + 1][xx] = mix(px[yy + 1][xx], (16, 12, 24), 0.55)
            d += 2.4
    for b in m.booms:                                # fireballs
        bx, by, r, bt = b
        k = bt / 0.38
        rr = r * (0.55 + 0.6 * k)
        for y in range(max(0, int(by - rr)), min(WH, int(by + rr) + 1)):
            row = px[y]
            for x in range(max(0, int(bx - rr)), min(cols, int(bx + rr) + 1)):
                d = math.hypot(x + 0.5 - bx, y + 0.5 - by) / rr
                if d < 1:
                    core = mix((255, 255, 230), (255, 170, 60), min(1.0, d + k))
                    edge = mix(core, (200, 60, 30), k)
                    row[x] = mix(row[x], edge, (1 - k * 0.8) * (1 - d * d * 0.6))
        if bt < 0.12:                                # the first instant: a white shock ring
            sr = r * (1.0 + bt * 6)
            for i in range(int(sr * 6) + 8):
                aa = i * 6.283 / (int(sr * 6) + 8)
                x, y = int(bx + math.cos(aa) * sr), int(by + math.sin(aa) * sr)
                if 0 <= x < cols and 0 <= y < WH:
                    px[y][x] = mix(px[y][x], (255, 255, 255), 0.8 * (1 - bt / 0.12))
    for p in m.parts:
        x, y = int(p[0]), int(p[1])
        if 0 <= x < cols and 0 <= y < WH:
            f = p[4] / p[5]
            px[y][x] = mix(px[y][x], p[6], min(1.0, f * (0.6 if p[7] == 2 else 1.4)))
    for s in m.shells:
        n = len(s.trail)
        for i, (x, y) in enumerate(s.trail):
            xi, yi = int(x), int(y)
            if 0 <= xi < cols and 0 <= yi < WH:
                px[yi][xi] = mix(px[yi][xi], (255, 196, 100), 0.2 + 0.7 * i / max(1, n))
        xi, yi = int(s.x), int(s.y)
        if 0 <= xi < cols:
            if 0 <= yi < WH:
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):   # a dark rim: the shell reads on any sky
                    if 0 <= xi + dx < cols and 0 <= yi + dy < WH:
                        px[yi + dy][xi + dx] = mix(px[yi + dy][xi + dx], (24, 16, 28), 0.6)
                px[yi][xi] = (255, 255, 240)
            elif yi < 0:
                px[0][xi] = (255, 255, 120) if int(now * 10) % 2 else (255, 160, 60)
    if m.flash:
        fx, fy, ft = m.flash
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                x, y = int(fx) + dx, int(fy) + dy
                if 0 <= x < cols and 0 <= y < WH:
                    px[y][x] = (255, 255, 200) if dx == 0 or dy == 0 else (255, 200, 90)
    for f in m.floats:                               # damage numbers on a dark backing
        cv.put(int(f[0]) - len(f[2]) // 2 - 1, int(f[1]) // 2, " %s " % f[2],
               f[3] if f[4] > 0.5 or int(now * 8) % 2 else shade(f[3], 0.7), (24, 14, 20))
    if not title_mode:
        overlay_texts(cv, m)
    return cv


SHORT = ["Shell", "Heavy", "Splitter", "Dirt"]
BAR_BG = (16, 16, 28)


def hp_bar(t, n):
    """The HP bar as (text, colour) runs: what is left, the chunk just lost (white, draining), what is gone."""
    hpc = (120, 230, 110) if t.hp > 50 else (240, 210, 80) if t.hp > 25 else (255, 90, 80)
    a = int(math.ceil(clamp(t.hp / 100, 0, 1) * n))
    b = max(a, int(math.ceil(clamp(t.shown / 100, 0, 1) * n)))
    return [("█" * a, hpc), ("█" * (b - a), (255, 236, 210)), ("░" * (n - b), (64, 68, 92))], hpc


def put_runs(cv, x, row, runs, bg=BAR_BG):
    for txt, fg in runs:
        cv.put(x, row, txt, fg, bg)
        x += len(txt)
    return x


def overlay_texts(cv, m):
    cols, rows = cv.cols, cv.rows
    now = m.t
    # top: both players' panels and the wind; the player whose turn it is has the bright name tag
    n = 10 if cols >= 100 else 7
    widths = []
    for i, t in enumerate(m.tanks):
        widths.append(len(m.names[i]) + 3 + 1 + n + 5 + 3)
    wn = 10 if cols - sum(widths) >= wind_width(10) + 4 else 5 if cols - sum(widths) >= wind_width(5) + 2 else 3
    for i, t in enumerate(m.tanks):
        on = i == m.turn and m.phase in ("aim", "flight", "settle")
        name = (" ▸%s " if on else "  %s ") % m.names[i]
        runs, hpc = hp_bar(t, n)
        x = 0 if i == 0 else cols - widths[i]
        if on:
            cv.put(x, 0, name, (14, 14, 20), t.colour)
        else:
            cv.put(x, 0, name, mix(t.colour, (255, 255, 255), 0.25), mix(t.colour, BAR_BG, 0.65))
        x = put_runs(cv, x + len(name), 0, [(" ", hpc)] + runs + [(" %3d " % t.hp, hpc)])
        cv.put(x, 0, "●" * m.wins[i] + "○" * (2 - m.wins[i]) + " ", (255, 214, 120), BAR_BG)
    wind_gauge(cv, (cols - wind_width(wn)) // 2, 0, m.wind, wn)
    # whose turn
    t = m.active
    if m.phase in ("aim", "flight", "settle"):
        nm = m.names[m.turn]
        if m.phase == "aim":
            if m.cpu[m.turn]:
                s = "  %s IS AIMING  " % nm
            elif m.mode == "cpu":
                s = "  YOUR TURN - aim and fire  "
            else:
                s = "  %s - YOUR TURN  " % nm
        else:
            s = "  %s FIRED  " % nm
        cv.center(1, s, (12, 12, 18), t.colour if m.phase == "aim" else shade(t.colour, 0.7))
        if m.phase == "aim" and t.hp > 0:
            bob = 1 if int(now * 3) % 2 else 0
            cv.put(t.x, max(2, int(t.y - 9) // 2 - bob), "▼", shade(t.colour, 1.25))
    if m.msg_t > 0 and m.msg:
        cv.center(2, " %s " % m.msg, (240, 240, 246), (20, 22, 40))
    hud(cv, m)
    if m.phase == "roundover":
        wn = m.round_winner
        who = m.names[wn]
        lines = ["%s %s THE ROUND" % (who, "WIN" if who == "YOU" else "WINS"), "", "rounds   %d : %d" % tuple(m.wins)]
        if m.phase_t > 0.6 and m.mode != "auto":
            lines += ["", "Enter  continue"]
        wd = max(len(l) for l in lines) + 4
        cv.box(max(0, (cols - wd) // 2), max(3, rows // 2 - 5), lines, (14, 14, 20), m.tanks[wn].colour)


def hud(cv, m):
    """The bottom bar: who is aiming, angle, power, the shells (chosen one lit, used-up ones dim), key hints."""
    cols, r = cv.cols, cv.rows - 1
    t = m.active
    rel = t.angle if t.angle <= 90 else 180 - t.angle
    arrow = "↗" if t.angle < 88 else "↖" if t.angle > 92 else "↑"
    human = not m.cpu[m.turn]
    dim = (130, 136, 170)
    chips = []
    for i, (wname, _, _, ammo, _) in enumerate(WEAPONS):
        left = t.ammo[i]
        txt = " %d %s%s " % (i + 1, SHORT[i], "" if left is None else " %d" % left)
        if i == t.weapon:
            chips.append((txt, (20, 14, 10), (250, 214, 120)))
        elif left == 0:
            chips.append((txt, (78, 80, 100), HUD_BG))
        else:
            chips.append((txt, (200, 200, 214), HUD_BG))
    wname, _, _, ammo, _ = WEAPONS[t.weapon]
    single = [(" [%d] %s%s " % (t.weapon + 1, wname, "" if ammo is None else " x%d" % t.ammo[t.weapon]),
               (255, 214, 130), HUD_BG)]
    groups = [[[(" %s " % m.names[m.turn], (14, 14, 20), t.colour)], 0],
              [[("  ANGLE %2d° %s " % (rel, arrow), (235, 235, 245), HUD_BG)], 1],
              [[(" POWER %3d " % t.power, (235, 235, 245), HUD_BG)], 1],
              [[(" ", HUD_BG, HUD_BG)] + chips, 2],
              [[("  round %d " % m.round_no, (170, 174, 196), HUD_BG)], 6]]
    if human:
        groups += [[[("  Tab shell  Space fire ", dim, HUD_BG)], 4], [[("  ←→ angle  ↑↓ power ", dim, HUD_BG)], 3]]
    right = " ? help  Esc menu "
    room = cols - len(right)
    width = lambda: sum(len(s) for g in groups for s, _, _ in g[0])
    while width() > room and len(groups) > 1:
        worst = max(groups, key=lambda g: g[1])
        if worst[1] == 2 and worst[0] is not single:    # out of room for all four: show just the chosen shell
            worst[0], worst[1] = single, 1.5
            continue
        groups.remove(worst)
    cv.put(0, r, " " * cols, HUD_BG, HUD_BG)
    x = 0
    for segs, _ in groups:
        for s, fg, bg in segs:
            cv.put(x, r, s, fg, bg)
            x += len(s)
    if x + len(right) <= cols:
        cv.put(cols - len(right), r, right, dim, HUD_BG)


def render_over(cv, m, record, streak):
    wn = m.winner
    if m.mode == "cpu":
        head = "YOU WIN THE MATCH!" if wn == 0 else "THE COMPUTER WINS THE MATCH"
    else:
        head = "%s WINS THE MATCH!" % m.names[wn]
    lines = [head, "", "rounds   %d : %d" % tuple(m.wins)]
    if m.mode == "cpu":
        lines.append("win streak vs computer (%s): %d%s" % (DIFFS[m.diff], streak, "   new record!" if record else ""))
    if m.mode == "auto":
        lines += ["", "the next duel starts in a moment      Esc  back to the title"]
    else:
        lines += ["", "Enter  play again      Esc / Q  back to the title"]
    wd = max(len(l) for l in lines) + 4
    x, y = max(0, (cv.cols - wd) // 2), max(2, cv.rows // 2 - 5)
    cv.frame(x - 1, y * 2 - 1, wd + 2, (len(lines) + 2) * 2 + 2, m.tanks[wn].colour)   # a rim in the winner's colour
    cv.box(x, y, lines, (240, 240, 246), (22, 22, 42))
    cv.put(max(0, (cv.cols - wd) // 2) + 2, max(2, cv.rows // 2 - 5) + 1, head, m.tanks[wn].colour, (22, 22, 42))


HELP = [
    "SKYSHOT - keys",
    "",
    "Left / Right  (A / D)   turn the barrel (angle)",
    "Up / Down     (W / S)   power      PgUp / PgDn  power +-10",
    "Tab  or  1 - 4          choose the shell",
    "Space / Enter           fire",
    "",
    "Wind changes every turn and pushes the shells (arrow at",
    "the top). Craters swallow tanks - and falling hurts.",
    "Two won rounds win the match; new land every round.",
    "",
    "1 Shell (unlimited)   2 Heavy shell (3 per round)",
    "3 Splitter (2, bursts in three at the top of its arc)",
    "4 Dirt ball (2, buries the other tank in fresh earth)",
    "",
    "Esc / P                 pause menu (Q quit, M sound)",
    "?                       this help",
    "",
    "Auto mode: the game plays itself (Space pause, +/- speed,",
    "Esc stop) - two computers at the chosen difficulty duel.",
]
PAUSE = ["P A U S E D", "", "Esc / P / Enter   continue", "?                 help", "M                 sound on / off",
         "V                 view: pixels / ASCII / mono",
         "Q                 quit to the menu"]


def world_size(cols, rows):
    return max(70, cols), max(42, (rows - 1) * 2)


class TitleDemo:
    """The computer playing itself behind the title (also usable as a launcher preview)."""

    def __init__(self, cols, rows, seed=3):
        self.size = (cols, rows)
        self.seed = seed
        self.m = Match(*world_size(cols, rows), mode="demo", diff=1, seed=seed)
        self.diff = 1

    def step(self, cols, rows, dt):
        if (cols, rows) != self.size:
            self.__init__(cols, rows, self.seed)
        m = self.m
        m.update(dt, budget=0.004)
        if m.phase == "roundover" and m.phase_t > 2.0:
            m.next_round()
        if m.phase == "matchover" and m.phase_t > 1.0:
            self.seed += 1
            self.m = Match(*world_size(cols, rows), mode="demo", diff=1, seed=self.seed)
        return self.m

    def frame(self, cols, rows, dt, help_=False, sel=0):
        m = self.step(cols, rows, dt)
        cv = render(m, cols, rows, title_mode=True)
        best = load_scores().get(GAME, {})
        rec = "  ".join("%s %d" % (d, best["streak " + d]) for d in DIFFS if ("streak " + d) in best)
        items = ["One player vs computer", "Two players (one keyboard)", AUTO_LABEL,
                 "Computer:  < %s >" % DIFFS[self.diff]]
        title_screen(cv, "SKYSHOT", "an artillery duel on crumbling hills", items, sel,
                     "best win streak vs computer:  " + rec if rec else None,
                     extra=["", "Left / Right: computer difficulty"],
                     keys="↑↓ choose  ←→ difficulty  Enter play  M %s  ? help  Esc quit" % SND.label().lower(),
                     help_lines=HELP, show_help=help_, dim=0.4)
        return cv


_PREVIEW = []


def preview(cv, x, y, w, h, t):
    """Launcher thumbnail: paint a live computer duel into cv at pixel box (x, y, w, h); t = time in seconds."""
    rows = (h + 1) // 2 + 1
    if not _PREVIEW or _PREVIEW[0].size != (w, rows):
        _PREVIEW[:] = [TitleDemo(w, rows), t]
    demo = _PREVIEW[0]
    dt = min(0.1, max(0.0, t - _PREVIEW[1]))
    _PREVIEW[1] = t
    m = demo.step(w, rows, dt)
    sub = render(m, w, rows, title_mode=True)
    for yy in range(h):
        if 0 <= y + yy < cv.H and yy < sub.H:
            cv.px[y + yy][x:x + w] = sub.px[yy][:max(0, min(w, cv.W - x))]


# =============================================================================================
# Main loop
# =============================================================================================
def too_small(term):
    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (70x22).")


def auto_frame(m, auto, cols, rows):
    """One auto-mode frame: the real duel with its HUD, the AUTO bar just above the HUD, the end box."""
    cv = render(m, cols, rows)
    names = "%s %s vs %s %s" % (m.names[0], DIFFS[m.diffs[0]], m.names[1], DIFFS[m.diffs[1]])
    auto.banner(cv, row=rows - 2, extra=names if cols >= 110 else "")
    if m.phase == "matchover":
        render_over(cv, m, None, 0)
    return cv


def auto_step(m, auto, dt, budget=0.012):
    """Advance an auto-mode duel by a real frame of dt: speed x0.25..x8 runs that many physics steps."""
    n = auto.steps(dt, PH)
    for i in range(n):
        m.update(PH, budget=budget if i == 0 else 0.0)   # the computers think within the frame budget
    return n


def screenshot(cols=100, rows=32):
    """README picture: real play (computer vs computer, normal) with a fixed seed, at a good moment, HUD and all.
    Seed 4, round 3 on cratered hills: RED's splitter lands on BLUE (direct hit, 2 hp left) with two more
    bomblets still falling."""
    m = Match(*world_size(cols, rows - 1), mode="auto", diff=1, seed=4)
    m.quiet = True
    for _ in range(4286):                     # physics steps (71 s of play)
        m.update(PH)
    return render(m, cols, rows)


def run_auto(term, diff, seconds=None, headless=None):
    """Auto mode: computer vs computer at the chosen difficulty, one match after the other, until Esc.
    headless=(cols, rows) runs without a terminal at x8 for `seconds` (the self-test); never records scores."""
    auto = AutoMode(8.0 if headless else 1.0)
    rnd = random.Random()
    matches = 0
    t_end = time.time() + seconds if seconds else None
    while True:
        cols, rows = headless or term.size()
        m = Match(*world_size(cols, rows - 1), mode="auto", diff=diff, seed=rnd.randrange(1 << 30))
        m.quiet = bool(headless)
        last = time.time()
        while True:
            now = time.time()
            if t_end and now > t_end:
                return matches
            if headless:
                auto_step(m, auto, 1 / 30, budget=None)
            else:
                for k in term.keys(0):
                    a = auto.key(k)
                    if a == "stop":
                        return matches
                    if a == "sound":
                        if SND.toggle():
                            SND.play("sound_on")
                auto_step(m, auto, min(0.1, now - last))
                last = now
                cols, rows = term.size()
                if cols < 70 or rows < 22:
                    too_small(term)
                    time.sleep(0.2)
                    continue
                term.write(auto_frame(m, auto, cols, rows).emit())
                time.sleep(max(0.0, 1 / 30 - (time.time() - now)))
            if m.phase == "matchover" and m.phase_t > 3.0:   # the result box for ~3 s, then the next duel
                matches += 1
                break


def main():
    with Terminal() as term:
        cols, rows = term.size()
        demo = TitleDemo(cols, rows)
        sel = 0
        streak = [0, 0, 0]
        while True:
            help_, go = False, False
            last = time.time()
            while not go:
                now = time.time()
                cols, rows = term.size()
                if cols < 70 or rows < 22:
                    too_small(term)
                    if any(k in ("q", "esc") for k in term.keys(0.3)):
                        return
                    continue
                term.write(demo.frame(cols, rows, min(0.1, now - last), help_, sel).emit())
                last = now
                for k in term.keys(1 / 30):
                    if help_:
                        help_ = False
                    elif k == "?":
                        help_ = True
                    elif k in ("q", "esc"):
                        return
                    elif k in ("up", "w"):
                        sel = (sel - 1) % 4
                        SND.play("menu")
                    elif k in ("down", "s"):
                        sel = (sel + 1) % 4
                        SND.play("menu")
                    elif k in ("left", "a", "right", "d"):
                        demo.diff = (demo.diff + (1 if k in ("right", "d") else -1)) % 3
                        SND.play("menu")
                    elif k == "m":
                        if SND.toggle():
                            SND.play("sound_on")
                    elif k in ("1", "2", "3"):
                        sel = int(k) - 1
                        go = True
                        SND.play("start")
                    elif k in ("enter", " "):
                        go = True
                        SND.play("start")
            if sel == 2:
                run_auto(term, demo.diff)
                continue
            mode = "two" if sel == 1 else "cpu"
            diff = demo.diff
            while True:                                   # one match; Enter on the end screen starts another
                m = Match(*world_size(cols, rows), mode=mode, diff=diff)
                last = time.time()
                record = None
                back = again = False
                while not (back or again):
                    now = time.time()
                    for k in term.keys(0):
                        if m.phase == "matchover":
                            if k in ("q", "esc"):
                                back = True
                            elif k in ("enter", " ") and m.phase_t > 0.5:
                                again = True
                                SND.play("start")
                            continue
                        a = shared_key(k, m.paused, pause_keys=("esc", "p", "q"))
                        if a == "pause":
                            m.paused = True
                            SND.play("pause")
                        elif a == "resume":
                            m.paused = m.help = False
                        elif a == "quit":
                            back = True
                        elif a == "help":
                            m.help = not m.help
                            m.paused = True
                        elif a == "sound":
                            if SND.toggle():
                                SND.play("sound_on")
                        elif a is None:
                            if m.phase == "roundover" and k in ("enter", " "):
                                m.skip()
                            else:
                                m.key(k)
                    m.update(min(0.1, now - last), budget=0.012)
                    last = now
                    if m.phase == "matchover" and record is None:
                        record = False
                        if mode == "cpu":
                            if m.winner == 0:
                                streak[diff] += 1
                                record = submit(GAME, "streak " + DIFFS[diff], streak[diff])
                            else:
                                streak[diff] = 0
                    cols, rows = term.size()
                    if cols < 70 or rows < 22:
                        too_small(term)
                        time.sleep(0.2)
                        continue
                    cv = render(m, cols, rows)
                    if m.paused:
                        overlay(cv, HELP if m.help else PAUSE + ["", SND.label()])
                    if m.phase == "matchover":
                        render_over(cv, m, record, streak[diff])
                    term.write(cv.emit())
                    time.sleep(max(0.0, 1 / 30 - (time.time() - now)))
                if back:
                    break


# =============================================================================================
# Tests
# =============================================================================================
def play_match(seed, diff=1, W=160, H=88, max_turns=400):
    m = Match(W, H, mode="demo", diff=diff, seed=seed)
    m.fast = False
    steps = 0
    while m.phase != "matchover":
        m.update(1 / 30)
        if m.phase == "roundover":
            m.next_round()
        steps += 1
        assert m.turns <= max_turns, "seed %d: no winner after %d turns" % (seed, m.turns)
        assert steps < 400000, "seed %d: the match is stuck in phase %s" % (seed, m.phase)
    return m


def aim_trial(diff, n=40, seed=100):
    """Shots by the computer at a stationary target on fresh land: how many do damage?"""
    hits = 0
    for i in range(n):
        m = Match(160, 88, mode="demo", diff=diff, seed=seed + i)
        me = m.tanks[m.turn]
        tgt = m.tanks[1 - m.turn]
        plan = cpu_plan(m.world, m.tanks, me, m.wind, diff, m.rnd)
        res = None
        for res in plan:
            pass
        a, p, _ = res
        ix, iy, hit = simulate(m.world, m.tanks, me, a, p, m.wind)
        cx, cy = tgt.centre()
        if hit is tgt or (hit != "off" and math.hypot(ix - cx, iy - cy) < WEAPONS[0][1] + 4):
            hits += 1
    return hits


def selftest():
    t0 = time.time()
    n = 0
    for seed in range(30):                     # every land: both tanks on solid ground, apart, inside the map
        for W, H in ((70, 42), (160, 88), (220, 120)):
            m = Match(W, H, mode="two", seed=seed)
            w = m.world
            a, b = m.tanks
            for t in m.tanks:
                assert 4 <= t.x <= W - 5, "seed %d: tank outside the map" % seed
                assert w.cols[t.x][int(t.y)] != 0, "seed %d: tank %d floats" % (seed, t.idx)
                assert all(w.cols[t.x + d][int(t.y) - 1] == 0 for d in (-1, 0, 1)), "seed %d: tank inside earth" % seed
                assert w.wl is None or t.y <= w.wl, "seed %d: tank under water" % seed
                assert t.grounded(w)
            assert b.x - a.x >= W * 0.5, "seed %d: tanks too close" % seed
            n += 1
    # craters remove earth, loose earth settles, tanks fall in and take damage
    m = Match(160, 88, mode="two", seed=5)
    w, t = m.world, m.tanks[0]
    before, y0 = w.solid_count(), t.y
    w.carve(t.x + 0.5, t.y + 3, 7)
    assert w.solid_count() < before - 60, "the crater removed hardly any earth"
    hp = t.hp
    for _ in range(600):
        m.tick()
    assert t.y > y0 + 4, "the tank did not drop into the crater"
    assert t.grounded(w) and t.fall0 is None, "the tank did not settle"
    assert not w.dirty, "loose earth never settled"
    for x in range(w.W):                      # no floating earth left in the touched columns
        c = w.cols[x]
        tp = w.H - len(c.lstrip(b"\0"))
        assert 0 not in c[tp:] or x not in range(t.x - 12, t.x + 13), "column %d still has a gap" % x
    # an overhang falls down: dig a tunnel under the surface
    m2 = Match(160, 88, mode="two", seed=8)
    w2 = m2.world
    x = w2.W // 2
    tp = w2.top[x]
    for xx in range(x - 3, x + 4):
        for yy in range(tp + 3, tp + 7):
            w2.cols[xx][yy] = 0
        w2.dirty.add(xx)
    for _ in range(30):
        w2.settle_step()
    assert not w2.dirty and all(0 not in w2.cols[xx][w2.top[xx]:] for xx in range(x - 3, x + 4)), "overhang hangs"
    # dirt ball adds earth, a direct hit hurts, the splitter splits
    added = w2.add_dirt(40, 20, 6)
    assert added > 60, "the dirt ball added no earth"
    m3 = Match(160, 88, mode="two", seed=9)
    tgt = m3.tanks[1]
    m3.explode(tgt.x + 0.5, tgt.y - 2, 0, 0, direct=tgt)
    assert tgt.hp == 100 - WEAPONS[0][2], "a direct hit should do full damage (hp %d)" % tgt.hp
    sh = m3.tanks[0]
    sh.weapon, sh.angle, sh.power = 2, 60, 70
    m3.turn = 0
    m3.phase = "aim"
    m3.fire()
    most = 0
    for _ in range(900):
        m3.tick()
        most = max(most, len(m3.shells))
        if m3.phase != "flight":
            break
    assert most == 3, "the splitter burst into %d" % most
    # the computer: hard hits a stationary target often, easy misses a fair share
    hard, normal, easy = aim_trial(2), aim_trial(1), aim_trial(0)
    assert hard >= 28, "hard computer hit only %d of 40" % hard
    assert easy <= 30 and easy < hard, "easy computer hit %d of 40 (hard %d)" % (easy, hard)
    assert easy >= 3, "easy computer hits almost never (%d of 40)" % easy
    # whole computer-vs-computer matches end with a winner
    results = []
    for seed, diff in ((1, 0), (2, 1), (3, 2), (4, 1), (5, 0), (6, 2)):
        mm = play_match(seed, diff)
        assert mm.winner in (0, 1) and max(mm.wins) == 2, "seed %d: no proper winner" % seed
        results.append(mm.turns)
    mm = play_match(11, 1, W=70, H=42)
    results.append(mm.turns)
    # frames: title, game, round banner, pause, end screen at the smallest and a big size
    for cols, rows in ((70, 22), (160, 45)):
        demo = TitleDemo(cols, rows)
        for i in range(40):
            demo.frame(cols, rows, 0.1, i == 39, i % 3).emit(True)
        demo.frame(cols, rows, 0.1, False, 0).emit(False)
        g = Match(*world_size(cols, rows), mode="cpu", seed=4)
        for k in ("left", "up", "tab", " "):
            g.key(k)
        for _ in range(20):
            g.update(1 / 30)
            render(g, cols, rows).emit(True)
        cv = render(g, cols, rows)
        overlay(cv, PAUSE)
        overlay(cv, HELP)
        cv.emit(True)
        g.round_winner, g.phase, g.phase_t = 0, "roundover", 1.0
        render(g, cols, rows).emit(True)
        g.phase, g.winner, g.wins = "matchover", 0, [2, 1]
        cv = render(g, cols, rows)
        render_over(cv, g, True, 3)
        cv.emit(True)
        render(g, cols + 9, rows + 3).emit(True)          # window grew mid-round
        render(g, max(70, cols - 9), rows).emit(True)    # or shrank
        cv = Canvas(cols, rows)
        preview(cv, 2, 2, 40, 24, 0.0)
        preview(cv, 2, 2, 40, 24, 0.1)
    # auto mode: the real duel at x8 for a few seconds headless, frames render, no score is ever submitted
    global submit
    real_submit, sent = submit, []
    submit = lambda *a, **k: sent.append(a)
    try:
        played = run_auto(None, 1, seconds=6, headless=(100, 30))
    finally:
        submit = real_submit
    assert not sent, "auto mode submitted a score"
    auto = AutoMode()
    for k in ("+", "+", "+", "+", "+", "+"):
        auto.key(k)
    assert auto.speed == 8.0
    am = Match(*world_size(160, 44), mode="auto", diff=2, seed=7)
    am.quiet = True
    steps = sum(auto_step(am, auto, 1 / 30, budget=None) for _ in range(30))
    assert steps >= 400, "x8 ran only %d physics steps in 30 frames (x1: 60)" % steps
    assert am.cpu == [True, True] and am.diffs == [2, 2]
    auto.key(" ")
    assert auto_step(am, auto, 1 / 30) == 0, "auto mode keeps running while paused"
    auto_frame(am, auto, 160, 45).emit(True)
    am.phase, am.winner, am.wins = "matchover", 1, [1, 2]
    auto.key("?")
    auto_frame(am, auto, 70, 22).emit(True)
    print("Self-test ok: %d lands with both tanks on solid ground; craters dig, earth settles, tanks fall; "
          "splitter bursts in 3; stationary target hit by hard %d/40, normal %d/40, easy %d/40; "
          "7 computer matches finished in %s turns; frames at 70x22 and 160x45 render; auto mode ran 6s at x8 "
          "(%d duels done, %d physics steps per 30 frames), no score submitted (%.1fs)"
          % (n, hard, normal, easy, "/".join(map(str, results)), played, steps, time.time() - t0))


def bench():
    m = Match(160, 88, mode="demo", seed=5)
    for _ in range(200):
        m.update(1 / 30)
    t = time.perf_counter()
    plan = cpu_plan(m.world, m.tanks, m.active, m.wind, 1, m.rnd)
    for _ in plan:
        pass
    print("computer aims in %.0f ms" % ((time.perf_counter() - t) * 1000))
    for cols, rows in ((160, 45), (200, 56)):
        g = Match(*world_size(cols, rows), mode="demo", seed=5)
        for _ in range(150):
            g.update(1 / 30)
        t = time.perf_counter()
        for _ in range(20):
            render(g, cols, rows).emit(True)
        print("frame %.1f ms at %dx%d" % ((time.perf_counter() - t) / 20 * 1000, cols, rows))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--bench" in sys.argv:
        bench()
    else:
        main()
