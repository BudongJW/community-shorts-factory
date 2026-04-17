"""커뮤니티 트렌딩 토픽을 채팅 형식 대본으로 변환하는 생성기.

v2: 제목 + 댓글 원문을 기반으로 원본에 충실한 대본을 생성한다.
"""

import json
import os

from dotenv import load_dotenv

load_dotenv()

CHAT_SCRIPT_PROMPT = """당신은 한국 커뮤니티 인기글을 "카카오톡 대화 형식의 쇼츠 영상 대본"으로 재구성하는 전문가입니다.

아래에 커뮤니티 인기 게시글의 제목, 본문, 실제 댓글이 주어집니다.
가장 재밌는 게시글 하나를 골라, **하나의 완결된 에피소드**로 재구성하세요.

## 가장 중요한 규칙: 스토리가 있어야 한다

시청자가 영상을 보고 "아 이런 일이 있었구나"를 이해할 수 있어야 한다.
맥락 없는 감탄사 나열 (ㅋㅋ, 대박, ㄹㅇ)은 절대 금지.

모든 대본은 반드시 아래 4단 구조를 따라야 한다:

1. **상황 설명** (메시지 1~2): 무슨 일이 있었는지 구체적으로 설명
   - "야 오늘 야쿠르트 아줌마한테 뭐 사먹었는데" (X - 뭘 샀는지 안 나옴)
   - "야 오늘 야쿠르트 아줌마가 냉동고에서 뭐 꺼내는데 칼국수가 나옴 ㅋㅋ" (O - 구체적)
2. **전개/디테일** (메시지 3~6): 상황이 어떻게 흘러갔는지
   - 원본 게시글의 본문 내용을 대화로 풀어서 전달
   - 댓글의 구체적인 반응/추가 정보를 활용
3. **클라이막스/반전** (메시지 7~9): 가장 재밌거나 충격적인 포인트
4. **마무리/결론** (메시지 10~12 + result_text): 핵심 한 줄 요약

## 원본 활용 규칙
- **본문이 있으면**: 본문의 핵심 스토리를 대화로 풀어서 재구성. 원본의 디테일을 살려라.
- **본문이 이미지 위주면**: 제목과 댓글에서 "무슨 일인지"를 파악하고, 댓글의 구체적 반응(특정 장면 언급, 추가 정보)을 대화에 녹여라.
- **댓글 활용**: 짧은 감탄사(ㅋㅋ, ㄹㅇ) 말고, 구체적 내용이 담긴 댓글을 우선 활용.
- 광고/스팸 댓글은 무시.

## 이미지 삽입 규칙 (이미지가 있는 게시글인 경우)
- 게시글에 이미지가 포함되어 있으면, 대화 중 이미지를 공유하는 메시지를 넣어라.
- 이미지 메시지에는 `"image_index"` 필드를 추가: 원본 게시글 이미지 순번 (0부터 시작).
- 이미지 메시지의 text는 짧은 설명 또는 빈 문자열 ("이거 봐 ㅋㅋ", "사진 보내줄게" 등).
- 이미지는 2~4장 정도만 핵심적인 것을 골라서 사용 (전부 넣지 마라).
- 이미지는 주로 left(글쓴이) 쪽에서 보내는 것이 자연스럽다.
- 이미지가 없는 게시글이면 image_index를 사용하지 마라.

## 바이럴 규칙

### 훅 (첫 메시지)
- 첫 메시지에 핵심 키워드 + 호기심을 넣어라
- 예: "야 야쿠르트 아줌마가 칼국수를 팔아 ㅋㅋㅋ" (구체적 + 의외성)
- 인사/뜬금없는 질문으로 시작 금지

### 루핑
- result_text가 첫 메시지를 다시 떠올리게 해야 한다
- 예: 훅 "야쿠르트 아줌마 칼국수" -> result "야쿠르트 아줌마 = 만물상"

### 분량
- 메시지 8~12개 / 각 메시지 1~2줄 (최대 40자)
- 매 메시지가 스토리를 진행시켜야 한다. 의미 없는 추임새 금지.

## 말투
- 실제 카카오톡 대화 구어체
- 원본 댓글의 말투 반영 (ㅋㅋ, ㄹㅇ 등)
- 비속어/혐오는 순화하되 뉘앙스 유지
- 반드시 한국어만 사용. 한자, 일본어, 중국어 글자 절대 금지.

## 등장인물
- side "left": 이야기를 전달하는 쪽 (글쓴이 역할)
- side "right": 반응하며 질문/공감하는 쪽 (친구 역할)
- 자연스러운 이름 (예: "글쓴이", "친구", "동생")

## 금지 사항 (이걸 쓰면 영상이 망한다)
- "와 대단하다", "맞아", "진짜?", "헐" 같은 의미 없는 추임새로만 이루어진 메시지 금지
- 반응하는 쪽도 반드시 구체적 내용을 담아야 함 (예: "그래서 결국 어떻게 됐는데?", "아니 그게 가능해? ㅋㅋ")
- subtitle 필드는 반드시 "디시인사이드 HIT 갤러리"로 고정

## 커뮤니티 게시글 데이터
{topics}

## 출력 형식 (JSON만 출력, 다른 텍스트 금지)
{{
  "category": "커뮤니티 썰",
  "title": "제목 (핵심 키워드 + 호기심, 15자 이내)",
  "subtitle": "디시인사이드 HIT 갤러리",
  "participants": ["글쓴이역이름", "반응역이름"],
  "messages": [
    {{"sender": "이름", "text": "상황설명 (구체적으로)", "side": "left"}},
    {{"sender": "이름", "text": "반응 (질문/공감)", "side": "right"}},
    {{"sender": "이름", "text": "이거 봐 ㅋㅋ", "side": "left", "image_index": 0}},
    {{"sender": "이름", "text": "전개 (디테일 추가)", "side": "left"}},
    {{"sender": "이름", "text": "...", "side": "right"}}
  ],
  "result_text": "핵심 한줄 결론 (15자 이내)",
  "tags": ["#Shorts", "태그1", "태그2", "태그3", "태그4", "태그5", "태그6", "태그7"],
  "topic_source": "선택한 원본 게시글 제목"
}}"""


def format_post_with_comments(post) -> str:
    """TrendingPost 객체를 LLM 입력용 텍스트로 포맷한다."""
    lines = [
        f"### [{post.voteup_count}추천 | {post.view_count}조회 | 댓글{post.comment_count}] {post.title}",
    ]

    if hasattr(post, 'image_urls') and post.image_urls:
        lines.append(f"\n[이미지 {len(post.image_urls)}장 포함 게시글 - image_index 0~{len(post.image_urls)-1} 사용 가능]")

    if post.content:
        # 본문 텍스트 (이미지 태그 제거 후 실제 텍스트만)
        content = post.content.strip()
        if len(content) > 800:
            content = content[:800] + "..."
        if content:
            lines.append(f"\n본문:\n{content}")

    if post.comments:
        # 스팸/광고/너무 짧은 댓글 필터링
        good_comments = []
        for c in post.comments:
            text = c.text.strip()
            if not text or len(text) <= 2:
                continue
            # 광고/스팸 필터
            if any(spam in text.lower() for spam in ["http", "카톡", "텔레", "오픈채팅", ".com", ".kr"]):
                continue
            good_comments.append(c)

        if good_comments:
            lines.append("\n댓글 (내용 있는 것만):")
            for c in good_comments[:20]:
                prefix = "  ㄴ" if c.is_reply else "  -"
                lines.append(f"{prefix} {c.author}: {c.text.strip()[:150]}")

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
