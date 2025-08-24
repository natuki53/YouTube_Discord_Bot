"""
YouTube Discord Bot - メインエントリーポイント

リファクタリング後のクリーンなメインファイル
"""

import asyncio
import logging
from pathlib import Path

# エンコーディング設定を最初に実行
from bot.utils.encoding import setup_encoding
setup_encoding()

from bot.config.settings import validate_settings, get_settings, DISCORD_TOKEN, DOWNLOAD_DIR
from bot.config.discord_config import create_bot_instance, setup_bot_activity
from bot.audio import AudioQueue, AudioPlayer
from bot.commands import setup_music_commands, setup_download_commands, setup_general_commands
from bot.utils.file_utils import cleanup_old_audio_files, force_kill_ffmpeg_processes

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class YouTubeBotMain:
    """メインボットクラス"""
    
    def __init__(self):
        # 設定の検証と取得
        validate_settings()
        self.settings = get_settings()
        
        # ボットインスタンスの作成
        self.bot = create_bot_instance(self.settings['BOT_PREFIX'])
        
        # 音声関連のインスタンス
        self.audio_queue = AudioQueue()
        self.audio_player = AudioPlayer(self.settings['DOWNLOAD_DIR'])
        
        # イベントハンドラーの設定
        self._setup_events()
        
        # コマンドのセットアップ
        self._setup_commands()
    
    def _setup_events(self):
        """ボットイベントの設定"""
        
        @self.bot.event
        async def on_ready():
            """ボットが起動した時の処理"""
            logger.info(f'{self.bot.user} としてログインしました！')
            logger.info(f'サーバー数: {len(self.bot.guilds)}')
            
            # ダウンロードディレクトリを作成
            Path(self.settings['DOWNLOAD_DIR']).mkdir(exist_ok=True)
            
            # 古い音声ファイルのクリーンアップ
            cleanup_old_audio_files(self.settings['DOWNLOAD_DIR'])
            
            # 残っているFFmpegプロセスのクリーンアップ
            force_kill_ffmpeg_processes()
            
            # アクティビティを設定
            setup_activity = setup_bot_activity(self.bot)
            await setup_activity()
            
            # スラッシュコマンドを同期
            await self._sync_commands()
    
    def _setup_commands(self):
        """コマンドのセットアップ"""
        # 音楽関連コマンド
        setup_music_commands(
            self.bot, 
            self.audio_queue, 
            self.audio_player, 
            self.settings['DOWNLOAD_DIR']
        )
        
        # ダウンロード関連コマンド
        setup_download_commands(
            self.bot,
            self.settings['DOWNLOAD_DIR'],
            self.settings['MAX_FILE_SIZE'],
            self.settings['SUPPORTED_QUALITIES']
        )
        
        # 一般的なコマンド
        setup_general_commands(self.bot)
    
    async def _sync_commands(self):
        """スラッシュコマンドの同期"""
        try:
            logger.info("Syncing slash commands...")
            
            # グローバルコマンドを同期
            logger.info("Syncing global commands...")
            global_synced = await self.bot.tree.sync()
            logger.info(f'✅ Synced {len(global_synced)} global command(s)')
            
            # 各ギルドにも個別に同期（即座に反映）
            logger.info("Syncing guild commands...")
            for guild in self.bot.guilds:
                try:
                    guild_synced = await self.bot.tree.sync(guild=guild)
                    logger.info(f'✅ Synced {len(guild_synced)} command(s) to guild: {guild.name}')
                    
                    # ギルドコマンドの詳細も表示
                    if guild_synced:
                        logger.info(f"  Guild commands for {guild.name}:")
                        for cmd in guild_synced:
                            logger.info(f"    - /{cmd.name}: {cmd.description}")
                    
                except Exception as e:
                    logger.error(f'❌ Failed to sync to guild {guild.name}: {e}')
            
            # 登録されたコマンドの詳細をログに出力
            logger.info("Global commands:")
            for cmd in global_synced:
                logger.info(f'  - /{cmd.name}: {cmd.description}')
                
            # コマンドが正しく登録されているか確認
            if len(global_synced) == 0:
                logger.warning("⚠️ No global commands were synced. This may indicate a permission issue.")
                logger.warning("Please check bot permissions and invite URL.")
                
        except Exception as e:
            logger.error(f'❌ Failed to sync commands: {e}')
            logger.error('Commands may not appear in Discord. Please check bot permissions.')
            logger.error('Make sure the bot has "applications.commands" scope when invited to the server.')
    
    def run(self):
        """ボットを起動"""
        try:
            self.bot.run(DISCORD_TOKEN)
        except Exception as e:
            logger.error(f"❌ ボット起動エラー: {e}")
            self._handle_startup_errors(e)
    
    def _handle_startup_errors(self, error):
        """起動エラーの処理"""
        import discord
        
        if isinstance(error, discord.LoginFailure):
            print("❌ Discordトークンが無効です。")
        elif isinstance(error, discord.errors.PrivilegedIntentsRequired):
            print("❌ 特権インテントが必要です。")
            print("Discord Developer Portalで以下を有効にしてください：")
            print("1. https://discord.com/developers/applications にアクセス")
            print("2. ボットアプリケーションを選択")
            print("3. 'Bot'セクションで以下を有効化：")
            print("   - MESSAGE CONTENT INTENT")
            print("   - SERVER MEMBERS INTENT")
            print("4. 変更を保存")
            print("5. ボットを再起動")
        else:
            print(f"❌ 予期しないエラーが発生しました: {error}")

def main():
    """メイン関数"""
    try:
        bot_main = YouTubeBotMain()
        bot_main.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()
