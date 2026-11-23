#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""LIGHTKEEPER - one beam, many ships, a long night.

You keep the lighthouse on a rocky island. Night falls, a storm comes in, and ships from every side are making
for the harbour - each with only a small lantern. Your beam is the only light on the coast: a ship that sees it
steers clear of the reefs; a ship left in the dark sails on blindly. Turn the beam, focus it, sound the horn in
the fog, refill the oil, and send the rescue boat when someone runs aground.

Alone you do it all; with a second player at the keyboard, one keeps the light and the other steers the
rescue boat.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
Run:        python3 lightkeeper.py
Self-test:  python3 lightkeeper.py --selftest
Benchmark:  python3 lightkeeper.py --bench
"""
import math
import random
import sys
import time
from collections import deque

from arcadekit import (AUTO_LABEL, AutoMode, Canvas, Terminal, clamp, load_scores, mix, overlay, shade, shared_key,
                       submit, title_screen)
from arcadesound import Sound

GAME = "lightkeeper"
WATER, ROCK, LAND, HARBOUR = 0, 1, 2, 3
TAU = 2 * math.pi

SHIPS = {  # speed px/s, length, hull colour, points, label
    "fishing": (9.0, 4, (150, 110, 70), 100, "fishing boat"),
    "sail": (7.5, 4, (190, 170, 130), 150, "sailing boat"),
    "freighter": (5.0, 7, (120, 70, 60), 250, "freighter"),
}
UPGRADES = [
    ("lens", "Fresnel lens", "the beam reaches 15% further"),
    ("tank", "Bigger oil tank", "40% more oil, refills twice as fast"),
    ("gear", "Geared mechanism", "the beam turns 30% faster"),
    ("horn", "Louder horn", "reaches further, ready sooner"),
    ("boat", "Motor launch", "the rescue boat is 20% faster"),
    ("pier", "Pier lanterns", "ships near the harbour find it alone"),
    ("buoy", "Spare lifebuoy", "one more life"),
]
WEATHER = ["calm", "breezy", "fog banks", "rain and lightning", "storm"]

# Sounds: the foghorn is the voice of the lighthouse; the rest is weather, wood and little bells.
SND = Sound(GAME, {
    "horn": [dict(w="saw", f=98, f2=94, d=1.05, v=0.34, a=0.12, r="hold", vib=(4.5, 0.08)),
             dict(w="square", f=98.8, f2=94.6, d=1.0, v=0.18, a=0.14, r="hold", duty=0.4, at=0),
             dict(w="saw", f=147.5, f2=141.5, d=0.95, v=0.1, a=0.16, r="hold", at=0)],
    "refill": [dict(w="sine", f=180, f2=120, d=0.09, v=0.32), dict(w="sine", f=210, f2=130, d=0.09, v=0.28),
               dict(w="sine", f=190, f2=115, d=0.1, v=0.24), dict(w="sine", f=230, f2=140, d=0.12, v=0.2)],
    "relit": [dict(w="noise", f=3000, f2=900, d=0.18, v=0.16), dict(w="tri", f=440, d=0.1, v=0.14, at=0.04)],
    "empty": [dict(w="tri", f=330, f2=160, d=0.3, v=0.24), dict(w="noise", f=1200, f2=300, d=0.2, v=0.1, at=0)],
    "saved": [dict(w="tri", f=784, d=0.08, v=0.28), dict(w="tri", f=1047, d=0.08, v=0.26),
              dict(w="sine", f=1568, d=0.35, v=0.18)],
    "wreck": [dict(w="noise", f=1400, f2=90, d=0.5, v=0.55), dict(w="square", f=110, f2=45, d=0.35, v=0.3, at=0),
              dict(w="noise", f=600, f2=120, d=0.25, v=0.3, at=0.12)],
    "flare": [dict(w="noise", f=6000, f2=2500, d=0.25, v=0.16, a=0.02),
              dict(w="saw", f=500, f2=1300, d=0.25, v=0.08, at=0), dict(w="noise", f=3000, d=0.1, v=0.12, at=0.28)],
    "boat_away": [dict(w="square", f=70, d=0.04, v=0.2, duty=0.3), dict(w="square", f=74, d=0.04, v=0.2, duty=0.3),
                  dict(w="square", f=80, d=0.04, v=0.2, duty=0.3), dict(w="square", f=86, d=0.04, v=0.2, duty=0.3),
                  dict(w="tri", f=440, f2=660, d=0.16, v=0.2)],
    "pickup": [dict(w="tri", f=523, d=0.07, v=0.26), dict(w="tri", f=659, d=0.12, v=0.24)],
    "rescued": [dict(w="tri", f=523, d=0.1, v=0.28), dict(w="tri", f=659, d=0.1, v=0.28),
                dict(w="tri", f=784, d=0.1, v=0.28), dict(w="sine", f=1047, d=0.4, v=0.24, vib=(5, 0.15))],
    "thunder": [dict(w="noise", f=260, f2=40, d=1.2, v=0.5, a=0.02, r="exp"),
                dict(w="noise", f=90, f2=30, d=1.1, v=0.35, a=0.15, r="lin", at=0.1)],
    "lost": [dict(w="sine", f=392, d=0.3, v=0.26), dict(w="sine", f=311, d=0.55, v=0.24, vib=(4, 0.2))],
    "dawn": [dict(w="tri", f=392, d=0.14, v=0.26), dict(w="tri", f=523, d=0.14, v=0.26),
             dict(w="tri", f=659, d=0.14, v=0.26), dict(w="tri", f=784, d=0.2, v=0.26),
             dict(w="sine", f=1047, d=0.45, v=0.22, vib=(5, 0.12)), dict(w="sine", f=523, d=0.6, v=0.12, at=0.56)],
    "pick": [dict(w="tri", f=880, d=0.03, v=0.18)],
    "upgrade": [dict(w="square", f=659, d=0.07, v=0.24, duty=0.25), dict(w="square", f=988, d=0.18, v=0.24, duty=0.25)],
    "over": [dict(w="saw", f=196, f2=180, d=0.4, v=0.2, a=0.05, r="lin"),
             dict(w="saw", f=165, f2=150, d=0.4, v=0.2, a=0.05, r="lin"),
             dict(w="saw", f=131, f2=98, d=0.42, v=0.2, a=0.05, r="lin", vib=(4, 0.2))],
    "sound_on": [dict(w="tri", f=440, d=0.07, v=0.3), dict(w="tri", f=880, d=0.14, v=0.28)],
})


def wrap(a):
    return (a + math.pi) % TAU - math.pi


# =============================================================================================
# The coast
# =============================================================================================
class Coast:
    """A stretch of coast sized to the screen: shore, harbour channel, the lighthouse island and reefs."""

    def __init__(self, W, H, seed, night=1):
        self.W, self.H = W, H
        rnd = self.rnd = random.Random(seed * 7 + night)
        for attempt in range(40):
            if self.generate(rnd, night):
                return
        raise RuntimeError("could not chart a navigable coast")

    def generate(self, rnd, night):
        W, H = self.W, self.H
        g = self.g = bytearray(W * H)
        ph = [rnd.uniform(0, 6.3) for _ in range(4)]
        base = H * 0.80
        self.coast = []
        for x in range(W):
            c = base - (math.sin(x * 0.045 + ph[0]) * 3.5 + math.sin(x * 0.11 + ph[1]) * 1.8
                        + math.sin(x * 0.019 + ph[2]) * 4)
            self.coast.append(c)
            for y in range(int(c), H):
                g[y * W + x] = LAND
        # the harbour channel: a gap in the shore, its basin is the goal
        hx = int(W * rnd.uniform(0.3, 0.7))
        self.harbour = (hx, int(self.coast[hx]) + 3)
        hw = 6
        for x in range(hx - hw, hx + hw + 1):
            for y in range(int(min(self.coast[max(0, hx - hw - 2):hx + hw + 3])) - 1, H):
                if 0 <= x < W:
                    g[y * W + x] = HARBOUR if y >= self.coast[x] - 1 else WATER
        # the lighthouse island, away from the channel
        side = rnd.choice((-1, 1))
        lx = int(clamp(hx + side * W * rnd.uniform(0.22, 0.32), 14, W - 14))
        if abs(lx - hx) < 18:
            lx = int(clamp(hx - side * W * 0.27, 14, W - 14))
        ly = int(H * rnd.uniform(0.45, 0.55))
        self.island = (lx, ly)
        self.blob(lx, ly, 4.5, LAND)
        for _ in range(5):
            a = rnd.uniform(0, TAU)
            self.blob(lx + math.cos(a) * 6, ly + math.sin(a) * 5, rnd.uniform(1, 2), ROCK)
        self.lamp = (lx, ly - 5)                      # the lamp on top of the tower
        self.dock = (lx, ly - 8) if ly > H * 0.3 else (lx, ly + 8)
        dx, dy = self.dock
        self.dock = (dx, dy)
        for yy in range(dy - 2, dy + 3):              # keep the jetty water clear
            for xx in range(dx - 3, dx + 4):
                if 0 <= xx < W and 0 <= yy < H and g[yy * W + xx] == ROCK:
                    g[yy * W + xx] = WATER
        # reefs: clusters of rocks, more each night, never inside the harbour approach
        for _ in range(7 + night):
            for _ in range(30):
                rx = rnd.uniform(6, W - 6)
                ry = rnd.uniform(H * 0.12, min(self.coast[int(rx)] - 8, H * 0.74))
                if math.hypot(rx - hx, ry - self.harbour[1]) > 16 and math.hypot(rx - lx, ry - ly) > 10:
                    break
            for _ in range(rnd.randint(3, 7)):
                self.blob(rx + rnd.gauss(0, 3.5), ry + rnd.gauss(0, 2.2), rnd.uniform(0.8, 2.2), ROCK)
        self.nav = self.field([(x, y) for y in range(H) for x in range(W) if g[y * W + x] == HARBOUR])
        # every spawn edge must have a way in
        self.spawns = [(x, 1) for x in range(4, W - 4, 3)] + [(1, y) for y in range(3, int(H * 0.55), 3)] \
            + [(W - 2, y) for y in range(3, int(H * 0.55), 3)]
        self.spawns = [p for p in self.spawns if self.nav[p[1] * W + p[0]] < 10 ** 6]
        dock_ok = self.nav[self.dock[1] * W + self.dock[0]] < 10 ** 6
        return len(self.spawns) > 20 and dock_ok

    def blob(self, cx, cy, r, kind):
        W, H, g = self.W, self.H, self.g
        for y in range(int(cy - r), int(cy + r) + 1):
            for x in range(int(cx - r), int(cx + r) + 1):
                if 0 <= x < W and 0 <= y < H and (x - cx) ** 2 + (y - cy) ** 2 <= r * r and g[y * W + x] != HARBOUR:
                    g[y * W + x] = kind

    def field(self, goals, keep_off=1):
        """BFS distance to the goals through water, keeping a little distance from rock where possible."""
        W, H, g = self.W, self.H, self.g
        INF = 10 ** 7
        near = bytearray(W * H)
        for y in range(H):
            for x in range(W):
                if g[y * W + x] in (ROCK, LAND):
                    for yy in range(max(0, y - keep_off), min(H, y + keep_off + 1)):
                        for xx in range(max(0, x - keep_off), min(W, x + keep_off + 1)):
                            near[yy * W + xx] = 1
        dist = [INF] * (W * H)
        q = deque()
        for x, y in goals:
            dist[y * W + x] = 0
            q.append((x, y))
        while q:
            x, y = q.popleft()
            d = dist[y * W + x] + 1
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < W and 0 <= ny < H:
                    i = ny * W + nx
                    if dist[i] > d and g[i] in (WATER, HARBOUR) and (not near[i] or g[i] == HARBOUR):
                        dist[i] = d
                        q.append((nx, ny))
        # cells right next to rock get a value too (higher), so nobody is ever "lost"
        for _ in range(3):
            for y in range(H):
                for x in range(W):
                    i = y * W + x
                    if dist[i] >= INF and g[i] in (WATER, HARBOUR):
                        best = min((dist[yy * W + xx] for xx, yy in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))
                                    if 0 <= xx < W and 0 <= yy < H), default=INF)
                        if best < INF:
                            dist[i] = best + 6
        return dist

    def at(self, x, y):
        ix, iy = int(x), int(y)
        if ix < 0 or iy < 0 or ix >= self.W or iy >= self.H:
            return WATER          # beyond the map: open sea
        return self.g[iy * self.W + ix]

    def downhill(self, dist, x, y):
        """Direction to the neighbouring water pixel with the smallest distance value (never through rock)."""
        W, H = self.W, self.H
        ix, iy = int(clamp(x, 0, W - 1)), int(clamp(y, 0, H - 1))
        here = dist[iy * W + ix]
        best, bv = None, here
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nx, ny = ix + dx, iy + dy
            if 0 <= nx < W and 0 <= ny < H:
                v = dist[ny * W + nx] + (0.4 if dx and dy else 0)
                if v < bv and self.g[ny * W + nx] in (WATER, HARBOUR):
                    if dx and dy and (self.g[iy * W + nx] in (ROCK, LAND) or self.g[ny * W + ix] in (ROCK, LAND)):
                        continue          # no squeezing diagonally between two rocks
                    best, bv = (nx + 0.5, ny + 0.5), v
        if best is None:
            return None
        return math.atan2(best[1] - y, best[0] - x)


# =============================================================================================
# The night
# =============================================================================================
class Ship:
    def __init__(self, kind, x, y, heading):
        self.kind = kind
        self.x, self.y = x, y
        self.h = heading
        self.speed, self.length, self.col, self.points, self.label = SHIPS[kind]
        self.aware = 0.0          # seconds it can still see well (lit, horn, lightning)
        self.slow = 0.0
        self.state = "sailing"    # sailing, saved, wrecked, rescued, lost
        self.crew = {"fishing": 3, "sail": 2, "freighter": 6}[kind]
        self.timer = 0.0          # distress time left once wrecked
        self.wake = deque(maxlen=10)


class Boat:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.home = (x, y)
        self.vx = self.vy = 0.0
        self.state = "docked"     # docked, out, carrying
        self.target = None
        self.field = None
        self.crew = 0
        self.pick = 0.0


class Night:
    def __init__(self, W, H, seed, night=1, keepers=1, up=None, lives=3, score=0):
        self.W, self.H = W, H
        self.seed, self.night, self.keepers = seed, night, keepers
        self.up = dict(up or {})
        self.c = Coast(W, H, seed, night)
        self.rnd = random.Random(seed * 31 + night)
        self.t = 0.0
        self.length = 110 + 12 * night
        self.beam = -math.pi / 2
        self.spin = 0.0
        self.half = 0.25           # beam half-width (rad): narrow = far, wide = near
        self.oil = self.tank()
        self.refill = 0.0          # seconds of refilling left (light off)
        self.horn_cd = 0.0
        self.horn_ring = None
        self.lives, self.score = lives, score
        self.ships = []
        self.boat = Boat(*self.c.dock)
        self.msgs = []
        self.flash = 0.0
        self.over = self.dawn = False
        self.paused = self.help = False
        self.quiet = False         # the title demo keeps its light without sound
        self.flare_at = None       # next distress flare sound while a wreck waits
        self.saved = self.wrecks = self.rescued = self.lost = 0
        n = 3 + 2 * night + max(0, night - 3) * 2
        self.schedule = sorted(self.rnd.uniform(4, self.length * 0.72) for _ in range(n))
        w = WEATHER[min(night - 1, len(WEATHER) - 1)]
        self.weather = w
        self.wind = (self.rnd.uniform(-1, 1) * (0.5 + 0.4 * night), self.rnd.uniform(-0.3, 0.6) * (0.4 + 0.3 * night))
        self.fog = 0.0 if night < 3 else min(0.85, 0.35 + 0.12 * (night - 3))
        self.rain = night >= 4
        self.lightning = 0.0 if night < 4 else 0.05 + 0.02 * (night - 4)
        self.fog_seed = [[self.rnd.random() for _ in range(17)] for _ in range(17)]
        self.drops = [[self.rnd.uniform(0, W), self.rnd.uniform(0, H)] for _ in range(int(W * H / 90))] if self.rain else []
        self.say("Night %d - %s. %d ships expected." % (night, w, n), 5)

    # --- numbers that upgrades change ---------------------------------------------------------
    def range_max(self):
        return max(self.W, self.H) * 0.75 * (1.15 ** self.up.get("lens", 0))

    def beam_range(self):
        narrow = (0.45 - self.half) / 0.33
        rain = 0.8 if self.rain else 1.0
        return self.range_max() * (0.45 + 0.55 * narrow) * rain

    def tank(self):
        return 100.0 * (1.4 ** self.up.get("tank", 0))

    def horn_radius(self):
        return 34 * (1.35 ** self.up.get("horn", 0))

    def refill_time(self):
        return 4.0 / (2 ** self.up.get("tank", 0))

    def boat_speed(self):
        return 20 * (1.2 ** self.up.get("boat", 0))

    def pier_radius(self):
        return 14 + 18 * self.up.get("pier", 0)

    def say(self, s, ttl=3.0):
        self.msgs.append([s, self.t + ttl])
        self.msgs = self.msgs[-3:]

    def sfx(self, name, vol=1.0, gap=0.04):
        if not self.quiet:
            SND.play(name, vol, gap)

    # --- the light --------------------------------------------------------------------------------
    def fog_at(self, x, y):
        if self.fog <= 0:
            return 0.0
        fx = (x / 22.0 + self.t * self.wind[0] * 0.05) % 16
        fy = (y / 22.0 + self.t * self.wind[1] * 0.05) % 16
        ix, iy = int(fx), int(fy)
        tx, ty = fx - ix, fy - iy
        s = self.fog_seed
        a = s[iy][ix] + (s[iy][ix + 1] - s[iy][ix]) * tx
        b = s[iy + 1][ix] + (s[iy + 1][ix + 1] - s[iy + 1][ix]) * tx
        v = a + (b - a) * ty
        return clamp((v - 0.35) * 1.8, 0, 1) * self.fog

    def light_at(self, x, y):
        """How brightly the beam lights the point (0..1)."""
        if self.refill > 0 or self.oil <= 0:
            return 0.0
        lx, ly = self.c.lamp
        dx, dy = x - lx, y - ly
        d = math.hypot(dx, dy)
        R = self.beam_range()
        if d > R or d < 0.5:
            return 1.0 if d < 0.5 else 0.0
        da = abs(wrap(math.atan2(dy, dx) - self.beam))
        if da > self.half:
            return 0.0
        return (1 - d / R) ** 0.6 * (1 - (da / self.half) ** 2) * (1 - self.fog_at(x, y) * 0.8)

    # --- controls ----------------------------------------------------------------------------------
    def key(self, k):
        if self.over or self.dawn:
            return
        coop = self.keepers == 2
        spin_max = 3.0 * (1.3 ** self.up.get("gear", 0))
        if k in ("left",) or (k == "a" and not coop):
            self.spin = max(-spin_max, self.spin - 1.0)
        elif k in ("right",) or (k == "d" and not coop):
            self.spin = min(spin_max, self.spin + 1.0)
        elif k in ("up",) or (k == "w" and not coop):
            self.half = max(0.12, self.half - 0.03)
        elif k in ("down",) or (k == "s" and not coop):
            self.half = min(0.45, self.half + 0.03)
        elif k == " ":
            self.horn()
        elif k == "r":
            if self.refill <= 0 and self.oil < self.tank() - 1:
                self.refill = self.refill_time()
                self.sfx("refill")
                self.say("Refilling the lamp - the coast goes dark for a moment.", 3)
        elif k == "b" and not coop:
            self.send_boat()
        elif coop and k in ("w", "a", "s", "d"):
            b = self.boat
            dx, dy = {"w": (0, -1), "a": (-1, 0), "s": (0, 1), "d": (1, 0)}[k]
            b.vx += dx * 7
            b.vy += dy * 5
            if b.state == "docked":
                b.state = "out"
                self.sfx("boat_away")

    def horn(self):
        if self.horn_cd > 0:
            self.say("The horn needs a moment (%.0f s)." % self.horn_cd, 1.2)
            return
        self.horn_cd = max(3.0, 8.0 - 2.0 * self.up.get("horn", 0))
        self.horn_ring = self.t
        self.sfx("horn", gap=1.0)
        R = self.horn_radius()
        n = 0
        for s in self.ships:
            if s.state == "sailing" and math.hypot(s.x - self.c.lamp[0], s.y - self.c.lamp[1]) < R:
                s.aware = max(s.aware, 3.5)
                s.slow = 3.0
                n += 1
        self.say("HOOOOONK - %d ship%s heard it." % (n, "" if n == 1 else "s"), 2)

    def send_boat(self):
        b = self.boat
        wrecks = [s for s in self.ships if s.state == "wrecked"]
        if b.state != "docked":
            self.say("The rescue boat is already out.", 1.5)
            return
        if not wrecks:
            self.say("Nobody needs rescuing right now.", 1.5)
            return
        w = min(wrecks, key=lambda s: math.hypot(s.x - b.x, s.y - b.y))
        self.boat_to(w)
        self.sfx("boat_away")
        self.say("Rescue boat away - light its way, it is slow in the dark.", 3)

    def boat_to(self, wreck):
        b = self.boat
        b.state, b.target = "out", wreck
        goals = [(int(wreck.x + dx), int(wreck.y + dy)) for dx in range(-3, 4) for dy in range(-3, 4)
                 if self.c.at(wreck.x + dx, wreck.y + dy) in (WATER, HARBOUR)
                 and 0 <= int(wreck.x + dx) < self.W and 0 <= int(wreck.y + dy) < self.H]
        b.field = self.c.field(goals or [(int(b.x), int(b.y))], keep_off=0)

    # --- time ----------------------------------------------------------------------------------------
    def update(self, dt):
        if self.over or self.dawn or self.paused:
            return
        self.t += dt
        c = self.c
        # the beam
        self.beam = (self.beam + self.spin * dt) % TAU
        self.spin *= 0.06 ** dt
        if self.refill > 0:
            self.refill -= dt
            self.oil = min(self.tank(), self.oil + self.tank() / self.refill_time() * dt)
            if self.refill <= 0:
                self.say("The lamp burns again.", 1.5)
                self.sfx("relit")
        else:
            narrow = (0.45 - self.half) / 0.33
            had_oil = self.oil > 0
            self.oil -= dt * (0.9 + 1.2 * narrow)      # a bigger tank simply lasts longer
            if self.oil <= 0:
                if had_oil:
                    self.sfx("empty")
                self.oil = 0
                if int(self.t * 2) % 8 == 0:
                    self.say("The lamp is out of oil! Press R to refill.", 1.5)
        self.horn_cd = max(0.0, self.horn_cd - dt)
        # lightning
        self.flash = max(0.0, self.flash - dt * 4)
        if self.lightning and self.rnd.random() < self.lightning * dt:
            self.flash = 1.0
            self.sfx("thunder", 0.8 + 0.2 * self.rnd.random(), gap=0.8)
            for s in self.ships:
                if s.state == "sailing":
                    s.aware = max(s.aware, 1.2)
        for drop in self.drops:
            drop[0] = (drop[0] + (self.wind[0] * 6 - 4) * dt) % self.W
            drop[1] = (drop[1] + 38 * dt) % self.H
        # arrivals
        while self.schedule and self.schedule[0] <= self.t:
            self.schedule.pop(0)
            self.spawn()
        for s in self.ships:
            self.update_ship(s, dt)
        self.update_boat(dt)
        if any(s.state == "wrecked" for s in self.ships):      # red distress flares now and then
            if self.flare_at is None:
                self.flare_at = self.t + 0.9
            elif self.t >= self.flare_at:
                self.flare_at = self.t + 10.0
                self.sfx("flare", 0.8)
        else:
            self.flare_at = None
        self.msgs = [m for m in self.msgs if m[1] > self.t]
        if self.lives <= 0:
            self.over = True
            self.sfx("over")
        elif self.t >= self.length and not self.schedule and not any(
                s.state in ("sailing", "wrecked") for s in self.ships) and self.boat.state != "carrying":
            self.dawn = True
            self.score += 300 * self.night
            self.say("Dawn.", 3)
            self.sfx("dawn")

    def spawn(self):
        c, rnd = self.c, self.rnd
        x, y = rnd.choice(c.spawns)
        kind = rnd.choice(["fishing", "fishing", "sail", "freighter"] if self.night > 1 else ["fishing", "sail"])
        hx, hy = c.harbour
        h = math.atan2(hy - y, hx - x) + rnd.gauss(0, 0.28)
        s = Ship(kind, x + 0.5, y + 0.5, h)
        self.ships.append(s)

    def update_ship(self, s, dt):
        c = self.c
        if s.state == "wrecked":
            s.timer -= dt
            if s.timer <= 0:
                s.state = "lost"
                self.lives -= 1
                self.lost += 1
                self.say("The crew of the %s was lost." % s.label, 4)
                self.sfx("lost")
            return
        if s.state != "sailing":
            return
        lit = self.light_at(s.x, s.y)
        if lit > 0.18:
            s.aware = 2.6
        near_harbour = math.hypot(s.x - c.harbour[0], s.y - c.harbour[1]) < self.pier_radius()
        s.aware = max(0.0, s.aware - dt)
        s.slow = max(0.0, s.slow - dt)
        turn = (1.6 if s.kind != "freighter" else 0.8) * dt
        if s.aware > 0 or near_harbour:
            want = c.downhill(c.nav, s.x, s.y)
            if want is not None:
                s.h += clamp(wrap(want - s.h), -turn, turn)
        else:
            fog = self.fog_at(s.x, s.y)
            storm = 0.03 * max(0, self.night - 2)
            s.h += self.rnd.gauss(0, (0.12 + storm + 0.35 * fog) * math.sqrt(dt))
            # in the dark they still head roughly for the harbour lights, if they can see them
            if fog < 0.5:
                hx, hy = c.harbour
                want = math.atan2(hy - s.y, hx - s.x)
                s.h += clamp(wrap(want - s.h), -0.15 * dt, 0.15 * dt)
        sp = s.speed * (0.5 if s.slow > 0 else 1.0) * (1 + 0.06 * (self.night - 1))
        wx, wy = self.wind
        if s.kind == "sail":
            sp *= 1.0 + 0.15 * (math.cos(s.h) * wx + math.sin(s.h) * wy)
        if not s.wake or math.hypot(s.wake[-1][0] - s.x, s.wake[-1][1] - s.y) > 1.2:
            s.wake.append((s.x, s.y))
        s.x += math.cos(s.h) * sp * dt + wx * 0.25 * dt
        s.y += math.sin(s.h) * sp * dt + wy * 0.25 * dt
        s.x = clamp(s.x, 0.5, self.W - 0.5)
        s.y = max(0.5, s.y)
        here = c.at(s.x, s.y)
        bow = c.at(s.x + math.cos(s.h) * s.length * 0.4, s.y + math.sin(s.h) * s.length * 0.4)
        if here == HARBOUR:
            s.state = "saved"
            self.saved += 1
            pts = int(s.points * (1 + 0.1 * self.night))
            self.score += pts
            self.say("The %s is safe in harbour. +%d" % (s.label, pts), 2.5)
            self.sfx("saved")
        elif here in (ROCK, LAND) or bow in (ROCK, LAND):
            s.state = "wrecked"
            s.timer = max(20.0, 52.0 - 4 * self.night)
            self.wrecks += 1
            hint = "Press B for the rescue boat!" if self.keepers == 1 else "Rescue boat, go!"
            self.say("The %s ran aground! %d aboard. %s" % (s.label, s.crew, hint), 4)
            self.sfx("wreck", gap=0.2)

    def update_boat(self, dt):
        b, c = self.boat, self.c
        lit = max(self.light_at(b.x, b.y), self.flash)
        if b.state == "docked":
            b.x, b.y = b.home
            return
        if self.keepers == 2:   # steered by the second player
            sp = self.boat_speed() * (1.0 if lit > 0.15 else 0.55)
            v = math.hypot(b.vx, b.vy)
            if v > sp:
                b.vx, b.vy = b.vx / v * sp, b.vy / v * sp
            b.vx *= 0.5 ** dt
            b.vy *= 0.5 ** dt
            nx, ny = b.x + b.vx * dt, b.y + b.vy * dt
            if c.at(nx, b.y) in (WATER, HARBOUR) and 0 <= nx < self.W:
                b.x = nx
            else:
                b.vx = 0
            if c.at(b.x, ny) in (WATER, HARBOUR) and 0 <= ny < self.H:
                b.y = ny
            else:
                b.vy = 0
        else:                   # sails itself, slowly unless lit
            if b.field is None:
                return
            sp = self.boat_speed() * (1.0 if lit > 0.15 else 0.3)
            want = c.downhill(b.field, b.x, b.y)
            if want is not None:
                nx, ny = b.x + math.cos(want) * sp * dt, b.y + math.sin(want) * sp * dt
                if c.at(nx, ny) in (WATER, HARBOUR):
                    b.x, b.y = nx, ny
        # pick up survivors
        if b.state == "out":
            for s in self.ships:
                if s.state == "wrecked" and math.hypot(s.x - b.x, s.y - b.y) < 5:
                    b.pick += dt
                    if b.pick > 1.2:
                        b.pick = 0.0
                        b.crew, s.state = s.crew, "rescued"
                        b.state = "carrying"
                        self.say("%d sailors aboard the rescue boat - bring them home." % b.crew, 3)
                        self.sfx("pickup")
                        if self.keepers == 1:
                            b.field = c.field([b.home], keep_off=0)
                    break
            else:
                b.pick = 0.0
                if self.keepers == 1 and (b.target is None or b.target.state != "wrecked"):
                    others = [s for s in self.ships if s.state == "wrecked"]
                    if others:
                        self.boat_to(min(others, key=lambda s: math.hypot(s.x - b.x, s.y - b.y)))
                    else:
                        b.state, b.field = "carrying", c.field([b.home], keep_off=0)
                        b.crew = 0
        if b.state == "carrying" and math.hypot(b.x - b.home[0], b.y - b.home[1]) < 4:
            if b.crew:
                pts = 60 * b.crew
                self.score += pts
                self.rescued += b.crew
                self.say("%d sailors rescued. +%d" % (b.crew, pts), 3)
                self.sfx("rescued")
            b.crew, b.state, b.target, b.field = 0, "docked", None, None
        if self.keepers == 2 and b.state == "out" and b.crew == 0 and \
                math.hypot(b.x - b.home[0], b.y - b.home[1]) < 3 and math.hypot(b.vx, b.vy) < 1:
            b.state = "docked"


# =============================================================================================
# Drawing
# =============================================================================================
SEA_DARK, SEA_LIT = (4, 8, 20), (60, 120, 150)
ROCK_DARK, ROCK_LIT = (14, 14, 18), (120, 110, 100)
LAND_DARK, LAND_LIT = (8, 12, 10), (70, 100, 60)
HARB_DARK, HARB_LIT = (6, 10, 24), (70, 110, 150)
SURF = (190, 210, 225)             # breakers around the reefs
LANTERN = (255, 220, 120)
DISTRESS = (255, 70, 60)


class Painter:
    """Static per-pixel data for a coast (angles, distances, colours), so a frame is cheap."""

    def __init__(self, night):
        c = night.c
        W, H = c.W, c.H
        lx, ly = c.lamp
        rnd = random.Random(night.seed)
        self.ang = [math.atan2(y - ly, x - lx) for y in range(H) for x in range(W)]
        self.dist = [math.hypot(x - lx, y - ly) for y in range(H) for x in range(W)]
        # coherent swell: long wave bands bent by a slow second wave, plus a little sparkle
        self.phase = [x * 0.33 + y * 0.52 + 1.6 * math.sin(y * 0.17 + x * 0.06) + rnd.uniform(0, 0.6)
                      for y in range(H) for x in range(W)]
        dark, lit = [], []
        for i, k in enumerate(c.g):
            j = rnd.uniform(-0.08, 0.08)
            if k == WATER:
                d, l = SEA_DARK, SEA_LIT
            elif k == ROCK:
                d, l = ROCK_DARK, shade(ROCK_LIT, 1 + j)
            elif k == LAND:
                d, l = LAND_DARK, shade(LAND_LIT, 1 + j * 2)
            else:
                d, l = HARB_DARK, HARB_LIT
            dark.append(d)
            lit.append(l)
        self.dark, self.lit = dark, lit
        self.water = [k in (WATER, HARBOUR) for k in c.g]
        # surf: water touching a reef breaks white, so reefs read even in the dark and in fog
        g = c.g
        self.surf = [False] * (W * H)
        for y in range(1, H - 1):
            for x in range(1, W - 1):
                i = y * W + x
                if g[i] == WATER and ROCK in (g[i - 1], g[i + 1], g[i - W], g[i + W]):
                    self.surf[i] = True


def render(n, painter, cols, rows, title_mode=False):
    cv = Canvas(cols, rows)
    c = n.c
    W, H = c.W, c.H
    PW, PH = cols, (rows - (0 if title_mode else 1)) * 2
    ox, oy = (PW - W) // 2, (PH - H) // 2
    px = cv.px
    t = n.t
    on = n.refill <= 0 and n.oil > 0
    R = n.beam_range()
    half = n.half
    beam = n.beam
    flash = n.flash
    ang, dist, phase, dark, lit, water = painter.ang, painter.dist, painter.phase, painter.dark, painter.lit, painter.water
    surf = painter.surf
    fogc = n.fog > 0
    # fog on a coarse grid
    fg = {}
    for y in range(0, H, 3):
        for x in range(0, W, 3):
            fg[(x // 3, y // 3)] = n.fog_at(x, y) if fogc else 0.0
    moon = 0.06 if n.night <= 2 else 0.03
    for y in range(H):
        Y = y + oy
        if not 0 <= Y < PH:
            continue
        row = px[Y]
        base = y * W
        for x in range(W):
            X = x + ox
            if not 0 <= X < PW:
                continue
            i = base + x
            L = moon
            d = dist[i]
            if on and d < R:
                da = ang[i] - beam
                if da > math.pi:
                    da -= TAU
                elif da < -math.pi:
                    da += TAU
                if -half < da < half:
                    q = da / half
                    L += (1 - d / R) ** 0.6 * (1 - q * q)
            if d < 6:                                  # the lamp's own glow
                L += (1 - d / 6) * (0.7 if on else 0.15)
            f = fg.get((x // 3, y // 3), 0.0)
            if f:
                L *= 1 - f * 0.8
            L = L + flash * 0.9
            if L > 1:
                L = 1.0
            if water[i]:
                L *= 0.8 + 0.2 * math.sin(t * 1.5 + phase[i])
            col = mix(dark[i], lit[i], L)
            if surf[i]:
                col = mix(col, SURF, 0.1 + 0.07 * math.sin(t * 2.2 + phase[i] * 2) + 0.3 * L)
            if f:
                col = mix(col, (40, 46, 56) if L < 0.3 else (150, 160, 170), f * 0.45)
            row[X] = col
    # rain streaks, visible where there is light
    for dx_, dy_ in n.drops:
        x, y = int(dx_), int(dy_)
        L = n.light_at(dx_, dy_) + flash
        if L > 0.1 and 0 <= x + ox < PW and 0 <= y + oy < PH:
            px[y + oy][x + ox] = mix(px[y + oy][x + ox], (170, 190, 210), min(0.6, L))

    def put(x, y, col, k=1.0):
        X, Y = int(x) + ox, int(y) + oy
        if 0 <= X < PW and 0 <= Y < PH:
            px[Y][X] = col if k >= 1 else mix(px[Y][X], col, k)

    # harbour lanterns, red and green
    hx, hy = c.harbour
    for sx_, col in ((hx - 7, (255, 60, 60)), (hx + 7, (60, 255, 110))):
        blink = 1.0 if int(t * 1.5) % 2 else 0.6
        put(sx_, c.coast[int(clamp(sx_, 0, W - 1))] - 1, col, blink)
    # the horn's ring
    if n.horn_ring is not None and t - n.horn_ring < 1.0:
        r = (t - n.horn_ring) * n.horn_radius()
        for k in range(0, 360, 3):
            a = math.radians(k)
            put(c.lamp[0] + math.cos(a) * r, c.lamp[1] + math.sin(a) * r, (200, 210, 230), 0.5 * (1 - (t - n.horn_ring)))
    # ships
    for s in n.ships:
        if s.state in ("saved", "rescued"):
            continue
        L = max(n.light_at(s.x, s.y), flash)
        if s.state == "sailing":
            for k, (wx_, wy_) in enumerate(s.wake):
                put(wx_, wy_, (120, 150, 170), 0.12 * k / 10 + L * 0.2)
        hcol = mix((20, 18, 18), s.col, max(0.15, L)) if s.state != "lost" else (30, 30, 34)
        ca, sa = math.cos(s.h), math.sin(s.h)
        tilt = 0.5 if s.state in ("wrecked", "lost") else 0.0
        for k in range(s.length):
            u = k - s.length / 2
            put(s.x + ca * u - sa * tilt * u * 0.3, s.y + sa * u + ca * tilt * u * 0.3, hcol)
            if s.kind == "freighter":
                put(s.x + ca * u - sa, s.y + sa * u + ca, shade(hcol, 0.8))
        if s.kind == "sail" and s.state == "sailing":
            put(s.x - sa * 1.5, s.y + ca * 1.5, mix((40, 40, 44), (235, 235, 230), max(0.2, L)))
        if s.state == "sailing":       # the lantern: always visible, with a small glow so ships never read as rock
            lx_, ly_ = s.x + ca * s.length * 0.3, s.y + sa * s.length * 0.3
            for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                put(lx_ + ddx, ly_ + ddy, LANTERN, 0.22)
            put(lx_, ly_, LANTERN)
            if not title_mode and s.aware <= 0 and danger(n, s) > 0.45 and int(t * 4) % 2:
                for ddy in (-4, -3, -1):    # "!" above a ship sailing blind towards rock
                    put(s.x, s.y + ddy, (255, 70, 60))
        elif s.state == "wrecked":     # distress flares, and the time the crew can still hold on
            urgent = s.timer < 10
            if int(t * (6 if urgent else 3)) % 2:
                for ddx, ddy in ((0, -1), (0, -2), (1, -2), (-1, -2)):
                    put(s.x + ddx, s.y + ddy, DISTRESS)
                put(s.x, s.y - 3, (255, 200, 160))
            if not (title_mode or n.over or n.dawn):
                tag = " %d " % max(0, math.ceil(s.timer))
                col_, row_ = int(s.x) + ox - len(tag) // 2, (int(s.y) + oy - 4) // 2
                if 0 <= row_ < rows - 1:
                    cv.put(max(0, min(cols - len(tag), col_)), row_, tag, (255, 255, 255) if urgent else (255, 210, 190),
                           (170, 30, 30) if urgent and int(t * 4) % 2 else (90, 20, 24))
    # the rescue boat
    b = n.boat
    bl = max(n.light_at(b.x, b.y), flash)
    if b.state != "docked":
        for ddx in range(-2, 3):
            for ddy in (-1, 0, 1):
                if abs(ddx) + abs(ddy) <= 2:
                    put(b.x + ddx, b.y + ddy, (255, 150, 60), 0.18 + 0.08 * math.sin(t * 5))
    put(b.x, b.y, mix((80, 40, 20), (255, 140, 40), max(0.4, bl)))
    put(b.x + 1, b.y, mix((80, 40, 20), (255, 140, 40), max(0.4, bl)))
    put(b.x - 1, b.y, (255, 240, 200) if b.state != "docked" else (160, 120, 80))
    # the lighthouse: tower and lamp
    lx, ly = c.island
    for k in range(5):
        put(lx, ly - k, (230, 230, 230) if k % 2 == 0 else (200, 40, 40))
    put(lx, ly - 5, (255, 250, 210) if on else (90, 80, 60))
    if not title_mode:
        hud(cv, n, cols, rows)
    return cv


HUD_BG = (12, 12, 20)
HUD_LABEL = (132, 136, 162)      # dim labels (4.7:1 on the bar); the values carry the colour
WARN = (255, 96, 80)
OIL_COL = (240, 200, 90)
WEATHER_SHORT = {"calm": "calm", "breezy": "breezy", "fog banks": "fog", "rain and lightning": "rain", "storm": "storm"}


def gauge(cv, x, r, v, n, col):
    """A gauge of coloured cells with half-cell resolution: full = col, empty = a dark trace of it."""
    v = clamp(v, 0.0, 1.0) * n
    empty = mix(HUD_BG, col, 0.22)
    for i in range(n):
        f = v - i
        cv.put(x + i, r, "▌" if 0.25 <= f < 0.75 else " ", col, col if f >= 0.75 else empty)
    return x + n


def hud(cv, n, cols, rows):
    r = rows - 1
    t = n.t
    blink = int(t * 4) % 2 == 0
    left = int(max(0, n.length - n.t))
    tank = n.tank()
    low = n.oil < tank * 0.2
    b = n.boat
    # every segment as a list of (text, colour) pieces, in a long and a short form; the bar picks what fits
    lives = max(0, n.lives)
    buoys = [("o" * lives or "-", (255, 120, 100))]
    oil_n = 10 if cols >= 120 else 6
    horn = ("ready", (150, 230, 170)) if n.horn_cd <= 0 else ("%.0fs" % n.horn_cd, (190, 196, 220))
    boat = {"docked": ("home", (200, 160, 120)), "out": ("out", (255, 160, 80)),
            "carrying": ("%d aboard" % b.crew, (255, 200, 120))}[b.state]
    dawn = ("%d:%02d" % (left // 60, left % 60), (220, 222, 236)) if left > 0 else ("soon", (255, 220, 140))
    wx = n.weather
    segs = [  # (long pieces, short pieces); "GAUGE" is the oil gauge
        ([(" LIGHTKEEPER ", None)], []),
        ([(" NIGHT ", HUD_LABEL), ("%d " % n.night, (236, 238, 246)), (wx, (170, 190, 220))],
         [(" N", HUD_LABEL), ("%d " % n.night, (236, 238, 246)), (WEATHER_SHORT[wx], (170, 190, 220))]),
        ([("  dawn ", HUD_LABEL), dawn], [(" ", None), dawn]),
        ([("  OIL ", WARN if low and blink else HUD_LABEL), "GAUGE"], [(" OIL ", WARN if low and blink else HUD_LABEL), "GAUGE"]),
        ([("  HORN ", HUD_LABEL), horn], [(" HORN ", HUD_LABEL), horn]),
        ([("  boat ", HUD_LABEL), boat], [(" boat ", HUD_LABEL), boat]),
        ([("  lifebuoys ", HUD_LABEL)] + buoys, [(" ", None)] + buoys),
        ([("  safe ", HUD_LABEL), ("%d" % n.saved, (150, 230, 170))], []),
        ([("  score ", HUD_LABEL), ("%d " % n.score, (240, 220, 140))], [(" ", None), ("%d" % n.score, (240, 220, 140))]),
    ]

    def width(pieces):
        return sum(oil_n if p == "GAUGE" else len(p[0]) for p in pieces)

    right = " ? help "
    choice = [s[0] for s in segs]
    for i in (0, 7, 2, 1, 4, 5, 6, 8, 3):     # shorten the least important first
        if sum(width(p) for p in choice) + len(right) <= cols:
            break
        choice[i] = segs[i][1]
    if sum(width(p) for p in choice) > cols:
        oil_n = 5
    cv.put(0, r, " " * cols, HUD_LABEL, HUD_BG)
    x = 0
    for i, pieces in enumerate(choice):
        for p in pieces:
            if p == "GAUGE":
                if n.refill > 0:
                    x = gauge(cv, x, r, n.oil / tank, oil_n, (120, 190, 255))
                else:
                    x = gauge(cv, x, r, n.oil / tank, oil_n, WARN if low else OIL_COL)
            elif i == 0:
                cv.put(x, r, p[0], (16, 14, 10), OIL_COL)
                x += len(p[0])
            else:
                cv.put(x, r, p[0], p[1] or HUD_LABEL, HUD_BG)
                x += len(p[0])
    if x + len(right) <= cols:
        cv.put(cols - len(right), r, right, HUD_LABEL, HUD_BG)
    for i, (s, _) in enumerate([] if (n.dawn or n.over) else n.msgs[-2:]):
        s = s if len(s) <= cols - 4 else s[:cols - 7] + "..."
        alarm = "aground" in s or "lost" in s or "out of oil" in s
        cv.center(i, " %s " % s, (255, 236, 230) if alarm else (236, 236, 240), (70, 18, 22) if alarm else (14, 16, 30))


HELP_SOLO = [
    "LIGHTKEEPER - keys (one keeper)",
    "",
    "Left / Right  (A / D)    turn the beam (hold to turn faster)",
    "Up / Down  (W / S)       focus: narrow reaches far, wide lights near",
    "Space                    horn: ships nearby slow down and see their way",
    "R                        refill the oil (the light is off for a moment)",
    "B                        send the rescue boat to a wreck",
    "",
    "Ships in your light steer clear of the reefs; ships in the dark sail",
    "on blindly - a blinking red ! warns of one heading for rock.",
    "Wrecks fire red flares - rescue the crew before time runs out.",
    "The rescue boat is slow in the dark: keep it in the light.",
    "",
    "Esc / P                  pause menu (Q there: quit, M: sound on / off)",
    "?                        this help",
    "",
    "Auto mode: the game plays itself (Space pause, +/- speed, Esc stop)",
]
HELP_COOP = [
    "LIGHTKEEPER - keys (two keepers)",
    "",
    "Keeper (arrows):   Left / Right turn the beam   Up / Down focus",
    "                   Space horn   R refill the oil",
    "Rescue boat (WASD): steer it to a wreck, wait a moment beside it,",
    "                   then bring the crew home to the jetty.",
    "",
    "The boat is slower in the dark - the keeper should light its way.",
    "",
    "Esc / P            pause menu (Q there: quit, M: sound on / off)",
    "?                  this help",
    "",
    "Auto mode: the game plays itself (Space pause, +/- speed, Esc stop)",
]
PAUSE = ["P A U S E D", "", "Esc / P / Enter   continue", "?                 help", "M                 sound on / off",
         "Q                 quit to the menu"]


# =============================================================================================
# Game flow
# =============================================================================================
class Campaign:
    """Night after night until the lifebuoys are gone."""

    def __init__(self, keepers, W, H, seed=None):
        self.keepers = keepers
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.W, self.H = W, H
        self.up = {}
        self.lives, self.score = 3, 0
        self.night_no = 0
        self.next_night()

    def next_night(self):
        self.night_no += 1
        self.n = Night(self.W, self.H, self.seed, self.night_no, self.keepers, self.up, self.lives, self.score)
        self.p = Painter(self.n)
        self.offer = random.Random(self.seed + self.night_no).sample(UPGRADES, 3)
        self.pick = 0

    def take_upgrade(self):
        key = self.offer[self.pick][0]
        if key == "buoy":
            self.lives = min(5, self.n.lives + 1)
        else:
            self.up[key] = self.up.get(key, 0) + 1
            self.lives = self.n.lives
        self.score = self.n.score
        self.next_night()


def render_dawn(cv, camp):
    """The dawn screen: the night's tally, then three improvements - the chosen one clearly highlighted."""
    n = camp.n
    bg, fg, dim, gold = (36, 26, 30), (240, 236, 224), (176, 160, 156), (255, 214, 120)
    stats = [("ships safe in harbour", "%d" % n.saved), ("ran aground", "%d" % n.wrecks),
             ("sailors rescued", "%d" % n.rescued), ("score", "%d" % n.score)]
    opts = ["%-18s %s" % (name, desc) for _, name, desc in camp.offer]
    inner = max([len(o) + 4 for o in opts] + [36])
    w = inner + 4
    h = 9 + len(stats) + len(opts)
    x0 = max(0, (cv.cols - w) // 2)
    y0 = max(0, (cv.rows - 1 - h) // 2)
    for j in range(h):
        cv.put(x0, y0 + j, " " * w, fg, bg)
    cv.put(x0, y0, " " * w, (30, 20, 10), (240, 180, 90))          # a dawn-coloured header band
    cv.center(y0, "D A W N  -  night %d survived" % n.night, (30, 20, 10), (240, 180, 90), col0=x0, width=w)
    y = y0 + 2
    for label, val in stats:
        cv.put(x0 + 4, y, label, dim, bg)
        cv.put(x0 + w - 4 - len(val), y, val, gold if label == "score" else fg, bg)
        y += 1
    y += 1
    cv.put(x0 + 4, y, "Choose an improvement for the lighthouse:", fg, bg)
    y += 2
    for i, o in enumerate(opts):
        if i == camp.pick:
            cv.put(x0 + 2, y, (" > " + o).ljust(w - 4), (30, 20, 10), gold)
        else:
            cv.put(x0 + 2, y, ("   " + o).ljust(w - 4), dim, bg)
        y += 1
    cv.put(x0 + 4, y + 1, "Up / Down choose   Enter take it", (150, 140, 136), bg)


def render_over(cv, camp, record, auto=False):
    n = camp.n
    lines = ["T H E   L I G H T   G O E S   O U T", "", "You kept the light for %d night%s." % (
        n.night - 1, "" if n.night == 2 else "s") if n.night > 1 else "The first night was too much.", "",
        "final score  %d" % n.score]
    if record:
        lines += ["", "** NEW RECORD **"]
    lines += ["", "a new watch begins in a moment   Esc: menu" if auto else "Enter: a new watch   Esc / Q: menu"]
    w = max(len(l) for l in lines) + 4
    cv.box(max(0, (cv.cols - w) // 2), max(0, cv.rows // 2 - len(lines) // 2 - 1), [l.center(w - 4) for l in lines],
           (240, 240, 246), (30, 16, 24))


def map_size(cols, rows):
    return max(60, min(cols, 200)), max(36, min((rows - 1) * 2, 110))


class TitleDemo:
    def __init__(self, cols, rows):
        W, H = map_size(cols, rows)
        self.size = (cols, rows)
        self.n = Night(W, H, 11, 2)
        self.n.quiet = True
        self.n.msgs = []
        self.p = Painter(self.n)
        self.n.half = 0.2

    def frame(self, cols, rows, dt, help_, sel):
        if (cols, rows) != self.size:
            self.__init__(cols, rows)
        n = self.n
        n.spin = 0.55
        n.oil = 100
        n.update(dt)
        n.msgs = []
        n.lives = 3
        n.over = n.dawn = False
        if n.t > n.length * 0.6:      # keep the demo going forever
            n.t = 10
            n.schedule = sorted(n.rnd.uniform(11, 40) for _ in range(4))
            n.ships = [s for s in n.ships if s.state == "sailing"]
        cv = render(n, self.p, cols, rows, title_mode=True)
        best = load_scores().get(GAME, {})
        rec = " / ".join("%s %d" % (m, v) for m, v in sorted(best.items()))
        title_screen(cv, "LIGHTKEEPER", "one beam, many ships, a long night",
                     ["One keeper (solo)", "Two keepers (co-op: the second steers the rescue boat)", AUTO_LABEL], sel,
                     "best: " + rec if rec else None, help_lines=HELP_COOP if sel == 1 else HELP_SOLO,
                     show_help=help_, dim=0.4)
        return cv


# =============================================================================================
# Auto mode: a keeper bot runs the light, the horn, the oil and the rescue boat, night after night
# =============================================================================================
STEP = 1 / 40          # the fixed simulation step of auto mode (and of the balance runs)
THINK = 6              # the bot decides every 6 steps (0.15 s) - quick, but not superhuman
UPGRADE_ORDER = ["tank", "pier", "boat", "buoy", "lens", "gear", "horn"]   # the bot's taste (from the balance runs)


def bot_upgrade(camp):
    """The bot's pick at dawn: a lifebuoy when it is down to its last one, otherwise its favourite."""
    keys = [o[0] for o in camp.offer]
    if "buoy" in keys and camp.n.lives <= 1:
        return keys.index("buoy")
    return min(range(len(keys)), key=lambda i: UPGRADE_ORDER.index(keys[i]))


class AutoKeeper:
    """One auto-mode watch: the real campaign (real nights, HUD, sound) with the keeper bot at the controls."""

    def __init__(self, W, H, seed=None, quiet=False):
        self.camp = Campaign(1, W, H, seed)
        self.quiet = quiet
        self.camp.n.quiet = quiet
        self.steps = 0
        self.wait = 0.0        # game seconds on the dawn / end screen

    def step(self):
        """One fixed step. Returns 'over' once the end box has been shown for ~3 s (then start a new watch)."""
        camp = self.camp
        n = camp.n
        if n.over:
            self.wait += STEP
            return "over" if self.wait > 3.0 else None
        if n.dawn:
            if self.wait == 0.0:
                camp.pick = bot_upgrade(camp)
            self.wait += STEP
            if self.wait > 3.0:
                if not self.quiet:
                    SND.play("upgrade")
                camp.take_upgrade()
                camp.n.quiet = self.quiet
                self.wait = 0.0
            return None
        if self.steps % THINK == 0:
            keeper(n)
        self.steps += 1
        n.update(STEP)
        return None


def run_auto(term, seconds=None, headless=None):
    """Auto mode until Esc. headless=(cols, rows) runs without a terminal at x8 for `seconds` (self-test).
    Never records a score."""
    auto = AutoMode(8.0 if headless else 1.0)
    t_end = time.time() + seconds if seconds else None
    watches, nights = 0, 0
    while True:
        cols, rows = headless or term.size()
        ak = AutoKeeper(*map_size(cols, rows - 1), quiet=bool(headless))
        last = time.time()
        done = False
        while not done:
            now = time.time()
            if t_end and now > t_end:
                return watches, nights + ak.camp.night_no
            if not headless:
                for k in term.keys(0):
                    a = auto.key(k)
                    if a == "stop":
                        return watches, nights + ak.camp.night_no
                    if a == "sound":
                        if SND.toggle():
                            SND.play("sound_on")
            for _ in range(auto.steps(1 / 30 if headless else min(0.1, now - last), STEP)):
                if ak.step() == "over":
                    done = True
                    break
            last = now
            if headless:
                continue
            cols, rows = term.size()
            if cols < 70 or rows < 22:
                term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (70x22).")
                time.sleep(0.2)
                continue
            term.write(auto_frame(ak, auto, cols, rows).emit())
            time.sleep(max(0.0, 1 / 30 - (time.time() - now)))
        watches += 1
        nights += ak.camp.night_no


def auto_frame(ak, auto, cols, rows):
    camp = ak.camp
    n = camp.n
    cv = render(n, camp.p, cols, rows)
    if n.dawn:
        render_dawn(cv, camp)
    if n.over:
        render_over(cv, camp, None, auto=True)
    auto.banner(cv, row=rows - 2, extra=("night %d" % n.night) if cols >= 100 else "")
    return cv


def main():
    with Terminal() as term:
        cols, rows = term.size()
        demo = TitleDemo(cols, rows)
        sel = 0
        while True:
            help_, go = False, False
            last = time.time()
            while not go:
                now = time.time()
                cols, rows = term.size()
                if cols < 70 or rows < 22:
                    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (70x22).")
                    term.keys(0.3)
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
                        sel = (sel - 1) % 3
                    elif k in ("down", "s"):
                        sel = (sel + 1) % 3
                    elif k in ("1", "2", "3"):
                        sel = int(k) - 1
                    elif k in ("enter", " "):
                        go = True
            if sel == 2:
                run_auto(term)
                continue
            keepers = sel + 1
            mode = "solo" if keepers == 1 else "co-op"
            while True:                                    # one watch; Enter on the end screen starts another
                camp = Campaign(keepers, *map_size(cols, rows))
                last = time.time()
                record = None
                back = again = False
                while not (back or again):
                    now = time.time()
                    n = camp.n
                    for k in term.keys(0):
                        if n.over:
                            if k in ("q", "esc"):
                                back = True
                            elif record is not None and k in ("enter", " "):
                                again = True
                            continue
                        if n.dawn:
                            if k in ("up", "w"):
                                camp.pick = (camp.pick - 1) % 3
                                SND.play("pick")
                            elif k in ("down", "s"):
                                camp.pick = (camp.pick + 1) % 3
                                SND.play("pick")
                            elif k in ("enter", " "):
                                SND.play("upgrade")
                                camp.take_upgrade()
                                n = camp.n
                            elif k in ("q", "esc"):
                                back = True
                            continue
                        a = shared_key(k, n.paused, pause_keys=("esc", "p", "q"))
                        if a == "pause":
                            n.paused = True
                        elif a == "resume":
                            n.paused = n.help = False
                        elif a == "quit":
                            back = True
                        elif a == "sound":
                            if SND.toggle():
                                SND.play("sound_on")
                        elif a == "help":
                            n.help = not n.help
                            n.paused = True
                        elif a is None:
                            n.key(k)
                    n.update(min(0.1, now - last))
                    last = now
                    if n.over and record is None:
                        record = submit(GAME, mode, n.score)
                    cols, rows = term.size()
                    if cols < 70 or rows < 22:
                        term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (70x22).")
                        time.sleep(0.2)
                        continue
                    cv = render(n, camp.p, cols, rows)
                    if n.paused:
                        overlay(cv, (HELP_COOP if keepers == 2 else HELP_SOLO) if n.help else PAUSE + ["", SND.label()])
                    if n.dawn:
                        render_dawn(cv, camp)
                    if n.over:
                        render_over(cv, camp, record)
                    term.write(cv.emit())
                    time.sleep(max(0.0, 1 / 30 - (time.time() - now)))
                if back:
                    break


# =============================================================================================
# Tests
# =============================================================================================
def keeper(n, asleep=False):
    """An attentive keeper for the tests: lights the ship in most danger, sends the boat, refills in time."""
    if asleep:
        return
    c = n.c
    lx, ly = c.lamp
    sailing = [s for s in n.ships if s.state == "sailing"]
    wrecks = [s for s in n.ships if s.state == "wrecked"]
    if wrecks and n.boat.state == "docked":
        n.key("b")
    if n.oil < n.tank() * 0.12 and n.refill <= 0:
        danger_now = any(s.aware <= 0 and danger(n, s) > 0.6 for s in sailing)
        if not danger_now or n.oil <= 0:
            n.key("r")
            return
    target = None
    if n.boat.state != "docked" and wrecks or n.boat.state == "carrying":
        target = n.boat
    worst = max(sailing, key=lambda s: danger(n, s) - (1.5 if s.aware > 0.8 else 0), default=None)
    if worst is not None and (target is None or danger(n, worst) > 0.5 and worst.aware <= 0.3):
        target = worst
    near = [s for s in sailing if math.hypot(s.x - lx, s.y - ly) < n.horn_radius() and s.aware <= 0 and danger(n, s) > 0.3]
    if len(near) >= 2 and n.horn_cd <= 0:
        n.key(" ")
    if target is None:
        return
    want = math.atan2(target.y - ly, target.x - lx)
    d = wrap(want - n.beam)
    dist = math.hypot(target.x - lx, target.y - ly)
    if abs(d) > 0.05:
        top = min(3.0 * (1.3 ** n.up.get("gear", 0)), abs(d) * 6)     # the geared mechanism turns faster
        for _ in range(1 + (abs(d) > 0.6) + (abs(d) > 1.2)):    # far off: hold the key (auto-repeat)
            if (d > 0 and n.spin < top) or (d < 0 and n.spin > -top):
                n.key("right" if d > 0 else "left")
    else:
        n.spin *= 0.3
    # focus: narrow for far targets, wide for near ones
    want_half = clamp(0.45 - (dist / n.range_max()) * 0.5, 0.14, 0.4)
    if n.half > want_half + 0.03:
        n.key("up")
    elif n.half < want_half - 0.03:
        n.key("down")


def danger(n, s):
    """How soon a ship in the dark is likely to hit something (0..1)."""
    c = n.c
    for k in range(1, 30):
        x, y = s.x + math.cos(s.h) * k, s.y + math.sin(s.h) * k
        a = c.at(x, y)
        if a == HARBOUR:
            return 0.0
        if a in (ROCK, LAND):
            return 1.0 - k / 30
    return 0.1


def play_nights(seed, nights=3, asleep=False, W=150, H=80, keepers=1):
    camp = Campaign(keepers, W, H, seed)
    results = []
    while True:
        n = camp.n
        steps = 0
        while not n.over and not n.dawn and steps < 40 * 600:
            if steps % 3 == 0:
                keeper(n, asleep)
            n.update(1 / 40)
            steps += 1
        results.append((n.night, n.saved, n.wrecks, n.rescued, n.lost, n.lives))
        if n.over or n.night >= nights:
            return camp, results
        camp.pick = 0
        camp.take_upgrade()


def selftest():
    t0 = time.time()
    for seed in range(20):              # every coast must be navigable from every spawn point
        for W, H in ((70, 42), (150, 80), (200, 110)):
            c = Coast(W, H, seed, 1 + seed % 6)
            assert len(c.spawns) > 20, "seed %d %dx%d: too few ways in" % (seed, W, H)
            assert c.nav[c.dock[1] * W + c.dock[0]] < 10 ** 6, "seed %d: the jetty is cut off" % seed
    wins, sleepy_losses = 0, 0
    for seed in range(8):
        camp, res = play_nights(seed, nights=3)
        survived = not camp.n.over
        wins += survived
        saved = sum(r[1] for r in res)
        assert saved > 0, "seed %d: the keeper saved nobody" % seed
        _, res2 = play_nights(seed, nights=1, asleep=True)
        sleepy_losses += res2[0][2] > res[0][2] or res2[0][4] > 0
    assert wins >= 6, "an attentive keeper survived 3 nights only %d of 8 times" % wins
    assert sleepy_losses >= 5, "the light hardly matters: a sleeping keeper did as well %d of 8 times" % (8 - sleepy_losses)
    # two keepers: the boat can be steered
    n = Night(120, 70, 3, 1, keepers=2)
    x0 = n.boat.x
    for _ in range(30):
        n.key("d")
        n.update(1 / 40)
    assert n.boat.x != x0, "the second player cannot steer the rescue boat"
    p = Painter(n)
    render(n, p, 120, 36)
    # auto mode: the real campaign at x8 for a few seconds headless, no score is ever submitted
    global submit
    real_submit, sent = submit, []
    submit = lambda *a, **k: sent.append(a)
    try:
        watches, nights = run_auto(None, seconds=6, headless=(120, 36))
    finally:
        submit = real_submit
    assert not sent, "auto mode submitted a score"
    assert nights >= 2, "auto mode did not get past the first night in 6 s at x8 (%d)" % nights
    auto = AutoMode()
    for _ in range(6):
        auto.key("+")
    assert auto.speed == 8.0 and auto.steps(1 / 30, STEP) >= 10, "x8 does not speed up the game"
    auto.key(" ")
    assert auto.steps(1 / 30, STEP) == 0, "auto mode keeps running while paused"
    ak = AutoKeeper(120, 70, seed=4, quiet=True)
    while not ak.camp.n.dawn and not ak.camp.n.over:
        ak.step()
    ak.camp.n.lives = 1
    assert ak.camp.offer[bot_upgrade(ak.camp)][0] == "buoy" or "buoy" not in [o[0] for o in ak.camp.offer]
    auto_frame(ak, auto, 120, 36).emit(True)
    ak.camp.n.over = True
    auto.key("?")
    auto_frame(ak, auto, 70, 22).emit(True)
    print("Self-test ok: 60 coasts navigable, the attentive keeper got through 3 nights %d of 8 times,"
          " a sleeping keeper did worse %d of 8 times, co-op boat steers, auto mode ran 6 s at x8 (%d nights,"
          " %d watches over), no score submitted (%.1fs)" % (wins, sleepy_losses, nights, watches, time.time() - t0))


def bench():
    camp, _ = play_nights(5, nights=1)
    n = Night(160, 88, 5, 4)
    for _ in range(400):
        keeper(n)
        n.update(1 / 40)
    p = Painter(n)
    for cols, rows in ((160, 45), (200, 56)):
        t = time.time()
        for _ in range(15):
            render(n, p, cols, rows).emit(True)
        print("frame %.1f ms at %dx%d" % ((time.time() - t) / 15 * 1000, cols, rows))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--bench" in sys.argv:
        bench()
    else:
        main()
