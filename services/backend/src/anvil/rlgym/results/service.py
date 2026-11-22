"""Report revisions, PDF renders, RL engineer diagnoses and packages (SPEC 07.6; SCREENS 3.32, 3.36, 3.17).

Export PDF stores the exact view as a report revision (a new revision only when the view changed, for example after a
re-score), prints it with headless Chromium (scripts/render-report-pdf.mjs), and keeps the PDF write-once with its
hash. A diagnosis never changes a score, a task or an evaluator; it can send a Studio inbox item when the S7
criterion itself must change or the case is a kind the template does not have (a grader defect is fixed as a new RL
Gym configuration version instead). A package bundles completed runs' manifests, scores and report revisions with a
data card, write-once with its hash.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile

from psycopg.types.json import Jsonb

from anvil.config import ROOT
from anvil.rlgym.catalog import inbox
from anvil.rlgym.common import GymError, audit, emit, new_id, require, sha
from anvil.rlgym.results import pdf, report

REPORT_ROOT = ROOT / ".local/rlgym/reports"
PACKAGE_ROOT = ROOT / ".local/rlgym/packages"
RENDERER = "headless Chromium via @playwright/test 1.58.2 (scripts/render-report-pdf.mjs)"
WRITERS = ("admin", "rl_engineer")
FINDINGS = {
    "task_finding": ("unresolved", "task_correct", "task_defect"),
    "attributed_to": ("unresolved", "agent", "task", "rubric", "grader", "environment"),
    "evaluator_finding": ("unresolved", "evaluator_correct", "grader_defect", "criterion_defect"),
    "strength": ("unresolved", "strong", "moderate", "weak"),
}
EVIDENCE_ITEMS = ("K1", "K2", "K3", "K4")


def _writer(actor):
    actor.require_person()
    require(actor.profile in WRITERS, "FORBIDDEN", "Viewers cannot change results")


def _write_once(path, data):
    """Write-once and read-only. The name carries the content hash, so a retry after a failed transaction finds the
    identical file instead of overwriting anything."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != hashlib.sha256(data).hexdigest():
            raise GymError("CONFLICT", "A different file already exists under this name")
        return
    with open(path, "xb") as handle:
        handle.write(data)
    os.chmod(path, 0o444)


def _read_checked(root, ref, digest):
    path = (root / ref).resolve()
    if root.resolve() not in path.parents:
        raise GymError("VALIDATION_FAILED", "Reference outside its store")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise GymError("HASH_MISMATCH", "Stored file does not match its hash")
    return raw


# --- appendices (part of the printed view) ---------------------------------------------------------------------------


def appendices(d, view):
    c, ws, m = d.c, d.ws, d.manifest
    task_scores = {t["task_id"]: t["per_model"] for t in view["tasks"]["tasks"]}
    env = c.execute(
        "SELECT * FROM catalog.environment_versions WHERE id=%s", (m["environment"]["version_id"],)
    ).fetchone()
    selected = {}
    for e in d.cases:
        if e["system_id"] == d.models[0]["system_id"] and e["attempt"] == 1:
            key = f"{e['application_type']}|{e['completeness']}"
            selected[key] = selected.get(key, 0) + 1
            for tag in e["edge_cases"]:
                selected[f"edge:{tag}"] = selected.get(f"edge:{tag}", 0) + 1
    cells = c.execute(
        "SELECT cell_key, quota, available FROM suites.data_plan_cells WHERE suite_version_id=%s ORDER BY cell_key",
        (d.run["suite_version_id"],),
    ).fetchall()
    frameworks = sorted({ev["framework"] for ev in m["evaluators"]})
    models = []
    for x in m["models"]:
        v = c.execute(
            "SELECT kind, provider, model_id, limits, config_sha256 FROM systems.system_versions WHERE workspace_id=%s AND system_id=%s AND version=%s",
            (ws, x["system_id"], x["version"]),
        ).fetchone()
        models.append(
            {**x, **(v or {}), "limits": json.dumps((v or {}).get("limits") or {}, sort_keys=True)}
        )
    counts = {}
    for e in d.episodes:
        counts[e["state"]] = counts.get(e["state"], 0) + 1
    return {
        "tasks": [
            {
                "task_id": t["task_id"],
                "revision": t["revision"],
                "selector": " · ".join(
                    [
                        t["case_selector"]["application_type"],
                        t["case_selector"]["completeness"],
                        *(t["case_selector"].get("edge_cases") or []),
                    ]
                ),
                "package_sha256": t["package_sha256"],
                "per_model": {
                    s: v.get("mean") for s, v in (task_scores.get(t["task_id"]) or {}).items()
                },
            }
            for t in m["tasks"]
        ],
        "environment": {
            "version": m["environment"]["version_id"],
            "registry image digest": m["environment"]["registry_image_digest"],
            "local image": (m["environment"].get("local_image") or {}).get("id"),
            "seed family": m["environment"]["seed_family"],
            "seed sha256": m["environment"]["seed_sha256"],
            "runtime profile": env and env["runtime_profile"],
            "tools": env and env["tools"],
            "released": env and env["released_at"] and env["released_at"].isoformat(),
            "selection rule": m["environment"]["rule"],
            "frameworks": ", ".join(frameworks),
            "data plan": f"{m['data_plan']['sample_size']} cases · quotas {json.dumps(m['data_plan']['completeness_quotas'], sort_keys=True)} · seed {m['data_plan']['sampling_seed']} · {m['data_plan']['missing_policy']}",
        },
        "cells": [{**cl, "selected": selected.get(cl["cell_key"], 0)} for cl in cells],
        "rubric": [
            {
                "criterion_id": ev["criterion_id"],
                "capability": ev.get("skill_group"),
                "weight": ev["weight"],
                "is_gate": ev.get("is_gate"),
                "evaluator": f"{ev['configuration_id']} v{ev['version']}",
                "framework": ev["framework"],
                "evidence": (
                    c.execute(
                        "SELECT evidence_type FROM catalog.evaluator_configurations WHERE workspace_id=%s AND id=%s AND version=%s",
                        (ws, ev["configuration_id"], ev["version"]),
                    ).fetchone()
                    or {}
                ).get("evidence_type"),
            }
            for ev in d.pass_row["evaluator_versions"]
        ],
        "models": models,
        "prompts": m["trust_and_safety"]["prompts"],
        "provenance": {
            "manifest sha256": d.manifest_sha256,
            "suite sha256": m["suite"]["suite_sha256"],
            "case ids sha256": m["data_plan"]["case_ids_sha256"],
            "episodes": ", ".join(f"{k} {v}" for k, v in sorted(counts.items())),
            "scoring pass": f"{d.pass_row['pass']} ({d.pass_row['reason']})",
            "evaluator versions sha256": d.pass_row["evaluator_versions_sha256"],
            "how scores were reviewed": "Automated only; SME review is work package 2.9",
            "execution": m["note"],
            "limits": "Python evaluator framework only; Promptfoo not installed (local prompt generator and safety oracle); environment built locally from the Studio stub recipe.",
        },
    }


# --- report revisions and PDF ----------------------------------------------------------------------------------------


def _revision(c, ws, d, view, actor):
    digest = report.view_sha(view)
    row = c.execute(
        "SELECT * FROM results.reports WHERE run_id=%s AND view_sha256=%s", (d.run["id"], digest)
    ).fetchone()
    if row:
        return row, False
    n = c.execute(
        "SELECT coalesce(max(revision),0)+1 n FROM results.reports WHERE run_id=%s", (d.run["id"],)
    ).fetchone()["n"]
    row = c.execute(
        "INSERT INTO results.reports(run_id,workspace_id,revision,pass_id,view,view_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (d.run["id"], ws, n, d.pass_row["id"], Jsonb(view), digest, actor.id),
    ).fetchone()
    return row, True


def render_pdf(c, ws, actor, run_id):
    actor.require_person()
    d, view = report.build(c, ws, run_id)
    require(
        d.run["state"] == "completed",
        "CONFLICT",
        "Export PDF is available when the run is completed",
    )
    rev, _ = _revision(c, ws, d, view, actor)
    existing = c.execute(
        "SELECT * FROM results.report_renders WHERE run_id=%s AND revision=%s",
        (run_id, rev["revision"]),
    ).fetchone()
    if existing:
        return _render_view(existing, rev)
    html = pdf.render(
        view,
        {
            **appendices(d, view),
            "revision": f"rep-{run_id}-r{rev['revision']}",
            "view_sha256": rev["view_sha256"],
        },
    )
    node = shutil.which("node")
    require(node, "VALIDATION_FAILED", "Node.js is required to render the PDF")
    with tempfile.TemporaryDirectory(prefix="rlgym-report-") as tmp:
        src, out = os.path.join(tmp, "report.html"), os.path.join(tmp, "report.pdf")
        with open(src, "w", encoding="utf-8") as handle:
            handle.write(html)
        footer = f"{run_id} · rep-{run_id}-r{rev['revision']} · manifest {d.manifest_sha256}"
        try:
            proc = subprocess.run(
                [node, str(ROOT / "scripts/render-report-pdf.mjs"), src, out, footer],
                cwd=str(ROOT),
                capture_output=True,
                timeout=120,
                env={"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")},
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise GymError("VALIDATION_FAILED", "PDF rendering timed out") from None
        if proc.returncode != 0 or not os.path.exists(out):
            raise GymError(
                "VALIDATION_FAILED", "PDF rendering failed", {"stderr": proc.stderr.decode()[-500:]}
            )
        data = open(out, "rb").read()
    pages = len(re.findall(rb"/Type\s*/Page[^s]", data))
    rel = f"{ws}/{run_id}/report-{run_id}-r{rev['revision']}-{hashlib.sha256(data).hexdigest()[:12]}.pdf"
    target = REPORT_ROOT / rel
    _write_once(target, data)
    row = c.execute(
        """INSERT INTO results.report_renders(run_id,revision,workspace_id,pdf_ref,pdf_sha256,pages,bytes,renderer,created_by)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (
            run_id,
            rev["revision"],
            ws,
            rel,
            hashlib.sha256(data).hexdigest(),
            pages,
            len(data),
            RENDERER,
            actor.id,
        ),
    ).fetchone()
    audit(
        c,
        ws,
        actor,
        "report.rendered",
        f"{run_id}:r{rev['revision']}",
        details={"pages": pages, "pdf_sha256": row["pdf_sha256"]},
    )
    emit(
        c,
        ws,
        "report.rendered",
        f"{run_id}:r{rev['revision']}",
        {"run_id": run_id, "revision": rev["revision"], "pages": pages},
    )
    return _render_view(row, rev)


def _render_view(row, rev):
    return {
        "run_id": row["run_id"],
        "revision": row["revision"],
        "label": f"rep-{row['run_id']}-r{row['revision']}",
        "pages": row["pages"],
        "bytes": row["bytes"],
        "pdf_sha256": row["pdf_sha256"],
        "view_sha256": rev["view_sha256"],
        "renderer": row["renderer"],
        "created_at": row["created_at"],
        "file_name": f"report-{row['run_id']}-r{row['revision']}.pdf",
    }


def renders(c, run_id):
    return [
        _render_view(r, {"view_sha256": r["view_sha256"]})
        for r in c.execute(
            """SELECT rr.*, r.view_sha256 FROM results.report_renders rr JOIN results.reports r USING (run_id, revision)
               WHERE rr.run_id=%s ORDER BY rr.revision DESC""",
            (run_id,),
        ).fetchall()
    ]


def pdf_bytes(c, ws, actor, run_id, revision):
    row = c.execute(
        "SELECT * FROM results.report_renders WHERE workspace_id=%s AND run_id=%s AND revision=%s",
        (ws, run_id, int(revision)),
    ).fetchone()
    if not row:
        raise GymError("NOT_FOUND", "No PDF for this revision")
    data = _read_checked(REPORT_ROOT, row["pdf_ref"], row["pdf_sha256"])
    audit(c, ws, actor, "report.downloaded", f"{run_id}:r{revision}")
    return data, f"report-{run_id}-r{revision}.pdf"


# --- diagnoses ------------------------------------------------------------------------------------------------------


def _episode(c, ws, episode_id):
    row = c.execute(
        """SELECT e.*, r.project_id, r.state run_state, m.manifest FROM runs.episodes e JOIN runs.runs r ON r.id=e.run_id
           JOIN runs.run_manifests m ON m.run_id=e.run_id WHERE e.workspace_id=%s AND e.id=%s""",
        (ws, episode_id),
    ).fetchone()
    if not row:
        raise GymError("NOT_FOUND", "Episode not found")
    return row


def save_diagnosis(c, ws, actor, episode_id, body):
    _writer(actor)
    e = _episode(c, ws, episode_id)
    require(e["kind"] == "case", "VALIDATION_FAILED", "Diagnoses are for benchmark episodes")
    values = {}
    for field, allowed in FINDINGS.items():
        value = body.get(field, "unresolved")
        require(
            value in allowed,
            "VALIDATION_FAILED",
            f"{field} must be one of {', '.join(allowed)}",
            field=field,
        )
        values[field] = value
    items = body.get("evidence_items") or []
    require(
        isinstance(items, list) and set(items) <= set(EVIDENCE_ITEMS),
        "VALIDATION_FAILED",
        "Evidence items are K1-K4",
        field="evidence_items",
    )
    why = (body.get("why") or "").strip()
    require(len(why) <= 4000, "VALIDATION_FAILED", "Why is at most 4000 characters", field="why")
    if values["attributed_to"] != "unresolved" or values["evaluator_finding"] not in (
        "unresolved",
        "evaluator_correct",
    ):
        require(why, "VALIDATION_FAILED", "Say why the evidence supports the finding", field="why")
    row = c.execute(
        """INSERT INTO results.diagnoses(episode_id,workspace_id,task_finding,attributed_to,evaluator_finding,strength,evidence_items,why,saved_by)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (episode_id) DO UPDATE SET task_finding=EXCLUDED.task_finding, attributed_to=EXCLUDED.attributed_to,
             evaluator_finding=EXCLUDED.evaluator_finding, strength=EXCLUDED.strength, evidence_items=EXCLUDED.evidence_items,
             why=EXCLUDED.why, saved_by=EXCLUDED.saved_by, saved_at=now() RETURNING *""",
        (
            episode_id,
            ws,
            values["task_finding"],
            values["attributed_to"],
            values["evaluator_finding"],
            values["strength"],
            sorted(items),
            why,
            actor.id,
        ),
    ).fetchone()
    audit(c, ws, actor, "diagnosis.saved", episode_id, details=values)
    return row


def send_inbox(c, ws, actor, episode_id, body):
    """From a saved diagnosis: evaluator_defect (the S7 criterion must change) or new_case_kind."""
    _writer(actor)
    e = _episode(c, ws, episode_id)
    diag = c.execute(
        "SELECT * FROM results.diagnoses WHERE episode_id=%s", (episode_id,)
    ).fetchone()
    require(diag, "CONFLICT", "Save the diagnosis first")
    require(
        not diag["inbox_item_id"],
        "CONFLICT",
        "This diagnosis already sent an inbox item",
        item=diag["inbox_item_id"],
    )
    kind = body.get("kind")
    m = e["manifest"]
    evidence = {
        "run_id": e["run_id"],
        "episode_id": episode_id,
        "case_id": e["case_id"],
        "task": {"task_id": e["task_id"], "revision": e["task_revision"]},
        "diagnosis": {
            k: diag[k]
            for k in (
                "task_finding",
                "attributed_to",
                "evaluator_finding",
                "strength",
                "evidence_items",
                "why",
            )
        },
        "manifest_sha256": c.execute(
            "SELECT manifest_sha256 FROM runs.run_manifests WHERE run_id=%s", (e["run_id"],)
        ).fetchone()["manifest_sha256"],
    }
    base = {
        "template_id": m["template"]["id"],
        "version": m["template"]["version"],
        "project_id": e["project_id"],
        "evidence": evidence,
    }
    if kind == "evaluator_defect":
        require(
            diag["evaluator_finding"] == "criterion_defect",
            "VALIDATION_FAILED",
            "Only a criterion defect goes to Studio; a grader defect is a new RL Gym configuration version (Admin → Evaluators)",
        )
        criterion = body.get("criterion_id")
        ev = next((x for x in m["evaluators"] if x["criterion_id"] == criterion), None)
        require(
            ev,
            "VALIDATION_FAILED",
            "Choose the criterion whose definition must change",
            field="criterion_id",
        )
        open_item = c.execute(
            """SELECT id FROM catalog.inbox_items WHERE workspace_id=%s AND kind='evaluator_defect' AND evaluator_configuration=%s
               AND state NOT IN ('declined','closed','released')""",
            (ws, ev["configuration_id"]),
        ).fetchone()
        require(
            not open_item,
            "CONFLICT",
            "An item is already open for this criterion",
            item=open_item and open_item["id"],
        )
        item = inbox.create(
            c,
            ws,
            actor,
            {
                **base,
                "kind": "evaluator_defect",
                "criterion_text_must_change": True,
                "evaluator_configuration": ev["configuration_id"],
                "summary": body.get("summary")
                or f"Criterion {criterion} must change (from {episode_id})",
            },
        )
    elif kind == "new_case_kind":
        item = inbox.create(
            c,
            ws,
            actor,
            {
                **base,
                "kind": "new_case_kind",
                "summary": body.get("summary")
                or f"Case {e['case_id']} is a kind the template does not have",
            },
        )
    else:
        raise GymError(
            "VALIDATION_FAILED", "kind must be evaluator_defect or new_case_kind", {"field": "kind"}
        )
    c.execute(
        "UPDATE results.diagnoses SET inbox_item_id=%s WHERE episode_id=%s",
        (item["id"], episode_id),
    )
    return item


# --- packages -------------------------------------------------------------------------------------------------------


def create_package(c, ws, actor, body):
    _writer(actor)
    run_ids = sorted(set(body.get("run_ids") or []))
    require(run_ids, "VALIDATION_FAILED", "Choose at least one completed run", field="run_ids")
    runs = []
    for run_id in run_ids:
        d, view = report.build(c, ws, run_id)
        require(
            d.run["state"] == "completed",
            "VALIDATION_FAILED",
            f"{run_id} is {d.run['state']}; only completed runs are packaged",
        )
        rev, _ = _revision(c, ws, d, view, actor)
        render = c.execute(
            "SELECT pdf_sha256, pages FROM results.report_renders WHERE run_id=%s AND revision=%s",
            (run_id, rev["revision"]),
        ).fetchone()
        runs.append(
            {
                "run_id": run_id,
                "name": d.run["name"],
                "manifest_sha256": d.manifest_sha256,
                "manifest": d.manifest,
                "scoring_pass": {
                    "pass": d.pass_row["pass"],
                    "reason": d.pass_row["reason"],
                    "evaluator_versions_sha256": d.pass_row["evaluator_versions_sha256"],
                },
                "score_cards": view["overview"]["cards"],
                "report": {
                    "revision": rev["revision"],
                    "view_sha256": rev["view_sha256"],
                    "pdf": render,
                },
            }
        )
    contents = {
        "schema": "rlgym.package.v1",
        "runs": runs,
        "data_card": {
            "data": "Synthetic Golden KYC V8 cases (synthetic-kyc-cases@1.0.0); no personal data",
            "agents": "Controlled mock agents (predetermined behaviour profiles); synthetic results, not model performance",
            "scoring": "Automated scoring passes from sealed evidence; no SME review in this package",
            "limits": "Local build; Python evaluator framework only; Promptfoo not installed",
        },
    }
    raw = json.dumps(contents, sort_keys=True, separators=(",", ":"), default=str).encode()
    package_id = new_id("pkg-")
    rel = f"{ws}/{package_id}-{hashlib.sha256(raw).hexdigest()[:12]}.json"
    _write_once(PACKAGE_ROOT / rel, raw)
    digest = hashlib.sha256(raw).hexdigest()
    summary = {
        "run_ids": run_ids,
        "runs": [{k: r[k] for k in ("run_id", "manifest_sha256", "report")} for r in runs],
    }
    c.execute(
        "INSERT INTO results.packages(id,workspace_id,run_ids,contents,package_ref,package_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (package_id, ws, run_ids, Jsonb(summary), rel, digest, actor.id),
    )
    audit(
        c, ws, actor, "package.created", package_id, details={"run_ids": run_ids, "sha256": digest}
    )
    emit(
        c,
        ws,
        "package.created",
        package_id,
        {"id": package_id, "run_ids": run_ids, "sha256": digest},
    )
    return {
        "id": package_id,
        "run_ids": run_ids,
        "package_sha256": digest,
        "bytes": len(raw),
        "file_name": f"{package_id}.json",
    }


def package_bytes(c, ws, actor, package_id):
    row = c.execute(
        "SELECT * FROM results.packages WHERE workspace_id=%s AND id=%s", (ws, package_id)
    ).fetchone()
    if not row:
        raise GymError("NOT_FOUND", "Package not found")
    data = _read_checked(PACKAGE_ROOT, row["package_ref"], row["package_sha256"])
    audit(c, ws, actor, "package.downloaded", package_id)
    return data, f"{package_id}.json"


def list_packages(c, ws):
    return c.execute(
        "SELECT id, run_ids, package_sha256, created_by, created_at FROM results.packages WHERE workspace_id=%s ORDER BY created_at DESC",
        (ws,),
    ).fetchall()


def view_digest(view):
    return sha(view)
