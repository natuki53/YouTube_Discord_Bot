import unittest

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


if __name__ == "__main__":
    unittest.main()
