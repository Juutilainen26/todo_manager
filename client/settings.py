"""사용자 설정/캐시 저장 (Windows: %APPDATA%\\TodoManager)."""
from __future__ import annotations

import json
import os
from pathlib import Path


def app_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    p = Path(base) / "TodoManager"
    p.mkdir(parents=True, exist_ok=True)
    return p


class Settings:
    def __init__(self, path: Path | None = None):
        self.path = path or app_dir() / "settings.json"
        self.data = {"server_url": "", "notify": True, "keep_closed_days": 3,
                     "window": None}
        try:
            self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            pass

    def __getitem__(self, k):
        return self.data.get(k)

    def __setitem__(self, k, v):
        self.data[k] = v
        self.save()

    def save(self):
        try:
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass


class Cache:
    """마지막으로 받은 목록 -> 시작할 때 즉시 표시(서버 응답 전/오프라인 대비)."""

    def __init__(self, path: Path | None = None):
        self.path = path or app_dir() / "cache.json"

    def load(self) -> dict | None:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None

    def save(self, payload: dict) -> None:
        try:
            self.path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
