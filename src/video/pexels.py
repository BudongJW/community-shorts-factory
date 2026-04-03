"""Pexels API를 통한 무료 스톡 영상 다운로드."""

import os
import subprocess
from pathlib import Path

import requests
from dotenv import load_dotenv

import imageio_ffmpeg

from config.settings import VIDEO_DIR, SHORTS_WIDTH, SHORTS_HEIGHT

load_dotenv()

PEXELS_VIDEO_SEARCH = "https://api.pexels.com/videos/search"


def search_videos(query: str, per_page: int = 5, orientation: str = "portrait") -> list[dict]:
    """Pexels에서 영상을 검색한다.

    Args:
        query: 검색 키워드 (영어 권장)
        per_page: 결과 수
        orientation: portrait (세로, 쇼츠용) / landscape / square
    """
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        raise ValueError("PEXELS_API_KEY가 설정되지 않았습니다.")

    resp = requests.get(
        PEXELS_VIDEO_SEARCH,
        headers={"Authorization": api_key},
        params={"query": query, "per_page": per_page, "orientation": orientation},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("videos", [])


def download_video(video_data: dict, filename: str) -> Path:
    """Pexels 영상을 다운로드한다. HD 해상도 우선."""
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    # HD 파일 우선 선택
    files = video_data.get("video_files", [])
    hd = next((f for f in files if f.get("quality") == "hd"), files[0] if files else None)

    if not hd:
        raise ValueError("다운로드 가능한 영상 파일이 없습니다.")

    url = hd["link"]
    output_path = VIDEO_DIR / f"{filename}.mp4"

    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    return output_path


def generate_placeholder(filename: str = "placeholder", duration: int = 10) -> Path:
    """Pexels API 키가 없을 때 단색 배경 테스트 영상을 생성한다."""
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    output_path = VIDEO_DIR / f"{filename}.mp4"

    cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(), "-y",
        "-f", "lavfi",
        "-i", f"color=c=0x1a1a2e:s={SHORTS_WIDTH}x{SHORTS_HEIGHT}:d={duration}:r=30",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return output_path


def fetch_videos(keywords: list[str], per_keyword: int = 2) -> list[Path]:
    """여러 키워드로 영상을 검색하고 다운로드한다.
    Pexels API 키가 없으면 플레이스홀더 영상을 생성한다."""
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        print("  (PEXELS_API_KEY 미설정 — 플레이스홀더 영상 사용)")
        return [generate_placeholder("placeholder_0", duration=15)]

    paths = []
    for i, kw in enumerate(keywords):
        videos = search_videos(kw, per_page=per_keyword)
        for j, v in enumerate(videos):
            path = download_video(v, f"clip_{i}_{j}")
            paths.append(path)
    return paths
