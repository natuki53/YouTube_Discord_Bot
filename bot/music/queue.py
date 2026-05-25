"""シンプルな FIFO 音楽キュー"""

from typing import List, Optional

from .models import Track


class MusicQueue:
    """ギルド単位の FIFO キュー"""

    def __init__(self):
        self._tracks: List[Track] = []

    def enqueue(self, track: Track) -> None:
        self._tracks.append(track)

    def dequeue(self) -> Optional[Track]:
        if not self._tracks:
            return None
        return self._tracks.pop(0)

    def clear(self) -> int:
        count = len(self._tracks)
        self._tracks.clear()
        return count

    def peek_all(self) -> List[Track]:
        return list(self._tracks)

    def __len__(self) -> int:
        return len(self._tracks)

    def __bool__(self) -> bool:
        return bool(self._tracks)
