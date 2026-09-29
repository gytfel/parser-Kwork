from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from kwork_bot.categories import CATEGORIES

BTN_LATEST = "📋 Последние заказы"
BTN_CATEGORIES = "🗂 Категории"
BTN_NOTIFY = "🔔 Уведомления"
BTN_HELP = "❓ Помощь"


class CategoryCb(CallbackData, prefix="cat"):
    action: str  # toggle | all | none | done
    key: str = ""


class NotifyCb(CallbackData, prefix="notify"):
    enabled: bool


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_LATEST), KeyboardButton(text=BTN_CATEGORIES)],
            [KeyboardButton(text=BTN_NOTIFY), KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
    )


def categories_kb(selected: set[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in CATEGORIES:
        mark = "✅" if category.key in selected else "▫️"
        builder.button(
            text=f"{mark} {category.title}",
            callback_data=CategoryCb(action="toggle", key=category.key),
        )
    builder.button(text="Выбрать все", callback_data=CategoryCb(action="all"))
    builder.button(text="Снять все", callback_data=CategoryCb(action="none"))
    builder.button(text="Готово 👌", callback_data=CategoryCb(action="done"))
    builder.adjust(*([1] * len(CATEGORIES)), 2, 1)
    return builder.as_markup()


def notify_kb(enabled: bool) -> InlineKeyboardMarkup:
    text = "🔕 Выключить" if enabled else "🔔 Включить"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=NotifyCb(enabled=not enabled).pack())]]
    )


def order_kb(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔗 Открыть на Kwork", url=url)]]
    )
