"""Edge TTS 기반 음성 합성 + SRT 자막 생성."""

import asyncio
import random
from pathlib import Path

import edge_tts

from config.settings import AUDIO_DIR, SRT_DIR

# 한국어 음성 목록 (이름, 성별, 특성)
KO_VOICES = [
    ("ko-KR-SunHiNeural", "female", "밝고 명랑"),
    ("ko-KR-InJoonNeural", "male", "차분하고 신뢰감"),
    ("ko-KR-HyunsuMultilingualNeural", "male", "또렷하고 자연스러움"),
]

# 속도 변화 옵션
RATE_OPTIONS = ["+0%", "+5%", "+10%", "-5%"]


def pick_voice(gender: str | None = None) -> tuple[str, str]:
    """음성을 선택한다.

    Args:
        gender: "male", "female", 또는 None (랜덤)

    Returns:
        (voice_name, rate) 튜플
    """
    pool = KO_VOICES
    if gender:
        pool = [v for v in KO_VOICES if v[1] == gender]

    voice_name, _, _ = random.choice(pool)
    rate = random.choice(RATE_OPTIONS)
    return voice_name, rate


async def _synthesize(
    text: str,
    audio_path: Path,
    srt_path: Path,
    voice: str | None = None,
    rate: str | None = None,
) -> dict:
    """Edge TTS로 음성과 자막을 동시에 생성한다."""
    if voice is None or rate is None:
        voice, rate = pick_voice()

    communicate = edge_tts.Communicate(text, voice, rate=rate)
    submaker = edge_tts.SubMaker()

    audio_path.parent.mkdir(parents=True, exist_ok=True)
    srt_path.parent.mkdir(parents=True, exist_ok=True)

    with open(audio_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                submaker.feed(chunk)

    srt_path.write_text(submaker.get_srt(), encoding="utf-8")
    return {"voice": voice, "rate": rate}


def synthesize(
    text: str,
    filename: str = "narration",
    voice: str | None = None,
    rate: str | None = None,
) -> tuple[Path, Path, dict]:
    """음성 + 자막 생성 동기 진입점.

    Args:
        text: 읽을 텍스트
        filename: 출력 파일명
        voice: 음성 이름 (None이면 랜덤)
        rate: 속도 (None이면 랜덤)

    Returns:
        (audio_path, srt_path, meta) 튜플. meta에 사용된 voice/rate 포함.
    """
    audio_path = AUDIO_DIR / f"{filename}.mp3"
    srt_path = SRT_DIR / f"{filename}.srt"
    meta = asyncio.run(_synthesize(text, audio_path, srt_path, voice, rate))
    return audio_path, srt_path, meta
