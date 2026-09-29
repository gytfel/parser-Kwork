import asyncio
import json

import pytest
from aiohttp import web

from kwork_bot.categories import CATEGORY_BY_KEY
from kwork_bot.kwork import KworkClient, KworkError, MOSCOW_TZ, parse_response

PARSERS = CATEGORY_BY_KEY["parsers"]

SAMPLE = {
    "success": True,
    "data": {
        "wants": [
            {
                "id": 2912345,
                "name": "Парсер &laquo;Авито&raquo; на Python",
                "description": "Нужно собрать объявления.<br />Выгрузка в&nbsp;Excel &amp; CSV",
                "priceLimit": "5000.00",
                "possiblePriceLimit": "15000",
                "isHigherPrice": True,
                "kwork_count": "3",
                "date_active": "2026-09-29 14:05:00",
                "date_create": "2026-01-01 10:00:00",
            },
            {
                "id": "2912346",
                "name": "",
                "priceLimit": None,
                "possiblePriceLimit": "9000",
                "isHigherPrice": False,
            },
            {"name": "без id — пропускаем"},
            "мусор",
        ]
    },
}


def test_parse_response_fields():
    orders = parse_response(SAMPLE, PARSERS)
    assert [o.id for o in orders] == [2912345, 2912346]

    first = orders[0]
    assert first.title == "Парсер «Авито» на Python"
    assert first.description == "Нужно собрать объявления.\nВыгрузка в Excel & CSV"
    assert (first.price, first.max_price) == (5000, 15000)
    assert first.offers == 3
    assert first.published_at.tzinfo is MOSCOW_TZ
    assert (first.published_at.hour, first.published_at.minute) == (14, 5)
    assert first.category is PARSERS
    assert first.url == "https://kwork.ru/projects/2912345/view"

    second = orders[1]
    assert second.title == "Без названия"
    assert (second.price, second.max_price) == (0, 0)
    assert second.offers is None
    assert second.published_at is None


@pytest.mark.parametrize("payload", [{}, {"data": None}, {"data": {"wants": None}}, [], "x"])
def test_parse_response_rejects_unexpected_payload(payload):
    with pytest.raises(KworkError):
        parse_response(payload, PARSERS)


async def _serve(handler):
    app = web.Application()
    app.router.add_post("/projects", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{port}/projects"


def test_client_sends_category_filter_and_parses_json():
    received = {}

    async def handler(request):
        received["form"] = dict(await request.post())
        received["xhr"] = request.headers.get("X-Requested-With")
        return web.Response(text=json.dumps(SAMPLE), content_type="text/html")

    async def scenario():
        runner, url = await _serve(handler)
        client = KworkClient(url=url)
        try:
            return await client.fetch_orders(PARSERS)
        finally:
            await client.close()
            await runner.cleanup()

    orders = asyncio.run(scenario())
    assert len(orders) == 2
    assert received["form"] == {"c": "41", "attr": "211", "page": "1"}
    assert received["xhr"] == "XMLHttpRequest"


@pytest.mark.parametrize(
    "response",
    [
        lambda: web.Response(status=403, text="Forbidden"),
        lambda: web.Response(text="<html>captcha</html>"),
    ],
)
def test_client_raises_kwork_error_on_bad_response(response):
    async def handler(request):
        return response()

    async def scenario():
        runner, url = await _serve(handler)
        client = KworkClient(url=url)
        try:
            await client.fetch_orders(PARSERS)
        finally:
            await client.close()
            await runner.cleanup()

    with pytest.raises(KworkError):
        asyncio.run(scenario())
