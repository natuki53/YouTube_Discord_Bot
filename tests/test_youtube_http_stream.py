import io
import unittest
from unittest.mock import Mock, patch

from bot.youtube.http_stream import YouTubeHTTPStream


class YouTubeHTTPStreamTests(unittest.TestCase):
    def test_reads_sequential_bounded_ranges(self):
        responses = []
        for payload in (b"abcd", b"efgh", b"ij"):
            response = Mock()
            response.raw = io.BytesIO(payload)
            responses.append(response)

        with patch("bot.youtube.http_stream.requests.Session") as session_cls:
            session_cls.return_value.get.side_effect = responses
            stream = YouTubeHTTPStream(
                "https://example.test/audio",
                {"User-Agent": "test"},
                filesize=10,
                chunk_size=4,
            )

            result = b"".join(iter(lambda: stream.read(2), b""))

        self.assertEqual(result, b"abcdefghij")
        requested_ranges = [
            call.kwargs["headers"]["Range"]
            for call in session_cls.return_value.get.call_args_list
        ]
        self.assertEqual(
            requested_ranges,
            ["bytes=0-3", "bytes=4-7", "bytes=8-9"],
        )

    @patch("bot.youtube.http_stream.time.sleep")
    def test_retries_from_current_position_after_interrupted_range(
        self,
        sleep,
    ):
        interrupted = Mock()
        interrupted.raw.read.side_effect = [
            b"ab",
            OSError("connection interrupted"),
        ]
        resumed = Mock()
        resumed.raw = io.BytesIO(b"cdef")

        with patch("bot.youtube.http_stream.requests.Session") as session_cls:
            session_cls.return_value.get.side_effect = [interrupted, resumed]
            stream = YouTubeHTTPStream(
                "https://example.test/audio",
                {},
                filesize=6,
                chunk_size=4,
            )

            result = b"".join(iter(lambda: stream.read(2), b""))

        self.assertEqual(result, b"abcdef")
        requested_ranges = [
            call.kwargs["headers"]["Range"]
            for call in session_cls.return_value.get.call_args_list
        ]
        self.assertEqual(requested_ranges, ["bytes=0-3", "bytes=2-5"])
        sleep.assert_called_once_with(0.25)

    @patch("bot.youtube.http_stream.time.sleep")
    def test_raises_after_range_retry_limit(self, sleep):
        responses = []
        for _ in range(4):
            response = Mock()
            response.raw.read.side_effect = OSError("connection interrupted")
            responses.append(response)

        with patch("bot.youtube.http_stream.requests.Session") as session_cls:
            session_cls.return_value.get.side_effect = responses
            stream = YouTubeHTTPStream(
                "https://example.test/audio",
                {},
                filesize=4,
                chunk_size=4,
            )

            with self.assertRaisesRegex(
                OSError,
                "YouTube ranged stream failed after retries",
            ):
                stream.read(2)

        self.assertEqual(session_cls.return_value.get.call_count, 4)
        self.assertEqual(sleep.call_count, 3)


if __name__ == "__main__":
    unittest.main()
