"""SQLite 저장소. 일정 CRUD + 완료/미완료 처리."""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import core

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    title             TEXT NOT NULL,
    note              TEXT NOT NULL DEFAULT '',
    kind              TEXT NOT NULL,
    reset_time        TEXT,
    reset_weekday     INTEGER,
    due_time          TEXT,
    due_weekday       INTEGER,
    due_at            TEXT,
    last_completed_at TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_kind ON tasks(kind);

CREATE TABLE IF NOT EXISTS completions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id      INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    completed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_comp_task ON completions(task_id, completed_at);
"""

COLS = ("id,title,note,kind,reset_time,reset_weekday,due_time,due_weekday,"
        "due_at,last_completed_at,created_at,updated_at")


class NotFound(Exception):
    pass


class NotCompletable(Exception):
    """마감 초과로 종료된 일정은 완료할 수 없다."""


class Repo:
    def __init__(self, path: str | Path = "data/todo.db"):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.executescript(SCHEMA)
        self._db.commit()

    # ---- 내부
    def _row(self, task_id: int) -> dict[str, Any]:
        r = self._db.execute(f"SELECT {COLS} FROM tasks WHERE id=?", (task_id,)).fetchone()
        if r is None:
            raise NotFound(f"일정 {task_id}번을 찾을 수 없습니다.")
        return dict(r)

    @staticmethod
    def _view(row: dict[str, Any], now: datetime) -> dict[str, Any]:
        return {**row, **core.evaluate(row, now)}

    # ---- 조회
    def list(self, now: datetime, keep_closed_days: int = 3) -> list[dict[str, Any]]:
        with self._lock:
            rows = [dict(r) for r in self._db.execute(f"SELECT {COLS} FROM tasks")]
        items = [self._view(r, now) for r in rows]
        if keep_closed_days >= 0:
            items = [i for i in items if not core.is_hidden_closed_once(i, now, keep_closed_days)]
        items.sort(key=core.sort_key)
        return items

    def get(self, task_id: int, now: datetime) -> dict[str, Any]:
        with self._lock:
            return self._view(self._row(task_id), now)

    # ---- 추가/수정/삭제
    def create(self, data: dict[str, Any], now: datetime) -> dict[str, Any]:
        t = core.normalize_task(data)
        ts = core.fmt_dt(now)
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO tasks(title,note,kind,reset_time,reset_weekday,due_time,"
                "due_weekday,due_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (t["title"], t["note"], t["kind"], t["reset_time"], t["reset_weekday"],
                 t["due_time"], t["due_weekday"], t["due_at"], ts, ts))
            self._db.commit()
            return self._view(self._row(cur.lastrowid), now)

    def update(self, task_id: int, patch: dict[str, Any], now: datetime) -> dict[str, Any]:
        with self._lock:
            cur = self._row(task_id)
            merged = {**cur, **patch}
            # 종류가 바뀌면 이전 종류 전용 필드는 비운다
            if "kind" in patch and patch["kind"] != cur["kind"]:
                for k in ("reset_time", "reset_weekday", "due_time", "due_weekday", "due_at"):
                    if k not in patch:
                        merged[k] = None
            t = core.normalize_task(merged)
            self._db.execute(
                "UPDATE tasks SET title=?,note=?,kind=?,reset_time=?,reset_weekday=?,"
                "due_time=?,due_weekday=?,due_at=?,updated_at=? WHERE id=?",
                (t["title"], t["note"], t["kind"], t["reset_time"], t["reset_weekday"],
                 t["due_time"], t["due_weekday"], t["due_at"], core.fmt_dt(now), task_id))
            self._db.commit()
            return self._view(self._row(task_id), now)

    def delete(self, task_id: int) -> None:
        with self._lock:
            self._row(task_id)
            self._db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
            self._db.commit()

    # ---- 완료 / 미완료
    def complete(self, task_id: int, now: datetime) -> dict[str, Any]:
        with self._lock:
            row = self._row(task_id)
            view = self._view(row, now)
            if view["status"] == core.DONE:
                return view  # 이미 완료 -> 그대로
            if view["status"] == core.MISSED:
                raise NotCompletable("마감이 지나 종료된 일정은 완료할 수 없습니다.")
            ts = core.fmt_dt(now)
            self._db.execute("INSERT INTO completions(task_id,completed_at) VALUES(?,?)", (task_id, ts))
            self._db.execute("UPDATE tasks SET last_completed_at=?,updated_at=? WHERE id=?",
                             (ts, ts, task_id))
            self._db.commit()
            return self._view(self._row(task_id), now)

    def uncomplete(self, task_id: int, now: datetime) -> dict[str, Any]:
        """현재 주기(일회성은 전체)의 완료 기록을 취소한다.
        취소 후 이미 마감이 지났다면 '마감 초과'가 된다(자연스러운 결과)."""
        with self._lock:
            row = self._row(task_id)
            view = self._view(row, now)
            if view["status"] == core.DONE:
                since = view["cycle_start"] or "0000-00-00T00:00:00"
                self._db.execute("DELETE FROM completions WHERE task_id=? AND completed_at>=?",
                                 (task_id, since))
                prev = self._db.execute(
                    "SELECT MAX(completed_at) FROM completions WHERE task_id=?", (task_id,)
                ).fetchone()[0]
                self._db.execute("UPDATE tasks SET last_completed_at=?,updated_at=? WHERE id=?",
                                 (prev, core.fmt_dt(now), task_id))
                self._db.commit()
            return self._view(self._row(task_id), now)

    def close(self) -> None:
        self._db.close()
