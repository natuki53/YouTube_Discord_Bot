#!/bin/bash

# Opusライブラリのパスを設定
export DYLD_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_LIBRARY_PATH"
export PKG_CONFIG_PATH="/opt/homebrew/lib/pkgconfig:$PKG_CONFIG_PATH"

# パスを確認
echo "Opus library path: $DYLD_LIBRARY_PATH"
echo "Pkg-config path: $PKG_CONFIG_PATH"

# ボットを起動
echo "Starting Discord bot with Opus support..."
python3 discord_bot.py
