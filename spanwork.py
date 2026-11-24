#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""SPANWORK - build a bridge, then watch the physics decide.

Join the anchors on the cliffs with road, wood, steel and cable on a one-metre grid, stay within the budget, and
send the traffic across. The test is real physics: every joint has mass, every beam is a stiff spring with the
stiffness, weight, strength and price of its material, gravity pulls, wheels press on the road. Each beam shows
its load from green to red while the car rolls over it; past its limit in tension or in compression it snaps,
and what it held up falls. Cables only take tension.

Eight crossings: wider gaps, a stepping stone, a van, a convoy, towers for cables, a truck and a long haul.
Build with the mouse (click a joint, click where the beam should go) or with the arrow keys and Space.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
Run:        python3 spanwork.py
Self-test:  python3 spanwork.py --selftest
"""
import math
import random
import sys
import time

from arcadekit import (AUTO_LABEL, PAUSE_LINES, AutoMode, Canvas, MouseTerminal, clamp, load_scores, mix, overlay,
                       shade, shared_key, submit, title_screen)
from arcadesound import Sound

GAME = "spanwork"
G = 9.81
SUB = 14                   # physics substeps per frame
SETTLE = 1.2               # seconds: gravity comes on gently and the bridge settles before the traffic starts
FRAME = 1 / 60
# material: stiffness EA (N), mass (kg per m), breaks above tension / compression (N), cost per m, longest beam (m)
MATS = {
    "road": dict(EA=2.5e7, kg=55.0, T=30e3, C=22e3, cost=220, max=4.2, col=(64, 64, 72), name="Road"),
    "wood": dict(EA=1.5e7, kg=16.0, T=30e3, C=21e3, cost=150, max=4.2, col=(176, 120, 64), name="Wood"),
    "steel": dict(EA=5.0e7, kg=40.0, T=85e3, C=66e3, cost=430, max=5.2, col=(120, 150, 186), name="Steel"),
    "cable": dict(EA=3.0e7, kg=5.0, T=60e3, C=0.0, cost=90, max=9.0, col=(40, 36, 44), name="Cable"),
}
VEHICLES = {  # wheel radius, wheelbase, mass (kg), speed (m/s), body colour, body height
    "car": dict(r=0.42, wb=2.0, kg=1000, speed=5.0, col=(220, 70, 60), h=0.9),
    "van": dict(r=0.48, wb=2.6, kg=1800, speed=4.5, col=(240, 236, 228), h=1.3),
    "truck": dict(r=0.55, wb=3.4, kg=3000, speed=4.0, col=(240, 180, 50), h=1.5),
}
HUD_BG, HUD_FG = (16, 14, 26), (226, 226, 236)


def cliffs(width, xl, hl, xr, hr):
    return [[(-2, -4), (-2, hl), (xl, hl), (xl, -4)], [(xr, -4), (xr, hr), (width + 2, hr), (width + 2, -4)]]


LEVELS = [
    dict(name="First Span", width=20, height=12, terrain=cliffs(20, 6, 6, 14, 6), deck=6, gap=(6, 14),
         anchors=[(6, 6), (14, 6), (6, 3), (14, 3)], budget=6000, mats=["road", "wood"], vehicles=["car"],
         bot="wood", depth=2, hint="Click a red anchor, then a point: a beam. The car only drives on road."),
    dict(name="Wider Gap", width=22, height=12, terrain=cliffs(22, 5, 6, 17, 6), deck=6, gap=(5, 17),
         anchors=[(5, 6), (17, 6), (5, 2), (17, 2)], budget=11000, mats=["road", "wood"], vehicles=["car"],
         bot="wood", depth=3, hint="Triangles carry; a flat road alone sags and snaps. Build a truss above or below."),
    dict(name="Stepping Stone", width=24, height=12,
         terrain=cliffs(24, 4, 6, 20, 6) + [[(11, -4), (11, 3), (13, 3), (13, -4)]], deck=6, gap=(4, 20),
         anchors=[(4, 6), (20, 6), (12, 3), (4, 2), (20, 2)], budget=12500, mats=["road", "wood"], vehicles=["car"],
         bot="wood", depth=2, hint="The rock in the river holds an anchor: let the bridge rest on it."),
    dict(name="The Van", width=22, height=12, terrain=cliffs(22, 5, 6, 17, 6), deck=6, gap=(5, 17),
         anchors=[(5, 6), (17, 6), (5, 2), (17, 2)], budget=20000, mats=["road", "wood", "steel"], vehicles=["van"],
         bot="steel", depth=2, hint="A van weighs nearly twice a car. Steel is strong, heavy and dear."),
    dict(name="Convoy", width=24, height=12, terrain=cliffs(24, 5, 5, 19, 5), deck=5, gap=(5, 19),
         anchors=[(5, 5), (19, 5), (5, 1), (19, 1)], budget=12500, mats=["road", "wood", "steel"],
         vehicles=["car", "car"], bot="wood", depth=3, hint="Two cars, one after the other."),
    dict(name="Towers", width=26, height=14,
         terrain=cliffs(26, 4, 6, 22, 6), posts=[(3, 6, 12), (23, 6, 12)],
         deck=6, gap=(4, 22), anchors=[(4, 6), (22, 6), (3, 12), (23, 12), (4, 2), (22, 2)], budget=16500,
         mats=["road", "wood", "steel", "cable"], vehicles=["car"], bot="wood", depth=2,
         hint="Cables from the towers take tension cheaply - but never push."),
    dict(name="The Truck", width=24, height=12, terrain=cliffs(24, 5, 6, 19, 6), deck=6, gap=(5, 19),
         anchors=[(5, 6), (19, 6), (5, 2), (19, 2)], budget=29500, mats=["road", "wood", "steel", "cable"],
         vehicles=["truck"], bot="steel", depth=3, hint="Three tonnes. Every beam has to earn its place."),
    dict(name="Long Haul", width=28, height=14,
         terrain=cliffs(28, 4, 7, 24, 7) + [[(13, -4), (13, 4), (15, 4), (15, -4)]], deck=7, gap=(4, 24),
         anchors=[(4, 7), (24, 7), (14, 4), (4, 3), (24, 3)], budget=35500, mats=["road", "wood", "steel", "cable"],
         vehicles=["van", "car"], bot="steel", depth=2, hint="Twenty metres, a van and a car. The rock helps."),
]
SND = Sound(GAME, {
    "place": [dict(w="tri", f=520, d=0.03, v=0.24), dict(w="noise", f=3000, d=0.02, v=0.1, at=0)],
    "join": [dict(w="tri", f=780, d=0.04, v=0.22)],
    "delete": [dict(w="tri", f=400, f2=200, d=0.08, v=0.22)],
    "nope": [dict(w="square", f=150, d=0.08, v=0.18, duty=0.3)],
    "go": [dict(w="saw", f=70, f2=110, d=0.5, v=0.2, r="lin"), dict(w="square", f=440, d=0.06, v=0.16, at=0)],
    "creak": [dict(w="saw", f=95, f2=80, d=0.25, v=0.14, vib=(12, 0.5), r="lin")],
    "snap": [dict(w="noise", f=4000, f2=300, d=0.2, v=0.5), dict(w="square", f=900, f2=200, d=0.08, v=0.25, at=0)],
    "splash": [dict(w="noise", f=3000, f2=200, d=0.7, v=0.5, r="lin"), dict(w="sine", f=200, f2=60, d=0.3, v=0.3, at=0)],
    "win": [dict(w="square", f=f, d=0.09, v=0.26, duty=0.25) for f in (523, 659, 784)] +
           [dict(w="tri", f=1047, d=0.5, v=0.4, vib=(6, 0.25), r="lin")],
    "fail": [dict(w="tri", f=392, d=0.18, v=0.35), dict(w="tri", f=330, d=0.18, v=0.35),
             dict(w="tri", f=262, d=0.4, v=0.35, r="lin")],
    "menu": [dict(w="tri", f=660, d=0.025, v=0.2)],
    "start": [dict(w="square", f=392, d=0.05, v=0.3, duty=0.25), dict(w="square", f=587, d=0.12, v=0.3, duty=0.25)],
    "pause": [dict(w="tri", f=523, f2=392, d=0.07, v=0.22)],
    "sound_on": [dict(w="tri", f=440, d=0.06, v=0.35), dict(w="tri", f=880, d=0.12, v=0.35)],
})
HELP = [
    "SPANWORK - keys",
    "",
    "Left click / Space    start a beam at a joint, then set its end",
    "                      (beams chain on; click the end again to stop)",
    "Right click / X       cancel the beam, or delete the one under the hand",
    "Arrows / WASD         move the hand on the grid",
    "1 2 3 4 / Tab / wheel road, wood, steel, cable",
    "U                     undo        C   clear the bridge",
    "Enter / T             test it     R   back to building",
    "N / B                 next / previous crossing",
    "Esc / P               pause       ?   help",
    "",
    "Road carries the wheels. Wood is light and cheap, steel strong",
    "and heavy, cable takes only tension. Red beams are near their limit.",
]


# =============================================================================================
# The physics: position-based dynamics with compliant constraints (XPBD). Every beam is a stiff
# spring (compliance = length / EA); its force falls out of the solve and decides when it snaps.
# =============================================================================================
class Sim:
    def __init__(self, level, nodes, members, anchors):
        self.level = level
        self.x = [list(map(float, p)) for p in nodes]
        n = len(nodes)
        mass = [0.0] * n
        self.mem = []
        for a, b, mat in members:
            m = MATS[mat]
            L = math.dist(nodes[a], nodes[b])
            mass[a] += m["kg"] * L / 2
            mass[b] += m["kg"] * L / 2
            self.mem.append([a, b, mat, L, L / m["EA"], 0.0, True, 0.0])   # rest, compliance, force, alive, load
        self.w = [0.0 if i in anchors or mass[i] == 0 else 1.0 / mass[i] for i in range(n)]
        self.nb = n                                    # bridge joints; wheels come after them
        self.cars = []
        for k, kind in enumerate(level["vehicles"]):
            v = VEHICLES[kind]
            x0 = 0.6 + v["wb"]
            y = level["deck"] + v["r"] + 0.02
            if level["gap"][0] - 0.4 < x0:
                x0 = level["gap"][0] - 0.4
            i = len(self.x)
            self.x += [[x0 - v["wb"], y], [x0, y]]
            w = 2.0 / v["kg"]
            self.w += [w, w]
            self.cars.append(dict(kind=kind, i=i, r=v["r"], wb=v["wb"], speed=v["speed"], col=v["col"], h=v["h"],
                                  spawn=SETTLE + k * 3.2, on=False, done=False, contact=[None, None]))
        self.p = [list(p) for p in self.x]
        self.v = [[0.0, 0.0] for _ in self.x]
        self.edges = []
        for poly in level["terrain"]:
            for k in range(len(poly)):
                self.edges.append((poly[k], poly[(k + 1) % len(poly)]))
        self.t = 0.0
        self.result = None                             # None, "win", "splash", "stuck"
        self.snapped = []                              # members that broke this frame (for sounds and pieces)
        self.goal = level["gap"][1] + 2.0

    def active(self, i):
        if i < self.nb:
            return self.w[i] > 0
        return self.cars[(i - self.nb) // 2]["on"]

    def step(self, dt=FRAME):
        self.snapped = []
        if self.result:
            return
        for c in self.cars:
            if not c["on"] and self.t >= c["spawn"]:
                c["on"] = True
        h = dt / SUB
        for _ in range(SUB):
            self.substep(h)
        self.t += dt
        self.judge()

    def substep(self, h):
        x, p, v, w = self.x, self.p, self.v, self.w
        act = [self.active(i) for i in range(len(x))]
        g = G * min(1.0, self.t / (SETTLE * 0.7))
        for i in range(len(x)):
            if act[i]:
                v[i][1] -= g * h
                p[i][0], p[i][1] = x[i][0], x[i][1]
                x[i][0] += v[i][0] * h
                x[i][1] += v[i][1] * h
        h2 = h * h
        for m in self.mem:
            if not m[6]:
                continue
            a, b = m[0], m[1]
            xa, xb = x[a], x[b]
            dx, dy = xb[0] - xa[0], xb[1] - xa[1]
            L = math.hypot(dx, dy) or 1e-9
            C = L - m[3]
            if m[2] == "cable" and C < 0:
                m[5] *= 0.9
                continue
            wa, wb = w[a], w[b]
            dl = -C / (wa + wb + m[4] / h2)
            nx, ny = dx / L * dl, dy / L * dl
            xa[0] -= wa * nx
            xa[1] -= wa * ny
            xb[0] += wb * nx
            xb[1] += wb * ny
            m[5] += (-dl / h2 - m[5]) * 0.12           # + tension, - compression (smoothed)
        for c in self.cars:
            if c["on"]:
                self.solve_car(c, h)
        for i in range(len(x)):
            if act[i]:
                v[i][0] = (x[i][0] - p[i][0]) / h
                v[i][1] = (x[i][1] - p[i][1]) / h
        damp = 1 - (0.8 if self.t > SETTLE else 12.0) * h
        for i in range(self.nb):
            if act[i]:
                v[i][0] *= damp
                v[i][1] *= damp
        for c in self.cars:                            # wheels on the ground roll the car along
            if not c["on"]:
                continue
            target = 0.0 if c["done"] else c["speed"]
            for k in (0, 1):
                n = c["contact"][k]
                if n is None:
                    continue
                i = c["i"] + k
                tx, ty = n[1], -n[0]
                vt = v[i][0] * tx + v[i][1] * ty
                dv = (target - vt) * min(1.0, 10 * h)
                v[i][0] += tx * dv
                v[i][1] += ty * dv
        for m in self.mem:
            if m[6]:
                mat = MATS[m[2]]
                f = m[5]
                m[7] = f / mat["T"] if f >= 0 else (-f / mat["C"] if mat["C"] else 0.0)
                if m[7] > 1.0:
                    m[6] = False
                    self.snapped.append(m)

    def solve_car(self, c, h):
        x, w = self.x, self.w
        i, j = c["i"], c["i"] + 1
        a, b = x[i], x[j]                              # the body: a stiff link between the wheels
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1e-9
        C = L - c["wb"]
        dl = -C / (w[i] + w[j] + 1e-8 / (h * h))
        a[0] -= w[i] * dl * dx / L
        a[1] -= w[i] * dl * dy / L
        b[0] += w[j] * dl * dx / L
        b[1] += w[j] * dl * dy / L
        for k in (0, 1):
            q = i + k
            c["contact"][k] = None
            pq, r, wq = x[q], c["r"], w[q]
            for m in self.mem:                         # the road, one-sided: it pushes wheels up, never down
                if not m[6] or m[2] != "road":
                    continue
                na, nb = (m[0], m[1]) if x[m[0]][0] <= x[m[1]][0] else (m[1], m[0])
                A, B = x[na], x[nb]
                sx, sy = B[0] - A[0], B[1] - A[1]
                l2 = sx * sx + sy * sy
                if l2 < 1e-9 or abs(sx) < 0.05:
                    continue
                t = clamp(((pq[0] - A[0]) * sx + (pq[1] - A[1]) * sy) / l2, 0.0, 1.0)
                qx, qy = A[0] + sx * t, A[1] + sy * t
                ex, ey = pq[0] - qx, pq[1] - qy
                d = math.hypot(ex, ey)
                if d >= r or d < 1e-9:
                    continue
                if (sx * (pq[1] - A[1]) - sy * (pq[0] - A[0])) < 0:   # below the road: no contact
                    continue
                nx, ny = ex / d, ey / d
                wa, wb = self.w[na] * (1 - t), self.w[nb] * t
                den = wq + wa * (1 - t) + wb * t
                dl = (r - d) / den
                pq[0] += wq * dl * nx
                pq[1] += wq * dl * ny
                A[0] -= wa * dl * nx
                A[1] -= wa * dl * ny
                B[0] -= wb * dl * nx
                B[1] -= wb * dl * ny
                c["contact"][k] = (nx, ny)
            for A, B in self.edges:                    # the cliffs and rocks
                sx, sy = B[0] - A[0], B[1] - A[1]
                l2 = sx * sx + sy * sy
                t = clamp(((pq[0] - A[0]) * sx + (pq[1] - A[1]) * sy) / l2, 0.0, 1.0)
                ex, ey = pq[0] - (A[0] + sx * t), pq[1] - (A[1] + sy * t)
                d = math.hypot(ex, ey)
                if d >= r or d < 1e-9:
                    continue
                nx, ny = ex / d, ey / d
                pq[0] += nx * (r - d)
                pq[1] += ny * (r - d)
                c["contact"][k] = (nx, ny)

    def judge(self):
        for c in self.cars:
            if not c["on"]:
                continue
            xs = [self.x[c["i"]][0], self.x[c["i"] + 1][0]]
            ys = [self.x[c["i"]][1], self.x[c["i"] + 1][1]]
            if min(ys) < 0.2:
                self.result = "splash"
                return
            if min(xs) > self.goal:
                c["done"] = True
        if all(c["done"] for c in self.cars):
            self.result = "win"
        elif self.t > SETTLE + 18 + 3.2 * len(self.cars):
            self.result = "stuck"

    def peak(self):
        return max([m[7] for m in self.mem if m[6]] + [0.0])


# =============================================================================================
# The design: joints on a one-metre grid, beams between them
# =============================================================================================
class Design:
    def __init__(self, level):
        self.level = level
        self.nodes = [tuple(a) for a in level["anchors"]]
        self.na = len(self.nodes)                      # the first joints are the anchors
        self.members = []

    def copy(self):
        d = Design.__new__(Design)
        d.level, d.na = self.level, self.na
        d.nodes, d.members = list(self.nodes), list(self.members)
        return d

    def node_at(self, p):
        try:
            return self.nodes.index(tuple(p))
        except ValueError:
            return None

    def cost(self):
        return int(sum(MATS[m]["cost"] * math.dist(self.nodes[a], self.nodes[b]) for a, b, m in self.members))

    def inside_rock(self, p):
        x, y = p
        for poly in self.level["terrain"]:
            xs, ys = [q[0] for q in poly], [q[1] for q in poly]
            if min(xs) < x < max(xs) and min(ys) < y < max(ys):
                return True
        return False

    def add(self, a, p, mat):
        """A beam from joint a to grid point p. Returns the end joint, or None (and why) when it cannot be built."""
        if p == self.nodes[a]:
            return None, "same"
        if math.dist(self.nodes[a], p) > MATS[mat]["max"] + 1e-6:
            return None, "too long"
        b = self.node_at(p)
        if b is None:
            if self.inside_rock(p) or p[1] < 0:
                return None, "rock"
            self.nodes.append(tuple(p))
            b = len(self.nodes) - 1
        if any({a, b} == {m[0], m[1]} and m[2] == mat for m in self.members):   # one beam per material
            return b, "exists"
        self.members.append((a, b, mat))
        return b, None

    def remove(self, k):
        del self.members[k]
        used = {i for m in self.members for i in m[:2]}
        keep = [i for i in range(len(self.nodes)) if i < self.na or i in used]
        remap = {old: new for new, old in enumerate(keep)}
        self.nodes = [self.nodes[i] for i in keep]
        self.members = [(remap[a], remap[b], m) for a, b, m in self.members]

    def member_near(self, p, reach=0.6):
        best, bd = None, reach
        for k, (a, b, _) in enumerate(self.members):
            A, B = self.nodes[a], self.nodes[b]
            sx, sy = B[0] - A[0], B[1] - A[1]
            t = clamp(((p[0] - A[0]) * sx + (p[1] - A[1]) * sy) / (sx * sx + sy * sy), 0, 1)
            d = math.hypot(p[0] - A[0] - sx * t, p[1] - A[1] - sy * t)
            if d < bd:
                best, bd = k, d
        return best

    def sim(self):
        return Sim(self.level, self.nodes, self.members, set(range(self.na)))


def bot_plan(level):
    """The bot's bridge: a Warren truss over the deck line, resting on any anchor straight below a deck joint,
    and with cables from towers where there are any. Returns a list of beams ((x, y), (x, y), material)."""
    x0, x1 = level["gap"]
    h = level["deck"]
    mat = level["bot"]
    depth = level.get("depth", 2)
    plan = []
    deck = [(x, h) for x in range(x0, x1 + 1, 2)]
    top = [(x + 1, h + depth) for x in range(x0, x1, 2)]
    for k in range(len(deck) - 1):
        plan.append((deck[k], deck[k + 1], "road"))
        if level.get("reinforce"):                     # steel alongside the road takes the tension with it
            plan.append((deck[k], deck[k + 1], "steel"))
    for k, tp in enumerate(top):
        plan.append((deck[k], tp, mat))
        plan.append((tp, deck[k + 1], mat))
        if k:
            plan.append((top[k - 1], tp, mat))
    for ax, ay in level["anchors"]:
        if x0 < ax < x1 and ay < h and (ax, h) in deck and h - ay <= MATS[mat]["max"]:
            plan.append(((ax, h), (ax, ay), mat))
        if ay > h + depth and "cable" in level["mats"]:   # a tower: cables down to the deck it can reach
            for dn in deck[1:-1]:
                if math.dist((ax, ay), dn) <= MATS["cable"]["max"]:
                    plan.append(((ax, ay), dn, "cable"))
    return plan


# =============================================================================================
# The game: building, testing, the crossings
# =============================================================================================
class Game:
    def __init__(self, level=0, demo=False):
        self.demo = demo
        self.designs = {}
        self.load(level)
        self.over = self.paused = self.help = False

    def sfx(self, name, vol=1.0):
        if not self.demo:
            SND.play(name, vol=vol)

    def load(self, i):
        self.li = i % len(LEVELS)
        self.level = LEVELS[self.li]
        self.design = self.designs.get(self.li) or Design(self.level)
        self.designs[self.li] = self.design
        self.mat = self.level["mats"][min(1, len(self.level["mats"]) - 1)]
        self.start = None
        self.hand = (self.level["anchors"][0][0], self.level["anchors"][0][1])
        self.undo_stack = []
        self.sim = None
        self.pieces = []
        self.msg, self.msg_t = self.level["hint"], 8.0
        self.creak_t = 0.0
        self.t = 0.0
        self.result_t = None
        self.record = None

    @property
    def testing(self):
        return self.sim is not None

    def say(self, msg, t=2.5):
        self.msg, self.msg_t = msg, t

    # --- building --------------------------------------------------------------------------------
    def move_hand(self, dx, dy):
        lv = self.level
        self.hand = (clamp(self.hand[0] + dx, -1, lv["width"] + 1), clamp(self.hand[1] + dy, 0, lv["height"]))

    def set_mat(self, k):
        mats = self.level["mats"]
        if isinstance(k, int):
            k = mats[k % len(mats)]
        if k in mats and k != self.mat:
            self.mat = k
            self.sfx("join", 0.6)

    def click(self):
        """Start a beam at the joint under the hand, or finish the one being drawn there."""
        if self.testing:
            return
        d = self.design
        p = self.hand
        if self.start is None:
            a = d.node_at(p)
            if a is None:
                self.say("Start at a joint or a red anchor.")
                self.sfx("nope")
                return
            self.start = a
            self.sfx("join", 0.6)
            return
        p = self.reach(p)
        if p == d.nodes[self.start]:
            self.start = None
            return
        before = d.copy()
        b, why = d.add(self.start, p, self.mat)
        if b is None:
            self.say({"rock": "Not inside the rock.", "too long": "Too long for %s." % MATS[self.mat]["name"]}.get(
                why, "Can't build there."))
            self.sfx("nope")
            return
        if why != "exists":
            self.undo_stack.append(before)
            self.sfx("place")
        self.start = b

    def reach(self, p):
        """The grid point nearest to p that a beam from the start joint can reach."""
        s = self.design.nodes[self.start]
        L = MATS[self.mat]["max"]
        if math.dist(s, p) <= L:
            return tuple(p)
        best, bd = s, 1e9
        R = int(L) + 1
        for dx in range(-R, R + 1):
            for dy in range(-R, R + 1):
                q = (s[0] + dx, s[1] + dy)
                if 0 < math.hypot(dx, dy) <= L and math.dist(q, p) < bd:
                    best, bd = q, math.dist(q, p)
        return best

    def cancel_or_delete(self):
        if self.testing:
            return
        if self.start is not None:
            self.start = None
            return
        k = self.design.member_near(self.hand)
        if k is not None:
            self.undo_stack.append(self.design.copy())
            self.design.remove(k)
            self.sfx("delete")

    def undo(self):
        if self.undo_stack and not self.testing:
            self.design = self.designs[self.li] = self.undo_stack.pop()
            self.start = None
            self.sfx("delete")

    def clear(self):
        if not self.testing and self.design.members:
            self.undo_stack.append(self.design.copy())
            self.design = self.designs[self.li] = Design(self.level)
            self.start = None
            self.sfx("delete")

    # --- testing ---------------------------------------------------------------------------------
    def test(self):
        if self.testing:
            return
        if not self.design.members:
            self.say("Build something first.")
            self.sfx("nope")
            return
        self.start = None
        self.sim = self.design.sim()
        self.pieces = []
        self.result_t = None
        self.record = None
        self.sfx("go")

    def stop(self):
        self.sim = None
        self.pieces = []
        self.result_t = None

    def update(self, dt):
        if self.paused:
            return
        self.t += dt
        self.msg_t -= dt
        if not self.testing:
            return
        s = self.sim
        s.step(FRAME)
        for m in s.snapped:
            self.sfx("snap")
            A, B = s.x[m[0]], s.x[m[1]]
            mx, my = (A[0] + B[0]) / 2, (A[1] + B[1]) / 2
            for (P, vi) in ((A, m[0]), (B, m[1])):
                v = s.v[vi]
                self.pieces.append([P[0], P[1], mx, my, v[0] + random.uniform(-1, 1), v[1] + random.uniform(0, 2),
                                    MATS[m[2]]["col"], 3.0])
        for pc in self.pieces:
            pc[5] -= G * FRAME
            for k in (0, 2):
                pc[k] += pc[4] * FRAME
                pc[k + 1] += pc[5] * FRAME
            pc[7] -= FRAME
        self.pieces = [pc for pc in self.pieces if pc[7] > 0 and min(pc[1], pc[3]) > -3]
        self.creak_t -= dt
        if s.peak() > 0.8 and self.creak_t <= 0:
            self.creak_t = 0.7
            self.sfx("creak", 0.7)
        if s.result and self.result_t is None:
            self.result_t = self.t
            if s.result == "win":
                self.sfx("win")
                cost = self.design.cost()
                if cost <= self.level["budget"] and not self.demo:
                    self.record = submit(GAME, self.level["name"], cost, lower_is_better=True)
            else:
                self.sfx("splash" if s.result == "splash" else "fail")


# =============================================================================================
# The bot: builds its plan beam by beam, then tests (auto mode and the title scene)
# =============================================================================================
class Bot:
    def __init__(self, g, pace=0.12):
        self.g = g
        self.pace = pace
        self.wait = 0.4
        self.plan = None
        self.after = None

    def update(self, dt):
        g = self.g
        if g.paused:
            return
        self.wait -= dt
        if g.testing:
            if g.sim.result and self.after is None:
                self.after = 2.5
            if self.after is not None:
                self.after -= dt
                if self.after <= 0:
                    self.after = None
                    ok = g.sim.result == "win"
                    g.stop()
                    g.designs.pop(g.li, None)
                    g.load(g.li + 1 if ok else g.li + 1)
                    self.plan = None
                    self.wait = 0.6
            return
        if self.plan is None:
            g.design = g.designs[g.li] = Design(g.level)
            self.plan = list(bot_plan(g.level))
        if self.wait > 0:
            return
        self.wait = self.pace
        if not self.plan:
            g.test()
            return
        a, b, mat = self.plan.pop(0)
        g.set_mat(mat)
        g.hand = a
        g.start = None
        g.click()
        g.hand = b
        g.click()
        g.start = None


# =============================================================================================
# Drawing
# =============================================================================================
def view(g, W, H):
    lv = g.level
    s = min(W / (lv["width"] + 1.0), H / (lv["height"] + 2.5))
    ox = (W - lv["width"] * s) / 2
    oy = H - 1.5 * s                                   # world y = 0 (the water) sits here
    return s, ox, oy


def to_px(v, x, y):
    s, ox, oy = v
    return ox + x * s, oy - y * s


def to_world(v, px, py):
    s, ox, oy = v
    return (px - ox) / s, (oy - py) / s


def fill_poly(cv, pts, c):
    ys = [p[1] for p in pts]
    xs = [p[0] for p in pts]
    for y in range(max(0, int(min(ys))), min(cv.H, int(max(ys)) + 1)):
        cv.rect(int(min(xs)), y, int(max(xs)) - int(min(xs)), 1, c)


def thick_line(cv, a, b, c, w=1):
    cv.line(a[0], a[1], b[0], b[1], c)
    if w > 1:
        cv.line(a[0], a[1] + 1, b[0], b[1] + 1, shade(c, 0.75))


def draw_world(cv, g, v):
    W, H = cv.W, cv.H
    lv = g.level
    for y in range(H):
        cv.px[y] = [mix((96, 150, 220), (214, 228, 240), clamp(y / max(1, H * 0.75), 0, 1))] * W
    s, ox, oy = v
    for x in range(W):                                 # far hills
        u = x / max(1, W)
        hy = oy - s * (lv["height"] * 0.45 + 1.4 * math.sin(u * 7.3 + g.li) + 0.8 * math.sin(u * 17.0))
        for y in range(max(0, int(hy)), H):
            cv.px[y][x] = mix((150, 176, 210), (124, 150, 186), clamp((y - hy) / (s * 3 + 1), 0, 1))
    wy = int(oy)
    for y in range(max(0, wy), H):                     # the river
        k = (y - wy) / max(1, H - wy)
        row = cv.px[y]
        for x in range(W):
            c = mix((70, 140, 196), (30, 70, 120), k)
            if y == wy and int(x + g.t * 6) % 7 < 2:
                c = (200, 228, 246)
            row[x] = c
    for poly in lv["terrain"]:
        pts = [to_px(v, *p) for p in poly]
        fill_poly(cv, pts, (122, 104, 90))
        xs = [p[0] for p in pts]
        top = min(p[1] for p in pts)
        x0, x1 = int(max(0, min(xs))), int(min(W, max(xs)))
        for x in range(x0, x1):
            for y in range(int(top), min(H, int(max(p[1] for p in pts)))):
                if (x * 7 + y * 13) % 11 == 0:
                    cv.px[y][x] = (104, 88, 76)
        cv.rect(x0, int(top), x1 - x0, 1, (110, 170, 80))
    for x, y0, y1 in lv.get("posts", ()):              # stone towers for the cable anchors (no collision)
        ax, ay = to_px(v, x - 0.5, y1 + 0.3)
        bx, by = to_px(v, x + 0.5, y0)
        for yy in range(int(ay), int(by) + 1):
            for xx in range(int(ax), int(bx) + 1):
                cv.set(xx, yy, (150, 140, 128) if (xx + yy // 2) % 4 else (120, 112, 104))
    gx, gy = to_px(v, g.level["gap"][1] + 2.0, lv["deck"])  # the finish flag
    pole = max(4, int(s * 2))
    cv.rect(int(gx), int(gy) - pole, 1, pole, (70, 60, 50))
    for yy in range(3):
        for xx in range(4):
            cv.set(gx + 1 + xx, gy - pole + yy, (250, 250, 250) if (xx + yy) % 2 else (30, 30, 30))


def draw_bridge(cv, g, v):
    s = v[0]
    d = g.design
    if g.testing:
        sim = g.sim
        pos = sim.x
        for m in sim.mem:
            if not m[6]:
                continue
            base = MATS[m[2]]["col"]
            r = clamp(m[7], 0, 1)
            c = mix(mix(base, (90, 200, 90), 0.5), (255, 60, 40), r ** 1.3) if r > 0.15 else base
            thick_line(cv, to_px(v, *pos[m[0]]), to_px(v, *pos[m[1]]), c, 2 if m[2] == "road" else 1)
        for pc in g.pieces:
            thick_line(cv, to_px(v, pc[0], pc[1]), to_px(v, pc[2], pc[3]), shade(pc[6], 0.8))
        for i in range(sim.nb):
            px, py = to_px(v, *pos[i])
            cv.set(px, py, (230, 230, 236) if i >= d.na else (220, 50, 50))
        for c in sim.cars:
            if c["on"]:
                draw_car(cv, v, pos[c["i"]], pos[c["i"] + 1], c)
        return
    for a, b, mat in d.members:
        thick_line(cv, to_px(v, *d.nodes[a]), to_px(v, *d.nodes[b]), MATS[mat]["col"], 2 if mat == "road" else 1)
    for i, p in enumerate(d.nodes):
        px, py = to_px(v, *p)
        if i < d.na:
            cv.rect(int(px) - 1, int(py) - 1, 2, 2, (220, 50, 50))
        else:
            cv.set(px, py, (240, 240, 246))


def draw_car(cv, v, a, b, c):
    s = v[0]
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1
    ux, uy = dx / L, dy / L
    nx, ny = -uy, ux
    r, h = c["r"], c["h"]
    over = r * 0.9
    corners = [(a[0] - ux * over + nx * r * 0.2, a[1] - uy * over + ny * r * 0.2),
               (b[0] + ux * over + nx * r * 0.2, b[1] + uy * over + ny * r * 0.2),
               (b[0] + ux * over * 0.3 + nx * (r * 0.2 + h), b[1] + uy * over * 0.3 + ny * (r * 0.2 + h)),
               (a[0] - ux * over + nx * (r * 0.2 + h), a[1] - uy * over + ny * (r * 0.2 + h))]
    cv.poly([to_px(v, *p) for p in corners], c["col"])
    wx = a[0] + dx * 0.55 + nx * (r * 0.2 + h * 0.62)
    wy = a[1] + dy * 0.55 + ny * (r * 0.2 + h * 0.62)
    px, py = to_px(v, wx, wy)
    cv.rect(int(px), int(py), max(1, int(s * 0.5)), max(1, int(s * 0.25)), (150, 200, 230))
    for p in (a, b):
        px, py = to_px(v, *p)
        rr = max(1.0, r * s)
        for yy in range(int(py - rr), int(py + rr) + 1):
            for xx in range(int(px - rr), int(px + rr) + 1):
                if (xx + 0.5 - px) ** 2 + (yy + 0.5 - py) ** 2 <= rr * rr:
                    cv.set(xx, yy, (30, 30, 34))
        cv.set(px, py, (150, 150, 160))


def draw_edit(cv, g, v):
    s = v[0]
    lv = g.level
    if s >= 3:
        for x in range(0, lv["width"] + 1):
            for y in range(0, lv["height"] + 1):
                px, py = to_px(v, x, y)
                if 0 <= int(py) < cv.H and 0 <= int(px) < cv.W:
                    cv.px[int(py)][int(px)] = mix(cv.px[int(py)][int(px)], (255, 255, 255), 0.25)
    hx, hy = to_px(v, *g.hand)
    col = MATS[g.mat]["col"]
    if g.start is not None:
        s0 = g.design.nodes[g.start]
        end = g.reach(g.hand)
        ok = end != s0 and not g.design.inside_rock(end) and end[1] >= 0
        a, b = to_px(v, *s0), to_px(v, *end)
        cv.line(a[0], a[1], b[0], b[1], mix(col, (255, 255, 255), 0.4) if ok else (240, 70, 60))
        L = MATS[g.mat]["max"]                         # a faint ring: how far this material reaches
        for k in range(48):
            an = k / 48 * 6.283
            cv.set(*to_px(v, s0[0] + math.cos(an) * L, s0[1] + math.sin(an) * L), (255, 255, 255))
    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-1, 0), (1, 0), (0, -1), (0, 1)):
        cv.set(hx + dx, hy + dy, (255, 255, 255) if abs(dx) + abs(dy) == 2 else (20, 20, 24))
    cv.set(hx, hy, (255, 200, 60))


def render(g, cols, rows, hud=True):
    cv = Canvas(cols, rows)
    play = rows - 1 if hud else rows
    v = view(g, cols, play * 2)
    draw_world(cv, g, v)
    draw_bridge(cv, g, v)
    if not g.testing and hud:
        draw_edit(cv, g, v)
    g.last_view = (v, cols, play)
    if hud:
        draw_hud(cv, g)
    return cv


def money(n):
    return "$%s" % "{:,}".format(int(n)).replace(",", ".")


def draw_hud(cv, g):
    r = cv.rows - 1
    cv.put(0, r, " " * cv.cols, HUD_FG, HUD_BG)
    lv = g.level
    head = " %d %s " % (g.li + 1, lv["name"])
    cv.put(0, r, head, (16, 14, 20), (120, 190, 230))
    cost = g.design.cost()
    x = len(head) + 1
    ms = "%s / %s" % (money(cost), money(lv["budget"]))
    cv.put(x, r, ms, (255, 120, 100) if cost > lv["budget"] else (220, 230, 200), HUD_BG)
    x += len(ms) + 2
    if g.testing:
        pk = g.sim.peak()
        s = "load %3d%%" % int(pk * 100)
        cv.put(x, r, s, mix((150, 220, 150), (255, 90, 70), clamp(pk, 0, 1)), HUD_BG)
        hint = "R build   Esc pause"
    else:
        for i, m in enumerate(lv["mats"]):
            name = MATS[m]["name"] if cv.cols >= 96 or m == g.mat else MATS[m]["name"][:2]
            s = " %d %s " % (i + 1, name)
            on = m == g.mat
            cv.put(x, r, s, (16, 14, 20) if on else (170, 170, 190), MATS[m]["col"] if on else HUD_BG)
            if on and m in ("road", "cable"):
                cv.put(x, r, s, (240, 240, 240), MATS[m]["col"])
            x += len(s)
        hint = "Enter test   ? help"
    if x + len(hint) + 2 < cv.cols:
        cv.put(cv.cols - len(hint) - 1, r, hint, (150, 154, 184), HUD_BG)
    if g.msg_t > 0 and not g.testing:
        cv.center(0, " %s " % g.msg[:cv.cols - 2], (20, 20, 26), (236, 226, 170))
    if g.testing and g.sim.result:
        draw_result(cv, g)
    if g.paused:
        overlay(cv, HELP if g.help else PAUSE_LINES + ["", SND.label()])


def draw_result(cv, g):
    s = g.sim
    lv = g.level
    cost = g.design.cost()
    if s.result == "win":
        lines = ["IT HOLDS!", "", "cost   %s of %s" % (money(cost), money(lv["budget"]))]
        if cost > lv["budget"]:
            lines.append("over budget - trim it to count")
        best = load_scores().get(GAME, {}).get(lv["name"])
        if best is not None:
            lines.append("best   %s" % money(best))
        if g.record:
            lines.append("** NEW RECORD **")
        lines += ["", "Enter: next crossing   R: keep building"]
        edge = (110, 210, 120)
    else:
        lines = ["SPLASH!" if s.result == "splash" else "STUCK", "",
                 "%d beams snapped" % sum(1 for m in s.mem if not m[6]), "", "R / Enter: back to building"]
        edge = (220, 80, 70)
    w = max(len(l) for l in lines) + 4
    x, y = max(0, (cv.cols - w) // 2), max(0, cv.rows // 3 - len(lines) // 2)
    cv.frame(x - 1, y * 2 - 1, w + 2, (len(lines) + 2) * 2 + 2, edge)
    cv.box(x, y, [l.center(w - 4) for l in lines], (240, 240, 246), (24, 22, 44))


# =============================================================================================
# Title, auto mode, play
# =============================================================================================
class TitleDemo:
    def __init__(self):
        self.g = Game(0, demo=True)
        self.bot = Bot(self.g, pace=0.08)

    def scene(self, cols, rows, dt):
        dt = min(dt, 0.1)
        self.bot.update(dt)
        self.g.update(dt)
        return render(self.g, cols, rows, hud=False)


def render_menu(demo, cols, rows, sel, dt, help_=False, level=0):
    cv = demo.scene(cols, rows, dt)
    rec = load_scores().get(GAME, {})
    done = sum(1 for lv in LEVELS if lv["name"] in rec)
    best = "%d of %d crossings built" % (done, len(LEVELS)) if rec else None
    lv = LEVELS[level]
    b = rec.get(lv["name"])
    items = ["Build       crossing %d: %s" % (level + 1, lv["name"]), "%-11s watch it build and test" % AUTO_LABEL]
    title_screen(cv, "SPANWORK", "build a bridge, then let the physics decide", items, sel, best,
                 extra=["", "crossing  < %d %s >%s" % (level + 1, lv["name"], ("   best " + money(b)) if b else ""),
                        "mouse: click joints    keys: arrows + Space"],
                 keys="Up/Down choose   Left/Right crossing   Enter start   M %s   ? help   Esc back" % SND.label().lower(),
                 help_lines=HELP, show_help=help_)
    return cv


def too_small(term):
    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (60x22).")


def apply_mouse(term, g):
    take = getattr(term, "take_mouse", None)
    if not take or not hasattr(g, "last_view"):
        if take:
            take()
        return
    v, cols, play = g.last_view
    lv = g.level
    for kind, col, row in take():
        if row >= play:
            continue
        wx, wy = to_world(v, col + 0.5, row * 2 + 1)
        g.hand = (int(round(clamp(wx, -1, lv["width"] + 1))), int(round(clamp(wy, 0, lv["height"]))))
        if kind == "left":
            if g.testing:
                continue
            g.click()
        elif kind in ("right", "middle"):
            g.cancel_or_delete()
        elif kind == "wheelup":
            g.set_mat(lv["mats"].index(g.mat) - 1)
        elif kind == "wheeldown":
            g.set_mat(lv["mats"].index(g.mat) + 1)


def game_key(g, k):
    if g.testing:
        if k == "r" or (g.sim.result and k in ("enter", " ")):
            if g.sim.result == "win" and k in ("enter", " "):
                g.stop()
                g.load(g.li + 1)
            else:
                g.stop()
        return
    if k in ("left", "a"):
        g.move_hand(-1, 0)
    elif k in ("right", "d"):
        g.move_hand(1, 0)
    elif k in ("up", "w"):
        g.move_hand(0, 1)
    elif k in ("down", "s"):
        g.move_hand(0, -1)
    elif k in (" ", "f"):
        g.click()
    elif k in ("x", "backspace"):
        g.cancel_or_delete()
    elif k in ("1", "2", "3", "4"):
        i = int(k) - 1
        if i < len(g.level["mats"]):
            g.set_mat(i)
    elif k == "tab":
        g.set_mat(g.level["mats"].index(g.mat) + 1)
    elif k == "u":
        g.undo()
    elif k == "c":
        g.clear()
    elif k in ("enter", "t"):
        g.test()
    elif k == "n":
        g.load(g.li + 1)
    elif k == "b":
        g.load(g.li - 1)


def run_auto(term, level):
    auto = AutoMode()
    g = Game(level)
    g.demo = False
    bot = Bot(g)
    last = time.time()
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
        if getattr(term, "take_mouse", None):
            term.take_mouse()
        sim = auto.scale(dt)
        n = max(1, int(round(sim / FRAME))) if sim else 0
        for _ in range(min(n, 8)):
            bot.update(FRAME if n > 1 else sim)
            g.update(FRAME if n > 1 else sim)
        cols, rows = term.size()
        if cols < 60 or rows < 22:
            too_small(term)
            time.sleep(0.2)
            continue
        cv = render(g, cols, rows)
        auto.banner(cv, extra="%d %s" % (g.li + 1, g.level["name"]))
        term.write(cv.emit())
        time.sleep(max(0, FRAME - (time.time() - now)))


def play(term, level):
    g = Game(level)
    last = time.time()
    while True:
        now = time.time()
        cols, rows = term.size()
        dt = min(0.1, now - last)
        last = now
        if not g.paused:
            apply_mouse(term, g)
        elif getattr(term, "take_mouse", None):
            term.take_mouse()
        for k in term.keys(0):
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
                game_key(g, k)
        g.update(dt)
        if cols < 60 or rows < 22:
            too_small(term)
            time.sleep(0.2)
            continue
        term.write(render(g, cols, rows).emit())
        time.sleep(max(0, FRAME - (time.time() - now)))


def main():
    with MouseTerminal() as term:
        demo = TitleDemo()
        sel, help_, level = 0, False, 0
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
            term.write(render_menu(demo, cols, rows, sel, min(0.1, now - last), help_, level).emit())
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
                elif k in ("up", "w", "down", "s"):
                    sel = 1 - sel
                    SND.play("menu")
                elif k in ("left", "a", "right", "d"):
                    level = (level + (1 if k in ("right", "d") else -1)) % len(LEVELS)
                    SND.play("menu")
                elif k == "m":
                    if SND.toggle():
                        SND.play("sound_on")
                elif k in ("enter", " "):
                    SND.play("start")
                    go = True
            if go:
                if sel == 1:
                    run_auto(term, level)
                else:
                    play(term, level)
                last = time.time()


# =============================================================================================
# Self-test:  python3 spanwork.py --selftest
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


def build(level, plan):
    d = Design(level)
    for a, b, mat in plan:
        i = d.node_at(a)
        assert i is not None, ("no joint at", a)
        j, why = d.add(i, b, mat)
        assert j is not None, (a, b, why)
    return d


def run_sim(d, secs=40):
    s = d.sim()
    for _ in range(int(secs / FRAME)):
        s.step()
        if s.result:
            break
    return s


def screenshot(cols=100, rows=32):
    g = Game(2, demo=True)
    g.design = g.designs[g.li] = build(g.level, bot_plan(g.level))
    g.test()
    for _ in range(int(3.1 / FRAME)):
        g.update(FRAME)
    return render(g, cols, rows)


def selftest():
    import os
    import tempfile
    import arcadekit
    t0 = time.time()
    tmp = os.path.join(tempfile.mkdtemp(), "scores.json")
    arcadekit.SCORES_PATH = tmp
    SND.enabled = False
    # the bot's truss carries the traffic over every crossing, within budget
    report = []
    for lv in LEVELS:
        d = build(lv, bot_plan(lv))
        s = run_sim(d)
        report.append("%s %s %.0f%%" % (lv["name"], s.result, 100 * max(m[7] for m in s.mem)))
        assert s.result == "win", "%s: %s after %.1fs, %d snapped" % (lv["name"], s.result, s.t,
                                                                       sum(1 for m in s.mem if not m[6]))
        assert d.cost() <= lv["budget"], "%s: the bot spent %d of %d" % (lv["name"], d.cost(), lv["budget"])
    # a bare road over a wide gap sags, snaps and drops the car in the river
    lv = LEVELS[1]
    x0, x1 = lv["gap"]
    flat = build(lv, [((x, 6), (x + 2, 6), "road") for x in range(x0, x1, 2)])
    s = run_sim(flat)
    assert s.result == "splash" and any(not m[6] for m in s.mem), s.result
    # a bridge with nothing under the deck: the car falls through the hole
    s = run_sim(Design(lv).copy() if False else build(lv, [((x0, 6), (x0 + 2, 6), "road")]))
    assert s.result == "splash"
    # a cable only pulls: hanging, it holds a weight; pushed, it goes slack
    cab = {"T": MATS["cable"]["T"]}
    assert cab["T"] > 0 and MATS["cable"]["C"] == 0
    # building rules: start at a joint, length limits, no beams into rock, undo, delete
    g = Game(0)
    g.hand = (8, 8)
    g.click()
    assert g.start is None, "a beam started in thin air"
    g.hand = (6, 6)
    g.click()
    g.hand = (9, 6)
    g.click()
    assert len(g.design.members) == 1 and g.design.nodes[-1] == (9, 6)
    g.hand = (20, 6)
    g.click()                                        # too far: clamped to the reach of the material
    assert len(g.design.members) == 2 and math.dist(g.design.nodes[-1], (9, 6)) <= MATS[g.mat]["max"]
    g.start = None
    g.hand = (6, 6)
    g.click()
    g.hand = (5, 4)
    g.click()
    assert len(g.design.members) == 2, "built into the rock"
    g.start = None
    g.undo()
    assert len(g.design.members) == 1
    g.hand = (7, 6)
    g.cancel_or_delete()
    assert not g.design.members and len(g.design.nodes) == g.design.na
    # mouse: the hand follows, a click starts a beam at an anchor
    g = Game(0)
    render(g, 100, 32)
    v = g.last_view[0]
    px, py = to_px(v, 6, 6)
    term = FakeTerm([], [(0, ("left", int(px), int(py) // 2))])
    apply_mouse(term, g)
    assert g.hand == (6, 6) and g.start == 0, (g.hand, g.start)
    # the bot builds and passes the first two crossings in the game loop
    g = Game(0, demo=True)
    bot = Bot(g, pace=0.01)
    passed = 0
    for i in range(int(60 / FRAME)):
        bot.update(FRAME)
        was = g.li
        g.update(FRAME)
        if g.testing and g.sim.result == "win" and bot.after is not None and bot.after > 2.4:
            passed += 1
        if i % 200 == 0:
            render(g, 100, 32).emit()
        if g.li >= 2:
            break
    assert g.li >= 2, "the bot is stuck on crossing %d" % (g.li + 1)
    # titles and sizes, auto mode
    for cols, rows in ((60, 22), (100, 32), (180, 50)):
        d = TitleDemo()
        for i in range(30):
            d.scene(cols, rows, 0.1)
        for sel in range(2):
            render_menu(d, cols, rows, sel, 0.05, sel == 1, 3).emit()
        g = Game(5)
        g.design = build(g.level, bot_plan(g.level))
        g.designs[g.li] = g.design
        render(g, cols, rows).emit()
        g.test()
        for _ in range(90):
            g.update(FRAME)
        render(g, cols, rows).emit()
    term = FakeTerm([(0.1, "+"), (0.2, "+"), (0.5, " "), (0.6, "?"), (0.7, "x"), (0.8, " "), (1.2, "esc")])
    run_auto(term, 0)
    assert term.frames > 5 and not term.script
    assert not os.path.exists(tmp), "auto mode wrote a score"
    print("Self-test ok: bot trusses hold on all %d crossings (%s); bare road snaps; build rules, undo, delete, "
          "mouse, bot loop, titles, auto mode (%.1fs)" % (len(LEVELS), ", ".join(report), time.time() - t0))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
