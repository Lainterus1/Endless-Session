"""Обнаружение локальных чатов; ошибки не превращаются в пустой состав."""
import json
import sqlite3
from contextlib import closing
import threading
import time
import uuid

from source_probe import Observer, SUPPORTED_VERSIONS, writer_alive


def _guardian(thread_source, source):
    if thread_source == "guardian_review":
        return True
    if not isinstance(source, str):
        return False
    try:
        value = json.loads(source)
    except (TypeError, ValueError):
        return False
    subagent = value.get("subagent") if isinstance(value, dict) else None
    return isinstance(subagent, dict) and subagent.get("other") == "guardian"


def thread_roster(home):
    databases = [(int(p.stem[6:]), p) for p in home.glob("state_*.sqlite") if p.stem[6:].isdigit()]
    if not databases: raise FileNotFoundError("metadata unavailable")
    with closing(sqlite3.connect(max(databases)[1].resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.execute("PRAGMA query_only=ON")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(threads)")}
        fields = ["id", "archived"] + [name for name in ("thread_source", "source") if name in columns]
        rows = connection.execute("SELECT " + ", ".join(fields) + " FROM threads").fetchall()
    ids = []
    guardians = set()
    for row in rows:
        record = dict(zip(fields, row))
        value = record["id"]
        if _guardian(record.get("thread_source"), record.get("source")):
            if isinstance(value, str):
                guardians.add(value)
            continue
        if record["archived"] != 0:
            continue
        if not isinstance(value, str) or str(uuid.UUID(value)) != value: raise ValueError("invalid thread identity")
        ids.append(value)
    return sorted(set(ids) - guardians), guardians


class Discovery:
    def __init__(self, home, clock=time.monotonic):
        self.home = home
        self.clock = clock
        self.observers = {}
        self.monitored = {}
        self.completed_at = {}
        self.state = "scanning"
        self.unknown_count = 0

    def scan(self, progress=lambda: None):
        try: ids, guardians = thread_roster(self.home)
        except (OSError, sqlite3.Error, ValueError):
            self.state = "unknown"
            self.monitored = {key: {**snap, "status": "disconnected"} for key, snap in self.monitored.items()}
            progress(); return
        for thread in guardians:
            self.observers.pop(thread, None)
            self.monitored.pop(thread, None)
            self.completed_at.pop(thread, None)
        unknown = 0
        for thread in ids:
            if thread not in self.monitored and writer_alive(self.home,thread) is False:
                # Historical questions/unfinished turns do not prove a live chat.
                # Re-read from the start if a writer later resumes this thread.
                self.observers.pop(thread,None)
                self.completed_at.pop(thread,None)
                progress();continue
            observer = self.observers.setdefault(thread, Observer(self.home, thread))
            snapshot = observer.poll()
            model = observer.model
            active = bool(model.active_turn or model.pending)
            clean_complete = bool(model.last_complete and not model.active_turn and not model.pending
                and not model.uncertain and not observer.buffer and not observer.error and model.version in SUPPORTED_VERSIONS)
            if snapshot["writer_alive"] is None or (not active and not clean_complete): unknown += 1
            if thread in self.monitored or (active and snapshot["writer_alive"] is True):
                self.monitored[thread] = snapshot
                if snapshot["status"] == "idle" and not snapshot["pending_questions"]:
                    self.completed_at.setdefault(thread, self.clock())
                    if self.clock() - self.completed_at[thread] >= 10:
                        del self.monitored[thread]; self.completed_at.pop(thread, None)
                else: self.completed_at.pop(thread, None)
            if thread not in self.monitored:
                # Для неактивных сохраняется состояние парсера, но не история текста.
                model.items.clear()
                if snapshot["writer_alive"] is not True:
                    # An unconfirmed writer may return later without new records.
                    self.observers.pop(thread,None)
            progress()
        for thread in set(self.monitored) - set(ids):
            self.monitored[thread] = {**self.monitored[thread], "status": "disconnected"}
        self.unknown_count = unknown
        self.state = "unknown" if unknown else "ready"
        progress()


class Worker:
    """Публикует законченные снимки; главный поток не ждёт обхода журналов."""
    def __init__(self, discovery, clock=time.monotonic):
        self.discovery = discovery
        self.clock = clock
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.latest = ("scanning", 0, [])
        self.progress_at = clock()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def publish(self):
        with self.lock:
            self.latest = (self.discovery.state, self.discovery.unknown_count,
                [dict(self.discovery.monitored[key]) for key in sorted(self.discovery.monitored)])
            self.progress_at = self.clock()

    def snapshot(self):
        with self.lock:
            state, count, chats = self.latest
            if self.clock() - self.progress_at > 5:
                return "unknown", count, [{**chat, "status": "disconnected"} for chat in chats]
            return state, count, list(chats)

    def run(self):
        while not self.stop.is_set():
            self.discovery.scan(self.publish)
            self.stop.wait(0.5)

    def start(self): self.thread.start()
