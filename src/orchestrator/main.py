"""전체 파이프라인 오케스트레이터.

실행: python -m src.orchestrator.main
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.collector.dcinside import run as collect_trending, save_posts
from src.collector.filter import filter_topics
from src.collector.history import filter_new_topics, record_topic
from src.script_gen.generator import generate
from src.tts.edge_tts_engine import synthesize
from src.video.pexels import fetch_videos
from src.editor.composer import compose
from src.uploader.youtube import upload
from src.utils.logger import setup_logger

log = setup_logger("pipeline")


def pipeline_single(
    posts,
    llm_provider: str = "groq",
    skip_upload: bool = False,
    run_id: str = "",
) -> dict | None:
    """단일 영상 생성 파이프라인.

    Returns:
        성공 시 결과 dict, 실패 시 None
    """
    if not run_id:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── 중복 필터링 ──
    titles = [p.title for p in posts[:5]]
    new_titles = filter_new_topics(titles)
    if not new_titles:
        log.warning("  모든 토픽이 이전에 사용됨 — 건너뜀")
        return None

    topics_text = "\n".join(
        f"- [{p.voteup_count}추천] {p.title}"
        for p in posts[:5]
        if p.title in new_titles
    )

    # ── LLM 대본 생성 ──
    log.info(f"[2/6] 대본 생성 중 (provider: {llm_provider})...")
    script = generate(topics_text, provider=llm_provider)
    log.info(f"  → 제목: {script.title}")
    log.info(f"  → 대본 길이: {len(script.script)}자")
    log.info(f"  → 원본 토픽: {script.topic_source}")
    log.debug(f"  → 대본: {script.script}")

    # ── TTS 음성 + 자막 ──
    log.info("[3/6] Edge TTS 음성 생성 중...")
    audio_path, srt_path, tts_meta = synthesize(script.script, filename=run_id)
    log.info(f"  → 음성: {tts_meta['voice']} (속도: {tts_meta['rate']})")
    log.info(f"  → 파일: {audio_path.name} ({audio_path.stat().st_size // 1024}KB)")

    # ── 배경 영상 다운로드 ──
    log.info("[4/6] 배경 영상 다운로드 중...")
    video_paths = fetch_videos(script.search_keywords, per_keyword=1)
    log.info(f"  → {len(video_paths)}개 클립 준비 완료")

    # ── 영상 합성 ──
    log.info("[5/6] FFmpeg 영상 합성 중...")
    final_path = compose(video_paths, audio_path, srt_path, output_name=run_id)
    log.info(f"  → 최종: {final_path.name} ({final_path.stat().st_size // 1024}KB)")

    # ── YouTube 업로드 ──
    video_id = ""
    if skip_upload:
        log.info("[6/6] 업로드 건너뜀 (--skip-upload)")
    else:
        log.info("[6/6] YouTube 업로드 중...")
        description = f"{script.script}\n\n#{' #'.join(script.tags)}"
        video_id = upload(final_path, script.title, description, script.tags)
        log.info(f"  → https://www.youtube.com/shorts/{video_id}")

    # ── 토픽 기록 ──
    record_topic(script.topic_source or script.title, video_id)

    return {
        "run_id": run_id,
        "title": script.title,
        "topic_source": script.topic_source,
        "voice": tts_meta["voice"],
        "final_path": str(final_path),
        "video_id": video_id,
    }


def pipeline(
    num_posts: int = 10,
    llm_provider: str = "groq",
    skip_upload: bool = False,
    dry_run: bool = False,
    batch: int = 1,
):
    """전체 파이프라인.

    Args:
        num_posts: 수집할 트렌딩 게시글 수
        llm_provider: "groq" 또는 "claude"
        skip_upload: True면 업로드 건너뜀
        dry_run: True면 수집+대본까지만
        batch: 생성할 영상 수
    """
    log.info("")
    log.info("=" * 50)
    log.info("  AI Shorts Pipeline")
    log.info("=" * 50)
    log.info("")

    # ── Step 1: 커뮤니티 트렌딩 수집 ──
    log.info("[1/6] 디시인사이드 HIT 갤러리 수집 중...")
    posts = collect_trending(num=num_posts)
    save_path = save_posts(posts)
    log.info(f"  → {len(posts)}개 게시글 수집 완료")

    top_posts = "\n".join(f"  - [{p.voteup_count}추천] {p.title}" for p in posts[:10])
    log.info(f"  → 상위 토픽:\n{top_posts}")

    # ── Step 1.5: 니치 필터링 ──
    log.info("\n[1.5/6] 니치 필터링 중 (바이럴 가능성 판단)...")
    posts_for_filter = "\n".join(
        f"- [{p.voteup_count}추천 | {p.view_count}조회 | 댓글{p.comment_count}] {p.title}"
        for p in posts[:10]
    )
    filter_result = filter_topics(posts_for_filter, provider=llm_provider)

    selected = filter_result.get("selected", [])
    rejected = filter_result.get("rejected", [])
    log.info(f"  → 선택: {len(selected)}개 / 제외: {len(rejected)}개")
    for s in selected:
        log.info(f"    ✓ [{s.get('score', '?')}점] {s['title']} — {s.get('angle', '')}")
    for r in rejected:
        log.info(f"    ✗ {r['title']} — {r.get('reason', '')}")

    if not selected:
        log.warning("  바이럴 가능한 토픽 없음 — 상위 3개로 대체 진행")
        selected_titles = [p.title for p in posts[:3]]
    else:
        selected_titles = [s["title"] for s in selected]

    # 선택된 토픽에 해당하는 posts만 필터
    filtered_posts = [p for p in posts if p.title in selected_titles] or posts[:3]

    if dry_run:
        topics_text = "\n".join(f"- [{p.voteup_count}추천] {p.title}" for p in filtered_posts[:5])
        log.info(f"\n[dry-run] 대본 생성 테스트...")
        script = generate(topics_text, provider=llm_provider)
        log.info(f"  → 제목: {script.title}")
        log.info(f"  → 대본 ({len(script.script)}자): {script.script}")
        log.info(f"  → 태그: {script.tags}")
        log.info(f"  → 키워드: {script.search_keywords}")
        log.info("\n(dry-run 모드 종료)")
        return

    # ── 배치 생성 ──
    results = []
    for i in range(batch):
        if batch > 1:
            log.info(f"\n{'─' * 40}")
            log.info(f"  영상 {i + 1}/{batch}")
            log.info(f"{'─' * 40}")

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + (f"_{i}" if batch > 1 else "")
        result = pipeline_single(filtered_posts, llm_provider, skip_upload, run_id)
        if result:
            results.append(result)

    # ── 완료 리포트 ──
    log.info("")
    log.info("=" * 50)
    log.info(f"  파이프라인 완료! ({len(results)}/{batch}편 생성)")
    log.info("=" * 50)

    for r in results:
        log.info(f"  [{r['run_id']}] {r['title']} → {r['final_path']}")

    log.info("")


def main():
    parser = argparse.ArgumentParser(description="AI Shorts Pipeline")
    parser.add_argument("--posts", type=int, default=10, help="수집할 게시글 수")
    parser.add_argument("--provider", choices=["groq", "claude"], default="groq")
    parser.add_argument("--skip-upload", action="store_true", help="YouTube 업로드 건너뜀")
    parser.add_argument("--dry-run", action="store_true", help="수집+대본까지만")
    parser.add_argument("--batch", type=int, default=1, help="생성할 영상 수 (기본 1)")
    args = parser.parse_args()

    pipeline(
        num_posts=args.posts,
        llm_provider=args.provider,
        skip_upload=args.skip_upload,
        dry_run=args.dry_run,
        batch=args.batch,
    )


if __name__ == "__main__":
    main()
