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

from arcadekit import (PAUSE_LINES, Canvas, Terminal, clamp, draw_title, footer, load_scores, mix, overlay, shade,
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
        self.slam_t = 0.0
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
        self.slam_t = self.t
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
            name = ["", "", "DOUBLE", "TRIPLE", "QUAD STACK!"][min(n, 4)]
            # the newest text is drawn on top, so add them bottom-up: combo, points, name
            if self.combo > 0:
                self.pops.append(["combo x%d" % self.combo, self.t + 1.1, (255, 220, 120)])
            self.pops.append(["+%d" % pts, self.t + 1.1, (240, 240, 250) if name else col])
            if name:
                self.pops.append([name, self.t + 1.1, col])
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
WELL_BG = (17, 19, 34)        # the well is a shade lighter than the room, so it reads as the play area
WELL_LANE = (20, 22, 39)      # every other column a touch lighter: easy to count columns when aiming
PANEL_BODY = (15, 16, 30)
PANEL_HEAD = (30, 32, 58)
PANEL_EDGE = (48, 52, 88)
LABEL = (138, 144, 182)       # dim labels, bright values (both above 4.5:1 on the panel)
VALUE = (240, 240, 250)
SCORE_C = (250, 214, 120)


def block(cv, x, y, k, c):
    if k <= 2:
        cv.rect(x, y, k, k, c)
        cv.set(x, y, shade(c, 1.25))
        return
    cv.rect(x, y, k, k, shade(c, 0.6))              # dark bottom / right edge
    cv.rect(x, y, k - 1, k - 1, shade(c, 1.3))      # light top / left edge
    cv.rect(x + 1, y + 1, k - 2, k - 2, c)
    if k >= 5:
        cv.set(x + 1, y + 1, shade(c, 1.5))


def ghost(cv, cells, bx, by, k, c):
    """Where the piece will land: a faint fill with one outline around the whole shape (never mistaken for a
    real block, at any size)."""
    occ = set(cells)
    if k <= 2:   # too small for an outline: a dim, flat shadow of the piece
        for x, y in cells:
            cv.rect(bx + x * k, by + (y - HID) * k, k, k, mix(WELL_BG, c, 0.34))
        return
    fill, edge = mix(WELL_BG, c, 0.16), shade(c, 0.95)
    for x, y in cells:
        px, py = bx + x * k, by + (y - HID) * k
        cv.rect(px, py, k, k, fill)
        if (x - 1, y) not in occ:
            cv.rect(px, py, 1, k, edge)
        if (x + 1, y) not in occ:
            cv.rect(px + k - 1, py, 1, k, edge)
        if (x, y - 1) not in occ:
            cv.rect(px, py, k, 1, edge)
        if (x, y + 1) not in occ:
            cv.rect(px, py + k - 1, k, 1, edge)


def mini(cv, kind, x, y, k, dim=0.0):
    """A piece preview centred in a 4k x 2k box; dim fades it into the panel."""
    cells = ROT[kind][0]
    xs, ys = [c[0] for c in cells], [c[1] for c in cells]
    w, h = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
    ox, oy = x + (4 - w) * k / 2 - min(xs) * k, y + (2 - h) * k / 2 - min(ys) * k
    col = mix(SHAPES[kind][2], PANEL_BODY, dim)
    for cx, cy in cells:
        block(cv, int(ox + cx * k), int(oy + cy * k), k, col)


def panel(cv, col, row, w, h, title=None, title_fg=LABEL):
    """A framed box in character cells, with an optional header strip."""
    cv.rect(col, row * 2, w, h * 2, PANEL_BODY)
    cv.frame(col, row * 2, w, h * 2, PANEL_EDGE)
    if title:
        cv.put(col + 1, row, (" " + title).ljust(w - 2)[:w - 2], title_fg, PANEL_HEAD)


def stat(cv, col, row, w, label, value, fg=VALUE):
    """One HUD line inside a panel: the label dim on the left, the value bright and right-aligned."""
    value = value[:w - 3]
    room = w - 5 - len(value)                    # the label gives way first when the panel is narrow
    cv.put(col + 1, row, (" " + label[:max(0, room)]).ljust(w - 2)[:w - 2], LABEL, PANEL_BODY)
    cv.put(col + w - 2 - len(value), row, value, fg, PANEL_BODY)


def fmt_time(t):
    return "%d:%05.2f" % (t // 60, t % 60)


def render(g, cols, rows):
    cv = Canvas(cols, rows)
    cv.vgradient((8, 8, 18), (18, 12, 26))
    PH = (rows - 1) * 2                               # the footer bar keeps the last row
    K = clamp(min((PH - 4) // H, (cols - 44) // W), 2, 8)
    fw = 2 if PH - H * K >= 4 else 1                  # frame thickness; thin when the well only just fits
    bw, bh = W * K, H * K
    bx = (cols - bw) // 2
    by = (PH - bh) // 2
    if g.slam_t and g.t - g.slam_t < 0.07:            # a hard drop nudges the well
        by += 1
    # danger: how close the stack is to the top (0 calm .. 1 about to top out)
    top = next((y for y in range(H + HID) if any(c is not None for c in g.board[y])), H + HID)
    danger = clamp((HID + 6 - top) / 6, 0, 1) if not g.over else 0
    pulse = 0.6 + 0.4 * math.sin(g.t * 8)
    frame = mix((70, 78, 122), (236, 64, 64), danger * pulse)
    cv.rect(bx - fw, by - fw, bw + 2 * fw, bh + 2 * fw, frame)
    if fw == 2:
        cv.rect(bx - 1, by - 1, bw + 2, bh + 2, mix((34, 38, 64), (90, 26, 34), danger))
    for x in range(W):
        cv.rect(bx + x * K, by, K, bh, WELL_LANE if x % 2 else WELL_BG)
    if danger > 0:   # the top rows glow red as the stack climbs into them
        for i in range(4):
            a = danger * (0.30 - i * 0.06) * pulse
            for x in range(W):
                cv.rect(bx + x * K, by + i * K, K, K, mix(WELL_LANE if x % 2 else WELL_BG, (200, 40, 48), a))
    clear_rows, clear_p = (), 0.0
    if g.clearing:
        clear_rows = g.clearing[0]
        clear_p = clamp(1 - (g.clearing[1] - g.t) / 0.22, 0, 1)
    for y in range(HID, H + HID):
        for x in range(W):
            c = g.board[y][x]
            if c is None:
                continue
            if y in clear_rows:   # a white wipe runs out from the middle, then the row is gone
                d = abs(x + 0.5 - W / 2) / (W / 2)
                c = (255, 255, 255) if d <= clear_p * 1.15 else mix(c, (255, 255, 255), 0.45)
            elif g.over and not g.won:
                c = mix(c, (70, 70, 80), 0.7)
            block(cv, bx + x * K, by + (y - HID) * K, K, c)
    for y in clear_rows:          # the frame lights up beside each row that clears
        if y >= HID:
            glow = mix(frame, (255, 255, 255), 1 - clear_p * 0.6)
            cv.rect(bx - fw, by + (y - HID) * K, fw, K, glow)
            cv.rect(bx + bw, by + (y - HID) * K, fw, K, glow)
    for x, y0, y1, c, _ in g.trails:
        for y in range(max(HID, y0), y1):
            cv.rect(bx + x * K + K // 3, by + (y - HID) * K, max(1, K // 3), K, mix(c, WELL_BG, 0.6))
    if not g.over and not g.clearing:
        col = SHAPES[g.kind][2]
        gy = g.y
        while g.fits(g.cells(y=gy + 1)):
            gy += 1
        if gy > g.y:
            ghost(cv, [(x, y) for x, y in g.cells(y=gy) if y >= HID], bx, by, K, col)
        for x, y in g.cells():
            if y >= HID:
                block(cv, bx + x * K, by + (y - HID) * K, K, col)
    # --- side panels: HOLD + stats on the left, NEXT on the right, each in its own frame ----------------
    gap = 2 + fw
    LW = min(clamp(bx - gap - 2, 12, 24), bx - gap)              # never over the well, even when narrow
    lx = max(0, bx - gap - LW)
    RW = min(clamp(cols - (bx + bw + gap) - 2, 12, 24), cols - (bx + bw + gap))
    rx = bx + bw + gap
    KP = clamp(min(K, (min(LW, RW) - 4) // 4), 2, 6)
    r0 = max(0, by // 2)
    hh = KP + 2
    panel(cv, lx, r0, LW, hh, "HOLD" if not g.held else "HOLD  (used)", LABEL if not g.held else (110, 114, 146))
    if g.hold:
        mini(cv, g.hold, lx + (LW - 4 * KP) // 2, (r0 + 1) * 2 + 1, KP, dim=0.6 if g.held else 0.0)
    # stats: score first and in gold; a bar shows how close the next level (or the Sprint goal) is
    rec = load_scores().get(GAME, {}).get(g.mode)
    sprint = g.mode == "Sprint"
    if sprint:
        lines = [("TIME", fmt_time(g.t), SCORE_C), ("ROWS", "%d/40" % g.lines, VALUE), None,
                 ("SCORE", "%d" % g.score, VALUE)]
    else:
        lines = [("SCORE", "%d" % g.score, SCORE_C), ("LEVEL", "%d" % g.level, VALUE), None,
                 ("ROWS", "%d" % g.lines, VALUE), ("TIME", fmt_time(g.t), VALUE)]
    if rec is not None:
        lines.append(("BEST", fmt_time(rec) if sprint else "%d" % rec, (196, 182, 124)))
    sr = r0 + hh + 1
    sh = len(lines) + 2
    if sr + sh > rows - 1:                          # tight terminal: tuck the stats right under HOLD
        sr = r0 + hh
    panel(cv, lx, sr, LW, sh, g.mode.upper(), (200, 204, 232))
    for i, ln in enumerate(lines):
        r = sr + 1 + i
        if ln is None:   # a bar: rows towards the next level (Marathon / Rising) or towards 40 (Sprint)
            frac = g.lines / 40 if sprint else (g.lines % 10) / 10
            n = LW - 4
            cv.rect(lx + 2, r * 2, n, 1, (38, 42, 70))
            cv.rect(lx + 2, r * 2, int(round(n * clamp(frac, 0, 1))), 1, (90, 190, 230) if sprint else (110, 204, 120))
        else:
            stat(cv, lx, r, LW, *ln)
    # NEXT: the coming piece full size, two more after it smaller and faded
    KS = max(2, KP - 1)
    nh = 1 + (KP + 1) + 2 * (KS + 1) + 1
    panel(cv, rx, r0, RW, nh, "NEXT")
    y = (r0 + 1) * 2 + 1
    for i, kind in enumerate(g.queue[:3]):          # three is plenty, and calmer than five
        k = KP if i == 0 else KS
        mini(cv, kind, rx + (RW - 4 * k) // 2, y, k, dim=0.0 if i == 0 else 0.35 + 0.1 * i)
        y += 2 * k + 2
    # floating texts over the well, with a dark backing so they always read
    for i, (txt, until, c) in enumerate(reversed(g.pops[-3:])):
        r = by // 2 + H * K // 4 - 2 + i * 2 - int((1 - (until - g.t)) * 2)
        cv.center(r, "  %s  " % txt, (14, 14, 20), c, bx, bw)
    if g.paused:
        overlay(cv, HELP if g.help else PAUSE_LINES + ["", SND.label()])
    footer(cv, "<- -> move  Up turn  Space slam  C hold  ? help")
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
    x, y = max(0, (cv.cols - w) // 2), max(0, cv.rows // 2 - len(lines) // 2 - 1)
    edge = SCORE_C if record else (110, 204, 120) if g.won else (200, 76, 86)
    cv.frame(x - 1, y * 2 - 1, w + 2, (len(lines) + 2) * 2 + 2, edge)   # a coloured rim lifts it off the well
    cv.box(x, y, [l.center(w - 4) for l in lines], (240, 240, 246), (24, 22, 44))


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
