import QtQuick
import QtTest
import "../../ui"
import "../../ui/NativeTheme.js" as NativeTheme

TestCase {
    id: test
    name: "Dashboard"
    width: 1440; height: 1000; visible: true; when: windowShown
    property var dashboard
    Component { id: factory; Dashboard { width: 1440; height: 1000; rotate: false } }
    Component { id: hubFactory; ContextHub { rotate: false } }
    Component { id: anchoredFactory; Dashboard { anchors.fill: parent; rotate: false } }
    function init() { dashboard = createTemporaryObject(factory, test); }
    function id(number) { return "00000000-0000-4000-8000-" + String(number).padStart(12, "0"); }
    function chat(number, text) { return {thread_id: id(number), name: "Чат " + number, source_epoch: 0, reset: true, status: "working", pending_questions: 0,
        items: [{id: "shared-id", type: "message", phase: "commentary", timestamp: null, text: text || "Текст " + number}]}; }
    function frame(chats, sequence, light) { return {schema_version: 1, sequence: sequence || 1, discovery: "ready", unknown_count: 0, chats: chats,
        theme: light ? {foreground:"#111111",background:"#ffffff",accent:"#333333",fontFamily:"serif"} : {foreground:"#cacccc",background:"#101315",accent:"#cacccc",fontFamily:"monospace"}}; }
    function send(value) { verify(dashboard.receive(JSON.stringify(value))); }
    function test_isolation_identity_and_removal() {
        send(frame([chat(1), chat(2), chat(3)]));
        var first = dashboard.panels[id(1)], third = dashboard.panels[id(3)];
        var changed = chat(1, "Обновлён только первый"); changed.reset = false;
        var same = chat(3); same.reset = false; same.items = [];
        send(frame([changed, same], 2));
        compare(dashboard.panels[id(1)], first); compare(dashboard.panels[id(3)], third);
        compare(first.lane.find("shared-id").body, "Обновлён только первый");
        compare(third.lane.find("shared-id").body, "Текст 3"); compare(Object.keys(dashboard.panels).length, 2);
    }
    function test_pages_keep_full_roster_and_resize_reflows() {
        var chats = []; for (var i = 1; i <= 7; i++) chats.push(chat(i, ("Текст " + i + " ").repeat(100)));
        send(frame(chats)); compare(dashboard.monitored.length, 7); compare(Object.keys(dashboard.panels).length, 4);
        dashboard.advance(); compare(dashboard.visibleIds, [id(5), id(6), id(7)]);
        compare(dashboard.panels[id(5)].lane.cards[0].body, chats[4].items[0].text);
        dashboard.page = 0; dashboard.syncPanels(null);
        var first = dashboard.panels[id(1)];
        first.lane.motion = false;
        dashboard.width = 700;
        compare(dashboard.monitored.length, 7); compare(Object.keys(dashboard.panels).length, 2); compare(dashboard.panels[id(1)], first);
        compare(first.width, 700); verify(first.height > 0);
        var secondPanel=dashboard.panels[id(2)];
        verify(first.y >= 60); verify(first.y+first.height <= secondPanel.y); verify(secondPanel.y+secondPanel.height <= dashboard.height-56);
        var next = chat(1, "Дополнение"); next.reset = false; next.items[0].id = "second";
        var update = chats.map(function(c) { return Object.assign({}, c, {reset:false, items:[]}); }); update[0] = next;
        send(frame(update, 2)); wait(420);
        dashboard.width = 1000;
        var a = first.lane.find("shared-id"), b = first.lane.find("second");
        verify(a !== null && b !== null); verify(b.y >= a.y + a.height + 15);
    }
    function test_theme_preserves_objects_text_and_motion() {
        send(frame([chat(1)])); var panel = dashboard.panels[id(1)]; var card = panel.lane.find("shared-id");
        var next = chat(1); next.reset = false; next.items = [];
        send(frame([next], 2, true));
        compare(dashboard.panels[id(1)], panel); compare(panel.lane.find("shared-id"), card);
        compare(card.body, "Текст 1"); compare(card.foreground, "#111111"); compare(card.background, "#ffffff"); compare(card.fontFamily, "serif");
        var before = card.y; wait(150); verify(card.y < before);
    }
    function test_unknown_discovery_and_bad_packet_keep_context() {
        send(frame([chat(1)]));
        var data = frame([chat(1)], 2); data.discovery = "unknown"; send(data);
        compare(dashboard.monitored.length, 1); compare(dashboard.discovery, "unknown");
        verify(!dashboard.receive("{broken")); compare(dashboard.monitored.length, 1);
        compare(dashboard.panels[id(1)].status, "disconnected");
    }
    function test_disconnected_chat_is_not_labelled_completed() {
        var lost=chat(1);lost.status="disconnected";send(frame([lost]));
        compare(findChild(dashboard,"activitySummary").text,"Источник не полностью доступен");
    }
    function test_shared_feed_and_late_monitor() {
        var hub = createTemporaryObject(hubFactory, test);
        hub.attach(dashboard);
        var chats = []; for (var i = 1; i <= 7; i++) chats.push(chat(i));
        verify(hub.receive(JSON.stringify(frame(chats))));
        var second = createTemporaryObject(factory, test);
        hub.attach(second);
        compare(second.monitored.length, 7); compare(second.panels[id(1)].lane.cards[0].body, "Текст 1");
        hub.advance(); compare(dashboard.visibleIds, second.visibleIds); compare(dashboard.visibleIds, [id(5),id(6),id(7)]);
        second.width = 700;
        compare(dashboard.capacity, 2); compare(dashboard.visibleIds, second.visibleIds);
        hub.disconnected();
        var third = createTemporaryObject(factory, test); hub.attach(third);
        compare(third.discovery, "unknown"); compare(third.monitored[0].status, "disconnected");
        hub.detach(second); compare(hub.dashboards.length, 2);
    }
    function test_anchored_construction_clamps_page_and_creates_visible_panels() {
        var anchored = createTemporaryObject(anchoredFactory, test);
        verify(anchored.receive(JSON.stringify(frame([chat(1), chat(2)]))));
        compare(anchored.page, 0); compare(anchored.visibleIds.length, 2); compare(Object.keys(anchored.panels).length, 2);
        verify(anchored.panels[id(1)].visible); verify(anchored.panels[id(1)].width > 0);
        verify(anchored.panels[id(1)].height > 0);
    }
    function test_native_theme_override_keeps_content_and_falls_back() {
        send(frame([chat(1)])); var panel=dashboard.panels[id(1)], card=panel.lane.find("shared-id");
        dashboard.themeOverride=NativeTheme.normalize("#111111","#ffffff","#999999","test-font");
        compare(card.foreground,"#111111");compare(card.background,"#ffffff");compare(card.fontFamily,"test-font");
        compare(dashboard.theme.accent,"#111111");
        var next=chat(1);next.reset=false;next.items=[];send(frame([next],2));
        compare(card.background,"#ffffff");compare(card.body,"Текст 1");compare(dashboard.panels[id(1)],panel);
        dashboard.themeOverride=NativeTheme.normalize("#aaaaaa","#aaaaaa","transparent","");
        compare(card.foreground,"#cacccc");compare(card.background,"#101315");compare(card.fontFamily,"monospace");
    }

    function test_reference_composition_single_and_three_columns() {
        send(frame([chat(1)]));var one=dashboard.panels[id(1)];
        verify(one.width<=810);compare(one.x,(dashboard.width-one.width)/2);verify(one.y>=60);verify(one.y+one.height<=dashboard.height-56);
        send(frame([chat(1),chat(2),chat(3)],2));
        var a=dashboard.panels[id(1)],b=dashboard.panels[id(2)],c=dashboard.panels[id(3)];
        compare(a.y,b.y);compare(b.y,c.y);verify(a.x+a.width<=b.x);verify(b.x+b.width<=c.x);verify(b.showDivider && c.showDivider);
    }
    function test_hub_preserves_frames_without_surface_at_handoff() {
        var hub=createTemporaryObject(hubFactory,test);
        verify(hub.receive(JSON.stringify(frame([chat(1,"До блокировки")]))));
        hub.attach(dashboard);compare(dashboard.panels[id(1)].lane.cards[0].body,"До блокировки");
        hub.detach(dashboard);compare(hub.dashboards.length,0);
        var next=chat(1,"Во время перехода");next.reset=false;next.items[0].id="transition";
        verify(hub.receive(JSON.stringify(frame([next],2))));
        var secure=createTemporaryObject(factory,test);hub.attach(secure);
        compare(secure.panels[id(1)].lane.cardCount,2);
        compare(secure.panels[id(1)].lane.find("transition").body,"Во время перехода");
        hub.detach(secure);hub.disconnected();
        var late=createTemporaryObject(factory,test);hub.attach(late);
        compare(late.discovery,"unknown");compare(late.monitored[0].status,"disconnected");
    }

}
