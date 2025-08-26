"""
Discord音声プレイヤー - シンプル版
"""

import asyncio
import logging
import discord
from typing import Optional, List, Dict, Callable
from pathlib import Path

logger = logging.getLogger(__name__)

class Track:
    """音楽トラック情報"""
    
    def __init__(self, url: str, title: str, file_path: str, requester: str):
        self.url = url
        self.title = title
        self.file_path = file_path
        self.requester = requester

class AudioPlayer:
    """Discord音声プレイヤー"""
    
    def __init__(self, volume: float = 0.25):
        self.volume = volume
        self.queues: Dict[int, List[Track]] = {}  # guild_id -> track list
        self.current_track: Dict[int, Optional[Track]] = {}  # guild_id -> current track
        self.loop_mode: Dict[int, bool] = {}  # guild_id -> loop enabled
        
    def add_to_queue(self, guild_id: int, track: Track):
        """キューにトラックを追加"""
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        
        self.queues[guild_id].append(track)
        logger.info(f"Added to queue [{guild_id}]: {track.title}")
    
    def get_queue(self, guild_id: int) -> List[Track]:
        """キューを取得"""
        return self.queues.get(guild_id, [])
    
    def clear_queue(self, guild_id: int):
        """キューをクリア"""
        if guild_id in self.queues:
            self.queues[guild_id].clear()
            logger.info(f"Cleared queue [{guild_id}]")
    
    def get_current_track(self, guild_id: int) -> Optional[Track]:
        """現在再生中のトラックを取得"""
        return self.current_track.get(guild_id)
    
    def set_loop(self, guild_id: int, enabled: bool):
        """ループモードを設定"""
        self.loop_mode[guild_id] = enabled
        logger.info(f"Loop mode [{guild_id}]: {enabled}")
    
    def is_loop_enabled(self, guild_id: int) -> bool:
        """ループモードが有効かチェック"""
        return self.loop_mode.get(guild_id, False)
    
    async def play_track(self, voice_client, track: Track, on_finish: Optional[Callable] = None) -> bool:
        """トラックを再生"""
        try:
            if not Path(track.file_path).exists():
                logger.error(f"Audio file not found: {track.file_path}")
                return False
            
            # FFmpegオプション
            ffmpeg_options = {
                'options': '-vn -bufsize 64k',
                'before_options': '-nostdin -loglevel error'
            }
            
            # 音声ソースを作成
            audio_source = discord.FFmpegPCMAudio(track.file_path, **ffmpeg_options)
            audio_source = discord.PCMVolumeTransformer(audio_source, volume=self.volume)
            
            # 再生終了時のコールバック
            def after_playing(error):
                if error:
                    logger.error(f"Playback error: {error}")
                else:
                    logger.info(f"Playback finished: {track.title}")
                
                # ファイルをクリーンアップ
                try:
                    if Path(track.file_path).exists():
                        Path(track.file_path).unlink()
                        logger.info(f"Cleaned up: {track.file_path}")
                except Exception as e:
                    logger.warning(f"Cleanup failed: {e}")
                
                # 次の曲を再生
                if on_finish:
                    asyncio.create_task(on_finish())
            
            # 再生開始
            if voice_client.is_playing():
                voice_client.stop()
            
            voice_client.play(audio_source, after=after_playing)
            
            # 現在のトラックを記録
            guild_id = voice_client.guild.id
            self.current_track[guild_id] = track
            
            logger.info(f"Started playing: {track.title}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to play track: {e}")
            return False
    
    def stop_playback(self, voice_client):
        """再生を停止"""
        try:
            if voice_client and voice_client.is_playing():
                voice_client.stop()
                
            guild_id = voice_client.guild.id
            if guild_id in self.current_track:
                del self.current_track[guild_id]
                
            logger.info("Playback stopped")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop playback: {e}")
            return False
    
    def pause_playback(self, voice_client) -> bool:
        """再生を一時停止"""
        try:
            if voice_client and voice_client.is_playing():
                voice_client.pause()
                logger.info("Playback paused")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to pause: {e}")
            return False
    
    def resume_playback(self, voice_client) -> bool:
        """再生を再開"""
        try:
            if voice_client and voice_client.is_paused():
                voice_client.resume()
                logger.info("Playback resumed")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to resume: {e}")
            return False
    
    def is_playing(self, voice_client) -> bool:
        """再生中かチェック"""
        return voice_client and voice_client.is_playing()
    
    def is_paused(self, voice_client) -> bool:
        """一時停止中かチェック"""
        return voice_client and voice_client.is_paused()
    
    def get_next_track(self, guild_id: int) -> Optional[Track]:
        """次のトラックを取得"""
        # ループモードの場合は現在のトラックを返す
        if self.is_loop_enabled(guild_id) and guild_id in self.current_track:
            return self.current_track[guild_id]
        
        # キューから次のトラックを取得
        if guild_id in self.queues and self.queues[guild_id]:
            return self.queues[guild_id].pop(0)
        
        return None
    
    def cleanup_guild(self, guild_id: int):
        """ギルドのデータをクリーンアップ"""
        if guild_id in self.queues:
            del self.queues[guild_id]
        if guild_id in self.current_track:
            del self.current_track[guild_id]
        if guild_id in self.loop_mode:
            del self.loop_mode[guild_id]
        
        logger.info(f"Cleaned up guild data: {guild_id}")
