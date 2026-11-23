#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""DEPTHWELL - falling blocks in three dimensions, seen from above, looking down into a well.

Pieces made of cubes sink into a square well. Move them, turn them about all three axes and fill a whole
floor layer to make it vanish. The colours tell the depth; the gauge on the left shows how high the stack is.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
"""
import math
import random
import time

from arcadekit import (AUTO_LABEL, PAUSE_LINES, AutoMode, Canvas, Terminal, clamp, draw_title, footer, load_scores, mix,
                       overlay, shade, shared_key, submit, title_screen, title_width)
from arcadesound import Sound

GAME = "depthwell"

# piece sets: cube offsets around a pivot cube at (0, 0, 0)
FLAT = {
    "duo": [(0, 0, 0), (1, 0, 0)],
    "vee": [(0, 0, 0), (1, 0, 0), (0, 1, 0)],
    "bar": [(-1, 0, 0), (0, 0, 0), (1, 0, 0)],
    "long": [(-1, 0, 0), (0, 0, 0), (1, 0, 0), (2, 0, 0)],
    "hook": [(-1, 0, 0), (0, 0, 0), (1, 0, 0), (1, 1, 0)],
    "tee": [(-1, 0, 0), (0, 0, 0), (1, 0, 0), (0, 1, 0)],
    "step": [(-1, 0, 0), (0, 0, 0), (0, 1, 0), (1, 1, 0)],
    "square": [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)],
}
SOLID = {
    "tripod": [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)],
    "twist": [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 1, 1)],
    "twirl": [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 0, 1)],
}
BIG = {
    "plus": [(0, 0, 0), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)],
    "cup": [(-1, 0, 0), (-1, 1, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)],
    "stair": [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 2, 0), (2, 2, 0)],
    "corner": [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0), (0, 0, 1)],
    "pillar": [(0, 0, 0), (1, 0, 0), (0, 0, 1), (1, 0, 1), (0, 1, 0)],
}
SETS = [("Flat", "flat pieces only", FLAT), ("Solid", "adds pieces that use all three axes", {**FLAT, **SOLID}),
        ("Wild", "adds big five-cube pieces", {**FLAT, **SOLID, **BIG})]
PITS = [(3, 3, 10), (4, 4, 12), (5, 5, 12), (6, 6, 14)]
# Pieces left out of the 3x3 well: the plus leaves four lone corners in every way it can lie there, and with it
# Wild games in 3x3 lasted about 35 s (level 2-3) against level 12+ for Solid; without it level 10.
NOT_IN_3X3 = ("plus",)
# one colour per depth layer, from the rim down
LAYER = [(236, 84, 84), (244, 150, 56), (236, 212, 70), (130, 214, 76), (56, 200, 160), (60, 170, 236),
         (100, 110, 240), (170, 96, 236), (226, 90, 200), (200, 200, 210), (140, 120, 100), (90, 150, 130),
         (180, 140, 220), (120, 120, 140)]
CLEAR_SCORE = [0, 200, 600, 1200, 2000, 3000]
SND = Sound(GAME, {
    # small and soft: these happen all the time; the three turn axes each have their own pitch
    "move": [dict(w="tri", f=330, d=0.022, v=0.18)],
    "turn_x": [dict(w="square", f=440, f2=523, d=0.03, v=0.14, duty=0.25)],
    "turn_y": [dict(w="square", f=523, f2=622, d=0.03, v=0.14, duty=0.25)],
    "turn_z": [dict(w="square", f=622, f2=740, d=0.03, v=0.14, duty=0.25)],
    "sink": [dict(w="sine", f=220, f2=165, d=0.03, v=0.25)],
    "lock": [dict(w="tri", f=131, f2=98, d=0.08, v=0.32), dict(w="noise", f=500, f2=150, d=0.05, v=0.14, at=0)],
    "drop": [dict(w="sine", f=600, f2=110, d=0.16, v=0.32),
             dict(w="noise", f=1500, f2=120, d=0.12, v=0.26, at=0.1), dict(w="tri", f=98, f2=65, d=0.12, v=0.32, at=0.1)],
    # a floor layer vanishing: a deep, echoing chord that grows with the count
    "clear1": [dict(w="tri", f=294, d=0.1, v=0.4), dict(w="tri", f=440, d=0.3, v=0.38, r="lin")],
    "clear2": [dict(w="tri", f=294, d=0.08, v=0.4), dict(w="tri", f=370, d=0.08, v=0.4),
               dict(w="tri", f=587, d=0.36, v=0.4, vib=(5, 0.2), r="lin")],
    "clear3": [dict(w="tri", f=294, d=0.08, v=0.4), dict(w="tri", f=370, d=0.08, v=0.4), dict(w="tri", f=440, d=0.08, v=0.4),
               dict(w="tri", f=587, d=0.5, v=0.42, vib=(5, 0.25), r="lin"),
               dict(w="sine", f=880, d=0.5, v=0.18, at=0.24, r="lin")],
    "clear4": [dict(w="square", f=f, d=0.07, v=0.26, duty=0.25) for f in (294, 370, 440, 587)] +
              [dict(w="tri", f=740, d=0.6, v=0.42, vib=(5, 0.25), r="lin"), dict(w="tri", f=440, d=0.6, v=0.3, at=0.28, r="lin"),
               dict(w="noise", f=80, d=0.5, v=0.16, at=0.28, r="lin")],
    "clear5": [dict(w="noise", f=1200, f2=60, d=0.5, v=0.36)] +
              [dict(w="square", f=f, d=0.07, v=0.26, duty=0.25, at=0.05 + i * 0.07)
               for i, f in enumerate((294, 370, 440, 587, 740))] +
              [dict(w="tri", f=880, d=0.6, v=0.42, vib=(6, 0.3), r="lin", at=0.4),
               dict(w="tri", f=587, d=0.6, v=0.3, at=0.4, r="lin")],
    "empty": [dict(w="sine", f=f, d=0.06, v=0.32) for f in (587, 740, 880, 1175, 1480, 1760)] +
             [dict(w="tri", f=1175, d=0.6, v=0.3, vib=(7, 0.3), r="lin")],
    "levelup": [dict(w="tri", f=392, d=0.07, v=0.36), dict(w="tri", f=494, d=0.07, v=0.36),
                dict(w="tri", f=587, d=0.07, v=0.36), dict(w="square", f=784, d=0.26, v=0.26, duty=0.25, vib=(6, 0.2))],
    "over": [dict(w="tri", f=330, f2=294, d=0.22, v=0.4), dict(w="tri", f=262, f2=233, d=0.22, v=0.4),
             dict(w="tri", f=196, f2=131, d=0.6, v=0.42, r="lin"), dict(w="noise", f=70, d=0.6, v=0.14, at=0.44, r="lin")],
    # menus
    "menu": [dict(w="tri", f=587, d=0.025, v=0.2)],
    "start": [dict(w="tri", f=440, d=0.05, v=0.34), dict(w="tri", f=587, d=0.05, v=0.34), dict(w="tri", f=880, d=0.16, v=0.36)],
    "pause": [dict(w="tri", f=494, f2=370, d=0.07, v=0.22)],
    "sound_on": [dict(w="tri", f=440, d=0.06, v=0.35), dict(w="tri", f=880, d=0.12, v=0.35)],
})
HELP = [
    "DEPTHWELL - keys",
    "",
    "Arrows  (I J K L)        move the piece across the well",
    "Q / A                    turn about the x axis",
    "W / S                    turn about the y axis",
    "E / D                    turn about the z axis (flat spin)",
    "Space                    drop to the bottom",
    "Enter  (Z)               sink one layer",
    "G                        ghost on / off",
    "",
    "The white piece is yours. The coloured outline on it is where",
    "it lands; the coloured ring on the walls is its depth.",
    "FROM ABOVE: each column coloured by its height, landing cells",
    "outlined. DEPTH (left of the well): the stack's height, the",
    "white mark is your piece. The rim turns red near the top.",
    "",
    "Esc / P                  pause menu (Q quit, M sound)",
    "?                        this help",
    "",
    "Auto mode: the game plays itself (Space pause, +/- speed, Esc stop).",
]


def rot(c, axis, n):
    x, y, z = c
    for _ in range(n % 4):
        if axis == 0:
            x, y, z = x, -z, y
        elif axis == 1:
            x, y, z = z, y, -x
        else:
            x, y, z = -y, x, z
    return x, y, z


class Well:
    def __init__(self, pit, pieces, level=1):
        self.W, self.H, self.D = pit
        if self.W * self.H <= 9:
            pieces = {k: v for k, v in pieces.items() if k not in NOT_IN_3X3} or pieces
        self.pieces = pieces
        self.cell = [[[False] * self.W for _ in range(self.H)] for _ in range(self.D)]  # [z][y][x], z=0 rim
        self.score = self.cubes = self.layers = 0
        self.start_level = self.level = level
        self.t = 0.0
        self.fall = 0.0
        self.lock_at = None
        self.clearing = None
        self.over = self.paused = self.help = False
        self.pops = []
        self.next = self.pick()
        self.spawn()

    def pick(self):
        return random.choice(list(self.pieces))

    def offsets(self, kind):
        return list(self.pieces[kind])

    def spawn(self):
        self.kind, self.next = self.next, self.pick()
        offs = self.offsets(self.kind)
        # random starting orientation, but kept flat-ish so it fits
        for _ in range(random.randrange(4)):
            offs = [rot(c, 2, 1) for c in offs]
        self.offs = offs
        xs, ys, zs = zip(*offs)
        self.px = (self.W - (max(xs) - min(xs) + 1)) // 2 - min(xs)
        self.py = (self.H - (max(ys) - min(ys) + 1)) // 2 - min(ys)
        self.pz = -min(zs)
        self.fall = 0.0
        self.lock_at = None
        if not self.fits(self.offs, self.px, self.py, self.pz):
            # try any orientation that fits before giving up
            for a in range(3):
                for n in range(1, 4):
                    o = [rot(c, a, n) for c in offs]
                    xs, ys, zs = zip(*o)
                    if max(xs) - min(xs) < self.W and max(ys) - min(ys) < self.H:
                        px = (self.W - (max(xs) - min(xs) + 1)) // 2 - min(xs)
                        py = (self.H - (max(ys) - min(ys) + 1)) // 2 - min(ys)
                        if self.fits(o, px, py, -min(zs)):
                            self.offs, self.px, self.py, self.pz = o, px, py, -min(zs)
                            return
            self.over = True

    def cubes_at(self, offs=None, px=None, py=None, pz=None):
        offs = self.offs if offs is None else offs
        px = self.px if px is None else px
        py = self.py if py is None else py
        pz = self.pz if pz is None else pz
        return [(px + x, py + y, pz + z) for x, y, z in offs]

    def fits(self, offs, px, py, pz):
        W, H, D, cell = self.W, self.H, self.D, self.cell
        for x, y, z in offs:
            x, y, z = x + px, y + py, z + pz
            if not (0 <= x < W and 0 <= y < H and 0 <= z < D) or cell[z][y][x]:
                return False
        return True

    def interval(self):
        return max(0.12, 2.4 * 0.83 ** (self.level - 1))

    def move(self, dx, dy):
        if self.fits(self.offs, self.px + dx, self.py + dy, self.pz):
            self.px += dx
            self.py += dy
            self.touch()
            SND.play("move", gap=0.03)

    def turn(self, axis, n):
        o = [rot(c, axis, n) for c in self.offs]
        for dx, dy, dz in ((0, 0, 0), (-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0), (0, 0, 1), (-1, -1, 0),
                           (1, 1, 0), (-1, 1, 0), (1, -1, 0), (-2, 0, 0), (2, 0, 0), (0, -2, 0), (0, 2, 0), (0, 0, 2)):
            if self.fits(o, self.px + dx, self.py + dy, self.pz + dz):
                self.offs, self.px, self.py, self.pz = o, self.px + dx, self.py + dy, self.pz + dz
                self.touch()
                SND.play("turn_" + "xyz"[axis], gap=0.03)
                return

    def touch(self):
        if self.lock_at is not None:
            self.lock_at = self.t + 0.6

    def step(self):
        if self.fits(self.offs, self.px, self.py, self.pz + 1):
            self.pz += 1
            self.score += self.level
            self.fall = 0.0
            SND.play("sink", gap=0.05)

    def drop(self):
        z0 = self.pz
        while self.fits(self.offs, self.px, self.py, self.pz + 1):
            self.pz += 1
        self.score += 2 * (self.pz - z0) * self.level
        self.lock(dropped=True)

    def landing(self):
        z = self.pz
        while self.fits(self.offs, self.px, self.py, z + 1):
            z += 1
        return z

    def lock(self, dropped=False):
        SND.play("drop" if dropped else "lock")
        for x, y, z in self.cubes_at():
            self.cell[z][y][x] = True
        n = len(self.offs)
        self.cubes += n
        self.score += n * 5 * self.level
        full = [z for z in range(self.D) if all(all(row) for row in self.cell[z])]
        if full:
            self.clearing = (full, self.t + 0.35)
            SND.play("clear%d" % min(len(full), 5))
        else:
            self.spawn()

    def finish_clear(self):
        full, _ = self.clearing
        self.clearing = None
        for z in sorted(full):
            del self.cell[z]
            self.cell.insert(0, [[False] * self.W for _ in range(self.H)])
        n = len(full)
        pts = CLEAR_SCORE[min(n, 5)] * self.level * max(1, self.W * self.H // 16)
        self.layers += n
        self.pops.append([["", "LAYER!", "DOUBLE LAYER!", "TRIPLE LAYER!", "QUAD LAYER!", "DEPTH CHARGE!"][min(n, 5)],
                          self.t + 1.3, LAYER[(self.D - 1) % len(LAYER)]])
        if not any(any(any(r) for r in lay) for lay in self.cell):
            pts += 5000 * self.level
            self.pops.append(["EMPTY WELL!", self.t + 1.8, (255, 255, 170)])
            SND.play("empty")
        self.score += pts
        lv = self.level
        self.level = max(self.level, self.start_level + self.layers // 4)
        if self.level > lv:
            SND.play("levelup")
        self.spawn()

    def height(self):
        """How many layers from the bottom contain something."""
        for z in range(self.D):
            if any(any(r) for r in self.cell[z]):
                return self.D - z
        return 0

    def update(self, dt):
        if self.over or self.paused:
            return
        self.t += dt
        self.pops = [p for p in self.pops if p[1] > self.t]
        if self.clearing:
            if self.t >= self.clearing[1]:
                self.finish_clear()
            return
        self.fall += dt
        iv = self.interval()
        while self.fall >= iv and self.fits(self.offs, self.px, self.py, self.pz + 1):
            self.fall -= iv
            self.pz += 1
        if not self.fits(self.offs, self.px, self.py, self.pz + 1):
            self.fall = 0.0
            if self.lock_at is None:
                self.lock_at = self.t + 0.6
            elif self.t >= self.lock_at:
                self.lock()
        else:
            self.lock_at = None

    def key(self, k):
        if self.over or self.paused or self.clearing:
            return
        moves = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1),
                 "j": (-1, 0), "l": (1, 0), "i": (0, -1), "k": (0, 1)}
        turns = {"q": (0, 1), "a": (0, 3), "w": (1, 1), "s": (1, 3), "e": (2, 1), "d": (2, 3)}
        if k in moves:
            self.move(*moves[k])
        elif k in turns:
            self.turn(*turns[k])
        elif k == " ":
            self.drop()
        elif k in ("enter", "z", "y"):
            self.step()


# =============================================================================================
# Auto mode: a placement bot. It tries every orientation the turn keys can reach and every spot across the well,
# rates the result (stack height, holes, bumpiness in both directions, layers cleared), then plays it with the
# keys like a person: a short look, the turns, the slides, the drop.
# =============================================================================================
TURN_KEYS = {"q": (0, 1), "a": (0, 3), "w": (1, 1), "s": (1, 3), "e": (2, 1), "d": (2, 3)}


def orient_key(offs):
    return tuple(sorted(offs))


def turn_paths(offs):
    """Breadth-first over the turn keys: {orientation: shortest key list} (at most 24 orientations)."""
    start = orient_key(offs)
    seen = {start: []}
    todo = [start]
    while todo:
        o = todo.pop(0)
        for k, (axis, n) in TURN_KEYS.items():
            p = orient_key(rot(c, axis, n) for c in o)
            if p not in seen:
                seen[p] = seen[o] + [k]
                todo.append(p)
    return seen


class WellBot:
    """Plays DEPTHWELL through Well.key, at a human pace that quickens with the sinking speed."""
    WEIGHTS = (-0.5, 4.0, -0.9, -0.2)               # stack height, layers, holes, bumpiness

    def __init__(self, rnd=None, err=0.06, pace=1.6, fmin=1.0):
        self.rnd = rnd or random.Random()
        self.err = err                               # chance of a slightly worse move
        self.pace = pace                             # 1 = human-ish; smaller = quicker hands
        self.fmin = fmin                             # how much quicker the hands get when pieces sink fast
        self.piece = None
        self.plan = None
        self.wait = 0.0
        self.replans = 0

    def delays(self, g):
        f = clamp(g.interval() / 0.8, self.fmin, 1.0) * self.pace
        return (0.35 + self.rnd.random() * 0.25) * f, (0.11 + self.rnd.random() * 0.05) * f

    # --- planning --------------------------------------------------------------------------------------------
    def columns(self, g):
        W, H, D = g.W, g.H, g.D
        top = [[D] * W for _ in range(H)]
        holes = [[0] * W for _ in range(H)]
        for y in range(H):
            for x in range(W):
                t = D
                for z in range(D):
                    if g.cell[z][y][x]:
                        t = z
                        break
                top[y][x] = t
                holes[y][x] = sum(1 for z in range(t, D) if not g.cell[z][y][x])
        return top, holes

    def rate(self, g, top, holes, layers):
        W, H, D = g.W, g.H, g.D
        agg = hol = bump = 0
        hi = 0
        for y in range(H):
            for x in range(W):
                h = D - top[y][x]
                agg += h
                hi = max(hi, h)
                hol += holes[y][x]
                if x + 1 < W:
                    bump += abs(top[y][x] - top[y][x + 1])
                if y + 1 < H:
                    bump += abs(top[y][x] - top[y + 1][x])
        w = self.WEIGHTS
        n = W * H
        v = (w[0] * agg + w[2] * hol * 1.0 + w[3] * bump) / n * 16 + w[1] * layers
        if hi > D - 4:                               # close to the rim: keep it low above all
            v -= (hi - (D - 4)) * 6.0
        return v

    def options(self, g):
        """[(value, orientation, px, py)] for every landing of the current piece."""
        W, H, D = g.W, g.H, g.D
        top, holes = self.columns(g)
        full = W * H
        counts = [sum(row.count(True) for row in g.cell[z]) for z in range(D)]
        out = []
        done = set()
        for o in turn_paths(g.offs):
            xs, ys, zs = zip(*o)
            norm = orient_key((x - min(xs), y - min(ys), z - min(zs)) for x, y, z in o)
            if norm in done:                         # the same shape at another pivot: same landings
                continue
            done.add(norm)
            for px in range(-min(xs), W - max(xs)):
                for py in range(-min(ys), H - max(ys)):
                    pz = min(top[py + y][px + x] - 1 - z for x, y, z in o)
                    if pz + min(zs) < 0:
                        continue                     # sticks out over the rim
                    cubes = [(px + x, py + y, pz + z) for x, y, z in o]
                    add = {}
                    for x, y, z in cubes:
                        add[z] = add.get(z, 0) + 1
                    layers = sum(1 for z, n in add.items() if counts[z] + n == full)
                    if layers:                       # rare: recount the columns properly
                        cell = [[row[:] for row in lay] for lay in g.cell]
                        for x, y, z in cubes:
                            cell[z][y][x] = True
                        cell = [lay for lay in cell if not all(all(r) for r in lay)]
                        cell = [[[False] * W for _ in range(H)] for _ in range(D - len(cell))] + cell
                        t2 = [[next((z for z in range(D) if cell[z][y][x]), D) for x in range(W)] for y in range(H)]
                        h2 = [[sum(1 for z in range(t2[y][x], D) if not cell[z][y][x]) for x in range(W)]
                              for y in range(H)]
                    else:
                        t2 = [r[:] for r in top]
                        h2 = [r[:] for r in holes]
                        col = {}
                        for x, y, z in cubes:
                            c = col.setdefault((x, y), [D, 0])
                            c[0] = min(c[0], z)
                            c[1] += 1
                        for (x, y), (zt, n) in col.items():
                            h2[y][x] += top[y][x] - zt - n
                            t2[y][x] = zt
                    out.append((self.rate(g, t2, h2, layers), o, px, py))
        out.sort(key=lambda c: -c[0])
        return out

    def choose(self, g):
        opts = self.options(g)
        if not opts:
            return None
        if self.err and len(opts) > 2 and self.rnd.random() < self.err:
            return opts[self.rnd.choice((1, 2))]
        return opts[0]

    # --- playing ---------------------------------------------------------------------------------------------
    def update(self, g, dt):
        if g.over or g.clearing or g.paused:
            return
        if (g.kind, g.cubes, g.layers) != self.piece:
            self.piece, self.plan, self.replans = (g.kind, g.cubes, g.layers), None, 0
            self.wait = self.delays(g)[0]
        self.wait -= dt
        if self.wait > 0:
            return
        act = self.delays(g)[1]
        if self.plan is None:
            self.plan = self.choose(g)
            if self.plan is None:
                g.key(" ")
                return
        _, o, px, py = self.plan
        before = (orient_key(g.offs), g.px, g.py)
        if orient_key(g.offs) != o:
            path = turn_paths(g.offs).get(o)
            if not path:
                self.plan = None
                return
            g.key(path[0])
        elif g.px != px:
            g.key("right" if px > g.px else "left")
        elif g.py != py:
            g.key("down" if py > g.py else "up")
        else:
            g.key(" ")
            return
        if (orient_key(g.offs), g.px, g.py) == before:   # blocked: think again from here
            self.replans += 1
            self.plan = self.choose(g) if self.replans < 3 else None
            if self.plan is None:
                g.key(" ")
                return
        self.wait = act


# =============================================================================================
# Drawing
# =============================================================================================
class View:
    """Perspective looking straight down the well."""

    def __init__(self, g, cx, cy, size):
        self.g = g
        self.cx, self.cy = cx, cy
        self.cs = size / max(g.W, g.H)
        self.z0 = g.D * 0.62

    def p(self, x, y, z):
        s = self.z0 / (self.z0 + z)
        g = self.g
        return self.cx + (x - g.W / 2) * self.cs * s, self.cy + (y - g.H / 2) * self.cs * s


def layer_col(g, z):
    return LAYER[(g.D - 1 - z) % len(LAYER)]


def draw_well(cv, v):
    g = v.g
    W, H, D = g.W, g.H, g.D
    p = v.p
    r = [p(0, 0, 0), p(W, 0, 0), p(W, H, 0), p(0, H, 0)]
    b = [p(0, 0, D), p(W, 0, D), p(W, H, D), p(0, H, D)]
    cv.poly([r[0], r[1], b[1], b[0]], (15, 16, 30))   # far wall (top of screen)
    cv.poly([r[1], r[2], b[2], b[1]], (12, 13, 25))
    cv.poly([r[2], r[3], b[3], b[2]], (9, 10, 21))
    cv.poly([r[3], r[0], b[0], b[3]], (13, 14, 28))
    cv.poly(b, (8, 9, 19))
    grid = (27, 34, 60)
    for z in range(D + 1):
        q = [p(0, 0, z), p(W, 0, z), p(W, H, z), p(0, H, z)]
        c = grid if z < D else (44, 56, 96)
        for i in range(4):
            cv.line(*q[i], *q[(i + 1) % 4], c)
    for i in range(W + 1):
        cv.line(*p(i, 0, 0), *p(i, 0, D), grid)
        cv.line(*p(i, H, 0), *p(i, H, D), grid)
        cv.line(*p(i, 0, D), *p(i, H, D), grid)
    for j in range(H + 1):
        cv.line(*p(0, j, 0), *p(0, j, D), grid)
        cv.line(*p(W, j, 0), *p(W, j, D), grid)
        cv.line(*p(0, j, D), *p(W, j, D), grid)
    cv.frame(int(r[0][0]) - 1, int(r[0][1]) - 1, int(r[2][0] - r[0][0]) + 3, int(r[2][1] - r[0][1]) + 3, (66, 76, 120))


def face_detail(cv, q, col):
    """A cube top seen from above is an upright rectangle on screen. When it is big enough (a large window),
    give it an inner bevel, a soft falloff and a glint, so a big window shows finer cubes, not flat slabs.
    Small faces stay exactly as they were."""
    x0, y0 = int(round(q[0][0])), int(round(q[0][1]))
    x1, y1 = int(round(q[2][0])), int(round(q[2][1]))
    w, h = x1 - x0, y1 - y0
    if q[2][0] - q[0][0] < 10 or w < 8 or h < 8:   # decided on the exact size, so a whole layer agrees
        return
    b = 2 if w >= 24 else 1
    px, W, H = cv.px, cv.W, cv.H
    lo_y, hi_y = max(0, y0 + 1), min(H, y1)
    lo_x, hi_x = max(0, x0 + 1), min(W, x1)
    if hi_x <= lo_x:
        return
    hi, hi2, dk = shade(col, 1.22), shade(col, 1.1), shade(col, 0.82)
    span = max(1, (w + h - 4 * b - 2))
    for y in range(lo_y, hi_y):
        u, d = y - y0, y1 - y
        row = px[y]
        if u <= b:
            row[lo_x:hi_x] = [hi if u == 1 else hi2] * (hi_x - lo_x)
            continue
        if d <= b:
            row[lo_x:hi_x] = [dk] * (hi_x - lo_x)
            continue
        # the face: a gentle diagonal falloff away from the lit corner, in four steps (cheap, no banding noise)
        for x in range(lo_x, hi_x):
            l, r = x - x0, x1 - x
            if l <= b:
                row[x] = hi if l == 1 else hi2
            elif r <= b:
                row[x] = dk
            else:
                f = (u + l - 2 * b - 2) / span
                row[x] = shade(col, 1.06 - 0.12 * f)
    g = shade(col, 1.5)
    gl = max(2, w // 5)
    if b + 1 < h:
        for i in range(gl):
            xx, yy = x0 + b + 1 + i, y0 + b + 1
            if 0 <= yy < H and 0 <= xx < W:
                px[yy][xx] = g if i < gl - 1 else mix(g, px[yy][xx], 0.5)
        if 0 <= y0 + b + 2 < H and 0 <= x0 + b + 1 < W:
            px[y0 + b + 2][x0 + b + 1] = mix(g, px[y0 + b + 2][x0 + b + 1], 0.5)


def draw_cubes(cv, v, flash=()):
    g = v.g
    W, H, D, cell = g.W, g.H, g.D, g.cell
    p = v.p
    hw, hh = W / 2, H / 2
    for z in range(D - 1, -1, -1):
        base = layer_col(g, z)
        if z in flash:
            base = mix(base, (255, 255, 255), 0.8 if int(g.t * 24) % 2 else 0.5)
        fog = mix(base, (8, 8, 16), 0.32 * z / D)
        top, sx, sy, edge = fog, shade(fog, 0.74), shade(fog, 0.56), shade(fog, 0.42)
        order = sorted(((x, y) for y in range(H) for x in range(W) if cell[z][y][x]),
                       key=lambda c: -max(abs(c[0] + 0.5 - hw), abs(c[1] + 0.5 - hh)))
        for x, y in order:
            # side faces turned towards the middle of the well, unless a neighbour covers them
            if x > hw - 0.01 and (x == 0 or not cell[z][y][x - 1]):
                cv.poly([p(x, y, z), p(x, y + 1, z), p(x, y + 1, z + 1), p(x, y, z + 1)], sx)
            if x + 1 < hw + 0.01 and (x + 1 >= W or not cell[z][y][x + 1]):
                cv.poly([p(x + 1, y, z), p(x + 1, y + 1, z), p(x + 1, y + 1, z + 1), p(x + 1, y, z + 1)], sx)
            if y > hh - 0.01 and (y == 0 or not cell[z][y - 1][x]):
                cv.poly([p(x, y, z), p(x + 1, y, z), p(x + 1, y, z + 1), p(x, y, z + 1)], sy)
            if y + 1 < hh + 0.01 and (y + 1 >= H or not cell[z][y + 1][x]):
                cv.poly([p(x, y + 1, z), p(x + 1, y + 1, z), p(x + 1, y + 1, z + 1), p(x, y + 1, z + 1)], sy)
            if z == 0 or not cell[z - 1][y][x]:
                q = [p(x, y, z), p(x + 1, y, z), p(x + 1, y + 1, z), p(x, y + 1, z)]
                cv.poly(q, top)
                face_detail(cv, q, top)
                for i in range(4):
                    cv.line(*q[i], *q[(i + 1) % 4], edge)


def wire(cv, v, cubes, col):
    p = v.p
    for x, y, z in cubes:
        a = [p(x, y, z), p(x + 1, y, z), p(x + 1, y + 1, z), p(x, y + 1, z)]
        b = [p(x, y, z + 1), p(x + 1, y, z + 1), p(x + 1, y + 1, z + 1), p(x, y + 1, z + 1)]
        for i in range(4):
            cv.line(*b[i], *b[(i + 1) % 4], shade(col, 0.6))
            cv.line(*a[i], *b[i], shade(col, 0.8))
        for i in range(4):
            cv.line(*a[i], *a[(i + 1) % 4], col)


def ring(cv, v, z, col):
    """A line round the four walls at depth z: tells at a glance how deep something is."""
    g, p = v.g, v.p
    q = [p(0, 0, z), p(g.W, 0, z), p(g.W, g.H, z), p(0, g.H, z)]
    for i in range(4):
        cv.line(*q[i], *q[(i + 1) % 4], col)


def footprint(cv, v, cubes, col):
    """Where the piece will land: the outline of its cubes at the landing depth, in that layer's colour.
    Drawn over the falling piece, so it shows as a smaller outline inside it, like a shadow."""
    p = v.p
    occ = {(x, y) for x, y, _ in cubes}
    for x, y, z in cubes:
        if (x, y, z - 1) in cubes:
            continue
        for (dx, dy), (a, b) in (((-1, 0), ((x, y), (x, y + 1))), ((1, 0), ((x + 1, y), (x + 1, y + 1))),
                                 ((0, -1), ((x, y), (x + 1, y))), ((0, 1), ((x, y + 1), (x + 1, y + 1)))):
            if (x + dx, y + dy) not in occ:
                cv.line(*p(a[0], a[1], z), *p(b[0], b[1], z), col)


def solid_piece(cv, v, cubes, g):
    """The falling piece: bright filled tops with white edges and dim sides, deepest cubes first."""
    p = v.p
    occupied = set(cubes)
    base = (226, 230, 246)
    for x, y, z in sorted(cubes, key=lambda c: -c[2]):
        for dx, dy, face in ((-1, 0, ((x, y), (x, y + 1))), (1, 0, ((x + 1, y), (x + 1, y + 1))),
                             (0, -1, ((x, y), (x + 1, y))), (0, 1, ((x, y + 1), (x + 1, y + 1)))):
            if (x + dx, y + dy, z) in occupied:
                continue
            (ax, ay), (bx, by) = face
            cv.poly([p(ax, ay, z), p(bx, by, z), p(bx, by, z + 1), p(ax, ay, z + 1)], (110, 116, 140))
        if (x, y, z - 1) not in occupied:
            q = [p(x, y, z), p(x + 1, y, z), p(x + 1, y + 1, z), p(x, y + 1, z)]
            cv.poly(q, base)
            face_detail(cv, q, base)
            for i in range(4):
                cv.line(*q[i], *q[(i + 1) % 4], (255, 255, 255))


def height_map(cv, g, x0, y0, cell):
    """A top-down map of the well: each column coloured by its stack height, the piece's landing cells outlined."""
    W, H, D = g.W, g.H, g.D
    land = set()
    if not g.over and not g.clearing:
        lz = g.landing()
        land = {(x, y) for x, y, z in g.cubes_at(pz=lz)}
    cv.rect(x0 - 1, y0 - 1, W * cell + 1, H * cell + 1, (40, 44, 70))
    for y in range(H):
        for x in range(W):
            top = next((z for z in range(D) if g.cell[z][y][x]), None)
            c = layer_col(g, top) if top is not None else (14, 15, 26)
            cv.rect(x0 + x * cell, y0 + y * cell, cell - 1, cell - 1, c)
            if (x, y) in land:
                if cell >= 4:
                    cv.frame(x0 + x * cell, y0 + y * cell, cell - 1, cell - 1, (255, 255, 255))
                else:    # too small to outline: the cell turns white
                    cv.rect(x0 + x * cell, y0 + y * cell, cell - 1, cell - 1, (255, 255, 255))


def iso_box(offs, k):
    """The pixel bounds of iso()'s picture, relative to its origin."""
    xs = [(x - y) * k for x, y, z in offs]
    ys = [(x + y) * k / 2 - z * k for x, y, z in offs]
    return min(xs) - k, min(ys) - k / 2, max(xs) + k, max(ys) + k * 1.5


def iso(cv, offs, ox, oy, k, col):
    """A small isometric picture of a piece (for the NEXT box)."""
    cubes = sorted(offs, key=lambda c: (c[2], c[0] + c[1]))
    for x, y, z in cubes:
        sx, sy = ox + (x - y) * k, oy + (x + y) * k / 2 - z * k
        t = [(sx, sy - k / 2), (sx + k, sy), (sx, sy + k / 2), (sx - k, sy)]
        cv.poly(t, shade(col, 1.15))
        cv.poly([(sx - k, sy), (sx, sy + k / 2), (sx, sy + k * 1.5), (sx - k, sy + k)], shade(col, 0.7))
        cv.poly([(sx + k, sy), (sx, sy + k / 2), (sx, sy + k * 1.5), (sx + k, sy + k)], shade(col, 0.5))


PANEL_BODY = (15, 16, 30)
PANEL_HEAD = (30, 32, 58)
PANEL_EDGE = (48, 52, 88)
LABEL = (138, 144, 182)
VALUE = (240, 240, 250)
SCORE_C = (250, 214, 120)


def panel(cv, col, row, w, h, title=None, title_fg=LABEL):
    """A framed box in character cells, with an optional header strip."""
    cv.rect(col, row * 2, w, h * 2, PANEL_BODY)
    cv.frame(col, row * 2, w, h * 2, PANEL_EDGE)
    if title:
        cv.put(col + 1, row, (" " + title).ljust(w - 2)[:w - 2], title_fg, PANEL_HEAD)


def stat(cv, col, row, w, label, value, fg=VALUE):
    cv.put(col + 1, row, (" " + label).ljust(w - 2)[:w - 2], LABEL, PANEL_BODY)
    cv.put(col + w - 2 - len(value), row, value, fg, PANEL_BODY)


def render(g, cols, rows, ghost=True):
    cv = Canvas(cols, rows)
    cv.vgradient((6, 6, 14), (14, 8, 22))
    PH = (rows - 1) * 2                              # the footer keeps the last row
    RW = clamp(cols - (PH - 4) - 15, 20, 30)          # the side panel grows when there is room
    size = max(20, min(PH - 4, cols - RW - 15))
    x0 = max(0, (cols - (8 + size + 3 + RW)) // 2)   # gauge, well and panel centred as one group
    cx = x0 + 8 + size / 2
    cy = PH / 2
    v = View(g, cx, cy, size)
    hgt = g.height()
    danger = clamp((hgt - (g.D - 3)) / 3, 0, 1) if not g.over else 0
    pulse = 0.6 + 0.4 * math.sin(g.t * 8)
    draw_well(cv, v)
    if danger or g.clearing:   # the rim glows red near the top, and flashes white as layers vanish
        r0, r2 = v.p(0, 0, 0), v.p(g.W, g.H, 0)
        c = mix((66, 76, 120), (236, 64, 64), danger * pulse)
        if g.clearing:
            c = mix(c, (255, 255, 255), clamp((g.clearing[1] - g.t) / 0.35, 0, 1))
        x, y, w, h = int(r0[0]) - 1, int(r0[1]) - 1, int(r2[0] - r0[0]) + 3, int(r2[1] - r0[1]) + 3
        cv.frame(x, y, w, h, c)
        cv.frame(x - 1, y - 1, w + 2, h + 2, c)
    clearing = g.clearing[0] if g.clearing else ()
    for z in clearing:            # a cleared layer: its ring on the walls flashes white
        ring(cv, v, z, (255, 255, 255))
        ring(cv, v, z + 1, (255, 255, 255))
    playing = not g.over and not g.clearing
    if playing:
        cubes = g.cubes_at()
        bottom = max(z for _, _, z in cubes) + 1
        ring(cv, v, bottom, shade(layer_col(g, bottom - 1), 1.1))     # the piece's depth, on the walls
    draw_cubes(cv, v, clearing)
    if playing:
        solid_piece(cv, v, cubes, g)
        if ghost:
            lz = g.landing()
            if lz != g.pz:
                land = g.cubes_at(pz=lz)
                footprint(cv, v, land, layer_col(g, max(z for _, _, z in land)))
    # depth gauge just left of the well: one box per layer, lit up to the stack height
    gx = int(cx - size / 2) - 8
    gh = min(PH - 6, g.D * 4)
    step = gh / g.D
    gy = (PH - gh) / 2
    cv.put(gx, max(0, int(gy) // 2 - 1), "DEPTH", LABEL)
    pz = {z for _, _, z in g.cubes_at()} if playing else set()
    lzs = {z for _, _, z in g.cubes_at(pz=g.landing())} if playing and ghost else set()
    for i in range(g.D):
        z = g.D - 1 - i
        y = int(gy + gh - (i + 1) * step) + 1
        hh = max(1, int(step) - 1)
        c = layer_col(g, z) if i < hgt else (30, 32, 54)
        if z in clearing:
            c = (255, 255, 255)
        elif i < hgt and i >= g.D - 3:
            c = mix(c, (236, 64, 64), pulse * 0.5)
        cv.rect(gx, y, 4, hh, c)
        if z in pz:            # the falling piece's layers
            cv.rect(gx + 5, y, 2, hh, (255, 255, 255))
        elif z in lzs:         # where it will land
            cv.rect(gx + 5, y, 1, hh, (120, 126, 160))
    # side panel: stats, next piece, the map from above; each in its own frame
    px = int(cx + size / 2) + 4
    RW = min(RW, cols - px)
    sh = 6
    panel(cv, px, 0, RW, sh, "WELL %dx%dx%d" % (g.W, g.H, g.D))
    for i, (a, b, c) in enumerate([("SCORE", "%d" % g.score, SCORE_C), ("LEVEL", "%d" % g.level, VALUE),
                                   ("LAYERS", "%d" % g.layers, VALUE), ("CUBES", "%d" % g.cubes, VALUE)]):
        stat(cv, px, 1 + i, RW, a, b, c)
    free = rows - 1 - sh                             # rows left for NEXT and the map
    cell = max(2, min(6, ((free - 9) * 2 - 3) // max(g.W, g.H), (RW - 4) // g.W))   # NEXT keeps 7+ rows
    mh = (max(g.W, g.H) * cell + 2) // 2 + 2         # map panel rows
    k = 3 if free - mh >= 9 else 2
    offs = g.offsets(g.next)
    bx0, by0, bx1, by1 = iso_box(offs, k)
    nh = max(4, min(free - mh, int(by1 - by0 + 3) // 2 + 2))
    panel(cv, px, sh, RW, nh, "NEXT")
    iso(cv, offs, px + (RW - (bx1 - bx0)) / 2 - bx0, (sh + 1) * 2 + ((nh - 1) * 2 - (by1 - by0)) / 2 - by0, k,
        (200, 210, 240))
    my = sh + nh
    mh = max(3, min(mh, rows - 1 - my))
    panel(cv, px, my, RW, mh, "FROM ABOVE")
    height_map(cv, g, px + (RW - g.W * cell) // 2, (my + 1) * 2 + 1, cell)
    for i, (txt, until, c) in enumerate(reversed(g.pops[-2:])):
        cv.center(int(cy / 2) - 2 + i * 2, "  %s  " % txt, (14, 14, 20), c, int(cx - size / 2), int(size))
    if g.paused:
        overlay(cv, HELP if g.help else PAUSE_LINES + ["", SND.label()])
    footer(cv, "Arrows move  Q W E turn  Space drop  ? help")
    return cv


def render_over(g, cv, record, auto=False):
    lines = ["THE WELL IS FULL", "", "score  %d" % g.score, "layers %d   cubes %d   level %d" % (g.layers, g.cubes, g.level)]
    if record:
        lines += ["", "** NEW RECORD **"]
    lines += ["", "auto mode: a new round starts" if auto else "Enter: again   Esc / Q: menu"]
    w = max(len(l) for l in lines) + 4
    cv.box(max(0, (cv.cols - w) // 2), max(0, cv.rows // 2 - len(lines) // 2 - 1), [l.center(w - 4) for l in lines],
           (240, 240, 246), (24, 22, 44))


def mode_key(pit, si):
    return "%dx%dx%d %s" % (pit + (SETS[si][0],))


def render_menu(cols, rows, sel, opts, t, help_=False):
    cv = Canvas(cols, rows)
    cv.vgradient((6, 6, 14), (18, 8, 26))
    # a slowly turning demo well in the background
    demo = Well((4, 4, 10), FLAT)
    rnd = random.Random(3)
    for z in range(6, 10):
        for y in range(4):
            for x in range(4):
                demo.cell[z][y][x] = rnd.random() < 0.8 - (9 - z) * 0.12
    demo.t = t
    PH = rows * 2
    size = min(PH - 6, cols // 2)
    v = View(demo, cols / 2 + math.sin(t * 0.4) * cols * 0.02, PH / 2 + 4, size)
    draw_well(cv, v)
    draw_cubes(cv, v)
    pit, si, level = opts
    items = ["well     < %dx%dx%d >" % PITS[pit], "pieces   < %s - %s >" % (SETS[si][0], SETS[si][1]),
             "level    < %d >" % level, "START", AUTO_LABEL]
    rec = load_scores().get(GAME, {}).get(mode_key(PITS[pit], si))
    title_screen(cv, "DEPTHWELL", "falling blocks in three dimensions", items, sel,
                 "best for this well: %d" % rec if rec is not None else None,
                 keys="Up/Down choose   Left/Right change   Enter start   M %s   ? help   Esc back" % SND.label().lower(),
                 help_lines=HELP, show_help=help_)
    return cv


STEP = 1 / 120              # auto mode steps the game in fixed slices (more of them when sped up)


def run_auto(term, pit, si, level):
    """Auto mode: the bot plays rounds in the chosen well until the viewer stops it. Nothing is recorded."""
    auto = AutoMode()
    while True:
        g = Well(pit, SETS[si][2], level)
        bot = WellBot()
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
            for _ in range(auto.steps(dt, STEP)):
                if g.over:
                    break
                bot.update(g, STEP)
                g.update(STEP)
            if g.over and over_at is None:
                SND.play("over")
                over_at = now
            if over_at is not None:
                if auto.paused:
                    over_at += dt                    # paused: the result box stays
                elif now - over_at > 3.0:
                    break
            cols, rows = term.size()
            if cols < 70 or rows < 22:
                term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (70x22).")
                time.sleep(0.2)
                continue
            cv = render(g, cols, rows)
            if g.over:
                render_over(g, cv, None, auto=True)
            auto.banner(cv, extra="level %d" % g.level)
            term.write(cv.emit())
            time.sleep(max(0, 1 / 30 - (time.time() - now)))


def main():
    with Terminal() as term:
        sel, opts = 3, [1, 1, 1]
        help_ = False
        while True:
            t0 = time.time()
            go = False
            while not go:
                cols, rows = term.size()
                term.write(render_menu(cols, rows, sel, opts, time.time() - t0, help_).emit())
                for k in term.keys(1 / 15):
                    if help_:            # any key closes the help
                        help_ = False
                        continue
                    if k == "?":
                        help_ = True
                    elif k in ("q", "esc"):
                        return
                    if k in ("up", "w"):
                        sel = (sel - 1) % 5
                        SND.play("menu")
                    elif k in ("down", "s"):
                        sel = (sel + 1) % 5
                        SND.play("menu")
                    elif k in ("left", "right", "a", "d") and sel < 3:
                        d = -1 if k in ("left", "a") else 1
                        lim = [len(PITS), len(SETS), 15][sel]
                        opts[sel] = (opts[sel] + d) % lim if sel < 2 else clamp(opts[sel] + d, 1, lim)
                        SND.play("menu")
                    elif k == "m":
                        if SND.toggle():
                            SND.play("sound_on")
                    elif k in ("enter", " "):
                        SND.play("start")
                        go = True
            pit, si, level = PITS[opts[0]], opts[1], opts[2]
            if sel == 4:
                run_auto(term, pit, si, level)
                continue
            while True:
                g = Well(pit, SETS[si][2], level)
                ghost = True
                last = time.time()
                record = None
                back = again = False
                while not (back or again):
                    now = time.time()
                    g.update(min(0.1, now - last))
                    last = now
                    for k in term.keys(0):
                        if g.over:
                            if k in ("q", "esc"):
                                back = True
                            elif record is not None and k in ("enter", " "):
                                again = True
                            continue
                        a = shared_key(k, g.paused, pause_keys=("esc", "p"))   # Q turns pieces here
                        if a == "pause":
                            g.paused = True
                            SND.play("pause")
                        elif a == "resume":
                            g.paused = g.help = False
                        elif a == "quit":
                            back = True
                        elif a == "help":
                            g.help = not g.help
                            g.paused = True
                        elif a == "sound":
                            if SND.toggle():
                                SND.play("sound_on")
                        elif a is None:
                            if k == "g":
                                ghost = not ghost
                            else:
                                g.key(k)
                    if g.over and record is None:
                        SND.play("over")
                        record = submit(GAME, mode_key(pit, si), g.score)
                    cols, rows = term.size()
                    if cols < 70 or rows < 22:
                        term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (70x22).")
                        time.sleep(0.2)
                        continue
                    cv = render(g, cols, rows, ghost)
                    if g.over:
                        render_over(g, cv, record)
                    term.write(cv.emit())
                    time.sleep(max(0, 1 / 30 - (time.time() - now)))
                if back:
                    break


# =============================================================================================
# Self-test:  python3 depthwell.py --selftest
# =============================================================================================
def screenshot(cols=100, rows=32, pit=2, si=2, level=1, seed=2, secs=186.26):
    """README picture: real play (the auto-mode WellBot) with a fixed seed, at a good moment, HUD and all.
    The 5x5x12 well with the Wild pieces, seed 2, 186 s in (level 5): five coloured layers deep, a piece
    on its way down with its landing outlined."""
    state, quiet = random.getstate(), SND.enabled
    SND.enabled = False
    try:
        random.seed(seed)
        g = Well(PITS[pit], SETS[si][2], level)
        bot = WellBot(random.Random(seed))
        for _ in range(int(secs / STEP)):
            if g.over:
                break
            bot.update(g, STEP)
            g.update(STEP)
        return render(g, cols, rows)
    finally:
        random.setstate(state)
        SND.enabled = quiet


class FakeTerm:
    """Stands in for the terminal: scripted keys by time, a fixed size, output thrown away."""

    def __init__(self, script, size=(100, 32)):
        self.script = sorted(script)                 # [(seconds after start, key)]
        self.t0 = time.time()
        self.cols_rows = size
        self.frames = 0

    def keys(self, timeout=0.0):
        now = time.time() - self.t0
        out = [k for t, k in self.script if t <= now]
        self.script = [(t, k) for t, k in self.script if t > now]
        return out

    def size(self):
        return self.cols_rows

    def write(self, s):
        self.frames += 1


def selftest():
    import os
    import sys
    import tempfile
    import arcadekit
    t0 = time.time()
    tmp = os.path.join(tempfile.mkdtemp(), "scores.json")
    arcadekit.SCORES_PATH = tmp                      # never touch the player's real scores
    random.seed(2)
    # rules: a full layer vanishes and scores
    g = Well(PITS[0], FLAT)
    for y in range(3):
        for x in range(3):
            g.cell[g.D - 1][y][x] = (x, y) not in ((0, 1), (1, 1), (2, 1))
    g.offs, g.px, g.py, g.pz = [(-1, 0, 0), (0, 0, 0), (1, 0, 0)], 1, 1, 0
    g.drop()
    g.update(0.5)
    assert g.layers == 1 and g.height() == 0, "a full layer did not clear"
    # the turn keys reach every orientation (24 for an asymmetric piece, 6 for the long bar about its pivot)
    assert "plus" not in Well(PITS[0], SETS[2][2]).pieces and "plus" in Well(PITS[1], SETS[2][2]).pieces
    assert len(turn_paths(SOLID["twist"])) == 24 and len(turn_paths(FLAT["long"])) == 6
    # the bot plays every well and piece set at x8 without errors; the results stay unrecorded
    for pit in PITS:
        for name, _, pieces in SETS:
            random.seed(7)
            g = Well(pit, pieces, 1)
            bot = WellBot(random.Random(7))
            auto = AutoMode()
            for _ in range(5):
                auto.key("+")
            assert auto.speed == 8.0
            frames = 0
            while not g.over and frames < 60 * 8:   # 8 s of watching at x8 = 64 s of play
                for _ in range(auto.steps(1 / 60, STEP)):
                    if g.over:
                        break
                    bot.update(g, STEP)
                    g.update(STEP)
                frames += 1
            assert g.cubes > 0
            assert g.layers >= 3, "%s %s: the bot cleared only %d layers" % (pit, name, g.layers)
            cv = render(g, 100, 32)
            auto.banner(cv, extra="level %d" % g.level)
            if g.over:
                render_over(g, cv, None, auto=True)
            cv.emit()
    # the real auto-mode loop: speed up, pause, help, stop
    term = FakeTerm([(0.05, "+"), (0.1, "+"), (0.15, "+"), (0.6, " "), (0.8, "?"), (0.9, "x"), (1.0, " "), (1.4, "esc")])
    run_auto(term, PITS[1], 1, 2)
    assert term.frames > 10 and not term.script
    for cols, rows in ((70, 22), (160, 48)):
        for sel in range(5):
            render_menu(cols, rows, sel, [1, 1, 1], 1.0).emit()
        render_menu(cols, rows, 4, [1, 1, 1], 1.0, True).emit()
    assert not os.path.exists(tmp), "auto mode wrote a score"
    print("Self-test ok: layers, turn reach, auto mode in all %d wells x %d piece sets at x8 (no scores written), "
          "auto loop keys, title (%.1fs)" % (len(PITS), len(SETS), time.time() - t0))


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
