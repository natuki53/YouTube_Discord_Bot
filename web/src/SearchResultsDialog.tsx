import { useEffect, useRef, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { LoaderCircle, Search, X } from "lucide-react";
import { TrackResults, type SearchTrack } from "./TrackResults";

export function SearchResultsDialog({
  query,
  changeQuery,
  searching,
  results,
  error,
  feedback,
  canAdd,
  hint,
  add,
  search,
  close,
}: {
  query: string;
  changeQuery: (query: string) => void;
  searching: boolean;
  results: SearchTrack[] | null;
  error: string;
  feedback: string;
  canAdd: boolean;
  hint: string;
  add: (url: string) => void;
  search: (event: FormEvent) => void;
  close: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const element = dialog.current!;
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    element.showModal();
    closeButton.current?.focus({ preventScroll: true });
    return () => {
      element.close();
      if (previous?.isConnected && !previous.hasAttribute("disabled"))
        previous.focus({ preventScroll: true });
    };
  }, []);

  return createPortal(
    <dialog
      ref={dialog}
      className="search-dialog"
      aria-labelledby="search-results-title"
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
      onKeyDown={(event) => {
        if (event.key !== "Tab") return;
        const items = Array.from(
          event.currentTarget.querySelectorAll<HTMLElement>(
            'button:not(:disabled), input:not(:disabled), a[href], [tabindex="0"]',
          ),
        ).filter((element) => element.getClientRects().length);
        const first = items[0],
          last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }}
      onClick={(event) => {
        const rect = event.currentTarget.getBoundingClientRect();
        if (
          event.target === event.currentTarget &&
          (event.clientX < rect.left ||
            event.clientX > rect.right ||
            event.clientY < rect.top ||
            event.clientY > rect.bottom)
        )
          close();
      }}
    >
      <div className="search-dialog-heading">
        <div>
          <span className="eyebrow">FIND YOUR NEXT SONG</span>
          <h2 id="search-results-title">YouTubeの検索結果</h2>
        </div>
        <button
          ref={closeButton}
          type="button"
          className="icon-button"
          aria-label="検索結果を閉じる"
          onClick={close}
        >
          <X size={20} />
        </button>
      </div>
      <form className="search-dialog-form" onSubmit={search}>
        <label htmlFor="search-dialog-query">曲名・アーティスト名</label>
        <div className="search-dialog-query">
          <div className="query-field">
            <Search size={18} />
            <input
              id="search-dialog-query"
              maxLength={500}
              value={query}
              onChange={(event) => changeQuery(event.target.value)}
              placeholder="曲名・アーティスト名"
            />
          </div>
          <button className="primary" disabled={searching || !query.trim()}>
            {searching ? (
              <LoaderCircle size={16} className="spin" />
            ) : (
              <Search size={16} />
            )}
            再検索
          </button>
        </div>
      </form>
      <div className="search-dialog-body">
        <div className="search-status" role="status" aria-live="polite">
          {searching
            ? "YouTubeから候補を探しています…"
            : results !== null
              ? results.length
                ? `${results.length}件の検索結果。聴きたい曲を選んで追加できます。`
                : "一致する動画が見つかりませんでした。曲名やアーティスト名を変えて検索してください。"
              : "曲名やアーティスト名を入力して検索してください。"}
        </div>
        {error && (
          <p className="search-error" role="alert">
            {error}
          </p>
        )}
        {!!results?.length && (
          <TrackResults
            tracks={results}
            label="YouTube検索結果"
            disabled={!canAdd}
            add={add}
          />
        )}
      </div>
      <div className="search-dialog-footer">
        <div>
          <p className="search-add-feedback" role="status" aria-live="polite">
            {feedback}
          </p>
          <p>{hint}</p>
        </div>
        <button type="button" className="secondary" onClick={close}>
          閉じる
        </button>
      </div>
    </dialog>,
    document.body,
  );
}
