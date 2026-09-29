import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from kwork_bot.config import load_settings
from kwork_bot.handlers import AccessMiddleware, router
from kwork_bot.kwork import KworkClient
from kwork_bot.monitor import Monitor
from kwork_bot.storage import Storage

COMMANDS = [
    BotCommand(command="start", description="Запустить бота"),
    BotCommand(command="latest", description="Последние заказы"),
    BotCommand(command="categories", description="Выбрать категории"),
    BotCommand(command="notify", description="Включить/выключить уведомления"),
    BotCommand(command="help", description="Помощь"),
]


async def main() -> None:
    settings = load_settings()

    storage = Storage(settings.db_path)
    await storage.connect()
    client = KworkClient(proxy=settings.kwork_proxy)
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    monitor = Monitor(bot, storage, client, settings.check_interval)

    dp = Dispatcher()
    dp["storage"] = storage
    dp["monitor"] = monitor
    access = AccessMiddleware(settings.allowed_users)
    dp.message.outer_middleware(access)
    dp.callback_query.outer_middleware(access)
    dp.include_router(router)

    await bot.set_my_commands(COMMANDS)
    monitor_task = asyncio.create_task(monitor.run())
    try:
        await dp.start_polling(bot)
    finally:
        monitor_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await monitor_task
        await client.close()
        await storage.close()
        await bot.session.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(main())
