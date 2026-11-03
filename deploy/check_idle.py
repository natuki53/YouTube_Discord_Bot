"""docker exec -i youtube-bot python < deploy/check_idle.py で使用する。"""

import json
import os
import pathlib
import sys
import time

if os.getenv("WEB_ENABLED", "false").lower() == "true":
    state_file = (
        pathlib.Path(os.getenv("WEB_DATABASE_PATH", "/app/data/web.sqlite3")).parent
        / "activity.json"
    )
    try:
        activity = json.loads(state_file.read_text())
        idle = (
            time.time() - activity["at"] < 15
            and activity["jobs"] == 0
            and activity["voice"] == 0
        )
    except (OSError, ValueError, KeyError):
        idle = False
    if not idle:
        print(
            json.dumps(
                {"idle": False, "reason": "active or unconfirmed web/voice state"}
            )
        )
        sys.exit(1)

ffmpeg = any(
    p.read_text().strip() == "ffmpeg"
    for p in pathlib.Path("/proc").glob("[0-9]*/comm")
    if p.exists()
)
voice = False
for name in ("/proc/net/udp", "/proc/net/udp6"):
    for row in pathlib.Path(name).read_text().splitlines()[1:]:
        host, port = row.split()[2].split(":")
        if int(host, 16) != 0 and int(port, 16) != 53:
            voice = True
print(json.dumps({"idle": not (voice or ffmpeg), "voice": voice, "ffmpeg": ffmpeg}))
sys.exit(1 if voice or ffmpeg else 0)
