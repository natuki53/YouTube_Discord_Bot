import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
import sys
import logging
from pathlib import Path

# Windows環境でのエンコーディング問題を解決
if os.name == 'nt':  # Windows
    import codecs
    import locale
    
    # 環境変数を強制的にUTF-8に設定
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['PYTHONUTF8'] = '1'
    os.environ['PYTHONLEGACYWINDOWSSTDIO'] = 'utf-8'
    os.environ['PYTHONLEGACYWINDOWSFSENCODING'] = 'utf-8'
    
    # コンソールのエンコーディングをUTF-8に設定
    try:
        if hasattr(sys.stdout, 'detach'):
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())
        if hasattr(sys.stderr, 'detach'):
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.detach())
    except Exception:
        pass
    
    # ロケール設定をUTF-8に変更
    try:
        locale.setlocale(locale.LC_ALL, 'C.UTF-8')
    except Exception:
        try:
            locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
        except Exception:
            pass

# クロスプラットフォーム対応のエンコーディング設定
def setup_encoding():
    """すべての環境でエンコーディング問題を回避する設定"""
    try:
        import platform
        
        # 環境変数を設定
        os.environ['PYTHONIOENCODING'] = 'utf-8'
        os.environ['PYTHONUTF8'] = '1'
        
        # Windows環境での追加設定
        if platform.system() == 'Windows':
            os.environ['PYTHONLEGACYWINDOWSSTDIO'] = 'utf-8'
            os.environ['PYTHONLEGACYWINDOWSFSENCODING'] = 'utf-8'
            # Windowsでのコンソールエンコーディングを設定
            try:
                import codecs
                sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())
                sys.stderr = codecs.getwriter('utf-8')(sys.stderr.detach())
            except Exception:
                pass
        
        # 標準出力と標準エラーのエンコーディングを設定
        if hasattr(sys.stdout, 'reconfigure'):
            try:
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            except Exception:
                pass
        if hasattr(sys.stderr, 'reconfigure'):
            try:
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')
            except Exception:
                pass
        
        # locale設定をUTF-8に変更（可能な場合）
        try:
            import locale
            if hasattr(locale, 'setlocale'):
                if platform.system() == 'Windows':
                    # WindowsではUTF-8ロケールを試行
                    try:
                        locale.setlocale(locale.LC_ALL, 'C.UTF-8')
                    except Exception:
                        try:
                            locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
                        except Exception:
                            pass
                else:
                    locale.setlocale(locale.LC_ALL, 'C.UTF-8')
        except Exception:
            pass
            
    except Exception as e:
        # エンコーディング設定に失敗しても続行
        pass

# エンコーディング設定を実行
setup_encoding()

# Windows環境での追加設定
if os.name == 'nt':  # Windows
    # システム全体のエンコーディングをUTF-8に設定
    import sys
    import codecs
    
    # 標準入出力のエンコーディングを強制的にUTF-8に設定
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    if hasattr(sys.stderr, 'reconfigure'):
        try:
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    
    # 環境変数をさらに設定
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['PYTHONUTF8'] = '1'
    os.environ['PYTHONLEGACYWINDOWSSTDIO'] = 'utf-8'
    os.environ['PYTHONLEGACYWINDOWSFSENCODING'] = 'utf-8'

def safe_subprocess_run(*args, **kwargs):
    """
    クロスプラットフォーム対応の安全なsubprocess.run呼び出し
    
    Args:
        *args: subprocess.runに渡す引数
        **kwargs: subprocess.runに渡すキーワード引数
        
    Returns:
        subprocess.CompletedProcess: 実行結果
    """
    try:
        import subprocess
        import platform
        
        # 環境変数を設定
        env = kwargs.get('env', os.environ.copy())
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUTF8'] = '1'
        
        # Windows環境での追加設定
        if platform.system() == 'Windows':
            env['PYTHONLEGACYWINDOWSSTDIO'] = 'utf-8'
            env['PYTHONLEGACYWINDOWSFSENCODING'] = 'utf-8'
            # Windowsでの追加環境変数
            env['PYTHONIOENCODING'] = 'utf-8'
            env['PYTHONUTF8'] = '1'
            # Windowsでの追加設定
            env['PYTHONLEGACYWINDOWSSTDIO'] = 'utf-8'
            env['PYTHONLEGACYWINDOWSFSENCODING'] = 'utf-8'
            # Windows用のstartupinfo設定
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            kwargs['startupinfo'] = startupinfo
        
        kwargs['env'] = env
        
        # エンコーディング設定を強制
        kwargs['encoding'] = 'utf-8'
        kwargs['errors'] = 'replace'
        
        # Windows環境での追加設定
        if platform.system() == 'Windows':
            # Windowsでは、より安全な設定を使用
            kwargs['text'] = True
            kwargs['universal_newlines'] = True
            # Windowsでの追加オプション
            kwargs['shell'] = False
            # 標準出力と標準エラー出力をパイプに設定
            kwargs['stdout'] = subprocess.PIPE
            kwargs['stderr'] = subprocess.PIPE
        
        # タイムアウトの設定（デフォルト30秒）
        if 'timeout' not in kwargs:
            kwargs['timeout'] = 30
            
        return subprocess.run(*args, **kwargs)
        
    except Exception as e:
        logger.error(f"Subprocess execution failed: {e}")
        # エラーが発生した場合、適切なエラーオブジェクトを返す
        from subprocess import CompletedProcess
        return CompletedProcess(args, returncode=-1, stdout=None, stderr=str(e))

# YouTube_Downloaderのモジュールをインポート
sys.path.append('./YouTube_Downloader')
from youtube_video_downloader import YouTubeVideoDownloader
from youtube_to_mp3 import YouTubeToMP3

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
        import subprocess
        import platform
        
        # Windows環境での追加オプション
        cmd_args = ['yt-dlp', '--get-title', '--no-playlist', url]
        if platform.system() == 'Windows':
            # Windows環境では、より安全なエンコーディング設定を使用
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

def normalize_youtube_url(url: str) -> str:
    """
    YouTube URLを標準形式に正規化する
    
    Args:
        url (str): 入力されたURL
        
    Returns:
        str: 正規化されたURL、無効な場合はNone
    """
    import re
    
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

# 設定をインポート
try:
    from config import *
except ImportError:
    # config.pyが存在しない場合のデフォルト設定
    DISCORD_TOKEN = 'your_discord_bot_token_here'
    BOT_PREFIX = '!'
    DOWNLOAD_DIR = './downloads'
    MAX_FILE_SIZE = 25
    SUPPORTED_QUALITIES = ['144p', '240p', '360p', '480p', '720p', '1080p']

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ボットの設定
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True
intents.voice_states = True

# ボットの作成（スラッシュコマンド用）
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)

# 音声再生の状態管理
current_audio_files = {}  # guild_id -> file_path

class AudioQueue:
    """音声キューを管理するクラス"""
    def __init__(self):
        self.queues = {}  # guild_id -> queue
        self.now_playing = {}  # guild_id -> current_track
    
    def add_track(self, guild_id: int, track_info: dict):
        """キューにトラックを追加"""
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        self.queues[guild_id].append(track_info)
        logger.info(f"Added track to queue for guild {guild_id}: {track_info.get('title', 'Unknown')}")
    
    def get_next_track(self, guild_id: int):
        """次のトラックを取得"""
        if guild_id in self.queues and self.queues[guild_id]:
            track = self.queues[guild_id].pop(0)
            self.now_playing[guild_id] = track
            logger.info(f"Next track for guild {guild_id}: {track.get('title', 'Unknown')}")
            return track
        return None
    
    def get_queue(self, guild_id: int):
        """キューの内容を取得"""
        if guild_id in self.queues:
            return self.queues[guild_id]
        return []
    
    def clear_queue(self, guild_id: int):
        """キューをクリア"""
        if guild_id in self.queues:
            self.queues[guild_id].clear()
            logger.info(f"Cleared queue for guild {guild_id}")
    
    def get_queue_length(self, guild_id: int):
        """キューの長さを取得"""
        if guild_id in self.queues:
            return len(self.queues[guild_id])
        return 0
    
    def is_playing(self, guild_id: int):
        """現在再生中かどうかを確認"""
        return guild_id in self.now_playing and self.now_playing[guild_id] is not None
    
    def get_now_playing(self, guild_id: int):
        """現在再生中のトラックを取得"""
        return self.now_playing.get(guild_id)
    
    def clear_now_playing(self, guild_id: int):
        """現在再生中のトラックをクリア"""
        if guild_id in self.now_playing:
            del self.now_playing[guild_id]
    
    def has_queue(self, guild_id: int):
        """キューに曲があるかどうかを確認"""
        return guild_id in self.queues and len(self.queues[guild_id]) > 0

# グローバルな音声キューインスタンス
audio_queue = AudioQueue()

async def download_and_play_track(guild_id: int, track_info: dict, voice_client, text_channel_id: int = None):
    """
    トラックをダウンロードして再生する関数
    
    Args:
        guild_id (int): ギルドID
        track_info (dict): トラック情報
        voice_client: ボイスクライアント
        text_channel_id (int, optional): テキストチャンネルID
    """
    # 既に再生中の場合は待機
    while voice_client and voice_client.is_playing():
        await asyncio.sleep(1)
        
    # ダウンロードの完了を待機
    url = track_info['url']
    download_key = f"{guild_id}_{url}"
    
    # ダウンロードの完了を最大30秒待機
    timeout = 30
    while timeout > 0:
        if hasattr(audio_queue, 'downloaded_tracks') and audio_queue.downloaded_tracks.get(download_key):
            break
        await asyncio.sleep(1)
        timeout -= 1
    
    if timeout <= 0:
        logger.error(f"Download timeout for track: {track_info.get('title', 'Unknown')}")
        return
    try:
        url = track_info['url']
        title = track_info.get('title', 'Unknown Track')
        

        
        logger.info(f"Downloading and playing track: {title}")
        
        # 音声ファイルをダウンロード
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(
            None, 
            mp3_downloader.download_mp3, 
            url
        )
        
        if success:
            # 最新のMP3ファイルを検索
            mp3_files = list(Path(DOWNLOAD_DIR).glob("*.mp3"))
            if mp3_files:
                latest_file = max(mp3_files, key=lambda x: x.stat().st_mtime)
                file_path = str(latest_file)
                
                # 音声ファイルの存在確認
                if not os.path.exists(file_path):
                    logger.error(f"Audio file not found: {file_path}")
                    return
                
                # ファイルサイズの確認
                file_size = os.path.getsize(file_path)
                if file_size == 0:
                    logger.error(f"Audio file is empty: {file_path}")
                    return
                
                logger.info(f"Playing track: {file_path} (size: {file_size} bytes)")
                
                # 音声を再生
                try:
                    # FFmpegオプションを設定
                    ffmpeg_options = {
                        'options': '-vn',
                        'before_options': '-y -nostdin -loglevel error -hide_banner -re'
                    }
                    
                    # 音声ソースを作成
                    audio_source = discord.FFmpegPCMAudio(file_path, **ffmpeg_options)
                    audio_source = discord.PCMVolumeTransformer(audio_source)
                    audio_source.volume = 0.5
                    
                    # 再生終了時のコールバックを設定
                    def after_playing_track(error):
                        if error:
                            logger.error(f"Track playback finished with error: {error}")
                        else:
                            logger.info("Track playback finished successfully")
                        
                        # メインイベントループで非同期処理を実行
                        future = asyncio.run_coroutine_threadsafe(handle_track_finish(error, file_path, guild_id, voice_client), bot.loop)
                        try:
                            # 結果を待機（タイムアウト5秒）
                            future.result(timeout=5)
                        except Exception as e:
                            logger.error(f"Error in after_playing_track: {e}")
                    
                    # 非同期のトラック終了ハンドラ
                    async def handle_track_finish(error, file_path, guild_id, voice_client):
                        try:
                            # ファイルを確実に削除
                            cleanup_audio_file(file_path, guild_id)
                            
                            # 現在再生中のトラックをクリア
                            audio_queue.clear_now_playing(guild_id)
                            
                            # キューから次の曲を取得
                            next_track = audio_queue.get_next_track(guild_id)
                            
                            if next_track:
                                logger.info(f"Playing next track from queue: {next_track.get('title', 'Unknown')}")
                                # 次の曲を再生
                                await download_and_play_track(guild_id, next_track, voice_client)
                            else:
                                logger.info("No more tracks in queue, disconnecting")
                                # キューが空の場合は切断
                                if voice_client and voice_client.is_connected():
                                    await voice_client.disconnect()
                                    logger.info("Disconnected from voice channel after queue finished")
                        except Exception as e:
                            logger.error(f"Error in handle_track_finish: {e}")
                    
                    # 再生開始
                    if voice_client and voice_client.is_connected():
                        voice_client.play(audio_source, after=after_playing_track)
                        current_audio_files[guild_id] = file_path
                        logger.info(f"Started playing track: {title}")
                        
                        # チャンネルに通知
                        try:
                            embed = discord.Embed(
                                title="🎵 再生開始",
                                description=f"**タイトル：** {title}\n\n**URL：** {url}\n\n**チャンネル：** {voice_client.channel.name if voice_client.channel else 'Unknown'}",
                                color=discord.Color.green()
                            )
                            embed.add_field(
                                name="🎵 ステータス",
                                value="音声を再生中...",
                                inline=False
                            )
                            # コマンドが実行されたテキストチャンネルに通知を送信
                            if text_channel_id:
                                try:
                                    text_channel = voice_client.guild.get_channel(text_channel_id)
                                    if text_channel and text_channel.permissions_for(voice_client.guild.me).send_messages:
                                        await text_channel.send(embed=embed)
                                    else:
                                        # 指定されたチャンネルが見つからない場合や権限がない場合は、最初の利用可能なチャンネルに送信
                                        guild = voice_client.guild
                                        for channel in guild.text_channels:
                                            if channel.permissions_for(guild.me).send_messages:
                                                await channel.send(embed=embed)
                                                break
                                except Exception as e:
                                    logger.error(f"Failed to send to specified channel: {e}")
                                    # フォールバック: 最初の利用可能なチャンネルに送信
                                    guild = voice_client.guild
                                    for channel in guild.text_channels:
                                        if channel.permissions_for(guild.me).send_messages:
                                            await channel.send(embed=embed)
                                            break
                            else:
                                # テキストチャンネルIDが指定されていない場合、最初の利用可能なチャンネルに送信
                                guild = voice_client.guild
                                for channel in guild.text_channels:
                                    if channel.permissions_for(guild.me).send_messages:
                                        await channel.send(embed=embed)
                                        break
                        except Exception as e:
                            logger.error(f"Failed to send track notification: {e}")
                    
                except Exception as e:
                    logger.error(f"Failed to play track: {e}")
                    cleanup_audio_file(file_path, guild_id)
                    
                    # エラー内容をEmbedボックスで表示
                    error_embed = discord.Embed(
                        title="❌ 音声再生エラー",
                        description=f"**{title}**\n\n📺 **URL:** {url}\n🎤 **チャンネル:** {voice_client.channel.name if voice_client.channel else 'Unknown'}",
                        color=discord.Color.red()
                    )
                    error_embed.add_field(
                        name="❌ エラー詳細",
                        value=f"音声の再生に失敗しました。\n\n**エラー内容:**\n```{str(e)}```",
                        inline=False
                    )
                    error_embed.add_field(
                        name="🔧 対処法",
                        value="• URLが正しいか確認してください\n• 動画が利用可能か確認してください\n• しばらく時間をおいて再試行してください",
                        inline=False
                    )
                    
                    # テキストチャンネルにエラーメッセージを送信
                    try:
                        guild = voice_client.guild
                        for channel in guild.text_channels:
                            if channel.permissions_for(guild.me).send_messages:
                                await channel.send(embed=error_embed)
                                break
                    except Exception as send_error:
                        logger.error(f"Failed to send error message: {send_error}")
                    
        else:
            logger.error(f"Failed to download track: {url}")
            
    except Exception as e:
        logger.error(f"Error in download_and_play_track: {e}")

def cleanup_audio_file(file_path: str, guild_id: int):
    """音声ファイルを確実に削除するヘルパー関数"""
    try:
        # ファイルが存在するか確認
        if os.path.exists(file_path):
            # ファイルを削除
            os.remove(file_path)
            logger.info(f"✅ Cleaned up audio file: {file_path}")
            
            # 記録からも削除
            if guild_id in current_audio_files:
                del current_audio_files[guild_id]
                logger.info(f"✅ Removed audio file record for guild: {guild_id}")
        else:
            logger.info(f"Audio file already removed: {file_path}")
            
    except PermissionError:
        logger.warning(f"Permission denied when trying to delete: {file_path}")
        # 少し待ってから再試行
        import time
        time.sleep(1)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"✅ Cleaned up audio file on retry: {file_path}")
        except Exception as e:
            logger.error(f"Failed to delete file on retry: {e}")
            
    except Exception as e:
        logger.error(f"Failed to cleanup audio file: {e}")
        # 最終手段：ファイルパスを記録して後で削除を試行
        logger.warning(f"File {file_path} will be cleaned up later")

async def play_next_track(guild, track_info):
    """キューから次の曲を再生する関数"""
    try:
        url = track_info['url']
        title = track_info.get('title', 'Unknown Track')
        
        logger.info(f"Playing next track from queue: {title}")
        
        # 音声ファイルをダウンロード
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(
            None, 
            mp3_downloader.download_mp3, 
            url
        )
        
        if success:
            # 最新のMP3ファイルを検索
            mp3_files = list(Path(DOWNLOAD_DIR).glob("*.mp3"))
            if mp3_files:
                latest_file = max(mp3_files, key=lambda x: x.stat().st_mtime)
                file_path = str(latest_file)
                
                # 音声ファイルの存在確認
                if not os.path.exists(file_path):
                    logger.error(f"Audio file not found: {file_path}")
                    return
                
                # ファイルサイズの確認
                file_size = os.path.getsize(file_path)
                if file_size == 0:
                    logger.error(f"Audio file is empty: {file_path}")
                    return
                
                logger.info(f"Playing next track: {file_path} (size: {file_size} bytes)")
                
                # 音声を再生
                try:
                    # FFmpegオプションを設定
                    ffmpeg_options = {
                        'options': '-vn',
                        'before_options': '-y -nostdin -loglevel error -hide_banner -re'
                    }
                    
                    # 音声ソースを作成
                    audio_source = discord.FFmpegPCMAudio(file_path, **ffmpeg_options)
                    audio_source = discord.PCMVolumeTransformer(audio_source)
                    audio_source.volume = 0.5
                    
                    # 再生終了時のコールバックを設定
                    def after_playing_next(error):
                        if error:
                            logger.error(f"Next track playback finished with error: {error}")
                        else:
                            logger.info("Next track playback finished successfully")
                        
                        # ファイルを確実に削除
                        cleanup_audio_file(file_path, guild.id)
                        
                        # さらに次の曲があるかチェック
                        next_track = audio_queue.get_next_track(guild.id)
                        if next_track:
                            logger.info(f"Playing next track from queue: {next_track.get('title', 'Unknown')}")
                            # 次の曲の再生をメインループで実行するためにイベントループを取得
                            loop = asyncio.get_event_loop()
                            if loop and loop.is_running():
                                loop.create_task(play_next_track(guild, next_track))
                            else:
                                logger.error("No running event loop available for next track playback")
                        else:
                            logger.info("No more tracks in queue, disconnecting")
                            # キューが空の場合は切断
                            try:
                                voice_client = guild.voice_client
                                if voice_client and voice_client.is_connected():
                                    loop = asyncio.get_event_loop()
                                    if loop and loop.is_running():
                                        loop.create_task(voice_client.disconnect())
                                        logger.info("Disconnected from voice channel after queue finished")
                                    else:
                                        logger.error("No running event loop available for disconnect")
                            except Exception as e:
                                logger.error(f"Failed to disconnect after queue: {e}")
                    
                    # 再生開始
                    voice_client = guild.voice_client
                    if voice_client and voice_client.is_connected():
                        voice_client.play(audio_source, after=after_playing_next)
                        current_audio_files[guild.id] = file_path
                        logger.info(f"Started playing next track: {title}")
                        
                        # チャンネルに通知
                        try:
                            embed = discord.Embed(
                                title="🎵 次の曲を再生中",
                                description=f"**タイトル：** {title}\n\n**URL：** {url}\n\n**チャンネル：** {guild.voice_client.channel.name if guild.voice_client and guild.voice_client.channel else 'Unknown'}\n\n**キューから再生開始**",
                                color=discord.Color.green()
                            )
                            embed.add_field(
                                name="🎵 ステータス",
                                value="音声を再生中...",
                                inline=False
                            )
                            # テキストチャンネルを見つけて通知
                            for channel in guild.text_channels:
                                if channel.permissions_for(guild.me).send_messages:
                                    await channel.send(embed=embed)
                                    break
                        except Exception as e:
                            logger.error(f"Failed to send next track notification: {e}")
                    
                except Exception as e:
                    logger.error(f"Failed to play next track: {e}")
                    cleanup_audio_file(file_path, guild.id)
                    
                    # エラー内容をEmbedボックスで表示
                    error_embed = discord.Embed(
                        title="❌ 音声再生エラー",
                        description=f"**{title}**\n\n📺 **URL:** {url}\n🎤 **チャンネル:** {guild.voice_client.channel.name if guild.voice_client and guild.voice_client.channel else 'Unknown'}",
                        color=discord.Color.red()
                    )
                    error_embed.add_field(
                        name="❌ エラー詳細",
                        value=f"音声の再生に失敗しました。\n\n**エラー内容:**\n```{str(e)}```",
                        inline=False
                    )
                    error_embed.add_field(
                        name="🔧 対処法",
                        value="• URLが正しいか確認してください\n• 動画が利用可能か確認してください\n• しばらく時間をおいて再試行してください",
                        inline=False
                    )
                    
                    # テキストチャンネルにエラーメッセージを送信
                    try:
                        for channel in guild.text_channels:
                            if channel.permissions_for(guild.me).send_messages:
                                await channel.send(embed=error_embed)
                                break
                    except Exception as send_error:
                        logger.error(f"Failed to send error message: {send_error}")
                    
        else:
            logger.error(f"Failed to download next track: {url}")
            
    except Exception as e:
        logger.error(f"Error in play_next_track: {e}")

def force_kill_ffmpeg_processes():
    """残っているFFmpegプロセスを強制終了する関数"""
    try:
        import psutil
        
        # FFmpegプロセスを検索して終了
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if 'ffmpeg' in proc.info['name'].lower():
                    logger.warning(f"Force killing FFmpeg process: {proc.info['pid']}")
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
                
        logger.info("FFmpeg processes cleanup completed")
        
    except ImportError:
        logger.warning("psutil not available, skipping FFmpeg process cleanup")
    except Exception as e:
        logger.error(f"Failed to cleanup FFmpeg processes: {e}")

def cleanup_old_audio_files():
    """古い音声ファイルをクリーンアップする関数"""
    try:
        import time
        current_time = time.time()
        # 1時間以上古い音声ファイルを削除
        cutoff_time = current_time - 3600  # 1時間前
        
        audio_files = list(Path(DOWNLOAD_DIR).glob("*.mp3"))
        cleaned_count = 0
        
        for file_path in audio_files:
            try:
                file_age = current_time - file_path.stat().st_mtime
                if file_age > cutoff_time:
                    os.remove(file_path)
                    cleaned_count += 1
                    logger.info(f"Cleaned up old audio file: {file_path}")
            except Exception as e:
                logger.error(f"Failed to cleanup old file {file_path}: {e}")
        
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} old audio files")
        else:
            logger.info("No old audio files to clean up")
            
    except Exception as e:
        logger.error(f"Failed to cleanup old audio files: {e}")

# ダウンローダーのインスタンス
video_downloader = YouTubeVideoDownloader()
mp3_downloader = YouTubeToMP3()

@bot.event
async def on_ready():
    """ボットが起動した時の処理"""
    logger.info(f'{bot.user} としてログインしました！')
    logger.info(f'サーバー数: {len(bot.guilds)}')
    
    # ダウンロードディレクトリを作成
    Path(DOWNLOAD_DIR).mkdir(exist_ok=True)
    
    # 古い音声ファイルのクリーンアップ
    cleanup_old_audio_files()
    
    # 残っているFFmpegプロセスのクリーンアップ
    force_kill_ffmpeg_processes()
    
    # スラッシュコマンドを同期
    try:
        logger.info("Syncing slash commands...")
        
        # まずグローバルコマンドを同期
        logger.info("Syncing global commands...")
        global_synced = await bot.tree.sync()
        logger.info(f'✅ Synced {len(global_synced)} global command(s)')
        
        # 各ギルドにも個別に同期（即座に反映）
        logger.info("Syncing guild commands...")
        for guild in bot.guilds:
            try:
                guild_synced = await bot.tree.sync(guild=guild)
                logger.info(f'✅ Synced {len(guild_synced)} command(s) to guild: {guild.name}')
                
                # ギルドコマンドの詳細も表示
                if guild_synced:
                    logger.info(f"  Guild commands for {guild.name}:")
                    for cmd in guild_synced:
                        logger.info(f"    - /{cmd.name}: {cmd.description}")
                
            except Exception as e:
                logger.error(f'❌ Failed to sync to guild {guild.name}: {e}')
        
        # 登録されたコマンドの詳細をログに出力
        logger.info("Global commands:")
        for cmd in global_synced:
            logger.info(f'  - /{cmd.name}: {cmd.description}')
            
        # コマンドが正しく登録されているか確認
        if len(global_synced) == 0:
            logger.warning("⚠️ No global commands were synced. This may indicate a permission issue.")
            logger.warning("Please check bot permissions and invite URL.")
            
        # コマンドの登録状況を詳細に確認
        logger.info("Checking command registration status...")
        try:
            # 登録されているコマンドの数を確認
            global_count = len(await bot.tree.fetch_commands())
            logger.info(f"Global commands count: {global_count}")
            
            for guild in bot.guilds:
                guild_count = len(await bot.tree.fetch_commands(guild=guild))
                logger.info(f"Guild commands count for {guild.name}: {guild_count}")
                
        except Exception as e:
            logger.error(f"❌ Failed to check command status: {e}")
            
    except Exception as e:
        logger.error(f'❌ Failed to sync commands: {e}')
        logger.error('Commands may not appear in Discord. Please check bot permissions.')
        logger.error('Make sure the bot has "applications.commands" scope when invited to the server.')
        logger.error('')
        logger.error('🔗 正しい招待URLの例:')
        logger.error('https://discord.com/api/oauth2/authorize?client_id=YOUR_BOT_ID&permissions=8&scope=bot%20applications.commands')
        logger.error('')
        logger.error('📋 必要な権限:')
        logger.error('• Send Messages')
        logger.error('• Use Slash Commands')
        logger.error('• Connect (音声チャンネル接続)')
        logger.error('• Speak (音声再生)')
        logger.error('• Attach Files')
        logger.error('• Embed Links')
    
    # アクティビティを設定
    await bot.change_presence(activity=discord.Game(name="YouTubeを再生中..."))

@bot.tree.command(name='download', description='Download YouTube video with specified quality')
@app_commands.describe(
    url='YouTube動画のURL',
    quality='動画の画質'
)
@app_commands.choices(quality=[
    app_commands.Choice(name='144p (低画質)', value='144p'),
    app_commands.Choice(name='240p (低画質)', value='240p'),
    app_commands.Choice(name='360p (標準画質)', value='360p'),
    app_commands.Choice(name='480p (標準画質)', value='480p'),
    app_commands.Choice(name='720p (高画質)', value='720p'),
    app_commands.Choice(name='1080p (フルHD)', value='1080p')
])
async def download_video(interaction: discord.Interaction, url: str, quality: str):
    """YouTube動画をダウンロードするコマンド"""
    # YouTube URLの形式をチェック（より柔軟に）
    youtube_patterns = [
        'https://www.youtube.com/watch',
        'https://youtube.com/watch',
        'https://youtu.be/',
        'https://www.youtube.com/embed/',
        'https://youtube.com/embed/'
    ]
    
    is_valid_youtube = any(url.startswith(pattern) for pattern in youtube_patterns)
    if not is_valid_youtube:
        await interaction.response.send_message(
            "❌ 有効なYouTube URLを入力してください。\n\n"
            "対応形式:\n"
            "• https://www.youtube.com/watch?v=...\n"
            "• https://youtu.be/...\n"
            "• https://youtube.com/watch?v=...",
            ephemeral=True
        )
        return
    
    # URLを標準形式に正規化
    normalized_url = normalize_youtube_url(url)
    if normalized_url:
        url = normalized_url
        logger.info(f"URL normalized to: {url}")
    
    # 動画タイトルを取得（可能な場合）
    video_title = "Unknown Title"
    try:
        # yt-dlpを使用して動画情報を取得（Windows環境でのエンコーディング問題を回避）
        import subprocess
        import platform
        
        # Windows環境での追加オプション
        cmd_args = ['yt-dlp', '--get-title', '--no-playlist', url]
        if platform.system() == 'Windows':
            # Windows環境では、より安全なエンコーディング設定を使用
            result = safe_subprocess_run(
                cmd_args,
                capture_output=True, 
                timeout=10,
                env=dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
            )
        else:
            result = safe_subprocess_run(cmd_args, capture_output=True, timeout=10)
        
        if result and result.returncode == 0 and result.stdout and result.stdout.strip():
            video_title = result.stdout.strip()
            logger.info(f"Retrieved video title for download: {video_title}")
        else:
            stderr_msg = result.stderr if result and result.stderr else 'No result or stderr'
            logger.warning(f"Could not retrieve video title for download: {stderr_msg}")
            # yt-dlpが失敗した場合、URLからビデオIDを抽出してタイトルを生成
            if 'youtube.com/watch?v=' in url:
                video_id = url.split('v=')[1].split('&')[0]
                video_title = f"YouTube Video ({video_id})"
            elif 'youtu.be/' in url:
                video_id = url.split('youtu.be/')[1].split('?')[0]
                video_title = f"YouTube Video ({video_id})"
            else:
                video_title = "YouTube Video"
    except Exception as e:
        logger.warning(f"Failed to get video title for download: {e}")
        # エラーが発生した場合、URLからビデオIDを抽出してタイトルを生成
        try:
            if 'youtube.com/watch?v=' in url:
                video_id = url.split('v=')[1].split('&')[0]
                video_title = f"YouTube Video ({video_id})"
            elif 'youtu.be/' in url:
                video_id = url.split('youtu.be/')[1].split('?')[0]
                video_title = f"YouTube Video ({video_id})"
            else:
                video_title = "YouTube Video"
        except Exception:
            video_title = "YouTube Video"
    
    # 処理開始メッセージ
    embed = discord.Embed(
        title="📥 ダウンロード開始",
        description=f"**{video_title}**\n\n📺 **URL:** {url}\n🎬 **画質:** {quality}",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="⏳ ステータス",
        value="動画をダウンロード中...",
        inline=False
    )
    await interaction.response.send_message(embed=embed)
    
    try:
        # ダウンロード実行
        await interaction.followup.send("⏳ ダウンロード中... しばらくお待ちください。")
        
        # 非同期でダウンロードを実行
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(
            None, 
            video_downloader.download_video, 
            url, 
            quality
        )
        
        if success:
            # ダウンロード成功後、最新のファイルを検索
            video_files = list(Path(DOWNLOAD_DIR).glob("*.mp4"))
            if video_files:
                # 最新のファイルを取得（作成時刻順）
                latest_file = max(video_files, key=lambda x: x.stat().st_mtime)
                file_path = str(latest_file)
                file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
            
            if file_size <= MAX_FILE_SIZE:
                # ファイルサイズが制限内の場合、Discordにアップロード
                file = discord.File(file_path)
                embed = discord.Embed(
                    title="✅ ダウンロード完了",
                    description=f"**{video_title}**\n\n📁 **ファイル:** {os.path.basename(file_path)}\n📊 **サイズ:** {file_size:.2f} MB\n🎬 **画質:** {quality}",
                    color=discord.Color.green()
                )
                embed.add_field(
                    name="📥 ダウンロード情報",
                    value=f"URL: {url}",
                    inline=False
                )
                await interaction.followup.send(embed=embed, file=file)
                
                # ファイルを削除（Discordにアップロード後）
                os.remove(file_path)
            else:
                # ファイルサイズが大きすぎる場合
                embed = discord.Embed(
                    title="⚠️ ファイルサイズが大きすぎます",
                    description=f"**{video_title}**\n\n📊 **ファイルサイズ:** {file_size:.2f} MB\n📏 **Discordの制限:** {MAX_FILE_SIZE} MB\n🎬 **画質:** {quality}\n\n容量制限のため、ファイルを削除しました。",
                    color=discord.Color.orange()
                )
                embed.add_field(
                    name="📥 ダウンロード情報",
                    value=f"URL: {url}",
                    inline=False
                )
                await interaction.followup.send(embed=embed)
                
                # 容量制限でDiscordにアップロードできない場合は、サーバー内のファイルを削除
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger.info(f"Removed oversized file due to size limit: {file_path}")
                        embed.add_field(
                            name="🗑️ ファイル削除",
                            value="容量制限により、サーバー内のファイルを削除しました。",
                            inline=False
                        )
                        await interaction.followup.send(embed=embed)
                except Exception as e:
                    logger.error(f"Failed to remove oversized file: {e}")
                    embed.add_field(
                        name="⚠️ 注意",
                        value="ファイルの削除に失敗しました。手動で削除してください。",
                        inline=False
                    )
                    await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("❌ ダウンロードに失敗しました。")
            
    except Exception as e:
        logger.error(f"ダウンロードエラー: {e}")
        embed = discord.Embed(
            title="❌ エラーが発生しました",
            description=f"エラー: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@bot.tree.command(name='download_mp3', description='Convert YouTube video to MP3 and download')
@app_commands.describe(
    url='YouTube動画のURL'
)
async def download_mp3(interaction: discord.Interaction, url: str):
    """YouTube動画をMP3に変換してダウンロードするコマンド"""
    # YouTube URLの形式をチェック（より柔軟に）
    youtube_patterns = [
        'https://www.youtube.com/watch',
        'https://youtube.com/watch',
        'https://youtu.be/',
        'https://www.youtube.com/embed/',
        'https://youtube.com/embed/'
    ]
    
    is_valid_youtube = any(url.startswith(pattern) for pattern in youtube_patterns)
    if not is_valid_youtube:
        await interaction.response.send_message(
            "❌ 有効なYouTube URLを入力してください。\n\n"
            "対応形式:\n"
            "• https://www.youtube.com/watch?v=...\n"
            "• https://youtu.be/...\n"
            "• https://youtube.com/watch?v=...",
            ephemeral=True
        )
        return
    
    # URLを標準形式に正規化
    normalized_url = normalize_youtube_url(url)
    if normalized_url:
        url = normalized_url
        logger.info(f"URL normalized to: {url}")
    
    # 動画タイトルを取得（可能な場合）
    video_title = "Unknown Title"
    try:
        # yt-dlpを使用して動画情報を取得（Windows環境でのエンコーディング問題を回避）
        import subprocess
        import platform
        
        # Windows環境での追加オプション
        cmd_args = ['yt-dlp', '--get-title', '--no-playlist', url]
        if platform.system() == 'Windows':
            # Windows環境では、より安全なエンコーディング設定を使用
            result = safe_subprocess_run(
                cmd_args,
                capture_output=True, 
                timeout=10,
                env=dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
            )
        else:
            result = safe_subprocess_run(cmd_args, capture_output=True, timeout=10)
        
        if result and result.returncode == 0 and result.stdout and result.stdout.strip():
            video_title = result.stdout.strip()
            logger.info(f"Retrieved video title for MP3 download: {video_title}")
        else:
            stderr_msg = result.stderr if result and result.stderr else 'No result or stderr'
            logger.warning(f"Could not retrieve video title for MP3 download: {stderr_msg}")
            # yt-dlpが失敗した場合、URLからビデオIDを抽出してタイトルを生成
            if 'youtube.com/watch?v=' in url:
                video_id = url.split('v=')[1].split('&')[0]
                video_title = f"YouTube Video ({video_id})"
            elif 'youtu.be/' in url:
                video_id = url.split('youtu.be/')[1].split('?')[0]
                video_title = f"YouTube Video ({video_id})"
            else:
                video_title = "YouTube Video"
    except Exception as e:
        logger.warning(f"Failed to get video title for MP3 download: {e}")
        # エラーが発生した場合、URLからビデオIDを抽出してタイトルを生成
        try:
            if 'youtube.com/watch?v=' in url:
                video_id = url.split('v=')[1].split('&')[0]
                video_title = f"YouTube Video ({video_id})"
            elif 'youtu.be/' in url:
                video_id = url.split('v=')[1].split('&')[0]
                video_title = f"YouTube Video ({video_id})"
            else:
                video_title = "YouTube Video"
        except Exception:
            video_title = "YouTube Video"
    
    # 処理開始メッセージ
    embed = discord.Embed(
        title="🎵 MP3変換開始",
        description=f"**{video_title}**\n\n📺 **URL:** {url}\n🎵 **形式:** MP3音声ファイル",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="⏳ ステータス",
        value="MP3に変換中...",
        inline=False
    )
    await interaction.response.send_message(embed=embed)
    
    try:
        await interaction.followup.send("⏳ MP3変換中... しばらくお待ちください。")
        
        # 非同期でMP3変換を実行
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(
            None, 
            mp3_downloader.download_mp3, 
            url
        )
        
        if success:
            # ダウンロード成功後、最新のMP3ファイルを検索
            mp3_files = list(Path(DOWNLOAD_DIR).glob("*.mp3"))
            if mp3_files:
                # 最新のファイルを取得（作成時刻順）
                latest_file = max(mp3_files, key=lambda x: x.stat().st_mtime)
                file_path = str(latest_file)
                file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
                
                if file_size <= MAX_FILE_SIZE:
                    file = discord.File(file_path)
                    embed = discord.Embed(
                        title="✅ MP3変換完了",
                        description=f"**{video_title}**\n\n📁 **ファイル:** {os.path.basename(file_path)}\n📊 **サイズ:** {file_size:.2f} MB\n🎵 **形式:** MP3音声ファイル",
                        color=discord.Color.green()
                    )
                    embed.add_field(
                        name="📥 ダウンロード情報",
                        value=f"URL: {url}",
                        inline=False
                    )
                    await interaction.followup.send(embed=embed, file=file)
                    
                    # ファイルを削除
                    os.remove(file_path)
                else:
                    embed = discord.Embed(
                        title="⚠️ ファイルサイズが大きすぎます",
                        description=f"**{video_title}**\n\n📊 **ファイルサイズ:** {file_size:.2f} MB\n📏 **Discordの制限:** {MAX_FILE_SIZE} MB\n🎵 **形式:** MP3音声ファイル\n\n容量制限のため、ファイルを削除しました。",
                        color=discord.Color.orange()
                    )
                    embed.add_field(
                        name="📥 ダウンロード情報",
                        value=f"URL: {url}",
                        inline=False
                    )
                    await interaction.followup.send(embed=embed)
                    
                    # 容量制限でDiscordにアップロードできない場合は、サーバー内のファイルを削除
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            logger.info(f"Removed oversized MP3 file due to size limit: {file_path}")
                            embed.add_field(
                                name="🗑️ ファイル削除",
                                value="容量制限により、サーバー内のMP3ファイルを削除しました。",
                                inline=False
                            )
                            await interaction.followup.send(embed=embed)
                    except Exception as e:
                        logger.error(f"Failed to remove oversized MP3 file: {e}")
                        embed.add_field(
                            name="⚠️ 注意",
                            value="MP3ファイルの削除に失敗しました。手動で削除してください。",
                            inline=False
                        )
                        await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("❌ MP3変換に失敗しました。")
            
    except Exception as e:
        logger.error(f"MP3変換エラー: {e}")
        embed = discord.Embed(
            title="❌ エラーが発生しました",
            description=f"エラー: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

@bot.tree.command(name='quality', description='Show available video quality options')
async def show_quality(interaction: discord.Interaction):
    """利用可能な画質を表示するコマンド"""
    embed = discord.Embed(
        title="🎬 利用可能な画質",
        description="\n".join([f"• {q}" for q in SUPPORTED_QUALITIES]),
        color=discord.Color.blue()
    )
    embed.add_field(
        name="使用例",
        value=f"`/download <URL> <画質>`\n例: `/download https://youtube.com/watch?v=... 1080p`",
        inline=False
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name='play', description='Play YouTube audio in voice channel')
async def play_audio(interaction: discord.Interaction, url: str):
    """YouTubeの音声を再生するコマンド"""
    # ユーザーがボイスチャンネルに接続しているかチェック
    if not interaction.user.voice:
        await interaction.response.send_message(
            "❌ ボイスチャンネルに接続してから使用してください。",
            ephemeral=True
        )
        return
    
    guild_id = interaction.guild_id
    voice_client = interaction.guild.voice_client
    
    # ボイスチャンネルに接続していない場合は接続を試行
    if not voice_client or not voice_client.is_connected():
        try:
            voice_channel = interaction.user.voice.channel
            voice_client = await voice_channel.connect()
            logger.info(f"Connected to voice channel: {voice_channel.name}")
        except Exception as e:
            logger.error(f"Failed to connect to voice channel: {e}")
            await interaction.response.send_message(
                "❌ ボイスチャンネルに接続できませんでした。",
                ephemeral=True
            )
            return
    
    # 既に再生中の場合はキューに追加
    if voice_client and voice_client.is_playing():
        # 即座に応答
        embed = discord.Embed(
            title="🎵 キューに追加中",
            description=f"**URL：** {url}\n👤 **リクエスト:** {interaction.user.display_name}",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="⏳ ステータス",
            value="動画情報を取得中...",
            inline=False
        )
        await interaction.response.send_message(embed=embed)
        
        # URLからタイトルを取得
        video_title = get_title_from_url(url)
        
        # キューに追加
        track_info = {
            'url': url,
            'title': video_title,
            'user': interaction.user.display_name,
            'added_at': interaction.created_at
        }
        audio_queue.add_track(guild_id, track_info)
        
        # キューに追加メッセージを更新
        embed = discord.Embed(
            title="🎵 キューに追加",
            description=f"**タイトル：** {video_title}\n\n**URL：** {url}\n👤 **リクエスト:** {interaction.user.display_name}\n📋 **現在のキュー:** {audio_queue.get_queue_length(guild_id)}曲",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="⏳ ステータス",
            value="キューに追加されました。順番をお待ちください。",
            inline=False
        )
        await interaction.followup.send(embed=embed)
        
        # キューに追加後、即座にダウンロードを開始（バックグラウンドで）
        asyncio.create_task(start_background_download(guild_id, track_info))
        return
    
    # 再生中でない場合は即座に再生を開始
    try:
        # 即座に応答してから詳細処理を行う
        embed = discord.Embed(
            title="🎵 音声準備開始",
            description=f"**URL：** {url}\n\n**チャンネル：** {voice_client.channel.name if voice_client.channel else 'Unknown'}",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="⏳ ステータス",
            value="動画情報を取得中...",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
        
        # URLからタイトルを取得
        video_title = get_title_from_url(url)
        
        # トラック情報を作成
        track_info = {
            'url': url,
            'title': video_title,
            'user': interaction.user.display_name,
            'added_at': interaction.created_at
        }
        
        # 準備開始メッセージを更新
        embed = discord.Embed(
            title="🎵 音声準備開始",
            description=f"**タイトル：** {video_title}\n\n**URL：** {url}\n\n**チャンネル：** {voice_client.channel.name if voice_client.channel else 'Unknown'}",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="⏳ ステータス",
            value="音声ファイルをダウンロード中...",
            inline=False
        )
        await interaction.followup.send(embed=embed)
        
        # バックグラウンドでダウンロードと再生を開始
        asyncio.create_task(download_and_play_track(guild_id, track_info, voice_client, interaction.channel_id))
        
    except Exception as e:
        logger.error(f"Failed to start playback: {e}")
        await interaction.response.send_message(
            f"❌ 音声再生の開始に失敗しました: {str(e)}",
            ephemeral=True
        )

async def process_playback_start(guild_id: int, url: str, voice_client, user_name: str, created_at):
    """再生開始の処理をバックグラウンドで実行する関数"""
    try:
        # 動画タイトルを取得（可能な場合）
        video_title = "Unknown Title"
        try:
            # yt-dlpを使用して動画情報を取得（Windows環境でのエンコーディング問題を回避）
            import subprocess
            import platform
            
            # Windows環境での追加オプション
            cmd_args = ['yt-dlp', '--get-title', '--no-playlist', url]
            if platform.system() == 'Windows':
                # Windows環境では、より安全なエンコーディング設定を使用
                result = safe_subprocess_run(
                    cmd_args,
                    capture_output=True, 
                    timeout=10,
                    env=dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
                )
            else:
                result = safe_subprocess_run(cmd_args, capture_output=True, timeout=10)
            
            if result and result.returncode == 0 and result.stdout and result.stdout.strip():
                video_title = result.stdout.strip()
                logger.info(f"Retrieved video title for playback: {video_title}")
            else:
                stderr_msg = result.stderr if result and result.stderr else 'No result or stderr'
                logger.warning(f"Could not retrieve video title for playback: {stderr_msg}")
                # yt-dlpが失敗した場合、URLからビデオIDを抽出してタイトルを生成
                if 'youtube.com/watch?v=' in url:
                    video_id = url.split('v=')[1].split('&')[0]
                    video_title = f"YouTube Video ({video_id})"
                elif 'youtu.be/' in url:
                    video_id = url.split('youtu.be/')[1].split('?')[0]
                    video_title = f"YouTube Video ({video_id})"
                else:
                    video_title = "YouTube Video"
        except Exception as e:
            logger.warning(f"Failed to get video title for playback: {e}")
            # エラーが発生した場合、URLからビデオIDを抽出してタイトルを生成
            try:
                if 'youtube.com/watch?v=' in url:
                    video_id = url.split('v=')[1].split('&')[0]
                    video_title = f"YouTube Video ({video_id})"
                elif 'youtu.be/' in url:
                    video_id = url.split('v=')[1].split('?')[0]
                    video_title = f"YouTube Video ({video_id})"
                else:
                    video_title = "YouTube Video"
            except Exception:
                video_title = "YouTube Video"
        
        # トラック情報を作成
        track_info = {
            'url': url,
            'title': video_title,
            'user': user_name,
            'added_at': created_at
        }
        
        # バックグラウンドでダウンロードと再生を開始
        asyncio.create_task(download_and_play_track(guild_id, track_info, voice_client))
        
    except Exception as e:
        logger.error(f"Error in process_playback_start: {e}")

async def process_queue_addition(guild_id: int, url: str, user_name: str, created_at):
    """キューに追加する処理をバックグラウンドで実行する関数"""
    try:
        # 動画タイトルを取得（可能な場合）
        video_title = "Unknown Title"
        try:
            # yt-dlpを使用して動画情報を取得（Windows環境でのエンコーディング問題を回避）
            import subprocess
            import platform
            
            # Windows環境での追加オプション
            cmd_args = ['yt-dlp', '--get-title', '--no-playlist', url]
            if platform.system() == 'Windows':
                # Windows環境では、より安全なエンコーディング設定を使用
                result = safe_subprocess_run(
                    cmd_args,
                    capture_output=True, 
                    timeout=10,
                    env=dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
                )
            else:
                result = safe_subprocess_run(cmd_args, capture_output=True, timeout=10)
            
            if result and result.returncode == 0 and result.stdout and result.stdout.strip():
                video_title = result.stdout.strip()
                logger.info(f"Retrieved video title for queue: {video_title}")
            else:
                stderr_msg = result.stderr if result and result.stderr else 'No result or stderr'
                logger.warning(f"Could not retrieve video title for queue: {stderr_msg}")
                # yt-dlpが失敗した場合、URLからビデオIDを抽出してタイトルを生成
                if 'youtube.com/watch?v=' in url:
                    video_id = url.split('v=')[1].split('&')[0]
                    video_title = f"YouTube Video ({video_id})"
                elif 'youtu.be/' in url:
                    video_id = url.split('youtu.be/')[1].split('?')[0]
                    video_title = f"YouTube Video ({video_id})"
                else:
                    video_title = "YouTube Video"
        except Exception as e:
            logger.warning(f"Failed to get video title for queue: {e}")
            # エラーが発生した場合、URLからビデオIDを抽出してタイトルを生成
            try:
                if 'youtube.com/watch?v=' in url:
                    video_id = url.split('v=')[1].split('&')[0]
                    video_title = f"YouTube Video ({video_id})"
                elif 'youtu.be/' in url:
                    video_id = url.split('v=')[1].split('?')[0]
                    video_title = f"YouTube Video ({video_id})"
                else:
                    video_title = "YouTube Video"
            except Exception:
                video_title = "YouTube Video"
        
        # キューに追加
        track_info = {
            'url': url,
            'title': video_title,
            'user': user_name,
            'added_at': created_at
        }
        audio_queue.add_track(guild_id, track_info)
        
        # キューに追加後、即座にダウンロードを開始（バックグラウンドで）
        asyncio.create_task(start_background_download(guild_id, track_info))
        
    except Exception as e:
        logger.error(f"Error in process_queue_addition: {e}")

async def start_background_download(guild_id: int, track_info: dict):
    """バックグラウンドでトラックをダウンロードする関数"""
    try:
        url = track_info['url']
        title = track_info.get('title', 'Unknown Track')
        
        logger.info(f"Starting background download for: {title}")
        
        # 音声ファイルをダウンロード
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(
            None, 
            mp3_downloader.download_mp3, 
            url
        )
        
        if success:
            logger.info(f"Background download completed for: {title}")
            # ダウンロード完了後、ファイルは一時的に保存される
            # 次の曲の再生時に使用される
            
            # ダウンロード完了を記録
            if not hasattr(audio_queue, 'downloaded_tracks'):
                audio_queue.downloaded_tracks = {}
            audio_queue.downloaded_tracks[f"{guild_id}_{url}"] = True
            
        else:
            logger.error(f"Background download failed for: {title}")
            
    except Exception as e:
        logger.error(f"Error in background download: {e}")
        
    # ボイスチャンネルに接続
    voice_channel = None
    try:
        # guild_idからguildを取得
        guild = bot.get_guild(guild_id)
        if guild and guild.voice_client:
            voice_client = guild.voice_client
        else:
            logger.error(f"No voice client found for guild {guild_id}")
            return
    except Exception as e:
        logger.error(f"Failed to get voice client: {e}")
        return
    
    # 動画タイトルを取得（可能な場合）
    video_title = track_info.get('title', 'Unknown Title')
    
    # 準備開始メッセージ
    embed = discord.Embed(
        title="🎵 音声準備開始",
        description=f"**{video_title}**\n\n📺 **URL:** {track_info['url']}\n🎤 **チャンネル:** {voice_client.channel.name if voice_client.channel else 'Unknown'}\n👤 **リクエスト:** {track_info.get('user', 'Unknown')}",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="⏳ ステータス",
        value="音声ファイルをダウンロード中...",
        inline=False
    )
    
    try:
        # 音声ファイルをダウンロード
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(
            None, 
            mp3_downloader.download_mp3, 
            track_info['url']
        )
        
        if success:
            # 最新のMP3ファイルを検索
            mp3_files = list(Path(DOWNLOAD_DIR).glob("*.mp3"))
            if mp3_files:
                latest_file = max(mp3_files, key=lambda x: x.stat().st_mtime)
                file_path = str(latest_file)
                
                # 音声ファイルの存在確認
                if not os.path.exists(file_path):
                    logger.error(f"Audio file not found: {file_path}")
                    return
                
                # ファイルサイズの確認
                file_size = os.path.getsize(file_path)
                if file_size == 0:
                    logger.error(f"Audio file is empty: {file_path}")
                    return
                
                # 現在再生中のトラックとして記録
                audio_queue.now_playing[guild_id] = track_info
                
                logger.info(f"Playing audio file: {file_path} (size: {file_size} bytes)")
                
                # 音声を再生
                try:
                    # FFmpegオプションを設定
                    ffmpeg_options = {
                        'options': '-vn',
                        'before_options': '-y -nostdin -loglevel error -hide_banner -re'
                    }
                    
                    # 音声ソースを作成
                    audio_source = discord.FFmpegPCMAudio(file_path, **ffmpeg_options)
                    audio_source = discord.PCMVolumeTransformer(audio_source)
                    audio_source.volume = 0.5
                    
                    # 再生終了時のコールバックを設定
                    def after_playing(error):
                        if error:
                            logger.error(f"Audio playback finished with error: {error}")
                        else:
                            logger.info("Audio playback finished successfully")
                        
                        # ファイルを確実に削除
                        cleanup_audio_file(file_path, guild_id)
                        
                        # 現在再生中のトラックをクリア
                        audio_queue.clear_now_playing(guild_id)
                        
                        # キューから次の曲を取得して再生
                        next_track = audio_queue.get_next_track(guild_id)
                        if next_track:
                            logger.info(f"Playing next track from queue: {next_track.get('title', 'Unknown')}")
                            # 次の曲を再生
                            asyncio.create_task(download_and_play_track(guild_id, next_track, voice_client))
                        else:
                            logger.info("No more tracks in queue, disconnecting")
                            # キューが空の場合は切断
                            try:
                                if voice_client and voice_client.is_connected():
                                    asyncio.create_task(voice_client.disconnect())
                                    logger.info("Disconnected from voice channel after queue finished")
                            except Exception as e:
                                logger.error(f"Failed to disconnect after queue: {e}")
                    
                    # 再生開始
                    if voice_client and voice_client.is_connected():
                        voice_client.play(audio_source, after=after_playing)
                        current_audio_files[guild_id] = file_path
                        logger.info(f"Started playing track: {video_title}")
                        
                        # チャンネルに通知
                        try:
                            # テキストチャンネルを見つけて通知
                            for channel in guild.text_channels:
                                if channel.permissions_for(guild.me).send_messages:
                                    await channel.send(embed=embed)
                                    break
                        except Exception as e:
                            logger.error(f"Failed to send track notification: {e}")
                    
                except Exception as e:
                    logger.error(f"Failed to play track: {e}")
                    cleanup_audio_file(file_path, guild_id)
                    
                    # エラー内容をEmbedボックスで表示
                    error_embed = discord.Embed(
                        title="❌ 音声再生エラー",
                        description=f"**{video_title}**\n\n📺 **URL:** {track_info['url']}\n🎤 **チャンネル:** {voice_client.channel.name if voice_client.channel else 'Unknown'}",
                        color=discord.Color.red()
                    )
                    error_embed.add_field(
                        name="❌ エラー詳細",
                        value=f"音声の再生に失敗しました。\n\n**エラー内容:**\n```{str(e)}```",
                        inline=False
                    )
                    error_embed.add_field(
                        name="🔧 対処法",
                        value="• URLが正しいか確認してください\n• 動画が利用可能か確認してください\n• しばらく時間をおいて再試行してください",
                        inline=False
                    )
                    
                    # テキストチャンネルにエラーメッセージを送信
                    try:
                        for channel in guild.text_channels:
                            if channel.permissions_for(guild.me).send_messages:
                                await channel.send(embed=error_embed)
                                break
                    except Exception as send_error:
                        logger.error(f"Failed to send error message: {send_error}")
                    
        else:
            logger.error(f"Failed to download track: {track_info['url']}")
            
    except Exception as e:
        logger.error(f"Error in start_background_download: {e}")

@bot.tree.command(name='stop', description='Stop audio playback and disconnect from voice channel')
async def stop_audio(interaction: discord.Interaction):
    """音声再生を停止し、ボイスチャンネルから切断するコマンド"""
    # ボイスクライアントが存在するかチェック
    voice_client = interaction.guild.voice_client
    if not voice_client:
        await interaction.response.send_message(
            "❌ ボイスチャンネルに接続していません。",
            ephemeral=True
        )
        return
    
    try:
        # 音声再生を停止
        if voice_client.is_playing():
            voice_client.stop()
            logger.info("Audio playback stopped")
        
        # 現在の音声ファイルを記録から削除
        guild_id = interaction.guild_id
        if guild_id in current_audio_files:
            file_path = current_audio_files[guild_id]
            cleanup_audio_file(file_path, guild_id)
        
        # キューと現在再生中のトラックをクリア
        audio_queue.clear_queue(guild_id)
        audio_queue.clear_now_playing(guild_id)
        logger.info(f"Cleared queue and now playing for guild {guild_id}")
        
        # 少し待ってから切断（FFmpegプロセスの終了を待つ）
        await asyncio.sleep(1)
        
        # ボイスチャンネルから切断
        await voice_client.disconnect()
        logger.info("Disconnected from voice channel")
        
        embed = discord.Embed(
            title="🛑 再生停止",
            description="音声再生を停止し、ボイスチャンネルから切断しました。\nキューもクリアされました。",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        logger.error(f"Stop command error: {e}")
        await interaction.response.send_message("❌ 音声停止に失敗しました。")

@bot.tree.command(name='pause', description='Pause audio playback')
async def pause_audio(interaction: discord.Interaction):
    """音声再生を一時停止するコマンド"""
    voice_client = interaction.guild.voice_client
    if not voice_client or not voice_client.is_playing():
        await interaction.response.send_message(
            "❌ 現在音声を再生していません。",
            ephemeral=True
        )
        return
    
    try:
        voice_client.pause()
        embed = discord.Embed(
            title="⏸️ 一時停止",
            description="音声再生を一時停止しました。",
            color=discord.Color.yellow()
        )
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        logger.error(f"Pause command error: {e}")
        await interaction.response.send_message("❌ 一時停止に失敗しました。")

@bot.tree.command(name='resume', description='Resume audio playback')
async def resume_audio(interaction: discord.Interaction):
    """音声再生を再開するコマンド"""
    voice_client = interaction.guild.voice_client
    if not voice_client or not voice_client.is_paused():
        await interaction.response.send_message(
            "❌ 現在音声は一時停止されていません。",
            ephemeral=True
        )
        return
    
    try:
        voice_client.resume()
        embed = discord.Embed(
            title="▶️ 再生再開",
            description="音声再生を再開しました。",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        logger.error(f"Resume command error: {e}")
        await interaction.response.send_message("❌ 再生再開に失敗しました。")

@bot.tree.command(name='ping', description='Test bot response')
async def ping(interaction: discord.Interaction):
    """ボットの応答テスト用コマンド"""
    await interaction.response.send_message("🏓 Pong! Bot is working!", ephemeral=True)

@bot.tree.command(name='queue', description='Show current music queue')
async def show_queue(interaction: discord.Interaction):
    """現在の音楽キューを表示するコマンド"""
    guild_id = interaction.guild_id
    queue = audio_queue.get_queue(guild_id)
    now_playing = audio_queue.now_playing.get(guild_id)
    
    embed = discord.Embed(
        title="🎵 音楽キュー",
        color=discord.Color.blue()
    )
    
    if now_playing:
        embed.add_field(
            name="🎶 現在再生中",
            value=f"**{now_playing.get('title', 'Unknown')}**\n追加者: {now_playing.get('user', 'Unknown')}",
            inline=False
        )
    
    if queue:
        queue_text = ""
        for i, track in enumerate(queue[:10], 1):  # 最大10曲まで表示
            queue_text += f"{i}. **{track.get('title', 'Unknown')}**\n   追加者: {track.get('user', 'Unknown')}\n"
        
        if len(queue) > 10:
            queue_text += f"\n... 他 {len(queue) - 10} 曲"
        
        embed.add_field(
            name=f"📋 キュー ({len(queue)}曲)",
            value=queue_text,
            inline=False
        )
    else:
        embed.add_field(
            name="📋 キュー",
            value="キューは空です。",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name='clear', description='Clear music queue')
async def clear_queue(interaction: discord.Interaction):
    """音楽キューをクリアするコマンド"""
    guild_id = interaction.guild_id
    audio_queue.clear_queue(guild_id)
    
    embed = discord.Embed(
        title="🗑️ キューをクリア",
        description="音楽キューがクリアされました。\n現在再生中の曲は影響を受けません。",
        color=discord.Color.orange()
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name='skip', description='Skip current track and play next track in queue')
async def skip_audio(interaction: discord.Interaction):
    """現在再生中の曲をスキップするコマンド"""
    # ボイスクライアントが存在するかチェック
    voice_client = interaction.guild.voice_client
    if not voice_client:
        await interaction.response.send_message(
            "❌ ボイスチャンネルに接続していません。",
            ephemeral=True
        )
        return
    
    # 再生中かどうかチェック
    if not voice_client.is_playing():
        await interaction.response.send_message(
            "❌ 現在音声を再生していません。",
            ephemeral=True
        )
        return
    
    try:
        # 現在再生中の曲の情報を取得
        guild_id = interaction.guild_id
        current_track = audio_queue.get_now_playing(guild_id)
        current_title = current_track.get('title', 'Unknown Track') if current_track else 'Unknown Track'
        
        # 次の曲があるかチェック
        next_track = audio_queue.get_queue(guild_id)[0] if audio_queue.has_queue(guild_id) else None
        next_title = next_track.get('title', 'Unknown Track') if next_track else None
        
        # 即座に応答を送信
        embed = discord.Embed(
            title="⏭️ スキップ",
            description=f"**現在の曲をスキップします**\n\n🎵 **スキップする曲：** {current_title}",
            color=discord.Color.blue()
        )
        if next_title:
            embed.add_field(
                name="⏭️ 次の曲",
                value=next_title,
                inline=False
            )
        await interaction.response.send_message(embed=embed)
        
        # 現在の曲を停止（これにより after_playing_track コールバックが呼ばれ、次の曲の再生が開始される）
        voice_client.stop()
        logger.info(f"Skipped track: {current_title}")
        
    except Exception as e:
        logger.error(f"Skip command error: {e}")
        await interaction.response.send_message(
            "❌ スキップに失敗しました。",
            ephemeral=True
        )

@bot.tree.command(name='help', description='Show bot help and command list')
async def show_help(interaction: discord.Interaction):
    """ヘルプコマンド"""
    embed = discord.Embed(
        title="🤖 YouTube Downloader Bot ヘルプ",
        description="YouTube動画をダウンロードできるDiscordボットです。",
        color=discord.Color.blue()
    )
    
    # スラッシュコマンド用に更新
    slash_commands = {
        '/ping': 'ボットの応答テスト',
        '/download': 'YouTube動画をダウンロードします（画質はプルダウンメニューから選択）',
        '/download_mp3': 'YouTube動画をMP3に変換してダウンロードします',
        '/quality': '利用可能な画質を表示します',
        '/play': 'YouTube音声をボイスチャンネルで再生します（キューに追加）',
        '/pause': '音声再生を一時停止します',
        '/resume': '音声再生を再開します',
        '/stop': '音声再生を停止し、ボイスチャンネルから切断します',
        '/skip': '現在再生中の曲をスキップして次の曲を再生します',
        '/queue': '現在の音楽キューを表示します',
        '/clear': '音楽キューをクリアします',
        '/help': 'コマンド一覧を表示します'
    }
    
    for command, description in slash_commands.items():
        embed.add_field(
            name=command,
            value=description,
            inline=False
        )
    
    embed.add_field(
        name="📝 注意事項",
        value="• ファイルサイズは25MB以下に制限されています\n• 個人使用目的でのみ使用してください\n• YouTubeの利用規約を遵守してください\n• 画質選択はプルダウンメニューから簡単に選択できます",
        inline=False
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.event
async def on_command_error(ctx, error):
    """コマンドエラー時の処理"""
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ 必要な引数が不足しています。`/help`で使用方法を確認してください。")
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send(f"❌ コマンドが見つかりません。`/help`で利用可能なコマンドを確認してください。")
    else:
        logger.error(f"コマンドエラー: {error}")
        await ctx.send("❌ 予期しないエラーが発生しました。")

def main():
    """メイン関数"""
    # クロスプラットフォーム対応のエンコーディング設定
    setup_encoding()
    
    if DISCORD_TOKEN == 'your_discord_bot_token_here':
        print("❌ config.pyでDISCORD_TOKENを設定してください。")
        return
    
    try:
        bot.run(DISCORD_TOKEN)
    except discord.LoginFailure:
        print("❌ Discordトークンが無効です。")
    except discord.errors.PrivilegedIntentsRequired:
        print("❌ 特権インテントが必要です。")
        print("Discord Developer Portalで以下を有効にしてください：")
        print("1. https://discord.com/developers/applications にアクセス")
        print("2. ボットアプリケーションを選択")
        print("3. 'Bot'セクションで以下を有効化：")
        print("   - MESSAGE CONTENT INTENT")
        print("   - SERVER MEMBERS INTENT")
        print("4. 変更を保存")
        print("5. ボットを再起動")
    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")

if __name__ == "__main__":
    # クロスプラットフォーム対応のエンコーディング設定
    setup_encoding()
    
    main()
