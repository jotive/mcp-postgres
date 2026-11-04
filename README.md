# mcp-postgres

A Model Context Protocol (MCP) server that exposes PostgreSQL to agentic LLM clients (Claude, OpenAI, custom agents) as a small set of **read-only, audited** tools. Schema discovery, guarded SELECTs, and query plans, each behind an explicit tool boundary with a per-call audit log.

Most MCP demos are toy echo servers. The hard case is exposing a real, sensitive resource with the safety primitives production demands. This is a working answer to "what does MCP look like when you actually have to ship it against a database?"

---

## Tools

| tool | does | safety |
|---|---|---|
| `schema_describe` | tables + columns for a schema | server-built SQL, no user input in the query |
| `query_safe` | runs a SELECT, returns capped rows | parser guard + read-only transaction + timeout + row cap |
| `explain_plan` | `EXPLAIN (FORMAT JSON)` for a SELECT | guards SQL, never executes the underlying query |

There is no write tool. Adding one is a deliberate future decision, not a config flag.

## Security model

Two independent layers. Either one alone blocks writes; both are kept on purpose.

### Layer 1: parser guard (`src/mcp_postgres/safety.py`)

Applied to `query_safe` and `explain_plan`. A query is rejected unless it parses (sqlglot, Postgres dialect) to exactly one `SELECT`/`UNION` statement. Rejected:

- multiple statements, including comment-smuggled ones
- `INSERT`/`UPDATE`/`DELETE`/`MERGE`/`DROP`/`CREATE`/`ALTER`/`TRUNCATE` anywhere in the tree, including data-modifying CTEs and subqueries
- bare commands: `COPY`, `SET`/`SET ROLE`/`RESET`, `BEGIN`/`COMMIT`/`ROLLBACK`, `DO`, `CALL`, `VACUUM`, `GRANT`, `LOCK`
- `SELECT ... INTO` and locking clauses (`FOR UPDATE`/`FOR SHARE`)
- calls to functions with side effects or server-side file/network access: `set_config`, `nextval`, `setval`, `pg_notify`, `pg_terminate_backend`, `pg_cancel_backend`, `pg_reload_conf`, `pg_advisory*`, `pg_read_*`, `pg_ls_*`, `loread`, `lowrite`, `query_to_xml*`, `cursor_to_xml*`, and a few others (see `_FORBIDDEN_FUNCTIONS`)
- every function whose name starts with `lo_` or `dblink`, matched by prefix, also when schema-qualified or quoted
- unicode-escaped identifiers (`U&"..."`), which could otherwise spell a denylisted function name in a form the guard cannot see

Compatibility notes:

- `set_config(..., true)` is rejected too, not only the session-wide form. It is a common row-level-security pattern (`set_config('app.tenant_id', ..., true)`), so queries that set RLS context inside the query itself no longer run through these tools. Set such context on the connection or role instead.
- Dollar-quoted strings and comments are not rejected; they parse as inert literals or are dropped, and the guard still sees exactly one statement.
- The guard relies on specific sqlglot expression classes. `pyproject.toml` pins `sqlglot>=26.0.0,<31`, and the module raises `RuntimeError` at import if an expected class is missing, instead of silently skipping the check.

A `LIMIT` is injected, or clamped to the target's `max_rows`.

### Layer 2: database enforcement (`src/mcp_postgres/db.py`)

Every call runs in an explicit `READ ONLY` transaction with `SET LOCAL statement_timeout`. Connections also start with `default_transaction_read_only=on` and the same timeout. Rows are read through a cursor limited to `max_rows`, so the server never materializes more than the cap.

### What is protected

- Writes, DDL and privilege changes through the tools: blocked by the guard and, independently, by the read-only transaction (verified in tests with a role that has full write privileges).
- Runaway queries: cancelled at `statement_timeout_ms`; the pool stays usable afterwards.
- Result size: at most `max_rows` rows per call.
- Session-state tampering (`set_config`, `SET ROLE`, transaction control): rejected by the guard and ineffective at the database level.
- Every call, accepted or rejected, is appended to the audit log.

### What is not protected

- **Reads are not restricted.** Any table the DSN's role can `SELECT` is readable, including through `pg_catalog`. Grant only what an agent should see; use views or row-level security for sensitive columns.
- **`dblink` and foreign data wrappers escape the local transaction.** Their connections to other servers are not covered by this server's read-only transaction or `statement_timeout`, so the guard's name denylist is the only barrier there. Do not install `dblink`, `postgres_fdw` or similar extensions in databases exposed to agents, or make sure the role cannot use them; the database role is the real security boundary.
- **The role is the real boundary.** A superuser or over-privileged DSN can still read files and settings through functions the guard does not list. Use a dedicated role with `SELECT` only and no `pg_read_server_files`, `pg_execute_server_program` or `pg_monitor`. `PUBLIC` can create temporary tables by default on a plain connection; `REVOKE TEMPORARY ON DATABASE ... FROM PUBLIC` if that matters. The test suite runs the attack cases as a non-superuser `SELECT`-only role created in the fixture.
- **The function denylist is not exhaustive.** Extensions may add functions with side effects; unknown ones are allowed through the guard and rely on layer 2.
- **Resource use below the timeout** (CPU, temp files, connections) is not limited beyond `statement_timeout_ms` and the pool size of 4. Set role-level limits (`work_mem`, `temp_file_limit`, `CONNECTION LIMIT`) for hard guarantees.
- **Row cap bounds count, not size.** A few very wide rows can still be large.
- **Parser differential.** The guard relies on sqlglot's reading of the SQL matching Postgres's. Layer 2 exists because that cannot be guaranteed.
- **Audit log** is a local append-only file, not tamper-proof, and records query text, which may contain sensitive literals.
- **No per-agent authorization.** All callers share the configured targets.

See `adr/ADR-001`.

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
pytest -q
```

Guard and service tests need no database. Database enforcement tests run when `MCPPG_TEST_DSN` points at a throwaway database; use a role that can write, so the tests prove the read-only transaction holds when privileges would otherwise allow writes. They are skipped when it is unset. CI runs them against a Postgres 16 service container.

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
