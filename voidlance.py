#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""VOIDLANCE - a side-scrolling star fighter with a charge lance.

Fly the Voidlance through eight stages, from an orbital wreck yard to the Null Citadel. Hold fire to charge the
lance (three levels and an overcharged nova), catch the Warden pod and dock it at your nose or your tail, feed
it weapon crystals (six colours, three levels each), add missiles, crawler bombs, orbiting bits, shields and
smart bombs. Every stage scrolls through its own caves, walls and machines and ends with a midboss and a
multi-phase boss.

Keys: arrows / WASD fly, Space shoot (hold to charge in terminals with the kitty keyboard protocol),
C charge on / release, X rapid fire, F launch / recall the pod, B smart bomb, Esc / P pause, ? help.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
Self-test:  python3 voidlance.py --selftest
"""
import math
import random
import sys
import time

from arcadekit import (AUTO_LABEL, PAUSE_LINES, AutoMode, Canvas, HeldKeys, KeyTerminal, clamp, load_scores, mix,
                       overlay, shade, shared_key, submit, title_screen)
from arcadesound import Sound

GAME = "voidlance"
DT = 1 / 60                  # fixed simulation step
FW, FH = 112, 64             # the logical play field; the window only changes how big it is drawn
MIN_COLS, MIN_ROWS = 70, 22
TAU = math.pi * 2
DIFFS = ["easy", "normal", "hard"]
DIFF = {  # lives, bombs, enemy fire rate, bullet speed, enemy hp
    "easy": dict(lives=5, bombs=3, fire=0.6, bspeed=0.8, hp=0.8),
    "normal": dict(lives=3, bombs=2, fire=1.0, bspeed=1.0, hp=1.0),
    "hard": dict(lives=3, bombs=1, fire=1.45, bspeed=1.2, hp=1.3, ramp=(0.8, 0.055)),
}
CHARGE_LV = (0.35, 0.85, 1.4, 2.3)       # seconds of charge for lance level 1, 2, 3 and the nova
SPEEDS = (34.0, 44.0, 54.0, 64.0)

# =============================================================================================
# Pixel art: one palette for every sprite, '.' is transparent; enemies face left
# =============================================================================================
PAL = {"k": (18, 18, 28), "w": (244, 244, 252), "g": (176, 182, 198), "G": (96, 102, 120), "d": (52, 56, 72),
       "r": (236, 64, 60), "R": (140, 30, 40), "o": (252, 150, 48), "O": (176, 84, 30), "y": (252, 222, 80),
       "Y": (184, 142, 40), "l": (150, 232, 84), "L": (58, 142, 62), "c": (96, 224, 244), "C": (30, 120, 164),
       "b": (84, 124, 250), "B": (40, 52, 142), "v": (184, 104, 252), "V": (98, 50, 160), "p": (250, 126, 192),
       "P": (168, 58, 100), "n": (156, 106, 62), "N": (92, 62, 40), "t": (64, 204, 164), "T": (28, 112, 100),
       "m": (240, 84, 236), "e": (255, 250, 176), "h": (255, 196, 196), "s": (200, 236, 255)}
WHITE = (255, 255, 255)


class Spr:
    """A pixel-art sprite; scaled copies are cached as horizontal runs for fast slice drawing."""
    __slots__ = ("rows", "w", "h", "cache")

    def __init__(self, rows):
        self.rows = rows
        self.w = max(len(r) for r in rows)
        self.h = len(rows)
        self.cache = {}

    def runs(self, s, flash=False, fh=False, fv=False):
        key = (int(s * 16 + 0.5), flash, fh, fv)
        r = self.cache.get(key)
        if r is None:
            r = self.cache[key] = self.build(key[0] / 16, flash, fh, fv)
        return r

    def build(self, s, flash, fh, fv):
        w, h = self.w, self.h
        ow, oh = max(1, int(w * s + 0.5)), max(1, int(h * s + 0.5))
        out = []
        for oy in range(oh):
            sy = min(h - 1, int((oy + 0.5) * h / oh))
            src = self.rows[h - 1 - sy if fv else sy]
            run_c, run_x = None, 0
            for ox in range(ow + 1):
                c = None
                if ox < ow:
                    sx = min(w - 1, int((ox + 0.5) * w / ow))
                    if fh:
                        sx = w - 1 - sx
                    ch = src[sx] if sx < len(src) else "."
                    if ch != ".":
                        c = mix(PAL[ch], WHITE, 0.55) if flash else PAL[ch]
                if c != run_c:
                    if run_c is not None:
                        n = ox - run_x
                        out.append((oy, run_x, n, run_c, [run_c] * n))
                    run_c, run_x = c, ox
        return ow, oh, out


def S(*rows):
    return Spr(list(rows))


SHIP = S("...dG..........", "..dGgg.........", ".dBbbbgwg.......", "dBbbbbbbbccwgk..", "BbbbbbbbbbbbccwG",
         "dBBBBbbbgggGG...", ".dBBBgg.........", "..dGG...........")
SPR = {
    "darter": [S("...rr...", ".rrRRr..", "wcRRRRrr", ".rrRRr..", "...rr..."),
               S("..rr....", ".rRRrr..", "wcRRRRrr", ".rRRrr..", "..rr....")],
    "scrapper": [S("..GgG....", ".GgnNGd..", "GgnNNnGG.", "dGNnNNgGd", ".dGNnGGd.", "..dGGd...", "....d...."),
                 S("....dG...", "..GgnGG..", ".GgNNnGd.", "GgNnNNgGd", "dGNnNGGd.", ".dGGd....", "..d......")],
    "turret": [S("..gGGg..", ".gGrrGg.", "gGGRRGGg", "GddddddG", "dGdGdGdG")],
    "strider": [S("..GgggG..", ".GgyyggG.", "rGGGGGGGG", ".dGddGd..", "..G..G...", ".G...G...", "GG....GG."),
                S("..GgggG..", ".GgyyggG.", "rGGGGGGGG", ".dGddGd..", "...GG....", "...GG....", "..GGGG...")],
    "spinner": [S("....v....", "...vVv...", "..vVwVv..", "vvVVwVVvv", "..vVwVv..", "...vVv...", "....v...."),
                S("v.......v", ".vV...Vv.", "..vVwVv..", "...VwV...", "..vVwVv..", ".vV...Vv.", "v.......v")],
    "polyp": [S("...pPp...", "..pPePp..", ".pPPPPPp.", "pPPpPpPPp", "PPPPPPPPP", "NPNPNPNPN"),
              S("...pwp...", "..pPePp..", ".pPPpPPp.", "pPpPpPpPp", "PPPPPPPPP", "NPNPNPNPN")],
    "spore": [S(".lL.", "lLlL", "LlLl", ".Ll.")],
    "tendril": [S("..PPp..", ".PpppP.", "PpeePPp", "PpeePPp", ".PpppP.", "..PPp..")],
    "tseg": [S(".PpP.", "PpPpP", "pPpPp", "PpPpP", ".PpP.")],
    "blister": [S("..pppp..", ".pwphpp.", "pphppppp", "PpppppPP", "PPPPPPPP"),
                S("..phpp..", ".pphwpp.", "pppppphp", "PpppppPP", "PPPPPPPP")],
    "leech": [S("...LLll.", "wLLLlllL", "wLLLLllL", "...LLLL."), S("..LLll..", "wLLlllLL", "wLLLllLL", "..LLLL..")],
    "vent": [S("GdGdGdGd", "dOdOdOdO", "GGGGGGGG", "dddddddd")],
    "hook": [S("..gGGg...", ".gG..Gg..", "gG....Gg.", "gG....Gg.", ".gG......", "..gGG....", "...gGGG..")],
    "rivet": [S("...oO.", ".oOyOO", "wOOOOO", "..oO..")],
    "cannon": [S("....gGGg....", "...gGrrGg...", "rrrGGRRGGg..", "..gGGGGGGGg.", ".gGGddddGGGg", "GGdGdGdGdGdG",
                 "dddddddddddd")],
    "eel": [S("..tTTT..", "tTtttTT.", "wetTttTT", "tTtttTT.", "..tTTT..")],
    "eseg": [S(".tTt.", "TtTtT", "tTtTt", ".TtT.")],
    "jelly": [S("..cCCCc..", ".cCwCCCc.", "cCCCCCCCc", "CCcCcCcCC", ".c.c.c.c.", ".c..c..c.", "c..c..c.."),
              S("..cCCCc..", ".cCwCCCc.", "cCCCCCCCc", "CCcCcCcCC", ".c.c.c.c.", "..c..c..c", ".c..c..c.")],
    "mine": [S("...G...", ".G.r.G.", "..GRG..", "GrRwRrG", "..GRG..", ".G.r.G.", "...G..."),
             S("...G...", ".G.R.G.", "..GrG..", "GRrwrRG", "..GrG..", ".G.R.G.", "...G...")],
    "angler": [S("..y.TTT.....", "..cTtttTT...", ".cCttettTT.T", "cCCtttttTTTT", "cCCtttttTTTT", ".cCttttTT..T",
                 "..cTtttT....", "....TTT.....")],
    "rockL": [S(".....NNNn.....", "...NNnnnnNN...", "..NnnNnnnnnN..", ".NnnnnnnNnnnN.", "NnnNnnnnnnnnnN",
                "NnnnnnnNNnnnnN", "NnnnnnnnnnnNnN", "NNnnnNnnnnnnnN", ".NnnnnnnnnnNN.", "..NNnnnNnnnN..",
                "...NNnnnnNN...", ".....NNNN.....")],
    "rockM": [S("..NNnN..", ".NnnnnN.", "NnnNnnnN", "NnnnnnnN", "NnnnnNnN", ".NnnnnN.", "..NNNN..")],
    "rockS": [S(".NnN.", "NnnnN", "NnNnN", ".NNN.")],
    "comet": [S("..cww...", ".cwwwwc.", "cwwewwcC", ".cwwwwc.", "..cww...")],
    "miner": [S("..YyyY...", ".YyyyyY..", "rYGGGGYy.", "rrGeeGYyy", "rYGGGGYy.", ".YyyyyY..", "..YyyY...")],
    "crawler": [S("..lLLl..", ".lLeeLl.", "LLLLLLLL", "L.L..L.L"), S("..lLLl..", ".lLeeLl.", "LLLLLLLL", ".L.LL.L.")],
    "drone": [S("y.Y.y", ".YoY.", "YoooY", ".Y.Y."), S(".yYy.", "yYoYy", "YoooY", ".Y.Y.")],
    "lancer": [S("...yY......", "..YyyYk..y.", "wkYkYkYkYYy", "..YyyYk..y.", "...yY......"),
               S("...yY...y..", "..YyyYk.y..", "wkYkYkYkYYy", "..YyyYk.y..", "...yY...y..")],
    "larva": [S("...yYYy...", "..yYoeYy..", ".yYYooYYy.", "yYyYyYyYyY", "YNYNYNYNYN", "NNNNNNNNNN")],
    "comb": [S(".YyyY.", "YyOOyY", "yOooOy", "yOooOy", "YyOOyY", ".YyyY.")],
    "shard": [S("...w...", "..wcc..", ".wcCcc.", "wcCwCcc", ".cCcCc.", "..cCc..", "...c..."),
              S("...c...", "..ccw..", ".ccCcw.", "ccCwCcw", ".cCcCc.", "..cCc..", "...c...")],
    "phantom": [S("..vVVVv..", ".vVwVwVv.", "vVVeVeVVv", "vVVVVVVVv", "vVVVVVVVv", "vVvVvVvVv", "v.v.v.v.v"),
                S("..vVVVv..", ".vVwVwVv.", "vVVeVeVVv", "vVVVVVVVv", "vVVVVVVVv", "vVvVvVvVv", ".v.v.v.v.")],
    "clock": [S("..gGGGg..", ".gYyyyYg.", "gYyywyyYg", "GyyywyyyG", "GyyykyyyG", "GyyyyyyyG", "gYyyyyyYg",
                ".gYyyyYg.", "..gGGGg.."),
              S("..gGGGg..", ".gYyyyYg.", "gYyyyyyYg", "GyyyyyyyG", "GyyykwwwG", "GyyyyyyyG", "gYyyyyyYg",
                ".gYyyyYg.", "..gGGGg..")],
    "node": [S("..mVm..", ".mVwVm.", "GmVVVmG", "GGGGGGG", "ddddddd")],
    "sentinel": [S("......RRr.....", "....RRrrrRR...", "rr.RrrgggrrRR.", "rrRrrgeegrrrRR", "..RRrrgggrrrRR",
                   "rrRrrrrrrrRRR.", "rr.RRrrrrRR...", "....RRRRR.....")],
    "ferry": [S("...lLLLl....", "..lLwwwLl...", "llLLLLLLLLl.", "LyLLLLLLLLLL", "..GgGgGgG...", "..GoooooG...",
                "...GGGGG....")],
    "seeker": [S(".vvv.", "vVwVv", "vwewv", "vVwVv", ".vvv.")],
    # midbosses
    "scrapclaw": [S("...gG............Gg...", "..gGG............GGg..", ".gG.G............G.Gg.",
                    ".gG..gG........Gg..Gg.",
                    "..gGGGgGGGGGGGGgGGGg..", "....GGgggggggggggGG...", "..GGgggGrrGGGrrGggGG..",
                    ".GgggggGRRGGGRRGgggggG", "GgnnnggggggggggggnnngG", "GgnNnggGGGGGGGGggnNngG",
                    ".GgnggGdddddddddGggngG", "..GGGGd.d.d.d.d.dGGGG.", "...G.G...........G.G..",
                    "..G...G.........G...G.")],
    "mawbloom": [S("......pPPPPPPp......", "....pPPpppppPPPp....", "..pPPppPPPPPPppPPp..", ".pPpPPP..rr..PPPpPp.",
                   "pPpPP..rRRRRr..PPpPp", "pPpP..rRkkkkRr..PpPp", "PpPP.rRkkwwkkRr.PPpP", "PpPP.rRkkwwkkRr.PPpP",
                   "pPpP..rRkkkkRr..PpPp", "pPpPP..rRRRRr..PPpPp", ".pPpPPP..rr..PPPpPp.", "..pPPppPPPPPPppPPp..",
                   "....pPPpppppPPPp....", "......LLlLLlLL......", ".....LL..LL..LL.....")],
    "smelter": [S("......GGGGGGGG......", "....GGggggggggGG....", "..GGggOOOOOOOOggGG..", ".GggOOooooooooOOggG.",
                  "rrrgOoyyyeeyyyoOggGG", "rrrgOoyyyeeyyyoOggGG", ".GggOOooooooooOOggG.", "..GGggOOOOOOOOggGG..",
                  "....GGggggggggGG....", "...dG.dG.dG.dG.dG...", "...O..O..O..O..O....", "...o..o..o..o..o....")],
    "siltback": [S(".......TTTTTTT........", "....TTTtTtTtTtTTT.....", "..TTtTtTtTtTtTtTtTT...",
                   ".TtTtTtTtTtTtTtTtTtT..", "cTTTTTTTTTTTTTTTTTTTTT", "ceccCCCCCCCCCCCCCCCCCT",
                   "cCCccccccccccccccccCTT", ".cCC.CC.......CC.CCT..", "..cc..cc.......cc.cc..")],
    "hauler": [S("..........GGGGGGG.....", "....YYYYYYgggggggG....", "..YYyyyyyyGGGGGGGGG...",
                 "rrYyGGGGGGGGgggggggGG.", "rrYyGeeGGGGGgNNNNNgGGG", "rrYyGGGGGGGGgnnnnngGGG", "..YYyyyyyyGGGNNNNNGGG.",
                 "....YYYYYYgggggggggG..", "......dd.dd.dd.dd.dd..", ".....d..d..d..d..d....")],
    "broodwarden": [S("........yYYYYy........", "......yYoooooYy.......", "..y..yYoeoooeoYy..y...",
                      ".yYy.YYoooooooYY.yYy..", "yYkYyYkYkYkYkYkYyYkYy.", "YkYkYkYkYkYkYkYkYkYkY.",
                      ".YyY.YkYkYkYkYkY.YyY..", "..y...YkYkYkYkY...y...", "........YkYkY.........",
                      ".........YkY..........", "..........Y...........")],
    "facet": [S("..........c..........", "........ccwcc........", "......ccCCwCCcc......", "....ccCCCcwcCCCcc....",
                "..ccCCcccCwCcccCCcc..", "ccCCccwwwmmmwwwccCCcc", "..ccCCcccCwCcccCCcc..", "....ccCCCcwcCCCcc....",
                "......ccCCwCCcc......", "........ccwcc........", "..........c..........")],
    "gatekeeper": [S("GGGGGGGGGGGGGGGGGG", "GrrrrGGGGGGGGrrrrG", "GrRRrGddddddGrRRrG", "GrRRrGdmmmmdGrRRrG",
                     "GrrrrGdmwwmdGrrrrG", "GGGGGGdmwwmdGGGGGG", "GrrrrGdmmmmdGrrrrG", "GrRRrGddddddGrRRrG",
                     "GrRRrGGGGGGGGrRRrG", "GrrrrGGGGGGGGrrrrG", "GGGGGGGGGGGGGGGGGG")],
}
# pickups: colour, short letter, long name
CRYSTALS = ["red", "blue", "yellow", "green", "violet", "white"]
CRYSTAL_C = {"red": (250, 80, 70), "blue": (90, 150, 255), "yellow": (250, 222, 70), "green": (110, 236, 110),
             "violet": (196, 110, 255), "white": (236, 240, 255)}
CRYSTAL_NAME = {"red": "RING SPREAD", "blue": "RICOCHET RAY", "yellow": "CRAWL WAVE", "green": "HOMING NEEDLES",
                "violet": "SCATTER BURST", "white": "CHAIN ARC"}
ITEMS = {  # kind: (colour, letter, name)
    "missile": ((250, 170, 70), "M", "MISSILES"), "crawlbomb": ((200, 150, 90), "G", "CRAWLER BOMBS"),
    "bit": ((120, 220, 255), "O", "ORBIT BIT"), "speed": ((120, 240, 200), "S", "SPEED UP"),
    "slow": ((90, 130, 170), "s", "SPEED DOWN"), "shield": ((110, 200, 255), "H", "SHIELD"),
    "bomb": ((255, 120, 90), "B", "SMART BOMB"), "life": ((255, 236, 120), "1", "EXTRA SHIP"),
    "gem": ((255, 220, 120), "$", "1000 POINTS"),
}

# =============================================================================================
# Sound
# =============================================================================================
SND = Sound(GAME, {
    "shot": [dict(w="square", f=1250, f2=700, d=0.04, v=0.13, duty=0.25)],
    "ring": [dict(w="tri", f=900, f2=1400, d=0.06, v=0.16)],
    "ray": [dict(w="saw", f=1800, f2=900, d=0.07, v=0.12)],
    "wave": [dict(w="tri", f=300, f2=520, d=0.09, v=0.2, vib=(30, 1.0))],
    "needle": [dict(w="square", f=1600, f2=2200, d=0.04, v=0.1, duty=0.125)],
    "scatter": [dict(w="noise", f=3000, f2=900, d=0.07, v=0.16), dict(w="tri", f=500, d=0.05, v=0.14, at=0)],
    "zap": [dict(w="noise", f=9000, f2=4000, d=0.08, v=0.2), dict(w="saw", f=2400, f2=600, d=0.08, v=0.1, at=0)],
    "missile": [dict(w="noise", f=1400, f2=500, d=0.12, v=0.14)],
    "bombdrop": [dict(w="tri", f=240, f2=120, d=0.08, v=0.18)],
    "charge1": [dict(w="tri", f=440, f2=660, d=0.08, v=0.2)],
    "charge2": [dict(w="tri", f=660, f2=990, d=0.08, v=0.24)],
    "charge3": [dict(w="square", f=990, f2=1320, d=0.1, v=0.2, duty=0.25)],
    "charge4": [dict(w="square", f=1320, d=0.05, v=0.2, duty=0.25), dict(w="square", f=1760, d=0.12, v=0.22, duty=0.25,
                                                                         vib=(12, 0.4))],
    "lance1": [dict(w="saw", f=900, f2=300, d=0.14, v=0.28)],
    "lance2": [dict(w="saw", f=700, f2=180, d=0.22, v=0.34), dict(w="noise", f=2000, f2=400, d=0.18, v=0.16, at=0)],
    "lance3": [dict(w="saw", f=1400, f2=90, d=0.42, v=0.4), dict(w="noise", f=5000, f2=300, d=0.4, v=0.22, at=0),
               dict(w="square", f=110, f2=55, d=0.4, v=0.2, at=0)],
    "nova": [dict(w="saw", f=2000, f2=60, d=0.7, v=0.45), dict(w="noise", f=7000, f2=100, d=0.8, v=0.3, at=0),
             dict(w="square", f=80, f2=40, d=0.7, v=0.28, at=0, duty=0.3)],
    "hit": [dict(w="noise", f=5000, f2=2000, d=0.025, v=0.12)],
    "clink": [dict(w="square", f=2600, f2=3200, d=0.03, v=0.1, duty=0.125)],
    "pop": [dict(w="noise", f=3500, f2=500, d=0.1, v=0.25), dict(w="tri", f=300, f2=90, d=0.1, v=0.2, at=0)],
    "boom": [dict(w="noise", f=1800, f2=80, d=0.35, v=0.4), dict(w="square", f=120, f2=40, d=0.3, v=0.24, at=0,
                                                                  duty=0.3)],
    "bigboom": [dict(w="noise", f=1200, f2=40, d=0.9, v=0.55, r="lin"), dict(w="square", f=90, f2=30, d=0.8, v=0.3,
                                                                              at=0, duty=0.3),
                dict(w="noise", f=3000, f2=200, d=0.4, v=0.3, at=0.25)],
    "eshot": [dict(w="square", f=520, f2=380, d=0.04, v=0.08, duty=0.5)],
    "eorb": [dict(w="tri", f=220, f2=160, d=0.08, v=0.18)],
    "laserwarn": [dict(w="square", f=1800, d=0.05, v=0.08, duty=0.125), dict(w="square", f=1800, d=0.05, v=0.08,
                                                                              duty=0.125, at=0.1)],
    "laser": [dict(w="saw", f=180, f2=160, d=0.5, v=0.24, r="hold", vib=(25, 0.6))],
    "flame": [dict(w="noise", f=600, f2=900, d=0.5, v=0.2, r="lin")],
    "item": [dict(w="square", f=880, d=0.04, v=0.24, duty=0.25), dict(w="square", f=1320, d=0.04, v=0.24, duty=0.25),
             dict(w="tri", f=1760, d=0.12, v=0.28)],
    "crystal": [dict(w="tri", f=660, d=0.05, v=0.3), dict(w="tri", f=990, d=0.05, v=0.3),
                dict(w="tri", f=1320, d=0.18, v=0.32, vib=(9, 0.3))],
    "powerup": [dict(w="square", f=523, d=0.05, v=0.25, duty=0.25), dict(w="square", f=784, d=0.05, v=0.25, duty=0.25),
                dict(w="square", f=1047, d=0.05, v=0.25, duty=0.25), dict(w="tri", f=1568, d=0.2, v=0.3)],
    "podin": [dict(w="tri", f=200, f2=900, d=0.18, v=0.3), dict(w="square", f=1200, d=0.08, v=0.18, duty=0.25)],
    "launch": [dict(w="saw", f=300, f2=1200, d=0.14, v=0.24)],
    "recall": [dict(w="saw", f=1200, f2=400, d=0.14, v=0.2)],
    "dock": [dict(w="square", f=660, d=0.03, v=0.2, duty=0.25), dict(w="square", f=990, d=0.06, v=0.2, duty=0.25)],
    "absorb": [dict(w="tri", f=1900, f2=2400, d=0.03, v=0.08)],
    "smart": [dict(w="noise", f=6000, f2=60, d=1.0, v=0.5, r="lin"), dict(w="saw", f=60, f2=600, d=0.5, v=0.25, at=0),
              dict(w="tri", f=880, f2=110, d=0.8, v=0.25, at=0.1)],
    "shield": [dict(w="tri", f=400, f2=1200, d=0.2, v=0.28, vib=(14, 0.5))],
    "shieldhit": [dict(w="noise", f=7000, f2=2000, d=0.2, v=0.3), dict(w="tri", f=1200, f2=300, d=0.2, v=0.25, at=0)],
    "life": [dict(w="square", f=f, d=0.07, v=0.26, duty=0.25) for f in (784, 988, 1175, 1568)] +
            [dict(w="tri", f=1568, d=0.3, v=0.3, vib=(7, 0.3))],
    "die": [dict(w="noise", f=3000, f2=60, d=1.0, v=0.55, r="lin"), dict(w="saw", f=600, f2=50, d=0.9, v=0.3, at=0)],
    "checkpoint": [dict(w="tri", f=784, d=0.08, v=0.28), dict(w="tri", f=1047, d=0.16, v=0.28)],
    "warning": [dict(w="square", f=440, d=0.22, v=0.26, duty=0.5, r="hold"), dict(w="square", f=330, d=0.22, v=0.26,
                                                                                    duty=0.5, r="hold")] * 3,
    "phase": [dict(w="saw", f=200, f2=900, d=0.3, v=0.3), dict(w="noise", f=2000, f2=300, d=0.3, v=0.25, at=0)],
    "spawn": [dict(w="tri", f=180, f2=420, d=0.12, v=0.16)],
    "clear": [dict(w="square", f=f, d=0.09, v=0.28, duty=0.25) for f in (523, 659, 784, 1047, 784, 1047)] +
             [dict(w="tri", f=1319, d=0.6, v=0.34, vib=(6, 0.25), r="lin")],
    "over": [dict(w="tri", f=392, d=0.18, v=0.4), dict(w="tri", f=330, d=0.18, v=0.4), dict(w="tri", f=262, d=0.18,
                                                                                         v=0.4),
             dict(w="tri", f=196, f2=130, d=0.7, v=0.42, r="lin")],
    "win": [dict(w="square", f=f, d=0.11, v=0.28, duty=0.25) for f in (523, 659, 784, 1047, 1319, 1047, 1319)] +
           [dict(w="tri", f=1568, d=0.9, v=0.36, vib=(5, 0.3), r="lin")],
    "menu": [dict(w="tri", f=660, d=0.025, v=0.2)],
    "start": [dict(w="square", f=392, d=0.06, v=0.28, duty=0.25), dict(w="square", f=587, d=0.06, v=0.28, duty=0.25),
              dict(w="saw", f=300, f2=1600, d=0.3, v=0.24)],
    "pause": [dict(w="tri", f=523, f2=392, d=0.07, v=0.22)],
    "sound_on": [dict(w="tri", f=440, d=0.06, v=0.35), dict(w="tri", f=880, d=0.12, v=0.35)],
})


def help_lines(kitty):
    mode = (["Your terminal reports key releases (kitty protocol):",
             "tap Space to shoot, hold it to charge, let go to fire the lance."] if kitty else
            ["Classic keys: hold Space for rapid fire. Press C to start",
             "charging and C again to fire the lance."])
    return ["VOIDLANCE - keys", "",
            "Arrows / WASD          fly (8 directions)",
            "Space                  shoot / charge the lance",
            "C                      charge on, again: fire the lance",
            "X                      rapid fire",
            "F                      launch the pod / call it back",
            "B                      smart bomb",
            "Esc / P                pause menu (Q quit, M sound)",
            "?                      this help", ""] + mode + [
            "",
            "Auto mode: the game plays itself (Space pause, +/- speed, Esc stop).",
            "",
            "Lance: 1 bolt, 2 piercing bolt, 3 beam through the screen;",
            "keep charging past 3 for the NOVA. The pod docks at the nose",
            "or the tail - whichever side touches it - and soaks up small",
            "shots. Same crystal colour: level up, new colour: new weapon.",
            "Never touch the walls."]

SPR["plate"] = [S(".GggG.", "GgGGgG", "gGddGg", "gGddGg", "GgGGgG", ".GggG.")]

# =============================================================================================
# The eight stages
# =============================================================================================
# air: (enemy, formation, weight); ground: (enemy, weight); extra: (special, chance per wave)
STAGES = [
    dict(name="GRAVEYARD ORBIT", blurb="an orbital wreck yard", far="stars", sky=((3, 6, 22), (14, 22, 50)),
         mid="wrecks", midc=((20, 28, 52), (40, 54, 88)), terrain="girders",
         tcol=((200, 210, 226), (120, 132, 156), (58, 66, 90), (40, 46, 66)), speed=15.0, accent=(140, 200, 255),
         air=[("darter", "sine", 4), ("darter", "line", 2), ("scrapper", "scatter", 2), ("rivet", "vee", 2),
              ("spinner", "single", 1)],
         ground=[("turret", 3), ("strider", 2)], extra=[], midboss="scrapclaw", boss="scrapmonarch"),
    dict(name="GULLET CAVERNS", blurb="a cave that is alive", far="flesh", sky=((26, 4, 12), (60, 12, 30)),
         mid="veins", midc=((54, 12, 30), (86, 24, 48)), terrain="flesh",
         tcol=((250, 150, 170), (196, 70, 104), (120, 30, 60), (90, 20, 46)), speed=14.0, accent=(255, 130, 170),
         air=[("leech", "line", 3), ("tendril", "snake", 3), ("spore", "cluster", 2), ("darter", "sine", 1)],
         ground=[("polyp", 3), ("blister", 3)], extra=[], midboss="mawbloom", boss="mothergland"),
    dict(name="IRONWORKS DRIFT", blurb="along the hull of a war cruiser", far="forge", sky=((20, 10, 6), (54, 26, 14)),
         mid="pipes", midc=((40, 22, 16), (70, 40, 26)), terrain="hull",
         tcol=((236, 196, 140), (150, 120, 96), (86, 70, 62), (62, 52, 48)), speed=16.0, accent=(255, 170, 90),
         air=[("rivet", "vee", 3), ("darter", "line", 2), ("sentinel", "single", 1), ("scrapper", "scatter", 1)],
         ground=[("cannon", 2), ("strider", 2), ("turret", 2)], extra=[("vent", 0.35), ("hook", 0.25)],
         midboss="smelter", boss="dreadkiln"),
    dict(name="DROWNED HALLS", blurb="flooded caverns under a dead moon", far="water", sky=((4, 18, 30), (6, 40, 62)),
         mid="kelp", midc=((8, 40, 52), (16, 66, 76)), terrain="flooded",
         tcol=((140, 220, 210), (60, 140, 140), (24, 80, 90), (16, 58, 70)), speed=14.0, accent=(110, 230, 220),
         air=[("eel", "snake", 3), ("jelly", "group", 2), ("mine", "field", 2), ("angler", "single", 2)],
         ground=[("crawler", 3), ("turret", 1)], extra=[], midboss="siltback", boss="drownedbell", water=22),
    dict(name="SHATTER BELT", blurb="an asteroid storm", far="storm", sky=((14, 8, 20), (40, 26, 36)),
         mid="dust", midc=((40, 28, 36), (64, 46, 50)), terrain="asteroid",
         tcol=((200, 170, 140), (130, 100, 80), (80, 60, 50), (60, 44, 38)), speed=17.0, accent=(240, 180, 120),
         air=[("comet", "burst", 2), ("miner", "single", 2), ("rockL", "field", 3), ("darter", "sine", 2)],
         ground=[("crawler", 2)], extra=[], midboss="hauler", boss="cinderheart"),
    dict(name="HIVE VERGE", blurb="inside an insect hive", far="hive", sky=((22, 14, 4), (52, 34, 8)),
         mid="combs", midc=((50, 34, 10), (80, 56, 16)), terrain="hive",
         tcol=((255, 214, 110), (200, 140, 40), (120, 80, 20), (90, 60, 16)), speed=15.0, accent=(255, 200, 80),
         air=[("drone", "swarm", 3), ("lancer", "single", 2), ("leech", "line", 1), ("drone", "line", 1)],
         ground=[("larva", 3), ("blister", 1)], extra=[("comb", 0.22)], midboss="broodwarden", boss="ambersovereign"),
    dict(name="PRISM RIFT", blurb="where time cracks like glass", far="prism", sky=((8, 4, 26), (30, 10, 50)),
         mid="facets", midc=((34, 20, 70), (60, 40, 110)), terrain="crystal",
         tcol=((220, 250, 255), (120, 200, 240), (70, 90, 180), (50, 60, 140)), speed=16.0, accent=(200, 150, 255),
         air=[("shard", "group", 2), ("phantom", "single", 2), ("clock", "single", 1), ("spinner", "single", 1),
              ("darter", "sine", 1)],
         ground=[("turret", 2)], extra=[("prism", 0.35)], midboss="facet", boss="chronoprism"),
    dict(name="NULL CITADEL", blurb="the fortress at the heart of the void", far="core", sky=((14, 2, 6), (40, 8, 14)),
         mid="towers", midc=((36, 10, 18), (60, 20, 30)), terrain="citadel",
         tcol=((210, 200, 210), (130, 116, 130), (70, 56, 70), (52, 40, 52)), speed=16.0, accent=(255, 90, 110),
         air=[("sentinel", "single", 2), ("rivet", "vee", 2), ("phantom", "single", 1), ("lancer", "single", 1),
              ("miner", "single", 1), ("drone", "swarm", 1)],
         ground=[("cannon", 1), ("turret", 2), ("strider", 1)], extra=[("piston", 0.3), ("node", 0.14), ("plate", 0.12)],
         midboss="gatekeeper", boss="voidengine"),
]
LEN = 1500                      # stage length in field units, then the boss arena
MINGAP = 30


def _smooth_noise(rnd, n, scale):
    pts = [rnd.uniform(-1, 1) for _ in range(n // scale + 3)]
    out = []
    for i in range(n):
        k, f = divmod(i, scale)
        f = f / scale
        f = f * f * (3 - 2 * f)
        out.append(pts[k] + (pts[k + 1] - pts[k]) * f)
    return out


def gen_terrain(si):
    """Ceiling (where it ends) and floor (where it starts) for every column of the stage, in field units."""
    st = STAGES[si]
    style = st["terrain"]
    rnd = random.Random(77 + si * 31)
    N = LEN + FW * 3
    c, f = [0.0] * N, [float(FH)] * N
    nz = _smooth_noise(rnd, N, 23)
    nz2 = _smooth_noise(rnd, N, 9)
    slope = 3.0
    if style == "girders":
        i = 0
        while i < N:
            seg = rnd.randint(40, 110)
            typ = rnd.choice(["open", "floor", "ceil", "both", "both", "floor"])
            hc, hf = rnd.choice([6, 8, 10, 12]), rnd.choice([6, 8, 10, 12, 14])
            for j in range(i, min(N, i + seg)):
                c[j] = hc if typ in ("ceil", "both") else 0
                f[j] = FH - hf if typ in ("floor", "both") else FH
            i += seg
    elif style == "flesh":
        p = [rnd.uniform(0, TAU) for _ in range(4)]
        for i in range(N):
            c[i] = 9 + 5 * math.sin(i * 0.031 + p[0]) + 3 * math.sin(i * 0.083 + p[1]) + 2 * nz[i]
            f[i] = FH - (9 + 5 * math.sin(i * 0.027 + p[2]) + 3 * math.sin(i * 0.07 + p[3]) + 2 * nz2[i])
    elif style == "hull":
        i = 0
        while i < N:
            seg = rnd.randint(30, 70)
            hull = rnd.random() < 0.8
            base = rnd.choice([10, 12, 14])
            for j in range(i, min(N, i + seg)):
                f[j] = FH - base if hull else FH
            if hull and rnd.random() < 0.6:          # a superstructure block on the hull
                a = i + rnd.randint(4, max(5, seg - 22))
                for j in range(a, min(N, a + rnd.randint(8, 18))):
                    f[j] = FH - base - rnd.choice([6, 8, 10])
            if rnd.random() < 0.3:                   # an overhead beam
                for j in range(i, min(N, i + rnd.randint(16, 34))):
                    c[j] = 7
            i += seg
    elif style == "flooded":
        for i in range(N):
            c[i] = 4 + 2 * nz[i]
            f[i] = FH - (6 + 3 * nz2[i] + 2 * math.sin(i * 0.05))
        i = 10
        while i < N:
            w, d = rnd.randint(6, 10), rnd.randint(4, 12)
            for j in range(w):
                if i + j < N:
                    c[i + j] += d * (1 - abs(j - w / 2) / (w / 2))
            i += rnd.randint(10, 22)
        i = 15
        while i < N:
            w, d = rnd.randint(6, 12), rnd.randint(3, 9)
            for j in range(w):
                if i + j < N:
                    f[i + j] -= d * (1 - abs(j - w / 2) / (w / 2))
            i += rnd.randint(14, 30)
    elif style == "asteroid":
        i = 0
        while i < N:
            seg = rnd.randint(50, 120)
            ridge = rnd.random() < 0.35
            for j in range(i, min(N, i + seg)):
                f[j] = FH - (6 + 4 * nz2[j] + 3 * nz[j]) if ridge else FH
            i += seg
        slope = 4.0
    elif style == "hive":
        for i in range(N):
            c[i] = 4 * int((10 + 7 * nz[i] + 3 * nz2[i]) / 4)
            f[i] = FH - 4 * int((10 + 7 * nz2[(i + 300) % N] + 3 * nz[(i + 77) % N]) / 4)
        slope = 4.0
    elif style == "crystal":
        for i in range(N):
            c[i] = 3 + 3 * nz[i]
            f[i] = FH - 3 - 3 * nz2[i]
        for arr, sign, off in ((c, 1, 0), (f, -1, 9)):
            i = off
            while i < N:
                w, d = rnd.randint(5, 9), rnd.randint(6, 16)
                for j in range(w):
                    if i + j < N:
                        arr[i + j] += sign * d * (1 - abs(j - w / 2) / (w / 2))
                i += rnd.randint(12, 26)
        slope = 5.0
    elif style == "citadel":
        i = 0
        while i < N:
            seg = rnd.randint(30, 60)
            hc, hf = rnd.choice([0, 6, 10, 14, 18]), rnd.choice([0, 6, 10, 14, 18])
            for j in range(i, min(N, i + seg)):
                c[j], f[j] = hc, FH - hf
            i += seg
        slope = 6.0
    # a calm start, a wide midboss area, a flat boss arena
    mid = int(LEN * 0.5)
    for i in range(N):
        k = 1.0
        if i < FW + 40:
            k = clamp((i - FW) / 40, 0, 1)
        if mid - 20 <= i < mid + 360:
            k = min(k, 0.35)
        if i >= LEN - 60:
            k = min(k, clamp((LEN - i) / 60, 0, 1))
        c[i] = c[i] * k + (1 - k) * (3 if style != "asteroid" else 0)
        f[i] = f[i] * k + (1 - k) * (FH - 3 if style != "asteroid" else FH)
        if f[i] - c[i] < MINGAP:
            m = clamp((c[i] + f[i]) / 2, MINGAP / 2 + 2, FH - MINGAP / 2 - 2)
            c[i], f[i] = min(c[i], m - MINGAP / 2), max(f[i], m + MINGAP / 2)
        c[i] = max(0.0, c[i])
        f[i] = min(float(FH), f[i])
    for arr, up in ((c, False), (f, True)):        # no wall rises faster than the ship can climb
        for rng in (range(1, N), range(N - 2, -1, -1)):
            for i in rng:
                prev = arr[i - 1] if rng.step > 0 else arr[i + 1]
                if up and arr[i] < prev - slope:
                    arr[i] = prev - slope
                elif not up and arr[i] > prev + slope:
                    arr[i] = prev + slope
    return c, f


def build_events(si, c, f):
    """The stage script: (world x of the right screen edge, event, ...), sorted by x."""
    st = STAGES[si]
    rnd = random.Random(500 + si * 17)
    ev = []
    x = FW + 30.0
    mid_x = LEN * 0.5
    mid_done = False
    next_car = 70.0
    air = [(k, fm) for k, fm, w in st["air"] for _ in range(w)]
    ground = [k for k, w in st["ground"] for _ in range(w)]
    while x < LEN - 70:
        i = int(x)
        if not mid_done and x >= mid_x:
            ev.append((x, "mid"))
            mid_done = True
            x += 60
            continue
        lo, hi = c[i] + 7, f[i] - 7
        if x >= next_car:
            ev.append((x, "carrier", rnd.uniform(lo, hi)))
            next_car += rnd.uniform(120, 170)
        kind, form = rnd.choice(air)
        ev.append((x, "wave", kind, form, rnd.uniform(lo + 3, hi - 3), rnd.random()))
        if ground and rnd.random() < 0.65:
            gx = x + rnd.uniform(4, 24)
            ev.append((gx, "ground", rnd.choice(ground), rnd.random() < 0.7))
        for sp, ch in st["extra"]:
            if rnd.random() < ch:
                ev.append((x + rnd.uniform(10, 20), "special", sp, rnd.random()))
        x += rnd.uniform(22, 36)
    for cp in (LEN * 0.34, LEN * 0.68):
        ev.append((cp, "check"))
    ev.append((LEN, "boss"))
    ev.sort(key=lambda e: e[0])
    return ev


# =============================================================================================
# Things that fly about
# =============================================================================================
class Shot:
    """A player projectile."""
    __slots__ = ("x", "y", "vx", "vy", "kind", "dmg", "life", "t", "pierce", "dead", "hw", "hh", "data", "hit")

    def __init__(self, x, y, vx, vy, kind, dmg=1.0, life=2.0, hw=1.5, hh=1.0, pierce=0.0):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.kind, self.dmg, self.life, self.t = kind, dmg, life, 0.0
        self.pierce, self.dead, self.hw, self.hh = pierce, False, hw, hh
        self.data = None
        self.hit = None


class Bullet:
    """An enemy bullet: 'pel' small (the pod and the bits soak it up), 'orb' big, 'lob' falls."""
    __slots__ = ("x", "y", "vx", "vy", "kind", "r", "dead", "t")

    def __init__(self, x, y, vx, vy, kind="pel"):
        self.x, self.y, self.vx, self.vy, self.kind = x, y, vx, vy, kind
        self.r = 2.2 if kind == "orb" else 1.2
        self.dead = False
        self.t = 0.0


class Enemy:
    __slots__ = ("kind", "x", "y", "vx", "vy", "hp", "maxhp", "t", "w", "h", "score", "anch", "flash", "st", "dead",
                 "data", "fire", "inv", "fv", "boss", "ghost", "ceil", "solid")

    def __init__(self, kind, x, y, hp, score, w, h):
        self.kind, self.x, self.y = kind, x, y
        self.vx = self.vy = 0.0
        self.hp = self.maxhp = hp
        self.t = 0.0
        self.w, self.h, self.score = w, h, score
        self.anch = self.dead = self.inv = self.fv = self.ghost = self.ceil = self.solid = False
        self.flash = 0.0
        self.st = y
        self.data = {}
        self.fire = 1.0
        self.boss = None


# kind: (hp, score, width, height, flags) - flags: a anchored to the terrain, i invulnerable, s solid wall
ESPEC = {
    "darter": (1, 100, 7, 4, ""), "scrapper": (5, 200, 8, 6, ""), "turret": (3, 300, 7, 4, "a"),
    "strider": (4, 300, 8, 7, "a"), "spinner": (6, 500, 8, 7, ""), "polyp": (8, 600, 8, 5, "a"),
    "spore": (1, 50, 4, 4, ""), "tendril": (6, 800, 6, 6, ""), "tseg": (2, 100, 5, 5, ""),
    "blister": (3, 300, 7, 4, "a"), "leech": (2, 150, 7, 4, ""), "vent": (99, 0, 8, 4, "ai"),
    "hook": (14, 700, 8, 7, "a"), "rivet": (1, 120, 6, 4, ""), "cannon": (8, 800, 11, 6, "a"),
    "eel": (5, 700, 7, 5, ""), "eseg": (2, 100, 5, 4, ""), "jelly": (4, 400, 8, 7, ""), "mine": (2, 200, 6, 6, ""),
    "angler": (8, 800, 11, 8, ""), "rockL": (12, 300, 13, 11, ""), "rockM": (5, 150, 8, 7, ""),
    "rockS": (2, 80, 5, 4, ""), "comet": (3, 300, 7, 4, ""), "miner": (6, 600, 8, 7, ""),
    "crawler": (3, 250, 8, 4, "a"), "drone": (1, 80, 5, 4, ""), "lancer": (3, 300, 10, 4, ""),
    "larva": (8, 600, 9, 5, "a"), "comb": (3, 50, 6, 6, "as"), "plate": (5, 60, 6, 6, "as"),
    "shard": (6, 500, 7, 7, ""), "phantom": (4, 500, 8, 7, ""), "clock": (10, 900, 9, 9, ""),
    "prism": (99, 0, 7, 10, "ais"), "piston": (99, 0, 10, 10, "ais"), "node": (6, 700, 6, 4, "a"),
    "sentinel": (24, 1500, 13, 8, ""), "ferry": (4, 500, 11, 6, ""), "seeker": (2, 100, 4, 4, ""),
    "orbiter": (8, 200, 6, 6, ""),
}
SPRITE_OF = {"orbiter": "rockS"}
MIDBOSSES = {
    "scrapclaw": dict(name="SCRAPCLAW", hp=[90, 60], w=22, h=14, core=(-2, 1, 10, 6), move=["hover", "track"],
                      atk=[[("aim", 1.5, dict(n=3, spread=14)), ("lob", 2.6, dict(n=4))],
                           [("aim", 1.0, dict(n=5, spread=12)), ("lob", 2.0, dict(n=5)),
                            ("spawn", 5.0, dict(kind="darter", n=3))]]),
    "mawbloom": dict(name="MAW BLOOM", hp=[100, 70], w=20, h=15, core=(0, 0, 8, 6), move=["bob", "bob"],
                     atk=[[("ring", 2.0, dict(n=10)), ("spawn", 3.5, dict(kind="spore", n=3))],
                          [("spiral", 4.0, dict(arms=2, dur=2.5)), ("ring", 2.6, dict(n=12))]]),
    "smelter": dict(name="SMELTER", hp=[110, 70], w=20, h=12, core=(0, 0, 8, 4), move=["track", "track"],
                    atk=[[("aim", 1.8, dict(n=7, spread=40, sp=50))],
                         [("laser", 3.2, {}), ("aim", 1.6, dict(n=7, spread=46, sp=54))]]),
    "siltback": dict(name="SILTBACK", hp=[110, 80], w=22, h=9, core=(-8, 0, 6, 4), move=["hover", "hover"],
                     atk=[[("aim", 1.6, dict(n=3, kind="orb")), ("mines", 4.0, dict(n=2))],
                          [("ring", 2.2, dict(n=10)), ("mines", 3.5, dict(n=2)), ("aim", 1.4, dict(n=1, kind="orb"))]]),
    "hauler": dict(name="QUARRY HAULER", hp=[120, 80], w=22, h=10, core=(-6, 0, 8, 4), move=["track", "track"],
                   atk=[[("spawn", 3.0, dict(kind="rockM", n=1)), ("laser", 4.0, {})],
                        [("spawn", 2.6, dict(kind="rockM", n=1)), ("laser", 3.4, {}),
                         ("aim", 1.6, dict(n=5, spread=30))]]),
    "broodwarden": dict(name="BROOD WARDEN", hp=[120, 90], w=22, h=11, core=(-2, -2, 8, 5), move=["hover", "hover"],
                        atk=[[("spawn", 3.5, dict(kind="drone", n=4)), ("aim", 1.6, dict(n=3, spread=16))],
                             [("spawn", 3.2, dict(kind="lancer", n=1)), ("ring", 2.4, dict(n=12)),
                              ("aim", 1.8, dict(n=3, spread=16))]]),
    "facet": dict(name="FACET GOLEM", hp=[130, 90], w=21, h=11, core=(0, 0, 6, 4), move=["eight", "eight"],
                  atk=[[("spiral", 3.5, dict(arms=3, dur=2.2))], [("ring", 2.2, dict(n=14)), ("sweep", 4.5, {})]]),
    "gatekeeper": dict(name="GATEKEEPER", hp=[140, 100], w=18, h=11, core=(0, 0, 6, 6), move=["still", "still"],
                       atk=[[("curtain", 2.8, {}), ("aim", 1.4, dict(n=3, spread=14))],
                            [("curtain", 3.0, {}), ("spiral", 4.0, dict(arms=3, dur=2.0)), ("laser", 3.6, {})]]),
}
BOSSES = {
    "scrapmonarch": dict(name="THE SCRAPMONARCH", hp=[200, 180, 160], w=30, h=34, core=(-6, 0, 8, 8),
                         move=["hover", "hover", "track"],
                         atk=[[("aim", 1.4, dict(n=3, spread=16)), ("lob", 2.5, dict(n=5))],
                              [("ring", 2.2, dict(n=12)), ("sweep", 5.0, {}), ("aim", 1.2, dict(n=1, kind="orb"))],
                              [("spiral", 4.0, dict(arms=3, dur=2.4)), ("spawn", 5.0, dict(kind="darter", n=4)),
                               ("lob", 3.0, dict(n=6))]]),
    "mothergland": dict(name="MOTHER GLAND", hp=[220, 200, 180], w=30, h=30, core=(-8, 0, 8, 8),
                        move=["bob", "hover", "bob"],
                        atk=[[("spawn", 3.0, dict(kind="spore", n=4)), ("ring", 2.4, dict(n=10))],
                             [("spawn", 6.0, dict(kind="tendril", n=1)), ("aim", 1.6, dict(n=5, spread=24))],
                             [("spiral", 4.5, dict(arms=4, dur=2.6)), ("rain", 3.0, dict(n=8)),
                              ("ring", 3.5, dict(n=14))]]),
    "dreadkiln": dict(name="DREADKILN", hp=[240, 220, 200], w=34, h=36, core=(-8, -6, 8, 8),
                      move=["still", "hover", "hover"],
                      atk=[[("aim", 1.8, dict(n=3, spread=20, kind="orb")), ("seek", 4.0, dict(n=2))],
                           [("laser", 3.0, {}), ("aim", 2.0, dict(n=7, spread=50))],
                           [("sweep", 4.0, {}), ("seek", 3.5, dict(n=3)), ("ring", 3.0, dict(n=16))]]),
    "drownedbell": dict(name="THE DROWNED BELL", hp=[240, 220, 220], w=28, h=30, core=(0, 9, 8, 6),
                        move=["bob", "hover", "track"],
                        atk=[[("ring", 2.0, dict(n=12)), ("mines", 4.5, dict(n=3))],
                             [("aim", 1.5, dict(n=5, spread=20)), ("curtain", 3.5, {})],
                             [("spiral", 3.5, dict(arms=2, dur=2.4)), ("ring", 2.8, dict(n=18)),
                              ("mines", 5.0, dict(n=2))]]),
    "cinderheart": dict(name="CINDER HEART", hp=[260, 240, 220], w=26, h=26, core=(0, 0, 10, 10),
                        move=["hover", "eight", "hover"],
                        atk=[[("aim", 1.4, dict(n=3, spread=18)), ("orbit", 9.0, dict(n=6))],
                             [("rain", 2.2, dict(n=10)), ("ring", 2.6, dict(n=12)), ("orbit", 10.0, dict(n=4))],
                             [("spiral", 3.5, dict(arms=3, dur=2.2)), ("spawn", 4.0, dict(kind="comet", n=3)),
                              ("aim", 1.4, dict(n=1, kind="orb"))]]),
    "ambersovereign": dict(name="THE AMBER SOVEREIGN", hp=[260, 250, 230], w=32, h=30, core=(-6, -4, 8, 8),
                           move=["hover", "track", "hover"],
                           atk=[[("spawn", 4.0, dict(kind="drone", n=6)), ("aim", 1.5, dict(n=3, spread=16))],
                                [("spawn", 3.5, dict(kind="lancer", n=2)), ("ring", 2.6, dict(n=14))],
                                [("curtain", 3.0, {}), ("spiral", 4.0, dict(arms=2, dur=2.5)),
                                 ("spawn", 5.0, dict(kind="drone", n=4))]]),
    "chronoprism": dict(name="CHRONOPRISM", hp=[280, 260, 240], w=26, h=30, core=(0, 0, 8, 8),
                        move=["eight", "still", "eight"],
                        atk=[[("sweep", 4.0, {}), ("aim", 1.6, dict(n=3, spread=16))],
                             [("blink", 3.0, {}), ("ring", 2.2, dict(n=16))],
                             [("spiral", 3.0, dict(arms=3, dur=2.2, alt=1)), ("laser", 3.5, {}),
                              ("spawn", 6.0, dict(kind="phantom", n=2))]]),
    "voidengine": dict(name="THE VOID ENGINE", hp=[300, 280, 260, 260], w=34, h=40, core=(-6, 0, 10, 10),
                       move=["hover", "hover", "track", "eight"],
                       atk=[[("aim", 1.4, dict(n=5, spread=22)), ("laser", 3.5, {})],
                            [("spiral", 3.5, dict(arms=4, dur=2.4)), ("seek", 4.0, dict(n=3)), ("curtain", 5.0, {})],
                            [("sweep", 3.5, {}), ("ring", 2.4, dict(n=18)), ("spawn", 8.0, dict(kind="sentinel", n=1))],
                            [("spiral", 2.6, dict(arms=5, dur=2.0, alt=1)), ("rain", 2.6, dict(n=10)),
                             ("aim", 1.2, dict(n=3, spread=14, kind="orb")), ("laser", 3.0, {})]]),
}


def make_enemy(kind, x, y):
    hp, score, w, h, fl = ESPEC[kind]
    e = Enemy(kind, x, y, hp, score, w, h)
    e.anch = "a" in fl
    e.inv = "i" in fl
    e.solid = "s" in fl
    return e


# ---------------------------------------------------------------------------------------------
# Enemy behaviours: f(g, e) once per step, in field coordinates (x grows to the right, y down)
# ---------------------------------------------------------------------------------------------
def fire_timer(g, e, every, first=0.6):
    """True when the enemy should shoot now (on screen, not too close to the left edge)."""
    if "fired" not in e.data:
        e.data["fired"] = 1
        e.fire = every * first * g.rnd.uniform(0.6, 1.4)
    e.fire -= DT * g.fire_k
    if e.fire <= 0:
        e.fire = every * g.rnd.uniform(0.75, 1.25)
        return 10 < e.x < FW - 3 and 0 < e.y < FH and abs(e.x - g.px) + abs(e.y - g.py) > 16
    return False


def on_ground(g, e):
    """Keep a terrain unit on the floor (or the ceiling when e.ceil)."""
    if e.ceil:
        e.y = g.ceil_at(e.x) + e.h / 2
    else:
        e.y = g.floor_at(e.x) - e.h / 2


def b_darter(g, e):
    e.x -= 34 * DT
    e.y = e.st + 9 * math.sin(e.t * 3.2 + e.data.get("ph", 0))
    if fire_timer(g, e, 4.0, 1.2):
        g.aimed(e.x, e.y, 1, 0, 36)


def b_scrapper(g, e):
    e.x += e.vx * DT
    e.y += e.vy * DT
    if e.y < 4 or e.y > FH - 4:
        e.vy = -e.vy


def b_turret(g, e):
    on_ground(g, e)
    if fire_timer(g, e, 2.3):
        g.aimed(e.x, e.y + (2 if e.ceil else -2), 1, 0, 34)


def b_strider(g, e):
    if e.t > e.data.get("turn", 0):
        e.data["turn"] = e.t + g.rnd.uniform(1.0, 2.4)
        e.vx = g.rnd.choice((-8.0, 6.0, -4.0))
    e.x += e.vx * DT
    on_ground(g, e)
    if fire_timer(g, e, 2.8):
        g.aimed(e.x, e.y - 2, 3, 18, 32)


def b_spinner(g, e):
    tx = e.data.setdefault("tx", g.rnd.uniform(FW * 0.6, FW * 0.85))
    if e.t < 7:
        e.x += (tx - e.x) * 1.5 * DT
        e.y = e.st + 4 * math.sin(e.t * 1.3)
        if fire_timer(g, e, 1.8):
            g.ring(e.x, e.y, 6, 26, e.t)
    else:
        e.x += 40 * DT
        e.y -= 10 * DT


def b_polyp(g, e):
    on_ground(g, e)
    if fire_timer(g, e, 2.6) and len(g.enemies) < 60:
        s = g.add("spore", e.x, e.y + (3 if e.ceil else -3))
        s.vy = 10 if e.ceil else -10
        g.sfx("spawn", 0.2)


def b_spore(g, e):
    dx, dy = g.px - e.x, g.py - e.y
    d = math.hypot(dx, dy) or 1
    e.vx += dx / d * 30 * DT
    e.vy += dy / d * 30 * DT
    sp = math.hypot(e.vx, e.vy)
    if sp > 20:
        e.vx, e.vy = e.vx / sp * 20, e.vy / sp * 20
    e.x += e.vx * DT
    e.y += e.vy * DT
    if e.t > 7:
        e.dead = True


def b_snake(g, e):
    fast = e.kind == "eel"
    e.x -= (30 if fast else 22) * DT
    e.y = e.st + (10 if fast else 14) * math.sin(e.t * (3.2 if fast else 2.2) + e.data.get("ph", 0))
    tr = e.data.setdefault("trail", [])
    tr.append((e.x, e.y))
    if len(tr) > 200:
        del tr[:50]
    if fire_timer(g, e, 3.0):
        g.aimed(e.x, e.y, 1, 0, 34)


def b_seg(g, e):
    head = e.data["head"]
    tr = head.data.get("trail", [])
    k = e.data["k"] * (6 if head.kind == "eel" else 7)
    if head.dead:
        e.x -= 26 * DT
        return
    if len(tr) > k:
        e.x, e.y = tr[-1 - k]
    else:
        e.x = head.x + 5 * e.data["k"]
        e.y = head.y


def b_blister(g, e):
    on_ground(g, e)
    if fire_timer(g, e, 3.2):
        g.aimed(e.x, e.y, 1, 0, 26, "orb")


def b_leech(g, e):
    if e.t < 0.9:
        e.x -= 32 * DT
        return
    dx, dy = g.px - e.x, g.py - e.y
    d = math.hypot(dx, dy) or 1
    sp = min(52, 20 + e.t * 14)
    if not e.data.get("locked") and dx < -6:
        e.vx, e.vy = dx / d * sp, dy / d * sp
    else:
        e.data["locked"] = True
        e.vx -= 20 * DT
    e.x += e.vx * DT
    e.y += e.vy * DT


def b_vent(g, e):
    on_ground(g, e)
    cyc = (e.t + e.data.get("ph", 0)) % 3.2
    e.data["warn"] = 1.6 < cyc < 2.2
    on = cyc >= 2.2
    if on and not e.data.get("on") and 0 < e.x < FW:
        g.sfx("flame", 0.3)
    e.data["on"] = on
    if on:
        y0 = e.y + 2 if e.ceil else e.y - 2 - 22
        g.hazards.append((e.x - 2.5, y0, e.x + 2.5, y0 + 22))
        if g.rnd.random() < 0.8:
            g.part(e.x + g.rnd.uniform(-2, 2), y0 + g.rnd.uniform(0, 22), g.rnd.uniform(-6, 6), (8 if e.ceil else -8),
                   0.3, g.rnd.choice(((255, 210, 80), (255, 140, 40), (255, 90, 30))))
    elif e.data["warn"] and g.rnd.random() < 0.3:
        g.part(e.x + g.rnd.uniform(-2, 2), e.y + (2 if e.ceil else -2), 0, (6 if e.ceil else -6), 0.4, (120, 110, 100))


def b_hook(g, e):
    top = g.ceil_at(e.x)
    e.data["top"] = top
    e.y = top + 8 + 12 * (0.5 - 0.5 * math.cos(e.t * 1.4 + e.data.get("ph", 0)))


def b_rivet(g, e):
    if not e.data.get("dive"):
        e.x -= 50 * DT
        if e.x < e.data.setdefault("tx", g.rnd.uniform(60, 90)):
            dx, dy = g.px - e.x, g.py - e.y
            d = math.hypot(dx, dy) or 1
            e.vx, e.vy = dx / d * 58, dy / d * 58
            e.data["dive"] = True
            if g.rnd.random() < 0.5 * g.fire_k:
                g.aimed(e.x, e.y, 1, 0, 40)
    else:
        e.x += e.vx * DT
        e.y += e.vy * DT


def b_cannon(g, e):
    on_ground(g, e)
    if fire_timer(g, e, 3.2) and math.hypot(g.px - e.x, g.py - e.y) > 30:   # no point-blank orb fans
        g.aimed(e.x - 3, e.y + (2 if e.ceil else -2), 3, 22, 28, "orb")
        g.sfx("eorb", 0.15)


def b_jelly(g, e):
    e.x -= 10 * DT
    e.y = e.st + 6 * math.sin(e.t * 1.4 + e.data.get("ph", 0))
    if fire_timer(g, e, 2.8):
        g.ring(e.x, e.y, 8, 20, e.t)


def b_mine(g, e):
    e.x -= 8 * DT
    e.y = e.st + 4 * math.sin(e.t * 1.1 + e.data.get("ph", 0))
    if "arm" in e.data:
        if e.t > e.data["arm"]:
            g.ring(e.x, e.y, 10, 26, 0)
            g.kill(e, quiet=True)
    elif math.hypot(g.px - e.x, g.py - e.y) < 13 and g.alive:
        e.data["arm"] = e.t + 0.45
        e.flash = 0.45


def b_angler(g, e):
    if e.x > e.data.setdefault("tx", g.rnd.uniform(70, 92)):
        e.x -= 14 * DT
    else:
        e.x -= 3 * DT
        e.y += clamp(g.py - e.y, -1, 1) * 9 * DT
    if fire_timer(g, e, 2.4):
        g.aimed(e.x - 5, e.y, 1, 0, 30, "orb")


def b_rock(g, e):
    e.x += e.vx * DT
    e.y += e.vy * DT
    if (e.y < e.h / 2 and e.vy < 0) or (e.y > FH - e.h / 2 and e.vy > 0):
        e.vy = -e.vy


def b_comet(g, e):
    if e.t < 0.8:
        e.x = FW - 2
        if g.rnd.random() < 0.6:
            g.part(FW - 1, e.y + g.rnd.uniform(-2, 2), -20, 0, 0.2, (200, 240, 255))
        return
    e.x -= 110 * DT
    if g.rnd.random() < 0.9:
        g.part(e.x + 4, e.y + g.rnd.uniform(-1.5, 1.5), 30, 0, 0.35, g.rnd.choice(((120, 200, 255), (220, 240, 255))))


def b_miner(g, e):
    st = e.data.setdefault("step", 0)
    if st >= 3:
        e.y += (-30 if e.y < FH / 2 else 30) * DT
        e.x += 10 * DT
        return
    if "next" not in e.data:
        e.data["next"] = e.t + 1.3
        e.data["ty"] = clamp(g.py, 8, FH - 8)
    e.x += (FW - 14 - e.x) * 2 * DT
    if e.t < e.data["next"]:
        e.y += (e.data["ty"] - e.y) * 3 * DT
    elif not e.data.get("shot"):
        e.data["shot"] = True
        g.laser(e, e.x - 5, e.y, 3.0)
    elif e.t > e.data["next"] + 2.0:
        e.data.pop("next")
        e.data.pop("shot")
        e.data["step"] = st + 1


def b_crawler(g, e):
    e.x -= 9 * DT
    on_ground(g, e)
    if fire_timer(g, e, 3.0):
        g.aimed(e.x, e.y, 1, 0, 30)


def b_drone(g, e):
    c = e.data.get("center")
    if c is not None:                      # one of a swarm circling a moving centre
        a = e.data["a"] + e.t * 2.4
        e.x = c[0] - 15 * e.t + 9 * math.cos(a)
        e.y = c[1] + 7 * math.sin(a) + 5 * math.sin(e.t * 0.9)
        if fire_timer(g, e, 5.0):
            g.aimed(e.x, e.y, 1, 0, 32)
        return
    dx, dy = g.px - e.x, g.py - e.y
    d = math.hypot(dx, dy) or 1
    e.vx += (dx / d * 40 - e.vx * 0.6) * DT * 2
    e.vy += (dy / d * 40 - e.vy * 0.6) * DT * 2
    e.x += (e.vx - 14) * DT
    e.y += e.vy * DT
    if e.t > 9:
        e.y += 40 * DT


def b_lancer(g, e):
    if e.t < 1.3:
        e.x += (FW - 10 - e.x) * 3 * DT
        e.y += clamp(g.py - e.y, -1, 1) * 30 * DT
        if e.t > 0.9 and g.rnd.random() < 0.5:
            g.part(e.x + 6, e.y, 20, g.rnd.uniform(-5, 5), 0.2, (255, 230, 120))
    else:
        if not e.data.get("go"):
            e.data["go"] = True
            g.sfx("launch", 0.2)
        e.x -= 120 * DT


def b_larva(g, e):
    on_ground(g, e)
    if fire_timer(g, e, 2.8) and len(g.enemies) < 60:
        d = g.add("drone", e.x, e.y + (3 if e.ceil else -3))
        d.vy = 20 if e.ceil else -20


def b_wall(g, e):
    pass


def b_shard(g, e):
    e.x -= 14 * DT
    e.y = e.st + 5 * math.sin(e.t * 1.7 + e.data.get("ph", 0))
    if fire_timer(g, e, 3.2):
        g.aimed(e.x, e.y, 2, 10, 36)


def b_phantom(g, e):
    cyc = e.t % 3.1
    n = int(e.t // 3.1)
    if n >= 3:
        e.ghost = True
        e.dead = True
        return
    e.ghost = cyc > 1.8
    if cyc < 0.02 and n > 0:
        e.x = g.rnd.uniform(FW * 0.5, FW - 8)
        e.y = g.rnd.uniform(g.ceil_at(e.x) + 8, g.floor_at(e.x) - 8)
    if n == 0 and cyc < 1.8:
        e.x += (FW * 0.78 - e.x) * 2 * DT
    if abs(cyc - 0.9) < DT / 2 + 1e-9:
        g.aimed(e.x, e.y, 3, 14, 34)


def b_clock(g, e):
    tx = e.data.setdefault("tx", g.rnd.uniform(FW * 0.62, FW * 0.82))
    if e.t < 8:
        e.x += (tx - e.x) * 1.4 * DT
        if e.t > 1.2:
            e.data["acc"] = e.data.get("acc", 0) + DT * g.fire_k
            while e.data["acc"] > 0.16:
                e.data["acc"] -= 0.16
                a = e.t * 2.0
                for k in range(2):
                    g.ebullet(e.x, e.y, a + k * math.pi, 26)
    else:
        e.x += 30 * DT


def b_mover(g, e):
    """Pistons and prism walls: reach out of the floor or the ceiling and pull back."""
    lo, hi = e.data["lo"], e.data["hi"]
    k = 0.5 - 0.5 * math.cos(e.t * e.data["sp"] + e.data["ph"])
    ln = lo + (hi - lo) * k
    if e.ceil:
        top = -2
        bot = g.ceil_at(e.x) + ln
    else:
        bot = FH + 2
        top = g.floor_at(e.x) - ln
    e.y, e.h = (top + bot) / 2, max(1.0, bot - top)


def b_node(g, e):
    on_ground(g, e)
    o = e.data.get("other")
    if e.ceil and o is not None and not o.dead:
        y0, y1 = e.y + 2, o.y - 2
        if y1 > y0:
            g.hazards.append((e.x - 1.2, y0, e.x + 1.2, y1))
    if fire_timer(g, e, 3.5):
        g.aimed(e.x, e.y, 1, 0, 30)


def b_sentinel(g, e):
    tx = e.data.setdefault("tx", FW - 16)
    if e.t < 9:
        e.x += (tx - e.x) * 1.2 * DT
        e.y = e.st + 8 * math.sin(e.t * 0.9)
        if fire_timer(g, e, 2.0):
            g.aimed(e.x - 6, e.y, 5, 14, 30)
        if e.t % 1.4 < DT:
            g.aimed(e.x - 6, e.y, 1, 0, 34, "orb")
    else:
        e.x += 30 * DT


def b_ferry(g, e):
    e.x -= 20 * DT
    e.y = e.st + 6 * math.sin(e.t * 2)


def b_seeker(g, e):
    dx, dy = g.px - e.x, g.py - e.y
    d = math.hypot(dx, dy) or 1
    e.vx += (dx / d * 22 - e.vx) * DT
    e.vy += (dy / d * 22 - e.vy) * DT
    e.x += e.vx * DT
    e.y += e.vy * DT
    if e.t > 8:
        g.kill(e, quiet=True)


def b_orbiter(g, e):
    b = e.data["boss"]
    if b.dead:
        g.kill(e, quiet=True)
        return
    a = e.data["a"] + e.t * 1.6
    r = 20 + 3 * math.sin(e.t * 2)
    e.x, e.y = b.x + r * math.cos(a), b.y + r * 0.85 * math.sin(a)


BEHAVE = {"darter": b_darter, "scrapper": b_scrapper, "turret": b_turret, "strider": b_strider, "spinner": b_spinner,
          "polyp": b_polyp, "spore": b_spore, "tendril": b_snake, "eel": b_snake, "tseg": b_seg, "eseg": b_seg,
          "blister": b_blister, "leech": b_leech, "vent": b_vent, "hook": b_hook, "rivet": b_rivet, "cannon": b_cannon,
          "jelly": b_jelly, "mine": b_mine, "angler": b_angler, "rockL": b_rock, "rockM": b_rock, "rockS": b_rock,
          "comet": b_comet, "miner": b_miner, "crawler": b_crawler, "drone": b_drone, "lancer": b_lancer,
          "larva": b_larva, "comb": b_wall, "plate": b_wall, "shard": b_shard, "phantom": b_phantom, "clock": b_clock,
          "prism": b_mover, "piston": b_mover, "node": b_node, "sentinel": b_sentinel, "ferry": b_ferry,
          "seeker": b_seeker, "orbiter": b_orbiter}


class Item:
    __slots__ = ("x", "y", "kind", "color", "t", "dead", "st")

    def __init__(self, x, y, kind, color=None):
        self.x, self.y, self.kind, self.color = x, y, kind, color
        self.t, self.dead, self.st = 0.0, False, y


class Pod:
    """The Warden pod: 'enter' (flies in), 'free' (hovers, fires on its own), 'front' / 'back' (docked),
    'out' (launched), 'return' (called back)."""
    __slots__ = ("x", "y", "state", "vx", "cd", "t")

    def __init__(self, x, y, state):
        self.x, self.y, self.state = x, y, state
        self.vx, self.cd, self.t = 0.0, 0.0, 0.0


class Inp:
    """One step of input: direction, shots, the charge, pod and bomb buttons."""
    __slots__ = ("dx", "dy", "fire", "charge", "pod", "bomb")

    def __init__(self, dx=0, dy=0, fire=False, charge=False, pod=False, bomb=False):
        self.dx, self.dy, self.fire, self.charge, self.pod, self.bomb = dx, dy, fire, charge, pod, bomb


_STAGE_CACHE = {}


def stage_data(si):
    if si not in _STAGE_CACHE:
        c, f = gen_terrain(si)
        _STAGE_CACHE[si] = (c, f, build_events(si, c, f))
    return _STAGE_CACHE[si]


POD_CD = {None: 0.5, "red": 0.2, "blue": 0.28, "yellow": 0.36, "green": 0.3, "violet": 0.42, "white": 0.28}
SMALL_SHOTS = ("bolt", "bitbolt", "ring", "needle", "frag", "ray", "scatter")


class Game:
    def __init__(self, stage=0, diff="normal", demo=False, god=False, sound=True, seed=None):
        self.diff = diff
        self.d = DIFF[diff]
        self.demo, self.god = demo, god
        self.sound = sound and not demo
        self.rnd = random.Random(seed)
        self.score = 0
        self.lives = self.d["lives"]
        self.bombs = self.d["bombs"]
        self.next_life, self.life_gap = 60000, 60000     # extra ships at 60k, 180k, 360k, 600k, ...
        self.has_pod, self.pod_color, self.pod_lv = False, None, 0
        self.missile = self.crawl = self.nbits = 0
        self.speed = 1
        self.shield = False
        self.dmg_mult = 1.0
        self.paused = self.help = False
        self.continues = 0
        self.t = 0.0
        self.shake = self.flash = 0.0
        self.flash_c = WHITE
        self.pod = None
        self.shots_fired = 0
        if stage > 0 and not demo:      # starting further in: a loadout that matches the stage
            self.has_pod, self.pod_color, self.pod_lv = True, "red", min(3, 1 + stage // 3)
            self.missile = 1 if stage >= 2 else 0
            self.nbits = 1 if stage >= 3 else 0
            self.crawl = 1 if stage >= 5 else 0
            self.speed = 2
        self.load_stage(stage)

    # --- stage set-up --------------------------------------------------------------------------
    def load_stage(self, si):
        self.si = si
        self.st = STAGES[si]
        self.ceil, self.floor, self.events = stage_data(si)
        self.N = len(self.ceil)
        self.wob = self.st["terrain"] == "flesh"
        self.water = self.st.get("water")
        base, step = self.d.get("ramp", (0.6, 0.08))
        self.fire_k = self.d["fire"] * (base + step * si)          # enemies shoot more as the stages go on
        self.bspeed = self.d["bspeed"] * (0.86 + 0.04 * si)
        self.cam = 0.0
        self.scroll = self.st["speed"]
        self.ev_i = 0
        self.checkpoint = 0.0
        self.phase, self.phase_t = "play", 0.0
        self.mid, self.mid_done = None, False
        self.boss, self.boss_due = None, False
        self.kills = self.spawned = self.stage_deaths = 0
        self.tally = None
        self.banners = []
        self.clear_field()
        self.spawn_player()
        self.banner("STAGE %d" % (si + 1), 3.0, self.st["accent"], self.st["name"])

    def clear_field(self):
        self.enemies, self.ebul, self.shots, self.beams, self.arcs, self.items = [], [], [], [], [], []
        self.lasers, self.sweeps, self.hazards, self.waves = [], [], [], []
        self.parts = getattr(self, "parts", [])
        self.blasts = getattr(self, "blasts", [])

    def spawn_player(self):
        self.px, self.py = -8.0, clamp((self.ceil_at(18) + self.floor_at(18)) / 2, 10, FH - 10)
        self.alive = True
        self.entering = 0.65
        self.inv = 2.6
        self.charge = 0.0
        self.fire_cd = self.pod_cd = self.missile_cd = self.crawl_cd = self.bit_cd = 0.0
        self.bit_a = 0.0
        self.respawn_t = 0.0
        self.pod = Pod(self.px + 9, self.py, "front") if self.has_pod else None

    def banner(self, text, dur, col, sub=None):
        self.banners = [b for b in self.banners if b[0] != text]
        self.banners.append([text, self.t + dur, col, sub])

    def sfx(self, name, gap=0.04):
        if self.sound:
            SND.play(name, gap=gap)

    # --- the terrain ---------------------------------------------------------------------------
    def ceil_at(self, x):
        i = int(self.cam + x)
        i = 0 if i < 0 else self.N - 1 if i >= self.N else i
        c = self.ceil[i]
        if self.wob and c > 0.5:
            c += 1.5 + 1.5 * math.sin(self.t * 1.8 + i * 0.05)
        return c

    def floor_at(self, x):
        i = int(self.cam + x)
        i = 0 if i < 0 else self.N - 1 if i >= self.N else i
        f = self.floor[i]
        if self.wob and f < FH - 0.5:
            f -= 1.5 + 1.5 * math.sin(self.t * 1.7 + i * 0.05 + 2)
        return f

    def in_wall(self, x, y):
        return y < self.ceil_at(x) or y > self.floor_at(x)

    # --- spawning --------------------------------------------------------------------------
    def add(self, kind, x, y):
        e = make_enemy(kind, x, y)
        if not e.inv:
            e.hp = e.maxhp = e.hp * self.d["hp"]
        self.enemies.append(e)
        if e.score:
            self.spawned += 1
        return e

    def band(self, x):
        lo, hi = self.ceil_at(x) + 6, self.floor_at(x) - 6
        if hi < lo:
            lo = hi = (lo + hi) / 2
        return lo, hi

    def spawn_events(self):
        edge = self.cam + FW
        ev = self.events
        busy = self.mid is not None and not self.mid.dead
        while self.ev_i < len(ev) and ev[self.ev_i][0] <= edge:
            e = ev[self.ev_i]
            self.ev_i += 1
            typ = e[1]
            if typ == "check":
                if self.checkpoint < e[0] - FW:
                    self.checkpoint = e[0] - FW
                    self.banner("CHECKPOINT", 1.5, (150, 230, 160))
                    self.sfx("checkpoint")
            elif typ == "boss":
                self.boss_due = True
            elif typ == "mid":
                if not self.mid_done and not busy:
                    self.start_boss(self.st["midboss"], True)
                    busy = True
            elif busy:
                continue
            elif typ == "wave":
                self.spawn_wave(e[2], e[3], e[4])
            elif typ == "ground":
                self.spawn_ground(e[0], e[2], e[3])
            elif typ == "special":
                self.spawn_special(e[0], e[2], e[3])
            elif typ == "carrier":
                lo, hi = self.band(FW + 8)
                f = self.add("ferry", FW + 8, clamp(e[2], lo, hi))
                f.st = f.y

    def spawn_wave(self, kind, form, y):
        X = FW + 6
        lo, hi = self.band(X)
        y = clamp(y, lo, hi)
        R = self.rnd
        if form == "sine":
            yy = clamp(y, lo + 9, max(lo + 9, hi - 9))
            for j in range(5):
                e = self.add(kind, X + j * 9, yy)
                e.st, e.data["ph"] = yy, j * 0.7
        elif form == "line":
            for j in range(4):
                self.add(kind, X + j * 10, y)
        elif form == "vee":
            for j, (dx, dy) in enumerate(((0, 0), (6, -5), (6, 5), (12, -10), (12, 10))):
                self.add(kind, X + dx, clamp(y + dy, lo, hi))
        elif form == "scatter":
            for j in range(3):
                e = self.add(kind, X + j * 14, R.uniform(lo, hi))
                e.vx, e.vy = -R.uniform(18, 26), R.choice((-1, 1)) * R.uniform(3, 9)
        elif form == "snake":
            yy = clamp(y, lo + 10, max(lo + 10, hi - 10))
            head = self.add(kind, X, yy)
            head.st, head.data["ph"] = yy, R.uniform(0, TAU)
            seg = "tseg" if kind == "tendril" else "eseg"
            for k in range(1, 9):
                s = self.add(seg, X + 5 * k, yy)
                s.data["head"], s.data["k"] = head, k
                head.data.setdefault("segs", []).append(s)
        elif form == "cluster":
            for j in range(6):
                e = self.add(kind, X + R.uniform(0, 10), clamp(y + R.uniform(-6, 6), lo, hi))
                e.vx = -14
        elif form == "group":
            for j in range(3):
                e = self.add(kind, X + j * 12, clamp(y + (j - 1) * 12, lo, hi))
                e.st, e.data["ph"] = e.y, j * 1.3
        elif form == "field":
            if kind == "mine":
                for j in range(5):
                    e = self.add(kind, X + j * 9, R.uniform(lo, hi))
                    e.st, e.data["ph"] = e.y, R.uniform(0, TAU)
            else:
                for j in range(R.randint(2, 3)):
                    e = self.add(kind, X + 4 + j * 18, R.uniform(lo, hi))
                    e.vx, e.vy = -R.uniform(14, 24), R.uniform(-6, 6)
        elif form == "burst":
            for j in range(3):
                e = self.add(kind, FW - 2, R.uniform(lo, hi))
                e.t = -0.45 * j
        elif form == "swarm":
            c = [X + 10, y, 0]
            for j in range(6):
                e = self.add(kind, X + 10, y)
                e.data["center"], e.data["a"] = c, j * TAU / 6
        else:  # single
            e = self.add(kind, X + 2, y)
            e.st = y
            if kind == "rockL":
                e.vx, e.vy = -18, R.uniform(-5, 5)

    def spawn_ground(self, wx, kind, floor_first):
        i = clamp(int(wx), 0, self.N - 1)
        has_f, has_c = self.floor[i] < FH - 2, self.ceil[i] > 2
        if kind in ("strider", "crawler"):
            has_c = has_c and kind == "crawler"
        if floor_first and has_f:
            ceil = False
        elif has_c:
            ceil = True
        elif has_f:
            ceil = False
        else:
            return None
        e = self.add(kind, wx - self.cam, 0)
        e.ceil = e.fv = ceil
        on_ground(self, e)
        return e

    def spawn_special(self, wx, kind, r):
        x = wx - self.cam
        R = self.rnd
        if kind == "vent":
            e = self.spawn_ground(wx, "vent", True)
            if e:
                e.data["ph"] = r * 3.2
        elif kind == "hook":
            e = self.add("hook", x, 10)
            e.data["ph"] = r * TAU
            e.anch = True
        elif kind in ("comb", "plate"):
            for col in range(2):
                xx = x + col * 6
                top, bot = self.ceil_at(xx), self.floor_at(xx)
                y = top + 3
                while y < bot - 2:
                    e = self.add(kind, xx, y)
                    if R.random() < 0.25:
                        e.hp = 1
                    y += 6
        elif kind in ("prism", "piston"):
            gap = self.floor_at(x) - self.ceil_at(x)
            e = self.add(kind, x, FH / 2)
            e.ceil = r < 0.5
            e.data.update(lo=3, hi=max(6, gap - 22), sp=R.uniform(0.9, 1.4), ph=R.uniform(0, TAU))
            b_mover(self, e)
        elif kind == "node":
            a = self.add("node", x, 0)
            b = self.add("node", x, 0)
            a.ceil = a.fv = True
            on_ground(self, a)
            on_ground(self, b)
            a.data["other"], b.data["other"] = b, a

    # --- enemy fire ----------------------------------------------------------------------------
    def ebullet(self, x, y, a, sp, kind="pel"):
        if len(self.ebul) < 420:
            sp *= self.bspeed
            self.ebul.append(Bullet(x, y, math.cos(a) * sp, math.sin(a) * sp, kind))

    def aimed(self, x, y, n, spread, sp, kind="pel"):
        base = math.atan2(self.py - y, self.px - x)
        st = math.radians(spread)
        for k in range(n):
            self.ebullet(x, y, base + (k - (n - 1) / 2) * st, sp, kind)
        self.sfx("eshot", 0.08)

    def ring(self, x, y, n, sp, off=0.0):
        for k in range(n):
            self.ebullet(x, y, off + k * TAU / n, sp)
        self.sfx("eorb", 0.1)

    def laser(self, owner, x, y, h):
        self.lasers.append(dict(o=owner, dx=x - owner.x, y=y, h=h, t=0.0, warn=0.9, dur=0.8, fired=False))
        self.sfx("laserwarn", 0.2)

    # --- effects ---------------------------------------------------------------------------
    def part(self, x, y, vx, vy, life, c):
        if len(self.parts) < 500:
            self.parts.append([x, y, vx, vy, life, life, c])

    def explode(self, x, y, size, cols=None):
        cols = cols or ((255, 250, 210), (255, 200, 90), (250, 120, 40), (180, 60, 40))
        self.blasts.append([x, y, size, 0.0, 0.22 + size * 0.035, cols])
        R = self.rnd
        for _ in range(min(40, int(5 + size * 2.5))):
            a = R.uniform(0, TAU)
            sp = R.uniform(8, 20 + size * 5)
            self.part(x, y, math.cos(a) * sp, math.sin(a) * sp, R.uniform(0.2, 0.5 + size * 0.04), R.choice(cols))
        self.shake = max(self.shake, min(3.0, size * 0.22))

    def sparks(self, x, y, c, n=4):
        for _ in range(n):
            a = self.rnd.uniform(0, TAU)
            self.part(x, y, math.cos(a) * 26, math.sin(a) * 26, 0.15, c)

    def add_score(self, n):
        self.score += int(n)
        while self.score >= self.next_life:
            self.life_gap += 60000
            self.next_life += self.life_gap
            self.lives += 1
            self.sfx("life")
            self.banner("EXTRA SHIP", 1.6, (255, 236, 120))

    # --- damage ----------------------------------------------------------------------------
    def damage(self, e, dmg, hx=None, hy=None):
        if e.inv or e.dead or e.ghost:
            return False
        b = e.boss
        if b is not None:
            if b["state"] != "fight":
                return False
            cx, cy, cw, ch = b["bd"]["core"]
            if hx is not None and not (abs(hx - (e.x + cx)) < cw / 2 + 2 and abs(hy - (e.y + cy)) < ch / 2 + 2):
                dmg *= 0.25
        e.hp -= dmg * self.dmg_mult
        e.flash = 0.07
        if e.hp <= 0:
            if b is not None:
                self.boss_down(e)
            else:
                self.kill(e)
            return True
        return False

    def kill(self, e, quiet=False):
        if e.dead:
            return
        e.dead = True
        size = max(1.0, (e.w * e.h) ** 0.5 / 2.2)
        if not quiet:
            self.add_score(e.score)
            if e.score:
                self.kills += 1
            self.sfx("boom" if size > 3 else "pop", 0.03)
        self.explode(e.x, e.y, size)
        k = e.kind
        if k == "blister":
            self.ring(e.x, e.y, 8, 24, self.rnd.uniform(0, 1))
        elif k == "mine" and not quiet:
            self.ring(e.x, e.y, 6, 22, 0)
        elif k in ("rockL", "rockM"):
            small = "rockM" if k == "rockL" else "rockS"
            for s in (-1, 1):
                r = self.add(small, e.x, e.y + s * 2)
                r.vx, r.vy = e.vx * 1.1 - 4, s * self.rnd.uniform(8, 16)
        elif k in ("tendril", "eel"):
            for s in e.data.get("segs", []):
                if not s.dead:
                    self.kill(s, quiet)
        elif k == "ferry":
            self.drop_item(e.x, e.y)
        elif k == "orbiter":
            pass

    def drop_item(self, x, y):
        R = self.rnd
        on_screen = any(i.kind == "crystal" for i in self.items)
        if not self.has_pod and not on_screen:
            self.items.append(Item(x, y, "crystal", R.choice(CRYSTALS)))
            return
        bag = (["crystal"] * 9 + ["missile"] * 2 + ["crawlbomb"] * 2 + ["bit"] * 2 + ["speed"] * 2 + ["shield"] * 2 +
               ["bomb"] * 1 + ["slow"] * 1 + ["gem"] * 1 + (["life"] if R.random() < 0.3 else []))
        kind = R.choice(bag)
        if kind == "speed" and self.speed >= 3:
            kind = R.choice(("slow", "crystal"))
        if kind == "crystal":
            self.items.append(Item(x, y, "crystal", R.choice(CRYSTALS)))
        else:
            self.items.append(Item(x, y, kind))

    def collect(self, it):
        it.dead = True
        k = it.kind
        if k == "crystal":
            self.sfx("crystal")
            if not self.has_pod:
                self.has_pod, self.pod_color, self.pod_lv = True, it.color, 1
                self.pod = Pod(-6, self.py, "enter")
                self.sfx("podin")
                self.banner("WARDEN POD", 1.6, CRYSTAL_C[it.color], CRYSTAL_NAME[it.color])
                return
            if self.pod is None:
                self.pod = Pod(-6, self.py, "enter")
            if it.color == self.pod_color:
                if self.pod_lv < 3:
                    self.pod_lv += 1
                else:
                    self.add_score(2000)
            else:
                self.pod_color = it.color
            self.banner("%s %d" % (CRYSTAL_NAME[self.pod_color], self.pod_lv), 1.4, CRYSTAL_C[self.pod_color])
            return
        col, letter, name = ITEMS[k]
        maxed = False
        if k == "missile":
            maxed = self.missile >= 2
            self.missile = min(2, self.missile + 1)
        elif k == "crawlbomb":
            maxed = self.crawl >= 2
            self.crawl = min(2, self.crawl + 1)
        elif k == "bit":
            maxed = self.nbits >= 2
            self.nbits = min(2, self.nbits + 1)
        elif k == "speed":
            maxed = self.speed >= 4
            self.speed = min(4, self.speed + 1)
        elif k == "slow":
            self.speed = max(1, self.speed - 1)
        elif k == "shield":
            self.shield = True
            self.sfx("shield")
        elif k == "bomb":
            maxed = self.bombs >= 5
            self.bombs = min(5, self.bombs + 1)
        elif k == "life":
            self.lives += 1
            self.sfx("life")
        elif k == "gem" or maxed:
            self.add_score(1000)
        self.sfx("powerup" if k not in ("gem", "slow") else "item")
        self.banner(name, 1.2, col)

    # --- the player ------------------------------------------------------------------------
    def update_player(self, inp):
        if not self.alive:
            self.respawn_t -= DT
            if self.respawn_t <= 0:
                self.after_death()
            return
        if self.entering > 0:
            self.entering -= DT
            self.px += 40 * DT
            self.inv = max(self.inv, 1.0)
        else:
            sp = SPEEDS[self.speed - 1]
            dx, dy = inp.dx, inp.dy
            if dx and dy:
                sp *= 0.7071
            self.px = clamp(self.px + dx * sp * DT, 5, FW - 9)
            self.py = clamp(self.py + dy * sp * DT, 3, FH - 3)
        self.inv = max(0.0, self.inv - DT)
        for a in ("fire_cd", "pod_cd", "missile_cd", "crawl_cd", "bit_cd"):
            setattr(self, a, getattr(self, a) - DT)
        if inp.charge and self.entering <= 0:
            old = self.charge
            self.charge = min(CHARGE_LV[3] + 0.6, self.charge + DT)
            for k, th in enumerate(CHARGE_LV):
                if old < th <= self.charge:
                    self.sfx("charge%d" % (k + 1))
            if self.charge > CHARGE_LV[0] and self.rnd.random() < 0.5:
                a = self.rnd.uniform(0, TAU)
                r = 6
                self.part(self.px + 8 + math.cos(a) * r, self.py + math.sin(a) * r, -math.cos(a) * 30,
                          -math.sin(a) * 30, 0.18, (200, 230, 255) if self.charge < CHARGE_LV[3] else (255, 140, 255))
        elif self.charge > 0:
            self.release_lance()
            self.charge = 0.0
        if inp.fire and self.fire_cd <= 0 and self.entering <= 0:
            self.fire_normal()
        if inp.pod:
            self.pod_button()
        if inp.bomb:
            self.smart_bomb()
        self.bit_a += 3.2 * DT

    def bits(self):
        a = self.bit_a
        return [(self.px + 2 + 10 * math.cos(a + k * math.pi), self.py + 8 * math.sin(a + k * math.pi))
                for k in range(self.nbits)]

    def fire_normal(self):
        self.fire_cd = 0.11
        self.shots_fired += 1
        self.shots.append(Shot(self.px + 8, self.py + 0.5, 165, 0, "bolt", 1.0, 1.0, 2.0, 1.0))
        self.sfx("shot", 0.07)
        p = self.pod
        if p is not None and p.state in ("front", "back") and self.pod_cd <= 0:
            self.pod_fire(p)
        if self.nbits and self.bit_cd <= 0:
            self.bit_cd = 0.22
            for bx, by in self.bits():
                self.shots.append(Shot(bx + 2, by, 150, 0, "bitbolt", 0.7, 1.0, 1.5, 1.0))
        if self.missile and self.missile_cd <= 0:
            self.missile_cd = 1.0 if self.missile == 1 else 0.75
            for k in range(2 * self.missile):
                up = -1 if k % 2 == 0 else 1
                s = Shot(self.px, self.py + up * 3, 30 + 8 * (k // 2), up * 40, "missile", 3.0, 2.2, 1.5, 1.2)
                self.shots.append(s)
            self.sfx("missile", 0.2)
        if self.crawl and self.crawl_cd <= 0:
            self.crawl_cd = 1.1 if self.crawl == 1 else 0.9
            for dirn in ((1,) if self.crawl == 1 else (1, -1)):
                s = Shot(self.px, self.py + dirn * 2, 22, 12 * dirn, "bomb", 4.0, 3.0, 1.8, 1.5)
                s.data = {"dir": dirn, "crawl": False}
                self.shots.append(s)
            self.sfx("bombdrop", 0.2)

    def targets(self):
        return [e for e in self.enemies if not e.dead and not e.ghost and not e.inv and -2 < e.x < FW + 2
                and (e.boss is None or e.boss["state"] == "fight")]

    def nearest(self, x, y, d=0, rng=999.0, exclude=()):
        best, bd = None, rng
        for e in self.targets():
            if e in exclude or (d > 0 and e.x < x - 4) or (d < 0 and e.x > x + 4):
                continue
            dist = math.hypot(e.x - x, e.y - y)
            if dist < bd:
                best, bd = e, dist
        return best

    def pod_fire(self, p, free=False):
        col, lv = self.pod_color, max(1, self.pod_lv)
        self.pod_cd = POD_CD[col] * (1.6 if free else 1.0)
        d = -1 if p.state == "back" else 1
        x, y = p.x + 3 * d, p.y
        sh = self.shots
        if col is None:
            sh.append(Shot(x, y, 150 * d, 0, "bitbolt", 0.8, 1.0, 1.5, 1.0))
        elif col == "red":
            angs = {1: (0, -12, 12), 2: (0, -10, 10, -22, 22), 3: (0, -8, 8, -18, 18, -30, 30)}[lv]
            for a in angs:
                r = math.radians(a)
                sh.append(Shot(x, y, math.cos(r) * 125 * d, math.sin(r) * 125, "ring", 1.3, 1.2, 1.8, 1.8))
            self.sfx("ring", 0.08)
        elif col == "blue":
            angs = {1: (-35, 35), 2: (-35, 0, 35), 3: (-45, -20, 20, 45)}[lv]
            for a in angs:
                r = math.radians(a)
                s = Shot(x, y, math.cos(r) * 135 * d, math.sin(r) * 135, "ray", 1.2, 1.4 + 0.2 * lv, 1.5, 1.5)
                s.data = {"b": 0, "max": 2 + lv, "tr": []}
                sh.append(s)
            self.sfx("ray", 0.08)
        elif col == "yellow":
            for dirn in (1, -1):
                s = Shot(x, y, 30 * d, 75 * dirn, "crawl", 1.6, 1.8, 2.0, 2.0, pierce=1)
                s.data = {"dir": dirn, "on": False, "d": d}
                s.hit = set()
                sh.append(s)
            for k in range(lv - 1):
                s = Shot(x, y, 105 * d, 0, "wave", 1.3 + 0.3 * lv, 1.2, 2.0, 3.0 + lv, pierce=1)
                s.data = {"y0": y, "ph": k * math.pi, "amp": 4 + 2 * lv}
                s.hit = set()
                sh.append(s)
            self.sfx("wave", 0.12)
        elif col == "green":
            for k in range(lv + 1):
                a = math.radians(-30 + 60 * k / max(1, lv))
                s = Shot(x, y, math.cos(a) * 80 * d, math.sin(a) * 80, "needle", 1.0, 1.7, 1.5, 1.2)
                s.data = {"tgt": None, "re": 0.0}
                sh.append(s)
            self.sfx("needle", 0.08)
        elif col == "violet":
            for k in range(lv):
                a = math.radians((k - (lv - 1) / 2) * 16)
                s = Shot(x, y, math.cos(a) * 100 * d, math.sin(a) * 100, "scatter", 2.0, 0.28, 2.0, 2.0)
                s.data = {"n": 4 + 2 * lv}
                sh.append(s)
            self.sfx("scatter", 0.1)
        elif col == "white":
            first = self.nearest(x, y, d, 52 + 10 * lv)
            if first is None:
                sh.append(Shot(x, y, 160 * d, 0, "bitbolt", 1.0, 0.5, 1.5, 1.0))
                return
            chain, prev = [first], first
            for _ in range(lv + 1):
                nxt = self.nearest(prev.x, prev.y, 0, 30, exclude=chain)
                if nxt is None:
                    break
                chain.append(nxt)
                prev = nxt
            pts = [(x, y)] + [(e.x, e.y) for e in chain]
            self.arcs.append([pts, 0.12])
            for e in chain:
                self.damage(e, 1.6 + 0.4 * lv, e.x, e.y)
            self.sfx("zap", 0.1)

    def release_lance(self):
        c = self.charge
        if c < CHARGE_LV[0] or not self.alive:
            return
        x, y = self.px + 9, self.py
        if c >= CHARGE_LV[3]:
            self.beam(y, 13, 45, nova=True)
            self.sfx("nova")
        elif c >= CHARGE_LV[2]:
            self.beam(y, 5, 26)
            self.sfx("lance3")
        elif c >= CHARGE_LV[1]:
            s = Shot(x, y, 180, 0, "lance2", 10.0, 1.2, 5.0, 3.0, pierce=28)
            s.hit = set()
            self.shots.append(s)
            self.sfx("lance2")
            self.shake = max(self.shake, 0.6)
        else:
            self.shots.append(Shot(x, y, 170, 0, "lance1", 5.0, 1.2, 3.5, 1.8))
            self.sfx("lance1")

    def beam(self, y, h, dmg, nova=False):
        x0 = self.px + 8
        self.beams.append([x0, y, h, 0.0, 0.4 if nova else 0.32, nova])
        for e in self.targets():
            if e.x + e.w / 2 > x0 and abs(e.y - y) < e.h / 2 + h / 2:
                self.damage(e, dmg, e.x + (e.boss["bd"]["core"][0] if e.boss else 0),
                            e.y + (e.boss["bd"]["core"][1] if e.boss else 0))
        for b in self.ebul:
            if nova or (b.x > x0 and abs(b.y - y) < h / 2 + 1):
                b.dead = True
                if self.rnd.random() < 0.3:
                    self.part(b.x, b.y, 0, 0, 0.2, (200, 220, 255))
        self.shake = max(self.shake, 2.5 if nova else 1.4)
        if nova:
            self.flash, self.flash_c = 0.25, (230, 200, 255)
            self.waves.append([self.px + 8, y, 0.0, 0.6])

    def pod_button(self):
        p = self.pod
        if p is None or not self.alive:
            return
        if p.state in ("front", "back"):
            p.vx = 140 if p.state == "front" else -140
            p.state = "out"
            self.sfx("launch")
        elif p.state in ("free", "out", "enter"):
            p.state = "return"
            self.sfx("recall")

    def smart_bomb(self):
        if self.bombs <= 0 or not self.alive:
            return
        self.bombs -= 1
        self.sfx("smart")
        self.flash, self.flash_c = 0.35, (255, 236, 200)
        self.shake = 3.0
        self.inv = max(self.inv, 0.8)
        self.waves.append([self.px, self.py, 0.0, 0.7])
        for b in self.ebul:
            b.dead = True
            self.part(b.x, b.y, 0, -6, 0.3, (255, 220, 160))
        for e in self.targets():
            if e.boss:
                cx, cy = e.boss["bd"]["core"][:2]
                self.damage(e, 30, e.x + cx, e.y + cy)
            else:
                self.damage(e, 30, e.x, e.y)

    def player_hit(self):
        if self.god or self.inv > 0 or not self.alive:
            return
        if self.shield:
            self.shield = False
            self.inv = 1.2
            self.sfx("shieldhit")
            self.sparks(self.px, self.py, (140, 210, 255), 12)
            self.shake = 1.0
            return
        self.alive = False
        self.respawn_t = 2.2
        self.lives -= 1
        self.stage_deaths += 1
        self.sfx("die")
        self.explode(self.px, self.py, 6, ((255, 255, 255), (160, 210, 255), (90, 130, 250), (255, 200, 90)))
        self.flash, self.flash_c = 0.2, (255, 255, 255)
        self.shake = 3.0
        self.charge = 0.0
        if self.has_pod:
            self.pod_lv = max(1, self.pod_lv - 1)
        self.pod = None
        self.nbits = 0
        self.missile = max(0, self.missile - 1)
        self.crawl = max(0, self.crawl - 1)
        self.speed = 1
        self.shield = False

    def after_death(self):
        if self.lives <= 0:
            self.phase, self.phase_t = "over", 0.0
            self.sfx("over")
            return
        fight = (self.boss is not None and not self.boss.dead) or (self.mid is not None and not self.mid.dead)
        if not fight:      # back to the last checkpoint
            self.cam = self.checkpoint
            self.ev_i = 0
            while self.ev_i < len(self.events) and self.events[self.ev_i][0] <= self.cam + FW * 0.9 \
                    and self.events[self.ev_i][1] != "mid":
                self.ev_i += 1
            self.clear_field()
            self.boss_due = False
        else:
            self.ebul = []
        self.spawn_player()

    # --- bosses ----------------------------------------------------------------------------
    def start_boss(self, key, mid):
        bd = (MIDBOSSES if mid else BOSSES)[key]
        mult = (1 + 0.1 * self.si) * self.d["hp"]
        hps = [h * mult for h in bd["hp"]]
        e = Enemy("boss", FW + bd["w"] / 2 + 4, FH / 2, hps[0], (3000 if mid else 12000) * (self.si + 1), bd["w"],
                  bd["h"])
        e.boss = dict(key=key, bd=bd, mid=mid, phase=0, hps=hps, state="intro", st=0.0, timers=[], spirals=[],
                      home=FW - bd["w"] / 2 - 5, total=sum(hps))
        self.boss_timers(e)
        self.enemies.append(e)
        self.spawned += 1
        if mid:
            self.mid = e
            self.banner(bd["name"], 2.0, (255, 200, 120))
        else:
            self.boss = e
            self.banner("WARNING", 2.6, (255, 80, 80), bd["name"])
            self.sfx("warning")
        return e

    def boss_timers(self, e):
        b = e.boss
        b["timers"] = [cd * self.rnd.uniform(0.5, 1.0) for _, cd, _ in b["bd"]["atk"][b["phase"]]]

    def update_boss(self, e):
        b = e.boss
        bd = b["bd"]
        b["st"] += DT
        st = b["st"]
        lo, hi = bd["h"] / 2 + 2, FH - bd["h"] / 2 - 2
        if b["state"] == "intro":
            e.x += (b["home"] - e.x) * 1.5 * DT
            e.y += (FH / 2 - e.y) * 2 * DT
            if st > 2.6:
                b["state"], b["st"] = "fight", 0.0
            return
        if b["state"] == "dying":
            if self.rnd.random() < 0.35:
                self.explode(e.x + self.rnd.uniform(-e.w / 2, e.w / 2), e.y + self.rnd.uniform(-e.h / 2, e.h / 2),
                             self.rnd.uniform(2, 5))
                self.sfx("boom", 0.12)
            e.x += 4 * DT
            if st > 2.4:
                e.dead = True
                self.explode(e.x, e.y, 14)
                self.flash, self.flash_c = 0.3, (255, 240, 210)
                self.sfx("bigboom")
                self.add_score(e.score)
                self.kills += 1
                if b["mid"]:
                    self.mid_done = True
                else:
                    self.stage_clear()
            return
        if b["state"] == "shift" and st > 1.2:
            b["state"] = "fight"
        style = bd["move"][b["phase"]]
        if (b["mid"] and e.t > 75) or e.data.get("flee"):       # a midboss gives up after a while
            e.data["flee"] = True
            e.x += 30 * DT
            if e.x > FW + e.w:
                e.dead = True
                self.mid_done = True
            return
        if style == "hover":
            ty, tx = FH / 2 + 14 * math.sin(st * 0.7), b["home"] + 3 * math.sin(st * 0.5)
        elif style == "bob":
            ty, tx = FH / 2 + 6 * math.sin(st * 1.1), b["home"]
        elif style == "track":
            ty, tx = self.py, b["home"] - 4 + 4 * math.sin(st * 0.4)
        elif style == "eight":
            ty, tx = FH / 2 + 16 * math.sin(st * 1.2), b["home"] - 10 + 10 * math.cos(st * 0.6)
        else:
            ty, tx = FH / 2 + 3 * math.sin(st * 0.8), b["home"]
        if any(sw["o"] is e for sw in self.sweeps):     # holds its height while it sweeps: the far side stays safe
            ty = e.y
        e.y += clamp(ty - e.y, -20 * DT, 20 * DT) if style == "track" else (ty - e.y) * 2 * DT
        e.x += (tx - e.x) * 2 * DT
        e.y = clamp(e.y, lo, hi)
        if b["state"] != "fight":
            return
        atk = bd["atk"][b["phase"]]
        for i, (name, cd, p) in enumerate(atk):
            b["timers"][i] -= DT * (0.6 + 0.4 * self.d["fire"])
            if b["timers"][i] <= 0:
                b["timers"][i] = cd * self.rnd.uniform(0.85, 1.15)
                self.boss_attack(e, name, p)
        for sp in b["spirals"]:
            sp[0] -= DT
            sp[4] += DT * self.d["fire"] ** 0.5
            while sp[4] > 0.09:
                sp[4] -= 0.09
                for k in range(sp[2]):
                    self.ebullet(e.x - 2, e.y, sp[1] + k * TAU / sp[2], sp[3])
                sp[1] += sp[5] * 0.09
        b["spirals"] = [sp for sp in b["spirals"] if sp[0] > 0]

    def boss_attack(self, e, name, p):
        R = self.rnd
        fx = e.x - e.w / 2 + 2
        if name == "aim":
            self.aimed(fx, e.y, p.get("n", 1), p.get("spread", 0), p.get("sp", 36), p.get("kind", "pel"))
        elif name == "ring":
            self.ring(e.x, e.y, p.get("n", 12), p.get("sp", 26), R.uniform(0, 1))
        elif name == "spiral":
            turn = 2.6 * (R.choice((-1, 1)) if p.get("alt") else 1)
            e.boss["spirals"].append([p.get("dur", 2.0), R.uniform(0, TAU), p.get("arms", 2), p.get("sp", 28), 0.0,
                                      turn])
        elif name == "lob":
            for _ in range(p.get("n", 4)):
                self.ebul.append(Bullet(fx, e.y - 4, -R.uniform(18, 60), -R.uniform(15, 45), "lob"))
            self.sfx("eorb", 0.1)
        elif name == "rain":
            for _ in range(p.get("n", 8)):
                self.ebul.append(Bullet(R.uniform(6, FW - 16), -2 - R.uniform(0, 14), -6, 26 * self.bspeed, "pel"))
        elif name == "curtain":
            gap = clamp(self.py + R.uniform(-14, 14), 10, FH - 10)
            y = 2.0
            while y < FH:
                if abs(y - gap) > 8:
                    self.ebul.append(Bullet(fx, y, -32 * self.bspeed, 0, "orb"))
                y += 4.5
            self.sfx("eorb")
        elif name == "spawn":
            self.boss_spawn(e, p["kind"], p.get("n", 1))
        elif name == "laser":
            self.laser(e, fx, clamp(self.py, 4, FH - 4), 3.2)
        elif name == "sweep":     # from steep up (or down) to just past level: the far side stays safe
            s = 1 if R.random() < 0.5 else -1
            self.sweeps.append(dict(o=e, a0=math.pi + 0.75 * s, a1=math.pi - 0.3 * s, a=math.pi + 0.75 * s, t=0.0,
                                    warn=0.8, dur=1.6))
            self.sfx("laserwarn")
        elif name == "seek":
            for k in range(p.get("n", 2)):
                s = self.add("seeker", fx, e.y + (k - 1) * 6)
                s.vx = -20
            self.sfx("spawn")
        elif name == "mines":
            for k in range(p.get("n", 2)):
                m = self.add("mine", fx, clamp(e.y + R.uniform(-14, 14), 6, FH - 6))
                m.st, m.data["ph"] = m.y, R.uniform(0, TAU)
        elif name == "blink":
            for _ in range(10):
                self.sparks(e.x, e.y, (200, 160, 255), 2)
            e.y = R.uniform(e.h / 2 + 2, FH - e.h / 2 - 2)
            e.flash = 0.2
            self.ring(e.x, e.y, 10, 24, R.uniform(0, 1))
        elif name == "orbit":
            if not any(o.kind == "orbiter" and not o.dead for o in self.enemies):
                n = p.get("n", 6)
                for k in range(n):
                    o = self.add("orbiter", e.x, e.y)
                    o.data["boss"], o.data["a"] = e, k * TAU / n

    def boss_spawn(self, e, kind, n):
        R = self.rnd
        self.sfx("spawn")
        for k in range(n):
            if kind in ("lancer", "comet"):
                m = self.add(kind, FW - 2, R.uniform(8, FH - 8))
                m.t = -0.3 * k
            elif kind == "tendril":
                self.spawn_wave("tendril", "snake", R.uniform(14, FH - 14))
            elif kind == "rockM":
                m = self.add(kind, e.x - e.w / 2, e.y)
                m.vx, m.vy = -R.uniform(24, 34), R.uniform(-14, 14)
            elif kind == "drone":
                m = self.add(kind, e.x - e.w / 2, e.y + R.uniform(-8, 8))
                m.vx, m.vy = -20, R.uniform(-20, 20)
            else:
                m = self.add(kind, e.x - e.w / 2 - 2, clamp(e.y + (k - (n - 1) / 2) * 8, 6, FH - 6))
                m.st = m.y
                m.data["ph"] = k * 0.8
                if kind == "spore":
                    m.vx = -16

    def boss_down(self, e):
        b = e.boss
        b["phase"] += 1
        if b["phase"] < len(b["hps"]):
            e.hp = b["hps"][b["phase"]]
            b["state"], b["st"] = "shift", 0.0
            b["spirals"] = []
            self.boss_timers(e)
            self.flash, self.flash_c = 0.18, (255, 220, 200)
            self.shake = 2.0
            self.sfx("phase")
            self.explode(e.x, e.y, 6)
            for bl in self.ebul[::2]:
                bl.dead = True
        else:
            e.hp = 0
            b["state"], b["st"] = "dying", 0.0
            b["spirals"] = []
            for bl in self.ebul:
                bl.dead = True
            self.lasers, self.sweeps = [], []
            self.sfx("bigboom")

    def boss_frac(self, e):
        b = e.boss
        left = max(0.0, e.hp) + sum(b["hps"][b["phase"] + 1:])
        return clamp(left / b["total"], 0, 1)

    def stage_clear(self):
        self.phase, self.phase_t = "clear", 0.0
        nomiss = 10000 * (self.si + 1) if self.stage_deaths == 0 else 0
        rate = self.kills / max(1, self.spawned)
        kb = int(rate * 20000) // 100 * 100
        self.tally = dict(kills=self.kills, spawned=self.spawned, rate=rate, nomiss=nomiss, killbonus=kb)
        self.add_score(nomiss + kb)
        self.sfx("clear")
        self.ebul = []

    # --- one fixed step --------------------------------------------------------------------
    def step(self, inp):
        self.t += DT
        self.phase_t += DT
        self.shake = max(0.0, self.shake - DT * 6)
        self.flash = max(0.0, self.flash - DT)
        self.update_effects()
        if self.phase == "over" or self.phase == "won":
            return
        if self.phase == "clear":
            if self.phase_t > 6.0:
                if self.si + 1 < len(STAGES):
                    self.load_stage(self.si + 1)
                else:
                    self.phase, self.phase_t = "won", 0.0
                    self.sfx("win")
            if self.alive:
                self.px += 40 * DT * clamp((self.phase_t - 1.5), 0, 3)
            return
        sp = self.st["speed"]
        if self.boss is not None or self.cam >= LEN:
            sp = 0.0
        elif self.mid is not None and not self.mid.dead:
            sp *= 0.45
        self.scroll = sp
        self.cam = min(float(LEN), self.cam + sp * DT)
        self.hazards = []
        self.spawn_events()
        if self.boss_due and self.boss is None and self.cam >= LEN:
            self.start_boss(self.st["boss"], False)
        self.update_player(inp)
        self.update_pod()
        self.update_shots()
        self.update_enemies()
        self.update_bullets()
        self.update_lasers()
        self.collide()
        for it in self.items:
            it.t += DT
            it.x -= 9 * DT
            it.y = it.st + 2.5 * math.sin(it.t * 3)
            if it.x < -6:
                it.dead = True
        self.items = [i for i in self.items if not i.dead]
        self.shots = [s for s in self.shots if not s.dead]
        self.enemies = [e for e in self.enemies if not e.dead]
        self.ebul = [b for b in self.ebul if not b.dead]

    def update_effects(self):
        ps = self.parts
        for p in ps:
            p[0] += p[2] * DT
            p[1] += p[3] * DT
            p[4] -= DT
        self.parts = [p for p in ps if p[4] > 0]
        for b in self.blasts:
            b[3] += DT
        self.blasts = [b for b in self.blasts if b[3] < b[4]]
        for bm in self.beams:
            bm[3] += DT
        self.beams = [b for b in self.beams if b[3] < b[4]]
        for a in self.arcs:
            a[1] -= DT
        self.arcs = [a for a in self.arcs if a[1] > 0]
        for w in self.waves:
            w[2] += DT
        self.waves = [w for w in self.waves if w[2] < w[3]]
        self.banners = [b for b in self.banners if b[1] > self.t]

    def update_pod(self):
        p = self.pod
        if p is None:
            return
        p.t += DT
        if p.state == "front":
            p.x, p.y = self.px + 9.5, self.py
        elif p.state == "back":
            p.x, p.y = self.px - 8.5, self.py
        elif p.state == "enter":
            p.x += 40 * DT
            p.y += (self.py - p.y) * 2 * DT
            if p.x >= 14:
                p.state = "free"
        elif p.state == "out":
            p.x += p.vx * DT
            p.vx *= 1 - 2.6 * DT
            if abs(p.vx) < 10 or p.x < 4 or p.x > FW - 6:
                p.x = clamp(p.x, 4, FW - 6)
                p.state = "free"
        elif p.state == "free":
            p.y += clamp(self.py - p.y, -1, 1) * 14 * DT
        elif p.state == "return":
            dx, dy = self.px - p.x, self.py - p.y
            d = math.hypot(dx, dy) or 1
            sp = min(d / DT, 95)
            p.x += dx / d * sp * DT
            p.y += dy / d * sp * DT
        if p.state in ("free", "out", "enter"):
            p.cd -= DT
            if p.cd <= 0 and self.alive and 0 < p.x < FW:
                p.cd = POD_CD[self.pod_color] * 1.7
                self.pod_cd, keep = 0, self.pod_cd
                self.pod_fire(p, free=True)
                self.pod_cd = keep
        if p.state in ("free", "return", "enter") and self.alive and self.entering <= 0:
            if abs(p.x - self.px) < 9 and abs(p.y - self.py) < 5:
                p.state = "front" if p.x > self.px else "back"
                self.sfx("dock")
                self.sparks(p.x, p.y, (200, 230, 255), 6)

    def update_shots(self):
        tg = None
        for s in self.shots:
            s.t += DT
            if s.t > s.life:
                s.dead = True
                if s.kind == "scatter":
                    self.burst(s)
                continue
            k = s.kind
            if k == "ray":
                tr = s.data["tr"]
                tr.append((s.x, s.y))
                if len(tr) > 5:
                    del tr[0]
                s.x += s.vx * DT
                s.y += s.vy * DT
                c, f = self.ceil_at(s.x), self.floor_at(s.x)
                if s.y < max(c, 0.5) or s.y > min(f, FH - 0.5):
                    s.vy = -s.vy
                    s.y = clamp(s.y, max(c, 0.5) + 0.5, min(f, FH - 0.5) - 0.5)
                    s.data["b"] += 1
                    if s.data["b"] > s.data["max"]:
                        s.dead = True
                    self.sparks(s.x, s.y, (150, 200, 255), 2)
                    self.sfx("clink", 0.1)
            elif k == "crawl":
                dd = s.data
                if not dd["on"]:
                    s.x += s.vx * DT
                    s.y += s.vy * DT
                    lim_c, lim_f = max(self.ceil_at(s.x), 1), min(self.floor_at(s.x), FH - 1)
                    if s.y <= lim_c + 1.5 or s.y >= lim_f - 1.5:
                        dd["on"] = True
                else:
                    s.x += 95 * dd["d"] * DT
                    if dd["dir"] < 0:
                        s.y = max(self.ceil_at(s.x), 1) + 1.8
                    else:
                        s.y = min(self.floor_at(s.x), FH - 1) - 1.8
            elif k == "wave":
                s.x += s.vx * DT
                s.y = s.data["y0"] + s.data["amp"] * math.sin(s.t * 14 + s.data["ph"])
            elif k in ("needle", "missile"):
                dd = s.data if s.data is not None else {}
                if s.data is None:
                    s.data = dd = {"tgt": None, "re": 0.0}
                dd["re"] -= DT
                t = dd["tgt"]
                if dd["re"] <= 0 or t is None or t.dead:
                    dd["re"] = 0.15
                    if tg is None:
                        tg = self.targets()
                    best, bd = None, 1e9
                    for e in tg:
                        dist = abs(e.x - s.x) + abs(e.y - s.y)
                        if dist < bd and not e.dead:
                            best, bd = e, dist
                    dd["tgt"] = t = best
                sp = 115 if k == "needle" else min(130, 40 + s.t * 120)
                turn = 7.0 if k == "needle" else 4.0
                a = math.atan2(s.vy, s.vx)
                if t is not None and not t.dead:
                    want = math.atan2(t.y - s.y, t.x - s.x)
                    da = (want - a + math.pi) % TAU - math.pi
                    a += clamp(da, -turn * DT, turn * DT)
                s.vx, s.vy = math.cos(a) * sp, math.sin(a) * sp
                s.x += s.vx * DT
                s.y += s.vy * DT
                if k == "missile" and self.rnd.random() < 0.5:
                    self.part(s.x, s.y, -s.vx * 0.1, -s.vy * 0.1, 0.25, (150, 150, 160))
                if self.in_wall(s.x, s.y):
                    s.dead = True
                    self.sparks(s.x, s.y, (255, 200, 120), 3)
            elif k == "bomb":
                dd = s.data
                if not dd["crawl"]:
                    s.vy += 110 * dd["dir"] * DT
                    s.x += s.vx * DT
                    s.y += s.vy * DT
                    edge = self.floor_at(s.x) if dd["dir"] > 0 else self.ceil_at(s.x)
                    if (dd["dir"] > 0 and s.y >= edge - 1.5 and edge < FH) or \
                            (dd["dir"] < 0 and s.y <= edge + 1.5 and edge > 0):
                        dd["crawl"] = True
                else:
                    s.x += 70 * DT
                    s.y = (self.floor_at(s.x) - 1.5) if dd["dir"] > 0 else (self.ceil_at(s.x) + 1.5)
                    if self.rnd.random() < 0.3:
                        self.part(s.x - 2, s.y, -10, 0, 0.2, (255, 180, 90))
            else:
                s.x += s.vx * DT
                s.y += s.vy * DT
                if k not in ("lance2",) and self.in_wall(s.x, s.y):
                    s.dead = True
                    self.sparks(s.x, s.y, (255, 230, 160), 2)
                    if k == "scatter":
                        self.burst(s)
            if s.x < -8 or s.x > FW + 8 or s.y < -8 or s.y > FH + 8:
                s.dead = True

    def burst(self, s):
        n = s.data["n"] if s.data else 6
        for k in range(n):
            a = k * TAU / n
            self.shots.append(Shot(s.x, s.y, math.cos(a) * 90, math.sin(a) * 90, "frag", 0.9, 0.35, 1.2, 1.2))
        self.sparks(s.x, s.y, (220, 160, 255), 5)

    def update_enemies(self):
        sc = self.scroll * DT
        for e in self.enemies:
            if e.dead:
                continue
            e.t += DT
            if e.flash > 0:
                e.flash -= DT
            if e.anch:
                e.x -= sc
            if e.boss is not None:
                self.update_boss(e)
            elif e.t >= 0:
                BEHAVE[e.kind](self, e)
            if e.x < -26 or e.x > FW + 100 or e.y < -34 or e.y > FH + 34:
                e.dead = True

    def update_bullets(self):
        bs = self.bspeed
        for b in self.ebul:
            b.t += DT
            if b.kind == "lob":
                b.vy += 34 * bs * DT
            b.x += b.vx * DT
            b.y += b.vy * DT
            if b.x < -4 or b.x > FW + 6 or b.y > FH + 4 or (b.y < -20):
                b.dead = True
            elif b.t > 0.1 and self.in_wall(b.x, b.y) and b.y > 0:
                b.dead = True

    def update_lasers(self):
        for L in self.lasers:
            L["t"] += DT
            o = L["o"]
            x = o.x + L["dx"]
            if L["t"] > L["warn"]:
                if not L["fired"]:
                    L["fired"] = True
                    self.sfx("laser", 0.2)
                self.hazards.append((-2, L["y"] - L["h"] / 2, x, L["y"] + L["h"] / 2))
        self.lasers = [L for L in self.lasers if L["t"] < L["warn"] + L["dur"] and not L["o"].dead]
        for sw in self.sweeps:
            sw["t"] += DT
            k = clamp((sw["t"] - sw["warn"]) / sw["dur"], 0, 1)
            sw["a"] = sw["a0"] + (sw["a1"] - sw["a0"]) * k
            if sw["t"] > sw["warn"] and sw["t"] < sw["warn"] + 0.05:
                self.sfx("laser", 0.3)
        self.sweeps = [s for s in self.sweeps if s["t"] < s["warn"] + s["dur"] and not s["o"].dead]

    def collide(self):
        enemies = [e for e in self.enemies if not e.dead and not e.ghost]
        # player shots against enemies
        for s in self.shots:
            if s.dead:
                continue
            sx, sy, hw, hh = s.x, s.y, s.hw, s.hh
            for e in enemies:
                if e.dead:
                    continue
                if abs(sx - e.x) < e.w * 0.5 + hw and abs(sy - e.y) < e.h * 0.5 + hh:
                    if s.hit is not None and e in s.hit:
                        continue
                    self.shot_hits(s, e)
                    if s.dead:
                        break
        # the pod and the bits soak up small bullets; the pod also rams enemies
        p = self.pod
        bits = self.bits() if self.alive else []
        if p is not None or bits:
            for b in self.ebul:
                if b.kind == "orb" or b.dead:
                    continue
                if p is not None and abs(b.x - p.x) < 4.5 and abs(b.y - p.y) < 4.5:
                    b.dead = True
                    self.sfx("absorb", 0.06)
                    continue
                for bx, by in bits:
                    if abs(b.x - bx) < 3 and abs(b.y - by) < 3:
                        b.dead = True
                        break
        if p is not None:
            for e in enemies:
                if not e.dead and abs(e.x - p.x) < e.w / 2 + 3.5 and abs(e.y - p.y) < e.h / 2 + 3.5:
                    if e.inv:
                        continue
                    if e.boss is not None:
                        self.damage(e, 0.5, p.x, p.y)
                    else:
                        self.damage(e, 0.6, p.x, p.y)
                    if self.rnd.random() < 0.3:
                        self.sparks(p.x, p.y, CRYSTAL_C.get(self.pod_color, (220, 220, 255)), 1)
        for it in self.items:
            if (abs(it.x - self.px) < 6 and abs(it.y - self.py) < 5 and self.alive) or \
                    (p is not None and abs(it.x - p.x) < 5 and abs(it.y - p.y) < 5):
                self.collect(it)
        if not self.alive or self.inv > 0 or self.god:
            return
        px, py = self.px, self.py
        hit = False
        for ox, oy in ((-5, 0), (6, 0), (0, -2), (0, 2), (-4, -2.5), (-4, 2.5), (3, -1.5), (3, 1.5)):
            if self.in_wall(px + ox, py + oy):
                hit = True
                break
        if not hit:
            for b in self.ebul:
                if abs(b.x - px) < b.r + 2.2 and abs(b.y - py) < b.r + 1.0:
                    b.dead = True
                    hit = True
                    break
        if not hit:
            for e in enemies:
                if e.dead:
                    continue
                k = 0.42 if e.boss is not None else 0.5
                if abs(e.x - px) < e.w * k + 3 and abs(e.y - py) < e.h * k + 1.3:
                    hit = True
                    break
        if not hit:
            for x0, y0, x1, y1 in self.hazards:
                if x0 - 2 < px < x1 + 2 and y0 - 1 < py < y1 + 1:
                    hit = True
                    break
        if not hit:
            for sw in self.sweeps:
                if sw["t"] < sw["warn"]:
                    continue
                o = sw["o"]
                ox, oy = o.x - o.w / 2 + 2, o.y
                dx, dy = math.cos(sw["a"]), math.sin(sw["a"])
                rx, ry = px - ox, py - oy
                along = rx * dx + ry * dy
                if along > 0 and abs(rx * dy - ry * dx) < 2.6:
                    hit = True
                    break
        if hit:
            self.player_hit()

    def shot_hits(self, s, e):
        k = s.kind
        if e.inv or (e.kind == "shard" and k in SMALL_SHOTS) or \
                (e.kind == "angler" and k in SMALL_SHOTS and s.x < e.x - 1 and s.vx > 0):
            if k in ("crawl", "wave", "lance2"):
                if e.inv:
                    s.dead = k != "wave"
                return
            s.dead = True
            self.sparks(s.x, s.y, (230, 240, 255), 3)
            self.sfx("clink", 0.06)
            return
        if s.hit is not None:
            s.hit.add(e)
            hp0 = e.hp
            self.damage(e, s.dmg, s.x, s.y)
            if k == "lance2":
                s.pierce -= max(1.0, hp0)
                if s.pierce <= 0 or e.boss is not None:
                    s.dead = True
        else:
            s.dead = True
            self.damage(e, s.dmg, s.x, s.y)
            if k == "scatter":
                self.burst(s)
        if not e.dead:
            self.sfx("hit", 0.05)
            if self.rnd.random() < 0.5:
                self.part(s.x, s.y, -20, self.rnd.uniform(-10, 10), 0.12, (255, 240, 200))


# =============================================================================================
# Drawing
# =============================================================================================
_CIRC = {}


def circ_runs(r):
    """Half widths of a filled circle of pixel radius r, per row offset."""
    v = _CIRC.get(r)
    if v is None:
        v = _CIRC[r] = [(dy, int(math.sqrt(max(0.0, (r + 0.5) ** 2 - dy * dy)))) for dy in range(-r, r + 1)]
    return v


class View:
    """Draws in field units onto a canvas; everything is clipped to the field rectangle."""

    def __init__(self, cv, s, ox, oy, fw, fh):
        self.cv, self.P, self.s, self.ox, self.oy, self.fw, self.fh = cv, cv.px, s, ox, oy, fw, fh
        self.x0, self.y0 = max(0, ox), max(0, oy)
        self.x1, self.y1 = min(cv.W, ox + fw), min(cv.H, oy + fh)

    def X(self, x):
        return self.ox + int(math.floor(x * self.s))

    def Y(self, y):
        return self.oy + int(math.floor(y * self.s))

    def prect(self, a, ya, b, yb, c):
        a, b = max(a, self.x0), min(b, self.x1)
        if b <= a:
            return
        ya, yb = max(ya, self.y0), min(yb, self.y1)
        row = [c] * (b - a)
        P = self.P
        for y in range(ya, yb):
            P[y][a:b] = row

    def rect(self, x, y, w, h, c):
        a, ya = self.X(x), self.Y(y)
        b, yb = self.X(x + w), self.Y(y + h)
        self.prect(a, ya, max(b, a + 1), max(yb, ya + 1), c)

    def dot(self, x, y, c):
        a, ya = self.X(x), self.Y(y)
        if self.x0 <= a < self.x1 and self.y0 <= ya < self.y1:
            self.P[ya][a] = c

    def blob(self, x, y, c, size=1.0):
        n = max(1, int(size * self.s + 0.5))
        a, ya = self.X(x) - n // 2, self.Y(y) - n // 2
        self.prect(a, ya, a + n, ya + n, c)

    def spr(self, sp, x, y, flash=False, fh=False, fv=False):
        ow, oh, runs = sp.runs(self.s, flash, fh, fv)
        px, py = self.X(x) - ow // 2, self.Y(y) - oh // 2
        x0, x1, y0, y1, P = self.x0, self.x1, self.y0, self.y1, self.P
        if px >= x0 and px + ow <= x1:
            for dy, dx, n, c, cl in runs:
                yy = py + dy
                if y0 <= yy < y1:
                    a = px + dx
                    P[yy][a:a + n] = cl
            return
        for dy, dx, n, c, cl in runs:
            yy = py + dy
            if y0 <= yy < y1:
                a = px + dx
                b = a + n
                if a < x0:
                    a = x0
                if b > x1:
                    b = x1
                if b > a:
                    P[yy][a:b] = [c] * (b - a)

    def circle(self, x, y, r, c):
        rp = int(r * self.s + 0.5)
        cx, cy = self.X(x), self.Y(y)
        x0, x1, y0, y1, P = self.x0, self.x1, self.y0, self.y1, self.P
        for dy, hw in circ_runs(rp):
            yy = cy + dy
            if y0 <= yy < y1:
                a, b = max(x0, cx - hw), min(x1, cx + hw + 1)
                if b > a:
                    P[yy][a:b] = [c] * (b - a)

    def ring(self, x, y, r, c, n=None):
        rp = r * self.s
        n = n or max(12, int(rp * 6))
        cx, cy = self.X(x), self.Y(y)
        x0, x1, y0, y1, P = self.x0, self.x1, self.y0, self.y1, self.P
        for k in range(n):
            a = k * TAU / n
            xx, yy = int(cx + math.cos(a) * rp), int(cy + math.sin(a) * rp)
            if x0 <= xx < x1 and y0 <= yy < y1:
                P[yy][xx] = c

    def line(self, xa, ya, xb, yb, c):
        a, b = self.X(xa), self.Y(ya)
        e, f = self.X(xb), self.Y(yb)
        n = max(abs(e - a), abs(f - b), 1)
        x0, x1, y0, y1, P = self.x0, self.x1, self.y0, self.y1, self.P
        for k in range(n + 1):
            xx, yy = a + (e - a) * k // n, b + (f - b) * k // n
            if x0 <= xx < x1 and y0 <= yy < y1:
                P[yy][xx] = c

    def poly(self, pts, c):
        s, ox, oy = self.s, self.ox, self.oy
        pp = [(ox + x * s, oy + y * s) for x, y in pts]
        ys = [p[1] for p in pp]
        ya, yb = max(self.y0, int(min(ys) + 0.5)), min(self.y1 - 1, int(max(ys) - 0.5))
        n = len(pp)
        P = self.P
        for y in range(ya, yb + 1):
            yc = y + 0.5
            lo, hi = 1e9, -1e9
            for i in range(n):
                ax, ay = pp[i]
                bx, by = pp[(i + 1) % n]
                if (ay <= yc < by) or (by <= yc < ay):
                    xx = ax + (yc - ay) * (bx - ax) / (by - ay)
                    lo, hi = min(lo, xx), max(hi, xx)
            if hi < lo:
                continue
            a, b = max(self.x0, int(lo + 0.5)), min(self.x1, int(hi + 0.5))
            if b > a:
                P[y][a:b] = [c] * (b - a)


# --- cached backgrounds ----------------------------------------------------------------------
_FAR, _MID, _GRAD, _VAR = {}, {}, {}, {}


def bake_far(si, fw, fh):
    """The far layer: a strip two fields wide that tiles; it scrolls slowly."""
    key = (si, fw, fh)
    if key in _FAR:
        return _FAR[key]
    if len(_FAR) > 12:
        _FAR.clear()
    st = STAGES[si]
    top, bot = st["sky"]
    TW = max(4, fw * 2)
    cv = Canvas(TW, (fh + 1) // 2)
    s = fh / FH
    rnd = random.Random(si * 7 + 1)
    for y in range(cv.H):
        cv.px[y] = [mix(top, bot, y / max(1, fh - 1))] * TW
    style = st["far"]
    P = cv.px

    def soft(cx, cy, r, col, k):   # a soft glow blended into the sky
        r = max(1, int(r))
        for dy in range(-r, r + 1):
            yy = cy + dy
            if 0 <= yy < cv.H:
                for dx in range(-r, r + 1):
                    d = (dx * dx + dy * dy) / (r * r)
                    if d < 1:
                        xx = (cx + dx) % TW
                        P[yy][xx] = mix(P[yy][xx], col, k * (1 - d))

    if style in ("stars", "storm", "prism", "core"):
        for _ in range(TW * fh // (50 if style == "stars" else 90)):
            x, y = rnd.randrange(TW), rnd.randrange(cv.H)
            b = rnd.uniform(0.3, 1.0)
            P[y][x] = mix(P[y][x], rnd.choice(((255, 255, 255), (180, 210, 255), (255, 230, 200))), b)
    if style == "stars":
        for _ in range(3):
            soft(rnd.randrange(TW), rnd.randrange(cv.H), rnd.uniform(10, 22) * s, rnd.choice(
                ((80, 60, 160), (40, 90, 160), (120, 50, 120))), 0.45)
        px_, py_, r = int(TW * 0.3), int(fh * 0.3), max(3, int(9 * s))
        cv_ = View(cv, 1, 0, 0, TW, cv.H)
        cv_.circle(px_, py_, r, (70, 90, 130))
        cv_.circle(px_ - r // 3, py_ - r // 3, max(1, int(r * 0.7)), (110, 130, 170))
        for dx in range(-int(r * 1.8), int(r * 1.8) + 1):
            yy = py_ + int(dx * 0.25)
            if 0 <= yy < cv.H and abs(dx) > r * 0.85:
                P[yy][(px_ + dx) % TW] = (170, 160, 140)
    elif style == "flesh":
        for _ in range(14):
            x, y = rnd.uniform(0, TW), rnd.uniform(0, cv.H)
            a = rnd.uniform(0, TAU)
            col = rnd.choice(((90, 20, 40), (110, 30, 50), (70, 14, 30)))
            for k in range(int(60 * s)):
                a += rnd.uniform(-0.3, 0.3)
                x, y = x + math.cos(a), y + math.sin(a) * 0.6
                if 0 <= y < cv.H:
                    P[int(y)][int(x) % TW] = col
        for _ in range(10):
            soft(rnd.randrange(TW), rnd.randrange(cv.H), rnd.uniform(4, 9) * s, (120, 40, 70), 0.5)
    elif style == "forge":
        step = max(8, int(24 * s))
        for x in range(0, TW, step):
            for y in range(cv.H):
                P[y][x] = mix(P[y][x], (70, 40, 28), 0.7)
                P[y][(x + step // 2 + y // 2) % TW] = mix(P[y][(x + step // 2 + y // 2) % TW], (60, 34, 24), 0.4)
        for _ in range(16):
            soft(rnd.randrange(TW), rnd.randrange(cv.H // 2, cv.H), rnd.uniform(2, 5) * s, (255, 120, 40), 0.6)
    elif style == "water":
        wl = int(st.get("water", 22) * s)
        for y in range(wl, cv.H):
            k = (y - wl) / max(1, cv.H - wl)
            P[y] = [mix((10, 50, 80), (2, 14, 30), k)] * TW
        for _ in range(9):
            x0 = rnd.randrange(TW)
            w = rnd.randint(2, max(3, int(6 * s)))
            for y in range(wl, cv.H):
                for dx in range(w):
                    xx = (x0 + dx + (y - wl) // 2) % TW
                    P[y][xx] = mix(P[y][xx], (60, 140, 170), 0.18 * (1 - (y - wl) / max(1, cv.H - wl)))
    elif style == "storm":
        for y in range(cv.H):
            k = 0.5 + 0.5 * math.sin(y * 0.3 / max(0.3, s) + 1.3)
            P[y] = [mix(c, (90, 60, 50), 0.12 * k) for c in P[y]]
        for _ in range(5):
            soft(rnd.randrange(TW), rnd.randrange(cv.H), rnd.uniform(5, 12) * s, (60, 40, 40), 0.7)
    elif style == "hive":
        r = max(4, int(7 * s))
        cv_ = View(cv, 1, 0, 0, TW, cv.H)
        for gy in range(-1, cv.H // r + 2):
            for gx in range(-1, TW // r + 2):
                cx, cy = gx * r * 1.5, gy * r * 1.7 + (r * 0.85 if gx % 2 else 0)
                pts = [(cx + r * math.cos(k * TAU / 6), cy + r * math.sin(k * TAU / 6)) for k in range(7)]
                for k in range(6):
                    cv_.line(pts[k][0], pts[k][1], pts[k + 1][0], pts[k + 1][1], (80, 54, 14))
        for _ in range(12):
            soft(rnd.randrange(TW), rnd.randrange(cv.H), rnd.uniform(2, 5) * s, (255, 180, 40), 0.35)
    elif style == "prism":
        cv_ = View(cv, 1, 0, 0, TW, cv.H)
        for _ in range(16):
            x, y = rnd.uniform(0, TW), rnd.uniform(0, cv.H)
            r = rnd.uniform(6, 18) * s
            col = mix(mix(top, bot, 0.5), rnd.choice(((120, 80, 220), (60, 160, 220), (200, 80, 200))), 0.35)
            cv_.poly([(x, y - r), (x + r * 0.5, y), (x, y + r), (x - r * 0.5, y)], col)
    elif style == "core":
        step = max(6, int(16 * s))
        for y in range(0, cv.H, step):
            P[y] = [mix(c, (90, 20, 30), 0.6) for c in P[y]]
        for x in range(0, TW, step):
            for y in range(cv.H):
                P[y][x] = mix(P[y][x], (90, 20, 30), 0.5)
        for _ in range(8):
            soft(rnd.randrange(TW), rnd.randrange(cv.H), rnd.uniform(2, 4) * s, (255, 60, 80), 0.5)
    _FAR[key] = P[:fh]
    return _FAR[key]


def mid_heights(si):
    """The middle parallax layer: (bottom height, top height, light) per field unit over a 256-unit tile."""
    if si in _MID:
        return _MID[si]
    st = STAGES[si]
    rnd = random.Random(si * 13 + 5)
    n = 256
    bot, top, lit = [0.0] * n, [0.0] * n, [0] * n
    style = st["mid"]
    if style in ("wrecks", "pipes", "towers"):
        x = 0
        while x < n:
            w = rnd.randint(6, 20)
            h = rnd.uniform(6, 22 if style == "towers" else 16)
            for i in range(x, min(n, x + w)):
                bot[i] = h + (rnd.random() < 0.15) * 2
                lit[i] = 1 if style == "towers" and i % 3 == 1 else 0
            if style == "pipes" and rnd.random() < 0.5:
                for i in range(x + 1, min(n, x + 3)):
                    bot[i] = h + rnd.uniform(6, 12)
            x += w + rnd.randint(0, 8)
    elif style in ("veins", "dust", "kelp"):
        p = [rnd.uniform(0, TAU) for _ in range(4)]
        for i in range(n):
            a = i * TAU / n
            bot[i] = 8 + 4 * math.sin(a * 3 + p[0]) + 3 * math.sin(a * 7 + p[1])
            if style != "kelp":
                top[i] = 6 + 4 * math.sin(a * 2 + p[2]) + 2 * math.sin(a * 9 + p[3])
        if style == "kelp":
            for _ in range(28):
                i = rnd.randrange(n)
                bot[i] = max(bot[i], rnd.uniform(14, 30))
    elif style in ("combs", "facets"):
        x = 0
        while x < n:
            w = rnd.randint(5, 12)
            hb, ht = rnd.uniform(4, 16), rnd.uniform(2, 12)
            for i in range(x, min(n, x + w)):
                k = 1 - abs(i - x - w / 2) / (w / 2) if style == "facets" else 1
                bot[i], top[i] = hb * (0.4 + 0.6 * k), ht * (0.4 + 0.6 * k)
            x += w + rnd.randint(0, 4)
    _MID[si] = (bot, top, lit)
    return _MID[si]


def terrain_grad(si, s):
    """Colours of the rock by depth from its face (pixels), in three column variants."""
    key = (si, int(s * 16))
    if key in _GRAD:
        return _GRAD[key]
    edge, midc, deep, deep2 = STAGES[si]["tcol"]
    out = []
    n = int(FH * s) + 4
    for v in range(3):
        g = []
        for d in range(n):
            u = d / s
            if u < 1:
                c = edge
            elif u < 2.5:
                c = mix(edge, midc, 0.6)
            elif u < 4:
                c = midc
            else:
                c = mix(midc, deep, min(1.0, (u - 4) / 4))
                if int(u) % 6 == 5:
                    c = deep2
            if v == 1 and u >= 1:
                c = shade(c, 0.78)
            elif v == 2 and 5 <= u < 6:
                c = mix(edge, (255, 230, 140), 0.6)
            g.append(c)
        out.append(g)
    _GRAD[key] = out
    return out


def terrain_var(si, N):
    if si in _VAR:
        return _VAR[si]
    style = STAGES[si]["terrain"]
    rnd = random.Random(si)
    v = []
    for i in range(N):
        if style == "girders":
            k = 1 if i % 12 < 2 else 0
        elif style == "flesh":
            k = 1 if math.sin(i * 0.4) > 0.6 else 0
        elif style == "hull":
            k = 1 if i % 16 < 2 else (2 if i % 6 == 3 else 0)
        elif style == "flooded":
            k = 1 if i % 7 == 0 else 0
        elif style == "asteroid":
            k = 1 if rnd.random() < 0.25 else 0
        elif style == "hive":
            k = 1 if i % 8 == 0 else (2 if i % 8 == 4 else 0)
        elif style == "crystal":
            k = 1 if (i // 3) % 3 == 0 else 0
        else:
            k = 1 if i % 10 == 0 else (2 if i % 20 == 5 else 0)
        v.append(k)
    _VAR[si] = v
    return v


def draw_world(g, v):
    """Sky, the middle layer and the cave walls."""
    s, P = v.s, v.P
    fw, fh = v.fw, v.fh
    x0, x1, y0, y1 = v.x0, v.x1, v.y0, v.y1
    if g.flash > 0.12:
        v.prect(x0, y0, x1, y1, mix(g.st["sky"][1], g.flash_c, min(1.0, g.flash * 3)))
    else:
        far = bake_far(g.si, fw, fh)
        TW = len(far[0])
        off = int(g.cam * s * 0.15 + g.t * s * 0.6) % TW
        a, b = x0 - v.ox, x1 - v.ox
        for y in range(y0, y1):
            src = far[y - v.oy]
            o = (off + a) % TW
            seg = src[o:o + (b - a)]
            if len(seg) < b - a:
                seg = seg + src[:b - a - len(seg)]
            P[y][x0:x1] = seg
    # middle layer
    bot, top, lit = mid_heights(g.si)
    mb, me = g.st["midc"]
    cam2 = g.cam * 0.45 + g.t * 1.5
    yb = v.oy + fh
    for sx in range(x0, x1):
        i = int(cam2 + (sx - v.ox) / s) % 256
        h = int(bot[i] * s)
        if h > 0:
            yt = max(y0, yb - h)
            for y in range(yt + 1, min(y1, yb)):
                P[y][sx] = mb
            if yt < y1:
                P[yt][sx] = me
            if lit[i] and h > 4:
                yy = yb - h + 2
                if y0 <= yy < y1 and int(g.t * 2 + i) % 5:
                    P[yy][sx] = (230, 200, 120)
        h = int(top[i] * s)
        if h > 0:
            yt = v.oy + h
            for y in range(y0, min(y1, yt)):
                P[y][sx] = mb
            if y0 <= yt < y1:
                P[yt][sx] = me
    # water surface
    if g.water:
        wy = g.water
        for sx in range(x0, x1, 1):
            lx = (sx - v.ox) / s
            yy = v.Y(wy + 0.6 * math.sin(lx * 0.4 + g.t * 3))
            if y0 <= yy < y1:
                P[yy][sx] = (150, 220, 230)
                if yy + 1 < y1:
                    P[yy + 1][sx] = mix(P[yy + 1][sx], (90, 170, 200), 0.5)
    # the walls
    grad = terrain_grad(g.si, s)
    var = terrain_var(g.si, g.N)
    N = g.N
    cam = g.cam
    for sx in range(x0, x1):
        lx = (sx - v.ox) / s
        i = int(cam + lx)
        i = 0 if i < 0 else N - 1 if i >= N else i
        gr = grad[var[i]]
        c = g.ceil_at(lx)
        if c > 0.2:
            cp = int(c * s)
            ytop = v.oy + cp - 1
            for y in range(max(y0, v.oy), min(y1, v.oy + cp)):
                P[y][sx] = gr[ytop - y]
        f = g.floor_at(lx)
        if f < FH - 0.2:
            fp = v.oy + int(f * s)
            for y in range(max(y0, fp), min(y1, v.oy + fh)):
                P[y][sx] = gr[y - fp]


# --- bosses: each one drawn from shapes ------------------------------------------------------
PHASE_CORE = [(255, 210, 90), (255, 130, 60), (255, 60, 70), (230, 80, 255)]


def draw_boss(v, e, t, py):
    b = e.boss
    fl = e.flash > 0 and int(t * 30) % 3 == 0
    C = (lambda c: mix(c, WHITE, 0.45)) if fl else (lambda c: c)
    x, y = e.x, e.y
    core = C(PHASE_CORE[min(3, b["phase"])])
    pulse = 0.5 + 0.5 * math.sin(t * 6)
    key = b["key"]
    if b["mid"]:
        v.spr(SPR[key][0], x, y, fl)
        cx, cy, cw, ch = b["bd"]["core"]
        v.circle(x + cx, y + cy, 1.2 + 0.6 * pulse, mix(core, WHITE, 0.4 * pulse))
        return
    if key == "scrapmonarch":
        G, gg, d, rust = C((96, 102, 120)), C((150, 156, 172)), C((44, 48, 64)), C((150, 96, 58))
        a = 0.5 + 0.5 * math.sin(t * 2.2)
        for sgn in (-1, 1):   # the claws
            bx, by = x - 6, y + sgn * 11
            tx, ty = x - 20, y + sgn * (13 + 5 * a)
            v.poly([(bx, by - 2), (tx, ty - 2), (tx, ty + 2), (bx, by + 2)], G)
            v.poly([(tx, ty - 3), (tx - 6, ty - sgn * 3 * a - 1), (tx - 1, ty)], gg)
            v.poly([(tx, ty + 3), (tx - 6, ty + sgn * 3 * a + 1), (tx - 1, ty)], gg)
        v.poly([(x - 8, y - 17), (x + 15, y - 14), (x + 15, y + 14), (x - 8, y + 17), (x - 14, y + 8),
                (x - 14, y - 8)], G)
        v.rect(x - 4, y - 13, 17, 4, gg)
        v.rect(x - 4, y + 9, 17, 4, gg)
        v.rect(x + 1, y - 7, 11, 14, d)
        v.rect(x + 3, y - 15, 3, 3, rust)
        v.rect(x + 8, y + 12, 4, 2, rust)
        for k in range(4):
            v.rect(x + 2 + k * 3, y - 5 + (k % 2) * 6, 2, 4, rust if k % 2 else gg)
        v.circle(x - 6, y, 4.8, d)
        v.circle(x - 6, y, 3.4, core)
        v.circle(x - 6.8, y - 0.8, 1.3, WHITE)
        v.line(x + 10, y - 14, x + 13, y - 22, gg)
        v.line(x + 5, y - 15, x + 2, y - 20, gg)
    elif key == "mothergland":
        fl1, fl2, fl3 = C((200, 70, 110)), C((150, 40, 80)), C((240, 140, 170))
        r = 13 + 1.2 * math.sin(t * 3)
        for k in range(6):   # tentacles
            a = math.pi + (k - 2.5) * 0.35
            px_, py_ = x - 6, y
            for j in range(9):
                a2 = a + 0.35 * math.sin(t * 2.5 + k + j * 0.6)
                nx, ny = px_ + math.cos(a2) * 2.2, py_ + math.sin(a2) * 2.2
                v.circle(nx, ny, 1.6 - j * 0.12, fl2 if j % 2 else fl1)
                px_, py_ = nx, ny
        v.circle(x + 2, y, r, fl2)
        v.circle(x + 1, y - 1, r - 2, fl1)
        for k in range(5):
            a = t * 0.7 + k * 1.3
            v.circle(x + 4 + math.cos(a) * 7, y + math.sin(a) * 7, 2.2, fl3)
        v.circle(x - 8, y, 5.5, C((250, 230, 220)))
        ang = math.atan2(py - y, -10)
        v.circle(x - 8 + math.cos(ang) * 2, y + math.sin(ang) * 2, 3, core)
        v.circle(x - 8 + math.cos(ang) * 2.4, y + math.sin(ang) * 2.4, 1.3, (20, 10, 16))
    elif key == "dreadkiln":
        H1, H2, H3, win = C((110, 96, 90)), C((150, 130, 116)), C((70, 60, 58)), C((255, 220, 140))
        v.rect(x - 12, y - 18, 28, 36, H1)
        v.rect(x - 16, y - 10, 6, 22, H3)
        v.rect(x - 8, y - 18, 20, 4, H2)
        for k in range(5):
            for j in range(3):
                if (k + j + int(t * 2)) % 4:
                    v.rect(x - 4 + k * 3.5, y - 12 + j * 4, 2, 1.5, win)
        v.rect(x - 28, y + 2, 16, 4, H2)    # the main gun
        v.rect(x - 30, y + 1, 3, 6, H3)
        v.rect(x + 4, y - 26, 4, 8, H3)      # stacks
        v.rect(x + 10, y - 24, 3, 6, H3)
        v.rect(x - 12, y + 10, 28, 3, H3)
        v.rect(x - 12, y + 14, 28, 1, C((255, 140, 50)))
        v.rect(x - 12, y - 8, 8, 6, C((40, 34, 34)))
        v.rect(x - 11, y - 7, 6, 4, mix(core, WHITE, 0.3 * pulse))
    elif key == "drownedbell":
        sw = 3 * math.sin(t * 1.6)
        B1, B2, B3 = C((60, 140, 130)), C((120, 200, 180)), C((30, 80, 80))
        v.poly([(x - 6, y - 15), (x + 6, y - 15), (x + 9, y - 4), (x + 14, y + 7), (x - 14, y + 7),
                (x - 9, y - 4)], B1)
        v.rect(x - 14, y + 5, 28, 3, B2)
        v.rect(x - 8, y - 6, 16, 2, B2)
        v.rect(x - 2, y - 19, 4, 4, B3)
        for k in range(4):
            v.line(x - 12 + k * 7, y + 8, x - 13 + k * 7 + sw * 0.3, y + 14 + k % 2 * 2, C((40, 120, 70)))
        v.line(x, y + 7, x + sw, y + 9, B3)
        v.circle(x + sw, y + 10, 3.2, B3)
        v.circle(x + sw, y + 10, 2.2, core)
        v.ring(x, y - 2, 6 + 4 * pulse, C((150, 230, 220)), 18)
    elif key == "cinderheart":
        R1, R2, R3 = C((70, 46, 36)), C((110, 70, 50)), C((255, 120, 40))
        v.circle(x, y, 12.5, R1)
        v.circle(x - 1, y - 1, 10.5, R2)
        for k in range(7):
            a = k * 0.9 + 0.3 * math.sin(t + k)
            v.line(x, y, x + math.cos(a) * 11, y + math.sin(a) * 11, mix(R3, (255, 220, 120), pulse * 0.5))
        v.circle(x, y, 5 + 1.2 * pulse, mix(R3, core, 0.5))
        v.circle(x, y, 3, mix(core, WHITE, 0.4))
    elif key == "ambersovereign":
        Y1, Y2, K1, wing = C((230, 170, 40)), C((255, 220, 100)), C((40, 30, 16)), C((200, 220, 230))
        fl_ = 4 * math.sin(t * 18)
        wc = mix(wing, (60, 50, 30), 0.4)
        v.poly([(x - 2, y - 6), (x + 10, y - 16 - fl_), (x + 16, y - 12 - fl_), (x + 4, y - 4)], wc)
        v.poly([(x - 2, y + 4), (x + 10, y + 14 + fl_), (x + 16, y + 10 + fl_), (x + 4, y + 2)], wc)
        for k in range(5):    # the abdomen
            v.circle(x + 6 + k * 2.2, y + 3 + k * 1.2, 6 - k * 0.6, Y1 if k % 2 == 0 else K1)
        v.circle(x - 2, y - 1, 5.5, Y1)
        v.circle(x - 2, y - 1, 3.5, K1)
        v.circle(x - 9, y - 3, 4.5, Y2)
        v.line(x - 13, y - 1, x - 17, y + 2 + fl_ * 0.3, K1)
        v.line(x - 13, y + 1, x - 16, y + 5, K1)
        v.line(x - 9, y - 7, x - 12, y - 13, K1)
        v.line(x - 8, y - 7, x - 6, y - 14, K1)
        v.circle(x - 6, y - 4, 2.0, core)
        v.circle(x - 11, y - 4, 1.2, C((200, 30, 20)))
        v.circle(x - 11, y - 1.5, 1.2, C((200, 30, 20)))
    elif key == "chronoprism":
        c1, c2, c3 = C((120, 200, 250)), C((200, 240, 255)), C((80, 90, 200))
        v.poly([(x, y - 15), (x + 10, y), (x, y + 15), (x - 10, y)], c3)
        v.poly([(x, y - 12), (x + 7, y), (x, y + 12), (x - 7, y)], c1)
        for k in range(3):
            a = t * 1.3 + k * TAU / 3
            v.line(x, y, x + math.cos(a) * 7, y + math.sin(a) * 11, c2)
        for k in range(12):
            a = -t * 0.8 + k * TAU / 12
            v.blob(x + math.cos(a) * 14, y + math.sin(a) * 14, c2 if k % 3 else core, 1.4)
        v.circle(x, y, 3.2, mix(core, WHITE, 0.3 * pulse))
    else:   # the void engine
        m1, m2, m3 = C((60, 50, 70)), C((100, 86, 110)), C((30, 24, 36))
        ring_c = C(PHASE_CORE[min(3, b["phase"])])
        v.rect(x - 4, y - 20, 20, 40, m1)
        v.rect(x - 2, y - 18, 16, 36, m3)
        for k in range(4):
            yy = y - 16 + k * 10 + 2 * math.sin(t * 3 + k)
            v.rect(x + 8, yy, 10, 3, m2)
            v.rect(x + 8, yy + 1, 10, 1, mix(ring_c, m2, 0.5))
        for k in range(10):
            a = t * (1.5 if k % 2 else -1.0) + k * TAU / 10
            v.blob(x - 6 + math.cos(a) * 11, y + math.sin(a) * 11, ring_c, 1.5)
        v.circle(x - 6, y, 8, m2)
        v.circle(x - 6, y, 6.5, (8, 4, 14))
        v.ring(x - 6, y, 5 + pulse, ring_c, 24)
        v.circle(x - 6, y, 2.4, mix(ring_c, WHITE, 0.5 * pulse))
        v.rect(x - 26, y - 1, 12, 2, m2)


# --- the rest of the picture -------------------------------------------------------------------
BOLT_C = ((140, 240, 255), (255, 255, 255))


def draw_actors(g, v):
    t = g.t
    s = v.s
    # enemies
    for e in g.enemies:
        if e.dead:
            continue
        if e.boss is not None:
            draw_boss(v, e, e.boss["st"], g.py)
            continue
        k = e.kind
        fl = e.flash > 0 and int(t * 30) % 2 == 0
        if k in ("piston", "prism"):
            top, h = e.y - e.h / 2, e.h
            if k == "piston":
                v.rect(e.x - 5, top, 10, h, (90, 84, 96))
                v.rect(e.x - 4, top, 2, h, (150, 140, 156))
                cap = top + h - 3 if e.ceil else top
                v.rect(e.x - 6, cap, 12, 3, (200, 190, 60))
                for j in range(0, 12, 3):
                    v.rect(e.x - 6 + j, cap, 1.5, 3, (40, 36, 30))
            else:
                tip = top + h if e.ceil else top
                base = top if e.ceil else top + h
                v.poly([(e.x - 4, base), (e.x + 4, base), (e.x + 1.5, tip), (e.x - 1.5, tip)], (110, 180, 240))
                v.poly([(e.x - 1, base), (e.x + 2, base), (e.x + 0.5, tip)], (210, 245, 255))
            continue
        if k == "hook":
            top = e.data.get("top", 0)
            v.rect(e.x - 0.5, top, 1, e.y - top - 2, (120, 120, 130))
        if k == "phantom" and e.ghost:
            if int(t * 20) % 3 == 0:
                v.dot(e.x + g.rnd.uniform(-3, 3), e.y + g.rnd.uniform(-3, 3), (150, 100, 220))
            continue
        frames = SPR[SPRITE_OF.get(k, k)]
        sp = frames[int(e.t * 6) % len(frames)] if len(frames) > 1 else frames[0]
        v.spr(sp, e.x, e.y, fl, False, e.fv)
        if k in ("turret", "cannon"):
            a = math.atan2(g.py - e.y, g.px - e.x)
            by = e.y + (1.5 if e.ceil else -1.5)
            ln = 4 if k == "turret" else 6
            v.line(e.x, by, e.x + math.cos(a) * ln, by + math.sin(a) * ln, (200, 206, 220))
        elif k == "vent" and e.data.get("on"):
            y0 = e.y + 2 if e.ceil else e.y - 24
            for j in range(0, 22, 2):
                w = 1.5 + 1.2 * math.sin(t * 20 + j)
                c = (255, 230, 120) if j % 4 == 0 else (255, 140, 40)
                v.rect(e.x - w, y0 + j, w * 2, 2, c)
        elif k == "node" and e.ceil:
            o = e.data.get("other")
            if o is not None and not o.dead:
                c = (255, 120, 255) if int(t * 20) % 2 else (200, 80, 255)
                v.rect(e.x - 0.5, e.y + 2, 1, max(0, o.y - e.y - 4), c)
        elif k == "mine" and "arm" in e.data and int(t * 16) % 2:
            v.ring(e.x, e.y, 5, (255, 80, 80), 14)
    # lasers and sweeps
    for L in g.lasers:
        x = L["o"].x + L["dx"]
        if L["t"] < L["warn"]:
            if int(g.t * 20) % 2:
                v.rect(0, L["y"] - 0.2, x, 0.5, (255, 90, 90))
        else:
            h = L["h"]
            v.rect(0, L["y"] - h / 2, x, h, (255, 70, 60))
            v.rect(0, L["y"] - h / 4, x, h / 2, (255, 230, 210))
    for sw in g.sweeps:
        o = sw["o"]
        ox, oy = o.x - o.w / 2 + 2, o.y
        dx, dy = math.cos(sw["a"]), math.sin(sw["a"])
        if sw["t"] < sw["warn"]:
            if int(g.t * 20) % 2:
                for k in range(0, 140, 4):
                    v.dot(ox + dx * k, oy + dy * k, (255, 120, 120))
        else:
            for off in (-1.2, 0, 1.2):
                c = (255, 240, 220) if off == 0 else (255, 80, 70)
                v.line(ox - dy * off, oy + dx * off, ox + dx * 150 - dy * off, oy + dy * 150 + dx * off, c)
    # items
    for it in g.items:
        if it.kind == "crystal":
            c = CRYSTAL_C[it.color]
            r = 3 + 0.4 * math.sin(it.t * 8)
            v.poly([(it.x, it.y - r), (it.x + r * 0.8, it.y), (it.x, it.y + r), (it.x - r * 0.8, it.y)], c)
            v.poly([(it.x - 0.4, it.y - r * 0.6), (it.x + r * 0.35, it.y), (it.x - 0.4, it.y)], WHITE)
        else:
            c, letter, _ = ITEMS[it.kind]
            v.circle(it.x, it.y, 3, shade(c, 0.6))
            v.circle(it.x, it.y, 2.2, c)
            col, row = v.X(it.x), v.Y(it.y) // 2
            if v.x0 <= col < v.x1 and v.y0 // 2 <= row < (v.y1 - 1) // 2 + 1 and s >= 0.9:
                v.cv.put(col, row, letter, (10, 10, 16), c)
    # player shots
    for sh in g.shots:
        k = sh.kind
        x, y = sh.x, sh.y
        if k == "bolt":
            v.rect(x - 2, y - 0.4, 4, 1, BOLT_C[0])
            v.rect(x, y - 0.4, 2, 1, WHITE)
        elif k == "bitbolt":
            v.rect(x - 1, y - 0.4, 2.5, 1, (180, 230, 255))
        elif k == "lance1":
            v.rect(x - 4, y - 1.2, 7, 2.4, (120, 200, 255))
            v.rect(x - 2, y - 0.6, 5, 1.2, WHITE)
        elif k == "lance2":
            v.rect(x - 9, y - 1, 6, 2, (80, 140, 255))
            v.circle(x, y, 3.2, (110, 180, 255))
            v.circle(x + 0.5, y, 2, (220, 240, 255))
        elif k == "ring":
            r = 1.0 + min(1.8, sh.t * 6)
            v.ring(x, y, r, (255, 110, 90) if int(sh.t * 20) % 2 else (255, 200, 160), 12)
        elif k == "ray":
            pts = sh.data["tr"] + [(x, y)]
            for i in range(len(pts) - 1):
                v.line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], (90, 150, 255) if i < 3 else (200, 230, 255))
        elif k == "crawl":
            v.rect(x - 2, y - 1.2, 4, 2.4, (250, 210, 60))
            v.rect(x - 1, y - 0.6, 2, 1.2, (255, 250, 200))
        elif k == "wave":
            hh = sh.hh
            v.rect(x - 0.8, y - hh, 1.6, hh * 2, (250, 220, 70))
            v.rect(x - 0.3, y - hh * 0.6, 1, hh * 1.2, (255, 255, 210))
        elif k == "needle":
            v.line(x - sh.vx * 0.025, y - sh.vy * 0.025, x, y, (110, 240, 120))
            v.dot(x, y, (230, 255, 220))
        elif k == "scatter":
            v.circle(x, y, 1.6, (200, 120, 255))
            v.dot(x, y, WHITE)
        elif k == "frag":
            v.blob(x, y, (220, 170, 255))
        elif k == "missile":
            v.line(x - sh.vx * 0.02, y - sh.vy * 0.02, x, y, (250, 160, 70))
            v.dot(x, y, WHITE)
        elif k == "bomb":
            v.circle(x, y, 1.3, (220, 150, 80))
            v.dot(x, y - 0.5, (255, 230, 160))
    for pts, life in g.arcs:
        for i in range(len(pts) - 1):
            (xa, ya), (xb, yb) = pts[i], pts[i + 1]
            mx, my = (xa + xb) / 2 + g.rnd.uniform(-2, 2), (ya + yb) / 2 + g.rnd.uniform(-2, 2)
            v.line(xa, ya, mx, my, (220, 240, 255))
            v.line(mx, my, xb, yb, (160, 200, 255))
    for x0, y, h, bt, dur, nova in g.beams:
        k = 1 - bt / dur
        hh = h * (0.4 + 0.6 * k)
        outer = (200, 120, 255) if nova else (90, 150, 255)
        v.rect(x0, y - hh / 2, FW - x0 + 2, hh, outer)
        v.rect(x0, y - hh / 3, FW - x0 + 2, hh * 2 / 3, mix(outer, WHITE, 0.6))
        v.rect(x0, y - hh / 6, FW - x0 + 2, max(0.6, hh / 3), WHITE)
    # the ship, its pod and bits
    if g.alive and not (g.inv > 0 and int(g.t * 16) % 2 and g.phase == "play"):
        if g.charge > CHARGE_LV[0]:
            lv = 3 if g.charge >= CHARGE_LV[2] else 2 if g.charge >= CHARGE_LV[1] else 1
            over = g.charge >= CHARGE_LV[3]
            r = 1.2 + lv * 0.9 + 0.5 * math.sin(t * 30)
            col = (255, 120, 255) if over else (140, 200, 255)
            v.circle(g.px + 9, g.py, r, col)
            v.circle(g.px + 9, g.py, max(0.6, r - 1.2), WHITE)
        fl = 1.5 + math.sin(t * 40)
        v.rect(g.px - 8 - fl, g.py - 0.5, 2 + fl, 1.6, (255, 170, 60))
        v.rect(g.px - 7, g.py - 0.2, 1.5, 1, (255, 250, 200))
        v.spr(SHIP, g.px, g.py)
        if g.shield:
            v.ring(g.px, g.py, 7 + 0.5 * math.sin(t * 8), (120, 210, 255), 30)
        for bx, by in g.bits():
            v.circle(bx, by, 1.7, (80, 150, 200))
            v.circle(bx, by, 0.9, (200, 240, 255))
    p = g.pod
    if p is not None:
        col = CRYSTAL_C.get(g.pod_color, (200, 200, 220))
        v.circle(p.x, p.y, 3.3, (70, 76, 96))
        v.circle(p.x - 0.4, p.y - 0.4, 2.6, (150, 156, 176))
        d = -1 if p.state == "back" else 1
        v.circle(p.x + d * 0.8, p.y, 1.6 + 0.3 * math.sin(t * 10), col)
        v.rect(p.x + d * 2.4 - 0.5, p.y - 3.5, 1, 1.5, (210, 214, 230))
        v.rect(p.x + d * 2.4 - 0.5, p.y + 2, 1, 1.5, (210, 214, 230))
    # enemy bullets
    for b in g.ebul:
        if b.kind == "orb":
            v.circle(b.x, b.y, 1.8, (255, 90, 60))
            v.circle(b.x, b.y, 0.9, (255, 230, 170))
        elif b.kind == "lob":
            v.circle(b.x, b.y, 1.2, (170, 130, 100))
        else:
            v.blob(b.x, b.y, (255, 120, 170) if int(b.t * 12) % 2 else (255, 80, 130), 1.6)
            v.dot(b.x, b.y, (255, 235, 245))
    # explosions, particles, shock waves
    for x, y, size, bt, dur, cols in g.blasts:
        k = bt / dur
        r = size * (0.5 + k)
        v.circle(x, y, r, cols[min(3, int(k * 4))])
        if k < 0.6:
            v.circle(x, y, r * 0.55, cols[0])
    for pp in g.parts:
        v.dot(pp[0], pp[1], pp[6] if pp[4] > pp[5] * 0.4 else shade(pp[6], 0.6))
    for x, y, wt, dur in g.waves:
        v.ring(x, y, 4 + wt / dur * 90, (255, 240, 220), 80)


def field_geom(cols, rows, hud):
    if hud:
        ah = (rows - 2) * 2
        s = min(cols / FW, ah / FH)
        fw, fh = int(FW * s), int(FH * s)
        return s, (cols - fw) // 2, 2 + (ah - fh) // 2, fw, fh
    H = rows * 2
    s = max(cols / FW, H / FH)
    fw, fh = int(FW * s) + 1, int(FH * s) + 1
    return s, (cols - fw) // 2, (H - fh) // 2, fw, fh


def render(g, cols, rows, hud=True):
    cv = Canvas(cols, rows, (6, 6, 12))
    s, ox, oy, fw, fh = field_geom(cols, rows, hud)
    if g.shake > 0.05:
        k = g.shake * s
        ox += int(g.rnd.uniform(-k, k))
        oy += int(g.rnd.uniform(-k, k) * 0.6)
    v = View(cv, s, ox, oy, fw, fh)
    if hud:   # keep the field inside its frame even while it shakes
        f0x, f0y = (cols - fw) // 2, 2 + ((rows - 2) * 2 - fh) // 2
        v.x0, v.y0 = max(v.x0, f0x, 0), max(v.y0, f0y, 2)
        v.x1, v.y1 = min(v.x1, f0x + fw), min(v.y1, f0y + fh, (rows - 1) * 2)
    draw_world(g, v)
    draw_actors(g, v)
    if hud:
        draw_hud(g, cv, v)
    return cv


def bar_cells(frac, n):
    return int(round(clamp(frac, 0, 1) * n))


def draw_hud(g, cv, v):
    cols, rows = cv.cols, cv.rows
    bg = (12, 12, 24)
    edge = mix(g.st["sky"][0], (0, 0, 0), 0.3)
    # letterbox bars in a dark stage tint
    if v.x0 > 0:
        cv.rect(0, 2, v.x0, (rows - 2) * 2 - 2, edge)
    if v.x1 < cv.W:
        cv.rect(v.x1, 2, cv.W - v.x1, (rows - 2) * 2 - 2, edge)
    if v.y0 > 2:
        cv.rect(0, 2, cv.W, v.y0 - 2, edge)
    if v.y1 < (rows - 1) * 2:
        cv.rect(0, v.y1, cv.W, (rows - 1) * 2 - v.y1, edge)
    # top line: score, best, ships, bombs, stage
    hi = max(g.score, load_scores().get(GAME, {}).get(g.diff, 0) if not g.demo else 0)
    cv.put(0, 0, " " * cols, (200, 200, 210), bg)
    left = [("SCORE ", (140, 144, 180)), ("%07d" % g.score, (250, 214, 120)), ("  HI ", (140, 144, 180)),
            ("%07d" % hi, (220, 220, 230)), ("  SHIPS ", (140, 144, 180)), (str(max(0, g.lives)), (160, 220, 255)),
            ("  BOMBS ", (140, 144, 180)), (str(g.bombs), (255, 150, 110))]
    x = 1
    for txt, c in left:
        cv.put(x, 0, txt, c, bg)
        x += len(txt)
    if g.boss is not None and not g.boss.dead:
        right = g.boss.boss["bd"]["name"]
        rc = (255, 110, 110)
    elif g.mid is not None and not g.mid.dead:
        right = g.mid.boss["bd"]["name"]
        rc = (255, 190, 120)
    else:
        right = "%d %s" % (g.si + 1, g.st["name"])
        rc = g.st["accent"]
    if x + len(right) + 3 <= cols:
        cv.put(cols - len(right) - 1, 0, right, rc, bg)
    # bottom line: lance meter, pod weapon, side arms
    r = rows - 1
    cv.put(0, r, " " * cols, (200, 200, 210), bg)
    cv.put(1, r, "LANCE", (140, 144, 180), bg)
    n = 14 if cols >= 90 else 10
    frac = g.charge / CHARGE_LV[3]
    filled = bar_cells(frac, n)
    marks = {bar_cells(th / CHARGE_LV[3], n) - 1 for th in CHARGE_LV[:3]}
    for k in range(n):
        if k < filled:
            lvk = (k + 1) / n * CHARGE_LV[3]
            c = (255, 120, 255) if frac >= 1 and int(g.t * 10) % 2 else \
                (120, 200, 255) if lvk < CHARGE_LV[1] else (200, 230, 255) if lvk < CHARGE_LV[2] else (255, 255, 255)
            cv.put(7 + k, r, " ", c, c)
        else:
            cv.put(7 + k, r, "|" if k in marks else " ", (90, 96, 130), (30, 32, 52))
    x = 8 + n
    if g.has_pod:
        col = CRYSTAL_C[g.pod_color]
        name = CRYSTAL_NAME[g.pod_color] if cols >= 100 else g.pod_color.upper()
        txt = " %s %s " % (name, "I" * g.pod_lv)
        cv.put(x, r, txt, (14, 14, 20), col)
        x += len(txt) + 1
    else:
        cv.put(x, r, "NO POD", (90, 96, 130), bg)
        x += 7
    arms = []
    if g.missile:
        arms.append(("MSL%d" % g.missile, (250, 170, 70)))
    if g.crawl:
        arms.append(("GRB%d" % g.crawl, (210, 160, 100)))
    if g.nbits:
        arms.append(("BIT%d" % g.nbits, (120, 220, 255)))
    arms.append(("SPD%d" % g.speed, (120, 240, 200)))
    if g.shield:
        arms.append(("SHLD", (110, 200, 255)))
    for txt, c in arms:
        if x + len(txt) + 1 > cols:
            break
        cv.put(x, r, txt, c, bg)
        x += len(txt) + 1
    # boss health under the top line
    for e in (g.boss, g.mid):
        if e is not None and not e.dead and e.boss["state"] != "intro":
            w = v.x1 - v.x0 - 8
            f = g.boss_frac(e)
            yb = v.y0 + 1
            cv.rect(v.x0 + 4, yb, w, 1, (60, 20, 30))
            cv.rect(v.x0 + 4, yb, int(w * f), 1, (255, 80, 90) if not e.boss["mid"] else (255, 170, 90))
            break
    # banners
    mid_row = (v.y0 + v.y1) // 4
    for i, (txt, until, c, sub) in enumerate(g.banners[-2:]):
        rr = mid_row - 3 + i * 3
        if txt == "WARNING" and int(g.t * 4) % 2 == 0:
            continue
        cv.center(rr, "  %s  " % txt, (12, 12, 18), c)
        if sub:
            cv.center(rr + 1, " %s " % sub, c, (14, 14, 26))
    if g.phase == "clear" and g.tally and g.phase_t > 1.2:
        t = g.tally
        lines = ["STAGE %d CLEAR" % (g.si + 1), "", "destroyed    %3d / %d  (%d%%)" % (t["kills"], t["spawned"],
                                                                                       t["rate"] * 100),
                 "kill bonus   %7d" % t["killbonus"], "no-miss      %7d" % t["nomiss"], "",
                 "score        %07d" % g.score]
        w = max(len(l) for l in lines) + 4
        x0, y0 = max(0, (cols - w) // 2), max(1, rows // 2 - len(lines) // 2 - 1)
        cv.frame(x0 - 1, y0 * 2 - 1, w + 2, (len(lines) + 2) * 2 + 2, g.st["accent"])
        cv.box(x0, y0, [l.center(w - 4) for l in lines], (240, 240, 246), (20, 20, 40))


# =============================================================================================
# The pilot: plays like a decent human (auto mode, title demo, launcher preview, self-test)
# =============================================================================================
PLAN_T = (0.05, 0.1, 0.16, 0.23, 0.32, 0.45, 0.6, 0.8)          # look-ahead samples in seconds
PLAN_W = (1.0, 1.0, 0.95, 0.9, 0.8, 0.7, 0.55, 0.4)              # how much a predicted hit at that sample counts
PLAN_G = tuple(((PLAN_T[min(i + 1, len(PLAN_T) - 1)] - PLAN_T[max(i - 1, 0)]) / 4) for i in range(len(PLAN_T)))
SAFE_ITEMS = {"missile", "crawlbomb", "bit", "shield", "bomb", "life", "gem", "crystal", "speed"}


class Pilot:
    """Threat-aware autopilot without cheats. It predicts bullets, enemies, lasers, sweeps, vents and the terrain a
    short time ahead, tries a fan of reachable spots and flies to the safest one that also lines up a target or an
    item. It sees new bullets only after a human-like reaction delay (react seconds), misjudges speeds a little
    (err) and re-plans only every few steps; it charges the lance, fires the beam or the nova at good moments, keeps
    the pod docked (calls it back when it floats) and bombs when a hit can no longer be dodged."""

    def __init__(self, react=0.28, err=0.15, every=6, seed=None, bombs=True, lapse=0.15, focus=9, blur=1.4):
        self.react, self.err, self.every, self.lapse, self.focus = react, err, every, lapse, focus
        self.blur = blur            # how far off (field units) it judges where a bullet is: one terminal cell ~ 1.6
        self.rnd = random.Random(seed)
        self.n = 0
        self.tx = self.ty = None
        self.seen = {}
        self.release = False
        self.bombs = bombs
        self.danger = 0.0
        self.pod_t = 0.0

    # --- one step ------------------------------------------------------------------------------
    def __call__(self, g):
        inp = Inp()
        if not g.alive or g.phase != "play":
            self.tx = None
            self.seen.clear()
            return inp
        if g.entering > 0:
            return inp
        if self.tx is None or (self.n % self.every == 0 and self.rnd.random() >= self.lapse):
            self.plan(g, inp)
        self.n += 1
        dx, dy = self.tx - g.px, self.ty - g.py
        sp = SPEEDS[g.speed - 1] * DT
        inp.dx = 0 if abs(dx) < sp else (1 if dx > 0 else -1)
        inp.dy = 0 if abs(dy) < sp else (1 if dy > 0 else -1)
        inp.fire = True
        if self.release:            # one step without the charge button lets the lance go
            self.release = False
            inp.charge = False
        else:
            inp.charge = True
        inp.pod = self._pod
        inp.bomb = self._bomb
        self._pod = self._bomb = False
        return inp

    _pod = _bomb = False

    # --- what will be where ----------------------------------------------------------------------
    def threats(self, g):
        """Per look-ahead sample a list of boxes (x, y, half width, half height, weight) the ship's centre must
        stay out of, and the sweeping lasers."""
        px, py = g.px, g.py
        R = self.rnd
        err = self.err
        out = [[] for _ in PLAN_T]
        sweeps = []
        pod = g.pod
        shield = pod is not None and pod.state == "front"
        react = self.react
        bs = g.bspeed
        sp = SPEEDS[g.speed - 1]
        vel = {}
        seen_b = []
        for b in g.ebul:
            if b.t < react or b.dead:
                continue
            dxb = b.x - px
            if dxb < -50 or dxb > 75 or abs(b.y - py) > 50:
                continue
            seen_b.append((abs(dxb) + abs(b.y - py), b))
        if len(seen_b) > self.focus:                # a human keeps an eye on a handful of bullets only
            seen_b.sort(key=lambda d: d[0])
            seen_b = seen_b[:self.focus]
        for _, b in seen_b:
            if shield and b.kind != "orb" and b.vx < 0 and b.x > px + 7 and abs(b.vy) < -b.vx * 0.8:
                continue                                           # the docked pod soaks it up
            k = 1 + R.gauss(0, err)
            vx, vy = b.vx * k, b.vy * k
            bx0, by0 = b.x + R.gauss(0, self.blur), b.y + R.gauss(0, self.blur)
            hx, hy = b.r + 2.2, b.r + 1.0
            grav = 34 * bs if b.kind == "lob" else 0.0
            for i, t in enumerate(PLAN_T):        # boxes grow by the way covered between two samples
                hg = PLAN_G[i]
                out[i].append((bx0 + vx * t, by0 + vy * t + 0.5 * grav * t * t, hx + abs(vx) * hg + sp * hg,
                               hy + abs(vy + grav * t) * hg + sp * hg, 1.0))
        seen = self.seen
        now = g.t
        nseen = {}
        sc = g.scroll
        for e in g.enemies:
            if e.dead:
                continue
            key = id(e)
            last = seen.get(key)
            nseen[key] = (e.x, e.y, now, last[3] if last else now)
            if e.ghost:
                continue
            first = last[3] if last else now
            if now - first < react and e.boss is None and not e.anch:
                continue
            k = e.kind
            if e.boss is not None:
                if e.boss["state"] == "dying":
                    continue
                hx, hy = e.w * 0.42 + 3, e.h * 0.42 + 1.3
            else:
                hx, hy = e.w * 0.5 + 3, e.h * 0.5 + 1.3
            if e.x - hx > px + 80 or e.x + hx < px - 40:
                continue
            if k in ("prism", "piston"):
                d = e.data
                for i, t in enumerate(PLAN_T):
                    ln = d["lo"] + (d["hi"] - d["lo"]) * (0.5 - 0.5 * math.cos((e.t + t) * d["sp"] + d["ph"]))
                    x = e.x - sc * t              # the terrain under it moves along: same column
                    if e.ceil:
                        top, bot = -2, g.ceil_at(e.x) + ln
                    else:
                        top, bot = g.floor_at(e.x) - ln, FH + 2
                    out[i].append((x, (top + bot) / 2, hx, (bot - top) / 2 + 1.3 + 1.0, 1.0))
                continue
            if k == "vent":
                for i, t in enumerate(PLAN_T):
                    cyc = (e.t + t + e.data.get("ph", 0)) % 3.2
                    if cyc >= 2.1:
                        y0 = e.y + 2 if e.ceil else e.y - 24
                        out[i].append((e.x - sc * t, y0 + 11, 2.5 + 2 + 1, 11 + 1 + 1, 1.0))
            if k == "node":
                o = e.data.get("other")
                if e.ceil and o is not None and not o.dead:
                    y0, y1 = e.y + 2, o.y - 2
                    for i, t in enumerate(PLAN_T):
                        out[i].append((e.x - sc * t, (y0 + y1) / 2, 1.2 + 2 + 1, (y1 - y0) / 2 + 1 + 1, 1.0))
            if k == "mine" and "arm" not in e.data:
                for i, t in enumerate(PLAN_T):           # do not wake it up: it bursts into a ring
                    out[i].append((e.x - 8 * t, e.y, 14, 14, 0.25))
            if k == "orbiter":
                b = e.data["boss"]
                for i, t in enumerate(PLAN_T):
                    a = e.data["a"] + (e.t + t) * 1.6
                    r = 20 + 3 * math.sin((e.t + t) * 2)
                    out[i].append((b.x + r * math.cos(a), b.y + r * 0.85 * math.sin(a), hx + 0.5, hy + 0.5, 1.0))
                continue
            if k == "lancer" and e.t < 1.3:
                for i, t in enumerate(PLAN_T):
                    x = e.x - max(0.0, e.t + t - 1.3) * 120
                    out[i].append((x - 4, e.y, hx + 4, hy + 0.5, 1.0))
                continue
            if k == "comet" and e.t < 0.8:
                for i, t in enumerate(PLAN_T):
                    x = e.x - max(0.0, e.t + t - 0.8) * 110
                    out[i].append((x - 3, e.y, hx + 3, hy + 0.5, 1.0))
                continue
            if e.anch:
                vx, vy = -sc, 0.0
            elif last is not None and now > last[2]:
                vx, vy = (e.x - last[0]) / (now - last[2]), (e.y - last[1]) / (now - last[2])
            else:
                vx, vy = -20.0, 0.0
            if e.boss is not None:
                vx *= 0.5
                vy *= 0.5
                vel[key] = (vx, vy)
            for i, t in enumerate(PLAN_T):
                tt = min(t, 0.45)                   # beyond that a straight line says little
                out[i].append((e.x + vx * tt, e.y + vy * tt, hx + 0.6 + t, hy + 0.6 + t, 1.0))
        self.seen = nseen
        for L in g.lasers:
            x = L["o"].x + L["dx"]
            for i, t in enumerate(PLAN_T):
                tt = L["t"] + t
                if L["warn"] - 0.05 < tt < L["warn"] + L["dur"]:
                    out[i].append(((x - 2) / 2, L["y"], (x + 2) / 2 + 2 + 1, L["h"] / 2 + 1 + 1, 1.0))
        for sw in g.sweeps:
            o = sw["o"]
            for i, t in enumerate(PLAN_T):
                tt = sw["t"] + t
                if tt < sw["warn"] - 0.05 or tt > sw["warn"] + sw["dur"]:
                    continue
                k = clamp((tt - sw["warn"]) / sw["dur"], 0, 1)
                vx, vy = vel.get(id(o), (0.0, 0.0))
                sweeps.append((i, o.x - o.w / 2 + 2 + vx * t, o.y + vy * t, sw["a0"] + (sw["a1"] - sw["a0"]) * k))
        return out, sweeps

    def walls(self, g, t):
        """Ceiling and floor limits for the ship centre t seconds ahead, as a function of the screen x."""
        cam = g.cam + g.scroll * t
        C, F, N = g.ceil, g.floor, g.N
        extra = 3.2 if g.wob else 0.0

        def lim(x):
            i0 = int(cam + x - 5)
            i1 = int(cam + x + 6)
            i0 = 0 if i0 < 0 else N - 1 if i0 >= N else i0
            i1 = 0 if i1 < 0 else N - 1 if i1 >= N else i1
            c = max(C[i0:i1 + 1]) if i1 >= i0 else C[i0]
            f = min(F[i0:i1 + 1]) if i1 >= i0 else F[i0]
            if extra:
                c += extra if c > 0.5 else 0
                f -= extra if f < FH - 0.5 else 0
            return c + 2.6, f - 2.6
        return lim

    # --- choosing --------------------------------------------------------------------------------
    def goal(self, g):
        """Where a sensible pilot wants to be: lined up with the target (a boss core, the next enemy), near an
        item worth having, otherwise in the open left third."""
        px, py = g.px, g.py
        boss = None
        for e in (g.boss, g.mid):
            if e is not None and not e.dead and e.boss["state"] in ("fight", "shift", "intro"):
                boss = e
        items = [it for it in g.items if (it.kind in SAFE_ITEMS and not (it.kind == "speed" and g.speed >= 3))
                 or (it.kind == "slow" and g.speed >= 4)]
        item = min(items, key=lambda it: abs(it.x - px) + abs(it.y - py)) if items else None
        lo, hi = g.band(px + 6)
        lo, hi = lo - 2, hi + 2                    # low enough to hit a turret on the floor
        if boss is not None:
            cx, cy = boss.boss["bd"]["core"][:2]
            wy = boss.y + cy
            wx = 20.0
            if boss.boss["state"] == "intro":
                wy = FH / 2
        else:
            wx = 22.0
            best, bs = None, 1e9
            for e in g.enemies:
                if e.dead or e.inv or e.ghost or e.x < px + 6 or e.x > FW + 2:
                    continue
                s = abs(e.y - py) + (e.x - px) * 0.35 - (8 if e.solid else 0) + (e.hp if e.solid else 0)
                if e.kind == "node" and e.data.get("other") is not None and not e.data["other"].dead:
                    s -= 60                      # a beam between two nodes closes the cave: break it first
                if s < bs:
                    best, bs = e, s
            wy = best.y if best is not None else (lo + hi) / 2
        if item is not None and item.x > 6:
            wx, wy = clamp(item.x - 2, 8, FW - 20), item.y
        return clamp(wx, 8, FW - 20), clamp(wy, lo, hi), boss

    def plan(self, g, inp):
        px, py = g.px, g.py
        sp = SPEEDS[g.speed - 1]
        th, sweeps = self.threats(g)
        lims = [self.walls(g, t) for t in PLAN_T]
        wx, wy, boss = self.goal(g)
        reach = sp * 0.8
        xs = sorted({clamp(px + d, 5, FW - 9) for d in (-reach * 0.6, -reach * 0.3, 0, reach * 0.3, reach * 0.6)}
                    | {clamp(wx, 5, FW - 9)})
        ys = [clamp(py + reach * k / 7, 3, FH - 3) for k in range(-7, 8)] + [clamp(wy, 3, FH - 3)]
        # threats near the ship only: one pruned list per sample
        near = []
        for i, t in enumerate(PLAN_T):
            m = sp * t + 4
            near.append([b for b in th[i] if abs(b[0] - px) < b[2] + m and abs(b[1] - py) < b[3] + m])
        sw_by = {}
        for i, ox, oy, a in sweeps:
            sw_by.setdefault(i, []).append((ox, oy, math.cos(a), math.sin(a)))
        diag = sp * 0.7071
        best, bc, bhit = (px, py), 1e18, 9
        for tx in xs:
            for ty in ys:
                ax, ay = abs(tx - px), abs(ty - py)
                sx, sy = (1 if tx > px else -1), (1 if ty > py else -1)
                tdiag = min(ax, ay) / diag
                cost = 0.0
                first = 9
                for i, t in enumerate(PLAN_T):
                    if t <= tdiag:
                        x, y = px + sx * diag * t, py + sy * diag * t
                    else:
                        d = min(ax, ay)
                        rest = (t - tdiag) * sp
                        x = px + sx * (d + min(ax - d, rest))
                        y = py + sy * (d + min(ay - d, rest))
                    w = PLAN_W[i]
                    c, f = lims[i](x)
                    if y < c or y > f:
                        cost += 900 * w
                    else:
                        gap = min(y - c, f - y)
                        if gap < 3:
                            cost += (3 - gap) * 6 * w
                    for bx, by, hx, hy, bw in near[i]:
                        ex, ey = abs(bx - x) - hx, abs(by - y) - hy
                        if ex < 0 and ey < 0:
                            cost += 1000 * w * bw
                            if bw >= 1:
                                first = min(first, i)
                        else:
                            e = ex if ex > ey else ey
                            if e < 2.5:
                                cost += (2.5 - e) * 5 * w * bw
                    for ox, oy, dx, dy in sw_by.get(i, ()):
                        rx, ry = x - ox, y - oy
                        if rx * dx + ry * dy > 0 and abs(rx * dy - ry * dx) < 2.6 + 2.0:
                            cost += 1000 * w
                            first = min(first, i)
                cost += abs(ty - wy) * 1.2 + abs(tx - wx) * 0.5 + (ax + ay) * 0.05
                if tx < 10 or tx > FW - 24:
                    cost += 15
                if cost < bc:
                    best, bc, bhit = (tx, ty), cost, first
        self.tx, self.ty = best
        self.danger = bhit
        # bombs: a hit that can no longer be dodged
        if self.bombs and bhit <= 1 and g.bombs > 0 and g.inv <= 0 and not g.shield:
            self._bomb = True
        # the lance: beam when something worth it is in the lane or bullets come down it, the nova at full charge
        if g.charge >= CHARGE_LV[2]:
            lane = 0.0
            for e in g.targets():
                if e.x > px + 8 and abs(e.y - py) < e.h / 2 + 3:
                    lane += 3 if e.boss is not None else max(1.0, e.hp / 4)
            bul = sum(1 for b in g.ebul if b.x > px + 8 and abs(b.y - py) < 4)
            if g.charge >= CHARGE_LV[3]:
                if lane > 0 or bul >= 2 or bhit <= 3:
                    self.release = True
            elif (lane >= 3 or bul >= 4 or bhit <= 2) and not boss:
                self.release = True
            elif boss is not None and bhit <= 1:
                self.release = True
        # the pod: keep it docked
        p = g.pod
        if p is not None and p.state in ("free", "out") and p.t > 0.3:
            self.pod_t += self.every * DT
            if self.pod_t > 0.6:
                self._pod = True
                self.pod_t = 0.0
        else:
            self.pod_t = 0.0


def bot_input(g):
    """The pilot for a game (one per game, kept on it); the title demo and the self-test use this."""
    p = getattr(g, "_pilot", None)
    if p is None:
        p = g._pilot = Pilot(react=0.12, seed=1)
    return p(g)


class TitleDemo:
    """The ship on autopilot through a stage (behind the title screen and in the launcher preview)."""

    def __init__(self, stage=None):
        self.k = random.randrange(len(STAGES)) if stage is None else stage
        self.new_run()

    def new_run(self):
        si = self.k % len(STAGES)
        self.k += 1
        g = self.g = Game(si, "normal", demo=True, god=True, seed=self.k)
        rnd = random.Random(self.k)
        g.has_pod, g.pod_color, g.pod_lv = True, rnd.choice(CRYSTALS), rnd.randint(2, 3)
        g.nbits, g.missile, g.speed = rnd.randint(1, 2), 1, 2
        g.cam = rnd.uniform(FW, LEN * 0.8)
        while g.ev_i < len(g.events) and g.events[g.ev_i][0] <= g.cam + FW * 0.9 and g.events[g.ev_i][1] != "mid":
            g.ev_i += 1
        g.spawn_player()
        g.banners = []
        self.t = 0.0
        self.acc = 0.0

    def scene(self, cols, rows, dt):
        g = self.g
        self.acc += min(0.1, max(0.0, dt))
        n = 0
        while self.acc >= DT and n < 8:
            g.step(bot_input(g))
            self.acc -= DT
            n += 1
        self.t += dt
        cv = render(g, cols, rows, hud=False)
        if self.t > 24 or g.phase != "play":
            self.new_run()
        return cv


# =============================================================================================
# Menus and the game loop
# =============================================================================================
def progress():
    rec = load_scores().get(GAME, {})
    return clamp(int(rec.get("unlocked", 1)), 1, len(STAGES)), rec


def too_small(term):
    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (%dx%d)." % (MIN_COLS, MIN_ROWS))


def render_title(demo, cols, rows, dt, sel, stage, diff, help_, kitty):
    cv = demo.scene(cols, rows, dt)
    unlocked, rec = progress()
    st = STAGES[stage]
    items = ["Play", "Stage       < %d  %s >" % (stage + 1, st["name"]), "Difficulty  < %s >" % DIFFS[diff], AUTO_LABEL]
    extra = ["", "Eight stages, sixteen bosses, six pod crystals.",
             "Stages unlocked: %d of %d" % (unlocked, len(STAGES)),
             "Keys: %s" % ("with releases (kitty protocol)" if kitty else "classic terminal mode")]
    b = rec.get(DIFFS[diff])
    title_screen(cv, "VOIDLANCE", "a side-scrolling star fighter with a charge lance", items, sel,
                 "best (%s): %d" % (DIFFS[diff], b) if b else None, extra=extra,
                 keys="Up/Down choose   Left/Right change   Enter start   ? help   Esc quit",
                 help_lines=help_lines(kitty), show_help=help_, dim=0.4)
    return cv


def render_over(g, cv, record, won, auto=False):
    if won:
        lines = ["THE VOID FALLS SILENT", "", "All eight stages cleared.", "score %07d" % g.score]
    else:
        lines = ["GAME OVER", "", "score %07d" % g.score, "reached stage %d  %s" % (g.si + 1, g.st["name"])]
    if g.continues:
        lines.append("continues used: %d" % g.continues)
    if record:
        lines += ["", "** NEW RECORD **"]
    if auto:
        lines += ["", "auto mode: a new round starts in a moment"]
    else:
        lines += ["", "Esc / Q: menu" if won else "Enter: continue (score resets)   Esc / Q: menu"]
    w = max(len(l) for l in lines) + 4
    x, y = max(0, (cv.cols - w) // 2), max(1, cv.rows // 2 - len(lines) // 2 - 1)
    edge = (250, 214, 120) if record else (110, 204, 160) if won else (200, 76, 86)
    cv.frame(x - 1, y * 2 - 1, w + 2, (len(lines) + 2) * 2 + 2, edge)
    cv.box(x, y, [l.center(w - 4) for l in lines], (240, 240, 246), (24, 22, 44))


def continue_game(g):
    g.continues += 1
    g.score = 0
    g.next_life, g.life_gap = 60000, 60000
    g.lives = g.d["lives"]
    g.bombs = g.d["bombs"]
    g.missile = g.crawl = g.nbits = 0
    g.pod_lv = 1 if g.has_pod else 0
    g.speed = 1
    g.load_stage(g.si)


def play(term, held, stage, diff):
    g = Game(stage, DIFFS[diff])
    charge_on = False
    tap = False
    shots_seen = 0
    acc = 0.0
    last = time.time()
    record = None
    unlocked, _ = progress()
    while True:
        now = time.time()
        frame = min(0.1, now - last)
        last = now
        for name, kind in term.events(0):
            held.feed(name, kind, now)
        held.tick(now)
        pod = bomb = False
        for k in held.take_hits():
            if g.phase in ("over", "won"):
                if k in ("q", "esc"):
                    return
                if k in ("enter", " ") and g.phase == "over" and g.phase_t > 1.0:
                    continue_game(g)
                    record = None
                    charge_on = False
                continue
            a = shared_key(k, g.paused)
            if a == "pause":
                g.paused = True
                SND.play("pause")
            elif a == "resume":
                g.paused = g.help = False
            elif a == "quit":
                if record is None and g.score:
                    submit(GAME, DIFFS[diff], g.score)
                return
            elif a == "help":
                g.help = not g.help
                g.paused = True
            elif a == "sound":
                if SND.toggle():
                    SND.play("sound_on")
            elif a is None:
                if k == "f":
                    pod = True
                elif k == "b":
                    bomb = True
                elif k == "c":
                    charge_on = not charge_on
                elif k == " " and term.kitty:
                    tap = True
        dx = (1 if held.down("right", "d") else 0) - (1 if held.down("left", "a") else 0)
        dy = (1 if held.down("down", "s") else 0) - (1 if held.down("up", "w") else 0)
        if not g.alive:
            charge_on = False
        if term.kitty:
            inp = Inp(dx, dy, tap or held.down("x"), held.down(" ") or charge_on, pod, bomb)
        else:
            inp = Inp(dx, dy, held.down(" ", "x"), charge_on, pod, bomb)
        if not g.paused:
            acc += frame
            n = 0
            while acc >= DT and n < 6:
                g.step(inp)
                inp.pod = inp.bomb = False
                acc -= DT
                n += 1
                if g.shots_fired != shots_seen:
                    shots_seen = g.shots_fired
                    tap = False
                    inp.fire = held.down("x") if term.kitty else inp.fire
            if n == 6:
                acc = 0.0
        if g.si + 1 > unlocked:
            unlocked = g.si + 1
            submit(GAME, "unlocked", unlocked)
        if g.phase in ("over", "won") and record is None:
            record = submit(GAME, DIFFS[diff], g.score)
            if g.phase == "won":
                submit(GAME, "unlocked", len(STAGES))
        cols, rows = term.size()
        if cols < MIN_COLS or rows < MIN_ROWS:
            too_small(term)
            time.sleep(0.2)
            last = time.time()
            continue
        cv = render(g, cols, rows)
        if g.phase in ("over", "won") and g.phase_t > 0.8:
            render_over(g, cv, record, g.phase == "won")
        elif g.paused:
            overlay(cv, help_lines(term.kitty) if g.help else PAUSE_LINES + ["", SND.label()])
        term.write(cv.emit())
        time.sleep(max(0.0, 1 / 60 - (time.time() - now)))


def render_auto(g, auto, cols, rows):
    """The real game screen one row shorter, with the auto-mode bar on the last row."""
    cv = render(g, cols, rows - 1)
    cv.rows, cv.H = rows, rows * 2
    cv.px += [[(6, 6, 12)] * cv.W for _ in range(2)]
    auto.banner(cv, extra="%s  stage %d" % (g.diff, g.si + 1))
    return cv


def play_auto(term, stage, diff, hook=None):
    """Auto mode: the real game (same stage and difficulty as chosen, no invulnerability) flown by the pilot.
    After a game over or the last stage the result box shows for three seconds, then a new round starts.
    Never records a score or unlocks a stage."""
    auto = AutoMode()
    rounds = 0

    def new_round():
        g = Game(stage, DIFFS[diff])
        return g, Pilot(seed=rounds)
    g, pilot = new_round()
    last = time.time()
    shown = 0.0
    while True:
        now = time.time()
        frame = min(0.1, now - last)
        last = now
        for k, kind in term.events(0):
            if kind != "press":
                continue
            a = auto.key(k)
            if a == "stop":
                return rounds
            if a == "sound" and SND.toggle():
                SND.play("sound_on")
        for _ in range(auto.steps(frame, DT)):
            g.step(pilot(g))
        if hook is not None:
            hook(g)
        if g.phase in ("over", "won") and g.phase_t > 0.8:
            if auto.scale(frame) > 0:                  # real seconds, not while paused
                shown += frame
            if shown > 3.0:
                rounds += 1
                g, pilot = new_round()
                shown = 0.0
        cols, rows = term.size()
        if cols < MIN_COLS or rows < MIN_ROWS:
            too_small(term)
            time.sleep(0.2)
            last = time.time()
            continue
        cv = render_auto(g, auto, cols, rows)
        if g.phase in ("over", "won") and g.phase_t > 0.8:
            render_over(g, cv, False, g.phase == "won", auto=True)
        term.write(cv.emit())
        time.sleep(max(0.0, 1 / 60 - (time.time() - now)))


def main():
    with KeyTerminal() as term:
        held = HeldKeys(term.kitty)
        demo = TitleDemo()
        sel, diff, help_ = 0, 1, False
        unlocked, _ = progress()
        stage = unlocked - 1
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
            cv = render_title(demo, cols, rows, min(0.1, now - last), sel, stage, diff, help_, term.kitty)
            last = now
            term.write(cv.emit())
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
                elif k in ("up", "w"):
                    sel = (sel - 1) % 4
                    SND.play("menu")
                elif k in ("down", "s", "tab"):
                    sel = (sel + 1) % 4
                    SND.play("menu")
                elif k in ("left", "a", "right", "d"):
                    d = -1 if k in ("left", "a") else 1
                    unlocked, _ = progress()
                    if sel == 1:
                        stage = (stage + d) % unlocked
                    elif sel == 2:
                        diff = (diff + d) % 3
                    else:
                        stage = (stage + d) % unlocked
                    SND.play("menu")
                elif k == "m":
                    if SND.toggle():
                        SND.play("sound_on")
                elif k in ("enter", " "):
                    SND.play("start")
                    go = "auto" if sel == 3 else True
            if go == "auto":
                play_auto(term, stage, diff)
                held.clear()
                last = time.time()
            elif go:
                held.clear()
                play(term, held, stage, diff)
                held.clear()
                unlocked, _ = progress()
                stage = min(stage, unlocked - 1)
                last = time.time()


# =============================================================================================
# Self-test
# =============================================================================================
def selftest():
    t0 = time.time()
    upd, rnd_t = [], []
    report = []

    kinds = set()

    def run(g, steps, inp_fn=bot_input):
        for _ in range(steps):
            a = time.perf_counter()
            g.step(inp_fn(g))
            upd.append(time.perf_counter() - a)
            for s in g.shots:
                kinds.add(s.kind)
            if g.arcs:
                kinds.add("arc")
            for b in g.beams:
                kinds.add("nova" if b[5] else "beam")

    def frame(g, cols, rows, emit=True):
        a = time.perf_counter()
        cv = render(g, cols, rows)
        if emit:
            cv.emit(True)
        rnd_t.append((cols, time.perf_counter() - a))
        return cv

    # terrain: every column leaves room to fly
    for si in range(len(STAGES)):
        c, f, ev = stage_data(si)
        gap = min(f[i] - c[i] for i in range(len(c)))
        assert gap >= MINGAP - 1e-6, "stage %d: the cave closes (%.1f)" % (si + 1, gap)
        assert any(e[1] == "mid" for e in ev) and ev[-1][1] == "boss", "stage %d: no midboss / boss" % (si + 1)
    # every enemy kind spawns, behaves, renders and dies
    g = Game(0, "normal", god=True, sound=False, seed=1)
    for kind in ESPEC:
        if kind in ("orbiter", "tseg", "eseg"):
            continue
        e = g.add(kind, 80, 32)
        e.st = 32
        if kind in ("prism", "piston"):
            e.data.update(lo=3, hi=20, sp=1.3, ph=0)
        if kind == "hook":
            e.anch = True
    g.spawn_wave("tendril", "snake", 30)
    g.spawn_wave("eel", "snake", 30)
    g.spawn_wave("drone", "swarm", 30)
    g.spawn_special(g.cam + FW, "node", 0.5)
    g.spawn_special(g.cam + FW, "comb", 0.5)
    run(g, 240, lambda g: Inp(0, 0, True))
    for cols, rows in ((70, 22), (120, 40)):
        frame(g, cols, rows)
    for e in list(g.enemies):
        g.kill(e)
    run(g, 30, lambda g: Inp())
    # every pickup and every pod crystal at every level, docked front, back and free
    g = Game(0, "normal", god=True, sound=False, seed=2)
    run(g, 60, lambda g: Inp())
    for kind in list(ITEMS) + ["crystal"] * 2:
        it = Item(g.px, g.py, kind, "red")
        g.collect(it)
    assert g.has_pod and g.missile and g.crawl and g.nbits and g.shield, "pickups missing"
    run(g, 60, lambda g: Inp())
    assert g.pod.state in ("front", "back"), "the pod did not dock (%s)" % g.pod.state
    for _ in range(3):
        g.collect(Item(g.px, g.py, "missile"))
        g.collect(Item(g.px, g.py, "crawlbomb"))
        g.collect(Item(g.px, g.py, "bit"))
    assert g.missile == 2 and g.crawl == 2 and g.nbits == 2
    weapons = 0
    for col in CRYSTALS:
        for lv in (1, 2, 3):
            g.pod_color, g.pod_lv = col, lv
            for state in ("front", "back", "free"):
                g.pod.state = state
                if state == "free":
                    g.pod.x, g.pod.y = 60, 30
                for _ in range(3):
                    tgt = g.add("scrapper", 70 if state != "back" else 10, g.py + 4)
                    tgt.vx = tgt.vy = 0
                n0 = len(g.shots) + len(g.arcs)
                run(g, 40, lambda g: Inp(0, 0, True))
                weapons += 1
                frame(g, 120, 40, emit=False)
                assert len(g.shots) + len(g.arcs) + g.kills >= n0, "no shots"
            g.pod.state = "front"
    # the lance at every level, the nova, smart bomb, launch and recall
    for secs in (0.5, 1.0, 1.6, 2.6):
        g.add("sentinel", 90, g.py)
        run(g, int(secs / DT), lambda g: Inp(0, 0, False, True))
        run(g, 2, lambda g: Inp())
    need = {"bolt", "bitbolt", "ring", "ray", "crawl", "wave", "needle", "scatter", "frag", "arc", "missile", "bomb",
            "lance1", "lance2", "beam", "nova"}
    assert need <= kinds, "weapons never fired: %s" % sorted(need - kinds)
    g.pod.state = "front"
    run(g, 1, lambda g: Inp(pod=True))
    assert g.pod.state == "out"
    run(g, 60, lambda g: Inp())
    run(g, 1, lambda g: Inp(pod=True))
    assert g.pod.state == "return"
    run(g, 90, lambda g: Inp())
    assert g.pod.state in ("front", "back"), "the pod did not come back (%s)" % g.pod.state
    b0 = g.bombs
    for _ in range(20):
        g.ebullet(80, 30, math.pi, 10)
    run(g, 1, lambda g: Inp(bomb=True))
    assert g.bombs == b0 - 1 and not g.ebul, "smart bomb"
    report.append("%d pod weapon set-ups, shots seen: %s" % (weapons, " ".join(sorted(kinds))))
    # dying, the checkpoint and the continue
    g = Game(0, "hard", sound=False, seed=3)
    g.has_pod, g.pod_color, g.pod_lv = True, "blue", 3
    g.cam = LEN * 0.4
    g.checkpoint = LEN * 0.34 - FW
    g.inv = 0
    g.player_hit()
    run(g, 200, lambda g: Inp())
    assert g.alive and g.lives == 2 and g.pod_lv == 2 and abs(g.cam - g.checkpoint) < 40, "respawn"
    while g.lives > 0:
        g.inv = 0
        g.player_hit()
        run(g, 200, lambda g: Inp())
    assert g.phase == "over"
    continue_game(g)
    assert g.phase == "play" and g.score == 0 and g.continues == 1
    # every stage: play from the start, the midboss, the boss with all its phases
    for si in range(len(STAGES)):
        g = Game(si, "normal", god=True, sound=False, seed=10 + si)
        g.has_pod, g.pod_color, g.pod_lv = True, CRYSTALS[si % 6], 3
        g.missile = g.crawl = g.nbits = 2
        g.spawn_player()
        run(g, 900)
        frame(g, 70, 22)
        frame(g, 120, 40)
        frame(g, 200, 60)
        g.cam = LEN * 0.5 - FW - 4
        g.ev_i = next(i for i, e in enumerate(g.events) if e[1] == "mid")
        run(g, 400)
        assert g.mid is not None, "stage %d: no midboss" % (si + 1)
        frame(g, 120, 40)
        g.dmg_mult = 3.0
        for _ in range(60):
            if g.mid_done:
                break
            run(g, 60)
        assert g.mid_done, "stage %d: the midboss was not beaten" % (si + 1)
        g.dmg_mult = 1.0
        g.cam = LEN - 2
        g.ev_i = len(g.events) - 1
        run(g, 200)
        assert g.boss is not None, "stage %d: no boss" % (si + 1)
        frame(g, 120, 40)
        g.dmg_mult = 2.5
        phases = set()
        for k in range(160):
            if g.phase != "play":
                break
            run(g, 30)
            phases.add(g.boss.boss["phase"])
            if k % 8 == 0:
                frame(g, (70, 120, 200)[k % 3], (22, 40, 60)[k % 3])
        assert g.phase == "clear", "stage %d: the boss was not beaten" % (si + 1)
        kills, spawned = g.kills, g.spawned
        bd = BOSSES[g.st["boss"]]
        assert len(phases) >= len(bd["hp"]), "stage %d: phases seen %s" % (si + 1, sorted(phases))
        frame(g, 120, 40)
        run(g, int(6.2 / DT))
        assert (g.si == si + 1) or g.phase == "won", "stage %d: no next stage" % (si + 1)
        report.append("stage %d %-16s ok: %d of %d enemies destroyed, midboss and %d-phase boss beaten" % (
            si + 1, STAGES[si]["name"], kills, spawned, len(bd["hp"])))
    # pause, help, over boxes; the title demo at all sizes; the launcher preview size
    for cols, rows in ((70, 22), (120, 40), (200, 60)):
        g = Game(2, "easy", sound=False, seed=5)
        run(g, 100)
        cv = render(g, cols, rows)
        overlay(cv, PAUSE_LINES + ["", SND.label()])
        overlay(cv, help_lines(True))
        cv.emit(False)
        g.phase = "over"
        cv = render(g, cols, rows)
        render_over(g, cv, True, False)
        render_over(g, cv, False, True)
        cv.emit(True)
        demo = TitleDemo(3)
        for i in range(30):
            render_title(demo, cols, rows, 0.1, i % 3, i % 8, i % 3, i == 29, i % 2 == 0).emit(True)
    demo = TitleDemo(0)
    for i in range(200):
        sub = demo.scene(46, 12, 0.1)
        assert sub.W == 46 and sub.H == 24
    # timing at 120x40
    g = Game(5, "normal", god=True, sound=False, seed=9)
    g.has_pod, g.pod_color, g.pod_lv, g.nbits, g.missile = True, "violet", 3, 2, 2
    g.spawn_player()
    upd.clear()
    run(g, 1200)
    a = time.perf_counter()
    for _ in range(30):
        render(g, 120, 40)
    r120 = (time.perf_counter() - a) / 30
    a = time.perf_counter()
    for _ in range(30):
        render(g, 120, 40).emit(True)
    e120 = (time.perf_counter() - a) / 30
    # auto mode: the real loop headless at x8 for a few seconds, one forced game over -> a new round, no scores
    global submit
    calls = []
    real_submit, submit = submit, (lambda *a, **k: calls.append(a))

    class FakeTerm:
        kitty = False

        def __init__(self):
            self.t0 = time.time()
            self.n = 0

        def events(self, timeout=0.0):
            self.n += 1
            if self.n <= 3:
                return [("+", "press")]          # x2, x4, x8
            if self.n == 4:
                return [("?", "press")]
            if self.n == 5:
                return [("x", "press")]           # closes the help
            return [("esc", "press")] if time.time() - self.t0 > 6.0 else []

        def size(self):
            return (70, 22)

        def write(self, s):
            pass
    seen = {"games": set(), "over": False, "far": 0.0}

    def hook(g):
        seen["games"].add(id(g))
        seen["far"] = max(seen["far"], g.cam)
        if time.time() - ft.t0 > 2.5 and not seen["over"]:
            seen["over"] = True
            g.lives = 0
            g.player_hit()
    snd, SND.enabled = SND.enabled, False          # silent, without touching the saved setting
    try:
        ft = FakeTerm()
        rounds = play_auto(ft, 0, 1, hook=hook)
    finally:
        submit = real_submit
        SND.enabled = snd
    assert not calls, "auto mode submitted a score"
    assert rounds >= 1 and len(seen["games"]) >= 2, "auto mode did not start a new round (%d)" % rounds
    report.append("auto mode: %.0fs at x8 headless, %d new round(s), no scores submitted, flew %d units" % (
        time.time() - ft.t0, rounds, seen["far"]))
    for line in report:
        print("  " + line)
    for c in (70, 120, 200):
        ts = [t for cc, t in rnd_t if cc == c]
        print("  frame with emit at %dx%d: %.1f ms average over %d frames" % (c, {70: 22, 120: 40, 200: 60}[c],
                                                                         sum(ts) / len(ts) * 1000, len(ts)))
    print("update %.2f ms per step (max %.1f), render %.1f ms at 120x40 (%.1f ms with emit); %d enemy kinds, "
          "%d midbosses, %d bosses" % (sum(upd) / len(upd) * 1000, max(upd) * 1000, r120 * 1000, e120 * 1000,
                                       len(ESPEC), len(MIDBOSSES), len(BOSSES)))
    print("Self-test ok (%.1fs)" % (time.time() - t0))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
