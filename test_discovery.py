import fcntl
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from discovery import Discovery, Worker, thread_roster
from theme import Theme, DEFAULT, contrast
from test_source_probe import THREAD, meta, lifecycle, message, question


@contextmanager
def database(path):
    connection = sqlite3.connect(path)
    try:
        with connection: yield connection
    finally: connection.close()


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        (self.home / "sessions").mkdir(); (self.home / "thread-writer-locks").mkdir()
        self.db = self.home / "state_5.sqlite"
        with database(self.db) as db: db.execute("CREATE TABLE threads(id TEXT, rollout_path TEXT, title TEXT, archived INTEGER, thread_source TEXT, source TEXT)")
        self.now = 10
        self.discovery = Discovery(self.home, lambda: self.now)

    def add(self, number, records, locked=True, thread_source="user", source=None):
        thread = f"00000000-0000-4000-8000-{number:012d}"
        path = self.home / "sessions" / (thread + ".jsonl")
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False).replace(THREAD, thread) for r in records) + "\n")
        with database(self.db) as db:
            db.execute("INSERT INTO threads VALUES(?,?,?,0,?,?)", (thread, str(path), "Fixture", thread_source, source))
        if locked:
            lock = (self.home / "thread-writer-locks" / (thread + ".lock")).open("w")
            fcntl.flock(lock, fcntl.LOCK_EX); self.addCleanup(lock.close)
        return thread, path

    def test_guardian_excluded_before_writer_or_journal_and_not_held(self):
        guardian, _ = self.add(1, [meta(), lifecycle("task_started"), message()],
                               thread_source="guardian_review")
        user, _ = self.add(2, [meta(), lifecycle("task_started"), question()])
        original = __import__("discovery").Observer
        def observer(home, thread):
            if thread == guardian: raise AssertionError("guardian journal opened")
            return original(home, thread)
        with patch("discovery.Observer", side_effect=observer):
            self.discovery.scan()
        self.assertEqual(set(self.discovery.monitored), {user})
        self.assertNotIn(guardian, self.discovery.observers)
        self.assertEqual(self.discovery.monitored[user]["status"], "waiting_input")
        with database(self.db) as db: db.execute("UPDATE threads SET archived=1 WHERE id=?", (user,))
        self.discovery = Discovery(self.home, lambda: self.now)
        with patch("discovery.Observer", side_effect=AssertionError("guardian journal opened")):
            self.discovery.scan()
        self.assertEqual(self.discovery.state, "ready")
        self.assertEqual(self.discovery.monitored, {})
        self.assertEqual(self.discovery.unknown_count, 0)

    def test_reclassified_guardian_is_removed_without_disconnected_snapshot(self):
        user, _ = self.add(1, [meta(), lifecycle("task_started"), message()])
        self.discovery.scan()
        self.assertIn(user, self.discovery.monitored)
        with database(self.db) as db:
            db.execute("UPDATE threads SET source=?, archived=1 WHERE id=?",
                       ('{"subagent":{"other":"guardian"}}', user))
        with patch("discovery.Observer", side_effect=AssertionError("guardian journal reopened")):
            self.discovery.scan()
        self.assertNotIn(user, self.discovery.monitored)
        self.assertNotIn(user, self.discovery.observers)
        self.assertEqual(self.discovery.state, "ready")

    def test_category_metadata_does_not_guess_from_titles_or_other_subagents(self):
        ordinary, _ = self.add(1, [meta(), lifecycle("task_started"), message()], source="{broken")
        other, _ = self.add(2, [meta(), lifecycle("task_started"), message()],
                            thread_source="subagent", source='{"subagent":{"other":"review"}}')
        guardian, _ = self.add(3, [meta(), lifecycle("task_started"), message()],
                               thread_source="user", source='{"subagent":{"other":"guardian"}}')
        ids, guardians = thread_roster(self.home)
        self.assertEqual(set(ids), {ordinary, other})
        self.assertEqual(guardians, {guardian})
        self.discovery.scan()
        self.assertEqual(set(self.discovery.monitored), {ordinary, other})

    def test_legacy_metadata_without_category_columns_remains_supported(self):
        with database(self.db) as db:
            db.execute("DROP TABLE threads")
            db.execute("CREATE TABLE threads(id TEXT, archived INTEGER)")
            db.execute("INSERT INTO threads VALUES(?,0)", ("00000000-0000-4000-8000-000000000001",))
        ids, guardians = thread_roster(self.home)
        self.assertEqual(ids, ["00000000-0000-4000-8000-000000000001"])
        self.assertEqual(guardians, set())

    def test_null_archived_value_does_not_become_candidate(self):
        thread, _ = self.add(1, [meta(), lifecycle("task_started"), message()])
        with database(self.db) as db: db.execute("UPDATE threads SET archived=NULL WHERE id=?", (thread,))
        ids, guardians = thread_roster(self.home)
        self.assertEqual(ids, [])
        self.assertEqual(guardians, set())

    def test_active_pending_finished_and_read_only(self):
        done, _ = self.add(1, [meta(), lifecycle("task_started"), message(), lifecycle("task_complete")], locked=False)
        active, _ = self.add(2, [meta(), lifecycle("task_started"), message()])
        waiting, _ = self.add(3, [meta(), lifecycle("task_started"), question(), lifecycle("task_complete")])
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        self.assertEqual(self.discovery.state, "scanning")
        self.discovery.scan()
        self.assertEqual(self.discovery.state, "ready")
        self.assertEqual(set(self.discovery.monitored), {active, waiting})
        self.assertEqual(self.discovery.monitored[waiting]["status"], "waiting_input")
        self.assertEqual(self.discovery.monitored[active]["status"], "working")
        self.assertNotIn(done,self.discovery.observers)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), before)

    def test_loss_archive_and_discovery_error_never_empty(self):
        active, path = self.add(1, [meta(), lifecycle("task_started"), message()])
        self.discovery.scan(); path.unlink(); self.discovery.scan()
        self.assertEqual(self.discovery.monitored[active]["status"], "disconnected")
        with database(self.db) as db: db.execute("UPDATE threads SET archived=1")
        self.discovery.scan(); self.assertIn(active, self.discovery.monitored)
        self.db.rename(self.home / "missing.sqlite")
        self.discovery.scan(); self.assertEqual(self.discovery.state, "unknown"); self.assertIn(active, self.discovery.monitored)

    def test_historical_question_and_interrupted_turn_are_not_live_chats(self):
        stale_question,_=self.add(1,[meta(),lifecycle("task_started"),question(),lifecycle("task_complete")],locked=False)
        interrupted,_=self.add(2,[meta(),lifecycle("task_started"),message()],locked=False)
        live,_=self.add(3,[meta(),lifecycle("task_started"),message()])
        self.discovery.scan()
        self.assertEqual(set(self.discovery.monitored),{live})
        self.assertEqual(self.discovery.state,"ready")
        self.assertNotIn(stale_question,self.discovery.observers)
        self.assertNotIn(interrupted,self.discovery.observers)

    def test_later_writer_admission_and_loss_preserve_context(self):
        thread,_=self.add(1,[meta(),lifecycle("task_started"),question()],locked=False)
        self.discovery.scan();self.assertNotIn(thread,self.discovery.monitored)
        with (self.home/"thread-writer-locks"/(thread+".lock")).open("w") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            self.discovery.scan();self.assertEqual(self.discovery.monitored[thread]["status"],"waiting_input")
            self.assertTrue(self.discovery.monitored[thread]["items"])
        self.discovery.scan()
        self.assertEqual(self.discovery.monitored[thread]["status"],"disconnected")
        self.assertTrue(self.discovery.monitored[thread]["items"])

    def test_unknown_writer_then_live_keeps_full_initial_context(self):
        thread,_=self.add(1,[meta(),lifecycle("task_started"),message(),question()])
        with patch("discovery.writer_alive",return_value=None),patch("source_probe.writer_alive",return_value=None):
            self.discovery.scan()
        self.assertNotIn(thread,self.discovery.monitored)
        self.assertEqual(self.discovery.state,"unknown")
        self.discovery.scan()
        self.assertEqual(self.discovery.monitored[thread]["status"],"waiting_input")
        self.assertEqual(self.discovery.monitored[thread]["pending_questions"],2)
        self.assertEqual(len(self.discovery.monitored[thread]["items"]),2)

    def test_completed_retention_and_new_turn(self):
        active, path = self.add(1, [meta(), lifecycle("task_started"), message()])
        self.discovery.scan()
        with path.open("a") as file: file.write(json.dumps(lifecycle("task_complete")) + "\n")
        self.discovery.scan(); self.assertEqual(self.discovery.monitored[active]["status"], "idle")
        self.now += 9; self.discovery.scan(); self.assertIn(active, self.discovery.monitored)
        self.now += 1; self.discovery.scan(); self.assertNotIn(active, self.discovery.monitored)
        with path.open("a") as file: file.write(json.dumps(lifecycle("task_started", "turn-2")) + "\n")
        self.discovery.scan(); self.assertEqual(self.discovery.monitored[active]["status"], "working")

    def test_unsupported_and_empty_are_distinct(self):
        self.discovery.scan(); self.assertEqual(self.discovery.state, "ready"); self.assertFalse(self.discovery.monitored)
        self.add(1, [meta("unsupported"), lifecycle("task_started")])
        self.discovery.scan(); self.assertEqual(self.discovery.state, "unknown"); self.assertEqual(self.discovery.unknown_count, 1)

    def test_worker_heartbeat_does_not_wait_for_scan(self):
        entered = threading.Event(); release = threading.Event()
        def slow_scan(progress): entered.set(); release.wait(2)
        self.discovery.scan = slow_scan
        worker = Worker(self.discovery, lambda: self.now)
        worker.start()
        try:
            self.assertTrue(entered.wait(1))
            start = time.monotonic(); self.assertEqual(worker.snapshot()[0], "scanning")
            self.assertLess(time.monotonic() - start, 0.05)
            self.now += 6; self.assertEqual(worker.snapshot()[0], "unknown")
        finally: worker.stop.set(); release.set(); worker.thread.join(1)


class ThemeTests(unittest.TestCase):
    def test_symlink_theme_switch_fallback_and_font_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory); current = home / ".local/state/omarchy/current"; current.mkdir(parents=True)
            dark = home / "dark"; light = home / "light"; dark.mkdir(); light.mkdir()
            (dark / "colors.toml").write_text('foreground="#ffffff"\nbackground="#101010"\naccent="#aaccff"')
            (light / "colors.toml").write_text('foreground="#111111"\nbackground="#ffffff"\naccent="#222222"')
            link = current / "theme"; link.symlink_to(dark, target_is_directory=True)
            theme = Theme(home)
            with patch("theme.subprocess.run") as process:
                process.return_value.returncode = 0; process.return_value.stdout = "Fixture Mono"
                first = theme.read(); self.assertEqual(first["background"], "#101010")
                self.assertEqual(first["fontFamily"], "Fixture Mono")
                link.unlink(); link.symlink_to(light, target_is_directory=True)
                second = theme.read(); self.assertEqual(second["background"], "#ffffff")
                self.assertEqual(process.call_count, 1)
                theme.font_path.parent.mkdir(parents=True); theme.font_path.write_text("fixture")
                process.return_value.stdout = "New Mono"; self.assertEqual(theme.read()["fontFamily"], "New Mono")
                (light / "colors.toml").write_text('foreground="#dddddd"\nbackground="#ffffff"\naccent="invalid"')
                fallback = theme.read(); self.assertEqual(fallback["foreground"], DEFAULT["foreground"])
                self.assertGreaterEqual(contrast(fallback["foreground"], fallback["background"]), 4.5)
                (light / "colors.toml").write_text("broken = [")
                self.assertEqual(theme.read()["background"], DEFAULT["background"])
                self.assertEqual((light / "colors.toml").read_text(), "broken = [")
