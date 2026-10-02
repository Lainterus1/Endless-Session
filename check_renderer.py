"""Проверка настоящего QML renderer и pipe, с неизменяемыми отчётами."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET


def inputs():
    names = ["source_probe.py", "test_source_probe.py", "stream_context.py", "test_stream_context.py", "check_renderer.py", "transport-test.qml", "tests/transport_fixture.py"]
    names += ["discovery.py", "theme.py", "watch_context.py", "test_discovery.py"]
    names += [str(p) for base in ("ui", "tests/qml") for p in sorted(Path(base).glob("*")) if p.is_file()]
    return {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in names}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    before = inputs()
    started = datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix="oc-idle-") as runtime:
        env = os.environ.copy()
        env.update(QT_QPA_PLATFORM="offscreen", QT_QPA_PLATFORMTHEME="generic", QT_STYLE_OVERRIDE="Fusion", QT_QUICK_BACKEND="software", XDG_RUNTIME_DIR=runtime, XDG_CACHE_HOME=runtime)
        commands = [
            ["python3", "-m", "unittest", "-v", "test_stream_context", "test_discovery"],
            ["/usr/lib/qt6/bin/qmltestrunner", "-input", "tests/qml", "-o", str(args.out / "qml.xml") + ",junitxml", "-o", "-,txt"],
            ["qs", "-p", str(Path("transport-test.qml").resolve()), "--no-color"]]
        results = []
        for command in commands:
            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
            results.append(dict(command=command, exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr))
        with (args.out / "commands.json").open("x") as file: json.dump(results, file, ensure_ascii=False, indent=2)
        try: qml = ET.parse(args.out / "qml.xml").getroot()
        except (ET.ParseError, OSError): qml = ET.Element("missing-report")
        cases = [{"id": node.attrib.get("name"), "passed": not any(node.find(tag) is not None for tag in ("failure", "error", "skipped"))} for node in qml.iter("testcase")]
        transport = None
        for line in results[2]["stdout"].splitlines():
            if "TRANSPORT_RESULT " in line: transport = json.loads(line.split("TRANSPORT_RESULT ", 1)[1])
        after = inputs()
        passed = all(r["exit_code"] == 0 for r in results) and len(cases) >= 8 and all(c["passed"] for c in cases) and bool(transport and transport["passed"]) and before == after
        report = dict(command="python3 check_renderer.py --out " + str(args.out), started_at=started, finished_at=datetime.now(timezone.utc).isoformat(), input_sha256=before,
            inputs_unchanged=before == after, results=results, qml_cases=cases, transport=transport, passed=passed)
        with (args.out / "report.json").open("x") as file: json.dump(report, file, ensure_ascii=False, indent=2)
        print(json.dumps({"passed": passed, "qml_cases": cases, "transport": transport, "report": str(args.out / "report.json")}))
        return 0 if passed else 1


if __name__ == "__main__": raise SystemExit(main())
