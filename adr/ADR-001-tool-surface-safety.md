# ADR-001 — Tool surface and safety defaults

Status: accepted · 2026-06-06

## Context

Exposing a database to an autonomous agent is the dangerous case MCP demos avoid. The agent
can be prompt-injected, can hallucinate a destructive query, or can simply be wrong. The
server must make the destructive path impossible, not merely discouraged.

## Decision

**Three tools, read-only only:**

- `schema_describe(target, schema)` — tables + columns from `information_schema`. Server-built
  SQL, no user SQL.
- `query_safe(sql, target)` — runs a guarded SELECT, returns rows (capped).
- `explain_plan(sql, target)` — guards the SQL, then runs `EXPLAIN (FORMAT JSON)` without
  executing the underlying query.

No write tool exists. Adding one is a deliberate future ADR, not a config flag.

**Two independent layers of defense — both must hold:**

1. **AST guard (`safety.guard_select`).** Parse with sqlglot. Reject if not exactly one
   statement, if any write/DDL/command node appears anywhere in the tree (`INSERT`, `UPDATE`,
   `DELETE`, `MERGE`, `DROP`, `CREATE`, `ALTER`, `TRUNCATE`, bare commands, `SELECT INTO`,
   `SET`, `COPY`, transaction control — this catches CTE writes and subquery DML), if the
   root is not `SELECT`/`UNION`, if a locking clause is present, if a denylisted function
   is called (side effects, server-side file access, `lo_*`, `dblink*`, `set_config`), or if
   a unicode-escaped identifier (`U&"..."`) is used. Inject/clamp a `LIMIT` to the target's
   `max_rows`. The sqlglot version range is pinned and the module fails at import if an
   expected expression class is missing.
2. **Read-only transaction (`db.TargetPool.fetch`).** Every call runs in an explicit
   `READ ONLY` transaction with `SET LOCAL statement_timeout`, reading through a cursor
   limited to `max_rows`. Connections also start with `default_transaction_read_only=on`
   and the same timeout.

Neither layer replaces the **database role**: the DSN must point at a least-privilege role
with only `SELECT` grants. The AST guard gives fast, legible rejection and the row cap; the
read-only transaction stops writes the guard misses; the role limits what a read can reach.
The read-only transaction does not cover connections that leave the local server (`dblink`,
foreign data wrappers), so there the denylist is the only barrier and the role is the real
boundary.

## Consequences

- Some legitimate read patterns (e.g. `SELECT ... FOR UPDATE`, `set_config(..., true)` for RLS context) are rejected. Acceptable.
- The operator MUST provision a read-only role. A superuser DSN defeats layer 2. Documented in
  the README and `.env.example`.
