"""채팅 메시지별 캐릭터 TTS 합성기.

각 참가자에게 고유한 Edge TTS 음성을 배정하고,
메시지별로 개별 음성 파일을 생성한다.
"""

import asyncio
import tempfile
from pathlib import Path

import edge_tts
import numpy as np
import wave

from config.settings import AUDIO_DIR

# 한국어 음성 풀 (이름, 성별, 특성)
KO_VOICE_POOL = [
    ("ko-KR-SunHiNeural", "female"),
    ("ko-KR-InJoonNeural", "male"),
    ("ko-KR-HyunsuMultilingualNeural", "male"),
]

SAMPLE_RATE = 44100


def assign_voices(participants: list[str]) -> dict[str, str]:
    """참가자에게 고유 음성을 배정한다.

    첫 번째 참가자(left side, 이야기 꺼내는 쪽) -> 여성
    두 번째 참가자(right side, 반응하는 쪽) -> 남성
    추가 참가자 -> 라운드 로빈
    """
    voice_map = {}
    for i, name in enumerate(participants):
        voice_idx = i % len(KO_VOICE_POOL)
        voice_map[name] = KO_VOICE_POOL[voice_idx][0]
    return voice_map


async def _synthesize_message(
    text: str,
    voice: str,
    output_path: Path,
    rate: str = "+5%",
    retries: int = 2,
) -> float:
    """단일 메시지를 TTS로 합성하고 재생 시간(초)을 반환한다."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(retries + 1):
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate)
            with open(output_path, "wb") as f:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
            duration = _get_mp3_duration(output_path)
            return duration
        except Exception:
            if attempt < retries:
                await asyncio.sleep(1.0)
            else:
                raise


def _get_mp3_duration(path: Path) -> float:
    """MP3 파일의 재생 시간을 초 단위로 반환한다."""
    import subprocess
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    result = subprocess.run(
        [ffmpeg, "-i", str(path), "-f", "null", "-"],
        capture_output=True, text=True, timeout=10,
    )
    # stderr에서 Duration 파싱
    for line in result.stderr.split("\n"):
        if "Duration:" in line:
            parts = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = parts.split(":")
            return float(h) * 3600 + float(m) * 60 + float(s)
    # fallback: 파일 크기 기반 추정 (128kbps mp3 기준)
    return path.stat().st_size / (128 * 1000 / 8)


def _mp3_to_numpy(path: Path) -> np.ndarray:
    """MP3를 numpy float64 배열로 변환한다 (모노, 44100Hz)."""
    import subprocess
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    result = subprocess.run(
        [
            ffmpeg, "-y", "-i", str(path),
            "-f", "s16le", "-acodec", "pcm_s16le",
            "-ar", str(SAMPLE_RATE), "-ac", "1",
            "pipe:1",
        ],
        capture_output=True, timeout=30,
    )
    if result.returncode != 0:
        return np.zeros(0, dtype=np.float64)

    samples = np.frombuffer(result.stdout, dtype=np.int16).astype(np.float64) / 32767.0
    return samples


async def synthesize_chat_messages(
    messages: list,
    participants: list[str],
    voice_map: dict[str, str] | None = None,
    rate: str = "+5%",
) -> list[dict]:
    """모든 채팅 메시지를 TTS로 합성한다.

    Args:
        messages: ChatMessage 리스트
        participants: 참가자 이름 리스트
        voice_map: 참가자->음성 매핑 (None이면 자동 배정)
        rate: TTS 속도

    Returns:
        각 메시지별 dict 리스트:
        [{"audio_path": Path, "duration": float, "samples": np.ndarray}, ...]
    """
    if voice_map is None:
        voice_map = assign_voices(participants)

    results = []
    tmp_dir = Path(tempfile.mkdtemp(prefix="chat_tts_"))

    for i, msg in enumerate(messages):
        voice = voice_map.get(msg.sender, KO_VOICE_POOL[0][0])
        audio_path = tmp_dir / f"msg_{i:03d}.mp3"

        try:
            duration = await _synthesize_message(msg.text, voice, audio_path, rate)
            samples = _mp3_to_numpy(audio_path)
            actual_duration = len(samples) / SAMPLE_RATE if len(samples) > 0 else duration
        except Exception:
            # 실패한 메시지는 빈 오디오로 처리
            actual_duration = max(len(msg.text) * 0.12, 1.0)
            samples = np.zeros(0, dtype=np.float64)

        results.append({
            "audio_path": audio_path,
            "duration": actual_duration,
            "samples": samples,
            "voice": voice,
        })

        # Rate limiting: Edge TTS 연속 호출 시 차단 방지
        await asyncio.sleep(0.3)

    return results


def synthesize_chat_sync(
    messages: list,
    participants: list[str],
    voice_map: dict[str, str] | None = None,
    rate: str = "+5%",
) -> list[dict]:
    """동기 진입점."""
    return asyncio.run(
        synthesize_chat_messages(messages, participants, voice_map, rate)
    )
