from __future__ import annotations

import asyncpg

from mcp_postgres.config import TargetConfig


class TargetPool:
    def __init__(self, cfg: TargetConfig) -> None:
        self.cfg = cfg
        self._pool: asyncpg.Pool | None = None

    async def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self.cfg.dsn,
                min_size=1,
                max_size=4,
                server_settings={
                    "default_transaction_read_only": "on",
                    "statement_timeout": str(self.cfg.statement_timeout_ms),
                    "application_name": f"mcp-postgres:{self.cfg.name}",
                },
            )
        return self._pool

    async def fetch(self, sql: str, max_rows: int) -> list[dict]:
        pool = await self.pool()
        async with pool.acquire() as conn, conn.transaction(readonly=True):
            await conn.execute(f"SET LOCAL statement_timeout = {int(self.cfg.statement_timeout_ms)}")
            cursor = await conn.cursor(sql)
            rows = await cursor.fetch(max_rows)
        return [dict(r) for r in rows]

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None


class Registry:
    def __init__(self, targets: dict[str, TargetConfig]) -> None:
        self._pools = {name: TargetPool(cfg) for name, cfg in targets.items()}

    def get(self, name: str) -> TargetPool:
        pool = self._pools.get(name)
        if pool is None:
            raise ValueError(f"unknown target '{name}'; known: {', '.join(self._pools)}")
        return pool

    async def close(self) -> None:
        for pool in self._pools.values():
            await pool.close()
