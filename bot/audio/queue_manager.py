"""
音声キュー管理

複数のギルドの音楽キューを管理するクラス
"""

import logging
from typing import Dict, List, Optional
from .track_info import TrackInfo

logger = logging.getLogger(__name__)

class AudioQueue:
    """音声キューを管理するクラス"""
    
    def __init__(self):
        self.queues: Dict[int, List[TrackInfo]] = {}  # guild_id -> queue
        self.now_playing: Dict[int, TrackInfo] = {}  # guild_id -> current_track
        self.downloaded_tracks: Dict[str, bool] = {}  # download_key -> status
    
    def add_track(self, guild_id: int, track_info: TrackInfo):
        """キューにトラックを追加"""
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        
        # 辞書形式のtrack_infoの場合はTrackInfoオブジェクトに変換
        if isinstance(track_info, dict):
            track_info = TrackInfo.from_dict(track_info)
        
        self.queues[guild_id].append(track_info)
        logger.info(f"Added track to queue for guild {guild_id}: {track_info.title}")
    
    def get_next_track(self, guild_id: int) -> Optional[TrackInfo]:
        """次のトラックを取得"""
        if guild_id in self.queues and self.queues[guild_id]:
            track = self.queues[guild_id].pop(0)
            self.now_playing[guild_id] = track
            logger.info(f"Next track for guild {guild_id}: {track.title}")
            return track
        return None
    
    def get_queue(self, guild_id: int) -> List[TrackInfo]:
        """キューの内容を取得"""
        if guild_id in self.queues:
            return self.queues[guild_id].copy()
        return []
    
    def clear_queue(self, guild_id: int):
        """キューをクリア"""
        if guild_id in self.queues:
            self.queues[guild_id].clear()
            logger.info(f"Cleared queue for guild {guild_id}")
    
    def get_queue_length(self, guild_id: int) -> int:
        """キューの長さを取得"""
        if guild_id in self.queues:
            return len(self.queues[guild_id])
        return 0
    
    def is_playing(self, guild_id: int) -> bool:
        """現在再生中かどうかを確認"""
        return guild_id in self.now_playing and self.now_playing[guild_id] is not None
    
    def get_now_playing(self, guild_id: int) -> Optional[TrackInfo]:
        """現在再生中のトラックを取得"""
        return self.now_playing.get(guild_id)
    
    def clear_now_playing(self, guild_id: int):
        """現在再生中のトラックをクリア"""
        if guild_id in self.now_playing:
            del self.now_playing[guild_id]
            logger.info(f"Cleared now playing for guild {guild_id}")
    
    def has_queue(self, guild_id: int) -> bool:
        """キューに曲があるかどうかを確認"""
        return guild_id in self.queues and len(self.queues[guild_id]) > 0
    
    def set_download_status(self, guild_id: int, url: str, status: bool):
        """ダウンロード状況を記録"""
        download_key = f"{guild_id}_{url}"
        self.downloaded_tracks[download_key] = status
        logger.debug(f"Set download status for {download_key}: {status}")
    
    def get_download_status(self, guild_id: int, url: str) -> bool:
        """ダウンロード状況を取得"""
        download_key = f"{guild_id}_{url}"
        return self.downloaded_tracks.get(download_key, False)
    
    def remove_guild_data(self, guild_id: int):
        """ギルドのすべてのデータを削除"""
        if guild_id in self.queues:
            del self.queues[guild_id]
        if guild_id in self.now_playing:
            del self.now_playing[guild_id]
        
        # ダウンロード情報も削除
        keys_to_remove = [key for key in self.downloaded_tracks.keys() if key.startswith(f"{guild_id}_")]
        for key in keys_to_remove:
            del self.downloaded_tracks[key]
        
        logger.info(f"Removed all data for guild {guild_id}")
    
    def get_guild_stats(self, guild_id: int) -> dict:
        """ギルドの統計情報を取得"""
        return {
            'queue_length': self.get_queue_length(guild_id),
            'is_playing': self.is_playing(guild_id),
            'current_track': self.get_now_playing(guild_id),
            'has_queue': self.has_queue(guild_id)
        }
