"""전체 파이프라인 오케스트레이터.

실행: python -m src.orchestrator.main
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.collector.dcinside import run as collect_trending, save_posts
from src.script_gen.generator import generate
from src.tts.edge_tts_engine import synthesize
from src.video.pexels import fetch_videos
from src.editor.composer import compose
from src.uploader.youtube import upload


def pipeline(
    num_posts: int = 10,
    llm_provider: str = "groq",
    skip_upload: bool = False,
    dry_run: bool = False,
):
    """전체 파이프라인을 순차 실행한다.

    Args:
        num_posts: 수집할 트렌딩 게시글 수
        llm_provider: LLM 제공자 ("groq" 또는 "claude")
        skip_upload: True면 업로드 단계 건너뜀
        dry_run: True면 수집+대본 생성까지만 실행
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"\n{'='*50}")
    print(f"  AI Shorts Pipeline - {timestamp}")
    print(f"{'='*50}\n")

    # ── Step 1: 커뮤니티 트렌딩 수집 ──
    print("[1/6] 디시인사이드 HIT 갤러리 수집 중...")
    posts = collect_trending(num=num_posts)
    save_path = save_posts(posts)
    print(f"  → {len(posts)}개 게시글 수집 완료 → {save_path}")

    topics_text = "\n".join(
        f"- [{p.voteup_count}추천] {p.title}" for p in posts[:5]
    )
    print(f"  → 상위 5개 토픽:\n{topics_text}\n")

    # ── Step 2: LLM 대본 생성 ──
    print(f"[2/6] 대본 생성 중 (provider: {llm_provider})...")
    script = generate(topics_text, provider=llm_provider)
    print(f"  → 제목: {script.title}")
    print(f"  → 대본: {script.script[:80]}...")
    print(f"  → 검색 키워드: {script.search_keywords}\n")

    if dry_run:
        print("(dry-run 모드: 여기서 종료)")
        return

    # ── Step 3: TTS 음성 + 자막 ──
    print("[3/6] Edge TTS 음성 생성 중...")
    audio_path, srt_path = synthesize(script.script, filename=timestamp)
    print(f"  → 음성: {audio_path}")
    print(f"  → 자막: {srt_path}\n")

    # ── Step 4: 배경 영상 다운로드 ──
    print("[4/6] Pexels 배경 영상 다운로드 중...")
    video_paths = fetch_videos(script.search_keywords, per_keyword=2)
    print(f"  → {len(video_paths)}개 클립 다운로드 완료\n")

    # ── Step 5: 영상 합성 ──
    print("[5/6] FFmpeg 영상 합성 중...")
    final_path = compose(video_paths, audio_path, srt_path, output_name=timestamp)
    print(f"  → 최종 영상: {final_path}\n")

    # ── Step 6: YouTube 업로드 ──
    if skip_upload:
        print("[6/6] 업로드 건너뜀 (--skip-upload)")
    else:
        print("[6/6] YouTube 업로드 중...")
        description = (
            f"{script.script}\n\n"
            f"#{' #'.join(script.tags)}"
        )
        video_id = upload(final_path, script.title, description, script.tags)
        print(f"  → 업로드 완료: https://www.youtube.com/shorts/{video_id}")

    print(f"\n{'='*50}")
    print("  파이프라인 완료!")
    print(f"{'='*50}\n")


def main():
    parser = argparse.ArgumentParser(description="AI Shorts Pipeline")
    parser.add_argument("--posts", type=int, default=10, help="수집할 게시글 수")
    parser.add_argument("--provider", choices=["groq", "claude"], default="groq", help="LLM 제공자")
    parser.add_argument("--skip-upload", action="store_true", help="YouTube 업로드 건너뜀")
    parser.add_argument("--dry-run", action="store_true", help="수집+대본까지만 실행")
    args = parser.parse_args()

    pipeline(
        num_posts=args.posts,
        llm_provider=args.provider,
        skip_upload=args.skip_upload,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
