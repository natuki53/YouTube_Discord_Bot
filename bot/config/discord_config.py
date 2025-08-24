"""
Discord ボット設定

Discord特有の設定とインテントの管理
"""

import discord
from discord.ext import commands
import logging

logger = logging.getLogger(__name__)

def create_bot_instance(prefix: str):
    """ボットインスタンスを作成する"""
    # ボットの設定
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.messages = True
    intents.voice_states = True
    
    # ボットの作成（スラッシュコマンド用）
    bot = commands.Bot(command_prefix=prefix, intents=intents)
    
    logger.info(f"Bot instance created with prefix: {prefix}")
    return bot

def setup_bot_activity(bot, activity_name: str = "YouTubeを再生中..."):
    """ボットのアクティビティを設定"""
    async def setup_activity():
        await bot.change_presence(activity=discord.Game(name=activity_name))
        logger.info(f"Bot activity set to: {activity_name}")
    
    return setup_activity
