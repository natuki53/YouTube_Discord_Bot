"""音楽トラックのデータモデル"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import uuid4
from urllib.parse import urlsplit


def requester_avatar_url(member):
    """Use Discord's cached avatar asset; never fetch a member for a queue row."""
    asset = getattr(member, "display_avatar", None)
    if asset is None:
        return None
    url = asset.with_size(64).url
    if not isinstance(url, str):
        return None
    parsed = urlsplit(url)
    if parsed.scheme == "https" and parsed.netloc == "cdn.discordapp.com":
        return url
    return None


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
    requester_avatar: Optional[str] = None
    queue_id: str = field(default_factory=lambda: uuid4().hex)
    resume_position: float = 0.0
    resume_paused: bool = False

    def __post_init__(self):
        if self.added_at is None:
            self.added_at = datetime.now()
