#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""
BLOCKFIRE - a first-person arena shooter in your terminal.

A raycasting 3D engine (textured walls, lit floor and ceiling, depth-sorted pixel-art sprites with a
z-buffer) painted with truecolor half-block pixels: two pixels per character cell.
Survive endless waves of combat bots.

Run:        python3 blockfire.py
Self-test:  python3 blockfire.py --selftest
Benchmark:  python3 blockfire.py --bench     (renders frames headless and prints the frame time)
"""
import math
import os
import random
import re
import select
import sys
import termios
import time
import tty
from collections import deque
import json


def _pixel_mode():
    """Pixel style: "fine" draws two pixels per cell with the half-block character; "smart" does that only
    where the two pixels differ clearly and fills near-equal pairs (gradients) with one background colour;
    "solid" draws one pixel per cell from background colour only. smart and solid are for terminals whose
    fonts leave gaps in half-blocks (macOS Terminal.app). ARCADE_PIXELS=fine|smart|solid overrides the setting
    kept in ~/.ascii_arcade_settings.json (switched with G in the ASCII ARCADE launcher)."""
    env = os.environ.get("ARCADE_PIXELS", "").strip().lower()
    if env in ("fine", "smart", "solid"):
        return env
    try:
        with open(os.path.expanduser("~/.ascii_arcade_settings.json")) as f:
            mode = json.load(f).get("pixels")
        return mode if mode in ("fine", "smart", "solid") else "fine"
    except (OSError, ValueError, AttributeError):
        return "fine"


PIXEL_MODE = _pixel_mode()
SOLID_PIXELS = PIXEL_MODE != "fine"   # some cells are filled with one colour instead of a half-block


def solid_cell(t, b):
    """One colour for a cell whose two pixels are t (top) and b (bottom), or None to keep the half-block.
    solid: the brighter pixel where they differ a lot (text, stars, outlines of light), else their mean.
    smart: their mean where they are nearly equal (no visible loss, no seam), else None."""
    if t == b:
        return t
    if not isinstance(t, tuple):      # palette indices (256 colours)
        return None if PIXEL_MODE == "smart" else t
    lt, lb = t[0] * 3 + t[1] * 6 + t[2], b[0] * 3 + b[1] * 6 + b[2]
    d = abs(lt - lb)
    if PIXEL_MODE == "smart":
        if d > 260:
            return None
    elif d > 600:
        return t if lt > lb else b
    return ((t[0] + b[0]) >> 1, (t[1] + b[1]) >> 1, (t[2] + b[2]) >> 1)

try:
    from arcadesound import Sound
except ImportError:
    class Sound:  # sound engine missing: stay silent
        available = enabled = False
        def __init__(self, *a, **k): pass
        def play(self, *a, **k): pass
        def toggle(self): return False
        def label(self): return "Sound: none"
        def stop(self): pass

FPS = 60
FOV_PLANE = 0.66          # camera plane length -> ~66 degree field of view
MOVE_SPEED = 3.6          # units per second
TURN_SPEED = 2.7          # radians per second
HOLD_MOVE = 0.20          # most terminals have no key-up events: a key press "holds" for this long
HOLD_TURN = 0.15
EASE = 14.0               # how fast movement and turning follow the keys (smooths out key-repeat gaps)
BRIDGE_TURN = 0.4         # share of turn speed while waiting for the keyboard's auto-repeat to start
BRIDGE_MOVE = 0.85        # the same for walking and strafing
PLAYER_R = 0.22
BOT_R = 0.25
BEST_FILE = os.path.expanduser("~/.blockfire_best")
FIRE_CD, PULSE_CD = 0.28, 0.6   # seconds between shots (bullets / pulse mode when out of ammo)
AMMO_PICK, AMMO_CLEAR = 15, 10    # ammo from a pickup / for clearing a wave (was 20 / 15: ammo never ran low)

# --- Sound effects (short and soft; the gunshot's gap is the fire interval) --------------------------------
SND = Sound("blockfire", {
    "shot": [dict(w="noise", f=6500, f2=700, d=0.09, v=0.5), dict(w="square", f=150, f2=48, d=0.08, v=0.5, at=0)],
    "pulse": [dict(w="noise", f=9000, d=0.012, v=0.35),                                   # dry click + weak zap
              dict(w="sine", f=950, f2=320, d=0.08, v=0.3, at=0.012)],
    "empty": [dict(w="square", f=1250, d=0.014, v=0.3), dict(w="noise", f=8000, d=0.02, v=0.25, at=0.05)],
    "hit": [dict(w="square", f=1500, f2=950, d=0.04, v=0.28, duty=0.25), dict(w="noise", f=5000, d=0.03, v=0.18, at=0)],
    "boom": [dict(w="noise", f=2600, f2=110, d=0.42, v=0.55), dict(w="square", f=120, f2=40, d=0.28, v=0.38, at=0)],
    "boom_big": [dict(w="noise", f=1900, f2=60, d=0.8, v=0.7), dict(w="square", f=90, f2=30, d=0.6, v=0.45, at=0),
                 dict(w="noise", f=420, f2=70, d=0.55, v=0.4, at=0.12)],
    "hurt": [dict(w="saw", f=320, f2=120, d=0.15, v=0.32), dict(w="noise", f=1300, d=0.08, v=0.28, at=0)],
    "eshot": [dict(w="square", f=920, f2=480, d=0.07, v=0.3, duty=0.25)],
    "health": [dict(w="tri", f=660, d=0.06, v=0.45), dict(w="tri", f=880, d=0.06, v=0.45),
               dict(w="tri", f=1320, d=0.15, v=0.45)],
    "ammo": [dict(w="square", f=330, d=0.04, v=0.3, duty=0.3), dict(w="noise", f=3500, d=0.03, v=0.25),
             dict(w="square", f=494, d=0.06, v=0.3, duty=0.3)],
    "alarm": [dict(w="square", f=700, f2=1050, d=0.22, v=0.26, duty=0.25, r="hold"),
              dict(w="square", f=700, f2=1050, d=0.22, v=0.26, duty=0.25, r="hold", at=0.3),
              dict(w="square", f=700, f2=1050, d=0.22, v=0.26, duty=0.25, r="lin", at=0.6)],
    "cleared": [dict(w="tri", f=523, d=0.1, v=0.45), dict(w="tri", f=659, d=0.1, v=0.45), dict(w="tri", f=784, d=0.1, v=0.45),
                dict(w="square", f=1047, d=0.4, v=0.3, duty=0.25, vib=(6, 0.2))],
    "death": [dict(w="saw", f=420, f2=55, d=1.0, v=0.38, r="lin"), dict(w="noise", f=1500, f2=80, d=0.9, v=0.45, at=0)],
    "start": [dict(w="square", f=440, d=0.06, v=0.3, duty=0.25), dict(w="square", f=880, d=0.14, v=0.3, duty=0.25)],
    "select": [dict(w="square", f=880, d=0.035, v=0.26, duty=0.25)],
})

# --- Arena -------------------------------------------------------------------
#  # concrete   B brick   T tech panel   M mossy stone
#  . floor   P player start   s bot spawn   h health   a ammo
MAP = [
    "################################",
    "#......#.......s........#......#",
    "#..P...#................#..h...#",
    "#......#....BB....BB....#......#",
    "#......#....BB....BB....T......#",
    "#..........................s...#",
    "#......#....BB....BB....T......#",
    "###.####....BB....BB....#......#",
    "#......#................####.###",
    "#..a...#.......a........#......#",
    "#......####TT....TT######......#",
    "#...........................s..#",
    "#..s....M..............M.......#",
    "#.......M..TTTT..TTTT..M...a...#",
    "#.......M..T........T..M.......#",
    "#######.M..T...h....T..M..######",
    "#.......M..T........T..M.......#",
    "#.......M..TTTT..TTTT..M.......#",
    "#..h....M..............M....s..#",
    "#..............................#",
    "#####.######BBBB..BBBB#####.####",
    "#......#..................#....#",
    "#..s...#....#..#..#..#....#.a..#",
    "#......#..................#....#",
    "#......#....#..#..#..#....#....#",
    "#...a..T..........s.......T....#",
    "#......T....#..#..#..#....T....#",
    "#......#..................#..h.#",
    "#......####......a.....####....#",
    "#..............................#",
    "#..s.........MMMM..........s...#",
    "################################",
]

# --- Bots ----------------------------------------------------------------------

# --- Bots ----------------------------------------------------------------------
BOT_TYPES = {
    "drone":    dict(hp=45,  speed=2.3, dmg=6,  cd=0.9, acc=0.62, size=0.80),
    "sentinel": dict(hp=75,  speed=1.9, dmg=9,  cd=1.2, acc=0.70, size=0.88),
    "brute":    dict(hp=150, speed=1.4, dmg=15, cd=1.6, acc=0.66, size=1.00),
}


def clamp(v, a, b):
    return a if v < a else b if v > b else v



# =============================================================================
# Game logic (no terminal needed -> testable headless)
# =============================================================================
class Bot:
    def __init__(self, kind, x, y, rnd):
        k = BOT_TYPES[kind]
        self.kind, self.k = kind, k
        self.x, self.y = x, y
        self.a = rnd.uniform(0, 2 * math.pi)
        self.hp = k["hp"]
        self.state = "hunt"
        self.path = []
        self.stuck = 0.0
        self.ghost = 0.0
        self.repath = 0.0
        self.cd = k["cd"] * rnd.uniform(0.5, 1.0)
        self.react = 0.0
        self.seen = False
        self.los_t = 0.0
        self.has_los = False
        self.last_seen = None
        self.strafe = 1
        self.strafe_t = 0.0
        self.flash = 0.0
        self.hit = 0.0
        self.dead_t = 0.0

    @property
    def alive(self):
        return self.state != "dead"


class Game:
    def __init__(self, seed=None):
        self.rnd = random.Random(seed)
        self.H = len(MAP)
        self.W = max(len(r) for r in MAP)
        self.grid = []
        self.spawns = []
        self.pickups = []
        start = (1.5, 1.5)
        for y, row in enumerate(MAP):
            out = []
            for x in range(self.W):
                c = row[x] if x < len(row) else '#'
                if x in (0, self.W - 1) or y in (0, self.H - 1):
                    c = c if c in "#BTM" else '#'
                if c == 'P':
                    start = (x + 0.5, y + 0.5)
                elif c == 's':
                    self.spawns.append((x + 0.5, y + 0.5))
                elif c in "ha":
                    self.pickups.append({"x": x + 0.5, "y": y + 0.5, "kind": c, "active": True,
                                         "t": 0.0, "temp": False})
                out.append(c if c in "#BTM" else '.')
            self.grid.append(out)
        self.start = start
        self.best = self.load_best()
        self.auto = False          # auto mode: never records a best score
        self.reset()

    def reset(self):
        self.px, self.py = self.start
        self.a = 0.0
        self.hp = 100.0
        self.ammo = 60
        self.max_ammo = 150
        self.kills = 0
        self.wave = 0
        self.bots = []
        self.spawn_queue = []
        self.spawn_t = 0.0
        self.inter = 3.0           # countdown until the next wave starts
        self.wave_t = -9.0         # when the current wave started (the renderer shows a banner)
        self.clear_t = -9.0        # when the last wave was cleared
        self.over = False
        self.t = 0.0
        self.hold = {"f": 0.0, "b": 0.0, "l": 0.0, "r": 0.0, "tl": 0.0, "tr": 0.0}
        self.bridge = dict(self.hold)   # a fresh key press keeps going (a bit slower) until auto-repeat starts
        self.fire_cd = 0.0
        self.muzzle = 0.0
        self.hitmark = 0.0
        self.dmg_flash = 0.0
        self.hurt_ang = 0.0
        self.hurt_t = 0.0
        self.moving = False
        self.smv = self.sst = self.str = 0.0   # eased move / strafe / turn
        self.bob = 0.0
        self.msgs = []
        self.fx = []              # events for the renderer: hits, kills, enemy shots
        self.paused = False
        self.show_map = True
        self.new_best = False
        for p in self.pickups:
            p["active"], p["t"] = True, 0.0
        self.pickups = [p for p in self.pickups if not p["temp"]]
        self.msg("Get ready. Bots inbound.")

    # --- helpers -------------------------------------------------------------
    @property
    def score(self):
        return self.kills * 100 + max(0, self.wave - 1) * 250

    def load_best(self):
        try:
            with open(BEST_FILE) as f:
                return int(f.read().strip() or 0)
        except (OSError, ValueError):
            return 0

    def save_best(self):
        if self.auto:
            return
        if self.score > self.best:
            self.best = self.score
            self.new_best = True
            try:
                with open(BEST_FILE, "w") as f:
                    f.write(str(self.best))
            except OSError:
                pass

    def msg(self, text, ttl=3.0):
        self.msgs.append([text, ttl])
        self.msgs = self.msgs[-3:]

    def solid(self, x, y):
        ix, iy = int(x), int(y)
        if ix < 0 or iy < 0 or ix >= self.W or iy >= self.H:
            return True
        return self.grid[iy][ix] != '.'

    def blocked(self, x, y, r):
        return (self.solid(x - r, y - r) or self.solid(x + r, y - r)
                or self.solid(x - r, y + r) or self.solid(x + r, y + r))

    def cast(self, px, py, rdx, rdy):
        """DDA raycast. Returns (perpendicular distance, side, wall char, wall x 0..1)."""
        mx, my = int(px), int(py)
        ddx = abs(1.0 / rdx) if rdx else 1e30
        ddy = abs(1.0 / rdy) if rdy else 1e30
        if rdx < 0:
            stx, sdx = -1, (px - mx) * ddx
        else:
            stx, sdx = 1, (mx + 1.0 - px) * ddx
        if rdy < 0:
            sty, sdy = -1, (py - my) * ddy
        else:
            sty, sdy = 1, (my + 1.0 - py) * ddy
        g, W, H = self.grid, self.W, self.H
        side = 0
        for _ in range(128):
            if sdx < sdy:
                sdx += ddx
                mx += stx
                side = 0
            else:
                sdy += ddy
                my += sty
                side = 1
            if mx < 0 or my < 0 or mx >= W or my >= H:
                return 40.0, side, '#', 0.0
            c = g[my][mx]
            if c != '.':
                if side == 0:
                    perp = sdx - ddx
                    wx = py + perp * rdy
                else:
                    perp = sdy - ddy
                    wx = px + perp * rdx
                return perp, side, c, wx - math.floor(wx)
        return 40.0, side, '#', 0.0

    def los(self, x0, y0, x1, y1):
        dx, dy = x1 - x0, y1 - y0
        n = int(math.hypot(dx, dy) / 0.2) + 1
        for i in range(1, n):
            t = i / n
            if self.solid(x0 + dx * t, y0 + dy * t):
                return False
        return True

    def path(self, sx, sy, tx, ty):
        start, goal = (int(sx), int(sy)), (int(tx), int(ty))
        if start == goal or self.grid[goal[1]][goal[0]] != '.':
            return []
        prev = {start: None}
        q = deque([start])
        while q:
            c = q.popleft()
            if c == goal:
                break
            x, y = c
            for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if n not in prev and self.grid[n[1]][n[0]] == '.':
                    prev[n] = c
                    q.append(n)
        if goal not in prev:
            return []
        out = []
        c = goal
        while c != start:
            out.append(c)
            c = prev[c]
        out.reverse()
        return out

    # --- input -------------------------------------------------------------------
    def press(self, action):
        if self.over or self.paused:
            return
        opposite = {"f": "b", "b": "f", "l": "r", "r": "l", "tl": "tr", "tr": "tl"}
        if action in self.hold:
            self.hold[opposite[action]] = 0.0
            self.bridge[opposite[action]] = 0.0
            self.hold[action] = HOLD_TURN if action in ("tl", "tr") else HOLD_MOVE
        elif action == "fire":
            self.fire()

    def aim_bot(self, ca, sa, wall_d=None):
        """The living bot a shot fired now would hit (or None)."""
        if wall_d is None:
            wall_d = self.cast(self.px, self.py, ca, sa)[0]
        best, best_d = None, 1e9
        for b in self.bots:
            if not b.alive:
                continue
            dx, dy = b.x - self.px, b.y - self.py
            along = dx * ca + dy * sa
            if along <= 0.1 or along >= wall_d or along >= best_d:
                continue
            if abs(-dx * sa + dy * ca) < 0.3 * b.k["size"] + 0.05:
                best, best_d = b, along
        return best

    def fire(self):
        if self.fire_cd > 0:
            return
        if self.ammo > 0:
            self.ammo -= 1
            dmg = self.rnd.uniform(28, 40)
            self.fire_cd = FIRE_CD
            SND.play("shot", 0.8, FIRE_CD - 0.02)
            if self.ammo == 0:
                SND.play("empty", 0.8)
        else:
            dmg = self.rnd.uniform(10, 14)
            self.fire_cd = PULSE_CD
            SND.play("pulse", 0.7, PULSE_CD - 0.02)
            if self.rnd.random() < 0.3:
                self.msg("Out of ammo - pulse mode. Find ammo (yellow ===).", 2.0)
        self.muzzle = 0.09
        ca, sa = math.cos(self.a), math.sin(self.a)
        wall_d = self.cast(self.px, self.py, ca, sa)[0]
        best, best_d = None, 1e9
        for b in self.bots:
            if not b.alive:
                continue
            dx, dy = b.x - self.px, b.y - self.py
            along = dx * ca + dy * sa
            if along <= 0.1:
                continue
            lateral = abs(-dx * sa + dy * ca)
            if lateral < 0.3 * b.k["size"] + 0.05 and along < wall_d and along < best_d:
                best, best_d = b, along
            if math.hypot(dx, dy) < 11 and b.state == "hunt":  # bots hear gunfire
                b.last_seen, b.repath = (self.px, self.py), 0.0
        if best:
            best.hp -= dmg
            best.hit = 0.12
            self.fx.append(("hit", best.x, best.y, best.k["size"]))
            self.hitmark = 0.15
            best.last_seen = (self.px, self.py)
            if best.hp <= 0:
                self.kill(best)
            else:
                SND.play("hit", 0.7)

    def kill(self, b):
        b.state = "dead"
        b.dead_t = 3.0
        self.fx.append(("kill", b.x, b.y, b.kind))
        SND.play("boom_big" if b.kind == "brute" else "boom", 0.9, 0.08)
        self.kills += 1
        self.msg("%s down. +100" % b.kind.capitalize(), 2.0)
        if self.rnd.random() < 0.35:
            self.pickups.append({"x": b.x, "y": b.y, "kind": self.rnd.choice("ha"), "active": True,
                                 "t": 0.0, "temp": True})

    # --- update ------------------------------------------------------------------
    def update(self, dt):
        dt = min(dt, 0.1)
        for m in self.msgs:
            m[1] -= dt
        self.msgs = [m for m in self.msgs if m[1] > 0]
        if self.over or self.paused:
            return
        self.t += dt
        self.fire_cd -= dt
        self.muzzle -= dt
        self.hitmark -= dt
        self.dmg_flash -= dt
        self.hurt_t -= dt
        self.update_player(dt)
        self.update_waves(dt)
        for b in self.bots:
            self.update_bot(b, dt)
        self.bots = [b for b in self.bots if b.alive or b.dead_t > 0]
        self.update_pickups(dt)
        if self.hp <= 0:
            self.hp = 0
            self.over = True
            self.save_best()
            SND.play("death")

    def update_player(self, dt):
        h, br = self.hold, self.bridge

        def on(a):
            return 1.0 if h[a] > 0 else (BRIDGE_TURN if a in ("tl", "tr") else BRIDGE_MOVE) if br[a] > 0 else 0.0
        mv = on("f") - on("b")
        st = on("r") - on("l")
        tr = on("tr") - on("tl")
        for k in h:
            h[k] = max(0.0, h[k] - dt)
            br[k] = max(0.0, br[k] - dt)
        e = min(1.0, dt * EASE)
        self.smv += (mv - self.smv) * e
        self.sst += (st - self.sst) * e
        self.str += (tr - self.str) * e
        for name in ("smv", "sst", "str"):
            if abs(getattr(self, name)) < 0.02:
                setattr(self, name, 0.0)
        mv, st, tr = self.smv, self.sst, self.str
        self.a = (self.a + tr * TURN_SPEED * dt) % (2 * math.pi)
        ca, sa = math.cos(self.a), math.sin(self.a)
        vx = ca * mv - sa * st
        vy = sa * mv + ca * st
        n = math.hypot(vx, vy)
        self.moving = n > 0.05
        if n > 0:
            k = min(1.0, n) / n
            vx, vy = vx * k * MOVE_SPEED * dt, vy * k * MOVE_SPEED * dt
            self.bob += dt * 9
            nx = self.px + vx
            if not self.blocked(nx, self.py, PLAYER_R) and not self.bot_near(nx, self.py, 0.55):
                self.px = nx
            ny = self.py + vy
            if not self.blocked(self.px, ny, PLAYER_R) and not self.bot_near(self.px, ny, 0.55):
                self.py = ny

    def bot_near(self, x, y, r, skip=None):
        for b in self.bots:
            if b is not skip and b.alive and abs(b.x - x) < r and abs(b.y - y) < r:
                return True
        return False

    def update_waves(self, dt):
        if self.inter > 0:
            self.inter -= dt
            if self.inter <= 0:
                self.wave += 1
                n = 2 + self.wave
                kinds = []
                # brutes grow from 21% (wave 3) to at most 40% (wave 10+); sentinels keep a steady 30% share
                # (before, the brute share grew without limit and pushed sentinels out entirely from wave 11)
                brute = min(0.40, 0.12 + 0.03 * self.wave) if self.wave >= 3 else 0.0
                for i in range(n):
                    r = self.rnd.random()
                    if r < brute:
                        kinds.append("brute")
                    elif self.wave >= 2 and r < brute + 0.30:
                        kinds.append("sentinel")
                    else:
                        kinds.append("drone")
                self.spawn_queue = kinds
                self.spawn_t = 0.0
                self.wave_t = self.t
                self.msg("WAVE %d - %d bots incoming" % (self.wave, n), 4.0)
                SND.play("alarm", 0.8)
            return
        alive = sum(1 for b in self.bots if b.alive)
        self.spawn_t -= dt
        if self.spawn_queue and self.spawn_t <= 0 and alive < 8:
            if self.spawn_bot(self.spawn_queue[0]):
                self.spawn_queue.pop(0)
                self.spawn_t = 1.3
        if not self.spawn_queue and alive == 0:
            self.hp = min(100.0, self.hp + 25)
            self.ammo = min(self.max_ammo, self.ammo + AMMO_CLEAR)
            self.clear_t = self.t
            self.msg("WAVE %d CLEARED  +25 HP  +%d ammo" % (self.wave, AMMO_CLEAR), 4.0)
            SND.play("cleared")
            self.inter = 4.0

    def spawn_bot(self, kind):
        opts = []
        for (x, y) in self.spawns:
            d = math.hypot(x - self.px, y - self.py)
            if d > 7 and not self.bot_near(x, y, 1.2):
                opts.append((not self.los(x, y, self.px, self.py), d, (x, y)))
        if not opts:
            return False
        opts.sort(reverse=True)
        x, y = self.rnd.choice(opts[:3])[2]
        self.bots.append(Bot(kind, x, y, self.rnd))
        return True

    def move_bot(self, b, vx, vy):
        """Move with wall sliding. A bot stuck behind another bot briefly 'ghosts' through it."""
        ox, oy = b.x, b.y
        crowd = b.ghost <= 0
        nx = b.x + vx
        if not self.blocked(nx, b.y, BOT_R) and not (crowd and self.bot_near(nx, b.y, 0.45, b)) \
                and math.hypot(nx - self.px, b.y - self.py) > 0.6:
            b.x = nx
        ny = b.y + vy
        if not self.blocked(b.x, ny, BOT_R) and not (crowd and self.bot_near(b.x, ny, 0.45, b)) \
                and math.hypot(b.x - self.px, ny - self.py) > 0.6:
            b.y = ny
        return (b.x, b.y) != (ox, oy)

    def follow_path(self, b, dt, speed):
        if not b.path:
            return True
        cx, cy = b.path[0]
        tx, ty = cx + 0.5, cy + 0.5
        dx, dy = tx - b.x, ty - b.y
        d = math.hypot(dx, dy)
        if d < 0.15:
            b.path.pop(0)
            return not b.path
        b.a = math.atan2(dy, dx)
        step = min(d, speed * dt)
        if self.move_bot(b, dx / d * step, dy / d * step):
            b.stuck = 0.0
        else:
            b.stuck += dt
            if b.stuck > 0.6:
                b.ghost, b.stuck = 0.8, 0.0
        return False

    def update_bot(self, b, dt):
        if not b.alive:
            b.dead_t -= dt
            return
        k = b.k
        b.hit -= dt
        b.flash -= dt
        b.cd -= dt
        b.repath -= dt
        b.ghost -= dt
        dx, dy = self.px - b.x, self.py - b.y
        dist = math.hypot(dx, dy)
        b.los_t -= dt
        if b.los_t <= 0:
            b.los_t = 0.15 + self.rnd.random() * 0.1
            b.has_los = dist < 18 and self.los(b.x, b.y, self.px, self.py)
        if b.has_los:
            if not b.seen:
                b.seen = True
                b.react = self.rnd.uniform(0.45, 0.85)
            b.last_seen = (self.px, self.py)
            b.state = "attack"
        else:
            b.seen = False
            if b.state == "attack":
                b.state, b.repath = "hunt", 0.0

        if b.state == "attack":
            b.a = math.atan2(dy, dx)
            want = 1 if dist > 7 else (-1 if dist < 3 else 0)
            b.strafe_t -= dt
            if b.strafe_t <= 0:
                b.strafe = self.rnd.choice((-1, 0, 1))
                b.strafe_t = self.rnd.uniform(0.7, 1.8)
            ca, sa = math.cos(b.a), math.sin(b.a)
            vx = ca * want * 0.8 - sa * b.strafe * 0.7
            vy = sa * want * 0.8 + ca * b.strafe * 0.7
            sp = k["speed"] * dt
            self.move_bot(b, vx * sp, vy * sp)
            b.react -= dt
            if b.react <= 0 and b.cd <= 0:
                self.bot_fire(b, dist)
        elif b.state == "hunt":
            # head for where the player was last seen, otherwise for a noisy guess of
            # the player's position (the arena's motion sensors feed the bots)
            if b.repath <= 0:
                if b.last_seen:
                    tx, ty = b.last_seen
                else:
                    tx = clamp(self.px + self.rnd.uniform(-4, 4), 1.5, self.W - 1.5)
                    ty = clamp(self.py + self.rnd.uniform(-4, 4), 1.5, self.H - 1.5)
                    if self.solid(tx, ty):
                        tx, ty = self.px, self.py
                b.path = self.path(b.x, b.y, tx, ty)
                b.repath = 0.7 if b.last_seen else 1.5
            if self.follow_path(b, dt, k["speed"] * (1.0 if b.last_seen else 0.75)):
                b.last_seen = None
                b.repath = 0.0

    def bot_fire(self, b, dist):
        k = b.k
        b.cd = k["cd"] * self.rnd.uniform(0.8, 1.25)
        b.flash = 0.1
        acc = k["acc"] - dist * 0.025 - (0.15 if self.moving else 0.0)
        hit = self.rnd.random() < max(0.08, acc)
        self.fx.append(("shot", b, hit))
        SND.play("eshot", max(0.12, 0.45 - dist * 0.025), 0.1)   # quieter than yours, fainter far away
        if hit:
            self.hp -= k["dmg"] * self.rnd.uniform(0.8, 1.2)
            self.dmg_flash = 0.25
            self.hurt_ang = math.atan2(b.y - self.py, b.x - self.px)
            self.hurt_t = 0.8
            if self.hp > 0:
                SND.play("hurt", 0.8, 0.2)

    def update_pickups(self, dt):
        for p in self.pickups:
            if not p["active"]:
                p["t"] -= dt
                if p["t"] <= 0:
                    p["active"] = True
                continue
            if abs(p["x"] - self.px) < 0.6 and abs(p["y"] - self.py) < 0.6:
                if p["kind"] == "h" and self.hp < 100:
                    self.hp = min(100.0, self.hp + 30)
                    self.msg("+30 health", 2.0)
                    SND.play("health", 0.8)
                elif p["kind"] == "a" and self.ammo < self.max_ammo:
                    self.ammo = min(self.max_ammo, self.ammo + AMMO_PICK)
                    self.msg("+%d ammo" % AMMO_PICK, 2.0)
                    SND.play("ammo", 0.8)
                else:
                    continue
                p["active"] = False
                p["t"] = 25.0
        self.pickups = [p for p in self.pickups if p["active"] or not p["temp"]]


# =============================================================================
# Auto mode: a bot that plays with the same controls as a person (held keys, turn speed, reaction time)
# =============================================================================
def angdiff(a, b):
    return (a - b + math.pi) % (2 * math.pi) - math.pi


class AutoPilot:
    """Plays BLOCKFIRE like a decent human with a kitty-protocol keyboard (keys held and released):
    it sees what the minimap shows, walks the arena by BFS paths, turns at the normal turn speed, needs a
    moment to react to a new target, aims with a little wobble, strafes while fighting and goes for
    health and ammo when low. No cheats: it only holds keys and presses fire."""
    MOVES = ("f", "b", "l", "r")

    def __init__(self, g, seed=None, skill=1.0):
        self.g = g
        self.rnd = random.Random(seed)
        self.skill = skill                      # 1.0 = decent player; lower = slower and sloppier
        self.target = None
        self.react = 0.0
        self.err, self.err_t = 0.0, 0.0
        self.strafe, self.strafe_t = 1, 0.0
        self.goal, self.path, self.repath = None, [], 0.0
        self.stuck_t, self.last_pos, self.unstick = 0.0, (g.px, g.py), 0.0
        self.unstick_dir = 0.0

    # --- perception -------------------------------------------------------------------------------------
    def visible(self):
        g = self.g
        best, best_d = None, 1e9
        for b in g.bots:
            if not b.alive:
                continue
            d = math.hypot(b.x - g.px, b.y - g.py)
            if d < 16 and g.los(g.px, g.py, b.x, b.y):
                # prefer what is in front (turning costs time) and near
                cost = d + abs(angdiff(math.atan2(b.y - g.py, b.x - g.px), g.a)) * 3
                if b is self.target:
                    cost -= 2.5                 # stick with the current target
                if cost < best_d:
                    best, best_d = b, cost
        return best

    def pickup_goal(self, kind, need):
        g = self.g
        if not need:
            return None
        best, best_d = None, 1e9
        for p in g.pickups:
            if p["active"] and p["kind"] == kind:
                d = math.hypot(p["x"] - g.px, p["y"] - g.py)
                if d < best_d:
                    best, best_d = p, d
        return (best["x"], best["y"]) if best else None

    def choose_goal(self, fighting):
        g = self.g
        calm = g.inter > 0 or (not g.spawn_queue and not any(b.alive for b in g.bots))
        goal = (self.pickup_goal("h", g.hp < (45 if fighting else 60) or (calm and g.hp < 85))
                or self.pickup_goal("a", g.ammo < 15 or (calm and g.ammo < g.max_ammo - 30)))
        if goal or fighting:
            return goal
        alive = [b for b in g.bots if b.alive]
        if alive:                               # hunt the nearest bot shown on the minimap
            b = min(alive, key=lambda b: math.hypot(b.x - g.px, b.y - g.py))
            return (b.x, b.y)
        return None

    # --- one decision step --------------------------------------------------------------------------------
    def step(self, dt):
        g = self.g
        if g.over:
            return
        want = set()
        tgt = self.visible()
        if tgt is not self.target:
            if tgt is not None and (self.target is None or not self.target.alive):
                self.react = self.rnd.uniform(0.22, 0.4) / self.skill
            elif tgt is not None:
                self.react = max(self.react, 0.12 / self.skill)
            self.target = tgt
        self.react -= dt
        self.err_t -= dt
        if self.err_t <= 0:                     # hand wobble, re-rolled a few times a second
            self.err_t = self.rnd.uniform(0.25, 0.5)
            self.err = self.rnd.gauss(0, 0.035 / self.skill)

        self.repath -= dt
        goal = self.choose_goal(tgt is not None)
        if goal is not None:
            cell = (int(goal[0]), int(goal[1]))
            if cell != self.goal or self.repath <= 0 or not self.path:
                self.goal, self.repath = cell, 0.5
                self.path = g.path(g.px, g.py, goal[0], goal[1])
        else:
            self.goal, self.path = None, []
        while self.path and math.hypot(self.path[0][0] + 0.5 - g.px, self.path[0][1] + 0.5 - g.py) < 0.3:
            self.path.pop(0)

        move = None                             # world direction to walk in (radians) or None
        if self.path:
            wx, wy = self.path[0][0] + 0.5, self.path[0][1] + 0.5
            move = math.atan2(wy - g.py, wx - g.px)
        elif goal is not None and math.hypot(goal[0] - g.px, goal[1] - g.py) > 0.2:
            move = math.atan2(goal[1] - g.py, goal[0] - g.px)

        if tgt is not None:
            dx, dy = tgt.x - g.px, tgt.y - g.py
            d = math.hypot(dx, dy)
            ta = math.atan2(dy, dx)
            face = ta + self.err
            if move is None:                    # fight: strafe to dodge, keep a medium range
                self.strafe_t -= dt
                if self.strafe_t <= 0:
                    self.strafe = self.rnd.choice((-1, 1, 1, -1, 0))
                    self.strafe_t = self.rnd.uniform(0.5, 1.3)
                rng = 1 if d > 7 else (-1 if d < 3.5 else 0)
                vx = math.cos(ta) * rng - math.sin(ta) * self.strafe
                vy = math.sin(ta) * rng + math.cos(ta) * self.strafe
                if vx or vy:
                    move = math.atan2(vy, vx)
            tol = math.atan2(0.3 * tgt.k["size"] + 0.05, max(d, 0.5)) * 0.85
            if self.react <= 0 and abs(angdiff(g.a, face)) < tol and g.fire_cd <= 0:
                if g.ammo > 0 or d < 9:         # pulse shots only when close
                    g.press("fire")
        elif move is not None:
            face = move
        else:
            face = g.a + 0.6                    # nothing to do: look around

        # unstick: walked into a corner or a bot for a while -> sidestep
        if self.unstick > 0:
            self.unstick -= dt
            move = self.unstick_dir
        elif move is not None:
            moved = math.hypot(g.px - self.last_pos[0], g.py - self.last_pos[1])
            self.stuck_t = self.stuck_t + dt if moved < 0.4 * MOVE_SPEED * dt else 0.0
            if self.stuck_t > 0.5:
                self.stuck_t, self.unstick, self.repath = 0.0, 0.35, 0.0
                self.unstick_dir = move + self.rnd.choice((-1.6, 1.6, math.pi))
                self.strafe = -self.strafe
        self.last_pos = (g.px, g.py)

        # turning: hold the turn key, let go early enough that the eased turn stops on target
        diff = angdiff(face, g.a)
        brake = abs(g.str) * TURN_SPEED / EASE + 0.02
        if diff > brake:
            want.add("tr")
        elif diff < -brake:
            want.add("tl")
        if move is not None:
            rel = angdiff(move, g.a)
            c, s = math.cos(rel), math.sin(rel)
            if c > 0.38:
                want.add("f")
            elif c < -0.38:
                want.add("b")
            if s > 0.38:
                want.add("r")
            elif s < -0.38:
                want.add("l")
        for a in g.hold:                        # like held keys with key-release events
            if a in want:
                g.hold[a] = max(g.hold[a], 0.25)
            else:
                g.hold[a] = 0.0
            g.bridge[a] = 0.0


# =============================================================================
# Art: textures and pixel sprites
# =============================================================================
FOG = (6, 7, 12)
LEVELS = 24               # distance shading steps
LVL_PER_UNIT = 1.4


def mix(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def shade(c, k):
    return (clamp(int(c[0] * k), 0, 255), clamp(int(c[1] * k), 0, 255), clamp(int(c[2] * k), 0, 255))


def fogged(c, lvl, emissive=False, floor=0.0):
    d = lvl / LVL_PER_UNIT
    k = max(floor, 1.0 / (1.0 + d * 0.16))
    if emissive:
        k = max(k, 0.8)
    return (int(c[0] * k + FOG[0] * (1 - k)) & 0xF8, int(c[1] * k + FOG[1] * (1 - k)) & 0xF8,
            int(c[2] * k + FOG[2] * (1 - k)) & 0xF8)


def make_wall_textures():
    """32x32 RGB wall textures, indexed [y * 32 + x], plus which texels glow."""
    rnd = random.Random(5)
    tex, glow = {}, {}

    def cl(c):
        return (clamp(int(c[0]), 0, 255), clamp(int(c[1]), 0, 255), clamp(int(c[2]), 0, 255))

    t = []  # brick: offset courses, mortar, per-brick tint, bevel
    tints = [rnd.uniform(0.82, 1.08) for _ in range(64)]
    for y in range(32):
        course, by = divmod(y, 8)
        off = 8 if course % 2 else 0
        for x in range(32):
            bx = (x + off) % 16
            if by == 7 or bx == 15:
                t.append(cl((66 + rnd.uniform(-6, 6),) * 3))
                continue
            k = tints[(course * 4 + (x + off) // 16) % 64] + rnd.uniform(-0.06, 0.05)
            hl = 1.18 if by == 0 or bx == 0 else 0.8 if by == 6 or bx == 14 else 1.0
            t.append(cl((152 * k * hl, 66 * k * hl, 48 * k * hl)))
    tex['B'], glow['B'] = t, [False] * 1024
    t = []  # concrete: big bevelled blocks, stains
    stain = [[rnd.random() for _ in range(8)] for _ in range(8)]
    for y in range(32):
        for x in range(32):
            bx, by = x % 16, y % 16
            if bx == 15 or by == 15:
                v = 60
            elif bx == 0 or by == 0:
                v = 150
            elif bx == 14 or by == 14:
                v = 84
            else:
                v = 112 + rnd.uniform(-7, 7) - 18 * stain[y // 4][x // 4] ** 3
            t.append(cl((v, v * 1.0, v * 1.05)))
    tex['#'], glow['#'] = t, [False] * 1024
    t, g = [], []  # tech panel: frame, ribs, glowing strip, rivets
    for y in range(32):
        for x in range(32):
            e = False
            if x in (0, 31) or y in (0, 31):
                c = (28, 34, 48)
            elif x in (1, 30) or y in (1, 30):
                c = (96, 118, 150)
            elif 13 <= y <= 17 and 5 <= x <= 26:
                c = (110, 236, 255) if y in (14, 15, 16) else (40, 120, 150)
                e = y in (14, 15, 16)
            elif (x, y) in ((4, 4), (27, 4), (4, 27), (27, 27)):
                c = (180, 190, 210)
            elif y % 4 == 0 and (y < 12 or y > 19):
                c = (44, 56, 78)
            else:
                c = (60, 76, 104)
            t.append(cl(c))
            g.append(e)
    tex['T'], glow['T'] = t, g
    noise = [[rnd.random() for _ in range(32)] for _ in range(32)]
    t = []  # mossy stone: irregular blocks, moss creeping up from below
    for y in range(32):
        for x in range(32):
            s = sum(noise[(y + j) % 32][(x + i) % 32] for i in (-2, 0, 2) for j in (-2, 0, 2)) / 9
            row = y // 10
            bx = (x + row * 7) % 13
            if y % 10 == 9 or bx == 12:
                c = (40, 42, 38)
            else:
                v = 84 + s * 50
                c = (v, v * 0.98, v * 0.88)
                if s + y / 64 > 0.86:
                    c = mix(c, (64, 128, 52), clamp((s + y / 64 - 0.86) * 6, 0, 1))
            t.append(cl(c))
    tex['M'], glow['M'] = t, [False] * 1024
    return tex, glow


def make_wall_tables():
    tex, glow = make_wall_textures()
    tab = {}
    for wc in tex:
        tab[wc] = []
        for side in (0, 1):
            k = 1.0 if side == 0 else 0.72
            per = []
            for lvl in range(LEVELS):
                per.append([fogged(shade(c, k if not e else 1.0), lvl, e) for c, e in zip(tex[wc], glow[wc])])
            tab[wc].append(per)
    return tab


def make_floor_tables():
    """Floor and ceiling texels for every distance level and light level."""
    rnd = random.Random(9)
    floor, ceil, lamp = [], [], []
    for y in range(16):
        for x in range(16):
            if x == 0 or y == 0:
                f = (36, 37, 42)
            elif x == 1 or y == 1:
                f = (82, 84, 92)
            elif (x, y) in ((4, 4), (12, 4), (4, 12), (12, 12)):
                f = (120, 122, 130)
            elif (x + y) % 6 == 0:
                f = (66, 68, 74)
            else:
                v = 58 + rnd.uniform(-4, 4)
                f = (v, v + 1, v + 6)
            floor.append(f)
            c = (24, 25, 32) if x == 0 or y == 0 else (36, 38, 48) if (x // 4 + y // 4) % 2 else (32, 34, 43)
            ceil.append(c)
            d = max(abs(x - 7.5), abs(y - 7.5))
            lamp.append((255, 238, 196) if d < 3 else (200, 180, 140) if d < 4 else c)
    FT, CT = [], []
    for lvl in range(LEVELS):
        fl, cl_ = [], []
        for li in range(6):
            boost = 1.0 + li * 0.17
            warm = li * 5
            par = []
            for p in (0, 1):
                tint = 1.0 if p == 0 else 0.86
                par.append([fogged((min(255, c[0] * boost * tint + warm), min(255, c[1] * boost * tint + warm * 0.7),
                                    min(255, c[2] * boost * tint)), lvl) for c in floor])
            fl.append(par)
            cb = 1.0 + li * 0.12
            cl_.append([[fogged(shade(c, cb), lvl) for c in ceil],
                        [fogged(c, lvl, emissive=(c[0] > 150)) for c in lamp]])
        FT.append(fl)
        CT.append(cl_)
    return FT, CT


# Pixel sprites. Letters pick colours from the bot's palette; '.' is transparent. An outline is added
# automatically, and the sprite is shaded lighter at the top and on the left.
DRONE = [
    "......m.m......",
    ".......m.......",
    "....bbbbbbb....",
    "..bbbbbbbbbbb..",
    ".bbbbdddddbbbb.",
    ".bbbdeeeeedbbb.",
    "mmbbdeeWeedbbmm",
    ".bbbdeeeeedbbb.",
    ".bbbbdddddbbbb.",
    "..bbbbbbbbbbb..",
    "....bbbbbbb....",
    ".....ddddd.....",
    "......fff......",
    ".......f.......",
]
SENT_TOP = [
    ".....bbbbb.....",
    "....bbbbbbb....",
    "....deeeeed....",
    "....bbbbbbb....",
    ".....ddddd.....",
    "..mmbbbbbbbmm..",
    ".mmbbbWWWbbbmgg",
    ".mbbbbWWWbbbmgg",
    ".mb.bbbbbbb.mgF",
    ".mb.bbbbbbb.m..",
    ".mm.ddddddd.m..",
    ".m...bbbbb..mm.",
]
SENT_LEGS = [[
    ".....bb.bb.....",
    "....bbb..bb....",
    "....bb...bbb...",
    "....bb....bb...",
    "....mm....mm...",
    "...mmm....mmm..",
], [
    ".....bb.bb.....",
    ".....bb.bbb....",
    "....bbb..bb....",
    "....bb...bb....",
    "....mm...mm....",
    "...mmm...mmm...",
]]
BRUTE_TOP = [
    ".......bbbbbbb.......",
    "......bbbbbbbbb......",
    "......ddeeeeedd......",
    "...mmmbbbbbbbbbmmm...",
    "..mmmmbbbbbbbbbmmmm..",
    ".ggmmbbbbWWWbbbbmmgg.",
    "gggmmbbbbWWWbbbbmmggg",
    "Fggmmbbbbbbbbbbbmmggf",
    "ggg.mbbbbbbbbbbbm.ggg",
    ".g..mdddddddddddm..g.",
    "....bbbbbbbbbbbbb....",
    ".....bbbbbbbbbbb.....",
    ".....ddddddddddd.....",
]
BRUTE_LEGS = [[
    "....bbbb.....bbbb....",
    "....bbbb.....bbbb....",
    "...bbbbb.....bbbbb...",
    "...mmmmm.....mmmmm...",
    "..mmmmmmm...mmmmmmm..",
], [
    "....bbbb.....bbbb....",
    "...bbbbb.....bbbb....",
    "...mmmmm.....bbbbb...",
    "..mmmmmmm....mmmmm...",
    ".............mmmmmmm.",
]]
WRECK = [
    "...............",
    "...............",
    ".......d.......",
    "....m..b..d....",
    "..dbbmbbddbm...",
    ".mbbdbbbmbbbdd.",
    "dmbbbddbbbmbbbd",
]
HEALTH = [
    "wwwwwwwwww",
    "wwwwrrwwww",
    "wwwwrrwwww",
    "wwrrrrrrww",
    "wwrrrrrrww",
    "wwwwrrwwww",
    "wwwwrrwwww",
    "wwwwwwwwww",
]
AMMO = [
    ".yy.yy.yy.",
    ".yy.yy.yy.",
    ".oo.oo.oo.",
    "gggggggggg",
    "gooooooog.",
    "goyyyyyyog",
    "gooooooooo",
    "gggggggggg",
]
GUN = [
    ".........mm.........",
    "........mWWm........",
    "........mccm........",
    "........mccm........",
    ".......mmccmm.......",
    "......mmmmmmmm......",
    "......mddddddm......",
    "......mddeeddm......",
    "......mmmmmmmm......",
    ".....mmbbbbbbmm.....",
    "....mbbbccccbbbm....",
    "....mbbbccccbbbm....",
    "...mmbbbeeeebbbmm...",
    "...mbbbbeeeebbbbm...",
    "..mmbbbbbbbbbbbbmm..",
    "..mbbbbddddddbbbbm..",
    ".hhhbbbddddddbbbhhh.",
    "hhhhhbbbbbbbbbbhhhhh",
    "hhhhhhbbbbbbbbhhhhhh",
]
PALETTES = {
    "drone": {"b": (70, 200, 150), "m": (150, 160, 172), "d": (26, 48, 44), "e": (255, 60, 60),
              "W": (255, 226, 220), "f": (120, 220, 255)},
    "sentinel": {"b": (236, 150, 50), "m": (134, 138, 154), "d": (66, 40, 22), "e": (90, 240, 255),
                 "W": (255, 240, 160), "g": (66, 70, 82), "F": (66, 70, 82)},
    "brute": {"b": (200, 52, 46), "m": (92, 92, 104), "d": (58, 18, 18), "e": (255, 230, 80),
              "W": (255, 150, 60), "g": (60, 60, 72), "F": (60, 60, 72), "f": (60, 60, 72)},
    "h": {"w": (236, 236, 240), "r": (220, 40, 40)},
    "a": {"y": (240, 200, 70), "o": (110, 104, 50), "g": (70, 76, 40)},
    "gun": {"m": (150, 156, 172), "b": (84, 90, 104), "c": (52, 56, 66), "d": (38, 40, 48),
            "e": (90, 230, 255), "h": (70, 56, 48), "W": (120, 130, 150)},
}
OUTLINE = (12, 12, 16)
SPRITE_FOG, SPRITE_FLOOR = 0.45, 0.62   # bots and pickups take less distance fog than walls: they stand out
EMISSIVE = set("eWfF")


def build_sprite(rows, pal, outline=True, flash=None):
    """Rows of palette letters -> grid of (colour, emissive) or None, with outline and shading."""
    w = max(len(r) for r in rows)
    rows = [r.ljust(w, ".") for r in rows]
    h = len(rows)
    W, H = w + 2, h + 2
    grid = [[None] * W for _ in range(H)]
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            if ch == ".":
                continue
            if flash and ch in flash:
                c, e = flash[ch], True
            else:
                c, e = pal[ch], ch in EMISSIVE
            if not e:
                k = 1.18 - 0.42 * y / h + (0.08 if x < w * 0.4 else -0.06 if x > w * 0.7 else 0)
                c = shade(c, k)
            grid[y + 1][x + 1] = (c, e)
    if outline:
        for y in range(H):
            for x in range(W):
                if grid[y][x] is None and any(0 <= y + j < H and 0 <= x + i < W and grid[y + j][x + i]
                                              and grid[y + j][x + i][0] != OUTLINE
                                              for i, j in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    grid[y][x] = (OUTLINE, False)
    return grid


class SpriteBank:
    """Sprites per bot kind and pose, fogged per distance level on demand (cached)."""

    def __init__(self):
        fl = {"F": (255, 240, 150), "f": (255, 240, 150), "g": (255, 190, 80)}
        self.base = {
            ("drone", 0): build_sprite(DRONE, PALETTES["drone"]),
            ("drone", 1): build_sprite(DRONE, dict(PALETTES["drone"], f=(200, 250, 255))),
            ("drone", "fire"): build_sprite(DRONE, dict(PALETTES["drone"], e=(255, 230, 150), W=(255, 255, 255))),
            ("drone", "dead"): build_sprite(WRECK, PALETTES["drone"]),
        }
        for kind, top, legs in (("sentinel", SENT_TOP, SENT_LEGS), ("brute", BRUTE_TOP, BRUTE_LEGS)):
            pal = PALETTES[kind]
            self.base[(kind, 0)] = build_sprite(top + legs[0], pal)
            self.base[(kind, 1)] = build_sprite(top + legs[1], pal)
            self.base[(kind, "fire")] = build_sprite(top + legs[0], pal, flash={"F": fl["F"], "f": fl["f"]})
            self.base[(kind, "dead")] = build_sprite(WRECK, pal)
        self.base[("h", 0)] = build_sprite(HEALTH, PALETTES["h"])
        self.base[("a", 0)] = build_sprite(AMMO, PALETTES["a"])
        self.gun = build_sprite(GUN, PALETTES["gun"])
        self.cache = {}

    def get(self, key, lvl, hit=False):
        ck = (key, lvl, hit)
        s = self.cache.get(ck)
        if s is None:
            s = []
            for row in self.base[key]:
                out = []
                for px in row:
                    if px is None:
                        out.append(None)
                    else:
                        c, e = px
                        if hit and c != OUTLINE:
                            c = mix(c, (255, 255, 255), 0.7)
                        out.append(fogged(c, lvl * SPRITE_FOG, e or hit, SPRITE_FLOOR))
                s.append(out)
            self.cache[ck] = s
        return s


# =============================================================================
# Terminal
# =============================================================================
KEYS = {"\x1b[A": "up", "\x1b[B": "down", "\x1b[C": "right", "\x1b[D": "left",
        "\x1bOA": "up", "\x1bOB": "down", "\x1bOC": "right", "\x1bOD": "left"}


KITTY_RE = re.compile(r"\x1b\[([0-9:;]*)([uABCDHF~])")
KITTY_NAMES = {13: "enter", 27: "esc", 32: " ", 9: "tab", 127: "backspace"}
ARROWS = {"A": "up", "B": "down", "C": "right", "D": "left"}


try:   # auto mode's speed / pause / stop handling is shared with the collection
    from arcadekit import AUTO_BG, AUTO_HELP, AUTO_LABEL, AutoMode
except ImportError:   # BLOCKFIRE on its own: a small copy of arcadekit.AutoMode
    AUTO_LABEL, AUTO_BG = "Auto mode", (236, 180, 70)
    AUTO_HELP = ["AUTO MODE - the game plays itself", "", "Space            pause / continue",
                 "+ / -            faster / slower", "M                sound on / off",
                 "Esc / Q          stop (back to the title)", "?                this help"]

    class AutoMode:
        SPEEDS = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)

        def __init__(self, speed=1.0):
            self.i, self.paused, self.help, self._acc = self.SPEEDS.index(speed), False, False, 0.0

        @property
        def speed(self):
            return self.SPEEDS[self.i]

        def key(self, k):
            if self.help:
                self.help = False
                return True
            if k in ("esc", "q"):
                return "stop"
            if k in (" ", "p", "enter"):
                self.paused = not self.paused
            elif k in ("+", "=", "right", "up"):
                self.i = min(len(self.SPEEDS) - 1, self.i + 1)
            elif k in ("-", "_", "left", "down"):
                self.i = max(0, self.i - 1)
            elif k == "m":
                return "sound"
            elif k == "?":
                self.help = True
                return "help"
            else:
                return None
            return True

        def scale(self, dt):
            return 0.0 if self.paused or self.help else dt * self.speed

        def steps(self, dt, step):
            self._acc += self.scale(dt)
            n = int(self._acc / step)
            self._acc -= n * step
            return min(n, int(8 * self.speed) + 1)

        def text(self, extra=""):
            state = "PAUSED" if self.paused else ("x%g" % self.speed).replace("x0.", "x.")
            return " AUTO %s %s  Space pause   +/- speed   Esc stop " % (state, (" " + extra) if extra else "")


class Terminal:
    """Raw keys. Where the terminal supports the kitty keyboard protocol (kitty, WezTerm, Ghostty,
    foot, recent iTerm2) it also reports key releases, so held keys work exactly."""

    def __enter__(self):
        if not sys.stdout.isatty():
            raise SystemExit("BLOCKFIRE needs a terminal.")
        self.fd = sys.stdin.fileno()
        self.old = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        self.write("\x1b[?1049h\x1b[?25l\x1b[2J\x1b[H")
        self.releases = []
        self.kitty = self.detect_kitty()
        if self.kitty:
            self.write("\x1b[>11u")   # disambiguate + event types + all keys as escape codes
        return self

    def __exit__(self, *exc):
        if self.kitty:
            self.write("\x1b[<u")
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)
        self.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        return exc[0] is KeyboardInterrupt

    def detect_kitty(self):
        """Ask for the keyboard protocol flags, with a device-attributes query as the fallback answer."""
        if os.environ.get("BLOCKFIRE_LEGACY_KEYS"):
            return False
        self.write("\x1b[?u\x1b[c")
        data, end = "", time.time() + 0.5
        while time.time() < end and "c" not in data.split("\x1b[?")[-1]:
            if select.select([self.fd], [], [], 0.05)[0]:
                data += os.read(self.fd, 1024).decode("utf-8", "ignore")
        return re.search(r"\x1b\[\?\d*u", data) is not None

    @staticmethod
    def write(s):
        sys.stdout.write(s)
        sys.stdout.flush()

    def keys(self, timeout=0.0):
        """Keys pressed (or auto-repeated) since the last call; releases are collected in self.releases."""
        out = []
        wait = timeout
        while select.select([self.fd], [], [], wait)[0]:
            wait = 0
            data = os.read(self.fd, 1024).decode("utf-8", "ignore")
            if not data:
                break
            i = 0
            while i < len(data):
                m = KITTY_RE.match(data, i) if self.kitty else None
                if m:
                    i = m.end()
                    params, final = m.group(1), m.group(2)
                    fields = params.split(";")
                    code = fields[0].split(":")[0]
                    event = fields[1].split(":")[1] if len(fields) > 1 and ":" in fields[1] else "1"
                    if final in ARROWS:
                        name = ARROWS[final]
                    elif final == "u" and code.isdigit():
                        c = int(code)
                        name = KITTY_NAMES.get(c) or (chr(c).lower() if 32 < c < 0x110000 else None)
                    else:
                        name = None
                    if name is None:
                        continue
                    if event == "3":
                        self.releases.append(name)
                    else:
                        out.append(name)
                    continue
                if data[i] == "\x1b":
                    for seq, name in KEYS.items():
                        if data.startswith(seq, i):
                            out.append(name)
                            i += len(seq)
                            break
                    else:
                        lone = i + 1 >= len(data) or data[i + 1] not in "[O"
                        out.append("esc" if lone else "?")
                        i += 1 if lone else 3
                else:
                    ch = data[i]
                    out.append("enter" if ch in "\r\n" else ch.lower())
                    i += 1
        return out


CUBE = (0, 95, 135, 175, 215, 255)
SAFE256 = {16: 232, 17: 234, 18: 24, 19: 25, 20: 26, 21: 27}


def x256(c):
    """Nearest xterm-256 colour: (index, its RGB)."""
    r, g, b = c
    q = [0 if v < 48 else 1 if v < 115 else min(5, (v - 35) // 40) for v in (r, g, b)]
    cr, cg, cb = CUBE[q[0]], CUBE[q[1]], CUBE[q[2]]
    gi = clamp((r + g + b) // 3 - 3, 0, 237) // 10
    gv = 8 + 10 * gi
    dc = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
    dg = (r - gv) ** 2 + (g - gv) ** 2 + (b - gv) ** 2
    if dg < dc:
        return 232 + gi, (gv, gv, gv)
    i = 16 + 36 * q[0] + 6 * q[1] + q[2]
    if i in SAFE256:          # base16 colour schemes repaint 16-21
        i = SAFE256[i]
        cr, cg, cb = (8, 8, 8) if i == 232 else (28, 28, 28) if i == 234 else (0, 95, (i - 24) * 40 + 135)
    return i, (cr, cg, cb)


# =============================================================================
# Rendering
# =============================================================================
HUD_BG = (16, 16, 26)
HUD_FG, HUD_DIM = (210, 210, 224), (140, 144, 168)
CROSS_ON = (255, 190, 60)
MAP_BG, MAP_WALL, MAP_EDGE = (10, 10, 18), (118, 122, 142), (70, 72, 92)
POP_BG = (14, 14, 28)


class Renderer:
    def __init__(self, game):
        self.g = game
        self.walls = make_wall_tables()
        self.FT, self.CT = make_floor_tables()
        self.sprites = SpriteBank()
        self.true = os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")
        self.fgc, self.bgc = {}, {}
        self.pal256 = {}         # RGB -> the palette RGB it is shown as (256-colour terminals)
        self.parts = []          # [x, y, z, vx, vy, vz, age, life, colour]
        self.tracers = []        # [screen-space start getter (bot), hit, until]
        self.pops = []           # "+100" rising from destroyed bots: [x, y, born]
        self.proj = None         # (project, K, mid) of the last rendered view
        self.t = 0.0
        self.help = False        # the help box instead of the pause menu
        self.prep_map()

    def prep_map(self):
        g = self.g
        W, H = g.W, g.H
        lamps = [(x + 0.5, y + 0.5) for y in range(H) for x in range(W)
                 if x % 4 == 2 and y % 4 == 2 and g.grid[y][x] == '.']
        self.lamp = [1 if (x % 4 == 2 and y % 4 == 2) else 0 for y in range(H) for x in range(W)]
        self.W4, self.H4 = W * 4, H * 4
        lg = []
        for sy in range(H * 4):
            for sx in range(W * 4):
                wx, wy = (sx + 0.5) / 4, (sy + 0.5) / 4
                best = min(((wx - lx) ** 2 + (wy - ly) ** 2 for lx, ly in lamps), default=99)
                lg.append(clamp(int((1 - math.sqrt(best) / 2.4) * 6), 0, 5))
        self.light = lg

    def fg(self, c):
        s = self.fgc.get(c)
        if s is None:
            s = self.fgc[c] = ("\x1b[38;2;%d;%d;%dm" % c) if self.true else "\x1b[38;5;%dm" % x256(c)[0]
        return s

    def bg(self, c):
        s = self.bgc.get(c)
        if s is None:
            s = self.bgc[c] = ("\x1b[48;2;%d;%d;%dm" % c) if self.true else "\x1b[48;5;%dm" % x256(c)[0]
        return s

    # --- effects --------------------------------------------------------------------------------------
    def events(self, dt):
        g = self.g
        self.t += dt
        for ev in g.fx:
            if ev[0] == "hit":
                _, x, y, size = ev
                for _ in range(10):
                    self.parts.append([x, y, 0.45 * size, random.uniform(-1.5, 1.5), random.uniform(-1.5, 1.5),
                                       random.uniform(0.5, 2.5), 0.0, random.uniform(0.15, 0.4),
                                       random.choice([(255, 230, 120), (255, 160, 60), (255, 255, 220)])])
            elif ev[0] == "kill":
                _, x, y, kind = ev
                self.pops.append([x, y, self.t])
                body = PALETTES[kind]["b"]
                for _ in range(46):
                    a, v = random.uniform(0, 6.3), random.uniform(0.5, 4)
                    self.parts.append([x, y, random.uniform(0.2, 0.7), math.cos(a) * v, math.sin(a) * v,
                                       random.uniform(0.5, 4), 0.0, random.uniform(0.4, 1.0),
                                       random.choice([body, (255, 200, 80), (255, 120, 40), (255, 250, 210)])])
                for _ in range(16):
                    self.parts.append([x, y, 0.3, random.uniform(-0.4, 0.4), random.uniform(-0.4, 0.4),
                                       random.uniform(0.2, 0.6), 0.0, random.uniform(1.0, 2.2), (70, 70, 76)])
            elif ev[0] == "shot":
                _, b, hit = ev
                self.tracers.append([b, hit, self.t + 0.08, random.uniform(-1, 1)])
        g.fx.clear()
        keep = []
        for p in self.parts:
            p[6] += dt
            if p[6] < p[7]:
                p[0] += p[3] * dt
                p[1] += p[4] * dt
                p[2] += p[5] * dt
                p[5] -= 7.0 * dt if p[8] != (70, 70, 76) else -0.3 * dt
                if p[2] < 0:
                    p[2], p[5] = 0.0, -p[5] * 0.35
                keep.append(p)
        self.parts = keep[-600:]
        self.tracers = [t for t in self.tracers if t[2] > self.t]
        if self.pops:
            self.pops = [p for p in self.pops if self.t - p[2] < 1.0]

    # --- the 3D view -------------------------------------------------------------------------------------
    def view(self, PW, PH, cam=None, dim=1.0):
        """Raycast into a row-major pixel buffer. Returns (buf, zbuf, projection helpers)."""
        g = self.g
        if cam is None:
            px, py, a = g.px, g.py, g.a
        else:
            px, py, a = cam
        dx, dy = math.cos(a), math.sin(a)
        plx, ply = -dy * FOV_PLANE, dx * FOV_PLANE
        K = PW / (2.0 * FOV_PLANE)       # pixels of a 1-unit wall at distance 1 (square pixels)
        mid = PH / 2.0
        buf = [[FOG] * PW for _ in range(PH)]
        zbuf = [0.0] * PW
        ybot = [0] * PW
        boost = 4 if g.muzzle > 0 and cam is None else 0
        cast, walls = g.cast, self.walls
        for c in range(PW):
            cm = 2.0 * c / PW - 1.0
            rdx, rdy = dx + plx * cm, dy + ply * cm
            perp, side, wc, wx = cast(px, py, rdx, rdy)
            if perp < 0.05:
                perp = 0.05
            zbuf[c] = perp
            lh = K / perp
            top = mid - lh * 0.5
            t0 = max(0, int(top + 0.5))
            b0 = min(PH, int(mid + lh * 0.5 + 0.5))
            ybot[c] = b0
            lvl = int(perp * LVL_PER_UNIT) - boost
            tab = walls[wc][side][0 if lvl < 0 else LEVELS - 1 if lvl >= LEVELS else lvl]
            tx = int(wx * 32) & 31
            scale = 32.0 / lh
            ty0 = (t0 + 0.5 - top) * scale
            for r in range(t0, b0):
                ty = int(ty0)
                buf[r][c] = tab[(31 if ty > 31 else ty) * 32 + tx]
                ty0 += scale
        # floor and ceiling, row by row, only where no wall covers them
        FT, CT, LG, LAMP = self.FT, self.CT, self.light, self.lamp
        W, W4, H4 = g.W, self.W4, self.H4
        rdx0, rdy0 = dx - plx, dy - ply
        rdx1, rdy1 = dx + plx, dy + ply
        y0 = int(mid)
        for y in range(y0, PH):
            rd = K * 0.5 / (y + 0.5 - mid)
            lvl = int(rd * LVL_PER_UNIT) - boost
            lvl = 0 if lvl < 0 else LEVELS - 1 if lvl >= LEVELS else lvl
            ft, ct = FT[lvl], CT[lvl]
            fx, fy = px + rd * rdx0, py + rd * rdy0
            sx, sy = rd * (rdx1 - rdx0) / PW, rd * (rdy1 - rdy0) / PW
            row = buf[y]
            yc = PH - 1 - y
            crow = buf[yc]
            for c in range(PW):
                if y >= ybot[c]:
                    lx, ly = int(fx * 4), int(fy * 4)
                    li = LG[(ly % H4) * W4 + lx % W4]
                    idx = (int(fy * 16) & 15) * 16 + (int(fx * 16) & 15)
                    cx, cy = lx >> 2, ly >> 2
                    row[c] = ft[li][(cx + cy) & 1][idx]
                    if yc < PH - ybot[c]:
                        crow[c] = ct[li][LAMP[(cy % g.H) * W + cx % W]][idx]
                fx += sx
                fy += sy
        inv = 1.0 / (plx * dy - dx * ply)

        def project(wx, wy):
            rx, ry = wx - px, wy - py
            return inv * (dy * rx - dx * ry), inv * (-ply * rx + plx * ry)

        return buf, zbuf, K, mid, project

    def draw_sprite(self, buf, zbuf, PW, PH, grid, left, top, w, h, tY):
        gh, gw = len(grid), len(grid[0])
        c0, c1 = max(0, int(left)), min(PW, int(left + w) + 1)
        r0, r1 = max(0, int(top)), min(PH, int(top + h) + 1)
        if c1 <= c0 or r1 <= r0:
            return
        sx, sy = gw / w, gh / h
        for c in range(c0, c1):
            if zbuf[c] <= tY:
                continue
            ax = int((c + 0.5 - left) * sx)
            if not 0 <= ax < gw:
                continue
            ay0 = (r0 + 0.5 - top) * sy
            for r in range(r0, r1):
                ay = int(ay0)
                ay0 += sy
                if 0 <= ay < gh:
                    px = grid[ay][ax]
                    if px is not None:
                        buf[r][c] = px

    def scene(self, PW, PH, cam=None):
        g = self.g
        buf, zbuf, K, mid, project = self.view(PW, PH, cam)
        if cam is not None:
            return buf
        self.proj = (project, K, mid)
        objs = []
        for b in g.bots:
            objs.append((b.x, b.y, b))
        for p in g.pickups:
            if p["active"]:
                objs.append((p["x"], p["y"], p))
        proj = []
        for x, y, o in objs:
            tX, tY = project(x, y)
            if tY > 0.2:
                proj.append((tY, tX, o))
        proj.sort(key=lambda t: -t[0])
        bank = self.sprites
        for tY, tX, o in proj:
            lvl = min(LEVELS - 1, int(tY * LVL_PER_UNIT))
            scr_x = PW / 2.0 * (1 + tX / tY)
            floor_y = mid + K * 0.5 / tY
            if isinstance(o, Bot):
                if not o.alive:
                    key, size, lift = (o.kind, "dead"), 0.42 * o.k["size"], 0.0
                elif o.flash > 0:
                    key, size, lift = (o.kind, "fire"), o.k["size"], 0.0
                else:
                    moving = int((o.x + o.y) * 3) % 2
                    key, size, lift = (o.kind, moving), o.k["size"], 0.0
                if o.kind == "drone" and o.alive:
                    size *= 0.62
                    lift = 0.28 + 0.05 * math.sin(self.t * 4 + o.x * 3)
                    key = (o.kind, "fire") if o.flash > 0 else (o.kind, int(self.t * 12) % 2)
                grid = bank.get(key, lvl, o.alive and o.hit > 0)
            else:
                size = 0.26
                lift = 0.08 + 0.04 * math.sin(self.t * 3 + o["x"])
                grid = bank.get((o["kind"], 0), lvl)
            gh, gw = len(grid), len(grid[0])
            h = K * size / tY
            w = h * gw / gh
            if not isinstance(o, Bot):
                w *= 0.35 + 0.65 * abs(math.cos(self.t * 2 + o["y"]))   # pickups turn
            if h < 1:
                continue
            bottom = floor_y - K * lift / tY
            self.draw_sprite(buf, zbuf, PW, PH, grid, scr_x - w / 2, bottom - h, w, h, tY)
        # particles
        for p in self.parts:
            tX, tY = project(p[0], p[1])
            if tY <= 0.15:
                continue
            c = int(PW / 2.0 * (1 + tX / tY))
            r = int(mid + K * (0.5 - p[2]) / tY)
            if 0 <= c < PW and 0 <= r < PH and zbuf[c] > tY:
                col = p[8]
                buf[r][c] = col
                if tY < 3 and c + 1 < PW:
                    buf[r][c + 1] = col
        # enemy shots: a bright streak from the bot's gun towards (or past) the screen
        for b, hit, _, wob in self.tracers:
            tX, tY = project(b.x, b.y)
            if tY <= 0.2:
                continue
            sx0 = PW / 2.0 * (1 + tX / tY)
            sy0 = mid + K * (0.5 - 0.55 * b.k["size"]) / tY
            ex = PW / 2 + (wob * PW * 0.05 if hit else wob * PW * 0.3)
            ey = PH * (0.9 if hit else 0.75)
            n = int(max(abs(ex - sx0), abs(ey - sy0)))
            for i in range(0, n, 1):
                t = i / max(1, n)
                x, y = int(sx0 + (ex - sx0) * t), int(sy0 + (ey - sy0) * t)
                if 0 <= x < PW and 0 <= y < PH and (zbuf[x] > tY * (1 - t) or t > 0.2):
                    buf[y][x] = (255, 120, 80) if i % 3 else (255, 230, 180)
        self.overlay_view(buf, PW, PH, mid)
        return buf

    def overlay_view(self, buf, PW, PH, mid):
        g = self.g
        # the gun, with bob and recoil
        S = max(1, PH // 64)
        grid = self.sprites.gun
        gh, gw = len(grid), len(grid[0])
        bobx = int(math.sin(g.bob) * 2 * S) if g.moving else 0
        boby = int(abs(math.cos(g.bob)) * 1.5 * S) if g.moving else 0
        rec = S * 2 if g.muzzle > 0 else 0
        gx0 = int(PW * 0.62) - gw * S // 2 + bobx      # held in the right hand, clear of the crosshair
        gy0 = PH - gh * S + boby + rec + S
        if g.ammo > 0:
            energy = (90, 230, 255)
        else:  # empty: the cells blink red
            energy = (255, 80, 60) if int(self.t * 3) % 2 else (90, 30, 30)
        for y in range(gh):
            for x in range(gw):
                px = grid[y][x]
                if px is None:
                    continue
                c, e = px
                if e:
                    c = energy
                if g.muzzle > 0 and c != OUTLINE:
                    c = mix(c, (255, 220, 160), 0.25)
                for yy in range(S):
                    r = gy0 + y * S + yy
                    if 0 <= r < PH:
                        row = buf[r]
                        for xx in range(S):
                            cc = gx0 + x * S + xx
                            if 0 <= cc < PW:
                                row[cc] = c
        if g.muzzle > 0:  # muzzle flash: a hot core with spikes
            mx, my = gx0 + (gw // 2) * S, gy0 + S * 2
            R = 4 * S
            for yy in range(-R, R + 1):
                for xx in range(-R, R + 1):
                    d = math.hypot(xx, yy * 1.2)
                    spike = abs(xx) < S or abs(yy) < S or abs(abs(xx) - abs(yy)) < S
                    if d < R * 0.45 or (spike and d < R):
                        x, y = mx + xx, my + yy - R // 2
                        if 0 <= x < PW and 0 <= y < PH:
                            buf[y][x] = (255, 255, 230) if d < R * 0.3 else (255, 200, 80)
        # crosshair
        cx, cy = PW // 2, int(mid)
        on = not g.over and g.aim_bot(math.cos(g.a), math.sin(g.a)) is not None
        col = (255, 70, 60) if g.hitmark > 0 else CROSS_ON if on else (240, 240, 240)
        if g.hitmark > 0:
            pts = [(cx + i, cy + i) for i in (-3, -2, 2, 3)] + [(cx + i, cy - i) for i in (-3, -2, 2, 3)]
        else:
            pts = [(cx + i, cy) for i in (-4, -3, -2, 2, 3, 4)] + [(cx, cy + i) for i in (-3, -2, 2, 3)]
            if on:
                pts.append((cx, cy))
        for x, y in pts:   # a dark drop shadow keeps it readable on bright walls
            if 0 <= x + 1 < PW and 0 <= y + 1 < PH:
                c = buf[y + 1][x + 1]
                buf[y + 1][x + 1] = (c[0] >> 2, c[1] >> 2, c[2] >> 2)
        for x, y in pts:
            if 0 <= x < PW and 0 <= y < PH:
                buf[y][x] = col
        # damage: red edges, brighter on the side the shot came from; low health pulses
        hurt = g.dmg_flash > 0
        low = g.hp < 30 and not g.over
        if hurt or low or g.hurt_t > 0:
            rel = (g.hurt_ang - g.a + math.pi) % (2 * math.pi) - math.pi if g.hurt_t > 0 else 0.0
            pulse = 0.25 + 0.15 * math.sin(self.t * 6) if low else 0.0
            for y in range(PH):
                row = buf[y]
                for x in list(range(0, 6)) + list(range(PW - 6, PW)):
                    edge = (6 - x) if x < 6 else (x - (PW - 7))
                    k = edge / 6 * (0.6 if hurt else 0) + edge / 6 * pulse
                    if g.hurt_t > 0 and abs(rel) > 0.5 and ((rel < 0) == (x < 6)) and abs(rel) < 2.6:
                        k += edge / 6 * 0.55 * min(1.0, g.hurt_t)
                    if k > 0:
                        row[x] = mix(row[x], (220, 20, 20), min(0.85, k))
            if g.hurt_t > 0 and abs(rel) >= 2.6:  # from behind: bottom edge
                for y in range(PH - 5, PH):
                    k = (y - (PH - 6)) / 5 * 0.6 * min(1.0, g.hurt_t)
                    buf[y] = [mix(c, (220, 20, 20), k) for c in buf[y]]

    def minimap(self, buf, PW, PH):
        """A compact, opaque map window round the player (top right). Bots outside it show on its edge."""
        g = self.g
        RW, RH = min(g.W, 26), min(g.H, 18)
        x0 = clamp(int(g.px) - RW // 2, 0, g.W - RW)
        y0 = clamp(int(g.py) - RH // 2, 0, g.H - RH)
        ox, oy = PW - RW - 3, 2
        for y in range(-1, RH + 1):   # backing with a one-pixel frame
            row = buf[oy + y]
            for x in range(-1, RW + 1):
                if y < 0 or y >= RH or x < 0 or x >= RW:
                    row[ox + x] = MAP_EDGE
                else:
                    row[ox + x] = MAP_WALL if g.grid[y0 + y][x0 + x] != '.' else MAP_BG
        for p in g.pickups:
            mx, my = int(p["x"]) - x0, int(p["y"]) - y0
            if p["active"] and 0 <= mx < RW and 0 <= my < RH:
                buf[oy + my][ox + mx] = (255, 170, 190) if p["kind"] == "h" else (240, 200, 70)
        blink = int(self.t * 4) % 2
        for b in g.bots:
            if b.alive:
                mx, my = int(b.x) - x0, int(b.y) - y0
                c = PALETTES[b.kind]["b"]
                if 0 <= mx < RW and 0 <= my < RH:
                    buf[oy + my][ox + mx] = (255, 255, 255) if b.has_los and blink else c
                else:              # off the window: a mark on the frame where it is
                    buf[oy + clamp(my, -1, RH)][ox + clamp(mx, -1, RW)] = c
        x, y = int(g.px) - x0, int(g.py) - y0
        for k in (1, 2):           # facing: two pixels ahead of the player
            fx, fy = int(g.px + math.cos(g.a) * k) - x0, int(g.py + math.sin(g.a) * k) - y0
            if 0 <= fy < RH and 0 <= fx < RW:
                buf[oy + fy][ox + fx] = (120, 200, 255) if k == 1 else (60, 110, 160)
        buf[oy + y][ox + x] = (255, 255, 255)

    # --- output -------------------------------------------------------------------------------------------
    def emit(self, buf, cols, prow, text=None):
        """Half-block frame for the top prow rows; text = {(col, row): (ch, fg, bg)} drawn into it."""
        text = text or {}
        sfg, sbg = self.fg, self.bg
        out = ["\x1b[?2026h\x1b[H"]
        q = None if self.true else self.pal256
        for j in range(prow):
            top, bot = buf[2 * j], buf[2 * j + 1]
            if q is not None:  # snap to the palette first, so equal-looking neighbours share one code
                top = [q.get(c) or q.setdefault(c, x256(c)[1]) for c in top]
                bot = [q.get(c) or q.setdefault(c, x256(c)[1]) for c in bot]
            lt = lb = None
            line = []
            for i in range(cols):
                t, b = top[i], bot[i]
                tx = text.get((i, j)) if text else None
                if tx:
                    ch, f, bg = tx
                    if bg is None:
                        bg = mix(t, b, 0.5)
                    if f != lt:
                        line.append(sfg(f))
                        lt = f
                    if bg != lb:
                        line.append(sbg(bg))
                        lb = bg
                    line.append(ch)
                    continue
                if SOLID_PIXELS and t != b:
                    c = solid_cell(t, b)
                    if c is not None:
                        t = b = c
                if t == b:
                    if b != lb:
                        line.append(sbg(b))
                        lb = b
                    line.append(" ")
                    continue
                if t != lt:
                    line.append(sfg(t))
                    lt = t
                if b != lb:
                    line.append(sbg(b))
                    lb = b
                line.append("▀")
            out.append("".join(line))
            out.append("\x1b[0m\r\n")
        return out

    def hud(self, cols):
        """Two lines: vitals first (health, ammo), then the wave; less important numbers drop out first
        when the window is narrow. The second line shows messages, or a few key hints."""
        g = self.g
        hp = int(g.hp)
        hpc = (80, 220, 100) if hp > 50 else (240, 200, 70) if hp > 25 else (255, 70, 60)
        filled = int(hp / 10 + 0.5)
        ammoc = (255, 70, 60) if not g.ammo else (255, 150, 60) if g.ammo < 10 else (240, 200, 70)
        bots = sum(1 for b in g.bots if b.alive) + len(g.spawn_queue)
        segs = [(" BLOCKFIRE ", (16, 16, 20), (244, 150, 56), 3),
                ("  HP ", HUD_DIM, HUD_BG, 0), ("█" * filled, hpc, HUD_BG, 0), ("░" * (10 - filled), (70, 72, 90), HUD_BG, 0),
                (" %3d " % hp, hpc, HUD_BG, 0),
                ("  AMMO ", HUD_DIM, HUD_BG, 0), ("%3d " % g.ammo if g.ammo else "PULSE ", ammoc, HUD_BG, 0),
                ("  WAVE ", HUD_DIM, HUD_BG, 1), ("%d " % max(1, g.wave), HUD_FG, HUD_BG, 1),
                ("  BOTS ", HUD_DIM, HUD_BG, 2), ("%d " % bots, (255, 120, 90) if bots else HUD_FG, HUD_BG, 2),
                ("  SCORE ", HUD_DIM, HUD_BG, 2), ("%d " % g.score, (110, 220, 255), HUD_BG, 2),
                ("  KILLS ", HUD_DIM, HUD_BG, 4), ("%d " % g.kills, HUD_FG, HUD_BG, 4),
                ("  BEST ", HUD_DIM, HUD_BG, 5), ("%d " % g.best, HUD_DIM, HUD_BG, 5)]
        while sum(len(x[0]) for x in segs) > cols:   # drop the least important label + value pair
            worst = max(x[3] for x in segs)
            if worst == 0:
                break
            segs = [x for x in segs if x[3] != worst]
        out, n = [], 0
        for s, f, b, _ in segs:
            s = s[:max(0, cols - n)]
            if s:
                out.append(self.fg(f) + self.bg(b) + s)
                n += len(s)
        out.append(self.bg(HUD_BG) + " " * max(0, cols - n) + "\x1b[0m\r\n")
        if g.msgs:
            s, f = " " + g.msgs[-1][0], (240, 200, 70)
        else:
            s, f = " W/S move   A/D strafe   Left/Right turn   Space fire   ? help", HUD_DIM
        out.append(self.fg(f) + self.bg((10, 10, 18)) + s.ljust(cols)[:cols] + "\x1b[0m")
        return "".join(out)

    def banner(self, buf, text, PW, prow, lines, t):
        """A dark stripe across the view with large spaced text; it slides in from the left."""
        PH = prow * 2
        r0 = max(0, int(prow * 0.22))
        h = len(lines) + 2
        k = min(1.0, t / 0.18)                       # slide in
        for y in range(r0 * 2, min(PH, (r0 + h) * 2)):
            row = buf[y]
            for x in range(int(PW * (1 - k)), PW):
                c = row[x]
                row[x] = (c[0] // 4, c[1] // 4, c[2] // 4 + 4)
        dx = int(-(1 - k) * PW * 0.5)
        for i, (s, c) in enumerate(lines):
            x = (PW - len(s)) // 2 + dx
            for j, ch in enumerate(s):
                if 0 <= x + j < PW and ch != " ":
                    text[(x + j, r0 + 1 + i)] = (ch, c, None)

    def frame(self, cols, rows):
        g = self.g
        prow = rows - 2
        PW, PH = cols, prow * 2
        buf = self.scene(PW, PH)
        text = {}
        if g.over:   # dim the arena so the result box is the one thing to read
            for y in range(PH):
                buf[y] = [(c[0] * 3 >> 3, c[1] * 3 >> 3, c[2] * 3 >> 3) for c in buf[y]]
        if self.pops and not g.over and self.proj:   # "+100" chips rising from destroyed bots
            project, K, mid = self.proj
            for x, y, born in self.pops:
                tX, tY = project(x, y)
                if tY > 0.3:
                    age = self.t - born
                    c = int(PW / 2.0 * (1 + tX / tY)) - 3
                    r = int(mid + K * (0.5 - 0.7 - age * 0.6) / tY) // 2
                    fgc = mix((255, 230, 120), POP_BG, clamp((age - 0.6) * 2.5, 0, 1))
                    for j, ch in enumerate(" +100 "):
                        if 0 <= c + j < cols and 0 <= r < prow:
                            text[(c + j, r)] = (ch, fgc, POP_BG)
        auto = getattr(self, "auto", None)
        if g.over and auto:
            self.box(text, cols, prow, ["", "Y O U   W E R E   S C R A P P E D", "",
                                        "Wave %d   Kills %d   Score %d" % (g.wave, g.kills, g.score), "",
                                        "Auto mode: a new round starts in a moment", ""], (255, 255, 255), (110, 20, 20))
        elif g.over:
            lines = ["", "Y O U   W E R E   S C R A P P E D", "",
                     "Wave %d   Kills %d   Score %d" % (g.wave, g.kills, g.score),
                     "NEW BEST SCORE!" if g.new_best else "Best %d" % g.best, "",
                     "R restart     Esc / Q quit", ""]
            self.box(text, cols, prow, lines, (255, 255, 255), (110, 20, 20))
            if g.new_best:     # the record line in gold
                y0 = prow // 2 - len(lines) // 2 + 4
                for (x, y), (ch, f, bg) in list(text.items()):
                    if y == y0 and ch != " ":
                        text[(x, y)] = (ch, (255, 220, 90), bg)
        elif g.paused:
            text_box(text, cols, prow, HELP if self.help else PAUSE + ["", SND.label()])
        elif g.wave and 0 <= g.t - g.wave_t < 1.8:   # a new wave rolls in
            n = sum(1 for b in g.bots if b.alive) + len(g.spawn_queue)
            self.banner(buf, text, PW, prow, [("W A V E   %d" % g.wave, (255, 214, 90)),
                                             ("%d bots incoming" % n, (235, 235, 245))], g.t - g.wave_t)
        elif g.wave and g.inter > 0 and 0 <= g.t - g.clear_t < 2.0:
            self.banner(buf, text, PW, prow, [("W A V E   %d   C L E A R E D" % g.wave, (120, 240, 140)),
                                             ("+25 HP    +%d ammo" % AMMO_CLEAR, (235, 235, 245))], g.t - g.clear_t)
        elif g.inter > 0 and not any(b.alive for b in g.bots):
            self.banner(buf, text, PW, prow, [("W A V E   %d" % (g.wave + 1), (255, 214, 90)),
                                             ("starts in %d" % (int(g.inter) + 1), (235, 235, 245))], 1.0)
        if g.show_map and not g.over and cols >= 80 and PH >= 44:
            self.minimap(buf, PW, PH)
        if auto:   # the amber AUTO bar on the top row of the view (the HUD keeps the bottom rows)
            t = auto.text()
            if len(t) > cols:
                t = (" AUTO %s  Esc stop " % ("PAUSED" if auto.paused else "x%g" % auto.speed))[:cols]
            text_put(text, cols, prow, 0, 0, " " * cols, (24, 16, 6), shade(AUTO_BG, 0.55))
            text_put(text, cols, prow, max(0, (cols - len(t)) // 2), 0, t, (20, 14, 4), AUTO_BG)
            if auto.help:
                text_box(text, cols, prow, AUTO_HELP)
        out = self.emit(buf, cols, prow, text)
        out.append(self.hud(cols))
        out.append("\x1b[?2026l")
        return "".join(out)

    @staticmethod
    def box(text, cols, prow, lines, fg, bg):
        w = max(len(s) for s in lines) + 8
        y0 = prow // 2 - len(lines) // 2
        x0 = max(0, (cols - w) // 2)
        for i, s in enumerate(lines):
            for j, ch in enumerate(s.center(w)):
                if 0 <= x0 + j < cols and 0 <= y0 + i < prow:
                    text[(x0 + j, y0 + i)] = (ch, fg, bg)


# =============================================================================
# Title screen and main loop
# =============================================================================
BIGFONT = {
    "B": ["####.", "#...#", "####.", "#...#", "####."], "L": ["#....", "#....", "#....", "#....", "#####"],
    "O": [".###.", "#...#", "#...#", "#...#", ".###."], "C": [".####", "#....", "#....", "#....", ".####"],
    "K": ["#...#", "#..#.", "###..", "#..#.", "#...#"], "F": ["#####", "#....", "####.", "#....", "#...."],
    "I": ["#####", "..#..", "..#..", "..#..", "#####"], "R": ["####.", "#...#", "####.", "#..#.", "#...#"],
    "E": ["#####", "#....", "####.", "#....", "#####"],
}


HELP = [
    "B L O C K F I R E  -  keys",
    "",
    "W / S  (Up / Down)       move forward / back",
    "A / D                    strafe left / right",
    "Left / Right  (J / L)    turn",
    "Space / F / Enter        fire",
    "M                        minimap on / off",
    "",
    "Esc / P                  pause menu (Q there: quit, M: sound on / off)",
    "?                        this help",
    "",
    "Auto mode: the game plays itself (Space pause, +/- speed, Esc stop)",
]
PAUSE = ["P A U S E D", "", "Esc / P / Enter   continue", "?                 help", "M                 sound on / off",
         "Q                 quit"]


# The ASCII ARCADE title layout (same look as arcadekit.title_screen in the collection)
TITLE_DIM, PANEL_BG, PANEL_FG = (6, 6, 14), (14, 14, 28), (220, 220, 232)
GOLD_TEXT, FOOTER_BG, FOOTER_FG = (240, 210, 120), (12, 10, 22), (150, 154, 184)
ACCENT = ((255, 165, 70), (215, 50, 40))
BOX_FG, BOX_BG = (240, 240, 246), (22, 22, 42)


def text_put(text, cols, rows, x, y, s, fg, bg=None):
    for j, ch in enumerate(s):
        if 0 <= x + j < cols and 0 <= y < rows:
            text[(x + j, y)] = (ch, fg, bg)


def text_box(text, cols, rows, lines):
    """A centred box like the collection's help and pause boxes."""
    w = max(len(l) for l in lines) + 4
    x0, y0 = max(0, (cols - w) // 2), max(0, rows // 2 - len(lines) // 2 - 1)
    for j, l in enumerate([""] + list(lines) + [""]):
        text_put(text, cols, rows, x0, y0 + j, ("  " + l).ljust(w), BOX_FG, BOX_BG)


TITLE_ITEMS = ["Start the fight", AUTO_LABEL]


def title_frame(r, cols, rows, t, help_=False, sel=0):
    PH = rows * 2
    buf = r.scene(cols, PH, cam=(8.0 - math.cos(t * 0.06) * 6, 19.5, math.sin(t * 0.2) * 0.16))   # down the open hall
    for y in range(PH):
        buf[y] = [mix(c, TITLE_DIM, 0.55) for c in buf[y]]
    items = TITLE_ITEMS
    extra = ["", "The arena is sealed. The bots keep coming.", "How many waves can you last?"]
    # the same letter size as every ASCII ARCADE title (it fits the longest name, 11 letters)
    k = 2 if cols >= 11 * 12 - 2 + 4 and 8 + len(items) * 2 + len(extra) + 9 <= rows else 1
    tw = 9 * 6 * k - k
    x0, y0 = (cols - tw) // 2, 3
    for n, ch in enumerate("BLOCKFIRE"):
        for gy, line in enumerate(BIGFONT[ch]):
            c = mix(ACCENT[0], ACCENT[1], gy / 4)
            for gx, bit in enumerate(line):
                if bit != "#":
                    continue
                for yy in range(k):
                    for xx in range(k):
                        x, y = x0 + (n * 6 + gx) * k + xx, y0 + gy * k + yy
                        if k >= 2 and x + 1 < cols and y + 1 < PH:   # soft shadow
                            buf[y + 1][x + 1] = mix(buf[y + 1][x + 1], (0, 0, 0), 0.7)
        for gy, line in enumerate(BIGFONT[ch]):
            c = mix(ACCENT[0], ACCENT[1], gy / 4)
            for gx, bit in enumerate(line):
                if bit == "#":
                    for yy in range(k):
                        for xx in range(k):
                            x, y = x0 + (n * 6 + gx) * k + xx, y0 + gy * k + yy
                            if 0 <= x < cols and 0 <= y < PH:
                                buf[y][x] = c
    text = {}
    row = (y0 + 5 * k) // 2 + 2
    tag = "a first-person arena shooter"
    text_put(text, cols, rows, (cols - len(tag)) // 2, row, tag, (205, 205, 220))
    gap = 2 if row + 3 + len(items) * 2 + len(extra) + 4 < rows else 1
    w = max([len(s) for s in items + extra] + [20]) + 8
    px0, r0 = max(0, (cols - w) // 2), row + 2
    height = len(items) * gap + len(extra) + (1 if gap == 2 else 0) + 1
    for j in range(height):
        text_put(text, cols, rows, px0, r0 + j, " " * w, PANEL_FG, PANEL_BG)
    sel_bg = mix(ACCENT[0], ACCENT[1], 0.3)
    for i, s in enumerate(items):
        y = r0 + 1 + i * gap if gap == 2 else r0 + i
        if i == sel:
            text_put(text, cols, rows, px0 + 2, y, (" > " + s).ljust(w - 4), (14, 14, 20), sel_bg)
        else:
            text_put(text, cols, rows, px0 + 2, y, ("   " + s).ljust(w - 4), PANEL_FG, PANEL_BG)
    ey = r0 + (1 + len(items) * gap if gap == 2 else len(items))
    for j, s in enumerate(extra):
        text_put(text, cols, rows, px0 + 2, ey + j, ("   " + s).ljust(w - 4), FOOTER_FG, PANEL_BG)
    if r.g.best:
        b = "best score: %d" % r.g.best
        text_put(text, cols, rows, (cols - len(b)) // 2, r0 + height + 1, b, GOLD_TEXT)
    label, keys = " ASCII ARCADE ", " Up/Down choose   Enter start   ? help   Esc back "
    text_put(text, cols, rows, 0, rows - 1, " " * cols, FOOTER_FG, FOOTER_BG)
    text_put(text, cols, rows, 0, rows - 1, label, (14, 14, 20), (200, 200, 215))
    text_put(text, cols, rows, max(len(label) + 1, cols - len(keys)), rows - 1, keys, FOOTER_FG, FOOTER_BG)
    if help_:
        text_box(text, cols, rows, HELP)
    out = r.emit(buf, cols, rows, text)
    out[-1] = "\x1b[0m"
    out.append("\x1b[?2026l")
    return "".join(out)


KEYMAP = {"w": "f", "up": "f", "s": "b", "down": "b", "a": "l", "d": "r",
          "left": "tl", "j": "tl", ",": "tl", "right": "tr", "l": "tr", ".": "tr",
          " ": "fire", "f": "fire", "enter": "fire"}


STEP = 1.0 / 60       # auto mode's fixed simulation step (the speed setting runs more or fewer of them)
AUTO_OVER = 3.0       # seconds the result box stays up before auto mode starts a new round


def auto_play(term, r):
    """Auto mode: the real game, driven by the AutoPilot, round after round until Esc / Q."""
    auto = r.auto = AutoMode()

    def new_round():
        g = r.g = Game()
        g.auto = True
        r.parts, r.tracers, r.pops = [], [], []
        SND.play("start")
        return g, AutoPilot(g)
    g, bot = new_round()
    last, over_t = time.perf_counter(), 0.0
    try:
        while True:
            now = time.perf_counter()
            dt, last = min(now - last, 0.25), now
            for k in term.keys(0):
                a = auto.key(k)
                if a == "stop":
                    return
                if a == "sound" and SND.toggle():
                    SND.play("select")
            term.releases.clear()
            if g.over:
                over_t += 0.0 if auto.paused or auto.help else dt
                r.events(0.0 if auto.paused else dt)
                if over_t >= AUTO_OVER:
                    g, bot = new_round()
                    over_t = 0.0
            else:
                for _ in range(auto.steps(dt, STEP)):
                    bot.step(STEP)
                    g.update(STEP)
                    r.events(STEP)
                    if g.over:
                        break
            cols, rows = os.get_terminal_size()
            if cols < 60 or rows < 18:
                term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (60x18).")
                time.sleep(0.2)
                continue
            term.write(r.frame(cols, rows))
            rest = 1.0 / FPS - (time.perf_counter() - now)
            if rest > 0:
                time.sleep(rest)
    finally:
        r.auto = None


def run(term):
    g = Game()
    r = Renderer(g)
    t0 = time.time()
    help_ = False
    sel = 0
    while True:  # title
        cols, rows = os.get_terminal_size()
        if cols < 60 or rows < 18:
            term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (60x18).")
            term.keys(0.3)
            continue
        term.write(title_frame(r, cols, rows, time.time() - t0, help_, sel))
        start = False
        for k in term.keys(1 / 20):
            if help_:              # any key closes the help
                help_ = False
            elif k == "?":
                help_ = True
            elif k in ("q", "esc"):
                return g
            elif k in ("up", "w", "k"):
                sel = (sel - 1) % len(TITLE_ITEMS)
                SND.play("select")
            elif k in ("down", "s", "j", "tab"):
                sel = (sel + 1) % len(TITLE_ITEMS)
                SND.play("select")
            elif k in (" ", "enter"):
                start = True
        term.releases.clear()
        if start and TITLE_ITEMS[sel] == AUTO_LABEL:
            auto_play(term, r)
            g = r.g = Game()       # back on the title with a fresh (normal) game
            r.parts, r.tracers, r.pops = [], [], []
            continue
        if start:
            SND.play("start")
            break
    last = time.perf_counter()
    held = set()           # actions whose keys are down (only known with the kitty protocol)
    rep_last, rep_seq, rep_first = {}, {}, {}
    rep_t = {"delay": 0.35, "rate": 0.09}   # learned auto-repeat timing (macOS-like defaults)
    while True:
        now = time.perf_counter()
        dt = now - last
        last = now
        keys = term.keys(0)
        for k in term.releases:
            a = KEYMAP.get(k)
            if a:
                held.discard(a)
                if a in g.hold:
                    g.hold[a] = 0.0
        term.releases.clear()
        if term.kitty:
            held.update(KEYMAP[k] for k in keys if k in KEYMAP)
            for a in held:
                if a in g.hold:
                    g.hold[a] = max(g.hold[a], 0.25)
                elif a == "fire":
                    g.press("fire")       # hold to keep firing
        for k in keys:
            # the keys every ASCII ARCADE game shares: Esc / P pause menu, Q quits from it, ? help
            if g.over:
                if k in ("q", "esc"):
                    return g
                if k == "r":
                    g.reset()
                    SND.play("start")
                continue
            if g.paused:
                if k in ("esc", "p", "enter", " "):
                    g.paused = r.help = False
                    held.clear()
                elif k == "q":
                    return g
                elif k == "?":
                    r.help = not r.help
                elif k == "m":     # M is the minimap during play, sound on / off in the pause menu
                    if SND.toggle():
                        SND.play("select")
                continue
            if k in ("esc", "p", "q", "?"):
                g.paused, r.help = True, k == "?"
                for h in g.hold:
                    g.hold[h] = g.bridge[h] = 0.0
                continue
            a = KEYMAP.get(k)
            if a in g.hold and not term.kitty:
                gap = now - rep_last.get(a, -9.0)
                rep_last[a] = now
                if gap < 0.8:      # an auto-repeat (or a quick second tap)
                    n = rep_seq[a] = rep_seq.get(a, 0) + 1
                    if n == 1:
                        rep_first[a] = gap
                    else:          # a steady run of repeats: now we know this keyboard's timing
                        if n == 2:
                            rep_t["delay"] = clamp(0.5 * rep_t["delay"] + 0.5 * rep_first[a], 0.1, 0.8)
                        rep_t["rate"] = clamp(0.5 * rep_t["rate"] + 0.5 * gap, 0.02, 0.3)
                    g.press(a)
                    g.hold[a] = max(g.hold[a], rep_t["rate"] + 0.07)
                    g.bridge[a] = 0.0
                else:              # a fresh press: keep going until the repeats should arrive
                    rep_seq[a] = 0
                    g.press(a)
                    g.bridge[a] = rep_t["delay"] + 0.05
                continue
            if k == "m":
                g.show_map = not g.show_map
            elif k in KEYMAP:
                g.press(KEYMAP[k])
        g.update(dt)
        r.events(0 if g.paused else min(dt, 0.1))
        cols, rows = os.get_terminal_size()
        if cols < 60 or rows < 18:
            term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (60x18).")
            time.sleep(0.2)
            continue
        term.write(r.frame(cols, rows))
        rest = 1.0 / FPS - (time.perf_counter() - now)
        if rest > 0:
            time.sleep(rest)


def selftest(ticks=20000):
    """Headless run with an aim-bot player: checks invariants and that waves progress."""
    global BEST_FILE
    BEST_FILE = os.devnull
    g = Game(seed=11)
    rnd = random.Random(4)
    t0 = time.time()
    max_wave = deaths = 0
    for i in range(ticks):
        target = None
        for b in g.bots:
            if b.alive and g.los(g.px, g.py, b.x, b.y):
                if target is None or math.hypot(b.x - g.px, b.y - g.py) < math.hypot(target.x - g.px, target.y - g.py):
                    target = b
        if target:
            g.a = math.atan2(target.y - g.py, target.x - g.px)
            g.press("fire")
        else:
            g.press(rnd.choice(["f", "f", "b", "l", "r", "tl", "tr"]))
        if rnd.random() < 0.3:
            g.press(rnd.choice(["l", "r"]))
        g.update(1.0 / 30)
        g.fx.clear()
        assert not g.blocked(g.px, g.py, PLAYER_R * 0.9), "player inside wall"
        for b in g.bots:
            assert not g.solid(b.x, b.y), "bot inside wall"
        max_wave = max(max_wave, g.wave)
        if g.over:
            deaths += 1
            g.reset()
    dur = time.time() - t0
    print("Self-test ok: %d ticks in %.1fs (%.2f ms/tick), reached wave %d, deaths %d, last kills %d"
          % (ticks, dur, dur * 1000 / ticks, max_wave, deaths, g.kills))
    assert max_wave >= 3, "waves do not progress"
    selftest_auto()


def selftest_auto(seconds=100, frame_dt=1 / 30):
    """Auto mode headless at x8: the AutoPilot plays the real game through AutoMode's fixed steps for
    `seconds` of real time (8x that in game time), rounds restart, frames render, and no best score is saved."""
    global BEST_FILE
    import tempfile
    BEST_FILE = os.path.join(tempfile.mkdtemp(), "best")
    auto = AutoMode()
    auto.i = auto.SPEEDS.index(8.0)
    g = Game(seed=2)
    g.auto = True
    bot = AutoPilot(g, seed=2)
    r = Renderer(g)
    r.auto = auto
    t0 = time.time()
    rounds, waves, game_t, over_t = 1, [], 0.0, 0.0
    for i in range(int(seconds / frame_dt)):
        if g.over:
            over_t += frame_dt
            if over_t >= AUTO_OVER:
                waves.append(g.wave)
                g = r.g = Game(seed=2 + rounds)
                g.auto = True
                bot = AutoPilot(g, seed=2 + rounds)
                rounds, over_t = rounds + 1, 0.0
        else:
            for _ in range(auto.steps(frame_dt, STEP)):
                bot.step(STEP)
                g.update(STEP)
                r.events(STEP)
                game_t += STEP
                if g.over:
                    break
        if i % 40 == 0:
            r.frame(120, 40)
        assert not g.blocked(g.px, g.py, PLAYER_R * 0.9), "auto: player inside wall"
    assert not os.path.exists(BEST_FILE) and not g.new_best, "auto mode saved a best score"
    assert game_t > seconds * 7, "auto mode does not run at x8 (%.0fs of game time)" % game_t
    waves.append(g.wave)
    print("Auto mode ok: %ds at x8 = %.0fs game time in %.1fs, %d round(s), waves %s, no score saved"
          % (seconds, game_t, time.time() - t0, rounds, waves))


def bench(cols=160, rows=45, frames=40):
    """Play a few seconds with an aim-bot and time the full frame (render + escape codes)."""
    global BEST_FILE
    BEST_FILE = os.devnull
    g = Game(seed=3)
    r = Renderer(g)
    total = 0.0
    for i in range(frames):
        for _ in range(3):
            target = next((b for b in g.bots if b.alive and g.los(g.px, g.py, b.x, b.y)), None)
            if target:
                g.a = math.atan2(target.y - g.py, target.x - g.px)
                g.press("fire")
            else:
                g.press("f")
                g.press("tl")
            g.update(1 / 30)
            r.events(1 / 30)
        t = time.time()
        r.frame(cols, rows)
        total += time.time() - t
    print("frame %.1f ms at %dx%d (%d bots, %d particles)" % (total / frames * 1000, cols, rows, len(g.bots), len(r.parts)))


def main():
    args = sys.argv[1:]
    if "--selftest" in args:
        selftest()
        return
    if "--bench" in args:
        bench()
        return
    with Terminal() as term:
        g = run(term)
    print("Thanks for playing BLOCKFIRE! Wave %d, kills %d, score %d (best %d)."
          % (g.wave, g.kills, g.score, g.best))


if __name__ == "__main__":
    main()
