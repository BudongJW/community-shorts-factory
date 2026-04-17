"""커뮤니티 트렌딩 토픽을 채팅 형식 대본으로 변환하는 생성기.

v2: 제목 + 댓글 원문을 기반으로 원본에 충실한 대본을 생성한다.
"""

import json
import os

from dotenv import load_dotenv

load_dotenv()

CHAT_SCRIPT_PROMPT = """당신은 한국 커뮤니티 인기글을 메신저 채팅 형식의 쇼츠 영상 대본으로 재구성하는 전문가입니다.

아래에 커뮤니티 인기 게시글의 제목과 실제 댓글들이 주어집니다.
이 중 가장 재밌고 바이럴 가능성이 높은 게시글 하나를 골라,
실제 댓글의 분위기와 내용을 살려서 카카오톡 대화 형식으로 재구성하세요.

## 핵심 원칙
- 댓글에서 실제로 나온 반응, 말투, 유머를 최대한 살려라
- 댓글의 핵심 내용을 대화 형식으로 자연스럽게 재배치하라
- 100% 창작하지 말고, 원본 댓글의 맥락을 기반으로 재구성하라
- 댓글에 없는 내용을 과도하게 추가하지 마라

## 대본 규칙

### 구조
1. 2~4명의 등장인물이 메신저로 대화하는 형식
2. 메시지 수: 8~15개
3. 각 메시지는 1~2줄 (최대 40자) - 짧고 임팩트 있게
4. 마지막에 반전/웃긴 결과를 result_text로 표시

### 말투
- 실제 카카오톡 대화처럼 자연스러운 구어체
- 원본 댓글의 말투를 최대한 반영 (ㅋㅋ, ㄹㅇ, ㅇㅇ 등)
- 비속어/혐오 표현은 순화하되 뉘앙스는 유지

### 등장인물 배치
- side "left": 이야기를 꺼내는 쪽 / 질문하는 쪽
- side "right": 반응하는 쪽 / 공감/반박하는 쪽
- 주제에 맞는 자연스러운 이름 (예: "글쓴이", "댓글러1", "지나가던 형", "동료 김씨")
- 실제 댓글 작성자의 닉네임 특성을 참고해도 좋음

### result_text
- 대화의 결론/반전을 한 줄로 요약 (20자 이내)

## 커뮤니티 게시글 데이터
{topics}

## 출력 형식 (JSON만 출력)
{{
  "category": "커뮤니티 썰",
  "title": "제목 (15자 이내, 호기심 유발)",
  "subtitle": "디시인사이드 HIT 갤러리",
  "participants": ["참가자1", "참가자2"],
  "messages": [
    {{"sender": "참가자1", "text": "메시지 내용", "side": "left"}},
    {{"sender": "참가자2", "text": "답변 내용", "side": "right"}}
  ],
  "result_text": "결과 한 줄 요약",
  "tags": ["태그1", "태그2", "태그3", "태그4", "태그5"],
  "topic_source": "선택한 원본 게시글 제목"
}}

JSON만 출력하세요."""


def format_post_with_comments(post) -> str:
    """TrendingPost 객체를 LLM 입력용 텍스트로 포맷한다."""
    lines = [
        f"### [{post.voteup_count}추천 | {post.view_count}조회 | 댓글{post.comment_count}] {post.title}",
    ]

    if post.content:
        # 본문이 너무 길면 앞부분만
        content = post.content[:500]
        lines.append(f"본문: {content}")

    if post.comments:
        lines.append("댓글:")
        for c in post.comments:
            prefix = "  ㄴ" if c.is_reply else "  -"
            text = c.text.strip()
            if text and len(text) > 2:  # 빈 댓글/너무 짧은 댓글 제외
                lines.append(f"{prefix} {c.author}: {text[:100]}")

    return "\n".join(lines)


def format_topics_with_comments(posts: list) -> str:
    """여러 게시글을 LLM 입력용으로 포맷한다."""
    sections = []
    for post in posts:
        sections.append(format_post_with_comments(post))
    return "\n\n".join(sections)


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
        topics: 트렌딩 토픽 텍스트 (format_topics_with_comments 출력)
        provider: "groq" (무료) 또는 "claude"

    Returns:
        채팅 대본 dict (ChatScript 로드 가능한 형식)
    """
    if provider == "claude":
        return generate_chat_with_claude(topics)
    return generate_chat_with_groq(topics)
