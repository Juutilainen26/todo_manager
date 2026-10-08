"""모바일 웹 화면 E2E (수동 실행): python tests/e2e_mobile.py
headless Chromium 으로 폰 크기(390x844)에서 실제로 조작한다. pytest 자동 수집 대상 아님."""
import os, socket, sys, tempfile, threading, time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from playwright.sync_api import sync_playwright
from client.api_client import Api
from server.api import create_app

OUT = Path(os.environ.get("SHOTS", tempfile.mkdtemp()))
OUT.mkdir(parents=True, exist_ok=True)
s = socket.socket(); s.bind(("127.0.0.1", 0)); PORT = s.getsockname()[1]; s.close()
db = str(Path(tempfile.mkdtemp()) / "e2e.db")
srv = uvicorn.Server(uvicorn.Config(create_app(db), port=PORT, log_level="error"))
threading.Thread(target=srv.run, daemon=True).start()
api = Api(f"http://127.0.0.1:{PORT}")
for _ in range(50):
    try: api.health(); break
    except Exception: time.sleep(0.1)

now = datetime.now()
ds = lambda **kw: (now + timedelta(**kw)).strftime("%Y-%m-%dT%H:%M:00")
api.create({"title": "약 먹기", "kind": "daily", "reset_time": "04:00", "due_time": (now + timedelta(minutes=40)).strftime("%H:%M")})
api.create({"title": "운동하기", "kind": "daily", "reset_time": "05:00"})
api.create({"title": "주간 리포트 제출", "note": "팀 폴더에 업로드", "kind": "weekly", "reset_weekday": 1, "reset_time": "00:00", "due_weekday": 4, "due_time": "18:00"})
api.create({"title": "방 청소", "kind": "weekly", "reset_weekday": 3, "reset_time": "00:00"})
api.create({"title": "병원 예약 전화", "kind": "once", "due_at": ds(hours=3)})
api.create({"title": "세금 납부", "kind": "once", "due_at": ds(days=5)})
api.create({"title": "언젠가 책 정리", "kind": "once"})
api.create({"title": "이미 지난 일", "kind": "once", "due_at": ds(seconds=2)})
done = api.create({"title": "아침 스트레칭", "kind": "daily", "reset_time": "00:00"}); api.complete(done["id"])
time.sleep(2.5)

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(f"http://127.0.0.1:{PORT}/")
    page.wait_for_selector(".row")
    titles = lambda: page.eval_on_selector_all(".row .title", "els=>els.map(e=>e.textContent)")

    check(page.is_checked("#only-pending"), "기본값: '진행 중만' 체크됨")
    t = titles()
    check("이미 지난 일" not in t and "아침 스트레칭" not in t, f"기본 목록에 마감초과/완료 숨김 ({len(t)}건)")
    check("약 먹기" in t and "병원 예약 전화" in t, "진행 중 일정 표시")
    page.screenshot(path=str(OUT / "m1_default.png"))

    page.uncheck("#only-pending")
    t = titles()
    check("이미 지난 일" in t and "아침 스트레칭" in t, "체크 해제하면 전체 표시")
    check(page.locator(".row.missed .chkbtn").first.inner_text() == "✕", "마감 초과는 ✕ 표시")
    page.locator(".row.missed .chkbtn").first.click()
    check("완료 처리할 수 없어요" in page.inner_text("#toast"), "마감 초과 완료 시도 → 안내")
    page.screenshot(path=str(OUT / "m2_all.png"))
    page.check("#only-pending")

    # 빠른 추가
    page.fill("#quick-title", "빠른 추가 테스트"); page.select_option("#quick-kind", "today"); page.press("#quick-title", "Enter")
    page.wait_for_selector("text=빠른 추가 테스트")
    check("빠른 추가 테스트" in titles(), "빠른 추가 → 즉시 표시")

    # 완료 체크 (진행 중만 켜진 상태 → 사라짐)
    row = page.locator(".row", has_text="운동하기")
    row.locator(".chkbtn").click()
    page.wait_for_function("()=>![...document.querySelectorAll('.row .title')].some(e=>e.textContent==='운동하기')")
    check("운동하기" not in titles(), "완료 체크 → 진행 중 목록에서 사라짐")
    time.sleep(0.8)
    check(api.list()["tasks"] and any(x["title"] == "운동하기" and x["status"] == "done" for x in api.list()["tasks"]), "서버에도 완료로 저장됨")
    page.uncheck("#only-pending")
    page.locator(".row", has_text="운동하기").locator(".chkbtn").click()   # 되돌리기
    time.sleep(0.8)
    check(any(x["title"] == "운동하기" and x["status"] == "pending" for x in api.list()["tasks"]), "완료 → 미완료 되돌리기")
    page.check("#only-pending")

    # 수정 시트
    page.locator(".row", has_text="방 청소").locator(".mid").click()
    page.wait_for_selector("#sheet:not([hidden])")
    check(page.input_value("#f-title") == "방 청소" and page.input_value("#f-kind") == "weekly", "수정 시트에 기존 값 채워짐")
    check(not page.is_visible("#f-dt") and not page.is_visible("#f-dwd"), "마감 지정 해제 상태에서는 마감 요일/시각 칸 숨김")
    check(page.is_visible("#f-rwd") and page.is_visible("#f-rt"), "주간: 초기화 요일/시각 칸 표시")
    page.check("#f-usedue")
    check(page.is_visible("#f-dt") and page.is_visible("#f-dwd"), "마감 지정 체크하면 마감 요일/시각 칸 표시")
    page.uncheck("#f-usedue")
    page.screenshot(path=str(OUT / "m3_edit_weekly.png"))
    page.fill("#f-title", "방 청소(수정)"); page.select_option("#f-rwd", "1")
    page.click("#sheet button[type=submit]")
    page.wait_for_selector("text=방 청소(수정)")
    time.sleep(0.8)
    got = [x for x in api.list()["tasks"] if x["title"] == "방 청소(수정)"]
    check(bool(got) and got[0]["reset_weekday"] == 1, "수정 저장(요일 변경) 서버 반영")

    # + 자세히 : 마감일 있는 일회성
    page.click("#fab"); page.wait_for_selector("#sheet:not([hidden])")
    page.fill("#f-title", "자세히 추가"); page.select_option("#f-kind", "once"); page.check("#f-useonce")
    check(page.is_visible("#f-due"), "한 번만 선택 시 마감 입력칸 표시")
    check(not page.is_visible("#f-rt") and not page.is_visible("#f-rwd"), "한 번만: 초기화 칸 숨김")
    page.screenshot(path=str(OUT / "m4_add_once.png"))
    page.fill("#f-due", ds(days=2)[:16]); page.click("#sheet button[type=submit]")
    page.wait_for_selector("text=자세히 추가")
    time.sleep(0.8)
    got = [x for x in api.list()["tasks"] if x["title"] == "자세히 추가"]
    check(bool(got) and got[0]["kind"] == "once" and got[0]["due_at"], "자세히 추가 저장")

    # 탭
    page.click("#tabs button[data-tab=upcoming]"); t = titles()
    check("세금 납부" in t and "약 먹기" not in t, "앞으로 탭 필터")
    page.click("#tabs button[data-tab=weekly]"); t = titles()
    check(all("주간" in x or "방 청소" in x for x in t) and len(t) == 2, f"주간 탭 필터 {t}")
    page.click("#tabs button[data-tab=all]")

    # 검색
    page.fill("#search", "세금"); check(titles() == ["세금 납부"], "검색")
    page.fill("#search", "")

    # 삭제 (두 번 눌러야)
    page.locator(".row", has_text="세금 납부").locator(".mid").click()
    page.click("#f-del"); check(page.inner_text("#f-del") == "정말 삭제", "삭제 1회 누르면 확인 문구")
    page.click("#f-del"); time.sleep(0.8)
    check(not any(x["title"] == "세금 납부" for x in api.list()["tasks"]), "삭제 2회 → 서버에서 삭제")

    # 남은 시간 텍스트
    rt = page.locator(".row", has_text="병원 예약 전화").locator("[data-rt]").inner_text()
    check("남음" in rt, f"남은 시간 표시: {rt}")
    page.screenshot(path=str(OUT / "m5_final.png"))

    check(not errors, f"브라우저 콘솔 에러 없음(서버 정상 구간) {errors[:3]}")

    # 오프라인
    srv.should_exit = True; time.sleep(1.5)
    page.click("#refresh")
    page.wait_for_selector("#banner:not([hidden])", timeout=15000)
    check(len(titles()) > 0, "서버 꺼짐 → 배너 표시 + 마지막 목록 유지")
    page.screenshot(path=str(OUT / "m6_offline.png"))
    b.close()

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
print("shots:", OUT)
sys.exit(1 if fails else 0)
