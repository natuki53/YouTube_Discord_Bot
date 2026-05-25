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
    
    @bot.tree.command(name="ping", description="ボットの応答をテストします")
    async def ping(interaction: discord.Interaction):
        """ボットの応答テスト用コマンド"""
        await interaction.response.send_message("🏓 Pong! Bot is working!", ephemeral=True)

    @bot.tree.command(name="help", description="コマンド一覧と使い方を表示します")
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
            '/download': 'YouTube動画をダウンロードします（画質はプルダウンメニューから選択）',
            '/download_mp3': 'YouTube動画をMP3に変換してダウンロードします',
            '/quality': '利用可能な画質を表示します',
            '/play': 'YouTube音声をボイスチャンネルで再生します（キューに追加）',
            '/pause': '音声再生を一時停止します',
            '/resume': '音声再生を再開します',
            '/stop': '音声再生を停止し、ボイスチャンネルから切断します',
            '/skip': '現在再生中の曲をスキップして次の曲を再生します',
            '/queue': '現在の音楽キューを表示します',
            '/clear': '音楽キューをクリアします',
            '/loop': '現在の曲のループ再生を切り替えます',
            '/volume': '再生音量を変更します（1〜100%）',
            '/help': 'コマンド一覧を表示します',
        }
        
        for command, description in slash_commands.items():
            embed.add_field(
                name=command,
                value=description,
                inline=False
            )
        
        embed.add_field(
            name="📝 注意事項",
            value="• VC再生はストリーミング（ディスクに保存しません）\n• ダウンロードは一時ファイルで、添付後に自動削除されます\n• ファイルサイズは25MB以下（超過時は低画質を自動試行）\n• 個人使用目的でのみ使用してください",
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
            logger.error(f"コマンドエラー: {error}")
            await ctx.send("❌ 予期しないエラーが発生しました。")
