# TODO - AI Shorts Pipeline

## 사용자 직접 수행 (API 키/계정 설정)

- [ ] **Pexels API 키 발급**: https://www.pexels.com/api/ 가입 → `.env`에 `PEXELS_API_KEY` 입력
- [ ] **YouTube OAuth 설정**: Google Cloud Console에서 OAuth 2.0 클라이언트 생성 → `config/client_secret.json` 배치 → `youtube.upload` 스코프 활성화
- [ ] **쿠팡 파트너스 가입** (선택): 제휴링크 수익화용

## Claude Code 구현 작업

### 우선순위 1: 핵심 기능 완성
- [ ] YouTube 업로드 모듈 실제 테스트 (OAuth 인증 플로우 → 테스트 업로드)
- [ ] Pexels API 연동 실제 테스트 (키 설정 후 영상 다운로드 검증)
- [ ] 제휴링크 자동 삽입 모듈 구현 (`src/uploader/` 내 description에 쿠팡 링크 삽입)

### 우선순위 2: 영상 퀄리티 개선
- [x] ~~프롬프트 고도화~~ → 훅/전개/마무리 구조 강제, 200~300자, MZ세대 말투
- [x] ~~자막 스타일 개선~~ → 큰 폰트+반투명 배경 박스+하단 여백 (SRT force_style)
- [x] ~~TTS 음성 다양화~~ → 한국어 남/여 3종 랜덤 + 속도 변화
- [x] ~~BGM 믹싱 지원~~ → compose()에 bgm_path 옵션 (나레이션 100% + BGM 20%)
- [ ] **배경 영상 매칭 품질**: 대본 문맥별 시퀀스 매칭 — search_keywords를 5개로 확장하여 장면별 클립 대응
- [ ] **영상 전환 효과**: 클립 간 페이드/디졸브 트랜지션 (xfade FFmpeg 필터)
- [ ] **썸네일 자동 생성**: 핵심 프레임 추출 + 텍스트 오버레이 (Pillow)
- [ ] **세로 영상 최적화**: Pexels portrait 검색 우선 + 스마트 크롭 로직
- [ ] **ASS 자막 전환**: 단어 단위 하이라이트 애니메이션 (현재 SRT 문장 단위)

### 우선순위 3: 자동화 및 스케일링
- [x] ~~중복 토픽 방지~~ → topic_history.json 기반 키워드 겹침 비교
- [x] ~~배치 생성 모드~~ → `--batch N` 옵션
- [ ] n8n 워크플로우 설계 또는 cron 기반 스케줄러 (하루 N편 자동 생산)
- [ ] 수집 소스 다양화: 에펨코리아, 네이트판 등 추가 커뮤니티 크롤러
- [ ] 멀티채널 전략: 카테고리별 다른 채널에 업로드하는 구조
- [ ] 성과 트래킹: 업로드된 영상의 조회수/구독자 변화 모니터링

### 우선순위 4: 코드 품질
- [x] ~~로깅 시스템~~ → 콘솔 + 파일(output/logs/) 이중 로깅
- [ ] 에러 핸들링 강화 (네트워크 실패, API 쿼터 초과, 재시도 로직)
- [ ] 단위 테스트 작성 (`tests/` 디렉토리)

### 벤치마킹 참고 프로젝트
- [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) (54.9k★) — 웹 UI, 배치 생성
- [ShortGPT](https://github.com/RayVentura/ShortGPT) (7.2k★) — Editing Markup Language, 다국어 더빙
- [short-video-maker](https://github.com/gyoridavid/short-video-maker) (1.1k★) — MCP 서버 통합
- [MoneyPrinterV2](https://github.com/FujiwaraChoki/MoneyPrinterV2) (28.1k★) — YouTube 자동 업로드+CRON
