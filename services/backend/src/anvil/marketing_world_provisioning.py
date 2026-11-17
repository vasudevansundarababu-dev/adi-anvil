"""Build a complete private source candidate from an existing immutable dataset.

No task, review, qualification, environment, SQL row or benchmark is created.
Only the operator supplies the existing task/revision and rights receipt binding.
"""

import hashlib
import secrets
from pathlib import Path

from anvil.marketing_paid_world import CampaignContext
from anvil.marketing_world_activation_definition import paths as activation_paths
from anvil.marketing_world_activation_definition import with_activation
from anvil.marketing_world_calendar import propose, with_program
from anvil.marketing_world_definition import COLLECTIONS, definition
from anvil.marketing_world_finance import FILES
from anvil.marketing_world_funding_definition import with_finance
from anvil.marketing_world_opening_definition import with_opening
from anvil.marketing_world_population import paths as population_paths
from anvil.marketing_world_population_definition import branch_declarations, with_population
from anvil.marketing_world_service_sources import CASE_FILES, SHARED_FILES, normalize, with_services
from anvil.praxis_marketing_contract import CampaignDataset


def needed_files(case):
    return (activation_paths(case) | population_paths(case)
            | {f"cases/{case}/{name}" for name in (*CASE_FILES, *FILES)}
            | {"shared/" + name for name in SHARED_FILES}
            | {f"reviewer_only/us-pair/{case}/reuse-test-{branch}/conditional_campaign_approval.json"
               for branch in ("positive", "null", "negative")})


def load_files(root, case, pins):
    """Read only the named environment sources, never answer/agent-output files."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Original owned source directory required")
    root = root.resolve()
    files, total = {}, 0
    for path in sorted(needed_files(case)):
        file = root / path
        if (not file.is_file() or not file.resolve().is_relative_to(root)
                or any(parent.is_symlink() for parent in (file, *file.parents) if parent != root and root in parent.parents)):
            raise ValueError("Original regular source files without symlink aliases required")
        with file.open("rb") as stream:
            raw = stream.read(16777217)
        total += len(raw)
        if not 0 < len(raw) <= 16777216 or total > 134217728 or hashlib.sha256(raw).hexdigest() != pins.get(path):
            raise ValueError("Existing bounded operator source inventory mismatch")
        files[path] = raw
    return files


def build(case, dataset, execution, *, task_id, revision_id, rights_receipt_sha256, files, branch_seed=None):
    dataset_model = CampaignDataset.model_validate(dataset["manifest"])
    reference = dataset_model.reference()
    member = next((row for row in dataset_model.cases if row.id == case), None)
    if member is None:
        raise ValueError("Actual existing dataset case required")
    pins = dataset["fixture_manifest"]["source_hashes"]
    services = normalize(case, files, pins, execution)
    calendar = propose(case, files, pins, services)
    context = CampaignContext(
        case_id=case, locale="en-US", campaign_ref=case + "_campaign", task_id=task_id, revision_id=revision_id,
        dataset_id=reference.id, dataset_version=reference.version, dataset_sha256=reference.sha256,
        public_source_refs=["anvil-source-sha256:" + pins[path] for path in ("shared/product.json", "shared/campaign_contract.json")],
        currency="USD", business_budget_minor=services["shared"]["campaign_contract"]["budget_usd_minor"],
        origin="fictional_campaign_environment",
    )
    base = {"schema_version": "anvil.marketing-private-world-definition.v1", "case_id": case,
            "case_snapshot_sha256": member.snapshot_sha256, "execution_sha256": services["execution_sha256"],
            "fixture_manifest_sha256": dataset["fixture_manifest_sha256"],
            "source_manifest_sha256": dataset["fixture_manifest_sha256"], "rights_receipt_sha256": rights_receipt_sha256,
            "campaign_context": context.model_dump(mode="json"),
            "start": services["shared"]["campaign_contract"]["start"] + "T00:00:00Z",
            "branch_seed": secrets.token_hex(32) if branch_seed is None else branch_seed,
            "branch_cycle": ["positive", "null", "negative"], "source_hashes": pins,
            "public_columns": {name: [] for name in COLLECTIONS}, "records": {name: [] for name in COLLECTIONS},
            "windows": [{**row, "window_ref": "anvil-source-review:" + case + ":" + str(row["week"]) + ":" + pins[f"cases/{case}/weekly_reports.jsonl"]}
                        for row in calendar["windows"]]}
    base["records"]["work"] = branch_declarations(case, services, pins)
    base["public_columns"]["work"] = ["id", "source_kind"]
    service_world = with_program(with_services(base, files, execution), calendar)
    complete = with_population(with_opening(with_activation(with_finance(service_world, files), files)), files)
    world = definition(complete)
    return world.model_dump(mode="json")
