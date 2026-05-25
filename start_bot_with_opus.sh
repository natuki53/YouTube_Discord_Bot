#!/bin/bash
cd "$(dirname "$0")"

export DYLD_LIBRARY_PATH="/opt/homebrew/lib:${DYLD_LIBRARY_PATH}"
export PKG_CONFIG_PATH="/opt/homebrew/lib/pkgconfig:${PKG_CONFIG_PATH}"

if [ -d ".venv" ]; then
  source .venv/bin/activate
fi

echo "Starting Discord bot..."
python main.py
