"""채팅 UI 프레임들을 MP4 영상으로 합성한다.

Pillow 프레임 시퀀스 + 캐릭터 TTS + BGM(볼륨 덕킹) + SFX(메시지 알림음) -> 최종 MP4.
"""

import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np
import imageio_ffmpeg

from config.settings import FINAL_DIR, SHORTS_FPS
from src.editor.chat_renderer import (
    ChatScript, load_chat_script, render_frames, render_frames_to_dir, build_timeline,
)
from src.utils.logger import setup_logger

log = setup_logger("chat_composer")

FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()

# 에셋 경로
ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"
DEFAULT_BGM = ASSETS_DIR / "bgm" / "lofi_pad.wav"
SFX_MESSAGE = ASSETS_DIR / "sfx" / "message_pop.wav"
SFX_RESULT = ASSETS_DIR / "sfx" / "result_boom.wav"

SAMPLE_RATE = 44100


def _load_wav(path: Path) -> np.ndarray:
    """WAV 파일을 numpy 배열로 로드한다."""
    with wave.open(str(path), 'r') as wf:
        frames = wf.readframes(wf.getnframes())
        samples = np.frombuffer(frames, dtype=np.int16).astype(np.float64) / 32767.0
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


def _build_sfx_track(
    timeline: list[tuple[int, int]],
    result_frame: int,
    total_frames: int,
    fps: int,
    has_result: bool = True,
) -> np.ndarray:
    """메시지 등장 타이밍에 맞춰 SFX 오디오 트랙을 생성한다."""
    duration = total_frames / fps
    total_samples = int(duration * SAMPLE_RATE)
    track = np.zeros(total_samples, dtype=np.float64)

    msg_sfx = _load_wav(SFX_MESSAGE) if SFX_MESSAGE.exists() else None
    result_sfx = _load_wav(SFX_RESULT) if SFX_RESULT.exists() else None

    for _, msg_appear in timeline:
        if msg_sfx is not None:
            sample_pos = int(msg_appear / fps * SAMPLE_RATE)
            _mix_at(track, msg_sfx, sample_pos)

    if result_sfx is not None and has_result:
        sample_pos = int(result_frame / fps * SAMPLE_RATE)
        _mix_at(track, result_sfx, sample_pos)

    return track


def _build_tts_track(
    timeline: list[tuple[int, int]],
    tts_results: list[dict],
    total_frames: int,
    fps: int,
) -> np.ndarray:
    """TTS 음성을 타임라인에 맞춰 오디오 트랙으로 합성한다."""
    duration = total_frames / fps
    total_samples = int(duration * SAMPLE_RATE)
    track = np.zeros(total_samples, dtype=np.float64)

    for i, (_, msg_appear) in enumerate(timeline):
        if i >= len(tts_results):
            break
        samples = tts_results[i].get("samples")
        if samples is not None and len(samples) > 0:
            sample_pos = int(msg_appear / fps * SAMPLE_RATE)
            _mix_at(track, samples, sample_pos)

    return track


def compose_chat(
    script: ChatScript | Path,
    bgm_path: Path | None = None,
    output_name: str = "chat_short",
    fps: int = SHORTS_FPS,
    bgm_volume: float = 0.12,
    sfx_volume: float = 0.6,
    tts_volume: float = 1.0,
    enable_tts: bool = True,
    enable_effects: bool = True,
) -> Path:
    """채팅 대본을 MP4 영상으로 생성한다.

    Args:
        script: ChatScript 객체 또는 JSON 파일 경로
        bgm_path: BGM 파일 (None이면 기본 BGM 사용)
        output_name: 출력 파일명 (확장자 제외)
        fps: 프레임 레이트
        bgm_volume: BGM 볼륨 (0.0~1.0)
        sfx_volume: 효과음 볼륨 (0.0~1.0)
        tts_volume: TTS 음성 볼륨 (0.0~1.0)
        enable_tts: 캐릭터 TTS 활성화 여부
        enable_effects: 시각 효과 (줌/흔들림) 활성화 여부

    Returns:
        최종 영상 파일 경로
    """
    if isinstance(script, Path):
        script = load_chat_script(script)

    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    output_path = FINAL_DIR / f"{output_name}.mp4"

    # ── TTS 합성 (캐릭터별 음성) ──
    tts_results = None
    msg_durations = None

    if enable_tts:
        try:
            from src.tts.chat_tts import synthesize_chat_sync
            log.info("  [TTS] 캐릭터별 음성 합성 중...")
            tts_results = synthesize_chat_sync(
                script.messages, script.participants
            )
            msg_durations = [r["duration"] for r in tts_results]
            voices_used = set(r["voice"] for r in tts_results)
            log.info(f"  [TTS] 음성 {len(voices_used)}종 사용: {voices_used}")
        except Exception as e:
            log.warning(f"  [TTS] 합성 실패, BGM+SFX만 사용: {e}")
            tts_results = None
            msg_durations = None

    # ── 타임라인 계산 (프레임 렌더링 + 오디오 믹싱 공용) ──
    timeline, result_frame, total_frames = build_timeline(
        script, fps, msg_durations,
    )
    duration = total_frames / fps

    # ── 오디오 트랙 생성 ──
    total_samples = int(duration * SAMPLE_RATE)
    audio_mix = np.zeros(total_samples, dtype=np.float64)

    # 1) BGM 트랙
    if bgm_path is None:
        bgm_path = DEFAULT_BGM
    if bgm_path.exists():
        bgm_data = _load_wav(bgm_path)
        if len(bgm_data) < total_samples:
            repeats = (total_samples // len(bgm_data)) + 1
            bgm_data = np.tile(bgm_data, repeats)
        bgm_data = bgm_data[:total_samples]
        # 페이드 인/아웃
        fade_samples = int(SAMPLE_RATE * 1.5)
        if fade_samples > 0 and len(bgm_data) > fade_samples * 2:
            bgm_data[:fade_samples] *= np.linspace(0, 1, fade_samples)
            bgm_data[-fade_samples:] *= np.linspace(1, 0, fade_samples)

        # TTS가 있을 때 BGM 볼륨 더 낮추기 (덕킹)
        effective_bgm_vol = bgm_volume * 0.6 if tts_results else bgm_volume
        audio_mix += bgm_data * effective_bgm_vol

    # 2) SFX 트랙
    sfx_track = _build_sfx_track(
        timeline, result_frame, total_frames, fps,
        has_result=bool(script.result_text),
    )
    if len(sfx_track) < total_samples:
        sfx_track = np.pad(sfx_track, (0, total_samples - len(sfx_track)))
    else:
        sfx_track = sfx_track[:total_samples]
    audio_mix += sfx_track * sfx_volume

    # 3) TTS 트랙 (캐릭터 음성)
    if tts_results:
        tts_track = _build_tts_track(timeline, tts_results, total_frames, fps)
        if len(tts_track) < total_samples:
            tts_track = np.pad(tts_track, (0, total_samples - len(tts_track)))
        else:
            tts_track = tts_track[:total_samples]
        audio_mix += tts_track * tts_volume

    # ── 프레임 렌더링 (디스크 직접 저장, 메모리 절약) + 오디오 -> MP4 ──
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        log.info(f"  [render] {total_frames} frames ({duration:.1f}s) rendering...")
        rendered = render_frames_to_dir(
            script, tmpdir_path, fps=fps,
            msg_durations=msg_durations, enable_effects=enable_effects,
        )
        log.info(f"  [render] {rendered} frames saved")

        audio_path = tmpdir_path / "audio_mix.wav"
        _save_wav(audio_path, audio_mix)

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
            log.error(f"FFmpeg stderr: {result.stderr[-500:]}")
            raise subprocess.CalledProcessError(result.returncode, cmd)

    return output_path
