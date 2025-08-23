#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTubeから動画形式でダウンロードするプログラム
yt-dlpを使用してYouTube動画を指定した画質でダウンロードします
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path
import re

class YouTubeVideoDownloader:
    def __init__(self, output_dir="downloads"):
        """
        YouTubeVideoDownloaderクラスの初期化
        
        Args:
            output_dir (str): ダウンロード先ディレクトリ
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.yt_dlp_path = None
        
    def check_yt_dlp(self):
        """
        yt-dlpがインストールされているかチェック
        
        Returns:
            bool: yt-dlpが利用可能な場合True
        """
        # yt-dlpのパスを探す
        yt_dlp_paths = [
            'yt-dlp',  # PATHにある場合
            '/Users/natuki/Library/Python/3.9/bin/yt-dlp',  # macOSの一般的なパス
            '/usr/local/bin/yt-dlp',  # Homebrewのパス
            '/opt/homebrew/bin/yt-dlp'  # Apple Silicon MacのHomebrewパス
        ]
        
        for path in yt_dlp_paths:
            try:
                result = subprocess.run([path, '--version'], 
                                      capture_output=True, text=True, check=True)
                print(f"yt-dlp バージョン: {result.stdout.strip()}")
                self.yt_dlp_path = path
                return True
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        
        print("エラー: yt-dlpがインストールされていません")
        print("インストール方法: pip install yt-dlp")
        return False
    
    def get_available_formats(self, url):
        """
        動画の利用可能な形式を取得
        
        Args:
            url (str): YouTube動画のURL
            
        Returns:
            dict: 形式IDをキーとした形式情報の辞書
        """
        try:
            cmd = [self.yt_dlp_path, '--list-formats', url]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return self.parse_formats_output(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"形式一覧の取得に失敗: {e}")
            if e.stderr:
                print(f"エラー詳細: {e.stderr}")
            return {}
    
    def parse_formats_output(self, output):
        """
        yt-dlpの形式一覧出力をパース
        
        Args:
            output (str): yt-dlp --list-formatsの出力
            
        Returns:
            dict: 形式IDをキーとした形式情報の辞書
        """
        formats = {}
        lines = output.strip().split('\n')
        
        for line in lines:
            # 形式ID、拡張子、解像度、FPS、ファイルサイズ、ビットレート、プロトコル、VCODEC、ACODEC
            # 例: ID  EXT   RESOLUTION FPS │   FILESIZE   TBR PROTO │ VCODEC          VBR ACODEC
            if 'ID' in line and 'EXT' in line and 'RESOLUTION' in line:
                continue  # ヘッダー行をスキップ
            
            # 形式情報行をパース
            parts = line.split()
            if len(parts) >= 9:
                try:
                    format_id = parts[0]
                    ext = parts[1]
                    resolution = parts[2]
                    fps = parts[3] if parts[3] != '0' else '30'
                    filesize = parts[5] if len(parts) > 5 else '0'
                    tbr = parts[6] if len(parts) > 6 else '0'
                    protocol = parts[8] if len(parts) > 8 else ''
                    vcodec = parts[9] if len(parts) > 9 else ''
                    acodec = parts[10] if len(parts) > 10 else ''
                    
                    # 解像度から高さを抽出
                    height = 0
                    if 'x' in resolution:
                        height = int(resolution.split('x')[1])
                    elif resolution == 'audio':
                        height = 0
                    
                    formats[format_id] = {
                        'ext': ext,
                        'resolution': resolution,
                        'height': height,
                        'fps': fps,
                        'filesize': filesize,
                        'tbr': tbr,
                        'protocol': protocol,
                        'vcodec': vcodec,
                        'acodec': acodec,
                        'is_video': vcodec != 'audio' and height > 0,
                        'is_audio': acodec != 'audio' or height == 0
                    }
                except (ValueError, IndexError):
                    continue
        
        return formats
    
    def select_best_format(self, quality, available_formats):
        """
        画質に応じて最適な形式IDを選択
        
        Args:
            quality (str): 要求画質
            available_formats (dict): 利用可能な形式一覧
            
        Returns:
            str: 最適な形式ID（動画+音声）
        """
        # 画質から目標高さを取得
        target_height = self.get_target_height(quality)
        
        # 動画形式と音声形式を分離
        video_formats = {}
        audio_formats = {}
        
        for format_id, format_info in available_formats.items():
            if format_info['is_video']:
                video_formats[format_id] = format_info
            elif format_info['is_audio']:
                audio_formats[format_id] = format_info
        
        # 最適な動画形式を選択
        best_video_id = self.select_best_video_format(target_height, video_formats)
        
        # 最適な音声形式を選択
        best_audio_id = self.select_best_audio_format(audio_formats)
        
        if best_video_id and best_audio_id:
            return f"{best_video_id}+{best_audio_id}"
        elif best_video_id:
            return best_video_id
        else:
            # フォールバック: 利用可能な最高品質
            return "best"
    
    def get_target_height(self, quality):
        """
        画質文字列から目標高さを取得
        
        Args:
            quality (str): 画質文字列（例: "1080p", "720p"）
            
        Returns:
            int: 目標高さ
        """
        height_map = {
            "144p": 144,
            "240p": 240,
            "360p": 360,
            "480p": 480,
            "720p": 720,
            "1080p": 1080,
            "1440p": 1440,
            "2160p": 2160
        }
        return height_map.get(quality, 720)
    
    def select_best_video_format(self, target_height, video_formats):
        """
        最適な動画形式を選択
        
        Args:
            target_height (int): 目標高さ
            video_formats (dict): 動画形式一覧
            
        Returns:
            str: 最適な動画形式ID
        """
        if not video_formats:
            return None
        
        # 目標高さ以下の最高品質形式を選択
        candidates = []
        for format_id, format_info in video_formats.items():
            if format_info['height'] <= target_height:
                # ビットレートを数値に変換
                try:
                    tbr = float(format_info['tbr'].replace('k', ''))
                except (ValueError, AttributeError):
                    tbr = 0
                
                candidates.append((format_id, format_info['height'], tbr))
        
        if not candidates:
            # 目標高さ以下がない場合、最も近い高さを選択
            candidates = [(fid, finfo['height'], 0) for fid, finfo in video_formats.items()]
        
        # 高さとビットレートでソート（高さ優先、同高さならビットレート優先）
        candidates.sort(key=lambda x: (x[1], x[2]), reverse=True)
        
        return candidates[0][0] if candidates else None
    
    def select_best_audio_format(self, audio_formats):
        """
        最適な音声形式を選択
        
        Args:
            audio_formats (dict): 音声形式一覧
            
        Returns:
            str: 最適な音声形式ID
        """
        if not audio_formats:
            return None
        
        # 音声品質の高い順でソート（ビットレートで判断）
        candidates = []
        for format_id, format_info in audio_formats.items():
            try:
                tbr = float(format_info['tbr'].replace('k', ''))
            except (ValueError, AttributeError):
                tbr = 0
            
            candidates.append((format_id, tbr))
        
        # ビットレートの高い順でソート
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        return candidates[0][0] if candidates else None
    
    def download_video(self, url, quality="720p", format_id=None, audio_quality="0", audio_format="best"):
        """
        YouTube動画を動画形式でダウンロード
        
        Args:
            url (str): YouTube動画のURL
            quality (str): 動画の画質
            format_id (str): 特定の形式ID（オプション）
            audio_quality (str): 音声品質 (0=最高品質)
            audio_format (str): 音声形式
        
        Returns:
            bool: ダウンロードが成功した場合True
        """
        if not self.check_yt_dlp():
            return False
        
        # 出力ファイル名のテンプレート
        output_template = str(self.output_dir / "%(title)s.%(ext)s")
        
        # yt-dlpコマンドの構築
        # 形式IDが指定されている場合はそれを使用、そうでなければ動的に選択
        if format_id:
            format_spec = format_id
            print(f"カスタム形式ID: {format_id}")
        else:
            print(f"画質 {quality} の最適な形式を動的に選択中...")
            available_formats = self.get_available_formats(url)
            
            if available_formats:
                format_spec = self.select_best_format(quality, available_formats)
                print(f"選択された形式: {format_spec}")
            else:
                print("形式の取得に失敗したため、デフォルト形式を使用")
                format_spec = "best"
        
        cmd = [
            self.yt_dlp_path,
            '--format', format_spec,                    # 選択された形式ID（動画+音声）
            '--output', output_template,                 # 出力先
            '--no-playlist',                             # プレイリストの場合は最初の動画のみ
            '--audio-quality', audio_quality,            # 音声品質
            '--audio-format', audio_format,              # 音声形式
            '--merge-output-format', 'mp4',              # 出力形式をMP4に統一
            url
        ]
        
        try:
            print(f"動画ダウンロード開始: {url}")
            print(f"出力先: {self.output_dir}")
            print(f"画質: {quality}")
            print("-" * 50)
            
            # yt-dlpコマンドを実行
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            
            print("動画ダウンロード完了!")
            print(result.stdout)
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"動画ダウンロードエラー: {e}")
            if e.stderr:
                print(f"エラー詳細: {e.stderr}")
            return False
        except Exception as e:
            print(f"予期しないエラー: {e}")
            return False
    
    def show_formats(self, url):
        """
        利用可能な形式一覧を表示
        
        Args:
            url (str): YouTube動画のURL
        """
        if not self.check_yt_dlp():
            return
        
        print(f"利用可能な形式を取得中: {url}")
        print("-" * 50)
        
        available_formats = self.get_available_formats(url)
        
        if not available_formats:
            print("形式の取得に失敗しました")
            return
        
        # 形式一覧を表示
        print("利用可能な形式:")
        print("ID  EXT   RESOLUTION FPS │   FILESIZE   TBR │ VCODEC          ACODEC")
        print("-" * 80)
        
        # 動画形式と音声形式を分離して表示
        video_formats = []
        audio_formats = []
        
        for format_id, format_info in available_formats.items():
            if format_info['is_video']:
                video_formats.append((format_id, format_info))
            elif format_info['is_audio']:
                audio_formats.append((format_id, format_info))
        
        # 動画形式を高さ順でソート
        video_formats.sort(key=lambda x: x[1]['height'], reverse=True)
        
        # 動画形式を表示
        for format_id, format_info in video_formats:
            height_str = f"{format_info['height']}p" if format_info['height'] > 0 else "audio"
            print(f"{format_id:3} {format_info['ext']:4} {format_info['resolution']:10} {format_info['fps']:3} │ {format_info['filesize']:10} {format_info['tbr']:6} │ {format_info['vcodec']:15} {format_info['acodec']:8}")
        
        print("-" * 80)
        print("音声形式:")
        for format_id, format_info in audio_formats:
            print(f"{format_id:3} {format_info['ext']:4} {format_info['resolution']:10} {format_info['fps']:3} │ {format_info['filesize']:10} {format_info['tbr']:6} │ {format_info['vcodec']:15} {format_info['acodec']:8}")
        
        # 推奨形式の提案
        print("\n推奨形式:")
        for quality in ["1080p", "720p", "480p", "360p"]:
            recommended = self.select_best_format(quality, available_formats)
            if recommended:
                print(f"  {quality}: {recommended}")
    
    def download_playlist(self, playlist_url, quality="720p", limit=None, format_id=None, audio_quality="0", audio_format="best"):
        """
        プレイリストから動画をダウンロード
        
        Args:
            playlist_url (str): YouTubeプレイリストのURL
            quality (str): 動画の画質
            limit (int): ダウンロードする動画数の制限
            format_id (str): 特定の形式ID（オプション）
            audio_quality (str): 音声品質 (0=最高品質)
            audio_format (str): 音声形式
        
        Returns:
            bool: ダウンロードが成功した場合True
        """
        if not self.check_yt_dlp():
            return False
        
        output_template = str(self.output_dir / "%(playlist_title)s/%(title)s.%(ext)s")
        
        # 形式IDが指定されている場合はそれを使用、そうでなければ動的に選択
        if format_id:
            format_spec = format_id
            print(f"カスタム形式ID: {format_id}")
        else:
            print(f"画質 {quality} の最適な形式を動的に選択中...")
            # プレイリストの場合は最初の動画で形式を決定
            available_formats = self.get_available_formats(playlist_url)
            
            if available_formats:
                format_spec = self.select_best_format(quality, available_formats)
                print(f"選択された形式: {format_spec}")
            else:
                print("形式の取得に失敗したため、デフォルト形式を使用")
                format_spec = "best"
        
        cmd = [
            self.yt_dlp_path,
            '--format', format_spec,
            '--output', output_template,
            '--audio-quality', audio_quality,            # 音声品質
            '--audio-format', audio_format,              # 音声形式
            '--merge-output-format', 'mp4',              # 出力形式をMP4に統一
            playlist_url
        ]
        
        if limit:
            cmd.extend(['--playlist-items', f'1-{limit}'])
        
        try:
            print(f"プレイリスト動画ダウンロード開始: {playlist_url}")
            print(f"出力先: {self.output_dir}")
            print(f"画質: {quality}")
            if limit:
                print(f"制限: {limit}個の動画")
            print("-" * 50)
            
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            
            print("プレイリスト動画ダウンロード完了!")
            print(result.stdout)
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"プレイリスト動画ダウンロードエラー: {e}")
            if e.stderr:
                print(f"エラー詳細: {e.stderr}")
            return False
    
    def show_formats(self, url):
        """
        利用可能な形式一覧を表示
        
        Args:
            url (str): YouTube動画のURL
        
        Returns:
            bool: 成功した場合True
        """
        if not self.check_yt_dlp():
            return False
        
        cmd = [self.yt_dlp_path, '--list-formats', url]
        
        try:
            print(f"利用可能な形式を取得中: {url}")
            print("-" * 50)
            
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(result.stdout)
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"形式一覧の取得エラー: {e}")
            if e.stderr:
                print(f"エラー詳細: {e.stderr}")
            return False
        except Exception as e:
            print(f"予期しないエラー: {e}")
            return False
    
    def list_downloads(self):
        """
        ダウンロード済みの動画ファイル一覧を表示
        """
        # 動画ファイルを検索
        video_files = list(self.output_dir.glob("**/*.mp4")) + list(self.output_dir.glob("**/*.webm")) + list(self.output_dir.glob("**/*.mkv"))
        
        if not video_files:
            print("ダウンロード済みの動画ファイルが見つかりません")
            return
        
        print(f"ダウンロード済み動画ファイル ({len(video_files)}個):")
        print("-" * 50)
        
        for i, video_file in enumerate(video_files, 1):
            file_size = video_file.stat().st_size / (1024 * 1024)  # MB
            print(f"{i:2d}. {video_file.name}")
            print(f"    サイズ: {file_size:.1f} MB")
            print(f"    パス: {video_file}")
            print()

def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description="YouTubeから動画形式でダウンロードするプログラム",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 単一動画をダウンロード（画質指定 - 形式ID自動選択）
  python youtube_video_downloader.py "https://www.youtube.com/watch?v=VIDEO_ID"
  python youtube_video_downloader.py "https://www.youtube.com/watch?v=VIDEO_ID" --quality 1080p
  python youtube_video_downloader.py "https://www.youtube.com/watch?v=VIDEO_ID" --quality 720p
  
  # 高品質音声でダウンロード
  python youtube_video_downloader.py "https://www.youtube.com/watch?v=VIDEO_ID" --quality 1080p --audio-quality 0
  python youtube_video_downloader.py "https://www.youtube.com/watch?v=VIDEO_ID" --quality 1080p --audio-format flac
  
  # 特定の形式IDを指定してダウンロード
  python youtube_video_downloader.py "https://www.youtube.com/watch?v=VIDEO_ID" --format-id "232+234"
  python youtube_video_downloader.py "https://www.youtube.com/watch?v=VIDEO_ID" --format-id "270+234"
  
  # 利用可能な形式一覧を表示
  python youtube_video_downloader.py "https://www.youtube.com/watch?v=VIDEO_ID" --show-formats
  
  # プレイリストをダウンロード
  python youtube_video_downloader.py "https://www.youtube.com/playlist?list=PLAYLIST_ID" --playlist
  python youtube_video_downloader.py "https://www.youtube.com/playlist?list=PLAYLIST_ID" --playlist --quality 1080p --limit 5
  
  # ダウンロード済みファイル一覧を表示
  python youtube_video_downloader.py --list
        """
    )
    
    parser.add_argument('url', nargs='?', help='YouTube動画またはプレイリストのURL')
    parser.add_argument('-o', '--output', default='downloads', 
                       help='出力ディレクトリ (デフォルト: downloads)')
    parser.add_argument('-q', '--quality', default='720p', 
                       choices=['144p', '240p', '360p', '480p', '720p', '1080p', '1440p', '2160p'],
                       help='動画画質 (デフォルト: 720p)')
    parser.add_argument('-f', '--format-id', 
                       help='特定の形式IDを直接指定 (例: "232+233", "270+140")')
    parser.add_argument('-a', '--audio-quality', default='0',
                       choices=['0', '1', '2', '3', '4', '5', '6', '7', '8', '9'],
                       help='音声品質 (0=最高品質, 9=最低品質, デフォルト: 0)')
    parser.add_argument('--audio-format', default='best',
                       choices=['best', 'aac', 'flac', 'mp3', 'm4a', 'opus', 'vorbis', 'wav'],
                       help='音声形式 (デフォルト: best)')
    parser.add_argument('-p', '--playlist', action='store_true',
                       help='プレイリストとしてダウンロード')
    parser.add_argument('-l', '--limit', type=int,
                       help='プレイリストからダウンロードする動画数の制限')
    parser.add_argument('--list', action='store_true',
                       help='ダウンロード済み動画ファイル一覧を表示')
    parser.add_argument('--show-formats', action='store_true',
                       help='利用可能な形式一覧を表示')
    
    args = parser.parse_args()
    
    # インスタンス作成
    downloader = YouTubeVideoDownloader(args.output)
    
    if args.list:
        # ダウンロード済みファイル一覧表示
        downloader.list_downloads()
        return
    
    if not args.url:
        parser.print_help()
        return
    
    # URLがYouTubeのものかチェック
    if not re.search(r'(youtube\.com|youtu\.be)', args.url):
        print("エラー: 有効なYouTube URLを入力してください")
        return
    
    # 形式一覧表示
    if args.show_formats:
        downloader.show_formats(args.url)
        return
    
    try:
        if args.playlist:
            # プレイリストダウンロード
            success = downloader.download_playlist(args.url, args.quality, args.limit, args.format_id, args.audio_quality, args.audio_format)
        else:
            # 単一動画ダウンロード
            success = downloader.download_video(args.url, args.quality, args.format_id, args.audio_quality, args.audio_format)
        
        if success:
            print("\n✅ 動画ダウンロードが正常に完了しました!")
            print(f"ファイルは {args.output} ディレクトリに保存されています")
        else:
            print("\n❌ 動画ダウンロードに失敗しました")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\nダウンロードが中断されました")
        sys.exit(1)
    except Exception as e:
        print(f"\n予期しないエラーが発生しました: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
