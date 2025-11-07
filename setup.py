#!/usr/bin/env python3
"""
Discord YouTube Downloader Bot セットアップスクリプト
"""

import os
import sys
import subprocess
import platform

def check_python_version():
    """Pythonバージョンをチェック"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8以上が必要です。")
        return False
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor} が検出されました")
    return True

def install_requirements():
    """依存関係をインストール"""
    print("📦 依存関係をインストール中...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ 依存関係のインストールが完了しました")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 依存関係のインストールに失敗しました: {e}")
        return False

def check_ffmpeg():
    """FFmpegがインストールされているかチェック"""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        print("✅ FFmpegがインストールされています")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ FFmpegがインストールされていません")
        return False

def install_ffmpeg():
    """FFmpegをインストール"""
    system = platform.system().lower()
    
    if system == "darwin":  # macOS
        print("🍎 macOS用のFFmpegインストール手順:")
        print("1. Homebrewをインストールしていない場合:")
        print("   /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")
        print("2. FFmpegをインストール:")
        print("   brew install ffmpeg")
        
    elif system == "linux":
        print("🐧 Linux用のFFmpegインストール手順:")
        print("Ubuntu/Debian:")
        print("   sudo apt update && sudo apt install ffmpeg")
        print("CentOS/RHEL:")
        print("   sudo yum install ffmpeg")
        
    elif system == "windows":
        print("🪟 Windows用のFFmpegインストール手順:")
        print("1. https://ffmpeg.org/download.html からFFmpegをダウンロード")
        print("2. アーカイブを解凍")
        print("3. binフォルダをPATH環境変数に追加")
        
    print("\nFFmpegのインストールが完了したら、このスクリプトを再実行してください。")

def create_env_template():
    """環境変数テンプレートファイルを作成"""
    env_content = """# Discord Bot Token
# Discord Developer Portal (https://discord.com/developers/applications) で取得
DISCORD_TOKEN=your_discord_bot_token_here

# Bot Prefix (コマンドの接頭辞)
BOT_PREFIX=!

# Download Directory (ダウンロード先ディレクトリ)
DOWNLOAD_DIR=downloads

# Max File Size (最大ファイルサイズ、MB単位)
# Discordの制限は25MB
MAX_FILE_SIZE=25
"""
    
    if not os.path.exists('.env'):
        with open('.env', 'w', encoding='utf-8') as f:
            f.write(env_content)
        print("✅ .envファイルを作成しました")
        print("⚠️  .envファイルでDISCORD_TOKENを設定してください")
    else:
        print("ℹ️  .envファイルは既に存在します")

def main():
    """メイン関数"""
    print("🤖 Discord YouTube Downloader Bot セットアップ")
    print("=" * 50)
    
    # Pythonバージョンチェック
    if not check_python_version():
        return
    
    # 依存関係インストール
    if not install_requirements():
        return
    
    # FFmpegチェック
    if not check_ffmpeg():
        install_ffmpeg()
        return
    
    # 環境変数テンプレート作成
    create_env_template()
    
    print("\n🎉 セットアップが完了しました！")
    print("\n次の手順:")
    print("1. .envファイルでDISCORD_TOKENを設定")
    print("2. Discord Developer Portalでボットアプリケーションを作成")
    print("3. ボットをサーバーに招待")
    print("4. python discord_bot.py でボットを起動")
    
    print("\n📚 詳細なセットアップ手順:")
    print("https://discordpy.readthedocs.io/en/stable/discord.html")

if __name__ == "__main__":
    main()
