"""Pillow 기반 채팅 UI 렌더러.

메신저 스타일 말풍선 프레임을 생성하여 '커뮤니티 썰' 쇼츠를 만든다.
각 메시지가 순차적으로 등장하는 프레임 시퀀스를 출력한다.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config.settings import SHORTS_WIDTH, SHORTS_HEIGHT, SHORTS_FPS

# ── 색상 팔레트 ──
BG_COLOR = (30, 33, 48)          # 다크 네이비 배경
HEADER_BG = (44, 48, 68)        # 헤더 영역
HEADER_ACCENT = (255, 70, 70)   # 빨간 액센트 (카테고리 태그)
BUBBLE_LEFT = (55, 60, 85)      # 상대방 말풍선 (회색-보라)
BUBBLE_RIGHT = (75, 80, 180)    # 나 말풍선 (파란색)
TEXT_WHITE = (255, 255, 255)
TEXT_GRAY = (180, 180, 195)
TEXT_DARK = (30, 33, 48)
FOOTER_BG = (38, 42, 60)        # 하단 결과 영역
RESULT_ACCENT = (255, 200, 50)  # 결과 강조색 (노란색)
TYPING_DOT = (150, 155, 175)    # 타이핑 인디케이터

# ── 레이아웃 상수 ──
PADDING = 40                     # 좌우 패딩
BUBBLE_MAX_W = int(SHORTS_WIDTH * 0.65)  # 말풍선 최대 너비
BUBBLE_RADIUS = 24               # 말풍선 둥근 모서리
BUBBLE_PAD_H = 24                # 말풍선 내부 좌우 패딩
BUBBLE_PAD_V = 18                # 말풍선 내부 상하 패딩
MSG_GAP = 20                     # 메시지 간 간격
AVATAR_SIZE = 44                 # 아바타 크기
IMG_BUBBLE_MAX_W = int(SHORTS_WIDTH * 0.55)  # 이미지 버블 최대 너비
IMG_BUBBLE_MAX_H = 360           # 이미지 버블 최대 높이
HEADER_HEIGHT = 200              # 헤더 높이
FOOTER_HEIGHT = 100              # 하단 결과 영역 높이
CHAT_AREA_TOP = HEADER_HEIGHT + 20
CHAT_AREA_BOTTOM = SHORTS_HEIGHT - FOOTER_HEIGHT - 20

# ── 폰트 경로 (크로스플랫폼) ──
import platform

def _find_font(bold: bool = False) -> str:
    """OS에 맞는 한글 폰트 경로를 반환한다."""
    if platform.system() == "Windows":
        return "C:/Windows/Fonts/malgunbd.ttf" if bold else "C:/Windows/Fonts/malgun.ttf"
    # Linux (GitHub Actions 등) - NanumGothic 사용
    if bold:
        candidates = [
            "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
            "/usr/share/fonts/nanum/NanumGothicBold.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            "/usr/share/fonts/nanum/NanumGothic.ttf",
        ]
    for c in candidates:
        if Path(c).exists():
            return c
    # fallback: 환경변수 또는 기본값
    import os
    return os.environ.get("FONT_BOLD" if bold else "FONT_REGULAR", candidates[0])

FONT_REGULAR = _find_font(bold=False)
FONT_BOLD = _find_font(bold=True)


@dataclass
class ChatMessage:
    """하나의 채팅 메시지."""
    sender: str         # 발신자 이름
    text: str           # 메시지 내용
    side: str = "left"  # "left" (상대방) 또는 "right" (나)
    emoji: str = ""     # 프로필 이모지 (텍스트로 대체)
    image_path: str = ""  # 이미지 경로 (카톡 사진 공유 스타일)


@dataclass
class ChatScript:
    """채팅 쇼츠 전체 대본."""
    category: str                       # "커뮤니티 썰" 등
    title: str                          # 제목
    subtitle: str = ""                  # 부제 (채널명 등)
    participants: list[str] = field(default_factory=list)
    messages: list[ChatMessage] = field(default_factory=list)
    result_text: str = ""               # 하단 결과 텍스트
    source: str = ""                    # 원본 출처


def load_chat_script(json_path: Path) -> ChatScript:
    """JSON 파일에서 채팅 대본을 로드한다."""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    messages = [ChatMessage(**m) for m in data.get("messages", [])]
    return ChatScript(
        category=data.get("category", ""),
        title=data.get("title", ""),
        subtitle=data.get("subtitle", ""),
        participants=data.get("participants", []),
        messages=messages,
        result_text=data.get("result_text", ""),
        source=data.get("source", ""),
    )


def _get_fonts() -> dict:
    """폰트 객체를 로드한다."""
    return {
        "category": ImageFont.truetype(FONT_BOLD, 28),
        "title": ImageFont.truetype(FONT_BOLD, 42),
        "subtitle": ImageFont.truetype(FONT_REGULAR, 24),
        "sender": ImageFont.truetype(FONT_BOLD, 22),
        "message": ImageFont.truetype(FONT_REGULAR, 28),
        "result": ImageFont.truetype(FONT_BOLD, 32),
        "footer": ImageFont.truetype(FONT_REGULAR, 22),
        "avatar": ImageFont.truetype(FONT_BOLD, 22),
        "typing": ImageFont.truetype(FONT_REGULAR, 26),
    }


def _draw_rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    radius: int,
    fill: tuple,
):
    """둥근 모서리 사각형을 그린다."""
    x0, y0, x1, y1 = xy
    r = min(radius, (x1 - x0) // 2, (y1 - y0) // 2)
    draw.rounded_rectangle(xy, radius=r, fill=fill)


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """텍스트를 max_width에 맞게 줄바꿈한다."""
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        words = list(paragraph)  # 한글은 글자 단위
        current = ""
        for ch in words:
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


def _draw_header(draw: ImageDraw.ImageDraw, script: ChatScript, fonts: dict):
    """상단 헤더를 그린다."""
    # 헤더 배경
    _draw_rounded_rect(draw, (0, 0, SHORTS_WIDTH, HEADER_HEIGHT), 0, HEADER_BG)

    # 카테고리 태그 (빨간 배경 둥근 태그)
    if script.category:
        cat_bbox = fonts["category"].getbbox(script.category)
        cat_w = cat_bbox[2] - cat_bbox[0] + 32
        cat_h = cat_bbox[3] - cat_bbox[1] + 16
        cat_x = PADDING
        cat_y = 30
        _draw_rounded_rect(
            draw,
            (cat_x, cat_y, cat_x + cat_w, cat_y + cat_h),
            cat_h // 2,
            HEADER_ACCENT,
        )
        draw.text(
            (cat_x + 16, cat_y + 6),
            script.category,
            fill=TEXT_WHITE,
            font=fonts["category"],
        )

    # 제목
    title_y = 85
    draw.text(
        (PADDING, title_y),
        script.title,
        fill=TEXT_WHITE,
        font=fonts["title"],
    )

    # 부제
    if script.subtitle:
        draw.text(
            (PADDING, title_y + 52),
            script.subtitle,
            fill=TEXT_GRAY,
            font=fonts["subtitle"],
        )

    # 참가자 표시
    if script.participants:
        parts_y = HEADER_HEIGHT - 45
        parts_text = "  ".join(f"@{p}" for p in script.participants)
        draw.text(
            (PADDING, parts_y),
            parts_text,
            fill=TEXT_GRAY,
            font=fonts["sender"],
        )


def _draw_footer(
    draw: ImageDraw.ImageDraw,
    script: ChatScript,
    fonts: dict,
    show_result: bool = False,
):
    """하단 결과 영역을 그린다."""
    footer_y = SHORTS_HEIGHT - FOOTER_HEIGHT
    _draw_rounded_rect(
        draw,
        (0, footer_y, SHORTS_WIDTH, SHORTS_HEIGHT),
        0,
        FOOTER_BG,
    )

    if show_result and script.result_text:
        # 결과 텍스트 (노란 강조)
        draw.text(
            (PADDING, footer_y + 30),
            script.result_text,
            fill=RESULT_ACCENT,
            font=fonts["result"],
        )
    else:
        # 입력창 모양
        input_y = footer_y + 25
        _draw_rounded_rect(
            draw,
            (PADDING, input_y, SHORTS_WIDTH - PADDING, input_y + 50),
            25,
            (50, 55, 75),
        )
        draw.text(
            (PADDING + 20, input_y + 10),
            "메시지를 입력하세요...",
            fill=TEXT_GRAY,
            font=fonts["footer"],
        )


def _calc_bubble_height(
    text: str, font: ImageFont.FreeTypeFont, max_text_w: int,
    image_path: str = "",
) -> int:
    """말풍선의 높이를 계산한다."""
    h = 0

    # 이미지가 있으면 이미지 높이 추가
    if image_path and Path(image_path).exists():
        try:
            with Image.open(image_path) as img:
                iw, ih = img.size
                ratio = min(IMG_BUBBLE_MAX_W / iw, IMG_BUBBLE_MAX_H / ih, 1.0)
                h += int(ih * ratio) + BUBBLE_PAD_V * 2 + 8
        except Exception:
            pass

    # 텍스트가 있으면 텍스트 높이 추가
    if text:
        lines = _wrap_text(text, font, max_text_w)
        line_h = font.getbbox("가")[3] - font.getbbox("가")[1]
        text_h = len(lines) * (line_h + 6)
        if image_path:
            h += text_h + BUBBLE_PAD_V  # 이미지 아래 캡션
        else:
            h += text_h + BUBBLE_PAD_V * 2
    elif not image_path:
        h += BUBBLE_PAD_V * 2

    return h


def _draw_avatar(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    sender: str,
    fonts: dict,
    side: str,
):
    """아바타 원을 그린다."""
    colors = [
        (100, 120, 220), (220, 100, 120), (100, 200, 150),
        (200, 160, 100), (160, 100, 200), (100, 180, 220),
    ]
    color = colors[hash(sender) % len(colors)]
    _draw_rounded_rect(
        draw,
        (x, y, x + AVATAR_SIZE, y + AVATAR_SIZE),
        AVATAR_SIZE // 2,
        color,
    )
    # 이름 첫 글자
    initial = sender[0] if sender else "?"
    bbox = fonts["avatar"].getbbox(initial)
    iw = bbox[2] - bbox[0]
    ih = bbox[3] - bbox[1]
    draw.text(
        (x + (AVATAR_SIZE - iw) // 2, y + (AVATAR_SIZE - ih) // 2 - 2),
        initial,
        fill=TEXT_WHITE,
        font=fonts["avatar"],
    )


def _load_bubble_image(image_path: str) -> Image.Image | None:
    """이미지 버블용 이미지를 로드하고 리사이즈한다."""
    try:
        p = Path(image_path)
        if not p.exists():
            return None
        img = Image.open(p).convert("RGB")
        iw, ih = img.size
        ratio = min(IMG_BUBBLE_MAX_W / iw, IMG_BUBBLE_MAX_H / ih, 1.0)
        new_w = int(iw * ratio)
        new_h = int(ih * ratio)
        return img.resize((new_w, new_h), Image.LANCZOS)
    except Exception:
        return None


def _draw_bubble(
    draw: ImageDraw.ImageDraw,
    msg: ChatMessage,
    y: int,
    fonts: dict,
    frame_img: Image.Image | None = None,
) -> int:
    """하나의 말풍선을 그리고, 사용한 높이를 반환한다.

    Args:
        frame_img: 이미지 paste가 필요할 때 전달 (draw는 ImageDraw이므로)

    Returns:
        이 메시지가 차지한 총 높이 (이름 + 말풍선 + 간격)
    """
    font = fonts["message"]
    max_text_w = BUBBLE_MAX_W - BUBBLE_PAD_H * 2
    has_image = bool(msg.image_path)
    bubble_img = _load_bubble_image(msg.image_path) if has_image else None
    has_text = bool(msg.text.strip())

    # 텍스트 계산
    lines = []
    line_h = 0
    text_h = 0
    max_line_w = 0
    if has_text:
        lines = _wrap_text(msg.text, font, max_text_w)
        line_h = font.getbbox("가")[3] - font.getbbox("가")[1]
        text_h = len(lines) * (line_h + 6) - 6
        max_line_w = max(
            (font.getbbox(line)[2] - font.getbbox(line)[0]) for line in lines
        )

    # 말풍선 크기 계산
    if bubble_img:
        img_w, img_h = bubble_img.size
        bubble_w = img_w + BUBBLE_PAD_H * 2
        bubble_h = BUBBLE_PAD_V + img_h
        if has_text:
            bubble_w = max(bubble_w, max_line_w + BUBBLE_PAD_H * 2)
            bubble_h += 8 + text_h + BUBBLE_PAD_V
        else:
            bubble_h += BUBBLE_PAD_V
    else:
        bubble_w = max_line_w + BUBBLE_PAD_H * 2
        bubble_h = text_h + BUBBLE_PAD_V * 2

    total_h = 0

    if msg.side == "left":
        avatar_x = PADDING
        bubble_x = PADDING + AVATAR_SIZE + 12

        # 이름 표시
        draw.text(
            (bubble_x, y),
            msg.sender,
            fill=TEXT_GRAY,
            font=fonts["sender"],
        )
        name_h = fonts["sender"].getbbox(msg.sender)[3] - fonts["sender"].getbbox(msg.sender)[1]
        total_h += name_h + 8

        _draw_avatar(draw, avatar_x, y, msg.sender, fonts, "left")

        bx = bubble_x
        by = y + total_h
        _draw_rounded_rect(
            draw,
            (bx, by, bx + bubble_w, by + bubble_h),
            BUBBLE_RADIUS,
            BUBBLE_LEFT,
        )

        # 이미지
        cy = by + BUBBLE_PAD_V
        if bubble_img and frame_img:
            ix = bx + BUBBLE_PAD_H
            # 둥근 모서리 마스크 적용
            _paste_rounded_image(frame_img, bubble_img, ix, cy, 12)
            cy += bubble_img.size[1] + 8

        # 텍스트
        if has_text:
            for line in lines:
                draw.text((bx + BUBBLE_PAD_H, cy), line, fill=TEXT_WHITE, font=font)
                cy += line_h + 6

        total_h += bubble_h

    else:  # right
        name_bbox = fonts["sender"].getbbox(msg.sender)
        name_w = name_bbox[2] - name_bbox[0]
        name_x = SHORTS_WIDTH - PADDING - AVATAR_SIZE - 12 - name_w
        draw.text(
            (name_x, y),
            msg.sender,
            fill=TEXT_GRAY,
            font=fonts["sender"],
        )
        name_h = name_bbox[3] - name_bbox[1]
        total_h += name_h + 8

        avatar_x = SHORTS_WIDTH - PADDING - AVATAR_SIZE
        _draw_avatar(draw, avatar_x, y, msg.sender, fonts, "right")

        bx = SHORTS_WIDTH - PADDING - AVATAR_SIZE - 12 - bubble_w
        by = y + total_h
        _draw_rounded_rect(
            draw,
            (bx, by, bx + bubble_w, by + bubble_h),
            BUBBLE_RADIUS,
            BUBBLE_RIGHT,
        )

        # 이미지
        cy = by + BUBBLE_PAD_V
        if bubble_img and frame_img:
            ix = bx + BUBBLE_PAD_H
            _paste_rounded_image(frame_img, bubble_img, ix, cy, 12)
            cy += bubble_img.size[1] + 8

        # 텍스트
        if has_text:
            for line in lines:
                draw.text((bx + BUBBLE_PAD_H, cy), line, fill=TEXT_WHITE, font=font)
                cy += line_h + 6

        total_h += bubble_h

    return total_h + MSG_GAP


def _paste_rounded_image(
    frame: Image.Image, img: Image.Image, x: int, y: int, radius: int
):
    """둥근 모서리 마스크를 적용하여 이미지를 프레임에 붙인다."""
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((0, 0, w, h), radius=radius, fill=255)
    frame.paste(img, (x, y), mask)


def _draw_typing_indicator(
    draw: ImageDraw.ImageDraw,
    y: int,
    sender: str,
    fonts: dict,
    frame: int,
):
    """타이핑 중 인디케이터 (점 3개 애니메이션)."""
    avatar_x = PADDING
    _draw_avatar(draw, avatar_x, y, sender, fonts, "left")

    # 이름
    bx = PADDING + AVATAR_SIZE + 12
    draw.text((bx, y), sender, fill=TEXT_GRAY, font=fonts["sender"])
    name_h = fonts["sender"].getbbox(sender)[3] - fonts["sender"].getbbox(sender)[1]

    # 타이핑 말풍선
    by = y + name_h + 8
    dot_bubble_w = 100
    dot_bubble_h = 45
    _draw_rounded_rect(
        draw,
        (bx, by, bx + dot_bubble_w, by + dot_bubble_h),
        BUBBLE_RADIUS,
        BUBBLE_LEFT,
    )

    # 점 3개 (프레임에 따라 크기 변화)
    for i in range(3):
        phase = (frame + i * 4) % 12
        size = 6 + 3 * math.sin(phase * math.pi / 6)
        cx = bx + 30 + i * 20
        cy = by + dot_bubble_h // 2
        r = int(size)
        draw.ellipse(
            (cx - r, cy - r, cx + r, cy + r),
            fill=TYPING_DOT,
        )


def _apply_zoom(img: Image.Image, factor: float) -> Image.Image:
    """이미지 중앙 기준 줌 효과를 적용한다."""
    if abs(factor - 1.0) < 0.001:
        return img
    w, h = img.size
    new_w = int(w * factor)
    new_h = int(h * factor)
    zoomed = img.resize((new_w, new_h), Image.LANCZOS)
    # 중앙 크롭
    left = (new_w - w) // 2
    top = (new_h - h) // 2
    return zoomed.crop((left, top, left + w, top + h))


def _apply_shake(img: Image.Image, intensity: int, frame: int) -> Image.Image:
    """화면 흔들림 효과를 적용한다."""
    if intensity <= 0:
        return img
    dx = int(intensity * math.sin(frame * 2.5))
    dy = int(intensity * math.cos(frame * 3.3))
    w, h = img.size
    shifted = Image.new("RGB", (w, h), BG_COLOR)
    shifted.paste(img, (dx, dy))
    return shifted


def build_timeline(
    script: ChatScript,
    fps: int = SHORTS_FPS,
    msg_durations: list[float] | None = None,
    typing_sec: float = 0.8,
    result_delay_sec: float = 1.0,
    hold_end_sec: float = 3.0,
    min_display_sec: float = 1.2,
) -> tuple[list[tuple[int, int]], int, int]:
    """타임라인을 계산한다.

    Args:
        script: 채팅 대본
        fps: 프레임 레이트
        msg_durations: 각 메시지의 TTS 재생 시간 리스트 (None이면 고정 1.5초)
        typing_sec: 타이핑 인디케이터 시간
        result_delay_sec: 결과 표시 딜레이
        hold_end_sec: 마지막 프레임 유지 시간
        min_display_sec: 메시지 최소 표시 시간

    Returns:
        (timeline, result_frame, total_frames)
        timeline: [(typing_start, msg_appear), ...]
    """
    timeline = []
    current_frame = int(1.0 * fps)

    for i, msg in enumerate(script.messages):
        typing_start = current_frame
        msg_appear = typing_start + int(typing_sec * fps)
        timeline.append((typing_start, msg_appear))

        # TTS 기반 표시 시간 또는 고정값
        if msg_durations and i < len(msg_durations):
            display_sec = max(msg_durations[i] + 0.3, min_display_sec)
        else:
            display_sec = 1.5

        current_frame = msg_appear + int(display_sec * fps)

    result_frame = current_frame + int(result_delay_sec * fps)
    total_frames = result_frame + int(hold_end_sec * fps)

    # Shorts 55초 제한 (60초에 약간 여유)
    max_frames = int(55 * fps)
    if total_frames > max_frames:
        # 비례적으로 타이밍 압축
        scale = max_frames / total_frames
        timeline = [(int(ts * scale), int(ma * scale)) for ts, ma in timeline]
        result_frame = int(result_frame * scale)
        total_frames = max_frames

    return timeline, result_frame, total_frames


def _iter_frames(
    script: ChatScript,
    fonts: dict,
    timeline: list[tuple[int, int]],
    msg_heights: list[int],
    result_frame: int,
    total_frames: int,
    fps: int,
    enable_effects: bool = True,
):
    """프레임을 하나씩 yield하는 제너레이터 (메모리 절약)."""
    hook_appear = timeline[0][1] if timeline else 0
    hook_end = hook_appear + int(0.5 * fps)
    result_shake_end = result_frame + int(0.4 * fps)

    for f_idx in range(total_frames):
        img = Image.new("RGB", (SHORTS_WIDTH, SHORTS_HEIGHT), BG_COLOR)
        draw = ImageDraw.Draw(img)

        _draw_header(draw, script, fonts)

        visible_count = 0
        typing_msg_idx = -1

        for i, (ts, ma) in enumerate(timeline):
            if f_idx >= ma:
                visible_count = i + 1
            elif f_idx >= ts:
                typing_msg_idx = i
                break

        total_msg_h = sum(msg_heights[:visible_count])
        available_h = CHAT_AREA_BOTTOM - CHAT_AREA_TOP
        extra_h = 80 if typing_msg_idx >= 0 else 0

        scroll_offset = 0
        if total_msg_h + extra_h > available_h:
            scroll_offset = total_msg_h + extra_h - available_h

        y = CHAT_AREA_TOP - scroll_offset
        for i in range(visible_count):
            if y + msg_heights[i] > CHAT_AREA_TOP - 20:
                _draw_bubble(draw, script.messages[i], max(y, CHAT_AREA_TOP), fonts, frame_img=img)
            y += msg_heights[i]

        if typing_msg_idx >= 0:
            next_msg = script.messages[typing_msg_idx]
            if next_msg.side == "left":
                ty = max(y, CHAT_AREA_TOP)
                if ty < CHAT_AREA_BOTTOM - 60:
                    _draw_typing_indicator(draw, ty, next_msg.sender, fonts, f_idx)

        show_result = f_idx >= result_frame
        _draw_footer(draw, script, fonts, show_result)

        for gy in range(HEADER_HEIGHT, HEADER_HEIGHT + 30):
            draw.line([(0, gy), (SHORTS_WIDTH, gy)], fill=BG_COLOR, width=1)

        if enable_effects:
            if hook_appear <= f_idx < hook_end:
                progress = (f_idx - hook_appear) / max(hook_end - hook_appear, 1)
                zoom = 1.0 + 0.06 * math.sin(progress * math.pi)
                img = _apply_zoom(img, zoom)

            if result_frame <= f_idx < result_shake_end:
                progress = (f_idx - result_frame) / max(result_shake_end - result_frame, 1)
                intensity = int(8 * (1.0 - progress))
                img = _apply_shake(img, intensity, f_idx)

        yield img


def render_frames(
    script: ChatScript,
    fps: int = SHORTS_FPS,
    msg_appear_sec: float = 1.5,
    typing_sec: float = 0.8,
    result_delay_sec: float = 1.0,
    hold_end_sec: float = 3.0,
    msg_durations: list[float] | None = None,
    enable_effects: bool = True,
) -> list[Image.Image]:
    """채팅 대본을 프레임 시퀀스로 렌더링한다 (리스트 반환).

    Note: 메모리 효율이 필요하면 render_frames_to_dir()을 사용하라.
    """
    return list(render_frames_iter(
        script, fps, msg_appear_sec, typing_sec,
        result_delay_sec, hold_end_sec, msg_durations, enable_effects,
    ))


def render_frames_iter(
    script: ChatScript,
    fps: int = SHORTS_FPS,
    msg_appear_sec: float = 1.5,
    typing_sec: float = 0.8,
    result_delay_sec: float = 1.0,
    hold_end_sec: float = 3.0,
    msg_durations: list[float] | None = None,
    enable_effects: bool = True,
):
    """채팅 대본을 프레임 제너레이터로 렌더링한다 (메모리 절약)."""
    fonts = _get_fonts()
    num_msgs = len(script.messages)

    if msg_durations:
        timeline, result_frame, total_frames = build_timeline(
            script, fps, msg_durations, typing_sec, result_delay_sec, hold_end_sec
        )
    else:
        timeline, result_frame, total_frames = build_timeline(
            script, fps, [msg_appear_sec] * num_msgs, typing_sec,
            result_delay_sec, hold_end_sec, min_display_sec=msg_appear_sec,
        )

    msg_heights = []
    for msg in script.messages:
        h = _calc_bubble_height(
            msg.text,
            fonts["message"],
            BUBBLE_MAX_W - BUBBLE_PAD_H * 2,
            image_path=msg.image_path,
        )
        name_h = fonts["sender"].getbbox(msg.sender)[3] - fonts["sender"].getbbox(msg.sender)[1]
        msg_heights.append(h + name_h + 8 + MSG_GAP)

    yield from _iter_frames(
        script, fonts, timeline, msg_heights,
        result_frame, total_frames, fps, enable_effects,
    )


def render_frames_to_dir(
    script: ChatScript,
    output_dir: Path,
    fps: int = SHORTS_FPS,
    msg_durations: list[float] | None = None,
    enable_effects: bool = True,
) -> int:
    """프레임을 디스크에 직접 저장한다 (메모리 효율).

    Returns:
        총 프레임 수
    """
    count = 0
    for img in render_frames_iter(
        script, fps=fps, msg_durations=msg_durations, enable_effects=enable_effects,
    ):
        img.save(output_dir / f"frame_{count:06d}.png")
        count += 1
    return count
