import unittest
from unittest.mock import patch

from bot.youtube.stream import YDL_OPTS, _extract_stream


class ExtractStreamTests(unittest.TestCase):
    def test_stream_prefers_hls_before_direct_audio(self):
        self.assertEqual(
            YDL_OPTS["format"],
            (
                "best[protocol^=m3u8][height<=360]/"
                "worst[protocol^=m3u8]/bestaudio/best"
            ),
        )

    @patch("bot.youtube.stream.yt_dlp.YoutubeDL")
    def test_stream_includes_http_headers_required_by_youtube(self, youtube_dl):
        extractor = youtube_dl.return_value.__enter__.return_value
        extractor.extract_info.return_value = {
            "url": "https://example.test/audio",
            "title": "Test track",
            "id": "video-id",
            "duration": 120,
            "webpage_url": "https://www.youtube.com/watch?v=video-id",
            "http_headers": {
                "User-Agent": "test-agent",
                "Accept": "*/*",
            },
        }

        stream = _extract_stream("https://youtu.be/video-id")

        self.assertEqual(
            stream.http_headers,
            {"User-Agent": "test-agent", "Accept": "*/*"},
        )


if __name__ == "__main__":
    unittest.main()
