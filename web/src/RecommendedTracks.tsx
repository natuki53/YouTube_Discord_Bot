import { useEffect, useState } from "react";
import { LoaderCircle, RefreshCw, Sparkles } from "lucide-react";
import { TrackResults, type SearchTrack } from "./TrackResults";

export type RecommendationResponse = {
  track_id: string;
  results: SearchTrack[];
};

export function RecommendedTracks({
  seed,
  autoplay,
  excludeIds,
  disabled,
  load,
  add,
}: {
  seed: { id: string; title: string } | null;
  autoplay: boolean;
  excludeIds: (string | null)[];
  disabled: boolean;
  load: (
    trackId: string,
    signal: AbortSignal,
  ) => Promise<RecommendationResponse>;
  add: (url: string) => void;
}) {
  const [results, setResults] = useState<SearchTrack[] | null>(null);
  const [loading, setLoading] = useState(!!seed);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const trackId = seed?.id;
  useEffect(() => {
    const controller = new AbortController();
    setResults(null);
    setError("");
    setLoading(!!trackId);
    if (!trackId) return;
    void (async () => {
      try {
        const response = await load(trackId, controller.signal);
        if (!controller.signal.aborted && response.track_id === trackId)
          setResults(response.results);
      } catch (error) {
        if (!controller.signal.aborted)
          setError(
            error instanceof Error
              ? error.message
              : "候補を取得できませんでした。",
          );
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [trackId, autoplay, revision, load]);
  const visible =
    results?.filter((track) => !excludeIds.includes(track.video_id)) ?? [];

  return (
    <section
      className="recommendations-panel panel"
      aria-labelledby="recommendations-heading"
    >
      <div className="recommendations-header">
        <div>
          <span className="eyebrow">
            <Sparkles size={14} />
            DISCOVER MORE
          </span>
          <h2 id="recommendations-heading">自動選曲の候補</h2>
        </div>
        <button
          className="secondary"
          disabled={!seed || loading}
          onClick={() => setRevision((value) => value + 1)}
        >
          {loading ? (
            <LoaderCircle size={15} className="spin" />
          ) : (
            <RefreshCw size={15} />
          )}
          候補を更新
        </button>
      </div>
      {seed && (
        <p className="recommendations-seed">「{seed.title}」からのおすすめ</p>
      )}
      <p className="recommendations-hint">
        気になる曲を選んでキューに追加できます。自動選曲のオン・オフは変わりません。
      </p>
      <div className="search-status" role="status" aria-live="polite">
        {!seed
          ? "曲を再生すると、ここに候補を表示します。"
          : loading
            ? "関連する曲を探しています…"
            : results !== null && !visible.length
              ? "まだ再生していない候補が見つかりませんでした。別の曲でもお試しください。"
              : visible.length
                ? `${visible.length}件の候補があります。`
                : ""}
      </div>
      {error && (
        <p className="search-error" role="alert">
          {error}
        </p>
      )}
      {!!visible.length && (
        <TrackResults
          tracks={visible}
          label="自動選曲の候補一覧"
          disabled={disabled}
          add={add}
          className="recommendation-results"
        />
      )}
    </section>
  );
}
