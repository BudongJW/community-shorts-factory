# Community Shorts Factory

커뮤니티 트렌딩 토픽을 자동 수집하여 YouTube Shorts를 생성하는 파이프라인.
초기 자본 $0으로 운영 가능. GitHub Actions로 매일 자동 생성/업로드.

## 영상 모드

### 1. chat 모드 (메신저 채팅 썰)
커뮤니티 글을 카카오톡 스타일 대화 영상으로 변환한다.
말풍선 순차 등장 + 타이핑 인디케이터 + 스크롤 애니메이션.

```
디시 HIT 갤러리 수집 -> LLM 채팅 대본 생성 -> Pillow 채팅 UI 렌더링 -> MP4 합성 -> YouTube 업로드
```

### 2. narration 모드 (나레이션 + 배경 영상)
트렌딩 토픽을 TTS 나레이션 + 배경 영상으로 합성한다.

```
디시 HIT 갤러리 수집 -> LLM 대본 생성 -> Edge TTS 음성 -> Pexels 배경 영상 -> FFmpeg 합성 -> YouTube 업로드
```

## 프로젝트 구조

```
src/
  collector/
    dcinside.py          # 디시인사이드 HIT 갤러리 스크래핑 (dc-api, 비동기)
    filter.py            # LLM 기반 바이럴 가능성 필터링 (70점+ 선별)
    history.py           # 토픽 중복 방지 (최근 200개 추적, 60% 키워드 겹침 차단)
  script_gen/
    generator.py         # narration 모드 대본 생성 (Groq/Claude)
    chat_generator.py    # chat 모드 대본 생성 (메신저 대화 형식)
  tts/
    edge_tts_engine.py   # Edge TTS 음성 + SRT 자막 동시 생성 (무료, 무제한)
  video/
    pexels.py            # Pexels 무료 스톡 영상 다운로드 (API 키 없으면 플레이스홀더)
  editor/
    composer.py          # narration 모드: 배경 영상 + 음성 + 자막 + BGM 합성
    chat_renderer.py     # chat 모드: Pillow 기반 메신저 UI 프레임 렌더링
    chat_composer.py     # chat 모드: 프레임 시퀀스 -> MP4 변환
  uploader/
    youtube.py           # YouTube Data API v3 업로드 (OAuth2, 환경변수/파일 토큰)
  orchestrator/
    main.py              # CLI 진입점 + 파이프라인 오케스트레이션
    scheduler.py         # 로컬 cron 스케줄러 (n시간 간격 반복)
config/
  settings.py            # 경로, 해상도(1080x1920), FPS(30), API 키 로딩
samples/
  chat_sample.json       # 채팅 대본 샘플 (연봉 협상 레전드)
scripts/
  setup_youtube_token.py # YouTube OAuth 토큰 최초 발급 헬퍼
.github/workflows/
  daily-shorts.yml       # 매일 09:00 KST 자동 생성 + 업로드
```

## 로컬 환경 설정 (새 머신에서 시작할 때)

### 1단계: 클론 및 의존성 설치

```bash
git clone https://github.com/BudongJW/community-shorts-factory.git
cd community-shorts-factory
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

pip install -r requirements.txt
```

### 2단계: 환경변수 설정

```bash
cp .env.example .env
```

`.env` 파일 편집:

```env
# [필수] LLM 대본 생성 - Groq 무료 (https://console.groq.com)
GROQ_API_KEY=gsk_실제키

# [chat 모드에서는 불필요] 배경 영상 소스
PEXELS_API_KEY=실제키

# [선택] Claude 사용 시
ANTHROPIC_API_KEY=sk-ant-실제키
```

### 3단계: 테스트 실행

```bash
# chat 모드 - JSON 직접 지정 (API 키 불필요, 완전 무료)
PYTHONIOENCODING=utf-8 python -m src.orchestrator.main --mode chat --json samples/chat_sample.json --skip-upload

# chat 모드 - 트렌딩 자동 수집 + LLM 대본 (GROQ_API_KEY 필요)
PYTHONIOENCODING=utf-8 python -m src.orchestrator.main --mode chat --skip-upload

# narration 모드
PYTHONIOENCODING=utf-8 python -m src.orchestrator.main --skip-upload

# dry-run (수집 + 대본까지만, 영상 생성 안 함)
PYTHONIOENCODING=utf-8 python -m src.orchestrator.main --mode chat --dry-run
```

> Windows 한글 깨짐 방지: `PYTHONIOENCODING=utf-8` 필수

### 4단계: YouTube 업로드 설정 (선택)

```bash
# 1) Google Cloud Console에서 OAuth 2.0 Client (Desktop) 생성
#    https://console.cloud.google.com/apis/credentials
#    - YouTube Data API v3 활성화 필수
#    - OAuth 동의 화면 설정 필요 (테스트 사용자에 본인 Gmail 추가)

# 2) 다운로드한 JSON을 config/에 저장
mv ~/Downloads/client_secret_*.json config/client_secret.json

# 3) 토큰 발급 (브라우저에서 Google 로그인)
python scripts/setup_youtube_token.py

# 4) 업로드 테스트
PYTHONIOENCODING=utf-8 python -m src.orchestrator.main --mode chat --json samples/chat_sample.json
```

## GitHub Actions 자동화 설정

매일 09:00 KST에 자동으로 쇼츠를 생성하여 YouTube에 업로드한다.

### 필요한 GitHub Secrets

레포 Settings > Secrets and variables > Actions 에서 등록:

| Secret 이름 | 값 | 용도 |
|---|---|---|
| `GROQ_API_KEY` | Groq API 키 | LLM 대본 생성 |
| `YOUTUBE_TOKEN_JSON` | `setup_youtube_token.py` 출력값 (JSON 전체) | YouTube 업로드 |

### 워크플로우 수동 실행

Actions 탭 > "Daily Community Shorts" > "Run workflow" 버튼

### 토큰 만료 시

YouTube OAuth 토큰은 refresh_token이 포함되어 자동 갱신되지만,
만료된 경우 로컬에서 다시 발급 후 `YOUTUBE_TOKEN_JSON` 시크릿 업데이트:

```bash
python scripts/setup_youtube_token.py
# 출력된 JSON을 GitHub Secrets에 다시 등록
```

## CLI 전체 옵션

```
python -m src.orchestrator.main [OPTIONS]

옵션:
  --mode {narration,chat}  영상 모드 (기본: narration)
  --json PATH              chat 모드에서 JSON 대본 직접 지정 (수집/LLM 건너뜀)
  --batch N                N개 영상 배치 생성 (기본: 1)
  --provider {groq,claude} LLM 프로바이더 (기본: groq)
  --posts N                수집할 게시글 수 (기본: 10)
  --skip-upload            YouTube 업로드 건너뜀
  --dry-run                수집 + 대본까지만 (영상 생성 안 함)
```

## 채팅 대본 JSON 형식

`samples/chat_sample.json` 참고:

```json
{
  "category": "커뮤니티 썰",
  "title": "제목 (15자 이내)",
  "subtitle": "출처",
  "participants": ["참가자1", "참가자2"],
  "messages": [
    {"sender": "참가자1", "text": "메시지", "side": "left"},
    {"sender": "참가자2", "text": "답변", "side": "right"}
  ],
  "result_text": "결과 한 줄 (하단 표시)",
  "tags": ["태그1", "태그2"]
}
```

- `side`: `"left"` = 왼쪽 말풍선 (질문/이야기), `"right"` = 오른쪽 말풍선 (답변/반응)
- `result_text`: 영상 마지막에 하단에 노란색으로 표시되는 결과/반전
- `messages`: 8~15개 권장, 각 메시지 40자 이내

## 비용

| 구성 요소 | 서비스 | 비용 |
|---|---|---|
| LLM 대본 | Groq (llama-3.3-70b) | 무료 |
| TTS 음성 | Edge TTS | 무료, 무제한 |
| 채팅 UI | Pillow (로컬 렌더링) | 무료 |
| 배경 영상 | Pexels API | 무료 |
| 영상 합성 | FFmpeg (imageio_ffmpeg) | 무료 |
| YouTube | Data API v3 | 무료 (일 6회 쿼터) |
| CI/CD | GitHub Actions | 무료 (월 2000분) |

## 기술 스택

- Python 3.12+
- FFmpeg (imageio_ffmpeg 번들, 시스템 설치 불필요)
- Pillow (채팅 UI 렌더링)
- Edge TTS (한국어 음성 합성)
- dc-api (디시인사이드 비동기 스크래핑)
- Groq / Anthropic (LLM 대본 생성)
- Google API (YouTube 업로드)

## 한글 폰트

- Windows: 맑은 고딕 (malgun.ttf) 자동 감지
- Linux/CI: NanumGothic (fonts-nanum 패키지) 자동 감지
- GitHub Actions에서는 워크플로우가 `fonts-nanum` 자동 설치
