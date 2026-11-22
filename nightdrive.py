#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""NIGHTDRIVE - an arcade checkpoint race through the night.

A winding, hilly highway after dark: neon city, a moonlit coast, a misty pine forest, the desert, a mountain
pass and a rainstorm. Your headlights carve the road out of the night, lamp posts throw pools of light,
traffic glows red ahead of you and on some stages comes towards you in the other lanes. Reach every
checkpoint before the clock runs out - each one buys more time.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
Run:        python3 nightdrive.py
Self-test:  python3 nightdrive.py --selftest
Benchmark:  python3 nightdrive.py --bench
"""
import math
import random
import sys
import time

from arcadekit import FONT, Canvas, Terminal, clamp, load_scores, mix, overlay, shade, shared_key, submit, title_screen

try:
    from arcadesound import Sound
except ImportError:
    class Sound:  # sound engine missing: stay silent
        available = enabled = False
        def __init__(self, *a, **k): pass
        def play(self, *a, **k): pass
        def toggle(self): return False
        def label(self): return "Sound: none"
        def stop(self): pass

GAME = "nightdrive"

# ---- sound effects (short and soft; nothing loops) ---------------------------------------------------------
SND = Sound(GAME, {
    "beep": [dict(w="square", f=659, d=0.12, v=0.38, duty=0.25, r="hold")],                       # 3, 2, 1
    "go": [dict(w="square", f=1319, d=0.36, v=0.34, duty=0.25, r="lin", vib=(7, 0.15)),
           dict(w="tri", f=659, d=0.36, v=0.3, at=0, r="lin")],
    "gear": [dict(w="saw", f=95, f2=170, d=0.09, v=0.26), dict(w="square", f=48, f2=85, d=0.09, v=0.18, duty=0.2, at=0)],
    "checkpoint": [dict(w="tri", f=784, d=0.08, v=0.45), dict(w="tri", f=988, d=0.08, v=0.45),
                   dict(w="square", f=1319, d=0.32, v=0.3, duty=0.25, vib=(6, 0.2)),
                   dict(w="tri", f=659, d=0.32, v=0.25, at=0.16)],
    "tick": [dict(w="square", f=1760, d=0.025, v=0.28, duty=0.5)],                                  # low time
    "tock": [dict(w="square", f=2349, d=0.03, v=0.32, duty=0.5)],                                   # last 3 s
    "crash": [dict(w="noise", f=3200, f2=260, d=0.32, v=0.62), dict(w="square", f=95, f2=40, d=0.24, v=0.45, at=0),
              dict(w="saw", f=880, f2=560, d=0.42, v=0.12, at=0.06, r="lin", vib=(28, 0.7))],          # crunch + skid
    "bump": [dict(w="noise", f=1400, f2=200, d=0.11, v=0.42), dict(w="square", f=82, f2=50, d=0.1, v=0.32, at=0)],
    "verge": [dict(w="noise", f=230, f2=170, d=0.26, v=0.22, a=0.02, r="hold")],                    # gravel rumble
    "whoosh": [dict(w="noise", f=4200, f2=1100, d=0.3, v=0.16, a=0.12, r="lin")],                  # overtaking
    "finish": [dict(w="tri", f=523, d=0.11), dict(w="tri", f=659, d=0.11), dict(w="tri", f=784, d=0.11),
               dict(w="tri", f=1047, d=0.11), dict(w="square", f=1047, d=0.55, v=0.3, duty=0.25, vib=(6, 0.25)),
               dict(w="tri", f=523, d=0.55, v=0.35, at=0.44), dict(w="tri", f=784, d=0.55, v=0.25, at=0.44)],
    "timeup": [dict(w="square", f=440, d=0.18, v=0.32, duty=0.25), dict(w="square", f=370, d=0.18, v=0.32, duty=0.25),
               dict(w="square", f=311, d=0.18, v=0.32, duty=0.25),
               dict(w="tri", f=262, f2=196, d=0.6, v=0.45, r="lin", vib=(5, 0.3))],
    "select": [dict(w="square", f=880, d=0.035, v=0.26, duty=0.25)],
    "start": [dict(w="square", f=659, d=0.06, v=0.3, duty=0.25), dict(w="square", f=988, d=0.14, v=0.3, duty=0.25)],
})
GEARS = (0.3, 0.52, 0.72, 0.88)  # share of top speed where the engine "shifts up" (a short blip)

# ---- world and car constants -------------------------------------------------------------------------------
SEG = 200.0               # length of one road segment (world units)
RW = 1400.0               # half the road width
CAM_H = 1000.0            # camera height above the road
DEPTH = 0.84              # 1 / tan(half the field of view)
PLAYER_Z = CAM_H * DEPTH  # the car sits this far in front of the camera (projects to the screen bottom)
DRAW = 150                # segments drawn ahead
MAXV = 8000.0             # top speed, world units per second
KMH = 280.0 / MAXV        # world units per second -> km/h on the speedometer
M_PER_UNIT = (280.0 / 3.6) / MAXV
STEER_RATE = 1.9          # road half-widths per second at full lock
CENTRIF = 0.5             # how hard curves push the car outwards
CAR_W = 500.0             # width of a car in world units
CAR_HALF = CAR_W / RW / 2
OFFROAD_V = MAXV * 0.33   # the verge will not let you go faster than this
BEAM_N = 44               # how many segments the headlights reach

# ---- stages ------------------------------------------------------------------------------------------------
# colours are "fully lit"; the renderer darkens them by the light falling on them and fades them into the haze
STAGES = [
    dict(name="NEON CITY", scene="city", lanes=3, oncoming=False, traffic=9, curve=2.0, straight=0.38, hill=16,
         length=2300, seed=101, sky=((4, 2, 16), (66, 20, 88)), haze=(50, 18, 66), far=(30, 20, 46),
         ground=((52, 44, 72), (58, 50, 80)), road=((80, 78, 98), (75, 73, 93)), rumble=((255, 60, 200), (225, 225, 240)),
         lane=(240, 240, 250), amb=0.42, fog=0.85, moon=0.055, stars=0.3, lamp=0.55,
         neon=((255, 60, 200), (60, 230, 255), (255, 210, 70), (140, 90, 255))),
    dict(name="COASTLINE", scene="coast", lanes=3, oncoming=False, traffic=8, curve=2.5, straight=0.3, hill=24,
         length=2400, seed=202, sky=((2, 4, 18), (28, 46, 92)), haze=(24, 36, 70), far=(10, 24, 50),
         ground=((14, 34, 62), (110, 96, 76)), ground2=((16, 38, 68), (118, 104, 82)), road=((78, 80, 92), (73, 75, 87)),
         rumble=((230, 50, 50), (230, 230, 236)), lane=(240, 240, 240), amb=0.34, fog=0.8, moon=0.1, stars=1.0,
         lamp=0.4, neon=((255, 120, 60), (60, 200, 255), (255, 230, 120), (255, 80, 120))),
    dict(name="PINE FOREST", pace=25.5, scene="forest", lanes=4, oncoming=True, traffic=6, curve=2.3, straight=0.3, hill=40,
         length=2300, seed=303, sky=((2, 6, 10), (24, 40, 46)), haze=(22, 34, 38), far=(14, 26, 22),
         ground=((26, 58, 30), (30, 66, 34)), road=((74, 76, 80), (70, 72, 76)), rumble=((230, 230, 230), (40, 40, 44)),
         lane=(235, 235, 235), amb=0.3, fog=1.0, fogpow=0.65, moon=0.05, stars=0.6, lamp=0.4,
         neon=((255, 200, 80), (120, 255, 160), (255, 120, 60), (200, 220, 255))),
    dict(name="DESERT HIGHWAY", pace=25.5, scene="desert", lanes=4, oncoming=True, traffic=6, curve=1.7, straight=0.5, hill=60,
         length=2600, seed=404, sky=((6, 3, 22), (86, 44, 70)), haze=(66, 36, 60), far=(46, 28, 40),
         ground=((120, 92, 62), (128, 100, 68)), road=((84, 78, 82), (79, 73, 77)), rumble=((240, 160, 40), (230, 226, 220)),
         lane=(245, 240, 230), amb=0.36, fog=0.75, moon=0.13, stars=1.2, lamp=0.45,
         neon=((255, 70, 90), (90, 220, 255), (255, 200, 60), (255, 120, 220))),
    dict(name="MOUNTAIN PASS", pace=21.5, scene="mountain", lanes=4, oncoming=True, traffic=5, curve=3.2, straight=0.18, hill=50,
         length=2400, seed=505, sky=((2, 4, 20), (40, 52, 96)), haze=(30, 38, 72), far=(24, 28, 50),
         ground=((62, 62, 70), (68, 68, 76)), road=((76, 76, 84), (71, 71, 79)), rumble=((235, 40, 40), (235, 235, 240)),
         lane=(240, 240, 245), amb=0.34, fog=0.8, moon=0.085, stars=1.0, lamp=0.4,
         neon=((255, 210, 60), (120, 200, 255), (255, 120, 60), (220, 220, 255))),
    dict(name="STORM RUN", scene="storm", lanes=3, oncoming=False, traffic=10, curve=2.3, straight=0.3, hill=22,
         length=2400, seed=606, sky=((6, 8, 14), (40, 46, 62)), haze=(36, 42, 56), far=(22, 26, 36),
         ground=((34, 40, 46), (38, 44, 50)), road=((58, 64, 78), (55, 61, 75)), rumble=((240, 60, 60), (215, 220, 230)),
         lane=(230, 236, 245), amb=0.34, fog=1.0, fogpow=0.7, moon=0.0, stars=0.0, lamp=0.55, rain=True,
         neon=((255, 60, 120), (60, 220, 255), (255, 200, 80), (160, 255, 120))),
]
TRAFFIC_COLOURS = [(200, 40, 40), (230, 230, 235), (40, 90, 200), (240, 190, 40), (40, 160, 90), (120, 120, 130),
                   (160, 60, 200), (230, 110, 30), (30, 30, 36)]


def allowance(si):
    """Seconds on the clock for stage si (also the checkpoint bonus when you reach it)."""
    return int(STAGES[si]["length"] / STAGES[si].get("pace", 28.0) + 0.5) + (4 if si == 0 else 0)


def traffic_gap(st):
    """Same-direction cars keep at least this far apart, so there is always a way past."""
    return (9 if len(same_lanes(st)) > 2 else 15) * SEG


def lanes_x(st):
    n = st["lanes"]
    return [-1 + (2 * k + 1) / n for k in range(n)]


def same_lanes(st):
    xs = lanes_x(st)
    return xs[len(xs) // 2:] if st["oncoming"] else xs


def onc_lanes(st):
    xs = lanes_x(st)
    return xs[:len(xs) // 2] if st["oncoming"] else []


# =============================================================================================
# The course: segments with curve, height, scenery
# =============================================================================================
SOLID = {"lamp": 180, "palm": 380, "pine": 560, "cactus": 320, "rock": 620, "bill": 1500, "chev": 300,
         "bldg": 2600, "post": 0}     # collision widths (world units); posts are harmless


def ease_in(a, b, p):
    return a + (b - a) * p * p


def ease_io(a, b, p):
    return a + (b - a) * (0.5 - math.cos(p * math.pi) / 2)


class Course:
    """Stages start..last laid end to end, then a straight run-out past the finish."""

    def __init__(self, start=0, stop=None):
        stop = len(STAGES) if stop is None else stop
        self.curve, self.y, self.stage, self.spr = [], [0.0], [], []
        self.ranges = []                       # (stage index, first segment, segment after its checkpoint)
        self.gates = {}
        for s in range(start, stop):
            i0 = len(self.curve)
            self.build_stage(s)
            self.ranges.append((s, i0, len(self.curve)))
        last = self.ranges[-1][0]
        self.finish = len(self.curve)
        for (s, i0, i1) in self.ranges:
            self.gates[i1] = "finish" if i1 == self.finish else "cp"
        self.add_road(0, DRAW + 260, 0, 0, 0, last)
        self.place_runout(last)
        self.n = len(self.curve)
        self.light = [0.0] * (self.n + 1)
        for i in range(self.n):
            for kind, off, seed in self.spr[i]:
                if kind == "lamp":
                    amp = STAGES[self.stage[i]]["lamp"]
                    for d in range(-9, 10):
                        j = i + d
                        if 0 <= j < self.n:
                            self.light[j] = min(1.0, self.light[j] + amp * (1 - abs(d) / 10) ** 2)
        self.pal_cache = {}

    def add(self, curve, y, s):
        self.curve.append(curve)
        self.y.append(y)
        self.stage.append(s)
        self.spr.append([])

    def add_road(self, enter, hold, leave, curve, hill, s):
        y0 = self.y[-1]
        y1 = y0 + hill * SEG
        total = max(1, enter + hold + leave)
        for n in range(enter):
            self.add(ease_in(0, curve, n / enter), ease_io(y0, y1, (n + 1) / total), s)
        for n in range(hold):
            self.add(curve, ease_io(y0, y1, (enter + n + 1) / total), s)
        for n in range(leave):
            self.add(ease_io(curve, 0, n / leave), ease_io(y0, y1, (enter + hold + n + 1) / total), s)

    def build_stage(self, s):
        st = STAGES[s]
        rnd = random.Random(st["seed"])
        i0 = len(self.curve)
        ybase = self.y[-1]
        self.add_road(0, 70, 0, 0, 0, s)
        while len(self.curve) - i0 < st["length"] - 200:
            enter, hold, leave = rnd.randint(25, 55), rnd.randint(30, 110), rnd.randint(25, 55)
            if rnd.random() < st["straight"]:
                curve = 0.0
                hold += rnd.randint(20, 80)
            else:
                curve = rnd.choice((-1, 1)) * rnd.uniform(0.45, 1.0) * st["curve"]
            hill = rnd.uniform(-1, 1) * st["hill"]
            rel = (self.y[-1] - ybase) / SEG
            if abs(rel) > st["hill"] * 1.5:              # keep the stage from climbing or sinking forever
                hill = -math.copysign(abs(hill), rel)
            room = st["length"] - 200 - (len(self.curve) - i0)
            if enter + hold + leave > room:
                hold = max(0, room - enter - leave)
            self.add_road(enter, hold, leave, curve, hill, s)
        rel = (self.y[-1] - ybase) / SEG
        self.add_road(40, st["length"] - (len(self.curve) - i0) - 80, 40, 0, -rel * 0.5, s)
        self.scenery(s, i0, len(self.curve), rnd)

    def put(self, i, kind, off):
        self.spr[i].append((kind, off, (i * 7919 + int(off * 100)) & 0xFFFF))

    def scenery(self, s, i0, i1, rnd):
        st = STAGES[s]
        scene = st["scene"]
        for i in range(i0 + 4, i1 - 2):
            n = i - i0
            c = self.curve[i]
            if scene in ("city", "storm"):
                if n % 16 == 0:
                    self.put(i, "lamp", -1.28)
                if n % 16 == 8:
                    self.put(i, "lamp", 1.28)
                if n % 11 == 3 and rnd.random() < (0.85 if scene == "city" else 0.45):
                    self.put(i, "bldg", rnd.choice((-1, 1)) * rnd.uniform(3.0, 4.8))
                if n % 53 == 20:
                    self.put(i, "bill", rnd.choice((-1, 1)) * 2.0)
                if scene == "storm" and n % 9 == 4:
                    self.put(i, "post", -1.12)
                    self.put(i, "post", 1.12)
            elif scene == "coast":
                if n % 8 == 0:
                    self.put(i, "post", -1.12)
                    self.put(i, "post", 1.12)
                if rnd.random() < 0.13:
                    self.put(i, "palm", rnd.uniform(1.45, 3.4))
                if n % 40 == 20:
                    self.put(i, "lamp", -1.28)
                if n % 140 == 70:
                    self.put(i, "bill", 2.1)
            elif scene == "forest":
                if n % 10 == 0:
                    self.put(i, "post", -1.12)
                    self.put(i, "post", 1.12)
                if rnd.random() < 0.42:
                    self.put(i, "pine", rnd.choice((-1, 1)) * rnd.uniform(1.5, 4.2))
                if n % 160 == 80:
                    self.put(i, "lamp", 1.28)
            elif scene == "desert":
                if n % 12 == 0:
                    self.put(i, "post", -1.12)
                    self.put(i, "post", 1.12)
                if rnd.random() < 0.06:
                    self.put(i, "cactus", rnd.choice((-1, 1)) * rnd.uniform(1.45, 4.0))
                if rnd.random() < 0.04:
                    self.put(i, "rock", rnd.choice((-1, 1)) * rnd.uniform(1.5, 3.8))
                if n % 230 == 115:
                    self.put(i, "bill", rnd.choice((-1, 1)) * 2.0)
                    self.put(i, "lamp", 1.28)
            elif scene == "mountain":
                if n % 8 == 0:
                    self.put(i, "post", -1.12)
                    self.put(i, "post", 1.12)
                if rnd.random() < 0.09:
                    self.put(i, "rock", rnd.choice((-1, 1)) * rnd.uniform(1.45, 3.6))
                if rnd.random() < 0.07:
                    self.put(i, "pine", rnd.choice((-1, 1)) * rnd.uniform(1.8, 4.0))
                if abs(c) > st["curve"] * 0.4 and n % 6 == 0:          # chevrons on the outside of curves
                    self.put(i, "chev", -math.copysign(1.35, c))

    def place_runout(self, s):
        i0 = self.finish
        for i in range(i0 + 2, self.n if hasattr(self, "n") else len(self.curve)):
            if (i - i0) % 14 == 0:
                self.put(i, "lamp", -1.28 if (i - i0) % 28 else 1.28)

    def seg(self, z):
        return min(len(self.curve) - 1, max(0, int(z // SEG)))


_COURSES = {}


def course(start=0, stop=None):
    key = (start, stop)
    if key not in _COURSES:
        _COURSES[key] = Course(start, stop)
    return _COURSES[key]


# =============================================================================================
# The race
# =============================================================================================
class Car:
    __slots__ = ("z", "x", "v", "v0", "col", "onc", "prev", "ahead")

    def __init__(self, z, x, v, col, onc):
        self.z, self.x, self.v, self.v0, self.col, self.onc = z, x, v, v, col, onc
        self.prev = z
        self.ahead = True


class Race:
    def __init__(self, start=0, auto=True, seed=None, stop=None, demo=False):
        self.trk = course(start, stop)
        self.start = start
        self.auto = auto
        self.demo = demo
        self.rnd = random.Random(seed)
        self.ci = 0                                  # index into trk.ranges: the stage being driven
        st = self.st
        self.pos = 0.0
        self.x = same_lanes(st)[len(same_lanes(st)) // 2]
        self.speed = 0.0
        self.steer = 0.0
        self.steer_dir = 0
        self.steer_hold = 0.0
        self.last_press = {-1: -9.0, 1: -9.0}
        self.gas = 0.0
        self.brake_t = 0.0
        self.auto_lock = 0.0
        self.time_left = float(allowance(start))
        self.t = 0.0
        self.state = "run" if demo else "count"
        self.t_state = 0.0
        self.score = 0.0
        self.dist = 0.0
        self.overtakes = 0
        self.crashes = 0
        self.spin = 0.0
        self.spin_dir = 1
        self.hit_cool = 0.0
        self.shake = 0.0
        self.bgx = 0.0
        self.flash = 0.0
        self.next_flash = 6.0
        self.msgs = []                               # [text, ttl, colour]
        self.paused = self.help = False
        self.cars = []
        self.cp_times = []                           # time left at each checkpoint
        self.reached = start                         # furthest stage entered
        self.count_n = -1                            # last countdown number beeped
        self.tick_s = 99                             # last low-time second ticked
        self.gear = 0
        self.verge_cd = 0.0
        self.fill_traffic(initial=True)

    # ---- small helpers ---------------------------------------------------------------------------------
    @property
    def st(self):
        return STAGES[self.trk.ranges[min(self.ci, len(self.trk.ranges) - 1)][0]]

    @property
    def stage_index(self):
        return self.trk.ranges[min(self.ci, len(self.trk.ranges) - 1)][0]

    @property
    def pz(self):
        return self.pos + PLAYER_Z

    def to_checkpoint(self):
        end = self.trk.ranges[min(self.ci, len(self.trk.ranges) - 1)][2]
        return max(0.0, end * SEG - self.pz)

    def say(self, s, ttl=2.5, col=(255, 240, 200)):
        self.msgs.append([s, ttl, col])

    def sfx(self, name, vol=1.0, gap=0.04):
        """A sound effect - never from the title demo (and silent in the tests anyway)."""
        if not self.demo:
            SND.play(name, vol, gap)

    # ---- input: the same calls for the player and the autopilot -------------------------------------
    def key(self, k):
        if self.state != "run":
            return
        if k in ("left", "a"):
            self.press_steer(-1)
        elif k in ("right", "d"):
            self.press_steer(1)
        elif k in ("up", "w"):
            self.gas = min(1.0, self.gas + 0.34)
            self.auto_lock = 0.0
        elif k in ("down", "s", " "):
            self.brake_t = 0.22
            self.auto_lock = 0.3
            self.gas = 0.0

    def press_steer(self, d):
        if self.steer_dir == -d and self.steer_hold > 0:
            self.steer *= 0.4                       # changing direction: let go of the old lock quickly
        self.steer_dir = d
        repeat = self.t - self.last_press[d] < 0.6
        self.steer_hold = 0.11 if not repeat else 0.12
        self.last_press[d] = self.t

    # ---- simulation ------------------------------------------------------------------------------------
    def update(self, dt):
        if self.paused:
            return
        while dt > 1e-6:
            h = min(dt, 1 / 60)
            self.step(h)
            dt -= h
        self.msgs = [m for m in self.msgs if m[1] > 0]

    def step(self, dt):
        self.t += dt
        self.t_state += dt
        for m in self.msgs:
            m[1] -= dt
        if self.state == "count":
            if int(self.t_state) != self.count_n and self.t_state < 3.0:
                self.count_n = int(self.t_state)
                self.sfx("beep")
            if self.t_state >= 3.0:
                self.state, self.t_state = "run", 0.0
                self.say("GO!", 1.2, (120, 255, 140))
                self.sfx("go")
            self.traffic(dt)
            return
        running = self.state == "run"
        if running and not self.demo:
            self.time_left -= dt
            if self.time_left <= 0:
                self.time_left = 0.0
                self.state, self.t_state = "timeup", 0.0
                running = False
                self.sfx("timeup")
            elif self.time_left < 10:                # one tick per second when time runs low
                s = int(math.ceil(self.time_left))
                if s != self.tick_s:
                    self.tick_s = s
                    self.sfx("tock" if s <= 3 else "tick", 0.8)
            else:
                self.tick_s = 99
        trk = self.trk
        # controls
        self.steer_hold -= dt
        self.brake_t -= dt
        self.auto_lock -= dt
        self.hit_cool -= dt
        self.shake = max(0.0, self.shake - dt * 3)
        if not self.auto:
            self.gas = max(0.0, self.gas - 0.22 * dt)
        target = self.steer_dir if (self.steer_hold > 0 and running and self.spin <= 0) else 0
        rate = 7.0 if target else 5.0
        self.steer += (target - self.steer) * min(1.0, rate * dt)
        sp = self.speed / MAXV
        pseg = trk.seg(self.pz)
        curve = trk.curve[pseg]
        if self.spin > 0:
            self.spin -= dt
            self.x += self.spin_dir * 0.25 * dt * sp
        else:
            self.x += self.steer * STEER_RATE * (0.3 + 0.7 * sp) * dt
        self.x -= CENTRIF * sp * sp * curve * dt
        # throttle and brakes
        if running and self.spin <= 0:
            thr = (1.0 if self.auto_lock <= 0 else 0.0) if self.auto else self.gas
        else:
            thr = 0.0
        braking = self.brake_t > 0 and running
        if braking:
            self.speed -= MAXV * 0.85 * dt
        elif thr > 0:
            self.speed += MAXV * 0.5 * thr * (1.0 - 0.55 * sp) * dt
            self.speed -= MAXV * 0.04 * (1 - thr) * dt
        else:
            self.speed -= MAXV * (0.10 if running else 0.35) * dt
        if self.spin > 0:
            self.speed -= MAXV * 0.5 * dt
        offroad = abs(self.x) > 1.0
        if offroad:
            if self.speed > OFFROAD_V:
                self.speed -= MAXV * 1.1 * dt
                self.speed = max(self.speed, OFFROAD_V * 0.9)
            if self.speed > MAXV * 0.08:
                self.shake = min(1.0, self.shake + dt * 8)
        self.speed = clamp(self.speed, 0.0, MAXV)
        self.x = clamp(self.x, -2.5, 2.5)
        # engine: a short blip when shifting up under hard throttle; rumble on the verge (rate-limited)
        g = sum(1 for b in GEARS if self.speed > b * MAXV)
        if g > self.gear:
            if thr > 0.6 and running and not offroad:
                self.sfx("gear", 0.7, 0.3)
            self.gear = g
        elif g < self.gear and self.speed < GEARS[self.gear - 1] * MAXV * 0.9:
            self.gear = g
        self.verge_cd -= dt
        if offroad and running and self.speed > MAXV * 0.08 and self.verge_cd <= 0:
            self.verge_cd = 0.3
            self.sfx("verge", 0.5 + 0.5 * self.speed / OFFROAD_V, 0.25)
        old_pz = self.pz
        self.pos += self.speed * dt
        moved = self.speed * dt
        self.dist += moved * M_PER_UNIT
        if running:
            self.score += moved * M_PER_UNIT
        self.bgx += curve * moved / SEG * 0.004
        # roadside objects
        if offroad and self.hit_cool <= 0:
            for i in (pseg, pseg + 1):
                for kind, off, seed in trk.spr[min(i, trk.n - 1)]:
                    w = SOLID.get(kind, 0)
                    if w and abs(self.x - off) < w / RW / 2 + CAR_HALF * 0.8:
                        self.crash(0.9, 0.18, -math.copysign(1, off))
                        self.x -= math.copysign(0.18, off)
                        break
        self.traffic(dt, old_pz)
        # rain and lightning
        if self.st.get("rain"):
            self.flash = max(0.0, self.flash - dt)
            self.next_flash -= dt
            if self.next_flash <= 0:
                self.flash = 0.18
                self.next_flash = self.rnd.uniform(5, 12)
        # checkpoints
        if running and self.ci < len(trk.ranges) and self.pz >= trk.ranges[self.ci][2] * SEG:
            self.cp_times.append(self.time_left)
            self.ci += 1
            if self.ci >= len(trk.ranges):
                if self.demo:
                    self.ci = len(trk.ranges) - 1
                else:
                    self.score += int(self.time_left) * 100
                    self.state, self.t_state = "finish", 0.0
                    self.sfx("finish")
            else:
                s = self.trk.ranges[self.ci][0]
                self.reached = max(self.reached, s)
                bonus = allowance(s)
                if not self.demo:
                    self.time_left += bonus
                    self.score += 1000
                self.sfx("checkpoint")
                self.say("CHECKPOINT  +%d s" % bonus, 3.0, (120, 255, 160))
                self.say("STAGE %d  %s" % (s + 1, STAGES[s]["name"]), 3.0, (255, 220, 120))

    def crash(self, spin, keep, d):
        self.spin = spin
        self.spin_dir = d
        self.speed = min(self.speed, MAXV * keep)
        self.hit_cool = spin + 0.5
        self.shake = 1.0
        self.crashes += 1
        self.sfx("crash", 0.9, 0.3)

    # ---- traffic ---------------------------------------------------------------------------------------
    def spawn(self, z, onc):
        st = STAGES[self.trk.stage[self.trk.seg(z)]]
        lanes = onc_lanes(st) if onc else same_lanes(st)
        if not lanes or z >= (self.trk.n - 5) * SEG:
            return False
        gap = traffic_gap(st) if not onc else 9 * SEG
        for c in self.cars:
            if c.onc == onc and abs(c.z - z) < gap:
                return False
        x = self.rnd.choice(lanes)
        v = (-1 if onc else 1) * MAXV * self.rnd.uniform(0.32, 0.6)
        self.cars.append(Car(z, x, v, self.rnd.choice(TRAFFIC_COLOURS), onc))
        return True

    def fill_traffic(self, initial=False):
        st = self.st
        pz = self.pz
        want_same, want_onc = st["traffic"], (st["traffic"] // 2 if st["oncoming"] else 0)
        n_same = sum(1 for c in self.cars if not c.onc)
        n_onc = len(self.cars) - n_same
        tries = 0
        while n_same < want_same and tries < 30:
            tries += 1
            z = pz + (self.rnd.uniform(20, DRAW + 60) if initial else self.rnd.uniform(DRAW + 5, DRAW + 70)) * SEG
            n_same += self.spawn(z, False)
        tries = 0
        while n_onc < want_onc and tries < 30:
            tries += 1
            z = pz + (self.rnd.uniform(40, DRAW + 60) if initial else self.rnd.uniform(DRAW + 5, DRAW + 90)) * SEG
            n_onc += self.spawn(z, True)

    def traffic(self, dt, old_pz=None):
        pz = self.pz
        cars = self.cars
        same = sorted((c for c in cars if not c.onc), key=lambda c: c.z)
        for k, c in enumerate(same):                 # keep a gap: never two cars side by side
            v = c.v0
            if k + 1 < len(same):
                a = same[k + 1]
                gap = traffic_gap(STAGES[self.trk.stage[self.trk.seg(c.z)]])
                if a.z - c.z < gap:
                    v = min(v, a.v * (0.9 if a.z - c.z < gap * 0.8 else 1.0))
            if 0 < pz - c.z < 4 * SEG and abs(self.x - c.x) < 0.5:
                v = min(v, self.speed)               # do not run into the player from behind
            c.v += (v - c.v) * min(1.0, dt * 2)
        for c in cars:
            c.prev = c.z
            c.z += c.v * dt
            cst = STAGES[self.trk.stage[self.trk.seg(c.z)]]       # a new stage may have other lanes
            ls = onc_lanes(cst) if c.onc else same_lanes(cst)
            if ls:
                lx = min(ls, key=lambda v: abs(v - c.x))
                if lx != c.x:
                    c.x = lx if abs(lx - c.x) < 0.6 * dt else c.x + math.copysign(0.6 * dt, lx - c.x)
        if old_pz is not None and self.state == "run":
            for c in cars:
                dz, pdz = c.z - pz, c.prev - old_pz
                if not c.onc and c.ahead and dz < -200:
                    c.ahead = False
                    self.overtakes += 1
                    self.score += 50
                    self.sfx("whoosh", 0.6, 0.5)
                if self.hit_cool > 0 or abs(c.x - self.x) > CAR_HALF * 1.8:
                    continue
                if abs(dz) < 260 or (pdz > 0) != (dz > 0):
                    if c.onc:
                        self.crash(1.1, 0.08, 1 if self.x > c.x else -1)
                        self.x += 0.35 if self.x >= c.x else -0.35
                        self.say("CRASH!", 1.2, (255, 110, 90))
                    elif self.speed > c.v:
                        rel = (self.speed - c.v) / MAXV
                        self.speed = c.v * 0.8
                        self.pos = c.z - 300 - PLAYER_Z
                        self.hit_cool = 0.5
                        self.shake = 0.8
                        if rel <= 0.4:
                            self.sfx("bump", 0.8, 0.3)
                        if rel > 0.4:
                            self.crash(0.6, c.v * 0.8 / MAXV, 1 if self.x > c.x else -1)
        self.cars = [c for c in cars if pz - 25 * SEG < c.z < pz + (DRAW + 160) * SEG]
        self.fill_traffic()


# =============================================================================================
# Drawing
# =============================================================================================
DIGITS = {
    "0": ["###", "#.#", "#.#", "#.#", "###"], "1": [".#.", "##.", ".#.", ".#.", "###"],
    "2": ["###", "..#", "###", "#..", "###"], "3": ["###", "..#", ".##", "..#", "###"],
    "4": ["#.#", "#.#", "###", "..#", "..#"], "5": ["###", "#..", "###", "..#", "###"],
    "6": ["###", "#..", "###", "#.#", "###"], "7": ["###", "..#", ".#.", ".#.", ".#."],
    "8": ["###", "#.#", "###", "#.#", "###"], "9": ["###", "#.#", "###", "..#", "###"],
}


def draw_big(cv, text, x, y, k, col, shadow=(0, 0, 0)):
    """Chunky digits (3x5) or letters (5x5 from arcadekit), each font pixel k x k, with a drop shadow."""
    gx = x
    glyphs = []
    for ch in text:
        g = DIGITS.get(ch) or FONT.get(ch.upper(), FONT[" "])
        glyphs.append((gx, g))
        gx += (len(g[0]) + 1) * k
    for dx, c in ((1, shadow), (0, col)):
        for ox, g in glyphs:
            for gy, row in enumerate(g):
                for gxx, bit in enumerate(row):
                    if bit == "#":
                        cv.rect(ox + gxx * k + dx, y + gy * k + dx, k, k, c)


def big_width(text, k):
    return sum((len((DIGITS.get(ch) or FONT.get(ch.upper(), FONT[" "]))[0]) + 1) * k for ch in text) - k


def fill(px, W, x0, y0, x1, y1, c, clip):
    x0, x1, y0, y1 = int(x0), int(x1), int(y0), int(y1)
    if x0 < 0:
        x0 = 0
    if x1 > W:
        x1 = W
    if y0 < 0:
        y0 = 0
    if y1 > clip:
        y1 = clip
    if x1 <= x0 or y1 <= y0:
        return
    run = [c] * (x1 - x0)
    for y in range(y0, y1):
        px[y][x0:x1] = run


def glow(px, W, cx, cy, r, c, a, clip):
    """Additive soft light around (cx, cy)."""
    if r < 1.0:
        return
    r = min(r, 16.0)
    r2 = r * r
    x0, x1 = max(0, int(cx - r)), min(W, int(cx + r) + 1)
    y0, y1 = max(0, int(cy - r)), min(int(clip), int(cy + r) + 1)
    cr, cg, cb = c
    for y in range(y0, y1):
        row = px[y]
        dy2 = (y + 0.5 - cy) ** 2
        for x in range(x0, x1):
            d2 = (x + 0.5 - cx) ** 2 + dy2
            if d2 < r2:
                t = 1 - d2 / r2
                t = a * t * t
                p = row[x]
                row[x] = (min(255, int(p[0] + cr * t)), min(255, int(p[1] + cg * t)), min(255, int(p[2] + cb * t)))


# ---- car pixel art (rear views; '.' is see-through) ----
PLAYER_ART = [
    "........DDDDDDDDDDDD........",
    "......DDWWWWWWWWWWWWDD......",
    ".....DWWwwWWWWWWWWWWWWD.....",
    "....DWWWwwWWWWWWWWWWWWWD....",
    "...DDDDDDDDDDDDDDDDDDDDDD...",
    "..DHHHHHHHHHHHHHHHHHHHHHHD..",
    ".DBBBBBBBBBBBBBBBBBBBBBBBBD.",
    "DRRRRRRBBBBBBBBBBBBBBRRRRRRD",
    "DRRRRRRBBBBBBBBBBBBBBRRRRRRD",
    "DBBBBBBBBBBBPPPPPBBBBBBBBBBD",
    "DDDDDDDDDDDDDDDDDDDDDDDDDDDD",
    "TTTTTDXXXEEXXXXXXEEXXXDTTTTT",
    "TTTTT..................TTTTT",
]
SIDE_ART = [
    "..........DDDDDDDD..........",
    "........DDWWWWWWWWDD........",
    "......DDWWWWWWwwWWWWDD......",
    "..DDDDDDDDDDDDDDDDDDDDDDDD..",
    ".DHHHHHHHHHHHHHHHHHHHHHHHHD.",
    "RBBBBBBBBBBBBBBBBBBBBBBBBBBL",
    "DBBBBBBBBBBBBBBBBBBBBBBBBBBD",
    "DDDDTTTTDDDDDDDDDDDDTTTTDDDD",
    "....TTTT............TTTT....",
]
TRAFFIC_ART = [
    "...DDDDDDDDDD...",
    "..DWWWWWWWWWWD..",
    ".DWwWWWWWWWWWWD.",
    "DDDDDDDDDDDDDDDD",
    "DBBBBBBBBBBBBBBD",
    "RRRBBBBBBBBBBRRR",
    "DBBBBBPPPPBBBBBD",
    "DDDDDDDDDDDDDDDD",
    "TTT..........TTT",
]
ONCOMING_ART = [
    "...DDDDDDDDDD...",
    "..DWWWWWWWWWWD..",
    ".DWWWWWWWWWwWWD.",
    "DDDDDDDDDDDDDDDD",
    "DBBBBBBBBBBBBBBD",
    "LLLBBDDDDDDBBLLL",
    "DBBBBDDDDDDBBBBD",
    "DDDDDDDDDDDDDDDD",
    "TTT..........TTT",
]


def car_colours(body, k, f, haze, brake=False, lights=1.0):
    def L(c, kk=k):
        return mix(shade(c, kk), haze, f)
    return {"B": L(body), "D": L(shade(body, 0.4)), "H": L(mix(body, (255, 255, 255), 0.35), k * 1.15),
            "W": L((26, 34, 52), max(k, 0.8)), "w": L((110, 130, 160), max(k, 0.8)),
            "R": mix((255, 50, 50) if brake else (200, 18, 28), haze, f * 0.4),
            "L": mix((255, 252, 235), haze, f * 0.15), "P": L((210, 210, 190)), "T": (12, 12, 14),
            "X": (24, 24, 28), "E": L((90, 90, 96))}


def draw_art(px, W, art, cols, x0, y0, w, h, clip, flip=False, lean=0.0):
    th, tw = len(art), len(art[0])
    w, h = int(w), int(h)
    if w < 1 or h < 1:
        return
    x0, y0 = int(x0), int(y0)
    for ty in range(h):
        y = y0 + ty
        if y < 0 or y >= clip:
            continue
        src = art[ty * th // h]
        out = px[y]
        sh = int(lean * (1 - ty / h) * 2.5)
        for tx in range(w):
            x = x0 + tx + sh
            if 0 <= x < W:
                ch = src[(w - 1 - tx) * tw // w if flip else tx * tw // w]
                if ch != ".":
                    out[x] = cols[ch]


# ---- backgrounds: a slow sky layer and a skyline layer, cached per stage and screen size ----
_BG = {}


def background(si, W, H, hz):
    key = (si, W, H, hz)
    if key in _BG:
        return _BG[key]
    if len(_BG) > 24:
        _BG.clear()
    st = STAGES[si]
    rnd = random.Random(st["seed"] * 31 + W)
    BW = W * 2
    top, hor = st["sky"]
    haze, far = st["haze"], st["far"]
    scene = st["scene"]
    sky = []
    for y in range(H):
        if y < hz:
            c = mix(top, hor, (y / max(1, hz)) ** 1.7)
        elif scene == "coast":
            c = mix(hor, (6, 16, 36), min(1.0, (y - hz) / max(1, (H - hz) * 0.5)))
        else:
            c = mix(haze, far, min(1.0, (y - hz) / max(1, (H - hz) * 0.3)))
        sky.append([c] * BW)
    if scene == "storm":                                     # heavy cloud banks
        for y in range(hz):
            row = sky[y]
            for x in range(BW):
                a = x / BW * math.tau
                n = (math.sin(a * 3 + y * 0.31) + math.sin(a * 7 - y * 0.17 + 1.3) * 0.6 +
                     math.sin(a * 13 + y * 0.6 + 2.1) * 0.3)
                t = clamp(n * 0.35 + 0.3, 0, 1) * (1 - y / max(1, hz) * 0.5)
                row[x] = mix(row[x], (58, 62, 78), t * 0.7)
    for _ in range(int(BW * hz / 30 * st["stars"])):
        x, y = rnd.randrange(BW), rnd.randrange(max(1, int(hz * 0.85)))
        sky[y][x] = mix(sky[y][x], (230, 230, 255), 0.25 + 0.6 * rnd.random() ** 2)
    if st["moon"] > 0:
        R = max(2.6, H * st["moon"])
        mx, my = BW * 0.3, max(R + 2, hz * 0.36)
        G = R * 3.2
        for y in range(max(0, int(my - G)), min(hz, int(my + G) + 1)):
            for x in range(int(mx - G), int(mx + G) + 1):
                xx = x % BW
                d = math.hypot(x + 0.5 - mx, y + 0.5 - my)
                p = sky[y][xx]
                if d < R:
                    crater = (math.sin(x * 1.7 / R * 3) + math.sin(y * 2.3 / R * 3 + 1)) > 1.1
                    lim = 1 - (d / R) ** 4 * 0.25
                    base = (236, 232, 214) if not crater else (200, 196, 182)
                    sky[y][xx] = shade(base, lim)
                elif d < G:
                    t = (1 - (d - R) / (G - R)) ** 2 * 0.35
                    sky[y][xx] = mix(p, (180, 190, 220), t)
        if scene == "coast":                                  # moonlight on the sea
            for y in range(hz, H):
                spread = 1 + (y - hz) * 0.6
                for x in range(int(mx - spread), int(mx + spread) + 1):
                    if rnd.random() < 0.4:
                        xx = x % BW
                        sky[y][xx] = mix(sky[y][xx], (220, 220, 200), rnd.uniform(0.3, 0.8))
    sky = [row + row[:W] for row in sky]
    # skyline layer
    BW2 = W * 3
    band = max(3, int(hz * 0.62))
    sl = [[None] * BW2 for _ in range(band)]          # sl[j] is screen row hz - band + j

    def col(x, y0, c):                                 # paint column x from row y0 (screen) down to the horizon
        for y in range(max(hz - band, int(y0)), hz):
            sl[y - (hz - band)][x % BW2] = c
    neon = st["neon"]
    if scene in ("city", "storm"):
        x = 0
        while x < BW2:
            w = rnd.randint(3, 9)
            h = rnd.uniform(0.25, 1.0) ** 1.3 * band * (0.9 if scene == "city" else 0.6)
            bc = mix((14, 10, 28) if scene == "city" else (18, 20, 28), haze, rnd.uniform(0.0, 0.35))
            for xx in range(x, x + w):
                col(xx, hz - h, bc)
            for yy in range(int(hz - h) + 1, hz - 1, 2):     # lit windows
                for xx in range(x + 1, x + w - 1, 2):
                    if rnd.random() < (0.3 if scene == "city" else 0.15):
                        j = yy - (hz - band)
                        if 0 <= j < band:
                            sl[j][xx % BW2] = rnd.choice(((255, 214, 140), (255, 230, 180), neon[1], neon[0]))
            if rnd.random() < 0.25 and h > 4:                # neon sign on the roof
                j = int(hz - h) - (hz - band)
                if 0 <= j < band:
                    nc = rnd.choice(neon)
                    for xx in range(x, x + w):
                        sl[j][xx % BW2] = nc
            x += w + rnd.randint(0, 2)
    elif scene == "coast":
        for x in range(BW2):                                   # a far headland with a few lights
            a = x / BW2 * math.tau
            h = band * (0.18 + 0.12 * math.sin(a * 2 + 0.5) + 0.08 * math.sin(a * 5))
            if math.sin(a * 2 + 0.5) > -0.2:
                col(x, hz - h, (8, 14, 30))
                if rnd.random() < 0.05:
                    j = hz - 1 - rnd.randint(0, max(0, int(h) - 1)) - (hz - band)
                    if 0 <= j < band:
                        sl[j][x] = (255, 210, 140)
    elif scene == "forest":
        for x in range(BW2):
            a = x / BW2 * math.tau
            hill = band * (0.35 + 0.15 * math.sin(a * 3) + 0.1 * math.sin(a * 7 + 1))
            col(x, hz - hill, (16, 30, 32))
        x = 0
        while x < BW2:
            h = rnd.uniform(0.25, 0.55) * band
            w = rnd.randint(3, 6)
            for k in range(w):
                d = abs(k - (w - 1) / 2) / (w / 2)
                col(x + k, hz - h * (1 - d * 0.9), (8, 16, 14))
            x += rnd.randint(1, 4)
    elif scene == "desert":
        x = 0
        while x < BW2:                                       # mesas
            w = rnd.randint(8, 26)
            h = rnd.uniform(0.25, 0.7) * band
            for k in range(w):
                edge = min(k, w - 1 - k)
                hh = h if edge >= 2 else h * (0.55 + edge * 0.2)
                col(x + k, hz - hh, (40, 22, 40))
                j = int(hz - hh) - (hz - band)
                if 0 <= j < band:
                    sl[j][(x + k) % BW2] = (110, 70, 80)
            x += w + rnd.randint(4, 30)
    elif scene == "mountain":
        peaks = [(rnd.uniform(0, BW2), rnd.uniform(0.45, 1.0) * band, rnd.uniform(0.7, 1.4))
                 for _ in range(max(4, BW2 // 22))]
        for x in range(BW2):
            h = 0
            for px_, ph, sl_ in peaks:
                d = min(abs(x - px_), BW2 - abs(x - px_))
                h = max(h, ph - d * sl_ + math.sin(d * 1.3 + ph) * 0.8)
            for px_, ph, sl_ in peaks:                       # a lower, nearer range in front
                d = min(abs(x - px_ * 0.7 - BW2 * 0.15) % BW2, BW2 - abs(x - px_ * 0.7 - BW2 * 0.15) % BW2)
                h2 = ph * 0.45 - d * sl_ * 0.8
                if h2 > band * 0.12:
                    h = max(h, -h2)                          # marker: negative = near range
            hh = abs(h)
            if hh > 0:
                near = h < 0
                for y in range(max(hz - band, int(hz - hh)), hz):
                    up = hz - y
                    snow = not near and up > hh - max(1.5, hh * 0.22) and hh > band * 0.5
                    c = (16, 20, 38) if near else (32, 38, 66)
                    if snow:
                        c = (120, 130, 162)
                    sl[y - (hz - band)][x] = c
    sl = [row + row[:W] for row in sl]
    _BG[key] = (sky, BW, sl, BW2, band)
    return _BG[key]


# ---- roadside sprites ----
def draw_sprite(px, W, kind, off, seed, sx, sy, s, clip, k, f, haze, st, near, t):
    """One roadside object standing at screen (sx, sy); s = pixels per world unit."""
    def L(c, kk=None):
        return mix(shade(c, k if kk is None else kk), haze, f)
    if kind == "post":
        h = 340 * s
        if h < 1.0:
            return
        w = max(1.0, 60 * s)
        fill(px, W, sx - w / 2, sy - h, sx + w / 2 + (1 if w < 1.5 else 0), sy, L((200, 200, 200)), clip)
        refl = (255, 170, 40) if off > 0 else (240, 240, 255)
        bright = mix(refl, haze, f * 0.5) if near < BEAM_N else L(refl, 0.5)
        fill(px, W, sx - w / 2, sy - h, sx + w / 2 + (1 if w < 1.5 else 0), sy - h + max(1, h * 0.25), bright, clip)
        return
    if kind == "lamp":
        h = 2600 * s
        if h < 2:
            if 0 <= int(sy - h) < clip and 0 <= int(sx) < W:
                px[int(sy - h)][int(sx)] = mix((255, 220, 150), haze, f * 0.5)
            return
        w = max(1.0, 70 * s)
        pole = L((90, 92, 100), max(k, 0.5))
        fill(px, W, sx - w / 2, sy - h, sx + w / 2 + 1, sy, pole, clip)
        arm = -math.copysign(1, off) * 500 * s
        ax0, ax1 = (sx, sx + arm) if arm > 0 else (sx + arm, sx)
        fill(px, W, ax0, sy - h, ax1 + 1, sy - h + max(1, 40 * s), pole, clip)
        hx = sx + arm
        lampc = mix((255, 226, 160), haze, f * 0.4)
        fill(px, W, hx - max(1, 90 * s), sy - h, hx + max(1, 90 * s) + 1, sy - h + max(1, 60 * s), lampc, clip)
        if near < 90:
            glow(px, W, hx, sy - h + 1, max(1.5, 420 * s), (120, 100, 60), 0.9 * (1 - f), clip)
        return
    if kind == "palm":
        h = 3000 * s
        if h < 2:
            return
        tw = max(1.0, 110 * s)
        trunk = L((70, 56, 44), k)
        lean = math.copysign(1, off) * 350 * s
        n = max(2, int(h / 2))
        for j in range(n):
            p = j / n
            yy = sy - h * p
            xx = sx + lean * p * p
            fill(px, W, xx - tw / 2, yy - h / n - 1, xx + tw / 2 + 1, yy, trunk, clip)
        topx, topy = sx + lean, sy - h
        leaf = L((24, 60, 40), k * 1.1)
        R = 1100 * s
        for a in (-2.6, -2.0, -1.2, -0.5, 0.0, 0.5, 1.2, 2.0, 2.6):
            for j in range(1, max(3, int(R))):
                p = j / max(3, int(R))
                xx = topx + math.sin(a) * R * p
                yy = topy - math.cos(a) * R * 0.45 * p + (R * 0.5) * p * p
                if 0 <= int(yy) < clip and 0 <= int(xx) < W:
                    px[int(yy)][int(xx)] = leaf
                    if R > 10 and int(yy) + 1 < clip:
                        px[int(yy) + 1][int(xx)] = leaf
        return
    if kind == "pine":
        h = 2800 * (0.75 + (seed % 7) / 14) * s
        if h < 2:
            return
        w = 1150 * s * (0.85 + (seed % 5) / 16)
        dark = L((18, 46, 30), k)
        lite = L((34, 74, 44), k)
        fill(px, W, sx - max(1, 90 * s), sy - h * 0.25, sx + max(1, 90 * s) + 1, sy, L((60, 42, 30), k), clip)
        rows = int(h * 0.85)
        top = sy - h
        for j in range(rows):
            p = j / max(1, rows)
            tier = (p * 3) % 1.0
            half = w / 2 * (0.25 + 0.75 * p) * (0.55 + 0.45 * tier)
            yy = int(top + j)
            if 0 <= yy < clip:
                x0, x1 = max(0, int(sx - half)), min(W, int(sx + half) + 1)
                if x1 > x0:
                    px[yy][x0:x1] = [dark] * (x1 - x0)
                    m = min(W, int(sx - half * 0.3) + 1)
                    if m > x0 and half > 3:
                        px[yy][x0:m] = [lite] * (m - x0)
        return
    if kind == "cactus":
        h = 1500 * (0.8 + (seed % 5) / 10) * s
        if h < 2:
            return
        w = max(1.0, 220 * s)
        c = L((40, 92, 54), k)
        fill(px, W, sx - w / 2, sy - h, sx + w / 2 + 1, sy, c, clip)
        aw = max(1.0, 160 * s)
        fill(px, W, sx - w / 2 - 380 * s, sy - h * 0.55, sx - w / 2, sy - h * 0.55 + aw, c, clip)
        fill(px, W, sx - w / 2 - 380 * s, sy - h * 0.85, sx - w / 2 - 380 * s + aw, sy - h * 0.55 + aw, c, clip)
        fill(px, W, sx + w / 2, sy - h * 0.4, sx + w / 2 + 340 * s, sy - h * 0.4 + aw, c, clip)
        fill(px, W, sx + w / 2 + 340 * s - aw, sy - h * 0.7, sx + w / 2 + 340 * s, sy - h * 0.4 + aw, c, clip)
        return
    if kind == "rock":
        h = 620 * (0.7 + (seed % 5) / 8) * s
        if h < 1:
            return
        w = 1000 * s * (0.7 + (seed % 3) / 4)
        rows = max(1, int(h))
        dark, lite = L((70, 64, 66), k), L((110, 104, 104), k)
        for j in range(rows):
            p = (j + 0.5) / rows
            half = w / 2 * math.sqrt(max(0.0, 1 - (1 - p) ** 2 * 0.9))
            yy = int(sy - h + j)
            if 0 <= yy < clip:
                x0, x1 = max(0, int(sx - half)), min(W, int(sx + half) + 1)
                if x1 > x0:
                    px[yy][x0:x1] = [dark] * (x1 - x0)
                    m = min(W, int(sx - half * 0.2))
                    if m > x0 and p < 0.6:
                        px[yy][x0:m] = [lite] * (m - x0)
        return
    if kind == "chev":
        h, w = 900 * s, 520 * s
        if h < 2:
            return
        fill(px, W, sx - max(1, 40 * s), sy - h * 0.55, sx + max(1, 40 * s) + 1, sy, L((80, 80, 80)), clip)
        lit_k = max(k, 1.0 if near < BEAM_N else 0.5)
        yel = mix(shade((250, 200, 40), lit_k), haze, f)
        blk = (14, 14, 14)
        fill(px, W, sx - w / 2, sy - h, sx + w / 2 + 1, sy - h * 0.55, yel, clip)
        d = 1 if off < 0 else -1          # arrows point into the curve
        rows = max(1, int(h * 0.45))
        for j in range(rows):
            yy = int(sy - h + j)
            if 0 <= yy < clip:
                p = abs(j - rows / 2) / (rows / 2)
                for base in (-0.2, 0.25):
                    xx = int(sx + d * (base - p * 0.25) * w)
                    if 0 <= xx < W:
                        px[yy][xx] = blk
        return
    if kind == "bill":
        h, w = 1700 * s, 1900 * s
        if h < 2:
            return
        nc = st["neon"][seed % len(st["neon"])]
        nc2 = st["neon"][(seed // 3 + 1) % len(st["neon"])]
        pole = L((70, 70, 80), max(k, 0.4))
        fill(px, W, sx - w * 0.3, sy - h * 0.5, sx - w * 0.3 + max(1, 60 * s), sy, pole, clip)
        fill(px, W, sx + w * 0.3, sy - h * 0.5, sx + w * 0.3 + max(1, 60 * s), sy, pole, clip)
        board = mix((20, 16, 30), haze, f)
        fill(px, W, sx - w / 2, sy - h, sx + w / 2 + 1, sy - h * 0.48, board, clip)
        bc = mix(nc, haze, f * 0.5)
        b = max(1, int(60 * s))
        fill(px, W, sx - w / 2, sy - h, sx + w / 2 + 1, sy - h + b, bc, clip)
        fill(px, W, sx - w / 2, sy - h * 0.48 - b, sx + w / 2 + 1, sy - h * 0.48, bc, clip)
        fill(px, W, sx - w / 2, sy - h, sx - w / 2 + b, sy - h * 0.48, bc, clip)
        fill(px, W, sx + w / 2 + 1 - b, sy - h, sx + w / 2 + 1, sy - h * 0.48, bc, clip)
        tc = mix(nc2, haze, f * 0.5)
        hh = h * 0.52
        for j, frac in enumerate((0.3, 0.55)):
            ln = w * (0.7 if j == 0 else 0.45)
            fill(px, W, sx - ln / 2, sy - h + hh * frac, sx + ln / 2, sy - h + hh * frac + max(1, 90 * s), tc, clip)
        if near < 80 and w > 6:
            glow(px, W, sx, sy - h * 0.74, w * 0.55, shade(nc, 0.35), 0.6 * (1 - f), clip)
        return
    if kind == "bldg":
        w = 2600 * s * (0.8 + (seed % 5) / 10)
        h = (4000 + (seed % 11) * 900) * s
        if h < 2:
            return
        bc = L((34, 30, 50) if st["scene"] == "city" else (40, 44, 54), max(k, 0.55))
        fill(px, W, sx - w / 2, sy - h, sx + w / 2 + 1, sy, bc, clip)
        cell = 300 * s
        x0 = sx - w / 2
        if cell >= 2.0:
            nx, ny = int(w / cell), int(h / cell)
            for jy in range(1, ny - 1):
                for jx in range(1, nx - 1):
                    hsh = (seed * 31 + jx * 17 + jy * 101) % 97
                    if hsh < 34:
                        wc = st["neon"][hsh % 4] if hsh < 4 else ((255, 214, 140) if hsh % 3 else (255, 236, 200))
                        wc = mix(wc, haze, f * 0.6)
                        fill(px, W, x0 + jx * cell, sy - h + jy * cell, x0 + jx * cell + max(1, cell * 0.55),
                             sy - h + jy * cell + max(1, cell * 0.5), wc, clip)
        else:
            nx, ny = max(1, int(w / 2)), max(1, int(h / 2))
            for jy in range(ny):
                for jx in range(nx):
                    hsh = (seed * 31 + jx * 17 + jy * 101) % 97
                    if hsh < 22:
                        yy, xx = int(sy - h + 1 + jy * 2), int(x0 + 1 + jx * 2)
                        if 0 <= yy < clip and 0 <= xx < W:
                            px[yy][xx] = mix((255, 214, 140), haze, f * 0.6)
        if seed % 3 == 0 and w > 4:                            # neon band on the roof
            fill(px, W, x0, sy - h, sx + w / 2 + 1, sy - h + max(1, 120 * s), mix(st["neon"][seed % 4], haze, f * 0.5), clip)
        return


def draw_gate(cv, px, W, sxl, sxr, sy, s, clip, f, haze, finish, t):
    """The checkpoint / finish arch over the road."""
    h = 2300 * s
    if h < 2:
        return
    pw = max(1.0, 160 * s)
    pc = mix((70, 70, 84), haze, f)
    fill(px, W, sxl - pw, sy - h, sxl, sy, pc, clip)
    fill(px, W, sxr, sy - h, sxr + pw, sy, pc, clip)
    bh = max(2.0, 420 * s)
    y0 = sy - h
    if finish:
        cell = max(1.0, 140 * s)
        nx = int((sxr - sxl + 2 * pw) / cell) + 1
        for j in range(int(bh / cell) + 1):
            for i in range(nx):
                c = (240, 240, 240) if (i + j) % 2 == 0 else (20, 20, 20)
                fill(px, W, sxl - pw + i * cell, y0 + j * cell, sxl - pw + (i + 1) * cell, min(y0 + bh, y0 + (j + 1) * cell),
                     mix(c, haze, f), clip)
    else:
        a = 0.5 + 0.5 * math.sin(t * 8)
        fill(px, W, sxl - pw, y0, sxr + pw, y0 + bh, mix((40, 10, 50), haze, f), clip)
        edge = mix(mix((255, 60, 200), (60, 230, 255), a), haze, f * 0.5)
        e = max(1.0, 60 * s)
        fill(px, W, sxl - pw, y0, sxr + pw, y0 + e, edge, clip)
        fill(px, W, sxl - pw, y0 + bh - e, sxr + pw, y0 + bh, edge, clip)
    label = "F I N I S H" if finish else "CHECKPOINT"
    row = int((y0 + bh / 2) // 2)
    if sxr - sxl > len(label) + 4 and y0 + bh < clip and 0 <= row < cv.rows:
        cv.center(row, label, (255, 255, 255) if not finish else (240, 40, 40), None, int(sxl), int(sxr - sxl))


def palette(trk, si, alt, k, f):
    key = (si, alt, int(k * 20), int(f * 24))
    p = trk.pal_cache.get(key)
    if p is None:
        st = STAGES[si]
        k, f = int(k * 20) / 20.0, int(f * 24) / 24.0
        haze = st["haze"]

        def L(c, kk=k):
            return mix(shade(c, kk), haze, f)
        g = st.get("ground2", st["ground"]) if alt else st["ground"]
        if st["scene"] != "coast":
            g = (st["ground"][alt], st["ground"][alt])
        p = (L(g[0]), L(g[1]), L(st["rumble"][alt], min(1.6, k * 1.25)), L(st["road"][alt]),
             L(st["lane"], min(1.6, k * 1.3)), L((235, 190, 50), min(1.6, k * 1.3)))
        trk.pal_cache[key] = p
    return p


def render(r, cols, rows, hud=True):
    cv = Canvas(cols, rows)
    W, H = cv.W, cv.H
    px = cv.px
    trk = r.trk
    view_si = trk.stage[trk.seg(r.pz)]
    st = STAGES[view_si]
    car_bot = H - 3 if hud else H - 1
    hz0 = int(H * 0.40)
    shake = int(round(r.rnd.uniform(-1, 1) * r.shake)) if r.shake > 0.05 else 0
    hz = hz0 + shake
    SY = car_bot - hz0
    SX = SY * 1.0
    W2 = W / 2
    pos = r.pos
    base = trk.seg(pos)
    bp = (pos - base * SEG) / SEG
    pseg = trk.seg(r.pz)
    pp = (r.pz - pseg * SEG) / SEG
    ys = trk.y
    py = ys[pseg] + (ys[pseg + 1] - ys[pseg]) * pp
    camy = CAM_H + py
    camx = r.x * RW
    curve = trk.curve
    xoff = 0.0
    dx = -curve[base] * bp
    maxy = H
    proj = []
    ntot = trk.n
    beam_c = r.x
    for n in range(DRAW):
        i = base + n
        if i + 1 >= ntot:
            break
        z1 = i * SEG - pos
        z2 = z1 + SEG
        if z1 < 1:
            z1 = 1.0
        s1, s2 = DEPTH / z1, DEPTH / z2
        x1 = W2 + s1 * (xoff - camx) * SX
        x2 = W2 + s2 * (xoff + dx - camx) * SX
        y1 = hz + s1 * (camy - ys[i]) * SY
        y2 = hz + s2 * (camy - ys[i + 1]) * SY
        w1, w2 = s1 * RW * SX, s2 * RW * SX
        xoff += dx
        dx += curve[i]
        proj.append((i, n, x1, y1, s1, x2, y2, s2, maxy))
        if n == 0 or y2 >= maxy or y1 <= y2:
            continue
        si = trk.stage[i]
        sst = STAGES[si]
        alt = (i // 3) & 1
        fogp = sst.get("fogpow", 0.9)
        f = (n / DRAW) ** fogp * sst["fog"]
        k = sst["amb"] + trk.light[i] * 0.9
        if n < 14:
            k += 0.25 * (1 - n / 14)
        P0 = palette(trk, si, alt, k, f)
        beam = n < BEAM_N
        if beam:
            fb = (1 - n / BEAM_N) ** 1.1
            P1 = palette(trk, si, alt, k + 0.38 * fb, f)
            P2 = palette(trk, si, alt, k + 0.8 * fb, f)
            bo = 0.62 + n * 0.014
            bi = 0.34 + n * 0.008
        nl = sst["lanes"]
        onc = sst["oncoming"]
        dash = ((i // 4) & 1) == 0
        top = int(y2 + 0.999)
        if top < 0:
            top = 0
        bot = maxy - 1
        if y1 < bot:
            bot = int(y1)
        inv = 1.0 / (y1 - y2)
        for yy in range(top, bot + 1):
            t = (yy + 0.5 - y2) * inv
            if t > 1:
                t = 1.0
            cx = x2 + (x1 - x2) * t
            w = w2 + (w1 - w2) * t
            row = road_row(W, cx, w, P0, nl, onc, dash, alt)
            if beam:
                bc = cx + beam_c * w
                a, b = int(bc - bo * w), int(bc + bo * w) + 1
                if a < 0:
                    a = 0
                if b > W:
                    b = W
                if b > a:
                    row[a:b] = road_row(W, cx, w, P1, nl, onc, dash, alt)[a:b]
                    a, b = int(bc - bi * w), int(bc + bi * w) + 1
                    if a < 0:
                        a = 0
                    if b > W:
                        b = W
                    if b > a:
                        row[a:b] = road_row(W, cx, w, P2, nl, onc, dash, alt)[a:b]
            px[yy] = row
        if top < maxy:
            maxy = top
    # background above the road
    sky, BW, sl, BW2, band = background(view_si, W, H, hz0)
    o1 = int(r.bgx * W * 0.3) % BW
    o2 = int(r.bgx * W) % BW2
    sy0 = hz0 - band
    lim = min(maxy, H)
    for y in range(lim):
        yb = y - shake
        if yb < 0:
            yb = 0
        elif yb >= H:
            yb = H - 1
        row = sky[yb][o1:o1 + W]
        j = yb - sy0
        if 0 <= j < band:
            srow = sl[j][o2:o2 + W]
            row = [a if a is not None else b for a, b in zip(srow, row)]
        px[y] = row
    if r.flash > 0:
        a = min(1.0, r.flash / 0.18) * 0.55
        for y in range(min(lim, hz)):
            px[y] = [mix(c, (200, 205, 230), a) for c in px[y]]
    # sprites and traffic, back to front
    by_seg = {}
    for c in r.cars:
        by_seg.setdefault(int(c.z // SEG), []).append(c)
    haze = st["haze"]
    for (i, n, x1, y1, s1, x2, y2, s2, clip) in reversed(proj):
        if n == 0:
            continue
        si = trk.stage[i]
        sst = STAGES[si]
        f = (n / DRAW) ** sst.get("fogpow", 0.9) * sst["fog"]
        hz_s = sst["haze"]
        kb = sst["amb"] * 0.8 + trk.light[i] * 0.8
        fb = (1 - n / BEAM_N) if n < BEAM_N else 0.0
        if i in trk.gates:
            sxl = x1 - s1 * RW * SX * 1.12
            sxr = x1 + s1 * RW * SX * 1.12
            draw_gate(cv, px, W, sxl, sxr, y1, s1 * SX, clip, f, hz_s, trk.gates[i] == "finish", r.t)
        for kind, off, seed in trk.spr[i]:
            sxp = x1 + s1 * off * RW * SX
            kk = kb + (0.6 * fb if abs(off - r.x) < 1.4 else 0.25 * fb)
            draw_sprite(px, W, kind, off, seed, sxp, y1, s1 * SX, clip, kk, f, hz_s, sst, n, r.t)
        for c in by_seg.get(i, ()):
            p = (c.z - i * SEG) / SEG
            sc = s1 + (s2 - s1) * p
            cxs = x1 + (x2 - x1) * p + sc * c.x * RW * SX
            cys = y1 + (y2 - y1) * p
            draw_car(px, W, c, cxs, cys, sc * SX, clip, kb + fb * (0.7 if abs(c.x - r.x) < 0.6 else 0.3), f, hz_s, sst)
    # the player's car
    draw_player(cv, r, W, H, car_bot, SX, st)
    if st.get("rain"):
        rain(px, W, H, r)
    if hud:
        draw_hud(cv, r, cols, rows)
    return cv


def road_row(W, cx, w, P, nl, onc, dash, alt):
    gl, gr, rum, road, lane, yel = P
    c = int(cx)
    if gl == gr:
        row = [gl] * W
    else:
        c0 = 0 if c < 0 else W if c > W else c
        row = [gl] * c0 + [gr] * (W - c0)
    rw = w * 0.13
    a, b, cc, d = int(cx - w - rw), int(cx - w), int(cx + w), int(cx + w + rw)
    if d <= 0 or a >= W:
        return row
    # rumble strips, then the road
    lo, hi = max(0, a), min(W, d)
    if hi > lo:
        row[lo:hi] = [rum] * (hi - lo)
    lo, hi = max(0, b), min(W, cc)
    if hi > lo:
        row[lo:hi] = [road] * (hi - lo)
    lw = w * 0.022
    if lw >= 0.3:
        lwi = max(1, int(lw + 0.5))
        # solid edge lines
        for e in (cx - w + w * 0.04, cx + w - w * 0.04 - lwi):
            ei = int(e)
            lo, hi = max(0, ei), min(W, ei + lwi)
            if hi > lo:
                row[lo:hi] = [lane] * (hi - lo)
        for kk in range(1, nl):
            lx = cx + (-1 + 2 * kk / nl) * w
            if onc and kk * 2 == nl:
                gap = max(lwi + 1, int(w * 0.035))
                for e in (lx - gap / 2 - lwi / 2, lx + gap / 2 - lwi / 2):
                    ei = int(e)
                    lo, hi = max(0, ei), min(W, ei + lwi)
                    if hi > lo:
                        row[lo:hi] = [yel] * (hi - lo)
            elif dash:
                ei = int(lx - lwi / 2)
                lo, hi = max(0, ei), min(W, ei + lwi)
                if hi > lo:
                    row[lo:hi] = [lane] * (hi - lo)
    return row


def draw_car(px, W, c, sx, sy, s, clip, k, f, haze, st):
    w = CAR_W * s
    if w < 3:                                     # far away: just the lights
        y = int(sy - max(1, w * 0.4))
        if 0 <= y < clip:
            lc = mix((255, 245, 215) if c.onc else (255, 30, 40), haze, f * 0.35)
            for x in ((int(sx),) if w < 1.5 else (int(sx - w / 2), int(sx + w / 2))):
                if 0 <= x < W:
                    px[y][x] = lc
        return
    h = w * 9 / 16 * 1.05
    art = ONCOMING_ART if c.onc else TRAFFIC_ART
    cols = car_colours(c.col, min(1.4, k), f, haze)
    if st.get("rain") and not c.onc:              # wet road: tail light reflections
        rc = (90, 10, 16)
        for x in (int(sx - w * 0.4), int(sx + w * 0.35)):
            for y in range(int(sy), min(int(clip), int(sy + h * 0.8))):
                if 0 <= x < W and 0 <= y < len(px):
                    p = px[y][x]
                    px[y][x] = (min(255, p[0] + rc[0]), p[1] + 2, p[2] + 2)
    draw_art(px, W, art, cols, sx - w / 2, sy - h, w, h, clip)
    if c.onc:
        for x in (sx - w * 0.4, sx + w * 0.4):
            glow(px, W, x, sy - h * 0.38, max(1.8, w * 0.45), (210, 205, 170), 0.9 * (1 - f * 0.5), clip)
    else:
        for x in (sx - w * 0.41, sx + w * 0.41):
            glow(px, W, x, sy - h * 0.38, max(1.2, w * 0.22), (150, 10, 10), 0.8 * (1 - f * 0.6), clip)


def draw_player(cv, r, W, H, car_bot, SX, st):
    px = cv.px
    w = CAR_W / PLAYER_Z * DEPTH * SX * 1.12
    w = max(12, int(w))
    h = int(w * len(PLAYER_ART) / len(PLAYER_ART[0]) * 0.95 + 0.5)
    bump = 0
    if abs(r.x) > 1.0 and r.speed > MAXV * 0.05:
        bump = r.rnd.choice((0, 0, -1))
    trk = r.trk
    k = 0.62 + trk.light[trk.seg(r.pz)] * 0.6
    braking = r.brake_t > 0 or r.state != "run"
    cols = car_colours((70, 150, 210), k, 0.0, st["haze"], brake=braking)
    x0 = W / 2 - w / 2
    y0 = car_bot - h + bump
    # shadow under the car
    sh = (6, 6, 10)
    fill(px, W, x0 + 1, car_bot - 1, x0 + w - 1, car_bot + 1, sh, H)
    if r.spin > 0:
        a = r.spin * 14
        cs = math.cos(a)
        side = abs(cs) < 0.45
        art = SIDE_ART if side else PLAYER_ART
        ww = int(w * 1.1) if side else max(8, int(w * (0.6 + 0.4 * abs(cs))))
        hh = int(ww * len(art) / len(art[0]) * 1.1 + 0.5) if side else h
        draw_art(px, W, art, cols, W / 2 - ww / 2, car_bot - hh, ww, hh, H, flip=math.sin(a) < 0)
        for j in range(6):                          # tyre smoke
            sx = W / 2 + r.rnd.uniform(-w * 0.7, w * 0.7)
            glow(px, W, sx, car_bot - r.rnd.uniform(0, h * 0.6), r.rnd.uniform(1.5, w * 0.18), (60, 60, 66), 0.7, H)
        return
    draw_art(px, W, PLAYER_ART, cols, x0, y0, w, h, H, lean=r.steer * (w / 28))
    lc = (255, 40, 40) if braking else (170, 10, 16)
    for x in (x0 + w * 0.12, x0 + w * 0.88):
        glow(px, W, x, y0 + h * 0.6, w * (0.16 if braking else 0.1), shade(lc, 0.6), 0.9, H)
    if abs(r.x) > 1.0 and r.speed > MAXV * 0.1:     # dust off the verge
        for j in range(4):
            glow(px, W, W / 2 + r.rnd.uniform(-w * 0.6, w * 0.6), car_bot - r.rnd.uniform(0, 3),
                 r.rnd.uniform(1.5, 4), (70, 60, 50), 0.6, H)


def rain(px, W, H, r):
    rnd = r.rnd
    sp = r.speed / MAXV
    slant = 0.4 + sp * 0.8
    for _ in range(W * H // 45):
        x, y = rnd.uniform(0, W), rnd.uniform(0, H - 2)
        ln = rnd.randint(2, 4)
        side = (x - W / 2) / (W / 2)
        for j in range(ln):
            xx, yy = int(x + side * slant * j), int(y + j)
            if 0 <= xx < W and 0 <= yy < H:
                p = px[yy][xx]
                px[yy][xx] = ((p[0] + 140) >> 1, (p[1] + 150) >> 1, (p[2] + 175) >> 1)


def bar(v, n):
    full = int(round(clamp(v, 0, 1) * n))
    return "█" * full + "░" * (n - full)


def draw_hud(cv, r, cols, rows):
    W, H = cv.W, cv.H
    trk = r.trk
    k = 3 if H >= 110 else 2 if H >= 56 else 1
    # time, big, top centre
    tl = r.time_left
    secs = int(math.ceil(tl)) if r.state != "finish" else int(tl)
    txt = "%d" % secs
    red = tl < 10 and r.state in ("run", "timeup")
    tcol = (255, 70, 60) if red and (int(r.t * 4) % 2 == 0 or tl <= 0) else (255, 70, 60) if red else (255, 240, 200)
    if red and int(r.t * 4) % 2:
        tcol = (255, 150, 120)
    tw = big_width(txt, k + 1)
    cv.center(0, "TIME", (230, 200, 120))
    draw_big(cv, txt, (W - tw) // 2, 2, k + 1, tcol)
    # stage and progress, top left
    s, i0, i1 = trk.ranges[min(r.ci, len(trk.ranges) - 1)]
    prog = clamp((r.pz / SEG - i0) / max(1, i1 - i0), 0, 1)
    cv.put(1, 0, "STAGE %d/%d  %s" % (s + 1, len(STAGES), STAGES[s]["name"]), (255, 220, 140))
    km = r.to_checkpoint() * M_PER_UNIT / 1000
    last = r.ci >= len(trk.ranges) - 1 and trk.ranges[-1][0] == len(STAGES) - 1
    nb = max(6, min(16, cols // 8))
    cv.put(1, 1, "%s %s %.1f km" % (bar(prog, nb), "FINISH" if last else "CP", km), (190, 200, 230))
    # score, top right
    sc = "SCORE %d" % int(r.score)
    cv.put(cols - len(sc) - 1, 0, sc, (240, 220, 140))
    ov = "passed %d" % r.overtakes
    cv.put(cols - len(ov) - 1, 1, ov, (170, 176, 200))
    # speed, big, bottom right
    kmh = int(r.speed * KMH)
    st_ = "%d" % kmh
    sw = big_width(st_, k)
    sx = W - sw - 7
    sy = H - 4 - 5 * k
    draw_big(cv, st_, sx, sy, k, (230, 240, 255))
    cv.put(cols - 6, (sy + 5 * k) // 2 - 1, "km/h", (170, 180, 210))
    # messages
    mrow = max(4, int(rows * 0.28))
    for j, (s_, ttl, col) in enumerate(r.msgs[-2:]):
        if int(ttl * 6) % 2 == 0 or ttl > 1.0:
            cv.center(mrow + j * 2, "  %s  " % s_, col, (16, 12, 30))
    if r.state == "count":
        n = 3 - int(r.t_state)
        txt = str(max(1, n))
        kk = k + 2
        draw_big(cv, txt, (W - big_width(txt, kk)) // 2, int(H * 0.3), kk, (255, 220, 90))
    if abs(r.x) > 1.0 and r.state == "run" and r.spin <= 0:
        cv.center(mrow + 5, " OFF ROAD ", (255, 200, 120), (40, 20, 10))
    # bottom bar
    rr = rows - 1
    bg = (12, 12, 20)
    segs = [(" NIGHTDRIVE ", (16, 10, 30), (255, 110, 230)),
            ("  %3d km/h " % kmh, (230, 236, 250), None),
            ("  time %d " % secs, (255, 110, 90) if red else (240, 220, 160), None),
            ("  %s %.1f km " % ("finish" if last else "checkpoint", km), (170, 200, 240), None),
            ("  score %d " % int(r.score), (240, 220, 140), None),
            ("  %s throttle " % ("auto" if r.auto else "manual"), (150, 156, 186), None)]
    right = " ? help  Esc menu "
    x = 0
    for s_, fg, b in segs:
        if x + len(s_) + len(right) > cols:
            break
        cv.put(x, rr, s_, fg, b or bg)
        x += len(s_)
    cv.put(x, rr, " " * max(0, cols - x), bg, bg)
    if x + len(right) <= cols:
        cv.put(cols - len(right), rr, right, (130, 136, 170), bg)


HELP = [
    "NIGHTDRIVE - keys",
    "",
    "Left / Right  (A / D)    steer: tap = small correction, hold = turn",
    "Up  (W)                  accelerate (manual throttle: each press adds gas)",
    "Down  (S) / Space        brake",
    "",
    "Reach each checkpoint before the clock runs out - it adds time.",
    "Overtake the traffic (red tail lights). On the forest, desert and",
    "mountain stages cars come towards you in the left-hand lanes.",
    "Curves push you outwards; the verge slows you; trees, lamps and",
    "rocks spin you round. Throttle auto/manual is set on the title.",
    "",
    "Esc / P                  pause menu (Q there: quit)",
    "M  (in the pause menu)   sound on / off",
    "?                        this help",
]
PAUSE = ["P A U S E D", "", "Esc / P / Enter   continue", "?                 help", "M                 sound on / off",
         "Q                 quit to the menu"]


def render_end(cv, r, record):
    fin = r.state == "finish"
    s = r.trk.ranges[min(r.ci, len(r.trk.ranges) - 1)][0]
    lines = ["F I N I S H" if fin else "T I M E   U P", ""]
    if fin:
        lines += ["You made it through the night.", "time bonus  %d x 100" % int(r.time_left)]
    else:
        lines += ["You ran out of time on stage %d, %s." % (s + 1, STAGES[s]["name"]),
                  "%.1f km short of the %s." % (r.to_checkpoint() * M_PER_UNIT / 1000,
                                                "finish" if s == len(STAGES) - 1 else "checkpoint")]
    lines += ["", "distance  %.1f km   passed  %d cars" % (r.dist / 1000, r.overtakes), "score  %d" % int(r.score)]
    if record:
        lines += ["", "** NEW RECORD **"]
    lines += ["", "Enter: drive again   Esc / Q: menu"]
    w = max(len(l) for l in lines) + 4
    cv.box(max(0, (cv.cols - w) // 2), max(0, cv.rows // 2 - len(lines) // 2 - 1), [l.center(w - 4) for l in lines],
           (240, 240, 246), (40, 14, 46) if fin else (46, 14, 20))


# =============================================================================================
# The autopilot (title demo and tests): it only presses keys, like a player
# =============================================================================================
def safe_speed(c, margin=0.8):
    """The highest speed fraction at which the steering can still hold curve c."""
    c = abs(c)
    if c < 1e-6:
        return 1.0
    s = 1.0
    while s > 0.2 and CENTRIF * s * s * c > margin * STEER_RATE * (0.3 + 0.7 * s):
        s -= 0.02
    return s


class Driver:
    def __init__(self, sloppy=False, seed=1):
        self.sloppy = sloppy
        self.rnd = random.Random(seed)
        self.lane = None
        self.tick = 0
        self.noise = 0.0
        self.lane_cool = 0.0

    def act(self, r, dt=1 / 30):
        self.tick += 1
        if r.state != "run":
            return
        if self.sloppy:
            if self.tick % 3:                         # reacts ten times a second
                return
            dt *= 3
            if self.tick % 30 == 0:
                self.noise = self.rnd.uniform(-0.12, 0.12)
        trk = r.trk
        st = STAGES[trk.stage[trk.seg(r.pz)]]
        lanes = same_lanes(st)
        if self.lane is None or self.lane >= len(lanes) or self.lane_cool <= -5:
            self.lane = min(range(len(lanes)), key=lambda j: abs(lanes[j] - r.x))
            self.lane_cool = 0.0
        self.lane_cool -= dt
        sp = r.speed / MAXV
        look = (8 + (30 if self.sloppy else 45) * sp) * SEG
        pz = r.pz

        def first(lx, back=-1.5 * SEG):
            """The nearest car in the lane at lx that is in the way (distance, car)."""
            best = (None, None)
            for c in r.cars:
                if abs(c.x - lx) < 0.45:
                    dz = c.z - pz
                    if back < dz < look and (c.onc or c.v < r.speed * 0.98 or dz < 3 * SEG):
                        if best[0] is None or dz < best[0]:
                            best = (dz, c)
            return best
        cur_d, cur_c = first(lanes[self.lane])
        if cur_d is not None and self.lane_cool <= 0:
            def free(j):
                d = first(lanes[j], -3.0 * SEG)[0]
                return look * 2 if d is None else d
            best_j, best_f = self.lane, cur_d + 4 * SEG
            for j in range(len(lanes)):
                if j == self.lane:
                    continue
                path_ok = all(free(m) > 5 * SEG for m in range(min(j, self.lane), max(j, self.lane) + 1) if m != self.lane)
                fj = free(j) - abs(j - self.lane) * SEG
                if path_ok and fj > best_f:
                    best_j, best_f = j, fj
            if best_j != self.lane:
                self.lane = best_j
                self.lane_cool = 0.5
                cur_d, cur_c = first(lanes[self.lane])
        # a car in the way of the car's actual path (e.g. while crossing a lane): give up the move or brake
        path_d, path_c = None, None
        tx = lanes[self.lane]
        for c in r.cars:
            dz = c.z - pz
            if -1.0 * SEG < dz < look and min(r.x, tx) - 0.4 < c.x < max(r.x, tx) + 0.4 and abs(c.x - r.x) < 0.75:
                if (c.onc or c.v < r.speed) and (path_d is None or dz < path_d):
                    path_d, path_c = dz, c
        if path_c is not None and path_c is not cur_c and path_d < 4 * SEG:
            home = min(range(len(lanes)), key=lambda j: abs(lanes[j] - r.x))
            if abs(lanes[home] - path_c.x) > 0.45:
                self.lane = home
                self.lane_cool = 0.4
        target = lanes[self.lane] + self.noise
        # steering: predict where the car drifts and press towards the line
        pseg = trk.seg(pz)
        ahead = 2 if self.sloppy else 4
        c_now = trk.curve[min(trk.n - 1, pseg + ahead)]
        eff = 0.3 + 0.7 * sp
        drift = CENTRIF * sp * sp * c_now
        ff = drift / (STEER_RATE * eff) * (0.8 if self.sloppy else 1.0)
        err = target - r.x
        vdes = clamp(err * (3.0 if self.sloppy else 4.0), -1.1, 1.1)
        want = clamp(ff + vdes / (STEER_RATE * eff), -1, 1)
        if want > r.steer + 0.08:
            r.key("right")
        elif want < r.steer - 0.08:
            r.key("left")
        # speed: brake for curves the car cannot hold, and when boxed in
        span = int(10 + 26 * sp)
        cmax = max(abs(trk.curve[min(trk.n - 1, pseg + j)]) for j in range(0, span, 2))
        limit = safe_speed(cmax, 0.75 if self.sloppy else 0.85)
        brake = sp > limit + 0.02
        for d, c in ((cur_d, cur_c), (path_d, path_c)):
            if c is not None and (c is path_c or abs(r.x - lanes[self.lane]) < 0.3):
                rel = r.speed - (c.v if not c.onc else -MAXV)
                if rel > 0 and d < rel * rel / (2 * MAXV * 0.8) + (3.5 if not self.sloppy else 5) * SEG:
                    brake = True
        if abs(r.x) > 1.05 and sp > 0.3:
            brake = True
        if brake:
            r.key("down")
        elif not r.auto:
            r.key("up")


# =============================================================================================
# Title and main loop
# =============================================================================================
class TitleDemo:
    """The road at night with the car driving itself, behind the title screen (and the launcher preview)."""

    def __init__(self, seed=3):
        self.k = 0
        self.seed = seed
        self.new_run()

    def new_run(self):
        s = [0, 1, 3, 2, 5, 4][self.k % 6]
        self.k += 1
        self.r = Race(s, auto=True, seed=self.seed + self.k, stop=s + 1, demo=True)
        self.r.pos = SEG * 40
        self.r.speed = MAXV * 0.8
        self.d = Driver(seed=self.k)
        self.t = 0.0

    def scene(self, cols, rows, dt):
        """Advance the demo and return the bare picture (no HUD) as a Canvas."""
        self.t += dt
        r = self.r
        steps = max(1, int(round(dt * 30)))
        for _ in range(steps):
            self.d.act(r)
            r.update(dt / steps)
        r.msgs = []
        if self.t > 24 or r.pz > (r.trk.finish - 30) * SEG:
            self.new_run()
        return render(r, cols, rows, hud=False)

    def frame(self, cols, rows, dt, help_, sel, start=0, auto=True, unlocked=0):
        cv = self.scene(cols, rows, dt)
        sc = load_scores().get(GAME, {})
        items = ["Drive", "Start  < stage %d  %s >" % (start + 1, STAGES[start]["name"]),
                 "Throttle  < %s >" % ("auto" if auto else "manual")]
        best = sc.get("score")
        line = None
        if best is not None:
            line = "best score %d   furthest: stage %d %s" % (best, min(len(STAGES), sc.get("stage", 1)),
                                                               STAGES[min(len(STAGES), sc.get("stage", 1)) - 1]["name"])
        extra = ["", "Six stages through the night. Beat the clock,", "reach every checkpoint, mind the traffic.",
                 "Stages unlock as you reach them (%d of %d)." % (unlocked + 1, len(STAGES))]
        title_screen(cv, "NIGHTDRIVE", "a race against the clock, after dark", items, sel, line, extra=extra,
                     keys="Up/Down choose   Left/Right change   Enter drive   ? help   Esc quit",
                     help_lines=HELP, show_help=help_, dim=0.35)
        return cv


def small(term):
    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (70x22).")


def main():
    with Terminal() as term:
        demo = TitleDemo()
        sel, start, auto = 0, 0, True
        while True:
            sc = load_scores().get(GAME, {})
            unlocked = clamp(sc.get("stage", 1) - 1, 0, len(STAGES) - 1)
            start = min(start, unlocked)
            help_, go = False, False
            last = time.time()
            while not go:
                now = time.time()
                cols, rows = term.size()
                if cols < 70 or rows < 22:
                    small(term)
                    if any(k in ("q", "esc") for k in term.keys(0.3)):
                        return
                    last = time.time()
                    continue
                term.write(demo.frame(cols, rows, min(0.1, now - last), help_, sel, start, auto, unlocked).emit())
                last = now
                for k in term.keys(max(0.0, 1 / 30 - (time.time() - now))):
                    if help_:
                        help_ = False
                    elif k == "?":
                        help_ = True
                    elif k in ("q", "esc"):
                        return
                    elif k in ("up", "w"):
                        sel = (sel - 1) % 3
                        SND.play("select")
                    elif k in ("down", "s"):
                        sel = (sel + 1) % 3
                        SND.play("select")
                    elif k in ("left", "right", "a", "d"):
                        d = -1 if k in ("left", "a") else 1
                        if sel == 1:
                            start = (start + d) % (unlocked + 1)
                        elif sel == 2:
                            auto = not auto
                        SND.play("select")
                    elif k in ("enter", " "):
                        go = True
                        SND.play("start")
            while True:                                  # one race; Enter on the end screen starts another
                r = Race(start, auto=auto)
                last = time.time()
                record = None
                back = again = False
                while not (back or again):
                    now = time.time()
                    over = r.state in ("timeup", "finish")
                    for k in term.keys(0):
                        if over and r.t_state > 0.8:
                            if k in ("q", "esc"):
                                back = True
                            elif k in ("enter", " "):
                                again = True
                                SND.play("start")
                            continue
                        a = shared_key(k, r.paused, pause_keys=("esc", "p", "q"))
                        if a == "pause":
                            r.paused = True
                        elif a == "resume":
                            r.paused = r.help = False
                        elif a == "quit":
                            back = True
                        elif a == "help":
                            r.help = not r.help
                            r.paused = True
                        elif a == "sound":
                            if SND.toggle():
                                SND.play("select")
                        elif a is None:
                            r.key(k)
                    r.update(min(0.1, now - last))
                    last = now
                    if r.state in ("timeup", "finish") and record is None:
                        record = submit(GAME, "score", int(r.score))
                        submit(GAME, "stage", r.reached + 1)
                    elif r.reached + 1 > sc.get("stage", 1):
                        submit(GAME, "stage", r.reached + 1)
                        sc = load_scores().get(GAME, {})
                    cols, rows = term.size()
                    if cols < 70 or rows < 22:
                        small(term)
                        r.paused = r.paused or r.state == "run"     # do not race on unseen
                        time.sleep(0.2)
                        continue
                    cv = render(r, cols, rows)
                    if r.paused:
                        overlay(cv, HELP if r.help else PAUSE + ["", SND.label()])
                    elif r.state in ("timeup", "finish") and r.t_state > 0.8:
                        render_end(cv, r, record)
                    term.write(cv.emit())
                    time.sleep(max(0.0, 1 / 32 - (time.time() - now)))
                if back:
                    break


# =============================================================================================
# Tests
# =============================================================================================
def drive(r, driver=None, limit=900.0, dt=1 / 30):
    """Run a race with a driver (None = hands off) until it ends or `limit` game seconds pass."""
    steps = 0
    while r.state in ("count", "run") and steps * dt < limit:
        if driver is not None:
            driver.act(r, dt)
        r.update(dt)
        steps += 1
    return r


def selftest():
    t0 = time.time()
    # 1. the track data is sane
    full = Course(0)
    assert len(full.ranges) == len(STAGES)
    for s, i0, i1 in full.ranges:
        st = STAGES[s]
        assert i1 - i0 == st["length"], "stage %d is %d segments, wanted %d" % (s, i1 - i0, st["length"])
        cs = full.curve[i0:i1]
        assert max(abs(c) for c in cs) <= st["curve"] + 1e-9, "stage %d: a curve is too sharp" % s
        assert max(abs(c) for c in cs) <= 3.3
        slopes = [abs(full.y[i + 1] - full.y[i]) / SEG for i in range(i0, i1)]
        assert max(slopes) < 1.2, "stage %d: a hill is too steep (%.2f)" % (s, max(slopes))
        assert all(abs(full.curve[i + 1] - full.curve[i]) < 0.35 for i in range(i0, i1 - 1)), "curve jumps"
        assert safe_speed(max(abs(c) for c in cs), 1.0) >= 0.8, "stage %d: curves need crawling" % s
        assert full.gates.get(i1), "stage %d has no checkpoint gate" % s
        for i in range(i0, i1):                       # the road itself is always clear
            for kind, off, seed in full.spr[i]:
                assert abs(off) > 1.05, "an object stands on the road"
    assert full.finish == sum(st["length"] for st in STAGES)
    # 2. the autopilot reaches every checkpoint in time, starting fresh on each stage
    report = []
    for s in range(len(STAGES)):
        for seed in (1, 2):
            r = drive(Race(s, auto=True, seed=seed, stop=s + 1), Driver(seed=seed))
            assert r.state == "finish", "autopilot ran out of time on stage %d (seed %d), %.0f m short" % (
                s + 1, seed, r.to_checkpoint() * M_PER_UNIT)
            margin = r.time_left / allowance(s)
            assert r.time_left >= 8 and margin >= 0.1, "stage %d: margin only %.1f s" % (s + 1, r.time_left)
            assert margin <= 0.45, "stage %d is too easy: %.1f s left" % (s + 1, r.time_left)
        report.append("%d:%.0fs/%ds" % (s + 1, r.time_left, allowance(s)))
        # a sloppy driver (reacts ten times a second, wobbles) still makes it
        r2 = drive(Race(s, auto=True, seed=9, stop=s + 1), Driver(sloppy=True, seed=9))
        assert r2.state == "finish", "a sloppy driver could not finish stage %d (%.0f m short)" % (
            s + 1, r2.to_checkpoint() * M_PER_UNIT)
        report[-1] += "(sloppy %.0fs)" % r2.time_left
        # nobody at the wheel does not
        r3 = drive(Race(s, auto=True, seed=4, stop=s + 1), None)
        assert r3.state == "timeup", "stage %d can be finished without steering" % (s + 1)
    # 3. the whole run in one go, with manual throttle
    r = drive(Race(0, auto=False, seed=5), Driver(seed=5), limit=1500)
    assert r.state == "finish", "the full run failed on stage %d" % (r.stage_index + 1)
    assert len(r.cp_times) == len(STAGES)
    full_left = r.time_left
    # 4. controls: taps make small corrections, held keys turn
    r = Race(0, seed=1)
    r.state = "run"
    r.speed = MAXV * 0.9
    r.pos = SEG * 10
    x0 = r.x
    r.key("right")
    for _ in range(30):
        r.update(1 / 30)
    tap = r.x - x0
    r = Race(0, seed=1)
    r.state, r.speed, r.pos = "run", MAXV * 0.9, SEG * 10
    x0 = r.x
    for j in range(30):
        if j == 0 or j >= 8:                          # first press, the repeat delay, then key repeat
            r.key("right")
        r.update(1 / 30)
    held = r.x - x0
    assert 0.03 < tap < 0.3 and held > 1.0 > tap * 3, "steering feel: tap %.2f held %.2f" % (tap, held)
    r = Race(0, auto=False, seed=1)
    r.state = "run"
    for _ in range(60):
        r.update(1 / 30)
    assert r.speed == 0, "manual throttle should not move without gas"
    for _ in range(3):
        r.key("up")
    for _ in range(60):
        r.update(1 / 30)
    assert r.speed > MAXV * 0.2, "gas presses do not accelerate"
    # 5. rendering at the smallest and a big window, every stage, with traffic and the HUD
    demo = TitleDemo()
    for s in range(len(STAGES)):
        r = Race(s, seed=s, stop=s + 1)
        r.state = "run"
        drive(r, Driver(), limit=6)
        for cols, rows in ((70, 22), (160, 45), (111, 31)):
            cv = render(r, cols, rows)
            out = cv.emit(True)
            assert len(cv.px) == rows * 2 and all(len(row) == cols for row in cv.px), "bad canvas size"
            assert out.count("\r\n") == rows - 1
            cv.emit(False)
        r.state = "timeup"
        render_end(render(r, 70, 22), r, True)
        demo.frame(70, 22, 0.05, s % 2 == 0, s % 3, 0, s % 2 == 0, 2)
        demo.frame(160, 45, 0.05, False, 1)
    print("Self-test ok: %d stages sane; autopilot time left per stage %s; nobody at the wheel runs out of time "
          "everywhere; full run with manual throttle finished with %.0f s left; tap %.2f vs held %.2f road widths; "
          "frames render at 70x22, 111x31, 160x45 (%.1fs)" % (len(STAGES), " ".join(report), full_left, tap / 2,
                                                            held / 2, time.time() - t0))


def bench():
    for s in (0, 2, 5):
        r = Race(s, seed=3, stop=s + 1)
        r.state = "run"
        drive(r, Driver(), limit=12)
        for cols, rows in ((70, 22), (160, 45), (200, 56)):
            t = time.time()
            for _ in range(20):
                cv = render(r, cols, rows)
            t1 = time.time()
            for _ in range(20):
                cv.emit(True)
            t2 = time.time()
            print("stage %d %-14s %3dx%-3d render %5.1f ms  emit %4.1f ms  total %5.1f ms" % (
                s + 1, STAGES[s]["name"], cols, rows, (t1 - t) / 20 * 1000, (t2 - t1) / 20 * 1000, (t2 - t) / 20 * 1000))
    r = Race(0, seed=1)
    t = time.time()
    drive(r, Driver(), limit=60)
    print("simulation: 60 s of racing in %.2f s" % (time.time() - t))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--bench" in sys.argv:
        bench()
    else:
        main()
