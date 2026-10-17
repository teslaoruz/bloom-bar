#!/usr/bin/env python3
"""Walk the bar widget through every state so you can watch it change.

    python3 ~/.local/share/claude-tray/check.py

It pauses the publisher, drives status.json by hand, and asks the shell what it
actually rendered after each step -- so a failure tells you *which* half broke:
the data, or the drawing.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

STATE = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "claude-tray"
STATUS = STATE / "status.json"
FOCUS_LOG = STATE / "focus.log"
HOLD = 4  # seconds to look at each state

GREEN, RED, DIM, BOLD, OFF = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"


def sh(*args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def shell_says():
    out = sh("qs", "-c", "caelestia", "ipc", "call", "claude", "state").stdout.strip()
    return out.splitlines()[-1] if out else "?"


def write(state, sessions):
    data = {}
    if STATUS.exists():
        try:
            data = json.loads(STATUS.read_text())
        except Exception:
            pass
    data.update({"state": state, "sessions": sessions, "updated": time.time()})
    tmp = STATUS.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(STATUS)


def check(label, ok):
    print(f"  {GREEN + 'OK ' if ok else RED + 'BAD'}{OFF}  {label}")
    return ok


def preflight():
    print(f"{BOLD}Before we start{OFF}")
    problems = []

    fs = sh("hyprctl", "-j", "activewindow").stdout
    if '"fullscreen": 2' in fs or '"fullscreen": 1' in fs:
        problems.append("a fullscreen window is covering the bar -- leave fullscreen first")
        print(f"  {RED}!{OFF}   fullscreen window detected; caelestia hides the bar")
    else:
        check("bar is not hidden by a fullscreen window", True)

    running = sh("qs", "list", "--all").stdout
    check("caelestia shell is running from the overlay",
          "/.config/quickshell/caelestia/shell.qml" in running)

    check("publisher service is active",
          sh("systemctl", "--user", "is-active", "claude-tray.service").stdout.strip() == "active")

    limits = {}
    try:
        limits = json.loads((STATE / "limits.json").read_text())
    except Exception:
        pass
    if limits.get("five_hour"):
        five, seven = limits["five_hour"]["used"], limits.get("seven_day", {}).get("used", "?")
        check(f"real /status limits captured (5h {five}%, 7d {seven}%)", True)
    else:
        check("real /status limits captured -- open a Claude session first", False)

    return problems


def main():
    problems = preflight()
    if problems:
        print(f"\n{RED}Fix this first:{OFF} {problems[0]}\n")
        if input("Continue anyway? [y/N] ").strip().lower() != "y":
            return

    print(f"\n{BOLD}Watch the bar icon.{OFF} Hover it to keep the popout open.\n")
    sh("systemctl", "--user", "stop", "claude-tray.service")

    fake = [{
        "session_id": "check", "state": "working", "cwd": str(Path.home() / "demo-project"),
        "window": None, "pid": os.getpid(), "ts": time.time(),
    }]

    steps = [
        ("working", "spinning flower, 'Working'"),
        ("waiting", "amber, '!' -- 'Needs permission'"),
        ("done", "green flower, 'Done'"),
        ("idle", "dim dot, 'Idle'"),
    ]

    results = []
    for state, looks in steps:
        fake[0]["state"] = state
        fake[0]["ts"] = time.time()
        write(state, fake)
        time.sleep(1.5)
        seen = shell_says()
        print(f"{BOLD}{state:8}{OFF} you should see: {looks}")
        results.append(check(f"shell reports '{seen}'", seen == state))
        time.sleep(HOLD - 1.5)

    print(f"\n{BOLD}Click test{OFF}")
    real = []
    for f in (STATE / "sessions").glob("*.json"):
        try:
            rec = json.loads(f.read_text())
        except Exception:
            continue
        if rec.get("window"):
            real.append(rec)

    if not real:
        print(f"  {DIM}no session with a known window; skipping{OFF}")
    else:
        before = FOCUS_LOG.stat().st_size if FOCUS_LOG.exists() else 0
        write("working", real)
        print(f"  Popout now lists {len(real)} real session(s).")
        print(f"  {BOLD}Hover the bar icon and click a session row now.{OFF}")
        input("  Press Enter once you have clicked... ")
        after = FOCUS_LOG.stat().st_size if FOCUS_LOG.exists() else 0
        if after > before:
            print(f"  {GREEN}The click reached the widget.{OFF} What it ran:")
            print(DIM + FOCUS_LOG.read_text()[before:].rstrip() + OFF)
            results.append(True)
        else:
            print(f"  {RED}The click never reached the widget{OFF} -- focus.sh was not called,")
            print("  so the problem is the click handler, not the hyprctl command.")
            results.append(False)

    sh("systemctl", "--user", "start", "claude-tray.service")
    print(f"\n{DIM}publisher restarted; real state is back{OFF}")

    print(f"\n{BOLD}{'All checks passed.' if all(results) else 'Something above is BAD -- paste this output.'}{OFF}")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
