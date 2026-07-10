"""Pollinations.ai로 사실적 공포 장면 이미지를 생성한다.

무료, API 키 불필요. 세로(1080x1920) 이미지를 직접 생성한다.

종이필름(Jongie Film) 스타일을 목표로 한다:
- abandoned : 폐가/버려진 건물을 1인칭으로 탐험하는 시퀀스
- everyday  : 평범한 일상(교실, 자취방, 스터디카페)에 무언가 잘못돼 있는 아날로그 호러

각 시퀀스는 '빌드업 장면들 + 마지막 점프스케어 리빌' 순서로 구성된다.
마지막 이미지(scare)는 컴포저가 점프스케어로 처리한다.
"""

import random
import time
from pathlib import Path

import requests

from src.utils.logger import setup_logger

log = setup_logger("ai_horror_images")

# 사진 사실감을 강제하는 공통 스타일 접미사 (flux/pollinations 기준).
# "게임/현실 그래픽" 느낌을 위해 first person POV, found footage, 손전등 조명을 강조.
PHOTO_STYLE = (
    "photorealistic, first person POV, found footage, handheld camera, "
    "dim flashlight lighting, deep shadows, film grain, high detail, "
    "eerie horror atmosphere, vertical 9:16 composition, cinematic, "
    "night, desaturated colors"
)

SCARE_STYLE = (
    "photorealistic, extreme close-up, sudden reveal, terrifying, "
    "flash lit face, dark background, film grain, vertical 9:16, "
    "high contrast, horror jumpscare"
)

# ── 폐가 탐험 시퀀스 (abandoned) ──
# 각 항목은 하나의 '탐험'을 구성하는 순서 있는 장면 리스트.
# 마지막 원소는 점프스케어 리빌.
ABANDONED_SCRIPTS = [
    [
        "the rotten front door of an abandoned house slowly opening into darkness",
        "a decayed living room covered in dust, broken furniture, faint light through boards",
        "a long dark hallway with peeling wallpaper stretching into blackness",
        "a child's abandoned bedroom, an old doll sitting on a broken bed",
        "a half-open closet door with something moving in the gap",
        ("a pale ghostly woman's face with black hollow eyes lunging at the camera", "scare"),
    ],
    [
        "the entrance of a flooded abandoned hospital corridor, wheelchairs overturned",
        "an abandoned hospital ward, rusted beds, torn curtains swaying",
        "a dark stairwell going down to the basement, flashlight beam trembling",
        "a morgue room with open metal drawers in the dark",
        "a figure standing motionless at the far end of the room",
        ("a decayed corpse face screaming inches from the camera", "scare"),
    ],
    [
        "an abandoned school hallway at night, lockers rusted, papers on the floor",
        "an empty classroom, desks overturned, a message scratched on the blackboard",
        "a dark school bathroom, cracked mirrors reflecting the flashlight",
        "a narrow storage room full of old chairs and mannequins",
        "a small pale hand reaching from under a desk",
        ("a demonic schoolgirl face with bleeding eyes appearing suddenly", "scare"),
    ],
    [
        "a deserted underground parking lot, flickering fluorescent light, one car left",
        "a dark maintenance corridor with dripping pipes and exposed wires",
        "an old boiler room, rusted machinery, steam and shadows",
        "a locked steel door with claw marks scratched into it",
        "a tall shadow figure standing under a broken light",
        ("a monstrous shadow creature with a gaping mouth rushing forward", "scare"),
    ],
]

# ── 일상 괴담 시퀀스 (everyday, 종이필름 스타일) ──
# 평범해 보이지만 후반으로 갈수록 무언가 잘못돼 있는 구성.
EVERYDAY_SCRIPTS = [
    [
        "a cozy one-room studio apartment at night, TV on, ordinary and calm",
        "the same room, but a dark humanoid figure faintly visible in the mirror",
        "a hallway of the apartment, the door slightly open, darkness outside",
        "the bed with blanket, a hand-shaped bulge underneath it",
        "a distorted face pressing against the window from outside",
        ("a pale face with a wide unnatural smile appearing right behind the viewer", "scare"),
    ],
    [
        "a quiet study cafe at night, empty seats, warm lamp light, ordinary",
        "the same cafe, one figure sitting perfectly still facing the wall",
        "a corridor to the restroom, lights flickering, a wet trail on the floor",
        "the restroom mirror showing a reflection that is slightly wrong",
        "a tall thin figure standing where no one was a second ago",
        ("a screaming ghost face lunging out of the mirror", "scare"),
    ],
    [
        "an ordinary school classroom during the day, empty desks, sunlight",
        "the same classroom but everyone's face turned away, unnaturally still",
        "the back of the class, a student with a wrong number of limbs, blurred",
        "the hallway, a long shadow with no body casting on the wall",
        "a child standing at the end of the corridor staring back",
        ("a pale child's face with black eyes rushing toward the camera", "scare"),
    ],
    [
        "a family living room in the evening, ordinary and warm, toys on the floor",
        "the same room, a dark figure standing behind the sofa unnoticed",
        "a child's room with a closet door creaking open by itself",
        "the closet interior, clothes hanging, two eyes glowing in the dark",
        "a crawling humanoid figure coming out from under the bed",
        ("a monstrous grinning face filling the whole screen", "scare"),
    ],
]

VARIANT_SCRIPTS = {
    "abandoned": ABANDONED_SCRIPTS,
    "everyday": EVERYDAY_SCRIPTS,
}


def _build_scene_list(variant: str, num_scenes: int) -> list[tuple[str, bool]]:
    """(프롬프트, is_scare) 튜플의 순서 있는 리스트를 만든다.

    스크립트에서 빌드업 장면 (num_scenes-1)개 + 점프스케어 1개를 선택한다.
    빌드업 장면은 원래 순서를 유지하되 필요 시 앞쪽부터 잘라 개수를 맞춘다.
    """
    scripts = VARIANT_SCRIPTS.get(variant, ABANDONED_SCRIPTS)
    script = random.choice(scripts)

    build = [s for s in script if not (isinstance(s, tuple) and s[1] == "scare")]
    scare = next((s for s in script if isinstance(s, tuple) and s[1] == "scare"), None)

    # 빌드업 장면 수 맞추기 (마지막 scare 자리 1개 확보)
    want_build = max(1, num_scenes - 1)
    if len(build) > want_build:
        # 앞(입구)과 뒤(가장 긴장감 높은 장면)를 유지하도록 균등 샘플
        idxs = sorted(random.sample(range(len(build)), want_build))
        build = [build[i] for i in idxs]

    scenes: list[tuple[str, bool]] = [(p, False) for p in build]
    if scare:
        scenes.append((scare[0], True))
    return scenes


def _fetch_one(prompt: str, style: str, out_path: Path) -> bool:
    """Pollinations에서 이미지 1장 생성. 성공 시 True."""
    full = f"{prompt}, {style}"
    encoded = requests.utils.quote(full)
    for attempt in range(3):
        seed = random.randint(1, 999999)
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width=1080&height=1920&nologo=true&seed={seed}&model=flux"
        )
        try:
            resp = requests.get(url, timeout=90)
            if resp.status_code == 200 and len(resp.content) > 10000:
                out_path.write_bytes(resp.content)
                return True
            log.warning(
                f"  attempt {attempt+1}/3 failed: "
                f"status={resp.status_code} bytes={len(resp.content)}"
            )
        except Exception as e:
            log.warning(f"  attempt {attempt+1}/3 failed: {e}")
        time.sleep(2 ** (attempt + 1))
    return False


def generate_horror_images(
    variant: str = "abandoned",
    num_scenes: int = 6,
    output_dir: Path | None = None,
) -> tuple[list[Path], Path | None]:
    """공포 장면 이미지 시퀀스를 생성한다.

    Args:
        variant: "abandoned"(폐가 탐험) 또는 "everyday"(일상 괴담)
        num_scenes: 총 장면 수 (빌드업 + 점프스케어 1). 5~6 권장.
        output_dir: 출력 디렉토리

    Returns:
        (빌드업 이미지 경로 리스트, 점프스케어 이미지 경로 or None)
    """
    if output_dir is None:
        output_dir = Path("output") / "ai_horror"
    output_dir.mkdir(parents=True, exist_ok=True)

    scenes = _build_scene_list(variant, num_scenes)
    log.info(f"  variant={variant}, {len(scenes)} scenes")

    build_paths: list[Path] = []
    scare_path: Path | None = None

    for i, (prompt, is_scare) in enumerate(scenes):
        log.info(f"  [{i+1}/{len(scenes)}] generating{' (SCARE)' if is_scare else ''}...")
        style = SCARE_STYLE if is_scare else PHOTO_STYLE
        path = output_dir / (f"scare.png" if is_scare else f"scene_{i:02d}.png")

        if _fetch_one(prompt, style, path):
            log.info(f"  -> {path.name} ({path.stat().st_size // 1024}KB)")
            if is_scare:
                scare_path = path
            else:
                build_paths.append(path)
        else:
            log.error(f"  scene {i} 3회 재시도 모두 실패")

        if i < len(scenes) - 1:
            time.sleep(2)

    return build_paths, scare_path
