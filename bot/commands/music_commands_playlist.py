"""
/playlist と「続きを読み込む」ボタン
"""

import asyncio
import logging
import time
import discord
from discord import app_commands

from ..audio import AudioQueue, AudioPlayer, TrackInfo
from ..youtube import validate_youtube_url, is_playlist_url
from .music_ui import build_progress_embed, safe_edit_message, get_next_queue_title
from .music_playback import download_and_play_track

logger = logging.getLogger(__name__)


def register_playlist_command(bot, audio_queue: AudioQueue, audio_player: AudioPlayer):
    @bot.tree.command(name='playlist', description='Add entire YouTube playlist to queue')
    @app_commands.describe(
        url='YouTubeプレイリストのURL',
        count='追加する曲数（デフォルト: 10、最大: 50）'
    )
    async def add_playlist(interaction: discord.Interaction, url: str, count: int = 10):
        if not interaction.user.voice:
            await interaction.response.send_message("❌ ボイスチャンネルに接続してから使用してください。", ephemeral=True)
            return

        if not validate_youtube_url(url):
            await interaction.response.send_message("❌ 有効なYouTube URLを入力してください。", ephemeral=True)
            return

        if not is_playlist_url(url):
            embed = discord.Embed(
                title="❌ プレイリストURLが必要です",
                description="このコマンドはプレイリストURL専用です。\n\n**使用方法:**\n• `/playlist` コマンドにプレイリストURLを指定\n• 個別の動画を再生する場合は `/play` コマンドを使用",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        initial_embed = build_progress_embed(
            title="⏳ 処理中",
            status="プレイリスト情報を取得中...",
            url=url,
            requester=interaction.user.display_name,
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=initial_embed)
        progress_message = await interaction.original_response()

        from ..youtube import YouTubeDownloader
        downloader = YouTubeDownloader()

        playlist_info = await asyncio.get_event_loop().run_in_executor(
            None, downloader.get_playlist_info, url
        )

        playlist_title = playlist_info.get('title', 'Unknown Playlist')

        await safe_edit_message(
            progress_message,
            embed=build_progress_embed(
                title="⏳ 処理中",
                status="動画URLを取得中...",
                url=url,
                track_title=playlist_title,
                requester=interaction.user.display_name,
                queue_length=audio_queue.get_queue_length(interaction.guild_id),
                next_title=get_next_queue_title(audio_queue, interaction.guild_id),
                color=discord.Color.blue()
            )
        )

        if count < 1:
            count = 10
        elif count > 50:
            count = 50

        start_index = 1
        if '&index=' in url or '?index=' in url:
            try:
                import re
                index_match = re.search(r'[?&]index=(\d+)', url)
                if index_match:
                    start_index = int(index_match.group(1))
            except Exception:
                pass

        end_index = start_index + count - 1
        video_urls = await asyncio.get_event_loop().run_in_executor(
            None, downloader.get_playlist_video_urls_range, url, start_index, end_index
        )

        if not video_urls:
            embed = discord.Embed(
                title="❌ プレイリストの取得に失敗しました",
                description="指定範囲の動画URLを取得できませんでした。\nプレイリストが非公開/存在しない/範囲外の可能性があります。",
                color=discord.Color.red()
            )
            await safe_edit_message(progress_message, embed=embed)
            return

        guild_id = interaction.guild_id
        voice_client = interaction.guild.voice_client

        total_count = playlist_info.get('video_count', 0) or 0
        next_index = start_index + len(video_urls)
        has_more = (total_count == 0) or (next_index <= total_count)
        if has_more:
            audio_queue.playlist_remaining[guild_id] = {
                'url': url,
                'user': interaction.user.display_name,
                'added_at': interaction.created_at,
                'playlist_title': playlist_title,
                'total_count': total_count,
                'loaded_count': len(video_urls),
                'start_index': start_index,
                'current_index': next_index
            }

        # View
        class LoadMoreView(discord.ui.View):
            def __init__(self, guild_id: int, audio_queue: AudioQueue, audio_player: AudioPlayer, voice_client, channel_id: int, command_user_id: int):
                super().__init__(timeout=3600)
                self.guild_id = guild_id
                self.audio_queue = audio_queue
                self.audio_player = audio_player
                self.voice_client = voice_client
                self.channel_id = channel_id
                self.command_user_id = command_user_id

            @discord.ui.button(label="続きを読み込む (10曲)", style=discord.ButtonStyle.primary, emoji="📥")
            async def load_more_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                if button_interaction.user.id != self.command_user_id:
                    await button_interaction.response.send_message("❌ このボタンはコマンドを実行したユーザーのみ使用できます。", ephemeral=True)
                    return

                if self.guild_id not in self.audio_queue.playlist_remaining:
                    await button_interaction.response.send_message("❌ 読み込む残りの曲がありません。", ephemeral=True)
                    return

                remaining_info = self.audio_queue.playlist_remaining[self.guild_id]
                current_index = remaining_info.get('current_index', 1)
                total_count = remaining_info.get('total_count', 0) or 0

                from ..youtube import YouTubeDownloader
                downloader = YouTubeDownloader()
                next_end = current_index + 10 - 1
                next_batch = await asyncio.get_event_loop().run_in_executor(
                    None, downloader.get_playlist_video_urls_range, remaining_info['url'], current_index, next_end
                )

                if not next_batch:
                    try:
                        del self.audio_queue.playlist_remaining[self.guild_id]
                    except Exception:
                        pass
                    await button_interaction.response.send_message("❌ 続きの曲を取得できませんでした（終端またはエラー）。", ephemeral=True)
                    return

                # 状態更新
                self.audio_queue.playlist_remaining[self.guild_id]['loaded_count'] += len(next_batch)
                self.audio_queue.playlist_remaining[self.guild_id]['current_index'] = current_index + len(next_batch)

                reached_end = False
                if total_count > 0:
                    reached_end = self.audio_queue.playlist_remaining[self.guild_id]['current_index'] > total_count
                else:
                    reached_end = len(next_batch) < 10

                if reached_end:
                    del self.audio_queue.playlist_remaining[self.guild_id]

                await button_interaction.response.defer()
                try:
                    await button_interaction.message.edit(
                        embed=build_progress_embed(
                            title="⏳ 処理中",
                            status="続きを読み込み中...",
                            url=remaining_info.get('url'),
                            track_title=remaining_info.get('playlist_title'),
                            requester=remaining_info.get('user'),
                            queue_length=self.audio_queue.get_queue_length(self.guild_id),
                            next_title=get_next_queue_title(self.audio_queue, self.guild_id),
                            color=discord.Color.blue()
                        ),
                        view=self
                    )
                except Exception:
                    pass

                # タイトル取得してキュー追加（順番維持）
                async def add_tracks():
                    batch_with_index = [(current_index + i, u) for i, u in enumerate(next_batch)]

                    async def get_title_and_pack(index_url_pair):
                        index, u = index_url_pair
                        try:
                            t = await asyncio.get_event_loop().run_in_executor(None, downloader.get_video_title, u)
                        except Exception:
                            t = "Unknown Title"
                        return (index, TrackInfo(url=u, title=t, user=remaining_info['user'], added_at=remaining_info['added_at']))

                    results = await asyncio.gather(*[get_title_and_pack(p) for p in batch_with_index], return_exceptions=False)
                    results.sort(key=lambda x: x[0])
                    for _, ti in results:
                        self.audio_queue.add_track(self.guild_id, ti)

                task_id = f"guild_{self.guild_id}_playlist_load_more_{int(time.time() * 1000)}"
                self.audio_queue.register_task(task_id, asyncio.create_task(add_tracks()))

                if reached_end:
                    button.disabled = True
                    button.label = "すべて読み込み完了"
                    await button_interaction.message.edit(view=self)
                else:
                    try:
                        await button_interaction.message.edit(
                            embed=build_progress_embed(
                                title="✅ 読み込み完了",
                                status=f"{len(next_batch)}曲を追加しました。",
                                url=remaining_info.get('url'),
                                track_title=remaining_info.get('playlist_title'),
                                requester=remaining_info.get('user'),
                                queue_length=self.audio_queue.get_queue_length(self.guild_id),
                                next_title=get_next_queue_title(self.audio_queue, self.guild_id),
                                color=discord.Color.green()
                            ),
                            view=self
                        )
                    except Exception:
                        pass

        remaining_info = audio_queue.playlist_remaining.get(guild_id)
        view = LoadMoreView(guild_id, audio_queue, audio_player, voice_client, interaction.channel_id, interaction.user.id) if remaining_info else None

        await safe_edit_message(
            progress_message,
            embed=build_progress_embed(
                title="✅ 読み込み完了",
                status=f"{len(video_urls)}曲を読み込みました。",
                url=url,
                track_title=playlist_title,
                requester=interaction.user.display_name,
                queue_length=audio_queue.get_queue_length(guild_id),
                next_title=get_next_queue_title(audio_queue, guild_id),
                color=discord.Color.green()
            ),
            view=view
        )

        if not voice_client or not voice_client.is_connected():
            try:
                voice_channel = interaction.user.voice.channel
                if not voice_channel:
                    await interaction.followup.send("❌ ボイスチャンネルに接続してから使用してください。", ephemeral=True)
                    return
                voice_client = await voice_channel.connect()
                if not voice_client.is_connected():
                    await interaction.followup.send("❌ ボイスチャンネルへの接続に失敗しました。", ephemeral=True)
                    return
            except Exception:
                logger.exception("Failed to connect to voice channel")
                await interaction.followup.send("❌ ボイスチャンネルに接続できませんでした。権限を確認してください。", ephemeral=True)
                return

        audio_queue.set_text_channel(guild_id, interaction.channel_id)

        is_currently_playing = audio_player.is_playing(voice_client) or audio_queue.is_playing(guild_id)
        is_starting_playback = audio_queue.is_starting_playback_active(guild_id)

        first_track = None
        if video_urls:
            first_url = video_urls[0]
            first_title = await asyncio.get_event_loop().run_in_executor(None, downloader.get_video_title, first_url)
            first_track = TrackInfo(url=first_url, title=first_title, user=interaction.user.display_name, added_at=interaction.created_at)
            if is_currently_playing or is_starting_playback:
                audio_queue.add_track(guild_id, first_track)

        async def add_remaining_tracks():
            if len(video_urls) <= 1:
                return
            remaining = video_urls[1:]
            async def get_title(u):
                try:
                    return await asyncio.get_event_loop().run_in_executor(None, downloader.get_video_title, u)
                except Exception:
                    return "Unknown Title"
            titles = await asyncio.gather(*[get_title(u) for u in remaining], return_exceptions=False)
            for u, t in zip(remaining, titles):
                audio_queue.add_track(guild_id, TrackInfo(url=u, title=t, user=interaction.user.display_name, added_at=interaction.created_at))

        if len(video_urls) > 1:
            task_id = f"guild_{guild_id}_playlist_add_{int(time.time() * 1000)}"
            audio_queue.register_task(task_id, asyncio.create_task(add_remaining_tracks()))

        if not is_currently_playing and not is_starting_playback and first_track:
            audio_queue.cancel_idle_timeout(guild_id)
            audio_queue.set_starting_playback(guild_id, True)
            task_id = f"guild_{guild_id}_play_{hash(first_track.url)}"
            task = asyncio.create_task(download_and_play_track(
                guild_id, first_track, voice_client, audio_queue, audio_player, interaction.channel_id, progress_message
            ))
            audio_queue.register_task(task_id, task)
        else:
            audio_queue.start_preload(guild_id)


