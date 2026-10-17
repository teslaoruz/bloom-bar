pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import Caelestia.Config
import qs.components
import qs.services

StyledRect {
    id: root

    readonly property color colour: ClaudeCode.colour(ClaudeCode.status)
    readonly property font glyphFont: Tokens.font.body.builders.medium.scale(1.25).build()
    readonly property var frames: ["·", "✢", "✳", "∗", "✻", "✽", "✻", "∗", "✳", "✢"]
    property int frame: 0

    implicitWidth: Tokens.sizes.bar.innerWidth
    implicitHeight: layout.implicitHeight + Tokens.padding.small * 2

    color: "transparent"
    radius: Tokens.rounding.full

    Timer {
        running: ClaudeCode.busy
        interval: 120
        repeat: true
        onTriggered: root.frame = (root.frame + 1) % root.frames.length
        onRunningChanged: if (!running)
            root.frame = 0
    }

    ColumnLayout {
        id: layout

        anchors.centerIn: parent
        spacing: Tokens.spacing.extraSmall

        // Claude Code's thinking spinner. The frames are very different widths,
        // so the glyph is centred in a box sized to the widest one.
        Item {
            Layout.alignment: Qt.AlignHCenter

            implicitWidth: metrics.width
            implicitHeight: glyph.implicitHeight

            TextMetrics {
                id: metrics

                font: root.glyphFont
                text: "✽"
            }

            StyledText {
                id: glyph

                anchors.centerIn: parent
                horizontalAlignment: Text.AlignHCenter

                // Idle keeps the resting flower, dimmed by ClaudeCode.colour().
                text: ClaudeCode.busy ? root.frames[root.frame] : ClaudeCode.status === "waiting" ? "✳" : "✽"
                color: root.colour
                font: root.glyphFont

                Behavior on color {
                    CAnim {}
                }
            }
        }

        // Session count, only once there is more than one to tell apart.
        Loader {
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: -2
            asynchronous: true
            active: ClaudeCode.count > 1
            visible: active

            sourceComponent: StyledText {
                text: ClaudeCode.count
                color: root.colour
                font: Tokens.font.body.builders.small.scale(0.85).build()
            }
        }
    }
}
