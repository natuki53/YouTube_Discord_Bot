"""
ダウンロード関連コマンド

DownloadService 経由でファイルDL・Discord添付
"""

import asyncio
import logging

import discord
from discord import app_commands

from ..youtube import (
    get_title_from_url,
    validate_youtube_url,
    normalize_youtube_url,
    is_playlist_url,
)
from ..youtube.download_service import DownloadService

logger = logging.getLogger(__name__)


def setup_download_commands(
    bot,
    download_service: DownloadService,
    supported_qualities: list,
):
    """ダウンロード関連コマンドをセットアップ"""

    @bot.tree.command(
        name="download",
        description="YouTube 動画を指定画質でダウンロードします（Discord に添付）",
    )
    @app_commands.describe(url="YouTube 動画の URL", quality="動画の画質")
    @app_commands.choices(
        quality=[
            app_commands.Choice(name="144p (低画質)", value="144p"),
            app_commands.Choice(name="240p (低画質)", value="240p"),
            app_commands.Choice(name="360p (標準画質)", value="360p"),
            app_commands.Choice(name="480p (標準画質)", value="480p"),
            app_commands.Choice(name="720p (高画質)", value="720p"),
            app_commands.Choice(name="1080p (フルHD)", value="1080p"),
        ]
    )
    async def download_video(interaction: discord.Interaction, url: str, quality: str):
        if not validate_youtube_url(url):
            await interaction.response.send_message(
                "❌ 有効なYouTube URLを入力してください。",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        normalized = normalize_youtube_url(url)
        if normalized:
            url = normalized

        try:
            title = await asyncio.to_thread(get_title_from_url, url)
            embed = discord.Embed(
                title="📥 ダウンロード開始",
                description=f"**{title}**\n🎬 **画質:** {quality}",
                color=discord.Color.blue(),
            )
            await interaction.followup.send(embed=embed)

            response = await download_service.run_video(url, quality, title)
            await _send_download_response(interaction, download_service, response)
        except asyncio.TimeoutError:
            await interaction.followup.send("❌ ダウンロードがタイムアウトしました。")
        except Exception as e:
            logger.error(f"Download command error: {e}")
            await interaction.followup.send(f"❌ エラー: {e}")

    @bot.tree.command(
        name="download_mp3",
        description="YouTube 動画を MP3 に変換してダウンロードします",
    )
    @app_commands.describe(url="YouTube 動画の URL")
    async def download_mp3(interaction: discord.Interaction, url: str):
        if not validate_youtube_url(url):
            await interaction.response.send_message(
                "❌ 有効なYouTube URLを入力してください。",
                ephemeral=True,
            )
            return

        if is_playlist_url(url):
            embed = discord.Embed(
                title="❌ プレイリストは変換できません",
                description="個別の動画URLを使用してください。",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer()

        normalized = normalize_youtube_url(url)
        if normalized:
            url = normalized

        try:
            title = await asyncio.to_thread(get_title_from_url, url)
            embed = discord.Embed(
                title="🎵 MP3変換開始",
                description=f"**{title}**",
                color=discord.Color.blue(),
            )
            await interaction.followup.send(embed=embed)

            response = await download_service.run_mp3(url, title)
            await _send_download_response(interaction, download_service, response)
        except Exception as e:
            logger.error(f"MP3 download error: {e}")
            await interaction.followup.send(f"❌ エラー: {e}")

    @bot.tree.command(
        name="quality",
        description="利用可能な画質一覧と 25MB 制限のヒントを表示します",
    )
    async def show_quality(interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎬 利用可能な画質",
            description="\n".join(f"• {q}" for q in supported_qualities),
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="💡 ヒント",
            value=(
                "Discord の添付上限は 25MB です。\n"
                "長い動画や高画質は自動で低画質に切り替わる場合があります。\n"
                "25MB を超えやすい場合は **480p 以下** を推奨します。"
            ),
            inline=False,
        )
        embed.add_field(
            name="使用例",
            value="`/download <URL> <画質>`",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def _send_download_response(
    interaction: discord.Interaction,
    service: DownloadService,
    response,
) -> None:
    try:
        if response.send_file and response.file_path:
            file = discord.File(response.file_path)
            await interaction.followup.send(embed=response.embed, file=file)
        else:
            await interaction.followup.send(embed=response.embed)
    finally:
        service.cleanup(response.video_id)
