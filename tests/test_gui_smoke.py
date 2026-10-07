"""서버를 실제로 띄우고 UI(오프스크린)를 조작하는 통합 점검."""
import os
import socket
import threading
import time
from datetime import datetime, timedelta

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
import uvicorn  # noqa: E402
from PySide6.QtCore import QThreadPool  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from client.api_client import Api  # noqa: E402
from client.main_window import MainWindow  # noqa: E402
from client.settings import Cache, Settings  # noqa: E402
from server.api import create_app  # noqa: E402


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture
def stack(tmp_path):
    port = free_port()
    srv = uvicorn.Server(uvicorn.Config(create_app(str(tmp_path / "t.db")), port=port, log_level="error"))
    threading.Thread(target=srv.run, daemon=True).start()
    api = Api(f"http://127.0.0.1:{port}")
    for _ in range(50):
        try:
            api.health(); break
        except Exception:  # noqa: BLE001
            time.sleep(0.1)
    app = QApplication.instance() or QApplication([])
    s = Settings(tmp_path / "s.json"); s["server_url"] = f"http://127.0.0.1:{port}"; s["notify"] = False
    w = MainWindow(s, Cache(tmp_path / "c.json")); w.show()

    def pump(sec):
        end = time.time() + sec
        while time.time() < end:
            app.processEvents(); time.sleep(0.02)
    yield api, w, pump, srv
    srv.should_exit = True
    QThreadPool.globalInstance().waitForDone(3000)   # 백그라운드 작업이 끝난 뒤 창을 정리
    w._quitting = True; w.tray.hide(); w.close()


def test_ui_flow(stack):
    api, w, pump, srv = stack
    now = datetime.now()
    api.create({"title": "매일A", "kind": "daily", "reset_time": "04:00"})
    api.create({"title": "주간B", "kind": "weekly", "reset_weekday": 1, "reset_time": "00:00"})
    api.create({"title": "미래C", "kind": "once"})
    api.create({"title": "지난D", "kind": "once", "due_at": (now + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S")})
    time.sleep(1.5)
    w.refresh(); pump(1.5)
    assert w.online and len(w.model.rows) == 4
    # 마감 초과는 완료 불가 + 목록 맨 아래
    assert w.model.rows[-1]["title"] == "지난D" and w.model.rows[-1]["status"] == "missed"
    # 완료 토글
    a = next(t for t in w.model.rows if t["title"] == "매일A")
    w.toggle(a); pump(1.0)
    assert next(t for t in w.model.all if t["title"] == "매일A")["status"] == "done"
    w.toggle(next(t for t in w.model.all if t["title"] == "매일A")); pump(1.0)
    assert next(t for t in w.model.all if t["title"] == "매일A")["status"] == "pending"
    # 탭 필터
    w.tabs.setCurrentIndex(3); pump(0.2)
    assert [t["title"] for t in w.model.rows] == ["주간B"]
    w.tabs.setCurrentIndex(4); pump(0.2)
    assert [t["title"] for t in w.model.rows] == ["미래C"]
    w.tabs.setCurrentIndex(0)
    # 빠른 추가
    w.quick.setText("빠른추가"); w.quick_kind.setCurrentIndex(1); w.quick_add(); pump(1.0)
    assert any(t["title"] == "빠른추가" and t["kind"] == "daily" for t in w.model.all)
    # 오프라인: 목록 유지 + 배너
    # 서버가 꺼진 상황: 아무도 듣지 않는 포트로 접속 (운영체제와 상관없이 동일하게 재현됨)
    w.set_server(f"http://127.0.0.1:{free_port()}")
    w.refresh(); pump(1.5)
    assert not w.online and not w.banner.isHidden() and len(w.model.rows) == 5
