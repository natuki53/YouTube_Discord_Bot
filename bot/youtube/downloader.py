"""
YouTube ダウンローダー

YouTube動画とMP3のダウンロード機能を統合
"""

import sys
import os
import logging
import re
import subprocess
import threading
import time
from pathlib import Path
from ..utils.subprocess_utils import safe_subprocess_run

logger = logging.getLogger(__name__)

class YouTubeDownloader:
    """YouTube動画/音声ダウンローダー（統合版）"""
    
    # クラス変数でダウンロード状況を管理
    _download_locks = {}
    _download_status = {}
    _lock = threading.Lock()
    
    def __init__(self, download_dir: str = "./downloads"):
        self.download_dir = download_dir
        Path(download_dir).mkdir(exist_ok=True)
        self.yt_dlp_path = None
        logger.info(f"YouTube downloader initialized with directory: {download_dir}")
    
    def check_yt_dlp(self) -> bool:
        """
        yt-dlpがインストールされているかチェック
        
        Returns:
            bool: yt-dlpが利用可能な場合True
        """
        # yt-dlpのパスを探す
        yt_dlp_paths = [
            'yt-dlp',  # PATHにある場合
            '/Users/natuki/Library/Python/3.9/bin/yt-dlp',  # macOSの一般的なパス
            '/usr/local/bin/yt-dlp',  # Homebrewのパス
            '/opt/homebrew/bin/yt-dlp'  # Apple Silicon MacのHomebrewパス
        ]
        
        for path in yt_dlp_paths:
            try:
                result = safe_subprocess_run([path, '--version'], capture_output=True, text=True)
                if result and result.returncode == 0:
                    logger.info(f"yt-dlp バージョン: {result.stdout.strip()}")
                    self.yt_dlp_path = path
                    return True
            except Exception:
                continue
        
        logger.error("yt-dlpがインストールされていません")
        return False
    
    def download_video(self, url: str, quality: str = "720p", format_id: str = None) -> bool:
        """
        YouTube動画をダウンロード
        
        Args:
            url: YouTube URL
            quality: 動画品質
            format_id: 特定の形式ID（オプション）
            
        Returns:
            bool: ダウンロード成功可否
        """
        try:
            if not self.check_yt_dlp():
                return False
            
            logger.info(f"Starting video download: {url} ({quality})")
            
            # 出力ファイル名のテンプレート
            output_template = str(Path(self.download_dir) / "%(title)s.%(ext)s")
            
            # 形式指定の処理
            if format_id:
                format_spec = format_id
                logger.info(f"カスタム形式ID: {format_id}")
            else:
                format_spec = "best"
                logger.info(f"画質 {quality} でダウンロード")
            
            cmd = [
                self.yt_dlp_path,
                '--format', format_spec,
                '--output', output_template,
                '--no-playlist',
                '--merge-output-format', 'mp4',
                url
            ]
            
            result = safe_subprocess_run(cmd, capture_output=True, text=True, timeout=300)
            
            if result and result.returncode == 0:
                logger.info(f"Video download completed: {url}")
                return True
            else:
                error_msg = result.stderr if result and result.stderr else "Unknown error"
                logger.error(f"Video download failed: {error_msg}")
                return False
            
        except Exception as e:
            logger.error(f"Video download error: {e}")
            return False
    
    def download_mp3(self, url: str, quality: str = "320") -> tuple:
        """
        YouTube動画をMP3に変換してダウンロード
        
        Args:
            url: YouTube URL
            quality: MP3音質（kbps）
            
        Returns:
            tuple: (bool, str) - (ダウンロード成功可否, 動画タイトル)
        """
        try:
            if not self.check_yt_dlp():
                return False, "Unknown Title"
            
            # URLのハッシュをキーとして使用
            url_key = str(hash(url))
            
            # ダウンロード競合をチェック
            with self._lock:
                if url_key in self._download_status:
                    status = self._download_status[url_key]
                    if status == 'downloading':
                        logger.info(f"URL already being downloaded, waiting: {url}")
                        # 他のダウンロードの完了を待つ
                        return self._wait_for_download_completion(url_key, url)
                    elif status == 'completed':
                        logger.info(f"URL already downloaded: {url}")
                        return True, self.get_video_title(url)
                
                # ダウンロード開始をマーク
                self._download_status[url_key] = 'downloading'
                self._download_locks[url_key] = threading.Event()
            
            logger.info(f"Starting MP3 download: {url} ({quality}kbps)")
            
            # まずタイトルを取得
            video_title = self.get_video_title(url)
            
            # 出力ファイル名のテンプレート
            output_template = str(Path(self.download_dir) / "%(title).50s [%(id)s].%(ext)s")
            
            cmd = [
                self.yt_dlp_path,
                '--extract-audio',
                '--audio-format', 'mp3',
                '--audio-quality', quality,
                '--embed-thumbnail',
                '--output', output_template,
                '--no-playlist',
                '--write-info-json',  # 情報ファイルも出力
                '--no-mtime',  # ファイルタイムスタンプを変更しない
                url
            ]
            
            result = safe_subprocess_run(cmd, capture_output=True, text=True, timeout=300)
            
            success = result and result.returncode == 0
            
            # ダウンロード状況を更新
            with self._lock:
                if success:
                    self._download_status[url_key] = 'completed'
                    logger.info(f"MP3 download completed: {video_title}")
                else:
                    self._download_status[url_key] = 'failed'
                    error_msg = result.stderr if result and result.stderr else "Unknown error"
                    logger.error(f"MP3 download failed: {error_msg}")
                
                # 待機中のスレッドに通知
                if url_key in self._download_locks:
                    self._download_locks[url_key].set()
                    
                # 完了または失敗したダウンロードのロックは一定時間後に自動クリーンアップ
                # （メモリリークを防ぐため）
                def cleanup_locks():
                    time.sleep(300)  # 5分後にクリーンアップ
                    with self._lock:
                        if url_key in self._download_locks:
                            del self._download_locks[url_key]
                            logger.debug(f"Cleaned up download lock for {url_key}")
                
                cleanup_thread = threading.Thread(target=cleanup_locks, daemon=True)
                cleanup_thread.start()
            
            return success, video_title
            
        except Exception as e:
            logger.error(f"MP3 download error: {e}")
            # エラー時も状況をクリーンアップ
            with self._lock:
                if url_key in self._download_status:
                    self._download_status[url_key] = 'failed'
                if url_key in self._download_locks:
                    self._download_locks[url_key].set()
            return False, "Unknown Title"
    
    def get_video_title(self, url: str) -> str:
        """
        YouTube URLからタイトルを取得
        
        Args:
            url: YouTube URL
            
        Returns:
            str: 動画タイトル、失敗時は生成されたタイトル
        """
        try:
            if not self.check_yt_dlp():
                return self._generate_title_from_url(url)
            
            # タイトル取得コマンドを実行
            title_cmd = [
                self.yt_dlp_path,
                '--get-title',
                '--no-playlist',
                url
            ]
            
            result = safe_subprocess_run(title_cmd, capture_output=True, text=True, timeout=10)
            
            if result and result.returncode == 0 and result.stdout and result.stdout.strip():
                title = result.stdout.strip()
                logger.info(f"Retrieved video title: {title}")
                return title
            else:
                logger.warning("Could not retrieve video title, using fallback")
                return self._generate_title_from_url(url)
                
        except Exception as e:
            logger.warning(f"Title retrieval error: {e}")
            return self._generate_title_from_url(url)
    
    def _generate_title_from_url(self, url: str) -> str:
        """URLから動画タイトルを生成"""
        try:
            if 'youtube.com/watch?v=' in url:
                video_id = url.split('v=')[1].split('&')[0]
                return f"YouTube動画 (ID: {video_id})"
            elif 'youtu.be/' in url:
                video_id = url.split('youtu.be/')[1].split('?')[0]
                return f"YouTube動画 (ID: {video_id})"
            else:
                return "YouTube動画（タイトル取得不可）"
        except Exception:
            return "YouTube動画（タイトル取得不可）"
    
    def get_latest_video_file(self) -> str:
        """最新の動画ファイルを取得"""
        try:
            video_files = list(Path(self.download_dir).glob("*.mp4"))
            if video_files:
                latest_file = max(video_files, key=lambda x: x.stat().st_mtime)
                return str(latest_file)
            return None
        except Exception as e:
            logger.error(f"Failed to get latest video file: {e}")
            return None
    
    def get_latest_mp3_file(self) -> str:
        """最新のMP3ファイルを取得"""
        try:
            mp3_files = list(Path(self.download_dir).glob("**/*.mp3"))  # 再帰検索
            logger.debug(f"Found {len(mp3_files)} MP3 files in {self.download_dir}")
            for file in mp3_files:
                logger.debug(f"  - {file}")
            
            if mp3_files:
                latest_file = max(mp3_files, key=lambda x: x.stat().st_mtime)
                logger.info(f"Latest MP3 file: {latest_file}")
                return str(latest_file)
            else:
                logger.warning(f"No MP3 files found in {self.download_dir}")
            return None
        except Exception as e:
            logger.error(f"Failed to get latest MP3 file: {e}")
            return None
    
    def get_file_size_mb(self, file_path: str) -> float:
        """ファイルサイズをMBで取得"""
        try:
            if os.path.exists(file_path):
                size_bytes = os.path.getsize(file_path)
                return size_bytes / (1024 * 1024)
            return 0.0
        except Exception as e:
            logger.error(f"Failed to get file size for {file_path}: {e}")
            return 0.0
    
    def cleanup_file(self, file_path: str) -> bool:
        """ファイルを削除"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Cleaned up file: {file_path}")
                return True
            return True  # ファイルが存在しない場合も成功とする
        except Exception as e:
            logger.error(f"Failed to cleanup file {file_path}: {e}")
            return False
    
    def download_playlist_mp3(self, playlist_url: str, quality: str = "320", limit: int = None) -> bool:
        """
        プレイリストからMP3をダウンロード
        
        Args:
            playlist_url: YouTubeプレイリストのURL
            quality: MP3音質（kbps）
            limit: ダウンロードする動画数の制限
            
        Returns:
            bool: ダウンロード成功可否
        """
        try:
            if not self.check_yt_dlp():
                return False
            
            logger.info(f"Starting playlist MP3 download: {playlist_url}")
            
            output_template = str(Path(self.download_dir) / "%(playlist_id)s/%(title).50s [%(id)s].%(ext)s")
            
            cmd = [
                self.yt_dlp_path,
                '--extract-audio',
                '--audio-format', 'mp3',
                '--audio-quality', quality,
                '--embed-thumbnail',
                '--output', output_template,
                playlist_url
            ]
            
            if limit:
                cmd.extend(['--playlist-items', f'1-{limit}'])
            
            result = safe_subprocess_run(cmd, capture_output=True, text=True, timeout=600)
            
            if result and result.returncode == 0:
                logger.info(f"Playlist MP3 download completed: {playlist_url}")
                return True
            else:
                error_msg = result.stderr if result and result.stderr else "Unknown error"
                logger.error(f"Playlist MP3 download failed: {error_msg}")
                return False
            
        except Exception as e:
            logger.error(f"Playlist MP3 download error: {e}")
            return False
    
    def get_available_formats(self, url: str) -> dict:
        """
        動画の利用可能な形式を取得
        
        Args:
            url: YouTube動画のURL
            
        Returns:
            dict: 形式情報
        """
        try:
            if not self.check_yt_dlp():
                return {}
            
            cmd = [self.yt_dlp_path, '--list-formats', url]
            result = safe_subprocess_run(cmd, capture_output=True, text=True, timeout=30)
            
            if result and result.returncode == 0:
                logger.info("Successfully retrieved format list")
                return {"output": result.stdout}
            else:
                error_msg = result.stderr if result and result.stderr else "Unknown error"
                logger.error(f"Failed to get formats: {error_msg}")
                return {}
                
        except Exception as e:
            logger.error(f"Get formats error: {e}")
            return {}
    
    def _wait_for_download_completion(self, url_key: str, url: str) -> tuple:
        """
        他のダウンロードの完了を待つ
        
        Args:
            url_key: URLのハッシュキー
            url: 元のURL
            
        Returns:
            tuple: (bool, str) - (ダウンロード成功可否, 動画タイトル)
        """
        try:
            # 最大90秒待機（より長い動画に対応）
            if url_key in self._download_locks:
                event = self._download_locks[url_key]
                # 10秒間隔でステータスをチェック
                for i in range(9):  # 90秒 / 10秒 = 9回
                    if event.wait(timeout=10):
                        # ダウンロード完了、結果を確認
                        status = self._download_status.get(url_key, 'failed')
                        if status == 'completed':
                            logger.info(f"Download completed successfully: {url}")
                            return True, self.get_video_title(url)
                        else:
                            logger.warning(f"Download failed: {url}")
                            return False, "Download failed"
                    else:
                        logger.debug(f"Still waiting for download... ({(i+1)*10}s elapsed)")
                
                logger.warning(f"Download timeout for URL after 90s: {url}")
                return False, "Download timeout"
            else:
                logger.error(f"Download lock not found for URL: {url}")
                return False, "Download status unknown"
        except Exception as e:
            logger.error(f"Error waiting for download completion: {e}")
            return False, "Wait error"
    
    def cleanup_download_status(self, url: str):
        """
        指定されたURLのダウンロード状況をクリーンアップ
        
        Args:
            url: YouTube URL
        """
        try:
            url_key = str(hash(url))
            with self._lock:
                if url_key in self._download_status:
                    del self._download_status[url_key]
                if url_key in self._download_locks:
                    del self._download_locks[url_key]
            logger.debug(f"Cleaned up download status for URL: {url}")
        except Exception as e:
            logger.error(f"Error cleaning up download status: {e}")
    
    @classmethod
    def get_download_status(cls, url: str) -> str:
        """
        URLのダウンロード状況を取得
        
        Args:
            url: YouTube URL
            
        Returns:
            str: ダウンロード状況 ('downloading', 'completed', 'failed', 'none')
        """
        url_key = str(hash(url))
        with cls._lock:
            return cls._download_status.get(url_key, 'none')
    
    def validate_youtube_url(self, url: str) -> bool:
        """
        YouTube URLの妥当性をチェック
        
        Args:
            url: チェックするURL
            
        Returns:
            bool: 有効なYouTube URLかどうか
        """
        youtube_patterns = [
            'https://www.youtube.com/watch',
            'https://youtube.com/watch', 
            'https://youtu.be/',
            'https://www.youtube.com/embed/',
            'https://youtube.com/embed/',
            'https://www.youtube.com/playlist',
            'https://youtube.com/playlist'
        ]
        
        return any(url.startswith(pattern) for pattern in youtube_patterns)
