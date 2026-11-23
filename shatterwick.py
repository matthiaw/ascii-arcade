#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""SHATTERWICK - bounce a spark through walls of glass.

The Gloam has sealed the old lamp town behind walls of tinted glass. Steer the lamplighter's brass tray and keep
Wick, a living candle spark, bouncing up to shatter the panes: tinted glass, frosted double panes that crack,
iron plates that never break, powder panes that blow up their neighbours, sliding panes, lantern panes that
always drop a gift, and frost panes that grow back. Five districts of five halls - the Glasshouse, the Tide
Cellar, the Clock Loft, the Frost Spire and the Kiln Heart - each ending with a keeper the Gloam has woken.
Endless mode builds new halls for as long as the spark lasts.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
In terminals with the kitty keyboard protocol (kitty, WezTerm, Ghostty, recent iTerm2) keys are read with their
releases; elsewhere a key counts as held while the terminal repeats it.
"""
import math
import random
import sys
import time

from arcadekit import (ACCENTS, AUTO_LABEL, PAUSE_LINES, AutoMode, Canvas, HeldKeys, KeyTerminal, clamp, footer,
                       load_scores, mix, overlay, scale_art, shade, shared_key, submit, title_screen)
from arcadesound import Sound

GAME = "shatterwick"
NAME = "SHATTERWICK"
TAGLINE = "bounce a spark through walls of glass"
ACCENTS.setdefault(NAME, ((255, 222, 130), (96, 160, 246)))

FW, FH = 26.0, 19.0             # the hall in units; a pane is 2 x 1 units, a unit is s x s screen pixels
COLS, ROWS = 13, 11             # the pane grid
GY = 1.5                        # top of the grid (above it the creatures come in through two hatches)
PY = 17.4                       # top of the tray
PTH = 0.75                      # tray thickness
BALL_R = 0.32
DT = 1 / 60                     # physics step
SUB = 0.18                      # a spark moves at most this far per sub-step (no tunnelling)
MAX_ANG = math.radians(62)      # bounce angle at the tray's tips
MIN_VY = 0.34                   # the spark never flies flatter than this (no endless side-to-side loops)
PW_NORMAL, PW_WIDE, PW_NARROW = 3.6, 5.4, 2.4
PADDLE_V = 27.0
CAP_W, CAP_H, CAP_VY = 1.7, 0.8, 5.0
BOLT_VY = 34.0
ENEMY_R = 0.62
BAR_Y = 18.55                   # the Hearth line
REGEN_T = 7.0
EXTRA_FIRST, EXTRA_EVERY = 20000, 30000
HATCHES = (6.0, 20.0)
WHITE = (255, 255, 255)

# =============================================================================================
# The five districts
# =============================================================================================
WORLDS = [
    dict(name="THE GLASSHOUSE", short="GLASSHOUSE",
         panes=[(112, 204, 92), (64, 176, 150), (182, 222, 84), (242, 204, 86), (232, 122, 152), (120, 184, 232)],
         sky=((8, 26, 24), (18, 52, 38)), field=(6, 18, 16), frame=((92, 120, 104), (50, 70, 60)), regen=(120, 210, 120),
         enemy="moth", boss="bramble", accent=(150, 232, 140), ambient=(230, 236, 150)),
    dict(name="THE TIDE CELLAR", short="TIDE CELLAR",
         panes=[(64, 142, 232), (42, 192, 204), (116, 112, 236), (72, 222, 172), (236, 150, 192), (242, 222, 124)],
         sky=((4, 12, 36), (8, 44, 74)), field=(4, 12, 28), frame=((96, 104, 120), (52, 58, 72)), regen=(100, 220, 210),
         enemy="jelly", boss="clam", accent=(110, 200, 255), ambient=(170, 220, 255)),
    dict(name="THE CLOCK LOFT", short="CLOCK LOFT",
         panes=[(234, 172, 72), (204, 112, 62), (244, 214, 124), (176, 124, 84), (124, 174, 184), (222, 92, 72)],
         sky=((40, 24, 14), (16, 10, 8)), field=(18, 11, 8), frame=((168, 128, 62), (96, 66, 32)), regen=(220, 190, 110),
         enemy="cog", boss="pendulum", accent=(250, 196, 100), ambient=(250, 220, 160)),
    dict(name="THE FROST SPIRE", short="FROST SPIRE",
         panes=[(172, 222, 255), (122, 172, 242), (222, 240, 255), (152, 132, 232), (122, 222, 222), (240, 172, 222)],
         sky=((6, 8, 28), (28, 34, 72)), field=(6, 10, 24), frame=((176, 206, 232), (96, 120, 156)), regen=(200, 240, 255),
         enemy="mote", boss="owl", accent=(190, 230, 255), ambient=(235, 245, 255)),
    dict(name="THE KILN HEART", short="KILN HEART",
         panes=[(242, 112, 52), (252, 172, 62), (212, 62, 62), (252, 222, 112), (174, 72, 122), (196, 132, 92)],
         sky=((24, 6, 6), (70, 20, 8)), field=(16, 6, 5), frame=((150, 70, 50), (86, 36, 26)), regen=(250, 150, 90),
         enemy="cinder", boss="bellows", accent=(255, 150, 80), ambient=(255, 170, 70)),
]

# Legend:  a-f tinted panes (the district's six colours)   2 3 frosted panes that take 2 / 3 hits   # iron plate
#          * powder pane (blows up its neighbours)   $ lantern pane (always drops a gift)   % frost (grows back)
#          < > sliding panes (start direction)   . nothing
LEVELS = [
    # --- the Glasshouse ---
    (0, "First Light", None, [
        ".............",
        "..aaaaaaaaa..",
        ".bbbbbbbbbbb.",
        ".cc$ccccc$cc.",
        ".ddddddddddd.",
        "..eeeeeeeee.."]),
    (0, "Trellis", None, [
        "a.b.c.d.c.b.a",
        ".2.2.2.2.2.2.",
        "a.b.c$d$c.b.a",
        ".2.2.2.2.2.2.",
        "a.b.c.d.c.b.a",
        ".............",
        ".fffff.fffff."]),
    (0, "Fern Spiral", None, [
        "....aaaaa....",
        "...a22222a...",
        "..ab.....ba..",
        ".ab..c$c..ba.",
        ".ab..ccc..ba.",
        "..ab.....ba..",
        "...a22222a...",
        "....aaaaa...."]),
    (0, "Potting Shed", None, [
        ".............",
        ".bb.#ddd#.bb.",
        ".bb.#ddd#.bb.",
        ".bb.##$##.bb.",
        ".............",
        "c.cc.eee.cc.c",
        "c.cc2eee2cc.c",
        ".....###.....",
        ".aaaaaaaaaaa."]),
    (0, "The Bramble Crown", "bramble", [
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
        "%%%.%%%%%.%%%",
        "a2a.......a2a"]),
    # --- the Tide Cellar ---
    (1, "Kelp Shelves", None, [
        ".............",
        "aaaa.....aaaa",
        ">............",
        ".bbbbbbbbbbb.",
        "............<",
        "cc$cc...cc$cc",
        ".............",
        ".ddddddddddd."]),
    (1, "Coral Pockets", None, [
        "..a.a...a.a..",
        ".bb*bb.bb*bb.",
        ".b2$2b.b2$2b.",
        ".bbbbb.bbbbb.",
        "......>......",
        ".cc.ccccc.cc.",
        "..d.d.d.d.d.."]),
    (1, "Shipwreck Hold", None, [
        "#...........#",
        "#.aaaaaaaaa.#",
        "#.a2222222a.#",
        "#.a2*$*$*2a.#",
        "#.a2222222a.#",
        "#.aaaaaaaaa.#",
        "#...........#",
        "..>.......<.."]),
    (1, "Lantern Reef", None, [
        "b.b.b.b.b.b.b",
        ".$.c.c.c.c.$.",
        "d.d.d.d.d.d.d",
        ">............",
        "..e*e...e*e..",
        ".2.2.2.2.2.2.",
        "............<",
        "aaaaaa.aaaaaa"]),
    (1, "The Grotto Clam", "clam", [
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
        ".>.........<.",
        "bb2bb...bb2bb"]),
    # --- the Clock Loft ---
    (2, "Escapement", None, [
        "aaaaaaaaaaaaa",
        ">............",
        "..b.b.b.b.b..",
        "............<",
        "cc2cc2c2cc2cc",
        ">............",
        "..d$d...d$d.."]),
    (2, "Gear Train", None, [
        "..#a#...#a#..",
        ".#aaa#.#aaa#.",
        "..#2#...#2#..",
        ".............",
        "b.b.b.#.b.b.b",
        ".c$c.###.c$c.",
        "b.b.b.#.b.b.b",
        ".............",
        "ddddddddddddd"]),
    (2, "Cuckoo Gallery", None, [
        "....a$a$a....",
        "...bbbbbbb...",
        "..cc33333cc..",
        ".dd.......dd.",
        "#.<.......>.#",
        ".eeee...eeee.",
        "..2.2...2.2.."]),
    (2, "Mainspring", None, [
        "3a3a3a3a3a3a3",
        ".............",
        "#b#b#b.b#b#b#",
        ".............",
        "c*c*c*c*c*c*c",
        "..>.......<..",
        "d.d.d.d.d.d.d",
        "#...........#",
        ".e$e.e$e.e$e."]),
    (2, "The Pendulum Warden", "pendulum", [
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
        "#a2a#...#a2a#",
        ".b.b.b.b.b.b."]),
    # --- the Frost Spire ---
    (3, "Hoarfrost", None, [
        "%%%%%%%%%%%%%",
        ".............",
        ".aaaaaaaaaaa.",
        ".b$bbbbbbb$b.",
        ".ccccccccccc.",
        "..%%%%%%%%%.."]),
    (3, "Icicle Gallery", None, [
        "a.a.a.a.a.a.a",
        "2.2.2.2.2.2.2",
        "b.b.b$b.b.b.b",
        "3.c.3.c.3.c.3",
        "..d...d...d..",
        "%...%...%...%"]),
    (3, "Aurora Steps", None, [
        "aa...........",
        "bbbb.........",
        "cc$ccc.......",
        "dddddddd.....",
        "eeeee$eeee...",
        "#2#2#2#2#2#..",
        "%%%%%%%%%%%%.",
        ">............"]),
    (3, "Glacier Vault", None, [
        ".###########.",
        ".#a2a2a2a2a#.",
        ".#b$b*b*b$b#.",
        ".#ccccccccc#.",
        ".#####.#####.",
        ".............",
        "..%%%...%%%..",
        ".d.d.d.d.d.d."]),
    (3, "The Rime Owl", "owl", [
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
        "%%.%%.%.%%.%%",
        "a3a.......a3a"]),
    # --- the Kiln Heart ---
    (4, "Firing Racks", None, [
        "aaaaaaaaaaaaa",
        "b*b*b*b*b*b*b",
        ".............",
        "cccccc$cccccc",
        "d*d*d*d*d*d*d",
        ".............",
        "#2#2#2#2#2#2#"]),
    (4, "Slag Chain", None, [
        "*a*a*a*a*a*a*",
        "..>..........",
        "b3b.b3b.b3b.b",
        "*...........*",
        ".c*c*c$c*c*c.",
        "#...........#",
        "..d%d%d%d%d.."]),
    (4, "Glaze Cascade", None, [
        "a...........a",
        "ab.........ba",
        "abc.......cba",
        "abcd.....dcba",
        "abcde$$$edcba",
        "#2#2#.*.#2#2#",
        ".....<.>....."]),
    (4, "Crucible", None, [
        "3333333333333",
        "#a*a*a#a*a*a#",
        "#bbbbb#bbbbb#",
        "#c$c$c#c$c$c#",
        "##.#######.##",
        ".............",
        "..%%%%%%%%%..",
        "<............",
        "e.e.e.e.e.e.e"]),
    (4, "The Bellows Heart", "bellows", [
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
        ".............",
        "*.*.*...*.*.*",
        "#2#.......#2#"]),
]
BOSS_HP = {"bramble": 12, "clam": 10, "pendulum": 14, "owl": 14, "bellows": 16}
BOSS_NAME = {"bramble": "THE BRAMBLE CROWN", "clam": "THE GROTTO CLAM", "pendulum": "THE PENDULUM WARDEN",
             "owl": "THE RIME OWL", "bellows": "THE BELLOWS HEART"}
BRICK_PTS = {"norm": 50, "tough": 120, "blast": 70, "drop": 90, "regen": 40, "move": 100}

POWERS = {   # letter, name, capsule colour, good?, seconds (0: at once), drop weight, what it does
    "wide": ("B", "BROADWICK", (92, 162, 255), True, 20, 14, "a broader tray"),
    "catch": ("T", "TALLOW", (242, 188, 82), True, 16, 10, "sparks stick to the tray"),
    "multi": ("K", "KINDLE", (236, 112, 222), True, 0, 11, "every spark splits in three"),
    "pierce": ("N", "NEEDLEFLAME", (255, 98, 86), True, 8, 6, "sparks burn through glass"),
    "laser": ("F", "FLINT", (82, 222, 232), True, 12, 9, "Space strikes flint bolts"),
    "slow": ("L", "LULL", (132, 228, 132), True, 12, 9, "a calmer spark"),
    "barrier": ("H", "HEARTH", (255, 152, 62), True, 15, 7, "a glowing line saves sparks"),
    "life": ("+", "SPARE WICK", (255, 238, 238), True, 0, 2.2, "one more spark"),
    "narrow": ("P", "PINCH", (118, 70, 96), False, 12, 7, "a narrow tray"),
    "fast": ("G", "GUST", (70, 88, 124), False, 10, 7, "a wild spark"),
    "heavy": ("S", "SOOT", (70, 66, 74), False, 8, 5, "a sluggish tray"),
}
OPPOSED = {"wide": "narrow", "narrow": "wide", "slow": "fast", "fast": "slow"}

ENDLESS_WORDS = (
    (("Dewy", "Sunlit", "Mossy", "Hanging", "Fernlit", "Budding"), ("Benches", "Arches", "Panes", "Beds", "Frames")),
    (("Sunken", "Brine", "Pearl", "Kelp", "Drowned", "Tidal"), ("Vaults", "Pools", "Racks", "Steps", "Hollows")),
    (("Ticking", "Brass", "Wound", "Gilded", "Oiled", "Chiming"), ("Wheels", "Lofts", "Springs", "Gears", "Cases")),
    (("Rime", "Pale", "Glassy", "Starlit", "Hushed", "Frozen"), ("Ledges", "Halls", "Steps", "Spires", "Vaults")),
    (("Molten", "Glazed", "Ashen", "Ember", "Searing", "Cinder"), ("Racks", "Kilns", "Flues", "Shelves", "Chambers")),
)

# =============================================================================================
# Sound: a bright glass-and-brass bank
# =============================================================================================
def _arp(fs, d=0.05, v=0.3, w="tri", last=0.18):
    out = [dict(w=w, f=f, d=d, v=v) for f in fs[:-1]]
    return out + [dict(w=w, f=fs[-1], d=last, v=v, vib=(7, 0.15))]


def _pane(f):
    return [dict(w="tri", f=f, f2=f * 1.06, d=0.05, v=0.26), dict(w="sine", f=f * 2, d=0.09, v=0.12, at=0.01),
            dict(w="noise", f=9000, f2=5000, d=0.05, v=0.07, at=0)]


SND = Sound(GAME, {
    "pad": [dict(w="tri", f=330, f2=300, d=0.05, v=0.26), dict(w="noise", f=600, d=0.02, v=0.06, at=0)],
    "wall": [dict(w="tri", f=220, d=0.025, v=0.12)],
    **{"pane%d" % i: _pane(f) for i, f in enumerate((784, 880, 988, 1047, 1175, 1319, 1480, 1568))},
    "crack": [dict(w="square", f=1568, f2=1400, d=0.03, v=0.12, duty=0.2), dict(w="noise", f=6000, d=0.04, v=0.1, at=0)],
    "clang": [dict(w="square", f=620, f2=600, d=0.08, v=0.14, duty=0.4), dict(w="noise", f=3500, d=0.03, v=0.1, at=0)],
    "boom": [dict(w="noise", f=900, f2=60, d=0.35, v=0.5), dict(w="tri", f=110, f2=40, d=0.3, v=0.4, at=0)],
    "launch": [dict(w="tri", f=523, f2=784, d=0.07, v=0.3), dict(w="sine", f=1568, d=0.08, v=0.14)],
    "good": _arp([784, 988, 1175, 1568], 0.04, 0.28),
    "bad": [dict(w="saw", f=330, f2=180, d=0.18, v=0.22), dict(w="saw", f=250, f2=120, d=0.2, v=0.18)],
    "split": [dict(w="tri", f=f, d=0.03, v=0.25) for f in (1175, 1568, 2093, 1568, 2349)],
    "life": _arp([784, 988, 1175, 1568, 1175, 1568, 1976], 0.06, 0.3, "square", 0.3),
    "laser": [dict(w="square", f=1760, f2=880, d=0.06, v=0.12, duty=0.25)],
    "pop": [dict(w="tri", f=660, f2=1320, d=0.05, v=0.25), dict(w="noise", f=4000, f2=1000, d=0.06, v=0.1, at=0)],
    "regrow": [dict(w="sine", f=1976, f2=2637, d=0.08, v=0.08)],
    "catch": [dict(w="tri", f=294, f2=262, d=0.06, v=0.24)],
    "save": [dict(w="tri", f=440, f2=880, d=0.1, v=0.25)],
    "stun": [dict(w="square", f=200, f2=90, d=0.25, v=0.2, duty=0.3), dict(w="noise", f=2000, d=0.1, v=0.12, at=0)],
    "boss_hit": [dict(w="square", f=392, f2=330, d=0.08, v=0.24, duty=0.3), dict(w="tri", f=196, f2=150, d=0.14, v=0.3, at=0)],
    "boss_shell": [dict(w="square", f=880, f2=860, d=0.06, v=0.14, duty=0.4)],
    "boss_shot": [dict(w="saw", f=500, f2=250, d=0.12, v=0.12)],
    "boss_die": [dict(w="noise", f=1500, f2=50, d=1.2, v=0.5), dict(w="tri", f=220, f2=55, d=1.0, v=0.4, at=0)] +
                [dict(w="tri", f=f, d=0.1, v=0.3, at=1.0 + i * 0.1) for i, f in enumerate((523, 659, 784, 1047))],
    "boss_in": [dict(w="saw", f=110, f2=220, d=0.6, v=0.22, r="lin"), dict(w="square", f=440, d=0.1, v=0.14, at=0.6),
                dict(w="square", f=440, d=0.1, v=0.14, at=0.8)],
    "lost": [dict(w="tri", f=880, f2=660, d=0.1, v=0.3), dict(w="tri", f=660, f2=330, d=0.16, v=0.3),
             dict(w="tri", f=330, f2=110, d=0.4, v=0.32, r="lin")],
    "clear": [dict(w="tri", f=f, d=0.07, v=0.3) for f in (784, 988, 1175, 1568, 1175, 1568)] +
             [dict(w="tri", f=2093, d=0.45, v=0.32, vib=(6, 0.2), r="lin")],
    "over": [dict(w="tri", f=523, d=0.18, v=0.36), dict(w="tri", f=466, d=0.18, v=0.36), dict(w="tri", f=392, d=0.18, v=0.36),
             dict(w="tri", f=330, f2=262, d=0.7, v=0.38, r="lin")],
    "won": [dict(w="tri", f=f, d=0.12, v=0.32) for f in (523, 659, 784, 1047, 784, 1047, 1319)] +
           [dict(w="tri", f=1568, d=0.8, v=0.36, vib=(6, 0.25), r="lin"), dict(w="tri", f=784, d=0.8, v=0.24, at=0.84, r="lin")],
    "extra": _arp([1047, 1319, 1568, 2093], 0.05, 0.26, "square", 0.25),
    "menu": [dict(w="tri", f=660, d=0.025, v=0.2)],
    "start": [dict(w="tri", f=523, d=0.06, v=0.3), dict(w="tri", f=784, d=0.06, v=0.3), dict(w="tri", f=1047, d=0.16, v=0.3)],
    "pause": [dict(w="tri", f=523, f2=392, d=0.07, v=0.22)],
    "sound_on": [dict(w="tri", f=440, d=0.06, v=0.35), dict(w="tri", f=880, d=0.12, v=0.35)],
})


def help_lines(kitty=True):
    mode = (["Your terminal reports key releases: the tray moves exactly as",
             "long as you hold a direction."] if kitty else
            ["Classic keys: a tap moves the tray a little, holding moves it",
             "on, the other direction turns at once."])
    return ["SHATTERWICK - keys", "",
            "Left / Right  (A / D)     move the tray",
            "Space  (Up / W)           launch the spark, release a stuck",
            "                          spark, strike Flint bolts",
            "Esc / P                   pause menu (Q there: quit, M sound)",
            "?                         this help", ""] + mode + [
            "",
            "Where the spark meets the tray sets its angle: the tips",
            "send it out flat, the middle straight up. Panes broken",
            "before it returns build the combo (x2, x3 ...).",
            "Gifts:  B broader  T tallow (catch)  K kindle (3 sparks)",
            "        N needleflame  F flint  L lull  H hearth  + life",
            "Dark capsules are trouble: P pinch  G gust  S soot.",
            "Extra spark at %d points, then every %d." % (EXTRA_FIRST, EXTRA_EVERY), "",
            "Auto mode: the game plays itself (Space pause, +/- speed,",
            "Esc stop), from the district chosen in World select."]


# =============================================================================================
# Panes and halls
# =============================================================================================
def fold(x, lo, hi):
    """x mirrored back into [lo, hi] as often as it takes (a spark bouncing between two walls)."""
    w = hi - lo
    if w <= 0:
        return lo
    u = (x - lo) % (2 * w)
    return lo + (u if u <= w else 2 * w - u)


class Brick:
    __slots__ = ("kind", "c", "r", "x", "y", "hp", "maxhp", "color", "vx", "flash", "seed")

    def __init__(self, kind, c, r, color, hp=1, vx=0.0):
        self.kind, self.c, self.r, self.color = kind, c, r, color
        self.x, self.y = c * 2.0, GY + r
        self.hp = self.maxhp = hp
        self.vx = vx
        self.flash = 0.0
        self.seed = c * 31 + r * 7

    @property
    def req(self):
        return self.kind != "iron"


class Board:
    """The panes of one hall: a grid of fixed panes plus the sliding ones."""

    def __init__(self, rows, world):
        self.world = world
        pal = WORLDS[world]["panes"]
        self.grid = [[None] * COLS for _ in range(ROWS)]
        self.movers = []
        self.regrow = []         # [seconds left, c, r, colour]
        for r, line in enumerate(rows[:ROWS]):
            for c, ch in enumerate(line[:COLS]):
                b = None
                if ch in "abcdef":
                    b = Brick("norm", c, r, pal["abcdef".index(ch)])
                elif ch in "23":
                    b = Brick("tough", c, r, pal[(r + 2) % 6], hp=int(ch))
                elif ch == "#":
                    b = Brick("iron", c, r, (92, 98, 112))
                elif ch == "*":
                    b = Brick("blast", c, r, (186, 44, 32))
                elif ch == "$":
                    b = Brick("drop", c, r, (232, 180, 70))
                elif ch == "%":
                    b = Brick("regen", c, r, WORLDS[world]["regen"])
                elif ch in "<>":
                    self.movers.append(Brick("move", c, r, pal[r % 6], vx=(2.4 + 0.3 * world) * (1 if ch == ">" else -1)))
                if b:
                    self.grid[r][c] = b
        self.count()

    def count(self):
        alive = [b for row in self.grid for b in row if b] + self.movers
        self.required = sum(1 for b in alive if b.req)
        self.nonregen = sum(1 for b in alive if b.req and b.kind != "regen")

    def solid(self, c, r):
        return 0 <= c < COLS and 0 <= r < ROWS and self.grid[r][c] is not None

    def bricks(self):
        for row in self.grid:
            for b in row:
                if b:
                    yield b
        for b in self.movers:
            yield b

    def remove(self, b):
        if b.kind == "move":
            if b in self.movers:
                self.movers.remove(b)
        elif self.grid[b.r][b.c] is b:
            self.grid[b.r][b.c] = None
        else:
            return False
        if b.req:
            self.required -= 1
            if b.kind != "regen":
                self.nonregen -= 1
        return True

    def add(self, b):
        self.grid[b.r][b.c] = b
        self.required += 1

    def move(self, dt):
        for m in self.movers:
            nx = m.x + m.vx * dt
            blocked = nx < 0 or nx + 2.0 > FW
            if not blocked:
                row = self.grid[m.r]
                c0, c1 = int(nx // 2), int((nx + 2.0 - 1e-6) // 2)
                blocked = any(0 <= c < COLS and row[c] is not None for c in (c0, c1))
            if not blocked:
                for o in self.movers:
                    if o is not m and o.r == m.r and abs(o.x - nx) < 2.0 and (o.x - m.x) * m.vx > 0:
                        blocked = True
                        break
            if blocked:
                m.vx = -m.vx
            else:
                m.x = nx


def reachable(rows):
    """Every pane that must break can be reached through cells that are not iron (the row above the grid and the
    open space below it count as open)."""
    h = len(rows)
    grid = [list(r.ljust(COLS, ".")) for r in rows]
    seen = set()
    todo = [(c, h) for c in range(COLS)] + [(c, -1) for c in range(COLS)]
    while todo:
        c, r = todo.pop()
        if (c, r) in seen:
            continue
        seen.add((c, r))
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nc, nr = c + dc, r + dr
            if 0 <= nc < COLS and -1 <= nr <= h and (nc, nr) not in seen:
                if nr in (-1, h) or grid[nr][nc] != "#":
                    todo.append((nc, nr))
    return [(c, r) for r in range(h) for c in range(COLS) if grid[r][c] not in ".#" and (c, r) not in seen]


def gen_endless(depth, rnd):
    """A new hall for Endless mode: a mirrored pattern whose pane mix gets harsher the deeper you go; every
    fifth hall is the district's keeper, tougher on every round."""
    world = (depth // 5) % 5
    loop = depth // 25
    if depth % 5 == 4:
        w, name, boss, rows = LEVELS[world * 5 + 4]
        return dict(world=w, name=name, boss=boss, rows=rows, hp=int(BOSS_HP[boss] * (1 + 0.3 * loop + 0.06 * (depth // 5))))
    for _ in range(30):
        n = rnd.randint(5, min(ROWS - 1, 6 + depth // 4))
        pat = rnd.choice(("stripes", "checker", "diamond", "pyramid", "columns", "frame", "waves", "scatter"))
        half = []
        for r in range(n):
            line = []
            for c in range(7):
                on = {"stripes": r % 2 == 0 or rnd.random() < 0.3,
                      "checker": (r + c) % 2 == 0,
                      "diamond": abs(c - 6) + abs(r - n // 2) <= n // 2 + 2,
                      "pyramid": c >= 6 - r,
                      "columns": c % 2 == 1 or r == 0,
                      "frame": r in (0, n - 1) or c in (1, 6) or rnd.random() < 0.2,
                      "waves": (r + int(2 * math.sin(c * 0.9))) % 3 != 0,
                      "scatter": rnd.random() < 0.55}[pat]
                if not on:
                    line.append(".")
                    continue
                x = rnd.random()
                d = depth
                if x < min(0.07, 0.006 * d):
                    ch = "#"
                elif x < min(0.07, 0.006 * d) + min(0.24, 0.04 + 0.016 * d):
                    ch = "3" if d > 8 and rnd.random() < 0.4 else "2"
                elif x < 0.40 and d > 1 and rnd.random() < 0.18:
                    ch = "*"
                elif x < 0.46 and rnd.random() < 0.22:
                    ch = "$"
                elif x < 0.52 and d > 5 and rnd.random() < 0.3:
                    ch = "%"
                else:
                    ch = "abcdef"[(r + (c // 3)) % 6]
                line.append(ch)
            half.append(line)
        rows = ["".join(l[:6] + [l[6]] + l[5::-1]) for l in half]
        if depth > 1 and n < ROWS - 1:
            for _ in range(rnd.randint(1, 1 + min(2, depth // 7))):
                at = rnd.randint(1, len(rows))
                if len(rows) < ROWS:
                    rows.insert(at, (">" + "." * 12) if rnd.random() < 0.5 else ("." * 12 + "<"))
        for (c, r) in reachable(rows):
            rows[r] = rows[r][:c] + "a" + rows[r][c + 1:]
        while True:     # iron that seals something away turns to glass
            bad = reachable(rows)
            if not bad:
                break
            c, r = bad[0]
            for dc, dr in ((0, 1), (1, 0), (-1, 0), (0, -1)):
                nc, nr = c + dc, r + dr
                if 0 <= nr < len(rows) and 0 <= nc < COLS and rows[nr][nc] == "#":
                    rows[nr] = rows[nr][:nc] + "b" + rows[nr][nc + 1:]
                    break
            else:
                break
        need = sum(1 for r in rows for ch in r if ch not in ".#")
        if need >= 10:
            break
    adj, noun = ENDLESS_WORDS[world]
    return dict(world=world, name="%s %s" % (rnd.choice(adj), rnd.choice(noun)), boss=None, rows=rows, hp=0)


def level_spec(i):
    w, name, boss, rows = LEVELS[i]
    return dict(world=w, name=name, boss=boss, rows=rows, hp=BOSS_HP.get(boss, 0))


# =============================================================================================
# Things in the hall
# =============================================================================================
class Ball:
    __slots__ = ("x", "y", "dx", "dy", "sp", "stuck", "hold", "trail", "idle")

    def __init__(self, x, y, dx=0.0, dy=-1.0, sp=11.0):
        self.x, self.y, self.dx, self.dy, self.sp = x, y, dx, dy, sp
        self.stuck = None        # offset from the tray's middle while it sits on the tray
        self.hold = 0.0
        self.trail = []
        self.idle = 0.0          # seconds since it last broke something or touched the tray


class Cap:
    __slots__ = ("kind", "x", "y", "t")

    def __init__(self, kind, x, y):
        self.kind, self.x, self.y, self.t = kind, x, y, 0.0


class Enemy:
    __slots__ = ("kind", "x", "y", "vx", "vy", "t", "seed", "enter")

    def __init__(self, kind, x, rnd):
        self.kind, self.x, self.y = kind, x, -0.8
        self.vx, self.vy = rnd.choice((-1, 1)) * rnd.uniform(1.2, 2.4), 2.2
        self.t = 0.0
        self.seed = rnd.random() * 10
        self.enter = True


class Shot:
    """Something a keeper throws at the tray: a hit stuns the tray for a moment."""
    __slots__ = ("kind", "x", "y", "vx", "vy", "t")

    def __init__(self, kind, x, y, vx, vy):
        self.kind, self.x, self.y, self.vx, self.vy, self.t = kind, x, y, vx, vy, 0.0


class Boss:
    def __init__(self, kind, hp):
        self.kind, self.hp, self.maxhp = kind, hp, hp
        self.t = 0.0
        self.x, self.y = 13.0, -4.0
        self.inv = 0.0
        self.flash = 0.0
        self.dead = False
        self.dead_t = 0.0
        self.atk = 3.0
        self.intro = 1.6
        self.open = 0.0
        self.warn = 0.0
        self.shields = [[i * math.pi / 3, 2, 0.0] for i in range(6)] if kind == "bellows" else []

    def pos(self, t):
        k = self.kind
        if k == "bramble":
            return 13 + 7 * math.sin(0.33 * t), 4.6 + 0.4 * math.sin(0.9 * t)
        if k == "clam":
            return 13 + 6.0 * math.sin(0.22 * t), 4.4
        if k == "pendulum":
            a = 0.95 * math.sin(1.0 * t)
            return 13 + 8 * math.sin(a), -1.5 + 8 * math.cos(a)
        if k == "owl":
            return 13 + 8 * math.sin(0.38 * t), 4.6 + 1.3 * math.sin(0.76 * t)
        return 13 + 2 * math.sin(0.4 * t), 5.5 + 0.6 * math.sin(0.8 * t)

    @property
    def radius(self):
        return {"bramble": 2.0, "clam": 2.3, "pendulum": 1.7, "owl": 1.9, "bellows": 1.6}[self.kind]

    def vulnerable(self):
        if self.dead or self.intro > 0 or self.inv > 0:
            return False
        return self.kind != "clam" or self.open > 0.6

    def shapes(self):
        """Circles the spark bounces off: (x, y, radius, tag); tag 'core' takes damage, 'shell' does not,
        an int is one of the Bellows Heart's shield plates."""
        if self.dead:
            return []
        x, y = self.x, self.y
        if self.kind == "clam":
            if self.open > 0.6:
                return [(x, y + 0.5, 1.3, "core"), (x, y - 1.6, 1.6, "shell"), (x - 2.5, y + 1.1, 0.7, "shell"),
                        (x + 2.5, y + 1.1, 0.7, "shell")]
            return [(x, y, 2.3, "shell")]
        out = [(x, y, self.radius, "core" if not (self.kind == "owl" and self.inv > 0) else "shell")]
        for i, sh in enumerate(self.shields):
            if sh[1] > 0:
                a = sh[0] + self.t * 0.9
                out.append((x + 3.3 * math.cos(a), y + 3.3 * math.sin(a), 0.85, i))
        return out


# =============================================================================================
# The game
# =============================================================================================
class Game:
    def __init__(self, mode="campaign", level=0, seed=None, quiet=False, demo=False, lives=3):
        self.rnd = random.Random(seed)
        self.mode, self.demo = mode, demo
        self.quiet = quiet or demo
        self.score = 0
        self.lives = lives
        self.level_i = level              # campaign: index into LEVELS; endless: the depth
        self.first_level = level
        self.next_extra = EXTRA_FIRST
        self.hi = 0 if demo else (load_scores().get(GAME, {}).get(mode) or 0)
        self.over = self.won = self.paused = self.help = False
        self.clock = 0.0
        self.acc = 0.0
        self.shake = 0.0
        self.deaths = 0
        self.broken = 0
        self.best_chain = 0
        self.halls = 0
        self.parts, self.floats, self.rings = [], [], []
        self.start_level()

    # --- set-up ----------------------------------------------------------------------------------
    def snd(self, name, vol=1.0, gap=0.04):
        if not self.quiet:
            SND.play(name, vol, gap)

    def start_level(self):
        if self.mode == "endless":
            self.spec = gen_endless(self.level_i, random.Random(self.level_i * 7919 + 17))
        else:
            self.spec = level_spec(self.level_i)
        self.world = self.spec["world"]
        self.board = Board(self.spec["rows"], self.world)
        self.boss = Boss(self.spec["boss"], self.spec["hp"]) if self.spec["boss"] else None
        self.caps, self.bolts, self.shots, self.enemies = [], [], [], []
        self.blasts = []
        self.level_t = 0.0
        self.enemy_t = 9.0
        self.chain = 0
        self.tally = None
        if self.boss:
            self.snd("boss_in")
        self.new_life()

    def new_life(self):
        self.powers = {}
        self.px, self.pv = FW / 2, 0.0
        self.pw_draw = PW_NORMAL
        self.stun = 0.0
        self.bolt_cd = 0.0
        self.chain = 0
        b = Ball(self.px, PY - BALL_R, sp=self.target_speed())
        b.stuck = self.rnd.uniform(-0.5, 0.5)
        self.balls = [b]
        self.caps, self.shots, self.bolts = [], [], []
        self.state, self.state_t = "ready", 0.0

    # --- derived values --------------------------------------------------------------------------
    @property
    def pw(self):
        return PW_WIDE if "wide" in self.powers else PW_NARROW if "narrow" in self.powers else PW_NORMAL

    @property
    def mult(self):
        return 1 + min(7, self.chain // 5)

    def paddle_speed(self):
        return PADDLE_V * (0.5 if "heavy" in self.powers else 1.0)

    def target_speed(self):
        d = min(self.level_i, 40)
        base = 11.0 + (0.12 if self.mode == "endless" else 0.1) * d + min(5.5, getattr(self, "level_t", 0.0) / 14)
        return base * (0.7 if "slow" in self.powers else 1.3 if "fast" in self.powers else 1.0)

    def label(self):
        if self.mode == "endless":
            return "HALL %d" % (self.level_i + 1)
        return "%d-%d" % (self.world + 1, self.level_i % 5 + 1)

    # --- scoring and effects ---------------------------------------------------------------------
    def add(self, pts, x=None, y=None, col=(255, 236, 150)):
        self.score += pts
        if x is not None and pts:
            self.floats.append([x, y, "%d" % pts, 0.0, col])
            if len(self.floats) > 14:
                del self.floats[0]
        while self.score >= self.next_extra:
            self.next_extra += EXTRA_EVERY
            self.lives += 1
            self.snd("extra")
            self.floats.append([self.px, PY - 1.5, "EXTRA SPARK", -0.4, (255, 240, 200)])

    def burst(self, x, y, n, cols, spd=6.0, life=0.7, grav=18.0, up=2.0):
        r = self.rnd
        for _ in range(n):
            a = r.uniform(0, 2 * math.pi)
            v = r.uniform(0.3, 1.0) * spd
            self.parts.append([x, y, math.cos(a) * v, math.sin(a) * v - up, 0.0, life * r.uniform(0.6, 1.2),
                               r.choice(cols), grav])
        if len(self.parts) > 420:
            del self.parts[:len(self.parts) - 420]

    # --- input & time ----------------------------------------------------------------------------
    def update(self, dt, inp):
        """Advance by dt seconds. inp: (dx, fire pressed, fire held) or a callable returning it per physics step."""
        if self.paused or self.over:
            return
        self.acc += min(dt, 0.1)
        first = True
        while self.acc >= DT:
            self.acc -= DT
            i = inp() if callable(inp) else (inp if first else (inp[0], False, inp[2]))
            first = False
            self.step(i)
            if self.over:
                break

    def step(self, inp):
        self.clock += DT
        self.state_t += DT
        self.shake = max(0.0, self.shake - DT)
        self.fx_step()
        st = self.state
        if st == "ready":
            self.paddle_step(inp)
            self.ball_follow()
            if self.boss:
                self.boss_step(intro_only=True)
            if inp[1] or self.state_t > 10.0:
                self.launch_all()
                self.state, self.state_t = "play", 0.0
        elif st == "play":
            self.play_step(inp)
        elif st == "lost":
            if self.state_t > 1.5:
                if self.lives <= 0:
                    self.state, self.over = "over", True
                    self.snd("over")
                else:
                    self.new_life()
        elif st == "clear":
            self.paddle_step((0, False, False))
            if self.state_t > 2.8:
                self.next_level()

    def next_level(self):
        self.halls += 1
        self.level_i += 1
        if self.mode == "campaign" and self.level_i >= len(LEVELS):
            self.level_i = len(LEVELS) - 1
            self.state, self.over, self.won = "won", True, True
            self.add(self.lives * 5000)
            self.snd("won")
            return
        lives = self.lives
        self.start_level()
        self.lives = lives

    def fx_step(self):
        keep = []
        for p in self.parts:
            p[4] += DT
            if p[4] < p[5]:
                p[2] *= 0.985
                p[3] += p[7] * DT
                p[0] += p[2] * DT
                p[1] += p[3] * DT
                keep.append(p)
        self.parts = keep
        for f in self.floats:
            f[3] += DT
            f[1] -= 1.2 * DT
        self.floats = [f for f in self.floats if f[3] < 0.9]
        for r in self.rings:
            r[2] += DT
        self.rings = [r for r in self.rings if r[2] < r[3]]

    # --- the tray ---------------------------------------------------------------------------------
    def paddle_step(self, inp):
        dx = inp[0]
        if self.stun > 0:
            self.stun -= DT
            dx = 0
            self.pv = 0.0
        vmax = self.paddle_speed()
        want = clamp(dx, -1.0, 1.0) * vmax
        acc = 260.0 if want * self.pv >= 0 and abs(want) > abs(self.pv) else 420.0
        if self.pv < want:
            self.pv = min(want, self.pv + acc * DT)
        else:
            self.pv = max(want, self.pv - acc * DT)
        half = self.pw / 2
        self.px += self.pv * DT
        if self.px < half:
            self.px, self.pv = half, 0.0
        elif self.px > FW - half:
            self.px, self.pv = FW - half, 0.0
        self.pw_draw += (self.pw - self.pw_draw) * min(1.0, 10 * DT)

    def ball_follow(self):
        half = self.pw / 2
        for b in self.balls:
            if b.stuck is not None:
                b.stuck = clamp(b.stuck, -half + 0.2, half - 0.2)
                b.x, b.y = self.px + b.stuck, PY - BALL_R
                b.trail = []

    def launch(self, b):
        u = clamp(b.stuck / (self.pw / 2), -1, 1)
        a = u * MAX_ANG * 0.85
        b.dx, b.dy = math.sin(a), -math.cos(a)
        b.stuck = None
        b.idle = 0.0
        self.norm(b)

    def launch_all(self):
        n = 0
        for b in self.balls:
            if b.stuck is not None:
                self.launch(b)
                n += 1
        if n:
            self.snd("launch")

    # --- one physics step of play ----------------------------------------------------------------
    def play_step(self, inp):
        self.level_t += DT
        self.paddle_step(inp)
        for k in list(self.powers):
            if POWERS[k][4]:
                self.powers[k] -= DT
                if self.powers[k] <= 0:
                    del self.powers[k]
        self.board.move(DT)
        for b in self.board.bricks():
            if b.flash > 0:
                b.flash -= DT
        self.regrow_step()
        self.blast_step()
        # fire: release stuck sparks, strike flint
        self.bolt_cd -= DT
        if inp[1] and any(b.stuck is not None for b in self.balls):
            self.launch_all()
        elif "laser" in self.powers and (inp[1] or inp[2]) and self.bolt_cd <= 0:
            self.bolt_cd = 0.3
            half = self.pw / 2
            self.bolts += [[self.px - half + 0.35, PY - 0.2], [self.px + half - 0.35, PY - 0.2]]
            self.snd("laser", 0.7)
        tgt = self.target_speed()
        self.ball_follow()
        alive = []
        for b in self.balls:
            if b.stuck is not None:
                b.hold += DT
                if b.hold > 2.5:
                    self.launch(b)
                    self.snd("launch", 0.6)
                alive.append(b)
                continue
            b.sp += (tgt - b.sp) * min(1.0, 2.0 * DT)
            b.idle += DT
            if self.move_ball(b, DT):
                b.trail.append((b.x, b.y))
                if len(b.trail) > 7:
                    del b.trail[0]
                alive.append(b)
        self.balls = alive
        self.caps_step()
        self.bolts_step()
        self.enemies_step()
        if self.boss:
            self.boss_step()
        self.shots_step()
        if self.chain > self.best_chain:
            self.best_chain = self.chain
        if not self.balls:
            self.lose_life()
            return
        done = (self.boss.dead and self.boss.dead_t > 2.2) if self.boss else (self.board.required == 0 and not self.board.regrow)
        if done:
            self.level_clear()

    def lose_life(self):
        self.deaths += 1
        if not self.demo:
            self.lives -= 1
        self.state, self.state_t = "lost", 0.0
        self.powers = {}
        self.snd("lost")
        self.burst(self.px, PY, 24, [(255, 200, 120), (255, 120, 60), (200, 200, 220)], 7, 0.9)

    def level_clear(self):
        bonus = 0 if self.boss else 1500 + 250 * self.world
        self.tally = (bonus, self.level_t)
        self.add(bonus)
        self.state, self.state_t = "clear", 0.0
        self.balls = []
        self.caps, self.shots, self.bolts = [], [], []
        for e in self.enemies:
            self.burst(e.x, e.y, 8, [WORLDS[self.world]["accent"]], 4, 0.5)
        self.enemies = []
        self.snd("clear")

    # --- the spark ---------------------------------------------------------------------------------
    def norm(self, b):
        m = math.hypot(b.dx, b.dy) or 1.0
        dx, dy = b.dx / m, b.dy / m
        if abs(dy) < MIN_VY:
            dy = MIN_VY if dy >= 0 else -MIN_VY
            dx = math.copysign(math.sqrt(1 - dy * dy), dx if dx else 1.0)
        b.dx, b.dy = dx, dy

    def nudge(self, b):
        """A spark that has not touched anything breakable for long gets a small random kick (no endless loops)."""
        if b.idle > 9.0:
            a = math.radians(self.rnd.uniform(6, 14)) * self.rnd.choice((-1, 1))
            ca, sa = math.cos(a), math.sin(a)
            b.dx, b.dy = b.dx * ca - b.dy * sa, b.dx * sa + b.dy * ca
            b.idle = 6.0
            self.norm(b)

    def move_ball(self, b, dt):
        """Move one spark through its sub-steps. False when it has fallen out of the hall."""
        n = max(1, int(math.ceil(b.sp * dt / SUB)))
        h = dt / n
        r = BALL_R
        for _ in range(n):
            b.x += b.dx * b.sp * h
            b.y += b.dy * b.sp * h
            if b.x < r:
                b.x = r
                if b.dx < 0:
                    b.dx = -b.dx
                    self.nudge(b)
            elif b.x > FW - r:
                b.x = FW - r
                if b.dx > 0:
                    b.dx = -b.dx
                    self.nudge(b)
            if b.y < r:
                b.y = r
                if b.dy < 0:
                    b.dy = -b.dy
                    self.nudge(b)
            if b.y - r < GY + ROWS:
                self.hit_grid(b)
                if self.board.movers:
                    self.hit_movers(b)
            if self.enemies:
                self.hit_enemies(b)
            if self.boss and not self.boss.dead:
                self.hit_boss(b)
            if b.dy > 0 and b.y + r >= PY and b.y <= PY + PTH * 0.6 and abs(b.x - self.px) <= self.pw / 2 + r * 0.7:
                self.hit_paddle(b)
                if b.stuck is not None:
                    return True
            if "barrier" in self.powers and b.dy > 0 and b.y + r >= BAR_Y:
                b.y = BAR_Y - r
                b.dy = -b.dy
                self.norm(b)
                self.snd("save")
                self.burst(b.x, BAR_Y, 6, [(255, 180, 90), (255, 230, 160)], 4, 0.4)
            if b.y - r > FH + 0.3:
                return False
        return True

    def hit_paddle(self, b):
        half = self.pw / 2
        u = clamp((b.x - self.px) / half, -1, 1)
        a = u * MAX_ANG
        b.dx, b.dy = math.sin(a), -math.cos(a)
        b.y = PY - BALL_R
        b.idle = 0.0
        self.chain = 0
        self.norm(b)
        if "catch" in self.powers:
            b.stuck = clamp(b.x - self.px, -half + 0.2, half - 0.2)
            b.hold = 0.0
            self.snd("catch")
        else:
            self.snd("pad", 0.8)
        self.burst(b.x, PY, 3, [(255, 230, 160), (255, 190, 90)], 4, 0.25, grav=10)

    def reflect(self, b, nx, ny):
        d = b.dx * nx + b.dy * ny
        if d < 0:
            b.dx -= 2 * d * nx
            b.dy -= 2 * d * ny
        self.norm(b)

    def pierce(self, b, br):
        return "pierce" in self.powers and br.kind != "iron"

    def hit_grid(self, b):
        r = BALL_R
        grid = self.board.grid
        done = set()
        for _ in range(4):
            c0, c1 = max(0, int((b.x - r) // 2)), min(COLS - 1, int((b.x + r) // 2))
            r0, r1 = max(0, int(math.floor(b.y - r - GY))), min(ROWS - 1, int(math.floor(b.y + r - GY)))
            best = None
            for rr in range(r0, r1 + 1):
                row = grid[rr]
                by0 = GY + rr
                for cc in range(c0, c1 + 1):
                    br = row[cc]
                    if br is None or br in done:
                        continue
                    bx0 = cc * 2.0
                    nx = bx0 if b.x < bx0 else bx0 + 2.0 if b.x > bx0 + 2.0 else b.x
                    ny = by0 if b.y < by0 else by0 + 1.0 if b.y > by0 + 1.0 else b.y
                    dx, dy = b.x - nx, b.y - ny
                    d2 = dx * dx + dy * dy
                    if d2 >= r * r:
                        continue
                    pen = r - math.sqrt(d2)
                    if best is None or pen > best[0]:
                        best = (pen, br, dx, dy, cc, rr)
            if best is None:
                return
            pen, br, dx, dy, cc, rr = best
            done.add(br)
            if self.pierce(b, br):
                self.damage(br, 99, "pierce")
                continue
            self.resolve_box(b, br.x, br.y, 2.0, 1.0, dx, dy, lambda c, rr_: self.board.solid(c, rr_), cc, rr)
            self.damage(br, 1, "ball")
            if br.kind != "iron":
                b.idle = 0.0

    def resolve_box(self, b, bx0, by0, w, h, dx, dy, solid=None, cc=0, rr=0):
        """Push the spark out of a box it overlaps and bounce it. A corner between two neighbouring panes counts
        as the flat face they make together."""
        r = BALL_R
        if dx == 0 and dy == 0:      # the middle is inside: out the shortest way
            opts = [(b.x - bx0, -1, 0), (bx0 + w - b.x, 1, 0), (b.y - by0, 0, -1), (by0 + h - b.y, 0, 1)]
            d, sx, sy = min(opts)
            if sx:
                b.x += sx * (d + r)
                b.dx = abs(b.dx) * sx
            else:
                b.y += sy * (d + r)
                b.dy = abs(b.dy) * sy
            self.norm(b)
            return
        sx = (dx > 0) - (dx < 0)
        sy = (dy > 0) - (dy < 0)
        if sx and sy and solid is not None:
            nbx, nby = solid(cc + sx, rr), solid(cc, rr + sy)
            if nbx and nby:
                if b.dx * sx < 0:
                    b.dx = -b.dx
                if b.dy * sy < 0:
                    b.dy = -b.dy
                b.x = (bx0 + w if sx > 0 else bx0) + sx * r
                b.y = (by0 + h if sy > 0 else by0) + sy * r
                self.norm(b)
                return
            if nbx:
                sx = 0
            elif nby:
                sy = 0
        if sx and sy:
            d = math.hypot(dx, dy)
            nx, ny = dx / d, dy / d
            b.x += nx * (r - d)
            b.y += ny * (r - d)
            self.reflect(b, nx, ny)
        elif sx:
            b.x = (bx0 + w if sx > 0 else bx0) + sx * r
            self.reflect(b, sx, 0)
        else:
            b.y = (by0 + h if sy > 0 else by0) + sy * r
            self.reflect(b, 0, sy)

    def hit_movers(self, b):
        r = BALL_R
        for m in list(self.board.movers):
            if abs(b.y - (m.y + 0.5)) > 0.5 + r or abs(b.x - (m.x + 1.0)) > 1.0 + r:
                continue
            nx = clamp(b.x, m.x, m.x + 2.0)
            ny = clamp(b.y, m.y, m.y + 1.0)
            dx, dy = b.x - nx, b.y - ny
            if dx * dx + dy * dy >= r * r:
                continue
            if self.pierce(b, m):
                self.damage(m, 99, "pierce")
                continue
            self.resolve_box(b, m.x, m.y, 2.0, 1.0, dx, dy)
            self.damage(m, 1, "ball")
            b.idle = 0.0

    def hit_enemies(self, b):
        rr = BALL_R + ENEMY_R
        for e in self.enemies:
            dx, dy = b.x - e.x, b.y - e.y
            d2 = dx * dx + dy * dy
            if d2 < rr * rr:
                d = math.sqrt(d2) or 1e-6
                nx, ny = dx / d, dy / d
                b.x, b.y = e.x + nx * rr, e.y + ny * rr
                self.reflect(b, nx, ny)
                self.pop_enemy(e)
                return

    def hit_boss(self, b):
        bo = self.boss
        for (cx, cy, rad, tag) in bo.shapes():
            rr = rad + BALL_R
            dx, dy = b.x - cx, b.y - cy
            d2 = dx * dx + dy * dy
            if d2 >= rr * rr:
                continue
            d = math.sqrt(d2) or 1e-6
            nx, ny = dx / d, dy / d
            b.x, b.y = cx + nx * rr, cy + ny * rr
            self.reflect(b, nx, ny)
            b.idle = 0.0
            if tag == "core":
                self.boss_hit(b.x, b.y)
            elif tag == "shell":
                self.snd("boss_shell", 0.8)
                if bo.kind == "clam" and bo.open < 0.1:
                    p = getattr(bo, "ct", 0.0) % 6.0
                    if p < 2.6:              # knocked: it flinches open
                        bo.ct = getattr(bo, "ct", 0.0) + (2.6 - p)
                self.burst(b.x, b.y, 4, [(230, 230, 240)], 3, 0.25)
            else:
                sh = bo.shields[tag]
                sh[1] -= 1
                self.snd("clang")
                if sh[1] <= 0:
                    sh[2] = 8.0
                    self.add(250, cx, cy)
                    self.burst(cx, cy, 12, [(150, 140, 160), (255, 160, 80)], 5, 0.6)
            return

    # --- breaking things -------------------------------------------------------------------------
    def damage(self, br, power=1, cause="ball"):
        if br.kind == "iron":
            if cause != "blast":
                self.snd("clang", 0.7)
                self.burst(br.x + 1, br.y + 0.5, 3, [(220, 226, 240), (255, 220, 150)], 4, 0.25, grav=6)
            return False
        br.hp -= power
        br.flash = 0.12
        if br.hp > 0:
            self.snd("crack")
            self.add(10)
            self.burst(br.x + 1, br.y + 0.5, 4, [mix(br.color, WHITE, 0.6)], 3, 0.3)
            return False
        self.destroy(br, cause)
        return True

    def destroy(self, br, cause):
        if not self.board.remove(br):
            return
        self.chain += 1
        self.broken += 1
        pts = (BRICK_PTS[br.kind] + (br.maxhp - 1) * 40 + 10 * self.world) * self.mult
        cx, cy = br.x + 1.0, br.y + 0.5
        self.add(pts, cx, cy, (255, 236, 150) if self.mult < 2 else (255, 190, 120))
        self.snd("pane%d" % min(7, self.chain - 1), 0.9, 0.02)
        c = br.color
        self.burst(cx, cy, 10, [c, mix(c, WHITE, 0.5), shade(c, 0.6)], 6.5, 0.7)
        if br.kind == "blast":
            self.blasts.append([0.09, cx, cy])
        elif br.kind == "regen" and not self.withered():
            self.board.regrow.append([REGEN_T, br.c, br.r, br.color])
        if br.kind == "drop":
            self.drop(cx, cy, 1.0, kind_bias=0.3)
        elif cause != "blast" or self.rnd.random() < 0.5:
            self.drop(cx, cy, 0.15 if br.kind == "tough" else 0.09)
        for b in self.balls:
            b.idle = 0.0

    def withered(self):
        """Frost stops growing back once everything else is broken (or the keeper is beaten)."""
        if self.boss:
            return self.boss.dead
        return self.board.nonregen <= 0

    def regrow_step(self):
        rg = self.board.regrow
        if not rg:
            return
        if self.withered():
            for item in rg:
                self.burst(item[1] * 2 + 1, GY + item[2] + 0.5, 4, [item[3]], 2, 0.5)
            rg.clear()
            return
        for item in list(rg):
            item[0] -= DT
            if item[0] > 0:
                continue
            c, r = item[1], item[2]
            if self.board.grid[r][c] is not None:
                rg.remove(item)
                continue
            x0, y0 = c * 2.0, GY + r
            if any(x0 - BALL_R - 0.2 < b.x < x0 + 2 + BALL_R + 0.2 and y0 - BALL_R - 0.2 < b.y < y0 + 1 + BALL_R + 0.2
                   for b in self.balls):
                item[0] = 0.25
                continue
            rg.remove(item)
            nb = Brick("regen", c, r, item[3])
            self.board.add(nb)
            self.burst(x0 + 1, y0 + 0.5, 6, [mix(item[3], WHITE, 0.5)], 2.5, 0.5, grav=0)
            self.snd("regrow", 0.6)

    def blast_step(self):
        if not self.blasts:
            return
        pending, self.blasts = self.blasts, []
        for bl in pending:
            bl[0] -= DT
            if bl[0] > 0:
                self.blasts.append(bl)
                continue
            _, x, y = bl
            self.rings.append([x, y, 0.0, 0.35])
            self.burst(x, y, 18, [(255, 220, 120), (255, 140, 50), (220, 60, 30), (90, 80, 80)], 9, 0.7, grav=8)
            self.shake = max(self.shake, 0.25)
            self.snd("boom", 0.8, 0.06)
            c, r = int(x // 2), int(math.floor(y - GY))
            for rr in range(r - 1, r + 2):
                for cc in range(c - 1, c + 2):
                    if 0 <= rr < ROWS and 0 <= cc < COLS:
                        br = self.board.grid[rr][cc]
                        if br is not None and br.kind != "iron":
                            self.damage(br, 99, "blast")
            for m in list(self.board.movers):
                if abs(m.x + 1 - x) < 3.2 and abs(m.y + 0.5 - y) < 1.6:
                    self.damage(m, 99, "blast")
            for e in list(self.enemies):
                if math.hypot(e.x - x, e.y - y) < 2.8:
                    self.pop_enemy(e)

    # --- gifts -------------------------------------------------------------------------------------
    def drop(self, x, y, chance, kind_bias=1.0):
        if self.rnd.random() >= chance:
            return
        if chance < 1.0 and len(self.caps) >= 3:
            return
        bad = 0.55 + 0.15 * self.world
        kinds = list(POWERS)
        weights = [POWERS[k][5] * (1.0 if POWERS[k][3] else bad * kind_bias) for k in kinds]
        if self.mode == "campaign" and self.boss is None and self.board.required <= 3:
            weights = [w * (0.3 if k == "multi" else 1.0) for k, w in zip(kinds, weights)]
        k = self.rnd.choices(kinds, weights)[0]
        self.caps.append(Cap(k, clamp(x, 1.0, FW - 1.0), y))

    def caps_step(self):
        keep = []
        half = self.pw / 2
        for c in self.caps:
            c.t += DT
            c.y += CAP_VY * DT
            if PY - CAP_H / 2 <= c.y <= PY + PTH + CAP_H / 2 and abs(c.x - self.px) <= half + CAP_W / 2:
                self.apply(c.kind)
                continue
            if c.y < FH + 1:
                keep.append(c)
        self.caps = keep

    def apply(self, kind):
        letter, name, col, good, dur, _, text = POWERS[kind]
        if kind == "multi":
            new = []
            for b in self.balls:
                if b.stuck is not None:
                    self.launch(b)
                for da in (-0.38, 0.38):
                    ca, sa = math.cos(da), math.sin(da)
                    nb = Ball(b.x, b.y, b.dx * ca - b.dy * sa, b.dx * sa + b.dy * ca, b.sp)
                    self.norm(nb)
                    new.append(nb)
            self.balls += new[:max(0, 12 - len(self.balls))]
            self.snd("split")
        elif kind == "life":
            self.lives += 1
            self.snd("life")
        else:
            opp = OPPOSED.get(kind)
            if opp:
                self.powers.pop(opp, None)
            self.powers[kind] = dur
            if kind != "catch":
                for b in self.balls:
                    if b.stuck is not None and "catch" not in self.powers:
                        self.launch(b)
            self.snd("good" if good else "bad")
        if good:
            self.add(100)
        self.floats.append([self.px, PY - 1.4, name, -0.5, col if good else (255, 120, 110)])

    def bolts_step(self):
        keep = []
        grid = self.board.grid
        for bl in self.bolts:
            bl[1] -= BOLT_VY * DT
            x, y = bl
            hit = False
            for yy in (y, y + 0.28):
                r = int(math.floor(yy - GY))
                c = int(x // 2)
                if 0 <= r < ROWS and 0 <= c < COLS and grid[r][c] is not None:
                    self.damage(grid[r][c], 1, "bolt")
                    hit = True
                    break
            if not hit:
                for m in self.board.movers:
                    if m.x <= x <= m.x + 2 and m.y <= y <= m.y + 1.3:
                        self.damage(m, 1, "bolt")
                        hit = True
                        break
            if not hit:
                for e in self.enemies:
                    if abs(e.x - x) < ENEMY_R + 0.1 and abs(e.y - y) < ENEMY_R + 0.3:
                        self.pop_enemy(e)
                        hit = True
                        break
            if not hit and self.boss and not self.boss.dead:
                for (cx, cy, rad, tag) in self.boss.shapes():
                    if (x - cx) ** 2 + (y - cy) ** 2 < rad * rad:
                        if tag == "core":
                            self.boss_hit(x, y)
                        elif isinstance(tag, int):
                            sh = self.boss.shields[tag]
                            sh[1] -= 1
                            if sh[1] <= 0:
                                sh[2] = 8.0
                        hit = True
                        break
            if not hit:
                for s in self.shots:
                    if abs(s.x - x) < 0.6 and abs(s.y - y) < 0.7:
                        s.y = 99
                        hit = True
                        break
            if hit:
                self.burst(x, y, 3, [(180, 255, 255), (255, 255, 255)], 3, 0.2)
            elif y > -0.5:
                keep.append(bl)
        self.bolts = keep

    # --- creatures --------------------------------------------------------------------------------
    def enemies_step(self):
        if self.boss is None:
            self.enemy_t -= DT
            cap = 2 + (1 if self.world >= 2 else 0)
            if self.enemy_t <= 0:
                self.enemy_t = self.rnd.uniform(9, 15)
                if len(self.enemies) < cap:
                    self.enemies.append(Enemy(WORLDS[self.world]["enemy"], self.rnd.choice(HATCHES), self.rnd))
        for e in self.enemies:
            e.t += DT
            if e.enter:
                e.y += 2.2 * DT
                if e.y > 1.0:
                    e.enter = False
                continue
            k = e.kind
            t = e.t + e.seed
            if k == "moth":
                e.vx += math.sin(t * 1.7) * 6 * DT
                e.vy = math.sin(t * 2.3) * 2.0 + 0.4 * math.sin(t * 0.5)
            elif k == "jelly":
                ph = (t * 0.8) % 1.0
                e.vy = -2.4 if ph < 0.25 else 0.9
                e.vx += math.sin(t * 0.6) * 1.5 * DT
            elif k == "cog":
                if e.vy == 0 or abs(e.vy) < 1:
                    e.vy = 2.2
            elif k == "mote":
                e.vx = 3.0 if int(t / 1.2) % 2 else -3.0
                e.vy = math.sin(t * 1.4) * 1.6
            else:   # cinder: little hops
                e.vy += 7.0 * DT
                if e.vy > 3.5:
                    e.vy = -4.5
            e.vx = clamp(e.vx, -3.5, 3.5)
            e.x += e.vx * DT
            e.y += e.vy * DT
            if e.x < 1.0:
                e.x, e.vx = 1.0, abs(e.vx)
            elif e.x > FW - 1.0:
                e.x, e.vx = FW - 1.0, -abs(e.vx)
            if e.y < 1.0:
                e.y, e.vy = 1.0, abs(e.vy)
            elif e.y > 15.0:
                e.y, e.vy = 15.0, -abs(e.vy)

    def pop_enemy(self, e):
        if e not in self.enemies:
            return
        self.enemies.remove(e)
        self.add(150 * self.mult, e.x, e.y, (190, 255, 200))
        self.snd("pop")
        self.burst(e.x, e.y, 12, ENEMY_POP[e.kind], 5, 0.6, grav=4)

    # --- keepers --------------------------------------------------------------------------------
    def boss_step(self, intro_only=False):
        bo = self.boss
        bo.t += DT
        if bo.intro > 0:
            bo.intro -= DT
            tx, ty = bo.pos(0.0)
            k = max(0.0, bo.intro) / 1.6
            bo.x, bo.y = tx, ty - 10 * k * k
            if intro_only or bo.intro > 0:
                bo.t = 0.0
                return
        if intro_only:
            return
        if bo.dead:
            bo.dead_t += DT
            if bo.dead_t < 1.8 and self.rnd.random() < 0.35:
                a = self.rnd.uniform(0, 2 * math.pi)
                rr = self.rnd.uniform(0, bo.radius * 1.3)
                self.burst(bo.x + rr * math.cos(a), bo.y + rr * math.sin(a), 8,
                           [(255, 230, 160), (255, 150, 60), BOSS_COL[bo.kind]], 7, 0.6)
                self.shake = max(self.shake, 0.2)
            return
        bo.inv = max(0.0, bo.inv - DT)
        bo.flash = max(0.0, bo.flash - DT)
        bo.x, bo.y = bo.pos(bo.t)
        k = bo.kind
        if k == "clam":
            bo.ct = getattr(bo, "ct", 0.0) + DT
            p = bo.ct % 6.0
            bo.open = clamp((p - 2.8) / 0.4, 0, 1) if p < 5.6 else clamp((6.0 - p) / 0.4, 0, 1)
        for sh in bo.shields:
            if sh[1] <= 0:
                sh[2] -= DT
                if sh[2] <= 0:
                    sh[1] = 2
        bo.atk -= DT
        if k == "owl" and bo.atk < 0.6:
            bo.warn = 0.6 - max(0.0, bo.atk)
        if bo.atk <= 0:
            px = self.px
            if k == "bramble":
                self.shots.append(Shot("thorn", bo.x, bo.y + 2.0, clamp((px - bo.x) * 0.25, -2.2, 2.2), 6.0))
                bo.atk = self.rnd.uniform(2.6, 3.2)
            elif k == "clam":
                if bo.open > 0.5:
                    for vx in (-1.6, 0.0, 1.6):
                        self.shots.append(Shot("bubble", bo.x + vx, bo.y + 1.6, vx * 0.6, 3.6))
                    bo.atk = 3.0
                else:
                    bo.atk = 0.3
            elif k == "pendulum":
                self.shots.append(Shot("gear", bo.x, bo.y + 1.4, 0.0, 6.5))
                bo.atk = self.rnd.uniform(2.6, 3.2)
            elif k == "owl":
                self.shots.append(Shot("icicle", bo.x, bo.y + 1.8, 0.0, 10.0))
                bo.atk = self.rnd.uniform(2.0, 2.6)
                bo.warn = 0.0
            else:
                ang = math.atan2(PY - bo.y, px - bo.x)
                self.shots.append(Shot("ember", bo.x, bo.y + 1.0, math.cos(ang) * 7.5, math.sin(ang) * 7.5))
                bo.atk = self.rnd.uniform(1.7, 2.2)
            self.snd("boss_shot", 0.7)

    def boss_hit(self, x, y):
        bo = self.boss
        if not bo.vulnerable():
            self.snd("boss_shell", 0.8)
            return
        bo.hp -= 1
        bo.flash = 0.18
        bo.inv = 1.0 if bo.kind == "owl" else 0.35
        self.add(300 * self.mult, x, y, (255, 200, 140))
        self.chain += 1
        self.snd("boss_hit")
        self.shake = max(self.shake, 0.15)
        self.burst(x, y, 10, [BOSS_COL[bo.kind], (255, 240, 200)], 6, 0.5)
        if self.rnd.random() < 0.3:
            self.drop(bo.x, bo.y + bo.radius, 1.0, 0.5)
        if bo.hp <= 0:
            bo.dead = True
            bo.dead_t = 0.0
            self.shots = []
            self.add(8000 + 2000 * (self.level_i // 25), bo.x, bo.y, (255, 240, 160))
            self.snd("boss_die")
            self.shake = 0.6

    def shots_step(self):
        keep = []
        half = self.pw / 2
        for s in self.shots:
            s.t += DT
            if s.kind == "bubble":
                s.vx = math.sin(s.t * 3 + s.x) * 1.4
            s.x += s.vx * DT
            s.y += s.vy * DT
            if PY - 0.3 <= s.y <= PY + PTH + 0.2 and abs(s.x - self.px) <= half + 0.3:
                self.stun = 0.8
                self.snd("stun")
                self.burst(s.x, PY, 8, [(200, 220, 255), (255, 255, 255)], 4, 0.4)
                continue
            if s.y < FH + 1 and 0 <= s.x <= FW:
                keep.append(s)
        self.shots = keep


BOSS_COL = {"bramble": (206, 44, 76), "clam": (226, 186, 172), "pendulum": (212, 166, 72), "owl": (206, 220, 240),
            "bellows": (236, 96, 44)}
ENEMY_POP = {"moth": [(220, 200, 240), (180, 150, 210)], "jelly": [(150, 220, 255), (220, 160, 240)],
             "cog": [(200, 170, 100), (140, 120, 90)], "mote": [(230, 245, 255), (170, 210, 255)],
             "cinder": [(255, 160, 60), (255, 230, 120)]}


# =============================================================================================
# The autopilot: it sees what a player sees (sparks, panes, gifts, what keepers throw) and nothing more
# =============================================================================================
class Bot:
    CANDS = (-0.78, -0.6, -0.42, -0.24, -0.08, 0.08, 0.24, 0.42, 0.6, 0.78)

    def __init__(self, g, seed=None):
        self.g = g
        self.rnd = random.Random(seed)
        self.reset()

    def reset(self):
        self.plan = None
        self.plan_t = 0.0
        self.target = None
        self.wait = 0.0
        self.aim = None

    def predict(self, b):
        if b.stuck is not None or b.dy <= 0:
            return None
        vy = b.dy * b.sp
        t = (PY - BALL_R - b.y) / vy
        if t < 0:
            return None
        return t, fold(b.x + b.dx * b.sp * t, BALL_R, FW - BALL_R)

    def ray(self, x, y, dx, dy):
        """Where a spark sent off this way would first hit something worth hitting (a rough look)."""
        g = self.g
        grid = g.board.grid
        bo = g.boss
        shapes = bo.shapes() if bo and not bo.dead else []
        step = 0.3
        pen = 0.0
        for _ in range(110):
            x += dx * step
            y += dy * step
            if x < BALL_R:
                x, dx = 2 * BALL_R - x, -dx
            elif x > FW - BALL_R:
                x, dx = 2 * (FW - BALL_R) - x, -dx
            if y < BALL_R:
                y, dy = 2 * BALL_R - y, -dy
            if dy > 0 and y > GY + ROWS + 0.5:
                return 0.5 + pen
            for (cx, cy, rad, tag) in shapes:
                if (x - cx) ** 2 + (y - cy) ** 2 < (rad + BALL_R) ** 2:
                    if tag == "core" and bo.vulnerable():
                        return 14.0 + pen
                    if isinstance(tag, int):
                        return 5.0 + pen
                    return 1.0 + pen
            r = int(math.floor(y - GY))
            c = int(x // 2)
            if 0 <= r < ROWS and 0 <= c < COLS and grid[r][c] is not None:
                br = grid[r][c]
                if br.kind == "iron":
                    pen -= 1.5
                    py = y - dy * step
                    if int(math.floor(py - GY)) != r:
                        dy = -dy
                    else:
                        dx = -dx
                    continue
                v = 10.0 - (br.hp - 1) * 1.5 + (4 if br.kind == "blast" else 2 if br.kind == "drop" else 0)
                return v + pen
            for m in g.board.movers:
                if m.x <= x <= m.x + 2 and m.y <= y <= m.y + 1:
                    return 8.0 + pen
        return pen

    def bad_spots(self):
        """(x, time to reach the tray) of everything that should not land on it."""
        g = self.g
        out = []
        for c in g.caps:
            if not POWERS[c.kind][3]:
                out.append((c.x, (PY - c.y) / CAP_VY))
        for s in g.shots:
            if s.vy > 0:
                t = (PY - s.y) / s.vy
                out.append((s.x + s.vx * t, t))
        return out

    def __call__(self):
        g = self.g
        if g.state not in ("ready", "play"):
            return (0.0, False, False)
        half = g.pw / 2
        vmax = g.paddle_speed()
        fire = False
        self.plan_t -= DT
        stuck = [b for b in g.balls if b.stuck is not None]
        threats = []
        for b in g.balls:
            p = self.predict(b)
            if p:
                threats.append((p[0], p[1], b))
        threats.sort(key=lambda q: q[0])
        bad = self.bad_spots()
        tx = None
        if threats:
            t, x, b = threats[0]
            key = (id(b), round(x, 1), round(b.dx, 2))
            if self.plan is None or self.plan[0] != key or self.plan_t <= 0:
                best = None
                for u in self.CANDS:
                    cx = clamp(x - u * half, half, FW - half)
                    uu = clamp((x - cx) / half, -1, 1)
                    if abs(cx - g.px) > vmax * max(0.0, t - 0.06) + 0.25:
                        continue
                    a = uu * MAX_ANG
                    sc = self.ray(x, PY - BALL_R, math.sin(a), -math.cos(a))
                    sc -= abs(uu) * 0.6 + self.rnd.random() * 0.8
                    for (bx, bt) in bad:
                        if abs(bt - t) < 0.6 and abs(bx - cx) < half + 1.0:
                            sc -= 20
                    if len(threats) > 1:     # keep the next spark in reach too
                        t2, x2, _ = threats[1]
                        if abs(x2 - cx) - half > vmax * (t2 - t):
                            sc -= 6
                    if best is None or sc > best[0]:
                        best = (sc, cx)
                if best is None:
                    best = (0, clamp(x, half, FW - half))
                self.plan = (key, best[1])
                self.plan_t = 0.25
            tx = self.plan[1]
            # a good gift on the way, if there is time for it
            if t > 0.6:
                for c in g.caps:
                    if POWERS[c.kind][3]:
                        tc = (PY - c.y) / CAP_VY
                        if 0 < tc < t - 0.15 and abs(c.x - g.px) < vmax * tc and \
                                abs(c.x - tx) < vmax * (t - tc) - half:
                            tx = c.x
                            break
        elif stuck:
            b = stuck[0]
            if self.aim is None or self.plan_t <= 0:
                best = None
                off = b.stuck
                for i in range(19):
                    cx = half + (FW - 2 * half) * i / 18
                    x = cx + off
                    u = clamp(off / half, -1, 1)
                    a = u * MAX_ANG * 0.85
                    sc = self.ray(x, PY - BALL_R, math.sin(a), -math.cos(a)) - abs(cx - g.px) * 0.05
                    sc -= self.rnd.random() * 0.5
                    if best is None or sc > best[0]:
                        best = (sc, cx)
                self.aim = best[1]
                self.plan_t = 0.5
            tx = self.aim
            self.wait += DT
            if abs(tx - g.px) < 0.3 or self.wait > 1.5:
                fire = True
                self.wait = 0.0
                self.aim = None
        else:
            goods = [c for c in g.caps if POWERS[c.kind][3]]
            if goods:
                tx = min(goods, key=lambda c: -c.y).x
            elif g.balls:
                tx = min(g.balls, key=lambda b: -b.y).x
            else:
                tx = FW / 2
        if not threats and not stuck:
            for (bx, bt) in bad:
                if bt < 0.8 and abs(bx - tx) < half + 0.8:
                    tx = bx + (half + 1.2) * (1 if tx >= bx else -1)
        tx = clamp(tx, half, FW - half)
        if "laser" in g.powers and g.board.required:
            fire = fire or g.bolt_cd <= 0
        d = tx - g.px
        dx = 0.0 if abs(d) < 0.06 else clamp(d / 0.6, -1.0, 1.0)
        return (dx, fire, fire)


# =============================================================================================
# Drawing: one unit of the hall is s x s screen pixels (s grows with the window: finer, not bigger)
# =============================================================================================
def hsh(x, y, s=0):
    h = (x * 374761393 + y * 668265263 + s * 2147483647) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    return (h ^ (h >> 16)) & 0xFFFF


HUD_BG = (12, 10, 22)
HUD_FG = (210, 212, 232)
HUD_DIM = (140, 144, 178)
GOLD = (250, 214, 120)


def layout(cols, rows, hud=True):
    """(s, ox, oy, wall): pixels per unit, the hall's top-left pixel, the frame's thickness."""
    top = bot = 1 if hud else 0
    aw, ah = cols, (rows - top - bot) * 2
    s = min((aw - 2) / FW, (ah - 1) / FH)
    if s >= 2:
        s = int(s)
        wall = max(1, min(s // 2 + 1, ah - int(FH * s), (aw - int(FW * s)) // 2))
    else:
        s = max(0.3, min(aw / FW, ah / FH))
        wall = 0
    fw, fh = int(round(FW * s)), int(round(FH * s))
    ox = (cols - fw) // 2
    oy = top * 2 + (ah - fh - wall) // 2 + wall
    return s, ox, oy, wall


class View:
    def __init__(self, cv, s, ox, oy):
        self.cv, self.s, self.ox, self.oy = cv, s, ox, oy

    def X(self, x):
        return self.ox + int(math.floor(x * self.s + 0.5))

    def Y(self, y):
        return self.oy + int(math.floor(y * self.s + 0.5))

    def r(self, x, y, w, h, c):
        x0, x1 = self.X(x), self.X(x + w)
        y0, y1 = self.Y(y), self.Y(y + h)
        self.cv.rect(x0, y0, max(1, x1 - x0), max(1, y1 - y0), c)


def blend(cv, x, y, c, a):
    if 0 <= x < cv.W and 0 <= y < cv.H:
        row = cv.px[y]
        row[x] = mix(row[x], c, a)


def disc(cv, cx, cy, rad, c):
    y0, y1 = int(math.floor(cy - rad)), int(math.ceil(cy + rad))
    for py in range(max(0, y0), min(cv.H, y1 + 1)):
        dy = py + 0.5 - cy
        if abs(dy) > rad:
            continue
        w = math.sqrt(rad * rad - dy * dy)
        a, b = max(0, int(math.floor(cx - w + 0.5))), min(cv.W, int(math.floor(cx + w + 0.5)))
        if b > a:
            cv.px[py][a:b] = [c] * (b - a)


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
            if r0 < d < r1:
                a = (1 - (d - r0) / span)
                row[px] = mix(row[px], c, a * a * k)


def shade_ellipse(cv, cx, cy, rx, ry, base, flash=False, spec=True, rim=0.0):
    """A lit body: per-pixel shading of a sphere-like ellipse, light from the top left. Bigger windows get
    a smoother, rounder body; small ones still read as a lit ball."""
    if rx < 0.6 or ry < 0.6:
        cv.set(int(cx), int(cy), base)
        return
    if flash:
        base = mix(base, WHITE, 0.6)
    dark = mix(base, (10, 6, 18), 0.72)
    lite = mix(base, (255, 250, 236), 0.5)
    W, H = cv.W, cv.H
    lx, ly, lz = -0.45, -0.55, 0.70
    y0, y1 = max(0, int(math.floor(cy - ry))), min(H - 1, int(math.ceil(cy + ry)))
    for py in range(y0, y1 + 1):
        v = (py + 0.5 - cy) / ry
        if v * v >= 1:
            continue
        hw = rx * math.sqrt(1 - v * v)
        a, b = max(0, int(math.floor(cx - hw + 0.5))), min(W, int(math.floor(cx + hw + 0.5)))
        if b <= a and 0 <= int(cx) < W:
            a, b = int(cx), int(cx) + 1
        row = cv.px[py]
        for px in range(a, b):
            u = (px + 0.5 - cx) / rx
            d = u * u + v * v
            nz = math.sqrt(max(0.0, 1 - d))
            l = u * lx + v * ly + nz * lz
            if l < 0.15:
                c = mix(dark, base, max(0.0, (l + 0.6) / 0.75))
            elif l < 0.8:
                c = mix(base, lite, (l - 0.15) / 0.65 * 0.6)
            else:
                c = mix(mix(base, lite, 0.6), WHITE, (l - 0.8) / 0.2 * (0.8 if spec else 0.2))
            if rim and d > 0.75:
                c = mix(c, lite, rim * (d - 0.75) * 4)
            row[px] = c


# --- panes --------------------------------------------------------------------------------------
_BRICK = {}


def crack_lines(seed, n):
    rnd = random.Random(seed * 101 + n)
    out = []
    for _ in range(n + 1):
        x, y = rnd.uniform(0.2, 0.8), rnd.uniform(0.2, 0.8)
        pts = [(x, y)]
        a = rnd.uniform(0, 2 * math.pi)
        for _ in range(3):
            a += rnd.uniform(-0.9, 0.9)
            x, y = x + math.cos(a) * 0.22, y + math.sin(a) * 0.5
            pts.append((x, y))
        out.append(pts)
    return out


def brick_img(kind, col, w, h, crack=0, flash=False, phase=0, seed=0):
    """A pane as rows of colours, cached per look and size."""
    key = (kind, col, w, h, crack, flash, phase, seed if crack else 0)
    img = _BRICK.get(key)
    if img is not None:
        return img
    if len(_BRICK) > 3000:
        _BRICK.clear()
    big = w >= 6 and h >= 3
    hi = mix(col, WHITE, 0.5)
    lead = mix(col, (6, 4, 12), 0.72)
    if kind == "iron":
        img = []
        for y in range(h):
            t = y / max(1, h - 1)
            img.append([mix((132, 140, 156), (52, 56, 68), t)] * w)
        img[0] = [(176, 184, 198)] * w
        if h > 1:
            img[h - 1] = [(28, 30, 38)] * w
        for row in img:
            row[w - 1] = (36, 38, 48)
        if big:
            for row in img[1:h - 1]:
                row[0] = (150, 156, 170)
            if w >= 8 and h >= 4:
                for (rx, ry) in ((1, 1), (w - 3, 1), (1, h - 3), (w - 3, h - 3)):
                    img[ry][rx] = (214, 220, 232)
                    if ry + 1 < h - 1:
                        img[ry + 1][rx] = (60, 64, 76)
            # a brushed stripe
            for x in range(1, w - 1):
                if (x * 7 + seed) % 5 == 0 and h >= 4:
                    img[h // 2][x] = mix(img[h // 2][x], (170, 176, 190), 0.5)
    elif kind == "blast":
        img = []
        glow_k = 0.55 + 0.45 * math.sin(phase / 4 * 2 * math.pi)
        for y in range(h):
            t = y / max(1, h - 1)
            img.append([mix((196, 54, 36), (110, 22, 18), t)] * w)
        cx, cy = (w - 1) / 2, (h - 1) / 2
        rr = max(0.8, min(w * 0.22, h * 0.48))
        for y in range(h):
            for x in range(w):
                d = math.hypot((x - cx) / max(1, rr * 1.6), (y - cy) / max(0.6, rr))
                if d < 1.0:
                    img[y][x] = mix((255, 150, 50), (255, 246, 170), (1 - d) * glow_k)
        if big:
            stripe = max(1, w // 7)
            for y in range(h):
                for x in list(range(stripe)) + list(range(w - stripe, w)):
                    img[y][x] = (240, 200, 60) if (x + y) % 2 == 0 else (30, 24, 20)
            img[0] = [mix(c, WHITE, 0.25) for c in img[0]]
            img[h - 1] = [shade(c, 0.5) for c in img[h - 1]]
        else:
            img[0] = [mix(c, WHITE, 0.2) for c in img[0]]
            for row in img:
                row[w - 1] = (70, 14, 10)
    elif kind == "drop":
        img = []
        frame, inner = (226, 176, 66), (140, 80, 30)
        cx, cy = (w - 1) / 2, (h - 1) / 2
        for y in range(h):
            row = []
            for x in range(w):
                d = math.hypot((x - cx) / max(1.0, w * 0.42), (y - cy) / max(0.8, h * 0.5))
                row.append(mix((255, 236, 160), inner, clamp(d, 0, 1)))
            img.append(row)
        if big:
            for x in range(w):
                img[0][x] = (255, 226, 130)
                img[h - 1][x] = (120, 84, 30)
            for y in range(h):
                img[y][0] = frame
                img[y][w - 1] = (120, 84, 30)
            if w >= 8 and h >= 4:           # a little flame in the lantern
                fx = w // 2
                for y in range(1, h - 1):
                    img[y][fx] = (255, 252, 220) if y > h // 3 else (255, 190, 90)
                for y in range(1, h - 1, 2):
                    img[y][2] = img[y][w - 3] = (160, 110, 40)
        else:
            img[0] = [(255, 226, 130)] * (w - 1) + [(120, 84, 30)]
            for row in img[1:]:
                row[w - 1] = (120, 84, 30)
    else:   # tinted glass: norm, move, regen, tough
        img = []
        frosted = kind == "tough"
        base = mix(col, (236, 240, 246), 0.38) if frosted else col
        for y in range(h):
            t = y / max(1, h - 1)
            img.append([mix(mix(base, WHITE, 0.2), shade(base, 0.78), t)] * w)
        if frosted:
            for y in range(h):
                for x in range(w):
                    if (x + 2 * y + seed) % 3 == 0:
                        img[y][x] = mix(img[y][x], WHITE, 0.16)
        if big:
            came = (210, 216, 228) if frosted else lead
            img[0] = [hi if not frosted else (240, 244, 250)] * w
            img[h - 1] = [came if frosted else lead] * w
            for y in range(h):
                img[y][0] = (240, 244, 250) if frosted else hi if y < h - 1 else lead
                img[y][w - 1] = came if frosted else lead
            if frosted and w >= 8 and h >= 4:
                for y in range(1, h - 1):
                    img[y][1] = mix(img[y][1], WHITE, 0.3)
            if w >= 8 and h >= 4 and not frosted:      # a glint across the glass
                for y in range(1, h - 1):
                    gx = int(w * 0.18) + (h - 1 - y)
                    for xx in (gx, gx + 1):
                        if 1 <= xx < w - 1:
                            img[y][xx] = mix(img[y][xx], WHITE, 0.45)
                img[1][1] = mix(hi, WHITE, 0.6)
            if kind == "regen":         # crystal facets
                for y in range(1, h - 1):
                    for x in range(1, w - 1):
                        if x / w + y / h > 1.0:
                            img[y][x] = shade(img[y][x], 0.82)
                        if abs(x / w - y / h) < 0.08:
                            img[y][x] = mix(img[y][x], WHITE, 0.35)
            if kind == "move" and w >= 6:   # chevrons
                ch = shade(col, 0.45)
                mid = h // 2
                for k in (-1, 1):
                    cx = w // 2 + k * max(1, w // 6)
                    for dy in range(-(h // 3), h // 3 + 1):
                        x = cx + (-abs(dy) if phase > 0 else abs(dy))
                        if 1 <= x < w - 1 and 1 <= mid + dy < h - 1:
                            img[mid + dy][x] = ch
        else:
            img[0] = [mix(hi, WHITE, 0.2) if frosted else hi] * (w - 1) + [lead]
            for row in img[1:]:
                row[w - 1] = lead
            if kind == "tough" and h >= 2:
                img[h - 1] = [mix(c, (230, 236, 244), 0.3) for c in img[h - 1]]
            if kind == "move" and h >= 2 and w >= 4:
                img[h - 1][w // 2 - (1 if phase > 0 else 0)] = shade(col, 0.45)
        if crack:
            dark = (40, 44, 56)
            for pts in crack_lines(seed, crack):
                for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                    n = max(2, int(max(abs(bx - ax) * w, abs(by - ay) * h) * 1.5))
                    for i in range(n + 1):
                        u = i / n
                        x = int((ax + (bx - ax) * u) * w)
                        y = int((ay + (by - ay) * u) * h)
                        if 0 <= x < w and 0 <= y < h:
                            img[y][x] = dark
                            if big and y + 1 < h - 1 and x + 1 < w - 1 and img[y + 1][x + 1] != dark:
                                img[y + 1][x + 1] = mix(img[y + 1][x + 1], WHITE, 0.4)
    if flash:
        img = [[mix(c, WHITE, 0.65) for c in row] for row in img]
    _BRICK[key] = img
    return img


def blit(cv, x0, y0, img, clip_y=None):
    h = len(img)
    if not h:
        return
    w = len(img[0])
    a = max(0, -x0)
    b = min(w, cv.W - x0)
    if b <= a:
        return
    ylo = 0 if clip_y is None else clip_y
    for j in range(h):
        y = y0 + j
        if ylo <= y < cv.H:
            cv.px[y][x0 + a:x0 + b] = img[j][a:b]


# --- backdrops ------------------------------------------------------------------------------------
_BG = {}


def leaf(cv, cx, cy, length, width, ang, col):
    ca, sa = math.cos(ang), math.sin(ang)
    R = length + width
    for py in range(max(0, int(cy - R)), min(cv.H, int(cy + R) + 1)):
        row = cv.px[py]
        for px in range(max(0, int(cx - R)), min(cv.W, int(cx + R) + 1)):
            dx, dy = px - cx, py - cy
            u = dx * ca + dy * sa
            v = -dx * sa + dy * ca
            if 0 <= u <= length:
                lim = width * math.sin(math.pi * u / length)
                if abs(v) < lim:
                    k = 0.8 + 0.35 * (v / max(0.5, lim))
                    c = shade(col, k)
                    if abs(v) < 0.6:
                        c = shade(col, 1.35)
                    row[px] = c


def gear(cv, cx, cy, R, teeth, col, phase=0.0):
    """A cog: toothed rim, five spokes, a hub, lit from the top left with a dark edge."""
    hi, lo = mix(col, (255, 236, 190), 0.35), shade(col, 0.55)
    for py in range(max(0, int(cy - R * 1.2)), min(cv.H, int(cy + R * 1.2) + 1)):
        row = cv.px[py]
        for px in range(max(0, int(cx - R * 1.2)), min(cv.W, int(cx + R * 1.2) + 1)):
            dx, dy = px + 0.5 - cx, py + 0.5 - cy
            d = math.hypot(dx, dy)
            if d > R * 1.16 or d < R * 0.12:
                continue
            a = math.atan2(dy, dx) + phase
            tooth = math.cos(a * teeth) > 0.2
            rim = R * (1.14 if tooth else 1.0)
            if d >= rim:
                continue
            inner = R * 0.74
            if R * 0.3 < d < inner and math.cos((a - phase) * 5 + phase * 5) < 0.7:
                continue
            lit = -(dx + dy) / max(1.0, d)
            c = col
            if rim - d < 1.0 or (R * 0.3 < d < inner + 1.0 and d > inner - 0.01):
                c = hi if lit > 0.2 else lo
            elif abs(d - inner) < 1.0 or abs(d - R * 0.3) < 1.0:
                c = lo if lit > 0 else hi
            elif d < R * 0.3:
                c = mix(col, hi, 0.4)
            row[px] = c


def paint_scenery(cv, world, s):
    W, H = cv.W, cv.H
    wd = WORLDS[world]
    top, bot = wd["sky"]
    for y in range(H):
        cv.px[y] = [mix(top, bot, y / max(1, H - 1))] * W
    u = max(1.0, s)
    if world == 0:      # a glasshouse: iron mullions, sun through the panes, big leaves
        P = max(5, int(u * 4))
        for y in range(H):
            row = cv.px[y]
            for x in range(W):
                c = row[x]
                if (x // P + y // (P * 3 // 2)) % 3 == 0:
                    c = mix(c, (60, 110, 80), 0.18)
                beam = (x - y * 0.6) / (u * 9)
                if (beam % 3.0) < 0.9:
                    c = mix(c, (150, 200, 120), 0.08)
                if x % P == 0 or y % (P * 3 // 2) == 0:
                    c = mix(c, (34, 52, 44), 0.7)
                row[x] = c
        rnd = random.Random(7)
        for i in range(int(W * H / max(1, u * u * 60)) + 6):
            side = rnd.random() < 0.5
            cx = rnd.uniform(0, W * 0.2) if side else rnd.uniform(W * 0.8, W)
            cy = rnd.uniform(H * 0.2, H)
            leaf(cv, cx, cy, rnd.uniform(3, 7) * u, rnd.uniform(1.0, 2.2) * u, rnd.uniform(-2.6, -0.5),
                 rnd.choice([(40, 110, 56), (52, 130, 62), (34, 92, 60), (70, 140, 60)]))
    elif world == 1:    # under water: caustic light, kelp, sand
        for y in range(H):
            row = cv.px[y]
            for x in range(W):
                a, b = x / u, y / u
                k = math.sin(a * 0.9 + math.sin(b * 0.7) * 1.6) + math.sin(b * 1.1 + math.sin(a * 0.5) * 1.8)
                if k > 1.25:
                    row[x] = mix(row[x], (90, 170, 220), min(0.35, (k - 1.25) * 0.5) * (1 - y / H * 0.6))
        rnd = random.Random(11)
        for i in range(10 + W // max(4, int(u * 3))):
            x0 = rnd.uniform(0, W)
            hgt = rnd.uniform(0.3, 0.7) * H
            col = rnd.choice([(30, 90, 60), (40, 110, 70), (24, 70, 56)])
            wid = max(1, int(u * 0.6))
            ph = rnd.uniform(0, 6)
            for y in range(int(H - hgt), H):
                t = (H - y) / hgt
                x = x0 + math.sin(y / (u * 2.2) + ph) * u * 1.2 * t
                cv.rect(int(x), y, wid, 1, shade(col, 0.8 + 0.4 * t))
        for y in range(int(H * 0.9), H):
            cv.px[y] = [mix(c, (120, 110, 80), 0.5) for c in cv.px[y]]
    elif world == 2:    # a clock loft: beams and big gears
        for y in range(H):
            row = cv.px[y]
            for x in range(W):
                if (y // max(3, int(u * 2))) % 4 == 0:
                    row[x] = mix(row[x], (60, 38, 20), 0.5)
        rnd = random.Random(3)
        for i in range(7):
            gx = rnd.choice([rnd.uniform(0, W * 0.25), rnd.uniform(W * 0.75, W), rnd.uniform(0, W)])
            gy = rnd.uniform(0, H)
            R = rnd.uniform(3, 7) * u
            gear(cv, gx, gy, R, rnd.choice([8, 10, 12, 14]), rnd.choice([(84, 60, 30), (110, 80, 36), (70, 50, 30)]),
                 rnd.uniform(0, 1))
        for x in range(0, W, max(6, int(u * 7))):   # posts
            cv.rect(x, 0, max(1, int(u * 0.6)), H, (40, 24, 14))
    elif world == 3:    # night over the spire: stars, aurora, ice
        for i in range(W * H // 60):
            x, y = hsh(i, 1, 3) % W, hsh(i, 2, 3) % max(1, H)
            b = 80 + hsh(i, 3, 3) % 170
            cv.px[y][x] = mix(cv.px[y][x], (b, b, min(255, b + 30)), 0.85)
        for x in range(W):
            a = x / u
            yc = H * 0.22 + math.sin(a * 0.18) * H * 0.08 + math.sin(a * 0.05 + 1) * H * 0.05
            for y in range(max(0, int(yc - u * 6)), min(H, int(yc + u * 3))):
                d = (y - yc) / (u * 2.5)
                k = math.exp(-d * d) * (0.5 + 0.5 * math.sin(a * 0.4))
                cv.px[y][x] = mix(cv.px[y][x], (80, 230, 170) if d > -1 else (120, 120, 240), k * 0.5)
        rnd = random.Random(5)
        for i in range(12):
            bx = rnd.uniform(0, W)
            hh = rnd.uniform(0.2, 0.55) * H
            ww = rnd.uniform(1.5, 3.5) * u
            cv.poly([(bx - ww, H), (bx, H - hh), (bx + ww, H)], (60, 84, 120))
            cv.poly([(bx - ww * 0.15, H), (bx, H - hh), (bx + ww * 0.4, H)], (120, 150, 190))
    else:               # the kiln: fire brick and a glow from below
        bw, bh = max(3, int(u * 2)), max(2, int(u))
        for y in range(H):
            row = cv.px[y]
            r = y // bh
            glowk = (y / H) ** 2
            for x in range(W):
                c = row[x]
                xx = x + (bw // 2 if r % 2 else 0)
                if y % bh == 0 or xx % bw == 0:
                    c = mix(c, (10, 4, 4), 0.6)
                else:
                    c = mix(c, (90 + hsh(xx // bw, r, 4) % 40, 30, 20), 0.35)
                row[x] = mix(c, (255, 110, 30), glowk * 0.45)


def backdrop(world, cols, rows, hud):
    key = (world, cols, rows, hud)
    c = _BG.get(key)
    if c is not None:
        return c
    if len(_BG) > 12:
        _BG.clear()
    s, ox, oy, wall = layout(cols, rows, hud)
    cv = Canvas(cols, rows)
    paint_scenery(cv, world, s)
    wd = WORLDS[world]
    fw, fh = int(round(FW * s)), int(round(FH * s))
    x0, y0, x1, y1 = ox, oy, ox + fw, oy + fh
    fc = wd["field"]
    for y in range(max(0, y0), min(cv.H, y1)):
        row = cv.px[y]
        t = (y - y0) / max(1, fh)
        for x in range(max(0, x0), min(cv.W, x1)):
            row[x] = mix(row[x], fc, (0.86 if world == 2 else 0.8) + 0.1 * t)
    # a faint pattern in the hall: the district's own
    if s >= 2:
        for y in range(max(0, y0), min(cv.H, y1)):
            row = cv.px[y]
            uy = (y - y0) / s
            for x in range(max(0, x0), min(cv.W, x1)):
                ux = (x - x0) / s
                if world == 0 and (abs(ux % 6.5) < 1 / s or abs(uy % 4.75) < 1 / s):
                    row[x] = mix(row[x], (40, 70, 56), 0.35)
                elif world == 1 and math.sin(ux * 0.9 + math.sin(uy * 0.7) * 1.6) + math.sin(uy * 1.1) > 1.5:
                    row[x] = mix(row[x], (30, 70, 110), 0.3)
                elif world == 2:
                    d = math.hypot(ux - FW / 2, uy - 8.5)
                    if abs(d - 7.5) < 0.6 / s * 2 or (abs(d - 6.8) < 0.5 and math.cos(math.atan2(uy - 8.5, ux - FW / 2) * 12) > 0.96):
                        row[x] = mix(row[x], (110, 80, 40), 0.35)
                elif world == 3 and hsh(x, y, 9) % 97 == 0:
                    row[x] = mix(row[x], (150, 180, 220), 0.4)
                elif world == 4 and (int(uy) % 2 == 0) and int(ux * 2) % 4 == 0 and y % max(1, int(s)) == 0:
                    row[x] = mix(row[x], (60, 20, 12), 0.5)
        for y in range(max(0, y1 - int(s * 1.2)), min(cv.H, y1)):    # the drop at the bottom darkens
            k = (y - (y1 - s * 1.2)) / (s * 1.2)
            cv.px[y][max(0, x0):x1] = [mix(c, (0, 0, 0), k * 0.5) for c in cv.px[y][max(0, x0):x1]]
    # the frame: left, right and top, with two hatches the creatures come through
    if wall:
        hi, lo = wd["frame"]
        for k in range(wall):
            c = mix(hi, lo, k / max(1, wall - 1)) if wall > 1 else hi
            cv.rect(x0 - wall + k, y0 - wall + k, 1, y1 - (y0 - wall + k), mix(hi, lo, 0.3 + 0.4 * k / max(1, wall)))
            cv.rect(x1 + wall - 1 - k, y0 - wall + k, 1, y1 - (y0 - wall + k), mix(lo, (0, 0, 0), 0.2 * (wall - k) / wall))
            cv.rect(x0 - wall + k, y0 - wall + k, fw + 2 * (wall - k), 1, c)
        if s >= 3:   # studs along the frame
            for y in range(y0 + int(s), y1, int(s * 3)):
                cv.set(x0 - wall + wall // 2, y, mix(hi, WHITE, 0.35))
                cv.set(x1 + wall // 2, y, mix(hi, WHITE, 0.2))
        for hx in HATCHES:
            a, b = ox + int((hx - 1.1) * s), ox + int((hx + 1.1) * s)
            cv.rect(a, y0 - wall, b - a, wall, (8, 6, 12))
            cv.rect(a - 1, y0 - wall, 1, wall, mix(hi, WHITE, 0.3))
            cv.rect(b, y0 - wall, 1, wall, lo)
    out = [row[:] for row in cv.px]
    _BG[key] = out
    return out


def draw_ambient(cv, g, s):
    """Light drifting about: pollen, bubbles, dust, snow, embers - over the whole picture."""
    W, H = cv.W, cv.H
    t = g.clock
    w = g.world
    col = WORLDS[w]["ambient"]
    n = 18 + W * H // 900
    for i in range(n):
        a = hsh(i, 5, w) / 65536.0
        b = hsh(i, 6, w) / 65536.0
        sp = 0.4 + hsh(i, 7, w) / 65536.0
        if w in (1, 4):          # rising
            x = (a * W + math.sin(t * 1.3 + i) * s * 0.6) % W
            y = (b * H - t * sp * s * 2.0) % H
        elif w == 3:             # falling snow
            x = (a * W + math.sin(t * 0.7 + i) * s * 1.2) % W
            y = (b * H + t * sp * s * 1.5) % H
        else:                    # drifting
            x = (a * W + t * sp * s * 0.8) % W
            y = (b * H + math.sin(t * 0.9 + i * 1.7) * s) % H
        k = 0.25 + 0.35 * (0.5 + 0.5 * math.sin(t * 3 + i))
        blend(cv, int(x), int(y), col, k)
        if s >= 6 and w == 1 and i % 3 == 0:       # bubbles get a rim in big windows
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                blend(cv, int(x) + dx, int(y) + dy, col, k * 0.4)


# --- creatures --------------------------------------------------------------------------------
ART = {
    "moth": (["ww...ww", "wew.wew", "wwwbwww", ".wwbww.", "..wbw..", "...b..."],
             [".w...w.", ".ww.ww.", ".wwbww.", "..wbw..", "..wbw..", "...b..."],
             {"w": (214, 196, 236), "e": (120, 70, 150), "b": (120, 90, 70)}),
    "jelly": (["..ccc..", ".ccccc.", "cchcccc", "ccccccc", "t.t.t.t", ".t.t.t."],
              ["..ccc..", ".ccccc.", "cchcccc", ".ccccc.", ".t.t.t.", "t.t.t.t"],
              {"c": (150, 200, 255), "h": (240, 250, 255), "t": (220, 150, 240)}),
    "cog": (["..g.g..", ".ggggg.", "ggrrrgg", ".ggrgg.", "..g.g..", "......."],
            [".g...g.", "..ggg..", "ggrrrgg", "..grg..", ".g...g.", "......."],
            {"g": (196, 166, 96), "r": (255, 80, 60)}),
    "mote": (["...s...", ".s.s.s.", "..sws..", "sswwwss", "..sws..", ".s.s.s."],
             ["s.....s", "..sss..", ".swwws.", ".swwws.", "..sss..", "s.....s"],
             {"s": (190, 220, 255), "w": (255, 255, 255)}),
    "cinder": (["..o.o..", ".oyyyo.", "oykyyko", "oyyyyyo", ".orrro.", "..r.r.."],
               ["...o...", ".oyyyo.", "oykyyko", "oyyyyyo", ".orrro.", ".r...r."],
               {"o": (255, 140, 50), "y": (255, 220, 110), "k": (40, 10, 10), "r": (200, 60, 30)}),
}
_SPR = {}


def sprite(kind, frame, w, h):
    key = (kind, frame, w, h)
    sp = _SPR.get(key)
    if sp is not None:
        return sp
    f0, f1, pal = ART[kind]
    grid = scale_art([list(r) for r in (f0 if frame == 0 else f1)], w, h)
    img = [[None] * (w + 2) for _ in range(h + 2)]
    for y in range(h):
        for x in range(w):
            ch = grid[y][x]
            if ch == ".":
                continue
            c = pal[ch]
            up = y == 0 or grid[y - 1][x] == "."
            dn = y == h - 1 or grid[y + 1][x] == "."
            if up:
                c = mix(c, WHITE, 0.3)
            elif dn:
                c = shade(c, 0.65)
            img[y + 1][x + 1] = c
    for y in range(h + 2):
        for x in range(w + 2):
            if img[y][x] is None and any(0 <= x + dx < w + 2 and 0 <= y + dy < h + 2 and img[y + dy][x + dx] not in (None, 0)
                                          for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                img[y][x] = 0
    runs = []
    for y, row in enumerate(img):
        for x, c in enumerate(row):
            if c is not None:
                runs.append((x, y, (10, 6, 18) if c == 0 else c))
    _SPR[key] = runs
    return runs


def draw_sprite(cv, runs, x0, y0):
    W, H = cv.W, cv.H
    for (x, y, c) in runs:
        xx, yy = x0 + x, y0 + y
        if 0 <= xx < W and 0 <= yy < H:
            cv.px[yy][xx] = c


# --- keepers --------------------------------------------------------------------------------------
def draw_boss(v, g):
    bo = g.boss
    cv, s = v.cv, v.s
    if bo.dead and bo.dead_t > 1.6:
        return
    if bo.dead and int(bo.dead_t * 14) % 2:
        return
    cx, cy = v.ox + bo.x * s, v.oy + bo.y * s
    R = bo.radius * s
    fl = bo.flash > 0
    t = bo.t
    k = bo.kind
    if k == "bramble":
        for i in range(11):     # the thorn crown
            a = i / 11 * 2 * math.pi + t * 0.25
            p1 = (cx + math.cos(a - 0.16) * R * 0.85, cy + math.sin(a - 0.16) * R * 0.85)
            p2 = (cx + math.cos(a) * R * 1.55, cy + math.sin(a) * R * 1.55)
            p3 = (cx + math.cos(a + 0.16) * R * 0.85, cy + math.sin(a + 0.16) * R * 0.85)
            cv.poly([p1, p2, p3], (46, 120, 56) if i % 2 else (34, 92, 46))
        shade_ellipse(cv, cx - R * 0.75, cy + R * 0.8, R * 0.7, R * 0.3, (60, 150, 70))
        shade_ellipse(cv, cx + R * 0.75, cy + R * 0.8, R * 0.7, R * 0.3, (60, 150, 70))
        shade_ellipse(cv, cx, cy, R, R * 1.05, BOSS_COL[k], fl)
        for j, (dx, dy, rr) in enumerate(((-0.35, -0.45, 0.5), (0.35, -0.4, 0.5), (0.0, -0.7, 0.42))):
            shade_ellipse(cv, cx + dx * R, cy + dy * R, rr * R, rr * R * 0.8, (230, 70, 104) if j < 2 else (246, 110, 140), fl)
        ey = cy + R * 0.18
        for dx in (-0.36, 0.36):
            ww = max(1, int(R * 0.3))
            cv.rect(int(cx + dx * R - ww / 2), int(ey), ww, max(1, int(R * 0.1)), (255, 230, 90))
    elif k == "clam":
        o = bo.open
        if o > 0.05:
            shade_ellipse(cv, cx, cy + R * 0.3, R * 0.9, R * 0.55 * (0.4 + o), (70, 24, 70), spec=False)
        shade_ellipse(cv, cx, cy + R * 0.25 + o * R * 0.3, R * 1.05, R * 0.5, (196, 150, 146), fl)
        if o > 0.3:
            shade_ellipse(cv, cx, cy + 0.5 * s, 1.3 * s * min(1.0, o + 0.2), 1.3 * s * min(1.0, o + 0.2), (244, 238, 252), fl)
        top_y = cy - o * R * 0.55
        shade_ellipse(cv, cx, top_y, R * 1.05, R * 0.62, (230, 188, 172), fl)
        if R >= 6:
            for i in range(-3, 4):
                a = i * 0.32
                cv.line(cx, top_y - R * 0.6, cx + math.sin(a) * R * 0.95, top_y + math.cos(a) * R * 0.5 - R * 0.05,
                        mix((230, 188, 172), (110, 70, 70), 0.5))
        for dx in (-0.45, 0.45):
            ex, ey = cx + dx * R, top_y - R * 0.62
            cv.line(ex, ey, ex + dx * R * 0.2, ey - R * 0.35, (150, 110, 100))
            disc(cv, ex + dx * R * 0.2, ey - R * 0.38, max(0.8, R * 0.11), (30, 20, 30))
            cv.set(int(ex + dx * R * 0.2), int(ey - R * 0.42), WHITE)
    elif k == "pendulum":
        pxv, pyv = v.ox + 13 * s, v.oy - 1.5 * s
        th = max(1, int(s * 0.35))
        n = int(math.hypot(cx - pxv, cy - pyv))
        for i in range(n):
            u = i / max(1, n)
            x, y = pxv + (cx - pxv) * u, pyv + (cy - pyv) * u
            if y >= v.oy:
                cv.rect(int(x - th / 2), int(y), th, 1, (180, 140, 60))
                cv.set(int(x - th / 2), int(y), (240, 210, 130))
        shade_ellipse(cv, cx, cy, R, R, BOSS_COL[k], fl)
        fr = R * 0.66
        disc(cv, cx, cy, fr, (236, 226, 196) if not fl else WHITE)
        if R >= 5:
            for i in range(12):
                a = i / 12 * 2 * math.pi
                cv.set(int(cx + math.cos(a) * fr * 0.82), int(cy + math.sin(a) * fr * 0.82), (60, 40, 30))
        for (rate, ln) in ((0.5, 0.45), (3.0, 0.7)):
            a = t * rate - math.pi / 2
            cv.line(cx, cy, cx + math.cos(a) * fr * ln, cy + math.sin(a) * fr * ln, (40, 26, 20))
        for dx in (-0.28, 0.28):
            disc(cv, cx + dx * R, cy - R * 0.22, max(0.7, R * 0.1), (255, 70, 50))
        disc(cv, cx, cy, max(0.6, R * 0.07), (40, 26, 20))
    elif k == "owl":
        flap = math.sin(t * 6) * R * 0.25
        wc = (150, 172, 214)
        cv.poly([(cx - R * 0.6, cy - R * 0.3), (cx - R * 1.7, cy + flap), (cx - R * 0.7, cy + R * 0.85)], wc)
        cv.poly([(cx + R * 0.6, cy - R * 0.3), (cx + R * 1.7, cy + flap), (cx + R * 0.7, cy + R * 0.85)], wc)
        cv.poly([(cx - R * 0.75, cy - R * 0.55), (cx - R * 0.55, cy - R * 1.25), (cx - R * 0.2, cy - R * 0.7)], (170, 190, 226))
        cv.poly([(cx + R * 0.75, cy - R * 0.55), (cx + R * 0.55, cy - R * 1.25), (cx + R * 0.2, cy - R * 0.7)], (170, 190, 226))
        shade_ellipse(cv, cx, cy, R * 0.85, R, BOSS_COL[k] if bo.inv <= 0 else (150, 220, 255), fl)
        shade_ellipse(cv, cx, cy + R * 0.35, R * 0.5, R * 0.5, (236, 242, 252), fl, spec=False)
        tb = g.balls[0] if g.balls else None
        for dx in (-0.36, 0.36):
            ex, ey = cx + dx * R, cy - R * 0.25
            disc(cv, ex, ey, max(0.8, R * 0.29), (250, 200, 60))
            lx = ly = 0.0
            if tb:
                ang = math.atan2(v.oy + tb.y * s - ey, v.ox + tb.x * s - ex)
                lx, ly = math.cos(ang) * R * 0.1, math.sin(ang) * R * 0.1
            disc(cv, ex + lx, ey + ly, max(0.6, R * 0.14), (20, 14, 24))
        cv.poly([(cx - R * 0.12, cy - R * 0.05), (cx + R * 0.12, cy - R * 0.05), (cx, cy + R * 0.2)], (240, 150, 60))
        if bo.warn > 0:
            glow(cv, cx, cy + R * 1.1, 0, R * 0.8, (200, 240, 255), bo.warn)
    else:
        pulse = 0.5 + 0.5 * math.sin(t * 5)
        if s >= 2:
            glow(cv, cx, cy, R * 0.9, R * 2.2, (255, 120, 40), 0.25 + 0.2 * pulse)
        shade_ellipse(cv, cx, cy, R, R, mix(BOSS_COL[k], (255, 200, 90), pulse * 0.4), fl)
        if R >= 3:
            for dx in (-0.38, 0.38):        # eyes: hot slits
                ww, hh = max(1, int(R * 0.34)), max(1, int(R * 0.16))
                cv.rect(int(cx + dx * R - ww / 2), int(cy - R * 0.32), ww, hh, (255, 246, 170))
            for i in range(3 if R >= 6 else 1):    # a grille for a mouth
                yy = int(cy + R * (0.25 + i * 0.18))
                hw = R * 0.42 * (1 - i * 0.18)
                cv.rect(int(cx - hw), yy, max(1, int(hw * 2)), 1, (90, 20, 10))
        for i, sh in enumerate(bo.shields):
            a = sh[0] + t * 0.9
            sx_, sy_ = cx + 3.3 * s * math.cos(a), cy + 3.3 * s * math.sin(a)
            if sh[1] > 0:
                shade_ellipse(cv, sx_, sy_, 0.85 * s, 0.85 * s, (120, 112, 130) if sh[1] == 2 else (150, 90, 80))
                if s >= 4:
                    cv.set(int(sx_), int(sy_), (40, 36, 48))
            elif s >= 3 and int(t * 4) % 2:
                blend(cv, int(sx_), int(sy_), (255, 160, 80), 0.6)


def draw_shot(cv, v, sh, t):
    s = v.s
    x, y = v.ox + sh.x * s, v.oy + sh.y * s
    k = sh.kind
    if k == "thorn":
        cv.poly([(x - 0.35 * s, y - 0.4 * s), (x + 0.35 * s, y - 0.4 * s), (x, y + 0.5 * s)], (60, 160, 70))
        cv.set(int(x), int(y), (200, 255, 160))
    elif k == "bubble":
        glow(cv, x, y, 0, max(1.2, 0.5 * s), (170, 230, 255), 0.8)
        cv.set(int(x - s * 0.15), int(y - s * 0.15), WHITE)
    elif k == "gear":
        if s >= 4:
            gear(cv, x, y, 0.45 * s, 6, (200, 160, 80), t * 6)
        else:
            disc(cv, x, y, max(0.8, 0.45 * s), (200, 160, 80))
    elif k == "icicle":
        cv.poly([(x - 0.3 * s, y - 0.8 * s), (x + 0.3 * s, y - 0.8 * s), (x, y + 0.6 * s)], (200, 236, 255))
        cv.set(int(x), int(y - 0.3 * s), WHITE)
    else:
        glow(cv, x, y, 0, max(1.5, 0.7 * s), (255, 140, 40), 0.7)
        disc(cv, x, y, max(0.7, 0.28 * s), (255, 236, 150))


# --- the tray, sparks and gifts -------------------------------------------------------------------
def draw_paddle(v, g):
    cv, s = v.cv, v.s
    w = g.pw_draw
    x0, x1 = v.X(g.px - w / 2), v.X(g.px + w / 2)
    y0 = v.Y(PY)
    h = max(1, int(round(PTH * s)))
    W = x1 - x0
    stun = g.stun > 0 and int(g.clock * 16) % 2
    heavy = "heavy" in g.powers
    top, mid, bot = (255, 232, 160), (214, 160, 66), (110, 70, 30)
    if heavy:
        top, mid, bot = (150, 140, 130), (96, 88, 82), (50, 44, 44)
    if stun:
        top, mid, bot = (220, 240, 255), (150, 190, 230), (70, 90, 130)
    rad = min(h, W // 2) if s >= 3 else 0
    lamp_c = W / 2
    for j in range(h):
        t = j / max(1, h - 1)
        c = mix(top, mid, t * 2) if t < 0.5 else mix(mid, bot, (t - 0.5) * 2)
        if h == 1:
            c = mid
        y = y0 + j
        if not 0 <= y < cv.H:
            continue
        row = cv.px[y]
        for i in range(W):
            x = x0 + i
            if not 0 <= x < cv.W:
                continue
            if rad:
                e = min(i, W - 1 - i)
                if e < rad:
                    dy = abs(j - (h - 1) / 2) / max(1, h / 2)
                    if (rad - e) / rad > math.sqrt(max(0, 1 - dy * dy)) + 0.15:
                        continue
            cc = c
            d = abs(i - lamp_c)
            if d < s * 0.45 and 0 < j < h - 1 or (h <= 2 and d < s * 0.45 and j == 0):
                cc = mix((255, 246, 200), c, d / (s * 0.45))
            row[x] = cc
    if s >= 3 and h >= 2:   # little rivets along the brass
        for xx in (x0 + max(2, int(s * 0.6)), x1 - 1 - max(2, int(s * 0.6))):
            cv.set(xx, y0 + h // 2, (255, 240, 190))
    if "catch" in g.powers:     # a coat of tallow
        for i in range(W):
            if 0 <= x0 + i < cv.W and 0 <= y0 < cv.H:
                cv.px[y0][x0 + i] = (250, 214, 120) if (i + int(g.clock * 6)) % 5 else (255, 246, 210)
    if "laser" in g.powers:     # flint strikers at the tips
        cw = max(1, int(s * 0.35))
        ch = max(1, int(s * 0.4))
        for xx in (v.X(g.px - w / 2 + 0.35) - cw // 2, v.X(g.px + w / 2 - 0.35) - cw // 2):
            cv.rect(xx, y0 - ch, cw, ch, (90, 220, 230))
            cv.set(xx, y0 - ch, (220, 255, 255))
    if s >= 3:
        glow(cv, x0 + lamp_c, y0 + h / 2, 0, s * 1.4, (255, 200, 110), 0.25)


def draw_ball(v, g, b):
    cv, s = v.cv, v.s
    pierce = "pierce" in g.powers
    core, rim, halo = ((255, 255, 255), (255, 120, 110), (255, 90, 80)) if pierce else \
        ((255, 252, 224), (255, 176, 70), (255, 150, 60))
    n = len(b.trail)
    for i, (tx, ty) in enumerate(b.trail):
        k = (i + 1) / (n + 1)
        x, y = v.ox + tx * s, v.oy + ty * s
        if s >= 4:
            disc(cv, x, y, max(0.5, BALL_R * s * 0.7 * k), mix(halo, (40, 20, 20), 1 - k))
        else:
            blend(cv, int(x), int(y), halo, k * 0.6)
    cx, cy = v.ox + b.x * s, v.oy + b.y * s
    R = BALL_R * s * 1.12
    fl = 0.5 + 0.5 * math.sin(g.clock * 23 + b.x)
    if s >= 2:
        glow(cv, cx, cy, R * 0.8, R * 3.0 + 1.5, halo, 0.42 + 0.12 * fl)
    if R < 1.1:
        x, y = int(cx - 0.5), int(cy - 0.5)
        cv.rect(x, y, 2 if s >= 2 else 1, 2 if s >= 2 else 1, rim)
        cv.set(x, y, core)
        return
    y0, y1 = int(math.floor(cy - R - 1)), int(math.ceil(cy + R + 1))
    for py in range(max(0, y0), min(cv.H, y1)):
        dy = py + 0.5 - cy
        row = cv.px[py]
        for px in range(max(0, int(cx - R - 1)), min(cv.W, int(cx + R + 2))):
            dx = px + 0.5 - cx
            d = math.sqrt(dx * dx + dy * dy)
            if d >= R + 0.5:
                continue
            k = clamp(math.hypot(dx + R * 0.25, dy + R * 0.25) / (R * 1.15), 0, 1)
            c = mix(core, rim, k ** (1.3 + 0.5 * fl))
            row[px] = c if d <= R - 0.5 else mix(row[px], c, R + 0.5 - d)


def draw_capsule(v, g, c):
    cv, s = v.cv, v.s
    letter, name, col, good, *_ = POWERS[c.kind]
    x0, x1 = v.X(c.x - CAP_W / 2), v.X(c.x + CAP_W / 2)
    y0, y1 = v.Y(c.y - CAP_H / 2), v.Y(c.y + CAP_H / 2)
    if s < 4:
        y0 = (y0 + 1) // 2 * 2 - (1 if s >= 3 else 0)
        y1 = y0 + (3 if s >= 3 else 2)
    w, h = max(2, x1 - x0), max(1, y1 - y0)
    spin = int(c.t * 8) % 4
    for j in range(h):
        t = j / max(1, h - 1)
        base = mix(mix(col, WHITE, 0.45), shade(col, 0.6), t) if h > 1 else col
        y = y0 + j
        if not 0 <= y < cv.H:
            continue
        for i in range(w):
            x = x0 + i
            if not 0 <= x < cv.W:
                continue
            if h >= 3 and (i == 0 or i == w - 1) and (j == 0 or j == h - 1):
                continue
            cc = base
            if (i - spin) % 4 == 0 and h >= 2:
                cc = mix(cc, WHITE, 0.2) if good else mix(cc, (200, 50, 50), 0.5)
            if i == 0 or i == w - 1:
                cc = shade(cc, 0.7)
            cv.px[y][x] = cc
    if not good and s >= 3:
        glow(cv, (x0 + x1) / 2, (y0 + y1) / 2, w / 2, w / 2 + s, (255, 60, 60), 0.25)
    if cv.rows > 10:
        row = (y0 + y1) // 4 if s >= 4 else (y1 - 1) // 2
        cv.put((x0 + x1) // 2, row, letter, (20, 14, 24) if good else (255, 120, 110),
               mix(col, WHITE, 0.15) if good else shade(col, 0.9))


def draw_bricks(v, g):
    cv, s = v.cv, v.s
    phase = int(g.clock * 4) % 4
    for row in g.board.grid:
        for b in row:
            if b is None:
                continue
            x0, x1 = v.X(b.x), v.X(b.x + 2)
            y0, y1 = v.Y(b.y), v.Y(b.y + 1)
            crack = b.maxhp - b.hp if b.kind == "tough" else 0
            img = brick_img(b.kind, b.color, max(1, x1 - x0), max(1, y1 - y0), crack, b.flash > 0,
                            phase if b.kind == "blast" else 0, b.seed % 7 if crack else 0)
            blit(cv, x0, y0, img)
    for b in g.board.movers:
        x0, x1 = v.X(b.x), v.X(b.x + 2)
        y0, y1 = v.Y(b.y), v.Y(b.y + 1)
        img = brick_img("move", b.color, max(1, x1 - x0), max(1, y1 - y0), 0, b.flash > 0, 1 if b.vx > 0 else -1)
        blit(cv, x0, y0, img)
    # frost growing back: a faint outline that fills in
    for (tl, c, r, col) in g.board.regrow:
        k = 1 - tl / REGEN_T
        x0, x1 = v.X(c * 2), v.X(c * 2 + 2)
        y0, y1 = v.Y(GY + r), v.Y(GY + r + 1)
        for x in range(x0, x1):
            if (x - x0) < (x1 - x0) * k:
                blend(cv, x, y1 - 1, col, 0.5)
                blend(cv, x, y0, col, 0.25 * k)
        if k > 0.7:
            for y in range(y0, y1):
                for x in range(x0, x1):
                    if (x + y) % 2 == 0:
                        blend(cv, x, y, col, (k - 0.7))


def render(g, cols, rows, hud=True):
    s, ox, oy, wall = layout(cols, rows, hud)
    cv = Canvas(cols, 1)
    cv.rows, cv.H = rows, rows * 2
    cv.px = [r[:] for r in backdrop(g.world, cols, rows, hud)]
    if g.shake > 0 and s >= 2:
        k = g.shake * s * 1.5
        ox += int(g.rnd.uniform(-k, k))
        oy += int(g.rnd.uniform(-k, k) * 0.5)
    v = View(cv, s, ox, oy)
    draw_ambient(cv, g, s)
    draw_bricks(v, g)
    if g.boss:
        draw_boss(v, g)
    for e in g.enemies:
        w = max(2, int(round(ENEMY_R * 2.2 * s)))
        h = max(2, int(round(ENEMY_R * 1.9 * s)))
        fr = int((g.clock + e.seed) * 6) % 2
        draw_sprite(cv, sprite(e.kind, fr, w, h), v.X(e.x) - w // 2 - 1, v.Y(e.y) - h // 2 - 1)
    for sh in g.shots:
        draw_shot(cv, v, sh, g.clock)
    for bl in g.bolts:
        x = v.X(bl[0])
        y0, y1 = v.Y(bl[1]), v.Y(bl[1] + 0.7)
        for y in range(y0, max(y0 + 1, y1)):
            blend(cv, x, y, (160, 255, 255), 0.9)
        cv.set(x, y0, WHITE)
    if "barrier" in g.powers:
        y = v.Y(BAR_Y)
        left = g.powers["barrier"]
        if left > 2 or int(g.clock * 8) % 2:
            for x in range(v.X(0), v.X(FW)):
                k = 0.6 + 0.4 * math.sin(x * 0.4 + g.clock * 8)
                blend(cv, x, y, (255, 160, 60), k)
                if s >= 4:
                    blend(cv, x, y - 1, (255, 200, 120), k * 0.3)
    for c in g.caps:
        draw_capsule(v, g, c)
    if g.state not in ("lost", "over") or g.state_t < 0.2:
        draw_paddle(v, g)
    for b in g.balls:
        draw_ball(v, g, b)
    for r in g.rings:
        x, y, t, life = r
        rad = (0.5 + t / life * 2.6) * s
        k = 1 - t / life
        n = max(8, int(rad * 5))
        for i in range(n):
            a = i / n * 2 * math.pi
            blend(cv, int(v.ox + x * s + math.cos(a) * rad), int(v.oy + y * s + math.sin(a) * rad), (255, 210, 120), k)
    psz = max(1, int(s // 3))
    for p in g.parts:
        k = 1 - p[4] / p[5]
        c = p[6]
        x, y = v.X(p[0]), v.Y(p[1])
        if psz == 1:
            blend(cv, x, y, c, 0.4 + 0.6 * k)
        else:
            cv.rect(x, y, psz, psz, mix((20, 10, 20), c, 0.3 + 0.7 * k))
    if cv.rows > 10:
        for f in g.floats:
            x, y, txt, t, col = f
            if t < 0:
                continue
            row = int(v.Y(y) // 2)
            if 0 < row < rows - 1:
                cv.put(int(v.X(x) - len(txt) / 2), row, txt, mix(col, (40, 30, 40), max(0.0, t - 0.5) * 1.6))
    if hud:
        draw_hud(cv, g, v)
        draw_banners(cv, g)
    return cv


# --- the text on top -------------------------------------------------------------------------------
def banner(cv, lines, col):
    w = max(len(l) for l in lines) + 4
    x = max(0, (cv.cols - w) // 2)
    y = max(1, cv.rows // 2 - len(lines) // 2)
    cv.box(x, y, [l.center(w - 4) for l in lines], (240, 240, 246), (20, 18, 38))
    cv.put(x + 2, y + 1, lines[0].center(w - 4), col, (20, 18, 38))


def draw_banners(cv, g):
    wd = WORLDS[g.world]
    if g.state == "ready" and g.state_t < 2.6 and g.lives and not g.over:
        sub = BOSS_NAME[g.boss.kind] if g.boss else g.spec["name"].upper()
        top = ("%s  -  HALL %d" % (wd["name"], g.level_i % 5 + 1)) if g.mode == "campaign" else \
            ("ENDLESS  -  HALL %d" % (g.level_i + 1))
        banner(cv, [top, sub, "", "Space: launch the spark"], wd["accent"])
    elif g.state == "clear" and g.state_t > 0.3:
        bonus, secs = g.tally or (0, 0)
        lines = ["KEEPER BROKEN" if g.boss else "HALL CLEAR", ""]
        if bonus:
            lines.append("clear bonus  %d" % bonus)
        lines.append("time  %d:%02d" % (int(secs) // 60, int(secs) % 60))
        banner(cv, lines, GOLD)
    elif g.state == "lost" and g.state_t > 0.4 and not g.over:
        banner(cv, ["SPARK LOST", "", ("%d spark%s left" % (g.lives, "" if g.lives == 1 else "s")) if g.lives else
                    "no sparks left"], (255, 130, 100))


def draw_hud(cv, g, v):
    cols, rows = cv.cols, cv.rows
    cv.put(0, 0, " " * cols, HUD_FG, HUD_BG)
    best = max(g.score, g.hi)
    parts = [("SCORE ", HUD_DIM), ("%07d" % g.score, GOLD), ("  HI ", HUD_DIM), ("%07d" % best, HUD_FG)]
    if g.mult > 1:
        parts.append(("  x%d" % g.mult, (255, 170, 90)))
    x = 1
    for s_, c in parts:
        cv.put(x, 0, s_, c, HUD_BG)
        x += len(s_)
    lives = "♦" * min(g.lives, 6) + ("+" if g.lives > 6 else "")
    cv.put(x + 2, 0, lives, (255, 190, 90), HUD_BG)
    x += 2 + len(lives)
    if g.boss and not g.boss.dead:
        right = BOSS_NAME[g.boss.kind]
        rc = (255, 120, 110)
    else:
        right = "%s %s" % (g.label(), g.spec["name"].upper())
        rc = WORLDS[g.world]["accent"]
    if x + len(right) + 3 > cols:
        right = g.label()
    if x + len(right) + 2 <= cols:
        cv.put(cols - len(right) - 1, 0, right, rc, HUD_BG)
    # keeper health along the top of the hall
    if g.boss and not g.boss.dead and g.boss.intro <= 0:
        f = g.boss.hp / g.boss.maxhp
        x0, x1 = v.X(3), v.X(FW - 3)
        y = v.Y(0.45)
        hh = max(1, int(v.s // 3))
        cv.rect(x0, y, x1 - x0, hh, (60, 20, 30))
        cv.rect(x0, y, int((x1 - x0) * f), hh, (255, 90, 100))
    # bottom line: what the tray carries
    r = rows - 1
    cv.put(0, r, " " * cols, HUD_FG, HUD_BG)
    x = 1
    for k in sorted(g.powers, key=lambda k: -g.powers[k]):
        letter, name, col, good, dur = POWERS[k][:5]
        left = g.powers[k]
        label = " %s %d " % (name if cols >= 90 else letter, math.ceil(left))
        if x + len(label) + 1 > cols - 16:
            break
        blink = left < 2.5 and int(g.clock * 6) % 2
        if good:
            cv.put(x, r, label, (16, 12, 20), shade(col, 0.6) if blink else col)
        else:
            cv.put(x, r, label, (255, 130, 120) if not blink else (140, 80, 80), (40, 24, 40))
        x += len(label) + 1
    if g.stun > 0:
        cv.put(x, r, " STUNNED ", (20, 20, 30), (180, 220, 255))
        x += 10
    if g.state == "ready" and x < cols - 40:
        cv.put(x + 1, r, "Space launch", HUD_DIM, HUD_BG)
    nb = len(g.balls)
    tag = ("%d sparks  " % nb if nb > 1 else "") + WORLDS[g.world]["short"]
    if cols - len(tag) - 1 > x + 14:
        cv.put(cols - len(tag) - 1, r, tag, HUD_DIM, HUD_BG)


def render_over(g, cv, record, auto=False):
    if g.won:
        lines = ["THE TOWN IS LIT", "", "Every lantern burns again.", "", "score  %d" % g.score,
                 "best combo  %d panes" % g.best_chain]
    else:
        where = ("hall %d" % (g.level_i + 1)) if g.mode == "endless" else "%s, hall %d" % (
            WORLDS[g.world]["short"].lower(), g.level_i % 5 + 1)
        lines = ["GAME OVER", "", "score  %d" % g.score, "reached  %s" % where, "best combo  %d panes" % g.best_chain]
    if record:
        lines += ["", "** NEW RECORD **"]
    lines += ["", "auto mode: a new round starts" if auto else "Enter: again   Esc / Q: menu"]
    w = max(len(l) for l in lines) + 4
    x, y = max(0, (cv.cols - w) // 2), max(0, cv.rows // 2 - len(lines) // 2 - 1)
    edge = GOLD if record or g.won else (200, 76, 86)
    cv.frame(x - 1, y * 2 - 1, w + 2, (len(lines) + 2) * 2 + 2, edge)
    cv.box(x, y, [l.center(w - 4) for l in lines], (240, 240, 246), (24, 22, 44))


# =============================================================================================
# Title demo, controls, menu, main loop
# =============================================================================================
class TitleDemo:
    """The autopilot playing a hall of each district in turn, behind the title (and in the launcher preview)."""
    PICK = (1, 6, 12, 15, 20, 9, 2, 17, 13, 22, 4, 7, 18, 24, 3, 8, 11, 16, 21, 14, 5, 10, 19, 23, 0)

    def __init__(self, k=0):
        self.k = k
        self.new_run()

    def new_run(self):
        lvl = self.PICK[self.k % len(self.PICK)]
        self.g = Game("campaign", lvl, seed=self.k + 1, demo=True)
        self.bot = Bot(self.g, seed=self.k)
        self.k += 1
        self.age = 0.0
        self.lvl = lvl

    def scene(self, cols, rows, dt):
        g = self.g
        self.age += dt
        g.update(min(dt, 0.1), self.bot)
        if g.level_i != self.lvl or g.over or self.age > 45:
            self.new_run()
        return render(self.g, cols, rows, hud=False)


LEFT, RIGHT, FIRE = ("left", "a"), ("right", "d"), (" ", "up", "w", "z")


class Controls:
    """Keys to (dx, fire pressed, fire held) via HeldKeys. Classic terminals: a direction counts as held while it
    repeats; the window that bridges the keyboard's initial repeat delay is learned from the first repeat."""

    def __init__(self, kitty):
        self.kitty = kitty
        self.held = HeldKeys(kitty, first=0.5, repeat=0.13)
        self.fedge = False
        self.first = {}
        self.delay = 0.45

    def reset(self):
        self.held.clear()
        self.fedge = False
        self.first = {}

    def feed(self, name, kind, now):
        if name in FIRE and kind == "press":
            self.fedge = True
        if not self.kitty and kind == "press" and name in LEFT + RIGHT:
            held_now = self.held.until.get(name, 0) > now
            if held_now and name in self.first:
                gap = now - self.first.pop(name)
                if 0.12 < gap < 0.8:
                    self.delay = clamp(self.delay * 0.5 + gap * 0.5, 0.2, 0.6)
                    self.held.first = min(0.55, self.delay + 0.08)
            elif not held_now:
                self.first[name] = now
        self.held.feed(name, kind, now)

    def sample(self, now):
        self.held.tick(now)
        dx = (1 if self.held.down(*RIGHT) else 0) - (1 if self.held.down(*LEFT) else 0)
        f = self.fedge
        self.fedge = False
        held = self.held.down(*FIRE)
        self.held.take_hits()
        return dx, f, held


class AutoRun:
    """Auto mode: the real game from the chosen district (three sparks, sound), played by the autopilot.
    After a game over the result stays for a few seconds, then a new round starts. No score is kept."""
    OVER_SHOW = 3.5

    def __init__(self, world, sound=True, seed=None, mode="campaign"):
        self.world, self.sound, self.seed, self.mode = world, sound, seed, mode
        self.auto = AutoMode()
        self.rounds = 0
        self.new()

    def new(self):
        self.rounds += 1
        start = self.world * 5 if self.mode == "campaign" else 0
        self.g = Game(self.mode, start, quiet=not self.sound, seed=None if self.seed is None else self.seed + self.rounds)
        self.bot = Bot(self.g, seed=None if self.seed is None else self.seed * 3 + self.rounds)
        self.mark = (self.g.level_i, self.g.deaths)
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
            if self.over_t >= self.OVER_SHOW:
                self.new()
                g = self.g
        else:
            for _ in range(self.auto.steps(dt, DT)):
                g.step(self.bot())
                if (g.level_i, g.deaths) != self.mark:
                    self.mark = (g.level_i, g.deaths)
                    self.bot.reset()
                if g.over:
                    break
        if not draw:
            return None
        cv = render(g, cols, rows)
        if g.over:
            render_over(g, cv, False, auto=True)
        self.auto.banner(cv, extra="round %d" % self.rounds)
        return cv


def run_auto(term, world):
    """Auto mode until the viewer stops it (Esc / Q)."""
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


def menu_items(world):
    return ["Campaign", "Endless", "World select   < %d %s >" % (world + 1, WORLDS[world]["short"]), AUTO_LABEL]


def render_menu(demo, cols, rows, sel, world, dt, help_, kitty):
    cv = demo.scene(cols, rows, dt)
    rec = load_scores().get(GAME, {})
    bits = []
    if rec.get("campaign"):
        bits.append("campaign %d" % rec["campaign"])
    if rec.get("endless"):
        bits.append("endless %d (hall %d)" % (rec["endless"], rec.get("endless_hall", 1)))
    best = ("best  " + "   ".join(bits)) if bits else None
    extra = ["", "The Gloam sealed the lamp town in glass.", "Keep the spark bouncing, break every pane.",
             "Keys: %s" % ("with releases (kitty protocol)" if kitty else "classic terminal mode")]
    title_screen(cv, NAME, TAGLINE, menu_items(world), sel, best, extra=extra,
                 keys="Up/Down choose   Left/Right world   Enter start   M %s   ? help   Esc back" % SND.label().lower(),
                 help_lines=help_lines(kitty), show_help=help_, dim=0.45)
    return cv


def too_small(term):
    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (60x22).")


def record(g):
    rec = submit(GAME, g.mode, g.score)
    if g.mode == "endless":
        submit(GAME, "endless_hall", g.level_i + 1)
    return rec


def play(term, ctl, mode, start):
    """One game. Returns 'again' or 'menu'."""
    g = Game(mode, start)
    ctl.reset()
    last = time.time()
    rec = None
    submitted = False
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
                if name in ("enter", " "):
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
                if not submitted and g.score:
                    record(g)
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
        if cols < 60 or rows < 22:
            too_small(term)
            g.paused = g.paused or not g.over
            time.sleep(0.2)
            last = time.time()
            continue
        if not g.paused:
            g.update(dt, ctl.sample(now))
        if g.over and not submitted:
            submitted = True
            rec = record(g)
        cv = render(g, cols, rows)
        if g.paused:
            overlay(cv, help_lines(ctl.kitty) if g.help else PAUSE_LINES + ["", SND.label()])
        elif g.over:
            render_over(g, cv, rec)
        term.write(cv.emit())
        time.sleep(max(0.0, 1 / 30 - (time.time() - now)))


def main():
    with KeyTerminal() as term:
        ctl = Controls(term.kitty)
        demo = TitleDemo()
        sel, world, help_ = 0, 0, False
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
            term.write(render_menu(demo, cols, rows, sel, world, min(0.1, now - last), help_, ctl.kitty).emit())
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
                elif k in ("left", "a"):
                    world = (world - 1) % 5
                    sel = sel if sel == 3 else 2
                    SND.play("menu")
                elif k in ("right", "d"):
                    world = (world + 1) % 5
                    sel = sel if sel == 3 else 2
                    SND.play("menu")
                elif k == "m":
                    if SND.toggle():
                        SND.play("sound_on")
                elif k in ("enter", " "):
                    SND.play("start")
                    go = True
            if not go:
                continue
            if sel == 3:
                run_auto(term, world)
                last = time.time()
                continue
            mode = "endless" if sel == 1 else "campaign"
            start = world * 5 if sel == 2 else 0
            while play(term, ctl, mode, start) == "again":
                pass
            last = time.time()


# =============================================================================================
# Self-test
# =============================================================================================
def run_bot(mode, level, limit=240.0, seed=1):
    """The autopilot plays one hall with endless sparks. Returns (cleared, game time, game)."""
    g = Game(mode, level, seed=seed, quiet=True)
    g.lives = 999
    bot = Bot(g, seed=seed)
    deaths = g.deaths
    t = 0.0
    while t < limit:
        g.step(bot())
        t += DT
        if g.deaths != deaths:
            deaths = g.deaths
            bot.reset()
        if g.state == "clear":
            return True, t, g
    return False, t, g


def selftest():
    t0 = time.time()
    global submit

    def no_scores(*a, **k):
        raise AssertionError("the self-test must not write scores")
    submit = no_scores
    random.seed(3)
    # 1. the halls: sizes, something to break, nothing sealed away behind iron
    assert len(LEVELS) == 25 and len(WORLDS) == 5
    kinds = {}
    for i, (w, name, boss, rows) in enumerate(LEVELS):
        assert len(rows) <= ROWS, name
        for r in rows:
            assert len(r) == COLS, "%s: row %r is %d wide" % (name, r, len(r))
            for ch in r:
                kinds[ch] = kinds.get(ch, 0) + 1
        assert not reachable(rows), "%s: panes sealed behind iron at %s" % (name, reachable(rows))
        assert (boss is not None) == (i % 5 == 4), name
        b = Board(rows, w)
        assert boss or b.required >= 10, name
    print("halls: 25 in 5 districts, %d panes (%d frosted, %d iron, %d powder, %d lantern, %d frost, %d sliding), "
          "5 keepers" % (sum(v for k, v in kinds.items() if k != "."), kinds["2"] + kinds["3"], kinds["#"], kinds["*"],
                         kinds["$"], kinds["%"], kinds["<"] + kinds[">"]))
    # 2. physics: a very fast spark never tunnels through a single row of panes; it never leaves the hall
    g = Game("campaign", 0, seed=1, quiet=True)
    g.board = Board([".............", ".............", ".............", "aaaaaaaaaaaaa"], 0)
    g.state = "play"
    tunnels = hits = 0
    for i in range(600):
        g.board = Board([".............", ".............", ".............", "aaaaaaaaaaaaa"], 0)
        a = math.radians(-80 + 160 * (i % 61) / 60)
        b = Ball(0.5 + (i * 0.37) % 25, 12.0, math.sin(a), -math.cos(a), 30.0 + (i % 7) * 25.0)
        g.norm(b)
        g.balls = [b]
        for _ in range(60):
            g.move_ball(b, DT)
            assert 0 <= b.x <= FW and b.y >= 0, "spark left the hall at %.2f, %.2f" % (b.x, b.y)
            if b.dy > 0:
                break
        if b.y < GY + 3:
            tunnels += 1
        hits += g.board.required < 13
    assert tunnels == 0, "%d sparks tunnelled through the panes" % tunnels
    print("physics: 600 sparks at 30-180 units/s against one row of panes: %d hits, no tunnelling" % hits)
    # the spark never sticks: in an iron cage with nothing to break it keeps coming back to the tray
    rows = ["#####.#######", "#a#.........#", "###.#.#.#.#.#", "#...........#", "#.#.#.#.#.#.#", ".............",
            "#...#...#...#"]
    worst = 0.0
    for seed in range(6):
        g = Game("campaign", 0, seed=seed, quiet=True)
        g.board = Board(rows, 0)
        g.enemy_t = 999
        g.lives = 99
        bot = Bot(g, seed=seed)
        last = 0.0
        for i in range(int(60 / DT)):
            before = [b.dy for b in g.balls]
            g.step(bot())
            for b in g.balls:
                if b.stuck is None and b.y > PY - 1.0:
                    worst = max(worst, g.level_t - last)
                    last = g.level_t
            for b in g.balls:
                assert abs(b.dy) >= MIN_VY - 1e-6 or b.stuck is not None, "a spark flies flat"
        assert worst < 20, "a spark stayed away from the tray for %.1f s" % worst
    print("no sticking: 6 x 60 s in an iron cage, the spark is back at the tray at least every %.1f s" % worst)
    # 3. every hall can be cleared by the autopilot with the real physics
    total = 0.0
    for i in range(len(LEVELS)):
        ok, tt, g = run_bot("campaign", i, limit=300, seed=i + 1)
        assert ok, "%s: the autopilot did not clear it in 300 s (%d panes left, boss hp %s)" % (
            LEVELS[i][1], g.board.required, g.boss.hp if g.boss else "-")
        total += tt
        if i % 5 == 4 or i < 1:
            print("clear: %-22s %5.1f s game time, %d sparks lost" % (LEVELS[i][1], tt, g.deaths))
    print("clear: all 25 halls by the autopilot, %.0f s of game time in all" % total)
    for d in (2, 7, 13):
        ok, tt, g = run_bot("endless", d, limit=300, seed=d)
        assert ok, "endless hall %d not cleared" % (d + 1)
    print("endless: generated halls 3, 8, 14 cleared; %d generated halls checked for sealed panes" % 60)
    for d in range(60):
        sp = gen_endless(d, random.Random(d))
        assert not reachable(sp["rows"]) and all(len(r) == COLS for r in sp["rows"]) and len(sp["rows"]) <= ROWS
    # 4. the rules
    g = Game("campaign", 0, seed=4, quiet=True)
    g.state = "play"
    g.board = Board(["**a..........", "aaa.........."], 0)
    g.damage(g.board.grid[0][0], 1)
    for _ in range(30):
        g.step((0, False, False))
    assert g.board.required == 0, "a powder pane did not set off its neighbours (%d left)" % g.board.required
    g = Game("campaign", 15, seed=5, quiet=True)
    g.state = "play"
    br = g.board.grid[0][0]
    g.balls = [Ball(13, 16, 0, 1)]
    g.damage(br, 1)
    assert g.board.grid[0][0] is None and g.board.regrow
    for _ in range(int((REGEN_T + 0.5) / DT)):
        g.balls = [Ball(13, 15, 0, 1)]
        g.step((0, False, False))
    assert g.board.grid[0][0] is not None, "frost did not grow back"
    g = Game("campaign", 5, seed=6, quiet=True)
    g.state = "play"
    m = g.board.movers[0]
    x0 = m.x
    for _ in range(30):
        g.step((0, False, False))
    assert m.x != x0, "a sliding pane does not slide"
    g = Game("campaign", 0, seed=7, quiet=True)
    g.state = "play"
    g.balls = [Ball(13, 10, 0.3, 1)]
    g.norm(g.balls[0])
    for k in POWERS:
        lives, nb = g.lives, len(g.balls)
        g.apply(k)
        if k == "multi":
            assert len(g.balls) == nb * 3
        elif k == "life":
            assert g.lives == lives + 1
        else:
            assert k in g.powers
    assert g.pw == PW_NARROW and "slow" not in g.powers and "fast" in g.powers
    g = Game("campaign", 0, seed=8, quiet=True)
    g.state = "play"
    g.powers["catch"] = 10
    b = g.balls[0]
    g.launch(b)
    b.x, b.y, b.dx, b.dy = g.px, PY - 3, 0.0, 1.0
    for _ in range(40):
        g.step((0, False, False))
    assert b.stuck is not None, "Tallow did not catch the spark"
    g.step((0, True, False))
    assert b.stuck is None, "a caught spark was not released"
    g = Game("campaign", 0, seed=9, quiet=True)
    g.state = "play"
    g.launch(g.balls[0])
    g.balls[0].y = 4
    g.powers["laser"] = 10
    req = g.board.required
    for _ in range(40):
        g.step((0, False, True))
    assert g.board.required < req, "flint bolts broke nothing"
    g = Game("campaign", 0, seed=10, quiet=True)
    g.state = "play"
    g.powers["barrier"] = 10
    b = g.balls[0]
    g.launch(b)
    g.px = 2.0
    b.x, b.y, b.dx, b.dy = 20.0, 17.0, 0.0, 1.0
    g.norm(b)
    for _ in range(30):
        g.step((0, False, False))
    assert g.balls and g.balls[0].dy < 0, "the Hearth line did not save the spark"
    g = Game("campaign", 0, seed=11, quiet=True)
    g.state = "play"
    b = g.balls[0]
    g.launch(b)
    e = Enemy("moth", 13.0, g.rnd)
    e.enter, e.x, e.y = False, 13.0, 14.0
    g.enemies = [e]
    b.x, b.y, b.dx, b.dy = 13.0, 16.0, 0.0, -1.0
    for _ in range(10):
        g.step((0, False, False))
    assert not g.enemies and b.dy > 0, "a creature did not turn the spark"
    g = Game("campaign", 0, seed=12, quiet=True)
    lives = g.lives
    g.add(EXTRA_FIRST)
    assert g.lives == lives + 1
    g.state = "play"
    g.balls = []
    g.lives = 1
    g.step((0, False, False))
    for _ in range(120):
        g.step((0, False, False))
    assert g.over and g.state == "over", "no game over with the last spark"
    g = Game("campaign", 4, seed=13, quiet=True)
    g.state = "play"
    g.boss.intro = 0
    hp = g.boss.hp
    g.boss_hit(13, 5)
    assert g.boss.hp == hp - 1
    g = Game("campaign", 24, seed=14, quiet=True)
    g.state = "play"
    g.boss.dead, g.boss.dead_t = True, 3.0
    g.step((0, False, False))
    for _ in range(int(3.0 / DT)):
        g.step((0, False, False))
    assert g.won and g.over, "beating the last keeper does not win"
    print("rules: powder chains, frost regrows, sliding panes, all 11 gifts, Tallow catch & release, Flint, "
          "Hearth, creatures turn the spark, extra spark, game over, keeper damage, the ending")
    # 5. the controls
    c = Controls(False)
    c.feed("right", "press", 0.0)
    held = [c.sample(t)[0] for t in (0.1, 0.3, 0.42)]
    for i in range(10):
        c.feed("right", "press", 0.45 + i * 0.033)
    held.append(c.sample(0.7)[0])
    gone = c.sample(1.4)[0]
    assert held == [1, 1, 1, 1] and gone == 0, "classic controls: %s / %s" % (held, gone)
    k = Controls(True)
    k.feed("left", "press", 0.0)
    a = k.sample(0.5)[0]
    k.feed("left", "release", 0.6)
    b = k.sample(0.61)[0]
    assert a == -1 and b == 0, "kitty controls"
    k.feed(" ", "press", 1.0)
    assert k.sample(1.01)[1] and not k.sample(1.02)[1]
    print("controls: classic repeat holds and stops, kitty releases, fire edge")
    # 6. rendering at every size, in every district and state
    n = 0
    timing = []
    for cols, rows in ((60, 22), (80, 24), (100, 32), (120, 40), (240, 70)):
        tr = te = 0.0
        frames = 0
        for lv in (1, 4, 7, 9, 12, 14, 17, 19, 21, 24):
            g = Game("campaign", lv, seed=lv, quiet=True)
            bot = Bot(g, seed=lv)
            for i in range(int(6 / DT)):
                g.step(bot())
            g.apply("multi")
            g.apply("laser")
            g.apply("barrier")
            for _ in range(20):
                g.step(bot())
            for state in ("play", "ready", "lost", "clear"):
                if state != "play":
                    g.state, g.state_t = state, 1.0
                a = time.time()
                cv = render(g, cols, rows)
                b = time.time()
                cv.emit(True)
                c_ = time.time()
                tr += b - a
                te += c_ - b
                frames += 1
            overlay(cv, help_lines(True))
            g.over = True
            render_over(g, cv, True)
            cv.emit(True)
        n += frames
        timing.append((cols, rows, tr / frames * 1000, te / frames * 1000))
    d = TitleDemo()
    for cols, rows in ((60, 22), (120, 40), (24, 8), (40, 12), (60, 30)):
        render_menu(d, cols, rows, 0, 2, 0.05, False, True).emit(True) if rows >= 20 else d.scene(cols, rows, 0.05)
        n += 1
    for _ in range(200):
        d.scene(30, 9, 0.1)
    print("rendering: %d frames at 60x22, 80x24, 100x32, 120x40, 240x70 (+ title, preview, overlays)" % n)
    for cols, rows, r_, e_ in timing:
        print("  %3dx%-3d render %5.1f ms  emit %5.1f ms  = %5.1f ms per frame (%3.0f fps)" % (
            cols, rows, r_, e_, r_ + e_, 1000 / max(0.1, r_ + e_)))
    # 7. auto mode: the real game at x8; pause, speed and stop work; no score kept
    run = AutoRun(0, sound=False, seed=31)
    assert run.g.lives == 3 and not run.g.demo
    run.key(" ")
    snap = (run.g.clock, run.g.score)
    for _ in range(30):
        run.frame(1 / 30, 70, 22, draw=False)
    assert (run.g.clock, run.g.score) == snap, "auto mode ran on while paused"
    run.key(" ")
    for _ in range(5):
        run.key("+")
    assert run.auto.speed == 8.0
    secs = 30
    for i in range(secs * 30):
        run.frame(1 / 30, 70 + i % 3 * 25, 22 + i % 2 * 10, draw=i % 30 == 0)
    assert run.key("esc") == "stop"
    print("auto mode: %d s at x8, reached %s hall %d with %d points, round %d, nothing recorded" % (
        secs, WORLDS[run.g.world]["short"].lower(), run.g.level_i % 5 + 1, run.g.score, run.rounds))
    # 8. simulation speed
    g = Game("campaign", 12, seed=2, quiet=True)
    bot = Bot(g, seed=2)
    g.lives = 99
    a = time.time()
    for _ in range(3000):
        g.step(bot())
    print("simulation: %.0f us per physics step with the autopilot" % ((time.time() - a) / 3000 * 1e6))
    print("Self-test ok (%.1f s)" % (time.time() - t0))


def screenshot(cols=100, rows=32):
    """README picture: real play in the Tide Cellar (hall 2-3 SHIPWRECK HOLD, seed 3) by the auto-mode pilot, 9 s in:
    three sparks after a Kindle, an x5 combo, gifts falling, Flint on the tray. Quiet (no sound), no score written;
    the HI field shows this run instead of a local record."""
    g = Game("campaign", 7, quiet=True, seed=3)
    g.hi = 0
    bot = Bot(g, seed=3)
    for _ in range(int(round(9.0 / DT))):
        g.step(bot())
    return render(g, cols, rows)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--auto" in sys.argv:
        with KeyTerminal() as _term:
            run_auto(_term, 0)
    else:
        main()
