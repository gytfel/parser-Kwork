import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import BotCommand

from kwork_bot.config import Settings
from kwork_bot.handlers import AccessMiddleware, router
from kwork_bot.kwork import KworkClient
from kwork_bot.monitor import Monitor
from kwork_bot.storage import Storage

logger = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="start", description="Запустить бота"),
    BotCommand(command="latest", description="Последние заказы"),
    BotCommand(command="categories", description="Выбрать категории"),
    BotCommand(command="notify", description="Включить/выключить уведомления"),
    BotCommand(command="help", description="Помощь"),
]


async def run_bot(settings: Settings) -> None:
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    storage = Storage(settings.db_path)
    client = KworkClient(proxy=settings.kwork_proxy)
    monitor = Monitor(bot, storage, client, settings.check_interval)

    dp = Dispatcher()
    dp["storage"] = storage
    dp["monitor"] = monitor
    access = AccessMiddleware(settings.allowed_users)
    dp.message.outer_middleware(access)
    dp.callback_query.outer_middleware(access)
    dp.include_router(router)

    monitor_task: asyncio.Task | None = None
    try:
        await storage.connect()
        me = await bot.get_me()
        logger.info("Бот @%s запущен. Остановить — Ctrl+C", me.username)
        if settings.allowed_users:
            logger.info("Доступ открыт только для: %s", ", ".join(map(str, settings.allowed_users)))
        with contextlib.suppress(TelegramNetworkError):
            await bot.set_my_commands(COMMANDS)

        monitor_task = asyncio.create_task(monitor.run())
        await dp.start_polling(bot)
    finally:
        if monitor_task is not None:
            monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await monitor_task
        await client.close()
        await storage.close()
        await bot.session.close()
