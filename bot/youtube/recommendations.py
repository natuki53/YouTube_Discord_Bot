"""YouTube Music の曲別ラジオから自動選曲の候補を取得する。"""

import asyncio
import logging
import re
from dataclasses import dataclass
from functools import partial
from typing import List, Optional
from urllib.parse import parse_qs, urlparse

import requests
from ytmusicapi import YTMusic

logger = logging.getLogger(__name__)
RADIO_TIMEOUT_SECONDS = 30
RADIO_TRACK_LIMIT = 25
VIDEO_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{11}\Z")


class RecommendationError(Exception):
    """関連曲の取得失敗。"""


@dataclass(frozen=True)
class RadioTrack:
    video_id: str
    title: str

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


def youtube_video_id(url: str) -> Optional[str]:
    """同じ動画の URL 表記違いも、履歴・キューから除外できるようにする。"""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in {"youtu.be", "www.youtu.be"}:
        video_id = parsed.path.strip("/").split("/")[0]
    elif host in {
        "youtube.com",
        "www.youtube.com",
        "music.youtube.com",
        "m.youtube.com",
    }:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith(("/embed/", "/shorts/")):
            video_id = parsed.path.split("/")[2]
        else:
            return None
    else:
        return None
    return video_id if VIDEO_ID_PATTERN.fullmatch(video_id) else None


def _fetch_radio_tracks(video_id: str) -> List[RadioTrack]:
    # ギルド間でセッションを共有せず、同期 HTTP はワーカースレッドで実行する。
    with requests.Session() as session:
        session.request = partial(session.request, timeout=(5, 10))
        music = YTMusic(requests_session=session, language="ja", location="JP")
        result = music.get_watch_playlist(
            videoId=video_id, radio=True, limit=RADIO_TRACK_LIMIT
        )

    tracks = []
    seen = {video_id}
    for entry in result.get("tracks") or []:
        if not isinstance(entry, dict):
            continue
        candidate_id = entry.get("videoId")
        title = entry.get("title")
        if (
            not isinstance(candidate_id, str)
            or not VIDEO_ID_PATTERN.fullmatch(candidate_id)
            or candidate_id in seen
            or not isinstance(title, str)
            or not title.strip()
            or entry.get("isAvailable") is False
            or entry.get("isLive")
            or entry.get("videoType") == "MUSIC_VIDEO_TYPE_PODCAST_EPISODE"
        ):
            continue
        seen.add(candidate_id)
        artists = ", ".join(
            artist["name"]
            for artist in entry.get("artists") or []
            if isinstance(artist, dict) and isinstance(artist.get("name"), str)
        )
        display_title = f"{artists} - {title.strip()}" if artists else title.strip()
        tracks.append(RadioTrack(candidate_id, display_title))
        if len(tracks) >= RADIO_TRACK_LIMIT:
            break
    return tracks


async def fetch_radio_tracks(video_id: str) -> List[RadioTrack]:
    if not VIDEO_ID_PATTERN.fullmatch(video_id):
        raise RecommendationError("この動画をもとに関連曲を取得できません。")
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_fetch_radio_tracks, video_id),
            timeout=RADIO_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        raise RecommendationError("関連曲の検索がタイムアウトしました。") from exc
    except Exception as exc:
        logger.exception("YouTube Music radio lookup failed")
        raise RecommendationError(
            "YouTube Musicから関連曲を取得できませんでした。"
        ) from exc
