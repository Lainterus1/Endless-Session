import QtQuick
import "StreamModel.js" as Model

Item {
    id: root
    clip: true
    property color foreground: "#cacccc"
    property color background: "#101315"
    property color accent: "#b1c7d4"
    property string fontFamily: "monospace"
    property int pushMs: 380
    property real speed: 16
    property int sequence: 0
    property real sceneTime: 0
    property real depth: 0.4
    property bool settled: false
    property real textSize: 15
    readonly property int gap: 22
    property bool motion: true
    property real pushOffset: 0
    property real driftOffset: 0
    readonly property real offset: pushOffset + driftOffset
    property var cards: []
    property double lastTick: Date.now()
    readonly property int cardCount: cards.length

    function clear() {
        push.stop(); cards.forEach(function(card) { card.destroy(); });
        cards = []; pushOffset = 0; driftOffset = 0; sequence = 0;
    }
    function find(id) {
        for (var i = 0; i < cards.length; ++i) if (cards[i].itemId === id) return cards[i];
        return null;
    }
    function make(item) {
        return factory.createObject(root, {itemId: item.id, label: Model.label(item), body: Model.body(item), event: item, ordinal: ++sequence});
    }
    function reset(items) {
        clear();
        var created = []; var bottom = 0;
        items.forEach(function(item) {
            var card = make(item); card.baseY = bottom;
            bottom += card.height + gap; created.push(card);
        });
        cards = created;
        pushOffset = height - 18 - Math.max(0, bottom - gap);
    }
    function upsert(item) {
        var card = find(item.id);
        if (card) {
            card.event = item; card.body = Model.body(item); card.label = Model.label(item);
            reflow();
            return;
        }
        card = make(item);
        var last = cards.length ? cards[cards.length - 1] : null;
        card.baseY = Math.max(height - offset, last ? last.baseY + last.height + gap : 0);
        cards = cards.concat([card]);
        push.stop();
        var distance = card.baseY + offset - height + Math.min(card.height, height * 0.85) + 18;
        if (motion) { push.from = pushOffset; push.to = pushOffset - distance; push.start(); }
        else pushOffset -= distance;
    }
    function prune() {
        var keep = [];
        cards.forEach(function(card, index) {
            if (index < cards.length - 1 && card.baseY + card.height + offset < -32) card.destroy(); else keep.push(card);
        });
        if (keep.length !== cards.length) cards = keep;
    }
    function reflow() {
        for (var i = 1; i < cards.length; ++i) cards[i].baseY = cards[i - 1].baseY + cards[i - 1].height + root.gap;
    }
    onMotionChanged: if (!motion) push.stop()
    Canvas {
        id: dots
        anchors.fill: parent
        onPaint: {
            var ctx=getContext("2d");ctx.clearRect(0,0,width,height);ctx.fillStyle=Qt.rgba(root.foreground.r,root.foreground.g,root.foreground.b,0.14);
            for(var x=10;x<width;x+=21)for(var y=10;y<height;y+=21){ctx.beginPath();ctx.arc(x,y,0.65,0,Math.PI*2);ctx.fill();}
        }
        Connections { target: root; function onForegroundChanged() { dots.requestPaint(); } }
    }
    Rectangle { z: 100; width: parent.width; height: 35; gradient: Gradient { GradientStop { position: 0; color: root.background } GradientStop { position: 1; color: Qt.rgba(root.background.r,root.background.g,root.background.b,0) } } }
    Component {
        id: factory
        ContextCard {
            id: visualCard
            width: root.width - 22
            x: 9 + (latest ? 0 : Math.sin(root.sceneTime / 2.6 + ordinal * 1.6) * root.depth * 3)
            latest: root.cards.length > 0 && root.cards[root.cards.length-1] === visualCard
            textSize: root.textSize
            readonly property real distance: Math.max(0,Math.min(1,1-(y+height/2)/Math.max(1,root.height)))
            scale: latest ? 1 : 1 - root.depth * distance * 0.035
            opacity: Math.max(0,Math.min(1,(y+height)/95)) * (1 - (latest ? 0 : root.depth * distance * 0.16))
            y: baseY + root.offset
            foreground: root.foreground; background: root.background; accent: root.accent
            fontFamily: root.fontFamily
            onHeightChanged: root.reflow()
        }
    }
    NumberAnimation { id: push; target: root; property: "pushOffset"; duration: root.pushMs; easing.type: Easing.OutCubic }
    Timer {
        interval: 16; repeat: true; running: root.visible && root.motion
        onTriggered: {
            var now = Date.now();
            var dt = Math.min(0.1, (now - root.lastTick) / 1000);
            root.sceneTime += dt;
            if (root.cards.length && !push.running) {
                var tail = root.cards[root.cards.length-1];
                var stop = tail.height > root.height - 48 ? root.height-tail.height-18
                    : root.settled ? Math.max(30,(root.height-tail.height)*0.55) : Math.max(30,Math.min(100,(root.height-tail.height)/3));
                // A status/size change may move the stop below the current position;
                // the queue must never jump down. Tall cards travel to their end.
                root.driftOffset = Math.min(root.driftOffset,Math.max(stop-tail.baseY-root.pushOffset,root.driftOffset-root.speed*dt));
            }
            root.lastTick = now; root.prune();
        }
        onRunningChanged: root.lastTick = Date.now()
    }
}
