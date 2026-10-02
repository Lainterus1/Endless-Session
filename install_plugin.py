"""Установка проверенного клона и восстановление; реальный запуск требует поручения."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import time
import uuid

from build_plugin import tree_hashes

RUNTIME_ATTEMPTS = 40


def digest(data): return hashlib.sha256(data).hexdigest()


def run(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    if result.returncode: raise RuntimeError("command failed: " + " ".join(command))
    return result.stdout.strip()


def no_symlinks(path):
    for node in [path, *path.parents]:
        if node.is_symlink(): raise ValueError("symlink path is not supported: " + str(node))


def verify_package(path):
    no_symlinks(path)
    if any(p.is_symlink() for p in path.rglob("*")): raise ValueError("symlink in package")
    package = json.loads((path / "package.json").read_text())
    if package.get("schema_version") != 1 or not re.fullmatch(r"[a-z0-9][a-z0-9._-]*\.(?:codex-idle|endless-session)", package.get("id", "")): raise ValueError("invalid package")
    actual = tree_hashes(path)
    if actual != package["files"]: raise ValueError("package content mismatch")
    identity = {key: value for key, value in package.items() if key != "build_id"}
    if digest(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()) != package["build_id"]: raise ValueError("package identity mismatch")
    if json.loads((path / "manifest.json").read_text())["id"] != package["id"]: raise ValueError("manifest identity mismatch")
    companion=package.get("companion")
    if companion:
        if companion.get("id")!=package["id"]+"-bridge" or companion.get("directory")!="companion" or companion.get("clonedFrom")!="omarchy.idle": raise ValueError("invalid companion")
        manifest=json.loads((path/"companion/manifest.json").read_text())
        if manifest["id"]!=companion["id"] or manifest.get("omarchy",{}).get("clonedFrom")!="omarchy.idle": raise ValueError("companion identity mismatch")
    return package


def package_units(path, package):
    units=[dict(id=package["id"],source="omarchy.lock",path=path,files=package["files"],suffix="package")]
    if package.get("companion"):
        units.append(dict(id=package["companion"]["id"],source="omarchy.idle",path=path/"companion",
            files={name[len("companion/"):]:value for name,value in package["files"].items() if name.startswith("companion/")},suffix="companion"))
    return units


def verify_unit(path, unit):
    no_symlinks(path)
    if not path.is_dir() or any(p.is_symlink() for p in path.rglob("*")) or tree_hashes(path)!=unit["files"]: raise ValueError("payload changed: "+unit["id"])
    if unit["suffix"]=="package": verify_package(path)


def config_prefixes(original, units):
    values=[json.loads(original)]
    for unit in units: values.append(expected_enabled(json.dumps(values[-1]).encode(),unit["id"],unit["source"]))
    return values


def check_runtime(package, runner):
    compatibility = package["compatibility"]
    if compatibility["origin"] != "/usr/share/omarchy/shell/plugins/lock" or set(compatibility["sha256"]) != {"Service.qml","LockView.qml","manifest.json"}: raise ValueError("unsupported compatibility origin")
    if runner(["pacman", "-Q", "omarchy"]).split()[-1] != compatibility["omarchy"]: raise ValueError("unsupported Omarchy version")
    if not re.search(r"(?<![\d.])"+re.escape(compatibility["quickshell"])+r"(?![\d.])", runner(["qs", "--version"])): raise ValueError("unsupported Quickshell version")
    if runner(["pacman", "-Q", "qt6-declarative"]).split()[-1].split("-")[0] != compatibility["qt"]: raise ValueError("unsupported Qt version")
    origin = Path(compatibility["origin"])
    for name, expected in compatibility["sha256"].items():
        if digest((origin / name).read_bytes()) != expected: raise ValueError("installed lock changed")
    companion=package.get("companion")
    if companion:
        compat=companion["compatibility"]
        if compat["origin"]!="/usr/share/omarchy/shell/plugins/services/idle" or set(compat["sha256"])!={"Service.qml","IdleModel.js","manifest.json"}: raise ValueError("unsupported idle compatibility")
        for name,expected in compat["sha256"].items():
            if digest((Path(compat["origin"])/name).read_bytes())!=expected: raise ValueError("installed idle changed")


def ensure_unlocked(runner):
    if runner(["omarchy", "shell", "lock", "isLocked"]) != "false": raise ValueError("unlock before changing lock plugin")
    status=json.loads(runner(["omarchy","shell","lock","status"]))
    if not isinstance(status,dict) or any(status.get(key) is not False for key in ("locked","requested","pending","sessionLocked","secure","authenticating")):
        raise ValueError("lock is active or status is incomplete")


def confirm_runtime(runner, revision=None, companion=True):
    for _ in range(RUNTIME_ATTEMPTS):
        try:
            lock=json.loads(runner(["omarchy","shell","lock","status"]))
            idle=json.loads(runner(["omarchy","shell","idle","status"])) if companion else {}
            if not isinstance(lock,dict) or not isinstance(idle,dict): raise ValueError("invalid runtime status")
            if revision:
                matched=lock.get("codexRuntimeRevision")==revision and (not companion or idle.get("codexRuntimeRevision")==revision)
            else:
                matched=not any(key.startswith("codex") for key in lock) and not any(key.startswith("codex") for key in idle)
            idle_ready=(not companion or (idle.get("stayAwakeStateLoaded") is True
                and type(idle.get("stayAwake")) is bool
                and idle.get("enabled") is (not idle["stayAwake"])))
            if matched and lock.get("passwordPam") is True and idle_ready: return
        except (RuntimeError,ValueError,subprocess.TimeoutExpired): pass
        time.sleep(.1)
    raise RuntimeError("running lock/idle revision was not confirmed")


def restart_unlocked(runner):
    ensure_unlocked(runner)
    runner(["omarchy","restart","shell"])


def write_atomic(path, data, mode):
    fd, name = tempfile.mkstemp(prefix=".codex-idle-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as target: target.write(data); target.flush(); os.fsync(target.fileno())
        os.chmod(name, mode); os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def save_state(backup, state):
    write_atomic(backup / "state.json", (json.dumps(state, indent=2) + "\n").encode(), 0o600)


def expected_enabled(original, plugin_id, source="omarchy.lock"):
    """Допустимое преобразование pinned PluginRegistry.setEnabled без иных правок."""
    data = json.loads(original)
    if not isinstance(data.get("bar"), dict): data["bar"] = {}
    bar = data["bar"]
    if not isinstance(bar.get("layout"), dict): bar["layout"] = {}
    for name in ("left", "center", "right"):
        if not isinstance(bar["layout"].get(name), list): bar["layout"][name] = []
    if not isinstance(data.get("plugins"), list): data["plugins"] = []
    data["plugins"].append({"id": plugin_id})
    disabled = [value for value in data.get("disabledPlugins", []) if value != plugin_id]
    data["disabledPlugins"] = disabled + [source]
    data["cloneSourceRestores"] = [value for value in data.get("cloneSourceRestores", []) if value != plugin_id] + [plugin_id]
    return data


def install(package_path, home, runner=run, on_backup=None):
    package=verify_package(package_path)
    if not re.fullmatch(r"[0-9a-f]{64}",package.get("runtime_revision","")): raise ValueError("package lacks runtime identity; rebuild it")
    units=package_units(package_path,package)
    check_runtime(package,runner);ensure_unlocked(runner)
    config=home/".config/omarchy/shell.json";plugins=home/".config/omarchy/plugins"
    no_symlinks(config)
    for unit in units:
        target=plugins/unit["id"];no_symlinks(target)
        if target.exists():raise ValueError("target already exists: "+unit["id"])
    original=config.read_bytes();original_mode=stat.S_IMODE(config.stat().st_mode);data=json.loads(original)
    sources={unit["source"] for unit in units}
    if sources.intersection(data.get("disabledPlugins",[])):raise ValueError("stock lock/idle disabled or replaced")
    for entry in data.get("plugins",[]):
        plugin_id=entry.get("id") if isinstance(entry,dict) else entry
        if not isinstance(plugin_id,str) or not re.fullmatch(r"[a-zA-Z0-9._-]+",plugin_id):raise ValueError("unsupported plugin entry")
        manifest=plugins/plugin_id/"manifest.json"
        if manifest.is_file() and json.loads(manifest.read_text()).get("omarchy",{}).get("clonedFrom") in sources:raise ValueError("another lock/idle clone is active")
    prefixes=config_prefixes(original,units)
    backup_root=home/".local/state/omarchy-codex-idle/backups"
    no_symlinks(backup_root);backup_root.mkdir(parents=True,exist_ok=True,mode=0o700)
    backup=backup_root/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-")+uuid.uuid4().hex[:12]);backup.mkdir(mode=0o700)
    write_atomic(backup/"shell.json.before",original,0o600);shutil.copytree(package_path,backup/"package")
    state=dict(schema_version=1,id=package["id"],home=str(home),config=str(config),target=str(plugins/package["id"]),before_sha256=digest(original),before_mode=original_mode,phase="prepared",post_sha256=None)
    save_state(backup,state);plugins.mkdir(parents=True,exist_ok=True);staging=[]
    try:
        if on_backup is not None:on_backup(backup)
        if verify_package(backup/"package")["build_id"]!=package["build_id"]:raise ValueError("package changed while copying")
        for unit in units:
            stage=plugins/(".codex-idle-stage-"+uuid.uuid4().hex);staging.append(stage)
            shutil.copytree(unit["path"],stage);verify_unit(stage,unit)
        if digest(config.read_bytes())!=state["before_sha256"]:raise ValueError("configuration changed before install")
        for unit,stage in zip(units,staging):
            target=plugins/unit["id"]
            if target.exists() or target.is_symlink():raise ValueError("target appeared during install")
            stage.rename(target)
        runner(["omarchy","shell","shell","rescanPlugins"])
        for _ in range(40):
            found=json.loads(runner(["omarchy","plugin","list","--json"]))
            if all(any(p.get("id")==u["id"] for p in found) for u in units):break
            time.sleep(0.05)
        else:raise RuntimeError("plugins were not discovered")
        expected_sha=state["before_sha256"]
        for index,unit in enumerate(units):
            if digest(config.read_bytes())!=expected_sha:raise ValueError("configuration changed before enable")
            ensure_unlocked(runner)
            runner(["omarchy","plugin","enable",unit["id"]])
            current=config.read_bytes()
            if json.loads(current)!=prefixes[index+1]:raise ValueError("unexpected changes during enable")
            expected_sha=digest(current)
            state.update(phase="enabling",enabled_count=index+1,post_sha256=expected_sha);save_state(backup,state)
        enabled=json.loads(runner(["omarchy","plugin","list","--json"]))
        if not all(any(p.get("id")==u["id"] and p.get("enabled") is True for p in enabled) for u in units):raise RuntimeError("enable not confirmed")
        restart_unlocked(runner)
        confirm_runtime(runner,package["runtime_revision"],bool(package.get("companion")))
        state.update(phase="installed");save_state(backup,state);return backup
    except BaseException as error:
        current=config.read_bytes()
        if current==original:
            # Validate every owned payload before moving any of them.
            movable=[u for u in units if (plugins/u["id"]).exists()]
            try:
                for unit in movable:verify_unit(plugins/unit["id"],unit)
                for unit in movable:(plugins/unit["id"]).rename(backup/("unactivated-"+unit["suffix"]))
                state["phase"]="failed-before-config-change"
            except (OSError,ValueError):state["phase"]="needs-recovery"
        else:state["phase"]="needs-recovery"
        state["observed_failure_sha256"]=digest(current);save_state(backup,state)
        raise RuntimeError("installation incomplete; recovery record: "+str(backup/"state.json")) from error
    finally:
        for stage in staging:
            if stage.exists():shutil.rmtree(stage)


def restore(backup, home, runner=run, emergency=False):
    no_symlinks(backup);state=json.loads((backup/"state.json").read_text())
    if backup.parent!=home/".local/state/omarchy-codex-idle/backups" or state.get("home")!=str(home):raise ValueError("backup belongs to another profile")
    package=verify_package(backup/"package");units=package_units(backup/"package",package)
    config=home/".config/omarchy/shell.json";plugins=home/".config/omarchy/plugins"
    if state.get("config")!=str(config) or state.get("target")!=str(plugins/package["id"]):raise ValueError("backup paths differ")
    no_symlinks(config)
    for unit in units:no_symlinks(plugins/unit["id"]);no_symlinks(backup/("restored-"+unit["suffix"]))
    if not emergency:ensure_unlocked(runner)
    before=(backup/"shell.json.before").read_bytes()
    if digest(before)!=state["before_sha256"]:raise ValueError("backup configuration changed")
    phase=state.get("phase")
    if phase in ("installed","enabling","needs-recovery"):
        expected=state.get("observed_failure_sha256") if phase=="needs-recovery" else state.get("post_sha256")
        current=config.read_bytes()
        if not expected or digest(current)!=expected:raise ValueError("configuration changed after install; refusing overwrite")
        if json.loads(current) not in config_prefixes(before,units):raise ValueError("unexpected enable changes; manual reconciliation required")
        for unit in units:
            if (backup/("restored-"+unit["suffix"])).exists():raise ValueError("restore destination already exists")
            verify_unit(plugins/unit["id"],unit)
        state.update(phase="restoring",restore_from_sha256=expected);save_state(backup,state)
    elif phase not in ("restoring","restored-pending-reload","restored"):raise ValueError("install not confirmed; inspect recovery state")
    if state["phase"]=="restoring":
        current=config.read_bytes()
        if digest(current) not in (state["restore_from_sha256"],state["before_sha256"]):raise ValueError("configuration changed during restore")
        for unit in units:
            target=plugins/unit["id"];archived=backup/("restored-"+unit["suffix"])
            if target.exists() and archived.exists():raise ValueError("both restore payload paths exist")
            verify_unit(target if target.exists() else archived,unit)
        if digest(current)!=state["before_sha256"]:write_atomic(config,before,state["before_mode"])
        for unit in units:
            target=plugins/unit["id"]
            if target.exists():target.rename(backup/("restored-"+unit["suffix"]))
        state["phase"]="restored-pending-reload";save_state(backup,state)
    if digest(config.read_bytes())!=state["before_sha256"]:raise ValueError("configuration changed after restore")
    for unit in units:
        target=plugins/unit["id"]
        if target.exists() or target.is_symlink():raise ValueError("plugin target reappeared")
        verify_unit(backup/("restored-"+unit["suffix"]),unit)
    # Drop retained services and cached components before claiming restoration.
    if emergency: runner(["omarchy","restart","shell"])
    else: restart_unlocked(runner)
    confirm_runtime(runner,companion=bool(package.get("companion")))
    state["phase"]="restored";save_state(backup,state);return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    add = sub.add_parser("install"); add.add_argument("--package", required=True, type=Path)
    remove = sub.add_parser("restore"); remove.add_argument("--backup", required=True, type=Path); remove.add_argument("--emergency", action="store_true")
    args = parser.parse_args(); home = Path.home()
    if args.action == "install": print(json.dumps({"backup":str(install(args.package.absolute(), home))}))
    else: print(json.dumps({"phase":restore(args.backup.absolute(), home, emergency=args.emergency)["phase"]}))


if __name__ == "__main__": main()
