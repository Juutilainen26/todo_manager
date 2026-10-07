"""서버 통신 (UI와 분리). 모든 호출은 블로킹이므로 UI 스레드 밖에서 호출할 것."""
from __future__ import annotations

import socket
from urllib.parse import urlsplit, urlunsplit

import requests
import urllib3.util.connection as _u3conn

# 서버는 IPv4로만 열려 있다. 윈도우에서 IPv6를 먼저 시도하다 몇 초씩 지연되는 것을 막는다.
_u3conn.allowed_gai_family = lambda: socket.AF_INET


def _fix_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.hostname and parts.hostname.lower() == "localhost":
        netloc = "127.0.0.1" + (f":{parts.port}" if parts.port else "")
        parts = parts._replace(netloc=netloc)
    return urlunsplit(parts).rstrip("/")


class ApiError(Exception):
    """서버가 거절한 요청(검증 오류, 마감 초과 등). message는 사용자에게 보여줄 수 있다."""


class Offline(Exception):
    """서버에 연결할 수 없음."""


class Api:
    def __init__(self, base_url: str, timeout: float = 4.0):
        self.base = _fix_url(base_url)
        self.timeout = timeout
        self.s = requests.Session()
        self.s.trust_env = False   # 시스템 프록시 설정 조회로 인한 지연 방지(내부망 직접 접속)

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
