"""
YouTube Discord Bot - メインエントリーポイント
"""

import asyncio
import logging
from pathlib import Path

from bot.utils.encoding import setup_encoding

setup_encoding()

from bot.commands import (
    setup_download_commands,
    setup_general_commands,
    setup_music_commands,
)
from bot.config.discord_config import create_bot_instance, setup_bot_activity
from bot.config.settings import DISCORD_TOKEN, get_settings, validate_settings
from bot.music import PlayerManager
from bot.utils.download_cleanup import cleanup_stale_tmp, ensure_tmp_dir
from bot.utils.file_utils import force_kill_ffmpeg_processes
from bot.youtube.download_service import DownloadService
from bot.youtube.file_downloader import FileDownloader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class YouTubeBotMain:
    """メインボットクラス"""

    def __init__(self):
        validate_settings()
        self.settings = get_settings()

        self.bot = create_bot_instance(self.settings["BOT_PREFIX"])
        self.player_manager = PlayerManager(
            self.bot, default_volume=self.settings["DEFAULT_VOLUME"]
        )

        ensure_tmp_dir(self.settings["DOWNLOAD_TMP_DIR"])
        self.download_semaphore = asyncio.Semaphore(
            self.settings["MAX_CONCURRENT_DOWNLOADS"]
        )
        self._ready_lock = asyncio.Lock()
        self._ready_initialized = False
        file_downloader = FileDownloader(
            tmp_dir=self.settings["DOWNLOAD_TMP_DIR"],
            max_file_size_mb=self.settings["MAX_FILE_SIZE"],
            mp3_bitrate_default=self.settings["MP3_BITRATE_DEFAULT"],
            mp3_bitrate_long=self.settings["MP3_BITRATE_LONG"],
        )
        self.download_service = DownloadService(
            file_downloader,
            self.download_semaphore,
            timeout_seconds=self.settings["DOWNLOAD_TIMEOUT_SECONDS"],
        )

        self._setup_events()
        self._setup_commands()

    def _setup_events(self):
        @self.bot.event
        async def on_ready():
            async with self._ready_lock:
                if self._ready_initialized:
                    logger.info("Discord Gateway に再接続しました")
                    return

                try:
                    Path(self.settings["DOWNLOAD_DIR"]).mkdir(
                        parents=True, exist_ok=True
                    )
                    ensure_tmp_dir(self.settings["DOWNLOAD_TMP_DIR"])
                    removed = cleanup_stale_tmp(
                        self.settings["DOWNLOAD_TMP_DIR"],
                        self.settings["TMP_MAX_AGE_MINUTES"],
                    )
                    if removed:
                        logger.info(f"Removed {removed} stale tmp file(s)")

                    setup_activity = setup_bot_activity(self.bot)
                    await setup_activity()
                    await self._sync_commands()
                except Exception:
                    logger.exception("Bot initialization failed")
                    return

                self._ready_initialized = True
                # deploy/deploy.sh はこのログを起動完了の判定に使用する。
                logger.info(f"{self.bot.user} としてログインしました！")
                logger.info(f"サーバー数: {len(self.bot.guilds)}")

    def _setup_commands(self):
        setup_music_commands(self.bot, self.player_manager)
        setup_download_commands(
            self.bot,
            self.download_service,
            self.settings["SUPPORTED_QUALITIES"],
        )
        setup_general_commands(self.bot)

    async def _sync_commands(self):
        logger.info("Syncing slash commands...")
        global_synced = await self.bot.tree.sync()
        logger.info(f"Synced {len(global_synced)} global command(s)")

        for cmd in global_synced:
            logger.info(f"  - /{cmd.name}: {cmd.description}")

    def run(self):
        try:
            # 前回の異常終了で残ったプロセスだけを、Gateway 接続前に掃除する。
            force_kill_ffmpeg_processes()
            self.bot.run(DISCORD_TOKEN)
        except KeyboardInterrupt:
            logger.info("ボットが手動で停止されました")
        except Exception as e:
            logger.error(f"ボット起動エラー: {e}")
            self._handle_startup_errors(e)
            raise
        finally:
            logger.info("ボット終了時のクリーンアップを実行中...")
            try:
                removed = cleanup_stale_tmp(
                    self.settings["DOWNLOAD_TMP_DIR"],
                    max_age_minutes=0,
                )
                logger.info(f"Tmp cleanup on shutdown: {removed} file(s)")
                force_kill_ffmpeg_processes()
            except Exception as cleanup_error:
                logger.warning(f"クリーンアップエラー: {cleanup_error}")

    def _handle_startup_errors(self, error):
        import discord

        if isinstance(error, discord.LoginFailure):
            print("❌ Discordトークンが無効です。")
        elif isinstance(error, discord.errors.PrivilegedIntentsRequired):
            print(
                "❌ 特権インテントが必要です。Developer Portal で有効化してください。"
            )
        else:
            print(f"❌ 予期しないエラー: {error}")


def main():
    try:
        YouTubeBotMain().run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        raise


if __name__ == "__main__":
    main()
