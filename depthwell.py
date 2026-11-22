#!/usr/bin/env python3
"""DEPTHWELL - falling blocks in three dimensions, seen from above, looking down into a well.

Pieces made of cubes sink into a square well. Move them, turn them about all three axes and fill a whole
floor layer to make it vanish. The colours tell the depth; the gauge on the left shows how high the stack is.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
"""
import math
import random
import time

from arcadekit import (PAUSE_LINES, Canvas, Terminal, clamp, draw_title, load_scores, mix, overlay, shade,
                       shared_key, submit, title_screen, title_width)

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
# one colour per depth layer, from the rim down
LAYER = [(236, 84, 84), (244, 150, 56), (236, 212, 70), (130, 214, 76), (56, 200, 160), (60, 170, 236),
         (100, 110, 240), (170, 96, 236), (226, 90, 200), (200, 200, 210), (140, 120, 100), (90, 150, 130),
         (180, 140, 220), (120, 120, 140)]
CLEAR_SCORE = [0, 200, 600, 1200, 2000, 3000]
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
    "The bright block is your piece; the outlined spot below shows where it lands.",
    "FROM ABOVE (right): every column coloured by its height, the landing cells",
    "outlined in white. The gauge on the left marks your piece's depth.",
    "",
    "Esc / P                  pause menu (Q there: quit)",
    "?                        this help",
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

    def turn(self, axis, n):
        o = [rot(c, axis, n) for c in self.offs]
        for dx, dy, dz in ((0, 0, 0), (-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0), (0, 0, 1), (-1, -1, 0),
                           (1, 1, 0), (-1, 1, 0), (1, -1, 0), (-2, 0, 0), (2, 0, 0), (0, -2, 0), (0, 2, 0), (0, 0, 2)):
            if self.fits(o, self.px + dx, self.py + dy, self.pz + dz):
                self.offs, self.px, self.py, self.pz = o, self.px + dx, self.py + dy, self.pz + dz
                self.touch()
                return

    def touch(self):
        if self.lock_at is not None:
            self.lock_at = self.t + 0.6

    def step(self):
        if self.fits(self.offs, self.px, self.py, self.pz + 1):
            self.pz += 1
            self.score += self.level
            self.fall = 0.0

    def drop(self):
        z0 = self.pz
        while self.fits(self.offs, self.px, self.py, self.pz + 1):
            self.pz += 1
        self.score += 2 * (self.pz - z0) * self.level
        self.lock()

    def landing(self):
        z = self.pz
        while self.fits(self.offs, self.px, self.py, z + 1):
            z += 1
        return z

    def lock(self):
        for x, y, z in self.cubes_at():
            self.cell[z][y][x] = True
        n = len(self.offs)
        self.cubes += n
        self.score += n * 5 * self.level
        full = [z for z in range(self.D) if all(all(row) for row in self.cell[z])]
        if full:
            self.clearing = (full, self.t + 0.35)
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
        self.score += pts
        self.level = max(self.level, self.start_level + self.layers // 4)
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


def footprint(cv, v, cubes):
    """Where the piece will land: the top faces at the landing spot, softly lit, with a pale outline."""
    p = v.p
    for x, y, z in cubes:
        q = [p(x, y, z), p(x + 1, y, z), p(x + 1, y + 1, z), p(x, y + 1, z)]
        cv.poly(q, (64, 70, 96))
        for i in range(4):
            cv.line(*q[i], *q[(i + 1) % 4], (190, 196, 150))


def solid_piece(cv, v, cubes, g):
    """The falling piece: bright filled tops with white edges and dim sides, deepest cubes first."""
    p = v.p
    occupied = set(cubes)
    base = (232, 236, 250)
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
                cv.frame(x0 + x * cell, y0 + y * cell, cell - 1, cell - 1, (255, 255, 255))


def iso(cv, offs, ox, oy, k, col):
    """A small isometric picture of a piece (for the NEXT box)."""
    cubes = sorted(offs, key=lambda c: (c[2], c[0] + c[1]))
    for x, y, z in cubes:
        sx, sy = ox + (x - y) * k, oy + (x + y) * k / 2 - z * k
        t = [(sx, sy - k / 2), (sx + k, sy), (sx, sy + k / 2), (sx - k, sy)]
        cv.poly(t, shade(col, 1.15))
        cv.poly([(sx - k, sy), (sx, sy + k / 2), (sx, sy + k * 1.5), (sx - k, sy + k)], shade(col, 0.7))
        cv.poly([(sx + k, sy), (sx, sy + k / 2), (sx, sy + k * 1.5), (sx + k, sy + k)], shade(col, 0.5))


def render(g, cols, rows, ghost=True):
    cv = Canvas(cols, rows)
    cv.vgradient((6, 6, 14), (14, 8, 22))
    PH = (rows - 1) * 2
    size = min(PH - 6, cols - 44)
    cx = 12 + size / 2 + max(0, (cols - 44 - size) // 2)
    cy = PH / 2
    v = View(g, cx, cy, size)
    draw_well(cv, v)
    draw_cubes(cv, v, g.clearing[0] if g.clearing else ())
    if not g.over and not g.clearing:
        cubes = g.cubes_at()
        if ghost:
            lz = g.landing()
            if lz != g.pz:
                footprint(cv, v, g.cubes_at(pz=lz))
        solid_piece(cv, v, cubes, g)
    # depth gauge: one box per layer, lit up to the stack height
    gx = 3
    gh = min(PH - 8, g.D * 4)
    step = gh / g.D
    gy = (PH - gh) / 2
    hgt = g.height()
    for i in range(g.D):
        z = g.D - 1 - i
        y = gy + gh - (i + 1) * step
        c = layer_col(g, z) if i < hgt else (28, 30, 50)
        cv.rect(gx, int(y) + 1, 5, max(1, int(step) - 1), c)
        if not g.over and any(cz == z for _, _, cz in g.cubes_at()):   # the falling piece's depth
            cv.rect(gx + 6, int(y) + 1, 2, max(1, int(step) - 1), (255, 255, 255))
    # panel
    px = int(cx + size / 2) + 6
    row = 1
    cv.put(px, row, "DEPTHWELL", (236, 212, 70))
    stats = [("SCORE", "%d" % g.score), ("LEVEL", "%d" % g.level), ("LAYERS", "%d" % g.layers),
             ("CUBES", "%d" % g.cubes), ("WELL", "%dx%dx%d" % (g.W, g.H, g.D))]
    for i, (a, b) in enumerate(stats):           # one line each keeps room for the map below
        cv.put(px, row + 2 + i, a, (130, 136, 170))
        cv.put(px + 8, row + 2 + i, b, (240, 240, 250))
    cv.put(px, row + 8, "NEXT", (130, 136, 170))
    iso(cv, g.offsets(g.next), px + 12, (row + 10) * 2 + 4, 3, (200, 210, 240))
    my = row + 16                                # the map from above fills what is left
    cv.put(px, my, "FROM ABOVE", (130, 136, 170))
    cell = max(2, min(6, (rows - 3 - my) * 2 // max(g.W, g.H)))
    height_map(cv, g, px + 1, (my + 1) * 2 + 1, cell)
    cv.put(px, rows - 2, "? keys   Esc pause", (110, 114, 140))
    for i, (txt, until, c) in enumerate(reversed(g.pops[-2:])):
        cv.center(int(cy / 2) - 2 + i * 2, " %s " % txt, (14, 14, 20), c, int(cx - size / 2), int(size))
    if g.paused:
        overlay(cv, HELP if g.help else PAUSE_LINES)
    return cv


def render_over(g, cv, record):
    lines = ["THE WELL IS FULL", "", "score  %d" % g.score, "layers %d   cubes %d" % (g.layers, g.cubes)]
    if record:
        lines += ["", "** NEW RECORD **"]
    lines += ["", "Enter: again   Esc / Q: menu"]
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
             "level    < %d >" % level, "START"]
    rec = load_scores().get(GAME, {}).get(mode_key(PITS[pit], si))
    title_screen(cv, "DEPTHWELL", "falling blocks in three dimensions", items, sel,
                 "best for this well: %d" % rec if rec is not None else None,
                 keys="Up/Down choose   Left/Right change   Enter start   ? help   Esc back",
                 help_lines=HELP, show_help=help_)
    return cv


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
                        sel = (sel - 1) % 4
                    elif k in ("down", "s"):
                        sel = (sel + 1) % 4
                    elif k in ("left", "right", "a", "d") and sel < 3:
                        d = -1 if k in ("left", "a") else 1
                        lim = [len(PITS), len(SETS), 15][sel]
                        opts[sel] = (opts[sel] + d) % lim if sel < 2 else clamp(opts[sel] + d, 1, lim)
                    elif k in ("enter", " "):
                        go = True
            pit, si, level = PITS[opts[0]], opts[1], opts[2]
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
                        elif a == "resume":
                            g.paused = g.help = False
                        elif a == "quit":
                            back = True
                        elif a == "help":
                            g.help = not g.help
                            g.paused = True
                        elif a is None:
                            if k == "g":
                                ghost = not ghost
                            else:
                                g.key(k)
                    if g.over and record is None:
                        record = submit(GAME, mode_key(pit, si), g.score)
                    cols, rows = term.size()
                    if cols < 70 or rows < 24:
                        term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (70x24).")
                        time.sleep(0.2)
                        continue
                    cv = render(g, cols, rows, ghost)
                    if g.over:
                        render_over(g, cv, record)
                    term.write(cv.emit())
                    time.sleep(max(0, 1 / 30 - (time.time() - now)))
                if back:
                    break


if __name__ == "__main__":
    main()
