"""Installed package/source/policy controls; no runtime admission or model calls."""

import hashlib
import importlib
import importlib.metadata as metadata
import json
from pathlib import Path
from threading import Event
from time import monotonic

import anvil_harbor

import anvil
from anvil.golden_kyc_evaluators import OPA_POLICIES, opa_guard
from anvil.golden_kyc_service import run_worker
from anvil.golden_kyc_source import source_hash

VERSIONS = {
    "harbor": "0.25.0",
    "openenv": "0.12.0",
    "mcp": "1.30.0",
    "langgraph": "1.2.14",
    "langgraph-checkpoint-postgres": "3.1.3",
    "zen-engine": "2.1.3",
}
for name, expected in VERSIONS.items():
    assert metadata.version(name) == expected, name
for name in (
    "harbor",
    "openenv",
    "mcp",
    "langgraph.graph",
    "langgraph.checkpoint.postgres",
    "anvil.golden_kyc_worker",
    "anvil.golden_kyc_grader",
    "anvil.golden_kyc_service",
    "anvil.marketing_paid_execution",
    "anvil.campaign_grader",
    "anvil_harbor.marketing",
):
    importlib.import_module(name)

matched = 0
for folder, package in (("backend", anvil), ("harbor", anvil_harbor)):
    source = Path("/opt/anvil-runtime-source/services") / folder / "src" / package.__name__
    installed = Path(package.__file__).parent
    for path in source.rglob("*.py"):
        assert path.read_bytes() == (installed / path.relative_to(source)).read_bytes()
        matched += 1
source_sha256 = source_hash()
facts = {name: True for name in OPA_POLICIES}
assert opa_guard(facts)["allow"] is True
assert opa_guard(facts | {"assigned_case": False})["allow"] is False
assert opa_guard({})["allow"] is False
# Execute the actual installed service child entry, without opening a DB.
run_worker(["--help"], deadline=monotonic() + 20, stop=Event())
print(
    json.dumps(
        {
            "scope": "installed_source_packages_and_software_controls_only",
            "source_files_matched": matched,
            "source_sha256": source_sha256,
            "versions": VERSIONS,
            "opa_binary_sha256": hashlib.sha256(Path("/opt/anvil/opa").read_bytes()).hexdigest(),
            "policy_controls": 3,
            "model_calls": 0,
            "native_qualified": False,
        }
    )
)
