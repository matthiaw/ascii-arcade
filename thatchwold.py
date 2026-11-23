#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""THATCHWOLD - raise a village, one season at a time.

Reeve Maudry leads a handful of thatchers out of the crowded lowlands to settle the empty wolds. Every turn is a
season: plan your fields, cottages and workshops on the map, read the forecast (+12 food, -4 wood), then end the
season and watch it happen. Farms grow in summer and are harvested in autumn, fisheries keep working, woodcutters
fell the woods, quarries cut the hills, mines and smithies turn ore into tools. Winter grows nothing and every hearth
burns wood, so the stores you lay up in autumn decide who sees the spring.

Placement matters: farms beside water and next to a mill yield more, woodcutters live off the trees around them,
markets off the cottages around them, wells and village greens cheer the houses near them, watchtowers keep wolves
and raiders away. A small lore track (crop rotation, masonry, milling, herb lore, trade charter, smelting,
stoneraising) unlocks better buildings. Droughts, fevers, floods, wolves, raiders, traders, wanderers and harvest
feasts come with choices.

Five scenarios from easy to hard - Brackenleigh (a gentle river valley), Larkholm (a trading island), Gorsecombe
(a marsh valley that floods), Harrowmoor (a cold highland with wolves) and Saltcrag (a raided coast where the Moot
Ring must rise) - each with a goal and a time limit, and an endless mode on a new map every time. Undo every
placement of the current season before you end it. The self-test lets the auto-mode reeve win every scenario.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
"""
import math
import random
import sys
import time

from arcadekit import (ACCENTS, AUTO_LABEL, PAUSE_LINES, AutoMode, Canvas, KeyTerminal, clamp, load_scores, mix,
                       overlay, shade, shared_key, submit, title_screen)
from arcadesound import Sound

GAME = "thatchwold"
NAME = "THATCHWOLD"
TAGLINE = "raise a village, season by season"
ACCENTS.setdefault(NAME, ((250, 222, 130), (150, 176, 74)))

MAP_W, MAP_H = 18, 12
SPRING, SUMMER, AUTUMN, WINTER = range(4)
SEASONS = ("Spring", "Summer", "Autumn", "Winter")
RES = ("food", "wood", "stone", "ore", "tools", "coin")
RES_NAME = {"food": "Food", "wood": "Wood", "stone": "Stone", "ore": "Ore", "tools": "Tools", "coin": "Coin",
            "lore": "Lore"}
RES_COL = {"food": (236, 196, 96), "wood": (196, 140, 84), "stone": (178, 184, 196), "ore": (204, 120, 96),
           "tools": (140, 186, 224), "coin": (250, 220, 110), "lore": (170, 150, 240)}
RANGE = 3                     # new buildings go within this many tiles of an existing one
NBR8 = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))

# =============================================================================================
# Terrain:  .  meadow   r  rich soil (a drained marsh)   s  sand   f  forest   h  hills   o  ore in the hills
#           ~  water    m  marsh   @  the Reeve's Hall (on meadow)
# =============================================================================================
TERRAIN = {".": "Meadow", "r": "Rich soil", "s": "Sand", "f": "Forest", "h": "Hills", "o": "Ore vein",
           "~": "Water", "m": "Marsh"}

# =============================================================================================
# Buildings. cost: what it takes; jobs: workers it needs; on: the ground it stands on
#   g = meadow or rich soil, s = sand too, h = hills, o = ore vein
# up: (name of the improved building, cost, lore it needs)
# =============================================================================================
B = {
    "hall": dict(name="Reeve's Hall", cost={}, jobs=0, on="", house=6,
                 text="Home of the reeve. Houses 6, gives food, wood and coin."),
    "cottage": dict(name="Cottage", cost={"wood": 5}, jobs=0, on="gs", house=4,
                    up=("Longhouse", {"wood": 4, "stone": 6}, "masonry"),
                    text="Houses 4 (a longhouse 7). Burns 1 wood in winter."),
    "farm": dict(name="Farm", cost={"wood": 4}, jobs=2, on="gs", up=("Ploughed farm", {"wood": 2, "tools": 2}, None),
                 text="Food: half in spring, full in summer, harvest in autumn, none in winter."),
    "fishery": dict(name="Fishery", cost={"wood": 4}, jobs=1, on="gs", up=("Fish weir", {"wood": 3, "tools": 1}, None),
                    text="On a shore: 1 food per water tile around (up to 2), all year."),
    "woodcut": dict(name="Woodcutter", cost={"wood": 3}, jobs=1, on="gs", up=("Saw pit", {"wood": 2, "tools": 2}, None),
                    text="1 wood, +1 per forest tile around (up to 3 more)."),
    "quarry": dict(name="Quarry", cost={"wood": 5}, jobs=2, on="h", up=("Deep quarry", {"wood": 2, "tools": 2}, None),
                   text="On hills: 2 stone, +1 with two more hills around."),
    "mine": dict(name="Ore mine", cost={"wood": 6, "stone": 4}, jobs=2, on="o",
                 text="On an ore vein: 2 ore. Its props burn 1 wood a season."),
    "smithy": dict(name="Smithy", cost={"wood": 6, "stone": 6}, jobs=1, on="gs",
                   text="Turns up to 2 ore into 2 tools (1 wood for charcoal)."),
    "mill": dict(name="Mill", cost={"wood": 6, "stone": 6, "tools": 1}, jobs=1, on="gs", tech="milling",
                 text="Every farm next to it grows 1 more food per season."),
    "market": dict(name="Market", cost={"wood": 8, "stone": 6}, jobs=2, on="gs",
                   text="2 coin, +1 per house around (up to 4). Cheers the village."),
    "well": dict(name="Well", cost={"stone": 5}, jobs=0, on="gs",
                 text="Houses within 2 are happier, safe from fire and fever."),
    "green": dict(name="Village green", cost={"wood": 4, "coin": 3}, jobs=0, on="gs",
                  text="Houses within 2 are happier. Feasts cheer more."),
    "store": dict(name="Storehouse", cost={"wood": 10, "stone": 4}, jobs=0, on="gs",
                  text="Room for 60 more of every good."),
    "tower": dict(name="Watchtower", cost={"wood": 6, "stone": 6}, jobs=1, on="gs",
                  text="Keeps wolves and raiders off within 3 tiles."),
    "lore": dict(name="Lore house", cost={"wood": 8, "stone": 8, "coin": 2}, jobs=2, on="gs",
                 text="2 lore a season (+1 by a green). Costs 1 coin a season."),
    "ring": dict(name="Moot Ring", cost={"wood": 30, "stone": 40, "tools": 12, "coin": 30}, jobs=0, on="g",
                 tech="stones", text="Standing stones for the moot: the village's pride."),
}
TOOLS = {
    "clear": dict(name="Clear woods", cost={}, text="Fell a forest tile into meadow: +3 wood."),
    "drain": dict(name="Drain marsh", cost={"wood": 4, "tools": 1}, text="Marsh becomes rich soil (farms +1)."),
    "improve": dict(name="Improve", cost={}, text="Upgrade the building under the cursor."),
    "demolish": dict(name="Demolish", cost={}, text="Pull it down: half its wood and stone back."),
}
MENU = ["cottage", "farm", "fishery", "woodcut", "quarry", "well", "green", "store", "lore", "market", "mill", "mine",
        "smithy", "tower", "ring", "clear", "drain", "improve", "demolish"]
HOUSES = ("hall", "cottage")
PRIO = {"farm": 0, "fishery": 0, "woodcut": 1, "quarry": 2, "mine": 3, "smithy": 4, "mill": 5, "market": 6,
        "lore": 7, "tower": 8}

TECHS = [  # (id, name, lore, what it does)
    ("rotation", "Crop rotation", 6, "farms +1 food"),
    ("masonry", "Masonry", 8, "longhouses, quarries +1"),
    ("milling", "Milling", 8, "the mill"),
    ("herbs", "Herb lore", 7, "fevers halved, mood +3"),
    ("charter", "Trade charter", 10, "markets +2, fair traders"),
    ("smelting", "Smelting", 10, "mines +1, smithies +1"),
    ("stones", "Stoneraising", 14, "the Moot Ring"),
]
TECH = {t[0]: t for t in TECHS}

FARM_SEASON = ((0.5, 1.0, 1.5, 0.0), (0.5, 1.0, 1.25, 0.0))     # mild, harsh
FISH_SEASON = (1.0, 1.0, 1.0, 0.5)

# =============================================================================================
# Scenarios: 18 x 12 maps, easy to hard
# =============================================================================================
SCENARIOS = [
    dict(name="Brackenleigh", short="Brackenleigh", level="easy", weight=1.0, years=8, goal=("pop", 36),
         blurb=["A gentle river valley with woods,", "hills and a quiet pond."],
         flags=set(), seed=11, start=dict(food=26, wood=26, stone=6, ore=0, tools=4, coin=6), pop=6,
         map=["fffff...hhh..~~...",
              "ffff....hoh..~....",
              "fff..........~~...",
              "ff.f...f......~...",
              "ff....ff......~~..",
              "f........@.....~..",
              "ff...~~.........~.",
              "fff..~....ff....~.",
              "ff.......fff...~~.",
              "f...hh.........~..",
              "...hhoh.......~~..",
              "..hhh........~~..."]),
    dict(name="Larkholm", short="Larkholm", level="fair", weight=1.3, years=8, goal=("coin", 70),
         blurb=["A small island on the trade lanes.", "Little timber, much sea, many barges."],
         flags={"storms", "traders"}, seed=23, start=dict(food=24, wood=24, stone=6, ore=0, tools=4, coin=8), pop=6,
         map=["~~~~~~~~~~~~~~~~~~",
              "~~~~~sss~~~~~~~~~~",
              "~~~~ss.ffs~~~~~~~~",
              "~~~s...fff.s~~~~~~",
              "~~s..h.....ss~~~~~",
              "~~s.hho..@...s~~~~",
              "~~~s.h.......s~~~~",
              "~~~s.....ff..ss~~~",
              "~~~~s...fff...s~~~",
              "~~~~~ss.....ss~~~~",
              "~~~~~~~ssss~~~~~~~",
              "~~~~~~~~~~~~~~~~~~"]),
    dict(name="Gorsecombe", short="Gorsecombe", level="fair", weight=1.5, years=8, goal=("pop", 48),
         blurb=["A marsh valley the river floods", "each spring. Drain it for rich soil."],
         flags={"floods"}, seed=37, start=dict(food=24, wood=24, stone=6, ore=0, tools=5, coin=6), pop=6,
         map=["hhh...fff...fffhhh",
              "ho....ff.......hoh",
              "h...............hh",
              "f.......mmm.....f.",
              "ff..mm...@..mm...f",
              "~~mmm~~mm...m~~mm~",
              "m~~~~mm~~~~~~~m~~~",
              "mm..m~~~mmm~~~~mmm",
              "...mm...mm.mmm....",
              "ff.........m....ff",
              "fff..hh.........ff",
              "ffff.hoh.......fff"]),
    dict(name="Harrowmoor", short="Harrowmoor", level="hard", weight=1.8, years=9, goal=("ring", 0),
         blurb=["A cold highland: short harvests,", "hungry winters, wolves in the woods."],
         flags={"harsh", "wolves"}, seed=41, start=dict(food=28, wood=24, stone=8, ore=0, tools=5, coin=6), pop=6,
         map=["hhhhh..fffff..hhhh",
              "hhoh....ffff...hoh",
              "hh.......ff.....hh",
              "h...~~...........h",
              "f..~~~~...hh.....f",
              "ff..~~..@.hoh...ff",
              "fff.......hh....ff",
              "ff..f.........mmff",
              "f..fff..hh....mm.f",
              "h...ff..hoh......h",
              "hh.......h.....hhh",
              "hhhh..........hhhh"]),
    dict(name="Saltcrag", short="Saltcrag", level="hardest", weight=2.2, years=9, goal=("popring", 40),
         blurb=["A raided coast below the crags.", "Grow to 40 and raise the Moot Ring."],
         flags={"raiders", "wolves", "storms"}, seed=53,
         start=dict(food=24, wood=22, stone=6, ore=0, tools=4, coin=6), pop=6,
         map=["fffff....hhh...~~~",
              "ffff.....hoh...~~~",
              "fff..........s~~~~",
              "ff..mm.......s~~~~",
              "f...mm...@...ss~~~",
              "ff.........hh.s~~~",
              "fff....~~...hhs~~~",
              "ff....~~~....ss~~~",
              "f......~.....s~~~~",
              "hh..........ss~~~~",
              "hoh.....sssss~~~~~",
              "hhh..sss~~~~~~~~~~"]),
    dict(name="Endless", short="Endless", level="free", weight=1.0, years=0, goal=("endless", 0),
         blurb=["A new wold every time. Grow as", "long as you like; score: prosperity."],
         flags={"wolves", "floods", "traders"}, seed=None,
         start=dict(food=26, wood=26, stone=6, ore=0, tools=4, coin=6), pop=6, map=None),
]
ENDLESS = len(SCENARIOS) - 1


def gen_map(seed):
    """A seeded wold for endless mode: a river, woods, hills with ore, marsh along the water, the hall in a
    meadow with timber and stone in reach."""
    rng = random.Random(seed)
    W, H = MAP_W, MAP_H
    while True:
        g = [["."] * W for _ in range(H)]
        # river from one edge to another, wandering
        if rng.random() < 0.5:
            x = rng.randrange(4, W - 4)
            for y in range(H):
                g[y][x] = "~"
                if rng.random() < 0.5 and 0 < x + 1 < W:
                    g[y][min(W - 1, x + 1)] = "~"
                x = clamp(x + rng.choice((-1, 0, 0, 1)), 1, W - 2)
        else:
            y = rng.randrange(3, H - 3)
            for x in range(W):
                g[y][x] = "~"
                if rng.random() < 0.4:
                    g[min(H - 1, y + 1)][x] = "~"
                y = clamp(y + rng.choice((-1, 0, 0, 0, 1)), 1, H - 2)

        def blob(ch, n, size, on="."):
            for _ in range(n):
                cx, cy = rng.randrange(W), rng.randrange(H)
                for _ in range(size):
                    if 0 <= cx < W and 0 <= cy < H and g[cy][cx] in on:
                        g[cy][cx] = ch
                    cx += rng.choice((-1, 0, 1))
                    cy += rng.choice((-1, 0, 1))
        blob("f", 5, 12)
        blob("h", 3, 7)
        blob("o", 3, 1, on="h")
        for y in range(H):
            for x in range(W):
                if g[y][x] == "." and rng.random() < 0.35 and any(
                        0 <= x + dx < W and 0 <= y + dy < H and g[y + dy][x + dx] == "~" for dx, dy in NBR8):
                    g[y][x] = "m"
        best, pos = -1, None
        for y in range(2, H - 2):
            for x in range(2, W - 2):
                if g[y][x] != ".":
                    continue
                near = [g[y + dy][x + dx] for dy in range(-6, 7) for dx in range(-6, 7)
                        if 0 <= x + dx < W and 0 <= y + dy < H]
                meadow = sum(1 for dy in range(-3, 4) for dx in range(-3, 4)
                             if 0 <= x + dx < W and 0 <= y + dy < H and g[y + dy][x + dx] == ".")
                if "f" in near and "h" in near and "o" in near and "~" in near and meadow > best:
                    best, pos = meadow, (x, y)
        if pos and best >= 20:
            g[pos[1]][pos[0]] = "@"
            return ["".join(r) for r in g]


# =============================================================================================
# The settlement: map, buildings, stores, people, mood, lore; the economy of one season
# =============================================================================================
def cost_text(cost):
    return " ".join("%d %s" % (v, k) for k, v in cost.items()) if cost else "free"


class State:
    def __init__(self, sc_index, seed=None):
        sc = SCENARIOS[sc_index]
        self.sc_i, self.sc = sc_index, sc
        self.seed = seed if seed is not None else (sc["seed"] if sc["seed"] is not None else random.randrange(1 << 30))
        rows = sc["map"] or gen_map(self.seed)
        assert len(rows) == MAP_H and all(len(r) == MAP_W for r in rows), sc["name"]
        self.ter = [list(r) for r in rows]
        self.bld = {}
        for y, r in enumerate(rows):
            for x, ch in enumerate(r):
                if ch == "@":
                    self.ter[y][x] = "."
                    self.hall = (x, y)
                    self.bld[(x, y)] = ("hall", 1)
        self.res = dict(sc["start"])
        self.pop = sc["pop"]
        self.mood = 55.0
        self.mood_temp = 0.0
        self.lore = 0
        self.techs = set()
        self.study = TECHS[0][0]
        self.turn = 0
        self.mods = {}
        self.event = None
        self.over = None           # None, "won" or "lost"
        self.why = ""
        self.peak = 0              # the best prosperity so far (endless score)
        self.log = []
        self.born = self.lost = 0
        self.ver = 0
        self._rng = None
        self.flags = sc["flags"]
        self.harsh = "harsh" in self.flags

    # ---- time
    @property
    def season(self):
        return self.turn % 4

    @property
    def year(self):
        return self.turn // 4 + 1

    @property
    def left(self):
        """Seasons left in a scenario (None in endless)."""
        return None if self.sc["years"] == 0 else self.sc["years"] * 4 - self.turn

    def when(self):
        return "%s, year %d" % (SEASONS[self.season], self.year)

    # ---- map helpers
    def inside(self, x, y):
        return 0 <= x < MAP_W and 0 <= y < MAP_H

    def around(self, x, y):
        for dx, dy in NBR8:
            if 0 <= x + dx < MAP_W and 0 <= y + dy < MAP_H:
                yield x + dx, y + dy

    def count_ter(self, x, y, chars):
        return sum(1 for a, b in self.around(x, y) if self.ter[b][a] in chars and (a, b) not in self.bld)

    def count_bld(self, x, y, kinds):
        return sum(1 for p in self.around(x, y) if p in self.bld and self.bld[p][0] in kinds)

    def has(self, kind):
        return any(k == kind for k, _ in self.bld.values())

    def num(self, kind):
        return sum(1 for k, _ in self.bld.values() if k == kind)

    def in_range(self, x, y):
        return any(max(abs(x - a), abs(y - b)) <= RANGE for a, b in self.bld)

    def reach(self):
        """Every tile within range of a building (for the map overlay and the bot)."""
        out = set()
        for a, b in self.bld:
            for y in range(max(0, b - RANGE), min(MAP_H, b + RANGE + 1)):
                for x in range(max(0, a - RANGE), min(MAP_W, a + RANGE + 1)):
                    out.add((x, y))
        return out

    def cover(self, kind, r=2):
        """The share of houses within r tiles of a building of this kind."""
        houses = [p for p, (k, _) in self.bld.items() if k in HOUSES]
        srcs = [p for p, (k, _) in self.bld.items() if k == kind]
        if not houses or not srcs:
            return 0.0
        n = sum(1 for (x, y) in houses if any(max(abs(x - a), abs(y - b)) <= r for a, b in srcs))
        return n / len(houses)

    def guarded(self, x, y):
        return any(k == "tower" and max(abs(x - a), abs(y - b)) <= 3 for (a, b), (k, _) in self.bld.items())

    def cap(self, r):
        n = self.num("store")
        if r == "coin":
            return 150 + 50 * n
        return (80 if r == "food" else 60) + 60 * n

    def housing(self):
        return sum(house_of(k, t) for k, t in self.bld.values())

    def snapshot(self):
        return ([row[:] for row in self.ter], dict(self.bld), dict(self.res))

    def restore(self, snap):
        self.ter = [row[:] for row in snap[0]]
        self.bld = dict(snap[1])
        self.res = dict(snap[2])
        self.ver += 1


def house_of(kind, tier):
    if kind == "hall":
        return 6
    if kind == "cottage":
        return 7 if tier > 1 else 4
    return 0


def bname(kind, tier):
    if tier > 1 and "up" in B[kind]:
        return B[kind]["up"][0]
    return B[kind]["name"]


def output(st, x, y, kind, tier, season, mods):
    """What one building gives in a season at full staff, before mood: ({res: amount}, [reasons])."""
    tc = st.techs
    notes = []
    if kind == "hall":
        return {"food": 2, "wood": 1, "coin": 1}, notes
    if kind == "farm":
        base = 4
        if "rotation" in tc:
            base += 1
            notes.append("rotation +1")
        if tier > 1:
            base += 2
            notes.append("plough +2")
        water = st.count_ter(x, y, "~") > 0
        if water:
            base += 1
            notes.append("water +1")
        if st.count_bld(x, y, ("mill",)):
            base += 1
            notes.append("mill +1")
        if st.ter[y][x] == "r":
            base += 1
            notes.append("rich soil +1")
        elif st.ter[y][x] == "s":
            base -= 1
            notes.append("sand -1")
        k = FARM_SEASON[1 if st.harsh else 0][season] * mods.get("farm", 1.0)
        if water and "flood" in mods:
            k *= mods["flood"]
        return {"food": base * k}, notes
    if kind == "fishery":
        n = min(2, st.count_ter(x, y, "~"))
        notes.append("water %d" % n)
        if tier > 1:
            n += 1
            notes.append("weir +1")
        return {"food": n * FISH_SEASON[season] * mods.get("fish", 1.0)}, notes
    if kind == "woodcut":
        n = min(3, st.count_ter(x, y, "f"))
        notes.append("forest +%d" % n)
        if tier > 1:
            n += 1
            notes.append("saw pit +1")
        return {"wood": 1 + n}, notes
    if kind == "quarry":
        n = 2
        if st.count_ter(x, y, "ho") + st.count_bld(x, y, ("quarry", "mine")) >= 2:
            n += 1
            notes.append("hills +1")
        if "masonry" in tc:
            n += 1
            notes.append("masonry +1")
        if tier > 1:
            n += 2
            notes.append("deep +2")
        return {"stone": n}, notes
    if kind == "mine":
        n = 2 + (1 if "smelting" in tc else 0)
        return {"ore": n}, notes
    if kind == "market":
        n = min(4, st.count_bld(x, y, HOUSES))
        notes.append("houses +%d" % n)
        c = 2 + n
        if "charter" in tc:
            c += 2
            notes.append("charter +2")
        return {"coin": c}, notes
    return {}, notes


def mood_factor(mood):
    return 0.8 if mood < 30 else 1.1 if mood >= 75 else 1.0


class Econ:
    """One season's economy: delta per resource (whole numbers), what each building gives, jobs, housing."""
    pass


def economy(st, season=None, pop=None, res=None):
    season = st.season if season is None else season
    mods = st.mods if season == st.season else {}
    pop = st.pop if pop is None else pop
    res = st.res if res is None else res
    mf = mood_factor(st.mood)
    e = Econ()
    d = dict.fromkeys(RES + ("lore",), 0)
    per = {}
    free = pop
    jobs = 0
    houses = 0
    later = []
    for (x, y), (k, t) in sorted(st.bld.items(), key=lambda it: (PRIO.get(it[1][0], 9), it[0][1], it[0][0])):
        need = B[k]["jobs"]
        got = min(need, free)
        free -= got
        jobs += need
        if k in HOUSES:
            houses += 1
        if k in ("smithy", "lore"):
            later.append(((x, y), k, t, got, need))
            continue
        out, notes = output(st, x, y, k, t, season, mods)
        eff = got / need if need else 1.0
        o = {}
        for r, v in out.items():
            o[r] = int(v * eff * (mf if k != "hall" else 1.0) + 0.5)
        if k == "mine" and got:
            o["wood"] = o.get("wood", 0) - 1
        for r, v in o.items():
            d[r] += v
        per[(x, y)] = (o, got, need, notes)
    ore = res["ore"] + d["ore"]
    coin = res["coin"] + d["coin"]
    for (x, y), k, t, got, need in later:
        eff = got / need if need else 1.0
        notes = []
        o = {}
        if k == "smithy":
            conv = min(int(2 * eff + 0.5), max(0, ore))
            if conv:
                ore -= conv
                o = {"ore": -conv, "tools": conv + (1 if "smelting" in st.techs else 0), "wood": -1}
            else:
                notes.append("no ore")
        else:
            if got and coin >= 1:
                coin -= 1
                g = 2 + (1 if st.count_bld(x, y, ("green",)) else 0)
                o = {"lore": int(g * eff * mf + 0.5), "coin": -1}
                if g > 2:
                    notes.append("green +1")
            elif got:
                notes.append("no coin")
        for r, v in o.items():
            d[r] += v
        per[(x, y)] = (o, got, need, notes)
    d["coin"] += pop // 8
    e.tithe = pop // 8
    e.heat = houses if season == WINTER else 0
    d["wood"] -= e.heat
    e.eat = int(math.ceil(pop * (1.5 if st.harsh and season == WINTER else 1.0)))
    d["food"] -= e.eat
    e.delta, e.per, e.jobs, e.filled, e.idle = d, per, jobs, pop - free, free
    e.houses = houses
    e.housing = st.housing()
    e.season = season
    return e


def mood_target(st):
    t = 50.0
    t += 10 * st.cover("well") + 12 * st.cover("green")
    if st.has("market"):
        t += 5
    if st.has("fishery") and st.has("farm"):
        t += 4
    if st.has("ring"):
        t += 10
    if "herbs" in st.techs:
        t += 3
    if st.pop > st.housing():
        t -= 3 * (st.pop - st.housing())
    return t


def births_for(st, pop, food_after, mood):
    free = st.housing() - pop
    if free <= 0 or mood < 35 or food_after < pop * 0.5:
        return 0
    return min(free, 1 + int(pop * (mood - 30) / 300))


def forecast(st):
    """What ending this season will do (without events): Econ plus the births, the losses and the next mood."""
    e = economy(st)
    food = st.res["food"] + e.delta["food"]
    wood = st.res["wood"] + e.delta["wood"]
    e.starve = int(math.ceil(-food / 2)) if food < 0 else 0
    e.cold = -wood if wood < 0 and st.season == WINTER else 0
    e.freeze = e.cold // 2
    e.births = 0 if st.season == WINTER or e.starve else births_for(st, st.pop, food, st.mood)
    e.full = [r for r in RES if st.res[r] + e.delta[r] > st.cap(r)]
    m = st.mood + (mood_target(st) + st.mood_temp - st.mood) * 0.5
    if e.starve:
        m -= 25
    if e.cold:
        m -= 15
    e.mood = clamp(m, 0, 100)
    return e


def project(st, n=4, extra_pop=0):
    """Food in store after each of the next n seasons with the buildings of today (no events, no births):
    the bot's and the panel's look ahead at winter."""
    out = []
    food = st.res["food"]
    wood = st.res["wood"]
    keep_turn, keep_mods = st.turn, st.mods
    try:
        for i in range(n):
            st.turn = keep_turn + i
            st.mods = keep_mods if i == 0 else {}
            e = economy(st, pop=st.pop + extra_pop, res=dict(st.res, food=max(0, food), wood=max(0, wood)))
            food = min(st.cap("food"), food + e.delta["food"])
            wood = min(st.cap("wood"), wood + e.delta["wood"])
            out.append((food, wood))
    finally:
        st.turn, st.mods = keep_turn, keep_mods
    return out


# =============================================================================================
# Placing: rules, costs, undo snapshots live in the Game; these only check and change the State
# =============================================================================================
def affordable(st, cost):
    return all(st.res.get(r, 0) >= v for r, v in cost.items())


def can_do(st, item, x, y):
    """(ok, reason) for using a build-menu item on tile (x, y)."""
    if not st.inside(x, y):
        return False, "off the map"
    ter = st.ter[y][x]
    here = st.bld.get((x, y))
    if item == "improve":
        if not here:
            return False, "nothing to improve here"
        k, t = here
        up = B[k].get("up")
        if not up:
            return False, "%s cannot be improved" % B[k]["name"]
        if t > 1:
            return False, "already improved"
        if up[2] and up[2] not in st.techs:
            return False, "needs %s" % TECH[up[2]][1]
        if not affordable(st, up[1]):
            return False, "needs " + cost_text(up[1])
        return True, "%s: %s" % (up[0], cost_text(up[1]))
    if item == "demolish":
        if not here:
            return False, "nothing to pull down"
        if here[0] == "hall":
            return False, "the hall stays"
        return True, "pull down the %s" % bname(*here)
    if here:
        return False, "%s stands here" % bname(*here)
    if not st.in_range(x, y):
        return False, "too far from the village"
    if item == "clear":
        return (True, "fell the trees: +3 wood") if ter == "f" else (False, "only forest can be cleared")
    if item == "drain":
        if ter != "m":
            return False, "only marsh can be drained"
        if not affordable(st, TOOLS["drain"]["cost"]):
            return False, "needs " + cost_text(TOOLS["drain"]["cost"])
        return True, "drain into rich soil"
    bd = B[item]
    on = bd["on"]
    okter = (ter in ".r" and "g" in on) or (ter == "s" and "s" in on) or (ter == "h" and "h" in on) or \
            (ter == "o" and "o" in on)
    if not okter:
        need = {"h": "hills", "o": "an ore vein"}.get(on, "meadow" if on == "g" else "meadow or sand")
        return False, "%s needs %s" % (bd["name"], need)
    if item == "fishery" and not st.count_ter(x, y, "~"):
        return False, "a fishery needs water beside it"
    if bd.get("tech") and bd["tech"] not in st.techs:
        return False, "needs the lore of %s" % TECH[bd["tech"]][1]
    if item == "ring" and st.has("ring"):
        return False, "there is one Moot Ring"
    if not affordable(st, bd["cost"]):
        return False, "needs " + cost_text(bd["cost"])
    return True, "%s: %s" % (bd["name"], cost_text(bd["cost"]))


def do_item(st, item, x, y):
    """Use a build-menu item (after can_do said yes). Returns a short message."""
    st.ver += 1
    if item == "improve":
        k, t = st.bld[(x, y)]
        up = B[k]["up"]
        for r, v in up[1].items():
            st.res[r] -= v
        st.bld[(x, y)] = (k, 2)
        return "improved to %s" % up[0]
    if item == "demolish":
        k, t = st.bld.pop((x, y))
        back = {r: v // 2 for r, v in B[k]["cost"].items() if r in ("wood", "stone")}
        for r, v in back.items():
            st.res[r] = min(st.cap(r), st.res[r] + v)
        return "pulled down the %s" % bname(k, t)
    if item == "clear":
        st.ter[y][x] = "."
        st.res["wood"] = min(st.cap("wood"), st.res["wood"] + 3)
        return "cleared the woods: +3 wood"
    if item == "drain":
        for r, v in TOOLS["drain"]["cost"].items():
            st.res[r] -= v
        st.ter[y][x] = "r"
        return "drained the marsh"
    for r, v in B[item]["cost"].items():
        st.res[r] -= v
    st.bld[(x, y)] = (item, 1)
    return "built a %s" % B[item]["name"].lower()


# =============================================================================================
# Events: one may come at the start of a season, each with a choice
# =============================================================================================
class Event:
    def __init__(self, eid, title, text, options):
        self.id, self.title, self.text, self.options = eid, title, text, options


def opt(label, cost=None, do=None, hint=""):
    return dict(label=label, cost=cost or {}, do=do or (lambda st: ""), hint=hint)


def _lose_frac(st, frac, res=("food", "wood")):
    lost = []
    for r in res:
        n = int(st.res[r] * frac)
        st.res[r] -= n
        if n:
            lost.append("%d %s" % (n, r))
    return ", ".join(lost) or "nothing"


def _kill(st, n):
    n = min(n, st.pop - 1)
    st.pop -= n
    st.lost += n
    return n


def ev_trader(st, rng):
    ch = "charter" in st.techs
    food_price = 4 if ch else 6
    wood_back = 6 if ch else 4
    return Event("trader", "Traders at the landing",
                 ["A barge of traders ties up and spreads", "its wares on the bank."],
                 [opt("Buy 12 food", {"coin": food_price}, lambda s: _gain(s, food=12)),
                  opt("Buy 3 tools", {"coin": 8 if not ch else 6}, lambda s: _gain(s, tools=3)),
                  opt("Sell 10 wood for %d coin" % wood_back, {"wood": 10}, lambda s: _gain(s, coin=wood_back)),
                  opt("Sell 8 stone for %d coin" % (wood_back + 1), {"stone": 8},
                      lambda s: _gain(s, coin=wood_back + 1)),
                  opt("Wave them on")])


def _gain(st, **kw):
    for r, v in kw.items():
        st.res[r] = min(st.cap(r), st.res[r] + v)
    return "+" + ", +".join("%d %s" % (v, r) for r, v in kw.items())


def _mods(st, **kw):
    st.mods.update(kw)
    return ""


def _cheer(st, n):
    st.mood_temp += n
    return ("mood +%d" % n) if n >= 0 else ("mood %d" % n)


def ev_drought(st, rng):
    if st.season != SUMMER or not st.has("farm"):
        return None
    return Event("drought", "Drought", ["The brook runs thin and the fields crack.", "Farms will suffer this summer."],
                 [opt("Dig a channel", {"wood": 6}, hint="farms unharmed"),
                  opt("Carry water by hand", do=lambda s: (_mods(s, farm=0.75), _cheer(s, -8))[1],
                      hint="farms at 3/4, mood -8"),
                  opt("Let it be", do=lambda s: _mods(s, farm=0.5), hint="farms at half")])


def ev_fever(st, rng):
    if st.pop < 10 or st.cover("well") > 0.85:
        return None
    k = 0.5 if "herbs" in st.techs else 1.0
    lose = max(1, int(st.pop * k / 6))
    small = max(1, lose // 3)
    return Event("fever", "Fever", ["A fever goes round the cottages."],
                 [opt("Brew herbs", {"coin": 5}, hint="nobody is lost"),
                  opt("Keep the sick apart", do=lambda s: "%d lost, %s" % (_kill(s, small), _cheer(s, -10)),
                      hint="%d lost, mood -10" % small),
                  opt("Hope for the best", do=lambda s: "%d lost" % _kill(s, lose), hint="%d lost" % lose)])


def ev_feast(st, rng):
    if st.season != AUTUMN or st.res["food"] < st.pop:
        return None
    n = st.pop // 2
    up = 15 + (5 if st.has("green") else 0)
    return Event("feast", "Harvest feast", ["The harvest is in. The folk want", "a feast on the green."],
                 [opt("Hold the feast", {"food": n}, lambda s: _cheer(s, up), hint="mood +%d" % up),
                  opt("Not this year", do=lambda s: _cheer(s, -5), hint="mood -5")])


def ev_wolves(st, rng):
    if "wolves" not in st.flags or st.season not in (AUTUMN, WINTER):
        return None
    if st.guarded(*st.hall):
        return Event("wolves", "Wolves", ["Wolves come down from the woods, but", "the watch drives them off."],
                     [opt("Well done", do=lambda s: _cheer(s, 3), hint="mood +3")])
    return Event("wolves", "Wolves", ["Wolves circle the village at night.",
                                      "(A watchtower near the hall stops this.)"],
                 [opt("Hunt them", {"tools": 2}, lambda s: _gain(s, food=4), hint="+4 food"),
                  opt("Bar the doors", do=lambda s: "lost %d food" % _take(s, "food", 8), hint="lose 8 food")])


def _take(st, r, n):
    n = min(n, st.res[r])
    st.res[r] -= n
    return n


def ev_raiders(st, rng):
    if "raiders" not in st.flags or st.year < 3:
        return None
    t = st.num("tower")
    if t >= 2:
        fight, hint = (lambda s: _cheer(s, 6)), "two towers: they flee, mood +6"
    elif t == 1:
        fight, hint = (lambda s: "lost " + _lose_frac(s, 0.25)), "one tower: lose 1/4 food and wood"
    else:
        fight, hint = (lambda s: "lost %s and %d folk" % (_lose_frac(s, 0.5), _kill(s, 2))), \
            "no tower: lose half the food and wood, 2 folk"
    return Event("raiders", "Raiders", ["Longboats are beached below the crags.", "Raiders want tribute."],
                 [opt("Pay them off", {"coin": 10}, hint="they leave"),
                  opt("Stand and fight", do=fight, hint=hint)])


def ev_flood(st, rng):
    if "floods" not in st.flags or st.season != SPRING:
        return None
    return Event("flood", "Spring flood", ["Meltwater swells the river over", "its banks."],
                 [opt("Raise the banks", {"stone": 8}, hint="no harm"),
                  opt("Let it run", do=_let_flood, hint="farms by water: nothing now, +50% in summer")])


def _let_flood(st):
    st.mods["flood"] = 0.0
    st.silt = True
    return ""


def ev_settlers(st, rng):
    if st.season == WINTER or st.housing() - st.pop < 3:
        return None
    return Event("settlers", "Wanderers", ["A family walks in from the far side", "of the wold, asking to stay."],
                 [opt("Take them in", do=lambda s: _arrive(s, 3), hint="+3 folk"),
                  opt("Send them on")])


def _arrive(st, n):
    st.pop += n
    st.born += n
    return "+%d folk" % n


def ev_fire(st, rng):
    if st.pop < 12:
        return None
    wells = [p for p, (k, _) in st.bld.items() if k == "well"]
    bare = sorted(p for p, (k, _) in st.bld.items() if k == "cottage" and not any(
        max(abs(p[0] - a), abs(p[1] - b)) <= 2 for a, b in wells))
    if not bare:
        return None
    p = bare[rng.randrange(len(bare))]

    def burn(s):
        if p in s.bld:
            del s.bld[p]
            s.ver += 1
        over = s.pop - s.housing()
        if over > 0:
            return "the cottage is lost, %d folk leave" % _kill(s, over)
        return "the cottage is lost"
    return Event("fire", "Fire!", ["A thatch roof catches in the night.", "(Wells within 2 tiles prevent this.)"],
                 [opt("Bucket chain", do=lambda s: _cheer(s, -6), hint="the house stands, mood -6"),
                  opt("Let it burn", do=burn, hint="lose the cottage")])


def ev_storm(st, rng):
    if "storms" not in st.flags or st.season not in (AUTUMN, WINTER) or not st.has("fishery"):
        return None
    return Event("storm", "Gale", ["A gale comes in off the sea."],
                 [opt("Haul the boats up", {"wood": 4}, hint="no harm"),
                  opt("Ride it out", do=lambda s: _mods(s, fish=0.0), hint="fisheries idle this season")])


def ev_bounty(st, rng):
    kind = rng.randrange(3)
    if kind == 0:
        return Event("bounty", "Berries and mushrooms", ["The woods are generous this year."],
                     [opt("Gather them", do=lambda s: _gain(s, food=6), hint="+6 food")])
    if kind == 1:
        return Event("bounty", "A peddler", ["A peddler pays well for a dry bed."],
                     [opt("Welcome", do=lambda s: _gain(s, coin=4), hint="+4 coin")])
    return Event("bounty", "Windfall", ["A storm brought down good timber."],
                 [opt("Haul it in", do=lambda s: _gain(s, wood=6), hint="+6 wood")])


def ev_frost(st, rng):
    if not st.harsh or st.season != WINTER:
        return None
    n = st.num("cottage") + 1
    return Event("frost", "Hard frost", ["A bitter frost bites the wold."],
                 [opt("Burn extra wood", {"wood": n}, hint="%d wood" % n),
                  opt("Shiver through it", do=lambda s: _cheer(s, -10), hint="mood -10")])


EVENTS = [(ev_trader, 3), (ev_drought, 3), (ev_fever, 2), (ev_feast, 3), (ev_wolves, 4), (ev_raiders, 4),
          (ev_flood, 6), (ev_settlers, 2), (ev_fire, 2), (ev_storm, 3), (ev_bounty, 2), (ev_frost, 4)]


def roll_event(st):
    """The event of the new season (or None). Depends only on the seed and the season, not on what was built."""
    rng = random.Random(st.seed * 7919 + st.turn * 104729 + 17)
    if st.turn == 0 or rng.random() > 0.55:
        return None
    pool = []
    for f, w in EVENTS:
        if f is ev_trader and "traders" in st.flags:
            w *= 2
        ev = f(st, random.Random(rng.random()))
        if ev:
            pool.append((ev, w))
    if not pool:
        return None
    tot = sum(w for _, w in pool)
    r = rng.random() * tot
    for ev, w in pool:
        r -= w
        if r <= 0:
            return ev
    return pool[-1][0]


def option_ok(st, o):
    return affordable(st, o["cost"])


def choose(st, i):
    """Take option i of the pending event. Returns the message."""
    ev = st.event
    o = ev.options[i]
    if not option_ok(st, o):
        return None
    for r, v in o["cost"].items():
        st.res[r] -= v
    msg = o["do"](st) or o["hint"] or ""
    st.event = None
    st.ver += 1
    line = "%s: %s" % (ev.title, o["label"].lower() + (" - " + msg if msg else ""))
    st.log.append(line)
    return line


# =============================================================================================
# Ending a season
# =============================================================================================
def prosperity(st):
    return 10 * st.pop + 4 * len(st.bld) + 30 * len(st.techs) + int(st.mood) + 5 * (st.year - 1)


def goal_text(st):
    g = st.sc["goal"]
    if g[0] == "pop":
        return "Grow to %d folk" % g[1]
    if g[0] == "coin":
        return "Gather %d coin" % g[1]
    if g[0] == "ring":
        return "Raise the Moot Ring"
    if g[0] == "popring":
        return "%d folk and the Moot Ring" % g[1]
    return "Prosper as long as you can"


def goal_progress(st):
    """(fraction 0..1, short text)."""
    g = st.sc["goal"]
    if g[0] == "pop":
        return min(1, st.pop / g[1]), "%d/%d folk" % (st.pop, g[1])
    if g[0] == "coin":
        return min(1, st.res["coin"] / g[1]), "%d/%d coin" % (st.res["coin"], g[1])
    if g[0] == "ring":
        return (1.0 if st.has("ring") else 0.0), "ring %s" % ("raised" if st.has("ring") else "not yet")
    if g[0] == "popring":
        f = min(1, st.pop / g[1]) * 0.6 + (0.4 if st.has("ring") else 0)
        return f, "%d/%d folk, ring %s" % (st.pop, g[1], "yes" if st.has("ring") else "no")
    return 0.0, "prosperity %d" % prosperity(st)


def goal_met(st):
    g = st.sc["goal"]
    return (g[0] == "pop" and st.pop >= g[1]) or (g[0] == "coin" and st.res["coin"] >= g[1]) or \
        (g[0] == "ring" and st.has("ring")) or (g[0] == "popring" and st.pop >= g[1] and st.has("ring"))


def final_score(st):
    if st.sc_i == ENDLESS:
        return st.peak
    if st.over != "won":
        return 0
    return int(st.sc["weight"] * (600 + 30 * st.left + 8 * st.pop + 2 * int(st.mood) + 3 * len(st.bld)))


class Report:
    pass


def end_season(st):
    """Run the season: yields, food, firewood, births, mood, lore; then the next season and its event.
    Returns a Report for the season card."""
    e = forecast(st)
    rp = Report()
    rp.season, rp.year = st.season, st.year
    rp.delta = dict(e.delta)
    rp.per = e.per
    before = dict(st.res)
    for r in RES:
        st.res[r] = st.res[r] + e.delta[r]
    st.res["food"] = max(0, st.res["food"])
    st.res["wood"] = max(0, st.res["wood"])
    for r in RES:
        st.res[r] = max(0, min(st.cap(r), st.res[r]))
    rp.got = {r: st.res[r] - before[r] for r in RES}
    rp.starve = _kill(st, e.starve) if e.starve else 0
    rp.freeze = _kill(st, e.freeze) if e.freeze else 0
    st.lore += e.delta["lore"]
    rp.learned = None
    t = TECH.get(st.study)
    if t and st.lore >= t[2] and t[0] not in st.techs:
        st.lore -= t[2]
        st.techs.add(t[0])
        rp.learned = t[1]
        rest = [x[0] for x in TECHS if x[0] not in st.techs]
        st.study = rest[0] if rest else None
    rp.births = e.births
    st.pop += e.births
    st.born += e.births
    st.mood = e.mood
    st.mood_temp *= 0.5
    if abs(st.mood_temp) < 1:
        st.mood_temp = 0.0
    if st.pop <= 0:
        st.pop = 0
    st.turn += 1
    st.mods = {}
    if getattr(st, "silt", False):
        st.mods["flood"] = 1.5          # the silt left by a spring flood feeds the summer
        st.silt = False
    st.peak = max(st.peak, prosperity(st))
    st.ver += 1
    lines = []
    if rp.starve:
        lines.append("%d starved" % rp.starve)
    if rp.freeze:
        lines.append("%d froze" % rp.freeze)
    if rp.births:
        lines.append("%d born" % rp.births)
    if rp.learned:
        lines.append("learned %s" % rp.learned)
    rp.lines = lines
    st.log.append("%s %d: %s" % (SEASONS[rp.season], rp.year, ", ".join(lines) or "a quiet season"))
    if st.sc_i != ENDLESS and goal_met(st):
        st.over, st.why = "won", "%s: %s." % (st.sc["name"], goal_text(st).lower())
    elif st.pop <= 1:
        st.over, st.why = "lost", "The last folk have left %s." % st.sc["name"]
    elif st.left is not None and st.left <= 0:
        st.over, st.why = "lost", "The years ran out before the goal."
    if not st.over:
        st.event = roll_event(st)
    return rp


# =============================================================================================
# The auto-mode reeve: a plain, sensible economy that sees only what the player sees (the map, the stores, the
# forecast). It picks one action at a time so auto mode can show the cursor walking to it.
# =============================================================================================
def yearly(st):
    """The resource balance of a whole year with today's buildings and people."""
    tot = dict.fromkeys(RES + ("lore",), 0)
    keep_turn, keep_mods = st.turn, st.mods
    try:
        for s in range(4):
            st.turn = keep_turn - keep_turn % 4 + s
            st.mods = keep_mods if st.turn == keep_turn else {}
            e = economy(st)
            for r in tot:
                tot[r] += e.delta[r]
    finally:
        st.turn, st.mods = keep_turn, keep_mods
    return tot


def spots(st, item):
    return [(x, y) for y in range(MAP_H) for x in range(MAP_W) if can_do(st, item, x, y)[0]]


def dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def food_value(st, item, x, y, tier=1):
    """Food a year per worker of a farm or fishery on (x, y)."""
    tot = sum(output(st, x, y, item, tier, s, {})[0].get("food", 0) for s in range(4))
    return tot / B[item]["jobs"]


def farmland(st, x, y):
    """How good this meadow is for a farm (the bot keeps such tiles free of other buildings)."""
    if st.ter[y][x] not in ".rs":
        return 0
    return (st.count_ter(x, y, "~") > 0) * 2 + (st.ter[y][x] == "r") * 2 + st.count_bld(x, y, ("farm", "mill"))


class Reeve:
    def __init__(self, st):
        g = st.sc["goal"][0]
        if g in ("ring", "popring"):
            self.order = ["rotation", "masonry", "stones", "milling", "smelting", "herbs", "charter"]
        elif g == "coin":
            self.order = ["charter", "rotation", "milling", "masonry", "herbs", "smelting", "stones"]
        else:
            self.order = ["rotation", "milling", "masonry", "herbs", "charter", "smelting", "stones"]
        self.cleared = -1

    def pick_study(self, st):
        for t in self.order:
            if t not in st.techs:
                if st.study != t:
                    st.study = t
                return

    # ---- event choices
    def choose_event(self, st):
        ev = st.event
        ok = [i for i, o in enumerate(ev.options) if option_ok(st, o)]
        names = [o["label"] for o in ev.options]

        def find(word):
            for i in ok:
                if names[i].lower().startswith(word):
                    return i
            return None
        low_food = min(f for f, w in project(st, 4)) < st.pop
        pick = None
        if ev.id == "trader":
            if low_food:
                pick = find("buy 12")
            elif st.res["tools"] < 3 and st.res["coin"] >= 14 and st.sc["goal"][0] != "coin":
                pick = find("buy 3")
            elif st.res["wood"] >= min(st.cap("wood") - 6, 40 if st.sc["goal"][0] == "coin" else 99):
                pick = find("sell 10")
            elif st.res["stone"] >= st.cap("stone") - 6:
                pick = find("sell 8")
        elif ev.id == "drought":
            pick = find("dig") if st.res["wood"] >= 6 + self.reserve(st) else None
            if pick is None:
                pick = find("carry") if st.mood > 62 else find("let")
        elif ev.id == "fever":
            pick = find("brew")
            if pick is None:
                pick = find("keep")
        elif ev.id == "feast":
            pick = find("hold") if not low_food and st.res["food"] - st.pop // 2 >= st.pop * 2 else find("not")
        elif ev.id == "wolves":
            pick = find("hunt") if st.res["tools"] >= 5 else None
        elif ev.id == "raiders":
            if st.num("tower") >= 2:
                pick = find("stand")
            else:
                pick = find("pay")
        elif ev.id == "flood":
            farms = sum(1 for (x, y), (k, _) in st.bld.items() if k == "farm" and st.count_ter(x, y, "~"))
            if farms >= 2 and st.res["stone"] >= 8 + (10 if st.sc["goal"][0] in ("ring", "popring") else 0):
                pick = find("raise")
        elif ev.id == "settlers":
            pick = find("take") if not low_food else None
        elif ev.id == "fire":
            pick = find("bucket") if st.mood > 40 else None
        elif ev.id == "storm":
            pick = find("haul") if st.res["wood"] >= 8 + self.reserve(st) else None
        elif ev.id == "frost":
            n = ev.options[0]["cost"].get("wood", 0)
            pick = find("burn") if st.res["wood"] >= n + self.reserve(st) else None
        if pick is None:
            free = [i for i in ok if not ev.options[i]["cost"]]
            pick = free[-1] if free else ok[0]
        return pick

    def reserve(self, st):
        """Wood kept back for the hearths of the coming winter."""
        houses = sum(1 for k, _ in st.bld.values() if k in HOUSES)
        return houses + 2 if st.season in (SUMMER, AUTUMN) else 2

    # ---- building
    def next_action(self, st):
        """One action (item, x, y) or None to end the season."""
        self.pick_study(st)
        e = forecast(st)
        yr = yearly(st)
        pop = st.pop
        free_house = st.housing() - pop
        res = st.res
        goal = st.sc["goal"]
        proj = project(st, 4)
        low = min(f for f, w in proj)
        wood_res = self.reserve(st)
        want_food = max(3, pop // 2 + 2)

        def can(item, need_wood=0):
            c = B[item]["cost"] if item in B else TOOLS[item]["cost"]
            return affordable(st, c) and res["wood"] - c.get("wood", 0) >= need_wood

        def best(item, score):
            sp = spots(st, item)
            if not sp:
                return None
            sc_ = [(score(x, y), -dist((x, y), st.hall), -y, -x, (x, y)) for x, y in sp]
            top = max(sc_)
            return (item, top[4][0], top[4][1]) if top[0] > -1e8 else None

        def food_spot():
            opts = []
            for item in ("farm", "fishery"):
                if not can(item, min(wood_res, res["wood"] - 4)):
                    continue
                for x, y in spots(st, item):
                    v = food_value(st, item, x, y) + 0.3 * st.count_bld(x, y, ("farm", "mill"))
                    if item == "farm" and st.count_ter(x, y, "f") >= 2:
                        v -= 0.5
                    opts.append((v, -dist((x, y), st.hall), -y, -x, item, x, y))
            if not opts:
                return None
            v = max(opts)
            return (v[4], v[5], v[6])

        jobs_ok = e.idle

        # 1. food first: the stores must last through the winter and leave room to grow
        if yr["food"] < want_food or low < 2:
            for x, y in sorted(st.bld):
                k, t = st.bld[(x, y)]
                if k == "farm" and t == 1 and can_do(st, "improve", x, y)[0] and res["tools"] >= 3:
                    return ("improve", x, y)
            a = food_spot()
            if a:
                return a
        # 2. timber
        wc = st.num("woodcut")
        want_wood = 5 + pop // 4 + 4 * st.num("mine") + 4 * st.num("smithy")
        if (yr["wood"] < want_wood or wc == 0) and can("woodcut"):
            a = best("woodcut", lambda x, y: min(3, st.count_ter(x, y, "f")) * 2 - farmland(st, x, y)
                     if st.count_ter(x, y, "f") >= 1 else -1e9)
            if a:
                return a
        if res["wood"] < 8 and self.cleared != st.turn:
            a = best("clear", lambda x, y: -st.count_bld(x, y, ("woodcut",)) * 3 - dist((x, y), st.hall) * 0.1)
            if a:
                self.cleared = st.turn
                return a
        # 2a. a lore house early: the lore track pays for itself
        if not st.has("lore") and pop >= 9 and can("lore", min(wood_res, 4)):
            a = best("lore", lambda x, y: 2 * st.count_bld(x, y, ("green",)) - farmland(st, x, y))
            if a:
                return a
        # 2b. saving up for the Moot Ring: make what it lacks, spend nothing else
        saving = goal[0] in ("ring", "popring") and "stones" in st.techs and not st.has("ring") and \
            (goal[0] == "ring" or pop >= goal[1])
        if saving:
            if affordable(st, B["ring"]["cost"]):
                a = best("ring", lambda x, y: -farmland(st, x, y) - dist((x, y), st.hall) * 0.2)
                if a:
                    return a
            a = self.save_for_ring(st, e, wood_res)
            if a != "go on":
                return a
        # 3. room for more folk
        if free_house <= 2 and yr["food"] >= want_food - 1 and goal[0] != "coin" or free_house <= 0:
            for x, y in sorted(st.bld):
                if st.bld[(x, y)] == ("cottage", 1) and can_do(st, "improve", x, y)[0] and \
                        res["wood"] - 4 >= wood_res:
                    return ("improve", x, y)
            if can("cottage", wood_res):
                a = self.cottage_spot(st)
                if a:
                    return a
        # 4. stone
        nq = st.num("quarry")
        want_q = 1 if pop < 14 else 2 if pop < 30 or goal[0] not in ("ring", "popring") else 3
        if nq < want_q and jobs_ok >= 2 and can("quarry", wood_res):
            a = best("quarry", lambda x, y: output(st, x, y, "quarry", 1, 0, {})[0]["stone"])
            if a:
                return a
        # 5. reach: grow toward the timber, stone and water the village still lacks
        a = self.expand(st, wood_res)
        if a:
            return a
        # 6. lore
        if not st.has("lore") and pop >= 9 and jobs_ok >= 2 and can("lore", wood_res):
            a = best("lore", lambda x, y: 2 * st.count_bld(x, y, ("green",)) - farmland(st, x, y))
            if a:
                return a
        # 7. stores near full
        if any(res[r] >= st.cap(r) - 8 for r in ("food", "wood", "stone")) and can("store", wood_res) and \
                st.num("store") < 2 + pop // 25:
            a = best("store", lambda x, y: -farmland(st, x, y) * 2)
            if a:
                return a
        # 8. wells and greens for the houses
        if pop >= 10 and st.cover("well") < 0.75 and res["stone"] >= 5 + 3:
            a = best("well", lambda x, y: self.uncovered(st, x, y, "well") * 2 - farmland(st, x, y)
                     if self.uncovered(st, x, y, "well") >= 2 else -1e9)
            if a:
                return a
        if st.mood < 64 and res["coin"] >= 3 + 4 and st.cover("green") < 0.7 and can("green", wood_res):
            a = best("green", lambda x, y: self.uncovered(st, x, y, "green") * 2 + st.count_bld(x, y, ("lore",)) -
                     farmland(st, x, y) if self.uncovered(st, x, y, "green") >= 2 else -1e9)
            if a:
                return a
        # 9. watch against wolves and raiders
        need_t = 0
        if "wolves" in st.flags and st.turn >= 2:
            need_t = 1
        if "raiders" in st.flags and st.year >= 2:
            need_t = 2
        if st.num("tower") < need_t and jobs_ok >= 1 and can("tower", wood_res):
            first = not st.guarded(*st.hall)
            a = best("tower", lambda x, y: (10 if first and dist((x, y), st.hall) <= 3 else 0) +
                     sum(1 for p, (k, _) in st.bld.items() if k in HOUSES and dist(p, (x, y)) <= 3) -
                     farmland(st, x, y) - 3 * sum(1 for p, (k, _) in st.bld.items() if k == "tower" and
                                                  dist(p, (x, y)) <= 3))
            if a:
                return a
        # 10. mills next to the fields
        if "milling" in st.techs and jobs_ok >= 1 and can("mill", wood_res):
            a = best("mill", lambda x, y: st.count_bld(x, y, ("farm",)) * 2 - 1
                     if st.count_bld(x, y, ("farm",)) >= 3 and not st.count_bld(x, y, ("mill",)) else -1e9)
            if a:
                return a
        # 11. markets for coin
        n_m = st.num("market")
        want_m = (1 if pop >= 14 else 0) + (pop // 10 if goal[0] == "coin" else 0) + \
            (1 if goal[0] in ("ring", "popring") and pop >= 20 else 0)
        if n_m < want_m and jobs_ok >= 2 and can("market", wood_res):
            a = best("market", lambda x, y: min(4, st.count_bld(x, y, HOUSES)) * 2 - farmland(st, x, y))
            if a:
                return a
        # 12. ore and tools for the ring and the improvements
        need_tools = goal[0] in ("ring", "popring") or res["tools"] < 3
        if need_tools and pop >= 12:
            if not st.has("mine") and jobs_ok >= 2 and can("mine", wood_res):
                a = best("mine", lambda x, y: 0)
                if a:
                    return a
            if st.has("mine") and not st.has("smithy") and jobs_ok >= 1 and can("smithy", wood_res):
                a = best("smithy", lambda x, y: -farmland(st, x, y) * 2 - min(dist((x, y), p) for p, (k, _) in
                                                                               st.bld.items() if k == "mine"))
                if a:
                    return a
        # 13. the Moot Ring
        if goal[0] in ("ring", "popring") and "stones" in st.techs and affordable(st, B["ring"]["cost"]):
            a = best("ring", lambda x, y: -farmland(st, x, y) - dist((x, y), st.hall) * 0.2)
            if a:
                return a
        # 14. better farms, longhouses, more food when there is spare
        if res["tools"] >= (5 if goal[0] in ("ring", "popring") and not st.has("ring") else 3):
            for x, y in sorted(st.bld):
                k, t = st.bld[(x, y)]
                if k in ("farm", "woodcut", "quarry") and t == 1 and can_do(st, "improve", x, y)[0] and \
                        res["wood"] - 3 >= wood_res:
                    return ("improve", x, y)
        if yr["food"] < want_food + pop // 4 and e.idle >= 2:
            a = food_spot()
            if a:
                return a
        if e.idle >= 3 and yr["stone"] < 6 and can("quarry", wood_res):
            a = best("quarry", lambda x, y: output(st, x, y, "quarry", 1, 0, {})[0]["stone"])
            if a:
                return a
        return None

    def save_for_ring(self, st, e, wood_res):
        cost = B["ring"]["cost"]
        lack = [r for r, v in cost.items() if st.res[r] < v]
        if not lack:
            return "go on"
        yr = yearly(st)
        sp = lambda item, score: self._best(st, item, score)
        if "wood" in lack and yr["wood"] < 16 and e.idle >= 1 and affordable(st, B["woodcut"]["cost"]):
            a = sp("woodcut", lambda x, y: min(3, st.count_ter(x, y, "f")) * 2 - farmland(st, x, y)
                   if st.count_ter(x, y, "f") >= 2 else -1e9)
            if a:
                return a
        if "stone" in lack and yr["stone"] < 12 and e.idle >= 2 and affordable(st, B["quarry"]["cost"]):
            a = sp("quarry", lambda x, y: output(st, x, y, "quarry", 1, 0, {})[0]["stone"])
            if a:
                return a
        if "tools" in lack:
            if not st.has("mine") and e.idle >= 2 and affordable(st, B["mine"]["cost"]):
                a = sp("mine", lambda x, y: 0)
                if a:
                    return a
            if st.has("mine") and st.num("smithy") < 1 + (st.num("mine") > 1) and \
                    affordable(st, B["smithy"]["cost"]):
                a = sp("smithy", lambda x, y: -farmland(st, x, y) * 2)
                if a:
                    return a
        if "coin" in lack and not st.has("market") and e.idle >= 2 and affordable(st, B["market"]["cost"]):
            a = sp("market", lambda x, y: min(4, st.count_bld(x, y, HOUSES)) * 2 - farmland(st, x, y))
            if a:
                return a
        if e.idle <= 1 and st.housing() - st.pop <= 1 and st.res["wood"] >= 5 + wood_res:
            return self.cottage_spot(st)          # more hands for the work the ring needs
        return None

    def _best(self, st, item, score):
        sp = spots(st, item)
        if not sp:
            return None
        top = max((score(x, y), -dist((x, y), st.hall), -y, -x, (x, y)) for x, y in sp)
        return (item, top[4][0], top[4][1]) if top[0] > -1e8 else None

    def uncovered(self, st, x, y, kind):
        srcs = [p for p, (k, _) in st.bld.items() if k == kind]
        return sum(1 for p, (k, _) in st.bld.items() if k in HOUSES and dist(p, (x, y)) <= 2 and
                   not any(dist(p, s) <= 2 for s in srcs))

    def lacking(self, st):
        """Terrain the village needs but cannot build on yet (nothing of it within reach)."""
        reach = st.reach()
        have = {st.ter[y][x] for x, y in reach if (x, y) not in st.bld}
        near_forest = any(st.count_ter(x, y, "f") for x, y in reach if (x, y) not in st.bld and
                          st.ter[y][x] in ".rs")
        out = []
        if not near_forest:
            out.append("f")
        if "h" not in have:
            out.append("h")
        if "~" not in have:
            out.append("~")
        if "o" not in have and (st.sc["goal"][0] in ("ring", "popring") or st.res["tools"] < 3) and st.pop >= 10:
            out.append("o")
        return out

    def expand(self, st, wood_res):
        need = self.lacking(st)
        if not need or not affordable(st, B["cottage"]["cost"]) or st.res["wood"] - 5 < wood_res - 2:
            return None
        targets = [(x, y) for y in range(MAP_H) for x in range(MAP_W) if st.ter[y][x] in need and
                   (x, y) not in st.bld]
        if not targets:
            return None
        sp = spots(st, "cottage")
        if not sp:
            return None
        best_ = min(sp, key=lambda p: (min(dist(p, t) for t in targets), farmland(st, *p), dist(p, st.hall)))
        return ("cottage", best_[0], best_[1])

    def cottage_spot(self, st):
        sp = spots(st, "cottage")
        if not sp:
            return None
        wells = [p for p, (k, _) in st.bld.items() if k in ("well", "green")]
        mk = [p for p, (k, _) in st.bld.items() if k == "market"]

        def score(p):
            s = -farmland(st, *p) * 2 - dist(p, st.hall) * 0.5
            s += sum(1.5 for w in wells if dist(p, w) <= 2)
            s += sum(1 for m in mk if dist(p, m) <= 1)
            if st.count_ter(p[0], p[1], "f") >= 2:
                s -= 1
            return (s, -p[1], -p[0])
        p = max(sp, key=score)
        return ("cottage", p[0], p[1])

    def play_season(self, st, limit=14):
        """Headless: the bot's whole season (actions, then end it, then the event). Returns the report."""
        for _ in range(limit):
            a = self.next_action(st)
            if not a:
                break
            ok, why = can_do(st, *a)
            assert ok, "bot chose %s at %d,%d: %s" % (a + (why,))
            do_item(st, *a)
        rp = end_season(st)
        if st.event:
            choose(st, self.choose_event(st))
        return rp


def bot_game(sc_i, seed=None, years=None):
    st = State(sc_i, seed)
    bot = Reeve(st)
    n = (years or st.sc["years"] or 20) * 4
    while not st.over and st.turn < n:
        bot.play_season(st)
    return st


# =============================================================================================
# Sound: wood and straw, a season chime, the village bell
# =============================================================================================
def _chime(fs, d=0.09, v=0.24, w="tri", last=0.4):
    out = [dict(w=w, f=f, d=d, v=v) for f in fs[:-1]]
    return out + [dict(w=w, f=fs[-1], d=last, v=v, vib=(5, 0.12), r="lin")]


SND = Sound(GAME, {
    "build": [dict(w="noise", f=700, f2=300, d=0.05, v=0.22), dict(w="tri", f=196, f2=150, d=0.07, v=0.2),
              dict(w="noise", f=600, f2=300, d=0.05, v=0.18), dict(w="tri", f=220, f2=170, d=0.08, v=0.18)],
    "chop": [dict(w="noise", f=1800, f2=500, d=0.06, v=0.22), dict(w="noise", f=1500, f2=400, d=0.07, v=0.2, at=0.12),
             dict(w="noise", f=300, f2=120, d=0.25, v=0.18)],
    "drain": [dict(w="noise", f=260, f2=120, d=0.22, v=0.2, r="lin"),
              dict(w="sine", f=330, f2=180, d=0.15, v=0.1, at=0)],
    "improve": _chime([523, 659, 784], 0.05, 0.2, "tri", 0.12),
    "demolish": [dict(w="noise", f=500, f2=120, d=0.3, v=0.24, r="lin"),
                 dict(w="tri", f=140, f2=70, d=0.2, v=0.18, at=0)],
    "undo": [dict(w="tri", f=660, f2=440, d=0.06, v=0.16)],
    "deny": [dict(w="tri", f=220, f2=180, d=0.09, v=0.2)],
    "move": [dict(w="tri", f=1200, d=0.012, v=0.05)],
    "menu": [dict(w="tri", f=740, d=0.025, v=0.18)],
    "season0": _chime([523, 659, 784, 1047]), "season1": _chime([587, 740, 880, 1175]),
    "season2": _chime([440, 554, 659, 880]), "season3": _chime([392, 466, 587, 784], last=0.6),
    "event": [dict(w="saw", f=220, d=0.18, v=0.12, vib=(4, 0.1)), dict(w="saw", f=330, d=0.3, v=0.12, vib=(4, 0.1))],
    "coin": [dict(w="square", f=1319, d=0.04, v=0.12, duty=0.25), dict(w="square", f=1760, d=0.09, v=0.12, duty=0.25)],
    "born": [dict(w="sine", f=1047, d=0.2, v=0.14), dict(w="sine", f=1568, d=0.3, v=0.08, at=0)],
    "learn": _chime([784, 988, 1175, 1568], 0.07, 0.2, "sine", 0.5),
    "starve": [dict(w="tri", f=196, f2=147, d=0.4, v=0.24, r="lin")],
    "won": _chime([523, 659, 784, 1047, 784, 1047, 1319], 0.1, 0.28, "tri", 0.8),
    "lost": [dict(w="tri", f=f, d=0.22, v=0.24) for f in (392, 349, 311)] +
            [dict(w="tri", f=262, d=0.7, v=0.24, r="lin")],
    "start": _chime([392, 523, 659], 0.06, 0.26, "tri", 0.2),
    "pause": [dict(w="tri", f=523, f2=392, d=0.07, v=0.2)],
    "sound_on": [dict(w="tri", f=440, d=0.06, v=0.32), dict(w="tri", f=880, d=0.12, v=0.32)],
})


# =============================================================================================
# Pixel art: every tile is painted at the size it is shown (T x T pixels) - a bigger window gives finer tiles:
# furrows and sprouts, single trees, thatch lines, chimney smoke, mill sails, shimmering water, snow in winter
# =============================================================================================
def hsh(x, y, s=0):
    h = (x * 374761393 + y * 668265263 + s * 2246822519) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return (h ^ (h >> 16)) & 0xFFFF


WHITE = (255, 255, 255)
SNOW = (234, 238, 246)
SNOW_DK = (196, 206, 222)
GRASS = ((108, 178, 70), (88, 156, 58), (160, 150, 66), SNOW)
SOIL = (112, 80, 52)
SOIL_DK = (84, 58, 38)
THATCH = (218, 176, 86)
THATCH_DK = (170, 128, 58)
WALL = (232, 214, 170)
WALL_DK = (186, 164, 122)
TIMBER = (110, 74, 46)
STONE = (160, 162, 170)
STONE_DK = (112, 114, 124)
WATER = (56, 118, 182)
WATER_DK = (40, 90, 158)
WATER_LT = (98, 160, 214)
ICE = (190, 216, 236)


class Img:
    """A T x T tile being painted; None is see-through (for buildings over their ground)."""

    def __init__(self, T, fill=None):
        self.T = T
        self.p = [[fill] * T for _ in range(T)]

    def set(self, x, y, c):
        x, y = int(x), int(y)
        if 0 <= x < self.T and 0 <= y < self.T:
            self.p[y][x] = c

    def rect(self, x0, y0, x1, y1, c):
        """Integer pixels, x1 / y1 exclusive."""
        T = self.T
        x0, y0, x1, y1 = max(0, int(x0)), max(0, int(y0)), min(T, int(x1)), min(T, int(y1))
        for y in range(y0, y1):
            row = self.p[y]
            for x in range(x0, x1):
                row[x] = c

    def frac(self, u0, v0, u1, v1, c):
        """A rectangle in fractions of the tile, at least one pixel."""
        T = self.T
        x0, y0 = int(u0 * T + 0.5), int(v0 * T + 0.5)
        x1, y1 = max(x0 + 1, int(u1 * T + 0.5)), max(y0 + 1, int(v1 * T + 0.5))
        self.rect(x0, y0, x1, y1, c)
        return x0, y0, x1, y1

    def disc(self, cx, cy, r, c, light=None, dark=None):
        T = self.T
        for y in range(max(0, int(cy - r - 1)), min(T, int(cy + r + 2))):
            for x in range(max(0, int(cx - r - 1)), min(T, int(cx + r + 2))):
                dx, dy = x + 0.5 - cx, y + 0.5 - cy
                if dx * dx + dy * dy <= r * r:
                    col = c
                    if light and dx + dy < -r * 0.5:
                        col = light
                    elif dark and dx + dy > r * 0.6:
                        col = dark
                    self.p[y][x] = col

    def roof(self, x0, x1, y0, y1, c, dark, snow=False, lines=True):
        """A gabled thatch / slate roof seen from the front: widening downwards, eaves at y1."""
        h = max(1, y1 - y0)
        for j in range(h):
            y = y0 + j
            inset = int((h - 1 - j) * 0.6)
            a, b = x0 + inset, x1 - inset
            col = dark if lines and j % 2 == 1 and self.T >= 8 else c
            if snow and j < max(1, h // 2):
                col = SNOW if j % 2 == 0 or self.T < 8 else SNOW_DK
            for x in range(max(0, a), min(self.T, b)):
                self.set(x, y, col)
            if b - 1 >= a:
                self.set(b - 1, y, shade(col, 0.8))
        for x in range(max(0, x0), min(self.T, x1)):
            self.set(x, y1 - 1 if y1 - 1 >= y0 else y0, shade(dark, 0.85))


def tex(base, i, j, var, k=0.07):
    n = hsh(i, j, var)
    if n % 7 == 0:
        return shade(base, 1 + k)
    if n % 9 == 0:
        return shade(base, 1 - k)
    return base


def grass_col(season, var):
    c = GRASS[season]
    if season != WINTER:
        c = shade(c, 0.95 + (var % 5) * 0.025)
    return c


def paint_ground(img, ter, season, var, mask):
    """The ground of a tile: meadow, rich soil, sand, forest floor, hills, ore, marsh or water."""
    T = img.T
    g = grass_col(season, var)
    if ter in ".rf":
        base = shade(g, 0.86) if ter == "f" and season != WINTER else g
        for j in range(T):
            for i in range(T):
                img.p[j][i] = tex(base, i, j, var)
        if ter == "." and T >= 5:
            n = 2 + T // 4
            for k in range(n):
                h = hsh(var, k, 3)
                x, y = h % T, (h >> 5) % T
                if season == SPRING and k % 2 == 0:
                    img.set(x, y, ((250, 244, 220), (250, 220, 90), (236, 150, 190))[h % 3])
                elif season == WINTER:
                    img.set(x, y, SNOW_DK)
                else:
                    img.set(x, y, shade(g, 0.78))
                    img.set(x, y - 1, shade(g, 0.88))
        if ter == "r":
            for k in range(max(1, T // 3)):
                h = hsh(var, k, 5)
                x, y = h % T, (h >> 4) % T
                col = SOIL_DK if season != WINTER else SNOW_DK
                img.rect(x, y, x + max(1, T // 4), y + 1, col)
        return
    if ter == "s":
        base = (222, 204, 150) if season != WINTER else (232, 230, 226)
        for j in range(T):
            for i in range(T):
                img.p[j][i] = tex(base, i, j, var, 0.05)
        for k in range(T // 3):
            h = hsh(var, k, 7)
            img.set(h % T, (h >> 4) % T, (196, 176, 124))
        return
    if ter in "ho":
        base = (126, 140, 80) if season in (SPRING, SUMMER) else (150, 132, 78) if season == AUTUMN else SNOW
        for j in range(T):
            for i in range(T):
                img.p[j][i] = tex(base, i, j, var)
        lt = shade(base, 1.3) if season != WINTER else WHITE
        dk = shade(base, 0.62) if season != WINTER else (170, 180, 200)
        mounds = [(0.5, 0.66, 0.46)] if T < 6 else [(0.32, 0.62, 0.32), (0.7, 0.74, 0.3)]
        for cx, cy, r in mounds:
            R = r * T
            for y in range(T):
                for x in range(T):
                    dx, dy = (x + 0.5 - cx * T) / R, (y + 0.5 - cy * T) / (R * 0.8)
                    if dx * dx + dy * dy <= 1 and y + 0.5 <= cy * T + R * 0.35:
                        img.p[y][x] = lt if dx + dy * 0.6 < -0.25 else dk if dx > 0.3 else shade(base, 1.1)
        rock = (150, 146, 140) if season != WINTER else (150, 156, 170)
        for k in range(max(1, T // 4)):
            h = hsh(var, k, 9)
            img.set(h % T, T // 2 + (h >> 4) % max(1, T // 2), rock)
        if ter == "o":
            for k in range(max(2, T // 2)):
                h = hsh(var, k, 11)
                x, y = h % T, T // 4 + (h >> 4) % max(1, T * 3 // 4)
                img.set(x, y, (200, 96, 56) if k % 3 else (230, 210, 150))
                if T >= 8 and k % 3:
                    img.set(x + 1, y, (150, 70, 46))
        return
    if ter == "m":
        base = (90, 112, 70) if season != WINTER else (200, 210, 214)
        for j in range(T):
            for i in range(T):
                img.p[j][i] = tex(base, i, j, var)
        pool = (72, 106, 118) if season != WINTER else ICE
        for k in range(1 if T < 6 else 2):
            h = hsh(var, k, 13)
            cx, cy = 0.25 + (h % 50) / 100.0, 0.3 + ((h >> 6) % 45) / 100.0
            img.disc(cx * T, cy * T, max(0.7, T * 0.17), pool, light=shade(pool, 1.2))
        if T >= 4:
            for k in range(T // 2):
                h = hsh(var, k, 15)
                x, y = h % T, T // 3 + (h >> 4) % max(1, T * 2 // 3)
                reed = (150, 146, 78) if season != WINTER else (170, 150, 110)
                for d in range(max(1, T // 5)):
                    img.set(x, y - d, reed)
                img.set(x, y - max(1, T // 5), (110, 72, 44))
        return
    if ter == "~":
        frozen = season == WINTER
        deep = WATER_DK if not frozen else mix(ICE, WATER_LT, 0.3)
        base = WATER if not frozen else ICE
        for j in range(T):
            for i in range(T):
                img.p[j][i] = base
        if T >= 3:          # shallows and foam along the land
            bank = (206, 190, 140) if not frozen else SNOW
            shallow = WATER_LT if not frozen else WHITE
            w = max(1, T // 6)
            for b, (x0, y0, x1, y1) in enumerate(((0, 0, T, w), (T - w, 0, T, T), (0, T - w, T, T), (0, 0, w, T))):
                if mask & (1 << b):
                    img.rect(x0, y0, x1, y1, bank if T >= 6 else shallow)
            if T >= 6:
                for b, (x0, y0, x1, y1) in enumerate(((0, w, T, 2 * w), (T - 2 * w, 0, T - w, T),
                                                      (0, T - 2 * w, T, T - w), (w, 0, 2 * w, T))):
                    if mask & (1 << b):
                        img.rect(x0, y0, x1, y1, shallow)
        if not mask and T >= 4:
            for k in range(T // 3):
                h = hsh(var, k, 17)
                img.set(h % T, (h >> 4) % T, deep)
        return


def paint_building(img, kind, tier, season, var, side, T):
    """A building over its ground (img already holds the ground)."""
    w = season == WINTER
    if T <= 3:
        icon(img, kind, tier, season)
        return
    if kind == "farm":
        per = 2 if T < 9 else 3
        for j in range(T):
            furrow = j % per == per - 1
            for i in range(T):
                n = hsh(i, j, var)
                if season == SPRING:
                    c = SOIL_DK if furrow else SOIL
                    if not furrow and (i + j // per) % 2 == 0:
                        c = (126, 186, 76)
                elif season == SUMMER:
                    c = (118, 132, 52) if furrow else (178, 204, 82)
                    if not furrow and n % 5 == 0:
                        c = (204, 222, 110)
                elif season == AUTUMN:
                    c = (170, 122, 52) if furrow else (236, 198, 92)
                    if not furrow and n % 4 == 0:
                        c = (252, 226, 140)
                else:
                    c = (150, 126, 104) if furrow else SNOW
                img.p[j][i] = c
        if T >= 6:      # a hedge around the field
            hedge = (64, 112, 54) if not w else (150, 170, 150)
            for i in range(T):
                img.p[0][i] = hedge
                img.p[T - 1][i] = shade(hedge, 0.8)
            for j in range(T):
                img.p[j][0] = hedge
                img.p[j][T - 1] = shade(hedge, 0.8)
        if season == AUTUMN and T >= 7:     # sheaves
            for k in range(2):
                x, y = int(T * (0.3 + 0.4 * k)), int(T * 0.62)
                img.rect(x, y - T // 6, x + max(1, T // 8), y + 1, (250, 220, 120))
                img.set(x, y + 1, (170, 120, 50))
        if tier > 1 and T >= 6:             # a scarecrow on the ploughed farm
            x, y = int(T * 0.72), int(T * 0.25)
            img.rect(x, y, x + 1, y + T // 3, TIMBER)
            img.rect(x - T // 7, y + T // 9, x + T // 7 + 1, y + T // 9 + 1, (180, 60, 50))
            img.disc(x + 0.5, y, max(0.8, T * 0.07), (230, 200, 120))
        return
    if kind == "hall":
        img.frac(0.12, 0.5, 0.88, 0.9, WALL)
        x0, y0, x1, y1 = img.frac(0.12, 0.5, 0.88, 0.9, WALL)
        if T >= 6:
            for x in range(x0, x1, max(2, T // 4)):
                img.rect(x, y0, x + 1, y1, TIMBER)
            img.rect(x0, y0 + (y1 - y0) // 2, x1, y0 + (y1 - y0) // 2 + 1, TIMBER)
        img.frac(0.42, 0.66, 0.58, 0.9, (90, 58, 36))
        img.roof(int(T * 0.02), T - int(T * 0.02), int(T * 0.14), y0 + 1, (176, 70, 54), (130, 48, 40), snow=w)
        px = int(T * 0.84)
        img.rect(px, 0, px + 1, int(T * 0.3), TIMBER)
        img.rect(px - max(1, T // 5), 0, px, max(1, T // 8), (240, 200, 90))
        return
    if kind == "cottage":
        long_ = tier > 1
        a, b = (0.08, 0.92) if long_ else (0.2, 0.8)
        x0, y0, x1, y1 = img.frac(a, 0.52, b, 0.88, WALL)
        img.rect(x1 - max(1, T // 10), y0, x1, y1, WALL_DK)
        if long_:
            img.rect(x0, y1 - max(1, T // 8), x1, y1, STONE)
        img.frac(0.44, 0.66, 0.56, 0.88, (110, 70, 42))
        win = (250, 214, 110) if season in (AUTUMN, WINTER) else (120, 150, 170)
        img.frac(a + 0.06, 0.6, a + 0.16, 0.7, win)
        if long_:
            img.frac(b - 0.16, 0.6, b - 0.06, 0.7, win)
        cx = int(T * (b - 0.14))
        img.rect(cx, int(T * 0.2), cx + max(1, T // 9), int(T * 0.42), STONE_DK)
        img.roof(int(T * (a - 0.08)), int(T * (b + 0.08)) + 1, int(T * 0.24), y0 + 1, THATCH, THATCH_DK, snow=w)
        return
    if kind == "fishery":
        dx, dy = side
        if T >= 5:      # a jetty out toward the water
            cx, cy = T // 2, T // 2
            for k in range(T // 2 + 1):
                x, y = cx + dx * k, cy + dy * k
                plank = (150, 112, 70) if k % 2 == 0 else (126, 92, 58)
                img.rect(x, y, x + (1 if dx else 2), y + (2 if dx else 1), plank)
        x0, y0, x1, y1 = img.frac(0.18, 0.5, 0.62, 0.86, (150, 108, 66))
        img.roof(x0 - 1, x1 + 1, int(T * 0.3), y0 + 1, (96, 80, 70), (70, 58, 52), snow=w)
        if T >= 6:      # nets drying on a rack
            nx = int(T * 0.7)
            img.rect(nx, int(T * 0.45), nx + 1, int(T * 0.88), TIMBER)
            img.rect(nx + T // 5, int(T * 0.45), nx + T // 5 + 1, int(T * 0.88), TIMBER)
            for y in range(int(T * 0.48), int(T * 0.8), 2):
                for x in range(nx + 1, nx + T // 5):
                    if (x + y) % 2 == 0:
                        img.set(x, y, (200, 200, 190))
        return
    if kind == "woodcut":
        x0, y0, x1, y1 = img.frac(0.12, 0.45, 0.5, 0.78, (140, 96, 58))
        img.roof(x0 - 1, x1 + 1, int(T * 0.26), y0 + 1, (120, 84, 54), (92, 62, 40), snow=w)
        r = max(0.7, T * 0.09)
        for k, (u, v) in enumerate(((0.62, 0.78), (0.8, 0.78), (0.71, 0.62))):
            img.disc(u * T, v * T, r, (170, 120, 70), light=(214, 176, 120), dark=(110, 72, 42))
            if T >= 8:
                img.set(u * T, v * T, (226, 194, 140))
        if T >= 6:
            img.rect(int(T * 0.2), int(T * 0.84), int(T * 0.34), int(T * 0.92), (120, 84, 50))
            img.set(int(T * 0.3), int(T * 0.8), STONE)
        return
    if kind == "quarry":
        cut = (172, 172, 178) if not w else (200, 206, 220)
        steps = max(2, T // 3)
        for s in range(steps):
            y = int(T * 0.3) + s * (T // 2) // steps
            a, b = int(T * (0.18 + s * 0.06)), int(T * (0.82 - s * 0.06))
            img.rect(a, y, b, y + max(1, T // 8), shade(cut, 1.0 - 0.08 * s))
            img.rect(a, y + max(1, T // 8), b, y + max(1, T // 8) + 1, shade(cut, 0.66))
        if T >= 6:
            img.rect(int(T * 0.66), int(T * 0.78), int(T * 0.86), int(T * 0.9), STONE)
            img.rect(int(T * 0.66), int(T * 0.78), int(T * 0.86), int(T * 0.8), (196, 196, 204))
        return
    if kind == "mine":
        img.disc(T * 0.5, T * 0.66, T * 0.24, (34, 26, 26))
        img.rect(int(T * 0.24), int(T * 0.42), int(T * 0.3) + 1, int(T * 0.9), TIMBER)
        img.rect(int(T * 0.7), int(T * 0.42), int(T * 0.76) + 1, int(T * 0.9), TIMBER)
        img.rect(int(T * 0.22), int(T * 0.4), int(T * 0.8), int(T * 0.4) + max(1, T // 10), (140, 96, 56))
        img.rect(0, int(T * 0.9), T, int(T * 0.9) + 1, (90, 80, 76))
        if T >= 6:
            img.rect(int(T * 0.04), int(T * 0.76), int(T * 0.24), int(T * 0.88), (96, 84, 80))
            img.rect(int(T * 0.06), int(T * 0.72), int(T * 0.22), int(T * 0.78), (190, 96, 60))
        return
    if kind == "smithy":
        x0, y0, x1, y1 = img.frac(0.14, 0.5, 0.86, 0.88, STONE)
        for y in range(y0, y1, 2):
            for x in range(x0 + (y // 2) % 2, x1, 3):
                img.set(x, y, STONE_DK)
        img.frac(0.3, 0.62, 0.5, 0.82, (255, 150, 60))
        img.roof(x0 - 1, x1 + 1, int(T * 0.28), y0 + 1, (80, 76, 84), (60, 56, 64), snow=w)
        cx = int(T * 0.72)
        img.rect(cx, int(T * 0.14), cx + max(1, T // 8), int(T * 0.4), STONE_DK)
        return
    if kind == "mill":
        x0, y0, x1, y1 = img.frac(0.34, 0.36, 0.66, 0.9, WALL)
        img.rect(x1 - max(1, T // 10), y0, x1, y1, WALL_DK)
        img.frac(0.45, 0.72, 0.55, 0.9, (110, 70, 42))
        img.roof(x0 - 1, x1 + 1, int(T * 0.2), y0 + 1, (110, 80, 60), (80, 58, 44), snow=w)
        return
    if kind == "market":
        cols_ = ((206, 64, 54), (60, 110, 190), (230, 180, 60))
        n = 2 if T < 8 else 3
        for k in range(n):
            a = 0.06 + k * (0.88 / n)
            b = a + 0.88 / n - 0.04
            x0, y0, x1, y1 = img.frac(a, 0.36, b, 0.52, cols_[(k + var) % 3])
            for x in range(x0, x1):
                if (x - x0) % 2 == 1:
                    for y in range(y0, y1):
                        img.set(x, y, (240, 236, 226) if not w else SNOW)
            img.rect(x0, y1, x0 + 1, int(T * 0.84), TIMBER)
            img.rect(x1 - 1, y1, x1, int(T * 0.84), TIMBER)
            img.rect(x0 + 1, int(T * 0.7), x1 - 1, int(T * 0.8), ((210, 160, 80), (150, 200, 90), (200, 90, 70))[k % 3])
        return
    if kind == "well":
        r = T * 0.26
        img.disc(T * 0.5, T * 0.64, r, STONE, light=(196, 198, 206), dark=STONE_DK)
        img.disc(T * 0.5, T * 0.64, max(0.6, r * 0.55), (30, 50, 80) if not w else ICE)
        img.rect(int(T * 0.24), int(T * 0.24), int(T * 0.24) + 1, int(T * 0.64), TIMBER)
        img.rect(int(T * 0.76), int(T * 0.24), int(T * 0.76) + 1, int(T * 0.64), TIMBER)
        img.roof(int(T * 0.16), int(T * 0.86), int(T * 0.1), int(T * 0.28), (150, 70, 50), (110, 50, 40), snow=w,
                 lines=False)
        return
    if kind == "green":
        lush = (130, 200, 90) if season != WINTER else WHITE
        for j in range(T):
            for i in range(T):
                if hsh(i, j, var) % 4 == 0:
                    img.p[j][i] = lush
        for k in range(T // 2):
            h = hsh(var, k, 21)
            img.set(h % T, (h >> 4) % T, ((250, 120, 140), (250, 230, 110), (240, 240, 250), (150, 120, 240))[k % 4]
                    if season != WINTER else SNOW_DK)
        cx = T // 2
        img.rect(cx, int(T * 0.12), cx + 1, int(T * 0.85), (240, 236, 220))
        if T >= 6:
            rib = ((230, 70, 70), (70, 140, 230), (250, 210, 80), (120, 200, 110))
            for k, (dx, dy) in enumerate(((-1, 1), (1, 1), (-2, 2), (2, 2))):
                for s in range(1, T // 3):
                    img.set(cx + dx * s * 0.7 + (dx > 0), int(T * 0.15) + abs(dy) * s * 0.9, rib[k])
        img.set(cx, int(T * 0.1), (250, 210, 80))
        return
    if kind == "store":
        x0, y0, x1, y1 = img.frac(0.1, 0.42, 0.9, 0.9, (156, 66, 50))
        img.rect(x1 - max(1, T // 10), y0, x1, y1, (120, 50, 40))
        d0, d1 = int(T * 0.36), int(T * 0.64)
        img.rect(d0, int(T * 0.56), d1, y1, (110, 46, 36))
        if T >= 7:
            for k in range(d1 - d0):
                img.set(d0 + k, int(T * 0.56) + k * (y1 - int(T * 0.56)) // max(1, d1 - d0), (236, 226, 210))
                img.set(d1 - 1 - k, int(T * 0.56) + k * (y1 - int(T * 0.56)) // max(1, d1 - d0), (236, 226, 210))
        img.roof(x0 - 1, x1 + 1, int(T * 0.12), y0 + 1, (96, 72, 60), (72, 54, 46), snow=w)
        return
    if kind == "tower":
        img.rect(int(T * 0.3), int(T * 0.3), int(T * 0.3) + 1, T - 1, TIMBER)
        img.rect(int(T * 0.7), int(T * 0.3), int(T * 0.7) + 1, T - 1, TIMBER)
        if T >= 7:
            for k in range(int(T * 0.34), T - 1, max(2, T // 4)):
                img.rect(int(T * 0.3), k, int(T * 0.71), k + 1, (130, 90, 56))
        img.frac(0.22, 0.24, 0.78, 0.34, (150, 104, 62))
        img.roof(int(T * 0.2), int(T * 0.82), int(T * 0.04), int(T * 0.25), (120, 84, 54), (92, 62, 40), snow=w,
                 lines=False)
        img.rect(int(T * 0.5), 0, int(T * 0.5) + 1, int(T * 0.06) + 1, TIMBER)
        img.set(int(T * 0.5) + 1, 0, (220, 60, 60))
        return
    if kind == "lore":
        x0, y0, x1, y1 = img.frac(0.12, 0.46, 0.88, 0.9, (196, 190, 176))
        img.rect(x1 - max(1, T // 10), y0, x1, y1, (150, 144, 132))
        img.disc(T * 0.5, T * 0.64, max(0.7, T * 0.1), (250, 220, 130), light=(255, 244, 190))
        img.frac(0.44, 0.76, 0.56, 0.9, (80, 60, 50))
        img.roof(x0 - 1, x1 + 1, int(T * 0.14), y0 + 1, (72, 92, 150), (54, 70, 120), snow=w)
        return
    if kind == "ring":
        n = 6 if T < 8 else 8
        for k in range(n):
            a = k / n * math.tau
            x = T * 0.5 + math.cos(a) * T * 0.36
            y = T * 0.56 + math.sin(a) * T * 0.3
            hgt = max(1, int(T * (0.22 if math.sin(a) > 0 else 0.16)))
            wid = max(1, T // 9)
            for yy in range(int(y) - hgt, int(y) + 1):
                for xx in range(int(x), int(x) + wid):
                    img.set(xx, yy, (176, 178, 186) if xx == int(x) else (128, 130, 140))
            if w:
                img.set(int(x), int(y) - hgt, WHITE)
        img.disc(T * 0.5, T * 0.56, max(0.6, T * 0.08), (250, 220, 120), light=(255, 246, 200))
        return


ICONS = {"hall": ((176, 70, 54), WALL), "cottage": (THATCH, WALL), "fishery": ((96, 80, 70), (150, 108, 66)),
         "woodcut": ((120, 84, 54), (170, 120, 70)), "quarry": ((172, 172, 178), (120, 120, 128)),
         "mine": (TIMBER, (34, 26, 26)), "smithy": ((80, 76, 84), (255, 150, 60)), "mill": ((110, 80, 60), WALL),
         "market": ((206, 64, 54), (240, 236, 226)), "well": ((150, 70, 50), STONE),
         "green": ((250, 120, 140), (130, 200, 90)), "store": ((96, 72, 60), (156, 66, 50)),
         "tower": ((120, 84, 54), TIMBER), "lore": ((72, 92, 150), (196, 190, 176)),
         "ring": ((176, 178, 186), (250, 220, 120))}


def icon(img, kind, tier, season):
    """Small tiles (2-3 pixels): two signature colours, roof over wall."""
    T = img.T
    if kind == "farm":
        c = ((150, 110, 66), (186, 208, 84), (236, 198, 92), (236, 232, 228))[season]
        d = ((120, 186, 76), (130, 140, 56), (176, 128, 56), (150, 126, 104))[season]
        for j in range(T):
            for i in range(T):
                img.p[j][i] = c if j % 2 == 0 else d
        return
    top, bot = ICONS[kind]
    if season == WINTER and kind not in ("ring", "green"):
        top = mix(top, WHITE, 0.6)
    if T == 1:
        img.p[0][0] = top
        return
    if T == 2:
        img.p[0][0] = img.p[0][1] = top
        img.p[1][0] = img.p[1][1] = bot
    else:
        img.p[0][1] = top
        img.p[1][0] = img.p[1][1] = img.p[1][2] = top
        img.p[2][0] = img.p[2][2] = bot
        img.p[2][1] = shade(bot, 0.7)


_TILES = {}


def water_mask(st, x, y):
    m = 0
    for b, (dx, dy) in enumerate(((0, -1), (1, 0), (0, 1), (-1, 0))):
        a, c = x + dx, y + dy
        if 0 <= a < MAP_W and 0 <= c < MAP_H and st.ter[c][a] != "~":
            m |= 1 << b
    return m


def shore_side(st, x, y):
    for dx, dy in ((0, 1), (1, 0), (-1, 0), (0, -1)):
        a, c = x + dx, y + dy
        if 0 <= a < MAP_W and 0 <= c < MAP_H and st.ter[c][a] == "~":
            return dx, dy
    return (0, 1)


def tile_img(st, x, y, T, season):
    """The cached picture of one tile (ground plus building)."""
    ter = st.ter[y][x]
    b = st.bld.get((x, y))
    var = hsh(x, y, 1) % 251
    mask = water_mask(st, x, y) if ter == "~" else 0
    side = shore_side(st, x, y) if b and b[0] == "fishery" else None
    key = (ter, b, var, season, T, mask, side)
    img = _TILES.get(key)
    if img is None:
        if len(_TILES) > 6000:
            _TILES.clear()
        im = Img(T)
        paint_ground(im, "." if b and ter == "f" else ter, season, var, mask)
        if ter == "f" and not b:
            paint_trees(im, season, var)
        if b:
            paint_building(im, b[0], b[1], season, var, side, T)
        img = _TILES[key] = im.p
    return img


def paint_trees(img, season, var):
    T = img.T
    if T <= 3:
        c = ((70, 140, 60), (40, 104, 50), (196, 116, 50), (60, 96, 76))[season]
        for j in range(T):
            for i in range(T):
                if (i + j + var) % 2 == 0 or T == 1:
                    img.p[j][i] = c
                elif season == WINTER:
                    img.p[j][i] = SNOW
                else:
                    img.p[j][i] = shade(c, 0.75)
        return
    if T < 7:           # mid sizes: a canopy of little round crowns
        cols_ = ((96, 176, 80), (50, 124, 56), (214, 128, 50), (52, 92, 66))
        alt = ((236, 190, 210), (40, 104, 50), (226, 180, 60), (52, 92, 66))
        for k, (u, v) in enumerate(((0, 0), (2, 1), (4, 0), (1, 3), (3, 4), (5, 3), (0, 5), (4, 6))):
            u, v = (u + var) % T, v % T
            h = hsh(var, k, 35)
            col = cols_[season] if h % 3 else alt[season]
            lt = SNOW if season == WINTER else shade(col, 1.25)
            img.set(u, v, lt)
            img.set(u + 1, v, col)
            img.set(u, v + 1, col)
            img.set(u + 1, v + 1, shade(col, 0.7))
            img.set(u + 1, v + 2, (90, 62, 40))
        return
    n = 4 if T < 10 else 5
    spots_ = [(0.28, 0.34), (0.74, 0.3), (0.5, 0.62), (0.2, 0.86), (0.8, 0.84), (0.5, 0.18)]
    order = sorted(range(len(spots_)), key=lambda k: hsh(var, k, 31))[:n]
    for k in sorted(order, key=lambda k: spots_[k][1]):
        u, v = spots_[k]
        h = hsh(var, k, 33)
        u += ((h % 9) - 4) / 60.0
        fir = h % 3 == 0
        cx, cy = u * T, v * T
        r = max(0.9, T * (0.22 if n <= 3 else 0.19))
        trunk = (100, 70, 44)
        img.rect(int(cx), int(cy), int(cx) + 1, int(cy + r * 1.2) + 1, trunk)
        if fir:
            col = (44, 100, 60) if season != AUTUMN else (52, 96, 58)
            for j in range(int(r * 2.2)):
                y = int(cy - r * 1.3) + j
                half = (j + 1) * r / (r * 2.2) * 1.1
                for xx in range(int(cx - half), int(cx + half) + 1):
                    c = col if xx <= cx else shade(col, 0.78)
                    if season == WINTER and j % 3 == 0:
                        c = SNOW
                    img.set(xx, y, c)
        elif season == WINTER:
            for d in range(int(r * 1.6)):
                img.set(cx, cy - d, trunk)
                if d % 2 == 0:
                    img.set(cx - d * 0.4 - 1, cy - d, (130, 100, 80))
                    img.set(cx + d * 0.4 + 1, cy - d, (130, 100, 80))
            img.set(cx, cy - r * 1.6, SNOW)
        else:
            col = ((96, 176, 80), (52, 128, 56), ((214, 120, 48), (226, 176, 60), (176, 70, 40))[h % 3])[season]
            if season == SPRING and h % 4 == 0:
                col = (236, 190, 210)       # blossom
            img.disc(cx, cy - r * 0.4, r, col, light=shade(col, 1.22), dark=shade(col, 0.7))


# =============================================================================================
# Layout and drawing of a whole frame
# =============================================================================================
BG = (24, 26, 22)
PANEL = (34, 30, 26)
PANEL_LT = (48, 42, 34)
INK = (236, 228, 208)
DIM = (160, 150, 128)
GOLD = (244, 204, 108)
GOOD = (130, 214, 110)
BAD = (240, 110, 90)
HEAD_BG = (52, 40, 28)
SEASON_COL = ((140, 214, 110), (240, 210, 90), (232, 140, 60), (170, 200, 240))


def layout(cols, rows, hud=True):
    """(T, mx, my, panel column, panel width, log rows) for a window."""
    if not hud:
        T = max(1, min(cols // MAP_W, rows * 2 // MAP_H))
        return T, (cols - T * MAP_W) // 2, (rows * 2 - T * MAP_H) // 2, cols, 0, 0
    pw = clamp(cols // 4, 26, 40)
    mcols = cols - pw
    mpx = (rows - 2) * 2
    T = max(1, min((mcols - 2) // MAP_W, (mpx - 2) // MAP_H))
    mx = (mcols - T * MAP_W) // 2
    spare = mpx - T * MAP_H
    log = spare // 2 - 1 if spare >= 8 else 0
    my = 2 + (2 if log else max(1, spare // 2))
    if my % 2:
        my -= 1
    return T, mx, my, mcols, pw, log


_BACK = {}


def backdrop(cv, season, x0, y0, x1, y1, clock):
    """Around the map: the surrounding wold, darker, so the map reads as a board."""
    key = (season, x0, y0, x1, y1)
    rows = _BACK.get(key)
    if rows is None:
        if len(_BACK) > 16:
            _BACK.clear()
        g = shade(GRASS[season], 0.35) if season != WINTER else (70, 76, 90)
        rows = _BACK[key] = [[tex(g, x, y, 5, 0.05) for x in range(x0, x1)] for y in range(y0, y1)]
    for y in range(y0, y1):
        cv.px[y][x0:x1] = rows[y - y0]


_DIM = {}


def draw_map(cv, g, T, mx, my, season, show_ui=True):
    st = g.st
    px = cv.px
    item = MENU[g.sel] if show_ui else None
    placing = show_ui and item not in ("improve", "demolish")
    reach = st.reach() if placing else None
    # frame shadow
    cv.rect(mx - 1, my - 1, T * MAP_W + 2, T * MAP_H + 2, (14, 14, 12))
    for y in range(MAP_H):
        for x in range(MAP_W):
            img = tile_img(st, x, y, T, season)
            X, Y = mx + x * T, my + y * T
            if placing and (x, y) not in reach:
                d = _DIM.get(id(img))
                if d is None or d[0] is not img:
                    if len(_DIM) > 3000:
                        _DIM.clear()
                    d = _DIM[id(img)] = (img, [[mix(c, (20, 22, 26), 0.45) for c in row] for row in img])
                img = d[1]
            for j in range(T):
                px[Y + j][X:X + T] = img[j]
    animate(cv, g, T, mx, my, season)


def blend(cv, x, y, c, a):
    if 0 <= x < cv.W and 0 <= y < cv.H:
        cv.px[y][x] = mix(cv.px[y][x], c, a)


def animate(cv, g, T, mx, my, season):
    """What moves: water shimmer, chimney smoke, mill sails, the forge, falling snow or leaves."""
    st = g.st
    t = g.clock
    if T >= 3:
        for y in range(MAP_H):
            for x in range(MAP_W):
                if st.ter[y][x] != "~" or season == WINTER:
                    continue
                for k in range(max(1, T // 4)):
                    h = hsh(x, y * 7 + k, 41)
                    ph = (t * 0.7 + (h % 100) / 100.0) % 1.0
                    if ph < 0.5:
                        a = math.sin(ph * 2 * math.pi)
                        sx = mx + x * T + h % T
                        sy = my + y * T + (h >> 5) % T
                        for d in range(max(1, T // 5)):
                            blend(cv, sx + d, sy, (190, 226, 250), 0.6 * a)
    for (x, y), (k, tier) in st.bld.items():
        X, Y = mx + x * T, my + y * T
        if k in ("cottage", "hall", "smithy") and T >= 4:
            cx = X + int(T * ((0.8 if tier > 1 else 0.66) if k == "cottage" else 0.72 if k == "smithy" else 0.3))
            top = Y + int(T * (0.18 if k != "hall" else 0.1))
            n = 3 if season == WINTER or k == "smithy" else 2
            for p in range(n):
                ph = (t * 0.45 + p / n + hsh(x, y, 3) / 65536.0) % 1.0
                yy = top - ph * T * 0.9
                xx = cx + math.sin(ph * 5 + x) * T * 0.08 + ph * T * 0.15
                a = 0.55 * (1 - ph)
                r = max(0.5, T * 0.05 * (1 + ph * 2))
                for dy in range(-int(r), int(r) + 1):
                    for dx in range(-int(r), int(r) + 1):
                        if dx * dx + dy * dy <= r * r + 0.3:
                            blend(cv, int(xx) + dx, int(yy) + dy, (220, 220, 226), a)
        if k == "smithy" and T >= 4:
            f = 0.5 + 0.5 * math.sin(t * 9 + x)
            for dy in range(max(1, T // 5)):
                for dx in range(max(1, T // 5)):
                    blend(cv, X + int(T * 0.3) + dx, Y + int(T * 0.62) + dy, (255, 230, 120), 0.4 * f)
        if k == "mill":
            hx, hy = X + T * 0.5, Y + T * 0.34
            L = T * 0.46
            a0 = t * 1.6 + x
            col = (236, 230, 214) if T >= 4 else (230, 230, 230)
            for s in range(4):
                a = a0 + s * math.pi / 2
                ex, ey = hx + math.cos(a) * L, hy + math.sin(a) * L
                cv.line(hx, hy, ex, ey, (96, 72, 50))
                if T >= 8:
                    nx, ny = -math.sin(a), math.cos(a)
                    for q in range(2, int(L)):
                        bx, by = hx + math.cos(a) * q + nx * 1.5, hy + math.sin(a) * q + ny * 1.5
                        blend(cv, int(bx), int(by), col, 0.9)
                        blend(cv, int(hx + math.cos(a) * q + nx * 0.7), int(hy + math.sin(a) * q + ny * 0.7), col, 0.6)
            blend(cv, int(hx), int(hy), (60, 44, 30), 1.0)
    # weather
    W, H = T * MAP_W, T * MAP_H
    if season == WINTER:
        n = 30 + W * H // 200
        for i in range(n):
            h = hsh(i, 7, 51)
            sp = 0.25 + (h % 50) / 100.0
            x = mx + (h % W + int(math.sin(t * 1.3 + i) * 2)) % W
            y = my + int((h >> 3) % H + t * sp * T * 2) % H
            blend(cv, x, y, WHITE, 0.85)
            if T >= 8 and i % 3 == 0:
                blend(cv, x + 1, y, WHITE, 0.5)
    elif season == AUTUMN and T >= 3:
        n = 8 + W * H // 900
        for i in range(n):
            h = hsh(i, 9, 53)
            x = mx + (h % W + int(t * T * 0.8 + math.sin(t * 2 + i) * T * 0.4)) % W
            y = my + int((h >> 3) % H + t * T * 0.6) % H
            blend(cv, x, y, ((220, 120, 50), (236, 180, 70), (180, 70, 40))[i % 3], 0.9)
    elif season == SPRING and T >= 5:
        n = 4 + W * H // 2000
        for i in range(n):
            h = hsh(i, 11, 55)
            x = mx + (h % W + int(t * T * 0.5 + math.sin(t * 3 + i) * T)) % W
            y = my + (h >> 3) % H + int(math.sin(t * 4 + i) * 2)
            blend(cv, x, y, (250, 240, 140), 0.9)


# =============================================================================================
# One settlement in play: cursor, build menu, undo of this season, the season card, floating yields
# =============================================================================================
def item_name(item):
    return B[item]["name"] if item in B else TOOLS[item]["name"]


def item_cost(item):
    return B[item]["cost"] if item in B else TOOLS[item]["cost"]


def item_text(item):
    return B[item]["text"] if item in B else TOOLS[item]["text"]


class Game:
    def __init__(self, sc_i, seed=None, quiet=False):
        self.st = State(sc_i, seed)
        self.quiet = quiet
        self.cx, self.cy = self.st.hall
        self.sel = 1
        self.undos = []
        self.msg, self.msg_t, self.msg_col = "", 0.0, INK
        self.clock = 0.0
        self.card = None
        self.card_t = 9.0
        self.floats = []
        self.dust = []
        self.ev_sel = 0
        self.paused = self.help = False
        self.recorded = False
        self.new_best = False
        self.score = 0
        self._fc = (None, None, None)
        self.say("%s. %s. Plan, then Enter ends the season." % (self.st.sc["name"], goal_text(self.st)), GOLD)

    def snd(self, name, vol=1.0):
        if not self.quiet:
            SND.play(name, vol)

    def say(self, text, col=INK):
        self.msg, self.msg_t, self.msg_col = text, 0.0, col

    def fc(self):
        """forecast and look-ahead, computed again only when something changed."""
        st = self.st
        key = (st.ver, st.turn, st.study)
        if self._fc[0] != key:
            e = forecast(st)
            self._fc = (key, e, project(st, 4))
        return self._fc[1], self._fc[2]

    @property
    def item(self):
        return MENU[self.sel]

    def move(self, dx, dy):
        self.cx = clamp(self.cx + dx, 0, MAP_W - 1)
        self.cy = clamp(self.cy + dy, 0, MAP_H - 1)

    def pick(self, i):
        self.sel = i % len(MENU)
        self.snd("menu")

    def act(self, item=None):
        st = self.st
        if st.event or st.over:
            return False
        item = item or self.item
        ok, why = can_do(st, item, self.cx, self.cy)
        if not ok:
            self.say(why, BAD)
            self.snd("deny")
            return False
        snap = st.snapshot()
        msg = do_item(st, item, self.cx, self.cy)
        self.undos.append((snap, msg))
        self.say(msg[0].upper() + msg[1:] + ".  (U undoes)", INK)
        self.snd({"clear": "chop", "drain": "drain", "improve": "improve", "demolish": "demolish"}.get(item, "build"))
        for k in range(10):
            self.dust.append([self.cx + 0.5, self.cy + 0.8, (k - 4.5) * 0.12, -0.2 - (k % 3) * 0.1, 0.0])
        return True

    def undo(self):
        if not self.undos:
            self.say("Nothing to undo this season.", DIM)
            self.snd("deny")
            return False
        snap, msg = self.undos.pop()
        self.st.restore(snap)
        self.say("Undone: %s." % msg, DIM)
        self.snd("undo")
        return True

    def end_turn(self):
        st = self.st
        if st.event or st.over:
            return None
        rp = end_season(st)
        self.undos = []
        self.card, self.card_t = rp, 0.0
        self.floats = []
        for (x, y), (o, got, need, notes) in rp.per.items():
            main = [(v, r) for r, v in o.items() if v > 0 and r != "lore"] or [(v, r) for r, v in o.items() if v > 0]
            if main:
                v, r = max(main)
                self.floats.append((x, y, "+%d" % v, RES_COL[r], 0.0))
        self.snd("season%d" % st.season)
        if rp.starve or rp.freeze:
            self.snd("starve", 0.8)
        elif rp.births:
            self.snd("born", 0.6)
        if rp.learned:
            self.snd("learn", 0.8)
        if st.over:
            self.snd("won" if st.over == "won" else "lost")
            self.say(st.why, GOLD if st.over == "won" else BAD)
        elif st.event:
            self.snd("event", 0.7)
            self.ev_sel = next((i for i, o in enumerate(st.event.options) if option_ok(st, o)), 0)
        return rp

    def choose(self, i):
        st = self.st
        if not st.event or not 0 <= i < len(st.event.options):
            return False
        line = choose(st, i)
        if line is None:
            self.say("You cannot afford that.", BAD)
            self.snd("deny")
            return False
        self.say(line, GOLD)
        self.snd("coin" if "coin" in line else "menu")
        return True

    def cycle_study(self):
        st = self.st
        rest = [t[0] for t in TECHS if t[0] not in st.techs]
        if not rest:
            self.say("Everything is learned.", DIM)
            return
        i = rest.index(st.study) if st.study in rest else -1
        st.study = rest[(i + 1) % len(rest)]
        t = TECH[st.study]
        self.say("Studying %s (%d lore): %s." % (t[1], t[2], t[3]), RES_COL["lore"])
        self.snd("menu")

    def update(self, dt):
        self.clock += dt
        self.msg_t += dt
        self.card_t += dt
        self.floats = [f[:4] + (f[4] + dt,) for f in self.floats if f[4] + dt < 1.8]
        for d in self.dust:
            d[0] += d[2] * dt
            d[1] += d[3] * dt
            d[3] += 0.6 * dt
            d[4] += dt
        self.dust = [d for d in self.dust if d[4] < 0.6]


# =============================================================================================
# The frame: map, panel, header, messages, the season card, events, the end
# =============================================================================================
def help_lines():
    return ["THATCHWOLD - keys", "",
            "Arrows / WASD     move the cursor (hold to keep going)",
            "Tab ]  Sh-Tab [   next / previous building",
            "1 - 9, 0          Cottage ... Market directly",
            "B / E             build or use the tool at the cursor",
            "I / X             improve / pull down at the cursor",
            "U  Z  Backspace   undo a placement of this season",
            "K                 what the lore house studies",
            "H                 cursor back to the hall",
            "Enter / Space     end the season",
            "Esc / P           pause (Q there: leave)   ? help", "",
            "Every turn is a season. Farms give half in spring,",
            "full in summer, the harvest in autumn, nothing in",
            "winter, and every hearth burns wood in winter. The",
            "panel shows what the season brings (+12 food)",
            "before you end it. Build within 3 tiles of the village."]


def put_parts(cv, col, row, parts, bg):
    for text, fg in parts:
        cv.put(col, row, text, fg, bg)
        col += len(text)
    return col


def res_parts(st, e, r, w_num=4):
    v = st.res[r]
    d = e.delta[r]
    cap = st.cap(r)
    num = ("%d" % v).rjust(w_num)
    dc = GOOD if d > 0 else BAD if d < 0 else DIM
    ds = ("%+d" % d) if d else "  ."
    full = v + d > cap and r != "coin"
    return [(RES_NAME[r].ljust(6), RES_COL[r]), (num, INK), (("/%d" % cap) if r != "coin" else "", DIM),
            (" " + ds + ("!" if full else ""), BAD if full else dc)]


def preview(st, item, x, y):
    """What the chosen menu item would do on (x, y): (text, ok)."""
    ok, why = can_do(st, item, x, y)
    if not ok:
        return why, False
    if item in ("farm", "fishery", "woodcut", "quarry", "mine", "market"):
        season = st.season
        out, notes = output(st, x, y, item, 1, season, st.mods)
        r = {"farm": "food", "fishery": "food", "woodcut": "wood", "quarry": "stone", "mine": "ore",
             "market": "coin"}[item]
        now = int(out.get(r, 0) + 0.5)
        yr = sum(int(output(st, x, y, item, 1, s, {})[0].get(r, 0) + 0.5) for s in range(4))
        n = ", ".join(notes)
        return "+%d %s now, %d a year%s" % (now, r, yr, (" (" + n + ")") if n else ""), True
    if item == "lore":
        return "+%d lore a season" % (2 + (1 if st.count_bld(x, y, ("green",)) else 0)), True
    if item in ("well", "green"):
        n = sum(1 for p, (k, _) in st.bld.items() if k in HOUSES and dist(p, (x, y)) <= 2)
        return "cheers %d house%s nearby" % (n, "" if n == 1 else "s"), True
    if item == "mill":
        return "+1 food for %d farm%s beside it" % (st.count_bld(x, y, ("farm",)),
                                                  "" if st.count_bld(x, y, ("farm",)) == 1 else "s"), True
    if item == "tower":
        n = sum(1 for p, (k, _) in st.bld.items() if k in HOUSES and dist(p, (x, y)) <= 3)
        return "guards %d house%s%s" % (n, "" if n == 1 else "s", ", and the hall" if dist((x, y), st.hall) <= 3
                                        else ""), True
    return why, True


def bonus_tiles(st, item, x, y):
    """The tiles that feed the chosen item at (x, y): lit up while placing."""
    out = []
    want = {"farm": ("~", ("mill",)), "fishery": ("~", ()), "woodcut": ("f", ()), "quarry": ("ho", ("quarry", "mine")),
            "market": ("", HOUSES), "mill": ("", ("farm",)), "lore": ("", ("green",))}.get(item)
    if want:
        for a, b in st.around(x, y):
            if (a, b) in st.bld:
                if st.bld[(a, b)][0] in want[1]:
                    out.append((a, b))
            elif st.ter[b][a] in want[0] and want[0]:
                out.append((a, b))
    elif item in ("well", "green", "tower"):
        r = 3 if item == "tower" else 2
        out = [p for p, (k, _) in st.bld.items() if k in HOUSES and dist(p, (x, y)) <= r]
    return out


_GHOST = {}


def ghost_img(st, x, y, T, season, item):
    key = (st.ter[y][x], item, T, season, hsh(x, y, 1) % 251, shore_side(st, x, y) if item == "fishery" else None)
    img = _GHOST.get(key)
    if img is None:
        if len(_GHOST) > 400:
            _GHOST.clear()
        im = Img(T)
        paint_ground(im, "." if st.ter[y][x] == "f" else st.ter[y][x], season, key[4], 0)
        paint_building(im, item, 1, season, key[4], key[5], T)
        img = _GHOST[key] = im.p
    return img


def draw_cursor(cv, g, T, mx, my):
    st = g.st
    item = g.item
    x, y = g.cx, g.cy
    X, Y = mx + x * T, my + y * T
    ok, _ = can_do(st, item, x, y)
    if not st.event and not st.over:
        for a, b in bonus_tiles(st, item, x, y):
            for j in range(T):
                for i in range(T):
                    if i in (0, T - 1) or j in (0, T - 1) or T <= 3:
                        blend(cv, mx + a * T + i, my + b * T + j, (255, 226, 120), 0.55)
        if item in B and ok:
            img = ghost_img(st, x, y, T, st.season, item)
            a = 0.55 + 0.25 * math.sin(g.clock * 5)
            for j in range(T):
                for i in range(T):
                    blend(cv, X + i, Y + j, img[j][i], a)
        elif not ok and item not in ("improve", "demolish"):
            for j in range(T):
                for i in range(T):
                    blend(cv, X + i, Y + j, (220, 60, 50), 0.3)
    c = (255, 255, 255) if int(g.clock * 3) % 2 == 0 else (255, 214, 110)
    if not ok:
        c = (255, 140, 120) if int(g.clock * 3) % 2 == 0 else (230, 80, 70)
    if T <= 2:
        cv.frame(X - 1, Y - 1, T + 2, T + 2, c)
    else:
        cv.frame(X - 1, Y - 1, T + 2, T + 2, c)
        if T >= 8:
            cv.frame(X, Y, T, T, shade(c, 0.6))


def draw_header(cv, g, cols):
    st = g.st
    cv.put(0, 0, " " * cols, INK, HEAD_BG)
    x = put_parts(cv, 0, 0, [(" THATCHWOLD ", (30, 22, 12))], GOLD)
    x = put_parts(cv, x + 1, 0, [(st.sc["name"], INK), ("  ", INK), (SEASONS[st.season], SEASON_COL[st.season]),
                                 (", year %d" % st.year, INK)], HEAD_BG)
    frac, txt = goal_progress(st)
    left = st.left
    tail = "%s   %s " % (txt, ("%d season%s left" % (left, "" if left == 1 else "s")) if left is not None else
                         "score %d" % st.peak)
    if x + len(tail) + 12 < cols:
        bar = 10
        n = int(frac * bar + 0.5)
        cv.put(cols - len(tail) - bar - 2, 0, "#" * n, GOOD, HEAD_BG)
        cv.put(cols - len(tail) - bar - 2 + n, 0, "-" * (bar - n), DIM, HEAD_BG)
        cv.put(cols - len(tail), 0, tail, INK, HEAD_BG)
    elif x + len(tail) < cols:
        cv.put(cols - len(tail), 0, tail, INK, HEAD_BG)


def draw_panel(cv, g, x0, pw, rows):
    st = g.st
    e, proj = g.fc()
    bg = PANEL
    for r in range(1, rows - 1):
        cv.put(x0, r, " " * pw, INK, bg)
    c = x0 + 1
    w = pw - 2
    lines = []           # (parts, bg)
    compact = rows < 30
    head = "%s, year %d" % (SEASONS[st.season], st.year)
    word = ("harvest!" if st.season == AUTUMN else "no crops" if st.season == WINTER else
            "sowing" if st.season == SPRING else "growing")
    lines.append(([(head, SEASON_COL[st.season]), (("  " + word) if len(head) + len(word) + 2 <= w else "", DIM)],
                  PANEL_LT))
    if compact and w < 34:
        for a, b in (("food", "wood"), ("stone", "tools"), ("ore", "coin")):
            pa, pb = res_parts(st, e, a), res_parts(st, e, b)
            short = lambda p: [(p[0][0][:4], p[0][1]), (p[1][0].strip().rjust(4), INK),
                               ((" " + p[3][0].strip().replace(".", "")).ljust(4), p[3][1])]
            lines.append((short(pa) + [(" ", INK)] + short(pb), bg))
    else:
        for r in RES:
            lines.append((res_parts(st, e, r), bg))
    hs = st.housing()
    lines.append(([("Folk  ", INK), ("%d" % st.pop, GOLD), ("/%d homes" % hs, DIM),
                   ((" +%d" % e.births) if e.births else "", GOOD),
                   ((" -%d" % (e.starve + e.freeze)) if e.starve + e.freeze else "", BAD)], bg))
    lines.append(([("Jobs  ", INK), ("%d/%d" % (e.filled, e.jobs), INK if e.filled >= e.jobs else BAD),
                   ("  idle %d" % e.idle, DIM)], bg))
    bar = max(4, min(10, w - 16))
    n = int(st.mood / 100 * bar + 0.5)
    mc = GOOD if st.mood >= 60 else GOLD if st.mood >= 35 else BAD
    arrow = ">" if e.mood > st.mood + 0.5 else "<" if e.mood < st.mood - 0.5 else "="
    lines.append(([("Mood  ", INK), ("|" * n, mc), ("." * (bar - n), DIM), (" %d%s%d" % (st.mood, arrow, e.mood), mc)],
                  bg))
    t = TECH.get(st.study)
    if t:
        lines.append(([("Lore  ", RES_COL["lore"]), (t[1][:w - 14], INK), (" %d/%d" % (st.lore, t[2]), DIM),
                       ((" +%d" % e.delta["lore"]) if e.delta["lore"] else "", GOOD)], bg))
    else:
        lines.append(([("Lore  all learned", RES_COL["lore"])], bg))
    low = [i for i, (f, wd) in enumerate(proj) if f < 0]
    lowwood = [i for i, (f, wd) in enumerate(proj) if wd < 0]
    if low:
        lines.append(([("! food runs out in %d season%s" % (low[0] + 1, "" if low[0] == 0 else "s"), BAD)], bg))
    elif lowwood:
        lines.append(([("! no firewood in %d season%s" % (lowwood[0] + 1, "" if lowwood[0] == 0 else "s"), BAD)], bg))
    elif st.season in (SUMMER, AUTUMN):
        wf = proj[WINTER - st.season][0]
        lines.append(([("winter stores: %d food" % wf, DIM)], bg))
    # what is under the cursor
    here = []
    x, y = g.cx, g.cy
    b = st.bld.get((x, y))
    if b:
        o, got, need, notes = e.per.get((x, y), ({}, 0, 0, []))
        if b[0] in HOUSES:
            here.append([(bname(*b), INK), (" houses %d" % house_of(*b), DIM)])
        else:
            here.append([(bname(*b), INK), ((" %d/%d at work" % (got, need)) if need else "", GOOD if got >= need
                                           else BAD)])
        gives = "  ".join("%+d %s" % (v, r) for r, v in sorted(o.items(), key=lambda kv: -kv[1]) if v)
        if gives or notes:
            for l in wrap((gives or "nothing") + (("  (" + ", ".join(notes) + ")") if notes else ""), w)[:2]:
                here.append([(l, DIM)])
    else:
        here.append([(TERRAIN[st.ter[y][x]], INK), ("" if st.in_range(x, y) else "  out of reach", BAD)])
    txt, ok = preview(st, g.item, x, y)
    for l in wrap("%s: %s" % (item_name(g.item), txt) if ok and g.item in B else txt, w)[:3 if not compact else 2]:
        here.append([(l, GOOD if ok else BAD)])
    gl = wrap("Goal " + goal_text(st), w)
    goal = [([("Goal ", GOLD), (gl[0][5:], INK)], bg)] + [([(l, INK)], bg) for l in gl[1:2]]
    # build menu: whatever rows are left
    used = len(lines) + len(here) + len(goal) + 3
    room = max(1, rows - 2 - used)
    build = []
    n = len(MENU)
    show = min(n, room)
    start = clamp(g.sel - show // 2, 0, n - show)
    for i in range(start, start + show):
        it = MENU[i]
        cost = item_cost(it)
        okc = affordable(st, cost)
        locked = it in B and B[it].get("tech") and B[it]["tech"] not in st.techs
        key = str((i + 1) % 10) if i < 10 else " "
        name = item_name(it)
        ctext = "lore" if locked else cost_text(cost) if cost else ""
        ctext = ctext.replace(" wood", "w").replace(" stone", "s").replace(" tools", "t").replace(" coin", "c")
        room_n = w - 3 - len(ctext) - 1
        s = "%s %s" % (key, name[:room_n].ljust(room_n))
        fg = INK if okc and not locked else DIM
        if i == g.sel:
            build.append(([(">" + s, (24, 18, 10)), (" " + ctext, (60, 40, 20))], GOLD))
        else:
            build.append(([(" " + s, fg), (" " + ctext, GOOD if okc and not locked else DIM)], bg))
    lines.append(([("Build", GOLD), ("  B builds" if w < 30 else "  Tab / 1-0 pick, B builds", DIM)], PANEL_LT))
    lines += build
    lines.append(([("Here", GOLD)], PANEL_LT))
    lines += [(p, bg) for p in here]
    lines += goal
    r = 1
    for parts, lbg in lines:
        if r >= rows - 1:
            break
        if lbg != bg:
            cv.put(x0, r, " " * pw, INK, lbg)
        s = "".join(p[0] for p in parts)
        if len(s) > w:          # clip the last parts
            out, k = [], 0
            for tx, fg in parts:
                if k + len(tx) > w:
                    tx = tx[:max(0, w - k)]
                out.append((tx, fg))
                k += len(tx)
            parts = out
        put_parts(cv, c, r, parts, lbg)
        r += 1


def wrap(text, width):
    out, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = word
        else:
            line = (line + " " + word) if line else word
    if line:
        out.append(line)
    return out


def draw_event(cv, g, mcols, rows):
    st = g.st
    ev = st.event
    w = min(mcols - 4, 52)
    lines = [(ev.title.upper(), GOLD, None), ("", INK, None)]
    for t in ev.text:
        for l in wrap(t, w - 4):
            lines.append((l, INK, None))
    lines.append(("", INK, None))
    for i, o in enumerate(ev.options):
        ok = option_ok(st, o)
        cost = (" (%s)" % cost_text(o["cost"])) if o["cost"] else ""
        s = "%d %s%s" % (i + 1, o["label"], cost)
        fg = INK if ok else DIM
        lines.append((s[:w - 4], (24, 18, 10) if i == g.ev_sel else fg, GOLD if i == g.ev_sel else None))
        if o["hint"]:
            lines.append(("    " + o["hint"][:w - 8], DIM if ok else (110, 104, 92), None))
    lines.append(("", INK, None))
    lines.append(("Up/Down choose   Enter take   1-%d" % len(ev.options), DIM, None))
    h = len(lines) + 2
    x0 = max(0, (mcols - w) // 2)
    y0 = max(1, (rows - h) // 2)
    box = (30, 26, 22)
    for j in range(h):
        cv.put(x0, y0 + j, " " * w, INK, box)
    cv.put(x0, y0, " " * w, INK, (70, 54, 34))
    for j, (s, fg, hbg) in enumerate(lines):
        if hbg:
            cv.put(x0 + 1, y0 + 1 + j, " " * (w - 2), fg, hbg)
        cv.put(x0 + 2, y0 + 1 + j, s, fg, hbg or box)


def draw_card(cv, g, mcols, T, mx, my):
    rp = g.card
    if rp is None or g.card_t > 2.8:
        return
    st = g.st
    s1 = " %s ends - %s, year %d " % (SEASONS[rp.season], SEASONS[st.season], st.year)
    gains = ["%+d %s" % (v, r) for r, v in rp.got.items() if v]
    s2 = " " + ("  ".join(gains) or "no change") + " "
    extra = (" " + ", ".join(rp.lines) + " ") if rp.lines else ""
    row = max(1, my // 2 + 1)
    col = SEASON_COL[st.season]
    cv.center(row, s1[:mcols], (20, 16, 10), col, 0, mcols)
    cv.center(row + 1, s2[:mcols], INK, (30, 26, 22), 0, mcols)
    if extra:
        cv.center(row + 2, extra[:mcols], GOLD, (30, 26, 22), 0, mcols)


def draw_over(cv, g, mcols, rows):
    st = g.st
    won = st.over == "won"
    if st.sc_i == ENDLESS:
        head = "THE WOLD WENT QUIET"
    else:
        head = ("%s THRIVES" % st.sc["name"].upper()) if won else "THE GOAL WAS NOT MET"
    lines = [head, "", st.why, "",
             "%d folk, %d buildings, %d lore learned" % (st.pop, len(st.bld), len(st.techs)),
             "after %d season%s" % (st.turn, "" if st.turn == 1 else "s"), ""]
    if won or st.sc_i == ENDLESS:
        lines.append("Score %d%s" % (g.score, "   new best!" if g.new_best else ""))
    lines += ["", "Enter: back to the title"]
    w = max(len(l) for l in lines) + 4
    x0 = max(0, (mcols - w) // 2)
    y0 = max(1, (rows - len(lines)) // 2 - 1)
    for j, l in enumerate([""] + lines + [""]):
        fg = GOLD if j == 1 else INK
        cv.put(x0, y0 + j, (" " * 2 + l).ljust(w), fg, (40, 32, 24))


def render(g, cols, rows, hud=True):
    st = g.st
    season = st.season
    cv = Canvas(cols, rows, BG)
    T, mx, my, mcols, pw, log = layout(cols, rows, hud)
    backdrop(cv, season, 0, 2 if hud else 0, mcols, cv.H - (2 if hud else 0), g.clock)
    draw_map(cv, g, T, mx, my, season, show_ui=hud)
    if not hud:
        return cv
    if not st.over:
        draw_cursor(cv, g, T, mx, my)
    for d in g.dust:
        blend(cv, int(mx + d[0] * T), int(my + d[1] * T), (210, 190, 150), 0.8 * (1 - d[4] / 0.6))
    if T >= 4:
        for x, y, text, col, age in g.floats:
            if age < 0.25:
                continue
            row = (my + y * T) // 2 - int((age - 0.25) * 2.2)
            c0 = mx + x * T + T // 2 - len(text) // 2
            if 1 <= row < rows - 1 and 0 <= c0 and c0 + len(text) <= mcols:
                cv.put(c0, row, text, col)
    draw_header(cv, g, cols)
    draw_panel(cv, g, mcols, pw, rows)
    if log > 0:
        r0 = (my + T * MAP_H) // 2 + 1
        entries = st.log[-log:]
        for j, l in enumerate(entries):
            cv.put(1, r0 + j, l[:mcols - 2], DIM if j < len(entries) - 1 else INK)
    # bottom row: the message, else the keys
    cv.put(0, rows - 1, " " * cols, DIM, HEAD_BG)
    if g.msg and g.msg_t < 5:
        cv.put(1, rows - 1, g.msg[:cols - 2], g.msg_col, HEAD_BG)
    else:
        hints = ["arrows move", "Tab/1-0 pick", "B build", "U undo", "K lore", "Enter end season", "? help"]
        while hints and len("   ".join(hints)) + 2 > cols:
            hints.pop()
        cv.put(1, rows - 1, "   ".join(hints), DIM, HEAD_BG)
    draw_card(cv, g, mcols, T, mx, my)
    if st.event and not st.over:
        draw_event(cv, g, mcols, rows)
    if st.over:
        draw_over(cv, g, mcols, rows)
    if g.paused:
        overlay(cv, help_lines() if g.help else PAUSE_LINES[:-1] + [
            "Q                 %s" % ("retire (score kept)" if st.sc_i == ENDLESS else "leave the wold"), "",
            SND.label()])
    return cv


# =============================================================================================
# Scores
# =============================================================================================
def score_key(sc_i):
    return "endless" if sc_i == ENDLESS else "s%d" % (sc_i + 1)


def record(g):
    """Store the result once (never in auto mode or the self-test)."""
    if g.recorded:
        return
    g.recorded = True
    st = g.st
    g.score = final_score(st)
    if g.score > 0:
        g.new_best = submit(GAME, score_key(st.sc_i), g.score)


# =============================================================================================
# The auto-mode reeve at work on screen: the cursor walks to each spot, the menu turns, it builds
# =============================================================================================
class Pilot:
    """Drives a Game with the Reeve, step by step and visibly."""
    MOVE = 0.06
    THINK = 0.25
    END = 0.7
    EVENT = 1.3

    def __init__(self, g):
        self.g = g
        self.bot = Reeve(g.st)
        self.plan = None
        self.t = 0.0
        self.acts = 0

    def step(self, dt):
        g, st = self.g, self.g.st
        self.t += dt
        if st.over:
            return
        if st.event:
            if self.plan is None or self.plan[0] != "event":
                self.plan = ("event", self.bot.choose_event(st))
                g.ev_sel = self.plan[1]
                self.t = 0.0
            if self.t >= self.EVENT:
                g.choose(self.plan[1])
                self.plan = None
                self.t = 0.0
            return
        if g.card_t < 1.2:
            return
        if self.plan is None:
            if self.t < self.THINK:
                return
            a = self.bot.next_action(st) if self.acts < 14 else None
            self.plan = a or ("end",)
            self.t = 0.0
        if self.plan[0] == "end":
            if self.t >= self.END:
                g.end_turn()
                self.plan = None
                self.acts = 0
                self.t = 0.0
            return
        item, x, y = self.plan
        if MENU[g.sel] != item:
            if self.t >= self.MOVE:
                d = 1 if (MENU.index(item) - g.sel) % len(MENU) <= len(MENU) // 2 else -1
                g.sel = (g.sel + d) % len(MENU)
                self.t = 0.0
            return
        if (g.cx, g.cy) != (x, y):
            if self.t >= self.MOVE:
                g.move((x > g.cx) - (x < g.cx), (y > g.cy) - (y < g.cy))
                self.t = 0.0
            return
        if self.t >= self.THINK:
            if not g.act(item):
                raise AssertionError("the reeve's %s at %d,%d failed: %s" % (item, x, y, g.msg))
            self.acts += 1
            self.plan = None
            self.t = 0.0


class TitleDemo:
    """The reeve building villages behind the title and in the launcher preview."""
    PICK = (0, 2, 3, 1, 4)

    def __init__(self, k=0):
        self.k = k
        self.new_run()

    def new_run(self):
        i = self.PICK[self.k % len(self.PICK)]
        self.k += 1
        self.g = Game(i, quiet=True)
        self.p = Pilot(self.g)
        self.p.MOVE, self.p.THINK, self.p.END, self.p.EVENT = 0.03, 0.08, 0.35, 0.5
        self.done_t = 0.0

    def scene(self, cols, rows, dt):
        g = self.g
        dt = min(dt, 0.1)
        for _ in range(3):
            g.update(dt / 3)
            self.p.step(dt / 3)
        if g.st.over or g.st.turn >= 4 * 7:
            self.done_t += dt
            if self.done_t > 2.0:
                self.new_run()
        return render(self.g, cols, max(1, rows), hud=False)


class AutoRun:
    """Auto mode: the reeve plays the chosen scenario, then the next ones. Nothing is recorded."""

    def __init__(self, sc_i, sound=True):
        self.auto = AutoMode()
        self.sound = sound
        self.sc_i = sc_i
        self.played = 0
        self.new()

    def new(self):
        self.g = Game(self.sc_i, quiet=not self.sound)
        self.p = Pilot(self.g)
        self.over_t = 0.0

    def key(self, k):
        a = self.auto.key(k)
        if a == "sound" and SND.toggle():
            SND.play("sound_on")
        return a

    def frame(self, dt, cols, rows, draw=True):
        sdt = self.auto.scale(dt)
        n = max(1, int(self.auto.speed))
        for _ in range(n):
            self.g.update(sdt / n)
            self.p.step(sdt / n)
        if self.g.st.over:
            self.g.score = final_score(self.g.st)
            self.over_t += sdt
            if self.over_t > 5.0:
                self.played += 1
                self.sc_i = (self.sc_i + 1) % len(SCENARIOS)
                self.new()
        if not draw:
            return None
        cv = render(self.g, cols, rows)
        self.auto.banner(cv, extra=self.g.st.sc["short"])
        return cv


# =============================================================================================
# Menus and loops
# =============================================================================================
MIN_W, MIN_H = 70, 22


def too_small(term):
    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (%dx%d)." % (MIN_W, MIN_H))


def run_auto(term, sc_i):
    run = AutoRun(sc_i)
    last = time.time()
    while True:
        now = time.time()
        dt, last = min(0.1, now - last), now
        for k, kind in term.events(0):
            if kind == "press" and run.key(k) == "stop":
                return
        cols, rows = term.size()
        if cols < MIN_W or rows < MIN_H:
            too_small(term)
            time.sleep(0.2)
            continue
        term.write(run.frame(dt, cols, rows).emit())
        time.sleep(max(0.0, 1 / 30 - (time.time() - now)))


def play(term, sc_i, seed=None):
    g = Game(sc_i, seed)
    SND.play("start")
    last = time.time()
    while True:
        now = time.time()
        dt = min(0.1, now - last)
        last = now
        st = g.st
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
                if st.sc_i == ENDLESS and st.turn > 0 and not st.over:
                    st.peak = max(st.peak, prosperity(st))
                    record(g)
                return
            elif a == "help":
                g.help = not g.help
                g.paused = True
            elif a == "sound":
                if SND.toggle():
                    SND.play("sound_on")
            elif a is None:
                if st.over:
                    if name in ("enter", " ") and kind == "press":
                        return
                    continue
                if st.event:
                    n = len(st.event.options)
                    if name in ("up", "w"):
                        g.ev_sel = (g.ev_sel - 1) % n
                        g.snd("menu")
                    elif name in ("down", "s", "tab"):
                        g.ev_sel = (g.ev_sel + 1) % n
                        g.snd("menu")
                    elif name in ("enter", " ") and kind == "press" and g.card_t > 0.4:
                        g.choose(g.ev_sel)
                    elif name.isdigit() and 1 <= int(name) <= n and kind == "press":
                        g.ev_sel = int(name) - 1
                        g.choose(g.ev_sel)
                    continue
                mv = {"up": (0, -1), "w": (0, -1), "down": (0, 1), "s": (0, 1), "left": (-1, 0), "a": (-1, 0),
                      "right": (1, 0), "d": (1, 0)}.get(name)
                if mv:
                    g.move(*mv)
                elif kind != "press":
                    continue
                elif name in ("tab", "]"):
                    g.pick(g.sel + 1)
                elif name in ("backtab", "["):
                    g.pick(g.sel - 1)
                elif name.isdigit():
                    g.pick((int(name) - 1) % 10)
                elif name in ("b", "e"):
                    g.act()
                elif name == "i":
                    g.act("improve")
                elif name == "x":
                    g.act("demolish")
                elif name in ("u", "z", "backspace"):
                    g.undo()
                elif name == "k":
                    g.cycle_study()
                elif name == "h":
                    g.cx, g.cy = st.hall
                elif name in ("enter", " "):
                    g.end_turn()
        cols, rows = term.size()
        if cols < MIN_W or rows < MIN_H:
            too_small(term)
            time.sleep(0.2)
            last = time.time()
            continue
        if not g.paused:
            g.update(dt)
        if g.st.over and not g.recorded:
            record(g)
        term.write(render(g, cols, rows).emit())
        time.sleep(max(0.0, 1 / 30 - (time.time() - now)))


def menu_items(sc_i):
    sc = SCENARIOS[sc_i]
    label = "%d %s (%s)" % (sc_i + 1, sc["name"], sc["level"]) if sc_i != ENDLESS else "Endless (a new wold)"
    return ["Settle      < %s >" % label, "%s   < %s >" % (AUTO_LABEL, sc["short"])]


def render_menu(demo, cols, rows, sel, sc_i, dt, help_):
    cv = demo.scene(cols, rows, dt)
    sc = SCENARIOS[sc_i]
    b = load_scores().get(GAME, {}).get(score_key(sc_i))
    best = ("best %s  %d" % (sc["name"], b)) if b else None
    g = sc["goal"]
    gl = {"pop": "grow to %d folk" % g[1], "coin": "gather %d coin" % g[1], "ring": "raise the Moot Ring",
          "popring": "%d folk and the Moot Ring" % g[1], "endless": "prosper; score = best prosperity"}[g[0]]
    when = ("in %d years" % sc["years"]) if sc["years"] else "no time limit"
    extra = [""] + sc["blurb"] + ["Goal: %s, %s." % (gl, when)]
    title_screen(cv, NAME, TAGLINE, menu_items(sc_i), sel, best, extra=extra,
                 keys="Up/Down choose   Left/Right scenario   Enter start   M %s   ? help   Esc back" %
                      SND.label().lower(), help_lines=help_lines(), show_help=help_, dim=0.45)
    return cv


def main():
    with KeyTerminal() as term:
        demo = TitleDemo()
        sel, sc_i, help_ = 0, 0, False
        last = time.time()
        while True:
            now = time.time()
            cols, rows = term.size()
            if cols < MIN_W or rows < MIN_H:
                too_small(term)
                if any(k in ("q", "esc") for k, kind in term.events(0.3) if kind == "press"):
                    return
                last = time.time()
                continue
            term.write(render_menu(demo, cols, rows, sel, sc_i, min(0.1, now - last), help_).emit())
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
                elif k in ("down", "s", "tab", "up", "w"):
                    sel = 1 - sel
                    SND.play("menu")
                elif k in ("left", "a", "right", "d"):
                    sc_i = (sc_i + (-1 if k in ("left", "a") else 1)) % len(SCENARIOS)
                    SND.play("menu")
                elif k == "m":
                    if SND.toggle():
                        SND.play("sound_on")
                elif k in ("enter", " "):
                    go = True
            if not go:
                continue
            if sel == 1:
                run_auto(term, sc_i)
            else:
                play(term, sc_i)
            last = time.time()


# =============================================================================================
# Self-test
# =============================================================================================
def selftest():
    t0 = time.time()
    global submit

    def no_scores(*a, **k):
        raise AssertionError("the self-test must not write scores")
    submit = no_scores
    # 1. the scenarios and their maps
    assert len(SCENARIOS) == 6 and len(set(s["name"] for s in SCENARIOS)) == 6
    for i, sc in enumerate(SCENARIOS[:ENDLESS]):
        rows = sc["map"]
        assert len(rows) == MAP_H and all(len(r) == MAP_W for r in rows), sc["name"]
        assert "".join(rows).count("@") == 1, sc["name"]
        assert set("".join(rows)) <= set(".rsfhom~@"), sc["name"]
        st = State(i)
        for need in "fh~o":
            assert any(need in r for r in rows), "%s has no %s" % (sc["name"], need)
        d = min(dist(st.hall, (x, y)) for y in range(MAP_H) for x in range(MAP_W) if st.ter[y][x] == "f")
        assert d <= 2 * RANGE, "%s: the woods are %d tiles from the hall" % (sc["name"], d)
    for seed in range(40):
        rows = gen_map(seed)
        assert "".join(rows).count("@") == 1 and len(rows) == MAP_H
    print("scenarios: 5 hand-made maps 18x12 (easy to hardest) + endless; 40 generated wolds valid")
    # 2. placement rules, costs, undo
    st = State(0)
    hx, hy = st.hall
    assert can_do(st, "farm", hx + 1, hy)[0]
    assert not can_do(st, "farm", hx + RANGE + 1, hy)[0], "built out of reach"
    assert not can_do(st, "quarry", hx + 1, hy)[0], "a quarry on meadow"
    assert not can_do(st, "fishery", hx + 1, hy)[0], "a fishery without water"
    assert not can_do(st, "mill", hx + 1, hy)[0], "a mill before milling"
    assert not can_do(st, "farm", hx, hy)[0], "built on the hall"
    assert not can_do(st, "demolish", hx, hy)[0], "the hall pulled down"
    g = Game(0, quiet=True)
    before = g.st.snapshot()
    g.cx, g.cy = hx + 1, hy
    assert g.act("farm") and g.st.res["wood"] == before[2]["wood"] - 4
    g.cx += 1
    assert g.act("cottage")
    g.cx, g.cy = 7, 4
    assert g.act("clear") and g.st.ter[4][7] == "."
    while g.undo():
        pass
    assert g.st.snapshot() == before, "undo did not bring the season back"
    g.cx, g.cy = hx + 1, hy
    g.act("farm")
    g.end_turn()
    assert not g.undos and not g.undo(), "a past season could be undone"
    print("placement: terrain, reach, lore, costs; undo of every placement of the season, none after it")
    # 3. the forecast is the truth: what the panel promises is what ending the season does
    checked = 0
    for i in range(ENDLESS + 1):
        st = State(i, seed=5)
        bot = Reeve(st)
        while not st.over and st.turn < 40:
            for _ in range(14):
                a = bot.next_action(st)
                if not a:
                    break
                do_item(st, *a)
            e = forecast(st)
            want = {r: max(0, min(st.cap(r), st.res[r] + e.delta[r])) for r in RES}
            pop = st.pop - min(e.starve + e.freeze, st.pop - 1) + e.births
            mood = e.mood
            end_season(st)
            assert all(st.res[r] == want[r] for r in RES), "forecast %s, got %s" % (want, st.res)
            assert st.pop == pop and abs(st.mood - mood) < 1e-9, "people or mood differ from the forecast"
            checked += 1
            if st.event:
                choose(st, bot.choose_event(st))
    print("forecast: %d seasons in all scenarios end exactly as the panel said (stores, folk, mood)" % checked)
    # 4. seasons
    st = State(0)
    st.bld[(st.hall[0] + 1, st.hall[1])] = ("farm", 1)
    ys = [output(st, st.hall[0] + 1, st.hall[1], "farm", 1, s, {})[0]["food"] for s in range(4)]
    assert ys[WINTER] == 0 and ys[SPRING] < ys[SUMMER] < ys[AUTUMN], ys
    st.turn = WINTER
    e = economy(st)
    assert e.heat == 1 and e.delta["wood"] == 1 - 1, "the hall's hearth burns no wood in winter"
    print("seasons: farm %s food (spring, summer, autumn, winter); every hearth burns wood in winter" %
          "/".join("%g" % y for y in ys))
    # 5. no runaway exploits: loops lose, stores and folk are bounded, growth flattens out
    for k, bd in B.items():
        back = sum(v // 2 for r, v in bd["cost"].items() if r in ("wood", "stone"))
        assert k == "hall" or back < sum(bd["cost"].values()), "%s: pulling down pays" % k
    st = State(0)
    rng = random.Random(1)
    for _ in range(30):
        ev = ev_trader(st, rng)
        buy, sell = ev.options[0], ev.options[2]
        assert buy["cost"]["coin"] > 0 and sell["cost"]["wood"] > 0
    forest = sum(r.count("f") for r in SCENARIOS[0]["map"])
    st = bot_game(ENDLESS, seed=77, years=1)
    curve = []
    peak_rate = 0.0
    for yr in range(40):
        bot = Reeve(st)
        for _ in range(4):
            if st.over:
                break
            e = forecast(st)
            gross = sum(max(0, v) for (o, got, need, n) in e.per.values() for v in o.values())
            peak_rate = max(peak_rate, gross / max(1, e.filled))
            bot.play_season(st)
            assert st.pop <= st.housing() + 3, "more folk than homes"
            assert all(0 <= st.res[r] <= st.cap(r) for r in RES), "stores over their room"
        curve.append(st.pop)
    g10, g20, g40 = curve[9] - curve[4], curve[19] - curve[14], curve[39] - curve[34]
    assert not st.over and st.pop >= 40, "the endless village did not grow (%d)" % st.pop
    assert g40 <= max(g10, g20) + 2, "growth keeps speeding up: %s" % curve
    assert peak_rate <= 8, "a worker yields %.1f a season" % peak_rate
    caps = st.cap("food")
    print("economy: no loop pays (pull down: half back; traders one way; %d trees to fell on Brackenleigh);" % forest)
    print("  endless 40 years: folk %s; growth per 5 years %d, %d, %d (it flattens, land is finite);" % (
        " ".join(str(curve[i]) for i in (4, 9, 19, 29, 39)), g10, g20, g40))
    print("  at most %.1f goods per worker a season; stores never above their room (food room %d)" % (peak_rate, caps))
    # 6. the reeve wins every scenario, on its own seed and on other seeds (other events)
    for i in range(ENDLESS):
        sc = SCENARIOS[i]
        used = []
        for seed in [None] + list(range(1, 13)):
            st = bot_game(i, seed=seed)
            assert st.over == "won", "%s (seed %s): %s" % (sc["name"], seed, st.why)
            used.append(st.turn)
        print("  %-12s %-7s goal %-26s won 13/13 in %2d-%2d of %d seasons, score %d" % (
            sc["name"], sc["level"], goal_text(State(i)).lower(), min(used), max(used), sc["years"] * 4,
            final_score(bot_game(i))))
    print("reeve: every scenario won by the auto-mode economy (only what the player sees)")
    # 7. rendering at every size
    timing = []
    frames = 0
    for cols, rows in ((70, 22), (80, 24), (100, 32), (120, 40), (160, 50), (240, 70)):
        tr = te = 0.0
        n = 0
        for i in (0, 2, 3, 4):
            g = Game(i, quiet=True)
            p = Pilot(g)
            for _ in range(int(30 * 8)):
                g.update(1 / 30)
                p.step(1 / 30 * 6)
            for s in range(4):
                g.st.turn = g.st.turn - g.st.turn % 4 + s
                a = time.time()
                cv = render(g, cols, rows)
                b = time.time()
                cv.emit(True)
                c_ = time.time()
                tr += b - a
                te += c_ - b
                n += 1
                g.update(0.05)
            g.sel = MENU.index("farm")
            render(g, cols, rows).emit(True)
            g.paused = g.help = True
            render(g, cols, rows)
            g.paused = g.help = False
            st = g.st
            if not st.event:
                st.event = ev_trader(st, random.Random(1))
            render(g, cols, rows).emit(True)
            st.event = None
            st.over, st.why = "won", "test"
            render(g, cols, rows).emit(True)
            frames += n + 4
        timing.append((cols, rows, tr / n * 1000, te / n * 1000))
    d = TitleDemo()
    for cols, rows in ((70, 22), (120, 40), (24, 8), (40, 12), (30, 9)):
        if rows >= 20:
            render_menu(d, cols, rows, 0, 2, 0.05, False).emit(True)
        else:
            d.scene(cols, rows, 0.05).emit(True)
        frames += 1
    for _ in range(600):
        d.scene(30, 9, 0.1)
    print("rendering: %d frames at 70x22 .. 240x70, all four seasons, events, help, the end, title, preview" % frames)
    for cols, rows, r_, e_ in timing:
        print("  %3dx%-3d render %5.1f ms  emit %5.1f ms  = %5.1f ms per frame (%3.0f fps)" % (
            cols, rows, r_, e_, r_ + e_, 1000 / max(0.1, r_ + e_)))
    # 8. auto mode: plays on screen, pause, speed, stop; nothing recorded
    run = AutoRun(0, sound=False)
    for _ in range(60):
        run.frame(1 / 30, 80, 24, draw=False)
    run.key(" ")
    snap = (run.g.st.turn, len(run.g.st.bld), run.g.clock)
    for _ in range(30):
        run.frame(1 / 30, 80, 24, draw=False)
    assert (run.g.st.turn, len(run.g.st.bld), run.g.clock) == snap, "auto mode ran on while paused"
    run.key(" ")
    for _ in range(5):
        run.key("+")
    assert run.auto.speed == 8.0
    for i in range(30 * 90):
        run.frame(1 / 30, 70 + i % 3 * 25, 22 + i % 2 * 10, draw=i % 30 == 0)
    assert run.played >= 1, "auto mode did not finish a scenario in 90 s at x8"
    assert run.key("esc") == "stop"
    print("auto mode: %d scenario(s) played to the end in 90 s at x8, now %s %s; nothing recorded" % (
        run.played, run.g.st.sc["name"], run.g.st.when()))
    # 9. simulation speed
    a = time.time()
    st = bot_game(ENDLESS, seed=3, years=10)
    print("simulation: %.1f ms per season with the reeve's choices (endless, %d folk)" % (
        (time.time() - a) / 40 * 1000, st.pop))
    print("Self-test ok (%.1f s)" % (time.time() - t0))


def screenshot(cols=100, rows=32):
    """README picture: the auto-mode reeve on Gorsecombe (seed 5), summer of year 3: farms on drained marsh
    beside the river, a farm being placed with its bonuses lit. Deterministic and quiet, nothing written."""
    g = Game(2, seed=5, quiet=True)
    bot = Reeve(g.st)
    while g.st.turn < 9:
        bot.play_season(g.st)
    g.st.event = None
    g.sel = MENU.index("farm")
    sp = spots(g.st, "farm")
    if sp:
        g.cx, g.cy = max(sp, key=lambda p: (food_value(g.st, "farm", *p), -dist(p, g.st.hall)))
    g.floats = []
    g.clock = 3.3
    g.msg = ""
    g.st.log = g.st.log[-6:]
    return render(g, cols, rows)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--auto" in sys.argv:
        with KeyTerminal() as _term:
            run_auto(_term, 0)
    else:
        main()
