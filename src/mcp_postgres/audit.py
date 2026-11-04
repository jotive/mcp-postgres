from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


class AuditLog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def record(
        self,
        *,
        target: str,
        tool: str,
        sql: str | None,
        ok: bool,
        rows: int | None = None,
        duration_ms: float | None = None,
        error: str | None = None,
    ) -> None:
        entry = {
            "ts": datetime.now(UTC).isoformat(),
            "target": target,
            "tool": tool,
            "sql": sql,
            "ok": ok,
            "rows": rows,
            "duration_ms": duration_ms,
            "error": error,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
