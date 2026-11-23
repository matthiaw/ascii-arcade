#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""CAIRNWARD - push the waystones home.

A storm off the high pass has scattered the waystones of the old mountain road. Hesper the cairn-keeper, a small
badger with a lantern, climbs from the moss steps to the summit and pushes every stone back onto its rune socket.
Stones only move when pushed, never when pulled; a stone in a corner stays there for good.

Seven regions of six cairns each: the Moss Steps and the Quarry Halls are pure pushing; Frostmere adds black ice
on which stones (and Hesper) slide until something stops them; Windgate adds wind tiles that can be crossed in one
direction only; the Lantern Vault adds pressure plates that hold iron gates open while a stone rests on them; the
Rune Garden adds stones of three colours for sockets of their own colour; the Summit mixes everything.

Unlimited undo, restart, a move counter, the best moves of every cairn, a par for each, and a level select that
shows your progress. Every cairn is checked by a real solver (A* with deadlock pruning) in the self-test, and the
same solver plays auto mode, thinking on screen before it walks a solution.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
"""
import heapq
import math
import random
import sys
import time

from arcadekit import (ACCENTS, AUTO_LABEL, PANEL_BG, PANEL_FG, PAUSE_LINES, AutoMode, Canvas, KeyTerminal, clamp,
                       footer, load_scores, mix, overlay, scale_art, shade, shared_key, submit, title_screen)
from arcadesound import Sound

GAME = "cairnward"
NAME = "CAIRNWARD"
TAGLINE = "push the waystones home"
ACCENTS.setdefault(NAME, ((246, 226, 150), (110, 176, 120)))

UP, RIGHT, DOWN, LEFT = 0, 1, 2, 3
DXY = ((0, -1), (1, 0), (0, 1), (-1, 0))
KEYDIR = {"up": UP, "w": UP, "k": UP, "right": RIGHT, "d": RIGHT, "l": RIGHT, "down": DOWN, "s": DOWN, "j": DOWN,
          "left": LEFT, "a": LEFT, "h": LEFT}
ARROWS = {"^": UP, ">": RIGHT, "v": DOWN, "<": LEFT}
NONE = 255
INF = 1 << 30
WHITE = (255, 255, 255)
MAX_W, MAX_H = 14, 10              # the largest cairn, walls included
COLOURS = ((218, 202, 168), (232, 106, 96), (104, 206, 132), (110, 160, 246))   # plain, ember, moss, sky stone


# =============================================================================================
# A cairn: walls, floor, sockets, ice, wind tiles, plates and gates; the stones and Hesper are the state
# =============================================================================================
# Map characters:
#   #  rock            space  floor         .  socket              $  stone           *  stone on a socket
#   @  Hesper          +  Hesper on socket  ~  black ice           ^ > v <  wind tile (enter only that way)
#   _  pressure plate  |  iron gate (open while every plate carries a stone)
#   a b c  ember / moss / sky stone          A B C  ember / moss / sky socket
class Level:
    def __init__(self, rows, name="", world=0, index=0):
        self.name, self.world, self.index = name, world, index
        self.rows = rows
        h = len(rows)
        w = max(len(r) for r in rows)
        self.w, self.h = w, h
        n = w * h
        self.n = n
        self.step = (-w, 1, w, -1)
        self.wall = bytearray(n)
        self.ice = bytearray(n)
        self.gate = bytearray(n)
        self.oneway = bytearray([NONE]) * n
        self.tcol = bytearray([NONE]) * n
        self.plates = []
        boxes = bytearray(n)
        player = None
        for y, row in enumerate(rows):
            for x in range(w):
                ch = row[x] if x < len(row) else " "
                i = y * w + x
                if ch == "#":
                    self.wall[i] = 1
                elif ch in ".*+":
                    self.tcol[i] = 0
                elif ch in "ABC":
                    self.tcol[i] = "ABC".index(ch) + 1
                elif ch == "~":
                    self.ice[i] = 1
                elif ch in ARROWS:
                    self.oneway[i] = ARROWS[ch]
                elif ch == "_":
                    self.plates.append(i)
                elif ch == "|":
                    self.gate[i] = 1
                if ch in "$*":
                    boxes[i] = 1
                elif ch in "abc":
                    boxes[i] = "abc".index(ch) + 2
                if ch in "@+":
                    player = i
        assert player is not None, "%s: no keeper" % name
        self.player0 = player
        self.boxes0 = bytes(boxes)
        self.targets = [i for i in range(n) if self.tcol[i] != NONE]
        # the inside: everything Hesper could ever reach, ignoring stones, gates and wind
        inside = bytearray(n)
        todo = [player]
        inside[player] = 1
        while todo:
            i = todo.pop()
            x, y = i % w, i // w
            for d in range(4):
                nx, ny = x + DXY[d][0], y + DXY[d][1]
                if not (0 <= nx < w and 0 <= ny < h):
                    raise AssertionError("%s: the cairn is open to the outside at %d,%d" % (name, x, y))
                j = ny * w + nx
                if not inside[j] and not self.wall[j]:
                    inside[j] = 1
                    todo.append(j)
        self.inside = inside
        for i in range(n):
            assert inside[i] or (not boxes[i] and self.tcol[i] == NONE), "%s: a stone or socket outside" % name
        self.colours = sorted(set(self.tcol[t] for t in self.targets))
        nbox = [sum(1 for b in self.boxes0 if b == c + 1) for c in range(4)]
        ntgt = [sum(1 for t in self.targets if self.tcol[t] == c) for c in range(4)]
        assert all(nbox[c] >= ntgt[c] for c in range(4)), "%s: too few stones for the sockets" % name
        # a colour with spare stones (some only weigh down plates) is never pruned: any stone may stay behind
        self.spare = [nbox[c] > ntgt[c] for c in range(4)]
        self.ntgt = ntgt
        self.box_colours = [c for c in range(4) if nbox[c]]
        self.cells = [i for i in range(n) if inside[i]]
        self.nbr = [[(d, i + self.step[d]) for d in range(4) if inside[i] and self.enter_ok(i + self.step[d], d, True)]
                    if inside[i] else [] for i in range(n)]
        self.dist = {c: self.box_distances(c) if ntgt[c] else [0] * n for c in range(4) if nbox[c]}

    # --- rules -------------------------------------------------------------------------------
    def gates_open(self, boxes):
        for p in self.plates:
            if not boxes[p]:
                return False
        return True

    def enter_ok(self, i, d, gates):
        if self.wall[i] or (self.gate[i] and not gates):
            return False
        o = self.oneway[i]
        return o == NONE or o == d

    def move(self, p, boxes, d):
        """Hesper steps in direction d. Returns (player, boxes, pushed_from, pushed_to, slide_to) or None when
        the way is blocked. pushed_* are -1 without a push; slide_to is where Hesper ends after sliding."""
        s = self.step[d]
        n = p + s
        gates = self.gates_open(boxes)
        if not self.enter_ok(n, d, gates):
            return None
        bf = bt = -1
        if boxes[n]:
            b2 = n + s
            if boxes[b2] or not self.enter_ok(b2, d, gates):
                return None
            nb = bytearray(boxes)
            c = nb[n]
            nb[n] = 0
            dest = b2
            if self.ice[dest]:
                g2 = self.gates_open(nb)
                while self.ice[dest]:
                    nx = dest + s
                    if nb[nx] or not self.enter_ok(nx, d, g2):
                        break
                    dest = nx
            nb[dest] = c
            boxes = bytes(nb)
            bf, bt = n, dest
        p = n
        if self.ice[p]:
            gates = self.gates_open(boxes)
            while self.ice[p]:
                nx = p + s
                if boxes[nx] or not self.enter_ok(nx, d, gates):
                    break
                p = nx
        return p, boxes, bf, bt

    def solved(self, boxes):
        for t in self.targets:
            if boxes[t] != self.tcol[t] + 1:
                return False
        return True

    # --- the solver's tables -----------------------------------------------------------------------
    def box_distances(self, colour):
        """For one stone of a colour alone in the cairn (gates open, Hesper anywhere she can stand): the fewest
        pushes from each cell to a socket of that colour. INF marks dead cells - a stone there is lost."""
        n, w = self.n, self.w
        edges = [[] for _ in range(n)]          # reverse edges: dest -> [src]
        for c in range(n):
            if not self.inside[c] or self.wall[c]:
                continue
            for d in range(4):
                s = self.step[d]
                behind, ahead = c - s, c + s
                if self.wall[behind] or not self.enter_ok(c, d, True) or not self.enter_ok(ahead, d, True):
                    continue
                dest = ahead
                while self.ice[dest] and self.enter_ok(dest + s, d, True):
                    dest += s
                edges[dest].append(c)
        dist = [INF] * n
        q = [t for t in self.targets if self.tcol[t] == colour]
        for t in q:
            dist[t] = 0
        k = 0
        while k < len(q):
            c = q[k]
            k += 1
            for src in edges[c]:
                if dist[src] == INF:
                    dist[src] = dist[c] + 1
                    q.append(src)
        return dist

    def frozen(self, boxes, i):
        """A 2x2 block of rock and stones around cell i that can never move again, with a stone off its socket."""
        w = self.w
        wall = self.wall
        for o in (0, -1, -w, -w - 1):
            a = i + o
            cells = (a, a + 1, a + w, a + w + 1)
            if all(wall[c] or boxes[c] for c in cells):
                for c in cells:
                    if boxes[c] and boxes[c] != self.tcol[c] + 1 and not self.spare[boxes[c] - 1]:
                        return True
        return False

    def heur(self, boxes):
        """A lower bound on the pushes still needed: per colour, the k nearest stones' fewest pushes home, where k is
        the number of sockets of that colour (every stone when there are no spares). INF: a needed stone is lost."""
        t = 0
        for c in self.box_colours:
            dist = self.dist[c]
            ds = [dist[i] for i in self.cells if boxes[i] == c + 1]
            if self.spare[c]:
                ds.sort()
                ds = ds[:self.ntgt[c]]
            for d in ds:
                if d >= INF:
                    return INF
                t += d
        return t

    def reach(self, p, boxes):
        """Where Hesper can walk without pushing: {cell: moves}. A slide on ice is one move."""
        gates = self.gates_open(boxes)
        seen = {p: 0}
        q = [p]
        k = 0
        nbr, ice, gate, ow, step = self.nbr, self.ice, self.gate, self.oneway, self.step
        while k < len(q):
            c = q[k]
            k += 1
            g = seen[c] + 1
            for d, n in nbr[c]:
                if boxes[n] or (gate[n] and not gates):
                    continue
                if ice[n]:
                    s = step[d]
                    while ice[n]:
                        nx = n + s
                        if boxes[nx] or not self.enter_ok(nx, d, gates):
                            break
                        n = nx
                if n not in seen:
                    seen[n] = g
                    q.append(n)
        return seen

    def paths(self, p, boxes):
        """Like reach, with the way back: {cell: (previous cell, direction)}."""
        seen = {p: (-1, -1)}
        q = [p]
        k = 0
        while k < len(q):
            c = q[k]
            k += 1
            for d in range(4):
                res = self.move(c, boxes, d)
                if res is None or res[2] >= 0:
                    continue
                n = res[0]
                if n not in seen:
                    seen[n] = (c, d)
                    q.append(n)
        return seen


def walk_path(level, p, boxes, goal):
    """The directions that take Hesper from p to goal without pushing (None if she cannot get there)."""
    seen = level.paths(p, boxes)
    if goal not in seen:
        return None
    out = []
    c = goal
    while c != p:
        prev, d = seen[c]
        out.append(d)
        c = prev
    return out[::-1]


def solve(level, p=None, boxes=None, budget=None, exact=True):
    """A* over (Hesper's cell, stones) after each push, cost = moves (a slide is one move). The heuristic
    (Level.heur) never overestimates and changes by at most one per push, so the first solution found has the fewest
    moves: that is the par of every cairn. Pruned: stones on dead cells (no way home even alone) and frozen 2x2
    blocks. exact=False merges positions that differ only in where Hesper stands inside the same walkable area:
    fewer positions, a solution that is not always the shortest.
    A generator: yields ('think', expanded) every `budget` expansions, finally ('done', [directions] or None, expanded)."""
    p = level.player0 if p is None else p
    boxes = level.boxes0 if boxes is None else boxes
    h0 = level.heur(boxes)
    if h0 >= INF:
        yield ("done", None, 0)
        return
    start = (p, boxes)
    best = {start: 0}
    parent = {start: None}
    closed = set()
    heap = [(h0, 0, 0, p, boxes)]
    tick = expanded = 0
    dist, step, cells, frozen, move = level.dist, level.step, level.cells, level.frozen, level.move
    spare = level.spare
    simple = not any(spare)          # then the heuristic can be updated push by push
    while heap:
        f, ng, _, p, boxes = heapq.heappop(heap)
        g = -ng
        key = (p, boxes)
        if best.get(key, INF) < g:
            continue
        reach = level.reach(p, boxes)
        if not exact:
            ckey = (min(reach), boxes)
            if ckey in closed:
                continue
            closed.add(ckey)
        if level.solved(boxes):
            pushes = []
            while parent[key] is not None:
                pk, r, d = parent[key]
                pushes.append((pk, r, d))
                key = pk
            path = []
            for (pk, r, d) in reversed(pushes):
                path += walk_path(level, pk[0], pk[1], r)
                path.append(d)
            yield ("done", path, expanded)
            return
        expanded += 1
        if budget and expanded % budget == 0:
            yield ("think", expanded)
        hcur = f - g
        for b in cells:
            if not boxes[b]:
                continue
            for d in range(4):
                r = b - step[d]
                wd = reach.get(r)
                if wd is None:
                    continue
                res = move(r, boxes, d)
                if res is None:
                    continue
                np_, nb, bf, bt = res
                col = nb[bt] - 1
                dt = dist[col][bt]
                if (dt >= INF and not spare[col]) or frozen(nb, bt):
                    continue
                ng2 = g + wd + 1
                nkey = (np_, nb)
                if best.get(nkey, INF) <= ng2:
                    continue
                if simple:
                    hn = hcur - dist[col][bf] + dt
                else:
                    hn = level.heur(nb)
                    if hn >= INF:
                        continue
                best[nkey] = ng2
                parent[nkey] = (key, r, d)
                tick += 1
                heapq.heappush(heap, (ng2 + hn, -ng2, tick, np_, nb))
    yield ("done", None, expanded)


def solve_now(level, p=None, boxes=None, exact=True):
    for out in solve(level, p, boxes, exact=exact):
        if out[0] == "done":
            return out[1], out[2]


# =============================================================================================
# The seven regions and their forty-two cairns (each designed by hand; the par is the solver's fewest moves)
# =============================================================================================
WORLDS = [
    dict(name="MOSS STEPS", short="MOSS STEPS", sky=((14, 30, 28), (44, 74, 52)), far=(36, 62, 50), near=(24, 46, 38),
         floor=(72, 84, 58), wall=(120, 122, 104), trim=(104, 156, 72), accent=(160, 224, 130), glow=(255, 214, 140),
         intro="Push every stone onto a rune socket. Stones never come back out of a corner."),
    dict(name="QUARRY HALLS", short="QUARRY", sky=((34, 22, 18), (86, 56, 38)), far=(72, 48, 34), near=(52, 34, 26),
         floor=(124, 96, 70), wall=(162, 126, 92), trim=(176, 138, 98), accent=(244, 186, 116), glow=(255, 206, 140),
         intro="Deeper halls, tighter seams: park a stone to free the way, then fetch it."),
    dict(name="FROSTMERE", short="FROSTMERE", sky=((10, 18, 42), (44, 74, 116)), far=(60, 86, 128), near=(36, 56, 92),
         floor=(148, 164, 182), wall=(92, 108, 138), trim=(230, 240, 252), accent=(176, 224, 255), glow=(230, 236, 255),
         intro="Black ice: a stone - and Hesper - slides on until something stops it."),
    dict(name="WINDGATE", short="WINDGATE", sky=((24, 34, 48), (92, 112, 122)), far=(70, 90, 104), near=(48, 64, 78),
         floor=(96, 104, 102), wall=(124, 132, 144), trim=(150, 170, 170), accent=(176, 236, 222), glow=(255, 226, 160),
         intro="Wind tiles: cross them only the way the wind blows - stones too."),
    dict(name="LANTERN VAULT", short="VAULT", sky=((10, 8, 18), (34, 24, 30)), far=(30, 22, 30), near=(20, 14, 22),
         floor=(66, 54, 48), wall=(104, 88, 80), trim=(150, 112, 70), accent=(255, 204, 112), glow=(255, 190, 100),
         intro="A stone on every plate holds the iron gates open."),
    dict(name="RUNE GARDEN", short="GARDEN", sky=((26, 16, 42), (72, 46, 92)), far=(62, 44, 84), near=(40, 30, 58),
         floor=(76, 90, 70), wall=(124, 108, 138), trim=(128, 170, 104), accent=(222, 176, 255), glow=(250, 220, 170),
         intro="Coloured stones belong on sockets of their own colour."),
    dict(name="THE SUMMIT", short="SUMMIT", sky=((10, 12, 32), (150, 110, 140)), far=(84, 80, 126), near=(50, 48, 84),
         floor=(110, 106, 112), wall=(150, 144, 164), trim=(236, 236, 246), accent=(255, 222, 164), glow=(255, 220, 170),
         intro="Ice, wind, plates and colours, all at once. The last cairns."),
]
PER_WORLD = 6

CAIRNS = [   # (region, name, par = the fewest moves, the map)
    # --- MOSS STEPS --------------------------------------------------------------------------------
    (0, 'First Stone', 4, [
        '#########',
        '#       #',
        '# @ $  .#',
        '#       #',
        '#########',
    ]),
    (0, 'The Bend', 11, [
        '#######',
        '#@    #',
        '# ### #',
        '# #.  #',
        '# # $ #',
        '#     #',
        '#######',
    ]),
    (0, 'Mossy Corner', 11, [
        '#######',
        '#. .  #',
        '#  $$ #',
        '## @  #',
        ' #   ##',
        ' #####',
    ]),
    (0, 'Two by Two', 18, [
        '########',
        '#  .   #',
        '# $##$ #',
        '#@  .  #',
        '########',
    ]),
    (0, 'Gatehouse', 26, [
        '#########',
        '#   #   #',
        '# $ . $ #',
        '## #@# ##',
        '# . $ . #',
        '#  $.   #',
        '#       #',
        '#########',
    ]),
    (0, 'Stepping Stones', 37, [
        ' ######',
        '##  . #',
        '# $#$ #',
        '#  @  #',
        '# $#. #',
        '#.    #',
        '#######',
    ]),
    # --- QUARRY HALLS ------------------------------------------------------------------------------
    (1, 'Cutting Floor', 21, [
        ' #######',
        ' #     #',
        '## #$# #',
        '#  . . #',
        '# $#@$ #',
        '#  .   #',
        '########',
    ]),
    (1, 'The Pillars', 28, [
        '#########',
        '#.  #  .#',
        '# $ # $ #',
        '#   @   #',
        '# $ # $ #',
        '#.  #  .#',
        '#########',
    ]),
    (1, 'Narrow Seam', 37, [
        '########',
        '#  #   #',
        '#  $ $ #',
        '## # # #',
        '#. . @ #',
        '########',
    ]),
    (1, 'Block and Tackle', 44, [
        ' #######',
        ' #     ###',
        '## $$    #',
        '#  #. .  #',
        '# @ $ #. #',
        '#    #####',
        '######',
    ]),
    (1, "Foreman's Riddle", 48, [
        '  #######',
        '###  .  #',
        '#  $#$# #',
        '# . @ . #',
        '# #$#$  #',
        '#  .  ###',
        '#######',
    ]),
    (1, 'Sledge Run', 76, [
        '##########',
        '#        #',
        '# $$  $  #',
        '#  ## ## #',
        '## .  .. #',
        ' #  @    #',
        ' #########',
    ]),
    # --- FROSTMERE ---------------------------------------------------------------------------------
    (2, 'First Frost', 9, [
        '###########',
        '#         #',
        '#@ $~~~~. #',
        '#   $     #',
        '#  ~~~~~. #',
        '###########',
    ]),
    (2, 'Skid Marks', 9, [
        '#########',
        '#  ~~~  #',
        '#@ ~~~ .#',
        '#  ~$~  #',
        '#  ~~~  #',
        '#########',
    ]),
    (2, 'Stopper', 11, [
        '##########',
        '#   #    #',
        '# $ ~~~~.#',
        '#   ~~~~ #',
        '#@ $~~~~ #',
        '#    #  .#',
        '##########',
    ]),
    (2, 'Thin Ice', 15, [
        '############',
        '#    #     #',
        '# ~~~~~~~~ #',
        '# ~$~~~~~~.#',
        '# ~~~~$~~~ #',
        '#@   .     #',
        '############',
    ]),
    (2, 'Glacier Pass', 19, [
        '###########',
        '#   #     #',
        '# $ ~~~~~.#',
        '#   ~~#~~ #',
        '#@$ ~~~~~ #',
        '#   ~~~~~.#',
        '##  ####  #',
        ' #.   $   #',
        ' ##########',
    ]),
    (2, 'Frozen Mill', 34, [
        '############',
        '#     #    #',
        '# $~~~~~~$ #',
        '# ~~~##~~~ #',
        '#.~~~  ~~~.#',
        '# ~~~##~~~ #',
        '# $~~~~~~$ #',
        '#@    #   .#',
        '#.         #',
        '############',
    ]),
    # --- WINDGATE ----------------------------------------------------------------------------------
    (3, 'Tailwind', 12, [
        '#########',
        '#   # . #',
        '# $ >   #',
        '#   #   #',
        '## ### ##',
        '#@      #',
        '#########',
    ]),
    (3, 'Draught', 14, [
        '#########',
        '#   v   #',
        '# $ # $ #',
        '#>  @  <#',
        '# . # . #',
        '#   ^   #',
        '#########',
    ]),
    (3, 'Crossdraught', 24, [
        '###########',
        '#    #    #',
        '# $  >  . #',
        '#    #    #',
        '#  $ > $. #',
        '#    #    #',
        '#@.  <    #',
        '#    #    #',
        '###########',
    ]),
    (3, 'Updraft', 37, [
        '##########',
        '# .#..#. #',
        '#  #^^#  #',
        '# $    $ #',
        '## >  < ##',
        '#  $  $  #',
        '#   @    #',
        '##########',
    ]),
    (3, 'Weathervane', 40, [
        '##########',
        '#  #  #  #',
        '# $>  <$ #',
        '#  # .#  #',
        '## #^## ##',
        '#  .@.   #',
        '#  $  $  #',
        '#    .   #',
        '##########',
    ]),
    (3, 'Mill Race', 36, [
        '###########',
        '#    #    #',
        '# $  #  . #',
        '#    >    #',
        '# $  #  . #',
        '#    <    #',
        '#@   #    #',
        '###########',
    ]),
    # --- LANTERN VAULT -----------------------------------------------------------------------------
    (4, 'First Plate', 10, [
        '###########',
        '#    #    #',
        '# $  |  . #',
        '#  $ #    #',
        '#@ _ #    #',
        '###########',
    ]),
    (4, 'Lamplit Hall', 22, [
        '###########',
        '#  _  #   #',
        '# $   | . #',
        '#   $ #   #',
        '#@  $ | . #',
        '#     #   #',
        '###########',
    ]),
    (4, 'Iron Vault', 29, [
        '###########',
        '#    #    #',
        '# $  |  . #',
        '#  _ #    #',
        '# $$ ## ###',
        '# $  |  . #',
        '#@ _ #    #',
        '###########',
    ]),
    (4, 'Counterweight', 37, [
        '##########',
        '#    #   #',
        '# $  _ $ #',
        '#    #   #',
        '#### #|###',
        '#@     . #',
        '##########',
    ]),
    (4, 'Two Keys', 39, [
        '###########',
        '#_   #    #',
        '#  $ |  . #',
        '# $$ #    #',
        '#  $ #  . #',
        '#_ @ #    #',
        '###########',
    ]),
    (4, "Warden's Toll", 59, [
        '############',
        '#     #    #',
        '# $ $ | .  #',
        '#  $  #  . #',
        '##_####    #',
        '#  $  | .  #',
        '#@    #    #',
        '############',
    ]),
    # --- RUNE GARDEN -------------------------------------------------------------------------------
    (5, 'Ember and Moss', 23, [
        '#########',
        '#   #   #',
        '# a   b #',
        '#@  #   #',
        '# B   A #',
        '#########',
    ]),
    (5, 'Crossing', 38, [
        '#########',
        '#   #   #',
        '# a   b #',
        '## # # ##',
        '# B   A #',
        '#   @   #',
        '#########',
    ]),
    (5, 'Garden Knot', 44, [
        '##########',
        '#   ##   #',
        '# a  b c #',
        '#  #  #  #',
        '# C  A B #',
        '#  @     #',
        '##########',
    ]),
    (5, 'Three Hues', 44, [
        '##########',
        '#  A  B  #',
        '# #c##a# #',
        '#    b   #',
        '# #  #   #',
        '#@  C    #',
        '##########',
    ]),
    (5, 'Petal Ring', 49, [
        '###########',
        '#    #    #',
        '# a  B  b #',
        '#  ## ##  #',
        '# A  @  C #',
        '#  ## ##  #',
        '# c  $  . #',
        '#         #',
        '###########',
    ]),
    (5, 'Rune Garden', 68, [
        '############',
        '#    #     #',
        '# a b  c a #',
        '## ## ## # #',
        '#  A  B   C#',
        '#  ##  ## A#',
        '#@    b   B#',
        '############',
    ]),
    # --- THE SUMMIT --------------------------------------------------------------------------------
    (6, 'Frost Gate', 25, [
        '###########',
        '#   #  _  #',
        '# $ ~~~~~ #',
        '#@$ #   # #',
        '#   |  ~~.#',
        '# $ #  ~~.#',
        '#   #     #',
        '###########',
    ]),
    (6, 'Hue Slide', 30, [
        '###########',
        '#   ~~~   #',
        '# a ~~~ B #',
        '#@  ~#~   #',
        '# b ~~~ A #',
        '#   ~~~   #',
        '# c ~~~ C #',
        '#   ~~~   #',
        '###########',
    ]),
    (6, 'Ridge Stair', 37, [
        '############',
        '#@   #  A  #',
        '# a  >  ~  #',
        '#  $ #  ~  #',
        '###_##~~~###',
        '#    |  ~  #',
        '# b  #  B  #',
        '#    <     #',
        '############',
    ]),
    (6, 'Wind and Iron', 41, [
        '###########',
        '#@  #     #',
        '# $ > $ _ #',
        '#   #  #  #',
        '#   <  |  #',
        '# $ #  # .#',
        '#   #  # .#',
        '###########',
    ]),
    (6, 'Coloured Wind', 46, [
        '###########',
        '#    #    #',
        '# a  >  A #',
        '#    #    #',
        '# b  >  B #',
        '#    #    #',
        '#@ $ <  . #',
        '#    #    #',
        '###########',
    ]),
    (6, 'Summit Cairn', 47, [
        '############',
        '#@   #   A #',
        '# a  >  ~~ #',
        '#  $ #  ~~ #',
        '## _### ####',
        '#  b |  ~~B#',
        '#    #  ~~ #',
        '# c  >    C#',
        '############',
    ]),
]
LEVELS = [Level(rows, name, w, i) for i, (w, name, par, rows) in enumerate(CAIRNS)]
PARS = [c[2] for c in CAIRNS]
SOLUTIONS = {}                      # cairn -> the solver's directions, filled the first time it is solved


def label(i):
    return "%d-%d" % (i // PER_WORLD + 1, i % PER_WORLD + 1)


# =============================================================================================
# Sound: stone, wood and a little bell
# =============================================================================================
def _arp(fs, d=0.05, v=0.3, w="tri", last=0.18):
    out = [dict(w=w, f=f, d=d, v=v) for f in fs[:-1]]
    return out + [dict(w=w, f=fs[-1], d=last, v=v, vib=(6, 0.15))]


def _bell(f, v=0.26):
    return [dict(w="sine", f=f, d=0.5, v=v), dict(w="sine", f=f * 2.01, d=0.3, v=v * 0.35, at=0),
            dict(w="tri", f=f * 3.0, d=0.12, v=v * 0.2, at=0)]


SND = Sound(GAME, {
    "step": [dict(w="noise", f=1400, f2=900, d=0.025, v=0.07)],
    "push": [dict(w="noise", f=420, f2=260, d=0.09, v=0.24), dict(w="tri", f=110, f2=92, d=0.08, v=0.18, at=0)],
    "slide": [dict(w="noise", f=5200, f2=2600, d=0.22, v=0.12, r="lin"), dict(w="sine", f=1320, f2=990, d=0.2, v=0.05, at=0)],
    "skate": [dict(w="noise", f=6000, f2=3800, d=0.12, v=0.07, r="lin")],
    "bump": [dict(w="tri", f=140, f2=90, d=0.06, v=0.2)],
    "socket0": _bell(784), "socket1": _bell(880), "socket2": _bell(988), "socket3": _bell(1175),
    "off": [dict(w="tri", f=520, f2=380, d=0.08, v=0.14)],
    "gate": [dict(w="square", f=196, f2=180, d=0.12, v=0.14, duty=0.3), dict(w="noise", f=2400, f2=800, d=0.14, v=0.12, at=0),
             dict(w="square", f=262, d=0.06, v=0.1, duty=0.3)],
    "plate": [dict(w="square", f=660, d=0.03, v=0.12, duty=0.25), dict(w="tri", f=330, d=0.05, v=0.14)],
    "wind": [dict(w="noise", f=900, f2=2400, d=0.16, v=0.08, r="lin")],
    "undo": [dict(w="tri", f=660, f2=440, d=0.05, v=0.14)],
    "restart": [dict(w="tri", f=523, f2=262, d=0.16, v=0.2)],
    "solved": [dict(w="tri", f=f, d=0.08, v=0.3) for f in (523, 659, 784, 1047, 784, 1047)] +
              [dict(w="tri", f=1319, d=0.5, v=0.32, vib=(6, 0.2), r="lin")] + _bell(1568, 0.16),
    "par": _arp([1047, 1319, 1568, 2093], 0.06, 0.24, "square", 0.3),
    "world": [dict(w="tri", f=f, d=0.12, v=0.3) for f in (392, 523, 659, 784)] +
             [dict(w="tri", f=1047, d=0.7, v=0.32, vib=(5, 0.2), r="lin")],
    "menu": [dict(w="tri", f=660, d=0.025, v=0.2)],
    "locked": [dict(w="tri", f=220, f2=180, d=0.08, v=0.2)],
    "start": [dict(w="tri", f=523, d=0.06, v=0.3), dict(w="tri", f=784, d=0.06, v=0.3), dict(w="tri", f=1047, d=0.16, v=0.3)],
    "pause": [dict(w="tri", f=523, f2=392, d=0.07, v=0.22)],
    "sound_on": [dict(w="tri", f=440, d=0.06, v=0.35), dict(w="tri", f=880, d=0.12, v=0.35)],
})


def help_lines(kitty=True):
    hold = ("Hold a direction to keep walking (key releases on)." if kitty else
            "Hold a direction to keep walking (key repeat).")
    return ["CAIRNWARD - keys", "",
            "Arrows / WASD     walk; push the stone ahead of you",
            "U  Z  Backspace   undo a move (hold to rewind)",
            "R                 restart (undo brings it back)",
            "[  ]              previous / next open cairn",
            "Esc / P           pause (Q there: leave the cairn)",
            "?                 this help", "",
            "Push every stone onto a rune socket. You can only",
            "push, never pull, and one stone at a time. A slide",
            "on ice is one move. Par: the solver's fewest moves.",
            "Black ice   stones and you slide until stopped",
            "Wind tile   cross it only the way the arrows point",
            "Plate       stones on all plates open the gates",
            "Colours     ember, moss, sky: each to its own socket", "",
            hold,
            "Auto mode: the solver thinks, then walks its line."]


# =============================================================================================
# Progress: the best moves of every cairn live in the shared score file
# =============================================================================================
def key_of(i):
    return "c%02d" % (i + 1)


def progress():
    rec = load_scores().get(GAME, {})
    return {i: rec[key_of(i)] for i in range(len(LEVELS)) if isinstance(rec.get(key_of(i)), int)}


def is_open(i, prog):
    """Solved cairns and the first three unsolved ones are open."""
    if i in prog:
        return True
    return sum(1 for j in range(i) if j not in prog) < 3


def first_open(prog):
    for i in range(len(LEVELS)):
        if i not in prog:
            return i
    return 0


_PROG = [None]


def progress_cache(refresh=False):
    """progress(), read from the score file once and again after every record."""
    if refresh or _PROG[0] is None:
        _PROG[0] = progress()
    return _PROG[0]


def record(i, moves):
    """Store the best moves of cairn i and the totals. Returns True for a new best."""
    new = submit(GAME, key_of(i), moves, lower_is_better=True)
    prog = progress_cache(True)
    submit(GAME, "solved", len(prog))
    submit(GAME, "par", sum(1 for j, m in prog.items() if m <= PARS[j]))
    return new


# =============================================================================================
# One cairn in play: the rules above, plus undo, counters and the animation of each step
# =============================================================================================
STEP_T = 0.095                      # seconds for one step
SLIDE_T = 0.045                     # and for every further cell of a slide


def ease(t):
    t = clamp(t, 0.0, 1.0)
    return 1 - (1 - t) * (1 - t)


class Game:
    def __init__(self, index, quiet=False, demo=False):
        self.index = index
        self.level = LEVELS[index]
        self.world = self.level.world
        self.quiet, self.demo = quiet, demo
        self.rnd = random.Random(index * 7 + 1)
        self.history = []
        self.paused = self.help = False
        self.clock = 0.0
        self.parts = []
        self.reset()
        self.intro_t = 0.0

    def snd(self, name, vol=1.0):
        if not self.quiet:
            SND.play(name, vol)

    def reset(self):
        lv = self.level
        self.p, self.boxes = lv.player0, lv.boxes0
        self.moves = self.pushes = 0
        self.facing = DOWN
        self.anim = None
        self.queue = []
        self.solved = False
        self.solved_t = 0.0
        self.walk = 0
        self.bump = None

    # --- input -----------------------------------------------------------------------------
    def press(self, d, repeat=False):
        """A direction key; while a step is still animating, the next one waits."""
        if self.solved:
            return
        if self.anim or self.queue:
            if not self.queue:          # one step waits in line (more would overshoot when a held key repeats)
                self.queue.append(d)
            return
        self.go(d)

    def go(self, d):
        lv = self.level
        self.facing = d
        res = lv.move(self.p, self.boxes, d)
        if res is None:
            self.bump = [d, 0.0]
            self.snd("bump", 0.6)
            return False
        np_, nb, bf, bt = res
        self.history.append((self.p, self.boxes, self.moves, self.pushes, self.facing))
        gates0 = lv.gates_open(self.boxes)
        op = self.p
        self.p, old = np_, self.boxes
        self.boxes = nb
        self.moves += 1
        self.walk += 1
        s = lv.step[d]
        pd = (np_ - op) // s
        bd = (bt - bf) // s if bf >= 0 else 0
        dur = STEP_T + SLIDE_T * max(0, max(pd, bd) - 1)
        self.anim = dict(p0=op, p1=np_, b0=bf, b1=bt, col=nb[bt] if bf >= 0 else 0, t=0.0, dur=dur, d=d,
                         pd=pd, bd=bd)
        if bf >= 0:
            self.pushes += 1
            self.snd("slide" if bd > 1 else "push", 0.8)
            if lv.tcol[bt] != NONE and lv.tcol[bt] + 1 == nb[bt]:
                self.anim["chime"] = True
            elif lv.tcol[bf] != NONE and lv.tcol[bf] + 1 == old[bf]:
                self.snd("off", 0.5)
            if bt in lv.plates or bf in lv.plates:
                self.snd("plate", 0.6)
        else:
            self.snd("skate" if pd > 1 else "step", 0.6 if pd > 1 else 0.35)
        if lv.oneway[np_] != NONE:
            self.snd("wind", 0.5)
        if lv.plates and lv.gates_open(nb) != gates0:
            self.snd("gate", 0.7)
        if lv.solved(nb):
            self.solved = True
            self.queue = []
        return True

    def undo(self):
        if not self.history:
            return False
        self.p, self.boxes, self.moves, self.pushes, self.facing = self.history.pop()
        self.anim = None
        self.queue = []
        self.solved = False
        self.solved_t = 0.0
        self.snd("undo", 0.6)
        return True

    def restart(self):
        if self.moves == 0 and self.p == self.level.player0:
            return
        self.history.append((self.p, self.boxes, self.moves, self.pushes, self.facing))
        hist = self.history
        self.reset()
        self.history = hist
        self.snd("restart", 0.6)

    @property
    def busy(self):
        return self.anim is not None or bool(self.queue)

    # --- time --------------------------------------------------------------------------------------
    def update(self, dt):
        self.clock += dt
        self.intro_t += dt
        if self.bump:
            self.bump[1] += dt
            if self.bump[1] > 0.14:
                self.bump = None
        a = self.anim
        if a:
            a["t"] += dt
            if a["b0"] >= 0 and a["bd"] > 1:
                self.trail(a)
            if a["t"] >= a["dur"]:
                self.land(a)
                self.anim = None
                if self.queue and not self.solved:
                    self.go(self.queue.pop(0))
        if self.solved and not self.anim:
            if self.solved_t == 0.0:
                self.celebrate()
            self.solved_t += dt
        for pt in self.parts:
            pt[4] += dt
            pt[0] += pt[2] * dt
            pt[1] += pt[3] * dt
            pt[3] += pt[7] * dt
        self.parts = [pt for pt in self.parts if pt[4] < pt[5]]

    def xy(self, i):
        return i % self.level.w, i // self.level.w

    def land(self, a):
        if a["b0"] < 0:
            return
        x, y = self.xy(a["b1"])
        dx, dy = DXY[a["d"]]
        for _ in range(6):     # dust where the stone stops
            self.parts.append([x + 0.5 + dx * 0.4 + self.rnd.uniform(-0.3, 0.3), y + 0.85, self.rnd.uniform(-1.2, 1.2) - dx,
                               self.rnd.uniform(-1.4, -0.3), 0.0, self.rnd.uniform(0.25, 0.5), (150, 140, 124), 2.0])
        if a.get("chime"):
            c = a["col"] - 1
            self.snd("socket%d" % c, 0.8)
            col = COLOURS[c] if c else SOCKET
            for k in range(14):
                ang = k / 14 * 2 * math.pi
                sp = self.rnd.uniform(1.6, 3.0)
                self.parts.append([x + 0.5, y + 0.5, math.cos(ang) * sp, math.sin(ang) * sp - 0.8, 0.0,
                                   self.rnd.uniform(0.4, 0.8), mix(col, WHITE, 0.4), 3.0])

    def trail(self, a):
        if self.rnd.random() < 0.5:
            f = ease(a["t"] / a["dur"])
            x0, y0 = self.xy(a["b0"])
            x1, y1 = self.xy(a["b1"])
            x, y = x0 + (x1 - x0) * f, y0 + (y1 - y0) * f
            self.parts.append([x + 0.5 + self.rnd.uniform(-0.3, 0.3), y + 0.5 + self.rnd.uniform(-0.3, 0.3), 0.0, -0.4, 0.0,
                               0.35, (220, 240, 255), 0.0])

    def celebrate(self):
        self.snd("solved")
        lv = self.level
        for t in lv.targets:
            x, y = self.xy(t)
            c = lv.tcol[t]
            col = COLOURS[c] if c else SOCKET
            for k in range(10):
                self.parts.append([x + 0.5, y + 0.5, self.rnd.uniform(-1.5, 1.5), self.rnd.uniform(-4.5, -2.0), 0.0,
                                   self.rnd.uniform(0.7, 1.3), mix(col, WHITE, 0.3), 5.0])

    # --- where things are drawn (in cells, fractional while moving) ------------------------------------
    def player_pos(self):
        a = self.anim
        if a:
            k = a["t"] / (STEP_T + SLIDE_T * max(0, a["pd"] - 1))
            f = ease(k) if a["pd"] > 1 else clamp(k, 0.0, 1.0)
            x0, y0 = self.xy(a["p0"])
            x1, y1 = self.xy(a["p1"])
            return x0 + (x1 - x0) * f, y0 + (y1 - y0) * f
        x, y = self.xy(self.p)
        if self.bump:
            dx, dy = DXY[self.bump[0]]
            k = math.sin(self.bump[1] / 0.14 * math.pi) * 0.12
            return x + dx * k, y + dy * k
        return x, y

    def moving_box(self):
        """(cell it is going to, x, y) of the stone being pushed, or None."""
        a = self.anim
        if not a or a["b0"] < 0:
            return None
        if a["bd"] > 1:
            f = ease(a["t"] / a["dur"])
        else:
            f = clamp(a["t"] / STEP_T, 0.0, 1.0)
        x0, y0 = self.xy(a["b0"])
        x1, y1 = self.xy(a["b1"])
        return a["b1"], x0 + (x1 - x0) * f, y0 + (y1 - y0) * f


# =============================================================================================
# Drawing: every cairn is drawn at the window's own resolution - a bigger window gives finer stones
# =============================================================================================
def hsh(x, y, s=0):
    h = (x * 374761393 + y * 668265263 + s * 2147483647) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    return (h ^ (h >> 16)) & 0xFFFF


HUD_BG = (14, 12, 22)
HUD_FG = (214, 214, 230)
HUD_DIM = (140, 144, 176)
GOLD = (250, 214, 120)
ICE = (126, 178, 214)
IRON = (70, 74, 86)
BRASS = (196, 156, 82)
INK = (12, 10, 18)


def layout(level, cols, rows, hud=True):
    """(T, ox, oy): the size of a cell in pixels and the top-left pixel of the cairn."""
    top = bot = 1 if hud else 0
    aw, ah = cols, (rows - top - bot) * 2
    T = max(1, min((aw - 2) // level.w, (ah - 2) // level.h))
    ox = (cols - T * level.w) // 2
    oy = top * 2 + (ah - T * level.h) // 2
    return T, ox, oy


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
                if d > r0:
                    a = 1 - (d - r0) / span
                    a = a * a * k
                    o = row[px]
                    row[px] = (int(o[0] + (c[0] - o[0]) * a), int(o[1] + (c[1] - o[1]) * a), int(o[2] + (c[2] - o[2]) * a))


def darken(cv, x, y, w, h, k):
    for yy in range(max(0, y), min(cv.H, y + h)):
        row = cv.px[yy]
        for xx in range(max(0, x), min(cv.W, x + w)):
            o = row[xx]
            row[xx] = (int(o[0] * k), int(o[1] * k), int(o[2] * k))


# --- the landscape behind the cairn -------------------------------------------------------------------
_BG = {}


def backdrop(world, cols, rows):
    key = (world, cols, rows)
    bg = _BG.get(key)
    if bg is not None:
        return bg
    wd = WORLDS[world]
    W, H = cols, rows * 2
    top, bot = wd["sky"]
    px = [[mix(top, bot, (y / max(1, H - 1)) ** 1.3)] * W for y in range(H)]
    px = [row[:] for row in px]
    rnd = random.Random(world * 31 + 7)
    if world in (2, 6, 4):        # stars over the frost, the summit and in the vault's dark
        for _ in range(W * H // (70 if world != 4 else 150)):
            x, y = rnd.randrange(W), rnd.randrange(int(H * 0.7))
            px[y][x] = mix(px[y][x], (255, 250, 236) if world != 4 else (200, 150, 90), rnd.uniform(0.2, 0.8) ** 2)
    if world == 6:                # dawn behind the summit
        cx, cy = W * 0.72, H * 0.78
        for y in range(H):
            for x in range(W):
                d = math.hypot((x - cx) / max(1, W * 0.5), (y - cy) / max(1, H * 0.6))
                if d < 1:
                    px[y][x] = mix(px[y][x], (255, 190, 150), (1 - d) ** 2 * 0.55)
    # two ranges of mountains (or hills, or vault arches), the far one paler
    for layer, (col, base, amp, seed) in enumerate(((wd["far"], 0.55, 0.26, 3), (wd["near"], 0.76, 0.18, 9))):
        r2 = random.Random(world * 13 + seed)
        ph = [r2.uniform(0, 6.3) for _ in range(3)]
        for x in range(W):
            u = x / max(1, W)
            if world == 4:        # vault: rows of arches
                k = (u * 7 + layer * 0.5) % 1.0
                hgt = base - amp * 0.7 * math.sqrt(max(0.0, 1 - (2 * k - 1) ** 2))
            else:
                hgt = base - amp * (0.5 + 0.28 * math.sin(u * 7.0 + ph[0]) + 0.16 * math.sin(u * 17 + ph[1]) +
                                    0.08 * math.sin(u * 41 + ph[2]))
                if world in (0, 5):
                    hgt += amp * 0.25
            y0 = int(hgt * H)
            for y in range(max(0, y0), H):
                c = mix(col, shade(col, 0.7), (y - y0) / max(1, H - y0))
                if world in (2, 6) and y - y0 < max(1, H // 40) + (hsh(x, layer) & 1):   # snow on the ridge
                    c = mix(c, (236, 240, 250), 0.6 if layer == 0 else 0.45)
                px[y][x] = c
    if world in (0, 5):           # fireflies and petals
        for _ in range(W * H // 120):
            x, y = rnd.randrange(W), rnd.randrange(H)
            px[y][x] = mix(px[y][x], wd["accent"], 0.5)
    _BG[key] = px
    return px


# --- the static cairn: rock, floor, sockets, ice, wind grooves ------------------------------------------
_STATIC = {}


def wall_vis(lv):
    """Rock cells that touch the inside (the rest is landscape)."""
    vis = bytearray(lv.n)
    w = lv.w
    for i in range(lv.n):
        if lv.wall[i]:
            x, y = i % w, i // w
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    xx, yy = x + dx, y + dy
                    if 0 <= xx < w and 0 <= yy < lv.h and lv.inside[yy * w + xx]:
                        vis[i] = 1
    return vis


def static_layer(lv, T, ox, oy, cols, rows):
    key = (lv.index, lv.name, T, ox, oy, cols, rows)
    st = _STATIC.get(key)
    if st is not None:
        return st
    if len(_STATIC) > 24:
        _STATIC.clear()
    wd = WORLDS[lv.world]
    px = [row[:] for row in backdrop(lv.world, cols, rows)]
    W, H = cols, rows * 2
    vis = wall_vis(lv)
    w = lv.w
    floor = wd["floor"]
    # the cairn's shadow on the landscape
    sh = max(1, T // 3)
    for i in range(lv.n):
        if vis[i] or lv.inside[i]:
            x0, y0 = ox + (i % w) * T + sh, oy + (i // w) * T + sh
            for y in range(max(0, y0), min(H, y0 + T)):
                row = px[y]
                for x in range(max(0, x0), min(W, x0 + T)):
                    o = row[x]
                    row[x] = (o[0] * 5 // 8, o[1] * 5 // 8, o[2] * 5 // 8)
    for i in range(lv.n):
        x0, y0 = ox + (i % w) * T, oy + (i // w) * T
        cx, cy = i % w, i // w
        if vis[i]:
            below = i + w
            front = below >= lv.n or not lv.wall[below] or not vis[below]
            above_open = i - w < 0 or not lv.wall[i - w]
            draw_rock(px, x0, y0, T, wd, cx, cy, front, above_open, lv.world)
        elif lv.inside[i]:
            if lv.ice[i]:
                draw_ice(px, x0, y0, T, cx, cy, lv, i)
            else:
                draw_floor(px, x0, y0, T, mix(shade(floor, 0.8), wd["accent"], 0.12) if lv.oneway[i] != NONE else floor,
                           cx, cy)
    # soft shadows of the rock on the floor (top and left edges)
    if T >= 3:
        for i in range(lv.n):
            if not lv.inside[i]:
                continue
            x0, y0 = ox + (i % w) * T, oy + (i // w) * T
            if lv.wall[i - w]:
                hh = max(1, T * 2 // 5)
                for v in range(hh):
                    k = 0.55 + 0.45 * v / hh
                    y = y0 + v
                    if 0 <= y < H:
                        row = px[y]
                        for x in range(max(0, x0), min(W, x0 + T)):
                            o = row[x]
                            row[x] = (int(o[0] * k), int(o[1] * k), int(o[2] * k))
            if lv.wall[i - 1]:
                ww = max(1, T // 4)
                for u in range(ww):
                    k = 0.7 + 0.3 * u / ww
                    x = x0 + u
                    for y in range(max(0, y0), min(H, y0 + T)):
                        o = px[y][x]
                        px[y][x] = (int(o[0] * k), int(o[1] * k), int(o[2] * k))
    for t in lv.targets:
        draw_socket(px, ox + (t % w) * T, oy + (t // w) * T, T, lv.tcol[t], wd)
    for i in range(lv.n):
        if lv.oneway[i] != NONE:
            draw_grooves(px, ox + (i % w) * T, oy + (i // w) * T, T, lv.oneway[i], wd)
    _STATIC[key] = px
    return px


def draw_floor(px, x0, y0, T, base, cx, cy):
    tint = ((hsh(cx, cy, 3) % 17) - 8) / 100.0
    c = shade(base, 1 + tint)
    grout = shade(base, 0.66)
    hi = mix(c, WHITE, 0.12)
    lo = shade(c, 0.88)
    edge = T >= 6
    for v in range(T):
        row = px[y0 + v]
        for u in range(T):
            if edge and (u == 0 or v == 0):
                col = grout
            elif edge and (u == 1 or v == 1):
                col = hi
            elif edge and (u == T - 1 or v == T - 1):
                col = lo
            else:
                n = hsh(x0 + u, y0 + v, 11) & 31
                col = c if n > 4 else (shade(c, 0.9) if n > 1 else mix(c, WHITE, 0.15))
            row[x0 + u] = col
    if T >= 9 and hsh(cx, cy, 5) % 3 == 0:     # a hairline crack
        x, y = x0 + 2 + hsh(cx, cy, 6) % (T - 4), y0 + 2
        for k in range(T // 2):
            if y0 < y < y0 + T - 1 and x0 < x < x0 + T - 1:
                px[y][x] = shade(c, 0.78)
            y += 1
            x += (hsh(cx, cy, 20 + k) % 3) - 1


def draw_rock(px, x0, y0, T, wd, cx, cy, front, above_open, world):
    wcol = wd["wall"]
    tint = ((hsh(cx, cy, 8) % 15) - 7) / 100.0
    topc = shade(wcol, 1.06 + tint)
    face_h = max(1, (T * 3) // 10) if front and T >= 3 else 0
    topk = T - face_h
    seam = shade(wcol, 0.58)
    for v in range(T):
        row = px[y0 + v]
        for u in range(T):
            if v >= topk:       # the front face, in shadow, with brick seams
                fv = (v - topk) / max(1, face_h)
                col = shade(wcol, 0.66 - 0.18 * fv)
                if T >= 8 and (v == topk or (u + (cy & 1) * (T // 2)) % max(2, T // 2) == 0):
                    col = shade(wcol, 0.5)
            else:
                n = hsh(x0 + u, y0 + v, 17) & 31
                col = topc if n > 5 else (shade(topc, 0.9) if n > 2 else mix(topc, WHITE, 0.12))
                if T >= 5:
                    if u == 0 or v == 0:
                        col = seam if T >= 7 else shade(topc, 0.85)
                    elif u == 1 or v == 1:
                        col = mix(topc, WHITE, 0.22)
                    elif u == T - 1 or v == topk - 1:
                        col = shade(topc, 0.78)
                # region trims: moss, strata, snow caps, vines
                if world in (0, 5) and T >= 4 and (hsh(cx * 9 + u // 2, cy * 7 + v // 2, 31) & 15) < (3 if v < topk // 2 else 1):
                    col = mix(col, wd["trim"], 0.75)
                elif world == 1 and T >= 6 and (v + (hsh(cx, cy) & 3)) % max(3, T // 3) == 0:
                    col = shade(col, 0.9)
                elif world in (2, 6) and above_open and v < max(1, T // 4) + ((hsh(x0 + u, cy, 2) & 1) if T >= 6 else 0):
                    col = mix(col, wd["trim"], 0.8)
            row[x0 + u] = col


def draw_ice(px, x0, y0, T, cx, cy, lv, i):
    base = shade(ICE, 0.92 + ((hsh(cx, cy, 4) % 9) / 100.0))
    rim = mix(base, WHITE, 0.45)
    ph = hsh(cx, cy, 9) % max(1, T)
    for v in range(T):
        row = px[y0 + v]
        for u in range(T):
            col = mix(base, (70, 110, 160), v / max(1, T) * 0.35)
            k = (u - v + ph) % max(4, T)
            if T >= 4 and k < max(1, T // 6):
                col = mix(col, WHITE, 0.35)
            if T >= 6 and ((u == 0 and not lv.ice[i - 1]) or (v == 0 and not lv.ice[i - lv.w])):
                col = rim
            row[x0 + u] = col
    if T >= 8:                                   # a few sparkles frozen in
        for k in range(2):
            u, v = 1 + hsh(cx, cy, 40 + k) % (T - 2), 1 + hsh(cx, cy, 50 + k) % (T - 2)
            px[y0 + v][x0 + u] = WHITE


SOCKET = (246, 204, 116)              # plain sockets glow gold in every region


def draw_socket(px, x0, y0, T, col, wd):
    tint = COLOURS[col] if col else SOCKET
    if T < 4:
        c = mix(px[y0][x0], tint, 0.8)
        for v in range(T):
            for u in range(T):
                px[y0 + v][x0 + u] = c
        return
    cx, cy = x0 + T / 2, y0 + T / 2
    R = T * 0.36
    th = max(0.9, T * 0.1)
    groove = mix(shade(px[int(cy)][int(cx)], 0.55), tint, 0.35)
    ring = mix(tint, WHITE, 0.15)
    for v in range(T):
        row = px[y0 + v]
        for u in range(T):
            dx, dy = x0 + u + 0.5 - cx, y0 + v + 0.5 - cy
            d = math.sqrt(dx * dx + dy * dy)
            if abs(d - R) <= th:
                row[x0 + u] = ring if (dy < 0 or abs(d - R) < th * 0.5) else mix(ring, groove, 0.5)
            elif abs(d - R) <= th + 1 and d > R:
                row[x0 + u] = groove
            elif d < R * 0.32:
                row[x0 + u] = mix(groove, tint, 0.5)
    if T >= 10:                                  # four rune ticks around the ring
        for a in range(4):
            ang = a * math.pi / 2 + math.pi / 4
            for r in (R + th + 1, R + th + 2):
                x, y = int(cx + math.cos(ang) * r), int(cy + math.sin(ang) * r)
                if x0 <= x < x0 + T and y0 <= y < y0 + T:
                    px[y][x] = mix(tint, groove, 0.4)


def draw_grooves(px, x0, y0, T, d, wd):
    """The worn channels of a wind tile (the moving chevrons are drawn every frame)."""
    if T < 4:
        return
    dark = shade(wd["floor"], 0.66)
    for k in range(T):
        for off in (T // 4, T - 1 - T // 4):
            if d in (LEFT, RIGHT):
                px[y0 + off][x0 + k] = dark
            else:
                px[y0 + k][x0 + off] = dark


# --- stones -------------------------------------------------------------------------------------------
RUNES = (["..#..", ".###.", "..#..", ".#.#.", "#...#"],        # plain: a little cairn man
         ["..#..", ".##..", ".#.#.", "#.#.#", ".###."],        # ember: a flame
         ["...##", "..###", ".##.#", "##.#.", "#...."],        # moss: a leaf
         [".###.", "#...#", "..###", ".#...", "..##."])        # sky: a swirl
_STONE = {}


def stone_img(col, lit, T, wd_glow):
    """A carved waystone of T x T pixels: rounded block, top light, a darker front face, an engraved rune that
    glows while the stone sits on its own socket. None = transparent."""
    key = (col, lit, T, wd_glow)
    img = _STONE.get(key)
    if img is not None:
        return img
    base = COLOURS[col]
    img = [[None] * T for _ in range(T)]
    if T <= 2:
        for v in range(T):
            for u in range(T):
                img[v][u] = mix(base, WHITE, 0.3) if lit else base
        _STONE[key] = img
        return img
    m = 0 if T < 6 else max(1, T // 12)
    r = T * 0.22 if T >= 5 else 0.6
    face = max(1, (T * 22) // 100)
    lo, hi = m, T - m
    for v in range(lo, hi):
        for u in range(lo, hi):
            # rounded corners
            cxr = min(u - lo + 0.5, hi - u - 0.5)
            cyr = min(v - lo + 0.5, hi - v - 0.5)
            if cxr < r and cyr < r and (r - cxr) ** 2 + (r - cyr) ** 2 > r * r:
                continue
            fy = (v - lo) / max(1, hi - lo - 1)
            fx = (u - lo) / max(1, hi - lo - 1)
            if v >= hi - face:
                c = shade(base, 0.62 - 0.12 * (v - (hi - face)) / max(1, face))
            else:
                c = shade(base, 1.08 - 0.22 * (fx * 0.5 + fy))
                if v == lo or u == lo:
                    c = mix(c, WHITE, 0.35)
                elif u == hi - 1:
                    c = shade(c, 0.8)
                elif T >= 8 and (hsh(u, v, col * 7 + 3) & 15) == 0:
                    c = shade(c, 0.9)
            img[v][u] = c
    if 4 <= T < 8:                               # too small for a rune: a single carved notch
        y = lo + max(1, (hi - face - lo) // 2) - 1
        for u in range(T // 2 - 1, T // 2 + (T >= 6)):
            if img[y][u] is not None:
                img[y][u] = mix(wd_glow if not col else COLOURS[col], WHITE, 0.6) if lit else shade(base, 0.5)
    elif T >= 8:
        g = max(3, int((hi - lo - face) * 0.62))
        rune = scale_art([list(rw) for rw in RUNES[col]], g, g)
        gx = (T - g) // 2
        gy = lo + max(0, (hi - face - lo - g) // 2)
        ink = mix(wd_glow if not col else COLOURS[col], WHITE, 0.55) if lit else shade(base, 0.48)
        for v in range(g):
            for u in range(g):
                if rune[v][u] == "#" and img[gy + v][gx + u] is not None:
                    img[gy + v][gx + u] = ink
                    if not lit and gy + v + 1 < T and img[gy + v + 1][gx + u] is not None and \
                            (v + 1 >= g or rune[v + 1][u] != "#"):
                        img[gy + v + 1][gx + u] = mix(shade(base, 1.0), WHITE, 0.25)    # the cut catches light
    _STONE[key] = img
    return img


def blit_img(cv, img, x0, y0):
    W, H = cv.W, cv.H
    for v, row in enumerate(img):
        y = y0 + v
        if 0 <= y < H:
            prow = cv.px[y]
            for u, c in enumerate(row):
                if c is not None:
                    x = x0 + u
                    if 0 <= x < W:
                        prow[x] = c


# --- Hesper the badger ----------------------------------------------------------------------------------
BADGER = {
    "front": ["..dd..dd..", ".wkkwwkkw.", ".wkkwwkkw.", ".wkewwekw.", "..kkwwkk..", "...wnnw...",
              "..rrrrrr..", ".ggrrggggl", ".gggggggyl", "..dd..dd.."],
    "side": ["....dd....", "...dwwww..", "..dkkkkww.", "..gkekkkwn", ".ggwwwwww.", "gggrrrrr..",
             "gggrrgggyl", "gggggggg.l", ".gggggg...", ".dd...dd.."],
    "back": ["..dd..dd..", ".dggwwggd.", ".gggwwggg.", ".gggwwggg.", ".gggggggg.", "..rrrrrr..",
             ".gggrrgggl", ".gggggggyl", ".gggggggg.", "..dd..dd.."],
}
BADGER_PAL = {"d": (64, 60, 70), "k": (30, 28, 34), "w": (238, 234, 226), "e": (250, 250, 250), "n": (40, 30, 34),
              "g": (132, 128, 138), "r": (196, 72, 58), "y": (160, 120, 60), "l": (255, 222, 130)}
_SPR = {}


def badger_runs(view, frame, w, h, flip):
    key = (view, frame, w, h, flip)
    sp = _SPR.get(key)
    if sp is not None:
        return sp
    rows = list(BADGER[view])
    if frame:
        rows[-1] = ".dd....dd." if view != "side" else "..dd.dd..."
    grid = [list(r[::-1] if flip else r) for r in rows]
    g = scale_art(grid, w, h)
    img = [[None] * (w + 2) for _ in range(h + 2)]
    for y in range(h):
        for x in range(w):
            ch = g[y][x]
            if ch == ".":
                continue
            c = BADGER_PAL[ch]
            if ch in "gd" and (y == 0 or g[y - 1][x] == "."):
                c = mix(c, WHITE, 0.3)
            elif ch == "g" and (y == h - 1 or g[y + 1][x] == "." or x == 0 or g[y][x - 1] == "."):
                c = shade(c, 0.72)
            img[y + 1][x + 1] = c
    if w >= 6:
        for y in range(h + 2):
            for x in range(w + 2):
                if img[y][x] is None and any(0 <= x + dx < w + 2 and 0 <= y + dy < h + 2 and img[y + dy][x + dx] not in (None, 0)
                                              for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    img[y][x] = 0
    runs = [(x, y, INK if c == 0 else c) for y, row in enumerate(img) for x, c in enumerate(row) if c is not None]
    _SPR[key] = runs
    return runs


def draw_badger(cv, g, x0, y0, T):
    """Hesper at pixel (x0, y0) for a cell of T pixels."""
    d = g.facing
    view = "front" if d == DOWN else "back" if d == UP else "side"
    flip = d == LEFT
    moving = g.anim is not None
    frame = (g.walk & 1) if moving else 0
    if T <= 3:
        c = (236, 232, 226)
        cv.rect(x0, y0, T, T, (120, 116, 126))
        cv.set(x0 + T // 2, y0, c)
        return
    w = max(4, T - (2 if T >= 8 else 0))
    h = max(4, T - (1 if T >= 8 else 0))
    bob = -1 if moving and T >= 8 and g.anim and g.anim["t"] < g.anim["dur"] * 0.5 else 0
    ox, oy = x0 + (T - w) // 2 - 1, y0 + (T - h) - 1 + bob
    # a soft shadow under her feet
    if T >= 6:
        for u in range(w // 5, w - w // 5):
            blend(cv, ox + 1 + u, y0 + T - 1, INK, 0.45)
    W, H = cv.W, cv.H
    for (x, y, c) in badger_runs(view, frame, w, h, flip):
        xx, yy = ox + x, oy + y
        if 0 <= xx < W and 0 <= yy < H:
            cv.px[yy][xx] = c


# --- moving details: wind, plates, gates -------------------------------------------------------------------
def draw_wind(cv, x0, y0, T, d, t, wd):
    """Chevrons streaming the way the wind blows."""
    col = wd["accent"]
    if T < 4:
        cv.set(x0 + T // 2, y0 + T // 2, col)
        return
    dx, dy = DXY[d]
    n = 2 if T >= 10 else 1
    arm = max(1, int(T * 0.28))
    thick = 2 if T >= 6 else 1
    for k in range(n):
        f = (t * 1.4 + k / n) % 1.0
        a = 0.45 + 0.55 * math.sin(f * math.pi) if n > 1 else 0.6 + 0.4 * math.sin(t * 5)
        off = (f - 0.5) * T * 0.7 if n > 1 else T * 0.1
        cx = x0 + T / 2 + dx * off
        cy = y0 + T / 2 + dy * off
        for j in range(-arm, arm + 1):
            for th in range(thick):
                back = abs(j) + th
                x = int(math.floor(cx - dx * back + (j if dy else 0)))
                y = int(math.floor(cy - dy * back + (j if dx else 0)))
                if x0 <= x < x0 + T and y0 <= y < y0 + T:
                    blend(cv, x, y, col, a * (1.0 if th == 0 else 0.55))


def draw_plate(cv, x0, y0, T, pressed, t, wd):
    if T < 3:
        cv.set(x0 + T // 2, y0 + T // 2, BRASS if not pressed else wd["glow"])
        return
    m = max(1, T // 5)
    s = T - 2 * m
    if pressed:
        cv.rect(x0 + m, y0 + m, s, s, shade(BRASS, 0.55))
        cv.frame(x0 + m, y0 + m, s, s, mix(BRASS, wd["glow"], 0.6 + 0.2 * math.sin(t * 4)))
    else:
        cv.rect(x0 + m, y0 + m, s, s, BRASS)
        cv.rect(x0 + m, y0 + m + s - max(1, s // 4), s, max(1, s // 4), shade(BRASS, 0.6))
        cv.rect(x0 + m, y0 + m, s, 1, mix(BRASS, WHITE, 0.45))
        if T >= 9:
            cv.rect(x0 + T // 2 - 1, y0 + m + s // 3, 2, 2, shade(BRASS, 0.7))


def draw_gate(cv, x0, y0, T, open_, lv, i):
    if T < 3:
        if not open_:
            cv.rect(x0, y0, T, T, IRON)
        return
    horiz = lv.wall[i - 1] and lv.wall[i + 1]      # in a wall that runs across: Hesper passes up / down
    post = max(1, T // 6)
    if open_:
        # only the posts and the slot the gate sank into
        if horiz:
            cv.rect(x0, y0, post, T, shade(IRON, 0.8))
            cv.rect(x0 + T - post, y0, post, T, shade(IRON, 0.8))
            cv.rect(x0 + post, y0 + T // 2, T - 2 * post, 1, shade(IRON, 0.5))
        else:
            cv.rect(x0, y0, T, post, shade(IRON, 0.8))
            cv.rect(x0, y0 + T - post, T, post, shade(IRON, 0.8))
            cv.rect(x0 + T // 2, y0 + post, 1, T - 2 * post, shade(IRON, 0.5))
        return
    cv.rect(x0, y0, T, T, shade(IRON, 0.45))
    gap = max(2, T // 4)
    for k in range(0, T, gap):
        cv.rect(x0 + k, y0, 1 if T < 10 else 2, T, mix(IRON, WHITE, 0.25))
    for k in range(gap // 2, T, gap * 2):
        cv.rect(x0, y0 + k, T, 1, shade(IRON, 1.2))
    if T >= 8:
        for k in range(0, T, gap):
            cv.set(x0 + k, y0 + T - 1, (220, 200, 160))      # spikes catching the lantern light


# --- one frame ------------------------------------------------------------------------------------------
def render(g, cols, rows, hud=True, think=None):
    lv = g.level
    wd = WORLDS[lv.world]
    T, ox, oy = layout(lv, cols, rows, hud)
    cv = Canvas(cols, 1)
    cv.rows, cv.H = rows, rows * 2
    cv.px = [r[:] for r in static_layer(lv, T, ox, oy, cols, rows)]
    w = lv.w
    t = g.clock
    boxes = g.boxes
    gates = lv.gates_open(boxes)
    for i in range(lv.n):
        if lv.oneway[i] != NONE:
            draw_wind(cv, ox + (i % w) * T, oy + (i // w) * T, T, lv.oneway[i], t + (i % 7) * 0.13, wd)
    for p in lv.plates:
        draw_plate(cv, ox + (p % w) * T, oy + (p // w) * T, T, bool(boxes[p]), t, wd)
    mb = g.moving_box()
    # the lantern's warm light, then lit sockets
    px_, py_ = g.player_pos()
    pcx, pcy = ox + (px_ + 0.5) * T, oy + (py_ + 0.5) * T
    if T >= 4:
        glow(cv, pcx, pcy, 0, T * (2.6 if lv.world == 4 else 2.0), wd["glow"], 0.3 if lv.world == 4 else 0.16)
    stones = []
    for i in lv.cells:
        c = boxes[i]
        if not c:
            continue
        if mb and i == mb[0]:
            x, y = mb[1], mb[2]
        else:
            x, y = i % w, i // w
        lit = lv.tcol[i] + 1 == c and not (mb and i == mb[0] and g.anim["t"] < g.anim["dur"])
        stones.append((y, x, c - 1, lit))
    for (y, x, col, lit) in stones:
        if lit and T >= 4:
            gc = COLOURS[col] if col else SOCKET
            glow(cv, ox + (x + 0.5) * T, oy + (y + 0.5) * T, T * 0.3, T * 1.05, gc, 0.45 + 0.1 * math.sin(t * 3 + x))
    # gates (over the floor, under stones and Hesper)
    for i in range(lv.n):
        if lv.gate[i]:
            draw_gate(cv, ox + (i % w) * T, oy + (i // w) * T, T, gates or bool(boxes[i]), lv, i)
    # stones and Hesper from back to front
    items = [(y, 0, x, col, lit) for (y, x, col, lit) in stones] + [(py_, 1, px_, None, None)]
    items.sort(key=lambda e: (e[0], e[1]))
    for (y, kind, x, col, lit) in items:
        X, Y = ox + int(round(x * T)), oy + int(round(y * T))
        if kind == 0:
            if T >= 6:
                darken(cv, X + max(1, T // 10), Y + T - max(1, T // 8), T - max(1, T // 5), max(1, T // 8), 0.6)
            blit_img(cv, stone_img(col, lit, T, SOCKET), X, Y)
        else:
            draw_badger(cv, g, X, Y, T)
    # dust, sparkles
    psz = max(1, T // 7)
    for pt in g.parts:
        k = 1 - pt[4] / pt[5]
        x, y = int(ox + pt[0] * T), int(oy + pt[1] * T)
        if psz == 1:
            blend(cv, x, y, pt[6], 0.3 + 0.7 * k)
        else:
            for yy in range(y, y + psz):
                for xx in range(x, x + psz):
                    blend(cv, xx, yy, pt[6], 0.3 + 0.7 * k)
    if hud:
        draw_hud(cv, g)
        draw_banners(cv, g, think)
    return cv


def draw_hud(cv, g):
    cols, rows = cv.cols, cv.rows
    wd = WORLDS[g.world]
    cv.put(0, 0, " " * cols, HUD_FG, HUD_BG)
    left = " %s  %s " % (label(g.index), g.level.name.upper())
    cv.put(0, 0, left, INK, wd["accent"])
    best = None if g.demo else progress_cache().get(g.index)
    bits = [("moves ", HUD_DIM), ("%d" % g.moves, GOLD), ("  pushes ", HUD_DIM), ("%d" % g.pushes, HUD_FG),
            ("  par ", HUD_DIM), ("%d" % PARS[g.index], HUD_FG)]
    if best is not None:
        bits += [("  best ", HUD_DIM), ("%d" % best, GOLD if best <= PARS[g.index] else HUD_FG)]
    n = sum(len(s) for s, _ in bits)
    if n + len(left) + 2 > cols:
        bits = bits[:2] + bits[4:6]
        n = sum(len(s) for s, _ in bits)
    x = cols - n - 1
    for s, c in bits:
        cv.put(x, 0, s, c, HUD_BG)
        x += len(s)
    r = rows - 1
    cv.put(0, r, " " * cols, HUD_FG, HUD_BG)
    if not g.demo:
        keys = "arrows walk   U undo   R restart   [ ] cairns   Esc menu   ? help"
        if len(keys) + 2 > cols:
            keys = "arrows walk  U undo  R restart  Esc menu"
        cv.put(1, r, keys[:cols - 2], HUD_DIM, HUD_BG)
        tag = WORLDS[g.world]["name"]
        if len(keys) + len(tag) + 5 < cols:
            cv.put(cols - len(tag) - 1, r, tag, wd["accent"], HUD_BG)


def banner(cv, lines, col, row=None, colors=None):
    w = max(len(l) for l in lines) + 4
    w = min(w, cv.cols)
    x = max(0, (cv.cols - w) // 2)
    y = max(1, cv.rows // 2 - len(lines) // 2 - 1) if row is None else row
    cv.box(x, y, [l.center(w - 4)[:w - 4] for l in lines], (236, 236, 244), (20, 18, 36))
    cv.put(x + 2, y + 1, lines[0].center(w - 4)[:w - 4], col, (20, 18, 36))
    for j, c in (colors or {}).items():
        cv.put(x + 2, y + 1 + j, lines[j].center(w - 4)[:w - 4], c, (20, 18, 36))


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


def draw_banners(cv, g, think=None):
    wd = WORLDS[g.world]
    if think is not None:
        banner(cv, ["THE KEEPER IS THINKING", "", "%d positions weighed" % think], wd["accent"], row=max(1, cv.rows // 2 - 3))
        return
    if g.moves == 0 and g.intro_t < 3.2 and not g.solved:
        lines = ["%s   %s" % (wd["name"], label(g.index)), g.level.name.upper()]
        if g.index % PER_WORLD == 0:
            lines += [""] + wrap(wd["intro"], max(20, min(46, cv.cols - 8)))
        banner(cv, lines, wd["accent"], row=1)
    elif g.solved and g.solved_t > 0.5:
        par = PARS[g.index]
        lines = ["CAIRN SET", "", "moves %d   pushes %d" % (g.moves, g.pushes)]
        colors = {}
        if g.moves < par:
            lines.append("under par (%d)!" % par)
            colors[3] = GOLD
        elif g.moves == par:
            lines.append("at par - as few as the solver")
            colors[3] = GOLD
        else:
            lines.append("par is %d" % par)
        if getattr(g, "new_best", False):
            lines.append("new best for this cairn")
            colors[len(lines) - 1] = GOLD
        if not g.demo:
            last = g.index == len(LEVELS) - 1
            lines += ["", ("Enter: the next cairn" if not last else "Enter: back to the levels") + "   U undo   R again"]
        banner(cv, lines, GOLD, colors=colors)


# --- the level select ------------------------------------------------------------------------------------
def draw_preview(cv, lv, x0, y0, wpx, hpx):
    """The cairn as it starts, fitted into a pixel box."""
    T = max(1, min(wpx // lv.w, hpx // lv.h))
    ox = x0 + (wpx - T * lv.w) // 2
    oy = y0 + (hpx - T * lv.h) // 2
    st = static_layer(lv, T, ox, oy, cv.cols, cv.rows)
    vis = wall_vis(lv)
    w = lv.w
    sh = max(1, T // 3)
    for i in range(lv.n):
        if not (vis[i] or lv.inside[i]):
            continue
        X, Y = ox + (i % w) * T, oy + (i // w) * T
        for y in range(max(0, Y), min(cv.H, Y + T + sh)):
            a, b = max(0, X), min(cv.W, X + T + sh)
            cv.px[y][a:b] = st[y][a:b]
    wd = WORLDS[lv.world]
    for i in lv.cells:
        X, Y = ox + (i % w) * T, oy + (i // w) * T
        if lv.gate[i]:
            draw_gate(cv, X, Y, T, False, lv, i)
        if i in lv.plates:
            draw_plate(cv, X, Y, T, bool(lv.boxes0[i]), 0.0, wd)
        if lv.oneway[i] != NONE:
            draw_wind(cv, X, Y, T, lv.oneway[i], 0.3, wd)
    for i in lv.cells:
        c = lv.boxes0[i]
        if c:
            blit_img(cv, stone_img(c - 1, lv.tcol[i] + 1 == c, T, SOCKET), ox + (i % w) * T, oy + (i // w) * T)
    dummy = Game.__new__(Game)
    dummy.facing, dummy.anim, dummy.walk = DOWN, None, 0
    draw_badger(cv, dummy, ox + (lv.player0 % w) * T, oy + (lv.player0 // w) * T, T)


def render_select(cols, rows, sel, prog, help_=False, kitty=True):
    lv = LEVELS[sel]
    wd = WORLDS[lv.world]
    cv = Canvas(cols, 1)
    cv.rows, cv.H = rows, rows * 2
    cv.px = [[mix(c, (6, 6, 14), 0.35) for c in r] for r in backdrop(lv.world, cols, rows)]
    cv.put(0, 0, " " * cols, HUD_FG, HUD_BG)
    cv.put(0, 0, " CAIRNWARD - choose a cairn ", INK, ACCENTS[NAME][0])
    stat = "%d / %d set   %d at par " % (len(prog), len(LEVELS), sum(1 for j, m in prog.items() if m <= PARS[j]))
    cv.put(cols - len(stat), 0, stat, GOLD, HUD_BG)
    gap = 2 if rows >= 7 * 2 + 6 else 1
    lw = 32
    top = 2
    for wi, w in enumerate(WORLDS):
        r = top + wi * gap
        cv.put(1, r, " " * lw, PANEL_FG, PANEL_BG)
        cv.put(2, r, "%d %s" % (wi + 1, w["name"]), w["accent"] if wi == lv.world else HUD_DIM, PANEL_BG)
        if gap == 2:
            cv.put(1, r + 1, " " * lw, PANEL_FG, PANEL_BG)
        for k in range(PER_WORLD):
            i = wi * PER_WORLD + k
            x = 20 + k * 2
            if i in prog:
                ch, fg = ("♦", GOLD) if prog[i] <= PARS[i] else ("●", (150, 220, 150))
            elif is_open(i, prog):
                ch, fg = "○", (226, 226, 236)
            else:
                ch, fg = "·", (90, 90, 110)
            bg = mix(wd["accent"], WHITE, 0.2) if i == sel else PANEL_BG
            cv.put(x, r, ch, INK if i == sel else fg, bg)
    # the chosen cairn
    r = top + 7 * gap + (1 if gap == 2 else 0)
    info = ["%s  %s" % (label(sel), lv.name), "par %d" % PARS[sel] + ("   best %d" % prog[sel] if sel in prog else "")]
    if not is_open(sel, prog):
        info.append("locked - set earlier cairns")
    elif sel in prog:
        info.append("at par" if prog[sel] <= PARS[sel] else "set - par not yet reached")
    for j, s_ in enumerate(info):
        if r + j < rows - 1:
            cv.put(1, r + j, (" " + s_).ljust(lw)[:lw], (GOLD if j == 0 else HUD_FG), PANEL_BG)
    cv.put(1, rows - 1 if r + len(info) >= rows - 1 else r + len(info), "", HUD_FG)
    px0 = lw + 3
    draw_preview(cv, lv, px0, 4, cols - px0 - 2, (rows - 2) * 2 - 4)
    footer(cv, "arrows choose   Enter play   ? help   Esc back")
    legend = "♦ par  ● set  ○ open  · locked"
    if rows - 2 > r + len(info):
        cv.put(2, rows - 2, legend, HUD_DIM, None)
    if help_:
        overlay(cv, help_lines(kitty))
    return cv


# =============================================================================================
# The solver at work: thinking a little every frame, so the screen never freezes
# =============================================================================================
class Thinker:
    def __init__(self, index):
        self.index = index
        self.path = SOLUTIONS.get(index)
        self.gen = None if self.path is not None else solve(LEVELS[index], budget=150)
        self.expanded = 0
        self.failed = False

    @property
    def done(self):
        return self.path is not None or self.failed

    def step(self, secs):
        if self.done:
            return True
        end = time.perf_counter() + secs
        while time.perf_counter() < end:
            out = next(self.gen)
            if out[0] == "think":
                self.expanded = out[1]
            else:
                self.expanded = out[2]
                if out[1] is None:
                    self.failed = True
                else:
                    self.path = out[1]
                    SOLUTIONS[self.index] = out[1]
                return True
        return False


class TitleDemo:
    """The solver setting cairns from every region behind the title (and in the launcher preview)."""
    PICK = (5, 16, 20, 25, 37, 9, 30, 23, 14, 38, 32, 36, 2, 27, 19)

    def __init__(self, k=0):
        self.k = k
        self.new_run()

    def new_run(self):
        idx = self.PICK[self.k % len(self.PICK)]
        self.k += 1
        self.g = Game(idx, quiet=True, demo=True)
        self.th = Thinker(idx)
        self.step_i = 0
        self.timer = 0.0

    def scene(self, cols, rows, dt):
        g = self.g
        if not self.th.done:
            self.th.step(0.006)
        else:
            g.update(dt)
            self.timer += dt
            if self.th.failed:
                self.new_run()
            elif not g.solved and not g.busy and self.timer > 0.2 and self.step_i < len(self.th.path):
                g.go(self.th.path[self.step_i])
                self.step_i += 1
                self.timer = 0.0
            elif g.solved and g.solved_t > 1.6:
                self.new_run()
        if cols < g.level.w + 2 or rows * 2 < g.level.h + 2:      # too small for the cairn (tiny previews): sky only
            cv = Canvas(cols, max(1, rows))
            cv.px = [r[:] for r in backdrop(g.level.world, cols, max(1, rows))]
            return cv
        return render(self.g, cols, rows, hud=False)


class AutoRun:
    """Auto mode: from the chosen region on, the solver thinks (on screen), then Hesper walks its solution; after
    each cairn the next one. Nothing is recorded."""
    PAUSE = 0.16

    def __init__(self, world, sound=True):
        self.sound = sound
        self.auto = AutoMode()
        self.index = world * PER_WORLD
        self.cairns = 0
        self.new()

    def new(self):
        self.g = Game(self.index, quiet=not self.sound, demo=True)
        self.th = Thinker(self.index)
        self.step_i = 0
        self.timer = 0.0

    def key(self, k):
        a = self.auto.key(k)
        if a == "sound" and SND.toggle():
            SND.play("sound_on")
        return a

    def frame(self, dt, cols, rows, draw=True):
        g = self.g
        sdt = self.auto.scale(dt)
        if not self.th.done:
            if sdt > 0:
                self.th.step(0.014)
            g.clock += sdt
        else:
            n = max(1, int(self.auto.speed))
            sub = sdt / n
            for _ in range(n):
                g.update(sub)
                self.timer += sub
                if self.th.failed:
                    break
                if not g.solved and not g.busy and self.timer >= self.PAUSE and self.step_i < len(self.th.path):
                    if not g.go(self.th.path[self.step_i]):
                        raise AssertionError("the solver's move %d on %s is blocked" % (self.step_i, g.level.name))
                    self.step_i += 1
                    self.timer = 0.0
            if g.solved and g.solved_t > 2.6:
                self.cairns += 1
                self.index = (self.index + 1) % len(LEVELS)
                self.new()
                g = self.g
        if not draw:
            return None
        cv = render(g, cols, rows, think=None if self.th.done else self.th.expanded)
        self.auto.banner(cv, extra="cairn %s" % label(g.index))
        return cv


def too_small(term):
    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (60x22).")


def run_auto(term, world):
    run = AutoRun(world)
    last = time.time()
    while True:
        now = time.time()
        dt, last = min(0.1, now - last), now
        for k, kind in term.events(0):
            if kind == "press" and run.key(k) == "stop":
                return
        cols, rows = term.size()
        if cols < 60 or rows < 22:
            too_small(term)
            time.sleep(0.2)
            continue
        term.write(run.frame(dt, cols, rows).emit())
        time.sleep(max(0.0, 1 / 30 - (time.time() - now)))


# =============================================================================================
# Menus and the main loop
# =============================================================================================
def menu_items(world, prog):
    c = first_open(prog)
    return ["Continue      %s %s" % (label(c), LEVELS[c].name), "Level select",
            "%s     < %d %s >" % (AUTO_LABEL, world + 1, WORLDS[world]["short"])]


def render_menu(demo, cols, rows, sel, world, dt, help_, kitty):
    cv = demo.scene(cols, rows, dt)
    prog = progress_cache()
    npar = sum(1 for j, m in prog.items() if m <= PARS[j])
    best = ("best  %d / %d cairns set   %d at par" % (len(prog), len(LEVELS), npar)) if prog else None
    extra = ["", "A storm scattered the waystones of the pass.", "Push each one home - you can never pull."]
    title_screen(cv, NAME, TAGLINE, menu_items(world, prog), sel, best, extra=extra,
                 keys="Up/Down choose   Left/Right region   Enter start   M %s   ? help   Esc back" % SND.label().lower(),
                 help_lines=help_lines(kitty), show_help=help_, dim=0.45)
    return cv


def open_neighbour(i, step, prog):
    j = i + step
    while 0 <= j < len(LEVELS):
        if is_open(j, prog):
            return j
        j += step
    return i


def play(term, index):
    """Play cairns from index on. Returns the last cairn played (for the level select)."""
    g = Game(index)
    kitty = term.kitty
    last = time.time()
    while True:
        now = time.time()
        dt = min(0.1, now - last)
        last = now
        for name, kind in term.events():
            if kind == "release":
                continue
            a = shared_key(name, g.paused) if kind == "press" else (None if not g.paused else "eaten")
            if a == "pause":
                g.paused = True
                SND.play("pause")
            elif a == "resume":
                g.paused = g.help = False
            elif a == "quit":
                return g.index
            elif a == "help":
                g.help = not g.help
                g.paused = True
            elif a == "sound":
                if SND.toggle():
                    SND.play("sound_on")
            elif a is None:
                if name in KEYDIR:
                    g.press(KEYDIR[name], repeat=kind == "repeat")
                elif name in ("u", "z", "backspace"):
                    g.undo()
                elif name == "r" and kind == "press":
                    g.restart()
                elif name in ("[", "]") and kind == "press":
                    j = open_neighbour(g.index, -1 if name == "[" else 1, progress_cache())
                    if j != g.index:
                        SND.play("menu")
                        g = Game(j)
                elif name in ("enter", " ") and kind == "press" and g.solved:
                    if g.index == len(LEVELS) - 1:
                        return g.index
                    nxt = g.index + 1
                    SND.play("world" if nxt % PER_WORLD == 0 else "start")
                    g = Game(nxt)
        cols, rows = term.size()
        if cols < 60 or rows < 22:
            too_small(term)
            time.sleep(0.2)
            last = time.time()
            continue
        if not g.paused:
            g.update(dt)
        if g.solved and not g.anim and not getattr(g, "recorded", False):
            g.recorded = True
            g.new_best = record(g.index, g.moves)
            if g.moves <= PARS[g.index]:
                SND.play("par", 0.7)
        elif not g.solved:
            g.recorded = False
            g.new_best = False
        cv = render(g, cols, rows)
        if g.paused:
            overlay(cv, help_lines(kitty) if g.help else PAUSE_LINES[:-1] + ["Q                 level select", "",
                                                                             SND.label()])
        term.write(cv.emit())
        time.sleep(max(0.0, 1 / 30 - (time.time() - now)))


def select(term, sel):
    """The level select. Returns a cairn to play or None (back to the title)."""
    help_ = False
    while True:
        prog = progress_cache()
        cols, rows = term.size()
        if cols < 60 or rows < 22:
            too_small(term)
            if any(k in ("q", "esc") for k, kind in term.events(0.3) if kind == "press"):
                return None
            continue
        term.write(render_select(cols, rows, sel, prog, help_, term.kitty).emit())
        for k, kind in term.events(1 / 20):
            if kind == "release":
                continue
            if help_:
                help_ = False
            elif k == "?":
                help_ = True
            elif k in ("q", "esc"):
                return None
            elif k in ("left", "a", "h"):
                sel = (sel - 1) % len(LEVELS)
                SND.play("menu")
            elif k in ("right", "d", "l", "tab"):
                sel = (sel + 1) % len(LEVELS)
                SND.play("menu")
            elif k in ("up", "w", "k"):
                sel = (sel - PER_WORLD) % len(LEVELS)
                SND.play("menu")
            elif k in ("down", "s", "j"):
                sel = (sel + PER_WORLD) % len(LEVELS)
                SND.play("menu")
            elif k in ("enter", " ") and kind == "press":
                if is_open(sel, prog):
                    SND.play("start")
                    return sel
                SND.play("locked")


def main():
    with KeyTerminal() as term:
        demo = TitleDemo()
        sel, world, help_ = 0, 0, False
        pick = first_open(progress_cache())
        last = time.time()
        while True:
            now = time.time()
            cols, rows = term.size()
            if cols < 60 or rows < 22:
                too_small(term)
                if any(k in ("q", "esc") for k, kind in term.events(0.3) if kind == "press"):
                    return
                last = time.time()
                continue
            term.write(render_menu(demo, cols, rows, sel, world, min(0.1, now - last), help_, term.kitty).emit())
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
                    sel = (sel + 1) % 3
                    SND.play("menu")
                elif k in ("up", "w"):
                    sel = (sel - 1) % 3
                    SND.play("menu")
                elif k in ("left", "a", "right", "d"):
                    world = (world + (-1 if k in ("left", "a") else 1)) % len(WORLDS)
                    sel = 2
                    SND.play("menu")
                elif k == "m":
                    if SND.toggle():
                        SND.play("sound_on")
                elif k in ("enter", " "):
                    SND.play("start")
                    go = True
            if not go:
                continue
            if sel == 2:
                run_auto(term, world)
            elif sel == 0:
                pick = play(term, first_open(progress_cache()))
            else:
                while True:
                    choice = select(term, pick)
                    if choice is None:
                        break
                    pick = play(term, choice)
            last = time.time()


# =============================================================================================
# Self-test
# =============================================================================================
def replay(index, path):
    """Play directions through the real Game (with its animation). Returns the game."""
    g = Game(index, quiet=True, demo=True)
    for d in path:
        assert not g.solved, "%s: solved before the end of the line" % g.level.name
        g.press(d)
        while g.busy:
            g.update(1 / 30)
    return g


def selftest():
    t0 = time.time()
    global submit

    def no_scores(*a, **k):
        raise AssertionError("the self-test must not write scores")
    submit = no_scores
    # 1. the cairns: seven regions of six, sizes, the twists arrive one region at a time
    assert len(LEVELS) == 42 and len(WORLDS) == 7
    assert len(set(lv.name for lv in LEVELS)) == 42, "two cairns share a name"
    feats = []
    for i, lv in enumerate(LEVELS):
        assert lv.world == i // PER_WORLD, lv.name
        assert lv.w <= MAX_W and lv.h <= MAX_H, "%s is %dx%d" % (lv.name, lv.w, lv.h)
        f = set()
        if any(lv.ice):
            f.add("ice")
        if any(o != NONE for o in lv.oneway):
            f.add("wind")
        if lv.plates or any(lv.gate):
            assert lv.plates and any(lv.gate), "%s: plates without gates or gates without plates" % lv.name
            f.add("plates")
        if any(c > 1 for c in lv.boxes0):
            f.add("colours")
        feats.append(f)
        w = lv.world
        allowed = {0: set(), 1: set(), 2: {"ice"}, 3: {"wind"}, 4: {"plates"}, 5: {"colours"}}.get(w)
        if allowed is not None:
            assert f == allowed, "%s: %s in %s" % (lv.name, sorted(f), WORLDS[w]["name"])
        else:
            assert len(f) >= 2, "%s: a summit cairn needs two twists at least" % lv.name
    nstones = sum(sum(1 for b in lv.boxes0 if b) for lv in LEVELS)
    print("cairns: 42 in 7 regions, %d stones, at most %dx%d; pure, ice, wind, plates, colours, mixed" % (
        nstones, max(lv.w for lv in LEVELS), max(lv.h for lv in LEVELS)))
    # 2. the rules
    lv = Level(["#######", "#@$$ .#", "#    .#", "#######"], "t")
    assert lv.move(lv.player0, lv.boxes0, RIGHT) is None, "pushed two stones at once"
    p, b, bf, bt = lv.move(lv.player0, lv.boxes0, DOWN)
    assert bf < 0 and p == lv.player0 + lv.w
    lv = Level(["#########", "#@$~~~ .#", "#       #", "#########"], "t")
    p, b, bf, bt = lv.move(lv.player0, lv.boxes0, RIGHT)
    assert bt == lv.player0 + 5 and p == lv.player0 + 1, "a stone did not slide off the ice onto the floor"
    lv = Level(["########", "#@ ~~~$#", "#     .#", "########"], "t")
    p, b, bf, bt = lv.move(lv.player0 + 1, lv.boxes0, RIGHT)
    assert p == lv.player0 + 4 and bf < 0, "Hesper did not slide up to the stone"
    lv = Level(["#######", "#@ < .#", "#  $  #", "#######"], "t")
    assert lv.move(lv.player0 + 1, lv.boxes0, RIGHT) is None, "walked against the wind"
    assert lv.move(lv.player0 + 3, lv.boxes0, LEFT) is not None
    lv = Level(["#########", "#@$ _  ##", "# $  | .#", "#########"], "t")
    assert not lv.gates_open(lv.boxes0)
    st = lv.move(lv.player0, lv.boxes0, RIGHT)
    st = lv.move(st[0], st[1], RIGHT)
    assert lv.gates_open(st[1]), "a stone on the plate did not open the gate"
    lv = Level(["########", "#@a  A #", "#  B b #", "########"], "t")
    assert lv.solved(lv.boxes0) is False
    p, b = lv.player0, lv.boxes0
    for d in (RIGHT, RIGHT, RIGHT):
        p, b, _, _ = lv.move(p, b, d)
    assert b[lv.player0 + 4] == 2 and lv.tcol[lv.player0 + 4] == 1 and not lv.solved(b), "colours"
    p, b, _, _ = lv.move(p + lv.w - 1, b, LEFT)
    assert not lv.solved(b), "a moss stone on a sky socket counted"
    g = Game(5, quiet=True, demo=True)
    for d in (DOWN, RIGHT, UP, LEFT, LEFT, DOWN):
        g.press(d)
        while g.busy:
            g.update(0.05)
    m = g.moves
    assert m > 0
    while g.undo():
        pass
    assert g.moves == 0 and g.p == g.level.player0 and g.boxes == g.level.boxes0, "undo did not go back to the start"
    g.press(RIGHT)
    while g.busy:
        g.update(0.05)
    g.restart()
    assert g.moves == 0 and g.history and g.undo() and g.moves == 1, "restart could not be undone"
    print("rules: one stone at a time, ice slides (stones and Hesper), wind one way, plates open gates, colours, "
          "undo to the start, restart undoable")
    # 3. every cairn: the solver finds a line of exactly par moves, and the real game plays it to the end
    times = []
    expanded = 0
    for i, lv in enumerate(LEVELS):
        a = time.time()
        path, n = solve_now(lv)
        times.append(time.time() - a)
        expanded += n
        assert path is not None, "%s: the solver found no solution" % lv.name
        assert len(path) == PARS[i], "%s: the solver needs %d moves, par says %d" % (lv.name, len(path), PARS[i])
        g = replay(i, path)
        assert g.solved and g.moves == PARS[i], "%s: the game did not end solved" % lv.name
        SOLUTIONS[i] = path
    slow = max(range(len(LEVELS)), key=lambda i: times[i])
    print("solver: all 42 cairns solved in %.1f s (%d positions expanded), each line = par, replayed in the game; "
          "slowest %s %.1f s" % (sum(times), expanded, LEVELS[slow].name, times[slow]))
    for w in range(7):
        ps = PARS[w * PER_WORLD:(w + 1) * PER_WORLD]
        print("  %-14s par %s" % (WORLDS[w]["name"], " ".join("%3d" % p for p in ps)))
    # deadlock pruning: a stone in a corner, and a frozen 2x2 block, are recognised at once
    for rows in (["#####", "#$ .#", "#@  #", "#####"], ["######", "#    #", "# $$ #", "# $$ #", "#@...#", "#  . #",
                                                       "######"]):
        path, n = solve_now(Level(rows, "dead"))
        assert path is None and n < 2000, "a dead cairn was not recognised (%d expanded)" % n
    print("deadlocks: a cornered stone and a frozen block are seen as lost")
    # 4. rendering at every size
    timing = []
    n = 0
    for cols, rows in ((60, 22), (80, 24), (100, 32), (120, 40), (240, 70)):
        tr = te = 0.0
        frames = 0
        for i in (0, 7, 15, 20, 27, 33, 38, 41):
            g = Game(i, quiet=True)
            path = SOLUTIONS[i]
            for d in path[:len(path) // 2]:
                g.press(d)
                while g.busy:
                    g.update(1 / 30)
            g.press(path[len(path) // 2])
            g.update(0.03)
            for _ in range(3):
                a = time.time()
                cv = render(g, cols, rows)
                b = time.time()
                cv.emit(True)
                c_ = time.time()
                tr += b - a
                te += c_ - b
                frames += 1
                g.update(0.03)
            overlay(cv, help_lines(True))
            g.solved, g.solved_t = True, 1.0
            render(g, cols, rows).emit(True)
        prog = {0: 4, 1: 20, 3: 18}
        render_select(cols, rows, 3, prog).emit(True)
        render_select(cols, rows, 30, prog, help_=True).emit(True)
        n += frames + 2
        timing.append((cols, rows, tr / frames * 1000, te / frames * 1000))
    d = TitleDemo()
    for cols, rows in ((60, 22), (120, 40), (24, 8), (40, 12), (60, 30)):
        render_menu(d, cols, rows, 0, 2, 0.05, False, True).emit(True) if rows >= 20 else d.scene(cols, rows, 0.05)
        n += 1
    for _ in range(300):
        d.scene(30, 9, 0.1)
    print("rendering: %d frames at 60x22, 80x24, 100x32, 120x40, 240x70 (+ level select, title, preview, overlays)" % n)
    for cols, rows, r_, e_ in timing:
        print("  %3dx%-3d render %5.1f ms  emit %5.1f ms  = %5.1f ms per frame (%3.0f fps)" % (
            cols, rows, r_, e_, r_ + e_, 1000 / max(0.1, r_ + e_)))
    # 5. auto mode: the solver thinks on screen, then walks; pause, speed, stop; nothing recorded
    for i in (0, 1, 2):
        SOLUTIONS.pop(i, None)          # think afresh, as in a real start
    run = AutoRun(0, sound=False)
    thinking = 0
    while not run.th.done:
        run.frame(1 / 30, 80, 24, draw=thinking % 10 == 0)
        thinking += 1
    run.key(" ")
    snap = (run.g.moves, run.g.clock)
    for _ in range(20):
        run.frame(1 / 30, 80, 24, draw=False)
    assert (run.g.moves, run.g.clock) == snap, "auto mode ran on while paused"
    run.key(" ")
    for _ in range(5):
        run.key("+")
    assert run.auto.speed == 8.0
    for i in range(30 * 30):
        run.frame(1 / 30, 70 + i % 3 * 25, 22 + i % 2 * 10, draw=i % 15 == 0)
    assert run.cairns >= 3, "auto mode set only %d cairns in 30 s at x8" % run.cairns
    assert run.key("esc") == "stop"
    print("auto mode: %d cairns set in 30 s at x8 (the first after %d frames of thinking on screen), now at %s, "
          "nothing recorded" % (run.cairns, thinking, label(run.g.index)))
    # 6. simulation speed
    g = Game(41, quiet=True, demo=True)
    a = time.time()
    k = 0
    for _ in range(40):
        for d in SOLUTIONS[41]:
            g.press(d)
            while g.busy:
                g.update(1 / 30)
                k += 1
        g = Game(41, quiet=True, demo=True)
    print("simulation: %.0f us per animation frame" % ((time.time() - a) / max(1, k) * 1e6))
    print("Self-test ok (%.1f s)" % (time.time() - t0))


def screenshot(cols=100, rows=32):
    """README picture: the solver's line through 7-3 RIDGE STAIR (ice, wind, a plate and colours), 22 moves in and
    one step under way. Deterministic and quiet, nothing written; best moves are not shown."""
    i = 38
    path = SOLUTIONS.get(i) or solve_now(LEVELS[i])[0]
    g = Game(i, quiet=True, demo=True)
    for d in path[:22]:
        g.press(d)
        while g.busy:
            g.update(1 / 30)
    g.update(0.6)
    g.press(path[22])
    g.update(0.05)
    g.intro_t = 9.0
    return render(g, cols, rows)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--auto" in sys.argv:
        with KeyTerminal() as _term:
            run_auto(_term, 0)
    else:
        main()
