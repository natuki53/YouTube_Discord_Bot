"""YouTube 検索（曲名 → 動画 URL）"""

import logging
import math
import re
from dataclasses import dataclass
from itertools import islice

import yt_dlp

from .url_handler import is_playlist_url, normalize_youtube_url, validate_youtube_url

logger = logging.getLogger(__name__)
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")
SEARCH_LIMIT = 10

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


@dataclass(frozen=True)
class SearchResult:
    video_id: str
    title: str
    channel: str | None
    duration: int | None

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


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


def search_youtube(query: str, limit: int = SEARCH_LIMIT) -> list[SearchResult]:
    """候補のメタデータのみ取得し、音声の準備・キュー追加は行わない。"""
    query = query.strip()
    if not 1 <= len(query) <= 500:
        raise SearchError("検索する曲名を500文字以内で入力してください。")
    if type(limit) is not int or not 1 <= limit <= SEARCH_LIMIT:
        raise SearchError("検索結果は1〜10件で指定してください。")
    try:
        with yt_dlp.YoutubeDL(SEARCH_OPTS) as ydl:
            info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
    except Exception as e:
        logger.exception("YouTube search failed")
        raise SearchError(
            "YouTube検索に失敗しました。時間をおいて再試行してください。"
        ) from e

    results = []
    seen = set()
    for entry in islice((info or {}).get("entries") or [], limit):
        if not isinstance(entry, dict):
            continue
        video_id = entry.get("id")
        if (
            not isinstance(video_id, str)
            or not VIDEO_ID.fullmatch(video_id)
            or video_id in seen
            or entry.get("availability")
            in {"private", "needs_auth", "premium_only", "subscriber_only"}
        ):
            continue
        seen.add(video_id)
        title = entry.get("title")
        title = title.strip() if isinstance(title, str) and title.strip() else query
        channel = entry.get("channel") or entry.get("uploader")
        channel = (
            channel.strip() if isinstance(channel, str) and channel.strip() else None
        )
        duration = entry.get("duration")
        duration = (
            int(duration)
            if type(duration) in (int, float)
            and math.isfinite(duration)
            and duration >= 0
            else None
        )
        results.append(SearchResult(video_id, title, channel, duration))
    return results


def _search_youtube(query: str) -> PlayTarget:
    """Discordの曲名指定は従来どおり先頭1件を追加する。"""
    results = search_youtube(query, limit=1)
    if not results:
        raise SearchError(f"「{query}」に一致する動画が見つかりませんでした。")
    first = results[0]
    return PlayTarget(url=first.url, display_title=first.title)


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
