#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""ASCII ARCADE - a little collection of games for the terminal.

Pick a game with the arrow keys and press Enter; when it ends you are back here.
Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
"""
import math
import os
import random
import subprocess
import sys
import textwrap
import time

import depthwell
from arcadesound import Sound
import arcadekit
from arcadesound import load_settings, save_settings
from arcadekit import (ACCENTS, COPYRIGHT, VERSION, Canvas, Terminal, clamp, draw_title, footer, load_scores, mix, overlay, shade,
                       title_width)

HERE = os.path.dirname(os.path.abspath(__file__))

SND = Sound("arcade", {
    "move": [dict(w="square", f=660, d=0.035, v=0.35, duty=0.25)],
    "start": [dict(w="square", f=523, d=0.07, v=0.45), dict(w="square", f=784, d=0.07, v=0.45),
              dict(w="square", f=1047, d=0.2, v=0.5, duty=0.25)],
    "sound_on": [dict(w="tri", f=440, d=0.07), dict(w="tri", f=880, d=0.14)],
    "back": [dict(w="tri", f=660, f2=330, d=0.16, v=0.45)],
})

GAMES = [
    dict(file="hoverdrift.py", name="HOVERDRIFT", tag="glide over endless voxel worlds",
         info=["Four vehicles, six worlds: meadows, ice, desert,", "a volcano planet, Planet Xeno, a crystal moon.",
               "Six weapons; shoot balloons, drones and towers."],
         keys="arrows steer   V vehicle   L world   Space fire", size=(40, 12)),
    dict(file="emberfall.py", name="EMBERFALL", tag="a party role-playing adventure",
         info=["Create a hero, gather companions in a tavern,", "fight turn by turn with d20 rules and descend",
               "beneath a mountain where something is waking."],
         keys="arrows move   walk into things   f attack   ? help", size=(70, 22)),
    dict(file="blockfire.py", name="BLOCKFIRE", tag="first-person arena shooter",
         info=["The arena is sealed and the combat bots keep", "coming in waves: drones, sentinels, brutes.",
               "Textured 3D, lit floors, pixel-art robots."],
         keys="W/S move   A/D strafe   arrows turn   Space fire", size=(60, 18)),
    dict(file="deepcall.py", name="DEEPCALL", tag="a submarine alone in the dark",
         info=["Only your sonar shows the trench - and every", "ping can be heard. Find air, salvage and the",
               "Source at the bottom. Keep the deep quiet."],
         keys="arrows steer   Space ping   F focus   L lamp   E flare", size=(60, 20), score="deepcall"),
    dict(file="lightkeeper.py", name="LIGHTKEEPER", tag="one beam, many ships, a long night",
         info=["Keep the lighthouse through a stormy night:", "light the ships past the reefs, sound the horn,",
               "send the rescue boat. Alone or as two keepers."],
         keys="arrows beam   Space horn   R oil   B boat", size=(70, 22), score="lightkeeper"),
    dict(file="skyshot.py", name="SKYSHOT", tag="an artillery duel on crumbling hills",
         info=["Turn-based cannon duel on ground that breaks", "apart: craters, sliding tanks, wind. Two players",
               "at one keyboard, or alone against the computer."],
         keys="Left/Right angle  Up/Down power  Tab shell  Space fire", size=(70, 22), score="skyshot"),
    dict(file="nightdrive.py", name="NIGHTDRIVE", tag="a race against the clock, after dark",
         info=["Night racing on a winding, hilly highway:", "neon city, coast, forest, desert, mountain",
               "pass and storm. Reach every checkpoint in time."],
         keys="arrows steer   Up gas   Down brake   Esc pause", size=(70, 22), score="nightdrive"),
    dict(file="orbital.py", name="ORBITAL", tag="a calm gravity puzzle among the planets",
         info=["Set angle and power, launch the probe and let", "the planets' gravity bend its path to the dock.",
               "Moons, asteroid belts, wormholes; fewer tries."],
         keys="arrows aim/power   Space launch   R retry   N/B level", size=(70, 22), score="orbital"),
    dict(file="leafling.py", name="LEAFLING", tag="a jump'n'run with a leaf for a hat",
         info=["Run, jump, glide on your leaf and wall-jump", "through a forest canopy, crystal caves, sky",
               "ruins and an autumn storm. Find the seeds."],
         keys="arrows run   Space jump / glide   Down drop", size=(70, 22), score="leafling"),
    dict(file="stackfall.py", name="STACKFALL", tag="falling blocks, ten wide, twenty deep",
         info=["Turn and drop seven kinds of pieces, fill rows", "to melt them away. Marathon, Sprint (40 rows)",
               "and Rising, where rubble pushes up from below."],
         keys="arrows move   Up turn   Space slam   C hold", size=(40, 20), score="stackfall"),
    dict(file="depthwell.py", name="DEPTHWELL", tag="falling blocks in three dimensions",
         info=["Look down into a well and sink cube pieces.", "Turn them about all three axes, fill whole",
               "floor layers. Four well sizes, three piece sets."],
         keys="arrows move   Q/A W/S E/D turn   Space drop", size=(70, 22), score="depthwell"),
    dict(file="glimmer.py", name="GLIMMER", tag="a will-o'-wisp in a hedge maze at night",
         info=["Gather light motes in a night garden maze; sun", "blossoms turn four shadow spirits pale to catch.",
               "Eight mazes: one-way gates, fog, total dark."],
         keys="arrows move   Esc pause   ? help", size=(60, 22), score="glimmer"),
    dict(file="sporefield.py", name="SPOREFIELD", tag="stop the sporeworm before the roots",
         info=["Shoot the sporeworm winding down a night meadow:", "every hit splits it and leaves a toadstool.",
               "Jitterlegs, moths, puffballs; glowing seeds."],
         keys="arrows move   Space fire   F auto-fire", size=(60, 22), score="sporefield"),
    dict(file="scaffold.py", name="SCAFFOLD", tag="climb the tower past the Wrecker",
         info=["A runaway demolition robot holds the top of a", "skyscraper. Climb girders, belts, lifts and",
               "cranes past its drums; cut its power at night."],
         keys="arrows walk / climb   Space jump", size=(60, 22), score="scaffold"),
    dict(file="voidlance.py", name="VOIDLANCE", tag="a star fighter with a charge lance",
         info=["Charge the lance, dock the Warden pod at nose", "or tail, six crystal weapons, missiles, bits.",
               "Eight stages, eight midbosses, eight bosses."],
         keys="arrows fly   Space shoot/charge   F pod   B bomb", size=(70, 22), score="voidlance"),
    dict(file="shatterwick.py", name="SHATTERWICK", tag="a spark against walls of glass",
         info=["Bounce Wick, a living candle spark, off your", "brass tray and shatter tinted glass: 25 halls,",
               "five districts, five keepers, gifts and combos."],
         keys="arrows move   Space launch / release", size=(60, 22), score="shatterwick"),
    dict(file="wardstone.py", name="WARDSTONE", tag="rune towers against the Hollow",
         info=["Hold eight lands against the Hollow host:", "7 towers, 3 levels and 2 paths each, 10 foes,", "4 bosses, open squares your towers shape."],
         keys="arrows move   1-7 build   Space upgrade   N wave", size=(70, 22), score="wardstone"),
    dict(file="clatterbell.py", name="CLATTERBELL", tag="a silver ball on three wild tables",
         info=["Three original tables: belfry, reef and forge.", "Real ball physics, ramps, orbits, drop targets,", "spinners, kickback, multiball, missions, tilt."],
         keys="Z / M flippers   Space plunger   Up nudge", size=(60, 22), score="clatterbell"),
    dict(file="cairnward.py", name="CAIRNWARD", tag="push the scattered waystones home",
         info=["42 hand-made cairns in 7 regions:", "ice, wind tiles, plates & gates, colours;", "unlimited undo, par from a real solver."],
         keys="arrows push   U undo   R restart", size=(60, 22), score="cairnward"),
    dict(file="gemburrow.py", name="GEMBURROW", tag="dig sunstones under falling rock",
         info=["Pell digs for the warrens' lost sunstones:", "20 caves in 5 worlds + 5 intermissions,", "rocks fall and roll, moths burst to gems."],
         keys="arrows dig   Space+arrow reach   R give up", size=(60, 22), score="gemburrow"),
    dict(file="weftwar.py", name="WEFTWAR", tag="light-thread duels on a night loom",
         info=["Dye riders weave burning threads on a loom:", "cut rivals off, last one weaving wins. Two", "players or 1-3 computer riders, 7 looms."],
         keys="WASD / arrows steer   Space / Enter spur", size=(60, 22), score="weftwar"),
    dict(file="pebbleputt.py", name="PEBBLEPUTT", tag="putt a pebble round odd courses",
         info=["27 holes: a meadow, ice caverns and a", "copper foundry at night. Slopes, ramps,", "portals, gear arms; 1-4 players, scorecard."],
         keys="arrows aim/power   Space swing   Enter strike", size=(60, 22), score="pebbleputt"),
    dict(file="thatchwold.py", name="THATCHWOLD", tag="a village, one season at a time",
         info=["Every turn a season: sow, harvest, winter.", "Fields by water, mills by fields, forecasts.", "Five scenarios easy to hard, plus endless."],
         keys="arrows move   Tab pick   B build   U undo   Enter end season", size=(70, 22), score="thatchwold"),
    dict(file="fenmark.py", name="FENMARK", tag="sound the fen, mend the windows",
         info=["Probe the fen for bog-eyes without one guess:", "every fen proved solvable by logic. 22 hand-", "made leadlight panes + random, hints, auto."],
         keys="arrows move   Space probe/glass   F/X flag/lead", size=(70, 22), score="fenmark"),
    dict(file="heathshot.py", name="HEATHSHOT", tag="a shooting gallery on the heath",
         info=["Puffwings cross the heath near and far; the", "far ones score most. Eight shells, combos,", "peekers, a balloon, a windmill. Spare the sheep."],
         keys="mouse aim/click   R reload   arrows + Space", size=(60, 22), score="heathshot"),
    dict(file="breakroom.py", name="BREAKROOM", tag="rooms full of things that had it coming",
         info=["A rage room: office, kitchen, living room and", "china shop. Hammer, bat, firecracker; shards", "pile up. Free Smash with a stress bar, or 1 Min."],
         keys="mouse aim/click   1 2 3 tool   arrows + Space", size=(60, 22), score="breakroom"),
    dict(file="spanwork.py", name="SPANWORK", tag="build a bridge, then let the physics decide",
         info=["Road, wood, steel and cable on a grid, a budget,", "then real physics: mass, stiffness, load from", "green to red, beams that snap. Eight crossings."],
         keys="mouse click joints   1-4 material   Enter test", size=(60, 22), score="spanwork"),
    dict(file="solace.py", name="SOLACE", tag="patience on a green felt table",
         info=["Klondike (draw 1 or 3), Spider (1, 2 or 4", "suits) and FreeCell (numbered deals). Drag,", "click, undo, hints, auto-complete, best times."],
         keys="mouse drag/click   U undo   H hint   N new deal", size=(60, 22), score="solace"),
    dict(file="underhold.py", name="UNDERHOLD", tag="one hero, ten floors down, no second chances",
         info=["A roguelike: new floors every run, unknown", "potions and wands, 17 kinds of foes, three", "heroes, perks, permadeath. The Mawkeeper waits."],
         keys="arrows move   X explore   I items   > stairs", size=(60, 22), score="underhold"),
    dict(file="puckslide.py", name="PUCKSLIDE", tag="air hockey on a glowing table",
         info=["Real puck physics: mass, rebounds, hard swings", "make hard shots. Two players at one keyboard", "or you against the computer (easy/normal/hard)."],
         keys="W A S D left   arrows right   mouse vs computer", size=(60, 22), score="puckslide"),
]
GENRE = {"hoverdrift.py": "flight", "emberfall.py": "role-playing", "blockfire.py": "shooter", "deepcall.py": "exploration",
         "lightkeeper.py": "action", "skyshot.py": "artillery", "nightdrive.py": "racing", "orbital.py": "puzzle",
         "leafling.py": "platformer", "stackfall.py": "blocks", "depthwell.py": "3D blocks",
         "glimmer.py": "maze chase", "sporefield.py": "fixed shooter", "scaffold.py": "climber",
         "voidlance.py": "shoot 'em up", "shatterwick.py": "brick breaker",
         "wardstone.py": "tower defense", "clatterbell.py": "pinball", "cairnward.py": "box-pushing", "gemburrow.py": "cave digger", "weftwar.py": "trail duel", "pebbleputt.py": "minigolf",
         "thatchwold.py": "settlement", "fenmark.py": "logic puzzles", "heathshot.py": "shooting gallery",
         "breakroom.py": "rage room", "spanwork.py": "bridge builder",
         "solace.py": "patience", "underhold.py": "roguelike", "puckslide.py": "air hockey"}
HIDDEN = set(load_settings().get("hidden", []))     # files of games the player took off the list


def listed(all_=False):
    """Indices into GAMES of the games on the list (all of them with all_)."""
    return [i for i, g in enumerate(GAMES) if all_ or g["file"] not in HIDDEN]


def toggle_hidden(g):
    """Take a game off the list or put it back (remembered for every start). Never hides the last one."""
    if g["file"] in HIDDEN:
        HIDDEN.discard(g["file"])
    elif len(listed()) > 1:
        HIDDEN.add(g["file"])
    else:
        return False
    save_settings(hidden=sorted(HIDDEN))
    return True


HELP = [
    "ASCII ARCADE - keys",
    "",
    "Up / Down            choose a game",
    "1 - 9, 10 - %d       jump to a game (two digits: type them quickly)" % len(GAMES),
    "Enter / Space        play",
    "X                    hide the game from the list (and the start screen)",
    "V                    show all games, hidden ones too (X there: show again)",
    "M                    sound on / off",
    "G                    pixels: fine / smart / solid",
    "                     (smart and solid avoid streaks in macOS Terminal)",
    "A                    view: pixels / ASCII / mono (in a game: V)",
    "Esc / Q              quit",
    "",
    "The same in every game:",
    "Esc / P              pause / game menu (Q there: quit,",
    "                     M there: sound on / off, V: view)",
    "V                    view: pixels / ASCII art / mono ASCII",
    "                     (FENMARK's window panes: in the pause menu)",
    "?                    help with all of the game's keys",
    "Enter / Space        confirm",
    "Arrows / WASD        move, choose",
    "",
    "ASCII ARCADE %s  %s" % (VERSION, COPYRIGHT),
]
ACCENT = [(236, 84, 84), (244, 150, 56), (236, 212, 70), (130, 214, 76), (56, 200, 160), (60, 170, 236),
          (100, 110, 240), (170, 96, 236), (226, 90, 200)]


# --- little moving previews, one per game ---------------------------------------------------------------
def thumb_hover(cv, x, y, w, h, t):
    for yy in range(h):
        k = yy / h
        if k < 0.55:
            c = mix((58, 116, 204), (178, 210, 238), k / 0.55)
        else:
            c = mix((60, 150, 70), (30, 90, 40), (k - 0.55) / 0.45)
        cv.rect(x, y + yy, w, 1, c)
    for xx in range(w):  # two mountain ranges scrolling past
        a = (xx + t * 6) * 0.11
        m = h * (0.38 + 0.08 * math.sin(a) + 0.05 * math.sin(a * 2.7 + 1))
        cv.rect(x + xx, y + int(m), 1, int(h * 0.55 - m) + 1, (110, 120, 150))
        b = (xx + t * 14) * 0.07
        m2 = h * (0.5 + 0.06 * math.sin(b * 1.3) + 0.04 * math.sin(b * 3.1))
        cv.rect(x + xx, y + int(m2), 1, int(h * 0.62 - m2) + 1, (70, 120, 70))
    sx, sy = x + w * 0.75, y + h * 0.18
    for yy in range(-3, 4):
        for xx in range(-3, 4):
            if xx * xx + yy * yy <= 9:
                cv.set(sx + xx, sy + yy, (255, 246, 210))
    cx, cy = x + w // 2 + int(math.sin(t * 0.8) * w * 0.1), y + int(h * 0.74 + math.sin(t * 2) * 1)
    cv.rect(cx - 5, cy, 11, 2, (214, 64, 52))
    cv.rect(cx - 3, cy - 1, 7, 1, (196, 202, 214))
    cv.rect(cx - 1, cy - 2, 3, 1, (90, 176, 226))
    cv.rect(cx - 6, cy + 2, 13, 1, (62, 64, 76))
    cv.set(cx - 4, cy + 3, (150, 220, 255) if int(t * 10) % 2 else (210, 245, 255))
    cv.set(cx + 4, cy + 3, (150, 220, 255) if int(t * 10) % 2 else (210, 245, 255))


def thumb_ember(cv, x, y, w, h, t):
    for yy in range(h):
        cv.rect(x, y + yy, w, 1, mix((10, 6, 12), (40, 14, 10), yy / h))
    # a mountain with a glowing heart
    for xx in range(w):
        d = abs(xx - w / 2) / (w / 2)
        top = int(h * (0.3 + 0.55 * d))
        cv.rect(x + xx, y + top, 1, h - top, (28, 20, 24))
    rnd = random.Random(int(t * 12))
    for i in range(40):  # flames
        fx = x + w / 2 + rnd.gauss(0, w * 0.08)
        fy = y + h * 0.82 - rnd.random() ** 2 * h * 0.45
        hot = 1 - (y + h * 0.82 - fy) / (h * 0.45)
        cv.set(fx, fy, mix((255, 230, 140), (200, 40, 20), 1 - hot))
    cv.rect(x + int(w * 0.12), y + int(h * 0.66), 3, 6, (90, 70, 60))  # a tiny hero with a torch
    cv.set(x + int(w * 0.12) + 1, y + int(h * 0.62), (255, 180, 80) if int(t * 8) % 2 else (255, 230, 140))


def thumb_stack(cv, x, y, w, h, t):
    cv.rect(x, y, w, h, (14, 15, 26))
    k = max(2, min(w // 10, h // 14))
    bw = 10 * k
    ox = x + (w - bw) // 2
    rnd = random.Random(5)
    cols = ACCENT
    rows = h // k
    for r in range(rows - 5, rows):
        for c in range(10):
            if rnd.random() < 0.8 and c != 7:
                col = rnd.choice(cols)
                cv.rect(ox + c * k, y + r * k, k, k, shade(col, 0.6))
                cv.rect(ox + c * k, y + r * k, k - 1, k - 1, col)
    fall = int(t * 4) % max(1, rows - 6)
    for dx, dy in ((0, 0), (1, 0), (2, 0), (1, 1)):
        cv.rect(ox + (3 + dx) * k, y + (fall + dy) * k, k - 1, k - 1, (206, 92, 206))
    cv.frame(ox - 1, y, bw + 2, h, (64, 72, 112))


def thumb_depth(cv, x, y, w, h, t):
    cv.rect(x, y, w, h, (6, 6, 14))
    g = depthwell.Well((4, 4, 8), depthwell.FLAT)
    rnd = random.Random(2)
    for z in range(5, 8):
        for yy in range(4):
            for xx in range(4):
                g.cell[z][yy][xx] = rnd.random() < 0.9 - (7 - z) * 0.25
    v = depthwell.View(g, x + w / 2, y + h / 2, min(w, h) - 2)
    depthwell.draw_well(cv, v)
    depthwell.draw_cubes(cv, v)
    pz = int(t * 1.5) % 5
    depthwell.wire(cv, v, [(1, 1, pz), (2, 1, pz), (1, 2, pz)], (240, 246, 255))


_BF = []


def thumb_block(cv, x, y, w, h, t):
    """A live look around the BLOCKFIRE arena."""
    if not _BF:
        import blockfire
        blockfire.BEST_FILE = os.devnull
        g = blockfire.Game(seed=1)
        _BF.append(blockfire.Renderer(g))
    r = _BF[0]
    buf = r.scene(w, h, cam=(8.0 - math.cos(t * 0.08) * 6, 19.5, math.sin(t * 0.3) * 0.16))
    for yy in range(h):
        if 0 <= y + yy < cv.H:
            cv.px[y + yy][x:x + w] = buf[yy][:max(0, min(w, cv.W - x))]


_DC = []


def thumb_deep(cv, x, y, w, h, t):
    """DEEPCALL's title cave, pinged every few seconds, squeezed into the preview box."""
    if not _DC:
        import deepcall
        _DC.append(deepcall.TitleDemo())
        _DC.append(t)
    demo = _DC[0]
    dt = min(0.1, max(0.0, t - _DC[1]))
    _DC[1] = t
    import deepcall
    d = demo.d
    if d.t - demo.last > 3.0:
        demo.last = d.t
        d.power = 100
        d.ping(False)
    saved = (d.x, d.y, d.oxygen, d.hull)
    d.update(dt)
    d.x, d.y, d.oxygen, d.hull = saved
    d.vx = d.vy = d.noise = 0.0
    d.over = False
    d.msgs = []
    sub = deepcall.render(d, w, (h + 1) // 2, title_mode=True)
    for yy in range(h):
        if 0 <= y + yy < cv.H:
            cv.px[y + yy][x:x + w] = sub.px[yy][:max(0, min(w, cv.W - x))]


_LK = []


def thumb_light(cv, x, y, w, h, t):
    """A little stretch of LIGHTKEEPER coast with the beam sweeping round."""
    import lightkeeper
    if not _LK or _LK[0].n.W != w:
        demo = lightkeeper.TitleDemo(w, (h + 1) // 2 + 1)
        _LK[:] = [demo, t]
    demo = _LK[0]
    n = demo.n
    dt = min(0.1, max(0.0, t - _LK[1]))
    _LK[1] = t
    n.spin, n.oil = 0.55, 100
    n.update(dt)
    n.msgs, n.lives, n.over, n.dawn = [], 3, False, False
    if n.t > n.length * 0.6:
        n.t = 10
        n.schedule = sorted(n.rnd.uniform(11, 40) for _ in range(4))
        n.ships = [s for s in n.ships if s.state == "sailing"]
    sub = lightkeeper.render(n, demo.p, w, (h + 1) // 2, title_mode=True)
    for yy in range(h):
        if 0 <= y + yy < cv.H:
            cv.px[y + yy][x:x + w] = sub.px[yy][:max(0, min(w, cv.W - x))]


def thumb_sky(cv, x, y, w, h, t):
    import skyshot
    skyshot.preview(cv, x, y, w, h, t)


_ND, _OR, _LF = [], [], []


def blit_scene(cv, x, y, w, h, sub):
    for yy in range(h):
        if 0 <= y + yy < cv.H:
            cv.px[y + yy][x:x + w] = sub.px[yy][:max(0, min(w, cv.W - x))]


def thumb_night(cv, x, y, w, h, t):
    """NIGHTDRIVE's autopilot on the road."""
    import nightdrive
    if not _ND:
        _ND[:] = [nightdrive.TitleDemo(), t]
    dt = min(0.1, max(0.0, t - _ND[1]))
    _ND[1] = t
    blit_scene(cv, x, y, w, h, _ND[0].scene(w, (h + 1) // 2, dt))


def thumb_orbital(cv, x, y, w, h, t):
    """A probe looping round ORBITAL's ringed planet."""
    import orbital
    if not _OR:
        _OR[:] = [orbital.TitleDemo(), t]
    dt = min(0.1, max(0.0, t - _OR[1]))
    _OR[1] = t
    blit_scene(cv, x, y, w, h, _OR[0].scene(w, (h + 1) // 2, dt))


def thumb_leaf(cv, x, y, w, h, t):
    """Leafling running and gliding through LEAFLING's four worlds."""
    import leafling
    if not _LF:
        _LF[:] = [leafling.TitleDemo(), t]
    dt = min(0.1, max(0.0, t - _LF[1]))
    _LF[1] = t
    blit_scene(cv, x, y, w, h, _LF[0].scene(w, (h + 1) // 2, dt))


_DEMOS = {}


def thumb_demo(module):
    """A preview from a game's own TitleDemo (scene(cols, rows, dt) -> Canvas)."""
    def thumb(cv, x, y, w, h, t):
        if module not in _DEMOS:
            _DEMOS[module] = [__import__(module).TitleDemo(), t]
        d = _DEMOS[module]
        dt = min(0.1, max(0.0, t - d[1]))
        d[1] = t
        rows = (h + 1) // 2
        try:
            sub = d[0].scene(w, rows, dt)
        except Exception:          # too small for this game's scene: draw it bigger and shrink it into the box
            bw, br = max(w, 48), max(rows, 16)
            big = d[0].scene(bw, br, 0.0)
            sub = Canvas(w, rows)
            sub.px = [[big.px[min(big.H - 1, int((yy + 0.5) * big.H / (rows * 2)))][min(big.W - 1, int((xx + 0.5) * bw / w))]
                       for xx in range(w)] for yy in range(rows * 2)]
        blit_scene(cv, x, y, w, h, sub)
    return thumb


THUMBS = {"nightdrive.py": thumb_night, "orbital.py": thumb_orbital, "leafling.py": thumb_leaf, "skyshot.py": thumb_sky, "lightkeeper.py": thumb_light, "deepcall.py": thumb_deep, "hoverdrift.py": thumb_hover, "emberfall.py": thumb_ember, "stackfall.py": thumb_stack,
          "depthwell.py": thumb_depth, "blockfire.py": thumb_block, "glimmer.py": thumb_demo("glimmer"),
          "sporefield.py": thumb_demo("sporefield"), "scaffold.py": thumb_demo("scaffold"),
          "voidlance.py": thumb_demo("voidlance"), "shatterwick.py": thumb_demo("shatterwick"),
          "wardstone.py": thumb_demo("wardstone"), "clatterbell.py": thumb_demo("clatterbell"), "cairnward.py": thumb_demo("cairnward"), "gemburrow.py": thumb_demo("gemburrow"), "weftwar.py": thumb_demo("weftwar"), "pebbleputt.py": thumb_demo("pebbleputt"),
          "thatchwold.py": thumb_demo("thatchwold"), "fenmark.py": thumb_demo("fenmark"),
          "heathshot.py": thumb_demo("heathshot"), "breakroom.py": thumb_demo("breakroom"),
          "spanwork.py": thumb_demo("spanwork"), "solace.py": thumb_demo("solace"),
          "underhold.py": thumb_demo("underhold"), "puckslide.py": thumb_demo("puckslide")}



def _safe(thumb):
    """A preview that fails (a bug at some odd window size) leaves its box dark instead of ending the arcade."""
    def run(cv, x, y, w, h, t):
        try:
            thumb(cv, x, y, w, h, t)
        except Exception:
            pass
    return run


THUMBS = {k: _safe(v) for k, v in THUMBS.items()}


def record_line(g):
    if "score" not in g:
        return ""
    rec = load_scores().get(g["score"], {})
    if not rec:
        return "no records yet"
    if g["score"] == "thatchwold":
        won = sum(1 for k in rec if k.startswith("s") and k[1:].isdigit())
        return "best: %d of 5 scenarios won%s" % (won, (", endless %s" % rec["endless"]) if "endless" in rec else "")
    if g["score"] == "fenmark":
        def mmss(v):
            return "%d:%02d" % (v // 60, v % 60)
        parts = ["%s %s" % (k, mmss(rec[k])) for k in ("Reedbed", "Peat Meadow", "Deep Fen") if k in rec]
        return "best: " + ", ".join(parts + ["%d of 22 panes" % rec.get("panes", 0)])
    if g["score"] == "breakroom":
        return "best: %s € damage in One Minute" % "{:,}".format(rec.get("One Minute", 0)).replace(",", ".")
    if g["score"] == "solace":
        wins = sum(v for k, v in rec.items() if k.endswith(" wins"))
        times = {k[:-5]: v for k, v in rec.items() if k.endswith(" time")}
        best = ", ".join("%s %d:%02d" % (k, v // 60, v % 60) for k, v in sorted(times.items())[:3])
        return "best: %d games won%s" % (wins, (", " + best) if best else "")
    if g["score"] == "puckslide":
        return "wins vs computer: " + ", ".join("%s %d" % (d, rec[d]) for d in ("easy", "normal", "hard") if d in rec)
    if g["score"] == "spanwork":
        return "best: %d of 8 crossings built within budget" % len(rec)
    if g["score"] == "cairnward":
        return "best: %d of 42 cairns set, %d at par" % (rec.get("solved", 0), rec.get("par", 0))
    if g["score"] == "leafling":
        done = sum(1 for k in rec if k.endswith(" time"))
        seeds = sum(bin(v).count("1") for k, v in rec.items() if k.endswith(" seeds"))
        return "best: %d of 12 levels done, %d of 36 seeds" % (done, seeds)
    parts = []
    for mode, v in sorted(rec.items()):
        parts.append("%s %s" % (mode, ("%d:%05.2f" % (v // 60, v % 60)) if mode == "Sprint" else v))
    return "best: " + ",  ".join(parts[:3])


LIST_BG = ((18, 16, 34), (24, 21, 44))      # alternating row bands keep entries apart without extra lines
DIM = (150, 150, 178)                        # secondary text: >= 4.5:1 on the list bands
BADGE_BG = (44, 40, 76)
PANEL, PANEL_FG = (16, 14, 30), (222, 222, 234)                         # backing for the details text, so stars never run through it


def badge(i):
    """The game's number: typed as one digit, or two digits in quick succession (1 then 2 = game 12)."""
    return str(i + 1)


DIGIT_GAP = 0.8      # seconds in which a second digit joins the first one


def accent(g):
    top, bottom = ACCENTS.get(g["name"], ((240, 240, 250), (160, 160, 190)))
    return mix(top, bottom, 0.3)


def draw_logo(cv, cols, t):
    """ASCII ARCADE in block letters; on narrow windows the two words close up so the logo still fits."""
    wave = [ACCENT[(i + int(t * 3)) % len(ACCENT)] for i in range(12)]
    k = 3
    while k > 1 and title_width("ASCII ARCADE", k) > cols - 4:
        k -= 1
    if title_width("ASCII ARCADE", k) <= cols - 2:
        draw_title(cv, "ASCII ARCADE", (cols - title_width("ASCII ARCADE", k)) // 2, 3, k, wave)
    else:
        w1, w2, gap = title_width("ASCII", 1), title_width("ARCADE", 1), 2
        x = max(0, (cols - (w1 + gap + w2)) // 2)
        draw_title(cv, "ASCII", x, 3, 1, wave[:5])
        draw_title(cv, "ARCADE", x + w1 + gap, 3, 1, wave[6:])
    return k


def render(cols, rows, sel, t, note, help_=False, all_=False):
    """The menu. sel is an index into GAMES; the list shows the games not hidden (all_: every game)."""
    view_ = listed(all_)
    if sel not in view_:
        view_ = sorted(set(view_) | {sel})
    cv = Canvas(cols, rows)
    cv.vgradient((8, 6, 18), (24, 10, 30))
    rnd = random.Random(11)
    for i in range(90):  # drifting stars
        sx = (rnd.uniform(0, cols) + t * rnd.uniform(1, 4)) % cols
        sy = rnd.uniform(0, cv.H)
        cv.set(sx, sy, mix((60, 60, 90), (220, 220, 255), rnd.random() * (0.6 + 0.4 * math.sin(t * 2 + i))))
    k = draw_logo(cv, cols, t)
    top = (3 + 5 * k) // 2 + 2
    cv.center(top, "a little game collection for your terminal", (180, 180, 204))
    # list on the left, preview and details on the right
    lw = 46 if cols >= 116 else 40 if cols >= 96 else 34
    tw2 = min(60, cols - lw - 8)
    lx = max(2, (cols - lw - tw2 - 4) // 2)
    rx = lx + lw + 4
    ly = top + 3 if rows >= 30 else top + 2
    # tighter list on small windows: names with taglines and gaps, then without gaps, then names only
    n = len(view_)
    step = next((k for k in (3, 2) if ly + k * n < rows - 1), 1)
    fit = max(1, (rows - 2 - ly) // step)               # rows for the list; more games scroll
    pos = view_.index(sel)
    first = clamp(pos - fit // 2, 0, max(0, n - fit))
    for j, i in enumerate(view_[first:first + fit]):
        g = GAMES[i]
        r = ly + j * step
        on = i == sel
        off = g["file"] in HIDDEN
        acc = accent(g)
        band = acc if on else LIST_BG[j % 2]
        genre = "hidden" if off else GENRE.get(g["file"], "")
        b = badge(first + j)
        cv.put(lx, r, " " * lw, (14, 14, 20), band)
        cv.put(lx + 1, r, b.center(4), acc if on else (220, 220, 236), (14, 14, 22) if on else BADGE_BG)
        cv.put(lx + 6, r, g["name"], (14, 14, 20) if on else (120, 120, 140) if off else (236, 236, 246), band)
        if genre and lw - 6 - len(g["name"]) - len(genre) > 3:
            cv.put(lx + lw - len(genre) - 2, r, genre, (255, 140, 110) if off else shade(acc, 0.32) if on else DIM,
                   band)
        if step > 1:
            tb = mix(LIST_BG[i % 2], acc, 0.18) if on else LIST_BG[i % 2]
            cv.put(lx, r + 1, " " * lw, (14, 14, 20), tb)
            cv.put(lx + 6, r + 1, g["tag"][:lw - 7], (240, 240, 248) if on else DIM, tb)
            if on:
                cv.put(lx, r + 1, " ", acc, acc)
        if step > 2 and j < n - 1:
            cv.put(lx, r + 2, " " * lw, (14, 14, 20), (14, 12, 28))
    if first > 0:
        cv.put(lx + lw - 3, ly - 1, " ^ ", (200, 200, 220), (14, 12, 28))
    if first + fit < n:
        cv.put(lx + lw - 3, ly + fit * step - (1 if step > 2 else 0), " v ", (200, 200, 220), (14, 12, 28))
    g = GAMES[sel]
    acc = accent(g)
    list_bot = ly + min(n, fit) * step - (1 if step > 2 else 0)
    th = max(8, min(2 * (rows - ly - 11), 30, tw2 * 9 // 16 * 2 // 2))
    if tw2 >= 20:
        THUMBS[g["file"]](cv, rx, ly * 2, tw2, th, t)
        cv.frame(rx - 1, ly * 2 - 1, tw2 + 2, th + 2, shade(acc, 0.7))
        r = ly + th // 2 + 2
        bottom = max(list_bot, rows - 3)
        lines = []                                           # (text, fg, indent) in priority order of the space
        mc, mr = g["size"]
        name = g["name"]
        genre = GENRE.get(g["file"], "")
        lines.append(("%s%s" % (name, ("  -  " + genre) if genre and len(name) + len(genre) + 5 <= tw2 else ""), None))
        if cols < mc or rows < mr:
            warn = "needs a %dx%d window (now %dx%d)" % (mc, mr, cols, rows)
            if len(warn) > tw2:
                warn = "needs %dx%d (now %dx%d)" % (mc, mr, cols, rows)
            lines.append((warn[:tw2], (255, 130, 110)))
        info = textwrap.wrap(" ".join(g["info"]), tw2)
        keys = textwrap.wrap(g["keys"] if tw2 >= 44 else g["keys"].replace("   ", "  "), tw2 - 6)
        rec = record_line(g)
        room = bottom - r
        extra = len(keys) + 1 + (2 if rec else 0)
        if len(lines) + len(info) + extra > room:            # small window: shorter description first
            info = info[:max(1, room - len(lines) - extra)]
        lines += [(l, (222, 222, 234)) for l in info]
        lines.append(("", None))
        for j, l in enumerate(keys):
            lines.append((("keys  " if j == 0 else "      ") + l, "keys"))
        if rec:
            lines += [("", None), (rec[:tw2], (236, 212, 70))]
        shown = lines[:max(0, room + 1)]
        while shown and not shown[-1][0]:
            shown.pop()
        for j in range(len(shown) + 2):
            cv.put(rx - 1, r - 1 + j, " " * (tw2 + 2), PANEL_FG, PANEL)
        for j, (l, fg) in enumerate(shown):
            if j == 0:
                cv.put(rx, r, name, acc, PANEL)
                if len(l) > len(name):
                    cv.put(rx + len(name), r, l[len(name):], DIM, PANEL)
            elif fg == "keys":
                cv.put(rx, r + j, l[:6], DIM, PANEL)
                cv.put(rx + 6, r + j, l[6:], (206, 208, 230), PANEL)
            elif fg:
                cv.put(rx, r + j, l, fg, PANEL)
    if note:
        cv.center(rows - 3, " %s " % note, (14, 14, 20), (255, 150, 100))
    snd = SND.label().lower()
    pix = arcadekit.PIXEL_MODE
    view = arcadekit.VIEW_NAMES[arcadekit.VIEW_MODE]
    hide = "X %s" % ("show" if g["file"] in HIDDEN else "hide")
    vall = "V %s" % ("hide hidden" if all_ else "all (%d hidden)" % len(HIDDEN) if HIDDEN else "all")
    if cols >= 142:
        footer(cv, "Up/Down choose   Enter play   %s   %s   M %s   G pixels: %s   A view: %s   ? help   Esc quit"
               % (hide, vall, snd, pix, view))
    elif cols >= 130:
        footer(cv, "Up/Down choose   Enter play   %s   %s   M %s   G pixels: %s   ? help   Esc quit" % (hide, vall, snd, pix))
    elif cols >= 96:
        footer(cv, "Up/Down choose   Enter play   %s   %s   M %s   ? help   Esc quit" % (hide, vall, snd))
    else:
        footer(cv, "Enter play  %s  %s  ? help  Esc quit" % (hide, vall.split(" (")[0]))
    if TERMINAL_APP_HINT[0] and not arcadekit.SOLID_PIXELS and not help_:
        cv.center(rows - 2, " Streaky pixels in macOS Terminal? Press G for smart pixels. ", (20, 16, 10), (236, 200, 110))
    sig = "v%s" % VERSION
    if cols >= 150:
        cv.put(16, rows - 1, sig, (110, 114, 144), (12, 10, 22))
    if help_:
        overlay(cv, HELP)
    return cv


def render_start(cols, rows, t, hi, games=None):
    """The start screen: the big logo over a wall of all games playing at once; hi is the highlighted one."""
    cv = Canvas(cols, rows)
    cv.vgradient((6, 4, 16), (26, 10, 34))
    rnd = random.Random(7)
    for i in range(140):  # a star field rushing past
        sp = rnd.uniform(2, 10)
        sx = (rnd.uniform(0, cols) - t * sp) % cols
        sy = rnd.uniform(0, cv.H)
        cv.set(sx, sy, mix((50, 50, 80), (230, 230, 255), min(1.0, sp / 10) * (0.7 + 0.3 * math.sin(t * 3 + i))))
    # the logo, with a band of light sweeping across it
    wave = [ACCENT[(i + int(t * 3)) % len(ACCENT)] for i in range(12)]
    k = 3
    while k > 1 and title_width("ASCII ARCADE", k) > cols - 4:
        k -= 1
    lw = title_width("ASCII ARCADE", k)
    lx, ly = (cols - lw) // 2, 2
    sweep = (t * 0.6) % 1.6 - 0.3
    cols_lit = []
    for n in range(12):
        f = max(0.0, 1 - abs((n + 0.5) / 12 - sweep) * 5)
        cols_lit.append(mix(wave[n], (255, 255, 255), 0.55 * f))
    if lw <= cols - 2:
        draw_title(cv, "ASCII ARCADE", lx + 1, ly + 1, k, [(10, 6, 20)])     # drop shadow
        draw_title(cv, "ASCII ARCADE", lx, ly, k, cols_lit)
    else:
        draw_logo(cv, cols, t)
    top = (ly + 5 * k) // 2 + 2
    games = [GAMES[i] for i in listed()] if games is None else games
    cv.center(top, " %d games for your terminal " % len(games), (200, 200, 222), (12, 8, 24))
    # the wall of games: every preview running live, names underneath
    n = len(games)
    nc = (5 if n <= 15 else 6) if cols >= 90 else 3      # three rows on a wide window
    nr = (n + nc - 1) // nc
    gap = 2
    tw = (cols - 6 - gap * (nc - 1)) // nc
    avail = rows - top - 7                       # text rows left for the wall (info, prompt and footer below)
    cell = avail // nr                           # text rows per wall row: preview, name, gap
    th = min(2 * (cell - 3), tw * 9 // 16)       # preview height in pixels
    th -= th % 2                                 # whole text rows (the 3D previews need an even height)
    x0 = (cols - (tw * nc + gap * (nc - 1))) // 2
    y0 = top + 2 + max(0, (avail - nr * (th // 2 + 3)) // 2)     # the wall sits in the middle of the free space
    if th >= 6:
        for i, g in enumerate(games):
            c, r = i % nc, i // nc
            in_row = min(nc, n - r * nc)                 # an unfinished last row sits in the middle
            x = x0 + (nc - in_row) * (tw + gap) // 2 + c * (tw + gap)
            row = y0 + r * (th // 2 + 3)
            acc = accent(g)
            on = i == hi
            sub = Canvas(tw, th // 2)                # each preview on its own canvas, so none spills over
            THUMBS[g["file"]](sub, 0, 0, tw, th, t)
            blit_scene(cv, x, row * 2, tw, th, sub)
            if not on:                           # the others a little dimmer, so the eye finds the highlight
                for yy in range(row * 2, row * 2 + th):
                    line = cv.px[yy]
                    for xx in range(x, x + tw):
                        line[xx] = mix(line[xx], (12, 8, 24), 0.25)
            cv.frame(x - 1, row * 2 - 1, tw + 2, th + 2, acc if on else shade(acc, 0.45))
            label = "%d %s" % (i + 1, g["name"])
            lab = " %s " % label[:tw - 2]
            cv.put(x + max(0, (tw - len(lab)) // 2), row + th // 2 + 1, lab, (16, 12, 24) if on else (190, 190, 210),
                   acc if on else (14, 10, 26))
        info_row = y0 + nr * (th // 2 + 3)
    else:                                        # small window: just the names
        per = (n + 1) // 2
        for i, g in enumerate(games):
            c, r = i // per, i % per
            cv.put(cols // 2 - 22 + c * 24, y0 + r, " %2d %-12s" % (i + 1, g["name"]),
                   accent(g) if i == hi else (170, 170, 196), (14, 10, 26))
        info_row = y0 + per + 1
    g = games[hi % n]
    line = "%s  -  %s" % (g["name"], g["tag"])
    cv.center(min(info_row, rows - 4), " %s " % line[:cols - 4], accent(g), (14, 10, 26))
    if int(t * 1.6) % 2 == 0:
        cv.center(rows - 2, "  PRESS ANY KEY  ", (16, 12, 24), (236, 212, 70))
    if cols >= 100:
        cv.put(cols - len(COPYRIGHT) - 2, rows - 2, COPYRIGHT, (96, 96, 124), (16, 8, 30))
    footer(cv, "Enter play %s   Space / any key: to the menu   Esc quit" % g["name"])
    if cols >= 110:
        cv.put(16, rows - 1, "v%s" % VERSION, (110, 114, 144), (12, 10, 22))
    return cv


def start_screen():
    """Shown once when the arcade opens. Returns (selected game, play it now?) or None to quit."""
    with Terminal() as term:
        t0 = time.time()
        while True:
            cols, rows = term.size()
            if cols < 60 or rows < 20:
                term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (60x20).")
                for k in term.keys(0.3):
                    if k in ("q", "esc"):
                        return None
                continue
            t = time.time() - t0
            view_ = listed()
            hi = int(t / 2.2) % len(view_)
            term.write(render_start(cols, rows, t, hi).emit())
            for k in term.keys(1 / 20):
                if k in ("q", "esc"):
                    return None
                if k == "enter":
                    SND.play("start")
                    return view_[hi], True
                SND.play("move")
                return view_[hi], False


def menu(sel, note):
    with Terminal() as term:
        t0 = time.time()
        help_ = False
        all_ = False                 # V: the hidden games are listed too
        digit = (None, 0.0)          # the last digit typed and when
        while True:
            cols, rows = term.size()
            if cols < 60 or rows < 20:
                term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (60x20).")
                term.keys(0.3)
                continue
            view_ = listed(all_)
            if sel not in view_:
                sel = min(view_, key=lambda i: abs(i - sel))
            term.write(render(cols, rows, sel, time.time() - t0, note, help_, all_).emit())
            for k in term.keys(1 / 20):
                note = ""
                if help_:            # any key closes the help
                    help_ = False
                    continue
                if k == "?":
                    help_ = True
                elif k in ("q", "esc"):
                    SND.play("back")
                    return None
                elif k == "m":
                    if SND.toggle():
                        SND.play("sound_on")
                elif k == "g":
                    set_pixels({"fine": "smart", "smart": "solid"}.get(arcadekit.PIXEL_MODE, "fine"))
                    SND.play("move")
                elif k == "a":
                    arcadekit.cycle_view()
                    SND.play("move")
                elif k == "x":
                    g = GAMES[sel]
                    if toggle_hidden(g):
                        SND.play("back" if g["file"] in HIDDEN else "move")
                        note = ("%s hidden - V shows all games" % g["name"]) if g["file"] in HIDDEN and not all_ else ""
                        if g["file"] in HIDDEN and not all_:   # it left the list: move on to a neighbour
                            rest = listed()
                            sel = next((i for i in rest if i > sel), rest[-1])
                    else:
                        note = "the last game stays on the list"
                    view_ = listed(all_)
                elif k == "v":
                    all_ = not all_
                    SND.play("move")
                    view_ = listed(all_)
                pos = view_.index(sel) if sel in view_ else 0
                if k in ("up", "w", "k"):
                    sel = view_[(pos - 1) % len(view_)]
                    SND.play("move")
                elif k in ("down", "s", "j", "tab"):
                    sel = view_[(pos + 1) % len(view_)]
                    SND.play("move")
                elif k in tuple("0123456789"):
                    now = time.time()
                    prev, when = digit
                    n = int(k)
                    if prev is not None and now - when < DIGIT_GAP and 1 <= prev * 10 + n <= len(view_):
                        n = prev * 10 + n                 # second digit: 1 then 2 = game 12
                        digit = (None, 0.0)
                    else:
                        digit = (n, now)
                        if n == 0:
                            n = 10                        # 0 alone: game 10, as before
                    if 1 <= n <= len(view_):
                        sel = view_[n - 1]
                        SND.play("move")
                elif k in ("enter", " "):
                    SND.play("start")
                    return sel


USAGE = """usage: arcade [GAME | --list | --version | --help | --pixels fine|smart|solid | --view pixels|ascii|mono]

Without arguments the ASCII ARCADE menu opens. With a game name that game starts straight away,
for example:  arcade stackfall

--pixels fine    two pixels per cell with half-blocks (the default; sharp in WezTerm, iTerm2, kitty, Ghostty)
--pixels smart   half-blocks only where the two pixels clearly differ; gradients and flat areas become one
                 colour per cell: far fewer streaks in macOS Terminal.app, almost the full detail
--pixels solid   one pixel per cell, background colour only: no streaks at all, but coarse
The choice is remembered for every game (also: G in the menu; ARCADE_PIXELS=... for one run).

--view pixels    the pictures as half-block pixels (the default)
--view ascii     real ASCII art: every pixel pair becomes a coloured character ( .:-=+*#%@ and edges)
--view mono      the same in one colour, plain ASCII
The choice is remembered for every game (also: A in the menu, V in any game and its pause menu;
ARCADE_VIEW=... for one run).
"""

# in macOS Terminal.app, until the player has chosen a pixel style once, the menu suggests solid pixels
TERMINAL_APP_HINT = [os.environ.get("TERM_PROGRAM") == "Apple_Terminal" and "pixels" not in load_settings()
                     and not os.environ.get("ARCADE_PIXELS")]


def set_pixels(mode):
    """Switch the pixel style (fine / smart / solid) for the menu now and for every game started from here on."""
    arcadekit.PIXEL_MODE = mode
    arcadekit.SOLID_PIXELS = mode != "fine"
    save_settings(pixels=mode)
    os.environ.pop("ARCADE_PIXELS", None)
    TERMINAL_APP_HINT[0] = False


def run_game(g):
    code = subprocess.call([sys.executable, os.path.join(HERE, g["file"])], cwd=HERE)
    arcadekit.VIEW_MODE = arcadekit._view_mode()      # the game may have switched the view (V)
    return code


def cli(args):
    """Command line: returns an exit code, or None to open the menu."""
    if not args:
        return None
    a = args[0].lower()
    if a in ("-h", "--help", "help"):
        print(USAGE)
    elif a in ("-v", "-V", "--version", "version"):
        print("ASCII ARCADE %s  %s" % (VERSION, COPYRIGHT))
    elif a in ("--pixels", "pixels"):
        mode = args[1].lower() if len(args) > 1 else ""
        if mode not in ("fine", "smart", "solid"):
            print("pixels: %s   (arcade --pixels fine | smart | solid)" % arcadekit.PIXEL_MODE)
        else:
            set_pixels(mode)
            print("pixels: %s (remembered for every game)" % mode)
    elif a in ("--view", "view"):
        mode = args[1].lower() if len(args) > 1 else ""
        if mode not in arcadekit.VIEWS:
            print("view: %s   (arcade --view pixels | ascii | mono)" % arcadekit.VIEW_MODE)
        else:
            arcadekit.set_view(mode)
            print("view: %s (remembered for every game)" % mode)
    elif a in ("--list", "list"):
        for g in GAMES:
            print("%-12s %s" % (g["name"].lower(), g["tag"]))
    else:
        g = next((g for g in GAMES if g["name"].lower() == a or g["file"] == a), None)
        if g is None:
            print("unknown game %r - try: arcade --list" % args[0], file=sys.stderr)
            return 2
        return run_game(g)
    return 0


def main():
    sel, note = 0, ""
    first = start_screen()
    if first is None:
        return
    sel, play = first
    while True:
        if play:
            play = False
            g = GAMES[sel]
            code = run_game(g)
            note = "" if code == 0 else "%s ended unexpectedly (exit code %d)" % (g["name"], code)
        sel = menu(sel, note)
        if sel is None:
            return
        g = GAMES[sel]
        t = time.time()
        code = run_game(g)
        note = "" if code == 0 or time.time() - t > 3 else "%s ended unexpectedly (exit code %d)" % (g["name"], code)


if __name__ == "__main__":
    rc = cli(sys.argv[1:])
    if rc is not None:
        sys.exit(rc)
    try:
        main()
    except KeyboardInterrupt:
        pass
