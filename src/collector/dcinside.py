"""디시인사이드 갤러리 트렌딩 게시글 수집기.

본문 + 댓글까지 수집하여 LLM 대본 생성의 품질을 높인다.
"""

import asyncio
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

import dc_api


@dataclass
class Comment:
    author: str
    text: str
    is_reply: bool = False


@dataclass
class TrendingPost:
    id: int
    title: str
    author: str
    view_count: int
    comment_count: int
    voteup_count: int
    subject: str
    time: str
    content: str = ""
    comments: list[Comment] = field(default_factory=list)
    gallery_id: str = ""


# 수집 대상 갤러리 (id, is_minor)
DEFAULT_GALLERIES = [
    ("hit", False),         # HIT 갤러리 (핫 게시글 모음)
]

# 요청 간 대기 시간 (초) - 차단 방지
REQUEST_DELAY = 0.5


async def collect_posts(
    board_id: str = "hit",
    num: int = 20,
    is_minor: bool = False,
    with_content: bool = False,
    with_comments: bool = False,
    max_comments: int = 30,
) -> list[TrendingPost]:
    """갤러리에서 게시글을 수집한다.

    Args:
        board_id: 갤러리 ID
        num: 수집할 게시글 수
        is_minor: 마이너 갤러리 여부
        with_content: 본문 수집 여부
        with_comments: 댓글 수집 여부
        max_comments: 게시글당 최대 댓글 수
    """
    posts = []

    async with dc_api.API() as api:
        async for index in api.board(board_id=board_id, num=num, is_minor=is_minor):
            post = TrendingPost(
                id=index.id,
                title=index.title,
                author=index.author,
                view_count=index.view_count,
                comment_count=index.comment_count,
                voteup_count=index.voteup_count,
                subject=getattr(index, "subject", ""),
                time=str(index.time),
                gallery_id=board_id,
            )

            if with_content:
                try:
                    doc = await index.document()
                    post.content = doc.contents if doc.contents else ""
                    await asyncio.sleep(REQUEST_DELAY)
                except Exception:
                    pass

            if with_comments:
                try:
                    collected = []
                    async for com in index.comments():
                        collected.append(Comment(
                            author=com.author or "",
                            text=com.contents or "",
                            is_reply=getattr(com, "is_reply", False),
                        ))
                        if len(collected) >= max_comments:
                            break
                    post.comments = collected
                    await asyncio.sleep(REQUEST_DELAY)
                except Exception:
                    pass

            posts.append(post)

    posts.sort(key=lambda p: p.voteup_count, reverse=True)
    return posts


async def collect_multi_gallery(
    galleries: list[tuple[str, bool]] | None = None,
    num_per_gallery: int = 10,
    with_content: bool = False,
    with_comments: bool = False,
) -> list[TrendingPost]:
    """여러 갤러리에서 수집 후 통합한다."""
    if galleries is None:
        galleries = DEFAULT_GALLERIES

    all_posts = []
    for board_id, is_minor in galleries:
        try:
            posts = await collect_posts(
                board_id=board_id,
                num=num_per_gallery,
                is_minor=is_minor,
                with_content=with_content,
                with_comments=with_comments,
            )
            all_posts.extend(posts)
        except Exception:
            continue

    all_posts.sort(key=lambda p: p.voteup_count, reverse=True)
    return all_posts


def save_posts(posts: list[TrendingPost], output_dir: Path | None = None) -> Path:
    """수집 결과를 JSON으로 저장한다."""
    if output_dir is None:
        output_dir = Path(__file__).parent.parent.parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = output_dir / f"trending_{timestamp}.json"

    data = [asdict(p) for p in posts]
    filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return filepath


def run(num: int = 20, with_content: bool = False, with_comments: bool = False) -> list[TrendingPost]:
    """동기 진입점."""
    return asyncio.run(collect_posts(
        board_id="hit",
        num=num,
        with_content=with_content,
        with_comments=with_comments,
    ))


if __name__ == "__main__":
    posts = run(num=5, with_content=True, with_comments=True)
    for i, p in enumerate(posts, 1):
        print(f"\n{i}. [{p.voteup_count:>4}추천 | {p.view_count:>6}조회] {p.title}")
        if p.content:
            preview = p.content[:100].replace("\n", " ")
            print(f"   본문: {preview}...")
        if p.comments:
            print(f"   댓글 {len(p.comments)}개:")
            for c in p.comments[:3]:
                print(f"     {'ㄴ' if c.is_reply else '-'} {c.author}: {c.text[:50]}")
