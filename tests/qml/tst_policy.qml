import QtQuick
import QtTest
import "../../ui"

TestCase {
    id: test
    name: "DisplayPolicy"
    when: windowShown
    property var policy
    property int wakes: 0
    property var releases: []
    Component { id: factory; DisplayPolicy { liveClock: false; clockNow: 1000; discovery: "ready" } }
    function init() {
        wakes = 0; releases = [];
        policy = createTemporaryObject(factory, test);
        policy.wakeRequested.connect(function() { test.wakes++; });
        policy.releaseRequested.connect(function(timeout) { test.releases.push(timeout); });
    }
    function chat(id, status, pending) { return {thread_id:id,status:status,pending_questions:pending || 0}; }
    function time(value) { policy.clockNow = value; policy.refresh(); }
    function test_pending_and_hidden_active_keep_display() {
        policy.monitored = [chat("done","idle"),chat("question","waiting_input",1),chat("worker","working")]; policy.locked = true;
        verify(policy.hold); compare(wakes,1);
        policy.monitored = [chat("done","idle"),chat("question","waiting_input",1),chat("worker","idle")];
        verify(policy.hold); compare(releases.length,0);
        var seven = []; for (var i=0; i<6; i++) seven.push(chat("idle"+i,"idle")); seven.push(chat("hidden","working"));
        policy.monitored = seven; verify(policy.hold);
        seven[6] = chat("hidden","waiting_input",1); policy.monitored = seven.slice().reverse(); verify(policy.hold);
        compare(releases.length,0);
    }
    function test_all_completed_empty_new_activity_and_unlock() {
        policy.monitored = [chat("a","working")]; policy.locked = true;
        policy.monitored = [chat("a","idle")]; verify(!policy.hold); verify(policy.decision.all_completed); compare(releases,[false]);
        policy.monitored = []; verify(!policy.hold); compare(policy.decision.reason,"empty"); verify(!policy.decision.all_completed);
        policy.monitored = [chat("new","working")]; compare(wakes,2); verify(policy.hold);
        policy.locked = false; verify(!policy.hold); compare(policy.decision.reason,"unlocked");
        policy.monitored = [chat("new","waiting_input",1)]; compare(wakes,2); compare(releases,[false]);
    }
    function test_loss_five_minutes_heartbeat_recovery_and_fresh_loss() {
        policy.monitored = [chat("lost","disconnected",1)]; policy.locked = true;
        time(300999); verify(policy.hold); verify(!policy.decision.all_completed);
        policy.monitored = [chat("lost","disconnected",1)];
        time(301000); verify(!policy.hold); compare(policy.decision.reason,"loss_timeout"); compare(releases,[true]);
        verify(!policy.decision.all_completed);
        policy.monitored = [chat("lost","working")]; verify(policy.hold); compare(wakes,2);
        policy.monitored = [chat("lost","unknown")]; time(600999); verify(policy.hold);
        time(601000); verify(!policy.hold); compare(releases,[true,true]);
    }
    function test_discovery_error_and_new_uncertain_source() {
        policy.discovery = "scanning"; policy.locked = true;
        time(301000); verify(!policy.hold); verify(!policy.decision.all_completed);
        policy.discovery = "unknown"; verify(!policy.hold);
        policy.monitored = [chat("new-error","unknown")]; verify(policy.hold);
        time(601000); verify(!policy.hold);
        policy.discovery = "ready"; policy.monitored = []; compare(policy.decision.reason,"empty");
    }
    function test_manual_wake_suspend_and_password_priority() {
        policy.monitored = [chat("lost","disconnected")]; policy.locked = true; time(301000); verify(!policy.hold);
        policy.manualWake(); verify(policy.hold); time(305999); verify(policy.hold); time(306000); verify(!policy.hold);
        policy.tick(306100); policy.tick(400000); verify(policy.hold); compare(policy.decision.reason,"wake_grace");
        time(404999); verify(policy.hold);
        policy.authenticatingPassword = true; time(405000); verify(policy.hold); compare(policy.decision.reason,"password");
        policy.authenticatingPassword = false; verify(!policy.hold);
        policy.locked = false; compare(Object.keys(policy.lossStarts).length,0);
    }
}
