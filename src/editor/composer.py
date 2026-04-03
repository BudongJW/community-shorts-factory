"""FFmpeg 기반 영상 합성: 배경 영상 + 음성 + 자막 → 최종 Shorts."""

import subprocess
from pathlib import Path

import imageio_ffmpeg

from config.settings import FINAL_DIR, SHORTS_WIDTH, SHORTS_HEIGHT, SHORTS_MAX_DURATION

FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()


def compose(
    video_paths: list[Path],
    audio_path: Path,
    srt_path: Path,
    output_name: str = "short",
) -> Path:
    """배경 영상 클립들과 음성, 자막을 합성하여 최종 Shorts를 생성한다.

    Args:
        video_paths: 배경 영상 파일 경로 리스트
        audio_path: 나레이션 MP3
        srt_path: SRT 자막
        output_name: 출력 파일명 (확장자 제외)

    Returns:
        최종 영상 파일 경로
    """
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    output_path = FINAL_DIR / f"{output_name}.mp4"

    # 1) 배경 영상 클립들을 연결하는 concat 리스트 생성
    concat_file = FINAL_DIR / f"{output_name}_concat.txt"
    with open(concat_file, "w", encoding="utf-8") as f:
        for vp in video_paths:
            f.write(f"file '{vp.resolve()}'\n")

    # 2) 영상 연결 → 세로 크롭/리사이즈 → 음성 합성 → 자막 번인
    srt_escaped = str(srt_path.resolve()).replace("\\", "/").replace(":", "\\:")

    cmd = [
        FFMPEG_BIN, "-y",
        # 연결된 배경 영상
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        # 나레이션 오디오
        "-i", str(audio_path),
        # 필터: 리사이즈 + 자막
        "-vf", (
            f"scale={SHORTS_WIDTH}:{SHORTS_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={SHORTS_WIDTH}:{SHORTS_HEIGHT},"
            f"subtitles='{srt_escaped}':force_style="
            f"'FontSize=14,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Alignment=2'"
        ),
        # 오디오는 나레이션으로 교체
        "-map", "0:v:0", "-map", "1:a:0",
        # 오디오 길이에 맞춰 종료
        "-shortest",
        "-t", str(SHORTS_MAX_DURATION),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        output_path,
    ]

    subprocess.run(cmd, check=True, capture_output=True, text=True)

    # 임시 concat 파일 정리
    concat_file.unlink(missing_ok=True)

    return output_path
