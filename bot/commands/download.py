"""
ダウンロード関連コマンド

YouTube動画をMP3に変換してダウンロードするコマンド
"""

import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import logging
import os

from ..youtube import YouTubeDownloader, get_title_from_url, validate_youtube_url, normalize_youtube_url, is_playlist_url

logger = logging.getLogger(__name__)

def setup_download_commands(bot, download_dir: str, max_file_size: int):
    """ダウンロード関連コマンドをセットアップ"""
    
    @bot.tree.command(name='download', description='Convert YouTube video to MP3 and download')
    @app_commands.describe(
        url='YouTube動画のURL'
    )
    async def download(interaction: discord.Interaction, url: str):
        """YouTube動画をMP3に変換してダウンロードするコマンド"""
        # YouTube URLの形式をチェック
        if not validate_youtube_url(url):
            await interaction.response.send_message(
                "❌ 有効なYouTube URLを入力してください。\n\n"
                "対応形式:\n"
                "• https://www.youtube.com/watch?v=...\n"
                "• https://youtu.be/...\n"
                "• https://youtube.com/watch?v=...",
                ephemeral=True
            )
            return
        
        # プレイリストURL検証
        if is_playlist_url(url):
            embed = discord.Embed(
                title="❌ プレイリストは変換できません",
                description="申し訳ございませんが、プレイリストURLには対応していません。\n\n**代替案:**\n• 個別の動画URLを使用してください\n• プレイリスト内の特定の動画を選んでダウンロードしてください",
                color=discord.Color.red()
            )
            embed.add_field(
                name="💡 ヒント",
                value="プレイリスト内の動画を個別に選択して `/download_mp3` コマンドで変換できます。",
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # URLを標準形式に正規化
        normalized_url = normalize_youtube_url(url)
        if normalized_url:
            url = normalized_url
            logger.info(f"URL normalized to: {url}")
        
        # 動画タイトルを取得
        video_title = get_title_from_url(url)
        
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
            
            # MP3変換実行
            downloader = YouTubeDownloader(download_dir)
            download_result = await asyncio.get_event_loop().run_in_executor(
                None, downloader.download_mp3, url
            )
            
            # download_mp3は(bool, str)のタプルを返す
            success, downloaded_title = download_result
            
            if success:
                # 最新のMP3ファイルを取得
                file_path = downloader.get_latest_mp3_file()
                if file_path:
                    file_size = downloader.get_file_size_mb(file_path)
                    
                    if file_size <= max_file_size:
                        file = discord.File(file_path)
                        # ダウンロードで取得したタイトルを使用、取得できなかった場合は元のタイトルを使用
                        display_title = downloaded_title if downloaded_title != "Unknown Title" else video_title
                        embed = discord.Embed(
                            title="✅ MP3変換完了",
                            description=f"**{display_title}**\n\n📁 **ファイル:** {os.path.basename(file_path)}\n📊 **サイズ:** {file_size:.2f} MB\n🎵 **形式:** MP3音声ファイル",
                            color=discord.Color.green()
                        )
                        embed.add_field(
                            name="📥 ダウンロード情報",
                            value=f"URL: {url}",
                            inline=False
                        )
                        await interaction.followup.send(embed=embed, file=file)
                        
                        # ファイルを削除
                        downloader.cleanup_file(file_path)
                    else:
                        display_title = downloaded_title if downloaded_title != "Unknown Title" else video_title
                        embed = discord.Embed(
                            title="⚠️ ファイルサイズが大きすぎます",
                            description=f"**{display_title}**\n\n📊 **ファイルサイズ:** {file_size:.2f} MB\n📏 **Discordの制限:** {max_file_size} MB\n🎵 **形式:** MP3音声ファイル\n\n容量制限のため、ファイルを削除しました。",
                            color=discord.Color.orange()
                        )
                        embed.add_field(
                            name="📥 ダウンロード情報",
                            value=f"URL: {url}",
                            inline=False
                        )
                        await interaction.followup.send(embed=embed)
                        
                        # ファイルを削除
                        downloader.cleanup_file(file_path)
                else:
                    await interaction.followup.send("❌ MP3ファイルが見つかりませんでした。")
            else:
                await interaction.followup.send("❌ MP3変換に失敗しました。")
                
        except asyncio.TimeoutError:
            logger.error("MP3 conversion timeout occurred")
            embed = discord.Embed(
                title="❌ MP3変換がタイムアウトしました",
                description="動画のMP3変換に時間がかかりすぎています。\n短い動画を試すか、しばらく後に再試行してください。",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
        except FileNotFoundError as e:
            logger.exception("yt-dlp not found for MP3 conversion")
            embed = discord.Embed(
                title="❌ ダウンローダーが見つかりません",
                description="yt-dlpがインストールされていないか、パスが正しくありません。",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
        except PermissionError as e:
            logger.exception("Permission error during MP3 conversion")
            embed = discord.Embed(
                title="❌ 権限エラー",
                description="ファイルの書き込み権限がありません。",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.exception("Unexpected MP3 conversion error")
            embed = discord.Embed(
                title="❌ 予期しないエラーが発生しました",
                description=f"エラー: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
