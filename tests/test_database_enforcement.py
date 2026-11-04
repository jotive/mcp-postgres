import contextlib

import asyncpg
import pytest
from conftest import count_items

pytestmark = pytest.mark.usefixtures("items_table")


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO mcp_test_items VALUES (1000, 'x')",
        "UPDATE mcp_test_items SET name = 'x'",
        "DELETE FROM mcp_test_items",
        "TRUNCATE mcp_test_items",
        "DROP TABLE mcp_test_items",
        "CREATE TABLE mcp_test_copy (id int)",
        "ALTER TABLE mcp_test_items ADD COLUMN extra int",
        "SELECT * INTO mcp_test_copy FROM mcp_test_items",
        "CREATE TABLE mcp_test_copy AS SELECT * FROM mcp_test_items",
        "WITH gone AS (DELETE FROM mcp_test_items RETURNING id) SELECT * FROM gone",
        "WITH added AS (INSERT INTO mcp_test_items VALUES (1001, 'x') RETURNING id) SELECT * FROM added",
        "WITH changed AS (UPDATE mcp_test_items SET name = 'x' RETURNING id) SELECT * FROM changed",
        "SELECT * FROM mcp_test_items FOR UPDATE",
        "DO $$ BEGIN DELETE FROM mcp_test_items; END $$",
    ],
)
async def test_database_refuses_writes_even_when_guard_is_bypassed(make_pool, writable_dsn, sql):
    pool = make_pool()
    with pytest.raises(asyncpg.PostgresError):
        await pool.fetch(sql, 10)
    assert await count_items(writable_dsn) == 50


async def test_set_config_cannot_unlock_writes_in_following_queries(make_pool, writable_dsn):
    pool = make_pool()
    for statement in (
        "SELECT set_config('default_transaction_read_only', 'off', false)",
        "SELECT set_config('transaction_read_only', 'off', false)",
    ):
        with contextlib.suppress(asyncpg.PostgresError):
            await pool.fetch(statement, 10)
        with pytest.raises(asyncpg.PostgresError):
            await pool.fetch("DELETE FROM mcp_test_items", 10)
    assert await count_items(writable_dsn) == 50


async def test_session_state_does_not_leak_between_queries(make_pool):
    pool = make_pool(statement_timeout_ms=700)
    with contextlib.suppress(asyncpg.PostgresError):
        await pool.fetch("SELECT set_config('statement_timeout', '0', false)", 10)
    with pytest.raises(asyncpg.QueryCanceledError):
        await pool.fetch("SELECT pg_sleep(5)", 10)


async def test_role_and_transaction_control_statements_do_not_unlock_writes(make_pool, writable_dsn):
    pool = make_pool()
    for statement in ("SET ROLE postgres", "COMMIT", "BEGIN READ WRITE", "SET TRANSACTION READ WRITE"):
        with contextlib.suppress(asyncpg.PostgresError, asyncpg.InterfaceError):
            await pool.fetch(statement, 10)
    with pytest.raises(asyncpg.PostgresError):
        await pool.fetch("DELETE FROM mcp_test_items", 10)
    assert await count_items(writable_dsn) == 50


async def test_statement_timeout_cancels_long_query(make_pool):
    pool = make_pool(statement_timeout_ms=300)
    with pytest.raises(asyncpg.QueryCanceledError):
        await pool.fetch("SELECT pg_sleep(5)", 10)


async def test_statement_timeout_cancels_runaway_scan(make_pool):
    pool = make_pool(statement_timeout_ms=300)
    with pytest.raises(asyncpg.QueryCanceledError):
        await pool.fetch("SELECT count(*) FROM generate_series(1, 1000000000)", 10)


async def test_pool_recovers_after_timeout(make_pool):
    pool = make_pool(statement_timeout_ms=300)
    with pytest.raises(asyncpg.QueryCanceledError):
        await pool.fetch("SELECT pg_sleep(5)", 10)
    assert await pool.fetch("SELECT 1 AS one", 10) == [{"one": 1}]


async def test_fetch_never_returns_more_than_max_rows(make_pool):
    pool = make_pool()
    rows = await pool.fetch("SELECT g FROM generate_series(1, 100000) g", 25)
    assert len(rows) == 25


async def test_normal_query_returns_rows(make_pool):
    pool = make_pool()
    rows = await pool.fetch("SELECT id, name FROM mcp_test_items ORDER BY id LIMIT 3", 10)
    assert rows == [
        {"id": 1, "name": "item1"},
        {"id": 2, "name": "item2"},
        {"id": 3, "name": "item3"},
    ]
