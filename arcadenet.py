#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""LAN play for the ASCII ARCADE: one player hosts, the others join over the LAN or the WLAN.

The host's computer runs the game. Every player who joins sends the keys they press and gets back the picture,
drawn by the host at the size of their own window, plus the sounds to play. So a game needs only its own match
loop with a few extra lines: whose keys are whose, and the picture for each window (see Server.inputs and
Server.send_frames). The join screen finds games in the same network by themselves: the host shouts a small UDP
beacon once a second.

TCP port 47290 (or the next free one up to 47299), UDP port 47291 for finding games. JSON lines both ways;
nothing received is ever run, pictures are checked before they are drawn.

Self-test:  python3 arcadenet.py --selftest
"""
import base64
import json
import socket
import time
import zlib
from collections import deque
from itertools import chain

import arcadekit
from arcadekit import Canvas, footer, mix, overlay

try:
    from arcadesound import Sound, load_settings, save_settings
except ImportError:                     # pragma: no cover - arcadesound ships with the arcade
    Sound = None

    def load_settings():
        return {}

    def save_settings(**changes):
        pass

PORT, BEACON_PORT = 47290, 47291
FPS = 30                                # pictures per second for each player who joined
MAX_COLS, MAX_ROWS = 400, 160           # bigger windows get a picture of this size
DIM = (6, 6, 14)


# =============================================================================================
# The pipes: names, a non-blocking JSON-line connection, the listening socket with its beacon, the finder
# =============================================================================================
def clean_name(s, default="PLAYER"):
    s = "".join(c for c in str(s or "").upper() if c.isalnum() or c in " -_")[:8].strip()
    return s or default


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))           # UDP connect sends nothing; it only picks the way out
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class Link:
    """A TCP connection that sends and receives JSON lines without ever blocking the game."""
    LIMIT = 1 << 20

    def __init__(self, sock):
        sock.setblocking(False)
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        self.sock, self.inb, self.out, self.closed = sock, b"", b"", False

    def send(self, obj):
        self.send_raw((json.dumps(obj, separators=(",", ":")) + "\n").encode())

    def send_raw(self, data):
        if self.closed:
            return
        self.out += data
        self.flush()

    def flush(self):
        while self.out and not self.closed:
            try:
                n = self.sock.send(self.out)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                self.closed = True
                break
            self.out = self.out[n:]
        if len(self.out) > self.LIMIT:
            self.closed = True

    def recv(self):
        msgs = []
        while not self.closed:
            try:
                data = self.sock.recv(65536)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                self.closed = True
                break
            if not data:
                self.closed = True
                break
            self.inb += data
            if len(self.inb) > self.LIMIT:
                self.closed = True
        while b"\n" in self.inb:
            line, self.inb = self.inb.split(b"\n", 1)
            try:
                m = json.loads(line.decode("utf-8", "ignore"))
            except ValueError:
                continue
            if isinstance(m, dict):
                msgs.append(m)
        return msgs

    def close(self):
        self.flush()
        self.closed = True
        try:
            self.sock.close()
        except OSError:
            pass


class Host:
    """The listening socket and the beacon."""

    def __init__(self, game, proto, port=PORT, beacon=True):
        self.game, self.proto = game, proto
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        for p in ([0] if port == 0 else range(port, port + 10)):
            try:
                self.srv.bind(("", p))
                break
            except OSError:
                continue
        else:
            self.srv.close()
            raise OSError("no free port from %d on" % port)
        self.port = self.srv.getsockname()[1]
        self.srv.listen(8)
        self.srv.setblocking(False)
        self.links = []
        self.ip = local_ip()
        self.udp = None
        if beacon:
            try:
                self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                self.udp.setblocking(False)
            except OSError:
                self.udp = None
        self.beacon_at = 0.0

    def accept(self):
        while True:
            try:
                s, addr = self.srv.accept()
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                break
            ln = Link(s)
            ln.addr, ln.hello, ln.since = addr[0], False, time.time()
            self.links.append(ln)

    def beacon(self, now, info):
        if not self.udp or now < self.beacon_at:
            return
        self.beacon_at = now + 1.0
        data = json.dumps(dict(info, g=self.game, p=self.proto, port=self.port)).encode()
        for to in ("<broadcast>", "255.255.255.255"):
            try:
                self.udp.sendto(data, (to, BEACON_PORT))
                break
            except OSError:
                continue

    def close(self):
        for ln in self.links:
            ln.close()
        self.links = []
        for s in (self.srv, self.udp):
            if s:
                try:
                    s.close()
                except OSError:
                    pass


class Finder:
    """Listens for beacons of one game: hosts[(ip, port)] = dict(name, n, m, open, seen)."""

    def __init__(self, game, proto, port=BEACON_PORT):
        self.game, self.proto = game, proto
        self.hosts = {}
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except OSError:
                    pass
            self.sock.bind(("", port))
            self.sock.setblocking(False)
        except OSError:
            self.sock = None

    def poll(self, now):
        while self.sock:
            try:
                data, addr = self.sock.recvfrom(4096)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                break
            try:
                m = json.loads(data.decode("utf-8", "ignore"))
                if m.get("g") != self.game or m.get("p") != self.proto:
                    continue
                port = int(m["port"])
                self.hosts[(addr[0], port)] = dict(name=clean_name(m.get("name"), "HOST"),
                                                   n=max(0, min(8, int(m.get("n", 1)))),
                                                   m=max(1, min(8, int(m.get("m", 4)))),
                                                   open=bool(m.get("open")), seen=now)
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
        for k in [k for k, v in self.hosts.items() if now - v["seen"] > 4.0]:
            del self.hosts[k]
        return sorted(self.hosts.items(), key=lambda kv: (not kv[1]["open"], kv[1]["name"], kv[0]))

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None


# =============================================================================================
# Pictures over the wire: the canvas pixels as zlib-packed RGB, the text cells as a list
# =============================================================================================
def _byte(v):
    try:
        return max(0, min(255, int(v)))
    except (TypeError, ValueError):
        return 0


def _rgb(c):
    if isinstance(c, (list, tuple)) and len(c) == 3:
        return tuple(_byte(v) for v in c)
    return None


def pack_canvas(cv):
    try:
        flat = bytes(chain.from_iterable(chain.from_iterable(cv.px)))
    except (TypeError, ValueError):                       # floats or odd values somewhere: the slow way
        flat = bytes(_byte(v) for row in cv.px for c in row for v in c)
    tx = [[x, y, ch, list(fg), list(bg) if bg is not None else None]
          for (x, y), (ch, fg, bg) in cv.text.items()]
    return {"c": cv.cols, "r": cv.rows, "px": base64.b64encode(zlib.compress(flat, 1)).decode(), "tx": tx}


def unpack_canvas(m):
    """A canvas from a received picture, or None when anything about it is off."""
    try:
        cols, rows = int(m["c"]), int(m["r"])
        if not (1 <= cols <= MAX_COLS and 1 <= rows <= MAX_ROWS):
            return None
        need = cols * rows * 2 * 3
        d = zlib.decompressobj()
        flat = d.decompress(base64.b64decode(m["px"], validate=True), need + 1)
        if len(flat) != need:
            return None
        cv = Canvas(cols, rows)
        W = cols * 3
        cv.px = [list(zip(flat[o:o + W:3], flat[o + 1:o + W:3], flat[o + 2:o + W:3])) for o in range(0, need, W)]
        for e in m.get("tx", [])[:cols * rows]:
            x, y, ch, fg, bg = e
            if isinstance(ch, str) and len(ch) == 1 and isinstance(x, int) and isinstance(y, int) \
                    and 0 <= x < cols and 0 <= y < rows and ch.isprintable():
                f = _rgb(fg)
                if f is not None:
                    cv.text[(x, y)] = (ch, f, _rgb(bg) if bg is not None else None)
        return cv
    except (KeyError, TypeError, ValueError, zlib.error, base64.binascii.Error):
        return None


def fit(cv, cols, rows):
    """cv drawn into a canvas of cols x rows: centred, cut where it is bigger."""
    if cv.cols == cols and cv.rows == rows:
        return cv
    out = Canvas(cols, rows, DIM)
    ox, oy = (cols - cv.cols) // 2, (rows - cv.rows) // 2
    for y in range(out.H):
        sy = y - oy * 2
        if 0 <= sy < cv.H:
            a, b = max(0, ox), min(cols, ox + cv.cols)
            if b > a:
                out.px[y][a:b] = cv.px[sy][a - ox:b - ox]
    for (x, y), v in cv.text.items():
        if 0 <= x + ox < cols and 0 <= y + oy < rows:
            out.text[(x + ox, y + oy)] = v
    return out


# =============================================================================================
# What a game tells the LAN screens about itself
# =============================================================================================
class LanGame:
    """game: the short name (also in the beacon), title: shown on the screens, proto: raise it when the keys or
    the pictures change, players: (fewest, most) people, local: how many may share one keyboard, size: the
    smallest window, sound: the game's Sound bank, help: help(kitty) -> lines, backdrop: backdrop(cols, rows, dt)
    -> Canvas behind the screens, info: info() -> the line about the settings in the lobby, match: match(term,
    srv) -> 'lobby' or 'quit', the host's own match loop."""

    def __init__(self, game, title, match, backdrop, help=None, info=None, players=(2, 2), local=1,
                 size=(60, 22), sound=None, proto=1, seat_word="player"):
        self.game, self.title, self.match, self.backdrop = game, title, match, backdrop
        self.help = help or (lambda kitty=True: [title])
        self.info = info or (lambda: "")
        self.players, self.local, self.size, self.sound, self.proto = players, local, size, sound, proto
        self.seat_word = seat_word


def play_sound(spec, names):
    if spec.sound is None:
        return
    for n in dict.fromkeys(names):
        if isinstance(n, str) and n in getattr(spec.sound, "bank", {}):
            spec.sound.play(n)


def toggle_sound(spec):
    if spec.sound is not None and spec.sound.toggle() and "sound_on" in spec.sound.bank:
        spec.sound.play("sound_on")


def sound_label(spec):
    return spec.sound.label() if spec.sound is not None else "Sound: none"


def lan_name():
    v = load_settings().get("lan_name")
    return clean_name(v) if isinstance(v, str) else "PLAYER"


# =============================================================================================
# The host's side
# =============================================================================================
class Remote:
    """One computer that joined: its keys since the last frame and the window its picture is drawn for."""

    def __init__(self, link, name, n, kitty, size):
        self.link, self.name, self.n, self.kitty, self.size = link, name, n, kitty, size
        self.events, self.cleared = [], False
        self.frame_at, self.last = 0.0, None


class Server:
    """The host: who sits at which seat (the lobby), and once started their keys in and the pictures out.
    seats[i] = dict(name, kind 'here' | 'lan' | 'gone', remote, p): p is the player's number at that keyboard."""

    def __init__(self, spec, name, local=1, port=PORT, beacon=True):
        self.spec = spec
        self.name = clean_name(name)
        self.net = Host(spec.game, spec.proto, port, beacon)
        self.port, self.ip = self.net.port, self.net.ip
        self.seats = [dict(name=self.name, kind="here", remote=None, p=0)]
        for p in range(1, max(1, min(local, spec.local))):
            self.seats.append(dict(name=(self.name[:6] + " %d" % (p + 1)), kind="here", remote=None, p=p))
        self.remotes = {}                    # link -> Remote
        self.playing = False
        self.lobby_at = 0.0
        self.notes = deque(maxlen=3)
        self.note_at = 0.0
        self.sounds, self.left = [], []
        self.taps = None

    @property
    def most(self):
        return self.spec.players[1]

    def note(self, s):
        self.notes.append(s)
        self.note_at = time.time()

    def recent(self, secs=4.0):
        """The last note while it is fresh (for a line in the game), else None."""
        return self.notes[-1] if self.notes and time.time() - self.note_at < secs else None

    def here(self):
        return [i for i, s in enumerate(self.seats) if s["kind"] == "here"]

    def humans(self):
        return sum(1 for s in self.seats if s["kind"] in ("here", "lan"))

    def remote_count(self):
        return sum(1 for s in self.seats if s["kind"] == "lan")

    def ready(self):
        return self.humans() >= self.spec.players[0]

    def poll(self, now):
        self.net.accept()
        for ln in list(self.net.links):
            for m in ln.recv():
                self.handle(ln, m)
            if not ln.hello and time.time() - ln.since > 5:
                ln.closed = True
            ln.flush()
            if ln.closed:
                self.drop_link(ln)
        self.net.beacon(now, dict(name=self.name, n=len(self.seats), m=self.most,
                                  open=not self.playing and len(self.seats) < self.most))
        if not self.playing and now >= self.lobby_at:
            self.send_lobby()
            self.lobby_at = now + 1.0

    def unique(self, name):
        taken = {s["name"] for s in self.seats}
        if name not in taken:
            return name
        for k in range(2, 10):
            cand = "%s %d" % (name[:6], k)
            if cand not in taken:
                return cand
        return name

    def handle(self, ln, m):
        t = m.get("t")
        if t == "hello" and not ln.hello:
            ln.hello = True
            why = None
            if m.get("p") != self.spec.proto or m.get("g") not in (None, self.spec.game):
                why = "the host runs another version of %s" % self.spec.title
            elif self.playing:
                why = "that game has already started"
            elif len(self.seats) >= self.most:
                why = "that game is full (%d players)" % self.most
            if why:
                ln.send({"t": "no", "why": why})
                ln.closed = True
                return
            n = max(1, min(int(m.get("n", 1)) if isinstance(m.get("n"), int) else 1, self.spec.local,
                           self.most - len(self.seats)))
            name = clean_name(m.get("name"))
            r = Remote(ln, name, n, bool(m.get("kitty")), self.size_of(m.get("size")))
            self.remotes[ln] = r
            for p in range(n):
                self.seats.append(dict(name=self.unique(name if p == 0 else name[:6] + " %d" % (p + 1)),
                                       kind="lan", remote=r, p=p))
            ln.send({"t": "welcome", "you": self.you(r)})
            self.note("%s joined" % name)
            self.sounds.append("join")
            self.send_lobby()
            return
        r = self.remotes.get(ln)
        if r is None:
            return
        if t == "sz":
            r.size = self.size_of(m.get("size"))
        elif t == "k":
            if m.get("clr"):
                r.events, r.cleared = [], True
            for e in (m.get("e") or [])[:64]:
                if isinstance(e, list) and len(e) == 2 and isinstance(e[0], str) and len(e[0]) <= 12 \
                        and e[1] in ("press", "repeat", "release") and len(r.events) < 256:
                    r.events.append((e[0], e[1]))

    def size_of(self, v):
        try:
            c, r = int(v[0]), int(v[1])
        except (TypeError, ValueError, IndexError):
            c, r = self.spec.size
        return max(self.spec.size[0], min(MAX_COLS, c)), max(self.spec.size[1], min(MAX_ROWS, r))

    def you(self, r):
        return [i for i, s in enumerate(self.seats) if s["remote"] is r]

    def drop_link(self, ln):
        if ln in self.net.links:
            self.net.links.remove(ln)
        ln.close()
        r = self.remotes.pop(ln, None)
        if r is None:
            return
        mine = self.you(r)
        if not self.playing:
            self.seats = [s for s in self.seats if s["remote"] is not r]
            self.note("%s left" % r.name)
            self.send_lobby()
        else:
            for i in mine:
                self.seats[i].update(kind="gone", remote=None)
                self.left.append(i)
            self.note("%s left - the computer plays on" % r.name)
        self.sounds.append("leave")

    def seat_rows(self):
        return [[s["name"], s["kind"]] for s in self.seats]

    def send_lobby(self):
        base = {"t": "lobby", "seats": self.seat_rows(), "most": self.most, "info": str(self.spec.info())[:70]}
        for ln, r in self.remotes.items():
            if ln.hello:
                ln.send(dict(base, you=self.you(r)))

    # --- the match -------------------------------------------------------------------------
    def start(self):
        self.playing = True
        self.left = []
        for r in self.remotes.values():
            r.events, r.cleared, r.last, r.frame_at = [], False, None, 0.0
            r.link.send({"t": "start", "you": self.you(r)})
        self.taps = []
        if Sound is not None:
            Sound.tap = self.taps

    def inputs(self):
        """[(remote, [seat numbers], [(key, kind), ...], cleared)] since the last call, for every computer that
        joined and still plays."""
        out = []
        for r in self.remotes.values():
            seats = [i for i in self.you(r) if self.seats[i]["kind"] == "lan"]
            if seats:
                out.append((r, seats, r.events, r.cleared))
            r.events, r.cleared = [], False
        return out

    def take_left(self):
        """Seats whose player left since the last call (the game hands them to the computer)."""
        out, self.left = self.left, []
        return out

    def min_size(self, cols, rows):
        """The smallest of the host's window and the windows of everyone who joined."""
        for r in self.remotes.values():
            cols, rows = min(cols, r.size[0]), min(rows, r.size[1])
        return cols, rows

    def send_frames(self, now, draw):
        """draw(cols, rows, seats) -> Canvas: each player who joined gets the picture for their window, up to FPS
        times a second; a slow link misses pictures instead of falling behind. The sounds go out at once."""
        snd = []
        if self.taps:
            snd = list(dict.fromkeys(self.taps))[-16:]
            del self.taps[:]
        made = {}
        for ln, r in list(self.remotes.items()):
            if not ln.hello or not any(self.seats[i]["kind"] == "lan" for i in self.you(r)):
                continue
            if snd:
                ln.send({"t": "s", "n": snd})
            if now - r.frame_at < 1 / FPS or len(ln.out) > 96 * 1024:
                continue
            r.frame_at = now
            key = (r.size, tuple(self.you(r)))
            if key not in made:
                try:
                    made[key] = pack_canvas(draw(r.size[0], r.size[1], self.you(r)))
                except Exception as e:      # a picture that cannot be drawn must not end everyone's game
                    made[key] = None
                    self.note("no picture for %s (%s)" % (r.name, type(e).__name__))
            pic = made[key]
            if pic is None:
                continue
            body = json.dumps(dict(pic, t="f"), separators=(",", ":"))
            if body == r.last:               # nothing moved: nothing to send
                continue
            r.last = body
            ln.send_raw((body + "\n").encode())

    def to_lobby(self):
        self.playing = False
        if Sound is not None:
            Sound.tap = None
        self.taps = None
        self.seats = [s for s in self.seats if s["kind"] != "gone"]
        self.send_lobby()

    def close(self):
        if Sound is not None:
            Sound.tap = None
        for ln in self.net.links:
            ln.send({"t": "bye"})
        self.net.close()


# =============================================================================================
# A player's side: keys out, pictures in
# =============================================================================================
class Client:
    def __init__(self, spec, addr, port, name, n=1, kitty=False, size=(80, 24), timeout=2.5):
        s = socket.create_connection((addr, port), timeout=timeout)
        self.spec = spec
        self.link = Link(s)
        self.link.send({"t": "hello", "g": spec.game, "p": spec.proto, "name": clean_name(name), "n": n,
                        "kitty": bool(kitty), "size": list(size)})
        self.state, self.lobby, self.frame, self.you, self.why = "wait", None, None, [], None
        self.addr = "%s:%d" % (addr, port)
        self.size = tuple(size)

    def poll(self):
        sounds = []
        for m in self.link.recv():
            t = m.get("t")
            if t in ("welcome", "start", "lobby"):
                you = m.get("you")
                if isinstance(you, list) and all(isinstance(i, int) and 0 <= i < 8 for i in you):
                    self.you = you[:4]
            if t == "welcome":
                self.state = "lobby"
            elif t == "lobby":
                self.lobby, self.state, self.frame = m, "lobby", None
            elif t == "start":
                self.state, self.frame = "game", None
            elif t == "f":
                cv = unpack_canvas(m)
                if cv is not None:
                    self.frame, self.state = cv, "game"
            elif t == "s":
                sounds += [n for n in (m.get("n") or [])[:16] if isinstance(n, str)]
            elif t == "no":
                self.why, self.state = str(m.get("why", "the host said no"))[:60], "closed"
            elif t == "bye":
                self.why, self.state = "the host ended the game", "closed"
        self.link.flush()
        if self.link.closed and self.state != "closed":
            self.why, self.state = self.why or "the connection to the host was lost", "closed"
        return sounds

    def keys(self, events, clear=False):
        if events or clear:
            m = {"t": "k", "e": [list(e) for e in events]}
            if clear:
                m["clr"] = 1
            self.link.send(m)

    def resize(self, size):
        if tuple(size) != self.size:
            self.size = tuple(size)
            self.link.send({"t": "sz", "size": list(size)})

    def close(self):
        self.link.close()


# =============================================================================================
# The screens: the LAN menu (name, host, join), the host's lobby, the join list, a joined player's game
# =============================================================================================
def term_events(term):
    return term.events(0) if hasattr(term, "events") else [(k, "press") for k in term.keys(0)]


def drain_mouse(term):
    take = getattr(term, "take_mouse", None)
    if take:
        take()


def fits(term, spec):
    cols, rows = term.size()
    return cols >= spec.size[0] and rows >= spec.size[1]


def too_small(term, spec):
    term.write("\x1b[0m\x1b[2J\x1b[HPlease make the window larger (%dx%d)." % spec.size)


def dimmed(cv, k=0.6):
    for y in range(cv.H):
        cv.px[y] = [mix(c, DIM, k) for c in cv.px[y]]
    return cv


def screen(term, spec, dt, lines, keys):
    cols, rows = term.size()
    cv = dimmed(spec.backdrop(cols, rows, dt))
    cv.text = {}
    overlay(cv, lines)
    footer(cv, keys)
    term.write(cv.emit())


def seat_lines(rows, most, you=(), here_label="here"):
    out = []
    for i, (name, kind) in enumerate(rows[:most]):
        what = {"here": here_label, "lan": "LAN", "bot": "computer", "gone": "left"}.get(kind, "")
        out.append(" %d  %-9s %-9s%s" % (i + 1, name, what, "  <- you" if i in you else ""))
    for i in range(len(rows), most):
        out.append(" %d  %-9s" % (i + 1, "- free -"))
    return out


def lan_menu(term, spec):
    """The LAN screen a game's title menu leads to: your name, host a game, join one."""
    name = lan_name()
    local = 1
    items = ["host", "join", "name"] + (["local"] if spec.local > 1 else []) + ["back"]
    sel, note, help_ = 0, None, False
    last = time.time()
    while True:
        now = time.time()
        dt = min(0.1, now - last)
        last = now
        go = None
        for k, kind in term_events(term):
            if kind == "release":
                continue
            if help_:
                help_ = False
                continue
            key = items[sel]
            if key == "name" and (len(k) == 1 and (k.isalnum() or k in " -_") or k == "backspace"):
                nm = name if name != "PLAYER" or k == "backspace" else ""
                nm = nm[:-1] if k == "backspace" else (nm + k.upper())[:8]
                name = clean_name(nm)
                save_settings(lan_name=name)
                continue
            if k in ("esc", "q"):
                return
            if k == "?":
                help_ = True
            elif k in ("up", "w"):
                sel = (sel - 1) % len(items)
            elif k in ("down", "s", "tab"):
                sel = (sel + 1) % len(items)
            elif k in ("left", "right", "a", "d") and key == "local":
                local = 2 if local == 1 else 1
            elif k == "m":
                toggle_sound(spec)
            elif k in ("enter", " "):
                if key == "local":
                    local = 2 if local == 1 else 1
                elif key != "name":
                    go = key
        drain_mouse(term)
        if go == "back":
            return
        if go == "host":
            note = host_session(term, spec, name, local)
        elif go == "join":
            note = join_session(term, spec, name, local)
        if go:
            last = time.time()
            continue
        if not fits(term, spec):
            too_small(term, spec)
            time.sleep(0.2)
            continue
        labels = {"host": "Host a LAN game     others join you",
                  "join": "Join a LAN game     someone else hosts",
                  "name": "Your name           %s%s" % (name, "_" if items[sel] == "name" and int(now * 2) % 2 else ""),
                  "local": "At this keyboard    < %d >" % local,
                  "back": "Back"}
        lines = ["%s  -  LAN GAME" % spec.title, "",
                 "%d to %d players, each at their own computer," % spec.players if spec.players[0] != spec.players[1]
                 else "%d players, each at their own computer," % spec.players[0],
                 "in the same network (LAN or WLAN).", ""]
        lines += ["%s %s" % (">" if items[i] == items[sel] else " ", labels[it]) for i, it in enumerate(items)]
        if note:
            lines += ["", note]
        if help_:
            lines = spec.help(getattr(term, "kitty", False))
        keys = ("Up/Down choose   type your name   Enter   Esc back" if items[sel] == "name" else
                "Up/Down choose   Enter   M %s   ? help   Esc back" % sound_label(spec).lower())
        screen(term, spec, dt, lines, keys)
        time.sleep(max(0, 1 / 30 - (time.time() - now)))


def host_session(term, spec, name, local=1, port=PORT, beacon=True):
    """Host a LAN game. Returns a note for the LAN menu (or None)."""
    try:
        srv = Server(spec, name, local, port, beacon)
    except OSError as e:
        return "could not open a LAN game: %s" % (e.strerror or e)
    try:
        while True:
            if host_lobby(term, srv) != "start":
                return None
            srv.start()
            try:
                res = spec.match(term, srv)
            finally:
                srv.to_lobby()
            if res == "quit":
                return None
    finally:
        srv.close()


def host_lobby(term, srv):
    spec = srv.spec
    last = time.time()
    help_ = False
    while True:
        now = time.time()
        dt = min(0.1, now - last)
        last = now
        srv.poll(now)
        play_sound(spec, srv.sounds)
        srv.sounds = []
        for k, kind in term_events(term):
            if kind != "press":
                continue
            if help_:
                help_ = False
                continue
            if k in ("esc", "q"):
                return "quit"
            if k == "?":
                help_ = True
            elif k == "m":
                toggle_sound(spec)
            elif k in ("enter", " ") and srv.ready():
                play_sound(spec, ["start"])
                return "start"
        drain_mouse(term)
        if not fits(term, spec):
            too_small(term, spec)
            time.sleep(0.2)
            continue
        lines = ["%s  -  HOSTING A LAN GAME" % spec.title, "",
                 "the others choose  Join a LAN game  - this game shows",
                 "up there by itself, or they type:  %s  (port %d)" % (srv.ip, srv.port), ""]
        lines += seat_lines(srv.seat_rows(), srv.most, srv.here(), "here")
        info = spec.info()
        if info:
            lines += ["", info]
        lines += [""] + (list(srv.notes) or ["waiting for players ..."])
        if help_:
            lines = spec.help(getattr(term, "kitty", False))
        need = spec.players[0] - srv.humans()
        keys = ("Enter start   ? help   Esc cancel" if need <= 0 else
                "waiting for %d more   ? help   Esc cancel" % need)
        screen(term, spec, dt, lines, keys)
        time.sleep(max(0, 1 / 30 - (time.time() - now)))


def join_session(term, spec, name, local=1, finder=None):
    """Find (or type) a host and play there. Returns a note for the LAN menu (or None)."""
    finder = finder or Finder(spec.game, spec.proto)
    sel, addr, note = 0, "", None
    last = time.time()
    try:
        while True:
            now = time.time()
            dt = min(0.1, now - last)
            last = now
            hosts = finder.poll(now)
            n = len(hosts) + 1
            sel = min(sel, n - 1)
            target = None
            for k, kind in term_events(term):
                if kind == "release":
                    continue
                if k == "esc" or (k == "q" and not addr):
                    return None
                if k == "up":
                    sel = (sel - 1) % n
                elif k in ("down", "tab"):
                    sel = (sel + 1) % n
                elif k == "backspace":
                    addr = addr[:-1]
                    sel = n - 1
                elif len(k) == 1 and (k.isalnum() or k in ".:-"):
                    addr = (addr + k)[:40]
                    sel = n - 1
                elif k == "enter":
                    if sel < len(hosts):
                        target = hosts[sel][0]
                    elif addr:
                        h, _, p = addr.partition(":")
                        target = (h, int(p) if p.isdigit() else PORT)
            drain_mouse(term)
            if target:
                frame = ["JOIN A LAN GAME", "", "connecting to %s:%d ..." % target]
                if fits(term, spec):
                    screen(term, spec, 0.0, frame, "please wait")
                try:
                    cl = Client(spec, target[0], target[1], name, local, getattr(term, "kitty", False), term.size())
                except (OSError, ValueError) as e:
                    note = "no game at %s:%d (%s)" % (target[0], target[1], getattr(e, "strerror", None) or e)
                    continue
                try:
                    return client_loop(term, cl)
                finally:
                    cl.close()
            if not fits(term, spec):
                too_small(term, spec)
                time.sleep(0.2)
                continue
            lines = ["%s  -  JOIN A LAN GAME" % spec.title, "", "games in your network (LAN / WLAN):"]
            for i, ((ip, port), h) in enumerate(hosts):
                state = "%d/%d players" % (h["n"], h["m"]) if h["open"] else "playing / full"
                lines.append("%s %-9s %-15s %s" % (">" if sel == i else " ", h["name"], state, ip))
            if not hosts:
                lines.append("  (looking ... )" if finder.sock else "  (cannot listen for games here - type one)")
            lines += ["", "%s or type the host's address:  %s%s" % (">" if sel == len(hosts) else " ", addr,
                                                                     "_" if int(now * 2) % 2 else " ")]
            if note:
                lines += ["", note]
            screen(term, spec, dt, lines, "Up/Down choose   type an address   Enter join   Esc back")
            time.sleep(max(0, 1 / 30 - (time.time() - now)))
    finally:
        finder.close()


def client_loop(term, cl):
    """A joined player's screen: the lobby until the host starts, then the host's pictures. Esc opens a menu of
    this computer's own (the game goes on meanwhile). Returns a note for the LAN menu."""
    spec = cl.spec
    kitty = getattr(term, "kitty", False)
    menu = help_ = False
    shown = None
    last = time.time()
    while True:
        now = time.time()
        dt = min(0.1, now - last)
        last = now
        play_sound(spec, cl.poll())
        if cl.state == "closed":
            return cl.why
        game = cl.state == "game"
        out = []
        for name, kind in term_events(term):
            if kind == "press" and (menu or help_ or not game):
                if help_:
                    help_ = False
                elif name == "q" or (name == "esc" and not game):
                    return "you left the game"
                elif name in ("esc", "p", "enter", " ") and game:
                    menu = False
                elif name == "?":
                    help_ = True
                elif name == "m":
                    toggle_sound(spec)
                elif name == "v":
                    arcadekit.cycle_view()
                continue
            if menu or help_ or not game:
                continue
            if kind == "press" and name in ("esc", "?"):
                menu = True
                help_ = name == "?"
                cl.keys(out, clear=True)
                out = []
                continue
            out.append((name, kind))
        cl.keys(out)
        drain_mouse(term)
        cols, rows = term.size()
        cl.resize((cols, rows))
        if not fits(term, spec):
            too_small(term, spec)
            shown = None
            time.sleep(0.2)
            continue
        if game:
            if cl.frame is None:
                cv = Canvas(cols, rows, DIM)
                cv.center(rows // 2, "the game starts ...", (200, 200, 220))
            else:
                cv = fit(cl.frame, cols, rows)
            if help_:
                overlay(cv, spec.help(kitty))
            elif menu:
                overlay(cv, ["M E N U", "", "Esc / Enter   back to the game", "Q             leave the game",
                             "V             view   M sound", "", "(the game goes on meanwhile)"])
            if shown != (cols, rows, cv.cols, cv.rows):
                term.write("\x1b[0m\x1b[2J")
                shown = (cols, rows, cv.cols, cv.rows)
            term.write(cv.emit())
        else:
            lb = cl.lobby
            lines = ["%s  -  JOINED %s" % (spec.title, cl.addr), ""]
            if lb:
                most = lb.get("most") if isinstance(lb.get("most"), int) else spec.players[1]
                rows_ = [r for r in lb.get("seats", []) if isinstance(r, list) and len(r) == 2][:8]
                lines += seat_lines([(clean_name(a), str(b)) for a, b in rows_], max(1, min(8, most)), cl.you, "host")
                info = str(lb.get("info") or "")[:70]
                if info:
                    lines += ["", info]
            lines += ["", "waiting for the host to start ..."]
            if help_:
                lines = spec.help(kitty)
            screen(term, spec, dt, lines, "? help   Esc leave")
            shown = None
        time.sleep(max(0, 1 / 60 - (time.time() - now)))


# =============================================================================================
# Helpers for the games' match loops
# =============================================================================================
def host_bar(srv, extra="Esc pause"):
    return "LAN %s:%d   %s" % (srv.ip, srv.port, srv.recent() or extra)


def try_match(spec, host_script, guest_keys, seconds=3.0, size=(100, 32), guest_size=(90, 30), leave=False):
    """For the games' self-tests: a host and one guest over the loopback. The host's keys follow host_script
    [(t, key[, kind])], the guest presses guest_keys [(t, key, kind)] and, with leave, goes away after them.
    Returns (what spec.match returned, the pictures the guest got, the guest's sounds, the server)."""
    import threading
    srv = Server(spec, "host", port=0, beacon=False)
    got = dict(frames=0, sounds=[], last=None)
    stop = []

    def guest():
        cl = Client(spec, "127.0.0.1", srv.port, "guest", size=guest_size)
        t0 = None
        keys = sorted(guest_keys, key=lambda e: e[0])
        end = time.time() + seconds + 5
        while time.time() < end and not stop and cl.state != "closed":
            got["sounds"] += cl.poll()
            if cl.state == "game" and t0 is None:
                t0 = time.time()
            if t0 is not None:
                due = [k for k in keys if k[0] <= time.time() - t0]
                keys = keys[len(due):]
                cl.keys([(k[1], k[2]) for k in due])
                if leave and not keys:
                    break
            if cl.frame is not None and cl.frame is not got["last"]:
                got["frames"] += 1
                got["last"] = cl.frame
            time.sleep(0.005)
        cl.close()

    th = threading.Thread(target=guest, daemon=True)
    th.start()
    end = time.time() + 3
    while time.time() < end and srv.remote_count() < 1:
        srv.poll(time.time())
        time.sleep(0.005)
    assert srv.remote_count() == 1, "the guest did not get in"
    srv.start()
    try:
        res = spec.match(FakeTerm(host_script, size), srv)
    finally:
        srv.to_lobby()
        stop.append(1)
        th.join(5)
        srv.close()
    return res, got["frames"], got["sounds"], srv


# =============================================================================================
# Self-test:  python3 arcadenet.py --selftest
# =============================================================================================
class FakeTerm:
    def __init__(self, script, size=(100, 32), kitty=False):
        self.script = sorted(script, key=lambda e: e[0])
        self.t0 = time.time()
        self.cols_rows = size
        self.frames = 0
        self.kitty = kitty
        self.last = ""

    def events(self, timeout=0.0):
        now = time.time() - self.t0
        out = [e for e in self.script if e[0] <= now]
        self.script = [e for e in self.script if e[0] > now]
        return [(e[1], e[2] if len(e) > 2 else "press") for e in out]

    def keys(self, timeout=0.0):
        return [k for k, kind in self.events(timeout) if kind == "press"]

    def size(self):
        return self.cols_rows

    def write(self, s):
        self.frames += 1
        self.last = s


def selftest():
    import os
    import tempfile
    import arcadesound
    t0 = time.time()
    tmp = tempfile.mkdtemp()
    arcadesound.SETTINGS_PATH = os.path.join(tmp, "settings.json")
    # pictures survive the trip
    cv = Canvas(30, 6)
    cv.rect(3, 2, 10, 5, (200, 10, 99))
    cv.px[0][0] = (1.6, 2, 300)                      # odd values are clamped, not fatal
    cv.put(2, 1, "HELLO", (255, 255, 0), None)
    cv.put(2, 2, "X", (1, 2, 3), (4, 5, 6))
    m = json.loads(json.dumps(pack_canvas(cv)))
    back = unpack_canvas(m)
    assert back is not None and back.cols == 30 and back.rows == 6
    assert back.px[3][5] == (200, 10, 99) and back.px[0][0] == (1, 2, 255)
    assert back.text[(2, 1)] == ("H", (255, 255, 0), None) and back.text[(2, 2)] == ("X", (1, 2, 3), (4, 5, 6))
    assert back.emit()
    bad = dict(m, px=base64.b64encode(zlib.compress(b"\0" * 10)).decode())
    assert unpack_canvas(bad) is None
    assert unpack_canvas(dict(m, c=10 ** 6)) is None and unpack_canvas({"c": 2}) is None
    assert unpack_canvas(dict(m, px="!!")) is None
    bomb = dict(m, px=base64.b64encode(zlib.compress(b"\0" * (10 ** 7))).decode())
    assert unpack_canvas(bomb) is None
    big = fit(cv, 40, 10)
    assert big.cols == 40 and big.px[3 + 4][5 + 5] == (200, 10, 99) and big.text[(7, 3)][0] == "H"
    small = fit(cv, 20, 4)
    assert small.cols == 20 and len(small.px) == 8 and all(len(r) == 20 for r in small.px)
    assert clean_name(" ab<c>d!efghijk") == "ABCDEFG" and clean_name("") == "PLAYER"
    # a host and two players over the loopback: lobby, keys, pictures, sounds, a player who leaves
    got = {}

    def draw(cols, rows, seats):
        c = Canvas(cols, rows)
        c.put(0, 0, "seat %s" % seats[0], (255, 255, 255))
        got.setdefault("sizes", []).append((cols, rows))
        return c

    spec = LanGame("nettest", "NETTEST", match=None, backdrop=lambda c, r, dt: Canvas(c, r), players=(2, 3),
                   size=(40, 12), info=lambda: "first to 3")
    srv = Server(spec, "host", port=0, beacon=False)
    a = Client(spec, "127.0.0.1", srv.port, "anna", size=(60, 20))
    b = Client(spec, "127.0.0.1", srv.port, "anna", size=(10, 5))
    end = time.time() + 2
    while time.time() < end and (len(srv.seats) < 3 or a.state != "lobby" or b.state != "lobby"):
        srv.poll(time.time())
        a.poll(), b.poll()
        time.sleep(0.01)
    assert [s["name"] for s in srv.seats] == ["HOST", "ANNA", "ANNA 2"], srv.seats
    assert srv.ready() and a.you == [1] and b.you == [2]
    assert list(srv.remotes.values())[1].size == (40, 12)          # clamped to the game's smallest window
    late = Client(spec, "127.0.0.1", srv.port, "late")
    end = time.time() + 2
    while time.time() < end and late.state != "closed":
        srv.poll(time.time())
        late.poll()
        time.sleep(0.01)
    assert late.state == "closed" and "full" in late.why
    srv.start()
    srv.spec.sound = None
    Sound.tap.append("boom")
    a.keys([("w", "press"), ("w", "release"), ("bad" * 9, "press"), (" ", "nonsense")])
    end = time.time() + 2
    seen = []
    while time.time() < end and not (a.frame and b.frame and seen):
        srv.poll(time.time())
        for r, seats, evs, clr in srv.inputs():
            if evs:
                seen.append((seats, evs))
        srv.send_frames(time.time(), draw)
        sa = a.poll()
        b.poll()
        if sa:
            got["snd"] = sa
        time.sleep(0.01)
    assert seen and seen[0] == ([1], [("w", "press"), ("w", "release")]), seen
    assert a.frame and a.frame.text[(0, 0)][0] == "s" and a.frame.cols == 60 and b.frame.cols == 40
    assert got.get("snd") == ["boom"], got
    assert srv.min_size(100, 30) == (40, 12)
    n = len(got["sizes"])
    srv.send_frames(time.time() + 1, draw)
    srv.send_frames(time.time() + 2, draw)          # same picture: drawn, not sent again
    assert len(got["sizes"]) == n + 4
    b.close()
    end = time.time() + 2
    while time.time() < end and not srv.left:
        srv.poll(time.time())
        time.sleep(0.01)
    assert srv.take_left() == [2] and srv.seats[2]["kind"] == "gone" and srv.take_left() == []
    srv.to_lobby()
    assert Sound.tap is None and len(srv.seats) == 2
    srv.close()
    end = time.time() + 2
    while time.time() < end and a.state != "closed":
        a.poll()
        time.sleep(0.01)
    assert a.state == "closed" and "ended" in a.why
    # the screens: the LAN menu (a typed name, back), the host's lobby (cancel), the join list (a typed address
    # with nobody there, back)
    term = FakeTerm([(0.05, "down"), (0.1, "down"), (0.15, "z"), (0.2, "backspace"), (0.25, "o"), (0.3, "down"),
                     (0.35, "enter")])
    lan_menu(term, spec)
    assert lan_name() == "O" and term.frames > 3
    term = FakeTerm([(0.3, "enter"), (0.4, "esc")])
    assert host_session(term, spec, "o", port=0, beacon=False) is None and term.frames > 3
    term = FakeTerm([(0.05 + 0.02 * i, k) for i, k in enumerate("127.0.0.1:9")] + [(0.4, "enter"), (0.7, "esc")])
    assert join_session(term, spec, "o", finder=Finder("nettest", 1, port=0)) is None and term.frames > 3
    assert time.time() - t0 < 20
    print("arcadenet selftest ok (%.1fs)" % (time.time() - t0))


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        selftest()
    else:
        print(__doc__)
