"""Render a synthetic GIF from the real QML Dashboard, without reading Codex chats."""

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent
FRAMES = 210
FPS = 20
WIDTH = 1200

# Promo-only translations. The product UI files and installed Russian UI stay untouched.
DISPLAY_TEXT = {
    "Dashboard.qml": {
        "Поиск действующих чатов…": "Scanning active chats…",
        "Поиск чатов…": "Scanning chats…",
        "Нет действующих чатов": "No active chats",
        "Чаты завершены": "Chats completed",
        "Источник не полностью доступен": "Source not fully available",
        "Работа продолжается": "Work in progress",
        "Есть ожидание ответа": "Waiting for a reply",
        "Чатов: ": "Chats: ",
        "Экран заблокирован": "Screen locked",
        "Заставка · экран не заблокирован": "Screensaver · screen unlocked",
        "Предпросмотр": "Preview",
        "Ввод пароля  ↗": "Enter password  ↗",
        "Любая клавиша — вернуться": "Press any key to return",
        "Живой контекст": "Live context",
    },
    "ContextView.qml": {
        "Ожидание источника": "Waiting for source",
        "Фрагменты мыслей / публичные события": "Public context / session events",
        "Ожидание ответа · вопросов: ": "Waiting for reply · questions: ",
        "Последний контекст · без обновлений ": "Last context · no updates for ",
        '" с"': '" s"',
        "Чат завершён": "Chat completed",
        "Публичные сообщения, действия и результаты": "Public messages, actions and results",
    },
    "ContextCard.qml": {
        "событие ": "event ",
        "Вывод": "Output",
        "код выхода неизвестен": "exit code unknown",
    },
    "VisualStyle.js": {
        "Состояние неизвестно": "State unknown",
        "Ждёт ответа": "Waiting for reply",
        "Потеря связи": "Connection lost",
        "Работает": "Working",
        "Завершено": "Completed",
        "Codex · результат": "Codex · result",
        "Codex · сообщение": "Codex · update",
        "Изменение файла": "File change",
        "Codex · вопрос": "Codex · question",
        "Ты · ответ": "You · reply",
    },
    "StreamModel.js": {
        "Изменения файлов": "File changes",
        "Ответ пользователя": "User reply",
        "Результат": "Result",
        "Ход работы": "Progress",
        "Команда": "Command",
        "Вопрос": "Question",
    },
}


def stage_english_qml(temp: Path) -> Path:
    shutil.copytree(ROOT / "ui", temp / "ui")
    target = temp / "promo-capture.qml"
    shutil.copy2(ROOT / "promo-capture.qml", target)
    for filename, translations in DISPLAY_TEXT.items():
        path = temp / "ui" / filename
        source = path.read_text()
        for original, translated in sorted(translations.items(), key=lambda item: -len(item[0])):
            if original not in source:
                raise RuntimeError(f"outdated promo translation: {filename}: {original}")
            source = source.replace(original, translated)
        path.write_text(source)
    for path in list((temp / "ui").glob("*.qml")) + list((temp / "ui").glob("*.js")) + [target]:
        if re.search(r"[А-Яа-яЁё]", path.read_text()):
            raise RuntimeError(f"untranslated promo text in {path.name}")
    return target


def run(command, *, env=None):
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise RuntimeError(f"{' '.join(command)} failed:\n{result.stdout[-3000:]}\n{result.stderr[-3000:]}")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    output = args.out.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="endless-promo-") as temporary:
        temp = Path(temporary)
        for name in ("runtime", "config", "data", "cache", "state", "frames"):
            (temp / name).mkdir(mode=0o700)
        env = os.environ.copy()
        env.pop("WAYLAND_DISPLAY", None)
        env.update({
            "HOME": str(temp),
            "XDG_RUNTIME_DIR": str(temp / "runtime"),
            "XDG_CONFIG_HOME": str(temp / "config"),
            "XDG_DATA_HOME": str(temp / "data"),
            "XDG_CACHE_HOME": str(temp / "cache"),
            "XDG_STATE_HOME": str(temp / "state"),
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QPA_PLATFORMTHEME": "generic",
            "QT_QUICK_BACKEND": "software",
            "ENDLESS_PROMO_FRAMES": str(temp / "frames"),
        })
        qml_source = stage_english_qml(temp)
        qml = run(["qs", "-p", str(qml_source)], env=env)
        frames = sorted((temp / "frames").glob("frame-*.png"))
        if len(frames) != FRAMES or f"PROMO_FRAMES {FRAMES}" not in qml.stdout + qml.stderr:
            raise RuntimeError(f"incomplete QML capture: {len(frames)} frames\n{qml.stdout[-2000:]}\n{qml.stderr[-2000:]}")
        palette = temp / "palette.png"
        source = str(temp / "frames" / "frame-%03d.png")
        common = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(FPS), "-i", source]
        run(common + ["-vf", f"scale={WIDTH}:-1:flags=lanczos,palettegen=max_colors=112:reserve_transparent=0", str(palette)])
        run(common + ["-i", str(palette), "-lavfi",
            f"scale={WIDTH}:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4",
            "-loop", "0", str(output)])
    print(f"{output} ({output.stat().st_size} bytes, {FRAMES} frames, {FPS} fps)")


if __name__ == "__main__":
    main()
