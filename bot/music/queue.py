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

    def remove(self, queue_id: str) -> Track:
        track = self._find(queue_id)
        self._tracks.remove(track)
        return track

    def move(self, queue_id: str, before_id: str | None) -> None:
        track = self._find(queue_id)
        before = self._find(before_id) if before_id is not None else None
        if before is track:
            return
        self._tracks.remove(track)
        index = self._tracks.index(before) if before else len(self._tracks)
        self._tracks.insert(index, track)

    def _find(self, queue_id: str) -> Track:
        for track in self._tracks:
            if track.queue_id == queue_id:
                return track
        raise ValueError("曲はすでに再生・削除されています。キューを確認してください。")

    def __len__(self) -> int:
        return len(self._tracks)

    def __bool__(self) -> bool:
        return bool(self._tracks)
