"""
YouTube URL処理

URL正規化とタイトル取得機能
"""

import logging
import platform
from ..utils.subprocess_utils import safe_subprocess_run

logger = logging.getLogger(__name__)

def normalize_youtube_url(url: str) -> str:
    """
    YouTube URLを標準形式に正規化する
    
    Args:
        url (str): 入力されたURL
        
    Returns:
        str: 正規化されたURL、無効な場合はNone
    """
    try:
        # youtu.be形式を標準形式に変換
        if 'youtu.be/' in url:
            video_id = url.split('youtu.be/')[-1].split('?')[0]
            return f"https://www.youtube.com/watch?v={video_id}"
        
        # 埋め込み形式を標準形式に変換
        if '/embed/' in url:
            video_id = url.split('/embed/')[-1].split('?')[0]
            return f"https://www.youtube.com/watch?v={video_id}"
        
        # 標準形式の場合はそのまま返す
        if 'youtube.com/watch' in url:
            return url
        
        return None
    except Exception as e:
        logger.error(f"Failed to normalize URL {url}: {e}")
        return None

def generate_title_from_url(url: str) -> str:
    """
    YouTube URLからタイトルを生成する
    
    Args:
        url (str): YouTube URL
        
    Returns:
        str: 生成されたタイトル
    """
    try:
        # YouTube URLの形式をチェック
        if 'youtube.com/watch?v=' in url:
            video_id = url.split('v=')[1].split('&')[0]
            return f"YouTube動画 (ID: {video_id})"
        elif 'youtu.be/' in url:
            video_id = url.split('youtu.be/')[1].split('?')[0]
            return f"YouTube動画 (ID: {video_id})"
        elif '/embed/' in url:
            video_id = url.split('/embed/')[-1].split('?')[0]
            return f"YouTube動画 (ID: {video_id})"
        else:
            return "YouTube動画（タイトル取得不可）"
    except Exception:
        return "YouTube動画（タイトル取得不可）"

def get_title_from_url(url: str) -> str:
    """
    YouTube URLからタイトルを取得する
    
    Args:
        url (str): YouTube URL
        
    Returns:
        str: 取得されたタイトル、失敗時はURLから生成されたタイトル
    """
    try:
        # 統合されたYouTubeDownloaderクラスを使用
        from .downloader import YouTubeDownloader
        
        downloader = YouTubeDownloader()
        title = downloader.get_video_title(url)
        
        if title and title != "YouTube動画（タイトル取得不可）":
            logger.info(f"Retrieved video title from URL: {title}")
            return title
        else:
            logger.warning("Could not retrieve video title, using fallback")
            return generate_title_from_url(url)
            
    except Exception as e:
        logger.warning(f"Failed to get video title from URL: {e}")
        # エラーが発生した場合、URLからビデオIDを抽出してタイトルを生成
        return generate_title_from_url(url)

def is_playlist_url(url: str) -> bool:
    """
    プレイリストURLかどうかを判定
    
    Args:
        url (str): チェックするURL
        
    Returns:
        bool: プレイリストURLかどうか
    """
    playlist_patterns = [
        'playlist?list=',
        '&list=',
        '/playlist?list='
    ]
    
    return any(pattern in url for pattern in playlist_patterns)

def validate_youtube_url(url: str) -> bool:
    """
    YouTube URLの妥当性をチェック
    
    Args:
        url (str): チェックするURL
        
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
