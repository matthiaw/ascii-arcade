#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""LEAFLING - a little jump'n'run with a leaf for a hat.

Leafling is a tiny sprite who wears a leaf. Run and jump through twelve levels in four worlds (a sunlit forest
canopy, glowing crystal caves, wind-swept sky ruins and an autumn storm at night), glide on your leaf, slide down
mossy walls and jump off them, collect light motes and find the three hidden seeds in every level.

Keys:  Left / Right (A / D) run    Space / Up / W / Z jump    jump again in the air: glide
       Down (S) drop through thin platforms / stop    R back to the last lantern
       Esc / P pause menu (Q there: quit, M there: sound on / off)    ? help

In terminals with the kitty keyboard protocol (kitty, WezTerm, Ghostty, recent iTerm2) keys are read with their
releases: hold jump longer to jump higher, hold it in the air to glide. Elsewhere (macOS Terminal) a direction
key keeps you running while it repeats, jumps are always full and jump in the air switches the glide on / off.

Part of the ASCII ARCADE. Pure Python 3, no dependencies (macOS / Linux, truecolor terminal recommended).
Run:        python3 leafling.py
Self-test:  python3 leafling.py --selftest     (plans a route through every level with the real physics)
Benchmark:  python3 leafling.py --bench
"""
import heapq
import math
import os
import random
import re
import select
import sys
import time

import arcadekit
from arcadekit import Canvas, clamp, load_scores, mix, overlay, shade, shared_key, submit, title_screen

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

GAME = "leafling"


def _motes():
    """Eight tiny chimes on a rising pentatonic scale: quick chains of motes climb the scale."""
    out = {}
    for i, semi in enumerate((0, 2, 4, 7, 9, 12, 14, 16)):
        f = 1046.5 * 2 ** (semi / 12)
        out["mote%d" % i] = [dict(w="sine", f=f, d=0.035, v=0.26), dict(w="tri", f=f * 2, d=0.03, v=0.08, at=0)]
    return out


# ---- sound effects: short and soft, nothing per frame, the demo and the self-test stay silent ------------------
SND = Sound(GAME, dict(_motes(), **{
    "jump": [dict(w="tri", f=440, f2=760, d=0.04, v=0.3)],
    "glide": [dict(w="noise", f=5200, f2=2400, d=0.04, v=0.12, r="lin"),
              dict(w="tri", f=620, f2=820, d=0.04, v=0.14, vib=(40, 0.8), at=0)],
    "land": [dict(w="noise", f=700, f2=180, d=0.03, v=0.16)],
    "walljump": [dict(w="tri", f=380, f2=900, d=0.04, v=0.3), dict(w="noise", f=3800, d=0.02, v=0.1, at=0)],
    "seed": [dict(w="tri", f=1568, d=0.05, v=0.3), dict(w="tri", f=2093, d=0.05, v=0.3),
             dict(w="tri", f=2637, d=0.05, v=0.3), dict(w="sine", f=3136, d=0.3, v=0.22, vib=(9, 0.4))],
    "checkpoint": [dict(w="tri", f=659, d=0.07, v=0.34), dict(w="tri", f=988, d=0.07, v=0.34),
                   dict(w="sine", f=1319, d=0.3, v=0.26, vib=(6, 0.2))],
    "spring": [dict(w="sine", f=160, f2=560, d=0.16, v=0.42, vib=(16, 1.2)), dict(w="tri", f=320, f2=700, d=0.1, v=0.12, at=0)],
    "stomp": [dict(w="square", f=330, f2=120, d=0.06, v=0.26, duty=0.25), dict(w="noise", f=1800, f2=400, d=0.05, v=0.16, at=0)],
    "hurt": [dict(w="saw", f=620, f2=210, d=0.18, v=0.26), dict(w="noise", f=2400, f2=500, d=0.12, v=0.12, at=0)],
    "death": [dict(w="tri", f=660, f2=520, d=0.1, v=0.3), dict(w="tri", f=520, f2=390, d=0.12, v=0.3),
              dict(w="tri", f=390, f2=260, d=0.3, v=0.3, r="lin")],
    "clear": [dict(w="tri", f=523, d=0.09), dict(w="tri", f=659, d=0.09), dict(w="tri", f=784, d=0.09),
              dict(w="tri", f=1047, d=0.09), dict(w="square", f=1319, d=0.4, v=0.24, duty=0.25, vib=(6, 0.2)),
              dict(w="tri", f=659, d=0.4, v=0.25, at=0.36)],
    "biome": [dict(w="tri", f=392, d=0.12), dict(w="tri", f=523, d=0.12), dict(w="tri", f=659, d=0.12),
              dict(w="tri", f=784, d=0.12), dict(w="tri", f=1047, d=0.12), dict(w="tri", f=784, d=0.12),
              dict(w="square", f=1047, d=0.7, v=0.26, duty=0.25, vib=(5, 0.25)),
              dict(w="tri", f=523, d=0.7, v=0.3, at=0.72), dict(w="tri", f=659, d=0.7, v=0.22, at=0.72)],
    "crumble": [dict(w="noise", f=900, f2=300, d=0.1, v=0.16, r="lin")],
    "spit": [dict(w="square", f=520, f2=260, d=0.03, v=0.14, duty=0.3)],
    "boss": [dict(w="saw", f=110, f2=70, d=0.35, v=0.26, vib=(7, 0.6)), dict(w="square", f=55, d=0.35, v=0.14, at=0)],
    "bosshit": [dict(w="square", f=220, f2=880, d=0.08, v=0.3, duty=0.25), dict(w="noise", f=2600, f2=600, d=0.16, v=0.2, at=0)],
    "bump": [dict(w="noise", f=500, f2=90, d=0.22, v=0.3)],
    "gate": [dict(w="tri", f=392, d=0.1), dict(w="tri", f=587, d=0.1), dict(w="sine", f=784, d=0.35, v=0.3)],
    "thunder": [dict(w="noise", f=260, f2=60, d=0.8, v=0.22, a=0.04, r="lin")],
    "tick": [dict(w="square", f=880, d=0.03, v=0.22, duty=0.25)],
    "start": [dict(w="square", f=659, d=0.05, v=0.26, duty=0.25), dict(w="square", f=988, d=0.12, v=0.26, duty=0.25)],
}))

# =============================================================================================
# Physics (units: tiles and seconds, fixed steps of 1/60 s - the self-test plans with exactly this)
# =============================================================================================
DT = 1 / 60
HW, PH = 0.35, 1.2           # half width and height of Leafling's body
RUN_MAX = 7.0
ACC_G, DEC_G, TURN_G = 70.0, 62.0, 125.0     # on the ground: speed up, friction, turning round
ACC_A, DEC_A, TURN_A = 44.0, 10.0, 62.0      # in the air
GRAV, GRAV_FALL = 55.0, 68.0
JUMP_V, JUMP_CUT = 19.0, 0.45
APEX_V, APEX_MUL = 2.6, 0.5  # apex hang: gentler gravity near the top of a jump while jump is held
MAX_FALL = 21.0
GLIDE_FALL, GLIDE_MAX, GLIDE_BRAKE = 2.6, 6.2, 75.0
WALL_SLIDE, WJ_VX, WJ_VY, WJ_LOCK = 3.0, 8.2, 17.0, 9
COYOTE_F, BUFFER_F = 6, 7    # 0.1 s and about 0.12 s
SPRING_V, STOMP_V = 28.5, 15.0
CRUMBLE_GONE, CRUMBLE_BACK = 30, 180
PERIOD = 300                 # every moving thing repeats after 5 s
CHASE_V = 4.4
BOSS_W, BOSS_H = 2.2, 1.6

E_, SOL, MOSS, CRUM, ONE, THU, THD, WAT, GATE, HID = range(10)
TILECODE = {"#": SOL, "M": MOSS, "C": CRUM, "=": ONE, "^": THU, "v": THD, "~": WAT, "G": GATE, "H": HID}
STOPS = "!#MCG="
WAIT, WINDUP, CHARGE, STUN, HURT, DEAD = range(6)


def tri(u):
    u %= 1.0
    return 2 * u if u < 0.5 else 2 - 2 * u


def gust(f):
    """Strength 0..1 of the sky-ruin wind at frame f: calm, a gust builds, blows, fades."""
    u = f % PERIOD
    if u < 120:
        return 0.0
    if u < 150:
        return (u - 120) / 30
    if u < 240:
        return 1.0
    if u < 270:
        return (270 - u) / 30
    return 0.0


def hcat(*blocks, w=20):
    """Glue map blocks (multi-line strings of equal height, w columns each; a block may say otherwise with a
    first line '<24>') side by side."""
    cols = []
    for b in blocks:
        lines = b.strip("\n").split("\n")
        bw = w
        if lines[0].startswith("<"):
            bw = int(lines.pop(0).strip("<> "))
        assert all(len(l) <= bw for l in lines), "a map line is wider than its block: %r" % lines
        cols.append([l.ljust(bw) for l in lines])
    h = len(cols[0])
    assert all(len(c) == h for c in cols), "map blocks differ in height: %s" % [len(c) for c in cols]
    return ["".join(c[i] for c in cols) for i in range(h)]


# =============================================================================================
# The levels: text maps glued together from 20-column blocks
#   #  ground          M  mossy wall (slide + wall-jump)   H  hidden passage (looks like ground)
#   =  thin platform (Down drops through)   C  crumbling block   ^ v  thorns   ~  water
#   o  light mote      S  seed (3 per level)   L  lantern checkpoint   T  springy mushroom
#   P  platform moving sideways, I  moving up and down (a run of letters = its width), ! where it turns
#   b  beetle   a  bat   f / F  spitting plant facing left / right   B  boss   G  boss gate
#   @  start    E  exit (the leaf gate)   K  chase trigger column
# =============================================================================================
BIOMES = ["Sunlit Canopy", "Crystal Caves", "Sky Ruins", "Autumn Storm"]

CANOPY_1 = hcat("""
                    
                    
                    
                    
                    
                    
                    
                    
             o o    
           o     o  
                    
   @                
##########   #######
##########~~~#######
##########~~~#######
####################
""", """
                    
                    
                    
                    
                    
                    
         o o o      
                    
                    
        =======  ###
                 ###
   o o  b    #######
####################
####################
####################
####################
""", """
                    
                    
                    
                    
                    
       o   o   o    
                    
                    
  L     ===   ===   
#####               
#####               
#####               
#####               
#####~~~~~~~~~~~~~~~
#####~~~~~~~~~~~~~~~
####################
""", """
                    
                    
                    
         S          
                    
       =====        
          o         
          o         
          o     ####
                HH##
L o o     T     HS##
####################
####################
####################
####################
####################
""", """
                    
                    
                    
                    
                    
                    
   o  o  o          
                    
      S             
     ==             
           #########
           #########
~~~~~~~~~~~#########
~~~~~~~~~~~#########
~~~~~~~~~~~#########
####################
""", """
                    
                    
                    
                    
                    
                    
                    
                    
          o o       
      b          E  
####################
####################
####################
####################
####################
####################
""")

CANOPY_2 = hcat("""
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
              o o   
                    
         ===        
  @         o o     
                 f  
####################
####################
####################
""", """
                    
                    
     o              
  S                 
  #M   M############
  #M o M############
  #M   M############
  #M o M############
  #M   M############
  #M o M############
  #M   M############
  #M o M############
  #M   M############
       M############
       M############
####################
####################
####################
""", """
                    
     ===      ===   
      a        a    
L      o    o    o  
##  CCC  CCC  CCC  #
##                 #
##                 #
##                 #
##                 #
##                 #
##                 #
##                 #
##                 #
##~~~~~~~~~~~~~~~~~#
##~~~~~~~~~~~~~~~~~#
####################
####################
####################
""", """
                    
                    
                    
                    
####                
####   o            
####  =====         
####         o      
####        ====    
####                
####   ========     
####                
####   S       o    
####   ===          
####           b  L 
####################
####################
####################
""", """
                    
                    
                    
                    
                    
                    
            o o     
                  f 
                 ###
           ===== ###
      o o        ###
                 ###
     =====       ###
  o           o  HH#
                 HS#
#####^^^^^##########
####################
####################
""", """
                    
                    
                    
                    
                    
                    
     o o o          
                    
          b     E   
####################
####################
####################
####################
####################
####################
####################
####################
####################
""")

CANOPY_3 = hcat("""
                    
                    
                    
                    
                    
      S             
     ===            
                    
          o o       
         ===        
                    
  @    o o         K
####################
####################
####################
####################
""", """
                    
                    
                    
                    
                    
                    
                    
                    
        o o o       
                    
                    
              ^^    
######   ###########
######~~~###########
######~~~###########
####################
""", """
                    
                    
                    
           S        
                    
                    
      o o o o       
                    
    =====    =====  
                    
                    
   T     ^^^^^^^^^^^
####################
####################
####################
####################
""", """
                    
                    
                    
                    
                    
                    
                    
    o o o           
                    
                    
              L     
^^^^^^^^^^^#########
####################
####################
####################
####################
""", """
                    
                    
                    
                    
                    
                    
                    
                    
    o  o  o  o  o   
                    
                    
###CCCCCCCCCCCCCC###
###~~~~~~~~~~~~~~###
###~~~~~~~~~~~~~~###
###~~~~~~~~~~~~~~###
####################
""", """
                    
                    
                    
                    
        S           
       ===          
                    
                    
    ===     o o     
                    
                  E 
####################
####################
####################
####################
####################
""")

CAVES_1 = hcat("""
####################
####################
#####   ############
####       ####  ###
###             a   
##                  
##                  
##                  
##                  
##                  
##        o o o     
##                  
##       =====      
HH                  
SH  @           b   
####################
####################
####################
""", """
####################
####################
#####         ######
                ####
                    
                    
                    
                    
                    
                    
        o o o       
                    
                    
  !PPP          !   
                    
##~~~~~~~~~~~~~~~~~~
##~~~~~~~~~~~~~~~~~~
####################
""", """
####################
####################
######     #########
####         #######
###              ###
                  ##
                  ##
                  ##
                  ##
      S           ##
     ===    o o     
                    
   L     CCCCC  CCC 
######              
######              
######~~~~~~~~~~~~~~
######~~~~~~~~~~~~~~
####################
""", """
####################
####################
#####          #####
###      a       ###
##                ##
##                 #
#                   
                    
     o o     o o    
                    
    =====           
                    
                    
  o o   b      b    
####################
####################
####################
####################
""", """
####################
####################
#######         ####
####    !          #
###                 
##          o o o   
            ########
            ########
    S       ########
   ===      ########
            ########
            ########
            ########
       III  ########
####################
####################
####################
####################
""", """
####################
####################
######        ######
###              ###
                  ##
    o  o  o       ##
##                ##
##                ##
##             E  ##
##        ##########
##        ##########
##        ##########
##~~~~~~~~##########
##~~~~~~~~##########
####################
####################
####################
####################
""")

CAVES_2 = hcat("""
####################
####################
##########       ###
########          ##
######             #
####                
###                 
##                  
##                  
##                  
##                  
##                  
##            a     
##                  
##       o o o      
##                  
##  @          b    
####################
####################
####################
""", """
####################
####################
####                
####               L
####    M###########
####  o M###########
####M   M###########
####M o M###########
####M   M###########
####M o M###########
####M   M###########
####M o M###########
####M   M###########
####M o M###########
####M   M###########
        M###########
        M###########
####################
####################
####################
""", """
####################
####################
      a  S    a     
   o   o   o   o    
##  CCCC   CCCC   ##
##                ##
##                ##
##                ##
##                ##
##                ##
##                ##
##                ##
##                ##
##                ##
##                ##
##                ##
##^^^^^^^^^^^^^^^^##
####################
####################
####################
""", """
####################
####################
                 ###
                  ##
######             #
######  o o        #
######=====        #
######             #
######        o    #
######    ======   #
######             #
######             #
######=====        #
######  o   o       
######              
####HH              
####SH   b      f   
####################
####################
####################
""", """
####################
####################
########      ######
######  !        ###
####              ##
###               ##
##              E ##
##  S      #########
## ===     #########
##         #########
##         #########
##         #########
##         #########
           #########
           #########
           #########
      III  #########
####################
####################
####################
""")

CAVES_3 = hcat("""
####################
####################
#####       ########
###            #####
##               ###
##                  
##     S            
##    ===     o o   
##                  
##          =====   
##                  
##  @     o o       
####################
####################
####################
####################
""", """
####################
####################
######      ########
####           #####
##               ###
          S         
    o o      a      
                    
                    
    ====    ====    
                    
  L              b  
#####^^^^##^^^^#####
####################
####################
####################
""", """
####################
####################
#####       ########
###            #####
##              ####
         S      ####
        ===     ####
                ####
                ####
   =====        ####
    o o    L        
                    
####################
####################
####################
####################
""", """
<24>
########################
########################
#####              #####
##                    ##
#                      #
#                      #
#                      #
#                      #
#                      #
#                      #
G                      #
G                B   E #
########################
########################
########################
########################
""")

SKY_1 = hcat("""
                    
                    
                    
                    
                    
                    
                    
                    
                    
          o o o     
                    
                    
         ======     
                    
  @                 
#######   ##########
#######   ##########
 #####     ######## 
""", """
                    
                    
                    
                    
                    
                    
                S   
               ===  
         o          
         o    ##    
         o    ##    
              ##    
   o o        ##    
              ##    
         T    ##    
####################
################    
 ############       
""", """
                    
                    
                    
                    
                    
                    
                    
                    
       o o o o      
                    
                    
                    
                    
  !PPP         !    
 L                  
##                ##
##                ##
#                  #
""", """
                    
                    
                    
                    
                    
                    
            o o     
                    
           ====     
                    
               f    
  o o         ###   
       ##     ###   
    b  ##     ###   
       ##     ###   
##################  
##################  
 ################   
""", """
                    
                    
                    
                    
                    
                    
    o  o  o  o      
                    
                    
                    
                    
    ####      ######
    ####      ######
     ##        #### 
         ST     ##  
         ##         
          #         
                    
""", """
                    
                    
                    
                    
                    
                    
                    
                    
    o o o           
                    
              E     
######HH############
######HS############
 ################## 
   ############     
     #######        
                    
                    
""")

SKY_2 = hcat("""
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
         o o o      
        =====       
                    
  @                 
###############   ##
###############   ##
 #############     #
""", """
                    
                    
                    
                    
       !            
                    
            o o o   
           #########
   S       ## ## ## 
  ===      ## ## ## 
           ## ## ## 
            #  #  # 
                    
                    
      III           
####################
####################
 ################## 
""", """
                    
                    
                    
                    
     o o o          
                    
  L             f   
#####   ####   #####
 ## #   # ##   # ## 
 ## #   # ##   # ## 
 ## #   # ##   # ## 
  # #   #  #   #  # 
                    
      T             
      #S            
###########   ######
###########   ######
 #########     #### 
""", """
                    
                    
      !    !      ! 
                    
         o     o    
                    
                    
###                 
 ##       III       
 ##                 
 ##                 
 ##                 
 ##                 
 ##                 
 ##                 
###  III         III
###                 
 #    !    !      ! 
""", """
                    
        S           
       ===          
                    
                    
    ===   o o o     
                    
              b  E  
####################
####################
 ################## 
  ##############    
    ##########      
                    
                    
                    
                    
                    
""")

SKY_3 = hcat("""
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
      S             
     ===            
         o o        
  @                K
####################
####################
 ################## 
""", """
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
      o o o         
                    
                    
                    
###   ######   #####
###   ######   #####
 #     ####     ### 
""", """
                    
                    
                    
                    
                    
         S          
                    
     o o o o o      
   ===========      
                    
                    
                    
                    
                    
  T                 
#####               
#####               
 ###                
""", """
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
      o o o         
                    
                    
            L       
          ##########
          ##########
           ######## 
              ###   
""", """
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
   o   o   o   o    
                    
                    
CCCC   CCCC   CCCC  
                    
                    
                    
""", """
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
     o o o          
                    
               E    
########HH##########
########HS##########
 ################## 
   ############     
""")

STORM_1 = hcat("""
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
          o o o     
                    
         =====      
                    
  @                 
####################
####################
""", """
                    
                    
                    
                    
                    
                    
                    
                    
                    
        S           
     o ===   o o    
                    
                    
    ===    ===      
                 b  
###~~~~~~~~~~~~~####
####################
""", """
                    
                    
                    
                    
                    
                    
                    
                    
            S       
           ===      
      o o           
              f     
     CCCCC   ###    
            ####    
 L         #####    
####################
####################
""", """
                    
                    
                    
                    
                    
                    
                    
     o o o S o      
  ###############   
  ###############   
  ###############   
  ###############   
      a      a      
                    
T   o o o o o o     
####################
####################
""", """
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
      o o o         
                    
                    
  !PPPP         !   
                    
##~~~~~~~~~~~~~~~~##
####################
""", """
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
    o o o           
                    
                    
         b      E   
####################
####################
""")

STORM_2 = hcat("""
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
         o o o      
                    
        =====       
                    
  @                 
####################
####################
""", """
                    
                    
                    
        S           
                    
      o             
       M############
  #    M############
  #M o M############
  #M   M############
  #M o M############
  #M   M############
  #M o M############
  #M   M############
  #M   M############
       M############
       M############
####################
####################
""", """
                    
    ===      ===    
     a        a     
                    
                    
L    o    o    o    
##  CCC  CCC  CCC  #
##                 #
##                 #
##                 #
##                 #
##                 #
##                 #
##                 #
##                 #
##                 #
##                 #
##^^^^^^^^^^^^^^^^^#
####################
""", """
                    
                    
                    
                    
                    
      o o o o       
##                  
##                  
## !PPP         !   
##                  
##                  
##              ####
##              ####
##              ####
##  S T         ####
##  ====        ####
##              ####
##^^^^^^^^^^^^^^####
####################
""", """
                    
                    
                    
                    
                    
                    
                    
        o o o       
                    
                 f  
               #####
####  CCCCCC   #####
####           #####
####           #####
####           #####
####           #####
####           #####
####^^^^^^^^^^^#####
####################
""", """
                    
                    
                    
                    
                    
                    
             S      
            ===     
    o o o           
                 E  
####################
####################
####################
####################
####################
####################
####################
####################
####################
""")

STORM_3 = hcat("""
                    
                    
                    
                    
                    
                    
              S     
             ===    
                    
         o o o      
        =====       
  @                 
################HH##
################HS##
####################
####################
""", """
                    
                    
                    
                    
                    
                    
       o o o        
                    
                    
      ====          
           S        
  L                 
#####~~~~~#~~~######
#####~~~~~~~~~######
#####~~~~~~~~~######
####################
""", """
<24>
#                      #
#                      #
#                      #
#                      #
#                      #
#                      #
#                      #
#                      #
#                      #
#                      #
G                      #
G                B   E #
########################
########################
########################
########################
""")

DEMO_MAP = hcat("""
<64>
                                                                
                                                                
                                                                
                                                                
                o o o                         o o o             
                                                                
       o o                o o o                         o o     
                                    ##                          
###########   ##########  #######  ####   #######   ############
###########~~~##########~~#######~~####~~~#######~~~############
################################################################
""", w=64) * 1

LEVELS = [
    dict(id="1-1", name="Morning Boughs", biome=0, map=CANOPY_1,
         hints=[(1, "Left / Right run,  Space jumps"), (44, "Lanterns keep your place"),
                (66, "Springy mushrooms throw you high"), (95, "Jump again in the air to glide on your leaf")]),
    dict(id="1-2", name="Mossy Trunks", biome=0, map=CANOPY_2,
         hints=[(18, "Plants spit seeds - jump over them or stomp the plant"),
                (22, "Slide down mossy walls - jump to leap off them"), (65, "Down drops through thin branches")]),
    dict(id="1-3", name="Bramble Run", biome=0, map=CANOPY_3, chase=True,
         hints=[(14, "Something is growing behind you...")]),
    dict(id="2-1", name="Glimmer Grotto", biome=1, map=CAVES_1, hints=[(22, "Ride the floating crystal")]),
    dict(id="2-2", name="Echo Shafts", biome=1, map=CAVES_2),
    dict(id="2-3", name="Quartz Hollow", biome=1, map=CAVES_3, boss=dict(hp=3, speed=9.5, kind=0),
         hints=[(64, "Dodge the charge, stomp it while it is dizzy")]),
    dict(id="3-1", name="Windward Steps", biome=2, map=SKY_1, wind=1.0, hints=[(4, "Gusts push you - ride them")]),
    dict(id="3-2", name="Broken Aqueduct", biome=2, map=SKY_2, wind=-1.0),
    dict(id="3-3", name="Stormfront", biome=2, map=SKY_3, wind=1.0, chase=True,
         hints=[(14, "The storm is coming - run!")]),
    dict(id="4-1", name="Rainy Hollow", biome=3, map=STORM_1),
    dict(id="4-2", name="Thunder Ridge", biome=3, map=STORM_2),
    dict(id="4-3", name="The Old Oak", biome=3, map=STORM_3, boss=dict(hp=4, speed=11.0, kind=1),
         hints=[(44, "The storm beetle! Stomp it while it is dizzy")]),
]


class Level:
    """The static part of a level: tiles, where everything is and how the moving things move."""

    def __init__(self, n, meta=None):
        m = meta or LEVELS[n]
        self.n, self.meta = n, m
        self.biome = m.get("biome", 0)
        rows = m["map"]
        W, H = max(len(r) for r in rows), len(rows)
        g = [list(r.ljust(W)) for r in rows]
        self.W, self.H, self.chars = W, H, g
        code = [[0] * W for _ in range(H)]
        self.motes, self.seeds, self.lanterns, self.springs = [], [], [], []
        self.plats, self.beetles, self.bats, self.plants = [], [], [], []
        self.exit = self.start = self.boss_at = None
        self.chase_x = None
        self.gate_x = None
        self.wind = m.get("wind", 0.0)
        self.hints = m.get("hints", [])
        for y in range(H):
            for x in range(W):
                ch = g[y][x]
                c = TILECODE.get(ch, E_)
                if ch in "So" and any(0 <= x + dx < W and 0 <= y + dy < H and g[y + dy][x + dx] == "H"
                                      for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    c = HID
                code[y][x] = c
        self.code = code
        for y in range(H):
            x = 0
            while x < W:
                ch = g[y][x]
                if ch in "PI":
                    x1 = x
                    while x1 < W and g[y][x1] == ch:
                        x1 += 1
                    self.add_plat(ch, x, y, x1 - x)
                    x = x1
                    continue
                cx, cy = x + 0.5, y + 0.5
                if ch == "o":
                    self.motes.append((cx, cy))
                elif ch == "S":
                    self.seeds.append((cx, cy))
                elif ch == "L":
                    self.lanterns.append((cx, float(self.floor_below(x, y))))
                elif ch == "T":
                    self.springs.append((x, y))
                elif ch == "b":
                    self.add_beetle(x, y)
                elif ch == "a":
                    self.add_bat(x, y)
                elif ch in "fF":
                    self.add_plant(x, y, -1 if ch == "f" else 1)
                elif ch == "@":
                    self.start = (cx, float(self.floor_below(x, y)))
                elif ch == "E":
                    self.exit = (cx, float(self.floor_below(x, y)))
                elif ch == "B":
                    self.boss_at = (cx, float(self.floor_below(x, y)))
                elif ch == "K":
                    self.chase_x = float(x)
                elif ch == "G" and self.gate_x is None:
                    self.gate_x = x
                x += 1
        self.lanterns.sort()
        if self.start is None:
            self.start = (1.5, float(self.floor_below(1, 0)))
        self.chase = bool(m.get("chase")) and self.chase_x is not None
        self.boss = m.get("boss") if self.boss_at else None
        if self.boss:
            y = int(self.boss_at[1]) - 1
            self.arena = (self.gate_x + 1.0, float(next(x for x in range(int(self.boss_at[0]), W) if code[y][x] == SOL)))
        self.spring_cols = {}
        for sx, sy in self.springs:
            self.spring_cols.setdefault(sx, []).append(sy)
        # entities live in buckets 8 tiles wide, so a step only looks at what is near
        self.buckets = [[] for _ in range(W // 8 + 2)]
        def put(kind, i, x0, x1):
            for b in range(max(0, int(x0) // 8), min(len(self.buckets) - 1, int(x1) // 8) + 1):
                self.buckets[b].append((kind, i))
        for i, (x, y) in enumerate(self.lanterns):
            put(2, i, x, x)
        for i, b in enumerate(self.beetles):
            put(3, i, b[0] - 1, b[0] + b[1] + 1)
        for i, b in enumerate(self.bats):
            put(4, i, b[0] - 3.5, b[0] + 3.5)
        for i, p in enumerate(self.plants):
            put(5, i, min(p[0], p[0] + p[2] * p[3]) - 1, max(p[0], p[0] + p[2] * p[3]) + 1)
        self.near = []
        for b in range(len(self.buckets)):
            items = []
            for bb in (b - 1, b, b + 1):
                for it in (self.buckets[bb] if 0 <= bb < len(self.buckets) else ()):
                    if it not in items:
                        items.append(it)
            self.near.append(items)
        self.mossmask = [sum(1 << y for y in range(H) if code[y][x] == MOSS) for x in range(W)]
        self.pick = {}
        for kind, lst in ((0, self.motes), (1, self.seeds)):
            for i, (x, y) in enumerate(lst):
                self.pick[(int(x), int(y))] = (kind, i)
        self.hazmask = [sum(1 << x for x in range(W) if code[y][x] in (THU, THD, WAT)) for y in range(H)]
        self.periodic = bool(self.plats or self.beetles or self.bats or self.plants or self.wind)

    # -- building -------------------------------------------------------------------------
    def stop(self, x, y):
        return not (0 <= x < self.W and 0 <= y < self.H) or self.chars[y][x] in STOPS

    def floor_below(self, x, y):
        while y < self.H and self.code[y][x] not in (SOL, MOSS, CRUM, ONE):
            y += 1
        return y

    def add_plat(self, ch, x, y, w):
        if ch == "P":
            a = x
            while not self.stop(a - 1, y):
                a -= 1
            b = x + w - 1
            while not self.stop(b + 1, y):
                b += 1
            mn, mx, at, other, axis = a, b - w + 1, x, y, 0
        else:
            a = y
            while not any(self.stop(xx, a - 1) for xx in range(x, x + w)):
                a -= 1
            b = y
            while not any(self.stop(xx, b + 1) for xx in range(x, x + w)):
                b += 1
            mn, mx, at, other, axis = a, b, y, x, 1
        span = mx - mn
        period = PERIOD if span >= 5 else PERIOD // 2
        phase = (at - mn) / span * period / 2 if span else 0
        self.plats.append((axis, float(mn), float(span), w, period, phase, float(other)))

    def add_beetle(self, x, y):
        fy = self.floor_below(x, y)
        def ok(c):
            return (0 <= c < self.W and self.code[fy][c] in (SOL, MOSS, CRUM, ONE) and
                    self.code[fy - 1][c] in (E_, HID) and self.code[fy - 2][c] in (E_, HID))
        a = b = x
        while ok(a - 1):
            a -= 1
        while ok(b + 1):
            b += 1
        left, span = a + 0.5, float(b - a)
        period = PERIOD if span >= 5 else PERIOD // 2
        phase = (x - a) / span * period / 2 if span else 0
        self.beetles.append((left, span, float(fy), period, phase))

    def add_bat(self, x, y):
        fy = self.floor_below(x, y)
        depth = clamp(fy - y - 1.4, 1.5, 6.0)
        self.bats.append((x + 0.5, y + 0.5, depth, (len(self.bats) * 75) % PERIOD))

    def add_plant(self, x, y, d):
        fy = self.floor_below(x, y)
        my = fy - 0.62
        rng = 0.0
        while rng < 16 and self.code[int(my)][int(x + 0.5 + d * (rng + 0.6))] not in (SOL, MOSS, CRUM):
            rng += 0.5
            if not 0 <= x + 0.5 + d * (rng + 0.6) < self.W:
                break
        self.plants.append((x + 0.5, float(fy), d, rng, (len(self.plants) * 53) % 150))

    # -- the moving things, as pure functions of the frame number -------------------------
    def plat_pos(self, i, f):
        axis, mn, span, w, period, phase, other = self.plats[i]
        v = mn + span * tri((f + phase) / period) if span else mn
        return (v, other) if axis == 0 else (other, v)

    def beetle_pos(self, i, f):
        left, span, fy, period, phase = self.beetles[i]
        u = ((f + phase) / period) % 1.0 if span else 0.0
        return left + span * tri(u), fy, (1 if u < 0.5 else -1)

    def bat_pos(self, i, f):
        px, py, depth, off = self.bats[i]
        u = (f + off) % PERIOD
        if u < 180:
            return px, py + 0.12 * math.sin(f * 0.05 + i), 0.0
        s = (u - 180) / 120
        return px + 2.8 * math.sin(2 * math.pi * s), py + depth * math.sin(math.pi * s), s

    def shots(self, i, f):
        """Seed pellets of plant i in flight at frame f: [(x, y), ...]."""
        x, fy, d, rng, off = self.plants[i]
        life = int(rng / 3.6 * 60)
        out = []
        if life <= 0:
            return out
        t = f - off
        k = t // 150
        while k >= 0 and t - k * 150 < life:
            age = t - k * 150
            if age >= 0:
                out.append((x + d * (0.6 + age * 3.6 / 60), fy - 0.62))
            k -= 1
        return out

    def plant_mouth(self, i, f):
        """0..1: how far plant i has opened its mouth (it spits when it snaps shut)."""
        x, fy, d, rng, off = self.plants[i]
        u = (f - off) % 150
        return max(0.0, 1 - (150 - u) / 30) if u > 120 else (1.0 - u / 8 if u < 8 else 0.0)


class Sim:
    """Everything that changes while you play a level. step() is deterministic: same inputs, same run."""

    def __init__(self, lv, toggle_glide=False):
        self.lv = lv
        self.toggle = toggle_glide
        self.f = 0
        self.motes = frozenset()
        self.mote_count = 0
        self.seeds = 0
        self.lit = 0
        self.cp = -1
        self.dead_en = frozenset()
        self.crumble = {}
        self.boss = None
        self.boss_done = False
        self.chase_f0 = -1
        self.chase_x0 = 0.0
        self.won = False
        self.lives = 5
        self.deaths = 0
        self.ev = []
        self.place(*lv.start)

    def place(self, x, y):
        self.x, self.y = x, y
        self.vx = self.vy = 0.0
        self.ground, self.plat = True, -1
        self.coy, self.buf = COYOTE_F, 0
        self.glide = self.jumping = self.sliding = False
        self.lock = self.drop = 0
        self.wall = self.wall_coy = 0
        self.facing = 1
        self.dead = False
        self.stand = SOL

    def copy(self):
        s = object.__new__(Sim)
        s.__dict__ = self.__dict__.copy()
        if self.boss:
            s.boss = list(self.boss)
        s.ev = []
        s._own = self._own = False             # both copy the crumble table before changing it
        return s

    def respawn(self):
        """Back to the last lantern (or the start)."""
        lv = self.lv
        if self.cp >= 0:
            x, y = lv.lanterns[self.cp]
        else:
            x, y = lv.start
        self.place(x, y)
        self.crumble = {}
        if not self.boss_done:
            self.boss = None
        if lv.chase:
            if x > lv.chase_x:
                self.chase_f0, self.chase_x0 = self.f + 75, x - 9.0
            else:
                self.chase_f0 = -1

    # -- world queries --------------------------------------------------------------------
    def solid(self, tx, ty):
        lv = self.lv
        if tx < 0 or tx >= lv.W:
            return True
        if ty < 0 or ty >= lv.H:
            return False
        c = lv.code[ty][tx]
        if c == SOL or c == MOSS:
            return True
        if c == CRUM:
            s = self.crumble.get((tx, ty))
            return s is None or self.f - s < CRUMBLE_GONE
        if c == GATE:
            return self.boss is not None and not self.boss_done
        return False

    def chase_pos(self, f=None):
        if self.chase_f0 < 0:
            return None
        f = self.f if f is None else f
        return self.chase_x0 + CHASE_V * max(0, f - self.chase_f0) / 60

    def gate_open(self):
        return self.lv.boss is None or self.boss_done

    # -- one step of 1/60 s ---------------------------------------------------------------
    def step(self, inp):
        """inp = (direction -1/0/1, jump pressed now, jump held, down pressed). Returns the events."""
        d, jedge, jheld, down = inp
        lv = self.lv
        ev = self.ev = []
        if self.dead or self.won:
            self.f += 1
            return ev
        f = self.f
        y_old = self.y
        if self.plat >= 0:                          # ride the moving platform
            ox, oy = lv.plat_pos(self.plat, f)
            nx, ny = lv.plat_pos(self.plat, f + 1)
            self.move_x(nx - ox)
            self.y += ny - oy
        if d:
            self.facing = d
        # -- running
        if self.lock > 0:
            self.lock -= 1
            ctrl = 0.2
        else:
            ctrl = 1.0
        vx = self.vx
        target = d * (GLIDE_MAX if self.glide and not self.ground else RUN_MAX)
        if self.ground:
            a = DEC_G if d == 0 else (TURN_G if d * vx < 0 else ACC_G)
        else:
            a = DEC_A if d == 0 else (TURN_A if d * vx < 0 else ACC_A)
        a *= ctrl * DT
        if vx < target:
            vx = min(target, vx + a)
        elif vx > target:
            vx = max(target, vx - a)
        if lv.wind:
            g = gust(f)
            if g:
                vx += lv.wind * 16.0 * g * DT * (0.3 if self.ground else (1.5 if self.glide else 1.0))
        # -- jumping, wall jumps and the glide
        vy = self.vy
        if jedge:
            self.buf = BUFFER_F
        jumped = False
        if self.buf > 0:
            if self.ground or self.coy > 0:
                vy = -JUMP_V
                self.ground, self.plat, self.coy, self.buf = False, -1, 0, 0
                self.jumping, self.glide, jumped = True, False, True
                ev.append(("jump",))
            elif self.wall_coy > 0:
                vx = -self.wall * WJ_VX
                vy = -WJ_VY
                self.lock, self.buf, self.wall_coy = WJ_LOCK, 0, 0
                self.jumping, self.glide, jumped = True, False, True
                self.facing = -self.wall
                ev.append(("walljump", self.wall))
            else:
                self.buf -= 1
        if jedge and not jumped and not self.ground:
            if self.toggle:
                self.glide = not self.glide
            else:
                self.glide = True
            if self.glide:
                ev.append(("glide",))
        if not self.toggle and not jheld:
            self.glide = False
        if self.jumping:
            if vy < 0 and not jheld:
                vy *= JUMP_CUT
                self.jumping = False
            elif vy >= 0:
                self.jumping = False
        grav = GRAV if vy < 0 else GRAV_FALL
        if abs(vy) < APEX_V and (jheld or self.toggle):
            grav *= APEX_MUL
        vy += grav * DT
        self.sliding = False
        if self.wall and not self.ground and vy > 0 and d == self.wall:
            if vy > WALL_SLIDE:
                vy = max(WALL_SLIDE, vy - 90 * DT)
            self.sliding = True
            self.glide = False
        elif self.glide and vy > GLIDE_FALL:
            vy = max(GLIDE_FALL, vy - GLIDE_BRAKE * DT)
        if vy > MAX_FALL:
            vy = MAX_FALL
        self.vx, self.vy = vx, vy
        # -- move
        if down and self.ground and self.stand == ONE:
            self.drop = 12
            ev.append(("drop",))
        if self.drop > 0:
            self.drop -= 1
        was_ground = self.ground
        self.move_x(vx * DT)
        self.move_y(vy * DT)
        if self.ground:
            if not was_ground:
                ev.append(("land", vy))
                self.glide = False
            self.coy = COYOTE_F
        elif self.coy > 0:
            self.coy -= 1
        # -- touching a mossy wall?
        self.wall = 0
        if not self.ground:
            r0, r1 = int(self.y - PH + 0.15), int(self.y - 0.15)
            span = (2 << (r1 - r0)) - 1
            for side in (1, -1):
                tx = int(math.floor(self.x + side * (HW + 0.08)))
                if 0 <= tx < lv.W and r0 >= 0 and (lv.mossmask[tx] >> r0) & span:
                    self.wall = side
                    break
        if self.wall:
            self.wall_coy = 5
        elif self.wall_coy > 0:
            self.wall_coy -= 1
        # -- crumbling blocks under the feet
        if self.ground and self.stand == CRUM:
            ty = int(round(self.y))
            for tx in range(int(math.floor(self.x - HW + 1e-6)), int(math.floor(self.x + HW - 1e-6)) + 1):
                if 0 <= tx < lv.W and lv.code[ty][tx] == CRUM and (tx, ty) not in self.crumble:
                    if not self.__dict__.get("_own", True):
                        self.crumble = dict(self.crumble)
                        self._own = True
                    self.crumble[(tx, ty)] = f
                    ev.append(("crumble", tx, ty))
        if self.crumble and f % 15 == 0:
            gone = [k for k, s in self.crumble.items() if f - s >= CRUMBLE_BACK and not self.overlaps(*k)]
            if gone:
                self.crumble = {k: s for k, s in self.crumble.items() if k not in gone}
                self._own = True
        self.f = f + 1
        self.touch(y_old)
        return ev

    def overlaps(self, tx, ty):
        return self.x + HW > tx and self.x - HW < tx + 1 and self.y > ty and self.y - PH < ty + 1

    def move_x(self, dx):
        if not dx:
            return
        nx = self.x + dx
        r0, r1 = int(math.floor(self.y - PH + 1e-6)), int(math.floor(self.y - 1e-6))
        if dx > 0:
            tx = int(math.floor(nx + HW))
            if any(self.solid(tx, r) for r in range(r0, r1 + 1)):
                nx = tx - HW - 1e-6
                self.vx = 0.0
        else:
            tx = int(math.floor(nx - HW))
            if any(self.solid(tx, r) for r in range(r0, r1 + 1)):
                nx = tx + 1 + HW + 1e-6
                self.vx = 0.0
        self.x = nx

    def move_y(self, dy):
        lv = self.lv
        y = self.y
        ny = y + dy
        x0, x1 = self.x - HW + 1e-6, self.x + HW - 1e-6
        c0, c1 = int(math.floor(x0)), int(math.floor(x1))
        self.ground = False
        self.plat = -1
        if dy > 0:
            land, kind, plat = None, SOL, -1
            for c in range(c0 - 1, c1 + 1):            # springy mushrooms
                for sy in lv.spring_cols.get(c, ()):
                    top = sy + 0.45
                    if y <= top + 1e-6 and ny >= top and x1 > c + 0.1 and x0 < c + 0.9:
                        self.y = top
                        self.vy = -SPRING_V
                        self.jumping = self.glide = False
                        self.ev.append(("spring", c, sy))
                        return
            if self.drop == 0:
                f = self.f
                for i in range(len(lv.plats)):
                    px, py = lv.plat_pos(i, f + 1)
                    w = lv.plats[i][3]
                    if x1 > px and x0 < px + w and ny >= py and y <= max(py, lv.plat_pos(i, f)[1]) + 1e-6:
                        if land is None or py < land:
                            land, kind, plat = py, ONE, i
            r = int(math.floor(ny - 1e-9))
            if 0 <= r < lv.H:
                for c in range(c0, c1 + 1):
                    if self.solid(c, r):
                        if land is None or r <= land:
                            land, kind, plat = float(r), (lv.code[r][c] if 0 <= c < lv.W else SOL), -1
                    elif 0 <= c < lv.W and lv.code[r][c] == ONE and self.drop == 0 and y <= r + 1e-6:
                        if land is None or r < land:
                            land, kind, plat = float(r), ONE, -1
            if land is not None:
                self.y = land
                self.vy = 0.0
                self.ground = True
                self.stand = kind
                self.plat = plat
                return
            self.y = ny
        else:
            r = int(math.floor(ny - PH))
            if any(self.solid(c, r) for c in range(c0, c1 + 1)):
                # nudge round a corner we only just clipped
                for nudge in (0.3, -0.3):
                    a, b = int(math.floor(x0 + nudge)), int(math.floor(x1 + nudge))
                    if not any(self.solid(c, r) for c in range(a, b + 1)) and \
                            not any(self.solid(c, rr) for c in range(a, b + 1)
                                    for rr in range(r + 1, int(math.floor(y - 1e-6)) + 1)):
                        self.x += nudge
                        self.y = ny
                        return
                self.y = r + 1 + PH
                self.vy = 0.0
                self.jumping = False
            else:
                self.y = ny

    # -- what we touch: hazards, enemies, pickups -----------------------------------------
    def hurt(self, why):
        if not self.dead:
            self.dead = True
            self.ev.append(("hurt", why))

    def touch(self, y_old):
        lv = self.lv
        f = self.f
        x, y = self.x, self.y
        X0, X1, Y0, Y1 = x - HW, x + HW, y - PH, y
        if Y0 > lv.H + 1:
            self.hurt("fall")
            return
        tx0, tx1 = max(0, int(math.floor(X0))), min(lv.W - 1, int(math.floor(X1 - 1e-6)))
        span = (2 << (tx1 - tx0)) - 1 if tx1 >= tx0 else 0
        hm = lv.hazmask
        for ty in range(max(0, int(math.floor(Y0))), min(lv.H - 1, int(math.floor(Y1 - 1e-6))) + 1):
            if not (hm[ty] >> tx0) & span:
                continue
            row = lv.code[ty]
            for tx in range(tx0, tx1 + 1):
                c = row[tx]
                if c == THU:
                    if X1 > tx + 0.15 and X0 < tx + 0.85 and Y1 > ty + 0.45:
                        self.hurt("thorns")
                        return
                elif c == THD:
                    if X1 > tx + 0.15 and X0 < tx + 0.85 and Y0 < ty + 0.55:
                        self.hurt("thorns")
                        return
                elif c == WAT:
                    top = ty + (0.35 if ty == 0 or lv.code[ty - 1][tx] != WAT else 0.0)
                    if Y1 > top + 0.1:
                        self.hurt("water")
                        return
        cx, cy = x, y - PH / 2
        pick = lv.pick
        for ty in range(int(cy - 0.95), int(cy + 0.95) + 1):
            for tx in range(int(cx - 0.75), int(cx + 0.75) + 1):
                it = pick.get((tx, ty))
                if it is None:
                    continue
                kind, i = it
                if kind == 0:
                    if i not in self.motes:
                        mx, my = lv.motes[i]
                        if abs(mx - cx) < 0.75 and abs(my - cy) < 0.95:
                            self.motes = self.motes | {i}
                            self.mote_count += 1
                            self.ev.append(("mote", i))
                            if self.mote_count % 50 == 0:
                                self.lives += 1
                                self.ev.append(("life",))
                elif not self.seeds >> i & 1:
                    sx, sy = lv.seeds[i]
                    if abs(sx - cx) < 0.75 and abs(sy - cy) < 0.95:
                        self.seeds |= 1 << i
                        self.ev.append(("seed", i))
        b = int(x) // 8
        if 0 <= b < len(lv.near):
            for item in lv.near[b]:
                kind, i = item
                if kind == 2:
                    if not self.lit >> i & 1:
                        lx, ly = lv.lanterns[i]
                        if abs(lx - x) < 0.9 and ly - 3.0 < y <= ly + 0.6:
                            self.lit |= 1 << i
                            self.cp = max(self.cp, i)
                            self.ev.append(("cp", i))
                elif item in self.dead_en:
                    continue
                elif kind == 3:
                    ex, ey, _ = lv.beetle_pos(i, f)
                    self.enemy(kind, i, ex - 0.45, ex + 0.45, ey - 0.7, ey, y_old, X0, X1, Y0, Y1)
                elif kind == 4:
                    ex, ey, _ = lv.bat_pos(i, f)
                    self.enemy(kind, i, ex - 0.4, ex + 0.4, ey - 0.3, ey + 0.3, y_old, X0, X1, Y0, Y1)
                elif kind == 5:
                    px, py, _, _, _ = lv.plants[i]
                    self.enemy(kind, i, px - 0.38, px + 0.38, py - 0.9, py, y_old, X0, X1, Y0, Y1)
                    for sx, sy in lv.shots(i, f):
                        if X1 > sx - 0.18 and X0 < sx + 0.18 and Y1 > sy - 0.18 and Y0 < sy + 0.18:
                            self.hurt("shot")
                if self.dead:
                    return
        if lv.chase:
            if self.chase_f0 < 0 and x > lv.chase_x:
                self.chase_f0, self.chase_x0 = f, lv.chase_x - 12.0
                self.ev.append(("chase",))
            cxp = self.chase_pos()
            if cxp is not None and X0 < cxp:
                self.hurt("chase")
                return
        if lv.boss:
            self.boss_step(y_old, X0, X1, Y0, Y1)
            if self.dead:
                return
        if lv.exit and self.gate_open() and abs(x - lv.exit[0]) < 0.75 and abs(y - lv.exit[1]) < 1.2:
            self.won = True
            self.ev.append(("exit",))

    def enemy(self, kind, i, ex0, ex1, ey0, ey1, y_old, X0, X1, Y0, Y1):
        if X1 > ex0 and X0 < ex1 and Y1 > ey0 and Y0 < ey1:
            if self.vy > 0 and y_old <= ey0 + 0.35:
                self.dead_en = self.dead_en | {(kind, i)}
                self.vy = -STOMP_V
                self.jumping = True
                self.glide = False
                self.ev.append(("stomp", kind, i, (ex0 + ex1) / 2, ey1))
            else:
                self.hurt("enemy")

    # -- the boss: waits, winds up, charges into the wall, is dizzy (stomp it then) ------------
    def boss_step(self, y_old, X0, X1, Y0, Y1):
        lv = self.lv
        cfg = lv.boss
        a0, a1 = lv.arena
        if self.boss is None:
            if self.boss_done or self.x < a0 + 2.0:
                return
            self.boss = [WAIT, 70, lv.boss_at[0], 0.0, cfg["hp"], -1]
            self.ev.append(("boss",))
        b = self.boss
        st, tm, bx, bvx, hp, face = b
        speed = cfg["speed"] + (cfg["hp"] - hp) * 1.6
        tm -= 1
        if st == WAIT:
            face = 1 if self.x > bx else -1
            if tm <= 0:
                st, tm = WINDUP, 32
        elif st == WINDUP:
            if tm <= 0:
                st, bvx = CHARGE, face * speed
                self.ev.append(("charge",))
        elif st == CHARGE:
            bx += bvx * DT
            lo, hi = a0 + BOSS_W / 2, a1 - BOSS_W / 2
            if bx <= lo or bx >= hi:
                bx = clamp(bx, lo, hi)
                st, tm, bvx = STUN, 130, 0.0
                self.ev.append(("bump", bx))
        elif st == STUN:
            if tm <= 0:
                st, tm = WAIT, 50
        elif st == HURT:
            if tm <= 0:
                st, tm = WAIT, 45
        elif st == DEAD:
            pass
        b[:] = [st, tm, bx, bvx, hp, face]
        if st == DEAD:
            return
        by = lv.boss_at[1]
        ex0, ex1, ey0, ey1 = bx - BOSS_W / 2, bx + BOSS_W / 2, by - BOSS_H, by
        if X1 > ex0 and X0 < ex1 and Y1 > ey0 and Y0 < ey1:
            if st == STUN and self.vy > 0 and y_old <= ey0 + 0.45:
                hp -= 1
                self.vy = -STOMP_V * 1.2
                self.vx = 7.5 if bx < (a0 + a1) / 2 else -7.5      # thrown off towards the middle
                self.lock = 16
                self.jumping = True
                self.glide = False
                if hp <= 0:
                    b[:] = [DEAD, 0, bx, 0.0, 0, face]
                    self.boss_done = True
                    self.ev.append(("bossdead", bx, by))
                else:
                    b[:] = [HURT, 50, bx, 0.0, hp, face]
                    self.ev.append(("bosshit", bx, by))
            elif st in (WAIT, WINDUP, CHARGE):
                self.hurt("boss")


# =============================================================================================
# The route planner: a weighted A* search over the real step() function. It proves that every level
# can be finished, every lantern lies on the way and every seed can be reached (and left again).
# =============================================================================================
MACRO = 8                                       # one search move holds the keys for 8 steps
ACTS = [(d, j) for j in (0, 1, 2) for d in (1, -1, 0)] + [(0, 3)]


def _macro(d, j):
    if j == 0:
        return [(d, False, False, False)] * MACRO
    if j == 1:
        return [(d, True, True, False)] + [(d, False, True, False)] * (MACRO - 1)
    if j == 2:
        return [(d, False, True, False)] * MACRO
    return [(0, False, False, True)] + [(0, False, False, False)] * (MACRO - 1)


MACROS = {a: _macro(*a) for a in ACTS}


def distance_map(lv, gx, gy):
    """Rough distance (in tiles) from every open cell to the goal: guides the search round walls. Going up is
    only allowed where something can lift you there: ground a jump below, a spring, a mossy wall or a lift."""
    W, H = lv.W, lv.H
    INF = 1e9
    code = lv.code
    bad = (SOL, MOSS, CRUM, THU, THD, WAT)
    stand = (SOL, MOSS, CRUM, ONE)
    lift = [[False] * W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            if code[y][x] in stand and y > 0 and code[y - 1][x] not in bad:
                for k in range(1, 5):
                    if y - k >= 0:
                        lift[y - k][x] = True
            if code[y][x] == MOSS:
                for xx in (x - 1, x + 1):
                    if 0 <= xx < W:
                        for k in range(0, 4):
                            if 0 <= y - k < H:
                                lift[y - k][xx] = True
    for sx, sy in lv.springs:
        for k in range(0, 9):
            for xx in range(sx - 2, sx + 3):
                if 0 <= sy - k < H and 0 <= xx < W:
                    lift[sy - k][xx] = True
    for i, (axis, mn, span, w, period, phase, other) in enumerate(lv.plats):
        if axis == 0:
            xs, ys = range(int(mn), int(mn + span) + w), range(int(other) - 4, int(other) + 1)
        else:
            xs, ys = range(int(other), int(other) + w), range(int(mn) - 4, int(mn + span) + 1)
        for y in ys:
            for x in xs:
                if 0 <= x < W and 0 <= y < H:
                    lift[y][x] = True
    dist = [[INF] * W for _ in range(H)]
    gx, gy = clamp(gx, 0, W - 1), clamp(gy, 0, H - 1)
    dist[gy][gx] = 0.0
    q = [(0.0, gx, gy)]
    while q:
        dd, x, y = heapq.heappop(q)
        if dd > dist[y][x]:
            continue
        for nx, ny, cost in ((x - 1, y, 1.0), (x + 1, y, 1.0), (x, y + 1, 1.6), (x, y - 1, 0.6)):
            # (nx, ny) -> (x, y): going up from below costs more than dropping down, and needs a lift
            if 0 <= nx < W and 0 <= ny < H and code[ny][nx] not in bad:
                if ny == y + 1 and not lift[y][x]:
                    continue
                nd = dd + cost
                if nd < dist[ny][nx]:
                    dist[ny][nx] = nd
                    heapq.heappush(q, (nd, nx, ny))
    return dist


PLAN_W, PLAN_Q = 2.5, 3


def plan(sim, goal, cell, budget=20.0, weight=None, max_nodes=150000):
    """Search inputs that take sim to a state where goal(state) holds. Returns (inputs, end state, nodes).
    The search stops after max_nodes nodes (so it gives the same answer on every machine) or budget seconds."""
    lv = sim.lv
    weight = weight or PLAN_W
    q = PLAN_Q
    dist = distance_map(lv, *cell)
    W, H = lv.W, lv.H
    per = 60.0 / RUN_MAX
    t_end = time.time() + budget
    periodic = lv.periodic

    def hval(s):
        x, y = int(s.x), int(s.y - 0.6)
        if 0 <= x < W and 0 <= y < H:
            d = dist[y][x]
            if d < 1e8:
                return d * per
        return 200 * per

    def key(s):
        return (int(s.x * q), int(s.y * q), int(round(s.vx / 2.5)), max(-5, min(5, int(s.vy // 4))), s.ground,
                s.glide, s.wall_coy > 0, (s.f % PERIOD) // 30 if periodic else 0)

    if goal(sim):
        return [], sim, 0
    nodes = [(sim, -1, None, 0)]
    seen = {key(sim): 0}
    heap = [(hval(sim) * weight, 0, 0)]
    while heap and len(nodes) < max_nodes and (len(nodes) & 255 or time.time() < t_end):
        _, g, ni = heapq.heappop(heap)
        s = nodes[ni][0]
        for a in ACTS:
            if a[1] == 3 and not (s.ground and s.stand == ONE):
                continue
            if a[1] == 2 and s.ground:
                continue
            c = s.copy()
            done = 0
            for k, inp in enumerate(MACROS[a]):
                c.step(inp)
                if c.dead:
                    break
                if goal(c):
                    done = k + 1
                    break
            if c.dead:
                continue
            if done:
                out = MACROS[a][:done]
                while ni > 0:
                    _, parent, act, n = nodes[ni]
                    out = MACROS[act][:n] + out
                    ni = parent
                return out, c, len(nodes)
            k2 = key(c)
            g2 = g + MACRO
            if seen.get(k2, 1e9) <= g2:
                continue
            seen[k2] = g2
            hc = hval(c)
            nodes.append((c, ni, a, MACRO))
            heapq.heappush(heap, (g2 + weight * hc, g2, len(nodes) - 1))
    return None, None, len(nodes)


def boss_bot(s):
    """A reactive player for the boss arena: keep away, jump the charge, stomp it while it is dizzy."""
    lv = s.lv
    st, tm, bx, bvx, hp, face = s.boss
    a0, a1 = lv.arena
    dx = bx - s.x
    if st == STUN:
        d = 1 if dx > 0 else -1
        if s.ground:
            return (d, abs(dx) < 2.3, True, False)
        return (d if abs(dx) > 0.2 else 0, False, True, False)
    if st == CHARGE:
        gap = abs(dx) - BOSS_W / 2 - HW
        if bvx * dx < 0 and s.ground and gap < abs(bvx) * 0.16 + 0.3:
            return (0, True, True, False)
        return (0, False, True, False)
    if st in (HURT, DEAD):
        away = 1 if bx < (a0 + a1) / 2 else -1
        return (away if abs(dx) < 4.5 else 0, False, False, False)
    target = a1 - 3.0 if bx < (a0 + a1) / 2 else a0 + 3.0     # wait by the far wall: it crashes next to us
    if abs(target - s.x) < 0.4:
        return (0, False, False, False)
    return (1 if target > s.x else -1, False, False, False)


MAIN_NODES, SEED_NODES = 200000, 120000


def solve_level(n, budget=600.0, seeds=True):
    """Plan a route through level n: start -> every lantern -> (boss) -> exit, then every seed.
    Returns a report dict; 'ok' is False with a reason when something cannot be done in the budget."""
    t0 = time.time()
    lv = Level(n)
    rep = dict(n=n, id=lv.meta["id"], ok=False, why="", route=None, nodes=0, seeds=0, time=0.0)
    sim = Sim(lv)
    route = []
    starts = [(lv.start[0], sim.copy(), 0)]
    per = budget * (0.5 if seeds else 1.0) / (len(lv.lanterns) + 2)
    per_seed = budget * 0.5 / max(1, len(lv.seeds) * 2)
    goals = []
    for i, (lx, ly) in enumerate(lv.lanterns):
        goals.append(("lantern %d" % (i + 1), lambda s, i=i: s.lit >> i & 1 and safe(s), (int(lx), int(ly) - 1)))
    if lv.boss:
        goals.insert(sum(1 for lx, _ in lv.lanterns if lx < lv.arena[0]),
                     ("arena", lambda s: s.boss is not None, (int(lv.arena[0] + 3), int(lv.boss_at[1]) - 1)))
    goals.append(("exit", lambda s: s.won, (int(lv.exit[0]), int(lv.exit[1]) - 1)))
    for name, goal, cell in goals:
        ins, end, nodes = plan(sim, goal, cell, per, max_nodes=MAIN_NODES)
        rep["nodes"] += nodes
        if ins is None:
            rep["why"] = "no route to the %s (%d nodes)" % (name, nodes)
            return rep
        route += ins
        sim = end
        if name == "arena":
            fight = 0
            while not sim.boss_done and fight < 60 * 90:
                inp = boss_bot(sim)
                sim.step(inp)
                route.append(inp)
                fight += 1
                if sim.dead:
                    rep["why"] = "the boss bot was hurt (boss hp %d)" % sim.boss[4]
                    return rep
            if not sim.boss_done:
                rep["why"] = "the boss fight took too long"
                return rep
        starts.append((sim.x, sim.copy(), len(route)))
    # replay from scratch: the same inputs must give the same run (twice), lighting every lantern
    finals = []
    snaps = []
    for rep_i in range(2):
        r = Sim(lv)
        log = []
        for k, inp in enumerate(route):
            log.extend(r.step(inp))
            if rep_i == 0 and k % 20 == 0 and safe(r):
                snaps.append((r.x, r.copy()))
        finals.append((r.x, r.y, r.f, r.won, r.lit, r.mote_count, r.seeds, len(log), repr(log[-5:])))
    if finals[0] != finals[1]:
        rep["why"] = "replay is not deterministic"
        return rep
    if not finals[0][3]:
        rep["why"] = "replayed route does not reach the exit"
        return rep
    if finals[0][4] != (1 << len(lv.lanterns)) - 1:
        rep["why"] = "the route misses a lantern"
        return rep
    rep["route"] = route
    rep["motes_on_route"] = finals[0][5]
    if seeds:
        for i, (sx, sy) in enumerate(lv.seeds):
            behind = sorted((st for st in snaps if st[0] < sx - 0.5), key=lambda st: sx - st[0])
            order = behind[:1] + behind[6:7] + behind[15:16] + sorted(starts, key=lambda st: abs(st[0] - sx))[:1]
            got = None
            for st in order:
                ins, end, nodes = plan(st[1], lambda s, i=i: s.seeds >> i & 1 and safe(s), (int(sx), int(sy)), per_seed, max_nodes=SEED_NODES)
                rep["nodes"] += nodes
                if ins is not None:
                    got = (st, end)
                    break
            if got is None:
                rep["why"] = "seed %d at (%d, %d) cannot be reached" % (i + 1, sx, sy)
                return rep
            st, end = got
            # ... and you can carry on from there to the next lantern or the exit
            ahead = sorted((g for g in goals if g[2][0] >= sx - 1 and not g[1](end)),
                           key=lambda g: g[2][0])
            name, goal, cell = ahead[0] if ahead else goals[-1]
            ins, end2, nodes = plan(end, goal, cell, per_seed, max_nodes=SEED_NODES, weight=3.5)
            rep["nodes"] += nodes
            if ins is None:
                rep["why"] = "stuck after seed %d (no way on to the %s)" % (i + 1, name)
                return rep
            rep["seeds"] += 1
    rep["ok"] = True
    rep["frames"] = len(route)
    rep["time"] = time.time() - t0
    return rep


def safe(s):
    """Standing on something that will not crumble away."""
    return s.ground and s.stand != CRUM




# =============================================================================================
# Keys: the kitty keyboard protocol gives presses AND releases; elsewhere we only see presses and key repeat
# =============================================================================================
KITTY_RE = re.compile(r"\x1b\[([0-9:;]*)([uABCDHF~])")
KITTY_NAMES = {13: "enter", 27: "esc", 32: " ", 9: "tab", 127: "backspace", 57399: "0"}
ARROWS = {"A": "up", "B": "down", "C": "right", "D": "left"}
SHIFTED = {"/": "?", "1": "!"}


class Terminal(arcadekit.Terminal):
    """arcadekit's terminal plus the kitty keyboard protocol where the terminal speaks it (kitty, WezTerm,
    Ghostty, foot, recent iTerm2): then events() also reports repeats and releases."""

    def __enter__(self):
        super().__enter__()
        self.kitty = self.detect_kitty()
        if self.kitty:
            self.write("\x1b[>15u")   # disambiguate + event types + alternate keys + all keys as escape codes
        return self

    def __exit__(self, *exc):
        if getattr(self, "kitty", False):
            self.write("\x1b[<u")
        return super().__exit__(*exc)

    def detect_kitty(self):
        """Ask for the keyboard protocol flags; the device-attributes query makes every terminal answer.
        Keys typed meanwhile are kept for events()."""
        self.pending = ""
        if os.environ.get("LEAFLING_LEGACY_KEYS"):
            return False
        self.write("\x1b[?u\x1b[c")
        data, end = "", time.time() + 0.5
        while time.time() < end and not re.search(r"\x1b\[\?[0-9;]*c", data):
            if select.select([self.fd], [], [], 0.05)[0]:
                data += os.read(self.fd, 1024).decode("utf-8", "ignore")
        kitty = re.search(r"\x1b\[\?\d*u", data) is not None
        self.pending = re.sub(r"\x1b\[\?[0-9;]*[uc]", "", data)
        return kitty

    def events(self, timeout=0.0):
        """[(name, kind)] since the last call, kind = 'press', 'repeat' or 'release'."""
        data, self.pending = getattr(self, "pending", ""), ""
        wait = 0 if data else timeout
        while select.select([self.fd], [], [], wait)[0]:
            wait = 0
            chunk = os.read(self.fd, 4096).decode("utf-8", "ignore")
            if not chunk:
                break
            data += chunk
        return self.parse(data) if data else []

    def parse(self, data):
        out = []
        i = 0
        while i < len(data):
            m = KITTY_RE.match(data, i) if self.kitty else None
            if m:
                i = m.end()
                fields = m.group(1).split(";")
                codes = fields[0].split(":")
                mods, event = 1, "1"
                if len(fields) > 1 and fields[1]:
                    mm = fields[1].split(":")
                    mods = int(mm[0]) if mm[0].isdigit() else 1
                    event = mm[1] if len(mm) > 1 else "1"
                final = m.group(2)
                name = None
                if final in ARROWS:
                    name = ARROWS[final]
                elif final == "u" and codes[0].isdigit():
                    c = int(codes[0])
                    if (mods - 1) & 4 and c in (99, 100):       # ctrl+c / ctrl+d
                        raise KeyboardInterrupt
                    if (mods - 1) & 1 and len(codes) > 1 and codes[1].isdigit():
                        c = int(codes[1])                        # the shifted key, e.g. ?
                    name = KITTY_NAMES.get(c) or (chr(c).lower() if 32 < c < 0x110000 else None)
                    if name and (mods - 1) & 1 and name in SHIFTED:
                        name = SHIFTED[name]
                elif final == "~" and codes[0] in ("5", "6"):
                    name = "pgup" if codes[0] == "5" else "pgdn"
                if name:
                    out.append((name, {"1": "press", "2": "repeat", "3": "release"}.get(event, "press")))
                continue
            if data[i] == "\x1b":
                for seq, nm in arcadekit.KEYS.items():
                    if data.startswith(seq, i):
                        out.append((nm, "press"))
                        i += len(seq)
                        break
                else:
                    lone = i + 1 >= len(data) or data[i + 1] not in "[O"
                    if lone:
                        out.append(("esc", "press"))
                    i += 1 if lone else 3
            else:
                ch = data[i]
                out.append(("tab" if ch == "\t" else "enter" if ch in "\r\n" else
                            "backspace" if ch in "\x7f\x08" else ch.lower(), "press"))
                i += 1
        return out


LEFT, RIGHT, JUMP, DOWN = ("left", "a"), ("right", "d"), (" ", "up", "w", "z"), ("down", "s")
HOLD_FIRST, HOLD_REPEAT = 0.55, 0.13


class Controls:
    """Turns key events into the (direction, jump pressed, jump held, down) input of a physics step.

    kitty mode: real held keys; jump height follows the hold, holding jump in the air glides.
    classic mode (no releases): a direction press keeps you running for a window that bridges the initial key
    repeat delay (it learns the delay of your keyboard), every repeat extends it, the other direction turns at
    once, Down stops. Jumps are always full, jump in the air switches the glide on and off."""

    def __init__(self, kitty):
        self.kitty = kitty
        self.held = set()
        self.dir_order = []
        self.jedge = self.down_edge = False
        self.dir = 0
        self.until = 0.0
        self.first = 0.0            # when the current run started (to learn the repeat delay)
        self.repeats = 0
        self.delay = 0.5            # learned initial repeat delay
        self.last_jump = -9.0

    def reset(self):
        self.held.clear()
        self.dir_order = []
        self.jedge = self.down_edge = False
        self.dir = 0
        self.until = 0.0

    def feed(self, name, kind, now):
        if self.kitty:
            if kind == "release":
                self.held.discard(name)
                if name in self.dir_order:
                    self.dir_order.remove(name)
                return
            if kind == "press":
                self.held.add(name)
                if name in LEFT + RIGHT:
                    if name in self.dir_order:
                        self.dir_order.remove(name)
                    self.dir_order.append(name)
                if name in JUMP:
                    self.jedge = True
                if name in DOWN:
                    self.down_edge = True
            return
        if kind == "release":
            return
        if name in LEFT + RIGHT:
            d = -1 if name in LEFT else 1
            if d == self.dir and now < self.until:
                if self.repeats == 0:
                    gap = now - self.first
                    if 0.12 < gap < 0.8:
                        self.delay = clamp(self.delay * 0.5 + gap * 0.5, 0.2, 0.6)
                self.repeats += 1
                self.until = now + HOLD_REPEAT
            else:
                self.dir, self.first, self.repeats = d, now, 0
                self.until = now + min(HOLD_FIRST, self.delay + 0.08)
        elif name in JUMP:
            if now - self.last_jump > 0.09:     # key repeat of a held jump key does not count again
                self.jedge = True
            self.last_jump = now
        elif name in DOWN:
            self.dir, self.until = 0, 0.0
            self.down_edge = True

    def sample(self, now):
        """The input for the next physics step (pressed-edges are used up)."""
        if self.kitty:
            d = 0
            if self.dir_order:
                d = -1 if self.dir_order[-1] in LEFT else 1
            jheld = any(k in self.held for k in JUMP)
            down = self.down_edge or any(k in self.held for k in DOWN)
        else:
            d = self.dir if now < self.until else 0
            if not d:
                self.dir = 0
            jheld = True
            down = self.down_edge
        out = (d, self.jedge, jheld, down)
        self.jedge = self.down_edge = False
        return out


# =============================================================================================
# Pictures: palettes, parallax backdrops, tile art, sprites
# =============================================================================================
def hsh(x, y, s=0):
    h = (x * 374761393 + y * 668265263 + s * 2147483647) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    return (h ^ (h >> 16)) & 0xFFFF


PAL = [
    dict(  # sunlit canopy: warm bark, bright moss
        body=((128, 86, 52), (112, 74, 46), (138, 94, 58)), deep=(84, 56, 38), line=(52, 34, 26),
        top=(122, 192, 64), top_hi=(178, 228, 98), top_lo=(78, 142, 50),
        moss=(88, 176, 74), moss_hi=(150, 222, 96), crumble=(204, 162, 98), crack=(122, 86, 52),
        plank=(156, 108, 62), plank_hi=(206, 160, 98), plank_lo=(96, 64, 40),
        thorn=(124, 44, 58), thorn_hi=(236, 170, 176), water=(56, 140, 182), water_hi=(160, 218, 240),
        water_lo=(30, 86, 128), beetle=((96, 72, 176), (150, 128, 230), (52, 38, 104)),
        plant=((196, 70, 150), (240, 140, 200)), shot=(250, 230, 110), bat=((70, 52, 84), (120, 96, 140))),
    dict(  # crystal caves: violet stone, glowing frost
        body=((70, 60, 104), (62, 52, 94), (78, 68, 114)), deep=(42, 34, 66), line=(24, 18, 40),
        top=(150, 140, 220), top_hi=(214, 206, 255), top_lo=(104, 92, 170),
        moss=(60, 190, 190), moss_hi=(150, 250, 240), crumble=(170, 126, 230), crack=(88, 60, 140),
        plank=(120, 200, 230), plank_hi=(210, 250, 255), plank_lo=(60, 110, 160),
        thorn=(80, 200, 220), thorn_hi=(230, 255, 255), water=(40, 150, 160), water_hi=(150, 255, 240),
        water_lo=(20, 80, 100), beetle=((50, 170, 200), (150, 240, 255), (24, 80, 110)),
        plant=((150, 80, 220), (220, 160, 255)), shot=(170, 255, 240), bat=((40, 30, 60), (110, 80, 150))),
    dict(  # sky ruins: pale stone, green turf
        body=((196, 190, 176), (182, 176, 162), (206, 200, 188)), deep=(150, 144, 136), line=(96, 90, 92),
        top=(130, 196, 92), top_hi=(190, 236, 132), top_lo=(86, 150, 70),
        moss=(98, 168, 84), moss_hi=(160, 214, 116), crumble=(220, 212, 190), crack=(140, 130, 118),
        plank=(212, 206, 196), plank_hi=(250, 248, 240), plank_lo=(140, 134, 128),
        thorn=(150, 120, 90), thorn_hi=(250, 230, 200), water=(90, 160, 230), water_hi=(200, 240, 255),
        water_lo=(60, 110, 190), beetle=((200, 150, 60), (250, 210, 120), (120, 80, 30)),
        plant=((220, 90, 80), (255, 170, 140)), shot=(255, 240, 150), bat=((80, 76, 96), (140, 136, 160))),
    dict(  # autumn storm at night: dark soil under orange leaf litter
        body=((70, 52, 50), (62, 46, 44), (78, 58, 54)), deep=(42, 32, 34), line=(22, 16, 20),
        top=(204, 106, 44), top_hi=(250, 168, 76), top_lo=(140, 64, 34),
        moss=(76, 120, 70), moss_hi=(130, 176, 100), crumble=(140, 100, 70), crack=(70, 48, 40),
        plank=(120, 84, 60), plank_hi=(170, 124, 84), plank_lo=(70, 48, 36),
        thorn=(110, 60, 50), thorn_hi=(230, 180, 140), water=(40, 64, 96), water_hi=(130, 160, 200),
        water_lo=(22, 36, 60), beetle=((170, 50, 40), (240, 120, 80), (90, 24, 20)),
        plant=((120, 160, 60), (190, 220, 110)), shot=(255, 200, 90), bat=((36, 30, 44), (90, 80, 110))),
]

# ---- Leafling himself: L for tiles of 6+ pixels, S for small windows ---------------------------------------
HERO_COLS = {"o": (40, 30, 38), "b": (252, 238, 204), "s": (214, 192, 152), "e": (28, 22, 40), "c": (250, 150, 140),
             "g": (130, 216, 70), "G": (64, 150, 52), "v": (200, 248, 132), "r": (244, 122, 54), "R": (190, 78, 38),
             "f": (96, 62, 44)}
HERO_L = {
    "idle": ["..vgg..", ".gGgGg.", "..ooo..", ".obbbo.", "obbebeo", "obbbbbo", "obbbbco", ".orrRo.", ".obsbo.", ".f...f."],
    "blink": ["..vgg..", ".gGgGg.", "..ooo..", ".obbbo.", "obbobo.", "obbbbbo", "obbbbco", ".orrRo.", ".obsbo.", ".f...f."],
    "run0": ["...vgg.", "..gGgGg", "..ooo..", ".obbbo.", "obbbebe", "obbbbbo", "obbbbco", "RrrrRo.", ".obsbo.", "f....f."],
    "run1": ["...vgg.", "..gGgGg", "..ooo..", ".obbbo.", "obbbebe", "obbbbbo", "obbbbco", "rRrrRo.", ".obsbo.", "..ff..."],
    "run2": ["...vgg.", "..gGgGg", "..ooo..", ".obbbo.", "obbbebe", "obbbbbo", "obbbbco", "RrrrRo.", ".obsbo.", ".f...f."],
    "run3": ["...vgg.", "..gGgGg", "..ooo..", ".obbbo.", "obbbebe", "obbbbbo", "obbbbco", "rRrrRo.", ".obsbo.", "...ff.."],
    "jump": [".vgg...", "gGgGg..", "..ooo..", ".obbbo.", "obbbebe", "obbbbbo", "obbbbco", "rrrrRo.", ".obsbo.", "..f.f.."],
    "fall": ["....gv.", "...gGgg", "..ooo..", ".obbbo.", "obbbebe", "obbbbbo", "obbbbco", ".orrRo.", ".obsbo.", "f.....f"],
    "slide": ["..vgg..", ".gGgGg.", "o.ooo..", "bobbbo.", "obbbebe", "obbbbbo", "obbbbco", ".orrRo.", ".obsbo.", "..f..f."],
    "glide": ["...gvvvg...", ".ggGgggGgg.", "gG..vgv..Gg", ".....o.....", "....ooo....", "...obbbo...",
              "..obbbebe..", "..obbbbbo..", "..obbbbco..", "...orrRo...", "...f...f..."],
}
HERO_S = {
    "idle": ["..gv.", ".gGg.", "obbbo", "obebe", "obbco", ".rrR.", ".f.f."],
    "blink": ["..gv.", ".gGg.", "obbbo", "obobo", "obbco", ".rrR.", ".f.f."],
    "run0": ["...gv", "..gGg", "obbbo", "obbeb", "obbco", "Rrrr.", "f..f."],
    "run1": ["...gv", "..gGg", "obbbo", "obbeb", "obbco", "rRrr.", ".ff.."],
    "run2": ["...gv", "..gGg", "obbbo", "obbeb", "obbco", "Rrrr.", ".f..f"],
    "run3": ["...gv", "..gGg", "obbbo", "obbeb", "obbco", "rRrr.", "..ff."],
    "jump": [".gv..", "gGg..", "obbbo", "obbeb", "obbco", "rrrR.", "..f.."],
    "fall": ["...gv", "..gGg", "obbbo", "obbeb", "obbco", ".rrR.", "f...f"],
    "slide": ["..gv.", "bgGg.", "obbbo", "obbeb", "obbco", ".rrR.", "..ff."],
    "glide": [".ggvgg.", "gG...Gg", ".obbbo.", ".obbeb.", ".obbco.", "..rrR..", "..f.f.."],
}
_SPR = {}


def sprite(art, name, flip):
    """Hero frame as rows of colours (None = see-through), cached."""
    k = (id(art), name, flip)
    s = _SPR.get(k)
    if s is None:
        rows = art[name]
        s = [[HERO_COLS.get(ch) for ch in (r[::-1] if flip else r)] for r in rows]
        _SPR[k] = s
    return s


def blit_scaled(px, W, H, img, cx, by, sx=1.0, sy=1.0, tint=None):
    """Draw img with its bottom centre at (cx, by), scaled (nearest) by sx, sy."""
    h0, w0 = len(img), len(img[0])
    w, h = max(1, int(round(w0 * sx))), max(1, int(round(h0 * sy)))
    x0, y0 = int(round(cx - w / 2)), int(round(by - h))
    for j in range(h):
        y = y0 + j
        if not 0 <= y < H:
            continue
        src = img[min(h0 - 1, int(j * h0 / h))]
        row = px[y]
        for i in range(w):
            x = x0 + i
            if 0 <= x < W:
                c = src[min(w0 - 1, int(i * w0 / w))]
                if c is not None:
                    row[x] = c if tint is None else mix(c, tint[0], tint[1])


def add_glow(px, W, H, cx, cy, r, col, k):
    """Additive soft light around (cx, cy)."""
    r2 = r * r
    for y in range(max(0, int(cy - r)), min(H, int(cy + r) + 1)):
        dy = y + 0.5 - cy
        row = px[y]
        for x in range(max(0, int(cx - r)), min(W, int(cx + r) + 1)):
            dx = x + 0.5 - cx
            d = dx * dx + dy * dy
            if d < r2:
                a = k * (1 - d / r2) ** 2
                c = row[x]
                row[x] = (min(255, int(c[0] + col[0] * a)), min(255, int(c[1] + col[1] * a)),
                          min(255, int(c[2] + col[2] * a)))


def disc(px, W, H, cx, cy, r, col):
    r2 = r * r
    for y in range(max(0, int(cy - r)), min(H, int(cy + r) + 1)):
        dy = y + 0.5 - cy
        row = px[y]
        for x in range(max(0, int(cx - r)), min(W, int(cx + r) + 1)):
            dx = x + 0.5 - cx
            if dx * dx + dy * dy <= r2:
                row[x] = col


def pset(px, W, H, x, y, c):
    x, y = int(x), int(y)
    if 0 <= x < W and 0 <= y < H:
        px[y][x] = c


def wave(x, period, terms, seed):
    """A smooth, exactly periodic wiggle in -1..1-ish."""
    rnd = random.Random(seed)
    v = 0.0
    for k, a in terms:
        v += a * math.sin(2 * math.pi * k * x / period + rnd.uniform(0, 6.283))
    return v


class Backdrop:
    """The sky and two or three parallax layers of one world, for one canvas size."""

    def __init__(self, biome, W, H):
        self.biome, self.W, self.H = biome, W, H
        self.m = m = max(2, H // 6)               # vertical margin for the gentle vertical parallax
        self.P = P = max(256, (W * 2 // 64 + 1) * 64)
        self.sky = self.make_sky(False)
        self.layers = self.make_layers(False)
        if biome == 3:
            self.sky_flash = self.make_sky(True)
            self.layers_flash = self.make_layers(True)

    def grad(self, stops, n=None, k=1.0):
        """Colour table indexed by y + margin from a list of (position 0..1, colour)."""
        n = n or self.H + 2 * self.m
        out = []
        for i in range(n):
            t = (i - self.m) / max(1, self.H - 1)
            t = clamp(t, 0.0, 1.0)
            for j in range(len(stops) - 1):
                if stops[j][0] <= t <= stops[j + 1][0]:
                    a, b = stops[j], stops[j + 1]
                    c = mix(a[1], b[1], (t - a[0]) / max(1e-6, b[0] - a[0]))
                    break
            else:
                c = stops[-1][1]
            out.append(shade(c, k))
        return out

    def make_sky(self, flash):
        W, H, b = self.W, self.H, self.biome
        rnd = random.Random(7 + b)
        if b == 0:
            stops = [(0, (104, 172, 228)), (0.55, (196, 226, 228)), (1, (236, 238, 196))]
        elif b == 1:
            stops = [(0, (20, 12, 38)), (0.5, (40, 24, 64)), (1, (24, 16, 44))]
        elif b == 2:
            stops = [(0, (84, 146, 232)), (0.6, (180, 214, 248)), (1, (232, 240, 252))]
        else:
            stops = [(0, (10, 12, 30)), (0.6, (36, 28, 56)), (1, (66, 40, 50))]
            if flash:
                stops = [(0, (170, 172, 210)), (0.6, (210, 210, 236)), (1, (150, 140, 170))]
        tab = self.grad(stops)
        sky = [[tab[y + self.m]] * W for y in range(H)]
        if b == 0:                                  # the sun with a soft halo and light shafts
            sx, sy = W * 0.78, H * 0.16
            for y in range(H):
                row = sky[y] = list(sky[y])
                for x in range(W):
                    d = math.hypot((x - sx) / max(1, H), (y - sy) / max(1, H))
                    shaft = max(0.0, math.sin((x - y * 0.6) * 0.09 + 1.3)) ** 6 * 0.08 * (1 - y / H)
                    a = max(0.0, 0.55 - d) ** 2 * 1.4 + shaft
                    if d < 0.05:
                        a = 1.0
                    if a > 0:
                        row[x] = mix(row[x], (255, 250, 220), min(1.0, a))
        elif b == 2:                                # big soft clouds
            for c in range(max(3, W // 30)):
                cx, cy, r = rnd.uniform(0, W), rnd.uniform(H * 0.1, H * 0.55), rnd.uniform(H * 0.06, H * 0.14)
                for k in range(5):
                    bx, by, br = cx + rnd.uniform(-2.2, 2.2) * r, cy + rnd.uniform(-0.3, 0.3) * r, r * rnd.uniform(0.7, 1.2)
                    for y in range(max(0, int(by - br)), min(H, int(by + br))):
                        row = sky[y] = list(sky[y])
                        for x in range(max(0, int(bx - br * 1.6)), min(W, int(bx + br * 1.6))):
                            d = ((x - bx) / 1.6) ** 2 + (y - by) ** 2
                            if d < br * br:
                                lit = 1.0 - max(0.0, (y - by) / br) * 0.25
                                row[x] = mix(row[x], shade((250, 252, 255), lit), 0.85)
        elif b in (1, 3):                           # faint stars / crystal glints
            for i in range(W * H // (60 if b == 3 else 90)):
                x, y = rnd.randrange(W), rnd.randrange(int(H * (0.7 if b == 3 else 1.0)))
                row = sky[y] = list(sky[y])
                tw = rnd.random()
                c = (200, 200, 255) if b == 3 else rnd.choice([(120, 220, 255), (220, 140, 255)])
                row[x] = mix(row[x], c, 0.25 + 0.4 * tw * (0.3 if flash else 1))
        return sky

    def make_layers(self, flash):
        """[(parallax factor, columns)]; columns[x] = [(y0, y1, colour table), ...] in layer pixels."""
        W, H, P, m, b = self.W, self.H, self.P, self.m, self.biome
        layers = []
        sil = flash

        def col_list():
            return [[] for _ in range(P)]

        def tabs(stops, k=1.0):
            if sil:
                return self.grad([(0, (18, 16, 28)), (1, (10, 10, 16))])
            return self.grad(stops, k=k)

        if b == 0:
            far = col_list()
            t_far = tabs([(0, (168, 206, 196)), (1, (130, 178, 150))])
            t_rim = tabs([(0, (196, 226, 206)), (1, (160, 200, 170))])
            for x in range(P):
                hgt = H * 0.40 + H * 0.07 * wave(x, P, [(3, 1.0), (7, 0.5)], 1) - H * 0.07 * abs(math.sin(x * 2 * math.pi * 13 / P))
                y0 = int(hgt)
                far[x] += [(y0, y0 + 1, t_rim), (y0 + 1, H + m, t_far)]
            layers.append((0.12, far))
            mid = col_list()
            t_leaf = tabs([(0, (96, 156, 92)), (1, (70, 126, 72))])
            t_leaf_rim = tabs([(0, (140, 196, 116)), (1, (110, 170, 96))])
            t_tr = [tabs([(0, (120, 106, 90)), (1, (96, 84, 72))]), tabs([(0, (104, 92, 78)), (1, (82, 72, 62))]),
                    tabs([(0, (84, 74, 64)), (1, (66, 58, 50))])]
            t_bush = tabs([(0, (84, 146, 84)), (1, (62, 112, 64))])
            trunks = [(P * k // 5 + int(P / 5 * 0.3 * math.sin(k * 2.1)), 5 + (k * 3) % 5) for k in range(5)]
            for x in range(P):
                ceil = int(H * 0.16 + H * 0.06 * wave(x, P, [(4, 1.0), (11, 0.4)], 2) + H * 0.05 * abs(math.sin(x * 2 * math.pi * 17 / P)))
                for tx, tw in trunks:
                    dx = (x - tx) % P
                    if dx < tw:
                        mid[x].append((-m, H + m, t_tr[0 if dx == 0 else 2 if dx == tw - 1 else 1]))
                mid[x] += [(-m, ceil, t_leaf), (ceil, ceil + 1, t_leaf_rim)]
                bush = int(H * 0.82 + H * 0.05 * wave(x, P, [(6, 1.0), (15, 0.5)], 3))
                mid[x] += [(bush, bush + 1, t_leaf_rim), (bush + 1, H + m, t_bush)]
            layers.append((0.3, mid))
            near = col_list()
            t_vine = tabs([(0, (60, 118, 62)), (1, (48, 98, 52))])
            t_vleaf = tabs([(0, (98, 168, 82)), (1, (80, 146, 70))])
            rnd = random.Random(5)
            for k in range(P // 23):
                x = rnd.randrange(P)
                ln = int(H * rnd.uniform(0.12, 0.5))
                near[x].append((-m, ln, t_vine))
                for j in range(3, ln, 4):
                    xx = (x + (1 if (j // 4) % 2 else -1)) % P
                    near[xx].append((j, j + 1, t_vleaf))
            layers.append((0.55, near))
        elif b == 1:
            far = col_list()
            t_rock = tabs([(0, (50, 38, 82)), (1, (40, 30, 66))])
            for x in range(P):
                st = int(H * 0.2 + H * 0.12 * abs(wave(x, P, [(9, 1.0), (23, 0.6)], 4)) + H * 0.1 * max(0.0, math.sin(x * 2 * math.pi * 29 / P)) ** 4)
                sg = int(H * 0.78 - H * 0.16 * max(0.0, math.sin(x * 2 * math.pi * 19 / P + 1)) ** 3 - H * 0.05 * wave(x, P, [(7, 1.0)], 5))
                far[x] += [(-m, st, t_rock), (sg, H + m, t_rock)]
            layers.append((0.15, far))
            mid = col_list()
            t_c1 = [tabs([(0, (170, 250, 255)), (1, (60, 150, 190))]), tabs([(0, (110, 210, 240)), (1, (40, 100, 150))])]
            t_c2 = [tabs([(0, (240, 180, 255)), (1, (120, 60, 170))]), tabs([(0, (190, 130, 240)), (1, (80, 40, 130))])]
            t_base = tabs([(0, (36, 28, 60)), (1, (28, 22, 48))])
            rnd = random.Random(8)
            for x in range(P):
                g = int(H * 0.86 + H * 0.04 * wave(x, P, [(5, 1.0)], 6))
                mid[x].append((g, H + m, t_base))
            for k in range(P // 18):
                cx, hw, ht = rnd.randrange(P), rnd.randint(2, 4), rnd.uniform(0.12, 0.3) * H
                tt = t_c1 if k % 3 else t_c2
                base = int(H * 0.87)
                for dx in range(-hw, hw + 1):
                    top = int(base - ht * (1 - abs(dx) / (hw + 1)))
                    mid[(cx + dx) % P].append((top, base, tt[0 if dx <= 0 else 1]))
            layers.append((0.35, mid))
        elif b == 2:
            far = col_list()
            t_is = tabs([(0, (176, 198, 232)), (1, (150, 172, 214))])
            t_is_top = tabs([(0, (196, 222, 216)), (1, (170, 200, 196))])
            rnd = random.Random(9)
            for k in range(max(3, P // 90)):
                cx, hw, cy = rnd.randrange(P), rnd.randint(10, 24), int(H * rnd.uniform(0.3, 0.6))
                for dx in range(-hw, hw + 1):
                    t = abs(dx) / hw
                    top = cy - int(2 * (1 - t * t))
                    bot = cy + int(hw * 0.5 * (1 - t) ** 1.5) + 1
                    far[(cx + dx) % P] += [(top, top + 1, t_is_top), (top + 1, bot, t_is)]
            layers.append((0.08, far))
            mid = col_list()
            t_st = [tabs([(0, (220, 218, 232)), (1, (190, 188, 206))]), tabs([(0, (196, 194, 212)), (1, (168, 166, 188))]),
                    tabs([(0, (170, 168, 190)), (1, (146, 144, 168))])]
            x = 0
            while x < P - 30:
                w = rnd.randint(4, 7)
                top = int(H * rnd.uniform(0.25, 0.6))
                for dx in range(w):
                    brk = top + (hsh(x + dx, 3) % 3 if dx in (0, w - 1) else 0)
                    mid[(x + dx) % P].append((brk, H + m, t_st[0 if dx == 0 else 2 if dx == w - 1 else 1]))
                if rnd.random() < 0.6:                       # an arch beam to the next column
                    gap = rnd.randint(8, 18)
                    by = top + rnd.randint(2, 5)
                    for dx in range(w, w + gap):
                        mid[(x + dx) % P].append((by, by + 2, t_st[1]))
                    x += w + gap
                else:
                    x += w + rnd.randint(10, 30)
            layers.append((0.25, mid))
            near = col_list()
            t_cl = tabs([(0, (250, 252, 255)), (1, (220, 232, 246))])
            t_cl_lo = tabs([(0, (214, 226, 242)), (1, (196, 212, 236))])
            for x in range(P):
                top = int(H * 0.86 - H * 0.07 * abs(math.sin(x * 2 * math.pi * 9 / P)) - H * 0.03 * wave(x, P, [(4, 1.0)], 10))
                near[x] += [(top, top + 3, t_cl), (top + 3, H + m, t_cl_lo)]
            layers.append((0.5, near))
        else:
            far = col_list()
            t_hill = tabs([(0, (34, 30, 58)), (1, (28, 24, 44))])
            for x in range(P):
                top = int(H * 0.6 + H * 0.08 * wave(x, P, [(2, 1.0), (5, 0.4)], 11))
                far[x].append((top, H + m, t_hill))
            layers.append((0.1, far))
            mid = col_list()
            t_tr = tabs([(0, (58, 46, 60)), (1, (44, 34, 46))])
            t_lf = [tabs([(0, (130, 64, 44)), (1, (100, 48, 38))], 0.62), tabs([(0, (170, 96, 52)), (1, (126, 66, 42))], 0.62)]
            rnd = random.Random(12)
            for x in range(P):
                g = int(H * 0.78 + H * 0.03 * wave(x, P, [(4, 1.0)], 13))
                mid[x].append((g, H + m, t_tr))
            for k in range(P // 40):
                cx, ht = rnd.randrange(P), int(H * rnd.uniform(0.3, 0.55))
                base = int(H * 0.8)
                tw = rnd.randint(1, 2)
                for dx in range(tw):
                    mid[(cx + dx) % P].append((base - ht, base, t_tr))
                for br in range(3):                              # a few branches with leaf clumps
                    by = base - ht + br * ht // 5
                    d = 1 if br % 2 else -1
                    ln = rnd.randint(3, 7)
                    for j in range(ln):
                        mid[(cx + d * j) % P].append((by - j // 2, by - j // 2 + 1, t_tr))
                    lx, ly, lr = cx + d * ln, by - ln // 2, rnd.randint(2, 4)
                    for dx in range(-lr - 1, lr + 2):
                        h = math.sqrt(max(0, lr * lr - dx * dx * 0.8)) * 0.8
                        h1 = int(h + (hsh(lx + dx, ly) % 3) * 0.5)
                        h0 = int(h * 0.7 + (hsh(lx + dx, ly, 2) % 2))
                        if h1 or h0:
                            mid[(lx + dx) % P].append((ly - h1, ly + h0, t_lf[(hsh(dx, br) // 3) % 2]))
            layers.append((0.3, mid))
            near = col_list()
            t_gr = tabs([(0, (26, 22, 36)), (1, (20, 16, 28))])
            for x in range(P):
                top = int(H * 0.88 - (hsh(x, 1) % 5) * H * 0.012 - H * 0.03 * wave(x, P, [(6, 1.0)], 14))
                near[x].append((top, H + m, t_gr))
            layers.append((0.5, near))
        return layers

    def paint(self, cv, camx, camy, T, lvh, flash=False):
        px, W, H, m = cv.px, self.W, self.H, self.m
        sky = self.sky_flash if flash else self.sky
        for y in range(H):
            px[y] = sky[y][:]
        for factor, cols in (self.layers_flash if flash else self.layers):
            off = int(camx * T * factor)
            oy = int(clamp(-(camy - lvh * 0.3) * T * factor * 0.35, -m + 1, m - 1))
            P = self.P
            for sx in range(W):
                for y0, y1, tab in cols[(sx + off) % P]:
                    a, b = y0 + oy, y1 + oy
                    if a < 0:
                        a = 0
                    if b > H:
                        b = H
                    for y in range(a, b):
                        px[y][sx] = tab[y - oy + m]


_BACKDROPS = {}


def backdrop(biome, W, H):
    k = (biome, W, H)
    if k not in _BACKDROPS:
        if len(_BACKDROPS) > 8:
            _BACKDROPS.clear()
        _BACKDROPS[k] = Backdrop(biome, W, H)
    return _BACKDROPS[k]


SOLIDISH = (SOL, MOSS, HID)


def tile_keys(lv):
    """Which picture each tile gets: (kind, open-sides mask, variant, deep)."""
    code, W, H = lv.code, lv.W, lv.H
    keys = [[None] * W for _ in range(H)]

    def sol(x, y):
        if x < 0 or x >= W:
            return True
        if y < 0:
            return lv.biome == 1
        if y >= H:
            return True
        return code[y][x] in SOLIDISH

    for y in range(H):
        for x in range(W):
            c = code[y][x]
            v = hsh(x, y) % 4
            if c in SOLIDISH:
                mask = ((not sol(x, y - 1)) * 1 | (not sol(x, y + 1)) * 2 | (not sol(x - 1, y)) * 4 |
                        (not sol(x + 1, y)) * 8)
                deep = 0 if mask else (2 if sol(x, y - 2) and sol(x, y - 1) and sol(x - 1, y - 1) and sol(x + 1, y - 1) else 1)
                mossy = 0
                if c == MOSS:
                    mossy = 1
                keys[y][x] = ("S", mask, v, deep, mossy)
            elif c == CRUM:
                keys[y][x] = ("C", (code[y][x - 1] == CRUM if x > 0 else 0) * 1 + (code[y][x + 1] == CRUM if x < W - 1 else 0) * 2, v)
            elif c == ONE:
                keys[y][x] = ("O", (code[y][x - 1] == ONE if x > 0 else 0) * 1 + (code[y][x + 1] == ONE if x < W - 1 else 0) * 2, v)
            elif c in (THU, THD):
                keys[y][x] = ("T", c == THD, v)
            elif c == WAT:
                keys[y][x] = ("W", y == 0 or code[y - 1][x] != WAT, v)
            elif c == GATE:
                keys[y][x] = ("G", 0, v)
    return keys


def make_tile(biome, key, T, frame=0):
    """The pixels of one tile: (opaque?, T rows of T colours / None)."""
    p = PAL[biome]
    kind = key[0]
    img = [[None] * T for _ in range(T)]
    if kind == "S":
        _, mask, v, deep, mossy = key
        top_open, bot_open, l_open, r_open = mask & 1, mask & 2, mask & 4, mask & 8
        dark = (1.0, 0.86, 0.72)[deep]
        ts = max(1, (T + 1) // 3)
        for y in range(T):
            for x in range(T):
                h = hsh(x + v * 17, y + v * 5, biome)
                c = p["body"][h % 3]
                if biome == 0 and (x + (y // 3) * 2 + v) % 5 == 0:
                    c = shade(c, 0.88)                    # bark grain
                elif biome == 1 and h % 97 == 0 and deep < 2:
                    c = mix(c, p["moss_hi"] if h % 2 else p["top_hi"], 0.6)      # crystal flecks
                elif biome == 1 and (x + y * 2 + v) % 7 == 0:
                    c = shade(c, 0.9)
                elif biome == 2 and (y == T - 1 or (x == (0 if (y // max(2, T // 2)) % 2 else T // 2))):
                    c = shade(c, 0.84)                    # mortar between bricks
                elif biome == 3 and h % 17 == 0:
                    c = shade(p["top_lo"], 0.7)           # buried leaves
                img[y][x] = shade(c, dark)
        if l_open:
            for y in range(T):
                img[y][0] = mix(img[y][0], p["line"], 0.55)
        if r_open:
            for y in range(T):
                img[y][T - 1] = mix(img[y][T - 1], p["line"], 0.75)
        if bot_open:
            for x in range(T):
                img[T - 1][x] = p["line"]
                if T >= 6:
                    img[T - 2][x] = mix(img[T - 2][x], p["line"], 0.4)
        if mossy:
            for side, op in ((0, l_open), (T - 1, r_open)):
                if op:
                    d = 1 if side == 0 else -1
                    for y in range(T):
                        ln = 1 + (hsh(y, v, side) % 3 == 0) + (T >= 6)
                        for k in range(ln):
                            xx = side + d * k
                            img[y][xx] = p["moss_hi"] if k == 0 and (y + v) % 3 == 0 else p["moss"]
        if top_open:
            for x in range(T):
                h = hsh(x, v, 9)
                depth = ts + (1 if h % 3 == 0 else 0) - (1 if h % 5 == 0 and ts > 1 else 0)
                for y in range(min(T, depth)):
                    img[y][x] = p["top_hi"] if y == 0 else (p["top"] if y < depth - 1 else p["top_lo"])
                if T >= 6 and depth < T and h % 4 == 0:
                    img[depth][x] = p["top_lo"]             # a drip of turf over the edge
            if l_open:
                img[0][0] = mix(p["top"], p["line"], 0.4)
            if r_open:
                img[0][T - 1] = mix(p["top"], p["line"], 0.5)
        return (not False, img)
    if kind == "C":
        _, nb, v = key
        for y in range(T):
            for x in range(T):
                c = p["crumble"]
                if y == 0:
                    c = mix(c, (255, 255, 255), 0.35)
                elif y == T - 1 or (x == T - 1 and not nb & 2) or (x == 0 and not nb & 1):
                    c = p["crack"]
                elif (x + y + v) % max(3, T // 2 + 1) == 0 or (x - y + v) % (T + 1) == 0:
                    c = p["crack"]
                elif hsh(x, y, v) % 7 == 0:
                    c = shade(c, 0.9)
                img[y][x] = c
        return (True, img)
    if kind == "O":
        _, nb, v = key
        th = max(2, T // 3)
        for y in range(th):
            for x in range(T):
                c = p["plank_hi"] if y == 0 else (p["plank_lo"] if y == th - 1 else p["plank"])
                if biome in (0, 3) and y > 0 and (x + v * 3) % 7 == 0:
                    c = p["plank_lo"]
                if (x == 0 and not nb & 1) or (x == T - 1 and not nb & 2):
                    c = mix(c, p["line"], 0.5)
                img[y][x] = c
        if biome == 0 and T >= 6:                         # little leaves on the branch
            for x in range(T):
                if hsh(x, v, 4) % 5 == 0:
                    img[th][x] = p["top"]
        if biome == 1:                                    # crystal ledges drip light
            for x in range(T):
                if hsh(x, v, 6) % 4 == 0 and th < T:
                    img[th][x] = p["plank_lo"]
        return (False, img)
    if kind == "T":
        _, down, v = key
        n = 2 if T < 8 else 3
        w = T / n
        hgt = max(3, int(T * 0.75))
        for k in range(n):
            cx = (k + 0.5) * w
            for y in range(hgt):
                half = (y + 1) / hgt * w * 0.5
                for x in range(T):
                    if abs(x + 0.5 - cx) <= half:
                        yy = T - hgt + y
                        c = p["thorn_hi"] if y == 0 else (p["thorn"] if abs(x + 0.5 - cx) < half * 0.6 else shade(p["thorn"], 0.7))
                        img[(T - 1 - yy) if down else yy][x] = c
        return (False, img)
    if kind == "W":
        _, surface, v = key
        top = int(T * 0.35) if surface else 0
        for y in range(top, T):
            for x in range(T):
                c = mix(p["water"], p["water_lo"], (y - top) / max(1, T) * 0.7)
                if surface and y == top:
                    c = p["water_hi"] if (x + frame + v) % 4 < 2 else p["water"]
                elif (x * 3 + y * 5 + frame * 2 + v) % 11 == 0:
                    c = mix(c, p["water_hi"], 0.35)
                img[y][x] = c
        return (not surface, img)
    if kind == "G":
        for y in range(T):
            for x in range(T):
                if x in (1, T - 2) or (T >= 6 and x == T // 2):
                    img[y][x] = p["thorn"] if (y + x) % 3 else p["thorn_hi"]
        return (False, img)
    return (False, img)


class Painter:
    """Draws a level (tiles, things, Leafling, particles) into a canvas."""

    def __init__(self, lv):
        self.lv = lv
        self.keys = tile_keys(lv)
        self.cache = {}

    def tile(self, key, T, frame=0):
        k = (key, T, frame)
        t = self.cache.get(k)
        if t is None:
            t = self.cache[k] = make_tile(self.lv.biome, key, T, frame)
        return t

    def paint_tiles(self, cv, sim, ox, oy, T, t, near_hidden):
        lv, px, W, H = self.lv, cv.px, cv.W, cv.H
        tx0, ty0 = ox // T, oy // T
        wf = int(t * 4) % 4
        gate_on = lv.boss is not None and sim is not None and sim.boss is not None and not sim.boss_done
        for ty in range(max(0, ty0), min(lv.H, ty0 + H // T + 2)):
            sy = ty * T - oy
            krow = self.keys[ty]
            crow = lv.code[ty]
            for tx in range(max(0, tx0), min(lv.W, tx0 + W // T + 2)):
                key = krow[tx]
                if key is None:
                    continue
                c = crow[tx]
                sx = tx * T - ox
                shake = 0
                if c == CRUM and sim is not None:
                    st = sim.crumble.get((tx, ty))
                    if st is not None:
                        age = sim.f - st
                        if age >= CRUMBLE_GONE:
                            continue
                        shake = (1 if (age // 3) % 2 else -1) if age > 6 else 0
                if c == GATE and not gate_on:
                    continue
                opaque, img = self.tile(key, T, wf if key[0] == "W" else 0)
                ghost = c == HID and (tx, ty) in near_hidden
                if opaque and not ghost and not shake:
                    a, b = max(0, sx), min(W, sx + T)
                    if b <= a:
                        continue
                    for r in range(T):
                        y = sy + r
                        if 0 <= y < H:
                            px[y][a:b] = img[r][a - sx:b - sx]
                else:
                    for r in range(T):
                        y = sy + r
                        if not 0 <= y < H:
                            continue
                        row, src = px[y], img[r]
                        for i in range(T):
                            x = sx + i + shake
                            if 0 <= x < W and src[i] is not None:
                                row[x] = mix(row[x], src[i], 0.35) if ghost else src[i]

    # -- the things in a level --------------------------------------------------------------
    def paint_things(self, cv, sim, fx, ox, oy, T, t):
        lv, px, W, H = self.lv, cv.px, cv.W, cv.H
        p = PAL[lv.biome]
        f = sim.f if sim else int(t * 60)
        X = lambda x: int(math.floor(x * T)) - ox
        Y = lambda y: int(math.floor(y * T)) - oy
        vis = lambda x, y, r=2: -r * T < X(x) < W + r * T and -r * T < Y(y) < H + r * T
        glow = T >= 5 or lv.biome in (1, 3)
        # moving platforms
        for i in range(len(lv.plats)):
            x, y = lv.plat_pos(i, f)
            w = lv.plats[i][3]
            if not vis(x + w / 2, y, w):
                continue
            x0, y0 = int(X(x)), int(Y(y))
            th = max(2, T // 2)
            for yy in range(th):
                c = p["plank_hi"] if yy == 0 else (p["plank_lo"] if yy == th - 1 else p["plank"])
                for xx in range(w * T):
                    if xx in (0, w * T - 1):
                        c2 = mix(c, p["line"], 0.6)
                    elif (xx + yy) % 5 == 0 and yy:
                        c2 = shade(c, 0.9)
                    else:
                        c2 = c
                    pset(px, W, H, x0 + xx, y0 + yy, c2)
            if lv.biome in (1, 2):                    # floating: a faint glow underneath
                add_glow(px, W, H, x0 + w * T / 2, y0 + th + 1, T * 0.9, (90, 160, 200) if lv.biome == 1 else (200, 210, 240), 0.25)
        # springy mushrooms
        for sx, sy in lv.springs:
            if not vis(sx, sy):
                continue
            sq = fx.spring_squash.get((sx, sy), 0.0) if fx else 0.0
            cx, base = X(sx + 0.5), Y(sy + 1)
            stem_h = max(2, int(T * 0.45 * (1 - sq * 0.6)))
            cap_w, cap_h = max(3, int(T * 0.95 * (1 + sq * 0.3))), max(2, int(T * 0.42 * (1 - sq * 0.4)))
            sw = max(1, T // 4)
            for yy in range(stem_h):
                for xx in range(-sw, sw + 1):
                    pset(px, W, H, cx + xx, base - 1 - yy, (238, 226, 200) if xx < sw else (200, 186, 160))
            ctop = base - stem_h - cap_h
            for yy in range(cap_h):
                half = cap_w / 2 * (0.6 + 0.4 * (yy + 1) / cap_h)
                for xx in range(int(-half), int(half) + 1):
                    c = (242, 150, 52) if yy else (255, 196, 96)
                    if yy == cap_h - 1:
                        c = (190, 96, 34)
                    elif (xx + yy * 2 + sx) % 4 == 0 and yy > 0:
                        c = (255, 236, 196)
                    pset(px, W, H, cx + xx, ctop + yy, c)
        # lanterns
        for i, (lx, ly) in enumerate(lv.lanterns):
            if not vis(lx, ly):
                continue
            lit = sim is not None and sim.lit >> i & 1
            cx, base = X(lx), Y(ly)
            top = base - int(T * 1.5)
            for yy in range(top + 2, base):
                pset(px, W, H, cx, yy, (70, 52, 40))
            pset(px, W, H, cx - 1, base - 1, (70, 52, 40))
            pset(px, W, H, cx + 1, base - 1, (70, 52, 40))
            lc = (255, 214, 120) if lit else (110, 120, 140)
            lw = max(1, T // 4)
            for yy in range(max(2, T // 2)):
                for xx in range(-lw, lw + 1):
                    pset(px, W, H, cx + xx, top + yy, lc if 0 < yy and abs(xx) < lw else (60, 46, 38))
            if lit:
                fl = 0.75 + 0.25 * math.sin(t * 9 + i * 2) * math.sin(t * 5.3 + i)
                add_glow(px, W, H, cx + 0.5, top + T * 0.3, T * 1.6, (255, 190, 90), 0.45 * fl)
        # the leaf gate (exit)
        if lv.exit and vis(*lv.exit):
            ex, ey = lv.exit
            open_ = sim is None or sim.gate_open()
            cx, base = X(ex), Y(ey)
            rw, rh = T * 0.75, T * 1.0
            cy = base - rh
            if open_:
                add_glow(px, W, H, cx, cy, T * 1.8, (190, 255, 160), 0.35 + 0.1 * math.sin(t * 3))
            for yy in range(int(cy - rh) - 1, base):
                for xx in range(int(cx - rw) - 1, int(cx + rw) + 2):
                    dx, dy = (xx + 0.5 - cx) / rw, (yy + 0.5 - cy) / rh
                    d = dx * dx + dy * dy if yy < cy else dx * dx
                    if d < 0.55 and open_:
                        sw = math.sin(math.atan2(dy, dx) * 3 + t * 4 - d * 6)
                        pset(px, W, H, xx, yy, mix((220, 255, 200), (120, 220, 140), 0.5 + 0.5 * sw))
                    elif d < 0.55:
                        pset(px, W, H, xx, yy, (40, 46, 40))
                    elif d < 1.15:
                        h = hsh(xx, yy, 3)
                        c = (110, 196, 70) if h % 3 else (170, 230, 100)
                        if not open_:
                            c = shade(c, 0.45)
                        pset(px, W, H, xx, yy, c)
        # motes and seeds
        for i, (mx, my) in enumerate(lv.motes):
            if sim is not None and i in sim.motes or not vis(mx, my, 1):
                continue
            bob = math.sin(t * 3 + i * 0.7) * T * 0.12
            cx, cy = X(mx), Y(my) + bob
            if glow:
                add_glow(px, W, H, cx, cy, T * 0.55, (255, 230, 150), 0.5)
            core, rim = (255, 252, 226), (236, 158, 40)
            tw = int(t * 6 + i) % 8 == 0
            if T >= 6:
                for qx, qy in ((0, -2), (-2, 0), (1, 0), (0, 1), (-1, -2), (1, -1), (-2, -1), (-1, 1)):
                    pset(px, W, H, cx + qx, cy + qy, rim)
                for qx, qy in ((0, 0), (-1, 0), (0, -1), (-1, -1)):
                    pset(px, W, H, cx + qx, cy + qy, core)
            else:
                for qx, qy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
                    pset(px, W, H, cx + qx, cy + qy, rim)
                pset(px, W, H, cx, cy, core)
            if tw:
                pset(px, W, H, cx, cy - 2 - (T >= 6), (255, 255, 255))
        for i, (sx, sy) in enumerate(lv.seeds):
            if sim is not None and sim.seeds >> i & 1 or not vis(sx, sy, 1):
                continue
            if lv.code[int(sy)][int(sx)] == HID and sim is not None and not fx_near(sim, sx, sy):
                continue
            bob = math.sin(t * 2.2 + i) * T * 0.1
            cx, cy = X(sx), Y(sy) + bob
            add_glow(px, W, H, cx, cy, T * 0.8, (255, 210, 90), 0.35)
            rw, rh = max(1.2, T * 0.22), max(1.6, T * 0.32)
            for yy in range(int(cy - rh), int(cy + rh) + 1):
                for xx in range(int(cx - rw), int(cx + rw) + 1):
                    d = ((xx + 0.5 - cx) / rw) ** 2 + ((yy + 0.5 - cy) / rh) ** 2
                    if d <= 1.0:
                        pset(px, W, H, xx, yy, (255, 236, 150) if xx < cx and yy < cy else (224, 156, 50))
            if int(t * 3 + i) % 3 == 0:                  # twinkle
                k = int(T * 0.5)
                for d in range(1, k):
                    for qx, qy in ((d, 0), (-d, 0), (0, d), (0, -d)):
                        pset(px, W, H, cx + qx, cy - rh + qy, (255, 255, 230))
        # enemies
        dead = sim.dead_en if sim else frozenset()
        bp = p["beetle"]
        for i in range(len(lv.beetles)):
            if (3, i) in dead:
                continue
            x, y, d = lv.beetle_pos(i, f)
            if vis(x, y):
                draw_beetle(px, W, H, X(x), Y(y), T * 0.95, T * 0.72, d, bp, f // 6)
        for i in range(len(lv.bats)):
            if (4, i) in dead:
                continue
            x, y, s = lv.bat_pos(i, f)
            if vis(x, y):
                draw_bat(px, W, H, X(x), Y(y), T, s, p["bat"], t + i)
        for i in range(len(lv.plants)):
            x, y, d, rng, off = lv.plants[i]
            for sx, sy in lv.shots(i, f):
                if vis(sx, sy):
                    add_glow(px, W, H, X(sx), Y(sy), T * 0.45, p["shot"], 0.5)
                    disc(px, W, H, X(sx), Y(sy), max(1.0, T * 0.17), p["shot"])
            if (5, i) in dead or not vis(x, y):
                continue
            draw_plant(px, W, H, X(x), Y(y), T, d, lv.plant_mouth(i, f), p["plant"], t + i)
        # the boss
        if lv.boss and sim is not None and (sim.boss or not sim.boss_done):
            if sim.boss:
                st, tm, bx, bvx, hp, face = sim.boss
            else:
                st, tm, bx, bvx, hp, face = WAIT, 0, lv.boss_at[0], 0.0, lv.boss["hp"], -1
            if st != DEAD:
                draw_boss(px, W, H, X(bx), Y(lv.boss_at[1]), T, st, tm, face, lv.boss["kind"], t)
        # the chasing bramble / storm front
        if lv.chase and sim is not None:
            cxp = sim.chase_pos()
            if cxp is not None:
                draw_chase(px, W, H, X(cxp), T, lv.biome, t)

    def paint_hero(self, cv, sim, fx, ox, oy, T, t):
        px, W, H = cv.px, cv.W, cv.H
        if sim.dead or (fx and fx.blink > 0 and int(fx.blink * 12) % 2):
            return
        art = HERO_L if T >= 6 else HERO_S
        flip = sim.facing < 0
        if sim.sliding:
            name, flip = "slide", sim.wall > 0
        elif sim.glide and not sim.ground and sim.vy >= 0:
            name = "glide"
        elif not sim.ground:
            name = "jump" if sim.vy < 0 else "fall"
        elif abs(sim.vx) > 0.6:
            name = "run%d" % (int(fx.run_phase) % 4 if fx else 0)
        else:
            name = "blink" if (t % 3.7) < 0.12 else "idle"
        img = sprite(art, name, flip)
        sq = fx.squash if fx else 0.0
        sx, sy = 1.0 - sq * 0.5, 1.0 + sq
        bob = 0
        if name in ("run1", "run3"):
            bob = -1
        cx = sim.x * T - ox
        if name == "slide":
            cx += sim.wall * (T * HW - len(img[0]) / 2 + 0.5)
        by = sim.y * T - oy + bob + (1 if name == "glide" and T < 6 else 0)
        blit_scaled(px, W, H, img, cx, by, sx, sy)


def fx_near(sim, x, y, r=2.2):
    return abs(sim.x - x) < r and abs(sim.y - 0.6 - y) < r


def draw_beetle(px, W, H, cx, by, w, h, d, cols, frame):
    main, hi, dark = cols
    rx, ry = w / 2, h
    for yy in range(int(by - ry), int(by)):
        for xx in range(int(cx - rx), int(cx + rx) + 1):
            dx, dy = (xx + 0.5 - cx) / rx, (yy + 0.5 - by) / ry
            if dx * dx + dy * dy <= 1.0 and yy < by - 1:
                c = main
                if dy < -0.55 and dx * d < 0.1:
                    c = hi
                elif dx * dx + dy * dy > 0.7:
                    c = dark
                if abs(dx) < 0.08 and dy < -0.3:
                    c = dark                      # the split between the wing cases
                pset(px, W, H, xx, yy, c)
    hx = cx + d * rx * 0.85
    disc(px, W, H, hx, by - max(1.5, ry * 0.45), max(1.0, ry * 0.32), (30, 24, 34))
    pset(px, W, H, hx + d * max(1, ry * 0.2), by - max(2, ry * 0.55), (250, 250, 210))
    for k in range(3):                            # legs, scuttling
        lx = cx - rx * 0.6 + k * rx * 0.6 + (1 if (frame + k) % 2 else 0)
        pset(px, W, H, lx, by - 1, (30, 24, 34))


def draw_bat(px, W, H, cx, cy, T, swoop, cols, t):
    body, wing = cols
    eye = (255, 206, 90)
    if swoop <= 0:                                # hanging upside down, wings wrapped round
        rx, ry = max(1.2, T * 0.24), max(1.6, T * 0.36)
        for yy in range(int(cy - ry), int(cy + ry) + 1):
            for xx in range(int(cx - rx) - 1, int(cx + rx) + 2):
                dx, dy = (xx + 0.5 - cx) / rx, (yy + 0.5 - cy) / ry
                if dx * dx + dy * dy <= 1:
                    pset(px, W, H, xx, yy, body if abs(dx) < 0.45 else wing)
        pset(px, W, H, cx, cy - ry - 1, wing)                       # the feet holding on
        pset(px, W, H, cx - rx * 0.6, cy + ry, body)                 # ears (upside down)
        pset(px, W, H, cx + rx * 0.6, cy + ry, body)
        pset(px, W, H, cx - 1, cy + ry * 0.45, eye)
        pset(px, W, H, cx + 1, cy + ry * 0.45, eye)
        return
    flap = math.sin(t * 20)
    r = max(1.0, T * 0.2)
    span = max(3, int(T * 0.95))
    for side in (-1, 1):
        for k in range(span):
            u = (k + 1) / span
            top = cy - r * 0.6 - flap * u * T * 0.5
            th = (1 - u) * T * 0.42 + 1.2
            fingers = (k + 1) % max(2, span // 3) == 0
            for j in range(int(th) + (0 if fingers else 1)):
                pset(px, W, H, cx + side * (r + k), top + j, mix(wing, body, 0.5) if j == 0 else wing)
    disc(px, W, H, cx, cy, r, body)
    pset(px, W, H, cx - r * 0.7, cy - r - 0.5, body)                 # ears
    pset(px, W, H, cx + r * 0.7, cy - r - 0.5, body)
    pset(px, W, H, cx - 1, cy - r * 0.2, eye)
    pset(px, W, H, cx + 1, cy - r * 0.2, eye)


def draw_plant(px, W, H, cx, by, T, d, mouth, cols, t):
    head, head_hi = cols
    sway = math.sin(t * 2) * T * 0.05
    hx, hy = cx + sway + d * T * 0.04, by - T * 0.62
    stem = (54, 130, 58)
    for k in range(int(T * 0.45) + 1):            # the stem, gently swaying
        u = k / max(1, T * 0.45)
        x = cx + sway * u
        pset(px, W, H, x, by - 1 - k, stem)
        if T >= 7:
            pset(px, W, H, x + 1, by - 1 - k, shade(stem, 0.8))
    for side in (-1, 1):                          # two leaves at the foot
        ln = max(2, int(T * 0.42))
        for k in range(ln):
            yy = by - 1 - int(k * 0.55)
            pset(px, W, H, cx + side * (k + 1), yy, (100, 186, 80) if k < ln - 1 else (150, 220, 110))
            if T >= 6 and k < ln - 1:
                pset(px, W, H, cx + side * (k + 1), yy - 1, (80, 160, 70))
    rx, ry = max(1.6, T * 0.42), max(1.4, T * 0.34)
    for yy in range(int(hy - ry) - 1, int(hy + ry) + 2):
        for xx in range(int(hx - rx) - 1, int(hx + rx) + 2):
            dx, dy = (xx + 0.5 - hx) / rx, (yy + 0.5 - hy) / ry
            d2 = dx * dx + dy * dy
            if d2 > 1:
                continue
            open_ = dx * d > 0.05 and abs(dy) < (0.12 + 0.6 * mouth) * (dx * d) + 0.05
            if open_:
                c = (70, 14, 34) if d2 < 0.75 else (255, 190, 210)
            else:
                c = head_hi if dy < -0.35 and dx * d < 0.2 else head
                if d2 > 0.8:
                    c = shade(head, 0.72)
                elif (xx * 3 + yy * 5) % 7 == 0 and dy > -0.3:
                    c = mix(head, (255, 255, 255), 0.3)      # spots
            pset(px, W, H, xx, yy, c)
    pset(px, W, H, hx - d * rx * 0.25, hy - ry * 0.45, (255, 255, 236))
    pset(px, W, H, hx - d * rx * 0.25, hy - ry * 0.45 + 1, (30, 20, 30))


def draw_boss(px, W, H, cx, by, T, st, tm, face, kind, t):
    w, h = BOSS_W * T, BOSS_H * T
    if kind == 0:
        main, hi, dark, eye = (90, 170, 220), (190, 245, 255), (40, 70, 120), (255, 120, 220)
    else:
        main, hi, dark, eye = (150, 44, 40), (240, 140, 90), (70, 20, 24), (255, 240, 120)
    shake = (1 if int(t * 30) % 2 else -1) if st == WINDUP else 0
    flash = st == HURT and int(t * 16) % 2
    cx += shake
    rx, ry = w / 2, h
    for yy in range(int(by - ry), int(by)):
        for xx in range(int(cx - rx), int(cx + rx) + 1):
            dx, dy = (xx + 0.5 - cx) / rx, (yy + 0.5 - by) / ry
            if dx * dx + dy * dy <= 1.0:
                c = main
                if dy < -0.6 and dx * face < 0.2:
                    c = hi
                elif dx * dx + dy * dy > 0.78:
                    c = dark
                elif kind == 0 and (int((dx + 1) * 5) + int(dy * 4)) % 3 == 0:
                    c = mix(main, hi, 0.45)        # crystal facets
                elif kind == 1 and abs(dx * 3 + dy * 2 + 0.5) < 0.12:
                    c = (255, 230, 90)             # a lightning stripe
                if flash:
                    c = mix(c, (255, 255, 255), 0.7)
                pset(px, W, H, xx, yy, c)
    if kind == 0:                                 # crystal spikes on the back
        for k in (-0.4, 0.0, 0.4):
            sx = cx + k * rx
            for j in range(int(T * 0.5)):
                for q in range(-max(0, int((T * 0.5 - j) * 0.3)), max(0, int((T * 0.5 - j) * 0.3)) + 1):
                    pset(px, W, H, sx + q, by - ry - j, hi if q <= 0 else main)
    hx = cx + face * rx * 0.9                     # head with a horn
    disc(px, W, H, hx, by - ry * 0.4, max(1.5, T * 0.38), dark)
    for j in range(int(T * 0.6)):
        pset(px, W, H, hx + face * (T * 0.3 + j * 0.6), by - ry * 0.55 - j, hi)
    ec = eye if st in (WINDUP, CHARGE) else (240, 240, 240)
    pset(px, W, H, hx + face * T * 0.12, by - ry * 0.5, ec)
    if T >= 6:
        pset(px, W, H, hx + face * T * 0.12 + 1, by - ry * 0.5, ec)
    for k in range(4):                            # legs
        lx = cx - rx * 0.7 + k * rx * 0.46 + ((int(t * 12) + k) % 2 if st == CHARGE else 0)
        pset(px, W, H, lx, by - 1, (20, 16, 20))
        pset(px, W, H, lx, by - 2, (20, 16, 20))
    if st == STUN:                                # dizzy stars
        for k in range(3):
            a = t * 5 + k * 2.094
            sx, sy = cx + math.cos(a) * rx * 0.7, by - ry - T * 0.4 + math.sin(a) * T * 0.25
            pset(px, W, H, sx, sy, (255, 250, 150))
            pset(px, W, H, sx + 1, sy, (255, 220, 90))


def draw_chase(px, W, H, ex, T, biome, t):
    """The thing that chases you: a wall of brambles (forest) or a storm front (sky)."""
    ex = int(ex)
    if ex < -T * 2:
        return
    for y in range(H):
        edge = ex + int(math.sin(y * 0.35 + t * 5) * T * 0.35 + math.sin(y * 0.9 + t * 2) * T * 0.2)
        row = px[y]
        for x in range(0, min(W, edge + 1)):
            depth = edge - x
            if biome == 2:
                c = mix((40, 44, 70), (90, 96, 130), max(0.0, 1 - depth / (T * 2.5)))
                if depth < 2:
                    c = (150, 156, 190)
            else:
                c = mix((34, 52, 30), (78, 104, 52), max(0.0, 1 - depth / (T * 2.0)))
                if (x * 7 + y * 3) % 11 == 0 and depth < T * 2:
                    c = (150, 60, 60)
            row[x] = c
        if biome != 2 and y % 3 == 0:            # thorns sticking out
            for k in range(max(1, T // 3)):
                pset(px, W, H, edge + 1 + k, y - k // 2, (200, 170, 150) if k == T // 3 - 1 else (90, 70, 50))
    if biome == 2 and int(t * 3) % 7 == 0:        # lightning inside the front
        x, y = ex - T, 0
        while y < H:
            pset(px, W, H, x, y, (255, 255, 230))
            y += 1
            x += random.Random(int(t * 3) * 31 + y).choice((-1, 0, 1))


# =============================================================================================
# Effects (only for the eyes and ears: particles, squash, shake, lightning, sounds) and the camera
# =============================================================================================
class Fx:
    def __init__(self, lv, sound=True):
        self.lv = lv
        self.sound = sound
        self.parts = []
        self.squash = 0.0
        self.shake = 0.0
        self.blink = 0.0
        self.run_phase = 0.0
        self.dust_t = 0.0
        self.spring_squash = {}
        self.chain, self.chain_t = 0, 9.0
        self.flash = 0.0
        self.next_bolt = 4.0
        self.thunder_at = None
        self.rnd = random.Random(lv.n * 7 + 1)
        self.t = 0.0

    def play(self, name, vol=1.0):
        if self.sound:
            SND.play(name, vol)

    def burst(self, x, y, n, cols, speed=3.0, life=0.5, kind="spark", up=0.0, grav=0.0):
        r = self.rnd
        for _ in range(n):
            a = r.uniform(0, 6.283)
            s = r.uniform(0.3, 1.0) * speed
            self.parts.append([x, y, math.cos(a) * s, math.sin(a) * s - up, life * r.uniform(0.6, 1.0), life,
                               r.choice(cols), kind, grav])

    def dust(self, x, y, n, spread=1.0, up=1.2):
        p = PAL[self.lv.biome]
        cols = [mix(p["top_lo"], (230, 220, 200), 0.6), (220, 214, 200), (190, 180, 170)]
        if self.lv.biome == 1:
            cols = [(170, 160, 220), (130, 120, 190)]
        r = self.rnd
        for _ in range(n):
            self.parts.append([x + r.uniform(-0.3, 0.3), y - 0.05, r.uniform(-2, 2) * spread, -r.uniform(0.2, 1) * up,
                               r.uniform(0.25, 0.45), 0.45, r.choice(cols), "dust", 2.0])

    def events(self, sim, evs):
        for e in evs:
            k = e[0]
            if k == "jump":
                self.squash = 0.28
                self.dust(sim.x, sim.y, 3, 0.6)
                self.play("jump", 0.8)
            elif k == "walljump":
                self.squash = 0.22
                self.dust(sim.x + e[1] * HW, sim.y - 0.6, 5, 0.7)
                self.play("walljump", 0.8)
            elif k == "glide":
                self.play("glide", 0.7)
            elif k == "land":
                v = e[1]
                self.squash = -min(0.4, 0.08 + v / 60)
                self.dust(sim.x, sim.y, 3 + int(v / 4), 1.0 + v / 20)
                if v > 6:
                    self.play("land", min(1.0, v / 18))
            elif k == "mote":
                mx, my = self.lv.motes[e[1]]
                self.burst(mx, my, 6, [(255, 250, 210), (255, 220, 120)], 2.5, 0.35)
                self.chain = self.chain + 1 if self.chain_t < 0.55 else 0
                self.chain_t = 0.0
                self.play("mote%d" % min(7, self.chain), 0.9)
            elif k == "life":
                self.burst(sim.x, sim.y - 0.6, 12, [(255, 120, 140), (255, 200, 210)], 3, 0.7)
            elif k == "seed":
                sx, sy = self.lv.seeds[e[1]]
                self.burst(sx, sy, 22, [(255, 240, 160), (255, 200, 80), (255, 255, 255)], 4.5, 0.8)
                self.play("seed")
            elif k == "cp":
                lx, ly = self.lv.lanterns[e[1]]
                self.burst(lx, ly - 1.4, 16, [(255, 220, 130), (255, 180, 80)], 3.5, 0.7, up=1.0)
                self.play("checkpoint")
            elif k == "spring":
                self.spring_squash[(e[1], e[2])] = 1.0
                self.squash = 0.35
                self.dust(e[1] + 0.5, e[2] + 0.5, 6, 1.2)
                self.play("spring")
            elif k == "stomp":
                self.squash = 0.25
                self.burst(e[3], e[4] - 0.4, 12, [(255, 255, 255), (220, 220, 230), PAL[self.lv.biome]["beetle"][1]], 4, 0.45)
                self.shake = max(self.shake, 0.15)
                self.play("stomp")
            elif k == "hurt":
                self.burst(sim.x, sim.y - 0.6, 18, [(130, 216, 70), (64, 150, 52), (252, 238, 204), (244, 122, 54)],
                           5, 0.9, kind="leaf", up=2.0, grav=6.0)
                self.shake = max(self.shake, 0.35)
                self.play("hurt")
            elif k == "crumble":
                self.play("crumble", 0.6)
            elif k == "boss":
                self.shake = 0.4
                self.play("boss")
            elif k == "bump":
                self.shake = 0.6
                self.dust(e[1], self.lv.boss_at[1], 10, 2.0, 2.0)
                self.play("bump")
            elif k == "bosshit":
                self.burst(e[1], e[2] - 1, 20, [(255, 255, 255), (255, 230, 120)], 5, 0.6)
                self.shake = 0.5
                self.play("bosshit")
            elif k == "bossdead":
                self.burst(e[1], e[2] - 1, 50, [(255, 255, 255), (255, 230, 120), (180, 255, 180)], 7, 1.2)
                self.shake = 0.9
                self.play("gate")
            elif k == "chase":
                self.shake = 0.3
                self.play("boss", 0.7)
            elif k == "drop":
                self.dust(sim.x, sim.y + 0.1, 3, 0.5, 0.3)

    def update(self, sim, dt, real=True):
        self.t += dt
        self.chain_t += dt
        self.squash *= max(0.0, 1 - dt * 9)
        self.shake = max(0.0, self.shake - dt * 1.6)
        self.blink = max(0.0, self.blink - dt)
        for k in list(self.spring_squash):
            self.spring_squash[k] -= dt * 4
            if self.spring_squash[k] <= 0:
                del self.spring_squash[k]
        if sim is not None and not sim.dead:
            if sim.ground and abs(sim.vx) > 0.6:
                self.run_phase += dt * (6 + abs(sim.vx) * 1.4)
                self.dust_t += dt
                if abs(sim.vx) > 5.5 and self.dust_t > 0.16:
                    self.dust_t = 0.0
                    self.dust(sim.x - sim.facing * 0.2, sim.y, 1, 0.5, 0.6)
            if sim.sliding and self.rnd.random() < dt * 14:
                self.dust(sim.x + sim.wall * HW, sim.y - 0.8, 1, 0.3, -0.5)
            if sim.glide and not sim.ground and self.rnd.random() < dt * 6:
                self.parts.append([sim.x + self.rnd.uniform(-0.5, 0.5), sim.y - 1.3, self.rnd.uniform(-1, 1), 0.4, 0.5, 0.5,
                                   (200, 248, 132), "spark", 0.0])
        keep = []
        for p in self.parts:
            p[4] -= dt
            if p[4] <= 0:
                continue
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += p[8] * dt
            if p[7] == "dust":
                p[2] *= max(0.0, 1 - dt * 4)
            elif p[7] == "leaf":
                p[2] += math.sin(self.t * 6 + p[1]) * dt * 4
                p[3] = min(p[3], 2.5)
            keep.append(p)
        self.parts = keep[-400:]
        # lightning over the autumn storm
        if self.lv.biome == 3:
            self.flash = max(0.0, self.flash - dt * 3.5)
            self.next_bolt -= dt
            if self.next_bolt <= 0:
                self.flash = 1.0
                self.next_bolt = self.rnd.uniform(5.0, 11.0)
                self.thunder_at = self.t + self.rnd.uniform(0.3, 1.2)
                if self.rnd.random() < 0.5:
                    self.next_bolt = 0.18             # a double flash
            if self.thunder_at is not None and self.t >= self.thunder_at:
                self.thunder_at = None
                if real:
                    self.play("thunder", 0.8)

    def paint(self, cv, ox, oy, T):
        px, W, H = cv.px, cv.W, cv.H
        for p in self.parts:
            a = p[4] / p[5]
            x, y = p[0] * T - ox, p[1] * T - oy
            c = p[6]
            if p[7] == "dust":
                pset(px, W, H, x, y, mix(px[int(y)][int(x)] if 0 <= int(x) < W and 0 <= int(y) < H else c, c, a))
                if T >= 7 and a > 0.5:
                    pset(px, W, H, x + 1, y, mix(px[int(y)][min(W - 1, int(x) + 1)] if 0 <= int(y) < H else c, c, a * 0.6))
            else:
                pset(px, W, H, x, y, c)
                if p[7] == "leaf" and T >= 6:
                    pset(px, W, H, x + 1, y, shade(c, 0.8))


class Camera:
    """Follows Leafling with a look-ahead in the running direction and a vertical dead zone."""

    def __init__(self):
        self.x = self.y = None
        self.look = 0.0
        self.ty = 0.0

    def update(self, sim, vw, vh, dt, snap=False):
        lv = sim.lv
        look = sim.facing * 2.0 + sim.vx * 0.22
        self.look = look if snap else self.look + (look - self.look) * min(1.0, dt * 2.5)
        tx = sim.x + self.look - vw / 2
        py = sim.y - 0.6
        if self.x is None or snap:
            self.ty = py - vh * 0.6
        lo, hi = self.ty + vh * 0.3, self.ty + vh * 0.7
        if py < lo:
            self.ty = py - vh * 0.3
        elif py > hi:
            self.ty = py - vh * 0.7
        if sim.ground:                                    # settle so the ground sits in the lower part
            self.ty += (py - vh * 0.62 - self.ty) * min(1.0, dt * 2.0)
        top = 0.0 if lv.biome == 1 else -3.0
        if lv.W <= vw:
            tx = (lv.W - vw) / 2
        else:
            tx = clamp(tx, 0.0, lv.W - vw)
        self.ty = clamp(self.ty, min(top, lv.H - vh), lv.H - vh) if lv.H > vh else lv.H - vh
        if self.x is None or snap:
            self.x, self.y = tx, self.ty
        else:
            self.x += (tx - self.x) * min(1.0, dt * 5.0)
            self.y += (self.ty - self.y) * min(1.0, dt * 6.0)


def tile_size(W, H):
    """Pixels per tile for a canvas of W x H pixels: 4 at 70x22, more on big windows."""
    return int(clamp(min(H / 11.5, W / 17.0), 4, 8))


def weather(cv, lv, sim, fx, ox, oy, T, t):
    """Rain, wind streaks, falling leaves and glowing dust - in front of everything."""
    px, W, H = cv.px, cv.W, cv.H
    b = lv.biome
    if b == 3:
        n = W * H // 170
        c = (150, 166, 210) if fx.flash < 0.3 else (235, 235, 255)
        for i in range(n):
            sp = 1.3 + (i % 5) * 0.12
            x = int((i * 37.17 + t * W * 0.3 * sp - ox * 0.3) % (W + 20) - 10)
            y = int((i * 91.3 + t * H * 1.7 * sp) % (H + 8) - 4)
            for k, a in ((0, 0.42), (1, 0.28), (2, 0.14)):
                xx, yy = x - k // 2, y - k
                if 0 <= xx < W and 0 <= yy < H:
                    px[yy][xx] = mix(px[yy][xx], c, a)
        for i in range(6):                                # falling leaves
            x = (i * 53.7 + t * 9 * (1 + i % 3) - ox * 0.6) % (W + 10) - 5
            y = (i * 31.1 + t * 7 * (1 + i % 2)) % (H + 6) - 3 + math.sin(t * 2 + i) * 2
            pset(px, W, H, x, y, (220, 110, 40) if i % 2 else (190, 70, 40))
    elif b == 0:
        for i in range(5):
            x = (i * 61.3 + t * 5 * (1 + i % 3) - ox * 0.5) % (W + 10) - 5
            y = (i * 27.9 + t * 4 * (1 + i % 2)) % (H + 6) - 3 + math.sin(t * 1.5 + i) * 2
            pset(px, W, H, x, y, (150, 214, 80) if i % 2 else (210, 200, 90))
    elif b == 1:
        for i in range(W * H // 900 + 3):
            x = (i * 47.3 - ox * 0.7 + math.sin(t * 0.7 + i) * 3) % W
            y = (i * 23.9 - t * 2 * (1 + i % 3)) % H
            add_glow(px, W, H, x, y, 1.6, (120, 220, 255) if i % 2 else (220, 150, 255), 0.5 * (0.5 + 0.5 * math.sin(t * 3 + i)))
    elif b == 2 and lv.wind:
        g = gust(sim.f if sim else int(t * 60))
        n = int(W * H / 300 * (0.25 + g))
        d = 1 if lv.wind > 0 else -1
        for i in range(n):
            ln = 3 + int(g * 6) + i % 4
            x = (i * 71.3 + d * t * W * (0.6 + g)) % (W + ln * 2) - ln
            y = (i * 37.7) % H + math.sin(t * 2 + i) * 1.5
            for k in range(ln):
                xx = int(x - d * k)
                if 0 <= xx < W and 0 <= int(y) < H:
                    px[int(y)][xx] = mix(px[int(y)][xx], (255, 255, 255), 0.35 * (1 - k / ln))


def render(sim, fx, cam, cols, rows, t, hud=True, painter=None, extra=None):
    """One frame of a level as a Canvas (with the HUD unless hud=False)."""
    lv = sim.lv
    cv = Canvas(cols, rows)
    W, H = cv.W, cv.H
    T = tile_size(W, H)
    vw, vh = W / T, H / T
    if cam.x is None:
        cam.update(sim, vw, vh, 0, snap=True)
    sx = sy = 0
    if fx.shake > 0:
        r = random.Random(int(t * 60))
        sx, sy = r.uniform(-1, 1) * fx.shake * T * 0.5, r.uniform(-1, 1) * fx.shake * T * 0.5
    ox, oy = int(round(cam.x * T + sx)), int(round(cam.y * T + sy))
    flash = lv.biome == 3 and fx.flash > 0.45
    backdrop(lv.biome, W, H).paint(cv, cam.x, cam.y, T, lv.H, flash)
    painter = painter or Painter(lv)
    near = set()
    for ty in range(int(sim.y - 2.5), int(sim.y + 1.5)):
        for tx in range(int(sim.x - 2.5), int(sim.x + 2.5)):
            if 0 <= ty < lv.H and 0 <= tx < lv.W and lv.code[ty][tx] == HID:
                near.add((tx, ty))
    if near:                                              # reveal the whole hidden pocket we stand in
        todo = list(near)
        while todo:
            x, y = todo.pop()
            for q in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if q not in near and 0 <= q[1] < lv.H and 0 <= q[0] < lv.W and lv.code[q[1]][q[0]] == HID:
                    near.add(q)
                    todo.append(q)
    painter.paint_tiles(cv, sim, ox, oy, T, t, near)
    painter.paint_things(cv, sim, fx, ox, oy, T, t)
    painter.paint_hero(cv, sim, fx, ox, oy, T, t)
    fx.paint(cv, ox, oy, T)
    weather(cv, lv, sim, fx, ox, oy, T, t)
    if lv.biome == 3 and fx.flash > 0.05 and not flash:
        k = fx.flash * 0.25
        for y in range(H):
            cv.px[y] = [mix(c, (220, 220, 255), k) for c in cv.px[y]]
    if hud:
        draw_hud(cv, sim, t, extra or {})
    return cv


HUD_BG, HUD_FG, HUD_DIM, HUD_GOLD = (14, 16, 26), (236, 236, 244), (140, 146, 176), (255, 214, 110)


def fmt_time(frames_or_s, frames=True):
    s = frames_or_s / 60 if frames else frames_or_s
    return "%d:%05.2f" % (int(s // 60), s % 60)


def draw_hud(cv, sim, t, extra):
    lv = sim.lv
    cols = cv.cols
    cv.put(0, 0, " " * cols, HUD_FG, HUD_BG)
    x = 1
    parts = [("•", HUD_GOLD), (" %d/%d" % (sim.mote_count, len(lv.motes)), HUD_FG), ("   ", HUD_FG)]
    parts += [("◆" if sim.seeds >> i & 1 else "◇", HUD_GOLD if sim.seeds >> i & 1 else HUD_DIM) for i in range(len(lv.seeds))]
    parts += [("   ", HUD_FG), ("♥", (255, 110, 130)), (" %d" % sim.lives, HUD_FG)]
    parts += [("   ", HUD_FG), (fmt_time(extra.get("frames", sim.f)), HUD_FG)]
    for s, c in parts:
        cv.put(x, 0, s, c, HUD_BG)
        x += len(s)
    name = "%s %s" % (lv.meta.get("id", ""), lv.meta.get("name", ""))
    if lv.boss and sim.boss and not sim.boss_done:
        name = "boss " + "■" * sim.boss[4] + "□" * (lv.boss["hp"] - sim.boss[4])
    if x + len(name) + 2 < cols:
        cv.put(cols - len(name) - 1, 0, name, HUD_DIM if not name.startswith("boss") else (255, 160, 120), HUD_BG)
    hint = extra.get("hint")
    if hint:
        a = extra.get("hint_a", 1.0)
        cv.center(cv.rows - 1, " %s " % hint, mix(HUD_BG, (250, 246, 220), a), mix(cv.px[-1][cols // 2], HUD_BG, a * 0.85))
    msg = extra.get("msg")
    if msg:
        cv.center(cv.rows // 2 - 2, " %s " % msg, (20, 18, 24), (255, 214, 110))


# =============================================================================================
# Screens: help, pause, title demo, world map, level clear, the play loop
# =============================================================================================
def help_lines(kitty):
    mode = (["Your terminal reports key releases: hold jump longer to jump",
             "higher, hold it again in the air to glide."] if kitty else
            ["Classic keys: a tap runs a little, holding runs on, the other",
             "direction turns at once. Jumps are full; jump again in the",
             "air switches the glide on and off (landing ends it)."])
    return ["LEAFLING - keys", "",
            "Left / Right  (A / D)     run",
            "Space / Up / W / Z        jump - again in the air: glide",
            "Down  (S)                 drop through thin platforms, stop",
            "R                         back to the last lantern",
            "Esc / P                   pause menu (Q there: quit)",
            "M  (in the pause menu)    sound on / off",
            "?                         this help", ""] + mode + [
            "",
            "Slide down mossy walls and jump off them to climb.",
            "Stomp beetles, bats and plants from above; dodge the seeds",
            "plants spit. Lanterns keep your place. Three seeds hide in",
            "every level. Every 50 motes give an extra leaf (life)."]


PAUSE = ["P A U S E D", "", "Esc / P / Enter   continue", "?                 help", "M                 sound on / off",
         "Q                 quit to the world map"]


def progress():
    sc = load_scores().get(GAME, {})
    done = ["%s time" % m["id"] in sc for m in LEVELS]
    best = [sc.get("%s time" % m["id"]) for m in LEVELS]
    seeds = [sc.get("%s seeds" % m["id"], 0) for m in LEVELS]
    unlocked = [i == 0 or done[i] or done[i - 1] for i in range(len(LEVELS))]
    return done, best, seeds, unlocked


def popcount(v):
    return bin(v).count("1")


def demo_input(s):
    """The title demo's autopilot: run right, jump gaps and steps, glide over water."""
    lv = s.lv

    def stand(x, y):
        x, y = int(x), int(y)
        return 0 <= y < lv.H and 0 <= x < lv.W and lv.code[y][x] in (SOL, MOSS, CRUM, ONE)

    if s.ground:
        gap = not stand(s.x + 1.1, s.y) or not stand(s.x + 1.8, s.y)
        wall = stand(s.x + 1.0, s.y - 0.5)
        return (1, gap or wall, gap or wall, False)
    below = any(stand(s.x, s.y + k) for k in range(0, 3))
    if s.vy > 0 and not below:
        return (1, not s.glide, True, False)
    return (1, False, s.vy < 0 or s.glide, False)


class TitleDemo:
    """Leafling running through the four worlds behind the title screen (and in the launcher preview)."""

    def __init__(self, biome=0):
        self.k = biome
        self.new_run()

    def new_run(self):
        b = self.k % 4
        self.k += 1
        self.lv = Level(-1, dict(id="", name="", biome=b, map=DEMO_MAP, wind=0.0))
        self.sim = Sim(self.lv)
        self.fx = Fx(self.lv, sound=False)
        self.cam = Camera()
        self.painter = Painter(self.lv)
        self.t = 0.0
        self.acc = 0.0

    def scene(self, cols, rows, dt):
        self.t += dt
        self.acc += dt
        s = self.sim
        n = 0
        while self.acc >= DT and n < 8:
            ev = s.step(demo_input(s))
            self.fx.events(s, ev)
            self.acc -= DT
            n += 1
        self.fx.update(s, dt, real=False)
        T = tile_size(cols, rows * 2)
        self.cam.update(s, cols / T, rows * 2 / T, dt)
        cv = render(s, self.fx, self.cam, cols, rows, self.t, hud=False, painter=self.painter)
        if s.x > self.lv.W - 6 or s.dead or self.t > 40:
            self.new_run()
        return cv

    def frame(self, cols, rows, dt, sel, help_, kitty):
        cv = self.scene(cols, rows, dt)
        done, best, seeds, unlocked = progress()
        nxt = next((i for i in range(len(LEVELS)) if unlocked[i] and not done[i]), len(LEVELS) - 1)
        m = LEVELS[nxt]
        items = ["%s   %s %s" % ("Play    " if not any(done) else "Continue", m["id"], m["name"]), "World map"]
        total = sum(popcount(v) for v in seeds)
        line = None
        if any(done):
            line = "%d of %d levels done   %d of %d seeds found" % (sum(done), len(LEVELS), total, len(LEVELS) * 3)
        extra = ["", "Four worlds, twelve levels. Glide, wall-jump,",
                 "find the hidden seeds. Levels unlock as you go.",
                 "Keys: %s" % ("with releases (kitty protocol)" if kitty else "classic terminal mode")]
        title_screen(cv, "LEAFLING", "a tiny leaf on a long journey", items, sel, line, extra=extra,
                     keys="Up/Down choose   Enter start   ? help   Esc quit", help_lines=help_lines(kitty),
                     show_help=help_, dim=0.35)
        return cv, nxt


_MAP_BG = {}


def draw_map(cols, rows, sel, t, kitty, show_help=False):
    """The world map: four worlds side by side, the levels as stepping stones."""
    cv = Canvas(cols, rows)
    W, H = cv.W, cv.H
    pw = W // 4
    for b in range(4):
        k = (b, pw, H)
        if k not in _MAP_BG:
            sub = Canvas(pw, rows)
            backdrop(b, pw, H).paint(sub, 6.0 * b, 4, 4, 18)
            _MAP_BG[k] = [[mix(c, (8, 8, 16), 0.25) for c in row] for row in sub.px]
        for y in range(H):
            cv.px[y][b * pw:(b + 1) * pw] = _MAP_BG[k][y]
    for y in range(H):
        cv.px[y][4 * pw:] = [(8, 8, 16)] * (W - 4 * pw)
    for b in range(1, 4):
        for y in range(H):
            cv.px[y][b * pw] = (10, 10, 18)
    done, best, seeds, unlocked = progress()
    pts = []
    for i in range(len(LEVELS)):
        b, k = LEVELS[i]["biome"], i % 3
        x = int(b * pw + (k + 0.5) * pw / 3)
        y = int(H * 0.52 + math.sin(i * 1.7 + 0.5) * H * 0.1)
        pts.append((x, y))
    for i in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        c = (255, 214, 110) if unlocked[i + 1] else (90, 90, 110)
        steps = max(abs(x1 - x0), abs(y1 - y0))
        for s in range(steps):
            if s % 3 == 2:
                continue
            x, y = x0 + (x1 - x0) * s / steps, y0 + (y1 - y0) * s / steps
            pset(cv.px, W, H, x, y, c)
            pset(cv.px, W, H, x, y + 1, shade(c, 0.6))
    r = max(2.2, H / 25)
    for i, (x, y) in enumerate(pts):
        if done[i]:
            ring, core = (255, 214, 110), (110, 200, 90)
        elif unlocked[i]:
            ring, core = (240, 240, 250), (60, 70, 100)
        else:
            ring, core = (70, 70, 86), (30, 30, 40)
        if i == sel:
            add_glow(cv.px, W, H, x + 0.5, y + 0.5, r * 2.6, (255, 230, 150), 0.5)
        disc(cv.px, W, H, x + 0.5, y + 0.5, r, ring)
        disc(cv.px, W, H, x + 0.5, y + 0.5, r - 1.2, core)
    x, y = pts[sel]
    art = HERO_L if H >= 70 else HERO_S
    blit_scaled(cv.px, W, H, sprite(art, "idle", False), x + 0.5, y - r - 1 + math.sin(t * 4) * 1.2)
    for b in range(4):
        name = BIOMES[b]
        cv.put(b * pw // 1 + max(0, (pw - len(name)) // 2), 1, name[:pw], (240, 240, 248), None)
    for i, (x, y) in enumerate(pts):
        lab = LEVELS[i]["id"]
        cv.put(x - 1, min(rows - 4, int((y + r) // 2) + 1), lab, (240, 240, 248) if unlocked[i] else (120, 120, 140), None)
        if done[i]:
            ss = "".join("◆" if seeds[i] >> k & 1 else "◇" for k in range(3))
            cv.put(x - 1, min(rows - 3, int((y + r) // 2) + 2), ss, (255, 214, 110), None)
    m = LEVELS[sel]
    info = "%s  %s  -  %s" % (m["id"], m["name"], BIOMES[m["biome"]])
    if not unlocked[sel]:
        info += "   (locked)"
    elif best[sel] is not None:
        info += "   best %s   seeds %d/3" % (fmt_time(best[sel], frames=False), popcount(seeds[sel]))
    cv.put(0, rows - 2, " " * cols, HUD_FG, HUD_BG)
    cv.center(rows - 2, info[:cols], HUD_FG, HUD_BG)
    arcadekit.footer(cv, "arrows choose   Enter play   ? help   Esc back")
    if show_help:
        overlay(cv, help_lines(kitty))
    return cv


def clear_lines(lv, sim, record, seeds_before, last_of_biome, last_level):
    secs = sim.f / 60
    lines = ["B I O M E   C L E A R" if last_of_biome else "L E V E L   C L E A R", ""]
    lines.append("%s %s" % (lv.meta["id"], lv.meta["name"]))
    lines.append("time    %s%s" % (fmt_time(secs, frames=False), "   new best!" if record else ""))
    lines.append("motes   %d / %d" % (sim.mote_count, len(lv.motes)))
    got = sim.seeds | seeds_before
    lines.append("seeds   " + " ".join("◆" if got >> i & 1 else "◇" for i in range(len(lv.seeds))) +
                 ("   (%d new)" % popcount(sim.seeds & ~seeds_before) if sim.seeds & ~seeds_before else ""))
    if last_level:
        lines += ["", "The storm has passed. Leafling is home.", "Thank you for playing!"]
    elif last_of_biome:
        lines += ["", "A new world opens: %s." % BIOMES[lv.biome + 1]]
    lines += ["", "Enter: %s   Esc: world map" % ("world map" if last_level else "next level")]
    return lines


def too_small(term):
    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (70x22).")


def play(term, ctl, n):
    """One level. Returns 'next', 'map' or 'quit'."""
    lv = Level(n)
    sim = Sim(lv, toggle_glide=not ctl.kitty)
    fx = Fx(lv)
    cam = Camera()
    painter = Painter(lv)
    ctl.reset()
    paused = help_ = False
    state, st_t = "play", 0.0
    acc = 0.0
    last = time.time()
    t = 0.0
    record = None
    sc = load_scores().get(GAME, {})
    seeds_before = sc.get("%s seeds" % lv.meta["id"], 0)
    last_of_biome = n == len(LEVELS) - 1 or LEVELS[n + 1]["biome"] != lv.biome
    banner = 2.2
    while True:
        now = time.time()
        dt = min(0.1, now - last)
        last = now
        for name, kind in term.events():
            if kind != "press":
                ctl.feed(name, kind, now)
                continue
            if state == "clear" and st_t > 0.7:
                if name in ("enter", " "):
                    SND.play("start")
                    return "next" if n < len(LEVELS) - 1 else "map"
                if name in ("esc", "q"):
                    return "map"
                continue
            a = shared_key(name, paused)
            if a == "pause":
                paused = True
                ctl.reset()
                SND.play("tick")
            elif a == "resume":
                paused = help_ = False
                ctl.reset()
                last = time.time()
            elif a == "quit":
                return "map"
            elif a == "help":
                help_ = not help_
                paused = True
                ctl.reset()
            elif a == "sound":
                if SND.toggle():
                    SND.play("tick")
            elif a is None:
                if name == "r" and kind == "press" and state == "play":
                    sim.respawn()
                    fx.blink = 1.0
                    cam.x = None
                    ctl.reset()
                else:
                    ctl.feed(name, kind, now)
        cols, rows = term.size()
        if cols < 70 or rows < 22:
            too_small(term)
            paused = paused or state == "play"
            time.sleep(0.2)
            last = time.time()
            continue
        T = tile_size(cols, rows * 2)
        if not paused:
            t += dt
            banner -= dt
            if state == "play":
                acc += dt
                steps = 0
                while acc >= DT and steps < 8:
                    ev = sim.step(ctl.sample(now))
                    fx.events(sim, ev)
                    acc -= DT
                    steps += 1
                    if sim.dead:
                        state, st_t = "dead", 0.0
                        SND.play("death", 0.8)
                        break
                    if sim.won:
                        state, st_t = "clear", 0.0
                        lid = lv.meta["id"]
                        record = submit(GAME, "%s time" % lid, round(sim.f / 60, 2), lower_is_better=True)
                        submit(GAME, "%s seeds" % lid, seeds_before | sim.seeds)
                        SND.play("biome" if last_of_biome else "clear")
                        fx.burst(sim.x, sim.y - 1, 40, [(220, 255, 200), (255, 240, 160), (140, 230, 120)], 6, 1.2)
                        break
                if steps >= 8:
                    acc = 0.0
            elif state == "dead":
                st_t += dt
                if st_t > 0.9:
                    sim.lives -= 1
                    sim.deaths += 1
                    if sim.lives <= 0:
                        state, st_t = "over", 0.0
                    else:
                        sim.respawn()
                        fx.blink = 1.2
                        cam.x = None
                        ctl.reset()
                        state = "play"
                        acc = 0.0
            elif state == "over":
                st_t += dt
                if st_t > 2.2:
                    sim = Sim(lv, toggle_glide=not ctl.kitty)
                    fx = Fx(lv)
                    cam.x = None
                    ctl.reset()
                    state, acc, banner = "play", 0.0, 2.0
            else:
                st_t += dt
            fx.update(sim, dt)
            cam.update(sim, cols / T, rows * 2 / T, dt)
        extra = {}
        hint = None
        for hx, text in lv.hints:
            if hx <= sim.x < hx + 14:
                hint = text
                extra["hint_a"] = clamp(min((sim.x - hx) * 1.5, (hx + 14 - sim.x) / 2), 0.0, 1.0)
        if hint and state == "play":
            extra["hint"] = hint
        if state == "over":
            extra["msg"] = "Out of leaves - the level starts again"
        elif banner > 0 and state == "play":
            extra["msg"] = "%s  %s" % (lv.meta["id"], lv.meta["name"])
        cv = render(sim, fx, cam, cols, rows, t, painter=painter, extra=extra)
        if paused:
            overlay(cv, help_lines(ctl.kitty) if help_ else PAUSE + ["", SND.label()])
        elif state == "clear" and st_t > 0.7:
            overlay(cv, clear_lines(lv, sim, record, seeds_before, last_of_biome, n == len(LEVELS) - 1))
        term.write(cv.emit())
        time.sleep(max(0.0, 1 / 40 - (time.time() - now)))


def world_map(term, ctl, sel):
    """Pick a level. Returns its number or None."""
    help_ = False
    t0 = time.time()
    while True:
        cols, rows = term.size()
        if cols < 70 or rows < 22:
            too_small(term)
            if any(k in ("q", "esc") for k, kind in term.events(0.3) if kind == "press"):
                return None
            continue
        done, best, seeds, unlocked = progress()
        now = time.time()
        term.write(draw_map(cols, rows, sel, now - t0, ctl.kitty, help_).emit())
        for k, kind in term.events(max(0.0, 1 / 30 - (time.time() - now))):
            if kind != "press":
                continue
            if help_:
                help_ = False
            elif k == "?":
                help_ = True
            elif k in ("esc", "q"):
                SND.play("tick")
                return None
            elif k in ("left", "a", "up", "w"):
                sel = (sel - 1) % len(LEVELS)
                SND.play("tick")
            elif k in ("right", "d", "down", "s", "tab"):
                sel = (sel + 1) % len(LEVELS)
                SND.play("tick")
            elif k in ("enter", " "):
                if unlocked[sel]:
                    SND.play("start")
                    return sel
                SND.play("hurt", 0.4)


def main():
    with Terminal() as term:
        ctl = Controls(term.kitty)
        demo = TitleDemo()
        sel, help_ = 0, False
        last = time.time()
        map_sel = None
        while True:
            now = time.time()
            cols, rows = term.size()
            if cols < 70 or rows < 22:
                too_small(term)
                if any(k in ("q", "esc") for k, kind in term.events(0.3) if kind == "press"):
                    return
                last = time.time()
                continue
            cv, nxt = demo.frame(cols, rows, min(0.1, now - last), sel, help_, ctl.kitty)
            last = now
            term.write(cv.emit())
            go = None
            for k, kind in term.events(max(0.0, 1 / 30 - (time.time() - now))):
                if kind != "press":
                    continue
                if help_:
                    help_ = False
                elif k == "?":
                    help_ = True
                elif k in ("q", "esc"):
                    return
                elif k in ("up", "w", "down", "s", "tab"):
                    sel = 1 - sel
                    SND.play("tick")
                elif k in ("enter", " "):
                    SND.play("start")
                    go = nxt if sel == 0 else "map"
            if go is None:
                continue
            if go == "map":
                go = world_map(term, ctl, nxt if map_sel is None else map_sel)
                if go is None:
                    last = time.time()
                    continue
            n = go
            while n is not None:
                map_sel = n
                res = play(term, ctl, n)
                if res == "next" and n + 1 < len(LEVELS):
                    n += 1
                elif res == "map":
                    n = world_map(term, ctl, min(len(LEVELS) - 1, n + (1 if progress()[0][n] else 0)))
                else:
                    n = None
            last = time.time()


# =============================================================================================
# Self-test and benchmark
# =============================================================================================
def _solve(args):
    n, budget = args
    r = solve_level(n, budget)
    r.pop("route", None)
    return r


def fallback_test():
    """Classic terminals send no releases: simulate key repeat and check the run is continuous."""
    lv = Level(-1, dict(id="t", name="test", biome=0, map=[" " * 80] * 8 + [" @" + " " * 78] + ["#" * 80] * 2))
    out = []
    for delay in (0.25, 0.5):
        ctl = Controls(False)
        sim = Sim(lv, toggle_glide=True)
        sim.place(2.5, 9.0)
        presses = [0.0] + [delay + k * 0.033 for k in range(int((1.4 - delay) / 0.033))]
        last_press = presses[-1]
        stopped_at, min_v, t, i = None, 99.0, 0.0, 0
        while t < 2.2:
            while i < len(presses) and presses[i] <= t:
                ctl.feed("right", "press", presses[i])
                i += 1
            sim.step(ctl.sample(t))
            if 0.2 <= t <= last_press:
                min_v = min(min_v, sim.vx)
            if t > last_press and stopped_at is None and abs(sim.vx) < 0.05:
                stopped_at = t
            t += DT
        assert min_v > RUN_MAX * 0.9, "classic keys: the run stalled during the repeat delay %.2f (vx %.2f)" % (delay, min_v)
        assert stopped_at is not None and stopped_at - last_press < 0.45, "classic keys: does not stop after release"
        out.append("repeat delay %.2fs: min speed %.1f, stops %.2fs after the last repeat" % (delay, min_v, stopped_at - last_press))
    # the other direction turns at once, Down stops
    ctl = Controls(False)
    ctl.feed("right", "press", 0.0)
    assert ctl.sample(0.01)[0] == 1
    ctl.feed("left", "press", 0.05)
    assert ctl.sample(0.06)[0] == -1, "classic keys: no instant turn"
    ctl.feed("down", "press", 0.1)
    assert ctl.sample(0.11)[0] == 0, "classic keys: Down does not stop"
    # a single tap runs a little (about the repeat window), not for ever
    ctl = Controls(False)
    ctl.feed("right", "press", 0.0)
    assert ctl.sample(0.3)[0] == 1 and ctl.sample(0.7)[0] == 0
    # jump is full, jump in the air toggles the glide, landing ends it, a held key's repeats do not toggle
    ctl = Controls(False)
    sim = Sim(lv, toggle_glide=True)
    sim.place(15.5, 9.0)
    t = 0.0
    ctl.feed(" ", "press", t)
    peak = sim.y
    glided = False
    for k in range(120):
        t = k * DT
        if k == 30:
            ctl.feed(" ", "press", t)               # second press, in the air: glide on
        if k in (31, 32, 33):
            ctl.feed(" ", "press", t + 0.002)       # key repeat: ignored
        sim.step(ctl.sample(t))
        peak = min(peak, sim.y)
        if k > 45 and not sim.ground:
            assert sim.glide and sim.vy <= GLIDE_FALL + 1e-6, "classic keys: glide did not switch on"
            glided = True
        if sim.ground and k > 40:
            break
    assert glided and not sim.glide, "classic keys: landing should end the glide"
    assert 9.0 - peak > 3.0, "classic keys: jumps should be full (%.2f)" % (9.0 - peak)
    out.append("full jump %.2f tiles, glide toggles" % (9.0 - peak))
    # kitty: real releases make short and long jumps
    hts = []
    for hold in (4, 30):
        ctl = Controls(True)
        sim = Sim(lv)
        sim.place(15.5, 9.0)
        ctl.feed(" ", "press", 0.0)
        top = sim.y
        for k in range(70):
            if k == hold:
                ctl.feed(" ", "release", k * DT)
            ctl.feed(" ", "repeat", k * DT)          # repeats never count as presses
            sim.step(ctl.sample(k * DT))
            top = min(top, sim.y)
        hts.append(9.0 - top)
    assert hts[0] < hts[1] * 0.6, "kitty keys: jump height does not follow the hold (%s)" % hts
    out.append("kitty jumps %.2f / %.2f tiles" % tuple(hts))
    return out


def determinism_test():
    """Random inputs, twice: identical runs."""
    res = []
    for n in range(len(LEVELS)):
        lv = Level(n)
        rnd = random.Random(n)
        inputs = [(rnd.choice((-1, 0, 1, 1)), rnd.random() < 0.06, rnd.random() < 0.6, rnd.random() < 0.03)
                  for _ in range(1500)]
        runs = []
        for _ in range(2):
            s = Sim(lv, toggle_glide=n % 2 == 1)
            log = []
            for inp in inputs:
                log.append(tuple(s.step(inp)))
                if s.dead:
                    s.respawn()
            runs.append((s.x, s.y, s.vx, s.vy, s.f, s.mote_count, hash(tuple(log))))
        assert runs[0] == runs[1], "level %s is not deterministic" % lv.meta["id"]
        res.append(runs[0][4])
    return res


def render_test():
    sizes = ((70, 22), (120, 40), (160, 45))
    count = 0
    for n in range(len(LEVELS)):
        lv = Level(n)
        sim = Sim(lv, toggle_glide=True)
        fx = Fx(lv, sound=False)
        painter = Painter(lv)
        rnd = random.Random(n)
        for k in range(3):
            sim.place(*lv.start)
            x = lv.W * (0.15 + 0.35 * k)
            col = int(clamp(x, 1, lv.W - 2))
            y = next((yy for yy in range(lv.H) if lv.code[yy][col] in (SOL, MOSS, ONE)), lv.H - 1)
            sim.place(col + 0.5, float(y))
            sim.f = rnd.randrange(600)
            for j in range(10):
                fx.events(sim, sim.step((1, j == 2, True, False)))
                fx.update(sim, DT, real=False)
            if lv.boss and k == 2:
                sim.boss = [STUN, 50, lv.boss_at[0], 0.0, 2, -1]
            if lv.chase and k == 1:
                sim.chase_f0, sim.chase_x0 = sim.f - 30, sim.x - 6
            fx.flash = 0.8 if k == 1 else 0.0
            for cols, rows in sizes:
                cam = Camera()
                cv = render(sim, fx, cam, cols, rows, 1.0 + k, painter=painter,
                            extra={"hint": "a hint", "hint_a": 0.7, "msg": "msg" if k else None})
                if k == 0:
                    overlay(cv, PAUSE + ["", SND.label()])
                assert len(cv.px) == rows * 2 and all(len(r) == cols for r in cv.px), "bad canvas size"
                out = cv.emit(True)
                assert out.count("\r\n") == rows - 1
                cv.emit(False)
                count += 1
        for cols, rows in sizes:
            cv = render(sim, fx, Camera(), cols, rows, 2.0, painter=painter)
            overlay(cv, clear_lines(lv, sim, True, 1, n % 3 == 2, n == len(LEVELS) - 1))
            cv.emit(True)
    demo = TitleDemo()
    for cols, rows in sizes:
        for sel in (0, 1):
            cv, nxt = demo.frame(cols, rows, 0.05, sel, sel == 1, sel == 0)
            assert len(cv.px) == rows * 2
            cv.emit(True)
        for sel in (0, 5, 11):
            draw_map(cols, rows, sel, 1.0, sel == 5, sel == 11).emit(True)
            count += 1
    # small launcher-preview sizes must work too
    for w, h in ((24, 8), (60, 30), (40, 12)):
        demo.scene(w, (h + 1) // 2, 0.05)
    return count


def demo_test():
    for b in range(4):
        d = TitleDemo(b)
        s = d.sim
        for i in range(60 * 20):
            s.step(demo_input(s))
            assert not s.dead, "the title demo falls in world %d at x=%.1f" % (b, s.x)
            if s.x > d.lv.W - 6:
                break
        else:
            raise AssertionError("the title demo gets stuck in world %d at x=%.1f" % (b, s.x))


def selftest():
    t0 = time.time()
    global submit
    def no_scores(*a, **k):
        raise AssertionError("the self-test must not write scores")
    submit = no_scores
    # 1. level data is sane
    for n, m in enumerate(LEVELS):
        lv = Level(n)
        assert lv.start and lv.exit, "%s: no start or exit" % m["id"]
        assert len(lv.seeds) == 3, "%s has %d seeds" % (m["id"], len(lv.seeds))
        assert lv.lanterns, "%s has no lantern" % m["id"]
        assert all(len(r) == lv.W for r in m["map"]), "%s: rows of different width" % m["id"]
        assert (lv.chase or lv.boss) if n % 3 == 2 else not (lv.chase or lv.boss), "%s: set piece misplaced" % m["id"]
        if lv.boss:
            assert lv.gate_x is not None and lv.arena[1] > lv.arena[0] + 10
    print("levels: %d in %d worlds, %d motes, %d seeds, %d lanterns" % (
        len(LEVELS), len(BIOMES), sum(len(Level(n).motes) for n in range(len(LEVELS))), 3 * len(LEVELS),
        sum(len(Level(n).lanterns) for n in range(len(LEVELS)))))
    # 2. fallback controls, kitty controls
    for line in fallback_test():
        print("controls: " + line)
    # 3. determinism
    determinism_test()
    print("determinism: random inputs give identical runs in all %d levels" % len(LEVELS))
    # 4. rendering
    print("rendering: %d frames at 70x22, 120x40 and 160x45 (+ title, world map, overlays)" % render_test())
    demo_test()
    print("title demo: the autopilot runs through all four worlds")
    # 5. the route planner: every level can be finished, every lantern is on the way, every seed reachable
    budget = 600.0
    for a in sys.argv:
        if a.startswith("--budget="):
            budget = float(a.split("=")[1])
    print("planning routes with the real physics (A* search, %dk nodes per goal, at most %.0f s per level, "
          "in parallel)..." % (MAIN_NODES // 1000, budget))
    sys.stdout.flush()
    os.environ["ARCADE_SOUND"] = "0"
    jobs = [(n, budget) for n in range(len(LEVELS))]
    try:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=max(1, min(len(jobs), os.cpu_count() or 1))) as ex:
            results = list(ex.map(_solve, jobs))
    except (ImportError, OSError, NotImplementedError):
        results = [_solve(j) for j in jobs]
    bad = []
    for r in sorted(results, key=lambda r: r["n"]):
        m = LEVELS[r["n"]]
        if r["ok"]:
            tag = " (boss beaten by the bot)" if m.get("boss") else (" (outran the chase)" if m.get("chase") else "")
            print("  %s %-16s finished in %s game time, %d lanterns on the route, 3/3 seeds reachable, "
                  "%d search nodes, %.0f s%s" % (m["id"], m["name"], fmt_time(r["frames"]), len(Level(r["n"]).lanterns),
                                                 r["nodes"], r["time"], tag))
        else:
            print("  %s %-16s FAILED: %s" % (m["id"], m["name"], r["why"]))
            bad.append(m["id"])
    assert not bad, "levels without a proven route: %s" % ", ".join(bad)
    print("Self-test ok (%.0f s)" % (time.time() - t0))


def bench():
    for n in (0, 3, 6, 9):
        lv = Level(n)
        sim = Sim(lv)
        fx = Fx(lv, sound=False)
        painter = Painter(lv)
        for k in range(200):
            fx.events(sim, sim.step((1, k % 50 == 0, True, False)))
            if sim.dead:
                sim.respawn()
            fx.update(sim, DT, real=False)
        for cols, rows in ((70, 22), (120, 40), (160, 45), (200, 56)):
            cam = Camera()
            render(sim, fx, cam, cols, rows, 1.0, painter=painter)
            t = time.time()
            for i in range(30):
                cv = render(sim, fx, cam, cols, rows, 1.0 + i / 30, painter=painter)
            t1 = time.time()
            for i in range(30):
                cv.emit(True)
            t2 = time.time()
            per = (t2 - t) / 30
            print("%s %-14s %3dx%-3d render %5.1f ms  emit %4.1f ms  = %5.1f ms  (%3.0f fps)" % (
                lv.meta["id"], BIOMES[lv.biome], cols, rows, (t1 - t) / 30 * 1000, (t2 - t1) / 30 * 1000, per * 1000,
                1 / per))
    lv = Level(4)
    s = Sim(lv)
    t = time.time()
    for k in range(6000):
        s.step((1 if (k // 90) % 3 else -1, k % 37 == 0, True, False))
        if s.dead:
            s.respawn()
    print("physics: %.1f us per step" % ((time.time() - t) / 6000 * 1e6))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--bench" in sys.argv:
        bench()
    else:
        main()
