"""
/play コマンド登録
"""

import asyncio
import logging
import discord

from ..audio import AudioQueue, AudioPlayer, TrackInfo
from ..youtube import get_title_from_url, validate_youtube_url, normalize_youtube_url
from .music_ui import build_progress_embed, safe_edit_message, get_next_queue_title
from .music_playback import download_and_play_track

logger = logging.getLogger(__name__)


def register_play_command(bot, audio_queue: AudioQueue, audio_player: AudioPlayer):
    @bot.tree.command(name='play', description='Play YouTube audio in voice channel')
    async def play_audio(interaction: discord.Interaction, url: str):
        if not interaction.user.voice:
            await interaction.response.send_message("❌ ボイスチャンネルに接続してから使用してください。", ephemeral=True)
            return

        if not validate_youtube_url(url):
            await interaction.response.send_message("❌ 有効なYouTube URLを入力してください。", ephemeral=True)
            return

        normalized_url = normalize_youtube_url(url, remove_list_param=True)
        if normalized_url:
            url = normalized_url

        guild_id = interaction.guild_id
        voice_client = interaction.guild.voice_client

        if not voice_client or not voice_client.is_connected():
            try:
                voice_channel = interaction.user.voice.channel
                if not voice_channel:
                    await interaction.response.send_message("❌ ボイスチャンネルに接続してから使用してください。", ephemeral=True)
                    return
                voice_client = await voice_channel.connect()
                if not voice_client.is_connected():
                    await interaction.response.send_message("❌ ボイスチャンネルへの接続に失敗しました。", ephemeral=True)
                    return
            except Exception:
                logger.exception("Failed to connect to voice channel")
                await interaction.response.send_message("❌ ボイスチャンネルに接続できませんでした。権限を確認してください。", ephemeral=True)
                return

        initial_embed = build_progress_embed(
            title="⏳ 処理中",
            status="動画情報を取得中...",
            url=url,
            requester=interaction.user.display_name,
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=initial_embed)
        progress_message = await interaction.original_response()

        from ..youtube import YouTubeDownloader
        downloader = YouTubeDownloader()
        video_title = downloader.get_video_title(url)
        if video_title == "Unknown Title":
            video_title = get_title_from_url(url)

        await safe_edit_message(
            progress_message,
            embed=build_progress_embed(
                title="⏳ 処理中",
                status="準備完了。再生/キュー処理中...",
                url=url,
                track_title=video_title,
                requester=interaction.user.display_name,
                queue_length=audio_queue.get_queue_length(guild_id),
                next_title=get_next_queue_title(audio_queue, guild_id),
                color=discord.Color.blue()
            )
        )

        track_info = TrackInfo(
            url=url,
            title=video_title,
            user=interaction.user.display_name,
            added_at=interaction.created_at
        )

        playback_lock = await audio_queue.get_playback_lock(guild_id)
        async with playback_lock:
            audio_queue.set_text_channel(guild_id, interaction.channel_id)

            is_currently_playing = audio_player.is_playing(voice_client) or audio_queue.is_playing(guild_id)
            is_starting_playback = audio_queue.is_starting_playback_active(guild_id)

            if is_currently_playing or is_starting_playback:
                # シンプル方針: 再生中/再生準備中に来た /play は「順番通りにキューへ追加」するだけ
                # 事前ダウンロードは AudioQueue.add_track() が start_preload() を呼ぶため、個別タスクは作らない
                audio_queue.add_track(guild_id, track_info)
                await safe_edit_message(
                    progress_message,
                    embed=build_progress_embed(
                        title="🎵 キューに追加",
                        status="キューに追加しました。順番をお待ちください。",
                        url=url,
                        track_title=video_title,
                        requester=interaction.user.display_name,
                        queue_length=audio_queue.get_queue_length(guild_id),
                        next_title=get_next_queue_title(audio_queue, guild_id),
                        color=discord.Color.blue()
                    )
                )
            else:
                audio_queue.cancel_idle_timeout(guild_id)
                audio_queue.set_starting_playback(guild_id, True)

                await safe_edit_message(
                    progress_message,
                    embed=build_progress_embed(
                        title="⏳ 処理中",
                        status="ダウンロード中...",
                        url=url,
                        track_title=video_title,
                        requester=interaction.user.display_name,
                        queue_length=audio_queue.get_queue_length(guild_id),
                        next_title=get_next_queue_title(audio_queue, guild_id),
                        color=discord.Color.blue()
                    )
                )

                task_id = f"guild_{guild_id}_play_{hash(track_info.url)}"
                task = asyncio.create_task(download_and_play_track(
                    guild_id, track_info, voice_client, audio_queue, audio_player, interaction.channel_id, progress_message
                ))
                audio_queue.register_task(task_id, task)


