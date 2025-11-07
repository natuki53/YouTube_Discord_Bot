"""
YouTube Discord Bot - メインファイル (クリーン版)
"""

import asyncio
import logging
import discord
from discord.ext import commands
import config

from core.youtube_downloader import YouTubeDownloader
from core.audio_player import AudioPlayer
from commands import music_commands, download_commands, general_commands

# ログ設定
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class YouTubeBot:
    """メインボットクラス"""
    
    def __init__(self):
        # 設定の検証
        if not config.validate_config():
            raise ValueError("設定エラーが発生しました")
        
        # Discord Bot設定
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        
        self.bot = commands.Bot(
            command_prefix=config.BOT_PREFIX,
            intents=intents,
            help_command=None  # カスタムヘルプを使用
        )
        
        # コアコンポーネント
        self.downloader = YouTubeDownloader(config.DOWNLOAD_DIR)
        self.audio_player = AudioPlayer(config.AUDIO_VOLUME)
        
        # イベントハンドラーの設定
        self._setup_events()
    
    def _setup_events(self):
        """イベントハンドラーの設定"""
        
        @self.bot.event
        async def on_ready():
            """ボット起動時の処理"""
            logger.info(f'🤖 {self.bot.user} がログインしました!')
            logger.info(f'📊 サーバー数: {len(self.bot.guilds)}')
            
            # アクティビティを設定
            activity = discord.Activity(
                type=discord.ActivityType.listening,
                name="/help でコマンド一覧"
            )
            await self.bot.change_presence(activity=activity)
            
            # コマンドを同期
            await self._sync_commands()
        
        @self.bot.event
        async def on_voice_state_update(member, before, after):
            """ボイスステート更新時の処理"""
            # ボットがボイスチャンネルに一人残された場合の処理
            if member == self.bot.user:
                return
            
            voice_client = member.guild.voice_client
            if voice_client and voice_client.channel:
                # ボイスチャンネルの人数をチェック（ボット以外）
                humans = [m for m in voice_client.channel.members if not m.bot]
                
                if len(humans) == 0:
                    # 人間がいなくなったら30秒後に切断
                    await asyncio.sleep(30)
                    
                    # 30秒後に再チェック
                    humans = [m for m in voice_client.channel.members if not m.bot]
                    if len(humans) == 0 and voice_client.is_connected():
                        await voice_client.disconnect()
                        self.audio_player.cleanup_guild(member.guild.id)
                        logger.info(f"Auto-disconnected from empty channel: {member.guild.name}")
        
        @self.bot.event
        async def on_guild_remove(guild):
            """サーバーから削除された時の処理"""
            self.audio_player.cleanup_guild(guild.id)
            logger.info(f"Cleaned up data for removed guild: {guild.name}")
    
    async def _sync_commands(self):
        """スラッシュコマンドの同期"""
        try:
            logger.info("🔄 スラッシュコマンドを同期中...")
            
            # グローバルコマンドを同期
            synced = await self.bot.tree.sync()
            logger.info(f"✅ {len(synced)}個のコマンドを同期しました")
            
            # 同期されたコマンドをログに出力
            for cmd in synced:
                logger.info(f"  • /{cmd.name}: {cmd.description}")
        
        except Exception as e:
            logger.error(f"❌ コマンド同期エラー: {e}")
    
    async def setup_commands(self):
        """コマンドのセットアップ"""
        try:
            # 各コマンドモジュールをセットアップ
            await music_commands.setup(self.bot, self.audio_player, self.downloader)
            await download_commands.setup(self.bot, self.downloader)
            await general_commands.setup(self.bot)
            
            logger.info("✅ すべてのコマンドがセットアップされました")
            
        except Exception as e:
            logger.error(f"❌ コマンドセットアップエラー: {e}")
            raise
    
    async def start(self):
        """ボットを開始"""
        try:
            # コマンドをセットアップ
            await self.setup_commands()
            
            # ボットを開始
            logger.info("🚀 ボットを開始しています...")
            await self.bot.start(config.DISCORD_TOKEN)
            
        except discord.LoginFailure:
            logger.error("❌ Discordトークンが無効です")
            print("\n設定を確認してください:")
            print("1. config.pyでDISCORD_TOKENを設定")
            print("2. 環境変数DISCORD_TOKENを設定")
            
        except discord.PrivilegedIntentsRequired:
            logger.error("❌ 特権インテントが必要です")
            print("\nDiscord Developer Portalで以下を有効にしてください:")
            print("1. https://discord.com/developers/applications")
            print("2. ボットアプリケーションを選択")
            print("3. 'Bot' → 'Privileged Gateway Intents'")
            print("4. 'MESSAGE CONTENT INTENT' を有効化")
            
        except Exception as e:
            logger.error(f"❌ 予期しないエラー: {e}")
            
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        """クリーンアップ処理"""
        try:
            logger.info("🧹 クリーンアップ中...")
            
            # 全ギルドのデータをクリーンアップ
            for guild_id in list(self.audio_player.queues.keys()):
                self.audio_player.cleanup_guild(guild_id)
            
            # ボットを閉じる
            if not self.bot.is_closed():
                await self.bot.close()
                
            logger.info("✅ クリーンアップ完了")
            
        except Exception as e:
            logger.error(f"❌ クリーンアップエラー: {e}")

async def main():
    """メイン関数"""
    bot = YouTubeBot()
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("🛑 ユーザーによって停止されました")
    except Exception as e:
        logger.error(f"❌ 実行エラー: {e}")
    finally:
        logger.info("👋 ボットを終了しています...")

if __name__ == "__main__":
    # Unix系OS対応の高速イベントループ設定
    import sys
    if sys.platform != "win32":
        try:
            import uvloop  # type: ignore
            uvloop.install()
        except ImportError:
            # uvloopが利用できない場合は標準のasyncioを使用
            pass
    
    # ボットを実行
    asyncio.run(main())
