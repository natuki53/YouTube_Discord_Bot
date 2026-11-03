import { memo, useEffect, useId, useRef, useState } from "react";
import {
  ChevronDown,
  Headphones,
  RotateCcw,
  Speaker,
  Orbit,
} from "lucide-react";
import { automaticPosition, type SpatialMotion } from "./spatialMotion";
import "./spatial.css";

export type SpatialPosition = {
  enabled: boolean;
  x: number;
  y: number;
  z: number;
  mode: "natural" | "binaural";
  auto: boolean;
};
export type SpatialState = SpatialPosition & {
  available: boolean;
  binaural_available?: boolean;
  motion?: SpatialMotion | null;
};
export const defaultSpatial: SpatialState = {
  enabled: false,
  x: 0,
  y: 1.5,
  z: 0,
  available: false,
  mode: "natural",
  auto: false,
};

export const SpatialControl = memo(function SpatialControl({
  value,
  disabled,
  onCommit,
}: {
  value: SpatialState;
  disabled: boolean;
  onCommit: (position: SpatialPosition) => Promise<SpatialState>;
}) {
  const id = useId();
  const [draft, setDraft] = useState<SpatialPosition>(value);
  const [expanded, setExpanded] = useState(value.enabled);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const latest = useRef<SpatialPosition>(value),
    server = useRef(value);
  const editing = useRef(false),
    sending = useRef(false),
    alive = useRef(true);
  const queued = useRef<SpatialPosition | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSent = useRef(0);
  server.current = value;
  const unavailable = disabled || !value.available;
  const locked = unavailable || !draft.enabled;

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      if (timer.current) clearTimeout(timer.current);
      queued.current = null;
    };
  }, []);
  useEffect(() => {
    if (!editing.current && !sending.current && !queued.current) {
      latest.current = value;
      setDraft(value);
    }
  }, [value, saving]);
  useEffect(() => {
    if (unavailable) {
      queued.current = null;
      editing.current = false;
      if (timer.current) clearTimeout(timer.current);
      timer.current = null;
      setSaving(false);
    }
  }, [unavailable]);
  useEffect(() => {
    if (!expanded || !value.enabled || !value.auto || !value.motion) return;
    const motion = value.motion,
      started = performance.now();
    let frame = 0,
      last = -Infinity;
    function tick(now: number) {
      if (!alive.current) return;
      if (
        now - last >= 32 &&
        latest.current.auto &&
        !editing.current &&
        !sending.current &&
        !queued.current
      ) {
        const next = {
          ...latest.current,
          ...automaticPosition(motion, motion.elapsed + (now - started) / 1000),
        };
        latest.current = next;
        setDraft(next);
        last = now;
      }
      frame = requestAnimationFrame(tick);
    }
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [expanded, value.enabled, value.auto, value.motion]);

  function schedule() {
    if (timer.current || sending.current || !alive.current) return;
    timer.current = setTimeout(
      () => {
        timer.current = null;
        void flush();
      },
      Math.max(0, 120 - (performance.now() - lastSent.current)),
    );
  }
  async function flush() {
    if (sending.current || !queued.current || !alive.current) return;
    const desired = queued.current;
    queued.current = null;
    sending.current = true;
    lastSent.current = performance.now();
    try {
      const applied = await onCommit(desired);
      if (alive.current && !editing.current && !queued.current) {
        latest.current = applied;
        setDraft(applied);
      }
    } catch (failure) {
      if (alive.current) {
        queued.current = null;
        setError(
          failure instanceof Error
            ? failure.message
            : "変更を反映できませんでした。",
        );
        latest.current = server.current;
        setDraft(server.current);
      }
    } finally {
      sending.current = false;
      if (alive.current) {
        if (queued.current) schedule();
        else setSaving(false);
      }
    }
  }
  function update(change: Partial<SpatialPosition>) {
    if (unavailable) return;
    if (
      ("x" in change || "y" in change || "z" in change) &&
      !("auto" in change)
    )
      change = { ...change, auto: false };
    const next = { ...latest.current, ...change };
    latest.current = next;
    setDraft(next);
    queued.current = {
      enabled: next.enabled,
      x: next.x,
      y: next.y,
      z: next.z,
      mode: next.mode || "natural",
      auto: next.auto || false,
    };
    setError("");
    setSaving(true);
    schedule();
  }
  function move(event: React.PointerEvent<HTMLDivElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const clamp = (number: number) =>
      Math.round(Math.max(-4, Math.min(4, number)) * 100) / 100;
    update({
      x: clamp(((event.clientX - rect.left) / rect.width - 0.5) * 8),
      y: clamp((0.5 - (event.clientY - rect.top) / rect.height) * 8),
    });
  }
  const distance = Math.hypot(draft.x, draft.y, draft.z);
  const angle = Math.round((Math.atan2(draft.x, draft.y) * 180) / Math.PI);
  return (
    <section className="spatial-panel panel" aria-labelledby={`${id}-title`}>
      <div className="spatial-heading">
        <div>
          <h2 id={`${id}-title`}>
            <Headphones size={18} />
            立体音響
          </h2>
          <p>ヘッドホン推奨 · 同じVCの全員に反映</p>
        </div>
        <div className="spatial-heading-actions">
          <button
            className="spatial-expand"
            aria-expanded={expanded}
            aria-controls={`${id}-body`}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? "配置を閉じる" : "配置を開く"}
            <ChevronDown size={15} />
          </button>
          <button
            className={`autoplay ${draft.enabled ? "enabled" : ""}`}
            role="switch"
            aria-label="立体音響"
            aria-checked={draft.enabled}
            disabled={unavailable}
            onClick={() => {
              if (!draft.enabled) setExpanded(true);
              update({ enabled: !draft.enabled, auto: false });
            }}
          >
            <span className="spatial-toggle-label">
              {draft.enabled ? "オン" : "オフ"}
            </span>
            <span className="toggle" aria-hidden="true">
              <i />
            </span>
          </button>
        </div>
      </div>
      {expanded && (
        <div className="spatial-body" id={`${id}-body`}>
          <div className="spatial-copy">
            <span className="eyebrow">SPATIAL AUDIO</span>
            <h3>音の居場所を、動かそう。</h3>
            <p id={`${id}-help`}>
              中央があなたの位置です。スピーカーをドラッグして、音の方向と距離を変えられます。
            </p>
            <p className="spatial-keyboard-help">
              矢印キーでも移動できます。高さは右のスライダーで調整。
            </p>
            <div className="spatial-position-actions">
              <button
                className="secondary spatial-reset"
                disabled={locked}
                onClick={() => update({ x: 0, y: 1.5, z: 0 })}
              >
                <RotateCcw size={14} />
                正面に戻す
              </button>
              <button
                className={`secondary spatial-auto ${draft.auto ? "active" : ""}`}
                aria-label="スピーカーのオート移動"
                aria-pressed={!!draft.auto}
                disabled={unavailable}
                onClick={() => update({ enabled: true, auto: !draft.auto })}
              >
                <Orbit size={14} />
                オート
              </button>
            </div>
          </div>
          <div className={`spatial-map ${locked ? "spatial-locked" : ""}`}>
            <span className="spatial-front">前</span>
            <span className="spatial-back">後</span>
            <span className="spatial-left">左</span>
            <span className="spatial-right">右</span>
            <div
              className="spatial-plane"
              role="group"
              aria-label="スピーカー配置"
              onPointerDown={(event) => {
                if (locked || event.button !== 0) return;
                event.preventDefault();
                editing.current = true;
                event.currentTarget.setPointerCapture(event.pointerId);
                move(event);
              }}
              onPointerMove={(event) => {
                if (editing.current && !locked) move(event);
              }}
              onPointerUp={() => {
                editing.current = false;
              }}
              onPointerCancel={() => {
                editing.current = false;
              }}
            >
              <svg
                className="spatial-grid"
                viewBox="0 0 200 200"
                aria-hidden="true"
              >
                {[25, 50, 75, 99].map((r) => (
                  <circle key={r} cx="100" cy="100" r={r} />
                ))}
                <path d="M0 100H200 M100 0V200" />
                <line
                  className="spatial-beam"
                  x1="100"
                  y1="100"
                  x2={100 + draft.x * 25}
                  y2={100 - draft.y * 25}
                />
              </svg>
              <div className="spatial-listener" aria-hidden="true">
                <span>▴</span>
                <Headphones size={26} />
                <small>あなた</small>
              </div>
              <button
                className="spatial-speaker"
                aria-label="スピーカー位置"
                aria-describedby={`${id}-help ${id}-coordinates`}
                disabled={locked}
                style={{
                  left: `${50 + draft.x * 12.5}%`,
                  top: `${50 - draft.y * 12.5}%`,
                }}
                onKeyDown={(event) => {
                  if (
                    ![
                      "ArrowLeft",
                      "ArrowRight",
                      "ArrowUp",
                      "ArrowDown",
                    ].includes(event.key)
                  )
                    return;
                  event.preventDefault();
                  editing.current = true;
                  const step = event.shiftKey ? 0.5 : 0.1;
                  update({
                    x: Math.max(
                      -4,
                      Math.min(
                        4,
                        latest.current.x +
                          (event.key === "ArrowRight"
                            ? step
                            : event.key === "ArrowLeft"
                              ? -step
                              : 0),
                      ),
                    ),
                    y: Math.max(
                      -4,
                      Math.min(
                        4,
                        latest.current.y +
                          (event.key === "ArrowUp"
                            ? step
                            : event.key === "ArrowDown"
                              ? -step
                              : 0),
                      ),
                    ),
                  });
                }}
                onKeyUp={() => {
                  editing.current = false;
                }}
                onBlur={() => {
                  editing.current = false;
                }}
              >
                <Speaker size={23} aria-hidden="true" />
              </button>
            </div>
          </div>
          <div className="spatial-details">
            <label className="spatial-mode">
              音の表現
              <select
                aria-label="音の表現"
                value={draft.mode || "natural"}
                disabled={unavailable}
                onChange={(event) =>
                  update({
                    mode: event.currentTarget.value as SpatialPosition["mode"],
                  })
                }
              >
                <option value="natural">音質優先（標準）</option>
                <option value="binaural" disabled={!value.binaural_available}>
                  立体感優先（HRTF）
                </option>
              </select>
              <small>
                {draft.mode === "binaural"
                  ? "前後・上下の表現を強めます。音色も変化します。"
                  : "元のステレオと音色を保ちます。前後・上下の定位は控えめです。"}
              </small>
            </label>
            <div className="spatial-readout" id={`${id}-coordinates`}>
              <div>
                <span>方向</span>
                <strong>
                  {angle > 0 ? "+" : ""}
                  {angle}°
                </strong>
              </div>
              <div>
                <span>距離</span>
                <strong>{distance.toFixed(1)} m</strong>
              </div>
            </div>
            <label className="spatial-height">
              高さ
              <span>
                {draft.z > 0 ? "+" : ""}
                {draft.z.toFixed(1)} m
              </span>
              <input
                aria-label="スピーカーの高さ"
                type="range"
                min="-2"
                max="2"
                step="0.1"
                value={draft.z}
                disabled={locked}
                onPointerDown={() => {
                  editing.current = true;
                }}
                onPointerUp={() => {
                  editing.current = false;
                }}
                onPointerCancel={() => {
                  editing.current = false;
                }}
                onKeyDown={() => {
                  editing.current = true;
                }}
                onKeyUp={() => {
                  editing.current = false;
                }}
                onBlur={() => {
                  editing.current = false;
                }}
                onChange={(event) =>
                  update({ z: Number(event.currentTarget.value) })
                }
              />
              <small>
                <span>下 −2 m</span>
                <span>上 ＋2 m</span>
              </small>
            </label>
            <div
              className="spatial-presets"
              aria-label="スピーカーの配置プリセット"
            >
              {[
                ["前", 0, 1.5],
                ["左", -1.5, 0],
                ["右", 1.5, 0],
                ["後", 0, -1.5],
              ].map(([name, x, y]) => (
                <button
                  key={name}
                  className="secondary"
                  disabled={locked}
                  aria-label={`スピーカーを${name}へ`}
                  onClick={() => update({ x: Number(x), y: Number(y), z: 0 })}
                >
                  {name}
                </button>
              ))}
            </div>
            <p
              className={`spatial-status ${error ? "spatial-error" : ""}`}
              role="status"
              aria-busy={saving}
            >
              {error ||
                (!value.available
                  ? "この環境では利用できません。"
                  : disabled
                    ? "Botと同じVCで操作できます。"
                    : draft.enabled
                      ? draft.auto
                        ? "自動で周回中 · ドラッグでオートを解除"
                        : "配置をリアルタイムで反映します"
                      : "オンにしてスピーカーを動かせます")}
            </p>
          </div>
        </div>
      )}
    </section>
  );
});
