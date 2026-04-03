import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
AUDIO_DIR = OUTPUT_DIR / "audio"
VIDEO_DIR = OUTPUT_DIR / "video"
SRT_DIR = OUTPUT_DIR / "srt"
FINAL_DIR = OUTPUT_DIR / "final"

# LLM
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Pexels
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")

# YouTube
YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET", "")

# TTS
TTS_VOICE = "ko-KR-SunHiNeural"  # Edge TTS 한국어 여성 음성
TTS_RATE = "+0%"

# Video
SHORTS_WIDTH = 1080
SHORTS_HEIGHT = 1920
SHORTS_FPS = 30
SHORTS_MAX_DURATION = 60  # seconds

# DCInside
DC_HIT_GALLERY_ID = "hit"
DC_COLLECT_COUNT = 20  # 수집할 게시글 수
