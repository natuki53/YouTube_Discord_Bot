import asyncio
import shlex
import unittest
from unittest.mock import AsyncMock, Mock, patch

from bot.music.guild_player import GuildPlayer
from bot.music.models import Track
from bot.youtube.stream import StreamError, StreamInfo


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

    async def test_playback_failure_retries_then_reports_to_discord(self):
        player = GuildPlayer(123, _Manager())
        track = Track(
            url="https://www.youtube.com/watch?v=test",
            title="test",
            requester="tester",
        )
        player._queue.enqueue(track)
        player._send_now_playing = AsyncMock()
        player._play_stream = AsyncMock(return_value=False)
        player._notify_error = AsyncMock()
        voice = _VoiceClient()
        stream = StreamInfo(
            url="stream",
            title="test",
            video_id="test",
            duration=60,
            http_headers={"User-Agent": "test-agent"},
        )

        with (
            patch(
                "bot.music.guild_player.resolve_stream",
                new=AsyncMock(return_value=stream),
            ) as resolve,
            patch("bot.music.guild_player.STREAM_RETRY_BASE_DELAY_SECONDS", 0),
        ):
            await player._play_loop(voice)

        self.assertEqual(resolve.await_count, 3)
        self.assertEqual(player._play_stream.await_count, 3)
        player._notify_error.assert_awaited_once_with(
            track,
            "YouTubeから音声を取得できませんでした。"
            "時間をおいて再度お試しください。",
        )

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

    async def test_ffmpeg_source_error_is_a_failed_playback(self):
        player = GuildPlayer(123, _Manager())
        track = Track(url="url", title="title", requester="tester")
        voice = _VoiceClient()
        raw = Mock()
        raw._current_error = RuntimeError("ffmpeg exited with code 8")

        with (
            patch(
                "bot.music.guild_player.discord.FFmpegPCMAudio",
                return_value=raw,
            ),
            patch(
                "bot.music.guild_player.discord.PCMVolumeTransformer",
                return_value=object(),
            ),
        ):
            played = await player._play_stream(voice, "stream", track, duration=60)

        self.assertFalse(played)

    async def test_ffmpeg_exit_race_is_a_failed_playback(self):
        player = GuildPlayer(123, _Manager())
        track = Track(url="url", title="title", requester="tester")
        voice = _VoiceClient()
        raw = Mock()
        raw._current_error = None
        raw._process.poll.return_value = None
        raw._process.wait.return_value = 8

        with (
            patch(
                "bot.music.guild_player.discord.FFmpegPCMAudio",
                return_value=raw,
            ),
            patch(
                "bot.music.guild_player.discord.PCMVolumeTransformer",
                return_value=object(),
            ),
        ):
            played = await player._play_stream(voice, "stream", track, duration=60)

        self.assertFalse(played)
        raw._process.wait.assert_called_once_with(timeout=1)

    async def test_ffmpeg_receives_youtube_http_headers(self):
        player = GuildPlayer(123, _Manager())
        track = Track(url="url", title="title", requester="tester")
        voice = _VoiceClient()

        with (
            patch(
                "bot.music.guild_player.discord.FFmpegPCMAudio",
                return_value=object(),
            ) as ffmpeg,
            patch(
                "bot.music.guild_player.discord.PCMVolumeTransformer",
                return_value=object(),
            ),
        ):
            played = await player._play_stream(
                voice,
                "stream",
                track,
                duration=60,
                http_headers={
                    "User-Agent": "test-agent",
                    "Accept": "*/*",
                },
            )

        self.assertTrue(played)
        before_options = ffmpeg.call_args.kwargs["before_options"]
        arguments = shlex.split(before_options)
        header_block = arguments[arguments.index("-headers") + 1]
        self.assertIn("User-Agent: test-agent\r\n", header_block)
        self.assertIn("Accept: */*\r\n", header_block)

    async def test_unsafe_http_headers_are_not_passed_to_ffmpeg(self):
        player = GuildPlayer(123, _Manager())
        track = Track(url="url", title="title", requester="tester")
        voice = _VoiceClient()

        with (
            patch(
                "bot.music.guild_player.discord.FFmpegPCMAudio",
                return_value=object(),
            ) as ffmpeg,
            patch(
                "bot.music.guild_player.discord.PCMVolumeTransformer",
                return_value=object(),
            ),
        ):
            await player._play_stream(
                voice,
                "stream",
                track,
                duration=60,
                http_headers={"User-Agent": "ok", "Injected": "bad\r\n-header"},
            )

        before_options = ffmpeg.call_args.kwargs["before_options"]
        self.assertNotIn("Injected", before_options)

    async def test_playback_error_notification_explains_skip(self):
        player = GuildPlayer(123, _Manager())
        track = Track(
            url="https://www.youtube.com/watch?v=video-id",
            title="再生できない曲",
            requester="tester",
        )
        channel = AsyncMock()

        with patch.object(player, "_get_text_channel", return_value=channel):
            await player._notify_error(track, "音声の取得に失敗しました。")

        embed = channel.send.await_args.kwargs["embed"]
        self.assertEqual(embed.title, "❌ 再生できませんでした")
        self.assertIn(track.title, embed.description)
        self.assertIn(track.url, embed.description)
        self.assertIn("この曲をスキップしました。", embed.description)

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

    async def test_skip_plays_and_announces_next_track(self):
        player = GuildPlayer(123, _Manager())
        player._current = Track(url="current", title="current", requester="tester")
        next_track = Track(
            url="https://www.youtube.com/watch?v=next",
            title="next title",
            requester="requester",
        )
        player._queue.enqueue(next_track)
        player._send_now_playing = AsyncMock()

        async def play_after_notification(*_args, **_kwargs):
            self.assertEqual(player._send_now_playing.await_count, 1)
            return True

        player._play_stream = AsyncMock(side_effect=play_after_notification)
        player._start_idle_timeout = Mock()
        voice = _VoiceClient()
        voice.playing = True

        await player.skip(voice)
        with patch(
            "bot.music.guild_player.resolve_stream",
            new=AsyncMock(
                return_value=StreamInfo(
                    url="stream",
                    title=next_track.title,
                    video_id="next",
                    duration=180,
                    webpage_url=next_track.url,
                )
            ),
        ):
            await player._play_loop(voice)

        player._send_now_playing.assert_awaited_once_with(
            next_track,
            180,
            "next",
        )
        player._play_stream.assert_awaited_once_with(
            voice,
            "stream",
            next_track,
            180,
            http_headers={},
        )

    async def test_now_playing_embed_shows_title_url_and_thumbnail(self):
        player = GuildPlayer(123, _Manager())
        track = Track(
            url="https://www.youtube.com/watch?v=video-id",
            title="表示する曲名",
            requester="tester",
        )
        channel = AsyncMock()

        with patch.object(player, "_get_text_channel", return_value=channel):
            await player._send_now_playing(track, 125, "video-id")

        embed = channel.send.await_args.kwargs["embed"]
        self.assertEqual(embed.title, "▶️ 再生開始")
        self.assertIn("表示する曲名", embed.description)
        self.assertIn(track.url, [field.value for field in embed.fields])
        self.assertIn("2:05", [field.value for field in embed.fields])
        self.assertEqual(
            embed.thumbnail.url,
            "https://i.ytimg.com/vi/video-id/hqdefault.jpg",
        )

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
