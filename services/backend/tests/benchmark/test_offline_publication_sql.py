"""Actual isolated SQL; manufactured publication records are not QA approval."""

from datetime import datetime, timedelta, timezone
import json
import secrets
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from test_golden_kyc_sql import connection, owned as owned_fixture
from test_kyc_policy_reviews_sql import scope
from anvil import praxis_offline_publication as offline
from anvil import praxis_template_registry as registry
from anvil.praxis_generic_contract import TemplateRef, canonical, digest, load

owned = owned_fixture


def staged(owned, status_fields=None):
    spec = json.loads(Path("fixtures/praxis-generic-v1/template-spec.json").read_text())
    with connection(owned) as c:
        scope(c, owned)
        template = registry.register(c, owned[1], owned[2], spec)
        record = {**(status_fields if status_fields is not None else {"publication_status": "published"}),
                  "template_id": template["template_id"], "version": template["version"],
                  "published_at": "2026-01-01T00:00:00Z",
                  "template_sha256": template["spec_sha256"], "part_hashes": template["part_hashes"],
                  "synthetic_only": "not-independent-publication-not-QA"}
        subject = offline.stage(c, owned[1], owned[2], template["id"], offline.Upload(record_utf8=canonical(record).decode()))
    return template, record, subject


def decision(subject, seconds=3600):
    return offline.Attestation(subject_sha256=subject["sha256"], rationale="Manufactured local SQL control, not actual publication approval.",
                               expires_at=datetime.now(timezone.utc) + timedelta(seconds=seconds))


def current(c, owned, template, receipt):
    return c.execute("SELECT anvil.template_publication_current(%s,%s,%s) AS current",
                     (owned[1], template["id"], Jsonb(receipt))).fetchone()["current"]


def test_explicit_other_po_attestation_qualifies_local_basis_without_api_event(owned, monkeypatch):
    template, _, subject = staged(owned)
    with connection(owned) as c:
        scope(c, owned)
        assert offline.basis(c, owned[1], template["id"]) is None
        with pytest.raises(HTTPException, match="409"):
            offline.attest(c, owned[1], owned[2], template["id"], subject["id"], decision(subject))
    with connection(owned) as c:
        scope(c, owned, owned[3])
        result = offline.attest(c, owned[1], owned[3], template["id"], subject["id"], decision(subject))
        assert result["publication_verified"] is False and result["publication_accepted"] is True
        assert result["self_approved"] is False
    monkeypatch.setattr("anvil.praxis_generic_environment.conformance", lambda execution: {
        "passed": True, "origin": "synthetic-isolated-SQL-control", "model_performance": False})
    with connection(owned) as c:
        scope(c, owned)
        qualified = registry.qualify(c, owned[1], owned[2], template["id"])
        receipt = qualified["receipt"]
        assert receipt["status"] == "qualified"
        assert receipt["publication_verified"] is False and receipt["publication_accepted"] is True
        assert receipt["publication_basis"]["kind"] == "po_attested_offline"
        assert current(c, owned, template, receipt)
        c.execute("RESET ROLE")
        for role in ("anvil_golden_scheduler", "anvil_golden_grader", "anvil_kyc_context_owner"):
            c.execute(f"SET LOCAL ROLE {role}")
            assert current(c, owned, template, receipt) is True
            c.execute("RESET ROLE")
        scope(c, owned)
        assert c.execute("SELECT count(*) AS n FROM anvil.praxis_template_events WHERE project_id=%s",
                         (owned[1],)).fetchone()["n"] == 0
        reference = TemplateRef(id=template["template_id"], version=template["version"], sha256=template["spec_sha256"])
        assert registry.lookup(c, owned[1], reference)["qualified"] is True
        changed = receipt | {"publication_basis": receipt["publication_basis"] | {"subject_sha256": "f" * 64}}
        assert current(c, owned, template, changed) is False
    login, password = "offline_qualifier_test_" + secrets.token_hex(5), secrets.token_urlsafe(32)
    with connection(owned) as c:
        c.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION")
                  .format(sql.Identifier(login), sql.Literal(password)))
        c.execute(sql.SQL("GRANT anvil_kyc_qualifier TO {}").format(sql.Identifier(login)))
        c.execute("INSERT INTO anvil.kyc_policy_operator_principals VALUES(%s,%s,%s)", (login, owned[1], owned[2]))
    with psycopg.connect(make_conninfo(owned[0], user=login, password=password), row_factory=dict_row) as c:
        from anvil.kyc_policy_provision import enter

        enter(c, UUID(owned[1]))
        assert current(c, owned, template, receipt) is True
        c.execute("SELECT set_config('anvil.user',%s,true)", (owned[3],))
        assert current(c, owned, template, receipt) is False
    with connection(owned) as c:
        scope(c, owned)
        offline.revoke(c, owned[1], owned[2], template["id"], subject["id"], "Withdraw synthetic local publication evidence.")
        assert current(c, owned, template, receipt) is False
        assert registry.lookup(c, owned[1], reference)["qualified"] is False
    with connection(owned) as c:
        c.execute("SELECT set_config('anvil.project',%s,true)", (owned[1],))
        for role in ("anvil_golden_scheduler", "anvil_golden_grader", "anvil_kyc_context_owner"):
            c.execute(f"SET LOCAL ROLE {role}")
            assert current(c, owned, template, receipt) is False
            c.execute("RESET ROLE")


def test_single_po_self_attestation_audits_identity_and_expiry_invalidates_runtime(owned):
    template, _, subject = staged(owned)
    with connection(owned) as c:
        c.execute("UPDATE anvil.memberships SET active=false WHERE project_id=%s AND user_id=%s", (owned[1], owned[3]))
    with connection(owned) as c:
        scope(c, owned)
        result = offline.attest(c, owned[1], owned[2], template["id"], subject["id"], decision(subject, seconds=1))
        assert result["self_approved"] is True
        event = c.execute("SELECT actor_id,metadata FROM anvil.audit_events WHERE project_id=%s "
                          "AND action='praxis.offline_publication.attested'", (owned[1],)).fetchone()
        assert str(event["actor_id"]) == owned[2] and event["metadata"]["self_approved"] is True
        basis = offline.basis(c, owned[1], template["id"])
        receipt = {"publication_verified": False, "publication_accepted": True, "publication_basis": basis}
        assert current(c, owned, template, receipt)
    with connection(owned) as c:
        c.execute("SELECT pg_sleep(1.1)")
        c.execute("SELECT set_config('anvil.project',%s,true)", (owned[1],))
        c.execute("SET LOCAL ROLE anvil_golden_scheduler")
        assert current(c, owned, template, receipt) is False


@pytest.mark.parametrize("fault", ["candidate", "alias_conflict", "missing_status", "null_status", "missing_date", "null_date", "naive_date", "future_date",
                                   "wrong_parts", "wrong_template", "wrong_identity", "internal_row_identity", "wrong_version", "string_version", "missing_identity"])
def test_unpublished_or_unbound_record_is_not_stageable(owned, fault):
    template, record, _ = staged(owned)
    if fault == "candidate":
        record["publication_status"] = "candidate"
    elif fault == "alias_conflict":
        record["status"] = "candidate"
    elif fault == "missing_status":
        record.pop("publication_status")
    elif fault == "null_status":
        record["status"] = None
    elif fault == "missing_date":
        record.pop("published_at")
    elif fault == "null_date":
        record["published_at"] = None
    elif fault == "naive_date":
        record["published_at"] = "2026-01-01T00:00:00"
    elif fault == "future_date":
        record["published_at"] = "2099-01-01T00:00:00Z"
    elif fault == "wrong_parts":
        record["part_hashes"]["execution"] = "f" * 64
    elif fault == "wrong_identity":
        record["template_id"] = "different-external-template"
    elif fault == "internal_row_identity":
        record["template_id"] = template["id"]
    elif fault == "wrong_version":
        record["version"] += 1
    elif fault == "string_version":
        record["version"] = str(record["version"])
    elif fault == "missing_identity":
        record.pop("template_id")
    else:
        record["template_sha256"] = "f" * 64
    with connection(owned) as c:
        scope(c, owned)
        with pytest.raises(HTTPException, match="422"):
            offline.stage(c, owned[1], owned[2], template["id"], offline.Upload(record_utf8=canonical(record).decode()))


@pytest.mark.parametrize("status_fields", [{"status": "published"}, {"publication_status": "published"},
                                           {"status": "published", "publication_status": "published"}])
def test_known_published_aliases_preserve_original_record_and_external_identity(owned, status_fields):
    template, record, subject = staged(owned, status_fields)
    with connection(owned) as c:
        scope(c, owned)
        stored = c.execute("SELECT raw_record_utf8,body_canonical FROM anvil.praxis_offline_publication_subjects WHERE id=%s",
                           (subject["id"],)).fetchone()
        assert stored["raw_record_utf8"] == canonical(record).decode()
        assert record["template_id"] == template["template_id"] != template["id"]
        assert subject["publication_accepted"] is False


@pytest.mark.parametrize("fault", ["alias_conflict", "wrong_identity", "string_version"])
def test_direct_sql_cannot_bypass_original_record_identity_and_alias_guard(owned, fault):
    import hashlib

    template, record, subject = staged(owned)
    with connection(owned) as c:
        scope(c, owned)
        stored = c.execute("SELECT body_canonical FROM anvil.praxis_offline_publication_subjects WHERE id=%s",
                           (subject["id"],)).fetchone()
        body = load(stored["body_canonical"].encode())
        if fault == "alias_conflict":
            record["status"] = "candidate"
        elif fault == "wrong_identity":
            record["template_id"] = template["id"]
        else:
            record["version"] = str(record["version"])
        raw = canonical(record)
        body.update(record=record, raw_record_sha256=hashlib.sha256(raw).hexdigest())
        with pytest.raises(psycopg.errors.RaiseException, match="published exact offline record"):
            c.execute("INSERT INTO anvil.praxis_offline_publication_subjects(id,project_id,template_id,created_by,raw_record_utf8,body_canonical,content_sha256) "
                      "VALUES(%s,%s,%s,%s,%s,%s,%s)",
                      (uuid4(), owned[1], template["id"], owned[2], raw.decode(), canonical(body).decode(), digest(body)))


def test_actual_http_identity_csrf_idempotency_and_current_role_controls(owned, monkeypatch):
    from anvil.api import app
    from anvil.auth import hashed

    monkeypatch.setenv("ANVIL_PRAXIS_GENERIC_EXPORT_ENABLED", "true")
    template, record, subject = staged(owned)
    clients = []
    for person in owned[2:4]:
        token, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
        with connection(owned) as c:
            c.execute("INSERT INTO anvil.sessions(token_hash,user_id,csrf_hash) VALUES(%s,%s,%s)",
                      (hashed(token), person, hashed(csrf)))
        client = TestClient(app)
        client.cookies.set("anvil_session", token)
        client.headers.update({"Origin": "http://127.0.0.1:3202", "X-CSRF-Token": csrf})
        clients.append(client)
    path = f"/api/v1/projects/{owned[1]}/dataset-exports/generic/templates/{template['id']}/offline-publications"
    assert TestClient(app).get(path).status_code == 401
    uploaded = {"record_utf8": canonical(record).decode()}
    assert clients[0].post(path, json=uploaded,
        headers={"Idempotency-Key": str(uuid4()), "X-CSRF-Token": "wrong"}).status_code == 403
    key = str(uuid4())
    first = clients[0].post(path, json=uploaded, headers={"Idempotency-Key": key})
    assert first.status_code == 201, first.text
    assert first.json()["data"]["publication_accepted"] is False
    assert clients[0].post(path, json=uploaded, headers={"Idempotency-Key": key}).json()["data"] == first.json()["data"]
    body = decision(subject).model_dump(mode="json")
    approve = path + f"/{subject['id']}/attest"
    assert clients[0].post(approve, json=body, headers={"Idempotency-Key": str(uuid4())}).status_code == 409
    key = str(uuid4())
    attested = clients[1].post(approve, json=body, headers={"Idempotency-Key": key})
    assert attested.status_code == 201, attested.text
    assert attested.json()["data"]["publication_verified"] is False
    assert clients[1].post(approve, json=body, headers={"Idempotency-Key": key}).json()["data"] == attested.json()["data"]
    listing = clients[0].get(path).json()["data"]["subjects"]
    assert len(listing) == 1 and listing[0]["attestation"]["current"] is True
    with connection(owned) as c:
        c.execute("UPDATE anvil.memberships SET role='rl-engineer' WHERE project_id=%s AND user_id=%s", (owned[1], owned[3]))
    assert clients[1].post(approve, json=body, headers={"Idempotency-Key": str(uuid4())}).status_code == 403
    assert clients[0].get(path).json()["data"]["subjects"][0]["attestation"]["current"] is False
    revoked = clients[0].post(path + f"/{subject['id']}/revoke", json={"reason": "Withdraw manufactured HTTP test record."},
                               headers={"Idempotency-Key": str(uuid4())})
    assert revoked.status_code == 200 and revoked.json()["data"]["revoked"] is True
