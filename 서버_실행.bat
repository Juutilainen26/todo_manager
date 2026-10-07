@echo off
chcp 65001 >nul
title 일정 관리 서버
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [최초 1회] 가상환경을 만들고 서버 패키지를 설치합니다...
  python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -r requirements-server.txt
)
".venv\Scripts\python.exe" run_server.py
echo.
echo 서버가 종료되었습니다.
pause
