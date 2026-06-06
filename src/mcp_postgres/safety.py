from __future__ import annotations

import sqlglot
from sqlglot import expressions as exp

# Layer 1 of defense: parse the SQL and refuse anything that is not a single,
# pure read. Layer 2 (read-only transaction + restricted role + statement_timeout)
# lives in db.py and is what actually protects the database if this parser is ever
# fooled. Both must hold. See adr/ADR-001.

# Any of these appearing ANYWHERE in the tree (including inside a CTE or subquery)
# means the statement can mutate state. Reject outright.
_FORBIDDEN = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.TruncateTable,
    exp.Command,  # COPY, VACUUM, SET, GRANT, CALL, and other bare commands
)

_ALLOWED_ROOTS = (exp.Select, exp.Union)


class UnsafeQuery(ValueError):
    """Raised when a query fails the read-only guard. Message is safe to surface."""


def guard_select(sql: str, *, max_rows: int, dialect: str = "postgres") -> str:
    try:
        statements = [s for s in sqlglot.parse(sql, read=dialect) if s is not None]
    except sqlglot.errors.ParseError as e:
        raise UnsafeQuery(f"could not parse SQL: {e}") from e

    if len(statements) != 1:
        raise UnsafeQuery(f"exactly one statement allowed, got {len(statements)}")

    stmt = statements[0]

    forbidden = list(stmt.find_all(*_FORBIDDEN))
    if forbidden:
        kinds = sorted({type(n).__name__ for n in forbidden})
        raise UnsafeQuery(f"write/DDL statement not allowed: {', '.join(kinds)}")

    if not isinstance(stmt, _ALLOWED_ROOTS):
        raise UnsafeQuery(f"only SELECT/UNION allowed, got {type(stmt).__name__}")

    return _apply_limit(stmt, max_rows).sql(dialect=dialect)


def _apply_limit(stmt: exp.Expression, max_rows: int) -> exp.Expression:
    limit = stmt.args.get("limit")
    if limit is None:
        return stmt.limit(max_rows)

    try:
        current = int(limit.expression.name)
    except (AttributeError, ValueError):
        # Non-literal limit (parameter, expression) — clamp to the cap.
        return stmt.limit(max_rows)

    return stmt if current <= max_rows else stmt.limit(max_rows)
