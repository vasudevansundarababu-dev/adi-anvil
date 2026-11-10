"""Read-only connected views and exact-cohort PDF reporting; no dispatch side effects."""

import io
import json
import os
from html import escape
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import Response

from anvil import auth
from anvil import benchmark_dashboard as dashboard
from anvil import benchmark_dashboard_traces as historical
from anvil import benchmark_evaluation as evaluation
from anvil import benchmark_execution as execution
from anvil import benchmark_pipeline as pipeline
from anvil.benchmark_storage import read_private_record
from anvil.db import one


def authorize(roles):
    if os.environ.get("ANVIL_BENCHMARK_ENABLED") != "true":
        raise HTTPException(503, "Benchmark dashboard is disabled for this installation")
    auth.require(roles, "rl-engineer", "admin")


def _comparison_metadata(c, trace_id):
    row = one(
        c,
        "SELECT cell.id,cell.run_id,a.id attempt_id,rt.output_artifact_id,rt.report_artifact_id "
        "FROM anvil.benchmark_cells cell LEFT JOIN anvil.benchmark_cell_attempts a "
        "ON a.project_id=cell.project_id AND a.cell_id=cell.id AND a.attempt_no=1 "
        "LEFT JOIN anvil.benchmark_offline_runtime rt ON rt.project_id=a.project_id AND rt.attempt_id=a.id "
        "WHERE cell.id=%s",
        (trace_id,),
    )
    if row is None:
        raise HTTPException(404, "Trace not found")
    execution.export_rights(c, row["run_id"])
    if row["output_artifact_id"] is None:
        return row, None, []
    artifact = pipeline.private_metadata(c, row["output_artifact_id"])
    if artifact["classification"] != "benchmark_sealed" or artifact["byte_size"] > 16 * 1024 * 1024:
        raise HTTPException(409, "Captured trace output is unavailable or exceeds read bound")
    criteria = c.execute(
        "SELECT cr.criterion_id,cr.earned_points,cr.possible_points FROM anvil.benchmark_criterion_results cr "
        "JOIN anvil.benchmark_evaluator_calls ec ON ec.project_id=cr.project_id AND ec.id=cr.evaluator_call_id "
        "WHERE ec.attempt_id=%s AND ec.evaluation_revision=1 AND ec.purpose='deterministic' ORDER BY cr.criterion_id",
        (row["attempt_id"],),
    ).fetchall()
    return row, artifact, [{key: str(value) for key, value in item.items()} for item in criteria]


def render_pdf(data, template, detail=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    output = io.BytesIO()
    styles = getSampleStyleSheet()

    def p(value, style="BodyText"):
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), styles[style])

    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=34,
        leftMargin=34,
        topMargin=34,
        bottomMargin=34,
        title="Anvil benchmark evidence report",
        author="ADI Anvil",
    )
    story = [
        p("Anvil Benchmark Evaluation", "Title"),
        p(
            "Executive evidence summary"
            if template == "executive"
            else "Technical evidence and provenance",
            "Heading2",
        ),
        p(data["origin_notice"]),
        Spacer(1, 12),
    ]
    story.extend(
        [
            p("Context", "Heading2"),
            p(json.dumps(data["context"], sort_keys=True)),
            p("Snapshot SHA-256: " + data["snapshot_sha256"]),
            p(
                "Raw prompts: excluded. No hidden reasoning or private evaluator material is included."
            ),
        ]
    )
    overview = data["overview"]
    story.extend(
        [
            p("Observed cohort", "Heading2"),
            p(
                f"Stored traces: {overview['total_traces']}; model cells: {overview['model_trace_count']}; historical controls: {overview['control_trace_count']}; reviewed models: {overview['ranked_models']}."
            ),
        ]
    )
    rows = [[p(x) for x in ("Model / suite", "Reviewed task score", "Diagnostic", "Judge")]]
    for model in overview["models"]:

        def label(value):
            return (
                "Unavailable"
                if value is None
                else value["earned_points"]
                + " / "
                + value["possible_points"]
                + " ("
                + value["percent"]
                + "%)"
            )

        rows.append(
            [
                p(
                    model["model_id"]
                    + " / "
                    + model["suite_key"]
                    + "\nBinding: "
                    + model.get("model_key", "unavailable")
                ),
                p(label(model["primary"])),
                p(label(model["diagnostic"])),
                p("Not run"),
            ]
        )
    if len(rows) > 1:
        table = Table(rows, colWidths=[165, 125, 125, 110], repeatRows=1, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9edf6")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.append(table)
    else:
        story.append(
            p(
                "No reviewed model measurements are present. Historical controls do not establish a model leader."
            )
        )
    story.extend(
        [
            p("Separate rankings", "Heading2"),
            p("Observed wins/ties: " + overview["ranking"]["observed_win_rate"]["status"]),
            p("Bradley–Terry: " + overview["ranking"]["bradley_terry"]["status"]),
            p(
                "Likelihood is not factual accuracy. Judge scores and token telemetry remain unavailable until actual supported observations exist."
            ),
        ]
    )
    failures = data["failures"]
    story.extend(
        [
            p("Failure analysis", "Heading2"),
            p(
                f"Eligible model cells: {failures['eligible_traces']}; model failures: {failures['failed_traces']}; infrastructure events: {failures['infrastructure_events']}. Intentional controls are excluded from model failure rates."
            ),
            p(
                "Error rate: "
                + (
                    str(failures["error_rate_percent"]) + "%"
                    if failures["error_rate_percent"] is not None
                    else "Unavailable (no eligible model observations)"
                )
            ),
        ]
    )
    curation = data.get("curation")
    if curation:
        story.extend(
            [
                p("Remediation and golden datasets", "Heading2"),
                p(
                    f"Visible datasets: {curation['datasets']}; current case versions: {curation['case_versions']}; verified cases: {curation['verified_cases']}; proposals: {curation['proposals']}; blocked execution intents: {curation['blocked_intents']}."
                ),
                p(
                    "Expected answers, inputs and proposed prompts are excluded from this report. Proposals do not authorize execution or change approvals."
                ),
            ]
        )
        if template == "technical":
            for case in curation["cases"]:
                story.append(
                    p(
                        f"Case {case['id']} revision {case['revision']} | {case['status']} | SHA-256 {case['content_sha256']}"
                    )
                )
            for proposal in curation["proposal_refs"]:
                story.append(p(f"Proposal {proposal['id']} | {proposal['status']}"))
    if template == "technical":
        story.append(p("Stored trace registry", "Heading2"))
        for trace in data["traces"]:
            story.append(
                p(
                    f"{trace['id']} | {trace['task_label']} | {trace['model_label']} | {trace['state']} | {trace['recorded_at']}"
                )
            )
        if detail:
            story.append(p("Selected authorized trace", "Heading2"))
            for step in detail["steps"]:
                story.append(
                    p(
                        step["label"]
                        + ": "
                        + step["content"][:2000]
                        + (" [excerpt]" if len(step["content"]) > 2000 else "")
                    )
                )
            for criterion in detail["criteria"]:
                story.append(
                    p(
                        criterion["criterion_id"]
                        + ": "
                        + criterion["earned_points"]
                        + " / "
                        + criterion["possible_points"]
                    )
                )
    story.append(p("Limitations and review state", "Heading2"))
    story.extend(p(x) for x in data["limitations"])
    document.build(story)
    raw = output.getvalue()
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(409, "PDF exceeds export bound; narrow the cohort")
    return raw


def routes(context, wrap, idempotent):
    router = APIRouter(
        prefix="/api/v1/projects/{project}/workspace/benchmarks", tags=["benchmark-dashboard"]
    )

    def load(project, request):
        selected = dashboard.query(request)
        with context(request, project) as (c, user, roles):
            authorize(roles)
            try:
                return dashboard.collect(c, selected)
            except (ValueError, KeyError, TypeError) as exc:
                raise HTTPException(
                    409, "Stored dashboard observations are unavailable or inconsistent"
                ) from exc

    def detail(project, trace_id, request, data):
        trace = next((x for x in data["traces"] if x["id"] == str(trace_id)), None)
        if trace is None:
            raise HTTPException(404, "Trace is outside this authorized cohort")
        if trace["kind"] == "historical_control":
            with context(request, project) as (c, user, roles):
                authorize(roles)
                before = historical.metadata(c, trace_id)
            try:
                projection = historical.read(before)
            except (ValueError, KeyError, TypeError, OSError) as exc:
                raise HTTPException(
                    409, "Historical trace evidence is unavailable or changed"
                ) from exc
            with context(request, project) as (c, user, roles):
                authorize(roles)
                after = historical.metadata(c, trace_id)
                if before != after:
                    raise HTTPException(409, "Trace access or receipt changed during inspection")
        else:
            with context(request, project) as (c, user, roles):
                authorize(roles)
                before = _comparison_metadata(c, trace_id)
            row, artifact, criteria = before
            outputs = []
            if artifact:
                try:
                    sealed = json.loads(read_private_record(artifact))
                    evaluation.seal_checked(sealed)
                    outputs = [
                        {key: item.get(key) for key in ("path", "sha256", "byte_size", "text")}
                        for item in sealed["files"]
                    ]
                except (ValueError, KeyError, TypeError, OSError) as exc:
                    raise HTTPException(409, "Captured output changed or is unavailable") from exc
            projection = {
                "steps": [
                    {
                        "id": "observation",
                        "kind": "execution",
                        "label": "Stored original attempt",
                        "status": trace["state"],
                        "content": "Actual original cell observation; source and private evidence rights are rechecked. Input prompt and hidden reasoning are not reconstructed.",
                    }
                ],
                "outputs": outputs,
                "criteria": criteria,
                "limitations": ["No private evaluator or hidden reasoning content is exposed."],
            }
            with context(request, project) as (c, user, roles):
                authorize(roles)
                if _comparison_metadata(c, trace_id) != before:
                    raise HTTPException(409, "Trace access or output changed during inspection")
        return {
            "trace": trace,
            "snapshot_sha256": data["snapshot_sha256"],
            **projection,
            "judge": dashboard.unavailable(dashboard.JUDGE_REASON),
            "logprobs": dashboard.unavailable(dashboard.LOGPROB_REASON, "unavailable"),
        }

    @router.get("/dashboard")
    def overview(project: UUID, request: Request):
        return wrap(load(project, request), request)

    @router.get("/dashboard/traces/{trace_id}")
    def trace(project: UUID, trace_id: UUID, request: Request):
        data = load(project, request)
        value = detail(project, trace_id, request, data)
        if load(project, request)["snapshot_sha256"] != data["snapshot_sha256"]:
            raise HTTPException(409, "Cohort changed during inspection; refresh")
        return wrap(value, request)

    @router.get("/dashboard/report")
    def report(project: UUID, request: Request):
        template = request.query_params.get("template", "executive")
        if template not in {"executive", "technical"}:
            raise HTTPException(422, "Unknown report template")
        if any(
            request.query_params.get(name, "false") != "false"
            for name in ("include_prompts", "include_raw_prompts")
        ):
            raise HTTPException(403, "Raw prompts are not available for this report")
        data = load(project, request)
        expected = request.query_params.get("snapshot_sha256")
        if expected and expected != data["snapshot_sha256"]:
            raise HTTPException(409, "Report snapshot changed; refresh before export")
        selected = (
            detail(project, UUID(data["context"]["trace_id"]), request, data)
            if data["context"]["trace_id"] and template == "technical"
            else None
        )
        raw = render_pdf(data, template, selected)
        if load(project, request)["snapshot_sha256"] != data["snapshot_sha256"]:
            raise HTTPException(409, "Cohort or access changed during report generation")
        return Response(
            raw,
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="anvil-benchmark-'
                + template
                + '.pdf"',
                "Cache-Control": "no-store",
                "X-Anvil-Snapshot": data["snapshot_sha256"],
            },
        )

    return router
