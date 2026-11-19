"""The real module entry must delegate to the factory's canonical module."""

import runpy
import sys

import pytest

pytest.importorskip("harbor")
from anvil_harbor import environment


def test_module_launch_uses_canonical_main_and_adapter_identity(monkeypatch):
    observed = []

    async def canonical_main(path):
        observed.append((path, environment.LocalComponentsDocker.__module__))

    monkeypatch.setattr(environment, "main", canonical_main)
    monkeypatch.setattr(sys, "argv", ["anvil_harbor.environment", "synthetic-trial.json"])
    with pytest.warns(RuntimeWarning, match="found in sys.modules"):
        runpy.run_module("anvil_harbor.environment", run_name="__main__")
    assert observed == [("synthetic-trial.json", "anvil_harbor.environment")]
