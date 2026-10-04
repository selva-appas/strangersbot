from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from config import settings


class RateLimiter:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.BOT_DB_PATH

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def record_event(self, user_id: int, event_type: str) -> None:
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO rate_events (user_id, event_type, created_at) VALUES (?, ?, ?)",
                (user_id, event_type, datetime.now(timezone.utc).isoformat()),
            )

    def count_recent(self, user_id: int, event_type: str, window_seconds: int) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=window_seconds)).isoformat()
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM rate_events WHERE user_id = ? AND event_type = ? AND created_at >= ?",
                (user_id, event_type, cutoff),
            ).fetchone()
            return int(row["count"])

    def is_allowed(self, user_id: int, event_type: str, max_per_window: int, window_seconds: int) -> bool:
        return self.count_recent(user_id, event_type, window_seconds) < max_per_window


rate_limiter = RateLimiter()
