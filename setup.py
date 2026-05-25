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

def ensure_venv():
    """仮想環境を作成（未作成の場合）"""
    venv_dir = os.path.join(os.path.dirname(__file__) or ".", ".venv")
    if not os.path.isdir(venv_dir):
        print("📦 仮想環境 .venv を作成中...")
        subprocess.check_call([sys.executable, "-m", "venv", venv_dir])
        print("✅ .venv を作成しました")
    else:
        print("ℹ️  .venv は既に存在します")
    return venv_dir


def install_requirements():
    """依存関係をインストール（.venv 内）"""
    print("📦 依存関係をインストール中...")
    try:
        venv_dir = ensure_venv()
        pip = os.path.join(venv_dir, "bin", "pip")
        if not os.path.isfile(pip):
            pip = os.path.join(venv_dir, "Scripts", "pip")  # Windows
        subprocess.check_call([pip, "install", "-r", "requirements.txt"])
        print("✅ 依存関係のインストールが完了しました")
        print("   起動前: source .venv/bin/activate")
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
    example = ".env.example"
    target = ".env"

    if os.path.exists(target):
        print("ℹ️  .env は既に存在します")
        return

    if os.path.exists(example):
        with open(example, "r", encoding="utf-8") as src:
            content = src.read()
        with open(target, "w", encoding="utf-8") as dst:
            dst.write(content)
        print("✅ .env.example から .env を作成しました")
    else:
        print("⚠️  .env.example が見つかりません。手動で .env を作成してください")

    print("⚠️  .env を開き、DISCORD_TOKEN に Bot トークンを設定してください")

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
    print("1. .env で DISCORD_TOKEN を設定（cp .env.example .env）")
    print("2. Discord Developer Portal でボットを作成")
    print("3. ボットをサーバーに招待（applications.commands スコープ）")
    print("4. source .venv/bin/activate")
    print("5. python main.py でボットを起動")
    
    print("\n📚 詳細なセットアップ手順:")
    print("https://discordpy.readthedocs.io/en/stable/discord.html")

if __name__ == "__main__":
    main()
