import QtQuick
import "VisualStyle.js" as Style

Rectangle {
    id: root
    property string itemId: ""
    property string label: ""
    property string body: ""
    property var event: ({type:"message",phase:"commentary",text:body})
    property int ordinal: 0
    property bool latest: false
    property real baseY: 0
    property real textSize: 15
    property color foreground: "#cacccc"
    property color background: "#101315"
    property color accent: "#b1c7d4"
    property string fontFamily: "monospace"
    property alias textItem: content
    readonly property color secondary: Style.mix(background,foreground,0.68)
    readonly property color line: Style.mix(background,foreground,0.18)
    readonly property bool tool: event.type === "command"
    readonly property bool question: event.type === "question"
    readonly property bool fileChange: event.type === "file_change"
    readonly property bool failed: (tool && event.exit_code !== null && event.exit_code !== 0) || event.status === "failed"
    readonly property color marker: failed ? (background.r+background.g+background.b > 1.5 ? "#af3029" : "#ef827b") : accent
    color: tool || fileChange ? Style.mix(background,foreground,0.045) : background
    border.width: 0
    height: cardContent.height + 33
    transformOrigin: Item.Top
    Rectangle { z: -2; x: 1; y: 5; width: parent.width-2; height: parent.height; color: Qt.rgba(0,0,0,0.025) }
    Rectangle { z: -1; x: 3; y: 8; width: parent.width-6; height: parent.height; color: Qt.rgba(0,0,0,0.018) }
    Rectangle { width: parent.width; height: 1; color: root.tool || root.fileChange ? root.line : Style.mix(root.background,root.marker,0.46) }
    Rectangle { anchors.right: parent.right; width: 18; height: 2; color: root.marker; visible: root.latest }
    Rectangle { anchors.right: parent.right; width: 2; height: 18; color: root.marker; visible: root.latest }
    Column {
        id: cardContent
        x: 19; y: 15; width: parent.width - 38; spacing: 10
        Item {
            width: parent.width; height: 17
            Text { anchors.left: parent.left; text: Style.glyph(root.event)+"  "+Style.kind(root.event); textFormat: Text.PlainText; font.family: root.fontFamily; font.pixelSize: 11; color: root.tool || root.fileChange || root.event.type === "user_reply" ? root.secondary : root.marker }
            Text { anchors.right: parent.right; text: "событие "+String(root.ordinal).padStart(2,"0"); font.family: root.fontFamily; font.pixelSize: 11; color: root.secondary }
        }
        Text {
            id: content
            width: parent.width; visible: !root.tool && !root.question
            text: root.body; textFormat: Text.PlainText
            wrapMode: Text.Wrap; font.family: root.fontFamily; font.pixelSize: root.fileChange ? 12 : root.textSize
            lineHeight: 1.7; color: root.foreground
        }
        Column {
            width: parent.width; visible: root.question; spacing: 18
            Repeater {
                model: root.question ? root.event.questions : []
                delegate: Column {
                    id: questionGroup
                    required property var modelData
                    width: parent.width; spacing: 15
                    Text { width: parent.width; text: questionGroup.modelData.question; textFormat: Text.PlainText; wrapMode: Text.Wrap; font.family: root.fontFamily; font.pixelSize: root.textSize; lineHeight: 1.7; color: root.foreground }
                    Flow {
                        id: optionsFlow
                        width: parent.width; spacing: 7
                        Repeater {
                            model: questionGroup.modelData.options
                            delegate: Rectangle {
                                required property var modelData
                                width: Math.min(optionsFlow.width,optionText.implicitWidth+20); height: optionText.implicitHeight+14
                                color: root.background; border.color: root.line
                                Text { id: optionText; x: 10; y: 7; width: parent.width-20; text: typeof parent.modelData === "string" ? parent.modelData : parent.modelData.label+(parent.modelData.description ? " — "+parent.modelData.description : ""); textFormat: Text.PlainText; wrapMode: Text.Wrap; font.family: root.fontFamily; font.pixelSize: 11; color: root.foreground }
                            }
                        }
                    }
                }
            }
        }
        Column {
            width: parent.width; visible: root.tool; spacing: 9
            Text { width: parent.width; text: "›  "+(root.event.command || ""); textFormat: Text.PlainText; wrapMode: Text.Wrap; font.family: root.fontFamily; font.pixelSize: 12; lineHeight: 1.65; color: root.foreground }
            Item { width: parent.width; height: 2 }
            Rectangle { width: parent.width; height: 1; color: root.line }
            Item {
                width: parent.width; height: 16
                Text { text: "Вывод"; font.family: root.fontFamily; font.pixelSize: 11; color: root.secondary }
                Text { anchors.right: parent.right; text: root.event.exit_code === null ? "код выхода неизвестен" : "exit "+root.event.exit_code; font.family: root.fontFamily; font.pixelSize: 11; color: root.failed ? root.marker : root.secondary }
            }
            Text { width: parent.width; text: root.event.output || ""; textFormat: Text.PlainText; wrapMode: Text.Wrap; font.family: root.fontFamily; font.pixelSize: 12; lineHeight: 1.65; color: root.failed ? root.marker : root.secondary }
        }
    }
}
