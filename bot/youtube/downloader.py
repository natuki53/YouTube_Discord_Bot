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
import shutil
from pathlib import Path
from typing import Optional
from ..utils.subprocess_utils import safe_subprocess_run

logger = logging.getLogger(__name__)

class YouTubeDownloader:
    """YouTube動画/音声ダウンローダー（統合版）"""
    
    # クラス変数でダウンロード状況を管理
    _download_locks = {}
    _download_status = {}
    _lock = threading.Lock()
    # タイトル取得の簡易キャッシュ（yt-dlp呼び出し削減で高速化）
    _title_cache = {}  # url -> (timestamp, title)
    _title_cache_ttl = 3600  # 1時間
    
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

    def _get_yt_dlp_extra_args(self) -> list:
        """
        .env / 環境変数で指定された yt-dlp の追加引数を生成
        - FFMPEG_LOCATION: ffmpeg/ffprobe の場所
        - YT_DLP_JS_RUNTIMES: YouTube抽出用 JS runtime (例: deno / node)
        """
        extra = []

        js_runtimes = os.getenv("YT_DLP_JS_RUNTIMES")
        if js_runtimes:
            extra += ["--js-runtimes", js_runtimes]

        ffmpeg_location = os.getenv("FFMPEG_LOCATION")
        if ffmpeg_location:
            extra += ["--ffmpeg-location", ffmpeg_location]

        return extra

    def _has_ffmpeg(self) -> bool:
        """ffmpeg が利用可能か簡易チェック（PATH or FFMPEG_LOCATION）"""
        ffmpeg_location = os.getenv("FFMPEG_LOCATION")
        if ffmpeg_location:
            p = Path(ffmpeg_location)
            if p.is_dir():
                return (p / "ffmpeg.exe").exists() or (p / "ffmpeg").exists()
            return p.exists()
        return shutil.which("ffmpeg") is not None
    
    def download_mp3(self, url: str, quality: str = "320", filename_template: str = None) -> tuple:
        """
        YouTube動画をMP3に変換してダウンロード
        
        Args:
            url: YouTube URL
            quality: MP3音質（kbps）
            filename_template: ファイル名テンプレート（Noneの場合はデフォルトテンプレートを使用）
            
        Returns:
            tuple: (bool, str) - (ダウンロード成功可否, 動画タイトル)
        """
        # URLのハッシュをキーとして使用（プロセス内での一意性用途）
        url_key = str(hash(url))
        try:
            if not self.check_yt_dlp():
                return False, "Unknown Title"

            if not self._has_ffmpeg():
                logger.error("FFmpeg/ffprobe が見つからないため、MP3変換ができません。FFmpeg をインストールするか FFMPEG_LOCATION を設定してください。")
                return False, "Unknown Title"
            
            # ダウンロード競合をチェック
            with self._lock:
                if url_key in self._download_status:
                    status = self._download_status[url_key]
                    if status == 'downloading':
                        logger.info(f"URL already being downloaded, waiting: {url}")
                        # 他のダウンロードの完了を待つ
                        return self._wait_for_download_completion(url_key, url)
                    elif status == 'completed':
                        logger.info(f"URL already downloaded (in memory): {url}")
                        return True, self.get_video_title(url)
                
                # ダウンロード開始をマーク
                self._download_status[url_key] = 'downloading'
                self._download_locks[url_key] = threading.Event()
            
            # 既存ファイルをチェック（ダウンロード前に確認）
            existing_file = self.get_latest_mp3_file(url)
            if existing_file and os.path.exists(existing_file):
                logger.info(f"File already exists, skipping download: {existing_file}")
                # ダウンロード状況を更新（既存ファイルを使用）
                with self._lock:
                    self._download_status[url_key] = 'completed'
                    if url_key in self._download_locks:
                        self._download_locks[url_key].set()
                video_title = self.get_video_title(url)
                return True, video_title
            
            logger.info(f"Starting MP3 download: {url} ({quality}kbps)")
            
            # まずタイトルを取得
            video_title = self.get_video_title(url)
            
            # 出力ファイル名のテンプレート
            if filename_template is None:
                # デフォルトテンプレート: %(title).50s でタイトルを50文字に制限（日本語も含む）
                # Windowsでの禁止文字はyt-dlpが自動的に処理
                output_template = str(Path(self.download_dir) / "%(title).50s [%(id)s].%(ext)s")
            else:
                # カスタムテンプレートを使用
                output_template = str(Path(self.download_dir) / filename_template)
            
            cmd = [
                self.yt_dlp_path,
                *self._get_yt_dlp_extra_args(),
                '--extract-audio',
                '--audio-format', 'mp3',
                '--audio-quality', quality,
                '--embed-thumbnail',
                '--output', output_template,
                '--no-playlist',
                '--write-info-json',  # 情報ファイルも出力
                '--no-mtime',  # ファイルタイムスタンプを変更しない
                '--no-overwrites',  # 既存ファイルを上書きしない（重複ダウンロード防止）
                '--windows-filenames',  # Windows用のファイル名サニタイズ（禁止文字を除去、日本語は保持）
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
            logger.exception("MP3 download error")
            # エラー時も待機中スレッドに通知（例外箇所によってはurl_keyが未定義になり得るため先に定義済み）
            with self._lock:
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
            # キャッシュ（プロセス内）
            try:
                with self._lock:
                    cached = self._title_cache.get(url)
                    if cached:
                        ts, title = cached
                        if (time.time() - ts) < self._title_cache_ttl and title:
                            return title
                        else:
                            self._title_cache.pop(url, None)
            except Exception:
                pass

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
                try:
                    with self._lock:
                        self._title_cache[url] = (time.time(), title)
                except Exception:
                    pass
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
    
    # ストリーミング再生機能は廃止（安定性重視でダウンロード完了後にファイル再生へ統一）
    
    def get_playlist_video_urls(self, playlist_url: str, limit: int = None) -> list:
        """
        プレイリスト内の動画URLを取得
        
        Args:
            playlist_url: YouTubeプレイリストのURL
            limit: 取得する動画数の制限（Noneの場合はすべて）
            
        Returns:
            list: 動画URLのリスト
        """
        try:
            if not self.check_yt_dlp():
                return []
            
            logger.info(f"Getting video URLs from playlist: {playlist_url}")
            
            # プレイリストから動画URLを取得
            cmd = [
                self.yt_dlp_path,
                '--flat-playlist',
                '--get-url',
                playlist_url
            ]
            
            # 制限がある場合は追加（先頭からN件）
            if limit:
                cmd.extend(['--playlist-items', f'1-{limit}'])
            
            result = safe_subprocess_run(cmd, capture_output=True, text=True, timeout=60)
            
            if result and result.returncode == 0 and result.stdout:
                # 出力からURLを抽出（1行1URL）
                urls = [url.strip() for url in result.stdout.strip().split('\n') if url.strip()]
                logger.info(f"Retrieved {len(urls)} video URLs from playlist")
                return urls
            else:
                error_msg = result.stderr if result and result.stderr else "Unknown error"
                logger.error(f"Failed to get playlist video URLs: {error_msg}")
                return []
                
        except Exception as e:
            logger.exception("Error getting playlist video URLs")
            return []

    def get_playlist_video_urls_range(self, playlist_url: str, start_index: int, end_index: int) -> list:
        """
        プレイリスト内の動画URLを指定範囲だけ取得（1ベースのインデックス）。
        巨大プレイリスト/ミックスで全件取得すると非常に遅くメモリも増えるため、必要分だけ取得する。

        Args:
            playlist_url: YouTubeプレイリストURL
            start_index: 開始インデックス（1ベース）
            end_index: 終了インデックス（1ベース、start_index以上）

        Returns:
            list: 動画URLのリスト（取得できた分のみ）
        """
        try:
            if not self.check_yt_dlp():
                return []

            if start_index < 1:
                start_index = 1
            if end_index < start_index:
                end_index = start_index

            playlist_items = f"{start_index}-{end_index}"
            logger.info(f"Getting video URLs from playlist range {playlist_items}: {playlist_url}")

            cmd = [
                self.yt_dlp_path,
                '--flat-playlist',
                '--get-url',
                '--playlist-items', playlist_items,
                playlist_url
            ]

            result = safe_subprocess_run(cmd, capture_output=True, text=True, timeout=60)

            if result and result.returncode == 0 and result.stdout:
                urls = [u.strip() for u in result.stdout.strip().split('\n') if u.strip()]
                logger.info(f"Retrieved {len(urls)} video URLs from playlist range {playlist_items}")
                return urls

            error_msg = result.stderr if result and result.stderr else "Unknown error"
            logger.error(f"Failed to get playlist video URLs (range {playlist_items}): {error_msg}")
            return []
        except Exception:
            logger.exception("Error getting playlist video URLs range")
            return []
    
    def get_playlist_info(self, playlist_url: str) -> dict:
        """
        プレイリストの情報を取得（動画数など）
        
        Args:
            playlist_url: YouTubeプレイリストのURL
            
        Returns:
            dict: プレイリスト情報（video_count, titleなど）
        """
        try:
            if not self.check_yt_dlp():
                return {'video_count': 0, 'title': 'Unknown Playlist'}
            
            logger.info(f"Getting playlist info: {playlist_url}")
            
            # プレイリスト情報を取得
            cmd = [
                self.yt_dlp_path,
                '--flat-playlist',
                '--print', '%(playlist_count)s',
                '--print', '%(playlist_title)s',
                playlist_url
            ]
            
            result = safe_subprocess_run(cmd, capture_output=True, text=True, timeout=30)
            
            if result and result.returncode == 0 and result.stdout:
                lines = result.stdout.strip().split('\n')
                video_count = 0
                title = 'Unknown Playlist'
                
                # 出力から情報を抽出
                for line in lines:
                    line = line.strip()
                    if line.isdigit():
                        video_count = int(line)
                    elif line and not line.isdigit():
                        title = line
                
                logger.info(f"Playlist info: {title} ({video_count} videos)")
                return {
                    'video_count': video_count,
                    'title': title
                }
            else:
                logger.warning("Could not get playlist info, using defaults")
                return {'video_count': 0, 'title': 'Unknown Playlist'}
                
        except Exception as e:
            logger.exception("Error getting playlist info")
            return {'video_count': 0, 'title': 'Unknown Playlist'}
    
    def get_latest_mp3_file(self, url: str = None) -> str:
        """
        最新のMP3ファイルを取得
        
        Args:
            url: YouTube URL（指定された場合、そのURLに対応するファイルを検索）
            
        Returns:
            str: ファイルパス、見つからない場合はNone
        """
        try:
            mp3_files = list(Path(self.download_dir).glob("**/*.mp3"))  # 再帰検索
            logger.debug(f"Found {len(mp3_files)} MP3 files in {self.download_dir}")
            
            if not mp3_files:
                logger.warning(f"No MP3 files found in {self.download_dir}")
                return None
            
            # URLが指定された場合、そのURLに対応するファイルを検索
            # ※ ここで見つからない場合に「最新の別MP3」を返すと、別動画のファイルを誤って使ってしまい
            #    再生/キューの崩壊や「同じ曲が最初から」などの不具合原因になるため、必ず None を返す。
            if url:
                video_id = self._extract_video_id(url)
                if video_id:
                    logger.debug(f"Searching for file with video ID: {video_id}")
                    # ファイル名に動画IDが含まれるファイルを検索
                    matching_files = [f for f in mp3_files if f"[{video_id}]" in f.name]
                    if matching_files:
                        # 複数見つかった場合は最新のものを返す
                        latest_file = max(matching_files, key=lambda x: x.stat().st_mtime)
                        logger.info(f"Found MP3 file for video ID {video_id}: {latest_file}")
                        return str(latest_file)
                    else:
                        # URL指定で一致するMP3が無い場合は None（誤って別MP3を返さない）
                        logger.debug(f"No MP3 file found with video ID: {video_id}")
                        return None
                # URLからIDが取れない場合も、誤ったファイル選択を避けるため None
                return None
            
            # URLが指定されていない場合、または見つからなかった場合は最新のファイルを返す
            latest_file = max(mp3_files, key=lambda x: x.stat().st_mtime)
            logger.info(f"Latest MP3 file: {latest_file}")
            return str(latest_file)
        except Exception as e:
            logger.exception("Failed to get latest MP3 file")
            return None
    
    def _extract_video_id(self, url: str) -> str:
        """URLから動画IDを抽出"""
        try:
            if 'youtube.com/watch?v=' in url:
                video_id = url.split('v=')[1].split('&')[0]
                return video_id
            elif 'youtu.be/' in url:
                video_id = url.split('youtu.be/')[1].split('?')[0]
                return video_id
            elif '/embed/' in url:
                video_id = url.split('/embed/')[-1].split('?')[0]
                return video_id
            return None
        except Exception:
            return None
    
    def get_file_size_mb(self, file_path: str) -> float:
        """ファイルサイズをMBで取得"""
        try:
            if os.path.exists(file_path):
                size_bytes = os.path.getsize(file_path)
                return size_bytes / (1024 * 1024)
            return 0.0
        except Exception as e:
            logger.exception("Failed to get file size for %s", file_path)
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
            logger.exception("Failed to cleanup file %s", file_path)
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

            if not self._has_ffmpeg():
                logger.error("FFmpeg/ffprobe が見つからないため、MP3変換ができません。FFmpeg をインストールするか FFMPEG_LOCATION を設定してください。")
                return False
            
            logger.info(f"Starting playlist MP3 download: {playlist_url}")
            
            output_template = str(Path(self.download_dir) / "%(playlist_id)s/%(title).50s [%(id)s].%(ext)s")
            
            cmd = [
                self.yt_dlp_path,
                *self._get_yt_dlp_extra_args(),
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
            logger.exception("Playlist MP3 download error")
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
            logger.exception("Get formats error")
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
            logger.exception("Error waiting for download completion")
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
            logger.exception("Error cleaning up download status")
    
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
