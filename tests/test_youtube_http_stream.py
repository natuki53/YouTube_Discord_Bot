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


if __name__ == "__main__":
    unittest.main()
