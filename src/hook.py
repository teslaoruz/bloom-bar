#!/usr/bin/env python3
"""Claude Code hook -> per-session state file, and starts the tray on demand.

Reads the hook payload on stdin, writes one small json per session, exits.
Must stay fast: it runs on every prompt and every tool call.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "claude-tray"
SESSIONS = STATE / "sessions"
EVENTLOG = STATE / "events.log"

# hook event -> state. Notification is resolved by its message text.
#
# SubagentStop is deliberately absent: a background agent can finish minutes
# after the turn it belonged to, and treating that as "working" flipped an
# idle session back to spinning with nothing left to clear it.
EVENTS = {
    "SessionStart": "idle",
    "UserPromptSubmit": "working",
    "PreToolUse": "working",
    "Stop": "done",
}


def compositor_windows():
    """{pid: window} from Hyprland (address) or niri (id), whichever is running."""
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        cmd, key = ["hyprctl", "-j", "clients"], "address"
    elif os.environ.get("NIRI_SOCKET"):
        cmd, key = ["niri", "msg", "-j", "windows"], "id"
    else:
        return {}
    try:
        clients = json.loads(subprocess.run(
            cmd, capture_output=True, text=True, timeout=2
        ).stdout)
    except Exception:
        return {}
    return {c.get("pid"): str(c.get(key)) for c in clients if c.get("pid")}


def find_window(pid):
    """The window owning `pid` or one of its ancestors."""
    by_pid = compositor_windows()
    if not by_pid:
        return None
    for _ in range(12):  # walk up the process tree
        if pid in by_pid:
            return by_pid[pid]
        try:
            stat = Path(f"/proc/{pid}/stat").read_text()
            pid = int(stat[stat.rindex(")") + 2:].split()[1])
        except Exception:
            return None
        if pid <= 1:
            return None
    return None


def ensure_daemon():
    """Start the tray if it is not already holding its lock."""
    try:
        import fcntl
        STATE.mkdir(parents=True, exist_ok=True)
        with (STATE / "daemon.lock").open("a+") as fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return  # someone holds it -> daemon is alive
            fcntl.flock(fh, fcntl.LOCK_UN)
    except Exception:
        pass
    log = (STATE / "daemon.log").open("a")
    subprocess.Popen(
        [sys.executable, str(HERE / "daemon.py")],
        stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True,
    )


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    event = payload.get("hook_event_name") or (sys.argv[1] if len(sys.argv) > 1 else "")
    sid = payload.get("session_id")
    if not sid:
        return

    SESSIONS.mkdir(parents=True, exist_ok=True)
    path = SESSIONS / f"{sid}.json"

    try:  # a rolling trace of what Claude Code actually sends us
        if EVENTLOG.exists() and EVENTLOG.stat().st_size > 200_000:
            EVENTLOG.write_text("".join(EVENTLOG.read_text().splitlines(True)[-500:]))
        with EVENTLOG.open("a") as fh:
            fh.write(f"{time.time():.1f} {event} {sid[:8]} {payload.get('message', '')[:40]}\n")
    except Exception:
        pass

    if event == "SessionEnd":
        path.unlink(missing_ok=True)
        return

    if event == "Notification":
        msg = (payload.get("message") or "").lower()
        if "permission" in msg or "approve" in msg or "confirm" in msg:
            state = "waiting"
        elif "waiting for your input" in msg:
            state = "idle"  # Claude Code telling us plainly that it is done
        else:
            return
    else:
        state = EVENTS.get(event)
        if state is None:
            return

    try:
        old = json.loads(path.read_text())
    except Exception:
        old = {}

    # ponytail: only SessionStart pays for the compositor round trip.
    window = old.get("window")
    if event == "SessionStart" or not window:
        window = find_window(os.getppid()) or window

    record = {
        "session_id": sid,
        "state": state,
        "cwd": payload.get("cwd") or old.get("cwd") or "",
        "window": window,
        # Our parent is the claude process. SessionEnd does not fire when a
        # terminal is killed, so the daemon uses this to drop dead sessions
        # instead of leaving them spinning forever.
        "pid": old.get("pid") or os.getppid(),
        "ts": time.time(),
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record))
    tmp.replace(path)

    if event == "SessionStart":
        ensure_daemon()


if __name__ == "__main__":
    main()
