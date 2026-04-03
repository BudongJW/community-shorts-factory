"""FFmpeg 기반 영상 합성: 배경 영상 + 음성 + 자막 + BGM → 최종 Shorts."""

import subprocess
from pathlib import Path

import imageio_ffmpeg

from config.settings import FINAL_DIR, SHORTS_WIDTH, SHORTS_HEIGHT, SHORTS_MAX_DURATION

FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()

# 자막 스타일 (SRT force_style)
# - 큰 폰트, 흰색 텍스트 + 검정 외곽선 + 반투명 배경 박스
# - 하단 중앙 정렬, 줄간격 넓게
SUBTITLE_STYLE = (
    "FontName=Arial,"
    "FontSize=20,"
    "Bold=1,"
    "PrimaryColour=&H00FFFFFF,"      # 흰색 텍스트
    "OutlineColour=&H00000000,"      # 검정 외곽선
    "BackColour=&H80000000,"         # 반투명 검정 배경
    "Outline=2,"
    "Shadow=0,"
    "BorderStyle=4,"                 # 배경 박스 스타일
    "MarginV=60,"                    # 하단 여백 (세로 영상에서 자막 위치)
    "Alignment=2"                    # 하단 중앙
)


def compose(
    video_paths: list[Path],
    audio_path: Path,
    srt_path: Path,
    bgm_path: Path | None = None,
    output_name: str = "short",
) -> Path:
    """배경 영상 클립들과 음성, 자막, BGM을 합성하여 최종 Shorts를 생성한다.

    Args:
        video_paths: 배경 영상 파일 경로 리스트
        audio_path: 나레이션 MP3
        srt_path: SRT 자막
        bgm_path: BGM 파일 (없으면 나레이션만)
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

    # 2) 자막 경로 이스케이프 (FFmpeg subtitles 필터용)
    srt_escaped = str(srt_path.resolve()).replace("\\", "/").replace(":", "\\:")

    # 3) 비디오 필터 체인: 리사이즈 → 크롭 → 자막 번인
    vf = (
        f"scale={SHORTS_WIDTH}:{SHORTS_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={SHORTS_WIDTH}:{SHORTS_HEIGHT},"
        f"subtitles='{srt_escaped}':force_style='{SUBTITLE_STYLE}'"
    )

    # 4) 오디오 처리: BGM이 있으면 나레이션과 믹싱
    if bgm_path and bgm_path.exists():
        # 나레이션(원본 볼륨) + BGM(20% 볼륨)으로 믹싱
        cmd = [
            FFMPEG_BIN, "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-i", str(audio_path),
            "-i", str(bgm_path),
            "-vf", vf,
            "-filter_complex",
            "[1:a]volume=1.0[narr];[2:a]volume=0.2[bgm];[narr][bgm]amix=inputs=2:duration=shortest[aout]",
            "-map", "0:v:0", "-map", "[aout]",
            "-shortest",
            "-t", str(SHORTS_MAX_DURATION),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            str(output_path),
        ]
    else:
        cmd = [
            FFMPEG_BIN, "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-i", str(audio_path),
            "-vf", vf,
            "-map", "0:v:0", "-map", "1:a:0",
            "-shortest",
            "-t", str(SHORTS_MAX_DURATION),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            str(output_path),
        ]

    subprocess.run(cmd, check=True, capture_output=True, text=True)

    # 임시 concat 파일 정리
    concat_file.unlink(missing_ok=True)

    return output_path
