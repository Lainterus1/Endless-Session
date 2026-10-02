import QtQuick
import "DisplayState.js" as State

Item {
    id: root
    property bool locked: false
    property bool authenticatingPassword: false
    property var monitored: []
    property string discovery: "scanning"
    property bool liveClock: true
    property double clockNow: Date.now()
    property double previousTick: 0
    property double wakeGraceUntil: 0
    property var lossStarts: ({})
    property var decision: ({hold:false, reason:"unlocked", all_completed:false, uncertain:false})
    readonly property bool hold: decision.hold
    signal wakeRequested()
    signal releaseRequested(bool lossTimeout)

    function refresh() {
        if (!locked) { lossStarts = {}; wakeGraceUntil = 0; previousTick = 0; decision = {hold:false,reason:"unlocked",all_completed:false,uncertain:false}; return; }
        var next = State.decide(monitored, discovery, clockNow, lossStarts);
        lossStarts = next.starts;
        if (authenticatingPassword) { next.hold = true; next.reason = "password"; }
        else if (clockNow < wakeGraceUntil) { next.hold = true; next.reason = "wake_grace"; }
        var previous = decision.hold;
        decision = next;
        if (!previous && next.hold) wakeRequested();
        if (previous && !next.hold) releaseRequested(next.reason === "loss_timeout");
    }
    function tick(now) {
        if (previousTick > 0 && (now - previousTick > 2000 || now < previousTick)) wakeGraceUntil = now + 5000;
        previousTick = now; clockNow = now; refresh();
    }
    function manualWake() { wakeGraceUntil = clockNow + 5000; refresh(); }
    onLockedChanged: { if (liveClock) clockNow = Date.now(); refresh(); }
    onAuthenticatingPasswordChanged: refresh()
    onMonitoredChanged: refresh()
    onDiscoveryChanged: refresh()
    Timer { interval: 100; repeat: true; running: root.locked && root.liveClock; onTriggered: root.tick(Date.now()) }
}
