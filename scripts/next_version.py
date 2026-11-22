#!/usr/bin/env python3
# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
"""Work out the next release version (used by .github/workflows/release.yml).

- If the version in VERSION has no tag yet, it is released as it is (so VERSION can be raised by hand).
- Otherwise it is raised from the commit messages since the last tag:
  "[major]" or "BREAKING" -> major, "[minor]" or a message starting with "feat" -> minor, anything else -> patch.
- A first argument patch / minor / major forces the step.
Prints the new version (without "v").
"""
import re
import subprocess
import sys


def git(*a):
    return subprocess.run(["git", *a], capture_output=True, text=True).stdout.strip()


def main():
    cur = open("VERSION").read().strip()
    major, minor, patch = map(int, re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", cur).groups())
    force = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in ("patch", "minor", "major") else None
    if not force and not git("tag", "-l", "v" + cur):
        print(cur)
        return
    step = force
    if not step:
        last = git("describe", "--tags", "--abbrev=0", "--match", "v*")
        log = git("log", "--format=%B%x00", (last + "..HEAD") if last else "HEAD")
        msgs = [m.strip() for m in log.split("\0") if m.strip()]
        if any("[major]" in m or "BREAKING" in m for m in msgs):
            step = "major"
        elif any("[minor]" in m or m.lower().startswith("feat") for m in msgs):
            step = "minor"
        else:
            step = "patch"
    if step == "major":
        major, minor, patch = major + 1, 0, 0
    elif step == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    print("%d.%d.%d" % (major, minor, patch))


if __name__ == "__main__":
    main()
