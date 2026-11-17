"""One native planning package from one genuine resolved reusable campaign.

No trial, provider request, automatic publication or spending authority is created.
The actor ZIP excludes the original private authored reference and future data.
"""

import hashlib
import io
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from fastapi import HTTPException

from anvil import artifacts
from anvil.db import Jsonb, audit, one, uid
from anvil.marketing_paid_contract import BINDING, ENVIRONMENT, MAX_CALLS
from anvil.marketing_paid_session import task_context
from anvil.praxis_generic_contract import canonical, digest


def prepare(c, project, user, resolved_id, task_group_id, max_calls, *, execution_data=None):
    if type(max_calls) is not int or not 1 <= max_calls <= MAX_CALLS:
        raise HTTPException(422, "Select1–1000 bounded physical model turns for the full campaign")
    try:
        context = task_context(
            c, project, resolved_id, task_group_id, execution_data=execution_data
        )
    except (RuntimeError, ValueError):
        raise HTTPException(
            409, {"code": "AV_MARKETING_NATIVE_SOURCE_QUALIFICATION_REQUIRED", "owner": "anvil"}
        ) from None
    actor, native = context["actor"], context["native_binding"]
    public_source = {
        "schema_version": "anvil.marketing-native-public-source.v1",
        "task_id": native["task_id"],
        "praxis_revision_id": native["revision_id"],
        "actor": actor,
        "native_binding": native,
    }
    if len(canonical(public_source)) > 524288:
        raise HTTPException(409, {"code": "AV_MARKETING_PUBLIC_SOURCE_CAPACITY", "owner": "anvil"})
    fingerprint = digest(public_source)
    revision = native["revision_id"] + ":anvil-marketing-native:" + digest(native)
    source = one(
        c,
        "SELECT * FROM anvil.praxis_sources WHERE project_id=%s AND task_id=%s AND revision_id=%s",
        (project, native["task_id"], revision),
    )
    if source and source["source_sha256"] != fingerprint:
        raise HTTPException(409, "Immutable Marketing source changed; resolve a new native binding")
    if not source:
        source_artifact = artifacts.store(
            c, project, canonical(public_source), "actor", origin="adi_executed"
        )
        source = c.execute(
            "INSERT INTO anvil.praxis_sources(id,project_id,task_id,task_version,revision_id,source_sha256,source_artifact_id,actor_spec,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                uid(),
                project,
                native["task_id"],
                "native-" + digest(native)[:12],
                revision,
                fingerprint,
                source_artifact,
                Jsonb(actor),
                user,
            ),
        ).fetchone()
    admission = {
        "schema_version": "anvil.marketing-native-agent-admission.v1",
        "binding": BINDING,
        "runtime_sha256": native["runtime_sha256"],
        "broker_sha256": native["broker_sha256"],
        "public_source_sha256": fingerprint,
        "roles": [role["id"] for role in context["execution"]["workflow_graph"]["roles"]],
        "run_authority": "not_granted",
        "provider_credential_to_worker": False,
        "private_reference_to_actor": False,
    }
    files = {"actor.json": canonical(actor), "anvil-agent/admission.json": canonical(admission)}
    manifest = {
        "schema_version": "anvil.marketing-native-package.v1",
        "task_id": native["task_id"],
        "task_version": source["task_version"],
        "revision_id": revision,
        "praxis_revision_id": native["revision_id"],
        "source_sha256": fingerprint,
        "binding": BINDING,
        "environment": ENVIRONMENT,
        "compiler_version": native["runtime_sha256"],
        "harbor_version": "0.25.0",
        "openenv_version": "0.12.0",
        "stage_order": ["turn-" + str(index) for index in range(max_calls)],
        "native_binding": native,
        "execution_sha256": native["execution_sha256"],
        "workflow_graph_sha256": native["workflow_graph_sha256"],
        "files": {name: hashlib.sha256(value).hexdigest() for name, value in files.items()},
        "run_authority": "not_granted",
    }
    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        for name, raw in sorted((files | {"package-manifest.json": canonical(manifest)}).items()):
            entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            archive.writestr(entry, raw)
    raw = output.getvalue()
    fingerprint = hashlib.sha256(raw).hexdigest()
    package = one(
        c,
        "SELECT * FROM anvil.harbor_packages WHERE project_id=%s AND source_id=%s AND package_sha256=%s",
        (project, source["id"], fingerprint),
    )
    if not package:
        artifact = artifacts.store(
            c, project, raw, "actor", mime="application/zip", origin="adi_executed"
        )
        package = c.execute(
            "INSERT INTO anvil.harbor_packages(id,project_id,source_id,package_sha256,package_artifact_id,manifest,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (uid(), project, source["id"], fingerprint, artifact, Jsonb(manifest), user),
        ).fetchone()
        audit(
            c,
            project,
            user,
            "marketing.native_planning_package_created",
            package["id"],
            {
                "resolved_task_id": str(resolved_id),
                "package_sha256": fingerprint,
                "run_authority": "not_granted",
            },
        )
    return {
        "package_id": str(package["id"]),
        "package_sha256": package["package_sha256"],
        "source_id": str(source["id"]),
        "native_binding": native,
        "run_authority": "not_granted",
        "case_count": len(native["cases"]),
        "max_model_calls": max_calls,
    }


def assignments(package, *, case_ids=None):
    manifest = package["manifest"]
    native = manifest.get("native_binding") or {}
    if (
        manifest.get("binding") != BINDING
        or native.get("task_mode") != "reusable_campaign_workflow"
    ):
        raise ValueError("Exact reusable five-role Marketing package required")
    cases = native.get("cases") or []
    members = {case["id"] for case in cases}
    if (
        not cases
        or len(members) != len(cases)
        or case_ids is not None
        and (len(case_ids) != len(set(case_ids)) or set(case_ids) != members)
    ):
        raise ValueError(
            "The complete frozen campaign membership is required; no silent case reduction"
        )
    return [
        {
            "package_id": str(package["id"]),
            "task_id": native["task_id"],
            "case_id": case["id"],
            "snapshot_sha256": case["snapshot_sha256"],
            "locale": case["locale"],
        }
        for case in cases
    ]
