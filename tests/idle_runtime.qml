import QtQuick
import QtQuick.Window
import QtTest
import Quickshell
import "plugin/companion" as Idle
import "plugin/prelock" as Prelock

ShellRoot {
    Idle.Service {
        id: idle
        shell: QtObject { property var idleConfig: ({screensaver:1,lock:3}) }
    }
    Prelock.Cycle { id: cycle }
    Prelock.CommandQueue { id: commands }
    Window {
        visible:true;width:100;height:100
        TestCase {
            name:"NativeIdleBridge"
            when:idle.stayAwakeStateLoaded
            function test_busy_transport_keeps_next_notification() {
                commands.enqueue(["omarchy","busy","first"]);
                commands.enqueue(["omarchy","busy","second"]);
                verify(commands.busy);tryCompare(commands,"busy",false,2000);
                compare(commands.failures,0);
                console.log("PRELOCK_QUEUE_RESULT "+JSON.stringify({passed:true,busyQueueDrained:true}));
            }
            function test_busy_transport_delivers_real_dismiss_ipc() {
                if(!Quickshell.env("OC_IDLE_IPC_CONFIG"))return;
                idle.startIdleCycle();var token=idle.codexCycle;
                commands.enqueue(["omarchy","busy","before-dismiss"]);
                commands.enqueue(["omarchy","shell","idle","codexScreensaverDismissed",token]);
                verify(idle.idledThisCycle);
                tryVerify(function(){return !idle.idledThisCycle;},1500);
                tryCompare(commands,"busy",false,1500);
                compare(commands.failures,0);verify(!JSON.parse(idle.statusJson()).timers.lock);
                console.log("PRELOCK_IPC_RESULT "+JSON.stringify({passed:true,queuedTokenDelivered:true,actualIdleDeadlineCancelled:true}));
            }
            function test_deadline_survives_failed_show_and_activity() {
                idle.startIdleCycle();var token=idle.codexCycle;
                verify(token.length>0);wait(100);
                idle.handleActiveSignal();
                verify(idle.idledThisCycle);verify(JSON.parse(idle.statusJson()).timers.lock);
                compare(idle.codexEndCycle("stale",false),"stale");
                verify(JSON.parse(idle.statusJson()).timers.lock);
                tryVerify(function(){return !idle.idledThisCycle;},2800);
                verify(!JSON.parse(idle.statusJson()).timers.lock);
                tryVerify(function(){return !JSON.parse(idle.statusJson()).processes.lock;},2000);
                console.log("IDLE_DEADLINE_RESULT "+JSON.stringify({passed:true,syntheticTiming:true,failedShowKeepsDeadline:true,spuriousActivityKeepsDeadline:true,staleDismissIgnored:true}));
            }
            function test_dismiss_cancels_only_current_cycle() {
                idle.startIdleCycle();var token=idle.codexCycle;
                compare(idle.codexEndCycle(token,false),"ok");
                verify(!idle.idledThisCycle);verify(!JSON.parse(idle.statusJson()).timers.lock);
                idle.startIdleCycle();verify(idle.codexCycle!==token);
                compare(idle.codexEndCycle(token,false),"stale");verify(idle.idledThisCycle);
                compare(idle.codexEndCycle(idle.codexCycle,true),"ok");verify(!idle.idledThisCycle);
            }
            function test_prelock_rejects_late_show_after_dismiss_or_lock() {
                var first=String(Date.now())+"-1";
                cycle.hide(first);compare(cycle.show(first),"stale");verify(!cycle.active);
                var second=String(Date.now())+"-2";
                compare(cycle.show(second),"shown");verify(cycle.active);
                cycle.locked=true;verify(!cycle.active);compare(cycle.token,"");
                cycle.locked=false;compare(cycle.show(second),"stale");
                compare(cycle.show("invalid"),"invalid-cycle");verify(!cycle.active);
                console.log("PRELOCK_CYCLE_RESULT "+JSON.stringify({passed:true,lateShowRejected:true,lockDropsSurface:true,secureExercised:false}));
            }
        }
    }
}
