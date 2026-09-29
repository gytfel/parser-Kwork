from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from kwork_bot.categories import CATEGORIES, CATEGORY_BY_KEY, PARENT_CATEGORY_NAME
from kwork_bot.keyboards import (
    BTN_CATEGORIES,
    BTN_HELP,
    BTN_LATEST,
    BTN_NOTIFY,
    CategoryCb,
    NotifyCb,
    categories_kb,
    main_menu,
    notify_kb,
)
from kwork_bot.monitor import Monitor
from kwork_bot.storage import Storage

router = Router(name="main")

ALL_KEYS = [c.key for c in CATEGORIES]

HELP_TEXT = (
    "Я слежу за биржей <b>Kwork</b>, раздел «{parent}», и присылаю новые проекты, "
    "как только они появляются.\n\n"
    "{categories}\n\n"
    "<b>Кнопки:</b>\n"
    "{latest} — свежие проекты по выбранным категориям прямо сейчас\n"
    "{cats} — какие подкатегории отслеживать\n"
    "{notify} — включить или выключить уведомления\n\n"
    "Проверка идёт каждые {interval} с."
)


class AccessMiddleware(BaseMiddleware):
    """Пускает только пользователей из ALLOWED_USERS (если список задан)."""

    def __init__(self, allowed: frozenset[int]) -> None:
        self.allowed = allowed

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if not self.allowed or (user and user.id in self.allowed):
            return await handler(event, data)

        text = f"⛔ Доступ закрыт.\nВаш Telegram ID: <code>{user.id if user else '?'}</code>"
        if isinstance(event, Message):
            await event.answer(text)
        elif isinstance(event, CallbackQuery):
            await event.answer("⛔ Доступ закрыт", show_alert=True)
        return None


def _categories_text(selected: set[str]) -> str:
    chosen = [c.title for c in CATEGORIES if c.key in selected]
    if not chosen:
        return "Сейчас не выбрано ни одной категории — уведомлений не будет."
    return "<b>Отслеживаю:</b>\n" + "\n".join(chosen)


def _help_text(selected: set[str], interval: int) -> str:
    return HELP_TEXT.format(
        parent=PARENT_CATEGORY_NAME,
        categories=_categories_text(selected),
        latest=BTN_LATEST,
        cats=BTN_CATEGORIES,
        notify=BTN_NOTIFY,
        interval=interval,
    )


@router.message(CommandStart())
async def cmd_start(message: Message, storage: Storage, monitor: Monitor) -> None:
    user_id = message.from_user.id
    is_new = await storage.add_user(user_id, ALL_KEYS)
    await storage.set_notify(user_id, True)
    selected = await storage.get_subscriptions(user_id)

    greeting = "👋 Привет! " if is_new else "С возвращением! "
    await message.answer(
        greeting + _help_text(selected, monitor.interval),
        reply_markup=main_menu(),
    )


@router.message(Command("help"))
@router.message(F.text == BTN_HELP)
async def cmd_help(message: Message, storage: Storage, monitor: Monitor) -> None:
    selected = await storage.get_subscriptions(message.from_user.id)
    await message.answer(
        _help_text(selected, monitor.interval),
        reply_markup=main_menu(),
    )


@router.message(Command("latest"))
@router.message(F.text == BTN_LATEST)
async def cmd_latest(message: Message, storage: Storage, monitor: Monitor) -> None:
    await storage.add_user(message.from_user.id, ALL_KEYS)
    selected = await storage.get_subscriptions(message.from_user.id)
    if not selected:
        await message.answer(
            "Не выбрано ни одной категории. Отметьте нужные 👇",
            reply_markup=categories_kb(selected),
        )
        return

    wait = await message.answer("⏳ Загружаю проекты с Kwork…")
    orders = await monitor.get_latest(selected, limit=5)
    await wait.delete()

    if not orders:
        await message.answer(
            "Не удалось получить проекты: Kwork не ответил или в выбранных категориях пусто. "
            "Попробуйте чуть позже."
        )
        return
    for order in orders:
        await monitor.send_order(message.chat.id, order, is_new=False)


@router.message(Command("categories"))
@router.message(F.text == BTN_CATEGORIES)
async def cmd_categories(message: Message, storage: Storage) -> None:
    await storage.add_user(message.from_user.id, ALL_KEYS)
    selected = await storage.get_subscriptions(message.from_user.id)
    await message.answer(
        f"Раздел «{PARENT_CATEGORY_NAME}».\nВыберите подкатегории для отслеживания:",
        reply_markup=categories_kb(selected),
    )


@router.callback_query(CategoryCb.filter())
async def on_category(call: CallbackQuery, callback_data: CategoryCb, storage: Storage) -> None:
    user_id = call.from_user.id
    await storage.add_user(user_id, ALL_KEYS)

    if callback_data.action == "done":
        selected = await storage.get_subscriptions(user_id)
        await call.message.edit_text("✅ Сохранено.\n\n" + _categories_text(selected))
        await call.answer()
        return

    if callback_data.action == "toggle" and callback_data.key in CATEGORY_BY_KEY:
        on = await storage.toggle_subscription(user_id, callback_data.key)
        name = CATEGORY_BY_KEY[callback_data.key].name
        await call.answer(f"{name}: {'включено' if on else 'выключено'}")
    elif callback_data.action == "all":
        await storage.set_subscriptions(user_id, ALL_KEYS)
        await call.answer("Выбраны все категории")
    elif callback_data.action == "none":
        await storage.set_subscriptions(user_id, [])
        await call.answer("Все категории сняты")
    else:
        await call.answer()
        return

    selected = await storage.get_subscriptions(user_id)
    await call.message.edit_reply_markup(reply_markup=categories_kb(selected))


def _notify_text(enabled: bool) -> str:
    if enabled:
        return "🔔 Уведомления о новых проектах <b>включены</b>."
    return "🔕 Уведомления <b>выключены</b>. Кнопка «Последние заказы» при этом работает."


@router.message(Command("notify"))
@router.message(F.text == BTN_NOTIFY)
async def cmd_notify(message: Message, storage: Storage) -> None:
    await storage.add_user(message.from_user.id, ALL_KEYS)
    enabled = await storage.get_notify(message.from_user.id)
    await message.answer(_notify_text(enabled), reply_markup=notify_kb(enabled))


@router.callback_query(NotifyCb.filter())
async def on_notify(call: CallbackQuery, callback_data: NotifyCb, storage: Storage) -> None:
    await storage.add_user(call.from_user.id, ALL_KEYS)
    await storage.set_notify(call.from_user.id, callback_data.enabled)
    await call.message.edit_text(
        _notify_text(callback_data.enabled), reply_markup=notify_kb(callback_data.enabled)
    )
    await call.answer()
