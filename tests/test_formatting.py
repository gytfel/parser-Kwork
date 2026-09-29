from datetime import datetime

from kwork_bot.categories import CATEGORY_BY_KEY
from kwork_bot.formatting import format_budget, format_order, shorten
from kwork_bot.kwork import MOSCOW_TZ, Order


def make_order(**overrides) -> Order:
    fields = dict(
        id=1,
        title="Бот <для> Telegram & WhatsApp",
        description="Описание",
        price=5000,
        max_price=0,
        offers=None,
        published_at=None,
        category=CATEGORY_BY_KEY["chatbots"],
    )
    fields.update(overrides)
    return Order(**fields)


def test_budget():
    assert format_budget(make_order(price=0)) == "не указан"
    assert format_budget(make_order(price=5000)) == "до 5 000 ₽"
    assert format_budget(make_order(price=5000, max_price=15000)) == (
        "до 5 000 ₽ (допустимо до 15 000 ₽)"
    )


def test_shorten_cuts_on_word_boundary():
    assert shorten("короткий текст", 100) == "короткий текст"
    assert shorten("один два три четыре", 12) == "один два…"


def test_format_order_escapes_html_and_shows_details():
    text = format_order(
        make_order(
            description="<script>alert(1)</script>",
            offers=4,
            published_at=datetime(2026, 9, 29, 14, 5, tzinfo=MOSCOW_TZ),
        )
    )
    assert text.startswith("🆕 <b><a href=\"https://kwork.ru/projects/1/view\">")
    assert "Бот &lt;для&gt; Telegram &amp; WhatsApp" in text
    assert "&lt;script&gt;" in text and "<script>" not in text
    assert "💬 Чат-боты" in text
    assert "👥 Предложений: 4" in text
    assert "🕒 29.09 в 14:05 МСК" in text


def test_format_order_skips_missing_parts():
    text = format_order(make_order(description=""), is_new=False)
    assert not text.startswith("🆕")
    assert "Предложений" not in text
    assert "🕒" not in text
    assert "blockquote" not in text
