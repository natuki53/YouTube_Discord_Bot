import { useState } from "react";
import { Music2 } from "lucide-react";

export function Thumbnail({ videoId }: { videoId: string | null }) {
  const [failed, setFailed] = useState<string | null>(null);
  return videoId && /^[\w-]{11}$/.test(videoId) && failed !== videoId ? (
    <img
      src={`https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`}
      alt=""
      loading="lazy"
      decoding="async"
      onError={() => setFailed(videoId)}
    />
  ) : (
    <Music2 size={17} />
  );
}
