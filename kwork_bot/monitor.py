"""Фоновая проверка Kwork и рассылка новых проектов."""

import asyncio
import logging
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter

from kwork_bot.categories import CATEGORIES, CATEGORY_BY_KEY, Category
from kwork_bot.formatting import format_order
from kwork_bot.keyboards import order_kb
from kwork_bot.kwork import KworkClient, KworkError, Order
from kwork_bot.storage import Storage

logger = logging.getLogger(__name__)

# Пауза между запросами к разным подкатегориям — не долбим Kwork залпом.
REQUEST_PAUSE = 1.5
# Пауза между сообщениями в Telegram, чтобы не упереться в лимиты.
SEND_PAUSE = 0.1
# Если категорию не проверяли дольше этого (бот был выключен, Kwork не отвечал),
# проекты на странице считаем старыми и не рассылаем, а просто запоминаем.
MIN_STALE_AFTER = timedelta(minutes=15)
PRUNE_EVERY = timedelta(hours=6)


def _sort_key(order: Order) -> tuple[datetime, int]:
    published = order.published_at or datetime.min.replace(tzinfo=timezone.utc)
    return published, order.id


class Monitor:
    def __init__(self, bot: Bot, storage: Storage, client: KworkClient, interval: int) -> None:
        self.bot = bot
        self.storage = storage
        self.client = client
        self.interval = interval
        self.stale_after = max(timedelta(seconds=interval * 5), MIN_STALE_AFTER)
        # Последняя успешно полученная страница каждой подкатегории — для «Последних заказов».
        self.latest: dict[str, list[Order]] = {}
        self._last_prune: datetime | None = None

    async def run(self) -> None:
        logger.info("Мониторинг запущен, интервал %s с", self.interval)
        while True:
            try:
                await self.check_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Ошибка в цикле мониторинга")
            await asyncio.sleep(self.interval)

    async def check_once(self) -> dict[str, list[Order]]:
        new_orders: dict[str, list[Order]] = {}
        for i, category in enumerate(CATEGORIES):
            if i:
                await asyncio.sleep(REQUEST_PAUSE)
            try:
                orders = await self.client.fetch_orders(category)
            except KworkError as e:
                logger.warning("Kwork, «%s»: %s", category.name, e)
                continue
            self.latest[category.key] = orders
            fresh = await self._pick_new(category, orders)
            if fresh:
                logger.info("«%s»: новых проектов — %d", category.name, len(fresh))
                new_orders[category.key] = fresh

        if new_orders:
            await self._notify(new_orders)
        await self._maybe_prune()
        return new_orders

    async def _pick_new(self, category: Category, orders: list[Order]) -> list[Order]:
        last_checked = await self.storage.get_last_checked(category.key)
        unseen = await self.storage.filter_unseen(category.key, (o.id for o in orders))
        await self.storage.mark_seen(category.key, unseen)
        await self.storage.set_last_checked(category.key)

        now = datetime.now(timezone.utc)
        if last_checked is None or now - last_checked > self.stale_after:
            # Первый запуск или долгий перерыв: не заваливаем пользователя всей лентой.
            if unseen:
                logger.info("«%s»: запомнил %d текущих проектов", category.name, len(unseen))
            return []
        return sorted((o for o in orders if o.id in unseen), key=_sort_key)

    async def _notify(self, new_orders: dict[str, list[Order]]) -> None:
        recipients = await self.storage.get_recipients()
        for user_id, keys in recipients.items():
            orders = self._merge(new_orders.get(key, []) for key in keys)
            for order in sorted(orders, key=_sort_key):
                if not await self.send_order(user_id, order):
                    break

    async def send_order(self, chat_id: int, order: Order, *, is_new: bool = True) -> bool:
        """Отправляет проект. False — пользователь заблокировал бота."""
        text = format_order(order, is_new=is_new)
        for attempt in range(2):
            try:
                await self.bot.send_message(
                    chat_id,
                    text,
                    reply_markup=order_kb(order.url),
                    disable_web_page_preview=True,
                )
                break
            except TelegramRetryAfter as e:
                if attempt:
                    logger.warning("Telegram просит подождать, пропускаю проект %s", order.id)
                    break
                await asyncio.sleep(e.retry_after)
            except TelegramForbiddenError:
                logger.info("Пользователь %s заблокировал бота — выключаю уведомления", chat_id)
                await self.storage.set_notify(chat_id, False)
                return False
            except TelegramAPIError as e:
                logger.warning("Не удалось отправить проект %s в %s: %s", order.id, chat_id, e)
                break
        await asyncio.sleep(SEND_PAUSE)
        return True

    async def get_latest(self, category_keys: Iterable[str], limit: int = 5) -> list[Order]:
        """Свежие проекты по выбранным категориям, самые новые первыми."""
        pages = []
        for key in category_keys:
            if key not in self.latest and key in CATEGORY_BY_KEY:
                try:
                    self.latest[key] = await self.client.fetch_orders(CATEGORY_BY_KEY[key])
                except KworkError as e:
                    logger.warning("Kwork, «%s»: %s", CATEGORY_BY_KEY[key].name, e)
                    continue
            pages.append(self.latest.get(key, []))
        return sorted(self._merge(pages), key=_sort_key, reverse=True)[:limit]

    @staticmethod
    def _merge(pages: Iterable[list[Order]]) -> list[Order]:
        # Один проект может оказаться в нескольких подкатегориях — шлём его один раз.
        merged: dict[int, Order] = {}
        for page in pages:
            for order in page:
                merged.setdefault(order.id, order)
        return list(merged.values())

    async def _maybe_prune(self) -> None:
        now = datetime.now(timezone.utc)
        if self._last_prune is None or now - self._last_prune > PRUNE_EVERY:
            await self.storage.prune_seen()
            self._last_prune = now
