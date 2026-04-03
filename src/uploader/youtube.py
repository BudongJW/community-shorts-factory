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
    """YouTube API 서비스 객체를 생성한다."""
    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
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
