import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

from build_plugin import build
from install_plugin import install, restore, verify_package
from unittest.mock import patch

ORIGIN=Path("/usr/share/omarchy/shell/plugins/lock")


class InstallerTests(unittest.TestCase):
    def setUp(self):
        attempts=patch("install_plugin.RUNTIME_ATTEMPTS",2);attempts.start();self.addCleanup(attempts.stop)
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name); self.home=self.base/"profile"; self.home.mkdir()
        self.config=self.home/".config/omarchy/shell.json"; self.config.parent.mkdir(parents=True)
        self.original=b'{\n "idle": {"lock":300}, "custom":"keep exact bytes"\n}\n'
        self.config.write_bytes(self.original); self.config.chmod(0o640)
        self.package=self.base/"package"; build(self.package,"fixture.codex-idle",ORIGIN)
        self.target=self.home/".config/omarchy/plugins/fixture.codex-idle"
        self.companion=self.home/".config/omarchy/plugins/fixture.codex-idle-bridge"

    def runner(self,args):
        result=subprocess.run([sys.executable,"tests/installer_sink.py",str(self.home),*args],capture_output=True,text=True,timeout=5)
        if result.returncode: raise RuntimeError("fixture refused command")
        return result.stdout.strip()

    def control(self,**values): (self.home/"control.json").write_text(json.dumps(values))

    def test_enabled_but_stale_runtime_cannot_report_installed(self):
        self.control(stale_runtime=True)
        with self.assertRaises(RuntimeError): install(self.package,self.home,self.runner)
        backup=next((self.home/".local/state/omarchy-codex-idle/backups").iterdir())
        self.assertEqual(json.loads((backup/"state.json").read_text())["phase"],"needs-recovery")
        self.control();restore(backup,self.home,self.runner)
        self.assertEqual(self.config.read_bytes(),self.original)

    def test_restart_failure_keeps_recoverable_pair(self):
        self.control(fail_restart=True)
        with self.assertRaises(RuntimeError): install(self.package,self.home,self.runner)
        backup=next((self.home/".local/state/omarchy-codex-idle/backups").iterdir())
        self.assertTrue(self.target.exists());self.assertTrue(self.companion.exists())
        self.control();restore(backup,self.home,self.runner)
        self.assertEqual(self.config.read_bytes(),self.original)

    def test_stale_idle_cannot_hide_behind_current_lock(self):
        self.control(stale_idle=True)
        with self.assertRaises(RuntimeError):install(self.package,self.home,self.runner)
        backup=next((self.home/".local/state/omarchy-codex-idle/backups").iterdir())
        self.assertEqual(json.loads((backup/"state.json").read_text())["phase"],"needs-recovery")

    def test_pending_lock_refuses_before_any_write(self):
        self.control(pending=True)
        with self.assertRaises(ValueError):install(self.package,self.home,self.runner)
        self.assertFalse(self.target.exists());self.assertEqual(self.config.read_bytes(),self.original)

    def test_lock_requested_before_restart_keeps_recovery(self):
        def runner(args):
            if args==["omarchy","shell","lock","status"] and self.companion.exists():
                data=json.loads(self.config.read_text())
                if any(p["id"]=="fixture.codex-idle-bridge" for p in data.get("plugins",[])):
                    result=json.loads(self.runner(args));result["requested"]=True;return json.dumps(result)
            return self.runner(args)
        with self.assertRaises(RuntimeError):install(self.package,self.home,runner)
        calls=[json.loads(line) for line in (self.home/"calls.jsonl").read_text().splitlines()]
        self.assertNotIn(["omarchy","restart","shell"],calls)
        backup=next((self.home/".local/state/omarchy-codex-idle/backups").iterdir())
        restore(backup,self.home,self.runner);self.assertEqual(self.config.read_bytes(),self.original)

    def test_restore_old_runtime_is_pending_and_retryable(self):
        backup=install(self.package,self.home,self.runner);self.control(retain_runtime=True)
        with self.assertRaises(RuntimeError):restore(backup,self.home,self.runner)
        self.assertEqual(self.config.read_bytes(),self.original)
        self.assertEqual(json.loads((backup/"state.json").read_text())["phase"],"restored-pending-reload")
        self.control();restore(backup,self.home,self.runner)
        self.assertEqual(json.loads((backup/"state.json").read_text())["phase"],"restored")

    def test_runtime_identity_is_literal_and_changes_with_payload(self):
        package=verify_package(self.package)
        for path in ("Service.qml","companion/Service.qml"):
            self.assertIn('codexRuntimeRevision: "'+package["runtime_revision"]+'"',(self.package/path).read_text())
        other=self.base/"other";build(other,"other.codex-idle",ORIGIN)
        self.assertNotEqual(package["runtime_revision"],verify_package(other)["runtime_revision"])

    def test_stay_awake_is_preserved_by_install_and_restore(self):
        self.control(stay_awake=True)
        backup=install(self.package,self.home,self.runner)
        self.assertFalse(json.loads(self.runner(["omarchy","shell","idle","status"]))["enabled"])
        restore(backup,self.home,self.runner)
        self.assertEqual(self.config.read_bytes(),self.original)
        self.assertTrue(json.loads(self.runner(["omarchy","shell","idle","status"]))["stayAwake"])

    def test_install_restore_exact_bytes_modes_and_unrelated_files(self):
        unrelated=self.home/".config/omarchy/plugins/neighbor/keep.txt"; unrelated.parent.mkdir(parents=True); unrelated.write_text("neighbor")
        backup=install(self.package,self.home,self.runner)
        self.assertEqual(verify_package(self.target)["build_id"],verify_package(self.package)["build_id"])
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode),0o700)
        self.assertEqual(stat.S_IMODE((backup/"shell.json.before").stat().st_mode),0o600)
        self.assertEqual((backup/"shell.json.before").read_bytes(),self.original)
        restore(backup,self.home,self.runner)
        self.assertEqual(self.config.read_bytes(),self.original); self.assertEqual(stat.S_IMODE(self.config.stat().st_mode),0o640)
        self.assertFalse(self.target.exists()); self.assertTrue((backup/"restored-package").is_dir()); self.assertEqual(unrelated.read_text(),"neighbor")

    def test_existing_target_and_lock_clone_refuse_without_writes(self):
        self.target.mkdir(parents=True); (self.target/"foreign").write_text("keep")
        with self.assertRaises(ValueError): install(self.package,self.home,self.runner)
        self.assertEqual((self.target/"foreign").read_text(),"keep"); self.assertEqual(self.config.read_bytes(),self.original)
        shutil.rmtree(self.target)
        self.config.write_text('{"disabledPlugins":["omarchy.lock"]}')
        before=self.config.read_bytes()
        with self.assertRaises(ValueError): install(self.package,self.home,self.runner)
        self.assertEqual(self.config.read_bytes(),before); self.assertFalse(self.target.exists())

    def test_restore_rejects_post_install_config_edit(self):
        backup=install(self.package,self.home,self.runner)
        self.config.write_bytes(self.config.read_bytes()+b'\n')
        changed=self.config.read_bytes()
        with self.assertRaises(ValueError): restore(backup,self.home,self.runner)
        self.assertEqual(self.config.read_bytes(),changed); self.assertTrue(self.target.exists())
        self.assertEqual((backup/"shell.json.before").read_bytes(),self.original)

    def test_modified_payload_and_symlink_rejected(self):
        backup=install(self.package,self.home,self.runner)
        before=self.config.read_bytes(); (self.target/"Service.qml").write_text("user changed")
        with self.assertRaises(ValueError): restore(backup,self.home,self.runner)
        self.assertEqual(self.config.read_bytes(),before); self.assertEqual((self.target/"Service.qml").read_text(),"user changed")
        (self.package/"outside").symlink_to(self.config)
        with self.assertRaises(ValueError): verify_package(self.package)

    def test_enable_failure_before_change_removes_only_owned_target(self):
        self.control(fail_before=True)
        with self.assertRaises(RuntimeError): install(self.package,self.home,self.runner)
        self.assertFalse(self.target.exists()); self.assertEqual(self.config.read_bytes(),self.original)
        backup=next((self.home/".local/state/omarchy-codex-idle/backups").iterdir())
        self.assertEqual(json.loads((backup/"state.json").read_text())["phase"],"failed-before-config-change")
        self.assertTrue((backup/"unactivated-package").is_dir())

    def test_enable_failure_after_write_preserves_recovery_state(self):
        self.control(fail_after=True)
        with self.assertRaises(RuntimeError): install(self.package,self.home,self.runner)
        backup=next((self.home/".local/state/omarchy-codex-idle/backups").iterdir())
        self.assertEqual((backup/"shell.json.before").read_bytes(),self.original)
        state=json.loads((backup/"state.json").read_text()); self.assertEqual(state["phase"],"needs-recovery")
        self.assertEqual(state["observed_failure_sha256"],hashlib.sha256(self.config.read_bytes()).hexdigest())
        restore(backup,self.home,self.runner)
        self.assertEqual(self.config.read_bytes(),self.original)

    def test_locked_machine_refuses_before_install(self):
        self.control(locked=True)
        with self.assertRaises(ValueError): install(self.package,self.home,self.runner)
        self.assertFalse(self.target.exists()); self.assertEqual(self.config.read_bytes(),self.original)

    def test_changed_origin_rejected_before_package_creation(self):
        changed=self.base/"origin"; shutil.copytree(ORIGIN,changed); (changed/"Service.qml").write_text("changed")
        with self.assertRaises(ValueError): build(self.base/"rejected","fixture.codex-idle",changed)
        self.assertFalse((self.base/"rejected").exists())

    def test_restore_resumes_after_config_write_before_move(self):
        backup=install(self.package,self.home,self.runner)
        original_rename=Path.rename
        def fail_move(path,dest):
            if path==self.target: raise OSError("injected interruption")
            return original_rename(path,dest)
        with patch.object(Path,"rename",fail_move):
            with self.assertRaises(OSError): restore(backup,self.home,self.runner)
        self.assertEqual(self.config.read_bytes(),self.original)
        restore(backup,self.home,self.runner)
        self.assertFalse(self.target.exists())

    def test_restore_reload_failure_can_retry(self):
        backup=install(self.package,self.home,self.runner);self.control(fail_reload=True)
        with self.assertRaises(RuntimeError): restore(backup,self.home,self.runner)
        self.assertEqual(json.loads((backup/"state.json").read_text())["phase"],"restored-pending-reload")
        self.control();restore(backup,self.home,self.runner)
        self.assertEqual(self.config.read_bytes(),self.original)

    def test_restore_destination_conflict_refuses_before_config_write(self):
        backup=install(self.package,self.home,self.runner);before=self.config.read_bytes()
        (backup/"restored-package").mkdir()
        with self.assertRaises(ValueError): restore(backup,self.home,self.runner)
        self.assertEqual(self.config.read_bytes(),before)

    def test_failed_enable_with_foreign_edit_refuses_recovery(self):
        self.control(fail_after=True)
        with self.assertRaises(RuntimeError): install(self.package,self.home,self.runner)
        backup=next((self.home/".local/state/omarchy-codex-idle/backups").iterdir())
        self.config.write_bytes(self.config.read_bytes()+b'\n')
        changed=self.config.read_bytes()
        with self.assertRaises(ValueError): restore(backup,self.home,self.runner)
        self.assertEqual(self.config.read_bytes(),changed)

    def test_changed_compatibility_invalidates_identity(self):
        manifest=self.package/"package.json";value=json.loads(manifest.read_text());value["compatibility"]["qt"]="0.0.0";manifest.write_text(json.dumps(value))
        with self.assertRaises(ValueError):verify_package(self.package)

    def test_second_enable_failure_restores_both_prefixes(self):
        for key in ("fail_before_id","fail_after_id"):
            with self.subTest(key=key):
                self.control(**{key:"fixture.codex-idle-bridge"})
                with self.assertRaises(RuntimeError):install(self.package,self.home,self.runner)
                backups=sorted((self.home/".local/state/omarchy-codex-idle/backups").iterdir(),key=lambda p:p.stat().st_mtime_ns)
                backup=backups[-1]
                self.assertTrue(self.target.exists());self.assertTrue(self.companion.exists())
                restore(backup,self.home,self.runner)
                self.assertEqual(self.config.read_bytes(),self.original)
                self.assertFalse(self.target.exists());self.assertFalse(self.companion.exists())

    def test_modified_companion_refuses_before_any_restore_write(self):
        backup=install(self.package,self.home,self.runner);before=self.config.read_bytes()
        (self.companion/"Service.qml").write_text("foreign change")
        with self.assertRaises(ValueError):restore(backup,self.home,self.runner)
        self.assertEqual(self.config.read_bytes(),before);self.assertTrue(self.target.exists())
        self.assertFalse((backup/"restored-package").exists())

    def test_restore_resumes_between_two_payload_moves(self):
        backup=install(self.package,self.home,self.runner);original_rename=Path.rename
        def fail_move(path,dest):
            if path==self.companion:raise OSError("injected second move failure")
            return original_rename(path,dest)
        with patch.object(Path,"rename",fail_move):
            with self.assertRaises(OSError):restore(backup,self.home,self.runner)
        self.assertEqual(self.config.read_bytes(),self.original);self.assertFalse(self.target.exists())
        self.assertTrue(self.companion.exists());restore(backup,self.home,self.runner)
        self.assertFalse(self.companion.exists())

    def test_existing_idle_clone_refuses_before_backup(self):
        self.companion.mkdir(parents=True);(self.companion/"foreign").write_text("keep")
        with self.assertRaises(ValueError):install(self.package,self.home,self.runner)
        self.assertEqual(self.config.read_bytes(),self.original);self.assertFalse(self.target.exists())
