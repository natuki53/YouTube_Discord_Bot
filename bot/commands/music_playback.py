"""
音楽再生/ダウンロード処理

コマンド層から切り離して、再生（ファイル再生）を集約。
"""

import asyncio
import logging
import time
import discord

from ..audio import AudioQueue, AudioPlayer, TrackInfo
from ..youtube import YouTubeDownloader
from .music_ui import build_progress_embed, safe_edit_message, get_next_queue_title, safe_send_to_text

logger = logging.getLogger(__name__)


async def download_and_play_track(
    guild_id: int,
    track_info: TrackInfo,
    voice_client,
    audio_queue: AudioQueue,
    audio_player: AudioPlayer,
    text_channel_id: int = None,
    progress_message: discord.Message = None,
):
    """トラックをダウンロードして（または事前ダウンロード済みを使って）ファイル再生する"""
    try:
        if text_channel_id is None:
            text_channel_id = audio_queue.get_text_channel(guild_id)

        downloader = YouTubeDownloader()

        # 事前ダウンロード済みのファイルを優先
        preloaded_track = audio_queue.get_preloaded_track(guild_id, track_info.url)
        if preloaded_track and preloaded_track.file_path:
            logger.info("Using preloaded track (file playback): %s", preloaded_track.title)
            track_info = preloaded_track
        else:
            if progress_message:
                await safe_edit_message(
                    progress_message,
                    embed=build_progress_embed(
                        title="⏳ 処理中",
                        status="ダウンロード中...",
                        url=track_info.url,
                        track_title=track_info.title,
                        requester=getattr(track_info, "user", None),
                        queue_length=audio_queue.get_queue_length(guild_id),
                        next_title=get_next_queue_title(audio_queue, guild_id),
                        color=discord.Color.blue()
                    )
                )

            logger.info("Downloading MP3 for playback: %s", track_info.title)
            download_result = await asyncio.get_event_loop().run_in_executor(
                None, downloader.download_mp3, track_info.url
            )

            if isinstance(download_result, tuple):
                success, downloaded_title = download_result
                if downloaded_title and downloaded_title != "Unknown Title":
                    track_info.title = downloaded_title
            else:
                success = bool(download_result)

            if not success:
                raise RuntimeError("download_mp3 failed")

            file_path = downloader.get_latest_mp3_file(track_info.url)
            if not file_path:
                raise FileNotFoundError("Downloaded MP3 file not found for URL")
            track_info.file_path = file_path

        finished_track_url = track_info.url

        async def on_finish(error, _guild_id, finished_track_info):
            manual_skip = audio_queue.consume_manual_skip(_guild_id)

            # on_finish の並行実行を避ける（次曲取得が二重に走るとキューが崩れる）
            playback_lock = await audio_queue.get_playback_lock(_guild_id)
            async with playback_lock:
                current_track = audio_queue.get_now_playing(_guild_id)
                if current_track and current_track.url != finished_track_url:
                    logger.warning(
                        "Playback finish callback called for wrong track. Current: %s, Finished: %s",
                        current_track.url, finished_track_url
                    )
                    return

                await asyncio.sleep(0.2)
                if voice_client and voice_client.is_playing():
                    logger.warning("Playback finish callback called but still playing after wait. Ignoring.")
                    return

                # 接続切断/張り直し中は次曲へ進まない（ユーザー操作待ち）
                try:
                    await asyncio.sleep(0.5)
                    if voice_client and not voice_client.is_connected() and not manual_skip:
                        logger.warning("Voice client disconnected/handshaking; not advancing queue.")
                        return
                except Exception:
                    pass

                logger.info("✅ Playback finished for track: %s (URL: %s)", finished_track_info.title, finished_track_url)

                audio_queue.cleanup_completed_downloads(_guild_id)

                if audio_queue.is_loop_enabled(_guild_id):
                    logger.info("🔁 Loop enabled, repeating track from beginning: %s", finished_track_info.title)
                    audio_queue.clear_now_playing(_guild_id)
                    saved_channel_id = audio_queue.get_text_channel(_guild_id)
                    channel_id_to_use = text_channel_id or saved_channel_id
                    await download_and_play_track(
                        _guild_id, finished_track_info, voice_client, audio_queue, audio_player, channel_id_to_use, progress_message
                    )
                    return

                next_track = audio_queue.get_next_track(_guild_id)
                if next_track:
                    logger.info("🎵 Playing next track for guild %s: %s", _guild_id, next_track.title)
                    audio_queue.clear_now_playing(_guild_id)
                    audio_queue.start_preload(_guild_id)
                    saved_channel_id = audio_queue.get_text_channel(_guild_id)
                    channel_id_to_use = text_channel_id or saved_channel_id
                    await download_and_play_track(
                        _guild_id, next_track, voice_client, audio_queue, audio_player, channel_id_to_use, None
                    )
                else:
                    audio_queue.clear_now_playing(_guild_id)
                    if voice_client and voice_client.is_connected():
                        audio_queue.start_idle_timeout(_guild_id, voice_client)

        if audio_player.is_playing(voice_client):
            logger.warning("Already playing audio for guild %s, skipping playback of: %s", guild_id, track_info.title)
            audio_queue.set_starting_playback(guild_id, False)
            return

        audio_queue.set_now_playing(guild_id, track_info)
        is_loop_track = audio_queue.is_loop_enabled(guild_id)
        logger.info("🔄 Loop check for guild %s: is_loop_enabled=%s, track=%s", guild_id, is_loop_track, track_info.title)

        started = await audio_player.play_track(guild_id, track_info, voice_client, on_finish, is_loop_track)
        audio_queue.set_starting_playback(guild_id, False)

        if not started:
            audio_queue.clear_now_playing(guild_id)
            raise RuntimeError("Failed to start file playback")

        # 再生開始通知（進捗メッセージがあればそれを更新、無ければ通常送信）
        try:
            file_size = downloader.get_file_size_mb(track_info.file_path) if track_info.file_path else None
        except Exception:
            file_size = None

        playback_embed = build_progress_embed(
            title="🎵 再生開始" if not is_loop_track else "🔁 ループ再生",
            status="再生中",
            url=track_info.url,
            track_title=track_info.title,
            requester=getattr(track_info, "user", None),
            queue_length=audio_queue.get_queue_length(guild_id),
            next_title=get_next_queue_title(audio_queue, guild_id),
            file_size_mb=file_size,
            color=discord.Color.green() if not is_loop_track else discord.Color.orange()
        )

        if progress_message:
            await safe_edit_message(progress_message, embed=playback_embed)
        else:
            channel_id_for_notification = text_channel_id or audio_queue.get_text_channel(guild_id)
            if channel_id_for_notification:
                try:
                    channel = voice_client.guild.get_channel(channel_id_for_notification)
                    if channel and channel.permissions_for(voice_client.guild.me).send_messages:
                        async def send_notification():
                            try:
                                await asyncio.wait_for(channel.send(embed=playback_embed), timeout=10.0)
                            except Exception:
                                logger.exception("Failed to send playback notification")
                        task_id = f"guild_{guild_id}_notification_{int(time.time() * 1000)}"
                        audio_queue.register_task(task_id, asyncio.create_task(send_notification()))
                except Exception:
                    logger.exception("Failed to setup playback notification")

    except asyncio.CancelledError:
        logger.info("Download and play task cancelled for guild %s", guild_id)
        raise
    except Exception:
        logger.exception("Unexpected error in download_and_play_track for guild %s", guild_id)
        try:
            audio_queue.clear_now_playing(guild_id)
            next_track = audio_queue.get_next_track(guild_id)
            if next_track and voice_client and voice_client.is_connected():
                saved_channel_id = audio_queue.get_text_channel(guild_id)
                await download_and_play_track(guild_id, next_track, voice_client, audio_queue, audio_player, saved_channel_id, None)
                return

            if voice_client and voice_client.is_connected():
                embed = discord.Embed(
                    title="❌ 再生に失敗しました",
                    description="エラーが発生したため、ボイスチャンネルから切断しました。",
                    color=discord.Color.red()
                )
                await safe_send_to_text(guild_id, audio_queue, voice_client, embed=embed, channel_id=text_channel_id)
                await voice_client.disconnect()
        except Exception:
            logger.exception("Failed to recover from error for guild %s", guild_id)
    finally:
        if audio_queue.is_starting_playback_active(guild_id):
            audio_queue.set_starting_playback(guild_id, False)
