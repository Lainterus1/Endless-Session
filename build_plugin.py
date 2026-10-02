"""Собирает полный клон lock в новом каталоге; установленную систему не меняет."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
from build_prelock import idle_source, patch_lock, ORIGIN as IDLE_ORIGIN

ROOT = Path(__file__).resolve().parent
FILES = ["source_probe.py", "stream_context.py", "discovery.py", "theme.py", "watch_context.py", "IdleContext.qml"]


def replace_once(text, old, new):
    if text.count(old) != 1: raise ValueError("incompatible lock source anchor")
    return text.replace(old, new, 1)


def tree_hashes(directory):
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.rglob("*")) if p.is_file() and p.relative_to(directory) != Path("package.json")}


def build(out, plugin_id, origin):
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*\.(?:codex-idle|endless-session)", plugin_id): raise ValueError("invalid plugin id")
    compatibility = json.loads((ROOT / "lock-compatibility.json").read_text())
    for name, expected in compatibility["sha256"].items():
        if hashlib.sha256((origin / name).read_bytes()).hexdigest() != expected: raise ValueError("unsupported installed lock revision: " + name)
    service = (origin / "Service.qml").read_text()
    service = replace_once(service, "  property bool lockRequested: false", '''  IdleContext {
    id: codexContext
    locked: root.lockRequested
    authenticatingPassword: root.authenticatingPassword
    onWakeRequested: root.runWake(false)
    onReleaseRequested: function(lossTimeout) {
      if (!root.lockRequested || root.authenticatingPassword) return
      if (lossTimeout) root.runBlank()
      else root.armBlankTimer()
    }
  }

  property bool lockRequested: false''')
    service = replace_once(service, "  function armBlankTimer() {\n", "  function armBlankTimer() {\n    if (root.lockRequested && codexContext.hold) { idleBlankTimer.stop(); return }\n")
    service = replace_once(service, "  function runWake() {\n", "  function runWake(userActivity) {\n    if (userActivity !== false && root.lockRequested) codexContext.manualWake()\n")
    service = replace_once(service, "  function runBlank() {\n", "  function runBlank() {\n    if (root.lockRequested && (codexContext.hold || root.authenticatingPassword)) return\n")
    service = replace_once(service, "        id: lockView\n", "        id: lockView\n        codexHub: codexContext.hub\n        codexActive: root.lockRequested\n")
    service = replace_once(service, "      return JSON.stringify({\n        locked: root.locked,", "      return JSON.stringify({\n        codexCollectorPid: codexContext.collectorPid,\n        codexRunning: codexContext.collectorRunning,\n        codexHold: codexContext.hold,\n        codexChats: codexContext.hub.dashboards.length ? codexContext.hub.dashboards[0].monitored.length : 0,\n        locked: root.locked,")
    view = (origin / "LockView.qml").read_text()
    view = replace_once(view, "import qs.Ui\n", 'import qs.Ui\nimport "ui"\nimport "ui/NativeTheme.js" as NativeTheme\n')
    view = replace_once(view, '  property string backgroundPath: ""', '''  property var codexHub: null
  property bool codexActive: false
  property bool codexAuthVisible: false
  property string backgroundPath: ""''')
    view = replace_once(view, "    MouseArea {\n", '''    Loader {
      anchors.fill: parent
      z: 1
      active: root.codexActive && root.codexHub !== null
      sourceComponent: Component {
        Dashboard {
          id: codexDashboard
          rotate: false
          mode: "locked"
          onPasswordRequested: { root.codexAuthVisible = true; root.forcePasswordFocus() }
          themeOverride: NativeTheme.normalize(Color.foreground, Color.background, Color.accent, Style.font.family)
          Component.onCompleted: root.codexHub.attach(codexDashboard)
          Component.onDestruction: if (root.codexHub) root.codexHub.detach(codexDashboard)
        }
      }
    }

    MouseArea {
''')
    view = replace_once(view, "    BorderSurface {\n", '''    Rectangle {
      anchors.fill: parent
      z: 2
      visible: root.codexActive && root.codexAuthVisible
      color: Qt.rgba(Color.background.r, Color.background.g, Color.background.b, 0.97)
    }
    Text {
      z: 3
      visible: root.codexActive && root.codexAuthVisible
      anchors.horizontalCenter: parent.horizontalCenter
      y: (parent.height - root.fieldHeight) / 2 - 40
      text: "Разблокировка"
      font.family: Style.font.family
      font.pixelSize: 11
      color: Color.foreground
    }
    Text {
      z: 3
      visible: root.codexActive && root.codexAuthVisible && !root.authenticatingPassword
      anchors.horizontalCenter: parent.horizontalCenter
      y: (parent.height + root.fieldHeight) / 2 + 25
      text: "Esc — вернуться к контексту"
      font.family: Style.font.family
      font.pixelSize: 11
      color: Color.foreground
    }
    BorderSurface {
''')
    view = replace_once(view, "      id: inputField\n", "      id: inputField\n      z: 3\n      opacity: !root.codexActive || root.codexAuthVisible ? 1 : 0\n")
    view = replace_once(view, "          if (text.length > 0) {\n", "          if (text.length > 0) {\n            if (root.codexActive) root.codexAuthVisible = true\n")
    view = replace_once(view, "          if (event.key === Qt.Key_Escape ||", "          if (event.key === Qt.Key_Escape && root.codexActive && !root.authenticatingPassword) root.codexAuthVisible = false\n          if (event.key === Qt.Key_Escape ||")
    manifest = json.loads((origin / "manifest.json").read_text())
    manifest.update(id=plugin_id, name="Endless Session", description="Контекст действующих чатов Codex на заставке и блокировке Omarchy.")
    manifest["omarchy"]["clonedFrom"] = "omarchy.lock"
    idle, idle_compatibility = idle_source(replace_once)
    service = patch_lock(service, replace_once)
    companion_id = plugin_id + "-bridge"
    idle_manifest = json.loads((IDLE_ORIGIN / "manifest.json").read_text())
    idle_manifest.update(id=companion_id, name="Endless Session — idle bridge")
    idle_manifest["omarchy"] = {"clonedFrom": "omarchy.idle"}
    out.mkdir(parents=True, exist_ok=False)
    try:
        (out / "Service.qml").write_text(service)
        (out / "LockView.qml").write_text(view)
        (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        shutil.copyfile(ROOT / "LICENSE", out / "LICENSE")
        for name in FILES: shutil.copyfile(ROOT / name, out / name)
        shutil.copytree(ROOT / "ui", out / "ui")
        shutil.copytree(ROOT / "prelock", out / "prelock")
        companion=out/"companion";companion.mkdir()
        (companion/"Service.qml").write_text(idle)
        (companion/"manifest.json").write_text(json.dumps(idle_manifest,ensure_ascii=False,indent=2)+"\n")
        shutil.copyfile(ROOT / "LICENSE", companion / "LICENSE")
        shutil.copyfile(IDLE_ORIGIN/"IdleModel.js",companion/"IdleModel.js")
        shutil.copyfile(ROOT/"prelock/CommandQueue.qml",companion/"CommandQueue.qml")
        # Hash the complete payload before inserting literal runtime identities.
        # A live manifest can change while a retained QML instance stays old.
        runtime_revision = hashlib.sha256(json.dumps(tree_hashes(out),sort_keys=True,separators=(",", ":")).encode()).hexdigest()
        for target in (out/"Service.qml",companion/"Service.qml"):
            text=target.read_text()
            text=replace_once(text,'return JSON.stringify({', 'return JSON.stringify({\n        codexRuntimeRevision: "'+runtime_revision+'",')
            target.write_text(text)
        hashes = tree_hashes(out)
        package = dict(schema_version=1, id=plugin_id, compatibility=compatibility, files=hashes,runtime_revision=runtime_revision)
        package["companion"] = {"id":companion_id,"directory":"companion","clonedFrom":"omarchy.idle","compatibility":idle_compatibility}
        package["build_id"] = hashlib.sha256(json.dumps(package, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        (out / "package.json").write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n")
        return package
    except BaseException:
        shutil.rmtree(out)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--id", default="lainterus.endless-session")
    parser.add_argument("--origin", type=Path, default=Path("/usr/share/omarchy/shell/plugins/lock"))
    args = parser.parse_args()
    result = build(args.out.resolve(), args.id, args.origin.resolve())
    print(json.dumps({"build_id":result["build_id"], "files":len(result["files"]), "path":str(args.out)}))


if __name__ == "__main__": main()
