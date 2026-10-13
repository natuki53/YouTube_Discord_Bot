import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from bot.commands.music import setup_music_commands
from bot.config.discord_config import create_bot_instance
from bot.youtube.search import PlayTarget, SearchError


class PlayNotificationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = create_bot_instance("!")
        self.player = Mock(
            enqueue=AsyncMock(return_value="playing"),
            get_queue_snapshot=Mock(return_value={"queue": []}),
        )
        self.manager = Mock(get=Mock(return_value=self.player))
        setup_music_commands(self.bot, self.manager)
        self.command = self.bot.tree.get_command("play")
        self.channel = SimpleNamespace(connect=AsyncMock())
        self.voice = SimpleNamespace(is_connected=lambda: True)
        self.interaction = SimpleNamespace(
            guild_id=123,
            channel_id=456,
            guild=SimpleNamespace(voice_client=self.voice),
            user=SimpleNamespace(
                display_name="依頼者", voice=SimpleNamespace(channel=self.channel)
            ),
            response=SimpleNamespace(send_message=AsyncMock(), defer=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),
            edit_original_response=AsyncMock(),
            delete_original_response=AsyncMock(),
        )
        self.target = PlayTarget(
            url="https://www.youtube.com/watch?v=video-id", display_title="確定した曲名"
        )

    def assert_no_extra_messages(self):
        self.interaction.response.send_message.assert_awaited_once()
        self.interaction.response.defer.assert_not_awaited()
        self.interaction.followup.send.assert_not_awaited()
        self.interaction.delete_original_response.assert_not_awaited()

    async def test_receipt_is_visible_while_search_is_still_pending(self):
        started = asyncio.Event()
        release = asyncio.Event()

        async def search(_resolver, query):
            self.assertEqual(query, "入力した曲名")
            started.set()
            await release.wait()
            return self.target

        with patch("bot.commands.music.asyncio.to_thread", side_effect=search):
            task = asyncio.create_task(
                self.command.callback(self.interaction, "入力した曲名")
            )
            try:
                await asyncio.wait_for(started.wait(), 1)
                sent = self.interaction.response.send_message.await_args.kwargs
                self.assertFalse(sent.get("ephemeral", False))
                self.assertEqual(sent["embed"].title, "🎵 リクエストを受け付けました")
                self.assertEqual(sent["embed"].fields[0].value, "入力した曲名")
                self.interaction.edit_original_response.assert_not_awaited()
                self.player.enqueue.assert_not_awaited()
            finally:
                release.set()
                await asyncio.wait_for(task, 1)

        self.assert_no_extra_messages()
        self.interaction.edit_original_response.assert_awaited_once()
        updated = self.interaction.edit_original_response.await_args.kwargs
        self.assertIsNone(updated["content"])
        self.assertIn(self.target.display_title, updated["embed"].description)
        self.assertIn(self.target.url, [f.value for f in updated["embed"].fields])
        self.assertIn("依頼者", [f.value for f in updated["embed"].fields])
        self.assertEqual(
            updated["embed"].thumbnail.url,
            "https://i.ytimg.com/vi/video-id/hqdefault.jpg",
        )

    async def test_queued_request_updates_receipt_with_queue_position(self):
        self.player.enqueue.return_value = "queued"
        self.player.get_queue_snapshot.return_value = {"queue": [Mock(), Mock()]}
        with patch("bot.commands.music.resolve_play_query", return_value=self.target):
            await self.command.callback(self.interaction, "曲名")

        self.assert_no_extra_messages()
        self.interaction.edit_original_response.assert_awaited_once()
        embed = self.interaction.edit_original_response.await_args.kwargs["embed"]
        self.assertEqual(embed.title, "🎵 リクエストを受け付けました")
        self.assertIn("2 番目", [f.value for f in embed.fields])
        self.assertEqual(embed.footer.text, "順番に再生します。")

    async def test_search_errors_replace_receipt_instead_of_sending_followups(self):
        cases = [
            (asyncio.TimeoutError(), "❌ 曲の検索がタイムアウトしました。"),
            (SearchError("動画が見つかりません。"), "❌ 動画が見つかりません。"),
            (RuntimeError("lookup failed"), "❌ 曲の検索に失敗しました。"),
        ]
        for error, message in cases:
            with self.subTest(error=type(error).__name__):
                self.interaction.response.send_message.reset_mock()
                self.interaction.edit_original_response.reset_mock()
                with patch("bot.commands.music.resolve_play_query", side_effect=error):
                    await self.command.callback(self.interaction, "曲名")
                self.assert_no_extra_messages()
                self.interaction.edit_original_response.assert_awaited_once_with(
                    content=message, embed=None
                )
                self.player.enqueue.assert_not_awaited()

    async def test_leaving_voice_during_search_replaces_receipt_with_error(self):
        def search(query):
            self.interaction.user.voice = None
            return self.target

        with patch("bot.commands.music.resolve_play_query", side_effect=search):
            await self.command.callback(self.interaction, "曲名")

        self.assert_no_extra_messages()
        self.interaction.edit_original_response.assert_awaited_once_with(
            content="❌ ボイスチャンネルに接続してから使用してください。", embed=None
        )
        self.player.enqueue.assert_not_awaited()

    async def test_voice_connection_errors_replace_receipt(self):
        self.interaction.guild.voice_client = None
        for error, expected in [
            (RuntimeError("davey missing"), "`davey` が未インストール"),
            (RuntimeError("PyNaCl missing"), "`PyNaCl` が未インストール"),
            (RuntimeError("connect failed"), "権限を確認してください。"),
        ]:
            with self.subTest(error=str(error)):
                self.interaction.response.send_message.reset_mock()
                self.interaction.edit_original_response.reset_mock()
                self.channel.connect.side_effect = error
                with patch(
                    "bot.commands.music.resolve_play_query", return_value=self.target
                ):
                    await self.command.callback(self.interaction, "曲名")
                self.assert_no_extra_messages()
                self.interaction.edit_original_response.assert_awaited_once()
                updated = self.interaction.edit_original_response.await_args.kwargs
                self.assertIn(expected, updated["content"])
                self.assertIsNone(updated["embed"])
                self.player.enqueue.assert_not_awaited()

    async def test_enqueue_failure_replaces_receipt_with_error(self):
        self.player.enqueue.side_effect = RuntimeError("enqueue failed")
        with patch("bot.commands.music.resolve_play_query", return_value=self.target):
            await self.command.callback(self.interaction, "曲名")

        self.assert_no_extra_messages()
        updated = self.interaction.edit_original_response.await_args.kwargs
        self.assertIn("リクエストを追加できませんでした", updated["content"])
        self.assertIsNone(updated["embed"])

    async def test_invalid_input_and_missing_voice_still_reply_privately(self):
        for query, in_voice in [("   ", True), ("曲名", False)]:
            with self.subTest(query=query):
                self.interaction.response.send_message.reset_mock()
                self.interaction.user.voice = (
                    SimpleNamespace(channel=self.channel) if in_voice else None
                )
                with patch("bot.commands.music.resolve_play_query") as search:
                    await self.command.callback(self.interaction, query)
                    search.assert_not_called()
                self.assertTrue(
                    self.interaction.response.send_message.await_args.kwargs["ephemeral"]
                )
                self.interaction.edit_original_response.assert_not_awaited()
                self.player.enqueue.assert_not_awaited()

    async def test_long_input_is_bounded_and_mentions_are_escaped_in_receipt(self):
        query = "@everyone **曲名** " * 200
        with patch(
            "bot.commands.music.resolve_play_query", return_value=self.target
        ) as search:
            await self.command.callback(self.interaction, query)
        search.assert_called_once_with(query)
        initial = self.interaction.response.send_message.await_args.kwargs["embed"]
        self.assertLessEqual(len(initial.fields[0].value), 1024)
        self.assertNotIn("@everyone", initial.fields[0].value)
        self.assertTrue(initial.fields[0].value.endswith("..."))


if __name__ == "__main__":
    unittest.main()
