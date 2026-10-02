"""Локальная проверка установки и настоящего LockView; без системной блокировки."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from build_plugin import build

ROOT=Path(__file__).resolve().parent

def hashes():
    paths=list(ROOT.glob('*.py'))+list(ROOT.glob('*.qml'))+[ROOT/'lock-compatibility.json',ROOT/'idle-compatibility.json']
    paths += [p for folder in ('ui','prelock','tests') for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--ipc',action='store_true',help='Проверить отдельный IPC собственного тестового qs; нужен доступ к локальным сокетам.');args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=False);before=hashes();started=datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix='oc-lock-') as tmp:
        base=Path(tmp);runtime=base/'runtime';runtime.mkdir(mode=0o700);stage=base/'config';stage.mkdir()
        package=build(stage/'plugin','fixture.codex-idle',Path('/usr/share/omarchy/shell/plugins/lock'))
        for name in ('Commons','Ui'):shutil.copytree(Path('/usr/share/omarchy/shell')/name,stage/name)
        shutil.copyfile(ROOT/'tests/lock_runtime.qml',stage/'shell.qml')
        shutil.copyfile(ROOT/'tests/lock_auth.qml',stage/'auth.qml')
        shutil.copyfile(ROOT/'tests/idle_runtime.qml',stage/'idle.qml')
        env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_QPA_PLATFORMTHEME='generic',QT_QUICK_BACKEND='software',XDG_RUNTIME_DIR=str(runtime),XDG_CACHE_HOME=str(runtime),OC_IDLE_FIXTURE=str(ROOT/'tests/lock_collector_fixture.py'),OC_IDLE_PID_FILE=str(base/'collector.pid'),OC_IDLE_CAPTURE=str((args.out/'lock-view.png').resolve()))
        results=[]
        for command in [['python3','-m','unittest','-v','test_install_plugin'],['qs','-p',str(stage/'shell.qml'),'--no-color'],['qs','-p',str(stage/'auth.qml'),'--no-color']]:
            result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=30)
            results.append(dict(command=command,exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr))
        lifecycle=None
        for line in results[1]['stdout'].splitlines():
            if 'LOCK_RUNTIME_RESULT ' in line:lifecycle=json.loads(line.split('LOCK_RUNTIME_RESULT ',1)[1])
        # Exercise the actual generated idle service, with all external commands
        # confined to a fake HOME and explicit command sinks. No system idle/DPMS.
        stub=base/'bin';stub.mkdir();home=base/'home';home.mkdir()
        sink=ROOT/'tests/idle_sink.py';calls=base/'idle-calls.jsonl'
        (stub/'omarchy').write_text('#!/bin/sh\nexec python3 "'+str(sink)+'" "$@"\n');(stub/'omarchy').chmod(0o700)
        bash_env=base/'bash-env'
        bash_env.write_text('omarchy-system-lock() { python3 "'+str(sink)+'" lock; }\nomarchy-system-wake() { python3 "'+str(sink)+'" wake; }\n')
        idle_env=dict(env,HOME=str(home),PATH=str(stub)+os.pathsep+os.environ['PATH'],BASH_ENV=str(bash_env),OC_IDLE_CALLS=str(calls))
        idle_env.pop('WAYLAND_DISPLAY',None);idle_env.pop('HYPRLAND_INSTANCE_SIGNATURE',None)
        if args.ipc:idle_env['OC_IDLE_IPC_CONFIG']=str(stage/'idle.qml')
        idle_command=['qs','-p',str(stage/'idle.qml'),'--no-color']
        idle_result=subprocess.run(idle_command,env=idle_env,capture_output=True,text=True,timeout=20)
        results.append(dict(command=idle_command,exit_code=idle_result.returncode,stdout=idle_result.stdout,stderr=idle_result.stderr))
        idle_calls=[json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []
        idle_passed=all(marker in idle_result.stdout for marker in ('IDLE_DEADLINE_RESULT','PRELOCK_CYCLE_RESULT','PRELOCK_QUEUE_RESULT')) and ['lock'] in idle_calls and [call for call in idle_calls if call in [['busy','first'],['busy','second']]]==[['busy','first'],['busy','second']]
        ipc_passed=args.ipc and 'PRELOCK_IPC_RESULT ' in idle_result.stdout and any(call[:3]==['shell','idle','codexScreensaverDismissed'] for call in idle_calls)
        if args.ipc:idle_passed=idle_passed and ipc_passed
        auth=None
        for line in results[2]['stdout'].splitlines():
            if 'LOCK_AUTH_RESULT ' in line:auth=json.loads(line.split('LOCK_AUTH_RESULT ',1)[1])
        pid=int((base/'collector.pid').read_text()) if (base/'collector.pid').exists() else 0
        stopped=pid>0 and bool(lifecycle) and all(not Path('/proc',str(value)).exists() for value in lifecycle.get('pids',[pid]))
        after=hashes()
        report=dict(started_at=started,finished_at=datetime.now(timezone.utc).isoformat(),input_sha256=before,inputs_unchanged=before==after,package_build_id=package['build_id'],results=results,lifecycle=lifecycle,collector_process_gone=stopped,secure_exercised=False,pam_exercised=False,system_config_changed=False)
        report['auth']=auth
        report['idle']={'passed':idle_passed,'calls':idle_calls,'real_idle_exercised':False,'isolated_ipc_exercised':ipc_passed}
        report['passed']=all(r['exit_code']==0 for r in results) and bool(lifecycle and lifecycle['passed']) and bool(auth and auth['passed']) and idle_passed and stopped and before==after
        (args.out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({k:report[k] for k in ('passed','lifecycle','collector_process_gone','package_build_id')}));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
