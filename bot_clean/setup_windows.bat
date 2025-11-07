@echo off
chcp 65001 > nul
echo YouTube Discord Bot - Windows セットアップ
echo =========================================
echo.

REM Pythonの確認
echo 🔍 Pythonを確認中...
python --version > nul 2>&1
if errorlevel 1 (
    echo ❌ Pythonが見つかりません
    echo.
    echo Pythonをインストールしてください:
    echo https://www.python.org/downloads/
    echo.
    echo インストール時は「Add Python to PATH」にチェックを入れてください
    pause
    exit /b 1
)

echo ✅ Python利用可能:
python --version
echo.

REM pipの確認とアップグレード
echo 🔍 pipを確認中...
python -m pip --version > nul 2>&1
if errorlevel 1 (
    echo ❌ pipが見つかりません
    pause
    exit /b 1
)

echo ✅ pipが利用可能です
echo.

REM pipのアップグレード
echo 📦 pipをアップグレード中...
python -m pip install --upgrade pip

REM 依存関係のインストール
echo.
echo 📦 依存関係をインストール中...
python -m pip install -r requirements_windows.txt

if errorlevel 1 (
    echo.
    echo ❌ 依存関係のインストールに失敗しました
    echo.
    echo 解決方法:
    echo 1. インターネット接続を確認
    echo 2. Pythonが正しくインストールされているか確認
    echo 3. 管理者権限で実行を試す
    pause
    exit /b 1
)

REM FFmpegの確認
echo.
echo 🔍 FFmpegを確認中...
ffmpeg -version > nul 2>&1
if errorlevel 1 (
    echo ⚠️ FFmpegが見つかりません
    echo.
    echo FFmpegは音声再生に必要です。以下の方法でインストールできます:
    echo.
    echo 方法1: Chocolateyを使用 (推奨)
    echo   choco install ffmpeg
    echo.
    echo 方法2: 手動インストール
    echo   1. https://ffmpeg.org/download.html からダウンロード
    echo   2. PATHに追加
    echo.
    echo FFmpegなしでもダウンロード機能は利用できますが、音声再生はできません
) else (
    echo ✅ FFmpegが利用可能です
)

REM 設定ファイルの作成
echo.
echo ⚙️ 設定ファイルを確認中...
if not exist config.py (
    echo config.pyが見つかりません。サンプルから作成します...
    copy config_example.py config.py > nul
    
    if errorlevel 1 (
        echo ❌ 設定ファイルの作成に失敗しました
        pause
        exit /b 1
    )
    
    echo ✅ config.pyを作成しました
    echo.
    echo ⚠️ 重要: config.pyを編集してDISCORD_TOKENを設定してください
    echo.
    echo 設定手順:
    echo 1. config.pyをテキストエディタで開く
    echo 2. DISCORD_TOKEN = 'your_discord_bot_token_here' の部分を編集
    echo 3. 'your_discord_bot_token_here'を実際のDiscordボットトークンに置き換え
    echo 4. ファイルを保存
    echo.
    echo Discord Developer Portal: https://discord.com/developers/applications
    echo.
    
    REM 設定ファイルを開く
    choice /c YN /m "config.pyを今すぐ開きますか？ (Y/N)"
    if errorlevel 2 goto skip_open
    if errorlevel 1 (
        echo config.pyを開いています...
        start notepad config.py
    )
    :skip_open
) else (
    echo ✅ config.pyが存在します
)

echo.
echo 🎉 セットアップ完了！
echo.
echo 次の手順:
echo 1. config.pyでDISCORD_TOKENを設定 (まだの場合)
echo 2. start_bot.bat を実行してボットを起動
echo.
pause
