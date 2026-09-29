"""Запуск из терминала: python -m kwork_bot [run|setup|check]."""

import argparse
import asyncio
import logging
import sys

from aiogram import Bot
from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError
from aiogram.utils.token import TokenValidationError

from kwork_bot.app import run_bot
from kwork_bot.categories import CATEGORIES
from kwork_bot.config import ConfigError, MissingTokenError, Settings, load_settings
from kwork_bot.formatting import shorten
from kwork_bot.kwork import KworkClient, KworkError
from kwork_bot.setup_wizard import run_setup


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m kwork_bot",
        description="Telegram-бот с новыми проектами Kwork. Без команды — запуск бота.",
    )
    sub = parser.add_subparsers(dest="command", metavar="команда")
    sub.add_parser("run", help="запустить бота (по умолчанию)")
    setup = sub.add_parser("setup", help="указать токен и кому доступен бот")
    setup.add_argument("--token", help="токен от @BotFather (без вопросов)")
    setup.add_argument(
        "--allowed-users",
        help="Telegram ID через запятую; пустая строка — доступ для всех",
    )
    sub.add_parser("check", help="проверить связь с Telegram и Kwork")
    return parser


async def run_check(settings: Settings) -> bool:
    ok = True

    print("Telegram:")
    try:
        async with Bot(settings.bot_token) as bot:
            me = await bot.get_me()
        print(f"  ✓ бот @{me.username} на связи")
    except (TelegramUnauthorizedError, TokenValidationError):
        print("  ✗ Telegram не принял BOT_TOKEN — пройдите настройку заново (setup)")
        ok = False
    except TelegramNetworkError as e:
        print(f"  ✗ нет связи с api.telegram.org: {e}")
        ok = False

    print("Kwork:")
    kwork_ok = True
    client = KworkClient(proxy=settings.kwork_proxy)
    try:
        for i, category in enumerate(CATEGORIES):
            if i:
                await asyncio.sleep(1)
            try:
                orders = await client.fetch_orders(category)
            except KworkError as e:
                print(f"  ✗ {category.title}: {e}")
                kwork_ok = False
                continue
            if orders:
                newest = max(orders, key=lambda o: o.id)
                print(f"  ✓ {category.title}: {len(orders)} шт., свежий — «{shorten(newest.title, 50)}»")
            else:
                print(f"  ✓ {category.title}: сейчас проектов нет")
    finally:
        await client.close()

    if not kwork_ok:
        print(
            "\nKwork не отвечает. Если сервер не в России, Kwork может его блокировать —\n"
            "укажите прокси в KWORK_PROXY в файле .env (например, http://user:pass@host:port)."
        )
    return ok and kwork_ok


def _load_or_setup(allow_setup: bool) -> Settings:
    try:
        return load_settings()
    except MissingTokenError:
        if not (allow_setup and sys.stdin.isatty()):
            raise

    print("Бот ещё не настроен — давайте настроим.\n")
    run_setup()
    print()
    return load_settings(override=True)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "run"

    try:
        if command == "setup":
            run_setup(token=args.token, allowed_users=args.allowed_users)
            return 0

        settings = _load_or_setup(allow_setup=command == "run")
        if command == "check":
            return 0 if asyncio.run(run_check(settings)) else 1

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        asyncio.run(run_bot(settings))
    except ConfigError as e:
        print(f"Ошибка настроек: {e}\nНастроить: python -m kwork_bot setup", file=sys.stderr)
        return 2
    except (TelegramUnauthorizedError, TokenValidationError):
        print(
            "Telegram не принял BOT_TOKEN. Проверьте токен: python -m kwork_bot setup",
            file=sys.stderr,
        )
        return 2
    except TelegramNetworkError as e:
        print(f"Нет связи с Telegram ({e}). Проверьте интернет на сервере.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nОстановлено.")
    return 0
