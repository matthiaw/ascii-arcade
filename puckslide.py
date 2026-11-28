#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""PUCKSLIDE - air hockey on a glowing table, for two at one keyboard or one against the computer.

A puck floats on an air cushion; two mallets guard two goals. The physics is real: the puck and the mallets have
mass, collisions are elastic with a little loss, the walls bounce, the cushion slows the puck only a touch, and a
mallet in motion hands its speed to the puck - a hard swing makes a hard shot. Each player stays in their half.
First to 7 (or 5, or 11) wins.

Left player: W A S D. Right player: the arrow keys. Against the computer you play left with either set, or with
the mouse. Over the LAN (or WLAN) one player hosts and plays left, the other joins from their own computer and
plays right, with either set of keys. In terminals with the kitty keyboard protocol (kitty, WezTerm, Ghostty, recent iTerm2) held keys are
exact; elsewhere every tap gives the mallet a shove and it glides, so two players can still play at once.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
Run:        python3 puckslide.py
Self-test:  python3 puckslide.py --selftest
"""
import math
import random
import sys
import time
from collections import deque

from arcadekit import (AUTO_LABEL, MOUSE_RE, PAUSE_LINES, AutoMode, Canvas, HeldKeys, KeyTerminal, clamp, draw_title,
                       load_scores, mix, overlay, shade, shared_key, submit, title_screen, title_width)
from arcadesound import Sound
import arcadenet

GAME = "puckslide"
TL, TW = 2.0, 1.0          # table length (x) and width (y), in table units
GOAL = (0.34, 0.66)        # the goal mouths in the short walls (y range)
PR, MR = 0.034, 0.062      # puck and mallet radius
PM, MM = 1.0, 6.0          # puck and mallet mass
E_WALL, E_HIT = 0.9, 0.92  # restitution: walls, puck against mallet
CUSHION = 0.22             # air-cushion damping of the puck, per second
PUCK_MAX = 7.0             # puck speed cap
M_MAX, M_ACC = 2.6, 30.0   # mallet top speed and acceleration
TARGETS = [5, 7, 11]
DIFFS = ["easy", "normal", "hard"]
AI = {  # reaction delay (s), top speed, aiming error, how far it comes out to attack
    "easy": dict(delay=0.3, speed=1.2, err=0.2, reach=0.5, acc=12.0),
    "normal": dict(delay=0.14, speed=2.0, err=0.08, reach=0.75, acc=22.0),
    "hard": dict(delay=0.07, speed=2.6, err=0.03, reach=0.92, acc=30.0),
}
COLS = [(255, 120, 70), (70, 220, 255)]
NAMES = ["LEFT", "RIGHT"]
P1_KEYS = {"w": (0, -1), "s": (0, 1), "a": (-1, 0), "d": (1, 0)}
P2_KEYS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
HUD_BG, HUD_FG = (12, 12, 22), (226, 226, 236)
SND = Sound(GAME, {
    "hit": [dict(w="noise", f=3000, f2=900, d=0.04, v=0.3), dict(w="tri", f=520, f2=380, d=0.05, v=0.3, at=0)],
    "smash": [dict(w="noise", f=5000, f2=600, d=0.08, v=0.5), dict(w="square", f=330, f2=160, d=0.07, v=0.3,
                                                                   duty=0.3, at=0)],
    "wall": [dict(w="tri", f=900, f2=700, d=0.04, v=0.2), dict(w="noise", f=2500, d=0.02, v=0.12, at=0)],
    "goal": [dict(w="square", f=f, d=0.07, v=0.28, duty=0.25) for f in (523, 659, 784, 1047)] +
            [dict(w="noise", f=1500, f2=400, d=0.5, v=0.25, at=0.05, r="lin")],
    "faceoff": [dict(w="tri", f=880, d=0.05, v=0.24), dict(w="tri", f=1320, d=0.09, v=0.24)],
    "win": [dict(w="square", f=f, d=0.09, v=0.28, duty=0.25) for f in (523, 659, 784, 1047, 784)] +
           [dict(w="tri", f=1047, d=0.5, v=0.42, vib=(6, 0.25), r="lin")],
    "lose": [dict(w="tri", f=392, d=0.18, v=0.35), dict(w="tri", f=330, d=0.18, v=0.35),
             dict(w="tri", f=262, d=0.45, v=0.35, r="lin")],
    "menu": [dict(w="tri", f=660, d=0.025, v=0.2)],
    "start": [dict(w="square", f=523, d=0.05, v=0.3, duty=0.25), dict(w="square", f=784, d=0.12, v=0.3, duty=0.25)],
    "pause": [dict(w="tri", f=523, f2=392, d=0.07, v=0.22)],
    "sound_on": [dict(w="tri", f=440, d=0.06, v=0.35), dict(w="tri", f=880, d=0.12, v=0.35)],
})


def help_lines(kitty=True):
    return [
        "PUCKSLIDE - keys",
        "",
        "W A S D               left mallet",
        "Arrow keys            right mallet",
        "Mouse                 left mallet (against the computer)",
        "Esc / P               pause     ? help",
        "",
        "Keys: held keys steer exactly (kitty protocol)." if kitty else
        "Keys: classic terminal - every tap shoves the mallet,",
        "" if kitty else "and it glides. Tap often; both players at once work.",
        "Hit the puck while moving: your speed goes into the shot.",
        "Against the computer W A S D and the arrows both steer you.",
        "LAN game: the host plays left, the one who joins plays right;",
        "both steer with either set of keys.",
    ]


# =============================================================================================
# The physics
# =============================================================================================
class Body:
    def __init__(self, x, y, r, m):
        self.x, self.y, self.r, self.m = x, y, r, m
        self.vx = self.vy = 0.0

    @property
    def speed(self):
        return math.hypot(self.vx, self.vy)


def collide(a, b, e):
    """Two discs: push them apart (by mass) and exchange an impulse along the line of centres. Returns the
    closing speed, or 0 when they do not touch or already move apart."""
    dx, dy = b.x - a.x, b.y - a.y
    d = math.hypot(dx, dy)
    rr = a.r + b.r
    if d >= rr or d < 1e-12:
        return 0.0
    nx, ny = dx / d, dy / d
    ia, ib = 1 / a.m, 1 / b.m
    over = rr - d
    a.x -= nx * over * ia / (ia + ib)
    a.y -= ny * over * ia / (ia + ib)
    b.x += nx * over * ib / (ia + ib)
    b.y += ny * over * ib / (ia + ib)
    vn = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny
    if vn >= 0:
        return 0.0
    j = -(1 + e) * vn / (ia + ib)
    a.vx -= j * nx * ia
    a.vy -= j * ny * ia
    b.vx += j * nx * ib
    b.vy += j * ny * ib
    return -vn


class Match:
    def __init__(self, ai=(None, None), target=7, seed=None, demo=False):
        self.ai = list(ai)                       # per side: None (human) or a difficulty name
        self.target = target
        self.rnd = random.Random(seed)
        self.demo = demo
        self.puck = Body(TL / 2, TW / 2, PR, PM)
        self.mallets = [Body(0.25, TW / 2, MR, MM), Body(TL - 0.25, TW / 2, MR, MM)]
        self.score = [0, 0]
        self.t = 0.0
        self.state, self.state_t = "faceoff", 0.9     # faceoff, play, goal, over
        self.scorer = None
        self.winner = None
        self.trail = deque(maxlen=10)
        self.flashes = []                        # [x, y, age, colour]
        self.pops = []
        self.walls = 0
        self.hits = [0, 0]
        self.paused = self.help = False
        self.inp = [(0.0, 0.0), (0.0, 0.0)]      # wanted direction per side (-1..1)
        self.mouse = [None, None]                # wanted position per side (pointer), or None
        self.brains = [Brain(self, s, d, self.rnd) if d else None for s, d in enumerate(self.ai)]
        self.faceoff(self.rnd.choice((0, 1)), first=True)

    def sfx(self, name, vol=1.0):
        if not self.demo:
            SND.play(name, vol=vol)

    def faceoff(self, side, first=False):
        """The puck rests in front of the side that conceded (the centre at the start)."""
        p = self.puck
        p.x = TL / 2 if first else (TL * 0.3 if side == 0 else TL * 0.7)
        p.y = TW / 2 + self.rnd.uniform(-0.15, 0.15)
        p.vx = p.vy = 0.0
        for s, m in enumerate(self.mallets):
            m.x, m.y = (0.22 if s == 0 else TL - 0.22), TW / 2
            m.vx = m.vy = 0.0
        self.trail.clear()
        self.state, self.state_t = "faceoff", 0.8

    # --- one frame -----------------------------------------------------------------------------
    def update(self, dt):
        if self.paused or self.state == "over":
            self.t += 0 if self.paused else dt
            self.state_t -= 0 if self.paused else dt
            return
        self.t += dt
        self.state_t -= dt
        for f in self.flashes:
            f[2] += dt
        self.flashes = [f for f in self.flashes if f[2] < 0.3]
        self.pops = [p for p in self.pops if p[2] > self.t]
        if self.state == "goal":
            if self.state_t <= 0:
                if max(self.score) >= self.target:
                    self.state = "over"
                    self.winner = 0 if self.score[0] > self.score[1] else 1
                    self.state_t = 0.0
                    human = [s for s in (0, 1) if self.ai[s] is None]
                    self.sfx("lose" if human and self.winner not in human else "win")
                else:
                    self.faceoff(1 - self.scorer)
            return
        if self.state == "faceoff" and self.state_t <= 0:
            self.state = "play"
            self.sfx("faceoff", 0.7)
        for s in (0, 1):
            if self.brains[s]:
                self.brains[s].update(dt)
        n = max(4, int(math.ceil((self.puck.speed + M_MAX) * dt / (PR * 0.45))))
        h = dt / n
        for _ in range(n):
            self.substep(h)
            if self.state == "goal":
                break
        self.trail.append((self.puck.x, self.puck.y))

    def drive(self, s, m, h):
        """A mallet follows its player: a pointer to chase, or a direction to accelerate in."""
        top, acc = M_MAX, M_ACC
        if self.brains[s]:
            top, acc = self.brains[s].p["speed"], self.brains[s].p["acc"]
        tgt = self.mouse[s]
        if tgt is not None:
            wx, wy = (tgt[0] - m.x) * 14, (tgt[1] - m.y) * 14
            sp = math.hypot(wx, wy)
            if sp > top * 1.25:
                wx, wy = wx / sp * top * 1.25, wy / sp * top * 1.25
        else:
            ix, iy = self.inp[s]
            wx, wy = ix * top, iy * top
        dvx, dvy = wx - m.vx, wy - m.vy
        dv = math.hypot(dvx, dvy)
        step = acc * h
        if dv > step:
            dvx, dvy = dvx / dv * step, dvy / dv * step
        m.vx += dvx
        m.vy += dvy
        sp = m.speed
        lim = top * (1.25 if tgt is not None else 1.0) + 0.6
        if sp > lim:                             # (a hit can briefly push it faster; it settles)
            m.vx, m.vy = m.vx / sp * lim, m.vy / sp * lim

    def confine(self, s, m):
        x0, x1 = (MR, TL / 2 - MR) if s == 0 else (TL / 2 + MR, TL - MR)
        if m.x < x0:
            m.x, m.vx = x0, max(0.0, m.vx)
        elif m.x > x1:
            m.x, m.vx = x1, min(0.0, m.vx)
        if m.y < MR:
            m.y, m.vy = MR, max(0.0, m.vy)
        elif m.y > TW - MR:
            m.y, m.vy = TW - MR, min(0.0, m.vy)

    def substep(self, h):
        p = self.puck
        for s, m in enumerate(self.mallets):
            if self.state == "play":
                self.drive(s, m, h)
            else:
                m.vx *= 0.9
                m.vy *= 0.9
            m.x += m.vx * h
            m.y += m.vy * h
            self.confine(s, m)
        k = math.exp(-CUSHION * h)
        p.vx *= k
        p.vy *= k
        p.x += p.vx * h
        p.y += p.vy * h
        for s, m in enumerate(self.mallets):
            v = collide(m, p, E_HIT)
            if v > 0:
                self.confine(s, m)
                self.hits[s] += 1
                self.flashes.append([p.x, p.y, 0.0, COLS[s]])
                self.sfx("smash" if v > 3.0 else "hit", min(1.0, 0.4 + v / 5))
        sp = p.speed
        if sp > PUCK_MAX:
            p.vx, p.vy = p.vx / sp * PUCK_MAX, p.vy / sp * PUCK_MAX
        self.walls_puck()

    def walls_puck(self):
        p = self.puck
        bounced = False
        in_mouth = GOAL[0] < p.y < GOAL[1]
        if p.x < PR or p.x > TL - PR:
            if in_mouth and (GOAL[0] + PR <= p.y <= GOAL[1] - PR or p.x < 0 or p.x > TL):
                if p.x < 0 or p.x > TL:                 # inside the goal: its side walls keep it in the mouth
                    if p.y < GOAL[0] + PR:
                        p.y, p.vy = GOAL[0] + PR, abs(p.vy) * E_WALL
                    elif p.y > GOAL[1] - PR:
                        p.y, p.vy = GOAL[1] - PR, -abs(p.vy) * E_WALL
                if p.x < -PR * 1.2 or p.x > TL + PR * 1.2:
                    self.goal(1 if p.x < 0 else 0)
                    return
            else:
                for px, py in ((0.0, GOAL[0]), (0.0, GOAL[1]), (TL, GOAL[0]), (TL, GOAL[1])):   # the goal posts
                    dx, dy = p.x - px, p.y - py
                    d = math.hypot(dx, dy)
                    if d < PR and d > 1e-9:
                        nx, ny = dx / d, dy / d
                        p.x, p.y = px + nx * PR, py + ny * PR
                        vn = p.vx * nx + p.vy * ny
                        if vn < 0:
                            p.vx -= (1 + E_WALL) * vn * nx
                            p.vy -= (1 + E_WALL) * vn * ny
                            bounced = True
                if not in_mouth:
                    if p.x < PR:
                        p.x, p.vx, bounced = PR, abs(p.vx) * E_WALL, True
                    elif p.x > TL - PR:
                        p.x, p.vx, bounced = TL - PR, -abs(p.vx) * E_WALL, True
        if p.y < PR:
            p.y, p.vy, bounced = PR, abs(p.vy) * E_WALL, True
        elif p.y > TW - PR:
            p.y, p.vy, bounced = TW - PR, -abs(p.vy) * E_WALL, True
        if bounced and p.speed > 0.4:
            self.walls += 1
            self.sfx("wall", min(1.0, 0.3 + p.speed / 6))

    def goal(self, side):
        self.score[side] += 1
        self.scorer = side
        self.state, self.state_t = "goal", 1.4
        self.sfx("goal")
        self.pops.append(["GOAL!", COLS[side], self.t + 1.3])
        p = self.puck
        p.vx = p.vy = 0.0
        p.x = -0.06 if side == 1 else TL + 0.06


# =============================================================================================
# The computer
# =============================================================================================
class Brain:
    """Watches the puck a little late (its reaction time), predicts where it will cross the defence line
    (bounces included), guards the goal, and attacks a puck in its half with an aimed or banked shot."""

    def __init__(self, g, side, diff, rnd):
        self.g, self.side, self.p, self.rnd = g, side, AI[diff], rnd
        self.seen = deque()
        self.aim = None
        self.aim_t = 0.0
        self.striking = False

    def update(self, dt):
        g, s = self.g, self.side
        p = g.puck
        self.seen.append((g.t, p.x, p.y, p.vx, p.vy))
        while len(self.seen) > 1 and self.seen[1][0] <= g.t - self.p["delay"]:
            self.seen.popleft()
        _, px, py, vx, vy = self.seen[0]
        m = g.mallets[s]
        home = MR + 0.05 if s == 0 else TL - MR - 0.05
        toward = -1 if s == 0 else 1                       # the direction of my goal
        mine = (px <= TL / 2 + PR) if s == 0 else (px >= TL / 2 - PR)     # a puck on the line is anyone's
        coming = vx * toward > 0.15
        self.aim_t -= dt
        if self.aim is None or self.aim_t <= 0:            # pick a shot now and then: straight or off a wall
            gy = TW / 2 + self.rnd.uniform(-0.12, 0.12)
            if self.rnd.random() < 0.35:
                gy = -gy if self.rnd.random() < 0.5 else 2 * TW - gy
            self.aim = (TL if s == 0 else 0.0, gy + self.rnd.uniform(-1, 1) * self.p["err"])
            self.aim_t = self.rnd.uniform(0.8, 1.6)
        far = abs(px - (TL / 2)) / (TL / 2)
        if mine and (not coming or abs(vx) < 1.2 or far < self.p["reach"]):
            # attack: get behind the puck on the line to the aim point, then drive through it
            ax, ay = self.aim
            if abs(px - (0.0 if s == 0 else TL)) < MR * 2.2:   # stuck against my own end: just clear it out
                ax, ay = TL / 2, TW / 2
            dx, dy = ax - px, ay - py
            d = math.hypot(dx, dy) or 1
            dx, dy = dx / d, dy / d
            back = PR + MR + 0.16                            # wind up far enough to arrive at speed
            bx, by = px - dx * back, py - dy * back
            rx, ry = px - m.x, py - m.y
            along = rx * dx + ry * dy
            side_off = abs(rx * dy - ry * dx)
            if self.striking and (along < 0 or side_off > PR + MR):
                self.striking = False                        # the shot is done (or missed): wind up again
            if along > (PR + MR) * 0.8 and side_off < (PR + MR) * 0.5 or self.striking:
                self.striking = True
                tx, ty = px + dx * 0.4, py + dy * 0.4        # strike through the puck
            else:
                tx, ty = bx, by
                if along < (PR + MR):                        # beside or in front of the puck: go round it
                    ty += (MR + PR) * 1.6 * (1 if m.y < py else -1)

        else:
            # defend: stand between the goal and where the puck will cross my line
            line = home + (0.12 if s == 0 else -0.12)
            yc = py
            if coming and abs(vx) > 1e-6:
                tt = (line - px) / vx
                yc = py + vy * tt
                span = TW - 2 * PR                           # unfold the wall bounces
                yy = (yc - PR) % (2 * span)
                yc = PR + (yy if yy <= span else 2 * span - yy)
            yc = clamp(yc, GOAL[0] - 0.05, GOAL[1] + 0.05)
            tx, ty = line, TW / 2 + (yc - TW / 2) * 0.9
        g.mouse[s] = (tx, ty)


# =============================================================================================
# Input: the kitty keyboard protocol where there is one, plus the mouse
# =============================================================================================
class PuckTerminal(KeyTerminal):
    """KeyTerminal (presses and releases) that also reads the mouse: positions in self.mouse_pos."""

    def __enter__(self):
        super().__enter__()
        self.mouse = []
        self.write("\x1b[?1000h\x1b[?1003h\x1b[?1006h")
        return self

    def __exit__(self, *exc):
        self.write("\x1b[?1006l\x1b[?1003l\x1b[?1000l")
        return super().__exit__(*exc)

    def parse(self, data):
        def grab(m):
            self.mouse.append((int(m.group(1)), int(m.group(2)) - 1, int(m.group(3)) - 1))
            return ""
        return super().parse(MOUSE_RE.sub(grab, data))

    def take_mouse(self):
        m, self.mouse = self.mouse, []
        return m


class Controls:
    """Turns key events into a wanted direction per side. Held keys steer (exact with kitty releases); in
    classic mode every press also gives a shove that fades, so taps work when two people share a keyboard."""

    def __init__(self, kitty, solo=False):
        self.kitty = kitty
        self.solo = solo
        self.held = HeldKeys(kitty, first=0.32, repeat=0.12)
        self.shove = [[0.0, 0.0], [0.0, 0.0]]

    def feed(self, name, kind, now):
        self.held.feed(name, kind, now)
        if kind == "press" and not self.kitty:
            for side, keys in ((0, P1_KEYS), (1, P2_KEYS)):
                if name in keys:
                    s = 0 if self.solo else side
                    dx, dy = keys[name]
                    sh = self.shove[s]
                    if dx:
                        sh[0] = dx * 1.0
                    if dy:
                        sh[1] = dy * 1.0
        self.held.take_hits()

    def direction(self, side, now, dt):
        self.held.tick(now)
        sets = [P1_KEYS, P2_KEYS] if self.solo else [(P1_KEYS, P2_KEYS)[side]]
        if self.solo and side == 1:
            return 0.0, 0.0
        x = y = 0.0
        for keys in sets:
            for k, (dx, dy) in keys.items():
                if self.held.down(k):
                    x += dx
                    y += dy
        sh = self.shove[side]
        if not self.kitty:
            x += sh[0]
            y += sh[1]
            f = math.exp(-dt / 0.28)
            sh[0] *= f
            sh[1] *= f
        return clamp(x, -1, 1), clamp(y, -1, 1)


# =============================================================================================
# Drawing
# =============================================================================================
def layout(cols, H):
    s = min((cols - 2) / (TL + 0.16), (H - 2) / (TW + 0.12))
    ox = (cols - TL * s) / 2
    oy = (H - TW * s) / 2
    return s, ox, oy


def disc(cv, x, y, r, c, ring=None):
    r = max(0.6, r)
    for yy in range(int(y - r - 1), int(y + r) + 2):
        for xx in range(int(x - r - 1), int(x + r) + 2):
            d = math.hypot(xx + 0.5 - x, yy + 0.5 - y)
            if d <= r:
                cv.set(xx, yy, ring if ring and d > r - 1.0 and r > 2 else c)


def draw_table(cv, g, v):
    s, ox, oy = v
    W, H = cv.W, cv.H
    flash = 0.0
    if g.state == "goal":
        flash = max(0.0, (g.state_t - 0.7) / 0.7)
    tint = COLS[g.scorer] if g.scorer is not None else (255, 255, 255)
    for y in range(H):
        cv.px[y] = [mix((6, 8, 20), (14, 10, 30), y / max(1, H))] * W
    x0, y0, x1, y1 = int(ox), int(oy), int(ox + TL * s), int(oy + TW * s)
    hole = max(2, int(s * 0.06))
    for y in range(y0, y1):
        row = cv.px[y]
        for x in range(x0, x1):
            u, w = (x - ox) / s, (y - oy) / s
            c = mix((20, 46, 92), (12, 30, 66), abs(w - 0.5) * 1.6)
            if (x - x0) % hole == hole // 2 and (y - y0) % hole == hole // 2:
                c = shade(c, 1.35)                              # the air holes
            row[x] = mix(c, tint, flash * 0.45)
    cx = ox + TL / 2 * s
    cy = oy + TW / 2 * s
    red = (230, 70, 90)
    cv.rect(int(cx), y0, 1, y1 - y0, red)
    for k in range(64):                                         # the centre circle and the goal creases
        a = k / 64 * 6.283
        cv.set(cx + math.cos(a) * 0.18 * s, cy + math.sin(a) * 0.18 * s, red)
        for gx in (0.0, TL):
            u = gx + math.cos(a) * 0.22 * (1 if gx == 0 else 1)
            if 0 <= u <= TL:
                cv.set(ox + u * s, cy + math.sin(a) * 0.22 * s, (90, 150, 230))
    for xx in (0.5, 1.5):
        cv.rect(int(ox + xx * s), y0, 1, y1 - y0, (60, 100, 170))
    rim = mix((120, 220, 255), (255, 255, 255), 0.25 + 0.15 * math.sin(g.t * 3))
    cv.rect(x0 - 1, y0 - 1, x1 - x0 + 2, 1, rim)
    cv.rect(x0 - 1, y1, x1 - x0 + 2, 1, rim)
    gy0, gy1 = int(oy + GOAL[0] * s), int(oy + GOAL[1] * s)
    for x in (x0 - 1, x1):
        cv.rect(x, y0 - 1, 1, gy0 - y0 + 1, rim)
        cv.rect(x, gy1, 1, y1 - gy1 + 1, rim)
    for side, x in ((0, x0 - 3), (1, x1 + 1)):                 # the goals: dark pockets glowing in the side colour
        c = mix((10, 10, 16), COLS[side], 0.25 + (0.6 if g.state == "goal" and g.scorer != side else 0) * flash)
        cv.rect(x, gy0, 2, gy1 - gy0, c)


def draw_things(cv, g, v):
    s, ox, oy = v
    for i, (tx, ty) in enumerate(g.trail):
        k = (i + 1) / max(1, len(g.trail))
        cv.set(ox + tx * s, oy + ty * s, mix((30, 60, 110), (200, 230, 255), k * 0.6))
    for x, y, age, c in g.flashes:
        r = (PR + age * 0.5) * s
        for k in range(20):
            a = k / 20 * 6.283
            cv.set(ox + (x + math.cos(a) * (PR + age * 0.5)) * s, oy + (y + math.sin(a) * (PR + age * 0.5)) * s,
                   mix(c, (255, 255, 255), 1 - age / 0.3))
    p = g.puck
    if -0.1 <= p.x <= TL + 0.1:
        disc(cv, ox + p.x * s, oy + p.y * s, PR * s, (250, 250, 255), (180, 190, 210))
    for side, m in enumerate(g.mallets):
        x, y = ox + m.x * s, oy + m.y * s
        disc(cv, x, y, MR * s, COLS[side], shade(COLS[side], 0.65))
        disc(cv, x, y, MR * s * 0.42, mix(COLS[side], (255, 255, 255), 0.55))


def render(g, cols, rows, hud=True, kitty=True, remote=False):
    play = rows - 1 if hud else rows
    if cols < 40 or play * 2 < 22:
        raise ValueError("too small for the table")
    cv = Canvas(cols, rows)
    v = layout(cols, play * 2)
    draw_table(cv, g, v)
    draw_things(cv, g, v)
    g.last_view = (v, cols, play)
    for txt, c, until in g.pops:
        k = 2 if cols >= 90 else 1
        w = title_width(txt, k)
        draw_title(cv, txt, (cols - w) // 2, play - 5 * k // 2, k, [c])
    if hud:
        draw_hud(cv, g)
        if g.state == "over":
            draw_over(cv, g, remote)
        if g.paused:
            overlay(cv, ["P A U S E D", "", "the host paused the game"] if remote else
                    help_lines(kitty) if g.help else getattr(g, "pause_lines", None) or PAUSE_LINES + ["", SND.label()])
    return cv


def who(g, s):
    names = getattr(g, "names", None)
    if names and not g.ai[s]:
        return names[s]
    return ("COMPUTER %s" % g.ai[s]) if g.ai[s] else ("YOU" if g.ai[1 - s] else NAMES[s] + (" WASD" if s == 0 else
                                                                                               " arrows"))


def draw_hud(cv, g):
    r = cv.rows - 1
    cv.put(0, r, " " * cv.cols, HUD_FG, HUD_BG)
    left, right = " %s " % who(g, 0), " %s " % who(g, 1)
    cv.put(0, r, left, (16, 14, 20), COLS[0])
    cv.put(cv.cols - len(right), r, right, (16, 14, 20), COLS[1])
    sc = " %d  :  %d " % tuple(g.score)
    cv.put((cv.cols - len(sc)) // 2, r, sc, (255, 255, 255), (30, 30, 50))
    t = "first to %d" % g.target
    if (cv.cols - len(sc)) // 2 - len(left) > len(t) + 3:
        cv.put(len(left) + 2, r, t, (150, 154, 184), HUD_BG)


def draw_over(cv, g, remote=False):
    w = g.winner
    name = who(g, w)
    hint = ("the host starts the next match" if remote else
            "Enter: back to the lobby   Esc / Q: end" if getattr(g, "names", None) else "Enter: again   Esc / Q: menu")
    lines = ["YOU WIN!" if name == "YOU" else "%s WINS!" % name, "", "%d : %d" % tuple(g.score), "", hint]
    if g.ai[1 - w] and not g.ai[w]:
        lines.insert(3, "you beat the %s computer" % g.ai[1 - w])
    bw = max(len(l) for l in lines) + 4
    x, y = max(0, (cv.cols - bw) // 2), max(0, cv.rows // 2 - len(lines) // 2 - 1)
    cv.frame(x - 1, y * 2 - 1, bw + 2, (len(lines) + 2) * 2 + 2, COLS[w])
    cv.box(x, y, [l.center(bw - 4) for l in lines], (240, 240, 246), (24, 22, 44))


# =============================================================================================
# Title, auto mode, play
# =============================================================================================
class TitleDemo:
    def __init__(self):
        self.k = 0
        self.new()

    def new(self):
        self.g = Match(ai=("hard", "normal") if self.k % 2 else ("normal", "hard"), target=99, seed=self.k, demo=True)
        self.k += 1

    def scene(self, cols, rows, dt):
        self.g.update(min(dt, 0.1))
        if self.g.t > 60:
            self.new()
        return render(self.g, cols, rows, hud=False)


ITEMS = [("2 Players", "left W A S D, right arrows")] + [("vs Computer", d) for d in DIFFS]
LAN_ITEM = len(ITEMS)            # then the LAN game, then auto mode


def render_menu(demo, cols, rows, sel, dt, help_, kitty, target):
    cv = demo.scene(cols, rows, dt)
    rec = load_scores().get(GAME, {})
    best = ("wins vs computer: " + ", ".join("%s %d" % (d, rec[d]) for d in DIFFS if d in rec)) if rec else None
    items = ["%-12s %s" % it for it in ITEMS] + ["%-12s host or join, two computers" % "LAN game",
                                                 "%-12s computer against computer" % AUTO_LABEL]
    title_screen(cv, "PUCKSLIDE", "air hockey on a glowing table", items, sel, best,
                 extra=["", "first to   < %d >" % target,
                        "keys: %s" % ("held keys exact (kitty protocol)" if kitty else "classic terminal - tap to shove")],
                 keys="Up/Down choose   Left/Right goals   Enter start   M %s   ? help   Esc back" % SND.label().lower(),
                 help_lines=help_lines(kitty), show_help=help_)
    return cv


def too_small(term):
    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (60x22).")


def apply_mouse(term, g, side):
    take = getattr(term, "take_mouse", None)
    if not take:
        return
    evs = take()
    if not evs or not hasattr(g, "last_view") or side is None:
        return
    (s, ox, oy), cols, play = g.last_view
    for b, col, row in evs:
        if row >= play:
            continue
        g.mouse[side] = ((col + 0.5 - ox) / s, (row * 2 + 1 - oy) / s)


def run_auto(term, target):
    auto = AutoMode()
    k = 0
    while True:
        g = Match(ai=("hard", "normal") if k % 2 else ("normal", "hard"), target=target, seed=None)
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
            if getattr(term, "take_mouse", None):
                term.take_mouse()
            sim = auto.scale(dt)
            n = max(1, int(math.ceil(sim / (1 / 60)))) if sim else 0
            for _ in range(min(n, 10)):
                g.update(sim / n)
            if g.state == "over" and over_at is None:
                over_at = now
            if over_at is not None:
                if auto.paused:
                    over_at += dt
                elif now - over_at > 4:
                    break
            cols, rows = term.size()
            if cols < 60 or rows < 22:
                too_small(term)
                time.sleep(0.2)
                continue
            cv = render(g, cols, rows)
            auto.banner(cv, extra="first to %d" % target)
            term.write(cv.emit())
            time.sleep(max(0, 1 / 60 - (time.time() - now)))


def play(term, sel, target):
    kitty = getattr(term, "kitty", False)
    ai = (None, None) if sel == 0 else (None, DIFFS[sel - 1])
    ctl = Controls(kitty, solo=sel > 0)
    while True:
        g = Match(ai=ai, target=target)
        last = time.time()
        recorded = again = False
        mouse_side = 0 if sel > 0 else None
        while True:
            now = time.time()
            dt = min(0.1, now - last)
            last = now
            events = term.events(0) if hasattr(term, "events") else [(k, "press") for k in term.keys(0)]
            for name, kind in events:
                if kind != "press":
                    ctl.feed(name, kind, now)
                    continue
                if g.state == "over":
                    if name in ("q", "esc"):
                        return
                    if name in ("enter", " ") and g.state_t < -0.6:
                        again = True
                    continue
                a = shared_key(name, g.paused, pause_keys=("esc", "p"))
                if a == "pause":
                    g.paused = True
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
                    ctl.feed(name, kind, now)
                    if mouse_side is not None and (name in P1_KEYS or name in P2_KEYS):
                        g.mouse[mouse_side] = None          # keys take over from the mouse
            if again:
                break
            apply_mouse(term, g, mouse_side)
            for s in (0, 1):
                if not g.ai[s]:
                    g.inp[s] = ctl.direction(s, now, dt)
                    if g.inp[s] != (0.0, 0.0) and s == mouse_side:
                        g.mouse[s] = None
            g.update(dt)
            if g.state == "over" and not recorded:
                recorded = True
                if sel > 0 and g.winner == 0:
                    d = DIFFS[sel - 1]
                    submit(GAME, d, load_scores().get(GAME, {}).get(d, 0) + 1)
            cols, rows = term.size()
            if cols < 60 or rows < 22:
                too_small(term)
                time.sleep(0.2)
                continue
            term.write(render(g, cols, rows, kitty=kitty).emit())
            time.sleep(max(0, 1 / 60 - (time.time() - now)))


# =============================================================================================
# The LAN game: the host plays left, the one who joins plays right (see arcadenet)
# =============================================================================================
LAN_PAUSE = ["P A U S E D", "", "Esc / P / Enter   continue", "?                 help", "M                 sound on / off",
             "V                 view", "Q                 end the game for both", "", "(the other one waits)"]


def lan_spec(demo, target):
    return arcadenet.LanGame(GAME, "PUCKSLIDE", match=lambda term, srv: lan_match(term, srv, target),
                             backdrop=lambda cols, rows, dt: demo.scene(cols, rows, dt), help=help_lines,
                             info=lambda: "first to %d" % target, players=(2, 2), size=(60, 22), sound=SND)


def lan_match(term, srv, target):
    """The host's match. Returns 'lobby' (Enter after the match) or 'quit'."""
    kitty = getattr(term, "kitty", False)
    g = Match(ai=(None, None), target=target)
    g.names = [s["name"] for s in srv.seats[:2]]
    g.pause_lines = LAN_PAUSE
    srv.game = g
    ctl = Controls(kitty, solo=True)
    far = {}                                        # the other computer's keys: its own controls, solo
    last = time.time()
    while True:
        now = time.time()
        dt = min(0.1, now - last)
        last = now
        srv.poll(now)
        arcadenet.play_sound(srv.spec, srv.sounds)
        srv.sounds = []
        for name, kind in arcadenet.term_events(term):
            if kind != "press":
                ctl.feed(name, kind, now)
                continue
            if g.state == "over":
                if name in ("q", "esc"):
                    return "quit"
                if name in ("enter", " ") and g.state_t < -0.6:
                    return "lobby"
                continue
            a = shared_key(name, g.paused, pause_keys=("esc", "p"))
            if a == "pause":
                g.paused = True
                SND.play("pause")
            elif a == "resume":
                g.paused = g.help = False
            elif a == "quit":
                return "quit"
            elif a == "help":
                g.help = not g.help
                g.paused = True
            elif a == "sound":
                if SND.toggle():
                    SND.play("sound_on")
            elif a is None:
                ctl.feed(name, kind, now)
                g.mouse[0] = None
        apply_mouse(term, g, 0)
        for r, seats, events, cleared in srv.inputs():
            c = far.setdefault(r, Controls(r.kitty, solo=True))
            if cleared:
                c.held.clear()
            for name, kind in events:
                c.feed(name, kind, now)
            if 1 in seats and not g.ai[1]:
                g.inp[1] = c.direction(0, now, dt)
        for i in srv.take_left():
            if i == 1:
                g.ai[1] = "normal"
                g.brains[1] = Brain(g, 1, "normal", g.rnd)
        g.inp[0] = ctl.direction(0, now, dt)
        if g.inp[0] != (0.0, 0.0):
            g.mouse[0] = None
        g.update(dt)
        srv.send_frames(now, lambda cols, rows, seats: render(g, cols, rows, remote=True))
        cols, rows = term.size()
        if cols < 60 or rows < 22:
            too_small(term)
            time.sleep(0.2)
            continue
        cv = render(g, cols, rows, kitty=kitty)
        if srv.recent() and not g.paused and g.state != "over":
            cv.put(0, 0, " %s " % srv.recent(), (230, 230, 240), (30, 30, 50))
        term.write(cv.emit())
        time.sleep(max(0, 1 / 60 - (time.time() - now)))


def main():
    with PuckTerminal() as term:
        demo = TitleDemo()
        sel, help_, ti = 1, False, 1
        n = len(ITEMS) + 2
        last = time.time()
        while True:
            now = time.time()
            cols, rows = term.size()
            if cols < 60 or rows < 22:
                too_small(term)
                if any(k in ("q", "esc") for k in term.keys(0.3)):
                    return
                last = time.time()
                continue
            term.write(render_menu(demo, cols, rows, sel, min(0.1, now - last), help_, term.kitty, TARGETS[ti]).emit())
            last = now
            go = False
            term.take_mouse()
            for k in term.keys(max(0.0, 1 / 30 - (time.time() - now))):
                if help_:
                    help_ = False
                    continue
                if k == "?":
                    help_ = True
                elif k in ("q", "esc"):
                    return
                elif k in ("up", "w"):
                    sel = (sel - 1) % n
                    SND.play("menu")
                elif k in ("down", "s"):
                    sel = (sel + 1) % n
                    SND.play("menu")
                elif k in ("left", "a", "right", "d"):
                    ti = (ti + (1 if k in ("right", "d") else -1)) % len(TARGETS)
                    SND.play("menu")
                elif k == "m":
                    if SND.toggle():
                        SND.play("sound_on")
                elif k in ("enter", " "):
                    SND.play("start")
                    go = True
            if go:
                if sel == len(ITEMS) + 1:
                    run_auto(term, TARGETS[ti])
                elif sel == LAN_ITEM:
                    arcadenet.lan_menu(term, lan_spec(demo, TARGETS[ti]))
                else:
                    play(term, sel, TARGETS[ti])
                last = time.time()


# =============================================================================================
# Self-test:  python3 puckslide.py --selftest
# =============================================================================================
class FakeTerm:
    def __init__(self, script, size=(100, 32)):
        self.script = sorted(script)
        self.t0 = time.time()
        self.cols_rows = size
        self.frames = 0
        self.kitty = False

    def keys(self, timeout=0.0):
        now = time.time() - self.t0
        out = [k for t, k in self.script if t <= now]
        self.script = [(t, k) for t, k in self.script if t > now]
        return out

    def events(self, timeout=0.0):
        return [(k, "press") for k in self.keys(timeout)]

    def take_mouse(self):
        return []

    def size(self):
        return self.cols_rows

    def write(self, s):
        self.frames += 1


def screenshot(cols=100, rows=32):
    quiet, SND.enabled = SND.enabled, False
    try:
        g = Match(ai=("hard", "normal"), target=7, seed=4)
        g.score = [3, 2]
        best = None
        for i in range(int(40 * 60)):
            g.update(1 / 60)
            if g.state == "play" and g.puck.speed > 3.5 and 0.6 < g.puck.x < 1.4 and len(g.trail) == 10:
                best = True
                break
        cv = render(g, cols, rows)
    finally:
        SND.enabled = quiet
    return cv


def selftest():
    import os
    import tempfile
    import arcadekit
    t0 = time.time()
    tmp = os.path.join(tempfile.mkdtemp(), "scores.json")
    arcadekit.SCORES_PATH = tmp
    SND.enabled = False
    rnd = random.Random(1)
    # puck-mallet hits conserve momentum (and lose a little energy)
    for _ in range(200):
        a, b = Body(0.5, 0.5, MR, MM), Body(0.5 + rnd.uniform(0.05, 0.095), 0.5 + rnd.uniform(-0.04, 0.04), PR, PM)
        a.vx, a.vy = rnd.uniform(-3, 3), rnd.uniform(-3, 3)
        b.vx, b.vy = rnd.uniform(-6, 6), rnd.uniform(-6, 6)
        px0, py0 = a.m * a.vx + b.m * b.vx, a.m * a.vy + b.m * b.vy
        e0 = 0.5 * (a.m * (a.vx ** 2 + a.vy ** 2) + b.m * (b.vx ** 2 + b.vy ** 2))
        collide(a, b, E_HIT)
        px1, py1 = a.m * a.vx + b.m * b.vx, a.m * a.vy + b.m * b.vy
        e1 = 0.5 * (a.m * (a.vx ** 2 + a.vy ** 2) + b.m * (b.vx ** 2 + b.vy ** 2))
        assert abs(px1 - px0) < 1e-9 and abs(py1 - py0) < 1e-9, "momentum changed"
        assert e1 <= e0 + 1e-9, "energy appeared"
    # a moving mallet hands its speed to a resting puck: a hard swing makes a fast shot
    a, b = Body(0.5, 0.5, MR, MM), Body(0.5 + MR + PR - 0.001, 0.5, PR, PM)
    a.vx = 2.5
    collide(a, b, E_HIT)
    assert b.vx > 4.0, b.vx
    # walls bounce with restitution
    g = Match(target=7, seed=2)
    g.state = "play"
    p = g.puck
    p.x, p.y, p.vx, p.vy = 1.0, 0.2, 0.0, -3.0
    for m in g.mallets:
        m.x, m.y = (0.2, 0.8) if m is g.mallets[0] else (1.8, 0.8)
    for _ in range(10):
        g.update(1 / 60)
    assert p.vy > 0 and abs(abs(p.vy) - 3.0 * E_WALL) < 0.15, p.vy
    # no tunnelling: fast shots never pass through a mallet or out of the table
    for k in range(300):
        g = Match(target=99, seed=k)
        g.state = "play"
        p = g.puck
        m = g.mallets[1]
        m.x, m.y = rnd.uniform(1.3, 1.85), rnd.uniform(0.15, 0.85)
        p.x, p.y = 0.6, rnd.uniform(0.1, 0.9)
        a = math.atan2(m.y - p.y, m.x - p.x)
        p.vx, p.vy = math.cos(a) * PUCK_MAX, math.sin(a) * PUCK_MAX
        g.mallets[0].y = 0.05
        for _ in range(12):
            g.update(1 / 60)
            assert -0.2 < p.x < TL + 0.2 and -0.01 < p.y < TW + 0.01, (p.x, p.y)
            if g.state != "play":
                break
        assert p.vx < 0 or g.state == "goal" or p.x < m.x, "the puck went through the mallet (seed %d)" % k
    # goals: through the mouth counts, the wall beside it does not
    g = Match(target=7, seed=3)
    g.state = "play"
    g.mallets[0].y = 0.06
    g.puck.x, g.puck.y, g.puck.vx, g.puck.vy = 0.3, 0.5, -4.0, 0.0
    for _ in range(30):
        g.update(1 / 60)
    assert g.score == [0, 1], g.score
    g = Match(target=7, seed=3)
    g.state = "play"
    g.mallets[0].y = 0.06
    g.puck.x, g.puck.y, g.puck.vx, g.puck.vy = 0.3, 0.15, -4.0, 0.0
    for _ in range(30):
        g.update(1 / 60)
    assert g.score == [0, 0] and g.puck.vx > 0
    # each mallet stays in its half
    g = Match(target=7, seed=4)
    g.state = "play"
    g.inp = [(1.0, 1.0), (-1.0, -1.0)]
    for _ in range(240):
        g.update(1 / 60)
    assert g.mallets[0].x <= TL / 2 - MR + 1e-9 and g.mallets[1].x >= TL / 2 + MR - 1e-9
    assert g.mallets[0].y <= TW - MR + 1e-9 and g.mallets[1].y >= MR - 1e-9
    # the hard computer beats the easy one
    wins = 0
    for k in range(3):
        g = Match(ai=("hard", "easy") if k % 2 == 0 else ("easy", "hard"), target=5, seed=10 + k, demo=True)
        while g.state != "over" and g.t < 600:
            g.update(1 / 60)
        hard = 0 if k % 2 == 0 else 1
        wins += g.winner == hard
        assert g.state == "over", "a match did not finish"
    assert wins >= 2, "hard won only %d of 3 against easy" % wins
    # controls: classic taps shove and fade, kitty held keys steer
    c = Controls(False)
    c.feed("d", "press", 0.0)
    x, y = c.direction(0, 0.0, 1 / 60)
    assert x > 0.5
    for i in range(60):
        x, y = c.direction(0, 1.0 + i / 60, 1 / 60)
    assert abs(x) < 0.05, x
    c = Controls(True)
    c.feed("up", "press", 0.0)
    assert c.direction(1, 5.0, 1 / 60) == (0, -1)
    c.feed("up", "release", 5.1)
    assert c.direction(1, 5.2, 1 / 60) == (0, 0)
    c = Controls(True, solo=True)
    c.feed("left", "press", 0.0)
    assert c.direction(0, 0.1, 1 / 60) == (-1, 0) and c.direction(1, 0.1, 1 / 60) == (0, 0)
    # titles, sizes, auto mode, a real play loop
    for cols, rows in ((60, 22), (100, 32), (180, 50)):
        d = TitleDemo()
        for i in range(30):
            d.scene(cols, rows, 0.1)
        for sel in range(len(ITEMS) + 1):
            render_menu(d, cols, rows, sel, 0.05, sel == 2, sel % 2 == 0, 7).emit()
        g = Match(ai=(None, "hard"), target=5)
        g.paused = True
        render(g, cols, rows).emit()
        g.paused, g.state, g.winner = False, "over", 1
        render(g, cols, rows).emit()
    try:
        TitleDemo().scene(20, 8, 0.1)
        raise AssertionError("a tiny scene should refuse")
    except ValueError:
        pass
    term = FakeTerm([(0.1, "+"), (0.2, "+"), (0.5, " "), (0.6, "?"), (0.7, "x"), (0.8, " "), (1.2, "esc")])
    run_auto(term, 5)
    assert term.frames > 5 and not term.script
    term = FakeTerm([(0.1, "d"), (0.2, "right"), (0.3, "w"), (0.5, "esc"), (0.7, "q")])
    play(term, 0, 7)
    assert term.frames > 5
    # the LAN game: the guest steers the right mallet with W A S D, the host ends it; a guest who leaves is
    # replaced by the computer
    spec = lan_spec(TitleDemo(), 5)
    res, frames, sounds, srv = arcadenet.try_match(spec, [(1.4, "esc"), (1.5, "q")],
                                                   [(0.2, "w", "press"), (0.3, "w", "press"), (0.4, "w", "press")])
    assert res == "quit" and frames >= 5, (res, frames)
    assert srv.game.mallets[1].y < TW / 2 - 0.05 and srv.game.ai == [None, None], srv.game.mallets[1].y
    res, frames, sounds, srv = arcadenet.try_match(spec, [(1.6, "esc"), (1.7, "q")], [(0.1, "a", "press")],
                                                   leave=True)
    assert res == "quit" and any("left" in n for n in srv.notes) and srv.game.ai[1] == "normal", list(srv.notes)
    assert not os.path.exists(tmp), "a score was written without a win"
    print("Self-test ok: momentum and energy in hits, hard swings, wall restitution, no tunnelling in 300 fast "
          "shots, goals and posts, half confinement, hard beats easy %d/3, tap and held controls, titles at three "
          "sizes, auto mode, play loop (%.1fs)" % (wins, time.time() - t0))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
