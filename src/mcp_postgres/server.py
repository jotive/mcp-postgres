from __future__ import annotations

import structlog
from mcp.server.fastmcp import FastMCP

from mcp_postgres.audit import AuditLog
from mcp_postgres.config import Settings
from mcp_postgres.db import Registry
from mcp_postgres.tools import Service

log = structlog.get_logger()


def build_service() -> Service:
    settings = Settings()
    targets = settings.target_map()
    default = settings.resolve_default(targets)
    registry = Registry(targets)
    audit = AuditLog(settings.audit_path)
    log.info("mcp-postgres configured", targets=list(targets), default=default)
    return Service(registry, targets, audit, default)


def build_server(service: Service) -> FastMCP:
    mcp = FastMCP(name="mcp-postgres")

    @mcp.tool()
    async def schema_describe(target: str | None = None, schema: str = "public") -> dict:
        """List tables and columns for a schema on a configured Postgres target."""
        return await service.schema_describe(target=target, schema=schema)

    @mcp.tool()
    async def query_safe(sql: str, target: str | None = None) -> dict:
        """Run a read-only SELECT. Writes, DDL, and multi-statement SQL are rejected; a row cap is enforced."""
        return await service.query_safe(sql=sql, target=target)

    @mcp.tool()
    async def explain_plan(sql: str, target: str | None = None) -> dict:
        """Return the JSON EXPLAIN plan for a read-only SELECT without executing it."""
        return await service.explain_plan(sql=sql, target=target)

    return mcp


def main() -> None:
    server = build_server(build_service())
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
