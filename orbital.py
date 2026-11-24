#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""ORBITAL - a calm gravity puzzle among the planets.

A little star system seen from above: planets of every size pull on your probe, moons circle, asteroid belts
and wormholes wait in between. Set the launch angle and power, launch, and watch gravity bend the path. The dotted
line only shows the first part of the flight, so every level is a small puzzle: read the planets, launch, adjust
a little, launch again. Reach the dock ring in as few launches as you can.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
Run:        python3 orbital.py
Self-test:  python3 orbital.py --selftest
Benchmark:  python3 orbital.py --bench
"""
import math
import random
import sys
import time

from arcadekit import (AUTO_LABEL, AutoMode, Canvas, Terminal, clamp, load_scores, mix, overlay, shade, shared_key, submit,
                       title_screen)
from arcadesound import Sound

GAME = "orbital"
LEVELS_KEY = "orbital-levels"       # stars per level live here, totals under "orbital"
TAU = 2 * math.pi

# =============================================================================================
# The physics: world units, independent of the window. The map is WW x WH, y grows downwards.
# =============================================================================================
WW, WH = 1.6, 1.0
DT = 1 / 200                        # fixed time step (semi-implicit Euler)
MAX_T = 12.0                        # after this the probe drifts out of signal range
MAX_STEPS = int(MAX_T / DT)
VMAX = 0.9                          # launch speed at 100 % power (world units per second)
PROBE_R = 0.006
DOCK_R = 0.036                      # capture radius of the dock ring
BEACON_R = 0.032
HOLE_R = 0.032
NUDGE_STEPS = 50                    # a nudge burns for 0.25 s ...
NUDGE_ACC = 0.7                     # ... along the direction of flight: +0.175 speed

# Sounds: calm and soft, sine and triangle bells. Aim ticks are nearly silent and never machine-gun (gap).
_C = [523.25, 659.25, 783.99, 1046.5, 1318.5]     # C major, for chimes that rise in order
SND = Sound(GAME, {
    "tick": [dict(w="tri", f=1500, d=0.012, v=0.08)],
    "tick_up": [dict(w="sine", f=900, f2=1000, d=0.015, v=0.09)],
    "tick_down": [dict(w="sine", f=800, f2=720, d=0.015, v=0.09)],
    "launch": [dict(w="noise", f=2600, f2=700, d=0.4, v=0.2, a=0.06, r="lin"),
               dict(w="sine", f=220, f2=440, d=0.3, v=0.12, a=0.04, at=0)],
    "nudge": [dict(w="noise", f=1800, f2=600, d=0.18, v=0.18, a=0.01), dict(w="sine", f=330, f2=380, d=0.12, v=0.1, at=0)],
    "empty": [dict(w="tri", f=300, d=0.03, v=0.12)],
    "wormhole": [dict(w="sine", f=300, f2=1200, d=0.45, v=0.22, vib=(14, 1.5), a=0.03),
                 dict(w="tri", f=1200, f2=500, d=0.3, v=0.12, vib=(9, 1.0))],
    "beacon1": [dict(w="sine", f=_C[1], d=0.25, v=0.24), dict(w="sine", f=_C[1] * 2, d=0.15, v=0.06, at=0)],
    "beacon2": [dict(w="sine", f=_C[2], d=0.25, v=0.24), dict(w="sine", f=_C[2] * 2, d=0.15, v=0.06, at=0)],
    "beacon3": [dict(w="sine", f=_C[3], d=0.25, v=0.24), dict(w="sine", f=_C[3] * 2, d=0.15, v=0.06, at=0)],
    "dock1": [dict(w="tri", f=_C[0], d=0.12, v=0.26), dict(w="tri", f=_C[2], d=0.14, v=0.26),
              dict(w="sine", f=_C[3], d=0.6, v=0.24, at=0.4)],
    "dock2": [dict(w="tri", f=_C[0], d=0.12, v=0.26), dict(w="tri", f=_C[2], d=0.14, v=0.26),
              dict(w="sine", f=_C[3], d=0.3, v=0.24, at=0.4), dict(w="sine", f=_C[4], d=0.6, v=0.24, at=0.6)],
    "dock3": [dict(w="tri", f=_C[0], d=0.12, v=0.26), dict(w="tri", f=_C[2], d=0.14, v=0.26),
              dict(w="sine", f=_C[3], d=0.3, v=0.24, at=0.4), dict(w="sine", f=_C[4], d=0.3, v=0.24, at=0.6),
              dict(w="sine", f=1567.98, d=0.42, v=0.22, at=0.8, vib=(5, 0.1))],
    "crash": [dict(w="sine", f=120, f2=45, d=0.35, v=0.4), dict(w="noise", f=700, f2=120, d=0.25, v=0.18, at=0)],
    "lost": [dict(w="sine", f=660, f2=330, d=0.9, v=0.18, r="lin", vib=(3, 0.2))],
    "abort": [dict(w="tri", f=440, f2=330, d=0.1, v=0.14)],
    "level": [dict(w="sine", f=_C[0], d=0.12, v=0.2), dict(w="sine", f=_C[1], d=0.12, v=0.2),
              dict(w="sine", f=_C[2], d=0.3, v=0.2)],
    "sound_on": [dict(w="sine", f=660, d=0.07, v=0.26), dict(w="sine", f=990, d=0.14, v=0.24)],
})
ANGLE_STEP, POWER_STEP = 0.5, 0.5   # one tap on the arrow keys
POWER_MIN, POWER_MAX = 10.0, 100.0

KINDS = {  # base colour, second colour, gravity per area (GM / r^2)
    "rock": ((178, 146, 112), (120, 96, 80), 9.0),
    "ocean": ((64, 124, 206), (86, 160, 96), 8.5),
    "gas": ((214, 176, 126), (170, 118, 84), 6.0),
    "ice": ((196, 224, 242), (140, 182, 220), 7.0),
    "lava": ((96, 44, 36), (255, 130, 50), 10.0),
    "violet": ((156, 124, 222), (104, 84, 176), 6.0),
    "teal": ((90, 196, 180), (50, 130, 140), 7.5),
}


class Level:
    """Everything that describes one puzzle. All positions in world units."""

    def __init__(self, num, name, hint, launch, planets, beacons, moons=(), rocks=(), holes=(), fuel=0,
                 preview=2.0, aim=(0.0, 50.0), solution=None):
        self.num, self.name, self.hint = num, name, hint
        self.launch = launch
        # planets: (x, y, r, gm, kind, ring)
        self.planets = [(x, y, r, KINDS[k][2] * r * r if gm is None else gm, k, ring)
                        for (x, y, r, gm, k, ring) in planets]
        self.beacons = list(beacons)        # in order; the last one is the dock ring
        self.moons = list(moons)            # (host_x, host_y, orbit, phase, omega, r, gm)
        self.rocks = list(rocks)            # (x, y, r)
        self.holes = list(holes)            # ((ax, ay), (bx, by))
        self.fuel = fuel
        self.preview = preview              # seconds of flight shown by the dotted line
        self.aim = aim                      # angle / power when the level opens
        self.solution = solution            # a known solution (generated levels), for the tests
        self.station = True

    def moon_pos(self, m, t):
        hx, hy, R, a0, w = m[0], m[1], m[2], m[3], m[4]
        return hx + R * math.cos(a0 + w * t), hy + R * math.sin(a0 + w * t)


class Flight:
    """One launch, stepped with a fixed time step: the same code runs the preview, the real flight and the tests."""

    def __init__(self, L, angle, power):
        self.L = L
        a = math.radians(angle)
        v = power / 100.0 * VMAX
        self.x, self.y = L.launch
        self.vx, self.vy = math.cos(a) * v, -math.sin(a) * v
        self.t = 0.0
        self.steps = 0
        self.nb = 0                      # next beacon to pass
        self.fuel = L.fuel
        self.thrust = 0
        self.outcome = None              # dock / planet / moon / rock / lost / time
        self.path = [(self.x, self.y)]   # None marks a jump through a wormhole
        self.inside = None               # the wormhole mouth we just came out of
        self.passed = []                 # (beacon index, step)

    def nudge(self):
        if self.fuel > 0 and self.outcome is None and self.thrust == 0:
            self.fuel -= 1
            self.thrust = NUDGE_STEPS
            return True
        return False

    def run(self, n):
        """Advance up to n steps (stops at the end of the flight). Returns the number of steps done."""
        L = self.L
        planets = [(p[0], p[1], (p[2] + PROBE_R) ** 2, p[3]) for p in L.planets]
        moons, rocks, holes, beacons = L.moons, L.rocks, L.holes, L.beacons
        x, y, vx, vy, t = self.x, self.y, self.vx, self.vy, self.t
        path = self.path
        sqrt, cos, sin = math.sqrt, math.cos, math.sin
        done = 0
        outcome = self.outcome
        while done < n and outcome is None:
            ax = ay = 0.0
            for px, py, r2, gm in planets:
                dx, dy = px - x, py - y
                d2 = dx * dx + dy * dy
                k = gm / (d2 * sqrt(d2))
                ax += dx * k
                ay += dy * k
            mpos = []
            for m in moons:
                mx, my = m[0] + m[2] * cos(m[3] + m[4] * t), m[1] + m[2] * sin(m[3] + m[4] * t)
                mpos.append((mx, my, m[5]))
                if m[6]:
                    dx, dy = mx - x, my - y
                    d2 = dx * dx + dy * dy + 1e-6
                    k = m[6] / (d2 * sqrt(d2))
                    ax += dx * k
                    ay += dy * k
            if self.thrust > 0:
                self.thrust -= 1
                sp = sqrt(vx * vx + vy * vy) or 1.0
                ax += vx / sp * NUDGE_ACC
                ay += vy / sp * NUDGE_ACC
            vx += ax * DT
            vy += ay * DT
            x += vx * DT
            y += vy * DT
            t += DT
            done += 1
            path.append((x, y))
            # what did we run into?
            for px, py, r2, gm in planets:
                if (px - x) ** 2 + (py - y) ** 2 < r2:
                    outcome = "planet"
            for mx, my, mr in mpos:
                if (mx - x) ** 2 + (my - y) ** 2 < (mr + PROBE_R) ** 2:
                    outcome = "moon"
            for rx, ry, rr in rocks:
                if (rx - x) ** 2 + (ry - y) ** 2 < (rr + PROBE_R) ** 2:
                    outcome = "rock"
            if outcome:
                break
            if not (0.0 <= x <= WW and 0.0 <= y <= WH):
                outcome = "lost"
                break
            if holes:
                if self.inside is not None:
                    hx, hy = holes[self.inside[0]][self.inside[1]]
                    if (hx - x) ** 2 + (hy - y) ** 2 > (HOLE_R * 1.6) ** 2:
                        self.inside = None
                for i, pair in enumerate(holes):
                    for e in (0, 1):
                        if self.inside == (i, e):
                            continue
                        hx, hy = pair[e]
                        if (hx - x) ** 2 + (hy - y) ** 2 < HOLE_R * HOLE_R:
                            x, y = pair[1 - e]
                            self.inside = (i, 1 - e)
                            path.append(None)
                            path.append((x, y))
                            break
                    else:
                        continue
                    break
            if self.nb < len(beacons):
                bx, by = beacons[self.nb]
                last = self.nb == len(beacons) - 1
                rad = DOCK_R if last else BEACON_R
                if (bx - x) ** 2 + (by - y) ** 2 < rad * rad:
                    self.passed.append((self.nb, self.steps + done))
                    self.nb += 1
                    if last:
                        outcome = "dock"
                        break
            if t >= MAX_T - 1e-9:
                outcome = "time"
        self.x, self.y, self.vx, self.vy, self.t = x, y, vx, vy, t
        self.steps += done
        self.outcome = outcome
        return done

    def finish(self):
        self.run(MAX_STEPS + 10)
        return self.outcome


def fly(L, angle, power):
    f = Flight(L, angle, power)
    f.finish()
    return f


def snap(v, step):
    return round(v / step) * step


# =============================================================================================
# Levels: hand-made lessons first, then generated ones (level number -> seed, checked solvable)
# =============================================================================================
def _arc(cx, cy, R, a0, a1, step=0.038, r=0.016):
    n = int(abs(a1 - a0) * R / step) + 1
    return [(round(cx + R * math.cos(a0 + (a1 - a0) * i / n), 4), round(cy + R * math.sin(a0 + (a1 - a0) * i / n), 4), r)
            for i in range(n + 1)]


def _wall(x, y0, y1, gap, step=0.04, r=0.016):
    out, y = [], y0
    while y <= y1 + 1e-9:
        if not gap[0] <= y <= gap[1]:
            out.append((round(x + 0.012 * math.sin(y * 37), 4), round(y, 4), r))
        y += step
    return out


INTRO = [  # each teaches one idea; all checked solvable by the self-test
    dict(name="First Light", hint="Left/Right aim, Up/Down power, Space launch. Reach the glowing dock ring.",
         launch=(0.12, 0.62), planets=[(0.8, 0.45, 0.06, None, "ocean", False)], beacons=[(1.33, 0.43)],
         preview=3.0, aim=(10.0, 60.0)),
    dict(name="Slingshot", hint="Gravity bends your path: aim past the planet and let it pull you round.",
         launch=(0.12, 0.5), planets=[(0.78, 0.5, 0.09, None, "gas", True)], beacons=[(1.37, 0.52)],
         preview=2.4, aim=(0.0, 50.0)),
    dict(name="Twin Wells", hint="Two planets pull at once. Bigger planets pull harder.",
         launch=(0.12, 0.3), planets=[(0.62, 0.62, 0.05, None, "rock", False), (1.0, 0.3, 0.07, None, "ice", True)],
         beacons=[(1.39, 0.29)], preview=2.0, aim=(0.0, 50.0)),
    dict(name="Moonrise", hint="The moon only starts to move when you launch. Power changes your timing.",
         launch=(0.12, 0.5), planets=[(0.8, 0.5, 0.05, None, "lava", False)], beacons=[(1.36, 0.55)],
         moons=[(0.8, 0.5, 0.17, 1.2, TAU / 8, 0.022, 0.0015)], preview=1.8, aim=(0.0, 50.0)),
    dict(name="The Belt", hint="Asteroids do not pull, but they are solid. Find the gap in the belt.",
         launch=(0.12, 0.75), planets=[(0.6, 0.4, 0.055, None, "teal", False)], beacons=[(1.34, 0.26)],
         rocks=_wall(1.0, 0.05, 0.95, (0.44, 0.64)), preview=1.8, aim=(30.0, 50.0)),   # gap was 0.47-0.6: the
    # narrowest lesson by far (74 docking launches on a 1 deg x 1 % grid against 190-380 around it), now 132
    dict(name="Wormhole", hint="Fly into one mouth, come out of the other one at the same speed.",
         launch=(0.12, 0.8), planets=[(0.8, 0.55, 0.09, None, "violet", True)], beacons=[(1.445, 0.18)],
         rocks=_arc(1.6, 0.0, 0.45, math.pi / 2, math.pi), holes=[((0.45, 0.3), (1.3, 0.25))], preview=1.6,
         aim=(35.0, 50.0)),
    dict(name="Second Wind", hint="Fuel for one nudge: press Space in flight for a short push forward.",
         launch=(0.1, 0.85), planets=[(0.7, 0.55, 0.075, None, "gas", False), (1.15, 0.35, 0.05, None, "rock", False)],
         beacons=[(1.445, 0.198)], fuel=1, preview=1.4, aim=(25.0, 50.0)),
    dict(name="Waypoints", hint="Pass the numbered beacons in order, then dock.",
         launch=(0.12, 0.2), planets=[(0.55, 0.55, 0.06, None, "ocean", False), (1.1, 0.45, 0.07, None, "gas", True)],
         beacons=[(0.795, 0.475), (1.374, 0.807)], preview=1.4, aim=(0.0, 50.0)),
]


def intro_level(i):
    d = INTRO[i - 1]
    return Level(i, d["name"], d["hint"], d["launch"], d["planets"], d["beacons"], d.get("moons", ()),
                 d.get("rocks", ()), d.get("holes", ()), d.get("fuel", 0), d["preview"], d["aim"])


ADJ = ["Quiet", "Amber", "Silver", "Distant", "Drifting", "Hollow", "Velvet", "Pale", "Golden", "Sleeping",
       "Glass", "Wandering", "Northern", "Cobalt", "Lantern", "Still", "Copper", "Misty", "Gentle", "Far"]
NOUN = ["Reach", "Harbour", "Crossing", "Lagoon", "Drift", "Meridian", "Orchard", "Passage", "Garden", "Shoal",
        "Halo", "Current", "Atrium", "Tide", "Hollow", "Sound", "Arbour", "Causeway", "Narrows", "Cradle"]


def default_aim(launch):
    a = math.degrees(math.atan2(-(WH / 2 - launch[1]), WW / 2 - launch[0]))
    return snap(a % 360, ANGLE_STEP), 50.0


def free_flight(L, angle, power):
    """A flight in the level without beacons (for building levels around a path)."""
    beacons, L.beacons = L.beacons, []
    f = fly(L, angle, power)
    L.beacons = beacons
    return f


def bend(path, upto):
    """How far the path strays from the straight line between its ends (world units)."""
    pts = [p for p in path[:upto + 1] if p is not None]
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    dx, dy = x1 - x0, y1 - y0
    n = math.hypot(dx, dy) or 1.0
    return max(abs((px - x0) * dy - (py - y0) * dx) / n for px, py in pts)


def neighbours_hit(L, a, p):
    n = 0
    for da, dp in ((-ANGLE_STEP, 0), (ANGLE_STEP, 0), (0, -POWER_STEP), (0, POWER_STEP),
                   (-2 * ANGLE_STEP, 0), (2 * ANGLE_STEP, 0), (0, -2 * POWER_STEP), (0, 2 * POWER_STEP)):
        pp = p + dp
        if POWER_MIN <= pp <= POWER_MAX and fly(L, (a + da) % 360, pp).outcome == "dock":
            n += 1
    return n


def direct_shot(L):
    """True when aiming straight at the first beacon docks at some power: the first thing a player tries,
    so such a level is no puzzle (it happened in about one generated level in ten)."""
    lx, ly = L.launch
    tx, ty = L.beacons[0]
    a = snap(math.degrees(math.atan2(-(ty - ly), tx - lx)) % 360, ANGLE_STEP) % 360
    p = POWER_MIN
    while p <= POWER_MAX:
        if fly(L, a, p).outcome == "dock":
            return True
        p += 2 * POWER_STEP
    return False


def generate(g, num):
    """Generated level number g (1, 2, ...). Re-rolls the seed deterministically until the level is fair."""
    for attempt in range(400):
        rnd = random.Random(g * 7919 + attempt * 104729 + 17)
        L = build(rnd, g, num)
        if L is not None and not direct_shot(L):
            return L
    raise RuntimeError("could not build generated level %d" % g)


def build(rnd, g, num):
    feats = []
    hard = min(1.0, g / 30.0)
    np_ = rnd.randint(1, 2) if g < 5 else rnd.randint(2, 3) if g < 15 else rnd.randint(2, 4)
    want_moon = g >= 3 and rnd.random() < 0.5
    want_rocks = g >= 6 and rnd.random() < 0.5
    want_hole = g >= 9 and rnd.random() < 0.35
    fuel = 1 if g >= 12 and rnd.random() < 0.4 else 0
    nbeacons = 1
    if g >= 15 and rnd.random() < 0.35:
        nbeacons = 3 if g >= 30 and rnd.random() < 0.35 else 2
    launch = (rnd.uniform(0.07, 0.16), rnd.uniform(0.2, 0.8))
    planets = []
    kinds = list(KINDS)
    for _ in range(np_):
        for _ in range(60):
            k = rnd.choice(kinds)
            r = rnd.uniform(0.04, 0.095) if k in ("gas", "violet") else rnd.uniform(0.032, 0.07)
            x, y = rnd.uniform(0.38, 1.36), rnd.uniform(0.15, 0.85)
            if math.hypot(x - launch[0], y - launch[1]) < 0.28:
                continue
            if any(math.hypot(x - q[0], y - q[1]) < r + q[2] + 0.14 for q in planets):
                continue
            ring = k in ("gas", "violet", "ice") and rnd.random() < 0.5
            planets.append((x, y, r, None, k, ring))
            break
    if not planets:
        return None
    moons = []
    if want_moon:
        host = rnd.choice(planets)
        R = host[2] + rnd.uniform(0.07, 0.12)
        ok = all(math.hypot(host[0] - q[0], host[1] - q[1]) > R + q[2] + 0.04 for q in planets if q is not host)
        ok = ok and math.hypot(host[0] - launch[0], host[1] - launch[1]) > R + 0.06
        if ok and R + 0.03 < min(host[0], WW - host[0], host[1], WH - host[1]) + 0.1:
            w = rnd.choice((-1, 1)) * TAU / rnd.uniform(6.0, 10.0)
            moons.append((host[0], host[1], R, rnd.uniform(0, TAU), w, rnd.uniform(0.016, 0.022), 0.0015))
            feats.append("moon")
    holes = []
    if want_hole:
        for _ in range(40):
            a = (rnd.uniform(0.35, 0.85), rnd.uniform(0.12, 0.88))
            b = (rnd.uniform(0.95, 1.48), rnd.uniform(0.12, 0.88))
            if abs(a[1] - b[1]) < 0.25:
                continue
            ends = [a, b]
            if all(math.hypot(e[0] - q[0], e[1] - q[1]) > q[2] + 0.08 for e in ends for q in planets) and \
                    all(abs(math.hypot(e[0] - m[0], e[1] - m[1]) - m[2]) > 0.06 for e in ends for m in moons) and \
                    math.hypot(a[0] - launch[0], a[1] - launch[1]) > 0.2:
                holes.append((a, b))
                break
    L = Level(num, "", "", launch, planets, [], moons, (), holes, fuel)
    # look for a launch whose path is worth following, then put the beacons on it
    for _ in range(40):
        a0 = snap(rnd.uniform(-70, 70) % 360, ANGLE_STEP)
        p0 = snap(rnd.uniform(28, 92), POWER_STEP)
        f = free_flight(L, a0, p0)
        path = f.path
        if holes and None not in path:
            continue
        cand = []
        for i in range(400, len(path), 8):
            q = path[i]
            if q is None or path[i - 1] is None:
                continue
            x, y = q
            if not (0.06 < x < WW - 0.06 and 0.06 < y < WH - 0.06):
                continue
            if math.hypot(x - launch[0], y - launch[1]) < 0.55:
                continue
            if any(math.hypot(x - pl[0], y - pl[1]) < pl[2] + 0.07 for pl in L.planets):
                continue
            if any(abs(math.hypot(x - m[0], y - m[1]) - m[2]) < 0.05 for m in moons):
                continue
            if any(math.hypot(x - e[0], y - e[1]) < 0.09 for h in holes for e in h):
                continue
            cand.append(i)
        if len(cand) < 6:
            continue
        if holes:
            jump = path.index(None)
            cand = [i for i in cand if i > jump + 60]
            if not cand:
                continue
        lo = cand[len(cand) // 3] if not holes else cand[0]
        late = [i for i in cand if i >= lo]
        ti = rnd.choice(late)
        if bend(path, ti) < 0.06 + 0.06 * hard:
            continue
        idx = [ti]
        for _ in range(nbeacons - 1):
            earlier = [i for i in cand if i < idx[0] - 150 and
                       all(math.hypot(path[i][0] - path[j][0], path[i][1] - path[j][1]) > 0.28 for j in idx)]
            if not earlier:
                break
            idx.insert(0, rnd.choice(earlier[len(earlier) // 2:]))
        if len(idx) < nbeacons:
            continue
        L.beacons = [path[i] for i in idx]
        L.beacons = [(round(x, 4), round(y, 4)) for x, y in L.beacons]
        if want_rocks:
            L.rocks = belt(rnd, L, path[:ti + 1])
            if L.rocks:
                feats.append("rocks")
        # mirror for variety (the launch may sit on any side)
        sol = (a0, p0)
        if rnd.random() < 0.5:
            L, sol = mirror(L, sol, True)
        if rnd.random() < 0.5:
            L, sol = mirror(L, sol, False)
        L.aim = default_aim(L.launch)
        if fly(L, *sol).outcome != "dock":
            continue
        if fly(L, *L.aim).outcome == "dock":
            return None
        if neighbours_hit(L, *sol) < 5:
            continue
        frac = max(0.22, 0.52 - 0.012 * g)
        L.preview = round(max(0.6, frac * ti * DT), 2)
        L.solution = sol
        L.name = "%s %s" % (rnd.choice(ADJ), rnd.choice(NOUN))
        tags = []
        if holes:
            tags.append("wormhole")
        if "moon" in feats:
            tags.append("moon")
        if "rocks" in feats:
            tags.append("asteroids")
        if fuel:
            tags.append("1 nudge")
        if len(L.beacons) > 1:
            tags.append("%d beacons in order" % len(L.beacons))
        L.hint = ", ".join(tags)
        return L
    return None


def belt(rnd, L, path):
    """A loose asteroid belt across the straight line to the dock, with a gap where the path goes."""
    (x0, y0), (x1, y1) = L.launch, L.beacons[-1]
    t = rnd.uniform(0.4, 0.65)
    cx, cy = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
    a = math.atan2(y1 - y0, x1 - x0) + math.pi / 2 + rnd.uniform(-0.5, 0.5)
    half = rnd.uniform(0.25, 0.42)
    pts = [p for p in path if p is not None][::4]
    rocks = []
    s = -half
    while s <= half:
        x = cx + math.cos(a) * s + rnd.uniform(-0.012, 0.012)
        y = cy + math.sin(a) * s + rnd.uniform(-0.012, 0.012)
        r = rnd.uniform(0.012, 0.019)
        s += rnd.uniform(0.04, 0.055)
        if not (0.02 < x < WW - 0.02 and 0.02 < y < WH - 0.02):
            continue
        if any(math.hypot(x - px, y - py) < r + 0.045 for px, py in pts):
            continue
        if any(math.hypot(x - p[0], y - p[1]) < p[2] + r + 0.03 for p in L.planets):
            continue
        if any(abs(math.hypot(x - m[0], y - m[1]) - m[2]) < m[5] + r + 0.02 for m in L.moons):
            continue
        if any(math.hypot(x - b[0], y - b[1]) < 0.07 for b in L.beacons):
            continue
        if any(math.hypot(x - e[0], y - e[1]) < 0.07 for h in L.holes for e in h):
            continue
        if math.hypot(x - x0, y - y0) < 0.12:
            continue
        rocks.append((round(x, 4), round(y, 4), round(r, 4)))
    return rocks if len(rocks) >= 4 else []


def mirror(L, sol, horizontal):
    if horizontal:
        fx = lambda x: WW - x
        fy = lambda y: y
        fa = lambda a: snap((180 - a) % 360, ANGLE_STEP)
    else:
        fx = lambda x: x
        fy = lambda y: WH - y
        fa = lambda a: snap((-a) % 360, ANGLE_STEP)
    M = Level(L.num, L.name, L.hint, (fx(L.launch[0]), fy(L.launch[1])),
              [(fx(p[0]), fy(p[1]), p[2], p[3], p[4], p[5]) for p in L.planets],
              [(fx(x), fy(y)) for x, y in L.beacons],
              [(fx(m[0]), fy(m[1]), m[2], (math.pi - m[3]) if horizontal else -m[3], -m[4], m[5], m[6]) for m in L.moons],
              [(fx(x), fy(y), r) for x, y, r in L.rocks],
              [((fx(a[0]), fy(a[1])), (fx(b[0]), fy(b[1]))) for a, b in L.holes], L.fuel, L.preview, L.aim)
    return M, (fa(sol[0]), sol[1])


_CACHE = {}


def get_level(num):
    if num not in _CACHE:
        _CACHE[num] = intro_level(num) if num <= len(INTRO) else generate(num - len(INTRO), num)
    return _CACHE[num]




def search(L, astep=1.0, pstep=2.0, limit=None):
    """Look for a launch that docks, on a grid the arrow keys can reach. Starts near the direct line to
    the first beacon and sweeps outwards over the whole circle. Returns (angle, power, tries) or None."""
    lx, ly = L.launch
    tx, ty = L.beacons[0]
    direct = math.degrees(math.atan2(-(ty - ly), tx - lx))
    n = int(round(360 / astep))
    angles = sorted((i * astep for i in range(n)), key=lambda a: abs((a - direct + 180) % 360 - 180))
    powers = [POWER_MIN + i * pstep for i in range(int((POWER_MAX - POWER_MIN) / pstep) + 1)]
    tries = 0
    for a in angles:
        for p in powers:
            tries += 1
            if fly(L, a, p).outcome == "dock":
                return a, p, tries
            if limit and tries >= limit:
                return None
    return None


# =============================================================================================
# Auto mode: a pilot that studies the map (it searches angle and power with the game's own physics, like the
# self-test), then sets the aim with the arrow keys and launches like a player: the first launch carries an aiming
# error that shrinks with every miss, so narrow docking windows take a few tries and wide ones are hit at once.
# =============================================================================================
def search_steps(L, astep=1.0, pstep=2.0):
    """search() in small pieces: yields None while it works, then (angle, power, tries) or False."""
    lx, ly = L.launch
    tx, ty = L.beacons[0]
    direct = math.degrees(math.atan2(-(ty - ly), tx - lx))
    n = int(round(360 / astep))
    angles = sorted((i * astep for i in range(n)), key=lambda a: abs((a - direct + 180) % 360 - 180))
    powers = [POWER_MIN + i * pstep for i in range(int((POWER_MAX - POWER_MIN) / pstep) + 1)]
    tries = 0
    for a in angles:
        for p in powers:
            tries += 1
            if fly(L, a, p).outcome == "dock":
                yield (a, p, tries)
                return
            yield None
    yield False


def miss(L, a, p):
    """How far a launch stays from the next beacon it has to pass (0 = it docks); beacons left count extra."""
    f = fly(L, a, p)
    if f.outcome == "dock":
        return 0.0
    bx, by = L.beacons[f.nb]
    d = min((q[0] - bx) ** 2 + (q[1] - by) ** 2 for q in f.path if q is not None)
    return math.sqrt(d) + 0.4 * (len(L.beacons) - 1 - f.nb)


def guided_steps(L):
    """A quicker search than search(): a coarse sweep (5 degrees x 15 % power) that remembers how close each
    launch came, then a pattern search (halving steps down to the arrow-key grid) from the eight best
    distinct ones. Yields None per flight, then (angle, power, flights); falls back to the full fine search."""
    lx, ly = L.launch
    tx, ty = L.beacons[0]
    direct = math.degrees(math.atan2(-(ty - ly), tx - lx))
    n = 0
    cand = []
    for a in sorted(range(0, 360, 5), key=lambda a: abs((a - direct + 180) % 360 - 180)):
        for p in (20, 35, 50, 65, 80, 95):
            n += 1
            m = miss(L, float(a), float(p))
            if m == 0:
                yield (float(a), float(p), n)
                return
            cand.append((m, float(a), float(p)))
            yield None
    cand.sort()
    starts = []
    for c in cand:
        if all(abs((c[1] - b + 180) % 360 - 180) > 6 or abs(c[2] - q) > 10 for _, b, q in starts):
            starts.append(c)
        if len(starts) >= 8:
            break
    for m, a, p in starts:
        sa, sp = 2.5, 7.5
        while sa >= ANGLE_STEP - 1e-9:
            best = None
            for da, dp in ((sa, 0), (-sa, 0), (0, sp), (0, -sp), (sa, sp), (-sa, -sp), (sa, -sp), (-sa, sp)):
                aa = snap((a + da) % 360, ANGLE_STEP) % 360
                pp = clamp(snap(p + dp, POWER_STEP), POWER_MIN, POWER_MAX)
                n += 1
                mm = miss(L, aa, pp)
                if mm == 0:
                    yield (aa, pp, n)
                    return
                if mm < m and (best is None or mm < best[0]):
                    best = (mm, aa, pp)
                yield None
            if best:
                m, a, p = best
            else:
                sa, sp = sa / 2, max(POWER_STEP, sp / 2)
    for r in search_steps(L, ANGLE_STEP, POWER_STEP):
        n += 1
        yield None if r is None else r if r is False else (r[0], r[1], n)


def window_centre(L, a, p, reach=12):
    """The middle of the docking window around a known hit, on the arrow-key grid: first along the angle,
    then along the power. Returns (angle, power, width in angle steps, width in power steps)."""
    def docks(aa, pp):
        return POWER_MIN <= pp <= POWER_MAX and fly(L, aa % 360, pp).outcome == "dock"
    lo = hi = 0
    while lo > -reach and docks(a + (lo - 1) * ANGLE_STEP, p):
        lo -= 1
    while hi < reach and docks(a + (hi + 1) * ANGLE_STEP, p):
        hi += 1
    a = snap((a + (lo + hi) / 2 * ANGLE_STEP) % 360, ANGLE_STEP) % 360
    plo = phi = 0
    while plo > -reach and docks(a, p + (plo - 1) * POWER_STEP):
        plo -= 1
    while phi < reach and docks(a, p + (phi + 1) * POWER_STEP):
        phi += 1
    p = clamp(snap(p + (plo + phi) / 2 * POWER_STEP, POWER_STEP), POWER_MIN, POWER_MAX)
    return a, p, hi - lo + 1, phi - plo + 1


class Pilot:
    """Plays ORBITAL through Game.key. think(seconds) does the searching (call it once per frame with a time
    budget); update(dt) presses the keys in game time."""
    AIM_ERR = (2.2, 5.0)         # first-launch aiming error (degrees, percent power), shrinking per miss
    SHRINK = 0.4

    def __init__(self, rnd=None):
        self.rnd = rnd or random.Random()
        self.num = None
        self.wait = 0.0
        self.searching = None
        self.target = None       # the centre of the docking window
        self.aim = None          # where this launch goes
        self.err = (0.0, 0.0)
        self.study = 0.0
        self.attempt_seen = -1
        self.flights = 0         # simulated flights for the current level (the "how hard is it to find" number)

    def new_level(self, g):
        self.num = g.num
        self.target = self.aim = None
        self.searching = guided_steps(g.L)
        self.study = 1.2 + self.rnd.random() * 0.8            # look at the map for a moment first
        self.attempt_seen = -1
        self.flights = 0
        ang = self.rnd.uniform(0, TAU)
        k = self.rnd.uniform(0.5, 1.0)
        self.err = (math.cos(ang) * self.AIM_ERR[0] * k, math.sin(ang) * self.AIM_ERR[1] * k)

    def think(self, budget):
        """Search for a launch that docks, for at most `budget` seconds of real time."""
        if self.searching is None:
            return
        end = time.time() + budget
        while time.time() < end:
            r = next(self.searching)
            self.flights += 1
            if r is None:
                continue
            if r is False:                    # cannot happen (the self-test solves every level); aim somewhere
                self.searching = None
                self.target = self.L_aim
                return
            a, p, _ = r
            a, p, _, _ = window_centre(self.L, a, p)
            if fly(self.L, a, p).outcome != "dock":
                a, p = r[0], r[1]
            self.target = (a, p)
            self.searching = None
            return

    def plan_launch(self, g):
        """The aim for the next launch: the window centre plus an error that shrinks with each miss."""
        n = g.attempts                         # launches already made on this level
        if n >= 4:
            k = 0.0
        else:
            k = self.SHRINK ** n
        a = snap((self.target[0] + self.err[0] * k) % 360, ANGLE_STEP) % 360
        p = clamp(snap(self.target[1] + self.err[1] * k, POWER_STEP), POWER_MIN, POWER_MAX)
        self.aim = (a, p)

    def update(self, g, dt):
        if g.paused:
            return
        if g.num != self.num:
            self.L = g.L
            self.L_aim = g.L.aim
            self.new_level(g)
        self.wait -= dt
        self.study -= dt
        if self.wait > 0:
            return
        if g.state == "done":
            self.wait = 2.8                    # enjoy the stars, then on to the next level
            if getattr(self, "done_seen", None) == (g.num, g.attempts):
                g.key("enter", g.t)
                return
            self.done_seen = (g.num, g.attempts)
            return
        if g.state != "aim" or self.target is None or self.study > 0:
            return
        if self.attempt_seen != g.attempts:    # a fresh aim for this launch
            self.attempt_seen = g.attempts
            self.plan_launch(g)
            self.wait = 0.35 + self.rnd.random() * 0.4
            return
        a, p = self.aim
        da = (a - g.angle + 180) % 360 - 180
        dp = p - g.power
        if abs(da) > 1e-9:
            k, far = ("left" if da > 0 else "right"), abs(da) > 6
        elif abs(dp) > 1e-9:
            k, far = ("up" if dp > 0 else "down"), abs(dp) > 6
        else:
            g.key("enter", g.t)                # launch
            self.wait = 0.2
            return
        # far away: hold the key (fast repeat); close by: single taps
        g.key(k, g.t)
        self.wait = 0.03 if far else 0.13


# =============================================================================================
# Drawing
# =============================================================================================
SPACE_TOP, SPACE_BOT = (5, 6, 15), (9, 7, 20)
HUD_BG = (12, 12, 22)
TOP_BG = (9, 9, 18)
DOCK_COL = (255, 214, 110)
BEACON_COL = (120, 230, 255)
HOLE_COLS = [(190, 120, 255), (110, 230, 210)]
AIM_COL = (236, 246, 255)
PREVIEW_COL = (170, 255, 210)
TRAIL_COL = (150, 220, 255)
HISTORY_COLS = [(120, 128, 170), (100, 104, 140), (82, 84, 116)]
LIGHT = (-0.55, -0.5, 0.67)


class View:
    """Maps the world onto the window: the map keeps its shape and sits between the top line and the HUD."""

    def __init__(self, cols, rows):
        self.cols, self.rows = cols, rows
        top = 2
        h = (rows - 2) * 2
        self.s = min(cols / WW, h / WH)
        self.ox = (cols - WW * self.s) / 2
        self.oy = top + (h - WH * self.s) / 2

    def p(self, x, y):
        return self.ox + x * self.s, self.oy + y * self.s


def _hash(i, j, seed):
    h = (i * 374761393 + j * 668265263 + seed * 2147483647) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65535.0


def vnoise(x, y, seed):
    i, j = math.floor(x), math.floor(y)
    fx, fy = x - i, y - j
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a, b = _hash(i, j, seed), _hash(i + 1, j, seed)
    c, d = _hash(i, j + 1, seed), _hash(i + 1, j + 1, seed)
    return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy


def fbm(x, y, seed):
    return vnoise(x, y, seed) * 0.6 + vnoise(x * 2.1, y * 2.1, seed + 7) * 0.3 + vnoise(x * 4.3, y * 4.3, seed + 3) * 0.1


def blend(px, x, y, c, a):
    if 0 <= y < len(px) and 0 <= x < len(px[0]):
        px[y][x] = mix(px[y][x], c, a)


def planet_colour(kind, u, v, nz, seed):
    base, second, _ = KINDS[kind]
    glow = None
    if kind in ("gas", "violet"):
        s = math.sin(v * 9.0 + 1.4 * math.sin(u * 2.6 + seed) + seed)
        c = mix(base, second, 0.5 + 0.5 * s)
        c = mix(c, (240, 230, 210), max(0.0, s - 0.8) * 1.5)
    elif kind == "ocean":
        n = fbm(u * 2.2 + seed, v * 2.2, seed)
        c = second if n > 0.55 else base
        if abs(v) > 0.82:
            c = (230, 240, 250)
    elif kind == "teal":
        n = fbm(u * 2.5 + seed, v * 3.5, seed)
        c = mix(base, second, clamp((n - 0.35) * 2.5, 0, 1))
    elif kind == "ice":
        n = fbm(u * 3 + seed, v * 3, seed)
        c = mix(base, second, clamp((n - 0.3) * 2, 0, 1))
    elif kind == "lava":
        n = fbm(u * 2.6 + seed, v * 2.6, seed)
        c = mix(base, (60, 30, 28), n)
        g = max(0.0, 1 - abs(n - 0.5) * 9)
        if g > 0:
            glow = mix((120, 40, 10), second, g)
    else:  # rock
        n = fbm(u * 2.8 + seed, v * 2.8, seed)
        c = mix(base, second, n)
        for k in range(4):
            cx, cy = _hash(k, 1, seed) * 1.4 - 0.7, _hash(k, 2, seed) * 1.4 - 0.7
            cr = 0.12 + _hash(k, 3, seed) * 0.16
            d = math.hypot(u - cx, v - cy)
            if d < cr:
                c = shade(c, 0.78 if d < cr * 0.75 else 1.12)
    return c, glow


def draw_ring(px, cx, cy, R, front, col):
    a = R * 2.0
    tilt = -0.32
    ct, st = math.cos(tilt), math.sin(tilt)
    H, W = len(px), len(px[0])
    ext = int(a) + 2
    for y in range(int(cy) - ext, int(cy) + ext + 1):
        if not 0 <= y < H:
            continue
        for x in range(int(cx) - ext, int(cx) + ext + 1):
            if not 0 <= x < W:
                continue
            dx, dy = x + 0.5 - cx, y + 0.5 - cy
            rx, ry = dx * ct + dy * st, -dx * st + dy * ct
            if (ry > 0) != front:
                continue
            rr = math.hypot(rx, ry / 0.34) / R
            if 1.35 < rr < 2.0:
                if front is False and dx * dx + dy * dy < R * R:
                    continue
                band = 0.55 + 0.45 * math.sin(rr * 19)
                k = 0.35 if rr < 1.5 else 0.6
                px[y][x] = mix(px[y][x], shade(col, 0.6 + 0.5 * band), k)


def draw_planet(px, cx, cy, R, kind, seed, ring=False, light=1.0):
    base = KINDS[kind][0]
    if ring:
        draw_ring(px, cx, cy, R, False, mix(base, (230, 220, 200), 0.5))
    H, W = len(px), len(px[0])
    halo = kind in ("ocean", "teal", "ice")
    ext = R * (1.35 if halo else 1.0) + 1.5
    lx, ly, lz = LIGHT
    for y in range(int(cy - ext), int(cy + ext) + 1):
        if not 0 <= y < H:
            continue
        row = px[y]
        for x in range(int(cx - ext), int(cx + ext) + 1):
            if not 0 <= x < W:
                continue
            u, v = (x + 0.5 - cx) / R, (y + 0.5 - cy) / R
            d2 = u * u + v * v
            d = math.sqrt(d2)
            cover = clamp((1 - d) * R + 0.5, 0.0, 1.0)
            if cover <= 0:
                if halo and d < 1.35:
                    row[x] = mix(row[x], mix(base, (200, 230, 255), 0.5), 0.22 * (1 - (d - 1) / 0.35) ** 2)
                continue
            nz = math.sqrt(max(0.0, 1 - min(1.0, d2)))
            lam = max(0.0, u * lx + v * ly + nz * lz)
            c, glow = planet_colour(kind, u, v, nz, seed)
            c = shade(c, (0.1 + 1.05 * lam) * light)
            if glow:
                c = mix(c, glow, 0.85)
            if halo:
                c = mix(c, (190, 225, 255), 0.35 * (1 - nz) ** 3)
            row[x] = mix(row[x], c, cover)
    if ring:
        draw_ring(px, cx, cy, R, True, mix(base, (230, 220, 200), 0.5))


def dotted_circle(px, cx, cy, R, col, a, gap=2.0):
    n = max(8, int(TAU * R / gap))
    for i in range(n):
        t = TAU * i / n
        blend(px, int(cx + math.cos(t) * R), int(cy + math.sin(t) * R), col, a)


def static_layer(L, view, seed):
    """Everything that does not move: space, planets, gravity hints, asteroids, the moons' orbits."""
    cols, rows = view.cols, view.rows
    W, H = cols, rows * 2
    rnd = random.Random(seed)
    px = []
    blobs = [(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(0.25, 0.5) * W,
              rnd.choice([(40, 24, 70), (20, 34, 70), (60, 22, 50), (16, 46, 60)])) for _ in range(3)]
    for y in range(H):
        base = mix(SPACE_TOP, SPACE_BOT, y / max(1, H - 1))
        row = []
        for x in range(W):
            c = base
            for bx, by, br, bc in blobs:
                k = ((x - bx) ** 2 + ((y - by) * 1.3) ** 2) / (br * br)
                if k < 1:
                    c = mix(c, bc, 0.28 * (1 - k) ** 2 * (0.6 + 0.4 * vnoise(x * 0.08, y * 0.08, seed)))
            row.append(c)
        px.append(row)
    stars = []
    for _ in range(W * H // 95):     # mostly faint: the starfield must not compete with the dotted preview
        x, y = rnd.randrange(W), rnd.randrange(H)
        b = rnd.random() ** 3
        tint = rnd.choice([(255, 255, 255), (200, 220, 255), (255, 230, 200), (255, 210, 210)])
        c = mix(px[y][x], tint, 0.05 + 0.6 * b)
        px[y][x] = c
        if b > 0.5:
            stars.append((x, y, tint))
    s = view.s
    ox, oy = view.ox, view.oy
    # the edge of the map (where signal is lost), when the window is wider or taller than the map
    x0, y0, x1, y1 = int(ox), int(oy), int(ox + WW * s), int(oy + WH * s)
    edge = (40, 44, 70)
    if x0 > 0 and L.station:
        for y in range(max(0, y0), min(H, y1), 2):
            blend(px, x0 - 1, y, edge, 0.6)
            blend(px, x1, y, edge, 0.6)
    if y0 > 2 and L.station:
        for x in range(max(0, x0), min(W, x1), 2):
            blend(px, x, y0 - 1, edge, 0.6)
            blend(px, x, y1, edge, 0.6)
    # gravity hints: where the pull is gentle and where it is strong
    for (x, y, r, gm, kind, ring) in L.planets:
        cx, cy = ox + x * s, oy + y * s
        tint = mix(KINDS[kind][0], (180, 200, 255), 0.4)
        for acc, a in ((0.45, 0.12), (1.6, 0.2)):
            R = math.sqrt(gm / acc) * s
            if R > r * s + 2:
                dotted_circle(px, cx, cy, R, tint, a, 2.2)
    for m in L.moons:
        dotted_circle(px, ox + m[0] * s, oy + m[1] * s, m[2] * s, (150, 150, 170), 0.18, 1.7)
    for i, (x, y, r, gm, kind, ring) in enumerate(L.planets):
        draw_planet(px, ox + x * s, oy + y * s, max(1.2, r * s), kind, seed * 13 + i * 5 + 1, ring)
    for i, (x, y, r) in enumerate(L.rocks):
        cx, cy, R = ox + x * s, oy + y * s, max(0.9, r * s)
        for yy in range(int(cy - R - 1), int(cy + R) + 2):
            for xx in range(int(cx - R - 1), int(cx + R) + 2):
                u, v = (xx + 0.5 - cx) / R, (yy + 0.5 - cy) / R
                lump = 1 + 0.25 * math.sin(math.atan2(v, u) * 3 + i)
                d = math.hypot(u, v) / lump
                cover = clamp((1 - d) * R + 0.5, 0, 1)
                if cover > 0:
                    lit = clamp(0.55 - 0.45 * u - 0.4 * v, 0.2, 1.1)
                    blend(px, xx, yy, shade((182, 166, 150), lit), cover)
    if not L.station:
        return px, stars
    # the launch station
    lx, ly = ox + L.launch[0] * s, oy + L.launch[1] * s
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            blend(px, int(lx) + dx, int(ly) + dy, (90, 100, 124) if dx or dy else (40, 44, 60), 1.0)
    return px, stars


class Painter:
    """Caches the static layer per level and window size."""

    def __init__(self):
        self.key = None

    def base(self, L, view):
        key = (id(L), view.cols, view.rows)
        if key != self.key:
            self.key = key
            self.px, self.stars = static_layer(L, view, 1000 + (L.num or 0))
        return [row[:] for row in self.px]


def draw_path(px, view, pts, col, alpha, step=1, fade=False):
    s, ox, oy = view.s, view.ox, view.oy
    H, W = len(px), len(px[0])
    n = len(pts)
    last = None
    for i in range(0, n, step):
        p = pts[i]
        if p is None:
            last = None
            continue
        x, y = int(ox + p[0] * s), int(oy + p[1] * s)
        if (x, y) == last:
            continue
        last = (x, y)
        if 0 <= x < W and 0 <= y < H:
            a = alpha * (0.25 + 0.75 * i / n) if fade else alpha
            px[y][x] = mix(px[y][x], col, a)


def draw_dots(px, view, pts, col, alpha, spacing=2.6):
    """The dotted preview: one dot every few pixels, fading towards its end."""
    s, ox, oy = view.s, view.ox, view.oy
    H, W = len(px), len(px[0])
    acc = 0.0
    prev = None
    n = len(pts)
    for i, p in enumerate(pts):
        if p is None:
            prev = None
            continue
        x, y = ox + p[0] * s, oy + p[1] * s
        if prev is not None:
            acc += math.hypot(x - prev[0], y - prev[1])
        prev = (x, y)
        if acc >= spacing or i == 0:
            acc = 0.0
            ix, iy = int(x), int(y)
            if 0 <= ix < W and 0 <= iy < H:
                k = 1 - i / max(1, n)
                px[iy][ix] = mix(px[iy][ix], col, alpha * (0.45 + 0.55 * k))


def draw_disc(px, cx, cy, R, col, a=1.0):
    for y in range(int(cy - R - 1), int(cy + R) + 2):
        for x in range(int(cx - R - 1), int(cx + R) + 2):
            d = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
            cover = clamp(R - d + 0.5, 0, 1)
            if cover > 0:
                blend(px, x, y, col, a * cover)


def draw_world(cv, px, view, L, t, moon_t, nb=0, stars=()):
    """The moving parts of a level: twinkling stars, wormholes, beacons, moons."""
    s, ox, oy = view.s, view.ox, view.oy
    for i, (x, y, tint) in enumerate(stars):
        k = 0.5 + 0.5 * math.sin(t * (0.7 + (i % 7) * 0.23) + i * 1.7)
        if k > 0.8:
            blend(px, x, y, tint, (k - 0.8) * 3)
    for hi, (a, b) in enumerate(L.holes):
        col = HOLE_COLS[hi % 2]
        for e, (hx, hy) in enumerate((a, b)):
            cx, cy = ox + hx * s, oy + hy * s
            R = max(1.6, HOLE_R * s)
            draw_disc(px, cx, cy, R * 0.75, (6, 4, 14), 0.9)
            n = max(10, int(TAU * R * 1.2))
            for k in range(n):
                ang = TAU * k / n + t * (1.3 if e == 0 else -1.3)
                br = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(ang * 3 - t * 2))
                for rr in (R, R * 0.6):
                    blend(px, int(cx + math.cos(ang) * rr), int(cy + math.sin(ang) * rr), col, br * (0.9 if rr == R else 0.5))
    nbeacons = len(L.beacons)
    for i, (bx, by) in enumerate(L.beacons):
        cx, cy = ox + bx * s, oy + by * s
        last = i == nbeacons - 1
        col = DOCK_COL if last else BEACON_COL
        if i < nb:
            col = (90, 150, 110)
        R = max(2.0, (DOCK_R if last else BEACON_R) * s)
        pulse = 0.5 + 0.5 * math.sin(t * 2.4 + i)
        if i >= nb:
            # a soft expanding glow ring
            g = (t * 0.6 + i * 0.3) % 1.0
            dotted_circle(px, cx, cy, R * (1.0 + g * 1.4), col, 0.35 * (1 - g), 1.4)
            draw_disc(px, cx, cy, R * 1.6, col, 0.06 + 0.05 * pulse)
        n = max(12, int(TAU * R * 2))
        for k in range(n):
            ang = TAU * k / n
            sweep = 0.5 + 0.5 * math.cos(ang - t * 1.6)
            br = (0.55 + 0.45 * sweep) * (0.8 + 0.2 * pulse) if last else (0.85 if k % 2 == 0 else 0.35)
            blend(px, int(cx + math.cos(ang) * R), int(cy + math.sin(ang) * R), col, br)
        draw_disc(px, cx, cy, max(0.6, R * 0.28), mix(col, (255, 255, 255), 0.5), 0.9)
        if nbeacons > 1 and not last:
            cv.put(int(cx + R + 1), int(cy) // 2, str(i + 1), col if i >= nb else (90, 150, 110))
    for j, m in enumerate(L.moons):
        mx, my = L.moon_pos(m, moon_t)
        draw_planet(px, ox + mx * s, oy + my * s, max(1.0, m[5] * s), "rock" if j % 2 == 0 else "ice", 77 + j)


STAR_PIX = ["....#....", "...###...", "#########", ".#######.", "..#####..", "..##.##..", ".##...##.", ".#.....#."]


def draw_star(px, x, y, col):
    for j, row in enumerate(STAR_PIX):
        for i, ch in enumerate(row):
            if ch == "#":
                blend(px, x + i, y + j, col, 1.0)


# =============================================================================================
# The game
# =============================================================================================
def stars_for(attempts):
    # 2 stars up to 4 launches (was 3): later levels have docking windows only one or two arrow taps wide,
    # and even a pilot that knows the answer and only mis-aims a little needed 4 launches on them now and then
    return 3 if attempts <= 1 else 2 if attempts <= 4 else 1


def load_progress():
    raw = load_scores().get(LEVELS_KEY, {})
    out = {}
    for k, v in raw.items():
        try:
            out[int(k)] = int(v)
        except (TypeError, ValueError):
            pass
    return out


OUTCOME_TEXT = {"planet": "Crashed into a planet.", "moon": "Hit a moon.", "rock": "Hit an asteroid.",
                "lost": "Left the map - signal lost.", "time": "Drifted too long - signal lost.",
                "abort": "Flight aborted."}
SPEED = 1.0


class Game:
    def __init__(self, num=1, progress=None, auto=False):
        self.auto = auto                    # auto mode: stars are shown but never saved
        self.progress = load_progress() if progress is None else progress
        self.paused = self.help = False
        self.t = 0.0
        self.rep = (None, -9.0, 0)
        self.load(num)

    # --- levels ---------------------------------------------------------------------------
    def unlocked(self):
        return max(self.progress, default=0) + 1

    def load(self, num):
        self.num = num
        self.L = get_level(num)
        self.angle, self.power = self.L.aim
        self.attempts = 0
        self.history = []
        self.state = "aim"
        self.flight = None
        self.pv_key = None
        self.pv = []
        self.parts = []
        self.fast = False
        self.acc = 0.0
        self.timer = 0.0
        self.msg, self.msg_t = "", 0.0
        self.banner = None
        self.banner_t = 0.0

    def say(self, s, ttl=3.0):
        self.msg, self.msg_t = s, ttl

    def preview(self):
        key = (self.angle, self.power)
        if key != self.pv_key:
            self.pv_key = key
            f = Flight(self.L, self.angle, self.power)
            f.run(int(self.L.preview / DT))
            self.pv = f.path
        return self.pv

    # --- input ----------------------------------------------------------------------------
    def repeat(self, k, now):
        key, last, n = self.rep
        n = n + 1 if key == k and now - last < 0.11 else 0
        self.rep = (k, now, n)
        return 1 if n < 6 else 4 if n < 18 else 10

    def key(self, k, now=None):
        now = time.time() if now is None else now
        if k in ("n", "]"):
            if self.num + 1 <= self.unlocked():
                self.load(self.num + 1)
                SND.play("level")
            else:
                self.say("Dock here first to unlock level %d." % (self.num + 1))
            return
        if k in ("b", "["):
            if self.num > 1:
                self.load(self.num - 1)
                SND.play("level")
            return
        if self.state == "done":
            if k in ("enter", " "):
                self.load(self.num + 1)
                SND.play("level")
            elif k == "r":
                self.load(self.num)
                SND.play("level")
            return
        if self.state == "aim":
            if k in ("left", "right", "a", "d"):
                m = self.repeat("lr" + k, now)
                d = ANGLE_STEP * m * (1 if k in ("left", "a") else -1)
                self.angle = snap((self.angle + d) % 360, ANGLE_STEP) % 360
                SND.play("tick", gap=0.07)
            elif k in ("up", "down", "w", "s"):
                m = self.repeat("ud" + k, now)
                d = POWER_STEP * m * (1 if k in ("up", "w") else -1)
                self.power = clamp(snap(self.power + d, POWER_STEP), POWER_MIN, POWER_MAX)
                SND.play("tick_up" if d > 0 else "tick_down", gap=0.07)
            elif k in ("enter", " "):
                self.launch()
            return
        if self.state == "fly":
            if k == " ":
                if self.L.fuel:
                    if self.flight.nudge():
                        SND.play("nudge")
                        self.say("Nudge!", 1.2)
                    elif self.flight.fuel <= 0:
                        SND.play("empty", gap=0.2)
                        self.say("No fuel left for this launch.", 1.5)
                else:
                    self.fast = not self.fast
            elif k == "enter":
                self.fast = not self.fast
            elif k == "r":
                self.end_flight("abort")
            return
        if self.state == "after" and k in ("enter", " ", "r"):
            self.state = "aim"

    def launch(self):
        self.attempts += 1
        self.flight = Flight(self.L, self.angle, self.power)
        self.state = "fly"
        SND.play("launch")
        self.acc = 0.0
        self.fast = False
        self.msg_t = 0

    # --- time -----------------------------------------------------------------------------
    def update(self, dt):
        self.t += dt
        self.msg_t -= dt
        for p in self.parts:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[2] *= 0.96
            p[3] *= 0.96
            p[4] -= dt
        self.parts = [p for p in self.parts if p[4] > 0]
        if self.paused:
            return
        if self.state == "fly":
            f = self.flight
            self.acc += dt * SPEED * (3 if self.fast else 1)
            n = int(self.acc / DT)
            self.acc -= n * DT
            n0, nb0 = len(f.path), f.nb
            f.run(n)
            if None in f.path[n0:]:
                SND.play("wormhole", gap=0.3)
            if f.nb > nb0 and f.outcome != "dock":         # a waypoint beacon: chimes rise in order
                SND.play("beacon%d" % min(3, f.nb))
            if f.outcome:
                self.end_flight(f.outcome)
        elif self.state == "after":
            self.timer -= dt
            if self.timer <= 0:
                self.state = "aim"

    def end_flight(self, outcome):
        f = self.flight
        self.history.insert(0, (f.path[::2] + [f.path[-1]], outcome))
        del self.history[3:]
        if outcome == "dock":
            stars = stars_for(self.attempts)
            old = self.progress.get(self.num, 0)
            self.progress[self.num] = max(old, stars)
            total = sum(self.progress.values())
            if not self.auto:
                submit(LEVELS_KEY, str(self.num), stars)
                submit(GAME, "stars", total)
                submit(GAME, "levels", max(self.progress))
            self.banner = (stars, self.attempts, stars > old and old > 0, total)
            self.banner_t = self.t
            self.state = "done"
            SND.play("dock%d" % clamp(stars, 1, 3))
            rnd = random.Random(self.num)
            for _ in range(40):
                a, v = rnd.uniform(0, TAU), rnd.uniform(0.05, 0.35)
                self.parts.append([f.x, f.y, math.cos(a) * v, math.sin(a) * v, rnd.uniform(0.6, 1.6),
                                   rnd.choice([DOCK_COL, (255, 250, 220), BEACON_COL])])
            return
        if outcome in ("planet", "moon", "rock"):
            rnd = random.Random(self.attempts * 31 + self.num)
            for _ in range(26):
                a, v = rnd.uniform(0, TAU), rnd.uniform(0.04, 0.22)
                self.parts.append([f.x, f.y, math.cos(a) * v, math.sin(a) * v, rnd.uniform(0.3, 1.0),
                                   rnd.choice([(255, 210, 120), (255, 140, 60), (255, 250, 230), (200, 80, 50)])])
        SND.play("crash" if outcome in ("planet", "moon", "rock") else "abort" if outcome == "abort" else "lost")
        self.say(OUTCOME_TEXT.get(outcome, "") + "  Adjust and launch again.", 3.0)
        self.state = "after"
        self.timer = 1.1 if outcome != "abort" else 0.2


# =============================================================================================
# Rendering the game
# =============================================================================================
def render(g, painter, cols, rows):
    view = View(cols, rows)
    L = g.L
    cv = Canvas(cols, rows)
    cv.px = painter.base(L, view)
    px = cv.px
    s, ox, oy = view.s, view.ox, view.oy
    f = g.flight
    flying = g.state == "fly"
    moon_t = f.t if (f is not None and g.state in ("fly", "after", "done")) else 0.0
    nb = f.nb if (f is not None and g.state in ("fly", "after", "done")) else 0
    draw_world(cv, px, view, L, g.t, moon_t, nb, painter.stars)
    # earlier attempts, faint
    for i, (pts, outcome) in enumerate(reversed(g.history)):
        age = len(g.history) - 1 - i
        if flying or g.state == "done":
            age += 1
        if age >= 3:
            continue
        col = HISTORY_COLS[age]
        draw_path(px, view, pts, col, 0.75 - age * 0.15, 1)
        if outcome in ("planet", "moon", "rock") and pts[-1] is not None:
            ex, ey = view.p(*pts[-1])
            blend(px, int(ex), int(ey), (220, 110, 90), 0.8 - age * 0.2)
    lx, ly = view.p(*L.launch)
    if g.state in ("aim", "after"):
        pv = g.preview()
        draw_dots(px, view, pv, PREVIEW_COL, 1.0, 2.2)
        a = math.radians(g.angle)
        ln = 3 + (0.05 + 0.13 * g.power / 100) * s
        ex, ey = lx + math.cos(a) * ln, ly - math.sin(a) * ln
        cv.line(lx, ly, ex, ey, AIM_COL)
        blend(px, int(ex), int(ey), (255, 255, 255), 1.0)
        blink = 0.5 + 0.5 * math.sin(g.t * 4)
        draw_disc(px, lx, ly, 1.2, mix((90, 200, 255), (255, 255, 255), blink), 0.9)
    if f is not None and g.state in ("fly", "after", "done") and g.state != "aim":
        if flying:
            draw_path(px, view, f.path, TRAIL_COL, 0.55, 1, fade=True)
            # recent trail, brighter
            recent = f.path[-90:]
            draw_path(px, view, recent, (210, 240, 255), 0.85, 1, fade=True)
            if f.thrust > 0:
                sp = math.hypot(f.vx, f.vy) or 1
                for k in range(1, 4):
                    blend(px, int(ox + (f.x - f.vx / sp * 0.008 * k) * s), int(oy + (f.y - f.vy / sp * 0.008 * k) * s),
                          (255, 170, 70), 0.9 - k * 0.2)
            cx, cy = ox + f.x * s, oy + f.y * s
            draw_disc(px, cx, cy, 1.6, (120, 200, 255), 0.35)
            blend(px, int(cx), int(cy), (255, 255, 255), 1.0)
    for p in g.parts:
        k = clamp(p[4], 0, 1)
        blend(px, int(ox + p[0] * s), int(oy + p[1] * s), p[5], k)
    # top line: level, name and hint (or a message)
    cv.put(0, 0, " " * cols, (200, 200, 210), TOP_BG)
    if g.msg_t > 0 and g.msg:
        cv.center(0, " %s " % g.msg, (255, 230, 170), TOP_BG)
    else:
        head = " Level %d  %s " % (g.num, L.name)
        cv.put(1, 0, head, (200, 240, 255), TOP_BG)
        hint = L.hint
        room = cols - len(head) - 3
        if hint and room > 8:
            if len(hint) > room:
                hint = hint[:room - 3].rstrip() + "..."
            cv.put(1 + len(head), 0, "- " + hint, (150, 156, 186), TOP_BG)
    hud(cv, g, cols, rows)
    if g.state == "done":
        render_banner(cv, g)
    if g.paused:
        overlay(cv, HELP if g.help else PAUSE + ["", SND.label()])
    return cv


HUD_LABEL = (132, 138, 168)      # dim labels (4.7:1 on the bar); values carry the colour
STAR_ON, STAR_OFF = (255, 214, 110), (70, 72, 98)
POWER_COL = (255, 214, 140)


def gauge(cv, x, r, v, n, col):
    """A gauge of coloured cells with half-cell resolution: full = col, empty = a dark trace of it."""
    v = clamp(v, 0.0, 1.0) * n
    empty = mix(HUD_BG, col, 0.22)
    for i in range(n):
        f = v - i
        cv.put(x + i, r, "▌" if 0.25 <= f < 0.75 else " ", col, col if f >= 0.75 else empty)
    return x + n


def hud(cv, g, cols, rows):
    r = rows - 1
    fuel = None
    if g.L.fuel:
        left = g.flight.fuel if (g.flight is not None and g.state == "fly") else g.L.fuel
        fuel = left > 0
    total = sum(g.progress.values())
    # the launch in play decides the stars: three while it is the first, then fewer
    n_try = g.attempts + (1 if g.state in ("aim", "after") else 0)
    if g.state == "done" and g.banner:
        n_try = g.banner[1]
    can = stars_for(max(1, n_try))
    rating = [("★" * can, STAR_ON), ("★" * (3 - can), STAR_OFF)]
    variants = []
    for wide in (2, 1, 0):
        segs = []                                    # pieces: (text, colour, bg) or ("GAUGE", n)
        if wide:
            segs.append((" ORBITAL ", (14, 16, 26), (200, 230, 255)))
        segs += [(" level " if wide else " L", HUD_LABEL, None), ("%d" % g.num, (236, 238, 246), None),
                 ("  launch " if wide else "  try ", HUD_LABEL, None), ("%d " % max(1, n_try), (236, 238, 246), None)]
        segs += [(t, c, None) for t, c in rating]
        segs += [("  angle " if wide else "  aim ", HUD_LABEL, None), ("%5.1f°" % g.angle if wide else "%.1f°" % g.angle, (200, 230, 255), None),
                 ("  power " if wide else "  pow ", HUD_LABEL, None), ("GAUGE", 10 if wide == 2 else 6 if wide else 5),
                 (" %5.1f%%" % g.power if wide else " %d%%" % round(g.power), POWER_COL, None)]
        if fuel is not None:
            segs.append(("  nudge " if wide else "  ", HUD_LABEL, None))
            segs.append((("ready" if wide else "nudge") if fuel else "used", (255, 170, 90) if fuel else (110, 106, 116), None))
        if g.state == "fly" and g.fast:
            segs.append(("  x3", (160, 255, 170), None))
        segs += [("  ★ ", STAR_ON, None), ("%d" % total, (240, 220, 160), None)]
        variants.append(segs)
    right = " ? help  Esc menu " if cols >= 110 else " ? help "

    def width(segs):
        return sum(p[1] if p[0] == "GAUGE" else len(p[0]) for p in segs)

    for segs in variants:
        if width(segs) + len(right) <= cols:
            break
    cv.put(0, r, " " * cols, HUD_LABEL, HUD_BG)
    x = 0
    for p in segs:
        if p[0] == "GAUGE":
            x = gauge(cv, x, r, (g.power - POWER_MIN) / (POWER_MAX - POWER_MIN), p[1], POWER_COL)
        else:
            cv.put(x, r, p[0], p[1], p[2] or HUD_BG)
            x += len(p[0])
    if x + len(right) <= cols:
        cv.put(cols - len(right), r, right, HUD_LABEL, HUD_BG)


def render_banner(cv, g):
    stars, attempts, better, total = g.banner
    lines = ["D O C K E D", "", "", "", "", "",
             "Level %d solved with %d launch%s" % (g.num, attempts, "" if attempts == 1 else "es"),
             ("a better result!  " if better else "") + "stars in total: %d" % total, "",
             "Enter next level    R play again    B back"]
    w = max(len(l) for l in lines) + 6
    h = len(lines) + 2
    x0 = max(0, (cv.cols - w) // 2)
    y0 = max(1, (cv.rows - 1 - h) // 2)
    bg = (16, 20, 38)
    cv.rect(x0, y0 * 2, w, h * 2, bg)
    cv.frame(x0, y0 * 2, w, h * 2, (60, 70, 110))
    for j, l in enumerate(lines):
        if l:
            col = DOCK_COL if j == 0 else (150, 156, 186) if j == len(lines) - 1 else (230, 232, 240)
            cv.center(y0 + 1 + j, l, col, bg, x0, w)
    sx = x0 + w // 2 - 15
    sy = (y0 + 3) * 2
    for i in range(3):
        k = clamp((g.t - g.banner_t - 0.3 - i * 0.3) * 4, 0, 1)
        col = mix((44, 48, 70), DOCK_COL, k) if i < stars else (44, 48, 70)
        draw_star(cv.px, sx + i * 11, sy, col)


HELP = [
    "ORBITAL - keys",
    "",
    "Left / Right        aim (tap: fine steps, hold: faster)",
    "Up / Down           launch power",
    "Space / Enter       launch",
    "Space (in flight)   nudge: a short push forward (fuel levels)",
    "Enter (in flight)   fast forward on / off",
    "R                   abort the flight / try again",
    "N or ]  /  B or [   next / previous unlocked level",
    "",
    "Gravity bends the path; the dots show only its first part.",
    "Reach the gold dock ring (pass numbered beacons first).",
    "1 launch = 3 stars, 2-4 launches = 2 stars, more = 1 star.",
    "",
    "Esc / P             pause menu (Q there: quit, M: sound on / off, V: view)",
    "?                   this help",
    "",
    "Auto mode: the game plays itself (Space pause, +/- speed, Esc stop).",
]
PAUSE = ["P A U S E D", "", "Esc / P / Enter   continue", "?                 help", "M                 sound on / off",
         "V                 view: pixels / ASCII / mono",
         "Q                 quit to the menu"]


# =============================================================================================
# Title screen: a probe looping round a ringed planet
# =============================================================================================
DEMO = Level(0, "demo", "", (1.12, 0.5), [(0.8, 0.5, 0.1, None, "gas", True), (0.2, 0.3, 0.05, 0.0, "ocean", False),
                                         (1.42, 0.8, 0.04, 0.0, "lava", False)],
             [(1.4, 0.2)], moons=[(0.8, 0.5, 0.2, 0.0, TAU / 9, 0.02, 0.0)])
DEMO.station = False


class TitleDemo:
    def __init__(self, cols=80, rows=24):
        self.painter = Painter()
        self.progress = {}
        self.t = 0.0
        self.new_flight()

    def new_flight(self):
        self.f = Flight(DEMO, 90.0, 47.0)
        self.acc = 0.0

    def scene(self, cols, rows, dt):
        """Just the moving star system (a launcher can use this as a thumbnail)."""
        self.t += dt
        self.acc += dt
        n = int(self.acc / DT)
        self.acc -= n * DT
        f = self.f
        f.run(n)
        if f.t > 9.0:
            f.t -= 9.0                  # the probe orbits for ever
        if len(f.path) > 1600:
            del f.path[:len(f.path) - 1200]
        if f.outcome:
            self.new_flight()
            f = self.f
        view = View(cols, rows + 1)
        cv = Canvas(cols, rows)
        base = self.painter.base(DEMO, view)
        cv.px = base[:rows * 2]
        draw_world(cv, cv.px, view, DEMO, self.t, self.t, 0, self.painter.stars)
        cv.text.clear()
        draw_path(cv.px, view, f.path[-500:], TRAIL_COL, 0.8, 1, fade=True)
        cx, cy = view.p(f.x, f.y)
        draw_disc(cv.px, cx, cy, 1.5, (120, 200, 255), 0.4)
        blend(cv.px, int(cx), int(cy), (255, 255, 255), 1.0)
        return cv

    def frame(self, cols, rows, dt, help_, sel, unlocked=1, pick=1, stars=0, solved=0):
        cv = self.scene(cols, rows, dt)
        got = self.progress.get(pick, 0) if self.progress else 0
        sel_txt = "%s %2d %s" % ("<" if pick > 1 else " ", pick, ">" if pick < unlocked else " ")
        items = ["Continue        level %d" % unlocked,
                 "Level select   %s  %s" % (sel_txt, "★" * got + "·" * (3 - got) if got else "new"), "From level 1",
                 "%-14s from level %d" % (AUTO_LABEL, pick)]
        best = "best: %d levels solved, %d stars" % (solved, stars) if solved else None
        extra = ["", "Set angle and power, launch, and let", "gravity carry the probe to the dock."]
        title_screen(cv, "ORBITAL", "a calm gravity puzzle among the planets", items, sel, best, extra=extra,
                     keys="Enter start   Left/Right level   ? help   Esc quit", help_lines=HELP,
                     show_help=help_, dim=0.42)
        return cv


# =============================================================================================
# Main loop
# =============================================================================================
def too_small(term):
    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (70x22).")


AUTO_STEP = 1 / 40          # auto mode steps the game in fixed slices (more of them when sped up)


def screenshot(cols=100, rows=32):
    """README picture: real play (the auto-mode pilot) with a fixed seed, at a good moment, HUD and all.
    Level 8 (Waypoints), pilot seed 1, launch 4 at 43 s: the probe has slung round both planets through
    beacon 1 and is about to dock, the three earlier tries still drawn faintly."""
    was, SND.enabled = SND.enabled, False
    try:
        g = Game(8, {}, auto=True)                   # empty progress: nothing read, nothing saved
        pilot = Pilot(random.Random(1))
        for _ in range(1730):
            pilot.think(60.0)                        # a generous budget: the search always finishes (deterministic)
            pilot.update(g, AUTO_STEP)
            g.update(AUTO_STEP)
        return render(g, Painter(), cols, rows)
    finally:
        SND.enabled = was


def run_auto(term, start, progress):
    """Auto mode: the pilot plays from level `start` onwards until the viewer stops it. Nothing is saved.
    Returns the level it reached (the title's level select stays within the unlocked ones)."""
    auto = AutoMode()
    g = Game(start, dict(progress), auto=True)
    painter = Painter()
    pilot = Pilot()
    last = time.time()
    while True:
        now = time.time()
        dt = min(0.1, now - last)
        last = now
        for k in term.keys(0):
            a = auto.key(k)
            if a == "stop":
                return g.num
            if a == "sound" and SND.toggle():
                SND.play("sound_on")
        if not auto.paused and not auto.help:
            pilot.think(0.012)                       # the search shares the frame with drawing
        for _ in range(auto.steps(dt, AUTO_STEP)):
            pilot.update(g, AUTO_STEP)
            g.update(AUTO_STEP)
        cols, rows = term.size()
        if cols < 70 or rows < 22:
            too_small(term)
            time.sleep(0.2)
            continue
        cv = render(g, painter, cols, rows)
        status = ("studying the map" if pilot.target is None else "docked" if g.state == "done" else
                  "launch %d" % (g.attempts + (g.state == "aim")))
        auto.banner(cv, row=0, extra="level %d  %s" % (g.num, status))
        term.write(cv.emit())
        time.sleep(max(0.0, 1 / 40 - (time.time() - now)))


def main():
    with Terminal() as term:
        demo = TitleDemo()
        sel, pick = 0, None
        while True:
            progress = load_progress()
            unlocked = max(progress, default=0) + 1
            pick = unlocked if pick is None else clamp(pick, 1, unlocked)
            help_, start = False, None
            last = time.time()
            while start is None:                      # title
                now = time.time()
                cols, rows = term.size()
                if cols < 70 or rows < 22:
                    too_small(term)
                    if any(k in ("q", "esc") for k in term.keys(0.3)):
                        return
                    continue
                demo.progress = progress
                cv = demo.frame(cols, rows, min(0.1, now - last), help_, sel, unlocked, pick,
                                sum(progress.values()), max(progress, default=0))
                term.write(cv.emit())
                last = now
                for k in term.keys(1 / 30):
                    if help_:
                        help_ = False
                    elif k == "?":
                        help_ = True
                    elif k in ("q", "esc"):
                        return
                    elif k in ("up", "w"):
                        sel = (sel - 1) % 4
                    elif k in ("down", "s"):
                        sel = (sel + 1) % 4
                    elif k in ("left", "a", "right", "d") and sel in (1, 3):   # auto mode starts at the picked level
                        pick = clamp(pick + (1 if k in ("right", "d") else -1), 1, unlocked)
                    elif k in ("left", "a", "right", "d"):
                        sel = 1
                        pick = clamp(pick + (1 if k in ("right", "d") else -1), 1, unlocked)
                    elif k in ("enter", " "):
                        start = (unlocked, pick, 1, pick)[sel]
            if sel == 3:
                pick = run_auto(term, start, progress)
                continue
            g = Game(start, progress)
            painter = Painter()
            last = time.time()
            back = False
            while not back:
                now = time.time()
                for k in term.keys(0):
                    a = shared_key(k, g.paused, pause_keys=("esc", "p", "q"))
                    if a == "pause":
                        g.paused = True
                    elif a == "resume":
                        g.paused = g.help = False
                    elif a == "quit":
                        back = True
                    elif a == "sound":
                        if SND.toggle():
                            SND.play("sound_on")
                    elif a == "help":
                        g.help = not g.help
                        g.paused = True
                    elif a is None:
                        g.key(k, now)
                g.update(min(0.1, now - last))
                last = now
                cols, rows = term.size()
                if cols < 70 or rows < 22:
                    too_small(term)
                    time.sleep(0.2)
                    continue
                term.write(render(g, painter, cols, rows).emit())
                time.sleep(max(0.0, 1 / 40 - (time.time() - now)))
            pick = g.num


# =============================================================================================
# Tests
# =============================================================================================
def keys_to(g, angle, power, held=False):
    """Press the arrow keys like a player until the aim is (angle, power). held: fast key repeat first."""
    now = 1000.0
    for _ in range(4000):
        da = (angle - g.angle + 180) % 360 - 180
        dp = power - g.power
        if abs(da) < 1e-9 and abs(dp) < 1e-9:
            return True
        if abs(da) > 1e-9:
            k = "left" if da > 0 else "right"
            big = held and abs(da) > 12
        else:
            k = "up" if dp > 0 else "down"
            big = held and abs(dp) > 12
        now += 0.03 if big else 0.5
        g.key(k, now)
    return False


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
    import arcadekit
    import os
    import tempfile
    t0 = time.time()
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp.close()
    os.unlink(tmp.name)
    arcadekit.SCORES_PATH = tmp.name          # never touch the player's real scores
    nums = list(range(1, len(INTRO) + 1)) + [len(INTRO) + g for g in range(1, 61)]
    tries_total, worst = 0, (0, 0)
    for num in nums:
        L = get_level(num)
        assert L.beacons, "level %d has no dock" % num
        found = search(L)
        if found is None:
            found = search(L, ANGLE_STEP, POWER_STEP)
        assert found is not None, "level %d (%s) cannot be solved" % (num, L.name)
        a, p, tries = found
        tries_total += tries
        worst = max(worst, (tries, num))
        assert fly(L, a, p).outcome == "dock"
        if num > 3:
            assert fly(L, *L.aim).outcome != "dock", "level %d is solved by the default aim" % num
        if num > len(INTRO):
            assert not direct_shot(L), "level %d is solved by aiming straight at the dock" % num
        if L.solution:
            assert fly(L, *L.solution).outcome == "dock", "level %d: its generated solution fails" % num
        # the arrow keys reach the solution exactly, and launching it from the game docks
        g = Game(num, {n: 3 for n in range(1, num)})
        assert keys_to(g, a, p, held=num % 2 == 0), "level %d: keys cannot reach %.1f / %.1f" % (num, a, p)
        assert g.angle == a and g.power == p
        g.key("enter", 0)
        for _ in range(int(MAX_T * 30) + 10):
            g.update(1 / 30)
            if g.state != "fly":
                break
        assert g.state == "done", "level %d: the game did not dock (%s)" % (num, g.state)
        assert g.banner[0] == 3 and g.progress[num] == 3
    # generated levels are fixed by their number
    _CACHE.clear()
    for g_ in (1, 17, 42):
        A, B = generate(g_, 0), generate(g_, 0)
        assert A.planets == B.planets and A.beacons == B.beacons and A.rocks == B.rocks and A.solution == B.solution
    # the same launch flies the same path; the preview is the start of the real flight
    for num in (2, 4, 6, 20, 40):
        L = get_level(num)
        for a, p in ((10.0, 40.0), (33.5, 72.5), (300.0, 55.0)):
            f1, f2 = fly(L, a, p), fly(L, a, p)
            assert f1.path == f2.path and f1.outcome == f2.outcome, "flights differ"
            g = Game(num, {})
            g.angle, g.power = a, p
            pv = g.preview()
            assert pv == f1.path[:len(pv)], "the preview does not match the flight"
            # flying it frame by frame in the game gives the same path
            g.launch()
            while g.state == "fly":
                g.update(0.037)
            assert g.history[0][0][-1] == f1.path[-1], "the game flight differs from the simulation"
    # preview is generous early, short later
    assert get_level(1).preview > get_level(len(INTRO) + 50).preview
    # wormholes carry the probe; a nudge changes the path and uses the fuel
    L = get_level(6)
    a, p, _ = search(L)
    assert None in fly(L, a, p).path, "the wormhole level is solved without the wormhole"
    L = get_level(7)
    a, p, _ = search(L)
    f1 = Flight(L, a, p)
    f1.run(200)
    assert f1.outcome is None and f1.nudge() and not f1.nudge() and f1.fuel == 0
    f1.finish()
    f0 = fly(L, a, p)
    assert f1.path[:201] == f0.path[:201] and f1.path[260:270] != f0.path[260:270], "the nudge does nothing"
    # attempts and stars; progress is saved
    g = Game(1, {})
    g.angle, g.power = 180.0, 30.0
    g.key(" ", 0)
    while g.state == "fly":
        g.update(0.05)
    assert g.state == "after" and g.attempts == 1 and len(g.history) == 1
    g.key("n", 0)
    assert g.num == 1, "a locked level opened"
    assert stars_for(1) == 3 and stars_for(4) == 2 and stars_for(5) == 1
    assert load_progress().get(1) == 3 and load_scores()[GAME]["stars"] >= 3
    # key repeat: taps are fine, holding speeds up, the aim stays on the grid
    g = Game(1, {})
    a0 = g.angle
    g.key("left", 0.0)
    g.key("left", 1.0)
    assert abs(g.angle - a0 - 2 * ANGLE_STEP) < 1e-9
    for i in range(30):
        g.key("up", 5.0 + i * 0.03)
    assert g.power == POWER_MAX
    for i in range(40):
        g.key("right", 9.0 + i * 0.03)
    assert abs(g.angle / ANGLE_STEP - round(g.angle / ANGLE_STEP)) < 1e-9
    # auto mode: the pilot docks level after level at x8, in a few launches, and saves nothing
    before = load_scores()
    auto = AutoMode()
    for _ in range(5):
        auto.key("+")
    assert auto.speed == 8.0
    g = Game(1, dict(load_progress()), auto=True)
    pilot = Pilot(random.Random(3))
    docked = []
    for frame in range(40 * 120):                   # up to 120 s of watching at x8
        pilot.think(1.0)
        for _ in range(auto.steps(1 / 40, AUTO_STEP)):
            n, st = g.num, g.state
            pilot.update(g, AUTO_STEP)
            g.update(AUTO_STEP)
            if g.state == "done" and st != "done":
                docked.append((n, g.attempts))
        if g.num > 4:
            break
    assert [n for n, _ in docked] == [1, 2, 3, 4], "the pilot did not get through levels 1-4: %s" % docked
    assert all(1 <= a <= 5 for _, a in docked)
    assert load_scores() == before, "auto mode saved progress"
    # the pilot's quick search finds a docking launch on every level the self-test checks
    for num in (2, 6, 9, len(INTRO) + 31, len(INTRO) + 51):
        r = None
        for r in guided_steps(get_level(num)):
            if r is not None:
                break
        assert r and fly(get_level(num), r[0], r[1]).outcome == "dock", "guided search failed on level %d" % num
    # the real auto-mode loop with scripted keys: speed up, pause, help, stop
    term = FakeTerm([(0.05, "+"), (0.1, "+"), (0.15, "+"), (0.8, " "), (1.0, "?"), (1.1, "x"), (1.2, " "), (2.0, "esc")])
    assert run_auto(term, 2, {1: 3}) >= 2 and term.frames > 10 and not term.script
    assert load_scores() == before, "auto mode saved progress"
    # every screen draws at the smallest and a large window
    painter = Painter()
    for cols, rows in ((70, 22), (160, 45), (101, 37)):
        demo = TitleDemo()
        for i in range(3):
            demo.frame(cols, rows, 0.05, i == 1, i, 5, 3, 12, 4).emit(True)
        demo.frame(cols, rows, 0.05, False, 3, 5, 3, 12, 4).emit(True)      # the auto-mode entry
        for num in (1, 5, 6, 8, len(INTRO) + 33):
            g = Game(num, {1: 3})
            render(g, painter, cols, rows).emit(True)
            g.launch()
            for _ in range(20):
                g.update(0.05)
                render(g, painter, cols, rows).emit(False)
            g.paused = True
            render(g, painter, cols, rows).emit(True)
            g.help = True
            render(g, painter, cols, rows).emit(True)
            g.paused = False
            g.end_flight("dock")
            g.update(1.0)
            cv = render(g, painter, cols, rows)
            assert len(cv.px) == rows * 2 and all(len(r) == cols for r in cv.px)
            cv.emit(True)
    os.path.exists(tmp.name) and os.unlink(tmp.name)
    print("Self-test ok: %d hand-made + 60 generated levels all solvable with the arrow keys "
          "(search tried %d launches, worst %d on level %d), no default aim solves a level past 3, "
          "no generated level solved by a straight shot, deterministic flights, preview = flight, wormhole, nudge, "
          "stars, saving, auto mode (pilot docks levels 1-4 at x8, nothing saved), rendering at 70x22 / 160x45 "
          "(%.1fs)" % (len(INTRO), tries_total, worst[0], worst[1], time.time() - t0))


def bench():
    import arcadekit
    import os
    import tempfile
    arcadekit.SCORES_PATH = os.path.join(tempfile.gettempdir(), "orbital-bench-scores.json")
    t = time.time()
    for num in range(len(INTRO) + 1, len(INTRO) + 21):
        _CACHE.pop(num, None)
        get_level(num)
    print("generate 20 levels: %.0f ms each" % ((time.time() - t) / 20 * 1000))
    L = get_level(len(INTRO) + 30)
    t = time.time()
    steps = 0
    for a in range(0, 360, 10):
        steps += fly(L, a, 55).steps
    print("physics: %.2f us per step" % ((time.time() - t) / steps * 1e6))
    painter = Painter()
    for cols, rows in ((70, 22), (160, 45), (200, 56)):
        g = Game(len(INTRO) + 30, {})
        render(g, painter, cols, rows)
        g.angle, g.power = 20.0, 55.0
        g.history = [(fly(L, 18 + k, 50).path[::2], "lost") for k in range(3)]
        g.launch()
        g.update(0.8)
        t = time.time()
        for _ in range(30):
            g.update(1 / 40)
            render(g, painter, cols, rows).emit(True)
        fly_ms = (time.time() - t) / 30 * 1000
        g2 = Game(len(INTRO) + 30, {})
        g2.history = g.history
        t = time.time()
        for i in range(30):
            g2.angle = (g2.angle + 0.5) % 360
            render(g2, painter, cols, rows).emit(True)
        aim_ms = (time.time() - t) / 30 * 1000
        demo = TitleDemo()
        t = time.time()
        for _ in range(30):
            demo.frame(cols, rows, 1 / 30, False, 0).emit(True)
        print("frame at %dx%d: flight %.1f ms, aiming %.1f ms, title %.1f ms" % (
            cols, rows, fly_ms, aim_ms, (time.time() - t) / 30 * 1000))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--bench" in sys.argv:
        bench()
    else:
        main()
