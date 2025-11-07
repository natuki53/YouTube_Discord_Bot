"""
一般的なDiscordコマンド
"""

import logging
import discord
from discord.ext import commands
from discord import app_commands

logger = logging.getLogger(__name__)

class GeneralCommands(commands.Cog):
    """一般的なコマンド"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="ping", description="ボットの応答速度をテスト")
    async def ping(self, interaction: discord.Interaction):
        """Pingコマンド"""
        latency = round(self.bot.latency * 1000)
        
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"レイテンシ: {latency}ms",
            color=discord.Color.green()
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="help", description="ボットの使用方法を表示")
    async def help(self, interaction: discord.Interaction):
        """ヘルプコマンド"""
        embed = discord.Embed(
            title="🤖 YouTube Discord Bot ヘルプ",
            description="YouTube動画の再生とダウンロードが可能なボットです。",
            color=discord.Color.blue()
        )
        
        # 音楽コマンド
        music_commands = [
            "`/play <URL>` - YouTube音声を再生",
            "`/stop` - 再生停止・切断",
            "`/pause` - 一時停止",
            "`/resume` - 再生再開",
            "`/skip` - 曲をスキップ",
            "`/queue` - キューを表示",
            "`/clear` - キューをクリア",
            "`/loop` - ループ切り替え"
        ]
        
        embed.add_field(
            name="🎵 音楽コマンド",
            value="\n".join(music_commands),
            inline=False
        )
        
        # ダウンロードコマンド
        download_commands = [
            "`/download <URL> <画質>` - 動画ダウンロード",
            "`/download_mp3 <URL>` - MP3変換ダウンロード",
            "`/quality` - 利用可能な画質を表示"
        ]
        
        embed.add_field(
            name="📥 ダウンロードコマンド",
            value="\n".join(download_commands),
            inline=False
        )
        
        # 一般コマンド
        general_commands = [
            "`/ping` - 応答速度テスト",
            "`/help` - このヘルプを表示"
        ]
        
        embed.add_field(
            name="🔧 一般コマンド",
            value="\n".join(general_commands),
            inline=False
        )
        
        embed.add_field(
            name="💡 使用例",
            value=(
                "**音楽再生:**\n"
                "`/play https://youtube.com/watch?v=...`\n\n"
                "**動画ダウンロード:**\n"
                "`/download https://youtube.com/watch?v=... 720p`\n\n"
                "**MP3変換:**\n"
                "`/download_mp3 https://youtube.com/watch?v=...`"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⚠️ 注意事項",
            value=(
                "• ボイスチャンネルに接続してから音楽コマンドを使用してください\n"
                "• YouTube URLのみ対応しています\n"
                f"• ファイルサイズ制限: 25MB\n"
                "• 著作権を遵守してご利用ください"
            ),
            inline=False
        )
        
        embed.set_footer(text="YouTube Discord Bot v2.0")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="info", description="ボットの情報を表示")
    async def info(self, interaction: discord.Interaction):
        """ボット情報コマンド"""
        embed = discord.Embed(
            title="ℹ️ ボット情報",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="🤖 ボット名", value=self.bot.user.name, inline=True)
        embed.add_field(name="🆔 ボットID", value=self.bot.user.id, inline=True)
        embed.add_field(name="📊 サーバー数", value=len(self.bot.guilds), inline=True)
        
        embed.add_field(
            name="⚡ 機能",
            value=(
                "• YouTube音楽再生\n"
                "• 動画・音声ダウンロード\n"
                "• キュー管理\n"
                "• ループ再生"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🛠️ 技術スタック",
            value=(
                "• Python 3.9+\n"
                "• discord.py 2.3+\n"
                "• yt-dlp\n"
                "• FFmpeg"
            ),
            inline=True
        )
        
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)
        embed.set_footer(text="YouTube Discord Bot v2.0 - Clean Architecture")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    """コマンドをセットアップ"""
    await bot.add_cog(GeneralCommands(bot))
