# ADR-002 — Audit log shape and storage

Status: accepted · 2026-06-06

## Context

"An agent queried our database" is not an acceptable audit answer. Compliance and debugging
both need: which target, which tool, the exact SQL that ran, how many rows, how long, and
whether it failed. Rejected calls matter as much as successful ones, because a stream of
rejections is a prompt-injection signal.

## Decision

- **Append-only JSONL**, one object per tool call, written in `audit.AuditLog`. JSONL because
  it is trivially greppable, streamable into Loki/BigQuery/anything, and never needs a schema
  migration.
- **Every call is recorded**, success or failure, including guard rejections (with the
  original SQL and the rejection reason).
- For `query_safe`/`explain_plan` the recorded SQL is the **post-guard** SQL that actually hit
  the database (with the injected `LIMIT` and `EXPLAIN` wrapper), so the log reflects reality,
  not intent.

### Field contract

| field | meaning |
|---|---|
| `ts` | ISO-8601 UTC timestamp |
| `target` | resolved target name |
| `tool` | `schema_describe` / `query_safe` / `explain_plan` |
| `sql` | SQL as executed (post-guard) or, on rejection, the original SQL |
| `ok` | did the call succeed |
| `rows` | rows returned (null on failure) |
| `duration_ms` | execution time |
| `error` | rejection or DB error message (null on success) |

## Consequences

- Local file by default. Production swaps the sink (DB table, log shipper) behind the same
  `AuditLog.record` interface — the optional integration with a multi-tenant audit store noted
  in the README plugs in here.
- No prompt/response content is logged, only SQL and metadata. Avoids storing PII pulled by a
  query while still giving a full action trail.
