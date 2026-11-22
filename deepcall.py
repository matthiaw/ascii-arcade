#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""DEEPCALL - a submarine alone in the dark.

Dive into a deep-sea trench where nothing can be seen. Only your sonar shows the way: every ping sends out
a ring that lights up rock, wrecks and creatures for a moment before the dark swallows them again. But every
ping can be heard. Things down here hunt by sound, and something very large is listening.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
Run:        python3 deepcall.py
Self-test:  python3 deepcall.py --selftest
Benchmark:  python3 deepcall.py --bench
"""
import math
import random
import sys
import time
from collections import deque

from arcadekit import (Canvas, Terminal, clamp, load_scores, mix, overlay, shade, shared_key, submit,
                       title_screen)

GAME = "deepcall"
W, H = 320, 1700                 # world size in pixels (one pixel = one half-block)
ROCK, METAL = 1, 2
PING_R, PING_SPEED = 118.0, 150.0
FOCUS_R = 190.0
ECHO_DECAY = 2.2                 # seconds for an echo to fade to a third
METERS_PER_PX = 2.5

ZONES = [  # name, top y, sonar colour, water colour, rock memory colour
    ("Twilight Shelf", 0, (90, 230, 255), (5, 16, 28)),
    ("Midnight Gorge", 420, (150, 150, 255), (5, 7, 22)),
    ("The Abyss", 850, (255, 110, 120), (14, 4, 10)),
    ("Hadal Garden", 1280, (120, 255, 170), (2, 12, 8)),
]
AMBER = (255, 190, 90)
LAMP = (255, 240, 200)
FLARE = (255, 150, 60)
GOLD = (255, 220, 110)


def water_col(y):
    """Water colour at depth y, blended across zone borders."""
    z = zone_of(y)
    c = ZONES[z][3]
    if z + 1 < len(ZONES) and ZONES[z + 1][1] - y < 60:
        c = mix(c, ZONES[z + 1][3], 0.5 * (1 - (ZONES[z + 1][1] - y) / 60))
    if z > 0 and y - ZONES[z][1] < 60:
        c = mix(ZONES[z - 1][3], c, 0.5 + 0.5 * (y - ZONES[z][1]) / 60)
    return c


HULL = [(dx, 0) for dx in range(-4, 5)] + [(dx, dy) for dy in (-1, 1) for dx in range(-3, 4)]


def sub_hits(solid, x, y):
    """Does the sub's hull (9 pixels wide, 3 rows high) at (x, y) touch rock?
    The generator's passability check uses exactly the same shape."""
    ix, iy = int(x), int(y)
    for dx, dy in HULL:
        if solid(ix + dx, iy + dy):
            return True
    return False


def zone_of(y):
    z = 0
    for i, zn in enumerate(ZONES):
        if y >= zn[1]:
            z = i
    return z


# =============================================================================================
# The trench
# =============================================================================================
class World:
    def __init__(self, seed):
        self.seed = seed
        rnd = self.rnd = random.Random(seed)
        g = self.g = bytearray([ROCK]) * (W * H)
        self.mem = bytearray(W * H)          # explored pixels (a faint map)
        self.path = []                       # points along the main shaft
        self.chambers = []
        # open sea above the trench
        for y in range(0, 26):
            g[y * W:(y + 1) * W] = bytes(W)
        # the main shaft: a worm wandering down, with rough edges and the odd big cavern
        x, y, a = W / 2, 18.0, math.pi / 2
        phase = rnd.uniform(0, 6)
        next_branch, next_cavern = 60, rnd.uniform(200, 320)
        while y < H - 70:
            z = zone_of(y)
            r = 8 + 2 * z + 4 * math.sin(y * 0.021 + phase) + rnd.uniform(-1.5, 1.5)
            self.carve(x, y, max(6.0, r))
            self.path.append((x, y, r))
            if y > next_cavern:
                self.carve(x, y, 26 + 4 * z)
                self.chambers.append((x, y, 26 + 4 * z, "cavern"))
                next_cavern = y + rnd.uniform(240, 360)
            if y > next_branch:
                self.branch(x, y, rnd.choice((-1, 1)))
                next_branch = y + rnd.uniform(45, 95)
            a += rnd.gauss(0, 0.22) + (math.pi / 2 - a) * 0.08
            if x < 50:
                a -= 0.12
            elif x > W - 50:
                a += 0.12
            a = clamp(a, 0.35, math.pi - 0.35)
            x += math.cos(a) * 3
            y += math.sin(a) * 3
        self.carve(x, H - 60, 30)
        self.source = (x, H - 60)
        self.objects()
        self.ensure_passable()

    START = (int(W / 2), 14)

    def free_map(self, margin=0):
        """free[i] = 1 where the whole hull fits (the HULL shape, via runs of water per row).
        margin > 0 asks for that many extra pixels of room on every side."""
        g = self.g
        runs = []
        for y in range(H):
            row, r, n = g[y * W:(y + 1) * W], [0] * W, 0
            for x in range(W):
                n = n + 1 if row[x] == 0 else 0
                r[x] = n
            runs.append(r)
        free = bytearray(W * H)
        m = margin
        rows = [(dy, (4 if dy == 0 else 3) + m) for dy in range(-1 - m, 2 + m)]   # (row offset, half width)
        for y in range(2 + m, H - 2 - m):
            base = y * W
            need = [(runs[y + dy], hw) for dy, hw in rows]
            for x in range(5 + m, W - 5 - m):
                for r, hw in need:
                    if r[x + hw] < 2 * hw + 1:
                        break
                else:
                    free[base + x] = 1
        return free

    def sub_reach(self, margin=0):
        """Every position the sub's hull fits into, flood-filled from the start."""
        free = self.free_map(margin)
        seen = bytearray(W * H)
        sx, sy = self.START
        seen[sy * W + sx] = 1
        q = deque([sy * W + sx])
        while q:
            i = q.popleft()
            for j in (i + 1, i - 1, i + W, i - W):
                if free[j] and not seen[j]:
                    seen[j] = 1
                    q.append(j)
        return seen

    def reached(self, seen, x, y, rx, ry):
        return any(seen[int(y + j) * W + int(x + i)] for i in range(-rx, rx + 1) for j in range(-ry, ry + 1)
                   if 0 <= int(x + i) < W and 0 <= int(y + j) < H)

    def ensure_passable(self):
        """The trench must be finishable by the sub, not just by a pixel: if not, open a corridor down the shaft."""
        seen = self.sub_reach(margin=1)      # with room to spare: no pixel-perfect squeezes
        sx, sy = self.source
        if not self.reached(seen, sx, sy, 10, 10):
            g = self.g
            for px, py, r in self.path:
                rr = max(9.0, min(r, 11.0))
                for yy in range(int(py - rr), int(py + rr) + 1):
                    for xx in range(int(px - rr), int(px + rr) + 1):
                        if 1 <= xx < W - 1 and 1 <= yy < H - 1 and (xx - px) ** 2 + (yy - py) ** 2 <= rr * rr:
                            g[yy * W + xx] = 0
            seen = self.sub_reach(margin=1)
        self.passable = self.reached(seen, sx, sy, 10, 10)
        self.loot = [it for it in self.loot if self.reached(seen, it["x"], it["y"], 5, 3)]
        self.vents = [v for v in self.vents if self.reached(seen, v[0], v[1], 12, 12)]

    def carve(self, cx, cy, r, solid=0):
        """A rough-edged hole: one big circle and a few smaller ones around its rim."""
        rnd, g = self.rnd, self.g
        circles = [(cx, cy, r)] + [(cx + math.cos(t) * r * 0.75, cy + math.sin(t) * r * 0.75, r * rnd.uniform(0.3, 0.5))
                                   for t in (rnd.uniform(0, 6.3) for _ in range(3))]
        for ccx, ccy, rr in circles:
            r2 = rr * rr
            for yy in range(max(1, int(ccy - rr)), min(H - 1, int(ccy + rr) + 1)):
                dy2 = (yy - ccy) ** 2
                if dy2 > r2:
                    continue
                span = math.sqrt(r2 - dy2)
                x0, x1 = max(1, int(ccx - span)), min(W - 1, int(ccx + span) + 1)
                if x1 > x0:
                    g[yy * W + x0:yy * W + x1] = bytes([solid]) * (x1 - x0)
        if solid == 0 and r > 6 and cy > 60 and rnd.random() < 0.18:   # a little rock spike on the wall
            t = rnd.uniform(0, 6.3)
            ex, ey = cx + math.cos(t) * r, cy + math.sin(t) * r
            if self.solid(cx + math.cos(t) * (r + 3), cy + math.sin(t) * (r + 3)):   # only on real rock
                self.blob(ex, ey, rnd.uniform(1.5, 3.0))

    def blob(self, cx, cy, r):
        g = self.g
        for yy in range(int(cy - r), int(cy + r) + 1):
            for xx in range(int(cx - r), int(cx + r) + 1):
                if 0 < xx < W - 1 and 0 < yy < H - 1 and (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r:
                    g[yy * W + xx] = ROCK

    def branch(self, x, y, side):
        rnd = self.rnd
        a = (0.0 if side > 0 else math.pi) + rnd.uniform(-0.5, 0.5) + side * 0.3
        n = rnd.randint(12, 34)
        for _ in range(n):
            a += rnd.gauss(0, 0.25)
            x += math.cos(a) * 3
            y += math.sin(a) * 3 + 0.6
            if not (20 < x < W - 20 and 30 < y < H - 80):
                break
            self.carve(x, y, rnd.uniform(4.5, 8))
        if rnd.random() < 0.65 and 30 < x < W - 30 and y < H - 90:
            r = rnd.uniform(14, 21)
            self.carve(x, y, r)
            self.chambers.append((x, y, r, "chamber"))

    def solid(self, x, y):
        ix, iy = int(x), int(y)
        if ix < 0 or ix >= W or iy < 0 or iy >= H:
            return True
        return self.g[iy * W + ix] != 0

    def water_near(self, x, y, tries=40, spread=10):
        for _ in range(tries):
            px, py = x + self.rnd.uniform(-spread, spread), y + self.rnd.uniform(-spread, spread)
            if not self.solid(px, py) and not self.solid(px + 3, py) and not self.solid(px - 3, py):
                return px, py
        return None

    WRECK = [
        "......MMM...........",
        ".....M...M..........",
        "MMMMMMMMMMMMMMMMMMMM",
        "M..................M",
        ".M................M.",
        "..MMMMMMM....MMMMM..",
    ]

    def objects(self):
        rnd = self.rnd
        self.wrecks, self.loot, self.vents, self.creatures = [], [], [], []
        # wrecks with salvage in the chambers and caverns
        for cx, cy, r, kind in self.chambers:
            on_shaft = any(abs(px - cx) < r + 14 and abs(py - cy) < r + 14 for px, py, _ in self.path[::4])
            if kind == "chamber" and not on_shaft and rnd.random() < 0.55:
                ox, oy = int(cx - 10), int(cy + r * 0.25)
                for j, row in enumerate(self.WRECK):
                    for i, ch in enumerate(row):
                        if ch == "M" and not self.solid(ox + i, oy + j):
                            self.g[(oy + j) * W + ox + i] = METAL
                self.wrecks.append((ox, oy))
                for k in range(rnd.randint(1, 3)):
                    self.add_loot(ox + 3 + k * 5, oy + 3)
            for _ in range(rnd.randint(1, 2)):
                p = self.water_near(cx, cy, spread=r * 0.7)
                if p:
                    self.add_loot(*p)
        # air vents along the shaft, on the nearest floor
        for i in range(30, len(self.path), 48):
            x, y, r = self.path[i]
            for dx, dy in ((0, 1), (0.6, 0.8), (-0.6, 0.8), (1, 0.2), (-1, 0.2)):
                hit = next((d for d in range(1, 80) if self.solid(x + dx * d, y + dy * d)), None)
                if hit:
                    self.vents.append([x + dx * (hit - 1), y + dy * (hit - 1)])
                    break
        # creatures, more and nastier the deeper it gets
        for x, y, r in self.path[12::9]:
            z = zone_of(y)
            roll = rnd.random()
            if roll < 0.20:
                kind = "jelly"
            elif roll < 0.20 + 0.03 + 0.035 * z:
                kind = "lurker"
            else:
                continue
            p = self.water_near(x, y, spread=r)
            if p:
                self.creatures.append(Creature(kind, p[0], p[1], rnd))
        for y0 in (ZONES[2][1] + 150, ZONES[3][1] + 160):
            near = min(self.path, key=lambda q: abs(q[1] - y0))
            self.creatures.append(Creature("leviathan", near[0], near[1], rnd))
        # a few loose finds in the shaft itself
        for x, y, r in self.path[20::40]:
            p = self.water_near(x, y, spread=r)
            if p:
                self.add_loot(*p)

    def add_loot(self, x, y):
        rnd = self.rnd
        roll = rnd.random()
        kind = "salvage" if roll < 0.68 else "oxygen" if roll < 0.83 else "battery" if roll < 0.94 else "flares"
        value = int(40 + y * 0.18 + rnd.uniform(0, 30)) if kind == "salvage" else 0
        self.loot.append(dict(x=x, y=y, kind=kind, value=value, seen=-99.0))


class Creature:
    def __init__(self, kind, x, y, rnd):
        self.kind, self.x, self.y = kind, x, y
        self.hx, self.hy = x, y          # home
        self.vx = self.vy = 0.0
        self.ph = rnd.uniform(0, 6.3)
        self.seen = -99.0                 # when sonar or light last touched it
        self.target = None
        self.cool = 0.0                   # time until it may bite again
        self.flee = 0.0
        self.state = "idle"
        if kind == "leviathan":
            self.body = [(x, y)] * 18


# =============================================================================================
# The dive
# =============================================================================================
class Ping:
    def __init__(self, world, x, y, t, R, cone=None, color=(90, 230, 255)):
        self.x, self.y, self.t0, self.R, self.color = x, y, t, R, color
        self.r = 0.0
        self.cone = cone
        span = cone[1] * 2 if cone else 2 * math.pi
        a0 = cone[0] - cone[1] if cone else 0.0
        n = max(60, int(span * R * 0.95))
        g = world.g
        self.rays = []
        self.angles = (a0, span, n)
        dists = []
        for k in range(n):
            a = a0 + span * (k + 0.5) / n
            dx, dy = math.cos(a), math.sin(a)
            px, py = x, y
            d = 0.0
            hit = None
            while d < R:
                d += 1.0
                px += dx
                py += dy
                ix, iy = int(px), int(py)
                if ix < 0 or ix >= W or iy < 0 or iy >= H:
                    break
                m = g[iy * W + ix]
                if m:
                    hit = (ix, iy, m)
                    break
            dists.append(d if hit else R)
            self.rays.append((d if hit else R + 1, dx, dy, hit))
        self.dists = dists
        self.order = sorted(range(n), key=lambda i: self.rays[i][0])
        self.next = 0

    def clear_to(self, x, y):
        """Is the point (x, y) in line of sight from the ping's origin, within its cone?"""
        a = math.atan2(y - self.y, x - self.x)
        a0, span, n = self.angles
        rel = (a - a0) % (2 * math.pi)
        if rel >= span:
            return False
        k = int(rel / span * n)
        reach = max(self.dists[(k + j) % n] if not self.cone else self.dists[min(n - 1, max(0, k + j))]
                    for j in (-3, -2, -1, 0, 1, 2, 3))   # a few neighbouring rays: creatures are not points
        return math.hypot(x - self.x, y - self.y) <= reach + 2


class Dive:
    def __init__(self, seed=None):
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.w = World(self.seed)
        self.x, self.y = W / 2, 14.0
        self.vx = self.vy = 0.0
        self.face = 1
        self.t = 0.0
        self.hull, self.oxygen, self.power = 100.0, 100.0, 100.0
        self.flares = 3
        self.salvage = 0
        self.lamp = False
        self.noise = 0.0                  # 0..1, what the deep can hear
        self.loud = (self.x, self.y)      # where the last loud sound came from
        self.pings, self.echo, self.flare_list, self.noises, self.bubbles = [], {}, [], [], []
        self.msgs = []
        self.hurt = 0.0
        self.max_depth = 0.0
        self.zone = 0
        self.over = self.won = False
        self.paused = self.help = False
        self.cause = ""
        self.say("Dive! Space pings the sonar, F a focused ping, L the lamp, E a flare.", 6)

    # --- helpers ---------------------------------------------------------------------------------
    def say(self, s, ttl=3.0):
        self.msgs.append([s, self.t + ttl])
        self.msgs = self.msgs[-3:]

    def make_noise(self, x, y, radius, meter):
        self.noises.append((x, y, radius, self.t))
        self.noise = min(1.0, self.noise + meter)
        if meter > 0:
            self.loud = (x, y)

    def depth_m(self):
        return max(0.0, self.y - 26) * METERS_PER_PX

    @property
    def score(self):
        return self.salvage + int(self.max_depth / 2) + (5000 if self.won else 0)

    # --- actions ------------------------------------------------------------------------------------
    def key(self, k):
        if self.over:
            return
        thrust = {"left": (-1, 0), "a": (-1, 0), "right": (1, 0), "d": (1, 0),
                  "up": (0, -1), "w": (0, -1), "down": (0, 1), "s": (0, 1)}
        if k in thrust:
            dx, dy = thrust[k]
            self.vx += dx * 9.0
            self.vy += dy * 7.0
            if dx:
                self.face = dx
        elif k == " ":
            self.ping(False)
        elif k == "f":
            self.ping(True)
        elif k == "l":
            self.lamp = not self.lamp
            self.say("Lamp on - it shows the way, and you to them." if self.lamp else "Lamp off.", 2)
        elif k == "e":
            if self.flares > 0:
                self.flares -= 1
                self.flare_list.append([self.x - self.face * 4, self.y + 2, -self.face * 6.0, -4.0, self.t + 14])
                self.say("Flare away - it draws them to itself.", 2)
            else:
                self.say("No flares left.", 2)

    def ping(self, focused):
        cost = 6 if focused else 10
        if self.power < cost:
            self.say("Not enough power for a ping.", 1.5)
            return
        self.power -= cost
        col = ZONES[self.zone][2]
        if focused:
            a = math.atan2(self.vy * 0.4, self.face * 1.0)
            self.pings.append(Ping(self.w, self.x, self.y, self.t, FOCUS_R, (a, 0.42), col))
            self.make_noise(self.x, self.y, 110, 0.15)
        else:
            self.pings.append(Ping(self.w, self.x, self.y, self.t, PING_R, None, col))
            self.make_noise(self.x, self.y, 150, 0.27)

    # --- light: mark what a ray of light reaches ---------------------------------------------------
    def light(self, x, y, a0, span, R, n, strength, color):
        g, echo, t = self.w.g, self.echo, self.t
        mem = self.w.mem
        for k in range(n):
            a = a0 + span * (k + 0.5) / n
            dx, dy = math.cos(a), math.sin(a)
            px, py = x, y
            d = 0.0
            while d < R:
                d += 1.0
                px += dx
                py += dy
                ix, iy = int(px), int(py)
                if ix < 0 or ix >= W or iy < 0 or iy >= H:
                    break
                i = iy * W + ix
                if g[i]:
                    s = strength * (1 - d / R * 0.6)
                    old = echo.get(i)
                    if not old or old[1] * math.exp(-(t - old[0]) / ECHO_DECAY) < s:
                        echo[i] = (t, s, AMBER if g[i] == METAL else color)
                    mem[i] = 1
                    break
        for c in self.w.creatures:
            dx, dy = c.x - x, c.y - y
            d = math.hypot(dx, dy)
            if d < R:
                rel = (math.atan2(dy, dx) - a0) % (2 * math.pi)
                if rel < span:
                    c.seen = t
        for it in self.w.loot:
            if math.hypot(it["x"] - x, it["y"] - y) < R:
                it["seen"] = t

    # --- time -------------------------------------------------------------------------------------
    def update(self, dt):
        if self.over or self.paused:
            return
        self.t += dt
        w = self.w
        # the sub: sluggish, as a submarine should be - key repeat gaps do not matter
        drag = 0.55 ** dt
        self.vx *= drag
        self.vy *= drag
        sp = math.hypot(self.vx, self.vy)
        if sp > 34:
            self.vx, self.vy = self.vx / sp * 34, self.vy / sp * 34
        self.move(self.vx * dt, self.vy * dt)
        # depth, zones
        self.max_depth = max(self.max_depth, self.depth_m())
        z = zone_of(self.y)
        if z != self.zone:
            if z > self.zone:
                self.say("Entering %s - %d m" % (ZONES[z][0], self.depth_m()), 4)
            self.zone = z
        # oxygen, power, noise
        self.oxygen -= dt * 0.42
        self.power = min(100.0, self.power + dt * (3.0 - (1.6 if self.lamp else 0)))
        if self.lamp:
            if self.power <= 0:
                self.lamp = False
                self.say("Power out - the lamp dies.", 2)
            self.make_noise(self.x, self.y, 45, dt * 0.03)
        if sp > 22:
            self.make_noise(self.x, self.y, 30, 0)
        self.noise = max(0.0, self.noise - dt * 0.07)
        self.noises = [n for n in self.noises if self.t - n[3] < 0.6]
        for v in w.vents:
            if math.hypot(v[0] - self.x, v[1] - self.y) < 14:
                if self.oxygen < 99:
                    self.oxygen = min(100.0, self.oxygen + dt * 22)
                    if int(self.t * 2) % 6 == 0:
                        self.say("Air vent - filling the tanks.", 1)
            if random.random() < dt * 6:
                self.bubbles.append([v[0] + random.uniform(-2, 2), v[1], random.uniform(2.5, 5.0)])
        for b in self.bubbles:
            b[1] -= b[2] * dt * 6
            b[0] += math.sin(b[1] * 0.3) * dt * 2
        self.bubbles = [b for b in self.bubbles if b[1] > 0 and not w.solid(b[0], b[1])][-400:]
        # sonar rings travel outward and light up what they meet
        keep = []
        for p in self.pings:
            r_new = (self.t - p.t0) * PING_SPEED
            rays, order = p.rays, p.order
            while p.next < len(order) and rays[order[p.next]][0] <= r_new:
                d, dx, dy, hit = rays[order[p.next]]
                p.next += 1
                if hit is None:
                    continue
                ix, iy, m = hit
                s = 1.0 - d / p.R * 0.55
                col = AMBER if m == METAL else p.color
                for depth in range(3):   # the echo has some thickness into the rock
                    jx, jy = int(ix + dx * depth), int(iy + dy * depth)
                    if 0 <= jx < W and 0 <= jy < H and w.g[jy * W + jx]:
                        i = jy * W + jx
                        self.echo[i] = (self.t, s * (1 - depth * 0.3), col)
                        w.mem[i] = 1
            for c in w.creatures:
                for bx, by in (c.body[::3] if c.kind == "leviathan" else ((c.x, c.y),)):
                    d = math.hypot(bx - p.x, by - p.y)
                    if p.r < d <= r_new and p.clear_to(bx, by):
                        c.seen = self.t
                        break
            for it in w.loot:
                d = math.hypot(it["x"] - p.x, it["y"] - p.y)
                if p.r < d <= r_new and p.clear_to(it["x"], it["y"]):
                    it["seen"] = self.t
            p.r = r_new
            if r_new < p.R + 4:
                keep.append(p)
        self.pings = keep
        if self.lamp:
            self.light(self.x + self.face * 5, self.y, (0 if self.face > 0 else math.pi) - 0.5, 1.0, 30, 30, 0.55, LAMP)
        fl = []
        for f in self.flare_list:
            f[2] *= 0.97
            f[3] = f[3] * 0.97 + dt * 3
            if not w.solid(f[0] + f[2] * dt, f[1] + f[3] * dt):
                f[0] += f[2] * dt
                f[1] += f[3] * dt
            if self.t < f[4]:
                self.light(f[0], f[1], 0, 2 * math.pi, 34, 40, 0.6, FLARE)
                self.noises.append((f[0], f[1], 95, self.t))
                fl.append(f)
        self.flare_list = fl
        self.update_creatures(dt)
        # finds
        for it in list(w.loot):
            if abs(it["x"] - self.x) < 6 and abs(it["y"] - self.y) < 4:
                w.loot.remove(it)
                k = it["kind"]
                if k == "salvage":
                    self.salvage += it["value"]
                    self.say("Salvage: +%d" % it["value"], 2)
                elif k == "oxygen":
                    self.oxygen = min(100.0, self.oxygen + 40)
                    self.say("Oxygen tank: +40% air", 2)
                elif k == "battery":
                    self.power = 100.0
                    self.say("Battery: power full", 2)
                else:
                    self.flares += 2
                    self.say("Flare pack: +2 flares", 2)
        sx, sy = w.source
        if math.hypot(sx - self.x, sy - self.y) < 12:
            self.won = self.over = True
            self.cause = "You reached the Source at %d m." % self.depth_m()
        if self.hull <= 0:
            self.hull = 0
            self.over = True
            self.cause = self.cause or "The hull gave way at %d m." % self.depth_m()
        if self.oxygen <= 0:
            self.oxygen = 0
            self.over = True
            self.cause = "The air ran out at %d m." % self.depth_m()
        self.hurt = max(0.0, self.hurt - dt)
        # forget faded echoes
        if int(self.t * 4) != int((self.t - dt) * 4):
            t = self.t
            dead = [i for i, (t0, s, _) in self.echo.items() if s * math.exp(-(t - t0) / ECHO_DECAY) < 0.035]
            for i in dead:
                del self.echo[i]
        self.msgs = [m for m in self.msgs if m[1] > self.t]

    def move(self, mx, my):
        """Move with wall sliding: along a slope or over a small bump the hull glides instead of sticking."""
        x, y = self.x, self.y
        if mx:
            if not self.hits(x + mx, y):
                x += mx
            else:
                slid = False
                vs = 1 if self.vy > 0 else -1
                steps = (0.7, 1.4, 2.1) if abs(self.vy) > 2 else (0.7, -0.7, 1.4, -1.4, 2.1, -2.1)
                for oy in (k * vs for k in steps):     # step around the bump - never against the climb / dive
                    if not self.hits(x + mx, y + oy):
                        x, y, slid = x + mx, y + oy, True
                        break
                if not slid:
                    self.bump(abs(self.vx))
                    self.vx *= -0.3
                else:
                    self.vx *= 0.9
        if my:
            if not self.hits(x, y + my):
                y += my
            else:
                slid = False
                side = 1 if self.vx > 0 else -1
                steps = (0.7, -0.7, 1.4, -1.4, 2.1, -2.1, 2.8, -2.8)
                for ox in (k * side for k in steps):   # slide along the slope
                    if not self.hits(x + ox, y + my):
                        x, y, slid = x + ox, y + my, True
                        break
                if not slid:
                    self.bump(abs(self.vy))
                    self.vy *= -0.3
                else:
                    self.vy *= 0.9
        self.x, self.y = x, max(4.0, y)

    def hits(self, x, y):
        return sub_hits(self.w.solid, x, y)

    def bump(self, speed):
        if speed > 19:
            dmg = (speed - 19) * 0.7
            self.hull -= dmg
            self.hurt = 0.3
            self.make_noise(self.x, self.y, 70, 0.12)
            self.say("Hull impact! (-%d)" % dmg, 1.5)
            self.cause = "You crashed into the rock at %d m." % self.depth_m()

    def damage(self, n, cause):
        self.hull -= n
        self.hurt = 0.5
        self.cause = cause

    def update_creatures(self, dt):
        w = self.w
        for c in w.creatures:
            c.ph += dt
            c.cool = max(0.0, c.cool - dt)
            c.flee = max(0.0, c.flee - dt)
            d = math.hypot(c.x - self.x, c.y - self.y)
            if c.kind == "jelly":
                nx = c.hx + math.sin(c.ph * 0.4) * 10
                ny = c.hy + math.sin(c.ph * 0.25 + 1) * 6
                if not w.solid(nx, ny):
                    c.x, c.y = nx, ny
                if d < 5 and c.cool <= 0:
                    c.cool = 1.5
                    self.damage(4, "A jellyfish stung you to death at %d m." % self.depth_m())
                    self.say("Jellyfish sting!", 1.5)
                    dl = d or 1   # it pushes you off
                    self.vx += (self.x - c.x) / dl * 16
                    self.vy += (self.y - c.y) / dl * 16
                continue
            if c.kind == "lurker":
                for nx_, ny_, rad, _ in self.noises:     # it swims towards anything it hears
                    if math.hypot(nx_ - c.x, ny_ - c.y) < rad:
                        c.target = (nx_, ny_)
                if c.flee > 0:
                    tx, ty = c.x + (c.x - self.x), c.y + (c.y - self.y)
                    speed = 20
                elif d < 22 and (self.lamp or self.t - c.seen < 1.0):
                    tx, ty, speed = self.x, self.y, 17      # slower than the sub: you can get away
                elif c.target:
                    tx, ty, speed = c.target[0], c.target[1], 13
                    if math.hypot(tx - c.x, ty - c.y) < 4:
                        c.target = None
                else:
                    tx = c.hx + math.sin(c.ph * 0.3) * 18
                    ty = c.hy + math.cos(c.ph * 0.23) * 10
                    speed = 7
                self.swim(c, tx, ty, speed, dt)
                if d < 5 and c.cool <= 0 and c.flee <= 0:
                    c.cool, c.flee = 4.0, 7.0
                    c.target = None
                    self.damage(9, "A lurker tore the hull open at %d m." % self.depth_m())
                    self.say("Something bit the hull! (-9)", 2)
                continue
            # the leviathan: slow, huge, it follows the loudest sound when the deep is loud enough
            if c.flee > 0:
                tx, ty, speed = c.hx, c.hy, 10
            elif self.noise > 0.55 and abs(self.loud[1] - c.hy) < 260:
                if c.state != "hunt":
                    c.state = "hunt"
                    self.say("Something enormous has heard you...", 4)
                tx, ty, speed = self.loud[0], self.loud[1], 15
            else:
                if c.state == "hunt" and self.noise < 0.3:
                    c.state = "idle"
                    self.say("The deep goes quiet again.", 3)
                tx = c.hx + math.sin(c.ph * 0.07) * 50
                ty = c.hy + math.sin(c.ph * 0.05 + 2) * 30
                speed = 6
            dx, dy = tx - c.x, ty - c.y
            dl = math.hypot(dx, dy) or 1
            k = speed * dt * (0.55 if w.solid(c.x, c.y) else 1.0)   # it pushes through rock, slowly
            c.x += dx / dl * min(k, dl)
            c.y += dy / dl * min(k, dl)
            body = c.body
            body[0] = (c.x, c.y)
            for i in range(1, len(body)):
                px, py = body[i - 1]
                bx, by = body[i]
                gx, gy = bx - px, by - py
                gl = math.hypot(gx, gy) or 1
                if gl > 3.2:
                    body[i] = (px + gx / gl * 3.2, py + gy / gl * 3.2)
            if c.cool <= 0 and c.flee <= 0 and any(math.hypot(bx - self.x, by - self.y) < 8 - i * 0.2
                                                    for i, (bx, by) in enumerate(body[:8])):
                c.cool, c.flee = 4.0, 16.0
                c.state = "idle"
                self.noise = 0.0
                self.damage(42, "The leviathan crushed you at %d m." % self.depth_m())
                self.vx += (self.x - c.x) * 2
                self.vy += (self.y - c.y) * 2
                self.say("THE LEVIATHAN STRUCK! (-42)", 3)

    def swim(self, c, tx, ty, speed, dt):
        w = self.w
        dx, dy = tx - c.x, ty - c.y
        dl = math.hypot(dx, dy)
        if dl < 0.5:
            return
        step = min(dl, speed * dt)
        for turn in (0, 0.7, -0.7, 1.5, -1.5):
            a = math.atan2(dy, dx) + turn
            nx, ny = c.x + math.cos(a) * step, c.y + math.sin(a) * step
            if not w.solid(nx, ny):
                c.x, c.y = nx, ny
                return


# =============================================================================================
# Drawing
# =============================================================================================
SUB = [
    "....hh......",
    "...hHHh.....",
    ".hhhhhhhhh..",
    "hhwwhhhhhhhp",
    ".hhhhhhhhh..",
]
SUB_PAL = {"h": (210, 180, 70), "H": (240, 220, 120), "w": (120, 230, 255), "p": (150, 150, 160)}


def render(d, cols, rows, title_mode=False):
    cv = Canvas(cols, rows)
    PW = cols
    prow = rows - (0 if title_mode else 1)
    PH = prow * 2
    w = d.w
    camx = int(d.x - PW / 2)
    camy = int(d.y - PH * 0.42)
    px = cv.px
    t = d.t
    # water, darker with depth
    zrow = []
    for y in range(PH):
        wy = camy + y
        z = zone_of(max(0, wy))
        base = water_col(max(0, wy))
        k = 1.0 + max(0.0, (60 - wy) / 60) * 2.2 if wy < 60 else 1.0
        if wy < 0:
            base, k = (24, 60, 90), 1.0
        c = shade(base, k)
        px[y] = [c] * PW
        zrow.append(z)
    # marine snow
    rnd = random.Random(3)
    for i in range(70):
        sx = int((rnd.uniform(0, 400) - camx * 0.6) % PW)
        sy = int((rnd.uniform(0, 400) - camy * 0.6 + t * rnd.uniform(1, 3)) % PH)
        px[sy][sx] = mix(px[sy][sx], (120, 140, 150), 0.25)
    # the faint map of explored rock, and daylight near the surface
    g, mem = w.g, w.mem
    memcols = [mix(z[3], z[2], 0.16) for z in ZONES]
    for y in range(PH):
        wy = camy + y
        if not 0 <= wy < H:
            continue
        row = px[y]
        base = wy * W
        mc = memcols[zrow[y]]
        amb = (1 - wy / 110) if wy < 110 else 0.0
        if amb > 0:
            rock = mix(ZONES[0][3], (70, 120, 140), amb * 0.8)
        x0, x1 = max(0, -camx), min(PW, W - camx)
        for x in range(x0, x1):
            i = base + camx + x
            if g[i]:
                if amb > 0:
                    row[x] = rock
                elif mem[i]:
                    row[x] = mc
        if camx < 0 or camx + PW > W:   # outside the trench: solid rock
            for x in range(PW):
                if not 0 <= camx + x < W:
                    row[x] = (8, 8, 12) if amb <= 0 else rock
    # echoes
    for i, (t0, s, col) in d.echo.items():
        b = s * math.exp(-(t - t0) / ECHO_DECAY)
        if b < 0.035:
            continue
        x, y = i % W - camx, i // W - camy
        if 0 <= x < PW and 0 <= y < PH:
            if t - t0 < 0.12:
                col = mix(col, (255, 255, 255), 0.6)
            px[y][x] = mix(px[y][x], col, min(1.0, b))
    # sonar rings in the open water
    for p in d.pings:
        fade = max(0.0, 1 - p.r / p.R)
        for dist, dx, dy, hit in p.rays[::2]:
            if dist > p.r:
                x, y = int(p.x + dx * p.r) - camx, int(p.y + dy * p.r) - camy
                if 0 <= x < PW and 0 <= y < PH:
                    px[y][x] = mix(px[y][x], p.color, 0.5 * fade)
    # vents and their bubbles
    for vx, vy in w.vents:
        x, y = int(vx) - camx, int(vy) - camy
        if 0 <= x < PW and 0 <= y < PH:
            px[y][x] = mix(px[y][x], (160, 200, 220), 0.5)
    for bx, by, _ in d.bubbles:
        x, y = int(bx) - camx, int(by) - camy
        if 0 <= x < PW and 0 <= y < PH and math.hypot(bx - d.x, by - d.y) < 90:
            px[y][x] = mix(px[y][x], (190, 230, 255), 0.55)
    # finds glint where light has touched them
    for it in w.loot:
        x, y = int(it["x"]) - camx, int(it["y"]) - camy
        if not (0 <= x < PW - 2 and 0 <= y < PH - 1):
            continue
        age = t - it["seen"]
        near = math.hypot(it["x"] - d.x, it["y"] - d.y) < 16
        if age < 4 or near:
            b = max(0.3 if near else 0.0, 1 - age / 4)
            col = {"salvage": GOLD, "oxygen": (120, 220, 255), "battery": (140, 255, 140), "flares": FLARE}[it["kind"]]
            glint = 1.0 if int(t * 3 + it["x"]) % 3 == 0 else 0.7
            for ddx, ddy in ((0, 0), (1, 0), (0, 1), (1, 1)):
                px[y + ddy][x + ddx] = mix(px[y + ddy][x + ddx], col, b * glint)
    # the Source at the bottom: a pale glow you can sense from far away
    sx, sy = w.source
    ds = math.hypot(sx - d.x, sy - d.y)
    if ds < 220:
        R = 9
        for yy in range(-R, R + 1):
            for xx in range(-R, R + 1):
                r = math.hypot(xx, yy)
                if r <= R:
                    x, y = int(sx) + xx - camx, int(sy) + yy - camy
                    if 0 <= x < PW and 0 <= y < PH:
                        k = (1 - r / R) ** 1.5 * (0.6 + 0.4 * math.sin(t * 2)) * (1 - ds / 220)
                        px[y][x] = mix(px[y][x], (230, 255, 240), k)
    # creatures
    for c in w.creatures:
        x, y = int(c.x) - camx, int(c.y) - camy
        seen = max(0.0, 1 - (t - c.seen) / 2.5)
        dsub = math.hypot(c.x - d.x, c.y - d.y)
        if c.kind == "jelly":
            if not (-4 <= x < PW + 4 and -4 <= y < PH + 6):
                continue
            pulse = 0.45 + 0.35 * math.sin(c.ph * 2.3)
            col = (255, 120, 210)
            for ddx, ddy, k in ((-1, 0, 0.8), (0, 0, 1), (1, 0, 0.8), (-1, -1, 0.5), (0, -1, 0.7), (1, -1, 0.5),
                                (-1, 1, 0.4), (1, 2, 0.3), (0, 2, 0.35), (-1, 3, 0.2), (1, 3, 0.2)):
                xx, yy = x + ddx, y + ddy
                if 0 <= xx < PW and 0 <= yy < PH:
                    px[yy][xx] = mix(px[yy][xx], col, min(1.0, k * max(pulse, seen)))
        elif c.kind == "lurker":
            if not (-6 <= x < PW + 6 and -4 <= y < PH + 4):
                continue
            col = ZONES[zone_of(c.y)][2]
            if seen > 0:
                for ddx in range(-4, 5):
                    for ddy in ((0,) if abs(ddx) > 2 else (-1, 0, 1)):
                        xx, yy = x + ddx, y + ddy
                        if 0 <= xx < PW and 0 <= yy < PH:
                            px[yy][xx] = mix(px[yy][xx], col, seen * (0.9 - abs(ddx) * 0.08))
            # the lure light, blinking - a light in the dark is rarely a friend
            lx, ly = x + (3 if c.vx >= 0 else -3), y - 3
            if 0 <= lx < PW and 0 <= ly < PH and int(c.ph * 1.7) % 4 != 0:
                px[ly][lx] = mix(px[ly][lx], (255, 250, 170), 0.85)
            if dsub < 40:   # eyes, when you get close
                for ex in (x - 3, x - 2) if c.x > d.x else (x + 2, x + 3):
                    if 0 <= ex < PW and 0 <= y < PH:
                        px[y][ex] = mix(px[y][ex], (255, 60, 40), 0.7 * (1 - dsub / 40))
        else:
            for i, (bx, by) in enumerate(c.body):
                r = max(1.5, 6 - i * 0.28)
                cx, cy = int(bx) - camx, int(by) - camy
                if not (-8 <= cx < PW + 8 and -8 <= cy < PH + 8) or seen <= 0:
                    continue
                col = mix(ZONES[zone_of(by)][2], (225, 220, 200), 0.6)   # pale, not like the rock
                for yy in range(int(-r), int(r) + 1):
                    for xx in range(int(-r), int(r) + 1):
                        if xx * xx + yy * yy <= r * r:
                            X, Y = cx + xx, cy + yy
                            if 0 <= X < PW and 0 <= Y < PH:
                                px[Y][X] = mix(px[Y][X], col, seen * 0.85)
            if dsub < 90 or c.state == "hunt":   # two pale eyes in the dark
                hx, hy = int(c.x) - camx, int(c.y) - camy - 2
                k = 0.9 if c.state == "hunt" else 0.5 * (1 - dsub / 90)
                for ex in (hx - 2, hx + 2):
                    if 0 <= ex < PW and 0 <= hy < PH:
                        px[hy][ex] = mix(px[hy][ex], (255, 230, 120), k)
    # flares
    for f in d.flare_list:
        x, y = int(f[0]) - camx, int(f[1]) - camy
        for xx, yy, k in ((0, 0, 1.0), (1, 0, 0.6), (-1, 0, 0.6), (0, 1, 0.6), (0, -1, 0.6)):
            X, Y = x + xx, y + yy
            if 0 <= X < PW and 0 <= Y < PH:
                px[Y][X] = mix(px[Y][X], (255, 230, 160) if k == 1 else FLARE, k)
    # the sub, with a soft lamp cone
    if not title_mode:
        x0, y0 = int(d.x) - camx, int(d.y) - camy
        if d.lamp:
            for k in range(1, 30):
                half = int(k * 0.5)
                for yy in range(-half, half + 1):
                    X, Y = x0 + d.face * (5 + k), y0 + yy
                    if 0 <= X < PW and 0 <= Y < PH:
                        px[Y][X] = mix(px[Y][X], LAMP, 0.10 * (1 - k / 30))
        for j, line in enumerate(SUB):
            for i, ch in enumerate(line):
                if ch == ".":
                    continue
                c = SUB_PAL[ch]
                if ch == "p":
                    c = (190, 190, 200) if int(t * 12) % 2 else (90, 90, 100)
                ii = i if d.face > 0 else len(line) - 1 - i
                X, Y = x0 - 6 + ii, y0 - 3 + j
                if 0 <= X < PW and 0 <= Y < PH:
                    px[Y][X] = c
        blink = int(t * 2) % 2
        X, Y = x0 + (5 if d.face > 0 else -6), y0 - 1
        if blink and 0 <= X < PW and 0 <= Y < PH:
            px[Y][X] = (80, 255, 120) if d.face > 0 else (255, 70, 70)
        # damage and low air pulse red at the edges
        red = d.hurt * 2 + (max(0.0, 0.3 - d.oxygen / 100) * (0.5 + 0.5 * math.sin(t * 6)) * 2)
        if red > 0:
            for y in range(PH):
                row = px[y]
                for x in list(range(4)) + list(range(PW - 4, PW)):
                    e = (4 - x) / 4 if x < 4 else (x - (PW - 5)) / 4
                    row[x] = mix(row[x], (220, 30, 30), min(0.8, red * e))
        depth_gauge(cv, d, PW, PH)
        hud(cv, d, cols, rows)
    return cv


def depth_gauge(cv, d, PW, PH):
    """Where am I? Zones from the surface down to the Source, with the sub's depth marked."""
    x = PW - 3
    top, bot = 4, PH - 4
    span = bot - top
    for y in range(top, bot):
        wy = (y - top) / span * H
        z = zone_of(wy)
        c = mix(ZONES[z][3], ZONES[z][2], 0.35)
        cv.px[y][x] = c
        cv.px[y][x + 1] = c
    sy = top + int(clamp(d.y / H, 0, 1) * span)
    for yy in (sy - 1, sy, sy + 1):
        for xx in (x - 2, x - 1, x, x + 1):
            if 0 <= yy < PH:
                cv.px[yy][xx] = (255, 220, 110)
    ty = top + int(d.w.source[1] / H * span)
    for xx in (x - 1, x, x + 1, x + 2):
        if 0 <= xx < PW:
            cv.px[ty][xx] = (230, 255, 240)


def bar(v, n=8):
    f = int(round(clamp(v, 0, 100) / 100 * n))
    return "█" * f + "░" * (n - f)


def hud(cv, d, cols, rows):
    z = ZONES[d.zone]
    r = rows - 1
    segs = [(" DEEPCALL ", (10, 10, 16), z[2]),
            ("  %5d m " % d.depth_m(), (230, 230, 240), None),
            ("  HULL %s" % bar(d.hull), (255, 120, 100) if d.hull < 30 else (220, 220, 230), None),
            ("  AIR %s" % bar(d.oxygen), (255, 120, 100) if d.oxygen < 25 else (140, 220, 255), None),
            ("  PWR %s" % bar(d.power), (240, 220, 120), None),
            ("  FLARES %d" % d.flares, FLARE, None),
            ("  NOISE %s" % bar(d.noise * 100, 6), (255, 80, 80) if d.noise > 0.55 else (170, 170, 190), None),
            ("  $%d " % d.salvage, GOLD, None)]
    x = 0
    for s, fg, bg in segs:
        cv.put(x, r, s, fg, bg or (10, 12, 20))
        x += len(s)
    if x < cols:
        cv.put(x, r, " " * (cols - x), (10, 10, 16), (10, 12, 20))
    right = " %s   ? help  Esc menu " % z[0]
    if x + len(right) <= cols:
        cv.put(cols - len(right), r, right, (130, 136, 170), (10, 12, 20))
    for i, (s, _) in enumerate(d.msgs[-2:]):
        cv.center(1 + i, " %s " % s, (230, 236, 240), (12, 16, 30))


HELP = [
    "DEEPCALL - keys",
    "",
    "Arrows / WASD            steer the sub (it drifts - plan ahead)",
    "Space                    sonar ping all around (loud)",
    "F                        focused ping ahead: further, quieter",
    "L                        lamp on / off (drains power, can be seen)",
    "E                        drop a flare - it lures hunters to itself",
    "",
    "Find air vents (rising bubbles), salvage and the Source at the bottom.",
    "Keep the NOISE bar low: loud dives wake what lives down there.",
    "The gauge on the right edge shows your depth and the Source at the bottom.",
    "",
    "Esc / P                  pause menu (Q there: quit)",
    "?                        this help",
]
PAUSE = ["P A U S E D", "", "Esc / P / Enter   continue", "?                 help", "Q                 quit to the menu"]


def render_end(d, cv, record):
    lines = ["THE SOURCE" if d.won else "LOST IN THE DEEP", "", d.cause, "",
             "deepest  %d m" % d.max_depth, "salvage  $%d" % d.salvage, "score    %d" % d.score]
    if record:
        lines += ["", "** NEW RECORD **"]
    lines += ["", "Enter: dive again   Esc / Q: menu"]
    w = max(len(l) for l in lines) + 4
    cv.box(max(0, (cv.cols - w) // 2), max(0, cv.rows // 2 - len(lines) // 2 - 1), [l.center(w - 4) for l in lines],
           (240, 240, 246), (16, 20, 36) if d.won else (40, 14, 20))


class TitleDemo:
    """A quiet cave behind the title screen, pinged every few seconds."""

    def __init__(self):
        self.d = Dive(seed=7)
        p = self.d.w.path[60]
        self.d.x, self.d.y = p[0], p[1]
        self.d.msgs = []
        self.last = -9.0

    def frame(self, cols, rows, dt, help_):
        d = self.d
        if d.t - self.last > 3.0:
            self.last = d.t
            d.power = 100
            d.ping(False)
        # let rings, echoes and creatures move on, but keep the (invisible) sub safe where it is
        saved = (d.x, d.y, d.oxygen, d.hull)
        d.update(dt)
        d.x, d.y, d.oxygen, d.hull = saved
        d.vx = d.vy = d.noise = 0.0
        d.over = False
        d.msgs = []
        cv = render(d, cols, rows, title_mode=True)
        best = load_scores().get(GAME, {}).get("dive")
        title_screen(cv, "DEEPCALL", "a submarine alone in the dark", ["Dive"], 0,
                     "best score: %d" % best if best is not None else None,
                     extra=["", "Every ping lights the way -", "and tells the deep where you are."],
                     keys="Enter dive   ? help   Esc back", help_lines=HELP, show_help=help_, dim=0.35)
        return cv


# =============================================================================================
# Main
# =============================================================================================
def main():
    with Terminal() as term:
        demo = TitleDemo()
        while True:
            help_ = False
            go = False
            last = time.time()
            while not go:                       # title
                now = time.time()
                cols, rows = term.size()
                if cols < 60 or rows < 20:
                    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (60x20).")
                    term.keys(0.3)
                    continue
                term.write(demo.frame(cols, rows, min(0.1, now - last), help_).emit())
                last = now
                for k in term.keys(1 / 30):
                    if help_:
                        help_ = False
                    elif k == "?":
                        help_ = True
                    elif k in ("q", "esc"):
                        return
                    elif k in ("enter", " "):
                        go = True
            while True:                         # a dive (Enter on the end screen starts another)
                term.write("\x1b[0m\x1b[2J\x1b[H\n\n   Charting a new trench...")
                d = Dive()
                last = time.time()
                record = None
                back = again = False
                while not (back or again):
                    now = time.time()
                    for k in term.keys(0):
                        if d.over:
                            if k in ("q", "esc"):
                                back = True
                            elif record is not None and k in ("enter", " "):
                                again = True
                            continue
                        a = shared_key(k, d.paused)
                        if a == "pause":
                            d.paused = True
                        elif a == "resume":
                            d.paused = d.help = False
                        elif a == "quit":
                            back = True
                        elif a == "help":
                            d.help = not d.help
                            d.paused = True
                        elif a is None:
                            d.key(k)
                    d.update(min(0.1, now - last))
                    last = now
                    if d.over and record is None:
                        record = submit(GAME, "dive", d.score)
                    cols, rows = term.size()
                    if cols < 60 or rows < 20:
                        term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (60x20).")
                        time.sleep(0.2)
                        continue
                    cv = render(d, cols, rows)
                    if d.paused:
                        overlay(cv, HELP if d.help else PAUSE)
                    if d.over:
                        render_end(d, cv, record)
                    term.write(cv.emit())
                    time.sleep(max(0.0, 1 / 40 - (time.time() - now)))
                if back:
                    break


def reachable(w):
    """Flood fill the water from the start: can the Source be reached?"""
    start = (int(W / 2), 14)
    seen = bytearray(W * H)
    q = deque([start])
    seen[start[1] * W + start[0]] = 1
    g = w.g
    while q:
        x, y = q.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < W and 0 <= ny < H:
                i = ny * W + nx
                if not seen[i] and g[i] == 0:
                    seen[i] = 1
                    q.append((nx, ny))
    sx, sy = w.source
    return seen[int(sy) * W + int(sx)] == 1


def autopilot(seed, limit=400):
    """Dive down the main shaft without creatures, the way a careful player would. Returns the Dive."""
    d = Dive(seed)
    d.w.creatures = []
    path = d.w.path
    i = 0
    best_y, last_progress = d.y, 0.0
    while not d.over and d.t < limit and d.t - last_progress < 60:
        i = min(range(max(0, i - 5), min(len(path), i + 30)), key=lambda k: math.hypot(path[k][0] - d.x, path[k][1] - d.y))
        tx, ty = path[min(i + 3, len(path) - 1)][:2]
        if i >= len(path) - 4:
            tx, ty = d.w.source
        if d.oxygen < 35:
            v = min(d.w.vents, key=lambda v: math.hypot(v[0] - d.x, v[1] - d.y))
            if math.hypot(v[0] - d.x, v[1] - d.y) < 160:
                tx, ty = v[0], v[1] - 5
        dx, dy = tx - d.x, ty - d.y
        dl = math.hypot(dx, dy) or 1
        if abs(dx) > 1.5 and d.vx * (dx / dl) < 14 * abs(dx / dl):
            d.key("right" if dx > 0 else "left")
        if abs(dy) > 1.5 and d.vy * (dy / dl) < 14 * abs(dy / dl):
            d.key("down" if dy > 0 else "up")
        for _ in range(4):
            d.update(1 / 40)
            if d.over:
                break
        if d.y > best_y + 5:
            best_y, last_progress = d.y, d.t
    return d


def selftest():
    t0 = time.time()
    rnd = random.Random(5)
    for seed in range(40):          # every trench must be finishable by the sub itself
        w = World(seed)
        assert w.passable and w.reached(w.sub_reach(margin=1), w.source[0], w.source[1], 10, 10), \
            "seed %d: the sub cannot reach the Source" % seed
    for seed in range(8):
        d = Dive(seed)
        w = d.w
        assert reachable(w), "seed %d: the Source cannot be reached" % seed
        assert w.passable, "seed %d: the sub does not fit through to the Source" % seed
        assert len(w.vents) >= 5 and len(w.loot) >= 10, "seed %d: too few vents or finds" % seed
        kinds = {c.kind for c in w.creatures}
        assert {"jelly", "lurker", "leviathan"} <= kinds, "seed %d: creatures missing" % seed
        # a random pilot for a minute of game time: nothing may crash, the sub never ends up in rock
        for i in range(2400):
            if rnd.random() < 0.3:
                d.key(rnd.choice(["down", "down", "down", "left", "right", "up", " ", "f", "l", "e"]))
            d.update(1 / 40)
            assert not d.w.solid(d.x, d.y), "seed %d: the sub is inside rock" % seed
            if d.over:
                break
        render(d, 120, 40)
    for seed in range(100, 110):    # a careful pilot must be able to dive all the way down
        d = autopilot(seed)
        assert d.won, "seed %d: the pilot could not finish (%d m, %s)" % (seed, d.depth_m(), d.cause or "stuck")
    print("Self-test ok: 40 trenches passable for the sub, 8 played at random, 10 dived to the Source, %.1fs"
          % (time.time() - t0))


def bench():
    d = Dive(3)
    for i in range(200):
        if i % 4 == 0:
            d.key("down")
        if i % 40 == 0:
            d.key(" ")
        d.update(1 / 40)
    for cols, rows in ((160, 45), (240, 70)):
        t = time.time()
        for _ in range(20):
            render(d, cols, rows).emit(True)
        print("frame %.1f ms at %dx%d (%d echoes)" % ((time.time() - t) / 20 * 1000, cols, rows, len(d.echo)))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--bench" in sys.argv:
        bench()
    else:
        main()
