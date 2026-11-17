"""Anvil-owned public dataset discovery, integrity and installed readiness."""

from anvil.db import one
from anvil.golden_component_qualification import installed
from anvil.golden_kyc_anvil import source_hash, validate
from anvil.praxis_case_dataset import STATES, CaseDataset


def describe(c, imported):
    validate(c, imported)
    data = CaseDataset.model_validate(imported["manifest"]["case_dataset_manifest"])
    qualified = installed()
    return data.reference().model_dump() | {
        "selector_field": "governing_state",
        "selector_counts": {
            state: sum(m.governing_state == state for m in data.cases) for state in STATES
        },
        "qualified": qualified["ready"],
        "qualification_scope": "technical_dataset_and_runtime_not_legal_acceptance",
        "anvil_requirements": qualified["missing"],
        "review_gates": ["state_and_charter_legal_review", "independent_case_expectation_review"],
    }


def discover(c, project):
    rows = c.execute(
        "SELECT * FROM banking.anvil_imports WHERE project_id=%s AND manifest->>'task_mode'='reusable_state_workflow' AND manifest->>'source_sha256'=%s ORDER BY created_at DESC LIMIT 100",
        (project, source_hash()),
    ).fetchall()
    from anvil.praxis_campaign_registry import discover as campaigns

    return [describe(c, row) for row in rows] + campaigns(c, project)


def lookup(c, project, reference):
    row = one(
        c,
        "SELECT * FROM banking.anvil_imports WHERE project_id=%s AND manifest->>'task_mode'='reusable_state_workflow' AND manifest->'case_dataset'->>'id'=%s AND manifest->'case_dataset'->>'version'=%s AND manifest->'case_dataset'->>'sha256'=%s AND manifest->>'source_sha256'=%s ORDER BY created_at DESC LIMIT 1",
        (project, reference.id, reference.version, reference.sha256, source_hash()),
    )
    if row is None:
        from anvil.praxis_campaign_registry import lookup as campaign

        return campaign(c, project, reference)
    description = describe(c, row)
    return {
        "qualified": description["qualified"],
        "manifest": row["manifest"]["case_dataset_manifest"],
        "import": row,
        "description": description,
    }
