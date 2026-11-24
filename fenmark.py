#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""FENMARK - probe the bog, mend the glass.

Odile Sedge is the warden of the Fenmark, a lantern-lit peat marsh where the ground lies. By day she sounds the
fen with her ash pole: every tussock she probes tells how many hidden bog-eyes (sinkholes under the moss) touch
it, and she plants reed flags where the eyes must be. By night she mends the broken leadlight windows of the old
pump-house from the glazier's ledger: the numbers beside each row and column say how long the runs of glass are,
and when the pane is complete it lights up in colour.

Two kinds of pure-logic puzzles:
  Bog Sounding    numbers count the bog-eyes around a cell; probe, flag, chord. The first probe is always safe
                  and every fen is laid so that it can be sounded WITHOUT guessing - a logic solver proves it
                  before the fen is handed over. Reedbed, Peat Meadow, Deep Fen and custom sizes, best times.
  Leadlight       picture-from-clues panes: fill glass, mark lead, drag along a row. 22 hand-made windows that
                  turn into coloured pictures, plus generated panes; every pane has exactly one solution that
                  plain row-by-row logic finds (checked by the line solver).

Undo, hints (the solver explains the next deduction and highlights the cells it used), check for errors (costs
time), progress and best times. Auto mode shows the solver at work, one explained deduction at a time, using only
what the player can see.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
"""
import math
import random
import sys
import time

from arcadekit import (ACCENTS, AUTO_LABEL, PANEL_BG, PANEL_FG, PAUSE_LINES, AutoMode, Canvas,
                       KeyTerminal, clamp, footer, load_scores, mix, overlay, scale_art, shade, shared_key, submit,
                       title_screen)
from arcadesound import Sound

GAME = "fenmark"
NAME = "FENMARK"
TAGLINE = "probe the bog, mend the glass"
ACCENTS.setdefault(NAME, ((236, 228, 150), (86, 170, 150)))

MIN_COLS, MIN_ROWS = 70, 22


# =============================================================================================
# Bog Sounding: the fen, its hidden bog-eyes and the numbers
# =============================================================================================
def neighbours(w, h):
    nb = []
    for i in range(w * h):
        x, y = i % w, i // w
        nb.append(tuple((y + dy) * w + x + dx for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                        if (dx or dy) and 0 <= x + dx < w and 0 <= y + dy < h))
    return nb


_NB = {}


def nb_of(w, h):
    k = (w, h)
    if k not in _NB:
        _NB[k] = neighbours(w, h)
    return _NB[k]


class Fen:
    """A laid fen: where the bog-eyes are and the number of every cell."""

    def __init__(self, w, h, eyes):
        self.w, self.h, self.n = w, h, w * h
        self.nb = nb_of(w, h)
        self.eye = bytearray(self.n)
        for i in eyes:
            self.eye[i] = 1
        self.count = sum(self.eye)
        self.recount()

    def recount(self):
        e = self.eye
        self.num = [sum(e[j] for j in self.nb[i]) for i in range(self.n)]


# --- the logic: what a player can be sure of from the open numbers --------------------------------------
class Step:
    """One deduction: the rule, the numbers it read (src), and the cells it proves safe or bog-eye."""
    __slots__ = ("rule", "src", "safe", "mines", "text")

    def __init__(self, rule, src, safe, mines, text=""):
        self.rule, self.src, self.safe, self.mines, self.text = rule, tuple(src), tuple(safe), tuple(mines), text


def cell_name(i, w):
    return "%s%d" % (col_letter(i % w), i // w + 1)


def col_letter(x):
    s = ""
    x += 1
    while x:
        x, r = divmod(x - 1, 26)
        s = chr(65 + r) + s
    return s


def plural(n, one, many):
    return "%d %s" % (n, one if n == 1 else many)


class Logic:
    """A player's knowledge of a fen: the open cells with their numbers, the cells proved to be bog-eyes and the
    cells proved safe but not yet probed. find() returns the next deductions; nothing hidden is ever read."""
    ENUM_MAX = 20            # largest group of frontier cells the solver weighs case by case
    ENUM_NODES = 60000

    def __init__(self, w, h, total):
        self.w, self.h, self.n = w, h, w * h
        self.nb = nb_of(w, h)
        self.total = total
        self.num = [-1] * self.n            # -1: not open
        self.mine = bytearray(self.n)       # proved bog-eye
        self.safe = bytearray(self.n)       # proved safe (open cells included)

    def copy(self):
        o = Logic.__new__(Logic)
        o.w, o.h, o.n, o.nb, o.total = self.w, self.h, self.n, self.nb, self.total
        o.num, o.mine, o.safe = self.num[:], bytearray(self.mine), bytearray(self.safe)
        return o

    def open(self, i, number):
        self.num[i] = number
        self.safe[i] = 1

    def unknown(self, i):
        return not self.safe[i] and not self.mine[i]

    def constraints(self):
        """[(cell, frozenset of unknown neighbours, bog-eyes still missing among them)] for open numbers that
        still touch unknown cells."""
        out = []
        num, mine, safe, nb = self.num, self.mine, self.safe, self.nb
        for i in range(self.n):
            v = num[i]
            if v < 0:
                continue
            u = []
            m = 0
            for j in nb[i]:
                if mine[j]:
                    m += 1
                elif not safe[j]:
                    u.append(j)
            if u:
                out.append((i, frozenset(u), v - m))
        return out

    def find(self, first=True):
        """The next deductions, simplest rule first. first=True stops at the first rule that finds anything."""
        cons = self.constraints()
        w = self.w
        out = []
        # 1. one number on its own
        for c, u, r in cons:
            if r == 0:
                out.append(Step("clear", [c], sorted(u), [], "The %d at %s already has its %s: its other "
                                "neighbours are safe." % (self.num[c], cell_name(c, w),
                                                          plural(self.num[c], "bog-eye", "bog-eyes"))))
            elif r == len(u):
                out.append(Step("full", [c], [], sorted(u), "The %d at %s still needs %s and has just %s left: "
                                "%s." % (self.num[c], cell_name(c, w), plural(r, "bog-eye", "bog-eyes"),
                                         plural(r, "cell", "cells"), "it is a bog-eye" if r == 1 else
                                         "all are bog-eyes")))
        if out and first:
            return self._dedupe(out)
        # 2. two numbers side by side
        if not out:
            out = self._pairs(cons)
            if out and first:
                return self._dedupe(out)
        # 3. the count of bog-eyes left
        if not out:
            left = self.total - sum(self.mine)
            unk = [i for i in range(self.n) if self.unknown(i)]
            if unk and left == 0:
                out.append(Step("count", [], unk, [], "Every bog-eye is found: all hidden cells are safe."))
            elif unk and left == len(unk):
                out.append(Step("count", [], [], unk, "%s left and %s hidden: all are bog-eyes." % (
                    plural(left, "bog-eye", "bog-eyes"), plural(left, "cell", "cells"))))
        # 4. weighing every way the bog-eyes can lie around a group of numbers
        if not out:
            out = self._enumerate(cons)
        return self._dedupe(out)

    def _dedupe(self, steps):
        seen = set()
        res = []
        for s in steps:
            safe = tuple(i for i in s.safe if i not in seen)
            mines = tuple(i for i in s.mines if i not in seen)
            if safe or mines:
                seen.update(safe)
                seen.update(mines)
                s.safe, s.mines = safe, mines
                res.append(s)
        return res

    def _pairs(self, cons):
        w = self.w
        by_cell = {}
        for k, (c, u, r) in enumerate(cons):
            for j in u:
                by_cell.setdefault(j, []).append(k)
        out = []
        done = set()
        for ka, (ca, ua, ra) in enumerate(cons):
            partners = set()
            for j in ua:
                partners.update(by_cell[j])
            for kb in sorted(partners):
                if kb == ka or (kb, ka) in done:
                    continue
                done.add((ka, kb))
                cb, ub, rb = cons[kb]
                inter = ua & ub
                if not inter:
                    continue
                oa, ob = ua - ub, ub - ua
                for (x, ux, rx, ox), (y, uy, ry, oy) in (((ca, ua, ra, oa), (cb, ub, rb, ob)),
                                                         ((cb, ub, rb, ob), (ca, ua, ra, oa))):
                    # y's own cells hold at least ry - (what the shared cells can hold)
                    m = min(len(inter), rx)
                    if oy and ry - m == len(oy):
                        out.append(Step("pair", [x, y], [], sorted(oy), (
                            "The %d at %s can hold at most %s where it overlaps the %d at %s, so the %d's other "
                            "%s." % (self.num[x], cell_name(x, w), plural(m, "bog-eye", "bog-eyes"), self.num[y],
                                     cell_name(y, w), self.num[y],
                                     "cell is a bog-eye" if len(oy) == 1 else "%d cells are all bog-eyes" % len(oy)))))
                    # x's own cells keep what the shared cells cannot take
                    k = max(0, ry - len(oy))
                    if ox and rx - k == 0:
                        out.append(Step("pair", [y, x], sorted(ox), [], (
                            "The %d at %s needs %s where it overlaps the %d at %s - all the %d can take - so the "
                            "%d's other %s safe." % (self.num[y], cell_name(y, w), plural(k, "bog-eye", "bog-eyes"),
                                                     self.num[x], cell_name(x, w), self.num[x], self.num[x],
                                                     "cell is" if len(ox) == 1 else "cells are"))))
        return out

    def _enumerate(self, cons):
        if not cons:
            return []
        w = self.w
        # groups of frontier cells linked by shared numbers
        parent = {}

        def root(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        for c, u, r in cons:
            for j in u:
                parent.setdefault(j, j)
            it = iter(u)
            a = root(next(it))
            for j in it:
                b = root(j)
                if a != b:
                    parent[b] = a
        groups = {}
        for j in parent:
            groups.setdefault(root(j), []).append(j)
        left = self.total - sum(self.mine)
        frontier = set(parent)
        interior = [i for i in range(self.n) if self.unknown(i) and i not in frontier]
        out = []
        single = len(groups) == 1
        for g in sorted(groups.values(), key=len):
            if len(g) > self.ENUM_MAX:
                continue
            gs = set(g)
            gc = [(c, u, r) for c, u, r in cons if u & gs]
            res = self._weigh(sorted(g), gc, left, len(interior) if single else None)
            if res is None:
                continue
            always, never, ks = res
            src = sorted(c for c, u, r in gc)
            if always or never:
                txt = ("Weighing every way the bog-eyes can lie around %s: %s." % (
                    " ".join("%d@%s" % (self.num[c], cell_name(c, w)) for c in src[:4]) + (" ..." if len(src) > 4
                                                                                           else ""),
                    "these cells are always bog-eyes" if always and not never else
                    "these cells are never bog-eyes" if never and not always else
                    "some cells are always bog-eyes, some never"))
                out.append(Step("weigh", src, sorted(never), sorted(always), txt))
            if single and interior:
                if all(left - k == 0 for k in ks):
                    out.append(Step("count", src, interior, [], "Every way the numbers can be met uses all %s "
                                    "left: the cells away from the numbers are safe." % plural(
                                        left, "bog-eye", "bog-eyes")))
                elif all(left - k == len(interior) for k in ks):
                    out.append(Step("count", src, [], interior, "The numbers can take at most %d of the %s left: "
                                    "the cells away from them are all bog-eyes." % (
                                        max(ks), plural(left, "bog-eye", "bog-eyes"))))
            if out:
                return out
        return out

    def _weigh(self, cells, cons, left, interior):
        """Every assignment of the group's cells that meets its numbers (and the count). Returns (always mine,
        never mine, set of mine counts) or None when the group is too big to weigh."""
        idx = {c: k for k, c in enumerate(cells)}
        cl = [([idx[j] for j in u], r) for c, u, r in cons]
        of = [[] for _ in cells]
        for ci, (vs, r) in enumerate(cl):
            for v in vs:
                of[v].append(ci)
        # order cells so that constraints close early
        order, seen = [], set()
        for vs, r in sorted(cl, key=lambda t: len(t[0])):
            for v in vs:
                if v not in seen:
                    seen.add(v)
                    order.append(v)
        n = len(cells)
        assign = [-1] * n
        cnt_m = [0] * len(cl)            # mines assigned per constraint
        cnt_u = [len(vs) for vs, r in cl]
        need = [r for vs, r in cl]
        mines_in = [0] * n
        sols = [0]
        ks = set()
        nodes = [0]
        total = [0]

        def rec(p):
            nodes[0] += 1
            if nodes[0] > self.ENUM_NODES:
                raise OverflowError
            if p == n:
                k = total[0]
                if k > left:
                    return
                if interior is not None and left - k > interior:
                    return
                sols[0] += 1
                ks.add(k)
                for v in range(n):
                    if assign[v]:
                        mines_in[v] += 1
                return
            v = order[p]
            for val in (0, 1):
                ok = True
                for ci in of[v]:
                    m = cnt_m[ci] + val
                    u = cnt_u[ci] - 1
                    if m > need[ci] or m + u < need[ci]:
                        ok = False
                        break
                if not ok:
                    continue
                if val and total[0] + 1 > left:
                    continue
                assign[v] = val
                total[0] += val
                for ci in of[v]:
                    cnt_m[ci] += val
                    cnt_u[ci] -= 1
                rec(p + 1)
                for ci in of[v]:
                    cnt_m[ci] -= val
                    cnt_u[ci] += 1
                total[0] -= val
                assign[v] = -1
        try:
            rec(0)
        except OverflowError:
            return None
        if not sols[0]:
            return None
        always = [cells[v] for v in range(n) if mines_in[v] == sols[0]]
        never = [cells[v] for v in range(n) if mines_in[v] == 0]
        return always, never, ks


def sound_out(fen, first, logic=None):
    """The solver sounds the fen from the first probe on, knowing nothing hidden. Returns (solved, logic)."""
    lg = logic or Logic(fen.w, fen.h, fen.count)
    num, nb, n = fen.num, fen.nb, fen.n

    def reveal(i):
        stack = [i]
        while stack:
            c = stack.pop()
            if lg.num[c] >= 0:
                continue
            lg.open(c, num[c])
            if num[c] == 0:
                for j in nb[c]:
                    if lg.num[j] < 0 and not lg.mine[j]:
                        stack.append(j)
    if logic is None:
        reveal(first)
    while True:
        steps = lg.find(first=False)
        if not steps:
            break
        for s in steps:
            for j in s.mines:
                lg.mine[j] = 1
            for j in s.safe:
                if fen.eye[j]:
                    raise AssertionError("the solver proved a bog-eye safe")
                reveal(j)
    opened = sum(1 for i in range(n) if lg.num[i] >= 0)
    return opened == n - fen.count, lg


def lay_fen(w, h, count, first, rng, budget=None):
    """A fen with no bog-eye on or next to the first probe that the solver can sound to the end without a single
    guess. Stuck fens are mended: a bog-eye the solver could not settle is moved away from the open ground,
    and the fen is sounded again from the first probe. Returns (fen, tries)."""
    n = w * h
    nb = nb_of(w, h)
    keep = {first} | set(nb[first])
    if n - len(keep) < count:
        keep = {first}
    free = [i for i in range(n) if i not in keep]
    t_end = None if budget is None else time.perf_counter() + budget
    tries = 0
    best = None
    while True:
        eyes = set(rng.sample(free, count))
        fen = Fen(w, h, eyes)
        for _ in range(4 * count + 40):
            tries += 1
            ok, lg = sound_out(fen, first)
            if ok:
                return fen, tries
            opened = sum(1 for i in range(n) if lg.num[i] >= 0)
            if best is None or opened > best[0]:
                best = (opened, set(i for i in range(n) if fen.eye[i]))
            if t_end is not None and time.perf_counter() > t_end:
                return Fen(w, h, best[1]), -tries
            unk = [i for i in range(n) if lg.unknown(i)]
            front = [i for i in unk if any(lg.num[j] >= 0 for j in nb[i])]
            inner = [i for i in unk if i not in keep and not any(lg.num[j] >= 0 for j in nb[i])]
            fm = [i for i in front if fen.eye[i]]
            dst = [i for i in inner if not fen.eye[i]]
            if fm and dst:
                a, b = rng.choice(fm), rng.choice(dst)
            else:
                fs = [i for i in front if not fen.eye[i]]
                im = [i for i in inner if fen.eye[i]]
                if not (fs and im):
                    break
                a, b = rng.choice(im), rng.choice(fs)
                if rng.random() < 0.5:
                    break
            fen.eye[a], fen.eye[b] = 0, 1
            fen.recount()


# =============================================================================================
# Leadlight: picture-from-clues panes and the line solver
# =============================================================================================
UNK, GLASS, LEAD = 0, 1, 2


def clues_of(cells):
    out, run = [], 0
    for c in cells:
        if c:
            run += 1
        elif run:
            out.append(run)
            run = 0
    if run:
        out.append(run)
    return out


def line_solve(line, clues):
    """Everything plain logic can say about one row or column: a new line (UNK / GLASS / LEAD per cell), or None
    when no arrangement of the blocks fits the cells already set."""
    n, k = len(line), len(clues)
    pre = [0] * (n + 1)                 # filled cells in line[:i]
    for i, c in enumerate(line):
        pre[i + 1] = pre[i] + (c == GLASS)
    pe = [0] * (n + 1)                  # lead cells in line[:i]
    for i, c in enumerate(line):
        pe[i + 1] = pe[i] + (c == LEAD)

    def no_glass(a, b):
        return pre[b] - pre[a] == 0

    def no_lead(a, b):
        return pe[b] - pe[a] == 0
    # f[j][i]: blocks 0..j-1 fit in line[0:i]
    f = [[False] * (n + 1) for _ in range(k + 1)]
    for i in range(n + 1):
        f[0][i] = no_glass(0, i)
    for j in range(1, k + 1):
        L = clues[j - 1]
        fj, fp = f[j], f[j - 1]
        for i in range(n + 1):
            v = i > 0 and line[i - 1] != GLASS and fj[i - 1]
            if not v and i >= L and no_lead(i - L, i):
                s = i - L
                if j == 1:
                    v = fp[s]
                else:
                    v = s >= 1 and line[s - 1] != GLASS and fp[s - 1]
            fj[i] = v
    if not f[k][n]:
        return None
    # g[j][i]: blocks j..k-1 fit in line[i:n]
    g = [[False] * (n + 2) for _ in range(k + 1)]
    for i in range(n + 1):
        g[k][i] = no_glass(i, n)
    for j in range(k - 1, -1, -1):
        L = clues[j]
        gj, gn = g[j], g[j + 1]
        for i in range(n, -1, -1):
            v = i < n and line[i] != GLASS and gj[i + 1]
            if not v and i + L <= n and no_lead(i, i + L):
                e = i + L
                if j == k - 1:
                    v = gn[e]
                else:
                    v = e < n and line[e] != GLASS and gn[e + 1]
            gj[i] = v
    can_fill = [False] * n
    can_lead = [False] * n
    for j in range(k):
        L = clues[j]
        for s in range(n - L + 1):
            e = s + L
            if not no_lead(s, e):
                continue
            if s > 0 and line[s - 1] == GLASS or e < n and line[e] == GLASS:
                continue
            ok_pre = f[0][s] if j == 0 else (s >= 1 and f[j][s - 1])
            ok_suf = g[k][e] if j == k - 1 else (e < n and g[j + 1][e + 1])
            if ok_pre and ok_suf:
                for i in range(s, e):
                    can_fill[i] = True
    for i in range(n):
        if line[i] == GLASS:
            continue
        for j in range(k + 1):
            if f[j][i] and g[j][i + 1]:
                can_lead[i] = True
                break
    out = list(line)
    for i in range(n):
        if line[i] == UNK:
            if can_fill[i] and not can_lead[i]:
                out[i] = GLASS
            elif can_lead[i] and not can_fill[i]:
                out[i] = LEAD
            elif not can_fill[i] and not can_lead[i]:
                return None
        elif line[i] == GLASS and not can_fill[i]:
            return None
    return out


class Pane:
    """A leadlight pane: its solution (letters for colours, '.' for lead) and the clues."""

    def __init__(self, rows, name="", pal=None, story="", generated=False):
        self.rows = rows
        self.name, self.story, self.generated = name, story, generated
        self.h, self.w = len(rows), len(rows[0])
        self.sol = [[c != "." for c in r] for r in rows]
        self.pal = pal or {}
        self.rclues = [clues_of(r) for r in self.sol]
        self.cclues = [clues_of([self.sol[y][x] for y in range(self.h)]) for x in range(self.w)]

    def colour(self, x, y):
        return colour_of(self.rows[y][x], self.pal)


def line_text(kind, idx, clues):
    return "%s %d (%s)" % ("Row" if kind == "row" else "Column", idx + 1, " ".join(map(str, clues)) or "0")


def explain_line(kind, idx, clues, before, after):
    """Words for one line deduction."""
    n = len(before)
    name = line_text(kind, idx, clues)
    new_g = sum(1 for a, b in zip(before, after) if a == UNK and b == GLASS)
    new_l = sum(1 for a, b in zip(before, after) if a == UNK and b == LEAD)
    blank = all(c == UNK for c in before)
    if not clues:
        return "%s: no glass at all - lead the whole line." % name
    if blank and sum(clues) + len(clues) - 1 == n:
        return "%s: the blocks and their gaps fill the line exactly." % name
    if blank:
        return "%s: however the blocks slide, they overlap on %s." % (
            name, plural(new_g, "cell", "cells") if new_g else "nothing")
    if all(c != UNK for c in after) and new_l and not new_g:
        return "%s: every block is in place - the rest is lead." % name
    if all(c != UNK for c in after) and new_g and not new_l:
        return "%s: only glass is left to place." % name
    bits = []
    if new_g:
        bits.append(plural(new_g, "cell is", "cells are") + " glass")
    if new_l:
        bits.append(plural(new_l, "cell is", "cells are") + " lead")
    return "%s: with the cells already set, in every fit %s." % (name, " and ".join(bits))


def pane_steps(rclues, cclues, grid=None, best=True):
    """The line solver, one line at a time: yields (kind, index, before, after) until nothing more follows.
    best=True takes the line that settles the most cells next (the nicer order to watch)."""
    h, w = len(rclues), len(cclues)
    grid = [[UNK] * w for _ in range(h)] if grid is None else [r[:] for r in grid]
    dirty = set([("row", y) for y in range(h)] + [("col", x) for x in range(w)])
    while dirty:
        cand = []
        for kind, i in sorted(dirty):
            line = grid[i][:] if kind == "row" else [grid[y][i] for y in range(h)]
            clues = rclues[i] if kind == "row" else cclues[i]
            res = line_solve(line, clues)
            if res is None:
                yield (kind, i, line, None)
                return
            gain = sum(1 for a, b in zip(line, res) if a != b)
            cand.append((gain, kind, i, line, res))
            if gain and not best:
                break
        dirty = set((kind, i) for gain, kind, i, line, res in cand if gain) | (dirty - set((c[1], c[2]) for c in cand))
        good = [c for c in cand if c[0]]
        if not good:
            return
        gain, kind, i, line, res = max(good, key=lambda c: c[0]) if best else good[0]
        dirty.discard((kind, i))
        for j, v in enumerate(res):
            if kind == "row":
                if grid[i][j] != v:
                    grid[i][j] = v
                    dirty.add(("col", j))
            else:
                if grid[j][i] != v:
                    grid[j][i] = v
                    dirty.add(("row", j))
        yield (kind, i, line, res)


def line_solvable(rclues, cclues):
    """True when the line solver alone settles every cell (so the solution is unique)."""
    h, w = len(rclues), len(cclues)
    grid = [[UNK] * w for _ in range(h)]
    changed = True
    while changed:
        changed = False
        for y in range(h):
            res = line_solve(grid[y], rclues[y])
            if res is None:
                return False, grid
            if res != grid[y]:
                grid[y] = res
                changed = True
        for x in range(w):
            col = [grid[y][x] for y in range(h)]
            res = line_solve(col, cclues[x])
            if res is None:
                return False, grid
            if res != col:
                changed = True
                for y in range(h):
                    grid[y][x] = res[y]
    return all(c != UNK for r in grid for c in r), grid


# --- the glass: colours of the hand-made windows ------------------------------------------------------------
PAL = {
    "k": (58, 52, 78), "w": (238, 236, 222), "s": (164, 170, 186), "r": (218, 66, 60), "o": (240, 140, 50),
    "y": (250, 214, 86), "n": (150, 98, 56), "N": (98, 64, 42), "g": (98, 190, 86), "G": (46, 124, 70),
    "l": (180, 224, 92), "c": (96, 206, 226), "b": (74, 124, 222), "B": (42, 62, 146), "p": (156, 94, 206),
    "m": (238, 132, 174), "t": (44, 156, 144), "f": (236, 198, 152),
}


def colour_of(ch, pal=None):
    if pal and ch in pal:
        return pal[ch]
    return PAL.get(ch, (200, 200, 210))


PICTURES = [
    # name, story line, rows, palette overrides
    ("Lamp of the Weir", "The lamp that hangs over the sluice at night.", [
        "....kk....", "...k..k...", "..kkkkkk..", ".k.yyyy.k.", ".k.yooy.k.", ".k.yrry.k.", ".k.yyyy.k.",
        "..kkkkkk..", "...kkkk...", "..kk..kk.."], {"k": (96, 90, 112)}),
    ("Marsh Frog", "He sings under the boardwalk every spring.", [
        ".ww....ww.", "wkkw..wkkw", "wkkwggwkkw", ".wwggggww.", "gggggggggg", "g.rrrrrr.g", "gg......gg",
        ".gggggggg.", "gg.g..g.gg", "g..g..g..g"], {}),
    ("Night Moth", "Drawn to the warden's lamp, never caught.", [
        ".k......k.", "..k....k..", "pp.k..k.pp", "pmp.kk.pmp", "pppmkkmppp", ".ppmkkmpp.", "..ppkkpp..",
        ".pmpkkpmp.", ".pp.kk.pp.", "....kk...."], {"k": (110, 96, 120)}),
    ("Slow Snail", "It crossed the dyke path in a single week.", [
        "..........", "....nnn...", "...nyyyn..", "..nyynnyn.", "..nynyyny.", "k.nynnyyn.", ".k.nyyyn..",
        "ffffnnnn..", ".fffffffff", ".........."], {"k": (120, 110, 100)}),
    ("Toadstool", "Red caps grow where the old peat was cut.", [
        "...rrrr...", ".rrwrrrrr.", "rrrrrrwrrr", "rwrrrrrrrr", "rrrrrwrrwr", "..wwwwww..", "...wwww...",
        "...wwww...", "..wwwwww..", ".gggggggg."], {}),
    ("Warden's Kettle", "Always on the stove in the reed hut.", [
        "....kk....", "..kkkkkk..", ".k......k.", "kkbbbbbbkk", "k.bbbbbb.k", "k.bwbbbb.k", ".kbbbbbbkk",
        "..bbbbbb.k", "..kkkkkk..", ".kkkkkkkk."], {"k": (88, 84, 104)}),
    ("Dragonfly", "Blue darters over the open water.", [
        "....kk....", "ccc.kk.ccc", "cwcckkccwc", ".ccckkccc.", "..c.kk.c..", "cc..tt..cc", "cwc.tt.cwc",
        ".cc.tt.cc.", "....tt....", "....t....."], {"k": (70, 96, 120)}),
    ("Reed Flag", "Where a flag stands, the ground will not hold.", [
        ".k........", ".krrrr....", ".krrrrrr..", ".krrrrrrrr", ".krrrrrr..", ".krrrr....", ".k........",
        ".k......g.", ".k.g.g.gg.", "gggggggggg"], {"k": (150, 110, 70)}),
    ("Pump-house Key", "Iron, heavy, and always in the wrong pocket.", [
        "..yyyy....", ".yy..yy...", ".y.kk.y...", ".y.kk.y...", ".yy..yy...", "..yyyy....", "....y.....",
        "....yyy...", "....y.....", "....yyyy.."], {"y": (226, 182, 92), "k": (120, 40, 40)}),
    ("Bog Bean", "White fringed flowers on the black pools.", [
        "...mmmm...", "..mwwwwm..", ".mwwyywwm.", ".mwyyyywm.", ".mwwyywwm.", "..mwwwwm..", "...mmmm...",
        "....g.....", "..ggg.ggg.", ".gg.g..gg."], {}),
    ("Grey Heron", "Patient on one leg in the shallows.", [
        "......sss......", ".....swkss.....", ".....sssssyyyy.", "......ss.......", ".......s.......",
        "......ss.......", ".....sss.......", "....sswsss.....", "...sswwwsss....", "..ssswwwssss...",
        "...ssssssss.n..", ".......k....n..", ".......k...nnn.", ".n.....k....n..", "bbbbbbbbbbbbbbb"],
     {"k": (226, 180, 70)}),
    ("Windpump", "Its sails lift the water off the low fields.", [
        "ww...........ww", "www.........www", ".www.......www.", "..www.....www..", "...www...www...",
        "....wwrrrww....", ".....rrrrr.....", "....wwnnnww....", "...wwwnnnwww...", "..www.nnn.www..",
        ".www.nnnnn.www.", "www..nnnnn..www", "ww..nnnnnnn..ww", "....nnnynnn....", "ggggggggggggggg"], {}),
    ("Punt at Dusk", "Odile poles home under a low yellow moon.", [
        "..yy...........", ".yyyy..........", "..yy......k....", "..........k....", "......ff..k....",
        "......ff..k....", ".....ppppkk....", ".....pppp.k....", ".....pppp.k....", "......k.k.k....",
        "nnnnnnnnnnnnnnn", ".nnnnnnnnnnnnn.", "..b..bbk..bb...", "bbbbbbbbbbbbbbb", ".bbb..bbbb..bbb"],
     {"k": (150, 112, 72)}),
    ("Fen Owl", "It counts the bog-eyes too, from the willow.", [
        "..n.........n..", "..nn.......nn..", "..nnnnnnnnnnn..", ".nnwwwnnnwwwnn.", ".nwwkwwnwwkwwn.",
        ".nwkykwnwkykwn.", ".nwwkwwnwwkwwn.", ".nnwwwnynwwwnn.", ".nnnnnnynnnnnn.", ".nnfnfnfnfnfnn.",
        ".nnnfnfnfnfnnn.", "..nnnnnnnnnnn..", "...nnnnnnnnn...", "...yy.....yy...", "nnnnnnnnnnnnnnn"],
     {"y": (240, 170, 60)}),
    ("Will-o'-wisp", "A cold light that walks where no one should.", [
        "......c........", ".....ccc.......", "....ccwcc......", "...ccwwwcc.....", "...cwwywwc.....",
        "..ccwyyywcc....", "..cwyyyyywc....", "..cwyyyyywc....", "...cwyyywc.....", "....cwwwc......",
        ".....ccc.......", "...............", "..k.....k...k..", ".kkk...kkk.kkk.", "ttttttttttttttt"],
     {"c": (120, 230, 200), "k": (60, 110, 80)}),
    ("Eel in the Dyke", "Two eels, one ditch, no hurry at all.", [
        "bbbbbbbbbbbbbbb", "b.............b", "b..ttt........b", "b.ttwtt.......b", "b.tttttt...tt.b",
        "b...ttttt.ttttb", "b.....tttttt..b", "b.......tt....b", "b..tt.........b", "b.tttt..t.....b",
        "b..tttttt.....b", "b....tttttt...b", "b.........ttt.b", "b...........t.b", "bbbbbbbbbbbbbbb"],
     {"b": (64, 96, 160), "t": (120, 150, 80)}),
    ("Cattail Moon", "The reeds stand up to their knees in silver.", [
        "..........www..", ".........wwwww.", "...n.....wwwww.", "...n.....wwwww.", "..nnn.n...www..",
        "..nnn.n........", "..nnnnnn.......", "..nnnnnn..n....", "...g.nnn..n....", "...g.ggg.nnn...",
        ".g.g..g..nnn.g.", ".gg.g.g.g.g.gg.", "..gggg.ggggg...", "bbbbbbbbbbbbbbb", ".bb.bbbb.bb.bbb"],
     {"w": (246, 240, 196)}),
    ("The Warden", "Odile Sedge, hat, lamp and muddy boots.", [
        "......kkk......", ".....kkkkk.....", "..kkkkkkkkkkk..", ".....fffff.....", ".....fkfkf.....",
        ".....fffff.....", "......frf....k.", "....GGGGGGG.kyk", "...GGGGGGGGGyyy", "..GG.GGGGG..kyk",
        "..f..GGGGG.....", ".....GGGGG.....", ".....nn.nn.....", ".....nn.nn.....", "....nnn.nnn...."],
     {"k": (92, 70, 60)}),
    ("The Pump-house", "Red tiles, a tall stack, a lamp at the door.", [
        "..............ss....", ".........r....ss....", "........rrr...ss....", ".......rrrrr..ss....",
        "......rrrrrrr.ss....", ".....rrrrrrrrrss....", "....rrrrrrrrrrrrr...", "...rrrrrrrrrrrrrrr..",
        "....nnnnnnnnnnnnn...", "....n..nnnnnnn..n...", "....n..nnnyynn..n...", "....nnnnnnyynnnnn...",
        "....nnnnnnyynnnnn...", "gggggggggggggggggggg", ".bbbb.bbbbbbb.bbbbb."], {}),
    ("Lily Pond", "Pads, a pink cup and a frog's best seat.", [
        "..gggg.......mm.....", ".gggggg.....mmmm....", ".ggg.ggg...mmyymm...", ".gggggg.....mmmm....",
        "..gggg.....gggggg...", "..........gggggggg..", "....ll....ggg..ggg..", "...llll....gggggg...",
        "..llllll..........gg", "...llll.....ggg..ggg", "........b..ggggg.ggg", ".bb....bbb..ggg...gg",
        "bbbbb.bbbbb.......gg", "..........bbbb..bbbb", "bbb..bbbbbbbbbbbbbbb"], {}),
    ("Lantern Boat", "On midsummer night every boat carries one.", [
        "..........k.........", ".........kkk........", "........kyyyk.......", "........kyoyk.......",
        "........kyyyk.......", ".........kkk........", "..........k.........", "..........k.........",
        "....wwwwwwkwwwww....", "...wwwwwwwkwwwwww...", "nnnnnnnnnnnnnnnnnnnn", ".nnnnnnnnnnnnnnnnnn.",
        "..nnnnnnnnnnnnnnnn..", "bbb..bbbbbb..bbbbbbb", ".bbbb..bbb.bbbb..bb."], {"k": (110, 100, 90)}),
    ("Hedgehog", "It sleeps in the peat stack all winter.", [
        ".....k..k..k........", "...k.kk.kk.kk.k.....", "...kknnnnnnnnkk.....", "..knnnnnnnnnnnnk....",
        ".kknnnnnnnnnnnnkk...", ".knnnnnnnnnnnnnffff.", "kknnnnnnnnnnnnfffkff", ".knnnnnnnnnnnfffffff",
        "kknnnnnnnnnnnnffffk.", ".knnnnnnnnnnnnfff...", "..kknnnnnnnnnnkk....", "....kkkkkkkkkk......",
        ".....ff....ff.......", "..g.....g.......g...", "gggggggggggggggggggg"], {"k": (110, 80, 60)}),
]
PANES = [Pane(rows, name, pal, story) for name, story, rows, pal in PICTURES]
RANDOM_SIZES = ((10, 10), (15, 15), (20, 15))
GLASS_THEMES = (((96, 206, 226), (74, 124, 222)), ((250, 214, 86), (218, 66, 60)), ((180, 224, 92), (44, 156, 144)),
                ((238, 132, 174), (156, 94, 206)), ((240, 140, 50), (150, 98, 56)))


def max_col_clues(h):
    """The most clue numbers a column may carry (a 15-high pane must still fit a 70x22 window)."""
    return 5


def gen_pane(w, h, seed):
    """A generated pane: soft random shapes, kept only when the line solver alone settles it."""
    rng = random.Random(seed * 7919 + w * 31 + h)
    for _ in range(4000):
        dens = rng.uniform(0.5, 0.62)
        g = [[rng.random() < dens for _ in range(w)] for _ in range(h)]
        for _ in range(rng.choice((1, 1, 2))):           # smooth into blobs
            g2 = []
            for y in range(h):
                row = []
                for x in range(w):
                    c = sum(g[yy][xx] for yy in range(max(0, y - 1), min(h, y + 2))
                            for xx in range(max(0, x - 1), min(w, x + 2)))
                    tot = (min(h, y + 2) - max(0, y - 1)) * (min(w, x + 2) - max(0, x - 1))
                    row.append(c * 2 > tot if c * 2 != tot else g[y][x])
                g2.append(row)
            g = g2
        if not all(any(r) for r in g):
            continue
        rc = [clues_of(r) for r in g]
        cc = [clues_of([g[y][x] for y in range(h)]) for x in range(w)]
        if max(len(c) for c in cc) > max_col_clues(h) or max(len(c) for c in rc) > 7:
            continue
        ok, _ = line_solvable(rc, cc)
        if not ok:
            continue
        a, b = GLASS_THEMES[rng.randrange(len(GLASS_THEMES))]
        pal, rows = {}, []
        letters = "ABCDEFGH"
        for k, ch in enumerate(letters):
            pal[ch] = mix(a, b, k / (len(letters) - 1))
        ph = rng.random() * 6.28
        for y in range(h):
            s = ""
            for x in range(w):
                if g[y][x]:
                    v = 0.5 + 0.35 * math.sin(x * 0.45 + y * 0.3 + ph) + 0.15 * math.sin(x * 1.3 - y * 0.9)
                    s += letters[clamp(int(v * len(letters)), 0, len(letters) - 1)]
                else:
                    s += "."
            rows.append(s)
        return Pane(rows, "Pane No. %d" % (seed % 1000 + 1), pal, "A pane from the glazier's spare ledger.",
                    generated=True)
    raise RuntimeError("no pane found")


# =============================================================================================
# Pixel digits: small ones for small cells, smooth ones scaled from a finer font for big cells
# =============================================================================================
DIG3 = {
    "0": ["###", "#.#", "#.#", "#.#", "###"], "1": [".#.", "##.", ".#.", ".#.", "###"],
    "2": ["###", "..#", "###", "#..", "###"], "3": ["###", "..#", ".##", "..#", "###"],
    "4": ["#.#", "#.#", "###", "..#", "..#"], "5": ["###", "#..", "###", "..#", "###"],
    "6": ["###", "#..", "###", "#.#", "###"], "7": ["###", "..#", "..#", ".#.", ".#."],
    "8": ["###", "#.#", "###", "#.#", "###"], "9": ["###", "#.#", "###", "..#", "###"],
}
DIG5 = {
    "0": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": [".###.", "#...#", "....#", "..##.", "....#", "#...#", ".###."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    "6": [".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    "9": [".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."],
}
_GLYPH = {}


def glyph(ch, gh):
    """A digit as rows of booleans, gh pixels tall."""
    key = (ch, gh)
    g = _GLYPH.get(key)
    if g is None:
        if gh <= 6:
            src = DIG3[ch]
            gw = 3
            g = [[src[min(4, y * 5 // gh)][x] == "#" for x in range(gw)] for y in range(gh)]
        else:
            gw = max(4, int(gh * 5 / 7 + 0.5))
            # thicken the strokes of the fine font for larger sizes
            src = [[c == "#" for c in r] for r in DIG5[ch]]
            g = scale_art(src, gw, gh)
            if gh >= 14:
                t = max(1, gh // 14)
                g = [[any(g[y][xx] for xx in range(max(0, x - t), x + 1)) for x in range(gw)] for y in range(gh)]
        _GLYPH[key] = g
    return g


def glyph_w(text, gh, gap=None):
    gap = max(1, gh // 7) if gap is None else gap
    return sum(len(glyph(c, gh)[0]) for c in text) + max(0, len(text) - 1) * gap


def draw_digits(cv, text, cx, cy, gh, col, shadow=None, gap=None):
    """Digits centred on (cx, cy) in pixels."""
    gap = max(1, gh // 7) if gap is None else gap
    w = glyph_w(text, gh, gap)
    x = int(cx - w / 2 + 0.5)
    y0 = int(cy - gh / 2 + 0.5)
    W, H, px = cv.W, cv.H, cv.px
    for ch in text:
        g = glyph(ch, gh)
        for yy, row in enumerate(g):
            Y = y0 + yy
            if not 0 <= Y < H:
                continue
            for xx, b in enumerate(row):
                if b:
                    X = x + xx
                    if shadow is not None and gh >= 9 and 0 <= X + 1 < W and Y + 1 < H:
                        if not (yy + 1 < len(g) and xx + 1 < len(row) and g[yy + 1][xx + 1]):
                            px[Y + 1][X + 1] = shadow
                    if 0 <= X < W:
                        px[Y][X] = col
        x += len(g[0]) + gap


# =============================================================================================
# Sound: wet ground, reeds and glass
# =============================================================================================
def _chime(f, v=0.22):
    return [dict(w="sine", f=f, d=0.4, v=v), dict(w="sine", f=f * 2.0, d=0.25, v=v * 0.4, at=0),
            dict(w="tri", f=f * 3.01, d=0.1, v=v * 0.2, at=0)]


SND = Sound(GAME, {
    "probe": [dict(w="noise", f=700, f2=300, d=0.05, v=0.16), dict(w="sine", f=220, f2=160, d=0.05, v=0.12, at=0)],
    "splash": [dict(w="noise", f=2600, f2=600, d=0.22, v=0.16, r="lin"), dict(w="sine", f=520, f2=300, d=0.16, v=0.1,
                                                                             at=0)],
    "flag": [dict(w="noise", f=5000, f2=2400, d=0.06, v=0.1), dict(w="tri", f=880, d=0.04, v=0.12, at=0.02)],
    "unflag": [dict(w="tri", f=660, f2=440, d=0.05, v=0.12)],
    "chord": [dict(w="noise", f=1600, f2=500, d=0.12, v=0.16), dict(w="tri", f=330, d=0.06, v=0.12, at=0)],
    "gulp": [dict(w="sine", f=180, f2=50, d=0.5, v=0.42), dict(w="noise", f=300, f2=80, d=0.5, v=0.25, at=0),
             dict(w="sine", f=90, f2=40, d=0.4, v=0.3)],
    "won": [dict(w="tri", f=f, d=0.09, v=0.28) for f in (392, 523, 659, 784, 1047)] + _chime(1568, 0.2),
    "glass": [dict(w="tri", f=1760, d=0.03, v=0.12), dict(w="sine", f=2637, d=0.06, v=0.06, at=0)],
    "lead": [dict(w="square", f=330, d=0.02, v=0.08, duty=0.3)],
    "clear": [dict(w="tri", f=520, f2=390, d=0.04, v=0.1)],
    "line": [dict(w="sine", f=1319, d=0.08, v=0.1), dict(w="sine", f=1976, d=0.1, v=0.07)],
    "hint": _chime(988, 0.18) + _chime(1319, 0.12),
    "check": [dict(w="tri", f=660, d=0.05, v=0.16), dict(w="tri", f=990, d=0.08, v=0.14)],
    "wrong": [dict(w="square", f=196, f2=150, d=0.14, v=0.14, duty=0.3)],
    "undo": [dict(w="tri", f=660, f2=440, d=0.05, v=0.14)],
    "solved": [dict(w="sine", f=f, d=0.12, v=0.22) for f in (523, 659, 784, 1047, 1319)] + _chime(2093, 0.16) +
              [dict(w="tri", f=1568, d=0.6, v=0.12, vib=(5, 0.2), r="lin", at=0.6)],
    "move": [dict(w="tri", f=1200, d=0.012, v=0.04)],
    "menu": [dict(w="tri", f=660, d=0.025, v=0.2)],
    "start": [dict(w="tri", f=523, d=0.06, v=0.3), dict(w="tri", f=784, d=0.06, v=0.3), dict(w="tri", f=1047, d=0.16,
                                                                                            v=0.3)],
    "pause": [dict(w="tri", f=523, f2=392, d=0.07, v=0.22)],
    "sound_on": [dict(w="tri", f=440, d=0.06, v=0.35), dict(w="tri", f=880, d=0.12, v=0.35)],
})


# =============================================================================================
# Progress: best times in the shared score file
# =============================================================================================
DIFFS = (("Reedbed", 9, 9, 10), ("Peat Meadow", 16, 16, 40), ("Deep Fen", 30, 16, 99))
HINT_COST, CHECK_COST, RESCUE_COST = 15, 20, 30


def fmt_time(s):
    s = int(s)
    return "%d:%02d" % (s // 60, s % 60) if s < 3600 else "%d:%02d:%02d" % (s // 3600, s // 60 % 60, s % 60)


def sweep_key(w, h, count):
    for name, dw, dh, dc in DIFFS:
        if (dw, dh, dc) == (w, h, count):
            return name
    return "custom %dx%d/%d" % (w, h, count)


def pane_key(i):
    return "pane %02d" % (i + 1)


def random_key(w, h):
    return "random %dx%d" % (w, h)


_REC = [None]


def records(refresh=False):
    if refresh or _REC[0] is None:
        r = load_scores().get(GAME, {})
        _REC[0] = r if isinstance(r, dict) else {}
    return _REC[0]


def record(key, seconds):
    """Store a best time (whole seconds). Returns True for a new best."""
    new = submit(GAME, key, int(seconds), lower_is_better=True)
    rec = records(True)
    solved = sum(1 for i in range(len(PANES)) if pane_key(i) in rec)
    if solved:
        submit(GAME, "panes", solved)
        records(True)
    return new


# =============================================================================================
# A fen in play
# =============================================================================================
class Sweep:
    kind = "sweep"

    def __init__(self, w, h, count, seed=None, quiet=False, demo=False):
        self.w, self.h, self.n = w, h, w * h
        self.count = count
        self.key = sweep_key(w, h, count)
        self.rng = random.Random(seed)
        self.quiet, self.demo = quiet, demo
        self.nb = nb_of(w, h)
        self.fen = None
        self.opened = bytearray(self.n)
        self.flag = bytearray(self.n)
        self.rev_t = [0.0] * self.n            # when each cell opened (for the animation)
        self.cx, self.cy = w // 2, h // 2
        self.history = []
        self.time = self.penalty = 0.0
        self.clock = 0.0
        self.lost = None                        # the bog-eye that swallowed the pole
        self.won = False
        self.end_t = 0.0
        self.hint = None
        self.hint_t = 0.0
        self.wrong = ()
        self.wrong_t = -9.0
        self.msg, self.msg_t = "", 0.0
        self.parts = []
        self.paused = self.help = False
        self.recorded = False
        self.new_best = False
        self.helped = 0
        self.tries = 0

    def snd(self, name, vol=1.0):
        if not self.quiet:
            SND.play(name, vol)

    @property
    def total(self):
        return self.time + self.penalty

    @property
    def over(self):
        return self.won or self.lost is not None

    def say(self, text):
        self.msg, self.msg_t = text, self.clock

    def number(self, i):
        return self.fen.num[i] if self.fen else 0

    # --- actions ------------------------------------------------------------------------------
    def probe(self, i=None):
        i = self.cy * self.w + self.cx if i is None else i
        if self.over or self.flag[i]:
            return False
        if self.fen is None:
            self.fen, self.tries = lay_fen(self.w, self.h, self.count, i, self.rng, budget=6.0)
        if self.opened[i]:
            return self.chord(i)
        self.hint = None
        cells = self.flood([i])
        self.history.append(("open", cells))
        if self.fen.eye[i]:
            self.lose(i)
        else:
            self.snd("splash" if len(cells) > 6 else "probe")
            self.check_won()
        return True

    def flood(self, starts):
        """Open cells; zeros open their neighbours. Returns the cells opened, in order."""
        fen = self.fen
        out = []
        seen = set()
        q = [(s, 0) for s in starts]
        k = 0
        while k < len(q):
            c, d = q[k]
            k += 1
            if c in seen or self.opened[c] or self.flag[c]:
                continue
            seen.add(c)
            self.opened[c] = 1
            self.rev_t[c] = self.clock + d * 0.03
            out.append(c)
            if not fen.eye[c] and fen.num[c] == 0:
                for j in self.nb[c]:
                    if not self.opened[j] and j not in seen:
                        q.append((j, d + 1))
        return out

    def chord(self, i):
        if not self.opened[i] or self.fen.eye[i]:
            return False
        v = self.fen.num[i]
        nb = self.nb[i]
        if v == 0 or sum(self.flag[j] for j in nb) != v:
            return False
        todo = [j for j in nb if not self.opened[j] and not self.flag[j]]
        if not todo:
            return False
        self.hint = None
        cells = self.flood(todo)
        self.history.append(("open", cells))
        hit = [j for j in todo if self.fen.eye[j]]
        if hit:
            self.lose(hit[0])
        else:
            self.snd("chord")
            self.check_won()
        return True

    def toggle_flag(self, i=None):
        i = self.cy * self.w + self.cx if i is None else i
        if self.over or self.opened[i] or self.fen is None:
            return False
        self.flag[i] ^= 1
        self.history.append(("flag", i))
        self.snd("flag" if self.flag[i] else "unflag")
        if self.hint and i in self.hint.mines:
            self.hint = None
        return True

    def lose(self, i):
        self.lost = i
        self.end_t = self.clock
        self.snd("gulp")
        self.say("The ground gave way! U undo (+%d s)   N new fen" % RESCUE_COST if not self.demo else
                 "The ground gave way!")
        x, y = i % self.w, i // self.w
        for k in range(26):
            a = self.rng.random() * 6.283
            sp = 1.0 + self.rng.random() * 2.5
            self.parts.append([x + 0.5, y + 0.5, math.cos(a) * sp, math.sin(a) * sp - 1.5, 0.0,
                               0.6 + self.rng.random() * 0.6, (60, 90, 60) if k % 3 else (140, 200, 120)])

    def check_won(self):
        if sum(self.opened) == self.n - self.count:
            self.won = True
            self.end_t = self.clock
            for i in range(self.n):
                if self.fen.eye[i] and not self.flag[i]:
                    self.flag[i] = 1
            self.snd("won")
            self.say("The fen is sounded in %s!%s" % (fmt_time(self.total), "" if self.demo else
                                                     "   Enter: another fen   Esc: menu"))
            for k in range(40):
                self.parts.append([self.rng.random() * self.w, self.h * (0.4 + self.rng.random() * 0.6),
                                   (self.rng.random() - 0.5) * 0.6, -0.6 - self.rng.random() * 1.2, 0.0,
                                   1.6 + self.rng.random() * 1.8, (250, 230, 120)])

    def undo(self):
        if not self.history or self.won:
            return False
        op = self.history.pop()
        if op[0] == "open":
            for c in op[1]:
                self.opened[c] = 0
            if self.lost is not None:
                self.lost = None
                self.penalty += RESCUE_COST
                self.say("Pulled back out of the bog (+%d s)." % RESCUE_COST)
        else:
            self.flag[op[1]] ^= 1
        self.hint = None
        self.snd("undo")
        return True

    # --- the solver helps ------------------------------------------------------------------------
    def view_logic(self):
        lg = Logic(self.w, self.h, self.count)
        if self.fen:
            for i in range(self.n):
                if self.opened[i] and not self.fen.eye[i]:
                    lg.open(i, self.fen.num[i])
        return lg

    def next_step(self):
        """The next deduction that tells the player something new, from the open numbers only."""
        lg = self.view_logic()
        for _ in range(self.n):
            steps = lg.find(first=True)
            if not steps:
                return None
            for s in steps:
                if any(not self.opened[j] for j in s.safe) or any(not self.flag[j] for j in s.mines):
                    return s
            for s in steps:
                for j in s.mines:
                    lg.mine[j] = 1
                for j in s.safe:
                    lg.safe[j] = 1
        return None

    def ask_hint(self):
        if self.over:
            return False
        if self.fen is None:
            self.say("Probe anywhere: the first probe is always safe ground.")
            return True
        bad = [i for i in range(self.n) if self.flag[i] and not self.fen.eye[i]]
        s = self.next_step()
        self.penalty += HINT_COST
        self.helped += 1
        self.snd("hint")
        if s is None:
            self.say("No sure move found." + (" A flag stands on safe ground (C checks)." if bad else ""))
            return True
        self.hint, self.hint_t = s, self.clock
        extra = ""
        if any(self.flag[j] for j in s.safe):
            extra = "  (A flag there is wrong.)"
        self.say("Hint (+%d s): %s%s" % (HINT_COST, s.text, extra))
        return True

    def check(self):
        if self.over or self.fen is None:
            return False
        self.wrong = tuple(i for i in range(self.n) if self.flag[i] and not self.fen.eye[i])
        self.wrong_t = self.clock
        self.penalty += CHECK_COST
        self.snd("wrong" if self.wrong else "check")
        self.say(("Checked (+%d s): %s on safe ground." % (CHECK_COST, plural(len(self.wrong), "flag stands",
                                                                              "flags stand"))) if self.wrong else
                 "Checked (+%d s): every flag is right so far." % CHECK_COST)
        return True

    def flags_left(self):
        return self.count - sum(self.flag)

    def move(self, dx, dy):
        self.cx = clamp(self.cx + dx, 0, self.w - 1)
        self.cy = clamp(self.cy + dy, 0, self.h - 1)

    def update(self, dt):
        self.clock += dt
        if self.fen is not None and not self.over and not self.paused:
            self.time += dt
        alive = []
        for p in self.parts:
            p[4] += dt
            if p[4] < p[5]:
                p[0] += p[2] * dt
                p[1] += p[3] * dt
                if self.lost is not None:
                    p[3] += 4.0 * dt
                alive.append(p)
        self.parts = alive


# =============================================================================================
# A leadlight pane in play
# =============================================================================================
class Glaze:
    kind = "pane"

    def __init__(self, pane, key, quiet=False, demo=False, index=None):
        self.pane, self.key, self.index = pane, key, index
        self.w, self.h = pane.w, pane.h
        self.quiet, self.demo = quiet, demo
        self.grid = [[UNK] * self.w for _ in range(self.h)]
        self.cx, self.cy = 0, 0
        self.history = []
        self.stroke = None            # (target, set?, cells changed) while a key is held
        self.time = self.penalty = 0.0
        self.clock = 0.0
        self.started = False
        self.solved = False
        self.end_t = 0.0
        self.hint = None              # (kind, index, {(x, y): value})
        self.hint_t = 0.0
        self.wrong = ()
        self.wrong_t = -9.0
        self.msg, self.msg_t = "", 0.0
        self.paused = self.help = False
        self.recorded = False
        self.new_best = False
        self.helped = 0
        self.flash = {}               # (x, y) -> time set (the little pop)
        self.line_done = {}           # lines whose clues just came true -> time

    def snd(self, name, vol=1.0):
        if not self.quiet:
            SND.play(name, vol)

    @property
    def total(self):
        return self.time + self.penalty

    @property
    def over(self):
        return self.solved

    def say(self, text):
        self.msg, self.msg_t = text, self.clock

    # --- strokes: one key press (and the drag while it is held) is one undo step --------------------------
    def begin(self, target):
        if self.solved:
            return False
        self.end_stroke()
        cur = self.grid[self.cy][self.cx]
        self.stroke = [target, cur != target, []]
        self.started = True
        self.paint(first=True)
        return True

    def paint(self, first=False):
        if not self.stroke or self.solved:
            return
        target, setting, changed = self.stroke
        x, y = self.cx, self.cy
        cur = self.grid[y][x]
        if setting:
            if cur == target or (cur != UNK and not first):
                return
            new = target
        else:
            if cur != target:
                return
            new = UNK
        changed.append((x, y, cur))
        self.grid[y][x] = new
        self.flash[(x, y)] = self.clock
        self.hint = None if self.hint and (x, y) in self.hint[2] and self.hint[2][(x, y)] == new else self.hint
        self.snd("glass" if new == GLASS else "lead" if new == LEAD else "clear")
        self.after_change(x, y)

    def end_stroke(self):
        if self.stroke and self.stroke[2]:
            self.history.append(self.stroke[2])
        self.stroke = None

    def after_change(self, x, y):
        for kind, i in (("row", y), ("col", x)):
            line = [self.grid[i][k] == GLASS for k in range(self.w)] if kind == "row" else \
                [self.grid[k][i] == GLASS for k in range(self.h)]
            clues = self.pane.rclues[i] if kind == "row" else self.pane.cclues[i]
            if clues_of(line) == clues:
                if (kind, i) not in self.line_done:
                    self.line_done[(kind, i)] = self.clock
            else:
                self.line_done.pop((kind, i), None)
        sol = self.pane.sol
        if all((self.grid[yy][xx] == GLASS) == sol[yy][xx] for yy in range(self.h) for xx in range(self.w)):
            self.solve_done()

    def solve_done(self):
        self.end_stroke()
        self.solved = True
        self.end_t = self.clock
        for y in range(self.h):
            for x in range(self.w):
                if self.grid[y][x] == UNK:
                    self.grid[y][x] = LEAD
        self.hint = None
        self.snd("solved")
        self.say("%s is mended in %s!" % (self.pane.name, fmt_time(self.total)))

    def undo(self):
        self.end_stroke()
        if not self.history or self.solved:
            return False
        for x, y, old in reversed(self.history.pop()):
            self.grid[y][x] = old
            self.after_change(x, y)
        self.hint = None
        self.snd("undo")
        return True

    def restart(self):
        self.end_stroke()
        changed = [(x, y, self.grid[y][x]) for y in range(self.h) for x in range(self.w) if self.grid[y][x] != UNK]
        if changed and not self.solved:
            for x, y, _ in changed:
                self.grid[y][x] = UNK
            self.history.append(changed)
            self.line_done.clear()
            self.hint = None
            self.snd("undo")

    def move(self, dx, dy):
        self.cx = clamp(self.cx + dx, 0, self.w - 1)
        self.cy = clamp(self.cy + dy, 0, self.h - 1)
        self.paint()

    # --- the solver helps ----------------------------------------------------------------------------
    def next_step(self, grid=None):
        """The next line deduction from the clues and the cells set so far: (kind, index, before, after), or
        (kind, index, line, None) when a line cannot be completed any more, or None."""
        for st in pane_steps(self.pane.rclues, self.pane.cclues, self.grid if grid is None else grid):
            return st
        return None

    def ask_hint(self):
        if self.solved:
            return False
        self.end_stroke()
        st = self.next_step()
        self.penalty += HINT_COST
        self.helped += 1
        self.snd("hint")
        if st is None:
            self.say("No line can say more - a cell set somewhere is wrong (C checks).")
            return True
        kind, i, before, after = st
        clues = self.pane.rclues[i] if kind == "row" else self.pane.cclues[i]
        if after is None:
            cells = {((k, i) if kind == "row" else (i, k)): -1 for k in range(len(before))}
            self.hint, self.hint_t = (kind, i, cells), self.clock
            self.say("Hint (+%d s): %s cannot be completed with the cells set - something there is wrong." % (
                HINT_COST, line_text(kind, i, clues)))
            return True
        cells = {}
        for k, (a, b) in enumerate(zip(before, after)):
            if a != b:
                cells[(k, i) if kind == "row" else (i, k)] = b
        self.hint, self.hint_t = (kind, i, cells), self.clock
        self.say("Hint (+%d s): %s" % (HINT_COST, explain_line(kind, i, clues, before, after)))
        return True

    def check(self):
        if self.solved:
            return False
        self.end_stroke()
        sol = self.pane.sol
        self.wrong = tuple((x, y) for y in range(self.h) for x in range(self.w)
                           if (self.grid[y][x] == GLASS and not sol[y][x]) or (self.grid[y][x] == LEAD and sol[y][x]))
        self.wrong_t = self.clock
        self.penalty += CHECK_COST
        self.snd("wrong" if self.wrong else "check")
        self.say(("Checked (+%d s): %s wrong." % (CHECK_COST, plural(len(self.wrong), "cell is", "cells are")))
                 if self.wrong else "Checked (+%d s): no mistakes so far." % CHECK_COST)
        return True

    def apply(self, cells):
        """Set cells (the solver in auto mode): one undo step."""
        changed = []
        for (x, y), v in cells.items():
            if self.grid[y][x] != v:
                changed.append((x, y, self.grid[y][x]))
                self.grid[y][x] = v
                self.flash[(x, y)] = self.clock + 0.02 * len(changed)
        if changed:
            self.started = True
            self.history.append(changed)
            for x, y, _ in changed:
                if not self.solved:
                    self.after_change(x, y)

    def progress(self):
        return sum(1 for r in self.grid for c in r if c != UNK) / float(self.w * self.h)

    def update(self, dt):
        self.clock += dt
        if self.started and not self.solved and not self.paused:
            self.time += dt


# =============================================================================================
# Drawing helpers
# =============================================================================================
WHITE = (255, 255, 255)
HUD_BG = (14, 18, 24)
HUD_FG = (214, 218, 228)
HUD_DIM = (140, 150, 170)
GOLD = (250, 214, 120)
INK = (12, 14, 20)
CURSOR = (255, 226, 120)
HINT_SRC = (110, 200, 255)
HINT_SAFE = (130, 250, 150)
HINT_MINE = (255, 110, 90)
WRONG = (255, 70, 60)


def hsh(x, y, s=0):
    h = (x * 374761393 + y * 668265263 + s * 2147483647) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    return (h ^ (h >> 16)) & 0xFFFF


def blend(cv, x, y, c, a):
    if 0 <= x < cv.W and 0 <= y < cv.H:
        row = cv.px[y]
        row[x] = mix(row[x], c, a)


def tint(cv, x, y, w, h, c, a):
    for yy in range(max(0, y), min(cv.H, y + h)):
        row = cv.px[yy]
        for xx in range(max(0, x), min(cv.W, x + w)):
            o = row[xx]
            row[xx] = (int(o[0] + (c[0] - o[0]) * a), int(o[1] + (c[1] - o[1]) * a), int(o[2] + (c[2] - o[2]) * a))


def ring(cv, x, y, w, h, c, th=1, a=1.0):
    """A frame th pixels thick (blended when a < 1)."""
    for k in range(th):
        if w - 2 * k <= 0 or h - 2 * k <= 0:
            return
        if a >= 1:
            cv.frame(x + k, y + k, w - 2 * k, h - 2 * k, c)
        else:
            tint(cv, x + k, y + k, w - 2 * k, 1, c, a)
            tint(cv, x + k, y + h - 1 - k, w - 2 * k, 1, c, a)
            tint(cv, x + k, y + k + 1, 1, h - 2 * k - 2, c, a)
            tint(cv, x + w - 1 - k, y + k + 1, 1, h - 2 * k - 2, c, a)


def glow(cv, cx, cy, r0, r1, c, k=0.55):
    W, H = cv.W, cv.H
    y0, y1 = max(0, int(cy - r1)), min(H - 1, int(cy + r1))
    x0, x1 = max(0, int(cx - r1)), min(W - 1, int(cx + r1))
    span = max(0.01, r1 - r0)
    r1s = r1 * r1
    for py in range(y0, y1 + 1):
        row = cv.px[py]
        dy = py + 0.5 - cy
        dy2 = dy * dy
        for px in range(x0, x1 + 1):
            dx = px + 0.5 - cx
            d2 = dx * dx + dy2
            if d2 < r1s:
                d = math.sqrt(d2)
                a = 1.0 if d <= r0 else 1 - (d - r0) / span
                a = a * a * k
                o = row[px]
                row[px] = (int(o[0] + (c[0] - o[0]) * a), int(o[1] + (c[1] - o[1]) * a), int(o[2] + (c[2] - o[2]) * a))


def blit(cv, img, x0, y0):
    """A tile (rows of colours, None = keep) at a pixel position."""
    H, W = cv.H, cv.W
    for r, row in enumerate(img):
        y = y0 + r
        if not 0 <= y < H:
            continue
        line = cv.px[y]
        if None in row:
            for c, v in enumerate(row):
                if v is not None and 0 <= x0 + c < W:
                    line[x0 + c] = v
        else:
            a, b = max(0, x0), min(W, x0 + len(row))
            if b > a:
                line[a:b] = row[a - x0:b - x0]


def bevel_tile(T, base, hi, lo, b=1, spec=None):
    """A raised square: light top / left, dark bottom / right."""
    img = [[base] * T for _ in range(T)]
    for y in range(T):
        for x in range(T):
            if y < b or x < b:
                img[y][x] = hi if not (y >= T - b or x >= T - b) or (y < b and x < b) else base
            if y >= T - b or x >= T - b:
                img[y][x] = lo if not (y < b and x < T - b and y < T - b) or y >= T - b else img[y][x]
    if spec:
        img[b][b] = spec
    return img


def put_clipped(cv, col, row, s, fg, bg=None):
    if 0 <= row < cv.rows:
        cv.put(col, row, s[:max(0, cv.cols - col)], fg, bg)


def wrap(text, width):
    out, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = word
        else:
            line = (line + " " + word).strip()
    if line:
        out.append(line)
    return out


def fit_board(cw, ch, cols, rows, top, bottom, glyph_min):
    """(T, ox, oy): the cell size in pixels and the top-left pixel of a board of cw x ch cells. Below glyph_min
    pixels numbers are text, so cells keep an even size and their middle pixel rows on a text row."""
    aw = cols - 2
    ah = (rows - top - bottom) * 2 - 2
    T = max(1, min(aw // cw, ah // ch))
    if 2 <= T < glyph_min:
        T -= T % 2
    ox = (cols - T * cw) // 2
    oy = top * 2 + max(0, ((rows - top - bottom) * 2 - T * ch) // 2)
    if 2 <= T < glyph_min:
        want = 1 if T % 4 == 0 else 0          # the middle two pixel rows of a cell start on an even row
        if oy % 2 != want:
            oy = oy - 1 if oy - 1 >= top * 2 else oy + 1
    return T, ox, oy


def text_row(y0, T):
    """The text row that sits on the middle of a cell starting at pixel row y0 (text-number sizes)."""
    return (y0 + T // 2 - 1) // 2


# =============================================================================================
# The fen at night (behind the sounding board)
# =============================================================================================
_BG = {}


def fen_backdrop(cols, rows):
    key = ("fen", cols, rows)
    bg = _BG.get(key)
    if bg is not None:
        return bg
    W, H = cols, rows * 2
    top, mid, low = (10, 14, 34), (22, 36, 58), (30, 54, 58)
    px = []
    for y in range(H):
        t = y / max(1, H - 1)
        c = mix(top, mid, t / 0.6) if t < 0.6 else mix(mid, low, (t - 0.6) / 0.4)
        px.append([c] * W)
    rnd = random.Random(11)
    for _ in range(W * H // 90):
        x, y = rnd.randrange(W), rnd.randrange(int(H * 0.55))
        px[y][x] = mix(px[y][x], (220, 226, 255), 0.3 + rnd.random() * 0.5)
    # moon with a soft halo
    mx, my, mr = W * 0.84, H * 0.16, max(2.0, H * 0.06)
    for y in range(max(0, int(my - mr * 4)), min(H, int(my + mr * 4))):
        for x in range(max(0, int(mx - mr * 4)), min(W, int(mx + mr * 4))):
            d = math.hypot(x + 0.5 - mx, (y + 0.5 - my))
            if d < mr:
                k = 1 - 0.25 * max(0.0, (x - mx + y - my) / mr)
                px[y][x] = shade((236, 232, 200), k)
            elif d < mr * 4:
                a = (1 - (d - mr) / (mr * 3)) ** 2 * 0.25
                px[y][x] = mix(px[y][x], (200, 210, 220), a)
    # mist bands and a far tree line
    for x in range(W):
        hz = int(H * 0.68 + 2 * math.sin(x * 0.07) + 1.5 * math.sin(x * 0.23 + 1))
        for y in range(hz, H):
            px[y][x] = mix(px[y][x], (14, 26, 28), 0.7)
        for y in range(max(0, hz - 3), hz):
            px[y][x] = mix(px[y][x], (110, 140, 150), 0.18)
    # reeds along the bottom
    for x in range(W):
        if hsh(x, 3) % 3 == 0:
            hgt = 3 + hsh(x, 7) % max(3, H // 6)
            c = (12 + hsh(x, 9) % 10, 30 + hsh(x, 9) % 16, 24)
            for y in range(H - hgt, H):
                px[y][x] = c
            if hsh(x, 5) % 4 == 0 and H - hgt - 2 >= 0:
                px[H - hgt - 1][x] = (60, 40, 26)
                px[H - hgt - 2][x] = (60, 40, 26)
    _BG[key] = px
    return px


def wall_backdrop(cols, rows):
    """The inside of the pump-house: brick in candle light."""
    key = ("wall", cols, rows)
    bg = _BG.get(key)
    if bg is not None:
        return bg
    W, H = cols, rows * 2
    px = []
    cx, cy = W / 2, H * 0.45
    for y in range(H):
        row = []
        for x in range(W):
            d = math.hypot((x - cx) / max(1, W), (y - cy) / max(1, H))
            k = clamp(1.25 - d * 1.6, 0.35, 1.0)
            bh = 3 if H < 60 else 4
            bw = 8 if W < 160 else 10
            off = (y // bh) % 2 * (bw // 2)
            mortar = y % bh == 0 or (x + off) % bw == 0
            base = (40, 28, 30) if not mortar else (24, 18, 22)
            v = hsh(x // bw, y // bh, 4) % 9
            base = (base[0] + v, base[1] + v // 2, base[2] + v // 3)
            row.append(shade(base, k))
        px.append(row)
    _BG[key] = px
    return px


# =============================================================================================
# The sounding board: tussocks, open peat, flags and bog-eyes
# =============================================================================================
MOSS = ((72, 128, 74), (78, 136, 76), (68, 122, 72), (82, 140, 84))
PEAT = ((44, 42, 36), (46, 44, 38), (42, 40, 35), (47, 45, 40))
NUMCOL = {1: (120, 186, 255), 2: (128, 224, 120), 3: (255, 172, 86), 4: (206, 146, 255), 5: (255, 110, 110),
          6: (108, 230, 228), 7: (244, 240, 232), 8: (176, 176, 196)}
FLAG_SMALL = [".pRr..", ".pRrrr", ".pRr..", ".p....", ".p....", "gpg..."]
FLAG_ART = ["..pRrr..", "..pRrrrr", "..pRrrr.", "..pRr...", "..p.....", "..p.....", ".gpg....", "gg.gg..."]
FLAG_COL = {"p": (214, 186, 130), "R": (180, 50, 40), "r": (240, 96, 60), "g": (120, 190, 90)}
_TILE = {}


def tile(kind, T, v=0):
    key = (kind, T, v)
    img = _TILE.get(key)
    if img is not None:
        return img
    if kind == "moss":
        base = MOSS[v]
        hi, lo = mix(base, (190, 230, 160), 0.35), shade(base, 0.55)
        if T == 1:
            img = [[base]]
        elif T == 2:
            img = [[hi, base], [base, lo]]
        else:
            b = max(1, T // 7)
            img = bevel_tile(T, base, hi, lo, b)
            if T >= 8:
                for k in range(T * T // 14):
                    h = hsh(k, v, T)
                    x, y = b + h % max(1, T - 2 * b), b + (h >> 6) % max(1, T - 2 * b)
                    img[y][x] = mix(base, (30, 60, 30) if h & 1 else (150, 200, 120), 0.35)
                for k in range(3):                       # grass blades
                    bx = b + 1 + (hsh(k, v, 7) % max(1, T - 2 * b - 2))
                    ln = max(2, T // 4)
                    for yy in range(T - b - ln, T - b):
                        img[yy][bx] = mix(base, (170, 220, 120), 0.5)
    elif kind == "peat":
        base = PEAT[v]
        lo, hi = shade(base, 0.72), mix(base, (90, 96, 86), 0.22)
        if T == 1:
            img = [[base]]
        elif T == 2:
            img = [[lo, base], [base, base]]
        else:
            img = [[base] * T for _ in range(T)]
            for k in range(T):
                img[0][k] = lo
                img[k][0] = lo
            for k in range(1, T):
                img[T - 1][k] = hi
                img[k][T - 1] = hi
            if T >= 8:
                for k in range(T // 3):                    # a faint ripple
                    x = T // 4 + k
                    y = T * 2 // 3 + int(1.2 * math.sin(k * 0.9 + v))
                    if 0 < y < T - 1 and 0 < x < T - 1:
                        img[y][x] = mix(base, (80, 96, 96), 0.4)
    elif kind == "flag":
        s = max(2, T - 2 * max(1, T // 8)) if T >= 8 else T
        src = FLAG_ART if T >= 10 else FLAG_SMALL
        art = scale_art([[FLAG_COL.get(c) for c in r] for r in src], s, s)
        m = (T - s) // 2
        img = [[None] * T for _ in range(T)]
        for y in range(s):
            for x in range(s):
                img[m + y][m + x] = art[y][x]
    elif kind == "eye":
        base = PEAT[v]
        img = [[base] * T for _ in range(T)]
        c = (T - 1) / 2.0
        r = T * 0.42
        for y in range(T):
            for x in range(T):
                d = math.hypot(x - c, (y - c) * 1.1)
                if d < r * 0.62:
                    img[y][x] = (8, 12, 10)
                elif d < r:
                    img[y][x] = mix((20, 34, 26), (52, 74, 50), (d - r * 0.62) / (r * 0.38))
        g = int(c - r * 0.3)
        if 0 <= g < T:
            img[g][g] = (150, 230, 150)
    _TILE[key] = img
    return img


WARDEN_ART = [
    "....kkkk.....", "...kkkkkk....", ".kkkkkkkkkk..", "....ffff.....", "....fkfk.....", "....ffff.....",
    ".....ff....p.", "...GGGGGG..p.", "..GGGGGGGG.p.", ".GGGGGGGGGfp.", ".fGGGGGGGG.p.", ".kGGGGGGG..p.",
    "kyk.GGGGG..p.", "yoy.GGGGG..p.", "kyk.GG.GG..p.", "....nn.nn..p.", "...nnn.nnn.p."]
WARDEN_COL = {"k": (48, 40, 44), "f": (236, 196, 152), "G": (64, 112, 74), "n": (96, 66, 44), "p": (190, 160, 110),
              "y": (255, 214, 110), "o": (255, 246, 200)}
_ART = {}


def draw_warden(cv, x0, y1, hgt, t):
    """Odile with her lamp and ash pole, standing with her feet at pixel row y1."""
    wd = max(3, int(hgt * len(WARDEN_ART[0]) / len(WARDEN_ART) + 0.5))
    key = (wd, hgt)
    art = _ART.get(key)
    if art is None:
        art = scale_art([[WARDEN_COL.get(c) for c in r] for r in WARDEN_ART], wd, hgt)
        _ART[key] = art
    y0 = y1 - hgt
    ly = y0 + hgt * 13.5 / len(WARDEN_ART)
    lx = x0 + wd * 1.5 / len(WARDEN_ART[0])
    glow(cv, lx, ly, 0, hgt * 0.45, (255, 200, 110), 0.16 + 0.03 * math.sin(t * 3))
    blit(cv, art, x0, y0)


def sweep_layout(g, cols, rows, hud=True, auto=False):
    """(T, ox, oy, msg row or None)."""
    if not hud:
        T, ox, oy = fit_board(g.w + 1, g.h + 1, cols, rows, 0, 0, 6)
        return T, ox + T // 2, oy + T // 2, None
    for bottom in (2, 1):
        T, ox, oy = fit_board(g.w, g.h, cols, rows, 1, bottom, 6)
        if bottom == 1 or T >= fit_board(g.w, g.h, cols, rows, 1, 1, 6)[0]:
            break
    return T, ox, oy, (rows - 2 if bottom == 2 else None)


def render_sweep(g, cols, rows, hud=True, auto=None):
    cv = Canvas(cols, 1)
    cv.rows, cv.H = rows, rows * 2
    cv.px = [r[:] for r in fen_backdrop(cols, rows)]
    T, ox, oy, msg_row = sweep_layout(g, cols, rows, hud, auto is not None)
    w, h = g.w, g.h
    t = g.clock
    fen = g.fen
    # the boardwalk round the fen
    fb = max(1, T // 4)
    plank = (96, 70, 46)
    cv.rect(ox - fb, oy - fb, w * T + 2 * fb, h * T + 2 * fb, plank)
    if fb >= 2:
        cv.rect(ox - fb, oy - fb, w * T + 2 * fb, 1, (140, 106, 70))
        cv.rect(ox - fb, oy + h * T + fb - 1, w * T + 2 * fb, 1, (60, 42, 28))
        for k in range(0, w * T + 2 * fb, max(4, T * 2)):
            cv.rect(ox - fb + k, oy - fb, 1, fb, (70, 50, 32))
            cv.rect(ox - fb + k, oy + h * T, 1, fb, (70, 50, 32))
    hgt = min(h * T + 2 * fb, int(rows * 2 * 0.42), int((ox - fb - 3) * len(WARDEN_ART) / len(WARDEN_ART[0])))
    wwd = int(hgt * len(WARDEN_ART[0]) / len(WARDEN_ART) + 0.5)
    if hud and hgt >= 17 and ox - fb - wwd - 2 >= 0:
        draw_warden(cv, ox - fb - wwd - 2, oy + h * T + fb, hgt, t)
    glyph_mode = T >= 6
    texts = []
    glyphs = []
    lost = g.lost
    lx, ly = (lost % w, lost // w) if lost is not None else (0, 0)
    for y in range(h):
        Y = oy + y * T
        for x in range(w):
            i = y * w + x
            X = ox + x * T
            v = hsh(x, y) & 3
            if g.opened[i]:
                p = (t - g.rev_t[i]) / 0.2
                if p < 0:
                    blit(cv, tile("moss", T, v), X, Y)
                    continue
                if fen.eye[i]:
                    blit(cv, tile("eye", T, v), X, Y)
                    if T >= 2:
                        tint(cv, X, Y, T, T, (200, 40, 30), 0.35 + 0.15 * math.sin(t * 8))
                    continue
                blit(cv, tile("peat", T, v), X, Y)
                if p < 1:
                    ins = int(p * T / 2)
                    c = mix(MOSS[v], PEAT[v], p)
                    cv.rect(X + ins, Y + ins, T - 2 * ins, T - 2 * ins, c)
                    if p < 0.6:
                        continue
                n = fen.num[i]
                if n:
                    if glyph_mode:
                        glyphs.append((X, Y, n, v))
                    elif T >= 2:
                        texts.append((X + (T - 1) // 2, text_row(Y, T), str(n), NUMCOL[n]))
                    else:
                        cv.px[Y][X] = mix(PEAT[v], NUMCOL[n], 0.5)
            else:
                show_eye = lost is not None and fen.eye[i] and not g.flag[i]
                if show_eye:
                    delay = math.hypot(x - lx, y - ly) * 0.04
                    if t - g.end_t > delay:
                        blit(cv, tile("eye", T, v), X, Y)
                        continue
                blit(cv, tile("moss", T, v), X, Y)
                if g.flag[i]:
                    if T >= 6:
                        blit(cv, tile("flag", T), X, Y)
                    elif T >= 2:
                        texts.append((X + (T - 1) // 2, text_row(Y, T), "▲", (255, 110, 70)))
                    else:
                        cv.px[Y][X] = (240, 96, 60)
                    if lost is not None and not fen.eye[i]:
                        if T >= 4:
                            for k in range(T):
                                blend(cv, X + k, Y + k, WRONG, 0.9)
                                blend(cv, X + T - 1 - k, Y + k, WRONG, 0.9)
                        else:
                            texts[-1] = (texts[-1][0], texts[-1][1], "×", WRONG) if texts else None
    # the warden's lamp: the cursor
    if hud and not g.won:
        X, Y = ox + g.cx * T, oy + g.cy * T
        pul = 0.5 + 0.5 * math.sin(t * 5)
        c = mix(CURSOR, WHITE, 0.35 * pul)
        if T >= 4:
            if T >= 8:
                glow(cv, X + T / 2, Y + T / 2, T * 0.5, T * 1.4, (255, 210, 120), 0.18)
            ring(cv, X - 1, Y - 1, T + 2, T + 2, shade(c, 0.5)) if T >= 8 else None
            ring(cv, X, Y, T, T, c, max(1, T // 9))
        else:
            tint(cv, X, Y, T, T, c, 0.55 + 0.15 * pul)
    # hint highlight
    if g.hint is not None and not g.over:
        s = g.hint
        a = 0.45 + 0.25 * math.sin((t - g.hint_t) * 6)
        th = max(1, T // 8)
        for cells, col in ((s.src, HINT_SRC), (s.safe, HINT_SAFE), (s.mines, HINT_MINE)):
            for i in cells:
                X, Y = ox + (i % w) * T, oy + (i // w) * T
                if T >= 10:
                    ring(cv, X, Y, T, T, col, th, min(1.0, a + 0.3))
                    tint(cv, X + th, Y + th, T - 2 * th, T - 2 * th, col, a * 0.3)
                elif T >= 4:
                    if cells is s.src:
                        tint(cv, X, Y, T, T, col, 0.25 + a * 0.3)
                    else:
                        ring(cv, X, Y, T, T, col, 1, min(1.0, a + 0.35))
                        tint(cv, X + 1, Y + 1, T - 2, T - 2, col, a * 0.3)
                else:
                    tint(cv, X, Y, T, T, col, a * (0.6 if cells is s.src else 1.0))
    # wrong flags after a check
    if g.wrong and t - g.wrong_t < 3.0 and int((t - g.wrong_t) * 4) % 2 == 0:
        for i in g.wrong:
            X, Y = ox + (i % w) * T, oy + (i // w) * T
            ring(cv, X, Y, T, T, WRONG, max(1, T // 6)) if T >= 4 else tint(cv, X, Y, T, T, WRONG, 0.7)
    for X, Y, n, v in glyphs:
        gh = 5 if T < 9 else max(5, int(T * 0.62))
        draw_digits(cv, str(n), X + T / 2.0, Y + T / 2.0, gh, NUMCOL[n], shade(PEAT[v], 0.4))
    # particles
    psz = max(1, T // 6)
    for p in g.parts:
        k = 1 - p[4] / p[5]
        X, Y = int(ox + p[0] * T), int(oy + p[1] * T)
        for yy in range(Y, Y + psz):
            for xx in range(X, X + psz):
                blend(cv, xx, yy, p[6], 0.25 + 0.7 * k * (0.6 + 0.4 * math.sin(p[4] * 9 + p[0])))
    for tx in texts:
        if tx:
            put_clipped(cv, tx[0], tx[1], tx[2], tx[3])
    if hud:
        draw_hud_sweep(cv, g, msg_row, auto, (oy + h * T + fb + 1) // 2 + 1)
    return cv


def hud_bar(cv, row, left, accent, bits):
    cols = cv.cols
    cv.put(0, row, " " * cols, HUD_FG, HUD_BG)
    cv.put(0, row, left[:cols], INK, accent)
    n = sum(len(s) for s, _ in bits)
    while bits and n + len(left) + 2 > cols:
        bits = bits[2:]
        n = sum(len(s) for s, _ in bits)
    x = cols - n - 1
    for s, c in bits:
        cv.put(x, row, s, c, HUD_BG)
        x += len(s)


def draw_message(cv, g, msg_row, keys, auto=None, free=None):
    """The message (hints, results) in the rows under the board, the keys (or the amber auto banner) on the last
    row. free: the first text row below the board."""
    cols, rows = cv.cols, cv.rows
    msg = g.msg if g.msg and (g.clock - g.msg_t < 14 or g.hint is not None or g.over) else ""
    last = rows - 1
    if auto is not None:
        auto.banner(cv, row=last, extra=getattr(g, "label", ""))
    else:
        cv.put(0, last, " " * cols, HUD_FG, HUD_BG)
        k = keys
        while len(k) + 2 > cols and "   " in k:
            k = k[:k.rfind("   ")]
        put_clipped(cv, 1, last, k, HUD_DIM, HUD_BG)
    if not msg:
        if msg_row is not None:
            cv.put(0, msg_row, " " * cols, HUD_FG, HUD_BG)
        return
    lines = wrap(msg, cols - 2)
    if msg_row is None:
        r = 0 if auto is not None else last
        cv.put(0, r, " " * cols, HUD_FG, HUD_BG)
        put_clipped(cv, 1, r, msg[:cols - 2], (240, 236, 210), HUD_BG)
        return
    top = msg_row - len(lines) + 1
    if free is not None:
        top = max(top, min(free, msg_row))
    if top + len(lines) - 1 > msg_row and auto is None:
        lines = lines[:last - top + 1]           # the keys give way to a long message
        for j, ln in enumerate(lines):
            cv.put(0, top + j, " " * cols, HUD_FG, HUD_BG)
            put_clipped(cv, 1, top + j, ln, (240, 236, 210), HUD_BG)
        return
    lines = lines[:msg_row - top + 1]
    for j, ln in enumerate(lines):
        cv.put(0, top + j, " " * cols, HUD_FG, HUD_BG)
        put_clipped(cv, 1, top + j, ln, (240, 236, 210), HUD_BG)


SWEEP_KEYS = "arrows move   Space probe / chord   F flag   U undo   H hint   C check   N new   Esc menu   ? help"


def draw_hud_sweep(cv, g, msg_row, auto=None, free=None):
    acc = ACCENTS[NAME][1]
    best = None if g.demo else records().get(g.key)
    left = " BOG SOUNDING  %s %dx%d " % (g.key.upper() if not g.key.startswith("custom") else "CUSTOM", g.w, g.h)
    bits = [("eyes ", HUD_DIM), ("%d" % g.count, HUD_FG), ("  flags left ", HUD_DIM),
            ("%d" % g.flags_left(), GOLD if g.flags_left() >= 0 else WRONG), ("  time ", HUD_DIM),
            (fmt_time(g.total), GOLD)]
    if best is not None:
        bits += [("  best ", HUD_DIM), (fmt_time(best), HUD_FG)]
    hud_bar(cv, 0, left, acc, bits)
    draw_message(cv, g, msg_row, SWEEP_KEYS, auto, free)


# =============================================================================================
# The leadlight board: the ledger's clues, the pane and its colours
# =============================================================================================
PARCH = ((226, 210, 170), (212, 194, 152))
PARCH2 = ((232, 218, 180), (176, 154, 116))          # tiny cells: stronger stripes keep two-digit clues apart
INK_CLUE2, DONE_CLUE2 = (20, 12, 8), (124, 108, 80)
INK_CLUE = (58, 40, 30)
DONE_CLUE = (158, 146, 118)
SLATE = ((58, 62, 80), (52, 56, 74))
AMBER = (232, 182, 92)
LEADC = (26, 26, 32)


def pane_tile(kind, T, v=0, col=None):
    key = ("p", kind, T, v, col)
    img = _TILE.get(key)
    if img is not None:
        return img
    if kind == "unk":
        base = SLATE[v]
        if T <= 2:
            img = [[base] * T for _ in range(T)]
        else:
            img = bevel_tile(T, base, mix(base, (150, 160, 190), 0.25), shade(base, 0.7), 1)
            if T >= 8:
                for k in range(T // 3):
                    x, y = T - 2 - k - T // 4, 1 + k + T // 8
                    if 0 < x < T - 1 and 0 < y < T - 1:
                        img[y][x] = mix(base, (180, 190, 220), 0.18)
    elif kind == "glass":
        base = AMBER if col is None else col
        hi, lo = mix(base, WHITE, 0.45), shade(base, 0.62)
        if T == 1:
            img = [[base]]
        elif T == 2:
            img = [[hi, base], [base, base]]
        else:
            img = bevel_tile(T, base, hi, lo, max(1, T // 9))
            if T >= 6:                                   # a glint
                b = max(1, T // 9)
                for k in range(max(1, T // 4)):
                    if b + 1 + k < T - b:
                        img[b + 1][b + 1 + k] = mix(base, WHITE, 0.7)
                    if b + 1 + k < T - b:
                        img[b + 1 + k][b + 1] = mix(base, WHITE, 0.55)
    elif kind == "lead":
        base = shade(SLATE[v], 0.6)
        img = [[base] * T for _ in range(T)]
        if T >= 4:
            d = max(1, T // 5)
            m = (T - d) // 2
            for y in range(m, m + d):
                for x in range(m, m + d):
                    img[y][x] = (130, 134, 150)
    elif kind == "solid":                              # a solved pane's glass, lit from behind
        base = mix(col, WHITE, 0.08)
        hi, lo = mix(base, WHITE, 0.38), shade(base, 0.86)
        img = [[base] * T for _ in range(T)]
        if T >= 3:
            for y in range(T):
                for x in range(T):
                    f = (x + y) / (2.0 * T)
                    img[y][x] = mix(hi, lo, f) if T >= 6 else (base if f < 0.7 else lo)
            if T >= 6:
                img[1][1] = WHITE
    elif kind == "dark":
        img = [[LEADC] * T for _ in range(T)]
    _TILE[key] = img
    return img


def pane_layout(g, cols, rows, hud=True):
    """(T, ox, oy, rc, cc, msg row): rc / cc are the clue slots left of the rows and above the columns."""
    rc = max(1, max(len(c) for c in g.pane.rclues))
    cc = max(1, max(len(c) for c in g.pane.cclues))
    if not hud:
        T, ox, oy = fit_board(g.w + rc, g.h + cc, cols, rows, 0, 0, 6)
        return T, ox, oy, rc, cc, None
    for bottom in (2, 1):
        T, ox, oy = fit_board(g.w + rc, g.h + cc, cols, rows, 1, bottom, 6)
        if bottom == 1 or T >= fit_board(g.w + rc, g.h + cc, cols, rows, 1, 1, 6)[0]:
            break
    return T, ox, oy, rc, cc, (rows - 2 if bottom == 2 else None)


def clue_status(g, kind, i):
    line = [g.grid[i][k] for k in range(g.w)] if kind == "row" else [g.grid[k][i] for k in range(g.h)]
    return (kind, i) in g.line_done or all(c != UNK for c in line) and clues_of([c == GLASS for c in line]) == (
        g.pane.rclues[i] if kind == "row" else g.pane.cclues[i])


def render_pane(g, cols, rows, hud=True, auto=None):
    cv = Canvas(cols, 1)
    cv.rows, cv.H = rows, rows * 2
    cv.px = [r[:] for r in wall_backdrop(cols, rows)]
    T, ox, oy, rc, cc, msg_row = pane_layout(g, cols, rows, hud)
    w, h = g.w, g.h
    gx, gy = ox + rc * T, oy + cc * T
    t = g.clock
    pane = g.pane
    solved = g.solved
    st = t - g.end_t
    # the window frame (wood) and, once mended, the light behind it
    fb = max(1, T // 3)
    bw_, bh_ = (rc + w) * T + 2 * fb, (cc + h) * T + 2 * fb
    cv.rect(ox - fb, oy - fb, bw_, bh_, (92, 62, 40))
    if fb >= 2:
        cv.rect(ox - fb, oy - fb, bw_, 1, (140, 100, 64))
        cv.rect(ox - fb, oy - fb, 1, bh_, (120, 86, 56))
        cv.rect(ox - fb, oy + bh_ - fb - 1, bw_, 1, (54, 36, 24))
        cv.rect(ox + bw_ - fb - 1, oy - fb, 1, bh_, (64, 42, 28))
    if solved and T >= 4:
        a = min(1.0, st / 1.5)
        glow(cv, gx + w * T / 2, gy + h * T / 2, max(w, h) * T * 0.45, max(w, h) * T * 0.85, (255, 226, 160),
             0.25 * a)
    # the ledger: clue strips
    texts = []
    glyph_mode = T >= 6
    hl_kind = g.hint[0] if g.hint else None
    hl_i = g.hint[1] if g.hint else -1
    for kind in ("row", "col"):
        n = h if kind == "row" else w
        slots = rc if kind == "row" else cc
        for i in range(n):
            clues = pane.rclues[i] if kind == "row" else pane.cclues[i]
            show = clues if clues else [0]
            done = clue_status(g, kind, i) or solved
            cur = (kind == "row" and i == g.cy) or (kind == "col" and i == g.cx)
            hl = kind == hl_kind and i == hl_i
            for s in range(slots):
                if kind == "row":
                    X, Y = ox + s * T, gy + i * T
                else:
                    X, Y = gx + i * T, oy + s * T
                if T == 2:
                    base = PARCH2[(i + s) % 2]
                else:
                    base = PARCH[(i + s) % 2] if T <= 4 else PARCH[i % 2 if kind == "row" else (i + 1) % 2]
                if hud and cur and not solved:
                    base = mix(base, (255, 240, 170), 0.45)
                if hl:
                    base = mix(base, HINT_SRC, 0.4 + 0.15 * math.sin((t - g.hint_t) * 6))
                cv.rect(X, Y, T, T, base)
                if T >= 8:
                    cv.rect(X, Y + T - 1, T, 1, shade(base, 0.88)) if kind == "row" else \
                        cv.rect(X + T - 1, Y, 1, T, shade(base, 0.88))
                k = s - (slots - len(show))
                if k < 0:
                    continue
                num = str(show[k])
                col = DONE_CLUE if done else INK_CLUE
                if T == 2 and (i + s) % 2:
                    col = DONE_CLUE2 if done else INK_CLUE2
                if glyph_mode:
                    gh = max(5, int(T * 0.66))
                    while gh > 5 and glyph_w(num, gh) > T - 2:
                        gh -= 1
                    gap = 0 if glyph_w(num, gh) > T - 1 else None
                    draw_digits(cv, num, X + T / 2.0 + (0.5 if gap == 0 else 0), Y + T / 2.0, gh, col, gap=gap)
                elif T >= 2:
                    c0 = X + (T - len(num) if T == 2 else (T - len(num)) // 2)
                    texts.append((c0, text_row(Y, T), num, col))
                else:
                    cv.px[Y][X] = col
    # the corner: the pane's size
    cv.rect(ox, oy, rc * T, cc * T, (52, 38, 32))
    # cells
    for y in range(h):
        Y = gy + y * T
        for x in range(w):
            X = gx + x * T
            c = g.grid[y][x]
            v = ((x // 5) + (y // 5)) & 1 if T <= 4 else 0
            if solved:
                d = (x + y) * 0.035
                if st > d:
                    if pane.sol[y][x]:
                        blit(cv, pane_tile("solid", T, 0, pane.colour(x, y)), X, Y)
                    else:
                        blit(cv, pane_tile("dark", T), X, Y)
                    continue
            if c == UNK:
                blit(cv, pane_tile("unk", T, v), X, Y)
            elif c == GLASS:
                blit(cv, pane_tile("glass", T), X, Y)
            else:
                blit(cv, pane_tile("lead", T, v), X, Y)
                if T == 2:
                    texts.append((X, Y // 2, "·", (150, 154, 170)))
            f = g.flash.get((x, y))
            if f is not None:
                p = t - f
                if 0 <= p < 0.18:
                    tint(cv, X, Y, T, T, WHITE, 0.5 * (1 - p / 0.18))
    # lead came between the cells (bigger panes), heavier every five
    if T >= 5:
        came = (70, 70, 80) if solved else (30, 32, 40)
        for x in range(1, w):
            cv.rect(gx + x * T, gy, 1, h * T, shade(came, 1.6) if x % 5 == 0 and not solved else came)
        for y in range(1, h):
            cv.rect(gx, gy + y * T, w * T, 1, shade(came, 1.6) if y % 5 == 0 and not solved else came)
    # the hint
    if g.hint is not None and not solved:
        kind, i, cells = g.hint
        a = 0.4 + 0.2 * math.sin((t - g.hint_t) * 6)
        if kind == "row":
            tint(cv, gx, gy + i * T, w * T, T, HINT_SRC, a * 0.4)
        else:
            tint(cv, gx + i * T, gy, T, h * T, HINT_SRC, a * 0.4)
        th = max(1, T // 8)
        for (x, y), val in cells.items():
            col = HINT_SAFE if val == GLASS else (190, 150, 255) if val == LEAD else WRONG
            X, Y = gx + x * T, gy + y * T
            if T >= 4:
                ring(cv, X, Y, T, T, col, th, min(1.0, a + 0.4))
            else:
                tint(cv, X, Y, T, T, col, a + 0.2)
    if g.wrong and t - g.wrong_t < 3.0 and int((t - g.wrong_t) * 4) % 2 == 0 and not solved:
        for (x, y) in g.wrong:
            X, Y = gx + x * T, gy + y * T
            ring(cv, X, Y, T, T, WRONG, max(1, T // 6)) if T >= 4 else tint(cv, X, Y, T, T, WRONG, 0.7)
    if hud and not solved:
        X, Y = gx + g.cx * T, gy + g.cy * T
        pul = 0.5 + 0.5 * math.sin(t * 5)
        c = mix(CURSOR, WHITE, 0.35 * pul)
        if T >= 4:
            ring(cv, X, Y, T, T, c, max(1, T // 9))
            if T >= 8:
                ring(cv, X - 1, Y - 1, T + 2, T + 2, shade(c, 0.45))
        else:
            tint(cv, X, Y, T, T, c, 0.5 + 0.15 * pul)
    for tx in texts:
        put_clipped(cv, tx[0], tx[1], tx[2], tx[3])
    if hud:
        draw_hud_pane(cv, g, msg_row, auto, (oy + (cc + h) * T + fb + 1) // 2 + 1)
        if solved and st > 1.2 and not auto:
            lines = [pane.name.upper(), pane.story, "", "time %s" % fmt_time(g.total) +
                     ("   hints %d" % g.helped if g.helped else "")]
            if g.new_best:
                lines.append("a new best for this pane")
            if not g.demo:
                lines += ["", "Enter: next pane   Esc: the panes"]
            bw = max(len(l) for l in lines) + 4
            right = (gx + w * T + fb) + 2
            below = (gy + h * T + fb) // 2 + 1
            if right + bw <= cols:
                pbanner(cv, lines, max(1, (gy + h * T // 2) // 2 - len(lines) // 2 - 1), right)
            elif below + len(lines) + 2 < rows - 1:
                pbanner(cv, lines, below)
    return cv


def pbanner(cv, lines, row=None, col=None):
    w = min(cv.cols, max(len(l) for l in lines) + 4)
    x = max(0, (cv.cols - w) // 2) if col is None else col
    y = max(1, cv.rows - len(lines) - 4) if row is None else min(row, cv.rows - len(lines) - 4)
    cv.box(x, y, [l.center(w - 4)[:w - 4] for l in lines], (236, 236, 244), (24, 20, 30))
    cv.put(x + 2, y + 1, lines[0].center(w - 4)[:w - 4], GOLD, (24, 20, 30))


PANE_KEYS = "arrows move   Space glass   X lead   hold+move drag   U undo   H hint   C check   Esc menu   ? help"


def draw_hud_pane(cv, g, msg_row, auto=None, free=None):
    acc = ACCENTS[NAME][0]
    best = None if g.demo else records().get(g.key)
    num = ("%d " % (g.index + 1)) if g.index is not None else ""
    left = " LEADLIGHT  %s%s %dx%d " % (num, g.pane.name.upper(), g.w, g.h)
    bits = [("set ", HUD_DIM), ("%d%%" % int(g.progress() * 100), HUD_FG), ("  time ", HUD_DIM),
            (fmt_time(g.total), GOLD)]
    if best is not None:
        bits += [("  best ", HUD_DIM), (fmt_time(best), HUD_FG)]
    hud_bar(cv, 0, left, acc, bits)
    draw_message(cv, g, msg_row, PANE_KEYS, auto, free)


# =============================================================================================
# Help
# =============================================================================================
def help_lines(kitty=True):
    drag = ("Hold Space / X while moving to drag a stroke." if kitty else
            "Space / X then move quickly drags; V locks the brush.")
    return ["FENMARK - keys", "",
            "Arrows / WASD     move the lamp (hold to glide)",
            "Space / Enter     probe a tussock  |  set glass",
            "                  on a number: chord (opens the rest",
            "                  when its flags are all placed)",
            "F / X             plant a reed flag  |  mark lead",
            drag,
            "U / Backspace     undo (also out of a bog, +%d s)" % RESCUE_COST,
            "H                 hint: the next deduction (+%d s)" % HINT_COST,
            "C                 check flags / cells (+%d s)" % CHECK_COST,
            "N                 a new fen / random pane   R clear pane",
            "[  ]              previous / next pane",
            "Esc / P           pause (Q there: back)    ? help", "",
            "Bog Sounding: a number counts the bog-eyes in the",
            "8 cells around it. The first probe is always safe,",
            "and every fen can be sounded without a guess.",
            "Leadlight: the numbers are the runs of glass in a",
            "row or column, in order, with lead between them.",
            "Plain row-by-row logic always finds the picture."]


# =============================================================================================
# Keys: held action keys drag a stroke (kitty: exact; classic terminals: a short window, or V to lock)
# =============================================================================================
MOVES = {"up": (0, -1), "w": (0, -1), "down": (0, 1), "s": (0, 1), "left": (-1, 0), "a": (-1, 0),
         "right": (1, 0), "d": (1, 0)}
ACT1 = (" ", "enter")
ACT2 = ("f", "x")


class Controls:
    def __init__(self, kitty):
        self.kitty = kitty
        self.down = set()
        self.last = {}               # key -> (time, cursor) of its last press (classic repeats)
        self.drag_until = 0.0
        self.lock = False
        self.target = GLASS

    def reset(self):
        self.down.clear()
        self.lock = False
        self.drag_until = 0.0

    def is_repeat(self, name, kind, now, cursor):
        if kind == "repeat":
            return True
        if self.kitty:
            return False
        t, c = self.last.get(name, (-9.0, None))
        self.last[name] = (now, cursor)
        return now - t < 0.12 and c == cursor

    def dragging(self, now):
        if self.lock:
            return True
        if self.kitty:
            return any(k in self.down for k in ACT1 + ACT2)
        return now < self.drag_until


def handle_game_key(g, ctl, name, kind, now):
    """A key in play that is not a shared one. Returns 'new', 'next', 'prev' or None."""
    cursor = (g.cx, g.cy)
    if kind == "release":
        ctl.down.discard(name)
        if g.kind == "pane" and name in ACT1 + ACT2 and not ctl.dragging(now):
            g.end_stroke()
        return None
    if name in MOVES:
        dx, dy = MOVES[name]
        if g.kind == "pane":
            if ctl.lock and g.stroke is None and not g.solved:
                g.stroke = [ctl.target, True, []]
            if not ctl.dragging(now) and g.stroke is not None:
                g.end_stroke()
            g.move(dx, dy)
            if not ctl.kitty and g.stroke is not None and not ctl.lock:
                ctl.drag_until = now + 0.55
        else:
            g.move(dx, dy)
        return None
    if name in ACT1 + ACT2:
        if kind == "press" and ctl.kitty:
            ctl.down.add(name)
        if g.over and name in ACT1 and kind == "press":
            return "next"
        if g.over:
            return None
        if ctl.is_repeat(name, kind, now, cursor):
            return None
        if g.kind == "sweep":
            if name in ACT1:
                g.probe()
            else:
                g.toggle_flag()
        else:
            ctl.target = GLASS if name in ACT1 else LEAD
            g.begin(ctl.target)
            if not ctl.kitty:
                ctl.drag_until = now + 0.55
        return None
    if kind != "press":
        return None
    if name in ("u", "backspace"):
        g.undo()
    elif name == "h":
        g.ask_hint()
    elif name == "c":
        g.check()
    elif name == "v" and g.kind == "pane":
        ctl.lock = not ctl.lock
        if not ctl.lock:
            g.end_stroke()
        g.say("Brush lock on: moving keeps setting %s (V again: off)." % (
            "glass" if ctl.target == GLASS else "lead") if ctl.lock else "Brush lock off.")
    elif name == "r" and g.kind == "pane":
        g.restart()
    elif name == "n":
        return "new"
    elif name == "]" and g.kind == "pane":
        return "next"
    elif name == "[" and g.kind == "pane":
        return "prev"
    return None


# =============================================================================================
# Auto mode: the solver plays, one explained deduction at a time, reading only what a player sees
# =============================================================================================
class Bot:
    """Drives a Sweep or a Glaze: shows the next deduction (highlighted, with its words), then makes it."""

    def __init__(self, g, show=0.9, gap=0.25):
        self.g = g
        self.show_t, self.gap_t = show, gap
        self.phase = "think"
        self.timer = 0.0
        self.step = None
        self.done_t = 0.0
        self.stuck = False

    @property
    def finished(self):
        return self.g.over and self.done_t > (4.0 if self.g.kind == "pane" else 3.0) or self.stuck

    def update(self, dt):
        g = self.g
        g.update(dt)
        if g.over:
            self.done_t += dt
            return
        self.timer += dt
        if self.phase == "think":
            if self.timer < self.gap_t:
                return
            self.timer = 0.0
            if g.kind == "sweep":
                if g.fen is None:
                    g.say("The first probe is always safe: start in the middle of the fen.")
                    g.probe(g.cy * g.w + g.cx)
                    return
                s = g.next_step()
                if s is None:
                    self.stuck = True
                    return
                g.hint, g.hint_t = s, g.clock
                g.say(s.text)
                tgt = (s.safe or s.mines)[0]
                g.cx, g.cy = tgt % g.w, tgt // g.w
                self.step = s
            else:
                st = g.next_step()
                if st is None or st[3] is None:
                    self.stuck = True
                    return
                kind, i, before, after = st
                cells = {}
                for k, (a, b) in enumerate(zip(before, after)):
                    if a != b:
                        cells[(k, i) if kind == "row" else (i, k)] = b
                clues = g.pane.rclues[i] if kind == "row" else g.pane.cclues[i]
                g.hint, g.hint_t = (kind, i, cells), g.clock
                g.say(explain_line(kind, i, clues, before, after))
                (g.cx, g.cy) = min(cells)
                self.step = cells
            self.phase = "show"
        elif self.phase == "show" and self.timer >= self.show_t:
            self.timer = 0.0
            if g.kind == "sweep":
                s = self.step
                for j in s.mines:
                    if not g.flag[j]:
                        g.toggle_flag(j)
                src = s.src[0] if len(s.src) == 1 else None
                if s.rule == "clear" and src is not None and g.opened[src] and \
                        sum(g.flag[j] for j in g.nb[src]) == g.fen.num[src]:
                    g.chord(src)
                for j in s.safe:
                    if not g.opened[j] and not g.over:
                        g.probe(j)
            else:
                g.apply(self.step)
                g.snd("line", 0.6)
            g.hint = None
            self.phase = "think"


AUTO_KINDS = ("Both", "Bog Sounding", "Leadlight")


def auto_jobs(kind):
    """The endless programme of auto mode."""
    k = 0
    pane_order = [0, 10, 18, 2, 12, 5, 16, 20, 7, 14, 1, 19, 4, 11, 21, 3, 15, 8, 13, 6, 17, 9]
    while True:
        if kind in (0, 1):
            name, w, h, c = DIFFS[k % 3]
            yield "sweep", (w, h, c), "%s %dx%d" % (name, w, h)
        if kind in (0, 2):
            i = pane_order[k % len(pane_order)]
            yield "pane", i, "%d %s" % (i + 1, PANES[i].name)
        k += 1


def make_job(job, quiet, seed):
    kind, arg, label = job
    if kind == "sweep":
        w, h, c = arg
        return Sweep(w, h, c, seed=seed, quiet=quiet, demo=True)
    return Glaze(PANES[arg], pane_key(arg), quiet=quiet, demo=True, index=arg)


def render_game(g, cols, rows, hud=True, auto=None):
    return render_sweep(g, cols, rows, hud, auto) if g.kind == "sweep" else render_pane(g, cols, rows, hud, auto)


class AutoRun:
    def __init__(self, kind=0, sound=True, seed=1):
        self.auto = AutoMode()
        self.sound = sound
        self.jobs = auto_jobs(kind)
        self.seed = seed
        self.count = 0
        self.new()

    def new(self):
        self.job = next(self.jobs)
        self.seed += 1
        self.g = make_job(self.job, not self.sound, self.seed)
        self.g.label = self.job[2]
        self.bot = Bot(self.g)

    def key(self, k):
        a = self.auto.key(k)
        if a == "sound" and SND.toggle():
            SND.play("sound_on")
        return a

    def frame(self, dt, cols, rows, draw=True):
        sdt = self.auto.scale(dt)
        n = max(1, int(self.auto.speed))
        for _ in range(n):
            self.bot.update(sdt / n)
            if self.bot.finished:
                self.count += 1
                self.new()
        if not draw:
            return None
        cv = render_game(self.g, cols, rows, True, self.auto)
        return cv


# =============================================================================================
# The title demo (also the launcher preview)
# =============================================================================================
class TitleDemo:
    def __init__(self, k=0):
        self.k = k
        self.new()

    def new(self):
        if self.k % 2 == 0:
            self.g = Sweep(9, 9, 10, seed=100 + self.k, quiet=True, demo=True)
        else:
            self.g = Glaze(PANES[(self.k // 2 * 3) % 10], "demo", quiet=True, demo=True)
        self.bot = Bot(self.g, show=0.45, gap=0.12)
        self.k += 1

    def scene(self, cols, rows, dt):
        self.bot.update(min(0.1, dt))
        if self.bot.finished:
            self.new()
        return render_game(self.g, cols, max(1, rows), hud=False)


# =============================================================================================
# Menus
# =============================================================================================
CUSTOM = {"w": 20, "h": 14, "c": 50}


def custom_limits():
    w, h = CUSTOM["w"], CUSTOM["h"]
    return max(1, int(w * h * 0.25))


def menu_items(diff, akind):
    name, w, h, c = DIFFS[diff]
    rec = records()
    solved = sum(1 for i in range(len(PANES)) if pane_key(i) in rec)
    return ["Bog Sounding   < %s %dx%d >" % (name, w, h),
            "Custom fen       %dx%d, %d eyes" % (CUSTOM["w"], CUSTOM["h"], CUSTOM["c"]),
            "Leadlight panes  %d / %d mended" % (solved, len(PANES)),
            "%s      < %s >" % (AUTO_LABEL, AUTO_KINDS[akind])]


def render_menu(demo, cols, rows, sel, diff, akind, dt, help_, kitty):
    cv = demo.scene(cols, rows, dt)
    cv.text = {}                       # the demo's small numbers would sit on the title letters
    rec = records()
    bits = []
    for name, w, h, c in DIFFS:
        if name in rec:
            bits.append("%s %s" % (name, fmt_time(rec[name])))
    solved = sum(1 for i in range(len(PANES)) if pane_key(i) in rec)
    if solved:
        bits.append("%d / %d panes" % (solved, len(PANES)))
    best = ("best  " + "   ".join(bits)) if bits else None
    extra = ["", "Sound the fen without a guess,", "mend the pump-house windows."]
    title_screen(cv, NAME, TAGLINE, menu_items(diff, akind), sel, best, extra=extra,
                 keys="Up/Down choose   Left/Right change   Enter start   M %s   ? help   Esc back" %
                      SND.label().lower(),
                 help_lines=help_lines(kitty), show_help=help_, dim=0.5)
    return cv


def render_custom(cols, rows, sel):
    cv = Canvas(cols, 1)
    cv.rows, cv.H = rows, rows * 2
    cv.px = [[mix(c, (6, 6, 14), 0.4) for c in r] for r in fen_backdrop(cols, rows)]
    hud_bar(cv, 0, " FENMARK - a fen of your own ", ACCENTS[NAME][1], [])
    w, h, c = CUSTOM["w"], CUSTOM["h"], CUSTOM["c"]
    lines = [("Width", "%d" % w, "6 - 32"), ("Height", "%d" % h, "6 - 20"),
             ("Bog-eyes", "%d  (%d%%)" % (c, round(100.0 * c / (w * h))), "1 - %d" % custom_limits()),
             ("Sound it", "", "")]
    x0 = max(1, cols // 2 - 18)
    y0 = max(2, rows // 2 - 6)
    for k, (a, b, lim) in enumerate(lines):
        r = y0 + k * 2
        on = k == sel
        cv.put(x0, r, (" > " if on else "   ") + a.ljust(10) + ("<  %s  >" % b if b else "").ljust(16) +
               lim.rjust(9) + " ", INK if on else PANEL_FG, mix(ACCENTS[NAME][0], ACCENTS[NAME][1], 0.3) if on
               else PANEL_BG)
    # a little map of the size
    T = max(1, min((cols - 4) // max(1, w), (rows * 2 - (y0 + 9) * 2 - 4) // max(1, h)))
    T = min(T, 4)
    if T >= 1 and (y0 + 9) * 2 + h * T < rows * 2 - 2:
        ox, oy = (cols - w * T) // 2, (y0 + 9) * 2
        rnd = random.Random(w * 100 + h)
        eyes = set(rnd.sample(range(w * h), min(c, w * h)))
        for y in range(h):
            for x in range(w):
                col = MOSS[hsh(x, y) & 3]
                if y * w + x in eyes:
                    col = mix(col, (20, 30, 24), 0.5)
                cv.rect(ox + x * T, oy + y * T, T, T, col)
    footer(cv, "Up/Down choose   Left/Right change   Enter sound it   Esc back")
    return cv


def paste(cv, sub, col0, row0):
    """Another canvas (pixels and text) into this one at a text cell."""
    y0 = row0 * 2
    for y in range(sub.H):
        if 0 <= y0 + y < cv.H:
            row = cv.px[y0 + y]
            src = sub.px[y]
            for x in range(sub.W):
                if 0 <= col0 + x < cv.W:
                    row[col0 + x] = src[x]
    for (x, r), v in sub.text.items():
        if 0 <= col0 + x < cv.cols and 0 <= row0 + r < cv.rows:
            cv.text[(col0 + x, row0 + r)] = v


_SAMPLE = {}


def sample_pane(w, h):
    if (w, h) not in _SAMPLE:
        _SAMPLE[(w, h)] = gen_pane(w, h, 0)
    return _SAMPLE[(w, h)]


def pane_entries():
    return [("pane", i) for i in range(len(PANES))] + [("random", k) for k in range(len(RANDOM_SIZES))]


def render_panes(cols, rows, sel, help_=False, kitty=True):
    rec = records()
    cv = Canvas(cols, 1)
    cv.rows, cv.H = rows, rows * 2
    cv.px = [[mix(c, (6, 6, 14), 0.3) for c in r] for r in wall_backdrop(cols, rows)]
    solved = sum(1 for i in range(len(PANES)) if pane_key(i) in rec)
    hud_bar(cv, 0, " FENMARK - the pump-house windows ", ACCENTS[NAME][0],
            [("%d / %d mended " % (solved, len(PANES)), GOLD)])
    ents = pane_entries()
    lw = min(34, cols // 2 - 2)
    vis = rows - 3
    top = clamp(sel - vis // 2, 0, max(0, len(ents) - vis))
    for k in range(vis):
        j = top + k
        if j >= len(ents):
            break
        kind, i = ents[j]
        if kind == "pane":
            p = PANES[i]
            key = pane_key(i)
            mark = "♦" if key in rec else "·"
            txt = "%2d %s" % (i + 1, p.name)
            tm = fmt_time(rec[key]) if key in rec else "%dx%d" % (p.w, p.h)
        else:
            w, h = RANDOM_SIZES[i]
            key = random_key(w, h)
            mark = "?"
            txt = "   random pane %dx%d" % (w, h)
            tm = fmt_time(rec[key]) if key in rec else ""
        line = (" %s %s" % (mark, txt))[:lw - 7].ljust(lw - 7) + tm.rjust(6) + " "
        on = j == sel
        fg = INK if on else (GOLD if mark == "♦" else PANEL_FG)
        cv.put(1, 1 + k, line, fg, mix(ACCENTS[NAME][0], ACCENTS[NAME][1], 0.25) if on else PANEL_BG)
    # the chosen pane: in colour once mended, as frosted glass before
    kind, i = ents[sel]
    px0 = lw + 3
    aw, ah = cols - px0 - 2, (rows - 6) * 2
    if kind == "pane":
        p = PANES[i]
        done = pane_key(i) in rec
        g = Glaze(p, "preview", quiet=True, demo=True)
        if done:
            g.grid = [[GLASS if p.sol[y][x] else LEAD for x in range(p.w)] for y in range(p.h)]
            g.solved, g.clock, g.end_t = True, 10.0, 0.0
        sub = render_pane(g, cols - px0 - 1, rows - 6, hud=False)
        paste(cv, sub, px0, 1)
        info = [p.name, p.story if done else "Not yet mended - %dx%d." % (p.w, p.h)]
        if done:
            info.append("best %s" % fmt_time(rec[pane_key(i)]))
    else:
        w, h = RANDOM_SIZES[i]
        sub = render_pane(Glaze(sample_pane(w, h), "preview", quiet=True, demo=True), cols - px0 - 1, rows - 6,
                          hud=False)
        paste(cv, sub, px0, 1)
        info = ["A random pane %dx%d" % (w, h), "fresh from the glazier's spare ledger,",
                "each checked to solve by plain logic"]
        if random_key(w, h) in rec:
            info.append("best %s" % fmt_time(rec[random_key(w, h)]))
    for k, s_ in enumerate(info):
        r = rows - 2 - len(info) + k
        if r > 0:
            cv.center(r, " %s " % s_[:aw - 2], GOLD if k == 0 else HUD_FG, PANEL_BG, px0, aw)
    footer(cv, "Up/Down choose   Enter mend   ? help   Esc back")
    if help_:
        overlay(cv, help_lines(kitty))
    return cv


# =============================================================================================
# The loops
# =============================================================================================
def too_small(term):
    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (%dx%d)." % (MIN_COLS, MIN_ROWS))


def finish(g):
    """Record a best time once a puzzle is done (never in auto mode or the demo)."""
    if g.demo or g.recorded:
        return
    if (g.kind == "sweep" and g.won) or (g.kind == "pane" and g.solved):
        g.recorded = True
        g.new_best = record(g.key, g.total)
        if g.new_best and g.kind == "sweep":
            g.say("The fen is sounded in %s - a new best for %s!   Enter: another fen" % (fmt_time(g.total), g.key))


def play(term, make):
    """make(step) -> a new game ('new', 'next', 'prev' or None for the first)."""
    g = make(None)
    ctl = Controls(term.kitty)
    last = time.time()
    while True:
        now = time.time()
        dt = min(0.1, now - last)
        last = now
        for name, kind in term.events():
            a = None
            if kind == "press":
                a = shared_key(name, g.paused, view_key=g.kind != "pane")   # in the panes V is the brush lock
            elif g.paused:
                continue
            if a == "pause":
                g.paused = True
                if g.kind == "pane":
                    g.end_stroke()
                SND.play("pause")
            elif a == "resume":
                g.paused = g.help = False
                ctl.reset()
            elif a == "quit":
                return
            elif a == "help":
                g.help = not g.help
                g.paused = True
            elif a == "sound":
                if SND.toggle():
                    SND.play("sound_on")
            elif a in ("eaten",):
                pass
            elif a is None:
                r = handle_game_key(g, ctl, name, kind, now)
                ng = make(r) if r else None
                if ng is not None:
                    g = ng
                    ctl.reset()
                    SND.play("start")
        if g.kind == "pane" and g.stroke is not None and not ctl.dragging(now) and not ctl.down:
            g.end_stroke()
        cols, rows = term.size()
        if cols < MIN_COLS or rows < MIN_ROWS:
            too_small(term)
            time.sleep(0.2)
            last = time.time()
            continue
        if not g.paused:
            g.update(dt)
        finish(g)
        cv = render_game(g, cols, rows)
        if g.paused:
            overlay(cv, help_lines(term.kitty) if g.help else PAUSE_LINES[:-1] + ["Q                 back", "",
                                                                                   SND.label()])
        term.write(cv.emit())
        time.sleep(max(0.0, 1 / 30 - (time.time() - now)))


def sweep_maker(w, h, c):
    def make(step):
        return Sweep(w, h, c, seed=random.randrange(1 << 30)) if step in (None, "new", "next") else None
    return make


def pane_maker(sel):
    ents = pane_entries()
    state = {"sel": sel}

    def make(step):
        s = state["sel"]
        kind = ents[s][0]
        if step == "next" and kind == "pane":
            if s + 1 >= len(PANES):
                return None
            s += 1
        elif step == "prev":
            if kind != "pane" or s == 0:
                return None
            s -= 1
        elif step == "new" and kind == "pane":
            return None
        state["sel"] = s
        kind, i = ents[s]
        if kind == "pane":
            return Glaze(PANES[i], pane_key(i), index=i)
        w, h = RANDOM_SIZES[i]
        return Glaze(gen_pane(w, h, random.randrange(1 << 30)), random_key(w, h))
    make.state = state
    return make


def run_auto(term, kind):
    run = AutoRun(kind)
    last = time.time()
    while True:
        now = time.time()
        dt, last = min(0.1, now - last), now
        for k, ev in term.events(0):
            if ev == "press" and run.key(k) == "stop":
                return
        cols, rows = term.size()
        if cols < MIN_COLS or rows < MIN_ROWS:
            too_small(term)
            time.sleep(0.2)
            continue
        term.write(run.frame(dt, cols, rows).emit())
        time.sleep(max(0.0, 1 / 30 - (time.time() - now)))


def custom_screen(term):
    sel = 0
    while True:
        cols, rows = term.size()
        if cols < MIN_COLS or rows < MIN_ROWS:
            too_small(term)
            if any(k in ("q", "esc") for k, kind in term.events(0.3) if kind == "press"):
                return None
            continue
        term.write(render_custom(cols, rows, sel).emit())
        for k, kind in term.events(1 / 20):
            if kind == "release":
                continue
            if k in ("q", "esc"):
                return None
            if k in ("up", "w"):
                sel = (sel - 1) % 4
                SND.play("menu")
            elif k in ("down", "s", "tab"):
                sel = (sel + 1) % 4
                SND.play("menu")
            elif k in ("left", "a", "right", "d") and sel < 3:
                d = -1 if k in ("left", "a") else 1
                if sel == 0:
                    CUSTOM["w"] = clamp(CUSTOM["w"] + d, 6, 32)
                elif sel == 1:
                    CUSTOM["h"] = clamp(CUSTOM["h"] + d, 6, 20)
                else:
                    CUSTOM["c"] += d * (1 if kind == "press" else 2)
                CUSTOM["c"] = clamp(CUSTOM["c"], 1, custom_limits())
            elif k in ("enter", " ") and kind == "press":
                SND.play("start")
                return CUSTOM["w"], CUSTOM["h"], CUSTOM["c"]


def panes_screen(term, sel):
    help_ = False
    n = len(pane_entries())
    while True:
        cols, rows = term.size()
        if cols < MIN_COLS or rows < MIN_ROWS:
            too_small(term)
            if any(k in ("q", "esc") for k, kind in term.events(0.3) if kind == "press"):
                return None
            continue
        term.write(render_panes(cols, rows, sel, help_, term.kitty).emit())
        for k, kind in term.events(1 / 20):
            if kind == "release":
                continue
            if help_:
                help_ = False
            elif k == "?":
                help_ = True
            elif k in ("q", "esc"):
                return None
            elif k in ("up", "w"):
                sel = (sel - 1) % n
                SND.play("menu")
            elif k in ("down", "s", "tab"):
                sel = (sel + 1) % n
                SND.play("menu")
            elif k in ("pgup", "left", "a"):
                sel = max(0, sel - 5)
            elif k in ("pgdn", "right", "d"):
                sel = min(n - 1, sel + 5)
            elif k in ("enter", " ") and kind == "press":
                SND.play("start")
                return sel


def first_unsolved():
    rec = records()
    for i in range(len(PANES)):
        if pane_key(i) not in rec:
            return i
    return 0


def main():
    with KeyTerminal() as term:
        demo = TitleDemo()
        sel, diff, akind, help_ = 0, 0, 0, False
        psel = first_unsolved()
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
            term.write(render_menu(demo, cols, rows, sel, diff, akind, min(0.1, now - last), help_,
                                   term.kitty).emit())
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
                    d = -1 if k in ("left", "a") else 1
                    if sel == 3:
                        akind = (akind + d) % len(AUTO_KINDS)
                    else:
                        diff = (diff + d) % len(DIFFS)
                        sel = 0
                    SND.play("menu")
                elif k == "m":
                    if SND.toggle():
                        SND.play("sound_on")
                elif k in ("enter", " "):
                    SND.play("start")
                    go = True
            if not go:
                continue
            if sel == 0:
                play(term, sweep_maker(*DIFFS[diff][1:]))
            elif sel == 1:
                c = custom_screen(term)
                if c:
                    play(term, sweep_maker(*c))
            elif sel == 2:
                while True:
                    choice = panes_screen(term, psel)
                    if choice is None:
                        break
                    psel = choice
                    mk = pane_maker(choice)
                    play(term, mk)
                    psel = mk.state["sel"]
            else:
                run_auto(term, akind)
            last = time.time()


# =============================================================================================
# Self-test
# =============================================================================================
def brute_check(lg, steps, w, h):
    """Every deduction must hold in every placement of the bog-eyes that fits the open numbers and the count."""
    import itertools
    n = w * h
    unknown = [i for i in range(n) if lg.num[i] < 0 and not lg.mine[i]]
    known = sum(lg.mine)
    fits = []
    for k in range(0, len(unknown) + 1):
        if known + k != lg.total:
            continue
        for combo in itertools.combinations(unknown, k):
            m = set(combo) | set(i for i in range(n) if lg.mine[i])
            if all(lg.num[i] < 0 or sum(1 for j in lg.nb[i] if j in m) == lg.num[i] for i in range(n)):
                fits.append(m)
    for s in steps:
        for j in s.safe:
            assert all(j not in m for m in fits), "a cell proved safe can hide a bog-eye (%s)" % s.rule
        for j in s.mines:
            assert all(j in m for m in fits), "a cell proved a bog-eye can be safe (%s)" % s.rule
    return len(fits)


def selftest():
    t0 = time.time()
    global submit

    def no_scores(*a, **k):
        raise AssertionError("the self-test must not write scores")
    submit = no_scores
    _REC[0] = {}
    # 1. the hand-made windows: all different, each settled by plain line logic (so exactly one picture)
    assert len(PANES) == 22 and len(set(p.name for p in PANES)) == 22
    sizes = {}
    for p in PANES:
        assert all(len(r) == p.w for r in p.rows), p.name
        ok, _ = line_solvable(p.rclues, p.cclues)
        assert ok, "%s is not settled by line logic alone" % p.name
        assert max(len(c) for c in p.cclues) <= max_col_clues(p.h), p.name
        assert all(set(r) <= set(".") | set(PAL) | set(p.pal) for r in p.rows), p.name
        steps = list(pane_steps(p.rclues, p.cclues))
        grid = [[UNK] * p.w for _ in range(p.h)]
        for kind, i, before, after in steps:
            assert after is not None
            for k, v in enumerate(after):
                if kind == "row":
                    grid[i][k] = v
                else:
                    grid[k][i] = v
        assert all((grid[y][x] == GLASS) == p.sol[y][x] for y in range(p.h) for x in range(p.w)), p.name
        sizes["%dx%d" % (p.w, p.h)] = sizes.get("%dx%d" % (p.w, p.h), 0) + 1
    print("panes: 22 hand-made (%s), each solved uniquely by line logic, the solver's steps give the picture" %
          ", ".join("%d of %s" % (v, k) for k, v in sorted(sizes.items())))
    # 2. the line solver against brute force
    import itertools
    rng = random.Random(3)
    for _ in range(1500):
        n = rng.randint(1, 9)
        sol = [rng.random() < 0.5 for _ in range(n)]
        clues = clues_of(sol)
        line = [((GLASS if sol[i] else LEAD) if rng.random() < 0.3 else UNK) for i in range(n)]
        if rng.random() < 0.15:
            line[rng.randrange(n)] = rng.choice((GLASS, LEAD))
        fits = [c for c in itertools.product((0, 1), repeat=n) if clues_of(c) == clues and
                all(line[i] == UNK or (line[i] == GLASS) == bool(c[i]) for i in range(n))]
        res = line_solve(line, clues)
        if not fits:
            assert res is None
            continue
        exp = [line[i] if line[i] else (GLASS if all(f[i] for f in fits) else LEAD if not any(f[i] for f in fits)
                                        else UNK) for i in range(n)]
        assert res == exp, (line, clues, res, exp)
    print("line solver: 1500 random lines agree with brute force (contradictions found too)")
    # 3. generated panes
    a = time.time()
    k = 0
    for (w, h) in RANDOM_SIZES:
        for seed in range(12):
            p = gen_pane(w, h, seed)
            assert p.generated and p.w == w and p.h == h and line_solvable(p.rclues, p.cclues)[0]
            k += 1
    print("generated panes: %d at 10x10, 15x15, 20x15 all uniquely line-solvable (%.0f ms each)" % (
        k, (time.time() - a) / k * 1000))
    # 4. the sounding logic against brute force on small fens
    rng = random.Random(9)
    checked = rules = 0
    seen_rules = set()
    for trial in range(220):
        w, h = rng.choice(((4, 4), (5, 4), (5, 5)))
        cnt = rng.randint(2, 6)
        fen = Fen(w, h, rng.sample(range(w * h), cnt))
        lg = Logic(w, h, cnt)
        safe = [i for i in range(w * h) if not fen.eye[i]]
        for i in rng.sample(safe, rng.randint(1, max(1, len(safe) // 2))):
            lg.open(i, fen.num[i])
        for i in range(w * h):
            if fen.eye[i] and rng.random() < 0.2:
                lg.mine[i] = 1
        for _ in range(4):
            steps = lg.find(first=False)
            if not steps:
                break
            brute_check(lg, steps, w, h)
            checked += 1
            rules += len(steps)
            for s in steps:
                seen_rules.add(s.rule)
                for j in s.mines:
                    lg.mine[j] = 1
                for j in s.safe:
                    lg.safe[j] = 1
    assert {"clear", "full", "pair", "weigh"} <= seen_rules, seen_rules
    print("sounding logic: %d rounds, %d deductions (%s) hold in every placement brute force finds" % (
        checked, rules, ", ".join(sorted(seen_rules))))
    # 5. laying fens: first probe safe and open, solvable without a guess, the count right
    for name, w, h, c in DIFFS + (("custom small", 6, 6, 9), ("custom dense", 32, 20, 160)):
        rng = random.Random(len(name))
        a = time.time()
        worst = 0.0
        runs = 6 if w * h < 500 else 4
        for _ in range(runs):
            first = rng.randrange(w * h)
            b = time.time()
            fen, tries = lay_fen(w, h, c, first, rng)
            worst = max(worst, time.time() - b)
            assert tries > 0 and fen.count == c
            assert not fen.eye[first] and fen.num[first] == 0, "the first probe did not open ground"
            ok, lg = sound_out(fen, first)
            assert ok, "%s: a fen needs a guess" % name
            assert all(bool(lg.mine[i]) == bool(fen.eye[i]) for i in range(w * h))
        print("fens: %-12s %2dx%-2d %3d eyes: %d laid, none needs a guess (worst %.2f s)" % (
            name, w, h, c, runs, worst))
    # 6. the rules of a sounding in play
    g = Sweep(9, 9, 10, seed=5, quiet=True, demo=True)
    assert g.toggle_flag() is False, "a flag before the first probe"
    g.probe()
    assert g.fen and g.opened[g.cy * 9 + g.cx] and sum(g.opened) > 1 and not g.over
    i0 = g.cy * 9 + g.cx
    eyes = [i for i in range(81) if g.fen.eye[i]]
    shut = [i for i in range(81) if not g.opened[i] and not g.fen.eye[i]]
    # a flag, a chord, a wrong flag found by check, then a fall and the rescue
    num_cell = next(i for i in range(81) if g.opened[i] and g.fen.num[i] > 0)
    for j in g.nb[num_cell]:
        if g.fen.eye[j]:
            g.toggle_flag(j)
    before = sum(g.opened)
    g.chord(num_cell)
    assert sum(g.opened) >= before and not g.over, "a chord with the right flags"
    s = g.next_step()
    assert s is not None and all(not g.fen.eye[j] for j in s.safe) and all(g.fen.eye[j] for j in s.mines)
    pen = g.penalty
    g.ask_hint()
    assert g.hint is not None and g.penalty == pen + HINT_COST
    safe_shut = [i for i in range(81) if not g.opened[i] and not g.fen.eye[i] and not g.flag[i]]
    g.toggle_flag(safe_shut[0])
    g.check()
    assert safe_shut[0] in g.wrong and g.penalty == pen + HINT_COST + CHECK_COST
    g.toggle_flag(safe_shut[0])
    eye = next(i for i in eyes if not g.flag[i])
    g.probe(eye)
    assert g.lost == eye and g.over
    g.undo()
    assert g.lost is None and not g.opened[eye] and g.penalty == pen + HINT_COST + CHECK_COST + RESCUE_COST
    t_before = g.time
    g.update(1.0)
    assert abs(g.time - t_before - 1.0) < 1e-6
    for j in range(81):
        if not g.fen.eye[j] and not g.opened[j]:
            if g.flag[j]:
                g.toggle_flag(j)
            g.probe(j)
    assert g.won and all(g.flag[i] for i in eyes)
    t_won = g.time
    g.update(1.0)
    assert g.time == t_won, "the clock ran on after the end"
    print("sounding rules: first probe opens ground, flags, chord, hint (+%d s, sound), check finds a wrong flag "
          "(+%d s), a fall and undo out of it (+%d s), win flags the rest, clock stops" % (
              HINT_COST, CHECK_COST, RESCUE_COST))
    # 7. the rules of a pane in play, through the real keys (classic and kitty drag)
    p = PANES[0]
    g = Glaze(p, "t", quiet=True, demo=True)
    ctl = Controls(False)
    now = 100.0
    handle_game_key(g, ctl, " ", "press", now)
    assert g.grid[0][0] == GLASS
    handle_game_key(g, ctl, " ", "press", now + 0.03)              # a classic key repeat: no toggle back
    assert g.grid[0][0] == GLASS
    for k in range(3):
        handle_game_key(g, ctl, "right", "press", now + 0.1 + k * 0.05)
    assert [g.grid[0][x] for x in range(4)] == [GLASS] * 4, "classic drag"
    g.end_stroke()
    assert len(g.history) == 1
    g.undo()
    assert all(c == UNK for c in g.grid[0])
    ctl = Controls(True)
    g.cx = g.cy = 0
    handle_game_key(g, ctl, "x", "press", now)
    handle_game_key(g, ctl, "down", "press", now + 1)
    handle_game_key(g, ctl, "down", "repeat", now + 2)
    handle_game_key(g, ctl, "x", "release", now + 3)
    handle_game_key(g, ctl, "down", "press", now + 4)
    assert [g.grid[y][0] for y in range(4)] == [LEAD, LEAD, LEAD, UNK], "kitty drag"
    handle_game_key(g, ctl, "up", "press", now + 5)
    handle_game_key(g, ctl, "x", "press", now + 6)                  # on a lead cell: clears
    assert g.grid[2][0] == UNK
    g.end_stroke()
    st = g.next_step()
    assert st is not None and st[3] is not None
    g.grid[0][4] = LEAD                                             # a wrong cell (row 1 is ....kk....)
    g.check()
    assert (4, 0) in g.wrong
    g.grid[0][4] = UNK
    g.restart()
    assert all(c == UNK for r in g.grid for c in r) and g.undo()
    g.restart()
    # solve it with the keys: walk every row, set the glass
    ctl = Controls(True)
    for y in range(p.h):
        for x in range(p.w):
            g.cx, g.cy = x, y
            if p.sol[y][x]:
                handle_game_key(g, ctl, " ", "press", now)
                handle_game_key(g, ctl, " ", "release", now)
    assert g.solved and all(g.grid[y][x] == (GLASS if p.sol[y][x] else LEAD) for y in range(p.h) for x in range(p.w))
    print("pane rules: glass, lead, drag with classic repeats and kitty releases, clear by stroke, undo, restart, "
          "hint, check finds a wrong cell, solved by keys")
    # 8. the fair solver plays everything: every hand-made pane and every kind of fen, through the Bot
    a = time.time()
    for i in range(len(PANES)):
        g = Glaze(PANES[i], pane_key(i), quiet=True, demo=True, index=i)
        bot = Bot(g, show=0.05, gap=0.01)
        for _ in range(20000):
            bot.update(0.05)
            if g.solved:
                break
        assert g.solved and not bot.stuck, "the bot could not mend %s" % PANES[i].name
    for name, w, h, c in DIFFS:
        for seed in range(3):
            g = Sweep(w, h, c, seed=seed, quiet=True, demo=True)
            bot = Bot(g, show=0.02, gap=0.01)
            for _ in range(50000):
                bot.update(0.05)
                if g.over:
                    break
            assert g.won and not bot.stuck, "the bot did not sound %s (seed %d)" % (name, seed)
    print("bot: all 22 panes mended and 9 fens sounded step by step from what is visible (%.1f s)" % (time.time() - a))
    # 9. auto mode: runs, pauses, speeds up, stops, writes nothing
    run = AutoRun(0, sound=False)
    run.key("+")
    run.key("+")
    run.key("+")
    for k in range(1800):
        run.frame(1 / 30, 80, 24, draw=k % 20 == 0)
    assert run.count >= 2, "auto mode finished only %d puzzles" % run.count
    run.key(" ")
    snap = (run.g.clock, run.count)
    for _ in range(30):
        run.frame(1 / 30, 80, 24, draw=False)
    assert (run.g.clock, run.count) == snap, "auto mode ran on while paused"
    assert run.key("esc") == "stop"
    print("auto mode: %d puzzles done in 60 s at x8, pause holds, Esc stops, nothing recorded" % run.count)
    # 10. drawing at every size, with frame times
    timing = []
    nf = 0
    gs = []
    g = Sweep(30, 16, 99, seed=4, quiet=True)
    g.probe()
    bot = Bot(g, 0.01, 0.01)
    for _ in range(300):
        bot.update(0.05)
    g.ask_hint()
    gs.append(g)
    g = Sweep(16, 16, 40, seed=4, quiet=True)
    g.probe()
    eye = next(i for i in range(g.n) if g.fen.eye[i])
    g.probe(eye)
    gs.append(g)
    for i in (12, 21, 3):
        g = Glaze(PANES[i], pane_key(i), quiet=True, index=i)
        for k, st in enumerate(pane_steps(g.pane.rclues, g.pane.cclues)):
            if k > 12:
                break
            kind, j, b, a_ = st
            g.apply({((q, j) if kind == "row" else (j, q)): v for q, v in enumerate(a_) if b[q] != v})
        g.ask_hint()
        gs.append(g)
    g = Glaze(PANES[18], pane_key(18), quiet=True, index=18)
    g.apply({(x, y): GLASS for y in range(g.h) for x in range(g.w) if g.pane.sol[y][x]})
    g.update(3.0)
    gs.append(g)
    for cols, rows in ((70, 22), (80, 24), (100, 32), (120, 40), (160, 50), (240, 70)):
        tr = te = 0.0
        fr = 0
        for g in gs:
            for _ in range(2):
                b = time.time()
                cv = render_game(g, cols, rows)
                c_ = time.time()
                cv.emit(True)
                tr += c_ - b
                te += time.time() - c_
                fr += 1
                g.update(0.05)
                if g.kind == "pane":
                    T, ox, oy, rc, cc, mr = pane_layout(g, cols, rows)
                    assert T >= 2 and ox >= 0 and oy + (g.h + cc) * T <= rows * 2, "a pane does not fit %dx%d" % (
                        cols, rows)
                else:
                    T, ox, oy, mr = sweep_layout(g, cols, rows)
                    assert T >= 2 and oy + g.h * T <= rows * 2
        overlay(cv, help_lines(True))
        render_panes(cols, rows, 3).emit(True)
        render_panes(cols, rows, len(PANES) + 1, True).emit(True)
        render_custom(cols, rows, 2).emit(True)
        nf += fr + 3
        timing.append((cols, rows, tr / fr * 1000, te / fr * 1000))
    for i in range(len(PANES)):
        g = Glaze(PANES[i], pane_key(i), quiet=True)
        T, ox, oy, rc, cc, mr = pane_layout(g, MIN_COLS, MIN_ROWS)
        assert T >= 2 and oy + (g.h + cc) * T <= MIN_ROWS * 2 and ox + (g.w + rc) * T <= MIN_COLS, PANES[i].name
    d = TitleDemo()
    for cols, rows in ((70, 22), (120, 40), (24, 8), (40, 12), (60, 30)):
        if rows >= 20:
            render_menu(d, cols, rows, 0, 1, 0, 0.05, False, True).emit(True)
        else:
            d.scene(cols, rows, 0.05).emit(True)
        nf += 1
    for _ in range(900):
        d.scene(30, 9, 0.1)
    print("rendering: %d frames at 70x22 .. 240x70 (fens, a fall, panes, a lit pane, menus, previews 24x8)" % nf)
    for cols, rows, r_, e_ in timing:
        print("  %3dx%-3d render %5.1f ms  emit %5.1f ms  = %5.1f ms per frame (%3.0f fps)" % (
            cols, rows, r_, e_, r_ + e_, 1000 / max(0.1, r_ + e_)))
    shot = screenshot(100, 32)
    assert shot.cols == 100 and shot.emit(True) == screenshot(100, 32).emit(True), "the screenshot is not repeatable"
    print("Self-test ok (%.1f s)" % (time.time() - t0))


def screenshot(cols=100, rows=32):
    """README picture: the solver sounding a Peat Meadow, a deduction highlighted with its words. Deterministic
    and quiet; nothing written."""
    g = Sweep(9, 9, 10, seed=16, quiet=True, demo=True)
    bot = Bot(g, show=0.5, gap=0.2)
    k = 0
    while k < 6000 and not (sum(g.opened) >= 57 and bot.phase == "show" and g.hint is not None and
                            g.hint.rule in ("pair", "weigh")):
        bot.update(0.05)
        k += 1
    g.update(0.3)
    g.cx, g.cy = 4, 6
    g.say("Hint: " + g.hint.text)
    g.time, g.penalty = 83.0, 0.0
    g.parts = []
    return render_game(g, cols, rows)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--auto" in sys.argv:
        with KeyTerminal() as _term:
            run_auto(_term, 0)
    else:
        main()
