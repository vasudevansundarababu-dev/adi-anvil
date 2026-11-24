"""E-008 / D-047: the suite header's pure helpers (default case set names, change formatting)."""

from anvil.rlgym.suites import header


def test_case_set_letters():
    assert [header._letter(i) for i in (0, 1, 25, 26, 27)] == ["A", "B", "Z", "AA", "AB"]


def test_change_formatting():
    assert header._fmt({"complete": 50, "incomplete": 50}) == "complete 50, incomplete 50"
    assert header._fmt(["application_type", "edge_case"]) == "application_type × edge_case"
    assert header._fmt(None) == "none"
    assert header._fmt(40) == "40"
