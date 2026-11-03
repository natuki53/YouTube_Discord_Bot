"""Pace encrypted RTP at the final socket write, including after a send stall."""

import struct
import threading
import time

import discord


class RTPPacketPacer:
    def __init__(self, interval=0.02):
        self.interval = interval
        self._deadline = None
        self._last_sent = None
        self._lock = threading.Lock()
        self._audio_lock = threading.Lock()
        self._clock_origin = None
        self.packets = 0
        self.errors = 0
        self.min_gap_ms = None
        self.max_gap_ms = 0.0
        self.timestamp_corrections = 0
        self.skipped_frames = 0

    def align_timestamp(self, voice):
        """Advance the sampling clock across pauses/stalls before encryption.

        discord.py increments by 960 only when sending a packet. Keeping that
        counter unchanged during a gap makes the receiver see sender clock drift.
        Never edit the encrypted header: it is authenticated by the transport.
        """
        with self._lock:
            origin = self._clock_origin
            if origin is None or origin[2] != voice.ssrc:
                return
            elapsed = max(0, time.perf_counter() - origin[0])
            expected = (origin[1] + int(elapsed * 48000)) & 0xFFFFFFFF
            missing = (expected - voice.timestamp) & 0xFFFFFFFF
            # Ignore normal frame/scheduler jitter and unsigned wrap-ahead.
            if 1920 <= missing < 0x80000000:
                frames = missing // 960
                voice.timestamp = (voice.timestamp + frames * 960) & 0xFFFFFFFF
                self.timestamp_corrections += 1
                self.skipped_frames += frames

    def send(self, sender, packet):
        with self._lock:
            now = time.perf_counter()
            deadline = self._deadline if self._deadline is not None else now
            if deadline > now:
                time.sleep(deadline - now)
            try:
                sender(packet)
            except OSError:
                self.errors += 1
                self._deadline = time.perf_counter() + self.interval
                raise
            sent = time.perf_counter()
            if len(packet) >= 12 and packet[:2] == b"\x80\x78":
                timestamp, ssrc = struct.unpack_from("!II", packet, 4)
                if self._clock_origin is None or self._clock_origin[2] != ssrc:
                    self._clock_origin = (sent, timestamp, ssrc)
            if self._last_sent is not None:
                gap = (sent - self._last_sent) * 1000
                self.min_gap_ms = (
                    gap if self.min_gap_ms is None else min(self.min_gap_ms, gap)
                )
                self.max_gap_ms = max(self.max_gap_ms, gap)
            self.packets += 1
            self._last_sent = sent
            # Correct small sleep overshoot without accumulating clock drift.
            # Allow up to 1 ms of correction per frame for scheduler overshoot.
            # A late encode/write rebases the clock instead of catching up in a burst.
            self._deadline = max(deadline + self.interval, sent + self.interval * 0.95)


def install_packet_pacer(voice):
    if not isinstance(voice, discord.VoiceClient):
        return None
    connection = voice._connection
    existing = getattr(connection, "_music_packet_pacer", None)
    if isinstance(existing, RTPPacketPacer):
        return existing
    original_send = connection.send_packet
    original_audio_send = voice.send_audio_packet
    pacer = RTPPacketPacer()

    def send_packet(packet):
        if packet[:2] == b"\x80\x78":
            pacer.send(original_send, packet)
        else:
            original_send(packet)

    def send_audio_packet(data, *, encode=True):
        with pacer._audio_lock:
            pacer.align_timestamp(voice)
            original_audio_send(data, encode=encode)

    # discord.py is pinned to 2.7.1. Keep its encoder, DAVE encryption, RTP
    # sequence counters and transport intact. Adjust sampling time before its
    # header is encrypted, then pace the final synchronous UDP write.
    voice.send_audio_packet = send_audio_packet
    connection.send_packet = send_packet
    connection._music_packet_pacer = pacer
    return pacer
