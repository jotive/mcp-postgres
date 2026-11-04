from __future__ import annotations

import re

import sqlglot
from sqlglot import expressions as exp

_FORBIDDEN_NODE_NAMES = (
    "Insert",
    "Update",
    "Delete",
    "Merge",
    "Drop",
    "Create",
    "Alter",
    "TruncateTable",
    "Command",
    "Into",
    "Set",
    "Copy",
    "Transaction",
    "Commit",
    "Rollback",
    "Use",
    "Pragma",
)

_REQUIRED_NODE_NAMES = (*_FORBIDDEN_NODE_NAMES, "Select", "Union", "Lock", "Func", "Anonymous")


def _require_expression_classes(names: tuple[str, ...]) -> None:
    missing = [name for name in names if not hasattr(exp, name)]
    if missing:
        raise RuntimeError(
            f"installed sqlglot {sqlglot.__version__} lacks expected expression classes: "
            f"{', '.join(missing)}"
        )


_require_expression_classes(_REQUIRED_NODE_NAMES)

_FORBIDDEN = tuple(getattr(exp, name) for name in _FORBIDDEN_NODE_NAMES)

_UNICODE_ESCAPED_IDENTIFIER = re.compile(r'u&\s*"', re.IGNORECASE)

_FORBIDDEN_FUNCTIONS = frozenset(
    {
        "set_config",
        "nextval",
        "setval",
        "pg_notify",
        "pg_terminate_backend",
        "pg_cancel_backend",
        "pg_reload_conf",
        "pg_rotate_logfile",
        "pg_switch_wal",
        "pg_create_restore_point",
        "pg_logical_emit_message",
        "query_to_xml",
        "query_to_xml_and_xmlschema",
        "query_to_xmlschema",
        "cursor_to_xml",
        "cursor_to_xmlschema",
        "loread",
        "lowrite",
    }
)

_FORBIDDEN_FUNCTION_PREFIXES = (
    "pg_advisory",
    "pg_try_advisory",
    "pg_read_",
    "pg_ls_",
    "pg_stat_file",
    "lo_",
    "dblink",
)

_ALLOWED_ROOTS = (exp.Select, exp.Union)


class UnsafeQuery(ValueError):
    """Raised when a query fails the read-only guard. Message is safe to surface."""


def guard_select(sql: str, *, max_rows: int, dialect: str = "postgres") -> str:
    if _UNICODE_ESCAPED_IDENTIFIER.search(sql):
        raise UnsafeQuery("unicode-escaped identifiers are not allowed")

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

    blocked = sorted({name for name in _called_function_names(stmt) if _is_forbidden_function(name)})
    if blocked:
        raise UnsafeQuery(f"function not allowed: {', '.join(blocked)}")

    if stmt.find(exp.Lock):
        raise UnsafeQuery("locking clauses are not allowed")

    if not isinstance(stmt, _ALLOWED_ROOTS):
        raise UnsafeQuery(f"only SELECT/UNION allowed, got {type(stmt).__name__}")

    return _apply_limit(stmt, max_rows).sql(dialect=dialect)


def _called_function_names(stmt: exp.Expression) -> set[str]:
    names: set[str] = set()
    for node in stmt.find_all(exp.Func):
        if isinstance(node, exp.Anonymous):
            names.add(node.name.lower())
        else:
            names.add(node.sql_name().lower())
    return names


def _is_forbidden_function(name: str) -> bool:
    return name in _FORBIDDEN_FUNCTIONS or name.startswith(_FORBIDDEN_FUNCTION_PREFIXES)


def _apply_limit(stmt: exp.Expression, max_rows: int) -> exp.Expression:
    limit = stmt.args.get("limit")
    if limit is None:
        return stmt.limit(max_rows)

    try:
        current = int(limit.expression.name)
    except (AttributeError, ValueError):
        return stmt.limit(max_rows)

    return stmt if current <= max_rows else stmt.limit(max_rows)
