"""Synthetic test admission; never a project qualification or production award.

The installed private control driver is the only caller. No HTTP route, flag,
uploaded receipt or fabricated paid capture can supply this authority. SQL also
restricts it to a fresh disposable component database and a dedicated grader.
"""

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from anvil.db import Jsonb, digest, one
from anvil.native_image_profile import IMAGE_ID

SCHEMA = "anvil.private-python-control-grade.v1"
PURPOSE = "synthetic_private_scoring_control"
CONTEXT_SCHEMA = "anvil.private-python-control-admission.v1"
REVIEW_RECEIPT_SHA256 = "186be4ec9729428b91ad95fb7c85562167643bd09822db9845d46b07d3333c20"
REVIEW_CODE_SHA256 = "7e0785d67fab37b8e1c7d339000cd3190b667961cbd2af2a79712fdb02780dc7"
KEYS = {"schema_version", "purpose", "database", "fixture_nonce", "project_id", "job_id",
        "trial_id", "generation", "binding_id", "binding_sha256", "evaluator_id", "code_sha256",
        "criterion", "target", "group_id", "resolved_task_id", "task_key", "task_revision",
        "private_reference_sha256", "grader_source_sha256", "golden_source_sha256",
        "runtime_image_sha256", "executor_image_id", "review_receipt_sha256",
        "expectation_sha256", "state_sha256", "checks_sha256", "private_input"}


@dataclass(frozen=True, slots=True)
class ControlReference:
    id: UUID
    sha256: str

    def wire(self):
        if type(self.id) is not UUID or not valid_sha(self.sha256):
            raise ValueError("Exact control reference required")
        return {"id": str(self.id), "sha256": self.sha256, "purpose": PURPOSE}


def valid_sha(value):
    return type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def from_request(request):
    if request.get("schema_version") != SCHEMA:
        if "technical_control" in request:
            raise RuntimeError("Production request contains technical authority")
        return None
    value = request.get("technical_control")
    if not isinstance(value, dict) or set(value) != {"id", "sha256", "purpose"} or value["purpose"] != PURPOSE:
        raise RuntimeError("Exact technical grading purpose required")
    ref = ControlReference(UUID(value["id"]), value["sha256"])
    if ref.wire() != value:
        raise RuntimeError("Noncanonical technical authority")
    return ref


def load(c, project, ref):
    """Always reread current DB/row/expiry/revocation/source; no cache."""
    if type(ref) is not ControlReference:
        raise RuntimeError("Typed technical admission required")
    ref.wire()
    identity = one(c, "SELECT current_database() AS database,session_user AS login,"
                   "r.rolsuper OR r.rolbypassrls OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication AS privileged,"
                   "r.rolcanlogin AS login_allowed,(SELECT count(*) FROM pg_auth_members m WHERE m.member=r.oid) AS parents,"
                   "pg_has_role(session_user,'anvil_golden_grader','MEMBER') AS grader "
                   "FROM pg_roles r WHERE r.rolname=session_user")
    if (not identity or not identity["database"].startswith("anvil_golden_kyc_component_")
            or identity["privileged"] or not identity["login_allowed"] or identity["parents"] != 1 or not identity["grader"]):
        raise RuntimeError("Dedicated isolated technical grader required")
    row = one(c, "SELECT a.* FROM banking_private.python_control_admissions a WHERE a.project_id=%s AND a.id=%s "
                 "AND a.expires_at>clock_timestamp() AND NOT EXISTS(SELECT 1 FROM banking_private.python_control_revocations r WHERE r.admission_id=a.id)",
              (project, ref.id))
    if not row or digest(row["context"]) != ref.sha256 or row["context_sha256"] != ref.sha256:
        raise RuntimeError("Current exact technical admission required")
    context = row["context"]
    from anvil.custom_python_grading import source_hash
    from anvil.golden_kyc_source import source_hash as golden_source

    if (set(context) != KEYS or context["schema_version"] != CONTEXT_SCHEMA or context["purpose"] != PURPOSE
            or context["database"] != identity["database"] or context["project_id"] != str(project)
            or context["fixture_nonce"] != row["fixture_nonce"]
            or context["grader_source_sha256"] != source_hash() or context["golden_source_sha256"] != golden_source()
            or context["runtime_image_sha256"] != os.environ.get("ANVIL_RUNTIME_IMAGE_DIGEST")
            or context["executor_image_id"] != IMAGE_ID
            or context["review_receipt_sha256"] != REVIEW_RECEIPT_SHA256 or context["code_sha256"] != REVIEW_CODE_SHA256
            or type(context["generation"]) is not int
            or row["created_at"] > datetime.now(timezone.utc) or row["expires_at"] <= row["created_at"]
            or (row["expires_at"] - row["created_at"]).total_seconds() > 1800
            or any(not valid_sha(value) for key, value in context.items() if key.endswith("sha256"))
            or any(str(row[key]) != str(context[key]) for key in ("job_id", "trial_id", "generation", "binding_id", "evaluator_id", "criterion"))):
        raise RuntimeError("Technical admission source or exact subject changed")
    return context


def selection(c, project, ref, execution, binding, resolved, selected):
    context = load(c, project, ref)
    if (str(execution["group_id"]) != context["group_id"] or str(execution["resolved_task_id"]) != context["resolved_task_id"]
            or str(binding["id"]) != context["binding_id"] or binding["snapshot_sha256"] != context["binding_sha256"]
            or resolved["task_key"] != context["task_key"] or resolved["revision"] != context["task_revision"]
            or resolved["private_reference_sha256"] != context["private_reference_sha256"] or len(selected) != 1
            or any(str(selected[0][key]) != context[field] for key, field in
                   (("id", "evaluator_id"), ("sha256", "code_sha256"), ("target", "target"), ("criterion", "criterion")))
            or selected[0].get("policy") is not None):
        raise RuntimeError("Technical admission does not match frozen stored selection")
    active = one(c, "SELECT anvil.private_python_authors_active(%s,%s) AS allowed", (binding["id"], selected[0]["id"]))
    if not active or not active["allowed"]:
        raise RuntimeError("Current technical authors required")
    return context


def eligible(c, job):
    ref = from_request(job["request"])
    if ref is None:
        return False
    try:
        context = load(c, job["project_id"], ref)
        allowed = one(c, "SELECT banking_private.python_control_allowed(%s,%s,%s,%s,%s,%s,%s,%s,%s) AS allowed",
                      (ref.id, job["id"], job["project_id"], job["trial_id"], job["generation"], job["binding_id"],
                       job["evaluator_id"], job["criterion"], Jsonb(job["request"])))
        return bool(allowed and allowed["allowed"] and job["request"].get("state_sha256") == context["state_sha256"])
    except (ValueError, RuntimeError):
        return False
