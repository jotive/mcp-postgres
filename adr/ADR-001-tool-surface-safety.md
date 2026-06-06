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

1. **Parser guard (`safety.guard_select`).** Parse with sqlglot. Reject if not exactly one
   statement, if any `INSERT/UPDATE/DELETE/MERGE/DROP/CREATE/ALTER/TRUNCATE/COMMAND` node
   appears anywhere in the tree (catches CTE writes and subquery DML), or if the root is not
   `SELECT`/`UNION`. Inject/clamp a `LIMIT` to the target's `max_rows`.
2. **Database posture (`db.TargetPool`).** Every connection runs with
   `default_transaction_read_only=on` and a hard `statement_timeout`, and the DSN points at a
   **least-privilege role with only `SELECT` grants**. If the parser is ever fooled, the
   database still refuses the write and kills long queries.

The parser alone is not trusted. The role + read-only transaction is the real boundary; the
parser gives fast, legible rejection and the row cap.

## Consequences

- Some legitimate read patterns (e.g. `SELECT ... FOR UPDATE`) are rejected. Acceptable.
- The operator MUST provision a read-only role. A superuser DSN defeats layer 2. Documented in
  the README and `.env.example`.
