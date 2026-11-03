"""Stereo, variable-rate Nightcore with a fixed Discord 48 kHz/20 ms clock."""

import ctypes as ct
import ctypes.util
from functools import lru_cache

import discord
import numpy as np

NIGHTCORE_RATE = 1.25
SAMPLE_RATE = 48000
FRAME_SAMPLES = 960
RAMP_SAMPLES = 4800


@lru_cache(maxsize=1)
def soxr_path():
    return ctypes.util.find_library("soxr")


def nightcore_available():
    return bool(soxr_path())


class QualitySpec(ct.Structure):
    # libsoxr's public ABI: https://github.com/chirlu/soxr/blob/master/src/soxr.h
    _fields_ = [
        ("precision", ct.c_double),
        ("phase_response", ct.c_double),
        ("passband_end", ct.c_double),
        ("stopband_begin", ct.c_double),
        ("e", ct.c_void_p),
        ("flags", ct.c_ulong),
    ]


@lru_cache(maxsize=1)
def soxr_library():
    if not nightcore_available():
        raise ValueError("この環境ではNightcoreを利用できません。")
    lib = ct.CDLL(soxr_path())
    lib.soxr_quality_spec.argtypes = [ct.c_ulong, ct.c_ulong]
    lib.soxr_quality_spec.restype = QualitySpec
    lib.soxr_create.argtypes = [
        ct.c_double,
        ct.c_double,
        ct.c_uint,
        ct.POINTER(ct.c_char_p),
        ct.c_void_p,
        ct.POINTER(QualitySpec),
        ct.c_void_p,
    ]
    lib.soxr_create.restype = ct.c_void_p
    lib.soxr_process.argtypes = [
        ct.c_void_p,
        ct.c_void_p,
        ct.c_size_t,
        ct.POINTER(ct.c_size_t),
        ct.c_void_p,
        ct.c_size_t,
        ct.POINTER(ct.c_size_t),
    ]
    lib.soxr_process.restype = ct.c_char_p
    lib.soxr_set_io_ratio.argtypes = [ct.c_void_p, ct.c_double, ct.c_size_t]
    lib.soxr_set_io_ratio.restype = ct.c_char_p
    lib.soxr_delete.argtypes = [ct.c_void_p]
    lib.soxr_delete.restype = None
    return lib


class SoxrResampler:
    def __init__(self, rate):
        self.handle = None
        self.lib = soxr_library()
        # Allocate for the maximum ratio; variable-rate operation also supports 1x.
        quality = self.lib.soxr_quality_spec(4, 32)  # SOXR_HQ | SOXR_VR
        error = ct.c_char_p()
        self.handle = self.lib.soxr_create(
            SAMPLE_RATE * NIGHTCORE_RATE,
            SAMPLE_RATE,
            2,
            ct.byref(error),
            None,
            ct.byref(quality),
            None,
        )
        if error.value or not self.handle:
            self.close()
            raise RuntimeError("Nightcore resampler initialization failed")
        self.set_rate(rate, 0)

    def set_rate(self, rate, slew=RAMP_SAMPLES):
        error = self.lib.soxr_set_io_ratio(self.handle, rate, slew)
        if error:
            raise RuntimeError("Nightcore resampler ratio failed")

    def process(self, samples, capacity):
        output = np.empty((capacity, 2), dtype=np.float32)
        used, produced = ct.c_size_t(), ct.c_size_t()
        error = self.lib.soxr_process(
            self.handle,
            None if samples is None else samples.ctypes.data,
            0 if samples is None else len(samples),
            ct.byref(used),
            output.ctypes.data,
            capacity,
            ct.byref(produced),
        )
        if error:
            raise RuntimeError("Nightcore audio conversion failed")
        return used.value, output[: produced.value]

    def close(self):
        if self.handle:
            self.lib.soxr_delete(self.handle)
            self.handle = None


class NightcoreAudioSource(discord.AudioSource):
    """Only read() owns the resampler/FIFO; controls atomically set enabled.

    Normal playback bypasses conversion until Nightcore has first been used.
    Each returned block is still exactly 960 stereo samples, irrespective of
    how many source samples were consumed. Position is in original-song samples.
    """

    def __init__(self, source, enabled=False, *, live=False):
        self.source = source
        self.enabled = enabled
        self.live = live
        self.media_samples = 0.0
        self._read_samples = 0
        self._resampler = None
        self._input = np.empty((0, 2), dtype=np.float32)
        self._eof = False
        self._drained = False
        self._rate = 1.0
        self._target_rate = 1.0
        self._remaining = 0

    @property
    def rate(self):
        return NIGHTCORE_RATE if self.enabled and not self.live else 1.0

    def read(self):
        if self.source is None or self._drained:
            return b""
        desired = self.rate
        if self._resampler is None and desired == 1:
            data = self.source.read()
            self.media_samples += len(data) / 4
            self._read_samples += len(data) // 4
            return data
        if self._resampler is None:
            self._resampler = SoxrResampler(desired)
            self._rate = self._target_rate = desired
        if desired != self._target_rate:
            self._resampler.set_rate(desired)
            self._target_rate = desired
            self._remaining = RAMP_SAMPLES

        blocks, count = [], 0
        while count < FRAME_SAMPLES:
            if not len(self._input) and not self._eof:
                raw = self.source.read()
                if raw:
                    self._input = (
                        np.frombuffer(raw, dtype="<i2")
                        .reshape(-1, 2)
                        .astype(np.float32)
                    )
                    self._read_samples += len(self._input)
                else:
                    self._eof = True
            used, output = self._resampler.process(
                None if self._eof and not len(self._input) else self._input,
                FRAME_SAMPLES - count,
            )
            self._input = self._input[used:]
            if len(output):
                blocks.append(output)
                count += len(output)
            elif not used:
                if not self._eof:
                    raise RuntimeError("Nightcore converter made no progress")
                self._drained = True
                break

        if count:
            next_rate = desired
            if self._remaining:
                step = min(count, self._remaining)
                next_rate = self._rate + (desired - self._rate) * step / self._remaining
                self._remaining -= step
            self.media_samples += count * (self._rate + next_rate) / 2
            self._rate = next_rate
            if self._drained:
                self.media_samples = self._read_samples
            output = np.concatenate(blocks, axis=0)
            if count < FRAME_SAMPLES:
                output = np.pad(output, ((0, FRAME_SAMPLES - count), (0, 0)))
            return np.clip(np.rint(output), -32768, 32767).astype("<i2").tobytes()
        self.media_samples = self._read_samples
        return b""

    def is_opus(self):
        return False

    def cleanup(self):
        source, self.source = self.source, None
        if self._resampler is not None:
            self._resampler.close()
            self._resampler = None
        cleanup = getattr(source, "cleanup", None)
        if cleanup is not None:
            cleanup()
