import QtQuick
import QtTest
import "../../ui"

TestCase {
    id: test
    name: "Context"
    width: 600; height: 900
    visible: true
    when: windowShown
    property var view
    readonly property string thread: "11111111-1111-4111-8111-111111111111"
    Component { id: component; ContextView { width: 600; height: 900 } }
    function init() { view = createTemporaryObject(component, test, {threadId: thread}); verify(view !== null); view.lane.motion = false; }
    function event(id, text) { return {id: id, type: "message", phase: "commentary", timestamp: null, text: text || id}; }
    function frame(sequence, items, reset, epoch) {
        return {schema_version: 1, sequence: sequence, chats: [{thread_id: thread, name: "Синтетическая сессия", status: "working",
            pending_questions: 0, source_epoch: epoch || 0, reset: reset, items: items}]};
    }
    function send(data) { return view.receive(JSON.stringify(data)); }
    function test_identity_and_update() {
        verify(send(frame(1, [event("a"), event("b")], true)));
        var original = view.lane.find("a");
        verify(send(frame(2, [event("a", "Полностью обновлён")], false)));
        compare(view.lane.cardCount, 2); compare(view.lane.find("a"), original);
        compare(original.body, "Полностью обновлён");
        verify(!send(frame(2, [event("a", "Повтор")], false)));
        compare(original.body, "Полностью обновлён");
    }
    function test_plain_full_long_text_and_burst_no_overlap() {
        view.width = 528;
        compare(view.lane.width, 480);
        verify(send(frame(1, [], true)));
        var text = "<b>Это обычный текст, не HTML.</b>\n\n" + "Длинный абзац Unicode с переносом. ".repeat(160);
        verify(send(frame(2, [event("long", text)], false)));
        var card = view.lane.find("long");
        compare(card.textItem.text, text); compare(card.textItem.textFormat, Text.PlainText);
        verify(card.height > view.lane.height); compare(card.textItem.wrapMode, Text.Wrap);
        for (var i = 0; i < 12; ++i) verify(send(frame(i + 3, [event("burst" + i)], false)));
        wait(450);
        for (var j = 1; j < view.lane.cards.length; ++j) {
            var a = view.lane.cards[j - 1], b = view.lane.cards[j];
            verify(b.y >= a.y + a.height + 15, "Блоки не должны перекрываться");
        }
    }
    function test_common_push_then_continuous_drift() {
        verify(send(frame(1, [event("a"), event("b")], true)));
        var a = view.lane.find("a"), b = view.lane.find("b");
        var ay = a.y, by = b.y;
        verify(send(frame(2, [event("c")], false)));
        wait(440);
        verify(a.y < ay); verify(Math.abs((a.y - ay) - (b.y - by)) < 0.1);
        view.lane.motion = true;
        var before = view.lane.driftOffset, start = Date.now();
        wait(550);
        var elapsed = (Date.now() - start) / 1000;
        verify(Math.abs((before - view.lane.driftOffset) - 16 * elapsed) < 2);
    }
    function test_corruption_and_foreign_thread_are_atomic() {
        verify(send(frame(1, [event("safe")], true)));
        var data = frame(2, [event("bad")], false); data.schema_version = 999;
        verify(!send(data)); compare(view.status, "unknown"); compare(view.lane.cardCount, 1);
        data = frame(3, [event("bad")], false); data.chats[0].thread_id = "foreign";
        verify(!send(data)); verify(view.lane.find("bad") === null);
        verify(!view.receive("{broken")); verify(view.lane.find("safe") !== null);
    }
    function test_loss_timeout_restart_and_epoch() {
        verify(send(frame(1, [event("old")], true)));
        view.disconnected(); compare(view.status, "disconnected"); verify(view.lane.find("old") !== null);
        view.restartTransport();
        verify(!send(frame(1, [event("new")], false, 1))); compare(view.status, "unknown");
        verify(send(frame(1, [event("new")], true, 1))); compare(view.lane.cardCount, 1); verify(view.lane.find("old") === null);
        view.lastFrameAt = Date.now() - 5100;
        tryCompare(view, "status", "disconnected", 300);
        verify(view.lane.find("new") !== null);
    }
    function test_growing_revision_reflows_following_cards() {
        verify(send(frame(1, [event("a"), event("b")], true)));
        verify(send(frame(2, [event("a", "Обновление. ".repeat(100))], false)));
        var a = view.lane.find("a"), b = view.lane.find("b");
        verify(b.y >= a.y + a.height + 15); compare(view.lane.cardCount, 2);
    }
    function test_disconnect_freezes_visible_context() {
        view.destroy();
        view = createTemporaryObject(component, test, {threadId: thread});
        verify(send(frame(1, [event("kept")], true)));
        verify(send(frame(2, [event("pushing")], false)));
        wait(40); view.disconnected();
        var before = view.lane.find("kept").y;
        wait(500);
        compare(view.lane.find("kept").y, before); compare(view.lane.cardCount, 2);
        view.restartTransport();
        verify(send(frame(1, [event("restored")], true, 1)));
        before = view.lane.find("restored").y; wait(120);
        verify(view.lane.find("restored").y < before);
        verify(!view.receive("{broken")); compare(view.status, "unknown");
        before = view.lane.find("restored").y; wait(250);
        compare(view.lane.find("restored").y, before);
    }
    function test_last_block_remains_visible_after_quiet_drift() {
        verify(send(frame(1,[event("a"),event("last")],true)));
        view.lane.speed=10000;view.lane.motion=true;wait(350);
        var last=view.lane.find("last");verify(last!==null);verify(last.y>=29);verify(last.y<view.lane.height);
        var before=last.y;wait(150);compare(last.y,before);verify(last.opacity>0.8);
        view.disconnected();wait(150);compare(last.y,before);
    }
    function test_tall_latest_reaches_end_without_downward_jump() {
        verify(send(frame(1,[event("first")],true)));
        verify(send(frame(2,[event("tall","Длинный вывод. ".repeat(300))],false)));
        wait(420); view.lane.speed=10000;view.lane.motion=true;
        var tail=view.lane.find("tall"),before=tail.y;
        verify(tail.height>view.lane.height);wait(500);
        verify(tail.y<=before);verify(Math.abs(tail.y+tail.height-(view.lane.height-18))<2);
        before=tail.y;view.status="waiting_input";wait(150);compare(tail.y,before);
    }

}
