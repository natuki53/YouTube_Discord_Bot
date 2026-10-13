import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.commands.general import setup_general_commands
from bot.commands.music import setup_music_commands
from bot.config.discord_config import create_bot_instance
from bot.music import PlayerManager


class CommandRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.bot = create_bot_instance("!")

    def test_music_commands_are_guild_only(self):
        setup_music_commands(self.bot, PlayerManager(self.bot))

        self.assertTrue(hasattr(self.bot, "on_voice_state_update"))
        for command in self.bot.tree.get_commands():
            with self.subTest(command=command.name):
                self.assertTrue(command.guild_only)

    def test_slash_command_error_handler_is_registered(self):
        setup_general_commands(self.bot)

        self.assertEqual(self.bot.tree.on_error.__name__, "on_app_command_error")


class AutoplayCommandTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = create_bot_instance("!")
        self.manager = PlayerManager(self.bot)
        setup_music_commands(self.bot, self.manager)
        self.command = self.bot.tree.get_command("autoplay")
        self.channel = SimpleNamespace(id=1)
        self.voice = SimpleNamespace(channel=self.channel, is_connected=lambda: True)
        self.interaction = SimpleNamespace(
            guild_id=123,
            channel_id=456,
            guild=SimpleNamespace(voice_client=self.voice),
            user=SimpleNamespace(voice=SimpleNamespace(channel=self.channel)),
            response=SimpleNamespace(send_message=AsyncMock()),
        )

    async def test_status_does_not_create_a_player(self):
        await self.command.callback(self.interaction)
        self.assertIsNone(self.manager.get_existing(123))
        self.assertIn("オフ", self.interaction.response.send_message.await_args.args[0])

    async def test_enable_and_disable_from_same_vc(self):
        await self.command.callback(self.interaction, True)
        player = self.manager.get_existing(123)
        self.assertTrue(player.is_autoplay_enabled())
        self.assertEqual(player._text_channel_id, 456)
        await self.command.callback(self.interaction, False)
        self.assertFalse(player.is_autoplay_enabled())

    async def test_setting_requires_bot_voice_connection(self):
        self.interaction.guild.voice_client = None
        await self.command.callback(self.interaction, True)
        self.assertIsNone(self.manager.get_existing(123))
        self.assertIn(
            "/play", self.interaction.response.send_message.await_args.args[0]
        )

    async def test_setting_requires_same_vc(self):
        self.interaction.user.voice.channel = SimpleNamespace(id=2)
        await self.command.callback(self.interaction, True)
        self.assertIsNone(self.manager.get_existing(123))
        self.assertIn(
            "同じボイスチャンネル",
            self.interaction.response.send_message.await_args.args[0],
        )

    async def test_setting_requires_user_voice_connection(self):
        self.interaction.user.voice = None
        await self.command.callback(self.interaction, True)
        self.assertIsNone(self.manager.get_existing(123))


if __name__ == "__main__":
    unittest.main()
