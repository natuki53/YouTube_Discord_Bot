"""
YouTube ダウンローダー

YouTube動画とMP3のダウンロード機能を統合
"""

import sys
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class YouTubeDownloader:
    """YouTube動画/音声ダウンローダー"""
    
    def __init__(self, download_dir: str = "./downloads"):
        self.download_dir = download_dir
        Path(download_dir).mkdir(exist_ok=True)
        
        # YouTube_Downloaderのモジュールをインポート
        sys.path.append('./YouTube_Downloader')
        try:
            from youtube_video_downloader import YouTubeVideoDownloader
            from youtube_to_mp3 import YouTubeToMP3
            
            self.video_downloader = YouTubeVideoDownloader()
            self.mp3_downloader = YouTubeToMP3()
            logger.info("YouTube downloaders initialized successfully")
        except ImportError as e:
            logger.error(f"Failed to import YouTube downloaders: {e}")
            self.video_downloader = None
            self.mp3_downloader = None
    
    def download_video(self, url: str, quality: str = "720p") -> bool:
        """
        YouTube動画をダウンロード
        
        Args:
            url: YouTube URL
            quality: 動画品質
            
        Returns:
            bool: ダウンロード成功可否
        """
        try:
            if not self.video_downloader:
                logger.error("Video downloader not available")
                return False
            
            logger.info(f"Starting video download: {url} ({quality})")
            success = self.video_downloader.download_video(url, quality)
            
            if success:
                logger.info(f"Video download completed: {url}")
            else:
                logger.error(f"Video download failed: {url}")
            
            return success
            
        except Exception as e:
            logger.error(f"Video download error: {e}")
            return False
    
    def download_mp3(self, url: str) -> bool:
        """
        YouTube動画をMP3に変換してダウンロード
        
        Args:
            url: YouTube URL
            
        Returns:
            bool: ダウンロード成功可否
        """
        try:
            if not self.mp3_downloader:
                logger.error("MP3 downloader not available")
                return False
            
            logger.info(f"Starting MP3 download: {url}")
            success = self.mp3_downloader.download_mp3(url)
            
            if success:
                logger.info(f"MP3 download completed: {url}")
            else:
                logger.error(f"MP3 download failed: {url}")
            
            return success
            
        except Exception as e:
            logger.error(f"MP3 download error: {e}")
            return False
    
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
            mp3_files = list(Path(self.download_dir).glob("*.mp3"))
            if mp3_files:
                latest_file = max(mp3_files, key=lambda x: x.stat().st_mtime)
                return str(latest_file)
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
