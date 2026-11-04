import asyncpg
import pytest
from conftest import count_items

from mcp_postgres.audit import AuditLog
from mcp_postgres.config import TargetConfig
from mcp_postgres.db import Registry
from mcp_postgres.safety import UnsafeQuery
from mcp_postgres.tools import Service

pytestmark = pytest.mark.usefixtures("items_table")


@pytest.fixture
async def live_service(writable_dsn, tmp_path):
    configs = {
        "test": TargetConfig(name="test", dsn=writable_dsn, max_rows=20, statement_timeout_ms=500)
    }
    registry = Registry(configs)
    yield Service(registry, configs, AuditLog(tmp_path / "audit.jsonl"), "test")
    await registry.close()


async def test_row_cap_applied_end_to_end(live_service):
    result = await live_service.query_safe("SELECT * FROM mcp_test_items")
    assert result["row_count"] == 20
    assert "LIMIT 20" in result["executed_sql"].upper()


async def test_oversized_limit_is_clamped_end_to_end(live_service):
    result = await live_service.query_safe("SELECT * FROM mcp_test_items LIMIT 1000000")
    assert result["row_count"] == 20


async def test_explain_plan_returns_plan(live_service):
    result = await live_service.explain_plan("SELECT * FROM mcp_test_items WHERE id = 1")
    assert result["plan"]


async def test_schema_describe_lists_columns(live_service):
    result = await live_service.schema_describe(schema="public")
    assert result["columns"]


async def test_timeout_surfaces_as_error(live_service):
    with pytest.raises(asyncpg.QueryCanceledError):
        await live_service.query_safe("SELECT pg_sleep(5)")


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM mcp_test_items",
        "SELECT 1; DELETE FROM mcp_test_items",
        "WITH gone AS (DELETE FROM mcp_test_items RETURNING id) SELECT * FROM gone",
        "SET ROLE postgres",
        "COPY mcp_test_items TO PROGRAM 'id'",
        "SELECT set_config('default_transaction_read_only', 'off', false)",
        "SELECT * FROM mcp_test_items FOR UPDATE",
        "SELECT * INTO mcp_test_copy FROM mcp_test_items",
        "DO $$ BEGIN DELETE FROM mcp_test_items; END $$",
    ],
)
async def test_attacks_rejected_end_to_end(live_service, writable_dsn, sql):
    with pytest.raises(UnsafeQuery):
        await live_service.query_safe(sql)
    assert await count_items(writable_dsn) == 50
