import QtQuick
import "FrameStore.js" as Store

Item {
    id: root
    property var dashboards: []
    property int pageTick: 0
    property bool rotate: true
    property double lastSequence: 0
    property var cache: ({})
    property var monitored: []
    property string discovery: "scanning"
    property int unknownCount: 0
    property var theme: null
    property bool needsReset: true
    property double lastFrameAt: 0
    readonly property int sharedCapacity: dashboards.some(function(view) { return view.width < 960; }) ? 2 : 4
    function syncCapacity() { dashboards.forEach(function(view) { view.capacityOverride = sharedCapacity; }); syncPages(); }
    onSharedCapacityChanged: syncCapacity()
    function attach(view) {
        if (dashboards.indexOf(view) >= 0) return;
        if (lastSequence > 0) {
            view.receive(JSON.stringify({schema_version:1,sequence:lastSequence,discovery:discovery,unknown_count:unknownCount,
                theme:theme,chats:Object.keys(cache).map(function(id) { return cache[id]; })}));
        }
        dashboards = dashboards.concat([view]);
        syncCapacity();
    }
    function detach(view) { dashboards = dashboards.filter(function(old) { return old !== view; }); }
    function syncPages() { dashboards.forEach(function(view) { view.page = pageTick % view.pages; view.syncPanels(null); }); }
    function advance() { pageTick++; syncPages(); }
    function receive(line) {
        var result=Store.apply(cache,needsReset,lastSequence,line);
        if(result.invalid) { disconnected();return false; }
        if(result.stale) return false;
        cache=result.cache;monitored=result.monitored;discovery=result.frame.discovery;
        unknownCount=result.frame.unknown_count;theme=result.frame.theme;
        lastSequence=result.frame.sequence;lastFrameAt=Date.now();needsReset=false;
        dashboards.forEach(function(view) { view.receive(line); });
        syncPages();return true;
    }
    function disconnected() {
        discovery="unknown";
        var lost={};Object.keys(cache).forEach(function(id) { lost[id]=Object.assign({},cache[id],{status:"disconnected"}); });cache=lost;
        monitored=monitored.map(function(chat) { return Object.assign({},chat,{status:"disconnected"}); });
        dashboards.forEach(function(view) { view.disconnected(); });
    }
    function clear() { cache={};monitored=[];discovery="scanning";lastSequence=0;lastFrameAt=0;needsReset=true;pageTick=0; }
    function restartTransport() { disconnected(); lastSequence = 0; needsReset=true; dashboards.forEach(function(view) { view.restartTransport(); }); }
    Timer { interval: 100; repeat: true; running: root.lastFrameAt>0; onTriggered: if(Date.now()-root.lastFrameAt>=5000 && root.discovery!=="unknown")root.disconnected() }
    Timer { interval: 20000; repeat: true; running: root.rotate && root.dashboards.length > 0; onTriggered: root.advance() }
}
