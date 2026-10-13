import asyncio
import shlex
import unittest
from unittest.mock import AsyncMock, Mock, patch

from bot.music.guild_player import GuildPlayer
from bot.music.models import Track
from bot.music.paced_audio_source import PacedAudioSource
from bot.youtube.stream import StreamError, StreamInfo
from bot.youtube.recommendations import RadioTrack, RecommendationError


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
            "YouTubeから音声を取得できませんでした。時間をおいて再度お試しください。",
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

    async def test_token_protected_media_is_piped_through_bounded_ranges(self):
        player = GuildPlayer(123, _Manager())
        track = Track(url="url", title="title", requester="tester")
        voice = _VoiceClient()
        ranged_stream = Mock()
        raw = Mock()
        raw._current_error = None
        raw._process = None

        with (
            patch(
                "bot.music.guild_player.YouTubeHTTPStream",
                return_value=ranged_stream,
            ) as stream_cls,
            patch(
                "bot.music.guild_player.discord.FFmpegPCMAudio",
                return_value=raw,
            ) as ffmpeg,
            patch(
                "bot.music.guild_player.discord.PCMVolumeTransformer",
                return_value=object(),
            ) as volume_transformer,
        ):
            played = await player._play_stream(
                voice,
                "https://example.test/audio",
                track,
                duration=60,
                http_headers={"User-Agent": "test-agent"},
                filesize=123456,
                http_chunk_size=10485760,
            )

        self.assertTrue(played)
        stream_cls.assert_called_once_with(
            "https://example.test/audio",
            {"User-Agent": "test-agent"},
            123456,
            10485760,
        )
        self.assertIs(ffmpeg.call_args.args[0], ranged_stream)
        self.assertTrue(ffmpeg.call_args.kwargs["pipe"])
        paced_source = volume_transformer.call_args.args[0]
        self.assertIsInstance(paced_source, PacedAudioSource)
        self.assertIs(paced_source._source, raw)
        ranged_stream.close.assert_called_once_with()

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
            filesize=None,
            http_chunk_size=None,
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


class AutoplayTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.player = GuildPlayer(123, _Manager())
        self.player._send_now_playing = AsyncMock()
        self.player._notify_error = AsyncMock()
        self.player._notify_autoplay_stopped = AsyncMock()
        self.player._start_idle_timeout = Mock()
        self.voice = _VoiceClient(members=[_Member(bot=False)])
        self.seed = self.track("seed0000001")

    @staticmethod
    def track(video_id):
        return Track(
            url=f"https://www.youtube.com/watch?v={video_id}",
            title=video_id,
            requester="tester",
            video_id=video_id,
        )

    @staticmethod
    async def resolve(url):
        video_id = url.split("v=")[1]
        return StreamInfo(url="stream", title=video_id, video_id=video_id, duration=60)

    async def test_autoplay_is_opt_in(self):
        self.player._queue.enqueue(self.seed)
        self.player._play_stream = AsyncMock(return_value=True)
        with (
            patch("bot.music.guild_player.resolve_stream", new=self.resolve),
            patch(
                "bot.music.guild_player.fetch_radio_tracks", new=AsyncMock()
            ) as radio,
        ):
            await self.player._play_loop(self.voice)
        radio.assert_not_awaited()
        self.assertFalse(self.player.get_queue_snapshot()["autoplay"])

    async def test_autoplay_continues_using_each_previous_track(self):
        self.player.set_autoplay_enabled(True)
        self.player._queue.enqueue(self.seed)
        played = []

        async def play(voice, stream, track, *args, **kwargs):
            played.append(track)
            if len(played) == 3:
                self.player.set_autoplay_enabled(False)
            return True

        self.player._play_stream = AsyncMock(side_effect=play)
        with (
            patch("bot.music.guild_player.resolve_stream", new=self.resolve),
            patch(
                "bot.music.guild_player.fetch_radio_tracks",
                new=AsyncMock(
                    side_effect=[
                        [RadioTrack("next0000001", "next")],
                        [RadioTrack("next0000002", "next again")],
                    ]
                ),
            ) as radio,
        ):
            await asyncio.wait_for(self.player._play_loop(self.voice), 1)

        self.assertEqual(
            [t.video_id for t in played], ["seed0000001", "next0000001", "next0000002"]
        )
        self.assertEqual(
            [call.args[0] for call in radio.await_args_list],
            ["seed0000001", "next0000001"],
        )
        self.assertTrue(all(t.auto_selected for t in played[1:]))
        self.assertEqual(self.player._send_now_playing.await_count, 3)

    async def test_manual_queue_plays_before_autoplay(self):
        self.player.set_autoplay_enabled(True)
        manual = self.track("hand0000001")
        self.player._queue.enqueue(self.seed)
        self.player._queue.enqueue(manual)
        played = []

        async def play(voice, stream, track, *args, **kwargs):
            played.append(track.video_id)
            if track.auto_selected:
                self.player.set_autoplay_enabled(False)
            return True

        self.player._play_stream = AsyncMock(side_effect=play)
        with (
            patch("bot.music.guild_player.resolve_stream", new=self.resolve),
            patch(
                "bot.music.guild_player.fetch_radio_tracks",
                new=AsyncMock(return_value=[RadioTrack("next0000001", "next")]),
            ) as radio,
        ):
            await self.player._play_loop(self.voice)
        self.assertEqual(played, [self.seed.video_id, manual.video_id, "next0000001"])
        radio.assert_awaited_once_with(manual.video_id)

    async def test_loop_has_priority_over_autoplay(self):
        self.player.set_autoplay_enabled(True)
        self.player._loop_enabled = True
        self.player._queue.enqueue(self.seed)
        played = []

        async def play(voice, stream, track, *args, **kwargs):
            played.append(track.video_id)
            if len(played) == 2:
                self.player.toggle_loop()
                self.player.set_autoplay_enabled(False)
            return True

        self.player._play_stream = AsyncMock(side_effect=play)
        with (
            patch("bot.music.guild_player.resolve_stream", new=self.resolve),
            patch(
                "bot.music.guild_player.fetch_radio_tracks", new=AsyncMock()
            ) as radio,
        ):
            await self.player._play_loop(self.voice)
        self.assertEqual(played, [self.seed.video_id, self.seed.video_id])
        radio.assert_not_awaited()

    async def test_recent_and_queued_video_ids_are_excluded(self):
        self.player.set_autoplay_enabled(True)
        self.player._autoplay_seed = self.seed
        self.player._remember_video_id("prev0000001")
        queued = self.track("hand0000001")
        queued.video_id = None
        queued.url = "https://youtu.be/hand0000001?t=30"
        self.player._queue.enqueue(queued)
        candidates = [
            RadioTrack(video_id, video_id)
            for video_id in (
                self.seed.video_id,
                "prev0000001",
                "hand0000001",
                "next0000001",
            )
        ]
        with patch(
            "bot.music.guild_player.fetch_radio_tracks",
            new=AsyncMock(return_value=candidates),
        ):
            track = await self.player._get_autoplay_track(self.voice)
        self.assertEqual(track.video_id, "next0000001")

    async def test_skip_without_manual_queue_plays_an_automatic_track(self):
        self.player.set_autoplay_enabled(True)
        self.player._queue.enqueue(self.seed)
        started = asyncio.Event()
        finished = asyncio.Event()
        played = []

        def stop_voice():
            self.voice.playing = False
            finished.set()

        self.voice.stop = Mock(side_effect=stop_voice)

        async def play(voice, stream, track, *args, **kwargs):
            played.append(track.video_id)
            if track is self.seed:
                voice.playing = True
                started.set()
                await finished.wait()
            else:
                self.player.set_autoplay_enabled(False)
            return True

        self.player._play_stream = AsyncMock(side_effect=play)
        with (
            patch("bot.music.guild_player.resolve_stream", new=self.resolve),
            patch(
                "bot.music.guild_player.fetch_radio_tracks",
                new=AsyncMock(return_value=[RadioTrack("next0000001", "next")]),
            ),
        ):
            task = asyncio.create_task(self.player._play_loop(self.voice))
            await asyncio.wait_for(started.wait(), 1)
            await self.player.skip(self.voice)
            await asyncio.wait_for(task, 1)
        self.assertEqual(played, [self.seed.video_id, "next0000001"])

    async def test_manual_request_interrupts_pending_radio_lookup(self):
        await self.check_lookup_interruption(disable=False)

    async def test_disabling_interrupts_lookup_and_preserves_manual_queue(self):
        await self.check_lookup_interruption(disable=True)

    async def check_lookup_interruption(self, *, disable):
        self.player.set_autoplay_enabled(True)
        self.player._autoplay_seed = self.seed
        started = asyncio.Event()

        async def radio(seed_id):
            started.set()
            await asyncio.Event().wait()

        async def play(*args, **kwargs):
            self.player.set_autoplay_enabled(False)
            return True

        self.player._play_stream = AsyncMock(side_effect=play)
        manual = self.track("hand0000001")
        with (
            patch(
                "bot.music.guild_player.resolve_stream",
                new=AsyncMock(side_effect=self.resolve),
            ) as resolve,
            patch("bot.music.guild_player.fetch_radio_tracks", new=radio),
        ):
            task = asyncio.create_task(self.player._play_loop(self.voice))
            self.player._loop_task = task
            await asyncio.wait_for(started.wait(), 1)
            if disable:
                self.player.set_autoplay_enabled(False)
            await self.player.enqueue(manual, self.voice)
            await asyncio.wait_for(task, 1)
        resolve.assert_awaited_once_with(manual.url)
        self.assertIsNone(self.player._autoplay_task)
        self.player._notify_autoplay_stopped.assert_not_awaited()

    async def test_stop_cancels_pending_radio_and_disconnects(self):
        self.player.set_autoplay_enabled(True)
        self.player._autoplay_seed = self.seed
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def radio(seed_id):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        with (
            patch("bot.music.guild_player.resolve_stream", new=AsyncMock()) as resolve,
            patch("bot.music.guild_player.fetch_radio_tracks", new=radio),
        ):
            self.player._loop_task = asyncio.create_task(
                self.player._play_loop(self.voice)
            )
            await asyncio.wait_for(started.wait(), 1)
            await self.player.stop(self.voice)
        self.assertTrue(cancelled.is_set())
        self.assertFalse(self.voice.connected)
        self.assertFalse(self.player.is_autoplay_enabled())
        self.assertIsNone(self.player._loop_task)
        self.assertIsNone(self.player._autoplay_task)
        resolve.assert_not_awaited()

    async def test_disabling_during_stream_resolution_discards_the_automatic_track(
        self,
    ):
        await self.check_stream_interruption(disable=True)

    async def test_manual_request_during_stream_resolution_plays_first(self):
        await self.check_stream_interruption(disable=False)

    async def check_stream_interruption(self, *, disable):
        self.player.set_autoplay_enabled(True)
        self.player._autoplay_seed = self.seed
        started = asyncio.Event()
        release = asyncio.Event()
        manual = self.track("hand0000001")

        async def resolve(url):
            if "next0000001" in url:
                started.set()
                await release.wait()
            else:
                self.player.set_autoplay_enabled(False)
            return await self.resolve(url)

        self.player._play_stream = AsyncMock(return_value=True)
        with (
            patch("bot.music.guild_player.resolve_stream", new=resolve),
            patch(
                "bot.music.guild_player.fetch_radio_tracks",
                new=AsyncMock(return_value=[RadioTrack("next0000001", "next")]),
            ),
        ):
            task = asyncio.create_task(self.player._play_loop(self.voice))
            self.player._loop_task = task
            await asyncio.wait_for(started.wait(), 1)
            if disable:
                self.player.set_autoplay_enabled(False)
            else:
                await self.player.enqueue(manual, self.voice)
            release.set()
            await asyncio.wait_for(task, 1)
        if disable:
            self.player._play_stream.assert_not_awaited()
        else:
            self.assertEqual(self.player._play_stream.await_args.args[2], manual)
            self.assertEqual(self.player._play_stream.await_count, 1)

    async def test_no_human_in_vc_prevents_autoplay(self):
        self.player.set_autoplay_enabled(True)
        self.player._autoplay_seed = self.seed
        self.voice.channel.members = [_Member(bot=True)]
        with patch(
            "bot.music.guild_player.fetch_radio_tracks", new=AsyncMock()
        ) as radio:
            self.assertIsNone(await self.player._get_autoplay_track(self.voice))
        radio.assert_not_awaited()

    async def test_human_leaving_during_lookup_discards_recommendation(self):
        self.player.set_autoplay_enabled(True)
        self.player._autoplay_seed = self.seed

        async def radio(seed_id):
            self.voice.channel.members = [_Member(bot=True)]
            return [RadioTrack("next0000001", "next")]

        with patch("bot.music.guild_player.fetch_radio_tracks", new=radio):
            self.assertIsNone(await self.player._get_autoplay_track(self.voice))

    async def test_radio_error_disables_autoplay_and_starts_idle_timer(self):
        self.player.set_autoplay_enabled(True)
        self.player._autoplay_seed = self.seed
        with patch(
            "bot.music.guild_player.fetch_radio_tracks",
            new=AsyncMock(side_effect=RecommendationError("offline")),
        ):
            await self.player._play_loop(self.voice)
        self.assertFalse(self.player.is_autoplay_enabled())
        self.player._notify_autoplay_stopped.assert_awaited_once_with("offline")
        self.player._start_idle_timeout.assert_called_once_with(self.voice)

    async def test_candidate_exhaustion_disables_autoplay(self):
        self.player.set_autoplay_enabled(True)
        self.player._autoplay_seed = self.seed
        self.player._remember_video_id("prev0000001")
        with patch(
            "bot.music.guild_player.fetch_radio_tracks",
            new=AsyncMock(return_value=[RadioTrack("prev0000001", "previous")]),
        ) as radio:
            await self.player._play_loop(self.voice)
        self.assertFalse(self.player.is_autoplay_enabled())
        radio.assert_awaited_once()
        self.player._notify_autoplay_stopped.assert_awaited_once()

    async def test_three_failed_automatic_tracks_stop_without_reselecting_them(self):
        self.player.set_autoplay_enabled(True)
        self.player._autoplay_seed = self.seed
        candidates = [RadioTrack(f"next000000{i}", "next") for i in range(1, 6)]
        with (
            patch(
                "bot.music.guild_player.fetch_radio_tracks",
                new=AsyncMock(return_value=candidates),
            ) as radio,
            patch(
                "bot.music.guild_player.resolve_stream",
                new=AsyncMock(side_effect=StreamError("unavailable")),
            ) as resolve,
            patch("bot.music.guild_player.STREAM_RETRY_BASE_DELAY_SECONDS", 0),
        ):
            await asyncio.wait_for(self.player._play_loop(self.voice), 1)
        radio.assert_awaited_once_with(self.seed.video_id)
        self.assertEqual(resolve.await_count, 9)
        self.assertEqual(
            set(call.args[0] for call in resolve.await_args_list),
            {c.url for c in candidates[:3]},
        )
        self.assertFalse(self.player.is_autoplay_enabled())
        self.player._notify_autoplay_stopped.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
