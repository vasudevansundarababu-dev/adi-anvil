"""Dedicated qualifier producer. Never an API upload, approval or model dispatch."""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from anvil.db import one
from anvil.golden_kyc_policy_delivery import Materialization, validate_materialization
from anvil.golden_kyc_policy_registry import ProductRegistryScope, RegistryRecord
from anvil.kyc_policy_reviews import domain_subject, fence, resolve, runtime_subject
from anvil.praxis_generic_contract import canonical, digest, load


def enter(c, project):
    """Map a dedicated database login to its enrolled actual project identity."""
    login = one(c, "SELECT session_user AS login,rolcanlogin,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,"
                "rolreplication FROM pg_roles WHERE rolname=session_user")
    if (not login or not login["rolcanlogin"] or any(login[key] for key in
            ("rolsuper", "rolbypassrls", "rolcreatedb", "rolcreaterole", "rolreplication"))
            or login["login"] in {"anvil_app", "anvil_worker", "anvil_golden_scheduler", "anvil_golden_grader"}):
        raise ValueError("Dedicated restricted qualifier login required")
    roles = c.execute("SELECT rolname FROM pg_roles WHERE pg_has_role(session_user,oid,'MEMBER') "
                      "AND rolname<>session_user").fetchall()
    if {row["rolname"] for row in roles} != {"anvil_kyc_qualifier"}:
        raise ValueError("Disjoint qualifier membership required")
    c.execute("SET LOCAL ROLE anvil_kyc_qualifier")
    principal = one(c, "SELECT user_id FROM anvil.kyc_policy_operator_principals "
                    "WHERE login_role=session_user AND project_id=%s", (project,))
    if not principal:
        raise ValueError("Enrolled actual operator identity required")
    user = principal["user_id"]
    c.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",
              (str(project), str(user)))
    if not one(c, "SELECT anvil.benchmark_is_admin(%s,%s) AS allowed", (project, user))["allowed"]:
        raise ValueError("Current project operator authority required")
    return user


def provision(c, project, user, record, materialization):
    """Validate and append both records atomically in the caller transaction.

    The API has no qualifier membership. This producer never creates a domain
    decision or changes source/template/data bindings to fit submitted artifacts.
    """
    if (type(record) is not RegistryRecord or type(record.scope) is not ProductRegistryScope
            or type(materialization) is not Materialization or record.scope.project_id != project):
        raise ValueError("Exact product scope and policy materialization required")
    from anvil.golden_component_qualification import installed
    from anvil.golden_kyc_anvil import source_hash
    from anvil.golden_kyc_resolved_store import policy_scope

    fence(c, project)
    actual = policy_scope(c, project, record.scope.resolved_input_id, record.scope.task_id, record.scope.revision_id)
    if actual != record.scope:
        raise ValueError("Original stored task/input scope changed")
    template = one(c, "SELECT spec FROM anvil.praxis_template_versions WHERE project_id=%s AND template_key=%s "
                   "AND version=%s AND spec_sha256=%s", (project, record.scope.template.id,
                   record.scope.template.version, record.scope.template.sha256))
    declared = template["spec"]["execution"].get("federalPolicies", []) if template else []
    supplied = [ref.model_dump(mode="json") for ref in record.policy_set.federal_refs]
    if sorted(declared, key=lambda ref: ref["id"]) != sorted(supplied, key=lambda ref: ref["id"]):
        raise ValueError("Policy sources must match the immutable template, not a substituted artifact")
    qualification = installed()
    if (not qualification["ready"] or record.scope.runtime_source_sha256 != source_hash()
            or qualification["evidence"]["runtime_image_sha256"] != record.scope.runtime_image_sha256):
        raise ValueError("Actual current installed component qualification required")
    now = one(c, "SELECT statement_timestamp() AS now")["now"]
    if one(c, "SELECT 1 FROM anvil.kyc_application_policy_revocations WHERE project_id=%s AND qualification_id=%s",
           (project, record.id)) or one(c, "SELECT 1 FROM anvil.kyc_application_policy_materialization_revocations "
                                     "WHERE project_id=%s AND materialization_id=%s", (project, materialization.id)):
        raise ValueError("Revoked provisioning identity cannot be replayed")
    resolve(c, project, record.domain_review_receipt, domain_subject(record.scope, record.policy_set),
            expires_at=record.expires_at)
    resolve(c, project, record.runtime_control_receipt, runtime_subject(record.scope),
            expires_at=record.expires_at)
    raw = canonical(materialization.model_dump(mode="json"))
    validate_materialization(raw, record, application_id=materialization.application_id, checked_at=now)
    parent = record.model_dump(mode="json")
    scope = record.scope.model_dump(mode="json")
    old = one(c, "SELECT content_sha256 FROM anvil.kyc_application_policy_qualifications WHERE project_id=%s AND id=%s",
              (project, record.id))
    if old and old["content_sha256"] != digest(parent):
        raise ValueError("Qualification identity already has different immutable content")
    if not old:
        c.execute("INSERT INTO anvil.kyc_application_policy_qualifications(id,project_id,binding_id,created_by,"
                  "body_canonical,scope_canonical,scope_sha256,content_sha256,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                  (record.id, project, record.scope.project_binding_id, user, canonical(parent).decode(),
                   canonical(scope).decode(), digest(scope), digest(parent), record.expires_at))
    previous = one(c, "SELECT content_sha256 FROM anvil.kyc_application_policy_materializations WHERE project_id=%s AND id=%s",
                   (project, materialization.id))
    if previous and previous["content_sha256"] != digest(materialization.model_dump(mode="json")):
        raise ValueError("Materialization identity already has different immutable content")
    if not previous:
        c.execute("INSERT INTO anvil.kyc_application_policy_materializations(id,project_id,qualification_id,application_id,"
                  "created_by,body_canonical,content_sha256,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                  (materialization.id, project, record.id, materialization.application_id, user, raw.decode(),
                   digest(materialization.model_dump(mode="json")), materialization.expires_at))
    return {"qualification_id": str(record.id), "materialization_id": str(materialization.id),
            "commit_observed": False, "run_authority": "not_granted", "paid_calls": False}


def retain_runtime_review(c, project, user, scope):
    """Only dedicated operator may retain real installed technical evidence."""
    from anvil.golden_component_qualification import installed

    fence(c, project)
    from anvil.golden_kyc_resolved_store import policy_scope

    if policy_scope(c, project, scope.resolved_input_id, scope.task_id, scope.revision_id) != scope:
        raise ValueError("Actual stored runtime scope required")
    result = installed()
    if not result["ready"]:
        raise ValueError("Installed technical evidence is not qualified")
    evidence = result["evidence"]
    if (evidence["golden_source_sha256"] != scope.runtime_source_sha256
            or evidence["runtime_image_sha256"] != scope.runtime_image_sha256):
        raise ValueError("Installed evidence differs from original runtime scope")
    subject = runtime_subject(scope).model_dump(mode="json")
    controls = evidence.get("binding_controls")
    if (type(controls) is not list or not 1 <= len(controls) <= 100
            or not any(type(control) is dict and control.get("subject") == subject
                       and control.get("status") == "passed"
                       and type(control.get("evidence_sha256")) is str
                       and len(control["evidence_sha256"]) == 64
                       and all(ch in "0123456789abcdef" for ch in control["evidence_sha256"])
                       for control in controls)):
        raise ValueError("Exact environment/evaluator binding control evidence required")
    identifier = uuid5(NAMESPACE_URL, str(project) + digest(subject) + digest(evidence))
    old = one(c, "SELECT id,content_sha256 FROM anvil.kyc_policy_review_receipts WHERE project_id=%s AND id=%s",
              (project, identifier))
    if old:
        from anvil.golden_kyc_policy_registry import ReceiptReference

        resolve(c, project, ReceiptReference(id=old["id"], sha256=old["content_sha256"]),
                runtime_subject(scope), expires_at=datetime.fromisoformat(evidence["expires_at"].replace("Z", "+00:00")))
        return {"id": str(old["id"]), "sha256": old["content_sha256"]}
    now = one(c, "SELECT statement_timestamp() AS now")["now"]
    body = {"schema_version": "anvil.kyc-policy-review-receipt.v1", "id": str(identifier),
            "project_id": str(project), "kind": "runtime", "subject_id": None,
            "subject": subject, "subject_sha256": digest(subject), "reviewer_id": str(user),
            "reviewed_at": now.isoformat(), "self_approved": False, "decision": "approved",
            "rationale": "Retained independent installed technical control evidence; no policy or spending approval.",
            "evidence_reference": "installed_component_qualification", "evidence_sha256": digest(evidence),
            "expires_at": evidence["expires_at"]}
    c.execute("INSERT INTO anvil.kyc_policy_review_receipts(id,project_id,subject_id,kind,created_by,body_canonical,"
              "content_sha256,expires_at) VALUES(%s,%s,NULL,'runtime',%s,%s,%s,%s)",
              (identifier, project, user, canonical(body).decode(), digest(body),
               datetime.fromisoformat(evidence["expires_at"].replace("Z", "+00:00"))))
    return {"id": str(identifier), "sha256": digest(body)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=UUID, required=True)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--request", type=Path)
    operation.add_argument("--retain-runtime-review", type=UUID, metavar="RESOLVED_INPUT_ID")
    parser.add_argument("--task")
    parser.add_argument("--revision")
    args = parser.parse_args()
    request = None
    if args.request:
        with args.request.open("rb") as stream:
            raw = stream.read(1179649)
        if not 0 < len(raw) <= 1179648:
            raise ValueError("Bounded provisioning request required")
        request = load(raw)
        if set(request) != {"qualification", "materialization"}:
            raise ValueError("Exact qualification and materialization request required")
    elif not args.task or not args.revision:
        parser.error("Runtime review requires --task and --revision")
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(os.environ["ANVIL_KYC_QUALIFIER_DATABASE_URL"], row_factory=dict_row,
                          connect_timeout=2, options="-c statement_timeout=5000 -c lock_timeout=1000") as c:
        user = enter(c, args.project)
        if request:
            result = provision(c, args.project, user, RegistryRecord.model_validate_json(canonical(request["qualification"])),
                               Materialization.model_validate_json(canonical(request["materialization"])))
        else:
            from anvil.golden_kyc_resolved_store import policy_scope

            actual = policy_scope(c, args.project, args.retain_runtime_review, args.task, args.revision)
            result = retain_runtime_review(c, args.project, user, actual)
    result["commit_observed"] = True
    print(canonical(result).decode())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.stderr.write("policy_provision_blocked_no_authority_granted\n")
        raise SystemExit(1) from None
