"""E-006 §3: "Applies here?" is computed from the suite's task tools and the customer-facing operations."""

from anvil.rlgym.suites import safety_table

TOOLS = {
    "application.read",
    "document.read",
    "identity.check",
    "screening.check",
    "information.request",
    "finding.write",
    "recommend",
}


def test_applies_with_reasons():
    assert safety_table.applies("aml_tipping_off", TOOLS, {"information.request"})[0] == "Yes"
    verdict, why = safety_table.applies(
        "aml_tipping_off", TOOLS - {"screening.check"}, {"information.request"}
    )
    assert verdict == "No" and "screening.check" in why
    verdict, why = safety_table.applies("personal_data_leakage", TOOLS, set())
    assert verdict == "Partly" and "final answer" in why  # no customer-facing operation
    assert safety_table.applies("assigned_case_isolation", set(), set())[0] == "Yes"
    assert safety_table.applies("made_up", TOOLS, set())[0] == "Partly"
