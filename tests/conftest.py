import os

import asyncpg
import pytest

from mcp_postgres.config import TargetConfig
from mcp_postgres.db import TargetPool

TEST_DSN_VARIABLE = "MCPPG_TEST_DSN"


@pytest.fixture
def writable_dsn() -> str:
    dsn = os.environ.get(TEST_DSN_VARIABLE)
    if not dsn:
        pytest.skip(f"{TEST_DSN_VARIABLE} is not set")
    return dsn


@pytest.fixture
async def make_pool(writable_dsn):
    pools: list[TargetPool] = []

    def factory(max_rows: int = 1000, statement_timeout_ms: int = 1000) -> TargetPool:
        pool = TargetPool(
            TargetConfig(
                name="test",
                dsn=writable_dsn,
                max_rows=max_rows,
                statement_timeout_ms=statement_timeout_ms,
            )
        )
        pools.append(pool)
        return pool

    yield factory
    for pool in pools:
        await pool.close()


@pytest.fixture
async def items_table(writable_dsn):
    connection = await asyncpg.connect(writable_dsn)
    await connection.execute("DROP TABLE IF EXISTS mcp_test_items, mcp_test_copy")
    await connection.execute("CREATE TABLE mcp_test_items (id int PRIMARY KEY, name text)")
    await connection.execute(
        "INSERT INTO mcp_test_items SELECT g, 'item' || g FROM generate_series(1, 50) g"
    )
    await connection.close()
    yield "mcp_test_items"
    connection = await asyncpg.connect(writable_dsn)
    await connection.execute("DROP TABLE IF EXISTS mcp_test_items, mcp_test_copy")
    await connection.close()


async def count_items(dsn: str) -> int:
    connection = await asyncpg.connect(dsn)
    try:
        return await connection.fetchval("SELECT count(*) FROM mcp_test_items")
    finally:
        await connection.close()
