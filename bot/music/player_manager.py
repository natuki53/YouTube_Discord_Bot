"""ギルドごとの GuildPlayer 管理"""

import logging
from typing import Dict, Optional

import discord

from .guild_player import GuildPlayer

logger = logging.getLogger(__name__)


class PlayerManager:
    """guild_id -> GuildPlayer"""

    def __init__(self, bot: discord.Client, default_volume: int = 25):
        self.bot = bot
        self.default_volume = max(1, min(100, default_volume))
        self._players: Dict[int, GuildPlayer] = {}

    def get(self, guild_id: int) -> GuildPlayer:
        if guild_id not in self._players:
            self._players[guild_id] = GuildPlayer(
                guild_id, self, default_volume_percent=self.default_volume
            )
        return self._players[guild_id]

    def get_existing(self, guild_id: int) -> Optional[GuildPlayer]:
        return self._players.get(guild_id)

    def remove(self, guild_id: int) -> None:
        if guild_id in self._players:
            del self._players[guild_id]
            logger.debug(f"Removed GuildPlayer for guild {guild_id}")

    def get_all_guild_ids(self):
        return list(self._players.keys())
