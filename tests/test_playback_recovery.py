import asyncio
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from bot.music.guild_player import GuildPlayer
from bot.music.models import Track
from bot.web.server import WebServer, _write_activity
from bot.youtube.stream import StreamInfo


class PlaybackRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_retry_uses_played_position_and_resolves_fresh_stream(self):
        player = GuildPlayer(123, Mock())
        track = Track("https://www.youtube.com/watch?v=test", "test", "requester")
        player._queue.enqueue(track)
        player._start_idle_timeout = Mock()
        player._notify_error = AsyncMock()
        voice = SimpleNamespace(is_connected=lambda: True)
        calls = []

        async def play(*args, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                # _play_stream freezes this media position before cleanup.
                player._position_offset = 40.25
                return False
            return True

        player._play_stream = play
        stream = StreamInfo("stream", "test", "test", duration=208)
        with (
            patch("bot.music.guild_player.resolve_stream", new=AsyncMock(return_value=stream)) as resolve,
            patch("bot.music.guild_player.STREAM_RETRY_BASE_DELAY_SECONDS", 0),
        ):
            await player._play_loop(voice)
        self.assertNotIn("start_offset", calls[0])
        self.assertEqual(calls[1]["start_offset"], 40.25)
        self.assertEqual(resolve.await_count, 2)
        player._notify_error.assert_not_awaited()

    async def test_failed_stream_freezes_media_time_before_wrappers_are_cleared(self):
        player = GuildPlayer(123, Mock())
        track = Track("url", "test", "requester")
        player._current = player._announced_track = track
        player._position_offset = 15.0
        player._duration = 208
        player._start_next_track_prefetch = Mock()
        raw = Mock(_current_error=None, _process=None)
        nightcore = Mock(media_samples=40.25 * 48000, rate=1.25)
        voice = Mock()
        voice.is_playing.return_value = voice.is_paused.return_value = False
        voice.play.side_effect = lambda source, after: after(RuntimeError("interrupted"))
        with (
            patch("bot.music.guild_player.discord.FFmpegPCMAudio", return_value=raw),
            patch("bot.music.guild_player.NightcoreAudioSource", return_value=nightcore),
        ):
            self.assertFalse(await player._play_stream(voice, "stream", track, 208, start_offset=15))
        self.assertIsNone(player._nightcore_source)
        self.assertIsNone(player._audio_monitor)
        self.assertEqual(player.get_progress()["position"], 55.25)

    async def test_clean_ffmpeg_exit_does_not_hide_truncated_audio(self):
        player = GuildPlayer(123, Mock())
        track = Track("url", "test", "requester")
        player._current = player._announced_track = track
        player._duration = 208
        player._start_next_track_prefetch = Mock()
        raw = Mock(_current_error=None, _process=None)
        nightcore = Mock(media_samples=50 * 48000, rate=1.0)
        voice = Mock()
        voice.is_playing.return_value = voice.is_paused.return_value = False
        voice.play.side_effect = lambda source, after: after(None)
        with (
            patch("bot.music.guild_player.discord.FFmpegPCMAudio", return_value=raw),
            patch("bot.music.guild_player.NightcoreAudioSource", return_value=nightcore),
        ):
            self.assertFalse(await player._play_stream(voice, "stream", track, 208))
        self.assertEqual(player.get_progress()["position"], 50)

    async def test_skip_during_retry_wait_continues_with_next_track(self):
        player = GuildPlayer(123, Mock())
        first, second = Track("first", "first", "user"), Track("next", "next", "user")
        player._queue.enqueue(first)
        player._queue.enqueue(second)
        player._start_idle_timeout = Mock()
        player._play_stream = AsyncMock(side_effect=[False, True])
        voice = Mock()
        voice.is_connected.return_value = True
        voice.is_playing.return_value = voice.is_paused.return_value = False
        waiting = asyncio.Event()

        async def wait(seconds):
            waiting.set()
            await player.skip(voice)

        with (
            patch("bot.music.guild_player.resolve_stream", new=AsyncMock(return_value=StreamInfo("stream", "test", "id", duration=208))),
            patch("bot.music.guild_player.asyncio.sleep", side_effect=wait),
        ):
            await player._play_loop(voice)
        self.assertTrue(waiting.is_set())
        self.assertEqual([call.args[2] for call in player._play_stream.await_args_list], [first, second])


class ActivityReportingTests(unittest.IsolatedAsyncioTestCase):
    async def test_activity_disk_wait_does_not_block_event_loop(self):
        with tempfile.TemporaryDirectory() as directory:
            server = SimpleNamespace(
                config=SimpleNamespace(database=Path(directory) / "web.sqlite3"),
                jobs={}, bot=SimpleNamespace(guilds=[]),
                control=SimpleNamespace(manager=SimpleNamespace(get_all_guild_ids=lambda: [])),
            )
            loop = asyncio.get_running_loop()
            entered, release = asyncio.Event(), threading.Event()

            def blocked_write(target, data):
                loop.call_soon_threadsafe(entered.set)
                release.wait(3)

            with patch("bot.web.server._write_activity", side_effect=blocked_write):
                task = asyncio.create_task(WebServer.report_activity(server))
                try:
                    await asyncio.wait_for(entered.wait(), 1)
                    self.assertFalse(task.done())
                    await asyncio.sleep(0)
                    self.assertFalse(release.is_set())
                finally:
                    release.set()
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task

    async def test_private_snapshot_is_atomic_and_cleans_failed_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "activity.json"
            _write_activity(target, {"voice": 1})
            self.assertEqual(json.loads(target.read_text()), {"voice": 1})
            with patch("bot.web.server.os.chmod", side_effect=OSError("disk error")):
                with self.assertRaises(OSError):
                    _write_activity(target, {"voice": 2})
            self.assertEqual(json.loads(target.read_text()), {"voice": 1})
            self.assertEqual(list(Path(directory).iterdir()), [target])
