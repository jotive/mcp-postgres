import asyncpg
import pytest
from conftest import count_items

from mcp_postgres.config import TargetConfig
from mcp_postgres.db import TargetPool

pytestmark = pytest.mark.usefixtures("items_table")


@pytest.fixture
async def readonly_pool(readonly_dsn):
    pool = TargetPool(
        TargetConfig(name="readonly", dsn=readonly_dsn, max_rows=100, statement_timeout_ms=1000)
    )
    yield pool
    await pool.close()


@pytest.fixture
async def readonly_connection(readonly_dsn):
    connection = await asyncpg.connect(readonly_dsn)
    yield connection
    await connection.close()


async def test_role_is_not_privileged(readonly_connection):
    row = await readonly_connection.fetchrow(
        "SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication FROM pg_roles "
        "WHERE rolname = current_user"
    )
    assert not any(row.values())


async def test_role_can_read_granted_table(readonly_pool):
    rows = await readonly_pool.fetch("SELECT count(*) AS total FROM mcp_test_items", 10)
    assert rows == [{"total": 50}]


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO mcp_test_items VALUES (2000, 'x')",
        "UPDATE mcp_test_items SET name = 'x'",
        "DELETE FROM mcp_test_items",
        "TRUNCATE mcp_test_items",
        "DROP TABLE mcp_test_items",
        "ALTER TABLE mcp_test_items ADD COLUMN extra int",
        "CREATE TABLE mcp_test_copy (id int)",
        "WITH gone AS (DELETE FROM mcp_test_items RETURNING id) SELECT * FROM gone",
    ],
)
async def test_role_cannot_write_even_on_a_plain_connection(readonly_connection, readonly_dsn, sql):
    with pytest.raises(asyncpg.PostgresError):
        await readonly_connection.execute(sql)
    assert await count_items(readonly_dsn) == 50


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO mcp_test_items VALUES (2000, 'x')",
        "DELETE FROM mcp_test_items",
        "DROP TABLE mcp_test_items",
        "WITH gone AS (DELETE FROM mcp_test_items RETURNING id) SELECT * FROM gone",
        "SELECT * INTO mcp_test_copy FROM mcp_test_items",
        "CREATE TEMP TABLE mcp_test_copy AS SELECT * FROM mcp_test_items",
    ],
)
async def test_role_cannot_write_through_the_pool(readonly_pool, readonly_dsn, sql):
    with pytest.raises(asyncpg.PostgresError):
        await readonly_pool.fetch(sql, 10)
    assert await count_items(readonly_dsn) == 50


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT pg_read_binary_file('/etc/passwd')",
        "SELECT pg_ls_dir('/')",
        "SELECT pg_stat_file('/etc/passwd')",
        "SELECT lo_import('/etc/passwd')",
        "SELECT lo_export(1, '/tmp/mcp_test_export')",
        "SELECT pg_reload_conf()",
        "SELECT pg_rotate_logfile()",
        "SELECT pg_switch_wal()",
        "SELECT pg_create_restore_point('mcp_test')",
        "SELECT nextval('mcp_test_missing_sequence')",
        "COPY mcp_test_items TO PROGRAM 'id'",
        "COPY mcp_test_items TO '/tmp/mcp_test_export'",
        "CREATE EXTENSION dblink",
    ],
)
async def test_role_cannot_run_dangerous_functions(readonly_pool, sql):
    with pytest.raises(asyncpg.PostgresError):
        await readonly_pool.fetch(sql, 10)


async def test_role_cannot_escalate_with_set_role(readonly_connection):
    with pytest.raises(asyncpg.PostgresError):
        await readonly_connection.execute("SET ROLE postgres")


async def test_role_cannot_read_ungranted_catalog_secrets(readonly_pool):
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await readonly_pool.fetch("SELECT rolpassword FROM pg_authid", 10)


async def test_role_cannot_terminate_other_backends(readonly_pool, writable_dsn):
    other = await asyncpg.connect(writable_dsn)
    try:
        other_pid = await other.fetchval("SELECT pg_backend_pid()")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await readonly_pool.fetch(f"SELECT pg_terminate_backend({other_pid})", 10)
        assert await other.fetchval("SELECT 1") == 1
    finally:
        await other.close()
