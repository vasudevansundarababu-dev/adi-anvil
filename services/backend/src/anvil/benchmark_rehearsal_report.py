"""Snapshot-bound fictional software reports; never model or review evidence."""

import io
from html import escape
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import Response

from anvil import auth
from anvil import benchmark_rehearsal as rehearsal


def render(row, template):
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    target = io.BytesIO()
    styles = getSampleStyleSheet()

    def p(value, style="BodyText"):
        return Paragraph(escape(str(value)), styles[style])

    result = row["result"]
    labels = {item["id"]: item["label"] for item in row["manifest"]["profiles"]}
    story = [
        p("Fictional software comparison", "Title"),
        p(row["name"], "Heading2"),
        p(
            "Actual scripted execution on public fictional inputs. No model inference, model-performance claim, native isolation qualification or LLM judge result."
        ),
        p("Rehearsal: " + str(row["id"])),
        p("Manifest SHA-256: " + row["manifest_sha256"]),
        p("Result SHA-256: " + result["result_sha256"]),
        p("Environment: " + row["manifest"]["environment"]),
        p("Provider calls: 0. Official benchmark primary: unavailable."),
        p("Report authorization: " + row["report_authorization"]["state"]),
        p("Authorization is not a fabricated independent human review."),
        p("Full frozen suite scores", "Heading2"),
    ]
    for profile in result["profiles"]:
        story.append(
            p(
                f"{labels[profile['profile_id']]}: {profile['mean_points']} / {profile['possible_points']}; mean of two original repetitions."
            )
        )
    story.extend([p("Observed win/tie metric", "Heading2")])
    for item in result["ranking"]["observed_win_rate"]["rows"]:
        story.append(
            p(
                f"{labels[item['profile_id']]}: {item['percent']}%; {item['wins']} wins, {item['ties']} ties, {item['losses']} losses."
            )
        )
    bt = result["ranking"]["bradley_terry"]
    story.extend([p("Separate Bradley–Terry fit", "Heading2"), p(bt["status"])])
    if bt.get("reason"):
        story.append(p(bt["reason"]))
    for item in bt["rows"]:
        story.append(
            p(
                f"Rank {item['rank']}: {labels[item['profile_id']]} · relative strength {item['relative_strength']}"
            )
        )
    if template == "technical":
        story.append(p("Stored execution and deterministic checks", "Heading2"))
        for cell in result["cells"]:
            story.extend(
                [
                    Spacer(1, 8),
                    p(
                        f"{labels[cell['profile_id']]} / {cell['task_id']} / repetition {cell['repetition'] + 1}",
                        "Heading3",
                    ),
                    p(
                        f"{cell['earned_points']} / {cell['possible_points']} · {cell['state']} · {cell['duration_ms']} ms"
                    ),
                    p("Output SHA-256: " + cell["output_sha256"]),
                ]
            )
            for criterion in cell["criteria"]:
                story.append(
                    p(
                        f"{criterion['id']}: {criterion['earned_points']} / {criterion['possible_points']}"
                    )
                )
    story.extend(
        [
            p("Limitations", "Heading2"),
            p(
                "Judge metrics and token likelihoods were not run. Private golden expected answers, proposed prompts and hidden reasoning are excluded. No source qualification or release approval is granted by this report."
            ),
        ]
    )
    SimpleDocTemplate(
        target, title="Anvil fictional software comparison", leftMargin=35, rightMargin=35
    ).build(story)
    raw = target.getvalue()
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(409, "Fictional report exceeds bounded export size")
    return raw


def routes(context, wrap):
    router = APIRouter(prefix="/api/v1/projects/{project}/workspace/benchmarks")

    @router.get("/rehearsals/{identifier}/report")
    def report(project: UUID, identifier: UUID, request: Request):
        rehearsal.enabled()
        template = request.query_params.get("template", "executive")
        if template not in {"executive", "technical"}:
            raise HTTPException(422, "Unknown report template")
        if any(
            request.query_params.get(key, "false") != "false"
            for key in ("include_prompts", "include_raw_prompts")
        ):
            raise HTTPException(403, "Private inputs and expected answers are excluded")
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")
            row = rehearsal.get(c, identifier)
            rehearsal.require_report(c, row)
            if request.query_params.get("expected_result_sha256") != row["result"]["result_sha256"]:
                raise HTTPException(409, "Exact stored rehearsal result digest required")
        raw = render(row, template)
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")
            after = rehearsal.get(c, identifier)
            rehearsal.require_report(c, after)
            if after != row:
                raise HTTPException(409, "Report authorization or source changed; refresh")
        return Response(
            raw,
            media_type="application/pdf",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": f'attachment; filename="anvil-fictional-{template}.pdf"',
                "X-Anvil-Result-SHA256": row["result"]["result_sha256"],
            },
        )

    return router
