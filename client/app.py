"""클라이언트 진입점."""
import sys

from PySide6.QtCore import QLockFile, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox

from .main_window import MainWindow, make_icon
from .settings import app_dir
from .style import COLORS, build_qss


def _arrow_png() -> str:
    """콤보박스 화살표 아이콘을 만들어 파일로 저장하고 경로(슬래시 형식)를 돌려준다."""
    path = app_dir() / "arrow.png"
    pm = QPixmap(24, 24); pm.fill(Qt.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(COLORS["sub"]), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    from PySide6.QtCore import QPoint
    p.drawPolyline([QPoint(5, 9), QPoint(12, 16), QPoint(19, 9)])
    p.end()
    pm.save(str(path))
    return str(path).replace("\\", "/")


def _install_crash_log():
    """exe(콘솔 없음)에서는 에러 메시지가 보이지 않으므로 파일로 남긴다."""
    import traceback
    from datetime import datetime

    def hook(exc_type, exc, tb):
        try:
            with open(app_dir() / "error.log", "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}]\n")
                f.write("".join(traceback.format_exception(exc_type, exc, tb)))
        except Exception:  # noqa: BLE001
            pass
    sys.excepthook = hook


def main():
    _install_crash_log()
    app = QApplication(sys.argv)
    app.setApplicationName("일정 관리")
    app.setQuitOnLastWindowClosed(False)   # 창을 닫아도 트레이에서 계속 실행
    app.setStyleSheet(build_qss(_arrow_png()))
    app.setWindowIcon(make_icon())

    lock = QLockFile(str(app_dir() / "app.lock"))
    if not lock.tryLock(100):
        QMessageBox.information(None, "일정 관리", "이미 실행 중이에요. 트레이 아이콘을 확인해 주세요.")
        return 0

    win = MainWindow()
    win.show()
    return app.exec()
