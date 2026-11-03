import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from bot.music.guild_player import GuildPlayer
from bot.music.models import Track
from bot.music.nightcore import NightcoreAudioSource, nightcore_available
from bot.music.spatial import SpatialAudioSource, SpatialPosition, prepare_target


class PCMSource:
    def __init__(self, pcm):
        self.pcm, self.position, self.cleaned = pcm, 0, 0

    def read(self):
        data = self.pcm[self.position : self.position + 3840]
        self.position += len(data)
        return data

    def cleanup(self):
        self.cleaned += 1


def stereo_tone(seconds=2):
    t = np.arange(round(seconds * 48000)) / 48000
    return (
        np.column_stack(
            (np.sin(2 * np.pi * 440 * t) * 12000, np.sin(2 * np.pi * 880 * t) * 9000)
        )
        .astype("<i2")
        .tobytes()
    )


class NightcoreTests(unittest.TestCase):
    def test_off_and_live_preserve_original_stereo_without_loading_resampler(self):
        pcm = stereo_tone(0.04)
        for enabled, live in ((False, False), (True, True)):
            raw = PCMSource(pcm)
            source = NightcoreAudioSource(raw, enabled, live=live)
            with patch("bot.music.nightcore.SoxrResampler", side_effect=AssertionError):
                self.assertEqual(source.read() + source.read(), pcm)
                self.assertEqual(source.read(), b"")
            self.assertEqual(source.media_samples, 1920)
            source.cleanup()
            source.cleanup()
            self.assertEqual(raw.cleaned, 1)

    def test_progress_tracks_original_media_and_toggle_never_restarts_voice(self):
        player = GuildPlayer(1, Mock())
        player._current = Track("url", "song", "member")
        player._duration = 180
        player._position_offset = 30
        player._nightcore_source = NightcoreAudioSource(PCMSource(stereo_tone(0.04)))
        player._nightcore_source.media_samples = 48000 * 10
        with patch("bot.music.guild_player.nightcore_available", return_value=True):
            self.assertTrue(player.set_nightcore(True)["enabled"])
            self.assertEqual(player.get_progress()["position"], 40)
            self.assertEqual(player.get_progress()["rate"], 1.25)
            self.assertTrue(player._nightcore_source.enabled)
            player.set_nightcore(False)
            self.assertNotIn("rate", player.get_progress())
            for value in (None, 1, "true", {}, []):
                with self.assertRaises(ValueError):
                    player.set_nightcore(value)

    @unittest.skipUnless(nightcore_available(), "Native libsoxr requires Linux")
    def test_native_speed_pitch_and_stereo_remain_correct_through_spatial_audio(self):
        raw = PCMSource(stereo_tone(2))
        nightcore = NightcoreAudioSource(raw, True)
        source = SpatialAudioSource(nightcore, prepare_target(SpatialPosition(True)))
        blocks = []
        while data := source.read():
            self.assertEqual(len(data), 3840)
            blocks.append(data)
        samples = np.frombuffer(b"".join(blocks), dtype="<i2").reshape(-1, 2)
        self.assertAlmostEqual(len(samples) / 48000, 1.6, delta=0.02)
        self.assertEqual(nightcore.media_samples, 96000)
        for channel, expected in ((0, 550), (1, 1100)):
            segment = samples[4800:-4800, channel]
            spectrum = np.abs(np.fft.rfft(segment * np.hanning(len(segment))))
            frequencies = np.fft.rfftfreq(len(segment), 1 / 48000)
            self.assertAlmostEqual(frequencies[np.argmax(spectrum)], expected, delta=2)
        source.cleanup()
        self.assertEqual(raw.cleaned, 1)

    @unittest.skipUnless(nightcore_available(), "Native libsoxr requires Linux")
    def test_toggling_mid_track_keeps_frames_continuous_and_flushes_the_tail(self):
        raw = PCMSource(stereo_tone(3.007))
        source = NightcoreAudioSource(raw)
        output_frames, previous_position = 0, 0
        while True:
            if output_frames in (10, 45, 85):
                source.enabled = not source.enabled
            data = source.read()
            self.assertGreaterEqual(source.media_samples, previous_position)
            previous_position = source.media_samples
            if not data:
                break
            self.assertEqual(len(data), 3840)
            output_frames += 1
            self.assertLess(output_frames, 180)
        self.assertEqual(raw.position, len(raw.pcm))
        self.assertEqual(source.media_samples, len(raw.pcm) // 4)
        self.assertLess(output_frames * 0.02, 3.007)
        self.assertGreater(output_frames * 0.02, 3.007 / 1.25)
        source.cleanup()
