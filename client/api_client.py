"""서버 통신 (UI와 분리). 모든 호출은 블로킹이므로 UI 스레드 밖에서 호출할 것."""
from __future__ import annotations

import requests


class ApiError(Exception):
    """서버가 거절한 요청(검증 오류, 마감 초과 등). message는 사용자에게 보여줄 수 있다."""


class Offline(Exception):
    """서버에 연결할 수 없음."""


class Api:
    def __init__(self, base_url: str, timeout: float = 4.0):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.s = requests.Session()

    def _call(self, method: str, path: str, **kw):
        try:
            r = self.s.request(method, self.base + path, timeout=self.timeout, **kw)
        except requests.RequestException as e:
            raise Offline(str(e)) from e
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text)
            except Exception:  # noqa: BLE001
                detail = r.text
            if isinstance(detail, list):  # pydantic 오류 형태
                detail = "; ".join(str(d.get("msg", d)) for d in detail)
            raise ApiError(str(detail))
        return r.json() if r.content else None

    def health(self):
        return self._call("GET", "/api/health")

    def list(self, keep_closed_days: int = 3):
        return self._call("GET", "/api/tasks", params={"keep_closed_days": keep_closed_days})

    def create(self, data: dict):
        return self._call("POST", "/api/tasks", json=data)

    def update(self, task_id: int, data: dict):
        return self._call("PATCH", f"/api/tasks/{task_id}", json=data)

    def delete(self, task_id: int):
        return self._call("DELETE", f"/api/tasks/{task_id}")

    def complete(self, task_id: int):
        return self._call("POST", f"/api/tasks/{task_id}/complete")

    def uncomplete(self, task_id: int):
        return self._call("POST", f"/api/tasks/{task_id}/uncomplete")
