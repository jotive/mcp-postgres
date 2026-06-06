import pytest

from mcp_postgres.safety import UnsafeQuery, guard_select


def test_plain_select_passes_and_gets_limit():
    out = guard_select("SELECT id, name FROM users", max_rows=100)
    assert "LIMIT 100" in out.upper()


def test_existing_small_limit_kept():
    out = guard_select("SELECT id FROM users LIMIT 10", max_rows=100)
    assert "LIMIT 10" in out.upper()


def test_oversized_limit_clamped():
    out = guard_select("SELECT id FROM users LIMIT 999999", max_rows=100)
    assert "LIMIT 100" in out.upper()
    assert "999999" not in out


def test_subquery_select_passes():
    sql = "SELECT * FROM (SELECT id FROM users WHERE active) t"
    out = guard_select(sql, max_rows=50)
    assert out  # parsed and emitted, no raise


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO users (id) VALUES (1)",
        "UPDATE users SET name = 'x'",
        "DELETE FROM users",
        "DROP TABLE users",
        "ALTER TABLE users ADD COLUMN x int",
        "TRUNCATE users",
        "CREATE TABLE t (id int)",
        "GRANT SELECT ON users TO public",
        "COPY users TO '/tmp/out.csv'",
    ],
)
def test_writes_and_ddl_rejected(sql):
    with pytest.raises(UnsafeQuery):
        guard_select(sql, max_rows=100)


def test_multi_statement_rejected():
    with pytest.raises(UnsafeQuery):
        guard_select("SELECT 1; DROP TABLE users", max_rows=100)


def test_comment_smuggled_second_statement_rejected():
    with pytest.raises(UnsafeQuery):
        guard_select("SELECT 1 -- ok\n; DELETE FROM users", max_rows=100)


def test_cte_with_write_rejected():
    sql = "WITH moved AS (DELETE FROM users RETURNING id) SELECT * FROM moved"
    with pytest.raises(UnsafeQuery):
        guard_select(sql, max_rows=100)


def test_garbage_rejected():
    with pytest.raises(UnsafeQuery):
        guard_select("this is not sql ;;;", max_rows=100)
