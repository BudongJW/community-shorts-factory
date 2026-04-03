"""디시인사이드 HIT 갤러리 트렌딩 게시글 수집기."""

import asyncio
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

import dc_api


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


async def collect_hit_posts(num: int = 20) -> list[TrendingPost]:
    """디시인사이드 HIT 갤러리에서 인기 게시글을 수집한다.

    Args:
        num: 수집할 게시글 수 (기본 20)

    Returns:
        TrendingPost 리스트 (조회수 내림차순 정렬)
    """
    posts = []

    async with dc_api.API() as api:
        async for index in api.board(board_id="hit", num=num):
            post = TrendingPost(
                id=index.id,
                title=index.title,
                author=index.author,
                view_count=index.view_count,
                comment_count=index.comment_count,
                voteup_count=index.voteup_count,
                subject=getattr(index, "subject", ""),
                time=str(index.time),
            )
            posts.append(post)

    posts.sort(key=lambda p: p.view_count, reverse=True)
    return posts


async def collect_with_content(num: int = 5) -> list[TrendingPost]:
    """게시글 본문까지 포함하여 수집한다. API 호출이 많으므로 소량만 권장."""
    posts = []

    async with dc_api.API() as api:
        async for index in api.board(board_id="hit", num=num):
            doc = await index.document()
            post = TrendingPost(
                id=index.id,
                title=index.title,
                author=index.author,
                view_count=index.view_count,
                comment_count=index.comment_count,
                voteup_count=index.voteup_count,
                subject=getattr(index, "subject", ""),
                time=str(index.time),
                content=doc.contents if doc.contents else "",
            )
            posts.append(post)

    posts.sort(key=lambda p: p.view_count, reverse=True)
    return posts


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


def run(num: int = 20, with_content: bool = False) -> list[TrendingPost]:
    """동기 진입점."""
    if with_content:
        return asyncio.run(collect_with_content(num))
    return asyncio.run(collect_hit_posts(num))


if __name__ == "__main__":
    posts = run(num=10)
    for i, p in enumerate(posts, 1):
        print(f"{i}. [{p.voteup_count:>4}추천 | {p.view_count:>6}조회] {p.title}")
