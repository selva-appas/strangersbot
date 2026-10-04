import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _parse_admin_ids(raw: str | None) -> set[int]:
    if not raw:
        return set()
    result: set[int] = set()
    for item in raw.split(","):
        cleaned = item.strip()
        if cleaned:
            try:
                result.add(int(cleaned))
            except ValueError:
                continue
    return result


@dataclass(frozen=True)
class Settings:
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    ADMIN_IDS: set[int] = field(default_factory=lambda: _parse_admin_ids(os.getenv("ADMIN_IDS")))
    BOT_DB_PATH: str = os.getenv("BOT_DB_PATH", str(BASE_DIR / "bot.db"))
    BOT_NAME: str = "StrangerMatch"


settings = Settings()
