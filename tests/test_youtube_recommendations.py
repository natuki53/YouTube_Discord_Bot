import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from bot.youtube.recommendations import (
    RADIO_TRACK_LIMIT,
    RadioTrack,
    RecommendationError,
    _fetch_radio_tracks,
    fetch_radio_tracks,
    youtube_video_id,
)

SEED_ID = "seed0000001"
NEXT_ID = "next0000001"


class RadioParsingTests(unittest.TestCase):
    def test_video_id_matches_url_variants_but_rejects_other_hosts(self):
        for url in (
            f"https://www.youtube.com/watch?v={SEED_ID}&t=30",
            f"https://music.youtube.com/watch?v={SEED_ID}",
            f"https://youtu.be/{SEED_ID}?si=example",
            f"https://www.youtube.com/embed/{SEED_ID}",
            f"https://www.youtube.com/shorts/{SEED_ID}",
        ):
            with self.subTest(url=url):
                self.assertEqual(youtube_video_id(url), SEED_ID)
        for url in (
            f"https://example.test/watch?v={SEED_ID}",
            f"https://youtube.com.example.test/watch?v={SEED_ID}",
            "https://youtube.com/watch?v=invalid",
            "https://youtube.com/playlist?list=example",
        ):
            with self.subTest(url=url):
                self.assertIsNone(youtube_video_id(url))

    def test_radio_filters_seed_duplicates_and_unavailable_items(self):
        entries = [
            None,
            {"videoId": SEED_ID, "title": "seed"},
            {"videoId": "invalid", "title": "invalid"},
            {"videoId": "empty000001", "title": " "},
            {"videoId": "live0000001", "title": "live", "isLive": True},
            {"videoId": "dead0000001", "title": "dead", "isAvailable": False},
            {
                "videoId": "podc0000001",
                "title": "podcast",
                "videoType": "MUSIC_VIDEO_TYPE_PODCAST_EPISODE",
            },
            {
                "videoId": NEXT_ID,
                "title": "次の曲",
                "artists": [{"name": "歌手"}, {"id": "unknown"}],
            },
            {"videoId": NEXT_ID, "title": "duplicate"},
        ]
        with (
            patch("bot.youtube.recommendations.requests.Session") as session_cls,
            patch("bot.youtube.recommendations.YTMusic") as music_cls,
        ):
            music_cls.return_value.get_watch_playlist.return_value = {"tracks": entries}
            tracks = _fetch_radio_tracks(SEED_ID)

        self.assertEqual(tracks, [RadioTrack(NEXT_ID, "歌手 - 次の曲")])
        self.assertEqual(tracks[0].url, f"https://www.youtube.com/watch?v={NEXT_ID}")
        session = session_cls.return_value.__enter__.return_value
        music_cls.assert_called_once_with(
            requests_session=session, language="ja", location="JP"
        )
        music_cls.return_value.get_watch_playlist.assert_called_once_with(
            videoId=SEED_ID, radio=True, limit=RADIO_TRACK_LIMIT
        )
        session_cls.return_value.__exit__.assert_called_once()
        self.assertEqual(session.request.keywords["timeout"], (5, 10))

    def test_result_limit_bounds_radio_candidates(self):
        entries = [{"videoId": f"{i:011d}", "title": "song"} for i in range(100)]
        with (
            patch("bot.youtube.recommendations.requests.Session"),
            patch("bot.youtube.recommendations.YTMusic") as music_cls,
        ):
            music_cls.return_value.get_watch_playlist.return_value = {"tracks": entries}
            self.assertEqual(len(_fetch_radio_tracks(SEED_ID)), RADIO_TRACK_LIMIT)


class RadioRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_lookup_runs_in_worker_thread(self):
        tracks = [RadioTrack(NEXT_ID, "next")]
        with patch(
            "bot.youtube.recommendations._fetch_radio_tracks", return_value=tracks
        ) as fetch:
            self.assertEqual(await fetch_radio_tracks(SEED_ID), tracks)
        fetch.assert_called_once_with(SEED_ID)

    async def test_invalid_video_id_does_not_make_a_request(self):
        with patch("bot.youtube.recommendations._fetch_radio_tracks") as fetch:
            with self.assertRaises(RecommendationError):
                await fetch_radio_tracks("invalid")
        fetch.assert_not_called()

    async def test_network_error_becomes_a_user_facing_error(self):
        with patch(
            "bot.youtube.recommendations._fetch_radio_tracks",
            side_effect=RuntimeError("offline"),
        ):
            with self.assertRaisesRegex(
                RecommendationError, "関連曲を取得できませんでした"
            ):
                await fetch_radio_tracks(SEED_ID)

    async def test_lookup_has_an_overall_timeout(self):
        async def blocked(*args):
            await asyncio.Event().wait()

        with (
            patch(
                "bot.youtube.recommendations.asyncio.to_thread",
                new=AsyncMock(side_effect=blocked),
            ),
            patch("bot.youtube.recommendations.RADIO_TIMEOUT_SECONDS", 0.01),
        ):
            with self.assertRaisesRegex(RecommendationError, "タイムアウト"):
                await fetch_radio_tracks(SEED_ID)


if __name__ == "__main__":
    unittest.main()
