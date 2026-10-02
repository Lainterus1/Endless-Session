"""Изолированная проверка синтетической QML-галереи и её снимков."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent
INPUTS = [
    "check_storybook.py", "storybook.qml", "storybook/Fixtures.js", "storybook/StoryButton.qml",
    "ui/Dashboard.qml", "ui/ContextView.qml", "ui/ContextLane.qml", "ui/ContextCard.qml",
    "ui/FrameStore.js", "ui/StreamModel.js", "ui/VisualStyle.js",
]
EXPECTED_STATUS = {
    "scan": [], "empty": [], "single": ["working"],
    "pair": ["working", "waiting_input"],
    "triple": ["working", "working", "idle"],
    "quad": ["working", "working", "waiting_input", "working"],
    "pages": ["working", "working", "working", "working", "working", "waiting_input", "working"],
    "unknown": ["unknown"], "loss": ["disconnected"], "error": ["working"],
    "done": ["idle"], "burst": ["working"],
}
CASES = [
    ("scan", 0, 0, {}),
    ("empty", 0, 0, {}),
    ("single", 1, 1, {}),
    ("pair", 2, 2, {}),
    ("triple", 3, 3, {}),
    ("quad", 4, 4, {}),
    ("pages-first", 7, 4, {"OC_STORYBOOK_STORY": "pages"}),
    ("pages-second", 7, 3, {"OC_STORYBOOK_STORY": "pages", "OC_STORYBOOK_PAGE": "1"}),
    ("unknown", 1, 1, {}),
    ("loss", 1, 1, {}),
    ("error", 1, 1, {}),
    ("done", 1, 1, {}),
    ("burst-long", 1, 1, {"OC_STORYBOOK_STORY": "burst", "OC_STORYBOOK_STEPS": "3"}),
    ("burst", 1, 1, {"OC_STORYBOOK_STEPS": "9", "OC_STORYBOOK_THEME": "light",
                      "OC_STORYBOOK_WIDTH": "820", "OC_STORYBOOK_MODE": "locked",
                      "OC_STORYBOOK_PASSWORD": "1"}),
    ("interaction", 1, 1, {"OC_STORYBOOK_STORY": "burst", "OC_STORYBOOK_SELFTEST": "1"}),
    ("motion", 1, 1, {"OC_STORYBOOK_STORY": "burst", "OC_STORYBOOK_MOTION_TEST": "1"}),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    def fingerprints():
        return {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in INPUTS}
    before = fingerprints()
    results = []
    with tempfile.TemporaryDirectory(prefix="oc-storybook-") as temporary:
        home = Path(temporary)
        for directory in ("runtime", "config", "data", "cache", "state"):
            (home / directory).mkdir(mode=0o700)
        for name, count, visible, overrides in CASES:
            image = out / (name + ".png")
            env = os.environ.copy()
            env.pop("WAYLAND_DISPLAY", None)
            for key in list(env):
                if key.startswith("OC_STORYBOOK_"):
                    del env[key]
            env.update({
                "HOME": str(home),
                "XDG_RUNTIME_DIR": str(home / "runtime"),
                "XDG_CONFIG_HOME": str(home / "config"),
                "XDG_DATA_HOME": str(home / "data"),
                "XDG_CACHE_HOME": str(home / "cache"),
                "XDG_STATE_HOME": str(home / "state"),
                "QT_QPA_PLATFORM": "offscreen",
                "QT_QPA_PLATFORMTHEME": "generic",
                "QT_QUICK_BACKEND": "software",
                "OC_STORYBOOK_STORY": name.split("-")[0],
                "OC_STORYBOOK_CAPTURE": str(image),
            })
            env.update(overrides)
            run = subprocess.run(["qs", "-p", str(ROOT / "storybook.qml")], cwd=ROOT,
                                 env=env, capture_output=True, text=True, timeout=12)
            output = run.stdout + run.stderr
            match = re.search(r"STORYBOOK_STATE (\{[^\r\n]+\})", output)
            capture = "STORYBOOK_CAPTURE true" in output
            state = json.loads(match.group(1)) if match else None
            motion_info = None
            expected_story = "burst" if name in ("interaction", "motion") else name.split("-")[0]
            expected_status = ["idle"] if name == "burst" else EXPECTED_STATUS[expected_story]
            passed = (run.returncode == 0 and capture and image.is_file()
                      and state is not None and state["count"] == count
                      and state["visible"] == visible and state["story"] == expected_story
                      and state["status"] == expected_status)
            if name == "pages-second":
                passed = passed and state["page"] == 1 and state["pages"] == 2
            if name == "burst":
                passed = (passed and state["step"] == 9 and state["password"]
                          and state["mode"] == "locked" and state["theme"] == "light"
                          and state["width"] == 820 and state["cards"][0] >= 5)
            if name == "interaction":
                interaction = re.search(r"STORYBOOK_INTERACTION (\{[^\r\n]+\})", output)
                passed = (passed and interaction is not None
                          and json.loads(interaction.group(1))["passed"])
            if name == "motion":
                motion = re.search(r"STORYBOOK_MOTION (\{[^\r\n]+\})", output)
                motion_info = json.loads(motion.group(1)) if motion else None
                passed = passed and motion_info is not None and motion_info["passed"]
            results.append({"case": name, "passed": bool(passed), "state": state,
                            "motion": motion_info,
                            "image": image.name if image.is_file() else None,
                            "exit_code": run.returncode,
                            "diagnostic": None if passed else output[-3000:]})
    after = fingerprints()
    report = {"command": "python3 check_storybook.py --out " + str(out),
              "input_sha256": before, "inputs_unchanged": before == after,
              "isolated_home": True, "isolated_xdg": True, "cases": results,
              "passed": before == after and all(case["passed"] for case in results)}
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"passed": report["passed"], "cases": len(results),
                      "failed": [case["case"] for case in results if not case["passed"]],
                      "report": str(out / "report.json")}, ensure_ascii=False))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
