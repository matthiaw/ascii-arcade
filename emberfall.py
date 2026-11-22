#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EMBERFALL - The Pale Flame
A party-based fantasy role-playing game drawn entirely in ASCII, for the terminal.

Start:      python3 emberfall.py
Self-test:  python3 emberfall.py --selftest
Demo bot:   python3 emberfall.py --bot 600
Art dump:   python3 emberfall.py --art

The rules are a simplified take on the 5th-edition d20 rules from the System
Reference Document 5.1 by Wizards of the Coast LLC, licensed under CC-BY-4.0
(https://creativecommons.org/licenses/by/4.0/). Setting, story, characters
and art are original.
"""
import curses
import json
import locale
import math
import os
import random
import re
import sys
import textwrap
import time
from collections import Counter, deque

SAVE_PATH = os.path.expanduser("~/.emberfall_save.json")
MIN_W, MIN_H = 100, 30
SIDE_W = 34
LOG_H = 8
VERSION = 1

# =============================================================================
# Dice and small helpers
# =============================================================================
_DICE = re.compile(r"^(\d+)d(\d+)([+-]\d+)?$")


def roll(spec, crit=False):
    """Roll '2d6+3'. A critical hit doubles the dice, not the bonus."""
    if isinstance(spec, int):
        return spec
    m = _DICE.match(spec)
    if not m:
        return int(spec)
    n, s, b = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    if crit:
        n *= 2
    return max(0, sum(random.randint(1, s) for _ in range(n)) + b)


def dice_avg(spec):
    m = _DICE.match(spec)
    if not m:
        return int(spec)
    n, s, b = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    return n * (s + 1) / 2 + b


def d20():
    return random.randint(1, 20)


def mod(score):
    return (score - 10) // 2


def sgn(n):
    return "+%d" % n if n >= 0 else str(n)


def clamp(v, a, b):
    return a if v < a else b if v > b else v


def cheb(ax, ay, bx, by):
    return max(abs(ax - bx), abs(ay - by))


def line(x0, y0, x1, y1):
    """Bresenham line, both ends included."""
    pts = []
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        pts.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
    return pts


def wrap(text, width):
    out = []
    for para in text.split("\n"):
        if not para.strip():
            out.append("")
            continue
        out.extend(textwrap.wrap(para, width) or [""])
    return out


DIRS8 = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]

# =============================================================================
# Colours: (256-colour value, 8-colour fallback)
# =============================================================================
K = curses
BLACK = (232, K.COLOR_BLACK)   # not 16-21: base16 colour schemes repaint those
WHITE = (231, K.COLOR_WHITE)
LIGHT = (252, K.COLOR_WHITE)
GRAY = (246, K.COLOR_WHITE)
DGRAY = (240, K.COLOR_WHITE)
DDGRAY = (236, K.COLOR_BLACK)
NIGHT = (234, K.COLOR_BLACK)
RED = (196, K.COLOR_RED)
DRED = (88, K.COLOR_RED)
BLOODC = (124, K.COLOR_RED)
ORANGE = (208, K.COLOR_RED)
EMBER = (202, K.COLOR_RED)
YELLOW = (226, K.COLOR_YELLOW)
GOLD = (220, K.COLOR_YELLOW)
AMBER = (214, K.COLOR_YELLOW)
BROWN = (130, K.COLOR_YELLOW)
WOOD = (137, K.COLOR_YELLOW)
DWOOD = (94, K.COLOR_YELLOW)
FLOORBG = (52, K.COLOR_BLACK)
TAN = (180, K.COLOR_YELLOW)
SKIN = (223, K.COLOR_WHITE)
BONE = (230, K.COLOR_WHITE)
GREEN = (34, K.COLOR_GREEN)
LGREEN = (112, K.COLOR_GREEN)
DGREEN = (28, K.COLOR_GREEN)
GRASSBG = (22, K.COLOR_GREEN)
MOSS = (64, K.COLOR_GREEN)
CYAN = (51, K.COLOR_CYAN)
TEAL = (37, K.COLOR_CYAN)
PALE = (159, K.COLOR_CYAN)
ICE = (195, K.COLOR_CYAN)
BLUE = (33, K.COLOR_BLUE)
DBLUE = (24, K.COLOR_BLUE)
NAVY = (24, K.COLOR_BLUE)
PURPLE = (129, K.COLOR_MAGENTA)
MAGENTA = (201, K.COLOR_MAGENTA)
PLUM = (53, K.COLOR_MAGENTA)
PINK = (218, K.COLOR_MAGENTA)
STONE = (250, K.COLOR_WHITE)
STONEBG = (240, K.COLOR_BLACK)
CAVEBG = (235, K.COLOR_BLACK)
CAVEFL = (233, K.COLOR_BLACK)
ROCKFG = (101, K.COLOR_YELLOW)
FIRE_COLS = [RED, EMBER, ORANGE, AMBER, YELLOW]
PALE_COLS = [PALE, ICE, CYAN, (123, K.COLOR_CYAN)]
WATER_COLS = [(39, K.COLOR_CYAN), (45, K.COLOR_CYAN), (33, K.COLOR_BLUE)]
PANEL = (234, K.COLOR_BLACK)          # the shared ASCII ARCADE title colours
TITLE_SEL = (215, K.COLOR_YELLOW)
FOOTER_BG = (233, K.COLOR_BLACK)
FOOTER_FG = (246, K.COLOR_WHITE)
FOOTER_LABEL = (252, K.COLOR_WHITE)
TITLE_GRAD = [(222, K.COLOR_YELLOW), (221, K.COLOR_YELLOW), (215, K.COLOR_YELLOW), (209, K.COLOR_RED),
              (166, K.COLOR_RED)]   # top to bottom of the block letters, like the other games' titles
BRIGHT8 = {WHITE, YELLOW, CYAN, LGREEN, PINK, GOLD, ICE, PALE, MAGENTA, RED}

# =============================================================================
# Tiles
# =============================================================================
(T_GRASS, T_ROAD, T_WALL, T_FLOOR, T_DOOR, T_ODOOR, T_WATER, T_BRIDGE, T_TREE,
 T_FLOWER, T_TABLE, T_CHAIR, T_COUNTER, T_BED, T_BARREL, T_FIRE, T_ALTAR,
 T_GRAVE, T_FENCE, T_WELL, T_EXIT, T_SDOWN, T_SUP, T_CROPS, T_ROCK, T_CWALL,
 T_CFLOOR, T_ORE, T_TORCH, T_LAVA, T_PILLAR, T_SEAL, T_CHEST, T_OCHEST, T_TENT,
 T_CAGE, T_BONES, T_WEB, T_MUSH, T_ANVIL, T_RAIL, T_PALEFIRE, T_HOARD, T_CARPET,
 T_STONEFL, T_SHELF, T_CAGEDOOR, T_BUSH) = range(48)


class Tile:
    __slots__ = ("name", "glyphs", "fgs", "bg", "walk", "seethru", "anim")

    def __init__(self, name, glyphs, fgs, bg, walk, seethru, anim=False):
        self.name, self.glyphs = name, glyphs
        self.fgs = fgs if isinstance(fgs, list) else [fgs]
        self.bg, self.walk, self.seethru, self.anim = bg, walk, seethru, anim


TILES = {
    T_GRASS: Tile("grass", " , . ' ` ,  .  ", [DGREEN, GREEN, MOSS], GRASSBG, True, True),
    T_ROAD: Tile("road", " . :  .  ", [TAN, WOOD], DWOOD, True, True),
    T_WALL: Tile("wall", "#", STONE, STONEBG, False, False),
    T_FLOOR: Tile("floor", ".", WOOD, FLOORBG, True, True),
    T_DOOR: Tile("door", "+", AMBER, DWOOD, False, False),
    T_ODOOR: Tile("open door", "'", AMBER, FLOORBG, True, True),
    T_WATER: Tile("water", "~-~~", WATER_COLS, DBLUE, False, True, True),
    T_BRIDGE: Tile("bridge", "=", WOOD, DWOOD, True, True),
    T_TREE: Tile("tree", "&", [DGREEN, GREEN, (22, K.COLOR_GREEN), LGREEN], GRASSBG, False, False),
    T_FLOWER: Tile("flowers", '"*"', [PINK, YELLOW, MAGENTA, WHITE], GRASSBG, True, True),
    T_TABLE: Tile("table", "T", (223, K.COLOR_YELLOW), FLOORBG, False, True),
    T_CHAIR: Tile("chair", "h", WOOD, FLOORBG, True, True),
    T_COUNTER: Tile("counter", "=", TAN, DWOOD, False, True),
    T_BED: Tile("bed", "=", LIGHT, NAVY, False, True),
    T_BARREL: Tile("barrel", "o", BROWN, FLOORBG, False, True),
    T_FIRE: Tile("fire", "*^*'", FIRE_COLS, FLOORBG, False, True, True),
    T_ALTAR: Tile("altar", "_", GOLD, STONEBG, False, True),
    T_GRAVE: Tile("grave", "n", STONE, GRASSBG, False, True),
    T_FENCE: Tile("fence", "|", WOOD, GRASSBG, False, True),
    T_WELL: Tile("well", "O", STONE, DBLUE, False, True),
    T_EXIT: Tile("road out", ">", YELLOW, DWOOD, True, True),
    T_SDOWN: Tile("stairs down", ">", WHITE, DDGRAY, True, True),
    T_SUP: Tile("stairs up", "<", WHITE, DDGRAY, True, True),
    T_CROPS: Tile("field", '"', [GOLD, AMBER], (58, K.COLOR_YELLOW), True, True),
    T_ROCK: Tile("rock", "^", GRAY, DDGRAY, False, False),
    T_CWALL: Tile("rock wall", "#", [ROCKFG, (95, K.COLOR_YELLOW)], CAVEBG, False, False),
    T_CFLOOR: Tile("cave floor", ".", DGRAY, CAVEFL, True, True),
    T_ORE: Tile("ore vein", "*", [GOLD, AMBER], CAVEBG, False, False),
    T_TORCH: Tile("torch", "*", [AMBER, YELLOW, ORANGE], CAVEBG, False, False, True),
    T_LAVA: Tile("lava", "~~=~", [YELLOW, AMBER, ORANGE], (160, K.COLOR_RED), False, True, True),
    T_PILLAR: Tile("pillar", "O", STONE, DDGRAY, False, False),
    T_SEAL: Tile("sealed gate", "#", MAGENTA, PLUM, False, False, True),
    T_CHEST: Tile("chest", "=", GOLD, DWOOD, False, True),
    T_OCHEST: Tile("open chest", "_", WOOD, CAVEFL, False, True),
    T_TENT: Tile("tent", "A", TAN, (58, K.COLOR_YELLOW), False, False),
    T_CAGE: Tile("cage bars", "#", GRAY, CAVEFL, False, True),
    T_BONES: Tile("bones", ";", BONE, CAVEFL, True, True),
    T_WEB: Tile("cobweb", '"', LIGHT, CAVEFL, True, True),
    T_MUSH: Tile("mushrooms", ",", [PINK, MAGENTA, TAN], GRASSBG, True, True),
    T_ANVIL: Tile("anvil", "n", GRAY, FLOORBG, False, True),
    T_RAIL: Tile("rails", "=", DGRAY, CAVEFL, True, True),
    T_PALEFIRE: Tile("pale flame", "*^*'", PALE_COLS, NAVY, False, True, True),
    T_HOARD: Tile("gold hoard", "$", [GOLD, YELLOW, AMBER], CAVEFL, True, True, True),
    T_CARPET: Tile("carpet", ".", (167, K.COLOR_RED), DRED, True, True),
    T_STONEFL: Tile("flagstones", ".", GRAY, DDGRAY, True, True),
    T_SHELF: Tile("shelf", "#", WOOD, DWOOD, False, False),
    T_CAGEDOOR: Tile("cage door", "+", GRAY, CAVEFL, False, True),
    T_BUSH: Tile("bush", "%", [DGREEN, GREEN], GRASSBG, True, False),
}

# characters used in hand-drawn maps
LEGEND = {
    ',': T_GRASS, ':': T_ROAD, '#': T_WALL, '.': T_FLOOR, '+': T_DOOR, '~': T_WATER,
    '=': T_BRIDGE, '&': T_TREE, '"': T_FLOWER, 'T': T_TABLE, 'h': T_CHAIR, '_': T_COUNTER,
    'b': T_BED, 'o': T_BARREL, '*': T_FIRE, 'A': T_ALTAR, 'n': T_GRAVE, '|': T_FENCE,
    'W': T_WELL, 'X': T_EXIT, '>': T_SDOWN, '<': T_SUP, 'f': T_CROPS, '^': T_ROCK,
    'R': T_CWALL, 'r': T_CFLOOR, '$': T_ORE, 'i': T_TORCH, 'L': T_LAVA, 'O': T_PILLAR,
    'G': T_SEAL, 'C': T_CHEST, 'B': T_BONES, 'v': T_ANVIL, 'P': T_PALEFIRE, 'H': T_HOARD,
    'c': T_CARPET, 's': T_STONEFL, 'S': T_SHELF, '%': T_BUSH, 'w': T_WEB,
}

# =============================================================================
# Rules data (after SRD 5.1)
# =============================================================================
STATS = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
XP_LEVELS = [0, 0, 250, 800, 1600, 2800]   # index = level
MAX_LEVEL = 5
SLOTS = {1: {1: 2}, 2: {1: 3}, 3: {1: 4, 2: 2}, 4: {1: 4, 2: 3}, 5: {1: 4, 2: 3, 3: 2}}

RACES = {
    "human": dict(name="Human", bonus={s: 1 for s in STATS}, speed=6,
                  desc="Adaptable and ambitious. +1 to every ability."),
    "elf": dict(name="Elf", bonus={"DEX": 2, "INT": 1}, speed=6,
                desc="Graceful and keen-eyed. +2 DEX, +1 INT. Sees further in the dark, "
                     "immune to ghoul paralysis and magical sleep."),
    "dwarf": dict(name="Dwarf", bonus={"CON": 2, "STR": 2}, speed=5,
                  desc="Stout and stubborn. +2 CON, +2 STR. Resists poison. Speed 5."),
    "halfling": dict(name="Halfling", bonus={"DEX": 2, "CHA": 1}, speed=5,
                     desc="Small and lucky. +2 DEX, +1 CHA. Rerolls a natural 1. Speed 5."),
}

CLASSES = {
    "fighter": dict(name="Fighter", short="Ftr", hd=10, saves=("STR", "CON"), cast=None,
                    order=["STR", "CON", "DEX", "WIS", "CHA", "INT"],
                    weapon="longsword", armor="chain_mail", shield=True, bag=["longbow"],
                    armors={"light", "medium", "heavy"}, shields=True, weapons={"simple", "martial"},
                    desc="Master of arms and armour. Second Wind heals once per rest; criticals on "
                         "19-20 from level 3, two attacks per turn from level 5."),
    "rogue": dict(name="Rogue", short="Rog", hd=8, saves=("DEX", "INT"), cast=None,
                  order=["DEX", "CON", "WIS", "INT", "CHA", "STR"],
                  weapon="shortsword", armor="leather", shield=False, bag=["shortbow"],
                  armors={"light"}, shields=False, weapons={"simple", "longsword", "shortsword", "scimitar"},
                  desc="Quick and deadly. Sneak Attack deals extra dice when an ally flanks the "
                       "target. Finds traps, picks locks."),
    "wizard": dict(name="Wizard", short="Wiz", hd=6, saves=("INT", "WIS"), cast="INT",
                   order=["INT", "DEX", "CON", "WIS", "CHA", "STR"],
                   weapon="quarterstaff", armor="robes", shield=False, bag=["light_crossbow"],
                   armors=set(), shields=False, weapons={"dagger", "quarterstaff", "light_crossbow"},
                   desc="Scholar of the arcane. Fire Bolt, Magic Missile, Sleep, Burning Hands; "
                        "Scorching Ray at 3, Fireball at 5. Fragile."),
    "cleric": dict(name="Cleric", short="Clr", hd=8, saves=("WIS", "CHA"), cast="WIS",
                   order=["WIS", "CON", "STR", "DEX", "CHA", "INT"],
                   weapon="mace", armor="chain_mail", shield=True, bag=[],
                   armors={"light", "medium", "heavy"}, shields=True, weapons={"simple"},
                   desc="Voice of the Dawnmother. Heals, blesses and burns the undead. "
                        "Turn Undead at 2, Hold Person at 3."),
}

CLASS_SPELLS = {
    "wizard": {1: ["fire_bolt", "magic_missile", "sleep", "burning_hands"], 3: ["scorching_ray"], 5: ["fireball"]},
    "cleric": {1: ["sacred_flame", "cure_wounds", "healing_word", "bless", "guiding_bolt"],
               2: ["turn_undead"], 3: ["hold_person", "prayer_of_healing"], 5: ["mass_healing_word"]},
}

# kind: weapon / armor / shield / ring / amulet / potion / scroll / quest
ITEMS = {
    "dagger": dict(name="Dagger", kind="weapon", cat="simple", dmg="1d4", dtype="piercing", finesse=True, price=4),
    "quarterstaff": dict(name="Quarterstaff", kind="weapon", cat="simple", dmg="1d6", dtype="bludgeoning", price=2),
    "mace": dict(name="Mace", kind="weapon", cat="simple", dmg="1d6", dtype="bludgeoning", price=10),
    "spear": dict(name="Spear", kind="weapon", cat="simple", dmg="1d6", dtype="piercing", price=5),
    "shortsword": dict(name="Shortsword", kind="weapon", cat="martial", dmg="1d6", dtype="piercing", finesse=True, price=15),
    "scimitar": dict(name="Scimitar", kind="weapon", cat="martial", dmg="1d6", dtype="slashing", finesse=True, price=25),
    "longsword": dict(name="Longsword", kind="weapon", cat="martial", dmg="1d8", dtype="slashing", price=20),
    "battleaxe": dict(name="Battleaxe", kind="weapon", cat="martial", dmg="1d8", dtype="slashing", price=15),
    "warhammer": dict(name="Warhammer", kind="weapon", cat="martial", dmg="1d8", dtype="bludgeoning", price=20),
    "greatsword": dict(name="Greatsword", kind="weapon", cat="martial", dmg="2d6", dtype="slashing", twohand=True, price=60),
    "shortbow": dict(name="Shortbow", kind="weapon", cat="simple", dmg="1d6", dtype="piercing", ranged=14, twohand=True, price=25),
    "longbow": dict(name="Longbow", kind="weapon", cat="martial", dmg="1d8", dtype="piercing", ranged=20, twohand=True, price=50),
    "light_crossbow": dict(name="Light Crossbow", kind="weapon", cat="simple", dmg="1d8", dtype="piercing", ranged=14, twohand=True, price=25),
    "longsword_p1": dict(name="Longsword +1", kind="weapon", cat="martial", base="longsword", dmg="1d8", dtype="slashing", plus=1, price=400),
    "stinger": dict(name="Stinger (+1 shortsword)", kind="weapon", cat="martial", base="shortsword", dmg="1d6", dtype="piercing", finesse=True, plus=1, price=400),
    "dawnmace": dict(name="Dawnmace (+1 mace)", kind="weapon", cat="simple", base="mace", dmg="1d6", dtype="bludgeoning", plus=1,
                     extra=("1d6", "radiant"), extra_vs="undead", price=600,
                     desc="Its head is a little sun. +1d6 radiant against the undead."),
    "frostbite": dict(name="Frostbite (+1 battleaxe)", kind="weapon", cat="martial", base="battleaxe", dmg="1d8", dtype="slashing", plus=1,
                      extra=("1d6", "cold"), price=900, desc="Rime creeps along the blade. +1d6 cold damage."),
    "staff_embers": dict(name="Staff of Cinders", kind="weapon", cat="simple", base="quarterstaff", dmg="1d6", dtype="bludgeoning", plus=1,
                         spellbonus=1, price=700, desc="+1 to spell attacks and spell save DCs."),
    "robes": dict(name="Traveller's Robes", kind="armor", cat="none", ac=10, dexcap=99, price=1),
    "leather": dict(name="Leather Armour", kind="armor", cat="light", ac=11, dexcap=99, price=10),
    "studded": dict(name="Studded Leather", kind="armor", cat="light", ac=12, dexcap=99, price=45),
    "chain_shirt": dict(name="Chain Shirt", kind="armor", cat="medium", ac=13, dexcap=2, price=50),
    "scale": dict(name="Scale Mail", kind="armor", cat="medium", ac=14, dexcap=2, price=60),
    "chain_mail": dict(name="Chain Mail", kind="armor", cat="heavy", ac=16, dexcap=0, price=75),
    "splint": dict(name="Splint Mail", kind="armor", cat="heavy", ac=17, dexcap=0, price=200),
    "plate": dict(name="Plate Armour", kind="armor", cat="heavy", ac=18, dexcap=0, price=800),
    "elven_chain": dict(name="Elven Chain", kind="armor", cat="light", ac=14, dexcap=99, price=700,
                        desc="Silvery links, light as silk. Counts as light armour."),
    "shield": dict(name="Shield", kind="shield", ac=2, price=10),
    "ring_prot": dict(name="Ring of Protection", kind="ring", ac=1, saves=1, price=600, desc="+1 AC and +1 to saving throws."),
    "ward_embers": dict(name="Ward of Embers", kind="amulet", resist="fire", price=900,
                        desc="A red-gold scale on a chain. Its wearer resists fire."),
    "amulet_vigor": dict(name="Amulet of Vigor", kind="amulet", hpbonus=8, price=500, desc="+8 maximum hit points."),
    "potion": dict(name="Potion of Healing", kind="potion", heal="2d4+2", price=50),
    "potion_greater": dict(name="Potion of Greater Healing", kind="potion", heal="4d4+4", price=150),
    "scroll_fireball": dict(name="Scroll of Fireball", kind="scroll", spell="fireball", price=300, desc="Wizards only."),
    "scroll_mm": dict(name="Scroll of Magic Missile", kind="scroll", spell="magic_missile", price=80, desc="Wizards only."),
    "cage_key": dict(name="Rusty Cage Key", kind="quest", price=0),
    "goblin_map": dict(name="Goblin Scrawl", kind="quest", price=0,
                       desc="Crude charcoal on hide: a mountain, a red worm, little men with flames for heads, and "
                            "an arrow labelled SHINIES FOR MEAT."),
    "ledger": dict(name="Ledger of the Pale Flame", kind="quest", price=0,
                   desc="Columns of names - the missing miners - each marked 'fed' or 'kept'. Signed: Magister Corvane."),
    "lute": dict(name="Pell's Lute", kind="quest", price=0, desc="A battered lute with a cracked rose. Pell will want it back."),
    "hammer_greta": dict(name="Greta's Hammer", kind="quest", price=0, desc="A smith's hammer, worn smooth. Greta's mark on the handle."),
    "sunstone": dict(name="Sunstone Relic", kind="quest", price=0, desc="A warm amber stone set in silver. It belongs to the temple."),
    "locket": dict(name="Edrin's Locket", kind="quest", price=0, desc="A tin locket. Inside: a tiny painting of Sister Maren."),
}

SPELLS = {
    "fire_bolt": dict(name="Fire Bolt", lvl=0, target="enemy", range=16, kind="attack", dmg="1d10", dtype="fire",
                      desc="Ranged spell attack, 1d10 fire (2d10 at level 5)."),
    "magic_missile": dict(name="Magic Missile", lvl=1, target="enemy", range=16, kind="missile",
                          desc="Three darts that never miss, 1d4+1 force each."),
    "sleep": dict(name="Sleep", lvl=1, target="enemy", range=12, kind="sleep", radius=2,
                  desc="5d8 hit points of creatures around the target fall asleep (weakest first). Not undead."),
    "burning_hands": dict(name="Burning Hands", lvl=1, target="enemy", range=3, kind="cone", dmg="3d6", dtype="fire", save="DEX",
                          desc="A 3-tile cone of flame, 3d6 fire, DEX save for half."),
    "scorching_ray": dict(name="Scorching Ray", lvl=2, target="enemy", range=16, kind="rays", dmg="2d6", dtype="fire",
                          desc="Three rays, each a spell attack for 2d6 fire."),
    "fireball": dict(name="Fireball", lvl=3, target="enemy", range=20, kind="ball", radius=2, dmg="8d6", dtype="fire", save="DEX",
                     desc="Explodes in a radius of 2 tiles: 8d6 fire, DEX save for half. Burns friends too!"),
    "sacred_flame": dict(name="Sacred Flame", lvl=0, target="enemy", range=12, kind="save", dmg="1d8", dtype="radiant", save="DEX",
                         desc="Radiant flame, 1d8, DEX save negates (2d8 at level 5)."),
    "guiding_bolt": dict(name="Guiding Bolt", lvl=1, target="enemy", range=16, kind="attack", dmg="4d6", dtype="radiant",
                         desc="Ranged spell attack, 4d6 radiant."),
    "cure_wounds": dict(name="Cure Wounds", lvl=1, target="ally", range=1, kind="heal", heal="1d8",
                        desc="Touch: heals 1d8 + WIS."),
    "healing_word": dict(name="Healing Word", lvl=1, target="ally", range=12, kind="heal", heal="1d4",
                         desc="At range: heals 1d4 + WIS."),
    "bless": dict(name="Bless", lvl=1, target="self", range=6, kind="bless",
                  desc="Up to three allies add 1d4 to attacks and saves for 10 rounds."),
    "turn_undead": dict(name="Turn Undead", lvl=-1, target="self", range=6, kind="turn",
                        desc="Undead within 6 tiles must make a WIS save or flee. Once per rest."),
    "hold_person": dict(name="Hold Person", lvl=2, target="enemy", range=12, kind="hold", save="WIS",
                        desc="A humanoid is paralysed (WIS save, repeated each turn)."),
    "prayer_of_healing": dict(name="Prayer of Healing", lvl=2, target="self", range=6, kind="massheal", heal="2d8",
                              desc="Every ally within 6 tiles heals 2d8 + WIS."),
    "mass_healing_word": dict(name="Mass Healing Word", lvl=3, target="self", range=12, kind="massheal", heal="1d4",
                              desc="Every ally within 12 tiles heals 1d4 + WIS."),
    # monster-only
    "pale_flame": dict(name="Pale Flame", lvl=0, target="enemy", range=12, kind="save", dmg="2d8", dtype="fire", save="DEX",
                       desc="Cold white fire."),
    "inflict": dict(name="Inflict Wounds", lvl=1, target="enemy", range=1, kind="attack", dmg="3d10", dtype="necrotic"),
}

# Monster templates. attacks: (name, to-hit, damage, type, range, rider)
MONSTERS = {
    "rat": dict(name="Giant Rat", ch="r", fg=TAN, hp="2d6", ac=12, speed=6, xp=25,
                stats=(7, 15, 11, 2, 10, 4), attacks=[("bite", 4, "1d4+2", "piercing", 1, None)],
                tags={"beast"}, pack=True, gold=0),
    "wolf": dict(name="Wolf", ch="w", fg=GRAY, hp="2d8+2", ac=13, speed=8, xp=50,
                 stats=(12, 15, 12, 3, 12, 6), attacks=[("bite", 4, "2d4+2", "piercing", 1, None)],
                 tags={"beast"}, pack=True, gold=0),
    "goblin": dict(name="Goblin", ch="g", fg=LGREEN, hp="2d6", ac=15, speed=6, xp=50,
                   stats=(8, 14, 10, 10, 8, 8), attacks=[("scimitar", 4, "1d6+2", "slashing", 1, None)],
                   tags={"humanoid"}, gold="1d6", loot=[("potion", 8)]),
    "goblin_archer": dict(name="Goblin Archer", ch="g", fg=GREEN, hp="2d6", ac=13, speed=6, xp=50,
                          stats=(8, 14, 10, 10, 8, 8),
                          attacks=[("shortbow", 3, "1d6+1", "piercing", 14, None), ("dagger", 4, "1d4+2", "piercing", 1, None)],
                          tags={"humanoid"}, gold="1d6", ranged=True),
    "snagtooth": dict(name="Snagtooth", ch="G", fg=YELLOW, hp="5d6", ac=16, speed=6, xp=200,
                      stats=(10, 14, 10, 10, 8, 10), attacks=[("scimitar", 4, "1d6+2", "slashing", 1, None)],
                      multi=2, tags={"humanoid"}, gold="3d10", loot=[("cage_key", 100), ("goblin_map", 100), ("potion", 50)],
                      npc="snagtooth", boss=True),
    "bandit": dict(name="Bandit", ch="b", fg=TAN, hp="2d8+2", ac=12, speed=6, xp=25,
                   stats=(11, 12, 12, 10, 10, 10), attacks=[("scimitar", 3, "1d6+1", "slashing", 1, None)],
                   tags={"humanoid"}, gold="2d6", loot=[("potion", 10)]),
    "kobold": dict(name="Kobold", ch="k", fg=ORANGE, hp="2d6-1", ac=12, speed=6, xp=25,
                   stats=(7, 15, 9, 8, 7, 8), attacks=[("dagger", 4, "1d4+2", "piercing", 1, None)],
                   tags={"humanoid"}, pack=True, gold="1d4"),
    "kobold_slinger": dict(name="Kobold Slinger", ch="k", fg=AMBER, hp="2d6-1", ac=12, speed=6, xp=25,
                           stats=(7, 15, 9, 8, 7, 8),
                           attacks=[("sling", 4, "1d4+2", "bludgeoning", 10, None), ("dagger", 4, "1d4+2", "piercing", 1, None)],
                           tags={"humanoid"}, pack=True, gold="1d4", ranged=True),
    "cultist": dict(name="Cultist", ch="c", fg=PALE, hp="2d8", ac=12, speed=6, xp=25,
                    stats=(11, 12, 10, 10, 11, 10), attacks=[("scimitar", 3, "1d6+1", "slashing", 1, None)],
                    tags={"humanoid"}, gold="2d6", loot=[("potion", 10)]),
    "fanatic": dict(name="Cult Fanatic", ch="C", fg=ICE, hp="6d8+6", ac=13, speed=6, xp=450,
                    stats=(11, 14, 12, 10, 13, 14), attacks=[("dagger", 4, "1d4+2", "piercing", 1, None)], multi=2,
                    spells={"pale_flame": 0, "hold_person": 2, "inflict": 3}, spell_dc=11, spell_atk=3,
                    tags={"humanoid"}, gold="3d10", loot=[("potion", 40)]),
    "spider": dict(name="Giant Spider", ch="S", fg=PURPLE, hp="4d10+4", ac=14, speed=6, xp=200,
                   stats=(14, 16, 12, 2, 11, 4), attacks=[("bite", 4, "1d8+3", "piercing", 1, ("poison", "1d8", "CON", 11))],
                   tags={"beast"}, gold=0),
    "ogre": dict(name="Grukk the Ogre", ch="O", fg=TAN, hp="5d10+15", ac=11, speed=6, xp=450,
                 stats=(19, 8, 16, 5, 7, 7), attacks=[("greatclub", 5, "2d6+3", "bludgeoning", 1, None)],
                 tags={"giant"}, gold="4d10", loot=[("amulet_vigor", 100)], boss=True),
    "skeleton": dict(name="Skeleton", ch="s", fg=BONE, hp="2d8+4", ac=13, speed=6, xp=50,
                     stats=(10, 14, 15, 6, 8, 5), attacks=[("shortsword", 4, "1d6+2", "piercing", 1, None)],
                     tags={"undead"}, vuln={"bludgeoning"}, immune={"poison"}, gold=0),
    "skeleton_archer": dict(name="Skeleton Archer", ch="s", fg=STONE, hp="2d8+4", ac=13, speed=6, xp=50,
                            stats=(10, 14, 15, 6, 8, 5),
                            attacks=[("shortbow", 4, "1d6+2", "piercing", 14, None), ("claw", 4, "1d4+2", "slashing", 1, None)],
                            tags={"undead"}, vuln={"bludgeoning"}, immune={"poison"}, gold=0, ranged=True),
    "zombie": dict(name="Zombie Miner", ch="z", fg=MOSS, hp="3d8+9", ac=8, speed=4, xp=50,
                   stats=(13, 6, 16, 3, 6, 5), attacks=[("slam", 3, "1d6+1", "bludgeoning", 1, None)],
                   tags={"undead"}, immune={"poison"}, fortitude=True, gold="1d4"),
    "ghoul": dict(name="Ghoul", ch="u", fg=(150, K.COLOR_GREEN), hp="5d8", ac=12, speed=6, xp=200,
                  stats=(13, 15, 10, 7, 10, 6), attacks=[("claws", 4, "2d4+2", "slashing", 1, ("paralyze", "CON", 10))],
                  tags={"undead"}, immune={"poison"}, gold="2d6"),
    "corvane": dict(name="Magister Corvane", ch="M", fg=WHITE, hp="10d8+10", ac=15, speed=6, xp=1100,
                    stats=(9, 14, 12, 18, 12, 14), attacks=[("dagger", 5, "1d4+2", "piercing", 1, None)],
                    spells={"fire_bolt": 0, "magic_missile": 3, "burning_hands": 2, "hold_person": 2, "scorching_ray": 2},
                    spell_dc=14, spell_atk=6, cantrip_dice=2,
                    tags={"humanoid"}, gold="10d10", loot=[("staff_embers", 100), ("potion_greater", 100)],
                    npc="corvane", boss=True, ranged=True),
    "ashmaw": dict(name="Ashmaw", ch="D", fg=RED, hp="14d10+28", ac=17, speed=6, xp=3900,
                   stats=(21, 10, 19, 14, 11, 19),
                   attacks=[("bite", 7, "2d10+4", "piercing", 1, ("fire", "1d6")),
                            ("claw", 6, "1d8+4", "slashing", 1, None), ("claw", 6, "1d8+4", "slashing", 1, None)],
                   multi=3, breath=("6d6", "fire", "DEX", 14), immune={"fire"},
                   tags={"dragon"}, gold=0, npc="ashmaw", boss=True, big=True),
}

PORTRAIT_FG = {"fighter": STONE, "rogue": GREEN, "wizard": BLUE, "cleric": GOLD}
PARTY_COLS = [(231, K.COLOR_WHITE), (81, K.COLOR_CYAN), (213, K.COLOR_MAGENTA), (227, K.COLOR_YELLOW), (120, K.COLOR_GREEN)]


# =============================================================================
# Actors: party members, monsters and townsfolk
# =============================================================================
class Actor:
    SAVE_FIELDS = ("name", "ch", "faction", "x", "y", "is_pc", "race", "cls", "level", "xp",
                   "stats", "max_hp", "hp", "equip", "slots", "spells", "status", "dsaves", "dead",
                   "ai", "tmpl", "npc", "portrait", "uses", "recharge", "mslots", "home", "cid",
                   "engaged", "alerted", "pcol", "bio")

    def __init__(self):
        self.name, self.ch, self.fg, self.faction = "?", "@", WHITE, "neutral"
        self.x = self.y = 0
        self.is_pc, self.race, self.cls, self.level, self.xp = False, None, None, 1, 0
        self.stats = {s: 10 for s in STATS}
        self.max_hp = self.hp = 1
        self.equip = {"weapon": None, "armor": None, "shield": None, "ring": None, "amulet": None}
        self.slots, self.spells, self.status = {}, [], {}
        self.dsaves, self.dead, self.ai = [0, 0], False, False
        self.tmpl = self.npc = self.portrait = None
        self.uses, self.recharge, self.mslots = {}, True, {}
        self.home, self.cid, self.engaged, self.alerted = None, None, False, False
        self.pcol, self.bio = 0, ""
        self.mp, self.acted = 0, False

    # --- derived values -----------------------------------------------------
    @property
    def T(self):
        return MONSTERS[self.tmpl] if self.tmpl else None

    @property
    def conscious(self):
        return not self.dead and self.hp > 0

    @property
    def downed(self):
        return self.is_pc and not self.dead and self.hp <= 0

    @property
    def prof(self):
        return 2 + (self.level - 1) // 4

    def m(self, stat):
        return mod(self.stats[stat])

    @property
    def speed(self):
        if self.tmpl:
            return self.T["speed"]
        return RACES[self.race]["speed"] if self.race else 6

    def item(self, slot):
        k = self.equip.get(slot)
        return ITEMS[k] if k else None

    @property
    def weapon(self):
        return self.item("weapon") or dict(name="Fists", kind="weapon", cat="simple", dmg="1d2", dtype="bludgeoning")

    @property
    def ac(self):
        if self.tmpl:
            return self.T["ac"]
        arm = self.item("armor") or ITEMS["robes"]
        ac = arm["ac"] + min(self.m("DEX"), arm["dexcap"])
        w = self.weapon
        if self.equip.get("shield") and not w.get("twohand"):
            ac += 2
        r = self.item("ring")
        if r:
            ac += r.get("ac", 0)
        return ac

    def proficient(self, w):
        if self.tmpl:
            return True
        allowed = CLASSES[self.cls]["weapons"]
        base = w.get("base") or next((k for k, v in ITEMS.items() if v is w), None)
        return w.get("cat") in allowed or (base in allowed)

    def attack_bonus(self, w=None):
        w = w or self.weapon
        if w.get("ranged"):
            ab = self.m("DEX")
        elif w.get("finesse"):
            ab = max(self.m("STR"), self.m("DEX"))
        else:
            ab = self.m("STR")
        return ab + (self.prof if self.proficient(w) else 0) + w.get("plus", 0)

    def damage_bonus(self, w=None):
        w = w or self.weapon
        if w.get("ranged"):
            ab = self.m("DEX")
        elif w.get("finesse"):
            ab = max(self.m("STR"), self.m("DEX"))
        else:
            ab = self.m("STR")
        return ab + w.get("plus", 0)

    @property
    def cast_stat(self):
        return CLASSES[self.cls]["cast"] if self.cls else None

    @property
    def spell_dc(self):
        if self.tmpl:
            return self.T.get("spell_dc", 10)
        st = self.weapon.get("spellbonus", 0)
        return 8 + self.prof + self.m(self.cast_stat) + st

    @property
    def spell_atk(self):
        if self.tmpl:
            return self.T.get("spell_atk", 2)
        return self.prof + self.m(self.cast_stat) + self.weapon.get("spellbonus", 0)

    def save_bonus(self, stat):
        b = self.m(stat)
        if self.cls and stat in CLASSES[self.cls]["saves"]:
            b += self.prof
        r = self.item("ring")
        if r:
            b += r.get("saves", 0)
        return b

    def resists(self, dtype):
        if self.tmpl:
            return False
        a = self.item("amulet")
        if a and a.get("resist") == dtype:
            return True
        return dtype == "poison" and self.race == "dwarf"

    def immune(self, dtype):
        return bool(self.tmpl) and dtype in self.T.get("immune", ())

    def vulnerable(self, dtype):
        return bool(self.tmpl) and dtype in self.T.get("vuln", ())

    def has_tag(self, tag):
        return bool(self.tmpl) and tag in self.T.get("tags", ())

    @property
    def sneak_dice(self):
        return 0 if self.cls != "rogue" else (1 + (self.level - 1) // 2)

    @property
    def crit_range(self):
        return 19 if (self.cls == "fighter" and self.level >= 3) else 20

    @property
    def attacks_per_turn(self):
        if self.tmpl:
            return self.T.get("multi", 1)
        return 2 if (self.cls == "fighter" and self.level >= 5) else 1

    @property
    def is_ranged(self):
        if self.tmpl:
            return self.T.get("ranged", False)
        return bool(self.weapon.get("ranged"))

    @property
    def can_cast(self):
        return self.cls in ("wizard", "cleric")

    def known_spells(self):
        if not self.cls or self.cls not in CLASS_SPELLS:
            return []
        out = []
        for lv, sp in sorted(CLASS_SPELLS[self.cls].items()):
            if self.level >= lv:
                out.extend(sp)
        return out

    def max_hp_for_level(self):
        hd = CLASSES[self.cls]["hd"]
        con = self.m("CON")
        hp = hd + con + (self.level - 1) * (hd // 2 + 1 + con)
        a = self.item("amulet")
        if a:
            hp += a.get("hpbonus", 0)
        if self.race == "dwarf":
            hp += self.level
        return max(1, hp)

    def recompute(self, heal=False):
        old = self.max_hp
        self.max_hp = self.max_hp_for_level()
        if heal:
            self.hp = self.max_hp
        else:
            self.hp = clamp(self.hp + max(0, self.max_hp - old), 0, self.max_hp)
        sl = SLOTS.get(self.level, {}) if self.can_cast else {}
        for lv, n in sl.items():
            cur = self.slots.get(str(lv), [n, n])
            self.slots[str(lv)] = [min(n, cur[0] + max(0, n - cur[1])) if not heal else n, n]
        self.spells = self.known_spells()

    def rest(self):
        self.recompute(heal=True)
        self.uses = {}
        self.status = {}
        self.dsaves = [0, 0]
        self.recharge = True
        if self.tmpl:
            self.mslots = dict(self.T.get("spells", {}))

    def slot_ok(self, lvl):
        if lvl <= 0:
            return True
        return self.slots.get(str(lvl), [0, 0])[0] > 0

    def use_slot(self, lvl):
        if lvl > 0:
            self.slots[str(lvl)][0] -= 1

    def to_dict(self):
        return {k: getattr(self, k) for k in self.SAVE_FIELDS}

    @classmethod
    def from_dict(cls, d):
        a = cls()
        for k in cls.SAVE_FIELDS:
            if k in d:
                setattr(a, k, d[k])
        a.fg = PARTY_COLS[a.pcol % len(PARTY_COLS)] if a.is_pc else (a.T["fg"] if a.tmpl else NPC_FG.get(a.npc, SKIN))
        if a.home:
            a.home = tuple(a.home)
        return a


NPC_FG = {"hobb": AMBER, "pell": PINK, "aldous": GOLD, "greta": ORANGE, "oswin": (141, K.COLOR_MAGENTA),
          "captain": (75, K.COLOR_CYAN), "brannoc": (81, K.COLOR_CYAN), "tamsin": (213, K.COLOR_MAGENTA),
          "maren": (227, K.COLOR_YELLOW), "lysa": (120, K.COLOR_GREEN), "edrin": GRAY, "villager": SKIN}


def make_monster(key, x, y):
    t = MONSTERS[key]
    a = Actor()
    a.tmpl, a.name, a.ch, a.fg, a.faction = key, t["name"], t["ch"], t["fg"], "hostile"
    a.x, a.y = x, y
    st = t["stats"]
    a.stats = dict(zip(STATS, st))
    a.max_hp = a.hp = max(1, roll(t["hp"]))
    a.mslots = dict(t.get("spells", {}))
    a.npc = t.get("npc")
    a.home = (x, y)
    a.level = 3
    return a


def make_npc(npc, name, x, y, portrait=None):
    a = Actor()
    a.npc, a.name, a.ch, a.fg, a.faction = npc, name, "@", NPC_FG.get(npc, SKIN), "neutral"
    a.x, a.y, a.home, a.portrait = x, y, (x, y), portrait or npc
    a.max_hp = a.hp = 10
    return a


def make_pc(name, race, cls, base, level=1, pcol=0, portrait=None, cid=None, equip=None, bio=""):
    a = Actor()
    a.is_pc, a.name, a.race, a.cls, a.faction = True, name, race, cls, "party"
    a.ch, a.pcol = "@", pcol
    a.fg = PARTY_COLS[pcol % len(PARTY_COLS)]
    a.stats = {s: base[s] + RACES[race]["bonus"].get(s, 0) for s in STATS}
    c = CLASSES[cls]
    a.equip = {"weapon": c["weapon"], "armor": c["armor"], "shield": "shield" if c["shield"] else None,
               "ring": None, "amulet": None}
    if equip:
        a.equip.update(equip)
    a.level = level
    a.xp = XP_LEVELS[level]
    a.portrait = portrait or cls
    a.cid, a.bio = cid, bio
    a.recompute(heal=True)
    return a


def roll_stats():
    return [sum(sorted(random.randint(1, 6) for _ in range(4))[1:]) for _ in range(6)]


def assign_stats(values, cls):
    vals = sorted(values, reverse=True)
    return {s: vals[i] for i, s in enumerate(CLASSES[cls]["order"])}


COMPANIONS = {
    "brannoc": dict(name="Brannoc Ironvein", race="dwarf", cls="fighter",
                    base=dict(STR=15, DEX=10, CON=14, INT=9, WIS=12, CHA=8),
                    equip={"weapon": "battleaxe"}, bio="A gruff ex-miner of Deepdelve. Lost his crew to the dark."),
    "tamsin": dict(name="Tamsin Vale", race="elf", cls="wizard",
                   base=dict(STR=8, DEX=14, CON=13, INT=15, WIS=10, CHA=12),
                   equip={}, bio="An elven scholar of dragon lore with a tongue sharper than her knife."),
    "maren": dict(name="Sister Maren", race="human", cls="cleric",
                  base=dict(STR=13, DEX=10, CON=13, INT=10, WIS=15, CHA=12),
                  equip={}, bio="A priestess of the Dawnmother. Her brother Edrin works the mine."),
    "lysa": dict(name="Lysa Thistlefoot", race="halfling", cls="rogue",
                 base=dict(STR=8, DEX=15, CON=13, INT=12, WIS=10, CHA=13),
                 equip={}, bio="A halfling 'retrieval specialist'. Owes money to half of Emberfall."),
}


def make_companion(cid, level, pcol):
    c = COMPANIONS[cid]
    a = make_pc(c["name"], c["race"], c["cls"], c["base"], level=1, pcol=pcol, portrait=cid,
                cid=cid, equip=c["equip"], bio=c["bio"])
    while a.level < level:
        a.level += 1
        a.recompute(heal=True)
    a.xp = XP_LEVELS[a.level]
    return a


# =============================================================================
# Areas
# =============================================================================
class Area:
    def __init__(self, aid, name, w, h, kind="dungeon", fill=T_CWALL, light=8):
        self.id, self.name, self.w, self.h, self.kind, self.light = aid, name, w, h, kind, light
        self.tiles = [[fill] * w for _ in range(h)]
        self.explored = [[False] * w for _ in range(h)]
        self.actors = []
        self.items = {}      # (x, y) -> [item ids, "gold:N"]
        self.decals = {}     # (x, y) -> (ch, colour index into DECAL_COLS)
        self.links = {}      # (x, y) -> [area id, entry name]
        self.entries = {}    # name -> (x, y)
        self.chests = {}     # (x, y) -> {"items": [...], "locked": dc}
        self.traps = {}      # (x, y) -> {"hidden": bool, "dmg": "2d6"}
        self.notes = {}      # (x, y) -> text shown when stepping there
        self.scene = None

    def inb(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h

    def tile(self, x, y):
        return self.tiles[y][x] if self.inb(x, y) else T_ROCK

    def walkable(self, x, y):
        return self.inb(x, y) and TILES[self.tiles[y][x]].walk

    def seethru(self, x, y):
        return self.inb(x, y) and TILES[self.tiles[y][x]].seethru

    def set(self, x, y, t):
        if self.inb(x, y):
            self.tiles[y][x] = t

    def add_item(self, x, y, it):
        self.items.setdefault((x, y), []).append(it)

    def actor_at(self, x, y):
        for a in self.actors:
            if a.x == x and a.y == y and (a.conscious or a.downed):
                return a
        return None

    def to_dict(self):
        k = lambda p: "%d,%d" % p
        return dict(id=self.id, name=self.name, w=self.w, h=self.h, kind=self.kind, light=self.light,
                    tiles=["".join(chr(48 + t) for t in row) for row in self.tiles],
                    explored=["".join("1" if e else "0" for e in row) for row in self.explored],
                    actors=[a.to_dict() for a in self.actors if not a.dead],
                    items={k(p): v for p, v in self.items.items() if v},
                    decals={k(p): v for p, v in self.decals.items()},
                    links={k(p): v for p, v in self.links.items()},
                    entries=self.entries, chests={k(p): v for p, v in self.chests.items()},
                    traps={k(p): v for p, v in self.traps.items()},
                    notes={k(p): v for p, v in self.notes.items()}, scene=self.scene)

    @classmethod
    def from_dict(cls, d):
        a = cls(d["id"], d["name"], d["w"], d["h"], d["kind"], light=d["light"])
        a.tiles = [[ord(c) - 48 for c in row] for row in d["tiles"]]
        a.explored = [[c == "1" for c in row] for row in d["explored"]]
        a.actors = [Actor.from_dict(x) for x in d["actors"]]
        p = lambda s: tuple(int(v) for v in s.split(","))
        a.items = {p(s): v for s, v in d["items"].items()}
        a.decals = {p(s): tuple(v) for s, v in d["decals"].items()}
        a.links = {p(s): v for s, v in d["links"].items()}
        a.entries = {n: tuple(v) for n, v in d["entries"].items()}
        a.chests = {p(s): v for s, v in d["chests"].items()}
        a.traps = {p(s): v for s, v in d["traps"].items()}
        a.notes = {p(s): v for s, v in d["notes"].items()}
        a.scene = d.get("scene")
        return a


DECAL_COLS = [BLOODC, DRED, BONE, GRAY, (58, K.COLOR_YELLOW), PALE]

# --- field of view: recursive shadowcasting ---------------------------------
_OCT = [(1, 0, 0, 1), (0, 1, 1, 0), (0, -1, 1, 0), (-1, 0, 0, 1),
        (-1, 0, 0, -1), (0, -1, -1, 0), (0, 1, -1, 0), (1, 0, 0, -1)]


def fov(area, ox, oy, radius):
    vis = {(ox, oy)}
    for xx, xy, yx, yy in _OCT:
        _cast(area, ox, oy, 1, 1.0, 0.0, radius, xx, xy, yx, yy, vis)
    return vis


def _cast(area, cx, cy, row, start, end, radius, xx, xy, yx, yy, vis):
    if start < end:
        return
    r2 = radius * radius
    new_start = start
    for j in range(row, radius + 1):
        dx, dy = -j - 1, -j
        blocked = False
        while dx <= 0:
            dx += 1
            X, Y = cx + dx * xx + dy * xy, cy + dx * yx + dy * yy
            l_slope, r_slope = (dx - 0.5) / (dy + 0.5), (dx + 0.5) / (dy - 0.5)
            if start < r_slope:
                continue
            if end > l_slope:
                break
            if dx * dx + dy * dy <= r2 and area.inb(X, Y):
                vis.add((X, Y))
            opaque = not area.seethru(X, Y)
            if blocked:
                if opaque:
                    new_start = r_slope
                    continue
                blocked = False
                start = new_start
            elif opaque and j < radius:
                blocked = True
                _cast(area, cx, cy, j + 1, start, l_slope, radius, xx, xy, yx, yy, vis)
                new_start = r_slope
        if blocked:
            break


def los(area, x0, y0, x1, y1):
    for (x, y) in line(x0, y0, x1, y1)[1:-1]:
        if not area.seethru(x, y):
            return False
    return True


def bfs_dist(area, sources, blocked=frozenset(), limit=9999, doors=False):
    """Distance map from sources over walkable tiles (8-way)."""
    dist = {}
    q = deque()
    for s in sources:
        dist[s] = 0
        q.append(s)
    while q:
        x, y = q.popleft()
        d = dist[(x, y)]
        if d >= limit:
            continue
        for dx, dy in DIRS8:
            n = (x + dx, y + dy)
            if n in dist or n in blocked:
                continue
            if not area.walkable(*n) and not (doors and area.tile(*n) in (T_DOOR, T_SEAL)):
                continue
            dist[n] = d + 1
            q.append(n)
    return dist


# =============================================================================
# Map building
# =============================================================================
def stamp(grid, rows, x0, y0):
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch != ' ' and 0 <= y0 + j < len(grid) and 0 <= x0 + i < len(grid[0]):
                grid[y0 + j][x0 + i] = ch


def area_from_grid(aid, name, kind, grid, light, spawns, under, legend_over=None):
    h, w = len(grid), max(len(r) for r in grid)
    A = Area(aid, name, w, h, kind, light=light)
    lg = dict(LEGEND)
    if legend_over:
        lg.update(legend_over)
    marks = {}
    for y in range(h):
        row = grid[y]
        for x in range(w):
            ch = row[x] if x < len(row) else row[-1]
            if ch in spawns:
                marks.setdefault(ch, []).append((x, y))
                ch = under.get(ch, '.')
            A.tiles[y][x] = lg.get(ch, T_CWALL)
    for ch, pts in marks.items():
        for (x, y) in pts:
            a = spawns[ch](x, y)
            if a:
                A.actors.append(a)
    return A, marks


TAVERN = [
    "############################",
    "#oo_____......***....#b...b#",
    "#o.1...........*.....#.....#",
    "#____................+.....#",
    "#.......hTh....hTh...#b...b#",
    "#..2....hTh....hTh...#######",
    "#..............4.....#..o.>#",
    "#.hTh....hTh.........+...oo#",
    "#.hTh....hTh....hTh..#######",
    "#................hTh.....3.#",
    "#############+##############",
]
TEMPLE = [
    "########################",
    "#ssssssssssAAs6ssssssss#",
    "#sssss*ssssAAssss*sssss#",
    "#ssssssssss5sssssssssss#",
    "#sshhhhhhsssssshhhhhhss#",
    "#sshhhhhhsssssshhhhhhss#",
    "#sshhhhhhsssssshhhhhhss#",
    "#ssssssssssssssssssssss#",
    "#ssssssssssssssssssssss#",
    "###########++###########",
]
SMITHY = [
    "##########+###########",
    "#....................#",
    "#.o..............o...#",
    "#____________________#",
    "#o.....7.......v...oo#",
    "#***.............oooo#",
    "######################",
]
HALL = [
    "##########++##########",
    "#.........cc.........#",
    "#.o.......cc.......o.#",
    "#......TTTTTTTT......#",
    "#......h..8...h......#",
    "#o..................o#",
    "######################",
]
HOUSE = [
    "#####+#####",
    "#b...#...b#",
    "#....+....#",
    "#.T.h#h.T.#",
    "#####+#####",
]
CELLAR = [
    "##########################",
    "#oo..r..#.......oo#ooo..o#",
    "#o......+.....r...+......#",
    "#.....r.#..oo.....#..r...#",
    "####+####.........##+#####",
    "#.......#....r....#.....<#",
    "#..r....+.........+......#",
    "#oo...oo#oo....ooo#oo....#",
    "##########################",
]


def gen_town():
    rnd = random.Random(1187)
    W, H = 80, 32
    g = [[','] * W for _ in range(H)]
    for x in range(W):
        g[0][x] = g[H - 1][x] = '&'
        if rnd.random() < 0.6:
            g[1][x] = '&'
        if rnd.random() < 0.5:
            g[H - 2][x] = '&'
    for y in range(H):
        g[y][0] = g[y][W - 1] = '&'
        if rnd.random() < 0.5:
            g[y][1] = '&'
        if rnd.random() < 0.5:
            g[y][W - 2] = '&'
    for y in range(H):  # the river Emberrun
        rx = 47 + int(round(1.4 * math.sin(y / 4.0)))
        g[y][rx] = g[y][rx + 1] = '~'
    for y in range(13, 21):
        for x in range(30, 43):
            g[y][x] = ':'
    for x in range(W):
        for y in (16, 17):
            g[y][x] = '=' if g[y][x] == '~' else ':'
    g[16][0] = g[17][0] = g[16][W - 1] = g[17][W - 1] = 'X'
    g[15][36] = 'W'
    stamp(g, TAVERN, 2, 2)
    for y in range(13, 16):
        g[y][15] = ':'
    stamp(g, TEMPLE, 54, 2)
    for y in range(12, 16):
        g[y][65] = g[y][66] = ':'
    for gx, gy in [(56, 13), (59, 13), (62, 13), (70, 13), (73, 13), (57, 14), (60, 14), (71, 14), (74, 14)]:
        g[gy][gx] = 'n'
    stamp(g, SMITHY, 4, 19)
    g[18][14] = ':'
    stamp(g, HALL, 55, 19)
    g[18][65] = g[18][66] = ':'
    stamp(g, HOUSE, 32, 3)
    for y in range(8, 13):
        g[y][37] = ':'
    stamp(g, HOUSE, 30, 21)
    g[20][35] = ':'
    for y in range(26, 29):
        for x in range(30, 45):
            g[y][x] = 'f'
    for y in range(26, 29):
        g[y][29] = g[y][45] = '|'
    # scatter trees and flowers on open grass away from everything else
    for y in range(2, H - 2):
        for x in range(2, W - 2):
            if g[y][x] != ',':
                continue
            near = any(g[y + dy][x + dx] not in ',&"' for dx in (-1, 0, 1) for dy in (-1, 0, 1))
            if near:
                continue
            r = rnd.random()
            if r < 0.06:
                g[y][x] = '&'
            elif r < 0.10:
                g[y][x] = '"'
            elif r < 0.12:
                g[y][x] = '%'
    g[15][77] = '9'
    names = {'1': ("hobb", "Hobb the Innkeeper"), '2': ("brannoc", "Brannoc Ironvein"), '3': ("tamsin", "Tamsin Vale"),
             '4': ("pell", "Pell the Bard"), '5': ("maren", "Sister Maren"), '6': ("aldous", "Father Aldous"),
             '7': ("greta", "Greta Hammersong"), '8': ("oswin", "Mayor Oswin Thale"), '9': ("captain", "Captain Rook")}
    spawns = {k: (lambda x, y, v=v: make_npc(v[0], v[1], x, y)) for k, v in names.items()}
    under = {k: '.' for k in names}
    under.update({'5': 's', '6': 's', '9': ','})
    A, marks = area_from_grid("town", "Emberfall", "town", g, 30, spawns, under)
    A.entries = {"west": (2, 16), "east": (W - 3, 16), "cellar": (27, 8)}
    A.links[(28, 8)] = ["cellar", "up"]
    A.scene = "town"
    # a few villagers going about their day
    for (vx, vy, nm) in [(34, 18, "Old Wenna"), (40, 14, "Farmer Dobbs"), (20, 17, "Little Pip")]:
        v = make_npc("villager", nm, vx, vy, portrait="villager")
        A.actors.append(v)
    return A


def gen_cellar():
    spawns = {'r': lambda x, y: make_monster("rat", x, y)}
    A, _ = area_from_grid("cellar", "Cellar of the Rusty Lantern", "dungeon", [list(r) for r in CELLAR], 7,
                          spawns, {'r': '.'}, legend_over={'.': T_STONEFL})
    A.entries = {"up": (23, 5)}
    A.links[(24, 5)] = ["town", "cellar"]
    A.add_item(2, 6, "potion")
    A.add_item(10, 7, "gold:12")
    A.scene = "cellar"
    return A


def _smooth(grid, w, h, wall, floor, n=4):
    for _ in range(n):
        new = [row[:] for row in grid]
        for y in range(1, h - 1):
            for x in range(1, w - 1):
                c = sum(1 for dx in (-1, 0, 1) for dy in (-1, 0, 1) if grid[y + dy][x + dx] == wall)
                new[y][x] = wall if c >= 5 else floor
        grid[:] = new


def _carve_path(grid, rnd, x0, y0, x1, y1, ch, keep=(), width=1):
    x, y = x0, y0
    pts = []
    while (x, y) != (x1, y1):
        pts.append((x, y))
        if rnd.random() < 0.65:
            x += (x1 > x) - (x1 < x)
        if rnd.random() < 0.5:
            y += (y1 > y) - (y1 < y)
        elif rnd.random() < 0.3:
            y += rnd.choice((-1, 1))
            y = clamp(y, 2, len(grid) - 3)
    pts.append((x1, y1))
    for (px, py) in pts:
        for dx in range(-width, width + 1):
            for dy in range(-width, width + 1):
                X, Y = px + dx, py + dy
                if 0 < Y < len(grid) - 1 and 0 < X < len(grid[0]) - 1 and grid[Y][X] not in keep:
                    grid[Y][X] = ','
        grid[py][px] = ch
    return pts


def _flood_fix(A, start, wall):
    reach = bfs_dist(A, [start])
    for y in range(A.h):
        for x in range(A.w):
            if A.tiles[y][x] in (T_GRASS, T_FLOWER, T_MUSH, T_CFLOOR, T_BONES, T_WEB, T_ROAD, T_BUSH) and (x, y) not in reach:
                A.tiles[y][x] = wall


def gen_forest(seed):
    rnd = random.Random(seed)
    W, H = 96, 40
    g = [['&' if rnd.random() < 0.46 else ','
          for x in range(W)] for y in range(H)]
    for x in range(W):
        g[0][x] = g[H - 1][x] = '&'
    for y in range(H):
        g[y][0] = g[y][W - 1] = '&'
    _smooth(g, W, H, '&', ',', 4)
    y0, y1 = rnd.randint(14, 26), rnd.randint(14, 26)
    _carve_path(g, rnd, 1, y0, W - 2, y1, ':')
    # goblin camp
    cx, cy = rnd.randint(56, 70), rnd.choice((8, 31))
    for y in range(cy - 6, cy + 7):
        for x in range(cx - 9, cx + 10):
            if 0 < y < H - 1 and ((x - cx) / 9.0) ** 2 + ((y - cy) / 6.0) ** 2 <= 1.0:
                g[y][x] = ','
    _carve_path(g, rnd, cx, cy + (4 if cy < H // 2 else -4), cx - 8, (y0 + y1) // 2, ':')
    g[cy][cx] = '*'
    tents = [(cx - 6, cy - 2), (cx + 6, cy - 2), (cx - 5, cy + 3), (cx + 6, cy + 3), (cx, cy - 4)]
    for tx, ty in tents:
        g[ty][tx] = 'A'
    # the cage: bars around (lx, ly), door facing the fire
    lx, ly = cx + 3, cy + (-3 if cy > H // 2 else 3)
    lx = cx - 3
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            g[ly + dy][lx + dx] = 'K'
    g[ly][lx] = ','
    door = (lx + 1, ly)
    g[door[1]][door[0]] = 'Q'
    for y in range(1, H - 1):
        for x in range(1, W - 1):
            if g[y][x] == ',':
                r = rnd.random()
                if r < 0.04:
                    g[y][x] = '"'
                elif r < 0.06:
                    g[y][x] = 'm'
                elif r < 0.08:
                    g[y][x] = '%'
    g[y0][0] = 'X'
    g[y1][W - 1] = 'X'
    lg = {'K': T_CAGE, 'Q': T_CAGEDOOR, 'm': T_MUSH, 'A': T_TENT}
    A, _ = area_from_grid("forest", "The Whisperwood", "forest", g, 14, {}, {}, legend_over=lg)
    for x, y in [(lx, ly)]:
        A.tiles[y][x] = T_GRASS
    A.tiles[cy][cx] = T_FIRE
    A.entries = {"west": (1, y0), "east": (W - 2, y1)}
    _flood_fix(A, (1, y0), T_TREE)
    A.tiles[ly][lx] = T_GRASS
    lysa = make_npc("lysa", "Lysa Thistlefoot", lx, ly)
    A.actors.append(lysa)
    A.cage_door = door
    A.notes[door] = "cage"

    def free_near(px, py, r):
        for _ in range(200):
            x, y = px + rnd.randint(-r, r), py + rnd.randint(-r, r)
            if A.walkable(x, y) and not A.actor_at(x, y) and A.tiles[y][x] != T_EXIT:
                return x, y
        return None

    boss = make_monster("snagtooth", *free_near(cx, cy + (1 if cy < H // 2 else -1), 1))
    A.actors.append(boss)
    for k in ["goblin", "goblin", "goblin", "goblin_archer"]:
        p = free_near(cx, cy, 6)
        if p:
            A.actors.append(make_monster(k, *p))
    # wolves somewhere in the middle of the wood, plus goblin scouts
    for _ in range(40):
        wx, wy = rnd.randint(30, 50), rnd.randint(4, H - 5)
        if A.walkable(wx, wy):
            for _ in range(3):
                p = free_near(wx, wy, 2)
                if p:
                    A.actors.append(make_monster("wolf", *p))
            break
    for _ in range(2):
        p = free_near(rnd.randint(70, 88), y1, 4)
        if p:
            A.actors.append(make_monster("goblin", *p))
    A.add_item(*free_near(cx, cy, 5), "potion")
    A.scene = "forest"
    return A


def gen_encounter(seed, party_level, kind=None):
    rnd = random.Random(seed)
    W, H = 60, 24
    g = [['&' if rnd.random() < 0.38 else ',' for x in range(W)] for y in range(H)]
    for x in range(W):
        g[0][x] = g[H - 1][x] = '&'
    for y in range(H):
        g[y][0] = g[y][W - 1] = '&'
    _smooth(g, W, H, '&', ',', 3)
    ym = H // 2
    _carve_path(g, rnd, 1, ym, W - 2, ym + rnd.randint(-3, 3), ':')
    for y in range(ym - 4, ym + 5):
        for x in range(24, 40):
            if ((x - 32) / 8.0) ** 2 + ((y - ym) / 4.0) ** 2 <= 1:
                g[y][x] = ','
    g[ym][0] = 'X'
    A, _ = area_from_grid("road", "Roadside", "forest", g, 14, {}, {})
    for y in range(H):
        if A.tiles[y][W - 2] in (T_ROAD,):
            A.tiles[y][W - 1] = T_EXIT
    A.entries = {"west": (1, ym)}
    _flood_fix(A, (1, ym), T_TREE)
    kind = kind or rnd.choice(["wolves", "goblins", "bandits"])
    if kind == "wolves":
        group = ["wolf"] * (2 + party_level // 2)
    elif kind == "goblins":
        group = ["goblin", "goblin", "goblin_archer"] + ["goblin"] * (party_level // 2)
    else:
        group = ["bandit"] * (3 + party_level // 2)
    for k in group:
        for _ in range(100):
            x, y = rnd.randint(30, 44), rnd.randint(ym - 5, ym + 5)
            if A.walkable(x, y) and not A.actor_at(x, y):
                A.actors.append(make_monster(k, x, y))
                break
    A.encounter = kind
    return A


def gen_dungeon(aid, name, seed, W=78, H=40):
    rnd = random.Random(seed)
    A = Area(aid, name, W, H, "dungeon", fill=T_CWALL, light=7)
    rooms = []

    def split(x0, y0, x1, y1, depth):
        w, h = x1 - x0, y1 - y0
        can_h, can_v = h >= 16, w >= 22
        if depth > 4 or not (can_h or can_v):
            rw, rh = rnd.randint(5, max(5, w - 4)), rnd.randint(4, max(4, h - 3))
            rw, rh = min(rw, 14), min(rh, 9)
            rx, ry = rnd.randint(x0 + 1, x1 - rw - 1), rnd.randint(y0 + 1, y1 - rh - 1)
            rooms.append((rx, ry, rx + rw, ry + rh))
            return [len(rooms) - 1]
        if can_h and can_v:
            horiz = (w < h) if abs(w - h) > 4 else rnd.random() < 0.5
        else:
            horiz = can_h
        if horiz:
            cut = rnd.randint(y0 + 7, y1 - 7)
            a = split(x0, y0, x1, cut, depth + 1)
            b = split(x0, cut, x1, y1, depth + 1)
        else:
            cut = rnd.randint(x0 + 10, x1 - 10)
            a = split(x0, y0, cut, y1, depth + 1)
            b = split(cut, y0, x1, y1, depth + 1)
        corridor(rnd.choice(a), rnd.choice(b))
        return a + b

    def center(i):
        r = rooms[i]
        return (r[0] + r[2]) // 2, (r[1] + r[3]) // 2

    corridors = []

    def corridor(i, j):
        corridors.append((i, j))

    split(1, 1, W - 1, H - 1, 0)
    for (x0, y0, x1, y1) in rooms:
        for y in range(y0, y1):
            for x in range(x0, x1):
                A.tiles[y][x] = T_CFLOOR
    for i in range(3):  # a few extra loops
        corridors.append((rnd.randrange(len(rooms)), rnd.randrange(len(rooms))))
    for (i, j) in corridors:
        (ax, ay), (bx, by) = center(i), center(j)
        rail = rnd.random() < 0.35
        if rnd.random() < 0.5:
            pts = [(x, ay) for x in range(min(ax, bx), max(ax, bx) + 1)] + [(bx, y) for y in range(min(ay, by), max(ay, by) + 1)]
        else:
            pts = [(ax, y) for y in range(min(ay, by), max(ay, by) + 1)] + [(x, by) for x in range(min(ax, bx), max(ax, bx) + 1)]
        for (x, y) in pts:
            if A.tiles[y][x] == T_CWALL:
                A.tiles[y][x] = T_RAIL if rail else T_CFLOOR
    # decoration
    for y in range(1, H - 1):
        for x in range(1, W - 1):
            t = A.tiles[y][x]
            if t == T_CWALL:
                nb = sum(1 for dx, dy in DIRS8 if A.tiles[y + dy][x + dx] in (T_CFLOOR, T_RAIL))
                if nb:
                    r = rnd.random()
                    if r < 0.035:
                        A.tiles[y][x] = T_ORE
                    elif r < 0.05:
                        A.tiles[y][x] = T_TORCH
            elif t == T_CFLOOR:
                r = rnd.random()
                if r < 0.015:
                    A.tiles[y][x] = T_BONES
                elif r < 0.025:
                    A.tiles[y][x] = T_WEB
    A.rooms = rooms
    # stairs: up in room 0, down in the room farthest away by walking
    ux, uy = center(0)
    dist = bfs_dist(A, [(ux, uy)])
    far = max(range(1, len(rooms)), key=lambda i: dist.get(center(i), -1))
    dx_, dy_ = center(far)
    A.tiles[uy][ux] = T_SUP
    A.tiles[dy_][dx_] = T_SDOWN
    A.entries = {"up": (ux + 1 if A.walkable(ux + 1, uy) else ux, uy + (0 if A.walkable(ux + 1, uy) else 1)),
                 "down": (dx_ - 1 if A.walkable(dx_ - 1, dy_) else dx_, dy_ + (0 if A.walkable(dx_ - 1, dy_) else -1))}
    A.stair_up, A.stair_down, A.far_room = (ux, uy), (dx_, dy_), far
    _flood_fix(A, (ux, uy), T_CWALL)
    return A, rnd


def _room_spots(A, rnd, room, n):
    x0, y0, x1, y1 = room
    out = []
    for _ in range(80):
        x, y = rnd.randint(x0, x1 - 1), rnd.randint(y0, y1 - 1)
        if A.walkable(x, y) and A.tiles[y][x] not in (T_SUP, T_SDOWN) and not A.actor_at(x, y) and (x, y) not in out:
            out.append((x, y))
            if len(out) >= n:
                break
    return out


def _chest(A, rnd, room, items, locked=0):
    x0, y0, x1, y1 = room
    for _ in range(50):
        x, y = rnd.choice([x0, x1 - 1]), rnd.randint(y0, y1 - 1)
        if A.tiles[y][x] == T_CFLOOR and not A.actor_at(x, y):
            A.tiles[y][x] = T_CHEST
            A.chests[(x, y)] = {"items": items, "locked": locked}
            return (x, y)
    return None


def _traps(A, rnd, n):
    cells = [(x, y) for y in range(A.h) for x in range(A.w) if A.tiles[y][x] == T_RAIL or
             (A.tiles[y][x] == T_CFLOOR and rnd.random() < 0.05)]
    rnd.shuffle(cells)
    start = A.entries["up"]
    for c in cells:
        if n <= 0:
            break
        if cheb(c[0], c[1], start[0], start[1]) > 8:
            A.traps[c] = {"hidden": True, "dmg": "2d6"}
            n -= 1


def gen_mine1(seed):
    A, rnd = gen_dungeon("mine1", "Deepdelve Mine", seed)
    A.links[A.stair_up] = ["world", "mine"]
    A.links[A.stair_down] = ["mine2", "up"]
    rooms = A.rooms
    sizes = sorted(range(1, len(rooms)), key=lambda i: -(rooms[i][2] - rooms[i][0]) * (rooms[i][3] - rooms[i][1]))
    big = sizes[0]
    for (x, y) in _room_spots(A, rnd, rooms[big], 3):
        A.actors.append(make_monster("ogre" if not any(a.tmpl == "ogre" for a in A.actors) else "kobold", x, y))
    _chest(A, rnd, rooms[big], ["ledger", "gold:60", "potion"])
    for i in range(1, len(rooms)):
        if i == big:
            continue
        r = rnd.random()
        if r < 0.35:
            grp = ["kobold", "kobold_slinger"] + (["kobold"] if rnd.random() < 0.5 else [])
        elif r < 0.6:
            grp = ["cultist", "cultist", "kobold"]
        elif r < 0.75:
            grp = ["spider"]
        else:
            grp = []
        for k, (x, y) in zip(grp, _room_spots(A, rnd, rooms[i], len(grp))):
            A.actors.append(make_monster(k, x, y))
    extra = [i for i in range(1, len(rooms)) if i != big]
    rnd.shuffle(extra)
    loot = [["potion", "gold:25"], ["stinger", "gold:15"], ["scroll_mm", "potion"], ["studded", "gold:30"]]
    for i, items in zip(extra, loot):
        _chest(A, rnd, rooms[i], items, locked=13 if rnd.random() < 0.5 else 0)
    _traps(A, rnd, 6)
    A.scene = "mine"
    return A


def gen_mine2(seed):
    A, rnd = gen_dungeon("mine2", "Deepdelve - Lower Galleries", seed)
    A.links[A.stair_up] = ["mine1", "down"]
    A.links[A.stair_down] = ["sanctum", "up"]
    rooms = A.rooms
    far = A.far_room
    others = [i for i in range(1, len(rooms)) if i != far]
    rnd.shuffle(others)
    # Edrin lies in a quiet side room
    er = others[0] if others else far
    sp = _room_spots(A, rnd, rooms[er], 1)
    if sp:
        ex, ey = sp[0]
        A.decals[(ex, ey)] = ("%", 3)
        A.add_item(ex, ey, "locket")
        A.notes[(ex, ey)] = "edrin"
    for i in range(1, len(rooms)):
        r = rnd.random()
        if i == far:
            grp = ["ghoul", "skeleton", "skeleton_archer"]
        elif r < 0.35:
            grp = ["skeleton", "skeleton", "skeleton_archer"]
        elif r < 0.65:
            grp = ["zombie", "zombie"] + (["zombie"] if rnd.random() < 0.5 else [])
        elif r < 0.85:
            grp = ["ghoul"] + (["zombie"] if rnd.random() < 0.5 else [])
        else:
            grp = []
        for k, (x, y) in zip(grp, _room_spots(A, rnd, rooms[i], len(grp))):
            A.actors.append(make_monster(k, x, y))
    loot = [["dawnmace", "potion"], ["elven_chain"], ["potion", "potion", "gold:40"], ["ring_prot", "gold:20"]]
    for i, items in zip(others[1:] + [far], loot):
        _chest(A, rnd, rooms[i], items, locked=15 if "ring_prot" in items else (13 if rnd.random() < 0.4 else 0))
    _traps(A, rnd, 5)
    A.scene = "galleries"
    return A


def gen_sanctum():
    W, H = 50, 25
    A = Area("sanctum", "Sanctum of the Pale Flame", W, H, "dungeon", fill=T_WALL, light=10)

    def rect(x0, y0, x1, y1, t):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                A.tiles[y][x] = t

    rect(10, 7, 39, 17, T_STONEFL)
    rect(23, 7, 26, 17, T_CARPET)
    rect(23, 1, 26, 6, T_STONEFL)
    rect(21, 1, 28, 3, T_STONEFL)
    for x in range(23, 27):
        A.tiles[5][x] = T_SEAL
    A.tiles[1][24] = T_SDOWN
    rect(24, 18, 25, 22, T_STONEFL)
    A.tiles[22][24] = T_SUP
    for x in (13, 19, 30, 36):
        for y in (9, 12, 15):
            A.tiles[y][x] = T_PILLAR
    A.tiles[8][16] = A.tiles[8][33] = T_PALEFIRE
    A.tiles[8][24] = A.tiles[8][25] = T_ALTAR
    rect(2, 9, 8, 15, T_STONEFL)
    A.tiles[12][9] = T_DOOR
    for y in (10, 12, 14):
        A.tiles[y][3] = T_BED
    rect(41, 9, 47, 15, T_STONEFL)
    A.tiles[12][40] = T_DOOR
    A.links[(24, 22)] = ["mine2", "down"]
    A.links[(24, 1)] = ["lair", "up"]
    A.entries = {"up": (24, 21), "down": (24, 2)}
    for (x, y), items, lock in [((46, 10), ["frostbite"], 0), ((46, 14), ["ward_embers", "potion_greater"], 15),
                                ((42, 10), ["scroll_fireball", "gold:120"], 0)]:
        A.tiles[y][x] = T_CHEST
        A.chests[(x, y)] = {"items": items, "locked": lock}
    for key, (x, y) in [("corvane", (24, 10)), ("fanatic", (21, 11)), ("fanatic", (28, 11)),
                        ("cultist", (35, 14)), ("cultist", (20, 16)), ("cultist", (29, 16)),
                        ("cultist", (5, 11)), ("cultist", (6, 13))]:
        A.actors.append(make_monster(key, x, y))
    A.scene = "sanctum"
    return A


def gen_lair(seed):
    rnd = random.Random(seed)
    W, H = 70, 34
    A = Area("lair", "Ashmaw's Lair", W, H, "dungeon", fill=T_CWALL, light=11)
    cx, cy = W // 2, H // 2
    g = [[1] * W for _ in range(H)]
    for y in range(1, H - 1):
        for x in range(1, W - 1):
            e = ((x - cx) / 31.0) ** 2 + ((y - cy) / 15.0) ** 2
            g[y][x] = 0 if e + rnd.uniform(-0.25, 0.25) < 0.85 else 1
    for _ in range(3):
        new = [row[:] for row in g]
        for y in range(1, H - 1):
            for x in range(1, W - 1):
                c = sum(g[y + dy][x + dx] for dx in (-1, 0, 1) for dy in (-1, 0, 1))
                new[y][x] = 1 if c >= 5 else 0
        g = new
    for y in range(H):
        for x in range(W):
            A.tiles[y][x] = T_CWALL if g[y][x] else T_CFLOOR
    for y in range(4, H - 2):  # the approach
        for x in range(cx - 2, cx + 3):
            A.tiles[y][x] = T_CFLOOR
    for _ in range(4):  # lava rivers
        x, y = rnd.choice([(rnd.randint(4, cx - 8), rnd.randint(4, H - 5)), (rnd.randint(cx + 8, W - 5), rnd.randint(4, H - 5))])
        for _ in range(rnd.randint(25, 45)):
            if A.tiles[y][x] == T_CFLOOR and abs(x - cx) > 3:
                A.tiles[y][x] = T_LAVA
                if rnd.random() < 0.5 and abs(x + 1 - cx) > 3 and A.tiles[y][x + 1] == T_CFLOOR:
                    A.tiles[y][x + 1] = T_LAVA
            x = clamp(x + rnd.choice((-1, 0, 1, 1)), 2, W - 3)
            y = clamp(y + rnd.choice((-1, 0, 1)), 2, H - 3)
    for y in range(3, 10):  # the hoard
        for x in range(cx - 10, cx + 11):
            if A.tiles[y][x] == T_CFLOOR and rnd.random() < 0.35 and abs(x - cx) > 1:
                A.tiles[y][x] = T_HOARD
    for y in range(1, H - 1):
        for x in range(1, W - 1):
            if A.tiles[y][x] == T_CFLOOR and rnd.random() < 0.02:
                A.tiles[y][x] = T_BONES
    sy = H - 3
    A.tiles[sy][cx] = T_SUP
    A.links[(cx, sy)] = ["sanctum", "down"]
    A.entries = {"up": (cx, sy - 1)}
    _flood_fix(A, (cx, sy), T_CWALL)
    A.actors.append(make_monster("ashmaw", cx, 7))
    for (x, y) in [(cx - 4, 5), (cx + 5, 6), (cx + 2, 4)]:
        if A.walkable(x, y):
            A.add_item(x, y, "gold:%d" % rnd.randint(80, 160))
    A.scene = "lair"
    return A


# =============================================================================
# The game state and rules engine (no curses in here)
# =============================================================================
QUESTS = {
    "rats": "Rats in the Cellar",
    "miners": "The Missing Miners",
    "lysa": "A Halfling in a Cage",
    "edrin": "Brother Lost",
    "bounty": "The Captain's Bounty",
    "lost": "Lost and Found",
}
# random side quests, rolled per game from the map seed
BOUNTIES = [("wolf", "forest", "wolves in the Whisperwood", 4, 6), ("kobold", "mine1", "kobolds in Deepdelve", 6, 9),
            ("spider", "mine1", "giant spiders in Deepdelve", 2, 2), ("skeleton", "mine2", "skeletons in the galleries", 5, 7),
            ("zombie", "mine2", "walking dead in the galleries", 3, 5), ("goblin", "forest", "goblins in the Whisperwood", 4, 6)]
LOST = [("pell", "lute", "my lute - I dropped it running from goblins"),
        ("greta", "hammer_greta", "my good hammer - my apprentice took it to the mine and never came back"),
        ("aldous", "sunstone", "the temple's Sunstone - a pilgrim carried it off to the mines and was lost")]
REWARD_ITEMS = ["potion_greater", "ring_prot", "amulet_vigor", "longsword_p1", "scroll_mm"]
AREA_TITLE = {"forest": "the Whisperwood", "mine1": "Deepdelve Mine", "mine2": "the Lower Galleries"}


def roll_side_quests(g):
    rnd = random.Random(g.seed + 77)
    mon, area, what, lo, hi = rnd.choice(BOUNTIES)
    g.flags["sq_bounty"] = {"mon": mon, "area": area, "what": what, "need": rnd.randint(lo, hi), "have": 0,
                            "gold": rnd.randrange(60, 160, 10)}
    giver, item, why = rnd.choice(LOST)
    g.flags["sq_lost"] = {"giver": giver, "item": item, "why": why, "area": rnd.choice(["forest", "mine1", "mine2"]),
                          "gold": rnd.randrange(40, 120, 10), "reward": rnd.choice(REWARD_ITEMS)}


def place_lost_item(g, A):
    """Hide the lost item in a chest (or on the floor) when its area is first made."""
    q = g.flags.get("sq_lost")
    if not q or q["area"] != A.id:
        return
    rnd = random.Random(g.seed + 91)
    if A.chests:
        pos = rnd.choice(sorted(A.chests))
        A.chests[pos]["items"].append(q["item"])
        A.chests[pos]["locked"] = 0
        return
    cells = [(x, y) for y in range(A.h) for x in range(A.w) if A.walkable(x, y) and (x, y) not in A.links]
    A.items.setdefault(rnd.choice(cells), []).append(q["item"])


def side_quest_options(g, npc):
    """Extra dialogue nodes and options for the random side quests."""
    nodes, opts = {}, []
    b, l = g.flags.get("sq_bounty"), g.flags.get("sq_lost")
    if npc == "captain" and b:
        st = g.qstate("bounty")
        if not st:
            def take():
                g.quest("bounty", "Captain Rook pays %d gold for %d %s. (%d so far)" % (b["gold"], b["need"], b["what"], b["have"]))
                return "sq_b_took"
            nodes["sq_b"] = ("\"There's coin in it, if you're handy: %d %s, and %d gold from the watch chest. Bring me proof - "
                             "ears, fangs, whatever they have.\"" % (b["need"], b["what"], b["gold"]),
                             [_opt("Deal.", take), _opt("Not now.", "start")])
            nodes["sq_b_took"] = ("\"Good. Don't die - paperwork's a nightmare.\"", [_opt("(Back)", "start")])
            opts.append(_opt("Is there any work for me?", "sq_b"))
        elif st == "active" and b["have"] >= b["need"]:
            def pay():
                g.gold += b["gold"]
                g.award_xp(100 + 25 * b["need"])
                g.quest("bounty", "Captain Rook paid %d gold for the %s." % (b["gold"], b["what"]), "done")
                return "sq_b_paid"
            nodes["sq_b_paid"] = ("Rook counts the trophies twice, then the coins once. \"Fair's fair. The road's a little safer "
                                  "tonight.\"", [_opt("(Back)", "start")])
            opts.append(_opt("About the bounty - it's done.", pay))
    if l and npc == l["giver"]:
        st = g.qstate("lost")
        if not st:
            def take2():
                g.quest("lost", "%s lost %s. It should be somewhere in %s." % (NPC_NAMES.get(npc, npc), ITEMS[l["item"]]["name"],
                                                                                AREA_TITLE[l["area"]]))
                return "sq_l_took"
            nodes["sq_l"] = ("\"You're going out there? Then keep an eye open for %s. Somewhere in %s, I'd wager. "
                             "I'd make it worth your while.\"" % (l["why"], AREA_TITLE[l["area"]]),
                             [_opt("I'll keep an eye out.", take2), _opt("(Back)", "start")])
            nodes["sq_l_took"] = ("\"Thank you. Truly.\"", [_opt("(Back)", "start")])
            opts.append(_opt("Is there any work for me?", "sq_l"))
        elif st == "active" and l["item"] in g.bag:
            def give():
                g.bag.remove(l["item"])
                g.gold += l["gold"]
                g.bag.append(l["reward"])
                g.award_xp(150)
                g.quest("lost", "Returned %s. Reward: %d gold and %s." % (ITEMS[l["item"]]["name"], l["gold"],
                                                                         ITEMS[l["reward"]]["name"]), "done")
                return "sq_l_done"
            nodes["sq_l_done"] = ("Eyes wide, they take it back with both hands. \"I never thought I'd see it again. Here - "
                                  "take this, and this. No arguing.\"", [_opt("(Back)", "start")])
            opts.append(_opt("I found %s." % ITEMS[l["item"]]["name"], give))
    return nodes, opts


NPC_NAMES = {"pell": "Pell", "greta": "Greta", "aldous": "Father Aldous", "captain": "Captain Rook"}
COMP_HOME = {"brannoc": ("town", 5, 7), "tamsin": ("town", 27, 11), "lysa": ("town", 12, 8), "maren": ("town", 65, 5)}
WORLD = {  # location: (label, area, entry, map x, map y)
    "emberfall": ("Emberfall", "town", None, 15, 14),
    "whisperwood": ("The Whisperwood", "forest", None, 34, 10),
    "deepdelve": ("Deepdelve Mine", "mine1", "up", 52, 5),
}
TRAVEL_H = {frozenset(("emberfall", "whisperwood")): 3, frozenset(("whisperwood", "deepdelve")): 3,
            frozenset(("emberfall", "deepdelve")): 6}
BANTER = {
    "brannoc": ["Brannoc: \"My knee says rain. My knee also said 'don't go to the mine', so what does it know.\"",
                "Brannoc: \"When this is done I'm buying the biggest ale Hobb's got. Then a bigger one.\"",
                "Brannoc: \"Elves. Always looking at the sky. The interesting stuff is under your feet.\""],
    "tamsin": ["Tamsin: \"Did you know a red dragon's heart stays warm for a century after death? Lovely for tea.\"",
               "Tamsin: \"If we die, I want it noted that I suggested a library instead.\"",
               "Tamsin: \"Walk faster. Or slower. Just walk differently, the rhythm is distracting me.\""],
    "maren": ["Maren hums a dawn hymn under her breath, and for a moment the shadows seem a little thinner.",
              "Maren: \"Edrin used to say the mountain sang at night. I thought he was being poetic.\"",
              "Maren: \"Keep your wounds where I can see them, please.\""],
    "lysa": ["Lysa: \"I'm not saying I picked your pocket. I'm saying your pocket was very easy to pick.\"",
             "Lysa: \"Eight gold to Pell, twelve to Hobb, a chicken to Greta... I should really write this down.\"",
             "Lysa: \"Rule one of dungeons: never trust a floor tile that looks smug.\""],
}
AREA_BANTER = {
    ("mine1", "brannoc"): "Brannoc runs a hand along the timber supports. \"My lads cut these. Let's find them.\"",
    ("mine2", "maren"): "Maren: \"Death, everywhere down here. I can feel it. Stay close to the light.\"",
    ("mine2", "brannoc"): "Brannoc, hoarsely: \"Those... those are miners' boots on them. Dawn take the ones who did this.\"",
    ("lair", "tamsin"): "Tamsin, very quietly: \"I take back everything I ever said about wanting to see one.\"",
    ("lair", "lysa"): "Lysa stares at the hoard. \"Focus, Lysa. Dragon first. Then gold. Dragon first...\"",
    ("forest", "lysa"): "Lysa: \"Ugh. This wood again. Mind the third tree on the left, it's rude.\"",
    ("sanctum", "maren"): "Maren: \"These are Dawnmother pillars - they've defaced them with that pale fire. Blasphemers.\"",
}


# Difficulty: damage the party takes and deals (monster HP in effect), raising price, rest ambushes, start kit
DIFFICULTY = {
    "easy": dict(name="Easy", taken=0.7, dealt=1.4, raise_cost=50, ambush=0.10, gold=120, potions=4,
                 desc="Foes hit 30% softer and fall faster (about 30% less HP). Raising the dead costs 50 gold, "
                      "rests are rarely ambushed, and you start with more coin and potions."),
    "normal": dict(name="Normal", taken=1.0, dealt=1.0, raise_cost=150, ambush=0.25, gold=75, potions=2,
                   desc="The adventure as designed: the d20 rules as written."),
    "hard": dict(name="Hard", taken=1.15, dealt=0.87, raise_cost=300, ambush=0.35, gold=75, potions=2,
                 desc="Foes hit 15% harder and are tougher (about 15% more HP). Raising costs 300 gold and "
                      "resting in the wild is dangerous."),
}


class Game:
    def __init__(self, seed=None):
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.party, self.areas, self.area = [], {}, None
        self.flags, self.quests, self.waiting = {}, {}, {}
        self.gold, self.bag = 0, []
        self.minutes = 8 * 60
        self.log = deque(maxlen=300)
        self.events, self.pending = [], deque()
        self.combat = None
        self.trail = deque(maxlen=12)
        self.visible = set()
        self.discovered = ["emberfall"]
        self.kills, self.steps = 0, 0
        self.over = None
        self.travel = None
        self.diff = "normal"
        self.location = "emberfall"

    # --- basics ---------------------------------------------------------------
    def msg(self, text, col=LIGHT):
        self.log.append((text, col))

    @property
    def leader(self):
        """Whoever leads: the hero, or while the hero is dead, the first companion still alive."""
        return next((p for p in self.party if p.conscious), None) or next((p for p in self.party if not p.dead), self.party[0])

    @property
    def hero(self):
        return self.party[0]

    @property
    def day(self):
        return self.minutes // 1440 + 1

    @property
    def clock(self):
        m = self.minutes % 1440
        return "%02d:%02d" % (m // 60, m % 60)

    @property
    def night(self):
        h = (self.minutes % 1440) // 60
        return h >= 21 or h < 6

    def living(self):
        return [p for p in self.party if not p.dead]

    def able(self):
        return [p for p in self.party if p.conscious]

    def party_level(self):
        return max(1, sum(p.level for p in self.party) // max(1, len(self.party)))

    def has(self, item):
        return item in self.bag

    def in_party(self, cid):
        return any(p.cid == cid for p in self.party)

    def all_actors(self):
        return [p for p in self.party if not p.dead] + [a for a in self.area.actors if not a.dead]

    def actor_at(self, x, y):
        for p in self.party:
            if not p.dead and p.x == x and p.y == y:
                return p
        return self.area.actor_at(x, y)

    def free(self, x, y):
        return self.area.walkable(x, y) and self.actor_at(x, y) is None

    def free_near(self, x, y, n=1, avoid=()):
        out = []
        dist = bfs_dist(self.area, [(x, y)], limit=12)
        for p in sorted(dist, key=lambda q: (dist[q], random.random())):
            if self.free(*p) and p not in avoid and self.area.tile(*p) not in (T_EXIT, T_SUP, T_SDOWN):
                out.append(p)
                if len(out) >= n:
                    break
        return out

    def quest(self, qid, text, state=None):
        new = qid not in self.quests
        q = self.quests.setdefault(qid, {"title": QUESTS[qid], "state": "active", "log": []})
        q["log"].append("Day %d: %s" % (self.day, text))
        if state:
            q["state"] = state
        if new:
            self.msg("New quest: %s" % q["title"], GOLD)
        elif state == "done":
            self.msg("Quest complete: %s" % q["title"], GOLD)
        else:
            self.msg("Journal updated: %s" % q["title"], GOLD)

    def qstate(self, qid):
        return self.quests.get(qid, {}).get("state")

    # --- new game, areas --------------------------------------------------------
    @property
    def D(self):
        return DIFFICULTY.get(self.diff, DIFFICULTY["normal"])

    @property
    def raise_cost(self):
        return self.D["raise_cost"]

    def new_game(self, pc, diff="normal"):
        self.diff = diff if diff in DIFFICULTY else "normal"
        roll_side_quests(self)
        pc.pcol = 0
        self.party = [pc]
        self.gold = self.D["gold"]
        self.bag = ["potion"] * self.D["potions"] + list(CLASSES[pc.cls]["bag"])
        self.areas["town"] = gen_town()
        self.area = self.areas["town"]
        self.place_party(15, 11)
        self.update_fov()
        self.flags["visited_town"] = True
        self.msg("You wake in the Rusty Lantern, the inn of Emberfall. Talk to people by walking into them.", GOLD)
        self.msg("Press ? for help at any time.", GRAY)

    def generate(self, aid):
        s = self.seed
        gens = {"town": gen_town, "cellar": gen_cellar, "forest": lambda: gen_forest(s + 1),
                "mine1": lambda: gen_mine1(s + 2), "mine2": lambda: gen_mine2(s + 3),
                "sanctum": gen_sanctum, "lair": lambda: gen_lair(s + 5)}
        A = gens[aid]()
        place_lost_item(self, A)
        return A

    def place_party(self, x, y):
        L = self.leader
        L.x, L.y = x, y
        spots = self.free_near(x, y, len(self.party), avoid={(x, y)})
        i = 0
        for p in self.party:
            if p.dead or p is L:
                continue
            if i < len(spots):
                p.x, p.y = spots[i]
                i += 1
        self.trail.clear()

    def enter_area(self, aid, entry=None):
        if aid == "world":
            self.pending.append(("world",))
            return
        if aid not in self.areas:
            self.areas[aid] = self.generate(aid)
        A = self.areas[aid]
        self.area = A
        pos = A.entries.get(entry) if entry else None
        if pos is None:
            pos = list(A.entries.values())[0]
        self.place_party(*pos)
        for loc, v in WORLD.items():
            if v[1] == aid:
                self.location = loc
        self.update_fov()
        self.msg("You enter %s." % A.name, CYAN)
        first = not self.flags.get("visited_" + aid)
        self.flags["visited_" + aid] = True
        if first and A.scene:
            self.pending.append(("scene", A.scene))
        if first:
            for p in self.party[1:]:
                line_ = AREA_BANTER.get((aid, p.cid))
                if line_ and not p.dead:
                    self.msg(line_, PARTY_COLS[p.pcol % 5])
        if aid == "town" and self.hero.dead and self.gold < self.raise_cost:
            self.msg("You carry %s home, but there is no coin for a raising. The story ends here." % self.hero.name, RED)
            self.game_over()
            return
        if aid == "mine1" and "deepdelve" not in self.discovered:
            self.discovered.append("deepdelve")
        self.check_hostiles()

    def travel_to(self, dest):
        """World-map travel; may be interrupted by a roadside encounter."""
        a, b = self.location, dest
        hours = TRAVEL_H.get(frozenset((a, b)), 4)
        self.minutes += hours * 60
        self.msg("You travel for %d hours." % hours, GRAY)
        if a != b and random.random() < 0.3 and dest != "emberfall" or (a != b and random.random() < 0.12):
            self.travel = dest
            A = gen_encounter(random.randrange(1 << 30), self.party_level())
            self.areas["road"] = A
            self.area = A
            self.place_party(*A.entries["west"])
            self.update_fov()
            self.msg("Your journey is interrupted!", RED)
            self.pending.append(("scene", "ambush_" + A.encounter))
            self.check_hostiles()
            return
        self.arrive(dest, a)

    def arrive(self, dest, origin=None):
        self.travel = None
        self.areas.pop("road", None)
        lbl, aid, entry, mx, my = WORLD[dest]
        if entry is None:
            ox = WORLD.get(origin, WORLD["emberfall"])[3] if origin else 0
            entry = "west" if ox <= mx else "east"
        self.location = dest
        self.enter_area(aid, entry)

    # --- field of view ---------------------------------------------------------
    def light_radius(self):
        A = self.area
        r = A.light
        if A.kind in ("town", "forest") and self.night:
            r = min(r, 9)
        return r

    def update_fov(self):
        A = self.area
        r = self.light_radius()
        vis = set()
        for p in self.party:
            if p.dead:
                continue
            rr = r + (2 if p.race in ("elf", "dwarf") and A.kind == "dungeon" else 0)
            vis |= fov(A, p.x, p.y, rr)
        # lit tiles (fires, torches, lava) are visible from afar if in line of sight
        # foes that just shot or cast at us gave their position away
        if self.combat:
            rnd_ = self.combat["round"]
            for a in A.actors:
                if a.conscious and getattr(a, "revealed", -9) >= rnd_ - 1:
                    vis.add((a.x, a.y))
        self.visible = vis
        for (x, y) in vis:
            A.explored[y][x] = True

    def reveal(self, m):
        """An attacker in the dark gives itself away for this round and the next."""
        if not self.combat or m.is_pc or (m.x, m.y) in self.visible:
            return
        m.revealed = self.combat["round"]
        self.visible.add((m.x, m.y))
        self.area.explored[m.y][m.x] = True
        self.msg("Something attacks out of the darkness - %s!" % m.name, ORANGE)

    def sees(self, a):
        return (a.x, a.y) in self.visible

    # --- exploration --------------------------------------------------------------
    def try_move(self, dx, dy):
        if self.combat:
            return self.combat_move(dx, dy)
        L = self.leader
        if not L.conscious:
            return
        A = self.area
        nx, ny = L.x + dx, L.y + dy
        if not A.inb(nx, ny):
            return
        other = self.actor_at(nx, ny)
        if other is not None:
            if other.is_pc:
                other.x, other.y, L.x, L.y = L.x, L.y, nx, ny
                self.arrived_on(L)
                self.tick()
            elif other.faction == "hostile":
                self.msg("You charge %s!" % other.name, ORANGE)
                other.alerted = True
                self.start_combat(force=[other])
            elif other.npc:
                self.pending.append(("talk", other.npc, other.name))
            return
        t = A.tile(nx, ny)
        if t == T_DOOR:
            A.set(nx, ny, T_ODOOR)
            self.tick()
            return
        if t == T_CHEST:
            self.open_chest(nx, ny)
            return
        if t == T_CAGEDOOR:
            self.open_cage(nx, ny)
            return
        if t in (T_COUNTER, T_TABLE):
            b = self.actor_at(nx + dx, ny + dy)
            if b and b.npc and not b.is_pc:
                self.pending.append(("talk", b.npc, b.name))
            return
        if not A.walkable(nx, ny):
            if t == T_SEAL:
                self.msg("A seal of pale fire bars the way. Something on the other side is breathing.", PALE)
            return
        self.trail.append((L.x, L.y))
        L.x, L.y = nx, ny
        self.follow()
        self.arrived_on(L)
        self.tick()

    def follow(self):
        L = self.leader
        A = self.area
        if not A.inb(L.x, L.y):
            self.place_party(*list(A.entries.values())[0])
            return
        for p in self.party:
            if p.conscious and p is not L and not A.inb(p.x, p.y):
                spot = self.free_near(L.x, L.y, 1)
                if spot:
                    p.x, p.y = spot[0]
        trail = list(self.trail)
        k = 0
        for p in self.party:
            if not p.conscious or p is L:
                continue
            k += 1
            want = trail[-k] if len(trail) >= k else None
            if want and self.free(*want) and cheb(p.x, p.y, want[0], want[1]) <= 2:
                p.x, p.y = want
            elif cheb(p.x, p.y, L.x, L.y) > 1 + k // 2:
                self.step_toward(p, [(L.x, L.y)], 2)

    def step_toward(self, a, targets, steps, stop_at=1):
        occ = {(o.x, o.y) for o in self.all_actors() if o is not a and (o.conscious or o.downed)}
        dist = bfs_dist(self.area, targets, blocked=occ - set(targets), limit=60)
        moved = 0
        for _ in range(steps):
            cur = dist.get((a.x, a.y), 999)
            if cur <= stop_at:
                break
            best = None
            for dx, dy in DIRS8:
                n = (a.x + dx, a.y + dy)
                if n in occ or not self.area.walkable(*n):
                    continue
                d = dist.get(n, 999)
                if d < cur and (best is None or d < best[0]):
                    best = (d, n)
            if not best:
                break
            a.x, a.y = best[1]
            moved += 1
        return moved

    def arrived_on(self, a):
        A = self.area
        pos = (a.x, a.y)
        its = A.items.pop(pos, None)
        if its:
            for it in its:
                self.pick_up(it)
        tr = A.traps.get(pos)
        if tr:
            dmg = roll(tr["dmg"])
            self.msg("A trap! Darts hiss from the wall - %s takes %d damage." % (a.name, dmg), RED)
            self.events.append(("burst", [pos], RED))
            del A.traps[pos]
            self.damage(a, dmg, "piercing")
        note = A.notes.get(pos)
        if note == "edrin" and not self.flags.get("edrin_found"):
            self.found_edrin()
        link = A.links.get(pos)
        if link and a is self.leader:
            dest, entry = link
            if dest == "world":
                self.pending.append(("world",))
            else:
                self.enter_area(dest, entry)
            return
        if A.tile(*pos) == T_EXIT and a is self.leader:
            if self.travel:
                self.msg("You slip away and continue your journey.", GRAY)
                self.arrive(self.travel, None)
            else:
                if self.area.id == "forest" and pos[0] > self.area.w // 2 and "deepdelve" not in self.discovered:
                    self.discovered.append("deepdelve")
                    self.msg("Beyond the trees, a mine road climbs into the mountains: Deepdelve.", GOLD)
                if self.area.id == "forest" and "whisperwood" not in self.discovered:
                    self.discovered.append("whisperwood")
                self.pending.append(("world",))

    def pick_up(self, it):
        if it.startswith("gold:"):
            n = int(it[5:])
            self.gold += n
            self.msg("You pick up %d gold." % n, GOLD)
            return
        self.bag.append(it)
        self.msg("You pick up: %s." % ITEMS[it]["name"], GOLD)
        if it == "ledger":
            self.flags["ledger"] = True
            if self.qstate("miners") == "active":
                self.quest("miners", "A ledger in the mine lists the missing miners as 'fed' or 'kept', signed by one "
                                     "Magister Corvane of the Pale Flame. The cult is feeding people to something.")

    def found_edrin(self):
        self.flags["edrin_found"] = True
        text = ("Beneath a fallen lamp lies a young man in a torn yellow scarf, his miner's pick still in his hand. "
                "He fought. Clutched in his other fist is a tin locket.")
        if self.in_party("maren"):
            text += ("\n\nMaren falls to her knees beside him. For a long moment she says nothing at all. Then she "
                     "closes his eyes, presses the locket to her lips, and stands. \"Rest now, Edrin. I'll finish "
                     "this.\" Her voice does not shake. Her hands do.")
            if self.qstate("edrin") == "active":
                self.quest("edrin", "We found Edrin in the lower galleries. Maren has said her goodbyes.", "done")
                self.award_xp(200 * len(self.living()), quiet=True)
                self.msg("Each companion gains 200 experience.", GOLD)
        elif self.qstate("edrin") == "active":
            self.quest("edrin", "We found Edrin's body in the lower galleries, and a locket. Sister Maren should have it.")
        self.pending.append(("message", "Edrin", text, "grave"))

    def open_chest(self, x, y):
        A = self.area
        ch = A.chests.get((x, y), {"items": [], "locked": 0})
        if ch.get("locked"):
            dc = ch["locked"]
            rogue = max(self.able(), key=lambda p: (p.cls == "rogue", p.m("DEX")))
            if rogue.cls == "rogue":
                r = d20() + rogue.m("DEX") + rogue.prof * 2
                if r >= dc:
                    self.msg("%s picks the lock (%d vs DC %d)." % (rogue.name, r, dc), GREEN)
                else:
                    self.msg("%s fails to pick the lock (%d vs DC %d)." % (rogue.name, r, dc), GRAY)
                    self.tick()
                    return
            else:
                brute = max(self.able(), key=lambda p: p.m("STR"))
                r = d20() + brute.m("STR")
                if r >= dc + 2:
                    self.msg("%s smashes the lock open (%d vs DC %d)." % (brute.name, r, dc + 2), GREEN)
                else:
                    self.msg("Locked. %s strains at it (%d vs DC %d). A rogue would help." % (brute.name, r, dc + 2), GRAY)
                    self.tick()
                    return
        A.set(x, y, T_OCHEST)
        A.chests.pop((x, y), None)
        if not ch["items"]:
            self.msg("The chest is empty.", GRAY)
        for it in ch["items"]:
            self.pick_up(it)
        self.tick()

    def open_cage(self, x, y):
        if self.has("cage_key") or self.flags.get("lysa_free"):
            self.area.set(x, y, T_ODOOR)
            if not self.flags.get("lysa_free"):
                self.flags["lysa_free"] = True
                self.bag.remove("cage_key")
                self.msg("The rusty key turns with a shriek. The cage door swings open.", GREEN)
            return
        rogue = next((p for p in self.able() if p.cls == "rogue"), None)
        if rogue:
            r = d20() + rogue.m("DEX") + rogue.prof * 2
            if r >= 15:
                self.flags["lysa_free"] = True
                self.area.set(x, y, T_ODOOR)
                self.msg("%s picks the cage lock (%d vs DC 15)." % (rogue.name, r), GREEN)
                return
        self.msg("The cage is locked. The goblin chief must have the key.", GRAY)
        self.pending.append(("talk", "lysa"))

    def tick(self, minutes=1):
        self.minutes += minutes
        self.steps += 1
        if not self.combat:  # the fallen come round after a while (5e: 1 HP after 1d4 hours)
            for p in self.party:
                if p.downed and random.random() < 0.02:
                    p.hp, p.dsaves = 1, [0, 0]
                    self.msg("%s comes round, groggy but alive." % p.name, GREEN)
        self.update_fov()
        A = self.area
        for a in A.actors:
            if a.faction == "neutral" and a.home and not a.is_pc and a.npc in ("villager",) and random.random() < 0.3:
                dx, dy = random.choice(DIRS8)
                nx, ny = a.x + dx, a.y + dy
                if self.free(nx, ny) and cheb(nx, ny, a.home[0], a.home[1]) <= 4 and A.tile(nx, ny) in (T_ROAD, T_GRASS):
                    a.x, a.y = nx, ny
        self.search_traps()
        if self.steps % 180 == 0 and len(self.party) > 1:
            p = random.choice(self.party[1:])
            if p.conscious and p.cid in BANTER:
                self.msg(random.choice(BANTER[p.cid]), PARTY_COLS[p.pcol % 5])
        self.check_hostiles()

    def search_traps(self):
        rogue = next((p for p in self.able() if p.cls == "rogue"), None)
        best = max((p.m("WIS") + 10 for p in self.able()), default=10)
        if rogue:
            best = max(best, 10 + rogue.m("DEX") + rogue.prof * 2)
        for pos, tr in self.area.traps.items():
            if tr["hidden"] and cheb(pos[0], pos[1], self.leader.x, self.leader.y) <= 3 and pos in self.visible:
                if best + random.randint(-3, 3) >= 15:
                    tr["hidden"] = False
                    who = rogue.name if rogue else "Someone"
                    self.msg("%s spots a trap! (marked ^)" % who, YELLOW)

    def check_hostiles(self):
        if self.combat or self.over:
            return
        A = self.area
        for a in A.actors:
            if a.faction != "hostile" or not a.conscious or "asleep" in a.status or getattr(a, "truce", 0) > self.steps:
                continue
            if self.sees(a) and min(cheb(a.x, a.y, p.x, p.y) for p in self.able()) <= self.light_radius() + 1:
                if a.npc and not self.flags.get("talked_" + a.npc):
                    self.flags["talked_" + a.npc] = True
                    self.pending.append(("talk", a.npc))
                    return
                self.start_combat()
                return

    # --- resting, shops, temple ------------------------------------------------
    def can_rest(self):
        if self.combat:
            return "You cannot rest in the middle of a fight!"
        if self.area.id in ("sanctum", "lair"):
            return "This place is too evil to rest in."
        for a in self.area.actors:
            if a.faction == "hostile" and a.conscious and (self.sees(a) or cheb(a.x, a.y, self.leader.x, self.leader.y) < 10):
                return "You cannot rest - there are enemies nearby."
        if self.area.kind == "town":
            return "Sleeping in the street? Hobb rents rooms at the Rusty Lantern."
        return None

    def rest(self, safe=False):
        if not safe:
            why = self.can_rest()
            if why:
                self.msg(why, GRAY)
                return False
            if random.random() < self.D["ambush"]:
                self.minutes += 120
                self.ambush()
                return False
        for p in self.party:
            if not p.dead:
                p.rest()
        self.minutes += 8 * 60
        self.msg("You rest for eight hours. Wounds close, spells return.", GREEN)
        return True

    def ambush(self):
        A = self.area
        pool = {"forest": ["wolf", "wolf", "wolf"], "road": ["wolf", "wolf"], "mine1": ["kobold", "kobold", "kobold_slinger"],
                "mine2": ["skeleton", "zombie", "skeleton"], "cellar": ["rat", "rat"]}.get(A.id, ["bandit", "bandit"])
        L = self.leader
        rings = [p for p in bfs_dist(A, [(L.x, L.y)], limit=7) if cheb(p[0], p[1], L.x, L.y) >= 4 and self.free(*p)]
        random.shuffle(rings)
        self.msg("Your rest is interrupted! Something is coming...", RED)
        for k, pos in zip(pool, rings):
            m = make_monster(k, *pos)
            m.alerted = True
            A.actors.append(m)
        self.update_fov()
        self.start_combat(force=[a for a in A.actors if a.alerted and a.conscious])

    def inn_rest(self):
        if self.gold < 10:
            return False
        self.gold -= 10
        for p in self.party:
            if not p.dead:
                p.rest()
        h = (self.minutes % 1440)
        self.minutes += (1440 - h) + 7 * 60 if h > 7 * 60 else (7 * 60 - h)
        self.msg("You sleep at the Rusty Lantern. (-10 gold)", GREEN)
        return True

    def buy(self, it):
        p = ITEMS[it]["price"]
        if self.gold < p:
            self.msg("Not enough gold.", GRAY)
            return False
        self.gold -= p
        self.bag.append(it)
        self.msg("Bought %s for %d gold." % (ITEMS[it]["name"], p), GOLD)
        return True

    def sell(self, idx):
        it = self.bag[idx]
        if ITEMS[it]["kind"] == "quest":
            self.msg("You can't sell that.", GRAY)
            return False
        p = ITEMS[it]["price"] // 2
        self.gold += p
        self.bag.pop(idx)
        self.msg("Sold %s for %d gold." % (ITEMS[it]["name"], p), GOLD)
        return True

    def temple_heal(self):
        if self.gold < 20:
            return False
        self.gold -= 20
        for p in self.party:
            if not p.dead:
                p.hp = p.max_hp
                p.status = {}
        self.msg("Father Aldous lays his hands on each of you. (-20 gold)", GREEN)
        return True

    def temple_raise(self):
        dead = [p for p in self.party if p.dead]
        if not dead or self.gold < self.raise_cost:
            return False
        p = dead[0]
        self.gold -= self.raise_cost
        L = self.leader
        p.dead, p.hp, p.dsaves = False, 1, [0, 0]
        spot = self.free_near(L.x, L.y, 1) or self.free_near(*list(self.area.entries.values())[0], 1)
        p.x, p.y = spot[0] if spot else (L.x, L.y)
        self.trail.clear()
        self.msg("%s gasps, alive again. (-%d gold)" % (p.name, self.raise_cost), GREEN)
        return True

    # --- equipment -------------------------------------------------------------
    def can_equip(self, p, it):
        d = ITEMS[it]
        c = CLASSES[p.cls]
        if d["kind"] == "armor":
            if d["cat"] == "none" or d["cat"] in c["armors"]:
                return None
            return "%s can't wear %s armour." % (c["name"] + "s", d["cat"])
        if d["kind"] == "shield" and not c["shields"]:
            return "%ss don't use shields." % c["name"]
        if d["kind"] == "weapon" and p.cls == "wizard" and not p.proficient(d):
            return "Wizards fight with staves, daggers and crossbows."
        return None

    def equip(self, p, idx):
        it = self.bag[idx]
        d = ITEMS[it]
        slot = {"weapon": "weapon", "armor": "armor", "shield": "shield", "ring": "ring", "amulet": "amulet"}.get(d["kind"])
        if not slot:
            return False
        why = self.can_equip(p, it)
        if why:
            self.msg(why, GRAY)
            return False
        self.bag.pop(idx)
        old = p.equip.get(slot)
        if old:
            self.bag.append(old)
        p.equip[slot] = it
        p.recompute()
        self.msg("%s equips %s." % (p.name, d["name"]), LIGHT)
        if self.combat and self.current() is p:
            p.acted = True
        return True

    def unequip(self, p, slot):
        it = p.equip.get(slot)
        if not it:
            return False
        self.bag.append(it)
        p.equip[slot] = None
        p.recompute()
        return True

    def use_item(self, user, idx, target=None):
        it = self.bag[idx]
        d = ITEMS[it]
        target = target or user
        if d["kind"] == "potion":
            if target.dead:
                return False
            n = roll(d["heal"])
            self.bag.pop(idx)
            self.heal(target, n)
            self.msg("%s drinks %s and recovers %d HP." % (target.name, d["name"], n), GREEN)
            return True
        return False

    # --- party management -------------------------------------------------------
    def recruit(self, cid):
        if len(self.party) >= 4:
            return False
        A = self.area
        npc = next((a for a in A.actors if a.npc == cid), None)
        if cid in self.waiting:
            p = Actor.from_dict(self.waiting.pop(cid))
        else:
            p = make_companion(cid, self.leader.level, 0)
        used = {q.pcol for q in self.party}
        p.pcol = next(i for i in range(1, 5) if i not in used)
        p.fg = PARTY_COLS[p.pcol]
        p.faction, p.is_pc = "party", True
        if npc:
            A.actors.remove(npc)
            p.x, p.y = npc.x, npc.y
        else:
            spot = self.free_near(self.leader.x, self.leader.y, 1)
            p.x, p.y = spot[0] if spot else (self.leader.x, self.leader.y)
        p.status, p.ai = {}, False
        self.party.append(p)
        self.msg("%s joins the party." % p.name, GREEN)
        self.flags["recruited_" + cid] = True
        return True

    def dismiss(self, p):
        if p is self.hero or p.dead or self.combat:
            return False
        self.party.remove(p)
        p.status = {}
        self.waiting[p.cid] = p.to_dict()
        town = self.areas.get("town")
        home = COMP_HOME[p.cid]
        npc = make_npc(p.cid, p.name, home[1], home[2], portrait=p.cid)
        if town:
            town.actors.append(npc)
        self.msg("%s leaves the party. \"I'll wait at the Rusty Lantern.\"" % p.name, GRAY)
        return True

    # --- XP and levels ---------------------------------------------------------------
    def award_xp(self, xp, quiet=False):
        live = self.living()
        if not live:
            return
        share = max(1, 2 * xp // len(live))
        if not quiet:
            self.msg("Each party member gains %d experience." % share, GOLD)
        for p in live:
            p.xp += share
            while p.level < MAX_LEVEL and p.xp >= XP_LEVELS[p.level + 1]:
                p.level += 1
                old_hp = p.max_hp
                p.recompute()
                gains = ["+%d max HP" % (p.max_hp - old_hp)]
                new_sp = [SPELLS[s]["name"] for s in CLASS_SPELLS.get(p.cls, {}).get(p.level, [])]
                if new_sp:
                    gains.append("new: " + ", ".join(new_sp))
                if p.can_cast and SLOTS.get(p.level):
                    gains.append("spell slots " + " ".join("L%s:%d" % (k, v) for k, v in sorted(SLOTS[p.level].items())))
                if p.cls == "fighter" and p.level == 3:
                    gains.append("criticals on 19-20")
                if p.cls == "fighter" and p.level == 5:
                    gains.append("Extra Attack")
                if p.cls == "rogue" and p.level in (3, 5):
                    gains.append("Sneak Attack %dd6" % p.sneak_dice)
                if p.prof != 2 + (p.level - 2) // 4:
                    gains.append("proficiency +%d" % p.prof)
                self.msg("%s reaches level %d!" % (p.name, p.level), YELLOW)
                self.pending.append(("levelup", p.name, p.level, gains))

    # =============================================================================
    # Combat
    # =============================================================================
    def start_combat(self, force=()):
        if self.combat or self.over:
            return
        A = self.area
        eng = set(force)
        for a in A.actors:
            if a.faction == "hostile" and a.conscious and self.sees(a) and getattr(a, "truce", 0) <= self.steps:
                if min(cheb(a.x, a.y, p.x, p.y) for p in self.living()) <= self.light_radius() + 2:
                    eng.add(a)
        # alert friends close to anyone engaged
        changed = True
        while changed:
            changed = False
            for a in A.actors:
                if a.faction == "hostile" and a.conscious and a not in eng:
                    if any(cheb(a.x, a.y, e.x, e.y) <= 6 and los(A, a.x, a.y, e.x, e.y) for e in eng):
                        eng.add(a)
                        changed = True
        if not eng:
            return
        for e in sorted(eng, key=lambda a: a.name):
            if e.tmpl in BESTIARY and not self.flags.get("seen_" + e.tmpl):
                self.flags["seen_" + e.tmpl] = True
                self.pending.append(("message", e.T["name"], BESTIARY[e.tmpl], e.tmpl))
        surprise = self.flags.pop("surprise", False)
        order = []
        for a in list(self.living()) + list(eng):
            a.engaged = True if a.faction == "hostile" else a.engaged
            ini = d20() + a.m("DEX") + (10 if surprise and a.is_pc else 0)
            order.append((ini, random.random(), a))
        order.sort(key=lambda t: (-t[0], t[1]))
        self.combat = {"order": [t[2] for t in order], "idx": 0, "round": 1}
        names = ", ".join(sorted({e.name for e in eng}))
        self.msg("Combat! %s" % names, RED)
        self.msg("Initiative: " + " > ".join("%s %d" % (t[2].name.split()[0], t[0]) for t in order), GRAY)
        self.begin_turn()

    def current(self):
        c = self.combat
        if not c:
            return None
        return c["order"][c["idx"]]

    def hostiles(self):
        return [a for a in self.area.actors if a.faction == "hostile" and a.conscious and a.engaged]

    def needs_input(self):
        a = self.current()
        return (a is not None and a.is_pc and not a.ai and a.conscious and
                not self.incapacitated(a))

    @staticmethod
    def incapacitated(a):
        return "asleep" in a.status or "paralyzed" in a.status

    def begin_turn(self):
        a = self.current()
        a.mp, a.acted = a.speed, False
        a.sneak_used = False
        if a.tmpl and a.T.get("breath") and not a.recharge and random.randint(1, 6) >= 5:
            a.recharge = True
            self.msg("%s's throat glows with gathering fire!" % a.name, ORANGE)

    def end_turn(self):
        c = self.combat
        if not c:
            return
        a = self.current()
        for st in list(a.status):
            v = a.status[st]
            if st == "paralyzed":
                if d20() + a.save_bonus("WIS") >= v.get("dc", 10):
                    del a.status[st]
                    self.msg("%s breaks free of the paralysis." % a.name, GRAY)
                    continue
            v["rounds"] -= 1
            if v["rounds"] <= 0:
                del a.status[st]
                if st == "asleep":
                    self.msg("%s wakes up." % a.name, GRAY)
        if self.check_combat_end():
            return
        n = len(c["order"])
        for _ in range(n + 1):
            c["idx"] += 1
            if c["idx"] >= len(c["order"]):
                c["idx"] = 0
                c["round"] += 1
                self.join_new()
            nxt = c["order"][c["idx"]]
            if not nxt.dead and (nxt.conscious or nxt.downed) and (nxt.is_pc or nxt in self.area.actors):
                break
        self.begin_turn()

    def join_new(self):
        c = self.combat
        r = self.light_radius() + 6
        for a in self.area.actors:
            if a.engaged and a.faction == "hostile" and not self.sees(a):
                if min([cheb(a.x, a.y, p.x, p.y) for p in self.able()] or [99]) > r:
                    a.engaged = False
        if c["round"] > 80:  # a stalemate: everyone breaks off and leaves the other side alone for a while
            for a in self.area.actors:
                if a.engaged and a.faction == "hostile":
                    a.truce = self.steps + 300
                a.engaged = False
            return
        for a in self.area.actors:
            if a.faction == "hostile" and a.conscious and not a.engaged and self.sees(a) and getattr(a, "truce", 0) <= self.steps:
                a.engaged = True
                if a not in c["order"]:
                    c["order"].append(a)
                    self.msg("%s joins the fight!" % a.name, RED)

    def check_combat_end(self):
        if not self.combat:
            return True
        if not self.able():
            self.game_over()
            return True
        if not self.hostiles():
            self.end_combat()
            return True
        return False

    def end_combat(self):
        self.combat = None
        for a in self.area.actors:
            a.engaged = False
        for p in self.party:
            if p.downed:
                p.hp, p.dsaves = 1, [0, 0]
                self.msg("%s staggers back to their feet." % p.name, GREEN)
            for st in ("asleep", "paralyzed", "frightened"):
                p.status.pop(st, None)
        self.msg("The fight is over.", CYAN)
        self.update_fov()
        if self.flags.get("ashmaw_dead") and not self.over:
            self.over = "won"
            self.pending.append(("victory",))
        self.check_hostiles()

    def game_over(self):
        self.combat = None
        if self.over:
            return
        self.over = "dead"
        self.pending.append(("gameover",))

    # --- turn actions for the current PC ------------------------------------------
    def combat_move(self, dx, dy):
        a = self.current()
        if not self.needs_input():
            return
        nx, ny = a.x + dx, a.y + dy
        o = self.actor_at(nx, ny)
        if o and o.faction == "hostile":
            self.pc_attack(a, o)
            return
        if a.mp <= 0:
            self.msg("%s has no movement left. (Space ends the turn)" % a.name, GRAY)
            return
        t = self.area.tile(nx, ny)
        if t == T_DOOR:
            self.area.set(nx, ny, T_ODOOR)
            a.mp -= 1
            self.update_fov()
            return
        if o or not self.area.walkable(nx, ny):
            return
        a.x, a.y = nx, ny
        a.mp -= 1
        tr = self.area.traps.get((nx, ny))
        if tr:
            self.arrived_on(a)
        self.update_fov()
        self.join_new()
        self.auto_end(a)

    def auto_end(self, a):
        if self.combat and self.current() is a and a.acted and a.mp <= 0:
            self.end_turn()

    def targets_for(self, a, rng, enemies=True):
        if enemies:
            pool = [e for e in self.hostiles() if self.sees(e)]
        else:
            pool = [p for p in self.party if not p.dead]
        out = []
        for t in pool:
            d = cheb(a.x, a.y, t.x, t.y)
            if d <= rng and (d <= 1 or los(self.area, a.x, a.y, t.x, t.y)):
                out.append(t)
        out.sort(key=lambda t: (cheb(a.x, a.y, t.x, t.y), t.hp))
        return out

    def pc_attack(self, a, t):
        if a.acted:
            self.msg("%s has already acted this turn." % a.name, GRAY)
            return False
        w = a.weapon
        d = cheb(a.x, a.y, t.x, t.y)
        rng = w.get("ranged", 1)
        if d > rng:
            self.msg("Out of range.", GRAY)
            return False
        if d > 1 and not los(self.area, a.x, a.y, t.x, t.y):
            self.msg("No clear line of sight.", GRAY)
            return False
        a.acted = True
        for i in range(a.attacks_per_turn):
            if not t.conscious:
                nxt = [e for e in self.targets_for(a, rng)]
                if not nxt:
                    break
                t = nxt[0]
            spec = dict(name=w["name"], bonus=a.attack_bonus(w), dmg=w["dmg"], dbonus=a.damage_bonus(w),
                        dtype=w["dtype"], range=rng, crit=a.crit_range, extra=w.get("extra"), extra_vs=w.get("extra_vs"),
                        finesse=w.get("finesse") or bool(w.get("ranged")))
            self.resolve_attack(a, t, spec)
        self.auto_end(a)
        return True

    def d20_roll(self, a, adv, dis):
        r1, r2 = d20(), d20()
        if adv and not dis:
            r = max(r1, r2)
        elif dis and not adv:
            r = min(r1, r2)
        else:
            r = r1
        if r == 1 and a.race == "halfling":
            r = d20()
        return r

    def adv_dis(self, a, t, ranged):
        adv = dis = False
        why = []
        if self.incapacitated(t):
            adv = True
        if a.tmpl and a.T.get("pack"):
            if any(o is not a and o.faction == a.faction and o.conscious and cheb(o.x, o.y, t.x, t.y) <= 1 for o in self.area.actors):
                adv = True
                why.append("pack")
        if "frightened" in a.status or "poisoned" in a.status:
            dis = True
        if ranged:
            foes = self.party if a.faction == "hostile" else self.hostiles()
            if any(f.conscious and cheb(f.x, f.y, a.x, a.y) <= 1 for f in foes):
                dis = True
                why.append("close")
        return adv, dis

    def flanked(self, a, t):
        return any(p is not a and p.conscious and cheb(p.x, p.y, t.x, t.y) <= 1
                   for p in (self.party if a.is_pc else self.area.actors))

    def resolve_attack(self, a, t, spec):
        ranged = spec["range"] > 1
        adv, dis = self.adv_dis(a, t, ranged)
        r = self.d20_roll(a, adv, dis)
        bless = roll("1d4") if "bless" in a.status else 0
        total = r + spec["bonus"] + bless
        crit = r >= spec.get("crit", 20)
        hit = crit or (r != 1 and total >= t.ac)
        if ranged:
            self.events.append(("bolt", line(a.x, a.y, t.x, t.y), "*" if not a.is_pc else "-", WHITE if hit else GRAY))
        tag = " (adv)" if adv and not dis else (" (dis)" if dis and not adv else "")
        col_att = ORANGE if a.faction == "hostile" else LIGHT
        if not hit:
            self.msg("%s attacks %s with %s: %d%s vs AC %d - miss." % (a.name, t.name, spec["name"], total, tag, t.ac), GRAY)
            self.events.append(("text", t.x, t.y, "miss", GRAY))
            return False
        if self.incapacitated(t) and not ranged:
            crit = True
        dmg = roll(spec["dmg"], crit) + spec.get("dbonus", 0)
        extra_txt = ""
        if a.sneak_dice and spec.get("finesse") and not getattr(a, "sneak_used", False) and (
                (adv and not dis) or self.flanked(a, t)):
            sd = roll("%dd6" % a.sneak_dice, crit)
            dmg += sd
            a.sneak_used = True
            extra_txt = " +%d sneak" % sd
        self.msg("%s %s %s with %s: %d%s vs AC %d - %s %d%s." % (
            a.name, "CRITS" if crit else "hits", t.name, spec["name"], total, tag, t.ac,
            "for", dmg, extra_txt), YELLOW if crit else col_att)
        self.damage(t, dmg, spec["dtype"], a, crit)
        ex = spec.get("extra")
        if ex and t.conscious and (not spec.get("extra_vs") or t.has_tag(spec["extra_vs"])):
            self.damage(t, roll(ex[0], crit), ex[1], a)
        rider = spec.get("rider")
        if rider and (t.conscious or t.downed) and not t.dead:
            kind = rider[0]
            if kind == "fire":
                self.damage(t, roll(rider[1], crit), "fire", a)
            elif kind == "poison" and t.conscious:
                sv = d20() + t.save_bonus(rider[2])
                n = roll(rider[1])
                if sv >= rider[3]:
                    n //= 2
                self.msg("Venom burns in %s's veins (%s save %d vs DC %d)." % (t.name, rider[2], sv, rider[3]), PURPLE)
                self.damage(t, n, "poison", a)
            elif kind == "paralyze" and t.conscious:
                if t.race == "elf":
                    self.msg("%s's elven blood shrugs off the ghoul's touch." % t.name, GRAY)
                else:
                    sv = d20() + t.save_bonus(rider[1])
                    if sv < rider[2]:
                        t.status["paralyzed"] = {"rounds": 3, "dc": rider[2]}
                        self.msg("%s is paralysed! (CON save %d vs DC %d)" % (t.name, sv, rider[2]), PURPLE)
        return True

    def heal(self, t, n):
        if t.dead:
            return
        was_down = t.hp <= 0
        t.hp = min(t.max_hp, max(0, t.hp) + n)
        t.dsaves = [0, 0]
        self.events.append(("text", t.x, t.y, "+%d" % n, LGREEN))
        if was_down and t.hp > 0:
            self.msg("%s is back on their feet!" % t.name, GREEN)

    def damage(self, t, n, dtype, src=None, crit=False):
        if t.dead or (not t.is_pc and not t.tmpl):  # townsfolk and captives are not part of the fight
            return 0
        if t.immune(dtype):
            self.msg("%s is immune to %s." % (t.name, dtype), GRAY)
            self.events.append(("text", t.x, t.y, "immune", GRAY))
            return 0
        if t.resists(dtype):
            n //= 2
        if t.vulnerable(dtype):
            n *= 2
        if n > 0:
            n = max(1, int(n * (self.D["taken"] if t.is_pc else self.D["dealt"]) + 0.5))
        t.status.pop("asleep", None)
        self.events.append(("text", t.x, t.y, "-%d" % n, RED if t.is_pc else YELLOW))
        if t.is_pc:
            if t.hp <= 0:
                t.dsaves[1] += 2 if crit else 1
                self.msg("%s is struck while down!" % t.name, RED)
                if t.dsaves[1] >= 3:
                    self.die(t)
                return n
            t.hp -= n
            if t.hp <= 0:
                if True:
                    t.hp = 0
                    t.dsaves = [0, 0]
                    t.status = {}
                    self.msg("%s falls unconscious!" % t.name, RED)
                    if not self.able():
                        self.game_over()
            return n
        if t.T.get("fortitude") and t.hp - n <= 0 < t.hp and dtype != "radiant" and not crit:
            sv = d20() + t.m("CON")
            if sv >= 5 + n:
                t.hp = 1
                self.msg("%s refuses to fall! (undead fortitude)" % t.name, MOSS)
                return n
        t.hp -= n
        if t.hp <= 0:
            self.kill(t, src)
        return n

    def die(self, p):
        p.dead, p.hp = True, 0
        p.status = {}
        self.area.decals[(p.x, p.y)] = ("%", 0)
        self.msg("%s has died." % p.name, RED)
        if not self.able():
            self.game_over()
        elif p is self.hero:
            self.msg("Your companions take up %s's body. Father Aldous in Emberfall can still bring the hero back "
                     "- for %d gold." % (p.name, self.raise_cost), YELLOW)

    def kill(self, t, src=None):
        t.dead = True
        t.hp = 0
        b = self.flags.get("sq_bounty")
        if b and t.tmpl == b["mon"] and self.qstate("bounty") == "active" and b["have"] < b["need"]:
            b["have"] += 1
            self.msg("Bounty: %d of %d %s." % (b["have"], b["need"], b["what"]), YELLOW)
        A = self.area
        if t in A.actors:
            A.actors.remove(t)
        self.kills += 1
        A.decals[(t.x, t.y)] = ("%", 2 if t.has_tag("undead") else 0)
        self.events.append(("burst", [(t.x, t.y)], RED))
        self.msg("%s is slain!" % t.name, ORANGE)
        T = t.T
        g = T.get("gold", 0)
        if g:
            n = roll(g)
            if n:
                A.add_item(t.x, t.y, "gold:%d" % n)
        for it, pct in T.get("loot", []):
            if random.randint(1, 100) <= pct:
                A.add_item(t.x, t.y, it)
        self.award_xp(T["xp"])
        if t.tmpl == "snagtooth":
            self.flags["snagtooth_dead"] = True
        if t.tmpl == "corvane":
            self.flags["corvane_dead"] = True
            for y in range(A.h):
                for x in range(A.w):
                    if A.tiles[y][x] == T_SEAL:
                        A.tiles[y][x] = T_STONEFL
            self.msg("As Corvane falls, the pale seal shatters like ice. Deep below, something laughs.", MAGENTA)
            self.events.append(("shake",))
            if self.qstate("miners") == "active":
                self.quest("miners", "Magister Corvane is dead and his seal is broken. The way down to the dragon "
                                     "Ashmaw lies open. It must not leave that mountain.")
        if t.tmpl == "ashmaw":
            self.flags["ashmaw_dead"] = True
            self.events.append(("shake",))
            if self.qstate("miners"):
                self.quest("miners", "Ashmaw is slain. Emberfall is saved.", "done")
        if A.id == "cellar" and not any(a.tmpl == "rat" for a in A.actors) and not self.flags.get("rats_cleared"):
            self.flags["rats_cleared"] = True
            if self.qstate("rats") == "active":
                self.quest("rats", "The cellar is free of rats. Time to tell Hobb.")

    def death_save(self, p):
        if p.dsaves[0] >= 3:
            return
        r = d20()
        if r == 20:
            p.hp = 1
            p.dsaves = [0, 0]
            self.msg("%s rolls a 20 on a death save and rises!" % p.name, GREEN)
        elif r == 1:
            p.dsaves[1] += 2
            self.msg("%s's death save: 1! Two failures." % p.name, RED)
        elif r >= 10:
            p.dsaves[0] += 1
            self.msg("%s's death save: %d - success (%d/3)." % (p.name, r, p.dsaves[0]), GRAY)
            if p.dsaves[0] >= 3:
                self.msg("%s is stable." % p.name, GRAY)
        else:
            p.dsaves[1] += 1
            self.msg("%s's death save: %d - failure (%d/3)." % (p.name, r, p.dsaves[1]), RED)
        if p.dsaves[1] >= 3:
            self.die(p)

    # --- spells ---------------------------------------------------------------------
    def spell_list(self, a):
        """Spells the actor could cast now: [(id, ok, why)]."""
        out = []
        for s in a.spells:
            sp = SPELLS[s]
            ok, why = True, ""
            if sp["lvl"] > 0 and not a.slot_ok(sp["lvl"]):
                ok, why = False, "no level %d slots" % sp["lvl"]
            if s == "turn_undead" and a.uses.get("turn_undead"):
                ok, why = False, "used"
            out.append((s, ok, why))
        if a.cls == "fighter":
            out.append(("second_wind", not a.uses.get("second_wind"), "used" if a.uses.get("second_wind") else ""))
        return out

    def cone(self, a, tx, ty, length):
        ang = math.atan2(ty - a.y, tx - a.x)
        out = []
        for y in range(a.y - length, a.y + length + 1):
            for x in range(a.x - length, a.x + length + 1):
                if (x, y) == (a.x, a.y) or cheb(x, y, a.x, a.y) > length:
                    continue
                d = math.atan2(y - a.y, x - a.x) - ang
                d = (d + math.pi) % (2 * math.pi) - math.pi
                if abs(d) <= math.pi / 4 + 0.01 and self.area.seethru(x, y) and los(self.area, a.x, a.y, x, y):
                    out.append((x, y))
        return out

    def ball(self, cx, cy, r):
        return [(x, y) for y in range(cy - r, cy + r + 1) for x in range(cx - r, cx + r + 1)
                if self.area.inb(x, y) and cheb(x, y, cx, cy) <= r and los(self.area, cx, cy, x, y)]

    def actors_in(self, cells):
        cs = set(cells)
        return [o for o in self.all_actors() if (o.x, o.y) in cs and (o.conscious or o.downed)]

    def cast(self, a, sid, t=None, scroll=False):
        """Cast a spell. t is the target actor (or None for self spells)."""
        if sid == "second_wind":
            a.uses["second_wind"] = True
            n = roll("1d10") + a.level
            self.heal(a, n)
            self.msg("%s catches a second wind (+%d HP)." % (a.name, n), GREEN)
            a.acted = True
            self.auto_end(a)
            return True
        sp = SPELLS[sid]
        lvl = sp["lvl"]
        if not scroll:
            if a.tmpl:
                if a.mslots.get(sid, 0) <= 0 and MONSTERS[a.tmpl]["spells"].get(sid, 0) != 0:
                    return False
                if MONSTERS[a.tmpl]["spells"].get(sid, 0) != 0:
                    a.mslots[sid] -= 1
            elif lvl > 0:
                if not a.slot_ok(lvl):
                    self.msg("No spell slots of level %d left." % lvl, GRAY)
                    return False
                a.use_slot(lvl)
        if sid == "turn_undead":
            a.uses["turn_undead"] = True
        if self.combat and self.current() is a:
            a.acted = True
        k = sp["kind"]
        col = PALE if a.faction == "hostile" else CYAN
        self.msg("%s casts %s%s." % (a.name, sp["name"], (" at " + t.name) if t and t is not a else ""), col)
        cdice = 1
        if sp["lvl"] == 0:
            cdice = 2 if (a.is_pc and a.level >= 5) else (a.T.get("cantrip_dice", 1) if a.tmpl else 1)
        fire_col = PALE if a.faction == "hostile" else ORANGE
        if k == "attack":
            dmg = sp["dmg"]
            if cdice > 1:
                n, s = dmg.split("d")
                dmg = "%dd%s" % (int(n) * cdice, s)
            spec = dict(name=sp["name"], bonus=a.spell_atk, dmg=dmg, dbonus=0, dtype=sp["dtype"], range=max(2, sp["range"]))
            self.events.append(("bolt", line(a.x, a.y, t.x, t.y), "*", fire_col if sp["dtype"] == "fire" else YELLOW))
            self.resolve_attack(a, t, spec)
        elif k == "missile":
            for i in range(3):
                if not t.conscious:
                    break
                self.events.append(("bolt", line(a.x, a.y, t.x, t.y), "*", MAGENTA))
                self.damage(t, roll("1d4+1"), "force", a)
            self.msg("Three darts of force strike %s." % t.name, MAGENTA)
        elif k == "rays":
            for i in range(3):
                if not t.conscious:
                    alt = [e for e in (self.hostiles() if a.is_pc else self.able()) if los(self.area, a.x, a.y, e.x, e.y)]
                    if not alt:
                        break
                    t = alt[0]
                self.events.append(("bolt", line(a.x, a.y, t.x, t.y), "~", fire_col))
                self.resolve_attack(a, t, dict(name="ray", bonus=a.spell_atk, dmg=sp["dmg"], dbonus=0, dtype="fire", range=20))
        elif k == "save":
            dmg = sp["dmg"]
            if cdice > 1:
                n, s = dmg.split("d")
                dmg = "%dd%s" % (int(n) * cdice, s)
            self.events.append(("burst", [(t.x, t.y)], fire_col if sp["dtype"] == "fire" else YELLOW))
            sv = d20() + t.save_bonus(sp["save"]) + (roll("1d4") if "bless" in t.status else 0)
            if sv >= a.spell_dc:
                self.msg("%s dodges the flame (%s save %d vs DC %d)." % (t.name, sp["save"], sv, a.spell_dc), GRAY)
            else:
                self.damage(t, roll(dmg), sp["dtype"], a)
        elif k in ("cone", "ball"):
            cells = self.cone(a, t.x, t.y, sp["range"]) if k == "cone" else self.ball(t.x, t.y, sp["radius"])
            self.events.append(("burst", cells, fire_col))
            for o in self.actors_in(cells):
                if o is a:
                    continue
                sv = d20() + o.save_bonus(sp["save"]) + (roll("1d4") if "bless" in o.status else 0)
                n = roll(sp["dmg"])
                if sv >= a.spell_dc:
                    n //= 2
                if o.faction == a.faction:
                    self.msg("%s is caught in the blast!" % o.name, RED)
                self.damage(o, n, sp["dtype"], a)
        elif k == "sleep":
            pool = roll("5d8")
            cells = self.ball(t.x, t.y, sp["radius"])
            foes = [o for o in self.actors_in(cells) if o.faction != a.faction and o.conscious and not o.has_tag("undead")
                    and not o.has_tag("dragon") and o.race != "elf"]
            foes.sort(key=lambda o: o.hp)
            self.events.append(("burst", cells, PURPLE))
            n = 0
            for o in foes:
                if o.hp > pool:
                    break
                pool -= o.hp
                o.status["asleep"] = {"rounds": 10}
                n += 1
                self.events.append(("text", o.x, o.y, "zZz", PURPLE))
            self.msg("%d creature%s fall%s asleep." % (n, "" if n == 1 else "s", "s" if n == 1 else ""), PURPLE)
        elif k == "heal":
            n = roll(sp["heal"]) + a.m(a.cast_stat)
            self.events.append(("burst", [(t.x, t.y)], LGREEN))
            self.heal(t, n)
            self.msg("%s recovers %d HP." % (t.name, n), GREEN)
        elif k == "massheal":
            for p in self.party:
                if not p.dead and cheb(p.x, p.y, a.x, a.y) <= sp["range"]:
                    n = roll(sp["heal"]) + a.m(a.cast_stat)
                    self.heal(p, n)
            self.events.append(("burst", self.ball(a.x, a.y, 2), LGREEN))
        elif k == "bless":
            allies = sorted([p for p in self.party if p.conscious and cheb(p.x, p.y, a.x, a.y) <= sp["range"]],
                            key=lambda p: (p is not a, cheb(p.x, p.y, a.x, a.y)))[:3]
            for p in allies:
                p.status["bless"] = {"rounds": 10}
                self.events.append(("text", p.x, p.y, "+", GOLD))
            self.msg("A warm light settles on %s." % ", ".join(p.name.split()[-1] if p.name.split()[0] in ("Sister", "Father") else p.name.split()[0] for p in allies), GOLD)
        elif k == "turn":
            cells = self.ball(a.x, a.y, sp["range"])
            self.events.append(("burst", cells, GOLD))
            for o in self.actors_in(cells):
                if o.has_tag("undead") and o.conscious:
                    sv = d20() + o.save_bonus("WIS")
                    if sv < a.spell_dc:
                        o.status["frightened"] = {"rounds": 10}
                        self.msg("%s flees from the holy light!" % o.name, GOLD)
        elif k == "hold":
            if not (t.has_tag("humanoid") or t.is_pc):
                self.msg("%s is not a humanoid - the spell fizzles." % t.name, GRAY)
            else:
                self.events.append(("burst", [(t.x, t.y)], PURPLE))
                sv = d20() + t.save_bonus("WIS") + (roll("1d4") if "bless" in t.status else 0)
                if sv >= a.spell_dc:
                    self.msg("%s resists (WIS save %d vs DC %d)." % (t.name, sv, a.spell_dc), GRAY)
                else:
                    t.status["paralyzed"] = {"rounds": 10, "dc": a.spell_dc}
                    self.msg("%s is held fast! (WIS save %d vs DC %d)" % (t.name, sv, a.spell_dc), PURPLE)
        if self.combat:
            self.auto_end(a)
        return True

    def breath(self, a, tx, ty):
        b = a.T["breath"]
        cells = self.cone(a, tx, ty, 4)
        a.recharge = False
        self.msg("%s breathes a torrent of fire!" % a.name, ORANGE)
        self.events.append(("burst", cells, ORANGE))
        self.events.append(("shake",))
        for o in self.actors_in(cells):
            if o is a:
                continue
            sv = d20() + o.save_bonus(b[2]) + (roll("1d4") if "bless" in o.status else 0)
            n = roll(b[0])
            if sv >= b[3]:
                n //= 2
            self.damage(o, n, b[1], a)

    # --- AI ------------------------------------------------------------------------
    def step_ai(self):
        a = self.current()
        if a is None:
            return
        if a.downed:
            self.death_save(a)
        elif not a.conscious:
            pass
        elif self.incapacitated(a):
            self.msg("%s is %s." % (a.name, "asleep" if "asleep" in a.status else "paralysed"), GRAY)
        elif a.faction == "hostile":
            self.monster_ai(a)
        else:
            self.pc_ai(a)
        if self.combat and self.current() is a:
            self.end_turn()

    def melee_attacks(self, m):
        mel = [x for x in m.T["attacks"] if x[4] <= 1]
        n = m.T.get("multi", 1)
        if len(mel) >= n and n > 1:
            return mel[:n]
        return [mel[0]] * n if mel else []

    def m_attack(self, m, t, atk):
        spec = dict(name=atk[0], bonus=atk[1], dmg=atk[2], dbonus=0, dtype=atk[3], range=atk[4], rider=atk[5])
        self.reveal(m)
        self.resolve_attack(m, t, spec)

    def monster_ai(self, m):
        A = self.area
        targets = [p for p in self.party if p.conscious] or [p for p in self.party if p.downed]
        if not targets:
            return
        if "frightened" in m.status:
            best = max(DIRS8, key=lambda d: min(cheb(m.x + d[0], m.y + d[1], p.x, p.y) for p in targets)
                       if self.free(m.x + d[0], m.y + d[1]) else -1)
            for _ in range(m.speed // 2):
                nx, ny = m.x + best[0], m.y + best[1]
                if self.free(nx, ny):
                    m.x, m.y = nx, ny
            return
        # dragon breath
        if m.T.get("breath") and m.recharge:
            best, bn = None, 0
            for p in targets:
                if cheb(m.x, m.y, p.x, p.y) <= 4 and los(A, m.x, m.y, p.x, p.y):
                    n = sum(1 for o in self.actors_in(self.cone(m, p.x, p.y, 4)) if o.is_pc)
                    if n > bn:
                        best, bn = p, n
            if best and (bn >= 2 or random.random() < 0.5):
                self.breath(m, best.x, best.y)
                return
        # spellcasters
        if m.mslots or m.T.get("spells"):
            if self.monster_cast(m, targets):
                return
        adj = [p for p in targets if cheb(m.x, m.y, p.x, p.y) <= 1]
        ranged = [x for x in m.T["attacks"] if x[4] > 1]
        if ranged and not adj:
            vis = [p for p in targets if cheb(m.x, m.y, p.x, p.y) <= ranged[0][4] and los(A, m.x, m.y, p.x, p.y)]
            if vis:  # shoot whoever is closest (front-liners shield the back row), weaker ones on ties
                t = min(vis, key=lambda p: (cheb(m.x, m.y, p.x, p.y), p.hp))
                self.m_attack(m, t, ranged[0])
                return
        if not adj:
            self.step_toward(m, [(p.x, p.y) for p in targets], m.speed)
            adj = [p for p in targets if cheb(m.x, m.y, p.x, p.y) <= 1]
            if not adj and ranged:
                vis = [p for p in targets if cheb(m.x, m.y, p.x, p.y) <= ranged[0][4] and los(A, m.x, m.y, p.x, p.y)]
                if vis:
                    self.m_attack(m, vis[0], ranged[0])
                return
        if adj:
            t = min(adj, key=lambda p: (p.downed, p.hp))
            for atk in self.melee_attacks(m):
                if not t.conscious:
                    adj = [p for p in targets if cheb(m.x, m.y, p.x, p.y) <= 1 and p.conscious]
                    if not adj:
                        break
                    t = adj[0]
                self.m_attack(m, t, atk)

    def monster_cast(self, m, targets):
        A = self.area
        self.reveal(m)
        sl = m.mslots
        base = m.T.get("spells", {})

        def can(s):
            return s in base and (base[s] == 0 or sl.get(s, 0) > 0)

        inrange = lambda s: [p for p in targets if p.conscious and cheb(m.x, m.y, p.x, p.y) <= SPELLS[s]["range"] and
                              los(A, m.x, m.y, p.x, p.y)]
        r = random.random()
        if can("hold_person") and r < 0.35:
            c = [p for p in inrange("hold_person") if "paralyzed" not in p.status]
            if c:
                return self.cast(m, "hold_person", max(c, key=lambda p: p.level * 10 + p.hp))
        if can("burning_hands"):
            for p in inrange("burning_hands"):
                if sum(1 for o in self.actors_in(self.cone(m, p.x, p.y, 3)) if o.is_pc) >= 2:
                    return self.cast(m, "burning_hands", p)
        if can("scorching_ray") and r < 0.5:
            c = inrange("scorching_ray")
            if c:
                return self.cast(m, "scorching_ray", min(c, key=lambda p: p.ac))
        if can("magic_missile") and r < 0.6:
            c = [p for p in inrange("magic_missile") if p.hp <= 10]
            if c:
                return self.cast(m, "magic_missile", c[0])
        if can("inflict"):
            c = [p for p in targets if p.conscious and cheb(m.x, m.y, p.x, p.y) <= 1]
            if c and r < 0.5:
                return self.cast(m, "inflict", c[0])
        adj = any(cheb(m.x, m.y, p.x, p.y) <= 1 for p in targets if p.conscious)
        for s in ("fire_bolt", "pale_flame"):
            if can(s) and (not adj or m.tmpl == "corvane"):
                c = inrange(s)
                if c:
                    return self.cast(m, s, min(c, key=lambda p: p.hp))
        return False

    def pc_ai(self, a):
        A = self.area
        foes = [e for e in self.hostiles() if self.sees(e) or cheb(e.x, e.y, a.x, a.y) <= 2]
        if not foes:
            hidden = [e for e in self.hostiles() if e.engaged]
            if hidden:  # we know they are out there: close in
                self.step_toward(a, [(e.x, e.y) for e in hidden], a.mp, stop_at=1)
                a.mp = 0
            return
        # emergency potion
        if a.hp < a.max_hp * 0.3 and "potion" in self.bag:
            self.use_item(a, self.bag.index("potion"))
            a.acted = True
            return
        # a friend is down right next to us: pour a potion down their throat
        down = [p for p in self.party if p.downed and cheb(p.x, p.y, a.x, a.y) <= 1]
        if down and "potion" in self.bag and not (a.cls == "cleric" and a.slot_ok(1)):
            self.use_item(a, self.bag.index("potion"), down[0])
            a.acted = True
            return
        known = {s for s, ok, _ in self.spell_list(a) if ok}
        if a.cls == "cleric":
            hurt = [p for p in self.party if not p.dead and (p.downed or p.hp < p.max_hp * 0.4)]
            hurt.sort(key=lambda p: (not p.downed, p.hp))
            if hurt:
                p = hurt[0]
                if "healing_word" in known and cheb(a.x, a.y, p.x, p.y) <= 12:
                    return self.cast(a, "healing_word", p)
                if "cure_wounds" in known:
                    self.step_toward(a, [(p.x, p.y)], a.mp)
                    if cheb(a.x, a.y, p.x, p.y) <= 1:
                        return self.cast(a, "cure_wounds", p)
            undead = [e for e in foes if e.has_tag("undead") and cheb(e.x, e.y, a.x, a.y) <= 6]
            if "turn_undead" in known and len(undead) >= 2:
                return self.cast(a, "turn_undead", a)
            spare = a.slots.get("1", [0, 0])[0] >= 2
            if "bless" in known and spare and self.combat["round"] <= 2 and len(foes) >= 3 and not a.status.get("bless"):
                return self.cast(a, "bless", a)
            boss = [e for e in foes if e.has_tag("humanoid") and e.T["xp"] >= 200 and "paralyzed" not in e.status]
            if "hold_person" in known and boss:
                t = boss[0]
                if cheb(a.x, a.y, t.x, t.y) <= 12 and los(A, a.x, a.y, t.x, t.y):
                    return self.cast(a, "hold_person", t)
        if a.cls == "wizard":
            close = [e for e in foes if cheb(e.x, e.y, a.x, a.y) <= 1]
            if close and a.mp > 0:
                self.retreat(a, foes)
            allvis = [e for e in foes if cheb(a.x, a.y, e.x, e.y) <= 16 and los(A, a.x, a.y, e.x, e.y)]
            vis = [e for e in allvis if not e.immune("fire")]
            if allvis and not vis:
                if "magic_missile" in known:
                    return self.cast(a, "magic_missile", allvis[0])
                ts = self.targets_for(a, a.weapon.get("ranged", 1))
                if ts:
                    return self.pc_attack(a, ts[0])
                return
            if vis:
                allies = [p for p in self.party if p.conscious and p is not a]
                if "fireball" in known:
                    for e in vis:
                        cells = self.ball(e.x, e.y, 2)
                        hit = self.actors_in(cells)
                        if sum(1 for o in hit if o.faction == "hostile") >= 3 and not any(o in allies for o in hit) and cheb(a.x, a.y, e.x, e.y) > 2:
                            return self.cast(a, "fireball", e)
                if "sleep" in known:
                    for e in vis:
                        cells = self.ball(e.x, e.y, 2)
                        hit = [o for o in self.actors_in(cells) if o.faction == "hostile" and not o.has_tag("undead")
                               and "asleep" not in o.status]
                        if len(hit) >= 3 and sum(o.hp for o in hit) <= 30:
                            return self.cast(a, "sleep", e)
                if "burning_hands" in known:
                    for e in vis:
                        if cheb(a.x, a.y, e.x, e.y) <= 3:
                            hit = self.actors_in(self.cone(a, e.x, e.y, 3))
                            if sum(1 for o in hit if o.faction == "hostile") >= 2 and not any(o in allies for o in hit):
                                return self.cast(a, "burning_hands", e)
                big = max(vis, key=lambda e: e.hp)
                if "scorching_ray" in known and big.hp >= 20:
                    return self.cast(a, "scorching_ray", big)
                weak = [e for e in vis if e.hp <= 8]
                if "magic_missile" in known and weak and random.random() < 0.4:
                    return self.cast(a, "magic_missile", weak[0])
                return self.cast(a, "fire_bolt", min(vis, key=lambda e: (not e.is_ranged and not e.mslots, e.hp)))
            self.step_toward(a, [(e.x, e.y) for e in foes], a.mp, stop_at=6)
            return
        if a.cls == "cleric":
            adj = [e for e in foes if cheb(e.x, e.y, a.x, a.y) <= 1]
            if not adj and "sacred_flame" in known:
                vis = [e for e in foes if cheb(a.x, a.y, e.x, e.y) <= 12 and los(A, a.x, a.y, e.x, e.y)]
                if vis and random.random() < 0.6:
                    return self.cast(a, "sacred_flame", min(vis, key=lambda e: (not e.is_ranged and not e.mslots, e.hp)))
        if a.cls == "fighter" and "second_wind" in known and a.hp < a.max_hp * 0.5:
            self.cast(a, "second_wind")
            if not self.combat:
                return
            a.acted = False
        # weapon users
        if a.is_ranged:
            vis = self.targets_for(a, a.weapon["ranged"])
            if vis:  # enemy archers and casters first, then the weakest
                return self.pc_attack(a, min(vis, key=lambda e: (not e.is_ranged and not e.mslots, e.hp)))
        prefer = foes
        if a.cls == "rogue":
            fl = [e for e in foes if self.flanked(a, e) or any(cheb(p.x, p.y, e.x, e.y) <= 1 for p in self.party if p is not a and p.conscious)]
            if fl:
                prefer = fl
        t = min(prefer, key=lambda e: (cheb(a.x, a.y, e.x, e.y), e.hp))
        if cheb(a.x, a.y, t.x, t.y) > 1:
            self.step_toward(a, [(t.x, t.y)], a.mp)
            a.mp = 0
        adj = [e for e in foes if cheb(e.x, e.y, a.x, a.y) <= 1 and e.conscious]
        if adj:
            self.pc_attack(a, min(adj, key=lambda e: e.hp))

    def retreat(self, a, foes):
        for _ in range(a.mp):
            opts = []
            for dx, dy in DIRS8:
                nx, ny = a.x + dx, a.y + dy
                if self.free(nx, ny):
                    opts.append((min(cheb(nx, ny, e.x, e.y) for e in foes), (nx, ny)))
            if not opts:
                break
            d, p = max(opts)
            if d <= min(cheb(a.x, a.y, e.x, e.y) for e in foes):
                break
            a.x, a.y = p
            a.mp -= 1
        self.update_fov()

    # --- save / load ----------------------------------------------------------------
    def to_dict(self):
        return dict(version=VERSION, seed=self.seed, party=[p.to_dict() for p in self.party],
                    areas={k: v.to_dict() for k, v in self.areas.items()}, area=self.area.id,
                    flags=self.flags, quests=self.quests, waiting=self.waiting, gold=self.gold, bag=self.bag,
                    minutes=self.minutes, discovered=self.discovered, kills=self.kills, steps=self.steps,
                    travel=self.travel, location=self.location, log=list(self.log)[-40:], diff=self.diff)

    def save(self, path=SAVE_PATH):
        if self.combat:
            self.msg("You can't save during combat.", GRAY)
            return False
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.to_dict(), f)
        os.replace(tmp, path)
        self.msg("Game saved.", CYAN)
        return True

    @classmethod
    def from_dict(cls, d):
        g = cls(d["seed"])
        g.party = [Actor.from_dict(p) for p in d["party"]]
        g.areas = {k: Area.from_dict(v) for k, v in d["areas"].items()}
        g.area = g.areas[d["area"]]
        for k in ("flags", "quests", "waiting", "gold", "bag", "minutes", "discovered", "kills", "steps", "travel", "location"):
            setattr(g, k, d[k])
        g.diff = d.get("diff", "normal")
        for t, c in d.get("log", []):
            g.log.append((t, tuple(c)))
        g.update_fov()
        return g

    @classmethod
    def load(cls, path=SAVE_PATH):
        with open(path) as f:
            return cls.from_dict(json.load(f))


# =============================================================================
# Dialogue. Each builder returns (speaker, portrait, nodes).
# A node is (text, [(label, target, cond)]); target is a node id, None (end)
# or a callable returning one of those.
# =============================================================================
def _opt(label, target=None, cond=None):
    return (label, target, cond)


def dlg_hobb(g):
    def inn():
        return "slept" if g.inn_rest() else "poor"

    def rats_start():
        g.quest("rats", "Hobb the innkeeper wants the giant rats cleared out of his cellar. The trapdoor is in the "
                        "storeroom at the back of the Rusty Lantern. Reward: 30 gold.")
        return "thanks"

    def rats_pay():
        g.gold += 30
        g.quest("rats", "Hobb paid us 30 gold. And free ale, apparently.", "done")
        g.award_xp(50 * len(g.living()))
        return "paid"

    q = g.qstate("rats")
    return ("Hobb", "hobb", {
        "start": ("Hobb, a round man with a moustache like two sleeping ferrets, polishes a tankard. \"Welcome to the "
                  "Rusty Lantern, friend! Ale's cold, stew's hot, and the beds only creak a little.\"",
                  [_opt("A room for the night, please. (10 gold)", inn),
                   _opt("Heard any news?", "news"),
                   _opt("Need any help around here?", "work", lambda: q is None),
                   _opt("Your cellar is clear of rats.", rats_pay, lambda: q == "active" and g.flags.get("rats_cleared")),
                   _opt("About those rats...", "remind", lambda: q == "active" and not g.flags.get("rats_cleared")),
                   _opt("Farewell.")]),
        "slept": ("You sleep like a stone. Sometime before dawn you dream of red wings folding over the mountain, and "
                  "an eye opening in the dark.", [_opt("(Continue)")]),
        "poor": ("Hobb winces. \"Ten gold, friend. Even the rats pay rent here. Well. Sort of.\"", [_opt("(Leave)")]),
        "news": ("\"News? Miners keep vanishing up at Deepdelve - eleven now. Mayor Thale's offering coin to anyone with "
                 "a strong arm. And at night the peaks glow red, like a forge somebody forgot to bank. My grandmother "
                 "would've said the Old Red is waking. Bah. Grandmothers.\"",
                 [_opt("Where do I find the mayor?", "mayor"), _opt("(Back)", "start")]),
        "mayor": ("\"Town hall, south-east, across the bridge. Big doors, bigger ego. Don't mention the chicken tax.\"",
                  [_opt("(Back)", "start")]),
        "work": ("\"Aye! Rats. In my cellar. Big as dogs and mean as tax collectors. Clear 'em out and there's 30 gold in "
                 "it. The trapdoor's in the storeroom, back right.\"",
                 [_opt("Consider it done.", rats_start), _opt("Rats? I'm here for dragons.", "rude")]),
        "rude": ("\"Every dragon starts small, friend. Usually as a rat.\"", [_opt("Fine. I'll do it.", rats_start), _opt("(Leave)")]),
        "thanks": ("\"Bless you! Mind your ankles. They go for the ankles.\"", [_opt("(Leave)")]),
        "remind": ("\"Still squeaking down there. I can hear 'em plotting.\"", [_opt("(Leave)")]),
        "paid": ("\"Ha! I heard the squeaking stop. Here's your coin - and you'll not pay for an ale in this house again. "
                 "This week.\"", [_opt("(Leave)")]),
    })


def dlg_brannoc(g):
    def join():
        return "joined" if g.recruit("brannoc") else "full"
    back = g.flags.get("recruited_brannoc")
    return ("Brannoc Ironvein", "brannoc", {
        "start": ("A broad dwarf with a braided red beard nurses an ale that went flat an hour ago. He doesn't look up. "
                  "\"If you're selling, I've no coin. If you're buying, I've no patience.\"" if not back else
                  "Brannoc grunts. \"Back for me, are you? Knew you'd miss the beard.\"",
                  [_opt("You look like you've lost something.", "lost", lambda: not back),
                   _opt("Come with me to Deepdelve.", join),
                   _opt("(Leave him be)")]),
        "lost": ("\"Lost? Aye. A crew of six. Twenty years I was foreman at Deepdelve. Three weeks back we broke into an "
                 "old gallery - cold air, older than any dwarf-cut. Next shift my lads went down and never came up. I "
                 "was topside with a bad knee.\" He finally looks at you. \"They say stone remembers. That stone "
                 "remembers screaming.\"",
                 [_opt("Then come with me and find out what happened.", join), _opt("I'm sorry.")]),
        "joined": ("Brannoc drains his tankard and slams it down. \"About time somebody asked. I know those tunnels like my "
                   "own beard. Lead on - but if you get me killed, I'm haunting you.\"", [_opt("(Continue)")]),
        "full": ("\"Your band's crowded enough already. Make some room and ask again.\"", [_opt("(Leave)")]),
    })


def dlg_tamsin(g):
    def right():
        g.flags["riddle"] = True
        return "joined" if g.recruit("tamsin") else "full"

    def join():
        return "joined2" if g.recruit("tamsin") else "full"
    solved = g.flags.get("riddle")
    return ("Tamsin Vale", "tamsin", {
        "start": ("An elf in a travel-worn violet coat sits behind a fortress of books, one open to a drawing of a "
                  "dragon's skull. \"You're standing in my light. Unless you're about to say something interesting, "
                  "stand somewhere else.\"" if not solved else
                  "Tamsin marks her page with a dried leaf. \"Oh, it's you. The one who knows what a mountain is.\"",
                  [_opt("What are you reading?", "reading"),
                   _opt("Would you join my company?", "riddle", lambda: not solved),
                   _opt("Come with me.", join, lambda: solved),
                   _opt("(Leave her to it)")]),
        "reading": ("\"'On the Slumber of Wyrms', by Abbot Caeric. Dragons can sleep for centuries if bound by the "
                    "right rites - and wake when those rites are... fed. Something in those mountains is breathing "
                    "again. The snow on the peaks melts at night. I came to see it. Ideally from a safe distance.\"",
                    [_opt("(Back)", "start")]),
        "riddle": ("\"Join you? I don't travel with dullards. Answer me this: I have roots that nobody sees, I am taller "
                   "than trees. Up, up I go, and yet I never grow. What am I?\"",
                   [_opt("A tree.", "wrong"), _opt("A mountain.", right), _opt("A dragon.", "wrong2")]),
        "wrong": ("\"A tree. That grows. That is the entire point of the riddle.\" She turns a page. \"Come back when "
                  "you've read a book.\"", [_opt("(Leave)")]),
        "wrong2": ("\"Dragons grow. Sadly - that's rather the problem. Try again another time.\"", [_opt("(Leave)")]),
        "joined": ("\"A mountain. Correct, and faster than the last three.\" She snaps the book shut. \"Fine. If there "
                   "is a dragon at the end of your road, I want to see it before it sees us. Tamsin Vale, at your "
                   "service. Mostly.\"", [_opt("(Continue)")]),
        "joined2": ("\"Very well. Try not to step on my books.\"", [_opt("(Continue)")]),
        "full": ("\"Your little troupe is full. I don't do crowds.\"", [_opt("(Leave)")]),
    })


def dlg_pell(g):
    def lysa():
        if not g.qstate("lysa"):
            g.quest("lysa", "Pell the bard says Lysa Thistlefoot went into the Whisperwood a week ago to 'recover' "
                            "something from the goblins, and never came back.")
        return "lysa"
    return ("Pell the Bard", "pell", {
        "start": ("A lanky bard in a feathered cap strums a lute with more enthusiasm than skill. \"Pell Merriweather, "
                  "songsmith! Want to hear 'The Ballad of the Eleven Lost Miners'? It's a work in progress. Mostly the "
                  "ending.\"",
                  [_opt("Any rumours?", "rumors"),
                   _opt("Know a halfling called Lysa?", lysa, lambda: not g.flags.get("recruited_lysa")),
                   _opt("Play something.", "play"),
                   _opt("Farewell.")]),
        "rumors": ("\"Goblins in the Whisperwood have grown bold - ambushing the road, carrying folk off alive, which "
                   "is very unlike goblins. And old Wenna swears she saw men in white robes going up the mine road at "
                   "night, with torches that burned blue.\"", [_opt("(Back)", "start")]),
        "lysa": ("\"Lysa Thistlefoot? Owes me eight gold and a lute string! Last I heard she went into the Whisperwood "
                 "to 'recover' something from the goblins. That was a week ago.\" He strums a sad chord. \"If you find "
                 "her, remind her about the eight gold.\"", [_opt("(Back)", "start")]),
        "play": ("Pell clears his throat. \"Ohhh, the miners went down, down, down / and the mountain swallowed them "
                 "whole / and the mayor did frown, frown, frown / for he'd lose the tax on their coal...\" He stops. "
                 "\"Still working on it.\"", [_opt("(Back)", "start")]),
    })


def dlg_maren(g):
    def trouble():
        if not g.qstate("edrin"):
            g.quest("edrin", "Sister Maren's brother Edrin vanished with the night shift at Deepdelve. She wants to "
                             "come with us to find him.")
        return "trouble"

    def join():
        return "joined" if g.recruit("maren") else "full"

    def locket():
        g.bag.remove("locket")
        g.quest("edrin", "We gave Edrin's locket to Maren.", "done")
        g.award_xp(200 * len(g.living()))
        g.bag += ["potion_greater", "potion_greater"]
        g.msg("Maren presses two potions of greater healing into your hands.", GREEN)
        return "locket"
    return ("Sister Maren", "maren", {
        "start": ("A young priestess in sun-yellow robes kneels at the altar, lips moving in prayer. She rises as you "
                  "approach. \"Dawn keep you, traveller. Forgive me, I am poor company today.\"",
                  [_opt("What troubles you, Sister?", trouble, lambda: not g.qstate("edrin")),
                   _opt("Come with me to Deepdelve.", join, lambda: g.qstate("edrin") is not None or g.flags.get("recruited_maren")),
                   _opt("I found this in the mine. (Give the locket)", locket, lambda: g.has("locket")),
                   _opt("Dawn keep you.")]),
        "trouble": ("\"My brother Edrin works the mine. Worked. He went down with the night shift three weeks ago "
                    "and... I've prayed every hour since. Father Aldous says the Dawnmother hears. I'm starting to think "
                    "she's busy.\" She grips her holy symbol until her knuckles whiten. \"If you're going up there, take "
                    "me with you. I can mend wounds, and I won't sit here waiting any longer.\"",
                    [_opt("Come with me.", join), _opt("Not yet.")]),
        "joined": ("\"Thank you. I'll keep you standing and the dead lying down. That's a promise.\"", [_opt("(Continue)")]),
        "full": ("\"You have no room for me. I'll pray for you, then - and wait.\"", [_opt("(Leave)")]),
        "locket": ("Maren takes the locket in trembling hands and opens it. Inside is a tiny painted portrait of herself "
                   "as a girl. \"He kept it. The fool kept it all these years.\" She is quiet for a long time. \"Thank "
                   "you for bringing him back to me. Even this much.\"", [_opt("(Leave)")]),
    })


def dlg_aldous(g):
    return ("Father Aldous", "aldous", {
        "start": ("Father Aldous, bald as an egg and twice as serene, spreads his hands. \"The Dawnmother's light is "
                  "free. Her healers, alas, must eat.\"",
                  [_opt("Heal my companions. (20 gold)", lambda: "healed" if g.temple_heal() else "poor"),
                   _opt("Raise a fallen companion. (%d gold)" % g.raise_cost, lambda: "raised" if g.temple_raise() else "poor",
                        lambda: any(p.dead for p in g.party)),
                   _opt("Tell me about the Dawnmother.", "lore"),
                   _opt("Goodbye.")]),
        "healed": ("Warm golden light flows from his palms. Bruises fade, cuts knit. \"Go with the dawn.\"", [_opt("(Back)", "start")]),
        "raised": ("The light gathers, falters, then blazes. A breath. A cough. A life returned. Aldous sags, grey with "
                   "effort. \"Don't make me do that again.\"", [_opt("(Back)", "start")]),
        "poor": ("\"I am afraid the offering is not sufficient, my child.\"", [_opt("(Back)", "start")]),
        "lore": ("\"She is the first light after the longest night. Her clerics drive back the dead and the dark. Our "
                 "oldest texts say her priests once bound a great red wyrm beneath the Ashpeaks with a seal of "
                 "dawnfire.\" He chuckles. \"Old stories. Surely.\"", [_opt("(Back)", "start")]),
    })


def dlg_greta(g):
    def shop():
        g.pending.append(("shop",))
        return None
    return ("Greta Hammersong", "greta", {
        "start": ("Greta Hammersong, broad as a door and sooty to the elbows, leans on the counter. \"Iron, steel, "
                  "potions, sundries. If it's sharp or it heals, I've got it. If it's both, it's expensive.\"",
                  [_opt("Show me your wares.", shop), _opt("Heard anything about the mine?", "mine"), _opt("Goodbye.")]),
        "mine": ("\"Ore carts stopped three weeks back. The last load that came down had this in it.\" She shows you a "
                 "shard of black glass, warm to the touch. \"Volcanic. Fresh. Deepdelve's been cold iron for a "
                 "hundred years. Something down there is running hot.\"", [_opt("(Back)", "start")]),
    })


def dlg_oswin(g):
    def accept():
        g.quest("miners", "Mayor Thale will pay 500 gold to whoever ends the disappearances at the Deepdelve mine, "
                          "east past the Whisperwood. He gave us 50 gold up front.")
        g.gold += 50
        for loc in ("whisperwood", "deepdelve"):
            if loc not in g.discovered:
                g.discovered.append(loc)
        return "accepted"

    def progress():
        if g.flags.get("corvane_dead"):
            return "p3"
        if g.flags.get("ledger"):
            return "p2"
        return "p1"
    return ("Mayor Oswin Thale", "oswin", {
        "start": ("Mayor Oswin Thale, a thin man drowning in a chain of office, looks up from a mountain of papers. "
                  "\"Yes? If it's about the tax on chickens, the answer is still no.\"",
                  [_opt("I'm here about the missing miners.", "miners", lambda: not g.qstate("miners")),
                   _opt("About the mine...", progress, lambda: g.qstate("miners") == "active"),
                   _opt("Goodbye.")]),
        "miners": ("\"Ah! Finally, someone with a sword and no sense - I mean, courage. Eleven miners gone in three "
                   "weeks. My watch won't go near the place. Find out what is happening at Deepdelve and put a stop to "
                   "it. Five hundred gold from the town coffers.\" He slides a small purse across the desk. \"Fifty "
                   "now, for supplies. The mine lies east, past the Whisperwood.\"",
                   [_opt("Consider it done.", accept), _opt("I'll think about it.")]),
        "accepted": ("\"Splendid! Do try to come back. Paperwork for dead heroes is dreadful.\"", [_opt("(Leave)")]),
        "p1": ("\"Any news? No? The mine lies east, beyond the Whisperwood. Do hurry.\"", [_opt("(Leave)")]),
        "p2": ("You show him the ledger. He reads, and his face goes the colour of old porridge. \"A cult? Here? "
               "Feeding people to... gods above. Whatever it costs, end it.\"", [_opt("(Leave)")]),
        "p3": ("\"Corvane dead, and a DRAGON beneath the mine?\" The mayor sits down very slowly. \"Then you know what "
               "you have to do. Emberfall is counting on you. I am counting on you. Please don't let me down - I've "
               "already spent the reward on the victory feast.\"", [_opt("(Leave)")]),
    })


def dlg_captain(g):
    return ("Captain Rook", "captain", {
        "start": ("Captain Rook of the Emberfall watch leans on her spear by the east road. \"Road east runs through "
                  "the Whisperwood to the Deepdelve mine. Goblins in the wood, and worse in the mine if the stories "
                  "are true. Mind yourself.\"",
                  [_opt("Any advice?", "advice"), _opt("Thanks.")]),
        "advice": ("\"Rest before you go deep - nobody ever died of a good night's sleep. Undead hate blunt steel and "
                   "holy light. Dragons don't hate anything; they just eat it. And if you see white candles burning "
                   "blue, walk the other way.\"", [_opt("(Back)", "start")]),
    })


VILLAGER_LINES = {
    "Old Wenna": "\"In my day, dragons knew their place - under a mountain, asleep, where they belong!\"",
    "Farmer Dobbs": "\"Corn's coming up warm. Warm, in autumn! Mark my words, something's cooking under us.\"",
    "Little Pip": "\"Are you a real hero? Do you have a sword? Can I hold it? Can I hold it NOW?\"",
}


def dlg_villager(g, name):
    return (name, "villager", {"start": ("%s: %s" % (name, VILLAGER_LINES.get(name, "\"Good day.\"")), [_opt("(Leave)")])})


def dlg_lysa(g):
    def join():
        return "joined" if g.recruit("lysa") else "full"

    def send():
        A = g.area
        npc = next((a for a in A.actors if a.npc == "lysa"), None)
        if npc:
            A.actors.remove(npc)
        town = g.areas["town"]
        h = COMP_HOME["lysa"]
        town.actors.append(make_npc("lysa", "Lysa Thistlefoot", h[1], h[2]))
        g.flags["lysa_waiting"] = True
        return "sent"

    def freed():
        if g.qstate("lysa") != "done":
            g.quest("lysa", "We freed Lysa Thistlefoot from the goblins' cage.", "done")
            g.award_xp(150 * len(g.living()))
        return "free"
    if not g.flags.get("lysa_free"):
        if not g.qstate("lysa"):
            g.quest("lysa", "A halfling named Lysa is locked in a cage in the goblin camp. The goblin chief, "
                            "Snagtooth, has the key.")
        return ("Lysa Thistlefoot", "lysa", {
            "start": ("A halfling in a ragged green cloak rattles the bars. \"Oh good, a rescuer! Or a very well-dressed "
                      "goblin. Either way: the big ugly one with the tooth, Snagtooth, has the key. Kill him, grab it, "
                      "let me out. I'll be ever so grateful. Moderately grateful. Grateful.\"",
                      [_opt("Hang on, we'll get you out.")]),
        })
    if g.area.id == "forest":
        return ("Lysa Thistlefoot", "lysa", {
            "start": (lambda: (freed() and None) or
                      "Lysa stretches until her back pops. \"Freedom! Smells like goblin, but freedom.\" She looks you "
                      "over. \"You look like people who walk into dark holes for money. I'm very good at dark holes. "
                      "Locks, traps, pointy bits in backs. Want me?\"",
                      [_opt("Welcome aboard.", join), _opt("Head back to town. We'll talk at the Rusty Lantern.", send)]),
            "joined": ("\"Splendid. I'll take the left flank. And the loot. Mostly the loot.\"", [_opt("(Continue)")]),
            "sent": ("\"The Lantern it is. Tell Hobb it wasn't me who broke the window.\" She is gone between two "
                     "blinks.", [_opt("(Continue)")]),
            "full": ("\"Bit crowded, isn't it? I'll be at the Rusty Lantern when you need me.\"", [_opt("(Continue)", send)]),
        })
    return ("Lysa Thistlefoot", "lysa", {
        "start": ("Lysa is spinning a dagger on the tabletop. \"Need a rogue? I'm cheaper than a good lock. Slightly.\"",
                  [_opt("Join us.", join), _opt("Not now.")]),
        "joined": ("\"Ha! Knew you'd come crawling back.\"", [_opt("(Continue)")]),
        "full": ("\"No room? Story of my life.\"", [_opt("(Leave)")]),
    })


def dlg_snagtooth(g):
    def heard():
        g.flags["heard_firemen"] = True
        if g.qstate("miners") == "active":
            g.quest("miners", "The goblin chief Snagtooth sold captives to 'fire-men' in white robes, for the 'Big Red "
                              "under the mountain'.")
        return "firemen"
    return ("Snagtooth", "snagtooth", {
        "start": ("A huge goblin with a single tooth jutting past his nose bangs a scimitar on a pot lid. \"MORE MEAT! "
                  "Fire-men pay good shinies for meat! You go in cage, or you go in pot!\"",
                  [_opt("Who are the fire-men?", heard), _opt("(Attack!)")]),
        "firemen": ("\"White robes! Cold fire! They buy meat for Big Red under mountain. Big Red very hungry, very "
                    "sleepy. Snagtooth get RICH!\" He licks his tooth. \"Enough talk. POT!\"", [_opt("(Fight!)")]),
    })


def dlg_corvane(g):
    return ("Magister Corvane", "corvane", {
        "start": ("A gaunt man in white robes stands before the altar, pale flame dancing in his open palm. Behind him "
                  "the sealed gate pulses like a heartbeat. \"Ah. The heroes of Emberfall. Do you know what you are "
                  "interrupting? Two hundred years ago the Dawnmother's priests chained Ashmaw beneath this mountain. "
                  "Chains rust. Seals fade. A little blood - well, rather a lot of blood - and the greatest power in "
                  "the north wakes, grateful to those who fed it.\"",
                  [_opt("You fed the miners to a dragon?!", "fed"), _opt("Surrender, Corvane.", "surrender"),
                   _opt("(Attack!)")]),
        "fed": ("\"Fed? Some. The rest got up again and went back to work downstairs. Waste not.\" He smiles. \"When "
                "Ashmaw rises, Emberfall will be the first offering. You could be the second.\"",
                [_opt("Not today.")]),
        "surrender": ("\"Surrender? I have a dragon. You have...\" He looks you over. \"...enthusiasm.\" The fanatics "
                      "draw their knives.", [_opt("(Fight!)")]),
    })


def dlg_ashmaw(g):
    def draconic():
        g.flags["surprise"] = True
        return "draconic"
    return ("Ashmaw", "ashmaw", {
        "start": ("The darkness opens one eye. It is as big as a cartwheel and the colour of a forge. Gold slides like "
                  "water as the dragon uncoils, and the heat hits you like a wall. \"SMALL THINGS,\" says a voice you "
                  "feel in your teeth. \"THE PRIEST PROMISED ME A TOWN. INSTEAD HE SENDS ME... MORSELS.\"",
                  [_opt("Corvane is dead. Go back to sleep, wyrm.", "sleep"),
                   _opt("(Tamsin speaks in Draconic) \"Great one, a word before the feast?\"", draconic, lambda: g.in_party("tamsin")),
                   _opt("Take our gold and let us go.", "bribe", lambda: g.gold > 0),
                   _opt("For Emberfall!")]),
        "sleep": ("\"DEAD? GOOD. HE TALKED TOO MUCH.\" Smoke curls from its nostrils. \"BUT I AM AWAKE NOW. AND SO VERY "
                  "HUNGRY.\"", [_opt("(Fight!)")]),
        "draconic": ("Ashmaw's great head tilts, amused despite itself. \"AN ELF WHO SPEAKS THE TRUE TONGUE. HOW... "
                     "QUAINT.\" While it savours the moment, your company spreads out and readies weapons.\n\n(Your "
                     "party wins the initiative.)", [_opt("(Fight!)")]),
        "bribe": ("\"YOUR GOLD?\" The laughter shakes dust from the ceiling. \"ALL GOLD IS ALREADY MINE. I SIMPLY HAVE "
                  "NOT COLLECTED IT YET.\"", [_opt("(Fight!)")]),
    })


DIALOGUES = {"hobb": dlg_hobb, "brannoc": dlg_brannoc, "tamsin": dlg_tamsin, "pell": dlg_pell, "maren": dlg_maren,
             "aldous": dlg_aldous, "greta": dlg_greta, "oswin": dlg_oswin, "captain": dlg_captain, "lysa": dlg_lysa,
             "snagtooth": dlg_snagtooth, "corvane": dlg_corvane, "ashmaw": dlg_ashmaw}


def get_dialogue(g, npc):
    if npc in DIALOGUES:
        spk, port, nodes = DIALOGUES[npc](g)
        extra, opts = side_quest_options(g, npc)
        if opts and "start" in nodes:
            nodes = dict(nodes, **extra)
            text, base = nodes["start"]
            nodes["start"] = (text, base[:-1] + opts + base[-1:])  # before the farewell
        return spk, port, nodes
    a = next((x for x in g.area.actors if x.npc == npc), None)
    return dlg_villager(g, a.name if a else "Villager")


def talk_villager(g, actor):
    return dlg_villager(g, actor.name)


SHOP_STOCK = ["potion", "potion_greater", "dagger", "mace", "spear", "shortsword", "scimitar", "longsword", "battleaxe",
              "warhammer", "greatsword", "shortbow", "longbow", "light_crossbow", "leather", "studded", "chain_shirt",
              "scale", "chain_mail", "splint", "plate", "shield", "longsword_p1", "scroll_mm"]


# =============================================================================
# ASCII art
# =============================================================================
_MIR = str.maketrans("/\\()<>[]{}`'db", "\\/)(><][}{'`bd")


def _rows(s, marker=False):
    rows = s.strip("\n").split("\n")
    return [r[:-1] if marker and r.endswith(".") else r for r in rows]


def _mirror(s, center=True):
    half = _rows(s, True)
    w = max(len(l) for l in half)
    out = []
    for l in half:
        l = l.ljust(w)
        r = l[:-1] if center else l
        out.append(l + r[::-1].translate(_MIR))
    return out


FONT = {
    'E': [" _____ ", "| ____|", "|  _|  ", "| |___ ", "|_____|"],
    'M': [" __  __ ", "|  \\/  |", "| |\\/| |", "| |  | |", "|_|  |_|"],
    'B': [" ____  ", "| __ ) ", "|  _ \\ ", "| |_) |", "|____/ "],
    'R': [" ____  ", "|  _ \\ ", "| |_) |", "|  _ < ", "|_| \\_\\"],
    'F': [" _____ ", "|  ___|", "| |_   ", "|  _|  ", "|_|    "],
    'A': ["    _    ", "   / \\   ", "  / _ \\  ", " / ___ \\ ", "/_/   \\_\\"],
    'L': [" _     ", "| |    ", "| |    ", "| |___ ", "|_____|"],
}


def banner(text):
    out = [""] * 5
    for ch in text:
        g = FONT[ch]
        for i in range(5):
            out[i] += g[i]
    return out


DRAGON = _mirror(r"""
  _                                  .
 | `-._                         ,    .
 |  /\ `-._                      \   .
 | /  \    `-._                 __\  .
 |/ /\ \  /\   `-._         .-''   \ .
 ' /  \ \/  \  /\  `-._    /  .-.   .
  /    \     \/  \     `-./  ( @ )  .
 /  /\  \  /\     \       |   `-'   .
/  /  \  \/  \  /\ \      \   .  o  .
  /    \      \/  \ \      `.  \VVVV.
        \          \ \       `.  `--.
         `.         `.`._      `-.__.
           `-._       `-._`-._     /.
               `-._      `-._ `-. | .
                   `--.__    `.  \|/.
                          `--. `. ||.
                              `. \/|.
                                `.\|.
""")

ASHMAW_HEAD = _mirror(r"""
     /\                 .
    /  \_               .
   /     `-.        ___ .
  |  /\     `-.___.'   `.
  | /  `-.     ____      .
  |/      `-. /____\  .-..
   \  /\     | (@@) |(   .
    \/  \    | `--' | `-..
     \   `-._ \    /   / .
      \      `-`--'   /  .
       `.   \VVVVVVVVVVVV.
         `.  \           .
           `. `.  /\/\/\/.
             `-.`-._____ .
                `-._____ .
""")

PORTRAITS = {
    "hobb": r"""
          ________
        .'        `.
       /  __    __  \
      |  (o)    (o)  |
      |      ()      |
      | ~~~~~~~~~~~~ |
      |  ~~~~  ~~~~  |
       \   `----'   /
     __ `-.______.-' __
    /  \   |    |   /  \
   |    |__|____|__|    |
""",
    "fighter": r"""
        ______
      .'  ||  `.
     /    ||    \
    |=====||=====|
    | ===    === |
    |     ||     |
    |  :  ||  :  |
     \    ||    /
   ___\___||___/___
  /   |========|   \
 /____|________|____\
""",
    "rogue": r"""
         ______
      .-'      `-.
     /   .----.   \
    /  .'      `.  \
   |  /  __  __  \  |
   |  | .o.  .o. |  |
   |  |    /\    |  |
   |  |#########|   |
   |   \#######/    |
   /`-._`-----'_.-'\
  /     `-----'     \
""",
    "wizard": r"""
            /\
           /  \
          / *  \
         /   .  \
        /  *     \
   ____/__________\____
  `--------------------'
       |  _    _  |
       | (o)  (o) |
       |    /\    |
       |\\\\  ////|
        \\\\\////
         \\\\///
          \\\//
""",
    "cleric": r"""
       \   |   /
     `. \  |  / .'
   ---- .-'"'-. ----
       /       \
      |  ^   ^  |
      |  o   o  |
      |    '    |
       \  `-'  /
     .--`-----'--.
    /   \  O  /   \
   /     \___/     \
""",
    "brannoc": r"""
         .------.
        /  ____  \
       |==|_||_|==|
       |  _    _  |
      (| (o)  (o) |)
       |    ()    |
       |\ ~~~~~~ /|
       | \\||||// |
        \ \\||// /
         \_\\//_/
            ||
           (__)
""",
    "tamsin": r"""
         .-~~~~-.
        /  .--.  \
       /  /    \  \
   <\ |  | -  - |  | />
     \|  | o  o |  |/
      |  |  ''  |  |
      |  |  --  |  |
      |   \____/   |
      |  /|    |\  |
     /  / |____| \  \
""",
    "maren": r"""
           .-o-.
       .-~~~~~~~~~-.
      /  .-'''''-.  \
     /  /  _   _  \  \
    |  |  (o) (o)  |  |
    |  |     .     |  |
    |  |   `---'   |  |
    |   \         /   |
    |    `-.___.-'    |
     \     _|_|_     /
      `---/  O  \---'
""",
    "lysa": r"""
        @@@@@@@@
      @@@@@@@@@@@@
     @@  .----.  @@
     @  / -   - \ @
      ( | o   o | )
        |   >   |
        |  \__/ |
         \_____/
       __/|   |\__
      /   \___/   \
""",
    "pell": r"""
                ,,,/
          ____.-'''
        .'  ____  `.
       /___/    \___\
         |  ^   ^  |
         |  o   o  |
         |    >    |
         |  \___/  |
          \_______/
         /|  ~~~  |\
""",
    "aldous": r"""
         _.----._
       .'        `.
      /            \
     |  ___    ___  |
     |   _      _   |
     |   -      -   |
     |       (      |
     |    `----'    |
      \            /
       `-.______.-'
        /   \O/  \
""",
    "greta": r"""
       .~~~~~~~~~~.
      /~~~~~~~~~~~~\
     |  __      __  |
     |  (o)    (o)  |
   @ |      ||      | @
   @@|   ` '--' `   |@@
   @@ \   .____.   / @@
    @  \          /  @
        `-.____.-'
       /|========|\
""",
    "oswin": r"""
          _______
         |       |
        _|_______|_
       '-----------'
         |  -  -  |
         |  o  o  |
         |   _)   |
         |  ----  |
          \______/
     o-o-o-o-[$]-o-o-o-o
""",
    "captain": r"""
     |   ______
     |  /      \
     | /___||___\
     | | -  || - |
     | | o  || o |
     | |    ||   |
     | |  `----' |
     |  \_______/
    /|\  |=====|
     |   |     |
""",
    "villager": r"""
         .------.
        /        \
       |  o    o  |
       |    __    |
        \  \__/  /
         `------'
        /|      |\
""",
    "snagtooth": r"""
  \`.     _____     .'/
   \ `. .'     `. .' /
    \  /  _   _  \  /
     `|  (o) (o)  |'
      |     ^     |
      |  ._/|\_.  |
      |  |     |  |
       \ `-----' /
        `-.___.-'
       /|#######|\
""",
    "corvane": r"""
           .--.
         .'    `.
        /  .--.  \
       /  / -- \  \
      |  | (o)(o)|  |
      |  |   ><  |  |
      |  |  ____ |  |
      |   \ `--'/   |
     /     `----'    \
    /  *              \
   / (^) \          /  \
""",
}
PORTRAIT_COL = {
    "hobb": (AMBER, {"~": BROWN, "o": WHITE, "(": SKIN, ")": SKIN, "|": LIGHT, "_": LIGHT}),
    "fighter": (STONE, {"=": GOLD, ":": GRAY}),
    "rogue": (GREEN, {"o": YELLOW, "#": DGREEN}),
    "wizard": (BLUE, {"*": YELLOW, ".": YELLOW, "o": WHITE, "\\": LIGHT, "/": LIGHT}),
    "cleric": (GOLD, {"o": WHITE, "O": YELLOW, "-": AMBER}),
    "brannoc": ((81, K.COLOR_CYAN), {"|": STONE, "=": STONE, "_": STONE, "~": ORANGE, "\\": ORANGE, "/": ORANGE, "(": SKIN, ")": SKIN, "o": WHITE}),
    "tamsin": ((213, K.COLOR_MAGENTA), {"~": PURPLE, "o": CYAN, "<": SKIN, ">": SKIN}),
    "maren": ((227, K.COLOR_YELLOW), {"o": WHITE, "O": GOLD, "~": LIGHT}),
    "lysa": ((120, K.COLOR_GREEN), {"@": BROWN, "o": WHITE, ">": SKIN}),
    "pell": (PINK, {",": RED, "o": WHITE, "~": YELLOW}),
    "aldous": (GOLD, {"O": YELLOW}),
    "greta": (ORANGE, {"~": RED, "@": BROWN, "=": GRAY, "o": WHITE}),
    "oswin": ((141, K.COLOR_MAGENTA), {"o": GOLD, "-": GOLD, "$": YELLOW}),
    "captain": ((75, K.COLOR_CYAN), {"|": STONE, "o": WHITE, "=": BLUE}),
    "villager": (SKIN, {}),
    "snagtooth": (LGREEN, {"o": RED, "|": WHITE, "#": BROWN}),
    "corvane": (WHITE, {"o": PALE, "*": PALE, "^": CYAN, "(": PALE, ")": PALE}),
    "ashmaw": (RED, {"@": YELLOW, "V": WHITE, "/": DRED, "\\": DRED}),
}

SCENES = {
    "town": r"""
                         (  )                         )
          _____         (  )        ______           (
         /     \  ____   ||        / /\ \ \     ______)___
        /  []   \|    |  ||  ___  / /  \ \ \   /          \
       /_________\ [] |__||_/   \/ / /\ \ \ \_/  RUSTY     \
        | [] [] | |   |  |  | | |_/ /  \ \_\ |  LANTERN  []|
   ~~~~~|   _   |~|___|~~|__|_|_|  [ ]  |  | |     _       |~~~~~
  ~~~~~~|__| |__|~~~~~~~~~~~~~~~~|______|__|_|____| |______|~~~~~~
""",
    "cellar": r"""
       _____      _____      _____               .  .
      /     \    /     \    /     \             (o)(o)
     |=======|  |=======|  |=======|     __      \  /
     |  ===  |  |  ===  |  |  ===  |    (  )~~~   ''
     |=======|  |=======|  |=======|   (    )
      \_____/    \_____/    \_____/   ~~~~~~~~ squeak
""",
    "forest": r"""
       &&&        &&&&           &&&         &&&&        &&&
     &&&&&&&    &&&&&&&&       &&&&&&&     &&&&&&&&    &&&&&&&
    &&&&&&&&&  &&&&&&&&&&     &&&&&&&&&   &&&&&&&&&&  &&&&&&&&&
      &&|&&      &&&|&&&        &&|&&       &&&|&&&     &&|&&
        |   ,      .|  ,   .      |   . ,     .|    ,     |
   .,.,,|,.,.,,.,.,.|,.,,.,.,.,.,.|,.,,.,.,.,.,|.,.,,.,.,.|.,.,.
""",
    "mine": r"""
                   /\        /\/\         /\
              /\  /  \  /\  /    \   /\  /  \
             /  \/    \/  \/  __  \_/  \/    \
            /     ________   /  \           \
           /     |  ____  | |    |   DEEPDELVE\
          /      | |    | |  \__/      MINE    \
     ____/_______|_|____|_|_____________________\_____
         ========|=|====|=|====
""",
    "galleries": r"""
          .       .            .           .
      ___/|\_____/|\____    __/|\____     /|\
     |    |       |     |  |   |     |     |
     |   .-.     .-.    |  |  .-.    |    .-.
     |  (x x)   (x x)   |  | (x x)   |   (x x)
     |   |=|     |=|    |  |  |=|    |    |=|
     |  /| |\   /| |\   |  | /| |\   |   /| |\
""",
    "sanctum": r"""
       ___           ___           ___           ___
      |   |   *     |   |    *    |   |     *   |   |
      |   |  (^)    |   |   (^)   |   |    (^)  |   |
      |   |  /_\    |   |   /_\   |   |    /_\  |   |
      |   |        _|___|_________|___|_        |   |
      |   |       |  THE PALE FLAME BURNS  |    |   |
     _|___|_______|________________________|____|___|_
""",
    "lair": r"""
               .           .   .         .           .
        .           .--''''''''''--.          .
     .           .-'    .-''''-.    `-.            .
               .'      /  .--.  \      `.     .
       .      /       |  ( @@ )  |       \
              \        \  `--'  /        /       .
          .    `-.      `-.__.-'      .-'     .
                  `--..___________..--'    .
""",
    "ambush_wolves": r"""
            /\     /\                    /\     /\
           /  \___/  \                  /  \___/  \
          (  o     o  )                (  o     o  )
           \    ^    /      AWOOOO      \    ^    /
            \ \___/ /                    \ \___/ /
             `-----'                      `-----'
""",
    "ambush_goblins": r"""
          \`.  ___  .'/         \`.  ___  .'/
           \ `/   \' /           \ `/   \' /
            | o   o |    OI!      | o   o |
            |   ^   |  SHINIES!   |   ^   |
             \ VVV /               \ VVV /
           ---`---'---|>        <|---`---'---
""",
    "ambush_bandits": r"""
            ______                     ______
           /      \                   /      \
          |  ====  |   YOUR GOLD,    |  ====  |
          |  o  o  |   OR YOUR LIFE! |  o  o  |
          | ###### |                 | ###### |
          /|######|\--|=====>   <====|-/######|\
""",
    "grave": r"""
                          _______
                        .'       `.
                        |   R.I.P |
             .-.        |  EDRIN  |
            (   )~~     |         |
             |=|        |  ~ * ~  |
          ___|_|________|_________|______
""",
    "gameover": r"""
                       ___________
                     .'           `.
                    /    HERE LIES  \
                   |                 |
                   |   %-17s   |
                   |                 |
                   |   Slain in the  |
                   |    Ashpeaks     |
                   |        *        |
            ,,,,,,,|,,,,,,,,,,,,,,,,,|,,,,,,,,
""",
    "victory": r"""
                    \       |       /
                      \     |     /
                 `-.    \   |   /    .-'
                     `-.  .---.  .-'
        --------------- (  SUN  ) ---------------
            /\        /\ `---' /\        /\
           /  \  /\  /  \     /  \  /\  /  \
          /    \/  \/    \   /    \/  \/    \
     ____/                \_/                \____
""",
    "levelup": r"""
          .   *   .
        *  \  |  /  *
      .  -- LEVEL --  .
        *  /  |  \  *
          .   *   .
""",
}
SCENE_COL = {
    "town": (TAN, {"~": BLUE, "(": GRAY, ")": GRAY, "[": YELLOW, "]": YELLOW, "/": RED, "\\": RED, "R": AMBER, "U": AMBER,
                   "S": AMBER, "T": AMBER, "Y": AMBER, "L": AMBER, "A": AMBER, "N": AMBER, "E": AMBER}),
    "cellar": (BROWN, {"o": RED, "(": GRAY, ")": GRAY, "~": GRAY, "=": WOOD}),
    "forest": (GREEN, {"|": BROWN, ",": DGREEN, ".": MOSS}),
    "mine": (GRAY, {"=": WOOD, "|": WOOD, "_": WOOD, "D": AMBER, "E": AMBER, "P": AMBER, "L": AMBER, "V": AMBER,
                    "M": AMBER, "I": AMBER, "N": AMBER}),
    "galleries": (BONE, {"x": RED, "|": GRAY, "_": GRAY, ".": AMBER}),
    "sanctum": (STONE, {"*": PALE, "^": CYAN, "(": PALE, ")": PALE, "T": PALE, "H": PALE, "E": PALE, "P": PALE,
                        "A": PALE, "L": PALE, "F": PALE, "M": PALE, "B": PALE, "U": PALE, "R": PALE, "N": PALE, "S": PALE}),
    "lair": (DRED, {"@": YELLOW, ".": EMBER, "(": ORANGE, ")": ORANGE}),
    "ambush_wolves": (GRAY, {"o": YELLOW, "A": RED, "W": RED, "O": RED}),
    "ambush_goblins": (LGREEN, {"o": RED, "V": WHITE, "-": GRAY, "|": GRAY}),
    "ambush_bandits": (TAN, {"#": DGRAY, "=": GRAY, "o": WHITE}),
    "grave": (STONE, {"~": AMBER, "(": AMBER, ")": AMBER, "*": GOLD}),
    "gameover": (STONE, {",": DGREEN, "*": RED}),
    "victory": (GOLD, {"/": GRAY, "\\": GRAY, "_": GRAY, "-": AMBER, "S": YELLOW, "U": YELLOW, "N": YELLOW}),
    "levelup": (YELLOW, {"*": GOLD, ".": AMBER}),
}
SCENE_TEXT = {
    "town": ("Emberfall", "A mining town of timber and stone where the river Emberrun runs down from the Ashpeaks. "
                          "Lately the people here lock their doors at night, and nobody looks at the mountains for long."),
    "cellar": ("The Cellar", "It smells of old beer and wet fur. Somewhere in the dark, many small claws stop moving "
                             "all at once."),
    "forest": ("The Whisperwood", "Old trees lean together over the road like gossips. Goblin signs are scratched into "
                                  "the bark: a pot, a stick figure, an arrow pointing deeper in."),
    "mine": ("Deepdelve Mine", "Timbers groan. The rails are cold, but the air coming up the shaft is warm as breath, and "
                               "it smells of sulphur. Someone has hung white candles along the walls."),
    "galleries": ("The Lower Galleries", "Here the dwarf-cut tunnels give way to something older. The walls are scratched "
                                         "with tally marks. Shapes shuffle in the dark, wearing miners' boots."),
    "sanctum": ("Sanctum of the Pale Flame", "An ancient temple of the Dawnmother, defaced. Pale fire burns in the old "
                                             "braziers, cold as winter. At the far end, a gate of light pulses like a heart."),
    "lair": ("Ashmaw's Lair", "Heat. Gold. Bones. The cavern opens like the inside of a furnace, and the mountain itself "
                              "seems to breathe. In the dark ahead, something enormous shifts in its sleep."),
    "ambush_wolves": ("Ambush!", "Grey shapes slip between the trees, circling. A wolf pack has caught your scent."),
    "ambush_goblins": ("Ambush!", "\"OI! SHINIES!\" Goblins burst from the undergrowth, waving rusty blades."),
    "ambush_bandits": ("Ambush!", "Hooded figures step onto the road ahead. \"Your gold, or your life. Your choice, "
                                  "friends. Mostly ours.\""),
}

WORLD_MAP = r"""
  ^^^^  ^^^ ^^^^^^ ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 ^^  ^^^^ ^^^^^^^ ^^^^ T H E   A S H P E A K S ^^^^^ /\ ^^^^^^^^ ^^^^^^ ^^
   ^^^   ^^^^   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^  /  \  ^^^^ ^^^^ ^^^ ^^
 ,,,  ^^    ,,,,  ^^^^^^^ ^^^^^^ ^^^^^^ ^^^^ ^^^^  / ** \ ^^^ ^^^^^ ^^^^^
 ,,,,,,,,,,,,,,,,,,,,,, ^^^^ ^^^^^^ ^^^^^ ^^^^^^  /      \ ^^^^ ^^ ^^^^
 ,,,,,,,,,,,,,,,,,,,,,,,,,,,,, ^^^^^ ^^^ ^^^^^^ [=========] ^^^ ^^^^^ ^
 ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,, ^^^^ ^^^^ ...........:  ^^^^ ^^^^
 ,,~~,,,,,,,,,,,,,,,,,,,,,&&&&&&&&&&&&&&&&&&&&&&....,,,,,,,,,,, ^^^ ^^^^
 ,,,~~,,,,,,,,,,,,,,,,,&&&&&&&&&&&&&&&&&&&&&&&&&&&..,,,,,,,,,,,,,,,,,,,,
 ,,,,~~~,,,,,,,,,,,,,&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&.,,,,,,,,,,,,,,,,,,,
 ,,,,,,~~~,,,,,,,,,&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&,,,,,,,,,,,,,,,,,,,
 ,,,,,,,,~~~,,,,,,&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&,,,,,,,,,,,,,,,,,,
 ,,,,,,,,,,~~~,,,,&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&,,,,,,,,,,,,,,,,,,
 ,,,,,,,,,,,,~~ .........&&&&&&&&&&&&&&&&&&&&&&&&&&&,,,,,,,,,,,,,,,,,,,,
 ,,,,,,,,,,,,,[##]...........&&&&&&&&&&&&&&&&&&&&&,,,,,,,,,,,,,,,,,,,,,,
 ,,,,,,,,,,,,[####]~~,,,,,,,,,,&&&&&&&&&&&&&&&&&,,,,,,,,,,,,,,,,,,,,,,,,
 ,,,,,,,,,,,,,,,,,,,,~~~,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
 ,,,,,,,,,,,,,,,,,,,,,,,~~~~,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
 ,,,,,,,,,,,,,,,,,,,,,,,,,,,~~~~~~,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
"""
WORLD_COL = (DGREEN, {"^": GRAY, "&": GREEN, "~": BLUE, ".": TAN, ":": TAN, "#": WOOD, "[": WOOD, "]": WOOD, "=": WOOD,
                      "*": RED, "/": GRAY, "\\": GRAY, "T": LIGHT, "H": LIGHT, "E": LIGHT, "A": LIGHT, "S": LIGHT, "P": LIGHT, "K": LIGHT})

# --- painted world map (truecolor half-block pixels, generated for the screen size) ---
WORLD_ROAD_AT = {"emberfall": 0, "whisperwood": 3, "deepdelve": 6}  # index into WORLD_ROAD
WORLD_SIGN = {"emberfall": (3, None), "whisperwood": (1, None), "deepdelve": (0, 5)}  # sign offset: rows, cols (None: centred)
WORLD_PIX = {"emberfall": (0.22, 0.74), "whisperwood": (0.45, 0.62), "deepdelve": (0.66, 0.43)}
WORLD_ROAD = [(0.22, 0.74), (0.30, 0.72), (0.37, 0.66), (0.45, 0.62), (0.53, 0.58), (0.60, 0.52), (0.66, 0.43)]
WORLD_RIVER = [(0.06, 0.30), (0.09, 0.42), (0.14, 0.52), (0.15, 0.62), (0.13, 0.72), (0.17, 0.82), (0.28, 0.90),
               (0.42, 0.94), (0.55, 1.02)]
_WORLD_CACHE = {}


def _nhash(ix, iy, s):
    n = (ix * 374761393 + iy * 668265263 + s * 982451653) & 0xffffffff
    n = ((n ^ (n >> 13)) * 1274126177) & 0xffffffff
    return (n ^ (n >> 16)) / 4294967295.0


def _vnoise(x, y, s):
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x - ix, y - iy
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a, b = _nhash(ix, iy, s), _nhash(ix + 1, iy, s)
    c, d = _nhash(ix, iy + 1, s), _nhash(ix + 1, iy + 1, s)
    return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy


def _fbm(x, y, s, octaves=4):
    t, amp, norm = 0.0, 1.0, 0.0
    for o in range(octaves):
        t += amp * _vnoise(x, y, s + o * 17)
        norm += amp
        x, y, amp = x * 2.03, y * 2.03, amp * 0.5
    return t / norm


def _seg_dist(px, py, pts):
    """Distance from (px, py) to a polyline, and the index of the nearest segment."""
    best, bi = 1e9, 0
    for i in range(len(pts) - 1):
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy or 1
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
        d = math.hypot(px - ax - t * dx, py - ay - t * dy)
        if d < best:
            best, bi = d, i
    return best, bi


def _mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def _scale(c, k):
    return (c[0] * k, c[1] * k, c[2] * k)


def world_pixels(PW, PH):
    """An RGB pixel grid [y][x] of the Ashpeak Marches, PW x PH pixels."""
    key = (PW, PH)
    if key in _WORLD_CACHE:
        return _WORLD_CACHE[key]
    asp = PW / PH  # noise is sampled in square units so features keep their shape
    vx, vy = 0.84, 0.17  # Ashmaw's peak

    tx, ty = WORLD_PIX["emberfall"]
    fx, fy = WORLD_PIX["whisperwood"]
    mx, my = WORLD_PIX["deepdelve"]
    river = [(x * PW, y * PH) for x, y in WORLD_RIVER]
    road = [(x * PW, y * PH) for x, y in WORLD_ROAD]
    sc = PH / 60.0  # feature size relative to a 60 pixel tall map

    def elev(u, v):
        n = _fbm(u * asp * 5, v * 5, 3)
        r = 1 - abs(2 * _fbm(u * asp * 3.2, v * 3.2, 11, 5) - 1)
        band = 0.36 + 0.10 * (_fbm(u * 4, 0.5, 23) - 0.5) * 2
        m = max(0.0, 1 - v / band)
        e = m * (0.30 + 0.55 * r * r) + 0.12 * n
        return e

    E = [[elev(x / PW, y / PH) for x in range(PW + 1)] for y in range(PH + 1)]
    GRASS = [(54, 92, 40), (78, 120, 52), (104, 146, 66)]
    out, opn = [], []
    for y in range(PH):
        v = y / PH
        row, orow = [], []
        for x in range(PW):
            u = x / PW
            e = E[y][x]
            shade = 1 + 4.5 * (e - E[max(0, y - 1)][max(0, x - 1)]) * (PH / 60.0)
            shade = max(0.55, min(1.45, shade))
            dv = math.hypot((u - vx) * asp, v - vy)
            g = _fbm(u * asp * 9, v * 9, 5)
            if e < 0.30:
                c = _mix(GRASS[0], GRASS[1], g * 1.6 - 0.1)
                if g > 0.62:
                    c = _mix(c, GRASS[2], (g - 0.62) * 4)
                c = _mix(c, (120, 128, 70), (e - 0.18) * 5)  # dry foothills
            elif e < 0.55:
                c = _mix((120, 128, 70), (122, 104, 84), (e - 0.30) * 4)
            else:
                c = _mix((122, 104, 84), (92, 86, 92), (e - 0.55) * 2)
                if dv < 0.24:  # ash and cinder around the dragon's mountain
                    c = _mix(c, (66, 50, 50), 1 - dv / 0.24 + 0.2)
            c = _scale(c, shade)
            free = e < 0.3
            # fields around town
            dt = math.hypot((u - tx) * asp, v - ty)
            if 0.06 < dt + (_fbm(u * 12, v * 12, 61) - 0.5) * 0.12 < 0.17 and e < 0.3 and u > 0.165:
                cell = _nhash(int((x - tx * PW) // (4 * sc + 2)), int((y - ty * PH) // (2 * sc + 2)), 3)
                if cell < 0.75:
                    fc = [(170, 150, 60), (130, 138, 54), (150, 118, 64)][int(cell * 6) % 3]
                    if (x + y) % 3 == 0:
                        fc = _scale(fc, 0.88)
                    c = _mix(c, fc, 0.85)
                    free = False
            # the Whisperwood
            fn = _fbm(u * asp * 4, v * 4, 31)
            df = math.hypot((u - fx) * asp / 0.46, (v - fy) / 0.21) + (fn - 0.5) * 1.6
            if df < 1 and e < 0.5:
                cs = 2.6 * sc + 1
                gx, gy = x / cs, y / cs * 1.0
                best = 9
                for oy in (-1, 0, 1):
                    for ox in (-1, 0, 1):
                        cx_, cy_ = math.floor(gx) + ox, math.floor(gy) + oy
                        px_ = cx_ + _nhash(cx_, cy_, 41)
                        py_ = cy_ + _nhash(cx_, cy_, 43)
                        d = (gx - px_) ** 2 + (gy - py_) ** 2
                        if d < best:
                            best, bx_, by_ = d, gx - px_, gy - py_
                k = 1.15 - best * 1.4 - (bx_ + by_) * 0.35
                deep = max(0.0, 1 - df) * 0.5
                c = _scale(_mix((40, 104, 50), (22, 66, 34), deep + 0.2), max(0.45, k))
                free = False
            # a mere in the south-east
            dl = math.hypot((u - 0.83) * asp / 0.30, (v - 0.80) / 0.11) + (_fbm(u * 9, v * 9, 71) - 0.5) * 0.7
            if dl < 1:
                c = _mix((70, 120, 196), (36, 74, 150), 1 - dl)
                if _nhash(x, y, 19) > 0.95:
                    c = (160, 198, 238)
                free = False
            elif dl < 1.12:
                c = _mix(c, (160, 150, 108), 0.6)
                free = False
            # river with bright ripples
            d, i = _seg_dist(x, y, river)
            w = (0.7 + 1.3 * v) * sc + 0.3
            if d < w:
                c = _mix((60, 110, 190), (30, 66, 140), d / w)
                free = False
                if _nhash(x, y // 1, 9) > 0.93:
                    c = (150, 190, 235)
            elif d < w + 0.9:
                c = _mix(c, (150, 140, 100), 0.5)
                free = False
            # road (with a bridge-free ford south of town)
            d, i = _seg_dist(x, y, road)
            if d < 0.55 * sc + 0.25:
                c = _mix((176, 150, 104), (140, 116, 80), _nhash(x, y, 5))
            elif d < 0.55 * sc + 1.0:
                c = _scale(c, 0.85)
            if d < 3 * sc + 2 or math.hypot((u - tx) * asp, v - ty) < 0.19:
                free = False
            # gentle vignette
            ex = min(u, 1 - u) * asp
            ey = min(v, 1 - v)
            vg = min(1.0, min(ex, ey) / 0.12)
            c = _scale(c, 0.62 + 0.38 * vg)
            row.append(c)
            orow.append(free)
        out.append(row)
        opn.append(orow)

    def put(px, py, col):
        if 0 <= px < PW and 0 <= py < PH:
            out[py][px] = col

    _world_trees(out, opn, PW, PH, sc)
    _world_peaks(out, PW, PH, vx, vy, sc)
    # Emberfall: a cluster of roofs, a temple and a well
    cx, cy = int(tx * PW), int(ty * PH)
    houses = [(-6, -4), (-1, -5), (4, -3), (-7, 1), (-2, 0), (3, 2), (8, -1), (0, 4), (-5, 5)]
    for hx, hy in houses:
        hx, hy = cx + int(hx * max(1.0, sc)), cy + int(hy * max(1.0, sc))
        roof = (170, 70, 50) if (hx + hy) % 3 else (150, 98, 60)
        for j in range(2):
            for i in range(3):
                put(hx + i, hy + j, _scale(roof, 1.15 if j == 0 else 0.85))
        for i in range(3):
            put(hx + i, hy + 2, (206, 190, 160) if i != 1 else (80, 56, 40))
        put(hx + 3, hy + 1, (30, 40, 26))
        put(hx + 3, hy + 2, (30, 40, 26))
    for j in range(5):  # temple spire
        put(cx + 1, cy - 4 - j, (230, 220, 190) if j < 4 else (255, 210, 90))
    # Deepdelve: a dark adit in a timber frame, rails and a spoil heap
    ax_, ay_ = int(mx * PW), int(my * PH)
    for j in range(-2, 3):
        for i in range(-3, 4):
            if abs(i) == 3 or j == -2:
                put(ax_ + i, ay_ + j, (120, 82, 46) if j > -2 or abs(i) < 3 else (90, 60, 32))
            else:
                put(ax_ + i, ay_ + j, (14, 10, 10) if j < 2 else (40, 30, 26))
    for j in range(3, 3 + int(4 * sc)):
        put(ax_ - 1 + j // 3, ay_ + j, (90, 90, 96))
        put(ax_ + 1 + j // 3, ay_ + j, (90, 90, 96))
    for i in range(int(6 * sc)):
        for j in range(max(1, int(2 * sc) - abs(i - int(3 * sc)) // 2)):
            put(ax_ + 5 + i, ay_ + 2 - j, (96, 86, 78) if (i + j) % 2 else (80, 72, 66))
    res = [[(int(max(0, min(255, c[0]))), int(max(0, min(255, c[1]))), int(max(0, min(255, c[2])))) for c in r] for r in out]
    _WORLD_CACHE[key] = res
    return res


def _world_peaks(out, PW, PH, vx, vy, sc):
    """Mountains drawn as map symbols: lit west faces, shadowed east faces, snow caps; and Ashmaw's volcano."""
    asp = PW / PH

    def put(px, py, col, a=1.0):
        if 0 <= px < PW and 0 <= py < PH:
            out[py][px] = _mix(out[py][px], col, a) if a < 1 else col

    def mountain(ax, ay, hw, h, s, volcano=False):
        ax, ay = int(ax), int(ay)
        ridge = [int(1.5 * (_vnoise(j * 0.35, 0.5, s) - 0.5) * (j / max(1, h)) * hw * 0.6) for j in range(h + 1)]
        for j in range(h + 1):
            t = j / max(1, h)
            w = hw * (0.22 + 0.78 * t) if volcano else hw * t
            jl = (_vnoise(j * 0.5, 1.5, s) - 0.5) * 2.2 * t
            jr = (_vnoise(j * 0.5, 2.5, s) - 0.5) * 2.2 * t
            x0, x1 = int(round(ax - w + jl)), int(round(ax + w + jr))
            rx = ax + ridge[j]
            snow = (not volcano) and t < 0.30 + 0.12 * _vnoise(j * 0.7, 3.5, s)
            for x in range(x0, x1 + 1):
                lit = x <= rx
                if volcano:
                    c = (124, 92, 80) if lit else (62, 46, 48)
                    c = _mix(c, (150, 40, 20), max(0.0, 0.35 - t))
                elif snow:
                    c = (242, 244, 250) if lit else (168, 178, 204)
                else:
                    c = (156, 140, 122) if lit else (84, 74, 78)
                    c = _scale(c, 0.9 + 0.2 * _nhash(x, j, s))
                c = _scale(c, 1.0 - 0.28 * t)  # the foot fades into the hills
                if x in (x0, x1) and t < 0.9:
                    c = _scale(c, 0.55)
                put(x, ay + j, c, 1.0 if t < 0.85 else (1 - t) / 0.15 * 0.8 + 0.2)
        return ridge

    rnd = random.Random(1311)
    vxp, vyp = vx * PW, vy * PH
    # back row (smaller, hazier), then the front row
    for row, (top, hmin, hmax, haze) in enumerate([(0.02, 0.16, 0.24, 0.25), (0.10, 0.20, 0.32, 0.0)]):
        u = 0.01 + rnd.random() * 0.05
        while u < 1.02:
            h = int(PH * (hmin + rnd.random() * (hmax - hmin)))
            hw = h * (0.75 + rnd.random() * 0.35) * (asp / 2.2) ** 0.3
            if abs(u - vx) * PW > hw + 10 * sc or row == 0:
                ay = PH * (top + rnd.random() * 0.05)
                mountain(u * PW, ay, hw, h, rnd.randint(1, 9999))
                if haze:
                    for j in range(h + 1):
                        for x in range(int(u * PW - hw - 2), int(u * PW + hw + 3)):
                            if 0 <= x < PW and 0 <= int(ay) + j < PH:
                                out[int(ay) + j][x] = _mix(out[int(ay) + j][x], (110, 116, 140), haze * (1 - j / (h + 1)))
            u += (hw * 1.15 + rnd.random() * 4) / PW
    # Ashmaw's peak: a broad dark cone with a glowing crater, lava runs and a smoke plume
    h = int(PH * 0.30)
    hw = h * 1.25
    top = int(vyp)
    glowr = hw * 0.9
    for y in range(max(0, int(top - glowr)), min(PH, int(top + glowr))):
        for x in range(max(0, int(vxp - glowr * 1.6)), min(PW, int(vxp + glowr * 1.6))):
            d = math.hypot((x - vxp) / 1.6, y - top) / glowr
            if d < 1:
                c = out[y][x]
                g = (1 - d) ** 2
                out[y][x] = (c[0] + 110 * g, c[1] + 30 * g, c[2] + 5 * g)
    mountain(vxp, top, hw, h, 4242, volcano=True)
    cw = int(hw * 0.22)
    for x in range(int(vxp) - cw, int(vxp) + cw + 1):
        put(x, top, (255, 210, 80) if abs(x - vxp) < cw - 1 else (230, 90, 30))
        put(x, top + 1, (200, 60, 20))
    for k, (dx, s) in enumerate([(-0.5, 7), (0.35, 8), (0.05, 9)]):
        x, y = vxp + dx * cw, top + 1
        length = int(h * (0.85 - 0.25 * k))
        for j in range(length):
            x += dx * 0.7 + (_vnoise(j * 0.3, s, 5) - 0.5) * 1.4
            t = j / length
            put(int(round(x)), int(y + j), _mix((255, 200, 70), (190, 40, 10), t))
            if t < 0.5:
                put(int(round(x)) + 1, int(y + j), _mix((240, 120, 30), (150, 30, 10), t), 0.7)
    for k in range(int(46 * sc)):
        px_ = vxp + k * 0.95 + 2.5 * math.sin(k * 0.3)
        py_ = top - 2 - k * 0.16 - 2 * math.sin(k * 0.17)
        r = 1.2 + k * 0.10
        a = 0.85 * (1 - k / (46 * sc + 1)) ** 0.7
        for j in range(-int(r) - 1, int(r) + 2):
            for i in range(-int(r * 1.5) - 1, int(r * 1.5) + 2):
                if (i / 1.5) ** 2 + j * j <= r * r and _nhash(int(px_) + i, int(py_) + j, k // 3) > 0.25:
                    lit = 1.0 if j < 0 else 0.8
                    put(int(px_) + i, int(py_) + j, _scale((128, 118, 118), lit), a)


def _world_trees(out, opn, PW, PH, sc):
    """Lone trees and copses dotted over open grass."""
    cell = max(4, int(5 * sc))
    for cy in range(0, PH, cell):
        for cx in range(0, PW, cell):
            r = _nhash(cx, cy, 91)
            if r > 0.30:
                continue
            n = 1 + int(r * 10)
            for k in range(n):
                x = cx + int(_nhash(cx + k, cy, 92) * cell)
                y = cy + int(_nhash(cx, cy + k, 93) * cell)
                if not all(0 <= x + i < PW and 0 <= y + j < PH and opn[y + j][x + i] for i in (-1, 0, 1, 2) for j in (-1, 0, 1, 2)):
                    continue
                out[y][x] = (52, 116, 54)
                out[y][x + 1] = (36, 92, 44)
                out[y + 1][x] = (30, 80, 38)
                out[y + 1][x + 1] = (22, 62, 30)
                out[y + 2][x] = _scale(out[y + 2][x], 0.7)
                out[y + 2][x + 1] = _scale(out[y + 2][x + 1], 0.7)


ART_COL = {"dragon": (RED, {"@": YELLOW, "V": WHITE, "o": AMBER, "|": DRED})}

# -----------------------------------------------------------------------------
# Pictures: half-block pixel art with its own exact palette (made from images in
# art/src by tools/bake_art.py). Painted straight to the terminal after curses
# refreshes, so they are not limited by curses' 256 colour pairs. Where the
# terminal cannot show them the plain ASCII art above is used.
# -----------------------------------------------------------------------------
# --- BEGIN PICS (generated by tools/bake_art.py - do not edit) ---
FIG_TINT = {
    'aldous': {'h': (118, 51, 35), 's': (244, 214, 170), '#': (131, 108, 106)},
    'ashmaw': {'h': (150, 28, 74), 's': (190, 108, 51), '#': (186, 36, 65)},
    'bandit': {'h': (68, 66, 90), 's': (146, 80, 73), '#': (82, 82, 108)},
    'brannoc': {'h': (108, 51, 65), 's': (146, 82, 74), '#': (132, 59, 93)},
    'captain': {'h': (88, 89, 105), 's': (171, 105, 81), '#': (176, 41, 71)},
    'cleric': {'h': (101, 55, 61), 's': (174, 113, 79), '#': (199, 180, 176)},
    'corvane': {'h': (249, 249, 249), 's': (228, 186, 146), '#': (250, 251, 251)},
    'cultist': {'h': (148, 145, 139), 's': (173, 150, 120), '#': (89, 81, 92)},
    'dwarf_cleric': {'h': (253, 188, 145), 's': (137, 71, 44), '#': (90, 80, 90)},
    'dwarf_fighter': {'h': (76, 63, 86), 's': (234, 175, 144), '#': (84, 80, 111)},
    'dwarf_rogue': {'h': (95, 58, 62), 's': (106, 58, 44), '#': (115, 71, 76)},
    'dwarf_wizard': {'h': (137, 119, 115), 's': (217, 201, 181), '#': (82, 79, 118)},
    'elf_cleric': {'h': (139, 140, 148), 's': (239, 202, 177), '#': (148, 58, 53)},
    'elf_fighter': {'h': (172, 178, 168), 's': (215, 145, 107), '#': (96, 79, 83)},
    'elf_rogue': {'h': (47, 112, 84), 's': (210, 142, 112), '#': (53, 97, 101)},
    'elf_wizard': {'h': (95, 59, 57), 's': (169, 112, 77), '#': (129, 44, 180)},
    'fanatic': {'h': (242, 246, 248), 's': (228, 186, 146), '#': (184, 37, 70)},
    'fighter': {'h': (78, 62, 85), 's': (115, 80, 75), '#': (97, 75, 99)},
    'ghoul': {'h': (144, 163, 139), 's': (169, 118, 43), '#': (82, 86, 82)},
    'goblin': {'h': (73, 63, 91), 's': (121, 104, 81), '#': (119, 71, 63)},
    'goblin_archer': {'h': (102, 57, 48), 's': (179, 156, 123), '#': (112, 73, 71)},
    'greta': {'h': (113, 50, 57), 's': (209, 140, 104), '#': (126, 66, 72)},
    'halfling_cleric': {'h': (169, 52, 25), 's': (213, 123, 101), '#': (243, 237, 244)},
    'halfling_fighter': {'h': (125, 49, 26), 's': (143, 76, 50), '#': (133, 64, 61)},
    'halfling_rogue': {'h': (128, 42, 59), 's': (242, 144, 115), '#': (160, 51, 60)},
    'halfling_wizard': {'h': (48, 68, 138), 's': (206, 144, 111), '#': (61, 81, 166)},
    'hobb': {'h': (96, 59, 53), 's': (233, 152, 121), '#': (115, 72, 69)},
    'human_cleric': {'h': (101, 55, 61), 's': (174, 113, 79), '#': (199, 180, 176)},
    'human_fighter': {'h': (78, 62, 85), 's': (115, 80, 75), '#': (97, 75, 99)},
    'human_rogue': {'h': (63, 68, 93), 's': (110, 74, 53), '#': (97, 79, 81)},
    'human_wizard': {'h': (49, 68, 137), 's': (143, 74, 52), '#': (115, 54, 166)},
    'kobold': {'h': (206, 79, 15), 's': (114, 79, 44), '#': (185, 46, 16)},
    'kobold_slinger': {'h': (79, 66, 63), 's': (110, 54, 49), '#': (117, 72, 61)},
    'lysa': {'h': (80, 61, 85), 's': (236, 141, 103), '#': (162, 51, 57)},
    'maren': {'h': (246, 237, 216), 's': (176, 112, 77), '#': (248, 237, 213)},
    'ogre': {'h': (110, 51, 60), 's': (140, 84, 75), '#': (134, 61, 74)},
    'oswin': {'h': (143, 141, 143), 's': (209, 139, 106), '#': (111, 73, 75)},
    'pell': {'h': (103, 54, 60), 's': (144, 77, 52), '#': (125, 66, 70)},
    'rat': {'h': (66, 68, 89), 's': (228, 186, 146), '#': (124, 66, 75)},
    'rogue': {'h': (63, 68, 93), 's': (110, 74, 53), '#': (97, 79, 81)},
    'skeleton': {'h': (139, 42, 29), 's': (145, 73, 51), '#': (56, 94, 114)},
    'skeleton_archer': {'h': (75, 70, 81), 's': (195, 184, 164), '#': (111, 110, 109)},
    'snagtooth': {'h': (75, 68, 63), 's': (107, 77, 50), '#': (54, 99, 89)},
    'spider': {'h': (48, 76, 93), 's': (228, 186, 146), '#': (66, 91, 100)},
    'tamsin': {'h': (150, 46, 25), 's': (235, 175, 149), '#': (61, 95, 93)},
    'villager': {'h': (80, 63, 76), 's': (142, 74, 49), '#': (121, 69, 67)},
    'wizard': {'h': (49, 68, 137), 's': (143, 74, 52), '#': (115, 54, 166)},
    'wolf': {'h': (112, 113, 112), 's': (140, 112, 85), '#': (84, 84, 86)},
    'zombie': {'h': (101, 56, 56), 's': (103, 57, 47), '#': (88, 80, 97)},
}
PICS = {
    'ashmaw': {"w": 25, "h": 21,
        "pal": [(213, 34, 34), (197, 31, 37), (201, 31, 35), (184, 26, 36), (203, 45, 29), (169, 22, 39), (100, 5, 41), (205, 33, 34), (191, 27, 36), (73, 2, 37), (95, 4, 37), (88, 4, 41), (37, 0, 22), (176, 23, 38), (137, 14, 39), (62, 0, 37), (148, 16, 40), (127, 13, 40), (27, 0, 11), (46, 0, 26), (67, 1, 27), (36, 0, 14), (54, 0, 23), (160, 18, 39), (84, 4, 32), (183, 31, 39), (199, 111, 29), (172, 26, 39), (153, 22, 37), (113, 9, 37), (109, 9, 42), (118, 10, 42)],
        "fb": [160, 160, 160, 124, 160, 124, 52, 160, 124, 52, 52, 52, 52, 124, 88, 52, 88, 88, 16, 52, 52, 52, 52, 124, 52, 124, 166, 124, 124, 52, 52, 88],
        "rows": [
            ('     l             l', '.....m.............s', '....................'),
            ('    hh     h  h    fh', '....su.....v..s....wt', '....up.....t.......wj'),
            ('    hh    hh lhl   hhl', '....kp....tm.svs...wgm', '....Fl....p........uF.'),
            ('   hhh    h   hl   fhh', '...vkl....t...mt...lkt', '...wlg....w...v....llj'),
            ('   hhhh  hh hlhfh hhhh', '...wFEm..sm.Dmstv.sgFj', '...tkFj..v..r.ptt.wFgp'),
            ('    hhflhhhhhhhhhlhhhh', '....FDEtvjtwqwjpvtkFEt', '....roE.pglkogkgp.gro.'),
            ('  l fhhhhhhhhhhhhhhhf l', '..s.DxFjpoxErFxCppEor.s', '....DfrEjDddEncFlkrCr..'),
            ('llh hfhhhffhhhhhhhhhh hhl', 'wuj.uBxFyFocEixFlDCnj.wtw', '..g.mBdEgFoxCdrDElxBp.jy.'),
            (' fhhlhhhfhhhhhhhhhhhflhh', '.rosmCrqqCionqbnqCEqmkrr', '.rxF.poiqffqqCdBCxojm.qF'),
            (' hhhhhhfhhfhhhhfhfhhhhhh', '.vFngDxhfxxfrdbxxBorjxFw', '..tgFadhinxxobdxCBxdDlw.'),
            (' hhhhhhhhhhhhhfhhhhhhhhh', '.uyDEiibdabBxhfdxnndEguy', '..CcrjEobnnhBifBbfljyCrv'),
            ('   hfhhhhhhhhhhhhhhhhhh', '...ogjFgEfqaBnCirklllrs', '...tgoxeArrdqfooAAorkp.'),
            ('  hhhhhhhhhhhhhhhhhhhhh', '..srcfBfCkyqooljCqxoxFm', '....rhCooEFfCxEgroqnF..'),
            ('    hhhhhhhhfhhhfhhhh', '....snhhaoFqnCEgdnBqm', '.....tqdcfgCnxkDdBow.'),
            ('       hhhhhhhhhhfh', '.......jqxFdhnFrCjs', '.......ujfEnbzEojj.'),
            ('       hhhhhhhhhhh', '.......vloqrfFqFyu', '........kqjdxnlDE.'),
            ('        hhhhhfhfh', '........yxpddbtou', '........sqricbkov'),
            ('         fhhhhhf', '.........ycbbfBk', '.........yqxoqrk'),
            ('          hhhhhh', '..........oEpgEs', '..........woCqu.'),
            ('           hhhh', '...........rbos', '...........wxu.'),
            ('            h', '............r', '............w'),
        ]},
    'rat': {"w": 34, "h": 13,
        "pal": [(156, 97, 43), (161, 98, 47), (201, 164, 38), (12, 18, 31), (9, 14, 27), (105, 38, 50), (5, 12, 25), (114, 36, 52), (117, 50, 63), (73, 21, 36), (101, 54, 31), (61, 28, 39), (15, 20, 34), (75, 28, 39), (94, 36, 45), (12, 15, 28), (27, 32, 48), (138, 73, 51), (84, 31, 42), (129, 36, 55), (42, 13, 24), (28, 12, 24), (219, 146, 49), (20, 26, 41), (166, 59, 71), (92, 15, 37), (41, 49, 69), (119, 80, 33), (39, 30, 44), (59, 18, 30), (31, 38, 56), (36, 42, 60)],
        "fb": [130, 130, 178, 233, 233, 52, 232, 88, 88, 52, 88, 52, 233, 52, 52, 233, 234, 95, 52, 88, 52, 233, 172, 234, 124, 52, 236, 94, 235, 52, 235, 235],
        "rows": [
            ('       hhhl              lhhh', '.......nfDv..............Cjhl', '........ni................iu.'),
            ('      hl hfl   lllll    lfh ll', '......vv.fEx...pxqqx....qFo.uj', '......j..nE..............FD...'),
            ('     hhf hhh hhhfffhhhlhhhh fhh', '.....jjD.Dqx.gxEAAAFqxgexCv.jnu', '.....ssD.vxe.pEAAAAAAq..dl..jsj'),
            ('     hfh  hlhhhhhhhhfhhhlh  fhh', '.....sou..vedxFFFFFFAqmeeD..jsn', '.....hoD..g.xEAAAAAAAFEx....joo'),
            ('     hhh  hhhhhhhhhhhhhhhl lhhh', '.....fiD..gEAExFFAFEExEFqd.ujin', '.....utf..mxxAFmxqqxmAFqx...ht.'),
            ('       hh l lhhhfhhfhhhlllhhh', '.......nj.p.zmEqmqqmEEpupgvnl', '.............hmmmxxmxmt......'),
            ('      l   hhhh hhhhfhhhlhh  hl', '......p...eduz.gqFFqgvzemg..gp', '...........m...pxqqqp...p.....'),
            ('     lh l     hfhhfhhh    l  hl', '.....dp.g.....pxxqqxxe....g..de', '......g.......xxmEqmqm.......e.'),
            ('    lh     hlhhhhhhhhhhhh    hh', '....ep.....ggpmxDllCxddgg....ee', '.....m.......dgehyyoeem......gm'),
            ('     fhhhh  hhhfhhfhfhhh  hhlhh', '.....mmggg..gddgDosugpdg..ggpxm', '.....mde.....eegvjspgee......md'),
            ('     hhhh    hhhhhhhhhh   hhhh', '.....gmeg....eevgegevpg...ggdm', '......pmd.....uwBkBBw......mm.'),
            ('      hhfl    hhhhfhhh    lhh', '......emdg....ucDsoDcv....edd', '........d.....CBkooBBd.....p.'),
            ('         hll  hhhhhhh   llh', '.........dpe..eorbaro...ped', '.........g.....mssslp......'),
        ]},
    'wolf': {"w": 34, "h": 20,
        "pal": [(122, 123, 122), (122, 123, 122), (74, 76, 78), (149, 150, 149), (134, 134, 134), (130, 131, 131), (68, 69, 70), (70, 71, 72), (116, 118, 117), (75, 77, 76), (120, 121, 120), (56, 57, 58), (142, 143, 142), (127, 123, 118), (124, 125, 124), (25, 25, 26), (40, 40, 41), (62, 63, 64), (47, 49, 49), (106, 107, 107), (92, 93, 93), (152, 130, 109), (55, 53, 51), (72, 73, 74), (32, 32, 32), (67, 65, 63), (115, 114, 111), (93, 79, 66), (79, 81, 82), (155, 141, 129), (168, 164, 160), (210, 206, 201)],
        "fb": [243, 243, 239, 246, 102, 244, 238, 238, 243, 239, 243, 237, 245, 244, 244, 234, 235, 237, 236, 242, 59, 101, 237, 238, 234, 238, 243, 239, 239, 246, 248, 252],
        "rows": [
            ('    lhh                    lhl', '....yCp....................uCy', '.....hu.....................x.'),
            ('    ffhhl                lhhhf', '....qquxl................rrtqq', '....qqra..................ezyq'),
            ('    h  hhhl             hhh  h', '....w..Cewp.............sfu..w', '....l..ruf..............ftx..l'),
            ('    hh lhhhhl llllll  hhhhl hh', '....sw.ywAegp.pqqxpp..rfily.ws', '....ws..yzkd..........moxy..sr'),
            ('    hf hhhhhhhhhhhhhhhhhhhh  h', '....gp.qcytoouuuiAuuuaoiycs..x', '....qp.lCscdfaaaaaoaaodCqjr..s'),
            ('    fhl hlhhhfhhhhhhhhhhlh lhf', '....qlq.ywxooaaaaaaaaooCry.ysq', '....qx....Aaaatuiiuuiaai....hq'),
            ('     hhlhhffffhhhhhhhfffhhlhhh', '.....wrgptaaaaCcCCcCkaaaAyhlsp', '.....lp.AaaaaaauccCaaaaaaA..l.'),
            ('    lllhhhhhhffhhhhfffhhhhhlll', '....hAtjkaaaaaatCCtaaaaaaaCttC', '.......atfoikaakiikaaaioeta...'),
            ('  lhhfhhhhhhhhhfhhhhhhhhhhhhhhhl', '..qleotCCueehCaokkaaCgfmuCCtoezq', '...uoojjjlgumhgouuoxrmugljjjkot.'),
            ('  hhhhhhhflhhhhhhhhfhhhllhhhhhhh', '..ptfauwrpupCAwtqqtstuptprlCafiy', '..oACws..p.yscsl..wsjsy....qsCtf'),
            (' hhhhhhhhhhhhllhhhhh hhhfhhhlhhhh', '.hdArpylqyEwvpqyyyqp.vsFqqlyqltdx', '.xCCcqgjjqrex..uuutq.lehqjjh.cCCg'),
            ('hhhhfhhhfhhllhhhhffhhllhhfhhhhhhfh', 'luAthsycjclrypCAuutuyplscjjqqhtiul', '.CmCh.shjjj..skttutol..cjjxs.gCmu.'),
            ('lhhfhfhhhhfhlhhhhhhhhlhhfhhhhhfhhl', 'smmCrqqrjjjhplttAittryzjjjrsyrCmml', '.keCxqypgcjp.uouCCuot..cjgypqxCok.'),
            ('hhhhhhf  hhlhhhhhhhhhhlhh  hhhhhhh', 'yrgfCCy..gwplaxrssrgorpsg..pCCfhry', '.qsdfjy..py.ruw....suh.pp..yxoErq.'),
            ('  hhhhhf   hhhhh  hhhhh   lhhhhh', '..leAclp...qylxy..yhryq...psjtex', '..CCjCcp....pwwz..zwzpp....cCjju'),
            ('  hhhffhl   fhhhhhhhhf   lhfhfhh', '..ssctjhq...yvvDvvEnDy...qgjtCqr', '....xtjr....ydnt..utdy....ljuC..'),
            ('    hhhfhhh  hhl  lhh  hhhfhhh', '....rhuussp..hil..stC..pssCuhh', '......tugx...ys....rp...cgCa.p'),
            ('      hhhh   hhhhhhhh   hhhh', '......juur...qkurzgmq...suCu', '.......yxz...pAFggFfy...wjq.'),
            ('              hhhhhh', '..............rzuCzr', '...............qyyq.'),
            ('               hhhh', '...............sghl', '................yq.'),
        ]},
    'goblin': {"w": 34, "h": 19,
        "pal": [(93, 107, 62), (95, 79, 117), (106, 121, 70), (42, 36, 55), (122, 92, 71), (79, 92, 56), (65, 30, 28), (82, 68, 101), (47, 24, 25), (65, 43, 35), (50, 33, 35), (89, 88, 57), (80, 70, 92), (70, 58, 87), (73, 81, 51), (96, 44, 35), (105, 87, 115), (25, 14, 17), (83, 54, 44), (46, 35, 27), (78, 41, 33), (32, 31, 22), (104, 92, 63), (65, 71, 41), (89, 77, 104), (35, 18, 19), (59, 49, 69), (31, 27, 42), (47, 56, 36), (141, 133, 88), (47, 40, 61), (55, 47, 66)],
        "fb": [58, 60, 65, 235, 95, 58, 52, 60, 234, 236, 235, 59, 239, 59, 58, 52, 60, 233, 52, 235, 52, 234, 59, 23, 60, 234, 237, 234, 236, 101, 236, 236],
        "rows": [
            ('                lhl', '................nAd', '.................m.'),
            ('            llhfffffhll', '............BbEhnhEdEbd', '..............bhnhEdn..'),
            ('          lhhhfhfhffhhhfl', '..........dEbbbmnhFBFAhnF', '...........bqybnnnFBAFAn.'),
            ('         lhhhhhfffhfhhhhhh', '.........nybhyhnnnFBFFAAhr', '..........hhyhnnnnEBEAEFAh'),
            ('        lffhhhhhhhffhhhffhl', '........dbhybhhnFhdBdAFAAAB', '.........bhhhnAFhndBBdAAAE.'),
            ('        hhhhhffhhhhhfffffhf', '........AhnnnhhyhqFddddddFB', '........dnhhhhhnFABBddddddB'),
            ('  hhfhllhhhhhhhlhhhlllhhhhhllhfhh', '..vfxCafhhhAFdvfEEBofaBBddEoaCxft', '...txx..nA.jxaa.vd....xj.Bd..xxt.'),
            ('    hhhhfh hhhhfhhhhhhhh ffhhhh', '....voCvBE.gupccfaoacsug.Brvvov', '.....Ca.Bn...gjcacfcsg...Br.fx.'),
            ('lhh   hfhhhhhhhhhhhhhhhhhhhhh', 'zju...oxBnxfCxzjCcCCzxvCCBrCf', '.ks....xCyCafovCvxvvvCoxtdtor'),
            ('  hhllhh hfhhhhhfffhhhhh h  hll', '..ikrrrr.hBaDDaCacoCfcaf.E..ziz', '...i..i..nB.xfxoacoxCxC..d..r..'),
            ('   lfhhlhhh hlhhhhhfhlh hflllhl', '...zirzzzFF.tvoaxDCCCvt.rBzrzzi', '....izi.udn.C.sxvCvCs.C.BB...k.'),
            ('  hhhhhhhhhlhhhhhhhhhhh fhfffhfh', '..rkijiigihBvCeDellDDvt.dzguijjz', '...jkikkzzn.CosoDDDloxC.drguiijj'),
            ('  lhhfhhhhhhhhhhhhhhhhhlhhhf hhhf', '..zzrzkkjiEdCxeeeweeejCrBggu.kzzz', '...uizijugzE.axjsswjtx..iupu.rikz'),
            ('  hhhfhffhh  hhhhhhhhh  h hhhhhhhh', '..zikzkussr..xccoCxxoC..z.pgrkkzrr', '....rzrusut...CCzzrvC.....gz.z....'),
            ('       hhffll lhffhf lhhh h h', '.......issuiz.rupggi.zrii.i.r', '........ksu....ppgpi..ikr.r..'),
            ('         hfhhlhffhhffhh', '.........jsjzigppupirzi', '.........rssu.zpppuir..'),
            ('          hhhhlhhfhh', '..........zujkruppgi', '...........ksj.iupir'),
            ('            hhhhhfh', '............zizzipz', '.................p.'),
            ('                 h', '.................g', '..................'),
        ]},
    'goblin_archer': {"w": 34, "h": 20,
        "pal": [(83, 42, 33), (82, 42, 33), (0, 30, 18), (80, 41, 33), (39, 95, 38), (1, 41, 26), (0, 61, 41), (1, 74, 46), (47, 24, 26), (62, 130, 50), (3, 49, 26), (38, 18, 20), (78, 50, 36), (109, 85, 54), (7, 84, 47), (26, 12, 13), (43, 21, 22), (41, 107, 47), (53, 123, 49), (73, 37, 32), (46, 23, 23), (23, 97, 46), (5, 38, 18), (56, 28, 26), (65, 32, 29), (26, 77, 33), (21, 59, 25), (19, 12, 10), (0, 53, 34), (10, 62, 33), (31, 14, 15), (33, 17, 17)],
        "fb": [52, 52, 234, 52, 22, 17, 23, 23, 234, 64, 22, 234, 52, 59, 22, 233, 234, 22, 29, 52, 234, 22, 52, 235, 52, 22, 22, 233, 23, 22, 233, 233],
        "rows": [
            ('              llhhll', '..............FxFFxl', '................ii..'),
            ('           llhhhhfhhhhl', '...........ltydtyxtbyEu', '.............aaatxdaad.'),
            ('          hhhhhhhhhfffhh', '..........ltaaaayidbaadl', '..........ybbbbdtxybaaay'),
            ('        lhfffhhfhfhhfhhhhl', '........Fuddbaaaabytabtdil', '.........xddbbbabbaaaabty.'),
            ('hll     hhfhhhffhfffhffhhfl    llh', 'ckz.....uydabbaaabaabaabyip....zkc', '........ixdbaaaabbaaaaadxi........'),
            ('  hhhllffhhhfhhhhhhhhhfhhhfllfhh', '..kezskEixdyybbyytydadydiuFwszek', '..DCh..EiFixyyttxyttttyiFiF..zkD'),
            ('   hh hhhlffhhh   hhhhhhlfhhhhh', '...vf.Aqiqiiutd...pldyqiquukcfv', '...hg..uu.iitxx.....qttq.ui..Cz'),
            ('   hh  fhhhhh   ll   hhhhhf  fh', '...wv..iiqutu...cc...udtqqi..ok', '....o..i.lix..........qxy.i..o.'),
            ('     lfh h hlhhhhhhhhl  hlhfl', '.....piq.l.qngDohhzhkn..tqliE', '......iF.p...FwDooDfF.....Ei.'),
            ('     ffh hflhhllhhl hhlh hhfh', '.....uiu.EcgmncfgDk.nmCk.xqii', '.....uiy..c.fg..ss..gC.f..yiu'),
            ('     hhh    hhhhffhhhh    hhh', '.....iiy....kvrossoerC....xii', '.....qyx....rjhrssrDsr....uyu'),
            ('    hhfh   hhhhhhhhfhhh   hhhh', '....lqtE...fessAeekjsrc...Bdlq', '....ixt....ChjjjCksjjog....txx'),
            ('  lhhhfhl   hhhhhfhhhh   lhfh hl', '..uqpxiEp...gvrsressvg...ppix.lq', '...p.lil....chCzeeoChw....Fiq.F.'),
            (' hhlhlhhhl   hhhhhhhh   lhhhlhlhh', '.EqpFqEuFu...fhhDDhhf...lqqFqFplE', '.......Ep.....ksjjjC.....lF......'),
            ('     hh hhl l  hhhh ll  hh lh', '.....Ep.Eyp.l..wCkf.Bq..yF.lF', '......q..q..............u....'),
            ('       h hh lhhllllhhl hh h', '.......F.pu.xqulqxlxlx.qF.E', '..........d..up....Ey..t...'),
            ('          h  hhhllhhh  h', '..........b..iyxytyti..b', '..........d....u..tE...d'),
            ('          h     hhh    h', '..........t.....iiE....t', '..........x............i'),
            ('          h            h', '..........l............l', '........................'),
            ('', '', ''),
        ]},
    'snagtooth': {"w": 34, "h": 16,
        "pal": [(109, 95, 74), (77, 44, 28), (15, 25, 28), (103, 110, 122), (23, 32, 49), (112, 107, 75), (72, 71, 73), (80, 158, 51), (184, 159, 98), (66, 84, 110), (250, 206, 36), (116, 133, 150), (32, 75, 40), (25, 56, 38), (234, 193, 67), (91, 145, 54), (41, 20, 33), (131, 55, 61), (115, 84, 35), (12, 29, 20), (40, 24, 17), (183, 136, 38), (120, 122, 102), (68, 138, 49), (120, 18, 25), (43, 95, 45), (172, 170, 156), (41, 56, 51), (61, 42, 22), (22, 50, 28), (80, 64, 33), (74, 94, 43)],
        "fb": [241, 52, 234, 242, 234, 59, 238, 35, 143, 24, 220, 244, 22, 23, 214, 64, 234, 88, 94, 234, 234, 136, 243, 64, 88, 22, 248, 236, 236, 23, 58, 58],
        "rows": [
            ('          lll  lhfl  lll', '..........wAw..uBgu..wAw', '................gg......'),
            ('          hhh lhhhhl hhh', '..........aAB.bwyywb.BAa', '...........ww..abba..ww.'),
            ('       hhllhhhhhfhhhhhhllhf', '.......gwBuuwBqbssbqBwuuBwa', '.......aA..cassCsfCsssc..Aa'),
            ('       lfhhhhlllhhlhlhhhhhl', '.......guaEECzxxCCxtxCEEfcg', '........uECcn...mm.x.B.CEu.'),
            ('      hhhhhhhhhhhhfhfhhhhhhh', '......BluucEfhphhhhppfEcuuAB', '.......uC.nfrpxppphxprfn.Cu.'),
            ('  hll  l  hhhhhffffhhhhh  l  llh', '..mzm..u..marxpphhpxxrsm..q..mzn', '..........DFpfhphhppfpFD........'),
            ('   hhhhh hl hhhhhhhhhh lhlhhhhh', '...DDzzt.tt.txhxhhphxD.ttttzztD', '....mDDz.D....mmzzzm....D.ztDm.'),
            ('    hff hhhlhhllhhllhhlhhh ffh', '....nmt.DnmmyytDmmDtyymmnD.tmn', '.....mt.txz.nD..xp..Dn.zzt.tm.'),
            ('  lllhhhhhhhhfhhffhhfhhfhhhhhlll', '..egCDmttparFmmzhhzmmFrfpttmDCge', '.....CnD.zffhmDmhhmnmhafz.DnC...'),
            ('lhhf llhl fhhhhhhhhhhhhf lhll fhhl', 'cgle.CEDq.BxmxztnnDzxzfB.qDEC.edgc', '.lje...u..BzxhhxzxhhhxmB..u...ejl.'),
            ('fffh hh fhfhhhhhhhhhhhhfhf hh hfff', 'gljc.bu.qtmztmxhhhhhztnmtq.ub.cjlg', 'glje....q.mmCvvszmmnCvDm.q....ejlg'),
            ('hhhh    flhhhffhhhhhhfhhlf    hhhh', 'elde....qqnDokkkvfsvoitnqq....edle', '.jlj....q.ctkkkiCEEfii.c.q....jlj.'),
            (' hhfh   hf hffhhhhhfhhl fh   hfhh', '.Blde...qq.CkkiCmxxzmEn.qq...edlB', '..gdj....q.ukksDDDnzxx..q....jdg.'),
            ('   hhh   h  hhlllll hh  h   hhh', '...dde...q..ioqqqqq.DD..q...edd', '...ejj......bv..............jje'),
            ('     hf     hhffhhffhh     fh', '.....gc.....quqqqqqqqq.....cg', '......c.......qq..qq.......c.'),
            ('', '', ''),
        ]},
    'bandit': {"w": 34, "h": 17,
        "pal": [(67, 62, 95), (50, 48, 72), (71, 65, 99), (51, 49, 74), (39, 40, 58), (164, 98, 77), (17, 17, 28), (214, 120, 115), (39, 41, 59), (201, 121, 110), (94, 57, 57), (186, 115, 107), (71, 32, 37), (248, 171, 153), (120, 15, 34), (42, 20, 22), (228, 147, 115), (59, 43, 52), (166, 88, 74), (141, 79, 71), (56, 53, 81), (23, 22, 35), (40, 35, 50), (132, 49, 52), (79, 45, 40), (16, 16, 25), (35, 35, 52), (28, 10, 14), (59, 25, 29), (29, 28, 43), (41, 42, 61), (46, 45, 67)],
        "fb": [24, 236, 60, 236, 235, 131, 233, 174, 235, 174, 59, 131, 52, 216, 88, 234, 173, 236, 131, 95, 53, 234, 235, 88, 52, 233, 235, 233, 52, 234, 236, 236],
        "rows": [
            ('              llhhhll', '..............AcEueuD', '................cac..'),
            ('            lhhhhhhfhhl', '............uucccdFiubb', '.............cdduFbiEd.'),
            ('hhh        hhhfh  hhhhhh', 'yfB........AuuEd..gFEFbv', 'fqy........eFEEA...eiiiA'),
            (' hh        hfhhhl lhfhhh', '.yC........biADzB.mDEiAF', '..m........EiFe....BEFve'),
            ('  hfl     hhhhhhhhhhhhhhl', '..pmB.....DDeApxfslopeAvg', '...m......AzEvtqnnhxoviz.'),
            ('   hfl    f hlhhhhhhhlh f', '...BmB....D.dmtqnjxjkCd.v', '....m.....D.A.ypmxBwy.A.v'),
            ('    hfl   fhhhhhhhhhhhhlh', '....Bmp...DzpfhjtjssxsvDv', '.....m....DD.BkuucurpB..A'),
            ('     hhllhhf hhhhhhhhh ffh', '.....BmCBDzD.vDEdubEDg.Dvv', '......C..F.D..AeiEveA..DvE'),
            ('     lhhhhlf  hhhhhhl  hlhl', '.....pBkrivv..vEEEgeD..vvEv', '......kwe..v..AiiiiA...D...'),
            ('    hhfhf f   lhhhfhl  hhlfhl', '....prvDD.A...viiAEAg..zDzDDv', '.....gvaD.A....AEvED....v.Da.'),
            ('   lhhhhhhhl lhfhhhh l hhfhhfhhl', '...agFDDDvDD.vvEEzEF.D.zvgeAeFga', '....uvA.v......Ez.DD...D.gFgevu.'),
            (' lhh  hhlhll hl h l lhh lhhh  lhll', '.Dvi..zAFDvz.Av.E.v.vAg.AFgD..vFag', '..ue...v..............v..D.....i..'),
            (' hhhhhhfhhllhll     lhhhhlhhlhhhhh', '.auviDvAeFFegvD.....DvgidDgDueAvuu', '.AEiDEDAAg..v........Aib..E..F.EFD'),
            ('   hhhhhhhlhhhhhllhhhhhlhhhhhlhh', '...AidzzeeivFdeiFFvAiEEADivudvAD', '....giuA.D.D..Ab..AgeD..AEuE....'),
            ('      hhhhhhhhlllhhhlhhhhhh', '......AdaeAEivuuFgADvziAdFA', '........edbddu...D...AAFve.'),
            ('          h  hhhlllhhhhlh', '..........g..vDvgvFAEeggA', '...................dv.z..'),
            ('             hhhlll', '.............gDgAAz', '...............v...'),
        ]},
    'kobold': {"w": 34, "h": 16,
        "pal": [(222, 115, 29), (214, 76, 1), (131, 93, 39), (103, 25, 4), (160, 116, 51), (248, 99, 1), (239, 91, 0), (208, 68, 2), (120, 83, 32), (127, 38, 11), (205, 108, 23), (86, 29, 8), (124, 27, 5), (146, 109, 26), (185, 83, 23), (229, 83, 0), (194, 60, 4), (109, 41, 12), (118, 80, 81), (209, 110, 37), (51, 10, 0), (80, 21, 2), (111, 35, 6), (35, 4, 0), (125, 54, 18), (171, 54, 8), (229, 145, 23), (86, 52, 31), (55, 24, 15), (150, 46, 10), (124, 40, 3), (132, 50, 2)],
        "fb": [166, 166, 94, 52, 130, 202, 202, 166, 94, 88, 166, 52, 88, 94, 130, 166, 160, 88, 95, 166, 52, 52, 88, 52, 88, 124, 172, 52, 52, 124, 88, 88],
        "rows": [
            ('          lh       hh', '..........iu.......BC', '...........B.......Cc'),
            ('       lhhh        lfh', '.......iBeB........xei', '........eB..........ee'),
            ('     lhhhlhhhhffhhlhhhf', '.....BBeiFxjqqbhqliiceB', '......ncy.hqbpbhbr.nnnB'),
            ('    lhhhhhhhhhhhhhhhhhh', '....uccBzpgpfbbffbycncB', '.....BlzhbqhbgfgbhpBii.'),
            ('llllhhffhhfhhhhfhhhhhhhlll', 'xEzgxFqqggggqfggghqhyluoDl', '....jpqqphgpbbfgzwwqDqb...'),
            ('hhhhhhhhfhfhhhhhhfhfhhhhhh     lll', 'xzmdlzbpbfgphzqFAAuhqwvmDD.....xCC', '.vgjnFgbbgggqhmkeAvhjlDqq.........'),
            ('  hhhhhhhfhfhhhhhhhhhhhhh  llhhfh', '..DqvpphhbDvqzxcnDqqvjhpu..vzvrBB', '...jzbbbDbhvdhhqzzzDlqzx.....lBB.'),
            ('   hhhhfhhhhhhhhhhhhhh   lhhhhh', '...CgpfgqbozppaDEkovdu...CldlsB', '...jpgpgkoylrFFkkod.......sssC.'),
            ('   hhhhhhhhhhhhhhhhll llfhhhh', '...qghDrrzokkooDyddDx.vEdECBx', '...vFu.udFDEdlvvdqh.....dx...'),
            ('    llllhhfhhhhhfhhhhhhh', '....udxjxjjdotkFzzpbmEyu', '........DDjkaaoqzxvlodu.'),
            ('   hhhhhhhhhffhhhhhhhhh', '...uDzDzwCltaaaozvEljzz', '...xzwdx..oaaakFEruxbbv'),
            ('    hh   lhhhhfhhhllhllllhhh', '....lu...uoatodydddFxrEzqxxx', '..........jzFwdjzD..F....hzu'),
            ('        lhhhhhhhhhhhhhhhhh', '........vjwrEvlzbhwDhbqzmv', '.........wFvuzoEggmzzFvx..'),
            ('     llhhhhhl hhhhhh', '.....uwdEljlu.CrwhqC', '.......luuzD.....uDw'),
            ('  lhhhhlllhhh    lhhh', '..duywuFDqmjd....umDx', '...wl.....Dmx.....zhj'),
            (' hhh   hhh      hhhhhh', '.dvx...uoD......vpjmhE', '................lw..lr'),
        ]},
    'kobold_slinger': {"w": 34, "h": 15,
        "pal": [(93, 56, 31), (128, 82, 41), (180, 75, 55), (77, 40, 35), (97, 77, 62), (67, 33, 24), (78, 29, 32), (114, 90, 68), (99, 73, 51), (42, 34, 35), (151, 93, 50), (92, 63, 47), (161, 78, 53), (55, 30, 19), (77, 57, 48), (65, 24, 26), (133, 96, 59), (117, 73, 41), (157, 59, 50), (110, 60, 38), (112, 43, 40), (144, 56, 49), (52, 20, 19), (63, 46, 43), (76, 39, 25), (31, 11, 7), (32, 20, 22), (91, 34, 33), (160, 113, 67), (131, 49, 45), (88, 48, 27), (96, 43, 37)],
        "fb": [52, 94, 131, 52, 239, 52, 52, 59, 59, 235, 94, 59, 131, 235, 237, 52, 94, 94, 124, 88, 88, 124, 52, 236, 52, 233, 234, 52, 130, 88, 52, 52],
        "rows": [
            ('            fh  lll', '............jx..zAn', '............jo.....'),
            ('            hhhhhhhhhh', '............jhliljjxeA', '............xiqhelChjj'),
            ('l          hfhhhhhhffh  llh', 'p..........xohhhhexAAj..zDF', '...........jolexAAAAAA....w'),
            ('hhhhll     hfhhhhfhhhllhhh', 'zuuzvp.....jjxjAAAAAjwDBvg', '.wBs.......AjjAjjAjj...vF.'),
            ('  hhhhhhhhhhhhhhhhhhffhhh     hhhh', '..ABDssFpzAAwpdoexpwguDBA.....naaA', '...pppussuBuFqqlqllegugA......EAEn'),
            (' lhhffhhhhfhhhhhhfhhhhhh     hhfhf', '.BEBBpAfuDuDcsrhqeiFsgwz.....nwrrn', '..DDBpgAwBugBmsvueBDDwp......yyrtn'),
            (' hhhhffhhhhhfhhhhhhhhhh    lhhfhhh', '.FuuBgpwAButqaDvvDvDtiA....nAyaEyz', '.gpBggp.pgDuqCrBDssvup......branz.'),
            ('hhhhhh  lhhhhhhhhfhhhhhhhhhhhhh', 'zDppzz..ppDvDDuDDccvFpEynyEyEby', 'wrd..A...EBDBuvsvcsDu...Az..yEA'),
            ('hhhllhhhhhhhhhffffhhh      lfh', 'ztlzwzzBpafpgFuuvvDDB......nEn', '.Bp..FDgfqtwwpuuvvvvw.......E.'),
            (' hhhhhhhhffhfhfhffhhhl   hfhhl', '.gBpduttfqqwppgDscsspw...zFuDw', '.EugByfzzqqfpgguscCcg....uFBB.'),
            (' hhhhf lhhhhhhhhhhhhhf  hhfhhh', '.zDufn.wwtkrfpgguDccBB..wFuvBz', '.....n..yfqqEyyppFDvwB..FDuup.'),
            ('     hlhhhhfhhhhhhhhhhh hhhhh', '.....yzabytbEarbttFgwan.wgFgz', '.....f.nqkybtftrrbnzEEz.EEwA.'),
            ('      hhhhhhhhhhhhl hhhhhh', '......fyEbbaEEpwffA.nFyEyy', '.......wyEEdyaifda...gfta.'),
            ('        hhhhhhhfhl   hhhh', '........zyaEfyoodx...uuBA', '..........wfpfxox....wvz.'),
            ('            hhf       h', '............zjx.......z', '..............x........'),
        ]},
    'cultist': {"w": 33, "h": 20,
        "pal": [(204, 200, 186), (170, 167, 158), (59, 56, 58), (82, 79, 79), (234, 227, 211), (144, 137, 134), (66, 56, 71), (179, 173, 164), (151, 146, 144), (138, 131, 134), (160, 158, 150), (55, 44, 68), (49, 40, 56), (220, 210, 188), (47, 44, 45), (74, 68, 74), (199, 191, 175), (41, 33, 41), (97, 85, 101), (249, 243, 220), (192, 181, 170), (247, 237, 192), (93, 84, 87), (110, 87, 80), (26, 22, 30), (123, 113, 125), (167, 134, 124), (115, 110, 110), (105, 91, 112), (84, 70, 95), (132, 124, 119), (134, 128, 129)],
        "fb": [251, 248, 237, 239, 254, 245, 237, 145, 246, 102, 247, 236, 236, 187, 236, 238, 250, 235, 240, 255, 249, 230, 240, 59, 234, 243, 138, 242, 241, 239, 244, 244],
        "rows": [
            ('             llhhhll', '.............pfdkdid', '...............keu..'),
            ('           hhfhhhhhhhhl', '...........yCkkheukfCoy', '...........CfkuetnbkkB.'),
            ('          hhfffhfhhhhhh', '..........dzkkntttebkzD', '..........CikknatetebiC'),
            ('         hhffhhhhhffhhhh', '.........yBkkkqnntetekBo', '.........ozkkqeaaeettbzw'),
            ('         hhhhfhhhhhhfhhh', '.........gzkbteBywnttufd', '.........wjiqtd...oatbiC'),
            ('        lfhhhh      hhhhh', '........rCizep......ekjCr', '.........CFuk.......BqCzg'),
            ('        hfhhhhh   hhhhhhh', '........gCsaoiB...dichszd', '........sCEx.........czCC'),
            ('       hfhh           hhhh', '.......yDDf...........zzsm', '.......gDCc...........oFDp'),
            ('      lfhh             hhhh', '......yDDz.............fCCy', '.......Dsd.............czDm'),
            ('     lhhh               hhhl', '.....lmDB...............EDlw', '......rsp...............rzm.'),
            ('    hhfhll             llfhfh', '....oDykgl.............mlkysw', '....yCyf.................krsd'),
            ('  lhhhh hhh           hhhhlhhhl', '..woCwr.kDm...........rlFrmBrwC', '...FBDC.ykD...........ljo..sBk.'),
            (' lhhhhhhlhhh         hhfllfhhhhll', '.rEzjzzomrjg.........yzomgzCkzFyy', '..ywsfCB.opx.........dpo..zizBr..'),
            ('hhhhhhhfhhfhhlllhlllhfhfhhhhhhhhh', 'wDDolsizcgdFpqBExcBkpBpBpBzsgdgDs', '.lBBglFzspdxe...q...BBuBDCjgliDg.'),
            ('  hhhhhhhhhhhhhfhhhhhhhhhhhhhhh', '..wilscifsBzcbtvvnbEbhcgfkcyFzD', '...jdFDrkqwjhEBvtvEdlrBhacrgqB.'),
            ('    hhhhhhhhhhhhhhhhhhhh hhhhh', '....fzzmyBujCzhvtvEcinqj.dxibp', '....ribgBD.BubbnvnknqBr..ishd.'),
            ('     hhhhhhhhhhhhhfhhhhhhhhh', '.....cbzpbzmycBEuEApyoFcwEBF', '......lilfnisdy.DyA.mqirfoE.'),
            ('       hhhhhhhfhhhhhhhhhhh', '.......dzobebjfpsAAokimwxl', '........gggkabfxxxp.zsyzry'),
            ('         hhhhhhhhhlhhhhh', '.........DyDCjFmpoyyyrpp', '..........l.DDl..y..ryC.'),
            ('           h hf      h', '...........y.Dl......l', '..............l.......'),
        ]},
    'fanatic': {"w": 34, "h": 20,
        "pal": [(211, 209, 218), (145, 133, 148), (135, 16, 41), (121, 12, 38), (136, 119, 139), (104, 12, 42), (240, 244, 248), (76, 7, 30), (57, 101, 155), (75, 17, 44), (99, 52, 76), (116, 86, 107), (48, 4, 29), (224, 224, 231), (99, 9, 36), (126, 109, 125), (108, 118, 146), (104, 86, 103), (112, 135, 163), (140, 201, 240), (72, 42, 62), (122, 24, 52), (38, 25, 43), (101, 159, 213), (163, 150, 165), (29, 8, 28), (183, 226, 243), (77, 75, 97), (188, 181, 192), (31, 39, 67), (146, 24, 45), (181, 33, 49)],
        "fb": [252, 245, 88, 88, 244, 52, 255, 52, 24, 52, 53, 95, 52, 254, 52, 243, 67, 59, 67, 117, 52, 88, 234, 74, 247, 17, 153, 239, 250, 17, 88, 124],
        "rows": [
            ('  llh                        hll', '..wDw........................zDw', '................................'),
            ('  hhh                        hhh', '..wiD........................Diw', '..ixi........................Bxi'),
            (' hhffh                      hhfhh', '.DBAxz......................zsAiD', '.BsAx........................xAxi'),
            ('lhfhhh         hhhhl        hhhhhh', 'zBttsz.........wCaDw........zqtAiz', '.stAqD.........aaCn.........DiAtqD'),
            ('lhhfhhl       hhhhhh       lhhfhfh', 'BtAgxqD.......pgCCgb.......wixgAtw', '.xggAi........yewweC........BAggtB'),
            ('hhhhhh       lffhhhfl       hfhhhh', 'DtgCgs.......DguBBuaB.......iACgtu', '.yabAq........guCCka........BAbaCw'),
            (' hhhhf      lhfhhhhffl      hhhfh', '.pqysr......raguyykane......rsebe', '..eCbr.......ngmjwman.......uyybw'),
            ('   hhhllllhhhfhfffhhhhhhllllhhhh', '...pardbjczpppgmmmmabpezEhyduaew', '...wrF....ckypCmmmjCpbkd....FlD.'),
            ('    hhhhhhhhhhhhhhhhhhhhhhhhhh', '....hEFCylddvenlrBpCbvddkyaFFh', '....wjdnnyevdcEkppkEcdvpennvow'),
            ('    fhhhhhhhhhhhhhhhhhhhhhfhhf', '....wzBageyerkplEErplrpypnalzw', '....wryCabbupCnnlranCeuebCayrw'),
            ('     hhhhhhffhhhhhhhhfhhhhhhh', '.....ojBpekzyngeyargnCzuepBuo', '.....homhzzzygCpCCeygCmzzhmoh'),
            ('     hffhhffhhhhhhhhhhffhfhfh', '.....mfhhzzzrbbBplreylzzzhmfm', '......fhohzzzwjjwwuwwzzzhhhf.'),
            ('      hfffhfhhhhhhhhhhfhhhfh', '......dofhmzwwjjwwujwwzmjfof', '......cofhozlkheplefkpzhhdoE'),
            ('      hhfhfhhffhhhhffhhfhfhh', '......ccoodmplfaaaavkewfoodE', '......hFoddublfCnnCvkbBfdoEo'),
            ('       fhhfhhffhfhhfffhhhffh', '.......FhddBClfCggCvkalfdoFm', '.......FocdealfagnavkaydcoF.'),
            ('       hhhfhffffffhfffhfhhh', '.......doccbakdCnaadjaCdcoc', '.......hddcpakdCnaCdjayddfo'),
            ('       hhffhhhfhhhhhfhhfhfh', '.......zEfdbakEynaycjayvfcz', '........cfdyCjElaCeEjyCvoc.'),
            ('        hhhffffhhhhfhhffhh', '........hffyyjckCCkcjyCkoh', '........zdkyyjcfyyochbCkdm'),
            ('         hhhhhfffffhfhhhh', '.........dkyehcfebocopyld', '.........zBrpocfebodorrrm'),
            ('            hhhhhhhhhh', '............rujjpejjuB', '...............BBBB...'),
        ]},
    'spider': {"w": 34, "h": 18,
        "pal": [(13, 26, 34), (5, 15, 25), (101, 24, 45), (39, 77, 0), (12, 27, 37), (33, 59, 70), (47, 89, 2), (24, 33, 39), (45, 68, 78), (14, 29, 40), (6, 17, 27), (60, 86, 95), (24, 43, 52), (26, 48, 59), (28, 60, 0), (51, 76, 86), (56, 72, 78), (64, 38, 51), (8, 21, 32), (43, 18, 33), (15, 31, 11), (31, 49, 57), (18, 36, 47), (74, 102, 111), (47, 37, 30), (39, 58, 67), (19, 29, 16), (5, 16, 20), (46, 56, 65), (30, 66, 10), (71, 21, 39), (92, 15, 36)],
        "fb": [234, 233, 52, 22, 234, 237, 22, 234, 238, 234, 233, 239, 235, 236, 22, 238, 238, 236, 233, 52, 234, 236, 235, 241, 235, 237, 234, 233, 237, 22, 52, 52],
        "rows": [
            ('             llhfhhll', '.............qlvxlmpp', '...............xxxp..'),
            ('           lhhhhhhfhhhl', '...........wzlwplpfwlzm', '............fnjixlfjvf.'),
            ('          lhfhhhhhhhhhhl', '..........minpfillizimfm', '...........fnfnmiinnfnv.'),
            ('      ll  hhhhhhhhhhhhhh  ll', '......qm..wnnmwefnejwwnw..wq', '..........ajwsmjnmawsjja....'),
            ('   lhhhhhlhhfhhhhhhhffhhlhhhhhl', '...zzvjsesskbksswskabbkssesevzf', '....ms..k...bb.bjkb.bb...s..sw.'),
            ('  hh lfllhhl h  hhl h lhhllhl hh', '..vk.imwkess.b..bbk.b.skebwmi.bz', '..n...m...a.....vC.....e...w...m'),
            (' h  hh hhhhhfhhhffhhhhhhhhh hh  h', '.j..if.kesbeksrtEEtrsbjbses.vq..w', '.a..qw...es.kwecEEchwk.sj...jp..s'),
            ('h  lhh    hhfhhhhfhhhhhh    hhl  h', 's..wfb....sasjttcFttwsaa....bfm..k', '....w......ksbecFFcjbkk......w....'),
            ('   hhlllfhhhh hhhfhh hfhhfhllhhl', '...paqvawjwak.sEEtEs.kejewkmqaqa', '...w....wvnes.b.tt...semvwe...w.'),
            ('  hhhh  lhhhhfhl  lhhhhhhl  hhhh', '..zshp..qpwjekws..ahkejwpp..imkz', '..v.zm...mksakx....leaskw...wq.v'),
            ('  h fh  hh   hhhllhhh   fh  hh h', '..m.mj..im...mlhDDhqC...wq..en.m', '..j.ma..vw...wvg..gmm...wz..sv.w'),
            ('  hlh   hh   hhhhhhhh   ff   hlh', '..kal...im...AmDggDwA...wi...pha', '....p...zw...uDodDooo...wi...i..'),
            ('   hh   hfl  hhhhhhhh  lhf   hh', '...mv...snk..uggDoggu..bma...nm', '...iw...an....duogud....na...wi'),
            ('   hh    hh   h h  h   hhh   hh', '...ib....fj...D.o..d...afs...bi', '...q.....pw...u.D..u...wp.....p'),
            ('   hl    hh        h   hh    lh', '...ve....ij........u...jq....sn', '...h.....nw............wv.....h'),
            ('    hl    hl          lh     h', '....nk....nw..........jv.....n', '....e.....w............m.....h'),
            ('     h     h          f     f', '.....s.....m..........m.....s', '...........w..........m.....s'),
            ('      h     h        h     h', '......s.....s........k.....s', '............................'),
        ]},
    'ogre': {"w": 34, "h": 16,
        "pal": [(84, 32, 41), (143, 114, 129), (82, 31, 40), (49, 7, 30), (70, 21, 36), (179, 131, 133), (165, 91, 80), (82, 31, 41), (104, 53, 49), (108, 49, 55), (114, 53, 56), (123, 59, 59), (100, 41, 49), (143, 75, 69), (131, 69, 65), (60, 15, 33), (176, 101, 85), (146, 91, 69), (197, 170, 181), (69, 27, 34), (53, 13, 29), (168, 94, 84), (153, 82, 76), (88, 34, 44), (126, 71, 59), (33, 3, 19), (77, 26, 39), (165, 110, 77), (39, 11, 19), (84, 34, 40), (178, 102, 87), (174, 105, 95)],
        "fb": [52, 244, 52, 52, 52, 138, 131, 52, 88, 88, 88, 88, 52, 95, 95, 52, 131, 95, 181, 52, 52, 131, 95, 52, 95, 52, 52, 131, 52, 52, 131, 131],
        "rows": [
            ('                         lllhhhl', '.........................CDytyiD', '............................Bry.'),
            ('               lllllhhhhffhffhhfl', '...............ttyrBCtiyBBBrrlrrC', '....................BBrBBBrrrnyr.'),
            (' l   lllllhhhhhhhhhhhhhhfhhhhhhfh', '.C...CiiyBCtiryixmxiyrBrolynnojmC', '..........BBriaaaaaaaalooolkjmmm.'),
            ('hhhhfhfhhhfhhhhhffhfhhfhhhhhhhhh', 'tBryBBrBBrrnxhhhcaAhhAAjjxxhhaxe', 'iyylBrrrnorxAAeAcaehepAuuC..zuu.'),
            ('hhfhhhhhhhhhhhhfhhhhhhhh  ll', 'rBlnnlkooykpeupehaeAdppd..iC', 'DllylkjlkApdamxepAppxmhu....'),
            ('hhhhhhhhhhhhhhhhhhhhhhhhhhhl', 'CkmxheutwmdaoqqokxonqEneunoz', '.uaeC..CkoxxkoEvgwgqvklAkjj.'),
            ('     ffhhhhhhhhhhhhhhhhhhhhffl', '.....dddkjlApejggnqnxppmlkmddd', '.....ddpakexlmehheahejlxhlpdd.'),
            ('   lhhhhfhhhhhhhhhhhhhfhhhhfhhhl', '...pdpehpoAkqwmxAhejmggmAlpAepdp', '....phAApexnvfvoEEvovfglaeeAAAe.'),
            (' hhhhhhffffhhfhhhhhhhfhhffhfhhfhhl', '.pAaaAhehaaxksojwvljlsjxaahehAAaAz', '.ehAcaeehaaAlssojmklssoAaaAeAaAAe.'),
            (' hfhhhhhhfhhhhhhhhfhhhhhhfhhhhhhh', '.dAAeAuecaakkbfgnwwgfbmlaaaeueehe', '..AeAhpAhahojwwwonwnwvjocahApaAez'),
            ('   hhhhhffhhhhhhhhhhhhhhhfhhhhhh', '...pAeaaaahlwnqEEEEqqwwoAacaheeC', '....ppAAaaAjgqEqwnwvEqojeaaAApz.'),
            ('     hhhhfhfhhhhhfhhhhhhhfhhhh', '.....uphhhhamkkmxaamkmxhcacApz', '.....zeAAhcaAaahcahaaAhahahhd.'),
            ('      hhhhffhffhhhhhffhhhhfhh', '......duhAahcaacacaAaacachppd', '.......dApahaaaacaccaaaheepd.'),
            ('       hhhhhfhfhhfffhfhhhhh', '.......zducehAaaaaaaaAaeeud', '........zdudheahcaaaAAAuudz'),
            ('          hhhhhhhhhhhhhhh', '..........zCdpAAhaceeddzz', '..............dpeeAud....'),
            ('               hhhhh', '...............zuuuz', '.................z..'),
        ]},
    'skeleton': {"w": 34, "h": 15,
        "pal": [(50, 127, 151), (218, 85, 42), (97, 111, 103), (187, 77, 42), (198, 215, 191), (8, 24, 35), (101, 37, 20), (123, 49, 28), (37, 92, 111), (83, 95, 92), (68, 65, 67), (73, 78, 74), (43, 62, 69), (157, 180, 165), (37, 110, 125), (19, 59, 70), (73, 41, 31), (98, 57, 56), (74, 26, 17), (70, 56, 45), (41, 23, 18), (117, 142, 142), (159, 63, 33), (7, 170, 151), (139, 157, 145), (112, 129, 118), (21, 34, 40), (12, 20, 25), (17, 42, 53), (120, 95, 82), (33, 42, 44), (25, 48, 60)],
        "fb": [31, 166, 242, 130, 187, 233, 52, 88, 23, 59, 238, 239, 237, 145, 24, 23, 52, 59, 52, 237, 234, 102, 124, 36, 246, 244, 234, 233, 235, 95, 235, 236],
        "rows": [
            ('               lhhhhlll', '...............BEmmBlmB', '................ghuE...'),
            ('            lhhffffhhhhfhll', '............guggbbghsmkkAlE', '.............bwgbbgddhmkk..'),
            ('           lfhhhhhhhhhhhhhfh', '...........uwddqbbgdwduFkkrf', '............wwwgwdswhwq.Errk'),
            ('           hhfhhhhhhhhh  hhhhh', '...........shhsussugghg..squtu', '...........ushgwwdwhhgu...urrr'),
            ('          lhhhhhhhhhhhhflhfhhhl', '..........uhwhgqqqqqhhhuuBArrru', '.............jcyvvyzj..u.tAuuu.'),
            ('           lhhhhhhhhlhf hh  hfhl', '...........fcEAzynvEpcA.uE..srjk', '............k.xCmk.a.mA.....urr.'),
            ('            hhhhhhhhhhl      hhhhl', '............jpnpzyCxolB......krjmB', '............nyzyjAncve........jzv.'),
            ('            hhhhhlhfhh       lhhfh', '............lvkyAynlzc.......czvvz', '.............BAen.elB.........vyvB'),
            ('         llhfhhhhhhhhhl   hhhhhh', '.........qtAAkAznyvmkBp...AjyyvE', '...........mAcElzjjEcf....EE....'),
            ('     llhhhhhhhhhhhhhhfhf', '.....ElEttmFfkvjzzjzcBAi', '.......tu.iCC.ceeeey.BCi'),
            (' llhhhhllhfhh  hhhh  hhhhll', '.ElurtuBCAoiC..mccj..BiipCA', '...kE....moam....B...faoi..'),
            ('hhh   hhfhhhhhhhhhlflhhhhfhh', 'ttt...AFFiaiopfBfAffiooooCCf', 'uq.....CFA...mmAFF.f.A..AC..'),
            ('        hhhfhlfhlhlf lhhh', '........fCFCAfffFBFF.ACCF', '.........B.CF.fF.p.F..FfA'),
            ('            hhhhfhhhlhh', '............CCBpFffBCFB', '............BFCfFpFf.f.'),
            ('              hfhhh h', '..............CffpC.B', '...............fBA...'),
        ]},
    'skeleton_archer': {"w": 34, "h": 18,
        "pal": [(109, 106, 107), (57, 53, 53), (85, 133, 129), (143, 137, 128), (73, 21, 33), (82, 78, 89), (54, 52, 64), (126, 122, 122), (62, 17, 28), (64, 23, 35), (168, 158, 144), (47, 12, 22), (90, 88, 89), (90, 134, 175), (104, 99, 94), (25, 22, 38), (121, 117, 112), (87, 27, 41), (47, 22, 34), (137, 192, 232), (44, 47, 63), (79, 105, 110), (133, 144, 137), (76, 72, 77), (22, 21, 29), (33, 32, 42), (72, 72, 86), (61, 58, 69), (69, 63, 72), (24, 9, 19), (45, 42, 44), (45, 43, 54)],
        "fb": [242, 237, 66, 245, 52, 239, 237, 244, 52, 52, 247, 52, 240, 67, 241, 234, 243, 52, 234, 110, 236, 241, 245, 239, 233, 235, 239, 237, 238, 233, 236, 236],
        "rows": [
            ('                   hhl', '...................lri', '...................Di.'),
            ('                     hhl', '.....................iil', '......................j.'),
            ('              llll    hhh', '..............gCFp....DrD', '.......................ee'),
            ('            lhhhhhhhl  hhh', '............FBffACAzz..Drl', '.............fmABffA....ee'),
            ('       llhhfhhfhhhfhhl  hhl', '.......zcvbFCmAABACACy..lej', '.........cAFAfABACCBA....r.'),
            ('      lhhhhffhhhhhhfhfl  hh', '......yvcczCAAfBFppCABz..ee', '.......cxlFCAfCgfdACCB...li'),
            ('        hhffhhhhhffhhhhlhffl', '........lrsAfAzgqavyBfBzFjrl', '.........isAAuutFavC.gf.njr.'),
            ('  llhhhllllhh hhhhhh hhhhhfh', '..bbzyymmaCAB.CadbhE.pAnAirD', '....Cma....gF..yowoy..ntnDr.'),
            ('lhhhhhhhhhhhhhlhhhhhlhhhhhfh  l', 'BxhkkdamammfBDsobCxysuttverD..l', '.dmxBzy.zuoomE.sljjl.sCgBire...'),
            (' hhhhhll lfhhhhhhhhhhhfhhhhhhhhhh', '.zBfgyyp.ppxbEFCBgBuguppzslsElree', '..........pEEDzggFzFuppzoBmha....'),
            ('      hhhhhhhhhhffhhhf hffhhh', '......pyyppppzpyppzBzy.habdho', '......y.Dz..zfqqppgyDy.Dabmab'),
            ('        hf lfhhfhhlhhhl hhhhl', '........Dp.FFpqCyyFyECy.Bboqg', '.........p..FbBCoB.fFz..Dllp.'),
            ('           hlhhhfhhlhhll hfhhf', '...........bfkhbbgpaEofD.erpuy', '...........z.dmmbxo.x....rr.py'),
            ('           hhhhhfhhhhhhh fh', '...........bxfafhfCbmoyD.ej', '............kF.zhEBCzbE..el'),
            ('           hhh hhhhhhf  hh', '...........zay.yBdddox..Di', '............fz..yCCzEx..el'),
            ('            hlh  hhhfhhlh', '............myD..yxhxCyei', '..................Dzxu..D'),
            ('                     lhh', '.....................eel', '......................s.'),
            ('                   fhh', '...................Dil', '...................Dj.'),
        ]},
    'zombie': {"w": 31, "h": 20,
        "pal": [(185, 139, 102), (53, 52, 64), (181, 118, 78), (169, 119, 87), (46, 40, 53), (54, 43, 57), (144, 88, 63), (122, 73, 60), (67, 41, 54), (118, 114, 117), (71, 53, 62), (102, 54, 43), (72, 64, 75), (139, 114, 110), (94, 76, 85), (122, 83, 85), (37, 12, 15), (41, 29, 43), (95, 61, 63), (55, 64, 72), (192, 138, 89), (32, 18, 29), (115, 56, 48), (190, 150, 119), (149, 102, 76), (100, 92, 98), (65, 22, 34), (92, 41, 37), (134, 73, 53), (93, 37, 45), (62, 32, 41), (77, 36, 37)],
        "fb": [137, 237, 137, 137, 236, 236, 95, 95, 236, 243, 237, 88, 238, 243, 239, 95, 233, 235, 59, 237, 137, 234, 88, 137, 95, 59, 52, 52, 95, 52, 52, 52],
        "rows": [
            ('             lhhlll', '.............qFFFAq', '..............Cw...'),
            ('           lhfhhfhhhl', '...........FAFghlwlAA', '............lFhslCCB.'),
            ('          fhhhhhfhhhfh', '..........qBlbfmiCCwBq', '..........qlwfiiillBBA'),
            ('          hffhhhhfhhfhhll', '..........AllkEEBlwlFAqFA', '..........FllwlwllBFFFF..'),
            ('         hhhhhhhhhhfhhhh', '.........qAllFiimzoomEAq', '.........AFAmzjjjjzokfe.'),
            ('        hhhhhhhhhfhhhhh', '........AFEEkkzzzsnimev', '...........iDxniosxpoi.'),
            ('           hhhhhhhhfhh', '...........qspozjzkook', '............oozmmjjok.'),
            ('             hhhfhhhh', '.............voznnsEb', '..............ppnopkr'),
            ('    hllh     lhhhhhhhh', '....rrrv.....vonnnjsev', '....z..m......Ewppskfb'),
            ('   hhhhhhlhhhhhhfhhhhfhll', '...eiooobgqqvevAoskzmtbFq', '...kmzmmo.gFrtrioozjttC..'),
            ('  hhhhfhhhhfhhhhfhhfhhhhhhlll', '..qFmiDwAlgwrtbsjjotohCFFACBF', '..AAAFDDlAdwEroojotttCBlBl...'),
            ('  ffhhhhhfhhfhhfhhhhhhfhhhhfhhl', '..AArAFAgFxBFrojzktfzwllBgyyChB', '..AAslhyyFaDFFkjoEbgyFlBgaayyg.'),
            ('lhhhhhhhhhhffhhhhhhfhfhhhfffhhh', 'qAABnxuydDdBlBimmeCaCBBwcaydhgB', '.DFkgyxgswyBlFlEECaalBlhxaydgCF'),
            (' hfhhhhfhhhhhhhhhhfhhhhfhhhfhfh', '.vDEnccwghgAFECElaxaBBFgaydxxgE', '.qDkpwgwmweksmllyxxokkigdgxxcgq'),
            (' hhhhhhhhffhhhhhhhhffhhhhhhhhh', '.qFiFFDErDrfhselggmehhbkyyxdgB', '..DDEAFDEDrekrbfiebehlfbwgdyCq'),
            ('  hhfhhhfhfhhfhfhhfhhhhfhhhhh', '..FFDDwCDArrerbffbbffffbsddCq', '..rDDFFlDrrfrrefrtbbeebblggr.'),
            ('   fffhhhhffhhfhfhhfhfhhhhh', '...ADDFDAErrfrbbebbtrrbeEkr', '...ADDDwDArreebeeetterfrbb.'),
            ('       h  hffhhfhhhhhhhhh', '.......q..vrrbebebebbrerb', '...........rrfbbfefreerv.'),
            ('           fhhhhhhhh hh', '...........vvvbbbrfe.vv', '...........v..vtef.....'),
            ('               h', '...............e', '................'),
        ]},
    'ghoul': {"w": 34, "h": 19,
        "pal": [(119, 133, 112), (119, 133, 113), (212, 157, 18), (118, 131, 112), (120, 134, 114), (87, 93, 85), (34, 28, 40), (74, 63, 67), (153, 173, 146), (155, 176, 148), (52, 46, 52), (70, 56, 61), (96, 105, 93), (43, 41, 51), (41, 37, 43), (41, 33, 43), (139, 158, 133), (126, 141, 120), (45, 46, 44), (81, 87, 81), (74, 77, 74), (35, 33, 39), (29, 24, 34), (56, 54, 58), (25, 20, 32), (96, 94, 81), (102, 43, 23), (65, 63, 65), (38, 23, 32), (110, 122, 106), (20, 12, 26), (23, 22, 26)],
        "fb": [101, 101, 178, 244, 101, 240, 234, 238, 108, 144, 236, 237, 241, 235, 235, 235, 246, 101, 236, 240, 239, 235, 234, 237, 233, 59, 52, 238, 234, 243, 233, 233],
        "rows": [
            ('            llhhhhhhll', '............oexmddmxev', '..............ijjjji..'),
            ('          lhhffffffffhhl', '..........vsrjjjjjjjjrsv', '...........DijjjjjjjjiD.'),
            ('          hfffffffffffhh', '..........fejjjjjjjjjjbf', '..........mejjjjjjjjjjem'),
            ('      hl hhhhffffffffhhhf lh', '......sF.wmeijjjjjjjjiemw.Fs', '......B..gfdqjjjjjjjjqdfw..B'),
            ('      hhlhhhhhhhhhhhhhhhflhh', '......wumwhDaqijjjjiqaDhFmtF', '.......B..xzearqiiqqaefxF.B.'),
            ('       hhffhhfhffffhfhhhfhh', '.......nuukdqqrqqqqrqqdktuo', '.......wxukuDqqqqqqiqduntxw'),
            ('  l     hhhfhhhhhhhhhhhhhh     l', '..g.....BxnpCBDerredhgonxu.....g', '........wvopAcAxBBBAcApopw......'),
            (' lh llh  hhhhhhhhhhhhhhhh  hll hh', '.yn.kpy..otekmowqrgozkeun..ypk.gF', '..........sDrDDdbddDDrDs........y'),
            ('hhlhh lll   hhhhhfhhhh   lll hhlhh', 'Fpstt.sBn...wwumuumtgw...pBs.tfsgF', 'pw.mF.......gyffhufzyg........m.yp'),
            (' hhhlhhh h  hhhhhhhhhh  h hhhlhhh', '.pFuvrDx.E..wolzDDtlpg..E.xmrvuwv', '.oxf.mF.....Fxkhlllkxw.....Fm.fxn'),
            (' hhfhhlllhl  hhhhhfhh llhlllhhfhh', '.guuftFdmvp..BCCCCCCB.EpFmdwffuup', '.ymudx...u...xkpAACkx...u...xDumw'),
            (' hhhhhhhfllhhfhhhfhhhfhllfhhhhhhh', '.wtrmgffwoswEEBlllllyEwsnwtfgmetv', '..kdufDkw..kyEkhBlBxEEn..wnDfudk.'),
            ('  fhhhhhhhhhhfhhhhhhfhhfhhhhhhhf', '..kkdrBgouBnyyEtrrmyyyoxuopxrdkx', '..kuButummxonyy....EyppxmmuftBux'),
            ('  hfhhhhhhhlhhhhllfhhhhffhhhhhfh', '..stuBbDBgyygwyEEEEywgEygBDeButs', '..vtfuokyvE.wgww..Eggwyygwkouftv'),
            ('  hhhhfhhhhhhhhhhfhhhhhhhhhhhhhh', '..vtfftFygyEnpgkEEynppwEgywufftv', '..Futmt..ygw.yoxyEpkgEEpw..tmtuF'),
            ('  hfhhh   hhhhhhhhhhhfhh   hhhfh', '..Fttmh...wpnkopkxkpnkpw...hmttw', '..ktftk....wolxwpkooBkw....kuftx'),
            (' lhhhhh     hfhhhhhhfh     hhhhhl', '.xfmthw.....wwnkkkkkgw.....wBtmzx', '..ibhn.......wgggoggg.......nBdi.'),
            (' hhhh         hfhhfh         hhhh', '.xDto.........gggggg.........ofDk', '.ytug..........gwwg..........guty'),
            ('  hhh           hh           hhh', '..voy...........gw...........yov', '................................'),
        ]},
    'corvane': {"w": 31, "h": 20,
        "pal": [(255, 255, 255), (98, 99, 99), (225, 226, 226), (53, 53, 53), (200, 201, 200), (58, 58, 58), (103, 103, 103), (165, 165, 165), (160, 160, 160), (202, 202, 202), (111, 111, 111), (177, 177, 177), (47, 47, 47), (72, 73, 73), (231, 231, 231), (218, 218, 218), (253, 253, 253), (91, 92, 91), (209, 210, 209), (66, 66, 66), (171, 171, 171), (155, 155, 155), (195, 195, 195), (39, 39, 39), (125, 125, 125), (136, 136, 136), (185, 185, 185), (29, 29, 29), (244, 244, 244), (81, 81, 81), (143, 143, 143), (148, 148, 148)],
        "fb": [231, 241, 254, 237, 251, 237, 242, 248, 247, 251, 242, 249, 236, 238, 254, 253, 231, 59, 252, 238, 248, 247, 251, 235, 244, 102, 250, 234, 255, 239, 246, 246],
        "rows": [
            ('               h', '...............n', '...............l'),
            ('          hl  lhl  lh', '..........gE..baf..yy', '..........d....C....m'),
            ('          hh hhfh  hh', '..........Dv.trar..FD', '..........wD.nuaw..De'),
            ('         hhhhlhhhlhhhl', '.........xiAnEqohdtluF', '.........zmad.ags.mq..'),
            ('         hhhhfhhhfhhhh', '.........hhwhaatsauluh', '.........nqncalxhaptad'),
            ('         hhlhfh hfhlhh', '.........Fsmpad.Casxpy', '.........hl.yaD.zaz.hv'),
            ('        lhhh hh hh hhhl', '........Dlnr.yD.mk.nbvd', '.........aD...B.x...fa.'),
            ('        hfhllll llllhfh', '........zaCBvuD.Dhixpab', '........Aap.........sah'),
            ('       hfhhhhfhhffhhhhfh', '.......Baaripcegjcsukaax', '.......FaonsocjjjcpjmoaF'),
            ('      hhhhhhhhhhhhhhhhfhl', '......BqalkmrhwjwhbmgwaCh', '......EaqdAktxtztfnkhDaa.'),
            ('     hhhh hhhhhfhhhhh hhfh', '.....Bqav.DwlepjpeuAD.iaax', '.....zaqB.fxesjjjpsdt..Cai'),
            ('    lfhh  hhffffffhh   hhfh', '....uaqn..xyujjjjjAk...dqam', '.....az....tujjjjjlt....Eai'),
            ('    hhh    lhfffffhl    hhh', '....paB....mljjjjjlm....Bqs', '....lA......FjjjjjF......hA'),
            (' lllhhl    hhfffffhh    lhhlll', '.mindir....fzjjjjjEd....bvtnvt', '....uc.....mFjjjjjFf.....pu...'),
            ('hhffhfhhl  hhhhfhhfh  lhffhhfhh', 'Bjaaqaatd..xEjjjeezx..nbaaaaaqt', 'AaaaAaqp....zeejAiz....Caalqaal'),
            ('hhhfhhfhhh hhhhhfhhh hhhfhffhhh', 'nqaaAcaeex.nyulhiuEn.BwwaeAaaCt', '.xpauyaAze.Bbhiiihkm.lysayAaor.'),
            ('   hhhfhhhhlhhfffhhlhhhhfhhh', '...wazavnzbxbuiiihbBDydvaFau', '....ipac.mp.mgiiikn.on.sasl.'),
            ('     hhfhlhhhhhhhhhhhlhfhh', '.....haagfocmDEiEnmpCmbaal', '......zaq.baqExymyqaz.Cal.'),
            ('       hhhhhhhhlhhhhhhhh', '.......noCyyaaFsyaaFkqar', '........BwaslCa.aChwasm.'),
            ('          hhhhhhhhhhh', '..........nwCwlCAwqcb', '............BzpppFr..'),
        ]},
    'town': {"w": 60, "h": 17,
        "pal": [(168, 27, 28), (203, 127, 3), (2, 1, 26), (52, 20, 45), (100, 43, 4), (222, 63, 30), (35, 16, 45), (137, 69, 5), (73, 16, 36), (80, 22, 43), (136, 35, 20), (10, 4, 27), (203, 39, 26), (176, 107, 12), (78, 25, 35), (43, 17, 27), (48, 26, 25), (101, 18, 36), (126, 20, 32), (12, 7, 32), (34, 15, 41), (29, 14, 21), (24, 10, 35), (28, 9, 9), (69, 19, 42), (74, 30, 10), (50, 31, 50), (82, 34, 49), (45, 15, 7), (101, 26, 37), (41, 15, 43), (52, 16, 41)],
        "fb": [124, 172, 16, 52, 52, 160, 17, 94, 52, 52, 88, 17, 160, 130, 52, 52, 234, 52, 88, 17, 17, 233, 17, 233, 52, 52, 235, 52, 52, 52, 17, 52],
        "rows": [
            (' hffffhffffffhfhhfhffffffffffffffffhhffffhfhhhfhhfhfhhfffffh', '.uuuuuugggguuuAAAAgggggggggggggggggggdddddjBBBjjjjjjyddddddE', '.wuuuuggggguugABBAuggggggggggggggggEdddddjjrrjjrrjrjjjdddddd'),
            (' hfhhhffhhffhhhhfffffffhffhhhfffhhhfhhhhfffhhhhhhhhhhhhhhhfh', '.uuuggggggggABBdggggggggggggggggggEdddddjjrrrrssrErrjjyyyyjy', '.wuguuggEEggBeAggggggggEggEdEgggEEFdEtFjjjrDssrriwFDrrjjjjjd'),
            (' hhh hhhhhhhhfhhhhhhhhfhhffhhhhhhfhhfffhfhfhhhhhhfhhhhhhhhff', '.lEE.lwuEEEuAAgEEdddEEdydEEgEddFdyyuctujrrDsDskkrlisDDDDrjdd', '..Fp..l..lt.qAFdyyyyyyddEEEFyyyyyyElctuFrDDrkaaaklrasssryddd'),
            (' hh   hfl   fh hhhhhhhfhhfhhhhhhhhffhffhhhhhffhhhfhhhhfhhhhh', '.xy...ltt...qq.EyyyyFuFdFyyyyyyyuwccltwFyskammmaslFkEErrrrrj', '..x....t....qz.....tctFiiyjjjjjFclccttwEFjammmfkcltwturaksit'),
            ('        fhl fh    l hhhhfhhhhhhffhhhhfhhhfhhhfhhhfhffhfhhhfh', '........tlt.qB....v.ltwjrrDpwDoccclltwtuEFraffmucltttwwiaoll', '........tt..qq.......llwrspctulcclttwwuwFFyimfplllltttwuwllc'),
            ('    hh   hfffh   hhh llllllllffhhfhh hhhhhffhhfhfhhfhhfhfhhf', '....xz...ttttv...vqx.xCCCCCCxttctwtw.tuuuFFFiFllclllttttclcc', '....Ce....tttt...Cez.........ttwwwwl..wEEEFFtllccccllwtccclc'),
            ('     h     fh   lhhhlfhhhhhhhhfhhhhh  fhhhhhfhfffffhhhhfhhfh', '.....x.....xv...xzzzxCzqlCvCxwwwuAww..wuFAulclcccccctgwcccwc', '...........xx....eee.CevennbeuwgAgul..wEwwcwccccccclAAtc.uw.'),
            ('   l  ll hhhh  lhhhflhffhhhhhhffffh    h hhhhhhhfhhhhffh fh', '...C..xx.xzCq..CCzCCxCewhbbbhpuuAAE....t.wwwlccttcctBtcc.Al', '.........CCz.....qzC.xewennnewuuAAu......vvt.wtutltAAtc..Aq'),
            ('   h  hh fh  lhhhhhh  hfhhhhhhhffhh     h   lfhhhhh ff   hll', '...C..xx.Cz..CqzzCxx..ClenhnktwtAwl.....C...xxtutwt.vc...Axw', '.........C....zekez...zlvzeevlttAl......x....x....l.vc...q..'),
            ('         h   hfhhfff  h hhhhh hfh     ll  ll         hhf f', '.........x...zzqebhC..z.ltttl.wvp.....xv..Cx.........wtt.v', '.............ezzhbhC..C..cccc.pv......................wt.v'),
            ('   l         hfhhhhhllhllllf  h   l h hh  l    h   ll', '...v.........eCzzheCxCCCCxxx..v...t.x.zq..v....C...Cz', '.............zCCCeqx..x....x..........x........z.....'),
            ('        ll   hhhhhh f   ff l      hhl h    hh             hh', '........vp...CCCCqq.x...xx.v......pvq.v....vv.............tt', '.............vzekhe.x...xx........q...w....CC...............'),
            ('         llfhh hhhhl        l    hh h     hhh            hl', '.........vqvqq.pvxxv........x....xC.q.....xqz............CC', '...........v....pvp.........................C............e.'),
            ('          hh     hllhl        hl         llhh', '..........vv.....pvvxx........vp.........vppv', '....................v........................'),
            ('           hhhhf   hhffll         hhhhhhh', '...........xxxxx...vvvvCv.........vvvvpqp', '...............x....pvv............qqpv.x'),
            ('                     hhhffhhlllhhfhhhhh', '.....................vpppqvvqqqvpqqvxxx', '........................pqpq...pqqv....'),
            ('                          hhhhhhhh', '..........................vpqqqqpv', '...........................vvppvv.'),
        ]},
    'cellar': {"w": 60, "h": 17,
        "pal": [(168, 104, 60), (251, 209, 141), (64, 44, 40), (83, 60, 47), (71, 49, 40), (44, 29, 32), (78, 56, 44), (62, 42, 38), (54, 70, 79), (9, 7, 25), (45, 61, 70), (35, 23, 31), (17, 20, 36), (24, 22, 36), (53, 37, 37), (36, 27, 35), (32, 42, 56), (43, 56, 66), (37, 50, 61), (32, 36, 48), (46, 34, 38), (33, 22, 27), (23, 27, 40), (12, 13, 28), (117, 65, 36), (51, 62, 71), (25, 33, 49), (18, 14, 29), (22, 19, 29), (71, 58, 52), (64, 48, 44), (59, 71, 76)],
        "fb": [130, 222, 236, 238, 237, 235, 237, 236, 238, 232, 237, 234, 233, 234, 235, 234, 235, 237, 236, 235, 235, 234, 234, 233, 94, 237, 235, 233, 233, 237, 236, 238],
        "rows": [
            ('            llhhhh  l l         ll        hhhll', '............wBBACw..j.j.........xx........wqmAw', '............................................x..'),
            ('        llhh         fh        llh       lf    hhll', '........wnmm.........xx........jjj.......jj....Amqw', '.....................xB...................j.....w..'),
            ('      lhhlflllhhhhhhhllhhhhhfffhhhhhhhhhhllhlllflhhhl', '......AqCjjjxmjBBBnmxwnjBmmmnnnxjxmnmBmBjmBjjjjjjCkwm', '..........j...mnnnwww..mnnwwnnnnnwnwwwnnn..x...j...r.'),
            ('    lh     ll lhhl       l  ll   l hhh           l hfl', '....nw.....jj.jBBj.......j..jj...x.xBj...........j.qsq', '.....s.........ww..................Bmx..............s.'),
            ('   lh         hhhh                 hhh              hh', '...xq.........xpwj.................nnn..............ss', '....r.........jBB..................xBx...............q'),
            ('   hh         hfh                  hfh              hhl', '...ws.........xnm..................xwm..............CkC', '...At..........nC...................wx...............s.'),
            ('   h     lhllllhh      ll           fh         lll   hh', '...m.....vvzFFwCB......CC...........wj.........CwB...sq', '...q......u....wm...................wx...............tA'),
            ('   h    fhhfhhhhhl  lhhfhhh         fh        lhhhh  hh', '...w....pfrzkCulBC..jmAtwmB.........wB........vCCCx..qA', '...r....pAtzpoEef....nptpwC.........wx.........llvC..nm'),
            ('   h   hhhhhhhhfhhl hhhhhhhl        hf        hhhhh  fh', '...w...xBxAtehcccfC.ntsssAnB........wm........uoopl..qs', '...s...jj.wfdogceE...fvfffC.........pm........vplvC..qq'),
            ('   h   h  hfhhhhhff hhhffhfh        hf       hhhhhhl hh', '...t...j..jpgoeecgn.Chucoull........wn.......ClfvBvC.wA', '...A.......peuggogn.loocoflC........pn.......vuchff..qq'),
            ('   hh      hhfhhhhf hhhhfhhf    fh hhhl ff    hhhhhh hh', '...mC......pouedeeC.BfucocpC....vB.xwwt.BC....fhhuuB.qt', '...j.......nfuCoccC.jlfhoflC....v..qss..BC....BlplC..wm'),
            ('           hhh lhhh hhhhhhh     hhhhhhh hh    ffhhh  hh', '...........xlp.vvfC.jmAqqmm.....vjjAqtA.Bn....vfflC..qx', '............BB..CC...jBnnxj.....B..wmAw.xC....vfypB..w.'),
            ('    hh     hlhlhhhhfhhhhhhhlllllhllhlhhllhllllhhhh fhhh', '....wq.....CfxnBwullCxwttwBtrsqqjsAxqmmqtjAqAwCgbh.vDsC', '.....n.....l.C.ploBllpmwwnm.....q..q.tq..A....noal.vtm.'),
            ('     h     hhh  hhlhhhhhhhhhhhhfhhffhhhfhhhhhhffhhhhh', '.....m.....vov..posvptskriiFikkkkzzkrsskziiiiFzEpwAuq', '.....j.....Bp...Cq.krrzikrkkzzzkskzkkkkkkkksrkzECsrzt'),
            ('        hhhhhhhhhfhhhhhfhhhhhhfhhhffhhhhhhfllhfhhhhh', '........mAsrswtrkkzzkkkksqAttqqqqkkkrkizirqzdsstpnho', '.........xttnBnkskkkzizkkkkssrqiFikkkqqqqtq..dsnm.v.'),
            ('           hhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhh', '...........xAAAAAqqqsqBmkskkkkrsssqsqrssqqrsstwwx', '...............xmmnBwm..AAtqqsswmwwwxA.mmx.......'),
            ('', '', ''),
        ]},
    'forest': {"w": 60, "h": 17,
        "pal": [(88, 161, 173), (0, 36, 50), (6, 65, 81), (40, 137, 154), (12, 69, 85), (31, 133, 151), (0, 27, 40), (13, 90, 106), (17, 98, 115), (58, 140, 154), (4, 52, 68), (0, 31, 44), (39, 113, 127), (1, 30, 42), (13, 80, 96), (22, 113, 130), (22, 61, 77), (140, 195, 203), (10, 67, 83), (6, 60, 75), (1, 41, 55), (28, 119, 136), (4, 33, 45), (11, 30, 43), (5, 44, 57), (2, 49, 64), (8, 74, 90), (2, 15, 26), (2, 22, 33), (19, 46, 61), (9, 43, 57), (8, 52, 67)],
        "fb": [73, 17, 23, 30, 23, 30, 234, 23, 23, 66, 23, 234, 30, 234, 23, 24, 23, 116, 23, 23, 17, 30, 234, 234, 17, 17, 23, 233, 233, 235, 17, 23],
        "rows": [
            ('                          l hhhhhl', '..........................C.BgEzCg', '...............................Bg.'),
            ('                     ll    hhhllllhh  l f', '.....................CB....gbCglllgg..B.B', '............................wb....C.....B'),
            ('     l     l  l ll lhhhhlhlhhhhhhhll h hhh  lll  l   h  l', '.....C.....B..B.CB.ggyCBCBCluDbzAgCB.B.BCB..BCB..B...C..g', '....................lb.C.n.FvffiFE......nl...............'),
            ('lh   hlhl  flhhhhh hhhfhhhhhhhhhhhhlllh hh fhfhh h  llhhh hh', 'BC...lwgE..CCCyCwg.wlCCynlllFobullCgBub.Cb.CCubb.B..BBBBl.BC', '.....u.....C.ltFCB.Cb.CtCnzzoiztFtg...t....Clutg.g....gCb.C.'),
            ('hhhh hhh   fhhhhl  hhlhhhhhhhhhhhhhhhhhhhh  hhhh h   lhhh hh', 'yCCg.tgg...xzyzgb..CCCzhwbiFbzyhzyzyoutgyB..CCwy.t...BtkD.gb', 'Fbbb.Elw...xtzB....wB.bzBltecubbkppzegyCgE..yBCD.D....scC.yc'),
            ('hhhh ffh   hhhhhh hhhhhhhhhhhhhhhhhhhhhhhhf hhhhhhh  hhhh hh', 'tzzw.zzs...uzBbgb.BnCCuCClyipppjjitutgtCCnB.FBttBsB..gqtB.wt', 'uC...zzt...FcCybu.CbbgzBlwuuzidimoFbzb.nbCB.b.uF.cg..CtkC..B'),
            ('llh  hfh  hhhhhhh hhhhhhhhhhhhhhhhfhhlllhfh fhfhfhhh  fhh hh', 'zgz..Fyz..CEcCbzB.gzFCBglzysuyidjounwbnnyzx.BCtFCtgB..Acw.ng', '..c..tyu..bqewCuC.xblgbbyutAtzyofiugg...zzb.B.tgCcFC..Asg.zu'),
            ('hfhh hfh  hhhhhlh hhfhhhhhhfhhhhhhffhhhfhhh hlh hhhh  hhh hf', 'yuqC.zyg..gFAbBlw.BugbubuyethAiitcFnbyzbFEx.wCb.CtDB..FkC.Fb', 'buk..EyB....B...u.xzgFAwlzztovdfhtFnyzybEcE......B....uF..zb'),
            ('ffh  hh   lhfhhhf hhlhhffhhhhhffhhfhhffhhfh hhhfhhh   hhh hf', 'lzt..yb...CDtnuzF.gzusctbttctopfhczbFzuwytD.llgCuFx...wkB.yl', 'lzz..Cu....Ft.ztF.Cg.tttbkchivpfpAzuzzuzgtu.gbCCyuD...Bu..bl'),
            ('hhhll    lhhhhhhh  lhhhhhfhfhhhhhhfhhhhhhhh hffhhhhl     lff', 'uzbBC....BxyuBkkb..yFAoebttAvffvettzbFkenzE.CFBCFwDx.....lnn', 'wEg.......EuCCtzn...cotkgtAAAvvihotygzycAC...FBbtlE.......nn'),
            ('fh fh    hhhlhffh hhhfhhhhhhhhhhhhhhhhhhhhh  fhhhhhh    hfhf', 'lg.Bg....BFuBltzg.xtcAAubssipfposcczgwkAAsw..tBgtlbE....Blln', 'lC.Bn....CDC.btzC.betAsluooohiAAAoeclntshAq..tgCEnlD....Clgn'),
            ('hh hh   hhfhfhhh  hhhhhhhhhhhfhhhhhhhhhhhhhf hhhhffhh   hfff', 'lC.Cn...BxFBCuzz..tskczntovfhiphvfheugteieAx.unBgnnFg...Cngn', 'nB.gg....bF.Cyyb..zkFklueharaihjrristlzssctx..g.BnnAB...Bngn'),
            ('h  hh    fh fhh  fhhhhhhhhhhhfhhhhhhfhhhhhhfl  h hhfh    hhh', 'C..gC....xF.lyy..CqkkunkcoijdvvfjpiAtwnkFkzEB..B.glFC....ngB', '...B.....xq.ln...CFybglctsoipvpphoAttbgluuuE......xFB....CB.'),
            ('         fhhhh  hhhhhffhhhhhhfffhhfhhhffhhfhf     fhf', '.........CExCB..BCDggglkktcAoohostkktbggggwxB.....DCB', '.........CgE.....BuCCglzuyktAohockkyzlggCBwBB.....DBB'),
            ('         hhhh   fhfhhhfhhhhhhhhhhhhhhhfhhhhlf   lhhh', '.........CBFB...BBEBCCggbuzAostkzybbggCgBBbBB...CEbC', '...........gD...BCE..BgClbbucoeFbCCCCCCB..D.B....DB.'),
            ('            hhllhhhhllhhhhhhhfhhhfhhhh llhhhhllhh', '............CCCBBBbBgCBCgCEcetzwCCCCBB.CgCbBCBCCC', '.............B....Cx.....BBbyttzbCB......xB.B..B.'),
            ('                   hhhhhf hfhhhhhh lhhhhhh', '...................BCgCCB.BBCEtFEC.BCCgCCB', '........................B..BnuFgBB..B.....'),
        ]},
    'mine': {"w": 60, "h": 17,
        "pal": [(86, 116, 95), (44, 67, 73), (23, 40, 59), (63, 44, 47), (146, 0, 26), (77, 106, 92), (49, 34, 47), (183, 0, 24), (64, 90, 84), (5, 13, 40), (11, 22, 46), (13, 4, 32), (5, 5, 32), (49, 18, 38), (89, 77, 66), (60, 15, 36), (50, 49, 56), (31, 31, 47), (26, 5, 32), (30, 19, 39), (10, 15, 41), (37, 59, 70), (73, 92, 82), (50, 74, 77), (15, 29, 52), (0, 1, 27), (74, 29, 42), (62, 69, 68), (242, 0, 21), (30, 48, 62), (105, 0, 27), (98, 10, 32)],
        "fb": [65, 237, 235, 236, 88, 241, 235, 124, 240, 17, 17, 17, 17, 52, 239, 52, 236, 234, 17, 234, 17, 237, 240, 238, 17, 16, 52, 238, 196, 236, 52, 52],
        "rows": [
            ('hhhhhhhhfhfhhhhhhhhhhfhfhhfffhhhhhhhfhhhfhhfhhhhhffhhhhhfhff', 'bkDiviifwjcxyxfccyDkujujukkkzkkkkkukzmuukzmmujkkkkkkbiibkuky', 'xDcxyxfiwkcbbvivmjujmjkjzjkkzzuujmzzzzzjkkkmjkjyykkywxvDkyky'),
            ('hhfhfhhhfhhhhhhhhhhffhhhfhhhhfhhhhfffffhhffhhhhfffffhhhhhhhh', 'xykckbifymybvviikjjzzkkmzmujzzzmmzzzzzzmkkkujyukyujywvDyDDjk', 'iikukcbwyjmyybxqrmmzzmjzzzzz.z....zzzzzzjkktrtjkyujyxwxcvczm'),
            ('hfhhhhfhhhhfhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhfhhhhhhhhhhhh', 'virmbxixmmujkvqddoooodddddddBdBBBBBdddddddddddykkuuifxvDckyk', 'ciDuviiijzjjybDrrrrtrrrrttngggtnnnnntnrrntntttkkujyxxbccDvuu'),
            ('hhhhhhhhhhfhhhhhhfhhfhfffffffhhhhhhfffhhhhhfhhfhhhhffhhhhhhh', 'cDDucxxiDumzcbvtuzzmgtzzzzzzzzzzzzzzzzmrtzzzumzuukyxvvbDxvyv', 'yvvjyDwDwbmmkDkdtzsdgzzzzzzzzmjmmjjzzzzsgtmzguzmkjbxvbxbDcvx'),
            ('hhhhhhhhffhhhfhfhhhhhhhfhhhhhhhhhhhhhhhhhhhhffffhfhhfhhhhhhf', 'jcrkDxbDfikjkkudrldgslllsssssssssssssssstdrzdtzzukDxcxbDycxb', 'zjzcibvwfickjkzdgggzzzmlzzzzzmmzmzzzzlzzzlgtdtzzjkyvcvDyjxDb'),
            ('hhhhhhhhhhhffhfffhhfffhhhhhhhhhhfhhhfhhffhhhffhhfhhhhhhfffhh', 'myDvvvffafckkuzdggszllslmllllllllllllllllmtgdtzzjuvbrkyDcbbD', 'zkcDcbxifvkkkzzdgzlzllzzlmzzzmmzlzmzlzzlllmldtmkjvawxbxDcbDy'),
            ('hhhhfhhhhhhffhhfhffhfffhhffhffffhfhhfhfhffhhffffhfhhhhhhhhhh', 'jyyDvybxxyjykmjdrzsmlzlllmlllllslllllllmllmzdtjkuxxxDbcybDcy', 'cmucvDjkyzuykkkdtzsllzlmzmlmlllsslmmlzlzlllsdtjkkxvcycjkDcyu'),
            ('hhhhhhfhhfhhhhhffffffhffhhfhhhhhfhhhffhhfffffhffhhhhhhfhhhhh', 'bkjkcvykuzkukkmdnzszllmzzllmlsssnslmmmmllllsduzukvymkxcjyvix', 'vbujkyymzzummmzdnzszlzmzmmlsnnpnnnnsmmlzlllsdtzuumDfficyafxu'),
            ('fhhhhhhfhhhhhfffffffffhfhhhfhhhhhhfhffhhhfhffhfhhhhhhhhhhfhh', 'bbDDvyjcDcmjmzzggzszlzmzmzznpAFFFFpssmmzsllsduzjyaaiwckwaxDc', 'bDbbxiDcbfxuuzzggzszlzlzlllnFeeeeEppsmlmllmsdtzziwffiubiixby'),
            ('hfhfhhhhhhfhfhfffffhhfhhfhhhhhhhhhhhfhfhfffffhhfhhhhfhhhhhhh', 'cDvDbwaccxbukmzgnzszlzlzllnFeehhheEpslsmlllsdtzxfxwbkuiafibb', 'DDcDkDxbkybkkuzgnzsmszsmlspEhCCCCheFssszlllsdubxvDbDkwffivxv'),
            ('hffhhhhhhhhhhhffhhfhhfhhfffhfffffhhfhffffffhhhhhhhhhhffhhhhh', 'xxxvjucDuycyujzgtjsmszulsspEhCCCChslsslmlllsrjDwwxbvvaiwxcvk', 'bxxxcjucDkkumuzgnusjlzljsspehCCCCCmllslmllllbDfivDyjxaixDuyc'),
            ('hhhhhhhhhhhhhfhfhhfhfhhhhhfhhhhhhhhhhhhhhfhhfhhhfhhhhhhhfhfh', 'vxxbwvukvumkmzzgnululmmjtppFeCpsChzzlllzljjDiwwifwcDxxxvvcDb', 'yvbiixcukjyyzzjgtmljluuumsppppslFpllzzmlkjDfifaffikbfiDivuDv'),
            ('hhhhhfhhhhhhhhhhhfhfhfhhhhfhhhhhhhhhhhhhhhhhhhhhhhhhhhhfhhhh', 'kcbxibwyifwbujurnkluukkujujspsssppsllmtykrfwxfiiDuzDwvxDcjyc', 'cjcDvbDifaaaDkkttkuukkjjujjjljjluummmucvDxvrawbccyucDcbDymky'),
            ('hhhhhhhhhhhhfhhhhfhhhhffhhhhhfhhhhhhhhhhhhhhhfhhhhhhhhhhhhhh', 'cjjyyDkcvvxixcjutDvcjujukuummlsmjuummcffxybifxxxcyjjybDcjmyk', 'kmcrkkyvDDbbxxkmkDxxDkjuutllslujukyujbvvyvxcbxbcykmcDyjjzzzm'),
            ('hhhhhhhfhfhhhhfhhhhhhfhhfhhhhhhhhhhfhhhhfhhhhhhhhhfhhhhhhhhf', 'vbDDkuvvvvkcbccvruukyvDrtutttputrccccbDjDbbDbDyykmbxbDkzzDky', 'cDvccmcvDvykkkcbDcxvcvgttggggtgqxvxckvvyDcvccjcDDxbDDccmyvuy'),
            ('hhhhhhhhhhfffhhhffhhhhhhfffhfhfhfhhhhfhhhfhhhhhhfhhhhhhfhhhh', 'jkyyjzyDvvDkkccvvibxvgntggggntgDixixbvDyykmmmkvDvvbckckzcDym', 'uzjjzuuukDDkkykDviiqrttdgggnnrgvibxvDvbuzkcDyyccvDDyjkmzkcjz'),
            ('hhhhhhhhhfhhhhhhhhhhfhhhfhffhhhhhhhfhfhhhhhhhhhhhhhhhhhfhhff', 'uzzjzujuyyykmyvxivqAttrrgrggurgvwifbxcbvvbcyymmyykucckzzmjzz', 'yccDDkkmkycDbifiqqAutgqgggggtgDbixibbcDckjjjjzzkmzcDymkzzzzz'),
        ]},
    'galleries': {"w": 60, "h": 17,
        "pal": [(12, 32, 49), (23, 17, 30), (142, 67, 33), (37, 109, 116), (228, 152, 52), (196, 106, 35), (24, 65, 80), (15, 27, 48), (173, 80, 28), (38, 26, 35), (39, 44, 59), (26, 21, 34), (12, 21, 42), (61, 37, 40), (22, 38, 60), (39, 31, 41), (25, 50, 71), (118, 58, 35), (58, 49, 57), (11, 17, 36), (56, 32, 35), (23, 16, 26), (14, 37, 56), (21, 30, 49), (28, 79, 93), (87, 44, 36), (3, 9, 28), (36, 75, 89), (81, 49, 47), (37, 23, 31), (11, 11, 27), (8, 14, 34)],
        "fb": [234, 233, 94, 23, 172, 166, 23, 234, 130, 234, 236, 234, 233, 236, 17, 235, 17, 88, 236, 233, 235, 233, 17, 234, 23, 52, 232, 23, 52, 234, 233, 233],
        "rows": [
            ('                            lllllll', '............................momtmAa', '...................................'),
            ('      llll   fff   lhhlll lhhhhhhhhlhhh ll hfhll    ll', '......AAAE...FFt...wotFEA.hmhmhxxwgtgaF.AE.EmFAF....AA', '.............FFt....mA.....tAxxowBd.dgh....FmE........'),
            ('     hfhhh lfhhhh  hhfflhffhhhhhhffhhhhhhflhhflh l hfhh l', '.....EAFFt.AAhtFF..pDlEEtEmFqhomoydgdgwttFEttEEE.w.tmFA.A', '.....AAmtA..AAFxx..nulE..EmAoomogyddyygahF.EmE.t...hmmt..'),
            ('  l  fhhh lhhfffh fhhhhhhhhhhfhhhfhffffhhhhhhl h hhhfhhhlf', '..x..mmFm.AAAFhho.urznlvEAFtmhFwgyyydddoommAmE.v.ohmmtAAFE', '.....mxhx..FFFhhx.ucrjbE..AmthtmyypydddBaxhhF..b.lwwmmt..E'),
            ('  hhhhhhh ffhhhhhlfhhfhh  hhhhhhfhfhfhhhfhhhhhhhhhhhhhh hh', '..DvjjhoE.FtFFhFtlDnnujv..FqmotoygagddygxmxhFlDDExohFFE.mA', '..jznClt..FtmxxAv.Dljubj..tmAqwqywawdgqwxF..vDzzDllmAE..xt'),
            (' lhhfhhhhhhhhhhfhfhfhffhhhhhhhfhhhhfhhfhhhhlhhhhhhhhfl l hh', '.DnzrCjDDvhxohFEvDpDDnjDlthmAsgqBaoqyxootEEblzccrDDFtb.E.mh', '..rrrjDullbvlbbE.DjDpnjjjlmwFoggwwgqBoobjlD.xCiecjEAt....E.'),
            ('lhhhhhfhfhlhhhhhhhfllfhfhhhhhffhhhffhfhhhhhhfhhhhhlfhhhhhhf', 'vrircrnnvEuDnulAADEuAEEDljxqhgggaoqqwxmjnzpDmsrrCxDDDjppbEA', '.cfefcnuvb.zcnuEDjE..EvDblpxxggBoaqqlxlurczumokksb.Dunssp.A'),
            ('fhfhhhfhhhhhhhhhhhhhhl hffhhhhhhhffhfhhfhhhhhhhfhhhhhfhhfhf', 'DciefcnCEDnzrzuEDlbjEE.ElljpxggBywaaxhEpzrzphxootEjnzrskjEE', 'DriccrnnbnuCznpbjpjpl...llhlpkqqgwaxxmbpnCulmmxoEvurcrCujmE'),
            (' hhhhfhhhhhhhhhffhfh ll hhhfhhhhhhffhhhhhhhhhhhfhhhhhfhhhhf', '.nrcruunvuunCuuDjpEE.ED.EFxhokssokppkpppjulAmwhEEvunrzCsgqm', '.ljnuuluEjjupjnDjjEb....FhhhqBgoxoppxttbFEhxxoFEbbDjzzkqqom'),
            ('hffhhhffhfhhhfhfhfhhhhhlhfhhhhfhffhhhfhffhhhhhh hhhhfhhhhhh', 'FsCnnjjuEbjpjjujjlEbtllhmoxthBgoaaamFAFFthtAAmA.DppDunqooxE', 'tsCsCkjulbblbjpjblbllxh.howwxggaaaxhmA.FtxA.mA..b.AjuxoxmF.'),
            (' hhhhhhhhhhhhhhhhhhhhlhhhhhhffhfffhhhhh fflhhhhhhhhhhhhfhh', '.xossoDjjjnnpjjlEjjwAAtxAFxqtqqaaaxhmFA.AtEFmFhosCsppwwxAF', '..kqkqwpnCCCCskmt.Fh..mtFtmotqaaaahFFm..At.A..oxxhhoqoox..'),
            ('  hhhffhhhhhfhhhhhhhhhhhfhfhffhfffhhfhhlhhff hhhhhfhhhhll', '..oqooxxsssskxxxkhmthxmtAEtotqaaaahAAmAAAlEA.AmhmmqqqomtF', '..wwpoxoxkokkqqqqoF.AF.mA.thtqwaaaxFAAt.mDEA..AtFxqoxtF..'),
            ('  hfhhhhhhhhhhhfhhh hh fhlhfhhhhffhh  hlfhh hl hhhhhhhhhh', '..FmhwhhthxhwxqgoxF.tt.FFAFtFqqaaaat..FAtuE.EA.AhooxtFAAF', '...mmFxmmAFthFogqhA.mE.Fw.ttmoooaawA..A.tDA.A..oqxmtA....'),
            ('    hfhhfhlhhffhhhh hl fhhflhhhfffflhllhh  hhhhhhhhh', '....lFmtmFmAAtoooxA.FA.toAAhhwwaaahAAEtFF..AqqhhhhFt', '....bFAFmx.F.toqtht....thoA.qooaaah.t..mA..owooowotA'),
            ('      hhhhhffhhhhhhlff fhhhhhhhhffhhhhh h hhhhhhhhh', '......FtFhhxhAFomthAAA.AthAFmogaaamAFxt.A.mqhoxhmAA', '.........E.xhFtt.hF.AA.AAm..FtmhaatFhtA...oowtmtAt.'),
            ('          hhh h h hhll  fhf  hfhhffhhhh   hhhhh', '..........EFt.t.E.mtwq..AmF..AAtwahhtFA...mhttA', '...........A......hm....AAF...AAhahFA.....h.h..'),
            ('                   hhh    h     hh        h', '...................Ftt....A.....Ft........m', '...........................................'),
        ]},
    'sanctum': {"w": 60, "h": 17,
        "pal": [(217, 253, 248), (97, 131, 137), (144, 185, 174), (65, 97, 112), (77, 98, 110), (5, 8, 40), (14, 26, 56), (64, 92, 108), (72, 104, 118), (84, 119, 128), (155, 200, 186), (0, 0, 32), (33, 56, 83), (54, 82, 102), (119, 154, 155), (105, 145, 142), (11, 21, 51), (90, 127, 132), (50, 75, 97), (153, 117, 79), (28, 48, 76), (118, 97, 87), (23, 39, 68), (8, 14, 45), (43, 69, 92), (150, 157, 148), (58, 89, 106), (70, 99, 111), (37, 61, 85), (18, 32, 61), (77, 111, 122), (82, 111, 122)],
        "fb": [195, 66, 109, 59, 59, 17, 17, 240, 241, 242, 116, 17, 23, 23, 246, 66, 17, 66, 23, 101, 17, 95, 17, 17, 23, 247, 23, 59, 23, 17, 242, 242],
        "rows": [
            ('fhhhhfhhhfhfffhhfhhhhfhhhhfffhhfffhhhhhfhhhhhhhfffffhhfhhhhh', 'fxfqgwqgfflllllqxfqwfxxqDuCCCCCCCCuDqxxxDgfxqlllllffgqwgqfxx', 'ffxDDwDyxfflllxxxxDqxxguwwCCCyyCCCwwugqxxwxfxxflllffyDwDDqff'),
            ('fhfhhhhhffffhhhhhhhfhhhffhhhhhhhhhhffhhhfhhhhhhhhfffhfhhhfff', 'ffxqusqgfffffqxfxqwxxguDDuCCCssCCCuDDmgqxwqxfxgflfffgxsmqxxf', 'fxxgwCgfffffgxfxgwDxgmDDDmsnnCCnnsCDDgmgxgwDxfxgfffffxywDxxf'),
            ('hfhhhhfhhhhhhhhhhhfhhhffhhhhhffhhhhhffhhffhhhhhhhhhhhffhhhff', 'xxDwwDffffffqffxDDxqwugDwsndnCCndnnwDgwugxDwxxfqxfffffgwuDxf', 'fxqgmwfxxqgDuDummqxgCggDmAdyCCCCCdACDggmgxqmmuDuwgqxxfgCgqxf'),
            ('ffffhffhfhfhhhhffhhhhfffhhffffffffhhhfffhhhhfhhhhfhfhhfhhfff', 'fxwmyffgxqDwymwxxqDgmgDwnhCCCCCCCCAnwDgmqDgxxDmywDqxgxfCmwxf', 'fxwmBffxxxDCBwxxxwgDCgDwhnCCCCCCCCshuDgmDgwqxxwhyDxxxlfACwxf'),
            ('fffhhhfhffffhhhhhhhhhhhhhhfffhhhffhhhhhhhhhhhhhhhhffffhhhhff', 'xxwCBflfxqDCnfxgDDguygwChdCCCyCCCCAhCwgCmDDDgxfsmDqxflfAywxx', 'xxwsylllxqDCwwDwuAsCwDusEhCCCCAACCnEnmDDCsnmwDDDywqxfllCsuxx'),
            ('fffhffffffhhhhhfhhhhhhhhhhfhhhhfhffhhhhhhhhhfffhhhhfffffhfff', 'xxwsClllxgCsxggwsiygwuynrsCCCCBCCCCrnymwgydswgqxymgxllluswxx', 'xxwCClllxgyifqDwyBguuydEACCysBdCyCCsEiyuughywgqfdyDxllluCwxx'),
            ('ffhhhffffffhfhhhhhfhffhhhffhhhhhffhfhhhfhfhhhfhffhfffffhhhff', 'xqwCmlllxgCdfxDusCgwuyjdCCCCBposyCCmsbsuwgmnuDxfnyDxlllwCuqx', 'xqynwlllxgCAffgCjggDuyEumCCyrcaEyCmmuEyuDggFyDffnCDxlllqnsqx'),
            ('fffhffffhfhhfffffhfffhhfhhhfhfffhhfhfhhhffffhfffhhhfffffhfff', 'fqyiClllxDmnffDCbDgguAEumCCyEaapsCmmuiAugggryDffsmDqlllwEsgf', 'fqyEClllqDsAffDCbgggudjuummyjaapymmuuEimgggrCDffAywqlllwjsgf'),
            ('hhhhhffffhhhffhhhffffhhfffhfhhhhfhfffhhffffhhhffhfhffffhhhhf', 'xDmnDlllxDdEffwCjggguhEuummmezzemmuuuiimgggECwffihwxlllqnmwx', 'fgCiqlllxwAeffDnogggudiuumummvvCmuuuuBdmgggbADffhhuxlllfiCDx'),
            ('hhfhffffhfhhfffhfffhfhhfffhhfhhhhhhffhhfhffhfhffhhfhffffhhhf', 'xwndDlllxuAdffwAbgggujruuuAojppboBuuuFrmDggrADffAhmqlllfisux', 'qDnhDlllquiFffwnbggDurFuuuirjjFjjEmuuBbmwggjAwffBEmglllfdhwx'),
            ('fhhhhhfffhfhfhhhhffffhhfffhhhhhhhhfffhhffhfhhhhfhfhhffhhhhhf', 'xgsdwfllguieffwipggwmrEuuumnmCCmnCuuuBbCwggrEwffhFmglllqinDx', 'xqChgxllgwihfquhbggwmbvuuuuhAddyduuuuepCwDgFiuqfAFwDllxxdCgx'),
            ('fhhhfhffhfhhhhfhhhfffhhhhhhhhhhhhhhhhhhhffhhhfhhhhhhffhfhhff', 'xDmiwfllguBFfqwhrggwmjzvvttAnbjndtvvvztCwggFdwqfBimglllqECDx', 'xguhwxllqunjxgwnpqgwmBAsyssErorsjssyyhBmwgxbnwgxiAuqllxqBuDx'),
            ('hhhhfhhffhhhhffhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhfffhhhffhhhhhhh', 'xqmnDxllqwAdqgwsrqgwmhsmmmmFpbnyjmmmunACwgqEswgxAhuqllxxAmqx', 'fxwsDqxlqDsyxgwCEDwhijjeeeijihiFFFehAjFihwDiywgxCsDqlfqqswxf'),
            ('fffhhhhfffhhhhfhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhffhhhhhhfh', 'xxDCgxxqgDyBqDuyEFhdiiiFEjbbbrrbbbbjjiBidhiFywDxByDqxqxqCDxf', 'xxDunqgqgDmnnwuhFnnnnnnhAiEEiiFjFiBiBAnnnnnihuwCAmDqqgqsmwxx'),
            ('fffhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhffhhhhhhhhffff', 'xxqDsDgxqwCnjEAsssnnnAAhdrrFBdBiEBiddhhAnnsssnEEACwqxggswqxx', 'xxqwuyyiEEdiiBEEEEiijrpozcccccccccccczoobEjbbjEEEEiAAyyuwqxx'),
            ('ffhhhhhhhhffhhhhhhhhhhhhfhhhhhhhhhhhhhhhhhhhhhhhhhfhhhhffhhh', 'ffxqwmmmmmmmynnndBEjjEEFErppppoppbrrrjrrjFhABiAAAsmyymmwqxff', 'ffDwqDwwwummmmmmCsssshiBEFEBiBiiBBBBABBddhmyAdssCCmmmwuwqgqx'),
            ('fhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhfhh', 'lffxxqxxDwwuuuuwuuwuuuuChhhyhyCCCCymwmyCumwuwDwwwwwwgqxxxfff', 'llllfgggqgxxxxqqgqqqqgxxqqxqqggqDgxqqxxxqqxxxxxxxxxxxfffffll'),
        ]},
    'lair': {"w": 60, "h": 17,
        "pal": [(104, 22, 36), (68, 42, 63), (224, 98, 32), (125, 22, 39), (255, 120, 29), (161, 68, 80), (40, 29, 53), (26, 20, 47), (88, 46, 62), (69, 16, 33), (85, 17, 31), (52, 40, 64), (255, 94, 36), (125, 67, 54), (113, 44, 54), (55, 32, 55), (183, 92, 47), (250, 89, 41), (76, 32, 52), (48, 21, 44), (75, 52, 78), (79, 44, 54), (88, 67, 100), (49, 10, 25), (53, 46, 74), (161, 42, 42), (185, 59, 60), (128, 67, 88), (221, 64, 48), (105, 66, 92), (29, 3, 18), (21, 11, 31)],
        "fb": [52, 52, 166, 88, 208, 131, 17, 17, 52, 52, 52, 53, 202, 95, 88, 52, 130, 202, 52, 52, 53, 52, 60, 52, 53, 124, 124, 95, 160, 59, 16, 233],
        "rows": [
            (' ll  l         hh l h lllhllhlhhhll  llll             fl l', '.FF..F.........FF.E.E.EEEFxbjwtussE..EjxE.............FF.F', '.........................E..w.DDD.....................F...'),
            ('h l h h       hh   llflllhhfhfffhhhhhhhhhhhlll          hlfl', 'F.F.F.F.......FE...EjxxbiEgDDBBBBBijbbwijxEijx..........FFFF', '.....................x...iwDBBBBfffffDDwwoi...............F.'),
            ('hf        llll llhhhhhhffhffhfhhhhhhhhhfhfhfhhhfhlllf', 'FF........Exxx.xkxjthhlwDDwBBffffAABffBDwDwwuakjxkjxE', '.F...............thhgbwwDwwBffAACCCAiyuDBDDwwusjk...E'),
            ('         lhfhhhhfhhhffhhffhfhhfhhhffffffhhffhffhhhfhflfl  h', '.........ExxxxktgghlywwDwwDffABACCrrAyyyuBDDDubhggxkjxEx..E', '..........ExhhghghpyywDwwwBfAfBCrrrrAyyyyuDDwubghpxxj.E....'),
            ('       lhhfhffhffhffhfhfffhfhhhffhhhhhhhhhhfhhhhhfhhhhfhl  h', '.......xkxxFhhthhpyyuDDwwDBfAuCrrrrrDyyyiDwDwuighphkkjxxE..x', '........aFxhhhhhhyyywDwwwDffBorrrmmfliiBABDDDwbpgpghjExk....'),
            ('  l  hhh lffffhhhffffffffhfhhhhhhhhhhhhhhffhhhhfffffhhhhhhl', '..x..Ejj.thhhhhglyyywDwwwDfAubfffnisBACCCfBDDDbphhghjkjxkjE', '.....j....hhhhpyyyyywDwwwBfBbfbbbbpppbifAfBBBBiphhghhjxEjx.'),
            ('f   hh lfffhfhffhhfhhfhhffhfhhhhfhhhhhhhhhhhhfhfffhhhfhlhff', 'F...xj.ExthhhhuyyyyuwDwwDBfBoipppbpppbppbviiDBighhpghhjkExE', 'F...jE..xthghpuyuuywDDDDDBBBibsoppssAzibBBBDiBoghhhsgha..xE'),
            ('f  fhh  ffffhhfffffhhhhhhhhffhhhhhffhhhfffhhhhhfhhfffhhhhhf', 'F..xxE..thhphbuuuuuDDDDDDwuyylblblyyubpyyyyyyDoitphsphtaxEx', 'F..xEx..thhpgiuuuuuBwuuuyyyyyyyyyyyyylyyyyoniiiigghspghjj.x'),
            ('   hfhflhffhhfffhhfhhhhhhfffhffffhhhhhhhhfhhhfhhfhfhhhhhffhh', '...xkaExthhhpiuufoiuuyyuyyyylyyyyuyyllylllbyybpigggpgppjjxjx', '...jkjE.xhhpgiuuDiinzibylyyyyyyyyyibiiioilyiibhsghgthhgtjxk.'),
            ('    hhhhhhfhhhhhhhhhhhfhhhhfhfffhfhfhhhhhhhhhhhffhhfffhffhff', '....jjEEjhgppbyyuoioAbllyuibylllllblbnnoilbuibhphgpgghghkxxx', '....kxjjkggggglsCqoibllvblbbllllblglvbgbpblivpgphhtgghhhkkxx'),
            (' hfhhhhhhhfhhhfhhhhhhhhhhhhhhhhhhhhfhhhfhhhhhfhhhhfhhffffhhh', '.EEEaEkxslyllbllnnzzzAAAAdsblbbibiigggglvgbpppbbghspppggaajx', '..Ejk.jkabybiylyylgppnrmmCddsspttpbgsoplyyvybpppbpsbbpggakaE'),
            ('fhffh hhhhhhhhhhhhhhhfhhhhhhhhhhhhhhhhhhhhhhhhhfhhhhhhfffhhh', 'ttxxj.EksuybuyyllgglbginfnzACCAAzdapgllvbboibilllsggpgllakkE', 'tjxxk.xjalllllgpgtthsggiopsdmeemrzdjjjttgllllbblblllbllladxx'),
            ('hflhh hhhhfhhhhfhhhhhhhhhhhhhhhhhhhffhhhhhhfhhfhhhfhhhfhhhhh', 'ttjkk.ExdiivisjjtkkjsadddzCeccqqithhhthhglpppbblllybnbllddEk', 'jt.ax..EavinqvpjjazAzArrrrcopgttbvphhpiooibplvbgbbyyyllbak.x'),
            ('hhhhh  hfhhhhhhhhhhhhhhhhhhhfhfhfhhhhhhhhhhhhhhhhffhhhhhhhhf', 'jjxjk..EkslppsvtjCrmmemcnsbpttggbihtpofccnnpppgglllbbysdkkEx', 'ttFEj...kapkttazAreeemopginothgpbsgggpbpiilgggpppllllaaxaxxx'),
            ('fhhlhl lhhhfhhhffhhhhhhhhhhhhhhhhhhhhhhhfhhhhhhhhhhhhffl lff', 'tphFxs.xasggtkzeermmCojhhtoihtginnpggggggpggioooonybakEx.Fpg', 'ttp.t...dalgzzmeeeecapsptppgthhtpggpozfsggpbnqeecividkE...pg'),
            ('hfhhhhhhfhhhhhhfffhfhhhhhhhhhfhhhhhhfhhhhhhhhfhhhhhhh h hhfh', 'htptFpxaaapaCmemmemeCzzzzdajtttthpphgpvtgthgvinniilax.E.Fptt', 'tttphgsxaxasozcmmeeeeemmrAzddtgpthttggtssviinivbglbkj....gth'),
            ('fffhhfhfhffhhhfhhhhhffhhhfhhhhhhhhhhfhhhhhhhhhhhhhhhh   hhhf', 'gttjttpthtthgggicemrrmemmeCAzkjsjtttjtponqcccnoollaaE...gpth', 'gttpptttttttthggomeermreeermCAzzdddajhhgivnvipnlidkxx...pghh'),
        ]},
    'human_fighter': {"w": 22, "h": 15,
        "pal": [(217, 240, 242), (94, 61, 63), (177, 195, 199), (96, 67, 73), (85, 93, 109), (79, 53, 59), (250, 186, 127), (183, 117, 90), (108, 126, 140), (167, 192, 203), (59, 31, 48), (79, 59, 69), (65, 47, 60), (35, 28, 46), (150, 165, 178), (198, 222, 228), (60, 38, 56), (113, 66, 57), (81, 39, 53), (116, 74, 73), (60, 31, 32), (19, 14, 31), (148, 159, 166), (57, 36, 52), (125, 89, 83), (218, 147, 101), (160, 106, 84), (144, 97, 77), (34, 19, 34), (41, 36, 52), (176, 186, 187), (255, 201, 134)],
        "fb": [255, 59, 250, 239, 59, 237, 216, 137, 66, 250, 52, 238, 237, 234, 247, 253, 236, 59, 52, 59, 52, 233, 247, 236, 95, 173, 131, 95, 234, 235, 250, 222],
        "rows": [
            ('                    lh', '....................ci', '.....................w'),
            ('                   hhh', '...................dpe', '...................Ej.'),
            ('       lhhhhhl    hhh', '.......susqnCn....mae', '........bxDDn.....Ejv'),
            ('     lhfhffhhhl  hhh', '.....uCDssqqnxC..mae', '......rDmsqmqq...Ejn'),
            ('     fhhhhhhhfh hhh', '.....uqkDqfhhnC.mai', '.....unnxtAAAnn.ojn'),
            ('      hhhhhhhhhhhh', '......DfBAhBAmvDai', '......vbFgzFgD.wcD'),
            ('       hhffhhhhhh', '.......vgghFhvnai', '.......CAghzf.wcm'),
            ('   lhhlhhhhfhhhhl', '...tuCurbAhtsdaiv', '....td.tBBytboce.'),
            (' lhhhfhhfhhhhhhhhh', '.frAybbbblmnlawmqC', '..BtAbkmbfkqoceqfm'),
            (' hhfhfhhhhhhhhhfhhh', '.Aydfssqmmklawssbmn', '.tBdmsbfAtsocefsqlm'),
            ('hhfhhfhfhhhhhhhfhhh', 'CBdmnkskBAypwqmkmlD', 'ftdDvkkkDyzhdkskxfq'),
            ('lhhhhhhhhhhhhhffhhh', 'uxDvvCDknmrtrDnCCfx', '.dlxCvnDflmxfBnCvv.'),
            ('hfhhhhhfhhhffhfhhhhl', 'AdnfmqdxbfqDDqCxqxqC', 'bdfttdlxfqxDDDCCvCf.'),
            ('hhhhhhhhhhhhhh  fhh', 'dmxfmqnDnCCkCv..vmn', '..vDnnC.q...v...vq.'),
            ('  hhh  hf', '..vnC..Bu', '.......ru'),
        ]},
    'human_rogue': {"w": 28, "h": 14,
        "pal": [(133, 112, 109), (209, 138, 99), (81, 48, 31), (73, 62, 64), (121, 128, 157), (107, 100, 109), (35, 42, 64), (63, 43, 40), (46, 44, 56), (62, 36, 26), (14, 20, 41), (31, 18, 14), (123, 81, 65), (31, 21, 27), (55, 51, 64), (8, 11, 28), (32, 36, 54), (125, 120, 133), (97, 67, 60), (60, 58, 71), (71, 45, 30), (156, 105, 74), (66, 72, 93), (109, 69, 35), (21, 28, 50), (47, 26, 21), (51, 35, 35), (28, 26, 40), (157, 133, 130), (167, 162, 179), (57, 49, 56), (74, 57, 57)],
        "fb": [243, 173, 52, 238, 103, 241, 236, 236, 236, 236, 233, 233, 95, 234, 237, 232, 235, 243, 239, 237, 52, 131, 238, 58, 234, 234, 235, 234, 138, 248, 236, 237],
        "rows": [
            ('           lhhhhl', '...........qpkypq', '............gyqg.'),
            (' lhh      hffffffh      lhl', '.qdl......hggyqggh......osE', '..ft......dggyqggd.......f.'),
            (' hhhh    hhhhhfhhhh    lhhh', '.dtDl....zogykyygiz....CDtd', '...wC....ugkkyykyqc.....wp.'),
            ('   hhhl  ffhh  hhfh  lhhh', '...yeaA..Fqyy..ykqd..zfeq', '....gD...Fq......qF...Do.'),
            ('     hhlhhhllhhllhhhlhh', '.....wDrzoysmppmsyoAaDw', '.....ke.Fqk..BA..pqd.ey'),
            ('      hhhf fhhhhf hhhh', '......gCsy.Avssvh.qdeg', '.......siy.Abvvbh.yqs.'),
            ('      hhfh hhhhhh hfhh', '......zdyp.nmbbvn.pydz', '......jiy..tnhhnE..yih'),
            ('    lhhhflflhfhhlhlfhhhl', '....znuqypkihqAEgkpyqjnz', '.....Aigy.k.pqBp.B.yBcA.'),
            ('  hhhfhfhfhhhhhhhhhhhhhhhh', '..jvdgykkykqtqqtipykjzqtmu', '..shggqkpynikyyyAzBzzqgghs'),
            ('hhhhhhhhlhhfhhhhhffhhhhhhhhh', 'mvtBEggykplzsmssizackggEqovm', 'uxcgAAqp.kjzpppkBzaopqqAgcxc'),
            (' hhhhh hffhhhhhhhhhfh hhhhh', '.jhcgB.yyyBjzpkkzjByq.Bgchj', '..zjhE.kyyyp.zjz.Bqyk.ohjz.'),
            ('   hhhflhhfhhhhhhfhhlfhhh', '...ljhhlyqkkBjxckkyklhhjl', '.....zh..pkizzAAykp..hA..'),
            ('      hh hhhfhhhhhf hh', '......lj.ppAnkyyiBn.Al', '...........nnAhccjn...'),
            ('            hhhhhh', '............zjuuxu', '.............llz..'),
        ]},
    'human_wizard': {"w": 28, "h": 15,
        "pal": [(41, 61, 130), (132, 57, 20), (35, 50, 115), (255, 245, 202), (28, 9, 49), (255, 203, 77), (39, 15, 61), (22, 5, 39), (191, 148, 139), (135, 74, 64), (59, 87, 158), (17, 5, 19), (254, 153, 52), (78, 27, 16), (62, 45, 68), (52, 15, 15), (22, 21, 68), (56, 22, 76), (230, 126, 70), (97, 75, 96), (44, 47, 97), (84, 59, 118), (233, 222, 192), (167, 106, 83), (147, 118, 150), (175, 78, 41), (151, 121, 113), (95, 123, 189), (39, 12, 23), (91, 50, 50), (203, 177, 147), (239, 223, 146)],
        "fb": [24, 88, 18, 230, 17, 221, 17, 17, 138, 95, 25, 232, 208, 52, 53, 52, 17, 53, 173, 240, 18, 60, 187, 131, 103, 130, 244, 68, 52, 52, 180, 222],
        "rows": [
            ('     llhhhl           l fh', '.....halulu...........p.CC', '.......kkB..............C.'),
            ('   lfhhhfhhhh         hhhh', '...qqccaakBkl.........ClCn', '....qqqqaakBB..........pzb'),
            ('  hhhhhfhhhhhfl     llhhhhll', '..elllqqcaaaBBB.....lpCbsDpp', '......lqqqckkB........Dsmz..'),
            ('       ffffhhhfhl  lfhhhfhhh', '.......qqcakBBByo..lpnzffznC', '.......qqcaaakBi....pbmFfsbp'),
            ('       ffhhhhhhhhhlhhfhffhhf', '.......qqquuuttAylBCnbmddmbp', '.......qqgooovkBBB.ytbfddfzp'),
            ('      lhhhhhfhhhhhfhhffffhfh', '......hgggquaaBBvugovyiEdfsC', '.......qquccavjzxrgrtyiEdFs.'),
            (' lllhhfhhhhhhhffhhffhhhhhhh', '.qucquuquccqCnjsjovvtjsdFfb', '....ccuuqhgnxxjsivvvClzmmz.'),
            ('hhhhfhlhhhhhhhhhhh    hhhh', 'eeeehlhlpngDsmzssh....jjjb', '...hhh.ggpoojxjxi.....pnbC'),
            ('     lfhfhffhhhfhh     fh', '.....gooohttDEEiwD.....nD', '......otogttAAAiEi.....nz'),
            ('    lfhhhhffhhfffhl    hh', '....eheoeDtttAwddEp....pb', '.....hhehottAiwddi.....Cp'),
            ('  lhhhhhhhhhhhhhhfl    fh', '..eehehrrhroAiEddwr....ll', '...heggegregjAAwww.....lC'),
            (' hfhhhhffffhhhhfhhhf   hh', '.hhegrrrrrrettAiEEgg...Cp', '.ehhhegrrrrgeDtiAorg...pn'),
            ('fhfhhffhhhfhhhhhhhhhh  ff', 'hheeeeegrrrghloAAggrl..pn', 'heehheeeggrrreltoerg...pn'),
            ('        hhhfffhhhhh    ff', '........hggggelgere....pn', '..........hggehege.....pn'),
            ('            hhfhh       h', '............hgerg.......C', '..............eg.........'),
        ]},
    'human_cleric': {"w": 22, "h": 15,
        "pal": [(249, 167, 114), (151, 127, 135), (237, 171, 141), (168, 146, 148), (127, 106, 114), (125, 62, 66), (233, 215, 206), (203, 164, 151), (226, 198, 186), (156, 107, 110), (85, 36, 40), (251, 240, 224), (253, 200, 111), (179, 128, 130), (109, 46, 35), (84, 57, 64), (220, 125, 45), (157, 76, 52), (196, 172, 169), (234, 149, 48), (213, 128, 106), (189, 149, 145), (240, 218, 190), (211, 102, 46), (110, 89, 86), (219, 186, 176), (228, 150, 101), (42, 23, 19), (248, 207, 138), (251, 190, 51), (185, 106, 43), (168, 103, 78)],
        "fb": [216, 102, 216, 138, 242, 95, 253, 181, 252, 131, 52, 255, 222, 138, 88, 238, 172, 95, 249, 208, 173, 138, 223, 166, 59, 181, 173, 234, 222, 214, 130, 131],
        "rows": [
            ('   f      llll', '...o......ywdB', '...o..........'),
            (' fhhf   lhhfhhhl', '.BBBB...bdlfizpB', '.BqoB....lbffsz.'),
            ('lhhhl  lfhhhhhhh', 'oxDro..ylvrrffve', '.DlD....lrAauoyv'),
            ('hhfff  hhhhhhhhhh', 'EClCr..eiFraArfvB', 'omlCr..zgAmCaardp'),
            (' hhhf hfhhhhhhhhhl', '.FtxB.BlduCmaarebB', '.ofkB.eljraxuAopd.'),
            (' hhh lfhhhhhhhhfhh', '.kkk.kwwfkuaaFkkbe', '..oB..wAndcAAcfked'),
            ('  f lhhhhhhhhhfhhhl', '..k.Boilizlwgifpdjo', '..k..txcliwizcfjjr.'),
            ('  fhfffhhhhhhhhhfhfhl', '..kBtDDxuizccvffrqxoB', '..kntDDtizvAunbortxE.'),
            (' lhhhhhhhhhhfhhhhhhhh', '.kkzatqDiCFDqFayrxxjp', '..rccitCctDtqtEstEsve'),
            ('lfffhhfhhhfhhhhhhffhhl', 'BaauilllcqtmDqEzgigibB', '.aaugglwDttDtxqAwigsd.'),
            ('hhhfhfhhhhfffhhfhhfffh', 'BaAulgglhEqqxxrsgizdvp', '.nfuggzgctqqxExsizzdve'),
            (' hhhhhhhhhhhhhhhfhhfhh', '.pfdzzsihisuusivsvzbbp', '..kevddznzizslvnsbsbe.'),
            ('  fhhhfhfffffhffhfhh', '..kBebbznszsiinnsbvp', '..k..ybdnszsisnndbe.'),
            ('  hh  hhhhhhfffhhh', '..oB..yjjhzzsvnnby', '..B....erbsssvnjy.'),
            ('        hhhhhhhh', '........kjbdddbp', '..........pyyp..'),
        ]},
    'elf_fighter': {"w": 28, "h": 13,
        "pal": [(125, 115, 123), (39, 38, 44), (22, 71, 50), (167, 131, 108), (141, 103, 98), (50, 115, 61), (196, 200, 170), (190, 115, 94), (248, 204, 141), (166, 161, 147), (43, 31, 26), (36, 96, 56), (177, 185, 173), (13, 36, 39), (181, 95, 77), (81, 84, 68), (148, 96, 76), (201, 212, 198), (148, 145, 141), (61, 35, 33), (250, 190, 130), (102, 57, 51), (99, 88, 73), (69, 70, 75), (104, 89, 103), (23, 26, 26), (126, 97, 98), (22, 54, 48), (218, 140, 103), (125, 132, 123), (53, 49, 54), (68, 55, 52)],
        "fb": [243, 235, 23, 137, 95, 29, 251, 137, 222, 247, 235, 22, 249, 234, 131, 239, 95, 252, 246, 236, 216, 88, 240, 238, 59, 234, 95, 236, 173, 244, 236, 237],
        "rows": [
            ('hl         lhhhhhll', 'bp.........dpDDDDrp', 'w...........msgmg..'),
            ('hhhl     hhhhhfhfffh', 'zmFb.....zgjDrrrrrrE', '.eg......dsaysrgrrrD'),
            (' hhhh   fhhhhhhhhfhfll', '.vjrE...kmyhChaajmmsFw', '.kyaa...kjhiiuhAamgs..'),
            ('  hhf   fhhhhhhhhhhfhh', '..zFF...zdvCuqvhyadhCk', '...EF...zewACCdCaAqht.'),
            ('   hhh   fhhhfffhhhhh', '...taa...wACiiiuAdqAk', '....bv...wvhCiiuhsyjp'),
            ('     hh lhfhfhfhhhfhfl', '.....zk.wdyoCuiiCmamsb', '......t..eyyCiihdsags.'),
            ('       flhffhhhhhhfhh', '.......kdeyyAqqoDAygj', '.......k.ayyxFBnayyDD'),
            ('      lhhhhhhffhfhhhhhhlll', '......FwjyxEznnEyyccDlpffF', '.......syEznnnnByxBllff...'),
            ('     hhhhhhhhhfhhfhhfhhhhhhf', '.....EdyEkFwBBcBaBcfllllDmmk', '.....waxzbpxbccwEBlllfxxxybk'),
            ('     hhhhhhhhhhhhhhhhhhhhhh', '.....axnnbttwwFvtbllcxEEbzz', '.....EnBbEbFavvtBcBEbEbz...'),
            ('       hfffhffhhfffhhh', '.......znnnbttFxccBBck', '........nnntttxtccBnz.'),
            ('        hhhhhhhhhhh', '........nnbtkEkvtcn', '.........ztkBBBtvk.'),
            ('          hhfhhhh', '..........znncBnt', '............nnn..'),
        ]},
    'elf_rogue': {"w": 26, "h": 15,
        "pal": [(133, 63, 73), (44, 24, 69), (68, 80, 73), (64, 77, 95), (25, 59, 52), (30, 23, 55), (254, 193, 158), (236, 146, 122), (99, 67, 66), (41, 108, 88), (86, 79, 94), (99, 93, 77), (133, 54, 80), (248, 173, 136), (71, 63, 70), (36, 81, 82), (41, 89, 87), (166, 76, 89), (68, 36, 74), (70, 27, 54), (134, 82, 85), (36, 63, 82), (38, 41, 71), (36, 46, 78), (187, 102, 97), (101, 40, 72), (28, 28, 26), (208, 133, 102), (156, 132, 117), (43, 135, 91), (88, 102, 96), (100, 120, 126)],
        "fb": [95, 17, 239, 239, 236, 17, 216, 209, 239, 23, 239, 59, 89, 216, 238, 23, 23, 131, 53, 52, 95, 23, 17, 17, 131, 53, 234, 173, 245, 29, 241, 243],
        "rows": [
            ('           lhhhhl', '...........pApqAp', '............jDDj.'),
            ('         lhffffffhl', '.........epjDDDDjje', '..........qjDDDDjD.'),
            ('        lhhhhhhhhffl', '........eqqjpjDDqDDA', '.........pvzmzojjDD.'),
            ('     lllhhhhhfhhhfhhll', '.....tuAcpzBhymzqqDeey', '........EvyyByByzqjp..'),
            (' lhhhlhhhhfhfhhhhhhhhh', '.oiiceayCzmzyhnrzccCyt', '..CCF..rmmmCynhCCzora.'),
            ('hfhhhhlhhhfffhhfffhhh', 'iCCkvcoomrygnngggrzap', '.CsFoF.xbaygnBnggrswq'),
            (' hhhhhhhhhhhhhhfhfhfhh', '.AodFdFwbyrnghgghysbqq', '..AiEEEbtBuynyBgmyzbvj'),
            ('   hhhhfhhhhhhhhhhffhh', '...AocqbmBusygnrmrabxj', '....AwpbanitmmrBayabvw'),
            ('    lhhhffhhhhhhhfhhhhl', '....EcwplBztryhgaBupxxD', '.....jvwlBosECCFkBlwvj.'),
            ('   hhhhfhhhhhhhhhhhhfffhl', '...AcjjponxqqFdqvnovjDDje', '...EvxxpvCbbvxvwxBvqjDDD.'),
            ('  hhhfhfhhhhfffhhhhhhhhhhh', '..lqjqvxxivpsEEwvCpjjjDDDe', '..cppqqxzrbwsEEbbivqqvwwx.'),
            ('   hfhhhhhhhhhhhhhhhhhhhh', '...fwwwbmtmwxkdxxvxxwvxvA', '....wvsztmtsvxvvpppppppA.'),
            ('     hhhhhhhhhhhhfhhhh', '.....fzmtbzaiqjpjqjDqp', '......ttwvsmzcqqqqqqv.'),
            ('        hhhhhhfhhhhh', '........vjlszzzpqpvw', '.........evvstzaoxA.'),
            ('           hhhhhh', '...........wxbzbt', '............Awf..'),
        ]},
    'elf_wizard': {"w": 26, "h": 15,
        "pal": [(44, 6, 72), (205, 116, 123), (124, 75, 65), (98, 61, 54), (32, 4, 63), (121, 17, 87), (255, 226, 81), (91, 52, 56), (66, 37, 39), (252, 165, 47), (228, 158, 142), (196, 143, 90), (86, 16, 83), (177, 98, 105), (69, 34, 71), (222, 150, 82), (169, 117, 99), (118, 43, 52), (172, 113, 70), (125, 45, 82), (60, 10, 77), (158, 94, 71), (147, 37, 84), (39, 17, 40), (160, 76, 70), (51, 7, 43), (254, 206, 162), (15, 2, 34), (98, 79, 69), (205, 120, 90), (72, 18, 32), (81, 15, 74)],
        "fb": [17, 174, 95, 59, 17, 89, 221, 52, 236, 214, 181, 173, 53, 131, 53, 173, 137, 88, 130, 89, 53, 131, 89, 17, 131, 52, 223, 17, 240, 173, 52, 53],
        "rows": [
            ('         lhhhhhhhl', '.........dxdcvvdxs', '..........vsslpps.'),
            ('       lhffhfhfhhffh', '.......xhccssDlplslx', '........cccvssllpsls'),
            ('       fffhfhfhhhhhhh', '.......iddvssssslyhvi', '.......iddcslsyvkAndd'),
            ('      hhhhfhfhhhfhhhh', '......tdhhvsnnbqAAqhd', '......BywcvnnthbAqdi.'),
            ('       hhhhhfhhfhhfh   l', '.......cywvnklbbkvxi...E', '.......htyybkAAbbAx.....'),
            ('      hhfhffhffhfhl  hl', '......idditbkAAbkkx..rE', '......hcdhtbbAAkkl...y.'),
            ('     hhhfhhfhhhhhfh  lhh', '.....xhccdtybAkbksi..xEx', '.....iidcvyytbAAqsx...yr'),
            ('    lhhhhhhhhhhhhfl lhhfh', '....uiiicvybytyccvz.EEpDE', '.....aazhcdtbkkBhv...pjDx'),
            ('  llffhhhhhhhhhhhhhhffffh', '..BuuuFuuhceoqkBBvmFrjgjr', '....uuuFmmFoaooeetfwrjgjy'),
            (' hfhfhfhhhhfhhhhfffhhfffhf', '.eaaauuFFfwfFuueffwwDgggpB', '.aauaaummmmffffFffwtvgggjB'),
            ('hhhhhhhhhhfhfhffhhhfhhhhh', 'eeBBeeeefwfwfmmFffwfrpggy', '.BeaaaumeaffffmFvtmfEvpDq'),
            (' hhfffhfhhhhhhfhhhhhhhhhhh', '.eaaaauwuexeaFudllrfnqnqDv', '..eaaamwfaeoFmuzCsuFkdhbAh'),
            ('  hhhfhfhfhhhfhfhhfhfhhffh', '..BaaaFmfaazFmFexCBtknnbnc', '....eaummaueEmmeBaBckbbbnh'),
            ('     hhfhhhhhhhhfhhhfhhhh', '.....eaaFuaauzFBBBxbbbnyi', '......BauFuumuzEBeonbyx..'),
            ('        hhhhhhhhhhhhh', '........euuammeBeBaoE', '..........BezB.....B.'),
        ]},
    'elf_cleric': {"w": 25, "h": 15,
        "pal": [(76, 74, 75), (234, 203, 138), (149, 121, 111), (97, 86, 68), (180, 179, 185), (243, 207, 175), (190, 163, 140), (70, 60, 45), (229, 189, 130), (229, 209, 160), (159, 131, 115), (212, 157, 99), (168, 103, 78), (185, 126, 109), (204, 136, 87), (212, 151, 130), (251, 218, 192), (219, 167, 141), (109, 103, 106), (181, 145, 126), (189, 149, 114), (131, 103, 72), (36, 26, 18), (214, 188, 154), (48, 45, 43), (189, 115, 79), (167, 77, 68), (155, 129, 124), (145, 143, 151), (214, 178, 131), (233, 186, 155), (237, 192, 169)],
        "fb": [239, 186, 244, 240, 249, 223, 144, 237, 180, 187, 138, 179, 131, 138, 173, 174, 223, 180, 242, 138, 137, 95, 234, 180, 236, 137, 131, 102, 246, 180, 216, 216],
        "rows": [
            ('       llhhhhhhhll', '.......yCaCeeeCsey', '.........Chw..hC..'),
            ('      hhhlllllllhhh', '......yeaygblbgdaey', '......Ca.........aC'),
            ('     hhlhfffffhhhlhh', '.....asydjqbbbqbdyda', '.....cw.Djqbbbjji.wB'),
            ('    lflhfhhhhhhhfhlfl', '....yswujjbfqffjjuwsy', '.....s.ijDreCexlji.s.'),
            ('    hhhhhhhhhfhfhhhhh', '....kcwiDrfFeFfEDiyct', '....wrtDbEpEfFpEbDtry'),
            ('     hhhhhhhfhhhhhhh', '.....vrDFBcrqEcBEErc', '......poEErfqFxrFnpw'),
            ('      hhhhfhhhfhhhhl', '......zrrqqqqqqqErow', '......lbofqfFfqfziD.'),
            ('     hfhhhhhfhhhhhhh', '.....hbjlrqrprqrmbid', '.....DbbDzFfpFFzzDbD'),
            ('    hhhhhfhhhhhfhfhhh', '....dibilmzEFEzmzobDv', '....Dllbomtmzmnmmooiu'),
            ('   lfhhhhhfhhhfhfhhhfl', '...vlllbzmkkttkmmzoDod', '....loiDmckBkBkcmmzoo.'),
            ('  hhhhhhhhhhhfhhhhhhhfh', '..wlozinccBBkkBcccmzoow', '..vomDukBBkkBkkkkkcAmov'),
            (' lhhhhhhhhhhfhhhhhffhhhh', '.tDuAlAnDxgxnDgxDtAAAuuw', '..xjgmzArjppnAujrAAAujxg'),
            ('hhhhfhhhfhhhhhhhffhhffhhh', 'yjjxjgoAAmAgtnAmAAAujxjjh', 'txxjjjumAAnnrtnAAAujjxxxt'),
            ('hhhhhhfhhhhhhhhhhhfhhhhhh', 'ycxjxxxtArDtAnDDmnxxxjxcy', '...aakxxrxxDgDxxrxxtaaw..'),
            ('      hhhhhhhhhhhhh', '......ytjjjDjxjjjuh', '........wdkgxgksw..'),
        ]},
    'dwarf_fighter': {"w": 28, "h": 13,
        "pal": [(71, 71, 94), (78, 80, 102), (244, 169, 131), (212, 161, 124), (139, 80, 80), (161, 55, 27), (199, 53, 24), (254, 216, 167), (82, 31, 36), (140, 56, 46), (140, 164, 170), (154, 146, 135), (143, 33, 30), (116, 51, 40), (210, 139, 110), (90, 100, 118), (79, 51, 34), (76, 67, 77), (109, 30, 37), (231, 188, 147), (53, 39, 65), (171, 124, 98), (111, 124, 137), (222, 119, 50), (45, 20, 44), (122, 106, 99), (76, 17, 36), (38, 13, 21), (70, 50, 70), (109, 76, 70), (176, 83, 43), (175, 78, 72)],
        "fb": [239, 239, 216, 180, 95, 124, 160, 223, 52, 88, 109, 246, 88, 88, 173, 241, 52, 238, 52, 180, 53, 137, 243, 173, 52, 242, 52, 233, 237, 59, 130, 131],
        "rows": [
            ('       lhh          hhl', '.......qBz..........zyD', '........tu..........Bt.'),
            ('      lffl  llhhhl  lffh', '......qdtq..ywCCBu..iltB', '.......dt.....ppk....ltD'),
            ('      hhhhhfhhhhhfhhhhhh', '......BvhtDaaklklpardhvq', '.......DvlpablapwpbpvvD.'),
            ('llll llhhhhhhhhhhhhhhh', 'rzlB.bkBzDuyuCbwaCyurz', '.......wBuyuzbppbpayy.'),
            ('hffhhhhhhhhhhhhhhhhhhh', 'zkkpzpzwnDuyAyabyiAuDi', 'qkkDpbbbyvFgsisissgEoB'),
            ('hhhhhhhhflhhhhhhhhhfh', 'qkkpyyiAiqjfvvxcvomms', 'BzpC..Bsi.gsdhhhhhjmE'),
            ('      hflhfhhfhhfhffh', '......BnBqxschhchhsmj', '.......n..xiehdohvsms'),
            ('       hhhhhhhhhhhhhhl l', '.......iAujisjctFismqs.q', '.......ysbCAfnsssngfi...'),
            ('      lhhhhfhhfhhhffhhhhhhll', '......qDtFDynxEfxnmmAAeddnCu', '.......FhcvyCnEEfAmmyudenv..'),
            ('      hhhhhhfhhhhfhhhhhhhhhh', '......vfctCuaaCuuyimseecFBDi', '......qeFAACapbCayawFpryB...'),
            ('      hhhhhhhhhhhhhhhhhh', '......raCnyyuyjDiyAisCua', '.......yAiAnAAEsnAfgmgA.'),
            ('         fffhhhhhfhhhh', '.........AnuCarruymgiB', '.........AnuapaCayis..'),
            ('         hhhhhhhhh', '.........rauyaaCuu', '..............yy..'),
        ]},
    'dwarf_rogue': {"w": 28, "h": 13,
        "pal": [(146, 64, 28), (31, 24, 35), (161, 71, 31), (193, 115, 94), (123, 66, 56), (117, 55, 35), (58, 34, 32), (217, 94, 33), (46, 29, 33), (36, 23, 28), (35, 20, 17), (215, 132, 107), (164, 99, 83), (133, 62, 36), (72, 39, 47), (35, 26, 36), (133, 81, 67), (70, 40, 33), (77, 42, 49), (59, 29, 24), (69, 33, 26), (152, 87, 55), (67, 39, 43), (49, 30, 39), (81, 49, 47), (59, 35, 42), (83, 42, 32), (48, 26, 24), (100, 50, 32), (25, 18, 25), (104, 53, 48), (99, 64, 55)],
        "fb": [124, 234, 130, 167, 95, 88, 235, 166, 235, 234, 234, 173, 131, 88, 52, 234, 95, 52, 52, 52, 52, 95, 236, 235, 52, 236, 52, 234, 52, 233, 88, 59],
        "rows": [
            ('         lhhhhhll', '.........ukfnCkCk', '..........nsssE..'),
            ('        hhffhffhhhl', '........tnssssssfuB', '........czssossopa.'),
            (' l  l lhhhhhhhhffhh', '.k..y.kaywssooozbra', '.......fxgEowzzzbpc'),
            (' hhhhl fhfhhhhhhffhh', '.jFqFi.AAmldqpxzbbck', '.FvyD..Aqmdlr.bwbbCC'),
            ('hhhhhhlhhhhlllhhhffhhl', 'FFrgDigAAjeqrFozppxhtk', '..kir..Cmmd...ExzpxEh.'),
            ('   hhhhhhhhhhhhhhhhhhhl', '...gpBAiemdelmeDxzppfck', '....gtf.rwjDww...xxbpC.'),
            ('   hhhhhhhhhh     hfhhhll', '...krjCjyjeeD.....zbpitCA', '...DCgABBiwyi.....xbbDj..'),
            ('   lhhhhhhhh     hhhhhhhhhl', '...uCCArypxp.....DxDttjbinn', '....hruyzxpb.....xbtrgzzpx.'),
            ('  hhhhhhhhlh   lhhhhhfffhhhh', '..uaezgwzbpD...jjxgugossopxf', '..BEsszgpD.p....byFtwossszbj'),
            ('   hhhfhhfh   lhhhhhfhfhhh', '...wwssipbD...xDgrBywzssso', '....zoszgb.....zuujxwssoz.'),
            ('    hfffhfhlhhhhhhfhhhhh', '....iwszBbDgryygBixwowxb', '.....wszgb..Argmybxxbbb.'),
            ('     hhhhlhhhhfhhhhfhh', '.....DowDDbprtqyibbbbb', '......izx.zwsFqFgipb..'),
            ('        hhhhhhhhhh', '........iowowjwgyr', '..........xzttD...'),
        ]},
    'dwarf_wizard': {"w": 28, "h": 14,
        "pal": [(58, 52, 83), (204, 185, 165), (195, 172, 154), (229, 137, 98), (25, 22, 47), (79, 89, 113), (47, 48, 80), (85, 64, 82), (72, 61, 84), (34, 34, 64), (163, 135, 124), (50, 38, 59), (46, 27, 31), (221, 208, 191), (68, 56, 84), (216, 198, 178), (67, 31, 30), (24, 17, 20), (142, 117, 113), (236, 222, 202), (52, 45, 65), (232, 160, 123), (84, 135, 158), (79, 53, 59), (67, 74, 103), (123, 105, 106), (123, 74, 75), (205, 127, 99), (173, 104, 89), (175, 153, 140), (103, 56, 55), (128, 66, 58)],
        "fb": [53, 250, 249, 173, 17, 240, 53, 238, 238, 17, 138, 236, 235, 252, 53, 251, 52, 233, 244, 254, 236, 180, 67, 237, 24, 242, 95, 173, 131, 247, 88, 95],
        "rows": [
            ('         lhhhhhll', '.........AqDppspx', '..........tnbnn..'),
            ('        lhhhhhhhhl', '........qdcDDBBnDh', '.........vdddddBn.'),
            ('        hfhhfhhhfhl', '........CdddddBbbzm', '........vdBBdbvcbB.'),
            ('       hhhhhhhhhhhh', '.......ADDCkDsCBkAm', '........BABCACdCCFx'),
            ('     l hhhhhhffhhhfhl', '.....r.mdBdCCdCzkCDmr', '.......DvDCsDdCkDzDz.'),
            ('     hhhhhhhhhhhhhhhhfl', '.....mbptbzcntCbcsxluEr', '.....EkDszkskpnnpzmxEE.'),
            ('   lhfhhhhhhhhhhhhfhhhhll', '...rmFckDppbzzkDzxEEExqFr', '....FFsntttnbDDzkAEFFEF..'),
            (' lhhhhfhffhhffhfhhhfhhhhhl', '.qmFuxznnttntbnkhxxxxExlee', '..Fiajzcntnttbbklluxljgjg.'),
            ('hhhfhfhhhfhfhhhhhhhhhffhffl', 'qwfhhgkDpnntpbDzuulejaoajgg', 'lfhhaghbbnttbcsueegggaohjg.'),
            (' hfhhhhhhhhfhhhhffhhfhhhhhhh', '.AwogojbbntpbDijjaaojaohogfj', '.ywylhgknpppDiugjaoijgifhuyr'),
            ('  hhhhfhhhhhhhfhfhhhhfhhhh', '..gjaigfDbbkujhajaoiajfwfu', '...gfogesDzujahojgihojafm.'),
            ('   hhhhhhhfffhhffhhhhhh', '...gwfjeygeegohojuiwour', '....ageisfeegiiojjyfye.'),
            ('     hhhfhhhfffhfhhh', '.....eeDbcijgiwigjgj', '.......kbDyygiwyg...'),
            ('       hhhhhhhhh', '.......rDkerjljr', '........mA......'),
        ]},
    'dwarf_cleric': {"w": 26, "h": 15,
        "pal": [(159, 74, 35), (253, 186, 140), (203, 122, 95), (84, 75, 89), (255, 196, 147), (146, 69, 40), (156, 148, 152), (144, 66, 34), (34, 10, 5), (168, 69, 34), (34, 27, 36), (254, 162, 26), (219, 148, 115), (255, 205, 25), (104, 91, 99), (106, 86, 88), (125, 64, 55), (95, 59, 60), (118, 106, 116), (163, 95, 74), (214, 91, 33), (231, 123, 48), (245, 163, 126), (59, 48, 60), (195, 178, 168), (187, 105, 77), (181, 131, 115), (146, 81, 66), (125, 54, 33), (103, 41, 30), (72, 25, 19), (76, 34, 35)],
        "fb": [130, 216, 173, 239, 223, 95, 246, 94, 233, 130, 234, 214, 173, 220, 59, 59, 95, 59, 242, 131, 166, 173, 216, 236, 249, 131, 138, 95, 88, 52, 52, 52],
        "rows": [
            ('          lhhhhhhl', '..........CEDChDiC', '...........fhhajf.'),
            ('        hhhhhhhhhhhl', '........iCaaatChahFE', '........Dffhceectcc.'),
            ('        hhhhffffffhh', '........DCDceebeeebq', '........Caateebeeeet'),
            ('       lhfhhhhhhhhhh', '.......FCChtebmeeeem', '........mCDbwttBcbtB'),
            ('       hfhhhhhhhhhhh', '.......tczteebgBwbzr', '.......Bcahmbeeeeewc'),
            ('   fl  hhhfhhhhhhhhhl', '...Di..icthceeebmbwci', '...D...DCChabbwzfChq.'),
            ('  hhl hfffhhhhhfhhhhh', '..Dji.iDDDhaBzffhthhD', '..ju..DDDDDfaCCftDtfC'),
            (' hhhhhhhhhhfhfhhfhhhfl', '.iiuussDFtBCfhhffhqfCx', '.E.ElztzxkzCChaafaaCC.'),
            (' fhfhhfhhhhhhhhhfffhhhhhl', '.iDllvvtsxkqDCfaaaaahooki', '.ivlnlvsopdkxFDfaaahffsp.'),
            ('hhhfffhhhhhhhhhhhhhhhhhhfl', 'krvlnnlzosssdkkrhahDhqosxx', 'xsplnnnvddxoggsythpdqppdx.'),
            (' hhhhhhhhhhhhhffhhhhhhhhh', '.ppazvvAorCExsgyysdkxprod', '..doxrBssEDjBkgygpxFFkxx.'),
            ('   hhhhhhhhhhhhhhhhfh', '...kdprdqmwCjrpggkFDD', '.......iweemDaqxFFEDx'),
            ('       hhhhhhfhhhhhhh', '.......BmbeetDqrxEDFk', '.......CcwbbwDxddxED.'),
            ('       hhhhhhhhhffhh', '.......Eqcmbprppodxi', '........EqcBsydoodk.'),
            ('         hhhhhhhhh', '.........EDidgopdk', '............kx.xk.'),
        ]},
    'halfling_fighter': {"w": 23, "h": 15,
        "pal": [(255, 199, 139), (255, 192, 134), (217, 220, 225), (162, 162, 168), (138, 61, 41), (136, 60, 47), (174, 89, 61), (246, 175, 122), (164, 110, 77), (155, 76, 56), (154, 120, 99), (219, 134, 92), (132, 68, 56), (239, 205, 169), (77, 75, 94), (160, 88, 62), (131, 57, 42), (90, 105, 111), (117, 52, 41), (80, 55, 61), (195, 108, 72), (201, 138, 93), (244, 179, 130), (186, 99, 42), (107, 38, 34), (75, 154, 148), (167, 43, 34), (43, 14, 14), (225, 158, 114), (152, 74, 40), (75, 23, 19), (86, 39, 34)],
        "fb": [222, 216, 253, 247, 88, 88, 131, 216, 131, 95, 101, 173, 95, 223, 239, 131, 88, 241, 88, 237, 166, 173, 216, 130, 88, 66, 124, 52, 180, 94, 52, 52],
        "rows": [
            ('       llhllll', '.......EBEeBqB', '.........e....'),
            ('     lhhhhhhhhhfh', '.....qFupxDxugxxB', '......DxuDugxxgxs'),
            ('   lhfhfhhhhhhhhhh', '...FggpDguDxuxDDxs', '....xgxDugsuxqpugD'),
            ('   hhhhhhhhhhhhhhh', '...EeeeqeDDDpesqqq', '....EyEhgyefghhyEE'),
            ('  llhhhhhhfhhhhhhhhl', '..EhBomwwwwbabwmoEBm', '....vmusBvwhCFspmvb.'),
            ('l hhhhhhhhhhhhfhhhfh', 'B.FlvigaiyCCsjbupvlm', '...vljubFiaaCFbljul.'),
            ('fhlfhhfhhhhhhfffhhh', 'rdoBlluahwanbhalulE', 'rc.ByjubCCllChaljsF'),
            ('hhflffhhhhhhhhhhhhf', 'occtEyewCivvpCbgyyB', '.dc.EyEpbauuahgfefB'),
            (' hhh hhhhhhhhhhffhhhl', '.ocr.BByqlbwvxlggulym', '.Bdk..rsAAqeujfggeDu.'),
            ('  hhhhfhhhhhhhhhhhfhhh', '..rdBFzrAAAuqguuuguelF', '..Bjmszztyjgjppggxuuju'),
            (' hhhhhhhfhffhhhhhhhhhhh', '.FqffCorztpsfjgmqjmuquE', '.BsluvtzzmpsmmqjpejxpgF'),
            ('  hhhhhhhhhhffhhhhhhhhh', '..mhlvporopFfsqfjpfgpgy', '..BlhusEFFjsfssjqejjjDF'),
            ('   hhfhhhhhhhfhhhhhhhhh', '...slqEptFesffsyyyjqspE', '....Bqskviseyfqqsfqffj.'),
            ('      hhhhhhhhfhhfhhhh', '......BkCCDjyffqssfyjF', '.......Bivvyjqffyssjs.'),
            ('            hhhhhhhh', '............EjDfqejy', '.............BEFFFB.'),
        ]},
    'halfling_rogue': {"w": 25, "h": 15,
        "pal": [(48, 17, 35), (51, 18, 36), (255, 154, 116), (90, 27, 39), (247, 138, 107), (67, 18, 28), (154, 45, 53), (122, 57, 51), (56, 15, 25), (77, 19, 25), (35, 11, 25), (139, 54, 53), (171, 54, 52), (63, 21, 36), (81, 25, 38), (211, 101, 85), (80, 29, 27), (234, 130, 101), (180, 74, 66), (39, 7, 13), (121, 33, 42), (62, 19, 17), (134, 37, 46), (103, 38, 33), (58, 11, 14), (45, 15, 31), (153, 62, 58), (101, 26, 34), (186, 91, 76), (28, 4, 11), (98, 32, 42), (109, 32, 43)],
        "fb": [52, 52, 209, 52, 209, 52, 124, 88, 52, 52, 52, 88, 124, 52, 52, 167, 52, 173, 131, 52, 88, 52, 88, 52, 52, 52, 124, 52, 131, 16, 52, 88],
        "rows": [
            ('       llhhhhll', '.......DuyBfkak', '.........gwaa..'),
            ('     lhhhffhffffhl', '.....Bymgggnaaaakz', '......mdBgguaaaaa.'),
            ('    hhhllhhhhhhfffhl', '....yEkfdDjgoaaaaaaE', '....vjd..B.DFobaaab.'),
            ('    hhhhhfhhlhhhhffhh', '....twwwfitttjdbaaadt', '....FFofiif..FyFnaanv'),
            ('  lhhhlfllhhhhhhhhffh', '..DgutBtvgtDscltwbaaf', '...wfD.t..srceAiyFaad'),
            ('  lhhhh hfhfhhhhhhhfhh', '..ysFoj.vqrchDfBtFbanD', '...lwyi.hqpcCsqwjtdabj'),
            ('hlhhhfflfhhhfhhhh hhfhl', 'vjvBEDDtCrccceepj.dbadf', 'F.FdnDD.CcCecccst.foab.'),
            ('hhhhfhflhhfhhhhhhh hhhhl', 'tdodtuoiAcppcceADD.unadf', '.vBwtwo.jeprppcsi..yEbb.'),
            ('hhhhlhhhhhhhhhhhh  hhfhh', 'tvudDuFutheCpcpid..DEabo', '..Ff.fuEiDueesFjt..Fnao.'),
            ('   hhfhh   hhhhhhhhhhhh', '...wjtjz...ttwmjtjFnbzt', '....xtDi...vmsxdFdbzki.'),
            ('   hhhl hllhhhhhhhhhhhhl', '...tjtB.ttjwluFobakzknFt', '...juq..i..ldkdEuuEudbu.'),
            ('     hhhhhhhhhhhhhfffhhh', '.....vgoihxifFEFdbkkkazj', '.....mExAEEnnkzkkkkkkD.k'),
            ('    hhhhfhhhhhfhhhhhhh', '....ymlChjjEikkzaabbbz', '....ulsdhyqqlEkDkkzzkD'),
            ('    hhhhhfhfhhhhhhhhh', '....jgwixqqxvlnkDDkkD', '....kizDvqxxqAdbazD..'),
            ('      h hhhhfhhhhhh', '......D.qxxxxhtikkD', '.........itqx......'),
        ]},
    'halfling_wizard': {"w": 25, "h": 15,
        "pal": [(40, 70, 130), (7, 10, 35), (31, 48, 99), (117, 114, 140), (171, 124, 107), (121, 86, 78), (27, 39, 86), (170, 96, 63), (206, 136, 104), (147, 105, 101), (59, 9, 13), (36, 58, 114), (13, 5, 18), (119, 42, 28), (69, 64, 96), (150, 88, 61), (13, 18, 50), (232, 167, 128), (188, 157, 157), (76, 83, 127), (48, 71, 129), (106, 90, 110), (148, 52, 24), (47, 50, 92), (227, 154, 98), (69, 26, 36), (214, 112, 53), (21, 30, 71), (254, 195, 95), (145, 138, 159), (90, 21, 22), (92, 43, 40)],
        "fb": [24, 17, 18, 243, 137, 95, 17, 130, 173, 95, 52, 24, 232, 88, 59, 95, 17, 180, 248, 60, 24, 59, 124, 53, 173, 52, 166, 17, 215, 103, 52, 52],
        "rows": [
            ('     hhhhhhlll', '.....bBqqqbacb', '.....gggluu...'),
            ('   lhfhhffhhhhhhll', '...BggBlaaalglcBxg', '....cgbcaacgcutx..'),
            ('  hhhhfhhffhhhhhhhh', '..bacBBgalgguoxoDeF', '..llgqBBclglogdssre'),
            (' hhffhhhhfhhhhhhhhh', '.qaggBqglautFhjejef', '..lggqBcaatzzfiyfjp'),
            ('  hhfhhhhfhhhhhhhfh   lhh', '..lggqBcauowhkFyzjF...mEk', '..ccgBggcutfjvyedj.....km'),
            (' lhhhhhfhhhhhfhhhhl  lhf', '.BglBBBBuxohrrCrifk..wnn', '..lgqqbBoodjyrehFx....yn'),
            ('fhhhlhhfhhhhhhhhhfhl ffhh', 'blBbBqqBxdDDjesjyiFm.wCAm', 'bB.q.BBBbvvsssDeiie..wCyk'),
            (' h lfffhhffffhhhhhhhlhhhh', '.q.bBBBcgodDDDsyriizkEAnk', '....BBBqcodDDdDrirCe..pCn'),
            ('   lhhhhhfhhhhffhhhhhhhh', '...qqBBBbbovvdDDpnhAyhCA', '....cllcgbboovDDEkkkznwz'),
            ('  lfhhhfhhhlhhhhhhhhfhh', '..cccaaalgbbBvdjzpnkkkn', '...cgclacxg..BoopiiEkEE'),
            (' hfhffhhfhhhhhhhhfhhhhh', '.qaacgBqxogooxugphiEEhi', '.gaccggxxBatguacwhwknpe'),
            (' hhfffhfhhhhhfffhhhfhhh', '.BggggggBlulBaacFFzkEpF', '..qggglglclcgaacbmkkzB.'),
            ('   hhhhhfffhhhhhf fhlf', '...mBgalcggcccacb.BbbB', '.....qcacgggBglgb.Bq.B'),
            ('      hhhhffffhhf  hfh', '......qcacggBgcBb..Bqq', '........qBggBglgb...q.'),
            ('           hhhhhf', '...........qqBlcq', '..............mqq'),
        ]},
    'halfling_cleric': {"w": 22, "h": 15,
        "pal": [(215, 82, 19), (254, 158, 0), (255, 219, 183), (251, 245, 251), (181, 110, 113), (66, 58, 68), (184, 168, 195), (219, 132, 95), (152, 123, 151), (234, 140, 15), (121, 21, 18), (209, 139, 124), (132, 18, 40), (200, 106, 91), (254, 211, 175), (200, 64, 19), (237, 148, 119), (236, 227, 238), (244, 174, 149), (148, 25, 33), (208, 96, 47), (227, 207, 212), (173, 38, 25), (128, 107, 141), (39, 17, 22), (174, 148, 167), (178, 53, 31), (118, 64, 71), (206, 183, 198), (255, 209, 13), (73, 9, 4), (87, 11, 29)],
        "fb": [166, 214, 223, 231, 131, 237, 146, 173, 103, 172, 88, 174, 88, 167, 223, 160, 209, 254, 216, 88, 166, 188, 124, 96, 234, 139, 124, 95, 181, 220, 52, 52],
        "rows": [
            ('      lhhhhhhhhl', '......wFwwttwtyk', '.......apaapaaA.'),
            ('    lhhhffffhfhfhl', '....Ekapaaaaaappkk', '.....ApaaaaapaapA.'),
            ('   lhhffhhhhhhhhffl', '...EwAppaaaaAApapAE', '....AwppppppnwAppA.'),
            ('  lhfffhfhhhfhhhhfhl', '..kkwwwAwAppsAnAAwkk', '...wwwwpwwAqsqouwww.'),
            ('lhhfhhhffhhffhhhhhfhhl', 'yEwwwtqlAAscslqqtwwwEy', '.ktwnAolAsccselownwtk.'),
            ('lhffhhhhhhffhhhhfhffhl', 'yEttqnqxFecclFBlhqttFy', '.wttnhoolcccclochnttw.'),
            (' hhhfhhfffhhfffhhfhhh', '.mtttlocccoccccoqtttm', '.FmmtmlcccsscccsmtmmF'),
            (' hhffhhhhhhhhfhhhhfhh', '.kmttmtocsqqscoAmttmk', '.yktttmeocssccemtmtky'),
            ('  hhhhhffhhhhhfhhhhh', '..yFmixieoccolixxtFy', '....iziieqqqqeiizz..'),
            ('   hhfhhhhhhhhhhfhh', '...fgdzieqhhqniidgf', '...zvddzsosscozrdvg'),
            ('llhhhhfhhhhhhhhhhhhhll', 'yzfgdrrdvoccovddrdgfgy', '..dvgvrrdrqlrdrrvgCd..'),
            ('hhhfhhhfhhhhhhhhhhfhhh', 'xvddrggCvChjCvCggvddvx', '.zrdddrCejbbjegrdddrg.'),
            (' hhhhffhhffffhhhffhhh', '.fCrddddubDDbjrdddrCf', '..fCrddlbbDDbbhrddCx.'),
            ('   hhhhhhhhhhhhhhhh', '...fgvddubDDburdvCx', '....yzCCzjbbjlCCgf.'),
            ('      hhhhhhhhhh', '......figzehzCzf', '.........ffff...'),
        ]},
    'fighter': {"w": 22, "h": 15,
        "pal": [(217, 240, 242), (94, 61, 63), (177, 195, 199), (96, 67, 73), (85, 93, 109), (79, 53, 59), (250, 186, 127), (183, 117, 90), (108, 126, 140), (167, 192, 203), (59, 31, 48), (79, 59, 69), (65, 47, 60), (35, 28, 46), (150, 165, 178), (198, 222, 228), (60, 38, 56), (113, 66, 57), (81, 39, 53), (116, 74, 73), (60, 31, 32), (19, 14, 31), (148, 159, 166), (57, 36, 52), (125, 89, 83), (218, 147, 101), (160, 106, 84), (144, 97, 77), (34, 19, 34), (41, 36, 52), (176, 186, 187), (255, 201, 134)],
        "fb": [255, 59, 250, 239, 59, 237, 216, 137, 66, 250, 52, 238, 237, 234, 247, 253, 236, 59, 52, 59, 52, 233, 247, 236, 95, 173, 131, 95, 234, 235, 250, 222],
        "rows": [
            ('                    lh', '....................ci', '.....................w'),
            ('                   hhh', '...................dpe', '...................Ej.'),
            ('       lhhhhhl    hhh', '.......susqnCn....mae', '........bxDDn.....Ejv'),
            ('     lhfhffhhhl  hhh', '.....uCDssqqnxC..mae', '......rDmsqmqq...Ejn'),
            ('     fhhhhhhhfh hhh', '.....uqkDqfhhnC.mai', '.....unnxtAAAnn.ojn'),
            ('      hhhhhhhhhhhh', '......DfBAhBAmvDai', '......vbFgzFgD.wcD'),
            ('       hhffhhhhhh', '.......vgghFhvnai', '.......CAghzf.wcm'),
            ('   lhhlhhhhfhhhhl', '...tuCurbAhtsdaiv', '....td.tBBytboce.'),
            (' lhhhfhhfhhhhhhhhh', '.frAybbbblmnlawmqC', '..BtAbkmbfkqoceqfm'),
            (' hhfhfhhhhhhhhhfhhh', '.Aydfssqmmklawssbmn', '.tBdmsbfAtsocefsqlm'),
            ('hhfhhfhfhhhhhhhfhhh', 'CBdmnkskBAypwqmkmlD', 'ftdDvkkkDyzhdkskxfq'),
            ('lhhhhhhhhhhhhhffhhh', 'uxDvvCDknmrtrDnCCfx', '.dlxCvnDflmxfBnCvv.'),
            ('hfhhhhhfhhhffhfhhhhl', 'AdnfmqdxbfqDDqCxqxqC', 'bdfttdlxfqxDDDCCvCf.'),
            ('hhhhhhhhhhhhhh  fhh', 'dmxfmqnDnCCkCv..vmn', '..vDnnC.q...v...vq.'),
            ('  hhh  hf', '..vnC..Bu', '.......ru'),
        ]},
    'rogue': {"w": 28, "h": 14,
        "pal": [(133, 112, 109), (209, 138, 99), (81, 48, 31), (73, 62, 64), (121, 128, 157), (107, 100, 109), (35, 42, 64), (63, 43, 40), (46, 44, 56), (62, 36, 26), (14, 20, 41), (31, 18, 14), (123, 81, 65), (31, 21, 27), (55, 51, 64), (8, 11, 28), (32, 36, 54), (125, 120, 133), (97, 67, 60), (60, 58, 71), (71, 45, 30), (156, 105, 74), (66, 72, 93), (109, 69, 35), (21, 28, 50), (47, 26, 21), (51, 35, 35), (28, 26, 40), (157, 133, 130), (167, 162, 179), (57, 49, 56), (74, 57, 57)],
        "fb": [243, 173, 52, 238, 103, 241, 236, 236, 236, 236, 233, 233, 95, 234, 237, 232, 235, 243, 239, 237, 52, 131, 238, 58, 234, 234, 235, 234, 138, 248, 236, 237],
        "rows": [
            ('           lhhhhl', '...........qpkypq', '............gyqg.'),
            (' lhh      hffffffh      lhl', '.qdl......hggyqggh......osE', '..ft......dggyqggd.......f.'),
            (' hhhh    hhhhhfhhhh    lhhh', '.dtDl....zogykyygiz....CDtd', '...wC....ugkkyykyqc.....wp.'),
            ('   hhhl  ffhh  hhfh  lhhh', '...yeaA..Fqyy..ykqd..zfeq', '....gD...Fq......qF...Do.'),
            ('     hhlhhhllhhllhhhlhh', '.....wDrzoysmppmsyoAaDw', '.....ke.Fqk..BA..pqd.ey'),
            ('      hhhf fhhhhf hhhh', '......gCsy.Avssvh.qdeg', '.......siy.Abvvbh.yqs.'),
            ('      hhfh hhhhhh hfhh', '......zdyp.nmbbvn.pydz', '......jiy..tnhhnE..yih'),
            ('    lhhhflflhfhhlhlfhhhl', '....znuqypkihqAEgkpyqjnz', '.....Aigy.k.pqBp.B.yBcA.'),
            ('  hhhfhfhfhhhhhhhhhhhhhhhh', '..jvdgykkykqtqqtipykjzqtmu', '..shggqkpynikyyyAzBzzqgghs'),
            ('hhhhhhhhlhhfhhhhhffhhhhhhhhh', 'mvtBEggykplzsmssizackggEqovm', 'uxcgAAqp.kjzpppkBzaopqqAgcxc'),
            (' hhhhh hffhhhhhhhhhfh hhhhh', '.jhcgB.yyyBjzpkkzjByq.Bgchj', '..zjhE.kyyyp.zjz.Bqyk.ohjz.'),
            ('   hhhflhhfhhhhhhfhhlfhhh', '...ljhhlyqkkBjxckkyklhhjl', '.....zh..pkizzAAykp..hA..'),
            ('      hh hhhfhhhhhf hh', '......lj.ppAnkyyiBn.Al', '...........nnAhccjn...'),
            ('            hhhhhh', '............zjuuxu', '.............llz..'),
        ]},
    'wizard': {"w": 28, "h": 15,
        "pal": [(41, 61, 130), (132, 57, 20), (35, 50, 115), (255, 245, 202), (28, 9, 49), (255, 203, 77), (39, 15, 61), (22, 5, 39), (191, 148, 139), (135, 74, 64), (59, 87, 158), (17, 5, 19), (254, 153, 52), (78, 27, 16), (62, 45, 68), (52, 15, 15), (22, 21, 68), (56, 22, 76), (230, 126, 70), (97, 75, 96), (44, 47, 97), (84, 59, 118), (233, 222, 192), (167, 106, 83), (147, 118, 150), (175, 78, 41), (151, 121, 113), (95, 123, 189), (39, 12, 23), (91, 50, 50), (203, 177, 147), (239, 223, 146)],
        "fb": [24, 88, 18, 230, 17, 221, 17, 17, 138, 95, 25, 232, 208, 52, 53, 52, 17, 53, 173, 240, 18, 60, 187, 131, 103, 130, 244, 68, 52, 52, 180, 222],
        "rows": [
            ('     llhhhl           l fh', '.....halulu...........p.CC', '.......kkB..............C.'),
            ('   lfhhhfhhhh         hhhh', '...qqccaakBkl.........ClCn', '....qqqqaakBB..........pzb'),
            ('  hhhhhfhhhhhfl     llhhhhll', '..elllqqcaaaBBB.....lpCbsDpp', '......lqqqckkB........Dsmz..'),
            ('       ffffhhhfhl  lfhhhfhhh', '.......qqcakBBByo..lpnzffznC', '.......qqcaaakBi....pbmFfsbp'),
            ('       ffhhhhhhhhhlhhfhffhhf', '.......qqquuuttAylBCnbmddmbp', '.......qqgooovkBBB.ytbfddfzp'),
            ('      lhhhhhfhhhhhfhhffffhfh', '......hgggquaaBBvugovyiEdfsC', '.......qquccavjzxrgrtyiEdFs.'),
            (' lllhhfhhhhhhhffhhffhhhhhhh', '.qucquuquccqCnjsjovvtjsdFfb', '....ccuuqhgnxxjsivvvClzmmz.'),
            ('hhhhfhlhhhhhhhhhhh    hhhh', 'eeeehlhlpngDsmzssh....jjjb', '...hhh.ggpoojxjxi.....pnbC'),
            ('     lfhfhffhhhfhh     fh', '.....gooohttDEEiwD.....nD', '......otogttAAAiEi.....nz'),
            ('    lfhhhhffhhfffhl    hh', '....eheoeDtttAwddEp....pb', '.....hhehottAiwddi.....Cp'),
            ('  lhhhhhhhhhhhhhhfl    fh', '..eehehrrhroAiEddwr....ll', '...heggegregjAAwww.....lC'),
            (' hfhhhhffffhhhhfhhhf   hh', '.hhegrrrrrrettAiEEgg...Cp', '.ehhhegrrrrgeDtiAorg...pn'),
            ('fhfhhffhhhfhhhhhhhhhh  ff', 'hheeeeegrrrghloAAggrl..pn', 'heehheeeggrrreltoerg...pn'),
            ('        hhhfffhhhhh    ff', '........hggggelgere....pn', '..........hggehege.....pn'),
            ('            hhfhh       h', '............hgerg.......C', '..............eg.........'),
        ]},
    'cleric': {"w": 22, "h": 15,
        "pal": [(249, 167, 114), (151, 127, 135), (237, 171, 141), (168, 146, 148), (127, 106, 114), (125, 62, 66), (233, 215, 206), (203, 164, 151), (226, 198, 186), (156, 107, 110), (85, 36, 40), (251, 240, 224), (253, 200, 111), (179, 128, 130), (109, 46, 35), (84, 57, 64), (220, 125, 45), (157, 76, 52), (196, 172, 169), (234, 149, 48), (213, 128, 106), (189, 149, 145), (240, 218, 190), (211, 102, 46), (110, 89, 86), (219, 186, 176), (228, 150, 101), (42, 23, 19), (248, 207, 138), (251, 190, 51), (185, 106, 43), (168, 103, 78)],
        "fb": [216, 102, 216, 138, 242, 95, 253, 181, 252, 131, 52, 255, 222, 138, 88, 238, 172, 95, 249, 208, 173, 138, 223, 166, 59, 181, 173, 234, 222, 214, 130, 131],
        "rows": [
            ('   f      llll', '...o......ywdB', '...o..........'),
            (' fhhf   lhhfhhhl', '.BBBB...bdlfizpB', '.BqoB....lbffsz.'),
            ('lhhhl  lfhhhhhhh', 'oxDro..ylvrrffve', '.DlD....lrAauoyv'),
            ('hhfff  hhhhhhhhhh', 'EClCr..eiFraArfvB', 'omlCr..zgAmCaardp'),
            (' hhhf hfhhhhhhhhhl', '.FtxB.BlduCmaarebB', '.ofkB.eljraxuAopd.'),
            (' hhh lfhhhhhhhhfhh', '.kkk.kwwfkuaaFkkbe', '..oB..wAndcAAcfked'),
            ('  f lhhhhhhhhhfhhhl', '..k.Boilizlwgifpdjo', '..k..txcliwizcfjjr.'),
            ('  fhfffhhhhhhhhhfhfhl', '..kBtDDxuizccvffrqxoB', '..kntDDtizvAunbortxE.'),
            (' lhhhhhhhhhhfhhhhhhhh', '.kkzatqDiCFDqFayrxxjp', '..rccitCctDtqtEstEsve'),
            ('lfffhhfhhhfhhhhhhffhhl', 'BaauilllcqtmDqEzgigibB', '.aaugglwDttDtxqAwigsd.'),
            ('hhhfhfhhhhfffhhfhhfffh', 'BaAulgglhEqqxxrsgizdvp', '.nfuggzgctqqxExsizzdve'),
            (' hhhhhhhhhhhhhhhfhhfhh', '.pfdzzsihisuusivsvzbbp', '..kevddznzizslvnsbsbe.'),
            ('  fhhhfhfffffhffhfhh', '..kBebbznszsiinnsbvp', '..k..ybdnszsisnndbe.'),
            ('  hh  hhhhhhfffhhh', '..oB..yjjhzzsvnnby', '..B....erbsssvnjy.'),
            ('        hhhhhhhh', '........kjbdddbp', '..........pyyp..'),
        ]},
    'brannoc': {"w": 26, "h": 15,
        "pal": [(132, 155, 167), (156, 175, 182), (221, 138, 107), (158, 66, 78), (67, 77, 89), (142, 167, 179), (83, 99, 112), (105, 44, 56), (100, 119, 131), (58, 51, 63), (49, 69, 87), (59, 65, 77), (65, 81, 98), (172, 143, 131), (170, 94, 76), (130, 52, 65), (67, 91, 109), (90, 34, 49), (54, 17, 32), (98, 110, 118), (179, 201, 211), (137, 145, 143), (246, 160, 124), (200, 108, 88), (112, 135, 149), (31, 16, 21), (63, 30, 41), (28, 32, 42), (39, 50, 64), (95, 75, 72), (134, 63, 57), (135, 87, 76)],
        "fb": [246, 248, 173, 131, 239, 109, 241, 88, 243, 237, 238, 238, 239, 138, 131, 88, 240, 52, 52, 242, 251, 245, 216, 167, 66, 233, 52, 234, 236, 239, 95, 95],
        "rows": [
            ('            lhhhhhll', '............ABjgiDvz', '.............rrACi..'),
            ('     lhll hfffffhhhhhh', '.....BAbC.zhpdddACevgB', '......i...hhpdddpACgat'),
            ('lllllhhhhhhhhhhhhhhhhhh', 'eCBCgCtytsrhpddphCkgyvB', '.....BkmeAsrhhmhrBCmqlD'),
            ('fhhhffhhhhhfhhhfhhhhhhhh', 'uaqqkCBBDAAjrBmhrzBmergB', 'ubmmkC.zAsljsArhArACjhh.'),
            ('hfhhffhhhhhhhhhhhhhhhhlh', 'iumkkBxDszsAAszhoEArApes', '.uaCkBEccFz.zEeyFccocn.E'),
            (' hhhhflhhhhhhhhhhhhhhhhh', '.muimkCEExFmhorsgjrojlAE', '..ibik.AxhhkxwxFnExwDFrz'),
            ('   hhhhhhhhhhhhfhffhhhhl', '...tbbgzxEhgowwxxoxcowrB', '....BiejjoDtExoxEoxwxEl.'),
            ('     hhhh hfhhhhfhhhhhhh', '.....zCCl.gyedtyamApevDj', '.....Fll..qytibfatjBybfe'),
            ('    lhhlf hhhhhhhhhhhhhhh', '....zCBsz.Cemaaatjooribez', '.....As.z.BlqiigBBlClBmgq'),
            ('   hfffhhfhhhhhhhhhhhhhhhl', '...phhhAzsBeeqmBCiititBBAh', '...rhhhhssz.zBBeqfaabfttr.'),
            ('    hhhhffh ffhfhfhffhfhfh', '....ArhhrAA.Bmgtabffbbatjs', '.....srrrAz.Bmqtfbbfbfagj.'),
            ('      hfhhfh hhhhhhhhhhhh', '......ssAAsz.lltyffyaaqqB', '.......sssss.BCgmiytiiCe.'),
            ('        hhhhflhhhhhhhhfh', '........zsszzzBemlqqqtCC', '..........zsz..CkCkelmC.'),
            ('                hhhhhhh', '................BBjCleB', '..................BjkB.'),
            ('                   hh', '...................Ce', '....................B'),
        ]},
    'tamsin': {"w": 23, "h": 15,
        "pal": [(41, 73, 70), (42, 73, 72), (40, 68, 67), (39, 52, 57), (37, 65, 65), (239, 172, 145), (33, 53, 56), (139, 82, 69), (174, 47, 17), (20, 23, 37), (105, 23, 21), (150, 150, 159), (90, 22, 23), (125, 27, 22), (130, 104, 106), (28, 42, 50), (255, 206, 174), (157, 40, 20), (52, 71, 67), (121, 48, 43), (72, 22, 27), (68, 47, 51), (179, 170, 177), (74, 81, 89), (163, 89, 76), (131, 36, 19), (240, 187, 163), (195, 105, 82), (20, 11, 22), (47, 11, 15), (202, 136, 115), (226, 149, 122)],
        "fb": [238, 238, 237, 236, 237, 216, 236, 95, 124, 234, 52, 246, 52, 88, 95, 235, 223, 124, 238, 88, 52, 237, 145, 239, 131, 88, 216, 167, 233, 52, 173, 173],
        "rows": [
            ('       llhhhhhhl', '.......CzDknmkCm', '.........iriiii.'),
            ('      hhhhhhhhffhl', '......CziiiziiiikC', '......zirkrrrriii.'),
            ('     hhhhhhhhhhffhl', '.....niimutktmrrinD', '.....rrrtFqfqFtrii.'),
            ('    lhfhhhfffhhfhhh', '....hzirEqqqqqBkziC', '.....BinyAqqqFhknyE'),
            ('    hhhhhhhhhhhhhhh', '....DErtxmyqhtvtyEt', '....nikyEyEAFEoEtBz'),
            ('   hhhhhffhhhffhhhhhl', '...DrznBqqqAqqqFyzikD', '...mirutqqAFAqqyuuru.'),
            ('  lhfhffhhfffhhhhhhhh', '..prirkDAAffffquukrzD', '...yiikDhqfffqhDDuziz'),
            ('  hhhhhhhhhhhhfhfhhhhhl', '..DlyiuuChAqAyCjjjjmzzD', '...ywzjjjvBByhCCjpcekk.'),
            (' lffhhfhfhfhhhhhhhhhhl', '.kziwxjjCvEBBhpgabbvkD', '..ziowjCCuEoxbaabejur.'),
            (' hhhhhhhhhhffhhhfhhhhf', '.CrnvwoepebaaabegjgpuD', '.kmDpowjjpeaaeggggpjDD'),
            (' hhhfhhhfhhhhhhhhhhhhl', '.DCpgdwxpgpggbgjjjpppC', '..jggjolpablwdjgeaaae.'),
            (' hhhhfhhhhhhhhhhhfhhhhh', '.jjpaaduvlAlxjeaeaaejjC', '...CgasyBosjjgpgaapC...'),
            ('    hhhhfhhfhhhhhh', '....Ctzkkjjppgaaej', '.....DuDkuppeaej..'),
            ('        hfhhhh', '........ukdaap', '.........kudj.'),
            ('         hfh', '.........DDD', '..........D.'),
        ]},
    'maren': {"w": 24, "h": 15,
        "pal": [(35, 30, 56), (254, 246, 224), (173, 107, 61), (128, 74, 77), (169, 101, 50), (228, 135, 58), (86, 43, 40), (101, 55, 44), (129, 70, 45), (149, 82, 49), (176, 112, 90), (54, 33, 33), (240, 166, 69), (98, 61, 59), (55, 45, 59), (133, 105, 90), (231, 174, 109), (217, 176, 149), (33, 20, 34), (248, 216, 190), (199, 107, 52), (138, 81, 57), (99, 80, 88), (177, 160, 150), (197, 172, 162), (201, 142, 95), (203, 113, 66), (250, 234, 207), (216, 200, 188), (240, 198, 159), (171, 135, 110), (187, 131, 98)],
        "fb": [17, 230, 130, 95, 130, 172, 52, 88, 95, 95, 131, 235, 215, 59, 236, 95, 179, 180, 234, 223, 166, 95, 240, 248, 249, 173, 166, 255, 252, 223, 137, 137],
        "rows": [
            ('        llhhhhll', '........lCwxywtn', '..........bbbb..'),
            ('       hhffhhffhh', '.......otbbbbbbBw', '.......yBbbttbbbC'),
            ('      hhfhhhhhhfhh', '......oCbbqjvqBbtw', '......pBbqiuevfbbE'),
            ('     lhhhhhhhhhhhfl', '.....syBqvfAFfjqbCo', '......CteuurtkujtC.'),
            ('     hfhhhhhfhhfhhh', '.....wtqndkttFddzBw', '.....ptedwnDtwwdjtp'),
            ('    lhhhhhhffhhhfhhl', '....sEDvkyCttCyxiDxo', '.....yqixBBttBBrizC.'),
            ('    hhhhhhfhhhhhhhfh', '....wCcekBBttBBEeeyp', '....xrjAgrBDDtDgAjyy'),
            ('   lhhhhhhhhhhhhfhhhh', '...ntrifhnDtttdgAirBs', '....bqhuigkrrknhAgqbp'),
            ('  lhhhhhhfhhhhhhhhhhhl', '..oxbzhijanddnaijhFbCw', '...tBFggvaaaaasvggcBt.'),
            ('  hhhhhhhffffffhhhhfhh', '..ECCzissaaaaaasshzCCr', '..jqtyzgaaaaaaaagzyCDe'),
            (' lhhhhhhhhhhhhhhhhhhhhl', '.whizCyziaaooaahzyCqjhp', '..xcvcrtrFnhvhcrCDFicx.'),
            ('hhfhhhhhhhhhhhhhhhhhhfhh', 'lBbyencFrxAfAAxrzeijxbBg', 'hqbbCFionAecceAionFybbqh'),
            (' hhhhhhhhfhffhhhhhhhhhh', '.lzBbCEehfemmefhvECBBzl', '...vDBCyFfjmmjAFyCBDe..'),
            ('    hhhhhhhhhhhhhhhh', '....gmBtFueceeucCBqh', '.....seDhlufAullqcl.'),
            ('       h   hh   h', '.......g...iv...g', '...........sl....'),
        ]},
    'lysa': {"w": 23, "h": 15,
        "pal": [(23, 17, 40), (238, 129, 91), (16, 14, 39), (32, 25, 47), (108, 63, 37), (23, 19, 44), (205, 90, 82), (136, 64, 63), (102, 46, 37), (85, 49, 47), (215, 109, 83), (77, 27, 26), (47, 13, 11), (76, 34, 34), (85, 53, 61), (173, 78, 56), (176, 83, 72), (88, 33, 33), (140, 77, 36), (89, 30, 23), (113, 64, 55), (72, 17, 20), (130, 44, 29), (50, 19, 26), (236, 138, 106), (117, 69, 69), (70, 39, 52), (46, 31, 51), (29, 13, 15), (141, 79, 65), (253, 148, 99), (254, 165, 116)],
        "fb": [17, 209, 17, 234, 88, 17, 167, 95, 52, 52, 167, 52, 52, 52, 52, 131, 131, 52, 94, 52, 59, 52, 88, 52, 209, 95, 52, 235, 233, 95, 209, 216],
        "rows": [
            ('       lllhhhhhhl', '.......mmunjrmCCn', '..........AABdAj.'),
            ('     lhhhhfhhhffhhhll', '.....iiooddddfffajljC', '......uBaadfadffBAA..'),
            ('    hhhhhhhhfhhfhfhhhl', '....jAdfaBBddBfcdBBdju', '....iBccddfBdfacfBdfB.'),
            ('   hhfhhhfhhhhhhhhhfhhh', '...CuddaacadaaqhcdBcdAC', '...DAdfcfcfffAkAafdcBj.'),
            ('  lhhhfhfhhhhhfhhhhhfhl', '..vjBacdfffcajEzfcfacAn', '...udccffABaqkEyudafcB.'),
            ('  hfhfhfhhhhhhffhhfffhh', '..jdkgodfhAiAqEzizccccj', '..udzgBdcDzuDbEzDAcccan'),
            (' hhhhhhhhhfhfhhhhhffhhh', '.iiBapBcAkbbFEEyypcccjm', '.eAfcdhAchbEFFFbEqccav.'),
            ('hhfhhhhhhhfhhhhhhhhfhhl', 'vzdacadsBDbEFFkbEDdfdnm', 'CodddfepedbygyygkejfcA.'),
            ('lhhhffhhhhhhhhhhhhhhfhh', 'mDAcdanseaqEFggbAndccBC', '.odadacdaciqbFFzccfacfl'),
            ('hhhhhhhfhhhhhhhhfhhhhhh', 'eBffffadfBhqppocccfacdn', 'nddaBaddaaqgqhcfcadffij'),
            (' hhhhhhhfhhhhhhffhhfhh', '.juiddBfcaikghcccfacaA', '..swnfaccxtikglcccccdD'),
            (' hhhfhhhhhhhhhhhhhhhh', '.shwraxacxvirgpxxcAsn', '.pwirllvxttstlDvvxi..'),
            ('hhhffhfhhfhhhhhhffhf', 'mpwrrrllielsltxllvrC', 'swirrllvvesitlvvlvmC'),
            ('hhhhffffhfffhhhhhhh', 'xrrrrllvxvllvtvttrm', '..xlrllvmvlllvlxlt.'),
            ('     hhhhhhhhhhhhh', '.....CCmmvlllvltmC', '..........Cmxxvv..'),
        ]},
    'hobb': {"w": 28, "h": 12,
        "pal": [(174, 183, 183), (253, 164, 125), (117, 116, 127), (247, 158, 122), (90, 53, 49), (153, 81, 72), (251, 226, 175), (65, 38, 45), (168, 176, 177), (51, 28, 34), (153, 159, 162), (101, 97, 107), (197, 107, 91), (93, 54, 49), (40, 24, 34), (127, 93, 90), (80, 43, 46), (203, 132, 108), (228, 139, 111), (164, 102, 89), (140, 141, 148), (47, 38, 49), (133, 72, 66), (62, 34, 38), (79, 76, 87), (82, 51, 50), (106, 64, 61), (23, 16, 28), (65, 57, 66), (135, 131, 128), (180, 178, 165), (220, 172, 134)],
        "fb": [249, 216, 243, 216, 52, 95, 223, 236, 145, 235, 247, 241, 167, 52, 234, 95, 52, 173, 173, 131, 245, 235, 95, 236, 239, 52, 59, 233, 237, 102, 249, 180],
        "rows": [
            ('           lhhhhl', '...........jCFrAq', '............bbbs.'),
            ('           hhhhhhl', '...........pbbssqj', '...........nAsqff.'),
            ('    llll  fffhfhfh', '....BDky..jrrsrsmz', '..........jrrmrdmj'),
            ('  lhhhffh hhhhhhhhlll', '..fAsgggx.jjojoqAyvoC', '...drFggz.Bwssfnwl...'),
            (' lfhhhhhhhhhhhhhhhhhhhhl', '.xmdrzntDkhtddmfpyolkuBv', '..msswqAkDyltmfpkzzkiai.'),
            (' hhhhhfhhhffhhhhffhhfffhh', '.qrmmAqAuplcjxviDnyiiaakB', '.fffAzqeDAlcylDDDnlkiaaaD'),
            ('lhhhhhhhhhhhhhhhhhhhhhhhhhl', 'vdAoxqqelAkkukaDcADDaaaaiyC', '.bmwqAAnyjheeeezxxcluikkuu.'),
            ('hhhhhhfhfhhhhhhhhhhhhhfhhhhh', 'lrmwqvCChzzqxxhqqxlllccuuuco', 'yDtqhCCoheneeeeeehzCCyckaaky'),
            (' hhhhhhhfffffffffhhhfhhhhhhf', '.CllCvBBqeeeneeeehhCCvyDDkuv', '...BB..oqeeeneeeexozCofdrwlv'),
            ('      lhhhhhhhhhhhffhhhhhh', '......BoxzeneeeehjBBhqwsmw', '.......BjjxhqqhhjoBBBstewB'),
            ('      fffhhhffhhfffffhhfh', '......BBBjjjjjjoBBBBBrmqB', '......BBBBoojjoBBBBBBmtq.'),
            ('        hhfhhhhhhfhhhhhh', '........BBBBBBBBBBooooho', '..........BooooooB......'),
        ]},
    'pell': {"w": 25, "h": 15,
        "pal": [(200, 126, 103), (167, 125, 104), (58, 20, 31), (198, 154, 129), (89, 38, 35), (180, 100, 83), (174, 97, 53), (220, 128, 102), (78, 46, 51), (163, 80, 53), (145, 85, 73), (146, 78, 53), (88, 53, 52), (165, 92, 77), (119, 75, 61), (167, 143, 132), (234, 195, 159), (60, 38, 31), (44, 46, 52), (144, 66, 44), (195, 116, 85), (251, 167, 132), (231, 148, 117), (125, 107, 65), (76, 33, 39), (114, 56, 41), (115, 61, 54), (77, 91, 106), (35, 15, 15), (156, 125, 77), (55, 79, 72), (78, 82, 69)],
        "fb": [173, 137, 52, 173, 52, 131, 130, 173, 52, 131, 95, 95, 52, 131, 95, 138, 187, 236, 236, 95, 137, 216, 173, 94, 52, 88, 88, 240, 233, 101, 239, 239],
        "rows": [
            ('  lhhhhl', '..dbddFo', '...qqqq.'),
            ('lhhhhhffhll', 'mbqqqqqqrEs', '.qddbvqqF..'),
            ('hffh hhffhhhhhhl', 'rddb.mdBBdpBrmrC', 'oddi..BBBpbfjjf.'),
            ('fhh  hhfhhhhfhh      ll', 'mab..CBBBneyyyy......Cr', 'mkr..sEBAymeyAc........'),
            ('     fhhhhhhhf     hlhffl', '.....CBoyykkkA.....CCzjle', '.....CfyckfAvA.....e.ljl.'),
            ('      hhhhffhh    hfhhhhh', '......fnmhvvvh....CCeCetc', '......yfhwvvwa.....CjtzC.'),
            ('     lhhhhhhhh    lhhhlh', '.....Cccjhvbdh....ionzre', '......yyyfwvvb.....km..c'),
            ('     lhhhhhhhh  lhhh', '.....Cluzhjnuy..CroA', '......tguauyex...uaC'),
            ('   lhhhhhhhfhhhlhhhh', '...FEEEotghhlFCkkuuo', '....DxFEEzghgEm.nhhu'),
            ('  lhhfhhfhhfhhhhhhhh', '..mxxDxEFFAgjjguknwu', '...DDDDFFilggkufzjhk'),
            ('  hhhhhhhhhhhhhhfhhh', '..DDxxxieljgjnnoltlA', '..rxloFetttnfaAjliAm'),
            ('  hhhhhhhhhfhhfffhhh', '..CljoezAtwvvftgtyyc', '...hukAAkgvvwutgttr.'),
            ('  hhhhhfhhhhhhfhhh', '..CauakyAlfafjtjto', '...nffoyczAmttttC.'),
            ('   hhhhhhhhhffhh', '...cyeemiiyyttte', '......cyycAtttA.'),
            ('       hhhhhhhh', '.......CceAttzC', '.........CccC..'),
        ]},
    'aldous': {"w": 27, "h": 15,
        "pal": [(255, 227, 176), (255, 227, 176), (255, 227, 175), (147, 110, 106), (124, 91, 92), (254, 224, 172), (213, 136, 91), (254, 178, 119), (219, 183, 140), (172, 89, 65), (238, 151, 96), (250, 169, 109), (184, 119, 92), (172, 138, 118), (196, 102, 57), (114, 78, 62), (249, 187, 128), (241, 207, 158), (207, 164, 138), (232, 195, 150), (133, 103, 94), (219, 184, 151), (254, 229, 188), (88, 63, 54), (240, 135, 50), (192, 151, 123), (155, 94, 74), (193, 157, 140), (47, 34, 27), (153, 118, 108), (246, 211, 166), (251, 219, 168)],
        "fb": [223, 223, 223, 95, 95, 223, 173, 216, 180, 131, 209, 215, 137, 137, 166, 59, 216, 223, 180, 187, 95, 180, 223, 238, 208, 173, 95, 144, 235, 102, 223, 223],
        "rows": [
            ('          lhhhhhl', '..........ACAgACx', '...........hqqqg.'),
            ('         hfffffffh', '.........xqqqqqhjC', '.........gqqqqqhjp'),
            ('         fffhhhhhf', '.........khhlllkjA', '.........khhhhhhmA'),
            ('        fhhhhhhhhff', '........AlsBBkBnDjx', '........Akgooljoojx'),
            ('        hhffhhhhhh', '........CkkhhlghgA', '.........pkhsgmljx'),
            ('        lhhfhhhhhhl', '........DxlvvzsvjCx', '.........sBvttnsde.'),
            ('      lhffhhhhhhfffhl', '......DzittBwwBnddeex', '.......titFqzBdAddeu.'),
            ('   lhhhhhfhhhfhhhhhfhhll', '...nCnirtrsFFiBBdDedupdx', '....FcEtirvzvinsDeuddd..'),
            (' lhfhffhfhhhhhhhhhhhhhhhhl', '.uzcccctttrtrFtnudddDdddpx', '..ccaccftiiisnuDzzeDnDnDd.'),
            ('lhhhhfhhhhfhhhhhhhhhhhhhhfl', 'DtcaccccfzsisiiineDvarzzDdx', '.rfEfcaacFssznnDDnFcEEDsnd.'),
            ('hhfhhfffffhhhhhhhhhhhhhhhfh', 'srEEEcccccrvFFFFvrffrrDinde', 'ptEftcccccctvErvtcFctvdtDdx'),
            (' hhhhffffffhhhhhfhhhhhfhfh', '.srficcacaFftoArfffFrsdvdu', '.CtFtccacaFFlygqfFcrFndsdC'),
            ('  hhhffffhhhffhhhhhfhhfhh', '..prtFcccffrylootFctFndDx', '...eiFcccEchylyjzaftrDdx.'),
            ('    hhhfhhhhhhhhhfhhhhh', '....xtccfFFqyojorcFtidC', '.....CscFcrctgniacrrDC.'),
            ('       hhhhhhhhhhhhh', '.......xsaEccEtaaazp', '.........CpniiizeC..'),
        ]},
    'greta': {"w": 20, "h": 15,
        "pal": [(36, 40, 61), (111, 58, 60), (104, 111, 135), (50, 25, 44), (87, 45, 55), (52, 54, 79), (62, 33, 50), (48, 17, 21), (130, 73, 63), (74, 64, 83), (227, 147, 101), (39, 22, 41), (130, 64, 49), (111, 51, 53), (112, 55, 55), (68, 42, 58), (202, 124, 86), (101, 82, 98), (132, 90, 86), (27, 13, 25), (77, 39, 51), (77, 86, 111), (168, 90, 64), (84, 34, 42), (64, 27, 41), (193, 109, 72), (242, 171, 124), (102, 39, 43), (200, 132, 99), (105, 52, 47), (144, 75, 62), (153, 92, 72)],
        "fb": [235, 88, 242, 52, 52, 237, 52, 52, 95, 238, 173, 234, 95, 88, 88, 52, 173, 240, 95, 233, 52, 240, 131, 52, 52, 166, 216, 52, 173, 88, 95, 95],
        "rows": [
            ('        lhhhhl', '........nhyxhh', '.........BxEB.'),
            ('       hhhhhhhl', '.......hnnyBmBt', '.......yBFCEBx.'),
            ('       hhhhhhhh', '.......yxiqwdyh', '.......xBCAACx.'),
            ('       hfhhhhff', '.......nxkAqCyh', '.......BxEqzEyh'),
            ('    lhhhhhhhhhhll', '....vtaBxwwwEllvf', '.....ccDBFACigp..'),
            ('  lhffhhhhhhhffhfhl', '..ajccvexassajecval', '...cccjBBvjfvjevvj.'),
            (' lhhhhhhhhhhhhhhhhh', '.Degjjgonesrsbmfvft', '..ACeaenxBonBnDuaDm'),
            ('lhhhhhhhhffhffhhhfhh', 'hCAkCdeoBoonoooeskCt', '.AkCzugDnoooooBgCkkh'),
            ('hhhhh hhhfhhhhhhhhfh', 'EAkFn.dgpgggggguzkkD', 'Dsmne.luugueuuutFzkm'),
            (' hhfhh hhhfffhhhhhfh', '.uoont.uueeuuegdnoee', '.lBooy.ggueuuguloned'),
            ('llhhhhhhhhhhhfhhhhh', 'iDyeomDedyoxgdggnBp', '..hdzAACguCwndumogl'),
            ('hhhhhhhhhhhhhfhfhh', 'exxhFkqzBFqmmuqkqt', '.....xbedEzEeuzkk.'),
            ('     hffhhhhhhhhh', '.....tgggeoDeemzs', '.....lggxDDguggg.'),
            ('     hhhhhhhhhhh', '.....tdmEwzDEDdl', '.......Boommeg..'),
            ('       hhhhhhh', '.......ygdddgd', '........l.lth.'),
        ]},
    'oswin': {"w": 28, "h": 15,
        "pal": [(92, 61, 60), (95, 64, 63), (50, 17, 38), (59, 26, 43), (84, 49, 54), (122, 106, 119), (159, 99, 62), (237, 166, 115), (191, 110, 84), (210, 137, 105), (58, 18, 37), (118, 92, 91), (59, 25, 41), (65, 30, 30), (42, 12, 34), (81, 53, 63), (147, 100, 94), (92, 47, 48), (68, 35, 46), (136, 125, 131), (107, 54, 48), (98, 69, 81), (253, 197, 135), (136, 71, 51), (154, 148, 151), (111, 74, 79), (34, 11, 19), (140, 73, 74), (74, 42, 51), (182, 170, 160), (177, 113, 70), (180, 107, 92)],
        "fb": [238, 239, 52, 52, 52, 242, 130, 180, 131, 173, 52, 95, 52, 52, 52, 237, 95, 52, 52, 244, 88, 239, 222, 95, 246, 59, 233, 95, 52, 145, 137, 131],
        "rows": [
            ('           llhhhhhl', '...........ClCcplAA', '.............fttyt.'),
            ('         lhhfhhhhhfl', '.........bblfyyDDytC', '..........zffftyttt.'),
            ('        hhhhhhhhhhhh', '........AzlBiiqffyDt', '........evzqhwwhwwwD'),
            ('        hhffhhffhfhhh', '........uvzBjwwwwwwDA', '........CzzBBjwwhwjy.'),
            ('        hhfhhhhhhhhhf', '........rrvxrmCBrpztn', '........uCvFjiujFihqn'),
            ('     lllhffhhhhhhhhfll', '.....ArrurvBhhFhhwhtgn', '........CrvugiuiihFt..'),
            ('    hhhfhhhfhfhhhhhhhhhll', '....nxcdocpzBytvfytlzgxgn', '....gmodkoszyyFFFfytabq..'),
            (' lhhhffffhhhhfhhhhhhhfhhhhh', '.AridocdCcmpzBBtqFlsebzzggA', '..xsoocdCposCBtDDqmkCbbbzBx'),
            ('fhhhffhhhhhfhhhhhhhhhhhhfhhh', 'AisooocdCadAkptDDlCcsaabbzqu', 'AgkcookkseeAcospuzeoCeeebbzx'),
            ('hhhhhhffhhhhhhhhfhhffhhhhhfh', 'rFockcddksbsAcsuxqCosssCbzbm', 'AncmddddseebmoCrxlcosddaabb.'),
            ('  hhhfhhhhhffhhhhhhhhfhhhhh', '..AmdmckksppacoCrukkssCabbe', '...okmkcddspaexsuEgAmsseaaA'),
            ('    hhhhhhhhhfhhhhhhfhhhhh', '....AccdksCspakrgEEgodeabs', '......ocmkseeaxuxxuEoCabp.'),
            ('        hhhhhhhhhhhhffhhh', '........kdcCCaCksEEroCebn', '.........oddeeacooxcoCaa.'),
            ('          hhhhfhhhhfhhhh', '..........AdeaasemhsoCCn', '...........AdeaCdkgsAod.'),
            ('             hhhhhh', '.............sesdok', '.............AA....'),
        ]},
    'captain': {"w": 21, "h": 15,
        "pal": [(138, 25, 41), (148, 30, 44), (158, 34, 43), (247, 171, 138), (149, 78, 50), (171, 132, 108), (206, 132, 109), (134, 74, 48), (190, 46, 48), (35, 33, 46), (67, 65, 86), (251, 196, 145), (142, 145, 162), (135, 128, 130), (59, 54, 62), (85, 34, 27), (197, 153, 115), (121, 62, 43), (148, 109, 77), (62, 37, 49), (197, 170, 139), (69, 21, 22), (176, 100, 72), (141, 45, 44), (84, 9, 25), (93, 58, 52), (100, 20, 35), (127, 110, 113), (89, 88, 106), (117, 22, 36), (32, 10, 12), (51, 10, 16)],
        "fb": [88, 88, 124, 216, 95, 137, 173, 95, 160, 235, 238, 216, 246, 244, 237, 52, 173, 88, 95, 236, 180, 52, 131, 88, 52, 59, 52, 243, 240, 88, 233, 52],
        "rows": [
            ('   h', '...o', '...B'),
            ('  hf', '..jm', '..Cm'),
            ('  hhf     l', '..nmj.....o', '..fuj......'),
            ('  hhh  lhffhll', '..luk..sonBoCE', '..ufo...qnBk..'),
            ('  hhh hffhhfffl', '..fBj.zlfnBkkCE', '..tn..flfBCkkC.'),
            ('  hh lfhhfhhfhh', '..rm.EqqqBCkkCj', '...z..qsBBBCkkk'),
            ('   h hhhhhhhhhh', '...r.tzhrewhrzt', '...h..rwwggwwp.'),
            ('   f lfhffhfhfl', '...h.Eeglddldpv', '...h..eeldglgp.'),
            ('   flffhhhhhhfhfhl', '...hzhezgdqdrpvvFv', '...h.heptfgzFpzvv.'),
            (' lhhhhhhhhhfhhhfhfhl', '.pFhwehttjjjjzzpvvEF', '..wrezpoCkojoppppvp.'),
            (' hhfhfhhhhhhhfhfhffh', '.vhhehzzufCktvzppvvp', '..xhrhptkztpAvppvvvv'),
            (' hffhhhhhhhhhhhhhhfhh', '.AirzhryADDwhyrvvyyvF', '.iirApyaaaaDDAAyyAyyE'),
            ('lhhffhfhhhhhhhhffhhh', 'ycirDaacicAaabaAAAyF', '.ibrDDabDDbbbaAAAyF.'),
            ('hhhfhhhhfhhhhffhh', 'cccrbayAabbbaAAAF', '..yrDbbbaaDAAAAv.'),
            ('    hhhhhhhhhhh', '....AADAAyEEEyF', '.....FyyE......'),
        ]},
    'villager': {"w": 24, "h": 15,
        "pal": [(244, 150, 98), (102, 54, 49), (234, 139, 90), (110, 57, 47), (67, 30, 39), (91, 48, 45), (61, 26, 34), (83, 41, 39), (132, 81, 68), (215, 126, 85), (159, 78, 43), (160, 87, 61), (176, 107, 80), (64, 63, 73), (45, 29, 44), (49, 22, 25), (62, 28, 17), (89, 46, 43), (89, 43, 23), (88, 66, 70), (242, 160, 114), (132, 98, 90), (57, 46, 56), (29, 11, 20), (115, 55, 30), (113, 59, 48), (133, 73, 57), (140, 66, 42), (190, 107, 71), (181, 128, 107), (171, 89, 56), (170, 100, 75)],
        "fb": [209, 88, 173, 88, 52, 52, 52, 52, 95, 173, 130, 131, 131, 238, 235, 234, 52, 52, 52, 238, 216, 95, 236, 233, 88, 88, 95, 95, 131, 137, 130, 131],
        "rows": [
            ('        lhhhhhll', '........sxykyqkh', '.........EkBBk..'),
            ('      lhffhhhfhhhl', '......qykBBkkkkBqx', '.......kkBzyBklEk.'),
            ('      hhhhhhhhhhhh', '......klBzzbfbBkky', '......EBfoowwoohBk'),
            ('     hhhhhhhhhhhfhh', '.....sBeeAEntAfneBp', '.....yegEmadFaFCeeq'),
            ('     hhhhhhhhhhhhhh', '.....qoiiwFCjmtllop', '.....BtmFvtbztvFCrA'),
            ('     hhhhhhhhhhhhhh', '.....BfCFDuEcuujjtl', '.....dzmECcCjaacmzz'),
            ('      hhhhhhhhhhhh', '......CijcCFjCcjiC', '.......olmtwwiCFo.'),
            ('       ffhhhhhhhh', '.......pnwdllAwtx', '.......pnAjbbjln.'),
            ('        hhhffhhh', '........rtittviw', '........sontttnx'),
            ('      llhhhhhhhhll', '......yyyxooowAihq', '........Eexxpkcm..'),
            ('   llhhhfhhhhhhfhfhl', '...qBybgzzpeCcuuzbpr', '.....rehzBlCuaaulbr.'),
            ('lhhhfhhhhhfhhhhhffhfhhl', 'qxyzrhgeBjcjaacmffbzzqb', '.ArrrreghiccjjFfffzzdd.'),
            ('hhfffffhhhhhhhhhhhfffhhh', 'efrfrrreperFAebhfzdddzdh', '.hrfrrrfhggggghfbdddddb.'),
            ('  hhhhfffffhhhhfhffhhh', '..grffrfffgpgfbdbddddh', '....grrfffgghddddddh..'),
            ('      hhhhfhhhhhhh', '......phfhpedzzzbe', '.........ppghfhx..'),
        ]},
    'title_l': {"w": 96, "h": 28,
        "pal": [(19, 29, 69), (108, 28, 60), (151, 39, 72), (18, 18, 53), (30, 27, 62), (34, 50, 99), (60, 67, 124), (108, 44, 67), (13, 17, 53), (18, 24, 61), (73, 63, 118), (36, 59, 113), (107, 51, 58), (162, 63, 90), (172, 101, 69), (57, 55, 104), (133, 43, 60), (8, 11, 33), (54, 25, 55), (31, 33, 71), (13, 15, 45), (54, 43, 76), (77, 53, 87), (32, 41, 84), (134, 56, 92), (31, 19, 49), (21, 38, 83), (196, 44, 77), (107, 63, 104), (80, 36, 61), (14, 15, 50), (16, 14, 50)],
        "fb": [17, 89, 125, 17, 17, 18, 24, 89, 17, 17, 60, 24, 88, 125, 131, 24, 88, 17, 53, 17, 17, 53, 53, 17, 89, 17, 17, 161, 60, 52, 17, 17],
        "rows": [
            ('', '', ''),
            ('', '', ''),
            ('llllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllll', 'FFFFEFFdFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFdFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFjdFFFF', '................................................................................................'),
            ('hffhhfhhhfffffffffffffffffffffffffffffffffhfffffffffffffffffhhhhhfffffffffffffffffffffffffffhhhh', 'FEEFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFsDsFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFja', 'EEEEdFidEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFdFFFFFFFFFFFFFFFFFFsDDsFFFFFFFFFFFFFFFFFFFFFFFFFFFjjxx'),
            ('hhhffhfhhhhhhfhffffffffffffffhhffffffffffffffffffffffffhhhhhhhfhfhhhffffffffhhhffffffhhhhhhhhfhh', 'eEEEEEEiEFdFFFdFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFdFFFFFFFFFzdFFFzbDDDsFFFFFFFFFFFFFFFFFEFFFFFFjxxxx', 'tdiEEiEdidEdEFFFFFFFFFFFFFFFFEEFFFFFFFFFFFFFFFdFFFFFFFFsDbqDzFbhDbDsFFFFFFFFdedFFFFFEEEEixtpfxpp'),
            ('hhhhhfffffhfhffhhhhhhhhhhfhfhhhfhhhfhhhhhhhhhhhhfhhhhfhhhhfhhhhhhhhhhhhhhfhhhhhhhfhhhhhhhffffhhf', 'djtjddiiiEEEiEEFFFFFFFFFFFFEdFdEFFFEFFFFFFFFFFFFFFFFFFsqcbqcbsbbbbbbzFFFFdeejdFFFjEejjtxfgkkpppk', 'jdieediiiEiEEEEEEEEEEEidEFEEEiEEEEiEEEdEEEEEEEEEFEEEEFnBbsqbcqDhhDhhDEEdddEEFijjejdjtffpggkkpkkk'),
            ('hhhhfhhhhhhhffffhhffffhfhhfffhfhfhhfhhhhhfffhfhfhfffhhhhhhhhhhhhhhhhfhhhhhhhhhhhhhhhhhhhffffffff', 'xjiFeeeiiiiiiiiiEdiiiiEiiiiiididiiEiEiiEEiiiiiiiEiiiEbBczEsccDqcqbqhDEEjdEEjaxxttttfpgggkkkkkkkk', 'ppxtejdtjdddiiiiiiiiiiiiEEiiiiiiidiiijdiiiiididiiiiiiDqsidcqqqcqbcbbDsiiEadxfffxffpptxfvkkkkkkkk'),
            ('hhhhhhhffhhhhhhhfffffffhfffffhffhhhfhffhffhffffhfffhffhhfhhhhhfhfhhhfhhhhfhhhhhhhhhhhfhhhhfhhhhh', 'ppvvxvpvvxxxtjiiiiiiiiiiiiiiidiidddiiiiddiiiiiiiiiiEiidiiqcbDDssbqDsbDDaxfAffxffppftvjtxvkkkkkpp', 'ggppppvvvvpvxxtjiiiiiiidiiiiiiiiiiiidiiididiiiidiiiiiiidicqcbssDbDsDbchvffvvvvppgftjxjjiipkppxaf'),
            ('fffhhhffhhffhhhfhfhhhhhhhfhhhhhhhhhhhhhhhhhhhhhfhhhhhhhhhhhfhhhhhhhhhhhhhhhhhhfhhfhfhhffhhhhfhfh', 'gggkpppppppptatttjddiiididiididdididdddddddddddjdddddddddqBDszsbDsssDqcyppppppkkpxtjjtiiavkpppkp', 'ggggggppgkppppptajxjdddjedddjjjjjjdjjjjjjjjjjjjjjjjjjjjjsbDDDbDssuuFsbbBykkgkkkgAxvjiiiivavkpkkg'),
            ('hhhhfhhhhhhhfhfhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhfhhhhhhhhhhhhhhhffhhhhfhhffh', 'ggggggggglggggkppvfpfxxaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaasDzFzzzuEjjEzbbhcCkkkkkfAxftiitaxajpkggg', 'xfxfgftxxxapgkkkkpkkkkkppppxpxttttttttttttttttttttttttttDjiddrujeuudzcqbqwpppgaAxAxxiiatatjtpggk'),
            ('hfhhfhfhfhhhhhffffffhfhffffffhhhhhhhhhhhfhhhhhhhhhhffhhhhhfhhffhhhhhhfhfhhhfhhhhhhhfhfhhhhhhhhhh', 'lljxijataidAkkggggggggkggggggkfxxAAAAAAAxAAAAAAAAAAxxAAsseesdrdjdrrdbcqbDzppgfixxxAxjidaaaaxfggg', 'alajiiaaaxaaflggggggkgggggggggkkkkxxxxxxxxxxxxxxxxxxxxeejEejurddjEzDqchbzdtpAptAAtxxxijjttjtvtpk'),
            ('fhhhffhhffhhhhhhhhhhhhhhhfffhhhhhfhhhhhffffffffffffffhhhhhhfffhhhhhhhhhhfhfhhfhhfhhhhhhhhfhhhhhh', 'jAlfjjjtiixifAfggggggggggkkkkggggkfffffffffffffffffffvsjddjdurEjesbcqbDsudutAxvaAavxvtjjaaatvvja', 'jixAjjiiiiAaxaaflkCCkkkkkkkkgkkkkkgggppffffffffffffffdrduzsdurFDbqqbDsszuuuetxtjAxfvxpatxajaAtii'),
            ('hfhhhhhhhhhhhhhhhhfhhhhhhhhhfhhhfhhfhhfhhhhhhhhhhhhhhhhfhfhhhhhhhhhhhhhhhhhfhhfffhfhfhhhhhhhfhhh', 'aiiajxjiijEAAAjxfggxCyyyyywpggCyyyyCCwppppppppffpppkCdduEdtjrsqcbDDsszurduudeatjAxxxtAjjxaiiaiji', 'tiuiAaaaaiiiffafAfggfknBBnAAglggyBnCkkpkkkCCCCyCCCBBbzzudddrDbbssszFuEjzeErdzttjAAxatxtittjaajij'),
            ('hhffhhhfffhfhhhhfhhhhfhhhfhfhhfffhhfhhhhhhhhhhhhhhhhhhhhhhhhhhhhhfhhhhhhhhhfhhhhhhfhhhhhhhhhffhh', 'ajruajAAaAiialxxaApglxoBCfxAlggggCyyyyyppCCCCyyyCnBBzdujEdubhDszFurrddedteuuzjdjaxAaapxiaajtijur', 'turuiaiAaAjiiffiaallgxCCpfAAflggglkynnpAApnBnBBngknwsuiudrbqszuujudEjjEjedduEurdtAAAixvjejAiijiu'),
            ('hhfhhfhhhhhhfhfhhhfhhhfhhhhhhhffhfhhhffhfffhhfhfhhhhhhfhhfhhhhfhfhhhhhhhhfhhhfhhhhhfhhhhhhhffffh', 'tdruEjfjfxjijAlaailapgfACpfxAxllgglgglfxAfgllfklggljjdduubbsdEdddEjjddEejudjujujeaAAjjtaiajujaAa', 'irriijAaaAfjjflfjalxaffglgjplAlllggfllfAAfggfflllfjderdrsbszradjdjdeEuudduuEdjddudaAtiajAjaujaAj'),
            ('hllhhhhhffhhhfhfhhhhhhhhfhhhfhhhfhhffffffhfhfhfhhhfhhfhhffhffhhffhhhhhhhfhhhhhfhfhfhhhhhhhhhhhh', 'rrrrjijaiialiafljjflAfAlglfjjfffllglffffffgglffxxeddErrusszrdejjudjduruEuuuuruurujetAiaaiairjja', 'E..uAliiiiiAlalllaAgxtxfgfgfjxAllgllfffffAgllxfjeudrrriessurdjajujuEjErruzzddruzudedjajjjjAuiu.'),
            ('hhhhhhhhhhhhhhhhhfhhfhffhfhhhfhhhhhhhfffffhhhhhhhhhhhhfhfhfhhhhfhfhhhhhhhfhhhhhhhhhfhhhhhhh hhfh', 'irrjxffaiixjxfxlllalfAAjflllaafalggffffffAfllvteuuurujtzssrujaauEjjeteEzzDsurujeeddezeijaAd.uuuu', 'u..rrtAffjafijfAxlfaflAjjlgxlaAxaxlllffffAxxeddjrrEjjtteszrdejiujjdajdudsDbzurddjujedreAtar.riur'),
            ('l  hhhhfhfhhfhhhhhhhhhhffhhhhffhhhhhhfhffhhhhhhfhfhhfhhhfhfhfhhhhhfhhhhhhhhhhfhfhhhhhhhhhhh hhh', 'r..axAAAfxtxfaafaAlfAxAaaflgxfffAiafllffAAjjudjurujdtejsszjaddjjjedjiEzEsbqzeuurjdudeurjtji.uid', '....rjxAAxxAffAAxfxAxajaaaflgffllAiaxllfAjuureuuuudttudzsujddjdeejdueddurzssuurrrzzudjddaur.rr.'),
            ('l  fhhhhfhhfhhhhhhhfhhhhhhhfhhfhffhhhhfhhhhhhhhhhfhhhhfhfhhfhhhfhhhhhhhhhhhhhhhhhfhfhhhhhll lll', 'r..ruatfxAAAxfxvAAAAAfllfjxfgglllfAjAxxlfrurddrduetjEuursddddEjjdErusduuuuFdezdurrduFdjdrFr.rur', '...rtwwvxxxAAxffffxAxtfglfAflllglffxtaxduddjuudueejduruussudjuejzuEzeurrrruuruuddrruurrjj......'),
            ('h   hhffffhfhhhhhfhhhhhhhffhhffffffffhhhfhhhfhhfhhhhhhhhfhhhhhhhhhfhhfhhhfhhhhhhhhhhhhhhhhl hh l', 'r...rtvwwvxxAAAAxxxpfttfgllfllllllxdjdjdetjEuuueedddurEaessjuEjjdzDDsszuururrruuurrruuiudur.ru.r', '....zvvwwvvxxxtvAxDvlfAtflllflllllxdjuzteuduudtejjuurueeeuzDsDssDDDzzsssdrddjajjttttttxtz....r..'),
            ('ll  lhfhhhhfhhhhhhhhhhhhhhhhhfffhhhhhhfhhhhhhhhhfhhhhfhhhhhhhhhhfhhhhhhhhhhhhhfhhhhhhhhhhh    l', 'rr..ruvwwzvwxxthvADDtffAxflgllllltdudteeEuuuEejjdjuureeedjdrudzduuzFEdjetatxxxvvvvvvvvvvvt....r', '.....zvvvrzwvdzzzddsstAxtxfffllledueeeejjddjjjudduddtejjjeuzzsruujattAttxvwwvvvxtjjeettezr.....'),
            ('fffflhhhhhhhhfhhhfhhhfhhfhfhhhhhhhhhfhhhhhhfffhfhhhhhhhhhhhhhhhfhhhhhhhfhhhhhhfhhhfhhhhhhf l', 'rjrrirszDrrhtdeedzzvDsxAtxxxtadddjeeeeejteddddududeeaeeetdxDxpjtajjjatxwmCvjjjtdjtxvtteerr.r', 'rjrr.ur.s.zDjddjjzDDmssvtvxvvdettettesvtedjdddddtttttxatefgllvftjatAxxwwwetttxtjdxxxjetver..'),
            ('hf hhhhhll hhffhhfhfhhfffhhhhfhhhhfhhhfhhhhhhfffhhhhhhhhhhhhhhffhhhhhfhhhhhfhhffhffhhhhhhf   l', 'jr.uijurrr.suzFzzsDoomvvvhDDvDtllfxxtspxeeeeetttttAtAxtjtxflvovDxxtvwCwmtevxvxtedtvtjeezrr...r', 'rr.ruaji...r.zFFFshomovvvesvDDztetxzfgpDtxttttttxxxxtejevtjjwwvDDtewyCvxvppxwvteetvvevvvsr....'),
            ('hhhfhhhhfhh  hhhhfhfhfhfhffhhhffhhhhhhhhhhhhhfhhhhfhhhhhhfhhfhhhhhhhhhhhhhhhhhfhhhhhhhhhh    l l', 'uuiudurirur..FjessDmDmhmzFFeFsDDexzdttmosttxxxxxxxtteeetmmejwvDDwCwwteetAfxfmDwvtzuesvDvz....r.r', 'rrruururriu...rsrssmmmmmsFFFzzDDszruzsDsDvvvtxtetttetttvDmjewtwvCwtevvtesssDyhwwurruruzr........'),
            ('fhfhh hhhhhhll   hhhhffhhhhfhhhhhfffhfhhhfhhhfhhhhhhhfhhhfhhfhhhhhhhhhhhfffffhhhhhhffhhhl hlfhhh', 'jdrur.rruiurrr...rrFsDDDDDzsssqhzzrrzsDsDmqwhDvvvtvttDhDmoezvavsvwvvtvtesDsDhyeurrrrrrrrr.rrrruu', 'jar.i..urrru........uDDhmmssmmDwtzrrssoqmmmDDDmwwDwwwDssqossvvmvwhttetsssDsDhDrruuurruid....riri'),
            ('hhhhhhhhhhhh h       hhhhhhhhhhhhh hhhhhhhhhhhhhhhhhhhhhhhhhhhffhhhfhhhhhhfhhhhhhhhhhhhhhhhhhhhh', 'ujadaudrijuu.r.......smnqqDDnqzdxe.rDsqqmDvxvvDvmnnnnnnoonyyyyqmynymDwvvsvDhDurdiriurrrurrrrurri', '.........r............r.rr.zssrrr...zrzzssszsDzzrsDzrrzsvDDmqqqmmmmmmDDDDDDs....................'),
            ('', '', ''),
            ('', '', ''),
        ]},
    'title_m': {"w": 72, "h": 21,
        "pal": [(19, 30, 70), (17, 14, 50), (106, 29, 61), (158, 43, 78), (108, 48, 68), (14, 15, 50), (80, 44, 61), (79, 28, 60), (31, 26, 61), (18, 24, 62), (35, 50, 98), (72, 64, 120), (35, 58, 111), (103, 52, 61), (56, 53, 102), (104, 61, 105), (33, 19, 48), (58, 65, 122), (195, 65, 81), (32, 41, 83), (31, 33, 70), (130, 58, 88), (55, 25, 55), (22, 40, 84), (14, 15, 45), (130, 39, 62), (9, 11, 34), (55, 42, 74), (145, 60, 70), (76, 55, 90), (14, 17, 53), (19, 19, 54)],
        "fb": [17, 17, 89, 125, 88, 17, 52, 53, 17, 17, 18, 60, 24, 88, 53, 60, 17, 24, 131, 17, 17, 89, 53, 17, 17, 88, 17, 53, 95, 53, 17, 17],
        "rows": [
            ('', '', ''),
            ('', '', ''),
            ('hhfhhhhfffffffffffffffffffffffffffffffffffffffhhhfffffffffffffffffffhhhh', 'bbbbbFbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbqbbbbbbbbbbbbbbbbbbbbbbFbbb', 'ffbEfEfbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbqhwqbbbbbbbbbbbbbbbbbbbbFat'),
            ('hhhfhffhhhhffffffffffhfhfffffffffffffffffhhhhhffhhhfffffhhhfffhhhhhhhhhh', 'jffffEEFbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbqqbbhchhqbbbbbbbbbbbbfbfbbittt', 'ijFfEEEfEEfbbbbbbbbbbEbfbbbbbbbbbbbbbbbbbhzzzwhccchbbbbbjjjbbbEFFjuookkD'),
            ('hhhfhhfffhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhfhhhhfffhhhfhhhhhhhhhhhhhhhhhfhfh', 'FFijFEEEEEfffffffEfbffffffffFfffffffbffbwschzzcccccwfbFjEbEjjFjutorrloll', 'tjFjjFEEEfEEEEEEEfEEEEFEEEEEEEEEEEEEEEEbddqbzzcdzzchEFEfjtttttoorrlllllD'),
            ('hfhhhhhhhhhhfffffffffffffhffhfhffffffffhhhhhfhhfhhffhhhhhfhhhhhhhhhfhhhh', 'ootuutuiiFEEEEEEEEEEEEEEEFEEFEEEEEEEEEEbwwEzzzzhzzhcwEaatkktookuutDllDll', 'looooBBBBtujEEEEEEEEEEEEEEEEEEFEEEEEEEEEEEbdzhwhchhczokokkoorkatjjjlootk'),
            ('fhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhfhhffhhhhhhhhhhhhhhfhhhhhhffff', 'rrrooDooouuuiFFEEFFFFFFFFFFFFFFFFFFFFFFFFFwdcwwchqwhzdororrlktajjEuoooll', 'rlllllrrlolottkuajajjjjjjjjjjajaajjjjaajjjwhwwwqFFbqczvllllrxtuEFjBEooll'),
            ('hhhhhhhhhfhhhhfhfhhhhhhhhhhhhhhhhhhhhhhhhhhhhfhhhhhhhfhhhhhhhhfhhhffhhff', 'kkkrtkkxollloorolkkotBuuuuuuuuuuuuuuuuuuuuhyEyAFiyFqzczloomxtxtEjuujurll', 'mxxEjuajulrrrrrllrlrrlrkkttttttttttttttttiujiyyjfAEcdcwtrmuuxttjEaujtkll'),
            ('fhhhhhhhhhhhfhhhfffffhfffhhhhhhhhhhhhfffhhhhhffhhhfhhhhhhhhhfhhfhhhhhhhh', 'jmxEjujxjkkrrrrrlllllllllottkttttttttkktuiFFjyyFiwzzzhbFutoaxtttjjujuBut', 'jataEEfjaxjkrppllllllrllllrrokkkkkkkkkktFyywFyywczzhwqyyFutjxkktuutEaxjF'),
            ('hhhfhhhhhhhfhhhhhhhhhfhhhfhfhhhhhhhhhhhhhhfhhhhhhhhhhhhhhhhfhhhfhhfhhhhh', 'jfjaujEEaxaxkropvvvpkrlpddppoooooooooophFAFqFyczhhwqqAFAFiajxttuuEujjajE', 'aAfaaaajfkkxamrkDsdoxrrrldvppplpppvvvsswqfFFqzhwqyAEjiiyEqijuxautjuaajEy'),
            ('hfhhhhhhfhhhfhhfhhhhhhhhffhhhhhhhhhhhhhhfhhhhhhhhhhhhhhfhhhhhhffhfhfhhhh', 'uAfjjxaaEjmjjkmmopokxkrrrrvdpkkpddsslvpqyFEqzwqyjAEjjFiyyyyEuxxjoaijjEFy', 'aAyfxakxEaktjxxmmxpxmxkmrrmrkxxmrmorrrajyyycwyjEfFjFfiFyFfEFiuxjaajjfjaa'),
            ('h hhhhhhhhhfhhffhhfhhhhffffhfhhffhfhhhhhfhfhhhffhfhhhhfhhfhhffhhfhfhhhhh', 'A.yfjujatjkmjxmxkmrkakxmmrmmkxxmrkkmkiFFAAwhbEjjEFiyAEyyyyFyyjuajajayjaF', 'y.AxaEEExxtmtamxttrmkjkmmrmkkkkmrmkuiyyAAiwqAFjjyFyFyyyqbyAFyjFjjjjjFEy.'),
            ('h fhhhhfhhhhhhhfhhhffhhhhhfhffhfhhhhffhhhffhhfhhhfhhhhhhhhhhhhhfhhfhlhhh', 'y.ytkxEaaxtkmtkkxjkmmaxxkrmkkkkxmkBiAyAyiiwqAjaFFjiuFFqhqAEjiEiFjjaaAyfy', 'A.yjxtkataatxmxkkaammkakaxmmkkxxuFFFAyFiuiwyjjFEjjjFyEwcwFyEFyjFyaaE.AFA'),
            ('h fhfhhhhhhhfhhfhhhhhhhffhhhhhhhhhhhhhfhfhfhhfhfhhfhhhhhhhhhhhhhhhhh hh', 'A.AFuxxttkxxtktxajatrmkmmjakmkxEEAFyyEiiyqwfjFjjjFyFFyqhwbyAyFyjFfay.AA', '..AjuttxxtkttuuxkmkakrrmmkjxktayyEyEFiiyyAwbEFEjFyyifAyybFFyAybFyjAA...'),
            ('   fhfhhhhhhhhhhhhhhhffhhhhhhhhhhhhhhfhhhhhhhhhhhhhhhhhhhhhhhhhhhhhh hf', '...qDDttxuxkkkktumrkkmmrrttiuFFjEAEEuFEyAFwwFEFjFbqqAyAAAAyAbAAAAfjy.AA', '...qBDDBttuuttBmtummmmmmmmFFyiiFFyFiFFyAEuiqwwwwwhwwwqbyFFjjjjjuuuAA..A'),
            ('ll lhhhhhhhhhhhhhhhhhhhhhhhhhhhhhfhfhhhhhhhhhhhhhhhhhfhhhhhhhhhhhhhh  l', 'yA.AqDDqDBuhtihukxtmrrmmmjyjuiEyyFjFFEyEuiFjybbbyyqFjuuutBBBBBBBBBBy..A', '....iww.BuqiFFwwututttttyFiiiFjFFFFFyyjuijaFwwFEjaaauuDnBuuujiuuuiA....'),
            ('hhfhhfh hhhhhhhhhhhhhhhhhhhhhhhhhhhhhfhhfhhhhhhhhhhhhhhhhhfhhhhhfhhf', 'AFAAyAw.hjFFFwgnitutBuFiuiuiwiiFFFyFiuauuuimrmBujjuttnDuuutjittjuuqA', 'yAAEjAA.qyqbqBsCnBBgggwkktttoBuiiiuuuuxxujutknnBtuBDeDuBtBtiFuBiuiAA'),
            ('ffhfhhfhhhhhhhhhfhhhhhfhhhfhhhhhhhfhhhfhhhffhhfhhhhhfhhhhhhhhhhhhhh    l', 'AAyyyyAAAAiFqgggngqFiiwwitykoCwututtttuiiinBjgBhggDDuttkteBBiiBBBBq....A', 'AAAyAAAF..yqAwCnnCibFqwgwqyqwghBBttuuuuuuBnBiBBgnBuuuiwwBvngqAAqqy......'),
            ('hhhhlfhhhl   hhhhhhhhhhhhhfhhhhfhhhhhhhhhhffhhhhhhhhfhhhfhhhhfhffhl fhhh', 'jAAAAAAEAA...AywBBBwqwheqqAqhhgnnngBBBBueBCCiuuBDguuBiwwgvgFAAAAAyA.AAAy', 'yayF.AyAy.......nCCghCnjtyAwnsnnBBBDnvCvCnCCgngnnvgBBBBhggAyEAyAAA..AyyE'),
            ('      hh        hhhhhhhhh  hhhhhhhhhhhhhhhhhhhhhhhhhhhhhhh', '......AA........AAAAqwwAA..qAqwhqwwqqgwqqggnnCCCnCnggggggA', '..........................................................'),
            ('', '', ''),
        ]},
    'title_s': {"w": 54, "h": 16,
        "pal": [(21, 31, 72), (100, 29, 58), (17, 14, 50), (103, 61, 112), (100, 41, 69), (101, 54, 55), (15, 14, 50), (122, 33, 66), (77, 26, 58), (78, 62, 116), (31, 25, 59), (14, 18, 55), (19, 19, 55), (35, 48, 96), (77, 42, 60), (56, 55, 104), (19, 26, 64), (60, 64, 121), (36, 58, 111), (120, 64, 67), (9, 11, 34), (159, 52, 97), (32, 18, 46), (32, 40, 83), (78, 51, 77), (23, 41, 86), (32, 32, 69), (54, 42, 75), (14, 15, 45), (141, 44, 62), (52, 24, 46), (52, 26, 58)],
        "fb": [17, 52, 17, 60, 53, 88, 17, 89, 53, 60, 17, 17, 17, 18, 52, 24, 17, 24, 24, 95, 17, 125, 17, 17, 53, 17, 17, 53, 17, 88, 52, 53],
        "rows": [
            ('', '', ''),
            ('llllllllllllllllllllllllllllllllllllllllllllllllllllll', 'gggccggcgggggggggggggcccggggcggggcFccgcccgggggcccgcccm', '......................................................'),
            ('hhfhhfffffhffhhfffffffhhffhffhfhhhfhhhhfhfhhffhhhhhhhh', 'mgccgcccccggggggcggcccccgcgggccccgwiiwcccccgcccgccgqAx', 'kmcglccccccggccgcggcccgggccgggcihbwbbbwcgcmqccgclmxnxp'),
            ('hhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhffhhhfhhhhhhhhhhfhhhf', 'mmkmlgggcccgcccgcggggcgggcggggbDiDhbbeicmmmmmqmAnprrpj', 'BAqqqlmlllllgglllllllmlllllllcDFwDhDhhimllanxxpnspjjjj'),
            ('hhhfhhhhhhhffhhfffffhhfhhhhhhhfhhhhhhhhhhhhhhhhhfhhhfh', 'ppBpBBxamlllllllllllllmlllllllmlhhiFhibbxnnnnpxAqAprpn', 'rrrppppxAqmllmmlllllmmmmmmmmmmmmDbFiiwiDhppprnAqqqBppr'),
            ('hhhhhhhfhhhhhhhhhhhhhhhhhhhhhhhhhhhhfhhhhhhhhhhhhffhff', 'rrrrrsrrpBpxxaaqqqaqqqqqaqaqaaqAFwwwmmwbDjjrpznlqAqprr', 'saxazanrrrrrrrrppxxxxxxxxxxxxxxFkkCmmCiDeBpsaxxamAqxrr'),
            ('hfhhhhfhhfhhhhhhhhhhhhhfhhhhfhhhhhfhhhhhhhhhfhhfhhhhhh', 'azqqqaanrrrrrrrrrrrnxnxnxxxxnxAkmkumqiDhFmxnaaxxqqaxBn', 'lzalllaazrddjjjjjjdjrppnnnnnnncCEmuibhiFCCmxaxnxAAqaAl'),
            ('hhhhhhhfhhhhhhhhhhhhhhhhhhhffhhhhhhhhhhfhhhhhhhhhhffhh', 'qCqaqlqnzzrpdvdnrjvvdjjjjdddvhwcmwbbFkwmmCmkqzxAaaqqql', 'aulqaalnaqsrftnzsrrdvdndvvvdvFcgwbFccCmmkmcCcAzqnqqqlu'),
            ('hhhhhhhhhffhhhhhfhhhhfhfhhhhhhhhhhhhhfhhhfhhhhhhhffhfh', 'muCzazlznqnnsppnzsrsrnzsssssxqgCbFlmlmmCkCmmmmzqaqqlqa', 'u.qqqlzasqnzzrsaznsrnnnsrnnAcCuFFuqqCmcuCCCCuCkaqqqCqu'),
            ('ffhfhhhhhhhhhhffhhhhhfffhhhhhhhffhhfhfhhfhhfhhffhhhfhf', 'uuAzqqannsznazssazsrnnnzsxkCuCqFwCqmmmAmwiCCqkmmmqauCu', 'uuqznAzazznzzqssznazsnnzammumkAFwqmmqmmCwbECCmmmCalulu'),
            ('  hhhffhhhhfhhhhfhfhhhhhhhhhhhhhhfhfhhhhfhhhfhhhhhh l', '..uazxxnxzzzzzassssqzsngCmCCkkCFmmmqqCwcuwwmCummmmu.u', '..kBBxxxnnxznrnnsrszaalmgCckmCukFmgqmckuuCCCCCuCuqC..'),
            ('l hhhhhhhhhhhhhfffhhhhhhhhhhhhhhhhhhhhhhhhhhhhhfhhh h', 'u.uByBxxAxynznsssssAmmkmCckqgCmAwFFFFiFFwCmmqqqAAku.u', '...FBwyAFkkkxxnsssACqAqcmqmmCmqqqcwCCmqaABBBBAAABAC..'),
            ('hfhhhhhhhhhhhhhhhhhhhhhhhhhhhhfhfhhhhhhhfhhhhhhhfhf', 'uuuwEuomkkFoAxxxqmkAkFkkmmCmaAAaxpnAqqAByyAAkAxAAku', 'CuCmu.wwcwttyBooBnnxxpAAkAAAxxAAxntBxxyyyBxBAkBkAwu'),
            ('hhhhfflhhhhhhfhhfhfhhhhhhhhhffhhhhhffhhfhhhhhhhhhh  ll', 'uCCCuCuCkwfffogmFikkAofAxxxxAAABokyoyyBAxnByBkwFBk..uu', 'CuuuuC..uukoyoFwFekuwiiyyBAAAAootAAoyBAAFFotFuuuu.....'),
            ('hhhhhhhh   hhhhhhhhhhhhhhhhhhhhhhhhffhhhhhhhhhhhhh hhh', 'qlCuuCCu...uetfitFAuEtteBoyftttttooffyBBBioFCCCuuu.uCC', '.....u.........uE....uEEwEwwEuwEofffffoEEoE...........'),
            ('', '', ''),
        ]},
}
# --- END PICS ---

PIC_MODE = None   # set by the UI: "true" (24-bit), "256", or None (ASCII only)
PIC_MAXH = 99     # tallest picture that fits the current screen
PIC_CODE = {c: i for i, c in enumerate("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")}
PIC_GLYPH = {"h": "▀", "l": "▄", "f": "█"}

BESTIARY = {
    "rat": "Fat as a hound and twice as bold, the rats of the Rusty Lantern's cellar have grown fat on more than grain.",
    "wolf": "Grey hunters of the Whisperwood. Where you see one, the rest of the pack is already circling.",
    "goblin": "Cruel, cowardly and quick with a rusty blade. Goblins fight dirty and flee when the fight turns.",
    "goblin_archer": "A goblin with a short bow and a good eye. It prefers to shoot from behind its friends.",
    "bandit": "Desperate men who found the road easier to rob than to walk.",
    "kobold": "Small, scaled and fanatical. Kobolds worship dragons and die for them gladly.",
    "kobold_slinger": "A kobold with a sling and a pouch of sharp stones. Annoying at range, fragile up close.",
    "cultist": "A robed follower of the Pale Flame, eyes glassy with borrowed faith.",
    "fanatic": "A true believer of the Pale Flame, gifted with dark prayers. Strike it before it speaks.",
    "spider": "A spider the size of a pony. Its venom numbs the limbs; its webs hold the unwary fast.",
    "ogre": "Grukk is huge, hungry and not very clever. One blow from his club can fell a strong man.",
    "skeleton": "Old miners' bones, raised by cold fire. They feel no pain and know no fear.",
    "skeleton_archer": "Dead fingers still remember the bowstring. Keep moving.",
    "zombie": "One of the lost night shift. Slow and dull, but it does not stay down easily.",
    "ghoul": "A corpse-eater with a paralysing touch. Never fight one alone.",
}


def pic_for(key):
    """The picture for an art key, if pictures are on and it fits the screen."""
    p = PICS.get(key) if PIC_MODE else None
    return p if p and p["h"] <= PIC_MAXH else None


# Palette slots 16-21 are repainted by base16 colour schemes (WezTerm's Catppuccin, Gruvbox ...),
# so 256-colour output swaps them for the nearest colours outside that range.
SAFE256 = {16: 232, 17: 234, 18: 24, 19: 25, 20: 26, 21: 27}


def pic_escapes(p, y, x, true=True):
    """ANSI sequence painting picture p with its top-left at screen cell (y, x)."""
    pal, fb = p["pal"], p["fb"]

    def col(code, bg):
        i = PIC_CODE[code]
        if true:
            return "%d;2;%d;%d;%d" % (((48 if bg else 38),) + tuple(pal[i]))
        return "%d;5;%d" % (48 if bg else 38, SAFE256.get(fb[i], fb[i]))
    black = "48;2;0;0;0" if true else "48;5;232"
    out = []
    for j, (g, f, b) in enumerate(p["rows"]):
        out.append("\x1b[%d;%dH" % (y + j + 1, x + 1))
        last, skip = None, 0
        for k, ch in enumerate(g):
            if ch == " ":
                skip += 1
                continue
            if skip:
                out.append("\x1b[%dC" % skip)
                skip = 0
            sgr = col(f[k], False) + ";" + (black if b[k] == "." else col(b[k], True))
            if sgr != last:
                out.append("\x1b[0;" + sgr + "m")
                last = sgr
            out.append(PIC_GLYPH[ch])
    out.append("\x1b[0m")
    return "".join(out)


# --- map rendering helpers ----------------------------------------------------
# box-drawing wall pieces by neighbour mask (N=1, E=2, S=4, W=8)
BOX_WALL = {0: "\u25aa", 1: "\u2551", 4: "\u2551", 5: "\u2551", 2: "\u2550", 8: "\u2550", 10: "\u2550",
            3: "\u255a", 6: "\u2554", 12: "\u2557", 9: "\u255d",
            7: "\u2560", 14: "\u2566", 13: "\u2563", 11: "\u2569", 15: "\u256c"}
WALL_JOIN = (T_WALL, T_DOOR, T_ODOOR, T_SHELF, T_SEAL)
UNI_TILE = {T_TREE: "\u2663", T_ROCK: "\u25b2", T_PILLAR: "\u25cf", T_FLOOR: "\u00b7", T_CFLOOR: "\u00b7",
            T_STONEFL: "\u00b7", T_WELL: "\u25cb", T_GRAVE: "\u2229", T_BRIDGE: "\u2550", T_RAIL: "\u2550",
            T_CHEST: "\u25a0", T_TABLE: "\u2564", T_BED: "\u25ac", T_COUNTER: "\u2584", T_SEAL: "\u2593", T_CAGE: "\u256b",
            T_CAGEDOOR: "\u256a", T_CARPET: "\u2591"}
UNI_ANIM = (T_WATER, T_LAVA)
UNI_TR = str.maketrans({"~": "\u2248", "-": "~", "=": "\u2248"})
WIDE_FILL = (T_WATER, T_LAVA, T_BRIDGE, T_RAIL, T_COUNTER, T_BED, T_CARPET, T_CROPS, T_SEAL, T_HOARD, T_SHELF)
# light sources: tile -> (rgb tint, radius, flicker speed)
LIGHT_SRC = {T_FIRE: ((1.0, 0.55, 0.20), 5, 9.0), T_TORCH: ((1.0, 0.60, 0.25), 5, 11.0),
             T_LAVA: ((0.90, 0.30, 0.05), 2, 3.0), T_PALEFIRE: ((0.55, 0.75, 1.0), 6, 7.0),
             T_HOARD: ((0.60, 0.50, 0.15), 1, 2.0), T_SEAL: ((0.30, 0.10, 0.35), 2, 4.0)}
_SYS16 = [(0, 0, 0), (128, 0, 0), (0, 128, 0), (128, 128, 0), (0, 0, 128), (128, 0, 128), (0, 128, 128), (192, 192, 192),
          (128, 128, 128), (255, 0, 0), (0, 255, 0), (255, 255, 0), (0, 0, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255)]
_CUBE = (0, 95, 135, 175, 215, 255)


def rgb_of(col):
    """RGB of a colour tuple (xterm-256 index, 8-colour fallback)."""
    i = col[0]
    if i < 16:
        return _SYS16[max(0, i)]
    if i < 232:
        i -= 16
        return (_CUBE[i // 36], _CUBE[i // 6 % 6], _CUBE[i % 6])
    v = 8 + (i - 232) * 10
    return (v, v, v)


def memory_rgb(c, k):
    """Explored but out of sight: dim, desaturated, cool."""
    l = (0.30 * c[0] + 0.59 * c[1] + 0.11 * c[2]) * k
    return (int(l * 0.88), int(l * 0.92), int(min(255, l * 1.02)))


# --- sprite map (4x4 pixel tiles drawn with half blocks) --------------------------
SPAL = {
    "g": (88, 140, 58), "G": (106, 156, 66), "d": (72, 122, 50),
    "t": (96, 64, 36), "T": (70, 45, 25),
    "l": (34, 96, 44), "L": (62, 136, 58), "k": (16, 54, 28),
    "r": (150, 120, 80), "R": (120, 95, 62), "p": (182, 162, 122),
    "w": (122, 82, 46), "W": (148, 102, 60), "v": (88, 56, 30),
    "s": (112, 112, 118), "S": (152, 152, 158), "x": (72, 72, 80), "X": (44, 44, 52),
    "c": (56, 52, 50), "C": (68, 63, 60), "z": (44, 41, 40),
    "m": (122, 104, 84), "M": (156, 134, 108), "n": (82, 70, 58), "o": (225, 175, 60), "@": (40, 34, 30),
    "b": (40, 82, 165), "B": (95, 145, 215), "u": (25, 50, 112),
    "f": (255, 165, 40), "F": (255, 232, 125), "e": (205, 58, 20),
    "h": (232, 92, 22), "H": (255, 196, 70), "j": (148, 38, 10),
    "y": (225, 185, 55), "Y": (255, 236, 135),
    "a": (150, 70, 50), "A": (184, 98, 72), "q": (88, 58, 48),
    "D": (132, 86, 42), "E": (84, 52, 26), "K": (225, 195, 95),
    "P": (175, 210, 255), "Q": (240, 250, 255),
    "U": (150, 60, 190), "V": (205, 125, 245),
    "O": (222, 216, 196), "N": (150, 30, 36), "Z": (192, 62, 56),
    "i": (232, 120, 172), "I": (242, 222, 92),
    "1": (226, 200, 92), "2": (160, 128, 42), "3": (205, 58, 58), "4": (205, 205, 215),
    "5": (72, 92, 165), "6": (232, 232, 232), "7": (12, 12, 14), "8": (30, 30, 36), "9": (128, 128, 134),
    "0": (162, 166, 178),
    # inn furniture: pale oak with dark rims so it stands out from the plank floor
    "J": (200, 152, 94), "+": (230, 192, 132), "#": (54, 32, 16), "%": (70, 44, 22),
}
# tile -> list of variants (static tiles) or ("anim", frames)
SPRITES = {
    T_GRASS: [("gGgg", "ggdg", "gggG", "dggg"), ("ggGg", "dggg", "gggg", "ggdg"), ("gdgg", "gggg", "gGgg", "gggd")],
    T_ROAD: [("rRrr", "rrpr", "Rrrr", "rrRp"), ("rrrR", "prrr", "rrRr", "Rrrr")],
    T_FLOOR: [("wwWw", "wwww", "Wwww", "vvvv"), ("wwww", "wWww", "wwwW", "vvvv")],
    T_STONEFL: [("ssSx", "sssx", "Sssx", "xxxx"), ("sSsx", "Sssx", "sssx", "xxxx")],
    T_CFLOOR: [("cccc", "czcc", "cccC", "cccc"), ("cccc", "cccz", "Cccc", "cccc")],
    T_ROCK: [("gsSg", "sSSs", "sSsx", "sxxs")],
    T_TREE: [("gkkg", "kLlk", "klLk", "gtTg"), ("gkkg", "kLLk", "kllk", "gTtg"), ("kLlk", "LlLl", "kllk", "dtTd")],
    T_BUSH: [("gggg", "gkkg", "kLlk", "gkkg"), ("gggg", "gkLk", "klLk", "gkkg")],
    T_FLOWER: [("gigg", "ggIg", "Iggi", "ggig"), ("Iggg", "ggig", "gIgg", "ggiI")],
    T_MUSH: [("g3gg", "gOg3", "gggO", "3ggg")],
    T_CROPS: [("I1I1", "2I2I", "I1I1", "2I2I")],
    T_WATER: ("anim", [("bbBb", "bubb", "Bbbu", "bbBb"), ("bBbb", "bbbB", "ubBb", "Bbbu")]),
    T_LAVA: ("anim", [("hhHh", "jhhh", "hHhj", "hhjH"), ("hHhh", "hhjh", "Hhhh", "jhHh")]),
    T_FIRE: ("anim", [("zeFz", "zFfe", "efFf", "zeez"), ("zFez", "eFfz", "fFfe", "zeez")]),
    T_PALEFIRE: ("anim", [("7QP7", "PQQP", "QPPQ", "7PP7"), ("7PQ7", "QPPP", "PQQP", "7PP7")]),
    T_TORCH: ("anim", [("AFqa", "qfqq", "qEaa", "qqqq"), ("AfqA", "qFqq", "qEaa", "qqqq")]),
    T_HOARD: ("anim", [("yYyy", "YyyY", "yYYy", "yyyY"), ("yyYy", "yYyy", "Yyyy", "yYyY")]),
    T_BRIDGE: [("WwWw", "vvvv", "wWwW", "vvvv")],
    T_DOOR: [("EDDE", "EDDE", "EDKE", "EDDE")],
    T_ODOOR: [("E77E", "E77E", "E77E", "EwwE")],
    T_TABLE: [("####", "+JJ#", "####", "#%%#")],
    T_CHAIR: [("w##w", "w#J#", "#++#", "#ww#")],
    T_COUNTER: [("DDDD", "DDDD", "EEEE", "vvvv")],
    T_BED: [("6655", "6655", "5555", "5555")],
    T_BARREL: [("wDDw", "EDDE", "DDDD", "wDDw")],
    T_ALTAR: [("ssss", "SSSS", "sxxs", "sxxs")],
    T_GRAVE: [("g99g", "9999", "g99g", "gddg")],
    T_FENCE: [("gTgT", "tttt", "gTgT", "gggg")],
    T_WELL: [("gssg", "sbbs", "sbbs", "gssg")],
    T_EXIT: [("rrrr", "rYYr", "rYYr", "rrrr")],
    T_SDOWN: [("SSSS", "sSSS", "8sSS", "88sS")],
    T_SUP: [("xxxS", "xxSS", "xSSS", "SSSS")],
    T_PILLAR: [("sSxs", "SSSx", "SSSx", "sSxs")],
    T_SEAL: ("anim", [("UVUU", "VUUV", "UUVU", "UVUU"), ("UUVU", "UVUU", "VUUV", "UUUV")]),
    T_CHEST: [("cyyc", "DDDD", "DKDD", "EEEE")],
    T_OCHEST: [("cDDc", "D77D", "DDDD", "EEEE")],
    T_TENT: [("gRRg", "RrrR", "rRRr", "R77R")],
    T_CAGE: [("0c0c", "0c0c", "0c0c", "0c0c")],
    T_CAGEDOOR: [("0c0c", "0K0c", "0c0c", "0000")],
    T_BONES: [("czcc", "OccO", "cOOc", "czcO")],
    T_WEB: [("4cc4", "c44c", "c44c", "4cc4")],
    T_ANVIL: [("wwww", "0000", "w00w", "0000")],
    T_RAIL: [("0000", "vcvc", "vcvc", "0000")],
    T_CARPET: [("ZNNZ", "NNNN", "NNNN", "ZNNZ")],
    T_SHELF: [("EEEE", "3I5i", "EEEE", "i53I")],
}
# walls: front face (open ground below) or top
SPR_WALL_FACE = [("Aaqa", "qqqq", "qAaa", "qqqq"), ("aAqa", "qqqq", "qaAa", "qqqq")]
SPR_WALL_TOP = [("xxxx", "xXxx", "xxxX", "xxxx")]
SPR_CWALL_FACE = [("MmMm", "mmMm", "mMmm", "@n@n"), ("mMmM", "Mmmm", "mmMm", "n@n@")]
SPR_CWALL_TOP = [("@@n@", "n@@@", "@@@n", "@n@@")]
SPR_ORE = [("MmoM", "omMm", "mMmo", "@o@n")]
SOLID_TILES = (T_WALL, T_CWALL, T_ORE, T_ROCK, T_SHELF, T_TORCH, T_SEAL)
# creatures and items: '#' colour, '+' lighter, '-' darker, 's' skin, '.' transparent
ACTOR_SPR = {
    "person": (".ss.", "####", ".##.", ".#-."),
    "humanoid": (".++.", "####", ".##.", ".#-."),
    "beast": ("....", "-##+", "####", "-..-"),
    "rat": ("....", "....", "-##+", ".-.-"),
    "spider": ("-..-", ".##.", "-##-", "-..-"),
    "big": (".++.", "####", "####", "#..#"),
    "dragon": ("-+#+", "####", "####", "#--#"),
    "downed": ("....", "....", "s##-", "...."),
}
ITEM_SPR = {
    "$": ("....", ".+#.", "#+#+", "...."), "!": ("..-.", ".+#.", ".##.", "...."),
    "(": ("...+", "..+.", ".-..", "-..."), "[": ("....", "#++#", ".##.", "...."),
    "]": ("....", ".+#.", ".##.", ".-.."), "=": ("....", ".##.", "#..#", ".##."),
    '"': ("#..#", ".##.", "..+.", "...."), "?": ("....", ".+#.", ".##.", ".-#."),
    "*": ("....", ".+..", "+++.", ".+.."), "^": ("....", "#..#", ".##.", "#..#"),
    "%": ("....", ".#..", "..#.", "...."),
}
# --- large sprites: 8x8 pixels (8 columns x 4 rows of half blocks) ---------------------
SPRITES8 = {
    T_GRASS: [("gggggggg", "gGgggggg", "gdggggGg", "ggggggdg", "gggggggg", "ggggGggg", "gggGdggg", "gggggggg"),
              ("gggggggg", "ggggggGg", "gggggGdg", "gggggggg", "gGgggggg", "Gdgggggg", "gggggggg", "ggggggGg"),
              ("gggggGgg", "ggggGdgg", "gggggggg", "gggggggg", "ggGggggg", "gGdggggg", "gggggggg", "gggggggg")],
    T_ROAD: [("rrrrRrrr", "rprrrrrr", "rrrrrrpr", "Rrrrrrrr", "rrrprrrR", "rrrrrrrr", "rRrrrprr", "rrrrrrrr"),
             ("rrrrrrrr", "rrRrrrpr", "rrrrrrrr", "rprrRrrr", "rrrrrrrr", "rrrrrprr", "Rrprrrrr", "rrrrrrRr")],
    T_FLOOR: [("wwwwvwww", "wWwwvwww", "wwwwvwWw", "vvvvvvvv", "wwvwwwww", "wwvwwWww", "wWvwwwww", "vvvvvvvv"),
              ("wwvwwwww", "wwvwwWww", "wWvwwwww", "vvvvvvvv", "wwwwwvww", "wWwwwvww", "wwwwwvwW", "vvvvvvvv")],
    T_STONEFL: [("sssxSsss", "sSsxsssS", "sssxssss", "xxxxxxxx", "Sssssxss", "sssSsxss", "ssssSxsS", "xxxxxxxx")],
    T_CFLOOR: [("cccccccc", "cczccccc", "cccccCcc", "cccccccc", "cCcccccz", "cccccccc", "ccccczcc", "cccccccc"),
               ("cccccccc", "cccccczc", "cCcccccc", "cccczccc", "cccccccc", "czccccCc", "cccccccc", "cccccccc")],
    T_ROCK: [("gggggggg", "ggxSSxgg", "gxSSssxg", "xSssssxg", "xsssssxx", "xxsssxxg", "gdxxxxdg", "gggggggg")],
    T_TREE: [("ggkkkkgg", "gkLLllkg", "kLLllllk", "kLllllkk", "kllllllk", "gkkllkkg", "gggtTggg", "ggdtTdgg"),
             ("gggkkggg", "ggkLlkgg", "gkLllkkg", "ggkllkgg", "gkLlllkg", "kkllllkk", "gggtTggg", "gggtTggg"),
             ("ggkkkkgg", "gkllLLkg", "kllllLLk", "kkllllLk", "kllllllk", "gkkllkkg", "gggTtggg", "ggdTtdgg")],
    T_BUSH: [("gggggggg", "gggggggg", "ggkkkkgg", "gkLLlkkg", "kLllllkg", "kllllkkg", "gkkkkkgg", "gggggggg")],
    T_FLOWER: [("gggggggg", "giggggIg", "glggggLg", "ggggiggg", "ggIgglgg", "gglggggg", "gggggggi", "ggggiggl")],
    T_MUSH: [("gggggggg", "gg33gggg", "g3333ggg", "ggOOgg3g", "ggOOg333", "gggggOgg", "gggggOgg", "gggggggg")],
    T_CROPS: [("1I1I1I1I", "I2I2I2I2", "22222222", "rrrrrrrr", "1I1I1I1I", "I2I2I2I2", "22222222", "rrrrrrrr")],
    T_WATER: ("anim", [("bbbbbbbb", "bBBbbbbb", "bbbbbuub", "bbbbbbbb", "bbbbBBbb", "buubbbbb", "bbbbbbbb", "bbbbbbBB"),
                       ("bbbbbbbb", "bbbBBbbb", "buubbbbb", "bbbbbbbb", "BBbbbbbb", "bbbbbuub", "bbbbbbbb", "bbBBbbbb")]),
    T_LAVA: ("anim", [("hhhhjhhh", "hHHhhhhh", "hhhhhhHh", "jhhhhhhh", "hhhHHhhj", "hhhhhhhh", "hjhhhhHH", "hhhhhhhh"),
                      ("hhhhhhhh", "hhhhHHhh", "jhhhhhhh", "hhHhhhhj", "hhhhhhhh", "HHhhjhhh", "hhhhhhhh", "hhjhhHhh")]),
    T_FIRE: ("anim", [("zzzzzzzz", "zzzFzzzz", "zzzFfzzz", "zzfFFezz", "zefFFfez", "zeffffez", "zTeTTeTz", "zzTTTTzz"),
                      ("zzzzzzzz", "zzzzFzzz", "zzzfFzzz", "zzeFFfzz", "zefFFFez", "zeffffez", "zTeTTeTz", "zzTTTTzz")]),
    T_PALEFIRE: ("anim", [("88888888", "888Q8888", "88QPQ888", "88PQP888", "8PQQQP88", "8PPQPP88", "88sSSs88", "8xxxxxx8"),
                          ("88888888", "8888Q888", "888QPQ88", "88PQPP88", "8PQQQP88", "8PPQPP88", "88sSSs88", "8xxxxxx8")]),
    T_TORCH: ("anim", [("AaaFaaaa", "aaFfFaaa", "qqqfqqqq", "aqAEaaqA", "aqaEaaqa", "qqqEqqqq", "AaaaqAaa", "qqqqqqqq"),
                       ("AaaaFaaa", "aaaFfFaa", "qqqfqqqq", "aqAEaaqA", "aqaEaaqa", "qqqEqqqq", "AaaaqAaa", "qqqqqqqq")]),
    T_HOARD: ("anim", [("cyYycyyc", "yYyyYyyy", "yyYyyyYy", "YyyyYyyy", "yyyYyyYy", "yYyyyyyY", "cyyYyycy", "cccyyccc"),
                       ("cyyYcyyc", "yyYyyyYy", "yYyyYyyy", "yyyyyYyy", "YyyYyyyy", "yyyyYyyY", "cyYyyycy", "cccyyccc")]),
    T_BRIDGE: [("vvvvvvvv", "wWwwwWww", "wwwWwwww", "vvvvvvvv", "wwWwwwwW", "wwwwWwww", "vvvvvvvv", "uuuuuuuu")],
    T_DOOR: [("qqqqqqqq", "qEDDDDEq", "qEDEDDEq", "qEDDDDEq", "qEDDDKEq", "qEDEDDEq", "qEDDDDEq", "qEDDDDEq")],
    T_ODOOR: [("qqqqqqqq", "qE7777Eq", "qE7777Eq", "qE7777Eq", "qE7777Eq", "qE7777Eq", "qEwwwwEq", "qEwwwwEq")],
    T_TABLE: [("w######w", "#++++JJ#", "#+JJJJJ#", "#JJJJJJ#", "########", "#J%%%%J#", "#%%%%%%#", "v#vvvv#v")],
    T_CHAIR: [("wwwwvwww", "ww####ww", "ww#JJ#ww", "w######w", "w#+JJJ#w", "w######w", "w#wwww#w", "v#vvvv#v")],
    T_COUNTER: [("DDDDDDDD", "WWWWWWWW", "DDDDDDDD", "EEEEEEEE", "DEDDEDDE", "DEDDEDDE", "DEDDEDDE", "EEEEEEEE")],
    T_BED: [("EEEEEEEE", "E666666E", "E666666E", "E555555E", "E5B5555E", "E555555E", "E555555E", "EEEEEEEE")],
    T_BARREL: [("wwwwvwww", "wwEDDEww", "wEDWDDEw", "w000000w", "wDDWDDDw", "w000000w", "wEDDDDEw", "wwEEEEww")],
    T_ALTAR: [("xxxxxxxx", "xSSSSSSx", "SSSSSSSS", "sssssssS", "xsSsssxx", "xsSssxxx", "xsSssxxx", "xxxxxxxx")],
    T_GRAVE: [("gggggggg", "ggg99ggg", "gg9999gg", "gg9S99gg", "gg9999gg", "gg9999gg", "gdd99ddg", "gggggggg")],
    T_FENCE: [("gggggggg", "gTggggTg", "tttttttt", "gTggggTg", "tttttttt", "gTggggTg", "gTggggTg", "gggggggg")],
    T_WELL: [("gggggggg", "gsSSSSsg", "sxuuuuxs", "sxubbuxs", "sxuuuuxs", "sSSSSSSs", "gsssssSg", "gggggggg")],
    T_EXIT: [("rrrrrrrr", "rrrYrrrr", "rrrYYrrr", "YYYYYYrr", "YYYYYYrr", "rrrYYrrr", "rrrYrrrr", "rrrrrrrr")],
    T_SDOWN: [("SSSSSSSS", "xxxxxxxx", "sSSSSSSs", "xxxxxxxx", "xsSSSSsx", "8xxxxxx8", "88sSSs88", "88888888")],
    T_SUP: [("88888888", "88sSSs88", "8xxxxxx8", "xsSSSSsx", "xxxxxxxx", "sSSSSSSs", "xxxxxxxx", "SSSSSSSS")],
    T_PILLAR: [("ssSSSSss", "sxSSSSxs", "ssSSsxss", "ssSSsxss", "ssSSsxss", "ssSSsxss", "sxSSSSxs", "xxxxxxxx")],
    T_SEAL: ("anim", [("UUVUUUVU", "UVVVUUUU", "UUVUUVUU", "VUUUVVVU", "UUUUUVUU", "UVUUUUUV", "VVVUUVUU", "UUVUUUUU"),
                      ("UUUUVUUU", "VUUVVVUU", "UUUUVUUV", "UVUUUUUU", "VVVUUUVU", "UUVUUVVV", "UUUUUUVU", "VUUUVUUU")]),
    T_CHEST: [("cccccccc", "cEEEEEEc", "EDDDDDDE", "EyyyyyyE", "EDDKKDDE", "EDDDDDDE", "EEEEEEEE", "cccccccc")],
    T_OCHEST: [("cEEEEEEc", "EDDDDDDE", "E777777E", "EyYyyYyE", "EDDDDDDE", "EDDDDDDE", "EEEEEEEE", "cccccccc")],
    T_TENT: [("gggRRggg", "ggRrrRgg", "gRrrrrRg", "RrrRRrrR", "Rrr77rrR", "RrR77RrR", "RRR77RRR", "gggggggg")],
    T_CAGE: [("0cc0cc0c", "0cc0cc0c", "0cc0cc0c", "0cc0cc0c", "0cc0cc0c", "0cc0cc0c", "0cc0cc0c", "00000000")],
    T_CAGEDOOR: [("0cc0cc0c", "0cc0cc0c", "0cc0cc0c", "0cc0cK0c", "0cc0cc0c", "0cc0cc0c", "0cc0cc0c", "00000000")],
    T_BONES: [("cccccccc", "cOcccccc", "ccOOOccc", "cccccOcc", "cccOccOc", "ccOcOOcc", "cccccccc", "cOOccccc")],
    T_WEB: [("4cc4cc4c", "c4c4c4cc", "cc444ccc", "4444444c", "cc444ccc", "c4c4c4cc", "4cc4cc4c", "cccccccc")],
    T_ANVIL: [("wwwwwwww", "w0000000", "ww00000w", "www000ww", "www000ww", "ww00000w", "w0000000", "vvvvvvvv")],
    T_RAIL: [("cvccvccc", "00000000", "cvccvccc", "cvccvccc", "cvccvccc", "00000000", "cvccvccc", "cccccccc")],
    T_CARPET: [("ZNNNNNNZ", "NZNNNNZN", "NNZZZZNN", "NNZNNZNN", "NNZNNZNN", "NNZZZZNN", "NZNNNNZN", "ZNNNNNNZ")],
    T_SHELF: [("EEEEEEEE", "3I5i35I3", "3I5i35I3", "EEEEEEEE", "i53I5i3I", "i53I5i3I", "EEEEEEEE", "vvvvvvvv")],
}
SPR8_WALL_FACE = [("AaaaqAaa", "aaaaqaaa", "qqqqqqqq", "aqAaaaqA", "aqaaaaqa", "qqqqqqqq", "AaaaqAaa", "qqqqqqqq")]
SPR8_WALL_TOP = [("xxxxxxxx", "xxxxxxxx", "XXXXXXXX", "xxxxxxxx", "xxxxxxxx", "xxxxxxxx", "XXXXXXXX", "xxxxxxxx")]
SPR8_CWALL_FACE = [("MmmMmmMm", "mMmmmMmm", "mmmnmmMm", "MmmmnmmM", "mmMmmmmn", "nmmmMmmm", "mnmmmnmm", "@@n@@n@@")]
SPR8_CWALL_TOP = [("@@n@@@@n", "@n@@@n@@", "@@@@@@@@", "n@@@n@@@", "@@@n@@@n", "@@@@@@@@", "@n@@@@n@", "@@@n@@@@")]
SPR8_ORE = [("MmmMmmMm", "mMomMmmm", "mmoomMMm", "MmmmnoMm", "mmMmmoon", "nmmmMmmm", "mnmmmnmm", "@@n@@n@@")]
ACTOR8 = {
    "person": ("...--...", "..-ss-..", "...ss...", ".+####+.", ".s####s.", "..####..", "..-..-..", "..-..-.."),
    "humanoid": ("..+##+..", "..#ee#..", "...##...", ".-####-.", "-.####.-", "..####..", "..#..#..", ".--..--."),
    "beast": ("........", "......+#", "#....+e#", "-######.", ".######.", ".#-..#-.", ".#...#..", "........"),
    "rat": ("........", "........", "........", "......+#", "..-###e#", ".-#####.", "..-..-..", "........"),
    "spider": ("-......-", ".-.##.-.", "..####..", "-######-", ".-#ee#-.", "-.####.-", ".-.--.-.", "-......-"),
    "big": ("..+##+..", ".#e##e#.", ".######.", "+######+", "########", "-######-", ".##..##.", ".--..--."),
    "dragon": ("+......+", "#+.##.+#", "##+ee+##", "-######-", ".######.", "..####..", ".##..##.", "-#....#-"),
    "downed": ("........", "........", "........", "........", "s-######", "s-######", "........", "........"),
}
ITEM8 = {
    "$": ("........", "........", "..+#+...", ".#+#+#..", "#+#+#+#.", ".#####..", "........", "........"),
    "!": ("........", "...--...", "...++...", "..+##+..", ".+####+.", ".######.", "..####..", "........"),
    "(": ("......+.", ".....+..", "....+...", "...+....", "..-#....", ".-#-....", "-#......", "........"),
    "[": ("........", ".#....#.", ".######.", ".#+##+#.", "..####..", "..####..", "........", "........"),
    "]": ("........", "..+##+..", ".+####-.", ".##++#-.", ".######.", "..####..", "...--...", "........"),
    "=": ("........", "...++...", "..#..#..", ".#....#.", "..#..#..", "...##...", "........", "........"),
    '"': (".#....#.", "..#..#..", "...##...", "...+#...", "..+##+..", "...##...", "........", "........"),
    "?": ("........", ".+####..", ".#----#.", ".#----#.", ".#----#.", "..####+.", "........", "........"),
    "*": ("........", "...+....", "..+++...", ".+++++..", "..+++...", "...+....", "........", "........"),
    "^": ("........", ".#....#.", "..#..#..", "...##...", "...##...", "..#..#..", ".#....#.", "........"),
    "%": ("........", "........", "..#.....", ".###.#..", "..#.###.", "....#...", "........", "........"),
}
_SPR_CACHE = {}
_X2_CACHE = {}


def scale2x(rows):
    """Scale2x/EPX pixel-art doubling on a character sprite (smooth diagonals, no new colours)."""
    c = _X2_CACHE.get(rows)
    if c is not None:
        return c
    h, w = len(rows), len(rows[0])
    px = lambda x, y: rows[min(h - 1, max(0, y))][min(w - 1, max(0, x))]
    out = [[None] * (2 * w) for _ in range(2 * h)]
    for y in range(h):
        for x in range(w):
            P, A, B, C, D = px(x, y), px(x, y - 1), px(x + 1, y), px(x - 1, y), px(x, y + 1)
            e0 = A if C == A and C != D and A != B else P
            e1 = B if A == B and A != C and B != D else P
            e2 = C if D == C and D != B and C != A else P
            e3 = D if B == D and B != A and D != C else P
            out[2 * y][2 * x], out[2 * y][2 * x + 1] = e0, e1
            out[2 * y + 1][2 * x], out[2 * y + 1][2 * x + 1] = e2, e3
    c = _X2_CACHE[rows] = tuple("".join(r) for r in out)
    return c


def spr_rgb(rows):
    """Tile sprite rows -> 4x4 list of RGB tuples (cached)."""
    c = _SPR_CACHE.get(rows)
    if c is None:
        c = _SPR_CACHE[rows] = [[SPAL[ch] for ch in r] for r in rows]
    return c


def _shade(c, k):
    return (min(255, int(c[0] * k)), min(255, int(c[1] * k)), min(255, int(c[2] * k)))


TEX16 = [1.0, 0.94, 1.0, 1.05, 0.97, 1.0, 1.03, 0.95, 1.0, 1.02, 0.96]


def blit(pix, rows, col, tint=None):
    """Draw a creature/item sprite in colour col onto a pixel block; tint overrides clothes, hair and skin."""
    other = FIG_COL
    if tint:
        col = tint["#"]
        other = dict(FIG_COL, h=tint["h"], s=tint["s"])
    lite, dark = _shade(col, 1.35), _shade(col, 0.6)
    n = len(rows)
    # darken the ground right around the figure so it stands out (a soft outline)
    for j, r in enumerate(rows):
        for i, ch in enumerate(r):
            if ch == "." and any(0 <= j + dj < n and 0 <= i + di < n and rows[j + dj][i + di] != "."
                                 for dj, di in ((0, 1), (0, -1), (1, 0), (-1, 0))):
                pix[j][i] = _shade(pix[j][i], 0.45)
    for j, r in enumerate(rows):
        for i, ch in enumerate(r):
            if ch == ".":
                continue
            pix[j][i] = col if ch == "#" else lite if ch == "+" else dark if ch == "-" else other[ch]



def art_lines(key):
    """Returns (lines, default colour, char colour map)."""
    p = pic_for(key)
    if p:
        return [" " * p["w"]] * p["h"], LIGHT, {}
    if key and key not in PORTRAITS and key.rsplit("_", 1)[-1] in CLASSES:
        key = key.rsplit("_", 1)[-1]  # player portrait "elf_wizard" -> ASCII "wizard"
    if key == "dragon":
        return DRAGON, RED, ART_COL["dragon"][1]
    if key == "ashmaw":
        return ASHMAW_HEAD, PORTRAIT_COL["ashmaw"][0], PORTRAIT_COL["ashmaw"][1]
    if key in PORTRAITS:
        fg, pal = PORTRAIT_COL.get(key, (SKIN, {}))
        return _rows(PORTRAITS[key]), fg, pal
    if key in SCENES:
        fg, pal = SCENE_COL.get(key, (LIGHT, {}))
        return _rows(SCENES[key]), fg, pal
    if key == "world":
        return _rows(WORLD_MAP), WORLD_COL[0], WORLD_COL[1]
    return [], LIGHT, {}


# =============================================================================
# Terminal user interface
# =============================================================================
class BotDone(Exception):
    pass


TITLE_FONT = {
    "E": ["#####", "#....", "####.", "#....", "#####"], "M": ["#...#", "##.##", "#.#.#", "#...#", "#...#"],
    "B": ["####.", "#...#", "####.", "#...#", "####."], "R": ["####.", "#...#", "####.", "#..#.", "#...#"],
    "F": ["#####", "#....", "####.", "#....", "#...."], "A": [".###.", "#...#", "#####", "#...#", "#...#"],
    "L": ["#....", "#....", "#....", "#....", "#####"],
}


def title_cols(text, k):
    return len(text) * 6 * k - k


class BackToTitle(Exception):
    pass


class Colors:
    def __init__(self):
        self.ok = curses.has_colors()
        self.pairs = {}
        self.c256 = False
        self.maxp = 0
        if self.ok:
            curses.start_color()
            try:
                curses.use_default_colors()
            except curses.error:
                pass
            self.c256 = curses.COLORS >= 256
            self.maxp = curses.COLOR_PAIRS - 1

    def __call__(self, fg, bg=BLACK, bold=False):
        if not self.ok:
            return curses.A_BOLD if bold else 0
        key = (fg, bg)
        p = self.pairs.get(key)
        if p is None:
            if len(self.pairs) >= self.maxp:
                p = 0
            else:
                p = len(self.pairs) + 1
                f = fg[0] if self.c256 else fg[1]
                b = bg[0] if self.c256 else bg[1]
                try:
                    curses.init_pair(p, f, b)
                except curses.error:
                    p = 0
            self.pairs[key] = p
        a = curses.color_pair(p)
        if bold or (not self.c256 and fg in BRIGHT8):
            a |= curses.A_BOLD
        return a


MOVE_KEYS = {
    curses.KEY_UP: (0, -1), curses.KEY_DOWN: (0, 1), curses.KEY_LEFT: (-1, 0), curses.KEY_RIGHT: (1, 0),
    ord('8'): (0, -1), ord('2'): (0, 1), ord('4'): (-1, 0), ord('6'): (1, 0),
    ord('7'): (-1, -1), ord('9'): (1, -1), ord('1'): (-1, 1), ord('3'): (1, 1),
    ord('y'): (-1, -1), ord('u'): (1, -1), ord('b'): (-1, 1), ord('n'): (1, 1),
    curses.KEY_HOME: (-1, -1), curses.KEY_PPAGE: (1, -1), curses.KEY_END: (-1, 1), curses.KEY_NPAGE: (1, 1),
    getattr(curses, "KEY_A1", -9): (-1, -1), getattr(curses, "KEY_A3", -9): (1, -1),
    getattr(curses, "KEY_C1", -9): (-1, 1), getattr(curses, "KEY_C3", -9): (1, 1),
}
ENTER = (10, 13, curses.KEY_ENTER)
ESC = (27,)
ITEM_GLYPH = {"weapon": ("(", LIGHT), "armor": ("[", STONE), "shield": ("]", STONE), "ring": ("=", GOLD),
              "amulet": ('"', GOLD), "potion": ("!", MAGENTA), "scroll": ("?", BONE), "quest": ("*", YELLOW)}
NAMES = ["Aldric", "Kestrel", "Mira", "Torvin", "Isolde", "Garreth", "Wren", "Rowan", "Sable", "Corin"]


def item_glyph(it):
    if it.startswith("gold:"):
        return "$", GOLD
    return ITEM_GLYPH.get(ITEMS[it]["kind"], ("?", WHITE))


def item_desc(it):
    d = ITEMS[it]
    k = d["kind"]
    if k == "weapon":
        s = "%s %s" % (d["dmg"], d["dtype"])
        if d.get("plus"):
            s += ", +%d" % d["plus"]
        if d.get("extra"):
            s += ", +%s %s" % d["extra"]
        if d.get("ranged"):
            s += ", range %d" % d["ranged"]
        if d.get("finesse"):
            s += ", finesse"
        if d.get("twohand"):
            s += ", two-handed"
        return s
    if k == "armor":
        cap = "" if d["dexcap"] >= 99 else (" (max +%d)" % d["dexcap"] if d["dexcap"] else "")
        return "AC %d%s%s, %s" % (d["ac"], " + DEX" if d["dexcap"] else "", cap, d["cat"] if d["cat"] != "none" else "clothing")
    if k == "shield":
        return "+2 AC"
    if k == "potion":
        return "heals %s" % d["heal"]
    if k == "scroll":
        return "casts %s" % SPELLS[d["spell"]]["name"]
    return d.get("desc", "")


# --- 8x8 figures per class, people and monster ---------------------------------------
# '#' own colour, '+' lighter, '-' darker, '.' transparent; other letters: FIG_COL
FIG_COL = {"s": (228, 186, 146), "e": (245, 240, 220), "0": (172, 178, 190), "9": (110, 116, 128),
           "w": (124, 82, 42), "h": (96, 62, 34), "O": (226, 220, 200), "7": (16, 16, 20), "r": (232, 44, 32),
           "y": (236, 196, 60), "g": (96, 156, 62), "k": (212, 112, 46), "z": (128, 148, 118),
           "p": (200, 226, 255), "W": (226, 226, 234)}
FIG_CLASS = {
    "fighter": ("..0000..", "..0ss0..", "...ss..0", ".9####90", ".s####.w", "..####..", "..-..-..", "..9..9.."),
    "wizard": ("...+#..p", "..+##..w", ".######w", "..ssss.w", ".s####sw", "..####.w", ".######w", ".######."),
    "rogue": ("..----..", ".--ss--.", "..-ss-..", ".+####+.", ".s####s0", "..####..", "..-..-..", "..-..-.."),
    "cleric": ("...hh...", "..hssh..", "...ss...", ".+####+.", ".s#yy#s9", "..####.9", "..####..", "..-..-.."),
}
FIG_NPC = {
    "person": ("...hh...", "..hssh..", "...ss...", ".+####+.", ".s####s.", "..####..", "..-..-..", "..-..-.."),
    "villager": ("..hhhh..", "..hssh..", "..-ss-..", ".+####+.", ".s####s.", "..####..", "..-..-..", "..-..-.."),
    "hobb": ("........", "..ssss..", "..s77s..", ".+####+.", ".s#ww#sy", "..#ww#..", "..-..-..", "..-..-.."),
    "greta": ("..hhhh..", ".hhsshh.", ".h.ss.h9", ".+####99", ".s#ww#.w", "..#ww#..", "..-..-..", "..-..-.."),
    "captain": ("..0000.0", "..0ss0.0", "...ss..w", ".######w", ".s####.w", "..####.w", "..-..-.w", "..-..-.."),
    "aldous": ("...ss...", "..ssss..", "..WWWW..", ".######.", ".s#yy#s.", "..####..", "..####..", ".######."),
    "pell": ("..hhh.y.", "..hssh..", "...ss...", ".+####+.", ".s##ww..", "..##ww..", "..-..-..", "..-..-.."),
    "oswin": ("...hh...", "..hssh..", "..hhhh..", ".+#yy#+.", ".s####s.", "..####..", "..-..-..", "..-..-.."),
    "brannoc": ("........", "........", "0.hhhh.0", ".0hssh0.", "..WWWW..", ".9WWWW9w", ".s####00", "..9..9.."),
    "tamsin": ("..hhhh..", ".hhsshh.", "s.hssh.s", ".h####h.", ".s####s.", "..####..", ".######.", ".######."),
    "maren": ("..hhhh..", ".hhsshh.", "..hssh..", ".h####h.", ".s#yy#s.", "..####..", ".######.", ".######."),
    "lysa": ("........", "........", ".hhhhhh.", ".hhsshh.", "..hssh..", ".+####+.", ".s####s.", "..-..-.."),
}
FIG_MON = {
    "goblin": ("........", "g.gggg.g", ".grggrg.", "..gggg..", ".-####-0", "g.####g0", "..-..-..", ".--..--."),
    "goblin_archer": ("........", "g.gggg.g", ".grggrg.", "w.gggg..", "w-####-.", "w.####g.", "..-..-..", ".--..--."),
    "snagtooth": ("..y.y.y.", "g.yyyy.g", ".grggrg.", "..geeg..", ".-####-0", "g######0", "..-..-..", ".--..--."),
    "kobold": ("........", "..kkk..w", ".kkrkk.w", "..kkkkkw", ".-####-w", "..####.w", "..k..k..", ".k..k.kk"),
    "kobold_slinger": ("........", "..kkk...", ".kkrkk..", "..kkkk.w", ".-####ww", "..####..", "..k..k..", ".k..k.kk"),
    "bandit": ("..----..", ".--ss--.", "..7777..", ".+####+.", ".s####.0", "..####.0", "..-..-..", "..-..-.."),
    "cultist": ("..WWWW..", ".WW77WW.", "..W77W..", ".WWWWWW.", "pWWWWWW.", "p.WWWW..", ".WWWWWW.", ".WWWWWW."),
    "fanatic": ("p.WWWW.p", "s.W77W.s", ".s.77.s.", "..W##W..", ".WW##WW.", ".WWWWWW.", ".WWWWWW.", ".WW..WW."),
    "skeleton": ("..OOOO..", "..O77O..", "...OO.99", ".OOOOO.w", "O.O77O.w", "..OOOO.w", "..O..O..", ".OO..OO."),
    "skeleton_archer": ("..OOOO..", "..O77O..", "w..OO...", "wOOOOOO.", "wO.OO.O.", "w.O77O..", "..O..O..", ".OO..OO."),
    "zombie": ("...zz...", "..z77z..", "..zzzz..", "zz####..", "..####zz", "..####..", "..-..-..", ".--...-."),
    "ghoul": ("..zzzz..", ".zyzzyz.", "..z77z..", ".z####z.", "z.####.z", "7.####.7", "..z..z..", ".zz..zz."),
    "spider": ("-......-", ".-.##.-.", "..####..", "-######-", ".-#rr#-.", "-.####.-", ".-.--.-.", "-......-"),
    "rat": ("........", "........", "........", "......+#", "..-###r#", ".-#####.", "..-..-..", "........"),
    "wolf": ("........", "......+#", "#....+y#", "-######.", ".######.", ".#-..#-.", ".#...#..", "........"),
    "ogre": ("..ssss.w", ".srssrsw", ".seses.w", ".######w", "s######.", "s######.", ".##..##.", ".--..--."),
    "corvane": ("..p.p.p.", "..WWWW..", ".W0000W.", ".W0770W.", ".WWWWWW.", "pWWyyWWp", ".WWWWWW.", ".WWWWWW."),
    "ashmaw": ("+......+", "#+.##.+#", "##+yy+##", "-######-", ".######.", "..####..", ".##..##.", "-#....#-"),
}
_FIG_CACHE = {}


def hero_figure(race, cls):
    """Class figure adjusted for the people: elf ears, short dwarves (bearded) and halflings."""
    key = (race, cls)
    f = _FIG_CACHE.get(key)
    if f:
        return f
    rows = [list(r) for r in FIG_CLASS.get(cls, FIG_NPC["person"])]
    face = next((j for j, r in enumerate(rows) if "s" in r), 1)
    if race == "elf":
        r = rows[face]
        lo, hi = min(i for i, c in enumerate(r) if c == "s"), max(i for i, c in enumerate(r) if c == "s")
        for i in (lo - 1, hi + 1):
            if 0 <= i < 8:
                r[i] = "s"
    if race in ("dwarf", "halfling"):
        rows = [["."] * 8, ["."] * 8] + rows[:5] + rows[7:]
        if race == "dwarf":
            for j in (face + 3, face + 4):
                if j < 8:
                    rows[j][3] = rows[j][4] = "h"
    f = _FIG_CACHE[key] = tuple("".join(r) for r in rows)
    return f


def figure8(a):
    """8x8 figure rows for an actor on the large pixel map."""
    cid = a.cid if a.is_pc else a.npc
    if cid in FIG_NPC:
        return FIG_NPC[cid]
    if a.is_pc:
        return hero_figure(a.race, a.cls)
    if a.tmpl:
        return FIG_MON.get(a.tmpl, FIG_MON["goblin"])
    return FIG_NPC.get(a.npc, FIG_NPC["person"])


def figure_tint(a):
    """Hair, skin and clothing colours sampled from the actor's portrait (or monster picture)."""
    return FIG_TINT.get(a.portrait or "") or FIG_TINT.get(a.tmpl or "") or FIG_TINT.get(a.npc or "")


def actor_family(a):
    """Sprite family for a creature on the pixel map."""
    if a.is_pc or not a.tmpl:
        return "person"
    T = a.T
    if T.get("big") or a.tmpl == "ashmaw":
        return "dragon"
    return {"rat": "rat", "wolf": "beast", "spider": "spider", "ogre": "big"}.get(a.tmpl, "humanoid")


class UI:
    def __init__(self, scr, bot=0, save_path=SAVE_PATH):
        self.scr = scr
        self.C = Colors()
        self.bot, self.frames = bot, 0
        self.save_path = save_path
        self.fx = []
        self.overlay = {}
        self.burst = {}
        self.shake = 0
        self.sel = 0
        self.target_info = None
        self.g = None
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        scr.keypad(True)
        scr.timeout(140)
        self.rng = random.Random(7)
        self.pics, self.shown_pics = [], []
        self.rawmap, self.shown_raw = None, False
        self.pilot, self.watch_speed, self.paused = None, 1.0, False
        self.view_pref = None
        self.mark_attr = self.C((1, K.COLOR_RED), BLACK)  # marks map cells the lit renderer may paint
        global PIC_MODE
        utf = "UTF" in (locale.getpreferredencoding(False) or "").upper()
        if self.C.c256 and utf and not os.environ.get("EMBERFALL_ASCII"):
            PIC_MODE = "true" if os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit") else "256"
        else:
            PIC_MODE = None

    # --- screen updates (curses + pictures) ---------------------------------------
    def erase(self):
        global PIC_MAXH
        self.pics = []
        self.rawmap = None
        PIC_MAXH = self.scr.getmaxyx()[0] - 9
        self.scr.erase()

    def pic_clear(self, y, x, key):
        """True if nothing curses drew (a menu, a message box) lies over the picture's area."""
        p = PICS[key]
        want = self.C(BLACK, BLACK) & curses.A_COLOR
        for j in range(0, p["h"], 2):
            for i in range(0, p["w"], 3):
                try:
                    v = self.scr.inch(y + j, x + i)
                except curses.error:
                    return False
                if (v & curses.A_CHARTEXT) != 32 or (v & curses.A_COLOR) != want:
                    return False
        return True

    def refresh(self):
        pics = [p for p in self.pics if self.pic_clear(*p)]
        if (self.shown_pics and self.shown_pics != pics) or (self.shown_raw and not self.rawmap):
            self.scr.redrawwin()  # wipe direct paint curses does not know about
        self.scr.refresh()
        s = self.raw_map_escapes() if self.rawmap else ""
        if pics:
            s += "".join(pic_escapes(PICS[k], y, x, PIC_MODE == "true") for y, x, k in pics)
        if s:
            try:
                sys.__stdout__.write("\x1b7" + s + "\x1b8")
                sys.__stdout__.flush()
            except (OSError, ValueError):
                pass
        self.shown_pics = pics
        self.shown_raw = bool(self.rawmap)

    # --- primitives -------------------------------------------------------------
    @property
    def H(self):
        return self.scr.getmaxyx()[0]

    @property
    def W(self):
        return self.scr.getmaxyx()[1]

    def put(self, y, x, s, attr=0):
        H, W = self.scr.getmaxyx()
        if y < 0 or y >= H or x >= W:
            return
        if x < 0:
            s = s[-x:]
            x = 0
        s = s[:W - x]
        if y == H - 1 and x + len(s) >= W:
            s = s[:W - x - 1]
        if not s:
            return
        try:
            self.scr.addstr(y, x, s, attr)
        except curses.error:
            pass

    def fill(self, y, x, h, w, attr=0):
        for j in range(h):
            self.put(y + j, x, " " * w, attr)

    def box(self, y, x, h, w, fg=GOLD, title=None, bg=BLACK):
        a = self.C(fg, bg)
        self.fill(y, x, h, w, self.C(LIGHT, bg))
        self.put(y, x, "." + "-" * (w - 2) + ".", a)
        for j in range(1, h - 1):
            self.put(y + j, x, "|", a)
            self.put(y + j, x + w - 1, "|", a)
        self.put(y + h - 1, x, "'" + "-" * (w - 2) + "'", a)
        if title:
            t = "[ %s ]" % title
            self.put(y, x + max(2, (w - len(t)) // 2), t, self.C(YELLOW, bg, True))

    def block_title(self, text, y, k):
        """Block letters drawn with half-block characters (two pixels per cell), centred. Returns rows used."""
        W = self.W
        if PIC_MODE is None:                 # plain ASCII / 8 colours: the classic banner
            b = banner(text)
            cols = [EMBER, ORANGE, AMBER, GOLD, YELLOW]
            for j, l in enumerate(b):
                self.put(y + j, (W - len(l)) // 2, l, self.C(cols[j % len(cols)], BLACK, True))
            return len(b) + 1
        wpx, hpx = title_cols(text, k), 5 * k
        x0 = max(0, (W - wpx) // 2)
        px = {}
        for n, ch in enumerate(text):
            for gy, row in enumerate(TITLE_FONT[ch]):
                for gx, bit in enumerate(row):
                    if bit == "#":
                        for yy in range(k):
                            for xx in range(k):
                                px[(x0 + (n * 6 + gx) * k + xx, gy * k + yy)] = TITLE_GRAD[gy]
        rows = (hpx + 1) // 2
        for r in range(rows):
            for x in range(x0, x0 + wpx):
                top, bot = px.get((x, 2 * r)), px.get((x, 2 * r + 1))
                if top and bot:
                    self.put(y + r, x, "\u2588" if top == bot else "\u2580", self.C(top, bot))
                elif top:
                    self.put(y + r, x, "\u2580", self.C(top, BLACK))
                elif bot:
                    self.put(y + r, x, "\u2584", self.C(bot, BLACK))
        return rows + 1

    def art(self, y, x, key, lines=None, fg=None, pal=None, bg=BLACK, fmt=None):
        p = pic_for(key)
        if p:
            H, W = self.scr.getmaxyx()
            self.fill(y, x, p["h"], p["w"], self.C(BLACK, BLACK))
            if y >= 0 and x >= 0 and y + p["h"] <= H and x + p["w"] <= W:
                self.pics.append((y, x, key))
            return
        if lines is None:
            lines, fg, pal = art_lines(key)
        for j, row in enumerate(lines):
            if fmt:
                row = row.replace("%-17s", fmt)
            self.put_colored(y + j, x, row, fg, pal, bg)

    def put_colored(self, y, x, row, fg, pal, bg=BLACK):
        run, cur = "", None
        cx = x
        for ch in row:
            c = pal.get(ch, fg)
            if c != cur and run:
                self.put(y, cx, run, self.C(cur, bg))
                cx += len(run)
                run = ""
            cur = c
            run += ch
        if run:
            self.put(y, cx, run, self.C(cur, bg))

    def key(self):
        if self.bot:
            self.frames += 1
            if self.frames > self.bot:
                raise BotDone()
            self.refresh()
            r = self.rng.random()
            if r < 0.45:
                return self.rng.choice([curses.KEY_UP, curses.KEY_DOWN, curses.KEY_LEFT, curses.KEY_RIGHT,
                                        ord('7'), ord('9'), ord('1'), ord('3')])
            if r < 0.75:
                return self.rng.choice([10, 10, 10, 27, ord('1'), ord('2'), ord(' '), 9])
            return self.rng.choice([ord(c) for c in "fzpaicjrm?.x "] + [27, 10, curses.KEY_DOWN])
        k = self.scr.getch()
        if k == 27:
            k = self.escape_seq()
        if k == curses.KEY_RESIZE:
            try:
                curses.update_lines_cols()
            except Exception:
                pass
        return k

    def escape_seq(self):
        """Decode raw ESC [ x / ESC O x arrow sequences that curses left undecoded."""
        self.scr.nodelay(True)
        try:
            k2 = self.scr.getch()
            if k2 in (ord('['), ord('O')):
                seq = ""
                for _ in range(4):
                    c = self.scr.getch()
                    if c == -1:
                        break
                    seq += chr(c)
                    if chr(c).isalpha() or c == ord('~'):
                        break
                return {"A": curses.KEY_UP, "B": curses.KEY_DOWN, "C": curses.KEY_RIGHT, "D": curses.KEY_LEFT,
                        "H": curses.KEY_HOME, "F": curses.KEY_END, "1~": curses.KEY_HOME, "4~": curses.KEY_END,
                        "5~": curses.KEY_PPAGE, "6~": curses.KEY_NPAGE, "Z": curses.KEY_BTAB}.get(seq, -1)
            if k2 != -1:
                curses.ungetch(k2)
            return 27
        finally:
            self.scr.nodelay(False)
            self.scr.timeout(140)

    def wait_key(self):
        if self.pilot:
            self.watch_pause(1.2)
            return 10
        while True:
            k = self.key()
            if k != -1 and k != curses.KEY_RESIZE:
                return k

    # --- watch mode: the autopilot plays, the viewer can pause, speed up or stop --------------
    def watch_pause(self, secs):
        """Wait about secs (scaled by speed) while handling the viewer's keys."""
        if self.bot:
            self.frames += 1
            if self.frames > self.bot:
                raise BotDone()
            return
        end = time.time() + secs / self.watch_speed
        self.scr.timeout(30)
        try:
            while self.paused or time.time() < end:
                k = self.scr.getch()
                if k in (27, ord('q'), ord('Q')):
                    raise BackToTitle()
                if k == ord(' '):
                    self.paused = not self.paused
                    self.watch_status()
                elif k in (ord('+'), ord('=')):
                    self.watch_speed = min(8.0, self.watch_speed * 1.5)
                    self.watch_status()
                elif k in (ord('-'), ord('_')):
                    self.watch_speed = max(0.25, self.watch_speed / 1.5)
                    self.watch_status()
                elif k in (ord('v'), ord('V')) and self.g and self.g.area:
                    modes = self.view_modes()
                    cur = self.view_mode(self.W - SIDE_W, self.H - 1 - LOG_H)
                    self.view_pref = modes[(modes.index(cur) + 1) % len(modes)]
                    self.draw_main(self.g, refresh=False)
                    self.watch_status()
        finally:
            self.scr.timeout(140)

    def watch_status(self):
        H, W = self.scr.getmaxyx()
        goal = self.pilot.goal if self.pilot else ""
        txt = " AUTOPILOT: %s   %s  speed x%.1f   [Space] pause  [+/-] speed  [v] view  [Esc] stop " % (
            goal, "PAUSED" if self.paused else "", self.watch_speed)
        self.put(0, max(0, W - len(txt) - 1), txt[:W - 1], self.C(BLACK, AMBER))
        self.refresh()

    def watch(self, g):
        """Let the autopilot play this game while the viewer watches."""
        self.g = g
        pilot = self.pilot
        pilot.setup(g)
        while True:
            if g.pending:
                self.handle_pending(g)
                pilot.setup(g)
                continue
            self.draw_main(g, refresh=False)
            self.watch_status()
            if g.combat:
                self.watch_pause(0.28)
                g.step_ai()
            else:
                self.watch_pause(0.06)
                pilot.step(g)
            self.animate(g)

    def nap(self, t):
        if not self.bot:
            self.refresh()
            time.sleep(t)

    def too_small(self):
        H, W = self.scr.getmaxyx()
        if W >= MIN_W and H >= MIN_H:
            return False
        self.erase()
        msg = "Please enlarge the terminal to at least %dx%d (now %dx%d)." % (MIN_W, MIN_H, W, H)
        self.put(H // 2, max(0, (W - len(msg)) // 2), msg, self.C(YELLOW))
        self.refresh()
        return True

    # --- map rendering -------------------------------------------------------------
    def tile_look(self, A, x, y, t, lit):
        T = TILES[t]
        h = (x * 73856093 ^ y * 19349663) & 0xffff
        f = (self.frames // 2) if T.anim else 0
        if T.anim:
            f = int(time.time() * 4) + (h & 7)
        ch = T.glyphs[(h + f) % len(T.glyphs)]
        fg = T.fgs[((h >> 4) + f) % len(T.fgs)]
        bg = T.bg
        if not lit:
            return ch, (238, K.COLOR_BLACK), BLACK
        if self.g.night and A.kind in ("town", "forest") and t in (T_GRASS, T_ROAD, T_TREE, T_FLOWER, T_CROPS, T_BUSH, T_MUSH):
            bg = {GRASSBG: (234, K.COLOR_BLACK), DWOOD: (235, K.COLOR_BLACK)}.get(bg, bg)
        return ch, fg, bg

    def view_modes(self):
        return (["narrow", "square"] if PIC_MODE else ["narrow"]) + (["sprite", "large", "huge"] if PIC_MODE == "true" else [])

    def view_mode(self, vw, vh):
        """'narrow' (1 column per tile), 'square' (2 columns) or 'sprite' (4x4 pixel tiles)."""
        modes = self.view_modes()
        if self.view_pref in modes:
            return self.view_pref
        if "huge" in modes and vw // 16 >= 16 and vh // 8 >= 9:
            return "huge"
        if "large" in modes and vw // 8 >= 18 and vh // 4 >= 10:
            return "large"
        if "sprite" in modes and vw // 4 >= 22 and vh // 2 >= 13:
            return "sprite"
        if "square" in modes and vw // 2 >= 44:
            return "square"
        return "narrow"

    def wall_glyphs(self, A):
        """Per-area cache: connected box-drawing glyphs for built walls and fences."""
        c = getattr(A, "_ui_walls", None)
        if c is not None:
            return c
        c = {}
        W, H = A.w, A.h
        tl = A.tiles

        def t_at(x, y):
            return tl[y][x] if 0 <= x < W and 0 <= y < H else None

        def edge(x, y, solid):
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    t = t_at(x + dx, y + dy)
                    if t is not None and t not in solid:
                        return True
            return False
        for y in range(H):
            for x in range(W):
                t = tl[y][x]
                if t == T_WALL:
                    if not edge(x, y, (T_WALL,)):
                        c[(x, y)] = (" ", " ")
                        continue
                    m = 0
                    for bit, (dx, dy) in ((1, (0, -1)), (2, (1, 0)), (4, (0, 1)), (8, (-1, 0))):
                        n = t_at(x + dx, y + dy)
                        if n in WALL_JOIN and (n != T_WALL or edge(x + dx, y + dy, (T_WALL,))):
                            m |= bit
                    c[(x, y)] = (BOX_WALL[m], "═" if m & 2 else " ")
                elif t == T_CWALL:
                    if not edge(x, y, (T_CWALL, T_ORE, T_ROCK)):
                        c[(x, y)] = (" ", " ")
                    else:
                        h = (x * 7 + y * 13) % 5
                        c[(x, y)] = ("▓" if h else "▒", "▓" if h != 2 else "▒")
                elif t == T_FENCE:
                    ns = t_at(x, y - 1) == T_FENCE or t_at(x, y + 1) == T_FENCE
                    ew = t_at(x - 1, y) == T_FENCE or t_at(x + 1, y) == T_FENCE
                    g1 = "┼" if ns and ew else "─" if ew else "│"
                    c[(x, y)] = (g1, "─" if t_at(x + 1, y) == T_FENCE else " ")
        A._ui_walls = c
        return c

    def light_sources(self, A):
        s = getattr(A, "_ui_lights", None)
        if s is None:
            s = [(x, y) + LIGHT_SRC[t] for y, row in enumerate(A.tiles) for x, t in enumerate(row) if t in LIGHT_SRC]
            A._ui_lights = s
        return s

    def light_map(self, g, A, vis, x0, y0, x1, y1):
        """RGB light multipliers for visible cells inside the viewport."""
        outdoor = A.kind in ("town", "forest")
        if outdoor and not g.night:
            return None  # daylight: everything at full colour
        amb = (0.22, 0.25, 0.36) if outdoor else (0.10, 0.10, 0.13)
        tint = (0.80, 0.88, 1.05) if outdoor else (1.12, 0.98, 0.76)
        r = g.light_radius() + 1.0
        pcs = [(p.x, p.y) for p in g.party if not p.dead]
        L = {}
        for p in vis:
            x, y = p
            if not (x0 <= x < x1 and y0 <= y < y1):
                continue
            d2 = min((x - a) ** 2 + (y - b) ** 2 for a, b in pcs) if pcs else 999
            f = max(0.0, 1.0 - (d2 / (r * r)) ** 1.5)  # flat inside, soft edge
            L[p] = [amb[0] + tint[0] * f, amb[1] + tint[1] * f, amb[2] + tint[2] * f, 0.0, 0.0, 0.0]
        now = time.time()
        for (sx, sy, col, rad, speed) in self.light_sources(A):
            if not (x0 - rad <= sx < x1 + rad and y0 - rad <= sy < y1 + rad):
                continue
            fl = 0.82 + 0.18 * math.sin(now * speed + sx * 1.7 + sy * 2.3)
            for yy in range(sy - rad, sy + rad + 1):
                for xx in range(sx - rad, sx + rad + 1):
                    c = L.get((xx, yy))
                    if c is None:
                        continue
                    d = math.hypot(xx - sx, yy - sy)
                    if d > rad:
                        continue
                    f = (1.0 - d / (rad + 0.5)) ** 1.6 * fl
                    c[0] += col[0] * f * 0.6
                    c[1] += col[1] * f * 0.6
                    c[2] += col[2] * f * 0.6
                    c[3] += col[0] * f  # additive glow, so light pools show on dark stone
                    c[4] += col[1] * f
                    c[5] += col[2] * f
        return L

    def draw_map(self, g, x0, y0, vw, vh):
        A = g.area
        mode_v = self.view_mode(vw, vh)
        sprite = mode_v in ("sprite", "large", "huge")
        px = {"large": 8, "huge": 16}.get(mode_v, 4)
        cw = px if sprite else 2 if mode_v == "square" else 1
        mw = vw // cw
        mh = vh // (px // 2) if sprite else vh
        uni = PIC_MODE is not None
        raw = PIC_MODE == "true"
        cur = g.current()
        focus = g.leader if not g.leader.dead else next((p for p in g.party if not p.dead), g.leader)
        if cur and (cur.is_pc or g.sees(cur)):
            focus = cur
        if self.target_info:
            t = self.target_info["targets"][self.target_info["idx"]]
            focus = t if cheb(t.x, t.y, focus.x, focus.y) > min(mw // 2, mh) - 3 else focus
        if A.w <= mw:
            cx, ox = 0, (mw - A.w) // 2
        else:
            cx, ox = clamp(focus.x - mw // 2, 0, A.w - mw), 0
        if A.h <= mh:
            cy, oy = 0, (mh - A.h) // 2
        else:
            cy, oy = clamp(focus.y - mh // 2, 0, A.h - mh), 0
        if self.shake:
            ox += self.rng.choice((-1, 1))
            self.shake -= 1
        vis = g.visible
        over = {}
        for (p, it) in A.items.items():
            if it and p in vis:
                over[p] = item_glyph(it[-1]) + (None,)
        for p, tr in A.traps.items():
            if not tr["hidden"] and p in vis:
                over[p] = ("^", RED, None)
        for p, (ch, ci) in A.decals.items():
            if p in vis and p not in over and TILES[A.tile(*p)].walk:
                over[p] = (ch, DECAL_COLS[ci], None)
        blink = int(time.time() * 3) % 2 == 0
        fam = {}
        for a in A.actors:
            if (a.x, a.y) in vis and (a.conscious):
                fam[(a.x, a.y)] = (actor_family(a), a)
                bg = None
                if "asleep" in a.status:
                    bg = PLUM
                elif "paralyzed" in a.status:
                    bg = NAVY
                elif "frightened" in a.status:
                    bg = (58, K.COLOR_YELLOW)
                if a.tmpl and a.T.get("big"):
                    bg = DRED if blink else (52, K.COLOR_RED)
                over[(a.x, a.y)] = (a.ch, a.fg, bg)
        for p in g.party:
            if p.dead:
                continue
            fam[(p.x, p.y)] = ("downed" if p.downed else "person", p)
            if p.downed:
                over[(p.x, p.y)] = ("%", p.fg, DRED)
            else:
                bg = None
                if "asleep" in p.status:
                    bg = PLUM
                elif "paralyzed" in p.status:
                    bg = NAVY
                over[(p.x, p.y)] = ("@", p.fg, bg)
        if cur and (cur.is_pc or g.sees(cur)) and (cur.conscious or cur.downed):
            ch, fg, bg = over.get((cur.x, cur.y), ("@", WHITE, None))
            over[(cur.x, cur.y)] = (ch, fg, (94, K.COLOR_YELLOW) if blink else (58, K.COLOR_YELLOW))
        ti = self.target_info
        if ti:
            t = ti["targets"][ti["idx"]]
            src = ti["src"]
            for cell in ti.get("area", []):
                ch_, fg_, bg_ = over.get(cell, (None, None, None))
                over[cell] = (ch_, fg_, (52, K.COLOR_RED))
            for p in line(src.x, src.y, t.x, t.y)[1:-1]:
                if p not in over:
                    over[p] = ("*", YELLOW, None)
            ch, fg, _ = over.get((t.x, t.y), (t.ch, t.fg, None))
            over[(t.x, t.y)] = (ch, BLACK if blink else WHITE, RED if ti["enemy"] else GREEN)
        for p, v in self.overlay.items():
            over[p] = v
        walls = self.wall_glyphs(A) if uni else {}
        light = self.light_map(g, A, vis, cx - ox, cy - oy, cx - ox + mw, cy - oy + mh) if raw else None
        if sprite:
            return self.draw_sprites(g, A, x0, y0, vw, vh, cx, cy, ox, oy, mw, mh, vis, over, fam, light, px)
        # one entry per screen column: [ch, fg, bg, mode, light]; mode: 0 lit, 1 memory, 2 dark, 3 ui/actor
        rows = []
        for sy in range(vh):
            y = cy + sy - oy
            row = []
            for sx in range(mw):
                x = cx + sx - ox
                if not A.inb(x, y):
                    row += [[" ", BLACK, BLACK, 2, None]] * cw
                    continue
                p = (x, y)
                lit = p in vis
                if not (lit or A.explored[y][x]):
                    row += [[" ", BLACK, BLACK, 2, None]] * cw
                    continue
                t = A.tiles[y][x]
                ch, fg, bg = self.tile_look(A, x, y, t, lit or raw)
                c2 = " "
                if uni:
                    wg = walls.get(p)
                    if wg:
                        ch, c2 = wg
                        if cw == 2 and t == T_WALL and ch != " ":
                            ch = c2 = "\u2588"  # lines cannot be centred in a 2-column cell: solid masonry
                    else:
                        ch = UNI_TILE.get(t, ch).translate(UNI_TR) if t in UNI_TILE or t in UNI_ANIM else ch
                        if t in WIDE_FILL:
                            c2 = ch
                elif t in WIDE_FILL or t in (T_WALL, T_CWALL):
                    c2 = ch
                mode = 0 if lit else 1
                if lit and p in self.burst:
                    bg, mode = self.burst[p], 3
                o = over.get(p) if lit else None
                if o:
                    if o[0]:
                        ch, fg, c2 = o[0], o[1], " "
                    if o[2]:
                        bg, mode = o[2], 3
                    elif o[0]:
                        mode = 4  # actor/item on lit ground: keep it readable
                lv = light.get(p) if light is not None and lit else None
                row.append([ch, fg, bg, mode, lv])
                if cw == 2:
                    row.append([c2, fg, bg, mode, lv])
            rows.append(row)
        # floating combat text
        now = time.time()
        self.fx = [f for f in self.fx if f[4] > now]
        for (fx_, fy_, text, col, until) in self.fx:
            age = 1.0 - (until - now)
            sy = fy_ - 1 - int(age * 2) - cy + oy
            sx = (fx_ - cx + ox) * cw + (cw // 2) - len(text) // 2
            if 0 <= sy < vh and 0 <= sx and sx + len(text) < len(rows[sy]):
                for i, chx in enumerate(text):
                    rows[sy][sx + i] = [chx, col, BLACK, 5, None]
        if raw:
            out = []
            for row in rows:
                cells = []
                for ch, fg, bg, mode, lv in row:
                    f, b = rgb_of(fg), rgb_of(bg)
                    if mode == 1:
                        f, b = memory_rgb(f, 0.55), memory_rgb(b, 0.45)
                    elif mode in (0, 4) and lv is not None:
                        lf = lv if mode == 0 else [max(0.9, v) for v in lv[:3]] + lv[3:]
                        f = (min(255, int(f[0] * lf[0] + lf[3] * 40)), min(255, int(f[1] * lf[1] + lf[4] * 40)),
                             min(255, int(f[2] * lf[2] + lf[5] * 40)))
                        b = (min(255, int(b[0] * lv[0] + lv[3] * 55)), min(255, int(b[1] * lv[1] + lv[4] * 55)),
                             min(255, int(b[2] * lv[2] + lv[5] * 55)))
                    elif mode == 5:
                        b = (0, 0, 0)
                    cells.append((ch, f, b))
                out.append(cells)
            self.rawmap = (y0, x0, out)
            for sy in range(vh):
                self.put(y0 + sy, x0, " " * len(rows[sy]), self.mark_attr)
            return
        for sy, row in enumerate(rows):
            run, cattr, sx0 = "", None, 0
            for sx, (ch, fg, bg, mode, lv) in enumerate(row):
                attr = self.C(fg, bg, mode == 5)
                if attr != cattr and run:
                    self.put(y0 + sy, x0 + sx0, run, cattr)
                    run, sx0 = "", sx
                if not run:
                    sx0 = sx
                cattr = attr
                run += ch
            if run:
                self.put(y0 + sy, x0 + sx0, run, cattr)

    def tile_sprite(self, A, x, y, t, fr, n=4):
        if n == 16:
            return scale2x(self.tile_sprite(A, x, y, t, fr, 8))
        h = (x * 73856093 ^ y * 19349663) & 0xffff
        big = n == 8
        if t in (T_WALL, T_CWALL, T_ORE):
            below = A.tiles[y + 1][x] if y + 1 < A.h else T_WALL
            face = below not in SOLID_TILES
            if t == T_ORE:
                return (SPR8_ORE if big else SPR_ORE)[0] if face else (SPR8_CWALL_TOP if big else SPR_CWALL_TOP)[0]
            if t == T_WALL:
                v = (SPR8_WALL_FACE if big else SPR_WALL_FACE) if face else (SPR8_WALL_TOP if big else SPR_WALL_TOP)
            else:
                v = (SPR8_CWALL_FACE if big else SPR_CWALL_FACE) if face else (SPR8_CWALL_TOP if big else SPR_CWALL_TOP)
            return v[h % len(v)]
        sp = (SPRITES8 if big else SPRITES).get(t)
        if sp is None:
            return (SPR8_WALL_TOP if big else SPR_WALL_TOP)[0]
        if sp[0] == "anim":
            fs = sp[1]
            return fs[(fr + (h & 3)) % len(fs)]
        return sp[h % len(sp)]

    def draw_sprites(self, g, A, x0, y0, vw, vh, cx, cy, ox, oy, mw, mh, vis, over, fam, light, n=4):
        """Pixel-tile map: every tile is an n x n sprite (n columns x n/2 rows of half blocks)."""
        now = time.time()
        fr = int(now * 3)
        black = (0, 0, 0)
        W = mw * n
        prow = [[black] * W for _ in range(mh * n)]
        for ty in range(mh):
            y = cy + ty - oy
            for tx in range(mw):
                x = cx + tx - ox
                if not A.inb(x, y):
                    continue
                p = (x, y)
                lit = p in vis
                if not (lit or A.explored[y][x]):
                    continue
                pix = [list(r) for r in spr_rgb(self.tile_sprite(A, x, y, A.tiles[y][x], fr, n))]
                if n == 16:
                    pix = [[_shade(c, TEX16[(x * 7 + j * 5 + y * 11 + i * 3) % len(TEX16)]) for i, c in enumerate(r)]
                           for j, r in enumerate(pix)]
                o = over.get(p) if lit else None
                tint = self.burst.get(p) if lit else None
                f = fam.get(p) if o else None
                if o:
                    if o[2]:
                        tint = o[2]
                    if f:
                        if n >= 8:
                            rows8 = ACTOR8["downed"] if f[0] == "downed" else figure8(f[1])
                            blit(pix, scale2x(rows8) if n == 16 else rows8, rgb_of(o[1]), figure_tint(f[1]))
                        else:
                            blit(pix, ACTOR_SPR[f[0]], rgb_of(o[1]))
                    elif o[0]:
                        items = ITEM8 if n >= 8 else ITEM_SPR
                        rows_i = items.get(o[0], items["*"])
                        blit(pix, scale2x(rows_i) if n == 16 else rows_i, rgb_of(o[1]))
                if tint:
                    tc = rgb_of(tint)
                    pix = [[((c[0] + tc[0]) // 2, (c[1] + tc[1]) // 2, (c[2] + tc[2]) // 2) for c in r] for r in pix]
                if not lit:
                    pix = [[memory_rgb(c, 0.5) for c in r] for r in pix]
                elif light is not None:
                    lv = light.get(p)
                    if lv is not None:
                        m0, m1, m2 = lv[0], lv[1], lv[2]
                        a0, a1, a2 = lv[3] * 45, lv[4] * 45, lv[5] * 45
                        if f:  # keep creatures readable at the edge of the light
                            m0, m1, m2 = max(m0, 0.85), max(m1, 0.85), max(m2, 0.85)
                        pix = [[(min(255, int(c[0] * m0 + a0)), min(255, int(c[1] * m1 + a1)),
                                 min(255, int(c[2] * m2 + a2))) for c in r] for r in pix]
                for j in range(n):
                    prow[ty * n + j][tx * n:tx * n + n] = pix[j]
        rows = []
        for j in range(0, mh * n, 2):
            top, bot = prow[j], prow[j + 1]
            rows.append([["\u2580", top[i], bot[i]] for i in range(W)])
        self.fx = [f for f in self.fx if f[4] > now]
        for (fx_, fy_, text, col, until) in self.fx:
            age = 1.0 - (until - now)
            ry = (fy_ - cy + oy) * (n // 2) - int(age * 2)
            rx = (fx_ - cx + ox) * n + n // 2 - len(text) // 2
            if 0 <= ry < len(rows) and 0 <= rx and rx + len(text) < W:
                for i, chx in enumerate(text):
                    rows[ry][rx + i] = [chx, rgb_of(col), black]
        self.rawmap = (y0, x0, [[tuple(c) for c in r] for r in rows])
        for sy in range(vh):
            self.put(y0 + sy, x0, " " * vw, self.mark_attr)

    def raw_map_escapes(self):
        """Paint the lit map straight to the terminal, skipping cells curses has drawn over."""
        y0, x0, rows = self.rawmap
        want = self.mark_attr & curses.A_COLOR
        out = []
        for j, row in enumerate(rows):
            y = y0 + j
            pending_move = True
            last = None
            for i, (ch, f, b) in enumerate(row):
                try:
                    v = self.scr.inch(y, x0 + i)
                except curses.error:
                    v = 0
                if (v & curses.A_CHARTEXT) != 32 or (v & curses.A_COLOR) != want:
                    pending_move = True
                    continue
                if pending_move:
                    out.append("\x1b[%d;%dH" % (y + 1, x0 + i + 1))
                    pending_move = False
                sgr = (f, b)
                if sgr != last:
                    out.append("\x1b[0;38;2;%d;%d;%d;48;2;%d;%d;%dm" % (f + b))
                    last = sgr
                out.append(ch)
        out.append("\x1b[0m")
        return "".join(out)

    # --- main screen ------------------------------------------------------------------
    def draw_main(self, g, refresh=True):
        self.g = g
        if self.too_small():
            return
        H, W = self.scr.getmaxyx()
        self.erase()
        vw, vh = W - SIDE_W, H - 1 - LOG_H
        self.draw_top(g, W)
        self.draw_map(g, 0, 1, vw, vh)
        self.draw_side(g, vw, 1, SIDE_W, vh)
        self.draw_log(g, H - LOG_H, W)
        if refresh:
            self.refresh()

    def draw_top(self, g, W):
        a = self.C(LIGHT, (235, K.COLOR_BLACK))
        self.put(0, 0, " " * W, a)
        self.put(0, 1, "EMBERFALL", self.C(EMBER, (235, K.COLOR_BLACK), True))
        tod = "night" if g.night else ("morning" if (g.minutes % 1440) < 12 * 60 else "evening" if (g.minutes % 1440) >= 18 * 60 else "afternoon")
        s = "  %s   Day %d, %s (%s)   Gold %d" % (g.area.name, g.day, g.clock, tod, g.gold)
        self.put(0, 11, s, a)
        if g.combat:
            t = " COMBAT - Round %d " % g.combat["round"]
            self.put(0, W - len(t) - 1, t, self.C(WHITE, DRED, True))

    def hpbar(self, p, w):
        if p.max_hp <= 0:
            return "", GRAY
        f = clamp(int(round(w * max(0, p.hp) / p.max_hp)), 0, w)
        r = p.hp / p.max_hp
        col = LGREEN if r > 0.6 else (YELLOW if r > 0.3 else RED)
        return "#" * f + "-" * (w - f), col

    def draw_side(self, g, x, y, w, h):
        bg = (233, K.COLOR_BLACK)
        self.fill(y, x, h, w, self.C(LIGHT, bg))
        for j in range(h):
            self.put(y + j, x, "|", self.C(DGRAY, bg))
        cy = y
        cur = g.current()
        for i, p in enumerate(g.party):
            mark = ">" if (p is cur) else (" " if not (i == self.sel and not g.combat) else "*")
            name = p.name if len(p.name) <= 18 else p.name[:17] + "."
            col = p.fg if not p.dead else DGRAY
            self.put(cy, x + 2, "%s%d %-18s" % (mark, i + 1, name), self.C(col, bg, p is cur))
            self.put(cy, x + w - 7, "%s %d" % (CLASSES[p.cls]["short"], p.level), self.C(GRAY, bg))
            cy += 1
            if p.dead:
                self.put(cy, x + 4, "DEAD - raise at the temple", self.C(RED, bg))
                cy += 3
                continue
            bar, bc = self.hpbar(p, 14)
            self.put(cy, x + 4, "HP", self.C(GRAY, bg))
            self.put(cy, x + 7, bar, self.C(bc, bg))
            self.put(cy, x + 22, "%3d/%-3d" % (max(0, p.hp), p.max_hp), self.C(LIGHT, bg))
            cy += 1
            info = "AC %d" % p.ac
            if p.can_cast:
                sl = " ".join("%s:%d" % (k, v[0]) for k, v in sorted(p.slots.items()))
                info += "  Slots " + sl
            if p.ai:
                info += "  [AI]"
            self.put(cy, x + 4, info[:w - 5], self.C(GRAY, bg))
            cy += 1
            st = []
            if p.downed:
                st.append("DOWN %d/%d" % tuple(p.dsaves))
            for s in p.status:
                st.append(s.capitalize())
            if g.combat and p is cur:
                st.append("Move %d%s" % (p.mp, "" if not p.acted else "  acted"))
            self.put(cy, x + 4, ("  ".join(st))[:w - 5], self.C(PURPLE if st else GRAY, bg))
            cy += 1
        cy += 1
        if g.combat:
            self.put(cy, x + 2, "-- Initiative, round %d --" % g.combat["round"], self.C(YELLOW, bg))
            cy += 1
            order = g.combat["order"]
            idx = g.combat["idx"]
            seq = order[idx:] + order[:idx]
            for a in seq:
                if cy >= y + h:
                    break
                if a.dead or not (a.is_pc or a in g.area.actors) or not (a.conscious or a.downed):
                    continue
                if not a.is_pc and not g.sees(a):
                    continue
                col = a.fg if a.is_pc else (RED if a.faction == "hostile" else LIGHT)
                nm = a.name[:16]
                self.put(cy, x + 2, ("> " if a is cur else "  ") + nm, self.C(col, bg, a is cur))
                if not a.is_pc:
                    bar, bc = self.hpbar(a, 8)
                    self.put(cy, x + 21, bar, self.C(bc, bg))
                cy += 1
        else:
            lines = ["Walk into people to talk,", "into foes to fight.", "", "i inventory  c character",
                     "j journal    z cast spell", "r rest       m message log", "S save       ? help"]
            if g.area.kind != "town":
                lines[0:2] = ["Exits: > stairs or the", "yellow > at a map edge."]
            for l in lines:
                if cy >= y + h:
                    break
                self.put(cy, x + 2, l, self.C(DGRAY, bg))
                cy += 1

    def draw_log(self, g, y, W):
        self.put(y, 0, "-" * W, self.C(DGRAY))
        self.put(y, 2, " Log ", self.C(GRAY))
        if g.combat:
            hint = " arrows/numpad move  f attack  z spell  p potion  a auto  Space end turn "
        else:
            hint = " arrows/numpad/yubn move  i c j z r  S save  ? help  Q quit "
        self.put(y, max(8, W - len(hint) - 2), hint, self.C(GRAY))
        lines = []
        for text, col in list(g.log)[-(LOG_H + 4):]:
            for l in wrap(text, W - 3):
                lines.append((l, col))
        lines = lines[-(LOG_H - 1):]
        for i, (l, col) in enumerate(lines):
            self.put(y + 1 + i, 1, l, self.C(col))

    # --- animation ----------------------------------------------------------------------
    def animate(self, g):
        ev, g.events = g.events, []
        for e in ev:
            if e[0] == "text":
                _, x, y, text, col = e
                self.fx.append((x, y, text, col, time.time() + 0.9))
            elif e[0] == "shake":
                self.shake = 8
        if self.bot:
            return
        for e in ev:
            if e[0] == "bolt":
                _, path, ch, col = e
                for p in path[1:-1]:
                    if p not in g.visible:
                        continue
                    self.overlay = {p: (ch, col, None)}
                    self.draw_main(g)
                    time.sleep(0.018)
                self.overlay = {}
            elif e[0] == "burst":
                _, cells, col = e
                bgc = {RED: DRED, ORANGE: (166, K.COLOR_RED), PALE: (24, K.COLOR_BLUE), PURPLE: PLUM,
                       LGREEN: (22, K.COLOR_GREEN), GOLD: (94, K.COLOR_YELLOW), CYAN: (24, K.COLOR_BLUE),
                       YELLOW: (94, K.COLOR_YELLOW), MAGENTA: PLUM}.get(col, DRED)
                self.burst = {p: bgc for p in cells}
                self.draw_main(g)
                time.sleep(0.16)
                self.burst = {}
        if any(e[0] in ("text", "shake") for e in ev):
            for _ in range(3):
                self.draw_main(g)
                time.sleep(0.05)

    # --- generic modals --------------------------------------------------------------------
    def menu(self, title, items, art=None, footer=None, sel=0, width=None, detail=None):
        """items: [(label, value, enabled)] -> value or None."""
        if not items:
            return None
        while True:
            if self.g:
                self.draw_main(self.g, refresh=False)
            H, W = self.scr.getmaxyx()
            alines = art_lines(art)[0] if art else []
            w = width or min(W - 4, max(44, max(len(i[0]) for i in items) + 8, max([len(l) for l in alines] + [0]) + 4))
            dl = wrap(detail(items[sel][1]), w - 4) if detail else []
            h = min(H - 2, len(items) + 4 + len(alines) + (len(dl) + 1 if dl else 0) + (1 if footer else 0))
            y, x = max(0, (H - h) // 2), max(0, (W - w) // 2)
            self.box(y, x, h, w, GOLD, title)
            cy = y + 1
            if alines:
                self.art(cy, x + (w - max(len(l) for l in alines)) // 2, art)
                cy += len(alines) + 1
            room = y + h - 1 - cy - (len(dl) + 1 if dl else 0) - (1 if footer else 0)
            top = clamp(sel - room + 1, 0, max(0, len(items) - room))
            for i in range(top, min(len(items), top + room)):
                lab, val, en = items[i]
                a = self.C(BLACK, GOLD) if i == sel else self.C(LIGHT if en else DGRAY)
                self.put(cy, x + 2, (" %-*s" % (w - 5, lab))[:w - 4], a)
                cy += 1
            if dl:
                cy += 1
                for l in dl:
                    self.put(cy, x + 2, l, self.C(GRAY))
                    cy += 1
            if footer:
                self.put(y + h - 2, x + 2, footer[:w - 4], self.C(DGRAY))
            self.refresh()
            k = self.wait_key()
            if k in (curses.KEY_UP, ord('8'), ord('k')):
                sel = (sel - 1) % len(items)
            elif k in (curses.KEY_DOWN, ord('2'), 9, ord('j')):
                sel = (sel + 1) % len(items)
            elif k in ENTER or k == ord(' '):
                if items[sel][2]:
                    return items[sel][1]
            elif k in ESC or k == ord('q'):
                return None

    def message(self, title, text, art=None, fmt=None, col=LIGHT):
        while True:
            if self.g and self.g.area:
                self.draw_main(self.g, refresh=False)
            else:
                self.erase()
            H, W = self.scr.getmaxyx()
            alines = art_lines(art)[0] if art else []
            aw = max([len(l) for l in alines] + [0])
            w = min(W - 4, max(60, aw + 6))
            tl = wrap(text, w - 6)
            h = min(H - 2, len(tl) + len(alines) + 5 + (1 if alines else 0))
            y, x = max(0, (H - h) // 2), max(0, (W - w) // 2)
            self.box(y, x, h, w, GOLD, title)
            cy = y + 2
            if alines:
                self.art(cy, x + (w - aw) // 2, art, fmt=fmt)
                cy += len(alines) + 1
            for l in tl:
                if cy >= y + h - 2:
                    break
                self.put(cy, x + 3, l, self.C(col))
                cy += 1
            self.put(y + h - 2, x + w - 22, "[Enter] continue", self.C(DGRAY))
            self.refresh()
            k = self.wait_key()
            if k in ENTER or k in ESC or k == ord(' '):
                return

    def text_input(self, title, prompt, default=""):
        s = default
        while True:
            self.erase()
            H, W = self.scr.getmaxyx()
            w, h = 50, 7
            y, x = (H - h) // 2, (W - w) // 2
            self.box(y, x, h, w, GOLD, title)
            self.put(y + 2, x + 3, prompt, self.C(LIGHT))
            self.put(y + 4, x + 3, "> " + s + "_", self.C(YELLOW, BLACK, True))
            self.refresh()
            k = self.wait_key()
            if k in ENTER:
                if s.strip():
                    return s.strip()
            elif k in ESC:
                return None
            elif k in (curses.KEY_BACKSPACE, 127, 8):
                s = s[:-1]
            elif 32 <= k < 127 and len(s) < 16:
                s += chr(k)
            if self.bot and self.frames % 3 == 0:
                return s or "Bot"

    # --- pending queue ---------------------------------------------------------------------
    def handle_pending(self, g):
        p = g.pending.popleft()
        kind = p[0]
        if kind == "talk":
            self.dialogue(g, p[1], p[2] if len(p) > 2 else None)
            g.update_fov()
            g.check_hostiles()
        elif kind == "scene":
            title, text = SCENE_TEXT.get(p[1], ("", ""))
            self.message(title, text, p[1])
        elif kind == "message":
            self.message(p[1], p[2], p[3] if len(p) > 3 else None)
        elif kind == "levelup":
            self.message("Level up!", "%s has reached level %d!\n\n%s" % (p[1], p[2], "\n".join("  * " + x for x in p[3])),
                         "levelup", col=YELLOW)
        elif kind == "world":
            self.world_map(g)
        elif kind == "shop":
            self.shop(g)
        elif kind == "gameover":
            self.gameover(g)
        elif kind == "victory":
            self.victory(g)

    # --- dialogue ------------------------------------------------------------------------------
    def dialogue(self, g, npc, name=None):
        node = "start"
        sel = 0
        while node:
            if npc == "villager":
                spk, port, nodes = dlg_villager(g, name or "Villager")
            else:
                spk, port, nodes = get_dialogue(g, npc)
            if node not in nodes:
                return
            text, opts = nodes[node]
            if callable(text):
                text = text()
            opts = [o for o in opts if not o[2] or o[2]()]
            if not opts:
                opts = [("(Leave)", None, None)]
            sel = clamp(sel, 0, len(opts) - 1)
            if self.pilot:
                sel = self.pilot.choose_dialogue(g, npc, node, opts)
            self.draw_main(g, refresh=False)
            H, W = self.scr.getmaxyx()
            lines, pf, pp = art_lines(port)
            pw = max([len(l) for l in lines] + [0])
            w = min(W - 2, 112)
            tw = w - pw - 7
            tl = wrap(text, tw)
            ol = []
            for i, o in enumerate(opts):
                for j, l in enumerate(wrap("%d. %s" % (i + 1, o[0]), tw - 2)):
                    ol.append((i, ("   " if j else "") + l))
            h = min(H - 2, max(len(lines) + 4, len(tl) + len(ol) + 6))
            y, x = max(0, (H - h) // 2 - 1), max(0, (W - w) // 2)
            self.box(y, x, h, w, AMBER, spk)
            self.art(y + 2, x + 2, port, lines, pf, pp)
            self.put(y + 2 + len(lines) + 1, x + 2 + max(0, (pw - len(spk)) // 2), spk[:pw + 2], self.C(pf, BLACK, True))
            tx = x + pw + 5
            cy = y + 2
            for l in tl:
                if cy >= y + h - 2 - len(ol):
                    break
                self.put(cy, tx, l, self.C(LIGHT))
                cy += 1
            cy = max(cy + 1, y + h - 1 - len(ol) - 1)
            for i, l in ol:
                a = self.C(BLACK, AMBER) if i == sel else self.C(AMBER)
                self.put(cy, tx, l.ljust(tw)[:tw], a)
                cy += 1
            self.refresh()
            k = self.wait_key()
            if k in (curses.KEY_UP, ord('8')):
                sel = (sel - 1) % len(opts)
                continue
            if k in (curses.KEY_DOWN, ord('2'), 9):
                sel = (sel + 1) % len(opts)
                continue
            if k in ESC:
                return
            if ord('1') <= k <= ord('9') and k - ord('1') < len(opts):
                sel = k - ord('1')
            elif k not in ENTER and k != ord(' '):
                continue
            tgt = opts[sel][1]
            if callable(tgt):
                tgt = tgt()
            node, sel = tgt, 0
            while g.pending and g.pending[0][0] == "shop":
                g.pending.popleft()
                self.shop(g)

    # --- targeting -----------------------------------------------------------------------------
    def choose_target(self, g, src, targets, enemy=True, area_fn=None, title="Choose target"):
        if not targets:
            return None
        idx = 0
        while True:
            t = targets[idx]
            self.target_info = {"src": src, "targets": targets, "idx": idx, "enemy": enemy,
                                "area": area_fn(t) if area_fn else []}
            self.draw_main(g, refresh=False)
            H, W = self.scr.getmaxyx()
            info = "%s: %s" % (title, t.name)
            if enemy:
                info += "  HP %s  AC %d" % (self.hp_word(t), t.ac)
            else:
                info += "  HP %d/%d" % (max(0, t.hp), t.max_hp)
            info += "   [Tab/arrows] next  [Enter] confirm  [Esc] cancel"
            self.put(H - LOG_H, 1, " " + info[:W - 4] + " ", self.C(BLACK, YELLOW))
            self.refresh()
            k = self.wait_key()
            if k in (9, curses.KEY_RIGHT, curses.KEY_DOWN, ord('6'), ord('2')):
                idx = (idx + 1) % len(targets)
            elif k in (curses.KEY_LEFT, curses.KEY_UP, ord('4'), ord('8'), curses.KEY_BTAB):
                idx = (idx - 1) % len(targets)
            elif k in ENTER or k in (ord('f'), ord('z'), ord(' ')):
                self.target_info = None
                return t
            elif k in ESC:
                self.target_info = None
                return None

    @staticmethod
    def hp_word(t):
        r = t.hp / max(1, t.max_hp)
        return "unhurt" if r >= 1 else "scratched" if r > 0.75 else "wounded" if r > 0.4 else "badly hurt" if r > 0.15 else "near death"

    # --- player commands ------------------------------------------------------------------------
    def on_key(self, g, k):
        if k in MOVE_KEYS:
            dx, dy = MOVE_KEYS[k]
            g.try_move(dx, dy)
            return
        c = chr(k) if 0 <= k < 256 else ""
        if k in ESC or c in ("q", "Q"):   # the game menu - Esc works the same in every ASCII ARCADE game
            if not self.bot:
                self.game_menu(g)
            return
        if c in ".5" or (c == " " and g.combat):
            if g.combat:
                if g.needs_input():
                    g.end_turn()
            else:
                g.tick()
        elif c == "v":
            modes = self.view_modes()
            cur = self.view_mode(self.W - SIDE_W, self.H - 1 - LOG_H)
            self.view_pref = modes[(modes.index(cur) + 1) % len(modes)]
            g.msg("Map view: %s." % {"narrow": "narrow tiles", "square": "square tiles",
                                      "sprite": "pixel tiles", "large": "large pixel tiles",
                                      "huge": "huge pixel tiles"}[self.view_pref], GRAY)
        elif c == "f" and g.combat:
            self.cmd_attack(g)
        elif c == "z":
            self.cmd_cast(g)
        elif c == "p":
            self.cmd_potion(g)
        elif c == "a":
            self.cmd_ai(g, False)
        elif c == "A":
            self.cmd_ai(g, True)
        elif c == "i":
            self.inventory(g)
        elif c == "c":
            self.character(g)
        elif c == "j":
            self.journal(g)
        elif c == "m":
            self.log_view(g)
        elif c == "r":
            g.rest()
        elif c == "?":
            self.help()
        elif k == 9:
            self.sel = (self.sel + 1) % len(g.party)
        elif c == "S":
            if not self.bot:
                g.save(self.save_path)
        elif c == "L":
            if not self.bot and os.path.exists(self.save_path):
                if self.menu("Load the saved game?", [("Yes, load it", True, True), ("No", False, True)]):
                    raise LoadGame()
        elif c in ("d", "D"):
            if g.combat:
                g.msg("The difficulty can be changed after the fight (d).", YELLOW)
            elif not self.bot:
                d = self.pick_difficulty(g.diff)
                if d and d != g.diff:
                    g.diff = d
                    g.msg("Difficulty is now %s. Save with S to keep it." % g.D["name"], CYAN)
                else:
                    g.msg("Difficulty stays %s." % g.D["name"], GRAY)

    def game_menu(self, g):
        """Esc / Q: keep playing, read the help, or leave for the title screen."""
        save = "Save and quit" if not g.combat else "Quit (no saving during a fight)"
        v = self.menu("Game menu", [("Keep playing", False, True), ("How to play", "help", True),
                                    (save, "save", True), ("Quit without saving", "quit", True)])
        if v == "help":
            self.help()
        elif v in ("save", "quit"):
            if v == "save" and not g.combat:
                g.save(self.save_path)
            raise BackToTitle()

    def actor_for_command(self, g):
        if g.combat:
            return g.current() if g.needs_input() else None
        p = g.party[self.sel % len(g.party)]
        return p if p.conscious else None

    def cmd_attack(self, g):
        a = g.current()
        if not g.needs_input():
            return
        if a.acted:
            g.msg("%s has already acted. Move on or press Space." % a.name, GRAY)
            return
        rng = a.weapon.get("ranged", 1)
        ts = g.targets_for(a, rng)
        if not ts:
            g.msg("No enemy in reach of your %s (range %d)." % (a.weapon["name"].lower(), rng), GRAY)
            return
        t = self.choose_target(g, a, ts, True, title="Attack")
        if t:
            g.pc_attack(a, t)

    def cmd_cast(self, g):
        a = self.actor_for_command(g)
        if a is None:
            return
        if g.combat and a.acted:
            g.msg("%s has already acted this turn." % a.name, GRAY)
            return
        if not g.combat and not a.can_cast and a.cls != "fighter":
            casters = [p for p in g.party if p.conscious and p.can_cast]
            if not casters:
                g.msg("Nobody in the party can cast spells.", GRAY)
                return
            a = casters[0]
        sl = g.spell_list(a)
        if not sl:
            g.msg("%s knows no spells." % a.name, GRAY)
            return
        items = []
        for sid, ok, why in sl:
            if sid == "second_wind":
                items.append(("Second Wind (heal 1d10+%d)%s" % (a.level, "" if ok else " - used"), sid, ok))
                continue
            sp = SPELLS[sid]
            lv = "cantrip" if sp["lvl"] == 0 else ("1/rest" if sp["lvl"] < 0 else "level %d" % sp["lvl"])
            items.append(("%-20s %-8s%s" % (sp["name"], lv, (" - " + why) if why else ""), sid, ok))
        scrolls = sorted({it for it in g.bag if ITEMS[it]["kind"] == "scroll"}) if a.cls == "wizard" else []
        for it in scrolls:
            items.append(("%-20s scroll" % ITEMS[it]["name"], "scroll:" + it, True))

        def det(v):
            if v == "second_wind":
                return "Catch your breath and heal 1d10 + level. Once per rest."
            if v.startswith("scroll:"):
                return SPELLS[ITEMS[v[7:]]["spell"]]["desc"]
            return SPELLS[v]["desc"]
        sid = self.menu("%s's spells" % a.name.split()[0], items, detail=det)
        if not sid:
            return
        scroll = None
        if sid.startswith("scroll:"):
            scroll = sid[7:]
            sid = ITEMS[scroll]["spell"]
        if sid == "second_wind":
            g.cast(a, sid)
            return
        sp = SPELLS[sid]
        tgt = None
        if sp["target"] == "enemy":
            if not g.combat:
                g.msg("No battle is under way. Walk into a foe, or let it see you, to start one.", GRAY)
                return
            ts = g.targets_for(a, sp["range"])
            if not ts:
                g.msg("No enemy in range (%d)." % sp["range"], GRAY)
                return
            af = None
            if sp["kind"] == "ball":
                af = lambda t: g.ball(t.x, t.y, sp["radius"])
            elif sp["kind"] == "cone":
                af = lambda t: g.cone(a, t.x, t.y, sp["range"])
            elif sp["kind"] == "sleep":
                af = lambda t: g.ball(t.x, t.y, sp["radius"])
            tgt = self.choose_target(g, a, ts, True, af, sp["name"])
            if not tgt:
                return
        elif sp["target"] == "ally":
            ts = g.targets_for(a, sp["range"], enemies=False)
            if not ts:
                g.msg("Nobody in range.", GRAY)
                return
            ts.sort(key=lambda p: p.hp / max(1, p.max_hp))
            tgt = self.choose_target(g, a, ts, False, title=sp["name"])
            if not tgt:
                return
        else:
            tgt = a
        if scroll:
            g.bag.remove(scroll)
        g.cast(a, sid, tgt, scroll=bool(scroll))

    def cmd_potion(self, g):
        a = self.actor_for_command(g)
        if a is None:
            return
        if g.combat and a.acted:
            g.msg("%s has already acted this turn." % a.name, GRAY)
            return
        pots = sorted({it for it in g.bag if ITEMS[it]["kind"] == "potion"})
        if not pots:
            g.msg("No potions left.", GRAY)
            return
        it = pots[0] if len(pots) == 1 else self.menu("Drink which?", [(ITEMS[p]["name"], p, True) for p in pots])
        if not it:
            return
        target = a
        if not g.combat:
            ts = [p for p in g.party if not p.dead]
            target = self.menu("Who drinks it?", [("%s (%d/%d HP)" % (p.name, max(0, p.hp), p.max_hp), p, True) for p in ts])
            if not target:
                return
        g.use_item(a, g.bag.index(it), target)
        if g.combat:
            a.acted = True
            g.auto_end(a)

    def cmd_ai(self, g, all_):
        if all_:
            on = not all(p.ai for p in g.party[1:]) if len(g.party) > 1 else False
            for p in g.party[1:]:
                p.ai = on
            g.msg("Companions are now %s." % ("AI-controlled" if on else "under your control"), CYAN)
            return
        p = g.current() if g.combat else g.party[self.sel % len(g.party)]
        if p is None or not p.is_pc:
            return
        p.ai = not p.ai
        g.msg("%s is now %s." % (p.name, "AI-controlled" if p.ai else "under your control"), CYAN)

    # --- screens ------------------------------------------------------------------------------
    def full_box(self, title, fg=GOLD):
        self.erase()
        H, W = self.scr.getmaxyx()
        self.box(0, 0, H, W, fg, title)
        return H, W

    def inventory(self, g):
        sel = 0
        while True:
            H, W = self.full_box("Inventory - %d gold" % g.gold)
            counts = []
            for it in g.bag:
                for c in counts:
                    if c[0] == it:
                        c[1] += 1
                        break
                else:
                    counts.append([it, 1])
            self.put(2, 3, "Pack", self.C(YELLOW))
            if not counts:
                self.put(4, 5, "(empty)", self.C(DGRAY))
            sel = clamp(sel, 0, max(0, len(counts) - 1))
            room = H - 8
            top = clamp(sel - room + 1, 0, max(0, len(counts) - room))
            for i, (it, n) in enumerate(counts[top:top + room], top):
                ch, col = item_glyph(it)
                a = self.C(BLACK, GOLD) if i == sel else self.C(LIGHT)
                self.put(4 + i - top, 3, ch, self.C(col))
                self.put(4 + i - top, 5, (" %-26s %s" % (ITEMS[it]["name"] + (" x%d" % n if n > 1 else ""), "")).ljust(30)[:30], a)
            if counts:
                it = counts[sel][0]
                d = ITEMS[it]
                cx = 40
                self.put(2, cx, d["name"], self.C(YELLOW, BLACK, True))
                self.put(3, cx, (d["kind"].capitalize() + "  -  " + item_desc(it))[:W - cx - 2], self.C(GRAY))
                cy = 4
                if d.get("desc"):
                    for l in wrap(d["desc"], W - cx - 3):
                        self.put(cy, cx, l, self.C(LIGHT))
                        cy += 1
                self.put(cy + 1, cx, "Value: %d gold" % d["price"], self.C(DGRAY))
                cy += 3
                if d["kind"] in ("weapon", "armor", "shield", "ring", "amulet"):
                    for p in g.party:
                        why = g.can_equip(p, it)
                        cur = p.equip.get({"weapon": "weapon", "armor": "armor", "shield": "shield", "ring": "ring", "amulet": "amulet"}[d["kind"]])
                        s = "%-18s now: %s" % (p.name[:18], ITEMS[cur]["name"] if cur else "-")
                        self.put(cy, cx, s[:W - cx - 2], self.C(DGRAY if why else LIGHT))
                        cy += 1
            self.put(H - 2, 3, "[Enter] use / equip   [d] drop   [Esc] back", self.C(DGRAY))
            self.refresh()
            k = self.wait_key()
            if k in ESC or k == ord('i') or k == ord('q'):
                return
            if k in (curses.KEY_UP, ord('8')):
                sel -= 1
            elif k in (curses.KEY_DOWN, ord('2')):
                sel += 1
            elif counts and (k in ENTER or k == ord('d')):
                it = counts[sel][0]
                d = ITEMS[it]
                if k == ord('d'):
                    if d["kind"] == "quest":
                        g.msg("Better keep that.", GRAY)
                    elif self.menu("Drop %s?" % d["name"], [("Drop it", True, True), ("Keep it", False, True)]):
                        g.bag.remove(it)
                        g.area.add_item(g.leader.x, g.leader.y, it)
                        g.msg("Dropped %s." % d["name"], GRAY)
                    continue
                if d["kind"] == "potion":
                    if g.combat:
                        self.cmd_potion(g)
                        return
                    who = self.menu("Who drinks it?", [("%s (%d/%d HP)" % (p.name, max(0, p.hp), p.max_hp), p, True)
                                                       for p in g.party if not p.dead])
                    if who:
                        g.use_item(who, g.bag.index(it), who)
                elif d["kind"] in ("weapon", "armor", "shield", "ring", "amulet"):
                    if g.combat and not g.needs_input():
                        continue
                    pool = [g.current()] if g.combat else g.party
                    who = self.menu("Equip %s on..." % d["name"],
                                    [("%s%s" % (p.name, "" if not g.can_equip(p, it) else "  (can't)"), p, not g.can_equip(p, it))
                                     for p in pool if not p.dead])
                    if who:
                        g.equip(who, g.bag.index(it))
                        if g.combat:
                            return
                elif d["kind"] == "scroll":
                    g.msg("Read scrolls from a wizard's spell menu (z).", GRAY)
                else:
                    self.message(d["name"], d.get("desc", ""))

    def character(self, g):
        i = self.sel % len(g.party)
        slot_sel = 0
        slots = ["weapon", "armor", "shield", "ring", "amulet"]
        while True:
            p = g.party[i]
            H, W = self.full_box("Character - %d/%d" % (i + 1, len(g.party)))
            lines, pf, pp = art_lines(p.portrait)
            self.art(2, 3, p.portrait)
            ay = 3 + len(lines)
            self.put(ay, 3, p.name, self.C(p.fg, BLACK, True))
            self.put(ay + 1, 3, "%s %s, level %d" % (RACES[p.race]["name"], CLASSES[p.cls]["name"], p.level), self.C(LIGHT))
            nxt = XP_LEVELS[p.level + 1] if p.level < MAX_LEVEL else None
            self.put(ay + 2, 3, "XP %d%s" % (p.xp, (" / %d" % nxt) if nxt else " (max level)"), self.C(GRAY))
            for j, l in enumerate(wrap(p.bio, 30)[:4]):
                self.put(ay + 4 + j, 3, l, self.C(DGRAY))
            cx = 38
            hpcol = RED if p.dead else LIGHT
            self.put(2, cx, "HP %d/%d   AC %d   Speed %d   Proficiency +%d" % (max(0, p.hp), p.max_hp, p.ac, p.speed, p.prof), self.C(hpcol))
            w = p.weapon
            self.put(3, cx, "Attack %s with %s: %s%s %s" % (sgn(p.attack_bonus()), w["name"], w["dmg"],
                                                           sgn(p.damage_bonus()) if p.damage_bonus() else "", w["dtype"]), self.C(LIGHT))
            for j, s in enumerate(STATS):
                v = p.stats[s]
                sv = p.save_bonus(s)
                self.put(5 + j, cx, "%s %2d (%s)   save %s" % (s, v, sgn(mod(v)), sgn(sv)),
                         self.C(YELLOW if s in CLASSES[p.cls]["saves"] else LIGHT))
            fy = 5
            fx = cx + 30
            feats = []
            if p.cls == "fighter":
                feats += ["Second Wind (%s)" % ("used" if p.uses.get("second_wind") else "ready")]
                if p.level >= 3:
                    feats.append("Improved Critical 19-20")
                if p.level >= 5:
                    feats.append("Extra Attack")
            if p.cls == "rogue":
                feats += ["Sneak Attack %dd6" % p.sneak_dice, "Finds traps, picks locks"]
            if p.race == "dwarf":
                feats.append("Dwarven resilience (poison)")
            if p.race == "elf":
                feats.append("Elven trance (no sleep, no ghoul paralysis)")
            if p.race == "halfling":
                feats.append("Lucky (reroll natural 1s)")
            if p.can_cast:
                feats.append("Spell DC %d, spell attack %s" % (p.spell_dc, sgn(p.spell_atk)))
                feats.append("Slots: " + (" ".join("L%s %d/%d" % (k, v[0], v[1]) for k, v in sorted(p.slots.items())) or "-"))
                feats += ["  " + SPELLS[s]["name"] for s in p.spells]
            self.put(fy - 1, fx, "Features", self.C(YELLOW))
            for j, f in enumerate(feats[:H - fy - 14]):
                self.put(fy + j, fx, f[:W - fx - 2], self.C(LIGHT))
            ey = max(12, fy + len(feats) + 1)
            ey = min(ey, H - 9)
            self.put(ey, cx, "Equipment", self.C(YELLOW))
            for j, s in enumerate(slots):
                it = p.equip.get(s)
                a = self.C(BLACK, GOLD) if j == slot_sel else self.C(LIGHT)
                txt = "%-7s %s" % (s.capitalize(), ITEMS[it]["name"] + "  - " + item_desc(it) if it else "-")
                self.put(ey + 1 + j, cx, (" " + txt).ljust(W - cx - 3)[:W - cx - 3], a)
            ai = "on" if p.ai else "off"
            foot = "[Left/Right] member  [Up/Down] slot  [Enter] change  [a] AI: %s" % ai
            if p is not g.leader:
                foot += "  [D] dismiss"
            self.put(H - 2, 3, foot, self.C(DGRAY))
            self.refresh()
            k = self.wait_key()
            if k in ESC or k == ord('c') or k == ord('q'):
                self.sel = i
                return
            if k in (curses.KEY_RIGHT, 9, ord('6')):
                i = (i + 1) % len(g.party)
            elif k in (curses.KEY_LEFT, ord('4')):
                i = (i - 1) % len(g.party)
            elif k in (curses.KEY_UP, ord('8')):
                slot_sel = (slot_sel - 1) % len(slots)
            elif k in (curses.KEY_DOWN, ord('2')):
                slot_sel = (slot_sel + 1) % len(slots)
            elif k == ord('a'):
                p.ai = not p.ai
            elif k == ord('D') and p is not g.leader:
                if g.area.id != "town":
                    g.msg("Dismiss companions in town, so they can wait at the inn.", GRAY)
                elif self.menu("Dismiss %s?" % p.name, [("Yes - wait at the Rusty Lantern", True, True), ("No", False, True)]):
                    g.dismiss(p)
                    i = 0
            elif k in ENTER and not p.dead:
                if g.combat and g.current() is not p:
                    continue
                s = slots[slot_sel]
                kinds = {"weapon": "weapon", "armor": "armor", "shield": "shield", "ring": "ring", "amulet": "amulet"}
                opts = [("(take off)", "-", bool(p.equip.get(s)) and s != "armor")]
                seen = set()
                for it in g.bag:
                    if ITEMS[it]["kind"] == kinds[s] and it not in seen:
                        seen.add(it)
                        why = g.can_equip(p, it)
                        opts.append(("%s - %s%s" % (ITEMS[it]["name"], item_desc(it), "  (can't)" if why else ""), it, not why))
                ch = self.menu("%s: %s" % (p.name.split()[0], s), opts)
                if ch == "-":
                    g.unequip(p, s)
                elif ch:
                    g.equip(p, g.bag.index(ch))

    def journal(self, g):
        scroll = 0
        while True:
            H, W = self.full_box("Journal")
            lines = []
            for state in ("active", "done"):
                for qid, q in g.quests.items():
                    if q["state"] != state:
                        continue
                    lines.append(("%s %s" % ("*" if state == "active" else "+", q["title"] + ("" if state == "active" else " (completed)")),
                                  YELLOW if state == "active" else DGRAY))
                    for e in q["log"]:
                        for l in wrap(e, W - 10):
                            lines.append(("    " + l, LIGHT if state == "active" else DGRAY))
                    lines.append(("", LIGHT))
            if not lines:
                lines = [("No quests yet. Talk to people in town.", GRAY)]
            scroll = clamp(scroll, 0, max(0, len(lines) - (H - 5)))
            for j, (l, c) in enumerate(lines[scroll:scroll + H - 5]):
                self.put(2 + j, 3, l, self.C(c))
            self.put(H - 2, 3, "[Up/Down] scroll   [Esc] back      Kills: %d   Day %d" % (g.kills, g.day), self.C(DGRAY))
            self.refresh()
            k = self.wait_key()
            if k in ESC or k == ord('j') or k == ord('q'):
                return
            if k in (curses.KEY_UP, ord('8')):
                scroll -= 1
            elif k in (curses.KEY_DOWN, ord('2')):
                scroll += 1

    def log_view(self, g):
        scroll = 10 ** 6
        while True:
            H, W = self.full_box("Message log")
            lines = []
            for t, c in g.log:
                for l in wrap(t, W - 6):
                    lines.append((l, c))
            room = H - 4
            scroll = clamp(scroll, 0, max(0, len(lines) - room))
            for j, (l, c) in enumerate(lines[scroll:scroll + room]):
                self.put(2 + j, 3, l, self.C(c))
            self.refresh()
            k = self.wait_key()
            if k in ESC or k in ENTER or k == ord('m') or k == ord('q'):
                return
            if k in (curses.KEY_UP, ord('8')):
                scroll -= 1
            elif k in (curses.KEY_DOWN, ord('2')):
                scroll += 1
            elif k == curses.KEY_PPAGE:
                scroll -= room
            elif k == curses.KEY_NPAGE:
                scroll += room

    def shop(self, g):
        if self.pilot:
            got = self.pilot.shop(g)
            self.message("Greta's Iron & Sundries", ("Bought: " + ", ".join(got) + ".") if got else
                         "Nothing worth the money today.", "greta")
            return
        mode, sel = 0, 0
        while True:
            H, W = self.full_box("Greta's Iron & Sundries - you have %d gold" % g.gold, ORANGE)
            self.art(2, 3, "greta")
            lst = SHOP_STOCK if mode == 0 else g.bag
            sel = clamp(sel, 0, max(0, len(lst) - 1))
            self.put(2, 30, " BUY ", self.C(BLACK, ORANGE) if mode == 0 else self.C(GRAY))
            self.put(2, 37, " SELL ", self.C(BLACK, ORANGE) if mode == 1 else self.C(GRAY))
            room = H - 7
            top = clamp(sel - room + 1, 0, max(0, len(lst) - room))
            for j, it in enumerate(lst[top:top + room], top):
                d = ITEMS[it]
                price = d["price"] if mode == 0 else d["price"] // 2
                a = self.C(BLACK, GOLD) if j == sel else self.C(LIGHT if (mode == 1 or price <= g.gold) else DGRAY)
                self.put(4 + j - top, 30, (" %-26s %5d gp  %s" % (d["name"], price, item_desc(it)))[:W - 33].ljust(min(W - 33, 80)), a)
            if not lst:
                self.put(4, 31, "(nothing to sell)", self.C(DGRAY))
            elif lst:
                it = lst[sel]
                users = [p.name.split()[0] for p in g.party if not g.can_equip(p, it)] if ITEMS[it]["kind"] in ("weapon", "armor", "shield") else []
                if users:
                    self.put(H - 3, 30, ("Usable by: " + ", ".join(users))[:W - 33], self.C(GRAY))
            self.put(H - 2, 3, "[Tab] buy/sell   [Enter] trade   [Esc] leave", self.C(DGRAY))
            self.refresh()
            k = self.wait_key()
            if k in ESC or k == ord('q'):
                return
            if k in (9, curses.KEY_LEFT, curses.KEY_RIGHT):
                mode, sel = 1 - mode, 0
            elif k in (curses.KEY_UP, ord('8')):
                sel -= 1
            elif k in (curses.KEY_DOWN, ord('2')):
                sel += 1
            elif k in ENTER and lst:
                if mode == 0:
                    g.buy(lst[sel])
                else:
                    g.sell(sel)

    def paint_world(self, g, y0, x0, w, h, locs, dest, blink):
        """The painted world map (truecolor), with the route to dest and a sign at every known place."""
        base = world_pixels(w, h * 2)
        px = [row[:] for row in base]
        a, b = WORLD_ROAD_AT.get(g.location), WORLD_ROAD_AT.get(dest)
        if a is not None and b is not None and a != b:  # the way there, as a dashed golden trail
            pts = [(u * w, v * h * 2) for u, v in WORLD_ROAD[min(a, b):max(a, b) + 1]]
            step = 0
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                n = int(max(abs(x2 - x1), abs(y2 - y1)) * 2) + 1
                for i in range(n):
                    step += 1
                    if step % 6 < 4:
                        qx = int(round(x1 + (x2 - x1) * i / n))
                        qy = int(round(y1 + (y2 - y1) * i / n))
                        if 0 <= qx < w and 0 <= qy < h * 2:
                            px[qy][qx] = (255, 222, 110)
        rows = [[["▀", px[2 * j][i], px[2 * j + 1][i]] for i in range(w)] for j in range(h)]
        for l in locs:
            u, v = WORLD_PIX[l]
            cx, cy = int(u * w), min(h - 1, int(v * h * 2) // 2)
            here, chosen = l == g.location, l == dest
            mark = "@" if here else "◆"
            mcol = (255, 70, 50) if chosen and blink else ((255, 255, 255) if here else (255, 214, 90))
            lbl = " %s " % WORLD[l][0]
            dy, dx = WORLD_SIGN.get(l, (1, None))
            ly = max(0, min(h - 1, cy + dy))
            lx = max(0, min(w - len(lbl), cx - len(lbl) // 2 if dx is None else cx + dx))
            fg, bg = ((20, 14, 8), (246, 204, 84)) if chosen else ((236, 226, 206), (34, 26, 20))
            rows[cy][cx] = [mark, mcol, rows[cy][cx][2]]
            for i, ch in enumerate(lbl):
                rows[ly][lx + i] = [ch, fg, bg]
        self.rawmap = (y0, x0, [[tuple(c) for c in r] for r in rows])
        for j in range(h):
            self.put(y0 + j, x0, " " * w, self.mark_attr)

    def world_map(self, g):
        locs = [l for l in WORLD if l in g.discovered]
        sel = locs.index(g.location) if g.location in locs else 0
        if self.pilot:
            want = self.pilot.choose_dest(g)
            if want not in locs:
                locs.append(want)
            sel = locs.index(want)
        while True:
            H, W = self.full_box("The Ashpeak Marches")
            blink = int(time.time() * 3) % 2 == 0
            mh = min(H - 6, 34)
            mw = min(W - 4, int(mh * 2 * 2.2))
            if PIC_MODE == "true" and mh >= 14 and mw >= 56:
                ax, ay = (W - mw) // 2, 2
                self.paint_world(g, ay, ax, mw, mh, locs, locs[sel], blink)
                iy = ay + mh + 1
            else:
                lines, fg, pal = art_lines("world")
                aw = max(len(l) for l in lines)
                ax, ay = max(2, (W - aw) // 2), 2
                self.art(ay, ax, "world")
                for l in locs:
                    lbl, aid, ent, mx, my = WORLD[l]
                    here = l == g.location
                    col = YELLOW if l == locs[sel] else (WHITE if here else LIGHT)
                    self.put(ay + my, ax + mx, "@" if here else "*", self.C(RED if blink and l == locs[sel] else col, BLACK, True))
                    tx = ax + mx + 2
                    self.put(ay + my, tx, " %s " % lbl, self.C(BLACK, YELLOW) if l == locs[sel] else self.C(col, BLACK))
                iy = ay + len(lines) + 1
            dest = locs[sel]
            if dest == g.location:
                info = "You are here. [Enter] to go back in."
            else:
                info = "Travel to %s: about %d hours. [Enter] travel" % (WORLD[dest][0], TRAVEL_H.get(frozenset((g.location, dest)), 4))
            self.put(iy, ax, info, self.C(LIGHT))
            self.put(iy + 1, ax, "[Up/Down] choose destination   [Esc] stay here", self.C(DGRAY))
            self.refresh()
            k = self.wait_key()
            if k in (curses.KEY_UP, curses.KEY_LEFT, ord('8')):
                sel = (sel - 1) % len(locs)
            elif k in (curses.KEY_DOWN, curses.KEY_RIGHT, ord('2'), 9):
                sel = (sel + 1) % len(locs)
            elif k in ESC:
                return
            elif k in ENTER:
                if dest == g.location:
                    lbl, aid, ent, mx, my = WORLD[dest]
                    if g.area.id != aid:
                        g.enter_area(aid, ent)
                    else:
                        L = g.leader
                        if g.area.tile(L.x, L.y) == T_EXIT or g.area.links.get((L.x, L.y)):
                            pos = min(g.area.entries.values(), key=lambda q: cheb(q[0], q[1], L.x, L.y))
                            g.place_party(*pos)
                            g.update_fov()
                    return
                g.travel_to(dest)
                return

    def help(self):
        txt = [
            ("MOVING", YELLOW),
            ("Arrow keys, numpad (7 9 1 3 for diagonals) or y u b n for diagonals.", LIGHT),
            ("Walk into people to talk, into doors to open them, into chests to loot them.", LIGHT),
            ("Your party follows the leader. Leave an area via stairs (> <) or the yellow > on a map edge.", LIGHT),
            ("", LIGHT),
            ("COMBAT (turn-based, d20 rules)", YELLOW),
            ("Each round every creature acts in initiative order. On a party member's turn:", LIGHT),
            ("  move up to its speed in tiles, and take one action:", LIGHT),
            ("  f attack (or walk into a foe)   z cast a spell   p drink a potion", LIGHT),
            ("  Space / . ends the turn   a lets the AI play this character (A: all companions)", LIGHT),
            ("Attack roll: d20 + bonus vs the target's Armour Class. A natural 20 is a critical hit.", LIGHT),
            ("Rogues deal Sneak Attack damage when an ally stands next to the target.", LIGHT),
            ("Sleeping or paralysed foes are hit automatically harder. Fireball burns friends too!", LIGHT),
            ("At 0 HP a character falls and makes death saves. Healing brings them back.", LIGHT),
            ("If your hero dies, the companions carry on - Father Aldous can raise the dead for gold.", LIGHT),
            ("d changes the difficulty (Easy / Normal / Hard) at any time outside combat.", LIGHT),
            ("The adventure ends if the whole party falls, or if you come home with a dead hero and no coin.", LIGHT),
            ("", LIGHT),
            ("OTHER KEYS", YELLOW),
            ("i inventory   c character sheet (equipment, AI, dismiss)   j journal   m message log", LIGHT),
            ("r rest (restores HP and spells; might be interrupted)   Tab select party member", LIGHT),
            ("S save   L load   v map view (narrow/square/pixel/large/huge)", LIGHT),
            ("Esc / Q game menu: keep playing, help, save and quit   ? this help", LIGHT),
            ("d difficulty: Easy / Normal / Hard (any time outside combat)", LIGHT),
            ("", LIGHT),
            ("Rules after the D&D 5e System Reference Document 5.1 (CC-BY-4.0, Wizards of the Coast).", DGRAY),
        ]
        H, W = self.full_box("Help")
        for j, (l, c) in enumerate(txt[:H - 3]):
            self.put(2 + j, 3, l[:W - 6], self.C(c))
        self.refresh()
        self.wait_key()

    def gameover(self, g):
        H, W = self.full_box("Your adventure ends", RED)
        lines, fg, pal = art_lines("gameover")
        self.art(2, (W - 46) // 2, "gameover", fmt=g.hero.name[:17].center(17))
        y = 3 + len(lines)
        for l in ["%s fell on day %d." % (g.hero.name, g.day), "Foes slain: %d" % g.kills, "",
                  "Emberfall will have to find another hero.", "", "Press any key."]:
            self.put(y, (W - len(l)) // 2, l, self.C(LIGHT))
            y += 1
        self.refresh()
        time.sleep(0 if self.bot else 0.8)
        self.wait_key()
        raise BackToTitle()

    def victory(self, g):
        H, W = self.full_box("Victory!", GOLD)
        lines, fg, pal = art_lines("victory")
        self.art(2, (W - 50) // 2, "victory")
        text = ("Ashmaw's last breath rolls through the mountain like distant thunder, and then there is only the "
                "tick of cooling gold. Days later, Emberfall rings every bell it owns. Mayor Thale gives a very long "
                "speech and a very large purse. Hobb names an ale after you. Pell finally finishes his ballad - the "
                "ending, at least, is magnificent.\n\nThe Ashpeaks are quiet again. For now.")
        y = 3 + len(lines)
        for l in wrap(text, min(80, W - 8)):
            self.put(y, (W - min(80, W - 8)) // 2, l, self.C(LIGHT))
            y += 1
        y += 1
        party = ", ".join(p.name for p in g.party if not p.dead)
        for l in ["Heroes: " + party, "Days: %d   Foes slain: %d   Gold: %d" % (g.day, g.kills, g.gold + 500), "",
                  "THE END - thank you for playing!"]:
            self.put(y, (W - len(l)) // 2, l, self.C(YELLOW))
            y += 1
        self.refresh()
        time.sleep(0 if self.bot else 1.0)
        self.wait_key()
        try:
            os.remove(self.save_path)
        except OSError:
            pass
        raise BackToTitle()

    # --- title and character creation --------------------------------------------------------
    def title(self):
        self.g = None
        embers = []
        sel = 0
        has_save = os.path.exists(self.save_path)
        opts = [("Continue", "continue")] if has_save else []
        opts += [("New adventure", "new"), ("Watch the AI play", "watch"), ("How to play", "help"), ("Quit", "quit")]
        while True:
            if self.too_small():
                self.wait_key()
                continue
            H, W = self.scr.getmaxyx()
            self.erase()
            if self.rng.random() < 0.9:
                embers.append([self.rng.randint(0, W - 1), H - 1, self.rng.uniform(0.3, 1.0), self.rng.choice("..*'`")])
            for e in embers:
                e[1] -= e[2]
                e[0] += self.rng.choice((-1, 0, 0, 1)) if self.rng.random() < 0.3 else 0
            embers = [e for e in embers if e[1] > 0]
            for e in embers:
                self.put(int(e[1]), int(e[0]), e[3], self.C(self.rng.choice(FIRE_COLS)))
            # the ASCII ARCADE title layout: block title, scene, tagline, menu panel, footer bar
            k2 = W >= title_cols("X" * 11, 2) + 4 and H >= 30   # the letter size every arcade title uses
            y = 1
            y += self.block_title("EMBERFALL", y, 2 if k2 else 1)
            need = len(opts) * 2 + 7
            pk = next((k for k in ("title_l", "title_m", "title_s")
                       if pic_for(k) and PICS[k]["h"] <= H - y - need and PICS[k]["w"] <= W - 2), None)
            if pk:
                self.art(y, (W - PICS[pk]["w"]) // 2, pk)
                y += PICS[pk]["h"]
            sub = "~  T H E   P A L E   F L A M E  ~"
            self.put(y, (W - len(sub)) // 2, sub, self.C(PALE))
            y += 2
            pw = max(len(lab) for lab, _ in opts) + 14
            px0 = (W - pw) // 2
            panel, sel_a = self.C(LIGHT, PANEL), self.C(BLACK, TITLE_SEL)
            for j in range(len(opts) * 2 + 1):
                self.put(y + j, px0, " " * pw, panel)
            for i, (lab, v) in enumerate(opts):
                line = ((" > " if i == sel else "   ") + lab).ljust(pw - 4)
                self.put(y + 1 + i * 2, px0 + 2, line, sel_a if i == sel else panel)
            credit = "Rules after the D&D 5e SRD 5.1 (CC-BY-4.0)."
            self.put(H - 2, max(0, (W - len(credit)) // 2), credit, self.C(DGRAY))
            label, keys = " ASCII ARCADE ", " Up/Down choose   Enter start   ? help   Esc quit "
            self.put(H - 1, 0, " " * (W - 1), self.C(FOOTER_FG, FOOTER_BG))
            self.put(H - 1, 0, label, self.C(BLACK, FOOTER_LABEL))
            self.put(H - 1, max(len(label) + 1, W - 1 - len(keys)), keys, self.C(FOOTER_FG, FOOTER_BG))
            self.refresh()
            k = self.key()
            if k in (curses.KEY_UP, ord('8')):
                sel = (sel - 1) % len(opts)
            elif k in (curses.KEY_DOWN, ord('2'), 9):
                sel = (sel + 1) % len(opts)
            elif k in ENTER or k == ord(' '):
                v = opts[sel][1]
                if v == "help":
                    self.help()
                else:
                    return v
            elif k == ord('?'):
                self.help()
            elif k in ESC or k in (ord('q'), ord('Q')):
                return "quit"

    def create(self):
        self.g = None
        name = self.text_input("A new hero", "What is your name, adventurer?", random.choice(NAMES))
        if not name:
            return None
        race = self.pick_screen("Choose your people", [(RACES[r]["name"], r) for r in RACES],
                                lambda r: (r + "_fighter" if pic_for(r + "_fighter") else None,
                                           RACES[r]["desc"] + "\n\nSpeed %d tiles." % RACES[r]["speed"]))
        if not race:
            return None
        cls = self.pick_screen("Choose your calling", [(CLASSES[c]["name"], c) for c in CLASSES],
                               lambda c: (race + "_" + c, CLASSES[c]["desc"] + "\n\nHit die d%d. Saves: %s." % (
                                   CLASSES[c]["hd"], ", ".join(CLASSES[c]["saves"]))))
        if not cls:
            return None
        base = self.roll_screen(name, race, cls)
        if not base:
            return None
        diff = self.pick_difficulty("normal")
        if not diff:
            return None
        self.new_diff = diff
        return make_pc(name, race, cls, base, portrait=race + "_" + cls)

    def pick_difficulty(self, cur):
        items = [(d["name"], k, True) for k, d in DIFFICULTY.items()]
        return self.menu("How hard should the adventure be?", items, sel=list(DIFFICULTY).index(cur), width=60,
                         detail=lambda k: DIFFICULTY[k]["desc"], footer="[Enter] choose   [Esc] back   (d: change later)")

    def pick_screen(self, title, opts, info):
        sel = 0
        while True:
            H, W = self.full_box(title)
            for i, (lab, v) in enumerate(opts):
                self.put(4 + i * 2, 4, (" %-12s " % lab), self.C(BLACK, GOLD) if i == sel else self.C(LIGHT))
            art, text = info(opts[sel][1])
            x = 24
            y = 3
            if art:
                lines = art_lines(art)[0]
                self.art(y, x, art)
                y += len(lines) + 1
            for l in wrap(text, W - x - 4):
                self.put(y, x, l, self.C(LIGHT))
                y += 1
            self.put(H - 2, 4, "[Up/Down] choose   [Enter] select   [Esc] back", self.C(DGRAY))
            self.refresh()
            k = self.wait_key()
            if k in (curses.KEY_UP, ord('8')):
                sel = (sel - 1) % len(opts)
            elif k in (curses.KEY_DOWN, ord('2'), 9):
                sel = (sel + 1) % len(opts)
            elif k in ENTER or k == ord(' '):
                return opts[sel][1]
            elif k in ESC:
                return None

    def roll_screen(self, name, race, cls):
        vals = assign_stats(roll_stats(), cls)
        sel, mark = 0, None
        while True:
            H, W = self.full_box("Roll your abilities")
            self.art(2, 4, race + "_" + cls)
            x = 34
            self.put(2, x, "%s, %s %s" % (name, RACES[race]["name"], CLASSES[cls]["name"]), self.C(YELLOW, BLACK, True))
            self.put(3, x, "4d6, drop the lowest die. Reroll as often as you like.", self.C(GRAY))
            for i, s in enumerate(STATS):
                b = RACES[race]["bonus"].get(s, 0)
                v = vals[s] + b
                prim = s == CLASSES[cls]["order"][0]
                a = self.C(BLACK, GOLD) if i == sel else self.C(YELLOW if prim else LIGHT)
                txt = " %s  %2d %s = %2d  (%s) " % (s, vals[s], ("+%d" % b) if b else "  ", v, sgn(mod(v)))
                if mark == i:
                    txt += "<swap>"
                self.put(5 + i, x, txt, a)
                self.put(5 + i, x + 30, "#" * max(0, v - 2), self.C(EMBER if v >= 16 else (AMBER if v >= 12 else DGRAY)))
            tot = sum(vals.values())
            self.put(12, x, "Total %d %s" % (tot, "(heroic!)" if tot >= 80 else "(sturdy)" if tot >= 72 else "(humble)"), self.C(GRAY))
            hp = CLASSES[cls]["hd"] + mod(vals["CON"] + RACES[race]["bonus"].get("CON", 0))
            self.put(13, x, "Starting HP %d" % max(1, hp), self.C(GRAY))
            self.put(H - 2, 4, "[r] reroll   [Up/Down + Space] swap two scores   [Enter] begin   [Esc] back", self.C(DGRAY))
            self.refresh()
            k = self.wait_key()
            if k in (ord('r'), ord('R')):
                vals = assign_stats(roll_stats(), cls)
                mark = None
            elif k in (curses.KEY_UP, ord('8')):
                sel = (sel - 1) % 6
            elif k in (curses.KEY_DOWN, ord('2')):
                sel = (sel + 1) % 6
            elif k == ord(' '):
                if mark is None:
                    mark = sel
                else:
                    a, b = STATS[mark], STATS[sel]
                    vals[a], vals[b] = vals[b], vals[a]
                    mark = None
            elif k in ENTER:
                return vals
            elif k in ESC:
                return None

    def intro(self):
        text = ("For a hundred years the town of Emberfall has dug iron from the Ashpeaks and asked for nothing "
                "more. But three weeks ago the night shift at the Deepdelve mine went down the shaft and never came "
                "back up. Then the next. Eleven miners are gone. At night the peaks glow a dull and angry red, and the "
                "snow melts where no sun touches it.\n\nYou arrived yesterday with a pack, a weapon and an empty purse. "
                "Today you wake in the Rusty Lantern, and the whole town is whispering.")
        self.g = None
        self.message("Emberfall", text, "town")


class LoadGame(Exception):
    pass


def ui_run(self, g):
    self.g = g
    if self.pilot:
        return self.watch(g)
    while True:
        if g.pending:
            self.handle_pending(g)
            continue
        if g.combat and not g.needs_input():
            cur = g.current()
            self.draw_main(g)
            if self.bot:
                self.frames += 1
                if self.frames > self.bot:
                    raise BotDone()
            elif cur and (cur.is_pc or g.sees(cur)):
                time.sleep(0.22)
            g.step_ai()
            self.animate(g)
            continue
        self.draw_main(g)
        k = self.key()
        if k == -1 or k == curses.KEY_RESIZE:
            continue
        self.on_key(g, k)
        self.animate(g)


UI.run = ui_run


def play(scr, bot=0, save_path=SAVE_PATH, start=None, watch=False):
    ui = UI(scr, bot, save_path)
    ui.g = None
    while True:
        choice = "watch" if watch else "new" if bot else ui.title()
        if choice == "quit":
            return
        if choice == "watch":
            if not bot:
                names = {"narrow": "Narrow tiles (1 column)", "square": "Square tiles (2 columns)",
                         "sprite": "Pixel tiles (4x4)", "large": "Large pixel tiles (8x8)",
                         "huge": "Huge pixel tiles (16x16)"}
                items = [("Automatic (fits the window)", "auto", True)] + [(names[m], m, True) for m in ui.view_modes()]
                cur = ui.view_pref if ui.view_pref in ui.view_modes() else "auto"
                pick = ui.menu("How should the map look?", items, sel=[v for _, v, _ in items].index(cur),
                               footer="[Enter] start watching   [Esc] back   (v switches later too)")
                if pick is None:
                    if watch:
                        return
                    continue
                ui.view_pref = None if pick == "auto" else pick
            race, cls = random.choice(list(RACES)), random.choice(list(CLASSES))
            g = Game()
            g.new_game(make_pc(random.choice(NAMES), race, cls, assign_stats(roll_stats(), cls), portrait=race + "_" + cls))
            ui.pilot = Autopilot()
            ui.message("Watching the AI play", "%s the %s %s sets out from Emberfall. Sit back and watch.\n\n"
                       "[Space] pause   [+/-] speed   [Esc] stop" % (g.leader.name, RACES[race]["name"],
                                                                     CLASSES[cls]["name"]), race + "_" + cls)
            try:
                ui.run(g)
            except (BackToTitle, LoadGame):
                pass
            ui.pilot, ui.paused = None, False
            if watch and not bot:
                return
            if bot:
                return
            continue
        if choice == "continue":
            try:
                g = Game.load(save_path)
            except Exception as e:  # a broken save should not kill the game
                ui.message("Could not load", "The save file could not be read (%s)." % e)
                continue
        else:
            pc = ui.create()
            if not pc:
                continue
            g = Game()
            g.new_game(pc, getattr(ui, "new_diff", "normal"))
            if start:  # developer shortcut: a full party dropped into an area
                for c in ("brannoc", "tamsin", "maren"):
                    g.recruit(c)
                g.enter_area(start, None)
            else:
                ui.intro()
        ui.sel = 0
        while True:
            try:
                ui.run(g)
                break
            except LoadGame:
                g = Game.load(save_path)
            except BackToTitle:
                break


# =============================================================================
# Autopilot: plays the whole adventure like a careful player. Used to watch the
# game play itself (--watch, title menu) and for balance runs (--simulate).
# =============================================================================
STORY_AREAS = ["cellar", "forest", "mine1", "mine2", "sanctum", "lair"]
AREA_GRAPH = {"town": ["cellar", "world"], "cellar": ["town"], "forest": ["world"], "mine1": ["world", "mine2"],
              "mine2": ["mine1", "sanctum"], "sanctum": ["mine2", "lair"], "lair": ["sanctum"], "road": ["world"],
              "world": ["town", "forest", "mine1"]}
WORLD_OF = {"town": "emberfall", "forest": "whisperwood", "mine1": "deepdelve"}
DLG_GOOD = ("any work for me", "about the bounty", "i'll keep an eye", "deal.", "i found ", "need any help", "consider it done", "fine. i'll do it", "cellar is clear", "come with me",
            "then come with me", "would you join", "a mountain", "what troubles you", "missing miners",
            "about the mine", "i found this", "know a halfling", "who are the fire-men", "draconic",
            "show me your wares")
DLG_INFO = ("heard any news", "where do i find", "what are you reading", "any rumours", "play something",
            "tell me about", "heard anything", "any advice", "you fed the miners")
DLG_BAD = ("a tree", "a dragon.", "rats? i'm here", "i'm sorry", "not yet", "i'll think", "take our gold")
DLG_END = ("farewell", "goodbye", "(leave", "thanks.", "dawn keep", "(continue", "(back", "for emberfall",
           "(attack", "(fight", "not today", "hang on", "surrender")


class Autopilot:
    def __init__(self, seed=None):
        self.rnd = random.Random(seed)
        self.said = set()          # (npc, label) already chosen
        self.met = set()           # npcs talked to
        self.fails = {}            # target -> failed attempts (locked chests ...)
        self.stuck = 0
        self.last_pos = None
        self.goal = "start"        # human readable, shown while watching
        self.shopped_at = -1
        self.home_trip = False
        self.town_steps = 0
        self.rest_tries = {}
        self.idle, self.sig, self.calm_until, self.ticks = 0, None, 0, 0

    # --- helpers ------------------------------------------------------------------------
    @staticmethod
    def hp_frac(g):
        live = [p for p in g.party if not p.dead]
        return sum(max(0, p.hp) for p in live) / max(1, sum(p.max_hp for p in live))

    @staticmethod
    def potions(g):
        return sum(1 for it in g.bag if ITEMS[it]["kind"] == "potion")

    def needs_rest(self, g):
        low_slots = any(p.can_cast and ((p.cls == "wizard" and not p.slot_ok(1)) or
                                        (p.cls == "cleric" and p.slots.get("1", [0, 0])[0] < 2)) for p in g.party if not p.dead)
        return self.hp_frac(g) < 0.7 or low_slots or any(p.downed for p in g.party)

    def area_done(self, g, aid):
        A = g.areas.get(aid)
        if A is None:
            return False
        if aid == "cellar":
            return not any(a.faction == "hostile" and a.conscious for a in A.actors)
        if aid == "forest":
            return g.flags.get("snagtooth_dead") and (g.flags.get("lysa_free") or g.in_party("lysa")
                                                       or getattr(A, "_pilot_done", False))
        if aid == "sanctum":
            return g.flags.get("corvane_dead")
        if aid == "lair":
            return g.flags.get("ashmaw_dead")
        return getattr(A, "_pilot_done", False)

    def target_area(self, g):
        """Where the story wants us next."""
        if g.area.id != getattr(self, "_last_area", None):
            self._last_area = g.area.id
            self.rest_tries.pop(g.area.id, None)
        if self.wants_town(g) and g.area.id != "town":
            return "town"
        if g.area.id == "town" and not self.town_done(g):
            return "town"
        if g.qstate("rats") and not self.area_done(g, "cellar"):
            return "cellar"
        for aid in ("forest", "mine1", "mine2", "sanctum", "lair"):
            if not self.area_done(g, aid):
                return aid
        return "lair"

    def wants_town(self, g):
        if g.area.id in ("town", "cellar") or self.ticks < self.calm_until:
            return False
        if g.hero.dead and g.gold < g.raise_cost:
            return False  # coming home now would end the story: earn the coin first
        dead = any(p.dead for p in g.party)
        if dead and g.gold >= g.raise_cost:
            return True
        between = g.area.id == "road" or self.area_done(g, g.area.id)
        if between and self.potions(g) < len(g.party) and g.gold >= 100:
            return True  # restock between chapters
        if self.hp_frac(g) < 0.35 and self.potions(g) == 0 and g.area.id in ("sanctum", "lair"):
            return True
        return False

    def town_done(self, g):
        town = g.areas.get("town")
        if not town or self.town_steps > 600:
            return True
        todo = [a for a in town.actors if a.npc and a.npc not in self.met and a.npc != "villager" and a.faction == "neutral"]
        if todo:
            return False
        if any(p.dead for p in g.party) and g.gold >= g.raise_cost and "aldous" in [a.npc for a in town.actors]:
            return False
        if self.needs_rest(g) and g.gold >= 10:
            return False
        if self.shopped_at != g.day and g.gold >= 60:
            return False
        if g.qstate("rats") == "active" and self.area_done(g, "cellar"):
            return False  # collect Hobb's reward
        b, l = g.flags.get("sq_bounty"), g.flags.get("sq_lost")
        if (b and g.qstate("bounty") == "active" and b["have"] >= b["need"] and ("t", "captain", g.day) not in self.fails) or \
                (l and g.qstate("lost") == "active" and l["item"] in g.bag):
            return False
        return True

    # --- movement -------------------------------------------------------------------------
    def passable(self, g, x, y, goals, relaxed=False):
        A = g.area
        if (x, y) in goals:
            return True
        t = A.tile(x, y)
        if t == T_DOOR:
            return True
        if not A.walkable(x, y):
            return False
        if (x, y) in A.links or t == T_EXIT:
            return False
        tr = A.traps.get((x, y))
        if tr and not tr["hidden"] and not relaxed:
            return False
        a = g.actor_at(x, y)
        return a is None or a.is_pc or relaxed  # relaxed: walk through foes (fight) and folk (wait)

    def path_step(self, g, goals, adjacent=False):
        """First step (dx, dy) of a shortest path to any goal; adjacent=True stops next to it.
        Tries a clean path first, then one across known traps and through creatures in the way."""
        st = self._path(g, goals, adjacent, False)
        return st if st is not None else self._path(g, goals, adjacent, True)

    def _path(self, g, goals, adjacent, relaxed):
        L = g.leader
        goals = set(goals)
        if not goals:
            return None
        start = (L.x, L.y)
        prev = {start: None}
        q = deque([start])
        found = None
        while q:
            cur = q.popleft()
            if (adjacent and any(cheb(cur[0], cur[1], gx, gy) == 1 for gx, gy in goals)) or (not adjacent and cur in goals and cur != start):
                found = cur
                break
            for dx, dy in DIRS8:
                n = (cur[0] + dx, cur[1] + dy)
                if n in prev or not g.area.inb(*n):
                    continue
                if not self.passable(g, n[0], n[1], () if adjacent else goals, relaxed):
                    continue
                prev[n] = cur
                q.append(n)
        if found is None:
            return None
        if found == start:
            return (0, 0)
        while prev[found] != start:
            found = prev[found]
        return (found[0] - start[0], found[1] - start[1])

    def bump(self, g, target):
        L = g.leader
        if cheb(L.x, L.y, target[0], target[1]) == 1:
            g.try_move(target[0] - L.x, target[1] - L.y)
            return True
        st = self.path_step(g, [target], adjacent=True)
        if st and st != (0, 0):
            g.try_move(*st)
            return True
        return False

    def tries(self, key, limit):
        """Count attempts at one target; False once it is clearly not working."""
        n = self.fails.get(key, 0) + 1
        self.fails[key] = n
        return n <= limit

    def over_counter(self, g, a):
        """Talk to someone behind a counter or table: walk up to it and lean over."""
        A = g.area
        L = g.leader
        stands = {}
        for dx, dy in DIRS8:
            c = (a.x - dx, a.y - dy)
            s_ = (a.x - 2 * dx, a.y - 2 * dy)
            if A.inb(*c) and A.inb(*s_) and A.tile(*c) in (T_COUNTER, T_TABLE) and self.passable(g, s_[0], s_[1], ()):
                stands[s_] = (dx, dy)
        if (L.x, L.y) in stands:
            g.try_move(*stands[(L.x, L.y)])
            return True
        return bool(stands) and self.walk(g, list(stands))

    def walk(self, g, goals):
        st = self.path_step(g, goals)
        if st and st != (0, 0):
            L = g.leader
            other = g.actor_at(L.x + st[0], L.y + st[1])
            if other and not other.is_pc and other.faction != "hostile":
                g.tick()  # someone is in the way: wait for them to move
                return True
            g.try_move(*st)
            return True
        return False

    # --- decisions --------------------------------------------------------------------------
    def setup(self, g):
        for p in g.party:
            p.ai = True

    def manage(self, g):
        """Equipment upgrades and potions outside combat."""
        self.setup(g)
        for p in g.party:
            if p.dead:
                continue
            for it in list(g.bag):
                if it not in g.bag:
                    continue
                d = ITEMS[it]
                if d["kind"] not in ("weapon", "armor", "shield", "ring", "amulet") or g.can_equip(p, it):
                    continue
                if self.gain(p, it) > 0.3:
                    g.equip(p, g.bag.index(it))
        if not g.combat:
            for p in g.party:
                if p.conscious and p.hp < p.max_hp * 0.35 and g.can_rest() and "potion" in g.bag:
                    g.use_item(p, g.bag.index("potion"))

    @staticmethod
    def score(p):
        w = p.weapon
        hit = clamp((21 - (14 - p.attack_bonus())) / 20.0, 0.05, 0.95)
        dmg = dice_avg(w["dmg"]) + p.damage_bonus()
        off = hit * dmg * p.attacks_per_turn
        if p.cls == "wizard":
            off *= 0.3
        return off + p.ac * 1.2

    def gain(self, p, it):
        slot = {"weapon": "weapon", "armor": "armor", "shield": "shield", "ring": "ring", "amulet": "amulet"}[ITEMS[it]["kind"]]
        if slot in ("ring", "amulet"):
            return 1.0 if not p.equip.get(slot) else 0.0
        before = self.score(p)
        old = p.equip.get(slot)
        p.equip[slot] = it
        after = self.score(p)
        p.equip[slot] = old
        return after - before

    def shop(self, g):
        """Greta: upgrades first, then potions. Keeps money for the inn and the temple."""
        self.shopped_at = g.day
        reserve = 30
        bought = []
        live = [p for p in g.party if not p.dead]
        while self.potions(g) < len(live) and g.gold - ITEMS["potion"]["price"] >= reserve:
            g.buy("potion")
            bought.append("Potion of Healing")
        for _ in range(4):
            best = None
            for p in g.party:
                if p.dead:
                    continue
                for it in SHOP_STOCK:
                    d = ITEMS[it]
                    if d["kind"] in ("potion", "scroll") or d["price"] > g.gold - reserve or g.can_equip(p, it):
                        continue
                    gain = self.gain(p, it)
                    if gain > 1.0:
                        v = gain / max(25, d["price"])
                        if best is None or v > best[0]:
                            best = (v, p, it)
            if not best:
                break
            _, p, it = best
            if g.buy(it):
                g.equip(p, g.bag.index(it))
                bought.append(ITEMS[it]["name"])
        want = 2 * len([p for p in g.party if not p.dead])
        while self.potions(g) < want and g.gold - ITEMS["potion"]["price"] >= reserve:
            g.buy("potion")
            bought.append("Potion of Healing")
        return bought

    def choose_dialogue(self, g, npc, node, opts):
        """Index of the option to pick."""
        self.met.add(npc)
        self.dlg_picks = getattr(self, "dlg_picks", 0) + 1
        ends = [i for i, o in enumerate(opts) if any(k in o[0].lower() for k in DLG_END) or o[1] is None]
        if self.dlg_picks > 12 and ends:  # safety net: never talk in circles
            return ends[-1]
        best, bi = -99, len(opts) - 1
        need_rest = self.needs_rest(g)
        for i, o in enumerate(opts):
            lab = o[0].lower()
            s = 0
            if any(k in lab for k in DLG_GOOD):
                s = 10
            elif any(k in lab for k in DLG_INFO):
                s = 4
            elif any(k in lab for k in DLG_BAD):
                s = -20
            elif any(k in lab for k in DLG_END):
                s = -5
            if "room for the night" in lab:
                s = 12 if need_rest and g.gold >= 10 else -10
            if "heal my companions" in lab:
                s = 12 if self.hp_frac(g) < 0.9 and g.gold >= 60 else -10
            if "raise a fallen" in lab:
                s = 15 if any(p.dead for p in g.party) and g.gold >= g.raise_cost else -10
            if ("come with me" in lab or "join" in lab) and len(g.party) >= 4:
                s = -10
            if "any work for me" in lab:
                s = 13
            if "show me your wares" in lab:
                s = 11 if self.shopped_at != g.day and g.gold >= 60 else -10
            if (npc, o[0]) in self.said and s < 11:
                s -= 30
            if s > best or (s == best and i in ends):
                best, bi = s, i
        self.said.add((npc, opts[bi][0]))
        return bi

    def choose_dest(self, g):
        """World map destination."""
        tgt = self.target_area(g)
        path = self.route(g.area.id if g.area.id != "road" else "world", tgt) or [tgt]
        for aid in path:
            if aid in WORLD_OF:
                loc = WORLD_OF[aid]
                if loc in g.discovered or aid == "forest":
                    return loc
                return "whisperwood"
        return WORLD_OF.get(tgt, "emberfall")

    @staticmethod
    def route(src, dst):
        prev = {src: None}
        q = deque([src])
        while q:
            c = q.popleft()
            if c == dst:
                out = []
                while c != src:
                    out.append(c)
                    c = prev[c]
                return out[::-1]
            for n in AREA_GRAPH.get(c, []):
                if n not in prev:
                    prev[n] = c
                    q.append(n)
        return None

    def step(self, g):
        """One exploration action outside combat."""
        self.dlg_picks = 0
        self.ticks += 1
        if self.watchdog(g):
            return
        A = g.area
        L = g.leader
        self.manage(g)
        tgt = self.target_area(g)
        here = A.id
        self.town_steps = self.town_steps + 1 if here == "town" else 0
        # rest when it is safe and needed (but do not get stuck in a loop of ambushes)
        if self.needs_rest(g) and here not in ("town",) and not g.can_rest() and self.rest_tries.get(here, 0) < 8:
            self.goal = "resting"
            self.rest_tries[here] = self.rest_tries.get(here, 0) + 1
            g.rest()
            return
        if here == "road":
            self.goal = "pressing on"
            return self.walk(g, [(x, y) for y in range(A.h) for x in range(A.w) if A.tiles[y][x] == T_EXIT and x > A.w // 2]) \
                or self.explore(g)
        if here == "town" and tgt == "town":
            return self.town_step(g)
        if here == tgt:
            return self.explore(g)
        # travel towards the target area
        path = self.route(here, tgt)
        nxt = path[0] if path else "world"
        self.goal = "heading for %s" % (AREA_NAMES.get(nxt, nxt))
        if nxt == "world":
            goals = [p for p, v in A.links.items() if v[0] == "world"]
            goals += [(x, y) for y in range(A.h) for x in range(A.w) if A.tiles[y][x] == T_EXIT and A.explored[y][x]]
            if not goals:
                goals = [(x, y) for y in range(A.h) for x in range(A.w) if A.tiles[y][x] == T_EXIT]
        else:
            goals = [p for p, v in A.links.items() if v[0] == nxt]
        if goals and self.walk(g, goals):
            return
        self.explore(g, force=True)

    def watchdog(self, g):
        """Notice when nothing has happened for a long time and break out of whatever loop that is."""
        A = g.area
        seen = sum(row.count(True) for row in A.explored)
        sig = (A.id, seen, g.kills, len(g.bag), g.gold, g.party_level(), len(g.party),
               tuple(sorted(k for k, v in g.flags.items() if v is True)))
        if sig != self.sig:
            self.sig, self.idle = sig, 0
            return False
        self.idle += 1
        if self.idle == 800:
            A._pilot_done = True                  # treat this place as finished
            for k in list(self.fails):
                self.fails[k] = 999               # give up on stubborn chests, items, people
            self.town_steps = 9999
            self.rest_tries[A.id] = 99
            self.calm_until = self.ticks + 3000   # no trips home for a while
            self.goal = "moving on"
        if self.idle >= 1500:
            foes = [a for a in A.actors if a.faction == "hostile" and a.conscious]
            if foes:  # last resort: go and settle it with whoever is left
                L = g.leader
                f = min(foes, key=lambda a: cheb(a.x, a.y, L.x, L.y))
                f.truce = 0
                self.fails = {k: v for k, v in self.fails.items() if k[0] != "f"}
                self.goal = "seeking out %s" % f.name
                if self.bump(g, (f.x, f.y)):
                    return True
            ways = list(A.links) + [(x, y) for y in range(A.h) for x in range(A.w) if A.tiles[y][x] == T_EXIT]
            self.goal = "looking for a way"
            if ways and self.walk(g, ways):
                return True
            dx, dy = self.rnd.choice(DIRS8)
            g.try_move(dx, dy)
            return True
        return False

    def town_step(self, g):
        A = g.area
        L = g.leader
        # who still needs a word: temple and inn first when needed, then everybody once
        want = []
        if any(p.dead for p in g.party) and g.gold >= g.raise_cost:
            want.append("aldous")
        if self.needs_rest(g) and g.gold >= 10:
            want.append("hobb")
        if self.shopped_at != g.day and g.gold >= 60:
            want.append("greta")
        if g.qstate("rats") == "active" and self.area_done(g, "cellar"):
            want.append("hobb")
            self.said.discard(("hobb", "Your cellar is clear of rats."))
        b, l = g.flags.get("sq_bounty"), g.flags.get("sq_lost")
        if b and g.qstate("bounty") == "active" and b["have"] >= b["need"]:
            want.append("captain")
        if l and g.qstate("lost") == "active" and l["item"] in g.bag:
            want.append(l["giver"])
        want += [a.npc for a in A.actors if a.npc and a.npc not in self.met and a.npc != "villager" and a.faction == "neutral"]
        for npc in want:
            a = next((x for x in A.actors if x.npc == npc), None)
            if a:
                self.goal = "visiting %s" % a.name
                if self.tries(("talk", npc, g.day), 150) and (self.bump(g, (a.x, a.y)) or self.over_counter(g, a)):
                    return
                self.met.add(npc)  # cannot reach them: give up on this one
        self.goal = "leaving town"
        tgt = "cellar" if (g.qstate("rats") and not self.area_done(g, "cellar")) else "world"
        goals = [p for p, v in A.links.items() if v[0] == tgt] if tgt == "cellar" else \
            [(x, y) for y in range(A.h) for x in range(A.w) if A.tiles[y][x] == T_EXIT]
        if not self.walk(g, goals):
            self.explore(g, force=True)

    def explore(self, g, force=False):
        A = g.area
        L = g.leader
        vis = g.visible
        foes = [a for a in A.actors if a.faction == "hostile" and a.conscious and (a.x, a.y) in vis
                and getattr(a, "truce", 0) <= g.steps and self.fails.get(("f", id(a)), 0) < 300]
        if foes:
            self.goal = "attacking"
            f = min(foes, key=lambda a: cheb(a.x, a.y, L.x, L.y))
            self.tries(("f", id(f)), 300)
            if self.bump(g, (f.x, f.y)):
                return
            self.fails[("f", id(f))] = 999  # cannot reach it
        items = [p for p, its in A.items.items() if its and A.explored[p[1]][p[0]] and self.fails.get(("i", A.id, p), 0) < 60]
        if items:
            i = min(items, key=lambda p: cheb(p[0], p[1], L.x, L.y))
            self.goal = "picking something up"
            self.tries(("i", A.id, i), 60)
            if self.walk(g, [i]):
                return
            self.fails[("i", A.id, i)] = 99
        boxes = [(x, y) for y in range(A.h) for x in range(A.w) if A.tiles[y][x] in (T_CHEST, T_CAGEDOOR)
                 and A.explored[y][x] and self.fails.get(("c", A.id, (x, y)), 0) < 4]
        if boxes:
            b = min(boxes, key=lambda p: cheb(p[0], p[1], L.x, L.y))
            self.goal = "opening a chest" if A.tiles[b[1]][b[0]] == T_CHEST else "opening the cage"
            if cheb(L.x, L.y, b[0], b[1]) == 1:
                self.fails[("c", A.id, b)] = self.fails.get(("c", A.id, b), 0) + 1
            if self.bump(g, b):
                return
            self.fails[("c", A.id, b)] = 9
        notes = [p for p, v in A.notes.items() if v == "edrin" and not g.flags.get("edrin_found")]
        if notes and A.explored[notes[0][1]][notes[0][0]] and self.walk(g, notes):
            self.goal = "investigating"
            return
        # frontier: walkable cells next to unexplored ones
        front = []
        for y in range(A.h):
            row = A.explored[y]
            for x in range(A.w):
                if row[x] and (A.walkable(x, y) or A.tiles[y][x] == T_DOOR) and (x, y) not in A.links and A.tiles[y][x] != T_EXIT:
                    for dx, dy in DIRS8:
                        nx, ny = x + dx, y + dy
                        if A.inb(nx, ny) and not A.explored[ny][nx]:
                            front.append((x, y))
                            break
        front = [p for p in front if p != (L.x, L.y)]
        if front:
            self.goal = "exploring %s" % A.name
            if self.walk(g, front):
                return
        # nothing left to see: hunt remaining foes we know about, then call it done
        rest = [a for a in A.actors if a.faction == "hostile" and a.conscious and getattr(a, "truce", 0) <= g.steps
                and self.fails.get(("f", id(a)), 0) < 300]
        if rest and A.id in ("sanctum", "lair", "forest"):
            self.goal = "searching for the enemy"
            if self.bump(g, min(((a.x, a.y) for a in rest), key=lambda p: cheb(p[0], p[1], L.x, L.y))):
                return
        A._pilot_done = True
        self.goal = "done here"
        if force:
            dx, dy = self.rnd.choice(DIRS8)
            g.try_move(dx, dy)


AREA_NAMES = {"town": "Emberfall", "cellar": "the cellar", "forest": "the Whisperwood", "mine1": "Deepdelve Mine",
              "mine2": "the Lower Galleries", "sanctum": "the Sanctum", "lair": "Ashmaw's Lair", "world": "the road"}


def pilot_pending(g, pilot):
    """Resolve pending events without a screen (balance runs)."""
    while g.pending:
        p = g.pending.popleft()
        if p[0] == "talk":
            npc = p[1]
            spk, port, nodes = dlg_villager(g, "x") if npc == "villager" else get_dialogue(g, npc)
            node = "start"
            for _ in range(14):
                if node not in nodes:
                    break
                text, opts = nodes[node]
                if callable(text):
                    text()
                opts = [o for o in opts if not o[2] or o[2]()]
                if not opts:
                    break
                tgt = opts[pilot.choose_dialogue(g, npc, node, opts)][1]
                if callable(tgt):
                    tgt = tgt()
                if not tgt:
                    break
                node = tgt
                spk, port, nodes = dlg_villager(g, "x") if npc == "villager" else get_dialogue(g, npc)
            g.check_hostiles()
        elif p[0] == "world":
            g.travel_to(pilot.choose_dest(g))
        elif p[0] == "shop":
            pilot.shop(g)
        elif p[0] in ("gameover", "victory"):
            g.pending.clear()
            return


def play_campaign(seed, race=None, cls=None, limit=90000, diff="normal"):
    """One full autopilot campaign without a screen; returns a statistics dict."""
    rnd = random.Random(seed)
    race = race or rnd.choice(list(RACES))
    cls = cls or rnd.choice(list(CLASSES))
    random.seed(seed)
    st = {"seed": seed, "hero": "%s %s" % (race, cls), "outcome": "timeout", "where": None, "entry_level": {},
          "deaths": Counter(), "killers": Counter(), "taken": Counter(), "dealt": Counter(), "kills": Counter(),
          "by_class": Counter(), "potions": 0, "bought": Counter(), "spent": 0, "raises": 0, "inn": 0, "rests": 0,
          "ambushes": 0, "fights": Counter(), "level": 1, "day": 1, "steps": 0, "gold": 0}
    orig = {k: getattr(Game, k) for k in ("damage", "die", "kill", "use_item", "buy", "rest", "ambush", "temple_raise",
                                         "inn_rest", "enter_area", "start_combat")}
    last_hit = {}

    def damage(self, t, n, dtype, src=None, crit=False):
        before = max(0, t.hp)
        r = orig["damage"](self, t, n, dtype, src, crit)
        d = before - max(0, t.hp)
        if src is not None and d > 0:
            if t.is_pc:
                st["taken"][src.tmpl or src.name] += d
                last_hit[id(t)] = src.tmpl or src.name
            elif src.is_pc:
                st["dealt"][t.tmpl or t.name] += d
                st["by_class"][src.cls] += d
        return r

    def die(self, p):
        st["deaths"][self.area.id] += 1
        st["killers"][last_hit.get(id(p), "?")] += 1
        return orig["die"](self, p)

    def kill(self, t, src=None):
        st["kills"][t.tmpl or t.name] += 1
        return orig["kill"](self, t, src)

    def use_item(self, user, idx, target=None):
        if ITEMS[self.bag[idx]]["kind"] == "potion":
            st["potions"] += 1
        return orig["use_item"](self, user, idx, target)

    def buy(self, it):
        ok = orig["buy"](self, it)
        if ok:
            st["bought"][it] += 1
            st["spent"] += ITEMS[it]["price"]
        return ok

    def rest(self, safe=False):
        st["rests"] += 1
        return orig["rest"](self, safe)

    def ambush(self):
        st["ambushes"] += 1
        return orig["ambush"](self)

    def temple_raise(self):
        ok = orig["temple_raise"](self)
        st["raises"] += bool(ok)
        return ok

    def inn_rest(self):
        ok = orig["inn_rest"](self)
        st["inn"] += bool(ok)
        return ok

    def enter_area(self, aid, entry=None):
        if aid != "world" and aid not in st["entry_level"] and self.party:
            st["entry_level"][aid] = self.party_level()
        return orig["enter_area"](self, aid, entry)

    def start_combat(self, force=()):
        if not self.combat:
            st["fights"][self.area.id] += 1
        return orig["start_combat"](self, force)

    for k, f in list(locals().items()):
        if k in orig:
            setattr(Game, k, f)
    try:
        g = Game(seed=seed)
        g.new_game(make_pc("Hero", race, cls, assign_stats(roll_stats(), cls)), diff)
        pilot = Autopilot(seed)
        steps = 0
        tail = deque(maxlen=3000)
        while steps < limit and not g.over:
            steps += 1
            pilot_pending(g, pilot)
            if g.over:
                break
            if g.combat:
                tail.append(("combat r%d" % min(g.combat["round"], 99) if g.combat["round"] > 30 else "combat", g.area.id))
                g.step_ai()
            else:
                tail.append((pilot.goal, g.area.id))
                pilot.step(g)
            g.events.clear()
        if steps >= limit:
            st["tail"] = Counter(tail).most_common(4)
            st["tail_pos"] = (g.area.id, g.leader.x, g.leader.y, g.day, g.gold, [p.name[:6] + ("+" if p.dead else "") for p in g.party])
        st["side"] = (g.qstate("bounty"), g.qstate("lost"), g.flags["sq_bounty"]["mon"], g.flags["sq_lost"]["item"])
        st["outcome"] = {"won": "won", "dead": "dead"}.get(g.over, "timeout")
        st["lost_by"] = None if g.over != "dead" else ("no coin" if g.area.id == "town" else "wipe")
        st["where"] = g.area.id
        st["level"], st["day"], st["steps"], st["gold"] = g.party_level(), g.day, steps, g.gold
    finally:
        for k, f in orig.items():
            setattr(Game, k, f)
    return st


def _sim_worker(args):
    try:
        return play_campaign(*args)
    except Exception as ex:  # report, do not kill the whole run
        import traceback
        return {"error": "%s: %s" % (type(ex).__name__, ex), "trace": traceback.format_exc(), "seed": args[0]}


def simulate(n=40, seed0=1000, race=None, cls=None, jobs=None, diff="normal"):
    """Run n autopilot campaigns in parallel and print a balance report."""
    import multiprocessing as mp
    t0 = time.time()
    jobs = jobs or max(1, (os.cpu_count() or 2) - 1)
    args = [(seed0 + i, race, cls, 90000, diff) for i in range(n)]
    with mp.get_context("fork").Pool(jobs) as pool:
        runs = pool.map(_sim_worker, args)
    errs = [r for r in runs if "error" in r]
    runs = [r for r in runs if "error" not in r]
    out = Counter(r["outcome"] for r in runs)
    print("=== %d campaigns, %.0fs (%d errors) ===" % (len(runs), time.time() - t0, len(errs)))
    for e_ in errs[:3]:
        print("ERROR seed %s: %s\n%s" % (e_["seed"], e_["error"], e_["trace"][-600:]))
    if not runs:
        return runs
    print("Won %d (%.0f%%)  died %d  stuck %d" % (out["won"], 100.0 * out["won"] / len(runs), out["dead"], out["timeout"]))
    lb = Counter(r.get("lost_by") for r in runs if r["outcome"] == "dead")
    print("Defeats: whole party fell %d, came home with a dead hero and no coin %d" % (lb["wipe"], lb["no coin"]))
    where = Counter(r["where"] for r in runs if r["outcome"] == "dead")
    print("Party wiped in:", ", ".join("%s %d" % kv for kv in where.most_common()))
    stuck = Counter(r["where"] for r in runs if r["outcome"] == "timeout")
    if stuck:
        print("Stuck in:", ", ".join("%s %d" % kv for kv in stuck.most_common()))
        for r in runs:
            if r["outcome"] == "timeout":
                print("   seed %d %s: %s  %s" % (r["seed"], r["hero"], r.get("tail_pos"), r.get("tail")))
    print("\nArea      reached  avg level  fights/run  member deaths/run")
    for aid in ["cellar", "forest", "road", "mine1", "mine2", "sanctum", "lair"]:
        got = [r for r in runs if aid in r["entry_level"]]
        if not got:
            continue
        print("%-9s %5d %9.1f %10.1f %12.2f" % (aid, len(got), sum(r["entry_level"][aid] for r in got) / len(got),
                                                 sum(r["fights"][aid] for r in got) / len(got),
                                                 sum(r["deaths"][aid] for r in got) / len(got)))
    tk, dl, ki, kl = Counter(), Counter(), Counter(), Counter()
    for r in runs:
        tk.update(r["taken"]); dl.update(r["dealt"]); ki.update(r["kills"]); kl.update(r["killers"])
    print("\nMonster          dmg to party/kill  party dmg taken  times killed  heroes it killed")
    for m in sorted(ki, key=lambda m: -tk[m]):
        print("%-16s %12.1f %16d %13d %12d" % (m, tk[m] / max(1, ki[m]), tk[m], ki[m], kl[m]))
    bc = Counter()
    for r in runs:
        bc.update(r["by_class"])
    print("\nDamage dealt by class (all runs):", ", ".join("%s %d" % kv for kv in bc.most_common()))
    avg = lambda k: sum(r[k] for r in runs) / len(runs)
    print("Per run: potions %.1f, spent %.0f gold, end gold %.0f, rests %.1f, ambushes %.1f, inn %.1f, raises %.1f, "
          "days %.1f, final level %.1f" % (avg("potions"), avg("spent"), avg("gold"), avg("rests"), avg("ambushes"),
                                           avg("inn"), avg("raises"), avg("day"), avg("level")))
    sb, sl = Counter(r["side"][0] for r in runs), Counter(r["side"][1] for r in runs)
    print("Side quests - bounty: %s | lost item: %s | rolled: %s" % (dict(sb), dict(sl),
          ", ".join("%s %d" % kv for kv in Counter(r["side"][2] + "/" + r["side"][3] for r in runs).most_common(6))))
    bought = Counter()
    for r in runs:
        bought.update(r["bought"])
    print("Bought:", ", ".join("%s %d" % kv for kv in bought.most_common(12)))
    heroes = {}
    for r in runs:
        heroes.setdefault(r["hero"].split()[1], []).append(r["outcome"] == "won")
        heroes.setdefault(r["hero"].split()[0], []).append(r["outcome"] == "won")
    print("Win rate by hero:", ", ".join("%s %d%% (%d)" % (h, 100 * sum(v) / len(v), len(v)) for h, v in sorted(heroes.items())))
    return runs


# =============================================================================
# Headless self-test and balance simulation
# =============================================================================
def _party(level, seed=0):
    random.seed(seed)
    pc = make_pc("Hero", "human", "fighter", assign_stats([15, 14, 13, 12, 10, 8], "fighter"), level=1)
    while pc.level < level:
        pc.level += 1
        pc.recompute(heal=True)
    party = [pc] + [make_companion(c, level, i + 1) for i, c in enumerate(["maren", "tamsin", "lysa"])]
    for p in party:
        p.ai = True
    return party


def _fight(g, force, limit=3000):
    g.start_combat(force=force)
    n = 0
    while g.combat and n < limit:
        g.step_ai()
        g.events.clear()
        n += 1
    g.pending.clear()
    return g.over != "dead" and n < limit


def _resolve_pending_headless(g, rnd):
    while g.pending:
        p = g.pending.popleft()
        if p[0] == "talk":
            npc = p[1]
            spk, port, nodes = dlg_villager(g, "x") if npc == "villager" else get_dialogue(g, npc)
            node = "start"
            for _ in range(8):
                if node not in nodes:
                    break
                text, opts = nodes[node]
                if callable(text):
                    text()
                opts = [o for o in opts if not o[2] or o[2]()]
                if not opts:
                    break
                tgt = rnd.choice(opts)[1]
                if callable(tgt):
                    tgt = tgt()
                if not tgt:
                    break
                node = tgt
                spk, port, nodes = dlg_villager(g, "x") if npc == "villager" else get_dialogue(g, npc)
            g.check_hostiles()
        elif p[0] == "world":
            dest = rnd.choice(g.discovered)
            g.travel_to(dest)
        elif p[0] == "shop":
            if g.gold >= 50:
                g.buy("potion")


def selftest(verbose=True):
    fails = []

    def check(cond, what):
        if not cond:
            fails.append(what)

    t0 = time.time()
    # 1) every area is well formed
    for seed in range(4):
        g = Game(seed=seed * 7919)
        g.new_game(make_pc("T", "elf", "wizard", assign_stats(roll_stats(), "wizard")))
        for aid in ["town", "cellar", "forest", "mine1", "mine2", "sanctum", "lair"]:
            A = g.generate(aid)
            start = list(A.entries.values())[0]
            reach = bfs_dist(A, [start], doors=True)
            for name, pos in A.entries.items():
                check(A.walkable(*pos), "%s entry %s not walkable" % (aid, name))
                check(pos in reach or aid == "sanctum", "%s entry %s unreachable" % (aid, name))
            for pos in A.links:
                near = any((pos[0] + dx, pos[1] + dy) in reach for dx, dy in DIRS8) or pos in reach
                check(near, "%s link %s unreachable" % (aid, pos))
            for a in A.actors:
                check(A.walkable(a.x, a.y), "%s: %s stands in a wall" % (aid, a.name))
            for y in range(A.h):
                for x in range(A.w):
                    if A.tiles[y][x] == T_EXIT:
                        check((x, y) in reach, "%s exit %d,%d unreachable" % (aid, x, y))
            if aid == "forest":
                door = next(p for p, v in A.notes.items() if v == "cage")
                check(any((door[0] + dx, door[1] + dy) in reach for dx, dy in DIRS8), "forest cage door unreachable")
                check(any(a.tmpl == "snagtooth" for a in A.actors), "forest has no Snagtooth")
            if aid in ("mine1", "mine2"):
                check(A.links.get(A.stair_down) is not None, "%s has no way down" % aid)
        for kind in ("wolves", "goblins", "bandits"):
            A = gen_encounter(seed, 2, kind)
            reach = bfs_dist(A, [A.entries["west"]])
            check(any(A.tiles[y][A.w - 1] == T_EXIT and (A.w - 1, y) in reach for y in range(A.h)), "encounter has no exit")

    # 2) dialogue trees can be walked without errors
    rnd = random.Random(5)
    for rep in range(30):
        g = Game(seed=rep)
        g.new_game(make_pc("T", "human", "rogue", assign_stats(roll_stats(), "rogue")))
        g.gold = rnd.choice([0, 5, 500])
        g.bag.append("locket")
        for npc in list(DIALOGUES) + ["villager"]:
            g.pending.append(("talk", npc))
            _resolve_pending_headless(g, rnd)
        check(len(g.party) <= 4, "party too large")

    # 3) save / load round trip
    g = Game(seed=99)
    g.new_game(make_pc("Saver", "dwarf", "cleric", assign_stats(roll_stats(), "cleric")))
    g.enter_area("forest", "west")
    g.recruit("brannoc")
    g.update_fov()
    d1 = json.dumps(g.to_dict(), sort_keys=True)
    g2 = Game.from_dict(json.loads(d1))
    d2 = json.dumps(g2.to_dict(), sort_keys=True)
    check(d1 == d2, "save/load round trip differs")

    # 4) random exploration with an AI party
    for seed in range(3):
        random.seed(seed)
        g = Game(seed=seed)
        pc = make_pc("Walker", "halfling", "rogue", assign_stats(roll_stats(), "rogue"))
        g.new_game(pc)
        for c in ("brannoc", "tamsin", "maren"):
            g.recruit(c)
        for p in g.party:
            p.ai = True
        for aid in ("forest", "mine1", "mine2"):
            g.enter_area(aid, None)
            for step in range(700):
                if g.over:
                    break
                _resolve_pending_headless(g, rnd)
                if g.combat:
                    while g.combat and not g.over:
                        g.step_ai()
                        g.events.clear()
                    continue
                dx, dy = rnd.choice(DIRS8)
                g.try_move(dx, dy)
                g.events.clear()
                for p in g.party:
                    if not p.dead:
                        check(p.hp <= p.max_hp, "hp above max")
                        check(g.area.walkable(p.x, p.y) or g.area.tile(p.x, p.y) == T_ODOOR, "party member in wall")
            if g.over:
                break
            for p in g.party:
                if p.dead:
                    p.dead, p.hp = False, 1
                p.rest()

    # 5) balance: a full campaign run with an AI party, area by area
    report = []
    wins = 0
    for seed in range(6):
        random.seed(seed)
        g = Game(seed=seed * 31)
        pc = make_pc("Hero", "human", "fighter", assign_stats([15, 14, 13, 12, 10, 8], "fighter"))
        g.new_game(pc)
        g.recruit("brannoc")
        g.recruit("tamsin")
        g.areas["town"].actors.append(make_npc("maren", "Sister Maren", g.leader.x + 1, g.leader.y + 1))
        g.recruit("maren")
        for p in g.party:
            p.ai = True
        for npc in ("snagtooth", "corvane", "ashmaw"):
            g.flags["talked_" + npc] = True
        ok = True
        stages = []
        for aid in ("cellar", "forest", "mine1", "mine2", "sanctum", "lair"):
            for p in g.party:
                if not p.dead:
                    p.rest()
            g.enter_area(aid, None)
            g.pending.clear()
            if g.combat:
                ok = _fight(g, []) and ok
            guard = 0
            while not g.over and guard < 60:
                guard += 1
                foes = [a for a in g.area.actors if a.faction == "hostile" and a.conscious]
                if not foes:
                    break
                L = g.leader
                m = min(foes, key=lambda a: cheb(a.x, a.y, L.x, L.y))
                spots = g.free_near(m.x, m.y, 1)
                if spots:
                    g.place_party(*spots[0])
                g.update_fov()
                if not _fight(g, [m]):
                    ok = False
                    break
                for p in g.party:
                    if p.dead and p is not g.leader:
                        p.dead, p.hp = False, 1  # temple visit
                if g.party_level() < 5 and random.random() < 0.5:
                    for p in g.party:
                        if not p.dead:
                            p.rest()
            stages.append("%s:L%d%s" % (aid, g.party_level(), "" if not g.over else "X"))
            if g.over == "dead":
                ok = False
                break
        report.append(" ".join(stages))
        if ok and g.flags.get("ashmaw_dead"):
            wins += 1
    took = time.time() - t0
    if verbose:
        print("Campaign simulations (AI party, rests between fights):")
        for r in report:
            print("   ", r)
        print("Dragon slain in %d of %d simulated campaigns." % (wins, len(report)))
        print("%d checks failed, %.1fs." % (len(fails), took))
        for f in sorted(set(fails))[:30]:
            print("  FAIL:", f)
    return not fails


def dump_art():
    for k in ["dragon", "ashmaw"] + list(PORTRAITS) + list(SCENES) + ["world"]:
        lines, fg, pal = art_lines(k)
        print("== %s (%dx%d)" % (k, max(len(l) for l in lines), len(lines)))
        print("\n".join(lines))
    for l in banner("EMBERFALL"):
        print(l)


def main():
    args = sys.argv[1:]
    if "--selftest" in args:
        sys.exit(0 if selftest() else 1)
    if "--simulate" in args:
        i = args.index("--simulate")
        n = int(args[i + 1]) if i + 1 < len(args) and args[i + 1].isdigit() else 40
        hero = args[args.index("--hero") + 1].split("_") if "--hero" in args else [None, None]
        diff = args[args.index("--diff") + 1] if "--diff" in args else "normal"
        simulate(n, race=hero[0], cls=hero[-1] if len(hero) > 1 else None, diff=diff)
        return
    if "--ascii" in args:
        os.environ["EMBERFALL_ASCII"] = "1"
    if "--art" in args:
        dump_art()
        return
    bot = 0
    save = SAVE_PATH
    if "--bot" in args:
        i = args.index("--bot")
        bot = int(args[i + 1]) if i + 1 < len(args) else 600
        save = os.path.join(os.path.expanduser("~"), ".emberfall_bot_save.json")
    start = args[args.index("--start") + 1] if "--start" in args else None
    watch = "--watch" in args
    locale.setlocale(locale.LC_ALL, "")
    os.environ.setdefault("ESCDELAY", "25")
    try:
        curses.wrapper(play, bot, save, start, watch)
    except BotDone:
        print("Bot finished %d frames without errors." % bot)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
