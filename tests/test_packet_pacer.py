import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import discord
from discord.voice_state import VoiceConnectionState

from bot.music.packet_pacer import RTPPacketPacer, install_packet_pacer
from bot.music.paced_audio_source import PacedAudioSource


class PacketPacerTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.sent = []
        self.enterContext(
            patch(
                "bot.music.packet_pacer.time.perf_counter", side_effect=lambda: self.now
            )
        )
        self.enterContext(
            patch("bot.music.packet_pacer.time.sleep", side_effect=self.sleep)
        )

    def sleep(self, seconds):
        self.now += seconds

    def send(self, packet):
        self.sent.append(self.now)

    def test_encoder_delay_does_not_allow_following_packet_to_catch_up(self):
        pacer = RTPPacketPacer()
        self.now = 0.15  # A late encoder has only just produced the first packet.
        pacer.send(self.send, b"first")
        self.now += 0.001
        pacer.send(self.send, b"second")
        pacer.send(self.send, b"third")
        self.assertAlmostEqual(self.sent[1] - self.sent[0], 0.02)
        self.assertAlmostEqual(self.sent[2] - self.sent[1], 0.02)

    def test_socket_stall_rebases_next_packet_instead_of_bursting(self):
        pacer = RTPPacketPacer()

        def blocked_send(packet):
            self.now += 0.25
            self.send(packet)

        pacer.send(blocked_send, b"first")
        pacer.send(self.send, b"second")
        self.assertAlmostEqual(self.sent[1] - self.sent[0], 0.0198)

    def test_small_sleep_overshoot_does_not_slow_down_the_entire_track(self):
        pacer = RTPPacketPacer()

        def oversleep(seconds):
            self.now += seconds + 0.0001

        with patch("bot.music.packet_pacer.time.sleep", side_effect=oversleep):
            for _ in range(100):
                pacer.send(self.send, b"audio")
        self.assertAlmostEqual(self.sent[-1], 99 * 0.02 + 0.0001)

    def test_wraps_pinned_discord_transport_once_and_preserves_other_packets(self):
        connection = VoiceConnectionState.__new__(VoiceConnectionState)
        connection.socket = SimpleNamespace(sendall=Mock(side_effect=self.send))
        voice = discord.VoiceClient.__new__(discord.VoiceClient)
        voice._connection = connection
        pacer = install_packet_pacer(voice)
        self.assertIs(install_packet_pacer(voice), pacer)
        connection.send_packet(b"\x80\x78voice")
        connection.send_packet(b"\x80\x78voice")
        self.assertAlmostEqual(self.sent[1] - self.sent[0], 0.02)
        connection.send_packet(b"discovery")
        self.assertEqual(pacer.packets, 2)
        self.assertEqual(connection.socket.sendall.call_count, 3)

    def test_read_monitor_does_not_add_a_second_pacing_clock(self):
        source = Mock()
        source.read.return_value = b"pcm"
        monitor = PacedAudioSource(source, pace_reads=False)
        monitor.read()
        self.now += 0.001
        monitor.read()
        self.assertEqual(monitor.frames_read, 2)
        self.assertAlmostEqual(self.now, 0.001)
