"""일정 추가/수정 창, 서버 설정 창."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDateTime, QTime, Qt
from PySide6.QtWidgets import (QAbstractSpinBox, QCheckBox, QComboBox, QDateTimeEdit, QDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
                               QTimeEdit, QVBoxLayout, QWidget)

from .util import WEEKDAY_KR, pdt

KIND_ITEMS = [("매일 반복", "daily"), ("매주 반복", "weekly"), ("한 번만(마감일)", "once")]


def _time(hm: str | None, default="00:00") -> QTime:
    h, m = (hm or default).split(":")
    return QTime(int(h), int(m))


class TaskDialog(QDialog):
    def __init__(self, parent=None, task: dict | None = None, now: datetime | None = None,
                 default_kind: str = "daily"):
        super().__init__(parent)
        self.setWindowTitle("일정 수정" if task else "일정 추가")
        self.setMinimumWidth(420)
        now = now or datetime.now()
        t = task or {}

        self.title = QLineEdit(t.get("title", ""))
        self.title.setPlaceholderText("할 일을 입력하세요")
        self.note = QPlainTextEdit(t.get("note", ""))
        self.note.setPlaceholderText("메모 (선택)")
        self.note.setFixedHeight(60)

        self.kind = QComboBox()
        for label, val in KIND_ITEMS:
            self.kind.addItem(label, val)
        self.kind.setCurrentIndex([v for _, v in KIND_ITEMS].index(t.get("kind", default_kind)))

        # 반복 일정 옵션
        self.reset_wd = QComboBox()
        for i, n in enumerate(WEEKDAY_KR):
            self.reset_wd.addItem(f"{n}요일", i)
        self.reset_wd.setCurrentIndex(t.get("reset_weekday") if t.get("reset_weekday") is not None else 0)
        self.reset_time = QTimeEdit(_time(t.get("reset_time")))
        self.reset_time.setDisplayFormat("HH:mm")
        self.reset_time.setButtonSymbols(QAbstractSpinBox.NoButtons)

        self.use_due = QCheckBox("마감 시각 지정 (안 하면 다음 초기화 시점이 마감)")
        self.use_due.setChecked(bool(t.get("due_time")))
        self.due_wd = QComboBox()
        for i, n in enumerate(WEEKDAY_KR):
            self.due_wd.addItem(f"{n}요일", i)
        self.due_wd.setCurrentIndex(t.get("due_weekday") if t.get("due_weekday") is not None else 0)
        self.due_time = QTimeEdit(_time(t.get("due_time"), "22:00"))
        self.due_time.setDisplayFormat("HH:mm")
        self.due_time.setButtonSymbols(QAbstractSpinBox.NoButtons)

        # 일회성 옵션
        self.use_dt = QCheckBox("마감일 지정")
        due = pdt(t.get("due_at"))
        self.use_dt.setChecked(bool(due) or (not t and default_kind == "once"))
        base = due or now.replace(hour=23, minute=59, second=0, microsecond=0)
        self.due_dt = QDateTimeEdit(QDateTime(base.year, base.month, base.day, base.hour, base.minute, 0))
        self.due_dt.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.due_dt.setCalendarPopup(True)

        form = QFormLayout()
        form.addRow("제목", self.title)
        form.addRow("메모", self.note)
        form.addRow("종류", self.kind)
        self.rows: dict[str, list[QWidget]] = {}

        def add(key, label, w):
            form.addRow(label, w)
            self.rows[key] = [form.labelForField(w), w]

        add("rwd", "초기화 요일", self.reset_wd)
        add("rt", "초기화 시각", self.reset_time)
        add("ud", "", self.use_due)
        add("dwd", "마감 요일", self.due_wd)
        add("dt", "마감 시각", self.due_time)
        add("ud2", "", self.use_dt)
        add("ddt", "마감", self.due_dt)

        self.err = QLabel("")
        self.err.setStyleSheet("color:#E5484D")
        ok = QPushButton("저장"); ok.setObjectName("primary"); ok.setDefault(True)
        cancel = QPushButton("취소")
        ok.clicked.connect(self._accept)
        cancel.clicked.connect(self.reject)
        btns = QHBoxLayout(); btns.addStretch(); btns.addWidget(cancel); btns.addWidget(ok)
        lay = QVBoxLayout(self); lay.addLayout(form); lay.addWidget(self.err); lay.addLayout(btns)

        self.kind.currentIndexChanged.connect(self._sync)
        self.use_due.toggled.connect(self._sync)
        self.use_dt.toggled.connect(self._sync)
        self._sync()
        self.title.setFocus()

    def _show(self, key, visible):
        for w in self.rows[key]:
            if w is not None:
                w.setVisible(visible)

    def _sync(self):
        k = self.kind.currentData()
        rec = k in ("daily", "weekly")
        self._show("rwd", k == "weekly")
        self._show("rt", rec)
        self._show("ud", rec)
        self._show("dwd", k == "weekly" and self.use_due.isChecked())
        self._show("dt", rec and self.use_due.isChecked())
        self._show("ud2", k == "once")
        self._show("ddt", k == "once" and self.use_dt.isChecked())
        self.adjustSize()

    def _accept(self):
        if not self.title.text().strip():
            self.err.setText("제목을 입력해 주세요.")
            return
        self.accept()

    def payload(self) -> dict:
        k = self.kind.currentData()
        d = {"title": self.title.text().strip(), "note": self.note.toPlainText().strip(), "kind": k,
             "reset_time": None, "reset_weekday": None, "due_time": None, "due_weekday": None,
             "due_at": None}
        if k in ("daily", "weekly"):
            d["reset_time"] = self.reset_time.time().toString("HH:mm")
            if k == "weekly":
                d["reset_weekday"] = self.reset_wd.currentData()
            if self.use_due.isChecked():
                d["due_time"] = self.due_time.time().toString("HH:mm")
                if k == "weekly":
                    d["due_weekday"] = self.due_wd.currentData()
        elif self.use_dt.isChecked():
            d["due_at"] = self.due_dt.dateTime().toString("yyyy-MM-ddTHH:mm:00")
        return d


class ServerDialog(QDialog):
    """서버 주소 입력 + 연결 테스트."""

    def __init__(self, parent, url: str, test_fn):
        super().__init__(parent)
        self.setWindowTitle("서버 연결 설정")
        self.setMinimumWidth(440)
        self.test_fn = test_fn
        self.url = QLineEdit(url)
        self.url.setPlaceholderText("예) http://100.64.0.1:8765  (서버 실행 창에 표시된 주소)")
        self.result = QLabel("")
        self.result.setWordWrap(True)
        test = QPushButton("연결 테스트")
        ok = QPushButton("저장"); ok.setObjectName("primary")
        cancel = QPushButton("취소")
        test.clicked.connect(self._test)
        ok.clicked.connect(self._save)
        cancel.clicked.connect(self.reject)
        row = QHBoxLayout(); row.addWidget(test); row.addStretch(); row.addWidget(cancel); row.addWidget(ok)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("서버 PC에서 서버를 실행하면 접속 주소가 표시됩니다.\n그 주소를 아래에 입력해 주세요."))
        lay.addWidget(self.url); lay.addWidget(self.result); lay.addLayout(row)

    def value(self) -> str:
        u = self.url.text().strip().rstrip("/")
        if u and not u.startswith(("http://", "https://")):
            u = "http://" + u
        return u

    def _test(self):
        self.result.setText("연결 확인 중…")
        self.result.repaint()
        ok, msg = self.test_fn(self.value())
        self.result.setStyleSheet("color:#2FA866" if ok else "color:#E5484D")
        self.result.setText(("✔ " if ok else "✘ ") + msg)

    def _save(self):
        if not self.value():
            self.result.setStyleSheet("color:#E5484D")
            self.result.setText("주소를 입력해 주세요.")
            return
        self.accept()
