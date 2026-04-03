"""트렌딩 토픽 기반 YouTube Shorts 대본 생성기."""

import json
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

SCRIPT_PROMPT = """당신은 조회수 100만 이상을 달성하는 한국어 YouTube Shorts 전문 대본 작가입니다.
아래 커뮤니티 트렌딩 토픽 중 가장 바이럴 가능성이 높은 하나를 골라 60초 쇼츠 대본을 작성하세요.

## 대본 구조 (반드시 지킬 것)

### 1. 훅 (첫 3초, 1~2문장)
- 질문형, 충격적 사실, 또는 "이거 아는 사람 거의 없는데" 패턴
- 스크롤을 멈추게 만드는 첫 문장이 가장 중요

### 2. 전개 (30~40초, 5~8문장)
- 짧은 문장 위주 (한 문장 15자 내외)
- "근데 진짜 놀라운 건", "여기서 반전인데" 같은 전환 표현 활용
- 구체적인 숫자, 사례, 비교를 포함
- 감정적 공감 유도 ("소름 돋지 않나요?", "이거 실화입니다")

### 3. 마무리 (5~10초, 2~3문장)
- 반전이나 핵심 한 줄 요약
- 댓글 유도 ("여러분은 어떻게 생각하세요?", "경험 있는 사람 댓글로")
- 구독/좋아요 유도는 자연스럽게 한 줄

## 규칙
- 구어체, MZ세대 말투 (근데, 진짜, 대박, ㄹㅇ 등 적절히)
- 총 분량: 200~300자 (한국어 기준)
- 문장 사이에 적절한 호흡(쉼표, 마침표)을 넣어 TTS가 자연스럽게 읽을 수 있도록
- 비속어/혐오 표현 절대 금지
- search_keywords는 대본 내용과 분위기에 맞는 영어 키워드 5개 (추상적이지 않고 구체적인 시각 장면)

## 트렌딩 토픽
{topics}

## 출력 형식 (JSON)
{{
  "title": "쇼츠 제목 (20자 이내, 호기심 유발, 이모지 1개 포함)",
  "script": "대본 전문 (훅-전개-마무리 구조)",
  "tags": ["태그1", "태그2", "태그3", "태그4", "태그5"],
  "search_keywords": ["scene keyword 1", "scene keyword 2", "scene keyword 3", "scene keyword 4", "scene keyword 5"],
  "topic_source": "선택한 원본 토픽 제목"
}}

JSON만 출력하세요."""


@dataclass
class ShortScript:
    title: str
    script: str
    tags: list[str]
    search_keywords: list[str]
    topic_source: str = ""


def _parse_json(text: str) -> dict:
    """LLM 응답에서 JSON을 추출한다."""
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    return json.loads(text.strip())


def generate_with_groq(topics: str) -> ShortScript:
    """Groq 무료 티어로 대본 생성."""
    from groq import Groq

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": SCRIPT_PROMPT.format(topics=topics)}],
        temperature=0.9,
        max_tokens=2048,
        response_format={"type": "json_object"},
    )

    data = json.loads(response.choices[0].message.content)
    return ShortScript(**data)


def generate_with_claude(topics: str) -> ShortScript:
    """Anthropic Claude로 대본 생성."""
    import anthropic

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{"role": "user", "content": SCRIPT_PROMPT.format(topics=topics)}],
    )

    data = _parse_json(response.content[0].text)
    return ShortScript(**data)


def generate(topics: str, provider: str = "groq") -> ShortScript:
    """대본 생성 통합 진입점.

    Args:
        topics: 트렌딩 토픽 텍스트
        provider: "groq" (무료) 또는 "claude"
    """
    if provider == "claude":
        return generate_with_claude(topics)
    return generate_with_groq(topics)
