"""Проверяемые патчи полного клона idle и hooks lock; системных записей нет."""
import hashlib
import json
from pathlib import Path

ORIGIN=Path('/usr/share/omarchy/shell/plugins/services/idle')
ROOT=Path(__file__).resolve().parent

def idle_source(replace):
    compatibility=json.loads((ROOT/'idle-compatibility.json').read_text())
    for name,expected in compatibility['sha256'].items():
        if hashlib.sha256((ORIGIN/name).read_bytes()).hexdigest()!=expected:raise ValueError('unsupported installed idle revision: '+name)
    source=(ORIGIN/'Service.qml').read_text()
    source=replace(source,'import "IdleModel.js" as IdleModel\n','import "IdleModel.js" as IdleModel\nimport "."\n')
    source=replace(source,'  property bool stayAwake: false','  property string codexCycle: ""\n  property int codexSerial: 0\n  property bool stayAwake: false')
    a=source.index('  function launchScreensaver() {');b=source.index('  function lockSystem(',a)
    source=source[:a]+'''  function launchScreensaver() {
    root.screensaverStartedThisCycle = true
    root.codexCycle = String(Date.now()) + "-" + String(++root.codexSerial)
    // A layer surface has no openwindow/class event. Its token owns this cycle.
    screensaverProcess.enqueue(["omarchy", "shell", "lock", "showCodexScreensaver", root.codexCycle])
  }

  function codexEndCycle(cycle, locked) {
    if (!root.codexCycle || cycle !== root.codexCycle) return "stale"
    if (locked) {
      screensaverTimer.stop(); lockTimer.stop(); screensaverLaunchGraceTimer.stop()
      root.idledThisCycle = false; root.screensaverStartedThisCycle = false; root.codexCycle = ""
    } else cancelIdleCycle("screensaver-dismissed")
    return "ok"
  }

'''+source[b:]
    source=replace(source,'    logEvent("lock-system", reason || "requested")','    logEvent("lock-system", reason || "requested")\n    root.codexCycle = ""')
    source=replace(source,'    logEvent("idle-cycle-cancel", reason || "requested")','''    logEvent("idle-cycle-cancel", reason || "requested")
    if (root.codexCycle) {
      hideCodexProcess.enqueue(["omarchy", "shell", "lock", "hideCodexScreensaver", root.codexCycle])
      root.codexCycle = ""
    }''')
    source=replace(source,'root.screensaverWindowCount > 0 || screensaverLaunchGraceTimer.running','root.codexCycle.length > 0 || screensaverLaunchGraceTimer.running')
    # Native ordinary-window tracking must never dismiss a layer-surface cycle.
    source=replace(source,'    if (root.screensaverWindowCount > 0) return','    if (root.codexCycle || root.screensaverWindowCount > 0) return')
    source=replace(source,'      screensaverWindows: root.screensaverWindowCount,','      screensaverWindows: root.screensaverWindowCount,\n      codexCycle: root.codexCycle,')
    source=replace(source,'''  Process {
    id: screensaverProcess
    onExited: function(exitCode, exitStatus) { root.logEvent("process-exit", "screensaver exitCode=" + exitCode + " status=" + exitStatus) }
  }''','''  CommandQueue { id: hideCodexProcess }
  CommandQueue { id: screensaverProcess }''')
    source=replace(source,'    function status(): string {','''    function codexScreensaverDismissed(cycle: string): string { return root.codexEndCycle(cycle, false) }
    function codexScreensaverLocked(cycle: string): string { return root.codexEndCycle(cycle, true) }

    function status(): string {''')
    return source,compatibility


def patch_lock(source,replace):
    source=replace(source,'import qs.Commons\n','import qs.Commons\nimport "prelock"\n')
    source=replace(source,'  IdleContext {','''  Prelock {
    id: codexPrelock
    hub: codexContext.hub
    locked: root.lockRequested
    onWakeRequested: root.runWake()
    onActiveChanged: {
      if (active) root.armBlankTimer()
      else if (!root.lockRequested) idleBlankTimer.stop()
    }
  }

  IdleContext {''')
    source=replace(source,'    locked: root.lockRequested\n    authenticatingPassword:', '    locked: root.lockRequested\n    screensaver: codexPrelock.active\n    authenticatingPassword:')
    source=replace(source,'if (!root.lockRequested || root.authenticatingPassword) return','if (!codexContext.active || root.authenticatingPassword) return')
    source=replace(source,'if (root.lockRequested && codexContext.hold)','if (codexContext.active && codexContext.hold)')
    source=replace(source,'if (userActivity !== false && root.lockRequested)','if (userActivity !== false && codexContext.active)')
    source=replace(source,'    if (lockRequested) armBlankTimer()','    if (codexContext.active) armBlankTimer()')
    source=replace(source,'if (root.lockRequested && (codexContext.hold || root.authenticatingPassword))','if (codexContext.active && (codexContext.hold || root.authenticatingPassword))')
    source=replace(source,'if (root.lockRequested && !root.authenticatingPassword) root.runBlank()','if (codexContext.active && !root.authenticatingPassword) root.runBlank()')
    source=replace(source,'    function lock(): string {','''    function showCodexScreensaver(cycle: string): string { return root.locked ? "locked" : codexPrelock.show(cycle) }
    function hideCodexScreensaver(cycle: string): string { return codexPrelock.hide(cycle) }

    function lock(): string {''')
    source=replace(source,'        codexCollectorPid:', '        codexScreensaver: codexPrelock.active,\n        codexCollectorPid:')
    source=replace(source,'codexContext.hub.dashboards.length ? codexContext.hub.dashboards[0].monitored.length : 0','codexContext.hub.monitored.length')
    return source
