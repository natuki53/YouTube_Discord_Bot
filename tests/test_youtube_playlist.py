import unittest
from unittest.mock import patch

from bot.youtube.playlist import playlist_id, resolve_playlist
from bot.youtube.search import SearchError


class PlaylistTests(unittest.TestCase):
    def test_playlist_detection_accepts_youtube_music_and_watch_links(self):
        for url in (
            "https://www.youtube.com/playlist?list=PL123",
            "https://music.youtube.com/playlist?list=PL123",
            "https://www.youtube.com/watch?v=12345678901&list=PL123",
            "youtu.be/12345678901?list=PL123",
        ):
            self.assertEqual(playlist_id(url), "PL123")
        for url in (
            "https://youtube.com.evil.example/playlist?list=PL123",
            "https://youtube.com@evil.example/playlist?list=PL123",
            "好きな曲",
            "https://www.youtube.com/watch?v=12345678901",
        ):
            self.assertIsNone(playlist_id(url))

    def test_order_unavailable_entries_and_no_download(self):
        info = {
            "title": "Playlist",
            "entries": [
                {"id": "12345678901", "title": "First"},
                None,
                {"id": "23456789012", "title": "Private", "availability": "private"},
                {"id": "34567890123", "title": "Last"},
            ],
        }
        with patch("bot.youtube.playlist.yt_dlp.YoutubeDL") as ydl:
            ydl.return_value.__enter__.return_value.extract_info.return_value = info
            target = resolve_playlist("https://youtube.com/playlist?list=PL123")
        self.assertEqual([t.display_title for t in target.tracks], ["First", "Last"])
        self.assertEqual(target.skipped, 2)
        self.assertTrue(
            all(
                t.url.startswith("https://www.youtube.com/watch?v=")
                for t in target.tracks
            )
        )
        self.assertEqual(ydl.call_args.args[0]["playlistend"], 51)
        ydl.return_value.__enter__.return_value.extract_info.assert_called_once_with(
            "https://www.youtube.com/playlist?list=PL123", download=False
        )

    def test_large_playlist_is_bounded_to_first_fifty(self):
        info = {
            "entries": [{"id": f"{i:011d}", "title": str(i)} for i in range(51)],
            "playlist_count": 500,
        }
        with patch("bot.youtube.playlist.yt_dlp.YoutubeDL") as ydl:
            ydl.return_value.__enter__.return_value.extract_info.return_value = info
            target = resolve_playlist("https://youtube.com/playlist?list=PL123")
        self.assertEqual(len(target.tracks), 50)
        self.assertTrue(target.truncated)

    def test_private_or_empty_playlist_reports_error(self):
        with patch("bot.youtube.playlist.yt_dlp.YoutubeDL") as ydl:
            ydl.return_value.__enter__.return_value.extract_info.return_value = {
                "entries": []
            }
            with self.assertRaises(SearchError):
                resolve_playlist("https://youtube.com/playlist?list=PL123")
