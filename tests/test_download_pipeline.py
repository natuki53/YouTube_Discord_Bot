import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bot.youtube.download_service import DownloadService
from bot.youtube.file_downloader import (
    DownloadResult,
    FileDownloader,
    VideoMeta,
    _locks,
)


class _FakeDownloader:
    def __init__(self, tmp_dir):
        self.tmp_dir = Path(tmp_dir)
        self.max_file_size_mb = 25
        self.meta_calls = 0
        self.download_meta = None

    async def get_meta(self, url):
        self.meta_calls += 1
        return VideoMeta(
            video_id="video-id",
            title="Video title",
            duration=120,
            formats=[],
            webpage_url=url,
        )

    async def download_mp3(self, url, meta=None):
        self.download_meta = meta
        return DownloadResult(
            success=False,
            title=meta.title,
            error_code="download_failed",
            error_message="failed",
        )

    async def download_video(self, url, quality, meta=None):
        return DownloadResult(
            success=False,
            title=meta.title,
            error_code="download_failed",
            error_message="failed",
        )


class FileDownloaderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.downloader = FileDownloader(self.temp_dir.name)

    async def asyncTearDown(self):
        self.temp_dir.cleanup()
        _locks.clear()

    def test_short_mp3_uses_the_actual_default_bitrate(self):
        self.assertEqual(self.downloader._mp3_bitrate(300), "192")

    async def test_video_lock_is_removed_after_download(self):
        meta = VideoMeta(
            video_id="video-id",
            title="Video title",
            duration=120,
            formats=[],
            webpage_url="https://www.youtube.com/watch?v=test",
        )
        result = DownloadResult(success=False, error_code="download_failed")

        with patch.object(
            self.downloader,
            "_download_video_sync",
            return_value=result,
        ):
            await self.downloader.download_video(meta.webpage_url, meta=meta)

        self.assertNotIn(meta.video_id, _locks)


class DownloadServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_mp3_metadata_is_only_requested_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = _FakeDownloader(temp_dir)
            service = DownloadService(downloader, asyncio.Semaphore(1))

            await service.run_mp3("https://www.youtube.com/watch?v=test")

        self.assertEqual(downloader.meta_calls, 1)
        self.assertIsNotNone(downloader.download_meta)
        self.assertEqual(downloader.download_meta.video_id, "video-id")

    async def test_pipeline_has_an_overall_timeout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = _FakeDownloader(temp_dir)

            async def slow_meta(url):
                await asyncio.sleep(0.02)
                return VideoMeta(
                    video_id="video-id",
                    title="Video title",
                    duration=120,
                    formats=[],
                    webpage_url=url,
                )

            downloader.get_meta = slow_meta
            service = DownloadService(downloader, asyncio.Semaphore(1))
            service.timeout_seconds = 0.01

            with self.assertRaises(asyncio.TimeoutError):
                await service.run_video(
                    "https://www.youtube.com/watch?v=test",
                    "720p",
                )
            await asyncio.sleep(0.03)
            self.assertFalse(service._background_tasks)


if __name__ == "__main__":
    unittest.main()
