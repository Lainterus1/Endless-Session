import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from build_plugin import build
from install_plugin import install, verify_package
from migrate_plugin import migrate, restore_migration

ORIGIN = Path("/usr/share/omarchy/shell/plugins/lock")


class MigrationTests(unittest.TestCase):
    def setUp(self):
        attempts = patch("install_plugin.RUNTIME_ATTEMPTS", 2)
        attempts.start()
        self.addCleanup(attempts.stop)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.home = self.base / "profile"
        self.home.mkdir()
        self.config = self.home / ".config/omarchy/shell.json"
        self.config.parent.mkdir(parents=True)
        self.original = b'{\n "idle": {"lock":300}, "custom":"keep exact bytes"\n}\n'
        self.config.write_bytes(self.original)
        self.config.chmod(0o640)
        self.old_package = self.base / "old"
        self.new_package = self.base / "new"
        build(self.old_package, "lainterus.codex-idle", ORIGIN)
        build(self.new_package, "lainterus.endless-session", ORIGIN)
        self.old_backup = install(self.old_package, self.home, self.runner)
        changed = json.loads(self.config.read_text())
        changed["bar"]["releaseProbe"] = "user customization"
        self.config.write_text(json.dumps(changed, ensure_ascii=False, indent=2) + "\n")
        self.old_config = self.config.read_bytes()
        self.old_mode = stat.S_IMODE(self.config.stat().st_mode)

    def runner(self, args):
        result = subprocess.run(
            [sys.executable, "tests/installer_sink.py", str(self.home), *args],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode:
            raise RuntimeError("fixture refused command")
        return result.stdout.strip()

    def paths(self, prefix):
        return [self.home / ".config/omarchy/plugins" / (prefix + suffix) for suffix in ("", "-bridge")]

    def test_migrate_and_restore_previous_pair(self):
        self.assertEqual((self.new_package / "LICENSE").read_bytes(), (self.new_package / "companion/LICENSE").read_bytes())
        self.assertIn("Copyright (c) David Heinemeier Hansson", (self.new_package / "LICENSE").read_text())
        record = migrate(self.old_backup, self.new_package, self.home, self.runner)
        self.assertEqual(json.loads((record / "state.json").read_text())["phase"], "migrated")
        self.assertTrue(all(path.exists() for path in self.paths("lainterus.endless-session")))
        self.assertTrue(all(not path.exists() for path in self.paths("lainterus.codex-idle")))
        self.assertEqual(
            verify_package(self.paths("lainterus.endless-session")[0])["build_id"],
            verify_package(self.new_package)["build_id"],
        )
        state = restore_migration(record, self.home, self.runner)
        self.assertEqual(state["phase"], "legacy-restored")
        self.assertTrue(all(path.exists() for path in self.paths("lainterus.codex-idle")))
        self.assertTrue(all(not path.exists() for path in self.paths("lainterus.endless-session")))
        self.assertEqual(self.config.read_bytes(), self.old_config)
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), self.old_mode)
        self.assertEqual(restore_migration(record, self.home, self.runner)["phase"], "legacy-restored")

    def test_conflict_refuses_before_changes(self):
        changed_json = json.loads(self.old_config)
        changed_json["plugins"].pop()
        changed = json.dumps(changed_json).encode()
        self.config.write_bytes(changed)
        with self.assertRaises(ValueError):
            migrate(self.old_backup, self.new_package, self.home, self.runner)
        self.assertEqual(self.config.read_bytes(), changed)
        self.assertFalse((self.home / ".local/state/omarchy-codex-idle/migrations").exists())

    def test_failed_new_enable_recovers_old_pair(self):
        def runner(args):
            if args == ["omarchy", "plugin", "enable", "lainterus.endless-session-bridge"]:
                raise RuntimeError("injected enable failure")
            return self.runner(args)

        with self.assertRaisesRegex(RuntimeError, "legacy pair restored"):
            migrate(self.old_backup, self.new_package, self.home, runner)
        self.assertTrue(all(path.exists() for path in self.paths("lainterus.codex-idle")))
        self.assertTrue(all(not path.exists() for path in self.paths("lainterus.endless-session")))
        self.assertEqual(hashlib.sha256(self.config.read_bytes()).digest(), hashlib.sha256(self.old_config).digest())

    def test_failed_first_new_enable_recovers_old_pair(self):
        def runner(args):
            if args == ["omarchy", "plugin", "enable", "lainterus.endless-session"]:
                raise RuntimeError("injected first enable failure")
            return self.runner(args)

        with self.assertRaisesRegex(RuntimeError, "legacy pair restored"):
            migrate(self.old_backup, self.new_package, self.home, runner)
        self.assertTrue(all(path.exists() for path in self.paths("lainterus.codex-idle")))
        self.assertEqual(self.config.read_bytes(), self.old_config)

    def test_stock_restart_failure_recovers_old_pair(self):
        count = [0]

        def runner(args):
            if args == ["omarchy", "restart", "shell"]:
                count[0] += 1
                if count[0] == 1:
                    raise RuntimeError("injected stock restart failure")
            return self.runner(args)

        with self.assertRaisesRegex(RuntimeError, "legacy pair restored"):
            migrate(self.old_backup, self.new_package, self.home, runner)
        self.assertTrue(all(path.exists() for path in self.paths("lainterus.codex-idle")))
        self.assertEqual(self.config.read_bytes(), self.old_config)

    def test_interrupted_legacy_parking_recovers_old_pair(self):
        original = Path.rename
        failing = self.paths("lainterus.codex-idle")[1]
        once = [False]

        def rename(path, target):
            if path == failing and not once[0]:
                once[0] = True
                raise OSError("injected interruption")
            return original(path, target)

        with patch.object(Path, "rename", rename):
            with self.assertRaisesRegex(RuntimeError, "legacy pair restored"):
                migrate(self.old_backup, self.new_package, self.home, self.runner)
        self.assertTrue(all(path.exists() for path in self.paths("lainterus.codex-idle")))
        self.assertEqual(self.config.read_bytes(), self.old_config)

    def test_new_config_drift_refuses_restore(self):
        record = migrate(self.old_backup, self.new_package, self.home, self.runner)
        edited = json.loads(self.config.read_text())
        edited["bar"]["releaseProbe"] = "changed after migration"
        self.config.write_text(json.dumps(edited))
        with self.assertRaises(ValueError):
            restore_migration(record, self.home, self.runner)
        self.assertTrue(all(path.exists() for path in self.paths("lainterus.endless-session")))

    def test_resume_after_new_install_before_final_record(self):
        record = migrate(self.old_backup, self.new_package, self.home, self.runner)
        state = json.loads((record / "state.json").read_text())
        state["phase"] = "new-prepared"
        (record / "state.json").write_text(json.dumps(state))
        self.assertEqual(restore_migration(record, self.home, self.runner)["phase"], "legacy-restored")
        self.assertEqual(self.config.read_bytes(), self.old_config)

    def test_changed_parked_payload_refuses_recovery(self):
        record = migrate(self.old_backup, self.new_package, self.home, self.runner)
        (record / "legacy-companion" / "Service.qml").write_text("tampered")
        with self.assertRaises(ValueError):
            restore_migration(record, self.home, self.runner)
        self.assertTrue(all(path.exists() for path in self.paths("lainterus.endless-session")))

    def test_resume_after_old_config_restored_before_reload(self):
        record = migrate(self.old_backup, self.new_package, self.home, self.runner)
        restarts = [0]

        def runner(args):
            if args == ["omarchy", "restart", "shell"]:
                restarts[0] += 1
                if restarts[0] == 2:
                    raise RuntimeError("injected final restart interruption")
            return self.runner(args)

        with self.assertRaises(RuntimeError):
            restore_migration(record, self.home, runner)
        self.assertEqual(self.config.read_bytes(), self.old_config)
        self.assertTrue(all(path.exists() for path in self.paths("lainterus.codex-idle")))
        self.assertEqual(restore_migration(record, self.home, self.runner)["phase"], "legacy-restored")


if __name__ == "__main__":
    unittest.main()
