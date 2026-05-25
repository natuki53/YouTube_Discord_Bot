"""
ファイル操作ユーティリティ（簡素化版）

VC ストリーミング再生ではファイル削除キューは不要。
FFmpeg プロセス管理のみ維持。
"""

import logging

logger = logging.getLogger(__name__)


def force_kill_ffmpeg_processes():
    """残っている FFmpeg プロセスを強制終了"""
    try:
        import psutil

        killed_count = 0
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if "ffmpeg" in proc.info["name"].lower():
                    logger.warning(f"Force killing FFmpeg process: {proc.info['pid']}")
                    proc.kill()
                    killed_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        if killed_count > 0:
            logger.info(f"Killed {killed_count} FFmpeg process(es)")
        return killed_count

    except ImportError:
        logger.warning("psutil not available, skipping FFmpeg process cleanup")
        return 0
    except Exception as e:
        logger.error(f"Failed to cleanup FFmpeg processes: {e}")
        return 0
