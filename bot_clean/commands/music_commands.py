"""
音楽関連のDiscordコマンド
"""

import asyncio
import logging
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

from ..core.youtube_downloader import YouTubeDownloader
from ..core.audio_player import AudioPlayer, Track

logger = logging.getLogger(__name__)

class MusicCommands(commands.Cog):
    """音楽再生コマンド"""
    
    def __init__(self, bot, audio_player: AudioPlayer, downloader: YouTubeDownloader):
        self.bot = bot
        self.audio_player = audio_player
        self.downloader = downloader
        self.idle_timers = {}  # guild_id -> timer task
    
    @app_commands.command(name="play", description="YouTube動画を音声で再生します")
    async def play(self, interaction: discord.Interaction, url: str):
        """音楽再生コマンド"""
        # ユーザーがボイスチャンネルに接続しているかチェック
        if not interaction.user.voice:
            await interaction.response.send_message(
                "❌ ボイスチャンネルに接続してから使用してください。",
                ephemeral=True
            )
            return
        
        # YouTube URLの検証
        if not self.downloader.validate_youtube_url(url):
            await interaction.response.send_message(
                "❌ 有効なYouTube URLを入力してください。",
                ephemeral=True
            )
            return
        
        # 初期応答
        embed = discord.Embed(
            title="🎵 音楽準備中",
            description=f"**URL:** {url}\n**リクエスト:** {interaction.user.display_name}",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)
        
        try:
            # ボイスチャンネルに接続
            voice_channel = interaction.user.voice.channel
            voice_client = interaction.guild.voice_client
            
            if not voice_client:
                voice_client = await voice_channel.connect()
            elif voice_client.channel != voice_channel:
                await voice_client.move_to(voice_channel)
            
            # アイドルタイマーをキャンセル
            self._cancel_idle_timer(interaction.guild.id)
            
            # 音声をダウンロード
            success, title, file_path = await asyncio.get_event_loop().run_in_executor(
                None, self.downloader.download_audio, url
            )
            
            if not success:
                embed = discord.Embed(
                    title="❌ ダウンロード失敗",
                    description=f"音声のダウンロードに失敗しました。\n**エラー:** {title}",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed)
                return
            
            # トラック情報を作成
            track = Track(url, title, file_path, interaction.user.display_name)
            
            # 再生中の場合はキューに追加
            if self.audio_player.is_playing(voice_client):
                self.audio_player.add_to_queue(interaction.guild.id, track)
                
                embed = discord.Embed(
                    title="📋 キューに追加",
                    description=f"**タイトル:** {title}\n**リクエスト:** {interaction.user.display_name}",
                    color=discord.Color.green()
                )
                queue_length = len(self.audio_player.get_queue(interaction.guild.id))
                embed.add_field(name="📊 キュー", value=f"{queue_length}曲待機中", inline=True)
                
                await interaction.followup.send(embed=embed)
            else:
                # 即座に再生
                await self._play_track(voice_client, track, interaction)
        
        except Exception as e:
            logger.error(f"Play command error: {e}")
            embed = discord.Embed(
                title="❌ エラーが発生しました",
                description=str(e),
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
    
    async def _play_track(self, voice_client, track: Track, interaction: discord.Interaction):
        """トラックを再生"""
        async def on_finish():
            """再生終了時の処理"""
            guild_id = voice_client.guild.id
            
            # 次のトラックを取得
            next_track = self.audio_player.get_next_track(guild_id)
            
            if next_track:
                # 次の曲を再生
                await self._play_track(voice_client, next_track, interaction)
            else:
                # キューが空の場合は5分後に切断
                self._start_idle_timer(guild_id, voice_client)
        
        # 再生開始
        success = await self.audio_player.play_track(voice_client, track, on_finish)
        
        if success:
            # 再生開始通知
            embed = discord.Embed(
                title="🎵 再生開始",
                description=f"**タイトル:** {track.title}",
                color=discord.Color.green()
            )
            embed.add_field(name="👤 リクエスト", value=track.requester, inline=True)
            
            # ループ状態表示
            if self.audio_player.is_loop_enabled(voice_client.guild.id):
                embed.add_field(name="🔁 ループ", value="有効", inline=True)
            
            # キュー情報
            queue_length = len(self.audio_player.get_queue(voice_client.guild.id))
            if queue_length > 0:
                embed.add_field(name="📋 次の曲", value=f"{queue_length}曲待機中", inline=True)
            
            await interaction.followup.send(embed=embed)
        else:
            embed = discord.Embed(
                title="❌ 再生失敗",
                description="音声の再生に失敗しました。",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="stop", description="音楽再生を停止してボイスチャンネルから切断")
    async def stop(self, interaction: discord.Interaction):
        """停止コマンド"""
        voice_client = interaction.guild.voice_client
        
        if not voice_client:
            await interaction.response.send_message(
                "❌ ボイスチャンネルに接続していません。",
                ephemeral=True
            )
            return
        
        # 再生停止とキュークリア
        self.audio_player.stop_playback(voice_client)
        self.audio_player.clear_queue(interaction.guild.id)
        self.audio_player.set_loop(interaction.guild.id, False)
        
        # タイマーキャンセル
        self._cancel_idle_timer(interaction.guild.id)
        
        # 切断
        await voice_client.disconnect()
        
        embed = discord.Embed(
            title="🛑 停止完了",
            description="音楽再生を停止し、ボイスチャンネルから切断しました。",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="pause", description="音楽再生を一時停止")
    async def pause(self, interaction: discord.Interaction):
        """一時停止コマンド"""
        voice_client = interaction.guild.voice_client
        
        if not voice_client or not self.audio_player.is_playing(voice_client):
            await interaction.response.send_message(
                "❌ 現在音楽を再生していません。",
                ephemeral=True
            )
            return
        
        if self.audio_player.pause_playback(voice_client):
            embed = discord.Embed(
                title="⏸️ 一時停止",
                description="音楽再生を一時停止しました。",
                color=discord.Color.yellow()
            )
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("❌ 一時停止に失敗しました。")
    
    @app_commands.command(name="resume", description="音楽再生を再開")
    async def resume(self, interaction: discord.Interaction):
        """再開コマンド"""
        voice_client = interaction.guild.voice_client
        
        if not voice_client or not self.audio_player.is_paused(voice_client):
            await interaction.response.send_message(
                "❌ 一時停止中の音楽がありません。",
                ephemeral=True
            )
            return
        
        if self.audio_player.resume_playback(voice_client):
            embed = discord.Embed(
                title="▶️ 再開",
                description="音楽再生を再開しました。",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("❌ 再開に失敗しました。")
    
    @app_commands.command(name="skip", description="現在の曲をスキップ")
    async def skip(self, interaction: discord.Interaction):
        """スキップコマンド"""
        voice_client = interaction.guild.voice_client
        
        if not voice_client or not self.audio_player.is_playing(voice_client):
            await interaction.response.send_message(
                "❌ 現在音楽を再生していません。",
                ephemeral=True
            )
            return
        
        current_track = self.audio_player.get_current_track(interaction.guild.id)
        voice_client.stop()  # これにより次の曲が自動再生される
        
        embed = discord.Embed(
            title="⏭️ スキップ",
            description=f"**スキップした曲:** {current_track.title if current_track else '不明'}",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="queue", description="現在のキューを表示")
    async def queue(self, interaction: discord.Interaction):
        """キュー表示コマンド"""
        guild_id = interaction.guild.id
        queue = self.audio_player.get_queue(guild_id)
        current_track = self.audio_player.get_current_track(guild_id)
        
        embed = discord.Embed(
            title="🎵 音楽キュー",
            color=discord.Color.blue()
        )
        
        # 現在再生中の曲
        if current_track:
            loop_status = " 🔁" if self.audio_player.is_loop_enabled(guild_id) else ""
            embed.add_field(
                name=f"🎶 現在再生中{loop_status}",
                value=f"**{current_track.title}**\n👤 {current_track.requester}",
                inline=False
            )
        
        # キュー
        if queue:
            queue_text = ""
            for i, track in enumerate(queue[:10], 1):  # 最大10曲表示
                queue_text += f"{i}. **{track.title}**\n   👤 {track.requester}\n"
            
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
    
    @app_commands.command(name="clear", description="キューをクリア")
    async def clear(self, interaction: discord.Interaction):
        """キュークリアコマンド"""
        guild_id = interaction.guild.id
        queue_length = len(self.audio_player.get_queue(guild_id))
        
        if queue_length == 0:
            embed = discord.Embed(
                title="📋 キューは空です",
                description="クリアするキューがありません。",
                color=discord.Color.blue()
            )
        else:
            self.audio_player.clear_queue(guild_id)
            embed = discord.Embed(
                title="🗑️ キューをクリア",
                description=f"{queue_length}曲のキューがクリアされました。",
                color=discord.Color.orange()
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="loop", description="現在の曲のループを切り替え")
    async def loop(self, interaction: discord.Interaction):
        """ループコマンド"""
        voice_client = interaction.guild.voice_client
        
        if not voice_client or not self.audio_player.is_playing(voice_client):
            await interaction.response.send_message(
                "❌ 現在音楽を再生していません。",
                ephemeral=True
            )
            return
        
        guild_id = interaction.guild.id
        current_enabled = self.audio_player.is_loop_enabled(guild_id)
        self.audio_player.set_loop(guild_id, not current_enabled)
        
        if not current_enabled:
            embed = discord.Embed(
                title="🔁 ループ有効",
                description="現在の曲をループします。",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="🔁 ループ無効",
                description="ループを無効にしました。",
                color=discord.Color.orange()
            )
        
        await interaction.response.send_message(embed=embed)
    
    def _start_idle_timer(self, guild_id: int, voice_client):
        """アイドルタイマーを開始"""
        async def idle_disconnect():
            await asyncio.sleep(300)  # 5分待機
            
            if voice_client.is_connected():
                # まだ接続中で再生もしていない場合は切断
                if not self.audio_player.is_playing(voice_client):
                    await voice_client.disconnect()
                    self.audio_player.cleanup_guild(guild_id)
                    logger.info(f"Auto-disconnected due to inactivity: {guild_id}")
        
        # 既存のタイマーをキャンセル
        self._cancel_idle_timer(guild_id)
        
        # 新しいタイマーを開始
        self.idle_timers[guild_id] = asyncio.create_task(idle_disconnect())
    
    def _cancel_idle_timer(self, guild_id: int):
        """アイドルタイマーをキャンセル"""
        if guild_id in self.idle_timers:
            self.idle_timers[guild_id].cancel()
            del self.idle_timers[guild_id]

async def setup(bot, audio_player: AudioPlayer, downloader: YouTubeDownloader):
    """コマンドをセットアップ"""
    await bot.add_cog(MusicCommands(bot, audio_player, downloader))
