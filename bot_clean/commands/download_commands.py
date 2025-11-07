"""
ダウンロード関連のDiscordコマンド
"""

import asyncio
import logging
import discord
from discord.ext import commands
from discord import app_commands

from ..core.youtube_downloader import YouTubeDownloader
import config

logger = logging.getLogger(__name__)

class DownloadCommands(commands.Cog):
    """ダウンロードコマンド"""
    
    def __init__(self, bot, downloader: YouTubeDownloader):
        self.bot = bot
        self.downloader = downloader
    
    @app_commands.command(name="download", description="YouTube動画をダウンロード")
    @app_commands.describe(
        url="YouTube動画のURL",
        quality="動画の画質"
    )
    @app_commands.choices(quality=[
        app_commands.Choice(name='144p (低画質)', value='144p'),
        app_commands.Choice(name='240p (低画質)', value='240p'),
        app_commands.Choice(name='360p (標準画質)', value='360p'),
        app_commands.Choice(name='480p (標準画質)', value='480p'),
        app_commands.Choice(name='720p (高画質)', value='720p'),
        app_commands.Choice(name='1080p (フルHD)', value='1080p')
    ])
    async def download_video(self, interaction: discord.Interaction, url: str, quality: str = '720p'):
        """動画ダウンロードコマンド"""
        # YouTube URLの検証
        if not self.downloader.validate_youtube_url(url):
            await interaction.response.send_message(
                "❌ 有効なYouTube URLを入力してください。",
                ephemeral=True
            )
            return
        
        # 初期応答
        embed = discord.Embed(
            title="📥 ダウンロード開始",
            description=f"**URL:** {url}\n**画質:** {quality}",
            color=discord.Color.blue()
        )
        embed.add_field(name="⏳ ステータス", value="ダウンロード中...", inline=False)
        
        await interaction.response.send_message(embed=embed)
        
        try:
            # 動画をダウンロード
            success, title, file_path = await asyncio.get_event_loop().run_in_executor(
                None, self.downloader.download_video, url, quality
            )
            
            if not success:
                embed = discord.Embed(
                    title="❌ ダウンロード失敗",
                    description=f"動画のダウンロードに失敗しました。\n**エラー:** {title}",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed)
                return
            
            # ファイルサイズをチェック
            file_size_mb = self.downloader.get_file_size_mb(file_path)
            
            if file_size_mb <= config.MAX_FILE_SIZE_MB:
                # ファイルサイズが制限内の場合、Discordにアップロード
                file = discord.File(file_path)
                
                embed = discord.Embed(
                    title="✅ ダウンロード完了",
                    description=f"**タイトル:** {title}",
                    color=discord.Color.green()
                )
                embed.add_field(name="📊 ファイルサイズ", value=f"{file_size_mb:.1f} MB", inline=True)
                embed.add_field(name="🎬 画質", value=quality, inline=True)
                embed.add_field(name="🔗 元URL", value=f"[リンク]({url})", inline=False)
                
                await interaction.followup.send(embed=embed, file=file)
                
                # ファイルを削除
                self.downloader.cleanup_file(file_path)
            else:
                # ファイルサイズが大きすぎる場合
                embed = discord.Embed(
                    title="⚠️ ファイルサイズが大きすぎます",
                    description=f"**タイトル:** {title}",
                    color=discord.Color.orange()
                )
                embed.add_field(name="📊 ファイルサイズ", value=f"{file_size_mb:.1f} MB", inline=True)
                embed.add_field(name="📏 制限", value=f"{config.MAX_FILE_SIZE_MB} MB", inline=True)
                embed.add_field(
                    name="💡 提案", 
                    value="より低い画質を試してください。",
                    inline=False
                )
                
                await interaction.followup.send(embed=embed)
                
                # ファイルを削除
                self.downloader.cleanup_file(file_path)
        
        except Exception as e:
            logger.error(f"Download command error: {e}")
            embed = discord.Embed(
                title="❌ エラーが発生しました",
                description=str(e),
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="download_mp3", description="YouTube動画をMP3に変換してダウンロード")
    @app_commands.describe(url="YouTube動画のURL")
    async def download_mp3(self, interaction: discord.Interaction, url: str):
        """MP3ダウンロードコマンド"""
        # YouTube URLの検証
        if not self.downloader.validate_youtube_url(url):
            await interaction.response.send_message(
                "❌ 有効なYouTube URLを入力してください。",
                ephemeral=True
            )
            return
        
        # 初期応答
        embed = discord.Embed(
            title="🎵 MP3変換開始",
            description=f"**URL:** {url}",
            color=discord.Color.blue()
        )
        embed.add_field(name="⏳ ステータス", value="MP3に変換中...", inline=False)
        
        await interaction.response.send_message(embed=embed)
        
        try:
            # 音声をダウンロード
            success, title, file_path = await asyncio.get_event_loop().run_in_executor(
                None, self.downloader.download_audio, url
            )
            
            if not success:
                embed = discord.Embed(
                    title="❌ 変換失敗",
                    description=f"MP3変換に失敗しました。\n**エラー:** {title}",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed)
                return
            
            # ファイルサイズをチェック
            file_size_mb = self.downloader.get_file_size_mb(file_path)
            
            if file_size_mb <= config.MAX_FILE_SIZE_MB:
                # ファイルサイズが制限内の場合、Discordにアップロード
                file = discord.File(file_path)
                
                embed = discord.Embed(
                    title="✅ MP3変換完了",
                    description=f"**タイトル:** {title}",
                    color=discord.Color.green()
                )
                embed.add_field(name="📊 ファイルサイズ", value=f"{file_size_mb:.1f} MB", inline=True)
                embed.add_field(name="🎵 形式", value="MP3音声", inline=True)
                embed.add_field(name="🔗 元URL", value=f"[リンク]({url})", inline=False)
                
                await interaction.followup.send(embed=embed, file=file)
                
                # ファイルを削除
                self.downloader.cleanup_file(file_path)
            else:
                # ファイルサイズが大きすぎる場合
                embed = discord.Embed(
                    title="⚠️ ファイルサイズが大きすぎます",
                    description=f"**タイトル:** {title}",
                    color=discord.Color.orange()
                )
                embed.add_field(name="📊 ファイルサイズ", value=f"{file_size_mb:.1f} MB", inline=True)
                embed.add_field(name="📏 制限", value=f"{config.MAX_FILE_SIZE_MB} MB", inline=True)
                embed.add_field(
                    name="💡 提案", 
                    value="音声の長さが制限を超えています。短い動画を試してください。",
                    inline=False
                )
                
                await interaction.followup.send(embed=embed)
                
                # ファイルを削除
                self.downloader.cleanup_file(file_path)
        
        except Exception as e:
            logger.error(f"MP3 download command error: {e}")
            embed = discord.Embed(
                title="❌ エラーが発生しました",
                description=str(e),
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="quality", description="利用可能な画質を表示")
    async def show_quality(self, interaction: discord.Interaction):
        """画質一覧表示コマンド"""
        embed = discord.Embed(
            title="🎬 利用可能な画質",
            color=discord.Color.blue()
        )
        
        quality_list = "\n".join([f"• {q}" for q in config.SUPPORTED_QUALITIES])
        embed.add_field(
            name="📊 画質オプション",
            value=quality_list,
            inline=False
        )
        
        embed.add_field(
            name="💡 使用例",
            value="`/download <URL> <画質>`\n例: `/download https://youtube.com/watch?v=... 720p`",
            inline=False
        )
        
        embed.add_field(
            name="📏 制限",
            value=f"最大ファイルサイズ: {config.MAX_FILE_SIZE_MB} MB",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot, downloader: YouTubeDownloader):
    """コマンドをセットアップ"""
    await bot.add_cog(DownloadCommands(bot, downloader))
