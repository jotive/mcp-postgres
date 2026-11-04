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


@pytest.mark.parametrize(
    "sql",
    [
        "SET ROLE postgres",
        "SET SESSION AUTHORIZATION postgres",
        "SET default_transaction_read_only = off",
        "RESET ALL",
        "BEGIN READ WRITE",
        "COMMIT",
        "ROLLBACK",
        "START TRANSACTION",
        "COPY (SELECT 1) TO PROGRAM 'id'",
        "COPY users FROM '/etc/passwd'",
        "DO $$ BEGIN DELETE FROM users; END $$",
        "CALL do_things()",
        "VACUUM users",
        "SELECT * INTO new_table FROM users",
        "SELECT * FROM users FOR UPDATE",
        "SELECT * FROM users FOR SHARE",
        "LOCK TABLE users",
        "EXPLAIN ANALYZE DELETE FROM users",
        "WITH t AS (UPDATE users SET name = 'x' RETURNING id) SELECT * FROM t",
        "WITH t AS (INSERT INTO users VALUES (1) RETURNING id) SELECT * FROM t",
        "SELECT * FROM (DELETE FROM users RETURNING id) d",
    ],
)
def test_state_changing_statements_rejected(sql):
    with pytest.raises(UnsafeQuery):
        guard_select(sql, max_rows=100)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT set_config('default_transaction_read_only', 'off', false)",
        "SELECT SET_CONFIG('statement_timeout', '0', false)",
        "SELECT pg_catalog.set_config('statement_timeout', '0', false)",
        "SELECT \"set_config\"('statement_timeout', '0', false)",
        "SELECT * FROM users WHERE id = (SELECT set_config('role', 'postgres', false)::int)",
        "SELECT nextval('users_id_seq')",
        "SELECT setval('users_id_seq', 1)",
        "SELECT pg_advisory_lock(1)",
        "SELECT pg_try_advisory_lock(1)",
        "SELECT pg_advisory_xact_lock(1)",
        "SELECT pg_notify('c', 'p')",
        "SELECT pg_terminate_backend(1)",
        "SELECT pg_cancel_backend(1)",
        "SELECT pg_reload_conf()",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT pg_read_binary_file('/etc/passwd')",
        "SELECT pg_ls_dir('/')",
        "SELECT lo_import('/etc/passwd')",
        "SELECT lo_export(1, '/tmp/x')",
        "SELECT * FROM dblink('host=x', 'select 1') AS t(a int)",
        "SELECT query_to_xml('DELETE FROM users', true, true, '')",
    ],
)
def test_side_effect_functions_rejected(sql):
    with pytest.raises(UnsafeQuery):
        guard_select(sql, max_rows=100)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT count(*) FROM users",
        "SELECT lower(name), now(), current_setting('statement_timeout') FROM users",
        "WITH recent AS (SELECT id FROM users) SELECT * FROM recent",
        "SELECT id FROM users UNION ALL SELECT id FROM users",
        "SELECT u.id FROM users u JOIN users v ON v.id = u.id ORDER BY u.id",
        "SELECT pg_sleep(0.01)",
    ],
)
def test_normal_reads_accepted(sql):
    assert guard_select(sql, max_rows=100)


def test_limit_clamped_on_union():
    out = guard_select("SELECT id FROM users UNION SELECT id FROM users LIMIT 5000", max_rows=100)
    assert "5000" not in out


def test_non_literal_limit_clamped():
    out = guard_select("SELECT id FROM users LIMIT (SELECT 999999)", max_rows=100)
    assert "999999" not in out
