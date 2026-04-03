"""니치 필터링: 트렌딩 토픽 중 쇼츠 바이럴 가능성이 높은 것만 선별한다."""

import json
import os

from dotenv import load_dotenv

load_dotenv()

FILTER_PROMPT = """당신은 YouTube Shorts 전략 분석가입니다.
아래 커뮤니티 트렌딩 게시글 목록을 보고, 쇼츠 영상으로 만들었을 때 바이럴 가능성이 높은 토픽을 선별하세요.

## 선별 기준 (모두 충족해야 함)

### 포함 기준
- 대중적 관심사 (음식, 일상, 노스탤지어, 신기한 사실, 반전 스토리)
- 60초 안에 전달 가능한 스토리 (너무 복잡하지 않은 것)
- 감정적 반응을 유발 (놀라움, 공감, 웃음, 감동)
- 시각적으로 표현 가능 (배경 영상을 붙일 수 있는 주제)

### 제외 기준
- 정치/종교/젠더 논쟁 (리스크 높음)
- 특정 커뮤니티 내부 밈/은어 (대중성 부족)
- 단순 이미지 감상 (메피스토펠레스 완성 등 — 영상화 어려움)
- 선정적/자극적 낚시성 (채널 성장에 해로움)
- 저작권 이슈 가능성 (특정 작품/브랜드 중심)

## 트렌딩 게시글 목록
{posts}

## 출력 형식 (JSON)
{{
  "selected": [
    {{
      "title": "원본 게시글 제목",
      "score": 85,
      "reason": "선택 이유 (한 줄)",
      "angle": "쇼츠로 만들 때의 각도/컨셉 제안"
    }}
  ],
  "rejected": [
    {{
      "title": "원본 게시글 제목",
      "reason": "제외 이유 (한 줄)"
    }}
  ]
}}

score는 0~100 (바이럴 가능성). 70점 이상만 selected에 포함.
JSON만 출력하세요."""


def filter_with_groq(posts_text: str) -> dict:
    """Groq으로 토픽을 필터링한다."""
    from groq import Groq

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": FILTER_PROMPT.format(posts=posts_text)}],
        temperature=0.3,
        max_tokens=2048,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def filter_with_claude(posts_text: str) -> dict:
    """Claude로 토픽을 필터링한다."""
    import anthropic

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{"role": "user", "content": FILTER_PROMPT.format(posts=posts_text)}],
    )
    text = response.content[0].text
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    return json.loads(text.strip())


def filter_topics(posts_text: str, provider: str = "groq") -> dict:
    """토픽 필터링 통합 진입점.

    Returns:
        {"selected": [...], "rejected": [...]}
    """
    if provider == "claude":
        return filter_with_claude(posts_text)
    return filter_with_groq(posts_text)
