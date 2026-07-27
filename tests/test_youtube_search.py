import unittest
from unittest.mock import patch

from bot.youtube.search import SearchError, resolve_play_query


class ResolvePlayQueryTests(unittest.TestCase):
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
