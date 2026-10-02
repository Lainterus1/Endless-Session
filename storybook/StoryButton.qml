import QtQuick

Rectangle {
    id: root
    property string label: ""
    property string detail: ""
    property bool selected: false
    property bool emphasized: false
    property bool compact: false
    signal clicked()

    radius: 8
    height: compact ? 34 : (detail ? 56 : 40)
    color: selected ? "#26333a" : hover.containsMouse ? "#1d282e" : "#151d21"
    border.width: selected || emphasized ? 1 : 0
    border.color: emphasized ? "#c4dbcf" : "#678d81"

    Text {
        x: 12; y: root.detail ? 8 : 0
        height: root.detail ? 20 : parent.height
        verticalAlignment: Text.AlignVCenter
        width: parent.width - 24
        text: root.label
        textFormat: Text.PlainText
        color: root.selected || root.emphasized ? "#e0ede7" : "#c5d2cd"
        font.family: "monospace"
        font.pixelSize: root.compact ? 11 : 12
        elide: Text.ElideRight
    }
    Text {
        x: 12; y: 30; width: parent.width - 24; height: 18
        visible: root.detail.length > 0
        text: root.detail
        textFormat: Text.PlainText
        color: "#92a69d"
        font.family: "monospace"; font.pixelSize: 10
        elide: Text.ElideRight
    }
    MouseArea {
        id: hover
        anchors.fill: parent
        hoverEnabled: true
        onClicked: root.clicked()
    }
}
