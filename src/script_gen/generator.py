"""트렌딩 토픽 기반 YouTube Shorts 대본 생성기."""

import json
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

SCRIPT_PROMPT = """당신은 YouTube Shorts 대본 작가입니다.
아래 커뮤니티 트렌딩 토픽을 바탕으로 60초 이내의 쇼츠 대본을 작성하세요.

## 규칙
- 첫 3초 안에 시청자의 관심을 끄는 훅(hook)으로 시작
- 구어체, 짧은 문장, 빠른 전개
- 총 분량: 150~200자 (한국어 기준, 60초 내 읽을 수 있는 양)
- 마지막에 구독/좋아요 유도 한 줄

## 트렌딩 토픽
{topics}

## 출력 형식 (JSON)
{{
  "title": "쇼츠 제목 (30자 이내, 호기심 유발)",
  "script": "대본 전문",
  "tags": ["태그1", "태그2", "태그3"],
  "search_keywords": ["Pexels 영상 검색용 영어 키워드1", "키워드2", "키워드3"]
}}

JSON만 출력하세요."""


@dataclass
class ShortScript:
    title: str
    script: str
    tags: list[str]
    search_keywords: list[str]


def generate_with_groq(topics: str) -> ShortScript:
    """Groq 무료 티어로 대본 생성."""
    from groq import Groq

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": SCRIPT_PROMPT.format(topics=topics)}],
        temperature=0.8,
        max_tokens=1024,
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
        max_tokens=1024,
        messages=[{"role": "user", "content": SCRIPT_PROMPT.format(topics=topics)}],
    )

    text = response.content[0].text
    # Claude는 JSON 블록을 ```json ... ``` 으로 감쌀 수 있음
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    data = json.loads(text.strip())
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
