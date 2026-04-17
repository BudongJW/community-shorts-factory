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


def _load_history() -> set[str]:
    """사용한 영상 ID 히스토리를 로드한다."""
    if HISTORY_PATH.exists():
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        return set(data)
    return set()


def _save_history(ids: set[str]):
    """사용한 영상 ID를 저장한다."""
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(
        json.dumps(list(ids), ensure_ascii=False), encoding="utf-8"
    )


def _record_used(video_id: str):
    """영상 사용 기록을 추가한다."""
    history = _load_history()
    history.add(video_id)
    _save_history(history)


def search_pexels(query: str, per_page: int = 15) -> list[dict]:
    """Pexels API로 영상을 검색한다."""
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
            }
            for v in videos
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
        for v in hits:
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


def collect_cat_clips(
    count: int = 3,
    min_duration: int = 15,
    max_duration: int = 60,
) -> list[Path]:
    """고양이 영상 클립을 수집하여 다운로드한다.

    Args:
        count: 수집할 클립 수
        min_duration: 최소 길이(초)
        max_duration: 최대 길이(초)

    Returns:
        다운로드된 영상 파일 경로 리스트
    """
    history = _load_history()
    output_dir = VIDEO_DIR / "cats"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 랜덤 키워드로 검색
    queries = random.sample(CAT_QUERIES, min(len(CAT_QUERIES), count * 3))
    all_videos = []

    for q in queries:
        results = search_pexels(q)
        results += search_pixabay(q)
        all_videos.extend(results)

        if len(all_videos) >= count * 5:
            break

    # 필터링: 적절한 길이 + 미사용
    candidates = [
        v for v in all_videos
        if min_duration <= v["duration"] <= max_duration
        and v["id"] not in history
    ]

    # 셔플해서 다양성 확보
    random.shuffle(candidates)

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
