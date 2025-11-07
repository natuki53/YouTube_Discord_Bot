@echo off
chcp 65001 > nul
echo YouTube Discord Bot (Windows版)
echo ============================
echo.

REM 設定ファイルの確認
if not exist config.py (
    echo ❌ config.pyが見つかりません
    echo config_example.pyをconfig.pyにコピーして、DISCORD_TOKENを設定してください。
    echo.
    echo 手順:
    echo 1. copy config_example.py config.py
    echo 2. config.pyを編集してDISCORD_TOKENを設定
    echo 3. このバッチファイルを再実行
    pause
    exit /b 1
)

REM Pythonの確認
python --version > nul 2>&1
if errorlevel 1 (
    echo ❌ Pythonが見つかりません
    echo Pythonをインストールしてください: https://python.org
    pause
    exit /b 1
)

echo ✅ Pythonが利用可能です
python --version

REM 依存関係のインストール
echo.
echo 📦 依存関係を確認中...
pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo ❌ 依存関係のインストールに失敗しました
    pause
    exit /b 1
)

REM ボットの起動
echo.
echo 🚀 YouTube Discord Botを起動しています...
echo Ctrl+Cで停止できます
echo.

python main.py

echo.
echo 👋 ボットが終了しました
pause
