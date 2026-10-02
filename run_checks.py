"""Запускает проверки прототипа и сохраняет неизменяемый машинный отчёт."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import time
import unittest


class Result(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cases = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.cases.append({"id": test.id(), "status": "passed"})

    def addFailure(self, test, error):
        super().addFailure(test, error)
        self.cases.append({"id": test.id(), "status": "failed"})

    def addError(self, test, error):
        super().addError(test, error)
        self.cases.append({"id": test.id(), "status": "error"})

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.cases.append({"id": test.id(), "status": "skipped", "reason": reason})


def hashes():
    return {name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in ("source_probe.py", "test_source_probe.py", "run_checks.py")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    before = hashes()
    started = datetime.now(timezone.utc).isoformat()
    clock = time.monotonic()
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromName("test_source_probe")
    result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=Result).run(suite)
    after = hashes()
    passed = result.wasSuccessful() and result.testsRun > 0 and not result.skipped and before == after
    report = {"command": "python3 run_checks.py --out " + str(args.out), "started_at": started,
              "finished_at": datetime.now(timezone.utc).isoformat(), "duration_seconds": time.monotonic() - clock,
              "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "skipped": len(result.skipped), "cases": result.cases, "input_sha256": before,
              "inputs_unchanged": before == after, "output": stream.getvalue(), "passed": passed}
    with args.out.open("x") as target:
        json.dump(report, target, ensure_ascii=False, indent=2); target.write("\n")
    print(json.dumps({"passed": passed, "tests_run": result.testsRun, "report": str(args.out)}))
    return 0 if passed else 1


if __name__ == "__main__": raise SystemExit(main())
