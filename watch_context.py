"""Автоматический поток всех действующих локальных чатов и текущей темы."""
import argparse
import json
from pathlib import Path
import threading
import time

from discovery import Discovery, Worker
from stream_context import Stream
from theme import Theme, DEFAULT


class ThemeWorker:
    def __init__(self, theme):
        self.theme = theme
        self.latest = dict(DEFAULT)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        while not self.stop.is_set():
            self.latest = self.theme.read()
            self.stop.wait(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--theme-home", type=Path, default=Path.home())
    args = parser.parse_args()
    worker = Worker(Discovery(args.codex_home.resolve()))
    theme = ThemeWorker(Theme(args.theme_home))
    worker.start(); theme.thread.start()
    stream = Stream()
    try:
        while True:
            state, count, snapshots = worker.snapshot()
            frame = stream.frame(snapshots)
            # Повторное включение того же UUID обязательно начинает reset.
            present = {snap["thread_id"] for snap in snapshots}
            stream.previous = {key: value for key, value in stream.previous.items() if key in present}
            frame.update(discovery=state, unknown_count=count, theme=theme.latest)
            print(json.dumps(frame, ensure_ascii=True), flush=True)
            time.sleep(0.5)
    except (BrokenPipeError, KeyboardInterrupt): pass
    finally: worker.stop.set(); theme.stop.set()


if __name__ == "__main__": main()
