#!/usr/bin/env python3
"""Install the YouTube bot hook into an existing adnanh/webhook receiver."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
from datetime import datetime
from pathlib import Path


HOOK_ID = "deploy-youtube-bot"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--hooks-file",
        type=Path,
        default=Path("/home/natuki/services/web-server/deploy/hooks.json"),
    )
    parser.add_argument(
        "--trigger-source",
        type=Path,
        default=Path(
            "/home/natuki/services/discord-bots/youtube-bot/deploy/trigger.sh"
        ),
    )
    parser.add_argument(
        "--trigger-destination",
        type=Path,
        default=Path(
            "/home/natuki/services/web-server/deploy/youtube-bot-trigger.sh"
        ),
    )
    parser.add_argument(
        "--secret-file",
        type=Path,
        default=Path(
            "/home/natuki/services/web-server/deploy/youtube-bot-webhook-secret"
        ),
    )
    parser.add_argument(
        "--repository",
        default="natuki53/YouTube_Discord_Bot",
    )
    return parser.parse_args()


def load_or_create_secret(secret_file: Path) -> str:
    secret_file.parent.mkdir(parents=True, exist_ok=True)
    if secret_file.exists():
        secret = secret_file.read_text(encoding="utf-8").strip()
        if len(secret) < 32:
            raise ValueError(f"{secret_file} contains an invalid secret")
        return secret

    secret = secrets.token_hex(32)
    secret_file.write_text(f"{secret}\n", encoding="utf-8")
    secret_file.chmod(0o600)
    return secret


def build_hook(secret: str, repository: str) -> dict:
    return {
        "id": HOOK_ID,
        "execute-command": "/app/youtube-bot-trigger.sh",
        "response-message": "Deployment accepted.",
        "trigger-rule": {
            "and": [
                {
                    "match": {
                        "type": "payload-hmac-sha256",
                        "secret": secret,
                        "parameter": {
                            "source": "header",
                            "name": "X-Hub-Signature-256",
                        },
                    }
                },
                {
                    "match": {
                        "type": "value",
                        "value": "push",
                        "parameter": {
                            "source": "header",
                            "name": "X-GitHub-Event",
                        },
                    }
                },
                {
                    "match": {
                        "type": "value",
                        "value": "refs/heads/main",
                        "parameter": {
                            "source": "payload",
                            "name": "ref",
                        },
                    }
                },
                {
                    "match": {
                        "type": "value",
                        "value": repository,
                        "parameter": {
                            "source": "payload",
                            "name": "repository.full_name",
                        },
                    }
                },
            ]
        },
    }


def update_hooks(hooks_file: Path, hook: dict) -> bool:
    hooks = json.loads(hooks_file.read_text(encoding="utf-8"))
    if not isinstance(hooks, list):
        raise ValueError(f"{hooks_file} must contain a JSON array")

    updated_hooks = [hook if item.get("id") == HOOK_ID else item for item in hooks]
    if not any(item.get("id") == HOOK_ID for item in hooks):
        updated_hooks.append(hook)

    if updated_hooks == hooks:
        return False

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = hooks_file.with_name(f"{hooks_file.name}.backup-{timestamp}")
    shutil.copy2(hooks_file, backup)

    temporary = hooks_file.with_name(f".{hooks_file.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(updated_hooks, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    os.replace(temporary, hooks_file)
    return True


def main() -> None:
    args = parse_args()
    secret = load_or_create_secret(args.secret_file)

    shutil.copy2(args.trigger_source, args.trigger_destination)
    args.trigger_destination.chmod(0o755)

    changed = update_hooks(
        args.hooks_file,
        build_hook(secret=secret, repository=args.repository),
    )
    state = "updated" if changed else "already configured"
    print(f"{HOOK_ID}: {state}")
    print("Restart the webhook receiver, then configure GitHub with the secret file.")


if __name__ == "__main__":
    main()
