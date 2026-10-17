#!/usr/bin/env python3
"""Publishes Claude Code status for the caelestia bar.

Merges the per-session json files hook.py writes with the usage figures from
usage.py into one status.json. The bar entry and its popout live inside
caelestia itself (~/.config/quickshell/caelestia) and only read that file, so
this process draws nothing -- it just keeps the file current and raises a
notification when a session starts waiting on you.
"""

import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from gi.repository import GLib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import usage  # noqa: E402

HERE = Path(__file__).resolve().parent
ICONS = HERE / "icons"
STATE = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "claude-tray"
SESSIONS = STATE / "sessions"
STATUS = STATE / "status.json"
LIMITS = STATE / "limits.json"

STATE_POLL = 1        # seconds
USAGE_POLL = 30       # seconds
STALE = 3600          # backstop for records written before pids were tracked

# A turn that goes this long without a single hook firing is not a turn any
# more -- Stop was missed (crash, killed terminal, hook error). Without this
# the bar can spin for ever on a session that is really sitting idle.
WORKING_TIMEOUT = 150
# "Done" is worth showing briefly, then it should settle rather than sit there.
DONE_TIMEOUT = 60

# Worst state wins for the bar icon, highest number first.
RANK = {"waiting": 3, "working": 2, "done": 1, "idle": 0}


def alive(pid):
    """Is that claude process still around? Cheap: /proc is enough."""
    if not pid:
        return True  # written before we recorded pids; fall back to age
    try:
        return Path(f"/proc/{pid}").exists()
    except OSError:
        return True


def decay(rec, now):
    """Age a state out when the hook that should have cleared it never came.

    The state file is only ever written by a hook, so a session stuck at
    "working" means we missed Stop. Time is the only evidence available, so
    use it rather than spinning for ever.
    """
    age = now - rec.get("ts", 0)
    state = rec.get("state")
    if state == "working" and age > WORKING_TIMEOUT:
        return {**rec, "state": "idle", "stale": True}
    if state == "done" and age > DONE_TIMEOUT:
        return {**rec, "state": "idle"}
    return rec


def read_sessions():
    out = []
    now = time.time()
    if not SESSIONS.is_dir():
        return out
    for path in SESSIONS.glob("*.json"):
        try:
            rec = json.loads(path.read_text())
        except Exception:
            continue
        # A killed terminal never sends SessionEnd, which used to leave the
        # bar spinning on a session that no longer exists.
        if not alive(rec.get("pid")) or now - rec.get("ts", 0) > STALE:
            path.unlink(missing_ok=True)
            continue
        out.append(decay(rec, now))
    out.sort(key=lambda r: (-RANK.get(r.get("state"), 0), -r.get("ts", 0)))
    return out


def read_limits():
    """The real /status percentages, captured by statusline.py.

    Only Claude Code itself knows these, and only via the statusLine payload,
    so they are as fresh as the last statusline render of any session.
    """
    try:
        return json.loads(LIMITS.read_text())
    except Exception:
        return {}


def notify(title, body):
    subprocess.Popen(
        ["notify-send", "-a", "Claude Code", "-i", str(ICONS / "claude-waiting.svg"), title, body],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Publisher:
    def __init__(self):
        self.sessions = []
        self.usage = usage.summary()
        self.state = "idle"
        self.notified = set()

        self.refresh_state()
        GLib.timeout_add_seconds(STATE_POLL, self.refresh_state)
        GLib.timeout_add_seconds(USAGE_POLL, self.refresh_usage)

    def refresh_usage(self):
        try:
            self.usage = usage.summary()
        except Exception as exc:  # a bad read must never kill the daemon
            print(f"usage error: {exc}", file=sys.stderr, flush=True)
        self.publish()
        return True

    def refresh_state(self):
        sessions = read_sessions()
        key = lambda ss: [(s.get("session_id"), s.get("state"), s.get("ts")) for s in ss]  # noqa: E731
        changed = key(sessions) != key(self.sessions)
        self.sessions = sessions

        waiting = {s["session_id"] for s in sessions if s.get("state") == "waiting"}
        for sid in waiting - self.notified:
            rec = next(s for s in sessions if s["session_id"] == sid)
            notify("Claude Code needs permission", Path(rec.get("cwd") or "~").name or "session")
        self.notified = waiting

        state = sessions[0]["state"] if sessions else "idle"
        if state != self.state or changed:
            self.state = state
            self.publish()
        return True

    def publish(self):
        STATE.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated": time.time(),
            "state": self.state,
            "sessions": self.sessions,
            "usage": self.usage,
            "limits": read_limits(),
        }
        tmp = STATUS.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload))
        tmp.replace(STATUS)


def main():
    STATE.mkdir(parents=True, exist_ok=True)
    lock = (STATE / "daemon.lock").open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("already running", file=sys.stderr)
        return
    Publisher()
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
