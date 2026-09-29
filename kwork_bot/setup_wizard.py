"""Мастер настройки: спрашивает токен и Telegram ID и записывает их в .env."""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramNetworkError,
    TelegramUnauthorizedError,
)
from aiogram.types import User
from aiogram.utils.token import TokenValidationError
from dotenv import dotenv_values

from kwork_bot.config import ENV_FILE, ConfigError, parse_allowed_users

DETECT_TIMEOUT = 120

YES = {"", "д", "да", "y", "yes"}
NO = {"н", "нет", "n", "no"}


def update_env_text(text: str, values: dict[str, str]) -> str:
    """Проставляет значения ключей в тексте .env, сохраняя остальные строки и комментарии."""
    lines = text.splitlines()
    remaining = dict(values)
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key in remaining:
            lines[i] = f"{key}={remaining.pop(key)}"
    lines += [f"{key}={value}" for key, value in remaining.items()]
    return "\n".join(lines) + "\n"


def write_env(values: dict[str, str], env_file: Path = ENV_FILE) -> None:
    example = env_file.parent / ".env.example"
    if env_file.exists():
        text = env_file.read_text("utf-8")
    elif example.exists():
        text = example.read_text("utf-8")
    else:
        text = ""
    env_file.write_text(update_env_text(text, values), "utf-8")
    try:
        env_file.chmod(0o600)  # в файле токен — читать его может только владелец
    except OSError:
        pass


async def fetch_bot_username(token: str) -> str:
    async with Bot(token) as bot:
        me = await bot.get_me()
    return me.username or str(me.id)


async def detect_user(token: str, timeout: float = DETECT_TIMEOUT) -> User | None:
    """Ждёт, пока кто-нибудь напишет боту, и возвращает автора сообщения."""
    started = datetime.now(timezone.utc) - timedelta(seconds=5)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    offset = None
    async with Bot(token) as bot:
        while loop.time() < deadline:
            for update in await bot.get_updates(offset=offset, timeout=10):
                offset = update.update_id + 1
                message = update.message
                # Старые сообщения из очереди пропускаем — нужен именно тот, кто пишет сейчас.
                if message and message.from_user and message.date >= started:
                    return message.from_user
    return None


def ask_yes_no(question: str, default: bool = True) -> bool:
    hint = "[Д/н]" if default else "[д/Н]"
    while True:
        answer = input(f"{question} {hint}: ").strip().lower()
        if not answer:
            return default
        if answer in YES:
            return True
        if answer in NO:
            return False
        print("  Ответьте «д» или «н».")


def ask_token(current: str) -> tuple[str, str | None]:
    print(
        "Шаг 1. Токен бота.\n"
        "  Откройте @BotFather в Telegram, отправьте /newbot и следуйте подсказкам.\n"
        "  В конце он пришлёт токен вида 123456789:AAH... — вставьте его сюда."
    )
    while True:
        prompt = "Токен (Enter — оставить текущий): " if current else "Токен: "
        token = input(prompt).strip() or current
        if not token:
            continue
        try:
            username = asyncio.run(fetch_bot_username(token))
        except TokenValidationError:
            print("  ✗ Это не похоже на токен. Скопируйте его из @BotFather целиком.")
            continue
        except TelegramUnauthorizedError:
            print("  ✗ Telegram не принял токен. Проверьте, что скопировали его целиком.")
            continue
        except TelegramNetworkError as e:
            print(f"  ✗ Нет связи с Telegram, токен не проверить: {e}")
            if ask_yes_no("  Всё равно сохранить этот токен?", default=False):
                print()
                return token, None
            continue
        print(f"  ✓ Бот @{username} найден.\n")
        return token, username


def ask_allowed_users(token: str, username: str | None, current: str) -> str:
    print("Шаг 2. Кто может пользоваться ботом.")
    if current:
        print(f"  Сейчас доступ только у: {current}")
        if ask_yes_no("  Оставить так?"):
            return current
    if not ask_yes_no("  Разрешить бота только вам?"):
        return ""

    if username:
        user = None
        print(
            f"  Откройте @{username} в Telegram и отправьте ему /start.\n"
            f"  Жду до {DETECT_TIMEOUT // 60} минут (Ctrl+C — ввести ID вручную)…"
        )
        try:
            user = asyncio.run(detect_user(token))
        except KeyboardInterrupt:
            print()
        except TelegramAPIError as e:
            # Например, этот же бот уже запущен где-то ещё и забирает сообщения.
            print(f"  Не получилось определить автоматически: {e}")
        if user:
            name = user.full_name + (f" (@{user.username})" if user.username else "")
            if ask_yes_no(f"  Это вы: {name}, ID {user.id}?"):
                return str(user.id)

    while True:
        raw = input(
            "  Ваш Telegram ID (узнать можно у @userinfobot; несколько — через запятую): "
        ).strip()
        try:
            if parse_allowed_users(raw):
                return raw.replace(" ", "")
        except ConfigError as e:
            print(f"  ✗ {e}")


def run_setup(
    token: str | None = None,
    allowed_users: str | None = None,
    env_file: Path = ENV_FILE,
) -> None:
    """Интерактивная настройка. Значения, переданные аргументами, не спрашиваются."""
    interactive = sys.stdin.isatty()
    current = {k: (v or "") for k, v in dotenv_values(env_file).items()} if env_file.exists() else {}

    print("=== Настройка бота Kwork ===\n")
    username = None
    if token is None:
        if not interactive:
            raise ConfigError("не передан токен: setup --token <токен>")
        token, username = ask_token(current.get("BOT_TOKEN", ""))

    if allowed_users is None:
        allowed_users = (
            ask_allowed_users(token, username, current.get("ALLOWED_USERS", ""))
            if interactive
            else ""
        )
    allowed_users = allowed_users.replace(" ", "")
    parse_allowed_users(allowed_users)

    write_env({"BOT_TOKEN": token, "ALLOWED_USERS": allowed_users}, env_file)
    print(f"\n✓ Настройки сохранены в {env_file}")
    if allowed_users:
        print(f"  Доступ к боту только у: {allowed_users}")
    else:
        print("  Бот доступен всем, кто его найдёт.")
