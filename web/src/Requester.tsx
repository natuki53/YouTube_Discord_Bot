import { useState } from "react";
import { Sparkles, UserRound } from "lucide-react";

function discordAvatar(value?: string | null) {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    if (
      url.protocol === "https:" &&
      url.host === "cdn.discordapp.com" &&
      !url.username &&
      !url.password
    )
      return url.href;
  } catch {
    // Missing or invalid avatars use the same fixed-size placeholder.
  }
  return undefined;
}

export function Requester({
  name,
  avatar,
  automatic = false,
}: {
  name: string;
  avatar?: string | null;
  automatic?: boolean;
}) {
  const source = discordAvatar(avatar);
  const [failed, setFailed] = useState<string>();
  const Icon = automatic ? Sparkles : UserRound;
  return (
    <span className="requester" title={name}>
      <span className="requester-icon" aria-hidden="true">
        {source && source !== failed ? (
          <img
            className="requester-avatar"
            src={source}
            alt=""
            width={22}
            height={22}
            loading="lazy"
            decoding="async"
            referrerPolicy="no-referrer"
            draggable={false}
            onError={() => setFailed(source)}
          />
        ) : (
          <Icon size={14} />
        )}
      </span>
      <span className="requester-name">{name}</span>
    </span>
  );
}
