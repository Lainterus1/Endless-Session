"""Контракт потока; синтетические данные и настоящая subprocess/pipe граница."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from stream_context import Stream
from test_source_probe import THREAD, message, meta, lifecycle


def snapshot(items, epoch=0, status="working"):
    return {"thread_id": THREAD, "source_epoch": epoch, "status": status,
            "pending_questions": 0, "name": "Тестовая сессия", "items": items}


def item(index, text=None):
    return {"id": str(index), "type": "message", "phase": "commentary", "timestamp": None,
            "text": text if text is not None else "Сообщение " + str(index)}


class StreamTests(unittest.TestCase):
    def test_initial_history_is_last_eight_full_ordered_items(self):
        items = [item(i, ("Полный Unicode текст.\n" * 200) + str(i)) for i in range(12)]
        frame = Stream().frame([snapshot(items)])
        self.assertEqual(frame["schema_version"], 1)
        self.assertTrue(frame["chats"][0]["reset"])
        self.assertEqual(frame["chats"][0]["items"], items[-8:])

    def test_only_changed_items_emit_and_heartbeat_advances(self):
        stream = Stream()
        stream.frame([snapshot([item(1)])])
        frame = stream.frame([snapshot([item(1)])])
        self.assertEqual(frame["sequence"], 2)
        self.assertEqual(frame["chats"][0]["items"], [])
        updated = stream.frame([snapshot([item(1, "Изменён"), item(2)])])
        self.assertFalse(updated["chats"][0]["reset"])
        self.assertEqual(updated["chats"][0]["items"], [item(1, "Изменён"), item(2)])

    def test_epoch_and_process_restart_reset_history(self):
        stream = Stream()
        stream.frame([snapshot([item(1)])])
        frame = stream.frame([snapshot([item(1, "Другая эпоха")], epoch=1)])
        self.assertTrue(frame["chats"][0]["reset"])
        self.assertEqual(frame["chats"][0]["items"][0]["text"], "Другая эпоха")
        self.assertTrue(Stream().frame([snapshot([item(1)])])["chats"][0]["reset"])

    def test_state_changes_keep_pending_and_do_not_synthesize_completion(self):
        stream = Stream()
        first = snapshot([item(1)], status="waiting_input"); first["pending_questions"] = 2
        stream.frame([first])
        first["status"] = "disconnected"
        lost = stream.frame([first])["chats"][0]
        self.assertEqual(lost["status"], "disconnected")
        self.assertEqual(lost["pending_questions"], 2)
        self.assertEqual(lost["items"], [])

    def test_unknown_metadata_does_not_leave_projection(self):
        data = {**item(1), "private_metadata": "NOT_PUBLIC"}
        frame = Stream().frame([snapshot([data])])
        self.assertNotIn("NOT_PUBLIC", json.dumps(frame))

    def test_real_cli_pipe_reads_synthetic_selected_source(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory); (home / "sessions").mkdir()
            log = home / "sessions/test.jsonl"
            log.write_text("\n".join(json.dumps(r) for r in [meta(), lifecycle("task_started"), message("Полный <b>текст</b>")]) + "\n")
            with sqlite3.connect(home / "state_5.sqlite") as db:
                db.execute("CREATE TABLE threads(id TEXT, rollout_path TEXT, title TEXT, archived INTEGER)")
                db.execute("INSERT INTO threads VALUES(?,?,?,0)", (THREAD, str(log), "Fixture"))
            result = subprocess.run([sys.executable, "stream_context.py", "--thread", THREAD,
                                     "--codex-home", str(home), "--once"], text=True, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = result.stdout.splitlines(); self.assertEqual(len(lines), 1)
            frame = json.loads(lines[0]); chat = frame["chats"][0]
            self.assertEqual(chat["thread_id"], THREAD)
            self.assertEqual(chat["items"][0]["text"], "Полный <b>текст</b>")
            self.assertEqual(chat["status"], "disconnected")
            self.assertNotIn("idle", chat["status"])


if __name__ == "__main__":
    unittest.main()
