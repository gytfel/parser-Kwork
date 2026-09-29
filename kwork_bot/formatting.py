from html import escape

from kwork_bot.kwork import MOSCOW_TZ, Order

DESCRIPTION_LIMIT = 800


def format_price(value: int) -> str:
    return f"{value:,}".replace(",", " ") + " ₽"


def format_budget(order: Order) -> str:
    if not order.price:
        return "не указан"
    budget = f"до {format_price(order.price)}"
    if order.max_price:
        budget += f" (допустимо до {format_price(order.max_price)})"
    return budget


def shorten(text: str, limit: int = DESCRIPTION_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(".,;:!?-— \n") + "…"


def format_order(order: Order, *, is_new: bool = True) -> str:
    lines = [
        f"{'🆕 ' if is_new else ''}<b><a href=\"{order.url}\">{escape(order.title)}</a></b>",
        "",
        f"📂 {escape(order.category.title)}",
        f"💰 Бюджет: <b>{format_budget(order)}</b>",
    ]
    if order.offers is not None:
        lines.append(f"👥 Предложений: {order.offers}")
    if order.published_at is not None:
        published = order.published_at.astimezone(MOSCOW_TZ)
        lines.append(f"🕒 {published:%d.%m в %H:%M} МСК")
    if order.description:
        lines += ["", f"<blockquote expandable>{escape(shorten(order.description))}</blockquote>"]
    return "\n".join(lines)
