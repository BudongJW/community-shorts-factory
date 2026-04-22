"""쇼츠 첫 1초 훅 오버레이.

FFmpeg drawtext 필터용 표현식 및 PIL용 폰트/텍스트 렌더링 헬퍼.
첫 1.2초 동안 큰 텍스트를 중앙 상단에 띄웠다가 페이드 아웃시킨다.
"""

import platform
import random
from pathlib import Path

# 영어 훅 풀 — 쇼츠 리텐션 최적화용 짧은 텍스트
HOOKS = [
    "WAIT FOR IT...",
    "POV:",
    "NO WAY",
    "HOW??",
    "WATCH",
    "BRO",
    "OMG",
    "LOOK",
    "STOP",
    "???",
    "WHAT",
    "NOT AGAIN",
    "SEND HELP",
    "IM DONE",
    "WHY",
    "EVERY TIME",
]

HOOK_DURATION = 1.2  # 초. 이 시간 지나면 페이드 아웃.
HOOK_FADE = 0.3      # 페이드 아웃 길이(초)

# 훅 위치 옵션. 동일 채널에서 매 영상 같은 위치면 포맷 단조로움.
# ratio는 영상 높이 기준 y좌표 (0=최상단, 1=최하단).
HOOK_POSITIONS = [
    ("top", 0.18),      # 상단 1/5 지점 — 기본. 썸네일 영역과 겹침.
    ("upper", 0.28),    # 상단 1/4 지점 — 얼굴 피하면서 시선 유지.
    ("center", 0.42),   # 중앙 약간 위 — 고양이 얼굴 많을 때 가림 위험, 주의.
    ("lower", 0.70),    # 하단 1/3 지점 — UI 아이콘과 겹치지 않도록 70% 이내.
]


def pick_hook() -> str:
    """랜덤 훅 문구 선택."""
    return random.choice(HOOKS)


def pick_hook_position() -> tuple[str, float]:
    """랜덤 훅 위치 선택. (이름, y_ratio) 반환.

    top 위치에 가중치 — 쇼츠 시청자는 화면 상단 시선이 가장 먼저 닿음.
    단, 매번 top이면 단조로워서 가끔 다른 위치 섞음.
    """
    weights = [0.5, 0.25, 0.10, 0.15]  # top, upper, center, lower
    return random.choices(HOOK_POSITIONS, weights=weights, k=1)[0]


def find_bold_font() -> str:
    """OS별로 punchy한 bold 폰트 경로 반환.

    영문 훅 전용이므로 한글 폰트(Nanum)보다 DejaVu Sans Bold 선호.
    """
    if platform.system() == "Windows":
        for p in [
            "C:/Windows/Fonts/impact.ttf",
            "C:/Windows/Fonts/ariblk.ttf",   # Arial Black
            "C:/Windows/Fonts/malgunbd.ttf",
        ]:
            if Path(p).exists():
                return p
        return "C:/Windows/Fonts/arial.ttf"
    # Linux
    for p in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    ]:
        if Path(p).exists():
            return p
    return "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def ffmpeg_drawtext_filter(hook: str, video_h: int = 1920, y_ratio: float = 0.18) -> str:
    """훅 텍스트를 FFmpeg drawtext 필터 expression으로 변환.

    첫 HOOK_DURATION 초 동안 표시하고 마지막 HOOK_FADE 초에 알파 fade out.
    drawtext의 특수문자는 백슬래시 이스케이프 필요.
    """
    # drawtext 안전 이스케이프: single quote는 필터 파서가 close-reopen 패턴만 인정.
    # `\'`는 내부 처리되지 않아 문자열이 쪼개져 "filter not found" 발생.
    # HOOKS 풀에는 애초에 apostrophe를 넣지 않지만 외부 입력 대비용 방어책.
    safe = (
        hook.replace("\\", "\\\\")
        .replace("'", "'\\''")
        .replace(":", "\\:")
        .replace("%", "\\%")
    )
    font = find_bold_font().replace("\\", "/").replace(":", "\\:")
    y = int(video_h * y_ratio)
    fade_start = HOOK_DURATION - HOOK_FADE
    # alpha expression: t<fade_start면 1, 이후 선형 감소
    alpha_expr = f"if(lt(t,{fade_start}),1,max(0,1-(t-{fade_start})/{HOOK_FADE}))"
    return (
        f"drawtext=fontfile='{font}'"
        f":text='{safe}'"
        f":fontsize=120:fontcolor=white"
        f":borderw=6:bordercolor=black"
        f":x=(w-text_w)/2:y={y}"
        f":alpha='{alpha_expr}'"
        f":enable='between(t,0,{HOOK_DURATION})'"
    )


def pil_draw_hook(pil_img, hook: str, progress: float, y_ratio: float = 0.18):
    """PIL 이미지에 훅 텍스트를 in-place로 그린다.

    progress: 0.0(시작) ~ 1.0(HOOK_DURATION 끝)
    HOOK_DURATION 이후 호출되면 변화 없음.
    """
    from PIL import Image, ImageDraw, ImageFont

    if progress < 0 or progress >= 1.0:
        return pil_img

    # 알파 계산: 끝 HOOK_FADE/HOOK_DURATION 구간에서 선형 감소
    fade_start = (HOOK_DURATION - HOOK_FADE) / HOOK_DURATION
    if progress < fade_start:
        alpha = 1.0
    else:
        alpha = max(0.0, 1.0 - (progress - fade_start) / (1.0 - fade_start))

    if alpha <= 0:
        return pil_img

    overlay = Image.new("RGBA", pil_img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    try:
        font = ImageFont.truetype(find_bold_font(), 120)
    except OSError:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), hook, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (pil_img.width - tw) // 2 - bbox[0]
    y = int(pil_img.height * y_ratio)

    a = int(alpha * 255)
    # 검정 외곽선
    for dx, dy in [(-4, 0), (4, 0), (0, -4), (0, 4), (-3, -3), (3, -3), (-3, 3), (3, 3)]:
        draw.text((x + dx, y + dy), hook, font=font, fill=(0, 0, 0, a))
    # 흰색 본문
    draw.text((x, y), hook, font=font, fill=(255, 255, 255, a))

    if pil_img.mode != "RGBA":
        pil_img = pil_img.convert("RGBA")
    composited = Image.alpha_composite(pil_img, overlay)
    return composited.convert("RGB")
