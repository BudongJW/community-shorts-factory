"""Edge TTS 기반 음성 합성 + SRT 자막 생성."""

import asyncio
from pathlib import Path

import edge_tts

from config.settings import TTS_VOICE, TTS_RATE, AUDIO_DIR, SRT_DIR


async def _synthesize(text: str, audio_path: Path, srt_path: Path) -> None:
    """Edge TTS로 음성과 자막을 동시에 생성한다."""
    communicate = edge_tts.Communicate(text, TTS_VOICE, rate=TTS_RATE)
    submaker = edge_tts.SubMaker()

    audio_path.parent.mkdir(parents=True, exist_ok=True)
    srt_path.parent.mkdir(parents=True, exist_ok=True)

    with open(audio_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.feed(chunk)

    srt_path.write_text(submaker.generate_subs(), encoding="utf-8")


def synthesize(text: str, filename: str = "narration") -> tuple[Path, Path]:
    """음성 + 자막 생성 동기 진입점.

    Returns:
        (audio_path, srt_path) 튜플
    """
    audio_path = AUDIO_DIR / f"{filename}.mp3"
    srt_path = SRT_DIR / f"{filename}.srt"
    asyncio.run(_synthesize(text, audio_path, srt_path))
    return audio_path, srt_path
