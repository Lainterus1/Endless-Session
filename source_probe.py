#!/usr/bin/env python3
"""Пассивный прототип чтения публичных событий выбранного чата Codex."""
from __future__ import annotations

import argparse
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any
import uuid

SUPPORTED_VERSIONS = {"0.159.2"}
QUESTION_TOOLS = {"request_user_input", "request_user_input_async"}
PUBLIC_PHASES = {"commentary", "final_answer"}
IGNORED_RECORD_KINDS = {"world_state", "turn_context", "token_usage_record", "compacted",
                        "inter_agent_communication_metadata"}
IGNORED_EVENT_TYPES = {"token_count", "thread_settings_applied"}


def text_content(content: Any) -> str:
    if not isinstance(content, list):
        return ""
    return "\n".join(
        item["text"] for item in content
        if isinstance(item, dict) and item.get("type") in {"Text", "input_text", "output_text"}
        and isinstance(item.get("text"), str)
    )


@dataclass
class SessionState:
    thread_id: str
    version: str | None = None
    identity_verified: bool = False
    active_turn: str | None = None
    last_complete: str | None = None
    uncertain: bool = False
    invalid_records: int = 0
    observed_records: int = 0
    items: OrderedDict[str, dict] = field(default_factory=OrderedDict)
    pending: dict[str, dict[int, dict]] = field(default_factory=dict)
    revisions: int = 0

    def put(self, item: dict) -> None:
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            return
        if self.items.get(item_id) != item:
            self.items[item_id] = item
            self.revisions += 1

    def belongs_to_thread(self, value: dict) -> bool:
        claimed = value.get("thread_id")
        if claimed is not None and claimed != self.thread_id:
            self.uncertain = True
            return False
        return True

    def invalid(self) -> None:
        self.invalid_records += 1
        self.uncertain = True

    def accept(self, record: dict) -> None:
        self.observed_records += 1
        if not isinstance(record, dict):
            self.invalid()
            return
        payload = record.get("payload")
        kind = record.get("type")
        stamp = record.get("timestamp")
        if not isinstance(payload, dict) or not isinstance(kind, str) or not kind or (stamp is not None and not isinstance(stamp, str)):
            self.invalid()
            return
        if not self.belongs_to_thread(record) or not self.belongs_to_thread(payload):
            return
        if kind == "session_meta":
            if payload.get("id") != self.thread_id:
                self.uncertain = True
                self.identity_verified = False
                return
            self.identity_verified = True
            version = payload.get("cli_version")
            if not isinstance(version, str):
                self.invalid()
                self.version = None
                return
            self.version = version
            return
        if not self.identity_verified or self.version not in SUPPORTED_VERSIONS:
            return
        if kind == "event_msg":
            event_type = payload.get("type")
            if not isinstance(event_type, str) or not event_type:
                self.invalid()
                return
            turn_id = payload.get("turn_id")
            if event_type == "task_started":
                if isinstance(turn_id, str) and turn_id:
                    self.active_turn = turn_id
                else:
                    self.uncertain = True
            elif event_type == "task_complete":
                if not isinstance(turn_id, str) or not turn_id:
                    self.invalid()
                elif self.active_turn and turn_id == self.active_turn:
                    self.last_complete = turn_id
                    self.active_turn = None
                elif self.active_turn is None and turn_id != self.last_complete:
                    # Новый complete без наблюдённого start — неполная история.
                    self.uncertain = True
            elif event_type == "item_completed":
                item = payload.get("item")
                if isinstance(item, dict):
                    self.accept_public_item(item, stamp)
                else:
                    self.invalid()
            elif event_type not in IGNORED_EVENT_TYPES:
                self.uncertain = True
        elif kind == "response_item":
            item_type = payload.get("type")
            if not isinstance(item_type, str) or not item_type:
                self.invalid()
                return
            raw_name = payload.get("name")
            name = raw_name.split(".")[-1] if isinstance(raw_name, str) else ""
            if item_type == "function_call" and name in QUESTION_TOOLS:
                self.accept_question(payload, stamp)
            elif item_type == "function_call_output":
                self.accept_question_result(payload)
            elif item_type == "message" and payload.get("role") == "user":
                self.accept_reply(text_content(payload.get("content")), stamp)
            # reasoning, developer/system, произвольные tool outputs и raw metadata исключены.
        elif kind not in IGNORED_RECORD_KINDS:
            self.uncertain = True

    def accept_public_item(self, item: dict, stamp: Any) -> None:
        if not self.belongs_to_thread(item):
            return
        item_type = item.get("type")
        if not isinstance(item_type, str) or not item_type:
            self.invalid()
            return
        base = {"id": item.get("id"), "timestamp": stamp}
        if item_type in {"AgentMessage", "CommandExecution", "FileChange", "UserMessage"} and (not isinstance(base["id"], str) or not base["id"]):
            self.invalid()
            return
        if item_type == "AgentMessage":
            phase = item.get("phase")
            if not isinstance(phase, str):
                self.invalid()
            elif phase in PUBLIC_PHASES:
                text = text_content(item.get("content"))
                if text:
                    self.put({**base, "type": "message", "phase": phase, "text": text})
        elif item_type == "CommandExecution":
            argv = item.get("command")
            if not isinstance(argv, list) or not argv or not all(isinstance(part, str) for part in argv):
                self.invalid()
                return
            status, cwd, exit_code = item.get("status"), item.get("cwd"), item.get("exit_code")
            if (not isinstance(status, str) or status not in {"completed", "failed"}
                or (cwd is not None and not isinstance(cwd, str))
                or (exit_code is not None and type(exit_code) is not int)
                or any(item.get(key) is not None and not isinstance(item[key], str)
                       for key in ("aggregated_output", "stdout", "stderr"))):
                self.invalid()
                return
            command = argv[-1] if len(argv) >= 3 and argv[-2] in {"-c", "-lc", "-ic"} else " ".join(argv)
            output = item.get("aggregated_output")
            if not isinstance(output, str):
                output = "\n".join(item.get(key, "") for key in ("stdout", "stderr") if isinstance(item.get(key), str))
            self.put({**base, "type": "command", "command": command, "argv": argv,
                      "cwd": cwd, "output": output, "status": status, "exit_code": exit_code})
        elif item_type == "FileChange":
            if not isinstance(item.get("changes"), dict) or not isinstance(item.get("status"), str) or item["status"] not in {"completed", "failed"}:
                self.invalid()
                return
            changes = {}
            for path, change in item["changes"].items():
                if not isinstance(path, str) or not isinstance(change, dict):
                    continue
                if not isinstance(change.get("type"), str) or change["type"] not in {"add", "update", "delete"}:
                    self.invalid()
                    continue
                changes[path] = {key: value for key, value in change.items()
                                 if key in {"type", "content", "unified_diff", "move_path"}
                                 and (value is None or isinstance(value, str))}
            if changes:
                self.put({**base, "type": "file_change", "changes": changes, "status": item.get("status")})
        elif item_type == "UserMessage":
            self.accept_reply(text_content(item.get("content")), stamp)

    def accept_question(self, payload: dict, stamp: Any) -> None:
        call_id = payload.get("call_id")
        arguments = payload.get("arguments")
        if not isinstance(call_id, str) or not call_id or not isinstance(arguments, str):
            self.invalid()
            return
        try:
            data = json.loads(arguments)
        except (json.JSONDecodeError, TypeError):
            self.uncertain = True
            return
        questions = data.get("questions") if isinstance(data, dict) else None
        if not isinstance(questions, list):
            self.uncertain = True
            return
        pending = {}
        for index, question in enumerate(questions):
            if not isinstance(question, dict):
                self.uncertain = True
                continue
            title = question.get("title") or question.get("question")
            question_id = question.get("id")
            if not isinstance(title, str) or (question_id is not None and not isinstance(question_id, str)):
                self.invalid()
                continue
            raw_options = question.get("options", [])
            options = []
            if isinstance(raw_options, list):
                for option in raw_options:
                    if isinstance(option, str):
                        options.append(option)
                    elif isinstance(option, dict) and isinstance(option.get("label"), str):
                        options.append({key: value for key, value in option.items()
                                        if key in {"label", "description"} and isinstance(value, str)})
            pending[index] = {"index": index, "question": title, "options": options,
                              "question_id": question_id}
        if pending:
            self.pending[call_id] = pending
            self.put({"id": "question:" + call_id, "timestamp": stamp, "type": "question",
                      "call_id": call_id, "questions": list(pending.values())})

    def accept_question_result(self, payload: dict) -> None:
        call_id = payload.get("call_id")
        if not isinstance(call_id, str):
            self.invalid()
            return
        if call_id not in self.pending:
            return
        output = payload.get("output")
        if not isinstance(output, str):
            return
        try:
            result = json.loads(output)
        except json.JSONDecodeError:
            return
        if not isinstance(result, dict):
            return
        # accepted=true у async — квитанция, а не ответ на вопрос.
        answers = result.get("answers")
        if isinstance(answers, dict):
            answered_ids = set(answers)
            self.pending[call_id] = {
                index: question for index, question in self.pending[call_id].items()
                if question.get("question_id") not in answered_ids
            }
        elif result.get("accepted") is False or result.get("status") in {"cancelled", "canceled", "rejected"}:
            self.pending[call_id] = {}
        if not self.pending[call_id]:
            del self.pending[call_id]

    def accept_reply(self, text: str, stamp: Any) -> None:
        opening, closing = "<send_user_message_question_reply>", "</send_user_message_question_reply>"
        if opening not in text or closing not in text:
            return
        enclosed = text.split(opening, 1)[1].split(closing, 1)[0]
        try:
            replies = json.loads(enclosed)
        except json.JSONDecodeError:
            return
        if not isinstance(replies, list):
            return
        for reply in replies:
            if not isinstance(reply, dict) or not isinstance(reply.get("questionItemId"), str):
                continue
            try:
                key = json.loads(reply["questionItemId"])
            except json.JSONDecodeError:
                continue
            if not isinstance(key, list) or len(key) != 3:
                continue
            tool, call_id, index = key
            if not isinstance(tool, str) or tool not in QUESTION_TOOLS or not isinstance(call_id, str) or type(index) is not int:
                continue
            if call_id not in self.pending or index not in self.pending[call_id]:
                continue
            answer = reply.get("answer")
            if not isinstance(answer, str):
                continue
            self.pending[call_id].pop(index)
            self.put({"id": f"reply:{call_id}:{index}", "timestamp": stamp, "type": "user_reply", "text": answer})
            if not self.pending[call_id]:
                del self.pending[call_id]

    def state(self, writer_alive: bool | None) -> str:
        if writer_alive is False:
            return "disconnected"
        if writer_alive is None or self.uncertain or not self.identity_verified or self.version not in SUPPORTED_VERSIONS:
            return "unknown"
        if self.pending:
            return "waiting_input"
        if self.active_turn:
            return "working"
        if self.last_complete:
            return "idle"
        return "unknown"


def writer_alive(home: Path, thread_id: str) -> bool | None:
    """Проверяет существующий writer-lock чтением, без создания и записи файла."""
    path = home / "thread-writer-locks" / (thread_id + ".lock")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(stream, fcntl.LOCK_UN)
            return False
    except FileNotFoundError:
        return False
    except OSError:
        return None


def resolve_thread(home: Path, thread_id: str) -> dict:
    uuid.UUID(thread_id)
    candidates = []
    for path in home.glob("state_*.sqlite"):
        suffix = path.stem.removeprefix("state_")
        if suffix.isdigit():
            candidates.append((int(suffix), path))
    if not candidates:
        raise FileNotFoundError("state database unavailable")
    database = max(candidates)[1]
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(threads)")}
        selected = [name for name in ["id", "rollout_path", "title", "name", "cwd", "archived", "history_mode"] if name in columns]
        if not {"id", "rollout_path"}.issubset(columns):
            raise ValueError("unsupported thread metadata schema")
        row = connection.execute("SELECT " + ",".join(selected) + " FROM threads WHERE id=?", (thread_id,)).fetchone()
        if row is None:
            raise LookupError("thread not found")
        result = dict(row)
    finally:
        connection.close()
    if result.get("archived"):
        raise ValueError("archived thread is outside this probe")
    rollout_path = result.get("rollout_path")
    if not isinstance(rollout_path, str) or not rollout_path:
        raise ValueError("unsupported rollout path metadata")
    path = Path(rollout_path).resolve(strict=True)
    path.relative_to((home / "sessions").resolve(strict=True))
    if path.suffix != ".jsonl":
        raise ValueError("unsupported rollout path")
    result["rollout_path"] = str(path)
    return result


class Observer:
    def __init__(self, home: Path, thread_id: str):
        self.home = home.resolve()
        uuid.UUID(thread_id)
        self.thread_id = thread_id
        self.model = SessionState(thread_id)
        self.path: Path | None = None
        self.fingerprint: tuple[int, int] | None = None
        self.offset = 0
        self.buffer = b""
        self.epoch = 0
        self.metadata: dict = {}
        self.error: str | None = None

    def poll(self) -> dict:
        try:
            metadata = resolve_thread(self.home, self.thread_id)
            path = Path(metadata["rollout_path"])
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                fingerprint = (info.st_dev, info.st_ino)
                if self.path != path or self.fingerprint != fingerprint or info.st_size < self.offset:
                    self.model = SessionState(self.thread_id)
                    self.path, self.fingerprint = path, fingerprint
                    self.offset = 0
                    self.buffer = b""
                    self.epoch += 1
                stream.seek(self.offset)
                data = stream.read()
                self.offset += len(data)
            self.metadata = metadata
            self.buffer += data
            lines = self.buffer.split(b"\n")
            self.buffer = lines.pop()
            for line in lines:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    if not isinstance(record, dict):
                        raise ValueError("record is not an object")
                    self.model.accept(record)
                except (ValueError, TypeError, AttributeError):
                    self.model.invalid_records += 1
                    self.model.uncertain = True
            self.error = None
        except (OSError, sqlite3.Error, ValueError, LookupError, KeyError):
            # Последние публичные события сохраняются; ошибка не становится завершением.
            self.error = "source_unavailable_or_unsupported"
        alive = writer_alive(self.home, self.thread_id)
        status = "disconnected" if self.error else self.model.state(alive)
        # Хвост может быть началом нового turn: нельзя гасить экран по старому idle.
        if self.buffer and status == "idle":
            status = "unknown"
        return self.snapshot(status, alive)

    def snapshot(self, status: str, alive: bool | None) -> dict:
        return {
            "thread_id": self.thread_id,
            "name": self.metadata.get("name") or self.metadata.get("title"),
            "cwd": self.metadata.get("cwd"),
            "status": status,
            "writer_alive": alive,
            "runtime_approval_known": False,
            "status_source": "rollout_lifecycle_and_writer_lock",
            "version": self.model.version,
            "supported_version": self.model.version in SUPPORTED_VERSIONS,
            "source_epoch": self.epoch,
            "source_error": self.error,
            "observed_records": self.model.observed_records,
            "invalid_records": self.model.invalid_records,
            "pending_questions": sum(len(questions) for questions in self.model.pending.values()),
            "public_items": len(self.model.items),
            "public_item_types": dict(Counter(item["type"] for item in self.model.items.values())),
            "revision": self.model.revisions,
            "partial_record_bytes": len(self.buffer),
            "items": list(self.model.items.values()),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thread", required=True, help="UUID существующего чата")
    parser.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--watch", type=float, default=0, help="длительность наблюдения, секунды")
    parser.add_argument("--poll", type=float, default=.5, help="интервал чтения, секунды")
    parser.add_argument("--include-content", action="store_true", help="включить полный публичный текст в stdout")
    args = parser.parse_args()
    if args.watch < 0 or args.poll <= 0:
        parser.error("--watch >= 0; --poll > 0")
    try:
        observer = Observer(args.codex_home, args.thread)
    except ValueError:
        parser.error("--thread должен быть UUID")
    deadline = time.monotonic() + args.watch
    previous = None
    while True:
        snapshot = observer.poll()
        if not args.include_content:
            snapshot.pop("items")
        signature = json.dumps(snapshot, ensure_ascii=True, sort_keys=True)
        if signature != previous:
            print(json.dumps({"observed_at": datetime.now(timezone.utc).isoformat(), **snapshot}, ensure_ascii=True), flush=True)
            previous = signature
        if time.monotonic() >= deadline:
            return 0 if snapshot["status"] not in {"unknown", "disconnected"} else 2
        time.sleep(min(args.poll, max(0, deadline - time.monotonic())))


if __name__ == "__main__":
    raise SystemExit(main())
