from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config import settings


class DatabaseManager:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.BOT_DB_PATH
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_user_id INTEGER UNIQUE NOT NULL,
                    nickname TEXT,
                    date_of_birth TEXT,
                    gender TEXT,
                    city TEXT,
                    profile_photo_file_id TEXT,
                    min_age INTEGER,
                    max_age INTEGER,
                    preferred_gender TEXT,
                    preferred_location TEXT,
                    mode TEXT,
                    active INTEGER DEFAULT 0,
                    partner_id INTEGER,
                    banned INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT,
                    age_verified_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS blocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    blocker_id INTEGER NOT NULL,
                    blocked_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reporter_id INTEGER NOT NULL,
                    reported_id INTEGER NOT NULL,
                    reason TEXT,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS moderation_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER NOT NULL,
                    target_user_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rate_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_user_id INTEGER UNIQUE NOT NULL,
                    context_data TEXT DEFAULT '{}'
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_users_telegram_user_id ON users(telegram_user_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_blocks_pair ON blocks(blocker_id, blocked_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status, created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rate_events_user ON rate_events(user_id, event_type, created_at)"
            )
            self.migrate_legacy_schema(conn)

    def migrate_legacy_schema(self, conn: sqlite3.Connection) -> None:
        schema = conn.execute("PRAGMA table_info(users)").fetchall()
        columns = {row[1] for row in schema}
        required = [
            "date_of_birth",
            "age_verified_at",
            "profile_photo_file_id",
            "preferred_location",
            "min_age",
            "max_age",
            "preferred_gender",
            "mode",
            "partner_id",
        ]
        for column in required:
            if column not in columns:
                conn.execute(f"ALTER TABLE users ADD COLUMN {column} TEXT")
        if "age" in columns and "date_of_birth" in columns:
            conn.execute(
                "UPDATE users SET age_verified_at = NULL WHERE age_verified_at IS NULL AND date_of_birth IS NULL"
            )
        if "age" in columns and "date_of_birth" not in columns:
            conn.execute(
                "UPDATE users SET date_of_birth = NULL, age_verified_at = NULL WHERE telegram_user_id IS NOT NULL"
            )

    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def get_user_by_telegram_id(self, telegram_user_id: int):
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT * FROM users WHERE telegram_user_id = ?",
                (telegram_user_id,),
            ).fetchone()

    def upsert_user_profile(self, telegram_user_id: int, profile: dict) -> None:
        now = self.now_iso()
        existing = self.get_user_by_telegram_id(telegram_user_id)
        if existing:
            with self.get_connection() as conn:
                conn.execute(
                    """
                    UPDATE users
                    SET nickname = ?, date_of_birth = ?, gender = ?, city = ?, profile_photo_file_id = ?,
                        min_age = ?, max_age = ?, preferred_gender = ?, preferred_location = ?, mode = ?,
                        updated_at = ?, age_verified_at = ?, active = ?, partner_id = COALESCE(partner_id, NULL)
                    WHERE telegram_user_id = ?
                    """,
                    (
                        profile.get("nickname"),
                        profile.get("date_of_birth"),
                        profile.get("gender"),
                        profile.get("city"),
                        profile.get("profile_photo_file_id"),
                        profile.get("min_age"),
                        profile.get("max_age"),
                        profile.get("preferred_gender"),
                        profile.get("preferred_location"),
                        profile.get("mode"),
                        now,
                        profile.get("age_verified_at"),
                        profile.get("active", 1),
                        telegram_user_id,
                    ),
                )
            return
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    telegram_user_id, nickname, date_of_birth, gender, city, profile_photo_file_id,
                    min_age, max_age, preferred_gender, preferred_location, mode, active, partner_id,
                    banned, created_at, updated_at, age_verified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, NULL, 0, ?, ?, ?)
                """,
                (
                    telegram_user_id,
                    profile.get("nickname"),
                    profile.get("date_of_birth"),
                    profile.get("gender"),
                    profile.get("city"),
                    profile.get("profile_photo_file_id"),
                    profile.get("min_age"),
                    profile.get("max_age"),
                    profile.get("preferred_gender"),
                    profile.get("preferred_location"),
                    profile.get("mode"),
                    now,
                    now,
                    profile.get("age_verified_at"),
                ),
            )

    def record_report(self, reporter_id: int, reported_id: int, reason: str) -> None:
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO reports (reporter_id, reported_id, reason, created_at, status) VALUES (?, ?, ?, ?, 'pending')",
                (reporter_id, reported_id, reason, self.now_iso()),
            )

    def get_reports(self, limit: int = 20):
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT * FROM reports ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

    def get_pending_reports(self):
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT * FROM reports WHERE status = 'pending' ORDER BY created_at DESC"
            ).fetchall()

    def get_user_count(self) -> int:
        with self.get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def get_active_user_count(self) -> int:
        with self.get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM users WHERE active = 1").fetchone()[0]

    def get_matched_user_count(self) -> int:
        with self.get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM users WHERE partner_id IS NOT NULL").fetchone()[0]

    def get_banned_user_count(self) -> int:
        with self.get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM users WHERE banned = 1").fetchone()[0]

    def set_ban(self, telegram_user_id: int, banned: int) -> None:
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE users SET banned = ?, updated_at = ? WHERE telegram_user_id = ?",
                (banned, self.now_iso(), telegram_user_id),
            )

    def set_active(self, telegram_user_id: int, value: int) -> None:
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE users SET active = ?, updated_at = ? WHERE telegram_user_id = ?",
                (value, self.now_iso(), telegram_user_id),
            )

    def set_partner(self, telegram_user_id: int, partner_id: int | None) -> None:
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE users SET partner_id = ?, updated_at = ? WHERE telegram_user_id = ?",
                (partner_id, self.now_iso(), telegram_user_id),
            )

    def add_block(self, blocker_id: int, blocked_id: int) -> None:
        with self.get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO blocks (blocker_id, blocked_id, created_at) VALUES (?, ?, ?)",
                (blocker_id, blocked_id, self.now_iso()),
            )

    def has_blocked(self, user_a: int, user_b: int) -> bool:
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM blocks WHERE (blocker_id = ? AND blocked_id = ?) OR (blocker_id = ? AND blocked_id = ?)",
                (user_a, user_b, user_b, user_a),
            ).fetchone()
            return row is not None

    def delete_user_profile(self, telegram_user_id: int) -> None:
        with self.get_connection() as conn:
            conn.execute("DELETE FROM blocks WHERE blocker_id = ? OR blocked_id = ?", (telegram_user_id, telegram_user_id))
            conn.execute("DELETE FROM reports WHERE reporter_id = ? OR reported_id = ?", (telegram_user_id, telegram_user_id))
            conn.execute("DELETE FROM rate_events WHERE user_id = ?", (telegram_user_id,))
            conn.execute("DELETE FROM users WHERE telegram_user_id = ?", (telegram_user_id,))

    def record_moderation_action(self, admin_id: int, target_user_id: int, action: str, reason: str | None = None) -> None:
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO moderation_actions (admin_id, target_user_id, action, reason, created_at) VALUES (?, ?, ?, ?, ?)",
                (admin_id, target_user_id, action, reason, self.now_iso()),
            )

    def get_all_users(self):
        with self.get_connection() as conn:
            return conn.execute("SELECT * FROM users").fetchall()

    def get_by_telegram_id(self, telegram_user_id: int):
        return self.get_user_by_telegram_id(telegram_user_id)


db = DatabaseManager()
