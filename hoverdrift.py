#!/usr/bin/env python3
"""HOVERDRIFT - glide over endless painted landscapes, right in your terminal.

A voxel-space renderer (height map + colour map, drawn column by column like the flight games of the
early nineties) painted with truecolor half-block pixels. Pick a vehicle, pick a world (meadows, ice,
desert, volcano and alien planets) and shoot balloons, crystals, drones and towers with six weapons.

No dependencies: Python 3 on macOS / Linux in a truecolor terminal (WezTerm, iTerm2, kitty, Ghostty).
"""
import math
import os
import random
import select
import sys
import termios
import time
import tty

N = 512            # world size (it wraps around)
M = N - 1
MAX_H = 150.0
FAR = 420.0        # draw distance
TAU = 2 * math.pi

# --- palettes per time of day (themes override parts of these) ----------------------------------
TIMES = {
    "day": dict(sky_top=(58, 116, 204), sky_hor=(178, 210, 238), fog=(170, 200, 228), sun=(255, 250, 232),
                sun_dir=(0.55, 0.35, 0.76), sun_az=2.3, sun_el=0.55, light=(1.0, 0.98, 0.92), amb=0.42,
                cloud=(250, 250, 255), cloud_shade=(196, 206, 226), water=(46, 112, 176), stars=False),
    "sunset": dict(sky_top=(46, 52, 112), sky_hor=(250, 146, 84), fog=(222, 140, 100), sun=(255, 214, 140),
                   sun_dir=(-0.80, 0.45, 0.25), sun_az=-0.6, sun_el=0.10, light=(1.05, 0.72, 0.50), amb=0.34,
                   cloud=(255, 176, 128), cloud_shade=(150, 90, 110), water=(70, 70, 120), stars=False),
    "night": dict(sky_top=(4, 6, 20), sky_hor=(24, 34, 70), fog=(20, 28, 56), sun=(226, 232, 255),
                  sun_dir=(0.3, -0.6, 0.6), sun_az=0.9, sun_el=0.45, light=(0.36, 0.42, 0.62), amb=0.30,
                  cloud=(46, 54, 86), cloud_shade=(24, 30, 54), water=(16, 30, 64), stars=True),
}
TIME_ORDER = ["day", "sunset", "night"]

# --- what the low ground is filled with --------------------------------------------------------------
LIQUIDS = {
    "water": dict(ripple=0.09, spray=(230, 240, 255), grav=9.0, tint=0.55, glow=False),
    "ice": dict(ripple=0.025, spray=(244, 250, 255), grav=1.0, tint=0.25, glow=False),
    "lava": dict(ripple=0.16, spray=(255, 150, 40), grav=-2.0, tint=0.0, glow=True),
    "acid": dict(ripple=0.12, spray=(255, 170, 230), grav=9.0, tint=0.45, glow=False),
}

# --- worlds -------------------------------------------------------------------------------------------
# water: liquid level; rough/exp/swell/bias: terrain shape; dunes: dune height; spires: crystal spires;
# snow/rockline/forest/wet: biome thresholds; speck: share of glowing/flowery dots; pal: biome colours.
THEMES = {
    "meadow": dict(
        name="Green meadows", water=34.0, rough=0.52, exp=1.7, swell=0.45, bias=-0.18,
        liquid="water", snow=0.80, rockline=0.56, forest=0.56, wet=0.38, speck=0.03,
        pal=dict(deep=(18, 52, 110), shallow=(60, 168, 170), shore=((222, 204, 150), (196, 180, 128)),
                 snow=((236, 240, 248), (212, 220, 236)), rock=((132, 120, 110), (104, 98, 96)), high=(150, 150, 160),
                 forest=((34, 92, 44), (46, 112, 50), (24, 70, 36)), wet=((82, 150, 60), (106, 166, 70)),
                 dry=((150, 158, 78), (176, 170, 96)), speck=(230, 210, 90)),
        sky={}),
    "ice": dict(
        name="Ice world", water=30.0, rough=0.56, exp=2.0, swell=0.45, bias=-0.16,
        liquid="ice", snow=0.42, rockline=0.62, forest=0.64, wet=0.40, speck=0.02,
        pal=dict(deep=(110, 160, 210), shallow=(186, 222, 240), shore=((226, 236, 246), (206, 222, 240)),
                 snow=((244, 247, 252), (222, 232, 246)), rock=((88, 98, 122), (66, 74, 96)), high=(150, 162, 186),
                 forest=((36, 66, 70), (54, 86, 90), (26, 50, 56)), wet=((206, 220, 238), (186, 204, 228)),
                 dry=((232, 238, 248), (212, 222, 240)), speck=(130, 210, 255)),
        ambient=dict(col=(250, 252, 255), rate=70, vz=-5.0, grav=0.0, life=4.0),
        sky=dict(day=dict(sky_top=(84, 136, 208), sky_hor=(212, 230, 244), fog=(214, 228, 242),
                          light=(0.96, 0.99, 1.06)),
                 sunset=dict(sky_hor=(244, 176, 160), fog=(222, 184, 186), light=(1.02, 0.80, 0.74)),
                 night=dict(aurora=True, sky_hor=(20, 40, 70), fog=(18, 34, 60)))),
    "desert": dict(
        name="Desert", water=16.0, rough=0.46, exp=1.4, swell=0.40, bias=-0.12, dunes=7.0,
        liquid="water", snow=9.0, rockline=0.52, forest=0.50, forest_max=3.5, wet=0.55, speck=0.008,
        pal=dict(deep=(24, 96, 130), shallow=(64, 186, 176), shore=((96, 150, 60), (74, 128, 48)),
                 snow=((240, 240, 240), (230, 230, 230)), rock=((176, 96, 62), (146, 74, 50)), high=(196, 128, 86),
                 forest=((56, 112, 40), (78, 132, 50), (40, 88, 30)), wet=((226, 186, 120), (214, 172, 106)),
                 dry=((238, 204, 136), (228, 192, 122)), speck=(84, 136, 56)),
        dust=(222, 196, 140),
        sky=dict(day=dict(sky_top=(64, 118, 202), sky_hor=(238, 218, 178), fog=(236, 216, 180),
                          light=(1.08, 1.0, 0.86)),
                 sunset=dict(sky_hor=(255, 150, 70), fog=(232, 146, 90)))),
    "lava": dict(
        name="Volcano planet", water=40.0, rough=0.58, exp=1.9, swell=0.45, bias=-0.14,
        liquid="lava", snow=0.78, rockline=0.50, forest=0.58, wet=0.40, speck=0.025, speck_glow=True,
        pal=dict(deep=(220, 60, 16), shallow=(255, 180, 50), shore=((120, 52, 30), (90, 40, 30)),
                 snow=((124, 118, 114), (102, 98, 96)), rock=((50, 42, 44), (34, 30, 32)), high=(78, 66, 62),
                 forest=((22, 20, 26), (40, 34, 44), (14, 12, 16)), wet=((60, 50, 48), (74, 58, 52)),
                 dry=((88, 66, 54), (102, 76, 60)), speck=(255, 110, 30)),
        ambient=dict(col=(255, 150, 60), rate=35, vz=3.0, grav=-0.6, life=3.0),
        sky=dict(day=dict(sky_top=(74, 26, 22), sky_hor=(226, 112, 56), fog=(150, 74, 50), sun=(255, 206, 130),
                          light=(1.1, 0.78, 0.62), amb=0.40, cloud=(96, 66, 60), cloud_shade=(44, 30, 30)),
                 sunset=dict(sky_top=(34, 10, 22), sky_hor=(200, 64, 40), fog=(114, 42, 36),
                             cloud=(90, 46, 44), cloud_shade=(40, 20, 24)),
                 night=dict(sky_top=(10, 4, 8), sky_hor=(90, 26, 20), fog=(62, 22, 18),
                            cloud=(50, 24, 22), cloud_shade=(24, 12, 12)))),
    "alien": dict(
        name="Planet Xeno", water=40.0, rough=0.50, exp=1.5, swell=0.45, bias=-0.16,
        liquid="acid", snow=0.84, rockline=0.58, forest=0.52, wet=0.36, speck=0.03, speck_glow=True,
        pal=dict(deep=(110, 30, 130), shallow=(236, 110, 196), shore=((120, 222, 200), (96, 200, 184)),
                 snow=((250, 222, 250), (232, 204, 244)), rock=((84, 62, 124), (62, 46, 98)), high=(124, 104, 166),
                 forest=((140, 40, 160), (184, 64, 196), (100, 22, 122)), wet=((56, 188, 166), (80, 210, 180)),
                 dry=((206, 204, 84), (224, 214, 104)), speck=(255, 96, 150)),
        ambient=dict(col=(255, 190, 240), rate=25, vz=0.6, grav=0.0, life=5.0),
        sky=dict(all=dict(planet=dict(az=0.9, el=0.42, r=0.20, col=(232, 164, 112), ring=(244, 224, 186))),
                 day=dict(sky_top=(26, 116, 110), sky_hor=(186, 240, 204), fog=(170, 222, 196), sun=(255, 244, 210),
                          cloud=(255, 226, 250), cloud_shade=(204, 156, 214), water=(200, 80, 180)),
                 sunset=dict(sky_top=(62, 30, 104), sky_hor=(255, 124, 164), fog=(222, 114, 152),
                             water=(160, 60, 150)),
                 night=dict(sky_top=(8, 4, 26), sky_hor=(42, 22, 74), fog=(38, 22, 62), water=(70, 30, 90)))),
    "crystal": dict(
        name="Crystal moon", water=28.0, rough=0.55, exp=1.8, swell=0.45, bias=-0.16, spires=900,
        liquid="water", snow=0.80, rockline=0.56, forest=0.60, wet=0.40, speck=0.02, speck_glow=True,
        pal=dict(deep=(28, 18, 86), shallow=(86, 70, 196), shore=((150, 140, 192), (128, 118, 170)),
                 snow=((220, 238, 255), (198, 218, 250)), rock=((62, 58, 84), (46, 42, 66)), high=(92, 92, 124),
                 forest=((70, 50, 120), (90, 66, 140), (54, 40, 100)), wet=((72, 66, 112), (88, 80, 132)),
                 dry=((102, 94, 142), (118, 108, 158)), speck=(140, 255, 240),
                 spire=((90, 230, 250), (170, 130, 255), (120, 255, 210), (240, 160, 255))),
        ambient=dict(col=(180, 255, 250), rate=20, vz=0.3, grav=0.0, life=1.6),
        sky=dict(all=dict(stars=True, moons=((2.0, 0.50, 0.05, (224, 232, 255)), (0.4, 0.30, 0.09, (255, 196, 232)))),
                 day=dict(sky_top=(24, 14, 62), sky_hor=(146, 120, 222), fog=(124, 106, 198), sun=(236, 242, 255),
                          light=(0.92, 0.92, 1.1), amb=0.46, cloud=(200, 182, 255), cloud_shade=(118, 98, 180),
                          water=(60, 40, 160)),
                 sunset=dict(sky_top=(30, 10, 50), sky_hor=(232, 120, 200), fog=(170, 96, 170)),
                 night=dict(sky_top=(4, 2, 14), sky_hor=(30, 20, 66), fog=(26, 18, 56)))),
}
THEME_ORDER = list(THEMES)


def palette(theme, tod):
    P = dict(TIMES[tod])
    sky = THEMES[theme]["sky"]
    P.update(sky.get("all", {}))
    P.update(sky.get(tod, {}))
    return P


def clamp(v, a, b):
    return a if v < a else b if v > b else v


def mix(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


# =============================================================================================
# World generation
# =============================================================================================
def diamond_square(n, rough, rnd):
    """A tileable n x n fractal height field (flat list), values roughly in -1..1."""
    H = [0.0] * (n * n)
    step, scale = n, 1.0
    while step > 1:
        half = step // 2
        for y in range(0, n, step):
            y2 = (y + step) % n
            for x in range(0, n, step):
                x2 = (x + step) % n
                s = H[y * n + x] + H[y * n + x2] + H[y2 * n + x] + H[y2 * n + x2]
                H[((y + half) % n) * n + (x + half) % n] = s * 0.25 + (rnd.random() - 0.5) * scale
        for y in range(0, n, half):
            ya, yb = ((y - half) % n) * n, ((y + half) % n) * n
            for x in range(half if (y // half) % 2 == 0 else 0, n, step):
                s = H[ya + x] + H[yb + x] + H[y * n + (x - half) % n] + H[y * n + (x + half) % n]
                H[y * n + x] = s * 0.25 + (rnd.random() - 0.5) * scale
        step, scale = half, scale * rough
    return H


def blur(H, n):
    out = [0.0] * (n * n)
    for y in range(n):
        r0, r1, r2 = ((y - 1) % n) * n, y * n, ((y + 1) % n) * n
        for x in range(n):
            xl, xr = (x - 1) % n, (x + 1) % n
            out[r1 + x] = (H[r1 + x] * 4 + H[r0 + x] + H[r2 + x] + H[r1 + xl] + H[r1 + xr]) * 0.125
    return out


def normalize(H):
    lo, hi = min(H), max(H)
    k = 1.0 / (hi - lo or 1)
    return [(v - lo) * k for v in H]


class World:
    def __init__(self, seed, theme):
        self.seed, self.theme = seed, theme
        T = self.T = THEMES[theme]
        self.liq = LIQUIDS[T["liquid"]]
        self.wl = WL = T["water"]
        rnd = random.Random(seed)
        h = normalize(blur(blur(diamond_square(N, T["rough"], rnd), N), N))
        # broad valleys, sharper peaks; a gentle continental swell so there are lakes and ranges
        swell = normalize(blur(diamond_square(N, 0.35, rnd), N))
        raw = [clamp((v * 0.75 + s * T["swell"] + T["bias"]), 0, 1) ** T["exp"] * MAX_H for v, s in zip(h, swell)]
        self.moist = normalize(diamond_square(N, 0.55, rnd))
        if T.get("dunes"):  # long wind-blown ridges, bent by a slow warp, fading out on the mountains
            warp = normalize(blur(diamond_square(N, 0.5, rnd), N))
            A, k = T["dunes"], TAU / N
            for y in range(N):
                for x in range(N):
                    i = y * N + x
                    if raw[i] > WL:
                        s = 0.5 + 0.5 * math.sin((23 * x + 9 * y) * k + warp[i] * 9)
                        raw[i] += s * s * A * clamp((MAX_H * 0.5 - raw[i]) / (MAX_H * 0.3), 0, 1)
        self.spire = set()
        for _ in range(T.get("spires", 0)):  # glowing crystal spires
            x, y = rnd.randrange(N), rnd.randrange(N)
            i = y * N + x
            if WL + 3 < raw[i] < MAX_H * 0.6:
                top = raw[i] + rnd.uniform(6, 18)
                for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
                    j = ((y + dy) & M) * N + ((x + dx) & M)
                    raw[j] = max(raw[j], top - (dx + dy) * 3)
                    self.spire.add(j)
        self.raw = raw
        self.H = [max(v, WL) for v in raw]
        self.water = [v < WL for v in raw]
        self.albedo()
        self.time = None

    def height(self, x, y):
        """Bilinear terrain (or liquid) height at a world point."""
        ix, iy = math.floor(x), math.floor(y)
        fx, fy = x - ix, y - iy
        H = self.H
        a = H[(iy & M) * N + (ix & M)]
        b = H[(iy & M) * N + ((ix + 1) & M)]
        c = H[((iy + 1) & M) * N + (ix & M)]
        d = H[((iy + 1) & M) * N + ((ix + 1) & M)]
        return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy

    def over_liquid(self, x, y):
        return self.water[(int(y) & M) * N + (int(x) & M)]

    def albedo(self):
        """Base colour, glow and slope normal of every cell (independent of the time of day)."""
        raw, moist, T, Pl, WL = self.raw, self.moist, self.T, self.T["pal"], self.wl
        rnd = random.Random(self.seed + 7)
        self.base, self.nrm = [], []
        self.glow = glow = bytearray(N * N)
        lglow, sglow = self.liq["glow"], T.get("speck_glow", False)
        snow, rockline, forest, wet, speck = T["snow"], T["rockline"], T["forest"], T["wet"], 1 - T["speck"]
        fmax = WL + T.get("forest_max", 999.0)
        spire, spc = self.spire, Pl.get("spire")
        for y in range(N):
            r0, r1, r2 = ((y - 1) & M) * N, y * N, ((y + 1) & M) * N
            for x in range(N):
                i = r1 + x
                h = raw[i]
                gx = raw[r1 + ((x + 1) & M)] - raw[r1 + ((x - 1) & M)]
                gy = raw[r2 + x] - raw[r0 + x]
                if h < WL:
                    gx = gy = 0.0
                ln = math.sqrt(gx * gx + gy * gy + 4.0)
                self.nrm.append((-gx / ln, -gy / ln, 2.0 / ln))
                slope = math.sqrt(gx * gx + gy * gy)
                t = h / MAX_H
                m = moist[i]
                j = rnd.random()
                if h < WL:
                    c = mix(Pl["shallow"], Pl["deep"], clamp((WL - h) / 18.0, 0, 1))
                    if lglow:
                        glow[i] = 1
                elif spc and i in spire:
                    c = spc[(i * 7 + (i >> 9) * 3) % len(spc)]
                    glow[i] = 1
                elif h < WL + 2.2:
                    c = mix(*Pl["shore"], j)
                elif t > snow - 0.08 * m and slope < 5.5:
                    c = mix(*Pl["snow"], j)
                elif t > rockline or slope > 6.5:
                    c = mix(*Pl["rock"], j)
                    if t > 0.7:
                        c = mix(c, Pl["high"], 0.4)
                elif m > forest and t < 0.48 and h < fmax:  # forest: speckled crowns
                    f = Pl["forest"]
                    c = f[0] if j < 0.45 else f[1] if j < 0.8 else f[2]
                elif m > wet:
                    c = mix(*Pl["wet"], j)
                    if j > speck:
                        c, glow[i] = Pl["speck"], sglow
                else:
                    c = mix(*Pl["dry"], j)
                    if j > speck:
                        c, glow[i] = Pl["speck"], sglow
                self.base.append(c)

    def light(self, P, key):
        """Colour every cell for a palette: sun shading, ambient, tint. Glowing cells ignore the light."""
        if self.time == key:
            return
        sx, sy, sz = P["sun_dir"]
        lr, lg, lb = P["light"]
        amb = P["amb"]
        wat = P["water"]
        tint = self.liq["tint"]
        glow, water = self.glow, self.water
        self.C = C = []
        for i, (c, (nx, ny, nz)) in enumerate(zip(self.base, self.nrm)):
            if glow[i]:
                C.append((c[0] & 0xFC, c[1] & 0xFC, c[2] & 0xFC))
                continue
            d = nx * sx + ny * sy + nz * sz
            k = amb + (1 - amb) * (d if d > 0 else 0) * 1.25
            if water[i]:
                c = mix(c, wat, tint)
                k = amb + (1 - amb) * 0.85
            C.append((min(255, int(c[0] * k * lr)) & 0xFC, min(255, int(c[1] * k * lg)) & 0xFC,
                      min(255, int(c[2] * k * lb)) & 0xFC))
        self.time = key


# =============================================================================================
# Sky
# =============================================================================================
class Sky:
    def __init__(self, seed):
        rnd = random.Random(seed + 3)
        W = 720  # cloud texture all the way round
        cl = diamond_square(256, 0.6, rnd)
        cl = normalize(cl)
        self.CW, self.CH = W, 24
        self.clouds = [[clamp((cl[(y * 5 % 256) * 256 + (x * 256 // W)] - 0.52) * 3.2, 0, 1)
                        for x in range(W)] for y in range(self.CH)]
        self.stars = [(rnd.random() * TAU, rnd.random() ** 0.7, rnd.choice([150, 190, 240]))
                      for _ in range(260)]
        self.key = None

    def prepare(self, P, key, PH):
        if (key, PH) == self.key:
            return
        self.P = P
        # gradient indexed by (row - horizon) + PH*2: zenith above, a band of haze at the horizon
        g = []
        for k in range(-PH * 2, PH * 2):
            if k < 0:
                t = clamp(-k / (PH * 0.9), 0, 1) ** 0.6
                g.append(mix(P["sky_hor"], P["sky_top"], t))
            else:
                g.append(P["fog"])
        self.grad = g
        self.key = (key, PH)

    def column(self, ang, hor, PH, t, S):
        """The sky pixels of one screen column looking along heading ang (S: pixels per radian)."""
        off = PH * 2 - hor
        col = self.grad[off:off + PH]
        P = self.P

        def rel(a):
            return (ang - a + math.pi) % TAU - math.pi

        # stars
        if P["stars"]:
            for a, e, b in self.stars:
                if abs(rel(a)) < 0.0045:
                    y = int(hor - e * PH * 0.95)
                    if 0 <= y < hor - 1:
                        col[y] = (b, b, min(255, b + 15))
        # aurora curtains
        if P.get("aurora"):
            inten = (0.5 + 0.5 * math.sin(ang * 3 + t * 0.21)) * (0.5 + 0.5 * math.sin(ang * 7.3 - t * 0.37 + 1.3))
            if inten > 0.12:
                top = int(hor - PH * 0.8 - 6 * math.sin(ang * 5 + t * 0.3))
                bot = int(hor - PH * 0.3)
                for y in range(max(0, top), min(hor, bot)):
                    v = (y - top) / (bot - top)
                    a = clamp(inten * v * v * (1 - v) * 7.0, 0, 0.85)
                    col[y] = mix(col[y], mix((170, 70, 230), (70, 255, 150), v), a)
        # a giant ringed planet
        pl = P.get("planet")
        if pl:
            R = pl["r"] * PH
            dx = rel(pl["az"]) * S
            if abs(dx) < R * 2.5:
                cy = hor - pl["el"] * PH * 0.9
                c0, rc = pl["col"], pl["ring"]
                ct, st = 0.966, 0.259
                for y in range(max(0, int(cy - R * 1.2)), min(hor, int(cy + R * 1.2) + 1)):
                    dy = y - cy
                    rx, ry = dx * ct + dy * st, dy * ct - dx * st
                    e = (rx / (R * 2.2)) ** 2 + (ry / (R * 0.42)) ** 2
                    ring = 0.62 < e < 1.0 and not (0.78 < e < 0.84)
                    if dx * dx + dy * dy < R * R and not (ring and ry > 0):
                        band = 0.84 + 0.16 * math.sin(dy / R * 10 + 1)
                        lit = clamp(0.7 - 0.5 * (dx * 0.6 + dy * 0.5) / R, 0.18, 1.1) * band
                        col[y] = mix((min(255, int(c0[0] * lit)), min(255, int(c0[1] * lit)),
                                      min(255, int(c0[2] * lit))), col[y], 0.12)
                    elif ring:
                        col[y] = mix(col[y], rc, 0.7)
        # moons
        for az, el, r, mc in P.get("moons", ()):
            R = r * PH
            dx = rel(az) * S
            if abs(dx) < R + 1:
                cy = hor - el * PH * 0.9
                for y in range(max(0, int(cy - R - 1)), min(hor, int(cy + R + 2))):
                    dy = y - cy
                    if dx * dx + dy * dy < R * R:
                        lit = 0.5 + 0.5 * clamp((dx * 0.8 - dy * 0.3) / R + 0.3, -1, 1)
                        col[y] = mix(col[y], mc, 0.25 + 0.75 * lit)
        # sun
        da = rel(P["sun_az"])
        if abs(da) < 0.5:
            sy = hor - P["sun_el"] * PH * 0.9
            sun = P["sun"]
            for y in range(max(0, int(sy - 14)), min(PH, int(sy + 14), hor)):
                d = math.hypot(da * S, (y - sy) * 1.0)
                if d < 2.6:
                    col[y] = sun
                elif d < 14:
                    col[y] = mix(col[y], sun, (1 - d / 14) ** 2 * 0.7)
        # clouds: a band above the horizon, drifting slowly
        ci = int(((ang / TAU) * self.CW + t * 1.2)) % self.CW
        top = hor - int(PH * 0.42)
        cc, cs = P["cloud"], P["cloud_shade"]
        for j in range(self.CH):
            y = top + j
            if 0 <= y < hor:
                v = self.clouds[j][ci]
                if v > 0:
                    col[y] = mix(col[y], mix(cc, cs, j / self.CH), min(1.0, v) * 0.9)
        return col


# =============================================================================================
# Vehicles (seen from behind) and weapons
# =============================================================================================
# Sprite letters: # outline, . shade, w/W light, C canopy, R stripe, d hull, k skirt, G gun, M muzzle,
# E/e engine glow, g tractor glow, L blinking lights.
CRAFT_PAL = {"#": (28, 30, 40), ".": (70, 72, 86), "w": (196, 202, 214), "W": (238, 242, 248),
             "C": (90, 176, 226), "R": (214, 64, 52), "d": (126, 132, 148), "k": (62, 64, 76), "G": (78, 82, 94)}
LIGHTS = [(255, 70, 70), (255, 220, 80), (80, 255, 120), (90, 160, 255)]

VEHICLES = [
    dict(id="hovercraft", name="Hovercraft", desc="balanced, twin guns", vmax=70.0, turn=0.55, resp=0.8,
         hover=(3.0, 60.0, 7.0), rate=1.0, guns=(-1.6, 1.6), glow=((150, 220, 255), (210, 245, 255)), pal={},
         sprite=[
             "         .###.         ",
             "       .#wWWWw#.       ",
             "  M  ..#wwCCCww#..  M  ",
             "  G #RRRRRRRRRRRRR# G  ",
             " GG#ddddddWWWdddddd#GG ",
             "#kkkkdddddddddddddkkkk#",
             "  #kkk#.........#kkk#  ",
             "   EeE           EeE   ",
         ]),
    dict(id="jet", name="Jet glider", desc="fast, climbs high, quick turns", vmax=125.0, turn=0.8, resp=1.3,
         hover=(4.0, 130.0, 18.0), rate=1.0, guns=(-2.4, 2.4), glow=((255, 170, 80), (255, 240, 190)),
         pal={"R": (60, 140, 230), "C": (250, 200, 90), "d": (150, 156, 170)},
         sprite=[
             "           .#.           ",
             "          #wCw#          ",
             "         #wCCCw#         ",
             " M      #wwWWWww#      M ",
             " G   ###dddRRRddd###   G ",
             "#GkkkkkkdddddddddkkkkkkG#",
             "  ##kkk###kEeEk###kkk##  ",
             "          eEEEe          ",
         ]),
    dict(id="tank", name="Hover tank", desc="slow and heavy, three guns, fires faster", vmax=42.0, turn=0.42,
         resp=0.6, hover=(2.5, 22.0, 4.0), rate=1.5, guns=(-1.9, 0.0, 1.9), glow=((120, 255, 160), (220, 255, 230)),
         pal={"R": (112, 128, 70), "d": (92, 104, 72), "k": (54, 60, 44), "w": (150, 160, 120), "W": (180, 190, 150)},
         sprite=[
             "          #M#          ",
             "          #G#          ",
             "      ###########      ",
             "     #ddddGGGdddd#     ",
             " MM #RRRRRRRRRRRRR# MM ",
             " GG#ddddddddddddddd#GG ",
             "#kkkkkkkkkkkkkkkkkkkkk#",
             "#kk.................kk#",
             "  EeE             EeE  ",
         ]),
    dict(id="saucer", name="Saucer", desc="turns on the spot, floats high", vmax=75.0, turn=1.1, resp=1.6,
         hover=(3.0, 90.0, 10.0), rate=1.2, guns=(-2.2, 2.2), glow=((120, 255, 140), (200, 255, 210)),
         pal={"d": (150, 156, 170), "k": (90, 94, 110), "C": (140, 255, 200)},
         sprite=[
             "         .###.         ",
             "       .#CCCCC#.       ",
             "     ##wwwWWWwww##     ",
             "  ###ddddddddddddd###  ",
             " #LkLkLkLkLkLkLkLkLkL# ",
             " M##ddddddddddddddd##M ",
             "     ##ggggggggg##     ",
             "       g   g   g       ",
         ]),
]

WEAPONS = [
    dict(name="Laser", rate=9.0, speed=200.0, col=(120, 255, 220), kind="bolt", mode="alt", life=2.2, splash=0),
    dict(name="Twin laser", rate=7.0, speed=200.0, col=(255, 120, 220), kind="bolt", mode="all", life=2.2, splash=0),
    dict(name="Spread", rate=3.0, speed=170.0, col=(255, 240, 120), kind="bolt", mode="center", fan=5, life=1.6,
         splash=0),
    dict(name="Plasma", rate=2.2, speed=110.0, col=(170, 120, 255), kind="plasma", mode="center", life=3.0, splash=8),
    dict(name="Rockets", rate=1.8, speed=60.0, col=(255, 200, 90), kind="rocket", mode="alt", life=5.0, splash=9),
    dict(name="Bombs", rate=1.5, speed=0.0, col=(255, 140, 60), kind="bomb", mode="center", life=9.0, splash=14),
]
TARGETS = {  # radius, vertical half size, points
    "balloon": (2.4, 2.8, 1), "crystal": (2.0, 3.0, 3), "drone": (2.4, 1.4, 5), "tower": (1.8, 6.0, 4),
}


# =============================================================================================
# The game
# =============================================================================================
class Game:
    def __init__(self, seed=None, theme=None, vehicle=0):
        seed = seed if seed is not None else random.randrange(1 << 30)
        if theme is None:
            theme = random.Random(seed).choice(THEME_ORDER)
        self.tod = "day"
        self.vi = vehicle
        self.heading = 0.6
        self.yaw_rate = 0.0
        self.speed, self.throttle = 26.0, 26.0
        self.hover = self.veh["hover"][2]
        self.new_world(seed, theme)
        self.alt = self.world.height(self.x, self.y) + self.hover
        self.vz = 0.0
        self.pitch = 0.0
        self.t = 0.0
        self.armed = True
        self.autofire = False
        self.weapon = 0
        self.cool = 0.0
        self.firing = 0.0
        self.flash = 0.0
        self.gun_i = 0
        self.score = 0
        self.hits = 0
        self.drift = False
        self.hud = True
        self.help = True       # shown at the start until the first key
        self.msg, self.msg_t = "", 0.0
        self.fps = 0.0
        self.amb_acc = 0.0
        self.loading = None

    @property
    def veh(self):
        return VEHICLES[self.vi]

    def new_world(self, seed, theme):
        self.world = World(seed, theme)
        self.sky = Sky(seed)
        self.refresh_light()
        # start over open low land, not inside a mountain
        rnd = random.Random(seed)
        wl = self.world.wl
        for _ in range(400):
            x, y = rnd.random() * N, rnd.random() * N
            if wl + 3 < self.world.height(x, y) < wl + 25:
                break
        self.x, self.y = x, y
        self.shots, self.parts, self.targets = [], [], []

    def refresh_light(self):
        self.P = palette(self.world.theme, self.tod)
        self.world.light(self.P, (self.world.theme, self.tod))

    def finish_load(self):
        seed, theme = self.loading
        self.loading = None
        self.new_world(seed, theme)
        self.alt = self.world.height(self.x, self.y) + self.hover
        self.say("Welcome to: %s" % THEMES[theme]["name"])

    def say(self, s):
        self.msg, self.msg_t = s, self.t + 3.0

    # --- controls ------------------------------------------------------------------------------
    def key(self, k):
        if k == "?":
            self.help = not self.help
            return
        self.help = False
        V = self.veh
        if k in ("left", "a"):
            self.yaw_rate += V["turn"]
        elif k in ("right", "d"):
            self.yaw_rate -= V["turn"]
        elif k in ("up", "w"):
            self.throttle = min(V["vmax"], self.throttle + V["vmax"] / 16)
        elif k in ("down", "s"):
            self.throttle = max(0.0, self.throttle - V["vmax"] / 16)
        elif k in ("r", "pgup"):
            self.hover = min(V["hover"][1], self.hover + 2.5)
        elif k in ("f", "pgdn"):
            self.hover = max(V["hover"][0], self.hover - 2.5)
        elif k == "v":
            self.vi = (self.vi + 1) % len(VEHICLES)
            V = self.veh
            self.throttle = min(self.throttle, V["vmax"])
            self.hover = clamp(self.hover, V["hover"][0], V["hover"][1])
            self.say("Vehicle: %s - %s" % (V["name"], V["desc"]))
        elif k == "l":
            nxt = THEME_ORDER[(THEME_ORDER.index(self.world.theme) + 1) % len(THEME_ORDER)]
            self.loading = (random.randrange(1 << 30), nxt)
        elif k == "n":
            self.loading = (random.randrange(1 << 30), self.world.theme)
        elif k == "x":
            self.armed = not self.armed
            if not self.armed:
                self.targets = []
                self.autofire = False
            self.say("Weapons on: Space fires, 1-6 / Tab switch." if self.armed else "Weapons off. Just fly.")
        elif k in ("1", "2", "3", "4", "5", "6"):
            self.weapon = int(k) - 1
            self.armed = True
            self.say(WEAPONS[self.weapon]["name"])
        elif k in ("tab", "e"):
            self.weapon = (self.weapon + 1) % len(WEAPONS)
            self.armed = True
            self.say(WEAPONS[self.weapon]["name"])
        elif k == " ":
            self.armed = True
            self.firing = self.t + 0.55  # key repeat keeps it going while held
        elif k == "enter":
            self.autofire = not self.autofire
            self.armed = self.armed or self.autofire
            self.say("Autofire %s" % ("on" if self.autofire else "off"))
        elif k == "t":
            self.tod = TIME_ORDER[(TIME_ORDER.index(self.tod) + 1) % len(TIME_ORDER)]
            self.refresh_light()
            self.say("Time: %s" % self.tod)
        elif k == "c":
            self.drift = not self.drift
            self.say("Drift autopilot %s" % ("on: sit back" if self.drift else "off"))
        elif k == "h":
            self.hud = not self.hud

    # --- simulation -----------------------------------------------------------------------------
    def fwd(self, a=0.0):
        return -math.sin(self.heading + a), -math.cos(self.heading + a)

    def update(self, dt):
        self.t += dt
        W, V = self.world, self.veh
        if self.drift:
            self.yaw_rate += (0.35 * math.sin(self.t * 0.07) + 0.2 * math.sin(self.t * 0.023 + 1)) * dt
            # steer gently away from tall ground ahead
            fx, fy = self.fwd()
            ahead = W.height(self.x + fx * 60, self.y + fy * 60)
            if ahead > self.alt + 10:
                lx, ly = self.x + (fx * 50 - fy * 30), self.y + (fy * 50 + fx * 30)
                rx, ry = self.x + (fx * 50 + fy * 30), self.y + (fy * 50 - fx * 30)
                self.yaw_rate += (0.6 if W.height(lx, ly) < W.height(rx, ry) else -0.6) * dt
        lim = 1.4 * V["turn"] / 0.55
        self.yaw_rate = clamp(self.yaw_rate, -lim, lim) * (0.15 ** dt)
        self.heading = (self.heading + self.yaw_rate * dt) % TAU
        self.speed += (self.throttle - self.speed) * min(1.0, dt * V["resp"])
        fx, fy = self.fwd()
        self.x = (self.x + fx * self.speed * dt) % N
        self.y = (self.y + fy * self.speed * dt) % N
        # follow the ground, looking ahead so hills never come as a surprise
        look = [W.height(self.x + fx * d, self.y + fy * d) for d in (0, 4, 9, 16, 26, 40, 60)]
        want = max(look[0], look[1], look[2], look[3] - 1, look[4] - 3, look[5] - 6,
                   look[6] - 10 if self.speed > 60 else 0) + self.hover
        floor = look[0] + 2.5
        rate = 2.2 if want > self.alt else 0.9
        nalt = self.alt + (want - self.alt) * min(1.0, dt * rate)
        nalt += math.sin(self.t * 1.7) * 0.25 * dt * 4  # a lazy bob
        nalt = max(nalt, floor)
        self.vz = (nalt - self.alt) / max(dt, 1e-3)
        self.alt = nalt
        self.pitch += (clamp(self.vz * 0.35, -6, 8) - self.pitch) * min(1.0, dt * 3)
        self.effects(dt, fx, fy, look[0])
        self.update_weapons(dt)
        self.update_parts(dt)

    def effects(self, dt, fx, fy, ground):
        W = self.world
        low = self.alt - ground < 14 and self.speed > 6
        if low and W.over_liquid(self.x, self.y):  # spray, ice dust or embers
            liq = W.liq
            for _ in range(2):
                side = random.choice((-1, 1)) * random.uniform(0.6, 1.4)
                self.parts.append([self.x - fx * 2 + fy * side, self.y - fy * 2 - fx * side, W.wl + 0.3,
                                   random.uniform(-1, 1) - fx * 4, random.uniform(-1, 1) - fy * 4,
                                   random.uniform(2, 5), 0.0, random.uniform(0.5, 1.0), liq["spray"], liq["grav"]])
        elif low and W.T.get("dust") and self.alt - ground < 10:
            for _ in range(2):
                side = random.uniform(-1.5, 1.5)
                self.parts.append([self.x - fx * 3 + fy * side, self.y - fy * 3 - fx * side, ground + 0.4,
                                   random.uniform(-1.5, 1.5) - fx * 3, random.uniform(-1.5, 1.5) - fy * 3,
                                   random.uniform(1, 3), 0.0, random.uniform(0.8, 1.6), W.T["dust"], 1.5])
        amb = W.T.get("ambient")
        if amb:  # snowfall, embers, spores, sparkles
            self.amb_acc += amb["rate"] * dt
            while self.amb_acc >= 1:
                self.amb_acc -= 1
                d, a = random.uniform(4, 70), self.heading + random.uniform(-0.8, 0.8)
                px, py = (self.x - math.sin(a) * d) % N, (self.y - math.cos(a) * d) % N
                pz = (self.alt + random.uniform(0, 26)) if amb["vz"] < 0 else W.height(px, py) + random.uniform(1, 28)
                self.parts.append([px, py, pz, random.uniform(-1, 1) + 1.0, random.uniform(-1, 1),
                                   amb["vz"] * random.uniform(0.6, 1.2), 0.0, amb["life"] * random.uniform(0.6, 1.0),
                                   amb["col"], amb["grav"]])

    def spawn_target(self):
        W = self.world
        a = self.heading + random.uniform(-1.3, 1.3)
        d = random.uniform(90, 260)
        tx, ty = (self.x - math.sin(a) * d) % N, (self.y - math.cos(a) * d) % N
        kind = random.choice(("balloon", "balloon", "balloon", "crystal", "drone", "drone", "tower"))
        gz = W.height(tx, ty)
        r, rz, pts = TARGETS[kind]
        tg = dict(x=tx, y=ty, kind=kind, r=r, rz=rz, pts=pts, ph=random.uniform(0, 6.3))
        if kind == "balloon":
            tg.update(z=gz + random.uniform(8, 26),
                      col=random.choice([(230, 60, 60), (250, 200, 60), (150, 90, 230), (60, 200, 120)]))
        elif kind == "crystal":
            tg.update(z=gz + random.uniform(8, 26), col=(110, 240, 255))
        elif kind == "drone":
            tg.update(z=gz + 15, fly=random.uniform(10, 26), hd=random.uniform(0, TAU), col=(255, 70, 60))
        else:
            tg.update(z=gz + rz, base=gz, col=(255, 90, 90))
        self.targets.append(tg)

    def update_weapons(self, dt):
        W = self.world
        if self.armed:
            while len(self.targets) < 12:
                self.spawn_target()
            for tg in self.targets:
                tg["ph"] += dt
                if tg["kind"] == "drone":
                    tg["hd"] += math.sin(tg["ph"] * 0.7) * 0.9 * dt
                    tg["x"] = (tg["x"] - math.sin(tg["hd"]) * 14 * dt) % N
                    tg["y"] = (tg["y"] - math.cos(tg["hd"]) * 14 * dt) % N
                    tg["z"] += (W.height(tg["x"], tg["y"]) + tg["fly"] - tg["z"]) * min(1.0, dt * 1.5)
                elif tg["kind"] != "tower":
                    tg["z"] += math.sin(tg["ph"] * 1.3) * 0.6 * dt
            # forget targets left far behind
            self.targets = [tg for tg in self.targets if self.wdist(tg["x"], tg["y"]) < 330]
            if (self.firing > self.t or self.autofire) and self.cool <= 0:
                self.fire()
        self.cool -= dt
        keep = []
        for s in self.shots:
            k = s["kind"]
            if k == "rocket":  # accelerate and home in
                tg = s["tgt"] if s["tgt"] in self.targets else None
                sp = math.sqrt(s["vx"] ** 2 + s["vy"] ** 2 + s["vz"] ** 2)
                sp = min(sp + 90 * dt, 160)
                if tg:
                    dx, dy, dz = self.wrap(tg["x"] - s["x"]), self.wrap(tg["y"] - s["y"]), tg["z"] - s["z"]
                    dl = math.sqrt(dx * dx + dy * dy + dz * dz) or 1
                    q = min(1.0, dt * 4)
                    s["vx"] += (dx / dl * sp - s["vx"]) * q
                    s["vy"] += (dy / dl * sp - s["vy"]) * q
                    s["vz"] += (dz / dl * sp - s["vz"]) * q
                if random.random() < 0.9:
                    self.parts.append([s["x"], s["y"], s["z"], random.uniform(-1, 1), random.uniform(-1, 1),
                                       random.uniform(0, 1.5), 0.0, 0.9, (150, 150, 156), 0.0])
            elif k == "bomb":
                s["vz"] -= 30 * dt
                if random.random() < 0.4:
                    self.parts.append([s["x"], s["y"], s["z"], 0, 0, 0.5, 0.0, 0.5, (120, 120, 126), 0.0])
            elif k == "plasma" and random.random() < 0.7:
                self.parts.append([s["x"], s["y"], s["z"], random.uniform(-2, 2), random.uniform(-2, 2),
                                   random.uniform(-2, 2), 0.0, 0.4, s["col"], 0.0])
            s["x"] = (s["x"] + s["vx"] * dt) % N
            s["y"] = (s["y"] + s["vy"] * dt) % N
            s["z"] += s["vz"] * dt
            s["life"] -= dt
            pad = 2.6 if k == "plasma" else 1.6
            hit = None
            for tg in self.targets:
                if abs(self.wrap(tg["x"] - s["x"])) < tg["r"] + pad and abs(self.wrap(tg["y"] - s["y"])) < tg["r"] + pad \
                        and abs(tg["z"] - s["z"]) < tg["rz"] + pad:
                    hit = tg
                    break
            ground = W.height(s["x"], s["y"])
            if hit or s["z"] < ground or s["life"] <= 0:
                z = max(s["z"], ground)
                if s["splash"] and (k != "plasma" or hit or s["z"] < ground):
                    self.boom(s["x"], s["y"], z, hit["col"] if hit else s["col"], big=True,
                              huge=k == "bomb")
                    self.blast(s["x"], s["y"], z, s["splash"])
                    if hit:
                        self.pop(hit)
                elif hit:
                    self.boom(s["x"], s["y"], z, hit["col"], big=False)
                    self.pop(hit)
                elif s["z"] < ground:
                    self.puff(s["x"], s["y"], ground)
            else:
                keep.append(s)
        self.shots = keep

    def fire(self):
        w, V = WEAPONS[self.weapon], self.veh
        self.cool = 1.0 / (w["rate"] * V["rate"])
        self.flash = self.t + 0.07
        fx, fy = self.fwd()
        z0 = self.alt + 0.8
        guns = V["guns"]
        if w["mode"] == "all":
            offs = guns
        elif w["mode"] == "alt":
            offs = (guns[self.gun_i % len(guns)],)
            self.gun_i += 1
        else:
            offs = (0.0,)
        n = w.get("fan", 1)
        fan = [(i - (n - 1) / 2) * 0.07 for i in range(n)]
        sp = w["speed"] + self.speed
        vz = 0.0
        aim = self.aim_target(0.22)
        if aim and w["kind"] in ("bolt", "plasma"):
            vz = (aim["z"] - z0) / max(self.wdist(aim["x"], aim["y"]), 1) * sp
        for o in offs:
            for a in fan:
                hx, hy = self.fwd(a)
                s = dict(x=self.x + fx * 2 + fy * o, y=self.y + fy * 2 - fx * o, z=z0, vx=hx * sp, vy=hy * sp, vz=vz,
                         life=w["life"], kind=w["kind"], tgt=None, col=w["col"], splash=w["splash"])
                if w["kind"] == "rocket":
                    s["tgt"] = self.aim_target(0.6)
                elif w["kind"] == "bomb":
                    s.update(z=self.alt - 0.5, vx=fx * self.speed, vy=fy * self.speed, vz=2.0)
                self.shots.append(s)

    def pop(self, tg):
        if tg in self.targets:
            self.targets.remove(tg)
            self.score += tg["pts"]
            self.hits += 1
            self.boom(tg["x"], tg["y"], tg["z"], tg["col"], big=tg["kind"] in ("drone", "tower"))

    def blast(self, x, y, z, r):
        for tg in list(self.targets):
            dx, dy, dz = self.wrap(tg["x"] - x), self.wrap(tg["y"] - y), max(0.0, abs(tg["z"] - z) - tg["rz"])
            if dx * dx + dy * dy + dz * dz < r * r:
                self.pop(tg)

    def boom(self, x, y, z, col, big, huge=False):
        n = 120 if huge else 70 if big else 36
        vmax = 26 if huge else 18 if big else 12
        for _ in range(n):
            a, e = random.uniform(0, 6.3), random.uniform(-0.4, 1.2)
            v = random.uniform(4, vmax)
            c = random.choice([col, (255, 230, 140), (255, 140, 40), col])
            self.parts.append([x, y, z, math.cos(a) * math.cos(e) * v, math.sin(a) * math.cos(e) * v,
                               math.sin(e) * v, 0.0, random.uniform(0.5, 1.4), c, 14.0])
        for _ in range(n // 3):
            self.parts.append([x, y, z, random.uniform(-3, 3), random.uniform(-3, 3), random.uniform(1, 4), 0.0,
                               random.uniform(1.0, 2.2), (120, 116, 118), 0.0])

    def puff(self, x, y, z):
        for _ in range(8):
            self.parts.append([x, y, z, random.uniform(-3, 3), random.uniform(-3, 3), random.uniform(2, 5), 0.0,
                               random.uniform(0.3, 0.7), (180, 160, 120), 9.0])

    def update_parts(self, dt):
        keep = []
        for p in self.parts:
            p[6] += dt
            if p[6] < p[7]:
                p[0] = (p[0] + p[3] * dt) % N
                p[1] = (p[1] + p[4] * dt) % N
                p[2] += p[5] * dt
                p[5] -= p[9] * dt
                keep.append(p)
        self.parts = keep[-1100:]

    @staticmethod
    def wrap(d):
        return (d + N / 2) % N - N / 2

    def wdist(self, x, y):
        return math.hypot(self.wrap(x - self.x), self.wrap(y - self.y))

    def aim_target(self, cone):
        best, bd = None, 1e9
        for tg in self.targets:
            dx, dy = self.wrap(tg["x"] - self.x), self.wrap(tg["y"] - self.y)
            d = math.hypot(dx, dy)
            if d < 5 or d > 280:
                continue
            a = math.atan2(-dx, -dy)
            da = abs((a - self.heading + math.pi) % TAU - math.pi)
            if da < cone and da * 100 + d * 0.1 < bd:
                best, bd = tg, da * 100 + d * 0.1
        return best


# =============================================================================================
# Renderer
# =============================================================================================
class Screen:
    def __init__(self):
        self.true = os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")
        self.fgc, self.bgc = {}, {}

    def fg(self, c):
        s = self.fgc.get(c)
        if s is None:
            if len(self.fgc) > 40000:
                self.fgc.clear()
            s = self.fgc[c] = ("\x1b[38;2;%d;%d;%dm" % c) if self.true else "\x1b[38;5;%dm" % x256(c)
        return s

    def bg(self, c):
        s = self.bgc.get(c)
        if s is None:
            if len(self.bgc) > 40000:
                self.bgc.clear()
            s = self.bgc[c] = ("\x1b[48;2;%d;%d;%dm" % c) if self.true else "\x1b[48;5;%dm" % x256(c)
        return s


def x256(c):
    r, g, b = c
    if abs(r - g) < 10 and abs(g - b) < 10:
        return 232 + min(23, r * 24 // 256)
    q = lambda v: 0 if v < 48 else 1 if v < 115 else (v - 35) // 40
    return 16 + 36 * q(r) + 6 * q(g) + q(b)


def status_lines(g):
    return 2 if g.hud else 1


def render(g, scr, cols, rows):
    W = g.world
    PW = cols
    prow = rows - status_lines(g)
    PH = prow * 2
    S = PW / 2.0                      # focal length in pixels (90 degree view)
    P = g.P
    g.sky.prepare(P, (W.theme, g.tod), PH)
    hor = int(PH * 0.36 + g.pitch)
    fx, fy = g.fwd()
    cam_back = 12.0
    cx, cy = g.x - fx * cam_back, g.y - fy * cam_back
    camh = g.alt + 5.0
    camh = max(camh, W.height(cx, cy) + 2.0)
    sn, cs = math.sin(g.heading), math.cos(g.heading)
    # sky columns
    colsbuf = []
    for i in range(PW):
        ang = g.heading - math.atan((i - PW / 2) / S)
        colsbuf.append(g.sky.column(ang, hor, PH, g.t, S))
    depth = [[1e9] * PH for _ in range(PW)]
    ybuf = [PH] * PW
    Hm, Cm, Wt = W.H, W.C, W.water
    fog = P["fog"]
    fr, fgc, fb = fog
    t2 = g.t * 2.0
    ramp = W.liq["ripple"]
    z, dz = 1.0, 0.35
    while z < FAR:
        plx = -cs * z - sn * z + cx
        ply = sn * z - cs * z + cy
        dx = (2 * cs * z) / PW
        dy = (-2 * sn * z) / PW
        inv = S / z
        f = (z / FAR) ** 1.4
        nf = 1 - f
        fogr, fogg, fogb = fr * f, fgc * f, fb * f
        for i in range(PW):
            yb = ybuf[i]
            if yb > 0:
                idx = (int(ply) & M) * N + (int(plx) & M)
                hs = int((camh - Hm[idx]) * inv + hor)
                if hs < yb:
                    if hs < 0:
                        hs = 0
                    r, gg, b = Cm[idx]
                    if Wt[idx]:  # ripples
                        k = 1.0 + ramp * math.sin(t2 + (idx % 977) * 0.37)
                        r, gg, b = min(255, r * k), min(255, gg * k), min(255, b * k)
                    c = (int(r * nf + fogr) & 0xFC, int(gg * nf + fogg) & 0xFC, int(b * nf + fogb) & 0xFC)
                    n = yb - hs
                    colsbuf[i][hs:yb] = [c] * n
                    depth[i][hs:yb] = [z] * n
                    ybuf[i] = hs
            plx += dx
            ply += dy
        z += dz
        dz *= 1.022

    def project(wx, wy, wz):
        rx, ry = Game.wrap(wx - cx), Game.wrap(wy - cy)
        fz = rx * (-sn) + ry * (-cs)
        if fz < 0.5:
            return None
        lat = rx * cs - ry * sn
        return PW / 2 + lat / fz * S, (camh - wz) / fz * S + hor, fz

    def plot(x, y, d, c):
        x, y = int(x), int(y)
        if 0 <= x < PW and 0 <= y < PH and depth[x][y] > d:
            colsbuf[x][y] = c
            depth[x][y] = d

    def disc(sx, sy, d, rad, cin, cout):
        R = int(rad) + 1
        for yy in range(-R, R + 1):
            for xx in range(-R, R + 1):
                e = (xx * xx + yy * yy) / (rad * rad)
                if e <= 1:
                    plot(sx + xx, sy + yy, d, cin if e < 0.35 else cout)

    # targets
    for tg in g.targets:
        pr = project(tg["x"], tg["y"], tg["z"])
        if not pr:
            continue
        sx, sy, d = pr
        kind = tg["kind"]
        f = min(1.0, (d / FAR) ** 1.4)
        rad = tg["r"] / d * S
        if kind == "tower":
            pb = project(tg["x"], tg["y"], tg["base"])
            ptop = project(tg["x"], tg["y"], tg["base"] + tg["rz"] * 2)
            if pb and ptop:
                hw = max(0.6, rad * 0.5)
                for yy in range(int(ptop[1]), int(pb[1]) + 1):
                    stripe = (yy - int(ptop[1])) % 4 < 2
                    for xx in range(-int(hw), int(hw) + 1):
                        c = (96, 98, 116) if stripe else (60, 62, 76)
                        if xx < 0:
                            c = mix(c, (190, 190, 210), 0.3)
                        plot(sx + xx, yy, d, mix(c, P["fog"], f))
                blink = (255, 80, 80) if int(g.t * 3 + tg["ph"]) % 2 else (255, 200, 120)
                disc(ptop[0], ptop[1], d, max(0.8, rad * 0.9), (255, 255, 230), mix(blink, P["fog"], f))
            continue
        if rad < 0.6:
            plot(sx, sy, d, tg["col"])
            continue
        if kind == "drone":
            spin = int(g.t * 20) % 2
            for xx in range(-int(rad * 1.5), int(rad * 1.5) + 1):  # rotor blur
                plot(sx + xx, sy - rad * 0.7, d, mix((150, 150, 160) if spin else (90, 90, 100), P["fog"], f))
            for yy in range(-int(rad * 0.45), int(rad * 0.45) + 1):
                for xx in range(-int(rad * 0.9), int(rad * 0.9) + 1):
                    plot(sx + xx, sy + yy, d, mix((70, 74, 86) if yy < 0 else (44, 46, 56), P["fog"], f))
            plot(sx, sy, d * 0.999, (255, 60, 50) if int(g.t * 4 + tg["ph"]) % 2 else (120, 30, 30))
            continue
        R = int(rad) + 1
        for yy in range(-R - (1 if kind == "balloon" else R), R + 1):
            for xx in range(-R, R + 1):
                if kind == "balloon":
                    e = (xx / rad) ** 2 + (yy / (rad * 1.15)) ** 2
                    if e > 1:
                        continue
                    lit = 1.25 if (xx + yy) < -rad * 0.6 else 1.0 if e < 0.7 else 0.75
                else:
                    e = abs(xx) / rad + abs(yy) / (rad * 1.5)
                    if e > 1:
                        continue
                    lit = 1.3 if xx < 0 and yy < 0 else 1.0 if xx < 0 else 0.7
                    lit *= 0.9 + 0.2 * math.sin(g.t * 5 + tg["ph"])
                c = tuple(min(255, int(v * lit)) for v in tg["col"])
                plot(sx + xx, sy + yy, d, mix(c, P["fog"], f))
        if kind == "balloon":
            for k in range(int(rad * 1.1) + 1, int(rad * 2.4) + 1):
                plot(sx + math.sin(k * 0.6 + g.t * 2) * 0.6, sy + k, d, (60, 60, 64))
    # shots and particles
    for s in g.shots:
        pr = project(s["x"], s["y"], s["z"])
        if not pr:
            continue
        k = s["kind"]
        if k == "plasma":
            disc(pr[0], pr[1], pr[2], max(1.0, 1.5 / pr[2] * S), (255, 255, 255), s["col"])
            continue
        if k == "bomb":
            disc(pr[0], pr[1], pr[2], max(0.8, 0.7 / pr[2] * S), (90, 90, 96), (36, 36, 40))
            continue
        plot(pr[0], pr[1], pr[2], (255, 255, 255))
        pb = project(s["x"] - s["vx"] * 0.02, s["y"] - s["vy"] * 0.02, s["z"] - s["vz"] * 0.02)
        if pb:
            for j in range(1, 6):
                tx, ty = pr[0] + (pb[0] - pr[0]) * j / 5, pr[1] + (pb[1] - pr[1]) * j / 5
                plot(tx, ty, pr[2], s["col"])
                if pr[2] < 40:
                    plot(tx, ty + 1, pr[2], s["col"])
    for p in g.parts:
        pr = project(p[0], p[1], p[2])
        if pr:
            a = 1 - p[6] / p[7]
            c = p[8] if a > 0.5 else mix(p[8], colsbuf[int(pr[0])][int(pr[1])] if 0 <= int(pr[0]) < PW and 0 <= int(pr[1]) < PH else p[8], 1 - a * 2)
            plot(pr[0], pr[1], pr[2], c)
            if pr[2] < 25:
                plot(pr[0] + 1, pr[1], pr[2], c)
    # the vehicle, banking into turns, with a shadow on the ground
    V = g.veh
    pc = project(g.x, g.y, g.alt)
    if pc:
        ccx, ccy = pc[0], pc[1]
        ps = project(g.x, g.y, W.height(g.x, g.y))
        if ps and ps[1] > ccy + 3:
            for xx in range(-7, 8):
                for yy in range(-1, 1):
                    x, y = int(ps[0]) + xx, int(ps[1]) + yy
                    if 0 <= x < PW and 0 <= y < PH and depth[x][y] < 1e8:
                        c = colsbuf[x][y]
                        colsbuf[x][y] = (int(c[0] * 0.55), int(c[1] * 0.55), int(c[2] * 0.6))
        sprite = V["sprite"]
        sw = max(len(r) for r in sprite)
        mid = (len(sprite) - 1) / 2
        bank = clamp(g.yaw_rate * 2.2 * 0.55 / V["turn"], -2.2, 2.2)
        top = int(ccy) - len(sprite) + 3
        glow = V["glow"][int(g.t * 14) % 2]
        hot = (255, 255, 255) if g.speed > V["vmax"] * 0.45 else glow
        flash = g.t < g.flash
        wcol = WEAPONS[g.weapon]["col"]
        muzzle = (255, 255, 255) if flash else mix(wcol, (30, 30, 36), 0.35) if g.armed else (40, 42, 50)
        vpal = V["pal"]
        for j, row in enumerate(sprite):
            shift = int(round(bank * (j - mid) / mid))
            for k, ch in enumerate(row):
                if ch == " ":
                    continue
                if ch == "E":
                    c = glow
                elif ch == "e":
                    c = hot
                elif ch == "g":
                    c = mix(V["glow"][0], (30, 60, 40), 0.5 + 0.5 * math.sin(g.t * 6 + k * 0.8))
                elif ch == "L":
                    c = LIGHTS[(k // 2 + int(g.t * 6)) % len(LIGHTS)]
                elif ch == "M":
                    c = muzzle
                else:
                    c = vpal.get(ch) or CRAFT_PAL[ch]
                x = int(ccx) - sw // 2 + k + shift
                y = top + j + (1 if (k < sw // 2) == (bank > 0.8) and abs(bank) > 0.8 and j > 2 else 0)
                if 0 <= x < PW and 0 <= y < PH:
                    colsbuf[x][y] = c
                    if ch == "M" and flash:  # muzzle flash
                        for fx2, fy2 in ((0, -1), (-1, -1), (1, -1), (0, -2)):
                            if 0 <= x + fx2 < PW and 0 <= y + fy2 < PH:
                                colsbuf[x + fx2][y + fy2] = wcol if fy2 == -1 else (255, 255, 230)
        if g.armed:
            if WEAPONS[g.weapon]["kind"] == "bomb":  # where a bomb dropped now would land
                fall = math.sqrt(2 * max(1.0, g.alt - W.height(g.x, g.y)) / 30)
                ix, iy = g.x + fx * g.speed * fall, g.y + fy * g.speed * fall
                pa = project(ix, iy, W.height(ix, iy))
                if pa:
                    ax, ay = int(pa[0]), int(pa[1])
                    for x, y in ((ax - 3, ay), (ax + 3, ay), (ax - 2, ay - 1), (ax + 2, ay - 1),
                                 (ax - 2, ay + 1), (ax + 2, ay + 1), (ax, ay)):
                        if 0 <= x < PW and 0 <= y < PH:
                            colsbuf[x][y] = (255, 140, 60)
            else:  # crosshair where shots land at 70 units
                pa = project(g.x + fx * 70, g.y + fy * 70, g.alt + 0.8)
                if pa:
                    ax, ay = int(pa[0]), int(pa[1])
                    tgt = g.aim_target(0.22)
                    cc = (255, 80, 80) if tgt else (255, 255, 255)
                    for k in (2, 3, 4):
                        for x, y in ((ax - k, ay), (ax + k, ay), (ax, ay - k), (ax, ay + k)):
                            if 0 <= x < PW and 0 <= y < PH:
                                colsbuf[x][y] = cc
    # emit the frame
    out = ["\x1b[?2026h\x1b[H"]
    sfg, sbg = scr.fg, scr.bg
    overlay = help_lines(cols, prow) if g.help else {}
    hstyle = sfg((235, 235, 240)) + sbg((20, 24, 40))
    for j in range(prow):
        y0, y1 = 2 * j, 2 * j + 1
        lt = lb = None
        line = []
        ov = overlay.get(j)
        x0 = x1 = -1
        if ov:  # the help box is part of the frame, so nothing is drawn twice
            x0, text = ov
            x1 = x0 + len(text)
        for i in range(PW):
            if x0 <= i < x1:
                if i == x0:
                    line.append(hstyle + text)
                    lt = lb = None
                continue
            col = colsbuf[i]
            t, b = col[y0], col[y1]
            t = (t[0] & 0xF8, t[1] & 0xF8, t[2] & 0xF8)
            b = (b[0] & 0xF8, b[1] & 0xF8, b[2] & 0xF8)
            if t == b:  # one colour fills the cell: only the background matters
                if b != lb:
                    line.append(sbg(b))
                    lb = b
                line.append(" ")
                continue
            if t != lt:
                line.append(sfg(t))
                lt = t
            if b != lb:
                line.append(sbg(b))
                lb = b
            line.append("▀")
        out.append("".join(line))
        out.append("\x1b[0m\r\n")
    out.append(hud(g, cols, rows))
    out.append("\x1b[?2026l")
    return "".join(out)


COMPASS = "N . . NE . . E . . SE . . S . . SW . . W . . NW . . "


def rgb(fg, bg):
    return "\x1b[0;38;2;%d;%d;%d;48;2;%d;%d;%dm" % (fg + bg)


def weapon_bar(g, cols):
    """All six weapons, the current one lit up."""
    base = (12, 14, 24)
    segs = []
    if not g.armed:
        segs.append((" Weapons off - press X (or Space) to arm ", (230, 200, 120), base))
    else:
        for i, w in enumerate(WEAPONS):
            label = " %d %s " % (i + 1, w["name"])
            if i == g.weapon:
                segs.append((label, (10, 10, 16), w["col"]))
            else:
                segs.append((label, mix(w["col"], (120, 120, 130), 0.5), base))
            segs.append((" ", base, base))
        segs.append(("  Space fire  Tab next  Enter autofire%s " % (" [ON]" if g.autofire else ""),
                     (255, 120, 100) if g.autofire else (170, 172, 186), base))
    out, n = [], 0
    for text, fg, bg in segs:
        text = text[:max(0, cols - n)]
        if text:
            out.append(rgb(fg, bg) + text)
            n += len(text)
    out.append(rgb(base, base) + " " * max(0, cols - n) + "\x1b[0m\r\n")
    return "".join(out)


def hud(g, cols, rows):
    out = []
    if g.hud:
        out.append(weapon_bar(g, cols))
    out.append("\x1b[0;38;2;225;225;235;48;2;18;20;30m")
    deg = int(math.degrees(-g.heading)) % 360
    ci = int(deg / 360 * len(COMPASS))
    comp = (COMPASS * 3)[ci + len(COMPASS) - 8: ci + len(COMPASS) + 9]
    parts = [" HOVERDRIFT ", " %s | %s " % (g.veh["name"], THEMES[g.world.theme]["name"]), "[%s]" % comp,
             " speed %3d" % int(g.speed * 3.6), " hover %2d" % int(g.hover), " %s" % g.tod]
    if g.drift:
        parts.append(" DRIFT")
    if g.armed:
        parts.append("  score %d" % g.score)
    parts.append("  %2.0f fps" % g.fps)
    s = "".join(parts) if g.hud else ""
    if g.msg and g.t < g.msg_t:
        s = (s + "   " + g.msg) if g.hud else " " + g.msg
    right = "? help  q quit "
    s = s[:max(0, cols - len(right))]
    out.append(s + " " * max(0, cols - len(s) - len(right)) + (right if len(s) + len(right) <= cols else ""))
    out.append("\x1b[0m")
    return "".join(out)


HELP = [
    "HOVERDRIFT",
    "",
    "Left / Right  or  A / D    steer",
    "Up / Down     or  W / S    throttle",
    "R / F                      hover higher / lower",
    "V                          next vehicle",
    "L                          next world: meadows, ice, desert, planets",
    "N                          a new land of the same kind",
    "T                          time of day: day, sunset, night",
    "C                          drift autopilot (sit back)",
    "",
    "Space                      FIRE (hold it)   Enter: autofire",
    "1-6  or  Tab               laser, twin, spread, plasma, rockets, bombs",
    "X                          weapons off / on",
    "H                          hide the status lines",
    "? show / hide this help     Q / Esc quit",
]


def help_lines(cols, rows):
    """The help box as {screen row: (column, text)}, merged into the picture while it is drawn."""
    w = min(cols, max(len(l) for l in HELP) + 4)
    x = max(0, (cols - w) // 2)
    out = {}
    for j, l in enumerate([""] + HELP + [""]):
        if 1 + j >= rows:
            break
        out[1 + j] = (x, ("  " + l).ljust(w)[:w])
    return out


# =============================================================================================
# Terminal handling
# =============================================================================================
KEYS = {"\x1b[A": "up", "\x1b[B": "down", "\x1b[C": "right", "\x1b[D": "left", "\x1bOA": "up", "\x1bOB": "down",
        "\x1bOC": "right", "\x1bOD": "left", "\x1b[5~": "pgup", "\x1b[6~": "pgdn"}


def read_keys(fd):
    keys = []
    while select.select([fd], [], [], 0)[0]:
        data = os.read(fd, 1024).decode("utf-8", "ignore")
        if not data:
            break
        i = 0
        while i < len(data):
            if data[i] == "\x1b":
                for seq, name in KEYS.items():
                    if data.startswith(seq, i):
                        keys.append(name)
                        i += len(seq)
                        break
                else:
                    keys.append("esc" if i + 1 >= len(data) or data[i + 1] not in "[O" else "?seq")
                    i += 1 if i + 1 >= len(data) or data[i + 1] not in "[O" else 3
            else:
                ch = data[i]
                keys.append("tab" if ch == "\t" else "enter" if ch in "\r\n" else ch.lower())
                i += 1
    return keys


def arg(name):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def main():
    if "--bench" in sys.argv:
        return bench()
    theme, veh = arg("--world"), arg("--vehicle")
    if theme is not None and theme not in THEMES:
        print("Worlds: %s" % ", ".join(THEME_ORDER))
        return
    ids = [v["id"] for v in VEHICLES]
    if veh is not None and veh not in ids:
        print("Vehicles: %s" % ", ".join(ids))
        return
    if not sys.stdout.isatty():
        print("HOVERDRIFT needs a terminal.")
        return
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    w = sys.stdout.write
    w("\x1b[?1049h\x1b[?25l\x1b[2J\x1b[H")
    w("\n\n   HOVERDRIFT\n\n   Raising mountains, filling lakes, planting forests...\n")
    sys.stdout.flush()
    try:
        tty.setcbreak(fd)
        seed = int(arg("--seed")) if arg("--seed") else None
        g = Game(seed, theme, ids.index(veh) if veh else 0)
        scr = Screen()
        last = time.time()
        frame_t = []
        while True:
            if g.loading:
                w("\x1b[0m\x1b[2J\x1b[H\n\n   HOVERDRIFT\n\n   Raising a new world: %s...\n"
                  % THEMES[g.loading[1]]["name"])
                sys.stdout.flush()
                g.finish_load()
                last = time.time()
            now = time.time()
            dt = min(0.1, now - last)
            last = now
            quit_ = False
            for k in read_keys(fd):
                if k in ("q", "esc"):
                    quit_ = True
                else:
                    g.key(k)
            if quit_:
                break
            g.update(dt)
            cols, rows = os.get_terminal_size()
            if cols < 40 or rows < 12:
                w("\x1b[H\x1b[2JPlease make the window larger.")
                sys.stdout.flush()
                time.sleep(0.2)
                continue
            w(render(g, scr, cols, rows))
            sys.stdout.flush()
            frame_t.append(time.time())
            frame_t = frame_t[-20:]
            if len(frame_t) > 1:
                g.fps = (len(frame_t) - 1) / (frame_t[-1] - frame_t[0] or 1)
            spare = 1 / 40 - (time.time() - now)
            if spare > 0:
                time.sleep(spare)
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        w("\x1b[0m\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


def bench():
    scr = Screen()
    for theme in THEME_ORDER:
        t0 = time.time()
        g = Game(1, theme, THEME_ORDER.index(theme) % len(VEHICLES))
        t1 = time.time()
        n = 30
        for i in range(n):
            g.firing = g.t + 1
            g.weapon = i % len(WEAPONS)
            g.update(1 / 30)
            render(g, scr, 160, 45)
        t2 = time.time()
        print("%-15s world %.2fs, frame %.1f ms at 160x45  (shots %d, score %d)"
              % (THEMES[theme]["name"], t1 - t0, (t2 - t1) / n * 1000, len(g.shots), g.score))


if __name__ == "__main__":
    main()
