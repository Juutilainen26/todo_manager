"""서버 실행: python run_server.py [--host 0.0.0.0] [--port 8765]

상시 ON PC에서 이 프로그램을 직접 실행해 두면, 클라이언트 exe가 접속한다.
(PC를 껐다 켰다면 이 서버를 다시 실행해야 한다.)
"""
import argparse
import socket
import subprocess
import sys
from pathlib import Path

import uvicorn

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from server.api import create_app  # noqa: E402


def tailscale_ip() -> str | None:
    try:
        out = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=3)
        ip = out.stdout.strip().splitlines()[0] if out.returncode == 0 and out.stdout.strip() else None
        return ip
    except Exception:  # noqa: BLE001
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--db", default=str(BASE / "data" / "todo.db"))
    args = ap.parse_args()

    ts = tailscale_ip()
    print("=" * 56)
    print(" 일정 관리 서버 실행 중  (이 창을 닫으면 서버가 종료됩니다)")
    print(f" 포트        : {args.port}")
    if ts:
        print(f" 클라이언트 접속 주소 : http://{ts}:{args.port}   (Tailscale)")
    else:
        print(f" 클라이언트 접속 주소 : http://{socket.gethostname()}:{args.port}")
    print(f" 데이터 파일 : {args.db}")
    print("=" * 56)
    uvicorn.run(create_app(args.db), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
