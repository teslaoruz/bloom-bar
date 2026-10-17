pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import Quickshell
import Caelestia.Config
import qs.components
import qs.services

Column {
    id: root

    spacing: Tokens.spacing.small
    width: Tokens.sizes.bar.networkWidth

    // Keeps the elapsed and reset strings ticking while the popout is open.
    property int tick: 0
    Timer {
        running: root.visible
        interval: 1000
        repeat: true
        onTriggered: root.tick++
    }

    // ---- header ----
    RowLayout {
        width: parent.width
        spacing: Tokens.spacing.small

        Flower {}

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 0

            StyledText {
                text: qsTr("Claude Code")
                font: Tokens.font.body.builders.medium.weight(Font.DemiBold).build()
            }

            StyledText {
                text: {
                    const n = ClaudeCode.count;
                    const who = `${ClaudeCode.label(ClaudeCode.status)} · ${n} ${n === 1 ? qsTr("session") : qsTr("sessions")}`;
                    return ClaudeCode.modelName ? `${who} · ${ClaudeCode.modelName}` : who;
                }
                color: Colours.palette.m3onSurfaceVariant
                font: Tokens.font.body.builders.small.build()
            }
        }
    }

    // ---- the real limits, straight from /status ----
    Loader {
        width: root.width
        active: ClaudeCode.hasLimits
        visible: active

        sourceComponent: Column {
            width: root.width
            spacing: Tokens.spacing.small

            LimitBar {
                label: qsTr("Session")
                percent: ClaudeCode.fiveHourUsed
                caption: (root.tick, ClaudeCode.fmtReset(ClaudeCode.limits.five_hour?.resets_at ?? 0))
            }

            LimitBar {
                label: qsTr("Week")
                percent: ClaudeCode.sevenDayUsed
                caption: (root.tick, ClaudeCode.fmtReset(ClaudeCode.limits.seven_day?.resets_at ?? 0))
            }

            LimitBar {
                visible: ClaudeCode.opusUsed >= 0
                label: qsTr("Week (Opus)")
                percent: ClaudeCode.opusUsed
                caption: (root.tick, ClaudeCode.fmtReset(ClaudeCode.limits.seven_day_opus?.resets_at ?? 0))
            }
        }
    }

    Loader {
        width: root.width
        active: !ClaudeCode.hasLimits
        visible: active

        sourceComponent: StyledText {
            width: root.width
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            text: qsTr("Limits appear once a session renders its statusline")
            color: Colours.palette.m3onSurfaceVariant
            font: Tokens.font.body.builders.small.build()
        }
    }

    // ---- sessions ----
    StyledText {
        text: qsTr("SESSIONS")
        color: Colours.palette.m3onSurfaceVariant
        font: Tokens.font.body.builders.small.scale(0.8).weight(Font.Bold).build()
    }

    Repeater {
        model: ClaudeCode.sessions

        StyledRect {
            id: row

            required property var modelData

            readonly property color accent: ClaudeCode.colour(modelData.state ?? "idle")

            width: root.width
            implicitHeight: rowLayout.implicitHeight + Tokens.padding.small * 2

            color: Colours.tPalette.m3surfaceContainerHigh
            radius: Tokens.rounding.normal

            StateLayer {
                radius: parent.radius
                disabled: !row.modelData.window
                onClicked: ClaudeCode.focusSession(row.modelData.window)
            }

            RowLayout {
                id: rowLayout

                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: Tokens.padding.large
                anchors.rightMargin: Tokens.padding.large
                spacing: Tokens.spacing.small

                StyledRect {
                    implicitWidth: 8
                    implicitHeight: 8
                    radius: Tokens.rounding.full
                    color: row.accent

                    SequentialAnimation on opacity {
                        running: row.modelData.state === "working" || row.modelData.state === "waiting"
                        loops: Animation.Infinite
                        alwaysRunToEnd: true

                        Anim {
                            to: 0.3
                            type: Anim.SlowEffects
                        }
                        Anim {
                            to: 1
                            type: Anim.SlowEffects
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 0
                    spacing: 0

                    StyledText {
                        Layout.fillWidth: true
                        text: {
                            const cwd = row.modelData.cwd ?? "";
                            return cwd.split("/").filter(p => p).pop() || "~";
                        }
                        elide: Text.ElideRight
                        font: Tokens.font.body.builders.small.weight(Font.DemiBold).build()
                    }

                    StyledText {
                        Layout.fillWidth: true
                        text: (row.modelData.cwd ?? "").replace(Quickshell.env("HOME"), "~")
                        elide: Text.ElideLeft
                        color: Colours.palette.m3onSurfaceVariant
                        font: Tokens.font.mono.builders.small.scale(0.85).build()
                    }
                }

                ColumnLayout {
                    spacing: 0

                    StyledText {
                        Layout.alignment: Qt.AlignRight
                        text: ClaudeCode.label(row.modelData.state ?? "idle")
                        color: row.accent
                        font: Tokens.font.body.builders.small.scale(0.9).build()
                    }

                    StyledText {
                        Layout.alignment: Qt.AlignRight
                        text: (root.tick, ClaudeCode.fmtAgo(row.modelData.ts ?? 0))
                        color: Colours.palette.m3onSurfaceVariant
                        font: Tokens.font.mono.builders.small.scale(0.85).build()
                    }
                }
            }
        }
    }

    Loader {
        active: ClaudeCode.count === 0
        visible: active
        width: root.width

        sourceComponent: StyledText {
            horizontalAlignment: Text.AlignHCenter
            text: qsTr("No sessions running")
            color: Colours.palette.m3onSurfaceVariant
        }
    }

    // ---- 7-day shape, from the local transcripts ----
    StyledText {
        text: qsTr("LAST 7 DAYS")
        color: Colours.palette.m3onSurfaceVariant
        font: Tokens.font.body.builders.small.scale(0.8).weight(Font.Bold).build()
    }

    RowLayout {
        width: root.width
        spacing: Tokens.spacing.small

        readonly property var shown: {
            const days = ClaudeCode.week.daily ?? [];
            const i = weekChart.hoveredIndex;
            return i >= 0 && i < days.length ? days[i] : ClaudeCode.week;
        }

        StyledText {
            text: ClaudeCode.fmtTokens(parent.shown.tokens)
            font: Tokens.font.mono.builders.large.weight(Font.DemiBold).build()
        }

        StyledText {
            Layout.alignment: Qt.AlignBottom
            Layout.bottomMargin: 2
            text: weekChart.hoveredIndex >= 0 ? parent.shown.date.slice(5) : qsTr("tok")
            color: Colours.palette.m3onSurfaceVariant
            font: Tokens.font.body.builders.small.scale(0.85).build()
        }

        Item {
            Layout.fillWidth: true
        }

        StyledText {
            text: qsTr("%1 req").arg(parent.shown.requests ?? 0)
            color: Colours.palette.m3onSurfaceVariant
            font: Tokens.font.mono.builders.medium.build()
        }
    }

    Item {
        id: weekChart

        property int hoveredIndex: -1

        width: root.width
        implicitHeight: 46

        RowLayout {
            anchors.fill: parent
            spacing: Tokens.spacing.small

            Repeater {
                model: ClaudeCode.week.daily ?? []

                ColumnLayout {
                    id: col

                    required property var modelData
                    required property int index

                    readonly property bool today: index === (ClaudeCode.week.daily?.length ?? 0) - 1
                    readonly property real peak: {
                        let m = 1;
                        for (const d of ClaudeCode.week.daily ?? [])
                            m = Math.max(m, d.tokens);
                        return m;
                    }

                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 2

                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        StyledRect {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom

                            radius: Tokens.rounding.small
                            height: Math.max(3, parent.height * (col.modelData.tokens / col.peak))
                            color: col.today ? ClaudeCode.brand : Qt.alpha(ClaudeCode.brand, hover.hovered ? 0.7 : 0.35)

                            Behavior on height {
                                Anim {
                                    type: Anim.DefaultSpatial
                                }
                            }
                        }

                        HoverHandler {
                            id: hover

                            onHoveredChanged: weekChart.hoveredIndex = hovered ? col.index : -1
                        }
                    }

                    StyledText {
                        Layout.alignment: Qt.AlignHCenter
                        text: ["S", "M", "T", "W", "T", "F", "S"][new Date(col.modelData.date + "T00:00:00").getDay()]
                        color: col.today ? ClaudeCode.brand : Colours.palette.m3onSurfaceVariant
                        font: Tokens.font.body.builders.small.scale(0.8).build()
                    }
                }
            }
        }
    }

    // The flower, turning while a session is working and resting otherwise --
    // the header text already says which state that is.
    component Flower: StyledText {
        id: flower

        text: "✽"
        color: ClaudeCode.colour(ClaudeCode.status)
        font: Tokens.font.body.builders.medium.scale(2).build()

        RotationAnimation on rotation {
            running: ClaudeCode.busy
            loops: Animation.Infinite
            from: 0
            to: 360
            duration: 2400
            onRunningChanged: if (!running)
                flower.rotation = 0
        }
    }

    component LimitBar: ColumnLayout {
        id: bar

        property string label
        property string caption
        property int percent: 0

        readonly property color accent: ClaudeCode.limitColour(percent)

        width: root.width
        spacing: 3

        RowLayout {
            Layout.fillWidth: true

            StyledText {
                text: bar.label
                font: Tokens.font.body.builders.small.weight(Font.DemiBold).build()
            }

            Item {
                Layout.fillWidth: true
            }

            StyledText {
                text: `${bar.percent}%`
                color: bar.accent
                font: Tokens.font.mono.builders.small.weight(Font.DemiBold).build()
            }
        }

        StyledRect {
            Layout.fillWidth: true
            implicitHeight: 6
            radius: Tokens.rounding.full
            color: Colours.tPalette.m3surfaceContainerHighest

            StyledRect {
                height: parent.height
                radius: parent.radius
                color: bar.accent
                width: Math.max(height, parent.width * Math.min(1, bar.percent / 100))

                Behavior on width {
                    Anim {
                        type: Anim.DefaultSpatial
                    }
                }
            }
        }

        StyledText {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignRight
            text: bar.caption
            color: Colours.palette.m3onSurfaceVariant
            font: Tokens.font.body.builders.small.scale(0.85).build()
        }
    }
}
