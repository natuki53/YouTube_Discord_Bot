"""PCM frame pacing that remains stable after an upstream read stall."""

import time

import discord

PCM_FRAME_INTERVAL_SECONDS = 0.02


class PacedAudioSource(discord.AudioSource):
    """Prevent Discord's audio thread from sending delayed frames in a burst."""

    def __init__(
        self,
        source: discord.AudioSource,
        frame_interval: float = PCM_FRAME_INTERVAL_SECONDS,
    ) -> None:
        self._source: discord.AudioSource | None = source
        if frame_interval <= 0:
            raise ValueError("frame_interval must be positive")
        self._frame_interval = frame_interval
        self._last_frame_at: float | None = None

    def read(self) -> bytes:
        source = self._source
        if source is None:
            return b""

        if self._last_frame_at is not None:
            elapsed = time.perf_counter() - self._last_frame_at
            delay = self._frame_interval - elapsed
            if delay > 0:
                time.sleep(delay)

        data = source.read()
        if data:
            # Measure after the possibly blocking upstream read. If it stalled,
            # the next frame is still held to the normal 20 ms cadence.
            self._last_frame_at = time.perf_counter()
        return data

    def is_opus(self) -> bool:
        return bool(self._source and self._source.is_opus())

    def cleanup(self) -> None:
        source = self._source
        self._source = None
        cleanup = getattr(source, "cleanup", None)
        if cleanup is not None:
            cleanup()
