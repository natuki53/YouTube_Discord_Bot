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
            return f"YouTube Video ({video_id})"
        elif 'youtu.be/' in url:
            video_id = url.split('youtu.be/')[1].split('?')[0]
            return f"YouTube Video ({video_id})"
        elif '/embed/' in url:
            video_id = url.split('/embed/')[-1].split('?')[0]
            return f"YouTube Video ({video_id})"
        else:
            return "YouTube Video"
    except Exception:
        return "YouTube Video"

def get_title_from_url(url: str) -> str:
    """
    YouTube URLからタイトルを取得する
    
    Args:
        url (str): YouTube URL
        
    Returns:
        str: 取得されたタイトル、失敗時はURLから生成されたタイトル
    """
    try:
        # yt-dlpを使用して動画情報を取得（Windows環境でのエンコーディング問題を回避）
        cmd_args = ['yt-dlp', '--get-title', '--no-playlist', url]
        
        if platform.system() == 'Windows':
            # Windows環境では、より安全なエンコーディング設定を使用
            import os
            env = os.environ.copy()
            env.update({
                'PYTHONIOENCODING': 'utf-8',
                'PYTHONUTF8': '1',
                'PYTHONLEGACYWINDOWSSTDIO': 'utf-8',
                'PYTHONLEGACYWINDOWSFSENCODING': 'utf-8'
            })
            result = safe_subprocess_run(
                cmd_args,
                capture_output=True, 
                timeout=10,
                env=env
            )
        else:
            result = safe_subprocess_run(cmd_args, capture_output=True, timeout=10)
        
        if result and result.returncode == 0 and result.stdout and result.stdout.strip():
            title = result.stdout.strip()
            logger.info(f"Retrieved video title from URL: {title}")
            return title
        else:
            stderr_msg = result.stderr if result and result.stderr else 'No result or stderr'
            logger.warning(f"Could not retrieve video title from URL: {stderr_msg}")
            # yt-dlpが失敗した場合、URLからビデオIDを抽出してタイトルを生成
            return generate_title_from_url(url)
    except Exception as e:
        logger.warning(f"Failed to get video title from URL: {e}")
        # エラーが発生した場合、URLからビデオIDを抽出してタイトルを生成
        return generate_title_from_url(url)

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
        'https://youtube.com/embed/'
    ]
    
    return any(url.startswith(pattern) for pattern in youtube_patterns)
