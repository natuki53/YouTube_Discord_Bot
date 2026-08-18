"""YouTube ストリーム URL 解決（VC 再生用）"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

import yt_dlp

from .url_handler import normalize_youtube_url

logger = logging.getLogger(__name__)
STREAM_RESOLVE_TIMEOUT_SECONDS = 45

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

    return StreamInfo(
        url=stream_url,
        title=info.get("title") or "Unknown Track",
        video_id=info.get("id") or "",
        duration=info.get("duration"),
        webpage_url=info.get("webpage_url") or normalized,
        http_headers=http_headers,
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
