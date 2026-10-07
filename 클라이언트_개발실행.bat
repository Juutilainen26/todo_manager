@echo off
chcp 65001 >nul
title 일정 관리 클라이언트
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" python -m venv .venv
echo 필요한 패키지를 확인하는 중입니다... (처음엔 몇 분 걸릴 수 있어요)
".venv\Scripts\python.exe" -m pip install -q -r requirements-client.txt
if errorlevel 1 (
  echo.
  echo 패키지 설치에 실패했습니다. 위 메시지를 확인해 주세요.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" todo_client.py
if errorlevel 1 (
  echo.
  echo 프로그램이 오류로 종료되었습니다. 위 메시지를 확인해 주세요.
  pause
)
