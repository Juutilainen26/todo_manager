"""할일 목록: 모델 + 행 그리기(Delegate). 보이는 행만 그려서 수천 건도 빠르다."""
from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QAbstractListModel, QEvent, QModelIndex, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QListView, QStyle, QStyledItemDelegate

from . import util
from .style import COLORS, ROW_HEIGHT

TAB_ALL, TAB_TODAY, TAB_DAILY, TAB_WEEKLY, TAB_UPCOMING = range(5)
TAB_NAMES = ["전체", "오늘", "매일", "주간", "앞으로"]
TASK_ROLE = Qt.UserRole + 1


def prepare(t: dict) -> dict:
    """서버 응답 한 건에 계산용 datetime 필드를 붙인다."""
    t["_due"] = util.pdt(t.get("due_at"))
    t["_end"] = util.pdt(t.get("cycle_end")) if t["kind"] != "once" else None
    t["_exp"] = util.expiry(t)
    return t


class TaskModel(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self.all: list[dict] = []
        self.rows: list[dict] = []
        self.offset = timedelta(0)  # 서버 시각 - 이 PC 시각
        self.tab = TAB_ALL
        self.text = ""
        self.only_pending = False

    # ---- 시간
    def now(self) -> datetime:
        return datetime.now().replace(microsecond=0) + self.offset

    # ---- 데이터 설정/필터
    def set_tasks(self, tasks: list[dict], server_now: str):
        self.offset = datetime.fromisoformat(server_now) - datetime.now().replace(microsecond=0)
        self.all = [prepare(t) for t in tasks]
        self._refilter()

    # ---- 부분 갱신(서버 응답/낙관적 반영용): 전체 재조회 없이 한 건만 바꾼다
    def _sort_key(self, t: dict):
        order = {"pending": 0, "missed": 1, "done": 2}[t["status"]]
        rem = (t["_due"] - self.now()).total_seconds() if (t["status"] == "pending" and t["_due"]) else float("inf")
        return (order, rem, t["title"])

    def upsert(self, t: dict):
        t = prepare(dict(t))
        for i, x in enumerate(self.all):
            if x["id"] == t["id"]:
                self.all[i] = t
                break
        else:
            self.all.append(t)
        self.all.sort(key=self._sort_key)
        self._refilter()

    def remove(self, task_id: int):
        self.all = [x for x in self.all if x["id"] != task_id]
        self._refilter()

    def set_filter(self, tab=None, text=None, only_pending=None):
        if tab is not None: self.tab = tab
        if text is not None: self.text = text.strip().lower()
        if only_pending is not None: self.only_pending = only_pending
        self._refilter()

    def _match(self, t: dict, today) -> bool:
        if self.only_pending and t["status"] != "pending":
            return False
        if self.text and self.text not in (t["title"] + " " + (t.get("note") or "")).lower():
            return False
        k, due = t["kind"], t["_due"]
        if self.tab == TAB_DAILY: return k == "daily"
        if self.tab == TAB_WEEKLY: return k == "weekly"
        if self.tab == TAB_TODAY:
            return k == "daily" or (k == "once" and due is not None and due.date() == today)
        if self.tab == TAB_UPCOMING:
            return k == "once" and (due is None or due.date() > today)
        return True

    def _refilter(self):
        today = self.now().date()
        self.beginResetModel()
        self.rows = [t for t in self.all if self._match(t, today)]
        self.endResetModel()

    def counts(self) -> tuple[int, int]:
        """(진행 중, 전체) -- 현재 탭 기준"""
        return sum(1 for t in self.rows if t["status"] == "pending"), len(self.rows)

    def next_expiry(self) -> datetime | None:
        exps = [t["_exp"] for t in self.all if t["_exp"]]
        return min(exps) if exps else None

    def pending_with_due(self):
        return [t for t in self.all if t["status"] == "pending" and t["_due"]]

    # ---- Qt 모델 API
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid(): return None
        t = self.rows[index.row()]
        if role == TASK_ROLE: return t
        if role == Qt.DisplayRole: return t["title"]
        return None


class TaskDelegate(QStyledItemDelegate):
    toggled = Signal(dict)       # 체크 영역 클릭
    PAD = 8

    def __init__(self, model: TaskModel, parent=None):
        super().__init__(parent)
        self.m = model

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), ROW_HEIGHT)

    @staticmethod
    def _check_rect(r: QRect) -> QRect:
        return QRect(r.left() + 18, r.top() + (r.height() - 26) // 2, 26, 26)

    def paint(self, p: QPainter, option, index):
        t = index.data(TASK_ROLE)
        r = option.rect.adjusted(6, 3, -6, -3)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        hover = option.state & QStyle.State_MouseOver
        sel = option.state & QStyle.State_Selected
        p.setPen(QPen(QColor(COLORS["accent"] if sel else COLORS["line"]), 1.5 if sel else 1))
        p.setBrush(QColor(COLORS["card_hover"] if hover or sel else COLORS["card"]))
        p.drawRoundedRect(QRectF(r), 10, 10)

        status = t["status"]
        closed = status != "pending"
        now = self.m.now()

        # 체크 아이콘
        cr = self._check_rect(r)
        if status == "done":
            p.setBrush(QColor(COLORS["ok"])); p.setPen(Qt.NoPen); p.drawEllipse(cr)
            p.setPen(QPen(QColor("white"), 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPolyline([cr.topLeft() + p_ for p_ in (_pt(7, 13), _pt(11, 18), _pt(19, 8))])
        elif status == "missed":
            p.setBrush(QColor(COLORS["closed"])); p.setPen(Qt.NoPen); p.drawEllipse(cr)
            p.setPen(QPen(QColor("white"), 2.4, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(cr.topLeft() + _pt(8, 8), cr.topLeft() + _pt(18, 18))
            p.drawLine(cr.topLeft() + _pt(18, 8), cr.topLeft() + _pt(8, 18))
        else:
            p.setBrush(Qt.NoBrush); p.setPen(QPen(QColor(COLORS["line"]).darker(130), 2))
            p.drawEllipse(cr.adjusted(1, 1, -1, -1))

        # 오른쪽 텍스트
        rt, ck = util.right_text(t, now)
        f = QFont(p.font()); f.setPointSize(10); f.setBold(True)
        p.setFont(f)
        rw = p.fontMetrics().horizontalAdvance(rt) + 8
        right = QRect(r.right() - rw - 14, r.top(), rw, r.height())
        p.setPen(QColor(COLORS[ck] if not (closed and ck == "text") else COLORS["sub"]))
        p.drawText(right, Qt.AlignVCenter | Qt.AlignRight, rt)

        # 제목 / 부제
        tx = cr.right() + 14
        w = right.left() - tx - 10
        tf = QFont(p.font()); tf.setPointSize(11); tf.setBold(False); tf.setStrikeOut(closed)
        p.setFont(tf)
        p.setPen(QColor(COLORS["closed"] if closed else COLORS["text"]))
        title_rect = QRect(tx, r.top() + 7, w, 22)
        p.drawText(title_rect, Qt.AlignVCenter | Qt.AlignLeft,
                   p.fontMetrics().elidedText(t["title"], Qt.ElideRight, w))
        sf = QFont(p.font()); sf.setPointSize(9); sf.setStrikeOut(False)
        p.setFont(sf)
        p.setPen(QColor(COLORS["sub"]))
        sub = util.rule_text(t)
        if t["kind"] == "once" and t["_due"]:
            sub = f"마감 {util.fmt_due(t['_due'], now)}"
        if t.get("note"):
            sub += "  ·  " + t["note"].splitlines()[0]
        p.drawText(QRect(tx, r.top() + 30, w, 20), Qt.AlignVCenter | Qt.AlignLeft,
                   p.fontMetrics().elidedText(sub, Qt.ElideRight, w))
        p.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            r = option.rect.adjusted(6, 3, -6, -3)
            if self._check_rect(r).adjusted(-8, -8, 8, 8).contains(event.position().toPoint()):
                self.toggled.emit(index.data(TASK_ROLE))
                return True
        return False


def _pt(x, y):
    from PySide6.QtCore import QPoint
    return QPoint(x, y)


class TaskListView(QListView):
    def __init__(self, model: TaskModel):
        super().__init__()
        self.setModel(model)
        self.d = TaskDelegate(model, self)
        self.setItemDelegate(self.d)
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)           # 대량 목록 성능
        self.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.setSelectionMode(QListView.SingleSelection)
        self.setEditTriggers(QListView.NoEditTriggers)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
