# 🤖 Discord YouTube Downloader Bot

Discordから直接YouTube動画をダウンロードできるボットです。高品質な動画形式とMP3変換に対応しています。

## ✨ 機能

- 🎬 **高品質動画ダウンロード**: 144p〜1080pの画質選択
- 🎵 **MP3変換**: 音声ファイルへの変換
- 🎵 **音声再生**: ボイスチャンネルでの音楽再生
- 📱 **Discord統合**: スラッシュコマンドとチャットから簡単操作
- 🔄 **非同期処理**: 長時間のダウンロードも非ブロッキング
- 📁 **自動ファイル管理**: Discord制限内のファイルは自動アップロード
- 🎨 **美しいUI**: リッチなEmbedメッセージ
- 🎵 **音楽キュー**: 複数曲の順次再生

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

#### 新しい構造（推奨）
```bash
python main.py
# または
python3 main.py
```

#### 従来の方法（旧ファイル）
```bash
python discord_bot_old.py
```

## 📖 使用方法

### スラッシュコマンド（推奨）

| コマンド | 説明 | 使用例 |
|---------|------|--------|
| `/download <URL> <画質>` | 動画をダウンロード | `/download https://youtube.com/watch?v=... 1080p` |
| `/download_mp3 <URL>` | MP3に変換してダウンロード | `/download_mp3 https://youtube.com/watch?v=...` |
| `/play <URL>` | 音声をボイスチャンネルで再生 | `/play https://youtube.com/watch?v=...` |
| `/pause` | 音声再生を一時停止 | `/pause` |
| `/resume` | 音声再生を再開 | `/resume` |
| `/stop` | 音声再生を停止して切断 | `/stop` |
| `/skip` | 現在の曲をスキップ | `/skip` |
| `/queue` | 音楽キューを表示 | `/queue` |
| `/clear` | 音楽キューをクリア | `/clear` |
| `/quality` | 利用可能な画質を表示 | `/quality` |
| `/help` | ヘルプを表示 | `/help` |
| `/ping` | ボットの応答テスト | `/ping` |

### 従来のプレフィックスコマンド

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

### 使用例

#### 高画質動画のダウンロード
```
/download https://www.youtube.com/watch?v=dQw4w9WgXcQ 1080p
```

#### MP3変換
```
/download_mp3 https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

#### 音声再生
```
/play https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

## 🏗️ プロジェクト構造

### 新しい構造（リファクタリング後）

保守性と拡張性を向上させるため、プロジェクトを以下のようにモジュール化しました：

```
YouTube_Discord_Bot/
├── main.py                    # 新しいメインエントリーポイント
├── discord_bot_old.py        # 元のファイル（バックアップ）
├── config.py                  # 設定ファイル
├── requirements.txt
├── bot/                       # メインボットパッケージ
│   ├── __init__.py
│   ├── config/               # 設定管理
│   │   ├── __init__.py
│   │   ├── settings.py       # アプリケーション設定
│   │   └── discord_config.py # Discord設定
│   ├── utils/                # ユーティリティ
│   │   ├── __init__.py
│   │   ├── encoding.py       # エンコーディング処理
│   │   ├── file_utils.py     # ファイル操作
│   │   └── subprocess_utils.py # サブプロセス実行
│   ├── audio/                # 音声処理
│   │   ├── __init__.py
│   │   ├── track_info.py     # トラック情報
│   │   ├── queue_manager.py  # キュー管理
│   │   └── player.py         # 音声プレイヤー
│   ├── youtube/              # YouTube機能
│   │   ├── __init__.py
│   │   ├── url_handler.py    # URL処理
│   │   └── downloader.py     # ダウンロード機能
│   └── commands/             # Discordコマンド
│       ├── __init__.py
│       ├── music.py          # 音楽関連コマンド
│       ├── download.py       # ダウンロードコマンド
│       └── general.py        # 一般的なコマンド
└── YouTube_Downloader/       # 既存のダウンローダー
    ├── youtube_video_downloader.py
    └── youtube_to_mp3.py
```

### 従来の構造

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
SUPPORTED_QUALITIES = ['144p', '240p', '360p', '480p', '720p', '1080p']
```

### 環境変数

| 変数名 | 説明 | デフォルト値 |
|--------|------|-------------|
| `DISCORD_TOKEN` | Discordボットトークン | 必須 |
| `BOT_PREFIX` | コマンド接頭辞 | `!` |
| `DOWNLOAD_DIR` | ダウンロード先ディレクトリ | `downloads` |
| `MAX_FILE_SIZE` | 最大ファイルサイズ（MB） | `25` |

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
- `config.py`でトークンが正しく設定されているか確認
- ボットアプリケーションが正しく作成されているか確認

#### 3. ダウンロードエラー
- インターネット接続を確認
- YouTube URLが有効か確認
- 動画が公開されているか確認

#### 4. ファイルサイズエラー
- `config.py`で`MAX_FILE_SIZE`を調整
- より低い画質を選択

#### 5. インポートエラー（新しい構造）
- 現在のディレクトリがプロジェクトルートにあることを確認
- `bot/`ディレクトリとその中の`__init__.py`ファイルが存在することを確認

### ログの確認

```bash
# ログレベルを変更
logging.basicConfig(level=logging.DEBUG)
```

## 🔄 移行ガイド

### 従来のファイルから新しい構造への移行

1. **設定確認**: `config.py`のDISCORD_TOKENが正しく設定されていることを確認
2. **依存関係**: 既存の`requirements.txt`の依存関係がインストールされていることを確認
3. **新しいメインファイルで起動**: `python main.py`を実行
4. **機能テスト**: 各コマンドが正常に動作することを確認

### 元のファイルに戻す場合

新しい構造に問題がある場合は、元のファイル（`discord_bot_old.py`）を使用できます：

```bash
python discord_bot_old.py
```

## 📈 今後の拡張予定

- **データベース連携**: プレイリストの永続化
- **ウェブインターフェース**: 管理画面の追加
- **プラグインシステム**: サードパーティ拡張の対応
- **テストカバレッジ**: 単体テストの追加

## 📄 ライセンス

このプロジェクトはMITライセンスの下で公開されています。

## 🙏 謝辞

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - YouTubeダウンロードエンジン
- [discord.py](https://github.com/Rapptz/discord.py) - Discord APIライブラリ
- [FFmpeg](https://ffmpeg.org/) - 動画・音声処理

---

**⚠️ 免責事項**: このボットは教育目的で作成されています。著作権法を遵守してご利用ください。
