import { memo, useEffect, useRef, useState } from "react";
import { LoaderCircle } from "lucide-react";

export type PlaybackProgress = {
  position: number;
  duration: number | null;
  seekable: boolean;
  rate?: number;
};
export function formatTime(seconds: number) {
  const whole = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(whole / 60),
    remainder = whole % 60;
  return minutes >= 60
    ? `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`
    : `${minutes}:${String(remainder).padStart(2, "0")}`;
}

export const ProgressControl = memo(function ProgressControl({
  progress,
  running,
  disabled,
  onSeek,
}: {
  progress: PlaybackProgress;
  running: boolean;
  disabled: boolean;
  onSeek: (position: number) => Promise<void>;
}) {
  const [draft, setDraft] = useState(progress.position);
  const [saving, setSaving] = useState(false);
  const anchor = useRef({
    position: progress.position,
    at: performance.now(),
    running,
    rate: progress.rate || 1,
  });
  const editing = useRef(false),
    dirty = useRef(false),
    sending = useRef(false),
    alive = useRef(true);
  const queued = useRef<number | null>(null);
  const currentPosition = () =>
    Math.min(
      progress.duration ?? Infinity,
      anchor.current.position +
        (anchor.current.running
          ? ((performance.now() - anchor.current.at) / 1000) *
            anchor.current.rate
          : 0),
    );
  useEffect(() => {
    anchor.current = {
      position: progress.position,
      at: performance.now(),
      running,
      rate: progress.rate || 1,
    };
    if (!editing.current && !sending.current) setDraft(progress.position);
  }, [progress.position, progress.rate, running]);
  useEffect(() => {
    const timer = setInterval(() => {
      if (!editing.current && !sending.current) setDraft(currentPosition());
    }, 250);
    return () => clearInterval(timer);
  }, [progress.duration]);
  useEffect(
    () => () => {
      alive.current = false;
    },
    [],
  );
  async function flush() {
    if (sending.current) return;
    sending.current = true;
    setSaving(true);
    try {
      while (queued.current !== null && alive.current) {
        const desired = queued.current;
        queued.current = null;
        try {
          await onSeek(desired);
        } catch {
          if (alive.current && !editing.current && queued.current === null)
            setDraft(currentPosition());
        }
      }
    } finally {
      sending.current = false;
      if (alive.current) setSaving(false);
    }
  }
  function release(value: string) {
    editing.current = false;
    if (!dirty.current) return;
    dirty.current = false;
    queued.current = Number(value);
    void flush();
  }
  const duration = progress.duration;
  return (
    <div className="playback-progress" aria-busy={saving}>
      <span className="progress-time">{formatTime(draft)}</span>
      <div className="progress-slider">
        <input
          type="range"
          aria-label="再生位置"
          aria-valuetext={`${formatTime(draft)} / ${duration === null ? "長さ不明" : formatTime(duration)}`}
          min="0"
          max={duration || 1}
          step="1"
          value={duration ? Math.min(draft, duration) : 0}
          disabled={disabled || !progress.seekable || !duration}
          onPointerDown={(event) => {
            editing.current = true;
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onChange={(event) => {
            dirty.current = true;
            setDraft(Number(event.currentTarget.value));
          }}
          onPointerUp={(event) => release(event.currentTarget.value)}
          onPointerCancel={() => {
            editing.current = false;
            dirty.current = false;
            setDraft(currentPosition());
          }}
          onKeyDown={() => {
            editing.current = true;
          }}
          onKeyUp={(event) => {
            if (
              [
                "ArrowLeft",
                "ArrowRight",
                "ArrowUp",
                "ArrowDown",
                "Home",
                "End",
                "PageUp",
                "PageDown",
              ].includes(event.key)
            )
              release(event.currentTarget.value);
          }}
          onBlur={(event) => release(event.currentTarget.value)}
          title={
            !progress.seekable
              ? "再生時間が未確定の音声はシークできません"
              : "ドラッグして再生位置を変更"
          }
        />
        {saving && (
          <LoaderCircle
            size={12}
            className="spin progress-saving"
            aria-label="再生位置を変更中"
          />
        )}
      </div>
      <span className="progress-time">
        {duration === null ? "--:--" : formatTime(duration)}
      </span>
    </div>
  );
});
