# mcp-postgres

> Status: **planned** — repo scaffold. Code lands as the design solidifies.

A Model Context Protocol (MCP) server that exposes PostgreSQL as a set of safe, audited tools for agentic LLM clients (Claude, OpenAI, custom agents). Schema discovery, parameterized queries, query plans — all behind explicit tool boundaries with per-call audit log.

---

## What this will demonstrate

- **MCP applied, not playground** — concrete server with three useful tools (`schema_describe`, `query_safe`, `explain_plan`) instead of a tutorial echo server.
- **Safety boundaries on a database tool** — query allowlist, row limit caps, statement timeout, role-scoped credentials, no DDL exposure by default.
- **Audit log per agent call** — every tool call recorded with agent id, prompt context hash, executed SQL, rows touched, duration. Useful for compliance + debugging.
- **Multi-database routing** — one MCP process can expose multiple Postgres targets (dev / staging / shadow read-replica) with per-target ACL.
- **Production posture** — Docker, healthchecks, structured logs, metrics endpoint.

## Tentative stack

Python 3.12 · MCP SDK · psycopg3 / asyncpg · Pydantic v2 · Docker · Optional integration with `tenant-aware-llm-gateway` for multi-tenant audit storage

## Roadmap

| Milestone | Status |
|---|---|
| Repo scaffold | ✅ |
| ADR-001 — tool surface + safety defaults | ⬜ |
| ADR-002 — audit log shape + storage | ⬜ |
| `schema_describe` tool | ⬜ |
| `query_safe` tool with allowlist + limits | ⬜ |
| `explain_plan` tool | ⬜ |
| Audit log persistence | ⬜ |
| Demo client (Claude / agent SDK) | ⬜ |

## Why this exists

Most MCP demos are toy echo servers. The interesting case is exposing a real, sensitive resource (a database) with the safety primitives that production demands. This repo is a working answer to "what does MCP look like when you actually need to ship it?"

## Author

[Jotive](https://github.com/jotive) · [dev.jotive.com.co](https://dev.jotive.com.co)
