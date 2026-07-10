"""사실적 공포(폐가 탐험/일상 괴담) 쇼츠 합성기.

AI 생성 이미지 시퀀스에
  - 전진 줌(walk) + 핸드헬드 흔들림
  - 손전등 비네트(1인칭 POV/게임 느낌)
  - 게임 HUD 오버레이(크로스헤어, 코너 프레임, REC, 조사 프롬프트)
  - 후반부로 갈수록 어두워지고 붉게 물드는 긴장 고조
  - 마지막 점프스케어(급작스런 리빌 + 화면 흔들림 + 붉은/흰 플래시)
를 적용하고, numpy로 합성한 공포 앰비언트 + 점프스케어 굉음을 얹어
나레이션 없는 세로 쇼츠를 생성한다.
"""

import math
import platform
import random
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    import imageio_ffmpeg
except ImportError:  # 시스템 ffmpeg만 있는 환경(로컬 등) 대비
    imageio_ffmpeg = None

from config.settings import SHORTS_WIDTH, SHORTS_HEIGHT, SHORTS_FPS, FINAL_DIR
from src.utils.logger import setup_logger

log = setup_logger("horror_composer")

FFMPEG_BIN = (
    shutil.which("ffmpeg")
    or (imageio_ffmpeg.get_ffmpeg_exe() if imageio_ffmpeg else "ffmpeg")
)

W, H = SHORTS_WIDTH, SHORTS_HEIGHT

# 시작 훅(첫 1.2초). 나레이션이 없으므로 소리/끝까지 보기 유도로 완주율 확보.
HORROR_HOOKS = [
    "소리 켜고 보세요",
    "끝까지 보세요",
    "혼자 보지 마세요",
    "이어폰 필수",
    "마지막에 조심",
    "무서우면 멈춰요",
]
HOOK_DURATION = 1.4


def _find_korean_font(size: int) -> ImageFont.FreeTypeFont:
    """한글 지원 bold 폰트 로드 (Windows 맑은고딕 / Linux 나눔고딕)."""
    candidates = []
    if platform.system() == "Windows":
        candidates = ["C:/Windows/Fonts/malgunbd.ttf", "C:/Windows/Fonts/malgun.ttf"]
    candidates += [
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    ]
    for p in candidates:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


# ── 손전등 비네트 마스크 (한 번만 계산) ──
def _build_flashlight_mask() -> np.ndarray:
    """중앙 살짝 위를 밝게, 가장자리는 어둡게 하는 float32 (H,W,1) 마스크."""
    ys = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    xs = np.linspace(0, 1, W, dtype=np.float32)[None, :]
    cx, cy = 0.5, 0.42  # 시선이 닿는 지점 (약간 위)
    # 세로가 길므로 y거리를 화면비로 보정
    dist = np.sqrt((xs - cx) ** 2 + ((ys - cy) * (H / W)) ** 2)
    # 0.0(중심)~ 큰 값(가장자리). 부드러운 감쇠.
    mask = np.clip(1.0 - (dist / 0.75) ** 1.6, 0.0, 1.0)
    # 최소 밝기 바닥(완전 검정 방지) + 손전등 코어
    mask = 0.12 + 0.88 * mask
    return mask[:, :, None].astype(np.float32)


_FLASHLIGHT = _build_flashlight_mask()


def _build_hud() -> np.ndarray:
    """게임 POV HUD 오버레이 (RGBA uint8). 크로스헤어/코너/REC/조사 프롬프트."""
    hud = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(hud)
    green = (120, 255, 120, 210)
    white = (235, 235, 235, 200)

    # 중앙 크로스헤어
    cx, cy = W // 2, int(H * 0.46)
    r, gap = 26, 9
    d.line([(cx - r, cy), (cx - gap, cy)], fill=white, width=3)
    d.line([(cx + gap, cy), (cx + r, cy)], fill=white, width=3)
    d.line([(cx, cy - r), (cx, cy - gap)], fill=white, width=3)
    d.line([(cx, cy + gap), (cx, cy + r)], fill=white, width=3)
    d.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=white)

    # 코너 프레임 브래킷
    m, L, w = 46, 70, 4
    for (ax, ay, hx, vy) in [
        (m, m, 1, 1), (W - m, m, -1, 1), (m, H - m, 1, -1), (W - m, H - m, -1, -1),
    ]:
        d.line([(ax, ay), (ax + hx * L, ay)], fill=green, width=w)
        d.line([(ax, ay), (ax, ay + vy * L)], fill=green, width=w)

    # REC 표시 (좌상단)
    d.ellipse([m + 10, m + 22, m + 34, m + 46], fill=(230, 40, 40, 230))
    rec_font = _find_korean_font(38)
    d.text((m + 44, m + 20), "REC", font=rec_font, fill=(235, 235, 235, 230))

    # 하단 조사 프롬프트 (게임 상호작용 느낌)
    pf = _find_korean_font(46)
    prompt = "▶  살펴보기   [ E ]"
    bbox = d.textbbox((0, 0), prompt, font=pf)
    tw = bbox[2] - bbox[0]
    px = (W - tw) // 2
    py = int(H * 0.86)
    for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
        d.text((px + dx, py + dy), prompt, font=pf, fill=(0, 0, 0, 200))
    d.text((px, py), prompt, font=pf, fill=(235, 235, 235, 215))

    return np.asarray(hud, dtype=np.uint8)


_HUD = _build_hud()


def _alpha_composite_np(base: np.ndarray, overlay_rgba: np.ndarray) -> np.ndarray:
    """base(H,W,3 uint8) 위에 overlay_rgba(H,W,4 uint8)를 알파 합성."""
    a = overlay_rgba[:, :, 3:4].astype(np.float32) / 255.0
    out = base.astype(np.float32) * (1 - a) + overlay_rgba[:, :, :3].astype(np.float32) * a
    return np.clip(out, 0, 255).astype(np.uint8)


def _walk_frame(
    img: np.ndarray,
    progress: float,
    tension: float,
    zoom_lo: float = 1.06,
    zoom_hi: float = 1.30,
) -> np.ndarray:
    """전진 줌(walk) + 핸드헬드 흔들림 + 손전등 + 긴장 고조 톤을 적용한 프레임.

    Args:
        img: 원본 (H,W,3) uint8
        progress: 장면 내 진행도 0~1 (줌 정도)
        tension: 영상 전체 진행도 0~1 (어두움/붉은기/그레인 세기)
    """
    ih, iw = img.shape[:2]
    scale = zoom_lo + (zoom_hi - zoom_lo) * progress
    cw, ch = int(iw / scale), int(ih / scale)

    # 핸드헬드 흔들림: 긴장이 높을수록 진폭 증가
    amp = 6 + 26 * tension
    dx = int(math.sin(progress * math.pi * 6) * amp + random.uniform(-amp, amp) * 0.4)
    dy = int(math.cos(progress * math.pi * 5) * amp + random.uniform(-amp, amp) * 0.4)

    left = (iw - cw) // 2 + dx
    top = (ih - ch) // 2 + dy
    left = max(0, min(iw - cw, left))
    top = max(0, min(ih - ch, top))

    crop = img[top:top + ch, left:left + cw]
    frame = np.asarray(
        Image.fromarray(crop).resize((W, H), Image.BILINEAR), dtype=np.float32
    )

    # 손전등 비네트
    frame *= _FLASHLIGHT[:, :, 0][:, :, None]

    # 긴장 고조: 전체 어두워지고 + 붉은기 + 대비 상승
    darken = 1.0 - 0.30 * tension
    frame *= darken
    if tension > 0.05:
        red = np.array([28, -10, -10], dtype=np.float32) * tension
        frame += red

    # 필름 그레인 (긴장 높을수록 강함).
    # 매 프레임 독립 노이즈는 x264 압축을 방해해 용량이 폭증하므로 강도를 억제한다.
    grain_strength = 2.0 + 7.0 * tension
    noise = np.random.normal(0, grain_strength, (H, W, 1)).astype(np.float32)
    frame += noise

    return np.clip(frame, 0, 255).astype(np.uint8)


def _draw_hook(frame: np.ndarray, text: str, alpha: float) -> np.ndarray:
    """상단에 한글 훅 텍스트를 그린다."""
    if alpha <= 0:
        return frame
    img = Image.fromarray(frame).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    font = _find_korean_font(84)
    bbox = d.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (W - tw) // 2 - bbox[0]
    y = int(H * 0.16)
    a = int(alpha * 255)
    for dx, dy in [(-4, 0), (4, 0), (0, -4), (0, 4), (-3, -3), (3, 3), (-3, 3), (3, -3)]:
        d.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, a))
    d.text((x, y), text, font=font, fill=(240, 30, 30, a))  # 핏빛 레드
    out = Image.alpha_composite(img, overlay).convert("RGB")
    return np.asarray(out, dtype=np.uint8)


def _synthesize_audio(total_sec: float, scare_at: float, out_path: Path):
    """공포 앰비언트 + 라이저 + 점프스케어 굉음을 numpy로 합성해 WAV로 저장."""
    sr = 44100
    n = int(total_sec * sr)
    t = np.linspace(0, total_sec, n, endpoint=False)

    # 저역 드론 (55Hz + 살짝 디튠) — 전체 구간, scare로 갈수록 커짐
    env = np.clip(t / max(scare_at, 0.1), 0.0, 1.0) ** 1.5  # 0→1 상승
    drone = (
        np.sin(2 * math.pi * 55 * t) * 0.5
        + np.sin(2 * math.pi * 55.4 * t) * 0.4
        + np.sin(2 * math.pi * 110 * t) * 0.2
    )
    audio = drone * (0.10 + 0.28 * env)

    # 저역 브라운 노이즈 바람소리
    wind = np.cumsum(np.random.normal(0, 1, n))
    wind = wind / (np.max(np.abs(wind)) + 1e-9)
    audio += wind * (0.05 + 0.15 * env)

    # scare 직전 2초 라이저 (상승 스윕 + 노이즈 증가)
    riser_len = min(2.0, scare_at)
    r0 = int((scare_at - riser_len) * sr)
    r1 = int(scare_at * sr)
    if r1 > r0:
        rt = np.linspace(0, 1, r1 - r0)
        freq = 180 + 900 * rt
        phase = np.cumsum(2 * math.pi * freq / sr)
        audio[r0:r1] += np.sin(phase) * (0.15 + 0.5 * rt)
        audio[r0:r1] += np.random.normal(0, 1, r1 - r0) * (0.1 + 0.4 * rt)

    # 점프스케어 굉음: 화이트노이즈 버스트 + 불협 클러스터, 빠른 감쇠
    s0 = int(scare_at * sr)
    dur = min(0.9, total_sec - scare_at)
    sn = int(dur * sr)
    if sn > 0:
        st = np.linspace(0, dur, sn)
        decay = np.exp(-st * 5.0)
        stab = np.random.normal(0, 1, sn) * 0.9
        for f in (98, 233, 466, 622):  # 불협 저역 클러스터
            stab += np.sin(2 * math.pi * f * st) * 0.3
        audio[s0:s0 + sn] += stab * decay * 1.6

    # 노멀라이즈 + 클리핑 방지
    peak = np.max(np.abs(audio)) + 1e-9
    audio = (audio / peak) * 0.95
    pcm = (audio * 32767).astype(np.int16)

    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def compose_horror_short(
    build_paths: list[Path],
    scare_path: Path | None,
    output_name: str = "horror",
    target_duration: float = 22.0,
    hook: str | None = None,
) -> Path:
    """공포 이미지 시퀀스를 점프스케어 쇼츠로 합성한다.

    Args:
        build_paths: 빌드업 장면 이미지 경로 (순서 유지 = 탐험 진행)
        scare_path: 마지막 점프스케어 이미지 (None이면 마지막 빌드업 재활용)
        output_name: 출력 파일명
        target_duration: 목표 총 길이(초). 점프스케어 포함.
        hook: 시작 훅 텍스트. None이면 랜덤.

    Returns:
        최종 영상 파일 경로
    """
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    output_path = FINAL_DIR / f"{output_name}.mp4"

    if not build_paths:
        raise ValueError("빌드업 이미지가 없습니다")
    if scare_path is None:
        scare_path = build_paths[-1]

    fps = SHORTS_FPS
    scare_sec = 0.9
    build_total = max(4.0, target_duration - scare_sec)
    sec_per_scene = build_total / len(build_paths)
    frames_per_scene = int(sec_per_scene * fps)
    scare_frames = int(scare_sec * fps)

    total_frames = frames_per_scene * len(build_paths) + scare_frames
    total_sec = total_frames / fps
    scare_at = (frames_per_scene * len(build_paths)) / fps

    log.info(
        f"  {len(build_paths)} scenes x {sec_per_scene:.1f}s + scare {scare_sec}s "
        f"= {total_sec:.1f}s"
    )

    if hook is None:
        hook = random.choice(HORROR_HOOKS)
    hook_end_frame = int(HOOK_DURATION * fps)

    # 이미지 로드
    def _load(p: Path) -> np.ndarray:
        im = Image.open(p).convert("RGB")
        if im.size != (W, H):
            im = im.resize((W, H), Image.LANCZOS)
        return np.asarray(im, dtype=np.uint8)

    scene_imgs = [_load(p) for p in build_paths]
    scare_img = _load(scare_path)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        frame_idx = 0

        # ── 빌드업 장면 ──
        for si, img in enumerate(scene_imgs):
            for f in range(frames_per_scene):
                prog = f / max(frames_per_scene - 1, 1)
                tension = frame_idx / max(total_frames - scare_frames, 1)
                frame = _walk_frame(img, prog, tension)

                # 장면 전환 페이드 (앞 6프레임 어둠에서 등장)
                if f < 6 and si > 0:
                    frame = (frame.astype(np.float32) * (f / 6)).astype(np.uint8)

                # HUD 합성
                frame = _alpha_composite_np(frame, _HUD)

                # 시작 훅
                if frame_idx < hook_end_frame:
                    p = frame_idx / hook_end_frame
                    a = 1.0 if p < 0.7 else max(0.0, 1.0 - (p - 0.7) / 0.3)
                    frame = _draw_hook(frame, hook, a)

                Image.fromarray(frame).save(tmp / f"frame_{frame_idx:06d}.png")
                frame_idx += 1

        # ── 점프스케어 ──
        for f in range(scare_frames):
            # 급작스런 확대 펀치 + 격한 흔들림
            scale = 1.0 + 0.18 * (f / max(scare_frames - 1, 1))
            ih, iw = scare_img.shape[:2]
            cw, ch = int(iw / scale), int(ih / scale)
            amp = 40
            dx = random.randint(-amp, amp)
            dy = random.randint(-amp, amp)
            left = max(0, min(iw - cw, (iw - cw) // 2 + dx))
            top = max(0, min(ih - ch, (ih - ch) // 2 + dy))
            crop = scare_img[top:top + ch, left:left + cw]
            frame = np.asarray(
                Image.fromarray(crop).resize((W, H), Image.BILINEAR), dtype=np.float32
            )

            # 첫 3프레임 흰 플래시, 이후 간헐 붉은 플래시
            if f < 3:
                frame = frame * 0.3 + np.array([255, 255, 255], dtype=np.float32) * 0.7
            elif f % 4 == 0:
                frame = frame * 0.6 + np.array([180, 0, 0], dtype=np.float32) * 0.4

            frame += np.random.normal(0, 8, (H, W, 1)).astype(np.float32)
            frame = np.clip(frame, 0, 255).astype(np.uint8)
            Image.fromarray(frame).save(tmp / f"frame_{frame_idx:06d}.png")
            frame_idx += 1

        log.info(f"  {frame_idx} frames rendered")

        # ── 오디오 합성 ──
        audio_path = tmp / "audio.wav"
        _synthesize_audio(total_sec, scare_at, audio_path)

        # ── FFmpeg 합성 ──
        input_pattern = str(tmp / "frame_%06d.png").replace("\\", "/")
        cmd = [
            FFMPEG_BIN, "-y",
            "-framerate", str(fps), "-i", input_pattern,
            "-i", str(audio_path),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "fast", "-crf", "25",
            "-maxrate", "6M", "-bufsize", "12M",  # 그레인으로 인한 용량 폭증 방지 상한
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log.error(f"FFmpeg error: {result.stderr[-500:]}")
            raise subprocess.CalledProcessError(result.returncode, cmd)

    size_kb = output_path.stat().st_size // 1024
    log.info(f"  -> {output_path.name} ({size_kb}KB)")
    return output_path
