from __future__ import annotations

import time

from mcp_postgres.audit import AuditLog
from mcp_postgres.config import TargetConfig
from mcp_postgres.db import Registry
from mcp_postgres.safety import UnsafeQuery, guard_select

_SCHEMA_SQL = """
SELECT table_schema, table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = $SCHEMA$
ORDER BY table_name, ordinal_position
"""


class Service:
    # Holds the wiring (pools, per-target config, audit) so the MCP tool functions
    # in server.py stay thin. All three tools route through here.
    def __init__(self, registry: Registry, configs: dict[str, TargetConfig], audit: AuditLog, default: str) -> None:
        self._registry = registry
        self._configs = configs
        self._audit = audit
        self._default = default

    def _resolve(self, target: str | None) -> tuple[str, TargetConfig]:
        name = target or self._default
        if name not in self._configs:
            raise ValueError(f"unknown target '{name}'; known: {', '.join(self._configs)}")
        return name, self._configs[name]

    async def schema_describe(self, target: str | None = None, schema: str = "public") -> dict:
        name, cfg = self._resolve(target)
        sql = _SCHEMA_SQL.replace("$SCHEMA$", _quote_literal(schema))
        start = time.perf_counter()
        try:
            rows = await self._registry.get(name).fetch(sql, cfg.max_rows)
            ms = (time.perf_counter() - start) * 1000
            self._audit.record(target=name, tool="schema_describe", sql=sql, ok=True, rows=len(rows), duration_ms=ms)
            return {"target": name, "schema": schema, "columns": rows}
        except Exception as e:
            self._audit.record(target=name, tool="schema_describe", sql=sql, ok=False, error=str(e))
            raise

    async def query_safe(self, sql: str, target: str | None = None) -> dict:
        name, cfg = self._resolve(target)
        try:
            safe_sql = guard_select(sql, max_rows=cfg.max_rows)
        except UnsafeQuery as e:
            self._audit.record(target=name, tool="query_safe", sql=sql, ok=False, error=str(e))
            raise
        start = time.perf_counter()
        try:
            rows = await self._registry.get(name).fetch(safe_sql, cfg.max_rows)
            ms = (time.perf_counter() - start) * 1000
            self._audit.record(target=name, tool="query_safe", sql=safe_sql, ok=True, rows=len(rows), duration_ms=ms)
            return {"target": name, "row_count": len(rows), "rows": rows, "executed_sql": safe_sql}
        except Exception as e:
            self._audit.record(target=name, tool="query_safe", sql=safe_sql, ok=False, error=str(e))
            raise

    async def explain_plan(self, sql: str, target: str | None = None) -> dict:
        name, cfg = self._resolve(target)
        try:
            safe_sql = guard_select(sql, max_rows=cfg.max_rows)
        except UnsafeQuery as e:
            self._audit.record(target=name, tool="explain_plan", sql=sql, ok=False, error=str(e))
            raise
        explain_sql = f"EXPLAIN (FORMAT JSON) {safe_sql}"
        start = time.perf_counter()
        try:
            rows = await self._registry.get(name).fetch(explain_sql, cfg.max_rows)
            ms = (time.perf_counter() - start) * 1000
            self._audit.record(target=name, tool="explain_plan", sql=explain_sql, ok=True, rows=len(rows), duration_ms=ms)
            return {"target": name, "plan": rows}
        except Exception as e:
            self._audit.record(target=name, tool="explain_plan", sql=explain_sql, ok=False, error=str(e))
            raise


def _quote_literal(value: str) -> str:
    # schema name is server-built, not user SQL, but quote it anyway.
    return "'" + value.replace("'", "''") + "'"
