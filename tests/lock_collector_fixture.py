"""Долгоживущий синтетический collector для проверки stop после unlock."""
import json
import os
import signal
import sys
import time
from pathlib import Path

marker = Path(sys.argv[1]); marker.write_text(str(os.getpid()))
def stop(*args):
    marker.with_suffix(".stopped").write_text(str(time.monotonic()))
    raise SystemExit(0)
signal.signal(signal.SIGTERM, stop)
sequence = 0
while True:
    sequence += 1
    frame = dict(schema_version=1, sequence=sequence, discovery="ready", unknown_count=0,
        theme=dict(foreground="#cacccc",background="#101315",accent="#cacccc",fontFamily="monospace"),
        chats=[dict(thread_id="11111111-1111-4111-8111-111111111111",name="Синтетический lock",source_epoch=0,status="working",pending_questions=0,reset=sequence==1,
        items=[dict(id="fixture",type="message",phase="commentary",timestamp=None,text="Проверка жизненного цикла компонента.")] if sequence==1 else [])])
    print(json.dumps(frame),flush=True); time.sleep(0.1)
