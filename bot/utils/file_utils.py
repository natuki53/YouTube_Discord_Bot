"""
ファイル操作ユーティリティ

ファイルのクリーンアップとプロセス管理
"""

import os
import time
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def cleanup_audio_file(file_path: str, guild_id: int = None):
    """音声ファイルを確実に削除するヘルパー関数"""
    try:
        # ファイルが存在するか確認
        if os.path.exists(file_path):
            # ファイルを削除
            os.remove(file_path)
            logger.info(f"✅ Cleaned up audio file: {file_path}")
            return True
        else:
            logger.info(f"Audio file already removed: {file_path}")
            return True
            
    except PermissionError:
        logger.warning(f"Permission denied when trying to delete: {file_path}")
        # 少し待ってから再試行
        time.sleep(1)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"✅ Cleaned up audio file on retry: {file_path}")
                return True
        except Exception as e:
            logger.error(f"Failed to delete file on retry: {e}")
            return False
            
    except Exception as e:
        logger.error(f"Failed to cleanup audio file: {e}")
        # 最終手段：ファイルパスを記録して後で削除を試行
        logger.warning(f"File {file_path} will be cleaned up later")
        return False

def cleanup_old_audio_files(download_dir: str, max_age_hours: int = 1):
    """古い音声ファイルをクリーンアップする関数"""
    try:
        current_time = time.time()
        # 指定時間以上古い音声ファイルを削除
        cutoff_time = current_time - (max_age_hours * 3600)
        
        audio_files = list(Path(download_dir).glob("*.mp3"))
        cleaned_count = 0
        
        for file_path in audio_files:
            try:
                file_age = current_time - file_path.stat().st_mtime
                if file_age > cutoff_time:
                    os.remove(file_path)
                    cleaned_count += 1
                    logger.info(f"Cleaned up old audio file: {file_path}")
            except Exception as e:
                logger.error(f"Failed to cleanup old file {file_path}: {e}")
        
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} old audio files")
        else:
            logger.info("No old audio files to clean up")
            
        return cleaned_count
            
    except Exception as e:
        logger.error(f"Failed to cleanup old audio files: {e}")
        return 0

def force_kill_ffmpeg_processes():
    """残っているFFmpegプロセスを強制終了する関数"""
    try:
        import psutil
        
        killed_count = 0
        # FFmpegプロセスを検索して終了
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if 'ffmpeg' in proc.info['name'].lower():
                    logger.warning(f"Force killing FFmpeg process: {proc.info['pid']}")
                    proc.kill()
                    killed_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
                
        if killed_count > 0:
            logger.info(f"Killed {killed_count} FFmpeg processes")
        else:
            logger.info("No FFmpeg processes to kill")
        
        return killed_count
        
    except ImportError:
        logger.warning("psutil not available, skipping FFmpeg process cleanup")
        return 0
    except Exception as e:
        logger.error(f"Failed to cleanup FFmpeg processes: {e}")
        return 0

def get_latest_audio_file(download_dir: str, extension: str = "mp3"):
    """最新の音声ファイルを取得"""
    try:
        audio_files = list(Path(download_dir).glob(f"*.{extension}"))
        if audio_files:
            # 最新のファイルを取得（作成時刻順）
            latest_file = max(audio_files, key=lambda x: x.stat().st_mtime)
            return str(latest_file)
        return None
    except Exception as e:
        logger.error(f"Failed to get latest audio file: {e}")
        return None

def validate_audio_file(file_path: str):
    """音声ファイルの妥当性をチェック"""
    try:
        if not os.path.exists(file_path):
            logger.error(f"Audio file not found: {file_path}")
            return False
        
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            logger.error(f"Audio file is empty: {file_path}")
            return False
        
        logger.debug(f"Audio file validated: {file_path} (size: {file_size} bytes)")
        return True
        
    except Exception as e:
        logger.error(f"Failed to validate audio file {file_path}: {e}")
        return False
