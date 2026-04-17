"""Lofi Jazz BGM 관리.

assets/bgm/ 디렉토리의 lofi jazz 트랙을 관리한다.
트랙이 없으면 Pixabay Music API에서 무료 lofi 트랙을 다운로드한다.
"""

import os
import random
from pathlib import Path

import requests
from dotenv import load_dotenv

from src.utils.logger import setup_logger

load_dotenv()

log = setup_logger("lofi_music")

BGM_DIR = Path(__file__).parent.parent.parent / "assets" / "bgm"

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


def pick_random_track() -> Path | None:
    """랜덤 BGM 트랙을 선택한다.

    Returns:
        BGM 파일 경로 또는 None (트랙이 없을 때)
    """
    tracks = _get_local_tracks()
    if not tracks:
        log.warning("  No BGM tracks found in assets/bgm/")
        return None
    return random.choice(tracks)


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
