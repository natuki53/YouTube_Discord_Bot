# YouTube 動画ダウンローダー

YouTubeからyt-dlpを使って高品質な動画形式でダウンロードできるPythonプログラムです。

## 機能

- YouTube動画を高品質な動画形式でダウンロード
- 画質選択（144p, 240p, 360p, 480p, 720p, 1080p, 1440p, 2160p）
- 高品質音声との自動マージ
- プレイリスト対応
- 特定の形式IDでの直接指定
- 音声品質・形式のカスタマイズ
- 利用可能な形式一覧表示
- ダウンロード済みファイル一覧表示

## インストール

### 1. 依存関係のインストール

```bash
pip install -r requirements.txt
```

または、yt-dlpを直接インストール：

```bash
pip install yt-dlp
```

### 2. FFmpegのインストール（動画・音声処理に必要）

#### macOS
```bash
brew install ffmpeg
```

#### Ubuntu/Debian
```bash
sudo apt update
sudo apt install ffmpeg
```

#### Windows
[FFmpeg公式サイト](https://ffmpeg.org/download.html)からダウンロードしてインストール

## 使用方法

### 基本的な使い方

```bash
# 単一動画をダウンロード（デフォルト: 720p）
python youtube_video_downloader.py "https://www.youtube.com/watch?v=VIDEO_ID"

# 高画質（1080p）でダウンロード
python youtube_video_downloader.py "https://www.youtube.com/watch?v=VIDEO_ID" --quality 1080p

# プレイリストをダウンロード
python youtube_video_downloader.py "https://www.youtube.com/playlist?list=PLAYLIST_ID" --playlist

# プレイリストから最初の5個の動画のみダウンロード
python youtube_video_downloader.py "https://www.youtube.com/playlist?list=PLAYLIST_ID" --playlist --limit 5

# 利用可能な形式一覧を表示
python youtube_video_downloader.py "https://www.youtube.com/watch?v=VIDEO_ID" --show-formats

# ダウンロード済みファイル一覧を表示
python youtube_video_downloader.py --list
```

### コマンドラインオプション

- `url`: YouTube動画またはプレイリストのURL
- `-o, --output`: 出力ディレクトリ（デフォルト: downloads）
- `-q, --quality`: 動画画質（144p, 240p, 360p, 480p, 720p, 1080p, 1440p, 2160p、デフォルト: 720p）
- `-f, --format-id`: 特定の形式IDを直接指定（例: "270+234"）
- `-a, --audio-quality`: 音声品質（0=最高品質, 9=最低品質、デフォルト: 0）
- `--audio-format`: 音声形式（best, aac, flac, mp3, m4a, opus, vorbis, wav、デフォルト: best）
- `-p, --playlist`: プレイリストとしてダウンロード
- `-l, --limit`: プレイリストからダウンロードする動画数の制限
- `--show-formats`: 利用可能な形式一覧を表示
- `--list`: ダウンロード済みファイル一覧を表示

## 画質と形式IDの対応

プログラムは**動的に**各動画の利用可能な形式を分析し、指定された画質に最適な形式IDを自動選択します：

- **144p**: 144p以下の最高品質動画 + 最高品質音声
- **240p**: 240p以下の最高品質動画 + 最高品質音声
- **360p**: 360p以下の最高品質動画 + 最高品質音声
- **480p**: 480p以下の最高品質動画 + 最高品質音声
- **720p**: 720p以下の最高品質動画 + 最高品質音声
- **1080p**: 1080p以下の最高品質動画 + 最高品質音声
- **1440p**: 1440p以下の最高品質動画 + 最高品質音声
- **2160p**: 2160p以下の最高品質動画 + 最高品質音声

### 動的選択の利点

✅ **柔軟性**: 動画ごとに最適な形式を自動選択  
✅ **成功率向上**: 利用できない形式でのエラーを回避  
✅ **品質最適化**: 各動画で利用可能な最高品質を自動選択  
✅ **保守性**: 固定IDの更新が不要

## 使用例

### 1. 高画質動画をダウンロード
```bash
# 1080pでダウンロード
python youtube_video_downloader.py "https://www.youtube.com/watch?v=VIDEO_ID" --quality 1080p

# 720pでダウンロード
python youtube_video_downloader.py "https://www.youtube.com/watch?v=VIDEO_ID" --quality 720p
```

### 2. 特定の形式IDでダウンロード
```bash
# カスタム形式IDを指定
python youtube_video_downloader.py "https://www.youtube.com/watch?v=VIDEO_ID" --format-id "270+234"
```

### 3. 高品質音声でダウンロード
```bash
# 最高音質でダウンロード
python youtube_video_downloader.py "https://www.youtube.com/watch?v=VIDEO_ID" --quality 1080p --audio-quality 0

# FLAC形式でダウンロード
python youtube_video_downloader.py "https://www.youtube.com/watch?v=VIDEO_ID" --quality 1080p --audio-format flac
```

### 4. プレイリスト全体をダウンロード
```bash
python youtube_video_downloader.py "https://www.youtube.com/playlist?list=PLxxxxxxxx" --playlist
```

### 5. 利用可能な形式を確認
```bash
python youtube_video_downloader.py "https://www.youtube.com/watch?v=VIDEO_ID" --show-formats
```

## 出力

- 動画ファイルは指定したディレクトリ（デフォルト: `downloads`）に保存されます
- ファイル名は動画のタイトルが使用されます
- 出力形式はMP4に統一されます
- プレイリストの場合は、プレイリスト名のサブディレクトリが作成されます

## 注意事項

- YouTubeの利用規約を遵守してください
- 著作権で保護されたコンテンツのダウンロードは法律に違反する可能性があります
- 個人使用目的でのみ使用してください
- 大量のダウンロードは避けてください

## トラブルシューティング

### yt-dlpがインストールされていない場合
```bash
pip install yt-dlp
```

### FFmpegがインストールされていない場合
動画・音声処理にFFmpegが必要です。上記のインストール手順を参照してください。

### ダウンロードが失敗する場合
- インターネット接続を確認
- YouTubeのURLが正しいか確認
- 動画が公開されているか確認
- 地域制限がないか確認
- `--show-formats`で利用可能な形式を確認

### 画質が期待と異なる場合
- `--show-formats`で利用可能な形式を確認
- `--format-id`で特定の形式IDを直接指定

## ライセンス

このプログラムはMITライセンスの下で公開されています。
