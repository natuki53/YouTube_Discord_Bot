import asyncio
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, call, patch

import aiohttp

from main import DISCORD_TOKEN, YouTubeBotMain, _discord_retry_wait_seconds, main


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


class MainReconnectTests(unittest.TestCase):
    def test_run_delegates_retries_to_the_bounded_outer_loop(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app = YouTubeBotMain.__new__(YouTubeBotMain)
            app.bot = Mock()
            app.settings = {"DOWNLOAD_TMP_DIR": temp_dir}

            with (
                patch("main.cleanup_stale_tmp", return_value=0),
                patch("main.force_kill_ffmpeg_processes"),
            ):
                app.run()

            app.bot.run.assert_called_once_with(DISCORD_TOKEN, reconnect=False)

    def test_retryable_disconnect_recreates_the_bot_after_a_bounded_delay(self):
        disconnected = Mock(_ready_initialized=True)
        disconnected.run.side_effect = aiohttp.ClientOSError(1, "offline")
        recovered = Mock(_ready_initialized=False)

        with (
            patch("main.YouTubeBotMain", side_effect=[disconnected, recovered]),
            patch("main.time.sleep") as sleep,
        ):
            main()

        self.assertEqual(disconnected.run.call_count, 1)
        self.assertEqual(recovered.run.call_count, 1)
        self.assertEqual(sleep.call_args_list, [call(5)])

    def test_retry_delay_is_capped_at_one_minute(self):
        self.assertEqual(_discord_retry_wait_seconds(1), 5)
        self.assertEqual(_discord_retry_wait_seconds(2), 10)
        self.assertEqual(_discord_retry_wait_seconds(10), 60)


if __name__ == "__main__":
    unittest.main()
