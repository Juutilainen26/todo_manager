from datetime import datetime as D

import pytest
from fastapi.testclient import TestClient

from server.api import create_app


class Clock:
    def __init__(self, s): self.t = D.fromisoformat(s)
    def __call__(self): return self.t


@pytest.fixture
def env():
    clk = Clock("2026-10-07T10:00:00")
    return TestClient(create_app(":memory:", clk)), clk


def test_crud_and_complete(env):
    c, clk = env
    assert c.get("/api/health").json()["ok"]
    r = c.post("/api/tasks", json={"title": "운동", "kind": "daily", "reset_time": "05:00", "due_time": "22:00"})
    assert r.status_code == 201
    tid = r.json()["id"]
    assert c.post(f"/api/tasks/{tid}/complete").json()["status"] == "done"
    assert c.post(f"/api/tasks/{tid}/uncomplete").json()["status"] == "pending"
    r = c.patch(f"/api/tasks/{tid}", json={"title": "스트레칭"})
    assert r.json()["title"] == "스트레칭" and r.json()["due_time"] == "22:00"  # 일부 필드만 수정
    clk.t = D.fromisoformat("2026-10-07T23:00:00")
    assert c.get(f"/api/tasks/{tid}").json()["status"] == "missed"
    assert c.post(f"/api/tasks/{tid}/complete").status_code == 409
    assert c.delete(f"/api/tasks/{tid}").status_code == 204
    assert c.get(f"/api/tasks/{tid}").status_code == 404
    assert c.get("/api/tasks").json()["tasks"] == []


def test_validation_errors(env):
    c, _ = env
    assert c.post("/api/tasks", json={"title": "", "kind": "daily"}).status_code == 422
    assert c.post("/api/tasks", json={"title": "a", "kind": "weekly"}).status_code == 422
    assert c.patch("/api/tasks/999", json={"title": "x"}).status_code == 404


def test_cors_only_for_app_origins(env):
    """앱(WebView, http://localhost)만 허용하고 임의 사이트는 허용하지 않는다."""
    c, _ = env
    ok = c.options("/api/tasks", headers={"Origin": "http://localhost", "Access-Control-Request-Method": "POST",
                                            "Access-Control-Request-Headers": "content-type"})
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == "http://localhost"
    assert "PATCH" in ok.headers["access-control-allow-methods"] or "*" in ok.headers["access-control-allow-methods"]
    bad = c.options("/api/tasks", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in bad.headers
    g = c.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in g.headers
    g = c.get("/api/health", headers={"Origin": "http://localhost:5555"})
    assert g.headers["access-control-allow-origin"] == "http://localhost:5555"
