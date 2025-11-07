# 🤖 YouTube Discord Bot (クリーン版)

YouTube動画の再生とダウンロードが可能なDiscordボットです。元のコードベースを整理・再構築したクリーンなバージョンです。

## ✨ 機能

### 🎵 音楽再生機能
- YouTube音声の高品質再生
- 音楽キュー管理（複数曲の順次再生）
- プレイバック制御（一時停止・再開・スキップ）
- ループ再生機能
- 自動切断（アイドル時）

### 📥 ダウンロード機能
- 動画ダウンロード（144p〜1080p）
- MP3音声変換
- ファイルサイズ制限対応（Discord 25MB制限）
- 自動ファイル管理

### 🎨 ユーザー体験
- モダンなスラッシュコマンド
- 美しいEmbedメッセージ
- 直感的なエラーメッセージ
- 日本語対応

## 🚀 セットアップ

### 1. 必要な依存関係

#### Python 3.9以降
```bash
python --version  # 3.9以降であることを確認
```

#### FFmpeg
**macOS (Homebrew):**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt update && sudo apt install ffmpeg
```

**Windows:**
[FFmpeg公式サイト](https://ffmpeg.org/download.html)からダウンロード

### 2. プロジェクトのセットアップ

```bash
# リポジトリをクローン（または既存のディレクトリに移動）
cd YouTube_Discord_Bot/bot_clean

# 依存関係をインストール
pip install -r requirements.txt
```

### 3. Discord Botの作成

1. [Discord Developer Portal](https://discord.com/developers/applications)にアクセス
2. "New Application" をクリック
3. アプリケーション名を入力
4. "Bot" セクションで "Add Bot" をクリック
5. "Privileged Gateway Intents" で以下を有効化：
   - Message Content Intent
6. Tokenをコピー

### 4. 設定

`config.py` を編集してDiscordトークンを設定：

```python
# Discord Bot設定
DISCORD_TOKEN = 'your_actual_bot_token_here'  # ← ここを変更
```

または環境変数で設定：
```bash
export DISCORD_TOKEN="your_actual_bot_token_here"
```

### 5. ボットの起動

```bash
python main.py
```

## 📖 使用方法

### 🎵 音楽コマンド

| コマンド | 説明 | 使用例 |
|---------|------|--------|
| `/play <URL>` | YouTube音声を再生 | `/play https://youtube.com/watch?v=...` |
| `/stop` | 再生停止・切断 | `/stop` |
| `/pause` | 一時停止 | `/pause` |
| `/resume` | 再生再開 | `/resume` |
| `/skip` | 曲をスキップ | `/skip` |
| `/queue` | キューを表示 | `/queue` |
| `/clear` | キューをクリア | `/clear` |
| `/loop` | ループ切り替え | `/loop` |

### 📥 ダウンロードコマンド

| コマンド | 説明 | 使用例 |
|---------|------|--------|
| `/download <URL> <画質>` | 動画ダウンロード | `/download https://youtube.com/watch?v=... 720p` |
| `/download_mp3 <URL>` | MP3変換ダウンロード | `/download_mp3 https://youtube.com/watch?v=...` |
| `/quality` | 利用可能な画質を表示 | `/quality` |

### 🔧 一般コマンド

| コマンド | 説明 |
|---------|------|
| `/ping` | 応答速度テスト |
| `/help` | コマンド一覧表示 |
| `/info` | ボット情報表示 |

## 🏗️ プロジェクト構造

```
bot_clean/
├── main.py              # メインエントリーポイント
├── config.py            # 設定ファイル
├── requirements.txt     # 依存関係
├── README.md           # このファイル
├── core/               # コア機能
│   ├── youtube_downloader.py  # YouTubeダウンロード
│   └── audio_player.py        # 音声再生
└── commands/           # Discordコマンド
    ├── music_commands.py      # 音楽関連コマンド
    ├── download_commands.py   # ダウンロードコマンド
    └── general_commands.py    # 一般コマンド
```

## ⚙️ 設定オプション

`config.py` で以下の設定を変更できます：

```python
# Discord設定
BOT_PREFIX = '!'                    # プレフィックスコマンド用
AUDIO_VOLUME = 0.25                # 音声ボリューム (0.0-1.0)
IDLE_TIMEOUT_SECONDS = 300         # アイドルタイムアウト（秒）

# ファイル設定
DOWNLOAD_DIR = './downloads'        # ダウンロードディレクトリ
MAX_FILE_SIZE_MB = 25              # 最大ファイルサイズ

# ログ設定
LOG_LEVEL = 'INFO'                 # ログレベル
```

## 🔍 トラブルシューティング

### よくある問題

#### 1. yt-dlpが見つからない
```bash
# yt-dlpをインストール
pip install yt-dlp
```

#### 2. FFmpegが見つからない
- macOS: `brew install ffmpeg`
- Ubuntu: `sudo apt install ffmpeg`
- Windows: FFmpeg公式サイトからダウンロード

#### 3. Discordトークンエラー
- `config.py`でトークンが正しく設定されているか確認
- Discord Developer Portalでボットが正しく作成されているか確認

#### 4. 権限エラー
- Discord Developer Portalで以下を確認：
  - Message Content Intent が有効
  - ボット招待時に適切な権限を付与

#### 5. 音声が再生されない
- ボイスチャンネルに接続してからコマンド実行
- FFmpegが正しくインストールされているか確認

### ログの確認

問題が発生した場合は、ログを確認してください：

```bash
# デバッグモードで実行
# config.pyのLOG_LEVELを'DEBUG'に変更
```

## 🚀 元のボットとの違い

### 改善点

1. **コードの簡潔性**
   - 1000行超のファイルを分割
   - 明確な責任分離
   - 理解しやすい構造

2. **保守性の向上**
   - モジュール化された設計
   - 依存関係の簡素化
   - エラーハンドリングの改善

3. **パフォーマンス**
   - 不要な複雑な機能を除去
   - よりシンプルな非同期処理
   - メモリ使用量の最適化

4. **信頼性**
   - 安定したファイル管理
   - 適切なリソース解放
   - 予期しないエラーの処理

### 削除された機能

- 複雑な競争ダウンロード機能
- 過度に複雑な事前ダウンロード
- 複雑なファイル保護システム

これらの機能は必要に応じて将来再実装可能です。

## 📄 ライセンス

このプロジェクトはMITライセンスの下で公開されています。

## 🙏 謝辞

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - YouTubeダウンロードエンジン
- [discord.py](https://github.com/Rapptz/discord.py) - Discord APIライブラリ
- [FFmpeg](https://ffmpeg.org/) - 動画・音声処理

---

**⚠️ 免責事項**: このボットは教育目的で作成されています。著作権法を遵守してご利用ください。
