"""Компилирует полные QML-типы на Wayland без создания Service/окна/PAM."""
import argparse,hashlib,json,os,shutil,subprocess,tempfile
from datetime import datetime,timezone
from pathlib import Path
from build_plugin import build
from check_lock_local import hashes
ROOT=Path(__file__).resolve().parent
ENTRY='''import QtQuick
import Quickshell
import "plugin" as Lock
import "plugin/companion" as Idle
ShellRoot {
    id: root
    property var components: []
    property bool finished: false
    function check() {
        if(finished)return;
        if(components.some(function(c){return c.status===Component.Loading;}))return;
        finished=true;
        console.log("NATIVE_COMPILE_RESULT "+JSON.stringify({passed:components.every(function(c){return c.status===Component.Ready;}),statuses:components.map(function(c){return c.status;}),errors:components.map(function(c){return c.errorString();}),instantiated:false,secureExercised:false,pamExercised:false}));
        Qt.quit();
    }
    Component.onCompleted: {
        components=[Qt.createComponent("plugin/Service.qml"),Qt.createComponent("plugin/companion/Service.qml")];
        components.forEach(function(c){c.statusChanged.connect(root.check);});check();
    }
    Timer { interval:5000;running:true;onTriggered:{console.log("NATIVE_COMPILE_TIMEOUT");Qt.quit();} }
}
'''
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path);args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=False);before=hashes();started=datetime.now(timezone.utc).isoformat();records=[]
    with tempfile.TemporaryDirectory(prefix='oc-compile-') as tmp:
        base=Path(tmp);package=build(base/'plugin','lainterus.endless-session',Path('/usr/share/omarchy/shell/plugins/lock'))
        for name in ('Commons','Ui'):shutil.copytree(Path('/usr/share/omarchy/shell')/name,base/name)
        (base/'shell.qml').write_text(ENTRY)
        for command in [['omarchy','plugin','validate',str(base/'plugin')],['omarchy','plugin','validate',str(base/'plugin/companion')],['qs','-p',str(base/'shell.qml'),'--no-color']]:
            result=subprocess.run(command,env=dict(os.environ,QT_QPA_PLATFORM='wayland'),capture_output=True,text=True,timeout=15)
            records.append(dict(command=command,exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr))
        compile_result=None
        for line in records[-1]['stdout'].splitlines():
            if 'NATIVE_COMPILE_RESULT ' in line:compile_result=json.loads(line.split('NATIVE_COMPILE_RESULT ',1)[1])
    passed=all(r['exit_code']==0 for r in records) and bool(compile_result and compile_result['passed']) and before==hashes()
    report=dict(started_at=started,finished_at=datetime.now(timezone.utc).isoformat(),input_sha256=before,inputs_unchanged=before==hashes(),package_build_id=package['build_id'],results=records,compilation=compile_result,passed=passed,system_config_changed=False)
    (args.out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'passed':passed,'compilation':compile_result,'build_id':package['build_id']}));return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
