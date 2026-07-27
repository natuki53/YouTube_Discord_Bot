"""
アプリケーション設定管理

優先順位: デフォルト値 < .env < config.py（任意）
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


def _env(key: str, default: str = None) -> str:
    return os.getenv(key, default)


def _env_int(key: str, default: int) -> int:
    val = os.getenv(key)
    return int(val) if val is not None and val != "" else default


def _env_list(key: str, default: list) -> list:
    val = os.getenv(key)
    if val:
        return [x.strip() for x in val.split(",") if x.strip()]
    return default


DOWNLOAD_DIR = _env("DOWNLOAD_DIR", "./downloads")

DISCORD_TOKEN = _env("DISCORD_TOKEN", "your_discord_bot_token_here")
BOT_PREFIX = _env("BOT_PREFIX", "!")
DOWNLOAD_TMP_DIR = _env("DOWNLOAD_TMP_DIR") or os.path.join(DOWNLOAD_DIR, "tmp")
MAX_FILE_SIZE = _env_int("MAX_FILE_SIZE", 25)
SUPPORTED_QUALITIES = _env_list(
    "SUPPORTED_QUALITIES",
    ["144p", "240p", "360p", "480p", "720p", "1080p"],
)
MAX_CONCURRENT_DOWNLOADS = _env_int("MAX_CONCURRENT_DOWNLOADS", 2)
DOWNLOAD_TIMEOUT_SECONDS = _env_int("DOWNLOAD_TIMEOUT_SECONDS", 600)
MP3_BITRATE_DEFAULT = _env("MP3_BITRATE_DEFAULT", "192")
MP3_BITRATE_LONG = _env("MP3_BITRATE_LONG", "128")
TMP_MAX_AGE_MINUTES = _env_int("TMP_MAX_AGE_MINUTES", 30)
DEFAULT_VOLUME = _env_int("DEFAULT_VOLUME", 25)

# config.py があれば上書き（後方互換）
try:
    import config as _user_config

    for _key in (
        "DISCORD_TOKEN",
        "BOT_PREFIX",
        "DOWNLOAD_DIR",
        "DOWNLOAD_TMP_DIR",
        "MAX_FILE_SIZE",
        "SUPPORTED_QUALITIES",
        "MAX_CONCURRENT_DOWNLOADS",
        "DOWNLOAD_TIMEOUT_SECONDS",
        "MP3_BITRATE_DEFAULT",
        "MP3_BITRATE_LONG",
        "TMP_MAX_AGE_MINUTES",
        "DEFAULT_VOLUME",
    ):
        if hasattr(_user_config, _key):
            globals()[_key] = getattr(_user_config, _key)

    if not os.getenv("DOWNLOAD_TMP_DIR") and hasattr(_user_config, "DOWNLOAD_DIR"):
        if not hasattr(_user_config, "DOWNLOAD_TMP_DIR"):
            DOWNLOAD_TMP_DIR = os.path.join(DOWNLOAD_DIR, "tmp")

    logger.debug("Loaded overrides from config.py")
except ImportError:
    pass


def validate_settings():
    """設定値の検証"""
    if not DISCORD_TOKEN or DISCORD_TOKEN == "your_discord_bot_token_here":
        raise ValueError(
            ".env に DISCORD_TOKEN を設定してください。\n"
            "手順: cp .env.example .env のあと、トークンを記入して保存。"
        )

    Path(DOWNLOAD_DIR).mkdir(exist_ok=True)
    Path(DOWNLOAD_TMP_DIR).mkdir(parents=True, exist_ok=True)

    global DEFAULT_VOLUME
    if DEFAULT_VOLUME < 1:
        DEFAULT_VOLUME = 1
    elif DEFAULT_VOLUME > 100:
        DEFAULT_VOLUME = 100

    logger.info(f"Download directory: {DOWNLOAD_DIR}")
    logger.info(f"Default playback volume: {DEFAULT_VOLUME}%")
    logger.info(f"Download tmp directory: {DOWNLOAD_TMP_DIR}")

    return True


def get_settings():
    """設定値の辞書を返す"""
    return {
        "DISCORD_TOKEN": DISCORD_TOKEN,
        "BOT_PREFIX": BOT_PREFIX,
        "DOWNLOAD_DIR": DOWNLOAD_DIR,
        "DOWNLOAD_TMP_DIR": DOWNLOAD_TMP_DIR,
        "MAX_FILE_SIZE": MAX_FILE_SIZE,
        "SUPPORTED_QUALITIES": SUPPORTED_QUALITIES,
        "MAX_CONCURRENT_DOWNLOADS": MAX_CONCURRENT_DOWNLOADS,
        "DOWNLOAD_TIMEOUT_SECONDS": DOWNLOAD_TIMEOUT_SECONDS,
        "MP3_BITRATE_DEFAULT": MP3_BITRATE_DEFAULT,
        "MP3_BITRATE_LONG": MP3_BITRATE_LONG,
        "TMP_MAX_AGE_MINUTES": TMP_MAX_AGE_MINUTES,
        "DEFAULT_VOLUME": DEFAULT_VOLUME,
    }
