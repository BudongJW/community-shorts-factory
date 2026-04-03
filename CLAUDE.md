# AI Shorts Pipeline - Claude Code 작업 가이드

## 프로젝트 개요
커뮤니티(디시인사이드) 트렌딩 토픽을 자동 수집하여 YouTube Shorts를 생성하는 end-to-end 파이프라인.
초기 자본 $0으로 운영 가능하도록 설계됨.

## 파이프라인 흐름
```
디시 HIT 갤러리 수집 (dc-api)
→ LLM 대본 생성 (Groq 무료 / Claude)
→ Edge TTS 음성+자막 (무료, 무제한)
→ Pexels 배경 영상 (무료 API)
→ FFmpeg 합성 (imageio_ffmpeg 번들)
→ YouTube 업로드 (API v3)
```

## 현재 상태 (2026-04-03 기준)
- **e2e 테스트 통과**: `--skip-upload` 모드로 전체 파이프라인 동작 확인됨
- **FFmpeg**: 시스템 설치 불필요 — `imageio_ffmpeg` 번들 바이너리 사용
- **Edge TTS 7.x**: `SentenceBoundary` 이벤트 + `get_srt()` 사용 (구버전 API와 다름)
- **Pexels**: API 키 없으면 자동으로 단색 플레이스홀더 영상 생성

## 환경 설정
```bash
# venv은 이미 .venv/ 에 생성되어 있음
.venv\Scripts\activate     # Windows
pip install -r requirements.txt
cp .env.example .env       # API 키 설정
```

### .env 필수 키
- `GROQ_API_KEY`: Groq 무료 티어 (대본 생성)
- `PEXELS_API_KEY`: Pexels 무료 API (영상 소스)

### .env 선택 키
- `ANTHROPIC_API_KEY`: Claude 사용 시
- `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET`: 업로드 자동화 시

## 실행 명령
```bash
# dry-run (수집 + 대본만)
PYTHONIOENCODING=utf-8 python -m src.orchestrator.main --dry-run

# 업로드 제외 전체
PYTHONIOENCODING=utf-8 python -m src.orchestrator.main --skip-upload

# 풀 파이프라인
PYTHONIOENCODING=utf-8 python -m src.orchestrator.main
```
> Windows 터미널 한글 깨짐 방지: `PYTHONIOENCODING=utf-8` 필수

## 코드 컨벤션
- Python 3.12+, 타입 힌트 사용
- 각 모듈은 독립 실행 가능한 구조 (동기 진입점 `run()` 또는 직접 함수 호출)
- 비동기 함수는 내부에서만 사용, 외부 인터페이스는 `asyncio.run()` 래핑
- 민감정보(API 키, 토큰)는 절대 코드에 하드코딩 금지 — .env + dotenv 사용

## 보안 주의사항
- 이 레포는 **private** 이지만 민감정보를 코드에 포함하지 말 것
- `.env`, `config/client_secret.json`, `*token*.json`은 .gitignore에 포함됨
- 커밋 전 `git diff --cached`로 민감정보 누출 확인 필수
