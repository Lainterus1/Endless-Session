"""Проверка новых событий выбранного чата без сохранения реального текста."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import time

from source_probe import Observer, SessionState


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def historical_question_check(path, thread_id):
    state = SessionState(thread_id)
    submitted = {}
    accepted_receipts = 0
    receipt_remained_pending = 0
    resolved = set()
    for line in path.open("rb"):
        try: record = json.loads(line)
        except (ValueError, UnicodeError): continue
        before = set(state.pending)
        if not isinstance(record, dict):
            continue
        payload = record.get("payload")
        state.accept(record)
        if not isinstance(payload, dict):
            continue
        for call_id in set(state.pending) - before:
            submitted[call_id] = len(state.pending[call_id])
        if record.get("type") == "response_item" and payload.get("type") == "function_call_output" and payload.get("call_id") in state.pending:
            try: result = json.loads(payload.get("output", ""))
            except (ValueError, TypeError): result = {}
            if isinstance(result, dict) and result.get("accepted") is True:
                accepted_receipts += 1
                receipt_remained_pending += int(payload["call_id"] in state.pending)
        resolved.update(before - set(state.pending))
    return {"request_groups": len(submitted), "question_counts": sorted(submitted.values()),
            "accepted_receipts": accepted_receipts, "receipts_kept_pending": receipt_remained_pending,
            "resolved_groups": len(resolved), "pending_at_end": sum(map(len, state.pending.values())),
            "method": "replay_of_actual_public_question_requests_and_replies"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thread", required=True)
    parser.add_argument("--marker", required=True)
    parser.add_argument("--seconds", type=float, default=25)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    inputs = [Path("source_probe.py"), Path("verify_live_source.py")]
    input_hashes = {str(path): digest(path) for path in inputs}
    observer = Observer(Path.home() / ".codex", args.thread)
    started = datetime.now(timezone.utc).isoformat()
    before = observer.poll()
    initial_ids = set(observer.model.items)
    deadline = time.monotonic() + args.seconds
    print(json.dumps({"watch_ready": True, "status": before["status"], "public_items": before["public_items"]}), flush=True)
    found_marker = False
    fresh = []
    while time.monotonic() < deadline:
        after = observer.poll()
        fresh = [item for key, item in observer.model.items.items() if key not in initial_ids]
        found_marker = any(item["type"] == "message" and args.marker in item.get("text", "") for item in fresh)
        if found_marker and any(item["type"] == "command" for item in fresh): break
        time.sleep(.25)
    history = historical_question_check(observer.path, args.thread) if observer.path else {}
    checks = {
        "live_writer_observed": before["writer_alive"] is True and after["writer_alive"] is True,
        "current_turn_remains_working": before["status"] == after["status"] == "working",
        "actual_new_message_observed": found_marker,
        "actual_new_command_observed": any(item["type"] == "command" for item in fresh),
        "no_parser_error": after["invalid_records"] == 0 and after["source_error"] is None,
        "actual_async_receipts_are_not_answers": history.get("accepted_receipts", 0) > 0 and history.get("accepted_receipts") == history.get("receipts_kept_pending"),
        "actual_question_groups_resolved": history.get("request_groups", 0) > 0 and history.get("resolved_groups") == history.get("request_groups"),
        "inputs_unchanged": input_hashes == {str(path): digest(path) for path in inputs},
    }
    report = {"command": "python3 verify_live_source.py --thread <current-chat> --marker <public-commentary-marker> --seconds " + str(args.seconds) + " --out " + shlex.quote(str(args.out)),
              "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
              "thread_id": args.thread, "codex_cli_version": after["version"], "status": after["status"],
              "initial_public_items": before["public_items"], "final_public_items": after["public_items"],
              "new_public_item_types": dict(Counter(item["type"] for item in fresh)),
              "checks": checks, "question_history": history, "input_sha256": input_hashes,
              "runtime_approval_known": after["runtime_approval_known"],
              "limits": ["single_selected_chat", "typed_local_rollout_0.159.2", "approval_wait_not_observed", "no_lock_screen_activation"],
              "passed": all(checks.values())}
    with args.out.open("x") as target:
        json.dump(report, target, indent=2, ensure_ascii=False)
        target.write("\n")
    print(json.dumps({"passed": report["passed"], "checks": checks, "new_public_item_types": report["new_public_item_types"], "report": str(args.out)}), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__": raise SystemExit(main())
