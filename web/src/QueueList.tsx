import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  DndContext,
  PointerSensor,
  KeyboardSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  useSortable,
  arrayMove,
  verticalListSortingStrategy,
  sortableKeyboardCoordinates,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  GripVertical,
  MoreHorizontal,
  Trash2,
  ArrowUpToLine,
  ArrowUpRight,
} from "lucide-react";
import { ScrollingTitle } from "./ScrollingTitle";
import { Thumbnail } from "./Thumbnail";
import { Requester } from "./Requester";

export type QueueTrack = {
  id: string;
  title: string;
  url: string;
  requester: string;
  requester_avatar?: string | null;
  video_id: string | null;
  auto_selected: boolean;
};
type Edit = (
  action: "queue_remove" | "queue_move",
  id: string,
  beforeId?: string | null,
) => Promise<QueueTrack[]>;

function TrackMenu({
  index,
  disabled,
  onRemove,
  onFirst,
}: {
  index: number;
  disabled: boolean;
  onRemove: () => void;
  onFirst: () => void;
}) {
  const button = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState<{
    top: number;
    right: number;
  } | null>(null);
  const open = position !== null;
  useEffect(() => {
    if (!open) return;
    menu.current
      ?.querySelector<HTMLButtonElement>("button:not(:disabled)")
      ?.focus({ preventScroll: true });
    const close = (event: PointerEvent) => {
      if (
        !menu.current?.contains(event.target as Node) &&
        !button.current?.contains(event.target as Node)
      )
        setPosition(null);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setPosition(null);
        button.current?.focus();
      }
    };
    const scroll = () => {
      const rect = button.current?.getBoundingClientRect();
      if (!rect || rect.bottom < 0 || rect.top > window.innerHeight)
        setPosition(null);
      else
        setPosition({
          top: Math.max(8, Math.min(rect.bottom + 6, window.innerHeight - 132)),
          right: Math.max(12, window.innerWidth - rect.right),
        });
    };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", escape);
    window.addEventListener("scroll", scroll, true);
    window.addEventListener("resize", scroll);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", escape);
      window.removeEventListener("scroll", scroll, true);
      window.removeEventListener("resize", scroll);
    };
  }, [open]);
  return (
    <>
      <button
        ref={button}
        className="icon-button queue-menu-button"
        aria-label={`${index + 1}曲目のメニュー`}
        aria-haspopup="menu"
        aria-expanded={!!position}
        disabled={disabled}
        onClick={() => {
          const rect = button.current!.getBoundingClientRect();
          setPosition(
            position
              ? null
              : {
                  top: Math.min(rect.bottom + 6, window.innerHeight - 132),
                  right: Math.max(12, window.innerWidth - rect.right),
                },
          );
        }}
      >
        <MoreHorizontal size={20} />
      </button>
      {position &&
        createPortal(
          <div
            ref={menu}
            className="track-menu"
            role="menu"
            aria-label={`${index + 1}曲目の操作`}
            style={position}
            onBlur={(event) => {
              if (!event.currentTarget.contains(event.relatedTarget as Node))
                setPosition(null);
            }}
            onKeyDown={(event) => {
              if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
              event.preventDefault();
              const items = [
                ...event.currentTarget.querySelectorAll<HTMLButtonElement>(
                  "button:not(:disabled)",
                ),
              ];
              const next =
                (items.indexOf(document.activeElement as HTMLButtonElement) +
                  (event.key === "ArrowDown" ? 1 : -1) +
                  items.length) %
                items.length;
              items[next]?.focus();
            }}
          >
            <button
              role="menuitem"
              disabled={index === 0}
              onClick={() => {
                setPosition(null);
                button.current?.focus();
                onFirst();
              }}
            >
              <ArrowUpToLine size={16} />
              次に再生
            </button>
            <button
              role="menuitem"
              className="danger"
              onClick={() => {
                setPosition(null);
                onRemove();
              }}
            >
              <Trash2 size={16} />
              キューから削除
            </button>
          </div>,
          document.body,
        )}
    </>
  );
}

function Row({
  track,
  index,
  disabled,
  edit,
  firstId,
}: {
  track: QueueTrack;
  index: number;
  disabled: boolean;
  edit: Edit;
  firstId: string;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    setActivatorNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: track.id, disabled });
  return (
    <li
      ref={setNodeRef}
      data-track-id={track.id}
      className={isDragging ? "queue-dragging" : ""}
      style={{ transform: CSS.Transform.toString(transform), transition }}
    >
      <button
        className="queue-drag-handle"
        ref={setActivatorNodeRef}
        {...attributes}
        {...listeners}
        aria-label={`${index + 1}曲目を並べ替え`}
        title="ドラッグで並べ替え（キーボード: Space・矢印キー）"
        disabled={disabled}
      >
        <span className="track-number">
          {String(index + 1).padStart(2, "0")}
        </span>
        <GripVertical size={16} />
      </button>
      <div className="queue-track">
        <span className="queue-note">
          <Thumbnail videoId={track.video_id} />
        </span>
        <div>
          <a href={safeYoutube(track.url)} target="_blank" rel="noreferrer">
            <ScrollingTitle>{track.title}</ScrollingTitle>
          </a>
          <small>{track.auto_selected ? "自動選曲" : "YouTube"}</small>
        </div>
      </div>
      <Requester
        name={track.requester}
        avatar={track.requester_avatar}
        automatic={track.auto_selected}
      />
      <TrackMenu
        index={index}
        disabled={disabled}
        onRemove={() => void edit("queue_remove", track.id)}
        onFirst={() => void edit("queue_move", track.id, firstId)}
      />
    </li>
  );
}

function safeYoutube(value: string) {
  try {
    const url = new URL(value);
    if (
      url.protocol === "https:" &&
      [
        "youtube.com",
        "www.youtube.com",
        "music.youtube.com",
        "m.youtube.com",
        "youtu.be",
      ].includes(url.hostname)
    )
      return url.href;
  } catch {
    /* Invalid URLs are never opened. */
  }
  return undefined;
}

export function QueueList({
  tracks,
  disabled,
  onEdit,
  onInteractionChange,
}: {
  tracks: QueueTrack[];
  disabled: boolean;
  onEdit: Edit;
  onInteractionChange: (active: boolean) => void;
}) {
  const [rows, setRows] = useState(tracks);
  const [dragging, setDragging] = useState(false);
  const [pending, setPending] = useState(false);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
      scrollBehavior: "auto",
    }),
  );
  useEffect(() => {
    if (!dragging && !pending) setRows(tracks);
  }, [tracks, dragging, pending]);
  const edit: Edit = async (action, id, beforeId) => {
    setPending(true);
    try {
      const updated = await onEdit(action, id, beforeId);
      setRows(updated);
      return updated;
    } catch {
      setRows(tracks);
      return tracks;
    } finally {
      setPending(false);
    }
  };
  const end = (event: DragEndEvent) => {
    const { active, over } = event;
    if (over && active.id !== over.id) {
      const from = rows.findIndex((t) => t.id === active.id),
        to = rows.findIndex((t) => t.id === over.id);
      if (from >= 0 && to >= 0) {
        const reordered = arrayMove(rows, from, to);
        setRows(reordered);
        void edit(
          "queue_move",
          String(active.id),
          reordered[to + 1]?.id || null,
        );
      }
    }
    setDragging(false);
    onInteractionChange(false);
  };
  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragStart={() => {
        setDragging(true);
        onInteractionChange(true);
      }}
      onDragEnd={end}
      onDragCancel={() => {
        setDragging(false);
        onInteractionChange(false);
      }}
      accessibility={{
        announcements: {
          onDragStart: ({ active }) =>
            `${rows.find((t) => t.id === active.id)?.title || "曲"}をつかみました。`,
          onDragOver: ({ over }) =>
            over
              ? `${rows.findIndex((t) => t.id === over.id) + 1}番目へ移動します。`
              : "移動先を選んでください。",
          onDragEnd: ({ over }) =>
            over ? "並べ替えを確定しました。" : "並べ替えを取り消しました。",
          onDragCancel: () => "並べ替えを取り消しました。",
        },
        screenReaderInstructions: {
          draggable:
            "スペースキーで曲をつかみ、上下の矢印キーで移動し、スペースキーで確定します。Escapeで取り消します。",
        },
      }}
    >
      <SortableContext
        items={rows.map((t) => t.id)}
        strategy={verticalListSortingStrategy}
      >
        <ol className="queue-list" aria-label="再生待ちの曲">
          {rows.map((track, index) => (
            <Row
              key={track.id}
              track={track}
              index={index}
              disabled={disabled || pending}
              edit={edit}
              firstId={rows[0].id}
            />
          ))}
        </ol>
      </SortableContext>
    </DndContext>
  );
}
