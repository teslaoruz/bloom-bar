# Bloom

Claude Code status on your bar, for [caelestia](https://github.com/caelestia-dots/shell)
(Hyprland) and [noctalia](https://github.com/noctalia-dev/noctalia) (niri): a
flower that spins while Claude works, and a panel with the **real** `/status`
limits, your live sessions and the last 7 days of tokens.

```
✽  Claude Code
   Working · 2 sessions · Opus 5

   Session   ████████░░  73%   resets 20:40
   Week      ██░░░░░░░░  17%   resets Mon 09:00

   SESSIONS
   ● api          ~/code/api                     Working  12s
   ● website      ~/code/website                 Done      4m

   LAST 7 DAYS
   134.7M tok                            561 req
   ▁ ▁ ▁ ▂ █ ▅ ▃
   F S S M T W T
```

Bloom is an unofficial community project. It is not made, endorsed or
supported by Anthropic. "Claude" and "Claude Code" are Anthropic's trademarks
and are used here only to say which tool Bloom works with.

## Install

```sh
git clone https://github.com/teslaoruz/bloom-bar
cd bloom-bar
./install.sh
```

Safe to re-run. The two config files it edits are backed up once, the first
time, as `*.bak-caelestia-claude-code`.

Needs Python 3 with python-gobject and Claude Code, plus either
caelestia-shell, quickshell and Hyprland, or noctalia v5 and niri.

Remove it with `./uninstall.sh`.

### Noctalia (niri)

`install.sh` picks noctalia when it is installed (force either with
`--noctalia` / `--caelestia`). The data side is identical; only the drawing
changes:

- `noctalia/` is the Luau plugin `teslaoruz/bloom`, copied to
  `~/.local/share/noctalia/plugins/bloom`. Its bar widget shows a dim flower
  when idle, the spinner while working, and the session limit; click it for
  the panel. If you installed Bloom from the noctalia plugin store, run
  `./install.sh` anyway: it sets up the backend and leaves the store copy alone.
- It goes on the left after `workspaces`, behind a 16px spacer: two tables,
  `[widget.bloom-gap]` and `[widget.bloom]`, are appended to
  `~/.config/noctalia/config.toml`. Move them by editing the `start` list.
- Session rows focus their terminal with `niri msg action focus-window`;
  `hook.py` finds the window id from `niri msg -j windows` by walking up from
  the claude pid.
- No overlay and no upgrade watcher: noctalia loads local plugins directly.

Open the panel from a keybind with
`noctalia msg panel-toggle teslaoruz/bloom:panel`.

## Where the numbers come from

Claude Code does not write its rate limits anywhere on disk. The only place
they surface is the JSON payload handed to the `statusLine` command, which
carries `rate_limits.five_hour` and `rate_limits.seven_day` — exactly what
`/status` prints.

So `statusline.py` sits in front of whatever statusline you already use: it
copies those percentages into `limits.json`, then execs your real statusline
command with the identical stdin. Your statusline is untouched, and if anything
in the shim fails your command still runs. The original is recorded in
`wrapped-statusline.txt` and restored on uninstall.

Token and request counts come separately from `~/.claude/projects/*.jsonl`.
There are no dollar figures — on a subscription they mean nothing.

## How it survives caelestia updates

caelestia ships in `/etc/xdg/quickshell/caelestia` and has no extension point,
so `~/.config/quickshell/caelestia` (which quickshell prefers) is built as a
**symlink farm**: every upstream file is a symlink straight back to the
package, so `pacman -Syu` reaches all of them with no action from anyone.

Only five files are real:

- three of ours, which upstream knows nothing about
- `Bar.qml` and `popouts/Content.qml`, which need a few lines inserted

Those two are regenerated from the new package whenever the version changes,
and that happens by itself — `claude-caelestia-sync.path` watches the pacman
database and re-syncs after any package transaction.

If upstream moves the code a patch attaches to, the sync **does not force it**.
Those two files fall back to plain symlinks, so you keep a fully working stock
bar and lose only the Claude entry, with a notification saying so. Fix the
anchor in `sync-caelestia.py`, then run it with `--stash`.

## States

| | |
|---|---|
| `working` | flower cycles `· ✢ ✳ ∗ ✻ ✽`, like the CLI's spinner |
| `waiting` | error colour — a session wants permission; also fires a notification |
| `done` | settles to idle after a minute |
| `idle` | dim flower |

Worst state across all sessions wins the bar icon. Sessions record their claude
pid, so a terminal killed without `SessionEnd` is dropped rather than left
spinning; and any `working` that goes 150s without a hook decays to idle, so
the flower can never spin forever.

## Layout

| Path | |
|---|---|
| `src/hook.py` | Claude Code hook: one json per session |
| `src/daemon.py` | merges sessions + usage + limits into `status.json` |
| `src/usage.py` | token/request accounting over the transcripts |
| `src/statusline.py` | statusline shim that captures the real limits |
| `src/focus.sh` | focuses a window without dragging the pointer |
| `src/sync-caelestia.py` | builds and repairs the overlay |
| `src/check.py` | walks the widget through every state so you can watch |
| `qml/` | the three files added to caelestia |
| `tools/configure.py` | the idempotent JSON edits |

Installs to `~/.local/share/claude-tray` (historical name, kept so existing
installs keep working).

## Checking it

```sh
python3 ~/.local/share/claude-tray/check.py
```

Drives each state for a few seconds and asks the shell what it actually
rendered, so a failure tells you which half broke — the data or the drawing.
Leave fullscreen first: caelestia hides the bar when a window is fullscreen.

To bind a key:

```sh
qs -c caelestia ipc call claude open
```

Also `claude state` and `claude sessions`.

## Troubleshooting

**quickshell crashes when the shell restarts.** Check its own startup warning:

    qs -c caelestia 2>&1 | head -3

If it says it was built against a different Qt than the one installed, that is
the cause and it is nothing to do with this widget — the segfault happens
during shutdown, after `Exiting due to IPC request`. Rebuild it:

    paru -S --rebuild quickshell-git

**The bar entry vanished after a caelestia update.** The sync refused to force
a patch onto changed upstream code, so you have a stock bar. See the notification,
fix the anchor in `sync-caelestia.py`, then `--stash`.

**Limits show as unavailable.** They arrive with the first statusline render of
a running Claude Code session. If they never arrive, check that
`~/.claude/settings.json` still points `statusLine.command` at `statusline.py`.

## Notes and limits

- Limits are as fresh as the last statusline render of any running session.
  With no session open, they are the last values seen.
- Hyprland warps the cursor into a window when focusing it, and on 0.56
  neither `cursor:no_warps` nor `warp = false` suppresses it — so `focus.sh`
  records the pointer and puts it back.
- Two Hyprland dispatch syntaxes exist (Lua and classic) and quickshell's
  `usingLua` reports false on a Lua config, so `focus.sh` tries one and falls
  back to the other rather than trusting the flag.
- `usage.py --selftest` checks the session-block maths.
- Logs: `~/.local/state/claude-tray/daemon.log`, `events.log`, `focus.log`.

## License

MIT, see [LICENSE](LICENSE). The repository ships no caelestia code beyond
the one-line anchors `sync-caelestia.py` searches for: the two caelestia
files Bloom patches are copied from your installed package and edited on your
machine.
