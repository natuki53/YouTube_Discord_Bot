import asyncio
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

from bot.youtube.file_downloader import FileDownloader
from bot.youtube.workers import LookupBusyError, LookupWorkers


class LookupWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_runs_in_another_process_and_can_serialize_download_settings(self):
        workers = LookupWorkers(workers=1)
        try:
            self.assertNotEqual(await workers.run(os.getpid), os.getpid())
            with tempfile.TemporaryDirectory() as directory:
                downloader = FileDownloader(directory)
                self.assertEqual(
                    await workers.run(downloader._height_for_quality, "720p"), 720
                )
        finally:
            workers.close()

    async def test_cancellation_does_not_release_capacity_until_running_work_finishes(
        self,
    ):
        workers = LookupWorkers(workers=1, capacity=1)
        workers._pool = ThreadPoolExecutor(max_workers=1)
        started, release = threading.Event(), threading.Event()

        def block():
            started.set()
            release.wait(2)

        task = asyncio.create_task(workers.run(block))
        try:
            await asyncio.to_thread(started.wait, 1)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            with self.assertRaises(LookupBusyError):
                await workers.run(os.getpid)
            release.set()
            for _ in range(100):
                if not workers._pending:
                    break
                await asyncio.sleep(0.01)
            self.assertEqual(await workers.run(os.getpid), os.getpid())
        finally:
            release.set()
            workers.close()
