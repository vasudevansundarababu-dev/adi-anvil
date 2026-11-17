"""Anvil-owned whole-campaign dataset discovery; no authoring or run dispatch."""

import os

from anvil.db import one
from anvil.praxis_generic_contract import digest
from anvil.praxis_marketing_contract import CampaignDataset


def describe(row, qualification, *, source, runtime, image):
    data = CampaignDataset.model_validate(row["manifest"])
    if (
        data.id != row["dataset_key"]
        or data.version != row["version"]
        or data.reference().sha256 != row["manifest_sha256"]
        or digest(row["fixture_manifest"]) != row["fixture_manifest_sha256"]
        or row["source_sha256"] != source
    ):
        raise ValueError("Immutable campaign dataset integrity/source mismatch")
    qualified = False
    if qualification and image:
        receipt = qualification["receipt"]
        expected = {
            "schema_version": "anvil.campaign-dataset-qualification.v1",
            "origin": "independent_qa",
            "dataset_sha256": data.reference().sha256,
            "fixture_manifest_sha256": row["fixture_manifest_sha256"],
            "source_sha256": source,
            "runtime_sha256": runtime,
            "runtime_image_sha256": image,
        }
        controls = receipt.get("controls", {})
        qualified = (
            digest(receipt) == qualification["receipt_sha256"]
            and qualification["source_sha256"] == source
            and qualification["runtime_sha256"] == runtime
            and qualification["runtime_image_sha256"] == image
            and all(receipt.get(key) == value for key, value in expected.items())
            and all(
                isinstance(controls.get(name), dict)
                and controls[name].get("status") == "passed"
                and isinstance(controls[name].get("evidence_sha256"), str)
                and len(controls[name]["evidence_sha256"]) == 64
                for name in (
                    "membership",
                    "released_evidence",
                    "private_isolation",
                    "role_scope",
                    "reset_isolation",
                )
            )
        )
    return data.reference().model_dump() | {
        "schema_version": data.schema_version,
        "selector_field": "dataset",
        "selector_counts": {"all": data.case_count},
        "qualified": qualified,
        "qualification_scope": "technical_case_pack_and_runtime_not_semantic_or_human_acceptance",
        "anvil_requirements": []
        if qualified
        else [
            {
                "code": "AV_CAMPAIGN_DATASET_QUALIFICATION_REQUIRED",
                "owner": "anvil",
                "status": "blocked",
            }
        ],
        "review_gates": ["case_expectations_and_semantic_calibration_not_established"],
    }


def binding(c, project, row):
    from anvil.golden_kyc_anvil import source_hash as runtime_hash
    from anvil.praxis_template_registry import source_hash

    qualification = one(
        c,
        "SELECT q.* FROM anvil.campaign_dataset_qualifications q WHERE q.project_id=%s AND q.dataset_id=%s AND q.expires_at>clock_timestamp() AND NOT EXISTS(SELECT 1 FROM anvil.campaign_dataset_revocations r WHERE r.qualification_id=q.id) ORDER BY q.created_at DESC,q.id DESC LIMIT 1",
        (project, row["id"]),
    )
    description = describe(
        row,
        qualification,
        source=source_hash(),
        runtime=runtime_hash(),
        image=os.environ.get("ANVIL_RUNTIME_IMAGE_DIGEST"),
    )
    return {
        "qualified": description["qualified"],
        "manifest": row["manifest"],
        "import": row,
        "description": description,
        "qualification": qualification,
    }


def lookup(c, project, reference):
    from anvil.praxis_template_registry import source_hash

    row = one(
        c,
        "SELECT * FROM anvil.campaign_dataset_versions WHERE project_id=%s AND dataset_key=%s AND version=%s AND manifest_sha256=%s AND source_sha256=%s",
        (project, reference.id, reference.version, reference.sha256, source_hash()),
    )
    return binding(c, project, row) if row else None


def discover(c, project):
    from anvil.praxis_template_registry import source_hash

    rows = c.execute(
        "SELECT * FROM anvil.campaign_dataset_versions WHERE project_id=%s AND source_sha256=%s ORDER BY created_at DESC,id DESC LIMIT 100",
        (project, source_hash()),
    ).fetchall()
    return [binding(c, project, row)["description"] for row in rows]
