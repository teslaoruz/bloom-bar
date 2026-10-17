#!/usr/bin/env bash
# Remove everything this installed: the noctalia plugin, or the caelestia
# overlay (putting caelestia back on its packaged shell).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL="$HOME/.local/share/claude-tray"
PLUGIN="$HOME/.local/share/noctalia/plugins/bloom"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
ok()   { printf '  \033[32mok\033[0m   %s\n' "$1"; }

bold "Stopping services"
systemctl --user disable --now claude-tray.service claude-caelestia-sync.path >/dev/null 2>&1 || true
rm -f "$HOME/.config/systemd/user/claude-tray.service" \
      "$HOME/.config/systemd/user/claude-caelestia-sync.service" \
      "$HOME/.config/systemd/user/claude-caelestia-sync.path"
systemctl --user daemon-reload
ok "services removed"

CAELESTIA=0
if [ -d "$PLUGIN" ]; then
    bold "Removing the noctalia plugin"
    noctalia msg plugins disable teslaoruz/bloom >/dev/null 2>&1 || true
    python3 "$HERE/tools/configure.py" --uninstall --noctalia
    rm -rf "$PLUGIN"
    ok "$PLUGIN"
else
    CAELESTIA=1
    bold "Unwiring Claude Code and the bar"
    python3 "$HERE/tools/configure.py" --uninstall

    bold "Removing the caelestia overlay"
    [ -f "$INSTALL/sync-caelestia.py" ] && python3 "$INSTALL/sync-caelestia.py" --uninstall | sed 's/^/  /' || true
fi

bold "Removing files"
rm -rf "$INSTALL"
ok "$INSTALL"
printf '  state and cache kept: ~/.local/state/claude-tray, ~/.cache/claude-tray\n'

if [ "$CAELESTIA" = 1 ] && [ -n "${WAYLAND_DISPLAY:-}" ] && command -v caelestia >/dev/null; then
    bold "Restarting the shell"
    qs -c caelestia kill >/dev/null 2>&1 || true
    sleep 2
    caelestia shell -d >/dev/null 2>&1 &
    ok "back on the packaged caelestia"
fi
