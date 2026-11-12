import asyncio
import sqlite3
from contextlib import closing
from types import SimpleNamespace

import pytest

from utils.chart_generator import ChartGenerator
from utils.db_handler import DatabaseHandler
from utils.guild_rules import GuildRules
from utils.polygon_handler import PolygonHandler

LEGACY_USERS = """
    CREATE TABLE users (
        user_id INTEGER PRIMARY KEY, username TEXT, first_seen TIMESTAMP,
        last_active TIMESTAMP, total_success INTEGER, success_streak INTEGER,
        last_success_check TIMESTAMP
    )
"""


def test_migration_rolls_back_schema_and_data(monkeypatch, tmp_path):
    path = tmp_path / "bot.db"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(LEGACY_USERS)
        conn.execute("INSERT INTO users (user_id, username, total_success) VALUES (9, 'Test', 12)")

    def fail(*args):
        raise RuntimeError("Interrupted migration")

    with monkeypatch.context() as patch:
        patch.setattr(DatabaseHandler, "_ensure_command_usage_table", fail)
        with pytest.raises(RuntimeError, match="Interrupted"):
            DatabaseHandler(str(path))

    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("SELECT user_id, total_success FROM users").fetchall() == [(9, 12)]
        assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'users_legacy'").fetchone() is None

    DatabaseHandler(str(path))
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("SELECT guild_id, user_id, total_success FROM users").fetchall() == [(0, 9, 12)]


def test_recovers_data_left_by_the_old_migration(tmp_path):
    path = tmp_path / "bot.db"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(LEGACY_USERS.replace("TABLE users", "TABLE users_legacy"))
        conn.execute("INSERT INTO users_legacy (user_id, username, total_success) VALUES (9, 'Test', 12)")
        conn.execute("CREATE TABLE users (guild_id INTEGER, user_id INTEGER)")

    DatabaseHandler(str(path))
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("SELECT guild_id, user_id, total_success FROM users").fetchall() == [(0, 9, 12)]
        assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'users_legacy'").fetchone() is None


@pytest.mark.asyncio
async def test_success_roll_commits_once_and_preserves_existing_points(tmp_path):
    db = DatabaseHandler(str(tmp_path / "bot.db"))
    await db.set_total_success(10, 20, "Test", 12)

    first, second = await asyncio.gather(
        db.record_success_roll(10, 20, "Test", 90, 6),
        db.record_success_roll(10, 20, "Test", 90, 6),
    )

    assert sorted(result[0] is None for result in (first, second)) == [False, True]
    assert await db.get_total_success(10, 20) == 18
    assert (await db.get_success_stats(10, 20))["success_streak"] == 1
    assert await db.get_command_execution_time(10, 20, "успех") is not None


@pytest.mark.asyncio
async def test_rule_edits_persist_in_the_selected_server(tmp_path):
    db = DatabaseHandler(str(tmp_path / "bot.db"))
    rules = GuildRules(db, "words", {"example": True})

    assert await rules.set(10, "example", None)
    assert await rules.set(20, "hello", True)
    restarted = GuildRules(db, "words", {"example": True})
    assert await restarted.get(10) == {}
    assert await restarted.get(20) == {"example": True, "hello": True}
    assert await restarted.get(30) == {"example": True}


@pytest.mark.asyncio
async def test_stock_requests_use_header_authentication_and_date_order(monkeypatch):
    request = {}

    class Response:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def raise_for_status(self):
            pass

        async def json(self):
            return {"status": "OK", "results": []}

    def get(url, **kwargs):
        request.update(url=url, **kwargs)
        return Response()

    client = PolygonHandler("test-key")

    async def session():
        return SimpleNamespace(get=get)

    monkeypatch.setattr(client, "_get_session", session)
    await client.get_aggregates("AAPL", limit=366)
    assert request["headers"] == {"Authorization": "Bearer test-key"}
    assert request["allow_redirects"] is False
    assert "test-key" not in request["url"]
    assert request["params"] == {"adjusted": "true", "limit": 366, "sort": "asc"}


def test_chart_ema_starts_after_the_first_full_window():
    assert ChartGenerator._calculate_ema([1, 2, 3, 4, 5], 3) == [2, 3, 4]
    assert ChartGenerator._calculate_ema([1, 2], 3) == []
