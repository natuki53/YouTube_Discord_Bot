"""
アプリケーション設定管理

このモジュールは、ボットの基本設定を管理します。
"""

import os
import logging
from pathlib import Path

# ロガー設定
logger = logging.getLogger(__name__)

# 設定をインポート
try:
    from config import *
except ImportError:
    # config.pyが存在しない場合のデフォルト設定
    logger.warning("config.py not found, using default settings")
    DISCORD_TOKEN = 'your_discord_bot_token_here'
    BOT_PREFIX = '!'
    DOWNLOAD_DIR = './downloads'
    MAX_FILE_SIZE = 25
    SUPPORTED_QUALITIES = ['144p', '240p', '360p', '480p', '720p', '1080p']

def validate_settings():
    """設定値の検証"""
    if DISCORD_TOKEN == 'your_discord_bot_token_here':
        raise ValueError("config.pyでDISCORD_TOKENを設定してください。")
    
    # ダウンロードディレクトリの作成
    Path(DOWNLOAD_DIR).mkdir(exist_ok=True)
    logger.info(f"Download directory: {DOWNLOAD_DIR}")
    
    return True

def get_settings():
    """設定値の辞書を返す"""
    return {
        'DISCORD_TOKEN': DISCORD_TOKEN,
        'BOT_PREFIX': BOT_PREFIX,
        'DOWNLOAD_DIR': DOWNLOAD_DIR,
        'MAX_FILE_SIZE': MAX_FILE_SIZE,
        'SUPPORTED_QUALITIES': SUPPORTED_QUALITIES
    }
