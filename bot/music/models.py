"""音楽トラックのデータモデル"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Track:
    """キューに入る音楽トラック"""

    url: str
    title: str
    requester: str
    added_at: Optional[datetime] = None

    def __post_init__(self):
        if self.added_at is None:
            self.added_at = datetime.now()
