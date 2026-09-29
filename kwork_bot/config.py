import os
from dataclasses import dataclass

from dotenv import load_dotenv

MIN_CHECK_INTERVAL = 30


@dataclass(frozen=True)
class Settings:
    bot_token: str
    check_interval: int
    allowed_users: frozenset[int]
    db_path: str
    kwork_proxy: str | None


def _parse_allowed_users(raw: str) -> frozenset[int]:
    ids = set()
    for part in raw.replace(" ", "").split(","):
        if not part:
            continue
        if not part.lstrip("-").isdigit():
            raise ValueError(f"ALLOWED_USERS: «{part}» не похоже на Telegram ID")
        ids.add(int(part))
    return frozenset(ids)


def load_settings() -> Settings:
    load_dotenv()

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Не задан BOT_TOKEN — скопируйте .env.example в .env и впишите токен")

    interval = int(os.getenv("CHECK_INTERVAL", "60"))

    return Settings(
        bot_token=token,
        check_interval=max(interval, MIN_CHECK_INTERVAL),
        allowed_users=_parse_allowed_users(os.getenv("ALLOWED_USERS", "")),
        db_path=os.getenv("DB_PATH", "kwork_bot.db").strip() or "kwork_bot.db",
        kwork_proxy=os.getenv("KWORK_PROXY", "").strip() or None,
    )
