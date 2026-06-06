from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class AuditLog:
    # Append-only JSONL. Every tool call lands here whether it succeeds or fails,
    # with the SQL that actually executed (post-guard), rows touched, and duration.
    # See adr/ADR-002 for the field contract and why JSONL.
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
            "ts": datetime.now(timezone.utc).isoformat(),
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
