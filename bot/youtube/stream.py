"""YouTube ストリーム URL 解決（VC 再生用）"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

import yt_dlp

from .url_handler import normalize_youtube_url

logger = logging.getLogger(__name__)
STREAM_RESOLVE_TIMEOUT_SECONDS = 45
PO_TOKEN_PROVIDER_URL = os.getenv(
    "YOUTUBE_PO_TOKEN_PROVIDER_URL",
    "http://youtube-pot-provider:4416",
)

YDL_OPTS = {
    # YouTube may reject direct DASH media URLs with HTTP 403 even when
    # yt-dlp's HTTP headers are forwarded to FFmpeg. Prefer the 360p HLS
    # variant because it keeps normal audio quality while FFmpeg discards
    # the video track with ``-vn``. Keep lower-bandwidth HLS and direct audio
    # as fallbacks for videos that do not expose the preferred variant.
    "format": (
        "best[protocol^=m3u8][height<=360]/"
        "worst[protocol^=m3u8]/bestaudio/best"
    ),
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "extract_flat": False,
    "socket_timeout": 30,
    "retries": 3,
    "extractor_retries": 3,
    # web_safari provides HLS for many videos. Music/Art Track videos often
    # expose only direct media URLs, so prefer the token-backed Music client,
    # retain the embedded client as a public fallback, and keep mweb last.
    "extractor_args": {
        "youtube": {
            "player_client": [
                "web_safari",
                "web_music",
                "web_embedded",
                "mweb",
            ]
        },
        "youtubepot-bgutilhttp": {"base_url": [PO_TOKEN_PROVIDER_URL]},
    },
}


class StreamError(Exception):
    """ストリーム解決エラー"""

    def __init__(self, message: str, code: str = "unknown"):
        super().__init__(message)
        self.code = code


@dataclass
class StreamInfo:
    url: str
    title: str
    video_id: str
    duration: Optional[int] = None
    webpage_url: Optional[str] = None
    http_headers: Dict[str, str] = field(default_factory=dict)
    filesize: Optional[int] = None
    http_chunk_size: Optional[int] = None


def _classify_error(exc: Exception) -> StreamError:
    msg = str(exc).lower()
    if "private" in msg or "unavailable" in msg:
        return StreamError(
            "動画が利用できません（削除済みまたは非公開）", "unavailable"
        )
    if "age" in msg or "sign in" in msg:
        return StreamError("年齢制限などのため再生できません", "age_restricted")
    if "copyright" in msg or "blocked" in msg:
        return StreamError("著作権等の理由で再生できません", "blocked")
    return StreamError(
        "ストリーム取得に失敗しました。時間をおいて再試行してください。",
        "unknown",
    )


def _extract_stream(url: str) -> StreamInfo:
    normalized = normalize_youtube_url(url) or url
    try:
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(normalized, download=False)
    except Exception as e:
        raise _classify_error(e) from e

    if not info:
        raise StreamError("動画情報を取得できませんでした", "unavailable")

    selected_format = info
    stream_url = info.get("url")
    if not stream_url and info.get("formats"):
        for fmt in reversed(info["formats"]):
            if fmt.get("url") and fmt.get("acodec") != "none":
                stream_url = fmt["url"]
                selected_format = fmt
                break

    if not stream_url:
        raise StreamError("ストリーム URL を取得できませんでした", "no_stream")

    # Some token-protected formats are intentionally unavailable until the
    # timestamp supplied by YouTube (for example, while a pre-roll ad window
    # elapses). yt-dlp's downloader honors this field, but the bot hands the
    # resolved URL directly to FFmpeg, so mirror that wait here.
    available_at = selected_format.get("available_at") or info.get("available_at")
    if isinstance(available_at, (int, float)):
        wait_seconds = available_at - int(time.time())
        if wait_seconds > 0:
            logger.info(
                "Waiting %ss for YouTube stream availability", wait_seconds
            )
            time.sleep(wait_seconds)

    http_headers = {}
    for headers in (
        info.get("http_headers"),
        selected_format.get("http_headers"),
    ):
        if isinstance(headers, dict):
            http_headers.update(
                {
                    key: value
                    for key, value in headers.items()
                    if isinstance(key, str) and isinstance(value, str)
                }
            )

    downloader_options = selected_format.get("downloader_options") or {}
    filesize = selected_format.get("filesize")
    http_chunk_size = downloader_options.get("http_chunk_size")

    return StreamInfo(
        url=stream_url,
        title=info.get("title") or "Unknown Track",
        video_id=info.get("id") or "",
        duration=info.get("duration"),
        webpage_url=info.get("webpage_url") or normalized,
        http_headers=http_headers,
        filesize=filesize if isinstance(filesize, int) and filesize > 0 else None,
        http_chunk_size=(
            http_chunk_size
            if isinstance(http_chunk_size, int) and http_chunk_size > 0
            else None
        ),
    )


async def resolve_stream(url: str) -> StreamInfo:
    """非ブロッキングでストリーム情報を取得"""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_extract_stream, url),
            timeout=STREAM_RESOLVE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as e:
        raise StreamError("ストリーム取得がタイムアウトしました", "timeout") from e
