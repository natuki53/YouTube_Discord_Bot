"""
トラック情報管理

音楽トラックの情報を格納するクラス
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class TrackInfo:
    """音楽トラックの情報を格納するデータクラス"""
    url: str
    title: str = "Unknown Track"
    user: str = "Unknown User"
    added_at: Optional[datetime] = None
    duration: Optional[int] = None
    file_path: Optional[str] = None
    
    def __post_init__(self):
        if self.added_at is None:
            self.added_at = datetime.now()
    
    def to_dict(self):
        """辞書形式に変換"""
        return {
            'url': self.url,
            'title': self.title,
            'user': self.user,
            'added_at': self.added_at,
            'duration': self.duration,
            'file_path': self.file_path
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        """辞書から復元"""
        return cls(
            url=data['url'],
            title=data.get('title', 'Unknown Track'),
            user=data.get('user', 'Unknown User'),
            added_at=data.get('added_at'),
            duration=data.get('duration'),
            file_path=data.get('file_path')
        )
