import time
from datetime import datetime as D

import pytest

from server import core
from server.db import NotCompletable, Repo


def dt(s):
    return D.fromisoformat(s)


# ---------------- 주기 경계 ----------------
@pytest.mark.parametrize("reset,now,start", [
    ("04:00", "2026-10-07T03:59:00", "2026-10-06T04:00:00"),  # 리셋 직전 -> 어제 주기
    ("04:00", "2026-10-07T04:00:00", "2026-10-07T04:00:00"),  # 정각 -> 새 주기
    ("05:00", "2026-10-07T12:00:00", "2026-10-07T05:00:00"),
    ("00:00", "2026-10-07T00:00:01", "2026-10-07T00:00:00"),
])
def test_daily_cycle(reset, now, start):
    s, e = core.cycle_bounds("daily", reset, None, dt(now))
    assert s == dt(start) and (e - s).days == 1


@pytest.mark.parametrize("wd,now,start", [
    (0, "2026-10-07T12:00:00", "2026-10-05T00:00:00"),  # 2026-10-07은 수요일, 월요일 00시
    (1, "2026-10-07T12:00:00", "2026-10-06T00:00:00"),  # 화
    (3, "2026-10-07T12:00:00", "2026-10-01T00:00:00"),  # 목(지난 목요일)
    (1, "2026-10-06T00:00:00", "2026-10-06T00:00:00"),  # 화 00시 정각
    (1, "2026-10-05T23:59:59", "2026-09-29T00:00:00"),  # 화 직전 -> 지난 화요일
])
def test_weekly_cycle(wd, now, start):
    s, e = core.cycle_bounds("weekly", "00:00", wd, dt(now))
    assert s == dt(start) and (e - s).days == 7


# ---------------- 매일 일정 ----------------
def make(**kw):
    base = dict(kind="daily", title="t", reset_time="04:00", reset_weekday=None,
                due_time=None, due_weekday=None, due_at=None, last_completed_at=None)
    base.update(kw)
    return base


def test_daily_reset_flow():
    t = make(last_completed_at="2026-10-07T09:00:00")
    assert core.evaluate(t, dt("2026-10-07T20:00:00"))["status"] == core.DONE
    assert core.evaluate(t, dt("2026-10-08T03:59:00"))["status"] == core.DONE
    assert core.evaluate(t, dt("2026-10-08T04:00:00"))["status"] == core.PENDING  # 초기화


def test_daily_completed_before_reset_does_not_count():
    # 03:00에 완료 -> 04:00 초기화 이전 주기 소속
    t = make(last_completed_at="2026-10-07T03:00:00")
    assert core.evaluate(t, dt("2026-10-07T05:00:00"))["status"] == core.PENDING


def test_daily_default_due_is_next_reset():
    r = core.evaluate(make(), dt("2026-10-07T23:00:00"))
    assert r["due_at"] == "2026-10-08T04:00:00" and r["remaining_sec"] == 5 * 3600


def test_daily_due_time_crossing_midnight():
    # 04시 초기화, 마감 02시 -> 마감은 다음날 02시
    t = make(due_time="02:00")
    r = core.evaluate(t, dt("2026-10-07T10:00:00"))
    assert r["due_at"] == "2026-10-08T02:00:00" and r["status"] == core.PENDING


def test_daily_missed_is_closed_until_reset():
    t = make(due_time="22:00")
    assert core.evaluate(t, dt("2026-10-07T21:59:59"))["status"] == core.PENDING
    r = core.evaluate(t, dt("2026-10-07T22:00:00"))
    assert r["status"] == core.MISSED and not r["can_complete"]
    assert core.evaluate(t, dt("2026-10-08T04:00:00"))["status"] == core.PENDING  # 다음 주기 부활


# ---------------- 주간 일정 ----------------
def test_weekly_due_weekday():
    t = make(kind="weekly", reset_time="00:00", reset_weekday=0, due_time="18:00", due_weekday=4)
    r = core.evaluate(t, dt("2026-10-07T12:00:00"))  # 수요일
    assert r["due_at"] == "2026-10-09T18:00:00" and r["status"] == core.PENDING
    assert core.evaluate(t, dt("2026-10-09T18:00:00"))["status"] == core.MISSED
    assert core.evaluate(t, dt("2026-10-12T00:00:00"))["status"] == core.PENDING


# ---------------- 일회성 ----------------
def test_once_states():
    t = make(kind="once", reset_time=None, due_at="2026-10-07T18:00:00")
    assert core.evaluate(t, dt("2026-10-07T17:00:00"))["status"] == core.PENDING
    assert core.evaluate(t, dt("2026-10-07T18:00:00"))["status"] == core.MISSED
    t["last_completed_at"] = "2026-10-07T10:00:00"
    assert core.evaluate(t, dt("2026-10-09T10:00:00"))["status"] == core.DONE  # 완료는 영구
    assert core.evaluate(make(kind="once", reset_time=None), dt("2030-01-01T00:00:00"))["status"] == core.PENDING


# ---------------- 검증 ----------------
def test_validation():
    with pytest.raises(ValueError):
        core.normalize_task({"kind": "daily", "title": "  "})
    with pytest.raises(ValueError):
        core.normalize_task({"kind": "weekly", "title": "a"})  # 요일 없음
    with pytest.raises(ValueError):
        core.normalize_task({"kind": "daily", "title": "a", "reset_time": "25:00"})
    with pytest.raises(ValueError):
        core.normalize_task({"kind": "weekly", "title": "a", "reset_weekday": 1, "due_time": "10:00"})
    n = core.normalize_task({"kind": "daily", "title": " a ", "reset_time": "4:0"})
    assert n["reset_time"] == "04:00" and n["title"] == "a"


# ---------------- DB 흐름 ----------------
def test_repo_flow():
    repo = Repo(":memory:")
    now = dt("2026-10-07T10:00:00")
    a = repo.create({"kind": "daily", "title": "약", "reset_time": "04:00", "due_time": "22:00"}, now)
    assert a["status"] == core.PENDING
    a = repo.complete(a["id"], now)
    assert a["status"] == core.DONE
    a = repo.uncomplete(a["id"], now)
    assert a["status"] == core.PENDING
    # 마감 후 완료 불가
    late = dt("2026-10-07T22:30:00")
    with pytest.raises(NotCompletable):
        repo.complete(a["id"], late)
    # 마감 전 완료 -> 마감 후 취소하면 마감 초과가 됨
    b = repo.complete(a["id"], now)
    assert repo.uncomplete(b["id"], late)["status"] == core.MISSED
    # 다음날 초기화 후 다시 완료 가능
    nxt = dt("2026-10-08T05:00:00")
    assert repo.complete(a["id"], nxt)["status"] == core.DONE
    # 수정: 종류 변경
    u = repo.update(a["id"], {"kind": "weekly", "reset_weekday": 2, "reset_time": "00:00"}, nxt)
    assert u["kind"] == "weekly" and u["due_time"] is None
    repo.delete(a["id"])
    assert repo.list(nxt) == []


def test_closed_once_hidden_after_days():
    repo = Repo(":memory:")
    t0 = dt("2026-10-01T10:00:00")
    x = repo.create({"kind": "once", "title": "x", "due_at": "2026-10-01T12:00:00"}, t0)
    assert len(repo.list(dt("2026-10-03T00:00:00"))) == 1
    assert len(repo.list(dt("2026-10-05T00:00:00"))) == 0
    assert len(repo.list(dt("2026-10-05T00:00:00"), keep_closed_days=-1)) == 1


def test_sort_order():
    repo = Repo(":memory:")
    now = dt("2026-10-07T10:00:00")
    repo.create({"kind": "once", "title": "늦은", "due_at": "2026-10-09T10:00:00"}, now)
    repo.create({"kind": "once", "title": "임박", "due_at": "2026-10-07T11:00:00"}, now)
    repo.create({"kind": "once", "title": "무기한"}, now)
    d = repo.create({"kind": "once", "title": "완료됨"}, now)
    repo.complete(d["id"], now)
    titles = [i["title"] for i in repo.list(now)]
    assert titles == ["임박", "늦은", "무기한", "완료됨"]


def test_performance_5000():
    repo = Repo(":memory:")
    now = dt("2026-10-07T10:00:00")
    for i in range(5000):
        k = ["daily", "weekly", "once"][i % 3]
        repo.create({"kind": k, "title": f"task{i}", "reset_time": f"{i % 24:02d}:00",
                     "reset_weekday": i % 7, "due_at": "2026-12-01T10:00:00"}, now)
    s = time.perf_counter()
    items = repo.list(now)
    el = time.perf_counter() - s
    assert len(items) == 5000 and el < 1.0, el
