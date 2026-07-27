"""音楽トラックを表示するDiscord Embed。"""

from urllib.parse import parse_qs, urlparse

import discord

from .models import Track


def _safe_text(value: str) -> str:
    escaped = discord.utils.escape_markdown(str(value))
    return discord.utils.escape_mentions(escaped)


def _format_duration(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _youtube_video_id(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.netloc.lower() in {"youtu.be", "www.youtu.be"}:
        return parsed.path.strip("/").split("/")[0] or None
    if parsed.path == "/watch":
        return parse_qs(parsed.query).get("v", [None])[0]
    if parsed.path.startswith("/embed/"):
        return parsed.path.removeprefix("/embed/").split("/")[0] or None
    return None


def build_track_embed(
    *,
    heading: str,
    track: Track,
    color: discord.Color,
    duration_seconds: int | None = None,
    queue_position: int | None = None,
    queued_tracks: int | None = None,
    video_id: str | None = None,
) -> discord.Embed:
    """タイトル、URL、依頼者などを揃えたトラックカードを作る。"""
    embed = discord.Embed(
        title=heading,
        description=f"## [{_safe_text(track.title)}]({track.url})",
        color=color,
    )
    embed.add_field(name="🔗 YouTube URL", value=track.url, inline=False)
    embed.add_field(
        name="👤 リクエスト",
        value=_safe_text(track.requester),
        inline=True,
    )

    if duration_seconds and duration_seconds > 0:
        embed.add_field(
            name="⏱️ 再生時間",
            value=_format_duration(duration_seconds),
            inline=True,
        )
    if queue_position is not None:
        embed.add_field(
            name="📋 キュー",
            value=f"{queue_position} 番目",
            inline=True,
        )
    elif queued_tracks:
        embed.add_field(
            name="📋 待機中",
            value=f"{queued_tracks} 曲",
            inline=True,
        )

    thumbnail_id = video_id or _youtube_video_id(track.url)
    if thumbnail_id:
        embed.set_thumbnail(url=f"https://i.ytimg.com/vi/{thumbnail_id}/hqdefault.jpg")

    return embed
