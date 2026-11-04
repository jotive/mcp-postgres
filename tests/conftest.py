import os
from urllib.parse import urlsplit, urlunsplit

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


READONLY_ROLE = "mcp_test_readonly"
READONLY_PASSWORD = "mcp_test_readonly_password"


@pytest.fixture
async def readonly_dsn(writable_dsn, items_table):
    admin = await asyncpg.connect(writable_dsn)
    try:
        database = await admin.fetchval("SELECT current_database()")
        try:
            await admin.execute(f"DROP ROLE IF EXISTS {READONLY_ROLE}")
            await admin.execute(
                f"CREATE ROLE {READONLY_ROLE} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                f"PASSWORD '{READONLY_PASSWORD}'"
            )
        except asyncpg.InsufficientPrivilegeError:
            pytest.skip("MCPPG_TEST_DSN role cannot create roles")
        await admin.execute(f'GRANT CONNECT ON DATABASE "{database}" TO {READONLY_ROLE}')
        await admin.execute(f"GRANT USAGE ON SCHEMA public TO {READONLY_ROLE}")
        await admin.execute(f"GRANT SELECT ON {items_table} TO {READONLY_ROLE}")
        parts = urlsplit(writable_dsn)
        host = parts.hostname or "localhost"
        port = f":{parts.port}" if parts.port else ""
        dsn = urlunsplit(
            (parts.scheme, f"{READONLY_ROLE}:{READONLY_PASSWORD}@{host}{port}", parts.path, parts.query, "")
        )
        yield dsn
    finally:
        await admin.execute(f"DROP OWNED BY {READONLY_ROLE}")
        await admin.execute(f"DROP ROLE IF EXISTS {READONLY_ROLE}")
        await admin.close()
