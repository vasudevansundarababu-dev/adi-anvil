"""Private grader-owned custom overrides; no inputs in API/scheduler test jobs.

Intent commits before a separate secret-free coordinator executes Python. A
consumed attempt is never replayed. The original rubric, vetoes and review gates
remain authoritative; an evaluator error is unscored, not an actor failure.
"""

import hashlib
import os
import re
import time
from pathlib import Path
from uuid import UUID

from anvil.db import Jsonb, digest, one, uid
from anvil.golden_kyc_evaluators import CRITERIA, score
from anvil.golden_native_bridge import owned_json, private_root, publish
from anvil.native_image_profile import IMAGE_ID

SCHEMA = "anvil.private-python-grade.v1"
ANCHORS = {"pass": 5, "partial": 2, "fail": 0, "unscored": None, "error": None}


def source_hash():
    from anvil.custom_python_executor import source_hash as executor_hash

    return digest(
        {
            "grader": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "executor": executor_hash(),
            "schema": SCHEMA,
        }
    )


def qualification_gaps(snapshot, evidence):
    """Additional source/image/target controls within the privileged receipt."""
    controls = evidence.get("custom_python", [])
    if not isinstance(controls, list):
        controls = []
    return [
        {
            "section": section,
            "target": ref["target"],
            "code": "custom_python_qualification_required",
        }
        for section in ("rubric", "policy")
        for ref in snapshot.get(section, [])
        if ref["kind"] == "custom_python"
        if not any(
            isinstance(control, dict)
            and all(
                control.get(key) == value
                for key, value in {
                    "id": str(ref["id"]),
                    "sha256": ref["sha256"],
                    "target": ref["target"],
                    "source_sha256": source_hash(),
                    "image_id": IMAGE_ID,
                    "status": "passed",
                    "private_input_isolation_passed": True,
                    "error_unscored_and_veto_controls_passed": True,
                }.items()
            )
            and isinstance(control.get("evidence_sha256"), str)
            and len(control["evidence_sha256"]) == 64
            and all(c in "0123456789abcdef" for c in control["evidence_sha256"])
            for control in controls
        )
    ]


def programs(c, project, paid):
    """Read the frozen execution selection, not a mutable UI recommendation."""
    execution = one(
        c,
        "SELECT snapshot FROM anvil.workspace_execution_groups WHERE project_id=%s AND id=%s",
        (project, paid["group_id"]),
    )
    frozen = (execution or {}).get("snapshot", {}).get("preparation", {}).get("project_binding")
    if not frozen:
        # Historical captures with no custom selection retain their original
        # builtin assessment. Current Run admission requires a frozen binding.
        return None, []
    binding = one(
        c,
        "SELECT * FROM anvil.project_binding_versions WHERE project_id=%s AND task_group_id=%s ORDER BY version DESC LIMIT 1",
        (project, frozen["task_group_id"]),
    )
    if (
        not binding
        or str(binding["id"]) != frozen["id"]
        or digest(binding["snapshot"]) != binding["snapshot_sha256"]
        or binding["snapshot_sha256"] != frozen["snapshot_sha256"]
    ):
        raise RuntimeError("custom_grading_frozen_binding_changed")
    snapshot = binding["snapshot"]
    refs = [
        r | {"section": section}
        for section in ("rubric", "policy")
        for r in snapshot.get(section, [])
        if r["kind"] == "custom_python"
    ]
    if not refs:
        return binding, []
    from anvil.project_bindings import evidence_gaps

    receipt = one(
        c,
        "SELECT q.* FROM anvil.project_binding_qualifications q WHERE q.project_id=%s AND q.binding_id=%s AND q.release_sha256=%s AND q.expires_at>clock_timestamp() AND NOT EXISTS(SELECT 1 FROM anvil.project_binding_qualification_revocations r WHERE r.qualification_id=q.id) ORDER BY q.created_at DESC,q.id DESC LIMIT 1",
        (project, binding["id"], os.environ.get("ANVIL_DEPLOYMENT_QUALIFICATION_SHA256", "")),
    )
    if (
        not receipt
        or digest(receipt["evidence"]) != receipt["evidence_sha256"]
        or evidence_gaps(snapshot, receipt["evidence"])
    ):
        raise RuntimeError("custom_grading_current_qualification_required")
    resolved = one(
        c,
        "SELECT task_key,revision,private_reference_sha256 FROM anvil.praxis_resolved_tasks WHERE project_id=%s AND id=%s",
        (project, paid["resolved_task_id"]),
    )
    if not resolved:
        raise RuntimeError("custom_grading_resolved_task_missing")
    identity = {
        "task_id": resolved["task_key"],
        "task_version": resolved["revision"],
        "payload_sha256": resolved["private_reference_sha256"],
    }
    targets = {
        "criterion:" + digest(identity | {"criterion_id": criterion}): criterion
        for criterion in CRITERIA
    }
    from anvil.project_bindings import group, requirement_descriptors

    descriptors = requirement_descriptors(c, group(c, project, frozen["task_group_id"]))
    policies = {
        p["target"]: p
        for p in descriptors["policy_rules"]
        if all(p.get(k) == v for k, v in identity.items())
    }
    selected = []
    for ref in refs:
        policy = policies.get(ref["target"]) if ref["section"] == "policy" else None
        criterion = ref["target"] if policy else targets.get(ref["target"])
        if criterion is None:
            continue  # A different state task's exact target, not this case.
        if any(p["criterion"] == criterion for p in selected):
            raise RuntimeError("custom_grading_duplicate_override")
        row = one(
            c,
            "SELECT e.* FROM anvil.custom_python_evaluators e WHERE e.project_id=%s AND e.id=%s AND NOT EXISTS(SELECT 1 FROM anvil.custom_python_revocations r WHERE r.evaluator_id=e.id)",
            (project, ref["id"]),
        )
        if (
            not row
            or row["code_sha256"] != ref["sha256"]
            or hashlib.sha256(row["code"].encode()).hexdigest() != ref["sha256"]
        ):
            raise RuntimeError("custom_grading_program_changed_or_revoked")
        selected.append(ref | {"code": row["code"], "criterion": criterion, "policy": policy})
    return binding, selected


def collect_or_queue(c, project, paid, trial, generation, sealed, expectation, checks):
    """Called inside the grader transaction; returns pending without a score."""
    binding, selected = programs(c, project, paid)
    if selected and os.environ.get("ANVIL_CUSTOM_PYTHON_SCORING_ENABLED") != "true":
        return {"pending": True, "receipts": [], "reason": "private_python_scoring_not_enabled"}
    receipts, pending = [], False
    for program in selected:
        criterion = program["criterion"]
        policy = program.get("policy")
        policy_reference = (
            expectation.get("policy_rule_references", {}).get(program["target"]) if policy else None
        )
        # Pending normative decisions never go to submitted code as a substitute
        # for review. Preserve the denominator without starting an executor job.
        if (
            expectation.get("independent_expectation_review") != "approved"
            or (
                criterion.startswith("state_")
                and expectation.get("legal_qualification") != "approved"
            )
            or (
                policy
                and (
                    not isinstance(policy_reference, dict)
                    or policy_reference.get("review_status") != "approved"
                    or policy_reference.get("target") != program["target"]
                    or policy_reference.get("source_sha256") != binding["snapshot"]["source_sha256"]
                )
            )
        ):
            receipts.append(
                {
                    "criterion": criterion,
                    "target": program["target"],
                    "status": "unscored",
                    "reason": "source_review_pending",
                    "target_kind": "policy" if policy else "criterion",
                }
            )
            continue
        request = {
            "schema_version": SCHEMA,
            "source_sha256": source_hash(),
            "image_id": IMAGE_ID,
            "binding_sha256": binding["snapshot_sha256"],
            "code_sha256": program["sha256"],
            "target": program["target"],
            "state_sha256": digest(sealed),
            "code": program["code"],
            "actual": {
                "criterion": criterion,
                "observed": checks.get(criterion),
                "citation_complete": checks.get("citation_complete", {}).get(criterion),
                "final": sealed.get("final"),
                "policy": policy,
            },
            # Only the criterion's explicit reference context, never future
            # customer documents, scenario labels or reference test verdicts.
            "expected": {
                "intended_decision": None if policy else expectation.get("intended_decision"),
                "criterion_reference": policy_reference
                if policy
                else expectation.get("criterion_references", {}).get(criterion),
            },
        }
        identifier = uid()
        c.execute(
            "INSERT INTO banking_private.python_grading_jobs(id,project_id,trial_id,generation,criterion,binding_id,evaluator_id,request,request_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(trial_id,generation,criterion) DO NOTHING",
            (
                identifier,
                project,
                trial,
                generation,
                criterion,
                binding["id"],
                program["id"],
                Jsonb(request),
                digest(request),
            ),
        )
        job = one(
            c,
            "SELECT * FROM banking_private.python_grading_jobs WHERE project_id=%s AND trial_id=%s AND generation=%s AND criterion=%s",
            (project, trial, generation, criterion),
        )
        if job["request_sha256"] != digest(request) or str(job["binding_id"]) != str(binding["id"]):
            raise RuntimeError("custom_grading_input_changed_no_replay")
        if job["state"] in ("queued", "claimed"):
            pending = True
            continue
        # Hold the authority fence through the final award INSERT, not just
        # while the isolated worker was running. Historical awards above remain
        # immutable, but this first award must consume current authority.
        receipts.append(consume_result(c, job, program))
    return {"pending": pending, "receipts": receipts}


def consume_result(c, job, program):
    """Keep authority locks until the caller commits its first final award."""
    receipt = {
        "criterion": job["criterion"],
        "target": program["target"],
        "job_id": str(job["id"]),
        "target_kind": "policy" if program.get("policy") else "criterion",
    }
    locked = one(
        c,
        "SELECT anvil.lock_private_python_award(%s,%s) AS allowed",
        (job["binding_id"], job["evaluator_id"]),
    )
    if not locked or not locked["allowed"] or not job_eligible(c, job):
        return receipt | {"status": "error", "reason": "final_award_authority_unavailable"}
    result = job["result"]
    if (
        not isinstance(result, dict)
        or digest(result) != job["result_sha256"]
        or result.get("request_sha256") != job["request_sha256"]
        or result.get("source_sha256") != source_hash()
        or result.get("image_id") != IMAGE_ID
    ):
        raise RuntimeError("custom_grading_result_custody_changed")
    return receipt | {
        "evaluator_id": str(program["id"]),
        "code_sha256": program["sha256"],
        "result_sha256": job["result_sha256"],
        "status": result.get("status", "error"),
    }


def apply_overrides(baseline, expectation, receipts):
    """KYC's original 5/2/0 rubric and all mandatory/critical vetoes survive."""
    checks, issues = dict(baseline["checks"]), list(baseline.get("issues", []))
    policy_receipts = []
    seen = set()
    for receipt in receipts:
        criterion, status = receipt["criterion"], receipt["status"]
        if receipt.get("target_kind") == "policy":
            if (
                not criterion.startswith("policy-rule:")
                or criterion != receipt["target"]
                or criterion in seen
                or status not in ANCHORS
            ):
                raise ValueError("Exact distinct policy target and supported status required")
            seen.add(criterion)
            policy_receipts.append(receipt)
            if status == "error":
                issues.append("custom_policy_evaluator_error:" + criterion)
            continue  # Policy findings never add rubric points or clear guard vetoes.
        if criterion not in CRITERIA or criterion in seen or status not in ANCHORS:
            raise ValueError("Exact distinct KYC criterion and supported Python status required")
        seen.add(criterion)
        reviewed = expectation.get("independent_expectation_review") == "approved" and (
            not criterion.startswith("state_")
            or expectation.get("legal_qualification") == "approved"
        )
        checks[criterion] = ANCHORS[status] if reviewed else None
        if status == "error":
            issues.append("custom_evaluator_error:" + criterion)
    return (
        baseline
        | score(
            checks,
            correct_decision=baseline["decision_correctness"],
            mandatory=baseline["mandatory_conditions"],
            critical_failures=baseline["critical_failures"],
        )
        | {
            "issues": issues,
            "builtin_checks": baseline["checks"],
            "custom_evaluators": receipts,
            "custom_policy_evaluators": policy_receipts,
        }
    )


def grading_root(root):
    root = private_root(Path(root))
    for variable in (
        "ANVIL_CUSTOM_PYTHON_BRIDGE_ROOT",
        "ANVIL_NATIVE_BRIDGE_ROOT",
        "ANVIL_GOLDEN_NATIVE_WORK_ROOT",
    ):
        if os.environ.get(variable):
            other = Path(os.environ[variable]).resolve()
            if root.is_relative_to(other) or other.is_relative_to(root):
                raise RuntimeError("Private grading and ordinary actor/test roots must be disjoint")
    return root


def job_eligible(c, job):
    """Fresh qualification/revocation/current-source check before publication."""
    binding = one(
        c,
        "SELECT * FROM anvil.project_binding_versions WHERE project_id=%s AND task_group_id=(SELECT task_group_id FROM anvil.project_binding_versions WHERE id=%s) ORDER BY version DESC LIMIT 1",
        (job["project_id"], job["binding_id"]),
    )
    request = job["request"]
    if (
        not binding
        or binding["id"] != job["binding_id"]
        or digest(binding["snapshot"]) != binding["snapshot_sha256"]
        or request.get("binding_sha256") != binding["snapshot_sha256"]
        or request.get("source_sha256") != source_hash()
        or request.get("image_id") != IMAGE_ID
        or not any(
            ref["kind"] == "custom_python"
            and str(ref["id"]) == str(job["evaluator_id"])
            and ref["sha256"] == request.get("code_sha256")
            and ref["target"] == request.get("target")
            for section in ("rubric", "policy")
            for ref in binding["snapshot"].get(section, [])
        )
    ):
        return False
    active = one(
        c,
        "SELECT anvil.private_python_authors_active(%s,%s) AS allowed",
        (job["binding_id"], job["evaluator_id"]),
    )
    program = one(
        c,
        "SELECT code_sha256 FROM anvil.custom_python_evaluators e WHERE e.project_id=%s AND e.id=%s AND NOT EXISTS(SELECT 1 FROM anvil.custom_python_revocations r WHERE r.evaluator_id=e.id)",
        (job["project_id"], job["evaluator_id"]),
    )
    receipt = one(
        c,
        "SELECT q.* FROM anvil.project_binding_qualifications q WHERE q.project_id=%s AND q.binding_id=%s AND q.release_sha256=%s AND q.expires_at>clock_timestamp() AND NOT EXISTS(SELECT 1 FROM anvil.project_binding_qualification_revocations r WHERE r.qualification_id=q.id) ORDER BY q.created_at DESC,q.id DESC LIMIT 1",
        (
            job["project_id"],
            job["binding_id"],
            os.environ.get("ANVIL_DEPLOYMENT_QUALIFICATION_SHA256", ""),
        ),
    )
    from anvil.project_bindings import evidence_gaps

    return bool(
        active
        and active["allowed"]
        and program
        and program["code_sha256"] == request.get("code_sha256")
        and receipt
        and digest(receipt["evidence"]) == receipt["evidence_sha256"]
        and not evidence_gaps(binding["snapshot"], receipt["evidence"])
    )


def grader_once(connections, root, *, seconds=60):
    """Grader identity only; intent commits BEFORE private publication/effect."""
    if not 1 <= seconds <= 120:
        raise ValueError("Bounded private grading wait required")
    root = grading_root(root)
    with connections() as c:
        job = one(
            c,
            "SELECT * FROM banking_private.python_grading_jobs WHERE state='queued' ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1",
        )
        if not job:
            return None
        token = uid()
        c.execute(
            "UPDATE banking_private.python_grading_jobs SET state='claimed',claim_token=%s,claimed_at=clock_timestamp() WHERE id=%s",
            (token, job["id"]),
        )
        if not job_eligible(c, job):
            result = {
                "schema_version": SCHEMA,
                "request_sha256": job["request_sha256"],
                "source_sha256": source_hash(),
                "image_id": IMAGE_ID,
                "status": "error",
                "reason": "current_scoring_authority_unavailable",
                "model_calls": 0,
            }
            c.execute(
                "UPDATE banking_private.python_grading_jobs SET state='error',result=%s,result_sha256=%s,finished_at=now() WHERE id=%s AND claim_token=%s",
                (Jsonb(result), digest(result), job["id"], token),
            )
            return {"id": str(job["id"]), "blocked_before_execution": True, "model_calls": 0}
    if digest(job["request"]) != job["request_sha256"]:
        raise RuntimeError("private_grading_input_integrity_no_replay")
    attempt = root / UUID(str(job["id"])).hex
    attempt.mkdir(mode=0o700)
    publish(
        attempt / "request.json",
        {
            "id": str(job["id"]),
            "project_id": str(job["project_id"]),
            "request": job["request"],
            "request_sha256": job["request_sha256"],
        },
    )
    deadline = time.monotonic() + seconds
    while not (attempt / "result.json").exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("private_grading_completion_unconfirmed_no_replay")
        time.sleep(0.05)
    record = owned_json(attempt, "result.json")
    if record.get("request_sha256") != job["request_sha256"] or digest(
        record.get("result")
    ) != record.get("result_sha256"):
        raise RuntimeError("private_grading_result_integrity")
    with connections() as c:
        if not job_eligible(c, job):
            result = {
                "schema_version": SCHEMA,
                "request_sha256": job["request_sha256"],
                "source_sha256": source_hash(),
                "image_id": IMAGE_ID,
                "status": "error",
                "reason": "authority_changed_during_execution",
                "model_calls": 0,
            }
            record = {"result": result, "result_sha256": digest(result)}
        changed = c.execute(
            "UPDATE banking_private.python_grading_jobs SET state=%s,result=%s,result_sha256=%s,finished_at=now() WHERE id=%s AND state='claimed' AND claim_token=%s RETURNING id",
            (
                "error" if record["result"].get("status") == "error" else "completed",
                Jsonb(record["result"]),
                record["result_sha256"],
                job["id"],
                token,
            ),
        ).fetchone()
        if not changed:
            raise RuntimeError("private_grading_finish_denied_no_replay")
    return {"id": str(job["id"]), "result_sha256": record["result_sha256"]}


def coordinator_once(root, *, host):
    """Separate grader-only bridge; never reuse the ordinary test volume."""
    from anvil.custom_python_executor import execute

    if any(
        v and ("DATABASE" in k or k.endswith("API_KEY") or k.endswith("PRIVATE_KEY"))
        for k, v in os.environ.items()
    ):
        raise RuntimeError("Private coordinator must not receive SQL/provider secrets")
    root = grading_root(root)
    for path in sorted(root.iterdir()):
        if not re.fullmatch(r"[a-f0-9]{32}", path.name):
            continue
        attempt = private_root(path)
        if (
            not (attempt / "request.json").exists()
            or (attempt / "claimed.json").exists()
            or (attempt / "cancelled.json").exists()
        ):
            continue
        try:
            os.link(attempt / "request.json", attempt / "claimed.json")
        except FileExistsError:
            continue
        if (attempt / "cancelled.json").exists():
            continue
        envelope = owned_json(attempt, "request.json")
        request = envelope["request"]
        if (
            set(envelope) != {"id", "project_id", "request", "request_sha256"}
            or UUID(envelope["id"]).hex != path.name
            or digest(request) != envelope["request_sha256"]
            or request.get("schema_version") != SCHEMA
            or request.get("source_sha256") != source_hash()
            or request.get("image_id") != IMAGE_ID
            or hashlib.sha256(request["code"].encode()).hexdigest() != request.get("code_sha256")
        ):
            raise RuntimeError("private_grading_claimed_request_invalid_no_replay")
        home = attempt / "executor"
        home.mkdir(mode=0o700)
        result = {
            "schema_version": SCHEMA,
            "request_sha256": envelope["request_sha256"],
            "source_sha256": source_hash(),
            "image_id": IMAGE_ID,
            "status": "error",
            "model_calls": 0,
        }
        try:
            execution = execute(
                home,
                {
                    "code": request["code"],
                    "cases": [
                        {
                            "actual": request["actual"],
                            "expected": request["expected"],
                            # Executor removes this host-only control field before container
                            # launch. Grading consumes actual_status, never test passed.
                            "expected_status": "unscored",
                        }
                    ],
                },
                host=host,
            )
            status = execution["cases"][0]["actual_status"]
            if status in ANCHORS:
                result["status"] = status
            result["execution_sha256"] = digest(execution)
        except Exception as exc:
            result["execution_error"] = type(exc).__name__
        publish(
            attempt / "result.json",
            {
                "request_sha256": envelope["request_sha256"],
                "result": result,
                "result_sha256": digest(result),
            },
        )
        return {"id": envelope["id"], "result_sha256": digest(result)}
    return None


def reconcile(
    connections,
    root,
    identifier,
    *,
    abandon=False,
    rationale="Inspect and consume the retained private coordinator result",
):
    """Status/result reconciliation only. Never publishes an execution request.

    An explicit unconfirmed disposition is an operational unknown, not a claim
    that code did not execute or that physical cleanup was observed.
    """
    if type(rationale) is not str or not 10 <= len(rationale) <= 1000:
        raise ValueError("Explicit bounded reconciliation rationale required")
    root = grading_root(root)
    with connections() as c:
        job = one(
            c,
            "SELECT * FROM banking_private.python_grading_jobs WHERE id=%s FOR UPDATE",
            (str(UUID(identifier)),),
        )
        if not job:
            raise ValueError("Private grading job not found in project scope")
        if job["state"] in ("completed", "error"):
            return {
                "id": str(job["id"]),
                "state": job["state"],
                "already_terminal": True,
                "physical_execution_replayed": False,
            }
        if job["state"] != "claimed":
            raise ValueError("Only a previously claimed execution can be reconciled")
        attempt = root / UUID(str(job["id"])).hex
        if attempt.exists():
            private_root(attempt)
        if (attempt / "result.json").exists():
            envelope = owned_json(attempt, "request.json")
            if (
                owned_json(attempt, "claimed.json") != envelope
                or envelope.get("id") != str(job["id"])
                or envelope.get("project_id") != str(job["project_id"])
                or envelope.get("request_sha256") != job["request_sha256"]
                or digest(envelope.get("request")) != job["request_sha256"]
            ):
                raise RuntimeError("private_grading_late_claim_custody_changed")
            record = owned_json(attempt, "result.json")
            result = record.get("result")
            if (
                record.get("request_sha256") != job["request_sha256"]
                or not isinstance(result, dict)
                or digest(result) != record.get("result_sha256")
                or result.get("request_sha256") != job["request_sha256"]
                or result.get("source_sha256") != source_hash()
                or result.get("image_id") != IMAGE_ID
                or result.get("status") not in ANCHORS
            ):
                raise RuntimeError("private_grading_late_result_custody_changed")
            action = "late_result_consumed"
            if not job_eligible(c, job):
                result = {
                    "schema_version": SCHEMA,
                    "source_sha256": source_hash(),
                    "image_id": IMAGE_ID,
                    "request_sha256": job["request_sha256"],
                    "status": "error",
                    "reason": "authority_changed_before_reconciliation",
                    "model_calls": 0,
                }
        elif not abandon:
            return {
                "id": str(job["id"]),
                "state": "claimed",
                "result_available": False,
                "physical_execution_replayed": False,
                "next_step": "Inspect coordinator custody or explicitly dispose as unconfirmed/unscored",
            }
        else:
            attempt.mkdir(mode=0o700, exist_ok=True)
            cancellation = {
                "id": str(job["id"]),
                "request_sha256": job["request_sha256"],
                "reason": "explicit_unconfirmed_disposition",
            }
            if not (attempt / "cancelled.json").exists():
                publish(attempt / "cancelled.json", cancellation)
            elif owned_json(attempt, "cancelled.json") != cancellation:
                raise RuntimeError("private_grading_cancellation_custody_changed")
            result = {
                "schema_version": SCHEMA,
                "source_sha256": source_hash(),
                "image_id": IMAGE_ID,
                "request_sha256": job["request_sha256"],
                "status": "error",
                "reason": "operator_reconciled_execution_unknown",
                "execution_may_have_occurred": True,
                "cleanup_status": "not_verified",
                "model_calls": 0,
            }
            action = "unconfirmed_disposed"
        fingerprint = digest(result)
        c.execute(
            "UPDATE banking_private.python_grading_jobs SET state=%s,result=%s,result_sha256=%s,finished_at=clock_timestamp() WHERE id=%s AND state='claimed' AND claim_token=%s",
            (
                "error" if result["status"] == "error" else "completed",
                Jsonb(result),
                fingerprint,
                job["id"],
                job["claim_token"],
            ),
        )
        c.execute(
            "INSERT INTO banking_private.python_grading_reconciliations(id,project_id,job_id,action,rationale,request_sha256,result_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s)",
            (
                uid(),
                job["project_id"],
                job["id"],
                action,
                rationale,
                job["request_sha256"],
                fingerprint,
            ),
        )
        return {
            "id": str(job["id"]),
            "state": "error" if result["status"] == "error" else "completed",
            "result_sha256": fingerprint,
            "action": action,
            "physical_execution_replayed": False,
        }
