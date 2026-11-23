# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""arcadekit - the little shared toolkit of the ASCII ARCADE games.

Raw terminal input, a half-block pixel canvas with text overlays, a chunky block font and a high score file.
Pure Python 3, no dependencies (macOS / Linux).
"""
import json
import os
import re
import select
import sys
import termios
import time
import tty


def _pixel_mode():
    """Pixel style: "fine" draws two pixels per cell with the half-block character; "smart" does that only
    where the two pixels differ clearly and fills near-equal pairs (gradients) with one background colour;
    "solid" draws one pixel per cell from background colour only. smart and solid are for terminals whose
    fonts leave gaps in half-blocks (macOS Terminal.app). ARCADE_PIXELS=fine|smart|solid overrides the setting
    kept in ~/.ascii_arcade_settings.json (switched with G in the ASCII ARCADE launcher)."""
    env = os.environ.get("ARCADE_PIXELS", "").strip().lower()
    if env in ("fine", "smart", "solid"):
        return env
    try:
        with open(os.path.expanduser("~/.ascii_arcade_settings.json")) as f:
            mode = json.load(f).get("pixels")
        return mode if mode in ("fine", "smart", "solid") else "fine"
    except (OSError, ValueError, AttributeError):
        return "fine"


PIXEL_MODE = _pixel_mode()
SOLID_PIXELS = PIXEL_MODE != "fine"   # some cells are filled with one colour instead of a half-block


def solid_cell(t, b):
    """One colour for a cell whose two pixels are t (top) and b (bottom), or None to keep the half-block.
    solid: the brighter pixel where they differ a lot (text, stars, outlines of light), else their mean.
    smart: their mean where they are nearly equal (no visible loss, no seam), else None."""
    if t == b:
        return t
    if not isinstance(t, tuple):      # palette indices (256 colours)
        return None if PIXEL_MODE == "smart" else t
    lt, lb = t[0] * 3 + t[1] * 6 + t[2], b[0] * 3 + b[1] * 6 + b[2]
    d = abs(lt - lb)
    if PIXEL_MODE == "smart":
        if d > 260:
            return None
    elif d > 600:
        return t if lt > lb else b
    return ((t[0] + b[0]) >> 1, (t[1] + b[1]) >> 1, (t[2] + b[2]) >> 1)

SCORES_PATH = os.path.expanduser("~/.ascii_arcade_scores.json")


def _read_version():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")) as f:
            return f.read().strip() or "dev"
    except OSError:
        return "dev"


VERSION = _read_version()
COPYRIGHT = "(c) 2026 Matthias Wegner - MIT License"


def clamp(v, a, b):
    return a if v < a else b if v > b else v


def mix(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def shade(c, k):
    return (clamp(int(c[0] * k), 0, 255), clamp(int(c[1] * k), 0, 255), clamp(int(c[2] * k), 0, 255))


SAFE256 = {16: 232, 17: 234, 18: 24, 19: 25, 20: 26, 21: 27}  # base16 schemes repaint 16-21


def x256(c):
    r, g, b = c
    if abs(r - g) < 10 and abs(g - b) < 10:
        return 232 + min(23, r * 24 // 256)
    q = lambda v: 0 if v < 48 else 1 if v < 115 else (v - 35) // 40
    i = 16 + 36 * q(r) + 6 * q(g) + q(b)
    return SAFE256.get(i, i)


# =============================================================================================
# Terminal
# =============================================================================================
KEYS = {"\x1b[A": "up", "\x1b[B": "down", "\x1b[C": "right", "\x1b[D": "left", "\x1bOA": "up", "\x1bOB": "down",
        "\x1bOC": "right", "\x1bOD": "left", "\x1b[5~": "pgup", "\x1b[6~": "pgdn", "\x1b[Z": "backtab"}


class Terminal:
    """Context manager: alternate screen, no cursor, keys without Enter. Restores everything on exit."""

    def __enter__(self):
        if not sys.stdout.isatty():
            raise SystemExit("This game needs a terminal.")
        self.fd = sys.stdin.fileno()
        self.old = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        self.write("\x1b[?1049h\x1b[?25l\x1b[2J\x1b[H")
        return self

    def __exit__(self, *exc):
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)
        self.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        return exc[0] is KeyboardInterrupt

    @staticmethod
    def write(s):
        sys.stdout.write(s)
        sys.stdout.flush()

    @staticmethod
    def size():
        c, r = os.get_terminal_size()
        return c, r

    def keys(self, timeout=0.0):
        """All keys pressed since the last call (waits up to timeout for the first one)."""
        out = []
        wait = timeout
        while select.select([self.fd], [], [], wait)[0]:
            wait = 0
            data = os.read(self.fd, 1024).decode("utf-8", "ignore")
            if not data:
                break
            i = 0
            while i < len(data):
                if data[i] == "\x1b":
                    for seq, name in KEYS.items():
                        if data.startswith(seq, i):
                            out.append(name)
                            i += len(seq)
                            break
                    else:
                        lone = i + 1 >= len(data) or data[i + 1] not in "[O"
                        out.append("esc" if lone else "?seq")
                        i += 1 if lone else 3
                else:
                    ch = data[i]
                    out.append("tab" if ch == "\t" else "enter" if ch in "\r\n" else
                               "backspace" if ch in "\x7f\x08" else ch.lower())
                    i += 1
        return out


# =============================================================================================
# Held keys: the kitty keyboard protocol reports presses AND releases (kitty, WezTerm, Ghostty, recent iTerm2);
# elsewhere a key counts as held while the terminal keeps repeating it
# =============================================================================================
KITTY_RE = re.compile(r"\x1b\[([0-9:;]*)([uABCDHF~])")
KITTY_NAMES = {13: "enter", 27: "esc", 32: " ", 9: "tab", 127: "backspace", 57399: "0"}
KITTY_ARROWS = {"A": "up", "B": "down", "C": "right", "D": "left"}
KITTY_SHIFTED = {"/": "?", "1": "!"}


class KeyTerminal(Terminal):
    """Terminal plus the kitty keyboard protocol where the terminal speaks it: events() returns
    [(name, kind)] with kind 'press', 'repeat' or 'release'. keys() still works (presses only).
    ARCADE_LEGACY_KEYS=1 switches the protocol off."""

    def __enter__(self):
        super().__enter__()
        self.kitty = self.detect_kitty()
        if self.kitty:
            self.write("\x1b[>15u")
        return self

    def __exit__(self, *exc):
        if getattr(self, "kitty", False):
            self.write("\x1b[<u")
        return super().__exit__(*exc)

    def detect_kitty(self):
        self.pending = ""
        if os.environ.get("ARCADE_LEGACY_KEYS") or os.environ.get("LEAFLING_LEGACY_KEYS"):
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
        data, self.pending = getattr(self, "pending", ""), ""
        wait = 0 if data else timeout
        while select.select([self.fd], [], [], wait)[0]:
            wait = 0
            chunk = os.read(self.fd, 4096).decode("utf-8", "ignore")
            if not chunk:
                break
            data += chunk
        return self.parse(data) if data else []

    def keys(self, timeout=0.0):
        return [n for n, kind in self.events(timeout) if kind == "press"]

    def parse(self, data):
        out = []
        i = 0
        while i < len(data):
            m = KITTY_RE.match(data, i) if getattr(self, "kitty", False) else None
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
                if final in KITTY_ARROWS:
                    name = KITTY_ARROWS[final]
                elif final == "u" and codes[0].isdigit():
                    c = int(codes[0])
                    if (mods - 1) & 4 and c in (99, 100):       # ctrl+c / ctrl+d
                        raise KeyboardInterrupt
                    if (mods - 1) & 1 and len(codes) > 1 and codes[1].isdigit():
                        c = int(codes[1])
                    name = KITTY_NAMES.get(c) or (chr(c).lower() if 32 < c < 0x110000 else None)
                    if name and (mods - 1) & 1 and name in KITTY_SHIFTED:
                        name = KITTY_SHIFTED[name]
                elif final == "~" and codes[0] in ("5", "6"):
                    name = "pgup" if codes[0] == "5" else "pgdn"
                if name:
                    out.append((name, {"1": "press", "2": "repeat", "3": "release"}.get(event, "press")))
                continue
            if data[i] == "\x1b":
                for seq, nm in KEYS.items():
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
                if ch == "\x03":
                    raise KeyboardInterrupt
                out.append(("tab" if ch == "\t" else "enter" if ch in "\r\n" else
                            "backspace" if ch in "\x7f\x08" else ch.lower(), "press"))
                i += 1
        return out


class HeldKeys:
    """Which keys are down right now, for action games.

    kitty mode: exact, from presses and releases. Classic mode: a key counts as held for a short window after
    each press or repeat (the first window bridges the keyboard's initial repeat delay); pressing the opposite
    direction drops the other one at once.

        held = HeldKeys(term.kitty)
        for name, kind in term.events(): held.feed(name, kind, now)
        held.down("left", "a")        # any of these held?
        held.hit(" ")                 # pressed since the last frame (an edge; used up by take_hits())
    """
    OPPOSITE = {"left": "right", "right": "left", "up": "down", "down": "up", "a": "d", "d": "a", "w": "s", "s": "w"}

    def __init__(self, kitty, first=0.55, repeat=0.14):
        self.kitty = kitty
        self.first, self.repeat = first, repeat
        self.until = {}          # classic mode: key -> held until
        self.real = set()        # kitty mode
        self.hits = []
        self.now = 0.0

    def feed(self, name, kind, now):
        self.now = now
        if kind == "release":
            self.real.discard(name)
            self.until.pop(name, None)
            return
        if kind == "press":
            self.hits.append(name)
        if self.kitty:
            self.real.add(name)
            return
        opp = self.OPPOSITE.get(name)
        if opp:
            self.until.pop(opp, None)
        held_now = self.until.get(name, 0) > now
        self.until[name] = now + (self.repeat if held_now else self.first)

    def tick(self, now):
        self.now = now

    def down(self, *names):
        if self.kitty:
            return any(n in self.real for n in names)
        return any(self.until.get(n, 0) > self.now for n in names)

    def hit(self, *names):
        return any(n in self.hits for n in names)

    def take_hits(self):
        h, self.hits = self.hits, []
        return h

    def clear(self):
        self.until.clear()
        self.real.clear()
        self.hits = []


# =============================================================================================
# Canvas: two pixels per character cell (upper half block), text drawn on top
# =============================================================================================
class Canvas:
    def __init__(self, cols, rows, bg=(8, 8, 14)):
        self.cols, self.rows = cols, rows
        self.W, self.H = cols, rows * 2
        self.px = [[bg] * self.W for _ in range(self.H)]
        self.text = {}

    def set(self, x, y, c):
        x, y = int(x), int(y)
        if 0 <= x < self.W and 0 <= y < self.H:
            self.px[y][x] = c

    def rect(self, x, y, w, h, c):
        x0, y0 = max(0, int(x)), max(0, int(y))
        x1, y1 = min(self.W, int(x + w)), min(self.H, int(y + h))
        if x1 <= x0:
            return
        for yy in range(y0, y1):
            self.px[yy][x0:x1] = [c] * (x1 - x0)

    def frame(self, x, y, w, h, c):
        self.rect(x, y, w, 1, c)
        self.rect(x, y + h - 1, w, 1, c)
        self.rect(x, y, 1, h, c)
        self.rect(x + w - 1, y, 1, h, c)

    def vgradient(self, top, bottom):
        for y in range(self.H):
            self.px[y] = [mix(top, bottom, y / max(1, self.H - 1))] * self.W

    def line(self, x0, y0, x1, y1, c):
        x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        W, H, px = self.W, self.H, self.px
        while True:
            if 0 <= x0 < W and 0 <= y0 < H:
                px[y0][x0] = c
            if x0 == x1 and y0 == y1:
                return
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def poly(self, pts, c):
        """Fill a convex polygon given as [(x, y), ...] in pixel coordinates."""
        ys = [p[1] for p in pts]
        y0, y1 = max(0, int(min(ys) + 0.5)), min(self.H - 1, int(max(ys) - 0.5))
        n = len(pts)
        px = self.px
        for y in range(y0, y1 + 1):
            yc = y + 0.5
            lo, hi = 1e9, -1e9
            for i in range(n):
                ax, ay = pts[i]
                bx, by = pts[(i + 1) % n]
                if (ay <= yc < by) or (by <= yc < ay):
                    x = ax + (yc - ay) * (bx - ax) / (by - ay)
                    lo, hi = min(lo, x), max(hi, x)
            if hi < lo:
                continue
            a, b = max(0, int(lo + 0.5)), min(self.W, int(hi + 0.5))
            if b > a:
                px[y][a:b] = [c] * (b - a)

    def put(self, col, row, s, fg=(230, 230, 236), bg=None):
        """Text at a character cell. Without bg the text sits on whatever pixels are underneath."""
        if not 0 <= row < self.rows:
            return
        for i, ch in enumerate(s):
            x = col + i
            if 0 <= x < self.cols:
                self.text[(x, row)] = (ch, fg, bg)

    def center(self, row, s, fg=(230, 230, 236), bg=None, col0=0, width=None):
        width = self.cols if width is None else width
        self.put(col0 + max(0, (width - len(s)) // 2), row, s, fg, bg)

    def box(self, col, row, lines, fg=(236, 236, 242), bg=(20, 22, 38), pad=2):
        w = max(len(l) for l in lines) + pad * 2
        for j, l in enumerate([""] + list(lines) + [""]):
            self.put(col, row + j, (" " * pad + l).ljust(w), fg, bg)

    def emit(self, true=None):
        """The whole frame as one string of escape codes (synchronised update)."""
        if true is None:
            true = os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")
        if true:
            fgs, bgs = (lambda c: "\x1b[38;2;%d;%d;%dm" % c), (lambda c: "\x1b[48;2;%d;%d;%dm" % c)
        else:
            fgs, bgs = (lambda c: "\x1b[38;5;%dm" % x256(c)), (lambda c: "\x1b[48;5;%dm" % x256(c))
        out = ["\x1b[?2026h\x1b[H"]
        px, text = self.px, self.text
        for j in range(self.rows):
            top, bot = px[2 * j], px[2 * j + 1]
            lt = lb = None
            line = []
            for i in range(self.cols):
                t, b = top[i], bot[i]
                tx = text.get((i, j))
                if tx:
                    ch, f, bg = tx
                    if bg is None:
                        bg = mix(t, b, 0.5)
                    if f != lt:
                        line.append(fgs(f))
                        lt = f
                    if bg != lb:
                        line.append(bgs(bg))
                        lb = bg
                    line.append(ch)
                    continue
                if SOLID_PIXELS and t != b:
                    c = solid_cell(t, b)
                    if c is not None:
                        t = b = c
                if t == b:
                    if b != lb:
                        line.append(bgs(b))
                        lb = b
                    line.append(" ")
                    continue
                if t != lt:
                    line.append(fgs(t))
                    lt = t
                if b != lb:
                    line.append(bgs(b))
                    lb = b
                line.append("▀")
            out.append("".join(line))
            out.append("\x1b[0m" + ("\r\n" if j < self.rows - 1 else ""))
        out.append("\x1b[?2026l")
        return "".join(out)


# =============================================================================================
# A chunky 5x5 block font for titles
# =============================================================================================
FONT = {
    "A": [".###.", "#...#", "#####", "#...#", "#...#"],
    "B": ["####.", "#...#", "####.", "#...#", "####."],
    "C": [".####", "#....", "#....", "#....", ".####"],
    "D": ["####.", "#...#", "#...#", "#...#", "####."],
    "E": ["#####", "#....", "####.", "#....", "#####"],
    "F": ["#####", "#....", "####.", "#....", "#...."],
    "G": [".####", "#....", "#..##", "#...#", ".###."],
    "H": ["#...#", "#...#", "#####", "#...#", "#...#"],
    "I": ["#####", "..#..", "..#..", "..#..", "#####"],
    "K": ["#...#", "#..#.", "###..", "#..#.", "#...#"],
    "L": ["#....", "#....", "#....", "#....", "#####"],
    "M": ["#...#", "##.##", "#.#.#", "#...#", "#...#"],
    "N": ["#...#", "##..#", "#.#.#", "#..##", "#...#"],
    "O": [".###.", "#...#", "#...#", "#...#", ".###."],
    "P": ["####.", "#...#", "####.", "#....", "#...."],
    "R": ["####.", "#...#", "####.", "#..#.", "#...#"],
    "S": [".####", "#....", ".###.", "....#", "####."],
    "T": ["#####", "..#..", "..#..", "..#..", "..#.."],
    "U": ["#...#", "#...#", "#...#", "#...#", ".###."],
    "V": ["#...#", "#...#", "#...#", ".#.#.", "..#.."],
    "W": ["#...#", "#...#", "#.#.#", "##.##", "#...#"],
    "Y": ["#...#", ".#.#.", "..#..", "..#..", "..#.."],
    " ": [".....", ".....", ".....", ".....", "....."],
}


def title_width(text, k):
    return len(text) * 6 * k - k


def draw_title(cv, text, x, y, k, colors, bevel=True):
    """Block letters, each font pixel a k x k block; colors cycles per letter."""
    for n, ch in enumerate(text):
        glyph = FONT.get(ch.upper(), FONT[" "])
        c = colors[n % len(colors)]
        for gy, row in enumerate(glyph):
            for gx, bit in enumerate(row):
                if bit == "#":
                    bx, by = x + (n * 6 + gx) * k, y + gy * k
                    if bevel and k >= 4:
                        cv.rect(bx, by, k, k, shade(c, 0.62))
                        cv.rect(bx, by, k - 1, k - 1, shade(c, 1.18))
                        cv.rect(bx + 1, by + 1, k - 2, k - 2, c)
                    else:
                        cv.rect(bx, by, k, k, c)


# =============================================================================================
# High scores
# =============================================================================================
def load_scores():
    try:
        with open(SCORES_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def best(game, mode):
    return load_scores().get(game, {}).get(mode)


def submit(game, mode, value, lower_is_better=False):
    """Store value if it beats the record. Returns True for a new record."""
    data = load_scores()
    g = data.setdefault(game, {})
    old = g.get(mode)
    if old is None or (value < old if lower_is_better else value > old):
        g[mode] = value
        try:
            with open(SCORES_PATH, "w") as f:
                json.dump(data, f, indent=1)
        except OSError:
            pass
        return True
    return False


# =============================================================================================
# The keys every game shares: Esc / P pause menu, Q quits from it, ? help, Enter / Space confirm
# =============================================================================================
PAUSE_LINES = ["P A U S E D", "", "Esc / P / Enter   continue", "?                 help", "M                 sound on / off",
               "Q                 quit to the menu"]


def shared_key(k, paused, pause_keys=("esc", "p", "q")):
    """What a key means for the shared in-game controls: 'pause', 'resume', 'quit', 'help',
    'sound' (M in the pause menu: sound on / off), 'eaten' (swallowed while paused) or None (the game's own key)."""
    if paused:
        if k in ("esc", "p", "enter", " "):
            return "resume"
        if k == "q":
            return "quit"
        if k == "?":
            return "help"
        if k == "m":
            return "sound"
        return "eaten"
    if k in pause_keys:
        return "pause"
    if k == "?":
        return "help"
    return None


def overlay(cv, lines, fg=(240, 240, 246), bg=(22, 22, 42)):
    """A centred text box (pause menu, help) on top of a canvas."""
    w = max(len(l) for l in lines) + 4
    cv.box(max(0, (cv.cols - w) // 2), max(0, cv.rows // 2 - len(lines) // 2 - 1), list(lines), fg, bg)


# =============================================================================================
# Auto mode: the game plays itself (every game has it on its title screen); the viewer can pause, change the
# speed or stop. High scores are never recorded in auto mode.
# =============================================================================================
# Pixel art at any size: a bigger window gets finer art, not just bigger blocks
# =============================================================================================
def scale2x(grid):
    """One Scale2x (EPX) step on a grid of any comparable cells (letters, colours, None): edges and diagonals
    come out smooth instead of as staircases of fat blocks."""
    h, w = len(grid), len(grid[0]) if grid else 0
    out = []
    for y in range(h):
        row, up, dn = grid[y], grid[y - 1] if y > 0 else grid[y], grid[y + 1] if y < h - 1 else grid[y]
        r0, r1 = [], []
        for x in range(w):
            p = row[x]
            a, d = up[x], dn[x]
            c = row[x - 1] if x > 0 else p
            b = row[x + 1] if x < w - 1 else p
            if c != b and a != d:
                r0 += [c if c == a else p, b if a == b else p]
                r1 += [c if d == c else p, b if b == d else p]
            else:
                r0 += [p, p]
                r1 += [p, p]
        out.append(r0)
        out.append(r1)
    return out


def scale_art(grid, ow, oh):
    """Pixel art (rows of cells) resized to ow x oh: smoothed with Scale2x as often as it takes to reach the
    size, then sampled down. Below the source size it is a plain nearest-neighbour sample."""
    g = [list(r) for r in grid]
    h, w = len(g), len(g[0]) if g else 0
    while w and h and (w < ow or h < oh) and w * h < 1 << 16:
        g = scale2x(g)
        h, w = len(g), len(g[0])
    return [[g[min(h - 1, int((y + 0.5) * h / oh))][min(w - 1, int((x + 0.5) * w / ow))] for x in range(ow)]
            for y in range(oh)]


# =============================================================================================
AUTO_LABEL = "Auto mode"          # the title-menu entry, the same wording in every game
AUTO_BG = (236, 180, 70)
AUTO_HELP = ["AUTO MODE - the game plays itself", "", "Space            pause / continue", "+ / -            faster / slower",
             "M                sound on / off", "Esc / Q          stop (back to the title)", "?                this help"]


class AutoMode:
    """Speed, pause and stop for auto mode.

        auto = AutoMode()
        for k in term.keys():
            a = auto.key(k)        # 'stop', 'sound', 'help', True (used) or None (not an auto-mode key)
        sim_dt = auto.scale(dt)    # 0 while paused, dt * speed otherwise (step the game with it)
        auto.banner(cv)            # the amber AUTO bar (default: on the last row)
    """
    SPEEDS = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)

    def __init__(self, speed=1.0):
        self.i = self.SPEEDS.index(speed) if speed in self.SPEEDS else 2
        self.paused = False
        self.help = False

    @property
    def speed(self):
        return self.SPEEDS[self.i]

    def key(self, k):
        if self.help:                       # any key closes the help
            self.help = False
            return True
        if k in ("esc", "q"):
            return "stop"
        if k in (" ", "p", "enter"):
            self.paused = not self.paused
            return True
        if k in ("+", "=", "right", "up"):
            self.i = min(len(self.SPEEDS) - 1, self.i + 1)
            return True
        if k in ("-", "_", "left", "down"):
            self.i = max(0, self.i - 1)
            return True
        if k == "m":
            return "sound"
        if k == "?":
            self.help = True
            return "help"
        return None

    def scale(self, dt):
        return 0.0 if self.paused or self.help else dt * self.speed

    def steps(self, dt, step):
        """How many fixed simulation steps of length step to run for a real frame of dt (keeps a remainder)."""
        self._acc = getattr(self, "_acc", 0.0) + self.scale(dt)
        n = int(self._acc / step)
        self._acc -= n * step
        return min(n, int(8 * self.speed) + 1)

    def text(self, extra=""):
        sp = ("x%g" % self.speed).replace("x0.", "x.")
        state = "PAUSED" if self.paused else sp
        return " AUTO %s %s  Space pause   +/- speed   Esc stop " % (state, (" " + extra) if extra else "")

    def banner(self, cv, row=None, extra=""):
        row = cv.rows - 1 if row is None else row
        t = self.text(extra)
        if len(t) > cv.cols:
            t = (" AUTO %s  Esc stop " % ("PAUSED" if self.paused else ("x%g" % self.speed)))[:cv.cols]
        cv.put(0, row, " " * cv.cols, (24, 16, 6), shade(AUTO_BG, 0.55))
        cv.put(max(0, (cv.cols - len(t)) // 2), row, t, (20, 14, 4), AUTO_BG)
        if self.help:
            overlay(cv, AUTO_HELP)


# =============================================================================================
# The shared title screen: every game puts its own live scene behind the same layout
# =============================================================================================
TITLE_DIM = (6, 6, 14)
PANEL_BG = (14, 14, 28)
PANEL_FG = (220, 220, 232)
GOLD_TEXT = (240, 210, 120)
FOOTER_BG = (12, 10, 22)
FOOTER_FG = (150, 154, 184)
TITLE_LONGEST = 11   # LIGHTKEEPER: every title uses the letter size that fits the longest name
ACCENTS = {  # (top, bottom) of each game's title gradient
    "HOVERDRIFT": ((150, 215, 255), (70, 140, 230)),
    "EMBERFALL": ((255, 215, 130), (205, 95, 45)),
    "BLOCKFIRE": ((255, 165, 70), (215, 50, 40)),
    "DEEPCALL": ((120, 240, 255), (40, 160, 210)),
    "LIGHTKEEPER": ((255, 232, 150), (235, 165, 65)),
    "STACKFALL": ((140, 235, 120), (60, 170, 95)),
    "DEPTHWELL": ((165, 160, 255), (105, 90, 225)),
    "SKYSHOT": ((255, 140, 170), (200, 60, 110)),
    "NIGHTDRIVE": ((255, 120, 230), (130, 70, 255)),
    "ORBITAL": ((200, 240, 255), (120, 170, 255)),
    "LEAFLING": ((250, 224, 110), (118, 196, 58)),
    "GLIMMER": ((255, 236, 140), (240, 150, 60)),
    "SPOREFIELD": ((200, 255, 140), (120, 70, 200)),
    "SCAFFOLD": ((255, 196, 90), (220, 80, 40)),
    "VOIDLANCE": ((140, 230, 255), (150, 80, 255)),
    "SHATTERWICK": ((255, 222, 130), (96, 160, 246)),
    "WARDSTONE": ((246, 224, 150), (64, 168, 146)),
    "CLATTERBELL": ((255, 226, 140), (226, 92, 70)),
    "CAIRNWARD": ((246, 226, 150), (110, 176, 120)),
    "GEMBURROW": ((255, 214, 120), (176, 104, 220)),
    "WEFTWAR": ((255, 214, 110), (236, 70, 120)),
    "PEBBLEPUTT": ((255, 196, 150), (70, 185, 110)),
    "THATCHWOLD": ((250, 222, 130), (150, 176, 74)),
    "FENMARK": ((236, 228, 150), (86, 170, 150)),
}


def block_title(cv, text, x, y, k, top, bottom):
    """Block letters with a soft shadow and a top-to-bottom gradient."""
    shadow = (0, 0, 0)
    for n, ch in enumerate(text):
        glyph = FONT.get(ch.upper(), FONT[" "])
        for gy, row in enumerate(glyph):
            c = mix(top, bottom, gy / 4)
            for gx, bit in enumerate(row):
                if bit == "#":
                    bx, by = x + (n * 6 + gx) * k, y + gy * k
                    if k >= 2:
                        cv.rect(bx + 1, by + 1, k, k, mix(cv.px[min(cv.H - 1, by + 1)][min(cv.W - 1, bx + 1)], shadow, 0.7))
            for gx, bit in enumerate(row):
                if bit == "#":
                    cv.rect(x + (n * 6 + gx) * k, y + gy * k, k, k, c)


def title_screen(cv, name, tagline, items, sel, best=None, extra=(), keys=None, help_lines=None, show_help=False,
                 dim=0.55):
    """Draw the ASCII ARCADE title layout over the game's scene already painted into cv.

    items: menu lines (sel is highlighted); extra: dim lines under the items inside the panel;
    best: a line in gold under the panel; keys: the footer's key hints."""
    cols, rows = cv.cols, cv.rows
    if dim:
        for y in range(cv.H):
            cv.px[y] = [mix(c, TITLE_DIM, dim) for c in cv.px[y]]
    top, bottom = ACCENTS.get(name, ((240, 240, 250), (160, 160, 190)))
    need = len(items) * 2 + len(extra) + 9            # rows below the title
    k = 2 if cols >= title_width("X" * TITLE_LONGEST, 2) + 4 and (5 * 2 + 6) // 2 + need <= rows else 1
    y0 = 3
    block_title(cv, name, (cols - title_width(name, k)) // 2, y0, k, top, bottom)
    row = (y0 + 5 * k) // 2 + 2
    cv.center(row, " %s " % tagline, (215, 215, 230), PANEL_BG)   # backed, so it reads over any scene
    gap = 2 if row + 3 + len(items) * 2 + len(extra) + 4 < rows else 1
    w = max([len(s) for s in items] + [len(s) for s in extra] + [20]) + 8
    x0 = max(0, (cols - w) // 2)
    r = row + 2
    height = len(items) * gap + len(extra) + (1 if gap == 2 else 0) + 1
    for j in range(height):
        cv.put(x0, r + j, " " * w, PANEL_FG, PANEL_BG)
    for i, s in enumerate(items):
        y = r + 1 + i * gap if gap == 2 else r + i
        if i == sel:
            cv.put(x0 + 2, y, (" > " + s).ljust(w - 4), (14, 14, 20), mix(top, bottom, 0.3))
        else:
            cv.put(x0 + 2, y, ("   " + s).ljust(w - 4), PANEL_FG, PANEL_BG)
    ey = r + (1 + len(items) * gap if gap == 2 else len(items))
    for j, s in enumerate(extra):
        cv.put(x0 + 2, ey + j, ("   " + s).ljust(w - 4), (150, 154, 184), PANEL_BG)
    if best:
        cv.center(r + height + 1, best, GOLD_TEXT)
    footer(cv, keys or "Up/Down choose   Enter start   ? help   Esc back")
    if show_help and help_lines:
        overlay(cv, help_lines)


def footer(cv, keys):
    """The bottom bar every title screen shares."""
    cols, r = cv.cols, cv.rows - 1
    label = " ASCII ARCADE "
    cv.put(0, r, " " * cols, FOOTER_FG, FOOTER_BG)
    cv.put(0, r, label, (14, 14, 20), (200, 200, 215))
    room = cols - len(label) - 1
    hints = [h for h in re.split(r"\s{3,}", keys.strip()) if h]
    while hints and len("   ".join(hints)) + 2 > room:   # drop whole hints from the end, never cut one
        hints.pop()
    k = " %s " % "   ".join(hints) if hints else ""
    if k:
        cv.put(cols - len(k), r, k, FOOTER_FG, FOOTER_BG)
