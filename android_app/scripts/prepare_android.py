"""안드로이드 빌드 준비 스크립트 (GitHub Actions 에서 실행, 로컬에서도 실행 가능).

  python android_app/scripts/prepare_android.py web
      server/web 의 화면 파일을 android_app/www 로 복사한다. (화면은 이 한 곳만 고치면 PC/폰 공통)
  python android_app/scripts/prepare_android.py patch --version 1.2.3
      `npx cap add android` 로 생긴 android/ 프로젝트에 우리 설정을 적용한다.
      - 매니페스트: http(Tailscale) 주소 접속 허용
      - 버전 이름/번호
      - 앱 아이콘, 시작 화면
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]            # android_app/
REPO = APP.parent
WEB_SRC = REPO / "server" / "web"
WWW = APP / "www"
ANDROID = APP / "android"
RES = ANDROID / "app" / "src" / "main" / "res"
ACCENT = (0x4C, 0x6F, 0xFF)
SPLASH_BG = (0xF5, 0xF6, 0xF8)


def copy_web() -> None:
    if not (WEB_SRC / "index.html").exists():
        sys.exit(f"화면 파일을 찾을 수 없어요: {WEB_SRC}")
    if WWW.exists():
        shutil.rmtree(WWW)
    shutil.copytree(WEB_SRC, WWW)
    print(f"[web] {WEB_SRC} -> {WWW} ({sum(1 for _ in WWW.iterdir())} files)")


def version_code(name: str) -> int:
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", name)
    if not m:
        sys.exit(f"버전은 1.2.3 형식이어야 해요: {name!r}")
    a, b, c = (int(x) for x in m.groups())
    if b > 99 or c > 99:
        sys.exit("버전의 가운데/끝 숫자는 99 이하여야 해요.")
    return a * 10000 + b * 100 + c


def patch_manifest() -> None:
    p = ANDROID / "app" / "src" / "main" / "AndroidManifest.xml"
    s = p.read_text(encoding="utf-8")
    if "usesCleartextTraffic" not in s:
        s, n = re.subn(r"<application\b", '<application\n        android:usesCleartextTraffic="true"', s, count=1)
        if n != 1:
            sys.exit("AndroidManifest.xml 에서 <application> 을 찾지 못했어요.")
    if "android.permission.INTERNET" not in s:
        sys.exit("INTERNET 권한이 매니페스트에 없어요.")
    p.write_text(s, encoding="utf-8")
    print("[manifest] usesCleartextTraffic=true")


def patch_version(name: str) -> None:
    p = ANDROID / "app" / "build.gradle"
    s = p.read_text(encoding="utf-8")
    code = version_code(name)
    s, n1 = re.subn(r"versionCode\s+\d+", f"versionCode {code}", s, count=1)
    s, n2 = re.subn(r'versionName\s+"[^"]*"', f'versionName "{name}"', s, count=1)
    if n1 != 1 or n2 != 1:
        sys.exit("app/build.gradle 에서 versionCode/versionName 을 찾지 못했어요.")
    p.write_text(s, encoding="utf-8")
    print(f"[version] name={name} code={code}")


def make_icons() -> None:
    from PIL import Image, ImageDraw

    src = Image.open(WEB_SRC / "icon-512.png").convert("RGBA")
    # 시작 아이콘(구형 기기용): 전체 아이콘 / 원형
    for d in RES.glob("mipmap-*dpi"):
        ref = Image.open(d / "ic_launcher.png")
        size = ref.size[0]
        icon = src.resize((size, size), Image.LANCZOS)
        icon.save(d / "ic_launcher.png")
        mask = Image.new("L", (size * 4, size * 4), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
        mask = mask.resize((size, size), Image.LANCZOS)
        flat = Image.new("RGBA", (size, size), ACCENT + (255,))
        flat.alpha_composite(icon)
        round_icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        round_icon.paste(flat, (0, 0), mask)
        round_icon.save(d / "ic_launcher_round.png")
        # 적응형 아이콘 전경: 108dp 캔버스 중앙 62% (안전 영역)
        fsize = Image.open(d / "ic_launcher_foreground.png").size[0]
        inner = int(fsize * 0.62)
        fg = Image.new("RGBA", (fsize, fsize), (0, 0, 0, 0))
        fg.alpha_composite(src.resize((inner, inner), Image.LANCZOS), ((fsize - inner) // 2, (fsize - inner) // 2))
        fg.save(d / "ic_launcher_foreground.png")
    bg = RES / "values" / "ic_launcher_background.xml"
    bg.write_text('<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="ic_launcher_background">#4C6FFF</color>\n</resources>\n', encoding="utf-8")
    # 시작 화면: 기본 Capacitor 로고 대신 우리 아이콘
    n = 0
    for f in RES.glob("drawable*/splash.png"):
        w, h = Image.open(f).size
        canvas = Image.new("RGBA", (w, h), SPLASH_BG + (255,))
        side = int(min(w, h) * 0.28)
        canvas.alpha_composite(src.resize((side, side), Image.LANCZOS), ((w - side) // 2, (h - side) // 2))
        canvas.convert("RGB").save(f)
        n += 1
    print(f"[icons] launcher icons + {n} splash images")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("web")
    pp = sub.add_parser("patch")
    pp.add_argument("--version", required=True)
    a = ap.parse_args()
    if a.cmd == "web":
        copy_web()
    else:
        if not ANDROID.exists():
            sys.exit("android/ 폴더가 없어요. 먼저 `npx cap add android` 를 실행하세요.")
        patch_manifest()
        patch_version(a.version)
        make_icons()


if __name__ == "__main__":
    main()
