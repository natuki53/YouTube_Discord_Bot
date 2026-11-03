"""音楽トラックのデータモデル"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import uuid4


@dataclass
class Track:
    """キューに入る音楽トラック"""

    url: str
    title: str
    requester: str
    added_at: Optional[datetime] = None
    video_id: Optional[str] = None
    auto_selected: bool = False
    requester_id: Optional[int] = None
    queue_id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self):
        if self.added_at is None:
            self.added_at = datetime.now()
