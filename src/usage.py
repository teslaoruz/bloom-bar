#!/usr/bin/env python3
"""Token and request accounting over ~/.claude/projects/*.jsonl.

ponytail: hourly buckets + per-file byte offsets in one json cache. A poll
only parses bytes appended since last time, so the 180MB corpus is read once.
"""

import json
import os
import sys
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "claude-tray" / "usage.json"

KEEP_DAYS = 8          # buckets older than this are pruned
SESSION_HOURS = 5      # Claude Code rolling session block
WEEK_DAYS = 7

def _account(usage):
    """-> total tokens for one API call. Cache tokens count toward the total."""
    return ((usage.get("input_tokens") or 0)
            + (usage.get("output_tokens") or 0)
            + (usage.get("cache_creation_input_tokens") or 0)
            + (usage.get("cache_read_input_tokens") or 0))


def _load():
    try:
        data = json.loads(CACHE.read_text())
        if data.get("version") == 2:
            return data
    except Exception:
        pass
    return {"version": 2, "files": {}, "hours": {}}


def _save(cache):
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache))
    tmp.replace(CACHE)


def _prune(cache, now):
    cutoff = (now - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%dT%H")
    cache["hours"] = {h: v for h, v in cache["hours"].items() if h >= cutoff}


def _scan_file(path, entry, hours):
    """Parse bytes appended since last scan. Mutates entry and hours."""
    size = path.stat().st_size
    offset = entry.get("offset", 0)
    if size < offset:  # truncated or rotated -> start over
        offset = 0
        entry["seen"] = []
    if size == offset:
        return
    # ponytail: adjacent duplicates share a message id (one assistant turn can
    # span several jsonl lines). A short window kills them without a global set.
    seen = deque(entry.get("seen", []), maxlen=32)
    with path.open("r", errors="replace") as fh:
        fh.seek(offset)
        for line in fh:
            if not line.endswith("\n"):  # partial write, stop before it
                break
            offset += len(line.encode("utf-8", "replace"))
            if '"usage"' not in line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            msg = rec.get("message") or {}
            usage = msg.get("usage")
            ts = rec.get("timestamp")
            if not usage or not ts:
                continue
            mid = msg.get("id") or rec.get("requestId")
            if mid and mid in seen:
                continue
            if mid:
                seen.append(mid)
            bucket = hours.setdefault(ts[:13], [0, 0])
            bucket[0] += _account(usage)
            bucket[1] += 1  # one API request
    entry["offset"] = offset
    entry["seen"] = list(seen)


def refresh(now=None):
    """Update the cache from disk. -> the cache dict."""
    now = now or datetime.now(timezone.utc)
    cache = _load()
    files = cache["files"]
    hours = cache["hours"]
    old = (now - timedelta(days=KEEP_DAYS)).timestamp()
    for path in PROJECTS.glob("*/*.jsonl"):
        key = str(path)
        try:
            st = path.stat()
        except OSError:
            continue
        entry = files.get(key)
        if entry is None:
            # Never seen and already outside the window: record its size so we
            # never pay to parse it. Only recent history is worth reading.
            files[key] = {"offset": 0 if st.st_mtime >= old else st.st_size, "seen": []}
            entry = files[key]
        elif st.st_mtime < old and entry.get("offset") == st.st_size:
            continue
        try:
            _scan_file(path, entry, hours)
        except OSError:
            continue
    _prune(cache, now)
    _save(cache)
    return cache


def _session_block(hour_keys, now):
    """-> start of the current 5h block, or None. A gap >= 5h opens a new one."""
    if not hour_keys:
        return None
    times = [datetime.strptime(h, "%Y-%m-%dT%H").replace(tzinfo=timezone.utc) for h in sorted(hour_keys)]
    span = timedelta(hours=SESSION_HOURS)
    start = prev = times[0]
    for t in times[1:]:
        if t - start >= span or t - prev >= span:
            start = t
        prev = t
    return start if now - start < span else None




def summary(cache=None, now=None):
    now = now or datetime.now(timezone.utc)
    cache = cache if cache is not None else refresh(now)
    hours = cache["hours"]

    def total(predicate):
        tok = req = 0
        for key, (t, r) in hours.items():
            when = datetime.strptime(key, "%Y-%m-%dT%H").replace(tzinfo=timezone.utc)
            if predicate(when):
                tok += t
                req += r
        return int(tok), int(req)

    start = _session_block(hours.keys(), now)
    if start:
        end = start + timedelta(hours=SESSION_HOURS)
        s_tok, s_req = total(lambda w: start <= w < end)
        remaining = int((end - now).total_seconds())
    else:
        s_tok, s_req, remaining = 0, 0, 0

    week_start = now - timedelta(days=WEEK_DAYS)
    w_tok, w_req = total(lambda w: w >= week_start)

    # Per-day series for the popout's chart. No plan quota is published
    # anywhere readable, so the week is shown as its own shape.
    days = []
    for back in range(WEEK_DAYS - 1, -1, -1):
        day = (now - timedelta(days=back)).strftime("%Y-%m-%d")
        tok = req = 0
        for key, (t, r) in hours.items():
            if key[:10] == day:
                tok += t
                req += r
        days.append({"date": day, "tokens": int(tok), "requests": int(req)})

    return {
        "session": {
            "tokens": s_tok,
            "requests": s_req,
            "remaining": remaining,
            "elapsed": int((now - start).total_seconds()) if start else 0,
            "window": SESSION_HOURS * 3600,
        },
        "week": {"tokens": w_tok, "requests": w_req, "daily": days},
    }


def human_tokens(n):
    for limit, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if n >= limit:
            return f"{n / limit:.1f}{suffix}"
    return str(n)


def human_left(seconds):
    if seconds <= 0:
        return "expired"
    h, m = divmod(seconds // 60, 60)
    return f"{h}h{m:02d}m left" if h else f"{m}m left"


def _selftest():
    now = datetime(2026, 8, 27, 12, 30, tzinfo=timezone.utc)
    assert _account({"input_tokens": 10, "output_tokens": 5,
                     "cache_creation_input_tokens": 1,
                     "cache_read_input_tokens": 2}) == 18

    # A >=5h gap opens a new block; the older hours must not count.
    hours = {
        "2026-08-27T00": [100, 1],   # old block
        "2026-08-27T10": [200, 2],   # current block starts here
        "2026-08-27T12": [300, 3],
        "2026-08-20T09": [999, 9],   # outside the 7d window
    }
    start = _session_block(hours.keys(), now)
    assert start == datetime(2026, 8, 27, 10, tzinfo=timezone.utc), start

    out = summary({"version": 2, "files": {}, "hours": hours}, now)
    assert out["session"]["tokens"] == 500, out
    assert out["session"]["requests"] == 5, out
    assert out["session"]["remaining"] == int(2.5 * 3600), out
    assert out["session"]["elapsed"] == int(2.5 * 3600), out
    assert out["week"]["tokens"] == 600, out  # the 08-20 hour is excluded
    assert out["week"]["requests"] == 6, out
    assert len(out["week"]["daily"]) == 7, out
    assert out["week"]["daily"][-1] == {"date": "2026-08-27", "tokens": 600, "requests": 6}, out

    assert _session_block([], now) is None
    assert human_tokens(4_100_000) == "4.1M"
    assert human_left(7860) == "2h11m left"
    assert human_left(0) == "expired"
    print("ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        t0 = time.time()
        print(json.dumps(summary(), indent=2))
        print(f"# {time.time() - t0:.2f}s", file=sys.stderr)
