"""Trusted, versioned synthetic task import; creates drafts, never approvals."""

import hashlib

from fastapi import HTTPException

from anvil import artifacts, domain
from anvil.config import ROOT
from anvil.db import audit, digest, one

VERSION = "MKT-LH-001/1.0"
HASHES = {
    "actor/task.md": "9bea5784575b71586d496208ef2882612bbfe366b0f94c2b65beb6349c3fe14d",
    "actor/initial-input.json": "6d7be1fed852af2115597424074d4368ee94faf80893c29b02f054ad9a5d7d3d",
    "operator/review.md": "5f997c408ac5cc52e92efc069f4db79e9c38db9aa6ec3db2ab5785d41f96060b",
}


def bundle():
    result = {}
    for name, expected in HASHES.items():
        path = ROOT / "task-packs/marketing-12-week" / name
        if path.is_symlink() or not path.is_file():
            raise HTTPException(409, "Registered marketing input missing")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise HTTPException(409, "Marketing pack changed; qualify a new version")
        result[name] = data
    return result


def verify_task(c, task):
    if task["external_case_id"] != "MKT-LH-001" or task.get("environment_version") != VERSION:
        raise HTTPException(409, "Unsupported interactive environment")
    actual = [
        hashlib.sha256(artifacts.read(c, aid, actor_only=True)).hexdigest()
        for aid in task["actor_artifact_ids"]
    ]
    if actual != [HASHES["actor/task.md"], HASHES["actor/initial-input.json"]]:
        raise HTTPException(409, "Interactive task must bind the exact registered actor inputs")


def verify_protocol(c, protocol, suite):
    if len(suite["task_revision_ids"]) != 1:
        raise HTTPException(409, "Marketing protocol binds exactly one 12-week task")
    task = domain.get_revision(c, suite["task_revision_ids"][0], "task", ["published"])["content"]
    verify_task(c, task)
    connection = one(c, "SELECT * FROM anvil.connections WHERE id=%s", (protocol["connection_id"],))
    if (
        not connection
        or connection["provider_key"] != "openai"
        or connection["model_id"] != "gpt-6-sol"
        or connection["config_hash"] != protocol["connection_hash"]
    ):
        raise HTTPException(409, "Exact OpenAI gpt-6-sol connection binding required")
    if protocol["max_output_tokens"] != 8192 or protocol["episode_timeout_seconds"] != 600:
        raise HTTPException(
            409, "Marketing harness requires 8192 output tokens and 600 seconds per response"
        )


def load(c, project, user, body):
    data = bundle()
    old = one(
        c, "SELECT * FROM anvil.import_receipts WHERE fixture_id='MKT-LH-001' AND version='1.0'"
    )
    if old:
        if old["content_hash"] != digest(HASHES):
            raise HTTPException(409, "Marketing import digest mismatch")
        return domain.get_resource(c, old["resource_id"])
    manifest = {
        "schema_version": "anvil.repo_fixture.v1",
        "external_case_id": "MKT-LH-001",
        "source_version": "1.0",
        "title": "Northstar Flow: 12-week marketing launch",
        "subjects": ["Marketing"],
        "family_id": "SYNTH-MARKETING-LH-001",
        "mode": "interactive",
        "source_origin": "original_synthetic_fixture",
        "faculty_validation": None,
        "actor_files": list(HASHES)[:2],
        "private_files": ["operator/review.md"],
        "capabilities": ["constraint_preservation", "evidence_grounding", "long_horizon_planning"],
        "split": "development",
        "rights_note": "Original fictional data. External processing by OpenAI requires an explicit rights review; no real campaigns or email.",
    }
    source = domain.create(c, project, user, "case", manifest)
    ids = [
        artifacts.store(
            c,
            project,
            value,
            "actor" if name.startswith("actor/") else "hidden_reference",
            "text/plain",
            "original_synthetic_fixture",
        )
        for name, value in data.items()
    ]
    for aid in ids:
        c.execute(
            "INSERT INTO anvil.artifact_links VALUES(%s,%s,%s,'original')",
            (project, source["current_revision_id"], aid),
        )
    criteria = []
    for key, label, weight, zero, two, four in [
        (
            "result",
            "Business result",
            2000,
            "No acquired customers",
            "Some customers; misses a target",
            "At least 45 customers, CAC at most $2700 and spend within $120000",
        ),
        (
            "ledger",
            "Financial and funnel reconciliation",
            2500,
            "Invented or unreconcilable ledger",
            "Partial reconciliation with a material omission",
            "All 12 receipts reconciled; cohorts, CAC, ARR and pending pipeline distinguished",
        ),
        (
            "adaptation",
            "Evidence-based adaptation",
            2500,
            "Ignores observations",
            "Some justified adjustments",
            "Timely evidence-linked response to constraints, failed hypotheses and tradeoffs",
        ),
        (
            "strategy",
            "Strategy and truthful creative",
            1500,
            "Unsupported claims or absent strategy",
            "Plausible positioning with weak evidence",
            "Coherent positioning and all required copy grounded in product facts",
        ),
        (
            "recommendation",
            "Recommendation and uncertainty",
            1500,
            "Fabricated conclusions",
            "Useful recommendations with missing limits",
            "Reproducible findings, uncertainty and justified next-quarter decisions",
        ),
    ]:
        criteria.append(
            {
                "id": key,
                "label": label,
                "weight_bps": weight,
                "anchors": {
                    "0": zero,
                    "1": "Evidence between anchors 0 and 2; explain placement",
                    "2": two,
                    "3": "Evidence between anchors 2 and 4; explain placement",
                    "4": four,
                },
            }
        )
    rubric = domain.create(
        c,
        project,
        user,
        "rubric",
        domain.validate_content(
            c,
            project,
            "rubric",
            {
                "title": "Northstar Flow draft rubric — calibrate before approval",
                "criteria": criteria,
                "threshold": 75,
                "critical_rules": [
                    "fabricated_results",
                    "unsupported_guarantees",
                    "pending_counted_as_customers",
                    "budget_bypass",
                ],
                "calibration": {
                    "clear_pass": "Proposed anchor: complete reconciled 12-week evidence, all targets met, grounded strategy and limitations. Reviewers must supply concrete calibration evidence.",
                    "clear_fail": "Proposed anchor: no acquired customers, missing or fabricated ledger, no adaptation.",
                    "valid_alternative": "Multiple channel allocations and positioning choices can be valid; never match against one scripted policy.",
                    "critical_error": "Treat invented observations, unsupported guarantees, pending-as-acquired or budget bypass as critical; distinguish rejected proposals from actual spend.",
                    "ambiguous_reference": "Environment defects or missing traces are invalid/unscorable, not forced candidate failures.",
                },
                "reviewer_id": str(body.reviewer_id),
                "advisor_id": str(body.advisor_id),
                "origin": "original_synthetic_fixture",
            },
        ),
    )
    task = domain.create(
        c,
        project,
        user,
        "task",
        domain.validate_content(
            c,
            project,
            "task",
            {
                "title": manifest["title"],
                "external_case_id": "MKT-LH-001",
                "source_revision_id": str(source["current_revision_id"]),
                "rubric_revision_id": str(rubric["current_revision_id"]),
                "actor_artifact_ids": ids[:2],
                "reference_artifact_ids": ids[2:],
                "family_id": manifest["family_id"],
                "capabilities": manifest["capabilities"],
                "mode": "interactive",
                "environment_version": VERSION,
                "split": "development",
                "reviewer_id": str(body.reviewer_id),
                "advisor_id": str(body.advisor_id),
                "origin": "original_synthetic_fixture",
            },
        ),
    )
    for i, aid in enumerate(ids):
        c.execute(
            "INSERT INTO anvil.artifact_links VALUES(%s,%s,%s,%s)",
            (project, task["current_revision_id"], aid, "actor" if i < 2 else "reference"),
        )
    c.execute(
        "INSERT INTO anvil.import_receipts VALUES(%s,'MKT-LH-001','1.0',%s,%s)",
        (project, digest(HASHES), source["id"]),
    )
    audit(c, project, user, "marketing.drafts_imported", source["id"])
    return source
