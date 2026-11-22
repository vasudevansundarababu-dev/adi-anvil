"""Task-bound method observations and reviewed publication; never model dispatch.

Only an enrolled, disjoint qualifier connection is accepted. Original mechanics
remain synthetic and unqualified by themselves. Public task binding, actual SQL
isolation and an independent exact-observation review are separate requirements.
"""

import hashlib
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from anvil.db import digest, one
from anvil.praxis_generic_contract import canonical, load

MECHANICS_OPERATOR = "70638a34692035aba10e653e3cbdad720cd7cf605e800bfb815bac71dc9c186f"
ARTIFACT_ROOT = Path("/app/.data/task-method-controls")
CASES = {"supported_nonstate_legal_pending", "missing_citation_partial",
         "unsupported_clearance_critical_veto", "pending_expectation_review",
         "missing_intended_decision", "aggregate_critical_veto"}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(value):
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def timestamp(value):
    require(type(value) is str, "Explicit qualification timestamp required")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.tzinfo is not None, "Timezone-bound qualification required")
    return result


def original(path, expected):
    """Only exact root-owned files in the immutable operator control mount."""
    path = Path(path)
    require(sha(expected) and path.is_relative_to(ARTIFACT_ROOT)
            and path.resolve(strict=True) == path, "Fixed original control artifact required")
    require(not any(parent.is_symlink() for parent in (path, *path.parents)), "No symlink control artifacts")
    info = path.stat()
    require(path.is_file() and info.st_uid == 0 and not info.st_mode & 0o022
            and info.st_nlink == 1 and 0 < info.st_size <= 2097152
            and os.statvfs(path).f_flag & os.ST_RDONLY, "Immutable bounded operator artifact required")
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, "Original control bytes changed")
    return raw


def identity():
    from anvil.benchmark_runs import METHODS
    from anvil.golden_component_qualification import installed
    from anvil.golden_kyc_source import source_hash
    from anvil.harbor_agents import code_digest

    component = installed()
    image = os.environ.get("ANVIL_RUNTIME_IMAGE_DIGEST", "")
    release = os.environ.get("ANVIL_DEPLOYMENT_QUALIFICATION_SHA256", "")
    require(component["ready"] and sha(image) and sha(release)
            and component["evidence"]["runtime_image_sha256"] == image,
            "Exact currently qualified installed runtime required")
    method = next(item for item in METHODS if item["id"] == "task-rubric-v1")
    require(method["status"] == "ready" and method["kind"] == "deterministic",
            "Actual registered deterministic method required")
    return {"runtime_source_sha256": source_hash(), "runtime_image_sha256": image,
            "broker_source_sha256": code_digest(), "release_sha256": release,
            "candidate_sha256": digest(method), "method": method,
            "component_receipt_sha256": digest(component["evidence"]),
            "component_expires_at": component["evidence"]["expires_at"]}


def reviewed_mechanics(raw, review, current, *, now):
    """Recompute original arithmetic; do not promote old binding/isolation claims."""
    from anvil.golden_kyc_evaluators import score

    packet = load(raw)
    require(review.get("schema_version") == "anvil.independent-kyc-method-mechanics-review.v1"
            and review.get("origin") == "independent_agent_read_only_review"
            and review.get("status") == "passed_software_observations_only"
            and review.get("scope") == "manufactured_method_and_diagnostic_mechanics_only"
            and review.get("findings") == [] and review.get("qualification_granted") is False
            and review.get("spending_authority") is False
            and review.get("packet_files", {}).get("positive.stdout") == hashlib.sha256(raw).hexdigest(),
            "Independent original mechanics review required")
    require(timestamp(review["issued_at"]) <= now < timestamp(review["issued_at"]) + timedelta(hours=24),
            "Current bounded original mechanics review required")
    require(packet.get("schema_version") == "anvil.kyc-method-mechanics-observation.v1"
            and packet.get("origin") == "manufactured_no_model_software_controls"
            and packet.get("status") == "observed_not_qualified"
            and packet.get("provider_calls") == 0 and packet.get("private_expectations_read") is False
            and packet.get("method") == current["method"]
            and packet.get("method_sha256") == current["candidate_sha256"]
            and packet.get("runtime_source_sha256") == current["runtime_source_sha256"]
            and packet.get("operator_sha256") == MECHANICS_OPERATOR,
            "Exact current synthetic mechanics identity required")
    for case, exit_code in (("positive", 0), ("credential-negative", 1)):
        item = review["cases"][case]
        require(item["terminal"] is True and item["exit"] == exit_code
                and item["image"].endswith("@sha256:" + current["runtime_image_sha256"]),
                "Exact terminal original mechanics image required")
    rows = packet.get("observations")
    require(type(rows) is list and len(rows) == 6 and {row["case"] for row in rows} == CASES,
            "All original method cases required")
    results = {}
    for row in rows:
        result = row["result"]
        require(digest(result) == row["result_sha256"], "Original method result changed")
        calculated = score(result["checks"], correct_decision=result["decision_correctness"],
                           mandatory=result["mandatory_conditions"], critical_failures=result["critical_failures"])
        require(all(result.get(key) == value for key, value in calculated.items()),
                "Actual scoring arithmetic does not match retained evidence")
        results[row["case"]] = result
    require(results["supported_nonstate_legal_pending"]["rubric_score"] ==
            {"earned_points": 80, "maximum_points": 100, "unscored_points": 20}
            and results["missing_citation_partial"]["checks"]["profile"] == 2
            and results["unsupported_clearance_critical_veto"]["overall_result"] == "critical_fail"
            and results["pending_expectation_review"]["rubric_score"]["unscored_points"] == 100
            and results["missing_intended_decision"]["decision_correctness"] is None
            and results["aggregate_critical_veto"]["overall_result"] == "critical_fail",
            "Positive, negative, missing and critical method controls required")
    return {"packet_sha256": hashlib.sha256(raw).hexdigest(), "review_sha256": digest(review),
            "case_result_sha256s": {name: digest(value) for name, value in results.items()},
            "expires_at": (timestamp(review["issued_at"]) + timedelta(hours=24)).isoformat(),
            "scope": "synthetic_method_mechanics_not_human_expectation_review"}


def public_group(c, project, group):
    return one(c, "SELECT anvil.task_method_public_group(%s,%s) AS body", (project, group))["body"]


def checked_group(body, project, group, source=None):
    require(type(body) is dict and body.get("project_id") == str(project) and body.get("id") == str(group)
            and sha(body.get("source_sha256")) and (source is None or body["source_sha256"] == source),
            "Exact current task group source required")
    tasks = body.get("tasks")
    require(type(tasks) is list and 1 <= len(tasks) <= 100
            and len({item["task_id"] for item in tasks}) == len(tasks), "Unique actual captured tasks required")
    for item in tasks:
        require(type(item.get("task_id")) is str and item["task_id"]
                and type(item.get("task_version")) is str and item["task_version"]
                and sha(item.get("payload_sha256")), "Exact captured task identities required")
    require(type(body.get("database_identity")) is dict
            and set(body["database_identity"]) == {"database", "database_oid", "system_identifier"}
            and all(type(v) is str and v for v in body["database_identity"].values()),
            "Actual SQL database identity required")
    return body


def checked_witness(witness, body, project, group, owner_raw, *, now):
    """Apply the same exact witness checks at observation and publication."""
    require(witness.get("schema_version") == "anvil.task-method-foreign-witness.v1"
            and witness.get("origin") == "independent_qa"
            and witness.get("database_identity") == body["database_identity"]
            and witness.get("own_project_id") == str(project) and witness.get("own_group_id") == str(group)
            and witness.get("own_source_sha256") == body["source_sha256"]
            and witness.get("known_foreign_group_exists") is True
            and sha(witness.get("owner_observation_sha256"))
            and timestamp(witness["issued_at"]) <= now < timestamp(witness["expires_at"])
            <= timestamp(witness["issued_at"]) + timedelta(hours=24),
            "Current independent known-foreign SQL witness and bounded expiry required")
    foreign_project, foreign_group = UUID(witness["foreign_project_id"]), UUID(witness["foreign_group_id"])
    require(foreign_project != project and foreign_group != group, "Disjoint actual witness required")
    require(type(owner_raw) is bytes and hashlib.sha256(owner_raw).hexdigest()
            == witness["owner_observation_sha256"], "Original owner observation bytes required")
    owner = load(owner_raw)
    require(canonical(owner) == owner_raw
            and owner.get("schema_version") == "anvil.task-method-owner-observation.v1"
            and owner.get("origin") == "actual_read_only_database_metadata"
            and owner.get("database_identity") == body["database_identity"]
            and owner.get("own_project_id") == str(project) and owner.get("own_group_id") == str(group)
            and owner.get("own_source_sha256") == body["source_sha256"]
            and owner.get("foreign_project_id") == str(foreign_project)
            and owner.get("foreign_group_id") == str(foreign_group)
            and owner.get("known_foreign_group_exists") is True
            and type(owner.get("observer")) is dict
            and type(owner["observer"].get("login")) is str and owner["observer"]["login"]
            and (owner["observer"].get("database_owner") is True or owner["observer"].get("superuser") is True)
            and owner.get("private_content_read") is False and owner.get("qualification_granted") is False
            and type(owner.get("provider_calls")) is int and owner["provider_calls"] == 0
            and sha(owner.get("foreign_source_sha256"))
            and timestamp(owner["observed_at"]) <= timestamp(witness["issued_at"])
            and now < timestamp(owner["observed_at"]) + timedelta(hours=24),
            "Exact current original owner existence observation required")
    return foreign_project, foreign_group


def observe(c, project, group, resolved_input, mechanics_raw, mechanics_review, witness, owner_raw):
    from anvil.kyc_policy_provision import enter
    from anvil.task_method_compatibility import check
    from infra.gcp.kyc_binding_observation import observe as binding_observation

    require(one(c, "SHOW transaction_read_only")["transaction_read_only"] == "on",
            "Method observations require a read-only transaction")
    enter(c, project)
    login = one(c, "SELECT session_user AS login")["login"]
    current = identity()
    now = one(c, "SELECT statement_timestamp() AS now")["now"]
    mechanics = reviewed_mechanics(mechanics_raw, mechanics_review, current, now=now)
    body = checked_group(public_group(c, project, group), project, group)
    foreign_project, foreign_group = checked_witness(witness, body, project, group, owner_raw, now=now)
    bindings = []
    for task in body["tasks"]:
        require(check({"workflow": task.get("workflow_declared")}, current["method"])["compatible"],
                "Actual task/method compatibility required")
        result = binding_observation(c, project, resolved_input, task["task_id"], task["task_version"])
        require(result["scope"]["source_sha256"] == body["source_sha256"], "Task/input source changed")
        bindings.append(result)
    missing = uuid4()
    require(public_group(c, project, missing) is None, "Missing captured task guard failed")
    require(not check({}, current["method"] | {"id": "humaneval-plus"})["compatible"],
            "Original-suite incompatibility guard failed")
    try:
        checked_group(body | {"source_sha256": "0" * 64}, project, group, body["source_sha256"])
    except ValueError:
        pass
    else:
        raise ValueError("Changed task source guard failed")
    require(public_group(c, project, foreign_group) is None, "Known foreign group became visible")
    import psycopg

    try:
        with c.transaction():
            c.execute("SELECT set_config('anvil.project',%s,true)", (str(foreign_project),))
            public_group(c, foreign_project, foreign_group)
    except psycopg.errors.InsufficientPrivilege:
        pass
    else:
        raise ValueError("Forged project context bypassed enrollment")
    enter(c, project)
    require(identity() == current and public_group(c, project, group) == body,
            "Installed method or captured group changed during observation")
    return {"schema_version": "anvil.task-method-observation.v1", "status": "observed_not_qualified",
            "project_id": str(project), "task_group_id": str(group), "source_sha256": body["source_sha256"],
            "observed_at": now.isoformat(), "observer_login": login, "identity": current,
            "public_group_sha256": digest(body), "mechanics": mechanics, "bindings": bindings,
            "resolved_input_id": str(resolved_input),
            "operator_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "foreign_witness_sha256": digest(witness),
            "controls": {"positive": {"actual_tasks": len(bindings), "binding_observations_sha256": digest(bindings)},
                         "negative": {"original_suite_rejected": True, "changed_source_rejected": True,
                                      "origin": "actual_compatibility_and_copied_source_guard"},
                         "missing": {"missing_group_id": str(missing), "actual_query_returned_none": True},
                         "project_isolation": {"known_foreign_group_hidden": True, "forged_context_rejected": True,
                                               "database_identity": body["database_identity"]}},
            "provider_calls": 0, "private_expectations_read": False,
            "human_review_approval": False, "spending_authority": False, "model_performance": False}


def receipt(observation, review, review_sha256, current, group_body, mechanics, witness, owner_raw, *, now, login):
    """Verify original outcomes/review and current identities before SQL append."""
    project, group = UUID(observation["project_id"]), UUID(observation["task_group_id"])
    checked_group(group_body, project, group, observation["source_sha256"])
    checked_witness(witness, group_body, project, group, owner_raw, now=now)
    require(observation.get("schema_version") == "anvil.task-method-observation.v1"
            and observation.get("status") == "observed_not_qualified"
            and observation.get("identity") == current
            and observation.get("public_group_sha256") == digest(group_body)
            and observation.get("mechanics") == mechanics
            and observation.get("foreign_witness_sha256") == digest(witness)
            and observation.get("operator_source_sha256") == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            and type(observation.get("provider_calls")) is int and observation["provider_calls"] == 0
            and all(observation.get(key) is False for key in
                    ("private_expectations_read", "human_review_approval", "spending_authority", "model_performance")),
            "Original exact nonspending task method observation required")
    bindings, tasks = observation.get("bindings"), group_body["tasks"]
    require(type(bindings) is list and len(bindings) == len(tasks), "All actual task observations required")
    for task, binding in zip(tasks, bindings, strict=True):
        scope = binding["scope"]
        require(scope["project_id"] == str(project) and scope["task_id"] == task["task_id"]
                and scope["revision_id"] == task["task_version"]
                and scope["source_sha256"] == group_body["source_sha256"]
                and scope["resolved_input_id"] == observation["resolved_input_id"]
                and scope["runtime_source_sha256"] == current["runtime_source_sha256"]
                and scope["runtime_image_sha256"] == current["runtime_image_sha256"]
                and binding["component_evidence_sha256"] == current["component_receipt_sha256"]
                and binding["provider_calls"] == 0 and binding["private_expectations_read"] is False,
                "Actual input/task/runtime observations changed")
    controls = observation.get("controls")
    require(type(controls) is dict and set(controls) == {"positive", "negative", "missing", "project_isolation"},
            "Complete original method control set required")
    require(controls["positive"] == {"actual_tasks": len(tasks), "binding_observations_sha256": digest(bindings)}
            and controls["negative"] == {"original_suite_rejected": True, "changed_source_rejected": True,
                                         "origin": "actual_compatibility_and_copied_source_guard"}
            and controls["missing"].get("actual_query_returned_none") is True
            and UUID(controls["missing"]["missing_group_id"]) not in (group, UUID(witness["foreign_group_id"]))
            and controls["project_isolation"] == {"known_foreign_group_hidden": True, "forged_context_rejected": True,
                                                 "database_identity": group_body["database_identity"]},
            "Original method outcomes are incomplete or inconsistent")
    control_hashes = {name: digest(value) for name, value in controls.items()}
    require(sha(review_sha256) and review.get("schema_version") == "anvil.independent-task-method-review.v1"
            and review.get("origin") == "independent_agent_read_only_review"
            and review.get("scope") == "task_method_technical_only"
            and review.get("status") == "passed" and review.get("findings") == []
            and review.get("observation_sha256") == digest(observation)
            and review.get("identity_sha256") == digest(current)
            and review.get("control_sha256s") == control_hashes
            and review.get("foreign_witness_sha256") == digest(witness)
            and review.get("owner_observation_sha256") == witness["owner_observation_sha256"]
            and all(review.get(key) is False for key in
                    ("human_review_approval", "spending_authority", "model_performance")),
            "Independent exact task method evidence review required")
    issued, expires = timestamp(review["issued_at"]), timestamp(review["expires_at"])
    require(timestamp(observation["observed_at"]) <= issued <= now < expires
            and expires <= min(issued + timedelta(hours=24), timestamp(current["component_expires_at"]),
                               timestamp(mechanics["expires_at"]), timestamp(witness["expires_at"]),
                               timestamp(load(owner_raw)["observed_at"]) + timedelta(hours=24)),
            "Original evidence/review expiry cannot be extended")
    return {"schema_version": "anvil.task-capability-control.v1", "origin": "independent_qa",
            "project_id": str(project), "task_group_id": str(group), "source_sha256": group_body["source_sha256"],
            "target": "method:task-rubric-v1", "candidate_id": "task-rubric-v1",
            "candidate_sha256": current["candidate_sha256"], "runtime_source_sha256": current["runtime_source_sha256"],
            "runtime_image_sha256": current["runtime_image_sha256"], "broker_source_sha256": current["broker_source_sha256"],
            "release_sha256": current["release_sha256"], "publisher_login": login,
            "observation_sha256": digest(observation), "review_sha256": review_sha256,
            "issued_at": issued.isoformat(), "expires_at": expires.isoformat(),
            "controls": {name: {"status": "passed", "evidence_sha256": value} for name, value in control_hashes.items()},
            "evidence_scope": "technical_method_controls_only", "spending_authority": False,
            "human_review_approval": False, "model_performance": False}


def publish(c, project, group, observation, review, review_sha256, mechanics_raw, mechanics_review, witness, owner_raw):
    from anvil.kyc_policy_provision import enter
    from infra.gcp.kyc_binding_observation import observe as binding_observation

    enter(c, project)
    require(observation["project_id"] == str(project) and observation["task_group_id"] == str(group),
            "Exact reviewed publication project/group required")
    require(one(c, "SELECT anvil.task_method_binding_fence(%s) AS locked", (project,))["locked"],
            "Current binding publication fence required")
    login = one(c, "SELECT session_user AS login")["login"]
    now = one(c, "SELECT statement_timestamp() AS now")["now"]
    current = identity()
    mechanics = reviewed_mechanics(mechanics_raw, mechanics_review, current, now=now)
    group_body = checked_group(public_group(c, project, group), project, group)
    body = receipt(observation, review, review_sha256, current, group_body, mechanics, witness,
                   owner_raw, now=now, login=login)
    # Re-read current qualification and revocation state under the same locks
    # held through INSERT and COMMIT. Observation timestamps are not identities.
    for task, previous in zip(group_body["tasks"], observation["bindings"], strict=True):
        fresh = binding_observation(c, project, UUID(observation["resolved_input_id"]),
                                    task["task_id"], task["task_version"])
        require({k: v for k, v in fresh.items() if k != "observed_at"}
                == {k: v for k, v in previous.items() if k != "observed_at"},
                "Reviewed task bindings changed before publication")
    # These are fresh supported read guards, not replayed model/control jobs.
    require(public_group(c, project, UUID(observation["controls"]["missing"]["missing_group_id"])) is None
            and public_group(c, project, UUID(witness["foreign_group_id"])) is None,
            "Captured missing/foreign SQL boundary changed")
    identifier = uuid4()
    result = one(c, "SELECT anvil.publish_task_method(%s,%s,%s,%s,%s,%s) AS id",
                 (project, group, identifier, canonical(body).decode(), digest(body), timestamp(body["expires_at"])))
    require(result["id"] == identifier and identity() == current and public_group(c, project, group) == group_body,
            "Current method changed before publication commit")
    return {"id": str(identifier), "evidence_sha256": digest(body), "commit_observed": False,
            "scope": "technical_method_controls_only", "spending_authority": False,
            "human_review_approval": False, "model_performance": False}


def main():
    import argparse
    import signal
    import sys

    import psycopg
    from psycopg.rows import dict_row

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("observe", "publish", "revoke"))
    parser.add_argument("--project", type=UUID, required=True)
    parser.add_argument("--group", type=UUID)
    parser.add_argument("--input", type=UUID)
    parser.add_argument("--mechanics-sha256")
    parser.add_argument("--mechanics-review-sha256")
    parser.add_argument("--foreign-witness-sha256")
    parser.add_argument("--owner-observation-sha256")
    parser.add_argument("--observation-sha256")
    parser.add_argument("--review-sha256")
    parser.add_argument("--qualification", type=UUID)
    parser.add_argument("--reason")
    args = parser.parse_args()
    require(all(os.environ.get(key, "false") == "false" for key in
                ("ANVIL_LIVE_PROVIDERS_ENABLED", "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED", "ANVIL_REAL_EMAIL_ENABLED")),
            "This operator never authorizes model/provider/email dispatch")

    def expired(*_):
        raise TimeoutError("Method qualification operator deadline exceeded")

    signal.signal(signal.SIGALRM, expired)
    signal.alarm(300)
    if args.mode != "revoke":
        require(args.group is not None, "Exact captured group required")
        mechanics_raw = original(ARTIFACT_ROOT / "mechanics.stdout", args.mechanics_sha256)
        mechanics_review = load(original(ARTIFACT_ROOT / "mechanics-review.json", args.mechanics_review_sha256))
        witness = load(original(ARTIFACT_ROOT / "foreign-witness.json", args.foreign_witness_sha256))
        owner_raw = original(ARTIFACT_ROOT / "owner-observation.json", args.owner_observation_sha256)
    with psycopg.connect(os.environ["ANVIL_KYC_QUALIFIER_DATABASE_URL"], row_factory=dict_row,
                          connect_timeout=2, options="-c statement_timeout=5000 -c lock_timeout=1000") as c:
        if args.mode == "observe":
            require(args.input is not None, "Exact stored input required")
            c.execute("SET TRANSACTION READ ONLY")
            result = observe(c, args.project, args.group, args.input, mechanics_raw, mechanics_review, witness, owner_raw)
        elif args.mode == "publish":
            raw = original(ARTIFACT_ROOT / "observation.json", args.observation_sha256)
            observation = load(raw)
            require(canonical(observation) == raw, "Exact canonical original observation required")
            review = load(original(ARTIFACT_ROOT / "review.json", args.review_sha256))
            result = publish(c, args.project, args.group, observation, review, args.review_sha256,
                             mechanics_raw, mechanics_review, witness, owner_raw)
        else:
            from anvil.kyc_policy_provision import enter

            require(args.qualification is not None and type(args.reason) is str
                    and 10 <= len(args.reason.strip()) <= 2000, "Exact method and technical revocation reason required")
            enter(c, args.project)
            result = one(c, "SELECT anvil.revoke_task_method(%s,%s,%s,%s) AS id",
                         (args.project, args.qualification, uuid4(), args.reason))
            result = {"revocation_id": str(result["id"]), "commit_observed": False, "spending_authority": False}
    if "commit_observed" in result:
        result["commit_observed"] = True
    signal.alarm(0)
    sys.stdout.buffer.write(canonical(result))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        __import__("sys").stderr.write("task_method_qualification_blocked_no_authority_granted\n")
        raise SystemExit(1) from None
