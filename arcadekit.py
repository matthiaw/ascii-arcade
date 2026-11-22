"""arcadekit - the little shared toolkit of the ASCII ARCADE games.

Raw terminal input, a half-block pixel canvas with text overlays, a chunky block font and a high score file.
Pure Python 3, no dependencies (macOS / Linux).
"""
import json
import os
import select
import sys
import termios
import tty

SCORES_PATH = os.path.expanduser("~/.ascii_arcade_scores.json")


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
PAUSE_LINES = ["P A U S E D", "", "Esc / P / Enter   continue", "?                 help", "Q                 quit to the menu"]


def shared_key(k, paused, pause_keys=("esc", "p", "q")):
    """What a key means for the shared in-game controls: 'pause', 'resume', 'quit', 'help',
    'eaten' (swallowed while paused) or None (the game's own key)."""
    if paused:
        if k in ("esc", "p", "enter", " "):
            return "resume"
        if k == "q":
            return "quit"
        if k == "?":
            return "help"
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
    cv.center(row, tagline, (205, 205, 220))
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
    k = " %s " % keys
    cv.put(max(len(label) + 1, cols - len(k)), r, k[:max(0, cols - len(label) - 1)], FOOTER_FG, FOOTER_BG)
