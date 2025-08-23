# 🤖 Discord YouTube Downloader Bot

Discordから直接YouTube動画をダウンロードできるボットです。高品質な動画形式とMP3変換に対応しています。

## ✨ 機能

- 🎬 **高品質動画ダウンロード**: 144p〜2160pの画質選択
- 🎵 **MP3変換**: 音声ファイルへの変換
- 📱 **Discord統合**: チャットから簡単操作
- 🔄 **非同期処理**: 長時間のダウンロードも非ブロッキング
- 📁 **自動ファイル管理**: Discord制限内のファイルは自動アップロード
- 🎨 **美しいUI**: リッチなEmbedメッセージ

## 🚀 セットアップ

### 1. リポジトリのクローン

```bash
git clone https://github.com/natuki53/YouTube_Downloader.git
cd YouTube_Downloader
```

### 2. 自動セットアップ

```bash
python setup.py
```

このスクリプトは以下を自動実行します：
- Pythonバージョンチェック
- 依存関係のインストール
- FFmpegの確認
- 環境変数テンプレートの作成

### 3. 手動セットアップ

#### 依存関係のインストール

```bash
pip install -r requirements.txt
```

#### FFmpegのインストール

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt update && sudo apt install ffmpeg
```

**Windows:**
[FFmpeg公式サイト](https://ffmpeg.org/download.html)からダウンロード

### 4. Discord Botの作成

1. [Discord Developer Portal](https://discord.com/developers/applications)にアクセス
2. "New Application"をクリック
3. アプリケーション名を入力
4. "Bot"セクションで"Add Bot"をクリック
5. Tokenをコピー（`config.py`に設定）

### 5. 環境変数の設定

`.env`ファイルを作成し、Discordトークンを設定：

```env
DISCORD_TOKEN=your_actual_bot_token_here
BOT_PREFIX=!
DOWNLOAD_DIR=downloads
MAX_FILE_SIZE=25
```

### 6. ボットの起動

```bash
python discord_bot.py
```

## 📖 使用方法

### 基本コマンド

| コマンド | 説明 | 使用例 |
|---------|------|--------|
| `!download <URL> [画質]` | 動画をダウンロード | `!download https://youtube.com/watch?v=... 1080p` |
| `!download_mp3 <URL>` | MP3に変換してダウンロード | `!download_mp3 https://youtube.com/watch?v=...` |
| `!quality` | 利用可能な画質を表示 | `!quality` |
| `!help` | ヘルプを表示 | `!help` |

### 画質オプション

- `144p` - 低画質、小ファイルサイズ
- `240p` - 標準画質
- `360p` - 中画質
- `480p` - 高画質
- `720p` - HD画質（デフォルト）
- `1080p` - Full HD画質
- `1440p` - 2K画質
- `2160p` - 4K画質

### 使用例

#### 高画質動画のダウンロード
```
!download https://www.youtube.com/watch?v=dQw4w9WgXcQ 1080p
```

#### MP3変換
```
!download_mp3 https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

## 🔧 設定

### config.py

```python
# Discord Bot設定
DISCORD_TOKEN = 'your_bot_token'
BOT_PREFIX = '!'

# ダウンロード設定
DOWNLOAD_DIR = 'downloads'
MAX_FILE_SIZE = 25  # MB

# サポートされている画質
SUPPORTED_QUALITIES = ['144p', '240p', '360p', '480p', '720p', '1080p', '1440p', '2160p']
```

### 環境変数

| 変数名 | 説明 | デフォルト値 |
|--------|------|-------------|
| `DISCORD_TOKEN` | Discordボットトークン | 必須 |
| `BOT_PREFIX` | コマンド接頭辞 | `!` |
| `DOWNLOAD_DIR` | ダウンロード先ディレクトリ | `downloads` |
| `MAX_FILE_SIZE` | 最大ファイルサイズ（MB） | `25` |

## 📁 ファイル構造

```
YouTube_Discord_Bot/
├── discord_bot.py          # メインのDiscordボット
├── config.py               # 設定ファイル
├── setup.py                # セットアップスクリプト
├── requirements.txt         # 依存関係
├── README.md               # このファイル
├── .env                    # 環境変数（自動生成）
├── downloads/              # ダウンロード先ディレクトリ
└── YouTube_Downloader/     # YouTubeダウンローダーモジュール
    ├── youtube_video_downloader.py
    ├── youtube_to_mp3.py
    └── ...
```

## 🛠️ 技術仕様

- **Python**: 3.8+
- **Discord.py**: 2.3.0+
- **yt-dlp**: 2023.12.30+
- **FFmpeg**: 動画・音声処理
- **非同期処理**: asyncio対応

## 🔒 セキュリティと制限

- **ファイルサイズ制限**: Discordの25MB制限に準拠
- **URL検証**: YouTube URLのみ受け付け
- **一時ファイル**: アップロード後は自動削除
- **エラーハンドリング**: 適切なエラーメッセージ

## 🚨 注意事項

- YouTubeの利用規約を遵守してください
- 著作権で保護されたコンテンツのダウンロードは法律に違反する可能性があります
- 個人使用目的でのみ使用してください
- 大量のダウンロードは避けてください

## 🐛 トラブルシューティング

### よくある問題

#### 1. FFmpegが見つからない
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

#### 2. Discordトークンエラー
- `.env`ファイルでトークンが正しく設定されているか確認
- ボットアプリケーションが正しく作成されているか確認

#### 3. ダウンロードエラー
- インターネット接続を確認
- YouTube URLが有効か確認
- 動画が公開されているか確認

#### 4. ファイルサイズエラー
- `config.py`で`MAX_FILE_SIZE`を調整
- より低い画質を選択

### ログの確認

```bash
# ログレベルを変更
logging.basicConfig(level=logging.DEBUG)
```

## 📄 ライセンス

このプロジェクトはMITライセンスの下で公開されています。

## 🙏 謝辞

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - YouTubeダウンロードエンジン
- [discord.py](https://github.com/Rapptz/discord.py) - Discord APIライブラリ
- [FFmpeg](https://ffmpeg.org/) - 動画・音声処理


---

**⚠️ 免責事項**: このボットは教育目的で作成されています。著作権法を遵守してご利用ください。
