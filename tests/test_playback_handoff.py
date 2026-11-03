import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord

from bot.music.handoff import restore_handoff


class HandoffTests(unittest.IsolatedAsyncioTestCase):
    async def test_restores_order_and_settings_once(self):
        channel = Mock(spec=discord.VoiceChannel)
        channel.members = [SimpleNamespace(bot=False)]
        channel.connect = AsyncMock(return_value=Mock())
        guild = Mock(voice_client=None)
        guild.get_channel.return_value = channel
        guild.id = 1
        bot = Mock()
        bot.get_guild.return_value = guild
        manager = Mock()
        manager.get.return_value.enqueue = AsyncMock()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "handoff.json"
            path.write_text(
                json.dumps(
                    {
                        "guild_id": 1,
                        "voice_channel_id": 2,
                        "notification_channel_id": 3,
                        "volume": 28,
                        "tracks": [
                            {
                                "url": f"https://www.youtube.com/watch?v={i:011d}",
                                "title": str(i),
                                "requester": "member",
                            }
                            for i in range(3)
                        ],
                    }
                )
            )
            self.assertEqual(await restore_handoff(bot, manager, path), 3)
            self.assertEqual(await restore_handoff(bot, manager, path), 0)
        self.assertEqual(
            [c.args[0].title for c in manager.get.return_value.enqueue.await_args_list],
            ["0", "1", "2"],
        )
        manager.get.return_value.set_volume_percent.assert_called_once_with(28)
        channel.connect.assert_awaited_once()
