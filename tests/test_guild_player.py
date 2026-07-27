import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from bot.music.guild_player import GuildPlayer
from bot.music.models import Track
from bot.youtube.stream import StreamError


class _Manager:
    bot = None

    def remove(self, guild_id):
        pass


class _VoiceClient:
    def __init__(self, callback_error=None, invoke_callback=True):
        self.callback_error = callback_error
        self.invoke_callback = invoke_callback
        self.playing = False
        self.paused = False
        self.connected = True
        self.stop_calls = 0

    def is_playing(self):
        return self.playing

    def is_paused(self):
        return self.paused

    def is_connected(self):
        return self.connected

    def play(self, source, after):
        self.playing = True
        if self.invoke_callback:
            self.playing = False
            after(self.callback_error)

    def stop(self):
        self.stop_calls += 1
        self.playing = False


class GuildPlayerTests(unittest.IsolatedAsyncioTestCase):
    async def test_looped_stream_failure_stops_after_retry_limit(self):
        player = GuildPlayer(123, _Manager())
        track = Track(
            url="https://www.youtube.com/watch?v=test",
            title="test",
            requester="tester",
        )
        player._current = track
        player._loop_enabled = True
        player._notify_error = AsyncMock()
        voice = _VoiceClient()

        with (
            patch(
                "bot.music.guild_player.resolve_stream",
                new=AsyncMock(side_effect=StreamError("temporary failure")),
            ) as resolve,
            patch("bot.music.guild_player.STREAM_RETRY_BASE_DELAY_SECONDS", 0),
        ):
            await asyncio.wait_for(player._play_loop(voice), timeout=1)

        self.assertEqual(resolve.await_count, 3)
        self.assertIsNone(player._current)
        player._notify_error.assert_awaited_once_with(track, "temporary failure")

    async def test_ffmpeg_callback_error_is_a_failed_playback(self):
        player = GuildPlayer(123, _Manager())
        track = Track(url="url", title="title", requester="tester")
        voice = _VoiceClient(callback_error=RuntimeError("ffmpeg failed"))

        with (
            patch(
                "bot.music.guild_player.discord.FFmpegPCMAudio", return_value=object()
            ),
            patch(
                "bot.music.guild_player.discord.PCMVolumeTransformer",
                return_value=object(),
            ),
        ):
            played = await player._play_stream(voice, "stream", track, duration=60)

        self.assertFalse(played)

    async def test_missing_ffmpeg_callback_times_out_and_stops(self):
        player = GuildPlayer(123, _Manager())
        track = Track(url="url", title="title", requester="tester")
        voice = _VoiceClient(invoke_callback=False)

        with (
            patch(
                "bot.music.guild_player.discord.FFmpegPCMAudio", return_value=object()
            ),
            patch(
                "bot.music.guild_player.discord.PCMVolumeTransformer",
                return_value=object(),
            ),
            patch("bot.music.guild_player.UNKNOWN_DURATION_TIMEOUT_SECONDS", 0.01),
        ):
            played = await player._play_stream(voice, "stream", track, duration=None)

        self.assertFalse(played)
        self.assertEqual(voice.stop_calls, 1)

    async def test_skip_disables_loop_even_when_queue_has_tracks(self):
        player = GuildPlayer(123, _Manager())
        player._loop_enabled = True
        player._current = Track(url="current", title="current", requester="tester")
        player._queue.enqueue(Track(url="next", title="next", requester="tester"))
        voice = _VoiceClient()
        voice.playing = True

        await player.skip(voice)

        self.assertFalse(player.is_loop_enabled())


if __name__ == "__main__":
    unittest.main()
