"""커뮤니티 트렌딩 토픽을 채팅 형식 대본으로 변환하는 생성기."""

import json
import os

from dotenv import load_dotenv

load_dotenv()

CHAT_SCRIPT_PROMPT = """당신은 한국 커뮤니티 '썰'을 메신저 채팅 형식으로 재구성하는 전문가입니다.
아래 트렌딩 토픽 중 가장 재밌고 바이럴 가능성이 높은 하나를 골라,
카카오톡/메신저 대화 형식의 쇼츠 대본을 작성하세요.

## 대본 규칙

### 구조
1. 2~4명의 등장인물이 메신저로 대화하는 형식
2. 메시지 수: 8~15개 (너무 적으면 밋밋, 너무 많으면 길어짐)
3. 각 메시지는 1~2줄 (최대 40자) - 짧고 임팩트 있게
4. 마지막에 반전/웃긴 결과를 result_text로 표시

### 말투
- 실제 카카오톡 대화처럼 자연스러운 구어체
- "ㅋㅋㅋ", "ㅎㅎ", "ㄹㅇ", "ㅇㅇ" 등 인터넷 표현 자연스럽게 사용
- 이모티콘은 텍스트 이모지로 (괜찮아요, 화이팅 등은 가능)

### 등장인물 배치
- side "left": 주로 이야기를 꺼내는 쪽 / 질문하는 쪽
- side "right": 주로 답변하는 쪽 / 반응하는 쪽
- 실감나는 직책이나 관계로 이름 설정 (예: "팀장 박과장", "후배 김대리", "친구 민수")

### result_text
- 대화의 결론/반전을 한 줄로 요약 (20자 이내)
- 예: "인상률: 0%", "결국 야근 확정", "월급 동결 ㅋㅋ"

## 트렌딩 토픽
{topics}

## 출력 형식 (JSON만 출력)
{{
  "category": "커뮤니티 썰",
  "title": "제목 (15자 이내, 호기심 유발)",
  "subtitle": "출처 또는 부제",
  "participants": ["참가자1", "참가자2"],
  "messages": [
    {{"sender": "참가자1", "text": "메시지 내용", "side": "left"}},
    {{"sender": "참가자2", "text": "답변 내용", "side": "right"}}
  ],
  "result_text": "결과 한 줄 요약",
  "tags": ["태그1", "태그2", "태그3", "태그4", "태그5"],
  "topic_source": "선택한 원본 토픽 제목"
}}

JSON만 출력하세요."""


def _parse_json(text: str) -> dict:
    """LLM 응답에서 JSON을 추출한다."""
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    return json.loads(text.strip())


def generate_chat_with_groq(topics: str) -> dict:
    """Groq 무료 티어로 채팅 대본 생성."""
    from groq import Groq

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": CHAT_SCRIPT_PROMPT.format(topics=topics)}],
        temperature=0.9,
        max_tokens=2048,
        response_format={"type": "json_object"},
    )

    return json.loads(response.choices[0].message.content)


def generate_chat_with_claude(topics: str) -> dict:
    """Anthropic Claude로 채팅 대본 생성."""
    import anthropic

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{"role": "user", "content": CHAT_SCRIPT_PROMPT.format(topics=topics)}],
    )

    return _parse_json(response.content[0].text)


def generate_chat(topics: str, provider: str = "groq") -> dict:
    """채팅 대본 생성 통합 진입점.

    Args:
        topics: 트렌딩 토픽 텍스트
        provider: "groq" (무료) 또는 "claude"

    Returns:
        채팅 대본 dict (ChatScript 로드 가능한 형식)
    """
    if provider == "claude":
        return generate_chat_with_claude(topics)
    return generate_chat_with_groq(topics)
