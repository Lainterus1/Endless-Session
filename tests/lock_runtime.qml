import QtQuick
import QtQuick.Window
import Quickshell
import "plugin"
import "plugin/ui"

ShellRoot {
    id: root
    property int phase: 0
    property int cycles: 0
    property var pids: []
    property bool captureDone: false
    property double activatedAt: 0
    property double stoppedAt: 0
    property int observedPid: 0
    property bool held: false
    property int wakeCalls: 0
    property bool handoffPreserved: false
    // Native Service требует Wayland; здесь проверяются настоящий LockView и lifecycle collector.
    IdleContext {
        id: context
        collectorCommand: ["python3","-B",Quickshell.env("OC_IDLE_FIXTURE"),Quickshell.env("OC_IDLE_PID_FILE")]
        onWakeRequested: root.wakeCalls++
    }
    Window {
        width: 1440; height: 1000; visible: true
        LockView { id: view; anchors.fill: parent; codexHub: context.hub; codexActive: context.locked; loadBackground: false; inputEnabled: true }
        Loader {
            anchors.fill:parent;active:context.screensaver
            sourceComponent: Component { Dashboard {
                id:saver;mode:"screensaver";rotate:false
                Component.onCompleted:context.hub.attach(saver)
                Component.onDestruction:context.hub.detach(saver)
            } }
        }
    }
    function finish(passed, reason) {
        console.log("LOCK_RUNTIME_RESULT " + JSON.stringify({passed:passed,reason:reason,serviceTypeReady:false,
            collectorPid:observedPid,cycles:cycles,pids:pids,captureDone:captureDone,holdObserved:held,handoffPreserved:handoffPreserved,stopDelayMs:Date.now()-stoppedAt,runningAfterStop:context.collectorRunning,
            holdAfterStop:context.hold,panelsAfterStop:context.hub.dashboards.length,wakeCalls:wakeCalls,secureExercised:false,pamExercised:false}));
        Qt.quit();
    }
    Timer {
        interval: 50; running: true; repeat: true
        onTriggered: {
            if (root.phase===0) {
                if (context.collectorRunning || context.hub.dashboards.length) { root.finish(false,"started-before-lock"); return; }
                root.activatedAt=Date.now(); context.screensaver=true; root.phase=1;
            } else if (root.phase===1 && context.hub.dashboards.length && context.hub.dashboards[0].monitored.length) {
                root.observedPid=context.collectorPid; root.held=context.hold;
                if (Date.now()-root.activatedAt>2000) { root.finish(false,"late-renderer"); return; }
                root.pids=root.pids.concat([root.observedPid]);
                if (root.cycles===0) { context.screensaver=false;root.phase=5; }
                else root.phase=3;
            } else if(root.phase===5) {
                // Reverse binding order with one frame lacking a surface.
                if(!context.collectorRunning || context.collectorPid!==root.observedPid) { root.finish(false,"collector-stopped-at-handoff");return; }
                context.locked=true;root.phase=4;
            } else if (root.phase===4 && context.hub.dashboards.length && context.hub.dashboards[0].monitored.length) {
                root.handoffPreserved=context.collectorRunning && context.collectorPid===root.observedPid && context.hub.monitored.length>0;
                if(!root.handoffPreserved) { root.finish(false,"collector-restarted-at-handoff");return; }
                view.grabToImage(function(result) { root.captureDone=result.saveToFile(Quickshell.env("OC_IDLE_CAPTURE")); });
                root.phase=3;
            } else if (root.phase===3 && root.captureDone) {
                context.locked=false;context.screensaver=false; root.stoppedAt=Date.now(); root.phase=2;
            } else if (root.phase===2 && !context.collectorRunning && context.hub.dashboards.length===0) {
                if (Date.now()-root.stoppedAt>2000) { root.finish(false,"late-stop"); return; }
                root.cycles++;
                if (root.cycles<2) root.phase=0;
                else root.finish(root.observedPid>0 && root.held && root.handoffPreserved && !context.hold && root.pids[0]!==root.pids[1],"local-lock-lifecycle");
            }
        }
    }
    Timer { interval: 8000; running: true; onTriggered: root.finish(false,"timeout") }
}
