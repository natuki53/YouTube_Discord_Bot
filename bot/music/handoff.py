"""修正配備時に退避したキューを、信頼済みの非公開ファイルから一度だけ戻す。"""

import json
import logging
import math
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import discord

from .models import Track, requester_avatar_url

logger = logging.getLogger(__name__)


async def restore_handoff(bot, manager, path: Path):
    if not path.is_file():
        return 0
    if path.stat().st_size > 128 * 1024:
        raise ValueError("Playback handoff is too large")
    data = json.loads(path.read_text(encoding="utf-8"))
    guild = bot.get_guild(int(data["guild_id"]))
    if guild is None:
        raise ValueError("Handoff guild is unavailable")
    channel = guild.get_channel(int(data["voice_channel_id"]))
    if not isinstance(channel, discord.VoiceChannel):
        raise ValueError("Handoff voice channel is unavailable")
    entries = data["tracks"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= 101:
        raise ValueError("Invalid handoff queue size")
    tracks = []
    for entry in entries:
        url = urlsplit(entry["url"])
        if (
            url.scheme != "https"
            or url.hostname != "www.youtube.com"
            or url.path != "/watch"
            or not parse_qs(url.query).get("v")
        ):
            raise ValueError("Invalid handoff URL")
        # Old deployment snapshots have only a display name. Resolve appearance
        # from a unique cached VC member; this is never used for authorization.
        members = [
            member
            for member in channel.members
            if getattr(member, "display_name", None) == entry["requester"]
        ]
        requester = members[0] if len(members) == 1 else None
        tracks.append(
            Track(
                url=entry["url"],
                title=str(entry["title"])[:500],
                requester=str(entry["requester"])[:100],
                requester_id=getattr(requester, "id", None),
                requester_avatar=requester_avatar_url(requester),
            )
        )
    volume = data.get("volume", 25)
    if type(volume) is not int or not 1 <= volume <= 100:
        raise ValueError("Invalid handoff volume")
    position = data.get("position", 0)
    paused = data.get("paused", False)
    if (
        type(position) not in (int, float)
        or not math.isfinite(position)
        or not 0 <= position <= 86400
        or type(paused) is not bool
    ):
        raise ValueError("Invalid handoff playback position")
    tracks[0].resume_position = float(position)
    tracks[0].resume_paused = paused
    if not any(not member.bot for member in channel.members):
        logger.warning("Handoff left pending because the voice channel is empty")
        return 0
    voice = guild.voice_client or await channel.connect()
    player = manager.get(guild.id)
    player.set_volume_percent(volume)
    player.set_text_channel(int(data["notification_channel_id"]))
    for track in tracks:
        await player.enqueue(track, voice)
    if data.get("loop"):
        player.toggle_loop()
    player.set_autoplay_enabled(bool(data.get("autoplay")))
    path.rename(path.with_name(path.name + ".consumed"))
    logger.info("Restored playback handoff: %s track(s)", len(tracks))
    return len(tracks)
