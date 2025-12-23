"""
音声プレイヤー

Discord音声チャンネルでの音声再生機能
"""

import asyncio
import discord
import logging
import inspect
import shutil
from pathlib import Path
from typing import Optional, Callable

from ..utils.file_utils import cleanup_audio_file, validate_audio_file, get_latest_audio_file, protect_file, unprotect_file
from .track_info import TrackInfo

logger = logging.getLogger(__name__)

class AudioPlayer:
    """音声再生を管理するクラス"""
    
    def __init__(self, download_dir: str, ffmpeg_location: Optional[str] = None):
        self.download_dir = download_dir
        self.current_audio_files = {}  # guild_id -> file_path
        # FFmpegのパスを決定（明示指定 > 環境変数 > 自動検出）
        self.ffmpeg_path = self._find_ffmpeg(ffmpeg_location)
        if self.ffmpeg_path:
            logger.info(f"Using FFmpeg at: {self.ffmpeg_path}")
        else:
            logger.warning("FFmpeg path not found, will try default")
    
    def _find_ffmpeg(self, explicit_path: Optional[str] = None) -> Optional[str]:
        """FFmpegのパスを検出"""
        import os
        # 1. 明示的に指定されたパス
        if explicit_path:
            p = Path(explicit_path)
            if p.is_dir():
                # ディレクトリ指定の場合、ffmpeg.exe または ffmpeg を探す
                for exe in ['ffmpeg.exe', 'ffmpeg']:
                    candidate = p / exe
                    if candidate.exists():
                        return str(candidate)
            elif p.exists():
                return str(p)
        
        # 2. 環境変数から
        env_path = os.environ.get('FFMPEG_LOCATION')
        if env_path:
            p = Path(env_path)
            if p.is_dir():
                for exe in ['ffmpeg.exe', 'ffmpeg']:
                    candidate = p / exe
                    if candidate.exists():
                        return str(candidate)
            elif p.exists():
                return str(env_path)
        
        # 3. PATHから自動検出
        ffmpeg_cmd = shutil.which('ffmpeg')
        if ffmpeg_cmd:
            return ffmpeg_cmd
        
        return None
    
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
            logger.exception("Failed to play track: %s", track_info.title)
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
            # この時点のイベントループ（Discord botのメインループ）を捕捉して、
            # voice_clientのafterスレッドから安全にコルーチンを戻すために使う
            main_loop = asyncio.get_running_loop()

            # FFmpegオプションを設定（-re はストリーミング用なのでファイル再生では削除）
            ffmpeg_options = {
                'options': '-vn',
                'before_options': '-y -nostdin -loglevel error -hide_banner'
            }
            
            # FFmpegのパスを明示的に指定（Windows環境で確実に動作させるため）
            if self.ffmpeg_path:
                ffmpeg_options['executable'] = self.ffmpeg_path
            
            # 音声ソースを作成
            try:
                audio_source = discord.FFmpegPCMAudio(file_path, **ffmpeg_options)
            except Exception as e:
                logger.exception("Failed to create FFmpegPCMAudio source: %s", e)
                raise
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
                    try:
                        result = on_finish_callback(error, guild_id, track_info)
                        if inspect.isawaitable(result):
                            # voice_client.after は別スレッドで呼ばれるため、メインループへ戻す
                            fut = asyncio.run_coroutine_threadsafe(result, main_loop)
                            # 結果待ちはしない（音声スレッドをブロックしない）
                            def _done_cb(f):
                                try:
                                    f.result()
                                except Exception:
                                    logger.exception("Error in on_finish_callback coroutine")
                            fut.add_done_callback(_done_cb)
                    except RuntimeError:
                        # ループ終了/未初期化等（終了処理中に起きがち）
                        logger.warning("Main event loop not available for on_finish_callback (probably shutting down)")
                    except Exception:
                        logger.exception("Error in playback callback")
            
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
            logger.exception("Failed to start playback")
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
            logger.exception("Failed to stop playback for guild %s", guild_id)
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
            logger.exception("Failed to pause playback")
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
            logger.exception("Failed to resume playback")
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
            logger.exception("Failed to cleanup loop file for guild %s", guild_id)
            return False
