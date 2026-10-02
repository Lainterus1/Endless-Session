"""Публичные снимки Observer → JSON Lines для визуальной ленты (без записи текстов)."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

from source_probe import Observer

ITEM_FIELDS = {
    "message": ("phase", "text"),
    "command": ("command", "argv", "cwd", "output", "status", "exit_code"),
    "file_change": ("changes", "status"),
    "question": ("call_id", "questions"),
    "user_reply": ("text",),
}


def public_item(item):
    kind = item.get("type")
    if kind not in ITEM_FIELDS:
        raise ValueError("unsupported public item")
    return {key: item.get(key) for key in ("id", "type", "timestamp", *ITEM_FIELDS[kind])}


class Stream:
    """Порядок берётся из Observer; при новой эпохе локальная база заменяется."""
    def __init__(self, history=8):
        self.history = history
        self.previous = {}
        self.sequence = 0

    def frame(self, snapshots):
        chats = []
        for snapshot in snapshots:
            thread = snapshot["thread_id"]
            epoch = snapshot["source_epoch"]
            previous = self.previous.get(thread)
            reset = previous is None or previous[0] != epoch
            items = [public_item(item) for item in snapshot["items"]]
            current = {item["id"]: item for item in items}
            changed = items[-self.history:] if reset else [item for item in items if previous[1].get(item["id"]) != item]
            self.previous[thread] = (epoch, current)
            name = snapshot.get("name")
            chats.append({"thread_id": thread, "name": name if isinstance(name, str) else thread,
                          "source_epoch": epoch, "status": snapshot["status"],
                          "pending_questions": snapshot["pending_questions"],
                          "reset": reset, "items": changed})
        self.sequence += 1
        return {"schema_version": 1, "sequence": self.sequence,
                "observed_at": datetime.now(timezone.utc).isoformat(), "chats": chats}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thread", required=True, action="append")
    parser.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--poll", type=float, default=0.5)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not 0 < args.poll <= 1:
        parser.error("--poll должен быть >0 и <=1 секунды")
    if len(set(args.thread)) != len(args.thread):
        parser.error("UUID не должен повторяться")
    try:
        observers = [Observer(args.codex_home, thread) for thread in args.thread]
    except ValueError:
        parser.error("--thread должен быть UUID")
    stream = Stream()
    try:
        while True:
            print(json.dumps(stream.frame([observer.poll() for observer in observers]), ensure_ascii=True), flush=True)
            if args.once:
                return 0
            time.sleep(args.poll)
    except (BrokenPipeError, KeyboardInterrupt):
        return 0


if __name__ == "__main__":
    sys.exit(main())
