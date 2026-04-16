"""YouTube Data API v3를 통한 영상 업로드."""

import os
from pathlib import Path

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_PATH = Path(__file__).parent.parent.parent / "config" / "youtube_token.json"
CLIENT_SECRET_PATH = Path(__file__).parent.parent.parent / "config" / "client_secret.json"


def get_youtube_service():
    """YouTube API 서비스 객체를 생성한다.

    토큰 소스 우선순위:
    1. YOUTUBE_TOKEN_JSON 환경변수 (GitHub Actions용, JSON 문자열)
    2. config/youtube_token.json 파일 (로컬 개발용)
    3. OAuth 브라우저 플로우 (최초 인증용)
    """
    creds = None

    # 1) 환경변수에서 토큰 로드 (CI/CD용)
    token_json = os.getenv("YOUTUBE_TOKEN_JSON")
    if token_json:
        import json
        creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)

    # 2) 파일에서 토큰 로드 (로컬용)
    if not creds and TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # 갱신된 토큰 저장 (로컬 환경에서만)
            if not token_json:
                TOKEN_PATH.write_text(creds.to_json())
        else:
            # CI 환경에서는 브라우저 플로우 불가
            if os.getenv("CI"):
                raise RuntimeError(
                    "YouTube 토큰이 만료되었거나 없습니다. "
                    "로컬에서 인증 후 YOUTUBE_TOKEN_JSON 시크릿을 업데이트하세요."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
            TOKEN_PATH.write_text(creds.to_json())

    return build("youtube", "v3", credentials=creds)


def upload(
    video_path: Path,
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    category_id: str = "22",  # People & Blogs
) -> str:
    """YouTube에 영상을 업로드한다.

    Args:
        video_path: 업로드할 MP4 파일 경로
        title: 영상 제목
        description: 영상 설명
        tags: 태그 리스트
        category_id: YouTube 카테고리 ID

    Returns:
        업로드된 영상의 video ID
    """
    youtube = get_youtube_service()

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = request.execute()
    video_id = response["id"]
    print(f"Upload complete: https://www.youtube.com/shorts/{video_id}")
    return video_id
