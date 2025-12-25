"""
制御系コマンド（/stop /pause /resume /queue /clear /skip /loop）
"""

import asyncio
import logging
import discord

from ..audio import AudioQueue, AudioPlayer

logger = logging.getLogger(__name__)


def register_control_commands(bot, audio_queue: AudioQueue, audio_player: AudioPlayer):
    @bot.tree.command(name='stop', description='Stop audio playback and disconnect from voice channel')
    async def stop_audio(interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.response.send_message("❌ ボイスチャンネルに接続していません。", ephemeral=True)
            return

        guild_id = interaction.guild_id
        try:
            audio_queue.cancel_idle_timeout(guild_id)
            audio_player.stop_playback(guild_id, voice_client)
            audio_queue.clear_queue(guild_id)
            audio_queue.clear_now_playing(guild_id)
            audio_queue.set_loop(guild_id, False)
            audio_queue.cancel_downloads(guild_id)
            audio_queue.set_starting_playback(guild_id, False)

            await asyncio.sleep(1)
            await voice_client.disconnect()

            embed = discord.Embed(
                title="🛑 再生停止",
                description="音声再生を停止し、ボイスチャンネルから切断しました。\nキューもクリアされました。",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed)
        except Exception:
            logger.exception("Stop command error")
            await interaction.response.send_message("❌ 音声停止に失敗しました。")

    @bot.tree.command(name='pause', description='Pause audio playback')
    async def pause_audio(interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_connected():
            await interaction.response.send_message("❌ ボイスチャンネルに接続していません。", ephemeral=True)
            return
        if not audio_player.is_playing(voice_client):
            await interaction.response.send_message("❌ 現在音声を再生していません。", ephemeral=True)
            return

        guild_id = interaction.guild_id
        audio_queue.set_text_channel(guild_id, interaction.channel_id)
        try:
            if audio_player.pause_playback(voice_client):
                await interaction.response.send_message(embed=discord.Embed(title="⏸️ 一時停止", description="音声再生を一時停止しました。", color=discord.Color.yellow()))
            else:
                await interaction.response.send_message("❌ 一時停止に失敗しました。")
        except Exception:
            logger.exception("Pause command error")
            await interaction.response.send_message("❌ 一時停止に失敗しました。")

    @bot.tree.command(name='resume', description='Resume audio playback')
    async def resume_audio(interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_connected():
            await interaction.response.send_message("❌ ボイスチャンネルに接続していません。", ephemeral=True)
            return
        if not audio_player.is_paused(voice_client):
            await interaction.response.send_message("❌ 現在音声は一時停止されていません。", ephemeral=True)
            return

        guild_id = interaction.guild_id
        audio_queue.set_text_channel(guild_id, interaction.channel_id)
        try:
            if audio_player.resume_playback(voice_client):
                await interaction.response.send_message(embed=discord.Embed(title="▶️ 再生再開", description="音声再生を再開しました。", color=discord.Color.green()))
            else:
                await interaction.response.send_message("❌ 再生再開に失敗しました。")
        except Exception:
            logger.exception("Resume command error")
            await interaction.response.send_message("❌ 再生再開に失敗しました。")

    @bot.tree.command(name='queue', description='Show current music queue')
    async def show_queue(interaction: discord.Interaction):
        guild_id = interaction.guild_id
        queue = audio_queue.get_queue(guild_id)
        now_playing = audio_queue.get_now_playing(guild_id)

        embed = discord.Embed(title="🎵 音楽キュー", color=discord.Color.blue())

        if now_playing:
            loop_status = " 🔁" if audio_queue.is_loop_enabled(guild_id) else ""
            embed.add_field(name=f"🎶 現在再生中{loop_status}", value=f"**{now_playing.title}**\n👤 追加者: {now_playing.user}", inline=False)
            if audio_queue.is_loop_enabled(guild_id):
                embed.add_field(name="🔁 ループモード", value="この曲を繰り返し再生します。\n`/loop` コマンドで無効にできます。", inline=False)

        if queue:
            text = ""
            for i, t in enumerate(queue[:10], 1):
                text += f"{i}. **{t.title}**\n   追加者: {t.user}\n"
            if len(queue) > 10:
                text += f"\n... 他 {len(queue) - 10} 曲"
            embed.add_field(name=f"📋 キュー ({len(queue)}曲)", value=text, inline=False)
        else:
            embed.add_field(name="📋 キュー", value="キューは空です。", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name='clear', description='Clear music queue')
    async def clear_queue(interaction: discord.Interaction):
        guild_id = interaction.guild_id
        queue_length = audio_queue.get_queue_length(guild_id)
        if queue_length == 0:
            embed = discord.Embed(title="📋 キューは空です", description="クリアするキューがありません。", color=discord.Color.blue())
        else:
            audio_queue.clear_queue(guild_id)
            embed = discord.Embed(title="🗑️ キューをクリア", description=f"{queue_length}曲のキューがクリアされました。\n現在再生中の曲は影響を受けません。", color=discord.Color.orange())
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @bot.tree.command(name='skip', description='Skip current track and play next track in queue')
    async def skip_audio(interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.response.send_message("❌ ボイスチャンネルに接続していません。", ephemeral=True)
            return
        if not audio_player.is_playing(voice_client):
            await interaction.response.send_message("❌ 現在音声を再生していません。", ephemeral=True)
            return

        guild_id = interaction.guild_id
        current_track = audio_queue.get_now_playing(guild_id)
        current_title = current_track.title if current_track else 'Unknown Track'

        audio_queue.set_text_channel(guild_id, interaction.channel_id)
        audio_queue.cancel_idle_timeout(guild_id)

        if audio_queue.is_loop_enabled(guild_id):
            next_title = current_title
        else:
            q = audio_queue.get_queue(guild_id)
            next_track = q[0] if q else None
            next_title = next_track.title if next_track else None

        embed = discord.Embed(title="⏭️ スキップ", description=f"**現在の曲をスキップします**\n\n🎵 **スキップする曲：** {current_title}", color=discord.Color.blue())
        if next_title:
            embed.add_field(name="⏭️ 次の曲", value=next_title, inline=False)
        else:
            embed.add_field(name="📋 キュー", value="次の曲はありません。5分後に自動切断されます。", inline=False)
        if audio_queue.is_loop_enabled(guild_id):
            embed.add_field(name="🔁 ループ", value="有効" if next_title else "無効化されました", inline=True)
        await interaction.response.send_message(embed=embed)

        if audio_queue.is_loop_enabled(guild_id) and not audio_queue.has_queue(guild_id):
            audio_queue.set_loop(guild_id, False)

        audio_queue.mark_manual_skip(guild_id)
        voice_client.stop()

    @bot.tree.command(name='loop', description='Toggle loop mode for current track')
    async def loop_audio(interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.response.send_message("❌ ボイスチャンネルに接続していません。", ephemeral=True)
            return

        guild_id = interaction.guild_id
        if not audio_player.is_playing(voice_client):
            await interaction.response.send_message("❌ 現在音声を再生していません。", ephemeral=True)
            return

        current_track = audio_queue.get_now_playing(guild_id)
        if not current_track:
            await interaction.response.send_message("❌ 現在再生中のトラック情報が見つかりません。", ephemeral=True)
            return

        loop_enabled = audio_queue.toggle_loop(guild_id)
        if loop_enabled:
            embed = discord.Embed(title="🔁 ループ有効", description=f"**現在の曲をループします**\n\n🎵 **ループ中の曲：** {current_track.title}", color=discord.Color.green())
            embed.add_field(name="💡 ヒント", value="もう一度 `/loop` コマンドでループを無効にできます。", inline=False)
        else:
            audio_player.cleanup_loop_file(guild_id)
            embed = discord.Embed(title="🔁 ループ無効", description="**ループを無効にしました**\n\n曲が終了したら次の曲に進みます。", color=discord.Color.orange())
        await interaction.response.send_message(embed=embed)


