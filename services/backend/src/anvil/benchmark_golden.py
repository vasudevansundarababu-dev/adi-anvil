"""Human-authored private golden drafts and bounded, non-executing remediation intents."""

from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field, StrictBool, model_validator

from anvil import benchmark_execution as execution
from anvil import benchmark_pipeline as pipeline
from anvil.benchmark_storage import read_private_record
from anvil.db import Jsonb, audit, digest, one, uid
from anvil.schemas import Strict


class Dataset(Strict):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)


class Anchor(Strict):
    run_id: UUID
    cell_id: UUID


class CaseVersion(Strict):
    case_key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
    title: str = Field(min_length=1, max_length=160)
    category: Literal["safety", "factuality", "tone", "latency", "task_correctness"]
    input_text: str = Field(min_length=1, max_length=16384)
    expected_output: str = Field(min_length=1, max_length=16384)
    fictional_task_id: Literal["FX-001", "FX-002", "FX-003"]
    source_build_id: UUID | None = None
    source_anchor: Anchor | None = None
    source_trace_id: UUID | None = None
    predecessor_id: UUID | None = None

    @model_validator(mode="after")
    def one_anchor(self):
        if self.source_trace_id is not None and (
            self.source_anchor is not None or self.source_build_id is not None
        ):
            raise ValueError("Historical trace and current source bindings must be separate")
        return self


class Verification(Strict):
    assignment_id: UUID
    evidence_artifact_id: UUID
    evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision: Literal["verified", "rejected"]
    human_reviewed: StrictBool
    rationale: str = Field(min_length=10, max_length=2000)


class Proposal(Strict):
    title: str = Field(min_length=1, max_length=160)
    persona: Literal[
        "prompt_injection", "customer_urgency", "contradictory_instructions", "repetitive_loop"
    ]
    rationale: str = Field(min_length=10, max_length=2000)
    proposed_prompt: str = Field(default="", max_length=8192)
    fictional_task_id: Literal["FX-001", "FX-002", "FX-003"]
    source_build_id: UUID | None = None
    source_anchor: Anchor | None = None
    source_trace_id: UUID | None = None
    offline_only: Literal[True] = True

    @model_validator(mode="after")
    def one_anchor(self):
        if self.source_trace_id is not None and (
            self.source_anchor is not None or self.source_build_id is not None
        ):
            raise ValueError("Historical trace and current source bindings must be separate")
        return self


class RunIntent(Strict):
    expected_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    offline_only: Literal[True] = True
    max_steps: int = Field(default=10, strict=True, ge=1, le=20)
    max_output_bytes: int = Field(default=8192, strict=True, ge=64, le=65536)


def dataset(c, identifier):
    row = one(c, "SELECT * FROM anvil.benchmark_golden_datasets WHERE id=%s", (identifier,))
    if row is None:
        raise HTTPException(404, "Golden dataset not found")
    archived = one(
        c, "SELECT 1 FROM anvil.benchmark_golden_dataset_events WHERE dataset_id=%s", (identifier,)
    )
    return row | {"archived": bool(archived)}


def create_dataset(c, project, user, body):
    identifier = uid()
    c.execute(
        "INSERT INTO anvil.benchmark_golden_datasets(id,project_id,name,description,created_by) VALUES(%s,%s,%s,%s,%s)",
        (identifier, project, body.name, body.description, user),
    )
    audit(
        c,
        project,
        user,
        "benchmark.golden_dataset_created",
        identifier,
        {"origin": "original_synthetic_fixture"},
    )
    return dataset(c, identifier)


def archive(c, project, user, identifier, rationale):
    row = dataset(c, identifier)
    if row["archived"]:
        raise HTTPException(409, "Golden dataset is already archived")
    c.execute(
        "INSERT INTO anvil.benchmark_golden_dataset_events(id,project_id,dataset_id,action,actor_id,rationale) VALUES(%s,%s,%s,'archived',%s,%s)",
        (uid(), project, identifier, user, rationale),
    )
    audit(c, project, user, "benchmark.golden_dataset_archived", identifier)
    return dataset(c, identifier)


def resolve_source(c, build_id, anchor, task_id):
    """Resolve actual cell ownership; caller never supplies derived source versions."""
    if anchor is not None:
        execution.export_rights(c, anchor.run_id)
        row = one(
            c,
            "SELECT run.benchmark_revision_id,cell.task_revision_id,a.id attempt_id,output.sha256 output_sha256,report.sha256 report_sha256 FROM anvil.benchmark_cells cell JOIN anvil.benchmark_comparisons run ON run.project_id=cell.project_id AND run.run_id=cell.run_id JOIN anvil.benchmark_cell_attempts a ON a.project_id=cell.project_id AND a.cell_id=cell.id AND a.attempt_no=1 JOIN anvil.benchmark_offline_runtime rt ON rt.project_id=a.project_id AND rt.attempt_id=a.id JOIN anvil.artifacts output ON output.project_id=rt.project_id AND output.id=rt.output_artifact_id JOIN anvil.artifacts report ON report.project_id=rt.project_id AND report.id=rt.report_artifact_id WHERE cell.run_id=%s AND cell.id=%s",
            (anchor.run_id, anchor.cell_id),
        )
        if row is None:
            raise HTTPException(
                404, "Captured source trace not found or private access unavailable"
            )
        bound = execution.version(c, row["benchmark_revision_id"])
        if bound["task_labels"].get(str(row["task_revision_id"])) != task_id:
            raise HTTPException(409, "Selected task does not match the actual trace")
        if build_id is not None and str(build_id) != str(bound["build_id"]):
            raise HTTPException(409, "Source trace belongs to another source build")
        build_id = bound["build_id"]
        canonical = {
            "run_id": str(anchor.run_id),
            "cell_id": str(anchor.cell_id),
            "attempt_id": str(row["attempt_id"]),
            "task_revision_id": str(row["task_revision_id"]),
            "output_sha256": row["output_sha256"],
            "report_sha256": row["report_sha256"],
        }
    else:
        canonical = None
    if build_id is not None:
        pipeline.record(c, "benchmark_builds", build_id)
        if not one(
            c,
            "SELECT 1 FROM anvil.benchmark_build_tasks WHERE build_id=%s AND task_id=%s",
            (build_id, task_id),
        ):
            raise HTTPException(409, "Fictional task is not bound to this exact source build")
    return build_id, canonical


def historical_binding(c, trace_id, task_id):
    if trace_id is None:
        return None
    from anvil import benchmark_dashboard, benchmark_dashboard_traces

    resolved = benchmark_dashboard.resolve_anchor(c, trace_id)
    if resolved["kind"] != "historical_control" or resolved["current_authority"] is not False:
        raise HTTPException(409, "Historical references cannot establish current source authority")
    row = benchmark_dashboard_traces.metadata(c, trace_id)
    if row["metadata"].get("task_id") != task_id:
        raise HTTPException(409, "Selected task does not match the actual historical trace")
    return {
        "trace_id": str(trace_id),
        "task_id": task_id,
        "artifact_id": str(row["artifact_id"]),
        "source_record_sha256": row["source_record_sha256"],
        "source_commit": row["source_commit"],
        "current_authority": False,
    }


def content_body(body, build_id, anchor, historical):
    value = body.model_dump(mode="json")
    value.pop("predecessor_id", None)
    value["source_build_id"] = str(build_id) if build_id is not None else None
    value["source_anchor"] = anchor
    value["historical_source_binding"] = historical
    value["origin"] = "original_synthetic_fixture"
    return value


def version(c, identifier):
    row = one(c, "SELECT * FROM anvil.benchmark_golden_versions WHERE id=%s", (identifier,))
    if row is None:
        raise HTTPException(404, "Golden version not found or current access unavailable")
    if digest(row["content"]) != row["content_sha256"]:
        raise HTTPException(409, "Golden content binding changed")
    decision = one(
        c,
        "SELECT id,decision,verifier_id,created_at,evidence_sha256 FROM anvil.benchmark_golden_verifications WHERE version_id=%s",
        (identifier,),
    )
    return row | {
        "status": decision["decision"] if decision else "draft",
        "verification": decision,
        "origin": "original_synthetic_fixture",
        "is_task_scoring_authority": False,
    }


def create_version(c, project, user, identifier, body):
    if dataset(c, identifier)["archived"]:
        raise HTTPException(409, "Golden dataset is archived")
    build_id, anchor = resolve_source(
        c, body.source_build_id, body.source_anchor, body.fictional_task_id
    )
    previous = one(
        c,
        "SELECT * FROM anvil.golden_latest_version(%s,%s,%s)",
        (project, identifier, body.case_key),
    )
    if (str(previous["id"]) if previous else None) != (
        str(body.predecessor_id) if body.predecessor_id else None
    ):
        raise HTTPException(409, "Exact latest case predecessor is required")
    if previous:
        version(c, previous["id"])
    content = content_body(
        body, build_id, anchor, historical_binding(c, body.source_trace_id, body.fictional_task_id)
    )
    key = uid()
    c.execute(
        "INSERT INTO anvil.benchmark_golden_versions(id,project_id,dataset_id,case_key,revision,predecessor_id,source_build_id,content,content_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            key,
            project,
            identifier,
            body.case_key,
            previous["revision"] + 1 if previous else 1,
            body.predecessor_id,
            build_id,
            Jsonb(content),
            digest(content),
            user,
        ),
    )
    audit(
        c,
        project,
        user,
        "benchmark.golden_case_drafted",
        key,
        {"content_sha256": digest(content), "never_auto_verified": True},
    )
    return version(c, key)


def verify(c, project, user, identifier, body):
    row = version(c, identifier)
    if row["created_by"] == user:
        raise HTTPException(403, "A distinct assigned human must verify this case")
    if not body.human_reviewed:
        raise HTTPException(422, "Explicit human review is required")
    if row["source_build_id"] is None or row["content"].get("source_trace_id") is not None:
        raise HTTPException(409, "A current exact source binding is required before verification")
    if row["verification"] is not None or row["content_sha256"] != body.expected_content_sha256:
        raise HTTPException(409, "Verification requires the exact undecided immutable version")
    duty = one(
        c,
        "SELECT id FROM anvil.benchmark_private_assignments a WHERE id=%s AND user_id=%s AND scope='evaluation_review' AND artifact_id IS NULL AND expires_at>now() AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_private_revocations r WHERE r.assignment_id=a.id)",
        (body.assignment_id, user),
    )
    if duty is None:
        raise HTTPException(403, "A current individual evaluation review duty is required")
    evidence = pipeline.private_metadata(c, body.evidence_artifact_id)
    if (
        evidence["classification"] not in {"benchmark_eval", "benchmark_trace"}
        or evidence["sha256"] != body.evidence_sha256
        or evidence["byte_size"] > 262144
    ):
        raise HTTPException(409, "Exact bounded private verification evidence is required")
    read_private_record(evidence)
    key = uid()
    c.execute(
        "INSERT INTO anvil.benchmark_golden_verifications(id,project_id,version_id,assignment_id,evidence_artifact_id,evidence_sha256,expected_content_sha256,verifier_id,decision,rationale,human_reviewed) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true)",
        (
            key,
            project,
            identifier,
            body.assignment_id,
            body.evidence_artifact_id,
            body.evidence_sha256,
            body.expected_content_sha256,
            user,
            body.decision,
            body.rationale,
        ),
    )
    audit(
        c,
        project,
        user,
        "benchmark.golden_case_human_reviewed",
        identifier,
        {"decision": body.decision, "content_sha256": row["content_sha256"]},
    )
    return version(c, identifier)


def proposal(c, identifier):
    row = one(c, "SELECT * FROM anvil.benchmark_remediation_proposals WHERE id=%s", (identifier,))
    if row is None:
        raise HTTPException(404, "Remediation proposal not found")
    if digest(row["content"]) != row["content_sha256"]:
        raise HTTPException(409, "Remediation proposal binding changed")
    intents = c.execute(
        "SELECT * FROM anvil.benchmark_remediation_intents WHERE proposal_id=%s ORDER BY created_at DESC,id DESC LIMIT 101",
        (identifier,),
    ).fetchall()
    return row | {
        "state": "proposed",
        "auto_applied": False,
        "provider_calls": 0,
        "run_intents": list(reversed(intents[:100])),
        "run_intents_has_more": len(intents) > 100,
        "run_intents_limit": 100,
    }


def create_proposal(c, project, user, body):
    build_id, anchor = resolve_source(
        c, body.source_build_id, body.source_anchor, body.fictional_task_id
    )
    content = content_body(
        body, build_id, anchor, historical_binding(c, body.source_trace_id, body.fictional_task_id)
    )
    key = uid()
    c.execute(
        "INSERT INTO anvil.benchmark_remediation_proposals(id,project_id,source_build_id,content,content_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s)",
        (key, project, build_id, Jsonb(content), digest(content), user),
    )
    audit(
        c,
        project,
        user,
        "benchmark.remediation_proposed",
        key,
        {"offline_only": True, "auto_applied": False},
    )
    return proposal(c, key)


def run_intent(c, project, user, identifier, body):
    row = proposal(c, identifier)
    if row["content_sha256"] != body.expected_content_sha256:
        raise HTTPException(409, "Exact remediation proposal required")
    key = uid()
    c.execute(
        "INSERT INTO anvil.benchmark_remediation_intents(id,project_id,proposal_id,created_by,state,code,provider_calls,auto_applied,limits) VALUES(%s,%s,%s,%s,'blocked','compatible_offline_executor_unavailable',0,false,%s)",
        (
            key,
            project,
            identifier,
            user,
            Jsonb({"max_steps": body.max_steps, "max_output_bytes": body.max_output_bytes}),
        ),
    )
    audit(
        c,
        project,
        user,
        "benchmark.remediation_run_blocked",
        key,
        {
            "code": "compatible_offline_executor_unavailable",
            "max_steps": body.max_steps,
            "max_output_bytes": body.max_output_bytes,
            "provider_calls": 0,
        },
    )
    return proposal(c, identifier)


def dashboard_summary(c, project, user, context):
    """Redacted current visible heads only; never fetch expected answers or prompts."""
    from anvil import benchmark_dashboard

    rows = c.execute(
        "SELECT v.id,v.dataset_id,v.case_key,v.revision,v.content_sha256,v.source_build_id,v.created_at,v.content-'input_text'-'expected_output' context_content FROM anvil.benchmark_golden_versions v JOIN LATERAL anvil.golden_latest_version(%s,v.dataset_id,v.case_key) head ON head.id=v.id WHERE NOT EXISTS(SELECT 1 FROM anvil.benchmark_golden_dataset_events e WHERE e.dataset_id=v.dataset_id) ORDER BY v.id LIMIT 501",
        (project,),
    ).fetchall()
    proposals = c.execute(
        "SELECT id,source_build_id,created_at,content-'proposed_prompt'-'rationale'-'title' context_content FROM anvil.benchmark_remediation_proposals ORDER BY id LIMIT 501"
    ).fetchall()
    if len(rows) > 500 or len(proposals) > 500:
        raise HTTPException(409, "Curation summary exceeds500 visible records; narrow the cohort")
    policy_cache = {}

    def current(build_id):
        if build_id is None:
            return False
        key = str(build_id)
        if key not in policy_cache:
            try:
                _, blocked = pipeline.policy_status(project, user, build_id)
                policy_cache[key] = not blocked
            except (HTTPException, ValueError, OSError, RuntimeError):
                policy_cache[key] = False
        return policy_cache[key]

    cases = []
    datasets = set()
    for row in rows:
        content = row["context_content"]
        if not benchmark_dashboard.matches_case_context(
            c, content, context, created_at=row["created_at"]
        ):
            continue
        decision = one(
            c,
            "SELECT g.decision,EXISTS(SELECT 1 FROM anvil.benchmark_private_assignments a JOIN anvil.memberships m ON m.project_id=a.project_id AND m.user_id=a.user_id AND m.active AND m.role IN ('admin','rl-engineer') JOIN anvil.users u ON u.id=m.user_id AND u.active WHERE a.id=g.assignment_id AND a.user_id=g.verifier_id AND a.scope='evaluation_review' AND a.artifact_id IS NULL AND a.expires_at>now() AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_private_revocations r WHERE r.assignment_id=a.id)) duty_current FROM anvil.benchmark_golden_verifications g WHERE g.version_id=%s",
            (row["id"],),
        )
        state = decision["decision"] if decision else "draft"
        if state == "verified" and (
            not decision["duty_current"]
            or not current(row["source_build_id"])
            or content.get("source_trace_id")
        ):
            state = "blocked"
        cases.append(
            {
                "id": str(row["id"]),
                "case_key": row["case_key"],
                "revision": row["revision"],
                "content_sha256": row["content_sha256"],
                "status": state,
            }
        )
        datasets.add(str(row["dataset_id"]))
    refs = []
    blocked_intents = 0
    for row in proposals:
        if not benchmark_dashboard.matches_case_context(
            c, row["context_content"], context, created_at=row["created_at"]
        ):
            continue
        state = "proposed"
        if row["source_build_id"] is not None and not current(row["source_build_id"]):
            state = "blocked"
        refs.append({"id": str(row["id"]), "status": state})
        blocked_intents += one(
            c,
            "SELECT count(*) n FROM anvil.benchmark_remediation_intents WHERE proposal_id=%s AND state='blocked'",
            (row["id"],),
        )["n"]
    all_context = (
        not context["model"]
        and context["task"] == "all"
        and context["period"] == "all"
        and context["environment"] == "all"
        and not any(
            context.get(key) for key in ("run_id", "score_revision_id", "trace_id", "cluster")
        )
    )
    dataset_count = (
        one(
            c,
            "SELECT count(*) n FROM anvil.benchmark_golden_datasets d WHERE NOT EXISTS(SELECT 1 FROM anvil.benchmark_golden_dataset_events e WHERE e.dataset_id=d.id)",
        )["n"]
        if all_context
        else len(datasets)
    )
    return {
        "datasets": dataset_count,
        "case_versions": len(cases),
        "verified_cases": sum(row["status"] == "verified" for row in cases),
        "proposals": len(refs),
        "blocked_intents": blocked_intents,
        "cases": cases,
        "proposal_refs": refs,
    }
