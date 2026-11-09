"""Evidence-bound business benchmark report. No invented model or safety observations."""

from html import escape
from io import BytesIO
from math import cos, pi, sin

from reportlab.graphics.shapes import Circle, Drawing, Line, String
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def render(data):
    output = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(name="SmallBody", fontName="Helvetica", fontSize=8, leading=11, spaceAfter=2)
    )
    styles["Title"].textColor = colors.HexColor("#153b59")
    story = []

    def text(value, style="BodyText"):
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), styles[style])

    def add(value, style="BodyText"):
        story.extend([text(value, style), Spacer(1, 4 if style == "SmallBody" else 7)])

    def table(rows, widths):
        block = Table(
            [[text(v, "SmallBody") for v in row] for row in rows],
            colWidths=widths,
            repeatRows=1,
            hAlign="LEFT",
        )
        block.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7f0f6")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#d4e0e8")),
                ]
            )
        )
        story.extend([block, Spacer(1, 12)])

    names = {m["id"]: m["name"] for m in data["run"]["snapshot"]["models"]}
    add("ADI ANVIL", "Heading2")
    add("Benchmark evaluation report", "Title")
    add(data["task_group"]["name"], "Heading2")
    add("FICTIONAL SOFTWARE RUN - no vendor model inference, no paid calls", "Heading3")
    add(
        f"Run {data['run']['id']} | Source Project {data['task_group']['source_project_id']} v{data['task_group']['source_version']}",
        "SmallBody",
    )
    add(
        f"Scope: {', '.join(names[m['model_key']] for m in data['summary']['models']) or 'No observations'}; environments: {', '.join(data['context']['environments']) or 'all selected Run environments'}; Task: {data['context']['task']}; period: {data['context']['period']}; method: {data['context']['method']}",
        "SmallBody",
    )
    table(
        [
            ["Agent / model", "Task score / 81", "Executions"],
            *[
                [names[m["model_key"]], m["mean_points"], m["cells"]]
                for m in data["summary"]["models"]
            ],
        ],
        [300, 110, 90],
    )
    drawing = Drawing(500, max(90, len(data["summary"]["models"]) * 40))
    for i, model in enumerate(data["summary"]["models"]):
        y = drawing.height - 22 - i * 40
        drawing.add(String(0, y, names[model["model_key"]], fontSize=8))
        drawing.add(
            Line(
                180,
                y + 3,
                180 + float(model["mean_points"]) / 81 * 270,
                y + 3,
                strokeWidth=12,
                strokeColor=colors.HexColor("#1a8b8e"),
            )
        )
    story.append(drawing)
    add("Report Reviewed", "Heading2")
    review = data["run"]["report_review"]
    add(
        f"{review['state'].replace('_', ' ')}. Executor: {(review['executor'] or {}).get('name', 'Not executed')}. Actual reviews: {review['completed_reviewers']}; frozen requirement: {review['required_reviewers']}. Contact: not supplied."
    )
    for decision in review["decisions"]:
        add(f"{decision['name']}: {decision['decision']} on {decision['created_at']}", "SmallBody")
    story.append(PageBreak())
    add("Matched software comparison", "Title")
    rankings = data["summary"]["ranking"]
    table(
        [
            ["Agent", "Wins", "Ties", "Losses", "Observed %"],
            *[
                [names[r["model_key"]], r["wins"], r["ties"], r["losses"], r["percent"]]
                for r in rankings["observed_win_rate"]["rows"]
            ],
        ],
        [230, 60, 60, 60, 90],
    )
    bt = rankings["bradley_terry"]
    add("Bradley-Terry: " + bt["status"].replace("_", " "), "Heading2")
    if bt["rows"]:
        table(
            [
                ["Agent", "Relative strength"],
                *[[names[r["model_key"]], r["relative_strength"]] for r in bt["rows"]],
            ],
            [350, 150],
        )
    else:
        add(bt.get("reason") or "Insufficient matched evidence")
    add(
        "Observed percentage is (wins + half ties) / matched comparisons. Bradley-Terry is a separate estimate, with half-win ties. Neither is a model-performance claim for these fictional software controls."
    )
    add("Selected evaluation methods", "Heading2")
    table(
        [
            ["Method", "Version", "State"],
            *[
                [m["name"], m["version"], m["execution_status"].replace("_", " ")]
                for m in data["methods"]
            ],
        ],
        [270, 80, 150],
    )
    add("Failures by Task", "Heading2")
    bars = Drawing(500, max(80, len(data["failures"]["by_task"]) * 35))
    for index, task in enumerate(data["failures"]["by_task"]):
        y = bars.height - 18 - index * 35
        bars.add(String(0, y, task["task_id"], fontSize=9))
        if task["total"]:
            bars.add(
                Line(
                    90,
                    y + 3,
                    90 + 300 * task["failed"] / task["total"],
                    y + 3,
                    strokeWidth=10,
                    strokeColor=colors.HexColor("#be704a"),
                )
            )
        bars.add(String(410, y, f"{task['failed']}/{task['total']}", fontSize=9))
    story.append(bars)
    story.append(PageBreak())
    add("Quality, trust and safety", "Title")
    radar = Drawing(500, 300)
    cx, cy, radius = 250, 155, 100
    for level in (25, 50, 75, 100):
        radar.add(
            Circle(
                cx, cy, radius * level / 100, strokeColor=colors.HexColor("#d8e2e9"), fillColor=None
            )
        )
    axis_labels = ["Correctness", "Evidence", "Constraints", "Policy", "Injection", "Containment"]
    points = [
        (cx + radius * cos(pi / 2 + i * pi / 3), cy + radius * sin(pi / 2 + i * pi / 3))
        for i in range(6)
    ]
    for i, (x, y) in enumerate(points):
        radar.add(Line(cx, cy, x, y, strokeColor=colors.lightgrey))
        radar.add(
            String(x, y + (12 if y >= cy else -15), axis_labels[i], textAnchor="middle", fontSize=9)
        )
    palette = ["#147d92", "#bd5638", "#755ca7"]
    for index, series in enumerate(data["series"]):
        shade = colors.HexColor(palette[index % 3])
        for i in range(6):
            a, b = series["axes"][i]["value"], series["axes"][(i + 1) % 6]["value"]
            if a is None or b is None:
                continue
            x, y = points[i]
            xx, yy = points[(i + 1) % 6]
            radar.add(
                Line(
                    cx + (x - cx) * a / 100,
                    cy + (y - cy) * a / 100,
                    cx + (xx - cx) * b / 100,
                    cy + (yy - cy) * b / 100,
                    strokeColor=shade,
                    strokeWidth=2,
                )
            )
        radar.add(String(5, 17 + index * 12, series["name"], fillColor=shade, fontSize=8))
    story.append(radar)
    add(
        "Axes are separate metrics, not a combined safety score. Missing or undecided axes are gaps. Quality uses rubric points; safety uses Pass/(Pass+Fail). Containment measures this local simulator only.",
        "SmallBody",
    )
    rows = [["Axis", *[s["name"] for s in data["series"]]]]
    for axis_index, axis_label in enumerate(
        [
            "Correctness",
            "Evidence completeness",
            "Constraint adherence",
            "Policy adherence",
            "Injection resistance",
            "Environment containment",
        ]
    ):
        values = []
        for series in data["series"]:
            a = series["axes"][axis_index]
            result = (
                f"{a['value']:.1f}%"
                if a["value"] is not None
                else a.get("availability", "not_evaluated").replace("_", " ")
            )
            values.append(
                f"{result}\n{a['decided']}/{a['planned']} decided; U {a['unknown']}; N/A {a.get('counts', {}).get('not_applicable', 0)}"
            )
        rows.append([axis_label, *values])
    table(
        rows,
        [125] + [375 / max(1, len(data["series"]))] * len(data["series"])
        if data["series"]
        else [500],
    )
    story.append(PageBreak())
    add("Task failures and evidence", "Title")
    table(
        [
            ["Task", "Failed executions", "Total"],
            *[[t["name"], t["failed"], t["total"]] for t in data["failures"]["by_task"]],
        ],
        [330, 85, 85],
    )
    grouped = {}
    for cell in data["cells"]:
        assessment = cell["assessment"]
        failed = [c for c in assessment["criteria"] if not c["passed"]]
        policy = [
            f
            for f in assessment["policy_findings"]
            if f["outcome"] in {"fail", "unknown", "error", "not_evaluated"}
        ]
        if not failed and not policy:
            continue
        group = grouped.setdefault(
            (cell["task_key"], cell["model_key"]), {"issues": set(), "evidence": []}
        )
        group["evidence"].append(
            f"{cell['environment_key']} / repeat {cell['repetition'] + 1}\n{cell['id']}"
        )
        for cr in failed:
            group["issues"].add(f"Rubric {cr['id']}: {cr['description']} - failed")
        for finding in policy:
            group["issues"].add(
                f"Policy {finding['rule_id']}: {finding['outcome']} ({finding['severity']})"
            )
    table(
        [
            ["Task / agent", "Observed failures", "Exact evidence IDs"],
            *[
                [
                    task + "\n" + names[model],
                    "\n".join(sorted(group["issues"])),
                    "\n\n".join(group["evidence"]),
                ]
                for (task, model), group in grouped.items()
            ],
        ],
        [125, 195, 180],
    )
    add(
        "Repetitions with the same failure are grouped here. The evidence JSON retains every captured tool event, full capture hash and individual assessment; no failed execution is omitted from the selected cohort.",
        "SmallBody",
    )
    story.append(PageBreak())
    add("Remediation datasets and environments", "Title")
    if data["remediation"]:
        add(data["remediation"][0]["recommendation"])
        add(
            "All examples are unverified drafts, not hidden evaluator references. Full inputs, observed example responses and exact evidence IDs are in the JSONL export.",
            "SmallBody",
        )
        for terms in dict.fromkeys(item["licensing"] for item in data["remediation"]):
            add(terms, "SmallBody")
    else:
        add(
            "No failure-matched package is proposed for this selected cohort; no failing evidence is present."
        )
    for item in data["remediation"]:
        add(item["title"], "Heading2")
        add(
            "Task "
            + item["task_id"]
            + " v"
            + item["task_version"]
            + " + environments "
            + ", ".join(item["environment_ids"]),
            "SmallBody",
        )
        add("Targeted behaviors: " + "; ".join(item["sample"]["expected_behavior"]), "SmallBody")
        add(
            "Sample input: "
            + str(item["sample"]["input"].get("environment", {}).get("initial_state", {})),
            "SmallBody",
        )
        example = item["sample"].get("example_response", {})
        proposed = example.get("output") or {}
        add(
            "Sample response: "
            + str(proposed.get("status", "Needs authoring"))
            + "; citations "
            + ", ".join(proposed.get("citations", []))
            + ". "
            + example.get("status", "needs_authoring").replace("_", " ")
            + "; not human verified.",
            "SmallBody",
        )
        add(
            f"Evidence-linked examples: {len(item['sample']['evidence_ids'])}; source Run {item['sample']['source_run_id']}.",
            "SmallBody",
        )
    if data["remediation"]:
        add(data["remediation"][0]["improvement"], "SmallBody")
    story.append(PageBreak())
    add("Appendix: all Task rubrics", "Title")
    for task in data["task_group"]["tasks"]:
        add(f"{task['task_id']} v{task['task_version']} - {task['title']}", "Heading2")
        table(
            [
                ["Criterion", "Description", "Weight bps"],
                *[
                    [c["id"], c["description"], c["weight_bps"]]
                    for c in (task["rubric"] or {}).get("criteria", [])
                ],
            ],
            [95, 330, 75],
        )
    story.append(PageBreak())
    add("Appendix: evaluation methodology", "Title")
    add(
        "Task score: sum of passed source criterion weights on the 81-point scale; hard constraints can zero the final score. Diagnostic dimension points remain visible. Every Run freezes Task, environment, method, policy, evaluator and source versions."
    )
    add(
        "Observed wins/ties use matched Task/environment/repetition cohorts; Bradley-Terry is separately fitted only when identifiable. These fictional agents are software controls, not frontier models. Judge metrics remain Not run; token probabilities remain Unavailable."
    )
    for method in data["methods"]:
        add(
            f"{method['name']} v{method['version']}: {method['execution_status']}. {method['scope']}. {method.get('reason') or ''}",
            "SmallBody",
        )
    for evaluator in data["evaluators"]:
        add(
            f"Verifier {evaluator['name']} {evaluator['version']} / rule {evaluator['rule_id']}; config {evaluator['id']}; known-case validation {evaluator['validation_id']}; source {evaluator['source_sha256']}",
            "SmallBody",
        )
        mapping = next(
            m
            for m in data["run"]["snapshot"]["mappings"]
            if m["configuration_id"] == evaluator["id"]
        )
        add(
            "Executable rule: "
            + str(mapping["configuration"]["rule"])
            + "; scope: "
            + str(mapping["scope"]),
            "SmallBody",
        )
    for limitation in data["limitations"]:
        add(limitation, "SmallBody")
    add("Exact result SHA256: " + data["run"]["result_sha256"], "SmallBody")
    add("Exact scope SHA256: " + data["view_sha256"], "SmallBody")

    def footer(canvas, doc):
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#526c7d"))
        canvas.drawString(48, 29, "ADI Anvil | Fictional software evaluation | Provider calls: 0")
        canvas.drawRightString(548, 29, str(doc.page))

    SimpleDocTemplate(
        output,
        pagesize=(595.28, 841.89),
        leftMargin=48,
        rightMargin=47,
        topMargin=45,
        bottomMargin=48,
        title="Anvil benchmark report",
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
