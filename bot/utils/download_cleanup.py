"""ダウンロード一時ファイルのクリーンアップ"""

import logging
import time
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)

ARTIFACT_SUFFIXES = (".part", ".ytdl", ".temp")


def ensure_tmp_dir(tmp_dir: Union[str, Path]) -> Path:
    path = Path(tmp_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def cleanup_artifacts(tmp_dir: Union[str, Path], video_id: str) -> int:
    """video_id に関連するファイルをすべて削除"""
    base = Path(tmp_dir)
    if not base.exists() or not video_id:
        return 0

    removed = 0
    patterns = [
        f"{video_id}.*",
        f"{video_id}.info.json",
    ]
    seen = set()
    for pattern in patterns:
        for path in base.glob(pattern):
            if path in seen:
                continue
            seen.add(path)
            try:
                path.unlink(missing_ok=True)
                removed += 1
                logger.debug(f"Removed artifact: {path}")
            except OSError as e:
                logger.warning(f"Failed to remove {path}: {e}")

    for path in base.iterdir():
        if video_id in path.name and path not in seen:
            try:
                path.unlink(missing_ok=True)
                removed += 1
            except OSError as e:
                logger.warning(f"Failed to remove {path}: {e}")

    return removed


def cleanup_stale_tmp(tmp_dir: Union[str, Path], max_age_minutes: int = 30) -> int:
    """古い一時ファイルを削除"""
    base = Path(tmp_dir)
    if not base.exists():
        return 0

    cutoff = time.time() - (max_age_minutes * 60)
    removed = 0
    for path in base.rglob("*"):
        if path.is_file():
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
                    removed += 1
            except OSError as e:
                logger.warning(f"Failed to remove stale file {path}: {e}")

    return removed
