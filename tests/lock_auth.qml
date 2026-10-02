import QtQuick
import QtQuick.Window
import QtTest
import Quickshell
import "plugin"

ShellRoot {
    Window {
        id: window
        width: 1600; height: 1000; visible: true
        LockView {
            id: view
            anchors.fill: parent
            codexActive: true
            loadBackground: false
            onPasswordTextEdited: function(value) { passwordText=value }
            onClearFailureRequested: failureMessage=""
            onSubmitPassword: function(value) { checks.submittedLength=value.length; checks.submittedExact=value==="bc" }
        }
        TestCase {
            id: checks
            name: "NativeLockInput"
            when: window.visible
            property int submittedLength: 0
            property bool submittedExact: false
            function inputIn(item) {
                if (item.echoMode !== undefined && item.passwordMaskDelay !== undefined) return item;
                for (var i=0;i<item.children.length;i++) { var result=inputIn(item.children[i]); if(result) return result; }
                return null;
            }
            function test_first_key_escape_submit_and_disabled_input() {
                window.requestActivate(); view.forcePasswordFocus(); wait(100);
                var input=inputIn(view);
                verify(input !== null); verify(input.activeFocus);
                compare(input.echoMode,TextInput.Password); compare(input.passwordMaskDelay,0);
                verify(!view.codexAuthVisible);
                keyClick(Qt.Key_A);
                verify(view.passwordText === "a"); verify(view.codexAuthVisible);
                keyClick(Qt.Key_Escape);
                compare(view.passwordText.length,0); verify(!view.codexAuthVisible); verify(input.activeFocus);
                keyClick(Qt.Key_B); keyClick(Qt.Key_C);
                compare(view.passwordText.length,2); verify(view.codexAuthVisible);
                keyClick(Qt.Key_Return);
                compare(submittedLength,2); verify(submittedExact); compare(view.passwordText.length,0);
                view.authenticatingPassword=true;
                keyClick(Qt.Key_D); keyClick(Qt.Key_Escape);
                compare(view.passwordText.length,0); verify(view.codexAuthVisible);
                view.authenticatingPassword=false; view.failureMessage="Синтетическая ошибка";
                view.forcePasswordFocus(); keyClick(Qt.Key_E);
                verify(view.passwordText === "e"); compare(view.failureMessage,"");
                keyClick(Qt.Key_Escape);
                console.log("LOCK_AUTH_RESULT "+JSON.stringify({passed:true,syntheticInput:true,firstKeyPreserved:true,masked:true,escapeClears:true,submitExact:submittedExact,disabledInputBlocked:true,pamExercised:false}));
            }
        }
    }
}
