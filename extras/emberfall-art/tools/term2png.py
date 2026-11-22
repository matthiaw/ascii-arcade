#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""Render img2term output back to a PNG as a terminal would show it (for checking).
Usage: term2png.py IMAGE out.png [--w 48] [--colors 32] [--256]"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
import img2term as I

a = sys.argv[1:]
opt = lambda k, d: a[a.index(k) + 1] if k in a else d
img = I.convert(a[0], int(opt("--w", 48)), "half", colors=int(opt("--colors", 32)), maxh=int(opt("--maxh", 0)) or None, crop="--nocrop" not in a)
pal, fb = img["pal"], img["fb"]


def rgb(i):
    if i is None:
        return (0, 0, 0)
    if pal is not None:
        return I.PAL[fb[i]] if "--256" in a else pal[i]
    return I.PAL[i]


CW, CH = 8, 16
W, H = img["w"] * CW, img["h"] * CH
px = bytearray(W * H * 3)
for cy, row in enumerate(img["rows"]):
    for cx, (ch, fg, bg) in enumerate(row):
        for y in range(CH):
            top = y < CH // 2
            on = ch == "█" or (ch == "▀" and top) or (ch == "▄" and not top)
            c = bytes(rgb(fg) if on else rgb(bg))
            o = ((cy * CH + y) * W + cx * CW) * 3
            px[o:o + CW * 3] = c * CW
tmp = os.path.join(tempfile.mkdtemp(), "x.ppm")
open(tmp, "wb").write(b"P6 %d %d 255\n" % (W, H) + px)
subprocess.run(["sips", "-s", "format", "png", tmp, "--out", a[1]], check=True, stdout=subprocess.DEVNULL)
