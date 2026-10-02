"""Изолированный subprocess sink штатных команд; никогда не вызывает Omarchy."""
import json
from pathlib import Path
import sys

home = Path(sys.argv[1]); command = sys.argv[2:]
control = json.loads((home / "control.json").read_text()) if (home / "control.json").exists() else {}
with (home / "calls.jsonl").open("a") as log: log.write(json.dumps(command) + "\n")
if command == ["pacman","-Q","omarchy"]: print("omarchy 4.0.4-1")
elif command == ["pacman","-Q","qt6-declarative"]: print("qt6-declarative 6.11.2-1")
elif command == ["qs","--version"]: print("quickshell 0.3.1")
elif command == ["omarchy","shell","lock","isLocked"]: print("true" if control.get("locked") else "false")
elif command in [["omarchy","shell","lock","status"],["omarchy","shell","idle","status"]]:
    lock=command[2]=="lock"
    state=dict(locked=bool(control.get("locked")),requested=False,pending=bool(control.get("pending")),sessionLocked=False,secure=False,authenticating=False,passwordPam=True) if lock else dict(enabled=not bool(control.get("stay_awake")),stayAwake=bool(control.get("stay_awake")),stayAwakeStateLoaded=True)
    if (home/"runtime.json").exists():
        revision=json.loads((home/"runtime.json").read_text()).get("revision")
        if revision:state["codexRuntimeRevision"]="stale" if control.get("stale_runtime") or control.get("stale_idle") and not lock else revision
    print(json.dumps(state))
elif command in [["omarchy","shell","shell","rescanPlugins"],["omarchy","restart","shell"]]:
    if control.get("fail_reload"): sys.exit(1)
    if command==["omarchy","restart","shell"] and control.get("fail_restart"): sys.exit(1)
    if command==["omarchy","restart","shell"]:
        packages=list((home/".config/omarchy/plugins").glob("*/package.json"))
        revision=json.loads(packages[0].read_text()).get("runtime_revision") if packages else None
        if control.get("retain_runtime") and (home/"runtime.json").exists():revision=json.loads((home/"runtime.json").read_text()).get("revision")
        (home/"runtime.json").write_text(json.dumps(dict(revision=revision)))
    print("ok")
elif command == ["omarchy","plugin","list","--json"]:
    config = json.loads((home / ".config/omarchy/shell.json").read_text())
    enabled = {p["id"] for p in config.get("plugins", [])}
    items = [{"id":"omarchy.lock","enabled":"omarchy.lock" not in config.get("disabledPlugins",[])}]
    for manifest in (home / ".config/omarchy/plugins").glob("*/manifest.json"):
        if manifest.parent.name.startswith("."): continue
        entry = json.loads(manifest.read_text()); items.append({"id":entry["id"],"enabled":entry["id"] in enabled})
    print(json.dumps(items))
elif command[:3] == ["omarchy","plugin","enable"]:
    target=command[3]
    if control.get("fail_before") or control.get("fail_before_id")==target: sys.exit(1)
    path = home / ".config/omarchy/shell.json"; config=json.loads(path.read_text()); plugin=command[3]
    config.setdefault("bar",{}).setdefault("layout",{})
    for section in ("left","center","right"): config["bar"]["layout"].setdefault(section,[])
    config.setdefault("plugins",[]).append({"id":plugin})
    manifest=json.loads((home/".config/omarchy/plugins"/plugin/"manifest.json").read_text())
    config.setdefault("disabledPlugins",[]).append(manifest["omarchy"]["clonedFrom"])
    config.setdefault("cloneSourceRestores",[]).append(plugin)
    path.write_text(json.dumps(config))
    if control.get("fail_after") or control.get("fail_after_id")==target: sys.exit(1)
    print("enabled")
else: raise SystemExit("unexpected fixture command")
