import { useEffect, useRef, useState, type FormEvent } from "react";
import { Headphones, LoaderCircle, Plus, Search } from "lucide-react";
import { TrackResults, type SearchTrack } from "./TrackResults";

type Props = {
  busy: boolean;
  canControl: boolean;
  controlReason: string;
  notificationReady: boolean;
  search: (
    query: string,
    signal: AbortSignal,
  ) => Promise<{ results: SearchTrack[] }>;
  add: (url: string) => void;
  previewPlaylist: (url: string) => void;
};

export function TrackRequest({
  busy,
  canControl,
  controlReason,
  notificationReady,
  search,
  add,
  previewPlaylist,
}: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchTrack[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => pending.current?.abort(), []);

  const url = looksLikeUrl(query.trim());
  const playlist = isPlaylist(query.trim());
  const canAdd = canControl && notificationReady && !busy;

  function changeQuery(value: string) {
    pending.current?.abort();
    pending.current = null;
    setSearching(false);
    setResults(null);
    setError("");
    setQuery(value);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = query.trim();
    if (!text || searching) return;
    if (url) {
      if (canAdd) (playlist ? previewPlaylist : add)(text);
      return;
    }
    const controller = new AbortController();
    pending.current = controller;
    setSearching(true);
    setResults(null);
    setError("");
    try {
      const response = await search(text, controller.signal);
      if (!controller.signal.aborted) setResults(response.results);
    } catch (error) {
      if (!controller.signal.aborted)
        setError(
          error instanceof Error
            ? error.message
            : "検索に失敗しました。時間をおいて再試行してください。",
        );
    } finally {
      if (!controller.signal.aborted) {
        setSearching(false);
        pending.current = null;
      }
    }
  }

  return (
    <section className="request-panel panel" aria-labelledby="request-heading">
      <span className="eyebrow">MAKE IT YOURS</span>
      <h2 id="request-heading">聴きたい曲を、探そう。</h2>
      <p>曲名やアーティスト名で検索して、好きな曲を追加。</p>
      <form onSubmit={(event) => void submit(event)}>
        <label htmlFor="query">曲名・YouTube URL（再生リスト対応）</label>
        <div className="query-field">
          <Search size={18} />
          <input
            id="query"
            maxLength={500}
            placeholder="曲名、アーティスト名、YouTube URL"
            value={query}
            onChange={(event) => changeQuery(event.target.value)}
          />
        </div>
        <button
          className="primary add-button"
          disabled={!query.trim() || searching || (url && !canAdd)}
        >
          {searching || (url && busy) ? (
            <LoaderCircle size={18} className="spin" />
          ) : url ? (
            <Plus size={18} />
          ) : (
            <Search size={18} />
          )}
          {searching
            ? "検索しています…"
            : playlist
              ? "再生リストを確認"
              : url
                ? "キューに追加"
                : "YouTubeで検索"}
        </button>
        {playlist && (
          <p className="playlist-detected">
            再生リストを検知しました。曲数を確認してから追加します。
          </p>
        )}
      </form>
      {error && (
        <p className="search-error" role="alert">
          {error}
        </p>
      )}
      <div className="search-status" role="status" aria-live="polite">
        {searching
          ? "YouTubeから候補を探しています。"
          : results !== null
            ? results.length
              ? `${results.length}件の検索結果。聴きたい曲を選んで追加できます。`
              : "一致する動画が見つかりませんでした。曲名やアーティスト名を変えて検索してください。"
            : ""}
      </div>
      {!!results?.length && (
        <TrackResults
          tracks={results}
          label="YouTube検索結果"
          disabled={!canAdd}
          add={add}
        />
      )}
      <div className="request-hint">
        <Headphones size={17} />
        <span>
          {!canControl
            ? controlReason
            : !notificationReady
              ? "サーバー管理者に通知先チャンネルを設定してもらってください。"
              : "検索だけでは再生されません。選んだ曲を同じVCのみんなと楽しめます。"}
        </span>
      </div>
    </section>
  );
}

function looksLikeUrl(value: string) {
  return (
    value.includes("://") ||
    /^(?:(?:www|m|music)\.)?(?:youtube\.com|youtu\.be)(?:[/?#]|$)/i.test(value)
  );
}

function isPlaylist(value: string) {
  try {
    const url = new URL(value.includes("://") ? value : `https://${value}`);
    return (
      [
        "youtube.com",
        "www.youtube.com",
        "music.youtube.com",
        "m.youtube.com",
        "youtu.be",
      ].includes(url.hostname) && !!url.searchParams.get("list")
    );
  } catch {
    return false;
  }
}
