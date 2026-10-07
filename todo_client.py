"""클라이언트 실행 파일 진입점 (PyInstaller 빌드 대상)."""
import sys

from client.app import main

if __name__ == "__main__":
    sys.exit(main())
