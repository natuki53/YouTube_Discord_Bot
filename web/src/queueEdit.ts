import type { QueueTrack } from "./QueueList";

export function editQueueTracks(
  tracks: QueueTrack[],
  action: "queue_remove" | "queue_move",
  id: string,
  beforeId?: string | null,
): QueueTrack[] {
  const track = tracks.find((item) => item.id === id);
  if (
    !track || beforeId === id ||
    (action === "queue_move" && beforeId && !tracks.some((item) => item.id === beforeId))
  )
    return tracks;
  const next = tracks.filter((item) => item.id !== id);
  if (action === "queue_move")
    next.splice(
      beforeId ? next.findIndex((item) => item.id === beforeId) : next.length,
      0,
      track,
    );
  return next;
}
