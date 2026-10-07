"""클라이언트 진입점."""
import sys

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication, QMessageBox

from .main_window import MainWindow, make_icon
from .settings import app_dir
from .style import QSS


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("일정 관리")
    app.setQuitOnLastWindowClosed(False)   # 창을 닫아도 트레이에서 계속 실행
    app.setStyleSheet(QSS)
    app.setWindowIcon(make_icon())

    lock = QLockFile(str(app_dir() / "app.lock"))
    if not lock.tryLock(100):
        QMessageBox.information(None, "일정 관리", "이미 실행 중이에요. 트레이 아이콘을 확인해 주세요.")
        return 0

    win = MainWindow()
    win.show()
    return app.exec()
