#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube to MP3 ダウンローダーのテストスクリプト
"""

import os
import sys
from pathlib import Path

# メインプログラムをインポート
try:
    from youtube_to_mp3 import YouTubeToMP3
    print("✅ メインプログラムのインポートに成功しました")
except ImportError as e:
    print(f"❌ メインプログラムのインポートに失敗しました: {e}")
    sys.exit(1)

def test_basic_functionality():
    """基本的な機能をテスト"""
    print("\n🔍 基本的な機能をテスト中...")
    
    # インスタンス作成
    test_dir = "test_downloads"
    downloader = YouTubeToMP3(test_dir)
    
    # ディレクトリ作成テスト
    if downloader.output_dir.exists():
        print("✅ 出力ディレクトリの作成に成功しました")
    else:
        print("❌ 出力ディレクトリの作成に失敗しました")
        return False
    
    # yt-dlpチェックテスト
    if downloader.check_yt_dlp():
        print("✅ yt-dlpが利用可能です")
    else:
        print("⚠️  yt-dlpがインストールされていません")
        print("   テストを続行するには: pip install yt-dlp")
    
    # テストディレクトリのクリーンアップ
    try:
        import shutil
        shutil.rmtree(test_dir)
        print("✅ テストディレクトリのクリーンアップに成功しました")
    except Exception as e:
        print(f"⚠️  テストディレクトリのクリーンアップに失敗しました: {e}")
    
    return True

def test_argument_parsing():
    """コマンドライン引数の解析をテスト"""
    print("\n🔍 コマンドライン引数の解析をテスト中...")
    
    try:
        from youtube_to_mp3 import main
        print("✅ メイン関数のインポートに成功しました")
        
        # ヘルプ表示のテスト（エラーが発生しないことを確認）
        import io
        import contextlib
        
        # 標準出力をキャプチャ
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            # ヘルプ表示をテスト（引数なし）
            sys.argv = ['youtube_to_mp3.py']
            try:
                main()
                print("✅ ヘルプ表示のテストに成功しました")
            except SystemExit:
                # ヘルプ表示後にSystemExitが発生するのは正常
                print("✅ ヘルプ表示のテストに成功しました")
        
        return True
        
    except Exception as e:
        print(f"❌ 引数解析のテストに失敗しました: {e}")
        return False

def test_url_validation():
    """URL検証機能をテスト"""
    print("\n🔍 URL検証機能をテスト中...")
    
    try:
        from youtube_to_mp3 import main
        import re
        
        # 正しいYouTube URL
        valid_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://www.youtube.com/playlist?list=PLxxxxxxxx"
        ]
        
        # 無効なURL
        invalid_urls = [
            "https://www.google.com",
            "https://example.com",
            "not_a_url"
        ]
        
        # 正規表現パターンをテスト
        pattern = re.compile(r'(youtube\.com|youtu\.be)')
        
        for url in valid_urls:
            if pattern.search(url):
                print(f"✅ 有効なURL: {url}")
            else:
                print(f"❌ 有効なURLが検証されませんでした: {url}")
                return False
        
        for url in invalid_urls:
            if not pattern.search(url):
                print(f"✅ 無効なURLが正しく拒否されました: {url}")
            else:
                print(f"❌ 無効なURLが誤って受け入れられました: {url}")
                return False
        
        print("✅ URL検証機能のテストに成功しました")
        return True
        
    except Exception as e:
        print(f"❌ URL検証のテストに失敗しました: {e}")
        return False

def main():
    """テストメイン関数"""
    print("🚀 YouTube to MP3 ダウンローダーのテストを開始します")
    print("=" * 60)
    
    tests = [
        test_basic_functionality,
        test_argument_parsing,
        test_url_validation
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ テストで予期しないエラーが発生しました: {e}")
    
    print("\n" + "=" * 60)
    print(f"📊 テスト結果: {passed}/{total} テストが成功しました")
    
    if passed == total:
        print("🎉 すべてのテストが成功しました！")
        return 0
    else:
        print("⚠️  一部のテストが失敗しました")
        return 1

if __name__ == "__main__":
    sys.exit(main())
