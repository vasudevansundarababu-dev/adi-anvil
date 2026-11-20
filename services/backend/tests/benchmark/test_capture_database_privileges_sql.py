"""Actual catalogue checks in the disposable SQL fixture; no serving target."""

import ast
import inspect

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row
from test_golden_kyc_sql import connection
from test_golden_kyc_sql import owned as owned_fixture
from test_golden_scheduler_fence_sql import login

from anvil.marketing_capture_database_probe import probe

owned = owned_fixture


def query():
    # Execute the actual production SELECT, not a separately simplified test
    # predicate. AST extraction cannot execute arbitrary application code.
    tree = ast.parse(inspect.getsource(probe))
    values = [node.args[0].value for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr == "execute" and node.args
              and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
              and "FROM pg_roles WHERE rolname=session_user" in node.args[0].value]
    assert len(values) == 1
    return values[0]


def observed(parameters):
    with psycopg.connect(**parameters, row_factory=dict_row) as c:
        c.execute("SET TRANSACTION READ ONLY")
        return c.execute(query()).fetchone()["restricted"]


def test_app_without_private_schema_usage_can_check_but_not_read_references(owned):
    parameters = login(owned, "anvil_app")
    with psycopg.connect(**parameters, row_factory=dict_row) as c:
        assert c.execute("SELECT has_schema_privilege(current_user,'banking_private','USAGE') AS allowed").fetchone()["allowed"] is False
    assert observed(parameters) is True


@pytest.mark.parametrize("schema,table", [("banking_private", "expectations"), ("campaign_private", "references")])
@pytest.mark.parametrize("column_only", [False, True])
def test_table_or_single_column_privilege_is_denied_even_without_schema_usage(owned, schema, table, column_only):
    parameters = login(owned, "anvil_app")
    grant = sql.SQL("SELECT(project_id)") if column_only else sql.SQL("SELECT")
    with connection(owned) as c:
        c.execute(sql.SQL("GRANT {} ON {}.{} TO {}").format(
            grant, sql.Identifier(schema), sql.Identifier(table), sql.Identifier(parameters["user"])))
    assert observed(parameters) is False


def test_missing_reference_does_not_vacuously_pass(owned):
    parameters = login(owned, "anvil_app")
    with connection(owned) as c:
        c.execute("ALTER TABLE campaign_private.references RENAME TO references_qualification_missing")
    try:
        assert observed(parameters) is False
    finally:
        with connection(owned) as c:
            c.execute(sql.SQL("ALTER TABLE campaign_private.references_qualification_missing RENAME TO {}").format(sql.Identifier("references")))


def test_removed_force_rls_is_denied(owned):
    parameters = login(owned, "anvil_app")
    with connection(owned) as c:
        c.execute("ALTER TABLE campaign_private.references NO FORCE ROW LEVEL SECURITY")
    try:
        assert observed(parameters) is False
    finally:
        with connection(owned) as c:
            c.execute("ALTER TABLE campaign_private.references FORCE ROW LEVEL SECURITY")
