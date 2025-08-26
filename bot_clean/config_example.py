"""
Discord YouTube Bot 設定ファイル（サンプル）

このファイルをconfig.pyにコピーして、DISCORD_TOKENを設定してください。
"""

import os
from pathlib import Path

# Discord Bot設定
DISCORD_TOKEN = 'your_discord_bot_token_here'  # ← ここにボットトークンを設定
BOT_PREFIX = '!'

# ダウンロード設定
DOWNLOAD_DIR = './downloads'
MAX_FILE_SIZE_MB = 25  # Discord制限

# 音声設定
AUDIO_VOLUME = 0.25  # 0.0 - 1.0
IDLE_TIMEOUT_SECONDS = 300  # 5分

# サポートされている画質
SUPPORTED_QUALITIES = ['144p', '240p', '360p', '480p', '720p', '1080p']

# ログ設定
LOG_LEVEL = 'INFO'

def validate_config():
    """設定の検証"""
    if DISCORD_TOKEN == 'your_discord_bot_token_here':
        print("❌ 設定エラー: DISCORD_TOKENが設定されていません")
        print("解決方法:")
        print("1. config.pyでDISCORD_TOKENを直接設定")
        print("2. 環境変数DISCORD_TOKENを設定")
        print("3. config_example.pyをconfig.pyにコピーして編集")
        return False
    
    # ダウンロードディレクトリを作成
    Path(DOWNLOAD_DIR).mkdir(exist_ok=True)
    return True
