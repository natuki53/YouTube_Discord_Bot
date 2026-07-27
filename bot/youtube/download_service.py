"""ダウンロードコマンド用の共通パイプライン"""

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Optional

import discord

from ..utils.download_cleanup import cleanup_artifacts
from .file_downloader import DownloadResult, FileDownloader

logger = logging.getLogger(__name__)


@dataclass
class ServiceResponse:
    embed: discord.Embed
    file_path: Optional[str] = None
    send_file: bool = False
    video_id: str = ""


class DownloadService:
    """見積もり → DL → 添付準備 → 掃除"""

    def __init__(
        self,
        downloader: FileDownloader,
        semaphore: asyncio.Semaphore,
        timeout_seconds: int = 600,
    ):
        self.downloader = downloader
        self.semaphore = semaphore
        self.timeout_seconds = max(1, int(timeout_seconds))
        self._background_tasks: set[asyncio.Task] = set()

    async def run_video(
        self,
        url: str,
        quality: str,
        video_title: str = "YouTube動画",
    ) -> ServiceResponse:
        async def _run() -> ServiceResponse:
            async with self.semaphore:
                meta = await self.downloader.get_meta(url)
                if meta.title and meta.title != "Unknown":
                    video_title_resolved = meta.title
                else:
                    video_title_resolved = video_title
                result = await self.downloader.download_video(url, quality, meta=meta)
                response = self._build_response(
                    result, video_title_resolved, url, quality
                )
                response.video_id = meta.video_id
                if not response.send_file and meta.video_id:
                    cleanup_artifacts(self.downloader.tmp_dir, meta.video_id)
                return response

        return await self._run_with_timeout(_run(), kind="video")

    async def run_mp3(
        self,
        url: str,
        video_title: str = "YouTube動画",
    ) -> ServiceResponse:
        async def _run() -> ServiceResponse:
            async with self.semaphore:
                meta = await self.downloader.get_meta(url)
                if meta.title and meta.title != "Unknown":
                    video_title_resolved = meta.title
                else:
                    video_title_resolved = video_title
                result = await self.downloader.download_mp3(url, meta=meta)
                response = self._build_response(
                    result, video_title_resolved, url, "MP3"
                )
                response.video_id = meta.video_id
                if not response.send_file and meta.video_id:
                    cleanup_artifacts(self.downloader.tmp_dir, meta.video_id)
                return response

        return await self._run_with_timeout(_run(), kind="mp3")

    async def _run_with_timeout(
        self,
        operation,
        *,
        kind: str,
    ) -> ServiceResponse:
        task = asyncio.create_task(operation)
        try:
            return await asyncio.wait_for(
                asyncio.shield(task),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "%s download timed out after %ss; cleanup will continue in background",
                kind,
                self.timeout_seconds,
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._finish_timed_out_task)
            raise

    def _finish_timed_out_task(self, task: asyncio.Task) -> None:
        self._background_tasks.discard(task)
        try:
            response = task.result()
        except asyncio.CancelledError:
            return
        except Exception as error:
            logger.error(
                "Timed-out download failed during background cleanup",
                exc_info=(type(error), error, error.__traceback__),
            )
            return

        self.cleanup(response.video_id)

    def cleanup(self, video_id: str) -> None:
        if video_id:
            cleanup_artifacts(self.downloader.tmp_dir, video_id)

    def _build_response(
        self,
        result: DownloadResult,
        title: str,
        url: str,
        quality_label: str,
    ) -> ServiceResponse:
        if result.success and result.file_path:
            embed = discord.Embed(
                title="✅ ダウンロード完了",
                description=(
                    f"**{title}**\n\n"
                    f"📁 **ファイル:** {os.path.basename(result.file_path)}\n"
                    f"📊 **サイズ:** {result.actual_mb:.2f} MB\n"
                    f"🎬 **画質:** {result.quality_used or quality_label}"
                ),
                color=discord.Color.green(),
            )
            embed.add_field(name="📥 URL", value=url, inline=False)
            return ServiceResponse(
                embed=embed, file_path=result.file_path, send_file=True
            )

        if result.error_code == "too_large":
            size = result.actual_mb or result.estimated_mb
            embed = discord.Embed(
                title="⚠️ ファイルサイズが大きすぎます",
                description=(
                    f"**{title}**\n\n"
                    f"📊 **サイズ:** {size:.2f} MB（推定含む）\n"
                    f"📏 **Discord制限:** {self.downloader.max_file_size_mb} MB\n\n"
                    f"{result.error_message or '低い画質を選ぶか、短い動画をお試しください。'}"
                ),
                color=discord.Color.orange(),
            )
            return ServiceResponse(embed=embed)

        embed = discord.Embed(
            title="❌ ダウンロード失敗",
            description=result.error_message or "ダウンロードに失敗しました。",
            color=discord.Color.red(),
        )
        return ServiceResponse(embed=embed)
