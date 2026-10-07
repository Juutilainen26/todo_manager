"""메인 창: 빠른 입력 / 탭 / 검색 / 목록 / 트레이 / 알림 / 오프라인 처리."""
from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QByteArray, QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                               QMenu, QMessageBox, QPushButton, QSystemTrayIcon, QTabBar,
                               QVBoxLayout, QWidget)

from . import util
from .api_client import Api, ApiError, Offline
from .dialogs import ServerDialog, TaskDialog
from .settings import Cache, Settings
from .style import COLORS
from .task_view import TAB_NAMES, TAB_ALL, TAB_DAILY, TAB_TODAY, TAB_UPCOMING, TAB_WEEKLY, TaskListView, TaskModel

QUICK_KINDS = [("오늘", "today"), ("매일", "daily"), ("주간", "weekly"), ("앞으로", "future")]
TAB_TO_QUICK = {TAB_TODAY: 0, TAB_DAILY: 1, TAB_WEEKLY: 2, TAB_UPCOMING: 3}
OFFLINE_MSG = ("서버에 연결할 수 없어요. 서버 PC에서 '서버_실행.bat'을 실행했는지, "
               "Tailscale이 켜져 있는지 확인해 주세요. (저장된 마지막 목록을 보여드리는 중)")


def make_icon() -> QIcon:
    pm = QPixmap(64, 64); pm.fill(Qt.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(COLORS["accent"])); p.setPen(Qt.NoPen); p.drawEllipse(4, 4, 56, 56)
    p.setPen(QPen(QColor("white"), 6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPolyline([_p(18, 33), _p(28, 43), _p(46, 22)])
    p.end()
    return QIcon(pm)


def _p(x, y):
    from PySide6.QtCore import QPoint
    return QPoint(x, y)


class _Sig(QObject):
    finished = Signal(object, object)   # (콜백, 결과)  -> 항상 UI 스레드에서 처리


class _Job(QRunnable):
    def __init__(self, fn, ok, err, sig):
        super().__init__()
        self.fn, self.ok, self.err, self.sig = fn, ok, err, sig

    def run(self):
        try:
            r = self.fn()
        except Exception as e:  # noqa: BLE001
            self.sig.finished.emit(self.err, e)
        else:
            self.sig.finished.emit(self.ok, r)


class MainWindow(QMainWindow):
    POLL_ONLINE = 30   # 초
    POLL_OFFLINE = 5

    def __init__(self, settings: Settings | None = None, cache: Cache | None = None):
        super().__init__()
        self.settings = settings or Settings()
        self.cache = cache or Cache()
        self.api: Api | None = None
        self.online = False
        self._busy = False
        self._again = False
        self._quitting = False
        self._first_load = True
        self._since_poll = 0
        self._last_refresh = 0.0
        self.notified: set = set()
        self.pool = QThreadPool.globalInstance()
        self.sig = _Sig()
        self.sig.finished.connect(self._dispatch)

        self.setWindowTitle("일정 관리")
        self.setWindowIcon(make_icon())
        self.resize(760, 760)
        self.model = TaskModel()
        self._build_ui()
        self._build_tray()
        self._restore_geometry()
        self.set_server(self.settings["server_url"])

        # 저장된 목록을 먼저 보여준 뒤(즉시 표시) 서버에서 최신 값을 받아온다
        c = self.cache.load()
        if c and c.get("tasks") is not None:
            self.model.set_tasks(c["tasks"], c["server_now"])
            self.model.offset = timedelta(0)  # 캐시는 PC 시각 기준으로 표시
            self._update_status()

        self.timer = QTimer(self); self.timer.timeout.connect(self._tick); self.timer.start(1000)
        QTimer.singleShot(0, self._startup)

    # ------------------------------------------------------------ UI 구성
    def _build_ui(self):
        root = QWidget(); self.setCentralWidget(root)
        lay = QVBoxLayout(root); lay.setContentsMargins(16, 14, 16, 10); lay.setSpacing(10)

        # 빠른 입력
        self.quick = QLineEdit(); self.quick.setPlaceholderText("할 일 입력 후 Enter  (Ctrl+N)")
        self.quick_kind = QComboBox()
        for n, k in QUICK_KINDS:
            self.quick_kind.addItem(n, k)
        self.quick_kind.setCurrentIndex(int(self.settings["quick_kind"] or 0))
        add = QPushButton("추가"); add.setObjectName("primary")
        detail = QPushButton("＋ 자세히")
        gear = QPushButton("⚙")
        gear.setToolTip("서버 연결 설정"); gear.setFixedWidth(40)
        top = QHBoxLayout(); top.setSpacing(8)
        for w in (self.quick,): top.addWidget(w, 1)
        for w in (self.quick_kind, add, detail, gear): top.addWidget(w)
        lay.addLayout(top)
        self.quick.returnPressed.connect(self.quick_add)
        add.clicked.connect(self.quick_add)
        detail.clicked.connect(self.add_dialog)
        gear.clicked.connect(self.server_dialog)
        self.quick_kind.currentIndexChanged.connect(lambda i: self.settings.__setitem__("quick_kind", i))

        # 탭 + 검색
        self.tabs = QTabBar(); self.tabs.setExpanding(False); self.tabs.setDrawBase(False)
        for n in TAB_NAMES:
            self.tabs.addTab(n)
        self.search = QLineEdit(); self.search.setPlaceholderText("검색"); self.search.setFixedWidth(150)
        self.only_pending = QCheckBox("진행 중만")
        row = QHBoxLayout(); row.addWidget(self.tabs); row.addStretch()
        row.addWidget(self.search); row.addWidget(self.only_pending)
        lay.addLayout(row)
        self.tabs.currentChanged.connect(self._on_tab)
        self.search.textChanged.connect(lambda t: self._filter(text=t))
        self.only_pending.toggled.connect(lambda v: self._filter(only_pending=v))

        # 배너 + 목록 + 상태줄
        self.banner = QLabel(OFFLINE_MSG); self.banner.setObjectName("banner")
        self.banner.setWordWrap(True); self.banner.hide()
        lay.addWidget(self.banner)
        self.view = TaskListView(self.model)
        lay.addWidget(self.view, 1)
        self.status = QLabel(""); self.status.setObjectName("status")
        lay.addWidget(self.status)

        self.view.d.toggled.connect(self.toggle)
        self.view.doubleClicked.connect(lambda ix: self.edit_dialog(ix.data(Qt.UserRole + 1)))
        self.view.customContextMenuRequested.connect(self._context_menu)

        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.quick.setFocus)
        QShortcut(QKeySequence("F5"), self, activated=self.refresh)
        QShortcut(QKeySequence("Delete"), self.view, activated=lambda: self._sel(self.delete))
        QShortcut(QKeySequence("Space"), self.view, activated=lambda: self._sel(self.toggle))
        QShortcut(QKeySequence("Return"), self.view, activated=lambda: self._sel(self.edit_dialog))

    def _build_tray(self):
        self.tray = QSystemTrayIcon(make_icon(), self)
        self.tray.setToolTip("일정 관리")
        m = QMenu()
        m.addAction("열기", self.show_front)
        self.act_notify = QAction("알림 켜기", m, checkable=True)
        self.act_notify.setChecked(bool(self.settings["notify"]))
        self.act_notify.toggled.connect(lambda v: self.settings.__setitem__("notify", bool(v)))
        m.addAction(self.act_notify)
        m.addSeparator()
        m.addAction("종료", self.quit_app)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(lambda r: self.show_front() if r == QSystemTrayIcon.Trigger else None)
        self.tray.show()
        self._tray_menu = m

    # ------------------------------------------------------------ 창 동작
    def show_front(self):
        self.showNormal(); self.raise_(); self.activateWindow()

    def quit_app(self):
        self._quitting = True
        self._save_geometry()
        self.tray.hide()
        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    def closeEvent(self, e):
        self._save_geometry()
        if self._quitting or not QSystemTrayIcon.isSystemTrayAvailable():
            e.accept(); return
        e.ignore(); self.hide()
        if not self.settings["tray_hint"]:
            self.tray.showMessage("일정 관리", "트레이에서 계속 실행 중이에요. 완전히 끄려면 트레이 아이콘 → 종료",
                                  QSystemTrayIcon.Information, 5000)
            self.settings["tray_hint"] = True

    def _save_geometry(self):
        self.settings["geometry"] = bytes(self.saveGeometry().toHex()).decode()

    def _restore_geometry(self):
        g = self.settings["geometry"]
        if g:
            self.restoreGeometry(QByteArray.fromHex(g.encode()))

    # ------------------------------------------------------------ 비동기 헬퍼
    def _dispatch(self, cb, payload):
        if cb:
            cb(payload)

    def run(self, fn, ok=None, err=None):
        self.pool.start(_Job(fn, ok, err, self.sig))

    def flash(self, msg: str, ms: int = 4000):
        self.status.setText(msg)
        QTimer.singleShot(ms, self._update_status)

    # ------------------------------------------------------------ 서버/동기화
    def set_server(self, url: str | None):
        self.api = Api(url) if url else None

    def _startup(self):
        if not self.api:
            self.server_dialog(first=True)
        else:
            self.refresh()

    def server_dialog(self, first=False):
        def test(url):
            try:
                Api(url, timeout=3).health(); return True, "서버에 연결되었습니다."
            except Offline:
                return False, "연결할 수 없어요. 주소/서버 실행/Tailscale 상태를 확인해 주세요."
            except Exception as e:  # noqa: BLE001
                return False, f"응답이 이상해요: {e}"
        d = ServerDialog(self, self.settings["server_url"] or "", test)
        if d.exec():
            self.settings["server_url"] = d.value()
            self.set_server(d.value())
            self._first_load = True
            self.refresh()

    def refresh(self):
        if not self.api:
            return
        if self._busy:
            self._again = True
            return
        self._busy = True
        self._since_poll = 0
        api, days = self.api, int(self.settings["keep_closed_days"] or 3)
        self.run(lambda: api.list(days), self._on_list, self._on_list_err)

    def _on_list(self, res):
        self._busy = False
        prev = {t["id"]: t for t in self.model.all}
        self.model.set_tasks(res["tasks"], res["server_now"])
        self.cache.save(res)
        if not self.online:
            self.online = True
        self.banner.hide()
        self._notify_missed(prev)
        self._check_notifications()
        self._first_load = False
        self._update_status()
        if self._again:
            self._again = False; self.refresh()

    def _on_list_err(self, e):
        self._busy = False
        self.online = False
        self.banner.show()
        self._update_status()

    def _update_status(self):
        pend, total = self.model.counts()
        conn = "● 연결됨" if self.online else "○ 오프라인"
        self.status.setText(f"{conn}   |   진행 중 {pend} / 표시 {total}   |   전체 {len(self.model.all)}건")

    # ------------------------------------------------------------ 주기 작업
    def _tick(self):
        self.view.viewport().update()               # 남은 시간 갱신(보이는 행만 다시 그림)
        self._since_poll += 1
        exp = self.model.next_expiry()
        interval = self.POLL_ONLINE if self.online else self.POLL_OFFLINE
        due_now = exp is not None and self.model.now() >= exp and self._since_poll >= 2
        if self.api and (self._since_poll >= interval or due_now):
            self.refresh()
        if self._since_poll % 20 == 0:
            self._check_notifications()

    # ------------------------------------------------------------ 알림
    def _notify(self, title: str, tasks: list[dict]):
        if not self.settings["notify"] or not tasks:
            return
        names = [t["title"] for t in tasks]
        body = "\n".join("• " + n for n in names[:4]) + (f"\n… 외 {len(names) - 4}건" if len(names) > 4 else "")
        self.tray.showMessage(title, body, QSystemTrayIcon.Warning, 10000)

    def _check_notifications(self):
        now = self.model.now()
        hits: dict[int, list] = {10: [], 60: []}
        for t in self.model.pending_with_due():
            rem = (t["_due"] - now).total_seconds()
            crossed = [lv for lv, th in ((10, 600), (60, 3600)) if rem <= th]
            if not crossed:
                continue
            keys = [(t["id"], t["due_at"], lv) for lv in crossed]
            fresh = keys[0] not in self.notified   # 가장 임박한 단계 기준
            self.notified.update(keys)
            if fresh and not self._first_load:
                hits[crossed[0]].append(t)
        self._notify("⏰ 마감 10분 이내", hits[10])
        self._notify("마감 1시간 이내", hits[60])

    def _notify_missed(self, prev: dict):
        if self._first_load:
            return
        newly = []
        for t in self.model.all:
            old = prev.get(t["id"])
            if t["status"] == "missed" and old and old["status"] == "pending" and old["due_at"] == t["due_at"]:
                newly.append(t)
        self._notify("❗ 마감 초과", newly)

    # ------------------------------------------------------------ 필터/탭
    def _on_tab(self, i):
        self._filter(tab=i)
        if i in TAB_TO_QUICK:
            self.quick_kind.setCurrentIndex(TAB_TO_QUICK[i])

    def _filter(self, **kw):
        self.model.set_filter(**kw)
        self._update_status()

    # ------------------------------------------------------------ 일정 조작
    def _sel(self, fn):
        ix = self.view.currentIndex()
        if ix.isValid():
            fn(ix.data(Qt.UserRole + 1))

    def _action(self, fn, ok_msg: str | None = None):
        if not self.api:
            return self.server_dialog()

        def done(_):
            if ok_msg:
                self.flash(ok_msg, 2000)
            self.refresh()

        def fail(e):
            if isinstance(e, ApiError):
                QMessageBox.warning(self, "처리할 수 없어요", str(e))
            else:
                QMessageBox.warning(self, "서버 연결 실패", OFFLINE_MSG)
            self.refresh()
        self.run(fn, done, fail)

    def quick_add(self):
        title = self.quick.text().strip()
        if not title:
            return
        k = self.quick_kind.currentData()
        now = self.model.now()
        data = {"title": title}
        if k == "today":
            data |= {"kind": "once", "due_at": now.strftime("%Y-%m-%dT23:59:00")}
        elif k == "daily":
            data |= {"kind": "daily", "reset_time": "00:00"}
        elif k == "weekly":
            data |= {"kind": "weekly", "reset_weekday": 0, "reset_time": "00:00"}
        else:
            data |= {"kind": "once"}
        self.quick.clear()
        api = self.api
        self._action(lambda: api.create(data), "추가했어요")

    def add_dialog(self):
        d = TaskDialog(self, now=self.model.now(), default_kind="daily")
        if d.exec():
            data, api = d.payload(), self.api
            self._action(lambda: api.create(data), "추가했어요")

    def edit_dialog(self, t: dict):
        d = TaskDialog(self, task=t, now=self.model.now())
        if d.exec():
            data, api, tid = d.payload(), self.api, t["id"]
            self._action(lambda: api.update(tid, data), "수정했어요")

    def toggle(self, t: dict):
        api, tid = self.api, t["id"]
        if t["status"] == "pending":
            self._action(lambda: api.complete(tid))
        elif t["status"] == "done":
            self._action(lambda: api.uncomplete(tid))
        else:
            self.flash("마감이 지난 일정은 완료 처리할 수 없어요.")

    def delete(self, t: dict):
        if QMessageBox.question(self, "삭제", f"'{t['title']}' 일정을 삭제할까요?\n(완료 기록도 함께 삭제돼요)") \
                == QMessageBox.Yes:
            api, tid = self.api, t["id"]
            self._action(lambda: api.delete(tid), "삭제했어요")

    def _context_menu(self, pos):
        ix = self.view.indexAt(pos)
        if not ix.isValid():
            return
        t = ix.data(Qt.UserRole + 1)
        m = QMenu(self)
        if t["status"] == "pending":
            m.addAction("완료 처리", lambda: self.toggle(t))
        elif t["status"] == "done":
            m.addAction("미완료로 되돌리기", lambda: self.toggle(t))
        m.addAction("수정", lambda: self.edit_dialog(t))
        m.addAction("삭제", lambda: self.delete(t))
        m.exec(self.view.viewport().mapToGlobal(pos))
