import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons
import "../ui"
import "../ui/NativeTheme.js" as NativeTheme

Cycle {
    id: root
    property var hub: null
    onEnded: function(cycle,reason) {
        notification.enqueue(["omarchy","shell","idle",reason==="locked" ? "codexScreensaverLocked" : "codexScreensaverDismissed",cycle]);
    }
    CommandQueue { id: notification }
    Variants {
        model: root.active ? Quickshell.screens : []
        PanelWindow {
            id: surface
            required property var modelData
            screen: modelData
            anchors { top:true;bottom:true;left:true;right:true }
            color: Color.background
            exclusionMode: ExclusionMode.Ignore
            WlrLayershell.namespace: "omarchy-codex-screensaver"
            WlrLayershell.layer: WlrLayer.Overlay
            WlrLayershell.keyboardFocus: root.active ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
            Dashboard {
                id: dashboard
                anchors.fill: parent
                rotate:false
                mode:"screensaver"
                themeOverride:NativeTheme.normalize(Color.foreground,Color.background,Color.accent,Style.font.family)
                Component.onCompleted: if(root.hub) root.hub.attach(dashboard)
                Component.onDestruction: if(root.hub) root.hub.detach(dashboard)
            }
            Item {
                anchors.fill:parent
                focus:true
                Component.onCompleted: forceActiveFocus()
                Keys.onPressed: function(event) { event.accepted=true;root.finish("activity"); }
                MouseArea {
                    anchors.fill:parent
                    hoverEnabled:true
                    acceptedButtons:Qt.AllButtons
                    property bool positioned:false
                    property real previousX:0
                    property real previousY:0
                    onPressed: root.finish("activity")
                    onWheel: function(wheel) { wheel.accepted=true;root.finish("activity"); }
                    onPositionChanged: function(mouse) {
                        if(positioned && (mouse.x!==previousX || mouse.y!==previousY))root.finish("activity");
                        previousX=mouse.x;previousY=mouse.y;positioned=true;
                    }
                }
            }
        }
    }
}
