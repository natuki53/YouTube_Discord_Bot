"""Live, frame-preserving binaural rendering of a single virtual speaker.

HRIR data: Bill Gardner and Keith Martin, MIT Media Lab (1994), KEMAR
normal pinna, distributed with libmysofa. See docs/spatial-audio.md.
"""

import atexit
import ctypes as ct
import ctypes.util
import math
import threading
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from pathlib import Path

import discord
import numpy as np

SAMPLE_RATE = 48000
MAX_TAPS = 1024
SOFA_FILE = Path("/usr/share/libmysofa/default.sofa")
AUTO_PERIOD_SECONDS = 20.0


def compensate_coloration(kernel):
    """Reduce shared mannequin/ear-canal coloration, retaining binaural cues.

    A common minimum-phase EQ preserves the L/R level ratio and time difference.
    Smooth on a log-frequency grid so narrow directional pinna notches survive.
    This runs in the control worker, never in the real-time audio thread.
    """
    size = 4096
    response = np.fft.rfft(kernel, n=size, axis=1)
    common = np.sqrt(np.mean(np.abs(response) ** 2, axis=0))
    frequencies = np.fft.rfftfreq(size, 1 / SAMPLE_RATE)
    grid = np.geomspace(40, 20000, 256)
    envelope = np.interp(grid, frequencies, np.log(np.maximum(common, 0.001)))
    envelope = np.convolve(
        np.pad(envelope, 3, mode="edge"), np.ones(7) / 7, mode="valid"
    )
    log_gain = np.clip(
        -0.85 * np.interp(frequencies, grid, envelope), -math.log(4), math.log(4)
    )
    cepstrum = np.fft.irfft(log_gain, n=size)
    minimum = np.zeros(size)
    minimum[0], minimum[size // 2] = cepstrum[0], cepstrum[size // 2]
    minimum[1 : size // 2] = 2 * cepstrum[1 : size // 2]
    equalizer = np.fft.irfft(np.exp(np.fft.rfft(minimum)), n=size)[:257]
    corrected = np.array(
        [np.convolve(channel, equalizer)[:MAX_TAPS] for channel in kernel],
        dtype=np.float32,
    )
    # Avoid boosting peaks into the int16 ceiling before master volume is applied.
    peak = float(np.max(np.abs(np.fft.rfft(corrected, n=size, axis=1))))
    corrected /= max(1, peak)
    return corrected


@dataclass(frozen=True)
class SpatialPosition:
    enabled: bool = False
    x: float = 0.0  # right
    y: float = 1.5  # forward
    z: float = 0.0  # above
    mode: str = "natural"
    auto: bool = False

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict) or type(value.get("enabled")) is not bool:
            raise ValueError("立体音響の設定が不正です。")
        coordinates = []
        for axis, limit in (("x", 4), ("y", 4), ("z", 2)):
            number = value.get(axis)
            if (
                type(number) not in (int, float)
                or not math.isfinite(number)
                or abs(number) > limit
            ):
                raise ValueError("スピーカー位置が範囲外です。")
            coordinates.append(round(float(number), 3))
        mode = value.get("mode", "natural")
        if mode not in ("natural", "binaural"):
            raise ValueError("立体音響のモードが不正です。")
        automatic = value.get("auto", False)
        if type(automatic) is not bool:
            raise ValueError("オートの設定が不正です。")
        return cls(value["enabled"], *coordinates, mode, automatic and value["enabled"])


def automatic_position(origin, elapsed):
    """A constant-radius orbit, easing into it from the last manual position."""
    elapsed = max(0.0, elapsed)
    phase = math.atan2(origin.x, origin.y)
    angle = phase + elapsed * 2 * math.pi / AUTO_PERIOD_SECONDS
    u = min(1.0, elapsed / 1.5)
    blend = u * u * (3 - 2 * u)
    destination = (
        1.5 * math.sin(angle),
        1.5 * math.cos(angle),
        0.35 * math.sin(angle / 2),
    )
    xyz = [
        start + (end - start) * blend
        for start, end in zip((origin.x, origin.y, origin.z), destination)
    ]
    return replace(origin, x=xyz[0], y=xyz[1], z=xyz[2], auto=True)


@lru_cache(maxsize=1)
def spatial_available():
    return SOFA_FILE.is_file() and bool(ctypes.util.find_library("mysofa"))


class SofaHRTF:
    def __init__(self):
        if not spatial_available():
            raise ValueError("この環境では立体音響を利用できません。")
        self.lib = ct.CDLL(ctypes.util.find_library("mysofa"))
        float_pointer = ct.POINTER(ct.c_float)
        self.lib.mysofa_open.argtypes = [
            ct.c_char_p,
            ct.c_float,
            ct.POINTER(ct.c_int),
            ct.POINTER(ct.c_int),
        ]
        self.lib.mysofa_open.restype = ct.c_void_p
        self.lib.mysofa_getfilter_float.argtypes = [
            ct.c_void_p,
            ct.c_float,
            ct.c_float,
            ct.c_float,
            float_pointer,
            float_pointer,
            float_pointer,
            float_pointer,
        ]
        self.lib.mysofa_getfilter_float.restype = None
        self.lib.mysofa_close.argtypes = [ct.c_void_p]
        self.lib.mysofa_close.restype = None
        length, error = ct.c_int(), ct.c_int()
        self.handle = self.lib.mysofa_open(
            bytes(SOFA_FILE), SAMPLE_RATE, ct.byref(length), ct.byref(error)
        )
        self.length = length.value
        if not self.handle or not 0 < self.length <= MAX_TAPS:
            self.close()
            raise ValueError("立体音響データを読み込めませんでした。")
        self.lock = threading.Lock()
        atexit.register(self.close)

    def close(self):
        if self.handle:
            self.lib.mysofa_close(self.handle)
            self.handle = None

    def filters(self, position):
        distance = math.sqrt(position.x**2 + position.y**2 + position.z**2)
        scale = max(distance, 0.001)
        # SOFA uses +X forward, +Y left, +Z up, at the measurement radius.
        xyz = (position.y / scale, -position.x / scale, position.z / scale)
        if distance < 0.001:
            xyz = (1.0, 0.0, 0.0)
        left, right = (ct.c_float * self.length)(), (ct.c_float * self.length)()
        dl, dr = ct.c_float(), ct.c_float()
        with self.lock:
            self.lib.mysofa_getfilter_float(
                self.handle, *xyz, left, right, ct.byref(dl), ct.byref(dr)
            )
        result = np.zeros((2, MAX_TAPS), dtype=np.float32)
        # Leave headroom and never amplify near-field positions. Directional
        # frequency response and interaural delays come from the measured HRIR.
        gain = 0.8 / max(1.0, distance) ** 0.7
        for channel, (impulse, delay) in enumerate(
            ((left, dl.value), (right, dr.value))
        ):
            offset = round(delay * SAMPLE_RATE)
            if not 0 <= offset <= MAX_TAPS - self.length:
                raise ValueError("立体音響データの遅延が範囲外です。")
            result[channel, offset : offset + self.length] = np.ctypeslib.as_array(
                impulse
            )
        result = compensate_coloration(result) * gain
        result.flags.writeable = False
        return result


@lru_cache(maxsize=1)
def hrtf():
    return SofaHRTF()


@dataclass(frozen=True)
class SpatialTarget:
    position: SpatialPosition
    kernel: object = None


def prepare_target(position):
    if not position.enabled:
        return SpatialTarget(position)
    if position.mode == "binaural":
        impulse = hrtf().filters(position)
        kernel = np.repeat(impulse[:, None, :], 2, axis=1) * 0.5
    else:
        # Transparent stereo: no mono downmix or frequency shaping. Only balance,
        # interaural delay and distance attenuation. Front/1.5 m is unity stereo.
        distance = math.sqrt(position.x**2 + position.y**2 + position.z**2)
        pan = position.x / max(distance, 0.001)
        gain = 1 / max(1, distance / 1.5) ** 0.7
        delay = round(abs(pan) * 0.0006 * SAMPLE_RATE)
        far_gain = 1 - 0.65 * abs(pan)
        kernel = np.zeros((2, 2, MAX_TAPS), dtype=np.float32)
        kernel[0, 0, delay if pan > 0 else 0] = gain * (far_gain if pan > 0 else 1)
        kernel[1, 1, delay if pan < 0 else 0] = gain * (far_gain if pan < 0 else 1)
    kernel.flags.writeable = False
    return SpatialTarget(position, kernel)


def spatial_state(target):
    return {
        **asdict(target.position),
        "available": True,
        "binaural_available": spatial_available(),
    }


class SpatialAudioSource(discord.AudioSource):
    """Only the Discord audio thread owns convolution history and fade state.

    Control requests atomically replace an immutable prepared target. No file,
    HTTP, SOFA lookup, or FFmpeg restart happens in read().
    """

    def __init__(self, source, target):
        self.source = source
        self.target = target
        self._seen_target = target
        self._kernel = target.kernel
        self._wet = 1.0 if target.position.enabled else 0.0
        self._remaining = 0
        self._history = np.zeros((MAX_TAPS - 1, 2), dtype=np.float32)

    def read(self):
        if self.source is None:
            return b""
        data = self.source.read()
        if not data:
            return data
        target = self.target
        if target is not self._seen_target:
            self._seen_target = target
            self._remaining = 5  # Smooth changes over 100 ms, keeping frame length.
        if not target.position.enabled and self._wet == 0:
            self._history.fill(0)
            return data  # Disabled output is byte-for-byte original stereo.

        stereo = np.frombuffer(data, dtype="<i2").reshape(-1, 2).astype(np.float32)
        signal = np.concatenate((self._history, stereo), axis=0)
        self._history = signal[-(MAX_TAPS - 1) :].copy()
        desired = target.kernel if target.kernel is not None else self._kernel
        if self._kernel is None:
            self._kernel = desired
        next_kernel = desired
        next_wet = float(target.position.enabled)
        if self._remaining:
            next_kernel = self._kernel + (desired - self._kernel) / self._remaining
            next_wet = self._wet + (next_wet - self._wet) / self._remaining

        def render(kernel, wet):
            if not wet:
                return stereo
            filtered = np.zeros_like(stereo)
            for ear in (0, 1):
                for channel in (0, 1):
                    if np.any(kernel[ear, channel]):
                        filtered[:, ear] += np.convolve(
                            signal[:, channel], kernel[ear, channel], mode="valid"
                        )
            return stereo * (1 - wet) + filtered * wet

        output = render(next_kernel, next_wet)
        if self._remaining:
            previous = render(self._kernel, self._wet)
            ramp = np.linspace(0, 1, len(stereo), dtype=np.float32)[:, None]
            output = previous * (1 - ramp) + output * ramp
            self._remaining -= 1
        self._kernel, self._wet = next_kernel, next_wet
        return np.clip(np.rint(output), -32768, 32767).astype("<i2").tobytes()

    def is_opus(self):
        return False

    def cleanup(self):
        source, self.source = self.source, None
        cleanup = getattr(source, "cleanup", None)
        if cleanup is not None:
            cleanup()
