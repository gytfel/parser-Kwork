"""Получение проектов с биржи Kwork.

Лента https://kwork.ru/projects подгружается фронтендом тем же адресом через
POST-запрос с заголовком X-Requested-With — в ответ приходит JSON вида
{"success": true, "data": {"wants": [...], ...}}. Им и пользуемся.
"""

import asyncio
import html
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from kwork_bot.categories import PARENT_CATEGORY_ID, Category

logger = logging.getLogger(__name__)

PROJECTS_URL = "https://kwork.ru/projects"
MOSCOW_TZ = timezone(timedelta(hours=3), "МСК")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://kwork.ru",
    "Referer": PROJECTS_URL,
    "Cache-Control": "no-cache",
}

_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


class KworkError(Exception):
    """Kwork не ответил или ответил не тем, что мы ждём."""


@dataclass(frozen=True)
class Order:
    id: int
    title: str
    description: str
    price: int             # желаемый бюджет, 0 — не указан
    max_price: int         # допустимый бюджет, 0 — не указан
    offers: int | None     # сколько фрилансеров уже откликнулось
    published_at: datetime | None
    category: Category

    @property
    def url(self) -> str:
        return f"https://kwork.ru/projects/{self.id}/view"


def clean_text(value: Any) -> str:
    text = _BR_RE.sub("\n", str(value or ""))
    text = _TAG_RE.sub("", text)
    text = html.unescape(text).replace("\xa0", " ")
    return text.strip()


def _to_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _parse_offers(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_date(raw: dict) -> datetime | None:
    # date_active — момент публикации или последнего поднятия проекта,
    # date_create у поднятых проектов бывает очень старым.
    value = raw.get("date_active") or raw.get("date_create")
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S").replace(tzinfo=MOSCOW_TZ)
    except ValueError:
        return None


def parse_order(raw: dict, category: Category) -> Order | None:
    order_id = _to_int(raw.get("id"))
    if not order_id:
        return None

    price = _to_int(raw.get("priceLimit"))
    max_price = _to_int(raw.get("possiblePriceLimit")) if raw.get("isHigherPrice") else 0

    return Order(
        id=order_id,
        title=clean_text(raw.get("name")) or "Без названия",
        description=clean_text(raw.get("description")),
        price=price,
        max_price=max_price if max_price > price else 0,
        offers=_parse_offers(raw.get("kwork_count")),
        published_at=_parse_date(raw),
        category=category,
    )


def parse_response(payload: Any, category: Category) -> list[Order]:
    data = payload.get("data") if isinstance(payload, dict) else None
    wants = data.get("wants") if isinstance(data, dict) else None
    if not isinstance(wants, list):
        raise KworkError("в ответе Kwork нет списка проектов (data.wants)")

    orders = []
    for raw in wants:
        if isinstance(raw, dict) and (order := parse_order(raw, category)):
            orders.append(order)
    return orders


class KworkClient:
    def __init__(
        self, proxy: str | None = None, timeout: float = 20, url: str = PROJECTS_URL
    ) -> None:
        self._url = url
        self._proxy = proxy
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=HEADERS, timeout=self._timeout)
        return self._session

    async def fetch_orders(self, category: Category, page: int = 1) -> list[Order]:
        form = {"c": PARENT_CATEGORY_ID, "attr": category.attr_id, "page": str(page)}
        session = await self._get_session()
        try:
            async with session.post(self._url, data=form, proxy=self._proxy) as resp:
                body = await resp.text(errors="replace")
                if resp.status != 200:
                    raise KworkError(f"HTTP {resp.status}")
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            raise KworkError(f"сетевая ошибка: {e!r}") from e

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as e:
            # Обычно это страница с капчей или блокировкой вместо JSON.
            raise KworkError(f"ответ не JSON: {body[:200]!r}") from e

        return parse_response(payload, category)

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
