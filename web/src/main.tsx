import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { createRoot } from "react-dom/client";
import {
  Music2,
  Headphones,
  ArrowUpRight,
  LogOut,
  Play,
  Pause,
  SkipForward,
  Square,
  Repeat2,
  Sparkles,
  Volume2,
  Plus,
  ListMusic,
  Download,
  Radio,
  Settings2,
  Check,
  LoaderCircle,
  Trash2,
  ChevronDown,
  X,
  Sun,
  Moon,
  Monitor,
} from "lucide-react";
import "./style.css";

type Guild = { id: string; name: string; icon: string | null };
type User = { id: string; username: string; global_name: string | null };
type Track = {
  title: string;
  url: string;
  requester: string;
  video_id: string | null;
  auto_selected: boolean;
};
type PlaylistPreview = {
  id: string;
  query: string;
  title: string;
  maximum: number;
  available: number;
  skipped: number;
  truncated: boolean;
  tracks: string[];
};
type Job = {
  id: string;
  status: "running" | "done" | "error";
  message: string;
  action: string;
  preview?: PlaylistPreview;
};
type State = {
  guild: Guild;
  current: Track | null;
  queue: Track[];
  loop: boolean;
  autoplay: boolean;
  volume: number;
  voice_channel: string | null;
  paused: boolean;
  connected: boolean;
  can_control: boolean;
  control_reason: string;
  can_manage: boolean;
  notification_channel_id: string | null;
  channels: { id: string; name: string }[];
  jobs: Job[];
};
class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
let csrf = "";
async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrf,
      ...init.headers,
    },
  });
  const body = await response.json();
  if (!response.ok)
    throw new ApiError(
      body.error || "接続を確認してください。",
      response.status,
    );
  return body;
}
function App() {
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem("music-theme") || "system";
    } catch {
      return "system";
    }
  });
  useEffect(() => {
    const media = matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const resolved =
        theme === "system" ? (media.matches ? "dark" : "light") : theme;
      document.documentElement.dataset.theme = resolved;
      document.documentElement.style.colorScheme = resolved;
      document
        .querySelector('meta[name="theme-color"]')
        ?.setAttribute("content", resolved === "dark" ? "#101314" : "#f5f6f2");
    };
    apply();
    try {
      localStorage.setItem("music-theme", theme);
    } catch {}
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);
  const [user, setUser] = useState<User | null>(null),
    [loading, setLoading] = useState(true),
    [guilds, setGuilds] = useState<Guild[]>([]),
    [guildId, setGuildId] = useState("");
  const [state, setState] = useState<State | null>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  const [query, setQuery] = useState(""),
    [volume, setVolume] = useState(25),
    [tab, setTab] = useState<"queue" | "download">("queue"),
    [settings, setSettings] = useState(false);
  const [channel, setChannel] = useState(""),
    [downloadUrl, setDownloadUrl] = useState(""),
    [quality, setQuality] = useState("480p"),
    [format, setFormat] = useState("video");
  const [preview, setPreview] = useState<PlaylistPreview | null>(null),
    [importCount, setImportCount] = useState(50);
  const previewDialog = useRef<HTMLDialogElement>(null),
    pendingPreview = useRef<string | null>(null);
  useEffect(() => {
    if (preview) previewDialog.current?.showModal();
    else previewDialog.current?.close();
  }, [preview]);
  const epoch = useRef(0),
    currentGuild = useRef(""),
    seenJobs = useRef(new Set<string>()),
    timer = useRef<number | null>(null);
  async function fail(e: unknown) {
    if (e instanceof ApiError && e.status === 401) {
      setUser(null);
      setState(null);
      setGuilds([]);
    }
    setError(e instanceof Error ? e.message : "処理に失敗しました。");
  }
  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const me = await api<{ user: User; csrf: string }>("/api/me");
        if (!live) return;
        csrf = me.csrf;
        setUser(me.user);
        const list = await api<{ guilds: Guild[] }>("/api/guilds");
        if (!live) return;
        setGuilds(list.guilds);
        const stored = localStorage.getItem("music-guild");
        setGuildId(
          list.guilds.some((g) => g.id === stored)
            ? stored!
            : list.guilds[0]?.id || "",
        );
      } catch (e) {
        if (live && !(e instanceof ApiError && e.status === 401)) void fail(e);
      } finally {
        if (live) setLoading(false);
      }
    })();
    return () => {
      live = false;
    };
  }, []);
  useEffect(() => {
    const version = ++epoch.current;
    currentGuild.current = guildId;
    setState(null);
    setError("");
    setNotice("");
    setBusy(false);
    setPreview(null);
    pendingPreview.current = null;
    if (!guildId || !user) return;
    localStorage.setItem("music-guild", guildId);
    let live = true;
    async function poll() {
      try {
        const next = await api<State>(`/api/guilds/${guildId}/state`);
        if (!live || epoch.current !== version) return;
        setState(next);
        setVolume(next.volume);
        setError("");
        setBusy(next.jobs.some((j) => j.status === "running"));
        for (const j of next.jobs)
          if (j.status !== "running" && !seenJobs.current.has(j.id)) {
            seenJobs.current.add(j.id);
            if (j.status === "error") setError(j.message);
            else {
              setNotice(j.message);
              if (j.preview && pendingPreview.current === j.id) {
                setPreview(j.preview);
                setImportCount(Math.min(50, j.preview.maximum));
                pendingPreview.current = null;
              }
            }
          }
      } catch (e) {
        if (live && epoch.current === version) {
          setState(null);
          void fail(e);
        }
      } finally {
        if (live)
          timer.current = window.setTimeout(
            () => void poll(),
            document.hidden ? 10000 : 2500,
          );
      }
    }
    void poll();
    return () => {
      live = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [guildId, user]);
  useEffect(
    () => setChannel(state?.notification_channel_id || ""),
    [state?.notification_channel_id, guildId],
  );
  async function action(
    name: string,
    value?: number | boolean,
    extra: { query?: string; preview_id?: string; count?: number } = {},
  ) {
    const target = guildId;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const job = await api<Job>(`/api/guilds/${target}/actions`, {
        method: "POST",
        headers: { "X-Request-ID": crypto.randomUUID() },
        body: JSON.stringify({
          action: name,
          value,
          query:
            name === "play" || name === "playlist_preview"
              ? query
              : downloadUrl,
          quality,
          ...extra,
        }),
      });
      if (currentGuild.current !== target) return;
      setNotice(job.message);
      if (name === "playlist_preview") pendingPreview.current = job.id;
      if (name === "play") {
        setQuery("");
        setPreview(null);
      }
    } catch (e) {
      if (currentGuild.current === target) {
        setBusy(false);
        void fail(e);
      }
    }
  }
  async function saveSettings(event: FormEvent) {
    event.preventDefault();
    try {
      await api(`/api/guilds/${guildId}/settings`, {
        method: "PUT",
        body: JSON.stringify({ channel_id: channel }),
      });
      setSettings(false);
      setNotice("通知先チャンネルを保存しました。");
    } catch (e) {
      void fail(e);
    }
  }
  const disabled = busy || !state?.can_control;
  function button(label: string, icon: ReactNode, name: string, extra = false) {
    return (
      <button
        className={`icon-button ${extra ? "active" : ""}`}
        title={label}
        aria-label={label}
        aria-pressed={
          name === "loop" || name === "autoplay" ? extra : undefined
        }
        disabled={disabled || !state?.voice_channel}
        onClick={() =>
          void action(
            name,
            name === "loop"
              ? !state?.loop
              : name === "autoplay"
                ? !state?.autoplay
                : undefined,
          )
        }
      >
        {icon}
      </button>
    );
  }
  return (
    <div className="app-shell">
      <header className="header">
        <a className="brand" href="/" aria-label="Music Room ホーム">
          <span className="brand-icon">
            <Music2 size={22} />
          </span>
          <span>
            MUSIC<span className="brand-light"> ROOM</span>
          </span>
          <span className="beta">BETA</span>
        </a>
        <div className="header-right">
          <span className="desktop-tag">A little music. A little closer.</span>
          <label className="theme-select">
            {theme === "light" ? (
              <Sun size={16} />
            ) : theme === "dark" ? (
              <Moon size={16} />
            ) : (
              <Monitor size={16} />
            )}
            <select
              aria-label="表示テーマ"
              value={theme}
              onChange={(e) => setTheme(e.target.value)}
            >
              <option value="system">自動</option>
              <option value="light">ライト</option>
              <option value="dark">ダーク</option>
            </select>
          </label>
          {user && (
            <>
              <span className="user-name">
                {user.global_name || user.username}
              </span>
              <button
                className="icon-button"
                aria-label="ログアウト"
                onClick={() =>
                  void api("/auth/logout", { method: "POST" })
                    .then(() => {
                      setUser(null);
                      setState(null);
                      setGuilds([]);
                    })
                    .catch(fail)
                }
              >
                <LogOut size={18} />
              </button>
            </>
          )}
        </div>
      </header>
      {loading ? (
        <main className="loading" role="status">
          <LoaderCircle className="spin" />
          読み込んでいます…
        </main>
      ) : !user ? (
        <main className="login-layout">
          <div className="login-copy">
            <span className="eyebrow">
              <span className="dot" /> YOUR SERVER. YOUR SOUND.
            </span>
            <h1>
              いつものVCに、
              <br />
              好きな音楽を。
            </h1>
            <p>
              聴きたい一曲を、みんなで。
              <br />
              Discordの音楽を、手元から気軽にコントロール。
            </p>
            <a className="primary login-button" href="/auth/login">
              <Headphones size={20} />
              Discordでログイン
              <ArrowUpRight size={18} />
            </a>
            <p className="fine-print">
              Botが参加しているサーバーのメンバーが利用できます。
            </p>
            {error && (
              <div className="alert" role="alert">
                {error}
              </div>
            )}
          </div>
          <div className="record-art" aria-hidden="true">
            <div className="record">
              <div className="record-label">
                <Music2 size={34} />
                <span>MUSIC ROOM</span>
              </div>
            </div>
            <span className="record-caption">GOOD COMPANY. GREAT MUSIC.</span>
            <div className="waveform">
              {Array.from({ length: 36 }, (_, i) => (
                <i key={i} />
              ))}
            </div>
          </div>
        </main>
      ) : (
        <main className="dashboard">
          <div className="page-heading">
            <div>
              <span className="eyebrow">YOUR LISTENING SPACE</span>
              <h1>今日も、いい音楽を。</h1>
              <p>サーバーを選んで、みんなのプレイリストへ。</p>
            </div>
            <label className="guild-select">
              <span>DISCORD SERVER</span>
              <div>
                <select
                  aria-label="Discordサーバー"
                  value={guildId}
                  onChange={(e) => {
                    setGuildId(e.target.value);
                    setSettings(false);
                  }}
                >
                  {guilds.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name}
                    </option>
                  ))}
                </select>
                <ChevronDown size={17} />
              </div>
            </label>
          </div>
          {error && (
            <div className="alert" role="alert">
              {error}
              <button aria-label="エラーを閉じる" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {notice && (
            <div className="notice" role="status">
              {busy ? (
                <LoaderCircle size={16} className="spin" />
              ) : (
                <Check size={16} />
              )}{" "}
              {notice}
            </div>
          )}
          {!guilds.length ? (
            <div className="empty-server">
              <Headphones size={32} />
              <h2>利用できるサーバーがありません</h2>
              <p>
                Botが導入されているDiscordサーバーに参加してから、ページを開き直してください。
              </p>
            </div>
          ) : !state ? (
            <div className="loading" role="status">
              <LoaderCircle className="spin" />
              サーバーの状態を取得しています…
            </div>
          ) : (
            <>
              <div className="main-grid">
                <section className="now-playing panel">
                  <div className="panel-top">
                    <span className="eyebrow">NOW PLAYING</span>
                    <span className="live">
                      <span className="dot" />
                      {state.voice_channel
                        ? `接続中 · ${state.voice_channel}`
                        : "再生待機中"}
                    </span>
                  </div>
                  <div className="track-display">
                    <div className="cover">
                      {state.current?.video_id &&
                      /^[\w-]{11}$/.test(state.current.video_id) ? (
                        <img
                          src={`https://i.ytimg.com/vi/${state.current.video_id}/hqdefault.jpg`}
                          alt="再生中の動画サムネイル"
                        />
                      ) : (
                        <div className="cover-placeholder">
                          <div className="mini-record">
                            <Music2 size={26} />
                          </div>
                        </div>
                      )}
                      <span className="cover-mark">
                        <Headphones size={14} />
                      </span>
                    </div>
                    <div className="track-info">
                      <span className="small-label">
                        {state.paused
                          ? "PAUSED"
                          : state.current
                            ? "ON AIR"
                            : "READY WHEN YOU ARE"}
                      </span>
                      <h2>
                        {state.current?.title || "次の一曲は、あなたから。"}
                      </h2>
                      <p>
                        {state.current
                          ? `リクエスト: ${state.current.requester}`
                          : "曲名やYouTube URLから音楽を追加しましょう。"}
                      </p>
                      {state.current && (
                        <a
                          href={safeYoutube(state.current.url)}
                          target="_blank"
                          rel="noreferrer"
                        >
                          YouTubeで開く
                          <ArrowUpRight size={13} />
                        </a>
                      )}
                    </div>
                  </div>
                  <div className="player-controls">
                    <div className="transport">
                      {button(
                        "ループ",
                        <Repeat2 size={19} />,
                        "loop",
                        state.loop,
                      )}
                      <button
                        className="play-button"
                        aria-label={state.paused ? "再開" : "一時停止"}
                        disabled={disabled || !state.current}
                        onClick={() =>
                          void action(state.paused ? "resume" : "pause")
                        }
                      >
                        {state.paused ? (
                          <Play size={22} fill="currentColor" />
                        ) : (
                          <Pause size={22} fill="currentColor" />
                        )}
                      </button>
                      {button("スキップ", <SkipForward size={22} />, "skip")}
                      {button("停止して退出", <Square size={17} />, "stop")}
                    </div>
                    <div className="volume">
                      <Volume2 size={18} />
                      <input
                        aria-label="音量"
                        type="range"
                        min="1"
                        max="100"
                        value={volume}
                        disabled={disabled || !state.voice_channel}
                        onChange={(e) => setVolume(Number(e.target.value))}
                        onPointerUp={() => void action("volume", volume)}
                        onKeyUp={(e) => {
                          if (
                            ["ArrowLeft", "ArrowRight", "Home", "End"].includes(
                              e.key,
                            )
                          )
                            void action("volume", volume);
                        }}
                      />
                      <span>{volume}%</span>
                    </div>
                  </div>
                  <div className="player-footer">
                    <span>
                      <Radio size={15} />
                      {state.connected
                        ? "Discordに接続済み"
                        : "Discordに再接続しています"}
                    </span>
                    <button
                      className={`autoplay ${state.autoplay ? "enabled" : ""}`}
                      disabled={disabled || !state.voice_channel}
                      aria-pressed={state.autoplay}
                      onClick={() => void action("autoplay", !state.autoplay)}
                    >
                      <Sparkles size={15} />
                      自動選曲
                      <span className="toggle">
                        <i />
                      </span>
                    </button>
                  </div>
                </section>
                <section className="request-panel panel">
                  <span className="eyebrow">MAKE IT YOURS</span>
                  <h2>聴きたい曲を、追加。</h2>
                  <p>曲名・動画URL・再生リストURLから追加。</p>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      void action(
                        isPlaylist(query) ? "playlist_preview" : "play",
                      );
                    }}
                  >
                    <label htmlFor="query">
                      曲名・YouTube URL（再生リスト対応）
                    </label>
                    <div className="query-field">
                      <Music2 size={18} />
                      <input
                        id="query"
                        maxLength={500}
                        placeholder="曲名、動画・再生リストのURL"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        disabled={busy}
                      />
                    </div>
                    <button
                      className="primary add-button"
                      disabled={
                        disabled ||
                        !query.trim() ||
                        !state.notification_channel_id
                      }
                    >
                      {busy ? (
                        <LoaderCircle size={18} className="spin" />
                      ) : (
                        <Plus size={18} />
                      )}
                      {isPlaylist(query) ? "再生リストを確認" : "キューに追加"}
                    </button>
                    {isPlaylist(query) && (
                      <p className="playlist-detected">
                        再生リストを検知しました。曲数を確認してから追加します。
                      </p>
                    )}
                  </form>
                  <div className="request-hint">
                    <Headphones size={17} />
                    <span>
                      {!state.can_control
                        ? state.control_reason
                        : !state.notification_channel_id
                          ? "サーバー管理者に通知先チャンネルを設定してもらってください。"
                          : "Botと同じVCで、みんなと一緒に楽しめます。"}
                    </span>
                  </div>
                </section>
              </div>
              <section className="queue-panel panel">
                <div className="queue-header">
                  <div className="tabs">
                    <button
                      className={tab === "queue" ? "selected" : ""}
                      onClick={() => setTab("queue")}
                    >
                      <ListMusic size={18} />
                      再生キュー
                      <span className="count">{state.queue.length}</span>
                    </button>
                    <button
                      className={tab === "download" ? "selected" : ""}
                      onClick={() => setTab("download")}
                    >
                      <Download size={17} />
                      ダウンロード
                    </button>
                  </div>
                  <div className="queue-tools">
                    {tab === "queue" && (
                      <button
                        className="text-button"
                        disabled={disabled || !state.queue.length}
                        onClick={() => {
                          if (
                            window.confirm("待機中の曲をすべて消去しますか？")
                          )
                            void action("clear");
                        }}
                      >
                        <Trash2 size={14} />
                        キューを消去
                      </button>
                    )}
                    {state.can_manage && (
                      <button
                        className="icon-button"
                        aria-label="サーバー設定"
                        onClick={() => setSettings(!settings)}
                      >
                        <Settings2 size={18} />
                      </button>
                    )}
                  </div>
                </div>
                {settings && (
                  <form className="settings" onSubmit={saveSettings}>
                    <label htmlFor="channel">再生通知・ファイルの送信先</label>
                    <select
                      id="channel"
                      value={channel}
                      onChange={(e) => setChannel(e.target.value)}
                    >
                      <option value="">チャンネルを選択</option>
                      {state.channels.map((c) => (
                        <option key={c.id} value={c.id}>
                          # {c.name}
                        </option>
                      ))}
                    </select>
                    <button className="primary" disabled={!channel}>
                      保存
                    </button>
                  </form>
                )}
                {tab === "queue" ? (
                  state.queue.length ? (
                    <>
                      <div className="queue-labels">
                        <span>#</span>
                        <span>TRACK</span>
                        <span>REQUESTED BY</span>
                        <span />
                      </div>
                      <ol className="queue-list">
                        {state.queue.map((t, i) => (
                          <li key={`${t.url}-${i}`}>
                            <span className="track-number">
                              {String(i + 1).padStart(2, "0")}
                            </span>
                            <div className="queue-track">
                              <span className="queue-note">
                                <Music2 size={17} />
                              </span>
                              <div>
                                <a
                                  href={safeYoutube(t.url)}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  {t.title}
                                </a>
                                <small>
                                  {t.auto_selected ? "自動選曲" : "YouTube"}
                                </small>
                              </div>
                            </div>
                            <span className="requester">{t.requester}</span>
                            <ArrowUpRight size={16} />
                          </li>
                        ))}
                      </ol>
                    </>
                  ) : (
                    <div className="empty-queue">
                      <ListMusic size={30} />
                      <h3>プレイリストは、ここから。</h3>
                      <p>お気に入りの曲を追加して、VCの時間を彩りましょう。</p>
                    </div>
                  )
                ) : (
                  <form
                    className="download-form"
                    onSubmit={(e) => {
                      e.preventDefault();
                      void action(
                        format === "mp3" ? "download_mp3" : "download",
                      );
                    }}
                  >
                    <div>
                      <h3>動画・音声をDiscordへ</h3>
                      <p>
                        変換したファイルを、設定済みの通知先チャンネルに送ります。
                      </p>
                    </div>
                    <label>
                      YouTube動画のURL
                      <input
                        type="url"
                        required
                        maxLength={500}
                        placeholder="https://www.youtube.com/watch?v=…"
                        value={downloadUrl}
                        onChange={(e) => setDownloadUrl(e.target.value)}
                      />
                    </label>
                    <div className="download-options">
                      <label>
                        形式
                        <select
                          value={format}
                          onChange={(e) => setFormat(e.target.value)}
                        >
                          <option value="video">動画 MP4</option>
                          <option value="mp3">音声 MP3</option>
                        </select>
                      </label>
                      {format === "video" && (
                        <label>
                          画質
                          <select
                            value={quality}
                            onChange={(e) => setQuality(e.target.value)}
                          >
                            {[
                              "144p",
                              "240p",
                              "360p",
                              "480p",
                              "720p",
                              "1080p",
                            ].map((q) => (
                              <option key={q}>{q}</option>
                            ))}
                          </select>
                        </label>
                      )}
                      <button
                        className="primary"
                        disabled={
                          disabled ||
                          !state.notification_channel_id ||
                          !downloadUrl
                        }
                      >
                        <Download size={16} />
                        変換して送信
                      </button>
                    </div>
                  </form>
                )}
              </section>
            </>
          )}
        </main>
      )}
      <dialog
        className="playlist-dialog"
        ref={previewDialog}
        onCancel={() => setPreview(null)}
        aria-labelledby="playlist-title"
      >
        {preview && (
          <>
            <div className="dialog-heading">
              <span className="eyebrow">PLAYLIST IMPORT</span>
              <button
                className="icon-button"
                aria-label="取り込みをキャンセル"
                onClick={() => setPreview(null)}
              >
                <X size={18} />
              </button>
            </div>
            <h2 id="playlist-title">再生リストを取り込む</h2>
            <p className="playlist-name">{preview.title}</p>
            <p>先頭から取り込む曲数を選んでください。1回の上限は50曲です。</p>
            {preview.truncated && (
              <p className="playlist-detail">
                このリストは51件以上あります。先頭50件を確認しています。
              </p>
            )}
            {preview.skipped > 0 && (
              <p className="playlist-detail">
                非公開・削除済みなど、取得できない{preview.skipped}
                件を除外しました。
              </p>
            )}
            <ol className="preview-tracks">
              {preview.tracks.map((title, i) => (
                <li key={i}>{title}</li>
              ))}
            </ol>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void action("play", undefined, {
                  query: preview.query,
                  preview_id: preview.id,
                  count: importCount,
                });
              }}
            >
              <label htmlFor="import-count">
                取り込む曲数 <span>最大 {preview.maximum} 曲</span>
              </label>
              <input
                id="import-count"
                type="number"
                min={1}
                max={preview.maximum}
                required
                value={Number.isNaN(importCount) ? "" : importCount}
                onChange={(e) => setImportCount(e.target.valueAsNumber)}
              />
              <div className="dialog-actions">
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setPreview(null)}
                >
                  キャンセル
                </button>
                <button
                  className="primary"
                  disabled={
                    busy ||
                    !Number.isInteger(importCount) ||
                    importCount < 1 ||
                    importCount > preview.maximum
                  }
                >
                  <Plus size={17} />
                  {Number.isNaN(importCount) ? 0 : importCount}曲を取り込む
                </button>
              </div>
            </form>
          </>
        )}
      </dialog>
      <footer className="footer">
        <span>
          <Music2 size={13} />
          MUSIC ROOM
        </span>
        <p>音楽があると、いつもの時間がちょっといい。</p>
        <span>POWERED BY DISCORD</span>
      </footer>
    </div>
  );
}
function safeYoutube(url: string) {
  try {
    const u = new URL(url);
    return u.protocol === "https:" &&
      ["youtube.com", "www.youtube.com", "youtu.be"].includes(u.hostname)
      ? u.href
      : "#";
  } catch {
    return "#";
  }
}
function isPlaylist(value: string) {
  try {
    const u = new URL(value.includes("://") ? value : `https://${value}`);
    return (
      [
        "youtube.com",
        "www.youtube.com",
        "music.youtube.com",
        "m.youtube.com",
        "youtu.be",
      ].includes(u.hostname) && !!u.searchParams.get("list")
    );
  } catch {
    return false;
  }
}
createRoot(document.getElementById("root")!).render(<App />);
