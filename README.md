# AI Shorts Pipeline

커뮤니티 트렌딩 토픽 기반 YouTube Shorts 자동 생성 파이프라인.

## Pipeline

```
디시인사이드 HIT 갤러리 → 트렌딩 키워드 추출 → LLM 대본 생성 → Edge TTS 음성
→ Pexels 영상 소스 → FFmpeg 합성 → YouTube 자동 업로드 → 제휴링크 수익화
```

## Architecture

```
src/
├── collector/      # 커뮤니티 데이터 수집 (dc-api)
├── script_gen/     # LLM 대본 생성 (Claude/Groq)
├── tts/            # 음성 합성 (Edge TTS)
├── video/          # 영상 소스 수집 (Pexels API)
├── editor/         # 자동 편집 (FFmpeg + MoviePy)
├── uploader/       # YouTube 업로드
└── orchestrator/   # 전체 파이프라인 오케스트레이션
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # API 키 설정
```

## Usage

```bash
python -m src.orchestrator.main
```

## Cost

모든 핵심 도구가 무료 티어로 운영 가능:
- **LLM**: Groq 무료 티어 / Anthropic API
- **TTS**: Edge TTS (무료, 무제한)
- **영상**: Pexels API (무료, 상업적 사용 가능)
- **편집**: FFmpeg (오픈소스)
- **업로드**: YouTube Data API v3 (일 6회 무료 쿼터)
