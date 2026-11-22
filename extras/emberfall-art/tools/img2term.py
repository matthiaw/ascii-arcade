#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""img2term - turn a picture into terminal art for Emberfall.

Dev tool only (the game itself never needs it). No Pillow required: uses macOS `sips`
to scale/convert to BMP, then decodes the BMP in pure Python.

  python3 tools/img2term.py IMAGE [--w 48] [--mode half|ascii] [--name key] [--preview]

Modes
  half   each cell = 2 vertical pixels via the upper half block, fg = top, bg = bottom.
  ascii  one char per cell picked by brightness from a ramp, coloured.

Output (without --preview) is a Python literal you paste into emberfall.py:
  IMG_<NAME> = {"w": W, "h": H, "mode": "half", "rows": [[(ch, fg256, bg256), ...], ...]}
Colours are xterm-256 indices; rows are run-length friendly lists.
"""
import os
import struct
import subprocess
import sys
import tempfile

RAMP = " .'`,:;-~=+*o#%@"


# --- image loading ------------------------------------------------------------------
def load_rgb(path, w, h):
    """Scale `path` to exactly w x h with sips and return rows of (r, g, b)."""
    tmp = tempfile.mkdtemp()
    out = os.path.join(tmp, "x.bmp")
    subprocess.run(["sips", "-s", "format", "bmp", "-z", str(h), str(w), path, "--out", out],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return read_bmp(out)


def image_size(path):
    o = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", path],
                       check=True, capture_output=True, text=True).stdout
    vals = {}
    for line in o.splitlines():
        if ":" in line:
            k, v = line.strip().split(":", 1)
            vals[k.strip()] = int(v)
    return vals["pixelWidth"], vals["pixelHeight"]


def read_bmp(path):
    d = open(path, "rb").read()
    off = struct.unpack_from("<I", d, 10)[0]
    w, h = struct.unpack_from("<ii", d, 18)
    bpp = struct.unpack_from("<H", d, 28)[0]
    if bpp not in (24, 32):
        raise SystemExit("unsupported BMP depth %d" % bpp)
    bypp = bpp // 8
    stride = (w * bypp + 3) & ~3
    flip = h > 0
    h = abs(h)
    rows = []
    for y in range(h):
        sy = h - 1 - y if flip else y
        base = off + sy * stride
        row = []
        for x in range(w):
            b, g, r = d[base + x * bypp: base + x * bypp + 3]
            row.append((r, g, b))
        rows.append(row)
    return rows


# --- xterm-256 colour matching ------------------------------------------------------
_LV = [0, 95, 135, 175, 215, 255]
PAL = []
for i in range(16):
    PAL.append(None)  # system colours vary per terminal, never pick them
for r in _LV:
    for g in _LV:
        for b in _LV:
            PAL.append((r, g, b))
for i in range(24):
    v = 8 + i * 10
    PAL.append((v, v, v))


def _lin(c):
    return c * c


_cache = {}


def _srgb2lin(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lab(rgb):
    r, g, b = (_srgb2lin(c) for c in rgb)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l, m, s = l ** (1 / 3), m ** (1 / 3), s ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


PAL_LAB = [None if c is None else _lab(c) for c in PAL]


def to256(rgb, chroma_w=1.2):
    """Nearest xterm colour in OKLab; chroma (a, b) weighted up so hue survives."""
    hit = _cache.get(rgb)
    if hit is not None:
        return hit
    L, A, B = _lab(rgb)
    coloured = (A * A + B * B) ** 0.5 > 0.045
    best, bi = 1e18, 232
    for i in range(22, 256):  # 16-21 are repainted by base16 colour schemes
        if coloured and i >= 232:
            continue
        l2, a2, b2 = PAL_LAB[i]
        d = (L - l2) ** 2 + chroma_w * ((A - a2) ** 2 + (B - b2) ** 2)
        if d < best:
            best, bi = d, i
    _cache[rgb] = bi
    return bi


def lum(rgb):
    r, g, b = rgb
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


# --- conversion ---------------------------------------------------------------------
def boost(rgb, contrast=1.08, sat=1.12, gamma=0.88):
    r, g, b = (255 * (c / 255) ** gamma for c in rgb)
    l = 0.299 * r + 0.587 * g + 0.114 * b
    out = []
    for c in (r, g, b):
        c = l + (c - l) * sat
        c = (c - 128) * contrast + 128
        out.append(max(0, min(255, int(c))))
    return tuple(out)


def quantize(px, black, dither=0.75):
    """Map pixels to xterm indices (None = transparent black) with damped
    Floyd-Steinberg error diffusion, so muted in-between tones survive."""
    h, w = len(px), len(px[0])
    buf = [[list(boost(c)) for c in row] for row in px]
    out = [[None] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            c = buf[y][x]
            c = tuple(max(0, min(255, int(v))) for v in c)
            if max(c) < black:
                continue
            i = to256((c[0] & ~3, c[1] & ~3, c[2] & ~3))
            out[y][x] = i
            if not dither:
                continue
            pr = PAL[i]
            err = [(c[k] - pr[k]) * dither for k in range(3)]
            for dx, dy, f in ((1, 0, 7 / 16), (-1, 1, 3 / 16), (0, 1, 5 / 16), (1, 1, 1 / 16)):
                xx, yy = x + dx, y + dy
                if 0 <= xx < w and yy < h and max(px[yy][xx]) >= black:
                    t = buf[yy][xx]
                    for k in range(3):
                        t[k] += err[k] * f
    return out


def median_cut(colors, k):
    """colors: list of (r,g,b). Returns up to k representative colours."""
    boxes = [colors]
    while len(boxes) < k:
        boxes.sort(key=lambda b: max(max(c[i] for c in b) - min(c[i] for c in b) for i in range(3)) * len(b) ** 0.5)
        b = boxes.pop()
        if len(b) < 2:
            boxes.append(b)
            break
        ch = max(range(3), key=lambda i: max(c[i] for c in b) - min(c[i] for c in b))
        b.sort(key=lambda c: c[ch])
        m = len(b) // 2
        boxes += [b[:m], b[m:]]
    return [tuple(sum(c[i] for c in b) // len(b) for i in range(3)) for b in boxes if b]


def palettize(px, black, k=32):
    """Own palette per picture: returns (palette, grid of palette index or None)."""
    pix = [boost(c) for row in px for c in row]
    pix = [c for c in pix if max(c) >= black]
    pal = median_cut(pix, k) if pix else []
    labs = [_lab(c) for c in pal]
    memo = {}

    def near(c):
        if c not in memo:
            L, A, B = _lab(c)
            memo[c] = min(range(len(pal)), key=lambda i: (L - labs[i][0]) ** 2 + (A - labs[i][1]) ** 2 + (B - labs[i][2]) ** 2)
        return memo[c]
    grid = []
    for row in px:
        out = []
        for c in row:
            c = boost(c)
            out.append(None if max(c) < black else near(c))
        grid.append(out)
    return pal, grid


def _bbox(px, black, pad=2):
    h, w = len(px), len(px[0])
    ys = [y for y in range(h) if any(max(c) >= black for c in px[y])]
    xs = [x for x in range(w) if any(max(px[y][x]) >= black for y in range(h))]
    if not ys or not xs:
        return 0, 0, w, h
    return (max(0, xs[0] - pad), max(0, ys[0] - pad), min(w, xs[-1] + 1 + pad), min(h, ys[-1] + 1 + pad))


def _resample(px, box, w, h):
    """Area-average the crop box of px down to w x h."""
    x0, y0, x1, y1 = box
    sw, sh = (x1 - x0) / w, (y1 - y0) / h
    out = []
    for y in range(h):
        ya, yb = y0 + int(y * sh), max(y0 + int(y * sh) + 1, y0 + int((y + 1) * sh))
        row = []
        for x in range(w):
            xa, xb = x0 + int(x * sw), max(x0 + int(x * sw) + 1, x0 + int((x + 1) * sw))
            r = g = b = n = 0
            for yy in range(ya, yb):
                line = px[yy]
                for xx in range(xa, xb):
                    c = line[xx]
                    r += c[0]; g += c[1]; b += c[2]; n += 1
            row.append((r // n, g // n, b // n))
        out.append(row)
    return out


def convert(path, w=48, mode="half", black=24, cell_aspect=2.0, crop=True, maxh=None, dither=0.0, colors=32):
    src = load_rgb(path, 512, 512 * image_size(path)[1] // image_size(path)[0])
    box = _bbox(src, black + 12) if crop else (0, 0, len(src[0]), len(src))
    bw, bh = box[2] - box[0], box[3] - box[1]
    if mode == "half":
        ph = int(round(w * bh / bw))  # half blocks give square pixels
        if maxh and ph > maxh * 2:
            ph = maxh * 2
            w = int(round(ph * bw / bh))
        ph += ph & 1
        small = _resample(src, box, w, ph)
        if colors:
            pal, q = palettize(small, black, colors)
            fb = [to256(c) for c in pal]
        else:
            pal, fb, q = None, None, quantize(small, black, dither)
        rows = []
        for y in range(0, ph, 2):
            row = []
            for x in range(w):
                t, b = q[y][x], q[y + 1][x]
                if t is None and b is None:
                    row.append((" ", None, None))
                elif t is None:
                    row.append(("\u2584", b, None))
                elif b is None:
                    row.append(("\u2580", t, None))
                elif t == b:
                    row.append(("\u2588", t, t))
                else:
                    row.append(("\u2580", t, b))
            rows.append(row)
        return {"w": w, "h": len(rows), "mode": "half", "rows": rows, "pal": pal, "fb": fb}
    ph = max(1, int(round(w * bh / bw / cell_aspect)))
    px = _resample(src, box, w, ph)
    rows = []
    for y in range(ph):
        row = []
        for x in range(w):
            c = boost(px[y][x])
            l = lum(c)
            ch = RAMP[min(len(RAMP) - 1, int(l * len(RAMP)))]
            row.append((ch, to256(c), 16))
        rows.append(row)
    return {"w": w, "h": len(rows), "mode": "ascii", "rows": rows}


def ansi(img, truecolor=True):
    pal, fb = img.get("pal"), img.get("fb")

    def code(i, bgnd):
        if i is None:
            return "\x1b[%dm" % (49 if bgnd else 39)
        if pal is not None:
            if truecolor:
                return "\x1b[%d;2;%d;%d;%dm" % (((48 if bgnd else 38),) + tuple(pal[i]))
            i = fb[i]
        return "\x1b[%d;5;%dm" % ((48 if bgnd else 38), i)
    out = []
    for row in img["rows"]:
        s, last = [], None
        for ch, fg, bg in row:
            if ch == " ":
                fg = bg = None
            elif bg is None:
                bg = None
            if (fg, bg) != last:
                s.append("\x1b[0m" + code(fg, False) + code(bg, True))
                last = (fg, bg)
            s.append(ch)
        out.append("".join(s) + "\x1b[0m")
    return "\n".join(out)


CODE = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def as_python(img, name):
    """Compact literal: palette, 256-colour fallbacks, and per row three equal-length
    strings (glyphs, fg codes, bg codes); code '.' = transparent/black."""
    enc = lambda i: "." if i is None else CODE[i]
    L = ["IMG_%s = {" % name.upper(),
         "    \"pal\": %r," % [tuple(c) for c in img["pal"]],
         "    \"fb\": %r," % img["fb"],
         "    \"rows\": ["]
    for row in img["rows"]:
        g = "".join("h" if ch == "\u2580" else "l" if ch == "\u2584" else "f" if ch == "\u2588" else " " for ch, _, _ in row)
        f = "".join(enc(None if ch == " " else fg) for ch, fg, bg in row)
        b = "".join(enc(None if ch in (" ", "\u2584", "\u2580") and bg is None else bg) for ch, fg, bg in row)
        L.append("        (%r, %r, %r)," % (g, f, b))
    L += ["    ]}"]
    return "\n".join(L)


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    path = a[0]
    opt = lambda k, d: a[a.index(k) + 1] if k in a else d
    img = convert(path, int(opt("--w", 48)), opt("--mode", "half"), maxh=int(opt("--maxh", 0)) or None, dither=float(opt("--dither", 0)), colors=int(opt("--colors", 32)))
    if "--preview" in a:
        print(ansi(img, "--256" not in a))
    else:
        print(as_python(img, opt("--name", os.path.splitext(os.path.basename(path))[0])))


if __name__ == "__main__":
    main()
