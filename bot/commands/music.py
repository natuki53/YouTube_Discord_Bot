"""
音楽関連コマンド

音声再生、キュー管理、プレイバック制御コマンド
"""

import asyncio
import os
import time
import discord
from discord.ext import commands
from discord import app_commands
import logging

from ..audio import AudioQueue, AudioPlayer, TrackInfo
from ..youtube import get_title_from_url, validate_youtube_url, normalize_youtube_url, is_playlist_url
from ..utils.file_utils import cleanup_old_audio_files, force_kill_ffmpeg_processes, get_deletion_queue_status

logger = logging.getLogger(__name__)

def setup_music_commands(bot, audio_queue: AudioQueue, audio_player: AudioPlayer, download_dir: str):
    """音楽関連コマンドをセットアップ"""

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
        
        # URL検証
        if not validate_youtube_url(url):
            await interaction.response.send_message(
                "❌ 有効なYouTube URLを入力してください。",
                ephemeral=True
            )
            return
        
        # プレイリストURL検証
        if is_playlist_url(url):
            embed = discord.Embed(
                title="❌ プレイリストは登録できません",
                description="申し訳ございませんが、プレイリストURLには対応していません。\n\n**代替案:**\n• 個別の動画URLを使用してください\n• プレイリスト内の特定の動画を選んで再生してください",
                color=discord.Color.red()
            )
            embed.add_field(
                name="💡 ヒント",
                value="プレイリスト内の動画を個別に選択して `/play` コマンドで追加できます。",
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # URLを正規化
        normalized_url = normalize_youtube_url(url)
        if normalized_url:
            url = normalized_url
        
        guild_id = interaction.guild_id
        voice_client = interaction.guild.voice_client
        
        # ボイスチャンネルに接続していない場合は接続を試行
        if not voice_client or not voice_client.is_connected():
            try:
                voice_channel = interaction.user.voice.channel
                if not voice_channel:
                    await interaction.response.send_message(
                        "❌ ボイスチャンネルに接続してから使用してください。",
                        ephemeral=True
                    )
                    return
                
                voice_client = await voice_channel.connect()
                logger.info(f"Connected to voice channel: {voice_channel.name}")
                
                # 接続後に再度確認
                if not voice_client.is_connected():
                    await interaction.response.send_message(
                        "❌ ボイスチャンネルへの接続に失敗しました。",
                        ephemeral=True
                    )
                    return
                    
            except Exception as e:
                logger.exception("Failed to connect to voice channel")
                await interaction.response.send_message(
                    "❌ ボイスチャンネルに接続できませんでした。権限を確認してください。",
                    ephemeral=True
                )
                return
        
        # 即座に応答
        embed = discord.Embed(
            title="🎵 音声準備開始",
            description=f"**URL：** {url}\n👤 **リクエスト:** {interaction.user.display_name}",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="⏳ ステータス",
            value="動画情報を取得中...",
            inline=False
        )
        await interaction.response.send_message(embed=embed)
        
        # URLからタイトルを取得（まずYouTubeDownloaderを試し、失敗した場合はget_title_from_urlを使用）
        from ..youtube import YouTubeDownloader
        downloader = YouTubeDownloader()
        video_title = downloader.get_video_title(url)
        
        # YouTubeDownloaderでタイトル取得に失敗した場合は、url_handlerの関数を使用
        if video_title == "Unknown Title":
            video_title = get_title_from_url(url)
        
        # トラック情報を作成
        track_info = TrackInfo(
            url=url,
            title=video_title,
            user=interaction.user.display_name,
            added_at=interaction.created_at
        )
        
        # 再生ロックを取得して同時実行を制御
        playback_lock = await audio_queue.get_playback_lock(guild_id)
        
        async with playback_lock:
            # テキストチャンネルIDを保存
            audio_queue.set_text_channel(guild_id, interaction.channel_id)
            
            # 既に再生中、または再生開始処理中の場合の判定
            is_currently_playing = audio_player.is_playing(voice_client) or audio_queue.is_playing(guild_id)
            is_starting_playback = audio_queue.is_starting_playback_active(guild_id)
            
            if is_currently_playing or is_starting_playback:
                # 既に再生中または開始処理中の場合
                if is_starting_playback:
                    # 同時実行の場合は保留リクエストに追加
                    audio_queue.add_pending_request(guild_id, track_info)
                    
                    # 現在ダウンロード中のタイトルと保留中のタイトルを取得
                    current_playing = audio_queue.get_now_playing(guild_id)
                    current_title = current_playing.title if current_playing else "不明"
                    
                    # 保留中のリクエスト数を確認（新しい曲が追加済み）
                    pending_requests = audio_queue.get_pending_requests(guild_id)
                    total_participants = len(pending_requests) + 1  # 現在ダウンロード中の曲も含む
                    
                    # 保留リクエスト通知（競争する主要2つのタイトルと説明）
                    embed = discord.Embed(
                        title="🏁 ダウンロード競争開始",
                        color=discord.Color.orange()
                    )
                    
                    if total_participants == 2:
                        # 2曲の場合：両方表示
                        embed.add_field(
                            name="🎵 競争するタイトル",
                            value=f"1️⃣ **{current_title}**\n2️⃣ **{video_title}**",
                            inline=False
                        )
                    else:
                        # 3曲以上の場合：最初の2曲と参加者数を表示
                        embed.add_field(
                            name="🎵 競争するタイトル",
                            value=f"1️⃣ **{current_title}**\n2️⃣ **{video_title}**\n\n📊 **総参加者：** {total_participants}曲",
                            inline=False
                        )
                    
                    embed.add_field(
                        name="⚡ 競争モード",
                        value="先にダウンロードが完了した曲が再生され、\n他の曲は自動的にキューに追加されます",
                        inline=False
                    )
                    await interaction.followup.send(embed=embed)
                    
                    # 競争ダウンロードを開始
                    task_id = f"guild_{guild_id}_competitive_{hash(track_info.url)}"
                    task = asyncio.create_task(start_competitive_download(
                        guild_id, track_info, audio_queue, audio_player, voice_client
                    ))
                    audio_queue.register_task(task_id, task)
                else:
                    # 通常のキュー追加
                    audio_queue.add_track(guild_id, track_info)
                    
                    # 事前ダウンロードを開始
                    audio_queue.start_preload(guild_id)
                    
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
                    
                    # バックグラウンドでダウンロード開始
                    task_id = f"guild_{guild_id}_background_{hash(track_info.url)}"
                    task = asyncio.create_task(start_background_download(guild_id, track_info, audio_queue))
                    audio_queue.register_task(task_id, task)
            else:
                # 再生中でない場合は即座に再生開始
                # アイドルタイムアウトをキャンセル（新しい再生開始のため）
                audio_queue.cancel_idle_timeout(guild_id)
                
                # 再生開始フラグを設定
                audio_queue.set_starting_playback(guild_id, True)
                
                # 即座に再生開始
                task_id = f"guild_{guild_id}_play_{hash(track_info.url)}"
                task = asyncio.create_task(download_and_play_track(
                    guild_id, track_info, voice_client, audio_queue, audio_player, interaction.channel_id
                ))
                audio_queue.register_task(task_id, task)

    @bot.tree.command(name='stop', description='Stop audio playback and disconnect from voice channel')
    async def stop_audio(interaction: discord.Interaction):
        """音声再生を停止し、ボイスチャンネルから切断するコマンド"""
        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.response.send_message(
                "❌ ボイスチャンネルに接続していません。",
                ephemeral=True
            )
            return
        
        try:
            guild_id = interaction.guild_id
            
            # アイドルタイムアウトをキャンセル
            audio_queue.cancel_idle_timeout(guild_id)
            
            # 音声再生を停止
            audio_player.stop_playback(guild_id, voice_client)
            
            # キューと現在再生中のトラックをクリア
            audio_queue.clear_queue(guild_id)
            audio_queue.clear_now_playing(guild_id)
            
            # ループもリセット
            audio_queue.set_loop(guild_id, False)
            
            # 事前ダウンロードもキャンセル
            audio_queue.cancel_downloads(guild_id)
            
            # 保留中のリクエストもクリア
            audio_queue.clear_pending_requests(guild_id)
            
            # 再生開始フラグもリセット
            audio_queue.set_starting_playback(guild_id, False)
            
            # 少し待ってから切断
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
            logger.exception("Stop command error")
            await interaction.response.send_message("❌ 音声停止に失敗しました。")

    @bot.tree.command(name='pause', description='Pause audio playback')
    async def pause_audio(interaction: discord.Interaction):
        """音声再生を一時停止するコマンド"""
        voice_client = interaction.guild.voice_client
        
        if not voice_client or not voice_client.is_connected():
            await interaction.response.send_message(
                "❌ ボイスチャンネルに接続していません。",
                ephemeral=True
            )
            return
            
        if not audio_player.is_playing(voice_client):
            await interaction.response.send_message(
                "❌ 現在音声を再生していません。",
                ephemeral=True
            )
            return
        
        # テキストチャンネルIDを保存
        guild_id = interaction.guild_id
        audio_queue.set_text_channel(guild_id, interaction.channel_id)
        
        try:
            if audio_player.pause_playback(voice_client):
                embed = discord.Embed(
                    title="⏸️ 一時停止",
                    description="音声再生を一時停止しました。",
                    color=discord.Color.yellow()
                )
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message("❌ 一時停止に失敗しました。")
        except Exception as e:
            logger.exception("Pause command error")
            await interaction.response.send_message("❌ 一時停止に失敗しました。")

    @bot.tree.command(name='resume', description='Resume audio playback')
    async def resume_audio(interaction: discord.Interaction):
        """音声再生を再開するコマンド"""
        voice_client = interaction.guild.voice_client
        
        if not voice_client or not voice_client.is_connected():
            await interaction.response.send_message(
                "❌ ボイスチャンネルに接続していません。",
                ephemeral=True
            )
            return
            
        if not audio_player.is_paused(voice_client):
            await interaction.response.send_message(
                "❌ 現在音声は一時停止されていません。",
                ephemeral=True
            )
            return
        
        # テキストチャンネルIDを保存
        guild_id = interaction.guild_id
        audio_queue.set_text_channel(guild_id, interaction.channel_id)
        
        try:
            if audio_player.resume_playback(voice_client):
                embed = discord.Embed(
                    title="▶️ 再生再開",
                    description="音声再生を再開しました。",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message("❌ 再生再開に失敗しました。")
        except Exception as e:
            logger.exception("Resume command error")
            await interaction.response.send_message("❌ 再生再開に失敗しました。")

    @bot.tree.command(name='queue', description='Show current music queue')
    async def show_queue(interaction: discord.Interaction):
        """現在の音楽キューを表示するコマンド"""
        guild_id = interaction.guild_id
        queue = audio_queue.get_queue(guild_id)
        now_playing = audio_queue.get_now_playing(guild_id)
        
        embed = discord.Embed(
            title="🎵 音楽キュー",
            color=discord.Color.blue()
        )
        
        if now_playing:
            loop_status = " 🔁" if audio_queue.is_loop_enabled(guild_id) else ""
            embed.add_field(
                name=f"🎶 現在再生中{loop_status}",
                value=f"**{now_playing.title}**\n👤 追加者: {now_playing.user}",
                inline=False
            )
            
            # ループが有効な場合の説明を追加
            if audio_queue.is_loop_enabled(guild_id):
                embed.add_field(
                    name="🔁 ループモード",
                    value="この曲を繰り返し再生します。\n`/loop` コマンドで無効にできます。",
                    inline=False
                )
        
        if queue:
            queue_text = ""
            for i, track in enumerate(queue[:10], 1):  # 最大10曲まで表示
                queue_text += f"{i}. **{track.title}**\n   追加者: {track.user}\n"
            
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
        
        # キューの長さを取得してからクリア
        queue_length = audio_queue.get_queue_length(guild_id)
        
        if queue_length == 0:
            embed = discord.Embed(
                title="📋 キューは空です",
                description="クリアするキューがありません。",
                color=discord.Color.blue()
            )
        else:
            audio_queue.clear_queue(guild_id)
            
            embed = discord.Embed(
                title="🗑️ キューをクリア",
                description=f"{queue_length}曲のキューがクリアされました。\n現在再生中の曲は影響を受けません。",
                color=discord.Color.orange()
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @bot.tree.command(name='preload', description='事前ダウンロードの状況を表示')
    async def show_preload_status(interaction: discord.Interaction):
        """事前ダウンロードの状況を表示"""
        try:
            guild_id = interaction.guild.id
            
            # ダウンロード統計を取得
            stats = audio_queue.get_download_stats(guild_id)
            queue_stats = audio_queue.get_guild_stats(guild_id)
            
            # 埋め込みメッセージを作成
            embed = discord.Embed(
                title="📥 事前ダウンロード状況",
                color=discord.Color.blue()
            )
            
            # 基本統計
            embed.add_field(
                name="📊 キュー情報",
                value=f"**現在のキュー:** {queue_stats['queue_length']}曲\n**再生中:** {'あり' if queue_stats['is_playing'] else 'なし'}",
                inline=True
            )
            
            # ダウンロード統計
            total_downloads = sum(stats.values())
            if total_downloads > 0:
                embed.add_field(
                    name="💾 ダウンロード状況",
                    value=f"**完了:** {stats['completed']}曲\n**進行中:** {stats['downloading']}曲\n**待機中:** {stats['pending']}曲\n**失敗:** {stats['failed']}曲",
                    inline=True
                )
            else:
                embed.add_field(
                    name="💾 ダウンロード状況",
                    value="**ダウンロード中の曲はありません**",
                    inline=True
                )
            
            # 現在再生中の曲
            if queue_stats['current_track']:
                current = queue_stats['current_track']
                embed.add_field(
                    name="🎵 現在再生中",
                    value=f"**{current.title}**",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.exception("Error in preload status command")
            await interaction.response.send_message(
                "❌ 事前ダウンロード状況の取得に失敗しました。",
                ephemeral=True
            )
    
    @bot.tree.command(name='cleanup', description='完了済みのダウンロードファイルをクリーンアップ')
    async def cleanup_downloads(interaction: discord.Interaction):
        """完了済みのダウンロードファイルをクリーンアップ"""
        try:
            guild_id = interaction.guild.id
            
            # クリーンアップ実行
            audio_queue.cleanup_completed_downloads(guild_id)
            
            # バックグラウンド削除キューの状況も表示
            queue_status = get_deletion_queue_status()
            
            status_text = "✅ ダウンロードファイルのクリーンアップが完了しました。"
            if queue_status.get('queue_size', 0) > 0:
                status_text += f"\n\n📋 バックグラウンド削除キュー: {queue_status['queue_size']}ファイル"
                if queue_status.get('worker_running', False):
                    status_text += " (処理中)"
                else:
                    status_text += " (待機中)"
            
            await interaction.response.send_message(
                status_text,
                ephemeral=True
            )
            
        except Exception as e:
            logger.exception("Error in cleanup command")
            await interaction.response.send_message(
                "❌ クリーンアップに失敗しました。",
                ephemeral=True
            )
    
    @bot.tree.command(name='debug_files', description='ファイル削除の状況とギルド状態をデバッグ表示')
    async def debug_files(interaction: discord.Interaction):
        """ファイル削除の状況とギルド状態をデバッグ表示"""
        try:
            guild_id = interaction.guild_id
            
            # バックグラウンド削除キューの状況を取得
            queue_status = get_deletion_queue_status()
            
            embed = discord.Embed(
                title="🔧 デバッグ情報",
                color=discord.Color.blue()
            )
            
            # ギルドの音楽状態
            current_track = audio_queue.get_now_playing(guild_id)
            loop_enabled = audio_queue.is_loop_enabled(guild_id)
            queue_length = audio_queue.get_queue_length(guild_id)
            is_playing = audio_queue.is_playing(guild_id)
            
            music_status = []
            music_status.append(f"**再生中:** {'はい' if is_playing else 'いいえ'}")
            if current_track:
                music_status.append(f"**現在の曲:** {current_track.title}")
                if current_track.file_path:
                    music_status.append(f"**ファイル:** {os.path.basename(current_track.file_path)}")
            else:
                music_status.append("**現在の曲:** なし")
            music_status.append(f"**ループ:** {'有効' if loop_enabled else '無効'}")
            music_status.append(f"**キュー:** {queue_length}曲")
            
            embed.add_field(
                name="🎵 音楽状態",
                value="\n".join(music_status),
                inline=False
            )
            
            # キューの状況
            embed.add_field(
                name="📋 削除キュー",
                value=f"**キューサイズ:** {queue_status.get('queue_size', 0)}ファイル\n**ワーカー状態:** {'動作中' if queue_status.get('worker_running', False) else '停止中'}",
                inline=False
            )
            
            # キュー内のファイル一覧（最大5件）
            queue_items = queue_status.get('queue_items', [])
            if queue_items:
                file_list = []
                for i, file_path in enumerate(queue_items[:5]):
                    # ファイル名のみを表示
                    file_name = os.path.basename(file_path)
                    file_list.append(f"{i+1}. {file_name}")
                
                if len(queue_items) > 5:
                    file_list.append(f"... 他 {len(queue_items) - 5} ファイル")
                
                embed.add_field(
                    name="📁 削除待ちファイル",
                    value="\n".join(file_list),
                    inline=False
                )
            else:
                embed.add_field(
                    name="📁 削除待ちファイル",
                    value="なし",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.exception("Error in debug_files command")
            await interaction.response.send_message(
                "❌ デバッグ情報の取得に失敗しました。",
                ephemeral=True
            )

    @bot.tree.command(name='skip', description='Skip current track and play next track in queue')
    async def skip_audio(interaction: discord.Interaction):
        """現在再生中の曲をスキップするコマンド"""
        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.response.send_message(
                "❌ ボイスチャンネルに接続していません。",
                ephemeral=True
            )
            return
        
        if not audio_player.is_playing(voice_client):
            await interaction.response.send_message(
                "❌ 現在音声を再生していません。",
                ephemeral=True
            )
            return
        
        try:
            guild_id = interaction.guild_id
            current_track = audio_queue.get_now_playing(guild_id)
            current_title = current_track.title if current_track else 'Unknown Track'
            
            # テキストチャンネルIDを保存（次の曲の通知のため）
            audio_queue.set_text_channel(guild_id, interaction.channel_id)
            
            # アイドルタイムアウトをキャンセル（スキップ処理のため）
            audio_queue.cancel_idle_timeout(guild_id)
            
            # 次の曲があるかチェック（ループを考慮）
            if audio_queue.is_loop_enabled(guild_id):
                # ループが有効な場合は同じ曲をリピート
                next_title = current_title
            else:
                # ループが無効な場合は通常のキューから次の曲を取得
                queue = audio_queue.get_queue(guild_id)
                next_track = queue[0] if queue else None
                next_title = next_track.title if next_track else None
            
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
            else:
                embed.add_field(
                    name="📋 キュー",
                    value="次の曲はありません。5分後に自動切断されます。",
                    inline=False
                )
            
            # ループ状態の表示
            if audio_queue.is_loop_enabled(guild_id):
                embed.add_field(
                    name="🔁 ループ",
                    value="有効" if next_title else "無効化されました",
                    inline=True
                )
            
            await interaction.response.send_message(embed=embed)
            logger.info(f"⏭️ Skip command executed for guild {guild_id}: {current_title} -> {next_title or 'None'}")
            
            # ループが有効でキューがない場合、スキップでループを無効化
            if audio_queue.is_loop_enabled(guild_id) and not audio_queue.has_queue(guild_id):
                logger.info(f"Disabling loop due to skip with empty queue for guild {guild_id}")
                audio_queue.set_loop(guild_id, False)
            
            # 現在の曲を停止（これにより次の曲が自動再生される）
            voice_client.stop()
            logger.info(f"Skipped track: {current_title}")
            
        except Exception as e:
            logger.exception("Skip command error")
            await interaction.response.send_message(
                "❌ スキップに失敗しました。",
                ephemeral=True
            )

    @bot.tree.command(name='loop', description='Toggle loop mode for current track')
    async def loop_audio(interaction: discord.Interaction):
        """現在再生中の曲をループするコマンド"""
        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.response.send_message(
                "❌ ボイスチャンネルに接続していません。",
                ephemeral=True
            )
            return
        
        guild_id = interaction.guild_id
        
        # 現在再生中の曲があるかチェック
        if not audio_player.is_playing(voice_client):
            logger.debug(f"Loop command failed: not playing audio for guild {guild_id}")
            await interaction.response.send_message(
                "❌ 現在音声を再生していません。\nループを有効にするには、まず曲を再生してください。",
                ephemeral=True
            )
            return
        
        try:
            # 現在再生中のトラック情報を取得
            current_track = audio_queue.get_now_playing(guild_id)
            if not current_track:
                logger.debug(f"Loop command failed: no current track for guild {guild_id}")
                await interaction.response.send_message(
                    "❌ 現在再生中のトラック情報が見つかりません。",
                    ephemeral=True
                )
                return
            
            # ループを切り替え
            loop_enabled = audio_queue.toggle_loop(guild_id)
            
            if loop_enabled:
                embed = discord.Embed(
                    title="🔁 ループ有効",
                    description=f"**現在の曲をループします**\n\n🎵 **ループ中の曲：** {current_track.title}",
                    color=discord.Color.green()
                )
                embed.add_field(
                    name="💡 ヒント",
                    value="もう一度 `/loop` コマンドでループを無効にできます。",
                    inline=False
                )
            else:
                # ループ無効時にファイルをクリーンアップ（次の曲のため）
                audio_player.cleanup_loop_file(guild_id)
                logger.info(f"Loop disabled, cleaned up loop file for guild {guild_id}")
                
                embed = discord.Embed(
                    title="🔁 ループ無効",
                    description="**ループを無効にしました**\n\n曲が終了したら次の曲に進みます。",
                    color=discord.Color.orange()
                )
                
            await interaction.response.send_message(embed=embed)
            logger.info(f"Loop toggled for guild {guild_id}: {loop_enabled}")
            
        except Exception as e:
            logger.exception("Loop command error")
            await interaction.response.send_message(
                "❌ ループ設定の変更に失敗しました。",
                ephemeral=True
            )

async def download_and_play_track(guild_id: int, track_info: TrackInfo, voice_client, 
                                 audio_queue: AudioQueue, audio_player: AudioPlayer, text_channel_id: int = None):
    """トラックをダウンロードして再生する"""
    async def _safe_send_to_text(embed: discord.Embed = None, content: str = None):
        """失敗しても再生処理を止めない安全な通知送信"""
        try:
            channel_id_for_notification = text_channel_id or audio_queue.get_text_channel(guild_id)
            if not channel_id_for_notification or not voice_client or not voice_client.guild:
                return
            channel = voice_client.guild.get_channel(channel_id_for_notification)
            if not channel:
                return
            if not channel.permissions_for(voice_client.guild.me).send_messages:
                return
            await asyncio.wait_for(channel.send(content=content, embed=embed), timeout=10.0)
        except Exception:
            logger.exception("Failed to send error notification for guild %s", guild_id)

    try:
        # テキストチャンネルIDが指定されていない場合は、保存されているものを使用
        if text_channel_id is None:
            text_channel_id = audio_queue.get_text_channel(guild_id)
        # まず事前ダウンロード済みのトラックがあるかチェック
        preloaded_track = audio_queue.get_preloaded_track(guild_id, track_info.url)
        
        if preloaded_track and preloaded_track.file_path:
            # 事前ダウンロード済みのトラックを使用
            logger.info(f"Using preloaded track: {preloaded_track.title}")
            track_info = preloaded_track  # ダウンロード済みの情報を使用
            success = True
        else:
            # リアルタイムダウンロード
            logger.info(f"Real-time downloading: {track_info.title}")
            from ..youtube import YouTubeDownloader
            
            downloader = YouTubeDownloader()
            
            # MP3をダウンロード
            download_result = await asyncio.get_event_loop().run_in_executor(
                None, downloader.download_mp3, track_info.url
            )
            
            # download_mp3は(bool, str)のタプルを返すため、成功可否のみを取得
            if isinstance(download_result, tuple):
                success, downloaded_title = download_result
                # タイトルが取得できた場合は更新
                if downloaded_title and downloaded_title != "Unknown Title":
                    track_info.title = downloaded_title
            else:
                # 後方互換性のため、boolが返された場合はそのまま使用
                success = download_result
            
            if success:
                # 最新のMP3ファイルを取得
                file_path = downloader.get_latest_mp3_file()
                track_info.file_path = file_path

        # ここまでで失敗していたら、ボイスに居残りしないように切断して終了
        if not success or not track_info.file_path:
            logger.warning("Download/convert failed for guild %s, disconnecting from voice to avoid lingering", guild_id)
            audio_queue.clear_now_playing(guild_id)
            audio_queue.set_starting_playback(guild_id, False)

            embed = discord.Embed(
                title="❌ 再生に失敗しました",
                description="ダウンロード/変換に失敗したため、ボイスチャンネルから切断しました。\n"
                            "FFmpeg の導入や yt-dlp の設定（Deno等）を確認してください。",
                color=discord.Color.red()
            )
            await _safe_send_to_text(embed=embed)

            try:
                # 再生中なら停止してから切断
                if voice_client and voice_client.is_connected():
                    if voice_client.is_playing() or voice_client.is_paused():
                        voice_client.stop()
                    await voice_client.disconnect()
                    logger.info("Disconnected from voice after failure (guild %s)", guild_id)
            except Exception:
                logger.exception("Failed to disconnect voice client after failure (guild %s)", guild_id)
            finally:
                # 最小限の状態クリア
                audio_queue.clear_queue(guild_id)
                audio_queue.set_loop(guild_id, False)
                audio_queue.cancel_downloads(guild_id)
                audio_queue.clear_pending_requests(guild_id)
            return
        
        if success and track_info.file_path:
            # 再生終了時のコールバック
            async def on_finish(error, guild_id, track_info):
                # 完了したダウンロードをクリーンアップ
                audio_queue.cleanup_completed_downloads(guild_id)
                
                # 次の曲を再生（ループの場合は同じ曲を再生）
                next_track = audio_queue.get_next_track(guild_id)
                if next_track:
                    logger.info(f"🎵 Playing next track for guild {guild_id}: {next_track.title}")
                    
                    # ループでない場合のみ現在再生中のトラックをクリア
                    # （ループの場合はget_next_trackで同じ曲が返され、new_playingが再設定される）
                    if not audio_queue.is_loop_enabled(guild_id):
                        audio_queue.clear_now_playing(guild_id)
                        # 次の曲の事前ダウンロードを再開
                        audio_queue.start_preload(guild_id)
                    else:
                        logger.info(f"🔁 Loop enabled, repeating track: {next_track.title}")
                    
                    # テキストチャンネルIDを渡して次の曲も通知を表示
                    # 保存されているテキストチャンネルIDを取得
                    saved_channel_id = audio_queue.get_text_channel(guild_id)
                    channel_id_to_use = text_channel_id or saved_channel_id
                    logger.info(f"📢 Using text channel {channel_id_to_use} for notification (text_channel_id={text_channel_id}, saved={saved_channel_id})")
                    await download_and_play_track(guild_id, next_track, voice_client, audio_queue, audio_player, channel_id_to_use)
                else:
                    # 現在再生中のトラックをクリア（次の曲がない場合）
                    audio_queue.clear_now_playing(guild_id)
                    # 次がない場合：3分間アイドルなら自動切断
                    if voice_client and voice_client.is_connected():
                        audio_queue.start_idle_timeout(guild_id, voice_client)
            
            # 既に再生中でない場合のみ再生開始
            if not audio_player.is_playing(voice_client):
                # 再生開始前に現在再生中のトラックを設定
                audio_queue.set_now_playing(guild_id, track_info)
                
                # ループかどうかを判定
                is_loop_track = audio_queue.is_loop_enabled(guild_id)
                logger.info(f"🔄 Loop check for guild {guild_id}: is_loop_enabled={is_loop_track}, track={track_info.title}")
                
                # 再生開始
                success = await audio_player.play_track(guild_id, track_info, voice_client, on_finish, is_loop_track)
                
                # 再生開始処理完了をマーク（成功・失敗問わず）
                audio_queue.set_starting_playback(guild_id, False)
                
                # 再生開始に失敗した場合は now_playing をクリア
                if not success:
                    audio_queue.clear_now_playing(guild_id)
                    logger.error(f"Failed to start playback for guild {guild_id}, track: {track_info.title}")
                    # 失敗時は切断（居残り防止）
                    try:
                        embed = discord.Embed(
                            title="❌ 再生開始に失敗しました",
                            description="音声再生の開始に失敗したため、ボイスチャンネルから切断しました。",
                            color=discord.Color.red()
                        )
                        await _safe_send_to_text(embed=embed)
                        if voice_client and voice_client.is_connected():
                            await voice_client.disconnect()
                    except Exception:
                        logger.exception("Failed to disconnect after playback start failure (guild %s)", guild_id)
                else:
                    logger.info(f"Started playback for guild {guild_id}, track: {track_info.title}, loop: {is_loop_track}")
            else:
                logger.warning(f"Already playing audio for guild {guild_id}, skipping playback of: {track_info.title}")
                success = False
                # 再生開始処理完了をマーク
                audio_queue.set_starting_playback(guild_id, False)
            
            if success:
                # 再生開始通知を送信（テキストチャンネルIDを取得）
                channel_id_for_notification = text_channel_id or audio_queue.get_text_channel(guild_id)
                
                if channel_id_for_notification:
                    # ループ時か通常再生かを判定
                    is_loop_replay = audio_queue.is_loop_enabled(guild_id)
                    
                    # 再生開始通知
                    if is_loop_replay:
                        embed = discord.Embed(
                            title="🔁 ループ再生",
                            description=f"**タイトル：** {track_info.title}",
                            color=discord.Color.orange()
                        )
                    else:
                        embed = discord.Embed(
                            title="🎵 再生開始",
                            description=f"**タイトル：** {track_info.title}",
                            color=discord.Color.green()
                        )
                
                    # URL情報を追加（短縮表示）
                    if len(track_info.url) > 60:
                        short_url = track_info.url[:60] + "..."
                    else:
                        short_url = track_info.url
                    embed.add_field(
                        name="🔗 URL",
                        value=f"[リンク]({track_info.url})",
                        inline=False
                    )
                    
                    # ファイル情報を追加
                    if track_info.file_path:
                        try:
                            from ..youtube import YouTubeDownloader
                            downloader = YouTubeDownloader()
                            file_size = downloader.get_file_size_mb(track_info.file_path)
                            embed.add_field(
                                name="📁 ファイル",
                                value=f"{file_size:.1f} MB",
                                inline=True
                            )
                        except Exception:
                            pass
                    
                    # キューの状況を追加
                    queue_length = audio_queue.get_queue_length(guild_id)
                    if queue_length > 0:
                        embed.add_field(
                            name="📋 キュー",
                            value=f"次に{queue_length}曲待機中",
                            inline=True
                        )
                    
                    # ユーザー情報を追加
                    if hasattr(track_info, 'user') and track_info.user:
                        embed.add_field(
                            name="👤 リクエスト",
                            value=track_info.user,
                            inline=True
                        )
                    
                    # ループ状態の表示
                    if audio_queue.is_loop_enabled(guild_id):
                        embed.add_field(
                            name="🔁 ループ",
                            value="有効",
                            inline=True
                        )
                    
                    try:
                        channel = voice_client.guild.get_channel(channel_id_for_notification)
                        if channel and channel.permissions_for(voice_client.guild.me).send_messages:
                            # 通知送信をasyncio.create_taskで安全に実行
                            async def send_notification():
                                try:
                                    await asyncio.wait_for(channel.send(embed=embed), timeout=10.0)
                                    logger.info(f"✅ Playback notification sent to channel {channel_id_for_notification} for guild {guild_id}: {track_info.title}")
                                except asyncio.TimeoutError:
                                    logger.warning(f"Notification send timeout for channel {channel_id_for_notification}")
                                except discord.HTTPException as e:
                                    logger.warning(f"Discord HTTP error when sending notification: {e}")
                                except discord.Forbidden:
                                    logger.warning(f"No permission to send message in channel {channel_id_for_notification}")
                                except Exception as e:
                                    logger.error(f"Error sending notification: {e}")
                            
                            # バックグラウンドで通知を送信（エラーが発生しても再生は継続）
                            task_id = f"guild_{guild_id}_notification_{int(time.time() * 1000)}"
                            task = asyncio.create_task(send_notification())
                            audio_queue.register_task(task_id, task)
                        else:
                            logger.warning(f"Cannot send notification: channel not found or no permission for channel {channel_id_for_notification}")
                            
                    except Exception as e:
                        logger.error(f"Failed to setup notification: {e}")
                else:
                    logger.warning(f"No text channel available for notification in guild {guild_id}")
        
    except asyncio.CancelledError:
        logger.info(f"Download and play task cancelled for guild {guild_id}")
        raise  # asyncio.CancelledErrorは再発生させる
    except discord.errors.ConnectionClosed:
        logger.warning(f"Discord connection closed during playback for guild {guild_id}")
    except FileNotFoundError as e:
        logger.error(f"Audio file not found for guild {guild_id}: {e}")
    except PermissionError as e:
        logger.error(f"Permission error during playback for guild {guild_id}: {e}")
    except Exception as e:
        logger.exception("Unexpected error in download_and_play_track for guild %s", guild_id)
        # エラー発生時は状態をクリーンアップして次の曲を試行（無ければ切断）
        try:
            audio_queue.clear_now_playing(guild_id)
            next_track = audio_queue.get_next_track(guild_id)
            if next_track and voice_client and voice_client.is_connected():
                logger.info(f"Attempting to play next track after error for guild {guild_id}")
                saved_channel_id = audio_queue.get_text_channel(guild_id)
                await download_and_play_track(guild_id, next_track, voice_client, audio_queue, audio_player, saved_channel_id)
            else:
                if voice_client and voice_client.is_connected():
                    try:
                        embed = discord.Embed(
                            title="❌ エラーが発生しました",
                            description="エラーが発生したため、ボイスチャンネルから切断しました。",
                            color=discord.Color.red()
                        )
                        await _safe_send_to_text(embed=embed)
                        await voice_client.disconnect()
                    except Exception:
                        logger.exception("Failed to disconnect after error (guild %s)", guild_id)
        except Exception as recovery_error:
            logger.exception("Failed to recover from error for guild %s", guild_id)
    finally:
        # 失敗パスで starting_playback が残り続けるのを防ぐ
        if audio_queue.is_starting_playback_active(guild_id):
            audio_queue.set_starting_playback(guild_id, False)

async def start_competitive_download(guild_id: int, track_info: TrackInfo, audio_queue: AudioQueue, 
                                   audio_player: AudioPlayer, voice_client):
    """競争ダウンロードを開始（先に完了した方が再生される）"""
    try:
        from ..youtube import YouTubeDownloader
        
        logger.info(f"🏁 Starting competitive download for guild {guild_id}: {track_info.title}")
        
        downloader = YouTubeDownloader()
        
        # ダウンロードを実行
        download_result = await asyncio.get_event_loop().run_in_executor(
            None, downloader.download_mp3, track_info.url
        )
        
        # ダウンロード結果を処理
        if isinstance(download_result, tuple):
            success, downloaded_title = download_result
            if downloaded_title and downloaded_title != "Unknown Title":
                track_info.title = downloaded_title
        else:
            success = download_result
        
        if success:
            # ファイルパスを設定
            file_path = downloader.get_latest_mp3_file()
            track_info.file_path = file_path
            
            # 再生ロックを取得して競争の勝者を決定
            playback_lock = await audio_queue.get_playback_lock(guild_id)
            async with playback_lock:
                # 勝者判定：まだ再生開始処理中で、実際の再生は始まっていない場合
                is_still_racing = (
                    audio_queue.is_starting_playback_active(guild_id) and 
                    not audio_player.is_playing(voice_client) and 
                    not audio_queue.is_playing(guild_id)
                )
                
                if is_still_racing:
                    # この曲が勝者となり、即座に再生開始
                    logger.info(f"🏆 Competitive download winner for guild {guild_id}: {track_info.title}")
                    
                    # 保留中のリクエストをキューに移動（勝者の曲は除く）
                    audio_queue.move_pending_to_queue(guild_id, track_info)
                    
                    # 勝者の曲を再生
                    await download_and_play_track(
                        guild_id, track_info, voice_client, audio_queue, audio_player, 
                        audio_queue.get_text_channel(guild_id)
                    )
                else:
                    # 既に他の曲が再生開始している場合はキューに追加
                    logger.info(f"🥈 Competitive download runner-up, adding to queue for guild {guild_id}: {track_info.title}")
                    audio_queue.add_track(guild_id, track_info)
        else:
            logger.error(f"Competitive download failed for guild {guild_id}: {track_info.title}")
            
    except Exception as e:
        logger.exception("Error in competitive download for guild %s", guild_id)

async def start_background_download(guild_id: int, track_info: TrackInfo, audio_queue: AudioQueue):
    """バックグラウンドでダウンロード開始"""
    try:
        from ..youtube import YouTubeDownloader
        
        # グローバルダウンロード状況をチェック
        global_status = YouTubeDownloader.get_download_status(track_info.url)
        
        if global_status in ['downloading', 'completed']:
            logger.info(f"Download already in progress or completed globally: {track_info.title}")
            if global_status == 'completed':
                audio_queue.set_download_status(guild_id, track_info.url, True)
            return
        
        downloader = YouTubeDownloader()
        
        # MP3をダウンロード（競合制御が実装済み）
        download_result = await asyncio.get_event_loop().run_in_executor(
            None, downloader.download_mp3, track_info.url
        )
        
        # download_mp3は(bool, str)のタプルを返すため、成功可否のみを取得
        if isinstance(download_result, tuple):
            success, downloaded_title = download_result
            # タイトルが取得できた場合は更新
            if downloaded_title and downloaded_title != "Unknown Title":
                track_info.title = downloaded_title
        else:
            # 後方互換性のため、boolが返された場合はそのまま使用
            success = download_result
        
        if success:
            audio_queue.set_download_status(guild_id, track_info.url, True)
            logger.info(f"Background download completed: {track_info.title}")
        else:
            logger.error(f"Background download failed: {track_info.title}")
            
    except asyncio.CancelledError:
        logger.info(f"Background download cancelled for guild {guild_id}")
        raise
    except FileNotFoundError as e:
        logger.error(f"yt-dlp not found for background download: {e}")
    except PermissionError as e:
        logger.error(f"Permission error in background download: {e}")
    except Exception as e:
        logger.exception("Unexpected error in background download for guild %s", guild_id)
