import unittest
from unittest.mock import Mock, patch

import requests

from bot.youtube.stream import (
    PO_TOKEN_PROVIDER_URL, YDL_OPTS, StreamError, StreamInfo,
    _extract_stream, _probe_direct_stream,
)


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
                    "player_client": ["tv_simply"]
                },
                "youtubepot-bgutilhttp": {
                    "base_url": [PO_TOKEN_PROVIDER_URL]
                },
            },
        )

    @patch("bot.youtube.stream.requests.get")
    def test_direct_media_is_checked_beyond_preview_boundary(self, get):
        response = get.return_value.__enter__.return_value
        response.status_code = 206
        response.headers = {"Content-Range": "bytes 2096128-2097151/2097152"}
        response.raw.read.return_value = b"a" * 1024
        stream = StreamInfo(
            "https://example.test/audio?signed=private", "test", "id",
            filesize=2097152, http_chunk_size=524288,
        )
        _probe_direct_stream(stream)
        self.assertEqual(get.call_args.kwargs["headers"]["Range"], "bytes=2096128-2097151")

    @patch("bot.youtube.stream.requests.get")
    def test_preview_only_media_is_rejected_without_logging_signed_url(self, get):
        response = get.return_value.__enter__.return_value
        response.raise_for_status.side_effect = requests.HTTPError(
            "403 for https://example.test/audio?signed=private",
            response=Mock(status_code=403),
        )
        stream = StreamInfo(
            "https://example.test/audio?signed=private", "test", "id",
            filesize=2097152, http_chunk_size=524288,
        )
        with self.assertLogs("bot.youtube.stream", level="WARNING") as logs:
            with self.assertRaises(StreamError):
                _probe_direct_stream(stream)
        self.assertIn("HTTP=403", " ".join(logs.output))
        self.assertNotIn("private", " ".join(logs.output))

    @patch("bot.youtube.stream.requests.get")
    def test_direct_probe_rejects_ignored_or_incomplete_range(self, get):
        response = get.return_value.__enter__.return_value
        stream = StreamInfo("url", "test", "id", filesize=2097152, http_chunk_size=524288)
        response.status_code = 200
        with self.assertRaises(StreamError):
            _probe_direct_stream(stream)
        response.status_code = 206
        response.headers = {"Content-Range": "bytes 2096128-2097151/2097152"}
        response.raw.read.return_value = b"short"
        with self.assertRaises(StreamError):
            _probe_direct_stream(stream)

    @patch("bot.youtube.stream._probe_direct_stream")
    @patch("bot.youtube.stream._extract_stream_with_options")
    def test_rejected_media_uses_fresh_default_client_fallback(self, extract, probe):
        first = StreamInfo("preview", "test", "id")
        complete = StreamInfo("full", "test", "id")
        extract.side_effect = [first, complete]
        probe.side_effect = [StreamError("preview only"), None]
        self.assertIs(_extract_stream("https://youtu.be/test"), complete)
        self.assertEqual(
            [call.args[1]["extractor_args"]["youtube"]["player_client"] for call in extract.call_args_list],
            [["tv_simply"], ["default"]],
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
