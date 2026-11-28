#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""WEFTWAR - weave light, cut your rivals off.

On the Night Loom the dye riders steer shuttles of light, and every cell they cross is woven shut behind them
with a burning weft thread. Touch a thread - a rival's or your own - or the loom's frame, and your shuttle
bursts. The last rider weaving takes the round; first to the set number of rounds takes the match.

Two riders at one keyboard (Saffron on W A S D, Woad on the arrows), two to four riders at their own computers
over the LAN / WLAN (one hosts, the others join), or one rider against one to three computer riders (Easy, Normal, Hard) who read the loom with a real look-ahead: flood fills of the free cloth,
who reaches which cell first, and how long a closed-off pocket can still be filled. Seven looms - open cloth,
bobbin posts, a cross, heddle gates, an oval ring, an hourglass and a teasel field. A limited Spur meter for
bursts of speed, and four optional charms on the cloth: Spur (refills the meter), Skip (the shuttle lifts and
crosses threads, leaving a gap), Thimble (tears through one thread instead of bursting) and Unravel (your
oldest thread comes undone). A rating that rises and falls with your matches against the computer riders.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
In terminals with the kitty keyboard protocol (kitty, WezTerm, Ghostty, recent iTerm2) the Spur keys are read
with their releases; elsewhere Spur counts as held while the terminal repeats the key.
"""
import math
import random
import sys
import time

from arcadekit import (ACCENTS, AUTO_LABEL, PAUSE_LINES, AutoMode, Canvas, HeldKeys, KeyTerminal, block_title,
                       clamp, load_scores, mix, overlay, scale_art, shade, shared_key, submit, title_screen)
from arcadesound import Sound, load_settings, save_settings
import arcadenet

GAME = "weftwar"
NAME = "WEFTWAR"
TAGLINE = "weave light, cut your rivals off"
ACCENTS.setdefault(NAME, ((255, 214, 110), (236, 70, 120)))

GW, GH = 50, 28                  # the loom in cells (the same in every window; bigger windows get bigger cells)
PW = GW + 2                      # padded width: a ring of frame cells around the loom, so no bounds checks
NCELL = PW * (GH + 2)
DX, DY = (0, 1, 0, -1), (-1, 0, 1, 0)       # up, right, down, left
OFF = (-PW, 1, PW, -1)
WALL, VOID = 9, 10               # grid values: 0 free, 1..5 a rider's thread, 9 post, 10 outside the loom
DT = 1 / 60                      # simulation step
SPEED = 9.0                      # cells per second
BOOST_K = 1.75                   # Spur: this much faster
DRAIN = 0.42                     # meter per second of Spur
REGEN = 0.085                    # meter per second while not spurring
CREEP_AT, CREEP = 28.0, 0.018    # after this long a round speeds up a little every second (no endless rounds)
INTRO = 3.0                      # countdown
END_T = 2.7                      # the round's result on screen
HOP_T = 1.3                      # Skip: seconds in the air
SHIELD_T = 12.0                  # Thimble lasts this long (or until used)
ITEM_LIFE = 11.0
WHITE = (255, 255, 255)
INF = 1 << 20

RIDERS = [("SAFFRON", (255, 184, 56)), ("WOAD", (72, 166, 255)), ("MADDER", (244, 62, 98)),
          ("VERDIGRIS", (60, 226, 166)), ("LICHEN", (188, 118, 255))]
SKILLS = ("easy", "normal", "hard")
SKILL_RATING = {"easy": 850, "normal": 1150, "hard": 1450}
TARGETS = (2, 3, 4, 5)           # first to ... rounds
ITEMS = {   # name, colour, what it does
    "spur": ("SPUR", (255, 196, 70), "refills the Spur meter"),
    "skip": ("SKIP", (110, 232, 255), "lift off: cross threads, leave a gap"),
    "thimble": ("THIMBLE", (226, 230, 255), "tear through one thread"),
    "unravel": ("UNRAVEL", (255, 104, 214), "your oldest thread comes undone"),
}
ITEM_ART = {
    "spur": ["a...a..", ".a...a.", "..a...a", ".a...a.", "a...a.."],
    "skip": ["..aaa..", ".a...a.", "a.....a", "a.....a", "b.....b"],
    "thimble": ["..aaa..", ".abbba.", ".ababa.", ".abbba.", ".ababa.", "aaaaaaa"],
    "unravel": [".aaaaa.", "a.....a", "a.aaa.a", "a.a.a.a", "a.a...a", ".a.aaa."],
}


def idx(x, y):
    return (y + 1) * PW + x + 1


def cxy(i):
    return i % PW - 1, i // PW - 1


PAR = bytes(((i % PW) + (i // PW)) & 1 for i in range(NCELL))   # checkerboard colour of each cell
TBL = bytes([0] + [1] * 255)                                     # grid -> 0 free / 1 blocked


# =============================================================================================
# The looms
# =============================================================================================
def _circle(x, y, cx, cy, r):
    return (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 < r * r


def _ellipse(x, y, cx, cy, rx, ry):
    return ((x + 0.5 - cx) / rx) ** 2 + ((y + 0.5 - cy) / ry) ** 2 < 1


def a_open(x, y):
    return 0


def a_bobbin(x, y):
    for cx, cy in ((13.5, 6.5), (36.5, 6.5), (13.5, 21.5), (36.5, 21.5)):
        if _circle(x, y, cx, cy, 2.7):
            return WALL
    return WALL if _circle(x, y, 25, 14, 2.4) else 0


def a_cross(x, y):
    return VOID if (x < 11 or x > 38) and (y < 7 or y > 20) else 0


def a_heddle(x, y):
    if x in (16, 33) and not (4 <= y <= 6 or 12 <= y <= 15 or 21 <= y <= 23):
        return WALL
    return 0


def a_ring(x, y):
    if not _ellipse(x, y, 25, 14, 25.3, 14.3):
        return VOID
    return WALL if _ellipse(x, y, 25, 14, 6.0, 3.2) else 0


def a_hourglass(x, y):
    if abs(x + 0.5 - 25) < 5 and abs(y + 0.5 - 14) > 4:
        return VOID
    if y in (13, 14) and x in (11, 12, 37, 38):
        return WALL
    return 0


def a_teasel(x, y):
    return WALL if (x - 4) % 8 in (0, 1) and (y - 5) % 7 in (0, 1) else 0


SP2 = [(7, 11, 1), (42, 16, 3)]
SP4 = [(6, 9, 1), (43, 18, 3), (18, 24, 0), (31, 3, 2)]
ARENAS = [   # name, shape, accent, floor
    dict(name="OPEN LOOM", f=a_open, accent=(120, 200, 255), floor=(15, 17, 33)),
    dict(name="BOBBIN COURT", f=a_bobbin, accent=(255, 186, 104), floor=(21, 15, 27)),
    dict(name="SPINDLE CROSS", f=a_cross, accent=(130, 255, 186), floor=(12, 21, 26)),
    dict(name="HEDDLE GATES", f=a_heddle, accent=(216, 140, 255), floor=(19, 14, 31)),
    dict(name="SELVAGE RING", f=a_ring, accent=(255, 128, 150), floor=(23, 13, 22)),
    dict(name="SHUTTLE RUN", f=a_hourglass, accent=(255, 226, 120), floor=(20, 19, 17)),
    dict(name="TEASEL FIELD", f=a_teasel, accent=(150, 236, 120), floor=(14, 20, 16)),
]
_TEMPLATES = {}


def arena_grid(ai):
    """The loom as a padded bytearray: 0 free cloth, WALL posts, VOID outside (also the ring around it)."""
    if ai not in _TEMPLATES:
        g = bytearray([VOID]) * NCELL
        f = ARENAS[ai]["f"]
        for y in range(GH):
            for x in range(GW):
                g[idx(x, y)] = f(x, y)
        _TEMPLATES[ai] = bytes(g)
    return bytearray(_TEMPLATES[ai])


def spawns(n):
    return SP2 if n == 2 else SP4[:n]


# =============================================================================================
# Sound
# =============================================================================================
def _arp(fs, d=0.05, v=0.3, w="tri", last=0.2):
    out = [dict(w=w, f=f, d=d, v=v) for f in fs[:-1]]
    return out + [dict(w=w, f=fs[-1], d=last, v=v, vib=(6, 0.18))]


SND = Sound(GAME, {
    "tick": [dict(w="square", f=660, d=0.07, v=0.22, duty=0.3)],
    "go": [dict(w="square", f=1320, d=0.05, v=0.24, duty=0.3), dict(w="tri", f=1760, d=0.22, v=0.26, vib=(7, 0.2))],
    "turn": [dict(w="tri", f=520, f2=560, d=0.025, v=0.08)],
    "boost": [dict(w="noise", f=1800, f2=4200, d=0.18, v=0.16), dict(w="saw", f=180, f2=360, d=0.16, v=0.1, at=0)],
    "crash": [dict(w="noise", f=1400, f2=60, d=0.55, v=0.55), dict(w="square", f=220, f2=40, d=0.4, v=0.3, at=0, duty=0.3),
              dict(w="tri", f=880, f2=110, d=0.25, v=0.2, at=0)],
    "tear": [dict(w="noise", f=6000, f2=1500, d=0.12, v=0.28), dict(w="tri", f=990, f2=1480, d=0.1, v=0.2, at=0)],
    "hop": [dict(w="tri", f=440, f2=1320, d=0.14, v=0.24), dict(w="sine", f=1760, d=0.1, v=0.1)],
    "land": [dict(w="tri", f=660, f2=330, d=0.08, v=0.2)],
    "pickup": _arp([988, 1319, 1760], 0.035, 0.24),
    "unravel": [dict(w="saw", f=880, f2=220, d=0.35, v=0.14), dict(w="noise", f=3000, f2=800, d=0.3, v=0.08, at=0)],
    "round": _arp([659, 784, 988, 1319], 0.06, 0.28, "square", 0.3),
    "draw": [dict(w="tri", f=440, f2=415, d=0.2, v=0.26), dict(w="tri", f=330, f2=311, d=0.3, v=0.26)],
    "lost": [dict(w="tri", f=523, f2=392, d=0.16, v=0.3), dict(w="tri", f=392, f2=262, d=0.3, v=0.3, r="lin")],
    "match": [dict(w="tri", f=f, d=0.11, v=0.32) for f in (523, 659, 784, 1047, 784, 1047, 1319)] +
             [dict(w="tri", f=1568, d=0.8, v=0.34, vib=(6, 0.25), r="lin")],
    "over": [dict(w="tri", f=523, d=0.18, v=0.34), dict(w="tri", f=466, d=0.18, v=0.34), dict(w="tri", f=392, d=0.18, v=0.34),
             dict(w="tri", f=330, f2=262, d=0.7, v=0.36, r="lin")],
    "menu": [dict(w="tri", f=660, d=0.025, v=0.2)],
    "start": [dict(w="tri", f=523, d=0.06, v=0.3), dict(w="tri", f=784, d=0.06, v=0.3), dict(w="tri", f=1047, d=0.16, v=0.3)],
    "pause": [dict(w="tri", f=523, f2=392, d=0.07, v=0.22)],
    "sound_on": [dict(w="tri", f=440, d=0.06, v=0.35), dict(w="tri", f=880, d=0.12, v=0.35)],
})


def help_lines(kitty=True):
    mode = (["Your terminal reports key releases: Spur runs exactly as long",
             "as you hold the key."] if kitty else
            ["Classic keys: Spur runs while the terminal repeats the key;",
             "a tap gives a short burst."])
    return ["WEFTWAR - keys", "",
            "W A S D    Saffron (player 1) steers   Space / E  Spur",
            "arrows     Woad (player 2) steers      Enter / 0  Spur",
            "           alone against the computer: either set",
            "           LAN game: every rider at their own computer,",
            "           with either set",
            "Esc / P    pause menu (Q there: quit, M sound)",
            "?          this help", ""] + mode + [
            "",
            "Every cell your shuttle crosses is woven shut behind it.",
            "Touch a thread or the frame and you burst; the last",
            "rider weaving takes the round. A burst rider's thread",
            "burns away and frees the cloth again.",
            "Spur: a burst of speed from the meter under the loom.",
            "Charms:  Spur     refills the Spur meter",
            "         Skip     lift off and cross threads",
            "         Thimble  tear through one thread",
            "         Unravel  your oldest thread comes undone",
            "Against the computer your rating rises and falls",
            "with every match (Easy %d, Normal %d, Hard %d)." % (
                SKILL_RATING["easy"], SKILL_RATING["normal"], SKILL_RATING["hard"]), "",
            "Auto mode: computer riders weave on their own",
            "(Space pause, +/- speed, Esc stop)."]


# =============================================================================================
# Riders and the match
# =============================================================================================
class Rider:
    def __init__(self, k, ci, ctl, skill="normal"):
        self.k, self.ci, self.ctl, self.skill = k, ci, ctl, skill
        self.name, self.col = RIDERS[ci]
        self.points = 0
        self.rounds = self.cells = self.crashes = self.cuts = 0
        self.brain = None
        self.place(idx(0, 0), 1)
        self.alive = False

    @property
    def human(self):
        return self.ctl != "cpu"

    def place(self, cell, d):
        self.cell = self.vfrom = cell
        self.d = d
        self.acc = 0.0
        self.alive = True
        self.queue = []
        self.want_boost = self.boosting = False
        self.meter = 1.0
        self.path = [cell]
        self.base = 0                   # absolute index of path[0] (the tail unravels from the front)
        self.hop = 0.0
        self.shield = 0.0
        self.unravel = 0
        self.crash_t = None
        self.burn = 0.0
        self.boost_t = 0.0
        self.trail_len = 1

    def last_abs(self):
        return self.base + len(self.path) - 1


class Game:
    def __init__(self, riders, target=3, arena=-1, pickups=True, seed=None, quiet=False, mode="duel"):
        self.rnd = random.Random(seed)
        self.quiet = quiet
        self.mode = mode
        self.target = target
        self.arena_pick = arena
        self.pickups = pickups
        self.riders = []
        for n, (ci, ctl, skill) in enumerate(riders):
            r = Rider(n + 1, ci, ctl, skill)
            if ctl == "cpu":
                r.brain = Brain(skill, self.rnd.random())
            self.riders.append(r)
        self.round_no = 0
        self.round_id = 0
        self.over = False
        self.winner = None
        self.paused = self.help = False
        self.clock = 0.0
        self.parts, self.rings, self.flashes = [], [], []
        self.shake = 0.0
        self.acc = 0.0
        self.arena_start = self.rnd.randrange(len(ARENAS)) if arena < 0 else arena
        self.history = []
        self.start_round()

    def snd(self, name, vol=1.0, gap=0.04):
        if not self.quiet:
            SND.play(name, vol, gap)

    # --- rounds -----------------------------------------------------------------------------
    def start_round(self):
        self.round_no += 1
        self.round_id += 1
        self.ai = self.arena_pick if self.arena_pick >= 0 else (self.arena_start + self.round_no - 1) % len(ARENAS)
        self.arena = ARENAS[self.ai]
        self.grid = arena_grid(self.ai)
        self.pos = [0] * NCELL
        self.changes = []
        self.items = []
        self.item_t = 3.5 + self.rnd.random() * 2
        self.state, self.state_t = "intro", 0.0
        self.round_t = 0.0
        self.round_winner = None
        self.speed = SPEED
        sp = spawns(len(self.riders))
        n = len(self.riders)
        for j, r in enumerate(self.riders):
            x, y, d = sp[(j + self.round_no - 1) % n]
            r.place(idx(x, y), d)
            self.grid[r.cell] = r.k
            self.pos[r.cell] = 0
            if r.brain:
                r.brain.reset()
        self.ticked = -1

    def standings(self):
        return sorted(self.riders, key=lambda r: (-r.points, -r.rounds, r.k))

    def humans(self):
        return [r for r in self.riders if r.human]

    # --- cells -------------------------------------------------------------------------------
    def owner(self, c):
        v = self.grid[c]
        return self.riders[v - 1] if 1 <= v <= len(self.riders) else None

    def stamp_info(self, c):
        """(rider, arm mask) of a thread cell for drawing: only the parts that are woven for good (an alive
        rider's last two cells are drawn by the moving shuttle)."""
        r = self.owner(c)
        if r is None:
            return None, 0
        p = self.pos[c] - r.base
        path = r.path
        if not 0 <= p < len(path) or path[p] != c:
            return None, 0
        last = len(path) - 1
        alive = r.alive and r.hop <= 0 and path[last] != -1
        if alive and p == last:
            return r, -1                 # the head: drawn live
        mask = 0
        for q in (p - 1, p + 1):
            if not 0 <= q <= last:
                continue
            if alive and q == last and p == last - 1:
                continue                 # the arm to the head is drawn live
            o = path[q]
            if o < 0:
                continue
            dd = o - c
            if dd in OFF:
                mask |= 1 << OFF.index(dd)
        return r, mask

    def touch(self, *cells):
        self.changes.extend(c for c in cells if c >= 0)

    def touch_path(self, r, a):
        """Cell at absolute path index a and its neighbours in the path need a new picture."""
        for q in (a - 1, a, a + 1):
            p = q - r.base
            if 0 <= p < len(r.path) and r.path[p] >= 0:
                self.changes.append(r.path[p])

    def lay(self, r, c):
        self.grid[c] = r.k
        r.path.append(c)
        self.pos[c] = r.last_abs()
        r.cells += 1
        r.trail_len += 1
        self.touch_path(r, r.last_abs())
        self.touch_path(r, r.last_abs() - 1)

    def clear_cell(self, r, a):
        """Take the cell at absolute path index a out of rider r's thread."""
        p = a - r.base
        c = r.path[p]
        if c < 0:
            return
        r.path[p] = -1
        if self.grid[c] == r.k:
            self.grid[c] = 0
        r.trail_len -= 1
        self.touch(c)
        self.touch_path(r, a)

    # --- update -----------------------------------------------------------------------------
    def update(self, dt, ctl=None):
        if self.over:
            self.fx(dt)
            return
        k = 1.0
        if self.state == "play" and self.mode == "versus" and not any(r.alive for r in self.humans()):
            k = 3.0                       # only computer riders left: let them settle it quickly
        self.acc += min(dt, 0.1) * k
        n = 0
        while self.acc >= DT and n < 40:
            self.acc -= DT
            self.step(ctl)
            n += 1

    def step(self, ctl=None):
        self.clock += DT
        self.state_t += DT
        if ctl is not None:
            for r in self.riders:
                if r.human:
                    t = ctl.turns(r.ctl)
                    if t and self.state != "end":
                        r.queue = (r.queue + t)[-3:]
                    r.want_boost = ctl.boost(r.ctl)
        if self.state == "intro":
            sec = int(self.state_t / 0.8 - 0.75)
            if sec != self.ticked and 0 <= sec < 3 and self.state_t >= 0.6:
                self.ticked = sec
                self.snd("tick")
            if self.state_t >= INTRO:
                self.state, self.state_t = "play", 0.0
                self.snd("go")
        elif self.state == "play":
            self.play_step()
        elif self.state == "end":
            if self.state_t >= END_T:
                if any(r.points >= self.target for r in self.riders):
                    self.state = "over"
                    self.over = True
                    self.winner = max(self.riders, key=lambda r: r.points)
                    self.snd("match" if self.winner.human or not self.humans() else "over")
                else:
                    self.start_round()
        self.burn_step()
        self.fx(DT)

    def play_step(self):
        self.round_t += DT
        if self.round_t > CREEP_AT:
            self.speed = SPEED * min(1.9, 1 + CREEP * (self.round_t - CREEP_AT))
        if self.pickups:
            self.items_step()
        movers = []
        for r in self.riders:
            if not r.alive:
                continue
            if r.shield > 0:
                r.shield = max(0.0, r.shield - DT)
            boosting = r.want_boost and r.meter > 0.02
            if boosting and not r.boosting:
                r.boost_t = 0.0
                if r.human:
                    self.snd("boost", 0.6)
            r.boosting = boosting
            if boosting:
                r.meter = max(0.0, r.meter - DRAIN * DT)
                r.boost_t += DT
                if self.rnd.random() < 0.5:
                    self.spark_behind(r)
            else:
                r.meter = min(1.0, r.meter + REGEN * DT)
            r.acc += self.speed * (BOOST_K if boosting else 1.0) * DT
            if r.hop > 0:
                r.hop -= DT
                if r.hop <= 0:
                    if self.grid[r.cell] == 0:
                        self.lay(r, r.cell)
                        r.hop = 0.0
                        if r.human:
                            self.snd("land", 0.6)
                    else:
                        r.hop = 0.001      # still above a thread: stay up until there is cloth to land on
            if r.unravel > 0:
                self.unravel_step(r)
            if r.acc >= 1.0:
                movers.append(r)
        if not movers:
            return
        for r in movers:
            if r.brain:
                r.d, r.want_boost = r.brain.decide(self, r)
            else:
                while r.queue:
                    nd = r.queue.pop(0)
                    if nd != r.d and nd != (r.d + 2) % 4:
                        r.d = nd
                        self.snd("turn", 0.5, 0.02)
                        break
        targets = {}
        for r in movers:
            t = r.cell + OFF[r.d]
            targets.setdefault(t, []).append(r)
        heads = {r.cell for r in self.riders if r.alive}
        crashed = []
        for r in movers:
            t = r.cell + OFF[r.d]
            v = self.grid[t]
            if len(targets[t]) > 1:
                crashed.append((r, None, t))
                continue
            if v in (WALL, VOID):
                crashed.append((r, None, t))
                continue
            if v:
                if t in heads and r.hop <= 0:
                    crashed.append((r, self.owner(t), t))
                    continue
                if r.hop > 0:
                    pass                    # Skip: flies over the thread
                elif r.shield > 0:
                    o = self.owner(t)
                    if o is not None:
                        self.clear_cell(o, self.pos[t])
                    r.shield = 0.0
                    self.burst(t, 18, [(255, 255, 255), (220, 226, 255), r.col], 6.0, 0.5)
                    self.rings.append([t, 0.0, 0.5, (226, 230, 255)])
                    self.snd("tear")
                else:
                    crashed.append((r, self.owner(t), t))
                    continue
        dead = {id(r) for r, _, _ in crashed}
        for r in movers:
            if id(r) in dead:
                continue
            t = r.cell + OFF[r.d]
            r.acc -= 1.0
            r.vfrom = r.cell
            r.cell = t
            if r.hop > 0:
                if r.path[-1] != -1:
                    r.path.append(-1)
                    self.touch_path(r, r.last_abs() - 1)
            else:
                self.lay(r, t)
            for it in self.items:
                if it["cell"] == t:
                    self.take(r, it)
            self.items = [it for it in self.items if not it.get("gone")]
        for r, o, t in crashed:
            self.crash(r, o, t)
        alive = [r for r in self.riders if r.alive]
        if len(alive) <= 1:
            self.end_round(alive[0] if alive else None)

    def crash(self, r, o, t):
        r.alive = False
        r.crashes += 1
        r.acc = 1.0
        r.crash_t = self.clock
        r.burn = -0.45
        r.boosting = False
        if o is not None and o is not r:
            o.cuts += 1
        self.touch_path(r, r.last_abs())
        self.touch_path(r, r.last_abs() - 1)
        x, y = cxy(r.cell)
        hx, hy = x + DX[r.d] * 0.5, y + DY[r.d] * 0.5
        self.burst_xy(hx + 0.5, hy + 0.5, 46, [WHITE, mix(r.col, WHITE, 0.5), r.col, shade(r.col, 0.6)], 11.0, 0.9)
        self.rings.append([(hx + 0.5, hy + 0.5), 0.0, 0.7, r.col])
        self.rings.append([(hx + 0.5, hy + 0.5), -0.12, 0.6, WHITE])
        self.flashes.append([hx + 0.5, hy + 0.5, 0.0, 0.6, r.col])
        self.shake = max(self.shake, 0.35)
        self.snd("crash", 0.9 if r.human or not self.humans() else 0.6)

    def end_round(self, w):
        self.state, self.state_t = "end", 0.0
        self.round_winner = w
        self.history.append(w.k if w else 0)
        if w:
            w.points += 1
            w.rounds += 1
            if not self.humans() or w.human:
                self.snd("round")
            else:
                self.snd("lost")
        else:
            self.snd("draw")

    def burn_step(self):
        """A burst rider's thread burns away from the crash back to its start."""
        for r in self.riders:
            if r.alive or r.crash_t is None:
                continue
            r.burn += DT
            if r.burn <= 0 or not r.path:
                continue
            rate = max(70.0, r.trail_len / 1.4)
            n = int(r.burn * rate)
            r.burn -= n / rate
            while n > 0 and r.path:
                c = r.path[-1]
                if c >= 0:
                    if self.grid[c] == r.k:
                        self.grid[c] = 0
                    self.touch(c)
                    if self.rnd.random() < 0.35:
                        x, y = cxy(c)
                        self.parts.append([x + 0.5, y + 0.5, self.rnd.uniform(-1.5, 1.5), self.rnd.uniform(-2.5, -0.5),
                                           0.0, self.rnd.uniform(0.4, 0.8), mix(r.col, (255, 230, 160), 0.4), 0])
                    n -= 1
                r.path.pop()
                if r.path and r.path[-1] >= 0:
                    self.touch(r.path[-1])
            if not r.path:
                r.crash_t = None

    def unravel_step(self, r):
        n = 2 if self.rnd.random() < 0.5 else 1
        while n > 0 and r.unravel > 0 and len(r.path) > 3:
            c = r.path[0]
            r.path.pop(0)
            r.base += 1
            if c >= 0:
                if self.grid[c] == r.k:
                    self.grid[c] = 0
                r.trail_len -= 1
                self.touch(c)
                if r.path and r.path[0] >= 0:
                    self.touch(r.path[0])
                if self.rnd.random() < 0.4:
                    x, y = cxy(c)
                    self.parts.append([x + 0.5, y + 0.5, self.rnd.uniform(-2, 2), self.rnd.uniform(-2, 2), 0.0, 0.5,
                                       mix(r.col, (255, 104, 214), 0.5), 0])
                r.unravel -= 1
                n -= 1
        if len(r.path) <= 3:
            r.unravel = 0

    # --- charms -----------------------------------------------------------------------------
    def items_step(self):
        for it in self.items:
            it["t"] += DT
        self.items = [it for it in self.items if it["t"] < ITEM_LIFE]
        self.item_t -= DT
        if self.item_t > 0:
            return
        self.item_t = 4.0 + self.rnd.random() * 3.5
        if len(self.items) >= 2:
            return
        heads = [cxy(r.cell) for r in self.riders if r.alive]
        for _ in range(40):
            x, y = self.rnd.randrange(1, GW - 1), self.rnd.randrange(1, GH - 1)
            c = idx(x, y)
            if self.grid[c] or any(self.grid[c + o] for o in OFF):
                continue
            if any(abs(x - hx) + abs(y - hy) < 6 for hx, hy in heads):
                continue
            if any(it["cell"] == c for it in self.items):
                continue
            kind = self.rnd.choice(("spur", "spur", "skip", "skip", "thimble", "unravel"))
            self.items.append(dict(kind=kind, cell=c, t=0.0))
            return

    def take(self, r, it):
        it["gone"] = True
        k = it["kind"]
        if k == "spur":
            r.meter = 1.0
        elif k == "skip":
            r.hop = HOP_T            # the cell it lifts from stays woven; the gap starts after it
            self.snd("hop", 0.8)
        elif k == "thimble":
            r.shield = SHIELD_T
        elif k == "unravel":
            r.unravel = max(r.unravel, int(r.trail_len * 0.5))
            self.snd("unravel", 0.8)
        self.burst(it["cell"], 16, [WHITE, ITEMS[k][1]], 5.0, 0.6)
        self.rings.append([it["cell"], 0.0, 0.45, ITEMS[k][1]])
        if k in ("spur", "thimble"):
            self.snd("pickup", 0.8)

    # --- effects ----------------------------------------------------------------------------
    def burst(self, c, n, cols, spd=6.0, life=0.7):
        x, y = cxy(c)
        self.burst_xy(x + 0.5, y + 0.5, n, cols, spd, life)

    def burst_xy(self, x, y, n, cols, spd=6.0, life=0.7):
        rnd = self.rnd
        for _ in range(n):
            a = rnd.random() * 2 * math.pi
            v = spd * (0.25 + rnd.random() * 0.9)
            self.parts.append([x, y, math.cos(a) * v, math.sin(a) * v, 0.0, life * (0.5 + rnd.random() * 0.7),
                               rnd.choice(cols), 1 if rnd.random() < 0.35 else 0])

    def spark_behind(self, r):
        x, y = self.head_xy(r)
        b = (r.d + 2) % 4
        self.parts.append([x + DX[b] * 0.4 + self.rnd.uniform(-0.2, 0.2), y + DY[b] * 0.4 + self.rnd.uniform(-0.2, 0.2),
                           DX[b] * 3 + self.rnd.uniform(-1.5, 1.5), DY[b] * 3 + self.rnd.uniform(-1.5, 1.5), 0.0,
                           0.3 + self.rnd.random() * 0.2, mix(r.col, WHITE, self.rnd.random() * 0.7), 0])

    def fx(self, dt):
        keep = []
        for p in self.parts:
            p[4] += dt
            if p[4] < p[5]:
                p[0] += p[2] * dt
                p[1] += p[3] * dt
                p[2] *= 1 - 2.2 * dt
                p[3] *= 1 - 2.2 * dt
                keep.append(p)
        self.parts = keep[-500:]
        for rg in self.rings:
            rg[1] += dt
        self.rings = [rg for rg in self.rings if rg[1] < rg[2]]
        for f in self.flashes:
            f[2] += dt
        self.flashes = [f for f in self.flashes if f[2] < f[3]]
        self.shake = max(0.0, self.shake - dt)

    def head_xy(self, r):
        """The shuttle's drawn position in cell units (centre of a cell = x + 0.5): it glides from the cell it
        left to the cell it is in, so the picture runs smoothly between the steps of the grid."""
        f = 1.0 if (not r.alive or self.state != "play") else min(1.0, r.acc)
        if r.vfrom == r.cell:
            f = 1.0
        ax, ay = cxy(r.vfrom)
        bx, by = cxy(r.cell)
        return ax + (bx - ax) * f + 0.5, ay + (by - ay) * f + 0.5


# =============================================================================================
# The computer riders: flood fills, who reaches which cell first, and how long a pocket lasts
# =============================================================================================
def opp_dist(occ, sources):
    """Breadth-first distances from all the given heads at once (occ: 0 free / non-zero blocked)."""
    dist = [INF] * NCELL
    fr = []
    for s in sources:
        dist[s] = 0
        fr.append(s)
    d = 0
    reach = red = 0
    up, rt, dn, lf = OFF
    while fr:
        d += 1
        nf = []
        for i in fr:
            for j in (i + up, i + rt, i + dn, i + lf):
                if not occ[j] and dist[j] == INF:
                    dist[j] = d
                    nf.append(j)
                    red += PAR[j]
        reach += len(nf)
        fr = nf
    return dist, reach, red


def territory(occ, t, dist, cap=0):
    """From cell t: the cells this rider reaches strictly before every rival (exact Voronoi split of the loom:
    a shortest path to a cell that is mine only runs through cells that are mine), the tied cells, whether any
    rival can reach the region at all, and the colour counts for the fill estimate."""
    seen = bytearray(occ)
    seen[t] = 1
    fr = [t]
    d = mine = ties = same = 0
    touch = False
    pt = PAR[t]
    up, rt, dn, lf = OFF
    while fr:
        d += 1
        if cap and d > cap:
            return mine, ties, True, same, True
        nf = []
        for i in fr:
            for j in (i + up, i + rt, i + dn, i + lf):
                if seen[j]:
                    continue
                seen[j] = 1
                dj = dist[j]
                if dj < INF:
                    touch = True
                if d < dj:
                    mine += 1
                    same += PAR[j] == pt
                    nf.append(j)
                elif d == dj:
                    ties += 1
        fr = nf
    return mine, ties, touch, same, False


def flood(occ, t, cap=INF):
    """Size of the free region around t and its count of cells of t's own checkerboard colour."""
    seen = bytearray(occ)
    seen[t] = 1
    q = [t]
    pt = PAR[t]
    same = 0
    up, rt, dn, lf = OFF
    for i in q:
        for j in (i + up, i + rt, i + dn, i + lf):
            if not seen[j]:
                seen[j] = 1
                q.append(j)
                same += PAR[j] == pt
        if len(q) > cap:
            break
    return len(q) - 1, same


def fill_est(n, same):
    """How many more cells a rider standing on a cell can still weave in a region of n cells: a path
    alternates checkerboard colours, so it is bounded by twice the rarer colour (plus one)."""
    other = n - same
    return min(n, 2 * min(same, other) + (1 if other > same else 0))


class Brain:
    """One computer rider. Easy reacts late and judges space by a short glance; Normal splits the loom by
    who gets where first, with some slack; Hard also checks for pockets it would seal itself into, fills a
    closed-off region tightly, races rivals with the Spur and heads for charms."""

    def __init__(self, skill, seed=0.0):
        self.skill = skill
        self.rnd = random.Random(seed)
        self.react = 2

    def reset(self):
        self.react = 2 + self.rnd.randrange(2)

    def decide(self, g, r):
        sk = self.skill
        if sk in ("easy", "rookie"):
            return self.simple(g, r)
        grid = g.grid
        rnd = self.rnd
        opps = [o for o in g.riders if o.alive and o is not r]
        occ = grid.translate(TBL)
        cands = []
        for nd in (r.d, (r.d + 1) % 4, (r.d + 3) % 4):
            t = r.cell + OFF[nd]
            if not occ[t] or (r.hop > 0.25 and grid[t] not in (WALL, VOID) and t not in [o.cell for o in opps]):
                cands.append((nd, t))
        if not cands:
            return r.d, False
        if len(cands) == 1 and not opps:
            return cands[0][0], False
        dist, reach, red = opp_dist(occ, [o.cell for o in opps])
        n_opp = max(1, len(opps))
        opp_est = 2 * min(red, reach - red) + 1 if opps else 0
        hard = sk == "hard"
        best, best_s, best_sep = cands[0], -1e9, False
        for nd, t in cands:
            o2 = bytearray(occ)
            o2[t] = 1
            mine, ties, touch, same, capped = territory(o2, t, dist, 0 if hard else 30)
            sep = not touch and not capped
            if sep:
                if hard:
                    m = 0
                    for o in OFF:
                        j = t + o
                        if not o2[j]:
                            n, s_ = flood(o2, j)
                            m = max(m, 1 + fill_est(n, s_))
                    mine_est = m
                else:
                    mine_est = fill_est(mine, same)
                score = mine_est - opp_est / n_opp
                score += 0.35 * sum(1 for o in OFF if o2[t + o])      # hug the walls when filling a pocket
            else:
                opp_terr = max(0, reach - mine - ties)
                score = mine - opp_terr / n_opp
                if hard and mine < 40:
                    # a narrow passage: make sure it is not a pocket that is about to close
                    n, s_ = flood(o2, t, 200)
                    score = min(score, fill_est(n, s_) - 2)
            for o in opps:          # a rival could move into t this very step: a head-on burst
                if t - o.cell in OFF and t != o.cell - OFF[o.d]:
                    score -= 30 if hard else 14
            if g.pickups and g.items:
                hx, hy = cxy(r.cell)
                tx, ty = cxy(t)
                for it in g.items:
                    ix, iy = cxy(it["cell"])
                    dd = abs(ix - hx) + abs(iy - hy)
                    if dd < 10 and abs(ix - tx) + abs(iy - ty) < dd:
                        score += (3.0 if hard else 1.5) * (1 if it["kind"] != "unravel" or r.trail_len > 60 else 0.3)
            if nd == r.d:
                score += 0.4
            score += rnd.uniform(-0.6, 0.6) if hard else rnd.uniform(-2.0, 2.0)
            if score > best_s:
                best, best_s, best_sep = (nd, t), score, sep
        if not hard and rnd.random() < 0.02:
            best = rnd.choice(cands)
        nd, t = best
        boost = False
        if opps and not best_sep and r.meter > 0.25:
            ahead = 0
            c = t
            while ahead < 4 and not occ[c + OFF[nd]]:
                c += OFF[nd]
                ahead += 1
            near = min(abs(cxy(o.cell)[0] - cxy(t)[0]) + abs(cxy(o.cell)[1] - cxy(t)[1]) for o in opps)
            if hard:
                boost = ahead >= 3 and near <= 12 and best_s >= -5
            else:
                boost = ahead >= 4 and r.meter > 0.6 and rnd.random() < 0.25
        return nd, boost

    def simple(self, g, r):
        """Easy (and the self-test's stand-in for a casual player, 'rookie'): straight on until something is
        close ahead, then the turn with the most room in a short glance."""
        rnd = self.rnd
        occ = g.grid.translate(TBL)
        rook = self.skill == "rookie"
        free = 0
        c = r.cell
        while free < 6 and not occ[c + OFF[r.d]]:
            c += OFF[r.d]
            free += 1
        wander = rnd.random() < (0.05 if rook else 0.07)
        if free > self.react and not wander:
            self.react = 1 + rnd.randrange(3) if not rook else 1 + rnd.randrange(2)
            return r.d, (not rook and rnd.random() < 0.01) or (rook and free >= 5 and r.meter > 0.7 and rnd.random() < 0.1)
        cands = []
        for nd in (r.d, (r.d + 1) % 4, (r.d + 3) % 4):
            t = r.cell + OFF[nd]
            if not occ[t]:
                cands.append((nd, t))
        if not cands:
            return r.d, False
        if not rook and rnd.random() < 0.06:
            return rnd.choice(cands)[0], False
        best, bs = cands[0][0], -1e9
        cap = 70 if rook else 22
        for nd, t in cands:
            o2 = bytearray(occ)
            o2[t] = 1
            n, _ = flood(o2, t, cap)
            s = min(n, cap) + rnd.uniform(-3, 3) + (1 if nd == r.d else 0)
            if s > bs:
                best, bs = nd, s
        return best, False


# =============================================================================================
# Drawing
# =============================================================================================
HUD_BG = (10, 9, 20)
HUD_FG = (210, 212, 232)
HUD_DIM = (136, 140, 176)
GOLD = (250, 214, 120)


def hsh(x, y, s=0):
    h = (x * 374761393 + y * 668265263 + s * 2147483647) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    return (h ^ (h >> 16)) & 0xFFFF


def blend(cv, x, y, c, a):
    if 0 <= x < cv.W and 0 <= y < cv.H:
        row = cv.px[y]
        row[x] = mix(row[x], c, a)


def glow(cv, cx, cy, r0, r1, c, k=0.55):
    """A soft halo from radius r0 out to r1 (screen pixels)."""
    W, H = cv.W, cv.H
    y0, y1 = max(0, int(cy - r1)), min(H - 1, int(cy + r1))
    x0, x1 = max(0, int(cx - r1)), min(W - 1, int(cx + r1))
    span = max(0.01, r1 - r0)
    for py in range(y0, y1 + 1):
        row = cv.px[py]
        dy = py + 0.5 - cy
        for px in range(x0, x1 + 1):
            d = math.sqrt((px + 0.5 - cx) ** 2 + dy * dy)
            if d < r1:
                a = 1.0 if d <= r0 else (1 - (d - r0) / span)
                row[px] = mix(row[px], c, a * a * k)


class Geo:
    """Where the loom sits in a window: the cell size s (fractional below 3 pixels, whole above) and the pixel
    edges of every column and row of cells."""

    def __init__(self, cols, rows, hud):
        top = bot = 1 if hud else 0
        ah = (rows - top - bot) * 2
        s = min((cols - 2) / GW, (ah - 2) / GH)
        if s >= 3:
            s = float(int(s))
        self.s = s
        fw, fh = GW * s, GH * s
        self.ox = (cols - fw) / 2
        self.oy = top * 2 + (ah - fh) / 2
        self.XS = [int(round(self.ox + i * s)) for i in range(GW + 1)]
        self.YS = [int(round(self.oy + i * s)) for i in range(GH + 1)]
        self.CX = [self.XS[i] + anchor(self.XS[i + 1] - self.XS[i]) for i in range(GW)]
        self.CY = [self.YS[i] + anchor(self.YS[i + 1] - self.YS[i]) for i in range(GH)]

    def px(self, x, y):
        """Cell coordinates (centre of cell i = i + 0.5) to screen pixels, through the cells' thread anchors."""
        fx, fy = x - 0.5, y - 0.5
        i, j = int(clamp(math.floor(fx), 0, GW - 2)), int(clamp(math.floor(fy), 0, GH - 2))
        tx, ty = fx - i, fy - j
        return (self.CX[i] + (self.CX[i + 1] - self.CX[i]) * tx, self.CY[j] + (self.CY[j + 1] - self.CY[j]) * ty)


def anchor(w):
    """Where a thread runs inside a cell w pixels wide: through the middle, or along the first pixel of a
    small cell (so neighbouring threads keep a dark pixel between them)."""
    return w / 2 if w >= 3 else 0.5


def core_px(s):
    return max(0.5, 0.22 * s)


def thread_light(d, cw, gl):
    """Light of a thread at distance d (pixels) from its centre line: 1 in the core, a glow beyond."""
    if d <= cw:
        return 1.0
    return 0.72 * math.exp(-(d - cw) / gl)


def arm_dist(x, y, ax, ay, w, h, mask):
    best = math.hypot(x - ax, y - ay)
    if mask & 1 and y <= ay:
        best = min(best, abs(x - ax))
    if mask & 2 and x >= ax:
        best = min(best, abs(y - ay))
    if mask & 4 and y >= ay:
        best = min(best, abs(x - ax))
    if mask & 8 and x <= ax:
        best = min(best, abs(y - ay))
    return best


_STAMP = {}


def floor_stamp(w, h, par, lvl, ai):
    key = ("f", w, h, par, lvl, ai)
    st = _STAMP.get(key)
    if st:
        return st
    ar = ARENAS[ai]
    b = shade(ar["floor"], 1.0 - 0.075 * lvl)
    if par:
        b = shade(b, 1.06)
    warp = mix(b, ar["accent"], 0.05)
    weft = mix(b, ar["accent"], 0.025)
    rows = []
    for j in range(h):
        row = []
        for i in range(w):
            c = b
            if w >= 4 and h >= 4:
                if i == 0 and j == 0:
                    c = mix(b, ar["accent"], 0.08)
                elif i == 0:
                    c = warp if par else weft      # over and under: the loom's own cloth
                elif j == 0:
                    c = weft if par else warp
                elif w >= 5 and (i + j * 3 + par * 2) % 7 == 3:
                    c = shade(b, 1.05)
            row.append(c)
        rows.append(row)
    _STAMP[key] = rows
    return rows


def thread_stamp(w, h, par, lvl, ai, col, mask, dead, s):
    key = ("t", w, h, par, lvl, ai, col, mask, dead, s)
    st = _STAMP.get(key)
    if st:
        return st
    fl = floor_stamp(w, h, par, lvl, ai)
    cw, gl = core_px(s), max(0.6, 0.3 * s)
    c = shade(col, 0.62) if dead else col
    hot = mix(c, WHITE, 0.4 if not dead else 0.2)
    ax, ay = anchor(w), anchor(h)
    rows = []
    for j in range(h):
        row = []
        for i in range(w):
            d = arm_dist(i + 0.5, j + 0.5, ax, ay, w, h, mask)
            k = thread_light(d, cw, gl)
            if k >= 1.0:
                row.append(hot if (s >= 4 and d <= 0.5) else c)
            else:
                row.append(mix(fl[j][i], c, k))
        rows.append(row)
    _STAMP[key] = rows
    return rows


def post_stamp(w, h, mask, ai, par):
    """A loom post: a bevelled dark block with a thin lit edge where it meets the cloth."""
    key = ("p", w, h, mask, ai, par)
    st = _STAMP.get(key)
    if st:
        return st
    ar = ARENAS[ai]
    base = mix((40, 38, 56), ar["accent"], 0.12)
    if par:
        base = shade(base, 1.05)
    hi, lo = mix(base, WHITE, 0.25), shade(base, 0.55)
    rim = mix(base, ar["accent"], 0.7)
    rows = []
    for j in range(h):
        row = []
        for i in range(w):
            c = base
            if w >= 3 and h >= 3:
                if j == 0 and not mask & 1:
                    c = rim
                elif i == w - 1 and not mask & 2:
                    c = mix(lo, rim, 0.35)
                elif j == h - 1 and not mask & 4:
                    c = mix(lo, rim, 0.25)
                elif i == 0 and not mask & 8:
                    c = mix(hi, rim, 0.5)
                elif j == 1 and not mask & 1:
                    c = hi
                elif (i + j) % 3 == 0 and w >= 4:
                    c = shade(base, 1.1)
            elif not mask & 1 and j == 0:
                c = mix(base, rim, 0.5)
            row.append(c)
        rows.append(row)
    _STAMP[key] = rows
    return rows


def void_stamp(w, h, mask, ai, x, y):
    """Outside the loom: dark, with a lit rim on the sides that face the cloth."""
    key = ("v", w, h, mask, ai, (x * 7 + y * 3) % 5)
    st = _STAMP.get(key)
    if st:
        return st
    ar = ARENAS[ai]
    base = (6, 6, 12)
    rim = mix(base, ar["accent"], 0.75)
    rows = []
    for j in range(h):
        row = []
        for i in range(w):
            c = base
            if (i + j * 2 + key[-1]) % 9 == 0 and w >= 3:
                c = (11, 10, 20)
            e = 9
            if mask & 1:
                e = min(e, j)
            if mask & 2:
                e = min(e, w - 1 - i)
            if mask & 4:
                e = min(e, h - 1 - j)
            if mask & 8:
                e = min(e, i)
            if e == 0:
                c = rim
            elif e == 1 and w >= 3:
                c = mix(base, ar["accent"], 0.22)
            row.append(c)
        rows.append(row)
    _STAMP[key] = rows
    return rows


_BACK = {}


def backdrop(cols, rows, ai, hud):
    """Everything that never changes in a round: the room, the frame, the cloth, the posts."""
    key = (cols, rows, ai, hud)
    if key in _BACK:
        return _BACK[key]
    if len(_BACK) > 12:
        _BACK.clear()
    geo = Geo(cols, rows, hud)
    ar = ARENAS[ai]
    W, H = cols, rows * 2
    top, bot = (8, 8, 18), (14, 9, 22)
    px = []
    for y in range(H):
        b = mix(top, bot, y / max(1, H - 1))
        row = []
        for x in range(W):
            c = b
            if x % 6 == 0:
                c = mix(b, ar["accent"], 0.05)         # the loom's warp running past the cloth
            if hsh(x, y, ai) % 211 == 0:
                c = mix(b, (200, 200, 230), 0.4)
            row.append(c)
        px.append(row)
    cv = Canvas(cols, 1)
    cv.rows, cv.H, cv.px = rows, H, px
    s = geo.s
    x0, x1, y0, y1 = geo.XS[0], geo.XS[GW], geo.YS[0], geo.YS[GH]
    if s >= 1.5:
        glow(cv, (x0 + x1) / 2, (y0 + y1) / 2, 0, max(x1 - x0, y1 - y0) * 0.75, shade(ar["accent"], 0.25), 0.25) \
            if W * H < 12000 else None
        for k, a in ((3, 0.12), (2, 0.25), (1, 0.75)):
            if s < 3 and k > 1:
                continue
            c = mix((10, 10, 20), ar["accent"], a)
            cv.frame(x0 - k, y0 - k, x1 - x0 + 2 * k, y1 - y0 + 2 * k, c)
        if s >= 3:
            for cx_, cy_ in ((x0 - 2, y0 - 2), (x1 + 1, y0 - 2), (x0 - 2, y1 + 1), (x1 + 1, y1 + 1)):
                cv.rect(cx_ - 1, cy_ - 1, 3, 3, mix(ar["accent"], WHITE, 0.5))
    elif s >= 1:
        cv.frame(x0 - 1, y0 - 1, x1 - x0 + 2, y1 - y0 + 2, mix((10, 10, 20), ar["accent"], 0.6))
    grid = arena_grid(ai)
    if s >= 1:
        for y in range(GH):
            for x in range(GW):
                paint_cell(px, geo, ai, grid, x, y, None, 0, False)
    _BACK[key] = (geo, px)
    return _BACK[key]


def lvl_of(x, y):
    dx, dy = (x + 0.5 - GW / 2) / (GW / 2), (y + 0.5 - GH / 2) / (GH / 2)
    return min(5, int((dx * dx + dy * dy) * 2.2))


def paint_cell(px, geo, ai, grid, x, y, rider, mask, dead):
    x0, x1, y0, y1 = geo.XS[x], geo.XS[x + 1], geo.YS[y], geo.YS[y + 1]
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return
    i = idx(x, y)
    v = grid[i]
    par = (x + y) & 1
    if v == WALL:
        m = sum(1 << k for k in range(4) if grid[i + OFF[k]] == WALL)
        st = post_stamp(w, h, m, ai, par)
    elif v == VOID and ARENAS[ai]["f"](x, y) == VOID:
        m = sum(1 << k for k in range(4) if grid[i + OFF[k]] not in (VOID,))
        st = void_stamp(w, h, m, ai, x, y)
    elif rider is not None:
        st = thread_stamp(w, h, par, lvl_of(x, y), ai, rider.col, mask, dead, geo.s)
    else:
        st = floor_stamp(w, h, par, lvl_of(x, y), ai)
    for j in range(h):
        px[y0 + j][x0:x1] = st[j]


class Painter:
    """Keeps the woven loom as a picture and repaints only the cells that changed since the last frame."""

    def __init__(self):
        self.key = None

    def layer(self, g, cols, rows, hud):
        key = (cols, rows, hud, g.round_id, g.ai)
        geo, base = backdrop(cols, rows, g.ai, hud)
        if key != self.key:
            self.key = key
            self.px = [r[:] for r in base]
            self.seen = 0
            if geo.s >= 1:
                for c in range(NCELL):
                    v = g.grid[c]
                    if 1 <= v <= 5:
                        self.cell(g, geo, c)
                self.seen = len(g.changes)
        if geo.s >= 1:
            ch = g.changes
            if self.seen > len(ch):
                self.seen = 0
            for c in ch[self.seen:]:
                self.cell(g, geo, c)
            self.seen = len(ch)
        return geo, self.px

    def cell(self, g, geo, c):
        x, y = cxy(c)
        if not (0 <= x < GW and 0 <= y < GH):
            return
        r, mask = g.stamp_info(c)
        if mask == -1:
            r, mask = None, 0      # the head's cell: cloth, the shuttle draws itself on top
        paint_cell(self.px, geo, g.ai, g.grid, x, y, r, mask, r is not None and not r.alive)


def beam(cv, ax, ay, bx, by, col, s):
    """A thread segment drawn live, from (ax, ay) to (bx, by) in screen pixels, with its glow."""
    cw, gl = core_px(s), max(0.6, 0.3 * s)
    ext = cw + 3 * gl
    x0, x1 = int(min(ax, bx) - ext), int(max(ax, bx) + ext) + 1
    y0, y1 = int(min(ay, by) - ext), int(max(ay, by) + ext) + 1
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    hc = mix(col, WHITE, 0.4)
    for py in range(max(0, y0), min(cv.H, y1 + 1)):
        row = cv.px[py]
        for px_ in range(max(0, x0), min(cv.W, x1 + 1)):
            qx, qy = px_ + 0.5 - ax, py + 0.5 - ay
            t = 0.0 if L2 == 0 else clamp((qx * dx + qy * dy) / L2, 0.0, 1.0)
            d = math.hypot(qx - t * dx, qy - t * dy)
            k = thread_light(d, cw, gl)
            if k >= 1.0:
                row[px_] = hc if (s >= 4 and d <= 0.5) else col
            elif k > 0.03:
                row[px_] = mix(row[px_], col, k)


def draw_shuttle(cv, g, r, geo):
    x, y = g.head_xy(r)
    sx, sy = geo.px(x, y)
    s = geo.s
    col = r.col
    t = g.clock
    lift = 0.0
    if r.hop > 0:
        lift = math.sin(min(1.0, (HOP_T - r.hop) / HOP_T) * math.pi) * 0.45 * s + 0.2 * s
    if s < 3:
        x0, y0 = int(sx), int(sy - lift)
        if s >= 1.5:
            glow(cv, x0 + 0.5, y0 + 0.5, 0.5, 2.6 if not r.boosting else 3.4, col, 0.5)
            if r.shield > 0:
                for o in range(4):
                    blend(cv, x0 + DX[o] * 2, y0 + DY[o] * 2, (226, 230, 255), 0.8)
        for o in range(4):
            blend(cv, x0 + DX[o], y0 + DY[o], mix(col, WHITE, 0.3), 0.85 if s >= 1.5 else 0.5)
        cv.set(x0 + DX[r.d], y0 + DY[r.d], mix(col, WHITE, 0.7)) if s >= 1.5 else None
        cv.set(x0, y0, WHITE)
        return
    if lift:
        glow(cv, sx, sy + 0.2 * s, 0, 0.8 * s, (0, 0, 0), 0.5)      # its shadow on the cloth
    sy -= lift
    k = 0.5 + (0.25 if r.boosting else 0) + 0.08 * math.sin(t * 9 + r.k)
    glow(cv, sx, sy, 0.3 * s, (2.2 if r.boosting else 1.7) * s, col, k)
    if r.shield > 0 and (r.shield > 2 or int(t * 8) % 2):
        R = 1.05 * s
        n = max(10, int(R * 6))
        for i in range(n):
            a = i / n * 2 * math.pi + t * 3
            blend(cv, int(sx + math.cos(a) * R), int(sy + math.sin(a) * R), (226, 230, 255), 0.85)
    # the body: a lozenge pointing where it rides, white-hot at the nose
    fx, fy = DX[r.d], DY[r.d]
    L, Wd = 0.9 * s, 0.5 * s
    ext = int(L + 2)
    for py in range(int(sy - ext), int(sy + ext) + 1):
        if not 0 <= py < cv.H:
            continue
        row = cv.px[py]
        for px_ in range(int(sx - ext), int(sx + ext) + 1):
            if not 0 <= px_ < cv.W:
                continue
            qx, qy = px_ + 0.5 - sx, py + 0.5 - sy
            al = qx * fx + qy * fy
            ac = abs(-qx * fy + qy * fx)
            e = abs(al) / L + ac / Wd
            if e <= 1.0:
                nose = clamp((al / L + 1) / 2, 0, 1)
                c = mix(mix(col, WHITE, 0.25), WHITE, nose ** 2)
                if e > 0.8:
                    c = mix(c, shade(col, 0.6), 0.5)
                row[px_] = c
            elif e <= 1.25:
                row[px_] = mix(row[px_], col, 0.7 * (1.25 - e) / 0.25)


def draw_item(cv, g, it, geo):
    x, y = cxy(it["cell"])
    sx, sy = geo.px(x + 0.5, y + 0.5)
    s = geo.s
    name, col, _ = ITEMS[it["kind"]]
    left = ITEM_LIFE - it["t"]
    if left < 2.5 and int(g.clock * 8) % 2:
        return
    pulse = 0.5 + 0.5 * math.sin(g.clock * 5 + it["cell"])
    if s < 2.5:
        cv.set(int(sx), int(sy), mix(col, WHITE, pulse * 0.6))
        if s >= 1.5:
            for o in range(4):
                blend(cv, int(sx) + DX[o], int(sy) + DY[o], col, 0.5)
        return
    glow(cv, sx, sy, 0.1 * s, 1.3 * s, col, 0.25 + 0.2 * pulse)
    size = max(5, int(round(1.5 * s)))
    art = ITEM_ART[it["kind"]]
    key = ("i", it["kind"], size)
    img = _STAMP.get(key)
    if img is None:
        grid = [list(rw) for rw in art]
        w = max(len(rw) for rw in grid)
        grid = [rw + ["."] * (w - len(rw)) for rw in grid]
        img = scale_art(grid, size, max(4, int(size * len(art) / w)))
        _STAMP[key] = img
    h = len(img)
    x0, y0 = int(sx - size / 2), int(sy - h / 2 - math.sin(g.clock * 3 + x) * 0.15 * s)
    hi = mix(col, WHITE, 0.55 + 0.3 * pulse)
    for j, rw in enumerate(img):
        for i, ch in enumerate(rw):
            if ch == "a":
                cv.set(x0 + i, y0 + j, hi)
            elif ch == "b":
                cv.set(x0 + i, y0 + j, col)


DIGITS = {"3": ["###", "..#", "###", "..#", "###"], "2": ["###", "..#", "###", "#..", "###"],
          "1": [".#.", "##.", ".#.", ".#.", "###"]}


def big_digit(cv, ch, cx, cy, k, col):
    rows = DIGITS[ch]
    w, h = 3 * k, 5 * k
    x0, y0 = int(cx - w / 2), int(cy - h / 2)
    glow(cv, cx, cy, 0, max(w, h) * 0.9, col, 0.35)
    for j, rw in enumerate(rows):
        for i, b in enumerate(rw):
            if b == "#":
                cv.rect(x0 + i * k + 1, y0 + j * k + 1, k, k, shade(col, 0.3))
    for j, rw in enumerate(rows):
        for i, b in enumerate(rw):
            if b == "#":
                cv.rect(x0 + i * k, y0 + j * k, k, k, mix(col, WHITE, 0.45 - j * 0.08))


def render(g, cols, rows, hud=True):
    painters = g.__dict__.setdefault("_painters", {})      # one per window size (a LAN game draws several)
    painter = painters.get((cols, rows, hud))
    if painter is None:
        if len(painters) > 6:
            painters.clear()
        painter = painters[(cols, rows, hud)] = Painter()
    geo, layer = painter.layer(g, cols, rows, hud)
    ch = g.changes
    if len(ch) > 4000:                      # every painter has caught up: the list starts again
        behind = [k for k, p in painters.items() if p.seen != len(ch)]
        if len(ch) > 16000:
            for k in behind:
                del painters[k]
            behind = []
        if not behind:
            del ch[:]
            for p in painters.values():
                p.seen = 0
    cv = Canvas(cols, 1)
    cv.rows, cv.H = rows, rows * 2
    s = geo.s
    if g.shake > 0 and s >= 3:
        k = int(round(g.shake * 4))
        dy = g.rnd.randint(-k, k) if k else 0
        dx = g.rnd.randint(-k, k) if k else 0
        src = layer[dy:] + layer[:dy] if dy else layer
        cv.px = [rw[dx:] + rw[:dx] if dx else rw[:] for rw in src]
    else:
        cv.px = [rw[:] for rw in layer]
    if s < 1:
        draw_tiny(cv, g, geo)
    else:
        draw_live(cv, g, geo)
    if hud:
        draw_hud(cv, g, geo)
        draw_banners(cv, g, geo)
    return cv


def draw_tiny(cv, g, geo):
    """Windows too small for one pixel per cell (the launcher's preview): sample the loom per pixel."""
    s = geo.s
    ar = g.arena
    x0, y0 = int(geo.ox), int(geo.oy)
    w, h = int(GW * s), int(GH * s)
    for py in range(max(0, y0), min(cv.H, y0 + h)):
        cy = int((py - geo.oy + 0.5) / s)
        if not 0 <= cy < GH:
            continue
        row = cv.px[py]
        for px_ in range(max(0, x0), min(cv.W, x0 + w)):
            cx = int((px_ - geo.ox + 0.5) / s)
            if not 0 <= cx < GW:
                continue
            v = g.grid[idx(cx, cy)]
            # several cells meet in one pixel: look at the block it covers so threads never vanish
            if v == 0 and s < 0.8:
                for dyy in (0, 1):
                    for dxx in (0, 1):
                        j = idx(min(GW - 1, cx + dxx), min(GH - 1, cy + dyy))
                        if 1 <= g.grid[j] <= 5:
                            v = g.grid[j]
            if v == 0:
                row[px_] = shade(ar["floor"], 1.1)
            elif v == WALL:
                row[px_] = mix((40, 38, 56), ar["accent"], 0.3)
            elif v == VOID:
                row[px_] = (6, 6, 12)
            else:
                rr = g.riders[v - 1]
                row[px_] = rr.col if rr.alive else shade(rr.col, 0.6)
    for r in g.riders:
        if r.alive:
            x, y = g.head_xy(r)
            cv.set(int(geo.ox + x * s), int(geo.oy + y * s), WHITE)
    for p in g.parts:
        if p[4] < p[5] * 0.6:
            blend(cv, int(geo.ox + p[0] * s), int(geo.oy + p[1] * s), p[6], 0.8)


def draw_live(cv, g, geo):
    s = geo.s
    for it in g.items:
        draw_item(cv, g, it, geo)
    for f in g.flashes:
        fx_, fy_ = geo.px(f[0], f[1])
        k = 1 - f[2] / f[3]
        glow(cv, fx_, fy_, 0, (1.5 + 4.5 * f[2] / f[3]) * max(2.0, s), mix(f[4], WHITE, 0.4), 0.7 * k * k)
    # the live end of each thread: from the last woven cell to the gliding shuttle
    for r in g.riders:
        if not r.path:
            continue
        if r.alive and r.hop <= 0 and len(r.path) >= 1 and r.path[-1] >= 0:
            hx, hy = g.head_xy(r)
            ax, ay = cxy(r.vfrom)
            prev_ok = len(r.path) >= 2 and r.path[-2] == r.vfrom
            sx, sy = geo.px(hx, hy)
            if prev_ok:
                a = geo.px(ax + 0.5, ay + 0.5)
                beam(cv, a[0], a[1], sx, sy, r.col, s)
            else:
                beam(cv, sx, sy, sx, sy, r.col, s)
    for r in g.riders:
        if r.alive:
            draw_shuttle(cv, g, r, geo)
        elif r.crash_t is not None and g.clock - r.crash_t < 0.25 and s >= 2:
            x, y = g.head_xy(r)
            sx, sy = geo.px(x, y)
            glow(cv, sx, sy, 0, 1.6 * s, WHITE, 0.9 * (1 - (g.clock - r.crash_t) / 0.25))
    # burning thread ends: embers where the fire runs back along a burst rider's thread
    for r in g.riders:
        if not r.alive and r.crash_t is not None and r.path and r.burn > -0.4:
            for c in r.path[-1:]:
                if c >= 0:
                    x, y = cxy(c)
                    sx, sy = geo.px(x + 0.5, y + 0.5)
                    if s >= 2:
                        glow(cv, sx, sy, 0, 1.1 * s, (255, 220, 150), 0.7)
                    else:
                        cv.set(int(sx), int(sy), (255, 230, 170))
    for rg in g.rings:
        where, tt, life, col = rg
        if tt < 0:
            continue
        if isinstance(where, tuple):
            x, y = where
        else:
            cx_, cy_ = cxy(where)
            x, y = cx_ + 0.5, cy_ + 0.5
        sx, sy = geo.px(x, y)
        k = 1 - tt / life
        rad = (0.4 + tt / life * 3.2) * max(1.5, s)
        n = max(10, int(rad * 6))
        for i in range(n):
            a = i / n * 2 * math.pi
            blend(cv, int(sx + math.cos(a) * rad), int(sy + math.sin(a) * rad), col, k * 0.9)
    psz = max(1, int(s // 3))
    for p in g.parts:
        k = 1 - p[4] / p[5]
        sx, sy = geo.px(p[0], p[1])
        x, y = int(sx), int(sy)
        if p[7] and s >= 3:
            ex, ey = sx - p[2] * 0.03 * s, sy - p[3] * 0.03 * s     # streaks
            cv.line(x, y, ex, ey, mix(shade(p[6], 0.4), p[6], k))
        if psz == 1:
            blend(cv, x, y, p[6], 0.35 + 0.65 * k)
        else:
            cv.rect(x, y, psz, psz, mix(shade(p[6], 0.3), p[6], 0.3 + 0.7 * k))


# --- the text on top ----------------------------------------------------------------------------
def pips(r, target):
    return "●" * min(r.points, target) + "○" * max(0, target - r.points)


def draw_hud(cv, g, geo):
    cols, rows = cv.cols, cv.rows
    cv.put(0, 0, " " * cols, HUD_FG, HUD_BG)
    x = 1
    left = "R%d" % g.round_no if cols < 80 else "ROUND %d" % g.round_no
    cv.put(x, 0, left, HUD_DIM, HUD_BG)
    x += len(left) + 2
    short = cols < 70 + 12 * max(0, len(g.riders) - 2)
    for r in g.riders:
        nm = r.name[:3] if short else r.name
        col = r.col if r.alive or g.state == "intro" else shade(r.col, 0.5)
        if x + len(nm) + g.target + 3 > cols:
            break
        cv.put(x, 0, nm, col, HUD_BG)
        x += len(nm) + 1
        cv.put(x, 0, pips(r, g.target), GOLD if r.points else HUD_DIM, HUD_BG)
        x += g.target + 2
    right = g.arena["name"]
    if g.mode == "versus" and getattr(g, "rating", None) is not None:
        right = "RATING %d   %s" % (g.rating, right)
    if x + len(right) + 2 > cols:
        right = g.arena["name"] if x + len(g.arena["name"]) + 2 <= cols else ""
    if right:
        cv.put(cols - len(right) - 1, 0, right, g.arena["accent"], HUD_BG)
    # bottom line: Spur meters and charms
    r_ = rows - 1
    cv.put(0, r_, " " * cols, HUD_FG, HUD_BG)
    show = [r for r in g.riders if r.human] or g.riders
    x = 1
    bw = 10 if cols >= 90 or len(show) <= 1 else 6
    for r in show:
        nm = r.name[:3] if (len(show) > 2 or cols < 90) else r.name
        tags = []
        if r.hop > 0:
            tags.append(("SKIP", ITEMS["skip"][1]))
        if r.shield > 0:
            tags.append(("THIMBLE", ITEMS["thimble"][1]))
        if r.unravel > 0:
            tags.append(("UNRAVEL", ITEMS["unravel"][1]))
        need = len(nm) + 1 + bw + 2 + sum(len(tg) + 1 for tg, _ in tags)
        if x + need > cols:
            break
        cv.put(x, r_, nm, r.col if r.alive else shade(r.col, 0.5), HUD_BG)
        x += len(nm) + 1
        fill = r.meter * bw
        for i in range(bw):
            k = clamp(fill - i, 0, 1)
            on = mix((36, 34, 54), r.col if not r.boosting else mix(r.col, WHITE, 0.4), k)
            cv.put(x + i, r_, "▀" if k > 0 else " ", mix(on, WHITE, 0.15) if k > 0 else on, on)
        x += bw + 1
        for tg, c in tags:
            cv.put(x, r_, tg, c, HUD_BG)
            x += len(tg) + 1
        x += 1
    if g.mode in ("duel", "lan") or not g.humans():
        tag = "first to %d" % g.target
    else:
        tag = "first to %d  %s" % (g.target, "/".join(sorted({r.skill.capitalize() for r in g.riders if r.brain})))
    if cols - len(tag) - 1 > x + 1:
        cv.put(cols - len(tag) - 1, r_, tag, HUD_DIM, HUD_BG)


def banner(cv, lines, col, row=None):
    w = max(len(l) for l in lines) + 4
    x = max(0, (cv.cols - w) // 2)
    y = max(1, cv.rows // 2 - len(lines) // 2) if row is None else row
    cv.box(x, y, [l.center(w - 4) for l in lines], (236, 236, 244), (18, 16, 34))
    cv.put(x + 2, y + 1, lines[0].center(w - 4), col, (18, 16, 34))


def draw_banners(cv, g, geo):
    s = geo.s
    if g.state == "intro":
        st = g.state_t
        top = "ROUND %d  -  %s" % (g.round_no, g.arena["name"])
        cv.center(max(1, int(geo.YS[0] // 2) + 1), " %s " % top, g.arena["accent"], (18, 16, 34))
        if st > 0.3 and cv.rows >= 18:
            for r in g.riders:
                x, y = cxy(r.cell)
                sx, sy = geo.px(x + 0.5, y + 0.5)
                row = int(sy // 2) + (2 if r.d != 0 else -2)
                nm = r.name + (" (you)" if r.ctl == "p1" and g.mode == "versus" else "")
                if r.ctl == "p1" and g.mode == "duel":
                    nm += " W A S D"
                elif r.ctl == "p2":
                    nm += " arrows"
                cv.put(int(clamp(sx - len(nm) / 2, 1, cv.cols - len(nm) - 1)), int(clamp(row, 1, cv.rows - 2)), nm,
                       r.col, (14, 12, 26))
        for r in g.riders:          # where each shuttle will set off: pulsing dots ahead of it
            x, y = cxy(r.cell)
            for k in range(1, 4):
                c = r.cell + OFF[r.d] * k
                if g.grid[c]:
                    break
                a = 0.5 + 0.5 * math.sin(g.clock * 8 - k * 1.2)
                sx, sy = geo.px(x + 0.5 + DX[r.d] * k, y + 0.5 + DY[r.d] * k)
                if s >= 3:
                    glow(cv, sx, sy, 0, 0.35 * s, r.col, 0.8 * a)
                else:
                    blend(cv, int(sx), int(sy), r.col, 0.3 + 0.5 * a)
        sec = int(st / 0.8 - 0.75)
        if 0 <= sec < 3 and st >= 0.6:
            ch = "321"[sec]
            k = max(1, int(s * 1.6)) if s >= 1.5 else 0
            if k and 5 * k < geo.YS[GH] - geo.YS[0]:
                big_digit(cv, ch, (geo.XS[0] + geo.XS[GW]) / 2, (geo.YS[0] + geo.YS[GH]) / 2, k,
                          g.arena["accent"])
            else:
                cv.center(cv.rows // 2, "  %s  " % ch, (20, 16, 30), g.arena["accent"])
    elif g.state == "play" and g.state_t < 0.7 and g.round_t < 0.7:
        k = 2 if cv.cols >= 80 and s >= 2.5 else 1
        wd = len("WEAVE") * 6 * k - k
        x = (cv.cols - wd) // 2
        y = int((geo.YS[0] + geo.YS[GH]) / 2 - 2.5 * k)
        block_title(cv, "WEAVE", x, y, k, mix(g.arena["accent"], WHITE, 0.5), g.arena["accent"])
    elif g.state == "end" and g.state_t > 0.5:
        w = g.round_winner
        if w:
            lines = ["%s TAKES THE ROUND" % w.name, ""]
            lines += ["%s  %s" % (r.name.ljust(9), pips(r, g.target)) for r in g.standings()]
            banner(cv, lines, w.col)
        else:
            lines = ["ALL THREADS CUT - NO ROUND", ""]
            lines += ["%s  %s" % (r.name.ljust(9), pips(r, g.target)) for r in g.standings()]
            banner(cv, lines, (230, 230, 240))
    elif g.state == "play" and g.mode == "versus" and not any(r.alive for r in g.humans()) and cv.rows >= 16:
        cv.center(cv.rows - 3, " your shuttle burst - the rivals settle the round ", HUD_DIM, (18, 16, 34))


def render_over(g, cv, auto=False, extra=(), hint=None):
    w = g.winner
    lines = ["%s WINS THE MATCH" % w.name, ""]
    lines += ["%-9s %s  rounds %d  cuts %d  woven %d" % (r.name, pips(r, g.target), r.rounds, r.cuts, r.cells)
              for r in g.standings()]
    lines += list(extra)
    lines += ["", hint or ("auto mode: a new match starts" if auto else "Enter: rematch   Esc / Q: menu")]
    wd = max(len(l) for l in lines) + 4
    x, y = max(0, (cv.cols - wd) // 2), max(0, cv.rows // 2 - len(lines) // 2 - 1)
    cv.frame(x - 1, y * 2 - 1, wd + 2, (len(lines) + 2) * 2 + 2, w.col)
    cv.box(x, y, [l.center(wd - 4) for l in lines], (240, 240, 246), (22, 20, 42))
    cv.put(x + 2, y + 1, lines[0].center(wd - 4), w.col, (22, 20, 42))


# =============================================================================================
# Ratings
# =============================================================================================
def rate(rating, g):
    """Elo-style: the human against each computer rider; a match win counts as beating them all, otherwise
    whoever has more rounds counts as ahead."""
    me = next(r for r in g.riders if r.ctl == "p1")
    opps = [r for r in g.riders if r.brain]
    if not opps:
        return rating, 0
    tot = 0.0
    for o in opps:
        if g.winner is me:
            sc = 1.0
        else:
            sc = 1.0 if me.points > o.points else 0.5 if me.points == o.points else 0.0
        ro = SKILL_RATING[o.skill] + 60 * (len(opps) - 1)
        ex = 1 / (1 + 10 ** ((ro - rating) / 400))
        tot += sc - ex
    delta = int(round(36 * tot / len(opps) * (1 + 0.25 * (len(opps) - 1))))
    return rating + delta, delta


def load_rating():
    v = load_settings().get("weftwar_rating")
    return int(v) if isinstance(v, (int, float)) else 1000


# =============================================================================================
# Title demo, controls, menu, main loop
# =============================================================================================
def auto_riders(rnd):
    n = rnd.choice((2, 3, 4, 4))
    cis = rnd.sample(range(len(RIDERS)), n)
    return [(ci, "cpu", rnd.choice(("normal", "hard", "hard"))) for ci in cis]


class TitleDemo:
    """Computer riders weaving on the looms in turn, behind the title (and in the launcher preview)."""

    def __init__(self, k=0):
        self.k = k
        self.new_run()

    def new_run(self):
        rnd = random.Random(self.k * 7 + 3)
        self.g = Game(auto_riders(rnd), target=99, arena=self.k % len(ARENAS), pickups=True, seed=self.k + 11,
                      quiet=True, mode="demo")
        self.g.state, self.g.state_t = "play", 1.0
        for _ in range(int(2.5 / DT)):
            self.g.step()
        self.k += 1

    def scene(self, cols, rows, dt):
        g = self.g
        g.update(min(dt, 0.1))
        if g.round_no > 1 or g.over:
            self.new_run()
        return render(self.g, cols, rows, hud=False)


P1_DIRS = {"w": 0, "d": 1, "s": 2, "a": 3}
P2_DIRS = {"up": 0, "right": 1, "down": 2, "left": 3}
P1_BOOST = (" ", "e")
P2_BOOST = ("enter", "0", "/")


class Controls:
    """Turn presses go into a short queue per rider (so a quick double turn works); Spur counts while held."""

    def __init__(self, kitty, solo=False):
        self.kitty = kitty
        self.solo = solo
        self.held = HeldKeys(kitty, first=0.5, repeat=0.13)
        self.q = {"p1": [], "p2": []}
        self.now = 0.0

    def reset(self):
        self.held.clear()
        self.q = {"p1": [], "p2": []}

    def feed(self, name, kind, now):
        self.now = now
        self.held.feed(name, kind, now)
        if kind == "press":
            if name in P1_DIRS:
                self.q["p1"].append(P1_DIRS[name])
            elif name in P2_DIRS:
                self.q["p1" if self.solo else "p2"].append(P2_DIRS[name])
        self.held.take_hits()

    def tick(self, now):
        self.now = now
        self.held.tick(now)

    def turns(self, who):
        t, self.q[who] = self.q[who], []
        return t

    def boost(self, who):
        if self.solo:
            return self.held.down(*(P1_BOOST + P2_BOOST))
        return self.held.down(*(P1_BOOST if who == "p1" else P2_BOOST))


class AutoRun:
    """Auto mode: computer riders play whole matches on the chosen loom setting; after a match the result stays
    for a few seconds and the next one starts. Nothing is recorded."""
    OVER_SHOW = 4.0

    def __init__(self, setup, sound=True, seed=None):
        self.setup, self.sound, self.seed = setup, sound, seed
        self.rnd = random.Random(seed)
        self.auto = AutoMode()
        self.rounds = 0
        self.new()

    def new(self):
        self.rounds += 1
        self.g = Game(auto_riders(self.rnd), target=self.setup.get("target", 3), arena=self.setup.get("arena", -1),
                      pickups=self.setup.get("pickups", True), quiet=not self.sound,
                      seed=None if self.seed is None else self.seed * 31 + self.rounds, mode="auto")
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
                g.fx(dt)
            if self.over_t >= self.OVER_SHOW:
                self.new()
                g = self.g
        else:
            for _ in range(self.auto.steps(dt, DT)):
                g.step()
                if g.over:
                    break
        if not draw:
            return None
        cv = render(g, cols, rows)
        if g.over:
            render_over(g, cv, auto=True)
        self.auto.banner(cv, extra="match %d" % self.rounds)
        return cv


MIN_COLS, MIN_ROWS = 60, 22


def too_small(term):
    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (%dx%d)." % (MIN_COLS, MIN_ROWS))


def run_auto(term, setup):
    run = AutoRun(setup)
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


DEFAULT_SETUP = dict(rivals=1, skill="normal", target=3, arena=-1, pickups=True)


def load_setup():
    s = dict(DEFAULT_SETUP)
    v = load_settings().get("weftwar_setup")
    if isinstance(v, dict):
        for k in s:
            if k in v and isinstance(v[k], type(s[k])):
                s[k] = v[k]
    s["rivals"] = int(clamp(s["rivals"], 1, 3))
    s["skill"] = s["skill"] if s["skill"] in SKILLS else "normal"
    s["target"] = s["target"] if s["target"] in TARGETS else 3
    s["arena"] = int(clamp(s["arena"], -1, len(ARENAS) - 1))
    return s


def menu_items(st):
    return ["Duel - two riders, one keyboard",
            "Versus the computer",
            "Rivals    < %d >" % st["rivals"],
            "Skill     < %s >" % st["skill"].capitalize(),
            "Match     < first to %d >" % st["target"],
            "Loom      < %s >" % ("rotate" if st["arena"] < 0 else ARENAS[st["arena"]]["name"].title()),
            "Charms    < %s >" % ("on" if st["pickups"] else "off"),
            "LAN game  2 to 4 computers",
            AUTO_LABEL]


def change(st, sel, d):
    if sel == 2:
        st["rivals"] = (st["rivals"] - 1 + d) % 3 + 1
    elif sel == 3:
        st["skill"] = SKILLS[(SKILLS.index(st["skill"]) + d) % 3]
    elif sel == 4:
        st["target"] = TARGETS[(TARGETS.index(st["target"]) + d) % len(TARGETS)]
    elif sel == 5:
        st["arena"] = (st["arena"] + 1 + d) % (len(ARENAS) + 1) - 1
    elif sel == 6:
        st["pickups"] = not st["pickups"]
    else:
        return False
    return True


def render_menu(demo, cols, rows, sel, st, dt, help_, kitty, rating, duel_tally):
    cv = demo.scene(cols, rows, dt)
    rec = load_scores().get(GAME, {})
    bits = ["rating %d" % rating]
    if rec.get("rating"):
        bits.append("peak %d" % rec["rating"])
    if rec.get("won"):
        bits.append("matches won %d" % rec["won"])
    if rec.get("streak"):
        bits.append("streak %d" % rec["streak"])
    best = "   ".join(bits)
    extra = ["", "Every cell you cross is woven shut behind you.",
             "Cut your rivals off; the last rider weaving wins."]
    if duel_tally and sum(duel_tally) and rows >= 34:
        extra.append("Duels today: Saffron %d - %d Woad" % tuple(duel_tally))
    if rows >= 32:
        extra.append("Keys: %s" % ("with releases (kitty protocol)" if kitty else "classic terminal mode"))
    title_screen(cv, NAME, TAGLINE, menu_items(st), sel, best, extra=extra,
                 keys="Up/Down choose   Left/Right change   Enter start   M %s   ? help   Esc back" % SND.label().lower(),
                 help_lines=help_lines(kitty), show_help=help_, dim=0.5)
    return cv


def make_game(mode, st, seed=None, quiet=False):
    if mode == "duel":
        riders = [(0, "p1", "normal"), (1, "p2", "normal")]
    else:
        riders = [(0, "p1", "normal")] + [(2 + i, "cpu", st["skill"]) for i in range(st["rivals"])]
    return Game(riders, target=st["target"], arena=st["arena"], pickups=st["pickups"], seed=seed, quiet=quiet,
                mode=mode)


class Session:
    def __init__(self):
        self.rating = load_rating()
        self.streak = 0
        self.duels = [0, 0]


def finish(g, ses):
    """Record a finished match. Returns the extra lines for the result box."""
    if g.mode == "duel":
        ses.duels[0 if g.winner.ctl == "p1" else 1] += 1
        return ["", "duels today: Saffron %d - %d Woad" % tuple(ses.duels)]
    new, delta = rate(ses.rating, g)
    ses.rating = new
    save_settings(weftwar_rating=new)
    won = g.winner.ctl == "p1"
    ses.streak = ses.streak + 1 if won else 0
    lines = ["", "rating %d  (%+d)" % (new, delta)]
    if submit(GAME, "rating", new):
        lines.append("** NEW PEAK RATING **")
    if won:
        submit(GAME, "won", (load_scores().get(GAME, {}).get("won") or 0) + 1)
        if ses.streak > 1 and submit(GAME, "streak", ses.streak):
            lines.append("** BEST WIN STREAK: %d **" % ses.streak)
        elif ses.streak > 1:
            lines.append("win streak %d" % ses.streak)
    return lines


def play(term, ctl, mode, st, ses):
    """One match. Returns 'again' or 'menu'."""
    g = make_game(mode, st)
    g.rating = ses.rating if mode == "versus" else None
    ctl.solo = mode == "versus"
    ctl.reset()
    last = time.time()
    extra = None
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
                if name in ("enter", " ") and g.state_t > 0.6:
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
                return "menu"
            elif a == "help":
                g.help = not g.help
                g.paused = True
                ctl.reset()
            elif a == "sound":
                if SND.toggle():
                    SND.play("sound_on")
            elif a is None:
                ctl.feed(name, kind, now)
        cols, rows = term.size()
        if cols < MIN_COLS or rows < MIN_ROWS:
            too_small(term)
            g.paused = g.paused or not g.over
            time.sleep(0.2)
            last = time.time()
            continue
        ctl.tick(now)
        if not g.paused:
            g.update(dt, ctl)
            if g.over:
                g.state_t += dt
        if g.over and extra is None:
            extra = finish(g, ses)
            g.rating = ses.rating if mode == "versus" else None
        cv = render(g, cols, rows)
        if g.paused:
            overlay(cv, help_lines(ctl.kitty) if g.help else PAUSE_LINES + ["", SND.label()])
        elif g.over:
            render_over(g, cv, extra=extra or ())
        term.write(cv.emit())
        time.sleep(max(0.0, 1 / 30 - (time.time() - now)))


# =============================================================================================
# The LAN game: two to four riders, each at their own computer (see arcadenet)
# =============================================================================================
LAN_PAUSE = ["P A U S E D", "", "Esc / P / Enter   continue", "?                 help", "M                 sound on / off",
             "V                 view", "Q                 end the match for everyone", "", "(the others wait)"]


def lan_spec(demo, st):
    def info():
        return "first to %d   loom: %s   charms %s" % (
            st["target"], "rotate" if st["arena"] < 0 else ARENAS[st["arena"]]["name"].title(),
            "on" if st["pickups"] else "off")
    return arcadenet.LanGame(GAME, NAME, match=lambda term, srv: lan_match(term, srv, st),
                             backdrop=lambda cols, rows, dt: demo.scene(cols, rows, dt), help=help_lines, info=info,
                             players=(2, 4), size=(MIN_COLS, MIN_ROWS), sound=SND)


class LanControls:
    """Game.step asks for turns and Spur by rider: each rider's own Controls (alone, so either set of keys)."""

    def __init__(self):
        self.of = {}

    def turns(self, who):
        c = self.of.get(who)
        return c.turns("p1") if c else []

    def boost(self, who):
        c = self.of.get(who)
        return c.boost("p1") if c else False


def lan_frame(g, cols, rows):
    cv = render(g, cols, rows)
    if g.paused:
        overlay(cv, ["P A U S E D", "", "the host paused the game"])
    elif g.over:
        render_over(g, cv, hint="the host starts the next match")
    return cv


def lan_match(term, srv, st):
    """The host's match. Returns 'lobby' (Enter after the match) or 'quit'."""
    kitty = getattr(term, "kitty", False)
    seats = srv.seats[:4]
    g = Game([(i, "p%d" % (i + 1), "normal") for i in range(len(seats))], target=st["target"], arena=st["arena"],
             pickups=st["pickups"], mode="lan")
    for r, seat in zip(g.riders, seats):
        r.name = seat["name"]
    srv.game = g
    mine = Controls(kitty, solo=True)
    lc = LanControls()
    lc.of["p1"] = mine
    far = {}
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
                mine.feed(name, kind, now)
                continue
            if g.over:
                if name in ("q", "esc"):
                    return "quit"
                if name in ("enter", " ") and g.state_t > 0.6:
                    SND.play("start")
                    return "lobby"
                continue
            a = shared_key(name, g.paused)
            if a == "pause":
                g.paused = True
                mine.reset()
                SND.play("pause")
            elif a == "resume":
                g.paused = g.help = False
                mine.reset()
            elif a == "quit":
                return "quit"
            elif a == "help":
                g.help = not g.help
                g.paused = True
                mine.reset()
            elif a == "sound":
                if SND.toggle():
                    SND.play("sound_on")
            elif a is None:
                mine.feed(name, kind, now)
        mine.tick(now)
        for r, idx, events, cleared in srv.inputs():
            c = far.get(r)
            if c is None:
                c = far[r] = Controls(r.kitty, solo=True)
                for i in idx:
                    lc.of["p%d" % (i + 1)] = c
            if cleared:
                c.reset()
            for name, kind in events:
                if not g.paused:
                    c.feed(name, kind, now)
            c.tick(now)
        for i in srv.take_left():
            if i < len(g.riders):
                rd = g.riders[i]
                lc.of.pop(rd.ctl, None)
                rd.ctl, rd.skill = "cpu", "normal"
                rd.brain = Brain("normal", g.rnd.random())
        if not g.paused:
            g.update(dt, lc)
            if g.over:
                g.state_t += dt
        srv.send_frames(now, lambda cols, rows, seats_: lan_frame(g, cols, rows))
        cols, rows = term.size()
        if cols < MIN_COLS or rows < MIN_ROWS:
            too_small(term)
            time.sleep(0.2)
            continue
        cv = render(g, cols, rows)
        if g.paused:
            overlay(cv, help_lines(kitty) if g.help else LAN_PAUSE)
        elif g.over:
            render_over(g, cv, hint="Enter: back to the lobby   Esc / Q: end")
        elif srv.recent():
            cv.put(0, 0, " %s " % srv.recent(), (230, 230, 240), (30, 30, 50))
        term.write(cv.emit())
        time.sleep(max(0.0, 1 / 30 - (time.time() - now)))


def main():
    with KeyTerminal() as term:
        ctl = Controls(term.kitty)
        demo = TitleDemo()
        st = load_setup()
        ses = Session()
        sel, help_ = 0, False
        n_items = len(menu_items(st))
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
            term.write(render_menu(demo, cols, rows, sel, st, min(0.1, now - last), help_, ctl.kitty, ses.rating,
                                   ses.duels).emit())
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
                    sel = (sel + 1) % n_items
                    SND.play("menu")
                elif k in ("up", "w"):
                    sel = (sel - 1) % n_items
                    SND.play("menu")
                elif k in ("left", "a", "right", "d"):
                    if change(st, sel, -1 if k in ("left", "a") else 1):
                        SND.play("menu")
                elif k == "m":
                    if SND.toggle():
                        SND.play("sound_on")
                elif k in ("enter", " "):
                    if change(st, sel, 1):
                        SND.play("menu")
                        continue
                    SND.play("start")
                    go = True
            if not go:
                continue
            save_settings(weftwar_setup=dict(st))
            if sel == n_items - 1:
                run_auto(term, st)
            elif sel == n_items - 2:
                arcadenet.lan_menu(term, lan_spec(demo, st))
                ctl.reset()
            else:
                mode = "duel" if sel == 0 else "versus"
                while play(term, ctl, mode, st, ses) == "again":
                    pass
            last = time.time()


# =============================================================================================
# Self-test
# =============================================================================================
def duel_bots(a, b, rounds, seed, arena=-1, pickups=True, limit=150.0):
    """Two computer riders of the given skills fight single rounds. Returns (wins a, wins b, draws, secs)."""
    wa = wb = dr = 0
    secs = 0.0
    for i in range(rounds):
        sk = (a, b) if i % 2 == 0 else (b, a)
        g = Game([(2, "cpu", sk[0]), (3, "cpu", sk[1])], target=1, arena=(i % len(ARENAS)) if arena < 0 else arena,
                 pickups=pickups, seed=seed * 1000 + i, quiet=True, mode="auto")
        g.state, g.state_t = "play", 0.0
        t = 0.0
        while g.state == "play" and t < limit:
            g.step()
            t += DT
        secs += t
        w = g.round_winner
        if w is None:
            dr += 1
        elif (w.k == 1) == (i % 2 == 0):
            wa += 1
        else:
            wb += 1
    return wa, wb, dr, secs


def selftest():
    t0 = time.time()
    global submit, save_settings

    def no_writes(*a, **k):
        raise AssertionError("the self-test must not write scores or settings")
    submit = no_writes
    save_settings = no_writes
    random.seed(3)
    # 1. the looms: spawns on free cloth with room ahead, all cloth connected, nothing outside the frame
    for ai, ar in enumerate(ARENAS):
        gr = arena_grid(ai)
        free = [c for c in range(NCELL) if gr[c] == 0]
        n, _ = flood(gr.translate(TBL), free[0])
        assert n + 1 == len(free), "%s: the cloth falls apart into pieces" % ar["name"]
        for sp in (SP2, SP4):
            cells = set()
            for x, y, d in sp:
                c = idx(x, y)
                assert gr[c] == 0, "%s: spawn %d,%d blocked" % (ar["name"], x, y)
                for k in range(1, 6):
                    assert gr[c + OFF[d] * k] == 0, "%s: spawn %d,%d has no room ahead" % (ar["name"], x, y)
                cells.add(c)
            assert len(cells) == len(sp)
        for c in range(NCELL):
            x, y = cxy(c)
            if not (0 <= x < GW and 0 <= y < GH):
                assert gr[c] == VOID
    print("looms: %d, every one connected, spawns for 2 and 4 riders with room ahead (%s)" % (
        len(ARENAS), ", ".join("%s %d" % (a["name"].title(), sum(1 for c in arena_grid(i) if c == 0))
                               for i, a in enumerate(ARENAS))))
    # 2. the rules
    def fresh(n=2, arena=0, pickups=False):
        g = Game([(i, "p1" if i == 0 else "p2" if i == 1 else "cpu", "normal") for i in range(n)], target=2,
                 arena=arena, pickups=pickups, seed=5, quiet=True)
        g.state, g.state_t = "play", 0.0
        return g

    class Ctl:
        def __init__(self):
            self.t = {"p1": [], "p2": []}
            self.b = {"p1": False, "p2": False}

        def turns(self, w):
            t, self.t[w] = self.t[w], []
            return t

        def boost(self, w):
            return self.b[w]

    g = fresh()
    a, b = g.riders
    c0 = a.cell
    for _ in range(int(1.0 / DT)):
        g.step(Ctl())
    assert abs(cxy(a.cell)[0] - cxy(c0)[0] - SPEED) <= 1, "speed: %d cells in 1 s" % (cxy(a.cell)[0] - cxy(c0)[0])
    assert all(g.grid[c] == a.k for c in a.path if c >= 0) and len(a.path) == a.cells + 1
    ctl = Ctl()
    ctl.t["p1"] = [3]                     # reverse: ignored
    g.step(ctl)
    assert a.d == 1, "a reverse turn was taken"
    ctl.t["p1"] = [0, 3]                  # a quick double turn: up, then left on the next cell
    for _ in range(30):
        g.step(ctl)
    assert a.d == 3, "the queued second turn was lost (d=%d)" % a.d
    for _ in range(int(3 / DT)):
        g.step(Ctl())
        if not a.alive:
            break
    assert not a.alive and g.state == "end" and g.round_winner is b and b.points == 1, "riding into own thread"
    g = fresh()                           # into the frame
    a, b = g.riders
    b.d = 0
    for _ in range(int(6 / DT)):
        ctl = Ctl()
        g.step(ctl)
        if g.state != "play":
            break
    assert not a.alive and not b.alive or g.round_winner is not None, "nobody crashed into the frame"
    g = fresh()                           # head-on: both burst, no point
    a, b = g.riders
    for r in (a, b):
        g.grid[r.cell] = 0
    a.place(idx(10, 5), 1)
    b.place(idx(14, 5), 3)
    for r in (a, b):
        g.grid[r.cell] = r.k
    for _ in range(int(1 / DT)):
        g.step(Ctl())
    assert not a.alive and not b.alive and g.round_winner is None and a.points == b.points == 0, "head-on"
    g = fresh()                           # into a rival's thread: a cut for the rival
    a, b = g.riders
    for x in range(GW):
        if g.grid[idx(x, 20)] == 0:
            g.grid[idx(x, 20)] = b.k
    a.d = 2
    for _ in range(int(3 / DT)):
        g.step(Ctl())
    assert not a.alive and b.cuts == 1, "a cut was not counted"
    # Spur: faster and it drains; it refills slowly
    g = fresh()
    a, b = g.riders
    ctl = Ctl()
    ctl.b["p1"] = True
    x0 = cxy(a.cell)[0]
    for _ in range(int(1 / DT)):
        ctl.b["p1"] = True
        g.step(ctl)
    assert cxy(a.cell)[0] - x0 >= SPEED * BOOST_K - 1 and abs(a.meter - (1 - DRAIN)) < 0.05, "Spur"
    m = a.meter
    for _ in range(int(1 / DT)):
        g.step(Ctl())
    assert abs(a.meter - m - REGEN) < 0.02
    # charms: Skip crosses a thread and leaves a gap, Thimble tears through, Unravel sheds, Spur refills
    g = fresh()
    a, b = g.riders
    wall = [idx(20, y) for y in range(GH)]
    for c in wall:
        g.grid[c] = b.k
    while cxy(a.cell)[0] < 15:
        g.step(Ctl())
    g.take(a, dict(kind="skip", cell=a.cell))
    for _ in range(int(2.0 / DT)):
        g.step(Ctl())
    assert a.alive and cxy(a.cell)[0] > 20 and -1 in a.path, "Skip did not cross the thread"
    assert any(g.grid[idx(x, cxy(a.cell)[1])] == 0 for x in range(16, 20)), "Skip left no gap"
    g = fresh()
    a, b = g.riders
    for c in wall:
        g.grid[c] = b.k
    b.path = [b.cell] + wall
    for i, c in enumerate(b.path):
        g.pos[c] = i
    g.take(a, dict(kind="thimble", cell=a.cell))
    for _ in range(int(2.0 / DT)):
        g.step(Ctl())
    assert a.alive and cxy(a.cell)[0] > 20 and a.shield == 0, "Thimble did not tear through"
    for _ in range(int(3.0 / DT)):
        g.step(Ctl())
    n0 = a.trail_len
    g.take(a, dict(kind="unravel", cell=a.cell))
    for _ in range(int(1.5 / DT)):
        g.step(Ctl())
        if not a.alive:
            break
    assert a.trail_len < n0 * 0.75 and all(g.grid[c] == a.k for c in a.path if c >= 0), "Unravel"
    a.meter = 0.1
    g.take(a, dict(kind="spur", cell=a.cell))
    assert a.meter == 1.0
    # a burst rider's thread burns away; matches end at the target
    g = fresh()
    a, b = g.riders
    for _ in range(int(2 / DT)):
        g.step(Ctl())
    g.crash(a, None, a.cell + OFF[a.d])
    for _ in range(int(2.5 / DT)):
        g.step(Ctl())
    assert not any(g.grid[c] == a.k for c in range(NCELL)), "the burst thread did not burn away"
    g = fresh()
    g.riders[1].points = 1
    g.end_round(g.riders[1])
    for _ in range(int((END_T + 0.1) / DT)):
        g.step(Ctl())
    assert g.over and g.winner is g.riders[1], "the match did not end at the target"
    g = fresh(4, 2, True)
    for _ in range(int(40 / DT)):
        g.step(Ctl())
        for c in range(0, NCELL, 7):
            v = g.grid[c]
            assert v in (0, WALL, VOID) or 1 <= v <= 4
    print("rules: speed, reverse ignored, queued double turn, own thread, frame, head-on draw, cuts, Spur drain "
          "and refill, Skip gap, Thimble tear, Unravel, burn-away, match target")
    # 3. the computer riders: win rates over single rounds on every loom, charms on
    tm = time.time()
    table = []
    for a_, b_, n in (("hard", "easy", 28), ("hard", "normal", 28), ("normal", "easy", 28), ("rookie", "easy", 28),
                      ("rookie", "normal", 28), ("hard", "rookie", 28)):
        wa, wb, dr, secs = duel_bots(a_, b_, n, seed=len(table) + 1)
        table.append((a_, b_, wa, wb, dr, secs / n))
        print("  %-6s vs %-6s  %2d : %2d  (%d draws, %.0f s per round)  %s wins %3.0f%%" % (
            a_, b_, wa, wb, dr, secs / n, a_, 100.0 * wa / max(1, wa + wb)))
    res = {(a_, b_): (wa, wb) for a_, b_, wa, wb, dr, _ in table}
    assert res["hard", "easy"][0] >= 0.85 * sum(res["hard", "easy"]), "Hard does not beat Easy reliably"
    assert res["hard", "normal"][0] > 2 * res["hard", "normal"][1], "Hard is not clearly stronger than Normal"
    assert res["normal", "easy"][0] > res["normal", "easy"][1], "Normal is not stronger than Easy"
    assert res["rookie", "easy"][0] >= res["rookie", "easy"][1], "a casual player cannot beat Easy"
    assert res["rookie", "normal"][1] > res["rookie", "normal"][0], "Normal is not stronger than a casual player"
    assert res["hard", "rookie"][0] >= 0.85 * sum(res["hard", "rookie"]), "Hard is not tough for a casual player"
    # one casual player against three computer riders: how often it is the last one weaving (fair share 25%)
    for sk in ("easy", "hard"):
        won = 0
        n = 16
        for i in range(n):
            g = Game([(0, "cpu", "rookie")] + [(2 + j, "cpu", sk) for j in range(3)], target=1, arena=i % len(ARENAS),
                     seed=500 + i, quiet=True, mode="auto")
            g.state = "play"
            while g.state == "play" and g.round_t < 150:
                g.step()
            won += g.round_winner is g.riders[0]
        print("  rookie vs 3 x %-6s rookie is last rider weaving in %d of %d rounds (%.0f%%)" % (
            sk, won, n, 100.0 * won / n))
        if sk == "hard":
            assert won <= n // 4, "three Hard riders are too easy"
    # decision time at a busy moment: four Hard riders, 3 s into a round on open cloth
    g = Game([(2, "cpu", "hard"), (3, "cpu", "hard"), (4, "cpu", "hard"), (0, "cpu", "hard")], target=9, arena=0,
             seed=4, quiet=True, mode="auto")
    g.state = "play"
    for _ in range(int(3 / DT)):
        g.step()
    worst = 0.0
    a = time.time()
    k = 0
    for r in g.riders:
        if r.alive:
            for _ in range(20):
                b = time.time()
                r.brain.decide(g, r)
                worst = max(worst, time.time() - b)
                k += 1
    print("computer riders: %.0f s of rounds above; a Hard decision with 4 riders takes %.2f ms (worst %.2f ms)" % (
        time.time() - tm, (time.time() - a) / max(1, k) * 1000, worst * 1000))
    # 4. controls
    c = Controls(False)
    c.feed("d", "press", 0.0)
    c.feed("up", "press", 0.01)
    assert c.turns("p1") == [1] and c.turns("p2") == [0]
    c.feed(" ", "press", 0.0)
    c.tick(0.3)
    assert c.boost("p1") and not c.boost("p2")
    c.tick(1.2)
    assert not c.boost("p1")
    k = Controls(True, solo=True)
    k.feed("left", "press", 0.0)
    k.feed("enter", "press", 0.0)
    assert k.turns("p1") == [3] and k.boost("p1")
    k.feed("enter", "release", 0.4)
    assert not k.boost("p1")
    print("controls: two key sets, solo maps both to you, Spur held (classic repeat window, kitty release)")
    # 5. rendering at every size
    n = 0
    timing = []
    for cols, rows in ((60, 22), (80, 24), (100, 32), (120, 40), (240, 70)):
        tr = te = 0.0
        frames = 0
        for ai in range(len(ARENAS)):
            g = Game(auto_riders(random.Random(ai)), target=3, arena=ai, seed=ai, quiet=True, mode="auto")
            g.state = "play"
            for i in range(int(7 / DT)):
                g.step()
                if i % 90 == 0:
                    render(g, cols, rows)
            for state in ("play", "intro", "end"):
                g.state, g.state_t = state, 1.2
                a = time.time()
                cv = render(g, cols, rows)
                b = time.time()
                cv.emit(True)
                c_ = time.time()
                tr += b - a
                te += c_ - b
                frames += 1
            overlay(cv, help_lines(True))
            g.over, g.winner = True, g.riders[0]
            render_over(g, cv, extra=["", "rating 1012 (+12)"])
            cv.emit(True)
        n += frames
        timing.append((cols, rows, tr / frames * 1000, te / frames * 1000))
    d = TitleDemo()
    for cols, rows in ((60, 22), (120, 40), (24, 8), (40, 12), (60, 30)):
        if rows >= 20:
            render_menu(d, cols, rows, 3, dict(DEFAULT_SETUP), 0.05, False, True, 1000, [1, 2]).emit(True)
        else:
            d.scene(cols, rows, 0.05).emit(True)
        n += 1
    for _ in range(300):
        d.scene(30, 9, 0.1)
    print("rendering: %d frames at 60x22, 80x24, 100x32, 120x40, 240x70 (+ title, preview, overlays)" % n)
    for cols, rows, r_, e_ in timing:
        print("  %3dx%-3d render %5.1f ms  emit %5.1f ms  = %5.1f ms per frame (%3.0f fps)" % (
            cols, rows, r_, e_, r_ + e_, 1000 / max(0.1, r_ + e_)))
    # a busy frame: four riders, a crash, sparks
    g = Game(auto_riders(random.Random(9)), arena=1, seed=9, quiet=True, mode="auto")
    g.state = "play"
    for _ in range(int(9 / DT)):
        g.step()
    for cols, rows in ((120, 40), (240, 70)):
        a = time.time()
        for _ in range(10):
            g.step()
            render(g, cols, rows).emit(True)
        print("  %dx%d live frames with the game running: %.1f ms" % (cols, rows, (time.time() - a) / 10 * 1000))
    # 6. auto mode: whole matches at x8; pause, speed and stop; nothing recorded
    run = AutoRun(dict(DEFAULT_SETUP), sound=False, seed=7)
    run.key(" ")
    snap = (run.g.clock, run.g.round_no)
    for _ in range(30):
        run.frame(1 / 30, 70, 22, draw=False)
    assert (run.g.clock, run.g.round_no) == snap, "auto mode ran on while paused"
    run.key(" ")
    for _ in range(5):
        run.key("+")
    assert run.auto.speed == 8.0
    secs = 25
    for i in range(secs * 30):
        run.frame(1 / 30, 70 + i % 3 * 25, 22 + i % 2 * 10, draw=i % 30 == 0)
    assert run.key("esc") == "stop"
    print("auto mode: %d s at x8, match %d round %d, nothing recorded" % (secs, run.rounds, run.g.round_no))
    # 7. rating
    g = make_game("versus", dict(DEFAULT_SETUP, rivals=2, skill="hard"), seed=1, quiet=True)
    g.over, g.winner = True, g.riders[0]
    up, d1 = rate(1000, g)
    g.winner = g.riders[1]
    g.riders[0].points, g.riders[1].points, g.riders[2].points = 1, 3, 2
    dn, d2 = rate(1000, g)
    assert d1 > 20 and d2 < 0, "rating %d %d" % (d1, d2)
    print("rating: beating two Hard riders from 1000: %+d, losing: %+d" % (d1, d2))
    # 8. simulation speed
    g = Game([(0, "cpu", "normal"), (1, "cpu", "hard")], target=99, arena=3, seed=2, quiet=True, mode="auto")
    g.state = "play"
    a = time.time()
    steps = 0
    while steps < 1800 and g.state == "play":
        g.step()
        steps += 1
    print("simulation: %.0f us per step with two computer riders" % ((time.time() - a) / max(1, steps) * 1e6))
    # 9. the LAN game: the guest turns its own shuttle; one who leaves becomes a computer rider; pictures for
    # several window sizes keep their own painters
    spec = lan_spec(TitleDemo(), dict(DEFAULT_SETUP, arena=0))
    res, frames, sounds, srv = arcadenet.try_match(spec, [(3.6, "esc"), (3.7, "q")], [(3.0, "left", "press")],
                                                   seconds=4)
    g = srv.game
    assert res == "quit" and frames >= 5 and g.mode == "lan" and g.riders[1].human, (res, frames)
    assert [r.name for r in g.riders] == ["HOST", "GUEST"] and len(g._painters) == 2, list(g._painters)
    lc = LanControls()
    lc.of["p2"] = c = Controls(False, solo=True)
    c.feed("up", "press", 0.0)
    c.feed(" ", "press", 0.0)
    assert lc.turns("p2") == [0] and lc.turns("p1") == [] and lc.boost("p2") and not lc.boost("p3")
    res, frames, sounds, srv = arcadenet.try_match(spec, [(1.0, "esc"), (1.1, "q")], [(0.1, "x", "press")],
                                                   leave=True)
    assert srv.game.riders[1].ctl == "cpu" and srv.game.riders[1].brain is not None
    lan_frame(srv.game, 120, 40).emit(True)
    print("LAN: own keys per rider, computer for one who left, a painter per window size")
    print("Self-test ok (%.1f s)" % (time.time() - t0))


def screenshot(cols=100, rows=32):
    """README picture: four computer riders on Bobbin Court (seed 5), round one, 7.6 s in: threads woven around
    the posts, a charm on the cloth, Spur sparks. Quiet, deterministic, nothing written."""
    g = Game([(0, "cpu", "hard"), (1, "cpu", "hard"), (2, "cpu", "normal"), (4, "cpu", "normal")], target=3,
             arena=1, seed=5, quiet=True, mode="auto")
    while g.state == "intro":
        g.step()
    for _ in range(int(round(7.6 / DT))):
        g.step()
    return render(g, cols, rows)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--auto" in sys.argv:
        with KeyTerminal() as _term:
            run_auto(_term, load_setup())
    else:
        main()
