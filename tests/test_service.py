import json

import pytest

from mcp_postgres.audit import AuditLog
from mcp_postgres.config import TargetConfig
from mcp_postgres.safety import UnsafeQuery
from mcp_postgres.tools import Service


class StubPool:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    async def fetch(self, sql, max_rows):
        self.executed.append(sql)
        return self.rows[:max_rows]


class StubRegistry:
    def __init__(self, pool):
        self._pool = pool

    def get(self, name):
        return self._pool


@pytest.fixture
def stub_pool():
    return StubPool([{"id": index} for index in range(10)])


@pytest.fixture
def audit_path(tmp_path):
    return tmp_path / "audit.jsonl"


@pytest.fixture
def service(stub_pool, audit_path):
    configs = {"dev": TargetConfig(name="dev", dsn="postgresql://unused", max_rows=5)}
    return Service(StubRegistry(stub_pool), configs, AuditLog(audit_path), "dev")


def read_audit(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


async def test_query_safe_output_shape(service):
    result = await service.query_safe("SELECT id FROM t")
    assert set(result) == {"target", "row_count", "rows", "executed_sql"}
    assert result["target"] == "dev"
    assert result["row_count"] == 5
    assert "LIMIT 5" in result["executed_sql"].upper()


async def test_query_safe_rejects_write_without_touching_database(service, stub_pool, audit_path):
    with pytest.raises(UnsafeQuery):
        await service.query_safe("DELETE FROM t")
    assert stub_pool.executed == []
    entry = read_audit(audit_path)[-1]
    assert entry["ok"] is False and entry["tool"] == "query_safe"


async def test_query_safe_rejects_side_effect_function_without_touching_database(service, stub_pool):
    with pytest.raises(UnsafeQuery):
        await service.query_safe("SELECT set_config('statement_timeout', '0', false)")
    assert stub_pool.executed == []


async def test_explain_plan_wraps_guarded_sql(service, stub_pool):
    result = await service.explain_plan("SELECT id FROM t")
    assert set(result) == {"target", "plan"}
    assert stub_pool.executed[0].startswith("EXPLAIN (FORMAT JSON) SELECT")


async def test_explain_plan_rejects_write(service, stub_pool):
    with pytest.raises(UnsafeQuery):
        await service.explain_plan("DELETE FROM t")
    assert stub_pool.executed == []


async def test_schema_describe_output_shape(service):
    result = await service.schema_describe(schema="public")
    assert set(result) == {"target", "schema", "columns"}


async def test_schema_describe_escapes_schema_name(service, stub_pool):
    await service.schema_describe(schema="x'; DROP TABLE users; --")
    assert "'x''; DROP TABLE users; --'" in stub_pool.executed[0]


async def test_unknown_target_rejected(service):
    with pytest.raises(ValueError):
        await service.query_safe("SELECT 1", target="missing")


async def test_successful_call_is_audited(service, audit_path):
    await service.query_safe("SELECT id FROM t")
    entry = read_audit(audit_path)[-1]
    assert entry["ok"] is True and entry["rows"] == 5
