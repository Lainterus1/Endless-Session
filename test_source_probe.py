from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from source_probe import Observer, SessionState, resolve_thread, writer_alive

THREAD = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


def record(kind, payload):
    return {"timestamp": "2026-10-01T17:00:00Z", "type": kind, "payload": payload}


def meta(version="0.159.2", thread=THREAD):
    return record("session_meta", {"id": thread, "cli_version": version})


def lifecycle(kind, turn="turn-1"):
    return record("event_msg", {"type": kind, "turn_id": turn})


def public(item, thread=THREAD):
    return record("event_msg", {"type": "item_completed", "thread_id": thread, "item": item})


def message(text="Проверю обработчик простоя.", item_id="message-1", phase="commentary"):
    return public({"type": "AgentMessage", "id": item_id, "phase": phase, "content": [{"type": "Text", "text": text}]})


def question(call="call-1", count=2, tool="request_user_input_async"):
    return record("response_item", {"type": "function_call", "name": tool, "call_id": call,
        "arguments": json.dumps({"questions": [{"id": f"q{i}", "title": f"Вопрос {i}", "options": ["A", "B"]} for i in range(count)]})})


def question_output(data, call="call-1"):
    return record("response_item", {"type": "function_call_output", "call_id": call, "output": json.dumps(data)})


def reply(indices=(0, 1), call="call-1"):
    data = [{"questionItemId": json.dumps(["request_user_input_async", call, i]), "answer": f"Ответ {i}"} for i in indices]
    text = "<send_user_message_question_reply>\n" + json.dumps(data, ensure_ascii=False) + "\n</send_user_message_question_reply>"
    return record("response_item", {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]})


class StateTests(unittest.TestCase):
    def setUp(self):
        self.state = SessionState(THREAD)
        self.state.accept(meta())
        self.state.accept(lifecycle("task_started"))

    def test_lifecycle_requires_matching_completion(self):
        self.assertEqual(self.state.state(True), "working")
        self.state.accept(lifecycle("task_complete", "older-turn"))
        self.assertEqual(self.state.state(True), "working")
        self.state.accept(lifecycle("task_complete"))
        self.assertEqual(self.state.state(True), "idle")
        self.state.accept(lifecycle("task_started", "turn-2"))
        self.state.accept(lifecycle("task_complete", "turn-1"))
        self.assertEqual(self.state.state(True), "working")

    def test_idle_requires_explicit_lifecycle(self):
        state = SessionState(THREAD)
        state.accept(meta())
        self.assertEqual(state.state(True), "unknown")
        state.accept(lifecycle("task_complete"))
        self.assertEqual(state.state(True), "unknown")

    def test_unseen_turn_completion_after_idle_is_unknown(self):
        self.state.accept(lifecycle("task_complete"))
        self.assertEqual(self.state.state(True), "idle")
        self.state.accept(lifecycle("task_complete", "unseen-turn"))
        self.assertEqual(self.state.state(True), "unknown")

    def test_duplicate_completion_keeps_confirmed_idle(self):
        self.state.accept(lifecycle("task_complete"))
        self.state.accept(lifecycle("task_complete"))
        self.assertEqual(self.state.state(True), "idle")
        self.assertFalse(self.state.uncertain)

    def test_late_old_completion_cannot_end_new_active_turn(self):
        self.state.accept(lifecycle("task_complete"))
        self.state.accept(lifecycle("task_started", "turn-2"))
        self.state.accept(lifecycle("task_complete", "turn-1"))
        self.assertEqual(self.state.state(True), "working")
        self.assertFalse(self.state.uncertain)
        self.state.accept(lifecycle("task_complete", "turn-2"))
        self.assertEqual(self.state.state(True), "idle")

    def test_async_acceptance_is_not_an_answer(self):
        self.state.accept(question())
        self.state.accept(question_output({"accepted": True}))
        self.assertEqual(self.state.state(True), "waiting_input")
        self.assertEqual(len(self.state.pending["call-1"]), 2)
        self.state.accept(lifecycle("task_complete"))
        self.assertEqual(self.state.state(True), "waiting_input")

    def test_partial_answer_keeps_remaining_question(self):
        self.state.accept(question())
        self.state.accept(reply((0,)))
        self.assertEqual(self.state.state(True), "waiting_input")
        self.assertEqual(set(self.state.pending["call-1"]), {1})
        self.state.accept(reply((1,)))
        self.assertEqual(self.state.state(True), "working")
        self.assertFalse(self.state.pending)

    def test_unrelated_reply_does_not_resolve_request(self):
        self.state.accept(question())
        self.state.accept(reply((0, 1), call="unrelated"))
        self.assertEqual(len(self.state.pending["call-1"]), 2)

    def test_duplicate_reply_does_not_duplicate_public_item(self):
        self.state.accept(question())
        self.state.accept(reply())
        count = len(self.state.items)
        self.state.accept(reply())
        self.assertEqual(len(self.state.items), count)

    def test_sync_answer_resolves_only_matching_question_ids(self):
        self.state.accept(question(tool="request_user_input"))
        self.state.accept(question_output({"answers": {"q0": {"answers": ["A"]}}}))
        self.assertEqual(len(self.state.pending["call-1"]), 1)
        self.state.accept(question_output({"answers": {"q1": {"answers": ["B"]}}}))
        self.assertEqual(self.state.state(True), "working")

    def test_cancelled_question_does_not_stay_pending(self):
        self.state.accept(question())
        self.state.accept(question_output({"status": "cancelled"}))
        self.assertEqual(self.state.state(True), "working")

    def test_lost_writer_does_not_mean_completed(self):
        self.state.accept(question())
        self.assertEqual(self.state.state(False), "disconnected")
        self.assertEqual(self.state.state(None), "unknown")
        self.assertTrue(self.state.pending)

    def test_completed_turn_pending_survives_lost_and_unknown_writer(self):
        self.state.accept(question())
        self.state.accept(lifecycle("task_complete"))
        self.assertEqual(self.state.state(True), "waiting_input")
        pending = json.dumps(self.state.pending, sort_keys=True)
        items = json.dumps(self.state.items, sort_keys=True)
        for alive, expected in ((False, "disconnected"), (None, "unknown")):
            with self.subTest(writer_alive=alive):
                self.assertEqual(self.state.state(alive), expected)
                self.assertEqual(json.dumps(self.state.pending, sort_keys=True), pending)
                self.assertEqual(json.dumps(self.state.items, sort_keys=True), items)

    def test_corrupt_record_overrides_completed_turn_pending(self):
        self.state.accept(question())
        self.state.accept(lifecycle("task_complete"))
        self.assertEqual(self.state.state(True), "waiting_input")
        pending = json.dumps(self.state.pending, sort_keys=True)
        items = json.dumps(self.state.items, sort_keys=True)
        before_invalid = self.state.invalid_records
        self.state.accept(record("event_msg", None))
        self.assertEqual(self.state.state(True), "unknown")
        self.assertEqual(self.state.invalid_records, before_invalid + 1)
        self.assertEqual(json.dumps(self.state.pending, sort_keys=True), pending)
        self.assertEqual(json.dumps(self.state.items, sort_keys=True), items)

    def test_unknown_version_has_no_public_projection(self):
        state = SessionState(THREAD)
        state.accept(meta("99.1.0"))
        state.accept(lifecycle("task_started"))
        state.accept(message())
        self.assertEqual(state.state(True), "unknown")
        self.assertFalse(state.items)

    def test_wrong_thread_items_are_rejected(self):
        self.state.accept(public({"type": "AgentMessage", "id": "foreign", "phase": "commentary", "content": [{"type": "Text", "text": "foreign text"}]}, thread=OTHER))
        self.assertFalse(self.state.items)
        self.assertEqual(self.state.state(True), "unknown")

    def test_second_header_from_another_thread_stops_projection(self):
        self.state.accept(message("Свой контекст"))
        self.state.accept(meta(thread=OTHER))
        self.state.accept(message("Чужой контекст", item_id="foreign"))
        self.assertEqual(len(self.state.items), 1)
        self.assertEqual(self.state.state(True), "unknown")

    def test_foreign_question_claims_in_wrapper_and_payload_are_rejected(self):
        for layer in ("record", "payload"):
            with self.subTest(layer=layer):
                state = SessionState(THREAD)
                state.accept(meta())
                entry = question()
                (entry if layer == "record" else entry["payload"])["thread_id"] = OTHER
                state.accept(entry)
                self.assertFalse(state.items)
                self.assertFalse(state.pending)
                self.assertEqual(state.state(True), "unknown")

    def test_foreign_answers_and_receipts_cannot_resolve_local_questions(self):
        nested_reply = public({"type": "UserMessage", "id": "foreign", "thread_id": OTHER,
                               "content": reply()["payload"]["content"]})
        foreign_reply = reply()
        foreign_reply["payload"]["thread_id"] = OTHER
        foreign_result = question_output({"answers": {"q0": {}, "q1": {}}})
        foreign_result["payload"]["thread_id"] = OTHER
        for entry in (nested_reply, foreign_reply, foreign_result):
            with self.subTest(kind=entry["payload"]["type"]):
                state = SessionState(THREAD)
                state.accept(meta())
                state.accept(question())
                state.accept(entry)
                self.assertEqual(len(state.pending["call-1"]), 2)
                self.assertEqual(len(state.items), 1)
                self.assertEqual(state.state(True), "unknown")

    def test_nested_foreign_public_item_is_rejected(self):
        entry = message()
        entry["payload"]["item"]["thread_id"] = OTHER
        self.state.accept(entry)
        self.assertFalse(self.state.items)
        self.assertEqual(self.state.state(True), "unknown")

    def test_malformed_envelope_after_completion_is_unknown(self):
        entries = [record("event_msg", None), record("event_msg", []), record("event_msg", {}),
                   record("response_item", {"type": []}),
                   record("event_msg", {"type": "item_completed", "item": None}),
                   public({}), record("new_record_kind", {})]
        for entry in entries:
            with self.subTest(entry=entry):
                state = SessionState(THREAD)
                state.accept(meta())
                state.accept(lifecycle("task_started"))
                state.accept(lifecycle("task_complete"))
                self.assertEqual(state.state(True), "idle")
                state.accept(entry)
                self.assertEqual(state.state(True), "unknown")

    def test_structured_metadata_in_scalar_fields_never_projects(self):
        private = {"unexpected_metadata": "PRIVATE_MARKER"}
        command = {"type": "CommandExecution", "id": "cmd", "command": ["npm", "test"],
                   "status": "completed", "cwd": "/example", "exit_code": 0, "aggregated_output": "ok"}
        entries = []
        stamped = message()
        stamped["timestamp"] = private
        entries.append(stamped)
        for key in ("cwd", "status", "exit_code", "aggregated_output"):
            entries.append(public({**command, key: private}))
        entries.append(public({**command, "exit_code": True}))
        entries.append(public({**command, "status": "new_status"}))
        entries.append(public({"type": "FileChange", "id": "patch", "status": private,
                               "changes": {"/example": {"type": "delete"}}}))
        bad_question = question()
        data = json.loads(bad_question["payload"]["arguments"])
        for entry in data["questions"]:
            entry["id"] = private
        bad_question["payload"]["arguments"] = json.dumps(data)
        entries.append(bad_question)
        for entry in entries:
            with self.subTest(kind=entry["payload"]["type"]):
                state = SessionState(THREAD)
                state.accept(meta())
                state.accept(lifecycle("task_started"))
                state.accept(entry)
                self.assertFalse(state.items)
                self.assertFalse(state.pending)
                self.assertEqual(state.state(True), "unknown")
                self.assertNotIn("PRIVATE_MARKER", json.dumps(list(state.items.values())))

    def test_structured_version_is_unknown_without_crashing(self):
        state = SessionState(THREAD)
        state.accept(meta({"unexpected_metadata": "PRIVATE_MARKER"}))
        state.accept(message())
        self.assertEqual(state.state(True), "unknown")
        self.assertFalse(state.items)

    def test_file_change_keeps_diff_and_excludes_unknown_metadata(self):
        self.state.accept(public({"type": "FileChange", "id": "patch", "status": "completed", "changes": {
            "/example/main.py": {"type": "update", "unified_diff": "- old\n+ new", "move_path": None, "private_extra": "PRIVATE_MARKER"}
        }}))
        item = self.state.items["patch"]
        self.assertEqual(item["changes"]["/example/main.py"]["unified_diff"], "- old\n+ new")
        self.assertNotIn("PRIVATE_MARKER", json.dumps(item))

    def test_private_reasoning_prompts_and_arbitrary_outputs_are_excluded(self):
        secret = "PRIVATE_REASONING_MARKER"
        for entry in [
            public({"type": "Reasoning", "id": "reason", "summary_text": [secret], "raw_content": [secret]}),
            record("response_item", {"type": "reasoning", "content": secret}),
            record("response_item", {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": secret}]}),
            record("response_item", {"type": "message", "role": "system", "content": [{"type": "input_text", "text": secret}]}),
            record("response_item", {"type": "custom_tool_call_output", "call_id": "opaque", "output": secret}),
            public({"type": "McpToolCall", "id": "opaque", "result": {"data": secret}}),
            message(secret, phase="analysis"),
        ]:
            self.state.accept(entry)
        self.state.accept(message())
        self.assertNotIn(secret, json.dumps(list(self.state.items.values())))
        self.assertEqual(len(self.state.items), 1)

    def test_message_keeps_full_unicode_and_long_paragraphs(self):
        text = ("Длинный абзац без обрыва предложения. " * 1000) + "\n\nПоследняя фраза."
        self.state.accept(message(text))
        self.assertEqual(self.state.items["message-1"]["text"], text)

    def test_command_result_keeps_public_output_and_exit_code(self):
        self.state.accept(public({"type": "CommandExecution", "id": "cmd", "command": ["/bin/bash", "-lc", "npm test"], "cwd": "/example", "status": "failed", "aggregated_output": "FAIL\nОшибка проверки", "exit_code": 1, "private_extra": "not projected"}))
        item = self.state.items["cmd"]
        self.assertEqual(item["command"], "npm test")
        self.assertEqual(item["exit_code"], 1)
        self.assertEqual(item["output"], "FAIL\nОшибка проверки")
        self.assertNotIn("private_extra", item)

    def test_updated_item_is_replaced_without_duplication(self):
        self.state.accept(message("Первая фраза."))
        self.state.accept(message("Первая фраза. Вторая фраза."))
        self.assertEqual(len(self.state.items), 1)
        self.assertEqual(self.state.items["message-1"]["text"], "Первая фраза. Вторая фраза.")

    def test_malformed_question_is_unknown(self):
        self.state.accept(record("response_item", {"type": "function_call", "name": "request_user_input_async", "call_id": "bad", "arguments": '{"questions": null}'}))
        self.assertEqual(self.state.state(True), "unknown")


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        (self.home / "sessions").mkdir()
        (self.home / "thread-writer-locks").mkdir()
        self.path = self.home / "sessions" / "rollout.jsonl"
        self.path.write_bytes(b"")
        self.append(meta(), lifecycle("task_started"))
        database = self.home / "state_5.sqlite"
        connection = sqlite3.connect(database)
        connection.execute("CREATE TABLE threads (id TEXT PRIMARY KEY, rollout_path TEXT, title TEXT, archived INTEGER)")
        connection.execute("INSERT INTO threads VALUES (?,?,?,?)", (THREAD, str(self.path), "Тестовый чат", 0))
        connection.commit(); connection.close()
        self.lock = self.home / "thread-writer-locks" / (THREAD + ".lock")
        self.lock.touch()
        self.writer = self.lock.open("rb")
        fcntl.flock(self.writer, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.addCleanup(self.writer.close)
        self.observer = Observer(self.home, THREAD)

    def append(self, *records):
        with self.path.open("ab") as stream:
            for entry in records:
                stream.write(json.dumps(entry, ensure_ascii=False).encode() + b"\n")

    def test_live_append_is_incremental_and_never_changes_database(self):
        database = self.home / "state_5.sqlite"
        before = hashlib.sha256(database.read_bytes()).hexdigest()
        first = self.observer.poll()
        self.assertEqual(first["status"], "working")
        self.append(message())
        second = self.observer.poll()
        self.assertEqual(second["public_items"], 1)
        self.assertEqual(second["observed_records"], first["observed_records"] + 1)
        self.assertEqual(self.observer.poll()["revision"], second["revision"])
        self.assertEqual(hashlib.sha256(database.read_bytes()).hexdigest(), before)

    def test_partial_unicode_record_waits_for_newline(self):
        self.observer.poll()
        encoded = json.dumps(message("Русский текст"), ensure_ascii=False).encode()
        split = encoded.index("Русский".encode()) + 1
        with self.path.open("ab") as stream: stream.write(encoded[:split])
        partial = self.observer.poll()
        self.assertEqual(partial["public_items"], 0)
        self.assertEqual(partial["invalid_records"], 0)
        with self.path.open("ab") as stream: stream.write(encoded[split:] + b"\n")
        complete = self.observer.poll()
        self.assertEqual(complete["items"][0]["text"], "Русский текст")
        self.assertEqual(complete["partial_record_bytes"], 0)

    def test_partial_new_turn_prevents_idle_until_record_is_complete(self):
        self.append(lifecycle("task_complete"))
        self.assertEqual(self.observer.poll()["status"], "idle")
        encoded = json.dumps(lifecycle("task_started", "turn-2")).encode()
        with self.path.open("ab") as stream: stream.write(encoded[:45])
        partial = self.observer.poll()
        self.assertEqual(partial["status"], "unknown")
        self.assertEqual(partial["invalid_records"], 0)
        with self.path.open("ab") as stream: stream.write(encoded[45:] + b"\n")
        self.assertEqual(self.observer.poll()["status"], "working")

    def test_completed_passive_tail_restores_confirmed_idle(self):
        self.append(lifecycle("task_complete"))
        self.assertEqual(self.observer.poll()["status"], "idle")
        encoded = json.dumps(record("event_msg", {"type": "token_count"})).encode()
        with self.path.open("ab") as stream: stream.write(encoded[:45])
        self.assertEqual(self.observer.poll()["status"], "unknown")
        with self.path.open("ab") as stream: stream.write(encoded[45:] + b"\n")
        self.assertEqual(self.observer.poll()["status"], "idle")

    def test_malformed_payload_after_idle_is_unknown_and_counted(self):
        self.append(lifecycle("task_complete"))
        self.assertEqual(self.observer.poll()["status"], "idle")
        self.append(record("event_msg", None))
        result = self.observer.poll()
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["invalid_records"], 1)

    def test_malformed_complete_record_does_not_become_idle(self):
        self.observer.poll()
        with self.path.open("ab") as stream: stream.write(b"{broken}\n")
        result = self.observer.poll()
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["invalid_records"], 1)

    def test_broken_json_after_confirmed_idle_is_unknown_and_counted(self):
        self.append(lifecycle("task_complete"))
        self.assertEqual(self.observer.poll()["status"], "idle")
        with self.path.open("ab") as stream:
            stream.write(b"{broken}\n")
        result = self.observer.poll()
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["invalid_records"], 1)

    def test_truncation_starts_new_source_epoch(self):
        self.append(message("Старый текст"))
        first = self.observer.poll()
        self.path.write_text(json.dumps(meta()) + "\n")
        second = self.observer.poll()
        self.assertGreater(second["source_epoch"], first["source_epoch"])
        self.assertEqual(second["public_items"], 0)
        self.assertEqual(second["status"], "unknown")

    def test_rotation_ignores_old_offset(self):
        first = self.observer.poll()
        replacement = self.path.with_suffix(".new")
        replacement.write_text("\n".join(json.dumps(x) for x in [meta(), lifecycle("task_started", "new-turn"), message("Новый поток")]) + "\n")
        os.replace(replacement, self.path)
        second = self.observer.poll()
        self.assertGreater(second["source_epoch"], first["source_epoch"])
        self.assertEqual(second["items"][0]["text"], "Новый поток")

    def test_missing_source_retains_public_context(self):
        self.append(message())
        self.observer.poll()
        self.path.unlink()
        result = self.observer.poll()
        self.assertEqual(result["status"], "disconnected")
        self.assertEqual(result["public_items"], 1)

    def test_invalid_rollout_path_metadata_retains_context_and_disconnects(self):
        self.append(message())
        self.observer.poll()
        for value in (None, 123, b"not-a-path", ""):
            with self.subTest(metadata_type=type(value).__name__):
                connection = sqlite3.connect(self.home / "state_5.sqlite")
                connection.execute("UPDATE threads SET rollout_path=?", (value,))
                connection.commit()
                connection.close()
                result = self.observer.poll()
                self.assertEqual(result["status"], "disconnected")
                self.assertEqual(result["public_items"], 1)
                self.assertEqual(result["items"][0]["text"], "Проверю обработчик простоя.")
                self.assertIsNotNone(result["source_error"])

    def test_released_writer_lock_is_disconnected(self):
        self.assertEqual(self.observer.poll()["status"], "working")
        fcntl.flock(self.writer, fcntl.LOCK_UN)
        self.assertEqual(self.observer.poll()["status"], "disconnected")

    def test_path_outside_sessions_is_rejected(self):
        outside = self.home / "auth.json"
        outside.write_text("SECRET_MARKER")
        connection = sqlite3.connect(self.home / "state_5.sqlite")
        connection.execute("UPDATE threads SET rollout_path=?", (str(outside),)); connection.commit(); connection.close()
        result = self.observer.poll()
        self.assertEqual(result["status"], "disconnected")
        self.assertFalse(result["items"])
        self.assertNotIn("SECRET_MARKER", json.dumps(result))

    def test_selected_metadata_lookup_does_not_fallback_to_another_chat(self):
        with self.assertRaises(LookupError): resolve_thread(self.home, OTHER)

    def test_process_exit_releases_actual_writer_lock(self):
        fcntl.flock(self.writer, fcntl.LOCK_UN)
        script = "import fcntl,sys,time; f=open(sys.argv[1],'rb'); fcntl.flock(f,fcntl.LOCK_EX); print('ready',flush=True); time.sleep(30)"
        process = subprocess.Popen([sys.executable, "-c", script, str(self.lock)], stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), "ready")
            self.assertTrue(writer_alive(self.home, THREAD))
            process.terminate(); process.wait(timeout=3)
            self.assertFalse(writer_alive(self.home, THREAD))
            self.assertEqual(self.observer.poll()["status"], "disconnected")
        finally:
            if process.poll() is None: process.kill(); process.wait()
            process.stdout.close()


if __name__ == "__main__":
    unittest.main()
