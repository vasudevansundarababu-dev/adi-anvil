import csv
import hashlib
import html
import io
import json
import zipfile
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from anvil import artifacts, auth, domain
from anvil.config import ROOT
from anvil.db import audit, digest, one
from anvil.evaluation import get_run

router = APIRouter(prefix="/api/v1/projects/{project}")
LABEL = "ILLUSTRATIVE SYNTHETIC FIXTURE - INTERNAL USE ONLY"


def facts(c, run_id, final=True):
    run = get_run(c, run_id)
    if final and run["state"] not in ("reviewed", "execution_complete", "cancelled"):
        raise HTTPException(409, "Run still has pending, disputed or incomplete assessments")
    protocol = domain.get_revision(c, run["protocol_revision_id"], "protocol")
    suite = domain.get_revision(c, protocol["content"]["suite_revision_id"], "suite")
    objective = domain.get_revision(c, protocol["content"]["objective_revision_id"], "objective")
    episodes = c.execute(
        "SELECT id,task_revision_id,state,outcome,score,final_assessment_id FROM anvil.episodes WHERE run_id=%s ORDER BY id",
        (run_id,),
    ).fetchall()
    valid = [
        e
        for e in episodes
        if e["state"] == "finalized" and e["outcome"] in ("pass", "fail") and e["score"] is not None
    ]
    tasks = [
        domain.get_revision(c, tid, "task")["content"]
        for tid in suite["content"]["task_revision_ids"]
    ]
    return {
        "origin": run["origin"],
        "source_origin": "original_synthetic_fixture",
        "run_id": str(run_id),
        "protocol_revision_id": str(protocol["id"]),
        "protocol_hash": protocol["content_hash"],
        "suite_revision_id": str(suite["id"]),
        "suite_hash": suite["content_hash"],
        "objective_revision_id": str(objective["id"]),
        "question": objective["content"]["hypothesis"],
        "case_count": len({t["source_revision_id"] for t in tasks}),
        "family_count": len({t["family_id"] for t in tasks}),
        "launched": len(episodes),
        "planned": len(suite["content"]["task_revision_ids"])
        * len(protocol["content"]["candidates"])
        * protocol["content"].get("repetitions", 1),
        "completed": sum(e["state"] == "finalized" for e in episodes),
        "valid": len(valid),
        "passes": sum(e["outcome"] == "pass" for e in valid),
        "failures": sum(e["outcome"] == "fail" for e in valid),
        "pending": sum(
            e["state"] in ("queued", "output_captured", "awaiting_review", "disputed")
            for e in episodes
        ),
        "invalid": sum(e["outcome"] == "invalid" for e in episodes),
        "unscorable": sum(e["outcome"] == "unscorable" for e in episodes),
        "unknown": sum(e["state"] == "execution_unknown" for e in episodes),
        "cancelled": sum(e["state"] == "cancelled" for e in episodes),
        "mean_score": float(sum(e["score"] for e in valid) / len(valid)) if valid else None,
        "pass_rate": sum(e["outcome"] == "pass" for e in valid) / len(valid) if valid else None,
        "assessment_ids": [str(e["final_assessment_id"]) for e in valid],
        "sources": [t["source_revision_id"] for t in tasks],
        "scorecards": [
            {
                "episode_id": str(e["id"]),
                "state": e["state"],
                "outcome": e["outcome"],
                "score": float(e["score"]) if e["score"] is not None else None,
            }
            for e in episodes
        ],
        "uncertainty": "not_estimated",
        "improvement": "not_tested",
        "limitations": "Custom development suite; predetermined fixture responses; synthetic source and scripted local reviews. No measured frontier-model performance, faculty validation, human baseline, causal diagnosis or generalization.",
        "denominator_definition": "Pass rate and mean include only finalized scored pass/fail episodes. Completed counts finalized reviews. Cancelled, invalid, unknown and pending episodes are disclosed separately.",
    }


def prepare_report(c, content):
    f = facts(c, content["run_id"])
    findings = []
    for fid in content["finding_revision_ids"]:
        finding = domain.get_revision(c, fid, "finding", ["approved"])
        e = one(
            c, "SELECT run_id FROM anvil.episodes WHERE id=%s", (finding["content"]["episode_id"],)
        )
        if not e or str(e["run_id"]) != content["run_id"]:
            raise HTTPException(409, "Finding belongs to a different run")
        findings.append(
            {
                "revision_id": str(finding["id"]),
                "hash": finding["content_hash"],
                "observation": finding["content"]["observation"],
                "confidence": finding["content"]["confidence"],
            }
        )
    return {
        **content,
        "facts": f,
        "reviewed_findings": findings,
        "evidence_manifest_hash": digest(f),
    }


def prepare_provisional(c, run_id):
    run = get_run(c, run_id)
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (run["project_id"],))
    prior = one(
        c,
        "SELECT r.id FROM anvil.resources r JOIN anvil.revisions v ON v.id=r.current_revision_id WHERE kind='sales_kit' AND v.content->>'run_id'=%s AND v.content->>'stage'='provisional'",
        (str(run_id),),
    )
    if prior:
        return domain.get_resource(c, prior["id"])
    f = facts(c, run_id, final=False)
    kit = domain.create(
        c,
        run["project_id"],
        run["created_by"],
        "sales_kit",
        {
            "title": "Provisional synthetic run digest",
            "run_id": str(run_id),
            "stage": "provisional",
            "label": "PROVISIONAL - NOT FOR EXTERNAL USE",
            "origin": run["origin"],
            "tested": f"{f['case_count']} original synthetic cases; {f['launched']} illustrative episodes.",
            "boundary": "Human review is incomplete. Performance is not established. No external download or sending authority.",
            "facts": f,
        },
    )
    return domain.move(c, kit, run["created_by"], "provisional")


def validity(c, report, sharing=True):
    if report["lifecycle"] != "approved":
        raise HTTPException(409, "Report scientific/audience/release approval required")
    b = report["content"]
    f = b["facts"]
    domain.get_revision(c, f["objective_revision_id"], "objective", ["approved"])
    domain.get_revision(c, f["protocol_revision_id"], "protocol", ["approved"])
    suite = domain.get_revision(c, f["suite_revision_id"], "suite", ["frozen"])
    for tid in suite["content"]["task_revision_ids"]:
        task = domain.get_revision(c, tid, "task", ["published"])
        # The worker cannot read rubric content; checking its metadata needs no hidden bytes.
        rubric = one(
            c,
            "SELECT r.lifecycle,r.current_revision_id FROM anvil.resources r WHERE r.current_revision_id=%s AND r.kind='rubric'",
            (task["content"]["rubric_revision_id"],),
        )
        if not rubric or rubric["lifecycle"] != "approved":
            raise HTTPException(409, "Bound rubric is no longer current and approved")
    if digest(facts(c, b["run_id"])) != b["evidence_manifest_hash"]:
        raise HTTPException(409, "Evidence changed; create and review a successor report")
    for source in b["facts"]["sources"]:
        if not domain.rights_ok(c, source):
            raise HTTPException(409, "Evaluation rights revoked")
        if sharing and not domain.rights_ok(c, source, "report_sharing", "internal_fixture"):
            raise HTTPException(409, "Internal fixture report-sharing rights required")
    for f in b["reviewed_findings"]:
        domain.get_revision(c, f["revision_id"], "finding", ["approved"])


def kit_content(report):
    b = report["content"]
    f = b["facts"]
    mean = "Not yet established" if f["mean_score"] is None else f"{f['mean_score']:.2f}/100"
    return {
        "label": LABEL,
        "title": "Constraint preservation diagnostic",
        "question": f["question"],
        "tested": f"Custom synthetic suite: {f['case_count']} cases, {f['family_count']} families, two deterministic fixture candidates, one attempt per case. Static document-to-deliverable harness; no live inference.",
        "observed": [
            f"{f['passes']} passes and {f['failures']} failures among {f['valid']} valid reviewed episodes.",
            f"Mean submitted-review score: {mean}. Critical violations override numeric thresholds.",
            "These results verify application mechanics; they do not measure model capability.",
        ],
        "relevance": "This workflow can support a scoped investigation of constraint preservation. A real-model study still needs processing rights, exact models, bounded spend, independent approvals and calibrated human review.",
        "boundary": f"{f['launched']} launched; {f['completed']} completed; {f['valid']} valid; {f['invalid']} invalid; {f['unscorable']} unscorable; {f['unknown']} unknown; {f['cancelled']} cancelled; {f['pending']} pending. Predetermined development fixtures and synthetic reviews. No faculty validation, human baseline, generalization or causal claim. Uncertainty not estimated; improvement not tested.",
        "next_step": "Review the evidence and agree a permitted, bounded real-model pilot with independent grading.",
        "report_revision_id": str(report["current_revision_id"]),
        "report_hash": report["content_hash"],
        "origin": f["origin"],
        "source_origin": f["source_origin"],
    }


def pdf_bytes(content):
    stream = io.BytesIO()
    width, height = A4
    pdf = canvas.Canvas(stream, pagesize=A4, invariant=1)
    pdf.setFillColor(colors.white)
    pdf.rect(0, 0, width, height, fill=1, stroke=0)
    pdf.setTitle("ADI Anvil - Internal synthetic diagnostic")
    margin = 16 * mm
    y = height - margin
    pdf.setFillColor(colors.HexColor("#0A2170"))
    pdf.rect(0, height - 42 * mm, width, 42 * mm, fill=1, stroke=0)
    pdf.drawImage(
        str(ROOT / "assets/brand/adi-anvil-logo-v1.png"),
        margin,
        height - 37 * mm,
        width=46 * mm,
        height=30 * mm,
        preserveAspectRatio=True,
        mask="auto",
    )
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 19)
    pdf.drawString(69 * mm, height - 18 * mm, "ADI Anvil")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(69 * mm, height - 25 * mm, "Frontier Evaluation & Diagnostics Platform")
    y = height - 51 * mm
    style = ParagraphStyle(
        "body", fontName="Helvetica", fontSize=10, leading=14, textColor=colors.HexColor("#23354d")
    )

    def paragraph(text, heading=False):
        nonlocal y
        s = (
            ParagraphStyle(
                "heading",
                parent=style,
                fontName="Helvetica-Bold",
                fontSize=11,
                textColor=colors.HexColor("#0A2170"),
            )
            if heading
            else style
        )
        p = Paragraph(html.escape(text), s)
        _, h = p.wrap(width - 2 * margin, height)
        if y - h < 28 * mm:
            raise ValueError("one_page_overflow")
        p.drawOn(pdf, margin, y - h)
        y -= h + (5 if heading else 10)

    paragraph(content["label"], True)
    for title, key in [
        ("Research question", "question"),
        ("What we tested", "tested"),
        ("What we observed", "observed"),
        ("Why a lab may care", "relevance"),
        ("Evidence boundary", "boundary"),
        ("Suggested next step", "next_step"),
    ]:
        paragraph(title, True)
        value = content[key]
        paragraph(" ".join(value) if isinstance(value, list) else value)
    pdf.setStrokeColor(colors.HexColor("#3FAC95"))
    pdf.line(margin, 23 * mm, width - margin, 23 * mm)
    pdf.setFont("Helvetica", 10)
    pdf.setFillColor(colors.HexColor("#526477"))
    pdf.drawString(
        margin,
        17 * mm,
        "Private diagnostic - internal fixture draft; not approved customer delivery",
    )
    pdf.setFont("Helvetica", 10)
    pdf.drawString(margin, 12 * mm, "Report revision: " + content["report_revision_id"])
    pdf.showPage()
    pdf.save()
    return stream.getvalue()


def html_bytes(content):
    body = "".join(
        f"<section><h2>{html.escape(k.replace('_', ' '))}</h2><p>{html.escape(' '.join(v) if isinstance(v, list) else str(v))}</p></section>"
        for k, v in content.items()
        if k in ["question", "tested", "observed", "relevance", "boundary", "next_step"]
    )
    return (
        f'<!doctype html><html lang="en"><meta charset="utf-8"><title>ADI Anvil diagnostic</title><style>body{{font:16px/1.6 Arial;max-width:850px;margin:40px auto;padding:24px;color:#172a45}}h1,h2{{color:#0a2170}}h2{{font-size:20px}}.label{{background:#e9f3f8;padding:14px}}</style><body><h1>ADI Anvil</h1><p>Frontier Evaluation &amp; Diagnostics Platform</p><p class="label">{LABEL}</p>{body}<footer>Report revision {html.escape(content["report_revision_id"])}</footer></body></html>'
    ).encode()


def render_kit(c, report, user):
    c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (report["project_id"],))
    validity(c, report)
    prior = one(
        c,
        "SELECT r.id FROM anvil.resources r JOIN anvil.revisions v ON v.id=r.current_revision_id WHERE r.kind='sales_kit' AND v.content->>'report_revision_id'=%s",
        (str(report["current_revision_id"]),),
    )
    if prior:
        return domain.get_resource(c, prior["id"])
    content = kit_content(report)
    pdf = pdf_bytes(content)
    html_data = html_bytes(content)
    email = (
        "Subject: Synthetic diagnostic workflow - internal review draft\n\n"
        + LABEL
        + "\n\n"
        + content["tested"]
        + "\n\n"
        + " ".join(content["observed"])
        + "\n\n"
        + content["next_step"]
        + "\n\nNo recipient or sending authority configured."
    ).encode()
    brief = (
        "INTERNAL BRIEF\nBuyer: evaluation or capability research lead.\nQuestions: Which constraint failures matter? What actor data may leave your boundary? Who owns acceptance and grading?\nDifferentiator: inspectable version-bound evidence.\nDo not claim model superiority, faculty endorsement, uplift or commercial acceptance.\nNext: agree rights, exact model, budget and independent reviews.\n"
    ).encode()
    rendered = {
        name: artifacts.store(
            c,
            report["project_id"],
            data,
            "approved_delivery" if name != "internal-brief.txt" else "internal",
            mime,
        )
        for name, data, mime in [
            ("sales-kit.pdf", pdf, "application/pdf"),
            ("sales-kit.html", html_data, "text/html"),
            ("email-draft.txt", email, "text/plain"),
            ("internal-brief.txt", brief, "text/plain"),
        ]
    }
    rendered["evidence.zip"] = artifacts.store(
        c,
        report["project_id"],
        bundle(c, report, {"content": {"artifacts": rendered}}),
        "approved_delivery",
        "application/zip",
    )
    kit = domain.create(
        c,
        report["project_id"],
        user,
        "sales_kit",
        {**content, "artifacts": rendered, "content_digest": digest(content)},
        [(report["current_revision_id"], "report")],
    )
    return domain.move(c, kit, user, "approved")


def bundle(c, report, kit):
    b = report["content"]
    f = b["facts"]
    content = kit_content(report)
    files = {
        "README.md": (
            LABEL
            + "\nCustom suite. Improvement not tested. No raw cases, references, identities or protected learning content included."
        ).encode(),
        "suite-card.json": json.dumps(
            {
                k: f[k]
                for k in [
                    "case_count",
                    "family_count",
                    "suite_revision_id",
                    "suite_hash",
                    "source_origin",
                ]
            },
            indent=2,
        ).encode(),
        "protocol.json": json.dumps(
            {
                k: f[k]
                for k in [
                    "protocol_revision_id",
                    "protocol_hash",
                    "origin",
                    "uncertainty",
                    "limitations",
                ]
            },
            indent=2,
        ).encode(),
        "report.html": html_bytes(content),
        "report.md": (
            LABEL
            + "\n\n"
            + content["tested"]
            + "\n\n"
            + "\n".join(content["observed"])
            + "\n\n"
            + content["boundary"]
        ).encode(),
        "findings.jsonl": "\n".join(json.dumps(x) for x in b["reviewed_findings"]).encode(),
    }
    csvfile = io.StringIO()
    writer = csv.DictWriter(csvfile, fieldnames=["episode_id", "state", "outcome", "score"])
    writer.writeheader()
    writer.writerows(f["scorecards"])
    files["scorecards.csv"] = csvfile.getvalue().encode()
    for name, aid in kit["content"]["artifacts"].items():
        if name in ("sales-kit.pdf", "sales-kit.html", "email-draft.txt"):
            files[name] = artifacts.read(c, aid)
    manifest = {
        "schema_version": "anvil.release.v1",
        "product": "ADI Anvil",
        "audience": "internal_fixture",
        "label": LABEL,
        "report_revision_id": str(report["current_revision_id"]),
        "report_hash": report["content_hash"],
        "origin": f["origin"],
        "source_origin": f["source_origin"],
        "evidence_manifest_hash": b["evidence_manifest_hash"],
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
    }
    files["manifest.json"] = json.dumps(manifest, indent=2).encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    return out.getvalue()


def routes(context, wrap, idempotent):
    @router.post("/reports/{rid}/build")
    def build(project: UUID, rid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher", "product-owner")

            def render():
                report = domain.get_resource(c, rid, True)
                if report["kind"] != "report":
                    raise HTTPException(404, "Report not found")
                domain.etag(report, request.headers.get("if-match"))
                return render_kit(c, report, user)

            return wrap(idempotent(c, project, user, request, {}, render), request)

    @router.get("/sales-kits")
    def kits(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher", "advisor", "sales", "product-owner")
            return wrap(
                c.execute(
                    "SELECT r.*,v.content,v.content_hash FROM anvil.resources r JOIN anvil.revisions v ON v.id=r.current_revision_id WHERE kind='sales_kit' ORDER BY r.created_at DESC LIMIT 100"
                ).fetchall(),
                request,
            )

    @router.get("/reports/{rid}/download/{name}")
    def download(project: UUID, rid: UUID, name: str, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "researcher", "product-owner", "sales")
            report = domain.get_resource(c, rid)
            if report["kind"] != "report":
                raise HTTPException(404, "Report not found")
            validity(c, report)
            row = one(
                c,
                "SELECT r.id FROM anvil.resources r JOIN anvil.revisions v ON v.id=r.current_revision_id WHERE kind='sales_kit' AND lifecycle='approved' AND v.content->>'report_revision_id'=%s",
                (str(report["current_revision_id"]),),
            )
            if not row:
                raise HTTPException(409, "Build the reviewed report kit first")
            kit = domain.get_resource(c, row["id"])
            types = {
                "sales-kit.pdf": "application/pdf",
                "sales-kit.html": "text/html",
                "email-draft.txt": "text/plain",
                "internal-brief.txt": "text/plain",
                "evidence.zip": "application/zip",
            }
            if name not in types:
                raise HTTPException(404, "Export not found")
            data = (
                bundle(c, report, kit)
                if name == "evidence.zip" and name not in kit["content"]["artifacts"]
                else artifacts.read(c, kit["content"]["artifacts"][name])
            )
            audit(
                c,
                project,
                user,
                "release.download",
                rid,
                {"format": name, "hash": hashlib.sha256(data).hexdigest()},
            )
            return Response(
                data,
                media_type=types[name],
                headers={
                    "Content-Disposition": f'attachment; filename="{name}"',
                    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
                },
            )

    @router.post("/sales-kits/{rid}/send")
    def send(project: UUID, rid: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "sales")
            domain.get_resource(c, rid)
            raise HTTPException(
                409, "Email sending disabled: no sender, recipient or external delivery authority"
            )

    return router
