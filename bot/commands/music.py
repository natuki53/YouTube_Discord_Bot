"""
音楽関連コマンド（薄いコマンド層）

再生ロジックは GuildPlayer に委譲
"""

import asyncio
import logging

import discord
from discord import app_commands

from ..music import PlayerManager, Track
from ..youtube import SearchError, resolve_play_query

logger = logging.getLogger(__name__)
PLAY_QUERY_TIMEOUT_SECONDS = 45


def setup_music_commands(bot, player_manager: PlayerManager):
    """音楽関連コマンドをセットアップ"""

    @bot.event
    async def on_voice_state_update(member, before, after):
        """BotのVCにいる人間が0人になったら自動退出タイマーを管理する。"""
        guild = member.guild
        voice_client = guild.voice_client

        if not voice_client or not voice_client.is_connected():
            player = player_manager.get_existing(guild.id)
            if player:
                player.cancel_empty_channel_timeout()
            return

        bot_channel = voice_client.channel
        bot_user = bot.user
        is_bot_event = bot_user is not None and member.id == bot_user.id
        if (
            not is_bot_event
            and before.channel != bot_channel
            and after.channel != bot_channel
        ):
            return

        player = player_manager.get(guild.id)
        player.update_empty_channel_timeout(voice_client)

    async def _connect_voice(
        interaction: discord.Interaction, *, use_followup: bool = False
    ) -> discord.VoiceClient | None:
        async def _reply(msg: str):
            if use_followup:
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)

        if interaction.guild is None or not getattr(interaction.user, "voice", None):
            await _reply("❌ ボイスチャンネルに接続してから使用してください。")
            return None

        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_connected():
            return voice_client

        try:
            return await interaction.user.voice.channel.connect()
        except Exception as e:
            logger.exception("Voice connect failed")
            err = str(e).lower()
            if "davey" in err:
                await _reply(
                    "❌ 音声機能に必要な `davey` が未インストールです。\n"
                    "`.venv` を有効化したうえで:\n"
                    "`python -m pip install -r requirements.txt`"
                )
            elif "nacl" in err or "pynacl" in err:
                await _reply(
                    "❌ 音声機能に必要な `PyNaCl` が未インストールです。\n"
                    "`python -m pip install -r requirements.txt`"
                )
            else:
                await _reply(
                    "❌ ボイスチャンネルに接続できませんでした。権限を確認してください。"
                )
            return None

    @bot.tree.command(
        name="play",
        description="YouTube の音声をボイスチャンネルで再生します",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        query="YouTube の URL、または曲名・キーワード（先頭の検索結果を再生）",
    )
    async def play_audio(interaction: discord.Interaction, query: str):
        if not query.strip():
            await interaction.response.send_message(
                "❌ URL または曲名を入力してください。",
                ephemeral=True,
            )
            return

        if not getattr(interaction.user, "voice", None):
            await interaction.response.send_message(
                "❌ ボイスチャンネルに接続してから使用してください。",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        try:
            target = await asyncio.wait_for(
                asyncio.to_thread(resolve_play_query, query),
                timeout=PLAY_QUERY_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            await interaction.followup.send(
                "❌ 曲の検索がタイムアウトしました。",
                ephemeral=True,
            )
            return
        except SearchError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)
            return
        except Exception:
            logger.exception("resolve_play_query failed")
            await interaction.followup.send(
                "❌ 曲の検索に失敗しました。", ephemeral=True
            )
            return

        voice_client = await _connect_voice(interaction, use_followup=True)
        if not voice_client:
            return

        track = Track(
            url=target.url,
            title=target.display_title,
            requester=interaction.user.display_name,
        )
        player = player_manager.get(interaction.guild_id)
        player.set_text_channel(interaction.channel_id)

        status = await player.enqueue(track, voice_client)

        if status == "queued":
            snap = player.get_queue_snapshot()
            embed = discord.Embed(
                title="🎵 キューに追加",
                description=f"**{target.display_title}**\n📋 待機: {len(snap['queue'])} 曲",
                color=discord.Color.blue(),
            )
            await interaction.followup.send(embed=embed)
        else:
            # 再生開始は GuildPlayer が実際に再生できたタイミングで通知
            try:
                await interaction.delete_original_response()
            except discord.HTTPException:
                pass

    @bot.tree.command(
        name="stop",
        description="再生を停止し、ボイスチャンネルから切断します",
    )
    @app_commands.guild_only()
    async def stop_audio(interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.response.send_message(
                "❌ ボイスチャンネルに接続していません。",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        player = player_manager.get(interaction.guild_id)
        await player.stop(voice_client)
        player_manager.remove(interaction.guild_id)

        embed = discord.Embed(
            title="🛑 再生停止",
            description="再生を停止し、ボイスチャンネルから切断しました。",
            color=discord.Color.orange(),
        )
        await interaction.followup.send(embed=embed)

    @bot.tree.command(name="pause", description="再生を一時停止します")
    @app_commands.guild_only()
    async def pause_audio(interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_connected():
            await interaction.response.send_message(
                "❌ ボイスチャンネルに接続していません。", ephemeral=True
            )
            return

        player = player_manager.get(interaction.guild_id)
        if player.pause(voice_client):
            await interaction.response.send_message(
                embed=discord.Embed(title="⏸️ 一時停止", color=discord.Color.yellow())
            )
        else:
            await interaction.response.send_message(
                "❌ 現在再生していません。", ephemeral=True
            )

    @bot.tree.command(name="resume", description="一時停止中の再生を再開します")
    @app_commands.guild_only()
    async def resume_audio(interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_connected():
            await interaction.response.send_message(
                "❌ ボイスチャンネルに接続していません。", ephemeral=True
            )
            return

        player = player_manager.get(interaction.guild_id)
        if player.resume(voice_client):
            await interaction.response.send_message(
                embed=discord.Embed(title="▶️ 再生再開", color=discord.Color.green())
            )
        else:
            await interaction.response.send_message(
                "❌ 一時停止中ではありません。", ephemeral=True
            )

    @bot.tree.command(name="queue", description="現在の再生キューを表示します")
    @app_commands.guild_only()
    async def show_queue(interaction: discord.Interaction):
        player = player_manager.get(interaction.guild_id)
        snap = player.get_queue_snapshot()

        embed = discord.Embed(title="🎵 音楽キュー", color=discord.Color.blue())
        current = snap["current"]
        if current:
            loop_mark = " 🔁" if snap["loop"] else ""
            embed.add_field(
                name=f"🎶 現在再生中{loop_mark}",
                value=f"**{current.title}**\n👤 {current.requester}",
                inline=False,
            )

        queue = snap["queue"]
        if queue:
            lines = [
                f"{i}. **{t.title}** ({t.requester})"
                for i, t in enumerate(queue[:10], 1)
            ]
            if len(queue) > 10:
                lines.append(f"... 他 {len(queue) - 10} 曲")
            embed.add_field(
                name=f"📋 キュー ({len(queue)}曲)", value="\n".join(lines), inline=False
            )
        elif not current:
            embed.add_field(name="📋 キュー", value="キューは空です。", inline=False)

        vol = player.get_volume_percent()
        embed.set_footer(text=f"🔊 音量: {vol}%（/volume で変更）")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(
        name="clear", description="待機中のキューをクリアします（再生中の曲は継続）"
    )
    @app_commands.guild_only()
    async def clear_queue_cmd(interaction: discord.Interaction):
        player = player_manager.get(interaction.guild_id)
        count = player.clear_queue()
        if count == 0:
            msg = "クリアするキューがありません。"
        else:
            msg = f"{count} 曲のキューをクリアしました。再生中の曲は継続します。"
        embed = discord.Embed(
            title="🗑️ キューをクリア", description=msg, color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="skip", description="現在の曲をスキップして次の曲へ進みます")
    @app_commands.guild_only()
    async def skip_audio(interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not (
            voice_client.is_playing() or voice_client.is_paused()
        ):
            await interaction.response.send_message(
                "❌ 現在再生していません。", ephemeral=True
            )
            return

        player = player_manager.get(interaction.guild_id)
        player.set_text_channel(interaction.channel_id)
        skipped = await player.skip(voice_client)
        snap = player.get_queue_snapshot()
        next_track = snap["queue"][0] if snap["queue"] else None

        embed = discord.Embed(
            title="⏭️ スキップ",
            description=f"**{skipped or '曲'}** をスキップしました。",
            color=discord.Color.blue(),
        )
        if next_track:
            embed.add_field(name="⏭️ 次の曲", value=next_track.title, inline=False)
        else:
            embed.add_field(
                name="📋 キュー",
                value="次の曲はありません。5分後に自動切断されます。",
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(
        name="loop",
        description="現在再生中の曲のループ再生を切り替えます",
    )
    @app_commands.guild_only()
    async def loop_audio(interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not (
            voice_client.is_playing() or voice_client.is_paused()
        ):
            await interaction.response.send_message(
                "❌ 再生中の曲がありません。",
                ephemeral=True,
            )
            return

        player = player_manager.get(interaction.guild_id)
        enabled = player.toggle_loop()
        status = "有効" if enabled else "無効"
        embed = discord.Embed(
            title="🔁 ループモード",
            description=f"ループを **{status}** にしました。",
            color=discord.Color.orange() if enabled else discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(
        name="volume",
        description="ボイスチャンネル再生の音量を変更します（1〜100%）",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        level="音量（%）。省略時は現在の音量を表示",
    )
    async def set_volume(
        interaction: discord.Interaction, level: app_commands.Range[int, 1, 100] = None
    ):
        player = player_manager.get(interaction.guild_id)

        if level is None:
            vol = player.get_volume_percent()
            await interaction.response.send_message(
                f"🔊 現在の音量: **{vol}%**\n"
                f"変更するには `/volume 50` のように指定してください。",
                ephemeral=True,
            )
            return

        new_vol = player.set_volume_percent(level)
        embed = discord.Embed(
            title="🔊 音量変更",
            description=f"音量を **{new_vol}%** に設定しました。",
            color=discord.Color.green(),
        )
        if interaction.guild.voice_client and (
            interaction.guild.voice_client.is_playing()
            or interaction.guild.voice_client.is_paused()
        ):
            embed.add_field(
                name="反映", value="再生中の曲に即時反映されました。", inline=False
            )
        await interaction.response.send_message(embed=embed)
