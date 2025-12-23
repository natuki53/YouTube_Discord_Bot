"""
アプリケーション設定管理

このモジュールは、ボットの基本設定を管理します。
"""

import os
import logging
import shutil
from pathlib import Path

# ロガー設定
logger = logging.getLogger(__name__)

# まず .env を読み込み（存在すれば環境変数へ反映）
# 仕様: 環境変数を最優先、次に config.py、最後にデフォルト
try:
    from dotenv import load_dotenv  # type: ignore
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")
except Exception:
    # python-dotenv が無い/失敗しても環境変数直指定は使えるので続行
    pass

# 設定をインポート（後方互換: config.py がある場合は参照）
_config = {}
try:
    import config as _user_config  # type: ignore
    # 必要なものだけ拾う（ワイルドカードimportの副作用回避）
    for _key in ("DISCORD_TOKEN", "BOT_PREFIX", "DOWNLOAD_DIR", "MAX_FILE_SIZE"):
        if hasattr(_user_config, _key):
            _config[_key] = getattr(_user_config, _key)
except ImportError:
    logger.warning("config.py not found, using environment variables / default settings")

def _get_env(name: str):
    """環境変数を取得（空文字は未設定扱い）"""
    val = os.getenv(name)
    if val is None:
        return None
    val = val.strip()
    return val if val else None

def _get_int(name: str, default: int) -> int:
    val = _get_env(name)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        logger.warning(f"Invalid int for {name}: {val!r}. Using default={default}")
        return default

def _get_list(name: str, default: list) -> list:
    """
    カンマ区切り/空白区切りのリストを env から取得。
    例: SUPPORTED_QUALITIES=144p,240p,360p
    """
    val = _get_env(name)
    if val is None:
        return default
    parts = [p.strip() for p in val.replace("\n", ",").split(",")]
    parts = [p for p in parts if p]
    return parts if parts else default

# 既定値
_DEFAULT_TOKEN = "your_discord_bot_token_here"
_DEFAULT_PREFIX = "!"
_DEFAULT_DIR = "./downloads"
_DEFAULT_MAX_MB = 25

DISCORD_TOKEN = _get_env("DISCORD_TOKEN") or _config.get("DISCORD_TOKEN") or _DEFAULT_TOKEN
BOT_PREFIX = _get_env("BOT_PREFIX") or _config.get("BOT_PREFIX") or _DEFAULT_PREFIX
DOWNLOAD_DIR = _get_env("DOWNLOAD_DIR") or _config.get("DOWNLOAD_DIR") or _DEFAULT_DIR
MAX_FILE_SIZE = _get_int("MAX_FILE_SIZE", int(_config.get("MAX_FILE_SIZE", _DEFAULT_MAX_MB)))

def validate_settings():
    """設定値の検証"""
    if DISCORD_TOKEN == _DEFAULT_TOKEN:
        raise ValueError("DISCORD_TOKEN を .env（推奨）または環境変数で設定してください。")

    # FFmpeg の存在確認（無い場合は警告。ダウンロード/変換/音声再生で必要）
    ffmpeg_location = _get_env("FFMPEG_LOCATION")
    ffmpeg_ok = False
    if ffmpeg_location:
        p = Path(ffmpeg_location)
        if p.is_dir():
            ffmpeg_ok = (p / "ffmpeg.exe").exists() or (p / "ffmpeg").exists()
        else:
            ffmpeg_ok = p.exists()
    else:
        ffmpeg_ok = shutil.which("ffmpeg") is not None

    if not ffmpeg_ok:
        logger.warning(
            "FFmpeg が見つかりません。音声再生/MP3変換/動画結合が失敗します。"
            " Windowsなら winget/choco でインストールするか、.env に FFMPEG_LOCATION を設定してください。"
        )
    
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
        'FFMPEG_LOCATION': _get_env('FFMPEG_LOCATION')  # None の場合は自動検出
    }
