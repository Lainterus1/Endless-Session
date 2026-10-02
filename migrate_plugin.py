"""Безопасная миграция установленной пары с сохранением текущего shell.json."""
from datetime import datetime, timezone
import json
from pathlib import Path
import stat
import uuid

from install_plugin import (
    check_runtime, config_prefixes, confirm_runtime, digest, ensure_unlocked,
    install, no_symlinks, package_units, restart_unlocked, restore, run,
    save_state, verify_package, verify_unit, write_atomic,
)

LEGACY_ID = "lainterus.codex-idle"
NEW_ID = "lainterus.endless-session"
STATE_ROOT = Path(".local/state/omarchy-codex-idle")
CONTROL_KEYS = ("plugins", "disabledPlugins", "cloneSourceRestores")


def _record(record):
    no_symlinks(record)
    return json.loads((record / "state.json").read_text())


def _save(record, state):
    save_state(record, state)


def _paths(home):
    return home / ".config/omarchy/shell.json", home / ".config/omarchy/plugins"


def _legacy_preflight(legacy_backup, new_package, home, runner):
    ensure_unlocked(runner)
    no_symlinks(legacy_backup)
    if legacy_backup.parent != home / STATE_ROOT / "backups":
        raise ValueError("legacy backup belongs to another profile")
    old_state = json.loads((legacy_backup / "state.json").read_text())
    if old_state.get("home") != str(home) or old_state.get("id") != LEGACY_ID or old_state.get("phase") != "installed":
        raise ValueError("legacy installation is not confirmed")
    old_package = verify_package(legacy_backup / "package")
    if old_package["id"] != LEGACY_ID or old_package.get("companion", {}).get("id") != LEGACY_ID + "-bridge":
        raise ValueError("unsupported legacy pair")
    candidate = verify_package(new_package)
    if candidate["id"] != NEW_ID or candidate.get("companion", {}).get("id") != NEW_ID + "-bridge":
        raise ValueError("Endless Session pair required")
    check_runtime(old_package, runner)
    check_runtime(candidate, runner)
    confirm_runtime(runner, old_package["runtime_revision"], companion=True)
    config, plugins = _paths(home)
    no_symlinks(config)
    old_bytes = config.read_bytes()
    previous = json.loads((legacy_backup / "shell.json.before").read_bytes())
    expected = config_prefixes((legacy_backup / "shell.json.before").read_bytes(),
                               package_units(legacy_backup / "package", old_package))[-1]
    current = json.loads(old_bytes)
    for key in CONTROL_KEYS:
        if current.get(key) != expected.get(key):
            raise ValueError("legacy plugin configuration changed: " + key)
    for unit in package_units(legacy_backup / "package", old_package):
        verify_unit(plugins / unit["id"], unit)
    for unit in package_units(new_package, candidate):
        target = plugins / unit["id"]
        no_symlinks(target)
        if target.exists():
            raise ValueError("new plugin target already exists")
    for key in CONTROL_KEYS:
        if key in previous:
            current[key] = previous[key]
        else:
            current.pop(key, None)
    stock_bytes = (json.dumps(current, ensure_ascii=False, indent=2) + "\n").encode()
    return old_package, old_bytes, stock_bytes


def migrate(legacy_backup, new_package, home, runner=run):
    old_package, old_bytes, stock_bytes = _legacy_preflight(legacy_backup, new_package, home, runner)
    config, plugins = _paths(home)
    root = home / STATE_ROOT / "migrations"
    no_symlinks(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    record = root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12])
    record.mkdir(mode=0o700)
    write_atomic(record / "shell.json.old", old_bytes, 0o600)
    write_atomic(record / "shell.json.stock", stock_bytes, 0o600)
    state = {
        "schema_version": 1, "home": str(home), "legacy_backup": str(legacy_backup),
        "old_sha256": digest(old_bytes), "old_mode": stat.S_IMODE(config.stat().st_mode),
        "stock_sha256": digest(stock_bytes), "new_backup": None, "phase": "prepared",
    }
    _save(record, state)
    try:
        if digest(config.read_bytes()) != state["old_sha256"]:
            raise ValueError("configuration changed before migration")
        write_atomic(config, stock_bytes, state["old_mode"])
        state["phase"] = "stock-written"
        _save(record, state)
        old_units = package_units(legacy_backup / "package", old_package)
        for unit in old_units:
            verify_unit(plugins / unit["id"], unit)
        for unit in old_units:
            (plugins / unit["id"]).rename(record / ("legacy-" + unit["suffix"]))
        state["phase"] = "legacy-parked"
        _save(record, state)
        restart_unlocked(runner)
        confirm_runtime(runner, companion=True)

        def registered(backup):
            state["new_backup"] = str(backup)
            state["phase"] = "new-prepared"
            _save(record, state)

        backup = install(new_package, home, runner, on_backup=registered)
        state["new_backup"] = str(backup)
        state["phase"] = "migrated"
        _save(record, state)
        return record
    except BaseException:
        state["phase"] = "needs-recovery"
        _save(record, state)
        try:
            restore_migration(record, home, runner)
        except BaseException as recovery_error:
            raise RuntimeError("migration incomplete; recover from " + str(record)) from recovery_error
        raise RuntimeError("migration failed; legacy pair restored; record: " + str(record))


def restore_migration(record, home, runner=run):
    state = _record(record)
    if record.parent != home / STATE_ROOT / "migrations" or state.get("home") != str(home):
        raise ValueError("migration record belongs to another profile")
    legacy_backup = Path(state["legacy_backup"])
    if legacy_backup.parent != home / STATE_ROOT / "backups":
        raise ValueError("invalid legacy backup")
    old_package = verify_package(legacy_backup / "package")
    if old_package["id"] != LEGACY_ID:
        raise ValueError("invalid legacy package")
    old_bytes = (record / "shell.json.old").read_bytes()
    stock_bytes = (record / "shell.json.stock").read_bytes()
    if digest(old_bytes) != state["old_sha256"] or digest(stock_bytes) != state["stock_sha256"]:
        raise ValueError("migration configuration backup changed")
    config, plugins = _paths(home)
    no_symlinks(config)
    ensure_unlocked(runner)
    if state.get("phase") == "legacy-restored":
        if digest(config.read_bytes()) != state["old_sha256"] or stat.S_IMODE(config.stat().st_mode) != state["old_mode"]:
            raise ValueError("legacy config changed after restore")
        for unit in package_units(legacy_backup / "package", old_package):
            verify_unit(plugins / unit["id"], unit)
        confirm_runtime(runner, old_package["runtime_revision"], companion=True)
        return state
    old_units = package_units(legacy_backup / "package", old_package)
    for unit in old_units:
        target = plugins / unit["id"]
        archived = record / ("legacy-" + unit["suffix"])
        no_symlinks(target)
        no_symlinks(archived)
        if target.exists() and archived.exists():
            raise ValueError("both legacy payload locations exist")
        verify_unit(target if target.exists() else archived, unit)
    new_backup = Path(state["new_backup"]) if state.get("new_backup") else None
    if new_backup:
        if new_backup.parent != home / STATE_ROOT / "backups":
            raise ValueError("invalid new backup")
        new_state = json.loads((new_backup / "state.json").read_text())
        if new_state.get("id") != NEW_ID:
            raise ValueError("invalid new installation")
        if new_state.get("phase") == "restored":
            new_package = verify_package(new_backup / "package")
            for unit in package_units(new_backup / "package", new_package):
                if (plugins / unit["id"]).exists():
                    raise ValueError("new target reappeared after restore")
                verify_unit(new_backup / ("restored-" + unit["suffix"]), unit)
        elif new_state.get("phase") != "failed-before-config-change":
            restore(new_backup, home, runner)
        else:
            if digest(config.read_bytes()) != new_state["before_sha256"]:
                raise ValueError("configuration changed after failed install")
            for unit in package_units(new_backup / "package", verify_package(new_backup / "package")):
                if (plugins / unit["id"]).exists():
                    raise ValueError("new target remains after failed install")
    current_sha = digest(config.read_bytes())
    if current_sha not in (state["old_sha256"], state["stock_sha256"]):
        raise ValueError("configuration changed during migration; refusing overwrite")
    for unit in old_units:
        target = plugins / unit["id"]
        archived = record / ("legacy-" + unit["suffix"])
        no_symlinks(target)
        no_symlinks(archived)
        if target.exists() and archived.exists():
            raise ValueError("both legacy payload locations exist")
        verify_unit(target if target.exists() else archived, unit)
    state["phase"] = "legacy-restoring"
    _save(record, state)
    for unit in old_units:
        target = plugins / unit["id"]
        archived = record / ("legacy-" + unit["suffix"])
        if archived.exists():
            archived.rename(target)
    if current_sha != state["old_sha256"]:
        write_atomic(config, old_bytes, state["old_mode"])
    if digest(config.read_bytes()) != state["old_sha256"] or stat.S_IMODE(config.stat().st_mode) != state["old_mode"]:
        raise ValueError("legacy configuration not restored exactly")
    restart_unlocked(runner)
    confirm_runtime(runner, old_package["runtime_revision"], companion=True)
    state["phase"] = "legacy-restored"
    _save(record, state)
    return state
