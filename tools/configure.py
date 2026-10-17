#!/usr/bin/env python3
"""Wire (or unwire) the widget into Claude Code and the bar's own config.

Every edit here is idempotent and backed up, because it touches two files the
user owns: ~/.claude/settings.json and the bar config -- caelestia's
~/.config/caelestia/shell.json, or noctalia's ~/.config/noctalia/config.toml.

    configure.py --install [--noctalia]
    configure.py --uninstall [--noctalia]
"""

import json
import re
import shutil
import sys
from pathlib import Path

HOME = Path.home()
INSTALL = HOME / ".local/share/claude-tray"
SETTINGS = HOME / ".claude/settings.json"
SHELL_JSON = HOME / ".config/caelestia/shell.json"
NOCTALIA_TOML = HOME / ".config/noctalia/config.toml"
NOCTALIA_WIDGET = "bloom"
NOCTALIA_TYPE = "teslaoruz/bloom:status"
WRAPPED = INSTALL / "wrapped-statusline.txt"

HOOK = str(INSTALL / "hook.py")
STATUSLINE = f"python3 -S {INSTALL / 'statusline.py'}"
SUFFIX = ".bak-caelestia-claude-code"

# Deliberately not PostToolUse (doubles the per-tool cost for nothing) and not
# SubagentStop (fires long after a turn ends, which used to leave the bar
# spinning on an idle session).
EVENTS = ["SessionStart", "UserPromptSubmit", "PreToolUse", "Stop",
          "Notification", "SessionEnd"]

DEFAULT_ENTRIES = [
    {"id": "logo", "enabled": True},
    {"id": "workspaces", "enabled": True},
    {"id": "spacer", "enabled": True},
    {"id": "activeWindow", "enabled": True},
    {"id": "spacer", "enabled": True},
    {"id": "tray", "enabled": True},
    {"id": "claude", "enabled": True},
    {"id": "clock", "enabled": True},
    {"id": "statusIcons", "enabled": True},
    {"id": "power", "enabled": True},
]


def load(path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    except ValueError:
        sys.exit(f"{path} is not valid JSON; fix or move it aside first")


def save(path, data, backup=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    if backup and path.exists() and not path.with_suffix(path.suffix + SUFFIX).exists():
        shutil.copy2(path, str(path) + SUFFIX)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


# ---------- Claude Code hooks ----------

def wire_hooks(data):
    hooks = data.setdefault("hooks", {})
    added = []
    for event in EVENTS:
        entries = hooks.setdefault(event, [])
        if any(HOOK in h.get("command", "")
               for entry in entries for h in entry.get("hooks", [])):
            continue
        entries.append({"matcher": ".*", "hooks": [{"type": "command", "command": HOOK}]})
        added.append(event)
    return added


def unwire_hooks(data):
    hooks = data.get("hooks", {})
    removed = []
    for event in list(hooks):
        kept = [e for e in hooks[event]
                if not any(HOOK in h.get("command", "") for h in e.get("hooks", []))]
        if len(kept) != len(hooks[event]):
            removed.append(event)
        hooks[event] = kept
        if not kept:
            del hooks[event]
    return removed


# ---------- statusline shim ----------

def wrap_statusline(data):
    """Put our shim in front of whatever statusline is configured."""
    current = (data.get("statusLine") or {}).get("command", "")
    if "claude-tray/statusline.py" in current:
        return "already wrapped"          # never wrap ourselves twice
    WRAPPED.parent.mkdir(parents=True, exist_ok=True)
    WRAPPED.write_text(current + "\n")    # empty is fine: shim just captures
    data["statusLine"] = {"type": "command", "command": STATUSLINE}
    return f"wrapped {current!r}" if current else "installed (no previous statusline)"


def unwrap_statusline(data):
    current = (data.get("statusLine") or {}).get("command", "")
    if "claude-tray/statusline.py" not in current:
        return "not wrapped"
    original = ""
    try:
        original = WRAPPED.read_text().strip()
    except OSError:
        pass
    if original:
        data["statusLine"] = {"type": "command", "command": original}
        return f"restored {original!r}"
    data.pop("statusLine", None)
    return "removed (there was none before)"


# ---------- caelestia bar entry ----------

def add_entry(data):
    bar = data.setdefault("bar", {})
    entries = bar.get("entries")
    if not entries:
        bar["entries"] = list(DEFAULT_ENTRIES)
        return "added the default bar layout with claude in it"
    if any(e.get("id") == "claude" for e in entries):
        return "already present"
    at = next((i for i, e in enumerate(entries) if e.get("id") == "clock"), len(entries))
    entries.insert(at, {"id": "claude", "enabled": True})
    return f"inserted at position {at}"


def remove_entry(data):
    entries = (data.get("bar") or {}).get("entries")
    if not entries:
        return "nothing to remove"
    kept = [e for e in entries if e.get("id") != "claude"]
    if len(kept) == len(entries):
        return "not present"
    data["bar"]["entries"] = kept
    return "removed"


# ---------- noctalia bar entry ----------
#
# Text edits rather than a TOML round trip: the stdlib only reads TOML, and a
# rewrite would drop the user's comments. Only two things are touched -- the
# first bar's `start` list and our own two widget tables.

START_LIST = re.compile(r'(?m)^start\s*=\s*\[([^\]]*)\]')
ENTRIES = f'"{NOCTALIA_WIDGET}-gap", "{NOCTALIA_WIDGET}"'
WIDGET_BLOCK = (f'\n# Claude Code status (teslaoruz/bloom, from bloom-bar).\n'
                f'[widget.{NOCTALIA_WIDGET}-gap]\ntype = "spacer"\nlength = 16\n\n'
                f'[widget.{NOCTALIA_WIDGET}]\ntype = "{NOCTALIA_TYPE}"\n')


def add_noctalia_widget(text):
    if NOCTALIA_TYPE in text:
        return text, "already present"
    bar = text.find("[bar.")
    match = START_LIST.search(text, bar) if bar >= 0 else None
    if not match:
        return text, (f'no bar `start = [...]` list found; add {ENTRIES} to a bar section '
                      f'and the [widget.{NOCTALIA_WIDGET}] table with type = "{NOCTALIA_TYPE}"')
    items = match.group(1)
    if '"workspaces"' in items:
        items, where = items.replace('"workspaces"', f'"workspaces", {ENTRIES}', 1), "after the workspaces"
    else:
        items, where = (f"{items.rstrip().rstrip(',')}, {ENTRIES}" if items.strip() else ENTRIES), "at the end of the left side"
    text = text[:match.start(1)] + items + text[match.end(1):]
    return text.rstrip("\n") + "\n" + WIDGET_BLOCK, f"added {where}"


def remove_noctalia_widget(text):
    if NOCTALIA_TYPE not in text:
        return text, "not present"
    text = text.replace(WIDGET_BLOCK, "\n")
    text = re.sub(rf',?\s*{re.escape(ENTRIES)}', "", text, count=1)
    return text, "removed"


def main():
    noctalia = "--noctalia" in sys.argv

    if "--uninstall" in sys.argv:
        settings = load(SETTINGS)
        print("  hooks removed from:", ", ".join(unwire_hooks(settings)) or "nothing")
        print("  statusline:", unwrap_statusline(settings))
        save(SETTINGS, settings, backup=False)

        if noctalia:
            if NOCTALIA_TOML.exists():
                text, note = remove_noctalia_widget(NOCTALIA_TOML.read_text())
                NOCTALIA_TOML.write_text(text)
                print("  bar entry:", note)
            return
        shell = load(SHELL_JSON)
        print("  bar entry:", remove_entry(shell))
        save(SHELL_JSON, shell, backup=False)
        return

    settings = load(SETTINGS)
    added = wire_hooks(settings)
    print("  hooks added:", ", ".join(added) if added else "none (already wired)")
    print("  statusline:", wrap_statusline(settings))
    save(SETTINGS, settings)

    if noctalia:
        text, note = add_noctalia_widget(NOCTALIA_TOML.read_text() if NOCTALIA_TOML.exists() else "")
        if text:
            backup = NOCTALIA_TOML.with_name(NOCTALIA_TOML.name + SUFFIX)
            if NOCTALIA_TOML.exists() and not backup.exists():
                shutil.copy2(NOCTALIA_TOML, backup)
            NOCTALIA_TOML.write_text(text)
        print("  bar entry:", note)
        return
    shell = load(SHELL_JSON)
    print("  bar entry:", add_entry(shell))
    save(SHELL_JSON, shell)


if __name__ == "__main__":
    main()
