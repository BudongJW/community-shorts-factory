"""Pexels / Pixabay에서 고양이 영상을 수집한다.

무료 API를 사용하여 로열티 프리 고양이 클립을 다운로드한다.
세로(portrait) 영상 우선, 없으면 가로 영상도 수집 후 크롭한다.
"""

import json
import os
import random
from pathlib import Path

import requests
from dotenv import load_dotenv

from config.settings import VIDEO_DIR
from src.utils.logger import setup_logger

load_dotenv()

log = setup_logger("cat_collector")

# 고양이 관련 검색 키워드 (영어)
CAT_QUERIES = [
    "funny cat",
    "cat jumping",
    "cat playing",
    "kitten",
    "cat fail",
    "cat running",
    "crazy cat",
    "cat surprise",
    "cat vs",
    "cat sleeping funny",
    "cat water",
    "cat box",
    "cat knock",
    "cat zoomies",
    "cat angry",
    "cat scared",
    "cat cute",
    "cat derp",
]

# 이미 사용한 영상 ID를 추적하여 중복 방지
HISTORY_PATH = Path(__file__).parent.parent.parent / "output" / "cat_video_history.json"
# 슬라이딩 윈도우 크기 — 이 개수만큼 최근 ID만 유지 (Pexels 풀 고갈 방지)
HISTORY_MAX = 500


def _load_history_list() -> list[str]:
    """사용 순서가 보존된 영상 ID 리스트."""
    if HISTORY_PATH.exists():
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        # 과거 포맷(set→list 변환)과 호환. 순서 없으면 그대로 사용.
        return list(data)
    return []


def _load_history() -> set[str]:
    return set(_load_history_list())


def _record_used(video_id: str):
    """영상 사용 기록을 추가한다. 슬라이딩 윈도우 적용."""
    ids = _load_history_list()
    # 중복 제거 후 맨 뒤에 추가 (최근성 유지)
    ids = [i for i in ids if i != video_id]
    ids.append(video_id)
    # 최근 HISTORY_MAX개만 유지
    if len(ids) > HISTORY_MAX:
        ids = ids[-HISTORY_MAX:]
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(
        json.dumps(ids, ensure_ascii=False), encoding="utf-8"
    )


def search_pexels(query: str, per_page: int = 30) -> list[dict]:
    """Pexels API로 영상을 검색한다. rank는 Pexels 응답 순서 = 관련성/인기도 프록시."""
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        return []

    try:
        resp = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": api_key},
            params={
                "query": query,
                "per_page": per_page,
                "orientation": "portrait",
                "size": "medium",
            },
            timeout=15,
        )
        resp.raise_for_status()
        videos = resp.json().get("videos", [])

        # portrait 결과 없으면 landscape로 재시도
        if not videos:
            resp = requests.get(
                "https://api.pexels.com/videos/search",
                headers={"Authorization": api_key},
                params={"query": query, "per_page": per_page},
                timeout=15,
            )
            resp.raise_for_status()
            videos = resp.json().get("videos", [])

        return [
            {
                "id": f"pexels_{v['id']}",
                "source": "pexels",
                "duration": v.get("duration", 0),
                "width": v.get("width", 0),
                "height": v.get("height", 0),
                "files": v.get("video_files", []),
                "rank": rank,  # 0 = Pexels 최상위 (가장 관련성·인기 있는 것)
            }
            for rank, v in enumerate(videos)
        ]
    except Exception as e:
        log.warning(f"  Pexels search failed: {e}")
        return []


def search_pixabay(query: str, per_page: int = 15) -> list[dict]:
    """Pixabay API로 영상을 검색한다."""
    api_key = os.getenv("PIXABAY_API_KEY")
    if not api_key:
        return []

    try:
        resp = requests.get(
            "https://pixabay.com/api/videos/",
            params={
                "key": api_key,
                "q": query,
                "per_page": per_page,
                "video_type": "film",
            },
            timeout=15,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])

        results = []
        for rank, v in enumerate(hits):
            # Pixabay video files
            vids = v.get("videos", {})
            files = []
            for quality in ["large", "medium", "small"]:
                vf = vids.get(quality, {})
                if vf.get("url"):
                    files.append({
                        "link": vf["url"],
                        "quality": quality,
                        "width": vf.get("width", 0),
                        "height": vf.get("height", 0),
                    })

            results.append({
                "id": f"pixabay_{v['id']}",
                "source": "pixabay",
                "duration": v.get("duration", 0),
                "width": v.get("videos", {}).get("large", {}).get("width", 0),
                "height": v.get("videos", {}).get("large", {}).get("height", 0),
                "files": files,
                "rank": rank,
            })
        return results
    except Exception as e:
        log.warning(f"  Pixabay search failed: {e}")
        return []


def _pick_best_file(files: list[dict]) -> str | None:
    """HD 이상 품질의 다운로드 URL을 선택한다."""
    # quality 우선순위: hd > sd > large > medium
    for q in ["hd", "sd", "large", "medium"]:
        for f in files:
            if f.get("quality") == q and f.get("link"):
                return f["link"]
    # 아무거나
    for f in files:
        if f.get("link"):
            return f["link"]
    return None


def _score_candidate(v: dict, sweet_spot: float = 22.0) -> float:
    """후보 영상의 품질 점수를 계산한다.

    Shorts 리텐션 근거:
    - 15~30초가 완주율이 가장 높음 (22초 근처 피크)
    - Pexels 상위 결과 = 관련성/인기도 프록시
    - portrait 원본 > 크롭한 landscape (위아래 잘림 없음)
    """
    duration = v.get("duration", 0)
    rank = v.get("rank", 50)
    # duration 점수: sweet_spot에서 1.0, 멀어질수록 감소 (10초 차이 = 0.5 감소)
    dur_score = max(0.0, 1.0 - abs(duration - sweet_spot) / 20.0)
    # rank 점수: 0위 = 1.0, 30위 = 0.0
    rank_score = max(0.0, 1.0 - rank / 30.0)
    # portrait 보너스: 세로 영상이면 +0.3
    aspect_bonus = 0.3 if v.get("height", 0) > v.get("width", 0) else 0.0
    return dur_score * 0.5 + rank_score * 0.4 + aspect_bonus


def _weighted_pick(candidates: list[dict], top_n: int = 10) -> list[dict]:
    """상위 top_n 후보를 점수 기반 가중치로 재정렬한다.

    shuffle하지 않음 — 상위권에 있을수록 뽑힐 확률이 높지만 완전 결정론적이진 않음.
    """
    if not candidates:
        return []
    top = candidates[:top_n]
    # 점수를 weight로 사용하여 비복원 추출 (상위권이 더 자주 선택됨)
    weights = [c["_score"] + 0.01 for c in top]  # 0 방지
    picked = []
    pool = list(top)
    pool_weights = list(weights)
    while pool:
        idx = random.choices(range(len(pool)), weights=pool_weights, k=1)[0]
        picked.append(pool.pop(idx))
        pool_weights.pop(idx)
    # 나머지는 그대로 뒤에 붙임
    return picked + candidates[top_n:]


def collect_cat_clips(
    count: int = 3,
    min_duration: int = 10,
    max_duration: int = 40,
) -> list[Path]:
    """고양이 영상 클립을 수집하여 다운로드한다.

    Args:
        count: 수집할 클립 수
        min_duration: 최소 길이(초) — Shorts는 짧을수록 완주율↑
        max_duration: 최대 길이(초) — 40초 이상이면 중간 이탈 급증

    Returns:
        다운로드된 영상 파일 경로 리스트
    """
    history = _load_history()
    output_dir = VIDEO_DIR / "cats"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 랜덤 키워드 3개로 풀을 넓힌다 (쿼리별 상위권 가능성↑)
    queries = random.sample(CAT_QUERIES, min(len(CAT_QUERIES), max(3, count * 3)))
    all_videos = []

    for q in queries:
        results = search_pexels(q)
        results += search_pixabay(q)
        all_videos.extend(results)

        if len(all_videos) >= count * 10:
            break

    # 필터링: 길이 + 미사용
    candidates = [
        v for v in all_videos
        if min_duration <= v["duration"] <= max_duration
        and v["id"] not in history
    ]

    # 점수 매기고 정렬
    for c in candidates:
        c["_score"] = _score_candidate(c)
    candidates.sort(key=lambda c: c["_score"], reverse=True)
    candidates = _weighted_pick(candidates, top_n=10)

    downloaded = []
    for v in candidates:
        if len(downloaded) >= count:
            break

        url = _pick_best_file(v["files"])
        if not url:
            continue

        try:
            log.info(f"  downloading {v['id']} ({v['duration']}s)...")
            resp = requests.get(url, stream=True, timeout=60)
            resp.raise_for_status()

            out_path = output_dir / f"{v['id']}.mp4"
            with open(out_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            _record_used(v["id"])
            downloaded.append(out_path)
            log.info(f"  -> {out_path.name} ({out_path.stat().st_size // 1024}KB)")

        except Exception as e:
            log.warning(f"  download failed {v['id']}: {e}")
            continue

    return downloaded
