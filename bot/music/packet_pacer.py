"""Pace encrypted RTP at the final socket write, including after a send stall."""

import threading
import time

import discord


class RTPPacketPacer:
    def __init__(self, interval=0.02):
        self.interval = interval
        self._deadline = None
        self._last_sent = None
        self._lock = threading.Lock()
        self.packets = 0
        self.errors = 0
        self.min_gap_ms = None
        self.max_gap_ms = 0.0

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
            if self._last_sent is not None:
                gap = (sent - self._last_sent) * 1000
                self.min_gap_ms = (
                    gap if self.min_gap_ms is None else min(self.min_gap_ms, gap)
                )
                self.max_gap_ms = max(self.max_gap_ms, gap)
            self.packets += 1
            self._last_sent = sent
            # Correct small sleep overshoot without accumulating clock drift.
            # A late encode/write rebases the clock instead of catching up in a burst.
            self._deadline = max(deadline + self.interval, sent + self.interval * 0.99)


def install_packet_pacer(voice):
    if not isinstance(voice, discord.VoiceClient):
        return None
    connection = voice._connection
    existing = getattr(connection, "_music_packet_pacer", None)
    if isinstance(existing, RTPPacketPacer):
        return existing
    original_send = connection.send_packet
    pacer = RTPPacketPacer()

    def send_packet(packet):
        if packet[:2] == b"\x80\x78":
            pacer.send(original_send, packet)
        else:
            original_send(packet)

    # discord.py is pinned to 2.7.1. Keep its encoder, DAVE encryption, RTP
    # counters and transport intact; only wrap its final synchronous UDP write.
    connection.send_packet = send_packet
    connection._music_packet_pacer = pacer
    return pacer
