"""FastAPI 서버. 모든 시각은 서버 PC 로컬 시간 기준."""
from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel

from . import core
from .db import NotCompletable, NotFound, Repo

API_VERSION = 1


class TaskIn(BaseModel):
    title: Optional[str] = None
    note: Optional[str] = None
    kind: Optional[str] = None            # daily | weekly | once
    reset_time: Optional[str] = None      # "HH:MM"
    reset_weekday: Optional[int] = None   # 0=월 ... 6=일
    due_time: Optional[str] = None        # 반복 일정의 마감 시각 "HH:MM"
    due_weekday: Optional[int] = None     # 주간 일정의 마감 요일
    due_at: Optional[str] = None          # 일회성 마감 "YYYY-MM-DDTHH:MM"


def create_app(db_path: str = "data/todo.db",
               clock: Callable[[], datetime] | None = None) -> FastAPI:
    app = FastAPI(title="Todo Manager Server", version=str(API_VERSION))
    repo = Repo(db_path)
    now = clock or (lambda: datetime.now().replace(microsecond=0))
    app.state.repo = repo
    app.add_middleware(GZipMiddleware, minimum_size=1024)  # 목록 응답 압축(Tailscale 구간 대비)

    def guard(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except NotFound as e:
            raise HTTPException(404, str(e))
        except NotCompletable as e:
            raise HTTPException(409, str(e))
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.get("/api/health")
    def health():
        return {"ok": True, "api_version": API_VERSION, "server_now": core.fmt_dt(now())}

    @app.get("/api/tasks")
    def list_tasks(keep_closed_days: int = 3):
        n = now()
        return {"server_now": core.fmt_dt(n), "tasks": repo.list(n, keep_closed_days)}

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: int):
        return guard(repo.get, task_id, now())

    @app.post("/api/tasks", status_code=201)
    def create_task(body: TaskIn):
        return guard(repo.create, body.model_dump(), now())

    @app.patch("/api/tasks/{task_id}")
    def update_task(task_id: int, body: TaskIn):
        return guard(repo.update, task_id, body.model_dump(exclude_unset=True), now())

    @app.delete("/api/tasks/{task_id}", status_code=204)
    def delete_task(task_id: int):
        guard(repo.delete, task_id)

    @app.post("/api/tasks/{task_id}/complete")
    def complete_task(task_id: int):
        return guard(repo.complete, task_id, now())

    @app.post("/api/tasks/{task_id}/uncomplete")
    def uncomplete_task(task_id: int):
        return guard(repo.uncomplete, task_id, now())

    return app
