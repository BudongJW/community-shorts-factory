"""이미지 ���반 쇼츠 영상 합성기.

게시글의 이미지를 순차적으로 보여주는 슬라이드쇼 영상을 생성한다.
세로(1080x1920) 화면에 이미지를 맞추고, 상단에 제목, 하단에 출처를 표시한다.
"""

import subprocess
import tempfile
from pathlib import Path

import numpy as np
import imageio_ffmpeg

from PIL import Image, ImageDraw, ImageFont

from config.settings import SHORTS_WIDTH, SHORTS_HEIGHT, SHORTS_FPS, FINAL_DIR
from src.editor.chat_renderer import (
    _find_font, _draw_rounded_rect, _wrap_text,
    BG_COLOR, HEADER_ACCENT, TEXT_WHITE, TEXT_GRAY, FOOTER_BG,
)
from src.editor.chat_composer import (
    FFMPEG_BIN, SAMPLE_RATE, DEFAULT_BGM,
    _load_wav, _save_wav,
)
from src.utils.logger import setup_logger

log = setup_logger("image_composer")

FONT_BOLD = _find_font(bold=True)
FONT_REGULAR = _find_font(bold=False)


def _fit_image(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    """이미지를 max_w x max_h 안에 맞춘다 (비율 ��지)."""
    w, h = img.size
    ratio = min(max_w / w, max_h / h)
    new_w = int(w * ratio)
    new_h = int(h * ratio)
    return img.resize((new_w, new_h), Image.LANCZOS)


def _render_image_frame(
    image: Image.Image,
    title: str = "",
    page_text: str = "",
) -> Image.Image:
    """하나의 이미지를 쇼츠 프레임에 배치한다."""
    frame = Image.new("RGB", (SHORTS_WIDTH, SHORTS_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(frame)

    # 상단 제목 영역 (120px)
    title_h = 120
    if title:
        title_font = ImageFont.truetype(FONT_BOLD, 36)
        lines = _wrap_text(title, title_font, SHORTS_WIDTH - 80)
        y = 30
        for line in lines[:2]:  # 최대 2줄
            draw.text((40, y), line, fill=TEXT_WHITE, font=title_font)
            y += 48

    # 하단 페이지 표시 영역 (80px)
    footer_h = 80
    if page_text:
        page_font = ImageFont.truetype(FONT_REGULAR, 28)
        bbox = page_font.getbbox(page_text)
        pw = bbox[2] - bbox[0]
        draw.text(
            ((SHORTS_WIDTH - pw) // 2, SHORTS_HEIGHT - footer_h + 20),
            page_text, fill=TEXT_GRAY, font=page_font,
        )

    # 이미지 배치 (중앙)
    available_h = SHORTS_HEIGHT - title_h - footer_h
    fitted = _fit_image(image, SHORTS_WIDTH - 40, available_h - 40)
    fx = (SHORTS_WIDTH - fitted.size[0]) // 2
    fy = title_h + (available_h - fitted.size[1]) // 2
    frame.paste(fitted, (fx, fy))

    return frame


def compose_image_slideshow(
    image_paths: list[Path],
    title: str = "",
    output_name: str = "image_short",
    fps: int = SHORTS_FPS,
    sec_per_image: float = 3.0,
    bgm_volume: float = 0.2,
) -> Path:
    """이미지 리스트를 슬라이드쇼 영상으로 합성한다.

    Args:
        image_paths: 이미지 파일 경로 리스트
        title: 영상 상단 제목
        output_name: 출력 파일명
        fps: 프레임 레이트
        sec_per_image: 이미지당 표시 시간
        bgm_volume: BGM 볼륨

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
    total_frames = int(total_sec * fps)
    frames_per_image = int(sec_per_image * fps)

    log.info(f"  [slideshow] {len(image_paths)} images, {total_sec:.0f}s")

    # 오디오 (BGM만)
    total_samples = int(total_sec * SAMPLE_RATE)
    audio_mix = np.zeros(total_samples, dtype=np.float64)

    if DEFAULT_BGM.exists():
        bgm = _load_wav(DEFAULT_BGM)
        if len(bgm) < total_samples:
            bgm = np.tile(bgm, (total_samples // len(bgm)) + 1)
        bgm = bgm[:total_samples]
        fade = int(SAMPLE_RATE * 1.5)
        if fade > 0 and len(bgm) > fade * 2:
            bgm[:fade] *= np.linspace(0, 1, fade)
            bgm[-fade:] *= np.linspace(1, 0, fade)
        audio_mix += bgm * bgm_volume

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # 프레임 렌더링
        frame_idx = 0
        for img_i, img_path in enumerate(image_paths):
            try:
                pil_img = Image.open(img_path).convert("RGB")
            except Exception:
                continue

            page_text = f"{img_i + 1} / {len(image_paths)}"
            rendered = _render_image_frame(pil_img, title=title, page_text=page_text)

            for _ in range(frames_per_image):
                rendered.save(tmpdir_path / f"frame_{frame_idx:06d}.png")
                frame_idx += 1

        if frame_idx == 0:
            raise ValueError("렌더링된 프레임이 없습니다")

        # 오디오 저장
        audio_path = tmpdir_path / "audio_mix.wav"
        _save_wav(audio_path, audio_mix)

        # FFmpeg
        input_pattern = str(tmpdir_path / "frame_%06d.png").replace("\\", "/")
        cmd = [
            FFMPEG_BIN, "-y",
            "-framerate", str(fps),
            "-i", input_pattern,
            "-i", str(audio_path),
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

    log.info(f"  [slideshow] -> {output_path.name} ({output_path.stat().st_size // 1024}KB)")
    return output_path
