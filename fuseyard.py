#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""FUSEYARD - fuse-pot duels in a walled yard, for 1 to 4 people: at one keyboard, over the LAN or with the computer.

Four tinkers walk a yard of stone pillars and stacked crates. Each one sets down clay fuse pots that burst in a
cross after a few seconds; the blast runs along the lanes until a pillar stops it, burns the first crate in its
way and sets off any pot it reaches. Burnt crates leave things behind: extra pots, longer blasts, quicker boots,
a kick for pots, a ward that takes one hit, and the curse - it slows you, shortens your fuses, makes you drip
pots or shrinks your blast, and it jumps to whoever you touch. The last tinker standing wins the round; when the
clock runs low, the walls close in. Four yards: Courtyard, Mill Yard, Frost Yard and Foundry.

Play with 1 to 4 people:
  * at one keyboard: one or two players, the computer fills the other places (easy, normal, hard)
  * over the LAN or the WLAN: one player hosts (the server), the others join. Games in the same network show up
    by themselves on the join screen; an address can be typed too. Two people may share each keyboard.

Keys: W A S D / arrows walk, Space / E drop a pot (second player at one keyboard: arrows, Enter / 0),
      Esc / P pause, ? help, V view, M sound.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
Run:        python3 fuseyard.py
Self-test:  python3 fuseyard.py --selftest
"""
import json
import math
import os
import random
import socket
import sys
import time
from collections import deque

import arcadekit
import arcadenet
from arcadenet import Link, clean_name
from arcadekit import (AUTO_LABEL, PAUSE_LINES, TITLE_DIM, AutoMode, Canvas, KeyTerminal, footer, load_scores, mix,
                       overlay, shade, shared_key, submit, title_screen)
from arcadesound import Sound

GAME = "fuseyard"
GW, GH = 15, 13                 # the yard in tiles, the outer ring is wall
DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
FUSE, FIZZ_FUSE = 2.6, 1.3      # seconds until a pot bursts (cursed: short fuses)
FLAME_LIFE = 0.6                # how long a blast burns on a tile
BURN_LIFE = 0.6                 # how long a crate burns before it is gone
KICK_SPEED = 8.0                # tiles per second for a kicked pot
BASE_SPEED, BOOT_SPEED, SLOW_SPEED = 3.4, 0.55, 2.2
MAX_POTS, MAX_FIRE, MAX_BOOTS = 8, 8, 4
ROUND_TIME, CLOSE_TIME = 150.0, 45.0
CURSE_TIME = 12.0
SPAWNS = [(1, 1), (13, 11), (13, 1), (1, 11)]
ITEM_POOL = "PPPPPPPFFFFFFFSSSSKKKWWCC"
ITEMS = {  # letter: (what it does, badge colour)
    "P": ("one pot more", (150, 150, 196)),
    "F": ("a longer blast", (255, 140, 44)),
    "S": ("quicker boots", (84, 196, 255)),
    "K": ("kick pots", (110, 220, 110)),
    "W": ("a ward for one hit", (245, 218, 110)),
    "C": ("the curse", (184, 84, 214)),
}
ITEM_GLYPH = {"P": "P", "F": "F", "S": "S", "K": "K", "W": "W", "C": "?"}
CURSES = ["slow", "fizz", "drip", "short"]
CURSE_TEXT = {"slow": "slow feet", "fizz": "short fuses", "drip": "drips pots", "short": "tiny blasts"}
COLOURS = [(255, 128, 64), (84, 196, 255), (132, 214, 88), (222, 124, 240)]
BOT_NAMES = ["EMBER", "SKY", "MOSS", "PLUM"]
DIFFS = ["easy", "normal", "hard"]
TARGETS = [1, 2, 3, 5]
MIN_COLS, MIN_ROWS = 70, 22
PANEL_W = 24
PORT, BEACON_PORT, PROTO = 47290, 47291, 1
HUD_BG, HUD_FG = (12, 12, 22), (226, 226, 236)
PANEL_BG = (16, 14, 26)
SKIN = (242, 212, 176)

SND = Sound(GAME, {
    "drop": [dict(w="tri", f=220, f2=140, d=0.07, v=0.35), dict(w="noise", f=900, d=0.03, v=0.12, at=0)],
    "boom": [dict(w="noise", f=1400, f2=120, d=0.42, v=0.62), dict(w="square", f=110, f2=40, d=0.3, v=0.3,
                                                                   duty=0.3, at=0)],
    "kick": [dict(w="noise", f=3000, f2=800, d=0.05, v=0.3), dict(w="tri", f=330, f2=520, d=0.08, v=0.25, at=0)],
    "item": [dict(w="square", f=880, d=0.04, v=0.25, duty=0.25), dict(w="square", f=1320, d=0.08, v=0.25, duty=0.25)],
    "curse": [dict(w="saw", f=300, f2=150, d=0.25, v=0.28, vib=(9, 0.8))],
    "ward": [dict(w="tri", f=1047, f2=1568, d=0.12, v=0.3), dict(w="noise", f=6000, d=0.05, v=0.1, at=0)],
    "out": [dict(w="square", f=523, f2=130, d=0.45, v=0.3, duty=0.3, curve="lin")],
    "thud": [dict(w="noise", f=500, f2=80, d=0.18, v=0.45), dict(w="tri", f=90, f2=50, d=0.15, v=0.35, at=0)],
    "intro": [dict(w="tri", f=440, d=0.09, v=0.28), dict(w="tri", f=440, d=0.09, v=0.28, at=0.5)],
    "go": [dict(w="square", f=659, d=0.06, v=0.3, duty=0.25), dict(w="square", f=988, d=0.16, v=0.3, duty=0.25)],
    "round": [dict(w="square", f=f, d=0.08, v=0.28, duty=0.25) for f in (523, 659, 784, 1047)],
    "draw": [dict(w="tri", f=392, d=0.16, v=0.3), dict(w="tri", f=370, d=0.3, v=0.3)],
    "champ": [dict(w="square", f=f, d=0.09, v=0.28, duty=0.25) for f in (523, 659, 784, 1047, 784, 1047)] +
             [dict(w="tri", f=1319, d=0.5, v=0.4, vib=(6, 0.25), r="lin")],
    "close": [dict(w="saw", f=180, f2=120, d=0.35, v=0.25)],
    "join": [dict(w="tri", f=660, d=0.05, v=0.25), dict(w="tri", f=990, d=0.09, v=0.25)],
    "leave": [dict(w="tri", f=660, d=0.05, v=0.25), dict(w="tri", f=440, d=0.09, v=0.25)],
    "menu": [dict(w="tri", f=660, d=0.025, v=0.2)],
    "start": [dict(w="square", f=523, d=0.05, v=0.3, duty=0.25), dict(w="square", f=784, d=0.12, v=0.3, duty=0.25)],
    "pause": [dict(w="tri", f=523, f2=392, d=0.07, v=0.22)],
    "sound_on": [dict(w="tri", f=440, d=0.06, v=0.35), dict(w="tri", f=880, d=0.12, v=0.35)],
})


def help_lines(kitty=True):
    return [
        "FUSEYARD - keys",
        "",
        "W A S D / arrows      walk (alone: either set)",
        "Space / E             drop a fuse pot",
        "Arrows + Enter / 0    the second player at one keyboard",
        "Esc / P  pause   ? help   V view   M sound",
        "",
        "P one pot more   F longer blast   S quicker boots",
        "K kick pots (walk into one)   W ward: takes one hit",
        "? the curse - it jumps to whoever you touch",
        "",
        "Last one standing wins the round. At 0:45 the walls",
        "close in. A tap walks one tile; hold to keep walking.",
        "" if kitty else "(classic terminal: you may walk one tile on.)",
    ]


def rt(v):
    return int(math.floor(v + 0.5))


# =============================================================================================
# The yards: '#' wall, ' ' a crate may stand here, '.' always open; the corners next to the four spawns stay open
# =============================================================================================
def courtyard_rows():
    return ["".join("#" if x in (0, GW - 1) or y in (0, GH - 1) or (x % 2 == 0 and y % 2 == 0) else " "
                    for x in range(GW)) for y in range(GH)]


MILL = [
    "###############",
    "#             #",
    "# # # # # # # #",
    "#             #",
    "# # ### ### # #",
    "#    .....    #",
    "# #  .###.  # #",
    "#    .....    #",
    "# # ### ### # #",
    "#             #",
    "# # # # # # # #",
    "#             #",
    "###############",
]
FROST = [
    "###############",
    "#      #      #",
    "# ##       ## #",
    "#  # # # # #  #",
    "#             #",
    "#  ## # # ##  #",
    "# .   ...   . #",
    "#  ## # # ##  #",
    "#             #",
    "#  # # # # #  #",
    "# ##       ## #",
    "#      #      #",
    "###############",
]
FOUNDRY = [
    "###############",
    "#    #   #    #",
    "# #  #   #  # #",
    "#      #      #",
    "###  #   #  ###",
    "#    #   #    #",
    "#  #   #   #  #",
    "#    #   #    #",
    "###  #   #  ###",
    "#      #      #",
    "# #  #   #  # #",
    "#    #   #    #",
    "###############",
]
YARDS = [
    dict(name="Courtyard", rows=None, floor=((156, 132, 98), (144, 121, 89)), wall=(206, 184, 146),
         crate=(180, 114, 56), bg=(30, 22, 18), crates=0.8),
    dict(name="Mill Yard", rows=MILL, floor=((98, 154, 76), (89, 143, 69)), wall=(152, 114, 76),
         crate=(198, 152, 82), bg=(16, 30, 18), crates=0.78),
    dict(name="Frost Yard", rows=FROST, floor=((194, 216, 232), (182, 206, 226)), wall=(104, 146, 192),
         crate=(158, 122, 94), bg=(12, 20, 36), crates=0.78),
    dict(name="Foundry", rows=FOUNDRY, floor=((78, 72, 80), (69, 63, 73)), wall=(132, 132, 146),
         crate=(164, 98, 52), bg=(16, 10, 14), crates=0.85),
]


def yard_rows(i):
    return YARDS[i]["rows"] or courtyard_rows()


def near_spawn(x, y):
    return any(abs(x - sx) + abs(y - sy) <= 1 for sx, sy in SPAWNS)


def spiral():
    """The order in which the walls close in: ring after ring, from the outside to the middle."""
    out = []
    x0, y0, x1, y1 = 1, 1, GW - 2, GH - 2
    while x0 <= x1 and y0 <= y1:
        out += [(x, y0) for x in range(x0, x1 + 1)]
        out += [(x1, y) for y in range(y0 + 1, y1 + 1)]
        if y1 > y0:
            out += [(x, y1) for x in range(x1 - 1, x0 - 1, -1)]
        if x1 > x0:
            out += [(x0, y) for y in range(y1 - 1, y0, -1)]
        x0, y0, x1, y1 = x0 + 1, y0 + 1, x1 - 1, y1 - 1
    return out


# =============================================================================================
# The game
# =============================================================================================
class Tinker:
    def __init__(self, slot, name, kind, diff=None):
        self.slot, self.name, self.kind, self.diff = slot, name, kind, diff   # kind: human, remote, bot
        self.colour = COLOURS[slot]
        self.wins = self.kills = 0
        self.place(*SPAWNS[slot])

    def place(self, x, y):
        self.x, self.y = float(x), float(y)
        self.alive, self.dead_t = True, 0.0
        self.face, self.moving, self.walk = "down", False, 0.0
        self.pots, self.fire, self.boots, self.kick, self.ward = 1, 2, 0, False, 0
        self.curse, self.curse_t, self.inv = None, 0.0, 0.0
        self.inp, self.nudge, self.nudge_to, self.drop = None, None, None, False
        self.got = []

    @property
    def tile(self):
        return rt(self.x), rt(self.y)

    def speed(self):
        return SLOW_SPEED if self.curse == "slow" else BASE_SPEED + BOOT_SPEED * self.boots

    def reach(self):
        return 1 if self.curse == "short" else self.fire


class Pot:
    def __init__(self, x, y, owner, reach, fuse):
        self.x, self.y = float(x), float(y)
        self.owner, self.reach = owner, reach
        self.fuse = self.fuse0 = fuse
        self.slide = None

    @property
    def tile(self):
        return rt(self.x), rt(self.y)


def approach(v, target, step):
    return min(target, v + step) if v < target else max(target, v - step)


class Match:
    """One match: rounds until someone has `target` wins. players: [(name, kind, diff)] for 2 to 4 slots."""

    def __init__(self, players, yard=-1, target=3, seed=None, demo=False):
        self.rnd = random.Random(seed)
        self.yard_pick, self.target, self.demo = yard, target, demo
        self.tinkers = [Tinker(i, n, k, d) for i, (n, k, d) in enumerate(players)]
        self.brains = {}
        for tk in self.tinkers:
            if tk.kind == "bot":
                self.brains[tk.slot] = Brain(self, tk, tk.diff or "normal", self.rnd)
        self.round = 0
        self.t = 0.0
        self.paused = self.help = False
        self.events = []
        self.debris = []
        self.champ = self.round_winner = None
        self.shake = 0.0
        self.new_round()

    # -- setting up ------------------------------------------------------------------------
    def new_round(self):
        self.round += 1
        self.yard = self.yard_pick if self.yard_pick >= 0 else self.rnd.randrange(len(YARDS))
        y_ = YARDS[self.yard]
        rows = yard_rows(self.yard)
        self.grid = []
        for y in range(GH):
            row = []
            for x in range(GW):
                c = rows[y][x]
                if c == "#":
                    row.append("#")
                elif c == " " and not near_spawn(x, y) and self.rnd.random() < y_["crates"]:
                    row.append("+")
                else:
                    row.append(".")
            self.grid.append(row)
        crates = [(x, y) for y in range(GH) for x in range(GW) if self.grid[y][x] == "+"]
        self.rnd.shuffle(crates)
        pool = list(ITEM_POOL)
        self.rnd.shuffle(pool)
        self.hidden = dict(zip(crates, pool))
        self.pots, self.flames, self.burning, self.falling = [], {}, {}, []
        self.clock, self.closing = ROUND_TIME, False
        self.close_order, self.close_i, self.close_t, self.close_dt = spiral(), 0, 0.0, 0.3
        for tk in self.tinkers:
            tk.place(*SPAWNS[tk.slot])
        for b in self.brains.values():
            b.reset()
        self.state, self.state_t = "intro", 2.0
        self.end_t = None
        self.round_winner = None
        self.sfx("intro")

    def make_bot(self, tk, diff="normal"):
        tk.kind, tk.diff = "bot", diff
        tk.inp = tk.nudge = None
        self.brains[tk.slot] = Brain(self, tk, diff, self.rnd)

    def sfx(self, name):
        self.events.append(name)

    def take_events(self):
        e, self.events = self.events, []
        return e

    # -- the map ---------------------------------------------------------------------------
    def pot_at(self, x, y):
        for p in self.pots:
            if p.tile == (x, y):
                return p
        return None

    def free(self, x, y, tk=None):
        """Can tk walk onto this tile? A pot blocks, except the one tk still stands on."""
        if not (0 <= x < GW and 0 <= y < GH) or self.grid[y][x] in "#+*":
            return False
        p = self.pot_at(x, y)
        return p is None or (tk is not None and tk.tile == (x, y))

    def blast(self, x, y, reach, pot_tiles=None):
        """The tiles a pot at (x, y) burns: [(x, y, kind)], kind 'c' centre, 'h' / 'v' a lane, or the direction of
        an end piece. It stops at walls, burns the first crate, an item or a pot and stops there."""
        has_pot = (lambda t: t in pot_tiles) if pot_tiles is not None else (lambda t: self.pot_at(*t) is not None)
        out = [(x, y, "c")]
        for d, (dx, dy) in DIRS.items():
            for i in range(1, reach + 1):
                tx, ty = x + dx * i, y + dy * i
                c = self.grid[ty][tx]
                if c == "#":
                    break
                if c in "+*":
                    out.append((tx, ty, d))
                    break
                out.append((tx, ty, d if i == reach else ("h" if dx else "v")))
                if c != "." or has_pot((tx, ty)):
                    break
        return out

    def danger(self, extra=None):
        """tile -> (from, until): when a blast will burn there (chains included), from now in seconds.
        extra: a pot that is not there yet, (tile, reach, fuse) - to ask whether dropping one is safe."""
        pots = [(p.tile, p.reach, max(0.0, p.fuse)) for p in self.pots]
        if extra:
            pots.append(extra)
        tiles = {t: i for i, (t, _, _) in enumerate(pots)}
        times = [f for _, _, f in pots]
        blasts = [self.blast(t[0], t[1], r, tiles) for t, r, _ in pots]
        changed = True
        while changed:
            changed = False
            for i, b in enumerate(blasts):
                for tx, ty, _ in b:
                    j = tiles.get((tx, ty))
                    if j is not None and times[j] > times[i]:
                        times[j] = times[i]
                        changed = True
        out = {}

        def add(t, a, b):
            o = out.get(t)
            out[t] = (min(a, o[0]), max(b, o[1])) if o else (a, b)
        for i, b in enumerate(blasts):
            for tx, ty, _ in b:
                add((tx, ty), times[i], times[i] + FLAME_LIFE)
        for t, (age, _, _) in self.flames.items():
            add(t, 0.0, FLAME_LIFE - age)
        for x, y, a in self.falling:
            add((x, y), 0.0, 999.0)
        if self.closing:                         # the next few tiles of the closing walls
            k, n = 0, self.close_i
            while n < len(self.close_order) and k < 10:
                x, y = self.close_order[n]
                if self.grid[y][x] != "#":
                    add((x, y), max(0.0, k * self.close_dt - 0.5), 999.0)
                    k += 1
                n += 1
        return out

    # -- moving ----------------------------------------------------------------------------
    def nudge(self, tk, d, finish=False):
        """A tap: walk one tile in d. finish: only on to the next tile centre ahead (a key let go mid-tile)."""
        if not tk.alive or d not in DIRS:
            return
        dx, dy = DIRS[d]
        cx, cy = tk.tile
        if finish:
            cur, c = (tk.x, cx) if dx else (tk.y, cy)
            s = dx or dy
            if abs(cur - c) < 1e-6 or (cur - c) * s < 0:
                return                               # on a centre already, or the centre is still ahead
            a = (cx + dx, cy + dy)
            if not self.free(a[0], a[1], tk):
                return
            tk.nudge, tk.nudge_to = d, a
            return
        a = (cx + dx, cy + dy)
        tk.nudge = d
        tk.nudge_to = a if self.free(a[0], a[1], tk) else (cx, cy)

    def move(self, tk, d, dt, stop=None):
        """Walk tk in direction d for dt. Lines up with a free lane first (corner help). Returns True if it moved."""
        dx, dy = DIRS[d]
        tk.face = d
        step = tk.speed() * dt
        cx, cy = tk.tile
        off = (tk.y - cy) if dx else (tk.x - cx)
        if abs(off) > 1e-6:
            for lane in (0, 1 if off > 0 else -1):
                lx, ly = (cx + dx, cy + lane) if dx else (cx + lane, cy + dy)
                if self.free(lx, ly, tk) and (lane == 0 or self.free(cx + (0 if dx else lane), cy + (lane if dx else 0), tk)):
                    if dx:
                        tk.y = approach(tk.y, cy + lane, step)
                    else:
                        tk.x = approach(tk.x, cx + lane, step)
                    return True
            return False
        if dx:
            tk.y = float(cy)
        else:
            tk.x = float(cx)
        s = dx or dy
        cur, c = (tk.x, cx) if dx else (tk.y, cy)
        ax, ay = cx + dx, cy + dy
        blocked = not self.free(ax, ay, tk)
        if blocked and tk.kick and abs(cur - c) < 0.25:
            p = self.pot_at(ax, ay)
            if p and p.slide is None and self.pot_can_go(p, d):
                p.slide = d
                self.sfx("kick")
        lim = c if blocked else c + s
        if stop is not None:
            st = stop[0] if dx else stop[1]
            lim = min(lim, st) if s > 0 else max(lim, st)
        nv = cur + s * step
        nv = min(nv, lim) if s > 0 else max(nv, lim)
        if (nv - cur) * s <= 0:
            return False
        if dx:
            tk.x = nv
        else:
            tk.y = nv
        tk.walk += abs(nv - cur)
        return True

    def pot_can_go(self, p, d):
        dx, dy = DIRS[d]
        tx, ty = p.tile
        ax, ay = tx + dx, ty + dy
        if self.grid[ay][ax] != "." or self.pot_at(ax, ay):
            return False
        return not any(tk.alive and tk.tile == (ax, ay) for tk in self.tinkers)

    def slide_pot(self, p, dt):
        dx, dy = DIRS[p.slide]
        tx, ty = p.tile
        s = dx or dy
        cur, c = (p.x, tx) if dx else (p.y, ty)
        ok = self.pot_can_go(p, p.slide)
        lim = c + s if ok else c
        nv = cur + s * KICK_SPEED * dt
        nv = min(nv, lim) if s > 0 else max(nv, lim)
        if dx:
            p.x = nv
        else:
            p.y = nv
        if not ok and abs(nv - c) < 1e-9:
            p.slide = None

    def try_drop(self, tk):
        x, y = tk.tile
        if self.grid[y][x] != "." or self.pot_at(x, y) or (x, y) in self.flames:
            return False
        if sum(1 for p in self.pots if p.owner == tk.slot) >= tk.pots:
            return False
        self.pots.append(Pot(x, y, tk.slot, tk.reach(), FIZZ_FUSE if tk.curse == "fizz" else FUSE))
        self.sfx("drop")
        return True

    # -- blasts ----------------------------------------------------------------------------
    def explode(self, p):
        if p not in self.pots:
            return
        self.pots.remove(p)
        x, y = p.tile
        for tx, ty, kind in self.blast(x, y, p.reach):
            c = self.grid[ty][tx]
            if c == "+":
                self.grid[ty][tx] = "*"
                self.burning[(tx, ty)] = 0.0
                self.shards(tx, ty)
                continue
            if c == "*":
                continue
            if c in ITEMS:
                self.grid[ty][tx] = "."
            q = self.pot_at(tx, ty)
            if q:
                q.fuse = min(q.fuse, 0.08)
                q.slide = None
            old = self.flames.get((tx, ty))
            if old and old[1] != kind:
                kind = "c"
            self.flames[(tx, ty)] = [0.0, kind, p.owner]
        self.shake = 0.22
        self.sfx("boom")

    def shards(self, x, y):
        col = YARDS[self.yard]["crate"]
        for _ in range(6):
            a = self.rnd.uniform(0, math.tau)
            v = self.rnd.uniform(1.0, 3.0)
            self.debris.append([x + 0.5, y + 0.5, math.cos(a) * v, math.sin(a) * v - 1.5, 0.0,
                                shade(col, self.rnd.uniform(0.6, 1.2))])

    def hit(self, tk, owner):
        if tk.ward:
            tk.ward -= 1
            tk.inv = 1.6
            self.sfx("ward")
            return
        self.kill(tk)
        if owner is not None and owner != tk.slot and owner < len(self.tinkers):
            self.tinkers[owner].kills += 1

    def kill(self, tk):
        tk.alive, tk.dead_t = False, 0.0
        tk.inp = tk.nudge = None
        self.sfx("out")
        got = list(tk.got)
        self.rnd.shuffle(got)
        spots = [(x, y) for y in range(GH) for x in range(GW) if self.grid[y][x] == "." and (x, y) not in self.flames
                 and not self.pot_at(x, y) and not any(o.alive and o.tile == (x, y) for o in self.tinkers)]
        self.rnd.shuffle(spots)
        for it, (x, y) in zip(got[:3], spots):
            self.grid[y][x] = it

    def pick_up(self, tk):
        x, y = tk.tile
        c = self.grid[y][x]
        if c not in ITEMS:
            return
        self.grid[y][x] = "."
        if c == "C":
            tk.curse, tk.curse_t = self.rnd.choice(CURSES), CURSE_TIME
            self.sfx("curse")
            return
        if c == "P":
            tk.pots = min(MAX_POTS, tk.pots + 1)
        elif c == "F":
            tk.fire = min(MAX_FIRE, tk.fire + 1)
        elif c == "S":
            tk.boots = min(MAX_BOOTS, tk.boots + 1)
        elif c == "K":
            tk.kick = True
        elif c == "W":
            tk.ward = 1
        tk.got.append(c)
        self.sfx("item")

    # -- the clock -------------------------------------------------------------------------
    def update_closing(self, dt):
        if not self.closing and self.clock <= CLOSE_TIME:
            self.closing = True
            open_ = sum(1 for x, y in self.close_order if self.grid[y][x] != "#")
            self.close_dt = CLOSE_TIME * 0.92 / max(1, open_)
            self.sfx("close")
        if self.closing:
            self.close_t += dt
            while self.close_t >= self.close_dt and self.close_i < len(self.close_order):
                x, y = self.close_order[self.close_i]
                self.close_i += 1
                if self.grid[y][x] == "#":
                    continue
                self.close_t -= self.close_dt
                self.falling.append([x, y, 0.0])
        for f in list(self.falling):
            f[2] += dt
            if f[2] >= 0.45:
                self.falling.remove(f)
                x, y = f[0], f[1]
                self.grid[y][x] = "#"
                self.flames.pop((x, y), None)
                self.burning.pop((x, y), None)
                self.hidden.pop((x, y), None)
                self.pots = [p for p in self.pots if p.tile != (x, y)]
                for tk in self.tinkers:
                    if tk.alive and tk.tile == (x, y):
                        self.kill(tk)
                self.sfx("thud")

    # -- one step --------------------------------------------------------------------------
    def advance(self, dt):
        """Real time in small fixed steps (a slow frame never makes anyone jump through a wall)."""
        n = max(1, int(math.ceil(dt / (1 / 60) - 1e-9)))
        for _ in range(min(n, 12)):
            self.update(dt / n)

    def update(self, dt):
        if self.paused:
            return
        self.t += dt
        self.shake = max(0.0, self.shake - dt)
        for d in list(self.debris):
            d[0] += d[2] * dt
            d[1] += d[3] * dt
            d[3] += 9 * dt
            d[4] += dt
            if d[4] > 0.6:
                self.debris.remove(d)
        for tk in self.tinkers:
            if not tk.alive:
                tk.dead_t += dt
        if self.state == "intro":
            self.state_t -= dt
            if self.state_t <= 0:
                self.state = "play"
                self.sfx("go")
            return
        if self.state == "over":
            self.state_t -= dt
        elif self.state == "roundend":
            self.state_t -= dt
            if self.state_t <= 0:
                self.new_round()
                return
        playing = self.state == "play"
        if playing:
            self.clock = max(0.0, self.clock - dt)
            self.update_closing(dt)
            for tk in self.tinkers:
                if tk.alive:
                    self.update_tinker(tk, dt)
            self.spread_curse()
        for p in list(self.pots):
            p.fuse -= dt
            if p.slide:
                self.slide_pot(p, dt)
            f = self.flames.get(p.tile)
            if f and f[0] < FLAME_LIFE:
                p.fuse = min(p.fuse, 0.05)
        for p in list(self.pots):
            if p.fuse <= 0:
                self.explode(p)
        for t, f in list(self.flames.items()):
            f[0] += dt
            if f[0] >= FLAME_LIFE:
                del self.flames[t]
        for t in list(self.burning):
            self.burning[t] += dt
            if self.burning[t] >= BURN_LIFE:
                del self.burning[t]
                self.grid[t[1]][t[0]] = self.hidden.pop(t, ".")
        if playing:
            for tk in self.tinkers:
                if tk.alive and tk.inv <= 0:
                    f = self.flames.get(tk.tile)
                    if f:
                        self.hit(tk, f[2])
            self.check_end(dt)

    def update_tinker(self, tk, dt):
        brain = self.brains.get(tk.slot)
        if brain:
            brain.update(dt)
        tk.inv = max(0.0, tk.inv - dt)
        if tk.curse:
            tk.curse_t -= dt
            if tk.curse_t <= 0:
                tk.curse = None
        if tk.nudge and tk.inp not in (None, tk.nudge):
            tk.nudge = None
        d = tk.inp or tk.nudge
        moved = False
        if d:
            stop = tk.nudge_to if (tk.inp is None and tk.nudge) else None
            moved = self.move(tk, d, dt, stop)
        if tk.nudge and tk.inp is None:
            tx, ty = tk.nudge_to
            if not moved or (abs(tk.x - tx) < 1e-9 and abs(tk.y - ty) < 1e-9):
                tk.nudge = None
        tk.moving = moved
        self.pick_up(tk)
        if tk.drop or tk.curse == "drip":
            self.try_drop(tk)
            tk.drop = False

    def spread_curse(self):
        alive = [tk for tk in self.tinkers if tk.alive]
        for a in alive:
            if not a.curse:
                continue
            for b in alive:
                if b is not a and not b.curse and abs(a.x - b.x) + abs(a.y - b.y) < 0.75:
                    b.curse, b.curse_t = a.curse, CURSE_TIME
                    self.sfx("curse")

    def check_end(self, dt):
        alive = [tk for tk in self.tinkers if tk.alive]
        if self.end_t is None and (len(alive) <= 1 or self.clock <= 0):
            self.end_t = 0.8 if len(alive) <= 1 else 0.0
        if self.end_t is not None:
            self.end_t -= dt
            if self.end_t <= 0:
                self.finish_round()

    def finish_round(self):
        alive = [tk for tk in self.tinkers if tk.alive]
        self.end_t = None
        if len(alive) == 1:
            w = alive[0]
            w.wins += 1
            self.round_winner = w.slot
            if w.wins >= self.target:
                self.state, self.state_t, self.champ = "over", 0.0, w.slot
                self.sfx("champ")
                return
            self.sfx("round")
        else:
            self.round_winner = None
            self.sfx("draw")
        self.state, self.state_t = "roundend", 3.2

    # -- the network picture ---------------------------------------------------------------
    def snapshot(self):
        """Everything a screen needs, as plain JSON (the host sends this to the other players)."""
        r = lambda v: round(v, 3)
        return {"t": "state", "grid": "".join("".join(row) for row in self.grid), "yard": self.yard,
                "state": self.state, "state_t": r(self.state_t), "clock": r(self.clock), "closing": self.closing,
                "round": self.round, "target": self.target, "rw": self.round_winner, "champ": self.champ,
                "time": r(self.t), "shake": r(self.shake),
                "tk": [[tk.name, tk.kind, tk.diff, r(tk.x), r(tk.y), tk.alive, r(tk.dead_t), tk.face, tk.moving,
                        r(tk.walk), tk.pots, tk.fire, tk.boots, tk.kick, tk.ward, tk.curse, r(tk.curse_t), r(tk.inv),
                        tk.wins, tk.kills] for tk in self.tinkers],
                "pots": [[r(p.x), r(p.y), r(p.fuse), p.fuse0, p.owner] for p in self.pots],
                "fl": [[x, y, r(a), k] for (x, y), (a, k, o) in self.flames.items()],
                "bu": [[x, y, r(a)] for (x, y), a in self.burning.items()],
                "fa": [[x, y, r(a)] for x, y, a in self.falling]}

    @classmethod
    def restore(cls, d, prev=None):
        """A Match to draw from a snapshot (no simulation). None if the snapshot does not make sense."""
        try:
            g = cls.__new__(cls)
            grid = str(d["grid"])
            if len(grid) != GW * GH or any(c not in "#+*." and c not in ITEMS for c in grid):
                return None
            g.grid = [list(grid[y * GW:(y + 1) * GW]) for y in range(GH)]
            g.yard = int(d["yard"]) % len(YARDS)
            g.state = d["state"] if d["state"] in ("intro", "play", "roundend", "over") else "play"
            g.state_t, g.clock, g.t = float(d["state_t"]), float(d["clock"]), float(d["time"])
            g.closing, g.round, g.target = bool(d["closing"]), int(d["round"]), int(d["target"])
            g.shake = float(d.get("shake", 0))
            rows = d["tk"]
            if not 1 <= len(rows) <= 4:
                return None
            g.tinkers = []
            for i, row in enumerate(rows):
                tk = Tinker.__new__(Tinker)
                (name, kind, diff, x, y, alive, dead_t, face, moving, walk, pots, fire, boots, kick, ward, curse,
                 curse_t, inv, wins, kills) = row
                tk.slot, tk.colour = i, COLOURS[i]
                tk.name, tk.kind, tk.diff = clean_name(name), str(kind), diff if diff in DIFFS else None
                tk.x, tk.y, tk.alive, tk.dead_t = float(x), float(y), bool(alive), float(dead_t)
                tk.face = face if face in DIRS else "down"
                tk.moving, tk.walk = bool(moving), float(walk)
                tk.pots, tk.fire, tk.boots, tk.kick, tk.ward = int(pots), int(fire), int(boots), bool(kick), int(ward)
                tk.curse = curse if curse in CURSES else None
                tk.curse_t, tk.inv, tk.wins, tk.kills = float(curse_t), float(inv), int(wins), int(kills)
                tk.inp = tk.nudge = tk.nudge_to = None
                tk.drop, tk.got = False, []
                g.tinkers.append(tk)
            rw, ch = d.get("rw"), d.get("champ")
            g.round_winner = rw if isinstance(rw, int) and 0 <= rw < len(g.tinkers) else None
            g.champ = ch if isinstance(ch, int) and 0 <= ch < len(g.tinkers) else None
            g.pots = []
            for x, y, fuse, fuse0, owner in d["pots"]:
                p = Pot(float(x), float(y), int(owner), 1, float(fuse0))
                p.fuse = float(fuse)
                g.pots.append(p)
            g.flames = {(int(x), int(y)): [float(a), str(k), None] for x, y, a, k in d["fl"]}
            g.burning = {(int(x), int(y)): float(a) for x, y, a in d["bu"]}
            g.falling = [[int(x), int(y), float(a)] for x, y, a in d["fa"]]
        except (KeyError, TypeError, ValueError, IndexError):
            return None
        g.rnd = random.Random()
        g.brains, g.events, g.hidden = {}, [], {}
        g.debris = prev.debris if prev is not None else []
        g.paused = g.help = False
        g.demo = False
        if prev is not None:                         # crates that started burning: let the shards fly here too
            for t in g.burning:
                if t not in prev.burning:
                    g.shards(*t)
            dt = max(0.0, min(0.2, g.t - prev.t))
            for dd in list(g.debris):
                dd[0] += dd[2] * dt
                dd[1] += dd[3] * dt
                dd[3] += 9 * dt
                dd[4] += dt
                if dd[4] > 0.6:
                    g.debris.remove(dd)
        return g


# =============================================================================================
# The computer: steps out of every blast it can foresee, burns crates, grabs things and hunts
# =============================================================================================
class Brain:
    PROFILE = {
        "easy": dict(think=0.42, err=0.25, margin=0.5, hunt=0.25, items=0.5, wander=0.35),
        "normal": dict(think=0.2, err=0.06, margin=0.38, hunt=0.6, items=0.85, wander=0.15),
        "hard": dict(think=0.07, err=0.0, margin=0.28, hunt=1.0, items=1.0, wander=0.05),
    }

    def __init__(self, g, tk, diff, rnd):
        self.g, self.tk, self.rnd = g, tk, rnd
        self.p = self.PROFILE.get(diff, self.PROFILE["normal"])
        self.reset()

    def reset(self):
        self.cool = self.rnd.uniform(0.1, 0.5)
        self.path, self.drop_at = [], None

    def update(self, dt):
        tk = self.tk
        if self.path and tk.tile == self.path[0]:
            self.path.pop(0)
        self.cool -= dt
        if self.cool <= 0:
            self.cool = self.p["think"] * self.rnd.uniform(0.7, 1.3)
            self.plan()
        if self.drop_at and tk.tile == self.drop_at and abs(tk.x - rt(tk.x)) + abs(tk.y - rt(tk.y)) < 0.3:
            self.drop_at = None
            if self.safe_drop():
                tk.drop = True
                self.cool = 0.0
        tk.inp = None
        if self.path:
            cx, cy = tk.tile
            nx, ny = self.path[0]
            step = (nx - cx, ny - cy)
            for d, v in DIRS.items():
                if v == step:
                    tk.inp = d
            if tk.inp is None:
                self.path = []
                self.cool = 0.0

    # -- searching -------------------------------------------------------------------------
    def bfs(self, danger, start=None, margin=None):
        g, tk = self.g, self.tk
        start = start or tk.tile
        speed = tk.speed()
        margin = self.p["margin"] if margin is None else margin
        dist, prev = {start: 0}, {start: None}
        q = deque([start])
        while q:
            t = q.popleft()
            for dx, dy in DIRS.values():
                n = (t[0] + dx, t[1] + dy)
                if n in dist or not g.free(n[0], n[1], tk):
                    continue
                arrive = (dist[t] + 1) / speed
                dz = danger.get(n)
                if dz and arrive - margin < dz[1] and arrive + 1.0 / speed + margin > dz[0]:
                    continue
                dist[n] = dist[t] + 1
                prev[n] = t
                q.append(n)
        return dist, prev

    @staticmethod
    def path_to(prev, t):
        out = []
        while prev.get(t) is not None:
            out.append(t)
            t = prev[t]
        return out[::-1]

    def escape(self, danger, start=None, desperate=False):
        """The shortest safe way to a tile no blast will reach. desperate: no time to spare any more, so take the
        tightest way there is (no margin), or at least the tile that burns last."""
        for margin in ((self.p["margin"], -0.12) if desperate else (self.p["margin"],)):
            dist, prev = self.bfs(danger, start, margin)
            best = None
            for t, d in dist.items():
                if t not in danger and (best is None or d < dist[best]):
                    best = t
            if best is not None:
                return self.path_to(prev, best), dist[best]
        if desperate:
            dist, prev = self.bfs({t: v for t, v in danger.items() if v[0] <= 0}, start, 0.0)
            here = danger.get(start or self.tk.tile, (0, 0))[0]
            best = max(dist, key=lambda t: (danger.get(t, (99, 0))[0] - dist[t] / self.tk.speed(), -dist[t]))
            if danger.get(best, (99, 0))[0] - dist[best] / self.tk.speed() > here:
                return self.path_to(prev, best), dist[best]
        return None, None

    def safe_drop(self, at=None, careless=True):
        """Is there a way out of a pot dropped at `at` (default: here) before it bursts?"""
        g, tk = self.g, self.tk
        if careless and self.rnd.random() < self.p["err"]:
            return True                                   # a careless one does not check
        at = at or tk.tile
        fuse = FIZZ_FUSE if tk.curse == "fizz" else FUSE
        danger = g.danger(extra=(at, tk.reach(), fuse))
        path, steps = self.escape(danger, at)
        return path is not None and steps / tk.speed() < fuse - self.p["margin"]

    def plan(self):
        g, tk, p = self.g, self.tk, self.p
        danger = g.danger()
        here = tk.tile
        self.drop_at = None
        if here in danger:
            path, _ = self.escape(danger, desperate=True)
            self.path = path or []
            return
        dist, prev = self.bfs(danger)
        foes = [o for o in g.tinkers if o.alive and o is not tk]
        free_pots = sum(1 for q in g.pots if q.owner == tk.slot) < tk.pots
        cands = []
        for t, d in dist.items():
            if t in danger:
                continue
            c = g.grid[t[1]][t[0]]
            v, dr = 0.0, False
            if c in ITEMS and c != "C" and self.rnd.random() < p["items"]:
                v = 5.0
            elif c == "C":
                continue
            if free_pots and c == "." and not g.pot_at(*t):
                crates = foes_hit = 0
                lanes = g.blast(t[0], t[1], tk.reach())
                hit = {(x, y) for x, y, _ in lanes}
                for x, y, _ in lanes:
                    if g.grid[y][x] == "+":
                        crates += 1
                for o in foes:
                    if o.tile in hit:
                        foes_hit += 1
                s = crates * 2.0 + foes_hit * 4.0 * p["hunt"]
                if s > v:
                    v, dr = s, True
            if v <= 0:
                continue
            cands.append((v / (d + 1.5), t, dr))
        cands.sort(reverse=True)
        best, drop = None, False
        for _, t, dr in cands[:8]:                       # the best place that leaves a way out
            if not dr or self.safe_drop(t, careless=False):
                best, drop = t, dr
                break
        if best is None and foes and self.rnd.random() > p["wander"]:
            calm = [t for t in dist if t not in danger]
            near = min(calm, key=lambda t: min(abs(t[0] - o.x) + abs(t[1] - o.y) for o in foes)) if calm else here
            if near != here:
                best = near
        if best is None:
            near = [t for t, d in dist.items() if 0 < d <= 4 and t not in danger]
            best = self.rnd.choice(near) if near else None
        if best is None:
            self.path = []
            return
        if best == here:
            self.path = []
            if drop and self.safe_drop():
                tk.drop = True
                self.cool = 0.0
            return
        self.path = self.path_to(prev, best)
        if drop:
            self.drop_at = best


# =============================================================================================
# Keys -> what each local player wants (one or two players at this keyboard)
# =============================================================================================
P_KEYS = [{"w": "up", "s": "down", "a": "left", "d": "right"},
          {"up": "up", "down": "down", "left": "left", "right": "right"}]
P_DROP = [(" ", "e", "tab"), ("enter", "0", "/")]


class Controls:
    """kitty protocol: held keys walk, a tap walks one tile, letting go walks on to the next tile centre.
    Classic terminals: every press (and every key repeat) walks on to the next tile."""

    def __init__(self, kitty, n):
        self.kitty, self.n = kitty, n
        self.held = [[], []]

    def who(self, name):
        for i in (0, 1):
            p = i if self.n == 2 else 0
            if name in P_KEYS[i]:
                return p, P_KEYS[i][name]
            if name in P_DROP[i]:
                return p, "drop"
        return None

    def feed(self, name, kind):
        """Actions: [('drop', p)], [('nudge', p, d, finish)]."""
        w = self.who(name)
        if not w:
            return []
        p, what = w
        if what == "drop":
            return [("drop", p)] if kind == "press" else []
        if not self.kitty:
            return [("nudge", p, what, False)] if kind != "release" else []
        h = self.held[p]
        if what in h:
            h.remove(what)
        if kind == "release":
            return [("nudge", p, what, True)]
        h.append(what)
        return [("nudge", p, what, False)] if kind == "press" else []

    def direction(self, p):
        h = self.held[p]
        return h[-1] if self.kitty and h else None

    def clear(self):
        self.held = [[], []]


def apply_actions(g, actions, slots):
    """Local key actions onto the tinkers: slots[p] is the tinker index of local player p."""
    for a in actions:
        if a[1] >= len(slots):
            continue
        tk = g.tinkers[slots[a[1]]]
        if not tk.alive or g.state != "play":
            continue
        if a[0] == "drop":
            tk.drop = True
        else:
            g.nudge(tk, a[2], a[3])


# =============================================================================================
# The LAN: one player hosts (a TCP server that runs the game), the others join; the host shouts a small UDP
# beacon once a second so the join screen finds it. JSON lines both ways; nothing received is ever run.
# =============================================================================================
class Host(arcadenet.Host):
    """The listening socket and the beacon (see arcadenet)."""

    def __init__(self, port=PORT, beacon=True):
        super().__init__(GAME, PROTO, port, beacon)


class Finder(arcadenet.Finder):
    """Listens for FUSEYARD beacons: hosts[(ip, port)] = dict(name, n, m, open, seen)."""

    def __init__(self, port=BEACON_PORT):
        super().__init__(GAME, PROTO, port)


class LanServer:
    """The host's side: who sits in which slot (the lobby), and once started the match, which runs here."""

    def __init__(self, cfg, port=PORT, beacon=True):
        self.cfg = cfg
        self.net = Host(port, beacon)
        self.port, self.ip = self.net.port, self.net.ip
        self.slots = [dict(name=cfg["name"], kind="here", link=None, p=0)]
        if cfg["local"] == 2:
            self.slots.append(dict(name="PLAYER 2", kind="here", link=None, p=1))
        self.g = None
        self.pending = []
        self.sent_at = self.lobby_at = 0.0
        self.notes = deque(maxlen=3)
        self.sounds = []

    def note(self, s):
        self.notes.append(s)

    def total(self):
        return min(4, max(2, self.cfg["total"], len(self.slots)))

    def here(self):
        return [i for i, s in enumerate(self.slots) if s["kind"] == "here"]

    def remote_count(self):
        return sum(1 for s in self.slots if s["kind"] == "lan")

    def poll(self, now):
        self.net.accept()
        for ln in list(self.net.links):
            for m in ln.recv():
                self.handle(ln, m)
            if not ln.hello and time.time() - ln.since > 5:
                ln.closed = True
            ln.flush()
            if ln.closed:
                self.drop_link(ln)
        self.net.beacon(now, dict(name=self.cfg["name"], n=len(self.slots),
                                  open=self.g is None and len(self.slots) < 4))
        if self.g is None and now >= self.lobby_at:
            self.send_lobby()
            self.lobby_at = now + 1.0

    def handle(self, ln, m):
        t = m.get("t")
        if t == "hello" and not ln.hello:
            ln.hello = True
            why = None
            if m.get("p") != PROTO:
                why = "the host runs another version of FUSEYARD"
            elif self.g is not None:
                why = "that game has already started"
            elif len(self.slots) >= 4:
                why = "that game is full (4 players)"
            if why:
                ln.send({"t": "no", "why": why})
                ln.closed = True
                return
            n = min(2 if m.get("n") == 2 else 1, 4 - len(self.slots))
            name = clean_name(m.get("name"))
            for p in range(n):
                self.slots.append(dict(name=name if p == 0 else (name[:6] + " 2"), kind="lan", link=ln, p=p))
            ln.send({"t": "welcome", "you": self.you(ln)})
            self.note("%s joined" % name)
            self.sounds.append("join")
            self.send_lobby()
            return
        if self.g is None or t not in ("in", "nu", "dr"):
            return
        p = m.get("p")
        if t == "in":
            ds = m.get("d")
            if not isinstance(ds, list):
                return
            for i, d in enumerate(ds[:2]):
                tk = self.tinker_of(ln, i)
                if tk is not None and tk.kind == "remote":
                    tk.inp = d if d in DIRS and tk.alive and self.g.state == "play" else None
            return
        tk = self.tinker_of(ln, p)
        if tk is None or tk.kind != "remote" or not tk.alive or self.g.state != "play":
            return
        if t == "dr":
            tk.drop = True
        elif m.get("d") in DIRS:
            self.g.nudge(tk, m["d"], bool(m.get("f")))

    def tinker_of(self, ln, p):
        for i, s in enumerate(self.slots):
            if s["link"] is ln and s["p"] == p and self.g is not None and i < len(self.g.tinkers):
                return self.g.tinkers[i]
        return None

    def you(self, ln):
        return [i for i, s in enumerate(self.slots) if s["link"] is ln]

    def drop_link(self, ln):
        if ln in self.net.links:
            self.net.links.remove(ln)
        ln.close()
        mine = [i for i, s in enumerate(self.slots) if s["link"] is ln]
        if not mine:
            return
        name = self.slots[mine[0]]["name"]
        if self.g is None:
            self.slots = [s for s in self.slots if s["link"] is not ln]
            self.note("%s left" % name)
            self.send_lobby()
        else:
            for i in mine:
                self.slots[i].update(kind="gone", link=None)
                if i < len(self.g.tinkers):
                    self.g.make_bot(self.g.tinkers[i], "normal")
            self.note("%s left - the computer plays on" % name)
        self.sounds.append("leave")

    def lobby_rows(self):
        rows = [[s["name"], s["kind"]] for s in self.slots]
        for i in range(len(self.slots), self.total()):
            rows.append([BOT_NAMES[i], "bot"])
        return rows

    def send_lobby(self):
        base = {"t": "lobby", "slots": self.lobby_rows(), "yard": yard_label(self.cfg["yard"]),
                "target": self.cfg["target"], "diff": self.cfg["diff"]}
        for ln in self.net.links:
            if ln.hello:
                ln.send(dict(base, you=self.you(ln)))

    def start(self, seed=None):
        players = [(s["name"], "human" if s["kind"] == "here" else "remote", None) for s in self.slots]
        for i in range(len(players), self.total()):
            players.append((BOT_NAMES[i], "bot", self.cfg["diff"]))
        self.g = Match(players, yard=self.cfg["yard"], target=self.cfg["target"], seed=seed)
        self.pending = []
        for ln in self.net.links:
            if ln.hello:
                ln.send({"t": "start", "you": self.you(ln)})
        return self.g

    def send_state(self, now, events, force=False):
        self.pending += events
        if not force and now - self.sent_at < 1 / 30:
            return
        self.sent_at = now
        snap = self.g.snapshot()
        snap["ev"], self.pending = self.pending[-24:], []
        data = (json.dumps(snap, separators=(",", ":")) + "\n").encode()
        for ln in self.net.links:
            if ln.hello and len(ln.out) < 256 * 1024:   # a slow link misses frames instead of falling behind
                ln.send_raw(data)

    def to_lobby(self):
        self.g = None
        self.slots = [s for s in self.slots if s["kind"] != "gone"]
        self.send_lobby()

    def close(self):
        for ln in self.net.links:
            ln.send({"t": "bye"})
        self.net.close()


class LanClient:
    """A joined player's side: sends the keys, draws what the host sends."""

    def __init__(self, addr, port, name, n, timeout=2.5):
        s = socket.create_connection((addr, port), timeout=timeout)
        self.link = Link(s)
        self.link.send({"t": "hello", "p": PROTO, "name": name, "n": n})
        self.state, self.lobby, self.view, self.you, self.why = "wait", None, None, [], None
        self.addr = "%s:%d" % (addr, port)

    def poll(self):
        sounds = []
        for m in self.link.recv():
            t = m.get("t")
            if t in ("welcome", "start", "lobby"):
                you = m.get("you")
                if isinstance(you, list) and all(isinstance(i, int) and 0 <= i < 4 for i in you):
                    self.you = you[:2]
            if t == "welcome":
                self.state = "lobby"
            elif t == "lobby":
                self.lobby, self.state, self.view = m, "lobby", None
            elif t == "start":
                self.state = "game"
            elif t == "state":
                v = Match.restore(m, self.view)
                if v is not None:
                    self.view, self.state = v, "game"
                    sounds += [e for e in m.get("ev", []) if isinstance(e, str) and e in SND.bank]
            elif t == "no":
                self.why, self.state = str(m.get("why", "the host said no"))[:60], "closed"
            elif t == "bye":
                self.why, self.state = "the host ended the game", "closed"
        self.link.flush()
        if self.link.closed and self.state != "closed":
            self.why, self.state = self.why or "the connection to the host was lost", "closed"
        return sounds

    def send(self, m):
        self.link.send(m)

    def close(self):
        self.link.close()


# =============================================================================================
# Drawing
# =============================================================================================
def layout(cols, rows, hud=True):
    H = (rows - 1) * 2 if hud else rows * 2
    panel = PANEL_W if hud and cols >= PANEL_W + GW * 3 else 0
    s = min(H // GH, (cols - panel) // GW)
    if s < 3:
        raise ValueError("too small for the yard")
    ox = panel + (cols - panel - GW * s) // 2
    oy = (H - GH * s) // 2
    return s, ox, oy, panel


def disc(cv, x, y, r, c):
    r = max(0.5, r)
    rr = r * r
    for yy in range(int(y - r) - 1, int(y + r) + 2):
        for xx in range(int(x - r) - 1, int(x + r) + 2):
            if (xx + 0.5 - x) ** 2 + (yy + 0.5 - y) ** 2 <= rr:
                cv.set(xx, yy, c)


def draw_floor(cv, px, py, s, c, x, y):
    cv.rect(px, py, s, s, c)
    if s >= 5 and (x * 7 + y * 13) % 5 == 0:
        cv.set(px + (x * 3 + y) % (s - 2) + 1, py + (y * 5 + x) % (s - 2) + 1, shade(c, 0.86))


def draw_wall(cv, px, py, s, c, x, y):
    cv.rect(px, py, s, s, shade(c, 0.8))
    cv.rect(px, py, s, max(1, s // 4), shade(c, 1.14))
    cv.rect(px, py + s - 1, s, 1, shade(c, 0.55))
    if s >= 6:
        seam = shade(c, 0.64)
        cv.rect(px, py + s // 2, s, 1, seam)
        cv.rect(px + (s // 2 if (x + y) % 2 else s // 4), py + s // 4, 1, s // 4, seam)
        cv.rect(px + (s // 4 if (x + y) % 2 else s * 3 // 4), py + s // 2 + 1, 1, s // 2 - 2, seam)


def draw_crate(cv, px, py, s, c):
    cv.rect(px, py, s, s, shade(c, 0.55))
    if s >= 4:
        cv.rect(px + 1, py + 1, s - 2, s - 2, c)
        cv.rect(px + 1, py + 1, s - 2, 1, shade(c, 1.18))
    else:
        cv.rect(px, py, s - 1, s - 1, c)
    if s >= 5:
        cv.line(px + 1, py + s - 2, px + s - 2, py + 1, shade(c, 0.72))


def draw_burning(cv, px, py, s, c, age, t):
    k = min(1.0, age / BURN_LIFE)
    base = mix(c, (40, 20, 14), k)
    cv.rect(px, py, s, s, shade(base, 0.7))
    for i in range(s):
        h = int(s * (1 - k) * (0.5 + 0.5 * math.sin(t * 30 + i * 1.7 + px)))
        if h > 0:
            cv.rect(px + i, py + s - h, 1, h, mix((255, 210, 90), (230, 70, 30), (i % 3) / 2))


def draw_item(cv, px, py, s, c, t):
    col = ITEMS[c][1]
    m = max(0, s // 6)
    glow = 1.0 + 0.12 * math.sin(t * 5 + px)
    cv.rect(px + m, py + m, s - 2 * m, s - 2 * m, shade(col, 0.6))
    cv.rect(px + m + (1 if s >= 5 else 0), py + m + (1 if s >= 5 else 0), s - 2 * m - (2 if s >= 5 else 0),
            s - 2 * m - (2 if s >= 5 else 0), shade(col, glow))


def item_letters(cv, g, s, ox, oy):
    for y in range(GH):
        for x in range(GW):
            c = g.grid[y][x]
            if c in ITEMS:
                row = (oy + y * s + s // 2) // 2
                col = ox + x * s + s // 2
                fg = (30, 20, 40) if c != "C" else (250, 236, 255)
                cv.put(col, row, ITEM_GLYPH[c], fg, ITEMS[c][1])


def draw_pot(cv, p, s, ox, oy, t):
    cx, cy = ox + (p.x + 0.5) * s, oy + (p.y + 0.5) * s
    k = max(0.0, p.fuse / max(0.1, p.fuse0))
    r = s * 0.42 * (1 + 0.1 * math.sin(t * (7 + 16 * (1 - k))))
    body = (52, 46, 64)
    if p.fuse < 0.7 and int(t * 14) % 2:
        body = (170, 50, 44)
    disc(cv, cx, cy + s * 0.04, r, body)
    if s >= 4:
        cv.set(cx - r * 0.45, cy - r * 0.35, shade(body, 1.9))
    spark = (255, 250, 200) if int(t * 20) % 2 else (255, 180, 60)
    cv.set(cx + r * 0.55, cy - r * 0.95, spark)


def draw_flame(cv, x, y, age, kind, s, ox, oy, t):
    k = max(0.0, 1 - age / FLAME_LIFE)
    px, py = ox + x * s, oy + y * s
    outer = mix((190, 50, 24), (255, 132, 36), k)
    mid = mix((240, 120, 40), (255, 206, 80), k)
    core = mix((255, 200, 120), (255, 252, 230), k)
    w = max(1, int(round(s * (0.4 + 0.6 * k))))
    w2 = max(1, w // 2 if s >= 4 else 1)
    a, a2 = (s - w) // 2, (s - w2) // 2
    horiz = kind in ("h", "left", "right", "c")
    vert = kind in ("v", "up", "down", "c")
    cut = max(1, s // 4)
    for on, (bx, by, bw, bh, ix, iy, iw, ih) in (
            (horiz, (px, py + a, s, w, px, py + a2, s, w2)),
            (vert, (px + a, py, w, s, px + a2, py, w2, s))):
        if not on:
            continue
        if kind == "left":
            bx, bw, ix, iw = bx + cut, bw - cut, ix + cut, iw - cut
        elif kind == "right":
            bw, iw = bw - cut, iw - cut
        elif kind == "up":
            by, bh, iy, ih = by + cut, bh - cut, iy + cut, ih - cut
        elif kind == "down":
            bh, ih = bh - cut, ih - cut
        cv.rect(bx, by, bw, bh, outer)
        cv.rect(ix, iy, iw, ih, mid)
    if kind == "c":
        cv.rect(px + a, py + a, w, w, mid)
        cv.rect(px + a2, py + a2, w2, w2, core)
    elif s >= 5 and k > 0.4:
        cv.set(px + s // 2, py + s // 2, core)


def draw_tinker(cv, tk, s, ox, oy, t):
    if not tk.alive:
        if tk.dead_t > 1.0:
            return
    elif tk.inv > 0 and int(t * 16) % 2:
        return
    cx, cy = ox + (tk.x + 0.5) * s, oy + (tk.y + 0.5) * s
    col = tk.colour
    r = s * 0.44
    if not tk.alive:
        k = tk.dead_t / 1.0
        col = mix((255, 255, 255), (90, 90, 110), k) if int(tk.dead_t * 12) % 2 else col
        r *= 1 - 0.7 * k
    bob = abs(math.sin(tk.walk * math.pi)) * s * 0.08 if tk.moving else 0.0
    cy -= bob
    hood, rr = shade(col, 0.72), r * r
    look = {"left": -1, "right": 1}.get(tk.face, 0)
    face_on = s >= 5 and tk.face != "up" and tk.alive
    for yy in range(int(cy - r) - 1, int(cy + r) + 2):
        for xx in range(int(cx - r) - 1, int(cx + r) + 2):
            ddx, ddy = xx + 0.5 - cx, yy + 0.5 - cy
            if ddx * ddx + ddy * ddy > rr:
                continue
            c = col
            if ddy < -r * 0.35:
                c = hood
            elif face_on and ddy < r * 0.25 and abs(ddx - look * r * 0.25) < r * 0.55:
                c = SKIN
            cv.set(xx, yy, c)
    if tk.alive:
        ey = cy - r * 0.05
        if face_on:
            for e in (-1, 1):
                if look == 0 or e == look or s >= 7:
                    cv.set(cx + look * r * 0.25 + e * r * 0.28, ey, (30, 24, 40))
        elif tk.face != "up":
            cv.set(cx + look * r * 0.4, ey, (255, 255, 255))
        if s >= 5 and tk.moving:
            ph = int(tk.walk * 2) % 2
            cv.set(cx - r * 0.4, cy + r + (0 if ph else -1), shade(col, 0.5))
            cv.set(cx + r * 0.3, cy + r + (-1 if ph else 0), shade(col, 0.5))
        if tk.ward:
            for i in range(10):
                a = t * 3 + i * math.tau / 10
                if i % 5:
                    cv.set(cx + math.cos(a) * (r + 1), cy + math.sin(a) * (r + 1), (255, 232, 140))
        if tk.curse:
            a = t * 6
            cv.set(cx + math.cos(a) * (r + 0.6), cy - r * 0.5 + math.sin(a) * 0.8, (210, 110, 255))


def draw_field(cv, g, s, ox, oy):
    y_ = YARDS[g.yard]
    fa, fb = y_["floor"]
    if g.shake > 0:
        ox += int(round(math.sin(g.t * 90) * min(1.0, g.shake * 6)))
    t = g.t
    for y in range(GH):
        for x in range(GW):
            px, py = ox + x * s, oy + y * s
            c = g.grid[y][x]
            if c == "#":
                draw_wall(cv, px, py, s, y_["wall"], x, y)
                continue
            draw_floor(cv, px, py, s, fa if (x + y) % 2 == 0 else fb, x, y)
            if c == "+":
                draw_crate(cv, px, py, s, y_["crate"])
            elif c == "*":
                draw_burning(cv, px, py, s, y_["crate"], g.burning.get((x, y), 0.0), t)
            elif c in ITEMS:
                draw_item(cv, px, py, s, c, t)
    for x, y, a in g.falling:                              # the shadow of a block about to land
        k = a / 0.45
        m = int(s * (0.5 - 0.5 * k))
        cv.rect(ox + x * s + m, oy + y * s + m, s - 2 * m, s - 2 * m, mix(fa, (10, 8, 12), 0.3 + 0.4 * k))
    for (x, y), (age, kind, _) in g.flames.items():
        draw_flame(cv, x, y, age, kind, s, ox, oy, t)
    for p in g.pots:
        draw_pot(cv, p, s, ox, oy, t)
    for tk in sorted(g.tinkers, key=lambda k: k.y):
        draw_tinker(cv, tk, s, ox, oy, t)
    for x, y, a in g.falling:
        k = a / 0.45
        draw_wall(cv, ox + x * s, oy + y * s - int((1 - k) * s * 2.5), s, y_["wall"], x, y)
    for d in g.debris:
        cv.set(ox + d[0] * s, oy + d[1] * s, d[5])
    item_letters(cv, g, s, ox, oy)


def clock_text(g):
    c = int(math.ceil(g.clock))
    return "%d:%02d" % (c // 60, c % 60)


def wins_pips(tk, target):
    return "●" * tk.wins + "○" * max(0, target - tk.wins) if target <= 6 else "%d/%d" % (tk.wins, target)


def draw_panel(cv, g, w, me):
    rows = cv.rows - 1
    for r in range(rows):
        cv.put(0, r, " " * w, HUD_FG, PANEL_BG)
    top, bottom = arcadekit.ACCENTS.get("FUSEYARD", ((255, 210, 120), (230, 90, 50)))
    cv.put(1, 0, "F U S E Y A R D", top, PANEL_BG)
    cv.put(1, 1, "%s, round %d" % (YARDS[g.yard]["name"], g.round), (160, 162, 190), PANEL_BG)
    if g.closing:
        txt, fg = "%s  WALLS CLOSE IN" % clock_text(g), (255, 120, 100) if int(g.t * 3) % 2 else (255, 200, 120)
    else:
        txt, fg = "%s   first to %d" % (clock_text(g), g.target), (230, 230, 240)
    cv.put(1, 2, txt[:w - 2], fg, PANEL_BG)
    r = 4
    per = 4 if rows >= 4 + 4 * len(g.tinkers) else 3
    for tk in g.tinkers:
        if r + 2 >= rows:
            break
        col = tk.colour if tk.alive else shade(tk.colour, 0.45)
        tag = tk.name + (" *" if tk.slot in me else "")
        pips = wins_pips(tk, g.target)
        cv.put(0, r, (" " + tag).ljust(w - len(pips) - 1) + pips + " ", (18, 14, 22), col)
        if not tk.alive:
            cv.put(1, r + 1, "out" + ("  - %d down" % tk.kills if tk.kills else ""), (150, 150, 170), PANEL_BG)
        else:
            cv.put(1, r + 1, "pots %d fire %d speed %d" % (tk.pots, tk.fire, tk.boots), (214, 214, 226), PANEL_BG)
            extra = []
            if tk.kick:
                extra.append("kick")
            if tk.ward:
                extra.append("ward")
            if tk.curse:
                extra.append(CURSE_TEXT[tk.curse])
            who = {"bot": "computer %s" % (tk.diff or ""), "remote": "LAN", "human": ""}.get(tk.kind, "")
            line = "  ".join(extra) if extra else who
            cv.put(1, r + 2, line[:w - 2], (210, 120, 255) if tk.curse else (150, 154, 184), PANEL_BG)
        r += per
    if r + 1 < rows:
        legend = ["P pot F fire S speed", "K kick W ward ? curse"]
        for i, l in enumerate(legend):
            if r + i < rows:
                cv.put(1, r + i, l[:w - 2], (110, 112, 140), PANEL_BG)


def draw_bar(cv, g, bar, me):
    r = cv.rows - 1
    cv.put(0, r, " " * cv.cols, HUD_FG, HUD_BG)
    x = 0
    for tk in g.tinkers:
        txt = " %s %d " % (tk.name[:6], tk.wins)
        cv.put(x, r, txt, (18, 14, 22), tk.colour if tk.alive else shade(tk.colour, 0.45))
        x += len(txt) + 1
    clock = " %s " % clock_text(g)
    if bar and x + len(bar) + len(clock) + 2 <= cv.cols:
        cv.put(x + 1, r, bar, (150, 154, 184), HUD_BG)
    cv.put(cv.cols - len(clock), r, clock, (255, 140, 110) if g.closing else (240, 240, 246), (30, 30, 50))


def banner(cv, lines, fg=(244, 244, 250), bg=(28, 24, 44), row=None):
    w = max(len(l) for l in lines) + 4
    x = max(0, (cv.cols - w) // 2)
    y = max(0, (cv.rows // 2 if row is None else row) - len(lines) // 2 - 1)
    cv.box(x, y, [l.center(w - 4) for l in lines], fg, bg)


def render(g, cols, rows, hud=True, me=(), bar=None, box=None, over_hint="Enter: again   Esc / Q: menu"):
    s, ox, oy, panel = layout(cols, rows, hud)
    y_ = YARDS[g.yard]
    cv = Canvas(cols, rows, y_["bg"])
    for y in range(cv.H):
        cv.px[y] = [mix(y_["bg"], shade(y_["bg"], 0.5), y / max(1, cv.H))] * cv.W
    draw_field(cv, g, s, ox, oy)
    if not hud:
        return cv
    if panel:
        draw_panel(cv, g, panel, me)
    draw_bar(cv, g, bar, me)
    fx = (ox + GW * s // 2)
    if g.state == "intro":
        lines = ["ROUND %d" % g.round, YARDS[g.yard]["name"]] if g.state_t > 0.6 else ["GO!"]
        cv_banner_at(cv, lines, fx, rows // 2)
    elif g.state == "roundend":
        if g.round_winner is not None:
            w = g.tinkers[g.round_winner]
            lines = ["%s WINS ROUND %d" % (w.name, g.round)]
        else:
            lines = ["NOBODY LEFT - A DRAW"]
        lines += ["", "  ".join("%s %d" % (tk.name, tk.wins) for tk in g.tinkers)]
        cv_banner_at(cv, lines, fx, rows // 2)
    elif g.state == "over" and g.champ is not None:
        w = g.tinkers[g.champ]
        lines = ["%s TAKES THE YARD" % w.name, ""]
        for tk in sorted(g.tinkers, key=lambda k: (-k.wins, -k.kills)):
            lines.append("%-8s %d %s   %d down" % (tk.name, tk.wins, "win " if tk.wins == 1 else "wins", tk.kills))
        lines += ["", over_hint]
        cv_banner_at(cv, lines, fx, rows // 2, bg=shade(w.colour, 0.3))
    if box:
        overlay(cv, box)
    return cv


def cv_banner_at(cv, lines, cx, row, fg=(244, 244, 250), bg=(28, 24, 44)):
    w = max(len(l) for l in lines) + 4
    x = max(0, min(cv.cols - w, cx - w // 2))
    y = max(0, row - len(lines) // 2 - 1)
    cv.box(x, y, [l.center(w - 4) for l in lines], fg, bg)


# =============================================================================================
# Settings, title, menus
# =============================================================================================
CFG_DEFAULT = dict(local=1, total=4, diff="normal", yard=-1, target=3, name="PLAYER")


def load_cfg():
    cfg = dict(CFG_DEFAULT)
    try:
        with open(arcadekit.SETTINGS_PATH) as f:
            saved = json.load(f).get(GAME, {})
        if isinstance(saved, dict):
            cfg.update({k: v for k, v in saved.items() if k in cfg})
    except (OSError, ValueError, AttributeError):
        pass
    cfg["local"] = 2 if cfg["local"] == 2 else 1
    cfg["total"] = cfg["total"] if cfg["total"] in (2, 3, 4) else 4
    cfg["diff"] = cfg["diff"] if cfg["diff"] in DIFFS else "normal"
    cfg["yard"] = cfg["yard"] if isinstance(cfg["yard"], int) and -1 <= cfg["yard"] < len(YARDS) else -1
    cfg["target"] = cfg["target"] if cfg["target"] in TARGETS else 3
    cfg["name"] = clean_name(cfg["name"])
    return cfg


def save_cfg(cfg):
    try:
        try:
            with open(arcadekit.SETTINGS_PATH) as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
        except (OSError, ValueError):
            data = {}
        data[GAME] = dict(cfg)
        tmp = arcadekit.SETTINGS_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, arcadekit.SETTINGS_PATH)
    except OSError:
        pass


def yard_label(i):
    return "changing" if i < 0 else YARDS[i]["name"]


class TitleDemo:
    def __init__(self):
        self.k = 0
        self.new()

    def new(self):
        diffs = ("hard", "normal", "normal", "easy")
        self.g = Match([(BOT_NAMES[i], "bot", diffs[(i + self.k) % 4]) for i in range(4)], yard=self.k % len(YARDS),
                       target=99, seed=self.k, demo=True)
        self.k += 1

    def scene(self, cols, rows, dt):
        self.g.advance(min(dt, 0.1))
        self.g.events.clear()
        if self.g.state == "roundend" and self.g.state_t < 0.3 or self.g.t > 150:
            self.new()
        return render(self.g, cols, rows, hud=False)


MENU = ["play", "host", "join", "auto", "local", "total", "diff", "yard", "target", "name"]


def menu_items(cfg):
    humans = cfg["local"]
    bots = max(0, max(2, cfg["total"]) - humans)
    play = "%d at this keyboard%s" % (humans, " + %d computer" % bots if bots else "")
    return ["Play             %s" % play,
            "Host a LAN game  others join you",
            "Join a LAN game  someone else hosts",
            "%-16s computer against computer" % AUTO_LABEL,
            "Players here     < %d >" % humans,
            "Tinkers          < %d >   (the computer fills up)" % max(cfg["total"], humans),
            "Computer         < %s >" % cfg["diff"],
            "Yard             < %s >" % yard_label(cfg["yard"]),
            "Wins needed      < %d >" % cfg["target"],
            "Your name        < %s >%s" % (cfg["name"], "")]


def change(cfg, key, step):
    if key == "local":
        cfg["local"] = 2 if cfg["local"] == 1 else 1
        cfg["total"] = max(cfg["total"], cfg["local"])
    elif key == "total":
        cfg["total"] = (cfg["total"] - 2 + step) % 3 + 2
        if cfg["total"] < cfg["local"]:
            cfg["total"] = cfg["local"]
    elif key == "diff":
        cfg["diff"] = DIFFS[(DIFFS.index(cfg["diff"]) + step) % len(DIFFS)]
    elif key == "yard":
        cfg["yard"] = (cfg["yard"] + 1 + step) % (len(YARDS) + 1) - 1
    elif key == "target":
        cfg["target"] = TARGETS[(TARGETS.index(cfg["target"]) + step) % len(TARGETS)]


def render_menu(demo, cols, rows, sel, dt, help_, cfg, note=None, kitty=True):
    cv = demo.scene(cols, rows, dt)
    rec = load_scores().get(GAME, {})
    best = ("matches won vs computer: " + ", ".join("%s %d" % (d, rec[d]) for d in DIFFS if d in rec)) \
        if rec and rows >= 26 else None
    extra = [note] if note else []
    keys = ("Up/Down choose   Left/Right change   type your name   Enter start   ? help   Esc back"
            if MENU[sel] == "name" else
            "Up/Down choose   Left/Right change   Enter start   M %s   ? help   Esc back" % SND.label().lower())
    title_screen(cv, "FUSEYARD", "fuse-pot duels for 1 to 4, at one keyboard or over the LAN", menu_items(cfg), sel,
                 best, extra=extra, keys=keys, help_lines=help_lines(kitty), show_help=help_)
    return cv


def too_small(term):
    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (%dx%d)." % (MIN_COLS, MIN_ROWS))


def fits(term):
    cols, rows = term.size()
    return cols >= MIN_COLS and rows >= MIN_ROWS


def dimmed(cv, k=0.6):
    for y in range(cv.H):
        cv.px[y] = [mix(c, TITLE_DIM, k) for c in cv.px[y]]
    return cv


def play_sounds(names):
    for n in dict.fromkeys(names):
        if n in SND.bank:
            SND.play(n)


def term_events(term):
    return term.events(0) if hasattr(term, "events") else [(k, "press") for k in term.keys(0)]


# =============================================================================================
# Playing at one keyboard, auto mode
# =============================================================================================
def local_players(cfg):
    humans = cfg["local"]
    players = [(cfg["name"] if humans == 1 else ("PLAYER 1" if cfg["name"] == "PLAYER" else cfg["name"]),
                "human", None)]
    if humans == 2:
        players.append(("PLAYER 2", "human", None))
    for i in range(humans, max(2, cfg["total"], humans)):
        players.append((BOT_NAMES[i], "bot", cfg["diff"]))
    return players


def play_local(term, cfg, seed=None):
    kitty = getattr(term, "kitty", False)
    players = local_players(cfg)
    humans = cfg["local"]
    slots = list(range(humans))
    ctl = Controls(kitty, humans)
    while True:
        g = Match(players, yard=cfg["yard"], target=cfg["target"], seed=seed)
        recorded = again = False
        last = time.time()
        while True:
            now = time.time()
            dt = min(0.1, now - last)
            last = now
            acts = []
            for name, kind in term_events(term):
                if kind != "press":
                    acts += ctl.feed(name, kind)
                    continue
                if g.state == "over":
                    if name in ("q", "esc"):
                        return
                    if name in ("enter", " ") and g.state_t < -0.8:
                        again = True
                    continue
                a = shared_key(name, g.paused, pause_keys=("esc", "p"))
                if a == "pause":
                    g.paused = True
                    ctl.clear()
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
                    acts += ctl.feed(name, kind)
            if again:
                break
            if not g.paused:
                apply_actions(g, acts, slots)
                for p, i in enumerate(slots):
                    tk = g.tinkers[i]
                    tk.inp = ctl.direction(p) if tk.alive and g.state == "play" else None
            g.advance(dt)
            play_sounds(g.take_events())
            if g.state == "over" and not recorded:
                recorded = True
                if g.champ is not None and g.champ < humans and humans < len(g.tinkers):
                    d = cfg["diff"]
                    submit(GAME, d, load_scores().get(GAME, {}).get(d, 0) + 1)
            if not fits(term):
                too_small(term)
                time.sleep(0.2)
                continue
            cols, rows = term.size()
            box = (help_lines(kitty) if g.help else PAUSE_LINES + ["", SND.label()]) if g.paused else None
            term.write(render(g, cols, rows, me=slots, bar="Esc pause   ? help", box=box).emit())
            time.sleep(max(0, 1 / 60 - (time.time() - now)))


def run_auto(term, cfg):
    auto = AutoMode()
    k = 0
    while True:
        diffs = ("hard", "normal", "normal", "easy")
        g = Match([(BOT_NAMES[i], "bot", diffs[(i + k) % 4]) for i in range(4)], yard=cfg["yard"],
                  target=cfg["target"])
        k += 1
        last = time.time()
        over_at = None
        while True:
            now = time.time()
            dt = min(0.1, now - last)
            last = now
            for name in term.keys(0):
                a = auto.key(name)
                if a == "stop":
                    return
                if a == "sound" and SND.toggle():
                    SND.play("sound_on")
            sim = auto.scale(dt)
            if sim:
                g.advance(sim)
            play_sounds(g.take_events())
            if g.state == "over" and over_at is None:
                over_at = now
            if over_at is not None:
                if auto.paused:
                    over_at += dt
                elif now - over_at > 4:
                    break
            if not fits(term):
                too_small(term)
                time.sleep(0.2)
                continue
            cols, rows = term.size()
            cv = render(g, cols, rows, over_hint="the next match starts in a moment")
            auto.banner(cv, extra="first to %d" % g.target)
            term.write(cv.emit())
            time.sleep(max(0, 1 / 60 - (time.time() - now)))


# =============================================================================================
# The LAN screens
# =============================================================================================
def slot_lines(rows, you=(), here_label="here"):
    out = []
    for i, (name, kind) in enumerate(rows):
        what = {"here": here_label, "lan": "LAN", "bot": "computer", "gone": "left"}.get(kind, kind)
        out.append(" %d  %-9s %-9s%s" % (i + 1, name, what, "  <- you" if i in you else ""))
    for i in range(len(rows), 4):
        out.append(" %d  %-9s" % (i + 1, "- free -"))
    return out


def lobby_screen(term, demo, dt, lines, keys):
    cols, rows = term.size()
    cv = dimmed(demo.scene(cols, rows, dt))
    overlay(cv, lines)
    footer(cv, keys)
    term.write(cv.emit())


def host_session(term, cfg, demo, port=PORT, beacon=True):
    """Host a LAN game. Returns a note for the menu (or None)."""
    try:
        srv = LanServer(cfg, port, beacon)
    except OSError as e:
        return "could not open a LAN game: %s" % (e.strerror or e)
    try:
        while True:
            if host_lobby(term, srv, demo) != "start":
                return None
            if host_match(term, srv) == "quit":
                return None
            srv.to_lobby()
    finally:
        srv.close()


def host_lobby(term, srv, demo):
    last = time.time()
    help_ = False
    while True:
        now = time.time()
        dt = min(0.1, now - last)
        last = now
        srv.poll(now)
        play_sounds(srv.sounds)
        srv.sounds = []
        for k in term.keys(0):
            if help_:
                help_ = False
                continue
            if k in ("esc", "q"):
                return "quit"
            if k == "?":
                help_ = True
            elif k == "m":
                if SND.toggle():
                    SND.play("sound_on")
            elif k in ("enter", " "):
                SND.play("start")
                srv.start()
                return "start"
        if not fits(term):
            too_small(term)
            time.sleep(0.2)
            continue
        lines = ["HOSTING A LAN GAME", "",
                 "the others choose  Join a LAN game  - this game shows",
                 "up there by itself, or they type:  %s  (port %d)" % (srv.ip, srv.port), ""]
        lines += slot_lines(srv.lobby_rows(), srv.here(), "here")
        lines += ["", "%s   first to %d   computer %s" % (yard_label(srv.cfg["yard"]), srv.cfg["target"],
                                                          srv.cfg["diff"])]
        lines += [""] + (list(srv.notes) or ["waiting for players ..."])
        if help_:
            lines = help_lines(getattr(term, "kitty", False))
        lobby_screen(term, demo, dt, lines, "Enter start (free places: computer)   ? help   Esc cancel")
        time.sleep(max(0, 1 / 30 - (time.time() - now)))


def host_match(term, srv):
    kitty = getattr(term, "kitty", False)
    g = srv.g
    slots = srv.here()
    ctl = Controls(kitty, len(slots))
    menu = help_ = False
    last = time.time()
    while True:
        now = time.time()
        dt = min(0.1, now - last)
        last = now
        srv.poll(now)
        play_sounds(srv.sounds)
        srv.sounds = []
        lan = srv.remote_count() > 0
        acts = []
        for name, kind in term_events(term):
            if kind != "press":
                acts += ctl.feed(name, kind)
                continue
            if g.state == "over":
                if name in ("q", "esc"):
                    return "quit"
                if name in ("enter", " ") and g.state_t < -0.8:
                    return "lobby"
                continue
            if menu or g.paused:
                if help_:
                    help_ = False
                elif name == "q":
                    return "quit"
                elif name in ("esc", "p", "enter", " "):
                    menu = g.paused = False
                elif name == "?":
                    help_ = True
                elif name == "m":
                    if SND.toggle():
                        SND.play("sound_on")
                elif name == "v":
                    arcadekit.cycle_view()
                continue
            if name in ("esc", "p"):
                ctl.clear()
                if lan:
                    menu = True                      # the others play on: the game does not stop
                else:
                    g.paused = True
                SND.play("pause")
            elif name == "?":
                menu, help_ = True, True
                g.paused = not lan
            elif name == "v":
                arcadekit.cycle_view()
            else:
                acts += ctl.feed(name, kind)
        if not g.paused:
            apply_actions(g, acts, slots)
            for p, i in enumerate(slots):
                tk = g.tinkers[i]
                tk.inp = ctl.direction(p) if tk.alive and g.state == "play" and not menu else None
        g.advance(dt)
        ev = g.take_events()
        play_sounds(ev)
        srv.send_state(now, ev)
        if not fits(term):
            too_small(term)
            time.sleep(0.2)
            continue
        cols, rows = term.size()
        box = None
        if help_:
            box = help_lines(kitty)
        elif menu or g.paused:
            box = ["M E N U" if menu else "P A U S E D", "",
                   "Esc / P / Enter   back to the game", "Q                 end the game for everyone",
                   "V                 view   M sound", "", "(the others play on)" if menu else SND.label()]
        bar = "LAN %s:%d   %s" % (srv.ip, srv.port, srv.notes[-1] if srv.notes else "Esc menu")
        term.write(render(g, cols, rows, me=slots, bar=bar, box=box,
                          over_hint="Enter: back to the lobby   Esc / Q: end").emit())
        time.sleep(max(0, 1 / 60 - (time.time() - now)))


def join_session(term, cfg, demo, finder=None):
    """Find (or type) a host and play there. Returns a note for the menu (or None)."""
    finder = finder or Finder()
    sel, addr, note = 0, "", None
    last = time.time()
    try:
        while True:
            now = time.time()
            dt = min(0.1, now - last)
            last = now
            hosts = finder.poll(now)
            n = len(hosts) + 1
            sel = min(sel, n - 1)
            target = None
            for k in term.keys(0):
                if k in ("esc",):
                    return None
                if k == "q" and not addr:
                    return None
                if k == "up":
                    sel = (sel - 1) % n
                elif k in ("down", "tab"):
                    sel = (sel + 1) % n
                elif k == "backspace":
                    addr = addr[:-1]
                    sel = n - 1
                elif len(k) == 1 and (k.isalnum() or k in ".:-"):
                    addr = (addr + k)[:40]
                    sel = n - 1
                elif k == "enter":
                    if sel < len(hosts):
                        target = hosts[sel][0]
                    elif addr:
                        h, _, p = addr.partition(":")
                        target = (h, int(p) if p.isdigit() else PORT)
            if target:
                frame = ["JOIN A LAN GAME", "", "connecting to %s:%d ..." % target]
                if fits(term):
                    lobby_screen(term, demo, 0.0, frame, "please wait")
                try:
                    cl = LanClient(target[0], target[1], cfg["name"], cfg["local"])
                except (OSError, ValueError) as e:
                    note = "no game at %s:%d (%s)" % (target[0], target[1], getattr(e, "strerror", None) or e)
                    continue
                why = client_loop(term, cl, cfg, demo)
                cl.close()
                return why
            if not fits(term):
                too_small(term)
                time.sleep(0.2)
                continue
            lines = ["JOIN A LAN GAME", "", "games in your network (LAN / WLAN):"]
            for i, ((ip, port), h) in enumerate(hosts):
                state = "%d/4 players" % h["n"] if h["open"] else "playing / full"
                lines.append("%s %-9s %-15s %s" % (">" if sel == i else " ", h["name"], state, ip))
            if not hosts:
                lines.append("  (looking ... )" if finder.sock else "  (cannot listen for games here - type one)")
            lines += ["", "%s or type the host's address:  %s%s" % (">" if sel == len(hosts) else " ", addr,
                                                                     "_" if int(now * 2) % 2 else " ")]
            if note:
                lines += ["", note]
            lobby_screen(term, demo, dt, lines, "Up/Down choose   type an address   Enter join   Esc back")
            time.sleep(max(0, 1 / 30 - (time.time() - now)))
    finally:
        finder.close()


def client_loop(term, cl, cfg, demo):
    kitty = getattr(term, "kitty", False)
    ctl = Controls(kitty, cfg["local"])
    menu = help_ = False
    sent, sent_at = None, 0.0
    last = time.time()
    while True:
        now = time.time()
        dt = min(0.1, now - last)
        last = now
        play_sounds(cl.poll())
        if cl.state == "closed":
            return cl.why
        game = cl.state == "game" and cl.view is not None
        for name, kind in term_events(term):
            if kind == "press" and (menu or not game):
                if help_:
                    help_ = False
                elif name == "q" or (name == "esc" and not game):
                    return "you left the game"
                elif name in ("esc", "p", "enter", " "):
                    menu = False
                elif name == "?":
                    help_ = True
                elif name == "m":
                    if SND.toggle():
                        SND.play("sound_on")
                elif name == "v":
                    arcadekit.cycle_view()
                continue
            if kind == "press" and name in ("esc", "p", "?"):
                menu = True
                help_ = name == "?"
                ctl.clear()
                continue
            if kind == "press" and name == "v":
                arcadekit.cycle_view()
                continue
            for a in ctl.feed(name, kind):
                if a[0] == "drop":
                    cl.send({"t": "dr", "p": a[1]})
                else:
                    cl.send({"t": "nu", "p": a[1], "d": a[2], "f": 1 if a[3] else 0})
        held = [None if menu else ctl.direction(p) for p in range(cfg["local"])]
        if held != sent or now - sent_at > 0.25:
            cl.send({"t": "in", "d": held})
            sent, sent_at = held, now
        if not fits(term):
            too_small(term)
            time.sleep(0.2)
            continue
        cols, rows = term.size()
        if game:
            box = None
            if help_:
                box = help_lines(kitty)
            elif menu:
                box = ["M E N U", "", "Esc / P / Enter   back to the game", "Q                 leave the game",
                       "V                 view   M sound", "", "(the game goes on meanwhile)"]
            term.write(render(cl.view, cols, rows, me=cl.you, bar="LAN %s   Esc menu" % cl.addr, box=box,
                              over_hint="the host starts the next one").emit())
        else:
            lb = cl.lobby
            lines = ["JOINED %s" % cl.addr, ""]
            if lb:
                rows_ = [r for r in lb.get("slots", []) if isinstance(r, list) and len(r) == 2][:4]
                lines += slot_lines([(clean_name(a), str(b)) for a, b in rows_], cl.you, "host")
                lines += ["", "%s   first to %s   computer %s" % (str(lb.get("yard", ""))[:12], lb.get("target"),
                                                                  str(lb.get("diff", ""))[:8])]
            lines += ["", "waiting for the host to start ..."]
            if help_:
                lines = help_lines(kitty)
            lobby_screen(term, demo, dt, lines, "? help   Esc leave")
        time.sleep(max(0, 1 / 60 - (time.time() - now)))


# =============================================================================================
# main
# =============================================================================================
def main():
    cfg = load_cfg()
    with KeyTerminal() as term:
        demo = TitleDemo()
        sel, help_, note = 0, False, None
        last = time.time()
        while True:
            now = time.time()
            if not fits(term):
                too_small(term)
                if any(k in ("q", "esc") for k in term.keys(0.3)):
                    return
                last = time.time()
                continue
            cols, rows = term.size()
            term.write(render_menu(demo, cols, rows, sel, min(0.1, now - last), help_, cfg, note, term.kitty).emit())
            last = now
            go = None
            for k in term.keys(max(0.0, 1 / 30 - (time.time() - now))):
                if help_:
                    help_ = False
                    continue
                key = MENU[sel]
                if key == "name" and (len(k) == 1 and (k.isalnum() or k in " -_") or k == "backspace"):
                    name = cfg["name"] if cfg["name"] != "PLAYER" or k == "backspace" else ""
                    name = name[:-1] if k == "backspace" else (name + k.upper())[:8]
                    cfg["name"] = name if name.strip() else "PLAYER"
                    save_cfg(cfg)
                    continue
                if k == "?":
                    help_ = True
                elif k in ("q", "esc"):
                    return
                elif k in ("up", "w"):
                    sel = (sel - 1) % len(MENU)
                    SND.play("menu")
                elif k in ("down", "s"):
                    sel = (sel + 1) % len(MENU)
                    SND.play("menu")
                elif k in ("left", "a", "right", "d"):
                    change(cfg, key, 1 if k in ("right", "d") else -1)
                    save_cfg(cfg)
                    SND.play("menu")
                elif k == "m":
                    if SND.toggle():
                        SND.play("sound_on")
                elif k in ("enter", " "):
                    if key in ("play", "host", "join", "auto"):
                        SND.play("start")
                        go = key
                    else:
                        change(cfg, key, 1)
                        save_cfg(cfg)
            if go:
                note = None
                if go == "play":
                    play_local(term, cfg)
                elif go == "auto":
                    run_auto(term, cfg)
                elif go == "host":
                    note = host_session(term, cfg, demo)
                else:
                    note = join_session(term, cfg, demo)
                last = time.time()


# =============================================================================================
# Self-test:  python3 fuseyard.py --selftest
# =============================================================================================
class FakeTerm:
    def __init__(self, script, size=(100, 32), kitty=False):
        self.script = sorted(script, key=lambda e: e[0])
        self.t0 = time.time()
        self.cols_rows = size
        self.frames = 0
        self.kitty = kitty

    def events(self, timeout=0.0):
        now = time.time() - self.t0
        out = [e for e in self.script if e[0] <= now]
        self.script = [e for e in self.script if e[0] > now]
        return [(e[1], e[2] if len(e) > 2 else "press") for e in out]

    def keys(self, timeout=0.0):
        return [k for k, kind in self.events(timeout) if kind == "press"]

    def size(self):
        return self.cols_rows

    def write(self, s):
        self.frames += 1


def screenshot(cols=100, rows=32):
    quiet, SND.enabled = SND.enabled, False
    try:
        best = None
        for seed in range(3, 12):
            g = Match([(BOT_NAMES[i], "bot", ("hard", "normal", "hard", "normal")[i]) for i in range(4)], yard=0,
                      target=3, seed=seed)
            g.tinkers[0].wins, g.tinkers[2].wins = 1, 1
            g.round = 3
            for _ in range(int(70 * 60)):
                g.update(1 / 60)
                alive = sum(tk.alive for tk in g.tinkers)
                items = sum(1 for row in g.grid for c in row if c in ITEMS)
                if g.state == "play" and g.t > 14 and alive >= 3 and len(g.flames) >= 5 and len(g.pots) >= 2 \
                        and items >= 2:
                    best = g
                    break
                if g.state != "play" and g.t > 3:
                    break
            if best:
                break
        g = best or g
        return render(g, cols, rows, me=(0,), bar="Esc pause   ? help")
    finally:
        SND.enabled = quiet


def connected(rows):
    open_ = [(x, y) for y in range(GH) for x in range(GW) if rows[y][x] != "#"]
    seen, q = {open_[0]}, [open_[0]]
    while q:
        x, y = q.pop()
        for dx, dy in DIRS.values():
            n = (x + dx, y + dy)
            if n not in seen and rows[n[1]][n[0]] != "#":
                seen.add(n)
                q.append(n)
    return len(seen) == len(open_)


def bare(players=2, seed=1, yard=0):
    """A match on an empty yard (no crates), already playing."""
    g = Match([("A%d" % i, "human", None) for i in range(players)], yard=yard, target=3, seed=seed)
    for y in range(GH):
        for x in range(GW):
            if g.grid[y][x] != "#":
                g.grid[y][x] = "."
    g.hidden = {}
    g.state = "play"
    return g


def run(g, seconds):
    for _ in range(int(seconds * 60)):
        g.update(1 / 60)


def selftest():
    import tempfile
    t0 = time.time()
    tmp = tempfile.mkdtemp()
    arcadekit.SCORES_PATH = os.path.join(tmp, "scores.json")
    arcadekit.SETTINGS_PATH = os.path.join(tmp, "settings.json")
    SND.enabled = False
    # the yards: closed ring, every open tile reachable, the spawns and their neighbours open
    for i in range(len(YARDS)):
        rows = yard_rows(i)
        assert len(rows) == GH and all(len(r) == GW for r in rows), YARDS[i]["name"]
        assert all(rows[0][x] == rows[-1][x] == "#" for x in range(GW))
        assert all(r[0] == r[-1] == "#" for r in rows)
        assert connected(rows), "%s has a closed-off part" % YARDS[i]["name"]
        for sx, sy in SPAWNS:
            assert rows[sy][sx] != "#"
            assert sum(rows[sy + dy][sx + dx] != "#" for dx, dy in DIRS.values()) >= 2, YARDS[i]["name"]
        g = Match([("A", "human", None), ("B", "human", None)], yard=i, seed=i)
        for sx, sy in SPAWNS:
            assert g.grid[sy][sx] == "." and g.grid[sy][sx + (1 if sx == 1 else -1)] == "."
        assert sum(c == "+" for row in g.grid for c in row) >= 40
        assert len(g.hidden) == min(len(ITEM_POOL), sum(c == "+" for row in g.grid for c in row))
    assert len(spiral()) == (GW - 2) * (GH - 2) and len(set(spiral())) == len(spiral())
    # walking: speed, walls, corner help, a tap walks exactly one tile
    g = bare()
    tk = g.tinkers[0]
    tk.inp = "right"
    run(g, 1.0)
    assert abs(tk.x - (1 + BASE_SPEED)) < 0.05 and tk.y == 1.0, (tk.x, tk.y)
    tk.x, tk.y, tk.inp = 1.0, 1.0, "up"
    run(g, 0.5)
    assert (tk.x, tk.y) == (1.0, 1.0), "walked into the wall"
    tk.x, tk.y, tk.inp = 2.0, 1.0, "down"             # a pillar below (2, 2): no way down here
    run(g, 0.3)
    assert tk.tile == (2, 1)
    tk.x, tk.y, tk.inp = 2.7, 1.0, "down"             # close to the lane at x = 3: corner help lines up
    run(g, 0.6)
    assert tk.x == 3.0 and tk.y > 2.0, (tk.x, tk.y)
    tk.inp = None
    tk.x, tk.y = 1.0, 3.0
    g.nudge(tk, "down")
    run(g, 1.0)
    assert (tk.x, tk.y) == (1.0, 4.0), (tk.x, tk.y)
    tk.y = 4.4
    g.nudge(tk, "down", finish=True)
    run(g, 1.0)
    assert (tk.x, tk.y) == (1.0, 5.0), (tk.x, tk.y)
    # pots: the limit, the cross that stops at walls, burning crates leave what they hid, chains
    g = bare()
    tk = g.tinkers[0]
    tk.x, tk.y = 3.0, 3.0
    assert g.try_drop(tk) and not g.try_drop(tk)
    tk.pots = 2
    tk.x = 4.0
    assert g.try_drop(tk)
    tk.x = 4.0
    tk.inp = "left"
    run(g, 0.4)
    assert tk.x == 4.0, "walked through a pot"
    b = {(x, y) for x, y, _ in g.blast(3, 3, 2)}
    assert b == {(3, 3), (3, 1), (3, 2), (3, 4), (3, 5), (1, 3), (2, 3), (4, 3)}, sorted(b)  # stops at the pot at 4
    g = bare()
    g.grid[3][5] = "+"
    g.hidden = {(5, 3): "F"}
    tk = g.tinkers[0]
    tk.x, tk.y, tk.fire = 3.0, 3.0, 4
    g.try_drop(tk)
    g.pots.append(Pot(3, 7, 0, 2, 9.0))
    tk.x, tk.y = 1.0, 1.0
    g.tinkers[1].x, g.tinkers[1].y = 13.0, 11.0
    run(g, FUSE + 0.1)
    assert g.grid[3][5] == "*" and (3, 6) in g.flames and (3, 7) in g.flames and (6, 3) not in g.flames
    run(g, 1.0)
    assert g.grid[3][5] == "F" and not g.pots, "the chained pot did not go off or the crate hid nothing"
    tk.x, tk.y = 5.0, 3.0
    g.update(1 / 60)
    assert tk.fire == 5 and g.grid[3][5] == "."
    # kick, ward, curse spread, death drops what one carried
    g = bare()
    a, b2 = g.tinkers
    a.x, a.y, a.kick = 1.0, 3.0, True
    g.pots.append(Pot(2, 3, 1, 1, 9.0))
    a.inp = "right"
    run(g, 0.2)
    a.inp = None
    run(g, 2.0)
    assert g.pots[0].tile == (13, 3) and g.pots[0].slide is None, g.pots[0].tile
    g = bare()
    a, b2 = g.tinkers
    a.x, a.y, a.ward = 5.0, 5.0, 1
    g.flames[(5, 5)] = [0.0, "c", 1]
    g.update(1 / 60)
    assert a.alive and a.ward == 0 and a.inv > 0
    run(g, 2.0)
    g.flames[(5, 5)] = [0.0, "c", 1]
    a.got = ["F", "S", "P"]
    g.update(1 / 60)
    assert not a.alive and b2.kills == 1
    assert sum(1 for row in g.grid for c in row if c in "FSP") == 3
    g = bare()
    a, b2 = g.tinkers
    a.x, a.y = 5.0, 5.0
    g.grid[5][5] = "C"
    g.update(1 / 60)
    assert a.curse in CURSES
    b2.x, b2.y = 5.5, 5.0
    g.update(1 / 60)
    assert b2.curse == a.curse
    # the round: last one standing wins, wins add up to the match, the walls close in and crush
    g = bare()
    g.tinkers[1].alive = False
    run(g, 1.0)
    assert g.state == "roundend" and g.round_winner == 0 and g.tinkers[0].wins == 1
    run(g, 3.5)
    assert g.state == "intro" and g.round == 2 and all(tk.alive for tk in g.tinkers)
    g = bare()
    g.clock = CLOSE_TIME + 0.05
    a, b2 = g.tinkers
    a.x, a.y, b2.x, b2.y = 1.0, 1.0, 7.0, 6.0
    run(g, 2.0)
    assert g.closing and not a.alive and g.grid[1][1] == "#"
    run(g, 1.0)
    assert g.state == "roundend" and g.round_winner == 1
    g = bare()                                          # nobody gives way: the walls fill the yard, a draw
    g.clock = CLOSE_TIME + 0.05
    g.tinkers[0].x, g.tinkers[0].y, g.tinkers[1].x, g.tinkers[1].y = 7.0, 6.0, 7.0, 6.0
    while g.state == "play" and g.t < CLOSE_TIME + 5:
        g.update(1 / 60)
    assert g.state == "roundend" and g.round_winner is None and all(row.count("#") == GW for row in g.grid[1:-1])
    # the computer: four of them finish a whole match; hard beats easy more often than not
    g = Match([(BOT_NAMES[i], "bot", DIFFS[i % 3]) for i in range(4)], target=2, seed=5)
    steps = 0
    while g.state != "over" and steps < 60 * 900:
        g.update(1 / 60)
        steps += 1
    assert g.state == "over", "four bots did not finish a match"
    hard = 0
    rounds = 0
    for seed in range(8):
        g = Match([("H", "bot", "hard"), ("E", "bot", "easy")], target=1, seed=100 + seed, yard=seed % 4)
        while g.state != "over" and g.t < 200:
            g.update(1 / 60)
        rounds += g.round
        hard += g.champ == 0
    assert hard >= 5, "hard won only %d of 8 against easy" % hard
    # a bot never drops a pot it cannot run from (normal and hard check every one)
    g = bare()
    g.make_bot(g.tinkers[0], "hard")
    g.tinkers[0].x, g.tinkers[0].y = 1.0, 1.0
    g.grid[1][2], g.grid[2][1] = "+", "+"                 # boxed in: a pot here would be the end
    run(g, 3.0)
    assert not g.pots and g.tinkers[0].alive
    # the picture sent over the network draws exactly the same
    g = Match([(BOT_NAMES[i], "bot", "hard") for i in range(4)], seed=9)
    run(g, 20)
    g.debris = []
    v = Match.restore(json.loads(json.dumps(g.snapshot())))
    assert v is not None
    v.debris = []
    a_, b_ = render(g, 100, 32), render(v, 100, 32)
    off = max(abs(p - q) for ra, rb in zip(a_.px, b_.px) for ca, cb in zip(ra, rb) for p, q in zip(ca, cb))
    assert off <= 3 and a_.text == b_.text, "the snapshot draws differently (%d)" % off   # 3 decimals: a shade off
    assert Match.restore({"grid": "x"}) is None and Match.restore({}) is None
    bad = g.snapshot()
    bad["grid"] = "!" * (GW * GH)
    assert Match.restore(bad) is None
    # the LAN, for real over this machine: join, lobby, start, keys travel, pictures arrive, a leaver is replaced
    cfg = dict(CFG_DEFAULT, name="HOSTY", total=4, target=2)
    srv = LanServer(cfg, port=0, beacon=False)
    cl = LanClient("127.0.0.1", srv.port, "visitor", 2)
    end = time.time() + 3
    while time.time() < end and cl.state != "lobby":
        srv.poll(time.time())
        cl.poll()
        time.sleep(0.01)
    assert cl.state == "lobby" and cl.you == [1, 2], (cl.state, cl.you)
    assert [s["name"] for s in srv.slots] == ["HOSTY", "VISITOR", "VISITO 2"]
    cl2 = LanClient("127.0.0.1", srv.port, "late", 2)
    cl3 = LanClient("127.0.0.1", srv.port, "full", 1)
    end = time.time() + 3
    while time.time() < end and (cl2.state == "wait" or cl3.state == "wait"):
        srv.poll(time.time())
        cl2.poll()
        cl3.poll()
        time.sleep(0.01)
    assert len(srv.slots) == 4 and cl2.you == [3] and cl3.state == "closed" and "full" in cl3.why
    cl3.close()
    g = srv.start(seed=3)
    assert [tk.kind for tk in g.tinkers] == ["human", "remote", "remote", "remote"]
    g.state = "play"
    for y in range(GH):
        for x in range(GW):
            if g.grid[y][x] == "+":
                g.grid[y][x] = "."
    end = time.time() + 4
    moved = False
    while time.time() < end:
        now = time.time()
        srv.poll(now)
        cl.poll()
        cl2.poll()
        cl.send({"t": "in", "d": ["up", None]})
        g.update(1 / 60)
        srv.send_state(now, g.take_events())
        if cl.view and cl.view.tinkers[1].y < 11.0 - 1.5 and g.tinkers[1].kind == "remote":
            moved = True
            break
        time.sleep(1 / 120)
    assert moved, "keys from the LAN did not move the tinker (or the picture did not come back)"
    cl.send({"t": "dr", "p": 1})
    cl.send({"t": "nu", "p": 1, "d": "up", "f": 0})
    cl.send({"t": "nu", "p": 7, "d": "sideways"})       # nonsense is ignored
    cl.link.send_raw(b"not json\n")
    end = time.time() + 2
    while time.time() < end and not g.pots:
        srv.poll(time.time())
        g.update(1 / 60)
        time.sleep(0.01)
    assert any(p.owner == 2 for p in g.pots), "the second player on the visiting keyboard could not drop"
    cl2.close()
    end = time.time() + 2
    while time.time() < end and g.tinkers[3].kind != "bot":
        srv.poll(time.time())
        time.sleep(0.01)
    assert g.tinkers[3].kind == "bot", "a player who left was not taken over by the computer"
    srv.to_lobby()
    assert len(srv.slots) == 3
    srv.close()
    end = time.time() + 2
    while time.time() < end and cl.state != "closed":
        cl.poll()
        time.sleep(0.01)
    assert cl.state == "closed" and "ended" in cl.why
    cl.close()
    f = Finder(port=0)
    f.close()
    # controls: classic presses walk a tile each; kitty: held keys, a release walks on to the centre
    c = Controls(False, 1)
    assert c.feed("up", "press") == [("nudge", 0, "up", False)] and c.direction(0) is None
    assert c.feed(" ", "press") == [("drop", 0)]
    c = Controls(True, 2)
    c.feed("left", "press")
    c.feed("w", "press")
    assert c.direction(1) == "left" and c.direction(0) == "up"
    assert c.feed("left", "release") == [("nudge", 1, "left", True)] and c.direction(1) is None
    assert c.feed("enter", "press") == [("drop", 1)]
    # settings, menus, titles at several sizes, the play loops
    cfg = load_cfg()
    assert cfg == CFG_DEFAULT
    change(cfg, "local", 1)
    change(cfg, "yard", 1)
    change(cfg, "target", -1)
    cfg["name"] = "TESTER"
    save_cfg(cfg)
    assert load_cfg() == cfg
    for cols, rows in ((70, 22), (100, 32), (180, 50)):
        d = TitleDemo()
        for _ in range(40):
            d.scene(cols, rows, 0.1)
        for sel in range(len(MENU)):
            render_menu(d, cols, rows, sel, 0.05, sel == 3, cfg, "a note" if sel == 1 else None).emit()
        g = Match(local_players(cfg), seed=2)
        for st in ("intro", "play", "roundend", "over"):
            g.state = st
            g.champ = 0 if st == "over" else None
            render(g, cols, rows, me=(0, 1), box=PAUSE_LINES if st == "play" else None).emit()
        layout(cols, rows)
    try:
        layout(40, 14)
        raise AssertionError("a tiny window should refuse")
    except ValueError:
        pass
    shot = screenshot(100, 32)
    assert shot.cols == 100
    term = FakeTerm([(0.1, "+"), (0.2, "+"), (0.4, " "), (0.5, "?"), (0.6, "x"), (0.7, " "), (1.2, "esc")])
    run_auto(term, dict(CFG_DEFAULT))
    assert term.frames > 5 and not term.script
    for kitty in (False, True):
        cfg = dict(CFG_DEFAULT, local=2, total=3)
        script = [(0.1, "d"), (0.15, "right"), (0.2, " "), (0.3, "enter"), (0.5, "esc"), (0.6, "v"), (0.65, "v"),
                  (0.7, "v"), (0.8, "q")]
        if kitty:
            script += [(0.12, "d", "release"), (0.18, "right", "release")]
        term = FakeTerm(script, kitty=kitty)
        play_local(term, cfg)
        assert term.frames > 5 and not term.script
    term = FakeTerm([(0.4, "esc")])
    host_session(term, dict(CFG_DEFAULT), TitleDemo(), port=0, beacon=False)
    assert term.frames > 3
    term = FakeTerm([(0.1, "1"), (0.15, "2"), (0.2, "7"), (0.25, "."), (0.3, "0"), (0.35, "."), (0.4, "0"),
                     (0.45, "."), (0.5, "1"), (0.55, ":"), (0.6, "1"), (0.7, "enter"), (1.0, "esc")])
    note = join_session(term, dict(CFG_DEFAULT), TitleDemo(), finder=Finder(port=0))
    assert note is None and term.frames > 3
    assert not os.path.exists(arcadekit.SCORES_PATH), "a score was written without a win"
    print("Self-test ok: %d yards closed and connected, walking, corner help, taps, pots and blasts, crates and "
          "hidden items, chains, kick, ward, curse, the closing walls, a four-bot match, hard beat easy %d/8, safe "
          "drops, snapshots draw the same, LAN join / full / keys / leave over localhost, controls, settings, "
          "titles at three sizes, auto mode, play loops (%.1fs)" % (len(YARDS), hard, time.time() - t0))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
