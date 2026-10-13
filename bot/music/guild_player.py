"""ギルド単位の再生ワーカー（ストリーミング再生）"""

import asyncio
import logging
import os
import shlex
import subprocess
from collections import deque
from typing import TYPE_CHECKING, Dict, Mapping, Optional

import discord

from ..youtube.http_stream import YouTubeHTTPStream
from ..youtube.recommendations import (
    RecommendationError,
    fetch_radio_tracks,
    youtube_video_id,
)
from ..youtube.stream import StreamError, resolve_stream
from .models import Track
from .paced_audio_source import PacedAudioSource
from .queue import MusicQueue

if TYPE_CHECKING:
    from .player_manager import PlayerManager

logger = logging.getLogger(__name__)

IDLE_TIMEOUT_SECONDS = 300
EMPTY_CHANNEL_TIMEOUT_SECONDS = 180
STREAM_RETRY_LIMIT = 3
STREAM_RETRY_BASE_DELAY_SECONDS = 2
PLAYBACK_TIMEOUT_GRACE_SECONDS = 300
UNKNOWN_DURATION_TIMEOUT_SECONDS = 6 * 60 * 60
AUTOPLAY_HISTORY_LIMIT = 50
AUTOPLAY_FAILURE_LIMIT = 3
FFMPEG_BEFORE = (
    "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 10 "
    "-nostdin -loglevel warning"
)
FFMPEG_OPTIONS = "-vn"


def _build_ffmpeg_before_options(
    http_headers: Optional[Mapping[str, str]],
) -> str:
    """yt-dlp が指定した安全な HTTP ヘッダーを FFmpeg に引き継ぐ。"""
    if not http_headers:
        return FFMPEG_BEFORE

    header_lines = []
    for name, value in http_headers.items():
        if not name or any(char in name for char in "\r\n:"):
            continue
        if any(char in value for char in "\r\n"):
            continue
        header_lines.append(f"{name}: {value}\r\n")

    if not header_lines:
        return FFMPEG_BEFORE

    header_block = "".join(header_lines)
    return f"{FFMPEG_BEFORE} -headers {shlex.quote(header_block)}"


def _get_ffmpeg_source_error(source, *, wait_for_exit: bool):
    """音声ラッパーで隠れる FFmpeg の異常終了を取得する。"""
    source_error = getattr(source, "_current_error", None)
    if source_error:
        return source_error

    process = getattr(source, "_process", None)
    if process is None or not hasattr(process, "poll"):
        return None

    returncode = process.poll()
    if returncode is None and wait_for_exit:
        try:
            returncode = process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            return None

    if returncode not in (None, 0):
        return RuntimeError(f"FFmpeg exited with code {returncode}")
    return None


class GuildPlayer:
    """1 ギルドにつき 1 つの再生ワーカー"""

    def __init__(
        self,
        guild_id: int,
        manager: "PlayerManager",
        default_volume_percent: int = 25,
    ):
        self.guild_id = guild_id
        self._manager = manager
        self._queue = MusicQueue()
        self._lock = asyncio.Lock()
        self._loop_task: Optional[asyncio.Task] = None
        self._current: Optional[Track] = None
        self._loop_enabled = False
        self._autoplay_enabled = False
        self._autoplay_generation = 0
        self._autoplay_task: Optional[asyncio.Task] = None
        self._autoplay_seed: Optional[Track] = None
        self._radio_seed_id: Optional[str] = None
        self._radio_tracks = deque()
        self._recent_video_ids = deque(maxlen=AUTOPLAY_HISTORY_LIMIT)
        self._autoplay_failures = 0
        self._text_channel_id: Optional[int] = None
        self._idle_task: Optional[asyncio.Task] = None
        self._empty_channel_task: Optional[asyncio.Task] = None
        self._skip_requested = False
        self._volume_percent = max(1, min(100, default_volume_percent))
        self._volume = self._volume_percent / 100.0
        self._current_source: Optional[discord.PCMVolumeTransformer] = None

    def get_volume_percent(self) -> int:
        return self._volume_percent

    def set_volume_percent(self, percent: int) -> int:
        """音量を 1〜100% で設定。再生中なら即時反映。"""
        self._volume_percent = max(1, min(100, int(percent)))
        self._volume = self._volume_percent / 100.0
        if self._current_source is not None:
            self._current_source.volume = self._volume
        return self._volume_percent

    def set_text_channel(self, channel_id: int) -> None:
        self._text_channel_id = channel_id

    async def enqueue(self, track: Track, voice_client: discord.VoiceClient) -> str:
        """トラックを追加。再生中ならキューへ、そうでなければ再生ループを起動。"""
        async with self._lock:
            self.update_empty_channel_timeout(voice_client)
            if voice_client.is_playing() or voice_client.is_paused() or self._current:
                self._queue.enqueue(track)
                self._cancel_idle_timeout()
                return "queued"
            self._cancel_idle_timeout()
            self._queue.enqueue(track)
            self._cancel_autoplay_lookup()
            self._ensure_play_loop(voice_client)
            return "playing"

    def _ensure_play_loop(self, voice_client: discord.VoiceClient) -> None:
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._play_loop(voice_client))

    async def _play_loop(self, voice_client: discord.VoiceClient) -> None:
        retry_track: Optional[Track] = None
        retry_count = 0

        while True:
            track = retry_track or self._get_next_track()
            retry_track = None
            if track is None:
                recommended = await self._get_autoplay_track(voice_client)
                # 関連曲取得中に追加された手動リクエストを最優先する。
                track = self._get_next_track() or recommended
                if track is None:
                    if voice_client.is_connected():
                        self._start_idle_timeout(voice_client)
                    break

            is_loop_restart = self._loop_enabled and track is self._current
            autoplay_generation = self._autoplay_generation
            self._current = track
            self._skip_requested = False

            try:
                if track.auto_selected and not is_loop_restart:
                    if not self._can_play_autoplay_selection(
                        voice_client, autoplay_generation
                    ):
                        self._current = None
                        retry_count = 0
                        continue
                stream_info = await resolve_stream(track.url)
                if track.auto_selected and not is_loop_restart:
                    if not self._can_play_autoplay_selection(
                        voice_client, autoplay_generation
                    ):
                        self._current = None
                        retry_count = 0
                        continue
                track.video_id = stream_info.video_id
                self._remember_video_id(track.video_id)
                if track.title == track.url or track.title.startswith("YouTube"):
                    track.title = stream_info.title

                if track.auto_selected and not is_loop_restart:
                    if not self._can_play_autoplay_selection(
                        voice_client, autoplay_generation
                    ):
                        self._current = None
                        retry_count = 0
                        continue

                played = await self._play_stream(
                    voice_client,
                    stream_info.url,
                    track,
                    stream_info.duration,
                    http_headers=stream_info.http_headers,
                    filesize=stream_info.filesize,
                    http_chunk_size=stream_info.http_chunk_size,
                )
                if not played and not self._skip_requested:
                    raise StreamError(
                        "YouTubeから音声を取得できませんでした。"
                        "時間をおいて再度お試しください。",
                        "playback_failed",
                    )

            except StreamError as e:
                logger.warning(f"Stream error guild={self.guild_id}: {e}")
                error_message = str(e)
            except Exception as e:
                logger.exception(f"Play loop error guild={self.guild_id}: {e}")
                error_message = "予期しないエラーが発生しました"
            else:
                retry_count = 0
                self._autoplay_seed = track
                self._autoplay_failures = 0
                if not self._loop_enabled:
                    self._current = None
                error_message = None

            if error_message is not None:
                if track.auto_selected and not is_loop_restart:
                    if not self._can_play_autoplay_selection(
                        voice_client, autoplay_generation
                    ):
                        self._current = None
                        retry_count = 0
                        if not voice_client.is_connected():
                            break
                        continue
                retry_count += 1
                if (
                    retry_count < STREAM_RETRY_LIMIT
                    and voice_client.is_connected()
                    and not self._skip_requested
                ):
                    delay = STREAM_RETRY_BASE_DELAY_SECONDS * retry_count
                    logger.info(
                        "Retrying stream guild=%s attempt=%s/%s in %ss",
                        self.guild_id,
                        retry_count + 1,
                        STREAM_RETRY_LIMIT,
                        delay,
                    )
                    retry_track = track
                    await asyncio.sleep(delay)
                    continue

                await self._notify_error(track, error_message)
                self._remember_video_id(track.video_id or youtube_video_id(track.url))
                self._current = None
                retry_count = 0
                if track.auto_selected:
                    self._autoplay_failures += 1
                    if self._autoplay_failures >= AUTOPLAY_FAILURE_LIMIT:
                        self.set_autoplay_enabled(False)
                        await self._notify_autoplay_stopped(
                            "自動選曲した曲を続けて再生できませんでした。"
                        )
                if not voice_client.is_connected():
                    break
                continue

            if not voice_client.is_connected():
                break

        self._loop_task = None

    def _get_next_track(self) -> Optional[Track]:
        if self._loop_enabled and self._current:
            return self._current
        return self._queue.dequeue()

    def is_autoplay_enabled(self) -> bool:
        return self._autoplay_enabled

    def set_autoplay_enabled(self, enabled: bool) -> bool:
        if self._autoplay_enabled != enabled:
            self._autoplay_generation += 1
            self._cancel_autoplay_lookup()
            self._radio_tracks.clear()
            self._radio_seed_id = None
            self._autoplay_failures = 0
        self._autoplay_enabled = enabled
        return enabled

    def _cancel_autoplay_lookup(self) -> None:
        if self._autoplay_task and not self._autoplay_task.done():
            self._autoplay_task.cancel()

    def _remember_video_id(self, video_id: Optional[str]) -> None:
        if not video_id:
            return
        if video_id in self._recent_video_ids:
            self._recent_video_ids.remove(video_id)
        self._recent_video_ids.append(video_id)

    def _can_autoplay(self, voice_client: discord.VoiceClient) -> bool:
        return (
            self._autoplay_enabled
            and self._autoplay_seed is not None
            and voice_client.is_connected()
            and self._has_human_member(voice_client)
        )

    def _can_play_autoplay_selection(
        self, voice_client: discord.VoiceClient, generation: int
    ) -> bool:
        return (
            generation == self._autoplay_generation
            and self._can_autoplay(voice_client)
            and not self._queue
        )

    async def _get_autoplay_track(
        self, voice_client: discord.VoiceClient
    ) -> Optional[Track]:
        if not self._can_autoplay(voice_client):
            return None
        seed_id = self._autoplay_seed.video_id or youtube_video_id(
            self._autoplay_seed.url
        )
        if not seed_id:
            self.set_autoplay_enabled(False)
            await self._notify_autoplay_stopped(
                "前の曲の動画IDを取得できませんでした。"
            )
            return None

        if self._radio_seed_id != seed_id:
            generation = self._autoplay_generation
            task = asyncio.create_task(fetch_radio_tracks(seed_id))
            self._autoplay_task = task
            try:
                # 子タスクのキャンセル（オフ・手動追加）と再生ループの
                # キャンセル（停止）を区別し、停止時は親へ伝播させる。
                await asyncio.wait({task})
                if (
                    task.cancelled()
                    or generation != self._autoplay_generation
                    or not self._can_autoplay(voice_client)
                ):
                    return None
                self._radio_tracks = deque(task.result())
                self._radio_seed_id = seed_id
            except RecommendationError as exc:
                self.set_autoplay_enabled(False)
                await self._notify_autoplay_stopped(str(exc))
                return None
            except Exception:
                logger.exception("Autoplay lookup failed guild=%s", self.guild_id)
                self.set_autoplay_enabled(False)
                await self._notify_autoplay_stopped("関連曲の取得に失敗しました。")
                return None
            finally:
                if not task.done():
                    task.cancel()
                elif not task.cancelled():
                    task.exception()
                if self._autoplay_task is task:
                    self._autoplay_task = None

        excluded = set(self._recent_video_ids)
        excluded.add(seed_id)
        excluded.update(
            track.video_id or youtube_video_id(track.url)
            for track in self._queue.peek_all()
        )
        while self._radio_tracks:
            candidate = self._radio_tracks.popleft()
            if candidate.video_id not in excluded:
                return Track(
                    url=candidate.url,
                    title=candidate.title,
                    requester="自動選曲",
                    video_id=candidate.video_id,
                    auto_selected=True,
                )

        self.set_autoplay_enabled(False)
        await self._notify_autoplay_stopped(
            "まだ再生していない関連曲が見つかりませんでした。"
        )
        return None

    async def _play_stream(
        self,
        voice_client: discord.VoiceClient,
        stream_url: str,
        track: Track,
        duration: Optional[int],
        http_headers: Optional[Mapping[str, str]] = None,
        filesize: Optional[int] = None,
        http_chunk_size: Optional[int] = None,
    ) -> bool:
        loop = asyncio.get_running_loop()
        finished = asyncio.Event()
        playback_error = None

        def after_playing(error):
            nonlocal playback_error
            source_error = _get_ffmpeg_source_error(
                raw,
                wait_for_exit=not self._skip_requested,
            )
            playback_error = error or source_error
            if playback_error:
                logger.error(
                    "FFmpeg error guild=%s: %s",
                    self.guild_id,
                    playback_error,
                )
            loop.call_soon_threadsafe(finished.set)

        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()
            await asyncio.sleep(0.3)

        ffmpeg_stderr = open(os.devnull, "wb")
        ranged_stream = None
        try:
            if filesize and http_chunk_size:
                ranged_stream = YouTubeHTTPStream(
                    stream_url,
                    http_headers or {},
                    filesize,
                    http_chunk_size,
                )
                raw = discord.FFmpegPCMAudio(
                    ranged_stream,
                    pipe=True,
                    options=FFMPEG_OPTIONS,
                    stderr=ffmpeg_stderr,
                )
            else:
                raw = discord.FFmpegPCMAudio(
                    stream_url,
                    before_options=_build_ffmpeg_before_options(http_headers),
                    options=FFMPEG_OPTIONS,
                    stderr=ffmpeg_stderr,
                )
            paced_source = PacedAudioSource(raw)
            self._current_source = discord.PCMVolumeTransformer(
                paced_source,
                volume=self._volume,
            )
            voice_client.play(self._current_source, after=after_playing)
            timeout = (
                duration + PLAYBACK_TIMEOUT_GRACE_SECONDS
                if duration and duration > 0
                else UNKNOWN_DURATION_TIMEOUT_SECONDS
            )
            try:
                await asyncio.wait_for(finished.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                logger.error(
                    "Playback timed out guild=%s track=%s after=%ss",
                    self.guild_id,
                    track.title,
                    timeout,
                )
                if voice_client.is_playing() or voice_client.is_paused():
                    voice_client.stop()
                return False
            return playback_error is None
        finally:
            self._current_source = None
            if ranged_stream is not None:
                ranged_stream.close()
            ffmpeg_stderr.close()

    async def skip(self, voice_client: discord.VoiceClient) -> Optional[str]:
        """現在の曲をスキップ"""
        if not voice_client.is_playing() and not voice_client.is_paused():
            return None
        current_title = self._current.title if self._current else "Unknown"
        self._skip_requested = True
        self._cancel_idle_timeout()

        if self._loop_enabled:
            self._loop_enabled = False

        voice_client.stop()
        return current_title

    async def stop(self, voice_client: discord.VoiceClient) -> None:
        """停止・キュークリア・切断"""
        self._cancel_idle_timeout()
        self.cancel_empty_channel_timeout()
        self._loop_enabled = False
        self.set_autoplay_enabled(False)
        self._autoplay_seed = None
        self._current = None
        self._queue.clear()

        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        self._loop_task = None

        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()
        await asyncio.sleep(0.5)
        if voice_client.is_connected():
            await voice_client.disconnect()

    def pause(self, voice_client: discord.VoiceClient) -> bool:
        if voice_client.is_playing():
            voice_client.pause()
            return True
        return False

    def resume(self, voice_client: discord.VoiceClient) -> bool:
        if voice_client.is_paused():
            voice_client.resume()
            return True
        return False

    def toggle_loop(self) -> bool:
        self._loop_enabled = not self._loop_enabled
        return self._loop_enabled

    def is_loop_enabled(self) -> bool:
        return self._loop_enabled

    def get_queue_snapshot(self) -> Dict:
        return {
            "current": self._current,
            "queue": self._queue.peek_all(),
            "loop": self._loop_enabled,
            "autoplay": self._autoplay_enabled,
        }

    def clear_queue(self) -> int:
        return self._queue.clear()

    def _start_idle_timeout(self, voice_client: discord.VoiceClient) -> None:
        self._cancel_idle_timeout()

        async def _timeout():
            try:
                await asyncio.sleep(IDLE_TIMEOUT_SECONDS)
                if (
                    voice_client.is_connected()
                    and not self._queue
                    and not self._current
                ):
                    await self._send_idle_disconnect()
                    await voice_client.disconnect()
                    self._manager.remove(self.guild_id)
            except asyncio.CancelledError:
                pass

        self._idle_task = asyncio.create_task(_timeout())

    def _cancel_idle_timeout(self) -> None:
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()
        self._idle_task = None

    def update_empty_channel_timeout(
        self,
        voice_client: discord.VoiceClient,
    ) -> None:
        """VCが無人なら退出タイマーを開始し、人が戻れば解除する。"""
        if not voice_client.is_connected():
            self.cancel_empty_channel_timeout()
            return

        if self._has_human_member(voice_client):
            had_empty_timeout = bool(
                self._empty_channel_task and not self._empty_channel_task.done()
            )
            self.cancel_empty_channel_timeout()
            if (
                had_empty_timeout
                and not self._current
                and not self._queue
                and not voice_client.is_playing()
                and not voice_client.is_paused()
            ):
                self._start_idle_timeout(voice_client)
            return

        # 再生終了後のタイマーより、無人になってから3分のタイマーを優先する。
        self._cancel_idle_timeout()
        if self._empty_channel_task and not self._empty_channel_task.done():
            return

        async def _timeout():
            try:
                await asyncio.sleep(EMPTY_CHANNEL_TIMEOUT_SECONDS)
                if voice_client.is_connected() and not self._has_human_member(
                    voice_client
                ):
                    await self._send_empty_channel_disconnect()
                    await self.stop(voice_client)
                    self._manager.remove(self.guild_id)
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception(
                    "Empty channel disconnect failed guild=%s",
                    self.guild_id,
                )
            finally:
                if self._empty_channel_task is asyncio.current_task():
                    self._empty_channel_task = None

        self._empty_channel_task = asyncio.create_task(_timeout())

    def cancel_empty_channel_timeout(self) -> None:
        task = self._empty_channel_task
        self._empty_channel_task = None
        if task and not task.done() and task is not asyncio.current_task():
            task.cancel()

    @staticmethod
    def _has_human_member(voice_client: discord.VoiceClient) -> bool:
        channel = getattr(voice_client, "channel", None)
        if channel is None:
            return False
        return any(
            not getattr(member, "bot", False)
            for member in getattr(channel, "members", [])
        )

    async def _notify_error(self, track: Track, message: str) -> None:
        channel = self._get_text_channel()
        if not channel:
            return
        embed = discord.Embed(
            title="❌ 再生できませんでした",
            description=(
                f"**[{track.title}]({track.url})**\n"
                f"{message}\n"
                + (
                    "この曲をスキップして、次の曲を再生します。"
                    if self._queue
                    else "この曲をスキップしました。"
                )
            ),
            color=discord.Color.red(),
        )
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as e:
            logger.warning("Failed to send playback error notification: %s", e)

    async def _notify_autoplay_stopped(self, message: str) -> None:
        channel = self._get_text_channel()
        if not channel:
            return
        embed = discord.Embed(
            title="🤖 自動選曲をオフにしました",
            description=(
                f"{message}\n手動で追加した曲は引き続き再生します。"
                "\n再開するには `/autoplay enabled:True` を使ってください。"
            ),
            color=discord.Color.orange(),
        )
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            logger.warning(
                "Failed to send autoplay notification guild=%s", self.guild_id
            )

    async def _send_idle_disconnect(self) -> None:
        channel = self._get_text_channel()
        if not channel:
            return
        embed = discord.Embed(
            title="👋 自動切断",
            description="5分間再生がなかったため、ボイスチャンネルから切断しました。",
            color=discord.Color.orange(),
        )
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    async def _send_empty_channel_disconnect(self) -> None:
        channel = self._get_text_channel()
        if not channel:
            return
        embed = discord.Embed(
            title="👋 無人のため自動切断",
            description="ボイスチャンネルが3分間無人だったため、再生を停止して切断しました。",
            color=discord.Color.orange(),
        )
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    def _get_text_channel(self):
        guild = self._manager.bot.get_guild(self.guild_id)
        if not guild or not self._text_channel_id:
            return None
        channel = guild.get_channel(self._text_channel_id)
        if channel and hasattr(channel, "send"):
            perms = channel.permissions_for(guild.me)
            if perms.send_messages:
                return channel
        return None
