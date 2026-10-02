import QtQuick
import "ui"

Item {
    id: root
    property bool locked: false
    property bool screensaver: false
    readonly property bool active: locked || screensaver
    property bool authenticatingPassword: false
    property alias hub: hub
    property alias policy: policy
    readonly property bool hold: policy.hold
    readonly property string collectorPath: decodeURIComponent(Qt.resolvedUrl("watch_context.py").toString().replace(/^file:\/\//, ""))
    property var collectorCommand: ["python3","-B",root.collectorPath]
    readonly property int collectorPid: feed.processId
    readonly property bool collectorRunning: feed.running
    signal wakeRequested()
    signal releaseRequested(bool lossTimeout)
    function manualWake() { policy.manualWake(); }
    ContextHub { id: hub }
    ContextSource { id: feed; view: hub; enabled: false; command: root.collectorCommand }
    DisplayPolicy {
        id: policy
        locked: feed.enabled
        authenticatingPassword: root.authenticatingPassword
        monitored: hub.monitored
        discovery: hub.discovery
        onWakeRequested: root.wakeRequested()
        onReleaseRequested: function(lossTimeout) { root.releaseRequested(lossTimeout); }
    }
    function syncActive() {
        if (active) { shutdown.stop();feed.enabled=true; }
        else shutdown.restart();
    }
    onActiveChanged: syncActive()
    Component.onCompleted: if(active) syncActive()
    // Bindings for prelock and secure surfaces may settle in either order.
    // A brief gap must not restart the collector or reset its loss deadline.
    Timer {
        id: shutdown
        interval:200
        onTriggered: if(!root.active) { feed.enabled=false;hub.clear(); }
    }
}
