"""Синтетический процесс: один кадр и завершение; не читает Codex."""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from source_probe import SessionState
from stream_context import Stream
from test_source_probe import THREAD, meta, lifecycle, message, public, question, reply

epoch = int(sys.argv[1])
model = SessionState(THREAD)
records = [meta(), lifecycle("task_started"), message("Эпоха " + str(epoch), item_id=str(epoch))]
if epoch == 0:
    records += [message("Готово <b>полностью</b>", item_id="final", phase="final_answer"),
        public({"type":"CommandExecution", "id":"cmd", "command":["echo", "fixture"], "status":"completed", "aggregated_output":"fixture", "exit_code":0}),
        public({"type":"FileChange", "id":"patch", "status":"completed", "changes":{"example.py":{"type":"update", "unified_diff":"- old\n+ new"}}}),
        question(count=1), reply(indices=(0,))]
for record in records: model.accept(record)
assert model.invalid_records == 0
print(json.dumps(Stream().frame([{"thread_id":THREAD, "name":"Синтетический процесс", "source_epoch":epoch,
    "status":"working", "pending_questions":0, "items":list(model.items.values())}])), flush=True)
time.sleep(0.15)
