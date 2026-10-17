#!/usr/bin/env bash
# Install the Claude Code bar entry for caelestia (Hyprland) or noctalia (niri).
#
# Picks noctalia when it is installed, caelestia otherwise; force one with
# --noctalia or --caelestia.
#
# Safe to re-run: every step is idempotent, and the two config files it edits
# (~/.claude/settings.json and the bar config) are backed up once, the first time.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL="$HOME/.local/share/claude-tray"
UNITS="$HOME/.config/systemd/user"
PLUGIN="$HOME/.local/share/noctalia/plugins/bloom"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
ok()   { printf '  \033[32mok\033[0m   %s\n' "$1"; }
warn() { printf '  \033[33mnote\033[0m %s\n' "$1"; }
die()  { printf '  \033[31mfail\033[0m %s\n' "$1" >&2; exit 1; }

TARGET=""
case "${1:-}" in
    --noctalia) TARGET=noctalia ;;
    --caelestia) TARGET=caelestia ;;
    "") command -v noctalia >/dev/null && TARGET=noctalia || TARGET=caelestia ;;
    *) die "unknown option $1 (use --noctalia or --caelestia)" ;;
esac

bold "Checking what this needs ($TARGET)"

if [ "$TARGET" = noctalia ]; then
    for cmd in python3 noctalia niri; do
        command -v "$cmd" >/dev/null || die "$cmd is not installed"
    done
    ok "python3, noctalia, niri"
else
    for cmd in python3 qs hyprctl; do
        command -v "$cmd" >/dev/null || die "$cmd is not installed"
    done
    ok "python3, quickshell, hyprctl"

    CAELESTIA=""
    for dir in /etc/xdg/quickshell/caelestia /usr/share/quickshell/caelestia; do
        [ -f "$dir/shell.qml" ] && CAELESTIA="$dir" && break
    done
    [ -n "$CAELESTIA" ] || die "caelestia-shell not found; install it first"
    ok "caelestia at $CAELESTIA"

    # quickshell segfaults on shutdown when it was built against a different Qt
    # than the one installed. It reports this itself; surface it here so a crash
    # after install is not mistaken for this widget's doing.
    if qs --version 2>&1 | grep -qi 'built against Qt' ||
       timeout 5 qs -c caelestia --help 2>&1 | grep -qi 'must be rebuilt'; then
        warn "quickshell was built against a different Qt than is installed;"
        warn "it will segfault on shutdown until rebuilt:  paru -S --rebuild quickshell-git"
    fi
fi

python3 -c 'import gi; gi.require_version("GLib", "2.0")' 2>/dev/null ||
    die "python-gobject is not installed (the daemon needs GLib)"
command -v notify-send >/dev/null || warn "notify-send missing: no permission notifications"
[ -d "$HOME/.claude" ] || warn "~/.claude missing: run Claude Code once, then re-run this"

bold "Installing files"
mkdir -p "$INSTALL/icons" "$UNITS"
install -m 755 "$HERE"/src/*.py "$HERE"/src/focus.sh "$INSTALL/"
install -m 644 "$HERE"/src/icons/* "$INSTALL/icons/"
install -m 644 "$HERE"/systemd/claude-tray.service "$UNITS/"
ok "$INSTALL"

if [ "$TARGET" = noctalia ]; then
    # Installed from the plugin store already: only the backend is needed, and a
    # local copy with the same id would shadow the store's updates.
    if noctalia msg plugins list 2>/dev/null | grep -q '^teslaoruz/bloom \[community\]'; then
        ok "plugin comes from the noctalia store; installing the backend only"
    else
        mkdir -p "$PLUGIN"
        install -m 644 "$HERE"/noctalia/* "$PLUGIN/"
        ok "$PLUGIN"
    fi
else
    mkdir -p "$INSTALL/caelestia-parts"
    install -m 644 "$HERE"/qml/*.qml "$INSTALL/caelestia-parts/"
    install -m 644 "$HERE"/systemd/claude-caelestia-sync.* "$UNITS/"

    bold "Building the caelestia overlay"
    # A symlink farm over the packaged shell: upstream updates flow through
    # untouched, and only the two patched files are ever regenerated.
    CAELESTIA_SRC="$CAELESTIA" python3 "$INSTALL/sync-caelestia.py" | sed 's/^/  /'
fi

bold "Wiring into Claude Code and the bar"
python3 "$HERE/tools/configure.py" --install "--$TARGET"

bold "Starting services"
systemctl --user daemon-reload
systemctl --user enable --now claude-tray.service >/dev/null 2>&1
ok "publisher: $(systemctl --user is-active claude-tray.service)"
if [ "$TARGET" = caelestia ]; then
    systemctl --user enable --now claude-caelestia-sync.path >/dev/null 2>&1
    ok "upgrade watcher: $(systemctl --user is-active claude-caelestia-sync.path)"
fi

if [ "$TARGET" = noctalia ]; then
    bold "Enabling the plugin"
    # noctalia picks up local plugins and config.toml edits live; no restart.
    if noctalia msg plugins enable teslaoruz/bloom >/dev/null 2>&1; then
        ok "teslaoruz/bloom enabled"
    else
        warn "noctalia is not running; enable it later: noctalia msg plugins enable teslaoruz/bloom"
    fi
    WHERE="on the left, after the workspaces. Click it for the panel"
else
    bold "Restarting the shell"
    if [ -n "${WAYLAND_DISPLAY:-}" ] && command -v caelestia >/dev/null; then
        qs -c caelestia kill >/dev/null 2>&1 || true
        sleep 2
        caelestia shell -d >/dev/null 2>&1 &
        sleep 6
        ok "caelestia restarted"
    else
        warn "not in a Wayland session; restart the shell yourself:"
        warn "  qs -c caelestia kill; caelestia shell -d"
    fi
    WHERE="above the clock. Hover it for the popout"
fi

cat <<EOF

$(bold "Done.")

  The Claude entry appears $WHERE,
  click a session row to focus that terminal.

  Limits show up once a Claude Code session renders its statusline -- open
  one and they will populate within a second or two.

  Remove everything:        $HERE/uninstall.sh
EOF
