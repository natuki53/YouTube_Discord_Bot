"""
音声キュー管理

複数のギルドの音楽キューを管理するクラス
"""

import asyncio
import logging
import threading
from typing import Dict, List, Optional, Callable
from .track_info import TrackInfo

logger = logging.getLogger(__name__)

class AudioQueue:
    """音声キューを管理するクラス"""
    
    def __init__(self):
        self.queues: Dict[int, List[TrackInfo]] = {}  # guild_id -> queue
        self.now_playing: Dict[int, TrackInfo] = {}  # guild_id -> current_track
        self.downloaded_tracks: Dict[str, bool] = {}  # download_key -> status
        
        # ループ機能
        self.loop_enabled: Dict[int, bool] = {}  # guild_id -> loop_status
        
        # 事前ダウンロード機能
        self.preload_tracks: Dict[str, TrackInfo] = {}  # download_key -> track_info
        self.download_status: Dict[str, str] = {}  # download_key -> status (pending/downloading/completed/failed)
        self.download_threads: Dict[str, threading.Thread] = {}  # download_key -> thread
        self.max_preload_tracks = 3  # 最大事前ダウンロード数（パフォーマンス向上）
        self.download_callback: Optional[Callable] = None  # ダウンロード完了コールバック
        
        # アイドルタイムアウト機能
        self.idle_timeout_tasks: Dict[int, asyncio.Task] = {}  # guild_id -> timeout_task
        self.idle_timeout_duration = 300  # 5分間（秒）
        
        # テキストチャンネル情報（通知用）
        self.text_channels: Dict[int, int] = {}  # guild_id -> text_channel_id
        
        # 同時再生リクエスト管理
        self.pending_requests: Dict[int, List[TrackInfo]] = {}  # guild_id -> pending_tracks
        self.playback_locks: Dict[int, asyncio.Lock] = {}  # guild_id -> lock
        self.is_starting_playback: Dict[int, bool] = {}  # guild_id -> bool
        
        # タスク管理
        self.active_tasks: Dict[str, asyncio.Task] = {}  # task_id -> task
    
    def add_track(self, guild_id: int, track_info: TrackInfo):
        """キューにトラックを追加"""
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        
        # 辞書形式のtrack_infoの場合はTrackInfoオブジェクトに変換
        if isinstance(track_info, dict):
            track_info = TrackInfo.from_dict(track_info)
        
        self.queues[guild_id].append(track_info)
        
        # 新しい曲が追加されたのでアイドルタイムアウトをキャンセル
        self.cancel_idle_timeout(guild_id)
        
        logger.info(f"Added track to queue for guild {guild_id}: {track_info.title}")
    
    def get_next_track(self, guild_id: int) -> Optional[TrackInfo]:
        """次のトラックを取得"""
        # ループが有効で現在再生中の曲がある場合は、同じ曲を返す
        if self.is_loop_enabled(guild_id) and guild_id in self.now_playing:
            current_track = self.now_playing[guild_id]
            if current_track:
                logger.info(f"Loop track for guild {guild_id}: {current_track.title}")
                # ループの場合は新しいTrackInfoオブジェクトを作成して返す
                # （同じオブジェクトを再利用すると状態管理で問題が起きる可能性があるため）
                return TrackInfo(
                    url=current_track.url,
                    title=current_track.title,
                    user=current_track.user,
                    added_at=current_track.added_at,
                    file_path=current_track.file_path
                )
        
        # 通常の次の曲取得
        if guild_id in self.queues and self.queues[guild_id]:
            track = self.queues[guild_id].pop(0)
            # ここでnow_playingを更新するのは適切ではない
            # 実際の再生開始時に更新されるべき
            logger.info(f"Next track for guild {guild_id}: {track.title}")
            return track
        return None
    
    def get_queue(self, guild_id: int) -> List[TrackInfo]:
        """キューの内容を取得"""
        if guild_id in self.queues:
            return self.queues[guild_id].copy()
        return []
    
    def clear_queue(self, guild_id: int):
        """キューをクリア"""
        if guild_id in self.queues:
            self.queues[guild_id].clear()
            logger.info(f"Cleared queue for guild {guild_id}")
    
    def get_queue_length(self, guild_id: int) -> int:
        """キューの長さを取得"""
        if guild_id in self.queues:
            return len(self.queues[guild_id])
        return 0
    
    def is_playing(self, guild_id: int) -> bool:
        """現在再生中かどうかを確認"""
        return guild_id in self.now_playing and self.now_playing[guild_id] is not None
    
    def get_now_playing(self, guild_id: int) -> Optional[TrackInfo]:
        """現在再生中のトラックを取得"""
        return self.now_playing.get(guild_id)
    
    def set_now_playing(self, guild_id: int, track_info: TrackInfo):
        """現在再生中のトラックを設定"""
        self.now_playing[guild_id] = track_info
        logger.info(f"Set now playing for guild {guild_id}: {track_info.title}")
    
    def clear_now_playing(self, guild_id: int):
        """現在再生中のトラックをクリア"""
        if guild_id in self.now_playing:
            del self.now_playing[guild_id]
            logger.info(f"Cleared now playing for guild {guild_id}")
    
    def has_queue(self, guild_id: int) -> bool:
        """キューに曲があるかどうかを確認"""
        return guild_id in self.queues and len(self.queues[guild_id]) > 0
    
    def set_download_status(self, guild_id: int, url: str, status: bool):
        """ダウンロード状況を記録"""
        download_key = f"{guild_id}_{url}"
        self.downloaded_tracks[download_key] = status
        logger.debug(f"Set download status for {download_key}: {status}")
    
    def get_download_status(self, guild_id: int, url: str) -> bool:
        """ダウンロード状況を取得"""
        download_key = f"{guild_id}_{url}"
        return self.downloaded_tracks.get(download_key, False)
    
    def remove_guild_data(self, guild_id: int):
        """ギルドのすべてのデータを削除"""
        if guild_id in self.queues:
            del self.queues[guild_id]
        if guild_id in self.now_playing:
            del self.now_playing[guild_id]
        if guild_id in self.text_channels:
            del self.text_channels[guild_id]
        if guild_id in self.loop_enabled:
            del self.loop_enabled[guild_id]
        
        # 新しい状態管理データも削除
        if guild_id in self.pending_requests:
            del self.pending_requests[guild_id]
        if guild_id in self.playback_locks:
            del self.playback_locks[guild_id]
        if guild_id in self.is_starting_playback:
            del self.is_starting_playback[guild_id]
        
        # アイドルタイムアウトもキャンセル
        self.cancel_idle_timeout(guild_id)
        
        # ギルドに関連するタスクもキャンセル
        self.cancel_guild_tasks(guild_id)
        
        # ダウンロード情報も削除
        keys_to_remove = [key for key in self.downloaded_tracks.keys() if key.startswith(f"{guild_id}_")]
        for key in keys_to_remove:
            del self.downloaded_tracks[key]
        
        logger.info(f"Removed all data for guild {guild_id}")
    
    def set_download_callback(self, callback: Callable):
        """ダウンロード完了コールバックを設定"""
        self.download_callback = callback
        logger.info("Download callback set")
    
    def set_text_channel(self, guild_id: int, channel_id: int):
        """ギルドのテキストチャンネルIDを設定"""
        self.text_channels[guild_id] = channel_id
        logger.debug(f"Set text channel for guild {guild_id}: {channel_id}")
    
    def get_text_channel(self, guild_id: int) -> Optional[int]:
        """ギルドのテキストチャンネルIDを取得"""
        return self.text_channels.get(guild_id)
    
    def _get_download_key(self, guild_id: int, url: str) -> str:
        """ダウンロードキーを生成"""
        return f"{guild_id}_{hash(url)}"
    
    def start_preload(self, guild_id: int):
        """事前ダウンロードを開始"""
        try:
            if guild_id not in self.queues or not self.queues[guild_id]:
                logger.debug(f"No tracks to preload for guild {guild_id}")
                return
            
            # 事前ダウンロード対象のトラックを取得
            tracks_to_preload = self.queues[guild_id][:self.max_preload_tracks]
            
            for track in tracks_to_preload:
                download_key = self._get_download_key(guild_id, track.url)
                
                # 既にダウンロード中または完了している場合はスキップ
                if download_key in self.download_status:
                    current_status = self.download_status[download_key]
                    if current_status in ['downloading', 'completed']:
                        logger.debug(f"Track already {current_status}: {track.title}")
                        continue
                
                # 事前ダウンロードを開始
                self._start_background_download(guild_id, track)
                
            logger.info(f"Started preload for guild {guild_id}: {len(tracks_to_preload)} tracks")
            
        except Exception as e:
            logger.error(f"Failed to start preload for guild {guild_id}: {e}")
    
    def _start_background_download(self, guild_id: int, track: TrackInfo):
        """バックグラウンドダウンロードを開始"""
        try:
            download_key = self._get_download_key(guild_id, track.url)
            
            # YouTubeDownloaderクラスレベルでのダウンロード状況をチェック
            from ..youtube import YouTubeDownloader
            global_status = YouTubeDownloader.get_download_status(track.url)
            
            if global_status in ['downloading', 'completed']:
                logger.info(f"Download already in progress or completed globally: {track.title}")
                self.download_status[download_key] = global_status
                if global_status == 'completed':
                    # 既に完了している場合は、ファイルパスを取得
                    downloader = YouTubeDownloader()
                    file_path = downloader.get_latest_mp3_file()
                    if file_path:
                        track.file_path = file_path
                        self.preload_tracks[download_key] = track
                return
            
            # ダウンロード状況を記録
            self.download_status[download_key] = 'pending'
            self.preload_tracks[download_key] = track
            
            def download_worker():
                try:
                    logger.info(f"Starting background download: {track.title}")
                    self.download_status[download_key] = 'downloading'
                    
                    # YouTubeDownloaderを使用してダウンロード
                    downloader = YouTubeDownloader()
                    
                    # MP3をダウンロード（既に競合制御が実装済み）
                    success, downloaded_title = downloader.download_mp3(track.url)
                    
                    if success:
                        # ファイルパスを取得して保存
                        file_path = downloader.get_latest_mp3_file()
                        if file_path:
                            track.file_path = file_path
                            if downloaded_title and downloaded_title != "Unknown Title":
                                track.title = downloaded_title
                            
                            self.download_status[download_key] = 'completed'
                            logger.info(f"Background download completed: {track.title}")
                            
                            # コールバックを実行
                            if self.download_callback:
                                try:
                                    self.download_callback(guild_id, track, True)
                                except Exception as cb_error:
                                    logger.error(f"Error in download callback: {cb_error}")
                        else:
                            self.download_status[download_key] = 'failed'
                            logger.error(f"Background download failed: file not found for {track.title}")
                    else:
                        self.download_status[download_key] = 'failed'
                        logger.error(f"Background download failed: {track.title}")
                        
                        # エラーコールバックを実行
                        if self.download_callback:
                            try:
                                self.download_callback(guild_id, track, False)
                            except Exception as cb_error:
                                logger.error(f"Error in download error callback: {cb_error}")
                
                except Exception as e:
                    self.download_status[download_key] = 'failed'
                    logger.error(f"Background download worker error: {e}")
                finally:
                    # スレッド情報をクリーンアップ
                    if download_key in self.download_threads:
                        del self.download_threads[download_key]
            
            # バックグラウンドスレッドでダウンロード実行
            download_thread = threading.Thread(target=download_worker, daemon=True)
            self.download_threads[download_key] = download_thread
            download_thread.start()
            
            logger.debug(f"Background download thread started for: {track.title}")
            
        except Exception as e:
            logger.error(f"Failed to start background download: {e}")
    
    def is_track_ready(self, guild_id: int, url: str) -> bool:
        """トラックがダウンロード済みかチェック"""
        download_key = self._get_download_key(guild_id, url)
        return self.download_status.get(download_key) == 'completed'
    
    def get_preloaded_track(self, guild_id: int, url: str) -> Optional[TrackInfo]:
        """事前ダウンロード済みのトラックを取得"""
        download_key = self._get_download_key(guild_id, url)
        if self.download_status.get(download_key) == 'completed':
            return self.preload_tracks.get(download_key)
        return None
    
    def cleanup_completed_downloads(self, guild_id: int):
        """完了済みダウンロードをクリーンアップ"""
        try:
            keys_to_remove = []
            guild_prefix = f"{guild_id}_"
            
            for download_key in self.download_status:
                if download_key.startswith(guild_prefix):
                    status = self.download_status[download_key]
                    if status in ['completed', 'failed']:
                        keys_to_remove.append(download_key)
            
            for key in keys_to_remove:
                if key in self.download_status:
                    del self.download_status[key]
                if key in self.preload_tracks:
                    # グローバルダウンロードステータスもクリーンアップ
                    track = self.preload_tracks[key]
                    from ..youtube import YouTubeDownloader
                    downloader = YouTubeDownloader()
                    downloader.cleanup_download_status(track.url)
                    del self.preload_tracks[key]
                if key in self.download_threads:
                    del self.download_threads[key]
            
            if keys_to_remove:
                logger.info(f"Cleaned up {len(keys_to_remove)} completed downloads for guild {guild_id}")
            
        except Exception as e:
            logger.error(f"Failed to cleanup completed downloads: {e}")
    
    def get_download_stats(self, guild_id: int) -> dict:
        """ダウンロード統計情報を取得"""
        guild_prefix = f"{guild_id}_"
        stats = {'pending': 0, 'downloading': 0, 'completed': 0, 'failed': 0}
        
        for download_key, status in self.download_status.items():
            if download_key.startswith(guild_prefix):
                if status in stats:
                    stats[status] += 1
        
        return stats
    
    def cancel_downloads(self, guild_id: int):
        """ギルドのすべてのダウンロードをキャンセル"""
        try:
            guild_prefix = f"{guild_id}_"
            cancelled_count = 0
            
            # ダウンロード中のスレッドをキャンセル（注意：Pythonではスレッドの強制終了は推奨されない）
            keys_to_remove = []
            for download_key in list(self.download_threads.keys()):
                if download_key.startswith(guild_prefix):
                    # スレッドの状態を失敗に変更してクリーンアップ
                    self.download_status[download_key] = 'failed'
                    keys_to_remove.append(download_key)
                    cancelled_count += 1
            
            # データをクリーンアップ
            for key in keys_to_remove:
                if key in self.download_status:
                    del self.download_status[key]
                if key in self.preload_tracks:
                    del self.preload_tracks[key]
                if key in self.download_threads:
                    del self.download_threads[key]
            
            if cancelled_count > 0:
                logger.info(f"Cancelled {cancelled_count} downloads for guild {guild_id}")
                
        except Exception as e:
            logger.error(f"Failed to cancel downloads for guild {guild_id}: {e}")
    
    def get_guild_stats(self, guild_id: int) -> dict:
        """ギルドの統計情報を取得"""
        download_stats = self.get_download_stats(guild_id)
        return {
            'queue_length': self.get_queue_length(guild_id),
            'is_playing': self.is_playing(guild_id),
            'current_track': self.get_now_playing(guild_id),
            'has_queue': self.has_queue(guild_id),
            'loop_enabled': self.is_loop_enabled(guild_id),
            'downloads': download_stats
        }
    
    def start_idle_timeout(self, guild_id: int, voice_client):
        """アイドルタイムアウトを開始"""
        try:
            # 既存のタイムアウトタスクをキャンセル
            self.cancel_idle_timeout(guild_id)
            
            async def timeout_task():
                try:
                    logger.info(f"Starting idle timeout for guild {guild_id} ({self.idle_timeout_duration} seconds)")
                    await asyncio.sleep(self.idle_timeout_duration)
                    
                    # タイムアウト後、キューが空で再生中でない場合は切断
                    if not self.has_queue(guild_id) and not self.is_playing(guild_id):
                        if voice_client and voice_client.is_connected():
                            logger.info(f"Idle timeout reached for guild {guild_id}, disconnecting...")
                            
                            # 切断通知を送信
                            await self._send_disconnect_notification(guild_id, voice_client)
                            
                            # ボイスチャンネルから切断
                            await voice_client.disconnect()
                            
                            # ギルドデータをクリーンアップ
                            self.remove_guild_data(guild_id)
                            
                            # 事前ダウンロードもキャンセル
                            self.cancel_downloads(guild_id)
                    
                    # タスクを削除
                    if guild_id in self.idle_timeout_tasks:
                        del self.idle_timeout_tasks[guild_id]
                    
                    # タスク管理システムからも削除
                    task_id = f"guild_{guild_id}_idle_timeout"
                    if task_id in self.active_tasks:
                        del self.active_tasks[task_id]
                        
                except asyncio.CancelledError:
                    logger.debug(f"Idle timeout cancelled for guild {guild_id}")
                    # キャンセル時もクリーンアップ
                    if guild_id in self.idle_timeout_tasks:
                        del self.idle_timeout_tasks[guild_id]
                    raise  # CancelledErrorは再発生させる
                except Exception as e:
                    logger.error(f"Error in idle timeout task for guild {guild_id}: {e}")
                    # エラー時もタスクを削除
                    if guild_id in self.idle_timeout_tasks:
                        del self.idle_timeout_tasks[guild_id]
            
            # タイムアウトタスクを開始
            task = asyncio.create_task(timeout_task())
            self.idle_timeout_tasks[guild_id] = task
            
            # タスク管理システムに登録
            task_id = f"guild_{guild_id}_idle_timeout"
            self.register_task(task_id, task)
            
        except Exception as e:
            logger.error(f"Failed to start idle timeout for guild {guild_id}: {e}")
    
    def cancel_idle_timeout(self, guild_id: int):
        """アイドルタイムアウトをキャンセル"""
        try:
            if guild_id in self.idle_timeout_tasks:
                task = self.idle_timeout_tasks[guild_id]
                task.cancel()
                del self.idle_timeout_tasks[guild_id]
                logger.debug(f"Cancelled idle timeout for guild {guild_id}")
                
                # タスク管理システムからもキャンセル
                task_id = f"guild_{guild_id}_idle_timeout"
                self.cancel_task(task_id)
        except Exception as e:
            logger.error(f"Failed to cancel idle timeout for guild {guild_id}: {e}")
    
    def is_idle_timeout_active(self, guild_id: int) -> bool:
        """アイドルタイムアウトが有効かどうかを確認"""
        return guild_id in self.idle_timeout_tasks and not self.idle_timeout_tasks[guild_id].done()
    
    async def _send_disconnect_notification(self, guild_id: int, voice_client):
        """切断通知を送信"""
        try:
            # 保存されているテキストチャンネルIDを取得
            text_channel_id = self.get_text_channel(guild_id)
            if not text_channel_id:
                logger.debug(f"No text channel saved for guild {guild_id}, skipping notification")
                return
            
            # テキストチャンネルを取得
            channel = voice_client.guild.get_channel(text_channel_id)
            if not channel:
                logger.warning(f"Text channel {text_channel_id} not found for guild {guild_id}")
                return
            
            # メッセージ送信権限をチェック
            if not channel.permissions_for(voice_client.guild.me).send_messages:
                logger.warning(f"No permission to send messages in channel {text_channel_id}")
                return
            
            # 切断通知の埋め込みメッセージを作成
            import discord
            embed = discord.Embed(
                title="💤 自動切断",
                description="5分間アクティビティがなかったため、ボイスチャンネルから自動的に切断しました。",
                color=discord.Color.orange()
            )
            embed.add_field(
                name="💡 ヒント",
                value="再度音楽を聴くには `/play` コマンドをご利用ください。",
                inline=False
            )
            embed.set_footer(text="音楽ボット • アイドルタイムアウト")
            
            # 通知を送信（安全な非同期実行）
            async def send_disconnect_notification():
                try:
                    await asyncio.wait_for(channel.send(embed=embed), timeout=15.0)
                    logger.info(f"Sent disconnect notification to channel {text_channel_id} for guild {guild_id}")
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout sending disconnect notification to channel {text_channel_id}")
                except discord.HTTPException as e:
                    logger.warning(f"HTTP error sending disconnect notification: {e}")
                except discord.Forbidden:
                    logger.warning(f"No permission to send disconnect notification in channel {text_channel_id}")
                except Exception as e:
                    logger.error(f"Error sending disconnect notification: {e}")
            
            # バックグラウンドで通知を送信
            import time
            task_id = f"guild_{guild_id}_disconnect_notification_{int(time.time() * 1000)}"
            task = asyncio.create_task(send_disconnect_notification())
            # 切断時は自分で管理する（selfが利用できない可能性があるため）
            def cleanup_notification_task(task):
                try:
                    logger.debug(f"Disconnect notification task completed: {task_id}")
                except Exception:
                    pass
            task.add_done_callback(cleanup_notification_task)
            
        except Exception as e:
            logger.error(f"Failed to send disconnect notification for guild {guild_id}: {e}")
    
    def toggle_loop(self, guild_id: int) -> bool:
        """ループを切り替える"""
        current_status = self.loop_enabled.get(guild_id, False)
        new_status = not current_status
        self.loop_enabled[guild_id] = new_status
        logger.info(f"Loop toggled for guild {guild_id}: {new_status}")
        return new_status
    
    def set_loop(self, guild_id: int, enabled: bool):
        """ループの状態を設定"""
        self.loop_enabled[guild_id] = enabled
        logger.info(f"Loop set for guild {guild_id}: {enabled}")
    
    def is_loop_enabled(self, guild_id: int) -> bool:
        """ループが有効かどうかを確認"""
        return self.loop_enabled.get(guild_id, False)
    
    async def get_playback_lock(self, guild_id: int) -> asyncio.Lock:
        """ギルドの再生ロックを取得"""
        if guild_id not in self.playback_locks:
            self.playback_locks[guild_id] = asyncio.Lock()
        return self.playback_locks[guild_id]
    
    def add_pending_request(self, guild_id: int, track_info: TrackInfo):
        """同時再生リクエストを保留に追加"""
        if guild_id not in self.pending_requests:
            self.pending_requests[guild_id] = []
        self.pending_requests[guild_id].append(track_info)
        logger.info(f"Added pending request for guild {guild_id}: {track_info.title}")
    
    def get_pending_requests(self, guild_id: int) -> List[TrackInfo]:
        """保留中のリクエストを取得"""
        return self.pending_requests.get(guild_id, [])
    
    def clear_pending_requests(self, guild_id: int):
        """保留中のリクエストをクリア"""
        if guild_id in self.pending_requests:
            del self.pending_requests[guild_id]
            logger.info(f"Cleared pending requests for guild {guild_id}")
    
    def move_pending_to_queue(self, guild_id: int, exclude_track: 'TrackInfo' = None):
        """保留中のリクエストをキューに移動（指定した曲は除く）"""
        if guild_id in self.pending_requests:
            pending = self.pending_requests[guild_id]
            if pending:
                moved_count = 0
                for track in pending:
                    # 勝者の曲は除外してキューに移動
                    if exclude_track is None or track.url != exclude_track.url:
                        self.add_track(guild_id, track)
                        moved_count += 1
                if moved_count > 0:
                    logger.info(f"Moved {moved_count} pending tracks to queue for guild {guild_id}")
                self.clear_pending_requests(guild_id)
    
    def is_starting_playback_active(self, guild_id: int) -> bool:
        """再生開始処理中かどうかを確認"""
        return self.is_starting_playback.get(guild_id, False)
    
    def set_starting_playback(self, guild_id: int, is_starting: bool):
        """再生開始処理の状態を設定"""
        self.is_starting_playback[guild_id] = is_starting
        if is_starting:
            logger.debug(f"Started playback initialization for guild {guild_id}")
        else:
            logger.debug(f"Finished playback initialization for guild {guild_id}")
    
    def register_task(self, task_id: str, task: asyncio.Task):
        """タスクを登録して管理"""
        self.active_tasks[task_id] = task
        logger.debug(f"Registered task: {task_id}")
        
        # タスク完了時の自動クリーンアップ
        def cleanup_task(task):
            try:
                if task_id in self.active_tasks:
                    del self.active_tasks[task_id]
                    logger.debug(f"Auto-cleaned up completed task: {task_id}")
            except Exception as e:
                logger.error(f"Error cleaning up task {task_id}: {e}")
        
        task.add_done_callback(cleanup_task)
        return task
    
    def cancel_task(self, task_id: str):
        """タスクをキャンセル"""
        if task_id in self.active_tasks:
            task = self.active_tasks[task_id]
            if not task.done():
                task.cancel()
                logger.debug(f"Cancelled task: {task_id}")
            del self.active_tasks[task_id]
    
    def cancel_guild_tasks(self, guild_id: int):
        """ギルドに関連するすべてのタスクをキャンセル"""
        guild_prefix = f"guild_{guild_id}_"
        tasks_to_cancel = [task_id for task_id in self.active_tasks.keys() if task_id.startswith(guild_prefix)]
        
        for task_id in tasks_to_cancel:
            self.cancel_task(task_id)
        
        if tasks_to_cancel:
            logger.info(f"Cancelled {len(tasks_to_cancel)} tasks for guild {guild_id}")
    
    def cancel_all_tasks(self):
        """すべてのアクティブタスクをキャンセル"""
        # 一般的なタスクをキャンセル
        task_count = len(self.active_tasks)
        for task_id in list(self.active_tasks.keys()):
            self.cancel_task(task_id)
        
        # アイドルタイムアウトタスクもすべてキャンセル
        idle_timeout_count = len(self.idle_timeout_tasks)
        for guild_id in list(self.idle_timeout_tasks.keys()):
            self.cancel_idle_timeout(guild_id)
        
        total_cancelled = task_count + idle_timeout_count
        if total_cancelled > 0:
            logger.info(f"Cancelled {total_cancelled} active tasks ({task_count} general + {idle_timeout_count} idle timeout)")
