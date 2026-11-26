"""New run (run 3, 25 Nov 2026): choosing "Custom" pre-ticked the current line-up (three golden-KYC mocks), so twice a
run started with "Mock agent · diligent" instead of "Mock agent · Judgment diligent". Custom now starts with no model
ticked, and the Models list groups the Judgment mocks under their own heading, apart from the golden-KYC mocks."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SRC = (ROOT / "apps/web/src/components/rlgym/Runs.tsx").read_text()


def test_custom_starts_empty():
    assert "if (e.target.value === 'custom') setCustom([]);" in SRC
    assert "setCustom(members)" not in SRC


def test_the_models_are_grouped_and_the_judgment_mocks_labelled():
    assert "function modelGroup(" in SRC
    assert "KYC Judgment mocks (synthetic)" in SRC
    assert "Golden KYC mocks (synthetic)" in SRC
    assert "mock-judgment-" in SRC
