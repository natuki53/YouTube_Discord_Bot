# Discord Music Room

Intel機のDocker Composeで、Botとaiohttp APIを同一プロセス・1インスタンスで起動する。Reactのビルド成果物も同じHTTPサーバーから配信する。音声の出力先はDiscordのVC。

## 利用方法

1. Discordでログインし、Botと自分が参加しているサーバーを選択する。
2. サーバー管理者は歯車から再生通知・ダウンロードファイルの送信先を設定する。利用者とBotの両方に閲覧・送信権限、Botには埋め込みリンク権限が必要。ファイル送信には添付権限も必要。
3. DiscordでVCに参加して操作する。Botが接続中なら同じVCへの参加が必要。
4. 曲名・動画URLで追加する。再生リストURLは「再生リストを確認」から曲数を指定して確定する。確認だけでは追加しない。
5. キュー左端のハンドルをドラッグして再生順を変更する。キーボードではSpaceでつかみ、上下キーで移動し、Spaceで確定・Escapeで取消。「…」から個別削除・次に再生を選べる。

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
- 検索は専用スレッドプールで実行し、音声のイベントループをブロックしない。
- 検証用の認証バイパスやデモAPIは本番コードに含めない。

SQLiteと暗号鍵の両方がセッション復元に必要。DBはSQLiteのbackup APIなどで一貫したスナップショットを作り、暗号鍵は秘密情報として別途保管する。鍵を失った場合は再ログインが必要。

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
