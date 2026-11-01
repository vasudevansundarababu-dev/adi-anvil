import hashlib
import json

from fastapi import HTTPException

from anvil import artifacts, domain
from anvil.config import ROOT, setting
from anvil.db import audit, digest, one

HASHES = {
    "rubric-template.json": "9fb506c3b2323d72c98c0564440bbef19e7cd9d840a2d669b3c0a63569384072",
    "FIN-001/case.json": "8cb5498832553b42ce54db8cab7d8bfacb87e40336f8c0fc717a807601b7bfa6",
    "MKT-001/case.json": "0d1f5fe3c30b8e63fcfda6f3acfd799d931f1ccb76c4489b0a7f129a5e524a67",
    "STR-001/case.json": "46bf06d8370508d0b6e40247860d1ebbe3b4889c0c0212ee7c22a04d3b64dcd8",
    "FIN-001/private/reference.json": "71899c960223a08a66f1167b245c769f5536dacf2af826581564190dafcd5371",
    "FIN-001/actor/exhibits.json": "5cce90a898dabd82bdda7fb626b79afc0f95ce6db506e92cb86212f76eb3b921",
    "FIN-001/actor/task.md": "e7bf4d86041edf57e66412216eb3257132399ebd7904dbd472ca03e21ca4add9",
    "MKT-001/private/reference.json": "082228ea4cbe8cbcd81cc894048ad029c16eb176175d22d50b35ca8aa29e714e",
    "MKT-001/actor/exhibits.json": "95b7ae6a191ef10d17a5e171bbc06f7517e73302b46e788473ca48ab94685749",
    "MKT-001/actor/task.md": "a3643a8c001cc624d31263e2115767e47d296fa55b671f77176fce219528ddc0",
    "STR-001/private/reference.json": "3f04e8c903541fbebb220c9d65bf637b60a633b8e405d6725a430d013df60dba",
    "STR-001/actor/exhibits.json": "e24e1a0905d745174770d629f457427baffe849b161693f38a01943baee002cd",
    "STR-001/actor/task.md": "0a5d4fd641b7bd3657a7d42a3472e205e90461c74f0943633e177dc611302798",
}


def trusted(path):
    if path not in HASHES or setting("ANVIL_FIXTURE_MODE") != "true":
        raise HTTPException(403, "Fixture path not registered")
    p = ROOT / "fixtures/cases" / path
    if p.is_symlink() or not p.exists():
        raise HTTPException(409, "Required fixture file missing")
    data = p.read_bytes()
    if hashlib.sha256(data).hexdigest() != HASHES[path]:
        raise HTTPException(
            409, "Fixture version digest mismatch; original will not be overwritten"
        )
    return data


def load(c, project, user, body, rubric_override=None):
    # D-SIMPLE: named reviewer/advisor are optional; the Admin approves the tasks.
    named = [str(x) for x in (body.reviewer_id, body.advisor_id) if x]
    if body.reviewer_id:
        domain.assigned(c, project, body.reviewer_id, "reviewer")
    if body.advisor_id:
        domain.assigned(c, project, body.advisor_id, "advisor")
    if len(set(named + [str(user)])) != len(named) + 1:
        raise HTTPException(409, "Named reviewers must be distinct from the importer")
    # Validate all bytes before any business writes; database transaction is all-or-nothing.
    bundles = {}
    for case in body.case_ids:
        if case == "MKT-LH-001":
            continue
        bundles[case] = {
            name: trusted(f"{case}/{name}")
            for name in [
                "case.json",
                "actor/task.md",
                "actor/exhibits.json",
                "private/reference.json",
            ]
        }
    template = json.loads(trusted("rubric-template.json"))
    results = []
    if "MKT-LH-001" in body.case_ids:
        from anvil.marketing_pack import load

        results.append(load(c, project, user, body))
    for case, bundle in bundles.items():
        manifest = json.loads(bundle["case.json"])
        content_hash = digest({k: hashlib.sha256(v).hexdigest() for k, v in bundle.items()})
        old = one(
            c,
            "SELECT * FROM anvil.import_receipts WHERE project_id=%s AND fixture_id=%s AND version=%s",
            (project, case, "1"),
        )
        if old:
            if old["content_hash"] != content_hash:
                raise HTTPException(409, "Existing version has different bytes")
            source = domain.get_resource(c, old["resource_id"])
            # Backfill lineage for the original local importer using independently checked bytes.
            hashes = [hashlib.sha256(value).hexdigest() for value in bundle.values()]
            c.execute(
                "INSERT INTO anvil.artifact_links(project_id,revision_id,artifact_id,use_role) SELECT project_id,%s,id,'original' FROM anvil.artifacts WHERE sha256=ANY(%s) AND origin='original_synthetic_fixture' AND scan_status='clean' ON CONFLICT DO NOTHING",
                (source["current_revision_id"], hashes),
            )
            if rubric_override is None:
                results.append(source)
                continue

            # An evaluation plan gets its own rubric and task over the already imported source,
            # bound to the same verified artifacts in manifest order.
            def linked(names, classification):
                ids = []
                for name in names:
                    row = one(
                        c,
                        """SELECT a.id FROM anvil.artifacts a JOIN anvil.artifact_links l
                           ON l.artifact_id=a.id WHERE l.revision_id=%s AND a.sha256=%s
                           AND a.classification=%s AND a.scan_status='clean' LIMIT 1""",
                        (
                            source["current_revision_id"],
                            hashlib.sha256(bundle[name]).hexdigest(),
                            classification,
                        ),
                    )
                    if not row:
                        raise HTTPException(409, "Imported fixture artifact missing")
                    ids.append(str(row["id"]))
                return ids

            results.append(
                rubric_and_task(
                    c,
                    project,
                    user,
                    body,
                    case,
                    manifest,
                    source,
                    linked(manifest["actor_files"], "actor"),
                    linked(manifest["private_files"], "hidden_reference"),
                    json.loads(bundle["private/reference.json"]),
                    template,
                    rubric_override,
                )
            )
            continue
        source = domain.create(c, project, user, "case", manifest)
        actor_ids = [
            artifacts.store(
                c,
                project,
                bundle[name],
                "actor",
                "text/plain" if name.endswith(".md") else "application/json",
                "original_synthetic_fixture",
            )
            for name in manifest["actor_files"]
        ]
        reference_ids = [
            artifacts.store(
                c, project, bundle[name], "hidden_reference", origin="original_synthetic_fixture"
            )
            for name in manifest["private_files"]
        ]
        for aid in actor_ids + reference_ids:
            c.execute(
                "INSERT INTO anvil.artifact_links VALUES(%s,%s,%s,'original')",
                (project, source["current_revision_id"], aid),
            )
        reference = json.loads(bundle["private/reference.json"])
        task = rubric_and_task(
            c,
            project,
            user,
            body,
            case,
            manifest,
            source,
            actor_ids,
            reference_ids,
            reference,
            template,
            rubric_override,
        )
        c.execute(
            "INSERT INTO anvil.import_receipts VALUES(%s,%s,%s,%s,%s)",
            (project, case, "1", content_hash, source["id"]),
        )
        audit(c, project, user, "synthetic_fixture.imported", source["id"])
        results.append(task if rubric_override is not None else source)
    return results


def rubric_and_task(
    c,
    project,
    user,
    body,
    case,
    manifest,
    source,
    actor_ids,
    reference_ids,
    reference,
    template,
    override,
):
    """Create the case rubric and task. An evaluation plan passes its own rubric definition."""
    people = {
        k: str(v)
        for k, v in (("reviewer_id", body.reviewer_id), ("advisor_id", body.advisor_id))
        if v
    }
    override = override or {}
    rubric_content = {
        "title": override.get("title") or f"{case} anchored synthetic rubric",
        "criteria": override.get("criteria") or template["criteria"],
        "threshold": override.get("threshold", template["threshold"]),
        "critical_rules": [reference["critical_rule"], *override.get("critical_rules", [])],
        "calibration": {
            "clear_pass": "Fixture correct response: independent scripted 4/4/4 example.",
            "clear_fail": "Fixture constraint-blind response: scripted 4/0/4.",
            "valid_alternative": reference["acceptable_alternatives"],
            "critical_error": reference["critical_rule"],
            "ambiguous_reference": "If required evidence is ambiguous, invalidate and request correction; do not assign candidate failure.",
        },
        **people,
        "origin": "original_synthetic_fixture",
    }
    rubric = domain.create(
        c,
        project,
        user,
        "rubric",
        domain.validate_content(c, project, "rubric", rubric_content),
    )
    task_content = {
        "title": manifest["title"],
        "external_case_id": case,
        "source_revision_id": str(source["current_revision_id"]),
        "rubric_revision_id": str(rubric["current_revision_id"]),
        "actor_artifact_ids": actor_ids,
        "reference_artifact_ids": reference_ids,
        "family_id": manifest["family_id"],
        "capabilities": manifest["capabilities"],
        "mode": manifest["mode"],
        "split": manifest["split"],
        **people,
        "origin": "original_synthetic_fixture",
    }
    task = domain.create(
        c, project, user, "task", domain.validate_content(c, project, "task", task_content)
    )
    for aid in actor_ids + reference_ids:
        c.execute(
            "INSERT INTO anvil.artifact_links VALUES(%s,%s,%s,%s)",
            (
                project,
                task["current_revision_id"],
                aid,
                "actor" if aid in actor_ids else "reference",
            ),
        )
    return task
