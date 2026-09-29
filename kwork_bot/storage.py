from collections.abc import Iterable
from datetime import datetime, timedelta, timezone

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id    INTEGER PRIMARY KEY,
    notify     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS subscriptions (
    user_id      INTEGER NOT NULL,
    category_key TEXT    NOT NULL,
    PRIMARY KEY (user_id, category_key)
);
CREATE TABLE IF NOT EXISTS seen_orders (
    category_key TEXT    NOT NULL,
    order_id     INTEGER NOT NULL,
    seen_at      TEXT    NOT NULL,
    PRIMARY KEY (category_key, order_id)
);
CREATE TABLE IF NOT EXISTS category_state (
    category_key    TEXT PRIMARY KEY,
    last_checked_at TEXT NOT NULL
);
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Storage:
    def __init__(self, path: str) -> None:
        self._path = path
        self._db: aiosqlite.Connection | None = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Storage.connect() не вызван")
        return self._db

    async def connect(self) -> None:
        self._db = await aiosqlite.connect(self._path)
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    # --- пользователи и подписки ---

    async def add_user(self, user_id: int, default_categories: Iterable[str]) -> bool:
        """Регистрирует пользователя. Возвращает True, если он новый."""
        cur = await self.db.execute(
            "INSERT OR IGNORE INTO users (user_id, created_at) VALUES (?, ?)",
            (user_id, _now().isoformat()),
        )
        is_new = cur.rowcount > 0
        if is_new:
            await self.db.executemany(
                "INSERT OR IGNORE INTO subscriptions VALUES (?, ?)",
                [(user_id, key) for key in default_categories],
            )
        await self.db.commit()
        return is_new

    async def get_subscriptions(self, user_id: int) -> set[str]:
        async with self.db.execute(
            "SELECT category_key FROM subscriptions WHERE user_id = ?", (user_id,)
        ) as cur:
            return {row[0] async for row in cur}

    async def toggle_subscription(self, user_id: int, category_key: str) -> bool:
        """Включает/выключает категорию. Возвращает True, если теперь она включена."""
        cur = await self.db.execute(
            "DELETE FROM subscriptions WHERE user_id = ? AND category_key = ?",
            (user_id, category_key),
        )
        subscribed = cur.rowcount == 0
        if subscribed:
            await self.db.execute(
                "INSERT INTO subscriptions VALUES (?, ?)", (user_id, category_key)
            )
        await self.db.commit()
        return subscribed

    async def set_subscriptions(self, user_id: int, category_keys: Iterable[str]) -> None:
        await self.db.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
        await self.db.executemany(
            "INSERT INTO subscriptions VALUES (?, ?)",
            [(user_id, key) for key in category_keys],
        )
        await self.db.commit()

    async def get_notify(self, user_id: int) -> bool:
        async with self.db.execute(
            "SELECT notify FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return bool(row and row[0])

    async def set_notify(self, user_id: int, enabled: bool) -> None:
        await self.db.execute(
            "UPDATE users SET notify = ? WHERE user_id = ?", (int(enabled), user_id)
        )
        await self.db.commit()

    async def get_recipients(self) -> dict[int, set[str]]:
        """Пользователи с включёнными уведомлениями и их категории."""
        result: dict[int, set[str]] = {}
        async with self.db.execute(
            "SELECT s.user_id, s.category_key FROM subscriptions s "
            "JOIN users u ON u.user_id = s.user_id WHERE u.notify = 1"
        ) as cur:
            async for user_id, key in cur:
                result.setdefault(user_id, set()).add(key)
        return result

    # --- уже виденные проекты ---

    async def filter_unseen(self, category_key: str, order_ids: Iterable[int]) -> set[int]:
        ids = set(order_ids)
        if not ids:
            return set()
        placeholders = ",".join("?" * len(ids))
        async with self.db.execute(
            f"SELECT order_id FROM seen_orders "
            f"WHERE category_key = ? AND order_id IN ({placeholders})",
            (category_key, *ids),
        ) as cur:
            seen = {row[0] async for row in cur}
        return ids - seen

    async def mark_seen(self, category_key: str, order_ids: Iterable[int]) -> None:
        now = _now().isoformat()
        await self.db.executemany(
            "INSERT OR IGNORE INTO seen_orders VALUES (?, ?, ?)",
            [(category_key, order_id, now) for order_id in order_ids],
        )
        await self.db.commit()

    async def get_last_checked(self, category_key: str) -> datetime | None:
        async with self.db.execute(
            "SELECT last_checked_at FROM category_state WHERE category_key = ?",
            (category_key,),
        ) as cur:
            row = await cur.fetchone()
        return datetime.fromisoformat(row[0]) if row else None

    async def set_last_checked(self, category_key: str, when: datetime | None = None) -> None:
        await self.db.execute(
            "INSERT INTO category_state VALUES (?, ?) "
            "ON CONFLICT(category_key) DO UPDATE SET last_checked_at = excluded.last_checked_at",
            (category_key, (when or _now()).isoformat()),
        )
        await self.db.commit()

    async def prune_seen(self, older_than: timedelta = timedelta(days=30)) -> None:
        await self.db.execute(
            "DELETE FROM seen_orders WHERE seen_at < ?", ((_now() - older_than).isoformat(),)
        )
        await self.db.commit()
