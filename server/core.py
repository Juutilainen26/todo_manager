"""일정 관리 코어 로직 (순수 함수, DB/네트워크 의존 없음).

핵심 아이디어
-------------
- 크론으로 '초기화'를 실행하지 않는다. 대신 '현재 주기 시작 시각'을 계산하고,
  마지막 완료 시각이 그 이후인지로 완료 여부를 조회 시점에 판정한다.
  -> 서버가 꺼져 있다 켜져도 상태가 항상 정확하다.
- 마감 초과(missed)는 '완료와 동일한 종료 상태'다. 더 이상 완료할 수 없다.
- 모든 시각은 서버 PC의 로컬 시간(naive datetime)을 사용한다.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

KINDS = ("daily", "weekly", "once")
WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]

PENDING = "pending"   # 진행 중(완료 가능)
DONE = "done"         # 완료
MISSED = "missed"     # 마감 초과(종료, 완료 불가)

ISO_FMT = "%Y-%m-%dT%H:%M:%S"


# ---------------------------------------------------------------- 파싱/검증
def parse_hm(value: str) -> tuple[int, int]:
    try:
        h, m = str(value).strip().split(":")[:2]
        h, m = int(h), int(m)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"시각 형식이 올바르지 않습니다(HH:MM): {value!r}") from e
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"시각 범위가 올바르지 않습니다: {value!r}")
    return h, m


def norm_hm(value: str) -> str:
    h, m = parse_hm(value)
    return f"{h:02d}:{m:02d}"


def parse_dt(value: str) -> datetime:
    try:
        s = str(value).strip().replace(" ", "T")
        if len(s) == 10:  # 날짜만 들어온 경우 -> 그날 23:59
            return datetime.fromisoformat(s).replace(hour=23, minute=59)
        return datetime.fromisoformat(s).replace(microsecond=0, tzinfo=None)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"날짜/시각 형식이 올바르지 않습니다: {value!r}") from e


def fmt_dt(dt: Optional[datetime]) -> Optional[str]:
    return dt.strftime(ISO_FMT) if dt else None


def normalize_task(data: dict[str, Any]) -> dict[str, Any]:
    """입력값을 검증하고 저장용 형태로 정규화한다. 잘못되면 ValueError."""
    kind = data.get("kind")
    if kind not in KINDS:
        raise ValueError(f"kind는 {KINDS} 중 하나여야 합니다.")
    title = (data.get("title") or "").strip()
    if not title:
        raise ValueError("제목을 입력해 주세요.")

    out: dict[str, Any] = {
        "title": title,
        "note": (data.get("note") or "").strip(),
        "kind": kind,
        "reset_time": None,
        "reset_weekday": None,
        "due_time": None,
        "due_weekday": None,
        "due_at": None,
    }

    if kind in ("daily", "weekly"):
        out["reset_time"] = norm_hm(data.get("reset_time") or "00:00")
        if kind == "weekly":
            wd = data.get("reset_weekday")
            if wd is None:
                raise ValueError("주간 일정은 초기화 요일이 필요합니다.")
            wd = int(wd)
            if not 0 <= wd <= 6:
                raise ValueError("요일은 0(월)~6(일) 이어야 합니다.")
            out["reset_weekday"] = wd
        if data.get("due_time"):
            out["due_time"] = norm_hm(data["due_time"])
            if kind == "weekly":
                dwd = data.get("due_weekday")
                if dwd is None:
                    raise ValueError("주간 일정의 마감 시각을 쓰려면 마감 요일도 필요합니다.")
                dwd = int(dwd)
                if not 0 <= dwd <= 6:
                    raise ValueError("마감 요일은 0(월)~6(일) 이어야 합니다.")
                out["due_weekday"] = dwd
    else:  # once
        if data.get("due_at"):
            out["due_at"] = fmt_dt(parse_dt(data["due_at"]))
    return out


# ---------------------------------------------------------------- 주기 계산
def cycle_bounds(kind: str, reset_time: str, reset_weekday: Optional[int],
                 now: datetime) -> tuple[datetime, datetime]:
    """now가 속한 주기의 [시작, 끝) 을 반환한다."""
    h, m = parse_hm(reset_time)
    start = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if kind == "daily":
        if start > now:
            start -= timedelta(days=1)
        return start, start + timedelta(days=1)
    if kind == "weekly":
        start -= timedelta(days=(start.weekday() - int(reset_weekday)) % 7)
        if start > now:
            start -= timedelta(days=7)
        return start, start + timedelta(days=7)
    raise ValueError("반복 일정이 아닙니다.")


def cycle_due(task: dict[str, Any], start: datetime, end: datetime) -> datetime:
    """주기 안에서의 마감 시각. 별도 마감이 없으면 주기 끝(=다음 초기화)."""
    due_time = task.get("due_time")
    if not due_time:
        return end
    h, m = parse_hm(due_time)
    cand = start.replace(hour=h, minute=m, second=0, microsecond=0)
    if task["kind"] == "weekly":
        cand += timedelta(days=(int(task["due_weekday"]) - start.weekday()) % 7)
        if cand <= start:
            cand += timedelta(days=7)
    else:
        if cand <= start:
            cand += timedelta(days=1)
    return min(cand, end)


# ---------------------------------------------------------------- 상태 판정
def evaluate(task: dict[str, Any], now: datetime) -> dict[str, Any]:
    """저장된 일정 한 건 + 현재 시각 -> 화면에 필요한 계산 결과.

    task 필수 키: kind, reset_time, reset_weekday, due_time, due_weekday,
                  due_at, last_completed_at
    """
    kind = task["kind"]
    last_done = parse_dt(task["last_completed_at"]) if task.get("last_completed_at") else None

    cycle_start = cycle_end = None
    reset_in = None
    closed_at = None

    if kind == "once":
        due = parse_dt(task["due_at"]) if task.get("due_at") else None
        done = last_done is not None
        if done:
            closed_at = last_done
    else:
        cycle_start, cycle_end = cycle_bounds(kind, task["reset_time"], task["reset_weekday"], now)
        due = cycle_due(task, cycle_start, cycle_end)
        done = last_done is not None and last_done >= cycle_start
        reset_in = int((cycle_end - now).total_seconds())

    if done:
        status = DONE
    elif due is not None and now >= due:
        status = MISSED
        if kind == "once":
            closed_at = due
    else:
        status = PENDING

    remaining = int((due - now).total_seconds()) if (status == PENDING and due) else None

    return {
        "status": status,
        "due_at": fmt_dt(due),
        "cycle_start": fmt_dt(cycle_start),
        "cycle_end": fmt_dt(cycle_end),
        "remaining_sec": remaining,
        "reset_in_sec": reset_in,
        "closed_at": fmt_dt(closed_at),
        "can_complete": status == PENDING,
    }


_STATUS_ORDER = {PENDING: 0, MISSED: 1, DONE: 2}


def sort_key(item: dict[str, Any]):
    """진행 중(마감 임박순, 마감 없음은 뒤) -> 마감 초과 -> 완료."""
    rem = item["remaining_sec"]
    return (_STATUS_ORDER[item["status"]],
            rem if rem is not None else float("inf"),
            item["title"])


def is_hidden_closed_once(item: dict[str, Any], now: datetime, keep_days: int) -> bool:
    """종료된 일회성 일정은 keep_days일이 지나면 기본 목록에서 숨긴다(DB에는 남음)."""
    if item["kind"] != "once" or item["status"] == PENDING or not item["closed_at"]:
        return False
    return now - parse_dt(item["closed_at"]) > timedelta(days=keep_days)
