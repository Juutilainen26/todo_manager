from datetime import datetime as D

from client import util


def test_fmt_span():
    assert util.fmt_span(30) == "1분 미만"
    assert util.fmt_span(12 * 60) == "12분"
    assert util.fmt_span(2 * 3600 + 15 * 60) == "2시간 15분"
    assert util.fmt_span(3 * 3600) == "3시간"
    assert util.fmt_span(3 * 86400 + 4 * 3600) == "3일 4시간"


def test_fmt_due():
    now = D(2026, 10, 7, 10, 0)
    assert util.fmt_due(D(2026, 10, 7, 18, 0), now) == "오늘 18:00"
    assert util.fmt_due(D(2026, 10, 8, 9, 5), now) == "내일 09:05"
    assert util.fmt_due(D(2026, 10, 12, 18, 0), now) == "10/12(월) 18:00"


def _t(**kw):
    base = {"kind": "daily", "status": "pending", "reset_time": "04:00", "due_time": None,
            "_due": D(2026, 10, 8, 4, 0), "_end": D(2026, 10, 8, 4, 0)}
    base.update(kw)
    return base


def test_right_text_and_rules():
    now = D(2026, 10, 7, 23, 0)
    assert util.right_text(_t(), now) == ("초기화까지 5시간", "text")
    assert util.right_text(_t(due_time="23:30", _due=D(2026, 10, 7, 23, 30)), now) == ("30분 남음", "warn")
    assert util.right_text(_t(status="missed"), now)[1] == "danger"
    assert util.right_text(_t(status="done"), now)[0].startswith("✔ 완료")
    once = {"kind": "once", "status": "pending", "due_at": None, "_due": None, "_end": None}
    assert util.right_text(once, now) == ("기한 없음", "sub")
    assert util.rule_text(_t(due_time="22:00")) == "매일 04:00 초기화 · 마감 22:00"
    w = {"kind": "weekly", "reset_weekday": 1, "reset_time": "00:00", "due_time": None}
    assert util.rule_text(w) == "매주 화 00:00 초기화"


def test_expiry():
    assert util.expiry(_t()) == D(2026, 10, 8, 4, 0)
    assert util.expiry(_t(status="done", _due=D(2026, 10, 7, 22, 0))) == D(2026, 10, 8, 4, 0)
    assert util.expiry({"kind": "once", "status": "done", "_due": None, "_end": None}) is None
