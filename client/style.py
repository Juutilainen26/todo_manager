"""화면 색/글꼴/스타일시트 한 곳에 모음 -> 사용해 보고 UI를 고칠 때 이 파일 위주로 수정."""

COLORS = {
    "bg": "#F5F6F8",
    "card": "#FFFFFF",
    "card_hover": "#F0F4FF",
    "text": "#1F2430",
    "sub": "#7A8294",
    "line": "#E3E6EC",
    "accent": "#4C6FFF",
    "ok": "#2FA866",
    "warn": "#E8890C",
    "danger": "#E5484D",
    "closed": "#A3A9B8",
}

ROW_HEIGHT = 58
FONT_FAMILY = "Malgun Gothic"  # 윈도우 기본 한글 글꼴 (없으면 시스템 기본으로 대체됨)

QSS = f"""
QMainWindow, QDialog {{ background: {COLORS['bg']}; }}
QWidget {{ font-family: '{FONT_FAMILY}'; color: {COLORS['text']}; font-size: 13px; }}
QLineEdit, QComboBox, QTimeEdit, QDateTimeEdit, QPlainTextEdit {{
    background: {COLORS['card']}; border: 1px solid {COLORS['line']};
    border-radius: 8px; padding: 6px 10px; }}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border: 1px solid {COLORS['accent']}; }}
QPushButton {{ background: {COLORS['card']}; border: 1px solid {COLORS['line']};
    border-radius: 8px; padding: 7px 14px; }}
QPushButton:hover {{ background: {COLORS['card_hover']}; }}
QPushButton#primary {{ background: {COLORS['accent']}; color: white; border: none; font-weight: bold; }}
QPushButton#primary:hover {{ background: #3F5FE6; }}
QPushButton#danger {{ color: {COLORS['danger']}; }}
QTabBar::tab {{ background: transparent; padding: 8px 16px; border: none;
    color: {COLORS['sub']}; font-weight: bold; }}
QTabBar::tab:selected {{ color: {COLORS['accent']}; border-bottom: 3px solid {COLORS['accent']}; }}
QListView {{ background: transparent; border: none; outline: none; }}
QLabel#banner {{ background: {COLORS['danger']}; color: white; padding: 8px 12px; border-radius: 8px; }}
QLabel#status {{ color: {COLORS['sub']}; font-size: 12px; }}
QCheckBox {{ spacing: 6px; }}
"""
