"""Append-only exact-version template/qualification registry; no human publication API."""

from fastapi import HTTPException

from anvil.db import Jsonb, audit, uid
from anvil.praxis_capabilities import catalogue, requirements
from anvil.praxis_generic_contract import TemplateSpec, digest


def source_hash():
    from anvil.praxis_template_source import source_hash as pure_source_hash

    return pure_source_hash()


def register(c, project, user, raw):
    spec = TemplateSpec.model_validate(raw)
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    candidates = c.execute(
        "SELECT * FROM anvil.praxis_template_versions WHERE project_id=%s AND template_key=%s AND version=%s ORDER BY created_at,id",
        (project, spec.template_id, spec.version),
    ).fetchall()
    fingerprint = digest(raw)
    for old in candidates:
        if old["spec_sha256"] == fingerprint:
            return public(old)
        if any(old["part_hashes"][part] != digest(raw[part]) for part in ("execution", "skills")):
            raise HTTPException(
                409, "Anvil execution/skills changed; propose a new template version"
            )
        if c.execute(
            "SELECT 1 FROM anvil.praxis_template_publications WHERE project_id=%s AND template_id=%s",
            (project, old["id"]),
        ).fetchone():
            raise HTTPException(409, "Published template version is immutable; use a new version")
    identifier = uid()
    row = c.execute(
        "INSERT INTO anvil.praxis_template_versions(id,project_id,template_key,version,spec,spec_sha256,part_hashes,catalogue_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (
            identifier,
            project,
            spec.template_id,
            spec.version,
            Jsonb(raw),
            fingerprint,
            Jsonb({p: digest(raw[p]) for p in ("authoring", "execution", "skills")}),
            catalogue(spec.execution.catalogue_version)["sha256"],
            user,
        ),
    ).fetchone()
    audit(c, project, user, "praxis_template.registered", identifier, {"spec_sha256": fingerprint})
    return public(row)


def public(row):
    return {
        "id": str(row["id"]),
        "template_id": row["template_key"],
        "anvil_template_key": row["spec"]["anvil_template_key"],
        "version": row["version"],
        "spec_sha256": row["spec_sha256"],
        "part_hashes": row["part_hashes"],
        "catalogue_sha256": row["catalogue_sha256"],
    }


def publication(c, project, user, template_id, body, *, origin):
    """Only the trusted server caller records authenticated Praxis API responses.

    No HTTP route accepts an author's claim of publication as an approval.
    MockTransport evidence is permanently labelled offline_fixture.
    """
    row = c.execute(
        "SELECT * FROM anvil.praxis_template_versions WHERE project_id=%s AND id=%s",
        (project, template_id),
    ).fetchone()
    if (
        not row
        or body.get("status") != "published"
        or body.get("template_sha256") != row["spec_sha256"]
        or body.get("part_hashes") != row["part_hashes"]
    ):
        raise ValueError("Exact published template/part hashes required")
    safe = {
        k: body[k]
        for k in (
            "status",
            "template_sha256",
            "part_hashes",
            "authorable_receipt_sha256",
            "praxis_template_version_id",
        )
        if k in body
    }
    c.execute(
        "INSERT INTO anvil.praxis_template_publications(id,project_id,template_id,publication,publication_sha256,origin,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (uid(), project, template_id, Jsonb(safe), digest(safe), origin, user),
    )


def qualify(c, project, user, template_id):
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    row = c.execute(
        "SELECT * FROM anvil.praxis_template_versions WHERE project_id=%s AND id=%s",
        (project, template_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Template not found")
    spec = TemplateSpec.model_validate(row["spec"])
    missing = requirements(spec)
    publication_row = c.execute(
        "SELECT * FROM anvil.praxis_template_publications WHERE project_id=%s AND template_id=%s ORDER BY created_at DESC,id DESC LIMIT 1",
        (project, template_id),
    ).fetchone()
    publication_verified = bool(
        publication_row
        and publication_row["origin"] == "praxis_authenticated_api"
        and digest(publication_row["publication"]) == publication_row["publication_sha256"]
    )
    from anvil.praxis_offline_publication import basis as offline_basis

    accepted_basis = None if publication_verified else offline_basis(c, project, template_id)
    publication_accepted = publication_verified or accepted_basis is not None
    from anvil.praxis_generic_environment import conformance

    try:
        if spec.execution.environment.id == "golden-kyc-openenv-v2":
            from anvil.praxis_golden_kyc import conformance as golden_conformance

            probe = golden_conformance(c, project, spec)
        elif spec.execution.schema_version == "anvil.template-execution.v3":
            # A parsed five-role graph is not an executable campaign. Its exact
            # runtime/SQL/Harbor/evaluator component control is still required.
            probe = {
                "passed": False,
                "origin": "marketing_native_qualification_pending",
                "model_performance": False,
                "paid_calls": False,
            }
        else:
            probe = conformance(spec.execution)
    except ValueError:
        probe = {"passed": False, "origin": "adapter_not_supported"}
    if not probe["passed"]:
        missing.append("AV_ENVIRONMENT_PROVISIONING_REQUIRED")
        missing.extend(probe.get("requirements", []))
    if not publication_accepted:
        missing.append("REVIEW_PRAXIS_PUBLICATION")
    receipt = {
        "schema_version": "anvil.template-qualification.v1",
        "project_id": str(project),
        "environment": environment(),
        "anvil_template_key": spec.anvil_template_key,
        "template_id": spec.template_id,
        "version": spec.version,
        "template_sha256": row["spec_sha256"],
        "part_hashes": row["part_hashes"],
        "catalogue_sha256": catalogue(spec.execution.catalogue_version)["sha256"],
        "source_sha256": source_hash(),
        "status": "blocked" if missing else "qualified",
        "requirements": sorted(set(missing)),
        "conformance": probe,
        "publication_verified": publication_verified,
        "qualification_scope": "golden_installed_runtime_and_frozen_evaluators"
        if spec.execution.environment.id == "golden-kyc-openenv-v2"
        else "structured_software_adapter_only",
        "paid_calls": False,
        "run_authority": "not_granted",
    }
    if accepted_basis is not None:
        receipt["publication_accepted"] = True
        receipt["publication_basis"] = accepted_basis
    identifier = uid()
    receipt["receipt_id"] = identifier
    c.execute(
        "INSERT INTO anvil.praxis_template_qualifications(id,project_id,template_id,receipt,receipt_sha256,status,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (
            identifier,
            project,
            template_id,
            Jsonb(receipt),
            digest(receipt),
            receipt["status"],
            user,
        ),
    )
    from anvil.praxis_template_delivery import enqueue

    if accepted_basis is None:
        enqueue(c, project, user, "qualification", receipt, str(identifier))
    # Offline attestation is local provenance, never an API-authenticated event.
    return {"id": identifier, "receipt": receipt, "receipt_sha256": digest(receipt)}


def lookup(c, project, reference):
    row = c.execute(
        "SELECT * FROM anvil.praxis_template_versions WHERE project_id=%s AND template_key=%s AND version=%s AND spec_sha256=%s",
        (project, reference.id, reference.version, reference.sha256),
    ).fetchone()
    if not row:
        return None
    integrity = bool(
        digest(row["spec"]) == row["spec_sha256"]
        and {p: digest(row["spec"][p]) for p in ("authoring", "execution", "skills")}
        == row["part_hashes"]
        and row["spec"].get("template_id") == row["template_key"]
        and row["spec"].get("version") == row["version"]
    )
    qualification = c.execute(
        "SELECT * FROM anvil.praxis_template_qualifications WHERE project_id=%s AND template_id=%s ORDER BY created_at DESC,id DESC LIMIT 1",
        (project, row["id"]),
    ).fetchone()
    revoked = bool(
        qualification
        and c.execute(
            "SELECT 1 FROM anvil.praxis_template_revocations WHERE project_id=%s AND qualification_id=%s",
            (project, qualification["id"]),
        ).fetchone()
    )
    current_source = source_hash() if qualification else None
    valid = bool(
        qualification
        and digest(row["spec"]) == row["spec_sha256"]
        and {p: digest(row["spec"][p]) for p in ("authoring", "execution", "skills")}
        == row["part_hashes"]
        and row["catalogue_sha256"]
        == catalogue(row["spec"]["execution"]["catalogue_version"])["sha256"]
        and qualification["status"] == "qualified"
        and digest(qualification["receipt"]) == qualification["receipt_sha256"]
        and qualification["receipt"]["source_sha256"] == current_source
        and qualification["receipt"].get("template_sha256") == row["spec_sha256"]
        and qualification["receipt"].get("part_hashes") == row["part_hashes"]
        and qualification["receipt"].get("catalogue_sha256")
        == catalogue(row["spec"]["execution"]["catalogue_version"])["sha256"]
        and c.execute("SELECT anvil.template_publication_current(%s,%s,%s) AS current",
                      (project, row["id"], Jsonb(qualification["receipt"]))).fetchone()["current"]
        and qualification["receipt"].get("conformance", {}).get("passed") is True
        and not revoked
    )
    if row["spec"]["execution"]["environment"]["id"] == "golden-kyc-openenv-v2" and valid:
        from anvil.golden_component_qualification import installed
        from anvil.golden_kyc_anvil import source_hash as golden_source_hash
        from anvil.golden_kyc_v7_export import product_template

        current_installation = installed()
        recorded = qualification["receipt"]["conformance"]
        valid = (
            current_installation["ready"]
            and qualification["receipt"]["conformance"].get("golden_source_sha256")
            == golden_source_hash()
            and recorded.get("installed_review_sha256")
            == current_installation.get("evidence", {}).get("review_receipt_sha256")
            and recorded.get("installed_image_sha256")
            == current_installation.get("evidence", {}).get("runtime_image_sha256")
            and recorded.get("installed_broker_sha256")
            == current_installation.get("evidence", {}).get("broker_source_sha256")
            and (not product_template(row["spec"]) or recorded.get("export_selector_field") == "product")
        )
    reasons = []
    if not qualification:
        reasons.append("qualification_missing")
    else:
        if qualification["status"] != "qualified":
            reasons.append("qualification_status_blocked")
        if qualification["receipt"].get("source_sha256") != current_source:
            reasons.append("template_source_changed")
        if revoked:
            reasons.append("qualification_revoked")
    if not valid and not reasons:
        reasons.append("qualification_not_current")
    return {
        "row": row,
        "integrity": integrity,
        "qualified": valid and integrity,
        "qualification": qualification,
        "revoked": revoked,
        "qualification_diagnostics": {
            "status": "current" if valid and integrity else "blocked",
            "reason_codes": reasons,
            "recorded_status": qualification["status"] if qualification else None,
            "receipt_sha256": qualification["receipt_sha256"] if qualification else None,
        },
    }


def revoke(c, project, user, qualification_id, reason):
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (project,))
    row = c.execute(
        "SELECT * FROM anvil.praxis_template_qualifications WHERE project_id=%s AND id=%s",
        (project, qualification_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Qualification not found")
    qualification = row
    old = c.execute(
        "SELECT id,event_sequence,reason FROM anvil.praxis_template_revocations WHERE project_id=%s AND qualification_id=%s",
        (project, qualification_id),
    ).fetchone()
    if old:
        return old
    sequence = c.execute(
        "SELECT COALESCE(max(event_sequence),0)+1 AS n FROM anvil.praxis_template_revocations WHERE project_id=%s",
        (project,),
    ).fetchone()["n"]
    row = c.execute(
        "INSERT INTO anvil.praxis_template_revocations(id,project_id,qualification_id,event_sequence,reason,created_by) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id,event_sequence,reason",
        (uid(), project, qualification_id, sequence, reason, user),
    ).fetchone()
    audit(
        c,
        project,
        user,
        "praxis_template.revoked",
        str(qualification_id),
        {"event_sequence": sequence},
    )
    from anvil.praxis_template_delivery import enqueue

    if qualification["receipt"].get("publication_basis", {}).get("kind") == "po_attested_offline":
        return row
    enqueue(
        c,
        project,
        user,
        "revocation",
        {
            "schema_version": "anvil.template-revocation.v1",
            "event_id": str(row["id"]),
            "environment": environment(),
            "project_id": str(project),
            "anvil_template_key": qualification["receipt"]["anvil_template_key"],
            "template_id": qualification["receipt"]["template_id"],
            "version": qualification["receipt"]["version"],
            "template_sha256": qualification["receipt"]["template_sha256"],
            "receipt_id": str(qualification["id"]),
            "receipt_hash": qualification["receipt_sha256"],
            "status": "revoked",
            "reason": reason,
            "sequence": sequence,
        },
        str(row["id"]),
    )
    return row


def environment():
    from anvil.pilot_environment import current

    return current() or "local"
