# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""arcadesound - little synthesized sound effects for the ASCII ARCADE games, with no dependencies.

Every sound is described as a few notes (square, triangle, saw, sine or noise, with pitch slides, vibrato and an
envelope). The notes are rendered once to small WAV files in a cache folder and played with the system player
(afplay on macOS, paplay / aplay / pw-play on Linux), so the game never waits for audio.

    from arcadesound import Sound
    snd = Sound("skyshot", {
        "fire": [dict(w="noise", f=900, f2=200, d=0.25, v=0.7)],
        "coin": [dict(w="square", f=988, d=0.06), dict(w="square", f=1319, d=0.18)],
    })
    snd.play("fire")            # fire and forget
    snd.play("coin", vol=0.5)   # quieter
    snd.toggle()                # sound on / off, remembered for every game

A note is a dict:
    w     wave: "square" (default), "tri", "saw", "sine", "noise"
    f     start frequency in Hz (for noise: how fast the noise changes; low = rumble, high = hiss)
    f2    end frequency (a slide), optional
    d     duration in seconds
    v     volume 0..1 (default 0.6)
    at    start time in seconds; default: right after the previous note (give at=0 for chords)
    a     attack in seconds (default 0.004)
    r     release: "exp" (plucked, default), "lin" (linear fade) or "hold" (flat, short fade at the end)
    duty  square duty cycle (default 0.5)
    vib   (rate Hz, depth in semitones), optional
    curve "exp" (default) or "lin": how the slide from f to f2 moves

Sound is off when ARCADE_SOUND=0 is set, when the output is not a terminal, during --selftest / --bench runs,
when there is no player on the system, or when the player switched it off (M in the pause menu or the launcher).
"""
import hashlib
import json
import math
import os
import queue
import random
import shutil
import struct
import subprocess
import sys
import threading
import time
import wave

RATE = 22050
SETTINGS_PATH = os.path.expanduser("~/.ascii_arcade_settings.json")
MAX_VOICES = 8


def _cache_dir():
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Caches")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, "ascii-arcade", "sounds")


def load_settings():
    try:
        with open(SETTINGS_PATH) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(**changes):
    data = load_settings()
    data.update(changes)
    try:
        tmp = SETTINGS_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, SETTINGS_PATH)
    except OSError:
        pass


def sound_enabled_setting():
    return bool(load_settings().get("sound", True))


def _player():
    if sys.platform == "darwin" and shutil.which("afplay"):
        return lambda path, vol: ["afplay", "-v", "%.2f" % vol, path]
    for name, cmd in (("pw-play", lambda p, v: ["pw-play", "--volume", "%.2f" % v, p]),
                      ("paplay", lambda p, v: ["paplay", "--volume", str(int(65536 * v)), p]),
                      ("aplay", lambda p, v: ["aplay", "-q", p])):
        if shutil.which(name):
            return cmd
    return None


# ------------------------------------------------------------------------------------------------
# synthesis
# ------------------------------------------------------------------------------------------------
def render(notes, rate=RATE):
    """Turn a list of notes into a list of float samples (-1..1)."""
    t, placed = 0.0, []
    for n in notes:
        start = n.get("at", t)
        placed.append((start, n))
        t = start + n.get("d", 0.1)
    total = max((s + n.get("d", 0.1) for s, n in placed), default=0.0) + 0.01
    out = [0.0] * int(total * rate)
    rnd = random.Random(7)
    for start, n in placed:
        w = n.get("w", "square")
        f0 = float(n.get("f", 440))
        f1 = float(n.get("f2", f0))
        d = max(0.005, n.get("d", 0.1))
        vol = n.get("v", 0.6)
        att = max(0.001, n.get("a", 0.004))
        rel = n.get("r", "exp")
        duty = n.get("duty", 0.5)
        vib = n.get("vib")
        lin = n.get("curve") == "lin"
        count = int(d * rate)
        base = int(start * rate)
        phase, noise, hold_until = 0.0, 0.0, -1.0
        for i in range(count):
            x = i / count
            if lin or f0 <= 0 or f1 <= 0:
                f = f0 + (f1 - f0) * x
            else:
                f = f0 * (f1 / f0) ** x
            if vib:
                f *= 2 ** (vib[1] * math.sin(2 * math.pi * vib[0] * i / rate) / 12)
            phase += f / rate
            if w == "noise":
                if phase >= hold_until:
                    noise = rnd.uniform(-1, 1)
                    hold_until = phase + 1.0
                s = noise
            else:
                p = phase % 1.0
                if w == "square":
                    s = 0.8 if p < duty else -0.8
                elif w == "tri":
                    s = 4 * p - 1 if p < 0.5 else 3 - 4 * p
                elif w == "saw":
                    s = 2 * p - 1
                else:
                    s = math.sin(2 * math.pi * p)
            tt = i / rate
            env = min(1.0, tt / att)
            if rel == "exp":
                env *= math.exp(-4.0 * x)
            elif rel == "lin":
                env *= 1.0 - x
            else:
                env *= min(1.0, (count - i) / (0.01 * rate))
            j = base + i
            if j < len(out):
                out[j] += s * env * vol
    # soft limit so chords never clip harshly
    return [math.tanh(1.2 * s) for s in out]


def write_wav(path, samples, rate=RATE):
    data = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s)) * 30000)) for s in samples)
    tmp = path + ".%d.tmp" % os.getpid()
    with wave.open(tmp, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(data)
    os.replace(tmp, path)


# ------------------------------------------------------------------------------------------------
# the player
# ------------------------------------------------------------------------------------------------
class Sound:
    """A bank of named sounds for one game."""
    tap = None      # a list while a LAN game is hosted: every sound played is noted there for the players who joined

    def __init__(self, game, bank, volume=0.55):
        self.game = game
        self.bank = dict(bank)
        self.volume = volume
        self.files = {}
        self.procs = []
        self.last = {}
        self.cmd = _player()
        quiet = ("--selftest" in sys.argv or "--bench" in sys.argv
                 or os.environ.get("ARCADE_SOUND", "1").lower() in ("0", "off", "no", "false"))
        try:
            tty_ok = sys.stdout.isatty()
        except (AttributeError, ValueError):
            tty_ok = False
        self.available = bool(self.cmd) and not quiet and tty_ok
        self.enabled = self.available and sound_enabled_setting()
        self.dir = _cache_dir()
        self.queue = queue.SimpleQueue()
        if self.available:
            self._prepare()
            threading.Thread(target=self._worker, daemon=True).start()

    # -- files -----------------------------------------------------------------------------
    def _path(self, name):
        key = hashlib.sha1(json.dumps(self.bank[name], sort_keys=True).encode()).hexdigest()[:12]
        return os.path.join(self.dir, "%s-%s-%s.wav" % (self.game, name, key))

    def _ensure(self, name):
        path = self.files.get(name)
        if path:
            return path
        path = self._path(name)
        if not os.path.exists(path):
            os.makedirs(self.dir, exist_ok=True)
            write_wav(path, render(self.bank[name]))
        self.files[name] = path
        return path

    def _prepare(self):
        """Render missing sounds in a separate Python process, so the game never waits for it."""
        missing = {}
        for name in self.bank:
            path = self._path(name)
            if os.path.exists(path):
                self.files[name] = path
            else:
                missing[name] = (path, self.bank[name])
        if not missing:
            return
        try:
            proc = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--render"],
                                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            proc.stdin.write(json.dumps({"dir": self.dir, "sounds": missing}).encode())
            proc.stdin.close()
        except OSError:
            pass

    # -- playing ---------------------------------------------------------------------------
    def play(self, name, vol=1.0, gap=0.04):
        """Play a sound without waiting. The same sound is not restarted within `gap` seconds.
        Starting the player takes some milliseconds, so it happens on a background thread."""
        if Sound.tap is not None and name in self.bank and len(Sound.tap) < 64:
            Sound.tap.append(name)
        if not self.enabled or name not in self.bank:
            return
        now = time.time()
        if now - self.last.get(name, 0.0) < gap:
            return
        self.last[name] = now
        self.queue.put((name, vol))

    def _worker(self):
        while True:
            name, vol = self.queue.get()
            if not self.enabled:
                continue
            self.procs = [p for p in self.procs if p.poll() is None]
            if len(self.procs) >= MAX_VOICES:
                continue
            path = self.files.get(name)
            if not path:
                path = self._path(name)
                if not os.path.exists(path):
                    continue  # still being rendered (first start only)
                self.files[name] = path
            try:
                self.procs.append(subprocess.Popen(self.cmd(path, max(0.0, min(1.0, self.volume * vol))),
                                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                                   stderr=subprocess.DEVNULL))
            except OSError:
                pass

    def toggle(self):
        """Sound on / off (remembered for every game). Returns the new state."""
        if not self.available:
            return False
        self.enabled = not self.enabled
        save_settings(sound=self.enabled)
        if not self.enabled:
            self.stop()
        return self.enabled

    def label(self):
        if not self.available:
            return "Sound: none"
        return "Sound: on" if self.enabled else "Sound: off"

    def stop(self):
        for p in list(self.procs):
            if p.poll() is None:
                try:
                    p.terminate()
                except OSError:
                    pass
        self.procs = []


class NoSound:
    """Stand-in with the same methods, for when arcadesound is missing."""
    available = enabled = False

    def __init__(self, *a, **k):
        pass

    def play(self, *a, **k):
        pass

    def toggle(self):
        return False

    def label(self):
        return "Sound: none"

    def stop(self):
        pass


def _render_job():
    """--render: read {"dir", "sounds": {name: [path, notes]}} from stdin and write the WAV files."""
    job = json.loads(sys.stdin.read() or "{}")
    os.makedirs(job.get("dir", _cache_dir()), exist_ok=True)
    for path, notes in job.get("sounds", {}).values():
        if not os.path.exists(path):
            try:
                write_wav(path, render(notes))
            except OSError:
                pass


if __name__ == "__main__" and "--render" in sys.argv:
    _render_job()
    sys.exit(0)

if __name__ == "__main__":
    # python3 arcadesound.py  -> plays a little demo
    demo = Sound("demo", {
        "coin": [dict(f=988, d=0.07), dict(f=1319, d=0.22)],
        "laser": [dict(w="saw", f=1600, f2=200, d=0.18, v=0.5)],
        "boom": [dict(w="noise", f=1800, f2=60, d=0.6, v=0.9, r="exp")],
        "jingle": [dict(w="tri", f=523, d=0.12), dict(w="tri", f=659, d=0.12), dict(w="tri", f=784, d=0.12),
                   dict(w="square", f=1047, d=0.4, duty=0.25, vib=(6, 0.3))],
    })
    if not demo.enabled:
        print("sound is off or unavailable (%s)" % demo.label())
    for n in ("coin", "laser", "boom", "jingle"):
        print(n)
        demo.play(n)
        time.sleep(0.8)
