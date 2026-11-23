#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""GEMBURROW - dig for sunstones under tumbling rock.

The sunstones that lit the badger warrens have sunk into the deep earth. Pell, a young badger in a brass miner's
helmet, digs down after them: through soil and packed clay, under boulders that roll off each other and fall the
moment the ground beneath them is gone. Collect each cave's quota of sunstones to open the burrow door before the
lamp oil runs out. Cinderbeetles creep along the walls and burst into flame, glassmoths shatter into sunstones
when a rock lands on them, creepmoss spreads through the soil, and old rune seams turn falling rock into gems.
Five worlds of four caves - the Rootwarren, the Glowmoss Grotto, the Ember Seams, the Frostvein Hollows and the
Starcore - each followed by a small intermission cave.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
In terminals with the kitty keyboard protocol (kitty, WezTerm, Ghostty, recent iTerm2) keys are read with their
releases; elsewhere a held key counts as held while the terminal repeats it.
"""
import math
import random
import sys
import time

from arcadekit import (ACCENTS, AUTO_LABEL, PAUSE_LINES, AutoMode, Canvas, KeyTerminal, clamp, load_scores, mix,
                       overlay, shared_key, submit, title_screen)
from arcadesound import Sound

GAME = "gemburrow"
NAME = "GEMBURROW"
TAGLINE = "dig for sunstones under tumbling rock"
ACCENTS.setdefault(NAME, ((255, 214, 120), (176, 104, 220)))

VW, VH = 20, 12                 # the view: always this many tiles; a bigger window makes the tiles bigger
TICK = 0.14                     # seconds per cave tick (everything in the cave moves one cell per tick)
EXTRA_EVERY = 500               # an extra life every this many points
WHITE = (255, 255, 255)

# --- cells --------------------------------------------------------------------------------------
EMPTY, DIRT, BRICK, STEEL, EXIT, DOOR, RUNE, PLAYER = 0, 1, 2, 3, 4, 5, 6, 7     # <= PLAYER: nothing to scan
ROCK, GEM, ROCKF, GEMF, CINDER, MOTH, MOSS = 8, 9, 10, 11, 12, 13, 14
BOOM, GBOOM = 15, 19            # explosion stages 15-18 (to empty) and 19-22 (to sunstones)
BOOM_END, GBOOM_END = 18, 22
ROUND = (ROCK, GEM, BRICK)      # things a rock rolls off
DX, DY = (0, 1, 0, -1), (-1, 0, 1, 0)   # directions 0 up, 1 right, 2 down, 3 left
CHARS = {"#": STEEL, "=": BRICK, ".": DIRT, " ": EMPTY, "o": ROCK, "*": GEM, "P": PLAYER, "E": EXIT, "c": CINDER,
         "m": MOTH, "~": MOSS, "R": RUNE}
DIFFS = [dict(name="EASY", key="easy", time=1.5, lives=5),
         dict(name="NORMAL", key="normal", time=1.0, lives=4),
         dict(name="HARD", key="hard", time=0.72, lives=3)]


# =============================================================================================
# The cave: a grid of cells and the rules that move them, one tick at a time
# =============================================================================================
class Cave:
    """The whole state of one cave and its tick rules. Copyable (the autopilot plans on copies).

    Each tick the player moves first, then the cave is scanned bottom to top, left to right; anything that moves
    is stamped and not looked at again in the same tick, so a column of falling rock falls together and no
    object ever moves twice. Rocks and sunstones fall into empty cells and roll off rocks, sunstones and clay when
    the side and the cell below it are free; a falling one crushes Pell and the creatures, passes through a
    glowing rune seam changed (rock to sunstone, sunstone to rock) and otherwise comes to rest."""

    def __init__(self, spec=None, diff=1, seed=0):
        self.rnd = random.Random(seed)
        if spec is None:
            return
        rows = spec["map"]
        self.w, self.h = len(rows[0]), len(rows)
        self.grid = []
        self.dirs = []
        self.player = -1
        for y, r in enumerate(rows):
            for x, ch in enumerate(r):
                v = CHARS[ch]
                if v == PLAYER:
                    self.player = y * self.w + x
                self.grid.append(v)
                self.dirs.append(3 if ch == "c" else 2 if ch == "m" else 0)
        self.exit = self.grid.index(EXIT)
        self.quota = spec["quota"]
        self.ticks_left = int(round(spec["time"] * DIFFS[diff]["time"] / TICK))
        self.rune_ticks = int(round(spec.get("rune", 22) / TICK))
        self.rune_state = 0          # 0 dormant, 1 glowing, 2 spent
        self.moss_slow = int(round(spec.get("moss_slow", 30) / TICK))
        self.moss_p = spec.get("moss_p", (0.012, 0.05))
        self.moss_limit = spec.get("moss_limit", 120)
        self.moss_state = 0          # 0 none / growing, 1 became sunstones, 2 became rock
        self.gems = 0
        self.alive, self.won, self.timeout = True, False, False
        self.door_open = False
        self.tick = 0
        self.push = None             # (direction, cell): pushing takes two ticks against the same rock
        self.face = 1
        self.ev, self.moves = [], []

    def copy(self, seed=0):
        c = Cave(seed=seed)
        c.__dict__.update(self.__dict__)
        c.rnd = random.Random(seed)
        c.grid = self.grid[:]
        c.dirs = self.dirs[:]
        c.ev, c.moves = [], []
        return c

    def xy(self, i):
        return i % self.w, i // self.w

    # --- one tick -----------------------------------------------------------------------------
    def step(self, act=(-1, False)):
        """act: (direction 0-3 or -1, reach). reach takes or digs the cell in that direction without moving."""
        g, w = self.grid, self.w
        done = bytearray(len(g))
        self.ev, self.moves = ev, mv = [], []
        self.tick += 1
        if self.alive and not self.won:
            self.player_step(act, done)
        moss_n, moss_room = 0, False
        rnd = self.rnd
        mp = self.moss_p[0] if self.tick < self.moss_slow else self.moss_p[1]
        for y in range(self.h - 2, 0, -1):
            base = y * w
            for i in range(base + 1, base + w - 1):
                c = g[i]
                if c <= PLAYER or done[i]:
                    continue
                if c == ROCK or c == GEM:
                    b = i + w
                    bc = g[b]
                    if bc == EMPTY:
                        g[i], g[b] = EMPTY, c + 2
                        done[b] = 1
                        mv.append((b, i))
                    elif bc in ROUND:
                        self.roll(i, c + 2, done)
                elif c == ROCKF or c == GEMF:
                    self.fall(i, c, done)
                elif c == CINDER or c == MOTH:
                    self.creature(i, c, done)
                elif c == MOSS:
                    moss_n += 1
                    if not moss_room:
                        for d in range(4):
                            n = g[i + DX[d] + DY[d] * w]
                            if n == EMPTY or n == DIRT:
                                moss_room = True
                                break
                    if rnd.random() < mp:
                        d = rnd.randrange(4)
                        n = i + DX[d] + DY[d] * w
                        if g[n] == EMPTY or g[n] == DIRT:
                            g[n] = MOSS
                            done[n] = 1
                elif c >= BOOM:
                    if c == BOOM_END:
                        g[i] = EMPTY
                    elif c == GBOOM_END:
                        g[i] = GEM
                    else:
                        g[i] = c + 1
        if moss_n:
            if moss_n >= self.moss_limit or not moss_room:
                to = ROCK if moss_room else GEM
                for i in range(len(g)):
                    if g[i] == MOSS:
                        g[i] = to
                self.moss_state = 2 if moss_room else 1
                ev.append(("moss", to))
        if self.rune_state == 1:
            self.rune_ticks -= 1
            if self.rune_ticks <= 0:
                self.rune_state = 2
                ev.append(("rune_off", 0))
        if not self.door_open and self.gems >= self.quota:
            self.door_open = True
            g[self.exit] = DOOR
            ev.append(("open", self.exit))
        if self.alive and not self.won:
            self.ticks_left -= 1
            if self.ticks_left <= 0:
                self.alive = False
                self.timeout = True
                ev.append(("timeout", self.player))

    def player_step(self, act, done):
        g, w = self.grid, self.w
        d, reach = act
        p = self.player
        if g[p] != PLAYER:
            self.alive = False
            return
        done[p] = 1
        if d < 0:
            self.push = None
            return
        if d in (1, 3):
            self.face = d
        n = p + DX[d] + DY[d] * w
        t = g[n]
        if t != ROCK:
            self.push = None
        if t == EMPTY or t == DIRT:
            if reach:
                if t == DIRT:
                    g[n] = EMPTY
                    self.ev.append(("dig", n))
                return
            g[p], g[n] = EMPTY, PLAYER
            self.player = n
            done[n] = 1
            self.moves.append((n, p))
            if t == DIRT:
                self.ev.append(("dig", n))
        elif t == GEM:
            self.gems += 1
            self.ev.append(("gem", n))
            if reach:
                g[n] = EMPTY
            else:
                g[p], g[n] = EMPTY, PLAYER
                self.player = n
                done[n] = 1
                self.moves.append((n, p))
        elif t == DOOR:
            if not reach:
                g[p] = EMPTY
                self.player = n
                self.won = True
                self.moves.append((n, p))
                self.ev.append(("exit", n))
        elif t == ROCK and d in (1, 3):
            b = n + DX[d]
            if g[b] == EMPTY:
                if self.push == (d, n):
                    g[b] = ROCK
                    done[b] = 1
                    self.moves.append((b, n))
                    self.push = None
                    if reach:
                        g[n] = EMPTY
                    else:
                        g[p], g[n] = EMPTY, PLAYER
                        self.player = n
                        done[n] = 1
                        self.moves.append((n, p))
                    self.ev.append(("push", b))
                else:
                    self.push = (d, n)
            else:
                self.push = None

    def roll(self, i, falling, done):
        g, w = self.grid, self.w
        for s in (-1, 1):
            if g[i + s] == EMPTY and g[i + w + s] == EMPTY:
                g[i], g[i + s] = EMPTY, falling
                done[i + s] = 1
                self.moves.append((i + s, i))
                return True
        return False

    def fall(self, i, c, done):
        g, w = self.grid, self.w
        b = i + w
        bc = g[b]
        if bc == EMPTY:
            g[i], g[b] = EMPTY, c
            done[b] = 1
            self.moves.append((b, i))
        elif bc == PLAYER:
            self.explode(b, False, done)
            self.ev.append(("crush", b))
        elif bc == CINDER or bc == MOTH:
            self.explode(b, bc == MOTH, done)
            self.ev.append(("crush", b))
        elif bc == RUNE:
            if self.rune_state == 0:
                self.rune_state = 1
                self.ev.append(("rune_on", b))
            if self.rune_state == 1:
                g[i] = EMPTY
                o = b + w
                if g[o] == EMPTY:
                    g[o] = GEMF if c == ROCKF else ROCKF
                    done[o] = 1
                    self.moves.append((o, i))
                self.ev.append(("sieve", b))
            else:
                g[i] = c - 2
                self.ev.append(("land", i, c - 2))
        elif bc == ROCKF or bc == GEMF:
            pass                              # the one below did not get to move yet: wait, do not land
        elif bc in ROUND and self.roll(i, c, done):
            pass
        else:
            g[i] = c - 2
            self.ev.append(("land", i, c - 2))

    def creature(self, i, c, done):
        g, w = self.grid, self.w
        for d in range(4):
            n = g[i + DX[d] + DY[d] * w]
            if n == PLAYER or n == MOSS:
                self.explode(i, c == MOTH, done)
                self.ev.append(("touch", i))
                return
        d = self.dirs[i]
        turn = 3 if c == CINDER else 1          # cinderbeetles keep a wall on their left, glassmoths on their right
        nd = (d + turn) & 3
        n = i + DX[nd] + DY[nd] * w
        if g[n] == EMPTY:
            d = nd
        else:
            n = i + DX[d] + DY[d] * w
            if g[n] != EMPTY:
                self.dirs[i] = (d - turn) & 3
                return
        g[i], g[n] = EMPTY, c
        self.dirs[n] = d
        done[n] = 1
        self.moves.append((n, i))

    def explode(self, i, gems, done):
        g, w = self.grid, self.w
        v = GBOOM if gems else BOOM
        for dy in (-w, 0, w):
            for dx in (-1, 0, 1):
                n = i + dx + dy
                t = g[n]
                if t == STEEL or t == EXIT or t == DOOR:
                    continue
                if t == PLAYER:
                    self.alive = False
                    self.ev.append(("die", n))
                g[n] = v
                done[n] = 1
        self.ev.append(("boom", i, gems))


# =============================================================================================
# The autopilot: plans a route on the cave it can see, checks it on a copy of the cave with the real rules
# =============================================================================================
WALKABLE = (EMPTY, DIRT, GEM)


class Bot:
    """Fair play: it reads only the cave as it is drawn (cells, the creatures' places and headings) and plans on
    a copy with the real tick rules. It never sees the game's dice: creepmoss grows on the copy with dice of its
    own, so where the moss really spreads the plan is checked again and made anew."""
    TRIES = 6
    IDLE = 6

    def __init__(self, g, seed=None):
        self.g = g
        self.rnd = random.Random(seed)
        self.reset()

    def reset(self):
        self.plan = []          # [(action, expected grid after it)]
        self.expect = None
        self.bad = {}           # target cell -> tick until which it is not tried again
        self.last_gem_tick = 0
        self.gems = 0

    # --- what the cave looks like from here ------------------------------------------------------
    def danger(self, c):
        """Cells next to a creature (plus the creature's cells) and cells right under falling things."""
        g, w = c.grid, c.w
        bad = set()
        for i, v in enumerate(g):
            if v == CINDER or v == MOTH:
                bad.add(i)
                for d in range(4):
                    n = i + DX[d] + DY[d] * w
                    bad.add(n)
                    for e in range(4):
                        bad.add(n + DX[e] + DY[e] * w)
            elif v == ROCKF or v == GEMF:
                bad.add(i + w)
                bad.add(i + 2 * w)
        return bad

    def bfs(self, c, avoid, door_ok):
        g, w = c.grid, c.w
        start = c.player
        prev = {start: None}
        order = [start]
        q = [start]
        k = 0
        while k < len(q):
            i = q[k]
            k += 1
            for d in range(4):
                n = i + DX[d] + DY[d] * w
                if n in prev or n in avoid:
                    continue
                v = g[n]
                if v in WALKABLE or (v == DOOR and door_ok):
                    prev[n] = (i, d)
                    q.append(n)
                    order.append(n)
                elif v == ROCK and d in (1, 3) and g[n + DX[d]] == EMPTY and i == start:
                    prev[n] = (i, d)          # a push: only as the first move, the rest is planned after it
                    q.append(n)
                    order.append(n)
        return prev, order

    @staticmethod
    def path(prev, t):
        out = []
        while prev[t] is not None:
            i, d = prev[t]
            out.append(d)
            t = i
        out.reverse()
        return out

    def targets(self, c):
        """(cell, route) to try, the most promising first."""
        g, w = c.grid, c.w
        avoid = self.danger(c)
        avoid.discard(c.player)
        prev, order = self.bfs(c, avoid, c.door_open)
        tick = c.tick
        out = []
        if c.door_open and c.exit in prev:
            out.append(c.exit)
        gems = [i for i in order if g[i] == GEM and self.bad.get(i, -1) < tick]
        out += gems[:self.TRIES]
        if len(out) < 2 or (not c.door_open and len(gems) + c.gems < c.quota):
            # loosen things: dirt that holds up a rock or a sunstone, so it falls (and maybe opens a way)
            digs = [i for i in order if g[i] == DIRT and g[i - w] in (ROCK, GEM) and self.bad.get(i, -1) < tick]
            out += digs[:4]
        return [(t, self.path(prev, t)) for t in out]

    # --- checking a route on a copy ----------------------------------------------------------------
    def simulate(self, c, route, idle=None):
        sim = c.copy(self.rnd.randrange(1 << 30))
        steps = []
        for d in route:
            want = sim.player + DX[d] + DY[d] * sim.w
            pushing = sim.grid[want] == ROCK
            sim.step((d, False))
            if pushing and sim.player != want:
                steps.append(((d, False), sim.grid[:]))
                sim.step((d, False))
            steps.append(((d, False), sim.grid[:]))
            if not sim.alive:
                return None
            if sim.won:
                return steps
            if sim.player != want:
                return None
        for _ in range(self.IDLE if idle is None else idle):
            sim.step((-1, False))
            if not sim.alive:
                return None
        if not self.escape(sim):
            return None
        return steps

    def escape(self, sim):
        """After the route Pell must not be shut in: the door has to stay reachable through soil and open cave,
        and so do enough sunstones to open it."""
        if sim.won:
            return True
        return self.open_way(sim)

    @staticmethod
    def open_way(sim):
        g, w = sim.grid, sim.w
        seen = bytearray(len(g))
        seen[sim.player] = 1
        q = [sim.player]
        gems = 0
        door = False
        while q:
            i = q.pop()
            for d in range(4):
                n = i + DX[d] + DY[d] * w
                if seen[n]:
                    continue
                v = g[n]
                if v == EXIT or v == DOOR:
                    seen[n] = 1
                    door = True
                elif v <= DIRT or v == GEM or v == CINDER or v == MOTH or v >= BOOM:
                    seen[n] = 1
                    gems += v == GEM
                    q.append(n)
        return door and (sim.door_open or sim.gems + gems >= sim.quota)

    def matches(self, c):
        """Did the cave do what the plan expected? Creepmoss is allowed to differ (its dice are unknown)."""
        if self.expect is None:
            return False
        if c.grid == self.expect:
            return True
        a, b = c.grid, self.expect
        for i in range(len(a)):
            if a[i] != b[i] and a[i] != MOSS and b[i] != MOSS:
                return False
        p = c.player
        w = c.w
        return all(a[p + DX[d] + DY[d] * w] != MOSS for d in range(4))

    # --- deciding -----------------------------------------------------------------------------------
    def __call__(self):
        c = self.g.cave
        if c.gems != self.gems:
            self.gems = c.gems
            self.last_gem_tick = c.tick
        if self.plan and self.matches(c):
            act, self.expect = self.plan.pop(0)
            return act
        self.plan = []
        for t, route in self.targets(c):
            if not route:
                continue
            steps = self.simulate(c, route)
            if steps:
                self.plan = steps
                act, self.expect = self.plan.pop(0)
                return act
            self.bad[t] = c.tick + 25
        return self.wander(c)

    def wander(self, c):
        """No route worked: the safest single move (or a reach), preferring ones that open the cave up."""
        best, best_v = (-1, False), -1e9
        acts = [(-1, False)] + [(d, r) for d in range(4) for r in (False, True)]
        prev, _ = self.bfs(c, set(), False)
        for act in acts:
            sim = c.copy(self.rnd.randrange(1 << 30))
            sim.step(act)
            ok = sim.alive
            for _ in range(self.IDLE):
                if not ok:
                    break
                sim.step((-1, False))
                ok = sim.alive
            if not ok:
                continue
            p2, order = self.bfs(sim, self.danger(sim), sim.door_open)
            if not self.open_way(sim):
                v0 = -100
            else:
                v0 = 0
            gems = sum(1 for i in order if sim.grid[i] == GEM)
            v = v0 + gems * 3 + len(order) * 0.05 + self.rnd.random() * 2 + (sim.gems - c.gems) * 10
            if sim.door_open and sim.exit in p2:
                v += 50
            if act[0] < 0:
                v -= 1.5
            if v > best_v:
                best, best_v = act, v
        self.expect = None
        return best


# =============================================================================================
# Pixel art: every tile is drawn at the size it is shown, so a bigger window gets finer tiles
# =============================================================================================
def hsh(x, y, s=0):
    h = (x * 374761393 + y * 668265263 + s * 2147483647) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    return (h ^ (h >> 16)) & 0xFFFF


def lit(c, k):
    """c brightened (k > 0, towards white) or darkened (k < 0, towards black)."""
    return mix(c, WHITE, k) if k >= 0 else mix(c, (0, 0, 0), -k)


_TILE = {}
SPRITES = (ROCK, GEM, ROCKF, GEMF, PLAYER, CINDER, MOTH)


def opaque_tile(kind, wd, t, var, frame, mask):
    """A t x t tile (rows of colours) for a cell that fills its square."""
    img = [[wd["bg"]] * t for _ in range(t)]
    bg, dirt = wd["bg"], wd["dirt"]
    big = t >= 6
    if kind == EMPTY:
        for y in range(t):
            row = img[y]
            for x in range(t):
                h = hsh(x + var * 31, y + var * 17, 3)
                c = lit(bg, 0.04 * ((h & 7) / 7)) if t > 3 else bg
                if big and h % 61 == 0:
                    c = lit(bg, 0.16)
                row[x] = c
        if big and var == 3:                          # a pebble on the cave floor now and then
            for y in range(t - 2, t):
                for x in range(t // 3, t // 3 + 2):
                    img[y][x] = lit(bg, 0.2 if y == t - 2 else 0.1)
        return img
    if kind == DIRT:
        up, rt, dn, lf = (mask >> 0) & 1, (mask >> 1) & 1, (mask >> 2) & 1, (mask >> 3) & 1   # an open side
        feat = wd["feature"]
        for y in range(t):
            row = img[y]
            for x in range(t):
                h = hsh(x + var * 13, y + var * 29, 5)
                k = ((h & 15) - 7.5) / 7.5 * 0.08
                if h % 9 == 0:
                    k += 0.14
                elif h % 13 == 0:
                    k -= 0.18
                c = lit(dirt, k)
                if t >= 4:
                    if up and y == 0:
                        c = lit(dirt, 0.28)
                    elif dn and y == t - 1:
                        c = lit(dirt, -0.45)
                    elif lf and x == 0 or rt and x == t - 1:
                        c = lit(c, -0.22)
                    elif up and y == 1 and t >= 7:
                        c = lit(dirt, 0.12)
                row[x] = c
        if big:
            r = random.Random(var * 7 + 1)
            for _ in range(1 + (t >= 9)):                 # pebbles
                cx, cy = r.uniform(1.5, t - 2.5), r.uniform(1.5, t - 2.5)
                rr = r.uniform(0.7, 1.0) * t / 9
                for y in range(int(cy - rr - 1), int(cy + rr + 2)):
                    for x in range(int(cx - rr - 1), int(cx + rr + 2)):
                        if 0 <= x < t and 0 <= y < t:
                            d = math.hypot((x + 0.5 - cx), (y + 0.5 - cy) * 1.2)
                            if d < rr:
                                img[y][x] = lit(wd["pebble"], 0.25 if y + 0.5 < cy - rr * 0.3 else -0.1)
            if feat == "roots" and var % 2 == 0:          # a thin root wandering across
                y0 = r.uniform(t * 0.3, t * 0.7)
                for x in range(t):
                    y = int(y0 + math.sin(x * 0.9 + var) * t * 0.12)
                    if 0 <= y < t:
                        img[y][x] = mix(dirt, (196, 150, 96), 0.55)
            elif feat in ("glow", "embers", "frost", "stars") and var % 2:
                col = wd["fleck"]
                for _ in range(1 + (t >= 10)):
                    x, y = r.randrange(1, t - 1), r.randrange(1, t - 1)
                    img[y][x] = col
                    if feat == "frost" and t >= 8:
                        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                            img[y + dy][x + dx] = mix(img[y + dy][x + dx], col, 0.5)
        return img
    if kind == BRICK:
        base = wd["brick"]
        mortar = lit(base, -0.55)
        bh = max(2, t // 2)
        for y in range(t):
            row = img[y]
            band = y // bh
            yy = y % bh
            off = (bh if band % 2 else 0) + (var & 1) * (t // 3)
            for x in range(t):
                xx = (x + off) % t
                bw = t
                if t < 4:
                    row[x] = base if (x + y) % 3 else lit(base, -0.25)
                    continue
                if yy == bh - 1 or xx == bw - 1:
                    c = mortar
                elif yy == 0 or xx == 0:
                    c = lit(base, 0.22)
                elif yy == bh - 2 or xx == bw - 2:
                    c = lit(base, -0.18)
                else:
                    h = hsh(x + var * 5, y, 9)
                    c = lit(base, ((h & 7) - 3.5) / 3.5 * 0.06 + (0.05 if band % 2 else 0))
                row[x] = c
        return img
    if kind in (STEEL, EXIT, RUNE):
        base = wd["steel"] if kind != RUNE else wd["rune"]
        for y in range(t):
            row = img[y]
            for x in range(t):
                h = hsh(x, y + var * 3, 11)
                c = lit(base, ((h & 7) - 3.5) / 3.5 * 0.04 + (x - y) / t * 0.06)
                if t >= 3:
                    if x == 0 or y == 0:
                        c = lit(base, 0.3)
                    elif x == t - 1 or y == t - 1:
                        c = lit(base, -0.5)
                row[x] = c
        if kind == STEEL and t >= 6:
            for cx, cy in ((2, 2), (t - 3, 2), (2, t - 3), (t - 3, t - 3)):
                img[cy][cx] = lit(base, 0.45)
                img[cy + 1][cx + 1] = lit(base, -0.4)
        if kind == EXIT and t >= 3:                        # the burrow door, shut: a round wooden door in stone
            wood = (112, 72, 40)
            for y in range(t):
                for x in range(t):
                    u, v = (x + 0.5) / t - 0.5, (y + 0.5) / t - 0.55
                    d = math.hypot(u / 0.38, v / 0.42) if v < 0 else max(abs(u) / 0.38, v / 0.42)
                    if d < 1:
                        c = lit(wood, -0.1 + 0.12 * math.sin(x * 2.2))
                        if d > 0.8:
                            c = lit(wood, -0.45)
                        if t >= 7 and abs(v + 0.05) < 0.5 / t:
                            c = (60, 56, 60)
                        img[y][x] = c
        if kind == RUNE:                                   # the carved glyph: dark (spent), dim (waiting), lit
            glow = [wd["rune_glow"], mix(wd["rune_glow"], WHITE, 0.5), wd["rune_glow"], mix(wd["rune_glow"], wd["gem"], 0.6)]
            col = lit(base, -0.4) if frame < 0 else lit(base, 0.25) if frame == 0 else glow[(frame - 1) % 4]
            pts = RUNE_GLYPHS[var % len(RUNE_GLYPHS)]
            for (a, b, c2, d2) in pts:
                n = max(2, t)
                for k in range(n + 1):
                    x = int((a + (c2 - a) * k / n) * (t - 1) + 0.5)
                    y = int((b + (d2 - b) * k / n) * (t - 1) + 0.5)
                    if 0 <= x < t and 0 <= y < t:
                        img[y][x] = col
            if frame > 0 and t >= 5:
                for y in range(1, t - 1):
                    for x in range(1, t - 1):
                        if img[y][x] != col and any(img[y + dy][x + dx] == col for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                            img[y][x] = mix(img[y][x], col, 0.35)
        return img
    if kind == DOOR:                                       # the open door: warm light pouring out, pulsing
        k = 0.5 + 0.5 * math.sin(frame / 8 * 2 * math.pi)
        inner = mix((255, 196, 90), (255, 250, 220), k)
        for y in range(t):
            for x in range(t):
                u, v = (x + 0.5) / t - 0.5, (y + 0.5) / t - 0.55
                d = math.hypot(u / 0.38, v / 0.42) if v < 0 else max(abs(u) / 0.38, v / 0.42)
                if d < 1:
                    img[y][x] = mix(inner, (255, 140, 40), d * d * 0.8)
                elif d < 1.25:
                    img[y][x] = mix(wd["steel"], (255, 200, 100), (1.25 - d) * 2.4 * (0.5 + 0.5 * k))
                else:
                    img[y][x] = lit(wd["steel"], 0.05 if x and y else 0.3)
        return img
    if kind == MOSS:
        mc = wd["moss"]
        for y in range(t):
            for x in range(t):
                img[y][x] = lit(mc, -0.62)
        r = random.Random(var * 11 + 5)
        blobs = [(r.uniform(0.2, 0.8), r.uniform(0.2, 0.8), r.uniform(0.22, 0.36)) for _ in range(4)]
        pulse = 0.08 * math.sin((frame + var * 2) / 8 * 2 * math.pi)
        for y in range(t):
            for x in range(t):
                u, v = (x + 0.5) / t, (y + 0.5) / t
                best = None
                for bx, by, br in blobs:
                    d = math.hypot(u - bx, v - by) / (br * (1 + pulse))
                    if d < 1 and (best is None or d < best[0]):
                        best = (d, u - bx, v - by)
                if best:
                    d, du, dv = best
                    l = -0.3 * d + (-du - dv) * 0.9
                    c = lit(mc, max(-0.5, min(0.5, l)))
                    if t >= 7 and d < 0.3 and (-du - dv) > 0:
                        c = mix(c, wd["moss_glow"], 0.6)
                    img[y][x] = c
        return img
    if BOOM <= kind <= GBOOM_END:
        stage = (kind - BOOM) % 4
        gems = kind >= GBOOM
        hot = [WHITE, (255, 236, 150), (255, 160, 70), (150, 70, 50)][stage]
        if gems:
            hot = mix(hot, wd["gem"], 0.45 + stage * 0.1)
        rad = [0.62, 0.72, 0.66, 0.5][stage]
        r = random.Random(var * 3 + stage)
        for y in range(t):
            for x in range(t):
                u, v = (x + 0.5) / t - 0.5, (y + 0.5) / t - 0.5
                a = math.atan2(v, u)
                d = math.hypot(u, v) / (rad * (0.85 + 0.15 * math.sin(a * 5 + var)))
                if d < 1:
                    img[y][x] = mix(hot, lit(hot, -0.5), d * d)
                else:
                    img[y][x] = mix(bg, hot, max(0.0, 0.5 - (d - 1)) * 0.6)
            if gems and t >= 5 and stage < 3:
                for _ in range(2):
                    img[r.randrange(t)][r.randrange(t)] = WHITE
        return img
    return img


RUNE_GLYPHS = [
    [(0.25, 0.2, 0.25, 0.8), (0.25, 0.5, 0.75, 0.2), (0.25, 0.5, 0.75, 0.8)],
    [(0.5, 0.18, 0.5, 0.82), (0.22, 0.4, 0.78, 0.4), (0.22, 0.75, 0.5, 0.55), (0.78, 0.75, 0.5, 0.55)],
    [(0.25, 0.25, 0.75, 0.75), (0.75, 0.25, 0.25, 0.75), (0.5, 0.15, 0.5, 0.35)],
    [(0.3, 0.2, 0.7, 0.2), (0.7, 0.2, 0.3, 0.8), (0.3, 0.8, 0.7, 0.8)],
]


def sprite_img(kind, wd, t, var, frame, face):
    """A t x t sprite with None where the cave shows through."""
    img = [[None] * t for _ in range(t)]
    outline = (12, 8, 14)
    if kind in (ROCK, ROCKF):
        base = wd["rock"]
        if t <= 3:                                         # tiny: a full block with dark corners (gems are a cross)
            for y in range(t):
                for x in range(t):
                    edge = (x in (0, t - 1)) + (y in (0, t - 1))
                    img[y][x] = lit(base, 0.2 if (x, y) == (0, 0) else -0.45 if edge == 2 else -0.1 if x + y > t - 1 else 0.05)
            return img
        r = random.Random(var * 19 + 3)
        wob = [r.uniform(-0.06, 0.05) for _ in range(6)]
        for y in range(t):
            for x in range(t):
                u, v = (x + 0.5) / t - 0.5, (y + 0.5) / t - 0.52
                a = math.atan2(v, u)
                rad = 0.53 if t <= 5 else 0.47 + wob[int((a + math.pi) / (2 * math.pi) * 6) % 6]
                d = math.hypot(u, v * 1.06) / rad
                if d >= 1:
                    continue
                nz = math.sqrt(max(0.0, 1 - d * d))
                l = (-u * 0.55 - v * 0.65) / rad * 0.8 + nz * 0.45 - 0.3
                h = hsh(x + var * 7, y, 21)
                c = lit(base, max(-0.42, min(0.5, l)) + ((h & 7) - 3.5) / 3.5 * 0.05)
                if t >= 6 and h % 17 == 0:
                    c = lit(c, -0.25)
                if t >= 6 and d > 1 - 1.15 / (t * 0.47):
                    c = mix(c, outline, 0.6)
                elif t < 6 and d > 0.8:
                    c = lit(c, -0.18)
                img[y][x] = c
        if t >= 8:                                         # a crack across the stone
            y0 = int(t * (0.35 + 0.1 * (var % 3)))
            for x in range(int(t * 0.3), int(t * 0.62)):
                y = y0 + (x % 3 == 0)
                if img[y][x] is not None:
                    img[y][x] = lit(base, -0.45)
        return img
    if kind in (GEM, GEMF):
        base = wd["gem"]
        glint = frame % 12
        for y in range(t):
            for x in range(t):
                u, v = (x + 0.5) / t - 0.5, (y + 0.5) / t - 0.5
                d = abs(u) / 0.44 + abs(v + 0.02) / 0.48
                if d >= 1:
                    continue
                crown = v < -0.1
                if crown:
                    c = lit(base, 0.35 if abs(u) < 0.14 else 0.15 if u < 0 else -0.05)
                else:
                    c = lit(base, 0.05 if u < 0 else -0.3)
                    if t >= 7 and abs(u) < 0.04 + (v + 0.1) * 0.0:
                        c = lit(base, -0.12)
                if t >= 5 and d > 1 - 1.2 / (t * 0.46):
                    c = mix(c, lit(base, -0.6), 0.7)
                if t >= 6 and abs(v + 0.1) < 0.5 / t:
                    c = lit(base, 0.5)
                img[y][x] = c
        if glint < 3 and t >= 3:                           # a glint travels round the stone
            gx, gy = int(t * (0.36 + 0.1 * glint)), int(t * 0.3)
            if 0 <= gx < t and 0 <= gy < t:
                img[gy][gx] = WHITE
                if t >= 7:
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        if img[gy + dy][gx + dx] is not None:
                            img[gy + dy][gx + dx] = mix(img[gy + dy][gx + dx], WHITE, 0.6)
        return img
    if kind == PLAYER:
        return pell_img(t, frame, face)
    if kind == CINDER:
        shell, hot = (70, 24, 18), (255, 120, 40)
        flick = 0.5 + 0.5 * math.sin(frame / 8 * 2 * math.pi * 2)
        for y in range(t):
            for x in range(t):
                u, v = (x + 0.5) / t - 0.5, (y + 0.5) / t - 0.52
                d = math.hypot(u / 0.46, v / 0.4)
                if t >= 6:
                    leg = abs(v - 0.0) < 0.34 and 0.44 < abs(u) < 0.5 and int((v + 0.3) * t) % 2 == (frame // 2) % 2
                    if leg and d >= 1:
                        img[y][x] = (40, 16, 12)
                        continue
                if d >= 1:
                    continue
                seam = abs(u) < 0.6 / t + 0.01
                c = mix(hot, (255, 230, 150), flick * 0.5) if (d < 0.5 or seam) else mix(shell, hot, (1 - d) * 0.8)
                if t >= 6 and v < -0.1 and d > 0.5:
                    c = lit(c, 0.2)
                if t >= 5 and d > 1 - 1.1 / (t * 0.44):
                    c = (40, 12, 8)
                img[y][x] = c
        if t >= 5:
            ey = int(t * 0.3)
            for ex in (int(t * 0.36), int(t * 0.62)):
                img[ey][ex] = (255, 250, 210)
        return img
    if kind == MOTH:
        wing = wd["moth"]
        flap = (1.0, 0.75, 0.42, 0.75)[frame % 4]
        for y in range(t):
            for x in range(t):
                u, v = (x + 0.5) / t - 0.5, (y + 0.5) / t - 0.5
                au = abs(u)
                if au < 0.07 + 0.5 / t and abs(v) < 0.34:
                    img[y][x] = (40, 30, 56) if t >= 4 else lit(wing, -0.5)
                    continue
                wu = au / max(0.05, flap)
                up = math.hypot((wu - 0.26) / 0.26, (v + 0.14) / 0.26)
                lo = math.hypot((wu - 0.2) / 0.2, (v - 0.2) / 0.18)
                d = min(up, lo)
                if d < 1:
                    c = mix(lit(wing, 0.45), wing, d)
                    if t >= 6 and d > 0.78:
                        c = lit(wing, 0.7)
                    if t >= 7 and up < 0.28:
                        c = mix(c, (255, 255, 255), 0.6)
                    img[y][x] = c
        return img
    return img


def pell_img(t, frame, face):
    """Pell the badger, head first: the white blaze between two black bands, grey coat, a brass helmet with its
    lamp, little black paws. frame: 0 stand, 1-2 walk, 3 push, 4 blink, 5-6 tap a foot."""
    img = [[None] * t for _ in range(t)]
    f = -1 if face == 3 else 1
    coat, coat_d, black, white = (150, 148, 160), (96, 94, 108), (22, 20, 26), (244, 242, 236)
    brass, brass_hi, brass_d = (214, 160, 56), (255, 222, 130), (140, 96, 30)
    lean = 0.07 * f if frame == 3 else 0.0
    bob = -0.03 if frame in (1, 2) else 0.0
    hx, hy, hr = 0.5 + lean + 0.03 * f, 0.47 + bob, 0.34
    for y in range(t):
        for x in range(t):
            u, v = (x + 0.5) / t, (y + 0.5) / t
            c = None
            # body and paws
            if math.hypot((u - 0.5 - lean * 0.4) / 0.33, (v - 0.84) / 0.15) < 1:
                c = coat_d if t >= 5 else coat
            step = 0.0 if frame not in (1, 2, 5, 6) else (0.07 if frame in (1, 5) else -0.07)
            for k, px_ in enumerate((0.3, 0.7)):
                lift = 0.05 if frame == 5 + k else 0.0
                if abs(u - px_ - (step if k == 0 else -step) * f) < 0.11 and 0.9 - lift < v < 1.0 - lift:
                    c = black
            du, dv = (u - hx) / hr, (v - hy) / (hr * 0.94)
            d = math.hypot(du, dv)
            if d < 1:
                if dv < -0.28:                                        # the helmet
                    c = brass
                    if dv < -0.62 and du * f < 0.1:
                        c = brass_hi
                    if t >= 6 and abs(dv + 0.34) < 0.9 / (t * hr):
                        c = brass_d                                   # the brim
                else:
                    s_ = du - 0.22 * f * (dv + 0.3)                    # the blaze leans with the snout
                    c = coat
                    if abs(s_) < 0.2:
                        c = white
                    elif abs(s_) < 0.5 and dv < 0.55:
                        c = black
                    elif dv > 0.25:
                        c = white                                     # cheeks
                    if t >= 7 and d > 0.88:
                        c = lit(c, -0.35)
            # the snout and nose, pointing the way Pell faces
            sn = math.hypot((u - hx - 0.25 * f) / 0.14, (v - hy - 0.12) / 0.1)
            if sn < 1:
                c = black if (sn < 0.45 and t >= 5) or ((u - hx) * f > 0.33) else white
            # the ears
            for k in (-1, 1):
                if math.hypot(u - hx - k * 0.27, v - hy + 0.2) < max(0.06, 0.6 / t) and c is None:
                    c = black
            # the lamp
            lp = math.hypot(u - hx - 0.16 * f, v - hy + 0.2)
            if lp < max(0.075, 0.6 / t):
                c = (255, 252, 220)
            if c is not None:
                img[y][x] = c
    if t >= 5 and frame != 4:                                         # the eye glints in the black band
        ex = int((hx + 0.15 * f) * t)
        ey = int((hy + 0.04) * t)
        if 0 <= ex < t and 0 <= ey < t:
            img[ey][ex] = (250, 250, 250) if t >= 8 else (200, 200, 210)
    if t >= 4:                                                        # a dark rim so Pell stands out
        for y in range(t):
            for x in range(t):
                if img[y][x] is None and any(0 <= x + dx < t and 0 <= y + dy < t and img[y + dy][x + dx] not in (None, (14, 10, 16))
                                             for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    img[y][x] = (14, 10, 16)
    return img


def runs_of(img):
    """A sprite as [(y, x, [colours])] runs, for fast slice drawing."""
    out = []
    for y, row in enumerate(img):
        x, n = 0, len(row)
        while x < n:
            if row[x] is None:
                x += 1
                continue
            s = x
            while x < n and row[x] is not None:
                x += 1
            out.append((y, s, row[s:x]))
    return out


def tile(kind, world, t, var=0, frame=0, mask=0, face=1):
    key = (kind, world, t, var, frame, mask, face)
    im = _TILE.get(key)
    if im is None:
        if len(_TILE) > 6000:
            _TILE.clear()
        wd = WORLDS[world]
        if kind in SPRITES:
            im = runs_of(sprite_img(kind, wd, t, var, frame, face))
        else:
            im = opaque_tile(kind, wd, t, var, frame, mask)
        _TILE[key] = im
    return im


# =============================================================================================
# The five worlds
# =============================================================================================
WORLDS = [
    dict(name="THE ROOTWARREN", short="ROOTWARREN", bg=(22, 15, 12), dirt=(124, 82, 48), pebble=(150, 120, 96),
         feature="roots", fleck=(180, 140, 90), brick=(156, 92, 60), steel=(78, 72, 78), rune=(84, 80, 96),
         rune_glow=(120, 220, 255), rock=(140, 128, 116), gem=(255, 204, 70), moth=(190, 210, 255),
         moss=(120, 196, 60), moss_glow=(210, 255, 140), accent=(240, 190, 110), back=((40, 26, 18), (16, 10, 8))),
    dict(name="THE GLOWMOSS GROTTO", short="GLOWMOSS", bg=(8, 20, 22), dirt=(48, 96, 84), pebble=(80, 130, 120),
         feature="glow", fleck=(150, 255, 210), brick=(70, 112, 104), steel=(62, 76, 84), rune=(70, 84, 104),
         rune_glow=(170, 255, 230), rock=(128, 142, 150), gem=(206, 150, 255), moth=(220, 190, 255),
         moss=(150, 220, 70), moss_glow=(230, 255, 150), accent=(120, 240, 200), back=((12, 42, 44), (4, 12, 14))),
    dict(name="THE EMBER SEAMS", short="EMBER SEAMS", bg=(24, 9, 8), dirt=(112, 52, 36), pebble=(140, 90, 70),
         feature="embers", fleck=(255, 150, 60), brick=(170, 72, 44), steel=(76, 64, 66), rune=(90, 70, 80),
         rune_glow=(255, 220, 120), rock=(132, 118, 120), gem=(120, 232, 255), moth=(255, 200, 170),
         moss=(170, 200, 60), moss_glow=(255, 255, 150), accent=(255, 150, 90), back=((52, 18, 12), (16, 6, 6))),
    dict(name="THE FROSTVEIN HOLLOWS", short="FROSTVEIN", bg=(8, 12, 26), dirt=(88, 108, 140), pebble=(150, 170, 200),
         feature="frost", fleck=(230, 245, 255), brick=(110, 140, 180), steel=(70, 78, 96), rune=(80, 90, 120),
         rune_glow=(160, 230, 255), rock=(152, 162, 182), gem=(255, 140, 180), moth=(255, 220, 250),
         moss=(110, 210, 150), moss_glow=(200, 255, 220), accent=(170, 220, 255), back=((20, 30, 56), (6, 8, 18))),
    dict(name="THE STARCORE", short="STARCORE", bg=(12, 7, 22), dirt=(78, 54, 112), pebble=(120, 96, 160),
         feature="stars", fleck=(255, 230, 255), brick=(124, 82, 168), steel=(70, 64, 88), rune=(86, 76, 112),
         rune_glow=(255, 160, 250), rock=(132, 122, 152), gem=(255, 238, 150), moth=(170, 240, 255),
         moss=(140, 230, 110), moss_glow=(230, 255, 180), accent=(220, 150, 255), back=((34, 18, 52), (8, 4, 16))),
]


# =============================================================================================
# The caves: twenty hand-made caves in five worlds, each world closed by a small intermission
#   #  ironstone (unbreakable)   =  packed clay (bursts)    .  soil       o  rock      *  sunstone
#   P  Pell                      E  the burrow door         c  cinderbeetle   m  glassmoth
#   ~  creepmoss                 R  rune seam
# =============================================================================================
CAVES = [
    # ---- the Rootwarren ----------------------------------------------------------------------------
    dict(world=0, name="THE FIRST DIG", quota=10, time=120, val=5, extra=10, hint="dig, take the sunstones, mind the rocks", map=[
        "########################################",
        "#P....o.....*.......o.....o.......*....#",
        "#.....o..*.......o..o.......*..o.......#",
        "#..*......o....o..*.......o.......o..*.#",
        "#.o....*.....o.........o.....*.........#",
        "#......o..o......*..o.......o.....o....#",
        "#..o.*........o..........*.......*..o..#",
        "#.......o...*....o...o......o..........#",
        "#.*..o.........o.......*..o.....o...*..#",
        "#.......o.*......*..........o..........#",
        "#..o.......o..o.....o..*.......*...o...#",
        "#....*..o..........o.....o.........o...#",
        "#..o.......*...o.......*....o..*.......#",
        "#.....o.........o..*.....o........o....#",
        "#.*.....o..*..........o.......o..*.....#",
        "#....o.......o...*..o.....*.......o....#",
        "#..o....*.......o........o....o.......*#",
        "#.......o...o......*........o....*.....#",
        "#..*..o.....*.....o...o..*.......o.....#",
        "#.....o.........o...........o.......o.E#",
        "#...o....*..o.....*....o........*......#",
        "########################################"]),
    dict(world=0, name="ROCKFALL GALLERY", quota=14, time=140, val=5, extra=10, hint="the stacks fall when the soil goes", map=[
        "########################################",
        "#P.....o..o..o..o..o..o..o..o..o.......#",
        "#......o..o..o..o..o..o..o..o..o.......#",
        "#......*..o..*..o..*..o..*..o..*.......#",
        "#......................................#",
        "#==.==.===.====.====.====.====.====..==#",
        "#..o....*....o....*.....o....*.........#",
        "#..o....o....o....o.....o....o.........#",
        "#..*....o....*....o.....*....o.........#",
        "#.......*.........*..........*.........#",
        "#.====.====.=====.=====.=====.=====..==#",
        "#.o.o.o.o.o.o.o.o.o.o.o.o.o.o.o.o......#",
        "#.*...*...*...*...*...*...*...*........#",
        "#......................................#",
        "#.oo..oo..oo..oo..oo..oo..oo..oo.......#",
        "#.**..**..**..**..**..**..**..**.......#",
        "#......................................#",
        "#====.======.======.======.======..====#",
        "#.o.....o.....o.....o.....o............#",
        "#.*..o..*..o..*..o..*..o..*..o.......E.#",
        "#....*.....*.....*.....*.....*.........#",
        "########################################"]),
    dict(world=0, name="BEETLE BURROWS", quota=12, time=150, val=6, extra=12, hint="cinderbeetles keep a wall on their left", map=[
        "########################################",
        "#P..........o.....*.........o......*...#",
        "#.....*.......o.........*.........o....#",
        "#..=======........====......=======....#",
        "#..=c    =..o.....=c =..*...=     =..*.#",
        "#..=     =........=  =......=   c =....#",
        "#..=======..*.....====......=======....#",
        "#.....o...........o......o.............#",
        "#..*.......o..*.........*.....o...*....#",
        "#.o.....o.......o.....o......o.........#",
        "#....          ....*.....          ....#",
        "#....  c       ..o.......       c  ..*.#",
        "#....          ......*...          ....#",
        "#..*......o.........o......o.....o.....#",
        "#......*......o.........*........*.....#",
        "#..o........o.....*........o..........*#",
        "#.....=====......=====......=====......#",
        "#..*..=c  =..o...=  c=..*...=c  =...o..#",
        "#.....=====......=====......=====......#",
        "#..o.......*.........o.....*.........E.#",
        "#.*....o.......*.........o.......*.....#",
        "########################################"]),
    dict(world=0, name="THE ROOT CELLAR", quota=15, time=160, val=6, extra=12, hint="push a rock: lean on it twice", map=[
        "########################################",
        "#P   o  ...........====........*.......#",
        "#=====  ..o...*....=**=....o.......o...#",
        "#....=  .....o.....=**=........*.......#",
        "#.*..=  ..*........====...o.......o....#",
        "#....=      o   ....... .....*.........#",
        "#..o.======.=====.....=======......o...#",
        "#....=*.*.*.*.*.=.....=o.o.o=..*.......#",
        "#....=.........o=..*..=*.*.*=......*...#",
        "#.o..====.=======.....==.====....o.....#",
        "#.........o.........o..........*.......#",
        "#..*.....o..*..o.........o.........o...#",
        "#......o..........*.......o....*.......#",
        "#..=================.......===========.#",
        "#..=o*o*o*o*o*o*o*o=..*....=*.*.*.*.*=.#",
        "#..=...............=.......=.........=.#",
        "#..=======.=========...o...=====.=====.#",
        "#.o.....*........o.....*.........o.....#",
        "#....o.......*.......o.......*.........#",
        "#..*.....o.......o.......*.......o..E..#",
        "#......*.....*.......*.......o.........#",
        "########################################"]),
    dict(world=0, name="SUNSTONE SHOWER", inter=True, quota=10, time=40, val=10, extra=20, hint="intermission: no life to lose", map=[
        "####################",
        "#o*o*o*o*o*o*o*o*o*#",
        "#..................#",
        "#.=.=.=.=.=.=.=.=..#",
        "#..................#",
        "#*o*o*o*o*o*o*o*o*.#",
        "#..................#",
        "#..=.=.=.=.=.=.=.=.#",
        "#..................#",
        "#.....P........E...#",
        "#..................#",
        "####################"]),
    # ---- the Glowmoss Grotto -----------------------------------------------------------------------
    dict(world=1, name="GLASSWING HOLLOW", quota=15, time=150, val=6, extra=12, hint="a glassmoth crushed is nine sunstones", map=[
        "########################################",
        "#P.........*.......o.........*.........#",
        "#....o..........*.......o..........o...#",
        "#..*....ooooooo.......*.....ooooooo....#",
        "#......=       =..o........=       =.*.#",
        "#..o...=   m   =......o....=   m   =...#",
        "#......=       =...*.......=       =...#",
        "#.*....=========.......*...=========...#",
        "#.........*.......o.....o..........*...#",
        "#...o.........*.........*.....o........#",
        "#.......*.....................o....*...#",
        "#..ooooooo....o..*....ooooooo........o.#",
        "#.=       =...........=       =..*.....#",
        "#.=   m   =..*...o....=   m   =........#",
        "#.=       =...........=       =...o....#",
        "#.=========.....*.....=========..*.....#",
        "#....*.......o.........*.......o.......#",
        "#..o.....*.......o.........*.......*...#",
        "#......o....*......*...o......o........#",
        "#.*........o.....o........*........E...#",
        "#....o.........*.......o.......*.......#",
        "########################################"]),
    dict(world=1, name="THE GREEN CREEP", quota=16, time=150, val=6, extra=12, moss_slow=20, moss_limit=110,
         hint="creepmoss eats the soil: be quick", map=[
        "########################################",
        "#P....*.....o.......*.......o....*.....#",
        "#..o......*......o......*.......o...*..#",
        "#.....o.......*.......o.....*..........#",
        "#.*.......o.......*.......o.......*..o.#",
        "#....*........o.......*......o.........#",
        "#..o....*..........~~.........*....o...#",
        "#.......o....*.....~~....*........*....#",
        "#.*..o.......o..........o......o.......#",
        "#......*.........*...........*.....o...#",
        "#..o.......o.........o..*........*.....#",
        "#.....*.......*..o........o.........*..#",
        "#.*.......o..........*..........o......#",
        "#....o........*..o.......o..*.......*..#",
        "#..*.....*..........*..........o.......#",
        "#.....o......o..*.......o.*.......o....#",
        "#.*.......*..........o.........*.......#",
        "#....o.......*...o.......*.......o..*..#",
        "#..*.....o.......*...........o.........#",
        "#......*.....o........*...o......*...E.#",
        "#..o.......*.......o..........*........#",
        "########################################"]),
    dict(world=1, name="LANTERN STEPS", quota=16, time=160, val=7, extra=14, hint="rocks roll down the steps", map=[
        "########################################",
        "#P..*..o.o.o.o.o..*....................#",
        "#=====..........o.o.o.o.o..*...........#",
        "#....=====.........*......o.o.o.o..*...#",
        "#.*......=====.......................*.#",
        "#............=====.......*.........====#",
        "#..o.*...........=====.........=====...#",
        "#....................=====..=====....*.#",
        "#.*..o..*..o..*...........*............#",
        "#......................................#",
        "#===.......o.o.o.o.o.o.o.o.o.......====#",
        "#..===.....*.*.*.*.*.*.*.*.*.....===...#",
        "#....===.....................===....*..#",
        "#.*....===.................===.........#",
        "#........===....m........===......o....#",
        "#..o.......===.........===.......*.....#",
        "#.....*......====...====.....*.........#",
        "#..*.....o.......===.......o......*....#",
        "#......*.....*.........*.......o.......#",
        "#..o......o......*.........o.......E...#",
        "#.....*.......o......*.........*.......#",
        "########################################"]),
    dict(world=1, name="MOTHS IN THE MOSS", quota=18, time=170, val=7, extra=14, moss_slow=25, moss_limit=90,
         hint="the moss bursts glassmoths that touch it", map=[
        "########################################",
        "#P.....*......o.......*.......o....*...#",
        "#..o.......*......*.......o........o...#",
        "#.....=================.....*..........#",
        "#..*..=  m          ~ =..o.......*.....#",
        "#.....=================......*.....o...#",
        "#.o.......*......o...........o.........#",
        "#.....*.......o.......*..........*..o..#",
        "#..*.......=================.......*...#",
        "#......o...=~           m  =..o........#",
        "#.*........=================.....*.....#",
        "#.....o.......*.......o.......*........#",
        "#..*.......o.......*......*.......o....#",
        "#......*.......o.......o........*......#",
        "#.o..======================......*..o..#",
        "#....=m                  ~=..*.........#",
        "#..*.======================.......*....#",
        "#.......o.....*......o.......*.....o...#",
        "#..*.......*.......*......o.......*....#",
        "#.....o.......o........*......o.....E..#",
        "#..*......*.......o........*.......*...#",
        "########################################"]),
    dict(world=1, name="THE SEALED GARDEN", inter=True, quota=10, time=45, val=10, extra=20, moss_slow=4, moss_p=(0.06, 0.12),
         hint="shut in, the moss turns to sunstones", map=[
        "####################",
        "#P.......*.......*.#",
        "#..===========.....#",
        "#..=~        =..*..#",
        "#..=         =.....#",
        "#..===========..*..#",
        "#.*...*...*........#",
        "#..===========..*..#",
        "#..=        ~=.....#",
        "#..===========..E..#",
        "#.*...*.......*....#",
        "####################"]),
    # ---- the Ember Seams ---------------------------------------------------------------------------
    dict(world=2, name="CINDER RUN", quota=16, time=150, val=7, extra=14, hint="give the beetles their tunnels", map=[
        "########################################",
        "#P..*......o.......*......o.......*....#",
        "#.....o.......*.........*.......o......#",
        "#..                              ..*...#",
        "#.. ............................ ......#",
        "#.. .*...o...*....o...*...o..*.. ..o...#",
        "#.. ............................ ......#",
        "#..c                             ..*...#",
        "#....*......o........*......o..........#",
        "#..o.....*......o.........*.......*....#",
        "#.....                         c.......#",
        "#.*... .*...o..*...o..*...o..*. ...o...#",
        "#..... ........................ .......#",
        "#.o...                          ...*...#",
        "#.....*......o.......*......o..........#",
        "#..*......o.......*......o.......*..o..#",
        "#.....o.......*.......o......*.........#",
        "#.*.......*.......o.......*......*.....#",
        "#....o......*........*.......o.........#",
        "#..*......o......*......o.........*.E..#",
        "#......*......o......*.......o.........#",
        "########################################"]),
    dict(world=2, name="THE CLAY VAULTS", quota=18, time=170, val=7, extra=14, hint="a burst cracks packed clay", map=[
        "########################################",
        "#P...*......o.........*.....o.......*..#",
        "#..o.....*.......o.........*......o....#",
        "#....=====....=====....=====....=====..#",
        "#.*..=***=....=***=....=***=....=***=..#",
        "#....=***=..*.=***=..*.=***=..*.=***=..#",
        "#....=====....=====....=====....=====..#",
        "#..o.....o.......o........o.......o....#",
        "#.....*.......*......*.......*.........#",
        "#.o.......o.......o.......o.......o....#",
        "#....                            ..*...#",
        "#..*. c                        c ......#",
        "#.... ...o...*...o...*...o...*.. ..o...#",
        "#.o..                            ......#",
        "#.....*.......*.......*.......*........#",
        "#..o......o.......o.......o......*.....#",
        "#......*......*.......*......*.......o.#",
        "#.*.......o.......o.......o............#",
        "#.....*.......*.......*.......*....*...#",
        "#..o......o.......o.......o.......E....#",
        "#......*.......*.......*.......*.......#",
        "########################################"]),
    dict(world=2, name="RUNE FORGE", quota=20, time=170, val=6, extra=12, rune=25, hint="rock through a glowing seam is a sunstone", map=[
        "########################################",
        "#P..*..................................#",
        "#.oooo.oooo.oooo.oooo.oooo.oooo.oooo...#",
        "#.oooo.oooo.oooo.oooo.oooo.oooo.oooo...#",
        "#......................................#",
        "#RRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRR..#",
        "#                                    ..#",
        "#                                    ..#",
        "#.....................................##",
        "#..*......o......*......o......*.......#",
        "#.....o......*......o......*......o....#",
        "#..*......*......o......*......o.......#",
        "#.....o......*......*......o......*....#",
        "#.*......o......*......o......*........#",
        "#=====.=======.=======.=======.=====...#",
        "#..o.....*......o......*......o........#",
        "#.....*......o......*......o......*....#",
        "#..o......*......*......o......*.......#",
        "#.....*......o......*......o.......o...#",
        "#.*......*......o......*......*....E...#",
        "#.....o......*......o......*...........#",
        "########################################"]),
    dict(world=2, name="MAGMA STAIR", quota=18, time=170, val=8, extra=16, hint="clay ledges and rolling rock", map=[
        "########################################",
        "#P.o.o.o.o.o.o.o.o.o.o.o.o.o.o.o.o.o.o.#",
        "#.*.*.*.*.*.*.*.*.*.*.*.*.*.*.*.*.*.*..#",
        "#......................................#",
        "#.=.=.=.=.=.=.=.=.=.=.=.=.=.=.=.=.=.=..#",
        "#......................................#",
        "#..o.....o.....o.....o.....o.....o.....#",
        "#..*.....*.....*.....*.....*.....*.....#",
        "#..=.....=.....=.....=.....=.....=.....#",
        "#.....c                          ......#",
        "#..... .....o.....o.....o.....o. ...*..#",
        "#..... ......................... ......#",
        "#..*..                           ......#",
        "#........*.....*.....*.....*.....*.....#",
        "#..o..o..o..o..o..o..o..o..o..o..o..o..#",
        "#..=..=..=..=..=..=..=..=..=..=..=..=..#",
        "#......................................#",
        "#.*.....*.....*.....*.....*.....*......#",
        "#....o.....o.....o.....o.....o.....o...#",
        "#..*.....*.....*.....*.....*.....*...E.#",
        "#......................................#",
        "########################################"]),
    dict(world=2, name="SPARK TRAP", inter=True, quota=8, time=40, val=12, extra=24, hint="drop a rock on the moth", map=[
        "####################",
        "#P..o..o..o..o..o..#",
        "#.....*.....*......#",
        "#..oooooooooooooo..#",
        "#..=            =..#",
        "#..=  m         =..#",
        "#..==============..#",
        "#.*..*..*..*..*....#",
        "#..................#",
        "#.*..*..*..*..*..E.#",
        "#..................#",
        "####################"]),
    # ---- the Frostvein Hollows ---------------------------------------------------------------------
    dict(world=3, name="ICE SIEVE", quota=22, time=170, val=6, extra=12, rune=30, hint="the seam glows only for a while", map=[
        "########################################",
        "#P.................................*...#",
        "#..o.o.o.o.o.o.o.o..*..o.o.o.o.o.o.o...#",
        "#..o.o.o.o.o.o.o.o.....o.o.o.o.o.o.o...#",
        "#......................................#",
        "#..RRRRRRRRRRRRRRRR.....RRRRRRRRRRRRR..#",
        "#..                .....             ..#",
        "#..                ..*..             ..#",
        "#.....................................##",
        "#.*.....o......*.......o......*......*.#",
        "#.....*......o.....*......o.....*......#",
        "#..o......*.....o......*.....o.....*...#",
        "#.....*......*......o......*......o....#",
        "#.====.======.======.======.======.====#",
        "#..*......o......*......o......*.......#",
        "#.....o......*......o......*......o....#",
        "#..*......*......o......*......*.......#",
        "#.....o......*......*......o......*....#",
        "#.*......o......*......o......*.....E..#",
        "#.....*......o......*......o...........#",
        "#..o......*......*......o......*.......#",
        "########################################"]),
    dict(world=3, name="FROZEN ROLL", quota=20, time=170, val=7, extra=14, hint="rocks slide off rocks: stand aside", map=[
        "########################################",
        "#P.......ooo.......ooo.......ooo.......#",
        "#.......ooooo.....ooooo.....ooooo..*...#",
        "#..*...ooo*ooo...ooo*ooo...ooo*ooo.....#",
        "#.......*.*.*.....*.*.*.....*.*.*......#",
        "#......................................#",
        "#..*.......*.......*.......*.......*...#",
        "#=====..=====..=====..=====..=====..===#",
        "#..o.......o.......o.......o.......o...#",
        "#.*o*.....*o*.....*o*.....*o*.....*o*..#",
        "#..o.......o.......o.......o.......o...#",
        "#......................................#",
        "#...=====..=====..=====..=====..=====..#",
        "#....*.......*.......*.......*.......*.#",
        "#..ooo.....ooo.....ooo.....ooo.....ooo.#",
        "#..*.*.....*.*.....*.*.....*.*.....*.*.#",
        "#......................................#",
        "#.*.....*.....*.....*.....*.....*......#",
        "#....o.....o.....o.....o.....o.....o...#",
        "#..*.....*.....*.....*.....*.....*..E..#",
        "#......................................#",
        "########################################"]),
    dict(world=3, name="GLASSWING MAZE", quota=20, time=180, val=7, extra=14, hint="moths circle the frozen halls", map=[
        "########################################",
        "#P....*.......o........*.......o.......#",
        "#..o......*.......*.......o.......*....#",
        "#.....                       ......o...#",
        "#.*.. ===========.=========== ..*......#",
        "#.... =.*.o.*.o.=.=.o.*.o.*.= ......o..#",
        "#..o. =.........=.=.........= ..*......#",
        "#.... ===========.=========== .........#",
        "#..*.m                       ....o..*..#",
        "#.......o.......*.......o..............#",
        "#..*.......*........*........*.....o...#",
        "#.....o.......o.........o.........*....#",
        "#..*...                       m ...*...#",
        "#..... ===========.=========== ........#",
        "#.o... =.*.o.*.o.=.=.o.*.o.*.= ..o.....#",
        "#..... =.........=.=.........= .....*..#",
        "#..*.. ===========.=========== ........#",
        "#.....                         ..o.....#",
        "#..o......*.......o.......*......*.....#",
        "#.....*.......*.......*.......o.....E..#",
        "#..*.......o.......*.......*...........#",
        "########################################"]),
    dict(world=3, name="THE DEEP THAW", quota=22, time=180, val=7, extra=14, moss_slow=30, moss_limit=130,
         hint="the moss grows into rock when it gets too big", map=[
        "########################################",
        "#P...*.......o.......*.......o....*....#",
        "#.o......*.......o.......*.......o.....#",
        "#.....o.......*.......o.......*.....*..#",
        "#..*......o.......*.......o.......o....#",
        "#.....*.......o.......*.......*........#",
        "#.o......*........~.......o.......*....#",
        "#.....o.......*.......*.......o.....o..#",
        "#..*.......o.......o.......*...........#",
        "#......*.......*.......o.......*....*..#",
        "#.o.......o.......*.......o............#",
        "#.....*.......*.......*.......*..o.....#",
        "#..*.......o.......o.......o.......*...#",
        "#......*.......*.......~.......*.......#",
        "#.o.......o.......*.......o.......o....#",
        "#.....*.......*.......*.......*........#",
        "#..*.......o.......o.......o......*....#",
        "#......*.......*.......*.......*.......#",
        "#.o.......o.......*.......o.......o....#",
        "#.....*.......*.......*.......*...E....#",
        "#..*.......o.......o.......*...........#",
        "########################################"]),
    dict(world=3, name="SNOWGLOBE", inter=True, quota=12, time=40, val=12, extra=24, rune=12, hint="quick: the seam fades fast", map=[
        "####################",
        "#P.oooooooooooooo..#",
        "#..oooooooooooooo..#",
        "#..................#",
        "#..RRRRRRRRRRRRRR..#",
        "#..              ..#",
        "#..              ..#",
        "#..................#",
        "#..*.*.*....*.*.*..#",
        "#..............E...#",
        "#..................#",
        "####################"]),
    # ---- the Starcore ------------------------------------------------------------------------------
    dict(world=4, name="STARFALL", quota=24, time=170, val=8, extra=16, hint="stars rain when the soil is gone", map=[
        "########################################",
        "#P.*.*.*.*.*.*.*.*.*.*.*.*.*.*.*.*.*.*.#",
        "#.o.o.o.o.o.o.o.o.o.o.o.o.o.o.o.o.o.o..#",
        "#.*.*.*.*.*.*.*.*.*.*.*.*.*.*.*.*.*.*..#",
        "#......................................#",
        "#.=..=..=..=..=..=..=..=..=..=..=..=...#",
        "#......................................#",
        "#..*..o..*..o..*..o..*..o..*..o..*..o..#",
        "#......................................#",
        "#.c                                  ..#",
        "#.. ................................ ..#",
        "#.. ..*..*..o..*..*..o..*..*..o..*.. ..#",
        "#.. ................................ ..#",
        "#..                                 c..#",
        "#......................................#",
        "#..o..*..o..*..o..*..o..*..o..*..o..*..#",
        "#......................................#",
        "#.*..*..*..*..*..*..*..*..*..*..*..*...#",
        "#..o.....o.....o.....o.....o.....o.....#",
        "#......*.....*.....*.....*.....*....E..#",
        "#..*.....*.....*.....*.....*...........#",
        "########################################"]),
    dict(world=4, name="THE ORRERY", quota=24, time=180, val=8, extra=16, hint="beetles and moths on their orbits", map=[
        "########################################",
        "#P....*.......o.......*.......o....*...#",
        "#..o......*.......*.......o.......*....#",
        "#....         .....*.....         .....#",
        "#.*.. ....... ..o.....o.. ....... ..*..#",
        "#.... ..*o*.. .....*..... ..*o*.. .....#",
        "#..o. ....... ..*.....*.. ....... ..o..#",
        "#....c        .....o.....        m.....#",
        "#.*.......*.......*.......*.......*....#",
        "#.....o.......o.......o.......o........#",
        "#..*.......*.......*.......*.......*...#",
        "#.....o.......*.......*.......o........#",
        "#..*.         ..*.....*..         .*...#",
        "#.... ....... ........... ....... .....#",
        "#.o.. ..*o*.. ..o.....o.. ..*o*.. ..o..#",
        "#.... ....... ........... ....... .....#",
        "#..*.m        .....*.....        c.*...#",
        "#.....o.......*.......*.......o........#",
        "#..*.......o.......o.......*.......*...#",
        "#.....*.......*.......*.......*....E...#",
        "#..o.......*.......o.......*...........#",
        "########################################"]),
    dict(world=4, name="COMET VEINS", quota=26, time=190, val=8, extra=16, rune=25, moss_slow=40, moss_limit=100,
         hint="everything the deep has, at once", map=[
        "########################################",
        "#P..*.......o.......*.......o.......*..#",
        "#.o.o.o.o.o.o.o.o..*...o.o.o.o.o.o.o...#",
        "#......................................#",
        "#.RRRRRRRRRRRRRRRR.....RRRRRRRRRRRRRR..#",
        "#.                .....              ..#",
        "#.................................... ##",
        "#..*.....o.....*.....o.....*.....o.....#",
        "#.....*.....o.....*.....o.....*........#",
        "#..o.....*.....~.....*.....o.....*.....#",
        "#.....*.....o.....*.....o.....*.....o..#",
        "#..*.....o.....*.....o.....*.....*.....#",
        "#....                           c......#",
        "#.*.. .o..*..o..*..o..*..o..*.. ...*...#",
        "#.... ......................... .......#",
        "#..o.m                          ...o...#",
        "#.....*.....o.....*.....o.....*........#",
        "#..*.....*.....o.....*.....o.....*.....#",
        "#.....o.....*.....*.....o.....*.....o..#",
        "#..*.....o.....*.....o.....*......E....#",
        "#.....*.....*.....o.....*.....*........#",
        "########################################"]),
    dict(world=4, name="HEART OF STARS", quota=30, time=200, val=9, extra=18, rune=30, hint="the last sunstones of the deep", map=[
        "########################################",
        "#P.*....o.......*.......o.......*......#",
        "#..o.o.o.o.o..*.....*..o.o.o.o.o.o..*..#",
        "#......................................#",
        "#..RRRRRRRRRR....=====....RRRRRRRRRR...#",
        "#..          ....=***=....          ...#",
        "#...............=***=..................#",
        "#..*.....o......=====......o.....*.....#",
        "#.....*......*..........*......*.......#",
        "#.c                                  ..#",
        "#.. ..*..o..*..o..*..o..*..o..*..o.. ..#",
        "#.. ................................ ..#",
        "#..                                 m..#",
        "#..o.....*......o.......*......o.......#",
        "#.....*......o......*......o......*....#",
        "#..*......*......o......*......*.......#",
        "#.====.======.======.======.======.====#",
        "#..*......o......*......o......*.......#",
        "#.....o......*......o......*......o....#",
        "#..*......*......o......*......*...E...#",
        "#.....*......o......*......o...........#",
        "########################################"]),
    dict(world=4, name="LAST LIGHT", inter=True, quota=14, time=45, val=15, extra=30, hint="the last sunstones before the dawn", map=[
        "####################",
        "#P*.*.*.*.*.*.*.*..#",
        "#.o.o.o.o.o.o.o.o..#",
        "#..................#",
        "#.*.*.*.*.*.*.*.*..#",
        "#..=.=.=.=.=.=.=...#",
        "#.*.*.*.*.*.*.*.*..#",
        "#..................#",
        "#.m              ..#",
        "#..............E...#",
        "#..................#",
        "####################"]),
]


# =============================================================================================
# Sound: soft earthy thuds, bright chimes for the sunstones
# =============================================================================================
def _chime(f, v=0.26):
    return [dict(w="tri", f=f, d=0.05, v=v), dict(w="sine", f=f * 1.5, d=0.16, v=v * 0.6, at=0.03, vib=(7, 0.1))]


SND = Sound(GAME, {
    "dig": [dict(w="noise", f=900, f2=300, d=0.05, v=0.1)],
    **{"gem%d" % i: _chime(f) for i, f in enumerate((1047, 1175, 1319, 1397, 1568, 1760))},
    "thud": [dict(w="noise", f=420, f2=90, d=0.09, v=0.26), dict(w="tri", f=110, f2=70, d=0.08, v=0.22, at=0)],
    "ting": [dict(w="sine", f=2093, f2=2000, d=0.08, v=0.14), dict(w="noise", f=7000, d=0.02, v=0.05, at=0)],
    "push": [dict(w="noise", f=300, f2=200, d=0.12, v=0.16), dict(w="saw", f=80, d=0.1, v=0.08, at=0)],
    "boom": [dict(w="noise", f=1100, f2=50, d=0.5, v=0.55), dict(w="tri", f=120, f2=36, d=0.4, v=0.45, at=0)],
    "gboom": [dict(w="noise", f=1400, f2=80, d=0.4, v=0.45), dict(w="tri", f=120, f2=40, d=0.3, v=0.35, at=0)] +
             [dict(w="tri", f=f, d=0.05, v=0.2, at=0.18 + k * 0.05) for k, f in enumerate((1568, 1976, 2349, 3136))],
    "door": [dict(w="tri", f=f, d=0.07, v=0.28) for f in (523, 659, 784, 1047)] +
            [dict(w="tri", f=1319, d=0.35, v=0.3, vib=(6, 0.2), r="lin")],
    "exit": [dict(w="tri", f=784, f2=1568, d=0.2, v=0.3), dict(w="sine", f=2093, d=0.25, v=0.16)],
    "die": [dict(w="saw", f=330, f2=110, d=0.3, v=0.3), dict(w="noise", f=600, f2=60, d=0.5, v=0.3, at=0.05)],
    "timeout": [dict(w="tri", f=440, f2=220, d=0.3, v=0.3), dict(w="tri", f=220, f2=110, d=0.5, v=0.3, r="lin")],
    "beep": [dict(w="square", f=1760, d=0.04, v=0.12, duty=0.3)],
    "moss": [dict(w="sine", f=f, d=0.08, v=0.18) for f in (392, 523, 659, 784)],
    "stone": [dict(w="noise", f=500, f2=80, d=0.3, v=0.3), dict(w="tri", f=98, d=0.25, v=0.25, at=0)],
    "rune": [dict(w="sine", f=880, f2=1760, d=0.35, v=0.18, vib=(9, 0.3)), dict(w="tri", f=440, d=0.3, v=0.1, at=0)],
    "sieve": [dict(w="sine", f=1568, f2=1319, d=0.12, v=0.14)],
    "tally": [dict(w="square", f=1319, d=0.02, v=0.08, duty=0.25)],
    "life": [dict(w="tri", f=f, d=0.06, v=0.28) for f in (784, 988, 1175, 1568, 1175, 1568)] +
            [dict(w="tri", f=1976, d=0.3, v=0.3, vib=(6, 0.2))],
    "over": [dict(w="tri", f=523, d=0.18, v=0.34), dict(w="tri", f=466, d=0.18, v=0.34), dict(w="tri", f=392, d=0.18, v=0.34),
             dict(w="tri", f=330, f2=262, d=0.7, v=0.36, r="lin")],
    "won": [dict(w="tri", f=f, d=0.12, v=0.3) for f in (523, 659, 784, 1047, 784, 1047, 1319)] +
           [dict(w="tri", f=1568, d=0.8, v=0.34, vib=(6, 0.25), r="lin")],
    "menu": [dict(w="tri", f=660, d=0.025, v=0.2)],
    "start": [dict(w="tri", f=392, d=0.06, v=0.3), dict(w="tri", f=523, d=0.06, v=0.3), dict(w="tri", f=784, d=0.16, v=0.3)],
    "pause": [dict(w="tri", f=523, f2=392, d=0.07, v=0.22)],
    "sound_on": [dict(w="tri", f=440, d=0.06, v=0.35), dict(w="tri", f=880, d=0.12, v=0.35)],
})


def help_lines(kitty=True):
    mode = (["Your terminal reports key releases: Pell walks exactly as long",
             "as you hold a direction."] if kitty else
            ["Classic keys: a tap moves one cell, holding keeps walking once",
             "the terminal starts repeating the key."])
    return ["GEMBURROW - keys", "",
            "Arrows / WASD             walk and dig (one cell per tick)",
            "Space + direction         reach: dig or take without moving",
            "R                         give up the cave (costs a life)",
            "Esc / P                   pause menu (Q there: quit, M sound)",
            "?                         this help", ""] + mode + [
            "",
            "Take the cave's quota of sunstones and the burrow door opens.",
            "Rocks and sunstones fall when the soil under them is gone and",
            "roll off each other; a falling one crushes. Push a rock by",
            "walking into it twice. Cinderbeetles (wall on their left) and",
            "glassmoths (wall on their right) burst when touched or hit;",
            "glassmoths burst into sunstones. Creepmoss spreads: shut in, it",
            "turns to sunstones, grown too big it turns to rock. A struck",
            "rune seam glows a while: rock falls through it as a sunstone.",
            "Extra life every %d points and for each intermission." % EXTRA_EVERY]


# =============================================================================================
# The game: lives, score, the caves one after another
# =============================================================================================
class Game:
    INTRO = 2.4

    def __init__(self, diff=1, start=0, seed=None, quiet=False, demo=False):
        self.rnd = random.Random(seed)
        self.diff = diff
        self.demo = demo
        self.quiet = quiet or demo
        self.score = 0
        self.lives = DIFFS[diff]["lives"]
        self.next_extra = EXTRA_EVERY
        self.cave_i = self.first = start
        self.hi = 0 if demo else (load_scores().get(GAME, {}).get(DIFFS[diff]["key"]) or 0)
        self.over = self.won = self.paused = self.help = False
        self.clock = 0.0
        self.deaths = 0
        self.cleared = 0
        self.parts, self.floats = [], []
        self.start_cave()

    def snd(self, name, vol=1.0, gap=0.04):
        if not self.quiet:
            SND.play(name, vol, gap)

    def start_cave(self):
        self.spec = CAVES[self.cave_i]
        self.world = self.spec["world"]
        self.inter = self.spec.get("inter", False)
        self.cave = Cave(self.spec, self.diff, seed=self.rnd.randrange(1 << 30))
        self.state, self.state_t = "intro", 0.0
        self.acc = 0.0
        self.moves = {}
        self.shake = 0.0
        self.flash = 0.0
        self.idle = 0
        self.tally = None
        self.parts, self.floats = [], []
        self.cam = self.cam_on(self.cave.exit)
        self.cam_start = self.cam

    # --- labels ---------------------------------------------------------------------------------
    def label(self):
        if self.inter:
            return "%d-I" % (self.world + 1)
        n = sum(1 for k in range(self.cave_i) if CAVES[k]["world"] == self.world and not CAVES[k].get("inter"))
        return "%d-%d" % (self.world + 1, n + 1)

    def seconds(self):
        return max(0, int(math.ceil(self.cave.ticks_left * TICK)))

    # --- the camera ----------------------------------------------------------------------------
    def cam_on(self, i, x=None, y=None):
        c = self.cave
        if x is None:
            x, y = c.xy(i)
        return (clamp(x + 0.5 - VW / 2, 0, max(0, c.w - VW)), clamp(y + 0.5 - VH / 2, 0, max(0, c.h - VH)))

    def frac(self):
        return clamp(self.acc / TICK, 0.0, 1.0) if self.state in ("play", "dead") else 1.0

    def pos(self, i):
        """Where the thing in cell i is drawn (in cells), between the cell it came from and i."""
        c = self.cave
        x, y = c.xy(i)
        f = self.moves.get(i)
        if f is None:
            return x, y
        fx, fy = c.xy(f)
        k = self.frac()
        return fx + (x - fx) * k, fy + (y - fy) * k

    def update_cam(self, dt):
        c = self.cave
        if self.state == "intro":
            k = clamp((self.state_t - 0.5) / (self.INTRO - 1.0), 0.0, 1.0)
            k = k * k * (3 - 2 * k)
            to = self.cam_on(c.player)
            self.cam = (self.cam_start[0] + (to[0] - self.cam_start[0]) * k,
                        self.cam_start[1] + (to[1] - self.cam_start[1]) * k)
            return
        px, py = self.pos(c.player)
        cx, cy = self.cam
        tx, ty = cx, cy
        if px + 0.5 - (cx + VW / 2) > 2.5:              # a dead zone in the middle: the view moves when Pell
            tx = px + 0.5 - VW / 2 - 2.5                  # walks out of it, and glides there
        elif (cx + VW / 2) - (px + 0.5) > 2.5:
            tx = px + 0.5 - VW / 2 + 2.5
        if py + 0.5 - (cy + VH / 2) > 1.5:
            ty = py + 0.5 - VH / 2 - 1.5
        elif (cy + VH / 2) - (py + 0.5) > 1.5:
            ty = py + 0.5 - VH / 2 + 1.5
        tx, ty = clamp(tx, 0, max(0, c.w - VW)), clamp(ty, 0, max(0, c.h - VH))
        k = min(1.0, dt * 7)
        self.cam = (cx + (tx - cx) * k, cy + (ty - cy) * k)

    # --- scoring and effects -------------------------------------------------------------------
    def add(self, pts, x=None, y=None, col=(255, 236, 150)):
        self.score += pts
        if x is not None and pts:
            self.floats.append([x, y, "+%d" % pts, 0.0, col])
            if len(self.floats) > 10:
                del self.floats[0]
        while self.score >= self.next_extra:
            self.next_extra += EXTRA_EVERY
            self.lives += 1
            self.snd("life")
            px, py = self.cave.xy(self.cave.player)
            self.floats.append([px + 0.5, py - 0.6, "EXTRA LIFE", -0.3, (255, 240, 200)])

    def burst(self, x, y, n, cols, spd=3.0, life=0.6, grav=9.0, up=1.5):
        r = self.rnd
        for _ in range(n):
            a = r.uniform(0, 2 * math.pi)
            v = r.uniform(0.3, 1.0) * spd
            self.parts.append([x, y, math.cos(a) * v, math.sin(a) * v - up, 0.0, life * r.uniform(0.6, 1.2),
                               r.choice(cols), grav])
        if len(self.parts) > 360:
            del self.parts[:len(self.parts) - 360]

    def fx(self, dt):
        keep = []
        for p in self.parts:
            p[4] += dt
            if p[4] < p[5]:
                p[3] += p[7] * dt
                p[0] += p[2] * dt
                p[1] += p[3] * dt
                keep.append(p)
        self.parts = keep
        for f in self.floats:
            f[3] += dt
            f[1] -= dt * 0.9
        self.floats = [f for f in self.floats if f[3] < 1.3]
        self.shake = max(0.0, self.shake - dt)
        self.flash = max(0.0, self.flash - dt)

    # --- time ------------------------------------------------------------------------------------
    def update(self, dt, inp, skip=False):
        """Advance by dt seconds. inp: a callable giving the move for each tick ((direction, reach))."""
        if self.paused or self.over:
            return
        dt = min(dt, 1.2)
        self.clock += dt
        self.state_t += dt
        self.fx(dt)
        st = self.state
        if st == "intro":
            if self.state_t >= self.INTRO or (skip and self.state_t > 0.3):
                self.state, self.state_t, self.acc = "play", 0.0, 0.0
        elif st == "play":
            self.acc += dt
            n = 0
            while self.acc >= TICK and n < 10:
                self.acc -= TICK
                n += 1
                self.tick(inp())
                if self.state != "play":
                    break
        elif st == "dead":
            self.acc += dt                                # the cave goes on: the burst burns out, rocks settle
            n = 0
            while self.acc >= TICK and n < 10:
                self.acc -= TICK
                n += 1
                self.tick((-1, False))
            if self.state_t > 2.6:
                self.after_death()
        elif st == "clear":
            self.tally_step(dt)
        self.update_cam(dt)

    def tick(self, act):
        c = self.cave
        before = self.seconds()
        c.step(act)
        self.moves = {to: frm for to, frm in c.moves}
        self.idle = self.idle + 1 if act[0] < 0 else 0
        wd = WORLDS[self.world]
        for e in c.ev:
            kind, i = e[0], e[1]
            x, y = c.xy(i)
            if kind == "dig":
                self.burst(x + 0.5, y + 0.5, 4, [wd["dirt"], lit(wd["dirt"], 0.25), lit(wd["dirt"], -0.3)], 2.0, 0.4)
                self.snd("dig", 0.5, 0.09)
            elif kind == "gem":
                over = c.gems > c.quota
                pts = self.spec["extra"] if over else self.spec["val"]
                self.add(pts, x + 0.5, y + 0.2, (255, 250, 200) if over else wd["gem"])
                self.burst(x + 0.5, y + 0.5, 8, [wd["gem"], WHITE, lit(wd["gem"], 0.4)], 3.0, 0.5, 2.0)
                self.snd("gem%d" % min(5, c.gems * 6 // max(1, c.quota)), 0.8, 0.02)
            elif kind == "land":
                if e[2] == ROCK:
                    self.burst(x + 0.5, y + 0.95, 3, [lit(wd["rock"], -0.2), wd["dirt"]], 1.5, 0.35, 6.0, 0.6)
                    self.snd("thud", 0.6, 0.06)
                else:
                    self.snd("ting", 0.6, 0.06)
            elif kind == "push":
                self.snd("push", 0.6, 0.1)
            elif kind == "boom":
                gems = e[2]
                self.shake = 0.35
                cols = [WHITE, (255, 220, 120), (255, 140, 60)] + ([wd["gem"], wd["gem"]] if gems else [(120, 90, 80)])
                self.burst(x + 0.5, y + 0.5, 26, cols, 6.0, 0.8, 6.0, 1.0)
                self.snd("gboom" if gems else "boom")
            elif kind == "die":
                self.snd("die")
            elif kind == "open":
                self.flash = 0.6
                self.snd("door")
            elif kind == "exit":
                self.snd("exit")
            elif kind == "timeout":
                self.snd("timeout")
            elif kind == "moss":
                self.snd("moss" if i == GEM else "stone")
                for j, v in enumerate(c.grid):
                    if v == i and self.rnd.random() < 0.3:
                        mx, my = c.xy(j)
                        self.burst(mx + 0.5, my + 0.5, 2, [wd["moss_glow"], wd["gem"] if i == GEM else wd["rock"]], 2.0, 0.6)
            elif kind == "rune_on":
                self.snd("rune")
            elif kind == "sieve":
                self.burst(x + 0.5, y + 1.0, 5, [wd["rune_glow"], WHITE, wd["gem"]], 2.5, 0.5, 4.0, 0.0)
                self.snd("sieve", 0.6, 0.05)
        if not c.won and c.alive and self.seconds() != before and self.seconds() <= 10:
            self.snd("beep", 0.8)
        if c.won:
            self.state, self.state_t = "clear", 0.0
            self.tally = [self.seconds(), 0.0]
            self.moves = {}
        elif not c.alive and self.state == "play":
            self.state, self.state_t = "dead", 0.0
            self.deaths += 1

    def give_up(self):
        if self.state in ("play", "intro") and self.cave.alive:
            c = self.cave
            c.alive = False
            c.explode(c.player, False, bytearray(len(c.grid)))
            self.snd("boom")
            self.shake = 0.3
            self.state, self.state_t, self.acc = "dead", 0.0, 0.0
            self.deaths += 1

    def after_death(self):
        if self.inter:
            self.next_cave()
            return
        self.lives -= 1
        if self.lives <= 0:
            self.state, self.over = "over", True
            self.snd("over")
        else:
            self.start_cave()

    def tally_step(self, dt):
        left, acc = self.tally
        if left > 0:
            acc += dt
            while acc >= 0.02 and left > 0:
                acc -= 0.02
                left -= 1
                self.add(1)
                if left % 3 == 0:
                    self.snd("tally", 0.5, 0.0)
            self.tally = [left, acc]
            self.state_t = 0.0
        elif self.state_t > 1.4:
            self.next_cave()

    def next_cave(self):
        self.cleared += self.state == "clear"
        if self.inter and self.state == "clear":
            self.lives += 1
            self.snd("life")
        self.cave_i += 1
        if self.cave_i >= len(CAVES):
            self.cave_i = len(CAVES) - 1
            self.state, self.over, self.won = "won", True, True
            self.snd("won")
            return
        self.start_cave()


# =============================================================================================
# Drawing
# =============================================================================================
HUD_BG = (14, 10, 18)
HUD_FG = (214, 210, 226)
HUD_DIM = (140, 136, 164)
GOLD = (250, 214, 120)
OPEN_SIDE = (EMPTY, ROCK, GEM, ROCKF, GEMF, PLAYER, CINDER, MOTH) + tuple(range(BOOM, GBOOM_END + 1))


def layout(cols, rows, hud=True):
    """(t, ox, oy, vw, vh): tile size in pixels, the view's top-left pixel and its size. The view always shows
    VW x VH tiles; the tile size follows the window."""
    top = bot = 1 if hud else 0
    ah = (rows - top - bot) * 2
    t = max(1, min(cols // VW, ah // VH))
    vw, vh = VW * t, VH * t
    return t, (cols - vw) // 2, top * 2 + (ah - vh) // 2, vw, vh


def blend(cv, x, y, c, a):
    if 0 <= x < cv.W and 0 <= y < cv.H:
        row = cv.px[y]
        row[x] = mix(row[x], c, a)


def glow(cv, cx, cy, r1, c, k, clip):
    """A soft halo of radius r1 (screen pixels), clipped to the view."""
    x0c, y0c, x1c, y1c = clip
    y0, y1 = max(y0c, int(cy - r1)), min(y1c - 1, int(cy + r1))
    x0, x1 = max(x0c, int(cx - r1)), min(x1c - 1, int(cx + r1))
    inv = 1.0 / max(0.5, r1)
    for py in range(y0, y1 + 1):
        row = cv.px[py]
        dy = (py + 0.5 - cy) * inv
        dy2 = dy * dy
        for px in range(x0, x1 + 1):
            dx = (px + 0.5 - cx) * inv
            d2 = dx * dx + dy2
            if d2 < 1:
                a = (1 - d2) * k
                o = row[px]
                row[px] = (int(o[0] + (c[0] - o[0]) * a), int(o[1] + (c[1] - o[1]) * a), int(o[2] + (c[2] - o[2]) * a))


def blit(cv, x0, y0, img, clip):
    cx0, cy0, cx1, cy1 = clip
    cx1, cy1 = min(cx1, cv.W), min(cy1, cv.H)          # never past the canvas (tiny previews)
    t = len(img)
    a, b = max(0, cx0 - x0), min(t, cx1 - x0)
    if b <= a:
        return
    px = cv.px
    for j in range(max(0, cy0 - y0), min(t, cy1 - y0)):
        px[y0 + j][x0 + a:x0 + b] = img[j][a:b]


def blit_runs(cv, x0, y0, runs, clip):
    cx0, cy0, cx1, cy1 = clip
    cx1, cy1 = min(cx1, cv.W), min(cy1, cv.H)
    px = cv.px
    for (y, x, cols) in runs:
        yy = y0 + y
        if yy < cy0 or yy >= cy1:
            continue
        xs = x0 + x
        xe = xs + len(cols)
        if xs >= cx0 and xe <= cx1:
            px[yy][xs:xe] = cols
        else:
            a, b = max(xs, cx0), min(xe, cx1)
            if b > a:
                px[yy][a:b] = cols[a - xs:b - xs]


_BG = {}


def backdrop(world, cols, rows, hud):
    """The rock face around the view and the view's frame (cached)."""
    key = (world, cols, rows, hud)
    c = _BG.get(key)
    if c is not None:
        return c
    if len(_BG) > 12:
        _BG.clear()
    wd = WORLDS[world]
    t, ox, oy, vw, vh = layout(cols, rows, hud)
    hi, lo = wd["back"]
    W, H = cols, rows * 2
    px = []
    for y in range(H):
        row = []
        for x in range(W):
            h = hsh(x // 2, y // 2, 41)
            k = (h & 15) / 15
            base = mix(hi, lo, min(1.0, abs(y - H / 2) / (H / 2) * 0.7 + 0.3))
            row.append(lit(base, (k - 0.5) * 0.12))
        px.append(row)
    if t >= 2:                                  # blocky strata in the rock face
        for y in range(H):
            for x in range(W):
                if hsh(x // 6, y // 3, 7) % 5 == 0:
                    px[y][x] = lit(px[y][x], 0.06 if (x + y) % 2 else -0.04)
    fr = max(1, min(3, t // 3))
    edge_hi, edge_lo = lit(wd["steel"], 0.35), lit(wd["steel"], -0.4)
    for k in range(fr):
        x0, y0, x1, y1 = ox - 1 - k, oy - 1 - k, ox + vw + k, oy + vh + k
        cl = mix(edge_hi, edge_lo, k / max(1, fr))
        for x in range(max(0, x0), min(W, x1 + 1)):
            if 0 <= y0 < H:
                px[y0][x] = cl
            if 0 <= y1 < H:
                px[y1][x] = lit(cl, -0.3)
        for y in range(max(0, y0), min(H, y1 + 1)):
            if 0 <= x0 < W:
                px[y][x0] = cl
            if 0 <= x1 < W:
                px[y][x1] = lit(cl, -0.3)
    _BG[key] = px
    return px


def pell_frame(g):
    c = g.cave
    if c.player in g.moves:
        return 1 + (c.tick & 1)
    if c.push is not None:
        return 3
    if g.idle > 28:
        return 5 + (int(g.clock * 4) & 1)
    return 4 if int(g.clock * 10) % 34 == 0 else 0


def render(g, cols, rows, hud=True):
    t, ox, oy, vw, vh = layout(cols, rows, hud)
    cv = Canvas(cols, 1)
    cv.rows, cv.H = rows, rows * 2
    cv.px = [r[:] for r in backdrop(g.world, cols, rows, hud)]
    c = g.cave
    w, h, grid = c.w, c.h, c.grid
    camx, camy = g.cam
    sx_off = int(round(camx * t))
    sy_off = int(round(camy * t))
    if g.shake > 0 and t >= 3:
        k = int(g.shake * t * 0.8) + 1
        sx_off += g.rnd.randint(-k, k)
        sy_off += g.rnd.randint(-k, k) // 2
    clip = (max(0, ox), max(0, oy), min(cols, ox + vw), min(len(cv.px), oy + vh))   # never past the canvas
    wi = g.world
    clock = g.clock
    tx0, ty0 = max(0, sx_off // t), max(0, sy_off // t)
    tx1, ty1 = min(w, tx0 + VW + 2), min(h, ty0 + VH + 2)
    sprites = []
    rune_f = 0 if c.rune_state == 0 else -1 if c.rune_state == 2 else 1 + int(clock * 10) % 4
    door_f = int(clock * 8) % 8
    moss_f = int(clock * 5) % 8
    for ty in range(ty0, ty1):
        sy = oy + ty * t - sy_off
        base = ty * w
        for tx in range(tx0, tx1):
            i = base + tx
            v = grid[i]
            sx = ox + tx * t - sx_off
            var = hsh(tx, ty, 1) & 3
            if ROCK <= v <= MOTH or v == PLAYER:
                sprites.append((i, v))
                v = EMPTY
            if v == DIRT:
                m = 0
                if grid[i - w] in OPEN_SIDE if ty > 0 else False:
                    m |= 1
                if tx < w - 1 and grid[i + 1] in OPEN_SIDE:
                    m |= 2
                if ty < h - 1 and grid[i + w] in OPEN_SIDE:
                    m |= 4
                if tx > 0 and grid[i - 1] in OPEN_SIDE:
                    m |= 8
                img = tile(DIRT, wi, t, var, 0, m)
            elif v == RUNE:
                img = tile(RUNE, wi, t, var, rune_f)
            elif v == DOOR:
                img = tile(DOOR, wi, t, 0, door_f)
            elif v == MOSS:
                img = tile(MOSS, wi, t, var, moss_f)
            elif v >= BOOM:
                img = tile(v, wi, t, var)
            else:
                img = tile(v, wi, t, var if v != EXIT else 0)
            blit(cv, sx, sy, img, clip)
    # the moving things, each where it is between its last cell and this one
    lights = []
    for i, v in sprites:
        x, y = g.pos(i)
        sx, sy = ox + int(round(x * t)) - sx_off, oy + int(round(y * t)) - sy_off
        var = hsh(*c.xy(i), 1) & 3 if v in (ROCK, ROCKF) else (i * 7) & 3
        if v == PLAYER:
            blit_runs(cv, sx, sy, tile(PLAYER, wi, t, 0, 4 if c.timeout else pell_frame(g), 0, c.face), clip)
            lights.append((sx + t * (0.5 + 0.17 * (1 if c.face == 1 else -1)), sy + t * 0.25, 2.6 * t, (255, 230, 160), 0.22))
        elif v in (GEM, GEMF):
            fr = int(clock * 9 + i * 5) % 12
            blit_runs(cv, sx, sy, tile(GEM, wi, t, 0, fr), clip)
            if fr < 3 and t >= 5:
                lights.append((sx + t / 2, sy + t / 2, 0.9 * t, WORLDS[wi]["gem"], 0.18))
        elif v == CINDER:
            blit_runs(cv, sx, sy, tile(CINDER, wi, t, 0, int(clock * 10 + i) % 8), clip)
            lights.append((sx + t / 2, sy + t / 2, 1.5 * t, (255, 120, 40), 0.3))
        elif v == MOTH:
            blit_runs(cv, sx, sy, tile(MOTH, wi, t, 0, int(clock * 12 + i) % 4), clip)
            lights.append((sx + t / 2, sy + t / 2, 1.1 * t, WORLDS[wi]["moth"], 0.16))
        else:
            blit_runs(cv, sx, sy, tile(ROCK, wi, t, var), clip)
    if t >= 4:
        if c.door_open:
            ex, ey = c.xy(c.exit)
            lights.append((ox + (ex + 0.5) * t - sx_off, oy + (ey + 0.5) * t - sy_off, 2.2 * t, (255, 210, 120),
                           0.3 + 0.12 * math.sin(clock * 6)))
        for (lx, ly, r, col, k) in lights:
            if clip[0] - r < lx < clip[2] + r and clip[1] - r < ly < clip[3] + r:
                glow(cv, lx, ly, r, col, k, clip)
    # particles and points
    psz = max(1, t // 5)
    for p in g.parts:
        k = 1 - p[4] / p[5]
        x, y = ox + int(p[0] * t) - sx_off, oy + int(p[1] * t) - sy_off
        if clip[0] <= x < clip[2] - psz + 1 and clip[1] <= y < clip[3] - psz + 1:
            if psz == 1:
                blend(cv, x, y, p[6], 0.35 + 0.65 * k)
            else:
                cv.rect(x, y, psz, psz, mix(WORLDS[wi]["bg"], p[6], 0.3 + 0.7 * k))
    if g.flash > 0:
        k = g.flash / 0.6 * 0.35
        for y in range(clip[1], clip[3]):
            row = cv.px[y]
            row[clip[0]:clip[2]] = [mix(q, (255, 240, 200), k) for q in row[clip[0]:clip[2]]]
    if rows > 14:
        for f in g.floats:
            x, y, txt, tt, col = f
            if tt < 0:
                continue
            row = int((oy + y * t - sy_off) // 2)
            col_ = int(ox + x * t - sx_off - len(txt) / 2)
            if (clip[1] // 2) <= row < (clip[3] // 2) and clip[0] <= col_ and col_ + len(txt) <= clip[2]:
                cv.put(col_, row, txt, mix(col, (40, 30, 40), max(0.0, tt - 0.6) * 1.4))
    if hud:
        draw_hud(cv, g)
        draw_banners(cv, g)
    return cv


# --- the text on top ------------------------------------------------------------------------------
def draw_hud(cv, g):
    cols, rows = cv.cols, cv.rows
    c = g.cave
    wd = WORLDS[g.world]
    cv.put(0, 0, " " * cols, HUD_FG, HUD_BG)
    need = c.quota
    got = c.gems
    gem_c = wd["gem"] if not c.door_open else (255, 250, 210) if int(g.clock * 4) % 2 else wd["gem"]
    secs = g.seconds()
    tc = (255, 110, 100) if secs <= 10 and int(g.clock * 4) % 2 else HUD_FG
    parts = [(" ♦ ", gem_c), ("%02d" % got, GOLD if got >= need else HUD_FG), ("/%02d" % need, HUD_DIM),
             ("  ♦%d" % (g.spec["extra"] if c.door_open else g.spec["val"]), HUD_DIM),
             ("   TIME ", HUD_DIM), ("%3d" % secs, tc),
             ("   ", HUD_DIM), ("%06d" % g.score, GOLD)]
    if cols >= 74:
        parts.append(("  HI %06d" % max(g.score, g.hi), HUD_DIM))
    parts.append(("   PELL x%d" % g.lives, (230, 200, 150)))
    x = 0
    for s_, col in parts:
        if x + len(s_) > cols:
            break
        cv.put(x, 0, s_, col, HUD_BG)
        x += len(s_)
    right = "%s %s" % (g.label(), g.spec["name"])
    if x + len(right) + 3 > cols:
        right = g.label()
    if x + len(right) + 2 <= cols:
        cv.put(cols - len(right) - 1, 0, right, wd["accent"], HUD_BG)
    r = rows - 1
    cv.put(0, r, " " * cols, HUD_FG, HUD_BG)
    left = " %s   %s" % (wd["short"], DIFFS[g.diff]["name"])
    cv.put(0, r, left, HUD_DIM, HUD_BG)
    hints = "arrows dig   Space+arrow reach   R give up   Esc pause"
    if len(left) + len(hints) + 3 > cols:
        hints = "Space+arrow reach   Esc pause"
    if len(left) + len(hints) + 3 <= cols:
        cv.put(cols - len(hints) - 1, r, hints, HUD_DIM, HUD_BG)
    if c.rune_state == 1 and cols >= 70:
        s_ = " RUNES %d " % int(math.ceil(c.rune_ticks * TICK))
        cv.put(len(left) + 3, r, s_, (20, 20, 30), wd["rune_glow"])


def banner(cv, lines, col):
    w = max(len(l) for l in lines) + 4
    x = max(0, (cv.cols - w) // 2)
    y = max(1, cv.rows // 2 - len(lines) // 2 - 1)
    cv.box(x, y, [l.center(w - 4) for l in lines], (236, 234, 244), (24, 18, 32))
    cv.put(x + 2, y + 1, lines[0].center(w - 4), col, (24, 18, 32))


def draw_banners(cv, g):
    wd = WORLDS[g.world]
    c = g.cave
    if g.state == "intro" and not g.over:
        top = "INTERMISSION" if g.inter else "%s  -  CAVE %s" % (wd["name"], g.label().split("-")[1])
        lines = [top, g.spec["name"], "", "%d sunstones open the door" % c.quota]
        if cv.rows >= 24:
            lines += [g.spec.get("hint", "")]
        banner(cv, lines, wd["accent"])
    elif g.state == "clear" and g.state_t > 0.2 or g.state == "clear" and g.tally and g.tally[0] > 0:
        lines = ["CAVE CLEAR" if not g.inter else "INTERMISSION CLEAR", "", "time left  %d" % (g.tally[0] if g.tally else 0)]
        if g.inter:
            lines += ["", "+1 life"]
        banner(cv, lines, GOLD)
    elif g.state == "dead" and g.state_t > 0.7 and not g.over:
        why = "OUT OF LAMP OIL" if c.timeout else "PELL IS DOWN"
        if g.inter:
            sub = "no life lost in an intermission"
        else:
            n = g.lives - 1
            sub = ("%d li%s left" % (n, "fe" if n == 1 else "ves")) if n else "that was the last one"
        banner(cv, [why, "", sub], (255, 130, 100))


def render_over(g, cv, record, auto=False):
    if g.won:
        lines = ["THE WARRENS SHINE AGAIN", "", "Every sunstone is home.", "", "score  %d" % g.score,
                 "%s, %d caves" % (DIFFS[g.diff]["name"].lower(), g.cleared)]
    else:
        lines = ["GAME OVER", "", "score  %d" % g.score,
                 "reached  %s %s" % (g.label(), g.spec["name"].lower()), "caves cleared  %d" % g.cleared]
    if record:
        lines += ["", "** NEW RECORD **"]
    lines += ["", "auto mode: a new round starts" if auto else "Enter: again   Esc / Q: menu"]
    w = max(len(l) for l in lines) + 4
    x, y = max(0, (cv.cols - w) // 2), max(0, cv.rows // 2 - len(lines) // 2 - 1)
    edge = GOLD if record or g.won else (200, 76, 86)
    cv.frame(x - 1, y * 2 - 1, w + 2, (len(lines) + 2) * 2 + 2, edge)
    cv.box(x, y, [l.center(w - 4) for l in lines], (240, 240, 246), (26, 20, 36))


# =============================================================================================
# Title demo, controls, menu, main loop
# =============================================================================================
class TitleDemo:
    """The autopilot digging through a cave of each world in turn, behind the title (and in the launcher)."""
    PICK = (0, 6, 11, 16, 21, 2, 8, 13, 18, 23, 1, 7, 12, 17, 22, 3, 9, 14, 19, 24, 4, 5, 10, 15, 20)

    def __init__(self, k=0):
        self.k = k
        self.new_run()

    def new_run(self):
        lvl = self.PICK[self.k % len(self.PICK)] % len(CAVES)
        self.g = Game(1, lvl, seed=self.k + 1, demo=True)
        self.g.lives = 1
        self.g.state, self.g.state_t = "play", 0.0
        self.g.cam = self.g.cam_on(self.g.cave.player)
        self.bot = Bot(self.g, seed=self.k)
        self.k += 1
        self.age = 0.0
        self.lvl = lvl

    def scene(self, cols, rows, dt):
        g = self.g
        self.age += dt
        g.update(min(dt, 0.1), self.bot)
        if g.cave_i != self.lvl or g.over or g.state in ("dead", "clear") and g.state_t > 1.5 or self.age > 50:
            self.new_run()
        return render(self.g, cols, rows, hud=False)


DIRKEYS = {"up": 0, "w": 0, "k": 0, "right": 1, "d": 1, "l": 1, "down": 2, "s": 2, "j": 2, "left": 3, "a": 3, "h": 3}


class Controls:
    """Keys to one move per tick: (direction or -1, reach). A tap always moves exactly one cell (it is queued);
    holding keeps walking. Classic terminals: a key counts as held once it repeats. Space held with a direction
    reaches instead of walking."""

    def __init__(self, kitty):
        self.kitty = kitty
        self.reset()

    def reset(self):
        self.pending = []
        self.until, self.rep = {}, {}
        self.real = set()
        self.space = 0.0
        self.now = 0.0
        self.pressed = False
        self.last = None

    def feed(self, name, kind, now):
        self.now = now
        if name == " ":
            if kind == "release":
                self.real.discard(" ")
                self.space = 0.0
            else:
                self.real.add(" ")
                self.space = now + 0.55
            return
        d = DIRKEYS.get(name)
        if d is None:
            return
        if kind == "release":
            self.real.discard(name)
            self.until.pop(name, None)
            self.rep.pop(name, None)
            return
        if self.kitty:
            if kind == "press":
                self._queue(d)
            self.real.add(name)
            self.last = name
            return
        if self.until.get(name, 0) > now and kind != "press-new":
            self.rep[name] = True
            self.until[name] = now + 0.17
        else:
            self._queue(d)
            self.until[name] = now + 0.6
            self.rep[name] = False
        for k, dk in DIRKEYS.items():            # another direction lets go of the rest
            if dk != d:
                self.until.pop(k, None)
                self.rep.pop(k, None)
        self.last = name

    def _queue(self, d):
        self.pressed = True
        if len(self.pending) < 2:
            self.pending.append(d)
        if self.space > self.now or " " in self.real:
            self.space = self.now + 0.55

    def held(self):
        if self.kitty:
            if self.last in self.real:
                return DIRKEYS[self.last]
            for n in self.real:
                if n in DIRKEYS:
                    return DIRKEYS[n]
            return -1
        for n, u in self.until.items():
            if u > self.now and self.rep.get(n):
                return DIRKEYS[n]
        return -1

    def action(self):
        d = self.pending.pop(0) if self.pending else self.held()
        reach = d >= 0 and (" " in self.real if self.kitty else self.space > self.now)
        return d, reach

    def take_press(self):
        p, self.pressed = self.pressed, False
        return p


class AutoRun:
    """Auto mode: the real game from the chosen world and difficulty, played by the autopilot. After a game
    over the result stays for a few seconds, then a new round starts. No score is kept."""
    OVER_SHOW = 3.5

    def __init__(self, world, diff=1, sound=True, seed=None):
        self.world, self.diff, self.sound, self.seed = world, diff, sound, seed
        self.auto = AutoMode()
        self.rounds = 0
        self.new()

    def new(self):
        self.rounds += 1
        self.g = Game(self.diff, world_start(self.world), quiet=not self.sound,
                      seed=None if self.seed is None else self.seed + self.rounds)
        self.bot = Bot(self.g, seed=None if self.seed is None else self.seed * 3 + self.rounds)
        self.mark = (self.g.cave_i, self.g.deaths)
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
            sdt = self.auto.scale(dt)
            while sdt > 0 and not g.over:
                g.update(min(sdt, 0.25), self.bot)
                sdt -= 0.25
                if (g.cave_i, g.deaths) != self.mark:
                    self.mark = (g.cave_i, g.deaths)
                    self.bot.reset()
        if not draw:
            return None
        cv = render(g, cols, rows)
        if g.over:
            render_over(g, cv, False, auto=True)
        self.auto.banner(cv, extra="round %d" % self.rounds)
        return cv


def world_start(world):
    return next(i for i, c in enumerate(CAVES) if c["world"] == world)


MIN_COLS, MIN_ROWS = 60, 22


def too_small(term):
    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (%dx%d)." % (MIN_COLS, MIN_ROWS))


def run_auto(term, world, diff=1):
    """Auto mode until the viewer stops it (Esc / Q)."""
    run = AutoRun(world, diff)
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


def menu_items(world, diff):
    return ["Start the dig", "World select   < %d %s >" % (world + 1, WORLDS[world]["short"]),
            "Difficulty     < %s >" % DIFFS[diff]["name"], AUTO_LABEL]


def render_menu(demo, cols, rows, sel, world, diff, dt, help_, kitty):
    cv = demo.scene(cols, rows, dt)
    rec = load_scores().get(GAME, {})
    bits = ["%s %d" % (d["key"], rec[d["key"]]) for d in DIFFS if rec.get(d["key"])]
    best = ("best  " + "   ".join(bits)) if bits else None
    extra = ["", "Pell digs for the warrens' lost sunstones.", "Take the quota, reach the door, mind the rocks.",
             "Keys: %s" % ("with releases (kitty protocol)" if kitty else "classic terminal mode")]
    title_screen(cv, NAME, TAGLINE, menu_items(world, diff), sel, best, extra=extra,
                 keys="Up/Down choose   Left/Right change   Enter start   M %s   ? help   Esc back" % SND.label().lower(),
                 help_lines=help_lines(kitty), show_help=help_, dim=0.45)
    return cv


def record(g):
    return submit(GAME, DIFFS[g.diff]["key"], g.score)


def play(term, ctl, diff, start):
    """One game. Returns 'again' or 'menu'."""
    g = Game(diff, start)
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
                if name == "r":
                    g.give_up()
                else:
                    ctl.feed(name, kind, now)
        cols, rows = term.size()
        if cols < MIN_COLS or rows < MIN_ROWS:
            too_small(term)
            g.paused = g.paused or not g.over
            time.sleep(0.2)
            last = time.time()
            continue
        if not g.paused:
            ctl.now = now
            g.update(dt, ctl.action, skip=ctl.take_press())
        if g.over and not submitted:
            submitted = True
            rec = record(g)
        cv = render(g, cols, rows)
        if g.paused:
            overlay(cv, help_lines(ctl.kitty) if g.help else PAUSE_LINES + ["", SND.label()])
        elif g.over:
            render_over(g, cv, rec)
        term.write(cv.emit())
        time.sleep(max(0.0, 1 / 30 - (time.time() - now)))


def main():
    with KeyTerminal() as term:
        ctl = Controls(term.kitty)
        demo = TitleDemo()
        sel, world, diff, help_ = 0, 0, 1, False
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
            term.write(render_menu(demo, cols, rows, sel, world, diff, min(0.1, now - last), help_, ctl.kitty).emit())
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
                    if sel == 2:
                        diff = (diff + step) % 3
                    else:
                        world = (world + step) % len(WORLDS)
                        sel = sel if sel == 3 else 1
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
                run_auto(term, world, diff)
                last = time.time()
                continue
            start = world_start(world) if sel in (1, 2) else 0
            while play(term, ctl, diff, start) == "again":
                pass
            last = time.time()


# =============================================================================================
# Self-test
# =============================================================================================
def _cave(rows, **kw):
    spec = dict(quota=kw.pop("quota", 99), time=kw.pop("time", 999), map=rows)
    spec.update(kw)
    return Cave(spec, 1, seed=kw.get("seed", 1))


def _count(c, *kinds):
    return sum(1 for v in c.grid if v in kinds)


def run_cave(i, diff=2, seed=1, limit=None):
    """The autopilot plays cave i in the real game (one life). Returns (cleared, cave seconds used, game)."""
    g = Game(diff, i, seed=seed, quiet=True)
    g.state, g.state_t = "play", 0.0
    bot = Bot(g, seed=seed)
    n = 0
    while g.state == "play" and n < 6000:
        g.update(TICK, bot)
        n += 1
    return g.state == "clear", g.cave.tick * TICK, g


def selftest():
    t0 = time.time()
    global submit

    def no_scores(*a, **k):
        raise AssertionError("the self-test must not write scores")
    submit = no_scores
    # 1. the caves
    worlds = {}
    for i, c in enumerate(CAVES):
        rows = c["map"]
        W, H = (VW, VH) if c.get("inter") else (40, 22)
        assert len(rows) == H and all(len(r) == W for r in rows), "%s: size" % c["name"]
        assert rows[0] == rows[-1] == "#" * W and all(r[0] == r[-1] == "#" for r in rows), "%s: border" % c["name"]
        flat = "".join(rows)
        assert flat.count("P") == 1 and flat.count("E") == 1 and set(flat) <= set(CHARS), c["name"]
        worlds.setdefault(c["world"], []).append(c.get("inter", False))
    assert len(worlds) == len(WORLDS) and all(v == [False] * 4 + [True] for v in worlds.values())
    print("caves: %d hand-made caves and %d intermissions in %d worlds" % (
        sum(not c.get("inter") for c in CAVES), sum(bool(c.get("inter")) for c in CAVES), len(WORLDS)))
    # 2. the rules
    c = _cave(["#####", "# o #", "#   #", "#   #", "#P E#", "#####"])
    seen = []
    for _ in range(4):
        c.step()
        seen.append(c.grid.index(ROCKF) if ROCKF in c.grid else c.grid.index(ROCK))
    assert seen == [12, 17, 22, 22] and c.grid[22] == ROCK, "falling: %s" % seen
    c = _cave(["#####", "# o #", "# o #", "# o #", "#   #", "#   #", "#   #", "#P E#", "#####"])
    for k in range(3):
        c.step()
        ys = sorted(c.xy(j)[1] for j, v in enumerate(c.grid) if v in (ROCK, ROCKF))
        assert ys == [ys[0], ys[0] + 1, ys[0] + 2], "a falling column split up: %s" % ys
    c = _cave(["#######", "#  o  #", "#  o  #", "#     #", "#P   E#", "#######"])
    for _ in range(6):
        c.step()
    assert _count(c, ROCK) == 2 and c.grid[4 * 7 + 2] in (ROCK, ROCKF) or c.grid[3 * 7 + 2] == ROCK, "rolling"
    # two rocks rolling into one gap: one takes it, nothing doubles or vanishes
    c = _cave(["#######", "#o   o#", "#o = o#", "#=====#", "#P   E#", "#######"])
    for _ in range(10):
        c.step()
        assert _count(c, ROCK, ROCKF) == 4, "rocks appeared or vanished while rolling"
    # no glitches: a cave full of rock and sunstone, left alone, keeps every stone and moves each one cell a tick
    r = random.Random(5)
    rows = ["#" * 30] + ["#" + "".join(r.choice("oo*.  ") for _ in range(28)) + "#" for _ in range(16)] + ["#" * 30]
    rows[1] = "#P" + rows[1][2:-2] + "E#"
    c = _cave(rows)
    n0 = _count(c, ROCK, ROCKF, GEM, GEMF)
    for _ in range(80):
        c.step()
        dests = [to for to, fr in c.moves]
        assert len(dests) == len(set(dests)), "two things moved into one cell"
        assert all(abs(c.xy(to)[0] - c.xy(fr)[0]) + abs(c.xy(to)[1] - c.xy(fr)[1]) == 1 for to, fr in c.moves)
        assert _count(c, ROCK, ROCKF, GEM, GEMF) == n0, "stones appeared or vanished"
    # a falling rock crushes; a resting one does not
    c = _cave(["#####", "# o #", "# . #", "# P #", "#  E#", "#####"])
    for _ in range(10):
        c.step()
    assert c.alive, "a resting rock hurt Pell"
    c = _cave(["#####", "# o #", "#   #", "#   #", "# P #", "#  E#", "#####"])
    for _ in range(4):
        c.step()
    assert not c.alive, "a falling rock did not crush"
    # Pell steps out from under a rock and it follows down behind him
    c = _cave(["######", "# o  #", "# P. #", "#    #", "#   E#", "######"])
    c.step((1, False))
    for _ in range(3):
        c.step()
    assert c.alive and c.grid[4 * 6 + 2] == ROCK
    # creatures: crushed glassmoths become nine sunstones, cinderbeetles nothing
    c = _cave(["#######", "#  o  #", "#     #", "#  m  #", "#     #", "#P   E#", "#######"])
    c.dirs[3 * 7 + 3] = 0
    for _ in range(8):
        c.step()
    assert _count(c, GEM, GEMF) == 9, "a crushed glassmoth gave %d sunstones" % _count(c, GEM, GEMF)
    c = _cave(["#######", "#  o  #", "#     #", "#  c  #", "#     #", "#P   E#", "#######"])
    c.dirs[3 * 7 + 3] = 0
    for _ in range(8):
        c.step()
    assert _count(c, GEM, GEMF, CINDER) == 0 and _count(c, STEEL) == 24, "cinderbeetle burst / ironstone"
    # wall huggers go round and round a room, every tick, keeping their wall
    for kind, ch in ((CINDER, "c"), (MOTH, "m")):
        c = _cave(["##########", "#........#", "#.  " + ch + "   .#", "#. .... .#", "#.      .#", "#........#",
                   "#P......E#", "##########"])
        cells = set()
        for _ in range(60):
            c.step()
            assert kind in c.grid, "a creature vanished"
            cells.add(c.grid.index(kind))
        assert len(cells) == 14, "a creature does not go round its ring (%d cells)" % len(cells)
    c = _cave(["#######", "#P c E#", "#######"])
    for _ in range(3):
        c.step()
    assert not c.alive and _count(c, CINDER) == 0, "touching a cinderbeetle"
    # pushing takes two ticks, only sideways, only into the open
    c = _cave(["#######", "#Po   #", "#.....#", "#    E#", "#######"])
    c.step((1, False))
    assert c.grid[9] == ROCK
    c.step((1, False))
    assert c.grid[10] == ROCK and c.player == 9, "push"
    # reach: take a sunstone without moving
    c = _cave(["######", "#P*  #", "#....#", "#   E#", "######"], quota=1)
    c.step((1, True))
    assert c.player == 7 and c.gems == 1 and c.door_open and c.grid[c.exit] == DOOR
    # creepmoss: shut in it turns to sunstones; grown too big, to rock; it bursts creatures
    c = _cave(["######", "#~  =#", "#====#", "#P  E#", "######"], moss_slow=0, moss_p=(0.5, 0.5))
    for _ in range(40):
        c.step()
    assert c.moss_state == 1 and _count(c, GEM) == 3, "shut-in moss"
    c = _cave(["############", "#~.........#", "#..........#", "#..........#", "#P........E#", "############"],
              moss_slow=0, moss_p=(0.3, 0.3), moss_limit=12)
    for _ in range(80):
        c.step()
    assert c.moss_state == 2 and _count(c, MOSS) == 0 and _count(c, ROCK, ROCKF) >= 12, "moss grown too big"
    # the rune seam: rock falls through as a sunstone while it glows, rests on it after
    c = _cave(["#######", "# o o #", "#     #", "#RRRRR#", "#     #", "#     #", "#P   E#", "#######"], rune=1)
    for _ in range(20):
        c.step()
    assert _count(c, GEM, GEMF) >= 1 and c.rune_state == 2, "rune seam"
    c = _cave(["#######", "# o   #", "#     #", "#RRRRR#", "#     #", "#P   E#", "#######"])
    c.rune_state = 2
    for _ in range(8):
        c.step()
    assert c.grid[2 * 7 + 2] == ROCK, "a spent seam lets rock through"
    # the door, the way out and the lamp oil
    c = _cave(["######", "#P*E #", "#....#", "######"], quota=1)
    c.step((1, False))
    c.step((1, False))
    assert c.won
    c = _cave(["######", "#P  E#", "######"], time=1.0)
    for _ in range(10):
        c.step()
    assert not c.alive and c.timeout
    print("rules: falling, columns fall together, rolling, no doubled or lost stones (80 ticks, %d stones), "
          "crushing, glassmoths to sunstones, wall huggers, pushing, reach, creepmoss both ways, rune seams, "
          "door, lamp oil" % n0)
    # 3. every cave: the autopilot clears it in the real game on HARD (least time), first life, two seeds
    worst = 0.0
    total = 0.0
    for i, cv_ in enumerate(CAVES):
        limit = cv_["time"] * DIFFS[2]["time"]
        for seed in (1, 2):
            ok, secs, g = run_cave(i, 2, seed)
            assert ok, "%s: not cleared by the autopilot (seed %d, %d of %d sunstones, %s)" % (
                cv_["name"], seed, g.cave.gems, g.cave.quota, "out of time" if g.cave.timeout else "lost")
            worst = max(worst, secs / limit)
            total += secs
        print("  %-4s %-20s quota %2d  cleared in %5.1f s of %3d s (hard)" % (
            Game(2, i, quiet=True, demo=True).label(), cv_["name"], cv_["quota"], secs, limit))
    print("clear: all %d caves by the autopilot on HARD with two seeds, first life each; at most %.0f%% of the "
          "time used (easier levels only give more time)" % (len(CAVES), worst * 100))
    g = Game(2, 0, seed=9, quiet=True)
    bot = Bot(g, seed=9)
    mark = (g.cave_i, g.deaths)
    n = 0
    while not g.over and n < 200000:
        g.update(TICK, bot)
        n += 1
        if (g.cave_i, g.deaths) != mark:
            mark = (g.cave_i, g.deaths)
            bot.reset()
    assert g.won, "the whole campaign was not won (stopped at %s)" % g.spec["name"]
    print("campaign: the autopilot plays all %d caves on HARD in one go: %d points, %d lives lost, %d left" % (
        len(CAVES), g.score, g.deaths, g.lives))
    # 4. scoring: points per sunstone, more after the quota, the time bonus, extra lives, intermissions
    g = Game(1, 4, seed=3, quiet=True)
    lives = g.lives
    g.add(EXTRA_EVERY)
    assert g.lives == lives + 1
    g.state = "play"
    g.cave.ticks_left = 1
    g.tick((-1, False))
    assert g.state == "dead"
    g.state_t = 9
    g.update(0.01, lambda: (-1, False))
    assert g.cave_i == 5 and g.lives == lives + 1, "an intermission must not cost a life"
    g = Game(1, 0, seed=3, quiet=True)
    g.lives = 1
    g.state = "play"
    g.give_up()
    for _ in range(40):
        g.update(0.1, lambda: (-1, False))
    assert g.over and not g.won
    print("scoring: extra life, intermissions free, giving up, game over")
    # 5. the controls: a tap is one cell, holding walks on, Space reaches
    k = Controls(False)
    k.feed("right", "press", 0.0)
    acts = [k.action() for _ in range(3)]
    assert acts == [(1, False), (-1, False), (-1, False)], "classic tap: %s" % acts
    for j in range(12):
        k.feed("right", "press", 0.45 + j * 0.033)
    k.now = 0.85
    assert k.action()[0] == 1, "classic hold"
    k.now = 1.5
    assert k.action()[0] == -1, "classic release"
    k.feed(" ", "press", 2.0)
    k.feed("up", "press", 2.05)
    assert k.action() == (0, True), "reach"
    q = Controls(True)
    q.feed("left", "press", 0.0)
    assert q.action() == (3, False) and q.action() == (3, False)
    q.feed("left", "release", 0.3)
    assert q.action() == (-1, False)
    print("controls: classic taps and repeats, kitty releases, Space reach")
    # 6. rendering at every size, in every world and state
    n = 0
    timing = []
    for cols, rows in ((60, 22), (80, 24), (100, 32), (120, 40), (240, 70)):
        tr = te = 0.0
        frames = 0
        for lv in (0, 6, 8, 12, 17, 19, 22, 23):
            g = Game(1, lv, seed=lv, quiet=True)
            bot = Bot(g, seed=lv)
            for _ in range(int(6 / (1 / 30))):
                g.update(1 / 30, bot)
            for state in ("play", "intro", "dead", "clear"):
                if state != "play":
                    g.state, g.state_t = state, 1.0
                    g.tally = [20, 0.0]
                a = time.time()
                cv = render(g, cols, rows)
                b = time.time()
                cv.emit(True)
                tr += b - a
                te += time.time() - b
                frames += 1
            overlay(cv, help_lines(True))
            g.over = True
            render_over(g, cv, True)
            cv.emit(True)
        n += frames
        timing.append((cols, rows, tr / frames * 1000, te / frames * 1000))
    d = TitleDemo()
    for cols, rows in ((60, 22), (120, 40), (24, 8), (40, 12), (30, 9)):
        (render_menu(d, cols, rows, 0, 2, 1, 0.05, False, True) if rows >= 20 else d.scene(cols, rows, 0.05)).emit(True)
        n += 1
    for _ in range(300):
        d.scene(30, 9, 0.1)
    print("rendering: %d frames at 60x22, 80x24, 100x32, 120x40, 240x70 (+ title, preview, overlays)" % n)
    for cols, rows, r_, e_ in timing:
        print("  %3dx%-3d render %5.1f ms  emit %5.1f ms  = %5.1f ms per frame (%3.0f fps)" % (
            cols, rows, r_, e_, r_ + e_, 1000 / max(0.1, r_ + e_)))
    a = screenshot(100, 32)
    b = screenshot(100, 32)
    assert a.px == b.px and a.text == b.text, "the screenshot is not deterministic"
    # 7. auto mode: the real game at x8; pause, speed and stop work; no score kept
    run = AutoRun(0, sound=False, seed=31)
    assert not run.g.demo and run.g.lives == DIFFS[1]["lives"]
    run.key(" ")
    snap = (run.g.clock, run.g.score)
    for _ in range(30):
        run.frame(1 / 30, 70, 22, draw=False)
    assert (run.g.clock, run.g.score) == snap, "auto mode ran on while paused"
    run.key(" ")
    for _ in range(5):
        run.key("+")
    assert run.auto.speed == 8.0
    secs = 40
    for j in range(secs * 30):
        run.frame(1 / 30, 70 + j % 3 * 25, 22 + j % 2 * 10, draw=j % 30 == 0)
    assert run.key("esc") == "stop"
    assert run.g.cave_i > 0 or run.g.score > 0
    print("auto mode: %d s at x8, reached %s with %d points, round %d, nothing recorded" % (
        secs, run.g.label(), run.g.score, run.rounds))
    # 8. simulation speed
    c = Cave(CAVES[22], 1, seed=2)
    a = time.time()
    for _ in range(2000):
        c.step()
    us = (time.time() - a) / 2000 * 1e6
    g = Game(1, 23, seed=2, quiet=True)
    g.state = "play"
    bot = Bot(g, seed=2)
    a = time.time()
    m = 0
    while g.state == "play" and m < 400:
        g.update(TICK, bot)
        m += 1
    print("simulation: %.0f us per cave tick, %.1f ms per tick with the autopilot planning" % (
        us, (time.time() - a) / max(1, m) * 1000))
    print("Self-test ok (%.1f s)" % (time.time() - t0))


def screenshot(cols=100, rows=32):
    """README picture: real play in the Glowmoss Grotto (cave 2-1 GLASSWING HOLLOW, seed 3) by the auto-mode
    autopilot, 3 s in: the rocks have dropped into a glassmoth's chamber and it bursts into sunstones while Pell
    digs past with the helmet lamp lit. Quiet (no sound), no score written; HI shows this run."""
    g = Game(1, 5, quiet=True, seed=3)
    g.hi = 0
    bot = Bot(g, seed=3)
    for _ in range(90):
        g.update(1 / 30, bot)
    return render(g, cols, rows)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--auto" in sys.argv:
        with KeyTerminal() as _term:
            run_auto(_term, 0)
    else:
        main()
