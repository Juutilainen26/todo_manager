"""화면 표시용 순수 함수 (Qt 의존 없음 -> 단위 테스트 가능)."""
from __future__ import annotations

from datetime import datetime

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]
KIND_KR = {"daily": "매일", "weekly": "매주", "once": "한 번"}


def pdt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def fmt_span(sec: int) -> str:
    """초 -> '3일 4시간' / '2시간 15분' / '12분' / '1분 미만'."""
    sec = max(0, int(sec))
    d, r = divmod(sec, 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    if d:
        return f"{d}일 {h}시간" if h else f"{d}일"
    if h:
        return f"{h}시간 {m}분" if m else f"{h}시간"
    if m:
        return f"{m}분"
    return "1분 미만"


def fmt_due(dt: datetime, now: datetime) -> str:
    """마감 시각 표기: 오늘/내일이면 '오늘 18:00', 아니면 '10/12(월) 18:00'."""
    delta = (dt.date() - now.date()).days
    hm = dt.strftime("%H:%M")
    if delta == 0:
        return f"오늘 {hm}"
    if delta == 1:
        return f"내일 {hm}"
    return f"{dt.month}/{dt.day}({WEEKDAY_KR[dt.weekday()]}) {hm}"


def rule_text(t: dict) -> str:
    """일정의 반복/초기화 규칙 설명."""
    k = t["kind"]
    if k == "daily":
        s = f"매일 {t['reset_time']} 초기화"
        if t.get("due_time"):
            s += f" · 마감 {t['due_time']}"
        return s
    if k == "weekly":
        s = f"매주 {WEEKDAY_KR[t['reset_weekday']]} {t['reset_time']} 초기화"
        if t.get("due_time"):
            s += f" · 마감 {WEEKDAY_KR[t['due_weekday']]} {t['due_time']}"
        return s
    due = pdt(t.get("due_at"))
    return f"마감 {due.month}/{due.day}({WEEKDAY_KR[due.weekday()]}) {due.strftime('%H:%M')}" if due else "기한 없음"


def has_explicit_due(t: dict) -> bool:
    return t["kind"] == "once" and bool(t.get("due_at")) or bool(t.get("due_time"))


def right_text(t: dict, now: datetime) -> tuple[str, str]:
    """(표시 문구, 색상 키) -> 행 오른쪽에 표시."""
    status = t["status"]
    due = t.get("_due")
    end = t.get("_end")  # 반복 일정의 다음 초기화 시각
    reset = f" · {fmt_span((end - now).total_seconds())} 후 초기화" if end else ""
    if status == "done":
        return "✔ 완료" + reset, "ok"
    if status == "missed":
        return "마감 초과" + reset, "danger"
    if due is None:
        return "기한 없음", "sub"
    rem = (due - now).total_seconds()
    label = f"{fmt_span(rem)} 남음" if has_explicit_due(t) else f"초기화까지 {fmt_span(rem)}"
    if rem <= 600:
        return label, "danger"
    if rem <= 3600:
        return label, "warn"
    return label, "text"


def expiry(t: dict) -> datetime | None:
    """이 시각이 지나면 서버 상태가 바뀌므로 다시 조회해야 한다."""
    if t["status"] == "pending":
        return t.get("_due")
    return t.get("_end")  # 완료/마감초과 반복 일정은 다음 초기화 때 부활
