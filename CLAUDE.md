# AI Shorts Pipeline - Claude Code 작업 가이드

## 프로젝트 개요
커뮤니티(디시인사이드) 트렌딩 토픽을 자동 수집하여 YouTube Shorts를 생성하는 end-to-end 파이프라인.
초기 자본 $0으로 운영 가능하도록 설계됨.

## 파이프라인 흐름

### narration 모드 (기존)
```
디시 HIT 갤러리 수집 (dc-api)
-> LLM 대본 생성 (Groq 무료 / Claude)
-> Edge TTS 음성+자막 (무료, 무제한)
-> Pexels 배경 영상 (무료 API)
-> FFmpeg 합성 (imageio_ffmpeg 번들)
-> YouTube 업로드 (API v3)
```

### chat 모드 (채팅 썰 쇼츠)
```
디시 HIT 갤러리 수집 (dc-api)
-> LLM 채팅 대본 생성 (Groq 무료 / Claude) -- 또는 JSON 직접 지정
-> Pillow 채팅 UI 프레임 렌더링 (말풍선, 타이핑 인디케이터, 스크롤)
-> FFmpeg 프레임 -> MP4 합성 (+ 선택적 BGM)
-> YouTube 업로드 (API v3)
```

## 현재 상태 (2026-04-16 기준)
- **e2e 테스트 통과**: 두 모드 모두 `--skip-upload`로 동작 확인됨
- **chat 모드**: Pillow 기반 메신저 스타일 채팅 UI 렌더링 (API 비용 $0)
- **GitHub Actions**: 매일 09:00 KST 자동 생성 워크플로우 (`.github/workflows/daily-shorts.yml`)
- **YouTube 업로드**: OAuth 토큰 환경변수 지원 (`YOUTUBE_TOKEN_JSON`), CI 호환
- **FFmpeg**: 시스템 설치 불필요 -- `imageio_ffmpeg` 번들 바이너리 사용
- **Edge TTS 7.x**: `SentenceBoundary` 이벤트 + `get_srt()` 사용 (구버전 API와 다름)
- **Pexels**: API 키 없으면 자동으로 단색 플레이스홀더 영상 생성
- **폰트**: Windows(맑은고딕) / Linux(NanumGothic) 자동 감지

## GitHub 레포
- **레포명**: `BudongJW/community-shorts-factory` (private)
- **원래 로컬 폴더명**: `ai-shorts-pipeline`
- remote origin: `https://github.com/BudongJW/community-shorts-factory.git`

## 미완료 작업 (TODO)
- YouTube OAuth 설정 미완료 (client_secret.json, youtube_token.json 모두 없음)
- GitHub Secrets 미등록 (GROQ_API_KEY, YOUTUBE_TOKEN_JSON)
- 채팅 UI 개선 여지: 카카오톡 UI 더 정교하게, 커뮤니티 게시판 스타일 템플릿 추가
- narration 모드: Pexels 실제 테스트, 썸네일 자동 생성, ASS 자막 전환
- 배경음악(BGM) 자동 첨부 미구현

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
# ── narration 모드 (기존) ──
PYTHONIOENCODING=utf-8 python -m src.orchestrator.main --dry-run
PYTHONIOENCODING=utf-8 python -m src.orchestrator.main --skip-upload
PYTHONIOENCODING=utf-8 python -m src.orchestrator.main

# ── chat 모드 (채팅 썰) ──
# JSON 대본 직접 지정 (API 불필요)
PYTHONIOENCODING=utf-8 python -m src.orchestrator.main --mode chat --json samples/chat_sample.json --skip-upload

# 트렌딩 토픽에서 자동 채팅 대본 생성
PYTHONIOENCODING=utf-8 python -m src.orchestrator.main --mode chat --skip-upload

# 배치 생성
PYTHONIOENCODING=utf-8 python -m src.orchestrator.main --mode chat --batch 5 --skip-upload
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
