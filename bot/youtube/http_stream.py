"""Bounded-range HTTP reader for token-protected YouTube media."""

import io
import logging
import threading
from typing import Mapping

import requests

logger = logging.getLogger(__name__)

# Current mweb media URLs reject FFmpeg's open-ended Range request and large
# bounded requests. 512 KiB remains comfortably below the accepted limit.
MAX_CHUNK_SIZE = 512 * 1024


class YouTubeHTTPStream(io.RawIOBase):
    """Read a signed media URL through sequential bounded Range requests."""

    def __init__(
        self,
        url: str,
        http_headers: Mapping[str, str],
        filesize: int,
        chunk_size: int,
    ) -> None:
        super().__init__()
        if filesize <= 0:
            raise ValueError("filesize must be positive")
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")

        self._url = url
        self._headers = dict(http_headers)
        self._filesize = filesize
        self._chunk_size = min(chunk_size, MAX_CHUNK_SIZE)
        self._position = 0
        self._chunk_end = -1
        self._session = requests.Session()
        self._response = None
        self._lock = threading.RLock()

    def readable(self) -> bool:
        return True

    def _close_response(self) -> None:
        if self._response is not None:
            self._response.close()
            self._response = None

    def _open_next_chunk(self) -> None:
        self._close_response()
        self._chunk_end = min(
            self._position + self._chunk_size,
            self._filesize,
        ) - 1
        headers = dict(self._headers)
        headers["Range"] = f"bytes={self._position}-{self._chunk_end}"
        response = self._session.get(
            self._url,
            headers=headers,
            stream=True,
            timeout=(10, 30),
        )
        response.raise_for_status()
        self._response = response

    def read(self, size: int = -1) -> bytes:
        with self._lock:
            if self.closed or self._position >= self._filesize:
                return b""

            try:
                if self._response is None or self._position > self._chunk_end:
                    self._open_next_chunk()

                remaining = self._chunk_end - self._position + 1
                read_size = (
                    remaining
                    if size is None or size < 0
                    else min(size, remaining)
                )
                data = self._response.raw.read(read_size)
                if not data:
                    raise OSError("YouTube range response ended unexpectedly")

                self._position += len(data)
                if self._position > self._chunk_end:
                    self._close_response()
                return data
            except Exception as exc:
                logger.warning(
                    "YouTube ranged stream failed at byte %s: %s",
                    self._position,
                    exc,
                )
                self.close()
                return b""

    def close(self) -> None:
        with self._lock:
            if not self.closed:
                self._close_response()
                self._session.close()
            super().close()
