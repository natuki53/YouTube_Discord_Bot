import array
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from bot.youtube.seek_proxy import SeekableYouTubeInput


class SeekProxyTests(unittest.TestCase):
    def start_proxy(self, data):
        self.opened = []
        owner = self

        class MemoryStream:
            def __init__(self, url, headers, size, chunk, *, start=0, end=None):
                owner.opened.append((start, end))
                self.position, self.end = start, len(data) if end is None else end + 1

            def read(self, size):
                result = data[self.position : min(self.position + size, self.end)]
                self.position += len(result)
                return result

            def close(self):
                pass

            def cancel(self):
                self.position = self.end

        self.enterContext(
            patch("bot.youtube.seek_proxy.YouTubeHTTPStream", MemoryStream)
        )
        proxy = SeekableYouTubeInput(
            "https://media.example.test/audio", {}, len(data), 512
        )
        self.addCleanup(proxy.close)
        return proxy

    def test_serves_requested_offset_without_reading_the_prefix(self):
        data = bytes(range(256)) * 4
        proxy = self.start_proxy(data)
        response = requests.get(
            proxy.url, headers={"Range": "bytes=700-799"}, timeout=3
        )
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.headers["Content-Range"], "bytes 700-799/1024")
        self.assertEqual(response.content, data[700:800])
        self.assertEqual(self.opened, [(700, 799)])

    def test_head_suffix_ranges_and_invalid_or_unknown_path(self):
        data = bytes(range(256))
        proxy = self.start_proxy(data)
        self.assertEqual(
            requests.head(proxy.url, timeout=3).headers["Content-Length"], "256"
        )
        self.assertFalse(self.opened)
        response = requests.get(proxy.url, headers={"Range": "bytes=-10"}, timeout=3)
        self.assertEqual(response.content, data[-10:])
        response = requests.get(proxy.url, headers={"Range": "bytes=900-"}, timeout=3)
        self.assertEqual(response.status_code, 416)
        self.assertEqual(requests.get(proxy.url + "/wrong", timeout=3).status_code, 404)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg required")
    def test_ffmpeg_seeks_to_second_tone_in_mp4_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "two-tones.m4a"
            subprocess.run(
                [
                    "ffmpeg",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:duration=2",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=880:duration=2",
                    "-filter_complex",
                    "[0:a][1:a]concat=n=2:v=0:a=1",
                    "-c:a",
                    "aac",
                    str(path),
                ],
                check=True,
                timeout=15,
            )
            proxy = self.start_proxy(path.read_bytes())
            audio = subprocess.check_output(
                [
                    "ffmpeg",
                    "-loglevel",
                    "error",
                    "-ss",
                    "3",
                    "-i",
                    proxy.url,
                    "-t",
                    "0.25",
                    "-f",
                    "s16le",
                    "-ac",
                    "1",
                    "-ar",
                    "48000",
                    "pipe:1",
                ],
                timeout=10,
            )
        samples = array.array("h", audio)
        crossings = sum(a < 0 <= b for a, b in zip(samples, samples[1:]))
        frequency = crossings / (len(samples) / 48000)
        self.assertAlmostEqual(frequency, 880, delta=40)
