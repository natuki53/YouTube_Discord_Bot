"""YouTube ストリーム URL 解決（VC 再生用）"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

import yt_dlp

from .url_handler import normalize_youtube_url

logger = logging.getLogger(__name__)

YDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "extract_flat": False,
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


def _classify_error(exc: Exception) -> StreamError:
    msg = str(exc).lower()
    if "private" in msg or "unavailable" in msg:
        return StreamError("動画が利用できません（削除済みまたは非公開）", "unavailable")
    if "age" in msg or "sign in" in msg:
        return StreamError("年齢制限などのため再生できません", "age_restricted")
    if "copyright" in msg or "blocked" in msg:
        return StreamError("著作権等の理由で再生できません", "blocked")
    return StreamError(f"ストリーム取得に失敗しました: {exc}", "unknown")


def _extract_stream(url: str) -> StreamInfo:
    normalized = normalize_youtube_url(url) or url
    try:
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(normalized, download=False)
    except Exception as e:
        raise _classify_error(e) from e

    if not info:
        raise StreamError("動画情報を取得できませんでした", "unavailable")

    stream_url = info.get("url")
    if not stream_url and info.get("formats"):
        for fmt in reversed(info["formats"]):
            if fmt.get("url") and fmt.get("acodec") != "none":
                stream_url = fmt["url"]
                break

    if not stream_url:
        raise StreamError("ストリーム URL を取得できませんでした", "no_stream")

    return StreamInfo(
        url=stream_url,
        title=info.get("title") or "Unknown Track",
        video_id=info.get("id") or "",
        duration=info.get("duration"),
        webpage_url=info.get("webpage_url") or normalized,
    )


async def resolve_stream(url: str) -> StreamInfo:
    """非ブロッキングでストリーム情報を取得"""
    return await asyncio.to_thread(_extract_stream, url)
