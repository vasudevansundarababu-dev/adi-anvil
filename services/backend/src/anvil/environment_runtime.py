"""Application-owned PostgreSQL state, real files and ordered evidence for six seeds.

No cloud provisioning, Docker access, credentials, provider dispatch or Task scoring.
The server is the trusted event producer; actor operations never accept event records.
"""

import base64
import hashlib
import struct
from decimal import Decimal
from importlib.metadata import version as package_version
from pathlib import Path
from time import perf_counter_ns

from fastapi import HTTPException

from anvil import environment_seeds as seeds
from anvil.db import Jsonb, digest, one, uid


def implementation_sha256():
    names = (
        "environment_seeds.py",
        "environment_runtime.py",
        "environment_validation.py",
        "environment_data.py",
        "environment_bindings.py",
    )
    root = Path(__file__).parent
    from anvil.config import ROOT

    return digest(
        {
            "sources": {
                name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names
            },
            "dependency_lock_sha256": hashlib.sha256(
                (ROOT / "services/backend/uv.lock").read_bytes()
            ).hexdigest(),
            "installed_versions": {
                name: package_version(name) for name in ("pillow", "psycopg", "pydantic")
            },
        }
    )


def current_runtime(version):
    if version["manifest"].get("implementation_sha256") != implementation_sha256():
        raise HTTPException(
            409, "Environment implementation changed; create and validate a new version"
        )


def readiness(c, version):
    receipts = c.execute(
        "SELECT kind,content,created_at FROM anvil.environment_receipts WHERE environment_id=%s AND kind IN('validation','registration') ORDER BY created_at DESC,id DESC",
        (version["id"],),
    ).fetchall()
    current = version["manifest"].get("implementation_sha256") == implementation_sha256()
    validated = any(
        r["kind"] == "validation"
        and r["content"].get("passed")
        and r["content"].get("environment_manifest_sha256") == version["manifest_sha256"]
        for r in receipts
    )
    registered = any(
        r["kind"] == "registration"
        and r["content"].get("environment_manifest_sha256") == version["manifest_sha256"]
        for r in receipts
    )
    return {
        "status": "implementation_changed"
        if not current
        else "registered_local"
        if registered
        else "validated_local"
        if validated
        else "draft",
        "implementation_current": current,
        "local_validation_passed": current and validated,
        "local_registered": current and registered,
        "cloud_ready": False,
        "model_benchmark": "not_run",
        "source_binding": "actual_published_sources_pending",
        "evidence_scope": "local_postgres_state_and_files; not native isolation",
    }


def get(c, table, identifier):
    if table not in ("environment_versions", "environment_packs", "environment_instances"):
        raise ValueError("Invalid environment table")
    row = one(c, f"SELECT * FROM anvil.{table} WHERE id=%s", (identifier,))
    if not row:
        raise HTTPException(404, "Environment object not found in this Project")
    return row


def pack_store(c, project, user, pack):
    validation = seeds.validate(pack)
    old = one(
        c, "SELECT * FROM anvil.environment_packs WHERE content_sha256=%s", (validation["sha256"],)
    )
    if old:
        return old
    return one(
        c,
        "INSERT INTO anvil.environment_packs(id,project_id,template_id,scenario_id,content,content_sha256,validation,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (
            uid(),
            project,
            pack["template"],
            pack["scenario"],
            Jsonb(pack),
            validation["sha256"],
            Jsonb(validation),
            user,
        ),
    )


def create_version(c, project, user, pack_id, name):
    pack = get(c, "environment_packs", pack_id)
    manifest = {
        "schema_version": "anvil.environment-version.v1",
        "template_id": pack["template_id"],
        "template_version": seeds.VERSION,
        "pack_id": str(pack_id),
        "pack_sha256": pack["content_sha256"],
        "scenario_id": pack["scenario_id"],
        "clock": pack["content"]["clock"],
        "runtime": "postgres-local-components-v1",
        "implementation_sha256": implementation_sha256(),
        "tools": seeds.CATALOG[pack["template_id"]]["tools"],
        "origin": pack["content"]["origin"],
        "cloud_provisioned": False,
        "native_isolation": False,
        "task_binding": "not_bound",
        "provider_calls": 0,
    }
    return one(
        c,
        "INSERT INTO anvil.environment_versions(id,project_id,pack_id,name,manifest,manifest_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (uid(), project, pack_id, name, Jsonb(manifest), digest(manifest), user),
    )


def records(c, instance, collection):
    return [
        r["content"]
        for r in c.execute(
            "SELECT content FROM anvil.environment_records WHERE instance_id=%s AND collection=%s ORDER BY record_id",
            (instance, collection),
        ).fetchall()
    ]


def put(c, instance, collection, record):
    c.execute(
        "INSERT INTO anvil.environment_records(project_id,instance_id,collection,record_id,content) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(instance_id,collection,record_id) DO UPDATE SET content=EXCLUDED.content",
        (instance["project_id"], instance["id"], collection, record["id"], Jsonb(record)),
    )


def put_file(c, instance, path, content, media):
    checksum = hashlib.sha256(content).hexdigest()
    c.execute(
        "INSERT INTO anvil.environment_files(project_id,instance_id,path,media_type,content,sha256) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(instance_id,path) DO UPDATE SET content=EXCLUDED.content,media_type=EXCLUDED.media_type,sha256=EXCLUDED.sha256",
        (instance["project_id"], instance["id"], path, media, content, checksum),
    )
    return {"path": path, "sha256": checksum, "size": len(content)}


def state(c, instance):
    row = get(c, "environment_instances", instance)
    version = get(c, "environment_versions", row["environment_id"])
    collections = seeds.CATALOG[version["manifest"]["template_id"]]["collections"]
    return {
        "records": {key: records(c, instance, key) for key in collections},
        "files": [
            {
                "path": r["path"],
                "sha256": r["sha256"],
                "size": r["size"],
                "media_type": r["media_type"],
            }
            for r in c.execute(
                "SELECT path,sha256,media_type,octet_length(content) AS size FROM anvil.environment_files WHERE instance_id=%s ORDER BY path",
                (instance,),
            ).fetchall()
        ],
    }


def load(c, instance, pack):
    for table in ("environment_records", "environment_files"):
        c.execute(f"DELETE FROM anvil.{table} WHERE instance_id=%s", (instance["id"],))
    for collection, items in pack["records"].items():
        for item in items:
            put(c, instance, collection, item)
    for artifact in pack["files"]:
        put_file(
            c,
            instance,
            artifact["path"],
            base64.b64decode(artifact["bytes_base64"]),
            artifact["media_type"],
        )


def receipt(c, project, user, environment, kind, content, instance=None):
    return one(
        c,
        "INSERT INTO anvil.environment_receipts(id,project_id,environment_id,instance_id,kind,content,content_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (uid(), project, environment, instance, kind, Jsonb(content), digest(content), user),
    )


def create_instance(c, project, user, environment):
    version = get(c, "environment_versions", environment)
    current_runtime(version)
    pack = get(c, "environment_packs", version["pack_id"])["content"]
    seeds.validate(pack)
    initial = {
        "records": {
            key: sorted(value, key=lambda r: r["id"]) for key, value in pack["records"].items()
        },
        "files": sorted(
            [{k: f[k] for k in ("path", "sha256", "size", "media_type")} for f in pack["files"]],
            key=lambda f: f["path"],
        ),
    }
    instance = one(
        c,
        "INSERT INTO anvil.environment_instances(id,project_id,environment_id,state,initial_sha256,created_by) VALUES(%s,%s,%s,'initializing',%s,%s) RETURNING *",
        (uid(), project, environment, digest(initial), user),
    )
    load(c, instance, pack)
    observed = digest(state(c, instance["id"]))
    if observed != instance["initial_sha256"]:
        raise HTTPException(409, "Materialized component read-back differs from pinned pack")
    c.execute(
        "UPDATE anvil.environment_instances SET state='active' WHERE id=%s", (instance["id"],)
    )
    return get(c, "environment_instances", instance["id"])


def lock(c, identifier):
    instance = one(
        c, "SELECT * FROM anvil.environment_instances WHERE id=%s FOR UPDATE", (identifier,)
    )
    if not instance:
        raise HTTPException(404, "Environment instance not found")
    if instance["state"] != "active":
        raise HTTPException(409, "Environment instance is not active")
    current_runtime(get(c, "environment_versions", instance["environment_id"]))
    return instance


def event(c, instance, user, operation, arguments, result):
    previous = one(
        c,
        "SELECT sequence,content_sha256 FROM anvil.environment_events WHERE instance_id=%s ORDER BY sequence DESC LIMIT 1",
        (instance["id"],),
    )
    content = {
        "instance_id": str(instance["id"]),
        "generation": instance["generation"],
        "sequence": previous["sequence"] + 1 if previous else 1,
        "operation": operation,
        "arguments": arguments,
        "result": result,
        "previous_sha256": previous["content_sha256"] if previous else None,
    }
    used = one(
        c,
        "SELECT coalesce(sum(octet_length(arguments::text)+octet_length(result::text)),0) AS bytes FROM anvil.environment_events WHERE instance_id=%s",
        (instance["id"],),
    )["bytes"]
    import json

    if (
        content["sequence"] > 200
        or used + len(json.dumps(arguments).encode()) + len(json.dumps(result).encode())
        > 8 * 1024 * 1024
    ):
        raise HTTPException(
            409, "Instance event budget exhausted; export/close and start a new instance"
        )
    c.execute(
        "INSERT INTO anvil.environment_events(id,project_id,instance_id,generation,sequence,operation,arguments,result,previous_sha256,content_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            uid(),
            instance["project_id"],
            instance["id"],
            instance["generation"],
            content["sequence"],
            operation,
            Jsonb(arguments),
            Jsonb(result),
            content["previous_sha256"],
            digest(content),
            user,
        ),
    )
    return content | {"sha256": digest(content)}


def reset(c, user, identifier, expected_generation):
    with c.transaction():
        return _reset(c, user, identifier, expected_generation)


def _reset(c, user, identifier, expected_generation):
    instance = lock(c, identifier)
    if instance["generation"] != expected_generation:
        raise HTTPException(409, "Stale instance generation")
    version = get(c, "environment_versions", instance["environment_id"])
    before = digest(state(c, identifier))
    load(c, instance, get(c, "environment_packs", version["pack_id"])["content"])
    after = digest(state(c, identifier))
    if after != instance["initial_sha256"]:
        raise HTTPException(409, "Reset did not restore the pinned logical baseline")
    c.execute(
        "UPDATE anvil.environment_instances SET generation=generation+1 WHERE id=%s", (identifier,)
    )
    instance["generation"] += 1
    content = event(
        c,
        instance,
        user,
        "reset",
        {"expected_generation": expected_generation},
        {"before_sha256": before, "after_sha256": after, "restored": True},
    )
    return receipt(c, instance["project_id"], user, version["id"], "reset", content, identifier)


def _fields(args, required=(), optional=()):
    if set(args) - set(required) - set(optional) or set(required) - set(args):
        raise ValueError("Unexpected or missing operation arguments")
    array_fields = {"source_ids", "audience_ids", "evidence_ids", "transaction_ids", "line_ids"}
    for key, value in args.items():
        if key in array_fields:
            if (
                not isinstance(value, list)
                or len(value) > 100
                or any(not isinstance(v, str) or not 1 <= len(v) <= 160 for v in value)
            ):
                raise ValueError("Bounded string identities required")
        elif not isinstance(value, str) or len(value) > 5000 or "\x00" in value:
            raise ValueError("Operation arguments must be bounded text")


def _decimal(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("Exact decimal must be a bounded string")
    amount = Decimal(value)
    if not amount.is_finite() or abs(amount) > Decimal("1000000000000"):
        raise ValueError("Invalid finite decimal")
    return amount


def _find(c, instance, collection, identifier):
    row = next((r for r in records(c, instance["id"], collection) if r["id"] == identifier), None)
    if not row:
        raise ValueError(f"Unknown {collection} record")
    return row


def approval_target(c, instance, template, target_id):
    target = _find(c, instance, "campaigns" if template == "MKT-PHONE" else "variants", target_id)
    artifact = one(
        c,
        "SELECT sha256 FROM anvil.environment_files WHERE instance_id=%s AND path=%s",
        (instance["id"], target.get("path", "")),
    )
    return target, digest(
        {"target": target, "artifact_sha256": artifact["sha256"] if artifact else None}
    )


def decide_approval(c, user, identifier, approval_id, decision, rationale):
    with c.transaction():
        return _decide_approval(c, user, identifier, approval_id, decision, rationale)


def _decide_approval(c, user, identifier, approval_id, decision, rationale):
    instance = lock(c, identifier)
    template = get(c, "environment_versions", instance["environment_id"])["manifest"]["template_id"]
    if template not in ("MKT-PHONE", "MKT-LOCALE"):
        raise HTTPException(409, "This environment has no campaign approval operation")
    row = _find(c, instance, "approvals", str(approval_id))
    if row["status"] != "pending":
        raise HTTPException(409, "Existing decision is immutable; request a new review")
    _, fingerprint = approval_target(c, instance, template, row["target_id"])
    if row["target_sha256"] != fingerprint:
        raise HTTPException(
            409, "Target changed after the request; request review of the new bytes"
        )
    put(
        c,
        instance,
        "approvals",
        row | {"status": decision, "decision_actor": str(user), "rationale": rationale},
    )
    return event(
        c,
        instance,
        user,
        "operator_approval_decision",
        {
            "approval_id": str(approval_id),
            "target_sha256": fingerprint,
            "decision": decision,
            "rationale": rationale,
        },
        {"status": "recorded_local_simulation", "real_source_review": False},
    )


def _operation(c, instance, manifest, operation, a):
    template = manifest["template_id"]
    if operation == "list_records":
        _fields(a, ("collection",))
        if a["collection"] not in seeds.CATALOG[template]["collections"]:
            raise ValueError("Collection is not exposed by this template")
        return {"records": records(c, instance["id"], a["collection"])}
    if operation == "read_file":
        _fields(a, ("path",))
        row = one(
            c,
            "SELECT path,media_type,sha256,content FROM anvil.environment_files WHERE instance_id=%s AND path=%s",
            (instance["id"], a["path"]),
        )
        if not row:
            raise ValueError("File not present in this instance")
        return {k: row[k] for k in ("path", "media_type", "sha256")} | {
            "bytes_base64": base64.b64encode(row["content"]).decode()
        }
    if operation == "query_statements":
        _fields(a, ("company_id", "period_id"), ("line_item",))
        result = c.execute(
            "SELECT content FROM anvil.environment_records WHERE instance_id=%s AND collection='financial_statement_lines' AND content->>'company_id'=%s AND content->>'period_id'=%s AND (%s::text IS NULL OR content->>'line_item'=%s) ORDER BY record_id LIMIT 100",
            (
                instance["id"],
                a["company_id"],
                a["period_id"],
                a.get("line_item"),
                a.get("line_item"),
            ),
        ).fetchall()
        return {
            "query": "statement_lines_by_company_period",
            "parameters": a,
            "rows": [r["content"] for r in result],
        }
    if operation == "calculate_financial":
        _fields(a, ("line_ids", "operator"))
        if not 1 <= len(a["line_ids"]) <= 20 or len(set(a["line_ids"])) != len(a["line_ids"]):
            raise ValueError("Select one through twenty unique statement lines")
        lines = [_find(c, instance, "financial_statement_lines", i) for i in a["line_ids"]]
        if any(line["value"] is None for line in lines):
            raise ValueError("Required statement value is null; calculation is unresolved")
        if len({(line["currency"], line["unit_scale"], line["basis"]) for line in lines}) != 1:
            raise ValueError(
                "Units, currency or consolidation basis differ; no implicit conversion"
            )
        values = [_decimal(line["value"]) for line in lines]
        if a["operator"] == "sum":
            result = sum(values, Decimal(0))
        elif a["operator"] == "subtract" and len(values) == 2:
            result = values[0] - values[1]
        elif a["operator"] == "ratio" and len(values) == 2 and values[1] != 0:
            result = values[0] / values[1]
        else:
            raise ValueError("Supported operations: sum, two-line subtract, nonzero two-line ratio")
        row = {
            "id": uid(),
            "operation": a["operator"],
            "source_ids": a["line_ids"],
            "inputs": [line["value"] for line in lines],
            "value": str(result),
            "currency": lines[0]["currency"],
            "unit_scale": lines[0]["unit_scale"],
            "rounding": "Python Decimal context precision 28; no float conversion",
        }
        put(c, instance, "saved_analysis", row)
        return row
    if operation == "save_analysis":
        _fields(a, ("text", "source_ids"))
        if (
            not isinstance(a["source_ids"], list)
            or len(a["source_ids"]) > 50
            or any(not isinstance(s, str) for s in a["source_ids"])
        ):
            raise ValueError("Bounded source IDs required")
        known = {r["id"] for r in records(c, instance["id"], "financial_statement_lines")}
        if not set(a["source_ids"]) <= known:
            raise ValueError("Analysis cites an unknown statement line")
        identifier = uid()
        output = put_file(
            c, instance, f"outputs/{identifier}.txt", a["text"].encode(), "text/plain"
        )
        put(
            c,
            instance,
            "saved_analysis",
            {"id": identifier, "sources": a["source_ids"], "output": output},
        )
        return output
    if operation == "create_campaign":
        _fields(a, ("objective", "copy", "audience_ids"))
        if (
            not isinstance(a["audience_ids"], list)
            or not a["audience_ids"]
            or not set(a["audience_ids"])
            <= {r["id"] for r in records(c, instance["id"], "audiences")}
        ):
            raise ValueError("Known campaign audiences required")
        row = {"id": uid(), "product_id": "phone", "status": "draft", **a}
        put(c, instance, "campaigns", row)
        return row
    if operation == "allocate_budget":
        _fields(a, ("campaign_id", "amount", "currency"))
        _find(c, instance, "campaigns", a["campaign_id"])
        amount = _decimal(a["amount"])
        product = records(c, instance["id"], "products")[0]
        total = sum(
            (_decimal(r["amount"]) for r in records(c, instance["id"], "allocations")), Decimal(0)
        )
        if (
            amount < 0
            or a["currency"] != product["currency"]
            or total + amount > _decimal(product["budget"])
        ):
            raise ValueError("Allocation exceeds the configured product budget/currency")
        row = {"id": uid(), **a}
        put(c, instance, "allocations", row)
        return row
    if operation == "request_approval":
        _fields(a, ("target_id",))
        _, target_sha256 = approval_target(c, instance, template, a["target_id"])
        row = {
            "id": uid(),
            "target_id": a["target_id"],
            "status": "pending",
            "decision_actor": None,
            "target_sha256": target_sha256,
        }
        put(c, instance, "approvals", row)
        return row
    if operation in ("schedule_placement", "submit_variant"):
        _fields(a, ("target_id",), ("channel",))
        target, fingerprint = approval_target(c, instance, template, a["target_id"])
        if not any(
            r["target_id"] == a["target_id"]
            and r["status"] == "approved"
            and r.get("target_sha256") == fingerprint
            for r in records(c, instance["id"], "approvals")
        ):
            raise ValueError("No actual authorized approval for this target")
        if template == "MKT-PHONE":
            product = records(c, instance["id"], "products")[0]
            allocations = records(c, instance["id"], "allocations")
            if any(r["currency"] != product["currency"] for r in allocations) or sum(
                (_decimal(r["amount"]) for r in allocations), Decimal(0)
            ) > _decimal(product["budget"]):
                raise ValueError("Configured aggregate budget/currency would be exceeded")
            channel = _find(c, instance, "channels", a.get("channel"))
            if not channel["available"]:
                raise ValueError("Channel service unavailable")
        row = {
            "id": uid(),
            "target_id": target["id"],
            "status": "scheduled" if template == "MKT-PHONE" else "submitted",
            "mode": "local_stub",
            **a,
        }
        put(c, instance, "placements" if template == "MKT-PHONE" else "submissions", row)
        return row
    if operation == "render_variant":
        _fields(a, ("channel", "locale", "caption", "disclosure"))
        spec = _find(c, instance, "channel_specs", a["channel"])
        _find(c, instance, "locale_requirements", a["locale"])
        identifier = a["channel"] + "-" + a["locale"]
        path = f"assets/{identifier}.png"
        output = put_file(
            c,
            instance,
            path,
            seeds.png(spec["width"], spec["height"], a["caption"], a["disclosure"]),
            "image/png",
        )
        put(
            c,
            instance,
            "variants",
            {"id": identifier, "bundle_id": "bundle", "source_version": "1", "path": path, **a},
        )
        return output | {
            "caption_storage": "rendered_png_and_structured_metadata",
            "visual_text_rendering": "reference_ascii_renderer",
            "translation_evaluation": "not_evaluated",
        }
    if operation == "inspect_asset":
        _fields(a, ("path",))
        row = one(
            c,
            "SELECT content,sha256 FROM anvil.environment_files WHERE instance_id=%s AND path=%s",
            (instance["id"], a["path"]),
        )
        if not row or not bytes(row["content"]).startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("No PNG artifact at selected path")
        width, height = struct.unpack(">II", bytes(row["content"])[16:24])
        return {
            "width": width,
            "height": height,
            "format": "image/png",
            "sha256": row["sha256"],
            "semantic_quality": "not_evaluated",
        }
    if operation == "screen_case":
        _fields(a, ("case_id",))
        _find(c, instance, "cases", a["case_id"])
        fixture = next(
            (
                r
                for r in records(c, instance["id"], "checks")
                if r["id"] == "screening-fixture" and r["case_id"] == a["case_id"]
            ),
            None,
        )
        row = {
            "id": uid(),
            "case_id": a["case_id"],
            "status": fixture["status"] if fixture else "unavailable",
            "origin": "synthetic_stub",
            "fixture_version": "1",
        }
        put(c, instance, "checks", row)
        return row
    if operation == "request_information":
        _fields(a, ("case_id", "reason"))
        _find(c, instance, "cases", a["case_id"])
        row = {"id": uid(), "status": "pending", **a}
        put(c, instance, "requests", row)
        return row
    if operation == "record_decision":
        _fields(a, ("case_id", "decision", "rationale", "evidence_ids"))
        case = _find(c, instance, "cases", a["case_id"])
        if a["decision"] not in ("needs_review", "escalated", "approved", "rejected"):
            raise ValueError("Invalid case decision")
        docs = {r["id"] for r in records(c, instance["id"], "documents")}
        if (
            not isinstance(a["evidence_ids"], list)
            or any(not isinstance(i, str) for i in a["evidence_ids"])
            or not set(a["evidence_ids"]) <= docs
        ):
            raise ValueError("Decision evidence must resolve to this instance")
        row = {"id": uid(), **a}
        put(c, instance, "decisions", row)
        put(c, instance, "cases", case | {"status": a["decision"]})
        return row | {"policy_compliance": "requires_frozen_task_binding"}
    if operation == "ownership_paths":
        _fields(a, ("entity_id",))
        _find(c, instance, "entities", a["entity_id"])
        edges = records(c, instance["id"], "ownership_edges")
        people = {r["id"] for r in records(c, instance["id"], "persons")}
        paths, problems = [], []

        def visit(entity, product, chain, trail, supported=True):
            if len(trail) > 30 or len(paths) + len(problems) > 100:
                raise ValueError("Ownership graph traversal exceeds bounds")
            if entity in trail:
                problems.append({"kind": "cycle", "entity": entity, "edges": chain})
                return
            for edge in edges:
                if edge["owned"] != entity:
                    continue
                value = product * _decimal(edge["share"]) / 100
                next_chain = chain + [edge["id"]]
                path_supported = supported and bool(edge["document_id"])
                if not edge["document_id"]:
                    problems.append({"kind": "missing_evidence", "edge": edge["id"]})
                if edge["owner"] in people:
                    paths.append(
                        {
                            "person": edge["owner"],
                            "percent": str(value),
                            "edges": next_chain,
                            "source_supported": path_supported,
                        }
                    )
                else:
                    visit(edge["owner"], value, next_chain, trail + [entity], path_supported)

        visit(a["entity_id"], Decimal(100), [], [])
        totals = {
            p: str(
                sum(
                    (
                        Decimal(x["percent"])
                        for x in paths
                        if x["person"] == p and x["source_supported"]
                    ),
                    Decimal(0),
                )
            )
            for p in sorted(people)
        }
        if any(p["kind"] == "cycle" for p in problems):
            totals = None
        result = {
            "id": uid(),
            "paths": paths,
            "totals": totals,
            "problems": problems,
            "beneficial_owner_classification": "not_evaluated_without_task_rules",
        }
        put(c, instance, "calculations", result)
        return result
    if operation == "query_transactions":
        _fields(a, ("account_id", "start", "end"))
        from datetime import datetime

        start, end = datetime.fromisoformat(a["start"]), datetime.fromisoformat(a["end"])
        if not start.tzinfo or not end.tzinfo or start > end:
            raise ValueError("Ordered timezone-aware query window required")
        _find(c, instance, "accounts", a["account_id"])
        rows = [
            r
            for r in records(c, instance["id"], "transactions")
            if r["account_id"] == a["account_id"]
            and start <= datetime.fromisoformat(r["timestamp"]) <= end
        ]
        return {
            "query": "transactions_by_account_window",
            "parameters": a,
            "rows": rows,
            "total": str(sum((_decimal(r["amount"]) for r in rows), Decimal(0))),
        }
    if operation == "record_step":
        _fields(a, ("case_id", "note", "transaction_ids"))
        _find(c, instance, "cases", a["case_id"])
        known = {r["id"] for r in records(c, instance["id"], "transactions")}
        if not isinstance(a["transaction_ids"], list) or not set(a["transaction_ids"]) <= known:
            raise ValueError("Unknown transaction evidence")
        row = {"id": uid(), **a}
        put(c, instance, "investigation_steps", row)
        return row
    if operation == "link_case":
        _fields(a, ("case_id", "related_case_id"))
        for key in a.values():
            _find(c, instance, "cases", key)
        if a["case_id"] == a["related_case_id"]:
            raise ValueError("Cannot link a case to itself")
        row = {"id": uid(), **a}
        put(c, instance, "case_links", row)
        return row
    if operation == "record_disposition":
        _fields(a, ("case_id", "disposition", "rationale"))
        case = _find(c, instance, "cases", a["case_id"])
        if a["disposition"] not in ("open", "closed", "escalated"):
            raise ValueError("Invalid disposition")
        row = {"id": uid(), **a}
        put(c, instance, "dispositions", row)
        if a["disposition"] == "escalated":
            put(
                c,
                instance,
                "escalations",
                {
                    "id": uid(),
                    "case_id": a["case_id"],
                    "disposition_id": row["id"],
                    "status": "local_pending",
                },
            )
        put(c, instance, "cases", case | {"status": a["disposition"]})
        return row | {"policy_compliance": "requires_frozen_task_binding"}
    raise ValueError("Operation is not implemented for this template")


def execute(c, user, identifier, operation, arguments, expected_generation):
    with c.transaction():
        return _execute(c, user, identifier, operation, arguments, expected_generation)


def _execute(c, user, identifier, operation, arguments, expected_generation):
    started = perf_counter_ns()
    instance = lock(c, identifier)
    if instance["generation"] != expected_generation:
        raise HTTPException(409, "Stale instance generation; re-read before a new operation")
    manifest = get(c, "environment_versions", instance["environment_id"])["manifest"]
    if operation not in manifest["tools"]:
        raise HTTPException(422, "Operation unavailable for this template")
    # Savepoint prevents partial writes on a rejected operation while retaining the event.
    try:
        with c.transaction():
            result = {
                "status": "ok",
                "value": _operation(c, instance, manifest, operation, arguments),
            }
            import json

            observed_state = state(c, identifier)
            if (
                len(json.dumps(observed_state).encode()) > 4 * 1024 * 1024
                or sum(f["size"] for f in observed_state["files"]) > 4 * 1024 * 1024
                or len(json.dumps(result).encode()) > 1024 * 1024
            ):
                raise ValueError("Component state or tool result exceeds its bounded runtime limit")
    except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
        result = {"status": "rejected", "reason": str(exc)[:300]}
    result["duration_ns"] = str(perf_counter_ns() - started)
    return event(c, instance, user, operation, arguments, result)


def export_evidence(c, user, identifier):
    instance = lock(c, identifier)
    version = get(c, "environment_versions", instance["environment_id"])
    events = c.execute(
        "SELECT generation,sequence,operation,arguments,result,previous_sha256,content_sha256 FROM anvil.environment_events WHERE instance_id=%s ORDER BY sequence",
        (identifier,),
    ).fetchall()
    envelope = {
        "schema_version": "anvil.environment-evidence.v1",
        "producer": "anvil_trusted_service",
        "instance_id": str(identifier),
        "environment_id": str(version["id"]),
        "environment_manifest_sha256": version["manifest_sha256"],
        "pack_sha256": version["manifest"]["pack_sha256"],
        "clock": version["manifest"]["clock"],
        "generation": instance["generation"],
        "state": state(c, identifier),
        "artifacts": [
            {
                "path": f["path"],
                "media_type": f["media_type"],
                "sha256": f["sha256"],
                "bytes_base64": base64.b64encode(f["content"]).decode(),
            }
            for f in c.execute(
                "SELECT path,media_type,sha256,content FROM anvil.environment_files WHERE instance_id=%s ORDER BY path",
                (identifier,),
            ).fetchall()
        ],
        "events": events,
        "provider_calls": 0,
        "model_performance": False,
        "native_isolation": False,
        "task_evaluation": "not_bound",
    }
    return receipt(c, instance["project_id"], user, version["id"], "evidence", envelope, identifier)


def close(c, user, identifier):
    instance = lock(c, identifier)
    evidence = export_evidence(c, user, identifier)
    c.execute("UPDATE anvil.environment_instances SET state='closed' WHERE id=%s", (identifier,))
    return receipt(
        c,
        instance["project_id"],
        user,
        instance["environment_id"],
        "cleanup",
        {
            "status": "closed_retained",
            "evidence_receipt": str(evidence["id"]),
            "cloud_resources": [],
            "data_deleted": False,
        },
        identifier,
    )
