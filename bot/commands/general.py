"""
一般的なコマンド

ヘルプ、ping、その他の汎用コマンド
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger(__name__)

def setup_general_commands(bot):
    """一般的なコマンドをセットアップ"""
    
    @bot.tree.command(name='ping', description='Test bot response')
    async def ping(interaction: discord.Interaction):
        """ボットの応答テスト用コマンド"""
        await interaction.response.send_message("🏓 Pong! Bot is working!", ephemeral=True)

    @bot.tree.command(name='help', description='Show bot help and command list')
    async def show_help(interaction: discord.Interaction):
        """ヘルプコマンド"""
        embed = discord.Embed(
            title="🤖 YouTube Downloader Bot ヘルプ",
            description="YouTube動画をダウンロードできるDiscordボットです。",
            color=discord.Color.blue()
        )
        
        # スラッシュコマンド用に更新
        slash_commands = {
            '/ping': 'ボットの応答テスト',
            '/download': 'YouTube動画をMP3に変換してダウンロードします',
            '/play': 'YouTube音声をボイスチャンネルで再生します（キューに追加）',
            '/playlist': 'YouTubeプレイリスト全体をキューに追加します',
            '/pause': '音声再生を一時停止します',
            '/resume': '音声再生を再開します',
            '/stop': '音声再生を停止し、ボイスチャンネルから切断します',
            '/skip': '現在再生中の曲をスキップして次の曲を再生します',
            '/queue': '現在の音楽キューを表示します',
            '/clear': '音楽キューをクリアします',
            '/loop': '現在の曲をループ再生します',
            '/help': 'コマンド一覧を表示します'
        }
        
        for command, description in slash_commands.items():
            embed.add_field(
                name=command,
                value=description,
                inline=False
            )
        
        embed.add_field(
            name="📝 注意事項",
            value="• ファイルサイズは25MB以下に制限されています\n• 個人使用目的でのみ使用してください\n• YouTubeの利用規約を遵守してください",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.event
    async def on_command_error(ctx, error):
        """コマンドエラー時の処理"""
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ 必要な引数が不足しています。`/help`で使用方法を確認してください。")
        elif isinstance(error, commands.CommandNotFound):
            await ctx.send(f"❌ コマンドが見つかりません。`/help`で利用可能なコマンドを確認してください。")
        else:
            logger.exception("コマンドエラー")
            await ctx.send("❌ 予期しないエラーが発生しました。")
