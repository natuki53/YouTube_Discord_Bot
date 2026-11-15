"""A private, seekable HTTP input for FFmpeg's bounded-range YouTube reader."""

import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .http_stream import YouTubeHTTPStream


class SeekableYouTubeInput:
    def __init__(self, url, headers, filesize, chunk_size):
        self.error = None
        self._streams = set()
        self._lock = threading.Lock()
        self._closed = threading.Event()
        token = "/" + secrets.token_urlsafe(24)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_HEAD(self):
                self.serve(head=True)

            def do_GET(self):
                self.serve(head=False)

            def serve(self, *, head):
                if self.path != token or owner._closed.is_set():
                    self.send_error(404)
                    return
                start, end = 0, filesize - 1
                value = self.headers.get("Range")
                if value:
                    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value)
                    if match and any(match.groups()):
                        first, last = match.groups()
                        if first:
                            start = int(first)
                            end = min(int(last), filesize - 1) if last else filesize - 1
                        else:
                            start = max(0, filesize - int(last))
                    else:
                        start = filesize
                    if not 0 <= start <= end < filesize:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{filesize}")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                self.send_response(206 if value else 200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(end - start + 1))
                if value:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{filesize}")
                self.end_headers()
                if head:
                    return
                stream = YouTubeHTTPStream(
                    url, headers, filesize, chunk_size, start=start, end=end
                )
                with owner._lock:
                    owner._streams.add(stream)
                try:
                    while not owner._closed.is_set():
                        data = stream.read(64 * 1024)
                        if not data:
                            break
                        self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    # FFmpeg deliberately closes the old range when seeking.
                    pass
                except Exception as error:
                    if not owner._closed.is_set():
                        owner.error = error
                finally:
                    stream.close()
                    with owner._lock:
                        owner._streams.discard(stream)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._server.block_on_close = False
        self.url = f"http://127.0.0.1:{self._server.server_port}{token}"
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            kwargs={"poll_interval": 0.05},
            daemon=True,
        )
        self._thread.start()

    def close(self):
        self._closed.set()
        with self._lock:
            for stream in self._streams:
                stream.cancel()
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=1)
