"""
YouTube ダウンローダー - シンプル版
"""

import logging
import subprocess
import os
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class YouTubeDownloader:
    """YouTube動画・音声ダウンローダー"""
    
    def __init__(self, download_dir: str = "./downloads"):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(exist_ok=True)
        self.yt_dlp_path = self._find_yt_dlp()
        
    def _find_yt_dlp(self) -> Optional[str]:
        """yt-dlpのパスを探す"""
        possible_paths = [
            'yt-dlp',
            '/usr/local/bin/yt-dlp',
            '/opt/homebrew/bin/yt-dlp',
            '/Users/natuki/Library/Python/3.9/bin/yt-dlp'
        ]
        
        for path in possible_paths:
            try:
                result = subprocess.run(
                    [path, '--version'], 
                    capture_output=True, 
                    text=True, 
                    timeout=5
                )
                if result.returncode == 0:
                    logger.info(f"yt-dlp found: {path}")
                    return path
            except (subprocess.SubprocessError, FileNotFoundError):
                continue
        
        logger.error("yt-dlp not found")
        return None
    
    def download_audio(self, url: str) -> Tuple[bool, str, Optional[str]]:
        """
        YouTube URLから音声をダウンロード
        
        Returns:
            Tuple[bool, str, Optional[str]]: (成功フラグ, タイトル, ファイルパス)
        """
        if not self.yt_dlp_path:
            return False, "yt-dlp not available", None
        
        try:
            # 出力テンプレート
            output_template = str(self.download_dir / "%(title).50s_%(id)s.%(ext)s")
            
            # yt-dlpコマンド
            cmd = [
                self.yt_dlp_path,
                '--extract-audio',
                '--audio-format', 'mp3',
                '--audio-quality', '192',
                '--output', output_template,
                '--no-playlist',
                url
            ]
            
            logger.info(f"Downloading audio: {url}")
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=300
            )
            
            if result.returncode == 0:
                # ダウンロードされたファイルを探す
                audio_file = self._get_latest_audio_file()
                title = self._get_video_title(url)
                
                logger.info(f"Audio download completed: {title}")
                return True, title, audio_file
            else:
                logger.error(f"Audio download failed: {result.stderr}")
                return False, "Download failed", None
                
        except subprocess.TimeoutExpired:
            logger.error("Audio download timeout")
            return False, "Download timeout", None
        except Exception as e:
            logger.error(f"Audio download error: {e}")
            return False, str(e), None
    
    def download_video(self, url: str, quality: str = '720p') -> Tuple[bool, str, Optional[str]]:
        """
        YouTube URLから動画をダウンロード
        
        Returns:
            Tuple[bool, str, Optional[str]]: (成功フラグ, タイトル, ファイルパス)
        """
        if not self.yt_dlp_path:
            return False, "yt-dlp not available", None
        
        try:
            output_template = str(self.download_dir / "%(title).50s_%(id)s.%(ext)s")
            
            cmd = [
                self.yt_dlp_path,
                '--format', f'best[height<={quality[:-1]}]',
                '--output', output_template,
                '--merge-output-format', 'mp4',
                '--no-playlist',
                url
            ]
            
            logger.info(f"Downloading video: {url} ({quality})")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode == 0:
                video_file = self._get_latest_video_file()
                title = self._get_video_title(url)
                
                logger.info(f"Video download completed: {title}")
                return True, title, video_file
            else:
                logger.error(f"Video download failed: {result.stderr}")
                return False, "Download failed", None
                
        except subprocess.TimeoutExpired:
            logger.error("Video download timeout")
            return False, "Download timeout", None
        except Exception as e:
            logger.error(f"Video download error: {e}")
            return False, str(e), None
    
    def _get_video_title(self, url: str) -> str:
        """動画タイトルを取得"""
        if not self.yt_dlp_path:
            return "Unknown Title"
        
        try:
            cmd = [self.yt_dlp_path, '--get-title', '--no-playlist', url]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            
        except Exception as e:
            logger.warning(f"Title retrieval failed: {e}")
        
        return "Unknown Title"
    
    def _get_latest_audio_file(self) -> Optional[str]:
        """最新の音声ファイルを取得"""
        try:
            audio_files = list(self.download_dir.glob("*.mp3"))
            if audio_files:
                latest = max(audio_files, key=lambda x: x.stat().st_mtime)
                return str(latest)
        except Exception as e:
            logger.error(f"Failed to get latest audio file: {e}")
        return None
    
    def _get_latest_video_file(self) -> Optional[str]:
        """最新の動画ファイルを取得"""
        try:
            video_files = list(self.download_dir.glob("*.mp4"))
            if video_files:
                latest = max(video_files, key=lambda x: x.stat().st_mtime)
                return str(latest)
        except Exception as e:
            logger.error(f"Failed to get latest video file: {e}")
        return None
    
    def get_file_size_mb(self, file_path: str) -> float:
        """ファイルサイズ（MB）を取得"""
        try:
            if os.path.exists(file_path):
                size_bytes = os.path.getsize(file_path)
                return size_bytes / (1024 * 1024)
        except Exception as e:
            logger.error(f"Failed to get file size: {e}")
        return 0.0
    
    def cleanup_file(self, file_path: str) -> bool:
        """ファイルを削除"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Cleaned up file: {file_path}")
                return True
        except Exception as e:
            logger.error(f"Failed to cleanup file: {e}")
        return False
    
    def validate_youtube_url(self, url: str) -> bool:
        """YouTube URLの検証"""
        youtube_domains = [
            'youtube.com/watch',
            'youtu.be/',
            'youtube.com/embed',
            'youtube.com/playlist'
        ]
        return any(domain in url for domain in youtube_domains)
