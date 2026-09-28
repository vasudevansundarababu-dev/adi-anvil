import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "overrides",
    [
        {"ANVIL_ENV": "production"},
        {"ANVIL_ENV": "staging"},
        {"WEB_ORIGIN": "https://example.invalid"},
    ],
)
def test_development_bootstrap_refuses_nonlocal_configuration(overrides):
    result = subprocess.run(
        [sys.executable, "-c", "import anvil.config"],
        env={**os.environ, **overrides},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "local-only" in result.stderr or "Unqualified web origin" in result.stderr
