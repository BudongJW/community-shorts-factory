"""전체 파이프라인 오케스트레이터.

실행:
  python -m src.orchestrator.main                    # 기존 나레이션 모드
  python -m src.orchestrator.main --mode chat         # 채팅 썰 모드
  python -m src.orchestrator.main --mode chat --json samples/chat_sample.json  # JSON 직접 지정
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.collector.dcinside import run as collect_trending, save_posts
from src.collector.filter import filter_topics
from src.collector.history import filter_new_topics, record_topic
from src.script_gen.generator import generate
from src.script_gen.chat_generator import generate_chat, format_topics_with_comments
from src.tts.edge_tts_engine import synthesize
from src.video.pexels import fetch_videos
from src.editor.composer import compose
from src.editor.chat_composer import compose_chat
from src.editor.chat_renderer import ChatScript, ChatMessage, load_chat_script
from src.editor.thumbnail import generate_thumbnail
from src.uploader.youtube import upload
from src.utils.logger import setup_logger

log = setup_logger("pipeline")


def pipeline_chat_single(
    posts,
    llm_provider: str = "groq",
    skip_upload: bool = False,
    run_id: str = "",
    json_path: str | None = None,
) -> dict | None:
    """채팅 썰 영상 생성 파이프라인.

    Returns:
        성공 시 결과 dict, 실패 시 None
    """
    if not run_id:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    if json_path:
        # JSON 파일에서 직접 로드
        log.info(f"[chat] JSON 대본 로드: {json_path}")
        script_data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    else:
        # ── 중복 필터링 ──
        titles = [p.title for p in posts[:5]]
        new_titles = filter_new_topics(titles)
        if not new_titles:
            log.warning("  모든 토픽이 이전에 사용됨 -- 건너뜀")
            return None

        filtered = [p for p in posts[:5] if p.title in new_titles]

        # ── 제목 + 댓글 기반 LLM 입력 생성 ──
        topics_text = format_topics_with_comments(filtered)

        # ── LLM 채팅 대본 생성 ──
        log.info(f"[chat 2/4] 채팅 대본 생성 중 (provider: {llm_provider})...")
        log.info(f"  -> 댓글 포함 게시글 {len(filtered)}개 입력")
        script_data = generate_chat(topics_text, provider=llm_provider)

    title = script_data.get("title", "커뮤니티 썰")
    log.info(f"  -> 제목: {title}")
    log.info(f"  -> 메시지 수: {len(script_data.get('messages', []))}개")

    # ChatScript 객체 생성
    messages = [ChatMessage(**m) for m in script_data.get("messages", [])]
    chat_script = ChatScript(
        category=script_data.get("category", "커뮤니티 썰"),
        title=title,
        subtitle=script_data.get("subtitle", ""),
        participants=script_data.get("participants", []),
        messages=messages,
        result_text=script_data.get("result_text", ""),
        source=script_data.get("topic_source", ""),
    )

    # ── 채팅 영상 합성 (BGM + SFX 포함) ──
    log.info("[chat 3/5] 채팅 영상 렌더링 중 (BGM + SFX)...")
    final_path = compose_chat(chat_script, output_name=run_id)
    log.info(f"  -> 최종: {final_path.name} ({final_path.stat().st_size // 1024}KB)")

    # ── 썸네일 생성 ──
    log.info("[chat 4/5] 썸네일 생성 중...")
    thumb_path = generate_thumbnail(
        title=title,
        result_text=script_data.get("result_text", ""),
        output_name=run_id,
    )
    log.info(f"  -> 썸네일: {thumb_path.name}")

    # ── YouTube 업로드 ──
    video_id = ""
    tags = script_data.get("tags", [])
    # #Shorts 태그 필수 포함
    if "#Shorts" not in tags and "Shorts" not in tags:
        tags.insert(0, "Shorts")

    # SEO 최적화된 설명
    description_lines = [
        title,
        "",
        " ".join(f"#{t.lstrip('#')}" for t in tags),
        "",
        "---",
        "커뮤니티 인기글을 채팅 형식으로 재구성한 쇼츠입니다.",
    ]
    description = "\n".join(description_lines)

    if skip_upload:
        log.info("[chat 5/5] 업로드 건너뜀 (--skip-upload)")
    else:
        log.info("[chat 5/5] YouTube 업로드 중...")
        video_id = upload(final_path, title, description, tags)
        log.info(f"  -> https://www.youtube.com/shorts/{video_id}")

    # ── 토픽 기록 ──
    topic_source = script_data.get("topic_source", title)
    record_topic(topic_source, video_id)

    return {
        "run_id": run_id,
        "title": title,
        "topic_source": topic_source,
        "final_path": str(final_path),
        "thumb_path": str(thumb_path),
        "video_id": video_id,
    }


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
    mode: str = "narration",
    json_path: str | None = None,
):
    """전체 파이프라인.

    Args:
        num_posts: 수집할 트렌딩 게시글 수
        llm_provider: "groq" 또는 "claude"
        skip_upload: True면 업로드 건너뜀
        dry_run: True면 수집+대본까지만
        batch: 생성할 영상 수
        mode: "narration" (기존) 또는 "chat" (채팅 썰)
        json_path: chat 모드에서 직접 JSON 대본 경로 지정
    """
    log.info("")
    log.info("=" * 50)
    log.info(f"  AI Shorts Pipeline ({mode} mode)")
    log.info("=" * 50)
    log.info("")

    # ── chat 모드: JSON 직접 지정 시 수집 건너뜀 ──
    if mode == "chat" and json_path:
        log.info(f"[chat] JSON 대본으로 직접 영상 생성: {json_path}")
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        result = pipeline_chat_single(
            [], llm_provider, skip_upload, run_id, json_path=json_path
        )
        if result:
            log.info("")
            log.info("=" * 50)
            log.info(f"  완료! {result['title']}")
            log.info(f"  -> {result['final_path']}")
            log.info("=" * 50)
        return

    # ── Step 1: 커뮤니티 트렌딩 수집 ──
    with_comments = (mode == "chat")
    with_content = (mode == "chat")  # 채팅 모드에서는 본문도 수집 (맥락 파악용)
    log.info(f"[1/6] 디시인사이드 HIT 갤러리 수집 중{'(+본문+댓글)' if with_comments else ''}...")
    posts = collect_trending(num=num_posts, with_content=with_content, with_comments=with_comments)
    save_path = save_posts(posts)
    log.info(f"  -> {len(posts)}개 게시글 수집 완료")

    top_posts = "\n".join(f"  - [{p.voteup_count}추천] {p.title}" for p in posts[:10])
    log.info(f"  -> 상위 토픽:\n{top_posts}")

    # ── Step 1.5: 니치 필터링 ──
    log.info("\n[1.5/6] 니치 필터링 중 (바이럴 가능성 판단)...")
    posts_for_filter = "\n".join(
        f"- [{p.voteup_count}추천 | {p.view_count}조회 | 댓글{p.comment_count}] {p.title}"
        for p in posts[:10]
    )
    filter_result = filter_topics(posts_for_filter, provider=llm_provider)

    selected = filter_result.get("selected", [])
    rejected = filter_result.get("rejected", [])
    log.info(f"  -> 선택: {len(selected)}개 / 제외: {len(rejected)}개")
    for s in selected:
        log.info(f"    [{s.get('score', '?')}점] {s['title']} -- {s.get('angle', '')}")
    for r in rejected:
        log.info(f"    x {r['title']} -- {r.get('reason', '')}")

    if not selected:
        log.warning("  바이럴 가능한 토픽 없음 -- 상위 3개로 대체 진행")
        selected_titles = [p.title for p in posts[:3]]
    else:
        selected_titles = [s["title"] for s in selected]

    # 선택된 토픽에 해당하는 posts만 필터
    filtered_posts = [p for p in posts if p.title in selected_titles] or posts[:3]

    if dry_run:
        log.info(f"\n[dry-run] 대본 생성 테스트...")
        if mode == "chat":
            topics_text = format_topics_with_comments(filtered_posts[:5])
            script_data = generate_chat(topics_text, provider=llm_provider)
            log.info(f"  -> 제목: {script_data.get('title', '')}")
            log.info(f"  -> 메시지 수: {len(script_data.get('messages', []))}개")
            log.info(f"  -> 결과: {script_data.get('result_text', '')}")
        else:
            script = generate(topics_text, provider=llm_provider)
            log.info(f"  -> 제목: {script.title}")
            log.info(f"  -> 대본 ({len(script.script)}자): {script.script}")
            log.info(f"  -> 태그: {script.tags}")
            log.info(f"  -> 키워드: {script.search_keywords}")
        log.info("\n(dry-run 모드 종료)")
        return

    # ── 배치 생성 ──
    results = []
    for i in range(batch):
        if batch > 1:
            log.info(f"\n{'--' * 20}")
            log.info(f"  영상 {i + 1}/{batch}")
            log.info(f"{'--' * 20}")

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + (f"_{i}" if batch > 1 else "")

        if mode == "chat":
            result = pipeline_chat_single(filtered_posts, llm_provider, skip_upload, run_id)
        else:
            result = pipeline_single(filtered_posts, llm_provider, skip_upload, run_id)

        if result:
            results.append(result)

    # ── 완료 리포트 ──
    log.info("")
    log.info("=" * 50)
    log.info(f"  파이프라인 완료! ({len(results)}/{batch}편 생성)")
    log.info("=" * 50)

    for r in results:
        log.info(f"  [{r['run_id']}] {r['title']} -> {r['final_path']}")

    log.info("")


def main():
    parser = argparse.ArgumentParser(description="AI Shorts Pipeline")
    parser.add_argument("--posts", type=int, default=10, help="수집할 게시글 수")
    parser.add_argument("--provider", choices=["groq", "claude"], default="groq")
    parser.add_argument("--skip-upload", action="store_true", help="YouTube 업로드 건너뜀")
    parser.add_argument("--dry-run", action="store_true", help="수집+대본까지만")
    parser.add_argument("--batch", type=int, default=1, help="생성할 영상 수 (기본 1)")
    parser.add_argument("--mode", choices=["narration", "chat"], default="narration",
                        help="영상 모드: narration(나레이션) 또는 chat(채팅 썰)")
    parser.add_argument("--json", type=str, default=None,
                        help="chat 모드에서 직접 JSON 대본 경로 지정")
    args = parser.parse_args()

    pipeline(
        num_posts=args.posts,
        llm_provider=args.provider,
        skip_upload=args.skip_upload,
        dry_run=args.dry_run,
        batch=args.batch,
        mode=args.mode,
        json_path=args.json,
    )


if __name__ == "__main__":
    main()
