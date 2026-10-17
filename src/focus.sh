#!/bin/sh
# Focus a window by niri id or Hyprland address, leaving the pointer where it was.
#
# niri needs nothing special: focusing does not warp the pointer unless
# warp-mouse-to-focus is set. Three Hyprland quirks are handled below:
#
#  1. Lua and classic configs take different dispatch syntax, and quickshell's
#     `usingLua` reports false on a Lua config -- so branching on it picked the
#     form that errors. Try one, fall back to the other.
#
#  2. Focusing a window warps the cursor into it whenever the cursor is
#     elsewhere -- which is always, since you just clicked a row in the bar.
#     Neither `cursor:no_warps` nor a `warp = false` argument stops it on
#     0.56, so the pointer is simply put back afterwards.
#
#  3. `movecursor` is absent from the Lua dispatch table; the equivalent there
#     is `hl.dsp.cursor.move({x, y})`, which is absolute.
#
# Every call is logged before dispatching, so "the click never fired" and "the
# dispatch failed" leave different evidence in focus.log.
#
# usage: focus.sh <niri window id | hyprland address>

log="${XDG_STATE_HOME:-$HOME/.local/state}/claude-tray/focus.log"
mkdir -p "$(dirname "$log")"

# Keep the log from growing without bound.
[ -f "$log" ] && [ "$(wc -c <"$log")" -gt 100000 ] && tail -n 200 "$log" >"$log.tmp" && mv "$log.tmp" "$log"

[ -n "$1" ] || { printf '%s no address given\n' "$(date +%s)" >>"$log"; exit 1; }

if [ -n "$NIRI_SOCKET" ]; then
    out=$(niri msg action focus-window --id "$1" 2>&1)
    status=$?
    printf '%s niri id=%s exit=%s %s\n' "$(date +%s)" "$1" "$status" "$out" >>"$log"
    exit "$status"
fi

before=$(hyprctl cursorpos 2>/dev/null)
printf '%s called addr=%s cursor=%s\n' "$(date +%s)" "$1" "$before" >>"$log"

out=$(hyprctl dispatch focuswindow "address:$1" 2>&1)
[ "$out" = "ok" ] || out=$(hyprctl dispatch "hl.dsp.focus({ window = \"address:$1\" })" 2>&1)

# Put the pointer back if focusing dragged it off.
case "$before" in
    *,*)
        x=${before%%,*}
        y=${before##*, }
        now=$(hyprctl cursorpos 2>/dev/null)
        if [ "$now" != "$before" ]; then
            hyprctl dispatch "hl.dsp.cursor.move({x=$x,y=$y})" >/dev/null 2>&1 ||
                hyprctl dispatch movecursor "$x" "$y" >/dev/null 2>&1
        fi
        ;;
esac

printf '  result: %s | cursor %s -> %s\n' "$out" "$before" "$(hyprctl cursorpos 2>/dev/null)" >>"$log"
[ "$out" = "ok" ]
