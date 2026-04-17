"""Pollinations.ai로 AI 고양이 애니메이션 이미지를 생성한다.

무료, API 키 불필요. 세로(1080x1920) 이미지를 직접 생성한다.
"""

import random
import time
from pathlib import Path

import requests

from src.utils.logger import setup_logger

log = setup_logger("ai_cat_images")

# 고양이 애니메이션 장면 프롬프트 템플릿
SCENE_TEMPLATES = [
    # 변신/합체 시리즈
    (
        "anime style, {cat_desc} cat transforming into a giant mecha robot, "
        "dramatic transformation pose, energy beams, {style}"
    ),
    (
        "anime style, three {cat_desc} cats combining together to form a mega cat robot, "
        "voltron style combination sequence, glowing energy, {style}"
    ),
    (
        "anime style, {cat_desc} cat piloting a giant gundam-style robot from cockpit, "
        "screens and controls, dramatic lighting, {style}"
    ),
    (
        "anime style, {cat_desc} cat in power armor suit flying through city, "
        "jet boosters, heroic pose, {style}"
    ),
    # 전투/액션 시리즈
    (
        "anime style, samurai {cat_desc} cat with katana sword in dramatic pose, "
        "cherry blossoms falling, moonlight, {style}"
    ),
    (
        "anime style, {cat_desc} cat wizard casting a massive fire spell, "
        "magic circles, glowing runes, epic fantasy, {style}"
    ),
    (
        "anime style, ninja {cat_desc} cat throwing shuriken on rooftop at night, "
        "dramatic action scene, speed lines, {style}"
    ),
    (
        "anime style, {cat_desc} cat boxer in boxing ring, uppercut punch, "
        "sweat flying, dramatic angle, intense expression, {style}"
    ),
    # 일상 코미디 시리즈
    (
        "anime style, {cat_desc} cat wearing a tiny business suit giving presentation "
        "to other cats in office, powerpoint, serious expression, {style}"
    ),
    (
        "anime style, {cat_desc} cat as a chef cooking ramen in japanese restaurant, "
        "steam rising, detailed food, cozy atmosphere, {style}"
    ),
    (
        "anime style, {cat_desc} cat DJ at huge music festival, turntables, "
        "crowd of cats dancing, neon lights, {style}"
    ),
    (
        "anime style, {cat_desc} cat astronaut floating in space station, "
        "earth visible through window, zero gravity, {style}"
    ),
    # 대서사 시리즈
    (
        "anime style, army of {cat_desc} cats marching in formation, "
        "epic battle scene, flags waving, dramatic sky, {style}"
    ),
    (
        "anime style, dragon-rider {cat_desc} cat flying on a dragon above clouds, "
        "sunset, epic fantasy landscape, {style}"
    ),
    (
        "anime style, {cat_desc} cat king sitting on golden throne, "
        "crown and royal cape, loyal cat subjects bowing, {style}"
    ),
    (
        "anime style, giant kaiju {cat_desc} cat destroying tokyo city, "
        "buildings crumbling, helicopters, godzilla parody, {style}"
    ),
]

CAT_TYPES = [
    "orange tabby", "black", "white", "calico", "tuxedo",
    "grey", "siamese", "persian fluffy", "scottish fold",
]

STYLES = [
    "vibrant colors, detailed, vertical composition 9:16, cinematic lighting",
    "pastel colors, soft glow, vertical composition 9:16, beautiful detailed",
    "dark dramatic lighting, vertical composition 9:16, epic scene, detailed",
    "bright colorful explosion background, vertical 9:16, dynamic composition",
]


def generate_scene_prompts(num_scenes: int = 4) -> list[str]:
    """연속된 장면 프롬프트를 생성한다.

    하나의 '에피소드'를 구성하는 4~6장의 장면.
    """
    cat = random.choice(CAT_TYPES)
    style = random.choice(STYLES)

    # 랜덤 템플릿 선택 (중복 없이)
    templates = random.sample(SCENE_TEMPLATES, min(num_scenes, len(SCENE_TEMPLATES)))

    prompts = []
    for tmpl in templates:
        prompt = tmpl.format(cat_desc=cat, style=style)
        prompts.append(prompt)

    return prompts


def generate_ai_cat_images(
    num_images: int = 4,
    output_dir: Path | None = None,
) -> list[Path]:
    """AI 고양이 애니메이션 이미지를 생성한다.

    Args:
        num_images: 생성할 이미지 수 (4~6 권장)
        output_dir: 출력 디렉토리

    Returns:
        생성된 이미지 파일 경로 리스트
    """
    if output_dir is None:
        output_dir = Path("output") / "ai_cats"
    output_dir.mkdir(parents=True, exist_ok=True)

    prompts = generate_scene_prompts(num_images)
    generated = []

    for i, prompt in enumerate(prompts):
        log.info(f"  [{i+1}/{len(prompts)}] generating...")

        encoded = requests.utils.quote(prompt)
        # seed를 다르게 해서 매번 다른 이미지 생성
        seed = random.randint(1, 999999)
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width=1080&height=1920&nologo=true&seed={seed}"
        )

        try:
            resp = requests.get(url, timeout=90)
            if resp.status_code == 200 and len(resp.content) > 10000:
                path = output_dir / f"scene_{i:02d}.png"
                path.write_bytes(resp.content)
                generated.append(path)
                log.info(f"  -> {path.name} ({len(resp.content) // 1024}KB)")
            else:
                log.warning(f"  failed: status={resp.status_code}")
        except Exception as e:
            log.warning(f"  failed: {e}")

        # API 레이트 리밋 방지
        if i < len(prompts) - 1:
            time.sleep(2)

    return generated
