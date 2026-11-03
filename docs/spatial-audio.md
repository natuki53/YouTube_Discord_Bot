# 立体音響

Webの「立体音響」をオンにすると、音楽全体を1つの仮想スピーカーとして再生する。中央の聴き手に対し、スピーカーを前後左右へドラッグして方向と距離を変える。高さはスライダー、位置は矢印キー（Shiftで大きく移動）でも変更できる。正面・左右・後方のプリセットとリセットを用意する。配置図は折りたためる。

出力はDiscord VCの全員に共通のバイノーラル音声。ヘッドホンを推奨し、個人の頭部形状によって方向感の強さは異なる。VC参加者別の位置やヘッドトラッキングは扱わない。オフ時は元のステレオ音声をそのまま返す。オン時は左右の音を1音源にまとめ、測定済みHRTFによる周波数特性・耳間の遅延・距離減衰を適用する。

処理は48 kHz・16 bit・ステレオの20 msフレームのままで、サンプル数と再生速度を変えない。SOFA読み込みとフィルター取得は制御側のワーカースレッドに分離し、音声スレッドではNumPyのFIR畳み込みと履歴管理のみを行う。位置変更とオン・オフは100 msで補間する。FFmpegの再起動、YouTubeの再取得、キューの変更は不要。曲の切り替え・シークでも設定を引き継ぎ、停止して退出した場合はオフに戻る。

GUIは即座に動かし、送信は120 ms間隔で最新位置へまとめる。1リクエストずつ処理し、中間の古い位置を蓄積しない。ドラッグ中・保存中・保存より前に始まったポーリングで表示を巻き戻さない。実際に耳へ届くまでにはDiscordのネットワーク・受信バッファーの遅延が加わる。

`PUT /api/guilds/{guild_id}/spatial` は `{enabled, x, y, z}` を受ける。xは右、yは前、zは上（m）。x/yは−4〜4、zは−2〜2で、非有限値・真偽値の座標などは拒否する。セッション・CSRF・Originを毎回検証し、同じVC・VC権限も毎回検証する。連続操作は最大2秒の短い所属・ロール確認キャッシュを使い、ポインター移動ごとにDiscord RESTを叩かない。キャッシュの期限後は必ず所属を再取得する。ログアウトやVC移動は期限を待たず拒否する。

Linuxでは `libmysofa1` と `/usr/share/libmysofa/default.sofa` を使用する（DockerとCIで明示的に導入）。データがない環境は立体音響の利用不可を表示し、通常再生は継続する。SOFAデータの任意アップロードや外部URLの読込は提供しない。

使用データは **Bill Gardner and Keith Martin, MIT Media Lab Machine Listening Group (1994), KEMAR normal pinna HRTF measurements**。MIT Media Laboratoryのデータは著者の明記を条件に利用できる。libmysofaはBSD-3-Clause、データとライセンスはOSパッケージに含む。

資料: [libmysofaのAPI](https://github.com/hoene/libmysofa#usage)、[Discordの音声仕様](https://github.com/discord/discord-api-docs/blob/main/developers/topics/voice-connections.mdx)。
