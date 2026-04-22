"""AI 생성 고양이 애니메이션 영상 합성기.

AI 이미지 시퀀스에 Ken Burns 효과(줌/팬)를 적용하고
lofi jazz BGM을 얹어 Shorts 영상을 생성한다.
"""

import random
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

import imageio_ffmpeg

from config.settings import SHORTS_WIDTH, SHORTS_HEIGHT, SHORTS_FPS, FINAL_DIR
from src.audio.lofi_music import pick_random_track
from src.editor.hook_overlay import (
    HOOK_DURATION,
    pick_hook,
    pick_hook_position,
    pil_draw_hook,
)
from src.utils.logger import setup_logger

log = setup_logger("anime_cat_composer")

# anime 경로는 훅을 PIL로 pre-render하므로 drawtext 불필요. 통일성을 위해 동일 규칙 적용.
FFMPEG_BIN = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()


def _ken_burns_frame(
    img: Image.Image,
    progress: float,
    effect: str = "zoom_in",
) -> Image.Image:
    """Ken Burns 효과가 적용된 프레임을 생성한다.

    Args:
        img: 원본 이미지 (1080x1920)
        progress: 0.0~1.0 (장면 내 진행도)
        effect: 효과 종류

    Returns:
        크롭/줌된 프레임 (1080x1920)
    """
    w, h = img.size

    if effect == "zoom_in":
        # 1.0x -> 1.15x 줌인
        scale = 1.0 + 0.15 * progress
        new_w = int(w / scale)
        new_h = int(h / scale)
        left = (w - new_w) // 2
        top = (h - new_h) // 2
        cropped = img.crop((left, top, left + new_w, top + new_h))
        return cropped.resize((SHORTS_WIDTH, SHORTS_HEIGHT), Image.LANCZOS)

    elif effect == "zoom_out":
        # 1.15x -> 1.0x 줌아웃
        scale = 1.15 - 0.15 * progress
        new_w = int(w / scale)
        new_h = int(h / scale)
        left = (w - new_w) // 2
        top = (h - new_h) // 2
        cropped = img.crop((left, top, left + new_w, top + new_h))
        return cropped.resize((SHORTS_WIDTH, SHORTS_HEIGHT), Image.LANCZOS)

    elif effect == "pan_up":
        # 하단 -> 상단으로 팬
        scale = 1.15
        new_w = int(w / scale)
        new_h = int(h / scale)
        left = (w - new_w) // 2
        max_top = h - new_h
        top = int(max_top * (1.0 - progress))
        cropped = img.crop((left, top, left + new_w, top + new_h))
        return cropped.resize((SHORTS_WIDTH, SHORTS_HEIGHT), Image.LANCZOS)

    elif effect == "pan_down":
        # 상단 -> 하단으로 팬
        scale = 1.15
        new_w = int(w / scale)
        new_h = int(h / scale)
        left = (w - new_w) // 2
        max_top = h - new_h
        top = int(max_top * progress)
        cropped = img.crop((left, top, left + new_w, top + new_h))
        return cropped.resize((SHORTS_WIDTH, SHORTS_HEIGHT), Image.LANCZOS)

    # 기본: 정적
    return img.resize((SHORTS_WIDTH, SHORTS_HEIGHT), Image.LANCZOS)


def compose_anime_cat(
    image_paths: list[Path],
    output_name: str = "anime_cat",
    sec_per_image: float = 5.0,
    bgm_volume: float = 0.7,
    transition_frames: int = 8,
    hook: str | None = None,
) -> Path:
    """AI 고양이 이미지 시퀀스를 영상으로 합성한다.

    Args:
        image_paths: AI 생성 이미지 경로 리스트
        output_name: 출력 파일명
        sec_per_image: 이미지당 표시 시간(초)
        bgm_volume: BGM 볼륨
        transition_frames: 장면 전환 페이드 프레임 수
        hook: 첫 1초 훅 오버레이 텍스트. None이면 랜덤 선택, ""면 비활성.

    Returns:
        최종 영상 파일 경로
    """
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    output_path = FINAL_DIR / f"{output_name}.mp4"

    if not image_paths:
        raise ValueError("이미지가 없습니다")

    # 55초 제한
    max_images = int(55 / sec_per_image)
    image_paths = image_paths[:max_images]
    total_sec = len(image_paths) * sec_per_image
    fps = SHORTS_FPS
    frames_per_image = int(sec_per_image * fps)

    log.info(f"  {len(image_paths)} scenes, {total_sec:.0f}s total")

    # Ken Burns 효과 가중 랜덤 — 단조로운 순차 적용 회피.
    # zoom_in이 가장 몰입감 높음 (시청자가 당겨지는 느낌). zoom_out은 이탈률 높아 비중 낮춤.
    # 같은 영상 내 연속으로 같은 효과 금지 — 2개 이상 장면이면 직전과 다른 효과 뽑음.
    effect_pool = ["zoom_in", "zoom_in", "zoom_in", "pan_up", "pan_down", "zoom_out"]
    effect_seq: list[str] = []
    for _ in range(len(image_paths)):
        choices = [e for e in effect_pool if not effect_seq or e != effect_seq[-1]]
        effect_seq.append(random.choice(choices))

    # BGM
    bgm_path = pick_random_track()
    if bgm_path:
        log.info(f"  bgm: {bgm_path.name}")

    # 훅 오버레이 (첫 HOOK_DURATION 초만 표시)
    if hook is None:
        hook = pick_hook()
    hook_y_ratio = 0.18
    if hook:
        pos_name, hook_y_ratio = pick_hook_position()
        log.info(f"  hook: {hook} @ {pos_name}")
    hook_end_frame = int(HOOK_DURATION * fps)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        frame_idx = 0

        for img_i, img_path in enumerate(image_paths):
            try:
                pil_img = Image.open(img_path).convert("RGB")
                # 이미지가 정확한 크기가 아니면 리사이즈
                if pil_img.size != (SHORTS_WIDTH, SHORTS_HEIGHT):
                    pil_img = pil_img.resize(
                        (SHORTS_WIDTH, SHORTS_HEIGHT), Image.LANCZOS
                    )
            except Exception as e:
                log.warning(f"  image load failed: {e}")
                continue

            effect = effect_seq[img_i]

            for f in range(frames_per_image):
                progress = f / max(frames_per_image - 1, 1)
                frame = _ken_burns_frame(pil_img, progress, effect)

                # 장면 전환 페이드 인/아웃
                if f < transition_frames and img_i > 0:
                    # 페이드 인
                    alpha = f / transition_frames
                    dark = Image.new("RGB", frame.size, (0, 0, 0))
                    frame = Image.blend(dark, frame, alpha)
                elif f >= frames_per_image - transition_frames and img_i < len(image_paths) - 1:
                    # 페이드 아웃
                    alpha = (frames_per_image - f) / transition_frames
                    dark = Image.new("RGB", frame.size, (0, 0, 0))
                    frame = Image.blend(dark, frame, alpha)

                # 첫 HOOK_DURATION 초 훅 오버레이
                if hook and frame_idx < hook_end_frame:
                    progress = frame_idx / hook_end_frame
                    frame = pil_draw_hook(frame, hook, progress, y_ratio=hook_y_ratio)

                frame.save(tmpdir_path / f"frame_{frame_idx:06d}.png")
                frame_idx += 1

        if frame_idx == 0:
            raise ValueError("렌더링된 프레임이 없습니다")

        log.info(f"  {frame_idx} frames rendered")

        # FFmpeg: 프레임 + BGM -> MP4
        input_pattern = str(tmpdir_path / "frame_%06d.png").replace("\\", "/")
        cmd = [FFMPEG_BIN, "-y", "-framerate", str(fps), "-i", input_pattern]

        if bgm_path:
            cmd += ["-i", str(bgm_path)]
            cmd += [
                "-map", "0:v:0", "-map", "1:a:0",
                "-af", f"volume={bgm_volume},afade=t=in:d=1.5,afade=t=out:st={total_sec - 2}:d=2",
            ]
        else:
            cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono"]
            cmd += ["-map", "0:v:0", "-map", "1:a:0"]

        cmd += [
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(output_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log.error(f"FFmpeg error: {result.stderr[-500:]}")
            raise subprocess.CalledProcessError(result.returncode, cmd)

    size_kb = output_path.stat().st_size // 1024
    log.info(f"  -> {output_path.name} ({size_kb}KB)")
    return output_path
