"""Discord と Web が共有する操作・VC 権限・直列化。"""

import asyncio
from collections import defaultdict


class ControlError(ValueError):
    pass


class MusicControl:
    def __init__(self, manager, *, max_queue=100):
        self.manager = manager
        self.max_queue = max_queue
        self.locks = defaultdict(asyncio.Lock)

    def authorize(self, guild, member, *, starting=False):
        user_channel = getattr(getattr(member, "voice", None), "channel", None)
        if user_channel is None:
            raise ControlError("ボイスチャンネルに接続してから操作してください。")
        voice = guild.voice_client
        if voice and voice.is_connected():
            if voice.channel.id != user_channel.id:
                raise ControlError(
                    "Botと同じボイスチャンネルに接続してから操作してください。"
                )
        elif not starting:
            raise ControlError("先に /play または再生ボタンで曲を再生してください。")
        permissions = user_channel.permissions_for(member)
        if not permissions.view_channel or not permissions.connect:
            raise ControlError("このボイスチャンネルを操作する権限がありません。")
        return user_channel

    async def enqueue(self, guild, member, track, *, channel_id=None, voice=None):
        statuses = await self.enqueue_many(
            guild, member, [track], channel_id=channel_id, voice=voice
        )
        return statuses[0]

    async def enqueue_many(self, guild, member, tracks, *, channel_id=None, voice=None):
        async with self.locks[guild.id]:
            channel = self.authorize(guild, member, starting=True)
            player = self.manager.get(guild.id)
            available = self.max_queue - len(player.get_queue_snapshot()["queue"])
            if not tracks or len(tracks) > available:
                raise ControlError(
                    f"キューは最大{self.max_queue}曲です。現在追加できるのは{max(0, available)}曲です。"
                )
            voice = voice or guild.voice_client
            if not voice or not voice.is_connected():
                permissions = channel.permissions_for(guild.me)
                if not permissions.connect or not permissions.speak:
                    raise ControlError("BotにVCへの接続・発言権限がありません。")
                try:
                    voice = await channel.connect()
                except Exception as error:
                    message = str(error).lower()
                    if "davey" in message:
                        raise ControlError(
                            "音声機能に必要な davey をインストールしてください。"
                        ) from error
                    if "nacl" in message:
                        raise ControlError(
                            "音声機能に必要な PyNaCl をインストールしてください。"
                        ) from error
                    raise ControlError(
                        "ボイスチャンネルに接続できませんでした。権限を確認してください。"
                    ) from error
            if channel_id:
                player.set_text_channel(channel_id)
            return [await player.enqueue(track, voice) for track in tracks]

    async def apply(self, guild, member, action, *, value=None, channel_id=None):
        async with self.locks[guild.id]:
            self.authorize(guild, member)
            player = self.manager.get(guild.id)
            voice = guild.voice_client
            if channel_id:
                player.set_text_channel(channel_id)
            if action == "stop":
                await player.stop(voice)
                self.manager.remove(guild.id)
                return True
            if action == "pause":
                return player.pause(voice)
            if action == "resume":
                return player.resume(voice)
            if action == "skip":
                return await player.skip(voice)
            if action == "clear":
                return player.clear_queue()
            if action == "seek":
                if not isinstance(value, dict) or not isinstance(
                    value.get("track_id"), str
                ):
                    raise ControlError("操作する曲を指定してください。")
                try:
                    return await player.seek(
                        voice, value["track_id"], value.get("position")
                    )
                except ValueError as error:
                    raise ControlError(str(error)) from error
            if action in ("queue_remove", "queue_move"):
                if not isinstance(value, dict) or not isinstance(value.get("id"), str):
                    raise ControlError("操作する曲を指定してください。")
                before = value.get("before_id")
                if before is not None and not isinstance(before, str):
                    raise ControlError("移動先が不正です。")
                try:
                    return player.edit_queue(action, value["id"], before)
                except ValueError as error:
                    raise ControlError(str(error)) from error
            if action == "volume":
                if type(value) is not int or not 1 <= value <= 100:
                    raise ControlError("音量は1〜100で指定してください。")
                return player.set_volume_percent(value)
            if action == "spatial":
                try:
                    return await player.set_spatial(value)
                except ValueError as error:
                    raise ControlError(str(error)) from error
            if action == "nightcore":
                try:
                    return player.set_nightcore(value)
                except ValueError as error:
                    raise ControlError(str(error)) from error
            if action == "loop":
                if value is not None and type(value) is not bool:
                    raise ControlError("ループ設定が不正です。")
                if value is None or player.is_loop_enabled() != value:
                    player.toggle_loop()
                return player.is_loop_enabled()
            if action == "autoplay":
                if value is not None and type(value) is not bool:
                    raise ControlError("自動選曲設定が不正です。")
                enabled = not player.is_autoplay_enabled() if value is None else value
                player.set_autoplay_enabled(enabled)
                return enabled
            raise ControlError("対応していない操作です。")
