#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""WARDSTONE - raise rune towers against the Hollow host.

The Hollow host marches out of the old portals to drain the Wardstones, the glowing standing stones that keep
the valley lands alive. Move the cursor over the land and raise towers beside the roads: Bolt Spires, Mortar
Kilns, Frost Bells, Storm Coils, Sky Harpoons, Venom Briars and Beacon Shrines. Each tower has three levels
and then two paths to choose from. Eight lands - a holly vale, a salt marsh, an ember canyon, a lantern
market, a frozen pass, moss-grown ruins, a clockwork yard and a starfall crater - some with fixed roads, some
open squares where your own towers shape the way. Scuttlers, Dartlings, Shellbacks, Wisps, Mirelumps that
split, Menders that heal, shielded Bulwarks, Gravelhorns, Gale Crows and four great bosses. Waves are shown
before they come; call them early for gold, earn interest, speed the game up. Three stars per land; the
campaign runs through all eight, endless mode never stops.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
"""
import math
import random
import sys
import time

from arcadekit import (ACCENTS, AUTO_LABEL, PAUSE_LINES, AutoMode, Canvas, KeyTerminal, clamp, load_scores, mix,
                       overlay, scale_art, shade, shared_key, submit, title_screen)
from arcadesound import Sound

GAME = "wardstone"
NAME = "WARDSTONE"
TAGLINE = "raise rune towers against the Hollow"
ACCENTS.setdefault(NAME, ((246, 224, 150), (64, 168, 146)))

GW, GH = 24, 14                 # the land in tiles
DT = 1 / 30                     # simulation step
FIRST_WAIT = 45.0               # seconds before the first wave comes by itself
WAVE_GAP = 14.0                 # countdown after a wave has fully marched out
SELL_BACK = 0.7
INTEREST, INTEREST_CAP = 0.04, 25
MIN_COLS, MIN_ROWS = 70, 22
WHITE = (255, 255, 255)
INF = 1 << 30

# =============================================================================================
# Towers: three levels, then two paths
# =============================================================================================
TOWERS = {
    "bolt": dict(name="Bolt Spire", short="Spire", cost=50, air=True, ground=True, role="single target, hits air too",
                 levels=[dict(dmg=9, rate=1.5, rng=2.6), dict(cost=55, dmg=15, rate=1.7, rng=2.9),
                         dict(cost=90, dmg=23, rate=1.9, rng=3.1)],
                 branches=[dict(name="Longshot", cost=170, dmg=62, rate=1.25, rng=4.6, crit=0.25,
                                desc="long range, critical hits"),
                           dict(name="Twinbolt", cost=160, dmg=27, rate=2.3, rng=3.3, multi=2,
                                desc="two bolts at two foes")]),
    "mortar": dict(name="Mortar Kiln", short="Kiln", cost=90, air=False, ground=True, role="splash, ground only",
                   levels=[dict(dmg=20, rate=0.5, rng=3.2, splash=0.95), dict(cost=80, dmg=34, rate=0.55, rng=3.4, splash=1.05),
                           dict(cost=120, dmg=52, rate=0.6, rng=3.6, splash=1.15)],
                   branches=[dict(name="Emberstorm", cost=220, dmg=66, rate=0.62, rng=3.7, splash=1.25, burn=20,
                                  desc="shells leave burning ground"),
                             dict(name="Quakeshell", cost=220, dmg=112, rate=0.5, rng=3.8, splash=1.5, stun=0.7,
                                  desc="a huge blast that stuns")]),
    "frost": dict(name="Frost Bell", short="Bell", cost=70, air=True, ground=True, role="slows everything near it",
                  levels=[dict(dmg=2, rate=0.9, rng=2.0, slow=0.35), dict(cost=60, dmg=4, rate=0.95, rng=2.3, slow=0.45),
                          dict(cost=90, dmg=7, rate=1.0, rng=2.5, slow=0.52)],
                  branches=[dict(name="Rimefang", cost=180, dmg=12, rate=1.0, rng=2.7, slow=0.6, freeze=0.12,
                                 desc="may freeze foes solid"),
                            dict(name="Brittle Chime", cost=170, dmg=8, rate=1.0, rng=3.0, slow=0.5, brittle=0.35,
                                 desc="chilled foes take +35%")]),
    "storm": dict(name="Storm Coil", short="Coil", cost=110, air=True, ground=True, role="chain lightning, no armour",
                  levels=[dict(dmg=14, rate=0.75, rng=2.6, jumps=3), dict(cost=100, dmg=23, rate=0.8, rng=2.8, jumps=4),
                          dict(cost=140, dmg=34, rate=0.85, rng=3.0, jumps=5)],
                  branches=[dict(name="Tempest", cost=240, dmg=44, rate=1.0, rng=3.2, jumps=9,
                                 desc="arcs through nine foes"),
                            dict(name="Overload", cost=220, dmg=62, rate=0.9, rng=3.1, jumps=4, strip=True,
                                 desc="tears shields apart")]),
    "harpoon": dict(name="Sky Harpoon", short="Harpoon", cost=80, air=True, ground=False, role="anti-air, heavy hits",
                    levels=[dict(dmg=36, rate=0.85, rng=3.6), dict(cost=70, dmg=60, rate=0.95, rng=3.9),
                            dict(cost=110, dmg=92, rate=1.0, rng=4.2)],
                    branches=[dict(name="Flak Rose", cost=200, dmg=78, rate=1.5, rng=4.3, splash=1.2,
                                   desc="bursting flak for flocks"),
                              dict(name="Skypiercer", cost=210, dmg=240, rate=0.8, rng=5.2, boss=1.5,
                                   desc="huge spears, +50% on bosses")]),
    "venom": dict(name="Venom Briar", short="Briar", cost=75, air=False, ground=True, role="poison, stops healing",
                  levels=[dict(dps=6, rate=1.0, rng=2.4, dur=4.0), dict(cost=70, dps=11, rate=1.0, rng=2.6, dur=4.0),
                          dict(cost=100, dps=18, rate=1.05, rng=2.8, dur=4.0)],
                  branches=[dict(name="Rotbloom", cost=190, dps=27, rate=1.1, rng=2.9, dur=4.5, spread=1.3,
                                 desc="poison spreads when foes fall"),
                            dict(name="Witherthorn", cost=180, dps=22, rate=1.1, rng=2.9, dur=4.5, multi=3, corrode=4,
                                 desc="three targets, eats armour")]),
    "beacon": dict(name="Beacon Shrine", short="Shrine", cost=120, air=False, ground=False, role="buffs towers next to it",
                   levels=[dict(buff=0.15, rng=1.5), dict(cost=100, buff=0.22, rng=1.5, plus=0.3),
                           dict(cost=140, buff=0.3, rng=1.9, plus=0.4)],
                   branches=[dict(name="War Drum", cost=220, buff=0.35, rng=1.9, plus=0.4, haste=0.25,
                                  desc="+25% attack speed as well"),
                             dict(name="Gilded Shrine", cost=200, buff=0.3, rng=1.9, plus=0.4, gold=20,
                                  desc="+20 gold at every wave")]),
}
ORDER = ["bolt", "mortar", "frost", "storm", "harpoon", "venom", "beacon"]
TARGETS = ["first", "last", "strong", "close"]
ROMAN = ["", "I", "II", "III"]


def tstats(kind, level, branch):
    T = TOWERS[kind]
    s = dict(T["levels"][min(level, 3) - 1])
    if branch is not None:
        s.update(T["branches"][branch])
    s.pop("cost", None)
    return s


def next_cost(kind, level, branch, which=0):
    T = TOWERS[kind]
    if branch is not None:
        return None
    if level < 3:
        return T["levels"][level]["cost"]
    return T["branches"][which]["cost"]


# =============================================================================================
# The Hollow host
# =============================================================================================
ENEMIES = {
    "scuttler": dict(name="Scuttler", hp=32, spd=1.0, bounty=3, cost=1.0, size=0.74),
    "dart": dict(name="Dartling", hp=22, spd=1.9, bounty=3, cost=1.0, size=0.68, tag="fast"),
    "shell": dict(name="Shellback", hp=64, spd=0.72, armor=5, bounty=6, cost=2.4, size=0.82, tag="armour"),
    "wisp": dict(name="Wisp", hp=30, spd=1.2, fly=True, bounty=5, cost=1.6, size=0.72, tag="air"),
    "lump": dict(name="Mirelump", hp=60, spd=0.8, bounty=4, cost=2.6, size=0.84, split=("mirelet", 2), tag="splits"),
    "mirelet": dict(name="Mirelet", hp=20, spd=1.35, bounty=2, cost=0.8, size=0.56),
    "mend": dict(name="Mender", hp=48, spd=0.85, bounty=7, cost=3.0, size=0.76, heal=0.1, tag="heals"),
    "ward": dict(name="Bulwark", hp=50, shield=50, spd=0.85, bounty=7, cost=3.0, size=0.8, tag="shield"),
    "brute": dict(name="Gravelhorn", hp=230, spd=0.55, armor=3, lives=2, bounty=18, cost=7.0, size=0.96, tag="heavy"),
    "crow": dict(name="Gale Crow", hp=36, spd=2.0, fly=True, bounty=7, cost=2.5, size=0.74, tag="air"),
    "ironhide": dict(name="IRONHIDE", hp=1600, spd=0.38, armor=10, lives=10, bounty=150, cost=40, size=1.4, boss=True),
    "brood": dict(name="THE BROODMOTHER", hp=1150, spd=0.42, lives=10, bounty=150, cost=40, size=1.4, boss=True,
                  spawn=("scuttler", 2.6)),
    "thunder": dict(name="THUNDERWING", hp=1000, shield=450, spd=0.55, fly=True, lives=10, bounty=150, cost=40,
                    size=1.45, boss=True),
    "king": dict(name="THE HOLLOW KING", hp=3000, shield=700, armor=6, spd=0.33, lives=20, bounty=400, cost=80,
                 size=1.55, boss=True, heal=0.04, spawn=("ward", 4.0)),
}
ALL_POOL = ["scuttler", "dart", "shell", "wisp", "lump", "mend", "ward", "crow", "brute"]

# =============================================================================================
# The eight lands
# =============================================================================================
MAPS = [
    dict(name="HOLLYBROOK VALE", theme="meadow", kind="path", waves=14, gold=220, lives=20, diff=0.8,
         paths=[[(0, 1), (6, 1), (6, 7), (13, 7), (13, 2), (20, 2), (20, 10), (12, 10), (12, 12), (21, 12)]],
         exit=(21, 12), blocks=[("water", 2, 9, 3, 2)], props=11,
         pool=["scuttler", "dart", "shell", "wisp"], mini=[("brute", 1)], boss=[("brute", 3)],
         story="The first portal opened in the meadow."),
    dict(name="SALTMARSH REACH", theme="marsh", kind="path", waves=16, gold=230, lives=20, diff=0.9,
         paths=[[(0, 2), (9, 2), (9, 6), (16, 6), (16, 11), (22, 11)], [(3, 13), (3, 9), (12, 9), (12, 6)]],
         exit=(22, 11), blocks=[("water", 18, 2, 4, 3), ("water", 0, 5, 3, 2), ("water", 6, 11, 4, 2)], props=10,
         pool=["scuttler", "dart", "lump", "wisp", "mend", "shell"], mini=[("brute", 1)], boss=[("brood", 1)],
         story="Two causeways cross the reeds."),
    dict(name="EMBER CANYON", theme="canyon", kind="path", waves=18, gold=240, lives=20, diff=1.0,
         paths=[[(0, 12), (4, 12), (4, 2), (9, 2), (9, 11), (14, 11), (14, 2), (19, 2), (19, 11), (22, 11)]],
         exit=(22, 11), blocks=[("lava", 6, 5, 2, 3), ("lava", 16, 6, 2, 3), ("lava", 21, 2, 2, 3)], props=12,
         pool=["scuttler", "dart", "shell", "ward", "crow", "brute"], mini=[("brute", 2)], boss=[("ironhide", 1)],
         story="A long road winds through hot stone."),
    dict(name="LANTERN MARKET", theme="market", kind="maze", waves=18, gold=280, lives=20, diff=0.95,
         spawns=[(0, 7)], exit=(23, 7),
         blocks=[("wall", 0, 0, 24, 1), ("wall", 0, 13, 24, 1), ("wall", 4, 1, 3, 2), ("wall", 4, 11, 3, 2),
                 ("wall", 16, 1, 3, 2), ("wall", 16, 11, 3, 2), ("water", 11, 6, 2, 2)], props=0,
         pool=["scuttler", "dart", "lump", "mend", "ward", "shell", "wisp"], mini=[("brute", 2)], boss=[("brood", 1)],
         story="An open square: your towers make the road."),
    dict(name="FROSTPINE PASS", theme="frost", kind="path", waves=20, gold=250, lives=20, diff=0.98,
         paths=[[(2, 0), (2, 4), (8, 4), (8, 7), (15, 7), (15, 3), (21, 3), (21, 12)], [(2, 13), (2, 10), (11, 10), (11, 7)]],
         exit=(21, 12), blocks=[("ice", 17, 8, 3, 3)], props=13,
         pool=["scuttler", "dart", "shell", "crow", "ward", "mend", "brute"], mini=[("brute", 2)],
         boss=[("ironhide", 1), ("brood", 1)], story="Two trails meet below the pines."),
    dict(name="MOSSLIGHT RUINS", theme="ruins", kind="maze", waves=20, gold=300, lives=20, diff=1.3,
         spawns=[(0, 3), (0, 10)], exit=(23, 7),
         blocks=[("wall", 7, 0, 1, 5), ("wall", 7, 9, 1, 5), ("wall", 15, 3, 1, 8), ("wall", 19, 0, 1, 3),
                 ("wall", 19, 11, 1, 3)], props=6,
         pool=["scuttler", "lump", "dart", "ward", "wisp", "mend", "shell", "crow", "brute"], mini=[("brute", 3)],
         boss=[("thunder", 1)], story="Old walls, two gates, wide halls."),
    dict(name="CLOCKWORK YARD", theme="clock", kind="path", waves=22, gold=270, lives=20, diff=1.1,
         paths=[[(0, 7), (12, 7), (18, 7), (18, 11), (22, 11)], [(5, 0), (5, 4), (12, 4), (12, 7)],
                [(5, 13), (5, 10), (12, 10), (12, 7)]],
         exit=(22, 11), blocks=[("wall", 15, 1, 3, 3), ("wall", 20, 4, 2, 2)], props=10,
         pool=["scuttler", "dart", "shell", "ward", "crow", "lump", "mend", "wisp", "brute"], mini=[("brute", 3)],
         boss=[("ironhide", 1), ("thunder", 1)], story="Three tracks run into one."),
    dict(name="STARFALL CRATER", theme="crater", kind="maze", waves=25, gold=340, lives=20, diff=1.65,
         spawns=[(0, 2), (0, 11), (10, 0)], exit=(19, 7),
         blocks=[("wall", 16, 3, 6, 1), ("wall", 16, 11, 6, 1), ("wall", 22, 3, 1, 9), ("wall", 16, 4, 1, 5)], props=8,
         pool=["scuttler", "dart", "ward", "wisp", "lump", "shell", "mend", "crow", "brute"], mini=[("brute", 3)],
         boss=[("king", 1)], story="The Hollow King walks out of the fallen star."),
]

GRASS, PATH, FIELD, WATER, LAVA, PROP, WALL, SPAWN, EXIT = range(9)
WALKABLE = (PATH, FIELD, SPAWN, EXIT)


def seg_tiles(path):
    """The tiles of a road given as axis-aligned waypoints, in walking order."""
    out = [path[0]]
    for (x0, y0), (x1, y1) in zip(path, path[1:]):
        dx, dy = (x1 > x0) - (x1 < x0), (y1 > y0) - (y1 < y0)
        x, y = x0, y0
        while (x, y) != (x1, y1):
            x, y = x + dx, y + dy
            out.append((x, y))
    return out


def build_grid(mi):
    """(tiles, spawns, exit) of a land: a flat list GW*GH of tile codes."""
    m = MAPS[mi]
    maze = m["kind"] == "maze"
    g = [FIELD if maze else GRASS] * (GW * GH)
    if maze:
        spawns = list(m["spawns"])
    else:
        spawns = [p[0] for p in m["paths"]]
        for p in m["paths"]:
            for x, y in seg_tiles(p):
                g[y * GW + x] = PATH
    for kind, bx, by, bw, bh in m["blocks"]:
        code = {"water": WATER, "ice": WATER, "lava": LAVA, "wall": WALL}[kind]
        for y in range(by, by + bh):
            for x in range(bx, bx + bw):
                if g[y * GW + x] in (GRASS, FIELD):
                    g[y * GW + x] = code
    for x, y in spawns:
        g[y * GW + x] = SPAWN
    ex, ey = m["exit"]
    g[ey * GW + ex] = EXIT
    rnd = random.Random(mi * 31 + 7)
    n, tries = m["props"], 0
    while n > 0 and tries < 4000:
        tries += 1
        x, y = rnd.randrange(GW), rnd.randrange(GH)
        if g[y * GW + x] not in (GRASS, FIELD):
            continue
        near = [g[yy * GW + xx] for yy in range(max(0, y - 1), min(GH, y + 2)) for xx in range(max(0, x - 1), min(GW, x + 2))]
        if any(c in (PATH, SPAWN, EXIT, PROP) for c in near):
            continue
        if maze:
            g2 = g[:]
            g2[y * GW + x] = PROP
            if not all(bfs(g2, (ex, ey))[sy * GW + sx] < INF for sx, sy in spawns):
                continue
        g[y * GW + x] = PROP
        n -= 1
    return g, spawns, (ex, ey)


def bfs(tiles, exit_, blocked=None):
    """Distance (in tiles) to the exit over walkable tiles; blocked: a set of extra blocked indexes."""
    dist = [INF] * (GW * GH)
    ex, ey = exit_
    start = ey * GW + ex
    dist[start] = 0
    q = [start]
    for i in q:
        d = dist[i] + 1
        x, y = i % GW, i // GW
        for j in ((i - 1) if x > 0 else -1, (i + 1) if x < GW - 1 else -1, (i - GW) if y > 0 else -1,
                  (i + GW) if y < GH - 1 else -1):
            if j >= 0 and dist[j] == INF and tiles[j] in WALKABLE and not (blocked and j in blocked):
                dist[j] = d
                q.append(j)
    return dist


NB4 = ((1, 0), (0, 1), (-1, 0), (0, -1))


def next_step(dist, x, y, dx, dy, blocked=None):
    """Where a walker on (x, y) heading (dx, dy) steps next: downhill in the distance field, straight on if it can."""
    here = dist[y * GW + x]
    best, bd = None, here
    order = ((dx, dy),) + NB4 if (dx or dy) else NB4
    for ax, ay in order:
        nx, ny = x + ax, y + ay
        if 0 <= nx < GW and 0 <= ny < GH:
            d = dist[ny * GW + nx]
            if d < bd:
                best, bd = (nx, ny), d
                if d == here - 1:
                    break
    return best


def route_from(dist, start, exit_):
    x, y = start
    out = [(x, y)]
    dx = dy = 0
    for _ in range(GW * GH):
        if (x, y) == exit_:
            return out
        n = next_step(dist, x, y, dx, dy)
        if n is None:
            return out
        dx, dy = n[0] - x, n[1] - y
        x, y = n
        out.append(n)
    return out


# =============================================================================================
# Waves: generated per land from its pool, the same every time
# =============================================================================================
def hp_mul(mi, w, endless=False):
    d = MAPS[mi]["diff"]
    k = d * (1 + 0.085 * w + 0.0045 * w * w)
    if endless and w > 20:
        k *= 1.045 ** (w - 20)
    return k


def make_wave(mi, w, endless=False):
    """A wave: list of groups (kind, count, gap seconds, spawn index or -1 for all in turn, hp multiplier)."""
    m = MAPS[mi]
    rnd = random.Random(mi * 7907 + w * 131 + (99991 if endless else 0))
    n = m["waves"]
    nsp = len(m["spawns"]) if m["kind"] == "maze" else len(m["paths"])
    hpm = hp_mul(mi, w, endless)
    if endless:
        pool = ALL_POOL if w >= 6 else m["pool"]
        unlocked = pool[:min(len(pool), 2 + w // 2)]
        newest = None
        budget = 8 + 2.7 * w + 0.07 * w * w
    else:
        pool = m["pool"]
        at = [int(i * (n - 4) / len(pool)) for i in range(len(pool))]
        unlocked = [k for k, a in zip(pool, at) if w >= a]
        newest = unlocked[-1] if at[len(unlocked) - 1] == w and w > 0 else None
        budget = (7 + 2.5 * w + 0.06 * w * w) * (0.9 + 0.1 * m["diff"])
    groups = []
    kinds = []
    if newest:
        kinds.append(newest)
    want = 1 if w < 2 else rnd.choice((1, 2, 2, 3))
    if newest and len(unlocked) > 1:
        want = max(2, want)
    weights = [1 + i for i in range(len(unlocked))]
    while len(kinds) < min(want, len(unlocked)):
        k = rnd.choices(unlocked, weights)[0]
        if k not in kinds:
            kinds.append(k)
    shares = [rnd.uniform(0.7, 1.3) for _ in kinds]
    if newest and len(kinds) > 1:
        shares[0] = sum(shares[1:]) * 0.6
    tot = sum(shares)
    for k, sh in zip(kinds, shares):
        e = ENEMIES[k]
        cnt = max(2, int(round(budget * sh / tot / e["cost"])))
        gap = clamp(0.95 / e["spd"], 0.45, 1.5)
        if rnd.random() < 0.3:
            gap *= 0.6                                      # a tight pack now and then
        groups.append((k, cnt, round(gap, 2), -1 if nsp > 1 and rnd.random() < 0.6 else rnd.randrange(nsp), hpm))
    boss_wave = (w + 1) % 10 == 0 if endless else w == n - 1
    mini_wave = ((w + 1) % 5 == 0 and not boss_wave) if endless else w == n // 2
    if mini_wave:
        for k, c in (m["mini"] if not endless else [("brute", 1 + w // 10)]):
            groups.append((k, c, 2.5, -1, hpm))
    if boss_wave:
        bosses = m["boss"] if not endless else [(("ironhide", "brood", "thunder", "king")[(w // 10) % 4], 1 + w // 40)]
        for k, c in bosses:
            bm = (d_boss(mi, w) if ENEMIES[k].get("boss") else hpm)
            groups.append((k, c, 4.0, -1, bm))
    return groups


def d_boss(mi, w):
    return MAPS[mi]["diff"] * (0.75 + 0.03 * w) * (1.06 ** max(0, w - 25))


def wave_text(groups, long=True):
    agg = {}
    for k, c, *_ in groups:
        agg[k] = agg.get(k, 0) + c
    bits = []
    for k, c in agg.items():
        e = ENEMIES[k]
        if e.get("boss"):
            bits.append(e["name"].replace("THE ", ""))
        else:
            bits.append("%d %s" % (c, e["name"] if long else e["name"][:5]))
    return ", ".join(bits)


def wave_tags(groups):
    tags = []
    for k, *_ in groups:
        t = "boss" if ENEMIES[k].get("boss") else ENEMIES[k].get("tag")
        if t and t not in tags:
            tags.append(t)
    return tags


# =============================================================================================
# Sound
# =============================================================================================
def _arp(fs, d=0.05, v=0.3, w="tri", last=0.18):
    out = [dict(w=w, f=f, d=d, v=v) for f in fs[:-1]]
    return out + [dict(w=w, f=fs[-1], d=last, v=v, vib=(6, 0.15))]


SND = Sound(GAME, {
    "build": [dict(w="tri", f=196, f2=180, d=0.06, v=0.3), dict(w="noise", f=1200, d=0.05, v=0.12, at=0),
              dict(w="tri", f=392, d=0.07, v=0.22, at=0.06)],
    "upgrade": _arp([523, 659, 784, 1047], 0.04, 0.25),
    "sell": [dict(w="tri", f=784, f2=523, d=0.1, v=0.24), dict(w="sine", f=1568, d=0.06, v=0.12, at=0.05)],
    "nope": [dict(w="square", f=180, f2=150, d=0.1, v=0.16, duty=0.3)],
    "bolt": [dict(w="noise", f=5000, f2=2000, d=0.03, v=0.08), dict(w="tri", f=880, f2=660, d=0.03, v=0.08)],
    "thump": [dict(w="tri", f=120, f2=70, d=0.12, v=0.3), dict(w="noise", f=800, d=0.05, v=0.1, at=0)],
    "boom": [dict(w="noise", f=900, f2=80, d=0.25, v=0.32), dict(w="tri", f=90, f2=45, d=0.2, v=0.3, at=0)],
    "chime": [dict(w="sine", f=1760, d=0.18, v=0.12, vib=(8, 0.01)), dict(w="sine", f=2637, d=0.12, v=0.06, at=0)],
    "zap": [dict(w="square", f=1400, f2=300, d=0.07, v=0.1, duty=0.2), dict(w="noise", f=7000, d=0.05, v=0.08, at=0)],
    "twang": [dict(w="tri", f=330, f2=220, d=0.09, v=0.2), dict(w="noise", f=3000, d=0.03, v=0.06, at=0)],
    "spit": [dict(w="noise", f=2500, f2=900, d=0.05, v=0.08), dict(w="sine", f=440, f2=300, d=0.05, v=0.06, at=0)],
    "pop": [dict(w="tri", f=660, f2=990, d=0.04, v=0.14)],
    "leak": [dict(w="saw", f=330, f2=160, d=0.22, v=0.26), dict(w="tri", f=110, d=0.2, v=0.2, at=0)],
    "wave": [dict(w="saw", f=196, d=0.18, v=0.18, r="lin"), dict(w="saw", f=294, d=0.3, v=0.18, at=0.16, r="lin")],
    "boss": [dict(w="saw", f=98, f2=147, d=0.6, v=0.25, r="lin"), dict(w="square", f=196, d=0.12, v=0.14, at=0.6),
             dict(w="square", f=196, d=0.2, v=0.14, at=0.8)],
    "bossdie": [dict(w="noise", f=1500, f2=50, d=1.0, v=0.4), dict(w="tri", f=220, f2=55, d=0.9, v=0.35, at=0)] +
               [dict(w="tri", f=f, d=0.1, v=0.28, at=0.9 + i * 0.1) for i, f in enumerate((523, 659, 784, 1047))],
    "coin": [dict(w="tri", f=1319, d=0.04, v=0.16), dict(w="tri", f=1760, d=0.08, v=0.16, at=0.04)],
    "clear": [dict(w="tri", f=f, d=0.08, v=0.3) for f in (523, 659, 784, 1047, 784, 1047)] +
             [dict(w="tri", f=1568, d=0.5, v=0.3, vib=(6, 0.2), r="lin")],
    "over": [dict(w="tri", f=440, d=0.2, v=0.34), dict(w="tri", f=392, d=0.2, v=0.34), dict(w="tri", f=349, d=0.2, v=0.34),
             dict(w="tri", f=262, f2=196, d=0.7, v=0.36, r="lin")],
    "won": [dict(w="tri", f=f, d=0.12, v=0.32) for f in (523, 659, 784, 1047, 784, 1047, 1319)] +
           [dict(w="tri", f=1568, d=0.8, v=0.34, vib=(6, 0.25), r="lin")],
    "menu": [dict(w="tri", f=660, d=0.025, v=0.2)],
    "move": [dict(w="tri", f=880, d=0.012, v=0.06)],
    "start": [dict(w="tri", f=392, d=0.06, v=0.3), dict(w="tri", f=523, d=0.06, v=0.3), dict(w="tri", f=784, d=0.16, v=0.3)],
    "pause": [dict(w="tri", f=523, f2=392, d=0.07, v=0.22)],
    "sound_on": [dict(w="tri", f=440, d=0.06, v=0.35), dict(w="tri", f=880, d=0.12, v=0.35)],
})


def help_lines():
    return ["WARDSTONE - keys", "",
            "Arrows / WASD       move the cursor (hold to glide)",
            "1 - 7               pick a tower; on free ground it is built",
            "Tab                 next tower type",
            "Space / Enter / U   build here, or upgrade the tower here",
            "B                   the second path for a level III tower",
            "X / Backspace       sell the tower here (70% back)",
            "T                   aim: first, last, strongest, closest",
            "N                   call the next wave now (bonus gold)",
            "F                   game speed x1 / x2 / x3",
            "Esc / P             pause menu (Q there: quit, M sound)", "",
            "Spire: one foe, air too    Kiln: splash, ground only",
            "Bell: slows all near it    Coil: chain lightning",
            "Harpoon: anti-air only     Briar: poison, stops healing",
            "Shrine: boosts its neighbours.  Each: 3 levels, 2 paths.",
            "Gold: bounties, a wave bonus, 4% interest (max 25).",
            "Stars: 3 for losing at most 2 lives, 2 for half kept."]


# =============================================================================================
# The pieces
# =============================================================================================
class Tower:
    __slots__ = ("kind", "x", "y", "level", "branch", "cd", "ang", "aim", "spent", "st", "kills", "flash", "buff_by")

    def __init__(self, kind, x, y):
        self.kind, self.x, self.y = kind, x, y
        self.level, self.branch = 1, None
        self.cd = 0.3
        self.ang = -math.pi / 2
        self.aim = 0
        self.spent = TOWERS[kind]["cost"]
        self.kills = 0
        self.flash = 0.0
        self.buff_by = None
        self.st = tstats(kind, 1, None)

    @property
    def title(self):
        T = TOWERS[self.kind]
        if self.branch is not None:
            return T["branches"][self.branch]["name"]
        return "%s %s" % (T["name"], ROMAN[self.level])


class Enemy:
    __slots__ = ("kind", "x", "y", "tx", "ty", "dx", "dy", "vx", "vy", "hp", "maxhp", "shield", "maxshield", "armor",
                 "spd", "fly", "sx", "sy", "ex", "ey", "flen", "p", "slow", "slow_t", "freeze_t", "stun_t", "pois",
                 "pois_t", "pois_src", "brittle", "brittle_t", "corrode", "corrode_t", "calm", "ab_t", "hit_t", "dead",
                 "seed", "rem", "lives", "bounty", "boss", "heal_fx", "size")

    def __init__(self, kind, hpm, x, y, seed):
        e = ENEMIES[kind]
        self.kind = kind
        self.x, self.y = x, y
        self.tx, self.ty = int(x), int(y)
        self.dx = self.dy = 0
        self.vx = self.vy = 0.0
        self.maxhp = self.hp = e["hp"] * hpm
        self.maxshield = self.shield = e.get("shield", 0) * hpm
        self.armor = e.get("armor", 0)
        self.spd = e["spd"]
        self.fly = e.get("fly", False)
        self.boss = e.get("boss", False)
        self.lives = e.get("lives", 1)
        self.bounty = e["bounty"]
        self.size = e["size"]
        self.slow = self.slow_t = self.freeze_t = self.stun_t = 0.0
        self.pois = self.pois_t = 0.0
        self.pois_src = None
        self.brittle = self.brittle_t = 0.0
        self.corrode = self.corrode_t = 0.0
        self.calm = 0.0
        self.ab_t = 1.5
        self.hit_t = 0.0
        self.heal_fx = 0.0
        self.dead = False
        self.seed = seed
        self.rem = 0.0
        self.sx = self.sy = self.ex = self.ey = self.flen = self.p = 0.0


class Proj:
    __slots__ = ("kind", "x", "y", "tgt", "gx", "gy", "sx", "sy", "spd", "dmg", "src", "t", "T", "dead", "vx", "vy")

    def __init__(self, kind, x, y, tgt, spd, dmg, src):
        self.kind, self.x, self.y, self.tgt, self.spd, self.dmg, self.src = kind, x, y, tgt, spd, dmg, src
        self.gx, self.gy = (tgt.x, tgt.y) if tgt else (x, y)
        self.sx, self.sy = x, y
        self.t, self.T = 0.0, 1.0
        self.dead = False
        self.vx = self.vy = 0.0


# =============================================================================================
# The game
# =============================================================================================
class Game:
    def __init__(self, mode="campaign", map_i=0, seed=None, quiet=False, demo=False):
        self.rnd = random.Random(seed)
        self.mode, self.demo = mode, demo
        self.quiet = quiet or demo
        self.endless = mode == "endless"
        self.score = 0
        self.map_i = map_i
        self.first_map = map_i
        self.hi = 0 if demo else (load_scores().get(GAME, {}).get(mode) or 0)
        self.over = self.won = self.paused = self.help = False
        self.clock = 0.0
        self.speed = 1
        self.sel = "bolt"
        self.cx, self.cy = GW // 2, GH // 2
        self.earned = {}                 # map -> stars won this run
        self.maps_done = 0
        self.total_kills = 0
        self.parts, self.floats, self.rings, self.arcs = [], [], [], []
        self.shake = 0.0
        self.start_map()

    def snd(self, name, vol=1.0, gap=0.05):
        if not self.quiet:
            SND.play(name, vol, gap * max(1, self.speed))

    # --- set-up ----------------------------------------------------------------------------------
    def start_map(self):
        m = MAPS[self.map_i]
        self.m = m
        self.maze = m["kind"] == "maze"
        self.tiles, self.spawns, self.exit = build_grid(self.map_i)
        self.towers = {}
        self.enemies, self.projs, self.burns = [], [], []
        self.gold = m["gold"] + (60 if self.endless else 0)
        self.lives = self.max_lives = m["lives"]
        self.wave = 0
        self.n_waves = None if self.endless else m["waves"]
        self.pending = []
        self.countdown = FIRST_WAIT
        self.time = 0.0
        self.state, self.state_t = "play", 0.0
        self.kills = 0
        self.leaks_wave = 0
        self.last_leak = 0
        self.wave_lost = {}
        self.stars = 0
        self.msg = None
        self.layout_v = 0
        self.cx, self.cy = GW // 2, GH // 2
        self.banner_t, self.banner = 0.0, None
        self.show_banner([m["name"], "%s - %s" % (("LAND %d OF %d" % (self.map_i + 1, len(MAPS))) if not self.endless
                                                  else "ENDLESS", "%d waves" % m["waves"] if not self.endless else
                                                  "the waves never stop"), "", m["story"],
                          "Build towers, then N calls the first wave."], 4.5, (190, 236, 170))
        self.flyline = []
        ex, ey = self.exit
        for sx, sy in self.spawns:
            self.flyline.append(((sx + 0.5, sy + 0.5), (ex + 0.5, ey + 0.5)))
        self.refield()
        self.next_groups = make_wave(self.map_i, 0, self.endless)

    def refield(self):
        self.dist = bfs(self.tiles, self.exit, self.blocked())
        self.routes = [route_from(self.dist, s, self.exit) for s in self.spawns]
        w = {}
        for r in self.routes:
            for p in r:
                w[p] = w.get(p, 0) + 1
        self.route_w = w
        self.layout_v += 1
        self.rebuff()

    def blocked(self):
        return set(self.towers) if self.maze else None

    def show_banner(self, lines, secs, col):
        self.banner, self.banner_t, self.banner_col = lines, secs, col

    def say(self, text, col=(255, 150, 120)):
        self.msg = (text, 2.2, col)

    @property
    def waves_left(self):
        return None if self.endless else self.n_waves - self.wave

    def label(self):
        return "ENDLESS" if self.endless else "LAND %d" % (self.map_i + 1)

    # --- building --------------------------------------------------------------------------------
    def can_build(self, x, y, kind=None, quiet=True):
        """(ok, why) for a new tower on (x, y)."""
        i = y * GW + x
        c = self.tiles[i]
        if i in self.towers:
            return False, "There is a tower here already."
        if c in (PATH, SPAWN, EXIT):
            return False, "Not on the road."
        if c not in (GRASS, FIELD):
            return False, "Nothing can be built there."
        if kind and TOWERS[kind]["cost"] > self.gold:
            return False, "Not enough gold (%d needed)." % TOWERS[kind]["cost"]
        if self.maze:
            for e in self.enemies:
                if not e.fly and not e.dead and (int(e.x) == x and int(e.y) == y or (e.tx, e.ty) == (x, y)):
                    return False, "A foe is standing there."
            bl = set(self.towers)
            bl.add(i)
            d = bfs(self.tiles, self.exit, bl)
            if any(d[sy * GW + sx] >= INF for sx, sy in self.spawns):
                return False, "That would block the road."
            for e in self.enemies:
                if not e.fly and not e.dead and d[e.ty * GW + e.tx] >= INF:
                    return False, "That would trap a foe."
        return True, ""

    def build(self, x, y, kind):
        ok, why = self.can_build(x, y, kind)
        if not ok:
            self.say(why)
            self.snd("nope")
            return False
        t = Tower(kind, x, y)
        self.towers[y * GW + x] = t
        self.gold -= t.spent
        if self.maze:
            self.refield()
        else:
            self.rebuff()
        self.snd("build")
        self.burst(x + 0.5, y + 0.6, 10, [(200, 190, 160), (150, 140, 120)], 2.5, 0.5, 4.0)
        return True

    def upgrade(self, t, which=0):
        c = next_cost(t.kind, t.level, t.branch, which)
        if c is None:
            self.say("This tower is fully grown.", (200, 200, 220))
            self.snd("nope")
            return False
        if c > self.gold:
            self.say("Not enough gold (%d needed)." % c)
            self.snd("nope")
            return False
        self.gold -= c
        t.spent += c
        if t.level < 3:
            t.level += 1
        else:
            t.branch = which
        self.rebuff()
        t.flash = 0.5
        self.snd("upgrade")
        self.rings.append([t.x + 0.5, t.y + 0.5, 0.2, 1.0, 0.0, 0.45, (255, 230, 150)])
        return True

    def sell(self, t):
        back = int(t.spent * SELL_BACK)
        self.gold += back
        del self.towers[t.y * GW + t.x]
        if self.maze:
            self.refield()
        else:
            self.rebuff()
        self.snd("sell")
        self.float_text(t.x + 0.5, t.y + 0.3, "+%d" % back, (255, 220, 120))
        return back

    def rebuff(self):
        beacons = [b for b in self.towers.values() if b.kind == "beacon"]
        for t in self.towers.values():
            st = tstats(t.kind, t.level, t.branch)
            t.buff_by = None
            if t.kind != "beacon":
                best = None
                for b in beacons:
                    bs = tstats("beacon", b.level, b.branch)
                    if (b.x - t.x) ** 2 + (b.y - t.y) ** 2 <= bs["rng"] ** 2 + 1e-6:
                        if best is None or bs["buff"] + bs.get("haste", 0) > best["buff"] + best.get("haste", 0):
                            best = bs
                            t.buff_by = b
                if best:
                    for k in ("dmg", "dps"):
                        if k in st:
                            st[k] *= 1 + best["buff"]
                    st["rng"] += best.get("plus", 0)
                    st["rate"] *= 1 + best.get("haste", 0)
            t.st = st

    # --- waves -----------------------------------------------------------------------------------
    def call_wave(self):
        if self.state != "play" or self.countdown is None:
            return 0
        bonus = int(self.countdown * 1.2) if self.wave > 0 else 0
        if bonus:
            self.gold += bonus
            self.score += bonus * 10
            self.float_text(self.exit[0] + 0.5, self.exit[1] - 0.2, "+%d early" % bonus, (255, 220, 120))
        self.start_wave()
        return bonus

    def start_wave(self):
        groups = self.next_groups
        w = self.wave
        self.wave += 1
        self.countdown = None
        self.leaks_wave = 0
        gild = sum(tstats("beacon", b.level, b.branch).get("gold", 0) for b in self.towers.values() if b.kind == "beacon")
        interest = min(INTEREST_CAP + gild // 2, int(self.gold * INTEREST))
        bonus = int(15 + 3 * w) + gild
        self.gold += interest + bonus
        if interest + bonus and w > 0:
            self.float_text(self.exit[0] + 0.5, self.exit[1] - 0.8, "+%d" % (interest + bonus), (255, 220, 120))
        t = self.time + 0.5
        nsp = len(self.spawns)
        turn = 0
        for kind, cnt, gap, sp, hpm in groups:
            for j in range(cnt):
                s = sp if sp >= 0 else (turn % nsp)
                turn += 1
                self.pending.append((t, kind, s, hpm))
                t += gap
            t += 1.2
        self.pending.sort(key=lambda p: p[0])
        boss = [ENEMIES[k]["name"] for k, *_ in groups if ENEMIES[k].get("boss")]
        last = self.n_waves is not None and self.wave == self.n_waves
        self.show_banner(["WAVE %d%s" % (self.wave, (" OF %d" % self.n_waves) if self.n_waves else "")] +
                         ([boss[0]] if boss else ["FINAL WAVE"] if last else []), 1.8,
                         (255, 120, 110) if boss else (240, 220, 150))
        self.snd("boss" if boss else "wave")
        if self.n_waves is None or self.wave < self.n_waves:
            self.next_groups = make_wave(self.map_i, self.wave, self.endless)
        else:
            self.next_groups = None

    def spawn(self, kind, s, hpm, at=None):
        sx, sy = self.spawns[s] if at is None else (int(at.x), int(at.y))
        e = Enemy(kind, hpm, sx + 0.5, sy + 0.5, self.rnd.randrange(1 << 16))
        if at is not None:
            e.x, e.y, e.tx, e.ty, e.dx, e.dy = at.x, at.y, at.tx, at.ty, at.dx, at.dy
            e.x += self.rnd.uniform(-0.12, 0.12)
            e.y += self.rnd.uniform(-0.12, 0.12)
        if e.fly:
            ex, ey = self.exit[0] + 0.5, self.exit[1] + 0.5
            e.sx, e.sy, e.ex, e.ey = e.x, e.y, ex, ey
            e.flen = max(0.1, math.hypot(ex - e.x, ey - e.y))
            e.rem = e.flen
        else:
            e.rem = self.dist[e.ty * GW + e.tx] + 0.5
        self.enemies.append(e)
        return e

    # --- the main step ---------------------------------------------------------------------------
    def step(self, dt=DT):
        self.clock += dt
        self.fx_step(dt)
        if self.banner_t > 0:
            self.banner_t -= dt
        if self.msg:
            t = self.msg[1] - dt
            self.msg = (self.msg[0], t, self.msg[2]) if t > 0 else None
        if self.state != "play":
            self.state_t += dt
            return
        self.time += dt
        if self.countdown is not None:
            self.countdown -= dt
            if self.countdown <= 0:
                self.start_wave()
        while self.pending and self.pending[0][0] <= self.time:
            _, kind, s, hpm = self.pending.pop(0)
            self.spawn(kind, s, hpm)
        if not self.pending and self.countdown is None and self.next_groups is not None:
            self.countdown = WAVE_GAP
        for e in self.enemies:
            if not e.dead:
                self.enemy_step(e, dt)
        for t in self.towers.values():
            if t.flash > 0:
                t.flash -= dt
            if t.kind != "beacon":
                t.cd -= dt
                if t.cd <= 0:
                    self.fire(t)
        for p in self.projs:
            self.proj_step(p, dt)
        if self.projs:
            self.projs = [p for p in self.projs if not p.dead]
        if self.burns:
            for b in self.burns:
                b[3] -= dt
                r2 = b[2] * b[2]
                for e in self.enemies:
                    if not e.dead and not e.fly and (e.x - b[0]) ** 2 + (e.y - b[1]) ** 2 < r2:
                        self.hurt(e, b[4] * dt, "magic", None)
            self.burns = [b for b in self.burns if b[3] > 0]
        if any(e.dead for e in self.enemies):
            self.enemies = [e for e in self.enemies if not e.dead]
        if self.lives <= 0:
            self.lives = 0
            self.state, self.state_t = "lost", 0.0
            self.over = True
            self.snd("over")
        elif self.n_waves is not None and self.wave >= self.n_waves and not self.pending and not self.enemies:
            self.finish_map()

    def finish_map(self):
        self.state, self.state_t = "clear", 0.0
        lost = self.max_lives - self.lives
        self.stars = 3 if lost <= 2 else 2 if self.lives * 2 >= self.max_lives else 1
        bonus = self.lives * 100 + self.stars * 1000
        self.score += bonus
        self.tally = bonus
        self.earned[self.map_i] = max(self.earned.get(self.map_i, 0), self.stars)
        self.maps_done += 1
        self.snd("clear")

    def next_map(self):
        """After a cleared land: on to the next one (campaign) or the end."""
        if self.mode != "campaign" or self.map_i + 1 >= len(MAPS):
            self.won = True
            self.over = True
            self.state = "won"
            self.snd("won")
            return False
        self.map_i += 1
        self.parts, self.floats, self.rings, self.arcs = [], [], [], []
        self.start_map()
        return True

    # --- foes ------------------------------------------------------------------------------------
    def enemy_step(self, e, dt):
        if e.hit_t > 0:
            e.hit_t -= dt
        if e.heal_fx > 0:
            e.heal_fx -= dt
        e.calm += dt
        if e.maxshield and e.calm > 3.0 and e.shield < e.maxshield:
            e.shield = min(e.maxshield, e.shield + e.maxshield * 0.2 * dt)
        if e.slow_t > 0:
            e.slow_t -= dt
            if e.slow_t <= 0:
                e.slow = 0.0
        if e.brittle_t > 0:
            e.brittle_t -= dt
        if e.corrode_t > 0:
            e.corrode_t -= dt
            if e.corrode_t <= 0:
                e.corrode = 0
        if e.pois_t > 0:
            e.pois_t -= dt
            self.hurt(e, e.pois * dt, "poison", e.pois_src)
            if e.dead:
                return
        info = ENEMIES[e.kind]
        if "heal" in info or "spawn" in info:
            e.ab_t -= dt
            if e.ab_t <= 0:
                if "heal" in info:
                    e.ab_t = 2.5
                    e.heal_fx = 0.5
                    for o in self.enemies:
                        if not o.dead and o.pois_t <= 0 and (o.x - e.x) ** 2 + (o.y - e.y) ** 2 < 3.2 and o.hp < o.maxhp:
                            o.hp = min(o.maxhp, o.hp + o.maxhp * info["heal"])
                    self.rings.append([e.x, e.y, 0.3, 1.8, 0.0, 0.5, (120, 255, 150)])
                if "spawn" in info and not e.fly:
                    kind, every = info["spawn"]
                    e.ab_t = every
                    c = self.spawn(kind, 0, hp_mul(self.map_i, self.wave, self.endless) * 0.8, at=e)
                    c.tx, c.ty = e.tx, e.ty
        if e.freeze_t > 0:
            e.freeze_t -= dt
            e.vx = e.vy = 0.0
            return
        if e.stun_t > 0:
            e.stun_t -= dt
            e.vx = e.vy = 0.0
            return
        slow = e.slow * (0.5 if e.boss else 1.0) if e.slow_t > 0 else 0.0
        go = e.spd * (1 - slow) * dt
        ox, oy = e.x, e.y
        if e.fly:
            e.p += go
            k = e.p / e.flen
            if k >= 1:
                self.leak(e)
                return
            ux, uy = (e.ex - e.sx) / e.flen, (e.ey - e.sy) / e.flen
            wob = math.sin(e.p * 1.7 + e.seed) * 0.35 * math.sin(math.pi * k)
            e.x = e.sx + (e.ex - e.sx) * k - uy * wob
            e.y = e.sy + (e.ey - e.sy) * k + ux * wob
            e.rem = e.flen - e.p
        else:
            dist = self.dist
            while go > 1e-9:
                cx, cy = e.tx + 0.5, e.ty + 0.5
                ddx, ddy = cx - e.x, cy - e.y
                d = math.hypot(ddx, ddy)
                if d <= go:
                    e.x, e.y = cx, cy
                    go -= d
                    if (e.tx, e.ty) == self.exit:
                        self.leak(e)
                        return
                    n = next_step(dist, e.tx, e.ty, e.dx, e.dy)
                    if n is None:
                        break
                    e.dx, e.dy = n[0] - e.tx, n[1] - e.ty
                    e.tx, e.ty = n
                else:
                    e.x += ddx / d * go
                    e.y += ddy / d * go
                    go = 0
            e.rem = dist[e.ty * GW + e.tx] + abs(e.tx + 0.5 - e.x) + abs(e.ty + 0.5 - e.y)
        if dt > 0:
            e.vx, e.vy = (e.x - ox) / dt, (e.y - oy) / dt

    def leak(self, e):
        e.dead = True
        self.lives -= e.lives
        self.leaks_wave += e.lives
        self.last_leak = self.time
        self.wave_lost[self.wave] = self.wave_lost.get(self.wave, 0) + e.lives
        self.shake = 0.35
        self.snd("leak")
        ex, ey = self.exit
        self.rings.append([ex + 0.5, ey + 0.5, 0.2, 1.6, 0.0, 0.5, (255, 90, 90)])
        self.float_text(ex + 0.5, ey - 0.3, "-%d" % e.lives, (255, 110, 100))

    def hurt(self, e, dmg, kind="phys", src=None, strip=False, bossx=1.0):
        if e.dead or dmg <= 0:
            return
        if e.brittle_t > 0:
            dmg *= 1 + e.brittle
        if e.boss:
            dmg *= bossx
        if kind == "phys":
            arm = max(0.0, e.armor - e.corrode)
            dmg = max(dmg * 0.25, dmg - arm)
        elif kind == "shell":
            arm = max(0.0, e.armor - e.corrode) * 0.5
            dmg = max(dmg * 0.35, dmg - arm)
        if kind != "poison":
            e.calm = 0.0
            e.hit_t = 0.07
        if e.shield > 0:
            k = 2.0 if strip else 1.0
            if dmg * k >= e.shield:
                dmg -= e.shield / k
                e.shield = 0.0
                if strip:
                    self.burst(e.x, e.y, 6, [(140, 230, 255), (220, 250, 255)], 3.0, 0.4, 0)
            else:
                e.shield -= dmg * k
                return
        e.hp -= dmg
        if e.hp <= 0:
            self.kill(e, src)

    def kill(self, e, src):
        e.dead = True
        info = ENEMIES[e.kind]
        bounty = int(e.bounty * (1 + 0.06 * self.wave) + 0.5)
        self.gold += bounty
        self.score += bounty * 10
        self.kills += 1
        self.total_kills += 1
        if src is not None:
            src.kills += 1
        pal = ENEMY_PAL[e.kind]
        if e.boss:
            self.snd("bossdie")
            self.shake = 0.6
            self.burst(e.x, e.y, 40, [pal["m"], pal["b"], WHITE], 5.0, 1.2, 2.0)
            self.rings.append([e.x, e.y, 0.3, 3.0, 0.0, 0.8, (255, 230, 160)])
            self.float_text(e.x, e.y - 0.8, "+%d" % e.bounty, (255, 220, 120))
        else:
            self.snd("pop", 0.6, 0.06)
            self.burst(e.x, e.y, 6 if self.speed == 1 else 3, [pal["m"], pal["l"]], 2.6, 0.45, 3.0)
        if "split" in info:
            kind, n = info["split"]
            for _ in range(n):
                self.spawn(kind, 0, e.maxhp / info["hp"], at=e)
        if e.pois_t > 0 and e.pois_src is not None and e.pois_src.st.get("spread"):
            r2 = e.pois_src.st["spread"] ** 2
            for o in self.enemies:
                if not o.dead and not o.fly and (o.x - e.x) ** 2 + (o.y - e.y) ** 2 < r2:
                    o.pois = max(o.pois if o.pois_t > 0 else 0, e.pois)
                    o.pois_t = max(o.pois_t, 3.0)
                    o.pois_src = e.pois_src
            self.rings.append([e.x, e.y, 0.2, e.pois_src.st["spread"], 0.0, 0.4, (170, 240, 90)])

    # --- towers ----------------------------------------------------------------------------------
    def in_range(self, t, rng, air, ground):
        cx, cy = t.x + 0.5, t.y + 0.5
        r2 = rng * rng
        out = []
        for e in self.enemies:
            if e.dead or (e.fly and not air) or (not e.fly and not ground):
                continue
            if (e.x - cx) ** 2 + (e.y - cy) ** 2 <= r2:
                out.append(e)
        return out

    def pick(self, t, cands):
        a = t.aim
        if a == 0:
            return min(cands, key=lambda e: e.rem)
        if a == 1:
            return max(cands, key=lambda e: e.rem)
        if a == 2:
            return max(cands, key=lambda e: e.hp + e.shield)
        cx, cy = t.x + 0.5, t.y + 0.5
        return min(cands, key=lambda e: (e.x - cx) ** 2 + (e.y - cy) ** 2)

    def fire(self, t):
        st = t.st
        T = TOWERS[t.kind]
        k = t.kind
        cands = self.in_range(t, st["rng"], T["air"], T["ground"])
        if not cands:
            t.cd = 0.1
            return
        t.cd += 1.0 / st["rate"]
        if t.cd < 0:
            t.cd = 0.0
        cx, cy = t.x + 0.5, t.y + 0.5
        if k == "frost":
            for e in cands:
                e.slow = max(e.slow if e.slow_t > 0 else 0.0, st["slow"])
                e.slow_t = 1.6
                if st.get("brittle"):
                    e.brittle, e.brittle_t = st["brittle"], 1.6
                if st.get("freeze") and not e.boss and self.rnd.random() < st["freeze"]:
                    e.freeze_t = 1.0
                self.hurt(e, st["dmg"], "magic", t)
            t.flash = 0.25
            self.rings.append([cx, cy, 0.3, st["rng"], 0.0, 0.45, (170, 225, 255)])
            self.snd("chime", 0.5, 0.15)
            return
        tgt = self.pick(t, cands)
        t.ang = math.atan2(tgt.y - cy, tgt.x - cx)
        if k == "storm":
            hit = [tgt]
            dmg = st["dmg"]
            pts = [(cx, cy - 0.3), (tgt.x, tgt.y)]
            self.hurt(tgt, dmg, "magic", t, strip=st.get("strip", False))
            last = tgt
            for _ in range(st["jumps"] - 1):
                best, bd = None, 2.6
                for e in self.enemies:
                    if e.dead or e in hit:
                        continue
                    d = (e.x - last.x) ** 2 + (e.y - last.y) ** 2
                    if d < bd:
                        best, bd = e, d
                if best is None:
                    break
                dmg *= 0.88
                hit.append(best)
                pts.append((best.x, best.y))
                self.hurt(best, dmg, "magic", t, strip=st.get("strip", False))
                last = best
            self.arcs.append([pts, 0.0, 0.2, self.rnd.randrange(1 << 16)])
            t.flash = 0.2
            self.snd("zap", 0.6, 0.08)
            return
        if k == "venom":
            n = st.get("multi", 1)
            pool = sorted(cands, key=lambda e: (e.pois_t > 1.0, e.rem))[:n]
            for e in pool:
                p = Proj("glob", cx, cy - 0.2, e, 7.5, st["dps"], t)
                self.projs.append(p)
            self.snd("spit", 0.5, 0.1)
            return
        if k == "mortar":
            T_ = 0.65 + 0.07 * math.hypot(tgt.x - cx, tgt.y - cy)
            gx = tgt.x + tgt.vx * T_ * 0.85
            gy = tgt.y + tgt.vy * T_ * 0.85
            p = Proj("shell", cx, cy - 0.2, None, 0, st["dmg"], t)
            p.gx, p.gy, p.T = clamp(gx, 0, GW), clamp(gy, 0, GH), T_
            self.projs.append(p)
            t.flash = 0.25
            self.burst(cx, cy - 0.3, 3, [(120, 110, 100), (90, 84, 80)], 1.0, 0.6, -1.0)
            self.snd("thump", 0.6, 0.1)
            return
        if k == "bolt":
            n = st.get("multi", 1)
            tg = [tgt] + [e for e in sorted(cands, key=lambda e: e.rem) if e is not tgt][:n - 1]
            for e in tg:
                dmg = st["dmg"]
                if st.get("crit") and self.rnd.random() < st["crit"]:
                    dmg *= 2
                self.projs.append(Proj("bolt", cx, cy - 0.25, e, 13.0, dmg, t))
            self.snd("bolt", 0.4, 0.07)
            return
        if k == "harpoon":
            self.projs.append(Proj("spear", cx, cy - 0.15, tgt, 15.0, st["dmg"], t))
            self.snd("twang", 0.5, 0.1)
            return

    def proj_step(self, p, dt):
        if p.kind == "shell":
            p.t += dt
            k = p.t / p.T
            p.x = p.sx + (p.gx - p.sx) * k
            p.y = p.sy + (p.gy - p.sy) * k
            if k >= 1:
                p.dead = True
                st = p.src.st
                r = st["splash"]
                for e in self.enemies:
                    if not e.dead and not e.fly and (e.x - p.gx) ** 2 + (e.y - p.gy) ** 2 < r * r:
                        self.hurt(e, p.dmg, "shell", p.src)
                        if st.get("stun"):
                            e.stun_t = max(e.stun_t, st["stun"] * (0.4 if e.boss else 1.0))
                if st.get("burn"):
                    self.burns.append([p.gx, p.gy, r * 0.8, 3.0, st["burn"]])
                self.boom(p.gx, p.gy, r)
            return
        e = p.tgt
        if e is not None and not e.dead:
            p.gx, p.gy = e.x, e.y
        dx, dy = p.gx - p.x, p.gy - p.y
        d = math.hypot(dx, dy)
        go = p.spd * dt
        if d > 1e-6:
            p.vx, p.vy = dx / d, dy / d
        if d <= go + 0.1:
            p.dead = True
            if e is None or e.dead:
                return
            st = p.src.st
            if p.kind == "glob":
                e.pois = max(e.pois if e.pois_t > 0 else 0.0, p.dmg)
                e.pois_t = st["dur"]
                e.pois_src = p.src
                if st.get("corrode"):
                    e.corrode, e.corrode_t = st["corrode"], st["dur"]
                self.burst(e.x, e.y, 3, [(150, 230, 80), (200, 120, 220)], 1.2, 0.3, 0)
            elif p.kind == "spear" and st.get("splash"):
                r2 = st["splash"] ** 2
                for o in self.enemies:
                    if not o.dead and o.fly and (o.x - e.x) ** 2 + (o.y - e.y) ** 2 < r2:
                        self.hurt(o, p.dmg * (1.0 if o is e else 0.6), "phys", p.src)
                self.burst(e.x, e.y, 8, [(255, 200, 120), (255, 240, 200)], 3.0, 0.35, 0)
            else:
                self.hurt(e, p.dmg, "phys", p.src, bossx=st.get("boss", 1.0))
                self.burst(e.x, e.y, 2, [(255, 240, 200)], 1.5, 0.2, 0)
        else:
            p.x += dx / d * go
            p.y += dy / d * go

    # --- effects ---------------------------------------------------------------------------------
    def burst(self, x, y, n, cols, spd=3.0, life=0.5, grav=3.0):
        if len(self.parts) > 500:
            return
        for _ in range(n):
            a = self.rnd.uniform(0, 2 * math.pi)
            v = self.rnd.uniform(0.3, 1.0) * spd
            self.parts.append([x, y, math.cos(a) * v, math.sin(a) * v - spd * 0.3, 0.0,
                               life * self.rnd.uniform(0.6, 1.2), self.rnd.choice(cols), grav])

    def boom(self, x, y, r):
        self.burst(x, y, 10 if self.speed == 1 else 5, [(255, 200, 90), (255, 120, 40), (120, 100, 90)], 3.5 * r, 0.5, 2.0)
        self.rings.append([x, y, 0.1, r, 0.0, 0.3, (255, 190, 100)])
        self.snd("boom", 0.5, 0.12)

    def float_text(self, x, y, txt, col):
        if len(self.floats) < 12:
            self.floats.append([x, y, txt, 0.0, col])

    def fx_step(self, dt):
        if self.shake > 0:
            self.shake = max(0.0, self.shake - dt)
        if self.parts:
            for p in self.parts:
                p[4] += dt
                p[0] += p[2] * dt
                p[1] += p[3] * dt
                p[3] += p[7] * dt
            self.parts = [p for p in self.parts if p[4] < p[5]]
        if self.floats:
            for f in self.floats:
                f[3] += dt
                f[1] -= dt * 0.6
            self.floats = [f for f in self.floats if f[3] < 1.3]
        if self.rings:
            for r in self.rings:
                r[4] += dt
            self.rings = [r for r in self.rings if r[4] < r[5]]
        if self.arcs:
            for a in self.arcs:
                a[1] += dt
            self.arcs = [a for a in self.arcs if a[1] < a[2]]

    # --- the player's keys -----------------------------------------------------------------------
    def tower_at(self, x, y):
        return self.towers.get(y * GW + x)

    def key(self, k):
        """One in-game key (not the shared pause / help keys). True when it was used."""
        moves = {"up": (0, -1), "w": (0, -1), "down": (0, 1), "s": (0, 1), "left": (-1, 0), "a": (-1, 0),
                 "right": (1, 0), "d": (1, 0)}
        if k in moves:
            dx, dy = moves[k]
            self.cx = clamp(self.cx + dx, 0, GW - 1)
            self.cy = clamp(self.cy + dy, 0, GH - 1)
            return True
        if self.state == "clear":
            return False
        t = self.tower_at(self.cx, self.cy)
        if k in "1234567" and len(k) == 1:
            self.sel = ORDER[int(k) - 1]
            if t is None and self.can_build(self.cx, self.cy)[0]:
                self.build(self.cx, self.cy, self.sel)
            return True
        if k == "tab":
            self.sel = ORDER[(ORDER.index(self.sel) + 1) % len(ORDER)]
            self.snd("move")
            return True
        if k in (" ", "enter", "u"):
            if t:
                self.upgrade(t, 0)
            else:
                self.build(self.cx, self.cy, self.sel)
            return True
        if k == "b":
            if t and t.level == 3 and t.branch is None:
                self.upgrade(t, 1)
            elif t:
                self.say("B picks the second path of a level III tower.", (200, 200, 220))
            return True
        if k in ("x", "backspace"):
            if t:
                self.sell(t)
            return True
        if k == "t":
            if t and t.kind not in ("frost", "beacon"):
                t.aim = (t.aim + 1) % len(TARGETS)
                self.say("Aim: %s" % TARGETS[t.aim], (200, 220, 255))
            return True
        if k == "n":
            if self.countdown is not None:
                self.call_wave()
            else:
                self.say("The wave is still marching in.", (200, 200, 220))
            return True
        if k == "f":
            self.speed = self.speed % 3 + 1
            return True
        return False


# =============================================================================================
# The autopilot: builds and upgrades from what is on the screen (the land, the road, the towers,
# the foes, the gold and the next wave's preview)
# =============================================================================================
def power(kind, st):
    """A rough damage-per-second worth of a tower (frost and shrines are valued by the bot from their neighbours)."""
    if kind == "bolt":
        return st["dmg"] * st["rate"] * st.get("multi", 1) * (1 + st.get("crit", 0))
    if kind == "mortar":
        return st["dmg"] * st["rate"] * (1.6 + st["splash"]) + st.get("burn", 0) * 0.8 + st.get("stun", 0) * 20
    if kind == "storm":
        return st["dmg"] * st["rate"] * min(st["jumps"], 4.5) * 0.85 + (10 if st.get("strip") else 0)
    if kind == "harpoon":
        return st["dmg"] * st["rate"] * (1.8 if st.get("splash") else 1.0) * st.get("boss", 1.0) ** 0.5
    if kind == "venom":
        return st["dps"] * st.get("multi", 1) * 2.0 + st.get("spread", 0) * 8 + st.get("corrode", 0) * 4
    return 0.0


BOT_BRANCH = {"bolt": 0, "mortar": 1, "frost": 1, "storm": 0, "harpoon": 0, "venom": 1, "beacon": 0}


class Bot:
    def __init__(self, g, seed=None):
        self.g = g
        self.rnd = random.Random(seed)
        self.reset()

    def reset(self):
        self.goal = None
        self.think_t = 0.0
        self.move_t = 0.0
        self.cov = {}
        self.cov_v = None
        self.wait = None

    # --- what the bot sees -------------------------------------------------------------------------
    def coverage(self, r, air=False):
        """For every tile: how much of the road (or of the flight lines) a tower there with range r reaches."""
        g = self.g
        if self.cov_v != g.layout_v:
            self.cov, self.cov_v = {}, g.layout_v
        key = (round(r * 4), air)
        c = self.cov.get(key)
        if c is not None:
            return c
        if air:
            pts = []
            for (sx, sy), (ex, ey) in g.flyline:
                n = int(math.hypot(ex - sx, ey - sy) * 2) + 1
                pts += [(sx + (ex - sx) * i / n, sy + (ey - sy) * i / n, 0.5) for i in range(n + 1)]
        else:
            pts = [(x + 0.5, y + 0.5, w) for (x, y), w in g.route_w.items()]
        r2 = r * r
        c = [0.0] * (GW * GH)
        for i in range(GW * GH):
            x, y = i % GW + 0.5, i // GW + 0.5
            s = 0.0
            for px, py, w in pts:
                if (px - x) ** 2 + (py - y) ** 2 <= r2:
                    s += w
            c[i] = s
        self.cov[key] = c
        return c

    def threat(self):
        """What is coming, from the foes on the field and the next wave's preview: hit points on the ground and in
        the air, and the shares of armour and of healing / shields."""
        g = self.g
        hg = ha = arm = mag = 0.0
        for e in g.enemies:
            w = (e.hp + e.shield) * (0.5 + 0.5 * e.spd)
            if e.fly:
                ha += w
            else:
                hg += w
            arm += w if e.armor >= 5 else 0
            mag += w if e.maxshield or "heal" in ENEMIES[e.kind] else 0
        for k, c, _, _, hpm in (g.next_groups or []):
            e = ENEMIES[k]
            w = (e["hp"] + e.get("shield", 0)) * hpm * c * (0.5 + 0.5 * e["spd"])
            if e.get("fly"):
                ha += w
            else:
                hg += w
            arm += w if e.get("armor", 0) >= 5 else 0
            mag += w if e.get("shield") or e.get("heal") else 0
        tot = max(1.0, hg + ha)
        return hg, ha, arm / tot, mag / tot

    @staticmethod
    def cfrac(c, cap):
        return c / (c + cap) * (1 + cap / 10.0)

    def defence(self):
        """Damage per second the towers bring to bear on the road and on the flight lines."""
        pg = pa = 0.0
        for t in self.g.towers.values():
            T = TOWERS[t.kind]
            p = power(t.kind, t.st)
            if T["ground"]:
                pg += p * self.cfrac(self.coverage(t.st["rng"])[t.y * GW + t.x], 6)
            if T["air"]:
                pa += p * self.cfrac(self.coverage(t.st["rng"], True)[t.y * GW + t.x], 3)
        return pg, pa

    def weights(self):
        hg, ha, arm, mag = self.threat()
        pg, pa = self.defence()
        wg = (hg + 150) / (pg * 18 + 250)
        wa = (ha + 30) / (pa * 18 + 250) if (ha > 0 or self.g.wave >= 3) else 0.02
        return wg, wa, arm, mag

    def value(self, kind, st, x, y, wt, skip=None):
        wg, wa, arm, mag = wt
        T = TOWERS[kind]
        i = y * GW + x
        if kind == "beacon":
            s = 0.0
            for t in self.g.towers.values():
                if t is skip or t.kind == "beacon":
                    continue
                if (t.x - x) ** 2 + (t.y - y) ** 2 <= st["rng"] ** 2 + 1e-6:
                    cur = 0.0
                    if t.buff_by is not None and t.buff_by is not skip:
                        b = tstats("beacon", t.buff_by.level, t.buff_by.branch)
                        cur = b["buff"] + b.get("haste", 0)
                    tt = TOWERS[t.kind]
                    w = (wg if tt["ground"] else 0) + (wa if tt["air"] else 0)
                    s += power(t.kind, tstats(t.kind, t.level, t.branch)) * max(0.0, st["buff"] + st.get("haste", 0) - cur) * w
            return s * 0.9 + st.get("gold", 0) * 0.5
        if kind == "frost":
            cov = self.coverage(st["rng"])[i]
            near = sum(power(t.kind, t.st) for t in self.g.towers.values() if t.kind not in ("frost", "beacon")
                       and (t.x - x) ** 2 + (t.y - y) ** 2 <= (st["rng"] + 1.8) ** 2)
            others = sum(1 for t in self.g.towers.values() if t is not skip and t.kind == "frost"
                         and (t.x - x) ** 2 + (t.y - y) ** 2 <= 9)
            v = (st["slow"] * 0.55 + st.get("brittle", 0) * 0.8 + st.get("freeze", 0)) * near * self.cfrac(cov, 6)
            return (v * (0.45 ** others) + st["dmg"] * st["rate"] * min(cov, 8) / 4) * (wg * 0.8 + wa * 0.2)
        p = power(kind, st)
        if kind in ("storm", "venom"):
            p *= 1 + arm * 0.8 + (mag * 0.8 if kind == "venom" else mag * 0.4)
        elif kind == "bolt":
            p *= 1 - arm * 0.4
        v = 0.0
        if T["ground"]:
            v += p * self.cfrac(self.coverage(st["rng"])[i], 6) * wg
        if T["air"]:
            v += p * self.cfrac(self.coverage(st["rng"], True)[i], 3) * wa
        return v

    def best_site(self, kind, wt):
        g = self.g
        st = tstats(kind, 1, None)
        cands = []
        for i in range(GW * GH):
            if g.tiles[i] in (GRASS, FIELD) and i not in g.towers:
                cands.append(i)
        if not cands:
            return None, 0.0
        x0 = [(self.value(kind, st, i % GW, i // GW, wt), i) for i in cands]
        x0.sort(reverse=True)
        if not g.maze:
            for v, i in x0[:6]:
                if g.can_build(i % GW, i // GW)[0]:
                    return i, v
            return None, 0.0
        # open ground: prefer the spots that also lengthen the road
        base = sum(len(r) for r in g.routes)
        best, bv = None, -1.0
        for v, i in x0[:22]:
            x, y = i % GW, i // GW
            ok, _ = g.can_build(x, y)
            if not ok:
                continue
            bl = set(g.towers)
            bl.add(i)
            d = bfs(g.tiles, g.exit, bl)
            ln = sum(len(route_from(d, s, g.exit)) for s in g.spawns)
            score = v * (1 + 0.06 * max(0, ln - base))
            if score > bv:
                best, bv = i, score
        return best, bv

    def options(self):
        g = self.g
        wt = self.weights()
        boss = any(ENEMIES[k].get("boss") for k, *_ in (g.next_groups or [])) or any(e.boss for e in g.enemies)
        opts = []
        n = len(g.towers)
        counts = {}
        for t in g.towers.values():
            counts[t.kind] = counts.get(t.kind, 0) + 1
        for kind in ORDER:
            if kind == "beacon" and n < 5:
                continue
            if kind == "harpoon" and wt[1] < 0.05:
                continue
            i, v = self.best_site(kind, wt)
            if i is None:
                continue
            if g.maze and n < 6 and kind == "bolt":
                v *= 1.4                    # cheap walls first
            if not counts.get(kind) and kind in ("frost", "venom", "storm", "mortar"):
                v *= 1.25
            cost = TOWERS[kind]["cost"]
            opts.append((v / cost, cost, ("build", i, kind)))
        for t in g.towers.values():
            if t.branch is not None:
                continue
            which = BOT_BRANCH[t.kind]
            if t.level < 3:
                nst = tstats(t.kind, t.level + 1, None)
            else:
                nst = tstats(t.kind, 3, which)
            cost = next_cost(t.kind, t.level, t.branch, which)
            old = self.value(t.kind, tstats(t.kind, t.level, t.branch), t.x, t.y, wt, skip=t)
            new = self.value(t.kind, nst, t.x, t.y, wt, skip=t)
            if new > old:
                opts.append(((new - old) / cost * (1.08 + 0.3 * boss), cost, ("up", t.y * GW + t.x, which)))
        opts.sort(key=lambda o: -o[0])
        return opts

    def decide(self):
        g = self.g
        opts = self.options()
        if not opts:
            return None
        best = opts[0]
        if best[1] <= g.gold:
            return best[2]
        for o in opts[1:6]:
            if o[1] <= g.gold and o[0] >= best[0] * 0.7:
                return o[2]
        self.wait = best[1]
        return None

    def __call__(self):
        g = self.g
        if g.state != "play":
            return
        if self.goal:
            act = self.goal
            gx, gy = act[1] % GW, act[1] // GW
            self.move_t -= DT
            if (g.cx, g.cy) != (gx, gy):
                if self.move_t <= 0:
                    self.move_t = 0.045
                    if g.cx != gx:
                        g.cx += 1 if gx > g.cx else -1
                    else:
                        g.cy += 1 if gy > g.cy else -1
                return
            self.goal = None
            if act[0] == "build":
                g.sel = act[2]
                if g.can_build(gx, gy, act[2])[0]:
                    g.build(gx, gy, act[2])
            else:
                t = g.towers.get(act[1])
                if t and next_cost(t.kind, t.level, t.branch, act[2]) is not None and \
                        next_cost(t.kind, t.level, t.branch, act[2]) <= g.gold:
                    g.upgrade(t, act[2])
            self.think_t = 0.15
            return
        self.think_t -= DT
        if self.think_t > 0:
            return
        self.think_t = 0.4
        if self.wait is not None and g.gold < self.wait and int(g.time * 2.5) % 5:
            act = None                          # saving up: look again now and then only
        else:
            self.wait = None
            act = self.decide()
        if act:
            self.goal = act
            return
        if g.countdown is not None and g.state == "play":
            calm = not g.enemies and not g.pending
            if g.wave == 0 and (g.gold < 50 or len(g.towers) >= 3):
                g.call_wave()
            elif calm and g.wave > 0 and g.leaks_wave == 0 and g.countdown > 1.0 and g.time - g.last_leak > 20:
                g.call_wave()


# =============================================================================================
# Drawing helpers
# =============================================================================================
def hsh(x, y, s=0):
    h = (x * 374761393 + y * 668265263 + s * 2147483647) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    return (h ^ (h >> 16)) & 0xFFFF


def blend(cv, x, y, c, a):
    if 0 <= x < cv.W and 0 <= y < cv.H:
        row = cv.px[y]
        row[x] = mix(row[x], c, a)


def disc(cv, cx, cy, rad, c, a=1.0):
    y0, y1 = int(math.floor(cy - rad)), int(math.ceil(cy + rad))
    for py in range(max(0, y0), min(cv.H, y1 + 1)):
        dy = py + 0.5 - cy
        if abs(dy) > rad:
            continue
        w = math.sqrt(rad * rad - dy * dy)
        x0, x1 = max(0, int(math.floor(cx - w + 0.5))), min(cv.W, int(math.floor(cx + w + 0.5)))
        row = cv.px[py]
        if a >= 1:
            if x1 > x0:
                row[x0:x1] = [c] * (x1 - x0)
        else:
            for px in range(x0, x1):
                row[px] = mix(row[px], c, a)


def glow(cv, cx, cy, r0, r1, c, k=0.55):
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
                a = 1.0 if d <= r0 else 1 - (d - r0) / span
                row[px] = mix(row[px], c, a * a * k)


def ring(cv, cx, cy, rad, c, a=1.0, dots=1):
    n = max(8, int(rad * 6.3))
    for j in range(0, n, dots):
        ang = j / n * 2 * math.pi
        blend(cv, int(cx + math.cos(ang) * rad), int(cy + math.sin(ang) * rad), c, a)


def shade_ellipse(cv, cx, cy, rx, ry, base, spec=True):
    """A lit body, light from the top left."""
    if rx < 0.6 or ry < 0.6:
        cv.set(int(cx), int(cy), base)
        return
    dark = mix(base, (10, 8, 16), 0.65)
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
        row = cv.px[py]
        for px in range(a, b):
            u = (px + 0.5 - cx) / rx
            nz = math.sqrt(max(0.0, 1 - u * u - v * v))
            l = u * lx + v * ly + nz * lz
            if l < 0.15:
                c = mix(dark, base, max(0.0, (l + 0.6) / 0.75))
            elif l < 0.8:
                c = mix(base, lite, (l - 0.15) / 0.65 * 0.6)
            else:
                c = mix(mix(base, lite, 0.6), WHITE, (l - 0.8) / 0.2 * (0.7 if spec else 0.15))
            row[px] = c


def layout(cols, rows, hud=True):
    """(s, ox, oy): pixels per tile and the land's top-left pixel."""
    top, bot = (1, 2) if hud else (0, 0)
    ah = (rows - top - bot) * 2
    s = min(cols / GW, ah / GH)
    if s >= 3:
        s = int(s)
    fw, fh = int(GW * s), int(GH * s)
    return s, (cols - fw) // 2, top * 2 + (ah - fh) // 2


class View:
    def __init__(self, s, ox, oy):
        self.s, self.ox, self.oy = s, ox, oy

    def X(self, x):
        return self.ox + int(math.floor(x * self.s))

    def Y(self, y):
        return self.oy + int(math.floor(y * self.s))

    def tile(self, x, y):
        x0, y0 = self.X(x), self.Y(y)
        return x0, y0, max(1, self.X(x + 1) - x0), max(1, self.Y(y + 1) - y0)


# =============================================================================================
# The lands' looks
# =============================================================================================
THEMES = {
    "meadow": dict(g0=(70, 132, 58), g1=(98, 158, 70), p0=(176, 140, 92), p1=(150, 116, 74), edge=(104, 82, 52),
                   w0=(46, 112, 168), w1=(96, 168, 214), frame=(34, 54, 30), prop="willow", accent=(190, 236, 150),
                   fleck=(240, 230, 120), mote=(250, 250, 200)),
    "marsh": dict(g0=(64, 108, 88), g1=(86, 128, 98), p0=(150, 118, 80), p1=(118, 90, 60), edge=(70, 54, 38),
                  w0=(34, 82, 96), w1=(76, 132, 140), frame=(24, 42, 40), prop="reeds", accent=(150, 220, 200),
                  fleck=(200, 210, 150), mote=(200, 255, 220)),
    "canyon": dict(g0=(168, 88, 56), g1=(196, 112, 66), p0=(214, 176, 128), p1=(190, 150, 106), edge=(120, 70, 46),
                   w0=(200, 60, 20), w1=(255, 170, 60), frame=(60, 26, 18), prop="cactus", accent=(255, 180, 110),
                   fleck=(220, 150, 90), mote=(255, 170, 80)),
    "market": dict(g0=(112, 104, 98), g1=(138, 128, 116), p0=(112, 104, 98), p1=(100, 92, 86), edge=(70, 64, 60),
                   w0=(56, 110, 150), w1=(130, 190, 220), frame=(40, 34, 40), prop="lamp", accent=(255, 214, 140),
                   fleck=(160, 150, 140), mote=(255, 220, 150)),
    "frost": dict(g0=(206, 218, 232), g1=(234, 242, 250), p0=(150, 174, 204), p1=(128, 152, 186), edge=(110, 130, 164),
                  w0=(150, 196, 228), w1=(214, 240, 255), frame=(70, 86, 110), prop="pine", accent=(190, 226, 255),
                  fleck=(255, 255, 255), mote=(255, 255, 255)),
    "ruins": dict(g0=(60, 98, 66), g1=(82, 120, 78), p0=(96, 104, 90), p1=(78, 86, 74), edge=(62, 66, 60),
                  w0=(44, 90, 100), w1=(90, 150, 150), frame=(26, 38, 30), prop="pillar", accent=(170, 230, 160),
                  fleck=(140, 200, 120), mote=(170, 255, 170)),
    "clock": dict(g0=(104, 90, 68), g1=(128, 110, 80), p0=(76, 80, 92), p1=(60, 64, 74), edge=(36, 38, 46),
                  w0=(60, 70, 90), w1=(110, 120, 140), frame=(40, 32, 24), prop="gear", accent=(255, 206, 120),
                  fleck=(180, 150, 90), mote=(255, 210, 140)),
    "crater": dict(g0=(46, 38, 72), g1=(64, 52, 92), p0=(46, 38, 72), p1=(40, 32, 62), edge=(26, 20, 44),
                   w0=(80, 50, 150), w1=(180, 140, 255), frame=(16, 12, 30), prop="crystal", accent=(210, 180, 255),
                   fleck=(150, 130, 220), mote=(220, 200, 255)),
}
STALL = [(214, 70, 60), (70, 140, 210), (230, 180, 60), (90, 170, 90), (200, 100, 180)]


def tile_code(g_tiles, x, y):
    if 0 <= x < GW and 0 <= y < GH:
        return g_tiles[y * GW + x]
    return -1


def paint_ground(cv, th, theme, tiles, v, maze):
    """Every pixel of the land: grass / floor, roads with their edges, water, lava, walls."""
    s = v.s
    fw, fh = int(GW * s), int(GH * s)
    g0, g1, p0, p1, edge = th["g0"], th["g1"], th["p0"], th["p1"], th["edge"]
    ew = max(1, int(s * 0.14 + 0.5)) if s >= 3 else 0
    for py in range(max(0, v.oy), min(cv.H, v.oy + fh)):
        row = cv.px[py]
        fy = (py - v.oy + 0.5) / s
        ty = min(GH - 1, int(fy))
        vv = fy - ty
        for px in range(max(0, v.ox), min(cv.W, v.ox + fw)):
            fx = (px - v.ox + 0.5) / s
            tx = min(GW - 1, int(fx))
            u = fx - tx
            c = tiles[ty * GW + tx]
            n = hsh(px, py, 3)
            if c in (PATH, SPAWN, EXIT) or (c == FIELD and maze):
                if c == FIELD or (maze and c in (SPAWN, EXIT)):
                    col = floor_px(theme, th, px, py, u, vv, tx, ty, s, n)
                else:
                    col = road_px(theme, th, u, vv, tx, ty, s, n)
                    if ew:
                        eu = ew / s
                        for (ax, ay), dd in (((-1, 0), u), ((1, 0), 1 - u), ((0, -1), vv), ((0, 1), 1 - vv)):
                            if dd < eu and tile_code(tiles, tx + ax, ty + ay) not in (PATH, SPAWN, EXIT, -1):
                                col = mix(edge, col, dd / eu * 0.5)
                                break
            elif c in (WATER, LAVA):
                col = water_px(theme, th, c, u, vv, tx, ty, s, n, tiles)
            elif c == WALL:
                col = wall_px(theme, th, u, vv, tx, ty, s, n, tiles)
            else:
                col = mix(g0, g1, ((tx * 7 + ty * 13) % 5) / 9 + (n % 100) / 320)
                if theme == "frost" and n % 13 == 0:
                    col = mix(col, (170, 190, 215), 0.4)
                elif n % 29 == 0:
                    col = mix(col, th["fleck"], 0.45)
                elif n % 7 == 0:
                    col = shade(col, 0.9)
                if s >= 3 and not maze:   # a soft shadow where grass meets the road
                    for (ax, ay), dd in (((-1, 0), u), ((1, 0), 1 - u), ((0, -1), vv), ((0, 1), 1 - vv)):
                        if dd < 0.12 and tile_code(tiles, tx + ax, ty + ay) == PATH:
                            col = shade(col, 0.8 + dd * 1.4)
                            break
            row[px] = col


def road_px(theme, th, u, v, tx, ty, s, n):
    p0, p1 = th["p0"], th["p1"]
    if theme == "marsh":          # boardwalk planks
        k = (u * 3 + (tx % 2) * 0.5) % 1.0 if (tx + ty) % 2 else (v * 3) % 1.0
        col = mix(p0, p1, 0.3 + 0.2 * ((n % 7) / 7))
        if k < 0.12:
            col = shade(p1, 0.7)
        return col
    if theme == "clock":          # riveted iron plates
        col = mix(p0, p1, (n % 9) / 18)
        if s >= 4 and (abs(u - 0.15) < 0.6 / s and abs(v - 0.15) < 0.6 / s or abs(u - 0.85) < 0.6 / s and abs(v - 0.85) < 0.6 / s):
            col = mix(col, (170, 170, 180), 0.6)
        if u < 0.06 or v < 0.06:
            col = shade(col, 0.75)
        return col
    if theme == "frost":
        return mix(p0, p1, (n % 13) / 26 + 0.2 * math.sin(u * 6 + tx))
    if theme == "canyon":
        col = mix(p0, p1, (n % 11) / 22)
        if n % 37 == 0:
            col = mix(col, (150, 100, 70), 0.5)
        return col
    col = mix(p0, p1, (n % 11) / 20)
    if n % 31 == 0:
        col = shade(p0, 1.15)
    elif n % 17 == 0:
        col = shade(p1, 0.85)
    return col


def floor_px(theme, th, px, py, u, v, tx, ty, s, n):
    g0, g1 = th["g0"], th["g1"]
    if theme == "market":          # cobbles
        k = 2
        cu, cv_ = (u * k + (0.5 if int(v * k) % 2 else 0)) % 1.0, (v * k) % 1.0
        col = mix(g0, g1, ((hsh(int(u * k + tx * 9 + (0.5 if int(v * k) % 2 else 0)), int(v * k) + ty * 7, 5)) % 7) / 8)
        if s >= 4 and (cu < 1.2 / s * k or cv_ < 1.2 / s * k):
            col = shade(col, 0.72)
        return col
    if theme == "ruins":           # flagstones with moss
        col = mix(th["p0"], th["p1"], ((tx * 3 + ty * 5) % 4) / 5 + (n % 9) / 40)
        if s >= 4 and (u < 0.07 or v < 0.07):
            col = mix(col, (60, 100, 60), 0.6)
        if n % 11 == 0:
            col = mix(col, (90, 140, 80), 0.5)
        return col
    col = mix(g0, g1, (n % 13) / 26 + ((tx + ty) % 3) / 10)   # crater dust
    if n % 97 == 0:
        col = mix(col, (230, 210, 255), 0.7)
    return col


def water_px(theme, th, c, u, v, tx, ty, s, n, tiles):
    if c == LAVA:
        X, Y = u + tx, v + ty
        k = math.sin(X * 3.1 + math.sin(Y * 2.3) * 1.7) + math.sin(Y * 2.7 + math.sin(X * 1.9) * 1.3)
        col = mix((150, 34, 12), (255, 168, 50), clamp(0.5 + k * 0.3, 0, 1))
        if k > 1.3:
            col = mix(col, (255, 236, 150), (k - 1.3) * 1.4)
        if k < -0.9:
            col = mix(col, (56, 26, 22), min(1.0, (-0.9 - k) * 3))
        for (ax, ay), dd in (((-1, 0), u), ((1, 0), 1 - u), ((0, -1), v), ((0, 1), 1 - v)):
            if dd < 0.1 and tile_code(tiles, tx + ax, ty + ay) not in (LAVA, -1):
                col = mix(col, (70, 30, 24), 0.7)
                break
        return col
    w0, w1 = th["w0"], th["w1"]
    if theme == "frost":
        col = mix(w0, w1, 0.4 + 0.3 * math.sin(u * 3 + v * 2 + tx))
        if abs((u + v * 0.6 + tx * 0.37) % 1.0 - 0.5) < 0.6 / max(1, s):
            col = mix(col, WHITE, 0.5)
        return col
    k = 0.5 + 0.25 * math.sin((u + tx) * 4.0 + (v + ty) * 2.0)
    col = mix(w0, w1, k * 0.6)
    if math.sin((u + tx) * 9 + (v + ty) * 3) > 0.92:
        col = mix(col, WHITE, 0.35)
    for (ax, ay), dd in (((-1, 0), u), ((1, 0), 1 - u), ((0, -1), v), ((0, 1), 1 - v)):
        if dd < 0.12 and tile_code(tiles, tx + ax, ty + ay) not in (WATER, -1):
            col = mix(col, (200, 230, 230), 0.45)
            break
    return col


def wall_px(theme, th, u, v, tx, ty, s, n, tiles):
    up = tile_code(tiles, tx, ty - 1) == WALL
    dn = tile_code(tiles, tx, ty + 1) == WALL
    if theme == "market":
        h = hsh(tx // 3, ty // 2, 4)
        awn = STALL[h % len(STALL)]
        if ty == 0 or ty == GH - 1:      # house fronts
            col = mix((110, 80, 70), (140, 100, 84), (n % 7) / 10)
            if (u * 2 % 1.0 < 0.5) and 0.25 < v < 0.75:
                col = (250, 200, 120) if (tx + ty) % 3 else (60, 50, 60)
            if v > 0.85 if ty == 0 else v < 0.15:
                col = (70, 50, 46)
            return col
        if not up or ty == 1:            # the striped awning
            col = awn if int(u * 4 + tx * 4) % 2 else (240, 230, 220)
            if v > 0.55:
                col = shade(col, 0.8)
            return col
        col = mix((120, 84, 52), (150, 110, 70), (n % 9) / 12)
        if v > 0.8 and not dn:
            col = (60, 42, 30)
        return col
    if theme == "crater":
        k = (n % 13) / 26
        col = mix((96, 80, 130), (130, 112, 166), k + 0.25 * (1 - v))
        if not up and v < 0.2:
            col = mix(col, (210, 190, 250), 0.5)
        elif not dn and v > 0.8:
            col = shade(col, 0.55)
        if (hsh(tx * 3 + int(u * 3), ty * 3 + int(v * 3), 2) % 6) == 0:
            col = mix(col, (200, 160, 255), 0.7)
        return col
    if theme == "clock":
        col = mix((150, 120, 60), (200, 160, 80), 0.5 + 0.3 * math.sin(u * 6))
        if (u * 4) % 1.0 < 0.15 or (v * 4) % 1.0 < 0.15:
            col = shade(col, 0.7)
        return col
    # ruins and the rest: mossy stone blocks
    bu = (u * 2 + (0.5 if int(v * 2) % 2 else 0)) % 1.0
    bv = (v * 2) % 1.0
    col = mix((150, 150, 138), (184, 182, 166), (hsh(int(u * 2 + tx * 5), int(v * 2) + ty * 3, 6) % 7) / 8)
    if s >= 6 and (bu < 1.0 / s * 2 or bv < 1.0 / s * 2):
        col = shade(col, 0.6)
    if not up and v < 0.22:
        col = mix(col, (110, 170, 90), 0.75)
    elif not dn and v > 0.82:
        col = shade(col, 0.5)
    elif n % 9 == 0:
        col = mix(col, (90, 140, 76), 0.5)
    return col


def paint_prop(cv, theme, th, x0, y0, w, h, seed):
    """The decoration on a blocked tile: drawn into the land picture (may overhang the tile above)."""
    cx, cy = x0 + w / 2, y0 + h / 2
    s = w
    if theme == "meadow":
        cv.rect(int(cx - s * 0.08), int(y0 + h * 0.5), max(1, int(s * 0.16)), int(h * 0.5), (92, 64, 40))
        disc(cv, cx + s * 0.05, cy + s * 0.15, s * 0.5, (30, 50, 26), 0.35)
        shade_ellipse(cv, cx, cy - s * 0.12, s * 0.55, s * 0.48, (80, 150, 60))
        for k in range(int(s * 2)):            # willow strands
            px = int(x0 + (hsh(seed, k, 1) % max(1, w)))
            for yy in range(int(cy), int(y0 + h * (0.8 + (k % 3) * 0.05))):
                blend(cv, px, yy, (110, 180, 80), 0.6)
        return
    if theme == "marsh":
        for k in range(max(2, int(s * 0.9))):
            px = x0 + (hsh(seed, k, 2) % max(1, w))
            top = y0 + int(h * (0.05 + (hsh(seed, k, 3) % 40) / 100))
            for yy in range(top, y0 + h):
                blend(cv, px, yy, mix((60, 110, 60), (150, 170, 90), (yy - top) / max(1, h)), 0.9)
            if s >= 4:
                cv.rect(px, top, 1, max(1, int(s * 0.18)), (120, 80, 50))
        return
    if theme == "canyon":
        if seed % 2:
            col = (70, 140, 80)
            cv.rect(int(cx - s * 0.12), int(y0 + h * 0.1), max(1, int(s * 0.24)), int(h * 0.85), col)
            cv.rect(int(cx - s * 0.4), int(y0 + h * 0.35), max(1, int(s * 0.16)), int(h * 0.3), col)
            cv.rect(int(cx - s * 0.4), int(y0 + h * 0.55), int(s * 0.3), max(1, int(s * 0.12)), col)
            cv.rect(int(cx + s * 0.25), int(y0 + h * 0.25), max(1, int(s * 0.16)), int(h * 0.3), col)
            cv.rect(int(cx + s * 0.1), int(y0 + h * 0.45), int(s * 0.3), max(1, int(s * 0.12)), col)
            for yy in range(int(y0 + h * 0.1), int(y0 + h * 0.95)):
                blend(cv, int(cx - s * 0.12), yy, (150, 210, 140), 0.5)
        else:
            shade_ellipse(cv, cx, cy + s * 0.1, s * 0.48, s * 0.36, (150, 96, 70))
        return
    if theme == "frost":
        for k in range(3):
            ww = s * (0.25 + 0.17 * k)
            yy = y0 - h * 0.25 + k * h * 0.3
            cv.poly([(cx, yy), (cx + ww, yy + h * 0.45), (cx - ww, yy + h * 0.45)], (36, 86, 70) if k % 2 else (46, 100, 80))
            cv.poly([(cx, yy), (cx + ww * 0.5, yy + h * 0.2), (cx - ww * 0.5, yy + h * 0.2)], (236, 244, 250))
        cv.rect(int(cx - s * 0.07), int(y0 + h * 0.75), max(1, int(s * 0.14)), int(h * 0.25), (90, 60, 40))
        return
    if theme == "ruins":
        cv.rect(int(cx - s * 0.28), int(y0 - h * 0.2), int(s * 0.56), int(h * 1.1), (130, 132, 122))
        cv.rect(int(cx - s * 0.28), int(y0 - h * 0.2), max(1, int(s * 0.12)), int(h * 1.1), (170, 172, 160))
        cv.rect(int(cx + s * 0.16), int(y0 - h * 0.2), max(1, int(s * 0.12)), int(h * 1.1), (96, 98, 90))
        cv.rect(int(cx - s * 0.38), int(y0 - h * 0.25), int(s * 0.76), max(1, int(s * 0.16)), (150, 152, 140))
        cv.rect(int(cx - s * 0.3), int(y0 + h * 0.2), int(s * 0.3), max(1, int(s * 0.12)), (90, 150, 80))
        return
    if theme == "clock":
        R = s * 0.45
        for py in range(int(cy - R - 1), int(cy + R + 2)):
            for px in range(int(cx - R - 1), int(cx + R + 2)):
                dx, dy = px + 0.5 - cx, py + 0.5 - cy
                d = math.hypot(dx, dy)
                a = math.atan2(dy, dx)
                rr = R * (0.82 + 0.18 * (math.cos(a * 8 + seed) > 0.2))
                if d < rr:
                    c = (186, 150, 70) if d > R * 0.3 else (70, 54, 30)
                    if d < R * 0.55 and d > R * 0.3:
                        c = (150, 118, 54)
                    blend(cv, px, py, mix(c, WHITE, 0.25) if dx + dy < -R * 0.4 else c, 1.0)
        return
    if theme == "crater":
        for k, (ox_, hh, ww) in enumerate(((0.0, 0.9, 0.22), (-0.25, 0.55, 0.16), (0.27, 0.65, 0.17))):
            bx = cx + ox_ * s
            top = y0 + h - hh * h - h * 0.15
            cv.poly([(bx, top), (bx + ww * s, top + hh * h * 0.35), (bx + ww * s * 0.7, y0 + h * 0.95),
                     (bx - ww * s * 0.7, y0 + h * 0.95), (bx - ww * s, top + hh * h * 0.35)], (150, 110, 240))
            cv.poly([(bx, top), (bx + ww * s * 0.1, top), (bx + ww * s * 0.15, y0 + h * 0.95),
                     (bx - ww * s * 0.7, y0 + h * 0.95), (bx - ww * s, top + hh * h * 0.35)], (210, 180, 255))
        return
    if theme == "market":
        cv.rect(int(cx), int(y0), 1, h, (50, 40, 40))
        disc(cv, cx, y0 + h * 0.2, s * 0.2, (255, 200, 110))
        return


_BG = {}


def backdrop(mi, cols, rows, hud):
    key = (mi, cols, rows, hud)
    c = _BG.get(key)
    if c is not None:
        return c
    if len(_BG) > 16:
        _BG.clear()
    m = MAPS[mi]
    theme = m["theme"]
    th = THEMES[theme]
    tiles, spawns, exit_ = build_grid(mi)
    s, ox, oy = layout(cols, rows, hud)
    v = View(s, ox, oy)
    cv = Canvas(cols, rows)
    fr = th["frame"]
    for y in range(cv.H):
        cv.px[y] = [mix(fr, (4, 4, 8), 0.4 + 0.5 * abs(y / cv.H - 0.5))] * cv.W
    for y in range(cv.H):
        for x in range(0, cv.W, 1):
            if hsh(x, y, 11) % 41 == 0:
                cv.px[y][x] = mix(cv.px[y][x], th["fleck"], 0.2)
    paint_ground(cv, th, theme, tiles, v, m["kind"] == "maze")
    for i, c in enumerate(tiles):
        if c == PROP:
            x0, y0, w, h = v.tile(i % GW, i // GW)
            paint_prop(cv, theme, th, x0, y0, w, h, hsh(i, mi, 9))
    if s >= 2:   # the land's rim: a soft dark line around it
        fw, fh = int(GW * s), int(GH * s)
        for x in range(max(0, ox - 1), min(cv.W, ox + fw + 1)):
            for y in (oy - 1, oy + fh):
                if 0 <= y < cv.H:
                    cv.px[y][x] = mix(cv.px[y][x], (0, 0, 0), 0.5)
    for sx, sy in spawns:      # the Hollow portals
        x0, y0, w, h = v.tile(sx, sy)
        cx, cy = x0 + w / 2, y0 + h / 2
        disc(cv, cx, cy, max(1.0, w * 0.48), (60, 30, 80))
        disc(cv, cx, cy, max(0.8, w * 0.36), (20, 8, 30))
    out = [row[:] for row in cv.px]
    _BG[key] = out
    return out


# =============================================================================================
# Sprites: towers (12 x 12) and foes (8 x 8, bosses 12 x 12), two frames each
# =============================================================================================
TOWER_ART = {
    "bolt": [".....oo.....", "....obco....", "....obbo....", "...obbbco...", "...obbbbo...", "..oaaaaaao..",
             "...ommlmo...", "...omkkmo...", "...omlmmo...", "...omlmmo...", "..ommlmmdo..", "..oddddddo.."],
    "mortar": ["............", "............", "....oooo....", "...ollmmo...", "..olmmmmdo..", "..omkkkkdo..",
               ".omkabbakdo.", ".omkbccbkdo.", ".ommkkkkmdo.", ".olmmmmmmdo.", "..oddddddo..", "..oooooooo.."],
    "frost": [".....oo.....", "....obbo....", "...obccbo...", "...obcbbo...", "..obcbbbbo..", "..obcbbbbo..",
              ".obcbbbbbao.", ".obbbbbbbao.", "oaaaaaaaaaao", ".ooooaaoooo.", ".....cc.....", "............"],
    "storm": ["....oooo....", "...obccbo...", "...obcbbo...", "....oaao....", "...ollmmo...", "....odmo....",
              "...ollmmo...", "....odmo....", "...ollmmo...", "....odmo....", "..ollmmmdo..", "..oddddddo.."],
    "harpoon": ["............", "............", "............", "...oooooo...", "..obbccbbo..", ".oabbbbbbao.",
                ".oaammmmaao.", "..omlllmmo..", "..omlmmmmo..", ".omlmmmmmdo.", ".oddddddddo.", "..oooooooo.."],
    "venom": [".....oo.....", "..o.obbo.o..", "..oobccboo..", "...obcbbo...", "..obbbbbao..", "..oabbbaao..",
              "...oaaaao...", "o..ommlmo..o", "lo.omlmmo.ol", ".lomlmmmmol.", "..ommmmmdo..", ".oddddddddo."],
    "beacon": [".....bb.....", "....bccb....", "....acca....", ".....aa.....", "....oooo....", "....olmo....",
               "...ollmdo...", "...olmmdo...", "...olmmdo...", "..olmmmmdo..", "..oggggggo..", ".oddddddddo."],
}
MICRO_ART = {      # the towers on small tiles (up to 5 pixels): one clear shape and colour each
    "bolt": [".cb.", "bbbb", ".lm.", "dmmd"],
    "mortar": [".mm.", "mbbm", "mccm", "dddd"],
    "frost": [".cb.", "cbbb", "bbba", ".aa."],
    "storm": [".cb.", ".ba.", ".ml.", "dmmd"],
    "harpoon": ["..cc", "bbc.", "mmml", "dddd"],
    "venom": ["b.cb", ".bb.", "lmml", ".dd."],
    "beacon": [".cb.", ".ba.", ".ml.", "gggg"],
}
TOWER_PAL = {
    "bolt": dict(d=(120, 98, 76), m=(168, 142, 106), l=(214, 192, 150), a=(40, 66, 130), b=(70, 112, 196), c=(150, 190, 240)),
    "mortar": dict(d=(86, 56, 48), m=(140, 88, 64), l=(190, 128, 90), a=(200, 70, 30), b=(250, 140, 40), c=(255, 226, 130)),
    "frost": dict(d=(100, 120, 140), m=(160, 180, 200), l=(210, 226, 240), a=(80, 150, 200), b=(150, 210, 240), c=(230, 248, 255)),
    "storm": dict(d=(100, 56, 40), m=(170, 100, 60), l=(226, 156, 104), a=(110, 60, 180), b=(170, 112, 240), c=(240, 216, 255)),
    "harpoon": dict(d=(84, 58, 38), m=(130, 94, 60), l=(176, 136, 90), a=(90, 100, 120), b=(146, 156, 176), c=(214, 224, 238)),
    "venom": dict(d=(36, 84, 40), m=(70, 132, 52), l=(126, 186, 84), a=(100, 30, 110), b=(166, 64, 176), c=(226, 150, 236)),
    "beacon": dict(d=(116, 96, 70), m=(176, 150, 102), l=(228, 206, 152), a=(220, 120, 30), b=(255, 190, 60), c=(255, 246, 196)),
}
BRANCH_ACCENT = [dict(a=(170, 60, 40), b=(230, 110, 50), c=(255, 210, 120)), dict(a=(40, 120, 150), b=(70, 190, 210), c=(200, 250, 255))]

ENEMY_ART = {
    "scuttler": [["........", "..oooo..", ".ommllo.", "omwmmmlo", "ommmmmmo", ".oddddo.", "o.o..o.o", "........"],
                 ["........", "..oooo..", ".ommllo.", "omwmmmlo", "ommmmmmo", ".oddddo.", ".o.oo.o.", "........"]],
    "dart": [["........", "......oo", ".oooooaw", "ommmmlmo", ".odddmo.", "..o..o..", "........", "........"],
             ["........", "......oo", ".oooooaw", "ommmmlmo", ".odddmo.", ".o....o.", "........", "........"]],
    "shell": [["..oooo..", ".oabbao.", "oabbbbao", "oaabbaao", "oddddddo", ".omwmmo.", ".o.oo.o.", "........"],
              ["..oooo..", ".oabbao.", "oabbbbao", "oaabbaao", "oddddddo", ".omwmmo.", "o..oo..o", "........"]],
    "wisp": [["...oo...", "..obbo..", ".obwwbo.", "obbwwbbo", ".obbbbo.", "..obbo..", ".o.oo.o.", "........"],
             ["...oo...", "..obbo..", ".obwwbo.", "obbwwbbo", ".obbbbo.", "..obbo..", "..o..o..", "...oo..."]],
    "lump": [["........", "...oo...", "..ommo..", ".omwmwo.", "ommmmmlo", "ommmmmmo", ".oddddo.", "..oooo.."],
             ["........", "........", "..oooo..", ".omwmwo.", "ommmmmlo", "ommmmmmo", "oddddddo", ".oooooo."]],
    "mend": [["...oo...", "..obbo..", "..owwo..", ".ommmmo.", "omlmmmmo", ".ommamo.", ".ommmmo.", ".oo..oo."],
             ["...oo...", "..obbo..", "..owwo..", ".ommmmo.", "omlmmmmo", ".ommamo.", ".ommmmo.", "..oooo.."]],
    "ward": [["..oooo..", ".ollmmo.", ".omkkmo.", "oaaommdo", "oabammdo", "oaaommdo", ".odddddo", ".o.o.o.."],
             ["..oooo..", ".ollmmo.", ".omkkmo.", "oaaommdo", "oabammdo", "oaaommdo", ".odddddo", "..o.o.o."]],
    "brute": [["o......o", "lo.oo.ol", ".ommmmo.", "omwmmwmo", "ommmmmmo", "olmmmmdo", ".odddddo", "oo.oo.oo"],
              ["o......o", "lo.oo.ol", ".ommmmo.", "omwmmwmo", "ommmmmmo", "olmmmmdo", ".odddddo", ".oo..oo."]],
    "crow": [["........", "o......o", "oo.oo.oo", ".oommoo.", "..omwmo.", "...oao..", "....o...", "........"],
             ["oo....oo", ".oo..oo.", "..oooo..", "..ommmo.", "..omwmo.", "...oao..", "....o...", "........"]],
    "ironhide": [["............", "..oooooooo..", ".oaabbbbaao.", "oabbccccbbao", "oabcbbbbcbao", "oaabbbbbbaao",
                  "ommwmmmmwmmo", "ommmmmmmmmmo", "olmmmmmmmmdo", ".oddddddddo.", ".oo.oo.oo.oo", "............"],
                 ["............", "..oooooooo..", ".oaabbbbaao.", "oabbccccbbao", "oabcbbbbcbao", "oaabbbbbbaao",
                  "ommwmmmmwmmo", "ommmmmmmmmmo", "olmmmmmmmmdo", ".oddddddddo.", "oo.oo.oo.oo.", "............"]],
    "brood": [["............", "o...oooo...o", ".o.ommmmo.o.", "..ommwwmmo..", "ooommmmmmooo", "..omllmmmo..",
               "ooomaaaamooo", "..oabbbbao..", ".o.oabbao.o.", "o...oaao...o", ".....oo.....", "............"],
              ["............", ".o..oooo..o.", ".o.ommmmo.o.", "..ommwwmmo..", "ooommmmmmooo", "..omllmmmo..",
               "ooomaaaamooo", "..oabbbbao..", ".o.oabbao.o.", ".o..oaao..o.", ".....oo.....", "............"]],
    "thunder": [["............", "o..........o", "oo...oo...oo", "obo.obbo.obo", "obboobboobbo", ".obbbwwbbbo.",
                 "..obbbbbbo..", "...oaccao...", "....oaao....", "....o..o....", "............", "............"],
                ["............", "............", ".....oo.....", "....obbo....", "oooobbbboooo", "obbbbwwbbbbo",
                 ".obbbbbbbbo.", "..ooaccaoo..", "....oaao....", "....o..o....", "............", "............"]],
    "king": [["...g.gg.g...", "...gggggg...", "..oaaaaaao..", ".ommmmmmmmo.", ".omwwmmwwmo.", ".ommmmmmmmo.",
              "oommmkkmmmoo", "olmmmmmmmmdo", "olmmmmmmmmdo", ".ommmmmmmdo.", ".oddo..oddo.", ".oo......oo."],
             ["...g.gg.g...", "...gggggg...", "..oaaaaaao..", ".ommmmmmmmo.", ".omwwmmwwmo.", ".ommmmmmmmo.",
              "oommmkkmmmoo", "olmmmmmmmmdo", "olmmmmmmmmdo", ".ommmmmmmdo.", "..oddooddo..", "..oo....oo.."]],
}
ENEMY_ART["mirelet"] = ENEMY_ART["lump"]


def _pal(m, l, d=None, a=None, b=None, w=(250, 250, 240)):
    d = d or shade(m, 0.62)
    return dict(m=m, l=l, d=d, a=a or shade(m, 0.5), b=b or l, w=w)


ENEMY_PAL = {
    "scuttler": _pal((176, 92, 206), (226, 160, 246), w=(255, 236, 120)),
    "dart": _pal((246, 140, 40), (255, 200, 110), a=(255, 236, 130), w=(30, 20, 20)),
    "shell": _pal((126, 132, 150), (186, 192, 206), a=(84, 92, 110), b=(160, 168, 188), w=(255, 120, 90)),
    "wisp": _pal((110, 230, 240), (220, 252, 255), b=(160, 240, 255), w=(255, 255, 255)),
    "lump": _pal((120, 176, 50), (178, 222, 96), w=(250, 250, 130)),
    "mirelet": _pal((140, 196, 66), (196, 234, 120), w=(250, 250, 130)),
    "mend": _pal((60, 190, 130), (140, 240, 180), a=(255, 255, 255), b=(140, 255, 170), w=(255, 255, 220)),
    "ward": _pal((176, 180, 206), (226, 228, 246), a=(50, 120, 220), b=(120, 196, 255), w=(255, 255, 255)),
    "brute": _pal((150, 110, 84), (204, 164, 124), w=(255, 90, 60)),
    "crow": _pal((92, 108, 186), (156, 176, 236), a=(255, 196, 60), w=(255, 226, 90)),
    "ironhide": _pal((100, 104, 124), (160, 164, 184), a=(70, 74, 92), b=(146, 152, 176), w=(255, 90, 50)),
    "brood": _pal((140, 48, 156), (204, 100, 216), a=(220, 60, 96), b=(255, 130, 160), w=(255, 236, 100)),
    "thunder": _pal((70, 96, 190), (130, 164, 246), a=(255, 226, 60), b=(130, 164, 246), w=(255, 255, 200)),
    "king": _pal((60, 36, 84), (110, 80, 150), a=(150, 36, 70), b=(220, 70, 110), w=(255, 60, 80)),
}
for _k in ENEMY_PAL:
    ENEMY_PAL[_k].update(o=mix(ENEMY_PAL[_k]["d"], (10, 6, 16), 0.6), k=(10, 6, 12), g=(255, 210, 80), c=WHITE)
for _k in TOWER_PAL:
    TOWER_PAL[_k].update(o=mix(TOWER_PAL[_k]["d"], (12, 8, 10), 0.62), k=(14, 10, 12), g=(250, 206, 90), w=WHITE)

_SPR = {}


def fit_art(grid, w, h):
    """Pixel art at w x h: Scale2x-smoothed on the way up, box-filtered on the way down (each target pixel the
    mean of the art it covers, see-through where most of it is), so small sprites stay clean colour shapes."""
    sh, sw = len(grid), len(grid[0])
    if w >= sw and h >= sh:
        return scale_art(grid, w, h)
    out = []
    for y in range(h):
        a0, a1 = y * sh / h, (y + 1) * sh / h
        row = []
        for x in range(w):
            b0, b1 = x * sw / w, (x + 1) * sw / w
            tot = wo = r = gg = bb = 0.0
            for yy in range(int(a0), min(sh, int(math.ceil(a1)))):
                fy = min(a1, yy + 1) - max(a0, yy)
                src = grid[yy]
                for xx in range(int(b0), min(sw, int(math.ceil(b1)))):
                    f = fy * (min(b1, xx + 1) - max(b0, xx))
                    tot += f
                    c = src[xx]
                    if c is not None:
                        wo += f
                        r += c[0] * f
                        gg += c[1] * f
                        bb += c[2] * f
            row.append((int(r / wo), int(gg / wo), int(bb / wo)) if wo > 0.42 * tot else None)
        out.append(row)
    return out


def sprite(art, pal, w, h, flip=False, tint=None, key=None):
    """Pixel art scaled to w x h (Scale2x smoothing on the way up), as [(dx, dy, colour)]."""
    k = (key, w, h, flip, tint)
    r = _SPR.get(k)
    if r is not None:
        return r
    if len(_SPR) > 3000:
        _SPR.clear()
    grid = [[pal.get(ch) if ch != "." else None for ch in (row[::-1] if flip else row)] for row in art]
    sc = fit_art(grid, w, h)
    out = []
    for y, row in enumerate(sc):
        for x, c in enumerate(row):
            if c is not None:
                if tint == "hit":
                    c = mix(c, WHITE, 0.7)
                elif tint == "slow":
                    c = mix(c, (150, 210, 255), 0.35)
                elif tint == "pois":
                    c = mix(c, (150, 255, 90), 0.3)
                elif tint == "ice":
                    c = mix(c, (200, 240, 255), 0.65)
                elif tint == "ghost":
                    c = mix(c, (200, 255, 200), 0.3)
                out.append((x, y, c))
    _SPR[k] = out
    return out


def blit(cv, runs, x0, y0, a=1.0, col=None):
    W, H, px = cv.W, cv.H, cv.px
    if col is not None:
        for x, y, c in runs:
            X, Y = x0 + x, y0 + y
            if 0 <= X < W and 0 <= Y < H:
                px[Y][X] = mix(px[Y][X], col, a)
        return
    if a >= 1:
        for x, y, c in runs:
            X, Y = x0 + x, y0 + y
            if 0 <= X < W and 0 <= Y < H:
                px[Y][X] = c
    else:
        for x, y, c in runs:
            X, Y = x0 + x, y0 + y
            if 0 <= X < W and 0 <= Y < H:
                px[Y][X] = mix(px[Y][X], c, a)


def tower_runs(kind, level, branch, w, h):
    pal = dict(TOWER_PAL[kind])
    if branch is not None:
        pal.update(BRANCH_ACCENT[branch])
    elif level >= 2:
        for c in ("a", "b", "c"):
            pal[c] = mix(pal[c], WHITE, 0.12 * (level - 1))
    if level >= 3 or branch is not None:
        pal["o"] = (70, 52, 24)
    art = MICRO_ART[kind] if w <= 5 else TOWER_ART[kind]
    return sprite(art, pal, w, h, key=("T", kind, level, branch))


def plinth(cv, x0, y0, w, h, col=(110, 104, 96)):
    if w < 3:
        return
    m = 1 if w >= 6 else 0
    cv.rect(x0 + m, y0 + m, w - 2 * m, h - 2 * m, col)
    if w >= 4:
        cv.rect(x0 + m, y0 + m, w - 2 * m, 1, shade(col, 1.25))
        cv.rect(x0 + m, y0 + m, 1, h - 2 * m, shade(col, 1.15))
        cv.rect(x0 + m, y0 + h - m - 1, w - 2 * m, 1, shade(col, 0.6))
        cv.rect(x0 + w - m - 1, y0 + m, 1, h - 2 * m, shade(col, 0.72))


def draw_tower(cv, v, t, g, ghost=False):
    x0, y0, w, h = v.tile(t.x, t.y)
    s = v.s
    if not ghost:
        if w >= 6:
            plinth(cv, x0, y0, w, h)
        else:
            cv.rect(x0, y0 + h - 1, w, 1, (40, 34, 36))
    sw = max(1, int(round(w * 1.0)))
    sh = max(1, int(round(h * (1.06 if w >= 6 else 1.0))))
    runs = tower_runs(t.kind, t.level, t.branch, sw, sh)
    yo = y0 + h - sh - (1 if h >= 6 else 0)
    blit(cv, runs, x0 + (w - sw) // 2, yo, 0.55 if ghost else 1.0)
    if ghost:
        return
    cx, cy = x0 + w / 2, y0 + h / 2
    if t.kind == "bolt" and s >= 4:
        L = s * 0.42
        ax, ay = math.cos(t.ang), math.sin(t.ang)
        bx, by = cx, y0 + h * 0.3
        cv.line(bx - ay * L * 0.5, by + ax * L * 0.5, bx + ay * L * 0.5, by - ax * L * 0.5, (110, 76, 44))
        cv.line(bx, by, bx + ax * L, by + ay * L, (200, 200, 210))
    elif t.kind == "harpoon" and s >= 3:
        L = s * 0.62
        ax, ay = math.cos(t.ang), math.sin(t.ang)
        bx, by = cx, y0 + h * 0.42
        cv.line(bx - ax * L * 0.3, by - ay * L * 0.3, bx + ax * L, by + ay * L, (190, 196, 210))
        cv.set(int(bx + ax * L), int(by + ay * L), WHITE)
    elif t.kind == "storm":
        k = 0.4 + 0.4 * math.sin(g.clock * 9 + t.x) + (0.8 if t.flash > 0 else 0)
        if s >= 4:
            glow(cv, cx, y0 + h * 0.15, 0, s * (0.35 + 0.25 * (t.flash > 0)), (200, 160, 255), 0.35 * k)
    elif t.kind == "beacon":
        f = 0.6 + 0.4 * math.sin(g.clock * 7 + t.x * 3)
        if s >= 4:
            glow(cv, cx, y0 + h * 0.08, 0, s * 0.45, (255, 200, 90), 0.3 * f)
    elif t.kind == "mortar" and t.flash > 0 and s >= 3:
        glow(cv, cx, cy, 0, s * 0.5, (255, 160, 60), 0.5 * t.flash / 0.25)
    if t.flash > 0.3:   # just upgraded
        for x, y, c in runs[::3]:
            blend(cv, x0 + (w - sw) // 2 + x, yo + y, WHITE, 0.5)
    if s >= 6:          # level pips and the path gem
        n = 3 if t.branch is not None else t.level
        for j in range(n):
            cv.set(x0 + 1 + j * 2, y0 + h - 2, (250, 210, 90))
        if t.branch is not None:
            cv.set(x0 + w - 3, y0 + h - 2, BRANCH_ACCENT[t.branch]["b"])
            cv.set(x0 + w - 2, y0 + h - 2, BRANCH_ACCENT[t.branch]["c"])


def draw_enemy(cv, v, e, g):
    s = v.s
    size = max(1, int(round(e.size * s)))
    fr = int(g.clock * (6 + e.spd * 3) + e.seed) % 2 if (e.freeze_t <= 0 and e.stun_t <= 0) else 0
    flip = e.vx < -0.05
    tint = "hit" if e.hit_t > 0 else "ice" if e.freeze_t > 0 else "pois" if e.pois_t > 0 else "slow" if e.slow_t > 0 else None
    runs = sprite(ENEMY_ART[e.kind][fr], ENEMY_PAL[e.kind], size, size, flip, tint, key=("E", e.kind, fr))
    # a sideways offset so a crowd does not stack on one pixel
    off = ((e.seed % 7) - 3) * 0.045
    nx, ny = (-e.vy, e.vx)
    nl = math.hypot(nx, ny) or 1.0
    ex, ey = e.x + nx / nl * off, e.y + ny / nl * off
    cx, cy = v.ox + ex * s, v.oy + ey * s
    lift = 0
    if e.fly:
        lift = int(s * 0.35 + math.sin(g.clock * 4 + e.seed) * s * 0.06)
        if s >= 3:
            disc(cv, cx, cy + size * 0.2, max(0.8, size * 0.32), (0, 0, 0), 0.3)
    elif s >= 4:
        disc(cv, cx, cy + size * 0.38, max(0.8, size * 0.35), (0, 0, 0), 0.25)
    x0, y0 = int(cx - size / 2), int(cy - size / 2) - lift
    if e.heal_fx > 0 and s >= 3:
        glow(cv, cx, y0 + size / 2, 0, size * 0.9, (120, 255, 150), 0.4 * e.heal_fx / 0.5)
    if e.boss and s >= 3:
        glow(cv, cx, y0 + size / 2, size * 0.3, size * 0.9, ENEMY_PAL[e.kind]["b"], 0.2)
    if size <= 5:       # a small foe gets a dark rim so it reads on any ground
        blit(cv, runs, x0 + 1, y0 + 1, 0.55, (14, 8, 18))
    blit(cv, runs, x0, y0)
    if e.shield > 0 and s >= 3:
        k = e.shield / max(1, e.maxshield)
        ring(cv, cx, y0 + size / 2, size * 0.62 + 0.5, (140, 210, 255), 0.35 + 0.5 * k, 2 if k < 0.5 else 1)
    if e.stun_t > 0 and s >= 4:
        for j in range(3):
            a = g.clock * 6 + j * 2.1
            cv.set(int(cx + math.cos(a) * size * 0.45), int(y0 - 1 + math.sin(a) * 1.2), (255, 240, 140))
    if (s >= 5 and e.hp < e.maxhp - 0.01) or (e.boss and s >= 3):
        bw = max(3, size)
        bx, by = int(cx - bw / 2), y0 - 2 if s >= 5 else y0 - 1
        f = clamp(e.hp / e.maxhp, 0, 1)
        cv.rect(bx, by, bw, 1, (60, 16, 20))
        cv.rect(bx, by, max(1, int(bw * f)), 1, (110, 230, 90) if f > 0.5 else (240, 200, 60) if f > 0.25 else (240, 70, 60))
        if e.maxshield and e.shield > 0 and s >= 5:
            cv.rect(bx, by - 1, max(1, int(bw * e.shield / e.maxshield)), 1, (140, 210, 255))


def draw_exit(cv, v, g):
    ex, ey = g.exit
    x0, y0, w, h = v.tile(ex, ey)
    s = v.s
    cx = x0 + w / 2
    pulse = 0.5 + 0.5 * math.sin(g.clock * 2.4)
    hurt = g.time - g.last_leak < 0.6 and g.last_leak > 0
    col = (255, 110, 100) if hurt else (120, 255, 210)
    if s >= 3:
        glow(cv, cx, y0 + h * 0.4, 0, s * 1.3, col, 0.25 + 0.15 * pulse)
    # the standing stone
    top = y0 - int(h * 0.75)
    sw = max(2, int(w * 0.62))
    if s >= 3:
        disc(cv, cx + w * 0.08, y0 + h * 0.9, w * 0.42, (0, 0, 0), 0.3)
    cv.poly([(cx - sw / 2, y0 + h * 0.92), (cx - sw / 2 * 0.8, top + h * 0.2), (cx, top), (cx + sw / 2 * 0.8, top + h * 0.2),
             (cx + sw / 2, y0 + h * 0.92)], (110, 116, 124))
    cv.poly([(cx - sw / 2, y0 + h * 0.92), (cx - sw / 2 * 0.8, top + h * 0.2), (cx, top), (cx, y0 + h * 0.92)], (150, 156, 164))
    if s >= 4:   # the rune
        for j in range(int(h * 0.6)):
            yy = top + int(h * 0.3) + j
            xx = cx + math.sin(j * 1.3) * sw * 0.12
            blend(cv, int(xx), yy, col, 0.6 + 0.4 * pulse)
    else:
        cv.set(int(cx), int(y0 + h * 0.3), col)


def draw_portals(cv, v, g):
    s = v.s
    for i, (sx, sy) in enumerate(g.spawns):
        x0, y0, w, h = v.tile(sx, sy)
        cx, cy = x0 + w / 2, y0 + h / 2
        if s >= 3:
            for j in range(6):
                a = g.clock * 2.2 + j * math.pi / 3
                r = w * (0.2 + 0.18 * ((j % 2) + math.sin(g.clock * 3 + j) * 0.3))
                blend(cv, int(cx + math.cos(a) * r), int(cy + math.sin(a) * r), (200, 120, 255), 0.8)
            glow(cv, cx, cy, 0, w * 0.6, (150, 70, 220), 0.18)
        else:
            cv.set(int(cx), int(cy), (180, 100, 240))


def draw_route(cv, v, g):
    """On open ground the road changes with every tower: marching dots show where the foes will walk."""
    s = v.s
    th = THEMES[g.m["theme"]]
    ph = g.clock * 2.0
    for r in g.routes:
        n = len(r)
        for j, (x, y) in enumerate(r):
            k = ((j - ph) % 4) / 4
            a = 0.25 + 0.35 * (k > 0.75)
            px, py = v.X(x + 0.5), v.Y(y + 0.5)
            if j + 1 < n and s >= 4:
                nx, ny = r[j + 1]
                blend(cv, int(v.ox + (x + 0.5 + (nx - x) * 0.5) * s), int(v.oy + (y + 0.5 + (ny - y) * 0.5) * s),
                      th["accent"], a * 0.6)
            blend(cv, px, py, th["accent"], a)


def draw_projs(cv, v, g):
    s = v.s
    for p in g.projs:
        x, y = v.ox + p.x * s, v.oy + p.y * s
        if p.kind == "shell":
            k = p.t / p.T
            hgt = math.sin(math.pi * k) * s * (0.8 + 0.4 * p.T)
            if s >= 3:
                disc(cv, x, y, max(0.6, s * 0.1), (0, 0, 0), 0.3)
            disc(cv, x, y - hgt, max(0.7, s * 0.13), (60, 50, 50))
            cv.set(int(x - s * 0.04), int(y - hgt - s * 0.05), (255, 200, 120))
        elif p.kind == "glob":
            disc(cv, x, y, max(0.6, s * 0.1), (140, 220, 70))
            cv.set(int(x), int(y), (230, 160, 240))
        else:
            L = s * (0.55 if p.kind == "spear" else 0.32)
            col = (200, 206, 220) if p.kind == "spear" else (220, 190, 130)
            cv.line(x - p.vx * L, y - p.vy * L, x, y, col)
            cv.set(int(x), int(y), WHITE)


def draw_arcs(cv, v, g):
    s = v.s
    for pts, t, life, seed in g.arcs:
        k = 1 - t / life
        rnd = random.Random(seed + int(t * 40))
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            n = max(2, int(math.hypot(bx - ax, by - ay) * 2.5))
            prev = (v.ox + ax * s, v.oy + ay * s)
            for j in range(1, n + 1):
                f = j / n
                jx = (rnd.uniform(-0.18, 0.18) if j < n else 0) * s
                jy = (rnd.uniform(-0.18, 0.18) if j < n else 0) * s
                cur = (v.ox + (ax + (bx - ax) * f) * s + jx, v.oy + (ay + (by - ay) * f) * s + jy)
                cv.line(prev[0], prev[1], cur[0], cur[1], mix((150, 100, 255), WHITE, k))
                prev = cur
            if s >= 4:
                glow(cv, v.ox + bx * s, v.oy + by * s, 0, s * 0.45, (190, 150, 255), 0.4 * k)


def draw_fx(cv, v, g):
    s = v.s
    for b in g.burns:
        n = max(2, int(b[2] * s * 1.5))
        r = b[2] * s
        for j in range(n):
            h = hsh(j, int(g.clock * 12), int(b[0] * 10))
            a = (h % 628) / 100
            d = (h % 97) / 97 * r
            blend(cv, int(v.ox + b[0] * s + math.cos(a) * d), int(v.oy + b[1] * s + math.sin(a) * d * 0.8),
                  (255, 120 + h % 100, 40), 0.7)
    for rg in g.rings:
        x, y, r0, r1, t, life, col = rg
        k = t / life
        rad = (r0 + (r1 - r0) * k) * s
        ring(cv, v.ox + x * s, v.oy + y * s, rad, col, (1 - k) * 0.8)
    psz = max(1, int(s // 4))
    for p in g.parts:
        k = 1 - p[4] / p[5]
        x, y = int(v.ox + p[0] * s), int(v.oy + p[1] * s)
        if psz == 1:
            blend(cv, x, y, p[6], 0.35 + 0.65 * k)
        else:
            for yy in range(y, y + psz):
                for xx in range(x, x + psz):
                    blend(cv, xx, yy, p[6], 0.35 + 0.65 * k)


def draw_ambient(cv, v, g):
    th = THEMES[g.m["theme"]]
    s = v.s
    n = 14 if s >= 4 else 6
    fw, fh = GW * s, GH * s
    for j in range(n):
        h = hsh(j, 7, g.map_i)
        t = g.clock * (0.15 + (h % 7) / 40) + (h % 1000) / 100
        if g.m["theme"] == "frost":
            x = ((h % 997) / 997 * fw + math.sin(t * 3) * s) % fw
            y = (t * s * 2.4 + (h % 613)) % fh
        else:
            x = ((h % 997) / 997 * fw + math.sin(t * 1.3) * s * 1.6) % fw
            y = ((h % 613) / 613 * fh + math.cos(t * 0.9) * s * 1.2) % fh
        a = 0.3 + 0.3 * math.sin(t * 5 + j)
        blend(cv, int(v.ox + x), int(v.oy + y), th["mote"], max(0.0, a))


def draw_cursor(cv, v, g):
    x0, y0, w, h = v.tile(g.cx, g.cy)
    t = g.tower_at(g.cx, g.cy)
    ok = t is not None or g.can_build(g.cx, g.cy)[0]
    k = 0.6 + 0.4 * math.sin(g.clock * 8)
    col = mix((255, 240, 160), WHITE, k * 0.5) if ok else (255, 110, 100)
    s = v.s
    if t:
        rng = t.st["rng"]
        ring(cv, x0 + w / 2, y0 + h / 2, rng * s, (255, 236, 170) if t.kind != "beacon" else (255, 200, 90), 0.8, 1 if s < 6 else 2)
        if t.kind == "beacon":
            for o in g.towers.values():
                if o.buff_by is t:
                    ox0, oy0, ow, oh = v.tile(o.x, o.y)
                    cv.frame(ox0, oy0, ow, oh, (255, 210, 110))
    elif ok:
        st = tstats(g.sel, 1, None)
        ring(cv, x0 + w / 2, y0 + h / 2, st["rng"] * s, (200, 236, 255), 0.7, 1 if s < 6 else 2)
        draw_tower(cv, v, Tower(g.sel, g.cx, g.cy), g, ghost=True)
    if w >= 7:
        L = max(2, w // 3)
        for (ax, ay) in ((x0 - 1, y0 - 1), (x0 + w, y0 - 1), (x0 - 1, y0 + h), (x0 + w, y0 + h)):
            dx = 1 if ax < x0 + w / 2 else -1
            dy = 1 if ay < y0 + h / 2 else -1
            cv.rect(min(ax, ax + dx * (L - 1)), ay, L, 1, col)
            cv.rect(ax, min(ay, ay + dy * (L - 1)), 1, L, col)
    else:
        cv.frame(x0 - 1, y0 - 1, w + 2, h + 2, col)


HUD_BG = (14, 12, 24)
HUD_FG = (214, 214, 232)
HUD_DIM = (136, 140, 172)
GOLD = (250, 214, 120)
HEART = (255, 110, 120)


def render(g, cols, rows, hud=True, cursor=None):
    s, ox, oy = layout(cols, rows, hud)
    cv = Canvas(cols, 1)
    cv.rows, cv.H = rows, rows * 2
    cv.px = [r[:] for r in backdrop(g.map_i, cols, rows, hud)]
    if g.shake > 0 and s >= 3:
        k = g.shake * s * 0.6
        ox += int(g.rnd.uniform(-k, k))
    v = View(s, ox, oy)
    if g.maze:
        draw_route(cv, v, g)
    draw_portals(cv, v, g)
    # towers and ground foes in row order, so the lower one overlaps the upper one
    things = [(t.y + 0.99, 0, t) for t in g.towers.values()] + [(e.y + 0.3, 1, e) for e in g.enemies if not e.fly]
    things.append((g.exit[1] + 0.98, 2, None))
    things.sort(key=lambda a: a[0])
    for _, kind, o in things:
        if kind == 0:
            draw_tower(cv, v, o, g)
        elif kind == 1:
            draw_enemy(cv, v, o, g)
        else:
            draw_exit(cv, v, g)
    draw_fx(cv, v, g)
    for e in g.enemies:
        if e.fly:
            draw_enemy(cv, v, e, g)
    draw_projs(cv, v, g)
    draw_arcs(cv, v, g)
    draw_ambient(cv, v, g)
    if (cursor if cursor is not None else hud) and g.state == "play":
        draw_cursor(cv, v, g)
    if rows > 10:
        for f in g.floats:
            x, y, txt, t, col = f
            row = int(v.Y(y) // 2)
            if (1 if hud else 0) <= row < rows - (2 if hud else 0):
                cv.put(int(v.X(x) - len(txt) / 2), row, txt, mix(col, (40, 30, 40), max(0.0, t - 0.7) * 1.6))
    if hud:
        draw_hud(cv, g)
        draw_banners(cv, g)
    return cv


def stars_txt(n, of=3):
    return "★" * n + "☆" * (of - n)


def draw_hud(cv, g):
    cols, rows = cv.cols, cv.rows
    cv.put(0, 0, " " * cols, HUD_FG, HUD_BG)
    parts = [(" ♥ ", HEART), ("%d" % g.lives, HUD_FG), ("   ◆ ", GOLD), ("%d" % int(g.gold), GOLD),
             ("   WAVE ", HUD_DIM), ("%d%s" % (g.wave, ("/%d" % g.n_waves) if g.n_waves else ""), HUD_FG),
             ("   SCORE ", HUD_DIM), ("%06d" % g.score, HUD_FG)]
    x = 0
    for s_, c in parts:
        cv.put(x, 0, s_, c, HUD_BG)
        x += len(s_)
    right = []
    if g.speed > 1:
        right.append((" ▶x%d " % g.speed, (20, 16, 10), (240, 200, 110)))
    if g.countdown is not None and g.state == "play":
        right.append((" next %ds " % max(0, math.ceil(g.countdown)), HUD_FG, HUD_BG))
    right.append((" %s " % g.m["name"], THEMES[g.m["theme"]]["accent"], HUD_BG))
    w = sum(len(r[0]) for r in right)
    if x + w + 1 > cols:
        right = right[:-1]
        w = sum(len(r[0]) for r in right)
    if g.next_groups and g.state == "play":
        room = cols - w - x - 4
        tags = wave_tags(g.next_groups)
        n = sum(c for k, c, *_ in g.next_groups if not ENEMIES[k].get("boss"))
        for txt in ("next: %s" % wave_text(g.next_groups), "next: %d foes" % n):
            tg = " [%s]" % " ".join(tags) if tags else ""
            if len(txt) + len(tg) <= room:
                cv.put(x + 3, 0, txt, (176, 180, 210), HUD_BG)
                cv.put(x + 3 + len(txt), 0, tg, (255, 170, 120) if "boss" in tags or "air" in tags else (200, 200, 140), HUD_BG)
                break
    rx = cols - w
    for s_, fg, bg in right:
        if rx > x:
            cv.put(rx, 0, s_, fg, bg)
        rx += len(s_)
    # the build bar
    r = rows - 2
    cv.put(0, r, " " * cols, HUD_FG, HUD_BG)
    x = 1
    compact = cols < 96
    for n, kind in enumerate(ORDER):
        T = TOWERS[kind]
        if compact and kind != g.sel:
            lab = " %d %s " % (n + 1, T["short"])
        else:
            lab = " %d %s %d " % (n + 1, T["short"], T["cost"])
        if x + len(lab) > cols:
            break
        afford = T["cost"] <= g.gold
        if kind == g.sel:
            cv.put(x, r, lab, (16, 14, 20), GOLD if afford else (170, 150, 120))
        else:
            cv.put(x, r, lab, HUD_FG if afford else (96, 96, 120), HUD_BG)
        x += len(lab) + (0 if compact else 1)
    # the context line
    r = rows - 1
    cv.put(0, r, " " * cols, HUD_FG, HUD_BG)
    line = context_line(g, cols)
    xx = 1
    for s_, c in line:
        if xx >= cols:
            break
        cv.put(xx, r, s_[:cols - xx], c, HUD_BG)
        xx += len(s_)


def context_line(g, cols):
    """What the bottom line says: a message, the tower under the cursor, what would be built, or the next wave."""
    if g.msg:
        return [(g.msg[0], g.msg[2])]
    t = g.tower_at(g.cx, g.cy)
    if t:
        st = t.st
        c = cols < 110
        bits = [(t.title.upper(), GOLD)]
        if t.kind == "beacon":
            bits.append(("  +%d%% dmg%s" % (st["buff"] * 100, " +%d%% speed" % (st["haste"] * 100) if st.get("haste") else ""), HUD_FG))
        elif t.kind == "frost":
            bits.append(("  slow %d%%  %s%.1f" % (st["slow"] * 100, "r" if c else "range ", st["rng"]), HUD_FG))
        elif t.kind == "venom":
            bits.append(("  %d/s poison  %s%.1f" % (st["dps"], "r" if c else "range ", st["rng"]), HUD_FG))
        else:
            bits.append(("  dmg %d %.1f/s %s%.1f %s" % (st["dmg"], st["rate"], "r" if c else " range ", st["rng"],
                                                     TARGETS[t.aim]), HUD_FG))
        if t.buff_by:
            bits.append((" ✦", (255, 210, 110)))
        bits.append(("  X sell %d" % int(t.spent * SELL_BACK), HUD_DIM))
        if t.branch is None:
            if t.level < 3:
                bits.append(("  U up %d" % next_cost(t.kind, t.level, None), HUD_FG))
            else:
                B = TOWERS[t.kind]["branches"]
                bits.append(("  U %s %d  B %s %d" % (B[0]["name"], B[0]["cost"], B[1]["name"], B[1]["cost"]), (200, 230, 255)))
        elif cols >= 110:
            bits.append(("  %s" % TOWERS[t.kind]["branches"][t.branch]["desc"], HUD_DIM))
        return bits
    ok, why = g.can_build(g.cx, g.cy)
    if ok:
        T = TOWERS[g.sel]
        bits = [(T["name"].upper(), GOLD), ("  %s" % T["role"], HUD_FG), ("   Space build %d" % T["cost"], HUD_DIM)]
        if sum(len(b[0]) for b in bits) + 40 < cols:
            bits += next_line(g)
        return bits
    return next_line(g)


def next_line(g):
    if g.next_groups is None:
        return [("Last wave on the field.", HUD_DIM)]
    tags = wave_tags(g.next_groups)
    out = [("   NEXT %d: " % (g.wave + 1), (200, 200, 230)), (wave_text(g.next_groups), HUD_FG)]
    if tags:
        out.append(("  [%s]" % " ".join(tags), (255, 170, 120) if "boss" in tags or "air" in tags else (200, 200, 140)))
    if g.countdown is not None:
        out.append(("  N call +%d" % (int(g.countdown * 1.2) if g.wave else 0), HUD_DIM))
    return out


def banner(cv, lines, col):
    w = max(len(l) for l in lines) + 4
    x = max(0, (cv.cols - w) // 2)
    y = max(1, cv.rows // 2 - len(lines) // 2 - 1)
    cv.box(x, y, [l.center(w - 4) for l in lines], (236, 236, 244), (20, 18, 36))
    cv.put(x + 2, y + 1, lines[0].center(w - 4), col, (20, 18, 36))


def draw_banners(cv, g):
    if g.state == "clear":
        lines = ["LAND CLEARED", "", stars_txt(g.stars), "", "lives kept  %d of %d" % (g.lives, g.max_lives),
                 "bonus  %d" % g.tally, ""]
        nxt = g.map_i + 1 < len(MAPS) and g.mode == "campaign"
        lines.append(("Enter: on to %s" % MAPS[g.map_i + 1]["name"].title()) if nxt else "Enter: finish")
        banner(cv, lines, GOLD)
    elif g.banner and g.banner_t > 0 and g.state == "play":
        if len(g.banner) <= 2:      # a wave call: a slim strip, the land stays visible
            txt = "  ".join(g.banner)
            cv.center(2, " %s " % txt, g.banner_col, (20, 18, 36))
        else:
            banner(cv, g.banner, g.banner_col)


def render_over(g, cv, record, auto=False):
    if g.won:
        lines = ["THE WARDSTONES SHINE", "", "All eight lands are safe.", "", "score  %d" % g.score,
                 "stars  %d of %d" % (sum(g.earned.values()), 3 * len(MAPS))]
    else:
        lines = ["THE WARDSTONE IS DRAINED", "", "score  %d" % g.score,
                 ("reached wave %d" % g.wave) if g.endless else "%s, wave %d of %d" % (g.m["name"].title(), g.wave, g.n_waves),
                 "foes felled  %d" % g.total_kills]
    if record:
        lines += ["", "** NEW RECORD **"]
    lines += ["", "auto mode: a new round starts" if auto else "Enter: again   Esc / Q: menu"]
    w = max(len(l) for l in lines) + 4
    x, y = max(0, (cv.cols - w) // 2), max(0, cv.rows // 2 - len(lines) // 2 - 1)
    edge = GOLD if record or g.won else (200, 76, 86)
    cv.frame(x - 1, y * 2 - 1, w + 2, (len(lines) + 2) * 2 + 2, edge)
    cv.box(x, y, [l.center(w - 4) for l in lines], (240, 240, 246), (24, 22, 44))


# =============================================================================================
# Title demo, menu, main loop
# =============================================================================================
class TitleDemo:
    """The autopilot defending a land, one after the other, behind the title (and in the launcher preview)."""
    PICK = (0, 3, 6, 1, 5, 2, 7, 4)

    def __init__(self, k=0):
        self.k = k
        self.new_run()

    def new_run(self):
        mi = self.PICK[self.k % len(self.PICK)]
        self.g = Game("campaign", mi, seed=self.k + 1, demo=True)
        self.g.countdown = 3.0
        self.bot = Bot(self.g, seed=self.k)
        self.k += 1
        self.age = 0.0
        # a quick start: the first waves are already under way
        for _ in range(int(40 / DT)):
            self.bot()
            self.g.step(DT)

    def scene(self, cols, rows, dt):
        g = self.g
        self.age += dt
        n = max(1, int(min(dt, 0.1) * 2 / DT + 0.5))
        for _ in range(n):
            self.bot()
            g.step(DT)
        if g.state != "play" or self.age > 70:
            self.new_run()
        return render(self.g, cols, rows, hud=False)


class AutoRun:
    """Auto mode: the real game (sound, lives, waves) played by the autopilot from the chosen land.
    A cleared land goes on to the next after a few seconds; after a loss a new round starts. No score is kept."""
    SHOW = 4.0

    def __init__(self, map_i, sound=True, seed=None, mode="campaign"):
        self.map_i, self.sound, self.seed, self.mode = map_i, sound, seed, mode
        self.auto = AutoMode()
        self.rounds = 0
        self.new()

    def new(self):
        self.rounds += 1
        self.g = Game(self.mode, self.map_i, quiet=not self.sound,
                      seed=None if self.seed is None else self.seed + self.rounds)
        self.g.hi = 0
        self.bot = Bot(self.g, seed=None if self.seed is None else self.seed * 3 + self.rounds)
        self.mark = self.g.map_i
        self.wait = 0.0

    def key(self, k):
        a = self.auto.key(k)
        if a == "sound" and SND.toggle():
            SND.play("sound_on")
        return a

    def frame(self, dt, cols, rows, draw=True):
        g = self.g
        if g.over or g.state == "clear":
            if not (self.auto.paused or self.auto.help):
                self.wait += dt * min(2.0, self.auto.speed)
            if self.wait >= self.SHOW:
                self.wait = 0.0
                if g.over:
                    self.new()
                elif not g.next_map():
                    self.new()
                else:
                    self.bot.reset()
                g = self.g
        else:
            for _ in range(self.auto.steps(dt, DT)):
                self.bot()
                g.step(DT)
                if g.over or g.state == "clear":
                    break
        if not draw:
            return None
        cv = render(g, cols, rows)
        if g.over:
            render_over(g, cv, False, auto=True)
        self.auto.banner(cv, extra="round %d" % self.rounds)
        return cv


def too_small(term):
    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (%dx%d)." % (MIN_COLS, MIN_ROWS))


def run_auto(term, map_i):
    run = AutoRun(map_i)
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


def saved_stars():
    rec = load_scores().get(GAME, {})
    return [int(rec.get("stars%d" % i, 0) or 0) for i in range(len(MAPS))]


def menu_items(map_i, stars):
    return ["Campaign", "Endless", "Land select  < %d %s %s >" % (map_i + 1, MAPS[map_i]["name"].title(),
                                                                stars_txt(stars[map_i])), AUTO_LABEL]


def render_menu(demo, cols, rows, sel, map_i, dt, help_):
    cv = demo.scene(cols, rows, dt)
    rec = load_scores().get(GAME, {})
    stars = saved_stars()
    bits = []
    if rec.get("campaign"):
        bits.append("campaign %d" % rec["campaign"])
    if rec.get("endless"):
        bits.append("endless %d (wave %d)" % (rec["endless"], rec.get("endless_wave", 0)))
    if sum(stars):
        bits.append("stars %d/%d" % (sum(stars), 3 * len(MAPS)))
    best = ("best  " + "   ".join(bits)) if bits else None
    extra = ["", "The Hollow host marches on the Wardstones.", "Raise towers by the roads, hold every land.",
             "Endless: the chosen land, waves without end."]
    title_screen(cv, NAME, TAGLINE, menu_items(map_i, stars), sel, best, extra=extra,
                 keys="Up/Down choose   Left/Right land   Enter start   M %s   ? help   Esc back" % SND.label().lower(),
                 help_lines=help_lines(), show_help=help_, dim=0.45)
    return cv


def record(g):
    rec = submit(GAME, g.mode, g.score)
    if g.endless:
        submit(GAME, "endless_wave", g.wave)
    return rec


def save_stars(g):
    for mi, st in g.earned.items():
        submit(GAME, "stars%d" % mi, st)


MOVE_KEYS = ("up", "down", "left", "right", "w", "a", "s", "d")


def play(term, mode, start):
    """One game. Returns 'again' or 'menu'."""
    g = Game(mode, start)
    last = time.time()
    rec = None
    submitted = False
    acc = 0.0
    while True:
        now = time.time()
        dt = min(0.1, now - last)
        last = now
        for name, kind in term.events():
            if kind == "release":
                continue
            if kind == "repeat" and name not in MOVE_KEYS:
                continue
            if g.over:
                if name in ("q", "esc"):
                    return "menu"
                if name in ("enter", " ") and kind == "press":
                    SND.play("start")
                    return "again"
                continue
            a = shared_key(name, g.paused)
            if a == "pause":
                g.paused = True
                SND.play("pause")
            elif a == "resume":
                g.paused = g.help = False
                last = time.time()
            elif a == "quit":
                save_stars(g)
                if not submitted and g.score:
                    record(g)
                return "menu"
            elif a == "help":
                g.help = not g.help
                g.paused = True
            elif a == "sound":
                if SND.toggle():
                    SND.play("sound_on")
            elif a is None:
                if g.state == "clear" and name in ("enter", " ") and g.state_t > 0.6:
                    save_stars(g)
                    g.next_map()
                    continue
                if g.key(name) and name in MOVE_KEYS:
                    SND.play("move", 0.5, 0.03)
        cols, rows = term.size()
        if cols < MIN_COLS or rows < MIN_ROWS:
            too_small(term)
            g.paused = g.paused or not g.over
            time.sleep(0.2)
            last = time.time()
            continue
        if not g.paused:
            acc += dt * g.speed
            n = 0
            while acc >= DT and n < 12:
                g.step(DT)
                acc -= DT
                n += 1
            if n == 12:
                acc = 0.0
        if g.over and not submitted:
            submitted = True
            save_stars(g)
            rec = record(g)
        cv = render(g, cols, rows)
        if g.paused:
            overlay(cv, help_lines() if g.help else PAUSE_LINES + ["", SND.label()])
        elif g.over:
            render_over(g, cv, rec)
        term.write(cv.emit())
        time.sleep(max(0.0, 1 / 30 - (time.time() - now)))


def main():
    with KeyTerminal() as term:
        demo = TitleDemo()
        sel, map_i, help_ = 0, 0, False
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
            term.write(render_menu(demo, cols, rows, sel, map_i, min(0.1, now - last), help_).emit())
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
                    map_i = (map_i - 1) % len(MAPS)
                    sel = sel if sel in (1, 3) else 2
                    SND.play("menu")
                elif k in ("right", "d"):
                    map_i = (map_i + 1) % len(MAPS)
                    sel = sel if sel in (1, 3) else 2
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
                run_auto(term, map_i)
                last = time.time()
                continue
            mode = "endless" if sel == 1 else "campaign"
            start = map_i if sel in (1, 2) else 0
            while play(term, mode, start) == "again":
                pass
            last = time.time()


# =============================================================================================
# Self-test
# =============================================================================================
def run_bot(mode, map_i, limit=2400.0, seed=1, waves=None):
    """The autopilot defends one land. Returns the game when it is cleared, lost or out of time."""
    g = Game(mode, map_i, seed=seed, quiet=True)
    bot = Bot(g, seed=seed)
    t = 0.0
    while t < limit and g.state == "play":
        bot()
        g.step(DT)
        t += DT
        if waves is not None and g.wave >= waves and not g.enemies and not g.pending:
            break
    return g


def selftest():
    t0 = time.time()
    global submit

    def no_scores(*a, **k):
        raise AssertionError("the self-test must not write scores")
    submit = no_scores
    random.seed(3)
    # 1. the lands: roads follow their waypoints, no shortcuts, open grounds reachable
    for mi, m in enumerate(MAPS):
        tiles, spawns, exit_ = build_grid(mi)
        assert len(tiles) == GW * GH
        d = bfs(tiles, exit_)
        for s in spawns:
            assert d[s[1] * GW + s[0]] < INF, "%s: spawn %s cut off" % (m["name"], s)
        if m["kind"] == "path":
            roads = set()
            for p in m["paths"]:
                roads |= set(seg_tiles(p))
            seen = set()
            for p in m["paths"]:
                r = route_from(d, p[0], exit_)
                want = seg_tiles(p)
                assert r[:len(want)] == want, "%s: the road from %s takes a shortcut" % (m["name"], p[0])
                assert r[-1] == exit_
                seen |= set(r)
            assert seen == roads, "%s: road tiles nobody walks: %s" % (m["name"], roads - seen)
        for i in range(m["waves"]):
            assert make_wave(mi, i), "%s: wave %d is empty" % (m["name"], i + 1)
    print("lands: %d (%d with fixed roads, %d open), every road walked as drawn, %d waves in all" % (
        len(MAPS), sum(m["kind"] == "path" for m in MAPS), sum(m["kind"] == "maze" for m in MAPS),
        sum(m["waves"] for m in MAPS)))

    # 2. the rules
    g = Game("campaign", 0, seed=1, quiet=True)
    g.gold = 10000
    x, y = 7, 3
    assert not g.can_build(6, 3)[0], "built on the road"
    assert g.build(x, y, "bolt") and g.tower_at(x, y)
    t = g.tower_at(x, y)
    for lv in (2, 3):
        assert g.upgrade(t) and t.level == lv
    assert g.upgrade(t, 1) and t.branch == 1 and t.st.get("multi") == 2
    assert not g.upgrade(t), "upgraded past the last path"
    spent = t.spent
    gold = g.gold
    assert g.sell(t) == int(spent * SELL_BACK) and g.gold == gold + int(spent * SELL_BACK)
    # armour, shields, poison, healing, splitting, flying
    g = Game("campaign", 0, seed=2, quiet=True)
    e = g.spawn("shell", 0, 1.0)
    hp = e.hp
    g.hurt(e, 8, "phys")
    assert abs(e.hp - (hp - 3)) < 1e-6, "armour: %s" % (hp - e.hp)
    g.hurt(e, 8, "magic")
    assert abs(e.hp - (hp - 11)) < 1e-6, "magic ignores armour"
    w = g.spawn("ward", 0, 1.0)
    g.hurt(w, 30, "magic")
    assert w.hp == w.maxhp and w.shield == 20, "the shield takes the first hits"
    g.hurt(w, 14, "magic", strip=True)
    assert w.shield == 0 and abs(w.hp - (w.maxhp - 4)) < 1e-6, "overload: shields take double"
    for _ in range(int(6 / DT)):
        g.enemy_step(w, DT)
    assert w.shield > 0, "shields come back after a calm"
    m = g.spawn("mend", 0, 1.0)
    s1 = g.spawn("scuttler", 0, 1.0)
    s2 = g.spawn("scuttler", 0, 1.0)
    for o in (m, s1, s2):
        o.x, o.y = 10.5, 5.5
        o.fly = True                      # held in place for the test
        o.spd = 0
        o.flen = 99
    s1.hp = s2.hp = 10
    s2.pois, s2.pois_t = 0.0001, 60
    m.ab_t = 0
    g.enemy_step(m, DT)
    assert s1.hp > 10 and s2.hp < 10.01, "the mender heals, but not the poisoned"
    g = Game("campaign", 1, seed=3, quiet=True)
    lump = g.spawn("lump", 0, 1.0)
    n = len(g.enemies)
    g.hurt(lump, 999, "magic")
    assert len(g.enemies) == n + 2 and all(o.kind == "mirelet" for o in g.enemies[-2:]), "the mirelump splits"
    g = Game("campaign", 3, seed=4, quiet=True)
    g.gold = 10000
    assert g.build(5, 7, "mortar")
    wisp = g.spawn("wisp", 0, 1.0)
    wisp.p = 4.0
    g.enemy_step(wisp, DT)
    tw = g.tower_at(5, 7)
    assert not g.in_range(tw, 9, False, True), "the kiln sees a flyer"
    assert g.in_range(tw, 9, True, False)
    # open ground: the road bends around towers and can never be blocked
    g = Game("campaign", 3, seed=5, quiet=True)
    g.gold = 100000
    before = len(g.routes[0])
    for yy in range(1, 13):
        if yy != 9:
            g.build(8, yy, "bolt")
    assert len(g.routes[0]) > before, "the road did not bend around the towers"
    assert not g.can_build(8, 9)[0], "a tower blocked the only way"
    # frost, beacon buffs, storm chains, venom, mortar splash, in a real fight
    g = Game("campaign", 0, seed=6, quiet=True)
    g.gold = 10000
    g.build(7, 4, "frost")
    g.build(7, 5, "storm")
    g.build(5, 5, "beacon")
    st = g.tower_at(7, 5)
    assert st.buff_by is None
    g.build(7, 6, "beacon")
    assert st.buff_by is not None and abs(st.st["dmg"] - 14 * 1.15) < 1e-6, "the shrine does not buff"
    foes = [g.spawn("scuttler", 0, 1.0) for _ in range(5)]
    for j, o in enumerate(foes):
        o.x, o.y, o.tx, o.ty = 6.5, 4.0 + j * 0.3, 6, 4
    g.fire(g.tower_at(7, 4))
    assert all(o.slow_t > 0 for o in foes[:4]), "the bell does not slow"
    hp = [o.hp for o in foes]
    g.fire(st)
    assert sum(1 for o, h in zip(foes, hp) if o.hp < h) >= 3, "the coil did not chain"
    # waves, early call, interest, leaks, stars, game over
    g = Game("campaign", 0, seed=7, quiet=True)
    g.gold = 300
    g.countdown = 0.01
    g.step(DT)
    assert g.wave == 1 and g.gold == 300 + min(INTEREST_CAP, int(300 * INTEREST)) + 15, "wave bonus / interest"
    while g.pending:
        g.step(DT)
    g.step(DT)
    assert g.countdown is not None
    g.countdown = 10.0
    gold = g.gold
    assert g.call_wave() == 12 and g.wave == 2 and g.gold >= gold + 12, "early call bonus"
    lives = g.lives
    e = g.spawn("brute", 0, 1.0)
    for _ in range(int(200 / DT)):
        g.enemy_step(e, DT)
        if e.dead:
            break
    assert e.dead and g.lives == lives - 2, "a gravelhorn costs two lives"
    g.lives = 1
    g.spawn("dart", 0, 1.0)
    for _ in range(int(120 / DT)):
        g.step(DT)
        if g.over:
            break
    assert g.over and g.state == "lost", "no game over"
    g = Game("campaign", 0, seed=8, quiet=True)
    g.wave, g.pending, g.enemies, g.next_groups = g.n_waves, [], [], None
    g.countdown = None
    g.lives = 18
    g.step(DT)
    assert g.state == "clear" and g.stars == 3
    g = Game("campaign", 0, seed=8, quiet=True)
    g.wave, g.countdown, g.next_groups, g.lives = g.n_waves, None, None, 9
    g.step(DT)
    assert g.stars == 1
    print("rules: build / upgrade / two paths / sell, armour, shields and overload, healing and poison, splitting,")
    print("       flyers vs ground towers, roads bend on open ground and never close, frost, shrines, chains,")
    print("       wave bonus, interest, early call, leaks, stars, game over")

    # 3. the autopilot holds every land
    total = 0.0
    tstars = 0
    for mi in range(len(MAPS)):
        a = time.time()
        g = run_bot("campaign", mi, seed=mi + 1)
        assert g.state == "clear", "%s: the autopilot lost (wave %d, %d lives)" % (MAPS[mi]["name"], g.wave, g.lives)
        tstars += g.stars
        total += g.time
        print("  %-16s %s  %2d/%d lives  %3d towers' worth %5d gold  %4.0f s game  (%.1f s)" % (
            MAPS[mi]["name"], stars_txt(g.stars), g.lives, g.max_lives, len(g.towers),
            sum(t.spent for t in g.towers.values()), g.time, time.time() - a))
    print("autopilot: all %d lands held, %d of %d stars, %.0f s of game time" % (len(MAPS), tstars, 3 * len(MAPS), total))
    g = run_bot("endless", 0, seed=5, limit=1500)
    print("endless: the autopilot held %s to wave %d in 25 minutes of game time (%d lives left)" % (
        MAPS[0]["name"].title(), g.wave, g.lives))
    assert g.wave >= 15

    # 4. auto mode: real game at x8, pause, speed, stop, no score
    run = AutoRun(0, sound=False, seed=11)
    run.key(" ")
    snap = (run.g.clock, run.g.score)
    for _ in range(20):
        run.frame(1 / 30, 80, 24, draw=False)
    assert (run.g.clock, run.g.score) == snap, "auto mode ran on while paused"
    run.key(" ")
    for _ in range(5):
        run.key("+")
    assert run.auto.speed == 8.0
    for i in range(30 * 30):
        run.frame(1 / 30, 80 + i % 3 * 20, 24 + i % 2 * 8, draw=i % 60 == 0)
    assert run.key("esc") == "stop"
    print("auto mode: 30 s at x8, wave %d on %s, %d towers, nothing recorded" % (
        run.g.wave, run.g.m["name"].title(), len(run.g.towers)))

    # 5. the player's keys
    g = Game("campaign", 0, seed=9, quiet=True)
    g.cx, g.cy = 7, 3
    g.key("2")
    assert g.tower_at(7, 3) and g.tower_at(7, 3).kind == "mortar"
    g.key("right")
    g.key("tab")
    assert g.sel == "frost" and g.cx == 8
    g.gold = 1000
    g.key(" ")
    assert g.tower_at(8, 3).kind == "frost"
    g.key(" ")
    assert g.tower_at(8, 3).level == 2
    g.key("left")
    g.key("t")
    assert g.tower_at(7, 3).aim == 1
    g.key("x")
    assert g.tower_at(7, 3) is None
    g.key("f")
    assert g.speed == 2
    g.key("n")
    assert g.wave == 1
    print("keys: cursor, 1-7, Tab, Space build / upgrade, T aim, X sell, F speed, N call")

    # 6. rendering at every size, timing
    timing = []
    for cols, rows in ((70, 22), (80, 24), (100, 32), (120, 40), (240, 70)):
        tr = te = 0.0
        frames = 0
        for mi in range(len(MAPS)):
            g = Game("campaign", mi, seed=mi, quiet=True)
            bot = Bot(g, seed=mi)
            g.countdown = 1.0
            for _ in range(int(40 / DT)):
                bot()
                g.step(DT)
            g.cx, g.cy = (next(iter(g.towers.values())).x, next(iter(g.towers.values())).y) if g.towers else (3, 3)
            render(g, cols, rows)                  # the land's picture is drawn once and kept
            for state in ("play", "clear"):
                if state == "clear":
                    g.state, g.stars, g.tally = "clear", 2, 1000
                a = time.time()
                cv = render(g, cols, rows)
                b = time.time()
                cv.emit(True)
                c_ = time.time()
                tr += b - a
                te += c_ - b
                frames += 1
            overlay(cv, help_lines())
            g.over = True
            render_over(g, cv, True)
            cv.emit(True)
        timing.append((cols, rows, tr / frames * 1000, te / frames * 1000))
    d = TitleDemo()
    for cols, rows in ((70, 22), (120, 40), (24, 8), (40, 12), (60, 30)):
        render_menu(d, cols, rows, 0, 2, 0.05, False).emit(True) if rows >= 20 else d.scene(cols, rows, 0.05).emit(True)
    for _ in range(100):
        d.scene(30, 9, 0.1)
    print("rendering: every land at 70x22, 80x24, 100x32, 120x40, 240x70 (+ title, preview 24x8, overlays)")
    for cols, rows, r_, e_ in timing:
        print("  %3dx%-3d render %5.1f ms  emit %5.1f ms  = %5.1f ms per frame (%3.0f fps)" % (
            cols, rows, r_, e_, r_ + e_, 1000 / max(0.1, r_ + e_)))
    g = Game("campaign", 7, seed=2, quiet=True)
    bot = Bot(g, seed=2)
    a = time.time()
    n = 0
    while g.wave < 12 and g.state == "play":
        bot()
        g.step(DT)
        n += 1
    print("simulation: %.0f us per step with the autopilot (%d foes on the field at the end)" % (
        (time.time() - a) / max(1, n) * 1e6, len(g.enemies)))
    print("Self-test ok (%.1f s)" % (time.time() - t0))


def screenshot(cols=100, rows=32):
    """README picture: real play on Clockwork Yard (seed 7) by the auto-mode pilot, 245 s in: wave 10 marching in
    from all three portals while the towers hold the yard by the Wardstone, the cursor on the best tower, HUD and
    all. Quiet, no score written."""
    g = Game("campaign", 6, quiet=True, seed=7)
    g.hi = 0
    bot = Bot(g, seed=7)
    while g.state == "play" and (g.wave < 9 or len(g.enemies) < 20):
        bot()
        g.step(DT)
    for _ in range(int(6.0 / DT)):
        bot()
        g.step(DT)
    bot.goal = None
    best = max(g.towers.values(), key=lambda t: (t.branch is not None, t.level, t.spent))
    g.cx, g.cy = best.x, best.y
    return render(g, cols, rows)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--auto" in sys.argv:
        with KeyTerminal() as _term:
            run_auto(_term, 0)
    else:
        main()
