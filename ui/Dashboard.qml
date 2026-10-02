import QtQuick
import "FrameStore.js" as Store
import "VisualStyle.js" as Style

Rectangle {
    id: root
    color: theme.background
    property string mode: "preview"
    property bool motionEnabled: true
    signal passwordRequested()
    property string clockText: Qt.formatTime(new Date(),"hh:mm")
    readonly property color ink: theme.foreground
    readonly property color paper: theme.background
    readonly property color secondary: Style.mix(paper,ink,0.66)
    readonly property color hairline: Style.mix(paper,ink,0.2)
    readonly property real contentWidth: Math.min(width,(visibleIds || []).length===1 ? 810 : (visibleIds || []).length===2 ? 1560 : width)
    readonly property real contentLeft: (width-contentWidth)/2
    property var sourceTheme: ({foreground: "#cacccc", background: "#101315", accent: "#cacccc", fontFamily: "monospace"})
    property var themeOverride: null
    readonly property var theme: themeOverride || sourceTheme
    property var cache: ({})
    property var panels: ({})
    property var monitored: []
    property string discovery: "scanning"
    property int unknownCount: 0
    property double lastSequence: 0
    property double lastFrameAt: 0
    property bool needsReset: true
    property int page: 0
    property bool rotate: true
    property int capacityOverride: 0
    readonly property int capacity: capacityOverride || (width < 960 ? 2 : 4)
    readonly property int pages: Math.max(1, Math.ceil(monitored.length / capacity))
    readonly property var visibleIds: monitored.slice(page * capacity, (page + 1) * capacity).map(function(c) { return c.thread_id; })

    function disconnected() {
        discovery = "unknown";
        var lost = {};
        Object.keys(cache).forEach(function(id) { lost[id] = Object.assign({}, cache[id], {status: "disconnected"}); });
        cache = lost;
        monitored = monitored.map(function(c) { return Object.assign({}, c, {status: "disconnected"}); });
        Object.keys(panels).forEach(function(id) { panels[id].disconnected(); });
    }
    function restartTransport() { disconnected(); lastSequence = 0; needsReset = true; }
    function receive(line) {
        var result=Store.apply(cache,needsReset,lastSequence,line);
        if(result.invalid) { disconnected();return false; }
        if(result.stale) return false;
        var frame=result.frame;
        cache=result.cache;sourceTheme=frame.theme;discovery=frame.discovery;unknownCount=frame.unknown_count;
        monitored=result.monitored;
        page=Math.max(0,Math.min(page,pages-1));
        lastSequence=frame.sequence;lastFrameAt=Date.now();needsReset=false;
        syncPanels(frame);return true;
    }
    function syncPanels(frame) {
        var ids = visibleIds || []; var next = Object.assign({}, panels || {});
        var updates = [];
        Object.keys(next).forEach(function(id) { if (ids.indexOf(id) < 0) { next[id].destroy(); delete next[id]; } });
        ids.forEach(function(id) {
            var chat;
            if (!next[id]) {
                next[id] = panelFactory.createObject(root, {threadId: id});
                chat = cache[id];
            } else if (frame) chat = frame.chats.find(function(c) { return c.thread_id === id; });
            if (chat) updates.push({panel: next[id], chat: chat});
        });
        panels = next; layout();
        updates.forEach(function(update) { update.panel.receive(JSON.stringify({schema_version: 1, sequence: lastSequence, chats: [update.chat]})); });
    }
    function layout() {
        var ids=visibleIds || [];
        var columns=width>=1200 && ids.length===3 ? 3 : width>=960 && ids.length>=2 ? 2 : 1;
        var rows=Math.max(1,Math.ceil(ids.length/columns));
        ids.forEach(function(id,index) {
            var panel=panels[id];if (!panel)return;
            panel.x=root.contentLeft+(index%columns)*root.contentWidth/columns;
            panel.y=83+Math.floor(index/columns)*(root.height-149)/rows;
            panel.width=root.contentWidth/columns;
            panel.height=Math.max(0,(root.height-149)/rows);
            panel.compact=columns===3 || panel.width<600;
            panel.showDivider=index%columns>0;
            panel.sessionIndex=root.monitored.findIndex(function(chat){return chat.thread_id===id;})+1;
        });
    }
    function advance() { page = (page + 1) % pages; syncPanels(null); }
    onWidthChanged: { page = Math.max(0, Math.min(page, pages - 1)); syncPanels(null); }
    onCapacityChanged: { page = Math.max(0, Math.min(page, pages - 1)); syncPanels(null); }
    onHeightChanged: layout()
    onContentWidthChanged: layout()
    Component {
        id: panelFactory
        ContextView {
            foreground: root.theme.foreground; background: root.theme.background; accent: root.theme.accent
            fontFamily: root.theme.fontFamily
            motionEnabled: root.motionEnabled
        }
    }
    Item {
        width: parent.width; height: 60
        Text { x: 24; anchors.verticalCenter: parent.verticalCenter; text: "◈"; font.family: root.theme.fontFamily; font.pixelSize: 25; color: root.theme.accent }
        Text { x: 58; anchors.verticalCenter: parent.verticalCenter; text: "omarchy  /  codex"; font.family: root.theme.fontFamily; font.pixelSize: 13; color: root.ink }
        Text { anchors.right: parent.right; anchors.rightMargin: 24; anchors.verticalCenter: parent.verticalCenter; text: root.clockText; font.family: root.theme.fontFamily; font.pixelSize: 20; color: root.ink }
        Text { anchors.right: parent.right; anchors.rightMargin: 109; anchors.verticalCenter: parent.verticalCenter; visible: root.width>700; text: (root.discovery === "scanning" ? "Поиск чатов…" : "Чатов: "+root.monitored.length)+(root.pages>1 ? " · "+(root.page+1)+"/"+root.pages : ""); font.family: root.theme.fontFamily; font.pixelSize: 11; color: root.secondary }
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: root.hairline }
    }
    Item {
        anchors.bottom: parent.bottom; width: parent.width; height: 56
        Rectangle { width: parent.width; height: 1; color: root.hairline }
        Text { x: 24; anchors.verticalCenter: parent.verticalCenter; text: root.mode==="locked" ? "♙  Экран заблокирован" : root.mode==="screensaver" ? "◇  Заставка · экран не заблокирован" : "◇  Предпросмотр"; font.family: root.theme.fontFamily; font.pixelSize: 11; color: root.secondary }
        Text {
            anchors.centerIn: parent; visible: root.width>1050
            objectName:"activitySummary"
            text: root.discovery==="scanning" ? "Поиск действующих чатов…" : root.monitored.some(function(c){return c.status==="waiting_input";}) ? "Есть ожидание ответа" : root.monitored.some(function(c){return c.status==="working";}) ? "Работа продолжается" : root.discovery!=="ready" || root.monitored.some(function(c){return c.status==="unknown" || c.status==="disconnected";}) ? "Источник не полностью доступен" : root.monitored.length ? "Чаты завершены" : "Нет действующих чатов"
            font.family: root.theme.fontFamily; font.pixelSize: 11; color: root.secondary
        }
        Rectangle {
            anchors.right: parent.right; anchors.rightMargin: 24; anchors.verticalCenter: parent.verticalCenter
            width: actionLabel.implicitWidth+22; height: 31; color: "transparent"; border.color: root.hairline
            Text { id: actionLabel; anchors.centerIn: parent; text: root.mode==="locked" ? "Ввод пароля  ↗" : root.mode==="screensaver" ? "Любая клавиша — вернуться" : "Живой контекст"; font.family: root.theme.fontFamily; font.pixelSize: 11; color: root.ink }
            MouseArea { anchors.fill: parent; enabled: root.mode==="locked"; onClicked: root.passwordRequested() }
        }
    }
    Timer { interval: 1000; repeat: true; running: root.visible; onTriggered: root.clockText=Qt.formatTime(new Date(),"hh:mm") }
    Timer { interval: 20000; repeat: true; running: root.visible && root.rotate && root.pages > 1; onTriggered: root.advance() }
    Timer { interval: 100; repeat: true; running: root.visible; onTriggered: if (root.lastFrameAt > 0 && Date.now() - root.lastFrameAt >= 5000) root.disconnected() }
}
