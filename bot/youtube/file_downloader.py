"""ファイルダウンロード専用（VC 再生とは分離）"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yt_dlp

from ..utils.download_cleanup import ensure_tmp_dir
from .url_handler import normalize_youtube_url

logger = logging.getLogger(__name__)

QUALITY_HEIGHTS = {
    "144p": 144,
    "240p": 240,
    "360p": 360,
    "480p": 480,
    "720p": 720,
    "1080p": 1080,
}

QUALITY_FALLBACK_ORDER = ["1080p", "720p", "480p", "360p", "240p", "144p"]

_locks: Dict[str, asyncio.Lock] = {}


def _get_lock(video_id: str) -> asyncio.Lock:
    if video_id not in _locks:
        _locks[video_id] = asyncio.Lock()
    return _locks[video_id]


@dataclass
class VideoMeta:
    video_id: str
    title: str
    duration: Optional[int]
    formats: list
    webpage_url: str


@dataclass
class DownloadResult:
    success: bool
    file_path: Optional[str] = None
    title: str = ""
    error_code: str = ""
    error_message: str = ""
    estimated_mb: float = 0.0
    actual_mb: float = 0.0
    quality_used: str = ""
    actual_height: int = 0


class FileDownloader:
    """video_id 固定パスで一時ディレクトリにダウンロード"""

    def __init__(
        self,
        tmp_dir: str,
        max_file_size_mb: float = 25,
        mp3_bitrate_default: str = "192",
        mp3_bitrate_long: str = "128",
        long_duration_seconds: int = 600,
        very_long_duration_seconds: int = 1200,
    ):
        self.tmp_dir = ensure_tmp_dir(tmp_dir)
        self.max_file_size_mb = max_file_size_mb
        self.max_bytes = int(max_file_size_mb * 1024 * 1024 * 0.95)
        self.mp3_bitrate_default = mp3_bitrate_default
        self.mp3_bitrate_long = mp3_bitrate_long
        self.long_duration = long_duration_seconds
        self.very_long_duration = very_long_duration_seconds

    def _extract_meta(self, url: str) -> VideoMeta:
        normalized = normalize_youtube_url(url) or url
        opts = {"quiet": True, "no_warnings": True, "noplaylist": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(normalized, download=False)
        return VideoMeta(
            video_id=info.get("id") or "",
            title=info.get("title") or "Unknown",
            duration=info.get("duration"),
            formats=info.get("formats") or [],
            webpage_url=info.get("webpage_url") or normalized,
        )

    async def get_meta(self, url: str) -> VideoMeta:
        return await asyncio.to_thread(self._extract_meta, url)

    def _height_for_quality(self, quality: str) -> int:
        return QUALITY_HEIGHTS.get(quality, 720)

    def _fallback_qualities(self, quality: str) -> List[str]:
        if quality not in QUALITY_FALLBACK_ORDER:
            quality = "720p"
        idx = QUALITY_FALLBACK_ORDER.index(quality)
        return QUALITY_FALLBACK_ORDER[idx:]

    def _format_video_spec(self, height: int) -> str:
        """動画+音声をマージし、高さ上限を厳守する形式指定"""
        max_m = int(self.max_file_size_mb * 0.95)
        return (
            f"bestvideo[height<={height}][filesize<{max_m}M]+bestaudio/"
            f"bestvideo[height<={height}]+bestaudio/"
            f"b[height<={height}][filesize<{max_m}M]/"
            f"b[height<={height}]/"
            f"worstvideo[height<={height}]+worstaudio/"
            f"worst[height<={height}]"
        )

    def _ydl_format_opts(self, height: int) -> dict:
        return {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "format_sort": [f"res:{height}", "size", "ext:mp4:m4a"],
            "format_sort_force": True,
        }

    def _probe_height(self, info: dict) -> int:
        """選択された形式の実効解像度を取得"""
        height = info.get("height") or 0
        for fmt in info.get("requested_formats") or []:
            if fmt.get("vcodec") and fmt.get("vcodec") != "none":
                height = max(height, fmt.get("height") or 0)
        if not height and info.get("formats"):
            fid = info.get("format_id")
            for fmt in info["formats"]:
                if fmt.get("format_id") == fid:
                    height = fmt.get("height") or 0
                    break
        return int(height)

    def _quality_label(
        self, requested: str, used: str, actual_height: int
    ) -> str:
        if actual_height:
            base = f"{used}（{actual_height}p）"
        else:
            base = used
        if used != requested:
            return f"指定 {requested} → {base}"
        return base

    def _select_video_format(
        self, meta: VideoMeta, quality: str
    ) -> Tuple[Optional[str], int, str, int, int]:
        requested = quality if quality in QUALITY_HEIGHTS else "720p"

        for q in self._fallback_qualities(requested):
            height = self._height_for_quality(q)
            spec = self._format_video_spec(height)
            opts = {**self._ydl_format_opts(height), "format": spec}
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(meta.webpage_url, download=False)
                if not info:
                    continue

                actual_h = self._probe_height(info)
                size = info.get("filesize") or info.get("filesize_approx") or 0

                # 指定より大きい解像度は採用しない
                if actual_h and actual_h > height + 16:
                    logger.info(
                        f"Rejected {q}: height {actual_h}p > cap {height}p"
                    )
                    continue

                if size and size > self.max_bytes:
                    logger.info(
                        f"Rejected {q}: size {size / (1024*1024):.1f}MB > limit"
                    )
                    continue

                label = self._quality_label(requested, q, actual_h)
                logger.info(f"Selected format: {label}, spec={spec}")
                return spec, int(size), label, actual_h, height

            except Exception as e:
                logger.debug(f"Format probe failed for {q}: {e}")

        return None, 0, requested, 0, 0

    def _mp3_bitrate(self, duration: Optional[int]) -> str:
        if duration and duration > self.very_long_duration:
            return self.mp3_bitrate_long
        if duration and duration > self.long_duration:
            return self.mp3_bitrate_default
        return "0"

    def _estimate_mp3_size(self, duration: Optional[int], bitrate: str) -> float:
        if not duration:
            return 0
        kbps = int(bitrate) if bitrate != "0" else 320
        return (duration * kbps * 1000 / 8) / (1024 * 1024)

    def _download_video_sync(self, meta: VideoMeta, quality: str) -> DownloadResult:
        format_spec, est_size, q_used, actual_h, height_cap = self._select_video_format(
            meta, quality
        )
        if not format_spec:
            return DownloadResult(
                success=False,
                title=meta.title,
                error_code="too_large",
                error_message="指定画質では25MB以内に収まりません。低い画質をお試しください。",
            )

        if est_size and est_size > self.max_bytes:
            return DownloadResult(
                success=False,
                title=meta.title,
                error_code="too_large",
                error_message="ファイルサイズが大きすぎるため、ダウンロードを開始できません。",
                estimated_mb=est_size / (1024 * 1024),
            )

        out_path = str(self.tmp_dir / f"{meta.video_id}.%(ext)s")
        opts = {
            **self._ydl_format_opts(height_cap),
            "format": format_spec,
            "outtmpl": out_path,
            "merge_output_format": "mp4",
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([meta.webpage_url])
        except Exception as e:
            logger.error(f"Video download failed: {e}")
            return DownloadResult(
                success=False,
                title=meta.title,
                error_code="download_failed",
                error_message=str(e),
            )

        file_path = self._find_output(meta.video_id, (".mp4", ".mkv", ".webm"))
        if not file_path:
            return DownloadResult(
                success=False,
                title=meta.title,
                error_code="not_found",
                error_message="ダウンロードファイルが見つかりません。",
            )

        actual_mb = Path(file_path).stat().st_size / (1024 * 1024)
        if actual_mb > self.max_file_size_mb:
            Path(file_path).unlink(missing_ok=True)
            return DownloadResult(
                success=False,
                title=meta.title,
                error_code="too_large",
                error_message="ダウンロード後のファイルがDiscord制限を超えています。低い画質をお試しください。",
                actual_mb=actual_mb,
                quality_used=q_used,
                actual_height=actual_h,
            )

        return DownloadResult(
            success=True,
            file_path=file_path,
            title=meta.title,
            actual_mb=actual_mb,
            quality_used=q_used,
            actual_height=actual_h,
        )

    def _download_mp3_sync(self, meta: VideoMeta) -> DownloadResult:
        bitrate = self._mp3_bitrate(meta.duration)
        est_mb = self._estimate_mp3_size(meta.duration, bitrate if bitrate != "0" else "320")

        if est_mb > self.max_file_size_mb:
            if bitrate == "0":
                bitrate = self.mp3_bitrate_default
                est_mb = self._estimate_mp3_size(meta.duration, bitrate)
            if est_mb > self.max_file_size_mb:
                bitrate = self.mp3_bitrate_long
                est_mb = self._estimate_mp3_size(meta.duration, bitrate)
            if est_mb > self.max_file_size_mb:
                return DownloadResult(
                    success=False,
                    title=meta.title,
                    error_code="too_large",
                    error_message="動画が長すぎるため、25MB以内のMP3に変換できません。",
                    estimated_mb=est_mb,
                )

        out_path = str(self.tmp_dir / f"{meta.video_id}.%(ext)s")
        opts = {
            "format": "bestaudio/best",
            "outtmpl": out_path,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": bitrate if bitrate != "0" else "192",
                }
            ],
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([meta.webpage_url])
        except Exception as e:
            logger.error(f"MP3 download failed: {e}")
            return DownloadResult(
                success=False,
                title=meta.title,
                error_code="download_failed",
                error_message=str(e),
            )

        file_path = self._find_output(meta.video_id, (".mp3",))
        if not file_path:
            return DownloadResult(
                success=False,
                title=meta.title,
                error_code="not_found",
                error_message="MP3ファイルが見つかりません。",
            )

        actual_mb = Path(file_path).stat().st_size / (1024 * 1024)
        if actual_mb > self.max_file_size_mb:
            Path(file_path).unlink(missing_ok=True)
            return DownloadResult(
                success=False,
                title=meta.title,
                error_code="too_large",
                error_message="MP3がDiscord制限を超えています。",
                actual_mb=actual_mb,
            )

        return DownloadResult(
            success=True,
            file_path=file_path,
            title=meta.title,
            actual_mb=actual_mb,
            quality_used=f"mp3-{bitrate}kbps",
        )

    def _find_output(self, video_id: str, extensions: tuple) -> Optional[str]:
        for ext in extensions:
            path = self.tmp_dir / f"{video_id}{ext}"
            if path.exists():
                return str(path)
        for path in self.tmp_dir.glob(f"{video_id}.*"):
            if path.suffix.lower() in extensions:
                return str(path)
        return None

    async def download_video(
        self,
        url: str,
        quality: str = "720p",
        meta: Optional[VideoMeta] = None,
    ) -> DownloadResult:
        if meta is None:
            meta = await self.get_meta(url)
        async with _get_lock(meta.video_id):
            return await asyncio.to_thread(self._download_video_sync, meta, quality)

    async def download_mp3(self, url: str) -> DownloadResult:
        meta = await self.get_meta(url)
        async with _get_lock(meta.video_id):
            return await asyncio.to_thread(self._download_mp3_sync, meta)
