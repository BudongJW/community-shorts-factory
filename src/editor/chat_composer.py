"""채팅 UI 프레임들을 MP4 영상으로 합성한다.

Pillow 프레임 시퀀스 + BGM(볼륨 덕킹) + SFX(메시지 알림음) -> 최종 MP4.
"""

import subprocess
import tempfile
import wave
import struct
from pathlib import Path

import numpy as np
import imageio_ffmpeg

from config.settings import FINAL_DIR, SHORTS_FPS
from src.editor.chat_renderer import ChatScript, load_chat_script, render_frames

FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()

# 에셋 경로
ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"
DEFAULT_BGM = ASSETS_DIR / "bgm" / "lofi_pad.wav"
SFX_MESSAGE = ASSETS_DIR / "sfx" / "message_pop.wav"
SFX_RESULT = ASSETS_DIR / "sfx" / "result_boom.wav"

SAMPLE_RATE = 44100


def _build_sfx_track(
    script: ChatScript,
    total_frames: int,
    fps: int,
    msg_appear_sec: float = 1.5,
    typing_sec: float = 0.8,
    result_delay_sec: float = 1.0,
) -> np.ndarray:
    """메시지 등장 타이밍에 맞춰 SFX 오디오 트랙을 생성한다."""
    duration = total_frames / fps
    total_samples = int(duration * SAMPLE_RATE)
    track = np.zeros(total_samples, dtype=np.float64)

    # SFX 파일 로드
    msg_sfx = _load_wav(SFX_MESSAGE) if SFX_MESSAGE.exists() else None
    result_sfx = _load_wav(SFX_RESULT) if SFX_RESULT.exists() else None

    # 타임라인 계산 (chat_renderer와 동일 로직)
    current_frame = int(1.0 * fps)
    for i in range(len(script.messages)):
        msg_appear_frame = current_frame + int(typing_sec * fps)

        if msg_sfx is not None:
            sample_pos = int(msg_appear_frame / fps * SAMPLE_RATE)
            _mix_at(track, msg_sfx, sample_pos)

        current_frame = msg_appear_frame + int(msg_appear_sec * fps)

    # 결과 등장음
    result_frame = current_frame + int(result_delay_sec * fps)
    if result_sfx is not None and script.result_text:
        sample_pos = int(result_frame / fps * SAMPLE_RATE)
        _mix_at(track, result_sfx, sample_pos)

    return track


def _load_wav(path: Path) -> np.ndarray:
    """WAV 파일을 numpy 배열로 로드한다."""
    with wave.open(str(path), 'r') as wf:
        frames = wf.readframes(wf.getnframes())
        samples = np.frombuffer(frames, dtype=np.int16).astype(np.float64) / 32767.0
        # 스테레오면 모노로 변환
        if wf.getnchannels() == 2:
            samples = samples.reshape(-1, 2).mean(axis=1)
    return samples


def _mix_at(track: np.ndarray, sfx: np.ndarray, position: int):
    """트랙의 특정 위치에 SFX를 믹싱한다."""
    end = min(position + len(sfx), len(track))
    length = end - position
    if length > 0 and position >= 0:
        track[position:end] += sfx[:length]


def _save_wav(path: Path, data: np.ndarray, sr: int = SAMPLE_RATE):
    """numpy 배열을 WAV로 저장한다."""
    data = np.clip(data, -1.0, 1.0)
    samples = (data * 32767).astype(np.int16)
    with wave.open(str(path), 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(samples.tobytes())


def compose_chat(
    script: ChatScript | Path,
    bgm_path: Path | None = None,
    output_name: str = "chat_short",
    fps: int = SHORTS_FPS,
    bgm_volume: float = 0.15,
    sfx_volume: float = 0.7,
) -> Path:
    """채팅 대본을 MP4 영상으로 생성한다.

    Args:
        script: ChatScript 객체 또는 JSON 파일 경로
        bgm_path: BGM 파일 (None이면 기본 BGM 사용)
        output_name: 출력 파일명 (확장자 제외)
        fps: 프레임 레이트
        bgm_volume: BGM 볼륨 (0.0~1.0)
        sfx_volume: 효과음 볼륨 (0.0~1.0)

    Returns:
        최종 영상 파일 경로
    """
    if isinstance(script, Path):
        script = load_chat_script(script)

    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    output_path = FINAL_DIR / f"{output_name}.mp4"

    # 프레임 렌더링
    frames = render_frames(script, fps=fps)
    total_frames = len(frames)
    duration = total_frames / fps

    # 오디오 트랙 생성
    total_samples = int(duration * SAMPLE_RATE)
    audio_mix = np.zeros(total_samples, dtype=np.float64)

    # 1) BGM 트랙
    if bgm_path is None:
        bgm_path = DEFAULT_BGM
    if bgm_path.exists():
        bgm_data = _load_wav(bgm_path)
        # BGM을 영상 길이에 맞게 루핑
        if len(bgm_data) < total_samples:
            repeats = (total_samples // len(bgm_data)) + 1
            bgm_data = np.tile(bgm_data, repeats)
        bgm_data = bgm_data[:total_samples]
        # 페이드 인/아웃
        fade_samples = int(SAMPLE_RATE * 1.5)
        bgm_data[:fade_samples] *= np.linspace(0, 1, fade_samples)
        bgm_data[-fade_samples:] *= np.linspace(1, 0, fade_samples)
        audio_mix += bgm_data * bgm_volume

    # 2) SFX 트랙
    sfx_track = _build_sfx_track(script, total_frames, fps)
    if len(sfx_track) < total_samples:
        sfx_track = np.pad(sfx_track, (0, total_samples - len(sfx_track)))
    else:
        sfx_track = sfx_track[:total_samples]
    audio_mix += sfx_track * sfx_volume

    # 프레임을 임시 디렉토리에 PNG로 저장 + 오디오 WAV
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        for i, frame in enumerate(frames):
            frame.save(tmpdir_path / f"frame_{i:06d}.png")

        # 오디오 WAV 저장
        audio_path = tmpdir_path / "audio_mix.wav"
        _save_wav(audio_path, audio_mix)

        # FFmpeg: 프레임 + 오디오 -> MP4
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

        subprocess.run(cmd, check=True, capture_output=True, text=True)

    return output_path
