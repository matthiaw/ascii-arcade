# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""Finer pixels from inside the arcade: shrink the terminal's font while the arcade runs.

A smaller font gives more character cells in the same window, and every game draws its world with more
detail when there are more cells. How the font is changed depends on the terminal:

  WezTerm        a user variable (OSC 1337 SetUserVar) that a few lines in ~/.wezterm.lua turn into a
                 per-window font override (see WEZTERM_SNIPPET; `arcade --zoom setup` prints it)
  Terminal.app   AppleScript sets the font size of this tab's profile; the old size is kept in the
                 settings file, so even after a crash the next start puts it back
  kitty          remote control by escape code (needs `allow_remote_control yes` in kitty.conf)
  iTerm2         switches to a profile named "ASCII Arcade" (you create it, with a small font), and back

The window keeps its size on screen: Terminal.app gets more rows and columns, WezTerm is told not to
shrink the window. Everything is undone when the arcade quits.
"""
import base64
import os
import subprocess
import sys

from arcadesound import load_settings, save_settings

LEVELS = ("normal", "fine", "finer")
FACTOR = {"normal": 1.0, "fine": 0.75, "finer": 0.55}
ITERM_PROFILE = "ASCII Arcade"

WEZTERM_SNIPPET = """\
-- ASCII ARCADE: finer pixels (R in the arcade). Put this above `return config`.
wezterm.on('user-var-changed', function(window, pane, name, value)
  if name ~= 'ARCADE_ZOOM' then return end
  local o = window:get_config_overrides() or {}
  local f = tonumber(value) or 1
  local g = wezterm.GLOBAL.arcade_base or {}
  local id = tostring(window:window_id())
  if f >= 1 then
    o.font_size = nil
    o.adjust_window_size_when_changing_font_size = nil
    g[id] = nil
  else
    if not o.font_size or not g[id] then g[id] = window:effective_config().font_size end
    o.font_size = g[id] * f
    o.adjust_window_size_when_changing_font_size = false
  end
  wezterm.GLOBAL.arcade_base = g
  window:set_config_overrides(o)
end)
"""


def terminal():
    """Which terminal the arcade runs in: 'wezterm', 'apple', 'kitty', 'iterm' or None."""
    tp = os.environ.get("TERM_PROGRAM", "")
    if tp == "WezTerm":
        return "wezterm"
    if tp == "Apple_Terminal":
        return "apple"
    if tp == "iTerm.app":
        return "iterm"
    if os.environ.get("KITTY_WINDOW_ID") or os.environ.get("TERM") == "xterm-kitty":
        return "kitty"
    return None


def wezterm_ready():
    """True when the WezTerm config contains the snippet (it looks for its variable name)."""
    paths = [os.environ.get("WEZTERM_CONFIG_FILE"), os.path.expanduser("~/.wezterm.lua"),
             os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "wezterm", "wezterm.lua")]
    for p in paths:
        try:
            with open(p) as f:
                if "ARCADE_ZOOM" in f.read():
                    return True
        except (OSError, TypeError):
            pass
    return False


def _out(s):
    sys.stdout.write(s)
    sys.stdout.flush()


def _tty():
    try:
        return os.ttyname(sys.stdout.fileno())
    except OSError:
        return None


def _osascript(script):
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=8)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _apple_font(tty, size=None):
    """Read (size None) or set the font size of the Terminal.app tab on this tty; returns the old size."""
    set_ = "" if size is None else "\n          set font size of s to %s" % size
    out = _osascript("""tell application "Terminal"
  repeat with w in windows
    repeat with t in tabs of w
      if tty of t is "%s" then
        set s to current settings of t
        set old to font size of s%s
        return old
      end if
    end repeat
  end repeat
end tell""" % (tty, set_))
    try:
        return float(out)
    except (TypeError, ValueError):
        return None


def _cells():
    try:
        sz = os.get_terminal_size(sys.stdout.fileno())
        return sz.columns, sz.lines
    except OSError:
        return None


class Zoom:
    """The font level the arcade asked for; apply() changes it, restore() undoes everything."""

    def __init__(self):
        self.kind = terminal()
        self.level = "normal"
        self.active = False

    def available(self):
        return self.kind is not None and (self.kind != "wezterm" or wezterm_ready())

    def hint(self):
        """Why R cannot work here, in one line (None when it can)."""
        if self.kind == "wezterm" and not wezterm_ready():
            return "WezTerm needs a few lines in ~/.wezterm.lua: run  arcade --zoom setup"
        if self.kind is None:
            return "this terminal cannot be zoomed from here - press Cmd - (or Ctrl -) for finer pixels"
        return None

    def apply(self, level):
        """Switch to a level (normal / fine / finer); returns a short note on failure, else None."""
        if level not in LEVELS:
            return None
        if not self.available():
            return self.hint()
        f = FACTOR[level]
        err = getattr(self, "_" + self.kind)(f)
        if err:
            return err
        self.level = level
        self.active = level != "normal"
        return None

    def restore(self):
        if self.active or load_settings().get("zoom_restore"):
            getattr(self, "_" + (self.kind or "none"), lambda f: None)(1.0)
            self.active = False
            self.level = "normal"

    # -- per terminal ---------------------------------------------------------------------------------
    def _wezterm(self, f):
        val = base64.b64encode(("%.3f" % f).encode()).decode()
        _out("\x1b]1337;SetUserVar=ARCADE_ZOOM=%s\x07" % val)

    def _kitty(self, f):
        # escape-code remote control: reset to the configured size, then scale relative to it
        import json
        def cmd(payload):
            msg = dict(cmd="set-font-size", version=[0, 26, 0], no_response=True, payload=payload)
            _out("\x1bP@kitty-cmd%s\x1b\\" % json.dumps(msg, separators=(",", ":")))
        cmd(dict(size=0, increment_op=None))
        if f < 1:
            cmd(dict(size=f, increment_op="*"))

    def _iterm(self, f):
        if f < 1:
            name = ITERM_PROFILE
        else:
            name = load_settings().get("zoom_restore", {}).get("iterm_profile") or os.environ.get("ITERM_PROFILE") or "Default"
        if f < 1 and not load_settings().get("zoom_restore"):
            save_settings(zoom_restore=dict(term="iterm", iterm_profile=os.environ.get("ITERM_PROFILE") or "Default"))
        _out("\x1b]1337;SetProfile=%s\x07" % name)
        if f >= 1:
            save_settings(zoom_restore=None)

    def _apple(self, f):
        tty = _tty()
        if not tty:
            return "no terminal window found"
        rec = load_settings().get("zoom_restore") or {}
        if rec.get("term") != "apple":          # first change: note the old font and window size
            base = _apple_font(tty)
            if base is None:
                return "Terminal.app did not answer (allow it in System Settings > Privacy > Automation)"
            cols, rows = _cells() or (0, 0)
            rec = dict(term="apple", tty=tty, font_size=base, cols=cols, rows=rows)
            save_settings(zoom_restore=rec)
        base = rec["font_size"]
        size = round(base * f, 1) if f < 1 else base
        now = _apple_font(tty, size)            # sets the new size, returns the one before
        if now is None:
            return "Terminal.app did not change the font"
        if f >= 1:
            if rec.get("tty") == tty and rec.get("cols"):
                _out("\x1b[8;%d;%dt" % (rec["rows"], rec["cols"]))
            save_settings(zoom_restore=None)
            return None
        cells = _cells()
        if cells and now != size:               # keep the window's size on screen: more cells
            k = now / size
            _out("\x1b[8;%d;%dt" % (round(cells[1] * k), round(cells[0] * k)))
        return None

ZOOM = Zoom()


def startup():
    """At arcade start: undo a zoom a crash left behind, then put back the level the player chose."""
    rec = load_settings().get("zoom_restore")
    if rec and rec.get("term") == ZOOM.kind:
        ZOOM.restore()
    elif rec:
        save_settings(zoom_restore=None)        # left by another terminal: nothing to do from here
    level = load_settings().get("zoom", "normal")
    if level != "normal" and ZOOM.available():
        ZOOM.apply(level)


def cycle():
    """R in the launcher: normal -> fine -> finer -> normal. Returns a note for the menu (or "")."""
    nxt = LEVELS[(LEVELS.index(ZOOM.level) + 1) % len(LEVELS)]
    err = ZOOM.apply(nxt)
    if err:
        return err
    save_settings(zoom=nxt)
    return ""
