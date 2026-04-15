"""채팅 UI 프레임들을 MP4 영상으로 합성한다.

Pillow 프레임 시퀀스 + (선택적) BGM -> 최종 MP4.
"""

import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg

from config.settings import FINAL_DIR, SHORTS_FPS
from src.editor.chat_renderer import ChatScript, load_chat_script, render_frames

FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()


def compose_chat(
    script: ChatScript | Path,
    bgm_path: Path | None = None,
    output_name: str = "chat_short",
    fps: int = SHORTS_FPS,
) -> Path:
    """채팅 대본을 MP4 영상으로 생성한다.

    Args:
        script: ChatScript 객체 또는 JSON 파일 경로
        bgm_path: BGM 파일 (없으면 무음)
        output_name: 출력 파일명 (확장자 제외)
        fps: 프레임 레이트

    Returns:
        최종 영상 파일 경로
    """
    if isinstance(script, Path):
        script = load_chat_script(script)

    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    output_path = FINAL_DIR / f"{output_name}.mp4"

    # 프레임 렌더링
    frames = render_frames(script, fps=fps)

    # 프레임을 임시 디렉토리에 PNG로 저장
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        for i, frame in enumerate(frames):
            frame.save(tmpdir_path / f"frame_{i:06d}.png")

        # FFmpeg로 프레임 -> MP4 변환
        input_pattern = str(tmpdir_path / "frame_%06d.png").replace("\\", "/")

        if bgm_path and bgm_path.exists():
            cmd = [
                FFMPEG_BIN, "-y",
                "-framerate", str(fps),
                "-i", input_pattern,
                "-i", str(bgm_path),
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                str(output_path),
            ]
        else:
            cmd = [
                FFMPEG_BIN, "-y",
                "-framerate", str(fps),
                "-i", input_pattern,
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-pix_fmt", "yuv420p",
                str(output_path),
            ]

        subprocess.run(cmd, check=True, capture_output=True, text=True)

    return output_path
