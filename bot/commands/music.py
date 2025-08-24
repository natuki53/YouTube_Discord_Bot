"""
音楽関連コマンド

音声再生、キュー管理、プレイバック制御コマンド
"""

import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import logging

from ..audio import AudioQueue, AudioPlayer, TrackInfo
from ..youtube import get_title_from_url, validate_youtube_url, normalize_youtube_url
from ..utils.file_utils import cleanup_old_audio_files, force_kill_ffmpeg_processes

logger = logging.getLogger(__name__)

def setup_music_commands(bot, audio_queue: AudioQueue, audio_player: AudioPlayer, download_dir: str):
    """音楽関連コマンドをセットアップ"""

    @bot.tree.command(name='play', description='Play YouTube audio in voice channel')
    async def play_audio(interaction: discord.Interaction, url: str):
        """YouTubeの音声を再生するコマンド"""
        # ユーザーがボイスチャンネルに接続しているかチェック
        if not interaction.user.voice:
            await interaction.response.send_message(
                "❌ ボイスチャンネルに接続してから使用してください。",
                ephemeral=True
            )
            return
        
        # URL検証
        if not validate_youtube_url(url):
            await interaction.response.send_message(
                "❌ 有効なYouTube URLを入力してください。",
                ephemeral=True
            )
            return
        
        # URLを正規化
        normalized_url = normalize_youtube_url(url)
        if normalized_url:
            url = normalized_url
        
        guild_id = interaction.guild_id
        voice_client = interaction.guild.voice_client
        
        # ボイスチャンネルに接続していない場合は接続を試行
        if not voice_client or not voice_client.is_connected():
            try:
                voice_channel = interaction.user.voice.channel
                voice_client = await voice_channel.connect()
                logger.info(f"Connected to voice channel: {voice_channel.name}")
            except Exception as e:
                logger.error(f"Failed to connect to voice channel: {e}")
                await interaction.response.send_message(
                    "❌ ボイスチャンネルに接続できませんでした。",
                    ephemeral=True
                )
                return
        
        # 即座に応答
        embed = discord.Embed(
            title="🎵 音声準備開始",
            description=f"**URL：** {url}\n👤 **リクエスト:** {interaction.user.display_name}",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="⏳ ステータス",
            value="動画情報を取得中...",
            inline=False
        )
        await interaction.response.send_message(embed=embed)
        
        # URLからタイトルを取得
        video_title = get_title_from_url(url)
        
        # トラック情報を作成
        track_info = TrackInfo(
            url=url,
            title=video_title,
            user=interaction.user.display_name,
            added_at=interaction.created_at
        )
        
        # 既に再生中の場合はキューに追加
        if audio_player.is_playing(voice_client):
            audio_queue.add_track(guild_id, track_info)
            
            # キューに追加メッセージを更新
            embed = discord.Embed(
                title="🎵 キューに追加",
                description=f"**タイトル：** {video_title}\n\n**URL：** {url}\n👤 **リクエスト:** {interaction.user.display_name}\n📋 **現在のキュー:** {audio_queue.get_queue_length(guild_id)}曲",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="⏳ ステータス",
                value="キューに追加されました。順番をお待ちください。",
                inline=False
            )
            await interaction.followup.send(embed=embed)
            
            # バックグラウンドでダウンロード開始
            asyncio.create_task(start_background_download(guild_id, track_info, audio_queue))
        else:
            # 即座に再生開始
            asyncio.create_task(download_and_play_track(
                guild_id, track_info, voice_client, audio_queue, audio_player, interaction.channel_id
            ))

    @bot.tree.command(name='stop', description='Stop audio playback and disconnect from voice channel')
    async def stop_audio(interaction: discord.Interaction):
        """音声再生を停止し、ボイスチャンネルから切断するコマンド"""
        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.response.send_message(
                "❌ ボイスチャンネルに接続していません。",
                ephemeral=True
            )
            return
        
        try:
            guild_id = interaction.guild_id
            
            # 音声再生を停止
            audio_player.stop_playback(guild_id, voice_client)
            
            # キューと現在再生中のトラックをクリア
            audio_queue.clear_queue(guild_id)
            audio_queue.clear_now_playing(guild_id)
            
            # 少し待ってから切断
            await asyncio.sleep(1)
            
            # ボイスチャンネルから切断
            await voice_client.disconnect()
            logger.info("Disconnected from voice channel")
            
            embed = discord.Embed(
                title="🛑 再生停止",
                description="音声再生を停止し、ボイスチャンネルから切断しました。\nキューもクリアされました。",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            logger.error(f"Stop command error: {e}")
            await interaction.response.send_message("❌ 音声停止に失敗しました。")

    @bot.tree.command(name='pause', description='Pause audio playback')
    async def pause_audio(interaction: discord.Interaction):
        """音声再生を一時停止するコマンド"""
        voice_client = interaction.guild.voice_client
        if not audio_player.is_playing(voice_client):
            await interaction.response.send_message(
                "❌ 現在音声を再生していません。",
                ephemeral=True
            )
            return
        
        try:
            if audio_player.pause_playback(voice_client):
                embed = discord.Embed(
                    title="⏸️ 一時停止",
                    description="音声再生を一時停止しました。",
                    color=discord.Color.yellow()
                )
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message("❌ 一時停止に失敗しました。")
        except Exception as e:
            logger.error(f"Pause command error: {e}")
            await interaction.response.send_message("❌ 一時停止に失敗しました。")

    @bot.tree.command(name='resume', description='Resume audio playback')
    async def resume_audio(interaction: discord.Interaction):
        """音声再生を再開するコマンド"""
        voice_client = interaction.guild.voice_client
        if not audio_player.is_paused(voice_client):
            await interaction.response.send_message(
                "❌ 現在音声は一時停止されていません。",
                ephemeral=True
            )
            return
        
        try:
            if audio_player.resume_playback(voice_client):
                embed = discord.Embed(
                    title="▶️ 再生再開",
                    description="音声再生を再開しました。",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message("❌ 再生再開に失敗しました。")
        except Exception as e:
            logger.error(f"Resume command error: {e}")
            await interaction.response.send_message("❌ 再生再開に失敗しました。")

    @bot.tree.command(name='queue', description='Show current music queue')
    async def show_queue(interaction: discord.Interaction):
        """現在の音楽キューを表示するコマンド"""
        guild_id = interaction.guild_id
        queue = audio_queue.get_queue(guild_id)
        now_playing = audio_queue.get_now_playing(guild_id)
        
        embed = discord.Embed(
            title="🎵 音楽キュー",
            color=discord.Color.blue()
        )
        
        if now_playing:
            embed.add_field(
                name="🎶 現在再生中",
                value=f"**{now_playing.title}**\n追加者: {now_playing.user}",
                inline=False
            )
        
        if queue:
            queue_text = ""
            for i, track in enumerate(queue[:10], 1):  # 最大10曲まで表示
                queue_text += f"{i}. **{track.title}**\n   追加者: {track.user}\n"
            
            if len(queue) > 10:
                queue_text += f"\n... 他 {len(queue) - 10} 曲"
            
            embed.add_field(
                name=f"📋 キュー ({len(queue)}曲)",
                value=queue_text,
                inline=False
            )
        else:
            embed.add_field(
                name="📋 キュー",
                value="キューは空です。",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name='clear', description='Clear music queue')
    async def clear_queue(interaction: discord.Interaction):
        """音楽キューをクリアするコマンド"""
        guild_id = interaction.guild_id
        audio_queue.clear_queue(guild_id)
        
        embed = discord.Embed(
            title="🗑️ キューをクリア",
            description="音楽キューがクリアされました。\n現在再生中の曲は影響を受けません。",
            color=discord.Color.orange()
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name='skip', description='Skip current track and play next track in queue')
    async def skip_audio(interaction: discord.Interaction):
        """現在再生中の曲をスキップするコマンド"""
        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.response.send_message(
                "❌ ボイスチャンネルに接続していません。",
                ephemeral=True
            )
            return
        
        if not audio_player.is_playing(voice_client):
            await interaction.response.send_message(
                "❌ 現在音声を再生していません。",
                ephemeral=True
            )
            return
        
        try:
            guild_id = interaction.guild_id
            current_track = audio_queue.get_now_playing(guild_id)
            current_title = current_track.title if current_track else 'Unknown Track'
            
            # 次の曲があるかチェック
            next_track = audio_queue.get_queue(guild_id)[0] if audio_queue.has_queue(guild_id) else None
            next_title = next_track.title if next_track else None
            
            # 即座に応答を送信
            embed = discord.Embed(
                title="⏭️ スキップ",
                description=f"**現在の曲をスキップします**\n\n🎵 **スキップする曲：** {current_title}",
                color=discord.Color.blue()
            )
            if next_title:
                embed.add_field(
                    name="⏭️ 次の曲",
                    value=next_title,
                    inline=False
                )
            await interaction.response.send_message(embed=embed)
            
            # 現在の曲を停止（これにより次の曲が自動再生される）
            voice_client.stop()
            logger.info(f"Skipped track: {current_title}")
            
        except Exception as e:
            logger.error(f"Skip command error: {e}")
            await interaction.response.send_message(
                "❌ スキップに失敗しました。",
                ephemeral=True
            )

async def download_and_play_track(guild_id: int, track_info: TrackInfo, voice_client, 
                                 audio_queue: AudioQueue, audio_player: AudioPlayer, text_channel_id: int = None):
    """トラックをダウンロードして再生する"""
    try:
        from ..youtube import YouTubeDownloader
        
        downloader = YouTubeDownloader()
        
        # MP3をダウンロード
        success = await asyncio.get_event_loop().run_in_executor(
            None, downloader.download_mp3, track_info.url
        )
        
        if success:
            # 最新のMP3ファイルを取得
            file_path = downloader.get_latest_mp3_file()
            track_info.file_path = file_path
            
            if file_path:
                # 再生終了時のコールバック
                async def on_finish(error, guild_id, track_info):
                    # 現在再生中のトラックをクリア
                    audio_queue.clear_now_playing(guild_id)
                    
                    # 次の曲を再生
                    next_track = audio_queue.get_next_track(guild_id)
                    if next_track:
                        await download_and_play_track(guild_id, next_track, voice_client, audio_queue, audio_player)
                    else:
                        # キューが空の場合は切断
                        if voice_client and voice_client.is_connected():
                            await voice_client.disconnect()
                
                # 再生開始
                success = await audio_player.play_track(guild_id, track_info, voice_client, on_finish)
                
                if success and text_channel_id:
                    # 再生開始通知
                    embed = discord.Embed(
                        title="🎵 再生開始",
                        description=f"**タイトル：** {track_info.title}\n\n**URL：** {track_info.url}",
                        color=discord.Color.green()
                    )
                    
                    try:
                        channel = voice_client.guild.get_channel(text_channel_id)
                        if channel and channel.permissions_for(voice_client.guild.me).send_messages:
                            await channel.send(embed=embed)
                    except Exception as e:
                        logger.error(f"Failed to send notification: {e}")
        
    except Exception as e:
        logger.error(f"Error in download_and_play_track: {e}")

async def start_background_download(guild_id: int, track_info: TrackInfo, audio_queue: AudioQueue):
    """バックグラウンドでダウンロード開始"""
    try:
        from ..youtube import YouTubeDownloader
        
        downloader = YouTubeDownloader()
        
        # MP3をダウンロード
        success = await asyncio.get_event_loop().run_in_executor(
            None, downloader.download_mp3, track_info.url
        )
        
        if success:
            audio_queue.set_download_status(guild_id, track_info.url, True)
            logger.info(f"Background download completed: {track_info.title}")
        else:
            logger.error(f"Background download failed: {track_info.title}")
            
    except Exception as e:
        logger.error(f"Error in background download: {e}")
