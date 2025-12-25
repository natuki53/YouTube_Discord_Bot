"""
音楽コマンド共通UI/通知ヘルパー

Embed生成・メッセージ編集・次曲タイトル取得など、表示周りを集約する。
"""

import asyncio
import logging
import discord

from ..audio import AudioQueue

logger = logging.getLogger(__name__)


async def safe_send_to_text(
    guild_id: int,
    audio_queue: AudioQueue,
    voice_client,
    *,
    embed: discord.Embed = None,
    content: str = None,
    channel_id: int = None,
):
    """
    再生処理を止めずに安全にテキスト通知を送る。
    通知失敗は握りつぶしてログだけ残す。
    """
    try:
        channel_id_for_notification = channel_id or audio_queue.get_text_channel(guild_id)
        if not channel_id_for_notification or not voice_client or not voice_client.guild:
            return
        channel = voice_client.guild.get_channel(channel_id_for_notification)
        if not channel:
            return
        if not channel.permissions_for(voice_client.guild.me).send_messages:
            return
        await asyncio.wait_for(channel.send(content=content, embed=embed), timeout=10.0)
    except Exception:
        logger.exception("Failed to send notification for guild %s", guild_id)


def get_next_queue_title(audio_queue: AudioQueue, guild_id: int) -> str:
    """キュー先頭の次曲タイトルを取得（無ければNone）"""
    try:
        q = audio_queue.get_queue(guild_id)
        if q:
            return q[0].title
    except Exception:
        pass
    return None


def build_progress_embed(
    *,
    title: str,
    status: str,
    url: str = None,
    track_title: str = None,
    requester: str = None,
    queue_length: int = None,
    next_title: str = None,
    file_size_mb: float = None,
    color: discord.Color = None,
) -> discord.Embed:
    """ユーザー向けの進捗/再生情報Embed（内部処理は見せない）"""
    embed = discord.Embed(
        title=title,
        description=(f"**タイトル：** {track_title}" if track_title else None),
        color=color or discord.Color.blue()
    )
    if url:
        embed.add_field(name="🔗 URL", value=f"[リンク]({url})", inline=False)
    if requester:
        embed.add_field(name="👤 リクエスト", value=requester, inline=True)
    if file_size_mb is not None:
        embed.add_field(name="📁 ファイル", value=f"{file_size_mb:.1f} MB", inline=True)
    if queue_length is not None:
        embed.add_field(name="📋 キュー", value=f"{queue_length}曲", inline=True)
    if next_title:
        embed.add_field(name="⏭️ 次の曲", value=next_title, inline=False)
    embed.add_field(name="⏳ ステータス", value=status, inline=False)
    return embed


async def safe_edit_message(message: discord.Message, *, embed: discord.Embed = None, view=None):
    """進捗表示を1メッセージに集約するための安全な編集"""
    try:
        await message.edit(embed=embed, view=view)
    except Exception:
        logger.exception("Failed to edit progress message")


