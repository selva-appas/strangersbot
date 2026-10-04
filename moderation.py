from __future__ import annotations

from typing import Iterable

from database import db
from safety import safety_warning


def contains_suspicious_content(text: str | None) -> bool:
    if not text:
        return False
    lowered = text.lower()
    suspicious_phrases = [
        "send money",
        "pay me",
        "investment",
        "otp",
        "bank account",
        "i need help with a payment",
        "bitcoin",
        "crypto",
        "wallet",
        "deposit",
        "buy me",
        "refund",
        "gift card",
    ]
    return any(phrase in lowered for phrase in suspicious_phrases)


def moderation_warning() -> str:
    return safety_warning()


def admin_stats() -> dict:
    return {
        "total_users": db.get_user_count(),
        "active_users": db.get_active_user_count(),
        "currently_matched": db.get_matched_user_count(),
        "banned_users": db.get_banned_user_count(),
        "total_reports": len(db.get_reports(limit=1000)),
        "pending_reports": len(db.get_pending_reports()),
    }


def list_recent_reports(limit: int = 20):
    return db.get_reports(limit=limit)
