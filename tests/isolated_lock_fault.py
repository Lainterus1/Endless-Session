"""Исполняется только внутри второй bwrap; guest lock без настоящих паролей."""
import json
import os
from pathlib import Path
import subprocess
import time
import fcntl
import sqlite3


def main():
    assert not Path('/parent').exists(), 'parent Wayland must be hidden'
    assert os.environ['WAYLAND_DISPLAY'].startswith('wayland-')
    base=Path('/work')
    assert Path('/proc/1/root/work').is_dir()
    signature=os.environ['HYPRLAND_INSTANCE_SIGNATURE']
    def monitors():
        return json.loads(subprocess.check_output(['hyprctl','-i',signature,'monitors','-j'],text=True,timeout=2))
    def status():
        p=subprocess.run(['qs','ipc','-p','/work/stage/shell.qml','call','lock','status'],capture_output=True,text=True,timeout=2)
        try:return json.loads(p.stdout) if p.returncode==0 else None
        except ValueError:return None
    def policy():
        p=subprocess.run(['qs','ipc','-p','/work/stage/shell.qml','call','fixture','state'],capture_output=True,text=True,timeout=2)
        return json.loads(p.stdout) if p.returncode==0 else {}
    report={'scope':'isolated guest; full generated lock service; synthetic empty Codex database',
            'pam_exercised':False,'physical_dpms_exercised':False,'samples':[]}
    report['allow_session_lock_restore']=json.loads(subprocess.check_output(['hyprctl','-i',signature,'getoption','misc:allow_session_lock_restore','-j'],text=True,timeout=2))
    with (base/'lock.log').open('w') as log:
        proc=subprocess.Popen(['qs','-p','/work/stage/shell.qml','--no-color'],stdout=log,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+12
            secure=False
            while proc.poll() is None and time.monotonic()<deadline:
                snapshot=status()
                outputs=monitors()
                report['samples'].append({'t':time.monotonic(),'status':snapshot,'outputs':outputs})
                if snapshot and snapshot.get('secure'):
                    secure=True
                    if outputs and all(not m['dpmsStatus'] for m in outputs):break
                time.sleep(.2)
            report['secure_observed']=secure
            report['empty_guest_blank']=bool(secure and outputs and all(not m['dpmsStatus'] for m in outputs))
            if report['empty_guest_blank']:
                thread='11111111-1111-4111-8111-111111111111'
                codex=base/'home/.codex'
                writer=(codex/'thread-writer-locks'/f'{thread}.lock').open('w')
                fcntl.flock(writer,fcntl.LOCK_EX)
                path=codex/'sessions'/f'{thread}.jsonl'
                records=[{'type':'session_meta','payload':{'id':thread,'cli_version':'0.159.2'}},
                         {'type':'event_msg','payload':{'type':'task_started','turn_id':'fixture-turn'}},
                         {'type':'event_msg','payload':{'type':'item_completed','thread_id':thread,'item':{'type':'AgentMessage','id':'fixture-message','phase':'commentary','content':[{'type':'Text','text':'Синтетический чат: проверка отказа компонента.'}]}}}]
                path.write_text(''.join(json.dumps(x)+'\n' for x in records))
                with sqlite3.connect(codex/'state_5.sqlite') as db:
                    db.execute('INSERT INTO threads VALUES(?,?,?,0)',(thread,str(path),'Изолированный тест'))
                deadline=time.monotonic()+6
                while proc.poll() is None and time.monotonic()<deadline:
                    snapshot=status();outputs=monitors()
                    if snapshot and snapshot.get('codexChats')==1 and snapshot.get('codexHold') and all(m['dpmsStatus'] for m in outputs):
                        report['active_source_woke_guest']=True
                        report['before_client_death']={'t':time.monotonic(),'status':snapshot,'outputs':outputs}
                        break
                    time.sleep(.2)
            if report.get('active_source_woke_guest') and os.environ.get('OC_GUEST_LOSS')=='1':
                writer.close()
                lost_at=time.monotonic()
                report['writer_released_at']=lost_at
                report['loss_samples']=[]
                deadline=lost_at+315
                premature=False
                while proc.poll() is None and time.monotonic()<deadline:
                    snapshot=status();outputs=monitors();decision=policy();now=time.monotonic()
                    report['loss_samples'].append({'t':now,'status':snapshot,'outputs':outputs,'policy':decision})
                    if not snapshot or not snapshot.get('secure'):
                        report['loss_failure']='secure/status lost';break
                    if not snapshot.get('codexHold') or not all(m['dpmsStatus'] for m in outputs):
                        if now-lost_at<300:premature=True
                        if not snapshot.get('codexHold') and all(not m['dpmsStatus'] for m in outputs):
                            report['loss_blank_after_seconds']=now-lost_at
                            break
                    time.sleep(.5)
                report['loss_retained_full_300_seconds']=not premature and report.get('loss_blank_after_seconds',0)>=300
                report['loss_guest_blank']=report.get('loss_blank_after_seconds',999)<=315
                report['loss_chat_retained']=bool(snapshot and snapshot.get('codexChats')==1)
                report['loss_error_not_completion']=decision.get('reason')=='loss_timeout' and decision.get('all_completed') is False and decision.get('statuses')==['disconnected']
                writer=(codex/'thread-writer-locks'/f'{thread}.lock').open('w')
                fcntl.flock(writer,fcntl.LOCK_EX)
                deadline=time.monotonic()+6
                while proc.poll() is None and time.monotonic()<deadline:
                    snapshot=status();outputs=monitors()
                    if snapshot and snapshot.get('codexHold') and all(m['dpmsStatus'] for m in outputs):
                        report['source_recovery_woke_guest']=True;break
                    time.sleep(.2)
            if secure and proc.poll() is None and report.get('active_source_woke_guest'):
                # Abrupt loss of this lock client only. The compositor is a
                # separate namespace peer, not the user's compositor.
                proc.kill();proc.wait(timeout=3)
                time.sleep(.5)
                subprocess.run(['hyprctl','-i',signature,'dispatch','hl.dsp.dpms({ action = "enable" })'],capture_output=True,timeout=2,check=True)
                outputs=monitors()
                report['after_client_death']=outputs
                report['lock_retained_after_client_death']=bool(outputs and all('LOCK' in m.get('solitaryBlockedBy',[]) for m in outputs))
                proc=subprocess.Popen(['qs','-p','/work/stage/shell.qml','--no-color'],stdout=log,stderr=subprocess.STDOUT)
                deadline=time.monotonic()+6
                while proc.poll() is None and time.monotonic()<deadline:
                    snapshot=status()
                    if snapshot and snapshot.get('secure') and snapshot.get('codexChats')==1:
                        report['native_recovery_secure']=True
                        report['recovered_status']=snapshot
                        report['recovery_via_native_orphan_detection']='lock-stranded: recovering' in (base/'lock.log').read_text()
                        break
                    time.sleep(.2)
        finally:
            if proc.poll() is None:proc.terminate();proc.wait(timeout=3)
            report['client_stopped']=proc.poll() is not None
            report['final_outputs']=monitors()
    report['passed']=all(report.get(k) for k in ['secure_observed','empty_guest_blank','active_source_woke_guest','lock_retained_after_client_death','native_recovery_secure','recovery_via_native_orphan_detection'])
    if os.environ.get('OC_GUEST_LOSS')=='1':
        report['passed']=report['passed'] and all(report.get(k) for k in ['loss_retained_full_300_seconds','loss_guest_blank','loss_chat_retained','loss_error_not_completion','source_recovery_woke_guest'])
    (base/'lock-result.json').write_text(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
