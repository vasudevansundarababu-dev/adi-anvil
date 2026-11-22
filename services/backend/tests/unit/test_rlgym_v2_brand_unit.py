"""RL Gym Evaluation branding (shared/BRANDING.md, work package 2.13): "Praxis", "Anvil" and "Benchmark Utility" never
appear in UI-facing strings: v2 screens, page titles, the Keycloak sign-in theme, the report PDF, and the To do and
report text people read. Code names, routes, package names and comments are exempt."""

import ast
import re

from anvil.config import ROOT

BANNED = re.compile(r"\b(Anvil|Praxis|Benchmark Utility)\b")
WEB = [
    *sorted((ROOT / "apps/web/src/components/rlgym").glob("*.ts*")),
    *sorted((ROOT / "apps/web/src/app/gym").rglob("*.tsx")),
]
THEME = sorted((ROOT / "infra/keycloak/themes/adi-labs-forge").rglob("*.*"))
PYTHON = [
    ROOT / "services/backend/src/anvil/rlgym/results/pdf.py",
    ROOT / "services/backend/src/anvil/rlgym/results/report.py",
    ROOT / "services/backend/src/anvil/rlgym/admin/todo.py",
]
SCRIPTS = [ROOT / "scripts/render-report-pdf.mjs"]


def _strip_js_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"\{\s*/\*.*?\*/\s*\}", "", text, flags=re.S)
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith("//"))


def _python_strings(path):
    tree = ast.parse(path.read_text())
    docstrings = {
        id(n.body[0].value)
        for n in ast.walk(tree)
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef))
        and n.body
        and isinstance(n.body[0], ast.Expr)
        and isinstance(n.body[0].value, ast.Constant)
    }
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            yield node.lineno, node.value


def _hits():
    out = []
    for path in [*WEB, *SCRIPTS]:
        text = _strip_js_comments(path.read_text())
        for n, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("import ") or " from '" in line:
                continue
            if BANNED.search(line):
                out.append(f"{path.relative_to(ROOT)}: {line.strip()[:120]}")
    for path in THEME:
        if path.suffix in (".properties", ".css", ".ftl", ".html"):
            for line in path.read_text().splitlines():
                if not line.lstrip().startswith(("#", "/*", "*")) and BANNED.search(line):
                    out.append(f"{path.relative_to(ROOT)}: {line.strip()[:120]}")
    for path in PYTHON:
        for n, value in _python_strings(path):
            if BANNED.search(value):
                out.append(f"{path.relative_to(ROOT)}:{n}: {value[:120]!r}")
    return out


def test_no_banned_product_names_in_ui_facing_strings():
    assert _hits() == []


def test_the_scan_would_catch_a_banned_name(tmp_path):
    sample = tmp_path / "x.tsx"
    sample.write_text("// ADI Anvil is a code name\n<h2>ADI Anvil · RL Gym</h2>\n")
    lines = [ln for ln in _strip_js_comments(sample.read_text()).splitlines() if BANNED.search(ln)]
    assert lines == ["<h2>ADI Anvil · RL Gym</h2>"]


def test_titles_lockup_and_pdf_use_the_brand():
    brand = (ROOT / "apps/web/src/components/rlgym/Brand.tsx").read_text()
    assert "export const PRODUCT = 'RL Gym Evaluation'" in brand
    assert "export const FAMILY = 'ADI Labs Forge'" in brand
    assert "[page, PRODUCT, FAMILY]" in brand  # <Page> · RL Gym Evaluation · ADI Labs Forge
    from anvil.rlgym.results import pdf

    assert pdf.RUNNING_HEADER == "ADI Labs Forge · RL Gym Evaluation"
    assert pdf._logo_uri().startswith("data:image/png;base64,")
    assert "ADI Labs Forge · RL Gym Evaluation" in SCRIPTS[0].read_text()
    props = (
        ROOT / "infra/keycloak/themes/adi-labs-forge/login/messages/messages_en.properties"
    ).read_text()
    assert "loginAccountTitle=Sign in to RL Gym Evaluation" in props
