import unittest
from unittest.mock import Mock, patch

from bot.music.paced_audio_source import PacedAudioSource


class PacedAudioSourceTests(unittest.TestCase):
    def test_paces_frame_after_upstream_read_stall(self):
        now = 0.0
        read_count = 0
        sleep_delays = []
        source = Mock()
        source.is_opus.return_value = False

        def read():
            nonlocal now, read_count
            read_count += 1
            if read_count == 2:
                now += 1.0
            return b"pcm"

        def sleep(delay):
            nonlocal now
            sleep_delays.append(delay)
            now += delay

        source.read.side_effect = read

        with (
            patch(
                "bot.music.paced_audio_source.time.perf_counter",
                side_effect=lambda: now,
            ),
            patch(
                "bot.music.paced_audio_source.time.sleep",
                side_effect=sleep,
            ),
        ):
            paced = PacedAudioSource(source)
            self.assertEqual(paced.read(), b"pcm")
            now += 0.02
            self.assertEqual(paced.read(), b"pcm")
            self.assertEqual(paced.read(), b"pcm")

        self.assertEqual(len(sleep_delays), 1)
        self.assertAlmostEqual(sleep_delays[0], 0.02)

    def test_delegates_source_protocol(self):
        source = Mock()
        source.is_opus.return_value = False
        paced = PacedAudioSource(source)

        self.assertFalse(paced.is_opus())
        paced.cleanup()
        paced.cleanup()

        source.cleanup.assert_called_once_with()

    def test_rejects_non_positive_frame_interval(self):
        with self.assertRaisesRegex(ValueError, "frame_interval"):
            PacedAudioSource(Mock(), frame_interval=0)


if __name__ == "__main__":
    unittest.main()
