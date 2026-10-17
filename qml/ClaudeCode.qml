pragma Singleton

import QtQuick
import Quickshell
import Quickshell.Io
import qs.services

// Reads the snapshot published by ~/.local/share/claude-tray/daemon.py.
Singleton {
    id: root

    readonly property string statusPath: `${Quickshell.env("XDG_STATE_HOME") || Quickshell.env("HOME") + "/.local/state"}/claude-tray/status.json`

    property string status: "idle"
    property var sessions: []
    property var session: ({
            tokens: 0,
            requests: 0,
            remaining: 0,
            elapsed: 0,
            window: 18000
        })
    property var week: ({
            tokens: 0,
            requests: 0,
            daily: []
        })
    property real updated: 0

    // The real /status figures, captured from the statusLine payload by
    // ~/.local/share/claude-tray/statusline.py. Nothing else on disk has them.
    property var limits: ({})

    readonly property int fiveHourUsed: limits.five_hour?.used ?? -1
    readonly property int sevenDayUsed: limits.seven_day?.used ?? -1
    readonly property int opusUsed: limits.seven_day_opus?.used ?? -1
    readonly property int contextUsed: limits.context?.used ?? -1
    readonly property string modelName: limits.model ?? ""
    readonly property bool hasLimits: fiveHourUsed >= 0

    readonly property int count: sessions.length
    readonly property bool busy: status === "working"

    // The theme's accent. Deliberately not Anthropic's brand colour: Bloom is
    // unofficial and should not look like an Anthropic product.
    readonly property color brand: Colours.palette.m3primary

    // Bar.qml listens for this so the popout can also be opened by a keybind.
    signal openRequested

    IpcHandler {
        target: "claude"

        function open(): void {
            root.openRequested();
        }

        function state(): string {
            return root.status;
        }

        function sessions(): string {
            return JSON.stringify(root.sessions);
        }
    }

    function label(s: string): string {
        if (s === "working")
            return qsTr("Working");
        if (s === "waiting")
            return qsTr("Needs permission");
        if (s === "done")
            return qsTr("Done");
        return qsTr("Idle");
    }

    function colour(s: string): color {
        if (s === "working" || s === "done")
            return root.brand;
        if (s === "waiting")
            return Colours.palette.m3error;
        return Colours.palette.m3outline;
    }

    function fmtTokens(n: real): string {
        if (n >= 1e9)
            return `${(n / 1e9).toFixed(1)}B`;
        if (n >= 1e6)
            return `${(n / 1e6).toFixed(1)}M`;
        if (n >= 1e3)
            return `${(n / 1e3).toFixed(1)}K`;
        return `${Math.round(n)}`;
    }

    function fmtLeft(seconds: int): string {
        if (seconds <= 0)
            return qsTr("expired");
        const h = Math.floor(seconds / 3600);
        const m = Math.floor(seconds % 3600 / 60);
        return h > 0 ? qsTr("%1h %2m left").arg(h).arg(`${m}`.padStart(2, "0")) : qsTr("%1m left").arg(m);
    }

    // "8:40pm" for something today, "Mon 9:00am" beyond that.
    function fmtReset(ts: real): string {
        if (!ts)
            return "";
        const when = new Date(ts * 1000);
        const soon = ts * 1000 - Date.now() < 20 * 3600 * 1000;
        return qsTr("resets %1").arg(Qt.formatDateTime(when, soon ? "h:mmap" : "ddd h:mmap"));
    }

    // Green while there is room, amber when it is getting close, red at the wall.
    function limitColour(pct: int): color {
        if (pct >= 90)
            return Colours.palette.m3error;
        if (pct >= 70)
            return Colours.palette.m3tertiary;
        return root.brand;
    }

    function fmtAgo(ts: real): string {
        const d = Math.max(0, Math.floor(Date.now() / 1000 - ts));
        if (d < 60)
            return `${d}s`;
        if (d < 3600)
            return `${Math.floor(d / 60)}m`;
        return `${Math.floor(d / 3600)}h`;
    }

    // focus.sh works out which dispatch syntax this Hyprland wants. Deciding
    // it here from Hypr.usingLua does not work: it reports false on a Lua
    // config, which sent every click down the syntax that errors.
    function focusSession(address: string): void {
        if (!address)
            return;
        focusProc.command = [`${Quickshell.env("HOME")}/.local/share/claude-tray/focus.sh`, address];
        focusProc.running = true;
    }

    Process {
        id: focusProc
    }

    // Polled rather than trusting watchChanges alone: the daemon publishes by
    // atomic rename, which swaps the inode out from under a file watcher and
    // leaves it silently dead -- the popout would then sit on a stale
    // "working" for ever.
    Timer {
        running: true
        interval: 1000
        repeat: true
        onTriggered: statusFile.reload()
    }

    FileView {
        id: statusFile

        path: root.statusPath
        watchChanges: true
        onFileChanged: reload()
        onLoaded: {
            try {
                const data = JSON.parse(text());
                root.status = data.state ?? "idle";
                root.sessions = data.sessions ?? [];
                root.session = data.usage?.session ?? root.session;
                root.week = data.usage?.week ?? root.week;
                root.updated = data.updated ?? 0;
                root.limits = data.limits ?? ({});
            } catch (e) {
                // A half-written file just means the next change event wins.
            }
        }
    }
}
