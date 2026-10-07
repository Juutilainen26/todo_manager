"""추가/수정 창이 모든 종류에서 열리고 올바른 값을 만드는지 점검."""
import os
from datetime import datetime

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from client.dialogs import TaskDialog  # noqa: E402
from client.api_client import _fix_url  # noqa: E402

app = QApplication.instance() or QApplication([])


@pytest.mark.parametrize("kind", ["daily", "weekly", "once"])
def test_new_dialog_opens(kind):
    d = TaskDialog(None, now=datetime(2026, 10, 7, 10, 0), default_kind=kind)
    d.show(); app.processEvents()
    d.title.setText("테스트")
    p = d.payload()
    assert p["kind"] == kind and p["title"] == "테스트"


def test_edit_dialog_prefills_and_roundtrips():
    t = {"title": "주간", "note": "메모", "kind": "weekly", "reset_time": "00:00", "reset_weekday": 3,
         "due_time": "18:00", "due_weekday": 4, "due_at": None}
    d = TaskDialog(None, task=t, now=datetime(2026, 10, 7, 10, 0))
    p = d.payload()
    assert (p["reset_weekday"], p["reset_time"], p["due_weekday"], p["due_time"]) == (3, "00:00", 4, "18:00")


def test_once_with_due():
    t = {"title": "x", "note": "", "kind": "once", "due_at": "2026-10-12T18:30:00",
         "reset_time": None, "reset_weekday": None, "due_time": None, "due_weekday": None}
    assert TaskDialog(None, task=t, now=datetime(2026, 10, 7)).payload()["due_at"] == "2026-10-12T18:30:00"


def test_localhost_is_mapped_to_ipv4():
    assert _fix_url("http://localhost:8765/") == "http://127.0.0.1:8765"
    assert _fix_url("http://DESKTOP-1:8765") == "http://DESKTOP-1:8765"
