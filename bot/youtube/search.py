"""YouTube 検索（曲名 → 動画 URL）"""

import logging
from dataclasses import dataclass

import yt_dlp

from .url_handler import is_playlist_url, normalize_youtube_url, validate_youtube_url

logger = logging.getLogger(__name__)

SEARCH_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "extract_flat": True,
    "skip_download": True,
    "socket_timeout": 30,
    "retries": 3,
    "extractor_retries": 3,
}


class SearchError(Exception):
    """検索失敗"""

    def __init__(self, message: str):
        super().__init__(message)


@dataclass
class PlayTarget:
    """再生対象（URL + 表示用タイトル）"""

    url: str
    display_title: str


def _ensure_https(url: str) -> str:
    text = url.strip()
    if not text.startswith(("http://", "https://")):
        return f"https://{text.lstrip('/')}"
    return text


def looks_like_youtube_url(text: str) -> bool:
    """URL らしい文字列か（https 省略含む）"""
    text = _ensure_https(text.strip()).lower()
    return (
        validate_youtube_url(text)
        or "youtube.com/watch" in text
        or "youtu.be/" in text
        or "youtube.com/embed/" in text
    )


def _url_to_target(url: str) -> PlayTarget:
    full = _ensure_https(url)
    if is_playlist_url(full):
        raise SearchError(
            "プレイリストURLには対応していません。個別の動画URLを指定してください。"
        )

    normalized = normalize_youtube_url(full) or full
    try:
        with yt_dlp.YoutubeDL(SEARCH_OPTS) as ydl:
            info = ydl.extract_info(normalized, download=False)
    except Exception as e:
        logger.exception("YouTube metadata lookup failed")
        raise SearchError(
            "動画情報の取得に失敗しました。時間をおいて再試行してください。"
        ) from e

    if not info:
        raise SearchError("動画情報を取得できませんでした。")

    title = info.get("title") or normalized
    return PlayTarget(url=normalized, display_title=title)


def _search_youtube(query: str) -> PlayTarget:
    """ytsearch1 で先頭1件を取得"""
    try:
        with yt_dlp.YoutubeDL(SEARCH_OPTS) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=False)
    except Exception as e:
        logger.exception("YouTube search failed")
        raise SearchError(
            "YouTube検索に失敗しました。時間をおいて再試行してください。"
        ) from e

    entries = info.get("entries") if info else None
    if not entries:
        raise SearchError(f"「{query}」に一致する動画が見つかりませんでした。")

    entry = entries[0]
    if not entry:
        raise SearchError(f"「{query}」に一致する動画が見つかりませんでした。")

    video_id = entry.get("id")
    if not video_id:
        raise SearchError("検索結果の動画IDを取得できませんでした。")

    url = entry.get("url") or f"https://www.youtube.com/watch?v={video_id}"
    if not url.startswith("http"):
        url = f"https://www.youtube.com/watch?v={video_id}"

    title = entry.get("title") or query
    logger.info(f"Search hit: {title} -> {url}")
    return PlayTarget(url=url, display_title=title)


def resolve_play_query(query: str) -> PlayTarget:
    """
    再生クエリを解決する。

    YouTube URL の場合はそのまま、それ以外は YouTube 検索（先頭1件）。
    """
    text = query.strip()
    if not text:
        raise SearchError("URL または曲名を入力してください。")

    if looks_like_youtube_url(text):
        return _url_to_target(text)

    return _search_youtube(text)
