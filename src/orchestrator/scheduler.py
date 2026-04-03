"""파이프라인 스케줄러: 지정된 간격으로 자동 실행.

실행:
  python -m src.orchestrator.scheduler                  # 기본 (6시간 간격, 1편)
  python -m src.orchestrator.scheduler --interval 4     # 4시간 간격
  python -m src.orchestrator.scheduler --batch 3        # 회당 3편
  python -m src.orchestrator.scheduler --once            # 1회만 실행 후 종료
"""

import argparse
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.orchestrator.main import pipeline
from src.utils.logger import setup_logger

log = setup_logger("scheduler")


def run_scheduled(
    interval_hours: float = 6,
    batch: int = 1,
    provider: str = "groq",
    once: bool = False,
    max_retries: int = 3,
):
    """파이프라인을 주기적으로 실행한다.

    Args:
        interval_hours: 실행 간격 (시간)
        batch: 회당 생성할 영상 수
        provider: LLM 제공자
        once: True면 1회 실행 후 종료
        max_retries: 실패 시 재시도 횟수
    """
    run_count = 0

    log.info("")
    log.info("=" * 50)
    log.info("  AI Shorts Pipeline Scheduler")
    log.info(f"  간격: {interval_hours}시간 | 회당: {batch}편 | LLM: {provider}")
    if once:
        log.info("  모드: 1회 실행")
    else:
        log.info("  모드: 무한 반복 (Ctrl+C로 종료)")
    log.info("=" * 50)
    log.info("")

    while True:
        run_count += 1
        start_time = datetime.now()
        log.info(f"[스케줄 #{run_count}] {start_time.strftime('%Y-%m-%d %H:%M:%S')} 시작")

        success = False
        for attempt in range(1, max_retries + 1):
            try:
                pipeline(
                    num_posts=15,
                    llm_provider=provider,
                    skip_upload=False,
                    dry_run=False,
                    batch=batch,
                )
                success = True
                break
            except KeyboardInterrupt:
                log.info("\n사용자 중단 (Ctrl+C)")
                return
            except Exception as e:
                log.error(f"  [시도 {attempt}/{max_retries}] 에러: {e}")
                log.debug(traceback.format_exc())
                if attempt < max_retries:
                    wait = 60 * attempt  # 1분, 2분, 3분 대기
                    log.info(f"  {wait}초 후 재시도...")
                    time.sleep(wait)

        elapsed = (datetime.now() - start_time).total_seconds()
        status = "성공" if success else "실패"
        log.info(f"[스케줄 #{run_count}] {status} (소요: {elapsed:.0f}초)")

        if once:
            break

        # 다음 실행까지 대기
        next_run = interval_hours * 3600 - elapsed
        if next_run > 0:
            next_time = datetime.now().timestamp() + next_run
            next_str = datetime.fromtimestamp(next_time).strftime("%H:%M:%S")
            log.info(f"  다음 실행: {next_str} ({next_run / 60:.0f}분 후)")
            try:
                time.sleep(next_run)
            except KeyboardInterrupt:
                log.info("\n사용자 중단 (Ctrl+C)")
                return


def main():
    parser = argparse.ArgumentParser(description="AI Shorts Pipeline Scheduler")
    parser.add_argument("--interval", type=float, default=6, help="실행 간격 (시간, 기본 6)")
    parser.add_argument("--batch", type=int, default=1, help="회당 생성 영상 수 (기본 1)")
    parser.add_argument("--provider", choices=["groq", "claude"], default="groq")
    parser.add_argument("--once", action="store_true", help="1회만 실행 후 종료")
    args = parser.parse_args()

    run_scheduled(
        interval_hours=args.interval,
        batch=args.batch,
        provider=args.provider,
        once=args.once,
    )


if __name__ == "__main__":
    main()
