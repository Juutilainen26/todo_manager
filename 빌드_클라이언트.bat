@echo off
chcp 65001 >nul
title 일정 관리 클라이언트 빌드
cd /d "%~dp0"
if not exist ".venv-build\Scripts\python.exe" python -m venv .venv-build
".venv-build\Scripts\python.exe" -m pip install -r requirements-client.txt pyinstaller
".venv-build\Scripts\python.exe" -m PyInstaller --noconfirm --noconsole --name TodoManager todo_client.py
echo.
echo 완료! dist\TodoManager 폴더 안의 TodoManager.exe 를 실행하세요.
echo (폴더 통째로 다른 PC에 복사해서 쓰면 됩니다.)
pause
