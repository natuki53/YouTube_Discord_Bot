# Discord Music Room

「立体音響」では、聴き手を中心に仮想スピーカーをドラッグし、前後左右・高さ・距離を再生中の音に反映できる。同じVCの全員へ共通のバイノーラル音声を出力する。ヘッドホン推奨。初期設定はオフ。操作・音声処理・権限確認・データ出典は [立体音響の説明](spatial-audio.md) を参照。

Intel機のDocker Composeで、Botとaiohttp APIを同一プロセス・1インスタンスで起動する。yt-dlpによる検索・先読み・ファイル変換は別のワーカープロセスへ分離し、音声送信スレッドとPythonのGILやプラグイン初期化を共有しない。検索2・ストリーム3・ダウンロード2の上限と待ち件数の上限を設け、LinuxではワーカーのCPU優先度を下げる。Reactのビルド成果物も同じHTTPサーバーから配信する。音声の出力先はDiscordのVC。

## 利用方法

1. Discordでログインし、Botと自分が参加しているサーバーを選択する。
2. サーバー管理者は歯車から再生通知・ダウンロードファイルの送信先を設定する。利用者とBotの両方に閲覧・送信権限、Botには埋め込みリンク権限が必要。ファイル送信には添付権限も必要。
3. DiscordでVCに参加して操作する。Botが接続中なら同じVCへの参加が必要。
4. 曲名・動画URLで追加する。再生リストURLは「再生リストを確認」から曲数を指定して確定する。確認だけでは追加しない。
5. キュー左端のハンドルをドラッグして再生順を変更する。キーボードではSpaceでつかみ、上下キーで移動し、Spaceで確定・Escapeで取消。「…」から個別削除・次に再生を選べる。
6. 再生バーに現在位置と曲の長さを表示する。ドラッグまたは矢印キーでシークし、操作中・保存中はポーリングで位置を戻さない。曲が切り替わった場合は固有IDを検証して古いシークを拒否する。キュー・ループ・音量・一時停止状態を維持し、再生通知は重複送信しない。

進捗は音声フレーム数をもとに計算し、ブラウザでは更新間を補間する。HLSはFFmpegの入力シークを使用する。Range制約のある直接音声では、シーク時だけコンテナ内の127.0.0.1に使い捨てのHTTP入力を開き、FFmpegの任意オフセット要求を上限付きのYouTube Rangeリクエストへ変換する。ホストへのポート公開や音声全体の事前保存は行わず、切替時に閉じる。ライブ・長さ未確定の音声はシークを無効化する。

タイトルは1行の高さを保ち、はみ出す場合だけ自動で横スクロールする。OSで動きを減らす設定が有効な場合は省略表示する。キューにも動画サムネイルを表示する。ドラッグ中・保存中のキューと音量は定期更新で上書きしない。削除・移動は曲ごとの固有IDと移動先IDを検証し、すでに再生・削除された曲の代わりに別の曲を操作しない。

再生中に手動キューの先頭3曲の音声URLを並行して準備し、切替ごとに補充する。順番を変えても準備済みの曲は再利用する。音声URLの有効期限を考慮し、準備から5分以上経過した場合は再取得する。全曲の音声ファイルをダウンロード・保存する方式ではない。

公開・限定公開のYouTube / YouTube Music再生リストに対応する。先頭50件を調べ、取得できる曲から1〜50曲を順番に追加する。非公開・削除済みなど判別できる動画は除外する。確認内容は本人・サーバー単位で5分間有効。確認後にキューの空きが減った場合、部分追加せずエラーにする。`/play` に再生リストURLを指定した場合は先頭50件を取り込む。ダウンロードは単一動画のみ。

キュー全体の上限は100曲。キューはメモリ管理で、再起動すると消える。音声接続はサーバーにつき1つ。ライト・ダーク・端末設定に従う自動テーマはブラウザごとに保存する。

## 認証・データ

- Discord OAuth2 Authorization Code Grant。スコープは `identify guilds`。所属・ロールはBotのGet Guild Member APIで確認し、OAuthの所属確認APIを定期ポーリングしない。
- OAuth stateはCookieとサーバーの使い捨て値で検証。セッションIDはSQLiteにSHA-256で保存し、OAuthトークンとセッション内容はFernetで暗号化する。
- CookieはSecure / HttpOnly / SameSite=Lax。変更APIは公開オリジンの一致とCSRFトークンを検証する。
- 読み取り時の所属キャッシュは15秒。変更時・検索完了後・ファイル送信前には所属とVCを再確認する。
- 通知先の変更にはDiscordのサーバー管理権限が必要。画面が送った権限値を信用しない。
- 非公開VCを閲覧できないメンバーには、再生中のタイトル・キューも返さない。
- Web操作は1人1件、全体8件まで同時処理。操作IDで二重送信を防ぎ、サーバー単位のロックで操作を直列化する。
- 検索・先読み・ダウンロードは用途別のプロセスプールで実行する。検索が先読みの待ち行列に入らないように分け、タイムアウト・キャンセル後も実行中の処理は件数上限へ含める。
- 検証用の認証バイパスやデモAPIは本番コードに含めない。

SQLiteと暗号鍵の両方がセッション復元に必要。DBはSQLiteのbackup APIなどで一貫したスナップショットを作り、暗号鍵は秘密情報として別途保管する。鍵を失った場合は再ログインが必要。

初期表示は `/api/bootstrap` の1リクエストでログイン情報・サーバー一覧・選択中サーバーの状態を取得する。従来の読み取りAPIと同じ所属・VCの閲覧権限を検証する。ハッシュ付きの公開アセットだけを1年間キャッシュし、HTMLは再検証、認証・個人データのAPIは `no-store` を維持する。キューのドラッグ用コードは必要時に読み込み、操作完了は200〜500ms間隔で確認して定期更新を待たずに表示へ反映する。

HTTP応答の `Server-Timing` でアプリ内処理時間を確認できる。非公開の `data/activity.json` には現在曲の送出フレーム数・40msを超えた読み出し間隔の件数・最大間隔も記録する。一時停止からの復帰時は間隔計測をリセットする。

音声の周期は読み出し側の相対sleepへ依存させず、discord.py 2.7.1の暗号化済みRTPの最終UDP書き込みを包み、20msの期限で制御する。小さなsleepの超過を蓄積させず、符号化・送信待ちで遅れた後もまとめ送りしない。Opus符号化・DAVE・RTPヘッダーはライブラリの処理をそのまま使う。修正配備の引き継ぎファイルは現在位置と一時停止状態にも対応する。

## 本番設定

Discord Developer Portalの対象Botアプリで、OAuth2のRedirect URIに次を登録する。

```text
https://music.mu-natuki.com/auth/callback
```

`.env` に次を設定する。Client SecretとBot Tokenは異なる。

```dotenv
WEB_ENABLED=true
WEB_PUBLIC_URL=https://music.mu-natuki.com
DISCORD_CLIENT_ID=<対象BotのApplication ID>
DISCORD_CLIENT_SECRET=<OAuth2 Client Secret>
WEB_ENCRYPTION_KEY=<Fernet.generate_key()で生成した鍵>
WEB_DATABASE_PATH=/app/data/web.sqlite3
COMPOSE_PROFILES=web
MUSIC_TUNNEL_ID=<専用TunnelのUUID>
```

暗号鍵は `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` などで生成する。値をコミット・ログ・チャットへ記録しない。`.env` と `deploy/private/music-tunnel.json` はホスト上でモード0600とする。

専用Cloudflare Tunnelのcredential JSONを `deploy/private/music-tunnel.json` に置く。アカウント全体のcert.pemはサーバーへ渡さない。`deploy/cloudflared.yml` はmusic.mu-natuki.comだけをBotの8080番へ転送する。ホストへのポート公開は不要。

```bash
docker compose --profile web config --quiet
docker compose --profile web build youtube-bot
# 現行BotのVC退出と処理終了を確認してから切り替える
docker compose --profile web up -d --no-build
```

DNSは専用TunnelへCNAMEを登録する。ログイン・APIにはキャッシュを適用しない。`/healthz` はDiscord接続時に200、未接続時に503。公開監視用の既存Botハートビートも継続する。

## 更新・切り戻し

GitHubのmainへのpush（PRのマージを含む）を署名検証付きWebhookで受け、BotとWebの両方をビルドする。Webだけの変更では共有アセット用volumeへ新しいファイルを配信し、index.htmlを最後に切り替える。Botの再起動や音声再生の中断は行わない。古いハッシュ付きアセットは開いたままのタブのために残す。

BotやAPIにも変更がある場合は、現在の再生・変換が終わってからコンテナを更新する。配備前にフロントエンドのビルドとLinuxのBotテスト、配備後にDiscord接続とWeb healthを確認する。秘密情報とサーバー設定はGitに含めない。配備用コンテナにはチェックアウトをホストと同じ絶対パスでマウントし、Tunnel設定のbind mount先も一致させる。

discord.py 2.7.1とdavey 0.1.7を組で固定する。davey 0.2以降への更新は、呼び出し側の鍵遷移API対応と実音声確認を伴う変更として扱う。

配備前に現行イメージ・Compose・`.env`・DBのバックアップを残す。サーバーに未コミット変更がある場合は比較・保全し、`git reset --hard` で失わないようにする。通常の自動配備スクリプトも未保存変更があれば停止する。

自動配備はボイス接続・FFmpeg・Web処理の終了を待つ。`data/activity.json` は更新用の非公開情報で、公開ステータスには含めない。起動失敗時は直前のイメージへ戻す。初回GUI公開前のイメージへ戻す際はWEB_ENABLEDをfalse、COMPOSE_PROFILESを空にして、元のComposeとイメージで起動する。SQLiteの初期スキーマは既存Botのファイルを変更しない。

## 検証

```bash
python -m unittest discover -s tests -q
cd web
npm ci
npm run build
npx playwright install chromium
npm test -- --workers=2
```

テストはDiscord送信・実音声再生を行わない。画面テストではAPIをモックし、PC・スマートフォン、テーマ保存、サーバー切り替え、再生リストの件数確認を検証する。本番のOAuthログインと実VC再生は別途確認する。
