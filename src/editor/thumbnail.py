"""채팅 쇼츠용 썸네일 자동 생성기.

핵심 프레임에서 큰 텍스트 오버레이를 추가하여 CTR을 높인다.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config.settings import SHORTS_WIDTH, SHORTS_HEIGHT, FINAL_DIR
from src.editor.chat_renderer import (
    _get_fonts, _draw_rounded_rect,
    BG_COLOR, HEADER_ACCENT, TEXT_WHITE, RESULT_ACCENT,
)

# 썸네일 전용 폰트 크기
FONT_BOLD_PATH = None  # _find_font에서 결정

def _get_bold_font_path() -> str:
    from src.editor.chat_renderer import FONT_BOLD
    return FONT_BOLD


def generate_thumbnail(
    title: str,
    result_text: str = "",
    output_name: str = "thumbnail",
    background_frame: Image.Image | None = None,
) -> Path:
    """쇼츠 썸네일을 생성한다.

    Args:
        title: 영상 제목
        result_text: 결과 텍스트 (있으면 강조 표시)
        output_name: 출력 파일명
        background_frame: 배경으로 사용할 프레임 (없으면 단색 배경)

    Returns:
        썸네일 파일 경로
    """
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    output_path = FINAL_DIR / f"{output_name}_thumb.png"

    bold_path = _get_bold_font_path()

    if background_frame:
        img = background_frame.copy()
        # 반투명 오버레이
        overlay = Image.new("RGBA", (SHORTS_WIDTH, SHORTS_HEIGHT), (0, 0, 0, 160))
        img = img.convert("RGBA")
        img = Image.alpha_composite(img, overlay)
        img = img.convert("RGB")
    else:
        img = Image.new("RGB", (SHORTS_WIDTH, SHORTS_HEIGHT), BG_COLOR)

    draw = ImageDraw.Draw(img)

    # 제목 (큰 폰트, 중앙)
    title_font = ImageFont.truetype(bold_path, 64)
    # 줄바꿈 처리
    lines = _wrap_title(title, title_font, SHORTS_WIDTH - 120)

    total_text_h = len(lines) * 80
    y_start = (SHORTS_HEIGHT - total_text_h) // 2 - 50

    for i, line in enumerate(lines):
        bbox = title_font.getbbox(line)
        w = bbox[2] - bbox[0]
        x = (SHORTS_WIDTH - w) // 2
        y = y_start + i * 80

        # 텍스트 그림자
        draw.text((x + 3, y + 3), line, fill=(0, 0, 0), font=title_font)
        draw.text((x, y), line, fill=TEXT_WHITE, font=title_font)

    # 결과 텍스트 (하단, 노란색 배경 태그)
    if result_text:
        result_font = ImageFont.truetype(bold_path, 48)
        rbbox = result_font.getbbox(result_text)
        rw = rbbox[2] - rbbox[0] + 48
        rh = rbbox[3] - rbbox[1] + 24
        rx = (SHORTS_WIDTH - rw) // 2
        ry = y_start + total_text_h + 40

        _draw_rounded_rect(draw, (rx, ry, rx + rw, ry + rh), rh // 2, HEADER_ACCENT)
        draw.text(
            (rx + 24, ry + 8),
            result_text,
            fill=TEXT_WHITE,
            font=result_font,
        )

    # 상단 카테고리 태그
    cat_font = ImageFont.truetype(bold_path, 32)
    cat_text = "커뮤니티 썰"
    cbbox = cat_font.getbbox(cat_text)
    cw = cbbox[2] - cbbox[0] + 32
    ch = cbbox[3] - cbbox[1] + 16
    cx = (SHORTS_WIDTH - cw) // 2
    cy = y_start - 80

    _draw_rounded_rect(draw, (cx, cy, cx + cw, cy + ch), ch // 2, HEADER_ACCENT)
    draw.text((cx + 16, cy + 6), cat_text, fill=TEXT_WHITE, font=cat_font)

    img.save(output_path)
    return output_path


def _wrap_title(text: str, font, max_width: int) -> list[str]:
    """제목을 max_width에 맞게 줄바꿈한다."""
    lines = []
    current = ""
    for ch in text:
        test = current + ch
        bbox = font.getbbox(test)
        w = bbox[2] - bbox[0]
        if w > max_width and current:
            lines.append(current)
            current = ch
        else:
            current = test
    if current:
        lines.append(current)
    return lines
