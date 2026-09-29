import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

MIN_CHECK_INTERVAL = 30

# Папка проекта (где лежат kwork_bot/, .env и база) — не зависит от того,
# из какой папки запущен бот.
PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_DIR / ".env"


class ConfigError(Exception):
    """Настройки не заданы или заданы с ошибкой."""


class MissingTokenError(ConfigError):
    """Бот ещё не настроен: нет BOT_TOKEN."""


@dataclass(frozen=True)
class Settings:
    bot_token: str
    check_interval: int
    allowed_users: frozenset[int]
    db_path: str
    kwork_proxy: str | None


def parse_allowed_users(raw: str) -> frozenset[int]:
    ids = set()
    for part in raw.replace(" ", "").split(","):
        if not part:
            continue
        if not part.lstrip("-").isdigit():
            raise ConfigError(f"ALLOWED_USERS: «{part}» не похоже на Telegram ID")
        ids.add(int(part))
    return frozenset(ids)


def load_settings(env_file: Path = ENV_FILE, override: bool = False) -> Settings:
    load_dotenv(env_file, override=override)

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise MissingTokenError(f"не задан BOT_TOKEN в {env_file}")

    try:
        interval = int(os.getenv("CHECK_INTERVAL", "60"))
    except ValueError:
        raise ConfigError("CHECK_INTERVAL должен быть числом секунд") from None

    db_path = Path(os.getenv("DB_PATH", "").strip() or "kwork_bot.db")
    if not db_path.is_absolute():
        db_path = env_file.parent / db_path

    return Settings(
        bot_token=token,
        check_interval=max(interval, MIN_CHECK_INTERVAL),
        allowed_users=parse_allowed_users(os.getenv("ALLOWED_USERS", "")),
        db_path=str(db_path),
        kwork_proxy=os.getenv("KWORK_PROXY", "").strip() or None,
    )
