"""고양이 쇼츠 합성기.

고양이 영상 클립을 세로(1080x1920)로 크롭하고,
lofi jazz BGM을 얹어 YouTube Shorts를 생성한다.
"""

import shutil
import subprocess
from pathlib import Path

import imageio_ffmpeg

from config.settings import SHORTS_WIDTH, SHORTS_HEIGHT, SHORTS_FPS, FINAL_DIR
from src.audio.lofi_music import pick_random_track
from src.editor.hook_overlay import (
    ffmpeg_drawtext_filter,
    ffmpeg_midcap_filter,
    pick_hook,
    pick_hook_position,
    pick_midcap,
    pick_midcap_time,
)
from src.utils.logger import setup_logger

log = setup_logger("cat_composer")

# 시스템 ffmpeg 우선. imageio_ffmpeg의 Linux 번들은 drawtext 필터 미포함 최소 빌드라
# 훅 오버레이가 CI에서 실패한다. ubuntu-latest는 ffmpeg 사전 설치되어 있음.
FFMPEG_BIN = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()
MAX_DURATION = 55  # Shorts 60초 제한에 여유


def _get_video_info(video_path: Path) -> dict:
    """FFprobe로 영상 정보를 가져온다."""
    cmd = [
        FFMPEG_BIN, "-i", str(video_path),
        "-hide_banner",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    stderr = result.stderr

    info = {"duration": 0, "width": 0, "height": 0, "has_audio": False}

    # Duration 파싱
    import re
    dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+)\.(\d+)", stderr)
    if dur_match:
        h, m, s, ms = dur_match.groups()
        info["duration"] = int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 100

    # 해상도 파싱
    res_match = re.search(r"(\d{2,5})x(\d{2,5})", stderr)
    if res_match:
        info["width"] = int(res_match.group(1))
        info["height"] = int(res_match.group(2))

    # 오디오 스트림 확인
    if "Audio:" in stderr:
        info["has_audio"] = True

    return info


def compose_cat_short(
    video_path: Path,
    output_name: str = "cat_short",
    bgm_volume: float = 0.7,
    caption: str = "",
    hook: str | None = None,
) -> Path:
    """고양이 영상을 Shorts 포맷으로 합성한다.

    Args:
        video_path: 원본 고양이 영상 경로
        output_name: 출력 파일명
        bgm_volume: BGM 볼륨 (0.0~1.0)
        caption: 상단/하단 캡션 텍스트 (옵션)
        hook: 첫 1초 훅 오버레이 텍스트. None이면 랜덤 선택, ""면 비활성.

    Returns:
        최종 영상 파일 경로
    """
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    output_path = FINAL_DIR / f"{output_name}.mp4"

    info = _get_video_info(video_path)
    log.info(f"  input: {info['width']}x{info['height']}, {info['duration']:.1f}s")

    # BGM 선택
    bgm_path = pick_random_track()
    if bgm_path:
        log.info(f"  bgm: {bgm_path.name}")

    # 영상 길이 제한
    duration = min(info["duration"], MAX_DURATION)
    if duration < 3:
        duration = MAX_DURATION  # 길이 파싱 실패 시 기본값

    # 비디오 필터: 세로 크롭 + 스케일
    # 가로 영상이면 중앙 크롭, 세로 영상이면 스케일만
    vf_parts = [
        f"scale={SHORTS_WIDTH}:{SHORTS_HEIGHT}:force_original_aspect_ratio=increase",
        f"crop={SHORTS_WIDTH}:{SHORTS_HEIGHT}",
        f"fps={SHORTS_FPS}",
    ]

    # 캡션이 있으면 자막 추가 (drawtext)
    if caption:
        # 특수문자 이스케이프
        safe_caption = caption.replace("'", "'\\''").replace(":", "\\:")
        vf_parts.append(
            f"drawtext=text='{safe_caption}'"
            f":fontsize=48:fontcolor=white"
            f":borderw=3:bordercolor=black"
            f":x=(w-text_w)/2:y=h-120"
        )

    # 첫 1초 훅 오버레이 (hook="" 이면 비활성화)
    if hook is None:
        hook = pick_hook()
    if hook:
        pos_name, y_ratio = pick_hook_position()
        log.info(f"  hook: {hook} @ {pos_name}")
        vf_parts.append(ffmpeg_drawtext_filter(hook, video_h=SHORTS_HEIGHT, y_ratio=y_ratio))

    # 2차 훅(midcap) — 5~8초 구간 리텐션 방어.
    # 훅 비활성화(hook="")면 midcap도 생략 — 전체 오버레이 off 용도 보존.
    if hook and duration > 4:
        midcap = pick_midcap()
        midcap_start = pick_midcap_time(duration)
        log.info(f"  midcap: {midcap} @ {midcap_start:.1f}s")
        vf_parts.append(
            ffmpeg_midcap_filter(midcap, midcap_start, video_h=SHORTS_HEIGHT)
        )

    vf = ",".join(vf_parts)

    # FFmpeg 명령 구성
    cmd = [FFMPEG_BIN, "-y"]

    # 입력 1: 비디오
    cmd += ["-i", str(video_path)]

    # 입력 2: BGM (있으면)
    if bgm_path:
        cmd += ["-i", str(bgm_path)]

    # 비디오 필터
    cmd += ["-vf", vf]

    # 오디오 처리
    if bgm_path:
        if info["has_audio"]:
            # 원본 오디오 제거하고 BGM만 사용
            cmd += [
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-af", f"volume={bgm_volume},afade=t=in:d=1,afade=t=out:st={duration - 2}:d=2",
            ]
        else:
            # 오디오 없으면 BGM만
            cmd += [
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-af", f"volume={bgm_volume},afade=t=in:d=1,afade=t=out:st={duration - 2}:d=2",
            ]
    else:
        # BGM도 없으면 무음
        cmd += [
            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono",
            "-map", "0:v:0",
            "-map", "1:a:0",
        ]

    # 출력 설정
    cmd += [
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(output_path),
    ]

    log.info(f"  composing {duration:.0f}s video...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error(f"FFmpeg error: {result.stderr[-500:]}")
        raise subprocess.CalledProcessError(result.returncode, cmd)

    size_kb = output_path.stat().st_size // 1024
    log.info(f"  -> {output_path.name} ({size_kb}KB)")
    return output_path


def compose_multi_clip(
    video_paths: list[Path],
    output_name: str = "cat_short",
    bgm_volume: float = 0.7,
    max_duration: int = MAX_DURATION,
) -> Path:
    """여러 고양이 클립을 이어붙여 하나의 Shorts를 만든다.

    Args:
        video_paths: 영상 클립 리스트
        output_name: 출력 파일명
        bgm_volume: BGM 볼륨
        max_duration: 최대 길이(초)

    Returns:
        최종 영상 파일 경로
    """
    if len(video_paths) == 1:
        return compose_cat_short(video_paths[0], output_name, bgm_volume)

    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    output_path = FINAL_DIR / f"{output_name}.mp4"

    bgm_path = pick_random_track()
    if bgm_path:
        log.info(f"  bgm: {bgm_path.name}")

    # 각 클립을 세로로 변환 후 concat
    # 1) 먼저 각 클립을 통일된 포맷으로 변환
    temp_clips = []
    for i, vp in enumerate(video_paths):
        temp_path = FINAL_DIR / f"_temp_clip_{i}.mp4"
        vf = (
            f"scale={SHORTS_WIDTH}:{SHORTS_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={SHORTS_WIDTH}:{SHORTS_HEIGHT},"
            f"fps={SHORTS_FPS}"
        )
        cmd = [
            FFMPEG_BIN, "-y",
            "-i", str(vp),
            "-vf", vf,
            "-an",  # 오디오 제거
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-t", str(max_duration // len(video_paths)),
            str(temp_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            temp_clips.append(temp_path)

    if not temp_clips:
        raise ValueError("No clips could be processed")

    # 2) concat 리스트 생성
    concat_file = FINAL_DIR / f"_concat_{output_name}.txt"
    with open(concat_file, "w") as f:
        for tc in temp_clips:
            f.write(f"file '{tc.resolve()}'\n")

    # 3) concat + BGM
    cmd = [FFMPEG_BIN, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file)]

    if bgm_path:
        cmd += ["-i", str(bgm_path)]
        cmd += [
            "-map", "0:v:0", "-map", "1:a:0",
            "-af", f"volume={bgm_volume},afade=t=in:d=1,afade=t=out:st={max_duration - 2}:d=2",
        ]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono"]
        cmd += ["-map", "0:v:0", "-map", "1:a:0"]

    cmd += [
        "-t", str(max_duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    # 임시 파일 정리
    for tc in temp_clips:
        tc.unlink(missing_ok=True)
    concat_file.unlink(missing_ok=True)

    if result.returncode != 0:
        log.error(f"FFmpeg error: {result.stderr[-500:]}")
        raise subprocess.CalledProcessError(result.returncode, cmd)

    size_kb = output_path.stat().st_size // 1024
    log.info(f"  -> {output_path.name} ({size_kb}KB)")
    return output_path
