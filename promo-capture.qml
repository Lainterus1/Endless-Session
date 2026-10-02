import QtQuick
import QtQuick.Window
import Quickshell
import "ui"

// Synthetic events rendered with the production Dashboard, never a Codex session.
ShellRoot {
    id: root
    property int sequence: 0
    property int frameNumber: 0
    property var chats: []
    readonly property var palette: ({foreground: "#d7ded7", background: "#101819",
        accent: "#a9d3b5", fontFamily: "monospace"})
    readonly property string outputDirectory: Quickshell.env("ENDLESS_PROMO_FRAMES")

    function uuid(index) {
        return "00000000-0000-4000-8000-" + String(index + 1).padStart(12, "0");
    }
    function message(id, text, phase) {
        return {id: id, type: "message", phase: phase || "commentary", timestamp: null, text: text};
    }
    function command(id) {
        return {id: id, type: "command", timestamp: null,
            command: "python3 -m unittest", argv: ["python3", "-m", "unittest"], cwd: null,
            output: "Selected checks passed.", status: "completed", exit_code: 0};
    }
    function fileChange(id) {
        return {id: id, type: "file_change", timestamp: null, status: "completed",
            changes: {"ui/ContextLane.qml": {type: "update",
                unified_diff: "- pushOffset = oldOffset\n+ pushOffset = oldOffset - distance\n+ drift starts after push"}}};
    }
    function userReply(id) {
        return {id: id, type: "user_reply", timestamp: null,
            text: "Check the lock screen first."};
    }
    function chat(index, name, status, items) {
        return {thread_id: uuid(index), name: name, source_epoch: 0,
            status: status, pending_questions: status === "waiting_input" ? 1 : 0,
            reset: true, items: items};
    }
    function publish(changedId, item, added) {
        var delta = chats.map(function(current) {
            return {thread_id: current.thread_id, name: current.name,
                source_epoch: current.source_epoch, status: current.status,
                pending_questions: current.pending_questions, reset: added && current.thread_id === changedId,
                items: current.thread_id === changedId ? (added ? current.items : [item]) : []};
        });
        dashboard.receive(JSON.stringify({schema_version: 1, sequence: ++sequence,
            discovery: "ready", unknown_count: 0, theme: palette, chats: delta}));
    }
    function addChat(index, name, status, items) {
        var next = chat(index, name, status, items);
        chats = chats.concat([next]);
        publish(next.thread_id, null, true);
    }
    function addItem(index, item, status) {
        var next = chats.slice();
        var current = Object.assign({}, next[index]);
        current.items = current.items.concat([item]);
        if (status) current.status = status;
        current.pending_questions = current.status === "waiting_input" ? 1 : 0;
        next[index] = current;
        chats = next;
        publish(current.thread_id, item, false);
    }
    function priorityQuestion() {
        return {id: "source-question", type: "question", timestamp: null,
            call_id: "synthetic-question", questions: [{index: 0, question_id: null,
                question: "What should I check next: the lock screen or the theme?",
                options: ["Lock screen", "Theme"]}]};
    }
    function advanceScene(n) {
        if (n === 23) addItem(0, message("thought-2",
            "New events push older blocks upward, then the feed keeps drifting."));
        if (n === 43) addItem(0, command("check-1"));
        if (n === 63) addChat(1, "Source verification", "waiting_input", [
            message("source-1", "Checking active chats and excluding service sessions."),
            priorityQuestion()]);
        if (n === 83) addItem(0, fileChange("change-1"));
        if (n === 101) addChat(2, "Omarchy theme", "working", [
            message("theme-1", "Adapting card contrast to the selected Omarchy theme.")]);
        if (n === 117) dashboard.mode = "locked";
        if (n === 127) addItem(1, userReply("reply-1"), "working");
        if (n === 143) addItem(2, message("theme-2",
            "Three independent feeds remain readable on the lock screen."));
        if (n === 160) addItem(0, message("thought-3",
            "The session is still active; its public context keeps updating."));
        if (n === 176) addItem(0, message("final-1",
            "Animation and lock-screen checks are complete.", "final_answer"), "idle");
    }

    Window {
        id: window
        width: 1360
        height: 800
        visible: true
        title: "Endless Session · synthetic promo"
        color: root.palette.background

        Dashboard {
            id: dashboard
            anchors.fill: parent
            rotate: false
            mode: "screensaver"
            motionEnabled: true
        }
        Rectangle {
            id: titleCard
            anchors.fill: parent
            color: root.palette.background
            z: 100
            opacity: root.frameNumber < 6 ? 1 : root.frameNumber < 18 ? (18 - root.frameNumber) / 12
                : root.frameNumber > 185 ? Math.min(1, (root.frameNumber - 185) / 18) : 0
            visible: opacity > 0
            Column {
                anchors.centerIn: parent
                width: Math.min(parent.width - 120, 980)
                spacing: 20
                Text { text: "◇  OMARCHY  /  CODEX"; color: root.palette.accent;
                    font.family: "monospace"; font.pixelSize: 20; font.bold: true }
                Rectangle { width: 96; height: 3; color: root.palette.accent }
                Text { text: "ENDLESS SESSION"; color: root.palette.foreground;
                    font.family: "monospace"; font.pixelSize: 70; font.bold: true }
                Text { text: "LIVE CONTEXT FROM ACTIVE CODEX CHATS";
                    color: "#91a59b"; font.family: "monospace"; font.pixelSize: 20 }
                Text { text: "Synthetic demo · production QML components";
                    color: "#71857c"; font.family: "monospace"; font.pixelSize: 15 }
            }
        }
        Rectangle {
            x: (parent.width - width) / 2
            y: 18
            width: 140
            height: 23
            color: "#21392d"
            radius: 3
            visible: titleCard.opacity < 0.5
            Text { anchors.centerIn: parent; text: "SYNTHETIC  /  QML";
                color: "#cae2d0"; font.family: "monospace"; font.pixelSize: 10 }
        }
    }

    Timer {
        interval: 70
        running: true
        onTriggered: root.addChat(0, "Screensaver plugin", "working", [
            root.message("opening-1", "Checking how public Codex events appear on the idle screen.")])
    }
    Timer {
        id: captureTimer
        interval: 50
        repeat: true
        running: true
        onTriggered: {
            if (!root.chats.length || root.outputDirectory === "") return;
            root.advanceScene(root.frameNumber);
            var number = root.frameNumber;
            window.contentItem.grabToImage(function(result) {
                var name = String(number).padStart(3, "0");
                if (!result.saveToFile(root.outputDirectory + "/frame-" + name + ".png")) {
                    console.log("PROMO_CAPTURE_FAILED " + name);
                    Qt.quit();
                }
            });
            root.frameNumber++;
            if (root.frameNumber >= 210) { captureTimer.stop(); doneTimer.start(); }
        }
    }
    Timer { id: doneTimer; interval: 1500; onTriggered: { console.log("PROMO_FRAMES " + root.frameNumber); Qt.quit(); } }
}
