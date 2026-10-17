#!/usr/bin/env python3
"""Install the Claude Code bar entry into caelestia as an overlay.

caelestia ships in /etc/xdg/quickshell/caelestia and has no extension point,
so ~/.config/quickshell/caelestia (which quickshell prefers) is built as a
*symlink farm*: every upstream file is a symlink back to the package, so a
`pacman -Syu` reaches all of them with no action from anyone.

Only three files are ours, and only two upstream files are real copies because
they need a few lines inserted. Those two are regenerated from the new package
whenever the version changes.

If upstream ever moves the code a patch attaches to, this degrades safely: the
two files fall back to plain symlinks, so you keep a working stock bar and only
lose the Claude entry, with a notification saying so.

    sync-caelestia.py              rebuild the overlay now
    sync-caelestia.py --if-changed only if caelestia-shell was upgraded
    sync-caelestia.py --stash      save our three files as the new pristine copies
    sync-caelestia.py --restart    restart the shell afterwards
    sync-caelestia.py --uninstall  remove the overlay entirely
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Overridable so the installer can point at wherever the distro put it.
SRC = Path(os.environ.get("CAELESTIA_SRC") or "/etc/xdg/quickshell/caelestia")
DST = Path.home() / ".config/quickshell/caelestia"
MINE = Path(__file__).resolve().parent / "caelestia-parts"
STAMP = ".claude-overlay"

OURS = [
    "services/ClaudeCode.qml",
    "modules/bar/components/ClaudeStatus.qml",
    "modules/bar/popouts/Claude.qml",
]

BAR = "modules/bar/Bar.qml"
CONTENT = "modules/bar/popouts/Content.qml"

# (file, marker, anchor, addition). The marker proves the patch is in place;
# the anchor is upstream text the addition is inserted before.
PATCHES = [
    (BAR, 'roleValue: "claude"',
     '            DelegateChoice {\n                roleValue: "clock"\n',
     '            DelegateChoice {\n'
     '                roleValue: "claude"\n'
     '                delegate: EntryWrapper {\n'
     '                    ClaudeStatus {\n'
     '                        objectName: "taskbarClaude"\n'
     '                    }\n'
     '                }\n'
     '            }\n'),

    (BAR, 'id === "claude"',
     '        } else if (id === "activeWindow" ',
     '        } else if (id === "claude") {\n'
     '            popouts.currentName = "claude";\n'
     '            popouts.currentCenter = Qt.binding(() => ch.mapToItem(root, 0, ch.implicitHeight / 2).y);\n'
     '            popouts.hasCurrent = true;\n'),

    (BAR, "onOpenRequested",
     "    Repeater {\n        id: repeater\n",
     "    // `qs -c caelestia ipc call claude open` opens the popout on the focused\n"
     "    // monitor, anchored to the bar entry exactly as hovering it would.\n"
     "    Connections {\n"
     "        target: ClaudeCode\n"
     "\n"
     "        function onOpenRequested(): void {\n"
     "            if (Hypr.focusedMonitor?.name !== root.screen?.name)\n"
     "                return;\n"
     "            for (let i = 0; i < repeater.count; i++) {\n"
     "                const ch = repeater.itemAt(i) as EntryWrapper;\n"
     '                if (ch?.entryId === "claude") {\n'
     '                    root.popouts.currentName = "claude";\n'
     "                    root.popouts.currentCenter = Qt.binding(() => ch.mapToItem(root, 0, ch.implicitHeight / 2).y);\n"
     "                    root.popouts.hasCurrent = true;\n"
     "                    return;\n"
     "                }\n"
     "            }\n"
     "        }\n"
     "    }\n"
     "\n"),

    (CONTENT, 'name: "claude"',
     '        Popout {\n            name: "activewindow"\n',
     '        Popout {\n'
     '            name: "claude"\n'
     "            sourceComponent: Claude {}\n"
     "        }\n"
     "\n"),
]

PATCHED_FILES = sorted({rel for rel, *_ in PATCHES})


def version():
    out = subprocess.run(["pacman", "-Q", "caelestia-shell"],
                         capture_output=True, text=True).stdout.strip()
    return out or "unknown"


def notify(title, body):
    subprocess.Popen(["notify-send", "-a", "Claude Code", title, body],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stash():
    """Save our three files as the pristine copies a rebuild restores from."""
    MINE.mkdir(parents=True, exist_ok=True)
    missing = [r for r in OURS if not (DST / r).is_file()]
    if missing:
        sys.exit(f"not present in the overlay, refusing to stash: {missing}")
    for rel in OURS:
        shutil.copy2(DST / rel, MINE / Path(rel).name)
    print(f"stashed {len(OURS)} files -> {MINE}")


def safe_to_replace():
    """Never delete a directory we did not build."""
    if not DST.exists():
        return True
    if (DST / STAMP).exists():
        return True
    sys.exit(f"{DST} exists but was not created by this script.\n"
             "Move it aside first -- refusing to delete someone else's config.")


def build_farm():
    """Mirror the package tree: real dirs, symlinked files."""
    for src in SRC.rglob("*"):
        rel = src.relative_to(SRC)
        dst = DST / rel
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.is_symlink() or dst.exists():
                dst.unlink()
            dst.symlink_to(src)


def apply_patches():
    """Turn the two patched files from symlinks into patched real copies.

    -> list of files that could not be patched (anchor gone).
    """
    failed = []
    for rel in PATCHED_FILES:
        text = (SRC / rel).read_text()
        for prel, marker, anchor, addition in PATCHES:
            if prel != rel:
                continue
            if marker in text:
                continue
            if anchor not in text:
                failed.append(rel)
                break
            text = text.replace(anchor, addition + anchor, 1)
        else:
            dst = DST / rel
            if dst.is_symlink() or dst.exists():
                dst.unlink()
            dst.write_text(text)
    return failed


def install_ours():
    for rel in OURS:
        target = DST / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink() or target.exists():
            target.unlink()
        shutil.copy2(MINE / Path(rel).name, target)


def build():
    if not MINE.is_dir() or any(not (MINE / Path(r).name).exists() for r in OURS):
        sys.exit(f"pristine copies missing from {MINE}; run --stash first")

    safe_to_replace()
    if DST.exists():
        shutil.rmtree(DST)
    DST.mkdir(parents=True)
    (DST / STAMP).write_text("built by claude-tray sync-caelestia.py\n")

    build_farm()
    links = sum(1 for p in DST.rglob("*") if p.is_symlink())
    print(f"symlinked {links} files -> {SRC}")

    failed = apply_patches()
    if failed:
        # Leave those files as plain symlinks: stock bar, no Claude entry.
        notify("Claude Code bar entry disabled",
               f"caelestia changed upstream ({', '.join(failed)}). "
               "Your bar is fine; re-apply the patch to get the entry back.")
        print(f"\nPATCH FAILED for {failed} -- left as upstream symlinks.")
        print("The bar still works; the Claude entry is absent.")
    else:
        install_ours()
        for rel, marker, *_ in PATCHES:
            assert marker in (DST / rel).read_text(), f"{marker!r} missing from {rel}"
        print(f"patched {len(PATCHED_FILES)} files, installed {len(OURS)} of ours")

    (DST / ".forked-from").write_text(version() + "\n")
    print(f"overlay built against {version()}")
    return not failed


def restart_shell():
    # From a systemd unit there may be no graphical session to talk to; in that
    # case just say the overlay is ready and let the next login pick it up.
    if not os.environ.get("WAYLAND_DISPLAY"):
        notify("Claude Code bar entry re-applied",
               "Restart the shell to load it: qs -c caelestia kill; caelestia shell -d")
        print("no WAYLAND_DISPLAY; skipped restart")
        return
    subprocess.run(["qs", "-c", "caelestia", "kill"],
                   capture_output=True, timeout=15)
    subprocess.Popen(["caelestia", "shell", "-d"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    print("shell restarted")


def uninstall():
    safe_to_replace()
    if DST.exists():
        shutil.rmtree(DST)
        print(f"removed {DST} -- caelestia falls back to {SRC}")
    print("also drop the \"claude\" entry from ~/.config/caelestia/shell.json")


def main():
    args = sys.argv[1:]
    if "--stash" in args:
        return stash()
    if "--uninstall" in args:
        return uninstall()

    if "--if-changed" in args:
        stamp = DST / ".forked-from"
        current = version()
        if stamp.exists() and stamp.read_text().strip() == current:
            return  # nothing to do; stay quiet, this runs from a path unit
        print(f"caelestia changed -> {current}, rebuilding overlay")

    ok = build()
    if "--restart" in args:
        restart_shell()
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
