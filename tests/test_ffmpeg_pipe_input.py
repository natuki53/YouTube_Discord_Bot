import io
import shutil
import subprocess
import threading
import unittest
import wave
from unittest.mock import Mock

import discord

from bot.youtube.http_stream import FFmpegPipeInput


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required")
class FFmpegPipeInputIntegrationTests(unittest.TestCase):
    def test_read_failure_closes_ffmpeg_stdin_and_reaches_audio_eof(self):
        wav = io.BytesIO()
        with wave.open(wav, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(b"\x00\x00" * 3200)

        failure = OSError("simulated upstream failure")
        source = Mock()
        source.read.side_effect = [wav.getvalue(), failure]
        reader = FFmpegPipeInput(source)
        audio = discord.FFmpegPCMAudio(
            reader, pipe=True, options="-vn", stderr=subprocess.DEVNULL
        )
        done = threading.Event()
        frames = []

        def consume():
            while data := audio.read():
                frames.append(data)
            done.set()

        consumer = threading.Thread(target=consume, daemon=True)
        consumer.start()
        try:
            self.assertTrue(done.wait(5), "FFmpeg remained blocked after the input failure")
            self.assertIs(reader.error, failure)
            self.assertGreater(len(frames), 0)
        finally:
            audio.cleanup()
            consumer.join(timeout=1)


if __name__ == "__main__":
    unittest.main()
