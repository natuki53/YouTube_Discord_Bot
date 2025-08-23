import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
import sys
import logging
from pathlib import Path

# YouTube_Downloaderのモジュールをインポート
sys.path.append('./YouTube_Downloader')
from youtube_video_downloader import YouTubeVideoDownloader
from youtube_to_mp3 import YouTubeToMP3

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
from config import *

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

# グローバルな音声キューインスタンス
audio_queue = AudioQueue()

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
                            asyncio.create_task(play_next_track(guild, next_track))
                        else:
                            logger.info("No more tracks in queue, disconnecting")
                            # キューが空の場合は切断
                            try:
                                voice_client = guild.voice_client
                                if voice_client and voice_client.is_connected():
                                    asyncio.create_task(voice_client.disconnect())
                                    logger.info("Disconnected from voice channel after queue finished")
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
                                description=f"**{title}**\nキューから再生を開始しました。",
                                color=discord.Color.green()
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
                    
        else:
            logger.error(f"Failed to download next track: {url}")
            
    except Exception as e:
        logger.error(f"Error in play_next_track: {e}")

def force_kill_ffmpeg_processes():
    """残っているFFmpegプロセスを強制終了する関数"""
    try:
        import subprocess
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
async def download_video(interaction: discord.Interaction, url: str, quality: str = '720p'):
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
    
    # 処理開始メッセージ
    embed = discord.Embed(
        title="📥 ダウンロード開始",
        description=f"URL: {url}\n画質: {quality}",
        color=discord.Color.blue()
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
                    description=f"ファイル: {os.path.basename(file_path)}\nサイズ: {file_size:.2f} MB",
                    color=discord.Color.green()
                )
                await interaction.followup.send(embed=embed, file=file)
                
                # ファイルを削除（Discordにアップロード後）
                os.remove(file_path)
            else:
                # ファイルサイズが大きすぎる場合
                embed = discord.Embed(
                    title="⚠️ ファイルサイズが大きすぎます",
                    description=f"ファイルサイズ: {file_size:.2f} MB\nDiscordの制限: {MAX_FILE_SIZE} MB\nファイルは {DOWNLOAD_DIR} に保存されました。",
                    color=discord.Color.orange()
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
    
    # 処理開始メッセージ
    embed = discord.Embed(
        title="🎵 MP3変換開始",
        description=f"URL: {url}",
        color=discord.Color.blue()
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
                        description=f"ファイル: {os.path.basename(file_path)}\nサイズ: {file_size:.2f} MB",
                        color=discord.Color.green()
                    )
                    await interaction.followup.send(embed=embed, file=file)
                    
                    # ファイルを削除
                    os.remove(file_path)
                else:
                    embed = discord.Embed(
                        title="⚠️ ファイルサイズが大きすぎます",
                        description=f"ファイルサイズ: {file_size:.2f} MB\nDiscordの制限: {MAX_FILE_SIZE} MB\nファイルは {DOWNLOAD_DIR} に保存されました。",
                        color=discord.Color.orange()
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
    
    # 既に再生中の場合はキューに追加
    if voice_client and voice_client.is_playing():
        # キューに追加
        track_info = {
            'url': url,
            'title': f"Track from {url}",
            'user': interaction.user.display_name,
            'added_at': interaction.created_at
        }
        audio_queue.add_track(guild_id, track_info)
        
        embed = discord.Embed(
            title="🎵 キューに追加",
            description=f"**{track_info['title']}**\nキューに追加されました。\n現在のキュー: {audio_queue.get_queue_length(guild_id)}曲",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)
        return
    
    # YouTube URLの形式をチェック
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
    
    # ボイスチャンネルに接続
    voice_channel = interaction.user.voice.channel
    try:
        voice_client = await voice_channel.connect()
        logger.info(f"Connected to voice channel: {voice_channel.name}")
    except Exception as e:
        # 既に接続されている場合
        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.response.send_message(
                "❌ ボイスチャンネルに接続できませんでした。",
                ephemeral=True
            )
            return
    
    # 処理開始メッセージ
    embed = discord.Embed(
        title="🎵 再生開始",
        description=f"URL: {url}\nチャンネル: {voice_channel.name}",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)
    
    try:
        await interaction.followup.send("⏳ 音声を準備中... しばらくお待ちください。")
        
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
                    await interaction.followup.send("❌ 音声ファイルが見つかりません。")
                    return
                
                # ファイルサイズの確認
                file_size = os.path.getsize(file_path)
                if file_size == 0:
                    await interaction.followup.send("❌ 音声ファイルが空です。")
                    return
                
                # 音声ファイルの形式を確認
                try:
                    import subprocess
                    result = subprocess.run([
                        'ffprobe', '-v', 'quiet', '-print_format', 'json', 
                        '-show_streams', file_path
                    ], capture_output=True, text=True)
                    
                    if result.returncode == 0:
                        import json
                        info = json.loads(result.stdout)
                        if 'streams' in info and len(info['streams']) > 0:
                            stream = info['streams'][0]
                            sample_rate = stream.get('sample_rate', 'unknown')
                            channels = stream.get('channels', 'unknown')
                            codec = stream.get('codec_name', 'unknown')
                            logger.info(f"Audio file info - Codec: {codec}, Sample Rate: {sample_rate}Hz, Channels: {channels}")
                except Exception as e:
                    logger.warning(f"Could not get audio file info: {e}")
                
                logger.info(f"Playing audio file: {file_path} (size: {file_size} bytes)")
                
                # 音声を再生（Jockie Musicの設計思想を参考に改善）
                try:
                    logger.info("Starting audio playback process...")
                    
                    # 1. より安全なFFmpegオプションを設定
                    ffmpeg_options = {
                        'options': '-vn',  # ビデオを無効化のみ
                        'before_options': '-y -nostdin -loglevel error -hide_banner -re'  # 既存ファイルを上書き、標準入力を無効化、ログレベルを最小限に、バナーを非表示、リアルタイム再生
                    }
                    logger.info(f"FFmpeg options set: {ffmpeg_options}")
                    
                    # 2. 音声ソースを作成（エラーハンドリング強化）
                    logger.info("Creating audio source...")
                    try:
                        # ファイルの存在確認
                        if not os.path.exists(file_path):
                            raise Exception(f"音声ファイルが存在しません: {file_path}")
                        
                        # ファイルの読み取り権限確認
                        if not os.access(file_path, os.R_OK):
                            raise Exception(f"音声ファイルの読み取り権限がありません: {file_path}")
                        
                        # FFmpegオプションの詳細をログに出力
                        logger.info(f"Creating FFmpegPCMAudio with file: {file_path}")
                        logger.info(f"FFmpeg options: {ffmpeg_options}")
                        
                        # FFmpegの動作テスト
                        try:
                            import subprocess
                            test_cmd = ['ffmpeg', '-i', file_path, '-f', 'null', '-']
                            result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=10)
                            if result.returncode == 0:
                                logger.info("FFmpeg test successful - file is valid")
                            else:
                                logger.warning(f"FFmpeg test failed: {result.stderr}")
                        except Exception as ffmpeg_test_error:
                            logger.warning(f"FFmpeg test error: {ffmpeg_test_error}")
                        
                        audio_source = discord.FFmpegPCMAudio(file_path, **ffmpeg_options)
                        logger.info("Audio source created successfully")
                        
                        # 音声ソースの属性を確認
                        logger.info(f"Audio source attributes: {dir(audio_source)}")
                        
                    except Exception as source_error:
                        logger.error(f"Failed to create audio source: {source_error}")
                        logger.error(f"Source error type: {type(source_error).__name__}")
                        logger.error(f"Source error details: {str(source_error)}")
                        
                        # より詳細なエラー情報を取得
                        import traceback
                        logger.error(f"Source creation traceback: {traceback.format_exc()}")
                        
                        raise Exception(f"音声ソースの作成に失敗: {source_error}")
                    
                    # 3. 音量調整
                    try:
                        audio_source = discord.PCMVolumeTransformer(audio_source)
                        audio_source.volume = 0.5
                        logger.info("Volume adjusted to 0.5")
                    except Exception as volume_error:
                        logger.error(f"Failed to adjust volume: {volume_error}")
                        # 音量調整に失敗しても続行
                    
                    # 4. 再生終了時のコールバックを設定
                    def after_playing(error):
                        if error:
                            logger.error(f"Audio playback finished with error: {error}")
                        else:
                            logger.info("Audio playback finished successfully")
                        
                        # ファイルを確実に削除
                        cleanup_audio_file(file_path, interaction.guild_id)
                        
                        # キューから次の曲を取得して再生
                        guild_id = interaction.guild_id
                        next_track = audio_queue.get_next_track(guild_id)
                        
                        if next_track:
                            logger.info(f"Playing next track from queue: {next_track.get('title', 'Unknown')}")
                            # 次の曲を再生
                            asyncio.create_task(play_next_track(interaction.guild, next_track))
                        else:
                            logger.info("No more tracks in queue, disconnecting")
                            # キューが空の場合は切断
                            try:
                                if voice_client and voice_client.is_connected():
                                    # 音声再生を明示的に停止
                                    if voice_client.is_playing():
                                        voice_client.stop()
                                        logger.info("Stopped audio playback in callback")
                                    
                                    # 少し待ってから切断（FFmpegプロセスの終了を待つ）
                                    async def safe_disconnect():
                                        await asyncio.sleep(1)
                                        try:
                                            if voice_client and voice_client.is_connected():
                                                await voice_client.disconnect()
                                                logger.info("Successfully disconnected from voice channel")
                                        except Exception as e:
                                            logger.error(f"Failed to disconnect: {e}")
                                    
                                    asyncio.create_task(safe_disconnect())
                                    logger.info("Scheduled safe disconnect from voice channel")
                            except Exception as e:
                                logger.error(f"Failed to schedule disconnect: {e}")
                    
                    logger.info("After playing callback set")
                    
                    # 5. 再生開始（エラーハンドリング強化）
                    logger.info("Starting audio playback...")
                    try:
                        # ボイスクライアントの状態を確認
                        logger.info(f"Voice client state - Connected: {voice_client.is_connected()}, Playing: {voice_client.is_playing()}")
                        
                        # 音声ソースの状態を確認
                        logger.info(f"Audio source type: {type(audio_source)}")
                        logger.info(f"Audio source ready: {hasattr(audio_source, 'read')}")
                        
                        # 再生を開始
                        voice_client.play(audio_source, after=after_playing)
                        logger.info(f"Audio playback started: {file_path}")
                        
                    except Exception as play_error:
                        logger.error(f"Failed to start playback: {play_error}")
                        logger.error(f"Play error type: {type(play_error).__name__}")
                        logger.error(f"Play error details: {str(play_error)}")
                        
                        # より詳細なエラー情報を取得
                        import traceback
                        logger.error(f"Full traceback: {traceback.format_exc()}")
                        
                        raise Exception(f"音声再生の開始に失敗: {play_error}")
                    
                    # 6. 現在の音声ファイルを記録
                    current_audio_files[interaction.guild_id] = file_path
                    logger.info(f"Recorded audio file for guild {interaction.guild_id}: {file_path}")
                    
                    # 7. 音声ソースの参照を保持
                    voice_client.source = audio_source
                    logger.info("Audio source reference stored")
                    
                    # 8. 成功メッセージを送信
                    embed = discord.Embed(
                        title="✅ 再生開始",
                        description=f"🎵 音声を再生中...\nチャンネル: {voice_channel.name}",
                        color=discord.Color.green()
                    )
                    await interaction.followup.send(embed=embed)
                    logger.info("Success message sent to user")
                    
                except Exception as e:
                    logger.error(f"Audio playback error: {e}")
                    logger.error(f"Error type: {type(e).__name__}")
                    logger.error(f"Error details: {str(e)}")
                    
                    # エラーの詳細をユーザーに表示
                    error_message = f"❌ 音声の再生に失敗しました。\nエラー: {str(e)}"
                    await interaction.followup.send(error_message)
                    
                    # エラーが発生した場合もファイルを確実に削除
                    cleanup_audio_file(file_path, interaction.guild_id)
            else:
                await interaction.followup.send("❌ 音声ファイルが見つかりません。")
        else:
            await interaction.followup.send("❌ 音声のダウンロードに失敗しました。")
            
    except Exception as e:
        logger.error(f"Play command error: {e}")
        embed = discord.Embed(
            title="❌ エラーが発生しました",
            description=f"エラー: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

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
        
        # 少し待ってから切断（FFmpegプロセスの終了を待つ）
        await asyncio.sleep(1)
        
        # ボイスチャンネルから切断
        await voice_client.disconnect()
        logger.info("Disconnected from voice channel")
        
        embed = discord.Embed(
            title="🛑 再生停止",
            description="音声再生を停止し、ボイスチャンネルから切断しました。",
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
        description="音楽キューがクリアされました。",
        color=discord.Color.orange()
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

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
        '/download': 'YouTube動画をダウンロードします',
        '/download_mp3': 'YouTube動画をMP3に変換してダウンロードします',
        '/quality': '利用可能な画質を表示します',
        '/play': 'YouTube音声をボイスチャンネルで再生します（キューに追加）',
        '/pause': '音声再生を一時停止します',
        '/resume': '音声再生を再開します',
        '/stop': '音声再生を停止し、ボイスチャンネルから切断します',
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
        value="• ファイルサイズは25MB以下に制限されています\n• 個人使用目的でのみ使用してください\n• YouTubeの利用規約を遵守してください",
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
    main()
