#!/usr/bin/env python3
"""Statusline shim: siphon off the real rate limits, then run yours unchanged.

Claude Code hands the statusLine command a JSON payload on stdin that contains
`rate_limits` -- the same five-hour and seven-day percentages `/status` shows.
Nothing else on disk has them, so this is the only honest source.

This script writes those to limits.json and then execs whatever statusline you
had before, feeding it the identical stdin. Your statusline is unchanged; if
anything here fails, the wrapped command still runs.

Wrapped command lives in wrapped-statusline.txt next to this file.
"""

import json
import os
import time
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
WRAPPED = HERE / "wrapped-statusline.txt"
STATE = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "claude-tray"
LIMITS = STATE / "limits.json"


def capture(payload):
    limits = payload.get("rate_limits") or {}
    if not limits:
        return
    out = {"updated": time.time()}
    for key in ("five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet"):
        block = limits.get(key)
        if isinstance(block, dict) and block.get("used_percentage") is not None:
            out[key] = {
                "used": block.get("used_percentage"),
                "resets_at": block.get("resets_at"),
            }
    ctx = payload.get("context_window") or {}
    if ctx.get("used_percentage") is not None:
        out["context"] = {
            "used": ctx.get("used_percentage"),
            "size": ctx.get("context_window_size"),
        }
    model = payload.get("model") or {}
    if model.get("display_name"):
        out["model"] = model["display_name"]

    STATE.mkdir(parents=True, exist_ok=True)
    tmp = LIMITS.with_suffix(".tmp")
    tmp.write_text(json.dumps(out))
    tmp.replace(LIMITS)


def main():
    raw = sys.stdin.read()

    try:
        capture(json.loads(raw))
    except Exception:
        pass  # never let our bookkeeping break the user's statusline

    try:
        command = WRAPPED.read_text().strip()
    except OSError:
        command = ""
    if not command:
        return

    # exec, not fork: the wrapped statusline inherits our stdout directly and
    # this process disappears, which keeps the added latency to interpreter
    # start-up alone.
    # A temp file rather than a pipe: a pipe deadlocks if the payload ever
    # outgrows the 64K buffer, and nothing here is worth that risk.
    with tempfile.TemporaryFile() as fh:
        fh.write(raw.encode())
        fh.seek(0)
        os.dup2(fh.fileno(), 0)
        os.execvp("sh", ["sh", "-c", command])


if __name__ == "__main__":
    main()
