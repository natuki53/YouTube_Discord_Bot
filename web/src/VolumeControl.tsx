import { memo, useEffect, useRef, useState } from "react";
import { LoaderCircle, Volume2 } from "lucide-react";

type Props = {
  value: number;
  disabled: boolean;
  onCommit: (value: number) => Promise<number>;
};

export const VolumeControl = memo(function VolumeControl({
  value,
  disabled,
  onCommit,
}: Props) {
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const editing = useRef(false),
    dirty = useRef(false),
    sending = useRef(false);
  const queued = useRef<number | null>(null),
    alive = useRef(true),
    serverValue = useRef(value);
  serverValue.current = value;
  useEffect(
    () => () => {
      alive.current = false;
    },
    [],
  );
  useEffect(() => {
    if (!editing.current && !sending.current && !dirty.current) setDraft(value);
  }, [value, saving]);

  async function flush() {
    if (sending.current) return;
    sending.current = true;
    setSaving(true);
    try {
      while (queued.current !== null && alive.current) {
        const desired = queued.current;
        queued.current = null;
        try {
          const applied = await onCommit(desired);
          if (alive.current && !editing.current && queued.current === null)
            setDraft(applied);
        } catch {
          if (alive.current && !editing.current && queued.current === null)
            setDraft(serverValue.current);
        }
      }
    } finally {
      sending.current = false;
      if (alive.current) setSaving(false);
    }
  }
  function release(raw: string) {
    editing.current = false;
    if (!dirty.current) return;
    dirty.current = false;
    const desired = Math.max(1, Math.min(100, Number(raw)));
    setDraft(desired);
    queued.current = desired;
    void flush();
  }
  return (
    <div className="volume" aria-busy={saving}>
      <Volume2 size={18} />
      <input
        aria-label="音量"
        type="range"
        min="1"
        max="100"
        value={draft}
        disabled={disabled}
        onPointerDown={(event) => {
          editing.current = true;
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onChange={(event) => {
          dirty.current = true;
          setDraft(Number(event.currentTarget.value));
        }}
        onPointerUp={(event) => release(event.currentTarget.value)}
        onPointerCancel={(event) => release(event.currentTarget.value)}
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
      />
      <span className="volume-value">
        {draft}%
        {saving && <LoaderCircle size={10} className="spin volume-saving" />}
      </span>
    </div>
  );
});
