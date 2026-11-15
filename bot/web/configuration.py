import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet


@dataclass(frozen=True)
class WebConfig:
    public_url: str
    client_id: str
    client_secret: str
    encryption_key: str
    database: Path = Path("data/web.sqlite3")
    static_dir: Path = Path("web/dist")
    host: str = "0.0.0.0"
    port: int = 8080
    secure_cookie: bool = True
    session_seconds: int = 604800

    def __post_init__(self):
        url = urlsplit(self.public_url)
        if url.scheme not in ("http", "https") or not url.netloc or url.path not in ("", "/") or url.query or url.fragment or url.username:
            raise ValueError("WEB_PUBLIC_URLには公開サイトのオリジンを指定してください。")
        if not self.client_id or not self.client_secret:
            raise ValueError("Discord OAuthのCLIENT_IDとCLIENT_SECRETが必要です。")
        if self.secure_cookie and url.scheme != "https":
            raise ValueError("本番のWEB_PUBLIC_URLにはHTTPSが必要です。")
        Fernet(self.encryption_key.encode())

    @property
    def redirect_uri(self):
        return self.public_url.rstrip("/") + "/auth/callback"

    @classmethod
    def from_env(cls):
        if os.getenv("WEB_ENABLED", "false").lower() != "true":
            return None
        return cls(
            public_url=os.getenv("WEB_PUBLIC_URL", "https://music.mu-natuki.com").rstrip("/"),
            client_id=os.getenv("DISCORD_CLIENT_ID", ""),
            client_secret=os.getenv("DISCORD_CLIENT_SECRET", ""),
            encryption_key=os.getenv("WEB_ENCRYPTION_KEY", ""),
            database=Path(os.getenv("WEB_DATABASE_PATH", "data/web.sqlite3")),
            static_dir=Path(os.getenv("WEB_STATIC_DIR", "web/dist")),
            host=os.getenv("WEB_HOST", "0.0.0.0"),
            port=int(os.getenv("WEB_PORT", "8080")),
        )
