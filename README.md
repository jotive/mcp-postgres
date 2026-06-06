# mcp-postgres

A Model Context Protocol (MCP) server that exposes PostgreSQL to agentic LLM clients (Claude, OpenAI, custom agents) as a small set of **read-only, audited** tools. Schema discovery, guarded SELECTs, and query plans, each behind an explicit tool boundary with a per-call audit log.

Most MCP demos are toy echo servers. The hard case is exposing a real, sensitive resource with the safety primitives production demands. This is a working answer to "what does MCP look like when you actually have to ship it against a database?"

---

## Tools

| tool | does | safety |
|---|---|---|
| `schema_describe` | tables + columns for a schema | server-built SQL, no user input in the query |
| `query_safe` | runs a SELECT, returns capped rows | parser guard + read-only role + row cap |
| `explain_plan` | `EXPLAIN (FORMAT JSON)` for a SELECT | guards SQL, never executes the underlying query |

There is no write tool. Adding one is a deliberate future decision, not a config flag.

## Safety model — two layers, both must hold

1. **Parser guard** (`src/app/safety.py`). Parses with sqlglot and rejects anything that is not a single pure read: multi-statement SQL, any `INSERT/UPDATE/DELETE/MERGE/DROP/CREATE/ALTER/TRUNCATE` anywhere in the tree (including CTEs and subqueries), bare commands like `COPY`/`GRANT`, and non-SELECT roots. Injects/clamps `LIMIT` to the target's cap.
2. **Database posture** (`src/app/db.py`). Every connection runs in a `default_transaction_read_only` transaction with a hard `statement_timeout`, against a **least-privilege role that only has `SELECT` grants**. If the parser is ever fooled, the database still refuses the write.

The parser is not trusted on its own. The read-only role is the real boundary. See `adr/ADR-001`.

Every call, success or rejection, is written to an append-only JSONL audit log: target, tool, executed SQL, rows, duration, error. See `adr/ADR-002`.

## Install

```bash
pip install -e ".[dev]"
cp .env.example .env   # then set MCPPG_TARGETS to a read-only DSN
```

Provision the read-only role first (snippet in `.env.example`). A superuser DSN defeats the safety model.

## Run

Stdio server, spawned by an MCP client:

```bash
mcp-postgres
```

Wire it into Claude Desktop with `examples/claude_desktop_config.json`. Run it in a container with `docker/Dockerfile`.

## Test

```bash
pytest -q   # safety guard tests are deterministic, no database needed
```

The guard tests are the point: they prove writes, DDL, multi-statement smuggling, and CTE writes are rejected, and that row caps are enforced.

## Stack

Python 3.12 · MCP SDK (`FastMCP`, stdio) · asyncpg · sqlglot · Pydantic v2 + pydantic-settings · structlog · Docker · GitHub Actions.

## Roadmap

| Milestone | Status |
|---|---|
| Repo scaffold | ✅ |
| ADR-001 — tool surface + safety defaults | ✅ |
| ADR-002 — audit log shape + storage | ✅ |
| `schema_describe` tool | ✅ |
| `query_safe` tool with guard + limits | ✅ |
| `explain_plan` tool | ✅ |
| Audit log persistence | ✅ |
| Demo client (Claude Desktop config) | ✅ |
| Multi-target ACL per agent identity | ⬜ |
| Audit sink: DB table / log shipper | ⬜ |

## Author

[Jotive](https://github.com/jotive) · [dev.jotive.com.co](https://dev.jotive.com.co)
