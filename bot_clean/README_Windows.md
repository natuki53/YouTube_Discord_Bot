# 🤖 YouTube Discord Bot - Windows セットアップガイド

WindowsでYouTube Discord Botを実行するための詳細なセットアップガイドです。

## 🔧 事前準備

### 1. Python のインストール

1. [Python公式サイト](https://www.python.org/downloads/)から最新版をダウンロード
2. インストール時に **「Add Python to PATH」にチェック** を入れる
3. インストール完了後、コマンドプロンプトで確認：
   ```cmd
   python --version
   ```

### 2. FFmpeg のインストール (音声再生用)

#### 方法1: Chocolatey使用 (推奨)
```cmd
# Chocolateyをインストール (管理者権限のPowerShellで実行)
Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# FFmpegをインストール
choco install ffmpeg
```

#### 方法2: 手動インストール
1. [FFmpeg公式サイト](https://ffmpeg.org/download.html)からWindows版をダウンロード
2. 適当な場所に解凍 (例: `C:\ffmpeg\`)
3. 環境変数PATHに `C:\ffmpeg\bin` を追加
4. コマンドプロンプトで確認：
   ```cmd
   ffmpeg -version
   ```

## 🚀 ボットのセットアップ

### 自動セットアップ (推奨)

1. `setup_windows.bat` をダブルクリックで実行
2. 画面の指示に従ってセットアップを完了
3. Discord トークンを設定
4. `start_bot.bat` でボットを起動

### 手動セットアップ

#### 1. 依存関係のインストール
```cmd
# コマンドプロンプトでbot_cleanフォルダに移動
cd path\to\YouTube_Discord_Bot\bot_clean

# Windows用の依存関係をインストール
python -m pip install -r requirements_windows.txt
```

#### 2. 設定ファイルの作成
```cmd
# 設定ファイルをコピー
copy config_example.py config.py

# config.pyをメモ帳で編集
notepad config.py
```

#### 3. Discord トークンの設定
`config.py` を開いて以下の行を編集：
```python
DISCORD_TOKEN = 'your_actual_bot_token_here'  # ← ここに実際のトークンを設定
```

#### 4. ボットの起動
```cmd
python main.py
```

## 🤖 Discord Bot の作成

1. [Discord Developer Portal](https://discord.com/developers/applications)にアクセス
2. "New Application" をクリック
3. アプリケーション名を入力 (例: "YouTube Bot")
4. "Bot" タブに移動
5. "Add Bot" をクリック
6. **重要**: "Privileged Gateway Intents" で以下を有効化：
   - ✅ Message Content Intent
7. "Token" セクションで "Copy" をクリックしてトークンをコピー
8. `config.py` の `DISCORD_TOKEN` に貼り付け

## 📂 ファイル構成

```
bot_clean/
├── main.py                    # メイン実行ファイル
├── config.py                  # 設定ファイル (要作成)
├── config_example.py          # 設定ファイルのサンプル
├── requirements_windows.txt   # Windows用依存関係
├── setup_windows.bat         # 自動セットアップスクリプト
├── start_bot.bat             # ボット起動スクリプト
├── README_Windows.md         # このファイル
└── (その他のPythonファイル)
```

## 🎯 使用方法

### 起動方法
- **簡単**: `start_bot.bat` をダブルクリック
- **コマンド**: `python main.py`

### 基本コマンド

#### 🎵 音楽コマンド
- `/play <YouTube URL>` - 音楽を再生
- `/stop` - 再生停止・切断
- `/pause` / `/resume` - 一時停止・再開
- `/skip` - 曲をスキップ
- `/queue` - キューを表示
- `/clear` - キューをクリア
- `/loop` - ループ切り替え

#### 📥 ダウンロードコマンド
- `/download <URL> <画質>` - 動画ダウンロード
- `/download_mp3 <URL>` - MP3変換
- `/quality` - 画質一覧

#### 🔧 一般コマンド
- `/help` - ヘルプ表示
- `/ping` - 応答テスト
- `/info` - ボット情報

## ❗ トラブルシューティング

### Python関連
- **"python is not recognized"**: PATHが正しく設定されていません
  - Pythonを再インストールし、"Add to PATH"にチェック
- **pip install エラー**: 管理者権限でコマンドプロンプトを実行

### Discord関連
- **ボットがオンラインにならない**: トークンが正しく設定されているか確認
- **コマンドが表示されない**: Message Content Intent が有効になっているか確認
- **音声チャンネルに接続できない**: ボットに適切な権限があるか確認

### 音声関連
- **音声が再生されない**: FFmpegがインストールされているか確認
- **ダウンロードできない**: yt-dlpが最新版か確認

### ファイアウォール
Windowsファイアウォールやアンチウイルスソフトがボットをブロックしている可能性があります。
必要に応じて例外設定を追加してください。

## 🔧 設定オプション

`config.py` で以下を調整できます：

```python
# 音声設定
AUDIO_VOLUME = 0.25              # ボリューム (0.0-1.0)
IDLE_TIMEOUT_SECONDS = 300       # 自動切断時間 (秒)

# ファイル設定
DOWNLOAD_DIR = './downloads'      # ダウンロード先
MAX_FILE_SIZE_MB = 25            # 最大ファイルサイズ

# ログ設定
LOG_LEVEL = 'INFO'               # ログレベル (DEBUG/INFO/WARNING/ERROR)
```

## 📱 ボットの招待

1. Discord Developer Portal で "OAuth2" → "URL Generator"
2. **Scopes** で選択:
   - ✅ bot
   - ✅ applications.commands
3. **Bot Permissions** で選択:
   - ✅ Send Messages
   - ✅ Use Slash Commands
   - ✅ Connect
   - ✅ Speak
   - ✅ Attach Files
4. 生成されたURLでボットをサーバーに招待

## 💡 ヒント

- ボットは一度に複数のサーバーで使用可能です
- 音楽の同時再生は1サーバーあたり1チャンネルのみ
- ダウンロードファイルは自動的に削除されます
- ボットを停止する場合は Ctrl+C を押してください

---

問題が発生した場合は、エラーメッセージを確認して適切な対処法を実行してください。
