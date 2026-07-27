"""ギルド単位の再生ワーカー（ストリーミング再生）"""

import asyncio
import logging
from typing import TYPE_CHECKING, Dict, Optional

import discord

from ..youtube.stream import StreamError, resolve_stream
from .embeds import build_track_embed
from .models import Track
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
FFMPEG_BEFORE = (
    "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 10 "
    "-nostdin -loglevel warning"
)
FFMPEG_OPTIONS = "-vn"


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
            self._ensure_play_loop(voice_client)
            return "playing"

    def _ensure_play_loop(self, voice_client: discord.VoiceClient) -> None:
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._play_loop(voice_client))

    async def _play_loop(self, voice_client: discord.VoiceClient) -> None:
        retry_track: Optional[Track] = None
        retry_count = 0

        while True:
            is_retry = retry_track is not None
            track = retry_track or self._get_next_track()
            retry_track = None
            if track is None:
                break

            is_loop_restart = self._loop_enabled and track is self._current
            self._current = track
            self._skip_requested = False

            try:
                stream_info = await resolve_stream(track.url)
                if track.title == track.url or track.title.startswith("YouTube"):
                    track.title = stream_info.title

                # 再生開始通知は FFmpeg 起動前に送る（await しないと音が先に鳴る）
                if not is_loop_restart and not is_retry:
                    await self._send_now_playing(
                        track,
                        stream_info.duration,
                        stream_info.video_id,
                    )

                played = await self._play_stream(
                    voice_client,
                    stream_info.url,
                    track,
                    stream_info.duration,
                )
                if not played and not self._skip_requested:
                    raise StreamError("FFmpeg が再生を完了できませんでした")

            except StreamError as e:
                logger.warning(f"Stream error guild={self.guild_id}: {e}")
                error_message = str(e)
            except Exception as e:
                logger.exception(f"Play loop error guild={self.guild_id}: {e}")
                error_message = "予期しないエラーが発生しました"
            else:
                retry_count = 0
                if not self._loop_enabled:
                    self._current = None
                error_message = None

            if error_message is not None:
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
                self._current = None
                retry_count = 0
                if not voice_client.is_connected():
                    break
                continue

            if not voice_client.is_connected():
                break

            if not self._loop_enabled and not self._queue and not self._skip_requested:
                if not voice_client.is_playing() and not voice_client.is_paused():
                    self._start_idle_timeout(voice_client)
                    break

        self._loop_task = None

    def _get_next_track(self) -> Optional[Track]:
        if self._loop_enabled and self._current:
            return self._current
        return self._queue.dequeue()

    async def _play_stream(
        self,
        voice_client: discord.VoiceClient,
        stream_url: str,
        track: Track,
        duration: Optional[int],
    ) -> bool:
        loop = asyncio.get_running_loop()
        finished = asyncio.Event()
        playback_error = None

        def after_playing(error):
            nonlocal playback_error
            playback_error = error
            if error:
                logger.error(f"FFmpeg error guild={self.guild_id}: {error}")
            loop.call_soon_threadsafe(finished.set)

        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()
            await asyncio.sleep(0.3)

        try:
            raw = discord.FFmpegPCMAudio(
                stream_url,
                before_options=FFMPEG_BEFORE,
                options=FFMPEG_OPTIONS,
            )
            self._current_source = discord.PCMVolumeTransformer(
                raw, volume=self._volume
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

    async def _send_now_playing(
        self,
        track: Track,
        duration: Optional[int],
        video_id: Optional[str] = None,
    ) -> None:
        channel = self._get_text_channel()
        if not channel:
            return
        embed = build_track_embed(
            heading="▶️ 再生開始",
            track=track,
            color=discord.Color.green(),
            duration_seconds=duration,
            queued_tracks=len(self._queue),
            video_id=video_id,
        )
        if self._loop_enabled:
            embed.add_field(name="🔁 ループ", value="有効", inline=True)
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as e:
            logger.warning(f"Failed to send now playing notification: {e}")

    async def _notify_error(self, track: Track, message: str) -> None:
        channel = self._get_text_channel()
        if not channel:
            return
        embed = discord.Embed(
            title="❌ 再生スキップ",
            description=f"**{track.title}**\n{message}",
            color=discord.Color.red(),
        )
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

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
