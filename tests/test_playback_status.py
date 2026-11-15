import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from bot.music.guild_player import GuildPlayer
from bot.music.models import Track
from bot.music.paced_audio_source import PacedAudioSource


class PlaybackStatusTests(unittest.TestCase):
    def test_does_not_claim_playing_before_pcm_frames_arrive(self):
        player = GuildPlayer(1, Mock())
        player._current = Track("url", "title", "requester")
        self.assertEqual(player.get_playback_status(), "preparing")
        source = Mock()
        source.read.return_value = b"\x01\x00" * 1920
        player._audio_monitor = PacedAudioSource(source)
        player._current_source = Mock()
        self.assertEqual(player.get_playback_status(), "buffering")
        player._audio_monitor.read()
        self.assertEqual(player.get_playback_status(), "playing")
        self.assertEqual(
            player.get_playback_status(SimpleNamespace(is_paused=lambda: True)),
            "paused",
        )
        player._audio_monitor.last_frame_at = time.monotonic() - 6
        self.assertEqual(player.get_playback_status(), "buffering")

    def test_keeps_last_error_visible_after_queue_exhaustion(self):
        player = GuildPlayer(1, Mock())
        self.assertEqual(player.get_playback_status(), "idle")
        player._last_error = "取得できませんでした"
        self.assertEqual(player.get_playback_status(), "error")
