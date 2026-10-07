
## [업데이트] 2~3단계 완료
- [x] 2단계 FastAPI: server/api.py, run_server.py, 서버_실행.bat (tests 포함, gzip 압축)
- [x] 3단계 클라이언트: client/{settings,api_client,style,util,task_view,dialogs,main_window,app}.py + todo_client.py
  - 오프스크린 통합 점검 통과(추가/완료/탭/마감초과 차단/오프라인 배너+캐시 목록 유지)
  - 성능(5000건): HTTP 목록 ~250ms, 화면 반영 ~40ms, 재그리기 ~1ms
- UI 스타일은 client/style.py 한 곳에서 수정(사용 후 개선 예정)
## 다음에 할 것
- 4~5단계: 빌드_클라이언트.bat(PyInstaller), GitHub Actions(윈도우 exe 자동 빌드), .gitignore
- 6단계: README, 최종 점검, 파일을 사용자 PC 폴더로 복사

## [최종 업데이트] 4~6단계 완료 (v1 완성)
- [x] 빌드_클라이언트.bat (PyInstaller onedir), github_build_workflow.yml(→ .github/workflows/build.yml 로 옮겨 사용), README.md
- [x] 전체 테스트 28 passed (서버/API/유틸/UI 통합). PC 폴더에서는 UI 제외 27 passed
- [x] 성능(5000건): HTTP ~250ms(gzip 적용), 화면 반영 ~40ms
- 아직 실제 윈도우에서 해보지 않은 것: exe 빌드, Tailscale 경유 접속, 윈도우 토스트 알림 -> 사용 후 피드백으로 UI/동작 수정
## 다음에 할 것 (사용 후)
- 사용감 기반 UI 수정(client/style.py, task_view.py 위주)
- 필요 시: 폰용 웹 화면, 완료 이력/통계 화면
