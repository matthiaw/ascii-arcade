#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""SOLACE - patience on a green felt table.

Three card games for one: Klondike (draw one or three), Spider (one, two or four suits) and FreeCell (numbered
deals, the classic numbering). Drag cards with the mouse, or click one to send it where it fits best; right click
sends a card to the foundation. Unlimited undo, hints, auto-complete, a bouncing finale, best times and wins per
game. In auto mode a solver plays: greedy with care in Klondike and Spider, a real search in FreeCell.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
Run:        python3 solace.py
Self-test:  python3 solace.py --selftest
"""
import heapq
import math
import random
import sys
import time

from arcadekit import (AUTO_LABEL, PAUSE_LINES, AutoMode, Canvas, MouseTerminal, clamp, load_scores, mix, overlay,
                       shade, shared_key, submit, title_screen)
from arcadesound import Sound

GAME = "solace"
VARIANTS = ["Klondike", "Spider", "FreeCell"]
SUITS = "♠♥♦♣"
RANKS = ["", "A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
RED = (1, 2)
FELT = ((30, 112, 70), (18, 78, 48))
CARD, EDGE = (250, 248, 240), (196, 194, 184)
INK_RED, INK_BLACK = (200, 40, 50), (24, 24, 30)
BACK, BACK_L = (44, 66, 150), (96, 128, 206)
HUD_BG, HUD_FG = (14, 30, 22), (220, 232, 222)
SUIT_ART = {
    0: ["..#..", ".###.", "#####", "#####", ".#.#."],
    1: [".#.#.", "#####", "#####", ".###.", "..#.."],
    2: ["..#..", ".###.", "#####", ".###.", "..#.."],
    3: ["..#..", ".###.", "#####", "#.#.#", "..#.."],
}
SND = Sound(GAME, {
    "flick": [dict(w="noise", f=6000, f2=2500, d=0.04, v=0.18)],
    "place": [dict(w="noise", f=2200, f2=900, d=0.05, v=0.24), dict(w="tri", f=330, d=0.03, v=0.12, at=0)],
    "flip": [dict(w="noise", f=5000, f2=1800, d=0.05, v=0.2), dict(w="tri", f=660, d=0.03, v=0.1, at=0.02)],
    "found": [dict(w="tri", f=784, d=0.05, v=0.2), dict(w="tri", f=1047, d=0.08, v=0.18)],
    "run": [dict(w="tri", f=f, d=0.06, v=0.22) for f in (523, 659, 784, 1047)],
    "shuffle": [dict(w="noise", f=4000, f2=1500, d=0.03, v=0.16, at=i * 0.035) for i in range(10)],
    "draw": [dict(w="noise", f=4500, f2=2000, d=0.05, v=0.18)],
    "nope": [dict(w="square", f=160, d=0.07, v=0.16, duty=0.3)],
    "win": [dict(w="square", f=f, d=0.1, v=0.24, duty=0.25) for f in (523, 659, 784, 1047)] +
           [dict(w="tri", f=1319, d=0.6, v=0.4, vib=(6, 0.25), r="lin")],
    "menu": [dict(w="tri", f=660, d=0.025, v=0.2)],
    "start": [dict(w="noise", f=4000, f2=1500, d=0.03, v=0.16, at=i * 0.035) for i in range(6)] +
             [dict(w="tri", f=784, d=0.1, v=0.24)],
    "pause": [dict(w="tri", f=523, f2=392, d=0.07, v=0.22)],
    "sound_on": [dict(w="tri", f=440, d=0.06, v=0.35), dict(w="tri", f=880, d=0.12, v=0.35)],
})
HELP = [
    "SOLACE - keys",
    "",
    "Mouse drag            move cards (a run moves with its top card)",
    "Click a card          send it where it fits best",
    "Right click           send a card to the foundation",
    "Click the stock       draw (Klondike) / deal a row (Spider)",
    "Arrows / WASD         move the cursor      Space / Enter  pick up, drop",
    "Tab / D               draw or deal         U  undo (unlimited)",
    "H                     hint                 A  auto-complete",
    "N                     new deal             Esc / P  pause",
    "",
    "Klondike: build down in alternating colours, kings on empty columns.",
    "Spider: build down in any suit; a run of one suit moves together,",
    "and a full King-to-Ace run of one suit leaves the table.",
    "FreeCell: four free cells; how many cards move at once depends on",
    "free cells and empty columns.",
]


def card_str(c):
    return RANKS[c[0]] + SUITS[c[1]]


def red(c):
    return c[1] in RED


def ms_deal(n):
    """The classic FreeCell deal number n: a list of 52 (rank, suit) in dealing order."""
    seed = n
    cards = list(range(51, -1, -1))
    for i in range(52):
        seed = (seed * 214013 + 2531011) & 0x7fffffff
        r = seed >> 16
        j = 51 - r % (52 - i)
        cards[i], cards[j] = cards[j], cards[i]
    msuit = {0: 3, 1: 2, 2: 1, 3: 0}                  # clubs, diamonds, hearts, spades
    return [(c // 4 + 1, msuit[c % 4]) for c in cards]


# =============================================================================================
# The rules: a card is (rank, suit, uid, up)
# =============================================================================================
class Game:
    def __init__(self, variant="Klondike", opt=None, seed=None, demo=False):
        self.variant = variant
        self.demo = demo
        if opt is None:
            opt = {"Klondike": 1, "Spider": 1, "FreeCell": 1}[variant]
        self.opt = opt
        self.seed = seed if seed is not None else random.randrange(1, 1 << 30)
        self.t = 0.0
        self.clock = 0.0
        self.started = False
        self.moves = 0
        self.undo_stack = []
        self.over = self.paused = self.help = False
        self.won_t = None
        self.record = None
        self.hint = None
        self.msg, self.msg_t = "", 0.0
        self.anims = []
        self.bounce = []
        self.deal()

    @property
    def key(self):
        if self.variant == "FreeCell":
            return "FreeCell"
        return "%s %d" % (self.variant, self.opt)

    def sfx(self, name, vol=1.0):
        if not self.demo:
            SND.play(name, vol=vol)

    def say(self, msg, t=2.0):
        self.msg, self.msg_t = msg, t

    def deal(self):
        v = self.variant
        self.found = [[] for _ in range(4)]
        self.cells = [[] for _ in range(4)]
        self.stock, self.waste, self.done = [], [], []
        if v == "FreeCell":
            deck = [(r, s, i, True) for i, (r, s) in enumerate(ms_deal(self.opt))]
            self.tab = [[] for _ in range(8)]
            for i, c in enumerate(deck):
                self.tab[i % 8].append(c)
            return
        rnd = random.Random(self.seed)
        if v == "Klondike":
            deck = [(r, s, s * 13 + r, False) for s in range(4) for r in range(1, 14)]
            rnd.shuffle(deck)
            self.tab = [[] for _ in range(7)]
            for i in range(7):
                for j in range(i + 1):
                    c = deck.pop()
                    self.tab[i].append(c[:3] + (j == i,))
            self.stock = deck
            return
        suits = {1: [0], 2: [0, 1], 4: [0, 1, 2, 3]}[self.opt]
        deck = []
        uid = 0
        for k in range(8):
            s = suits[k % len(suits)]
            for r in range(1, 14):
                deck.append((r, s, uid, False))
                uid += 1
        rnd.shuffle(deck)
        self.tab = [[] for _ in range(10)]
        for i in range(54):
            self.tab[i % 10].append(deck.pop())
        for col in self.tab:
            col[-1] = col[-1][:3] + (True,)
        self.stock = deck

    # --- piles -----------------------------------------------------------------------------------
    def pile(self, pid):
        k, i = pid
        return {"t": lambda: self.tab[i], "f": lambda: self.found[i], "c": lambda: self.cells[i],
                "s": lambda: self.stock, "w": lambda: self.waste}[k]()

    def snapshot(self):
        return ([list(p) for p in self.tab], [list(p) for p in self.found], [list(p) for p in self.cells],
                list(self.stock), list(self.waste), list(self.done), self.moves)

    def restore(self, s):
        tab, found, cells, stock, waste, done, moves = s
        self.tab, self.found, self.cells = [list(p) for p in tab], [list(p) for p in found], [list(p) for p in cells]
        self.stock, self.waste, self.done, self.moves = list(stock), list(waste), list(done), moves

    def push_undo(self):
        self.undo_stack.append(self.snapshot())
        if len(self.undo_stack) > 2000:
            del self.undo_stack[0]

    def undo(self):
        if self.undo_stack and not self.won:
            self.restore(self.undo_stack.pop())
            self.anims = []
            self.sfx("flick")
            return True
        return False

    def empty_cols(self, but=None):
        return sum(1 for i, p in enumerate(self.tab) if not p and i != but)

    def free_cells(self):
        return sum(1 for c in self.cells if not c)

    def supermove(self, to_empty=False):
        return (self.free_cells() + 1) * 2 ** max(0, self.empty_cols() - (1 if to_empty else 0))

    def is_run(self, cards):
        """Cards that may be picked up together."""
        if not cards or not all(c[3] for c in cards):
            return False
        for a, b in zip(cards, cards[1:]):
            if a[0] != b[0] + 1:
                return False
            if self.variant == "Spider":
                if a[1] != b[1]:
                    return False
            elif red(a) == red(b):
                return False
        return True

    def can_pick(self, pid, idx):
        p = self.pile(pid)
        if not 0 <= idx < len(p):
            return False
        k = pid[0]
        if k == "s":
            return False
        if k in ("w", "f", "c"):
            return idx == len(p) - 1 and (k != "f" or self.variant != "Spider")
        return self.is_run(p[idx:])

    def can_drop(self, cards, pid, src=None):
        k, i = pid
        c = cards[0]
        if src == pid:
            return False
        if k == "t":
            dst = self.tab[i]
            if self.variant == "FreeCell":
                limit = self.supermove(to_empty=not dst)
                if len(cards) > limit:
                    return False
            if not dst:
                return self.variant != "Klondike" or c[0] == 13
            top = dst[-1]
            if not top[3] or top[0] != c[0] + 1:
                return False
            return self.variant == "Spider" or red(top) != red(c)
        if k == "f":
            if self.variant == "Spider" or len(cards) != 1:
                return False
            dst = self.found[i]
            if not dst:
                return c[0] == 1
            return dst[-1][1] == c[1] and dst[-1][0] == c[0] - 1
        if k == "c":
            return self.variant == "FreeCell" and len(cards) == 1 and not self.cells[i]
        return False

    def legal(self, src, idx, dst):
        return self.can_pick(src, idx) and self.can_drop(self.pile(src)[idx:], dst, src)

    def move(self, src, idx, dst, record=True):
        """Move the cards from index idx of pile src onto pile dst. Returns True when done."""
        if self.won or not self.legal(src, idx, dst):
            return False
        if record:
            self.push_undo()
        p = self.pile(src)
        cards = p[idx:]
        del p[idx:]
        self.pile(dst).extend(cards)
        self.moves += 1
        self.started = True
        self.after_move(src, dst)
        self.sfx("found" if dst[0] == "f" else "place", 0.8)
        return True

    def after_move(self, src=None, dst=None):
        for col in self.tab:                          # the card under a move turns face up
            if col and not col[-1][3]:
                col[-1] = col[-1][:3] + (True,)
                self.sfx("flip", 0.6)
        if self.variant == "Spider":
            for col in self.tab:
                if len(col) >= 13:
                    run = col[-13:]
                    if run[0][0] == 13 and self.is_run(run):
                        del col[-13:]
                        self.done.append(run[0][1])
                        self.sfx("run")
                        for c2 in self.tab:
                            if c2 and not c2[-1][3]:
                                c2[-1] = c2[-1][:3] + (True,)
        if self.won and self.won_t is None:
            self.won_t = self.t
            self.sfx("win")
            if not self.demo:
                rec = load_scores().get(GAME, {})
                submit(GAME, self.key + " wins", rec.get(self.key + " wins", 0) + 1)
                self.record = submit(GAME, self.key + " time", round(self.clock, 1), lower_is_better=True)

    def draw(self):
        """Klondike: turn cards from the stock (or turn the waste over). Spider: deal a row."""
        if self.won:
            return False
        if self.variant == "Klondike":
            if not self.stock and not self.waste:
                return False
            self.push_undo()
            if not self.stock:
                self.stock = [c[:3] + (False,) for c in reversed(self.waste)]
                self.waste = []
            else:
                for _ in range(min(self.opt, len(self.stock))):
                    self.waste.append(self.stock.pop()[:3] + (True,))
            self.moves += 1
            self.started = True
            self.sfx("draw")
            return True
        if self.variant == "Spider":
            if not self.stock:
                return False
            if any(not col for col in self.tab):
                self.say("Fill every column before dealing.")
                self.sfx("nope")
                return False
            self.push_undo()
            for col in self.tab:
                col.append(self.stock.pop()[:3] + (True,))
            self.moves += 1
            self.started = True
            self.after_move()
            self.sfx("shuffle")
            return True
        return False

    @property
    def won(self):
        if self.variant == "Spider":
            return len(self.done) == 8
        return sum(len(f) for f in self.found) == 52

    def foundation_for(self, c):
        for i, f in enumerate(self.found):
            if self.can_drop([c], ("f", i)):
                return ("f", i)
        return None

    def best_target(self, src, idx, foundation_only=False):
        """Where a click sends the cards: the foundation first, then a built column, a free cell, an empty column."""
        if not self.can_pick(src, idx):
            return None
        cards = self.pile(src)[idx:]
        if len(cards) == 1 and src[0] != "f":
            f = self.foundation_for(cards[0])
            if f:
                return f
        if foundation_only:
            return None
        n = len(self.tab)
        order = [(src[1] + k) % n for k in range(1, n + 1)] if src[0] == "t" else range(n)
        empties = []
        for i in order:
            if ("t", i) == src:
                continue
            if self.can_drop(cards, ("t", i), src):
                if self.tab[i]:
                    if self.variant != "Spider" or self.tab[i][-1][1] == cards[0][1]:
                        return ("t", i)
                    empties.insert(0, ("t", i))        # any-suit builds before empty columns
                else:
                    empties.append(("t", i))
        if self.variant == "FreeCell" and len(cards) == 1 and src[0] != "c":
            for i in range(4):
                if not self.cells[i]:
                    if not (empties and empties[0][0] == "t" and self.tab[empties[0][1]]):
                        return ("c", i)
        return empties[0] if empties else None

    def all_moves(self):
        """Every legal move (src, idx, dst), foundations not taken back."""
        out = []
        srcs = [("t", i) for i in range(len(self.tab))] + [("c", i) for i in range(4)] + [("w", 0)]
        for src in srcs:
            p = self.pile(src)
            if not p:
                continue
            idxs = range(len(p)) if src[0] == "t" else [len(p) - 1]
            for idx in idxs:
                if not self.can_pick(src, idx):
                    continue
                cards = p[idx:]
                dsts = [("t", i) for i in range(len(self.tab))]
                if len(cards) == 1:
                    dsts += [("f", i) for i in range(4)] + [("c", i) for i in range(4)]
                for dst in dsts:
                    if self.can_drop(cards, dst, src):
                        out.append((src, idx, dst))
        return out

    def can_autocomplete(self):
        if self.variant == "Spider":
            return False
        return not self.stock and not self.waste and all(c[3] for p in self.tab for c in p) or \
            (self.variant == "Klondike" and all(c[3] for p in self.tab for c in p) and not self.stock and len(self.waste) <= 1)

    def auto_step(self):
        """One card to a foundation (auto-complete). Returns True if a card went."""
        best = None
        for src in [("t", i) for i in range(len(self.tab))] + [("c", i) for i in range(4)] + [("w", 0)]:
            p = self.pile(src)
            if p and p[-1][3]:
                f = self.foundation_for(p[-1])
                if f and (best is None or p[-1][0] < best[0]):
                    best = (p[-1][0], src, len(p) - 1, f)
        if best:
            return self.move(best[1], best[2], best[3])
        if self.variant == "Klondike" and (self.stock or self.waste):
            return self.draw()
        return False

    def find_hint(self):
        bot = SimpleBot()
        mv = bot.choose(self, hint=True)
        if mv and mv != "draw":
            return mv
        return mv

    def update(self, dt):
        if self.paused:
            return
        self.t += dt
        self.msg_t -= dt
        if self.started and not self.won:
            self.clock += dt
        self.anims = [a for a in self.anims if self.t - a[4] < a[5]]
        if self.hint and self.t > self.hint[1]:
            self.hint = None
        if self.won:
            self.update_bounce(dt)

    def update_bounce(self, dt):
        if not hasattr(self, "last_layout"):
            return
        L = self.last_layout
        if self.t - self.won_t < 8 and len(self.bounce) < 52 and int((self.t - self.won_t) / 0.09) >= len(self.bounce):
            k = len(self.bounce)
            if self.variant == "Spider":
                suit = self.done[k % len(self.done)] if self.done else 0
                c = (13 - (k // 8) % 13, suit, k, True)
                x, y = L.top_slot(k % 8)
            else:
                f = k % 4
                c = (13 - (k // 4) % 13, self.found[f][0][1] if self.found[f] else f, k, True)
                x, y = L.top_slot(L.found_cols[f])
            self.bounce.append([float(x), float(y), random.choice((-1, 1)) * random.uniform(14, 40),
                                random.uniform(-30, 0), c])
        floor = L.H - L.chp
        for b in self.bounce:
            b[3] += 160 * dt
            b[0] += b[2] * dt
            b[1] += b[3] * dt
            if b[1] > floor:
                b[1] = floor
                b[3] = -abs(b[3]) * 0.75
        self.bounce = [b for b in self.bounce if -L.cw - 2 < b[0] < L.W + 2]


# =============================================================================================
# The bots: greedy with care (Klondike, Spider), a best-first search for FreeCell
# =============================================================================================
def state_key(g):
    return (tuple(tuple(c[:2] + (c[3],) for c in p) for p in g.tab), tuple(len(f) for f in g.found),
            tuple(c[0][:2] if c else None for c in g.cells), len(g.stock), len(g.waste), len(g.done))


class SimpleBot:
    def __init__(self):
        self.seen = set()
        self.flat = 0
        self.passes = 0
        self.progress = True

    def score(self, g, src, idx, dst):
        p = g.pile(src)
        cards = p[idx:]
        c = cards[0]
        below = p[idx - 1] if idx > 0 else None
        reveals = below is not None and not below[3]
        v = g.variant
        if dst[0] == "f":
            return 100 + (20 if reveals else 0) - c[0]
        if dst[0] == "c":
            if v == "FreeCell":
                return 8 if (below is not None and g.foundation_for(below)) else 2
            return -1
        dtab = g.tab[dst[1]]
        if v == "Klondike":
            if src[0] == "w":
                return 50 if dtab else (45 if c[0] == 13 else -1)
            if src[0] != "t":
                return -1
            if reveals:
                return 60 + sum(1 for q in p if not q[3])
            if idx == 0:
                if not dtab:
                    return -1
                king_waiting = (g.waste and g.waste[-1][0] == 13) or any(
                    q[0] == 13 and i > 0 and not col[i - 1][3] for col in g.tab for i, q in enumerate(col) if q[3])
                return 25 if king_waiting else -1
            if below is not None and below[3] and g.foundation_for(below):
                return 40
            return -1
        if v == "Spider":
            if src[0] != "t":
                return -1
            same = bool(dtab) and dtab[-1][1] == c[1]
            if idx > 0 and below[3] and below[0] == c[0] + 1 and below[1] == c[1]:
                return -1                              # do not break a run of one suit
            if same:
                return 60 + len(cards) + (30 if reveals else 0)
            if not dtab:
                return 35 if reveals else (3 if idx > 0 else -1)
            if reveals:
                return 40
            if idx > 0 and below[3] and below[1] != c[1]:
                return 12                              # off a mixed-suit card: may lead to a run
            return -1
        # FreeCell (when the search gave up): plain greedy
        if dtab:
            return 30 + len(cards) + (10 if idx == 0 else 0)
        return 5 if idx > 0 else -1

    def spider_eval(self, g):
        v = 50 * len(g.done) + 6 * sum(1 for p in g.tab if not p)
        for p in g.tab:
            for k, c in enumerate(p):
                if not c[3]:
                    v -= 8
                elif k and p[k - 1][3] and p[k - 1][0] == c[0] + 1:
                    v += 3 if p[k - 1][1] == c[1] else 1
        return v

    def trial(self, g, mv, fn):
        snap = g.snapshot()
        quiet, g.demo = g.demo, True
        won_t = g.won_t
        g.move(*mv, record=False)
        try:
            return fn()
        finally:
            g.restore(snap)
            g.demo, g.won_t = quiet, won_t

    def spider_fill(self, g, moves):
        fill = [m for m in moves if not g.tab[m[2][1]] and m[1] > 0]
        fill = fill or [m for m in moves if not g.tab[m[2][1]]]
        return max(fill, key=lambda m: len(g.pile(m[0])) - m[1]) if fill else None

    def spider_choose(self, g, hint=False):
        moves = [m for m in g.all_moves() if m[2][0] == "t"]
        hold = g.stock and not hint and getattr(self, "fills", 0) >= 12   # tried enough: keep columns filled
        base = self.spider_eval(g)
        best, bv = None, 0
        for mv in moves:
            if hold and mv[1] == 0:
                continue                               # columns were just filled for a deal: keep them filled
            def after():
                gain = self.spider_eval(g) - base
                k = state_key(g)
                nxt = 0
                if gain >= 0:
                    for m2 in g.all_moves():
                        if m2[2][0] == "t":
                            nxt = max(nxt, self.trial(g, m2, lambda: self.spider_eval(g)) - base - gain)
                return gain, nxt, k
            gain, nxt, k = self.trial(g, mv, after)
            if k in self.seen and not hint:
                continue
            val = gain + max(0, nxt) * 0.5
            if gain < 0 or val <= 0 or (gain == 0 and self.flat >= 2):
                continue                               # at most two level moves in a row: no wandering
            if val > bv:
                best, bv, bgain = mv, val, gain
        if best:
            if not hint:
                self.flat = self.flat + 1 if bgain == 0 else 0
            return best
        if g.stock:
            fills = getattr(self, "fills", 0)
            if not all(g.tab):
                f = self.spider_fill(g, moves)
                if f and fills < 12:
                    if not hint:
                        self.fills = fills + 1
                    return f
                if f:                                 # enough tries: fill every column and deal
                    return f
            if not hint:
                self.fills = 0
            return "draw"
        return None

    def choose(self, g, hint=False):
        if g.variant == "Spider":
            return self.spider_choose(g, hint)
        best, bv = None, 0
        for mv in g.all_moves():
            v = self.score(g, *mv)
            if v <= 0 or v < bv:
                continue
            if not hint:
                snap = g.snapshot()
                quiet, g.demo = g.demo, True
                won_t = g.won_t
                g.move(*mv, record=False)
                k = state_key(g)
                g.restore(snap)
                g.demo, g.won_t = quiet, won_t
                if k in self.seen:
                    continue
            if v > bv:
                best, bv = mv, v
        if best:
            return best
        if g.variant == "Klondike" and (g.stock or g.waste):
            return "draw"
        if g.variant == "Spider" and g.stock:
            if any(not col for col in g.tab):
                for mv in g.all_moves():               # fill the empty columns first
                    if not g.tab[mv[2][1]] if mv[2][0] == "t" else False:
                        return mv
            return "draw"
        return None

    def step(self, g):
        """One move. Returns False when the bot has given up."""
        if g.won:
            return False
        self.seen.add(state_key(g))
        mv = self.choose(g)
        if mv is None:
            return False
        if mv == "draw":
            if g.variant == "Klondike":
                if not g.stock:
                    self.passes += 1
                    if self.passes > 3 and not self.progress:
                        return False
                    if not self.progress:
                        pass
                    self.progress = False
            ok = g.draw()
            if not ok:
                return False
            self.seen.add(state_key(g))
            return True
        self.progress = True
        g.move(*mv)
        return True


# --- FreeCell search -----------------------------------------------------------------------------
def fc_state(g):
    tab = tuple(tuple(c[:2] for c in p) for p in g.tab)
    cells = tuple(sorted((c[0][:2] for c in g.cells if c), reverse=True))
    found = [0, 0, 0, 0]
    for f in g.found:
        if f:
            found[f[-1][1]] = f[-1][0]
    return tab, cells, tuple(found)


def fc_safe(card, found):
    r, s = card
    if found[s] != r - 1:
        return False
    if r <= 2:
        return True
    opp = (1, 2) if s in (0, 3) else (0, 3)
    return all(found[o] >= r - 1 for o in opp)


def fc_moves(state):
    tab, cells, found = state
    out = []
    nfree = 4 - len(cells)
    nempty = sum(1 for p in tab if not p)
    for i, card in enumerate(cells):                  # cells -> foundation / columns
        r, s = card
        if found[s] == r - 1:
            out.append((("c", card), ("f", s), 1))
        for j, p in enumerate(tab):
            if not p or (p[-1][0] == r + 1 and (p[-1][1] in RED) != (s in RED)):
                out.append((("c", card), ("t", j), 1))
    for i, p in enumerate(tab):
        if not p:
            continue
        top = p[-1]
        if found[top[1]] == top[0] - 1:
            out.append((("t", i), ("f", top[1]), 1))
        run = 1
        while run < len(p):
            a, b = p[-run - 1], p[-run]
            if a[0] == b[0] + 1 and (a[1] in RED) != (b[1] in RED):
                run += 1
            else:
                break
        for j, q in enumerate(tab):
            if i == j:
                continue
            if q:
                need = q[-1][0] - 1
                k = need - p[-1][0] + 1
                if 1 <= k <= run and (p[-k][1] in RED) != (q[-1][1] in RED) and p[-k][0] == need:
                    if k <= (nfree + 1) * 2 ** nempty:
                        out.append((("t", i), ("t", j), k))
            else:
                if len(p) == 1:
                    continue
                lim = min(run, (nfree + 1) * 2 ** max(0, nempty - 1))
                for k in {lim, 1}:
                    if k < len(p) or k == lim:
                        out.append((("t", i), ("t", j), k))
        if nfree:
            out.append((("t", i), ("c", None), 1))
    return out


def fc_apply(state, mv):
    tab, cells, found = state
    (sk, si), (dk, di), n = mv
    tab = list(tab)
    cells = list(cells)
    found = list(found)
    if sk == "c":
        cards = (si,)
        cells.remove(si)
    else:
        cards = tab[si][-n:]
        tab[si] = tab[si][:-n]
    if dk == "f":
        found[di] = cards[0][0]
    elif dk == "c":
        cells.append(cards[0])
    else:
        tab[di] = tab[di] + tuple(cards)
    return tuple(tab), tuple(sorted(cells, reverse=True)), tuple(found)


def fc_auto(state):
    """Safe cards to the foundations; returns the new state and the moves taken."""
    taken = []
    changed = True
    while changed:
        changed = False
        tab, cells, found = state
        for card in cells:
            if fc_safe(card, found):
                mv = (("c", card), ("f", card[1]), 1)
                state = fc_apply(state, mv)
                taken.append(mv)
                changed = True
                break
        if changed:
            continue
        for i, p in enumerate(tab):
            if p and fc_safe(p[-1], found):
                mv = (("t", i), ("f", p[-1][1]), 1)
                state = fc_apply(state, mv)
                taken.append(mv)
                changed = True
                break
    return state, taken


def fc_h(state):
    tab, cells, found = state
    h = (52 - sum(found)) * 3 + len(cells) * 2
    for p in tab:
        for k, c in enumerate(p):                     # cards sitting on a lower card of the same suit... or any lower
            if any(d[0] < c[0] for d in p[:k]):
                h += 2
        for a, b in zip(p, p[1:]):
            if not (a[0] == b[0] + 1 and (a[1] in RED) != (b[1] in RED)):
                h += 1
    h -= 4 * sum(1 for p in tab if not p)
    return h


def fc_canon(state):
    tab, cells, found = state
    return tuple(sorted(tab)), cells, found


def fc_search(g, budget=60000):
    """Best-first search; a generator yielding None while it works, then the plan (or [] if none was found)."""
    start, auto = fc_auto(fc_state(g))
    heap = [(fc_h(start), 0, start)]
    parent = {fc_canon(start): (None, auto)}
    n = 0
    tie = 0
    while heap:
        _, depth, st = heapq.heappop(heap)
        if sum(st[2]) == 52:
            plan = []
            k = fc_canon(st)
            path = []
            while k is not None:
                prev, mvs = parent[k]
                path.append(mvs)
                k = prev
            for mvs in reversed(path):
                plan += mvs
            yield plan
            return
        n += 1
        if n > budget:
            break
        if n % 250 == 0:
            yield None
        ck = fc_canon(st)
        for mv in fc_moves(st):
            ns = fc_apply(st, mv)
            ns, auto = fc_auto(ns)
            nk = fc_canon(ns)
            if nk in parent:
                continue
            parent[nk] = (ck, [mv] + auto)
            tie += 1
            heapq.heappush(heap, (fc_h(ns) + depth * 0.5, depth + 1, ns))
    yield []


def fc_to_game(g, mv):
    """A search move as (src, idx, dst) for the game, or None if it does not fit (the plan is stale)."""
    (sk, si), (dk, di), n = mv
    if sk == "c":
        src = next((("c", i) for i in range(4) if g.cells[i] and g.cells[i][0][:2] == si), None)
        if src is None:
            return None
        idx = 0
    else:
        src = ("t", si)
        idx = len(g.tab[si]) - n
    if dk == "f":
        card = g.pile(src)[idx] if g.pile(src) else None
        if card is None:
            return None
        dst = g.foundation_for(card)
    elif dk == "c":
        dst = next((("c", i) for i in range(4) if not g.cells[i]), None)
    else:
        dst = ("t", di)
    if dst is None or not g.legal(src, idx, dst):
        return None
    return src, idx, dst


class Bot:
    """Plays a whole game one move per call to step(); FreeCell searches first (a little every call)."""

    def __init__(self, g):
        self.g = g
        self.simple = SimpleBot()
        self.plan = None
        self.search = fc_search(g) if g.variant == "FreeCell" else None
        self.gave_up = False

    def step(self):
        g = self.g
        if g.won or self.gave_up:
            return False
        if self.search is not None:
            r = next(self.search, [])
            if r is None:
                return True                           # still thinking
            self.search = None
            self.plan = list(r) if r else None
        if self.plan:
            mv = fc_to_game(g, self.plan.pop(0))
            if mv and g.move(*mv):
                return True
            self.plan = None
        if not self.simple.step(g):
            self.gave_up = True
            return False
        return True


# =============================================================================================
# Layout and drawing
# =============================================================================================
class Layout:
    """Where everything goes for one window size. Pixels: x per column, y two per text row."""

    def __init__(self, g, cols, rows):
        self.W, self.H = cols, rows * 2
        n = len(g.tab)
        gap = 2 if cols >= n * 12 else 1
        cw = (cols - 2 - gap * (n - 1)) // n
        cw = clamp(cw, 4, 16)
        ch = clamp(int(round(cw * 0.66)), 3, max(3, (rows - 2) // 4))
        self.cw, self.ch, self.chp, self.gap = cw, ch, ch * 2, gap
        total = n * cw + (n - 1) * gap
        self.x0 = (cols - total) // 2
        self.xs = [self.x0 + i * (cw + gap) for i in range(n)]
        self.top = 2
        self.tab_y = self.top + self.chp + 2
        self.n = n
        if g.variant == "Klondike":
            self.found_cols = [3, 4, 5, 6]
        elif g.variant == "FreeCell":
            self.found_cols = [4, 5, 6, 7]
        else:
            self.found_cols = list(range(8))

    def top_slot(self, col):
        return self.xs[col], self.top

    def offsets(self, pile):
        """y of every card in a column, squeezed to fit the window."""
        nd = sum(1 for c in pile if not c[3])
        nu = len(pile) - nd
        avail = self.H - self.tab_y - self.chp
        big = 4 if self.ch >= 4 else 2
        for fu, fd in ((big, 2), (2, 2), (2, 1)):
            if nd * fd + max(0, nu - 1) * fu + (2 if nd and nd * fd % 2 else 0) <= avail:
                break
        else:
            fu, fd = None, 1
        ys = []
        y = self.tab_y
        for k, c in enumerate(pile):
            ys.append(y)
            if k + 1 < len(pile):
                if not c[3]:
                    y += fd
                    if pile[k + 1][3] and y % 2:
                        y += 1
                else:
                    y += fu if fu else 0
        if fu is None:                                 # still too long: squeeze the face-up part evenly
            first = next((k for k, c in enumerate(pile) if c[3]), len(pile))
            y0 = ys[first] if first < len(pile) else self.tab_y
            room = max(0, avail - (y0 - self.tab_y))
            step = room / max(1, nu - 1)
            for k in range(first, len(pile)):
                ys[k] = int(y0 + (k - first) * step) // 2 * 2 if step >= 2 else int(y0 + (k - first) * step)
        if ys and ys[-1] > self.tab_y + avail:          # whatever the pile: never past the bottom
            k = avail / max(1, ys[-1] - self.tab_y)
            ys = [self.tab_y + int((y - self.tab_y) * k) for y in ys]
        return ys

    def waste_xs(self, n):
        step = 3 if self.cw >= 6 else 2
        return [self.xs[1] + k * step for k in range(n)]


def put_card_text(cv, x, y, s, fg, bg):
    if y % 2 == 0:
        cv.put(int(x), y // 2, s, fg, bg)


def draw_slot(cv, x, y, L, label=""):
    c = shade(FELT[0], 0.75)
    cv.frame(x, y, L.cw, L.chp, c)
    if label and L.cw >= 3:
        put_card_text(cv, x + (L.cw - len(label)) // 2, y + (L.chp // 2) // 2 * 2, label, shade(FELT[0], 1.4), None)


def draw_back(cv, x, y, L):
    cw, chp = L.cw, L.chp
    for yy in range(chp):
        for xx in range(cw):
            if (yy in (0, chp - 1)) and (xx in (0, cw - 1)):
                continue
            edge = xx in (0, cw - 1) or yy in (0, chp - 1)
            if edge:
                c = (232, 232, 240)
            elif (xx + yy) % 4 == 0 or (xx - yy) % 4 == 0:
                c = BACK_L
            else:
                c = BACK
            cv.set(x + xx, y + yy, c)


def draw_face(cv, x, y, L, card, full, hl=None):
    cw, chp = L.cw, L.chp
    ink = INK_RED if red(card) else INK_BLACK
    edge = hl or EDGE
    for yy in range(chp):
        for xx in range(cw):
            if (yy in (0, chp - 1)) and (xx in (0, cw - 1)):
                continue
            cv.set(x + xx, y + yy, edge if xx in (0, cw - 1) or yy in (0, chp - 1) else CARD)
    if hl:
        cv.frame(x, y, cw, chp, hl)
    label = card_str(card)
    put_card_text(cv, x + 1, y, label[:cw - 1], ink, CARD)
    if not full:
        return
    r = card[0]
    rows = chp // 2
    if r > 10 and cw >= 6 and rows >= 4:              # court cards: a tinted panel with the letter
        px0, py0, pw, ph = x + 2, y + 3, cw - 4, chp - 6
        tint = mix(ink, CARD, 0.78)
        cv.rect(px0, py0, pw, ph, tint)
        cv.frame(px0, py0, pw, ph, mix(ink, CARD, 0.4))
        mid = (y + chp // 2) // 2
        cv.put(x + cw // 2 - 1, mid, RANKS[r] + SUITS[card[1]], ink, tint)
    elif cw >= 7 and rows >= 4:                        # pip cards: the suit in pixels
        art = SUIT_ART[card[1]]
        k = max(1, min((cw - 2) // 6, (chp - 6) // 6))
        ax = x + (cw - 5 * k) // 2
        ay = y + (chp - 5 * k) // 2 + 1
        for j, row in enumerate(art):
            for i, b in enumerate(row):
                if b == "#":
                    cv.rect(ax + i * k, ay + j * k, k, k, ink)
    elif rows >= 3:
        put_card_text(cv, x + cw // 2, (y + chp // 2) // 2 * 2, SUITS[card[1]], ink, CARD)
    if rows >= 4 and cw >= 5:
        put_card_text(cv, x + cw - 1 - len(label), y + chp - 2, label, ink, CARD)


def draw_card(cv, x, y, L, card, full=True, hl=None):
    if card[3]:
        draw_face(cv, x, y, L, card, full, hl)
    else:
        draw_back(cv, x, y, L)
        if hl:
            cv.frame(x, y, L.cw, L.chp, hl)


def card_rects(g, L):
    """Every visible card: (pid, idx, x, y, visible height, card), back to front."""
    out = []
    if g.variant == "Klondike":
        if g.stock:
            out.append((("s", 0), len(g.stock) - 1, L.xs[0], L.top, L.chp, g.stock[-1]))
        n = min(len(g.waste), g.opt if g.opt > 1 else 1)
        shown = g.waste[-max(n, 1):] if g.waste else []
        xs = L.waste_xs(len(shown))
        for k, c in enumerate(shown):
            out.append((("w", 0), len(g.waste) - len(shown) + k, xs[k], L.top, L.chp, c))
        for f, col in zip(g.found, L.found_cols):
            if f:
                out.append((("f", L.found_cols.index(col)), len(f) - 1, L.xs[col], L.top, L.chp, f[-1]))
    elif g.variant == "FreeCell":
        for i in range(4):
            if g.cells[i]:
                out.append((("c", i), 0, L.xs[i], L.top, L.chp, g.cells[i][0]))
        for k, (f, col) in enumerate(zip(g.found, L.found_cols)):
            if f:
                out.append((("f", k), len(f) - 1, L.xs[col], L.top, L.chp, f[-1]))
    else:
        if g.stock:
            out.append((("s", 0), len(g.stock) - 1, L.xs[L.n - 1], L.top, L.chp, g.stock[-1]))
    for i, col in enumerate(g.tab):
        ys = L.offsets(col)
        for k, c in enumerate(col):
            vis = (ys[k + 1] - ys[k]) if k + 1 < len(col) else L.chp
            out.append((("t", i), k, L.xs[i], ys[k], vis, c))
    return out


def render_table(g, cols, rows, play):
    cv = Canvas(cols, rows)
    H = play * 2
    for y in range(H):
        base = mix(FELT[0], FELT[1], abs(y / max(1, H) - 0.35) * 1.3)
        cv.px[y] = [shade(base, 1.04) if (x * 3 + y * 5) % 17 == 0 else base for x in range(cols)]
    L = Layout(g, cols, play)
    g.last_layout = L
    # empty places
    if g.variant == "Klondike":
        draw_slot(cv, L.xs[0], L.top, L, "R" if g.waste and not g.stock else "")
        for k, col in enumerate(L.found_cols):
            draw_slot(cv, L.xs[col], L.top, L, "" if g.found[k] else "A")
    elif g.variant == "FreeCell":
        for i in range(4):
            draw_slot(cv, L.xs[i], L.top, L, "")
        for k, col in enumerate(L.found_cols):
            draw_slot(cv, L.xs[col], L.top, L, "" if g.found[k] else "A")
    else:
        for k in range(8):
            draw_slot(cv, L.xs[k], L.top, L, "")
        for k, s in enumerate(g.done):
            draw_face(cv, L.xs[k], L.top, L, (13, s, -1, True), True)
        if g.stock:                                    # the deals left, as a small stack of backs
            n = len(g.stock) // 10
            for k in range(n):
                draw_back(cv, L.xs[L.n - 1] - 2 * (n - 1 - k), L.top, L)
    for i in range(len(g.tab)):
        if not g.tab[i]:
            draw_slot(cv, L.xs[i], L.tab_y, L, "K" if g.variant == "Klondike" else "")
    drag = getattr(g, "drag", None)
    hidden = set()
    if drag and drag.get("moved"):
        hidden = {(drag["src"], k) for k in range(drag["idx"], len(g.pile(drag["src"])))}
    hint_src = hint_dst = None
    if g.hint:
        hint_src, hint_dst = g.hint[0]
    sel = getattr(g, "cursor_hl", None)
    for pid, idx, x, y, vis, c in card_rects(g, L):
        if (pid, idx) in hidden:
            continue
        if g.variant == "Spider" and pid[0] == "s":
            continue
        hl = None
        if hint_src and pid == hint_src[0] and idx >= hint_src[1]:
            hl = (90, 230, 255) if int(g.t * 4) % 2 else (40, 160, 220)
        if sel and pid == sel[0] and idx >= sel[1]:
            hl = (255, 210, 70)
        draw_card(cv, x, y, L, c, full=vis >= L.chp, hl=hl)
    if hint_dst:
        x, y = pile_anchor(g, L, hint_dst)
        cv.frame(x - 1, y - 1, L.cw + 2, L.chp + 2, (90, 230, 255))
    if drag and drag.get("moved"):
        cards = g.pile(drag["src"])[drag["idx"]:]
        x0, y0 = drag["x"] - drag["gx"], drag["y"] - drag["gy"]
        step = 4 if L.ch >= 4 else 2
        for k, c in enumerate(cards):
            draw_card(cv, int(x0) + 1, (int(y0) + k * step) // 2 * 2 + 1, L, c, full=k == len(cards) - 1)
    for b in g.bounce:
        draw_face(cv, int(b[0]), int(b[1]) // 2 * 2, L, b[4], True)
    return cv, L


def pile_anchor(g, L, pid):
    """The top-left of where a card dropped on pid would lie."""
    k, i = pid
    if k == "t":
        col = g.tab[i]
        if not col:
            return L.xs[i], L.tab_y
        ys = L.offsets(col + [(1, 0, -1, True)])
        return L.xs[i], ys[-1]
    if k == "f":
        return L.xs[L.found_cols[i]], L.top
    if k == "c":
        return L.xs[i], L.top
    if k == "w":
        return L.xs[1], L.top
    return L.xs[0 if g.variant == "Klondike" else L.n - 1], L.top


def fmt(t):
    return "%d:%02d" % (int(t) // 60, int(t) % 60)


def variant_label(g):
    if g.variant == "Klondike":
        return "KLONDIKE draw %d" % g.opt
    if g.variant == "Spider":
        return "SPIDER %d suit%s" % (g.opt, "s" if g.opt > 1 else "")
    return "FREECELL #%d" % g.opt


def render(g, cols, rows, hud=True):
    play = rows - 1 if hud else rows
    if cols < 40 or play < 12:
        raise ValueError("too small for the table")   # the launcher then draws it bigger and shrinks it
    cv, L = render_table(g, cols, rows, play)
    if hud:
        r = rows - 1
        cv.put(0, r, " " * cols, HUD_FG, HUD_BG)
        head = " %s " % variant_label(g)
        cv.put(0, r, head, (14, 20, 16), (230, 214, 140))
        s = "  %s   moves %d" % (fmt(g.clock), g.moves)
        cv.put(len(head), r, s, HUD_FG, HUD_BG)
        hint = "U undo   H hint   N new   ? help"
        if g.can_autocomplete() and not g.won:
            hint = "A auto-complete   " + hint
        if len(head) + len(s) + len(hint) + 3 < cols:
            cv.put(cols - len(hint) - 1, r, hint, (150, 176, 160), HUD_BG)
        if g.msg_t > 0:
            cv.center(rows - 2, " %s " % g.msg, (20, 20, 26), (236, 226, 170))
        if g.won and g.t - g.won_t > 1.0:
            draw_win(cv, g)
        if g.paused:
            overlay(cv, HELP if g.help else PAUSE_LINES + ["", SND.label()])
    return cv


def draw_win(cv, g, auto=False):
    rec = load_scores().get(GAME, {})
    lines = ["SOLVED!", "", "%s" % variant_label(g).title(), "time   %s" % fmt(g.clock), "moves  %d" % g.moves]
    b = rec.get(g.key + " time")
    if b is not None and not g.demo:
        lines.append("best   %s" % fmt(b))
    w = rec.get(g.key + " wins")
    if w and not g.demo:
        lines.append("wins   %d" % w)
    if g.record:
        lines += ["", "** NEW RECORD **"]
    lines += ["", "auto mode: next deal" if g.demo else "Enter: new deal   Esc: menu"]
    width = max(len(l) for l in lines) + 4
    x, y = max(0, (cv.cols - width) // 2), max(0, cv.rows // 2 - len(lines) // 2 - 1)
    cv.frame(x - 1, y * 2 - 1, width + 2, (len(lines) + 2) * 2 + 2, (240, 210, 110))
    cv.box(x, y, [l.center(width - 4) for l in lines], (240, 240, 246), (20, 40, 30))


# =============================================================================================
# Input: mouse drag and click, keyboard cursor
# =============================================================================================
def hit(g, L, px, py):
    """The card under a pixel (topmost), or the pile there: (pid, idx) with idx = None for an empty place."""
    found = None
    for pid, idx, x, y, vis, c in card_rects(g, L):
        h = L.chp if vis >= L.chp else max(1, vis)
        if pid[0] == "w":
            wxs = L.waste_xs(1)
            h = L.chp
        if x <= px < x + L.cw and y <= py < y + h:
            found = (pid, idx)
    if found:
        return found
    if py < L.tab_y - 1:
        for col, x in enumerate(L.xs):
            if x <= px < x + L.cw:
                return top_pid(g, L, col), None
    else:
        for i, x in enumerate(L.xs):
            if x <= px < x + L.cw:
                return ("t", i), None
    return None


def top_pid(g, L, col):
    if g.variant == "Klondike":
        return {0: ("s", 0), 1: ("w", 0), 2: None}.get(col, ("f", col - 3))
    if g.variant == "FreeCell":
        return ("c", col) if col < 4 else ("f", col - 4)
    return ("s", 0) if col == L.n - 1 else None


def drop_target(g, L, x, y):
    """The pile a dragged card (its top-left at x, y) lands on."""
    cx = x + L.cw / 2
    col = min(range(L.n), key=lambda i: abs(L.xs[i] + L.cw / 2 - cx))
    if abs(L.xs[col] + L.cw / 2 - cx) > L.cw:
        return None
    if y + L.chp / 2 < L.tab_y:
        return top_pid(g, L, col)
    return ("t", col)


def click_card(g, pid, idx, foundation_only=False):
    if pid is None:
        return False
    if pid[0] == "s":
        return g.draw()
    if idx is None:
        return False
    p = g.pile(pid)
    if pid[0] == "t" and not p[idx][3]:
        return False
    if pid[0] == "t" and not g.can_pick(pid, idx):
        idx = next((k for k in range(idx, len(p)) if g.can_pick(pid, k)), None)
        if idx is None:
            return False
    dst = g.best_target(pid, idx, foundation_only)
    if dst and g.move(pid, idx, dst):
        return True
    g.sfx("nope")
    return False


def apply_mouse(term, g, cols, rows):
    take = getattr(term, "take_mouse", None)
    if not take:
        return
    L = getattr(g, "last_layout", None)
    events = take()
    if L is None:
        return
    for kind, col, row in events:
        px, py = col, row * 2 + 1
        drag = getattr(g, "drag", None)
        if kind == "left":
            h = hit(g, L, px, py)
            g.drag = None
            if h is None:
                continue
            pid, idx = h
            if pid is None:
                continue
            if pid[0] == "s":
                g.draw()
                continue
            if idx is None:
                continue
            if pid[0] in ("w", "f", "c"):
                idx = len(g.pile(pid)) - 1
            x, y = pile_card_xy(g, L, pid, idx)
            g.drag = dict(src=pid, idx=idx, gx=px - x, gy=py - y, x=px, y=py, sx=px, sy=py, moved=False)
        elif kind == "move" and drag:
            drag["x"], drag["y"] = px, py
            if not drag["moved"] and (abs(px - drag["sx"]) > 1 or abs(py - drag["sy"]) > 2):
                if g.can_pick(drag["src"], drag["idx"]):
                    drag["moved"] = True
                    g.sfx("flick", 0.6)
                else:
                    g.drag = None
        elif kind == "up" and drag:
            g.drag = None
            if drag["moved"]:
                dst = drop_target(g, L, drag["x"] - drag["gx"], drag["y"] - drag["gy"])
                if not (dst and g.move(drag["src"], drag["idx"], dst)):
                    g.sfx("nope")
            else:
                click_card(g, drag["src"], drag["idx"])
        elif kind == "right":
            h = hit(g, L, px, py)
            if h and h[0] and h[1] is not None:
                p = g.pile(h[0])
                click_card(g, h[0], len(p) - 1, foundation_only=True)


def pile_card_xy(g, L, pid, idx):
    for p, i, x, y, vis, c in card_rects(g, L):
        if p == pid and i == idx:
            return x, y
    return pile_anchor(g, L, pid)


class Cursor:
    """The keyboard hand: a column, the top row or the tableau, and a card in it."""

    def __init__(self):
        self.col, self.area, self.idx = 0, "t", None
        self.held = None

    def pid(self, g, L):
        if self.area == "top":
            return top_pid(g, L, self.col)
        return ("t", self.col)

    def key(self, g, k):
        L = getattr(g, "last_layout", None)
        if L is None:
            return
        n = L.n
        if k in ("left", "a"):
            self.col = (self.col - 1) % n
            self.idx = None
        elif k in ("right", "d"):
            self.col = (self.col + 1) % n
            self.idx = None
        elif k in ("up", "w", "down", "s"):
            col = g.tab[self.col]
            up = k in ("up", "w")
            if self.area == "top":
                if not up:
                    self.area, self.idx = "t", None
            else:
                first = next((i for i, c in enumerate(col) if c[3]), len(col))
                cur = len(col) - 1 if self.idx is None else self.idx
                if up:
                    if cur <= first:
                        self.area = "top"
                    else:
                        self.idx = cur - 1
                else:
                    self.idx = min(len(col) - 1, cur + 1) if col else None
        elif k in (" ", "enter"):
            pid = self.pid(g, L)
            if pid is None:
                return
            if self.held is None:
                if pid[0] == "s":
                    g.draw()
                    return
                p = g.pile(pid)
                if not p:
                    return
                idx = len(p) - 1 if (self.idx is None or pid[0] != "t") else self.idx
                if g.can_pick(pid, idx):
                    self.held = (pid, idx)
                    g.sfx("flick", 0.6)
                else:
                    g.sfx("nope")
            else:
                src, idx = self.held
                self.held = None
                if pid == src:
                    click_card(g, src, idx)
                elif not g.move(src, idx, pid):
                    g.sfx("nope")
                self.idx = None
        g.cursor_hl = self.held

    def draw(self, cv, g):
        L = getattr(g, "last_layout", None)
        if L is None:
            return
        pid = self.pid(g, L)
        if self.area == "top":
            x, y = L.xs[self.col], L.top
        else:
            col = g.tab[self.col]
            if col:
                ys = L.offsets(col)
                i = len(col) - 1 if self.idx is None or self.idx >= len(col) else self.idx
                x, y = L.xs[self.col], ys[i]
            else:
                x, y = L.xs[self.col], L.tab_y
        c = (255, 240, 120) if int(g.t * 3) % 2 else (255, 190, 60)
        cv.rect(x + L.cw // 2 - 1, max(0, y - 1), 3, 1, c)
        cv.rect(x, max(0, y - 1), 1, 1, c)
        cv.rect(x + L.cw - 1, max(0, y - 1), 1, 1, c)


# =============================================================================================
# Title, auto mode, play
# =============================================================================================
class TitleDemo:
    """A solver at the table: Klondike, FreeCell and Spider in turn."""

    def __init__(self):
        self.k = 0
        self.new()

    def new(self):
        v = ["Klondike", "FreeCell", "Spider"][self.k % 3]
        opt = {"Klondike": 1, "FreeCell": 1 + (self.k * 7) % 30000, "Spider": 1}[v]
        self.g = Game(v, opt, seed=500 + self.k, demo=True)
        self.bot = Bot(self.g)
        self.k += 1
        self.wait = 0.0
        self.end = None

    def scene(self, cols, rows, dt):
        dt = min(dt, 0.1)
        g = self.g
        g.update(dt)
        self.wait -= dt
        if self.wait <= 0 and self.end is None:
            self.wait = 0.16
            if not self.bot.step():
                self.end = g.t
        if self.end is not None and g.t - self.end > (5 if g.won else 1.5):
            self.new()
        return render(self.g, cols, rows, hud=False)


def render_menu(demo, cols, rows, sel, dt, help_=False, opts=None, last=0):
    cv = demo.scene(cols, rows, dt)
    dim = (6, 6, 14)                                   # the card labels dim with the table behind the menu
    cv.text = {k: (ch, mix(fg, dim, 0.55), None if bg is None else mix(bg, dim, 0.55))
               for k, (ch, fg, bg) in cv.text.items()}
    opts = opts or {"Klondike": 1, "Spider": 1, "FreeCell": 1}
    rec = load_scores().get(GAME, {})
    items = ["Klondike    draw < %d >" % opts["Klondike"],
             "Spider      suits < %d >" % opts["Spider"],
             "FreeCell    deal < #%d >" % opts["FreeCell"],
             "%-11s watch %s" % (AUTO_LABEL, VARIANTS[last])]
    keys = {"Klondike": "Klondike %d" % opts["Klondike"], "Spider": "Spider %d" % opts["Spider"],
            "FreeCell": "FreeCell"}[VARIANTS[min(sel, 2) if sel < 3 else last]]
    b, w = rec.get(keys + " time"), rec.get(keys + " wins")
    best = ("%s: %d won, best %s" % (keys, w or 0, fmt(b))) if b is not None else None
    title_screen(cv, "SOLACE", "patience on a green felt table", items, sel, best,
                 extra=["", "Left/Right: draw, suits or deal number   R: random deal"],
                 keys="Up/Down choose   Left/Right option   Enter start   M %s   ? help   Esc back" % SND.label().lower(),
                 help_lines=HELP, show_help=help_)
    return cv


def too_small(term):
    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (60x22).")


def game_key(g, cur, k):
    if g.won:
        return
    if k == "u":
        g.undo()
    elif k == "h":
        mv = g.find_hint()
        if mv == "draw":
            g.say("Draw from the stock." if g.variant == "Klondike" else "Deal a new row.")
        elif mv:
            g.hint = ((mv[0], mv[1]), mv[2]), g.t + 2.5
            g.hint = (((mv[0], mv[1]), mv[2]), g.t + 2.5)
        else:
            g.say("No moves left. U undoes, N deals again.")
    elif k in ("tab", "t"):
        g.draw()
    elif k == "a":
        if g.can_autocomplete():
            g.auto = True
        else:
            g.say("Auto-complete needs every card face up.")
    else:
        cur.key(g, k)


def run_auto(term, variant, opts):
    auto = AutoMode()
    k = 0
    while True:
        opt = opts[variant] if variant != "FreeCell" else opts["FreeCell"] + k
        g = Game(variant, opt, seed=random.randrange(1 << 30), demo=True)
        bot = Bot(g)
        last = time.time()
        acc = 0.0
        end = None
        while True:
            now = time.time()
            dt = min(0.1, now - last)
            last = now
            for key in term.keys(0):
                a = auto.key(key)
                if a == "stop":
                    return
                if a == "sound" and SND.toggle():
                    SND.play("sound_on")
            if getattr(term, "take_mouse", None):
                term.take_mouse()
            sim = auto.scale(dt)
            g.update(sim)
            acc += sim
            while acc >= 0.18 and end is None:
                acc -= 0.18
                g.demo = False
                quiet = SND.enabled
                try:
                    ok = bot.step()
                finally:
                    g.demo = True
                if not ok:
                    end = g.t
            if end is not None and g.t - end > (6 if g.won else 2):
                break
            cols, rows = term.size()
            if cols < 60 or rows < 22:
                too_small(term)
                time.sleep(0.2)
                continue
            cv = render(g, cols, rows)
            auto.banner(cv, extra=variant_label(g).title())
            term.write(cv.emit())
            time.sleep(max(0, 1 / 40 - (time.time() - now)))
        k += 1


def play(term, variant, opt):
    g = Game(variant, opt)
    cur = Cursor()
    g.sfx("shuffle")
    last = time.time()
    while True:
        now = time.time()
        cols, rows = term.size()
        dt = min(0.1, now - last)
        last = now
        if not g.paused:
            apply_mouse(term, g, cols, rows)
        elif getattr(term, "take_mouse", None):
            term.take_mouse()
        for k in term.keys(0):
            if g.won and g.t - g.won_t > 0.8:
                if k in ("enter", " ", "n"):
                    opt2 = opt + 1 if variant == "FreeCell" else opt
                    g, cur = Game(variant, opt2), Cursor()
                    opt = opt2
                    g.sfx("shuffle")
                    continue
                if k in ("esc", "q"):
                    return
            a = shared_key(k, g.paused, pause_keys=("esc", "p"))
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
                if k == "n":
                    g, cur = Game(variant, opt), Cursor()
                    g.sfx("shuffle")
                else:
                    game_key(g, cur, k)
        if getattr(g, "auto", False) and not g.paused:
            g.auto_t = getattr(g, "auto_t", 0) - dt
            if g.auto_t <= 0:
                g.auto_t = 0.07
                if not g.auto_step():
                    g.auto = False
        g.update(dt)
        if cols < 60 or rows < 22:
            too_small(term)
            time.sleep(0.2)
            continue
        cv = render(g, cols, rows)
        if not g.won and not getattr(g, "drag", None):
            cur.draw(cv, g)
        term.write(cv.emit())
        time.sleep(max(0, 1 / 40 - (time.time() - now)))


def main():
    with MouseTerminal() as term:
        demo = TitleDemo()
        sel, help_, last_v = 0, False, 0
        opts = {"Klondike": 1, "Spider": 1, "FreeCell": random.randint(1, 32000)}
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
            term.write(render_menu(demo, cols, rows, sel, min(0.1, now - last), help_, opts, last_v).emit())
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
                    sel = (sel - 1) % 4
                    SND.play("menu")
                elif k in ("down", "s"):
                    sel = (sel + 1) % 4
                    SND.play("menu")
                elif k in ("left", "a", "right", "d") and sel < 3:
                    d = 1 if k in ("right", "d") else -1
                    v = VARIANTS[sel]
                    if v == "Klondike":
                        opts[v] = 3 if opts[v] == 1 else 1
                    elif v == "Spider":
                        seq = [1, 2, 4]
                        opts[v] = seq[(seq.index(opts[v]) + d) % 3]
                    else:
                        opts[v] = (opts[v] - 1 + d) % 32000 + 1
                    SND.play("menu")
                elif k == "r" and sel == 2:
                    opts["FreeCell"] = random.randint(1, 32000)
                    SND.play("menu")
                elif k == "m":
                    if SND.toggle():
                        SND.play("sound_on")
                elif k in ("enter", " "):
                    SND.play("start")
                    go = True
            if sel < 3:
                last_v = sel
            if go:
                if sel == 3:
                    run_auto(term, VARIANTS[last_v], opts)
                else:
                    play(term, VARIANTS[sel], opts[VARIANTS[sel]])
                last = time.time()


# =============================================================================================
# Self-test:  python3 solace.py --selftest
# =============================================================================================
class FakeTerm:
    def __init__(self, script, mouse=(), size=(100, 32)):
        self.script = sorted(script)
        self.mscript = sorted(mouse)
        self.t0 = time.time()
        self.cols_rows = size
        self.frames = 0

    def keys(self, timeout=0.0):
        now = time.time() - self.t0
        out = [k for t, k in self.script if t <= now]
        self.script = [(t, k) for t, k in self.script if t > now]
        return out

    def take_mouse(self):
        now = time.time() - self.t0
        out = [m for t, m in self.mscript if t <= now]
        self.mscript = [(t, m) for t, m in self.mscript if t > now]
        return out

    def size(self):
        return self.cols_rows

    def write(self, s):
        self.frames += 1


def C(r, s, up=True, uid=None):
    return (r, s, uid if uid is not None else s * 13 + r + random.randrange(1000) * 100, up)


def screenshot(cols=100, rows=32):
    g = Game("Klondike", 1, seed=21, demo=True)
    bot = Bot(g)
    for _ in range(46):
        bot.step()
    g.clock = 134.0
    return render(g, cols, rows)


def selftest():
    import os
    import tempfile
    import arcadekit
    t0 = time.time()
    tmp = os.path.join(tempfile.mkdtemp(), "scores.json")
    arcadekit.SCORES_PATH = tmp
    SND.enabled = False
    # FreeCell deal #1 starts with the well-known first row
    first = [card_str(c) for c in ms_deal(1)[:8]]
    assert first == ["J♦", "2♦", "9♥", "J♣", "5♦", "7♥", "7♣", "5♥"], first
    # Klondike: the deal, alternating colours down, kings to empty columns, foundations, flip, draw, undo
    g = Game("Klondike", 1, seed=3, demo=True)
    assert [len(p) for p in g.tab] == list(range(1, 8)) and len(g.stock) == 24
    assert all(p[-1][3] for p in g.tab) and not any(c[3] for p in g.tab for c in p[:-1])
    g.tab = [[C(9, 0)], [C(10, 1)], [C(10, 0)], [], [C(5, 2, False), C(13, 3)], [C(1, 1)], [C(2, 1)]]
    assert g.legal(("t", 0), 0, ("t", 1)) and not g.legal(("t", 0), 0, ("t", 2)), "colours"
    assert not g.legal(("t", 0), 0, ("t", 3)), "only kings go to an empty column"
    assert g.move(("t", 4), 1, ("t", 3)) and g.tab[4][-1][3], "king to empty, card underneath turns up"
    assert g.move(("t", 5), 0, ("f", 0)) and g.move(("t", 6), 0, ("f", 0)), "ace, two to the foundation"
    assert not g.legal(("t", 1), 0, ("f", 0)), "a ten on a two"
    g.undo()
    assert len(g.found[0]) == 1 and len(g.tab[6]) == 1, "undo"
    g = Game("Klondike", 3, seed=4, demo=True)
    g.draw()
    assert len(g.waste) == 3 and len(g.stock) == 21
    for _ in range(7):
        g.draw()
    assert not g.stock and len(g.waste) == 24
    g.draw()
    assert len(g.stock) == 24 and not g.waste, "the waste turns over"
    # Spider: runs of one suit move together, mixed runs do not; a full run leaves; dealing needs full columns
    g = Game("Spider", 2, seed=5, demo=True)
    assert sum(len(p) for p in g.tab) == 54 and len(g.stock) == 50
    g.tab = [[C(9, 0), C(8, 0), C(7, 0)], [C(10, 1)], [C(9, 1), C(8, 0)], [C(4, 0)]] + [[C(5, 1)] for _ in range(6)]
    assert g.legal(("t", 0), 0, ("t", 1)), "a same-suit run on any suit one higher"
    assert not g.can_pick(("t", 2), 0), "a mixed run does not move together"
    assert g.can_pick(("t", 2), 1)
    g.tab[0] = [C(5, 2, False)] + [C(r, 0) for r in range(13, 1, -1)]
    g.tab[3] = [C(1, 0)]
    assert g.move(("t", 3), 0, ("t", 0)) and g.done == [0] and len(g.tab[0]) == 1 and g.tab[0][0][3], "run off"
    g.tab[3] = []
    assert not g.draw(), "dealing with an empty column"
    g.tab[3] = [C(6, 1)]
    assert g.draw() and len(g.stock) == 40
    # FreeCell: cells, foundations, the supermove limit
    g = Game("FreeCell", 1, demo=True)
    assert [len(p) for p in g.tab] == [7, 7, 7, 7, 6, 6, 6, 6]
    run = [C(9, 0), C(8, 1), C(7, 3), C(6, 2), C(5, 0)]
    g.tab = [list(run), [C(10, 1)], [C(2, 0)], [C(3, 0)], [C(4, 3)], [C(11, 2)], [C(12, 2)], [C(13, 2)]]
    g.cells = [[C(1, 2)], [C(1, 3)], [], []]                 # two free cells, no empty column: (2+1)*1 = 3
    assert g.supermove() == 3 and not g.legal(("t", 0), 0, ("t", 1)), "five cards with room for three"
    g.cells[0] = []
    assert g.supermove() == 4 and not g.legal(("t", 0), 0, ("t", 1))
    g.cells[1] = []
    assert g.supermove() == 5 and g.legal(("t", 0), 0, ("t", 1)), "five with four free cells"
    g.tab[2] = []
    assert g.supermove() == 10 and g.supermove(to_empty=True) == 5
    assert g.move(("t", 3), 0, ("c", 0)) and not g.legal(("t", 4), 0, ("c", 0)), "one card per cell"
    # win detection
    g = Game("FreeCell", 2, demo=True)
    g.tab = [[] for _ in range(8)]
    g.found = [[C(r, s) for r in range(1, 14)] for s in range(4)]
    g.found[0].pop()
    g.tab[0] = [C(13, 0)]
    assert not g.won and g.move(("t", 0), 0, ("f", 0)) and g.won and g.won_t is not None
    # the bots win some deals
    wins = {"Klondike": 0, "FreeCell": 0, "Spider": 0}
    for v, seeds in (("Klondike", range(20)), ("FreeCell", range(1, 6)), ("Spider", range(6))):
        for sd in seeds:
            g = Game(v, sd if v == "FreeCell" else 1, seed=sd, demo=True)
            bot = Bot(g)
            for _ in range(6000):
                if not bot.step():
                    break
            wins[v] += g.won
    assert wins["FreeCell"] >= 4, wins
    assert wins["Klondike"] >= 2, wins
    assert wins["Spider"] >= 1, wins
    # hint and auto-complete
    g = Game("Klondike", 1, seed=8, demo=True)
    assert g.find_hint() is not None
    g = Game("FreeCell", 3, demo=True)
    g.tab = [[C(r, s)] for r, s in ((13, 0), (13, 1), (13, 2), (13, 3))] + [[] for _ in range(4)]
    g.found = [[C(r, s) for r in range(1, 13)] for s in range(4)]
    assert g.can_autocomplete()
    while g.auto_step():
        pass
    assert g.won
    # mouse: drag a card onto a legal column, click sends to the foundation
    g = Game("Klondike", 1, seed=3)
    g.tab = [[C(9, 0)], [C(10, 1)], [C(10, 0)], [], [C(13, 3)], [C(1, 1)], [C(2, 2)]]
    render(g, 100, 32)
    L = g.last_layout
    x0, y0 = L.xs[0] + 2, L.tab_y + 2
    x1, y1 = L.xs[1] + 2, L.tab_y + 4
    term = FakeTerm([], [(0, ("left", x0, y0 // 2)), (0, ("move", x0 + 4, y0 // 2 + 1)), (0, ("move", x1, y1 // 2)),
                         (0, ("up", x1, y1 // 2))])
    apply_mouse(term, g, 100, 32)
    assert len(g.tab[1]) == 2 and not g.tab[0], ("drag", [len(p) for p in g.tab])
    ax, ay = L.xs[5] + 2, L.tab_y + 2
    term = FakeTerm([], [(0, ("left", ax, ay // 2)), (0, ("up", ax, ay // 2))])
    apply_mouse(term, g, 100, 32)
    assert len(g.found[0]) == 1 or any(len(f) == 1 for f in g.found), "click to the foundation"
    # keyboard: pick up and drop
    g = Game("Klondike", 1, seed=3)
    g.tab = [[C(9, 0)], [C(10, 1)], [C(10, 0)], [], [C(13, 3)], [C(1, 1)], [C(2, 2)]]
    render(g, 100, 32)
    cur = Cursor()
    for k in (" ", "right", " "):
        game_key(g, cur, k)
    assert len(g.tab[1]) == 2, "keyboard move"
    # every size, long piles, titles, auto mode
    g = Game("Spider", 4, seed=9, demo=True)
    g.tab[0] = [C(r, 1, False) for r in range(6)] + [C(r, 0) for r in range(13, 0, -1)] + [C(r, 2) for r in range(13, 5, -1)]
    for cols, rows in ((60, 22), (100, 32), (180, 50)):
        cv = render(g, cols, rows)
        cv.emit()
        ys = g.last_layout.offsets(g.tab[0])
        assert ys[-1] + g.last_layout.chp <= (rows - 1) * 2, "a long pile runs off the table"
        d = TitleDemo()
        for i in range(30):
            d.scene(cols, rows, 0.1)
        for sel in range(4):
            render_menu(d, cols, rows, sel, 0.05, sel == 3).emit()
    for v in VARIANTS:
        g = Game(v, demo=True)
        for cols, rows in ((60, 22), (180, 50)):
            render(g, cols, rows).emit()
    try:
        TitleDemo().scene(20, 8, 0.1)
        raise AssertionError("a tiny table should refuse")
    except ValueError:
        pass
    term = FakeTerm([(0.1, "+"), (0.2, "+"), (0.5, " "), (0.6, "?"), (0.7, "x"), (0.8, " "), (1.2, "esc")])
    run_auto(term, "FreeCell", {"Klondike": 1, "Spider": 1, "FreeCell": 1})
    assert term.frames > 5 and not term.script
    assert not os.path.exists(tmp), "auto mode wrote a score"
    print("Self-test ok: deal #1, Klondike / Spider / FreeCell rules, supermove limit, run off, undo, win; bots won "
          "Klondike %d/20, FreeCell %d/5, Spider 1-suit %d/6; hint, auto-complete, mouse drag and click, keys, "
          "three sizes, titles, auto mode (%.1fs)" % (wins["Klondike"], wins["FreeCell"], wins["Spider"], time.time() - t0))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
