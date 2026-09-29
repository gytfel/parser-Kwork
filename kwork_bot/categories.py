"""Подкатегории раздела «Скрипты, боты и mini apps» на бирже Kwork.

Kwork фильтрует ленту проектов по разделу (c) и подрубрике (attr):
https://kwork.ru/projects?c=41&attr=211 — это «Парсеры».
"""

from dataclasses import dataclass

PARENT_CATEGORY_ID = "41"
PARENT_CATEGORY_NAME = "Скрипты, боты и mini apps"


@dataclass(frozen=True)
class Category:
    key: str       # короткий ключ для callback_data и базы
    attr_id: str   # id подрубрики на Kwork
    name: str
    emoji: str

    @property
    def title(self) -> str:
        return f"{self.emoji} {self.name}"

    @property
    def url(self) -> str:
        return f"https://kwork.ru/projects?c={PARENT_CATEGORY_ID}&attr={self.attr_id}"


# Порядок — как в меню Kwork.
CATEGORIES: tuple[Category, ...] = (
    Category("scripts", "7352", "Скрипты", "📜"),
    Category("parsers", "211", "Парсеры", "🕷"),
    Category("chatbots", "3587", "Чат-боты", "💬"),
    Category("miniapps", "3934090", "Telegram Mini Apps", "📱"),
    Category("ai_agents", "5548694", "ИИ-агенты", "🧠"),
    Category("ai_bots", "4158112", "ИИ-боты", "🤖"),
)

CATEGORY_BY_KEY: dict[str, Category] = {c.key: c for c in CATEGORIES}
