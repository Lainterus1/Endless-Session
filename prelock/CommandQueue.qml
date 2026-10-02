import QtQuick
import Quickshell.Io

Item {
    id: root
    property var queue: []
    property var current: null
    property int attempts: 0
    property int failures: 0
    readonly property bool busy: current !== null || queue.length > 0 || commandProcess.running
    readonly property bool running: busy
    function enqueue(command) {
        queue=queue.concat([command.slice()]);pump();
    }
    function pump() {
        if(commandProcess.running || retry.running) return;
        if(current===null) {
            if(!queue.length)return;
            current=queue[0];queue=queue.slice(1);attempts=0;
        }
        attempts++;commandProcess.command=current;commandProcess.running=true;deadline.restart();
    }
    Process {
        id: commandProcess
        onExited: function(code) {
            deadline.stop();
            if(code!==0 && root.attempts<3)retry.restart();
            else {
                if(code!==0)root.failures++;
                root.current=null;Qt.callLater(root.pump);
            }
        }
    }
    Timer { id: retry;interval:200;onTriggered:root.pump() }
    Timer { id: deadline;interval:3000;onTriggered:commandProcess.signal(9) }
}
