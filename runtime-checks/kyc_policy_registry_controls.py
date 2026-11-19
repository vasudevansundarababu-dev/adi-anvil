"""Synthetic registry SOFTWARE controls, not legal/runtime qualification.

Requires a NEW fixture from kyc_sql_fixture_setup.v2, never a serving database.
The paired helper manufactures publication/conformance prerequisite assertions.
Those assumptions are explicitly NOT validated by these reader controls.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import signal
import stat
import sys
import time
import traceback
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4


class Deadline(BaseException):
    pass


def require(condition):
    if not condition:
        raise ValueError("Synthetic registry control refused")


def contract(model, value):
    # These are JSON contracts. Python strict mode correctly refuses ISO
    # date/UUID strings; validate their actual wire encoding instead.
    return model.model_validate_json(json.dumps(value, default=lambda item: item.isoformat()
        if isinstance(item, (date, datetime)) else str(item), allow_nan=False))


def private_json(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o077
                and info.st_nlink == 1 and info.st_size <= 32768)
        return json.loads(stream.read(32769))


def run(path):
    require(os.geteuid() == 0 and sys.flags.isolated and sys.dont_write_bytecode)
    config = private_json(path)
    require(set(config) == {"schema_version", "owner_dsn", "fixture_config"}
            and config["schema_version"] == "anvil.synthetic-policy-registry-controls.v1")
    fixture = private_json(config["fixture_config"])
    require(fixture["schema_version"] == "anvil.synthetic-sql-component-config.v2"
            and fixture["fixture_label"] == "synthetic-component-control-not-performance"
            and fixture["database"].startswith("anvil_golden_kyc_component_"))
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    from psycopg.rows import dict_row

    from anvil.golden_kyc_anvil import source_hash
    from anvil.golden_kyc_policy_registry import RegistryRecord, load
    from anvil.kyc_policy_reviews import Decision, decide, domain_subject, runtime_subject, stage
    from anvil.praxis_case_dataset import PolicyRef
    from anvil.praxis_generic_contract import canonical, digest

    require(source_hash() == fixture["golden_source_sha256"]
            and os.environ.get("ANVIL_RUNTIME_IMAGE_DIGEST") == fixture["runtime_image_sha256"])
    parameters = {"owner": conninfo_to_dict(config["owner_dsn"]), "reader": conninfo_to_dict(fixture["app_dsn"])}
    for params in parameters.values():
        host = Path(params.get("host", ""))
        require(not set(params) - {"host", "port", "user", "password", "dbname", "sslmode"}
                and params.get("dbname") == fixture["database"] and params.get("port", "5432") == "5432"
                and host.is_absolute() and host.resolve() == host and (host / ".s.PGSQL.5432").is_socket())
    require(parameters["owner"].get("user") == "postgres" and parameters["reader"].get("user") != "postgres")
    project, user = fixture["project_id"], fixture["user_id"]

    @contextmanager
    def connect(role="reader", *, foreign=False):
        with psycopg.connect(**parameters[role], connect_timeout=2, row_factory=dict_row,
                             options="-c statement_timeout=5000 -c lock_timeout=500") as connection:
            identity = connection.execute("SELECT current_database() AS database,session_user AS login,inet_server_addr() AS address").fetchone()
            require(identity == {"database": fixture["database"], "login": parameters[role]["user"], "address": None})
            if role == "reader":
                flags = connection.execute("SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=session_user").fetchone()
                parents = connection.execute("SELECT r.rolname FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid JOIN pg_roles u ON u.oid=m.member WHERE u.rolname=session_user").fetchall()
                require(flags and not any(flags.values()) and [row["rolname"] for row in parents] == ["anvil_app"])
                connection.execute("SET LOCAL ROLE anvil_app")
            connection.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)", (str(uuid4()) if foreign else project, user))
            yield connection

    helper_path = Path(__file__).with_name("kyc_policy_registry_fixture.py")
    info = helper_path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022 and helper_path.resolve() == helper_path)
    helper_spec = importlib.util.spec_from_file_location("synthetic_policy_registry_fixture", helper_path)
    helper = importlib.util.module_from_spec(helper_spec)
    helper_spec.loader.exec_module(helper)
    with connect("owner") as connection:
        require(not connection.execute("SELECT datname FROM pg_database WHERE datname NOT IN('postgres','template0','template1',%s)", (fixture["database"],)).fetchall())
        marker = connection.execute("UPDATE anvil.component_control_fixture SET consumed_at=clock_timestamp() WHERE fixture_nonce=%s "
            "AND project_id=%s AND fixture_label=%s AND consumed_at IS NULL AND created_at>clock_timestamp()-interval '30 minutes' RETURNING fixture_nonce",
            (fixture["fixture_nonce"], project, fixture["fixture_label"])).fetchone()
        require(marker is not None)
    reference = {"id": "synthetic-policy-not-law", "version": "test-only", "content_sha256": digest("synthetic-not-law"),
                 "publication_ref": "urn:synthetic:never-publication"}
    with connect("owner") as connection:
        scope = helper.source(connection, (None, project, user, None, fixture["pack_id"]), fixture["golden_source_sha256"],
                              reference, runtime_image=fixture["runtime_image_sha256"])
    policy = {"id": "synthetic-policy-set", "version": "test-only", "product": "individual", "governing_state": "CA",
              "charter_profile": "synthetic-charter-not-law", "federal_refs": [reference], "state_refs": [reference],
              "effective_from": "2020-01-01", "effective_until": "2099-01-01"}
    expiry = datetime.now(timezone.utc) + timedelta(minutes=10)
    from anvil.golden_kyc_policy_registry import PolicySet
    subject = domain_subject(scope, contract(PolicySet, policy))
    with connect("owner") as connection:
        staged = stage(connection, UUID(project), UUID(user), subject)
        domain = decide(connection, project, user, staged["id"], Decision(subject_sha256=staged["sha256"], decision="approved",
            rationale="MANUFACTURED synthetic software prerequisite; no legal review or QA qualification.",
            evidence_reference="urn:synthetic:not-reviewed", evidence_sha256=digest("manufactured domain prerequisite"), expires_at=expiry))
        identifier = str(uuid4())
        runtime = {"schema_version": "anvil.kyc-policy-review-receipt.v1", "id": identifier, "project_id": project,
            "kind": "runtime", "subject_id": None, "subject": runtime_subject(scope).model_dump(mode="json"),
            "subject_sha256": digest(runtime_subject(scope).model_dump(mode="json")), "reviewer_id": user,
            "reviewed_at": datetime.now(timezone.utc).isoformat(), "self_approved": False, "decision": "approved",
            "rationale": "MANUFACTURED isolated software prerequisite, NOT installed component qualification.",
            "evidence_reference": "urn:synthetic:never-qualification", "evidence_sha256": digest("manufactured runtime prerequisite"),
            "expires_at": expiry.isoformat()}
        connection.execute("INSERT INTO anvil.kyc_policy_review_receipts(id,project_id,subject_id,kind,created_by,body_canonical,content_sha256,expires_at) "
            "VALUES(%s,%s,NULL,'runtime',%s,%s,%s,%s)", (identifier, project, user, canonical(runtime).decode(), digest(runtime), expiry))
    body = contract(RegistryRecord, {"schema_version": "anvil.private-kyc-policy-qualification.v1", "id": str(uuid4()),
        "scope": scope.model_dump(mode="json"), "policy_set": policy, "policy_set_sha256": digest(policy),
        "domain_review_receipt": {"id": str(domain["id"]), "sha256": domain["sha256"]},
        "runtime_control_receipt": {"id": identifier, "sha256": digest(runtime)}, "expires_at": expiry - timedelta(seconds=1)})
    request = {"product": "individual", "governing_state": "CA", "charter_profile": policy["charter_profile"],
               "assessment_date": date(2026, 1, 1), "federal_refs": (PolicyRef.model_validate(reference),)}
    results = {}

    def observe(name, operation):
        try:
            value = operation()
            results[name] = {"status": "passed", "observation_sha256": digest(value), "observation": value}
        except Exception as error:
            results[name] = {"status": "failed", "exception_type": type(error).__name__}

    def read(*, expected="blocked", which=scope, changes=None, role="reader", foreign=False, expected_id=None, expected_policy=None):
        with connect("owner" if role == "writer" else role, foreign=foreign) as connection:
            if role == "writer":
                connection.execute("SET LOCAL ROLE anvil_kyc_qualifier")
            if foreign:
                require(connection.execute("SELECT count(*) AS n FROM anvil.kyc_application_policy_qualifications WHERE project_id=%s", (project,)).fetchone()["n"] == 0)
            result = load(connection, which, **(request | (changes or {})))
        require(result.run_authority == "not_granted")
        if expected == "candidate":
            require(result.status == "registry_candidate_not_admitted" and result.requirement is None and len(result.qualification_record_ids) == 1)
            if expected_id is not None:
                require(result.qualification_record_ids == (str(expected_id),))
            if expected_policy is not None:
                require(len(result.qualifications) == 1 and result.qualifications[0].policy_set_sha256 == expected_policy)
        else:
            require(result.requirement is not None)
        if role == "writer":
            require(result.requirement == "AV_KYC_SCOPED_REGISTRY_REQUIRED")
        if role == "owner":
            require(result.requirement == "AV_KYC_REGISTRY_SCOPE_REQUIRED")
        return {"status": result.status, "requirement": result.requirement, "run_authority": result.run_authority,
                "qualification_record_ids": list(result.qualification_record_ids),
                "policy_set_sha256s": [value.policy_set_sha256 for value in result.qualifications]}

    def append(record, *, corrupt=False):
        value = record.model_dump(mode="json")
        with connect("owner") as connection:
            connection.execute("INSERT INTO anvil.kyc_application_policy_qualifications(id,project_id,binding_id,created_by,body_canonical,scope_canonical,scope_sha256,content_sha256,expires_at) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)", (record.id, project, scope.project_binding_id, user,
                canonical(value).decode(), canonical(value["scope"]).decode(), digest(value["scope"]), "0" * 64 if corrupt else digest(value), record.expires_at))

    def revoke(record):
        with connect("owner") as connection:
            connection.execute("INSERT INTO anvil.kyc_application_policy_revocations(id,project_id,qualification_id,created_by,reason) VALUES(%s,%s,%s,%s,%s)",
                (str(uuid4()), project, record.id, user, "Synthetic control withdrawal, not a legal decision."))

    observe("missing", lambda: read())
    append(body)
    observe("exact_candidate_not_admitted", lambda: read(expected="candidate"))
    observe("owner_refused", lambda: read(role="owner"))
    observe("writer_refused", lambda: read(role="writer"))
    observe("wrong_project", lambda: read(foreign=True))
    def wrong_product():
        try:
            with connect() as connection:
                load(connection, scope, **(request | {"product": "adult_joint"}))
        except ValueError as error:
            require(str(error) == "Exact application type/state/charter/date required")
            return {"typed_product_scope_mismatch": "refused before query"}
        raise ValueError("Mismatched product should fail the typed scope contract")

    observe("wrong_product", wrong_product)
    for name, changes in (("state", {"governing_state": "TX"}),
                          ("charter", {"charter_profile": "wrong"}), ("date", {"assessment_date": date(2100, 1, 1)}),
                          ("reference", {"federal_refs": (PolicyRef.model_validate(reference | {"content_sha256": "0" * 64}),)})):
        observe("wrong_" + name, lambda changes=changes: read(changes=changes))
    observe("wrong_source_scope", lambda: read(which=scope.model_copy(update={"runtime_source_sha256": "0" * 64})))

    def duplicate():
        other = body.model_copy(update={"id": uuid4()})
        append(other)
        try:
            result = read()
            require(result["requirement"] == "AV_KYC_POLICY_QUALIFICATION_AMBIGUOUS")
            return result
        finally:
            revoke(other)

    observe("ambiguous_duplicate", duplicate)

    def corrupt():
        try:
            append(body.model_copy(update={"id": uuid4()}), corrupt=True)
        except psycopg.errors.CheckViolation:
            return {"database_hash_constraint": "rejected", "reader_corrupt_stored_row": "not_injected; constraints intact"}
        raise ValueError("Corrupt hash inserted")

    observe("corrupt_hash_storage_rejected", corrupt)
    revoke(body)
    observe("revoked", lambda: read())

    def expired():
        record = body.model_copy(update={"id": uuid4(), "expires_at": datetime.now(timezone.utc) + timedelta(seconds=5)})
        append(record)
        read(expected="candidate")
        time.sleep(5.2)
        return read()

    observe("expired", expired)

    def product_state_matrix():
        from anvil.golden_kyc_resolved_store import policy_scope

        cells = []
        for product in ("individual", "adult_joint", "teen_joint", "custodial"):
            with connect("owner") as connection:
                current_scope = policy_scope(connection, UUID(project), scope.resolved_input_id,
                    "KYC-" + product, scope.revision_id)
            for state in ("CA", "NY", "TX", "FL", "IL"):
                with connect() as connection:
                    actual = connection.execute("SELECT id,snapshot,snapshot_sha256 FROM banking.applications WHERE project_id=%s AND pack_id=%s "
                        "AND snapshot->>'product'=%s AND snapshot->>'governing_state'=%s ORDER BY id LIMIT 1", (project, fixture["pack_id"], product, state)).fetchone()
                    require(actual is not None and digest(actual["snapshot"]) == actual["snapshot_sha256"])
                    original = json.loads(connection.execute("SELECT body_canonical FROM anvil.kyc_resolved_input_versions WHERE project_id=%s AND id=%s",
                        (project, scope.resolved_input_id)).fetchone()["body_canonical"])
                member = [row for row in original["rows"] if row["application_id"] == actual["id"]]
                require(len(member) == 1 and member[0]["application_sha256"] == actual["snapshot_sha256"]
                    and member[0]["task_id"] == current_scope.task_id and member[0]["revision_id"] == current_scope.revision_id
                    and member[0]["product"] == actual["snapshot"]["product"] == product
                    and member[0]["governing_state"] == actual["snapshot"]["governing_state"] == state)
                assessment = date.fromisoformat(actual["snapshot"]["assessment_date"])
                charter = actual["snapshot"]["charter_applicability"]["profile"]
                selected = policy | {"id": "synthetic-" + product + "-" + state, "product": actual["snapshot"]["product"],
                    "governing_state": actual["snapshot"]["governing_state"], "charter_profile": charter}
                require(date.fromisoformat(selected["effective_from"]) <= assessment < date.fromisoformat(selected["effective_until"]))
                current_subject = domain_subject(current_scope, contract(PolicySet, selected))
                runtime_id = str(uuid4())
                runtime_body = runtime | {"id": runtime_id, "subject": runtime_subject(current_scope).model_dump(mode="json"),
                    "subject_sha256": digest(runtime_subject(current_scope).model_dump(mode="json")),
                    "rationale": "MANUFACTURED product/state SOFTWARE control only; not legal or installed qualification."}
                with connect("owner") as connection:
                    staged_subject = stage(connection, UUID(project), UUID(user), current_subject)
                    reviewed = decide(connection, project, user, staged_subject["id"], Decision(
                        subject_sha256=staged_subject["sha256"], decision="approved", expires_at=expiry,
                        rationale="MANUFACTURED product/state reader prerequisite, not a real approval.",
                        evidence_reference="urn:synthetic:not-legal-review", evidence_sha256=digest(selected)))
                    connection.execute("INSERT INTO anvil.kyc_policy_review_receipts(id,project_id,subject_id,kind,created_by,body_canonical,content_sha256,expires_at) "
                        "VALUES(%s,%s,NULL,'runtime',%s,%s,%s,%s)",
                        (runtime_id, project, user, canonical(runtime_body).decode(), digest(runtime_body), expiry))
                record = contract(RegistryRecord, {"schema_version": "anvil.private-kyc-policy-qualification.v1", "id": str(uuid4()),
                    "scope": current_scope.model_dump(mode="json"), "policy_set": selected, "policy_set_sha256": digest(selected),
                    "domain_review_receipt": {"id": str(reviewed["id"]), "sha256": reviewed["sha256"]},
                    "runtime_control_receipt": {"id": runtime_id, "sha256": digest(runtime_body)}, "expires_at": expiry-timedelta(seconds=1)})
                append(record)
                observed = read(expected="candidate", which=current_scope, changes={"product": actual["snapshot"]["product"],
                    "governing_state": actual["snapshot"]["governing_state"], "charter_profile": charter, "assessment_date": assessment},
                    expected_id=record.id, expected_policy=digest(selected))
                cells.append({"product": product, "state": state, "application_id": actual["id"], "application_sha256": actual["snapshot_sha256"],
                    "task_id": current_scope.task_id, "revision_id": current_scope.revision_id,
                    "environment_binding_sha256": current_scope.environment_binding_sha256, "evaluator_bindings_sha256": current_scope.evaluator_bindings_sha256,
                    "status": observed["status"], "run_authority": observed["run_authority"],
                    "qualification_record_ids": observed["qualification_record_ids"], "policy_set_sha256s": observed["policy_set_sha256s"]})
        require(len(cells) == len({(cell["product"], cell["state"]) for cell in cells}) == len({cell["application_id"] for cell in cells}) == 20
            and len({cell["task_id"] for cell in cells}) == 4 and len({cell["environment_binding_sha256"] for cell in cells}) == 1
            and len({cell["evaluator_bindings_sha256"] for cell in cells}) == 1)
        return {"cells": cells, "manufactured_prerequisites": True, "actual_legal_review": False, "production_qualification_granted": False}

    observe("twenty_product_state_software_candidates", product_state_matrix)
    print(json.dumps({"schema_version": "anvil.synthetic-policy-registry-observations.v1", "controls": results,
        "manufactured_assumptions": ["Synthetic template publication/conformance assertions", "Synthetic domain decision and runtime review rows; not human/legal/installed qualification"],
        "registry_positive_status": "registry_candidate_not_admitted", "run_authority": "not_granted", "native_qualified": False,
        "installed_qualification_file_written": False, "manufactured_prerequisite_rows_written": True,
        "production_qualification_granted": False, "model_calls_authorized": 0, "actual_model_calls": None,
        "limitations": ["Corrupt stored-row reader branch not injected: real SQL hash constraints reject corruption first", "Not actual legal review or real authored-task applicability"],
        "source_sha256": fixture["golden_source_sha256"], "runtime_image_sha256": fixture["runtime_image_sha256"],
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "helper_sha256": hashlib.sha256(helper_path.read_bytes()).hexdigest()}, sort_keys=True))
    return 0 if all(result["status"] == "passed" for result in results.values()) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGALRM, lambda *args: (_ for _ in ()).throw(Deadline()))
    signal.alarm(180)
    try:
        raise SystemExit(run(args.config))
    except (Exception, Deadline) as error:
        details = [{"location": list(item["loc"]), "type": item["type"]} for item in error.errors(include_input=False, include_url=False)] if type(error).__name__ == "ValidationError" else []
        print(json.dumps({"status": "blocked_or_unknown_no_replay", "exception_type": type(error).__name__, "run_authority": "not_granted", "native_qualified": False,
            "validation_locations": details, "frames": [{"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name} for frame in traceback.extract_tb(error.__traceback__)[-8:]]}))
        raise SystemExit(1) from None
