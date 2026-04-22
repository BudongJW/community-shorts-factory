"""Cat Facts 쇼츠 합성기 (education 서브니치).

기존 고양이 클립 위에:
  - 영문 TTS 나레이션 (Edge TTS)
  - SRT 기반 번인 자막 (subtitles 필터)
  - 낮은 볼륨 lofi BGM (나레이션 명료도 우선)
을 얹어 Education 카테고리 진입용 쇼츠 생성.
"""

import shutil
import subprocess
from pathlib import Path

import imageio_ffmpeg

from config.settings import SHORTS_WIDTH, SHORTS_HEIGHT, SHORTS_FPS, FINAL_DIR
from src.audio.lofi_music import pick_random_track
from src.editor.cat_composer import _find_best_start_offset, _get_video_info
from src.editor.hook_overlay import (
    ffmpeg_drawtext_filter,
    pick_hook_position,
)
from src.utils.logger import setup_logger

log = setup_logger("cat_facts_composer")

FFMPEG_BIN = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()


def _escape_subtitles_path(p: Path) -> str:
    """subtitles 필터는 Windows 드라이브 콜론을 이스케이프해야 함."""
    s = str(p).replace("\\", "/")
    return s.replace(":", "\\:")


def compose_cat_facts_short(
    video_path: Path,
    narration_audio: Path,
    narration_srt: Path,
    hook_text: str,
    output_name: str = "cat_facts",
    narration_volume: float = 1.2,
    bgm_volume: float = 0.2,
    max_duration: float = 55.0,
) -> Path:
    """고양이 영상 + 영문 나레이션 + 자막 합성.

    나레이션 길이가 영상 길이 기준이 된다. 영상이 짧으면 loop로 늘리고,
    길면 나레이션 끝 시점에서 자연스럽게 종료.
    """
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    output_path = FINAL_DIR / f"{output_name}.mp4"

    info = _get_video_info(video_path)
    log.info(f"  clip: {info['width']}x{info['height']}, {info['duration']:.1f}s")

    # 나레이션 길이 계측
    aud_info = _get_video_info(narration_audio)
    narration_sec = aud_info["duration"] or 20.0
    final_sec = min(max_duration, narration_sec + 0.5)  # 끝부분 여유 0.5s
    log.info(f"  narration: {narration_sec:.1f}s -> final {final_sec:.1f}s")

    # 썸네일 오프셋
    start_offset = _find_best_start_offset(video_path, info["duration"])
    if start_offset > 0 and info["duration"] - start_offset < final_sec:
        # 오프셋 적용 시 남은 영상이 부족하면 오프셋 포기.
        start_offset = 0.0

    bgm_path = pick_random_track()
    if bgm_path:
        log.info(f"  bgm: {bgm_path.name}")

    vf_parts = [
        f"scale={SHORTS_WIDTH}:{SHORTS_HEIGHT}:force_original_aspect_ratio=increase",
        f"crop={SHORTS_WIDTH}:{SHORTS_HEIGHT}",
        f"fps={SHORTS_FPS}",
    ]

    # 훅 오버레이 (첫 1.2초)
    if hook_text:
        pos_name, y_ratio = pick_hook_position()
        log.info(f"  hook: {hook_text} @ {pos_name}")
        vf_parts.append(
            ffmpeg_drawtext_filter(hook_text, video_h=SHORTS_HEIGHT, y_ratio=y_ratio)
        )

    # SRT 자막 번인 — 가운데 하단, 큰 폰트, 외곽선 검정.
    # Windows 경로 대응 위해 escape 처리.
    srt_escaped = _escape_subtitles_path(narration_srt)
    subtitle_style = (
        "Fontname=Arial,Fontsize=18,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=0,"
        "Alignment=2,MarginV=60"
    )
    vf_parts.append(f"subtitles='{srt_escaped}':force_style='{subtitle_style}'")

    vf = ",".join(vf_parts)

    cmd = [FFMPEG_BIN, "-y"]
    if start_offset > 0:
        cmd += ["-ss", str(start_offset)]
    # 영상이 나레이션보다 짧으면 stream_loop로 루핑.
    if info["duration"] and info["duration"] < final_sec + start_offset:
        cmd += ["-stream_loop", "-1"]
    cmd += ["-i", str(video_path)]

    # 나레이션 오디오
    cmd += ["-i", str(narration_audio)]

    # BGM (옵션)
    if bgm_path:
        cmd += ["-i", str(bgm_path)]

    cmd += ["-vf", vf]

    # 오디오 믹스: 나레이션(1) + BGM(2). 원본 영상 오디오는 무시 (야옹·배경소음 TTS 방해).
    if bgm_path:
        # narration 강, bgm 약. afade는 전체 영상 길이 기준.
        fade_out_start = max(0.5, final_sec - 1.5)
        cmd += [
            "-filter_complex",
            (
                f"[1:a]volume={narration_volume},apad[a1];"
                f"[2:a]volume={bgm_volume},aloop=loop=-1:size=2e9,"
                f"afade=t=out:st={fade_out_start}:d=1.5[a2];"
                f"[a1][a2]amix=inputs=2:duration=first:dropout_transition=0[aout]"
            ),
            "-map", "0:v:0",
            "-map", "[aout]",
        ]
    else:
        cmd += [
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-af", f"volume={narration_volume}",
        ]

    cmd += [
        "-t", str(final_sec),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path),
    ]

    log.info(f"  composing {final_sec:.0f}s facts video...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error(f"FFmpeg error: {result.stderr[-800:]}")
        raise subprocess.CalledProcessError(result.returncode, cmd)

    size_kb = output_path.stat().st_size // 1024
    log.info(f"  -> {output_path.name} ({size_kb}KB)")
    return output_path
