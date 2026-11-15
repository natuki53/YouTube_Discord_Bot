import unittest
from unittest.mock import patch

from bot.youtube.search import SearchError, resolve_play_query, search_youtube


class ResolvePlayQueryTests(unittest.TestCase):
    @patch("bot.youtube.search.yt_dlp.YoutubeDL")
    def test_search_lists_metadata_without_downloading_and_uses_canonical_urls(
        self, youtube_dl
    ):
        extractor = youtube_dl.return_value.__enter__.return_value
        extractor.extract_info.return_value = {
            "entries": [
                {
                    "id": "12345678901",
                    "title": " First song ",
                    "channel": "Artist",
                    "duration": 245.7,
                    "url": "https://untrusted.example/",
                },
                {
                    "id": "23456789012",
                    "title": "Second song",
                    "uploader": "Channel",
                    "duration": None,
                },
                {"id": "12345678901", "title": "Duplicate"},
                {"id": "bad/id", "title": "Invalid"},
                None,
                {"id": "34567890123", "availability": "private"},
                {"id": "45678901234", "duration": float("nan")},
            ]
        }

        results = search_youtube("  artist song  ")

        extractor.extract_info.assert_called_once_with(
            "ytsearch10:artist song", download=False
        )
        self.assertTrue(youtube_dl.call_args.args[0]["extract_flat"])
        self.assertEqual(
            [r.video_id for r in results], ["12345678901", "23456789012", "45678901234"]
        )
        self.assertEqual(results[0].url, "https://www.youtube.com/watch?v=12345678901")
        self.assertEqual(
            (results[0].title, results[0].channel, results[0].duration),
            ("First song", "Artist", 245),
        )
        self.assertEqual((results[1].channel, results[1].duration), ("Channel", None))
        self.assertEqual((results[2].title, results[2].duration), ("artist song", None))

    @patch("bot.youtube.search.yt_dlp.YoutubeDL")
    def test_empty_search_is_distinct_from_upstream_failure(self, youtube_dl):
        extractor = youtube_dl.return_value.__enter__.return_value
        extractor.extract_info.return_value = {"entries": []}
        self.assertEqual(search_youtube("song"), [])
        with self.assertRaisesRegex(SearchError, "見つかりません"):
            resolve_play_query("song")
        extractor.extract_info.side_effect = RuntimeError("unavailable")
        with self.assertRaisesRegex(SearchError, "YouTube検索に失敗"):
            search_youtube("song")

    @patch("bot.youtube.search.yt_dlp.YoutubeDL")
    def test_search_rejects_invalid_input_before_network_access(self, youtube_dl):
        for query, limit in [
            (" ", 10),
            ("a" * 501, 10),
            ("song", 0),
            ("song", 11),
            ("song", True),
        ]:
            with self.subTest(query=query, limit=limit), self.assertRaises(SearchError):
                search_youtube(query, limit)
        youtube_dl.assert_not_called()

    @patch("bot.youtube.search.yt_dlp.YoutubeDL")
    def test_discord_keyword_resolution_still_selects_first_result(self, youtube_dl):
        extractor = youtube_dl.return_value.__enter__.return_value
        extractor.extract_info.return_value = {
            "entries": [{"id": "12345678901", "title": "First"}]
        }
        target = resolve_play_query("song")
        extractor.extract_info.assert_called_once_with("ytsearch1:song", download=False)
        self.assertEqual(
            (target.url, target.display_title),
            ("https://www.youtube.com/watch?v=12345678901", "First"),
        )

    @patch("bot.youtube.search.yt_dlp.YoutubeDL")
    def test_direct_url_uses_video_title(self, youtube_dl):
        extractor = youtube_dl.return_value.__enter__.return_value
        extractor.extract_info.return_value = {"title": "テスト楽曲"}

        target = resolve_play_query("https://youtu.be/dQw4w9WgXcQ")

        self.assertEqual(
            target.url,
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        self.assertEqual(target.display_title, "テスト楽曲")
        extractor.extract_info.assert_called_once_with(target.url, download=False)

    @patch("bot.youtube.search.yt_dlp.YoutubeDL")
    def test_direct_url_metadata_failure_is_reported(self, youtube_dl):
        extractor = youtube_dl.return_value.__enter__.return_value
        extractor.extract_info.side_effect = RuntimeError("metadata failed")

        with self.assertRaisesRegex(SearchError, "動画情報の取得に失敗"):
            resolve_play_query("https://youtu.be/dQw4w9WgXcQ")


if __name__ == "__main__":
    unittest.main()
