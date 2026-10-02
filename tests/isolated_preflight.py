"""Проверяет отдельный Hyprland в bwrap; не устанавливает плагин и не блокирует host."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys
import sqlite3

INNER = r'''
import json, os, subprocess, time
from pathlib import Path
base=Path('/work')
report={'plugin_started':False,'host_session_state_measured':False,'isolation':'private PID/network/HOME/runtime; only parent Wayland and render nodes shared'}
with (base/'hyprland.log').open('w') as log:
    proc=subprocess.Popen(['Hyprland','-c','/work/hyprland.lua'],stdout=log,stderr=subprocess.STDOUT)
    try:
        deadline=time.monotonic()+15
        while proc.poll() is None and time.monotonic()<deadline:
            instances=list((base/'runtime/hypr').glob('*/.socket.sock'))
            if instances:
                signature=instances[0].parent.name
                env=dict(os.environ,HYPRLAND_INSTANCE_SIGNATURE=signature)
                result=subprocess.run(['hyprctl','-i',signature,'monitors','-j'],env=env,capture_output=True,text=True,timeout=2)
                if result.returncode==0:
                    monitors=json.loads(result.stdout)
                    if monitors:
                        report.update(ready=True,monitors=monitors,private_signature=signature)
                        if (base/'lock-test.py').exists():
                            sockets=[p for p in (base/'runtime').glob('wayland-*') if p.is_socket()]
                            assert len(sockets)==1
                            child_env=dict(env,WAYLAND_DISPLAY=sockets[0].name,QT_QPA_PLATFORM='wayland',QT_QUICK_BACKEND='software',QT_QPA_PLATFORMTHEME='generic',PATH='/work/bin:/usr/bin',USER='fixture')
                            # Hide the parent socket and all render nodes from
                            # the product process. Only guest IPC is reachable.
                            child=['bwrap','--unshare-all','--die-with-parent','--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--symlink','usr/lib','/lib','--symlink','usr/lib','/lib64','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--bind','/work','/work','--ro-bind','/work/etc','/etc','/usr/bin/python3','/work/lock-test.py']
                            result=subprocess.run(child,env=child_env,capture_output=True,text=True,timeout=350 if os.environ.get('OC_GUEST_LOSS')=='1' else 32)
                            report['lock_test']={'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
                        break
            time.sleep(.2)
        else:
            report.update(ready=False,reason='nested compositor unavailable',exit_code=proc.poll())
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
        report['child_stopped']=proc.poll() is not None
(base/'result.json').write_text(json.dumps(report,indent=2))
raise SystemExit(0 if report.get('ready') and report.get('lock_test',{}).get('exit_code',0)==0 else 1)
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--lock-fault',action='store_true',help='Запустить полный lock в дополнительной изоляции и завершить только его процесс.')
    parser.add_argument('--loss-timeout',action='store_true',help='Дополнительно измерить настоящие 300 секунд потери синтетического writer.')
    args=parser.parse_args()
    if args.loss_timeout and not args.lock_fault:parser.error('--loss-timeout требует --lock-fault')
    parent_runtime=Path(os.environ['XDG_RUNTIME_DIR'])
    display=Path(os.environ['WAYLAND_DISPLAY'])
    parent_socket=display if display.is_absolute() else parent_runtime/display
    if not parent_socket.is_socket():raise RuntimeError('parent Wayland socket unavailable')
    args.out.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='codex-idle-isolated-') as tmp:
        base=Path(tmp)
        for name in ('runtime','home','cache'): (base/name).mkdir(mode=0o700)
        (base/'inner.py').write_text(INNER)
        if args.lock_fault:
            sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
            from build_plugin import build
            stage=base/'stage';stage.mkdir()
            package=build(stage/'plugin','lainterus.endless-session',Path('/usr/share/omarchy/shell/plugins/lock'))
            (base/'tested-package.json').write_text(json.dumps(package,indent=2))
            for name in ('Commons','Ui'):shutil.copytree(Path('/usr/share/omarchy/shell')/name,stage/name)
            (stage/'shell.qml').write_text('''import QtQuick
import Quickshell
import Quickshell.Io
import "plugin" as Lock
ShellRoot {
    Lock.Service { id: service }
    Timer { interval: 1000; running: true; onTriggered: if (!service.locked && !service.strandedLock) service.beginLock() }
    IpcHandler {
        target: "fixture"
        function state(): string {
            for (var i=0;i<service.children.length;i++) {
                var child=service.children[i];
                if (child.policy !== undefined && child.hub !== undefined)
                    return JSON.stringify({reason:child.policy.decision.reason, all_completed:child.policy.decision.all_completed,
                        discovery:child.hub.discovery,statuses:child.hub.monitored.map(function(c){return c.status;})});
            }
            return JSON.stringify({error:"context-not-found"});
        }
    }
}
''')
            etc=base/'etc/pam.d';etc.mkdir(parents=True)
            (etc/'omarchy-lock-password').write_text('auth requisite pam_deny.so\n')
            shutil.copytree('/etc/fonts',base/'etc/fonts',symlinks=True)
            codex=base/'home/.codex';codex.mkdir()
            (codex/'sessions').mkdir();(codex/'thread-writer-locks').mkdir()
            with sqlite3.connect(codex/'state_5.sqlite') as db:db.execute('CREATE TABLE threads(id TEXT, rollout_path TEXT, title TEXT, archived INTEGER)')
            bin_dir=base/'bin';bin_dir.mkdir()
            wrappers={'omarchy-system-wake':'exec hyprctl -i "$HYPRLAND_INSTANCE_SIGNATURE" dispatch \'hl.dsp.dpms({ action = "enable" })\'',
                      'omarchy-brightness-display':'exec hyprctl -i "$HYPRLAND_INSTANCE_SIGNATURE" dispatch \'hl.dsp.dpms({ action = "disable" })\'',
                      'omarchy-brightness-keyboard':'exit 0', 'omarchy':'exit 0'}
            for name,body in wrappers.items():
                p=bin_dir/name
                audit = "printf '%s %s %s\\n' \"$(date +%s.%N)\" \"$0\" \"$*\" >> /work/helper-calls.log\n"
                p.write_text('#!/bin/sh\n'+audit+body+'\n');p.chmod(0o700)
            shutil.copyfile('/usr/share/omarchy/bin/omarchy-hyprland-session-locked',bin_dir/'omarchy-hyprland-session-locked')
            (bin_dir/'omarchy-hyprland-session-locked').chmod(0o700)
            shutil.copyfile(Path(__file__).with_name('isolated_lock_fault.py'),base/'lock-test.py')
        (base/'hyprland.lua').write_text('hl.monitor({output="", mode="800x600@60", position="auto", scale=1})\nhl.config({debug={enable_stdout_logs=true}, misc={disable_hyprland_logo=true, disable_splash_rendering=true, allow_session_lock_restore=true}, xwayland={enabled=false}})\n')
        cmd=['bwrap','--unshare-all','--die-with-parent','--new-session','--clearenv',
             '--ro-bind','/usr','/usr','--symlink','usr/bin','/bin',
             '--symlink','usr/lib','/lib','--symlink','usr/lib','/lib64',
             '--proc','/proc','--dev','/dev','--tmpfs','/tmp','--ro-bind','/sys','/sys',
             '--bind',str(base),'/work','--ro-bind',str(parent_socket),'/parent/socket',
             '--setenv','PATH','/usr/bin','--setenv','HOME','/work/home',
             '--setenv','XDG_RUNTIME_DIR','/work/runtime','--setenv','XDG_CACHE_HOME','/work/cache',
             '--setenv','WAYLAND_DISPLAY','/parent/socket',
             '--setenv','XDG_SESSION_TYPE','wayland','--setenv','HYPRLAND_NO_SD_NOTIFY','1',
             '--setenv','HYPRLAND_NO_CRASHREPORTER','1']
        # Only render nodes: no KMS cards, host runtime directory, input devices,
        # system/session D-Bus, user HOME or host process namespace is exposed.
        for node in sorted(Path('/dev/dri').glob('renderD*')):
            cmd+=['--dev-bind',str(node),str(node)]
        if args.loss_timeout:cmd+=['--setenv','OC_GUEST_LOSS','1']
        cmd+=['/usr/bin/python3','/work/inner.py']
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=375 if args.loss_timeout else 50 if args.lock_fault else 25)
        (args.out/'launcher.json').write_text(json.dumps({'command':cmd,'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr},indent=2))
        for name in ('hyprland.log','result.json','hyprland.lua','inner.py','lock.log','lock-result.json','tested-package.json','helper-calls.log','lock-test.py'):
            if (base/name).exists():shutil.copyfile(base/name,args.out/name)
        shutil.copyfile(__file__,args.out/'isolated_preflight.py')
        print(json.dumps({'exit_code':result.returncode,'report':str(args.out/'result.json')}))
        return result.returncode


if __name__=='__main__':raise SystemExit(main())
