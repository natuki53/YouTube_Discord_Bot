import { ArrowUpRight, Plus } from "lucide-react";
import { Thumbnail } from "./Thumbnail";

export type SearchTrack = {
  video_id: string;
  url: string;
  title: string;
  channel: string | null;
  duration: number | null;
};

export function TrackResults({
  tracks,
  label,
  disabled,
  add,
  className = "",
}: {
  tracks: SearchTrack[];
  label: string;
  disabled: boolean;
  add: (url: string) => void;
  className?: string;
}) {
  return (
    <ul
      className={`search-results ${className}`}
      aria-label={label}
      tabIndex={0}
    >
      {tracks.map((track) => (
        <li key={track.video_id}>
          <a
            className="search-thumbnail"
            href={track.url}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`${track.title}をYouTubeで開く`}
          >
            <Thumbnail videoId={track.video_id} />
          </a>
          <div className="search-track">
            <a
              href={track.url}
              target="_blank"
              rel="noopener noreferrer"
              className="search-title"
            >
              {track.title}
              <ArrowUpRight size={12} />
            </a>
            <div className="search-meta">
              {track.channel && (
                <span className="search-channel" title={track.channel}>
                  {track.channel}
                </span>
              )}
              {track.duration !== null && (
                <span className="search-duration">
                  {durationLabel(track.duration)}
                </span>
              )}
            </div>
          </div>
          <button
            type="button"
            className="search-add"
            disabled={disabled}
            aria-label={`${track.title}をキューに追加`}
            onClick={() => add(track.url)}
          >
            <Plus size={16} />
            <span>追加</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function durationLabel(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const remaining = String(Math.floor(seconds % 60)).padStart(2, "0");
  return minutes >= 60
    ? `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}:${remaining}`
    : `${minutes}:${remaining}`;
}
