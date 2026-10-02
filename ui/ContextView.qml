import QtQuick
import "StreamModel.js" as Model
import "VisualStyle.js" as Style

Rectangle {
    id: root
    property string threadId: ""
    property int sessionIndex: 1
    property bool compact: false
    property bool showDivider: false
    property double now: Date.now()
    readonly property color secondary: Style.mix(background,foreground,0.66)
    property string chatName: "Ожидание источника"
    property string status: "unknown"
    property int pendingQuestions: 0
    property int sourceEpoch: -1
    property double lastSequence: 0
    property double lastFrameAt: 0
    property bool needsReset: true
    property int timeoutMs: 5000
    property color foreground: "#cacccc"
    property color background: "#101315"
    property color accent: "#b1c7d4"
    property string fontFamily: "monospace"
    property bool motionEnabled: true
    property alias lane: lane
    color: background

    function disconnected() { status = "disconnected"; }
    function restartTransport() { disconnected(); lastSequence = 0; needsReset = true; }
    function receive(line) {
        var frame;
        try { frame = JSON.parse(line); } catch (error) { status = "unknown"; return false; }
        if (!Model.validFrame(frame, threadId)) { status = "unknown"; return false; }
        if (frame.sequence <= lastSequence) return false;
        var chat = frame.chats[0];
        if ((needsReset || sourceEpoch !== chat.source_epoch) && !chat.reset) { status = "unknown"; return false; }
        if (chat.reset) lane.reset(chat.items); else chat.items.forEach(function(item) { lane.upsert(item); });
        sourceEpoch = chat.source_epoch; needsReset = false;
        chatName = chat.name; status = chat.status; pendingQuestions = chat.pending_questions;
        lastSequence = frame.sequence; lastFrameAt = Date.now();
        return true;
    }
    Rectangle { width: 1; height: parent.height; visible: root.showDivider; color: Style.mix(root.background,root.foreground,0.18) }
    Item {
        x: 24; y: 8; width: parent.width-48; height: 103
        Text { text: String(root.sessionIndex).padStart(2,"0")+"  / codex"; font.family: root.fontFamily; font.pixelSize: 11; color: root.accent }
        Text { anchors.right: parent.right; text: (root.status === "working" ? "◌  " : root.status === "idle" ? "✓  " : "◇  ")+Style.statusLabel(root.status); font.family: root.fontFamily; font.pixelSize: 11; color: root.status === "working" ? root.secondary : root.accent }
        Text {
            y: 25; width: parent.width; height: 53
            text: root.chatName; textFormat: Text.PlainText
            font.family: root.fontFamily; font.pixelSize: root.compact ? 17 : 21; lineHeight: 1.4; color: root.foreground
            wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight
        }
        Text { y: 82; text: "Фрагменты мыслей / публичные события"; font.family: root.fontFamily; font.pixelSize: 11; color: root.secondary }
    }
    ContextLane {
        id: lane
        x: 24; y: 120; width: parent.width-48; height: Math.max(0,parent.height-154)
        foreground: root.foreground; background: root.background; accent: root.accent; fontFamily: root.fontFamily
        textSize: root.compact ? 13 : 15
        settled: root.status === "waiting_input" || root.status === "idle"
        motion: root.motionEnabled && root.status !== "unknown" && root.status !== "disconnected"
    }
    Text {
        x: 33; y: parent.height-23; width: parent.width-66
        text: root.status === "waiting_input" ? "Ожидание ответа · вопросов: "+root.pendingQuestions : root.status === "disconnected" || root.status === "unknown" ? "Последний контекст · без обновлений "+Math.max(0,Math.floor((root.now-root.lastFrameAt)/1000))+" с" : root.status === "idle" ? "Чат завершён" : "Публичные сообщения, действия и результаты"
        textFormat: Text.PlainText; font.family: root.fontFamily; font.pixelSize: 11; color: root.secondary; elide: Text.ElideRight
    }
    Timer {
        interval: 100; repeat: true; running: root.visible
        onTriggered: { root.now=Date.now(); if (root.lastFrameAt > 0 && root.now - root.lastFrameAt >= root.timeoutMs) root.disconnected(); }
    }
}
