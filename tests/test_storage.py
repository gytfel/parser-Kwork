import asyncio

from kwork_bot.storage import Storage


def run_with_storage(tmp_path, scenario):
    async def wrapper():
        storage = Storage(str(tmp_path / "test.db"))
        await storage.connect()
        try:
            return await scenario(storage)
        finally:
            await storage.close()

    return asyncio.run(wrapper())


def test_new_user_gets_default_subscriptions(tmp_path):
    async def scenario(s: Storage):
        assert await s.add_user(1, ["parsers", "scripts"]) is True
        assert await s.add_user(1, ["ai_bots"]) is False
        assert await s.get_subscriptions(1) == {"parsers", "scripts"}
        assert await s.get_notify(1) is True

    run_with_storage(tmp_path, scenario)


def test_toggle_and_set_subscriptions(tmp_path):
    async def scenario(s: Storage):
        await s.add_user(1, ["parsers"])
        assert await s.toggle_subscription(1, "parsers") is False
        assert await s.toggle_subscription(1, "ai_bots") is True
        assert await s.get_subscriptions(1) == {"ai_bots"}

        await s.set_subscriptions(1, ["scripts", "chatbots"])
        assert await s.get_subscriptions(1) == {"scripts", "chatbots"}
        await s.set_subscriptions(1, [])
        assert await s.get_subscriptions(1) == set()

    run_with_storage(tmp_path, scenario)


def test_recipients_skip_users_with_notifications_off(tmp_path):
    async def scenario(s: Storage):
        await s.add_user(1, ["parsers"])
        await s.add_user(2, ["parsers", "scripts"])
        await s.add_user(3, [])
        await s.set_notify(1, False)
        assert await s.get_recipients() == {2: {"parsers", "scripts"}}

    run_with_storage(tmp_path, scenario)


def test_seen_orders_are_tracked_per_category(tmp_path):
    async def scenario(s: Storage):
        assert await s.filter_unseen("parsers", []) == set()
        assert await s.filter_unseen("parsers", [1, 2, 3]) == {1, 2, 3}
        await s.mark_seen("parsers", [1, 2])
        assert await s.filter_unseen("parsers", [1, 2, 3]) == {3}
        assert await s.filter_unseen("scripts", [1]) == {1}

        assert await s.get_last_checked("parsers") is None
        await s.set_last_checked("parsers")
        await s.set_last_checked("parsers")
        assert await s.get_last_checked("parsers") is not None

    run_with_storage(tmp_path, scenario)
