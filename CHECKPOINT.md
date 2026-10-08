
## [업데이트] 2~3단계 완료
- [x] 2단계 FastAPI: server/api.py, run_server.py, 서버_실행.bat (tests 포함, gzip 압축)
- [x] 3단계 클라이언트: client/{settings,api_client,style,util,task_view,dialogs,main_window,app}.py + todo_client.py
  - 오프스크린 통합 점검 통과(추가/완료/탭/마감초과 차단/오프라인 배너+캐시 목록 유지)
  - 성능(5000건): HTTP 목록 ~250ms, 화면 반영 ~40ms, 재그리기 ~1ms
- UI 스타일은 client/style.py 한 곳에서 수정(사용 후 개선 예정)
## 다음에 할 것
- 4~5단계: 빌드_클라이언트.bat(PyInstaller), GitHub Actions(윈도우 exe 자동 빌드), .gitignore
- 6단계: README, 최종 점검, 파일을 사용자 PC 폴더로 복사

---
## 모바일(안드로이드) 확장 진행 상황 (2026-10-08)

### 지금까지 완료
- 1단계: 서버가 `/` 에서 모바일 웹 UI 제공 (server/web/: index.html, style.css, app.js, manifest, 아이콘)
  - 기본값 "진행 중만" 체크, 낙관적 UI, 오프라인 배너, 하단 시트 폼, 두 번 탭 삭제
- 2단계: 폰 크기(390x844) E2E 테스트 통과 (`SHOTS=/tmp/shots python3 tests/e2e_mobile.py`, Playwright 필요)
- 데스크톱: 알림 3일 전 / 24시간 전만, 매일 할일 제외, 기본 "진행 중만" (v1.0.3 태그는 사용자가 push 후 진행)

### 다음에 이어서 할 것
- 사용자가 폰 브라우저로 `http://<서버 Tailscale IP>:8765` 접속해 써보고 피드백
- 3단계: Capacitor APK 껍데기 + GitHub Actions 빌드/Releases 첨부
  - 서명 키(.jks)와 비밀번호는 사용자가 직접 만들어 GitHub Secrets에 등록 (Claude는 방법만 안내)
  - workflow 파일은 `.github` 보호 경로라서 다른 이름으로 전달 → 사용자가 이동
- 4단계: 폰 알림 (3일 전 1회 / 24시간 전 완료될 때까지 유지 + 약 3시간마다 재알림, 매일 할일 제외)

---
## 3단계: 안드로이드 APK 껍데기 (2026-10-08)

### 지금까지 완료
- 설계 변경(이유: 폰 알림 기능은 앱 안의 화면에서만 호출 가능): 화면(server/web)을 APK 안에 복사해 넣고, 데이터는 사용자가 입력한 서버 주소로 받음
  - 화면을 고치면 APK도 새로 빌드해야 반영됨 (서버 PC 브라우저 접속 화면은 서버만 갱신하면 됨)
- server/web: 앱 모드(window.Capacitor)에서 서버 주소 입력/변경(⚙) 화면, 주소 정규화(http:// 와 :8765 자동 보정), 연결 테스트
- server/api.py: CORS (http(s)://localhost 출처만 허용), tests/test_api.py 에 테스트 추가
- android_app/: package.json(+lock), capacitor.config.json(androidScheme=http), scripts/prepare_android.py(화면 복사·매니페스트 패치·버전·아이콘)
- android_build_workflow.yml → 사용자가 .github/workflows/android.yml 로 이동. 태그 app-v* 로 빌드·서명·Releases 첨부
- 안드로이드_앱_안내.md: 서명 키 생성(keytool) · Secrets 4종 등록 · 릴리즈 · 설치 방법
- 테스트: pytest 35 통과, tests/e2e_mobile.py, tests/e2e_native.py 전부 통과
- 클라우드에서는 Android SDK/Gradle 저장소 접근이 막혀 실제 APK 컴파일은 못 해봄 (프로젝트 생성·패치·동기화까지만 검증)

### 다음에 이어서 할 것
- 사용자: workflow 파일 이동 → 서명 키 생성 → Secrets 등록 → `git tag app-v1.0.0` push → Actions 결과 확인 (실패하면 로그를 보고 수정)
- 폰에 APK 설치 후 서버 주소 입력 테스트
- 4단계: 폰 알림 (3일 전 1회 / 24시간 전 완료될 때까지 유지 + 약 3시간마다 재알림, 매일 할일 제외, 동기화 시 완료분 취소)
