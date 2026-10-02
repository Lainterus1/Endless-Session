import QtQuick
import Quickshell.Io

Item {
    id: root
    required property var view
    property var command: []
    property bool retryEnabled: true
    readonly property int processId: source.processId
    readonly property bool running: source.running
    signal applied(var frame)
    signal transportExited()
    Process {
        id: source
        command: root.command
        running: root.enabled && root.command.length > 0
        stdout: SplitParser {
            onRead: function(line) {
                if (root.view.receive(line)) root.applied(JSON.parse(line));
            }
        }
        onExited: {
            root.view.disconnected(); root.transportExited();
            if (root.enabled && root.retryEnabled) retry.start();
        }
    }
    Timer {
        id: retry; interval: 2000
        onTriggered: if (root.enabled) { root.view.restartTransport(); source.running = true; }
    }
    onEnabledChanged: {
        retry.stop();
        if (enabled) root.view.restartTransport();
        else root.view.disconnected();
        source.running = enabled && command.length > 0;
    }
}
