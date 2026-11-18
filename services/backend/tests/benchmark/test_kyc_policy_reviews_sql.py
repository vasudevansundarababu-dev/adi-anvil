"""Real isolated SQL controls; manufactured subjects never qualify QA policy."""

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi import HTTPException
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from test_golden_kyc_sql import connection
from test_golden_kyc_sql import owned as owned_fixture

from anvil.golden_kyc_policy_registry import ReceiptReference
from anvil.kyc_policy_reviews import Decision, DomainSubject, decide, resolve, revoke
from anvil.praxis_generic_contract import canonical, digest

owned = owned_fixture


def subject():
    ref = {"id": "synthetic-policy", "version": "test-v1", "content_sha256": "a" * 64,
           "publication_ref": "urn:synthetic:sql-test-not-qa"}
    return DomainSubject.model_validate_json(canonical({
        "schema_version": "anvil.kyc-policy-domain-subject.v1",
        "template": {"id": str(uuid4()), "version": 8, "sha256": "b" * 64},
        "task_id": "synthetic-task", "revision_id": "synthetic-r8",
        "policy_set": {"id": "synthetic-policy-set", "version": "test-v1", "product": "individual",
                       "governing_state": "CA", "charter_profile": "synthetic-charter",
                       "federal_refs": [ref], "state_refs": [ref],
                       "effective_from": "2026-01-01", "effective_until": "2027-01-01"}}))


def scope(c, owned, user=None, role="anvil_app"):
    c.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",
              (owned[1], user or owned[2]))
    c.execute({"anvil_app": "SET LOCAL ROLE anvil_app",
               "anvil_kyc_qualifier": "SET LOCAL ROLE anvil_kyc_qualifier"}[role])


def staged(owned):
    item, identifier = subject(), uuid4()
    body = item.model_dump(mode="json")
    with connection(owned) as c:
        scope(c, owned)
        c.execute("INSERT INTO anvil.kyc_policy_review_subjects(id,project_id,created_by,body_canonical,content_sha256) "
                  "VALUES(%s,%s,%s,%s,%s)", (identifier, owned[1], owned[2], canonical(body).decode(), digest(body)))
    return item, identifier


def decision(item):
    return Decision(subject_sha256=digest(item.model_dump(mode="json")), decision="approved", rationale="Manufactured SQL control, not real policy approval.",
                    evidence_reference="urn:synthetic:sql-review", evidence_sha256="c" * 64,
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1))


def test_two_po_self_approval_denies_other_po_decision_resolves_and_revokes(owned):
    item, identifier = staged(owned)
    with connection(owned) as c:
        scope(c, owned)
        with pytest.raises(HTTPException, match="409"):
            decide(c, owned[1], owned[2], identifier, decision(item))
    with connection(owned) as c:
        scope(c, owned, owned[3])
        result = decide(c, owned[1], owned[3], identifier, decision(item))
        assert result["self_approved"] is False and result["qualification_granted"] is False
    reference = ReceiptReference(id=UUID(result["id"]), sha256=result["sha256"])
    with connection(owned) as c:
        scope(c, owned)
        resolve(c, UUID(owned[1]), reference, item, expires_at=datetime.now(timezone.utc) + timedelta(minutes=10))
        wrong = item.model_copy(update={"revision_id": "wrong-task-revision"})
        with pytest.raises(ValueError, match="Exact current"):
            resolve(c, UUID(owned[1]), reference, wrong, expires_at=datetime.now(timezone.utc) + timedelta(minutes=10))
        revoke(c, owned[1], owned[2], reference.id, "Withdraw manufactured control review.")
    with connection(owned) as c:
        scope(c, owned)
        with pytest.raises(ValueError, match="unrevoked"):
            resolve(c, UUID(owned[1]), reference, item, expires_at=datetime.now(timezone.utc) + timedelta(minutes=10))


def test_single_po_self_approval_is_recorded_and_worker_capabilities_remain_disjoint(owned):
    item, identifier = staged(owned)
    with connection(owned) as c:
        c.execute("UPDATE anvil.memberships SET active=false WHERE project_id=%s AND user_id=%s", (owned[1], owned[3]))
    with connection(owned) as c:
        scope(c, owned)
        result = decide(c, owned[1], owned[2], identifier, decision(item))
        assert result["self_approved"] is True
        for role in ("anvil_app", "anvil_worker", "anvil_golden_scheduler", "anvil_golden_grader"):
            assert not c.execute("SELECT pg_has_role(%s,'anvil_kyc_qualifier','MEMBER') AS p", (role,)).fetchone()["p"]
            assert not c.execute("SELECT has_table_privilege(%s,'anvil.kyc_application_policy_qualifications','INSERT') AS p",
                                 (role,)).fetchone()["p"]


def test_decision_requires_displayed_subject_hash_and_current_reviewer(owned):
    item, identifier = staged(owned)
    wrong = decision(item).model_copy(update={"subject_sha256": "f" * 64})
    with connection(owned) as c:
        scope(c, owned, owned[3])
        with pytest.raises(HTTPException, match="409"):
            decide(c, owned[1], owned[3], identifier, wrong)
    with connection(owned) as c:
        scope(c, owned, owned[3])
        receipt = decide(c, owned[1], owned[3], identifier, decision(item))
    with connection(owned) as c:
        c.execute("UPDATE anvil.memberships SET active=false WHERE project_id=%s AND user_id=%s",
                  (owned[1], owned[3]))
    with connection(owned) as c:
        scope(c, owned)
        with pytest.raises(ValueError, match="unrevoked"):
            resolve(c, UUID(owned[1]), ReceiptReference(id=UUID(str(receipt["id"])), sha256=receipt["sha256"]), item,
                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=5))


def test_direct_app_insert_cannot_mint_runtime_evidence_or_spoof_receipt(owned):
    item, identifier = staged(owned)
    now = datetime.now(timezone.utc)
    receipt_id = uuid4()
    body = {"schema_version": "anvil.kyc-policy-review-receipt.v1", "id": str(receipt_id),
            "project_id": owned[1], "reviewer_id": owned[2], "kind": "runtime", "subject_id": None,
            "subject": {"schema_version": "anvil.kyc-policy-runtime-subject.v1"},
            "expires_at": (now + timedelta(hours=1)).isoformat(), "decision": "approved"}
    with connection(owned) as c:
        scope(c, owned)
        with pytest.raises(Exception, match="row-level security"):
            c.execute("INSERT INTO anvil.kyc_policy_review_receipts(id,project_id,kind,created_by,body_canonical,content_sha256,expires_at) "
                      "VALUES(%s,%s,'runtime',%s,%s,%s,%s)",
                      (receipt_id, owned[1], owned[2], canonical(body).decode(), digest(body), now + timedelta(hours=1)))


def test_hash_only_policy_approval_is_not_a_current_review(owned):
    with connection(owned) as c:
        scope(c, owned)
        body = {"domain_review_receipt": {"id": str(uuid4()), "sha256": "a" * 64},
                "runtime_control_receipt": {"id": str(uuid4()), "sha256": "b" * 64}}
        assert c.execute("SELECT anvil.kyc_policy_reviews_current(%s,%s::jsonb,%s) AS current",
                         (owned[1], canonical(body).decode(), datetime.now(timezone.utc) + timedelta(minutes=10))).fetchone()["current"] is False


def test_direct_sql_revocation_obeys_same_project_fence_as_producer(owned):
    item, identifier = staged(owned)
    with connection(owned) as c:
        scope(c, owned, owned[3])
        receipt = decide(c, owned[1], owned[3], identifier, decision(item))
    with connection(owned) as holder:
        holder.execute("SELECT pg_advisory_xact_lock(hashtextextended('anvil.kyc.policy.review:'||%s,0))",
                       (owned[1],))
        with connection(owned) as writer:
            scope(writer, owned)
            writer.execute("SET LOCAL lock_timeout='100ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                writer.execute("INSERT INTO anvil.kyc_policy_review_revocations(id,project_id,receipt_id,created_by,reason) "
                               "VALUES(%s,%s,%s,%s,%s)",
                               (uuid4(), owned[1], receipt["id"], owned[2], "Synthetic direct SQL revocation control."))


def test_actual_operator_login_is_bound_in_sql_not_just_a_user_guc(owned):
    from anvil.kyc_policy_provision import enter

    staged(owned)
    login, password = "kyc_qualifier_test_" + secrets.token_hex(5), secrets.token_urlsafe(32)
    with connection(owned) as c:
        c.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION")
                  .format(sql.Identifier(login), sql.Literal(password)))
        c.execute(sql.SQL("GRANT anvil_kyc_qualifier TO {}").format(sql.Identifier(login)))
        c.execute("INSERT INTO anvil.kyc_policy_operator_principals(login_role,project_id,user_id) VALUES(%s,%s,%s)",
                  (login, owned[1], owned[2]))
    with psycopg.connect(make_conninfo(owned[0], user=login, password=password), row_factory=dict_row) as c:
        assert str(enter(c, UUID(owned[1]))) == owned[2]
        assert c.execute("SELECT count(*) AS n FROM anvil.kyc_policy_review_subjects").fetchone()["n"] == 1
        c.execute("SELECT set_config('anvil.user',%s,true)", (owned[3],))
        assert c.execute("SELECT count(*) AS n FROM anvil.kyc_policy_review_subjects").fetchone()["n"] == 0
        assert c.execute("SELECT anvil.kyc_policy_operator_scope(%s) AS allowed", (owned[1],)).fetchone()["allowed"] is False
        c.execute("SELECT set_config('anvil.project',%s,true)", (str(uuid4()),))
        assert c.execute("SELECT count(*) AS n FROM anvil.praxis_template_qualifications").fetchone()["n"] == 0


def test_current_review_checker_binds_both_real_ledger_subjects_and_revocation(owned):
    from copy import deepcopy

    from anvil.kyc_policy_provision import enter

    item, identifier = staged(owned)
    with connection(owned) as c:
        scope(c, owned, owned[3])
        domain = decide(c, owned[1], owned[3], identifier, decision(item))
    login, password = "kyc_review_test_" + secrets.token_hex(5), secrets.token_urlsafe(32)
    with connection(owned) as c:
        c.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION")
                  .format(sql.Identifier(login), sql.Literal(password)))
        c.execute(sql.SQL("GRANT anvil_kyc_qualifier TO {}").format(sql.Identifier(login)))
        c.execute("INSERT INTO anvil.kyc_policy_operator_principals VALUES(%s,%s,%s)", (login, owned[1], owned[2]))
    runtime_subject = {"schema_version": "anvil.kyc-policy-runtime-subject.v1", "runtime_source_sha256": "a" * 64,
                       "runtime_image_sha256": "b" * 64, "environment_binding_sha256": "c" * 64,
                       "evaluator_bindings_sha256": "d" * 64}
    runtime_id = uuid4()
    expires = datetime.now(timezone.utc) + timedelta(minutes=30)
    body = {"schema_version": "anvil.kyc-policy-review-receipt.v1", "id": str(runtime_id),
            "project_id": owned[1], "reviewer_id": owned[2], "kind": "runtime", "subject_id": None,
            "subject": runtime_subject, "expires_at": expires.isoformat(), "decision": "approved",
            "rationale": "Manufactured isolated SQL evidence only; never installed in QA."}
    with psycopg.connect(make_conninfo(owned[0], user=login, password=password), row_factory=dict_row) as c:
        enter(c, UUID(owned[1]))
        c.execute("INSERT INTO anvil.kyc_policy_review_receipts(id,project_id,kind,created_by,body_canonical,content_sha256,expires_at) "
                  "VALUES(%s,%s,'runtime',%s,%s,%s,%s)",
                  (runtime_id, owned[1], owned[2], canonical(body).decode(), digest(body), expires))
    candidate = {"scope": {"template": item.template.model_dump(mode="json"), "task_id": item.task_id,
                           "revision_id": item.revision_id, **{key: value for key, value in runtime_subject.items() if key != "schema_version"}},
                 "policy_set": item.policy_set.model_dump(mode="json"),
                 "domain_review_receipt": {"id": str(domain["id"]), "sha256": domain["sha256"]},
                 "runtime_control_receipt": {"id": str(runtime_id), "sha256": digest(body)}}
    until = datetime.now(timezone.utc) + timedelta(minutes=5)
    with connection(owned) as c:
        scope(c, owned)

        def current(value):
            return c.execute("SELECT anvil.kyc_policy_reviews_current(%s,%s::jsonb,%s) AS p",
                             (owned[1], canonical(value).decode(), until)).fetchone()["p"]

        assert current(candidate) is True
        for field in ("environment_binding_sha256", "evaluator_bindings_sha256", "runtime_source_sha256"):
            wrong = deepcopy(candidate)
            wrong["scope"][field] = "f" * 64
            assert current(wrong) is False
        wrong = deepcopy(candidate)
        wrong["policy_set"]["charter_profile"] = "different-charter"
        assert current(wrong) is False
        revoke(c, owned[1], owned[2], domain["id"], "Withdraw synthetic SQL control decision.")
        assert current(candidate) is False


@pytest.mark.parametrize("materialization_version", [1, 2])
def test_synthetic_full_custody_producer_appends_atomically_and_replays_exactly(owned, monkeypatch, materialization_version):
    """Actual SQL/FKs/triggers; manufactured evidence is never QA admission."""
    import hashlib

    from kyc_policy_synthetic_source import source
    from anvil import golden_component_qualification
    from anvil.golden_kyc_anvil import source_hash
    from anvil.golden_kyc_policy_delivery import Materialization, load as delivery_load
    from anvil.golden_kyc_policy_registry import RegistryRecord
    from anvil.kyc_policy_provision import enter, provision, retain_runtime_review
    from anvil.kyc_policy_reviews import domain_subject, runtime_subject, stage

    text = "Manufactured public policy software control; no legal acceptance."
    if materialization_version == 2:
        text = text * 640
    fingerprint = hashlib.sha256(text.encode()).hexdigest()
    ref = {"id": "synthetic-policy", "version": "test-v1", "content_sha256": fingerprint,
           "publication_ref": "urn:synthetic:never-QA"}
    with connection(owned) as c:
        actual = source(c, owned, source_hash(), ref)
    policies = subject().policy_set.model_dump(mode="json")
    policies.update(federal_refs=[ref], state_refs=[ref])
    expected = domain_subject(actual, subject().policy_set.model_validate_json(canonical(policies)))
    with connection(owned) as c:
        scope(c, owned)
        staged_result = stage(c, UUID(owned[1]), UUID(owned[2]), expected)
    with connection(owned) as c:
        scope(c, owned, owned[3])
        domain = decide(c, owned[1], owned[3], staged_result["id"], decision(expected))
    login, password = "kyc_producer_test_" + secrets.token_hex(5), secrets.token_urlsafe(32)
    with connection(owned) as c:
        c.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION")
                  .format(sql.Identifier(login), sql.Literal(password)))
        c.execute(sql.SQL("GRANT anvil_kyc_qualifier TO {}").format(sql.Identifier(login)))
        c.execute("INSERT INTO anvil.kyc_policy_operator_principals VALUES(%s,%s,%s)", (login, owned[1], owned[2]))
    expires = datetime.now(timezone.utc) + timedelta(minutes=20)
    evidence = {"golden_source_sha256": actual.runtime_source_sha256, "runtime_image_sha256": actual.runtime_image_sha256,
                "expires_at": (expires + timedelta(minutes=5)).isoformat(), "origin": "synthetic-isolated-SQL-not-QA",
                "binding_controls": [{"subject": runtime_subject(actual).model_dump(mode="json"), "status": "passed",
                                      "evidence_sha256": "a" * 64}]}
    monkeypatch.setattr(golden_component_qualification, "installed", lambda: {"ready": True, "evidence": evidence})
    dsn = make_conninfo(owned[0], user=login, password=password)
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        user = enter(c, actual.project_id)
        runtime = retain_runtime_review(c, actual.project_id, user, actual)
    record = RegistryRecord.model_validate_json(canonical({
        "schema_version": "anvil.private-kyc-policy-qualification.v1", "id": str(uuid4()),
        "scope": actual.model_dump(mode="json"), "policy_set": policies, "policy_set_sha256": digest(policies),
        "domain_review_receipt": {"id": str(domain["id"]), "sha256": domain["sha256"]},
        "runtime_control_receipt": runtime, "expires_at": expires.isoformat()}))
    artifact = {"reference": ref, "hash_scheme": "sha256_raw_utf8", "artifact_utf8": text,
                "artifact_sha256": fingerprint, "public_text_utf8": text, "public_text_sha256": fingerprint}
    materialization = Materialization.model_validate_json(canonical({
        "schema_version": f"anvil.kyc-application-policy-materialization.v{materialization_version}", "id": str(uuid4()),
        "qualification_id": str(record.id), "scope": actual.model_dump(mode="json"),
        "policy_set_sha256": record.policy_set_sha256, "artifacts": [artifact | {"kind": kind} for kind in ("common", "state")],
        "expires_at": expires.isoformat()}))
    if materialization_version == 2:
        with pytest.raises(ValueError, match="Legacy public policy text bound"):
            Materialization.model_validate_json(canonical(materialization.model_dump(mode="json") |
                {"schema_version": "anvil.kyc-application-policy-materialization.v1"}))
    for _ in range(2):
        with psycopg.connect(dsn, row_factory=dict_row) as c:
            user = enter(c, actual.project_id)
            result = provision(c, actual.project_id, user, record, materialization)
            assert result["paid_calls"] is False and result["commit_observed"] is False
    successor = record.model_copy(update={"id": uuid4()})
    conflict = materialization.model_copy(update={"qualification_id": successor.id})
    with pytest.raises(ValueError, match="different immutable content"):
        with psycopg.connect(dsn, row_factory=dict_row) as c:
            user = enter(c, actual.project_id)
            provision(c, actual.project_id, user, successor, conflict)
    with connection(owned) as c:
        scope(c, owned)
        delivered = delivery_load(c, actual, "synthetic-application", record.id)
        if materialization_version == 1:
            assert delivered.public["bound_common_rules"][0]["text"] == text
        else:
            assert delivered.public["schema_version"] == "anvil.bound-application-policy.v2"
            assert delivered.documents and "bound_common_rules" not in delivered.public
            assert len(canonical(materialization.model_dump(mode="json"))) > 131072
        assert delivered.run_authority == "not_granted"
        assert c.execute("SELECT count(*) AS n FROM anvil.kyc_application_policy_qualifications WHERE project_id=%s",
                         (owned[1],)).fetchone()["n"] == 1
        assert c.execute("SELECT count(*) AS n FROM anvil.kyc_application_policy_materializations WHERE project_id=%s",
                         (owned[1],)).fetchone()["n"] == 1
        revoke(c, owned[1], owned[2], domain["id"], "Synthetic fixture review withdrawn after controls.")
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        user = enter(c, actual.project_id)
        with pytest.raises(ValueError, match="unrevoked"):
            provision(c, actual.project_id, user, record, materialization)
