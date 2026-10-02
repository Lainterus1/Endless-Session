"""Контролируемая замена внешних команд, только для изолированного Qt runtime."""
import json,os,sys,time,subprocess
from pathlib import Path
args=sys.argv[1:]
if args and args[0]=='busy':time.sleep(0.15)
with Path(os.environ['OC_IDLE_CALLS']).open('a') as out:out.write(json.dumps(args)+'\n')
if args[:2]==['shell','idle'] and os.environ.get('OC_IDLE_IPC_CONFIG'):
    raise SystemExit(subprocess.run(['qs','-p',os.environ['OC_IDLE_IPC_CONFIG'],'ipc','call','idle',*args[2:]],timeout=3).returncode)
if 'showCodexScreensaver' in args:raise SystemExit(1)
print('ok')
