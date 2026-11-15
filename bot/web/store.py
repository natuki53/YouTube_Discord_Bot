"""セッショントークンはハッシュ、OAuthトークンは暗号化して保存する。"""

import hashlib
import json
import os
import secrets
import sqlite3
import time

from cryptography.fernet import Fernet


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class WebStore:
    def __init__(self, path, key):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=1)
        os.chmod(path, 0o600)
        self.cipher = Fernet(key.encode())
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, data BLOB NOT NULL, expires REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS oauth_states (
                id TEXT PRIMARY KEY, expires REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id TEXT PRIMARY KEY, channel_id TEXT
            );
        """)

    def new_state(self):
        state = secrets.token_urlsafe(32)
        with self.db:
            self.db.execute(
                "DELETE FROM oauth_states WHERE expires < ?", (time.time(),)
            )
            self.db.execute(
                "INSERT INTO oauth_states VALUES (?, ?)",
                (digest(state), time.time() + 600),
            )
        return state

    def consume_state(self, state):
        with self.db:
            row = self.db.execute(
                "DELETE FROM oauth_states WHERE id=? AND expires>? RETURNING id",
                (digest(state), time.time()),
            ).fetchone()
        return row is not None

    def create_session(self, data, seconds):
        token = secrets.token_urlsafe(32)
        data = dict(data, csrf=secrets.token_urlsafe(32))
        self.save_session(token, data, time.time() + seconds)
        with self.db:
            self.db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
        return token

    def save_session(self, token, data, expires):
        encrypted = self.cipher.encrypt(json.dumps(data).encode())
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO sessions VALUES (?, ?, ?)",
                (digest(token), encrypted, expires),
            )

    def session(self, token):
        row = self.db.execute(
            "SELECT * FROM sessions WHERE id=? AND expires>?",
            (digest(token), time.time()),
        ).fetchone()
        if not row:
            return None
        return json.loads(self.cipher.decrypt(row["data"])), row["expires"]

    def delete_session(self, token):
        with self.db:
            self.db.execute("DELETE FROM sessions WHERE id=?", (digest(token),))

    def channel(self, guild_id):
        row = self.db.execute(
            "SELECT channel_id FROM guild_settings WHERE guild_id=?", (str(guild_id),)
        ).fetchone()
        return row[0] if row else None

    def set_channel(self, guild_id, channel_id):
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO guild_settings VALUES (?, ?)",
                (str(guild_id), channel_id),
            )

    def close(self):
        self.db.close()
