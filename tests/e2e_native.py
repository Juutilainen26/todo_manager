"""앱(Capacitor) 모드 E2E (수동 실행): python tests/e2e_native.py
앱처럼 화면 파일을 '다른 출처'(http://localhost:포트)에서 열고 window.Capacitor 를 흉내 내서,
서버 주소 입력 → 연결 → 목록/완료/수정이 CORS 를 거쳐 되는지 headless Chromium 으로 확인한다."""
import functools, http.server, os, socket, sys, tempfile, threading, time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import uvicorn
from playwright.sync_api import sync_playwright
from client.api_client import Api
from server.api import create_app

OUT = Path(os.environ.get("SHOTS", tempfile.mkdtemp())); OUT.mkdir(parents=True, exist_ok=True)
def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p
API_PORT, APP_PORT, DEAD_PORT = free_port(), free_port(), free_port()

srv = uvicorn.Server(uvicorn.Config(create_app(str(Path(tempfile.mkdtemp()) / "n.db")), port=API_PORT, log_level="error"))
threading.Thread(target=srv.run, daemon=True).start()
api = Api(f"http://127.0.0.1:{API_PORT}")
for _ in range(50):
    try: api.health(); break
    except Exception: time.sleep(0.1)
now = datetime.now()
api.create({"title": "약 먹기", "kind": "daily", "reset_time": "04:00", "due_time": (now + timedelta(minutes=40)).strftime("%H:%M")})
api.create({"title": "세금 납부", "kind": "once", "due_at": (now + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:00")})

# 앱 안에 들어갈 화면 파일(= server/web)을 별도 출처로 서빙
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "server" / "web"))
handler.log_message = lambda *a, **k: None
class Q(http.server.ThreadingHTTPServer): pass
httpd = Q(("127.0.0.1", APP_PORT), type("H", (http.server.SimpleHTTPRequestHandler,), {
    "log_message": lambda *a, **k: None,
    "__init__": lambda self, *a, **k: http.server.SimpleHTTPRequestHandler.__init__(self, *a, directory=str(ROOT / "server" / "web"), **k)}))
threading.Thread(target=httpd.serve_forever, daemon=True).start()

fails = []
def check(c, m):
    print(("PASS " if c else "FAIL ") + m)
    if not c: fails.append(m)

URL = f"http://localhost:{APP_PORT}/index.html"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    ctx.add_init_script("window.Capacitor = { isNativePlatform: () => true, getPlatform: () => 'android' };")
    page = ctx.new_page()
    page.goto(URL)
    page.wait_for_selector("#setup:not([hidden])")
    check(True, "서버 주소가 없으면 주소 입력 화면이 먼저 뜸")
    check(page.is_hidden("#s-cancel"), "처음에는 취소 버튼 없음(주소 없이 못 넘어감)")
    check(page.is_visible("#gear"), "앱 모드에서는 ⚙ 설정 버튼 표시")
    page.screenshot(path=str(OUT / "n1_setup.png"))

    # 잘못된 주소(꺼진 포트)
    page.fill("#s-url", f"127.0.0.1:{DEAD_PORT}"); page.click("#s-ok")
    page.wait_for_selector("#s-force:not([hidden])", timeout=10000)
    check("연결하지 못했어요" in page.inner_text("#s-msg"), "연결 실패 안내 문구")
    check(page.evaluate("localStorage.getItem('server')") is None, "실패한 주소는 저장되지 않음")
    page.screenshot(path=str(OUT / "n2_fail.png"))

    # 올바른 주소(http:// 생략, 포트 포함)
    page.fill("#s-url", f"127.0.0.1:{API_PORT}"); page.click("#s-ok")
    page.wait_for_selector(".row", timeout=10000)
    check(page.is_hidden("#setup"), "연결 성공하면 입력 화면 닫힘")
    check(page.evaluate("localStorage.getItem('server')") == f"http://127.0.0.1:{API_PORT}", "정규화된 주소 저장 (http:// 자동 보정)")
    t = page.eval_on_selector_all(".row .title", "e=>e.map(x=>x.textContent)")
    check("약 먹기" in t and "세금 납부" in t, "다른 출처에서 서버 목록을 받아옴(CORS 통과)")
    check(page.is_visible("#conn.on"), "연결 표시 초록")
    page.screenshot(path=str(OUT / "n3_list.png"))

    # 쓰기 요청(POST/PATCH/DELETE)도 CORS 사전요청 통과
    page.locator(".row", has_text="약 먹기").locator(".chkbtn").click()
    time.sleep(1.2)
    check(any(x["title"] == "약 먹기" and x["status"] == "done" for x in api.list()["tasks"]), "완료 처리(POST)가 서버에 반영")
    page.fill("#quick-title", "앱에서 추가"); page.press("#quick-title", "Enter")
    page.wait_for_selector("text=앱에서 추가"); time.sleep(1.0)
    check(any(x["title"] == "앱에서 추가" for x in api.list()["tasks"]), "빠른 추가(POST JSON)가 서버에 반영")
    page.locator(".row", has_text="세금 납부").locator(".mid").click()
    page.wait_for_selector("#sheet:not([hidden])"); page.fill("#f-title", "세금 납부(수정)"); page.click("#sheet button.primary")
    time.sleep(1.2)
    check(any(x["title"] == "세금 납부(수정)" for x in api.list()["tasks"]), "수정(PATCH)이 서버에 반영")

    # 재시작해도 주소 유지
    page.reload(); page.wait_for_selector(".row", timeout=10000)
    check(page.is_hidden("#setup"), "다시 열어도 입력 화면 없이 바로 목록")

    # 설정에서 주소 변경 화면
    page.click("#gear"); page.wait_for_selector("#setup:not([hidden])")
    check(page.input_value("#s-url") == f"127.0.0.1:{API_PORT}", "설정을 열면 현재 주소가 채워져 있음")
    check(page.is_visible("#s-cancel"), "설정에서는 취소 가능")
    page.click("#s-cancel"); check(page.is_hidden("#setup"), "취소하면 닫힘")
    # 끝에 슬래시/http:// 붙인 입력도 허용
    page.click("#gear"); page.fill("#s-url", f"http://127.0.0.1:{API_PORT}/"); page.click("#s-ok")
    page.wait_for_selector("#setup", state="hidden", timeout=10000)
    check(page.evaluate("localStorage.getItem('server')") == f"http://127.0.0.1:{API_PORT}", "http:// 와 끝 슬래시가 있어도 같은 주소로 정리")

    # 서버 꺼짐 → 목록 유지 + 배너
    srv.should_exit = True; time.sleep(2.0)
    page.click("#refresh"); time.sleep(1.5)
    check(page.is_visible("#banner") and page.locator(".row").count() > 0, "서버가 꺼지면 배너 + 저장된 목록 유지")
    b.close()

httpd.shutdown()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL -> {fails}")
sys.exit(1 if fails else 0)
