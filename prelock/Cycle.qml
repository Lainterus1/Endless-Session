import QtQuick

Item {
    id: root
    property bool locked: false
    property string token: ""
    property var retired: []
    property double lastLockAt: 0
    readonly property bool active: token.length > 0 && !locked
    signal wakeRequested()
    signal ended(string cycle,string reason)
    function show(cycle) {
        if (locked) return "locked";
        if (!/^[0-9]+-[0-9]+$/.test(cycle)) return "invalid-cycle";
        if (retired.indexOf(cycle)>=0 || Number(cycle.split("-")[0])<=lastLockAt) return "stale";
        if (token && token!==cycle) return "busy";
        token=cycle;return "shown";
    }
    function retire(cycle) { retired=retired.concat([cycle]).slice(-64); }
    function hide(cycle) { retire(cycle);if(token===cycle) token="";return "ok"; }
    function finish(reason) {
        if (!token) return;
        var cycle=token;retire(cycle);token="";
        ended(cycle,reason);
        if(reason!=="locked") wakeRequested();
    }
    onLockedChanged: if(locked) { lastLockAt=Date.now();finish("locked"); }
}
