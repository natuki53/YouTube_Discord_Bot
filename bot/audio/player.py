"""
音声プレイヤー

Discord音声チャンネルでの音声再生機能
"""

import asyncio
import discord
import logging
import threading
from pathlib import Path
from typing import Optional, Callable

from ..utils.file_utils import cleanup_audio_file, validate_audio_file, get_latest_audio_file, protect_file, unprotect_file
from .track_info import TrackInfo

logger = logging.getLogger(__name__)

class AudioPlayer:
    """音声再生を管理するクラス"""
    
    def __init__(self, download_dir: str):
        self.download_dir = download_dir
        self.current_audio_files = {}  # guild_id -> file_path
    
    async def play_track(self, 
                        guild_id: int, 
                        track_info: TrackInfo, 
                        voice_client, 
                        on_finish_callback: Optional[Callable] = None,
                        is_loop: bool = False):
        """
        トラックを再生する
        
        Args:
            guild_id: ギルドID
            track_info: トラック情報
            voice_client: ボイスクライアント
            on_finish_callback: 再生終了時のコールバック
        """
        try:
            # 音声ファイルを取得
            file_path = track_info.file_path or get_latest_audio_file(self.download_dir)
            
            if not file_path or not validate_audio_file(file_path):
                logger.error(f"Invalid audio file for track: {track_info.title}")
                return False
            
            logger.info(f"Playing track: {track_info.title} ({file_path})")
            
            # 音声を再生
            success = await self._start_playback(
                guild_id, file_path, track_info, voice_client, on_finish_callback, is_loop
            )
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to play track {track_info.title}: {e}")
            return False
    
    async def _start_playback(self, 
                             guild_id: int, 
                             file_path: str, 
                             track_info: TrackInfo, 
                             voice_client, 
                             on_finish_callback: Optional[Callable] = None,
                             is_loop: bool = False):
        """音声再生を開始"""
        try:
            # FFmpegオプションを設定
            ffmpeg_options = {
                'options': '-vn',
                'before_options': '-y -nostdin -loglevel error -hide_banner -re'
            }
            
            # 音声ソースを作成
            audio_source = discord.FFmpegPCMAudio(file_path, **ffmpeg_options)
            audio_source = discord.PCMVolumeTransformer(audio_source)
            audio_source.volume = 0.25
            
            # 再生終了時のコールバックを設定
            def after_playing(error):
                if error:
                    logger.error(f"Track playback finished with error: {error}")
                else:
                    logger.info(f"Track playback finished successfully: {track_info.title}")
                
                logger.info(f"🔄 After playing callback - is_loop={is_loop}, file_path={file_path}, guild={guild_id}")
                
                # ループ時はファイルを削除しない（再利用のため）
                if not is_loop:
                    unprotect_file(file_path)  # 保護を解除してから削除
                    cleanup_audio_file(file_path, guild_id)
                    logger.info(f"🗑️ Cleaned up audio file (non-loop): {file_path}")
                else:
                    logger.info(f"🔁 Keeping audio file for loop: {file_path}")
                
                # ループでない場合のみ、現在の音声ファイル記録を削除
                if not is_loop and guild_id in self.current_audio_files:
                    del self.current_audio_files[guild_id]
                
                # コールバックを実行
                if on_finish_callback:
                    # より安全な非同期コールバック実行
                    def run_callback():
                        try:
                            # 非同期コールバックの場合
                            if asyncio.iscoroutinefunction(on_finish_callback):
                                # 既存のイベントループを取得または新規作成
                                try:
                                    # 現在のイベントループを取得
                                    loop = asyncio.get_event_loop()
                                    if loop.is_running():
                                        # イベントループが実行中の場合、asyncio.run_coroutine_threadsafeを使用
                                        future = asyncio.run_coroutine_threadsafe(
                                            on_finish_callback(error, guild_id, track_info), loop
                                        )
                                        future.result(timeout=30)  # 30秒でタイムアウト
                                    else:
                                        # イベントループが停止中の場合、新しいループで実行
                                        loop.run_until_complete(
                                            on_finish_callback(error, guild_id, track_info)
                                        )
                                except RuntimeError:
                                    # イベントループが存在しない場合、新しいループを作成
                                    try:
                                        new_loop = asyncio.new_event_loop()
                                        asyncio.set_event_loop(new_loop)
                                        new_loop.run_until_complete(
                                            on_finish_callback(error, guild_id, track_info)
                                        )
                                    finally:
                                        try:
                                            new_loop.close()
                                            asyncio.set_event_loop(None)
                                        except Exception:
                                            pass
                                except Exception as async_error:
                                    logger.error(f"Error in async callback: {async_error}")
                            else:
                                # 同期コールバックの場合
                                on_finish_callback(error, guild_id, track_info)
                        except Exception as cb_error:
                            logger.error(f"Error in playback callback: {cb_error}")
                    
                    # 別スレッドでコールバックを実行
                    callback_thread = threading.Thread(target=run_callback, daemon=True)
                    callback_thread.start()
            
            # 再生開始
            if voice_client and voice_client.is_connected():
                # 既に再生中の場合はエラーを返す
                if voice_client.is_playing():
                    logger.warning(f"Already playing audio for guild {guild_id}, cannot start new track: {track_info.title}")
                    return False
                
                voice_client.play(audio_source, after=after_playing)
                self.current_audio_files[guild_id] = file_path
                
                # ループの場合はファイルを保護
                if is_loop:
                    protect_file(file_path)
                    logger.info(f"🔒 Protected loop file: {file_path}")
                
                logger.info(f"Started playing track: {track_info.title}")
                return True
            else:
                logger.error("Voice client not connected")
                return False
                
        except Exception as e:
            logger.error(f"Failed to start playback: {e}")
            cleanup_audio_file(file_path, guild_id)
            return False
    
    def stop_playback(self, guild_id: int, voice_client):
        """再生を停止"""
        try:
            if voice_client and voice_client.is_playing():
                voice_client.stop()
                logger.info(f"Stopped playback for guild {guild_id}")
            
            # 現在の音声ファイルをクリーンアップ（ループファイルも含む）
            if guild_id in self.current_audio_files:
                file_path = self.current_audio_files[guild_id]
                unprotect_file(file_path)  # 保護を解除
                cleanup_audio_file(file_path, guild_id, force_delete=True)  # 強制削除
                del self.current_audio_files[guild_id]
                logger.info(f"Cleaned up audio file on stop: {file_path}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop playback for guild {guild_id}: {e}")
            return False
    
    def pause_playback(self, voice_client):
        """再生を一時停止"""
        try:
            if voice_client and voice_client.is_playing():
                voice_client.pause()
                logger.info("Paused playback")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to pause playback: {e}")
            return False
    
    def resume_playback(self, voice_client):
        """再生を再開"""
        try:
            if voice_client and voice_client.is_paused():
                voice_client.resume()
                logger.info("Resumed playback")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to resume playback: {e}")
            return False
    
    def is_playing(self, voice_client) -> bool:
        """再生中かどうかを確認"""
        return voice_client and voice_client.is_playing()
    
    def is_paused(self, voice_client) -> bool:
        """一時停止中かどうかを確認"""
        return voice_client and voice_client.is_paused()
    
    def get_current_file(self, guild_id: int) -> Optional[str]:
        """現在再生中のファイルパスを取得"""
        return self.current_audio_files.get(guild_id)
    
    def cleanup_loop_file(self, guild_id: int):
        """ループ終了時にファイルをクリーンアップ"""
        try:
            if guild_id in self.current_audio_files:
                file_path = self.current_audio_files[guild_id]
                unprotect_file(file_path)  # 保護を解除
                cleanup_audio_file(file_path, guild_id, force_delete=True)  # 強制削除
                del self.current_audio_files[guild_id]
                logger.info(f"Cleaned up loop file: {file_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to cleanup loop file for guild {guild_id}: {e}")
            return False
