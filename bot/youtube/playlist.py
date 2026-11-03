"""公開・限定公開の YouTube 再生リストを上限付きで展開する。"""

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

import yt_dlp

from .search import SEARCH_OPTS, PlayTarget, SearchError, resolve_play_query

PLAYLIST_LIMIT = 50
VIDEO_ID = re.compile(r"^[a-zA-Z0-9_-]{11}$")


@dataclass
class PlaylistTarget:
    url: str
    display_title: str
    tracks: list[PlayTarget]
    skipped: int = 0
    truncated: bool = False


def playlist_id(query):
    text = query.strip()
    if not text.startswith(("http://", "https://")):
        text = "https://" + text
    try:
        url = urlsplit(text)
    except ValueError:
        return None
    if url.scheme != "https" or url.hostname not in {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
    }:
        return None
    if url.username or url.password:
        return None
    value = parse_qs(url.query).get("list", [None])[0]
    return value if value and re.fullmatch(r"[a-zA-Z0-9_-]{1,200}", value) else None


def resolve_playlist(query):
    list_id = playlist_id(query)
    if not list_id:
        raise SearchError("有効なYouTube再生リストのURLを入力してください。")
    url = "https://www.youtube.com/playlist?list=" + list_id
    options = {
        **SEARCH_OPTS,
        "noplaylist": False,
        "extract_flat": "in_playlist",
        "playlistend": PLAYLIST_LIMIT + 1,
        "ignoreerrors": True,
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as error:
        raise SearchError(
            "再生リストを取得できませんでした。公開範囲とURLをご確認ください。"
        ) from error
    if not info:
        raise SearchError(
            "再生リストを取得できませんでした。公開・限定公開のリストを指定してください。"
        )
    entries = list(info.get("entries") or [])
    tracks, skipped = [], 0
    for entry in entries[:PLAYLIST_LIMIT]:
        if (
            not entry
            or entry.get("title")
            in {"[Deleted video]", "[Private video]", "Deleted video", "Private video"}
            or not VIDEO_ID.fullmatch(entry.get("id") or "")
            or entry.get("availability")
            in {"private", "needs_auth", "premium_only", "subscriber_only"}
        ):
            skipped += 1
            continue
        video_url = "https://www.youtube.com/watch?v=" + entry["id"]
        tracks.append(PlayTarget(video_url, entry.get("title") or video_url))
    if not tracks:
        raise SearchError(
            "再生できる曲がありません。非公開・削除済みの動画は取り込めません。"
        )
    count = info.get("playlist_count") or info.get("n_entries") or 0
    return PlaylistTarget(
        url,
        info.get("title") or "YouTube再生リスト",
        tracks,
        skipped,
        len(entries) > PLAYLIST_LIMIT
        or (isinstance(count, int) and count > PLAYLIST_LIMIT),
    )


def resolve_play_request(query):
    return resolve_playlist(query) if playlist_id(query) else resolve_play_query(query)
