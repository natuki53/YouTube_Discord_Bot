"""Keep yt-dlp's CPU work and plugin globals out of Discord's audio process."""

import asyncio
import atexit
import multiprocessing
import os
import threading
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool


class LookupBusyError(RuntimeError):
    pass


def _initialize_worker():
    # Child processes never connect to Discord. Give its audio sender priority.
    if hasattr(os, "nice"):
        os.nice(5)


class LookupWorkers:
    def __init__(self, *, workers=2, capacity=8):
        self.workers = workers
        self.capacity = capacity
        self._pool = None
        self._pending = set()
        self._lock = threading.Lock()

    async def run(self, function, *args):
        with self._lock:
            if len(self._pending) >= self.capacity:
                raise LookupBusyError(
                    "曲の検索・準備が混み合っています。少し待ってください。"
                )
            if self._pool is None:
                self._pool = ProcessPoolExecutor(
                    max_workers=self.workers,
                    mp_context=multiprocessing.get_context("spawn"),
                    initializer=_initialize_worker,
                )
            try:
                future = self._pool.submit(function, *args)
            except BrokenProcessPool:
                self._pool.shutdown(wait=False, cancel_futures=True)
                self._pool = None
                raise
            self._pending.add(future)

        # Register outside the lock: a completed future may call back immediately.
        def done(completed):
            with self._lock:
                self._pending.discard(completed)

        future.add_done_callback(done)
        return await asyncio.wrap_future(future)

    def close(self):
        with self._lock:
            pool, self._pool = self._pool, None
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)


# A playlist/metadata lookup must not wait behind the entire prefetch queue.
search_workers = LookupWorkers(capacity=4)
stream_workers = LookupWorkers(workers=3, capacity=12)
download_workers = LookupWorkers(capacity=4)


def close_workers():
    search_workers.close()
    stream_workers.close()
    download_workers.close()


atexit.register(close_workers)
