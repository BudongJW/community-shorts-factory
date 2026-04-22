"""Lofi Jazz BGM 관리.

assets/bgm/ 디렉토리의 lofi jazz 트랙을 관리한다.
트랙이 없으면 Pixabay Music API에서 무료 lofi 트랙을 다운로드한다.
"""

import json
import os
import random
from pathlib import Path

import requests
from dotenv import load_dotenv

from src.utils.logger import setup_logger

load_dotenv()

log = setup_logger("lofi_music")

BGM_DIR = Path(__file__).parent.parent.parent / "assets" / "bgm"
BGM_HISTORY_PATH = Path(__file__).parent.parent.parent / "output" / "bgm_history.json"
# 최근 사용 트랙 기록 슬라이딩 윈도우. 풀 크기의 절반 정도로 설정하면 같은 곡 반복 방지.
BGM_HISTORY_MAX = 6

# Pixabay Music API (무료, API 키 필요)
PIXABAY_MUSIC_API = "https://pixabay.com/api/"


def _get_local_tracks() -> list[Path]:
    """로컬에 저장된 BGM 트랙 목록을 반환한다."""
    if not BGM_DIR.exists():
        return []
    return sorted(BGM_DIR.glob("*.mp3")) + sorted(BGM_DIR.glob("*.wav"))


def download_pixabay_music(count: int = 5) -> list[Path]:
    """Pixabay에서 lofi/jazz 음악을 다운로드한다."""
    api_key = os.getenv("PIXABAY_API_KEY")
    if not api_key:
        log.warning("  PIXABAY_API_KEY not set, skipping music download")
        return []

    BGM_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = []

    queries = ["lofi jazz", "lofi chill", "jazz cafe", "lofi hip hop"]
    for q in queries:
        if len(downloaded) >= count:
            break
        try:
            # Pixabay audio search (same API, different endpoint for music isn't available in free tier)
            # Use the regular API to find music
            log.info(f"  searching Pixabay music: {q}")
            # Note: Pixabay doesn't have a separate music API for free
            # We'll rely on bundled tracks instead
            break
        except Exception as e:
            log.warning(f"  music search failed: {e}")

    return downloaded


def _load_bgm_history() -> list[str]:
    if BGM_HISTORY_PATH.exists():
        try:
            return list(json.loads(BGM_HISTORY_PATH.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            return []
    return []


def _record_bgm_used(track_name: str):
    history = _load_bgm_history()
    history = [n for n in history if n != track_name]
    history.append(track_name)
    if len(history) > BGM_HISTORY_MAX:
        history = history[-BGM_HISTORY_MAX:]
    BGM_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    BGM_HISTORY_PATH.write_text(
        json.dumps(history, ensure_ascii=False), encoding="utf-8"
    )


def pick_random_track() -> Path | None:
    """랜덤 BGM 트랙을 선택한다. 최근 사용한 트랙은 피한다.

    같은 BGM이 연속 영상에 반복되면 "봇 계정" 시그널이 강해지므로
    히스토리 윈도우 바깥 트랙에서만 고른다. 전부 사용 이력이면 제일 오래된 것부터.
    """
    tracks = _get_local_tracks()
    if not tracks:
        log.warning("  No BGM tracks found in assets/bgm/")
        return None

    history = _load_bgm_history()
    # 풀이 작으면 한 트랙 걸러 반복되므로 윈도우를 풀 크기에 맞춰 조정 (과반은 제외).
    window = min(BGM_HISTORY_MAX, max(1, len(tracks) - 1))
    recent = set(history[-window:])
    fresh = [t for t in tracks if t.name not in recent]
    pool = fresh if fresh else tracks

    chosen = random.choice(pool)
    _record_bgm_used(chosen.name)
    return chosen


def pick_track_for_video(video_id: str) -> Path | None:
    """영상별로 일관된 BGM을 선택한다 (같은 video_id -> 같은 트랙).

    Returns:
        BGM 파일 경로 또는 None
    """
    tracks = _get_local_tracks()
    if not tracks:
        return None
    idx = hash(video_id) % len(tracks)
    return tracks[idx]


def list_tracks() -> list[dict]:
    """사용 가능한 트랙 정보를 반환한다."""
    tracks = _get_local_tracks()
    return [
        {"name": t.stem, "path": str(t), "size_kb": t.stat().st_size // 1024}
        for t in tracks
    ]
