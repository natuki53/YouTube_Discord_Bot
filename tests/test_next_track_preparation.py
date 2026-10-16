import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord

from bot.music.guild_player import GuildPlayer
from bot.music.models import Track
from bot.youtube.recommendations import RadioTrack
from bot.youtube.stream import StreamError, StreamInfo


class ControlledVoiceClient:
    def __init__(self, player):
        self.player = player
        self.channel = SimpleNamespace(members=[SimpleNamespace(bot=False)])
        self.playing = False
        self.connected = True
        self.started = asyncio.Queue()
        self.after = None

    def is_playing(self):
        return self.playing

    def is_paused(self):
        return False

    def is_connected(self):
        return self.connected

    def play(self, source, after):
        self.playing = True
        self.after = after
        self.started.put_nowait(self.player._current)

    def finish(self, error=None):
        self.playing = False
        callback, self.after = self.after, None
        if callback:
            callback(error)

    def stop(self):
        self.finish()

    async def disconnect(self):
        self.connected = False


class NextTrackPreparationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.player = GuildPlayer(123, Mock(bot=None))
        self.channel = SimpleNamespace(send=AsyncMock())
        self.player._get_text_channel = Mock(return_value=self.channel)
        self.player._notify_error = AsyncMock()
        self.player._notify_autoplay_stopped = AsyncMock()
        self.player._start_idle_timeout = Mock()
        self.voice = ControlledVoiceClient(self.player)
        self.seed = self.track("seed0000001")
        self.next = self.track("next0000001")
        self.manual = self.track("hand0000001")
        self.task = None
        self.resolve = self.enterContext(
            patch(
                "bot.music.guild_player.resolve_stream",
                new=AsyncMock(side_effect=self.stream),
            )
        )
        self.radio = self.enterContext(
            patch(
                "bot.music.guild_player.fetch_radio_tracks",
                new=AsyncMock(return_value=[RadioTrack(self.next.video_id, "次の曲")]),
            )
        )
        self.enterContext(
            patch(
                "bot.music.guild_player.discord.FFmpegPCMAudio", return_value=object()
            )
        )
        self.enterContext(
            patch(
                "bot.music.guild_player.discord.PCMVolumeTransformer",
                return_value=object(),
            )
        )
        self.enterContext(
            patch("bot.music.guild_player.STREAM_RETRY_BASE_DELAY_SECONDS", 0)
        )

    async def asyncTearDown(self):
        pending = [self.player._prefetch_task, self.player._autoplay_task, self.task]
        self.player._cancel_next_track_prefetch()
        self.player._cancel_autoplay_lookup()
        self.player.cancel_empty_channel_timeout()
        for task in pending:
            if task and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in pending if task), return_exceptions=True
        )

    @staticmethod
    def track(video_id):
        return Track(
            url=f"https://www.youtube.com/watch?v={video_id}",
            title=video_id,
            requester="tester",
            video_id=video_id,
        )

    @staticmethod
    async def stream(url):
        video_id = url.split("v=")[1]
        return StreamInfo(
            url=f"audio-{video_id}", title=video_id, video_id=video_id, duration=60
        )

    async def start(self, *, autoplay=False, queued=()):
        self.player.set_autoplay_enabled(autoplay)
        self.player._queue.enqueue(self.seed)
        for track in queued:
            self.player._queue.enqueue(track)
        self.task = asyncio.create_task(self.player._play_loop(self.voice))
        self.player._loop_task = self.task
        self.assertIs(await self.next_started(), self.seed)

    async def next_started(self):
        return await asyncio.wait_for(self.voice.started.get(), 1)

    async def prepared(self):
        task = self.player._prefetch_task
        self.assertIsNotNone(task)
        return await asyncio.wait_for(asyncio.shield(task), 1)

    async def finish_all(self):
        self.player.set_autoplay_enabled(False)
        self.voice.finish()
        await asyncio.wait_for(self.task, 1)

    async def test_autoplay_prepares_during_playback_reuses_stream_and_announces(self):
        await self.start(autoplay=True)
        track, stream, _ = await self.prepared()
        self.assertTrue(self.voice.playing)
        self.assertIs(self.player._current, self.seed)
        self.assertEqual(track.video_id, self.next.video_id)
        self.assertEqual(stream.url, f"audio-{self.next.video_id}")
        self.radio.assert_awaited_once_with(self.seed.video_id)
        self.channel.send.assert_awaited_once()
        self.assertEqual(
            self.channel.send.await_args.kwargs["embed"].title, "🎶 再生中"
        )
        self.voice.finish()
        playing = await self.next_started()
        self.assertTrue(playing.auto_selected)
        await self.finish_all()
        self.assertEqual(
            [call.args[0] for call in self.resolve.await_args_list],
            [self.seed.url, self.next.url],
        )
        self.assertEqual(self.channel.send.await_count, 2)
        embed = self.channel.send.await_args.kwargs["embed"]
        self.assertEqual(embed.title, "🤖 自動選曲で再生中")
        self.assertIn("次の曲", embed.description)
        self.assertEqual(embed.url, self.next.url)
        self.assertEqual(embed.fields[0].value, self.next.url)
        self.assertIn(self.next.video_id, embed.thumbnail.url)

    async def test_queued_tracks_are_prepared_in_order_with_autoplay_off(self):
        await self.start(queued=[self.manual, self.next])
        prepared, _, _ = await self.prepared()
        self.assertIs(prepared, self.manual)
        self.assertEqual(
            self.player.get_queue_snapshot()["queue"], [self.manual, self.next]
        )
        self.voice.finish()
        self.assertIs(await self.next_started(), self.manual)
        prepared, _, _ = await self.prepared()
        self.assertIs(prepared, self.next)
        self.voice.finish()
        self.assertIs(await self.next_started(), self.next)
        await self.finish_all()
        self.assertEqual(
            [call.args[0] for call in self.resolve.await_args_list],
            [self.seed.url, self.manual.url, self.next.url],
        )
        self.radio.assert_not_awaited()
        self.assertEqual(self.channel.send.await_count, 3)
        self.assertEqual(
            [call.kwargs["embed"].url for call in self.channel.send.await_args_list],
            [self.seed.url, self.manual.url, self.next.url],
        )

    async def test_enqueuing_while_playing_starts_preparation_without_restarting_it(
        self,
    ):
        await self.start()
        await self.player.enqueue(self.manual, self.voice)
        original_task = self.player._prefetch_task
        await self.player.enqueue(self.next, self.voice)
        self.assertIs(self.player._prefetch_task, original_task)
        prepared, _, _ = await self.prepared()
        self.assertIs(prepared, self.manual)
        self.assertIs(self.player._current, self.seed)

    async def test_transition_waits_for_in_progress_preparation_without_resolving_twice(
        self,
    ):
        started, release = asyncio.Event(), asyncio.Event()

        async def resolve(url):
            if url == self.manual.url:
                started.set()
                await release.wait()
            return await self.stream(url)

        self.resolve.side_effect = resolve
        await self.start(queued=[self.manual])
        await asyncio.wait_for(started.wait(), 1)
        self.assertTrue(self.voice.playing)
        self.voice.finish()
        release.set()
        self.assertIs(await self.next_started(), self.manual)
        await self.finish_all()
        self.assertEqual(self.resolve.await_count, 2)

    async def test_skip_uses_prepared_queued_track(self):
        await self.start(queued=[self.manual])
        await self.prepared()
        self.assertEqual(await self.player.skip(self.voice), self.seed.title)
        self.assertIs(await self.next_started(), self.manual)
        await self.finish_all()
        self.assertEqual(self.resolve.await_count, 2)
        self.assertEqual(self.channel.send.await_count, 2)

    async def test_loop_does_not_repeat_notifications_and_queue_resumes(self):
        await self.start(queued=[self.manual])
        await self.prepared()
        self.player.toggle_loop()
        self.voice.finish()
        self.assertIs(await self.next_started(), self.seed)
        self.player.toggle_loop()
        await self.prepared()
        self.voice.finish()
        self.assertIs(await self.next_started(), self.manual)
        await self.finish_all()
        self.assertEqual(self.channel.send.await_count, 2)

    async def test_playback_retry_does_not_duplicate_notification(self):
        await self.start()
        self.voice.finish(RuntimeError("stream interrupted"))
        self.assertIs(await self.next_started(), self.seed)
        await self.finish_all()
        self.channel.send.assert_awaited_once()
        self.assertEqual(self.resolve.await_count, 2)
        self.player._notify_error.assert_not_awaited()

    async def block_next_resolution(self):
        started, cancelled = asyncio.Event(), asyncio.Event()

        async def resolve(url):
            if url == self.next.url:
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
            return await self.stream(url)

        self.resolve.side_effect = resolve
        await self.start(autoplay=True)
        await asyncio.wait_for(started.wait(), 1)
        return cancelled

    async def test_manual_request_cancels_automatic_preparation_and_plays_first(self):
        cancelled = await self.block_next_resolution()
        await self.player.enqueue(self.manual, self.voice)
        await asyncio.wait_for(cancelled.wait(), 1)
        prepared, _, _ = await self.prepared()
        self.assertIs(prepared, self.manual)
        self.voice.finish()
        self.assertIs(await self.next_started(), self.manual)
        await self.finish_all()
        self.assertEqual(self.channel.send.await_count, 2)
        self.assertEqual(
            self.channel.send.await_args.kwargs["embed"].url, self.manual.url
        )
        self.player._notify_error.assert_not_awaited()

    async def test_disabling_cancels_automatic_preparation(self):
        cancelled = await self.block_next_resolution()
        self.player.set_autoplay_enabled(False)
        await asyncio.wait_for(cancelled.wait(), 1)
        self.voice.finish()
        await asyncio.wait_for(self.task, 1)
        self.assertIsNone(self.player._prefetch_task)
        self.assertTrue(self.voice.started.empty())
        self.channel.send.assert_awaited_once()
        self.assertEqual(
            self.channel.send.await_args.kwargs["embed"].url, self.seed.url
        )

    async def test_stop_cancels_preparation_and_disconnects(self):
        cancelled = await self.block_next_resolution()
        await self.player.stop(self.voice)
        self.assertTrue(cancelled.is_set())
        self.assertFalse(self.voice.connected)
        self.assertIsNone(self.player._prefetch_task)
        self.channel.send.assert_awaited_once()

    async def test_empty_channel_cancels_preparation(self):
        cancelled = await self.block_next_resolution()
        self.voice.channel.members = []
        self.player.update_empty_channel_timeout(self.voice)
        await asyncio.wait_for(cancelled.wait(), 1)
        self.voice.finish()
        await asyncio.wait_for(self.task, 1)
        self.assertTrue(self.voice.started.empty())

    async def test_human_returning_restarts_queued_preparation(self):
        await self.start(queued=[self.manual])
        await self.prepared()
        self.voice.channel.members = []
        self.player.update_empty_channel_timeout(self.voice)
        self.assertIsNone(self.player._prefetch_task)
        self.voice.channel.members = [SimpleNamespace(bot=False)]
        self.player.update_empty_channel_timeout(self.voice)
        prepared, _, _ = await self.prepared()
        self.assertIs(prepared, self.manual)
        self.voice.finish()
        self.assertIs(await self.next_started(), self.manual)
        await self.finish_all()

    async def test_loop_cancels_preparation_and_disabling_loop_restarts_it(self):
        cancelled = await self.block_next_resolution()
        self.assertTrue(self.player.toggle_loop())
        await asyncio.wait_for(cancelled.wait(), 1)
        self.assertIsNone(self.player._prefetch_task)
        self.resolve.side_effect = self.stream
        self.assertFalse(self.player.toggle_loop())
        prepared, _, _ = await self.prepared()
        self.assertEqual(prepared.video_id, self.next.video_id)

    async def test_enabling_autoplay_mid_track_starts_preparation(self):
        await self.start()
        self.assertIsNone(self.player._prefetch_task)
        self.player.set_autoplay_enabled(True)
        prepared, _, _ = await self.prepared()
        self.assertEqual(prepared.video_id, self.next.video_id)
        self.assertTrue(self.voice.playing)

    async def test_disabling_autoplay_preserves_manual_preparation(self):
        await self.start(autoplay=True, queued=[self.manual])
        original_task = self.player._prefetch_task
        self.player.set_autoplay_enabled(False)
        self.assertIs(self.player._prefetch_task, original_task)
        prepared, _, _ = await self.prepared()
        self.assertIs(prepared, self.manual)
        self.voice.finish()
        self.assertIs(await self.next_started(), self.manual)
        await self.finish_all()
        self.assertEqual(self.resolve.await_count, 2)

    async def test_clearing_queue_discards_manual_preparation_and_uses_autoplay(self):
        await self.start(autoplay=True, queued=[self.manual])
        await self.prepared()
        self.assertEqual(self.player.clear_queue(), 1)
        prepared, _, _ = await self.prepared()
        self.assertTrue(prepared.auto_selected)
        self.voice.finish()
        self.assertEqual((await self.next_started()).video_id, self.next.video_id)
        await self.finish_all()
        self.assertEqual(
            [call.args[0] for call in self.resolve.await_args_list],
            [self.seed.url, self.manual.url, self.next.url],
        )

    async def test_expired_preparation_refreshes_url_at_transition(self):
        await self.start(queued=[self.manual])
        await self.prepared()
        with patch("bot.music.guild_player.PREFETCH_MAX_AGE_SECONDS", -1):
            self.voice.finish()
            self.assertIs(await self.next_started(), self.manual)
        await self.finish_all()
        self.assertEqual(
            [call.args[0] for call in self.resolve.await_args_list],
            [self.seed.url, self.manual.url, self.manual.url],
        )

    async def test_prefetch_failure_retries_at_transition_without_skipping_track(self):
        calls = 0

        async def resolve(url):
            nonlocal calls
            if url == self.manual.url:
                calls += 1
                if calls == 1:
                    raise StreamError("temporary failure")
            return await self.stream(url)

        self.resolve.side_effect = resolve
        await self.start(queued=[self.manual])
        track, stream, _ = await self.prepared()
        self.assertIs(track, self.manual)
        self.assertIsNone(stream)
        self.assertTrue(self.voice.playing)
        self.voice.finish()
        self.assertIs(await self.next_started(), self.manual)
        await self.finish_all()
        self.assertEqual(calls, 2)
        self.player._notify_error.assert_not_awaited()

    async def test_failed_voice_start_does_not_announce_or_prefetch(self):
        self.next.auto_selected = True
        self.voice.play = Mock(side_effect=RuntimeError("not connected"))
        with self.assertRaisesRegex(RuntimeError, "not connected"):
            await self.player._play_stream(self.voice, "audio", self.next, 60)
        self.channel.send.assert_not_awaited()
        self.assertIsNone(self.player._prefetch_task)

    async def test_slow_notification_does_not_delay_next_track(self):
        sending, cancelled = asyncio.Event(), asyncio.Event()

        async def send(**kwargs):
            sending.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        await self.start(autoplay=True)
        self.channel.send.side_effect = send
        await self.prepared()
        self.voice.finish()
        await self.next_started()
        await asyncio.wait_for(sending.wait(), 1)
        await self.player.enqueue(self.manual, self.voice)
        await self.prepared()
        self.voice.finish()
        self.assertIs(await self.next_started(), self.manual)
        self.assertTrue(cancelled.is_set())
        await self.finish_all()

    async def test_notification_errors_do_not_interrupt_playback(self):
        self.channel.send.side_effect = discord.Forbidden(
            SimpleNamespace(status=403, reason="Forbidden"), "denied"
        )
        await self.start(autoplay=True)
        await self.prepared()
        self.voice.finish()
        await self.next_started()
        await self.finish_all()
        self.player._notify_error.assert_not_awaited()

    async def test_title_is_escaped_and_mentions_are_disabled(self):
        self.next.title = "**曲名** @everyone [リンク](https://example.com)"
        await self.player._send_now_playing(self.next)
        args = self.channel.send.await_args.kwargs
        self.assertIn(r"\*\*曲名\*\*", args["embed"].description)
        self.assertNotIn("@everyone", args["embed"].description)
        self.assertEqual(args["allowed_mentions"].to_dict(), {"parse": []})


if __name__ == "__main__":
    unittest.main()
