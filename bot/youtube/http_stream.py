"""Bounded-range HTTP reader for token-protected YouTube media."""

import io
import logging
import threading
import time
from typing import Mapping

import requests

logger = logging.getLogger(__name__)

# Current mweb media URLs reject FFmpeg's open-ended Range request and large
# bounded requests. 512 KiB remains comfortably below the accepted limit.
MAX_CHUNK_SIZE = 512 * 1024
MAX_RANGE_READ_RETRIES = 3
RANGE_READ_RETRY_BASE_DELAY_SECONDS = 0.25


class FFmpegPipeInput:
    """Signal EOF to FFmpeg when its input reader exhausts its retries.

    discord.py's pipe writer does not catch exceptions from source.read().
    Returning EOF lets it close stdin and complete the playback callback;
    the callback can then report the saved error and resolve a fresh URL.
    """

    def __init__(self, stream: io.RawIOBase) -> None:
        self._stream = stream
        self.error: Exception | None = None

    def read(self, size: int = -1) -> bytes:
        if self.error is not None:
            return b""
        try:
            return self._stream.read(size)
        except Exception as exc:
            self.error = exc
            return b""


class YouTubeHTTPStream(io.RawIOBase):
    """Read a signed media URL through sequential bounded Range requests."""

    def __init__(
        self,
        url: str,
        http_headers: Mapping[str, str],
        filesize: int,
        chunk_size: int,
        *,
        start: int = 0,
        end: int | None = None,
    ) -> None:
        super().__init__()
        if filesize <= 0:
            raise ValueError("filesize must be positive")
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if not 0 <= start < filesize or (
            end is not None and not start <= end < filesize
        ):
            raise ValueError("invalid byte range")

        self._url = url
        self._headers = dict(http_headers)
        self._filesize = filesize
        self._chunk_size = min(chunk_size, MAX_CHUNK_SIZE)
        self._position = start
        self._limit = filesize if end is None else end + 1
        self._cancelled = False
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
        self._chunk_end = (
            min(
                self._position + self._chunk_size,
                self._limit,
            )
            - 1
        )
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
            if self.closed or self._cancelled or self._position >= self._limit:
                return b""

            retry_count = 0
            while True:
                if self._cancelled:
                    return b""
                try:
                    if self._response is None or self._position > self._chunk_end:
                        self._open_next_chunk()

                    remaining = self._chunk_end - self._position + 1
                    read_size = (
                        remaining if size is None or size < 0 else min(size, remaining)
                    )
                    data = self._response.raw.read(read_size)
                    if not data:
                        raise OSError("YouTube range response ended unexpectedly")

                    self._position += len(data)
                    if self._position > self._chunk_end:
                        self._close_response()
                    return data
                except Exception as exc:
                    self._close_response()
                    if retry_count >= MAX_RANGE_READ_RETRIES:
                        logger.error(
                            "YouTube ranged stream exhausted retries at byte %s",
                            self._position,
                        )
                        raise OSError(
                            "YouTube ranged stream failed after retries"
                        ) from exc

                    retry_count += 1
                    delay = RANGE_READ_RETRY_BASE_DELAY_SECONDS * retry_count
                    logger.warning(
                        "YouTube ranged stream interrupted at byte %s; "
                        "retrying %s/%s in %.2fs",
                        self._position,
                        retry_count,
                        MAX_RANGE_READ_RETRIES,
                        delay,
                    )
                    time.sleep(delay)

    def close(self) -> None:
        with self._lock:
            if not self.closed:
                self._close_response()
                self._session.close()
            super().close()

    def cancel(self) -> None:
        # Do not block Discord's event loop on an upstream socket read.
        self._cancelled = True
