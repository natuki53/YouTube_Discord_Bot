import asyncio
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from main import YouTubeBotMain


class _FakeBot:
    user = "TestBot"
    guilds = []

    def event(self, handler):
        setattr(self, handler.__name__, handler)
        return handler


class MainLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_ready_initialization_only_runs_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app = YouTubeBotMain.__new__(YouTubeBotMain)
            app.bot = _FakeBot()
            app.settings = {
                "DOWNLOAD_DIR": temp_dir,
                "DOWNLOAD_TMP_DIR": temp_dir,
                "TMP_MAX_AGE_MINUTES": 30,
            }
            app._ready_lock = asyncio.Lock()
            app._ready_initialized = False
            app._sync_commands = AsyncMock()
            activity = AsyncMock()

            with (
                patch("main.setup_bot_activity", return_value=activity),
                patch("main.force_kill_ffmpeg_processes") as kill_ffmpeg,
            ):
                app._setup_events()
                await app.bot.on_ready()
                await app.bot.on_ready()

            self.assertTrue(app._ready_initialized)
            app._sync_commands.assert_awaited_once()
            activity.assert_awaited_once()
            kill_ffmpeg.assert_not_called()


if __name__ == "__main__":
    unittest.main()
