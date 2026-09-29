import asyncio
from datetime import timedelta

import pytest
from aiogram.exceptions import TelegramForbiddenError

from kwork_bot import monitor as monitor_module
from kwork_bot.categories import CATEGORIES, CATEGORY_BY_KEY
from kwork_bot.kwork import KworkError, Order
from kwork_bot.monitor import Monitor
from kwork_bot.storage import Storage


def make_order(order_id: int, key: str) -> Order:
    return Order(
        id=order_id,
        title=f"Проект {order_id}",
        description="",
        price=1000,
        max_price=0,
        offers=None,
        published_at=None,
        category=CATEGORY_BY_KEY[key],
    )


class FakeClient:
    def __init__(self) -> None:
        self.pages: dict[str, list[Order]] = {c.key: [] for c in CATEGORIES}
        self.failing: set[str] = set()

    async def fetch_orders(self, category, page=1):
        if category.key in self.failing:
            raise KworkError("HTTP 403")
        return list(self.pages[category.key])


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.blocked: set[int] = set()

    async def send_message(self, chat_id, text, **kwargs):
        if chat_id in self.blocked:
            raise TelegramForbiddenError(method=None, message="bot was blocked by the user")
        self.sent.append((chat_id, text))


@pytest.fixture(autouse=True)
def no_pauses(monkeypatch):
    monkeypatch.setattr(monitor_module, "REQUEST_PAUSE", 0)
    monkeypatch.setattr(monitor_module, "SEND_PAUSE", 0)


def run(tmp_path, scenario):
    async def wrapper():
        storage = Storage(str(tmp_path / "test.db"))
        await storage.connect()
        client, bot = FakeClient(), FakeBot()
        try:
            return await scenario(Monitor(bot, storage, client, interval=60), storage, client, bot)
        finally:
            await storage.close()

    return asyncio.run(wrapper())


def sent_ids(bot: FakeBot, chat_id: int) -> list[str]:
    return [text.split("Проект ")[1].split("<")[0] for cid, text in bot.sent if cid == chat_id]


def test_first_check_only_remembers_existing_orders(tmp_path):
    async def scenario(monitor, storage, client, bot):
        await storage.add_user(1, ["parsers"])
        client.pages["parsers"] = [make_order(10, "parsers"), make_order(11, "parsers")]
        assert await monitor.check_once() == {}
        assert bot.sent == []

        # Появился новый проект — приходит только он.
        client.pages["parsers"].insert(0, make_order(12, "parsers"))
        new = await monitor.check_once()
        assert [o.id for o in new["parsers"]] == [12]
        assert sent_ids(bot, 1) == ["12"]

        # Повторная проверка ничего не шлёт.
        await monitor.check_once()
        assert sent_ids(bot, 1) == ["12"]

    run(tmp_path, scenario)


def test_orders_go_only_to_subscribers_and_without_duplicates(tmp_path):
    async def scenario(monitor, storage, client, bot):
        await storage.add_user(1, ["parsers"])
        await storage.add_user(2, ["parsers", "scripts"])
        await storage.add_user(3, ["ai_bots"])
        await storage.add_user(4, ["parsers"])
        await storage.set_notify(4, False)
        await monitor.check_once()

        client.pages["parsers"] = [make_order(20, "parsers")]
        # Тот же проект сразу в двух подкатегориях.
        client.pages["scripts"] = [make_order(20, "scripts"), make_order(21, "scripts")]
        await monitor.check_once()

        assert sent_ids(bot, 1) == ["20"]
        assert sent_ids(bot, 2) == ["20", "21"]
        assert sent_ids(bot, 3) == []
        assert sent_ids(bot, 4) == []

    run(tmp_path, scenario)


def test_stale_category_is_reprimed_instead_of_spamming(tmp_path):
    async def scenario(monitor, storage, client, bot):
        await storage.add_user(1, ["parsers"])
        await monitor.check_once()

        last = await storage.get_last_checked("parsers")
        await storage.set_last_checked("parsers", last - monitor.stale_after - timedelta(minutes=1))
        client.pages["parsers"] = [make_order(30, "parsers")]
        await monitor.check_once()
        assert bot.sent == []

    run(tmp_path, scenario)


def test_kwork_failure_in_one_category_does_not_stop_others(tmp_path):
    async def scenario(monitor, storage, client, bot):
        await storage.add_user(1, ["parsers", "scripts"])
        await monitor.check_once()

        client.failing.add("parsers")
        client.pages["scripts"] = [make_order(40, "scripts")]
        await monitor.check_once()
        assert sent_ids(bot, 1) == ["40"]

    run(tmp_path, scenario)


def test_blocked_user_gets_notifications_disabled(tmp_path):
    async def scenario(monitor, storage, client, bot):
        await storage.add_user(1, ["parsers"])
        await monitor.check_once()

        bot.blocked.add(1)
        client.pages["parsers"] = [make_order(50, "parsers"), make_order(51, "parsers")]
        await monitor.check_once()
        assert await storage.get_notify(1) is False

    run(tmp_path, scenario)


def test_get_latest_merges_categories_newest_first(tmp_path):
    async def scenario(monitor, storage, client, bot):
        client.pages["parsers"] = [make_order(3, "parsers"), make_order(1, "parsers")]
        client.pages["scripts"] = [make_order(3, "scripts"), make_order(2, "scripts")]
        latest = await monitor.get_latest(["parsers", "scripts"], limit=2)
        assert [o.id for o in latest] == [3, 2]

    run(tmp_path, scenario)
