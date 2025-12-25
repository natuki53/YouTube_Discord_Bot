"""
音楽関連コマンド（エントリ）

このファイルは「コマンド登録の入口」だけを担当し、実装は機能別モジュールへ分割する。
"""

from ..audio import AudioQueue, AudioPlayer

from .music_commands_play import register_play_command
from .music_commands_playlist import register_playlist_command
from .music_commands_control import register_control_commands


def setup_music_commands(bot, audio_queue: AudioQueue, audio_player: AudioPlayer, download_dir: str):
    """
    音楽関連コマンドをセットアップ

    互換性のため署名は維持する（download_dir は AudioPlayer 側が保持しているので未使用）。
    """
    register_play_command(bot, audio_queue, audio_player)
    register_playlist_command(bot, audio_queue, audio_player)
    register_control_commands(bot, audio_queue, audio_player)


