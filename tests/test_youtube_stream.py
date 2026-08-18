import unittest
from unittest.mock import patch

from bot.youtube.stream import PO_TOKEN_PROVIDER_URL, YDL_OPTS, _extract_stream


class ExtractStreamTests(unittest.TestCase):
    def test_stream_prefers_hls_before_direct_audio(self):
        self.assertEqual(
            YDL_OPTS["format"],
            (
                "best[protocol^=m3u8][height<=360]/"
                "worst[protocol^=m3u8]/bestaudio/best"
            ),
        )

    def test_stream_uses_po_token_provider_for_direct_media(self):
        self.assertEqual(
            YDL_OPTS["extractor_args"],
            {
                "youtube": {
                    "player_client": [
                        "web_safari",
                        "web_music",
                        "web_embedded",
                        "mweb",
                    ]
                },
                "youtubepot-bgutilhttp": {
                    "base_url": [PO_TOKEN_PROVIDER_URL]
                },
            },
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
            "filesize": 123456,
            "downloader_options": {"http_chunk_size": 10485760},
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
        self.assertEqual(stream.filesize, 123456)
        self.assertEqual(stream.http_chunk_size, 10485760)

    @patch("bot.youtube.stream.time.sleep")
    @patch("bot.youtube.stream.time.time", return_value=100)
    @patch("bot.youtube.stream.yt_dlp.YoutubeDL")
    def test_stream_waits_until_youtube_format_is_available(
        self, youtube_dl, _time, sleep
    ):
        extractor = youtube_dl.return_value.__enter__.return_value
        extractor.extract_info.return_value = {
            "url": "https://example.test/audio",
            "title": "Test track",
            "id": "video-id",
            "available_at": 105,
        }

        _extract_stream("https://youtu.be/video-id")

        sleep.assert_called_once_with(5)


if __name__ == "__main__":
    unittest.main()
