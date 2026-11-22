#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""STACKFALL - falling blocks in your terminal.

Seven four-block pieces fall into a well ten wide and twenty deep. Fill a row and it melts away; let the
stack reach the top and it is over. Three modes: Marathon (endless, ever faster), Sprint (40 rows against the
clock) and Rising (the floor keeps pushing up rubble).

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
"""
import math
import random
import sys
import time

from arcadekit import (PAUSE_LINES, Canvas, Terminal, clamp, draw_title, load_scores, mix, overlay, shade,
                       shared_key, submit, title_screen, title_width)
from arcadesound import Sound

W, H = 10, 20
HID = 2                  # spawn rows above the visible well
GAME = "stackfall"

# shapes in a 4x4 box (x, y down), the rotation centre, the colour
SHAPES = {
    "I": ([(0, 1), (1, 1), (2, 1), (3, 1)], (1.5, 1.5), (60, 206, 196)),
    "O": ([(1, 0), (2, 0), (1, 1), (2, 1)], (1.5, 0.5), (236, 192, 64)),
    "T": ([(0, 1), (1, 1), (2, 1), (1, 0)], (1.0, 1.0), (206, 92, 206)),
    "S": ([(0, 1), (1, 1), (1, 0), (2, 0)], (1.0, 1.0), (146, 212, 72)),
    "Z": ([(0, 0), (1, 0), (1, 1), (2, 1)], (1.0, 1.0), (240, 100, 90)),
    "J": ([(0, 0), (0, 1), (1, 1), (2, 1)], (1.0, 1.0), (100, 116, 236)),
    "L": ([(2, 0), (0, 1), (1, 1), (2, 1)], (1.0, 1.0), (244, 142, 52)),
}
ROT = {}
for _k, (_cells, (_cx, _cy), _c) in SHAPES.items():
    states = [_cells]
    for _ in range(3):  # turn clockwise about the centre (y points down)
        states.append([(int(round(_cx - (y - _cy))), int(round(_cy + (x - _cx)))) for x, y in states[-1]])
    ROT[_k] = states
KICKS = [(0, 0), (-1, 0), (1, 0), (0, -1), (-2, 0), (2, 0), (-1, -1), (1, -1), (0, 1)]
GARBAGE = (104, 108, 124)
MODES = [
    ("Marathon", "endless; every 10 rows it gets faster"),
    ("Sprint", "clear 40 rows as fast as you can"),
    ("Rising", "the floor keeps pushing up rubble rows"),
]
LINE_SCORE = [0, 100, 300, 500, 800]
SND = Sound(GAME, {
    # small and soft: these happen all the time
    "move": [dict(w="square", f=392, d=0.022, v=0.14, duty=0.25, r="lin")],
    "turn": [dict(w="tri", f=587, f2=740, d=0.03, v=0.24)],
    "soft": [dict(w="tri", f=262, d=0.018, v=0.12)],
    "hold": [dict(w="tri", f=494, d=0.03, v=0.22), dict(w="tri", f=740, d=0.04, v=0.2)],
    "lock": [dict(w="noise", f=700, f2=200, d=0.05, v=0.2), dict(w="tri", f=147, f2=110, d=0.06, v=0.28, at=0)],
    "slam": [dict(w="noise", f=2400, f2=150, d=0.14, v=0.36),
             dict(w="square", f=165, f2=55, d=0.14, v=0.26, duty=0.3, at=0)],
    # rows melting away: bigger the more rows go at once
    "clear1": [dict(w="tri", f=659, d=0.07, v=0.45), dict(w="tri", f=880, d=0.16, v=0.42)],
    "clear2": [dict(w="tri", f=659, d=0.06, v=0.45), dict(w="tri", f=784, d=0.06, v=0.45),
               dict(w="tri", f=988, d=0.2, v=0.42)],
    "clear3": [dict(w="square", f=523, d=0.06, v=0.32, duty=0.25), dict(w="square", f=659, d=0.06, v=0.32, duty=0.25),
               dict(w="square", f=784, d=0.06, v=0.32, duty=0.25), dict(w="tri", f=1047, d=0.26, v=0.45, vib=(7, 0.2)),
               dict(w="noise", f=6000, d=0.18, v=0.08, at=0.18)],
    "clear4": [dict(w="square", f=392, d=0.07, v=0.3, duty=0.25), dict(w="square", f=523, d=0.07, v=0.3, duty=0.25),
               dict(w="square", f=659, d=0.07, v=0.3, duty=0.25), dict(w="square", f=784, d=0.07, v=0.3, duty=0.25),
               dict(w="tri", f=1047, d=0.5, v=0.45, vib=(6, 0.25), r="lin"),
               dict(w="tri", f=659, d=0.5, v=0.3, at=0.28, r="lin"), dict(w="tri", f=784, d=0.5, v=0.25, at=0.28, r="lin"),
               dict(w="noise", f=7000, f2=3000, d=0.4, v=0.07, at=0.28)],
    "allclear": [dict(w="tri", f=f, d=0.05, v=0.36) for f in (784, 988, 1175, 1568, 1319, 1568, 1976)] +
                [dict(w="square", f=1568, d=0.55, v=0.28, duty=0.125, vib=(8, 0.3), r="lin")],
    "levelup": [dict(w="square", f=440, d=0.06, v=0.3, duty=0.25), dict(w="square", f=554, d=0.06, v=0.3, duty=0.25),
                dict(w="square", f=659, d=0.06, v=0.3, duty=0.25), dict(w="tri", f=880, d=0.28, v=0.4, vib=(6, 0.2))],
    "rise": [dict(w="noise", f=90, d=0.3, v=0.26, r="lin"), dict(w="tri", f=70, f2=52, d=0.3, v=0.3, at=0)],
    "over": [dict(w="tri", f=392, d=0.16, v=0.4), dict(w="tri", f=349, d=0.16, v=0.4), dict(w="tri", f=311, d=0.16, v=0.4),
             dict(w="tri", f=262, f2=196, d=0.6, v=0.42, r="lin")],
    "win": [dict(w="square", f=523, d=0.09, v=0.3, duty=0.25), dict(w="square", f=659, d=0.09, v=0.3, duty=0.25),
            dict(w="square", f=784, d=0.09, v=0.3, duty=0.25), dict(w="square", f=1047, d=0.18, v=0.3, duty=0.25),
            dict(w="square", f=784, d=0.09, v=0.3, duty=0.25), dict(w="tri", f=1047, d=0.5, v=0.45, vib=(6, 0.25), r="lin")],
    # menus
    "menu": [dict(w="tri", f=660, d=0.025, v=0.2)],
    "start": [dict(w="square", f=523, d=0.05, v=0.3, duty=0.25), dict(w="square", f=784, d=0.05, v=0.3, duty=0.25),
              dict(w="square", f=1047, d=0.14, v=0.32, duty=0.25)],
    "pause": [dict(w="tri", f=523, f2=392, d=0.07, v=0.22)],
    "sound_on": [dict(w="tri", f=440, d=0.06, v=0.35), dict(w="tri", f=880, d=0.12, v=0.35)],
})
HELP = [
    "STACKFALL - keys",
    "",
    "Left / Right  (A / D)    move",
    "Up, X  (W)               turn clockwise",
    "Z  (Y)                   turn back",
    "Down  (S)                drop faster",
    "Space                    slam down",
    "C / Tab                  hold the piece for later",
    "",
    "The outlined piece at the bottom shows where it will land.",
    "The well's frame turns red when the stack nears the top.",
    "",
    "Esc / P                  pause menu (Q quit, M sound)",
    "?                        this help",
]


class Stack:
    def __init__(self, mode, level=1):
        self.mode = mode
        self.board = [[None] * W for _ in range(H + HID)]
        self.bag = []
        self.queue = [self.draw() for _ in range(5)]
        self.hold = None
        self.held = False
        self.score = self.lines = 0
        self.start_level = self.level = level
        self.combo = -1
        self.t = 0.0
        self.fall = 0.0
        self.lock_at = None
        self.lock_moves = 0
        self.clearing = None
        self.trails = []
        self.over = self.won = False
        self.paused = self.help = False
        self.rise_t = 0.0
        self.pops = []          # floating texts: [text, t_end, colour]
        self.spawn()

    # --- pieces ----------------------------------------------------------------------------------
    def draw(self):
        if not self.bag:
            self.bag = list(SHAPES)
            random.shuffle(self.bag)
        return self.bag.pop()

    def cells(self, kind=None, rot=None, x=None, y=None):
        kind = self.kind if kind is None else kind
        rot = self.rot if rot is None else rot
        x = self.x if x is None else x
        y = self.y if y is None else y
        return [(x + cx, y + cy) for cx, cy in ROT[kind][rot % 4]]

    def fits(self, cells):
        b = self.board
        for x, y in cells:
            if x < 0 or x >= W or y >= H + HID or (y >= 0 and b[y][x] is not None):
                return False
        return True

    def spawn(self, kind=None):
        self.kind = kind or self.queue.pop(0)
        if kind is None:
            self.queue.append(self.draw())
        self.rot, self.x, self.y = 0, 3, HID - 1
        self.fall = 0.0
        self.lock_at = None
        self.lock_moves = 0
        if not self.fits(self.cells()):
            self.over = True

    def interval(self):
        return max(0.035, 0.85 * 0.84 ** (self.level - 1))

    def grounded(self):
        return not self.fits(self.cells(y=self.y + 1))

    def touched(self):
        """A move or turn while resting on the stack buys a little time (up to 15 times)."""
        if self.lock_at is not None and self.lock_moves < 15:
            self.lock_moves += 1
            self.lock_at = self.t + 0.5

    def move(self, dx):
        if self.fits(self.cells(x=self.x + dx)):
            self.x += dx
            self.touched()
            SND.play("move", gap=0.03)
            return True
        return False

    def turn(self, d):
        r = (self.rot + d) % 4
        for kx, ky in KICKS:
            if self.fits(self.cells(rot=r, x=self.x + kx, y=self.y + ky)):
                self.rot, self.x, self.y = r, self.x + kx, self.y + ky
                self.touched()
                SND.play("turn", gap=0.03)
                return True
        return False

    def soft(self):
        if self.fits(self.cells(y=self.y + 1)):
            self.y += 1
            self.score += 1
            self.fall = 0.0
            SND.play("soft", gap=0.05)

    def hard(self):
        y0 = self.y
        while self.fits(self.cells(y=self.y + 1)):
            self.y += 1
        self.score += 2 * (self.y - y0)
        if self.y > y0:
            cols = sorted({x for x, _ in self.cells()})
            for x in cols:
                top = min(y for cx, y in self.cells() if cx == x)
                self.trails.append((x, y0, top, SHAPES[self.kind][2], self.t + 0.15))
        self.lock(slam=True)

    def do_hold(self):
        if self.held:
            return
        self.held = True
        SND.play("hold")
        k = self.kind
        if self.hold is None:
            self.hold = k
            self.spawn()
        else:
            self.hold, nk = k, self.hold
            self.spawn(nk)

    def lock(self, slam=False):
        SND.play("slam" if slam else "lock")
        col = SHAPES[self.kind][2]
        cells = self.cells()
        for x, y in cells:
            if y >= 0:
                self.board[y][x] = col
        self.held = False
        if all(y < HID for _, y in cells):
            self.over = True
            return
        full = [y for y in range(H + HID) if all(c is not None for c in self.board[y])]
        if full:
            self.combo += 1
            n = len(full)
            pts = LINE_SCORE[min(n, 4)] * self.level + (50 * self.combo * self.level if self.combo > 0 else 0)
            if all(c is None for y, row in enumerate(self.board) if y not in full for c in row):
                pts += 1500 * self.level
                self.pops.append(["ALL CLEAR!", self.t + 1.6, (255, 255, 160)])
                SND.play("allclear")
            else:
                SND.play("clear%d" % min(n, 4))
            self.score += pts
            self.pops.append([["", "", "DOUBLE", "TRIPLE", "QUAD STACK!"][min(n, 4)] or "+%d" % pts,
                              self.t + 1.1, col])
            if self.combo > 0:
                self.pops.append(["combo x%d" % self.combo, self.t + 1.1, (255, 220, 120)])
            self.clearing = (full, self.t + 0.22)
        else:
            self.combo = -1
            self.spawn()

    def finish_clear(self):
        rows, _ = self.clearing
        self.clearing = None
        for y in sorted(rows):
            del self.board[y]
            self.board.insert(0, [None] * W)
        self.lines += len(rows)
        if self.mode == "Sprint" and self.lines >= 40:
            self.won = self.over = True
            return
        if self.mode != "Sprint":
            lv = self.level
            self.level = max(self.level, self.start_level + self.lines // 10)
            if self.level > lv:
                SND.play("levelup")
        self.spawn()

    def rise(self):
        """Push a rubble row with one gap up from the bottom."""
        if any(c is not None for c in self.board[0]):
            self.over = True
            return
        gap = random.randrange(W)
        SND.play("rise")
        del self.board[0]
        self.board.append([None if x == gap else GARBAGE for x in range(W)])
        if not self.fits(self.cells()):
            self.y -= 1

    # --- time --------------------------------------------------------------------------------------
    def update(self, dt):
        if self.over or self.paused:
            return
        self.t += dt
        self.trails = [t for t in self.trails if t[4] > self.t]
        self.pops = [p for p in self.pops if p[1] > self.t]
        if self.clearing:
            if self.t >= self.clearing[1]:
                self.finish_clear()
            return
        if self.mode == "Rising":
            self.rise_t += dt
            every = max(2.5, 9.0 - (self.level - 1) * 0.6)
            if self.rise_t >= every:
                self.rise_t = 0.0
                self.rise()
                if self.over:
                    return
            lv = self.level
            self.level = max(self.level, self.start_level + int(self.t // 45))
            if self.level > lv:
                SND.play("levelup")
        self.fall += dt
        iv = self.interval()
        while self.fall >= iv and not self.grounded():
            self.fall -= iv
            self.y += 1
        if self.grounded():
            self.fall = 0.0
            if self.lock_at is None:
                self.lock_at = self.t + 0.5
            elif self.t >= self.lock_at:
                self.lock()
        else:
            self.lock_at = None

    def key(self, k):
        if self.over or self.paused or self.clearing:
            return
        if k in ("left", "a"):
            self.move(-1)
        elif k in ("right", "d"):
            self.move(1)
        elif k in ("down", "s"):
            self.soft()
        elif k in ("up", "x", "w"):
            self.turn(1)
        elif k in ("z", "y"):
            self.turn(-1)
        elif k == " ":
            self.hard()
        elif k in ("c", "tab"):
            self.do_hold()


# =============================================================================================
# Drawing
# =============================================================================================
def block(cv, x, y, k, c, ghost=False):
    if ghost:   # where the piece will land: a light fill and a clear coloured outline
        cv.rect(x, y, k, k, mix((14, 15, 26), c, 0.22))
        cv.frame(x, y, k, k, shade(c, 0.95))
        return
    if k <= 2:
        cv.rect(x, y, k, k, c)
        cv.set(x, y, shade(c, 1.25))
        return
    cv.rect(x, y, k, k, shade(c, 0.6))              # dark bottom / right edge
    cv.rect(x, y, k - 1, k - 1, shade(c, 1.3))      # light top / left edge
    cv.rect(x + 1, y + 1, k - 2, k - 2, c)
    if k >= 5:
        cv.set(x + 1, y + 1, shade(c, 1.5))


def mini(cv, kind, x, y, k, dim=False):
    """A piece preview centred in a 4k x 2k box."""
    cells = ROT[kind][0]
    xs, ys = [c[0] for c in cells], [c[1] for c in cells]
    w, h = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
    ox, oy = x + (4 - w) * k / 2 - min(xs) * k, y + (2 - h) * k / 2 - min(ys) * k
    col = SHAPES[kind][2]
    if dim:
        col = mix(col, (60, 60, 70), 0.6)
    for cx, cy in cells:
        block(cv, int(ox + cx * k), int(oy + cy * k), k, col)


def fmt_time(t):
    return "%d:%05.2f" % (t // 60, t % 60)


def render(g, cols, rows):
    cv = Canvas(cols, rows)
    cv.vgradient((10, 10, 22), (22, 14, 30))
    PH = rows * 2
    K = clamp(min((PH - 6) // H, (cols - 44) // W), 2, 8)
    KP = max(2, K * 2 // 3)
    bw, bh = W * K, H * K
    bx = (cols - bw) // 2
    by = ((PH - bh) // 2) & ~1
    # the well; its frame pulses red when the stack gets close to the top
    top = next((y for y in range(H + HID) if any(c is not None for c in g.board[y])), H + HID)
    danger = clamp((HID + 5 - top) / 5, 0, 1) if not g.over else 0
    frame = mix((64, 72, 112), (230, 60, 60), danger * (0.6 + 0.4 * math.sin(g.t * 8)))
    cv.rect(bx - 2, by - 2, bw + 4, bh + 4, frame)
    cv.rect(bx - 1, by - 1, bw + 2, bh + 2, (30, 34, 58))
    cv.rect(bx, by, bw, bh, (14, 15, 26))
    for gy in range(1, H):
        for gx in range(1, W):
            cv.set(bx + gx * K, by + gy * K, (30, 33, 52))
    flash = g.clearing[0] if g.clearing else ()
    for y in range(HID, H + HID):
        for x in range(W):
            c = g.board[y][x]
            if c is not None:
                if y in flash:
                    c = mix(c, (255, 255, 255), 0.75 if int(g.t * 30) % 2 else 0.4)
                if g.over and not g.won:
                    c = mix(c, (70, 70, 80), 0.7)
                block(cv, bx + x * K, by + (y - HID) * K, K, c)
    for x, y0, y1, c, _ in g.trails:
        for y in range(max(HID, y0), y1):
            cv.rect(bx + x * K + K // 3, by + (y - HID) * K, max(1, K // 3), K, mix(c, (14, 15, 26), 0.6))
    if not g.over and not g.clearing:
        col = SHAPES[g.kind][2]
        gy = g.y
        while g.fits(g.cells(y=gy + 1)):
            gy += 1
        for x, y in g.cells(y=gy):
            if y >= HID:
                block(cv, bx + x * K, by + (y - HID) * K, K, col, ghost=True)
        for x, y in g.cells():
            if y >= HID:
                block(cv, bx + x * K, by + (y - HID) * K, K, col)
    # side panels
    lx = max(1, bx - 4 * KP - 6)
    rx = bx + bw + 5
    row = by // 2
    cv.put(lx, row, "HOLD", (170, 176, 210))
    if g.hold:
        mini(cv, g.hold, lx, by + 3, KP, dim=g.held)
    cv.put(rx, row, "NEXT", (170, 176, 210))
    for i, kind in enumerate(g.queue[:3]):          # three is plenty, and calmer than five
        mini(cv, kind, rx, by + 3 + i * (2 * KP + 4), KP if i == 0 else max(2, KP - 1), dim=i > 0)
    srow = row + (2 * KP + 8) // 2
    stats = [("MODE", g.mode), ("SCORE", "%d" % g.score), ("ROWS", "%d%s" % (g.lines, "/40" if g.mode == "Sprint" else "")),
             ("LEVEL", "%d" % g.level), ("TIME", fmt_time(g.t))]
    rec = load_scores().get(GAME, {}).get(g.mode)
    if rec is not None:
        stats.append(("BEST", fmt_time(rec) if g.mode == "Sprint" else "%d" % rec))
    sx = max(1, min(lx, bx - 14))
    for i, (a, b) in enumerate(stats):
        cv.put(sx, srow + i * 2, a, (130, 136, 170))
        cv.put(sx, srow + i * 2 + 1, b, (240, 240, 250))
    # floating texts over the well
    for i, (txt, until, c) in enumerate(reversed(g.pops[-3:])):
        r = by // 2 + H * K // 4 - 2 + i * 2 - int((1 - (until - g.t)) * 2)
        cv.center(r, " %s " % txt, (14, 14, 20), c, bx, bw)
    if g.paused:
        overlay(cv, HELP if g.help else PAUSE_LINES + ["", SND.label()])
    cv.put(0, rows - 1, " <- -> move  Up/X turn  Z turn back  Down drop  Space slam  C hold  Esc menu  ? help "
           [:cols], (140, 144, 170), (12, 12, 22))
    return cv


def render_over(g, cv, record):
    lines = ["SPRINT DONE!" if g.won else "GAME OVER", ""]
    if g.mode == "Sprint" and g.won:
        lines.append("time  %s" % fmt_time(g.t))
    else:
        lines.append("score %d" % g.score)
    lines.append("rows  %d   level %d" % (g.lines, g.level))
    if record:
        lines += ["", "** NEW RECORD **"]
    lines += ["", "Enter: again   Esc / Q: menu"]
    w = max(len(l) for l in lines) + 4
    cv.box(max(0, (cv.cols - w) // 2), max(0, cv.rows // 2 - len(lines) // 2 - 1), [l.center(w - 4) for l in lines],
           (240, 240, 246), (24, 22, 44))


def render_menu(cols, rows, sel, level, t, help_=False):
    cv = Canvas(cols, rows)
    cv.vgradient((10, 10, 22), (26, 14, 34))
    rnd = random.Random(7)
    cols_ = [c for _, _, c in SHAPES.values()]
    for i in range(46):  # slowly falling blocks behind the menu
        x = rnd.randrange(cols)
        sp = rnd.uniform(4, 12)
        y = int((rnd.uniform(0, cv.H) + t * sp) % (cv.H + 8)) - 4
        block(cv, x, y, 3, mix(rnd.choice(cols_), (16, 12, 28), 0.3))
    rec = load_scores().get(GAME, {})
    name = MODES[sel][0]
    r = rec.get(name)
    best = None if r is None else "best %s: %s" % (name, fmt_time(r) if name == "Sprint" else r)
    items = ["%-9s %s" % m for m in MODES]
    title_screen(cv, "STACKFALL", "falling blocks, ten wide, twenty deep", items, sel, best,
                 extra=["", "start level   < %d >" % level],
                 keys="Up/Down mode   Left/Right level   Enter start   M %s   ? help   Esc back" % SND.label().lower(),
                 help_lines=HELP, show_help=help_)
    return cv


def main():
    with Terminal() as term:
        sel, level = 0, 1
        help_ = False
        while True:
            # menu
            t0 = time.time()
            go = False
            while not go:
                cols, rows = term.size()
                term.write(render_menu(cols, rows, sel, level, time.time() - t0, help_).emit())
                for k in term.keys(1 / 20):
                    if help_:            # any key closes the help
                        help_ = False
                        continue
                    if k == "?":
                        help_ = True
                    elif k in ("q", "esc"):
                        return
                    if k in ("up", "w"):
                        sel = (sel - 1) % len(MODES)
                        SND.play("menu")
                    elif k in ("down", "s"):
                        sel = (sel + 1) % len(MODES)
                        SND.play("menu")
                    elif k in ("left", "a"):
                        level = max(1, level - 1)
                        SND.play("menu")
                    elif k in ("right", "d"):
                        level = min(15, level + 1)
                        SND.play("menu")
                    elif k == "m":
                        if SND.toggle():
                            SND.play("sound_on")
                    elif k in ("enter", " "):
                        SND.play("start")
                        go = True
            # play
            while True:
                g = Stack(MODES[sel][0], level)
                last = time.time()
                record = None
                back = again = False
                while True:
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
                        a = shared_key(k, g.paused)
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
                            g.key(k)
                    if back or again:
                        break
                    if g.over and record is None:
                        SND.play("win" if g.won else "over")
                        if g.mode == "Sprint":
                            record = g.won and submit(GAME, g.mode, round(g.t, 2), lower_is_better=True)
                        else:
                            record = submit(GAME, g.mode, g.score)
                    cols, rows = term.size()
                    if cols < 40 or rows < 20:
                        term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (40x20).")
                        time.sleep(0.2)
                        continue
                    cv = render(g, cols, rows)
                    if g.over:
                        render_over(g, cv, record)
                    term.write(cv.emit())
                    time.sleep(max(0, 1 / 60 - (time.time() - now)))
                if back:
                    break


if __name__ == "__main__":
    main()
