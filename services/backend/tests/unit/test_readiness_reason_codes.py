"""Server readiness reason codes must match the checked-in web catalog contract."""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CONTRACT = ROOT / "contracts/readiness/reason-codes.v1.json"
SOURCES = {
    "workspace_preparation.py": {"readiness"},
    "workspace_execution.py": {"readiness", "plan_readiness"},
    "workspace_models.py": {"selection_issues"},
}
COLLECTORS = {"missing", "issues", "reasons"}


def _strings(node):
    if isinstance(node, ast.List):
        return [
            e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)
        ]
    return []


def scan(source, functions):
    """Literal codes appended to, or assigned/returned as, reason lists in readiness functions.

    Codes built dynamically are not detected; the web catalog's generic fallback covers them.
    """
    codes = set()
    for func in ast.walk(ast.parse(source)):
        if not isinstance(func, ast.FunctionDef) or func.name not in functions:
            continue
        for node in ast.walk(func):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "append"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in COLLECTORS
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                codes.add(node.args[0].value)
            elif isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in COLLECTORS for t in node.targets
            ):
                codes.update(_strings(node.value))
            elif isinstance(node, ast.Return) and node.value is not None:
                codes.update(_strings(node.value))
    return codes


def produced_codes():
    codes = set()
    for name, functions in SOURCES.items():
        codes |= scan((ROOT / "services/backend/src/anvil" / name).read_text(), functions)
    return codes


def test_contract_lists_exactly_the_server_produced_reason_codes():
    contract = json.loads(CONTRACT.read_text())
    assert contract["codes"] == sorted(contract["codes"])
    assert len(contract["codes"]) == len(set(contract["codes"]))
    assert set(contract["codes"]) == produced_codes()


def test_scanner_detects_new_codes_and_ignores_filters():
    source = """
def readiness(c):
    obsolete = {"filtered_out"}
    reasons = ["initial_code"]
    missing = [r for r in reasons if r not in obsolete]
    issues = [r for r in missing if r != "not_appended"]
    missing.append("added_code")
    other.append("unrelated_list")
    return {"missing": missing}

def selection_issues(c):
    return ["returned_code"]

def unrelated():
    missing = []
    missing.append("outside_scope")
"""
    found = scan(source, {"readiness", "selection_issues"})
    assert found == {"initial_code", "added_code", "returned_code"}
