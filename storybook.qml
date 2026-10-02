import QtQuick
import QtQuick.Window
import Quickshell
import "ui"
import "storybook"
import "storybook/Fixtures.js" as Fixtures

ShellRoot {
    id: root
    property int storyIndex: 2
    property int viewportIndex: 1
    property int themeIndex: 0
    property int modeIndex: 0
    property int rateIndex: 1
    property bool playing: false
    property bool stepAnimating: false
    property bool showPassword: false
    property int stepIndex: 0
    property int sequence: 0
    property var chats: []
    property real motionPushStart: 0
    property real motionPushMid: 0
    property real motionPushAfter: 0
    property real motionDriftAfter: 0
    property real motionDriftLate: 0
    readonly property var story: Fixtures.stories[storyIndex]
    readonly property int viewportWidth: [820,1360,1680][viewportIndex]
    readonly property int playbackInterval: [2400,1400,800][rateIndex]
    readonly property var palette: themeIndex ? Fixtures.light : Fixtures.dark

    function frame(changes) {
        return JSON.stringify({schema_version:1,sequence:++sequence,
            discovery:story.discovery,unknown_count:story.discovery === "unknown" ? 1 : 0,
            theme:palette,chats:changes});
    }
    function selectStory(index) {
        storyIndex = index; resetStory();
    }
    function resetStory() {
        playing = false;
        stepAnimating = false;
        stepMotionTimer.stop();
        showPassword = false;
        stepIndex = 0;
        chats = Fixtures.initial(story);
        dashboard.page = 0;
        dashboard.receive(frame(chats));
    }
    function pulse() {
        if (!dashboard || sequence < 1) return;
        var delta = chats.map(function(chat) {
            return {thread_id:chat.thread_id,name:chat.name,source_epoch:chat.source_epoch,
                status:chat.status,pending_questions:chat.pending_questions,reset:false,items:[]};
        });
        dashboard.receive(frame(delta));
    }
    function nextStep() {
        if (!chats.length) return;
        if (stepIndex >= Fixtures.steps.length) resetStory();
        if (!playing) {
            stepAnimating = true;
            stepMotionTimer.restart();
        }
        var step = Fixtures.steps[stepIndex % Fixtures.steps.length];
        var item = JSON.parse(JSON.stringify(step.item));
        var target = chats[0];
        var index = target.items.findIndex(function(existing) { return existing.id === item.id; });
        if (index >= 0) target.items[index] = item; else target.items.push(item);
        if (item.type === "question") { target.status = "waiting_input"; target.pending_questions = 1; }
        if (item.phase === "final_answer") { target.status = "idle"; target.pending_questions = 0; }
        var delta = chats.map(function(chat, i) {
            return {thread_id:chat.thread_id,name:chat.name,source_epoch:chat.source_epoch,
                status:chat.status,pending_questions:chat.pending_questions,reset:false,items:i === 0 ? [item] : []};
        });
        dashboard.receive(frame(delta));
        stepIndex++;
        if (stepIndex >= Fixtures.steps.length) {
            stepAnimating = true;
            stepMotionTimer.restart();
            playing = false;
        }
    }
    function changeTheme(index) { themeIndex = index; pulse(); }

    Window {
        id: window
        width: 1710; height: 1010; visible: true
        title: "Codex Idle · QML Storybook"
        color: "#0b1114"
        Rectangle {
            anchors.fill: parent
            color: "#0b1114"
            Rectangle {
                id: sidebar
                width: 314; height: parent.height
                color: "#11191d"
                Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: "#33443e" }
                Flickable {
                    anchors.fill: parent
                    clip: true
                    contentHeight: sidebarContent.height + 42
                    boundsBehavior: Flickable.StopAtBounds
                    Column {
                        id: sidebarContent
                        x: 18; y: 20; width: sidebar.width - 36; spacing: 10
                        Text { text: "◈  OMARCHY / CODEX"; color: "#a9d3b5"; font.family:"monospace"; font.pixelSize:14; font.bold:true }
                        Text { text: "STORYBOOK  ·  QML"; color: "#dce7df"; font.family:"monospace"; font.pixelSize:24; font.bold:true }
                        Text { width: parent.width; wrapMode: Text.Wrap; text:"Вымышленные события · настоящие компоненты интерфейса"; color:"#8fa69c"; font.family:"monospace"; font.pixelSize:11; lineHeight:1.45 }
                        Item { width:1; height:12 }
                        Text { text:"СЦЕНАРИИ"; color:"#8fa69c"; font.family:"monospace"; font.pixelSize:11; font.bold:true }
                        Repeater {
                            model: Fixtures.stories
                            delegate: StoryButton {
                                required property int index
                                required property var modelData
                                width: sidebarContent.width
                                label: modelData.label
                                detail: modelData.detail
                                selected: root.storyIndex === index
                                onClicked: root.selectStory(index)
                            }
                        }
                        Item { width:1; height:12 }
                        Text { text:"ОБЛАСТЬ ПРОСМОТРА"; color:"#8fa69c"; font.family:"monospace"; font.pixelSize:11; font.bold:true }
                        Row {
                            spacing:6
                            Repeater {
                                model: ["820","1360","1680"]
                                delegate: StoryButton {
                                    required property int index
                                    required property string modelData
                                    width: (sidebarContent.width-12)/3; compact:true
                                    label: modelData; selected:root.viewportIndex===index
                                    onClicked: root.viewportIndex=index
                                }
                            }
                        }
                        Text { text:"ТЕМА"; color:"#8fa69c"; font.family:"monospace"; font.pixelSize:11; font.bold:true }
                        Row {
                            spacing:6
                            Repeater {
                                model: ["Тёмная","Светлая"]
                                delegate: StoryButton {
                                    required property int index
                                    required property string modelData
                                    width:(sidebarContent.width-6)/2; compact:true
                                    label:modelData; selected:root.themeIndex===index
                                    onClicked: root.changeTheme(index)
                                }
                            }
                        }
                        Text { text:"РЕЖИМ"; color:"#8fa69c"; font.family:"monospace"; font.pixelSize:11; font.bold:true }
                        Row {
                            spacing:6
                            Repeater {
                                model: ["До блокировки","Заблокировано"]
                                delegate: StoryButton {
                                    required property int index
                                    required property string modelData
                                    width:(sidebarContent.width-6)/2; compact:true
                                    label:modelData; selected:root.modeIndex===index
                                    onClicked: { root.modeIndex=index; root.showPassword=false; }
                                }
                            }
                        }
                        StoryButton {
                            width:sidebarContent.width; compact:true
                            label:root.showPassword ? "Скрыть наложение пароля" : "Показать наложение пароля"
                            selected:root.showPassword
                            onClicked: if(root.modeIndex===1)root.showPassword=!root.showPassword
                        }
                        Text { width:parent.width; wrapMode:Text.Wrap; text:"Пароль — только макет. PAM и настоящая блокировка не запускаются."; color:"#789086"; font.family:"monospace"; font.pixelSize:10; lineHeight:1.4 }
                    }
                }
            }
            Item {
                id: content
                x: sidebar.width; width: parent.width-sidebar.width; height:parent.height
                Text {
                    x:28; y:22; width:parent.width-56
                    text:root.story.label
                    color:"#ecf1eb"; font.family:"monospace"; font.pixelSize:24; font.bold:true
                }
                Text {
                    x:29; y:56; width:parent.width-58
                    text:root.story.detail+"  /  "+root.viewportWidth+" × 900  /  шаг "+root.stepIndex+" из "+Fixtures.steps.length
                    color:"#91a59b"; font.family:"monospace"; font.pixelSize:12
                }
                Row {
                    x:28; y:91; spacing:8
                    StoryButton {
                        width:116; label:root.playing ? "Пауза Ⅱ" : "Пуск ▶"
                        emphasized:true
                        onClicked: {
                            if (!root.chats.length) return;
                            if (!root.playing && root.stepIndex >= Fixtures.steps.length) root.resetStory();
                            root.playing=!root.playing;
                        }
                    }
                    StoryButton { width:108; label:"Шаг →"; onClicked:root.nextStep() }
                    StoryButton { width:108; label:"Сброс ↺"; onClicked:root.resetStory() }
                    StoryButton {
                        width:105; label:"← Страница"
                        onClicked: { dashboard.page=Math.max(0,dashboard.page-1); dashboard.syncPanels(null); }
                    }
                    StoryButton {
                        width:105; label:"Страница →"
                        onClicked: { dashboard.page=Math.min(dashboard.pages-1,dashboard.page+1); dashboard.syncPanels(null); }
                    }
                    Repeater {
                        model:["½×","1×","2×"]
                        delegate: StoryButton {
                            required property int index
                            required property string modelData
                            width:51; compact:false
                            label:modelData; selected:root.rateIndex===index
                            onClicked:root.rateIndex=index
                        }
                    }
                }
                Rectangle {
                    id: stage
                    x:20; y:151; width:parent.width-40; height:parent.height-174
                    radius:12; color:"#080e11"; border.width:1; border.color:"#2e433b"
                    clip:true
                    Item {
                        id: previewCanvas
                        width:root.viewportWidth; height:900
                        transformOrigin:Item.TopLeft
                        scale:Math.min((stage.width-56)/width,(stage.height-48)/height,1)
                        x:(stage.width-width*scale)/2
                        y:(stage.height-height*scale)/2
                        Dashboard {
                            id: dashboard
                            anchors.fill:parent
                            rotate:false
                            mode:root.modeIndex ? "locked" : "screensaver"
                            motionEnabled:root.playing || root.stepAnimating
                            onPasswordRequested: if(root.modeIndex===1)root.showPassword=true
                        }
                        Rectangle {
                            anchors.centerIn:parent
                            width:Math.min(parent.width-80,420); height:184
                            visible:root.showPassword && root.modeIndex===1
                            color:root.palette.background
                            border.color:root.palette.accent; border.width:1
                            radius:6; z:1000
                            Rectangle { x:0; y:0; width:parent.width; height:4; color:root.palette.accent }
                            Column {
                                x:24; y:22; width:parent.width-48; spacing:12
                                Text { text:"ДЕМО  /  ВВОД ПАРОЛЯ"; color:root.palette.accent; font.family:"monospace"; font.pixelSize:12 }
                                Text { text:"Разблокировка Omarchy"; color:root.palette.foreground; font.family:"monospace"; font.pixelSize:20 }
                                Rectangle {
                                    width:parent.width; height:38; color:"transparent"
                                    border.color:root.palette.accent
                                    Text { anchors.centerIn:parent; text:"••••••••"; color:root.palette.foreground; font.pixelSize:18 }
                                }
                                Text { text:"Макет без ввода, PAM и отправки пароля"; color:root.palette.foreground; font.family:"monospace"; font.pixelSize:11 }
                            }
                        }
                    }
                    Rectangle {
                        x:16; y:14; width:158; height:27; radius:4
                        color:"#1d3128"; z:2000
                        Text { anchors.centerIn:parent; text:"SYNTHETIC  /  QML"; color:"#c9e0d0"; font.family:"monospace"; font.pixelSize:10 }
                    }
                }
            }
        }
    }
    Timer {
        interval:root.playbackInterval; repeat:true; running:root.playing
        onTriggered:root.nextStep()
    }
    Timer { id:stepMotionTimer; interval:850; onTriggered:root.stepAnimating=false }
    Timer { interval:1000; repeat:true; running:true; onTriggered:root.pulse() }
    Timer {
        interval:80; running:true
        onTriggered: {
            var requested = Quickshell.env("OC_STORYBOOK_STORY");
            var index = Fixtures.stories.findIndex(function(candidate) { return candidate.id === requested; });
            if (index >= 0) root.storyIndex = index;
            if (Quickshell.env("OC_STORYBOOK_THEME") === "light") root.themeIndex = 1;
            var width = Number(Quickshell.env("OC_STORYBOOK_WIDTH"));
            if ([820,1360,1680].indexOf(width) >= 0) root.viewportIndex = [820,1360,1680].indexOf(width);
            if (Quickshell.env("OC_STORYBOOK_MODE") === "locked") root.modeIndex = 1;
            root.resetStory();
            var steps = Math.min(9,Math.max(0,Number(Quickshell.env("OC_STORYBOOK_STEPS")) || 0));
            for (var i=0;i<steps;i++) root.nextStep();
            var page = Number(Quickshell.env("OC_STORYBOOK_PAGE")) || 0;
            dashboard.page=Math.max(0,Math.min(dashboard.pages-1,page));
            dashboard.syncPanels(null);
            if (Quickshell.env("OC_STORYBOOK_PASSWORD") === "1" && root.modeIndex===1) root.showPassword=true;
        }
    }
    Timer {
        interval:250; running:Quickshell.env("OC_STORYBOOK_SELFTEST") === "1"
        onTriggered: {
            var index=Fixtures.stories.findIndex(function(candidate){return candidate.id==="burst";});
            root.selectStory(index);
            root.nextStep();
            root.nextStep();
            var deduplicated=dashboard.panels[Fixtures.uuid(0)].lane.cardCount===2
                && dashboard.panels[Fixtures.uuid(0)].lane.find("stream-1")!==null;
            root.resetStory();
            root.changeTheme(1);
            root.viewportIndex=0;
            root.modeIndex=1;
            root.showPassword=true;
            root.playing=true;
            var motionStarted=dashboard.motionEnabled;
            root.playing=false;
            console.log("STORYBOOK_INTERACTION "+JSON.stringify({
                passed:deduplicated && root.stepIndex===0 && dashboard.panels[Fixtures.uuid(0)].lane.cardCount===1
                    && root.themeIndex===1 && root.viewportWidth===820 && root.showPassword
                    && motionStarted && !dashboard.motionEnabled}));
        }
    }
    Timer {
        interval:150; running:Quickshell.env("OC_STORYBOOK_MOTION_TEST") === "1"
        onTriggered: {
            root.nextStep();
            root.motionPushStart=dashboard.panels[Fixtures.uuid(0)].lane.pushOffset;
        }
    }
    Timer {
        interval:350; running:Quickshell.env("OC_STORYBOOK_MOTION_TEST") === "1"
        onTriggered: root.motionPushMid=dashboard.panels[Fixtures.uuid(0)].lane.pushOffset
    }
    Timer {
        interval:600; running:Quickshell.env("OC_STORYBOOK_MOTION_TEST") === "1"
        onTriggered: {
            var lane=dashboard.panels[Fixtures.uuid(0)].lane;
            root.motionPushAfter=lane.pushOffset;
            root.motionDriftAfter=lane.driftOffset;
        }
    }
    Timer {
        interval:900; running:Quickshell.env("OC_STORYBOOK_MOTION_TEST") === "1"
        onTriggered: root.motionDriftLate=dashboard.panels[Fixtures.uuid(0)].lane.driftOffset
    }
    Timer {
        interval:1030; running:Quickshell.env("OC_STORYBOOK_MOTION_TEST") === "1"
        onTriggered: {
            var lane=dashboard.panels[Fixtures.uuid(0)].lane;
            console.log("STORYBOOK_MOTION "+JSON.stringify({
            passed:lane.pushMs===380 && lane.speed===16
                && root.motionPushMid < root.motionPushStart
                && root.motionPushAfter < root.motionPushMid
                && root.motionDriftLate < root.motionDriftAfter
                && !root.stepAnimating && !dashboard.motionEnabled,
            pushMs:lane.pushMs,speed:lane.speed,samplesMs:[150,350,600,900,1030],
            pushStart:root.motionPushStart,pushMid:root.motionPushMid,pushAfter:root.motionPushAfter,
            driftAfter:root.motionDriftAfter,driftLate:root.motionDriftLate,
            stopped:!root.stepAnimating}));
        }
    }
    Timer {
        interval:1100; running:Quickshell.env("OC_STORYBOOK_CAPTURE") !== ""
        onTriggered: {
            console.log("STORYBOOK_STATE "+JSON.stringify({
                story:root.story.id,theme:root.themeIndex ? "light":"dark",
                width:root.viewportWidth,mode:dashboard.mode,count:dashboard.monitored.length,
                page:dashboard.page,pages:dashboard.pages,visible:dashboard.visibleIds.length,
                status:dashboard.monitored.map(function(chat){return chat.status;}),
                cards:Object.keys(dashboard.panels).map(function(id){return dashboard.panels[id].lane.cardCount;}),
                step:root.stepIndex,password:root.showPassword}));
            window.contentItem.grabToImage(function(result) {
                console.log("STORYBOOK_CAPTURE " + result.saveToFile(Quickshell.env("OC_STORYBOOK_CAPTURE")));
                Qt.quit();
            });
        }
    }
}
