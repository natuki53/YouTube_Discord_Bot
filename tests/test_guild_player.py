import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from bot.music.guild_player import GuildPlayer
from bot.music.models import Track
from bot.youtube.stream import StreamError


class _Manager:
    bot = None

    def __init__(self):
        self.removed = []

    def remove(self, guild_id):
        self.removed.append(guild_id)


class _Member:
    def __init__(self, *, bot=False):
        self.bot = bot


class _Channel:
    def __init__(self, members=None):
        self.members = list(members or [])


class _VoiceClient:
    def __init__(self, callback_error=None, invoke_callback=True, members=None):
        self.callback_error = callback_error
        self.invoke_callback = invoke_callback
        self.playing = False
        self.paused = False
        self.connected = True
        self.stop_calls = 0
        self.channel = _Channel(members)

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

    async def disconnect(self):
        self.connected = False


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

    async def test_empty_channel_disconnects_after_three_minute_timer(self):
        manager = _Manager()
        player = GuildPlayer(123, manager)
        voice = _VoiceClient(members=[_Member(bot=True)])
        player._idle_task = asyncio.create_task(asyncio.sleep(1))
        player.stop = AsyncMock()
        player._send_empty_channel_disconnect = AsyncMock()

        with patch("bot.music.guild_player.EMPTY_CHANNEL_TIMEOUT_SECONDS", 0.01):
            player.update_empty_channel_timeout(voice)
            self.assertIsNone(player._idle_task)
            await asyncio.sleep(0.02)

        player._send_empty_channel_disconnect.assert_awaited_once()
        player.stop.assert_awaited_once_with(voice)
        self.assertEqual(manager.removed, [123])
        self.assertIsNone(player._empty_channel_task)

    async def test_human_returning_cancels_empty_channel_timer(self):
        manager = _Manager()
        player = GuildPlayer(123, manager)
        voice = _VoiceClient(members=[_Member(bot=True)])
        player.stop = AsyncMock()

        with patch("bot.music.guild_player.EMPTY_CHANNEL_TIMEOUT_SECONDS", 0.03):
            player.update_empty_channel_timeout(voice)
            self.assertIsNotNone(player._empty_channel_task)

            voice.channel.members.append(_Member(bot=False))
            player.update_empty_channel_timeout(voice)
            await asyncio.sleep(0.04)

        player.stop.assert_not_awaited()
        self.assertEqual(manager.removed, [])
        self.assertIsNone(player._empty_channel_task)

    async def test_human_in_channel_does_not_start_empty_timer(self):
        player = GuildPlayer(123, _Manager())
        voice = _VoiceClient(members=[_Member(bot=True), _Member(bot=False)])

        player.update_empty_channel_timeout(voice)

        self.assertIsNone(player._empty_channel_task)


if __name__ == "__main__":
    unittest.main()
