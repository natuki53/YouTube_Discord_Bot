import math
import unittest
from unittest.mock import Mock

import numpy as np

from bot.music.spatial import (
    MAX_TAPS,
    SofaHRTF,
    SpatialAudioSource,
    SpatialPosition,
    SpatialTarget,
    spatial_available,
    prepare_target,
)


class SpatialAudioTests(unittest.TestCase):
    def source(self, target):
        source = Mock()
        self.pcm = (
            np.random.default_rng(42)
            .integers(-5000, 5000, (960, 2), dtype=np.int16)
            .tobytes()
        )
        source.read.return_value = self.pcm
        return SpatialAudioSource(source, target)

    def kernel(self, left=1.0, right=0.2, delay=0):
        result = np.zeros((2, 2, MAX_TAPS), dtype=np.float32)
        result[0, :, 0] = left * 0.5
        result[1, :, delay] = right * 0.5
        return result

    def test_disabled_is_exact_original_stereo_and_cleanup_propagates_once(self):
        source = self.source(SpatialTarget(SpatialPosition()))
        self.assertEqual(source.read(), self.pcm)
        raw = source.source
        source.cleanup()
        source.cleanup()
        self.assertEqual(source.read(), b"")
        raw.cleanup.assert_called_once()

    def test_binaural_filter_preserves_frame_size_and_applies_time_and_level_difference(
        self,
    ):
        source = self.source(
            SpatialTarget(SpatialPosition(True, -1, 0, 0), self.kernel(delay=20))
        )
        impulse = np.zeros((960, 2), dtype=np.int16)
        impulse[100] = 10000
        source.source.read.return_value = impulse.tobytes()
        rendered = source.read()
        self.assertEqual(len(rendered), len(impulse.tobytes()))
        samples = np.frombuffer(rendered, dtype="<i2").reshape(-1, 2)
        self.assertEqual(np.argmax(samples[:, 0]), 100)
        self.assertEqual(np.argmax(samples[:, 1]), 120)
        self.assertEqual(samples[:, 0].max(), 10000)
        self.assertEqual(samples[:, 1].max(), 2000)

    def test_filter_tail_crosses_frame_boundary_without_missing_samples(self):
        kernel = self.kernel(delay=20)
        kernel[0, :, 0], kernel[0, :, 20] = 0, 0.5
        source = self.source(SpatialTarget(SpatialPosition(True), kernel))
        impulse = np.zeros((960, 2), dtype=np.int16)
        impulse[-5] = 10000
        source.source.read.side_effect = [
            impulse.tobytes(),
            np.zeros_like(impulse).tobytes(),
            b"",
        ]
        source.read()
        samples = np.frombuffer(source.read(), dtype="<i2").reshape(-1, 2)
        self.assertEqual(samples[15, 0], 10000)
        self.assertEqual(source.read(), b"")

    def test_live_updates_and_on_off_fade_keep_the_same_stream_and_length(self):
        source = self.source(SpatialTarget(SpatialPosition()))
        raw = source.source
        source.target = SpatialTarget(SpatialPosition(True), self.kernel())
        for _ in range(5):
            self.assertEqual(len(source.read()), len(self.pcm))
        self.assertEqual(source._wet, 1)
        source.target = SpatialTarget(SpatialPosition(False))
        for _ in range(5):
            self.assertEqual(len(source.read()), len(self.pcm))
        self.assertEqual(source._wet, 0)
        self.assertEqual(source.read(), self.pcm)
        self.assertIs(source.source, raw)
        raw.cleanup.assert_not_called()

    def test_position_validation_rejects_nonfinite_out_of_range_and_wrong_types(self):
        baseline = {"enabled": True, "x": 0, "y": 1.5, "z": 0}
        for field, value in (
            ("enabled", 1),
            ("x", True),
            ("x", math.nan),
            ("y", math.inf),
            ("x", 4.1),
            ("z", -2.1),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                SpatialPosition.parse({**baseline, field: value})

    def test_quality_mode_preserves_original_stereo_samples_at_front_default(self):
        source = self.source(prepare_target(SpatialPosition(True)))
        self.assertEqual(source.read(), self.pcm)
        # Anti-phase stereo used to cancel during the mono downmix. Natural mode
        # preserves both channels, including their phase and full-band content.
        samples = np.random.default_rng(7).integers(-30000, 30000, 960, dtype=np.int16)
        antiphase = np.column_stack((samples, -samples)).astype("<i2").tobytes()
        source.source.read.return_value = antiphase
        self.assertEqual(source.read(), antiphase)

    def test_quality_mode_moves_image_without_crossfeeding_or_filtering_channels(self):
        target = prepare_target(SpatialPosition(True, 1.5, 0, 0))
        self.assertTrue(np.all(target.kernel[0, 1] == 0))
        self.assertTrue(np.all(target.kernel[1, 0] == 0))
        self.assertEqual(np.count_nonzero(target.kernel[0, 0]), 1)
        self.assertEqual(np.count_nonzero(target.kernel[1, 1]), 1)
        self.assertGreater(
            np.argmax(target.kernel[0, 0]), np.argmax(target.kernel[1, 1])
        )

    @unittest.skipUnless(
        spatial_available(), "Native SOFA data requires Linux libmysofa"
    )
    def test_native_hrtf_distinguishes_sides_front_back_and_elevation(self):
        hrtf = SofaHRTF()
        try:
            left = hrtf.filters(SpatialPosition(True, -1, 0, 0))
            right = hrtf.filters(SpatialPosition(True, 1, 0, 0))
            self.assertGreater(np.sum(left[0] ** 2), np.sum(left[1] ** 2))
            self.assertGreater(np.sum(right[1] ** 2), np.sum(right[0] ** 2))
            front = hrtf.filters(SpatialPosition(True, 0, 1, 0))
            back = hrtf.filters(SpatialPosition(True, 0, -1, 0))
            above = hrtf.filters(SpatialPosition(True, 0, 1, 1))
            self.assertFalse(np.allclose(front, back))
            self.assertFalse(np.allclose(front, above))
            far = hrtf.filters(SpatialPosition(True, 0, 3, 0))
            self.assertLess(np.sum(far**2), np.sum(front**2) / 2)
            self.assertTrue(np.isfinite(left).all())
            response = np.abs(np.fft.rfft(front[0], n=8192))
            frequencies = np.fft.rfftfreq(8192, 1 / 48000)
            bands = [
                20
                * np.log10(
                    np.sqrt(
                        np.mean(
                            response[
                                (frequencies > hz / 1.2) & (frequencies < hz * 1.2)
                            ]
                            ** 2
                        )
                    )
                )
                for hz in (125, 500, 1000, 2000, 4000, 8000, 12000)
            ]
            self.assertLess(max(bands) - min(bands), 6)
            self.assertLess(response.max(), 0.85)
        finally:
            hrtf.close()
