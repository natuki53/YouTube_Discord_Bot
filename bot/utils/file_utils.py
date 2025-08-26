"""
ファイル操作ユーティリティ

ファイルのクリーンアップとプロセス管理
"""

import os
import time
import platform
import gc
import threading
import asyncio
from pathlib import Path
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# バックグラウンド削除用のワーカー
_deletion_queue = []
_deletion_lock = threading.Lock()
_deletion_worker_running = False

# 保護されたファイル（ループ中など）を追跡
_protected_files = set()
_protected_files_lock = threading.Lock()

def cleanup_audio_file(file_path: str, guild_id: int = None, force_delete: bool = False):
    """音声ファイルを確実に削除するヘルパー関数（即座に返し、バックグラウンドで削除）"""
    try:
        # ファイルが存在するか確認
        if not os.path.exists(file_path):
            logger.info(f"Audio file already removed: {file_path}")
            return True
        
        # force_deleteがFalseの場合、保護されたファイルかチェック
        if not force_delete and _is_file_protected(file_path):
            logger.info(f"🔒 Skipping deletion of protected file (loop/active): {file_path}")
            return True
        
        # まずはシンプルに削除を試行
        try:
            os.remove(file_path)
            logger.info(f"✅ Cleaned up audio file: {file_path}")
            return True
        except PermissionError:
            # 削除できない場合はバックグラウンドキューに追加
            logger.info(f"Adding file to background deletion queue: {file_path}")
            _add_to_deletion_queue(file_path, guild_id)
            return True  # 即座にTrueを返して次の再生を妨げない
        
    except Exception as e:
        logger.error(f"Failed to cleanup audio file: {e}")
        # エラーが発生した場合もバックグラウンドで処理
        _add_to_deletion_queue(file_path, guild_id)
        return True

def protect_file(file_path: str):
    """ファイルを削除から保護する（ループ中など）"""
    if file_path:
        with _protected_files_lock:
            _protected_files.add(os.path.abspath(file_path))
            logger.debug(f"🔒 Protected file from deletion: {file_path}")

def unprotect_file(file_path: str):
    """ファイルの保護を解除する"""
    if file_path:
        with _protected_files_lock:
            abs_path = os.path.abspath(file_path)
            _protected_files.discard(abs_path)
            logger.debug(f"🔓 Unprotected file: {file_path}")

def _is_file_protected(file_path: str) -> bool:
    """ファイルが保護されているかチェック"""
    if not file_path:
        return False
    with _protected_files_lock:
        return os.path.abspath(file_path) in _protected_files

def _add_to_deletion_queue(file_path: str, guild_id: Optional[int] = None):
    """バックグラウンド削除キューにファイルを追加"""
    global _deletion_worker_running
    
    with _deletion_lock:
        _deletion_queue.append({
            'file_path': file_path,
            'guild_id': guild_id,
            'added_at': time.time()
        })
        logger.debug(f"Added to deletion queue: {file_path}")
        
        # ワーカーが動いていない場合は開始
        if not _deletion_worker_running:
            _deletion_worker_running = True
            worker_thread = threading.Thread(target=_background_deletion_worker, daemon=True)
            worker_thread.start()
            logger.debug("Started background deletion worker")

def _background_deletion_worker():
    """バックグラウンドでファイル削除を実行するワーカー"""
    global _deletion_worker_running
    
    try:
        processed_count = 0
        while True:
            # キューからファイルを取得
            file_item = None
            with _deletion_lock:
                if _deletion_queue:
                    file_item = _deletion_queue.pop(0)
                else:
                    # キューが空の場合はワーカーを停止
                    _deletion_worker_running = False
                    if processed_count > 0:
                        logger.info(f"Background deletion worker processed {processed_count} files")
                    logger.debug("Background deletion worker stopping (queue empty)")
                    break
            
            if file_item:
                success = _attempt_background_deletion(file_item)
                if success:
                    processed_count += 1
                # 次のファイル処理まで短い間隔で待機（CPUを過度に使用しないため）
                time.sleep(0.5)
    
    except Exception as e:
        logger.error(f"Background deletion worker error: {e}")
        _deletion_worker_running = False

def _attempt_background_deletion(file_item: dict):
    """バックグラウンドでファイル削除を試行"""
    file_path = file_item['file_path']
    guild_id = file_item.get('guild_id')
    
    try:
        # ファイルが存在するか確認
        if not os.path.exists(file_path):
            logger.info(f"Background: File already removed: {file_path}")
            return True
        
        # ガベージコレクションを実行
        gc.collect()
        
        # Windows特有の問題に対処
        if platform.system() == "Windows":
            try:
                import stat
                os.chmod(file_path, stat.S_IWRITE)
            except Exception:
                pass
        
        # 段階的リトライ（最大5回、短い間隔）
        for retry_count in range(5):
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"✅ Background deleted audio file: {file_path}")
                    return True
                else:
                    logger.info(f"Background: File already removed: {file_path}")
                    return True
            except PermissionError:
                if retry_count < 4:
                    # 短い待機時間でリトライ
                    wait_time = (retry_count + 1) * 1  # 1, 2, 3, 4, 5秒
                    logger.debug(f"Background retry {retry_count + 1} in {wait_time}s: {file_path}")
                    time.sleep(wait_time)
                    gc.collect()
                else:
                    # 最後の試行で失敗した場合は強制削除を試行
                    logger.warning(f"Background deletion failed after retries: {file_path}")
                    return _force_file_deletion(file_path)
            except Exception as e:
                logger.error(f"Background deletion error (attempt {retry_count + 1}): {e}")
                if retry_count == 4:
                    return _force_file_deletion(file_path)
                time.sleep(1)
        
        return False
        
    except Exception as e:
        logger.error(f"Background file deletion failed: {e}")
        return False

def _force_file_deletion(file_path: str) -> bool:
    """強制ファイル削除（最終手段）"""
    try:
        import tempfile
        import shutil
        
        # 一時ディレクトリにファイルを移動してから削除
        temp_dir = tempfile.mkdtemp()
        temp_file = os.path.join(temp_dir, f"temp_{int(time.time())}.tmp")
        
        try:
            shutil.move(file_path, temp_file)
            logger.info(f"Moved file to temp location: {temp_file}")
            
            # 移動後に削除を試行
            time.sleep(1)
            os.remove(temp_file)
            os.rmdir(temp_dir)
            logger.info(f"✅ Force deleted file: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Force deletion failed: {e}")
            # 一時ファイルが残った場合のクリーンアップ
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                if os.path.exists(temp_dir):
                    os.rmdir(temp_dir)
            except:
                pass
            return False
            
    except Exception as e:
        logger.error(f"Failed to setup force deletion: {e}")
        
        # 最後の最後：ファイルを削除予定リストに追加
        _schedule_file_for_deletion(file_path)
        return False

def _schedule_file_for_deletion(file_path: str):
    """削除予定ファイルリストに追加"""
    try:
        # 削除予定ファイルのリストファイルを作成
        pending_deletions_file = os.path.join(os.path.dirname(file_path), ".pending_deletions.txt")
        
        with open(pending_deletions_file, "a", encoding="utf-8") as f:
            f.write(f"{file_path}\n")
        
        logger.warning(f"File scheduled for later deletion: {file_path}")
        
    except Exception as e:
        logger.error(f"Failed to schedule file for deletion: {e}")

def cleanup_old_audio_files(download_dir: str, max_age_hours: int = 1):
    """古い音声ファイルをクリーンアップする関数"""
    try:
        # まず削除予定ファイルを処理
        pending_count = process_pending_deletions(download_dir)
        
        current_time = time.time()
        # 指定時間以上古い音声ファイルを削除
        cutoff_time = current_time - (max_age_hours * 3600)
        
        audio_files = list(Path(download_dir).glob("*.mp3"))
        cleaned_count = 0
        
        for file_path in audio_files:
            try:
                file_age = current_time - file_path.stat().st_mtime
                if file_age > cutoff_time:
                    # 保護されたファイルはスキップ
                    if _is_file_protected(str(file_path)):
                        logger.info(f"🔒 Skipping cleanup of protected old file: {file_path}")
                        continue
                        
                    success = cleanup_audio_file(str(file_path))
                    if success:
                        cleaned_count += 1
                        logger.info(f"Cleaned up old audio file: {file_path}")
            except Exception as e:
                logger.error(f"Failed to cleanup old file {file_path}: {e}")
        
        total_cleaned = cleaned_count + pending_count
        if total_cleaned > 0:
            logger.info(f"Cleaned up {total_cleaned} audio files (new: {cleaned_count}, pending: {pending_count})")
        else:
            logger.info("No old audio files to clean up")
            
        return total_cleaned
            
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

def process_pending_deletions(download_dir: str):
    """削除予定ファイルの処理"""
    try:
        pending_deletions_file = os.path.join(download_dir, ".pending_deletions.txt")
        
        if not os.path.exists(pending_deletions_file):
            return 0
        
        deleted_count = 0
        remaining_files = []
        
        with open(pending_deletions_file, "r", encoding="utf-8") as f:
            file_paths = [line.strip() for line in f.readlines() if line.strip()]
        
        for file_path in file_paths:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"✅ Deleted pending file: {file_path}")
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Still unable to delete: {file_path} - {e}")
                    remaining_files.append(file_path)
            else:
                logger.info(f"Pending file already removed: {file_path}")
                deleted_count += 1
        
        # 削除できなかったファイルがある場合、リストを更新
        if remaining_files:
            with open(pending_deletions_file, "w", encoding="utf-8") as f:
                for file_path in remaining_files:
                    f.write(f"{file_path}\n")
            logger.info(f"Updated pending deletions list with {len(remaining_files)} remaining files")
        else:
            # すべて削除できた場合、リストファイルも削除
            try:
                os.remove(pending_deletions_file)
                logger.info("Removed pending deletions list file")
            except Exception as e:
                logger.warning(f"Failed to remove pending deletions file: {e}")
        
        if deleted_count > 0:
            logger.info(f"Processed {deleted_count} pending file deletions")
        
        return deleted_count
        
    except Exception as e:
        logger.error(f"Failed to process pending deletions: {e}")
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

def safe_file_operation(file_path: str, operation_name: str = "operation"):
    """ファイル操作の安全なコンテキストマネージャー"""
    class SafeFileContext:
        def __enter__(self):
            return file_path
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type:
                logger.warning(f"Exception during {operation_name} on {file_path}: {exc_val}")
            # ガベージコレクションを実行してファイルハンドルを解放
            gc.collect()
            return False
    
    return SafeFileContext()

def cleanup_downloads_directory(download_dir: str):
    """ダウンロードディレクトリの包括的なクリーンアップ"""
    try:
        logger.info(f"Starting comprehensive cleanup of {download_dir}")
        
        # 1. 削除予定ファイルの処理
        pending_count = process_pending_deletions(download_dir)
        
        # 2. FFmpegプロセスの強制終了
        killed_count = force_kill_ffmpeg_processes()
        
        # 3. 古いファイルのクリーンアップ
        old_files_count = cleanup_old_audio_files(download_dir, max_age_hours=1)
        
        # 4. バックグラウンド削除キューの状況を報告
        with _deletion_lock:
            queue_size = len(_deletion_queue)
        
        logger.info(f"Cleanup completed: {pending_count} pending files, {killed_count} processes killed, {old_files_count} total files cleaned, {queue_size} files in background queue")
        
        return {
            'pending_files': pending_count,
            'killed_processes': killed_count,
            'cleaned_files': old_files_count,
            'background_queue': queue_size
        }
        
    except Exception as e:
        logger.error(f"Failed to cleanup downloads directory: {e}")
        return {'error': str(e)}

def get_deletion_queue_status():
    """バックグラウンド削除キューの状況を取得"""
    try:
        with _deletion_lock:
            queue_size = len(_deletion_queue)
            worker_running = _deletion_worker_running
            
        return {
            'queue_size': queue_size,
            'worker_running': worker_running,
            'queue_items': [item['file_path'] for item in _deletion_queue] if queue_size > 0 else []
        }
    except Exception as e:
        logger.error(f"Failed to get deletion queue status: {e}")
        return {'error': str(e)}
