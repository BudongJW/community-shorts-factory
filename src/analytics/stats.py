"""업로드된 영상의 통계를 YouTube Data API v3로 수집·기록한다.

Analytics API (yt-analytics.readonly 스코프)는 재인증이 필요해서 미사용.
대신 Data API videos().list(part='statistics')로 view/like/comment만 수집 →
Day N별 조회수 추이 비교 가능.
"""

import json
from datetime import datetime
from pathlib import Path

from googleapiclient.errors import HttpError

from src.uploader.youtube import get_youtube_service
from src.utils.logger import setup_logger

log = setup_logger("analytics_stats")

# 업로드 직후 기록되는 생성 메타 — 어떤 variant/title/bucket이었는지 추적.
GENERATION_LOG_PATH = Path("output") / "generation_log.json"
# 주기적으로 채우는 조회수·좋아요 스냅샷.
STATS_PATH = Path("output") / "video_stats.json"


def record_generation(
    video_id: str,
    variant: str,
    title: str,
    day_num: int,
    target_duration: float,
    hook: str | None,
    uploaded_at: str | None = None,
):
    """업로드 성공 후 생성 메타를 로그에 append."""
    if not video_id:
        return
    entries = []
    if GENERATION_LOG_PATH.exists():
        try:
            entries = json.loads(GENERATION_LOG_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            entries = []
    entries.append({
        "video_id": video_id,
        "variant": variant,
        "title": title,
        "day": day_num,
        "target_duration": round(target_duration, 1),
        "hook": hook or "",
        "uploaded_at": uploaded_at or datetime.utcnow().isoformat(timespec="seconds") + "Z",
    })
    GENERATION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    GENERATION_LOG_PATH.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def fetch_stats_for_ids(video_ids: list[str]) -> dict[str, dict]:
    """video_id 리스트에 대해 statistics 벌크 조회. 한 번에 50개까지."""
    if not video_ids:
        return {}
    youtube = get_youtube_service()
    result: dict[str, dict] = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        try:
            resp = (
                youtube.videos()
                .list(id=",".join(batch), part="statistics,contentDetails")
                .execute()
            )
        except HttpError as e:
            log.warning(f"  fetch failed for batch: {e}")
            continue
        for item in resp.get("items", []):
            stats = item.get("statistics", {})
            content = item.get("contentDetails", {})
            result[item["id"]] = {
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "duration_iso": content.get("duration", ""),
            }
    return result


def snapshot_recent_stats(limit: int = 50):
    """generation_log의 최근 limit개 영상에 대해 stats 갱신.

    video_stats.json에 {video_id: [{ts, views, likes, comments}, ...]} 누적.
    같은 영상을 다른 시점에 snapshot하여 조회수 곡선 재구성 가능.
    """
    if not GENERATION_LOG_PATH.exists():
        log.info("  generation_log.json 없음. 업로드부터 먼저 누적하세요.")
        return

    entries = json.loads(GENERATION_LOG_PATH.read_text(encoding="utf-8"))
    recent = entries[-limit:]
    ids = [e["video_id"] for e in recent if e.get("video_id")]
    if not ids:
        return

    fresh = fetch_stats_for_ids(ids)
    if not fresh:
        log.warning("  0건 조회. 인증 또는 video_id 확인 필요.")
        return

    history: dict = {}
    if STATS_PATH.exists():
        try:
            history = json.loads(STATS_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            history = {}

    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for vid, data in fresh.items():
        history.setdefault(vid, []).append({"ts": now, **data})

    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATS_PATH.write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info(f"  snapshot complete: {len(fresh)} videos at {now}")


def summarize_performance(top_n: int = 10) -> dict:
    """variant·hook·bucket별 평균 조회수를 반환한다.

    다음 실행에서 가중치 소스로 쓸 수 있는 형태.
    """
    if not (GENERATION_LOG_PATH.exists() and STATS_PATH.exists()):
        return {}

    entries = json.loads(GENERATION_LOG_PATH.read_text(encoding="utf-8"))
    stats = json.loads(STATS_PATH.read_text(encoding="utf-8"))

    # 각 영상의 최신 views
    latest_views = {}
    for vid, snaps in stats.items():
        if snaps:
            latest_views[vid] = snaps[-1].get("views", 0)

    # variant별 평균
    by_variant: dict[str, list[int]] = {}
    by_hook: dict[str, list[int]] = {}
    by_bucket: dict[str, list[int]] = {}

    for e in entries:
        v = latest_views.get(e.get("video_id"))
        if v is None:
            continue
        by_variant.setdefault(e.get("variant", "?"), []).append(v)
        if e.get("hook"):
            by_hook.setdefault(e["hook"], []).append(v)
        d = e.get("target_duration", 0)
        bucket = "short" if d < 26 else "medium"
        by_bucket.setdefault(bucket, []).append(v)

    def _avg(d: dict[str, list[int]]) -> dict[str, float]:
        return {k: round(sum(vs) / len(vs), 1) for k, vs in d.items() if vs}

    return {
        "variant_avg_views": _avg(by_variant),
        "bucket_avg_views": _avg(by_bucket),
        "top_hooks": sorted(
            _avg(by_hook).items(), key=lambda x: x[1], reverse=True
        )[:top_n],
        "sample_size": len(latest_views),
    }


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--snapshot", action="store_true", help="최근 업로드 stats 갱신")
    p.add_argument("--summary", action="store_true", help="성과 요약 출력")
    p.add_argument("--limit", type=int, default=50)
    args = p.parse_args()

    if args.snapshot:
        snapshot_recent_stats(limit=args.limit)
    if args.summary:
        print(json.dumps(summarize_performance(), ensure_ascii=False, indent=2))
