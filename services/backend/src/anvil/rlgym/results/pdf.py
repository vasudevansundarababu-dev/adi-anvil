"""PDF of the run report (SCREENS 3.36): the same view as the Report tab, printed in full on A4 by headless Chromium.

Cover, then every view in order (1 Overview, 2 Task results, 3 Agent performance, 4 Failures & evidence, 5 Trust &
Safety), then appendices A Tasks, B Environment and data plan, C Rubric and evaluators, D Models, E Trust & Safety
prompts, F Provenance. Tables print in full; filters are not printed; every page carries the manifest hash and
"Page n of N" (Chromium footer). No script, no network.
"""

import base64
import math
from functools import cache
from html import escape

from anvil.config import ROOT

# ADI Labs Forge branding (shared/BRANDING.md, work package 2.13): the full logo on page 1 (light background), and the
# running header on every page (set by scripts/render-report-pdf.mjs).
BRAND_FAMILY, BRAND_PRODUCT = "ADI Labs Forge", "RL Gym Evaluation"
RUNNING_HEADER = f"{BRAND_FAMILY} · {BRAND_PRODUCT}"


@cache
def _logo_uri():
    raw = (ROOT / "assets/brand/adi-labs-forge-logo.png").read_bytes()
    return "data:image/png;base64," + base64.b64encode(raw).decode()


CSS = """
@page { size: A4; }
* { box-sizing: border-box; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 9.5px; color: #1a2c3d; margin: 0; }
h1 { font-size: 20px; margin: 0 0 6px; }
h2 { font-size: 14px; margin: 0 0 8px; border-bottom: 2px solid #096f61; padding-bottom: 4px; }
h3 { font-size: 11px; margin: 12px 0 6px; }
section { break-before: page; }
section.cover { break-before: auto; }
table { width: 100%; border-collapse: collapse; margin: 4px 0 10px; }
th, td { border-bottom: 1px solid #dbe4e9; padding: 3px 4px; text-align: left; vertical-align: top; }
th { background: #f4f6f8; font-weight: 600; }
tr { break-inside: avoid; }
.muted { color: #536779; }
.brand { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }
.brand img { height: 92px; }
.brand .product { font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase; color: #5d6475; font-size: 10px; }
.note { background: #fff8e1; border: 1px solid #f0d78c; padding: 5px 7px; margin: 6px 0; }
.cards { display: flex; gap: 8px; flex-wrap: wrap; margin: 6px 0; }
.card { border: 1px solid #dbe4e9; border-radius: 6px; padding: 7px; flex: 1 1 30%; min-width: 150px; break-inside: avoid; }
.big { font-size: 20px; font-weight: 700; }
.gate { font-size: 8px; font-weight: 700; padding: 1px 5px; border-radius: 8px; float: right; }
.PASSED { background: #e5f3ed; color: #096f61; } .FAILED { background: #fbe3e1; color: #b3261e; }
.bar { height: 7px; background: #096f61; border-radius: 2px; }
.bar.alt1 { background: #3a7bd5; } .bar.alt2 { background: #c77d16; }
.mono { font-family: Menlo, Consolas, monospace; font-size: 8px; word-break: break-all; }
.toc li { margin: 2px 0; }
"""
ALT = ["", "alt1", "alt2", "alt1", "alt2"]
COLORS = ["#096f61", "#3a7bd5", "#c77d16", "#7a3fbf", "#b3261e"]


def e(v):
    return escape("—" if v is None else str(v))


def pct(v):
    return "—" if v is None else f"{round(v * 100)}%"


def table(head, rows):
    return (
        "<table><thead><tr>"
        + "".join(f"<th>{e(h)}</th>" for h in head)
        + "</tr></thead><tbody>"
        + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
        + "</tbody></table>"
    )


def bars(per_model, models, scale=100, fmt=lambda v: e(v)):
    out = []
    for i, m in enumerate(models):
        v = per_model.get(m["system_id"])
        width = 0 if v is None else max(0, min(100, 100 * float(v) / scale))
        out.append(
            f'<div style="display:flex;align-items:center;gap:4px"><span style="width:110px" class="muted">{e(m["name"])}</span>'
            f'<div style="flex:1;background:#f4f6f8"><div class="bar {ALT[i % 5]}" style="width:{width:.1f}%"></div></div>'
            f'<span style="width:36px;text-align:right">{fmt(v)}</span></div>'
        )
    return "".join(out)


def radar(axes, models, size=230):
    """Inline SVG radar chart: one polygon per model over the capability axes (0-100)."""
    n = len(axes)
    if n < 3:
        return ""
    cx = cy = size / 2
    r = size / 2 - 40
    pts = lambda i, v: (  # noqa: E731
        cx + r * v / 100 * math.sin(2 * math.pi * i / n),
        cy - r * v / 100 * math.cos(2 * math.pi * i / n),
    )
    svg = [
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">'
    ]
    for ring in (25, 50, 75, 100):
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pts(i, ring) for i in range(n)))
        svg.append(f'<polygon points="{poly}" fill="none" stroke="#dbe4e9" stroke-width="0.8"/>')
    for i, a in enumerate(axes):
        x, y = pts(i, 118)
        svg.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-size="7" text-anchor="middle" fill="#536779">{e(a["capability"])}</text>'
        )
    for j, m in enumerate(models):
        vals = [a["per_model"].get(m["system_id"]) or 0 for a in axes]
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pts(i, v) for i, v in enumerate(vals)))
        color = COLORS[j % len(COLORS)]
        svg.append(
            f'<polygon points="{poly}" fill="{color}" fill-opacity="0.12" stroke="{color}" stroke-width="1.2"/>'
        )
    svg.append("</svg>")
    legend = " ".join(
        f'<span style="color:{COLORS[j % len(COLORS)]}">■</span> {e(m["name"])}'
        for j, m in enumerate(models)
    )
    return "".join(svg) + f'<div class="muted">{legend}</div>'


def cards(items):
    out = ['<div class="cards">']
    for c in items:
        rng = c.get("likely_range")
        out.append(
            f'<div class="card"><span class="gate {e(c.get("gate"))}">{e(c.get("gate"))}</span><b>{e(c["name"])} v{e(c["version"])}</b>'
            f'<div class="big">{e(c.get("mean"))}<span class="muted" style="font-size:9px"> /100</span></div>'
            f'<div class="muted">automated · likely range {e(rng[0]) + "–" + e(rng[1]) if rng else "—"} · {e(c.get("scored"))} scored · passed {pct(c.get("pass_rate"))}</div>'
            + (
                f"<div>reviewed {e(c['reviewed']['reviewed'])} · automated {e(c['reviewed']['automated'])} · {e(c['reviewed']['excluded'])} excluded</div>"
                if c.get("reviewed")
                else ""
            )
            + (
                f'<div style="color:#b3261e">{e("; ".join(c["gate_notes"]))}</div>'
                if c.get("gate_notes")
                else ""
            )
            + "</div>"
        )
    out.append("</div>")
    return "".join(out)


def render(view, appendix):
    h = view["header"]
    models = h["models"]
    names = [m["name"] for m in models]
    ov, tk, ag, fl, ts = (
        view["overview"],
        view["tasks"],
        view["agent"],
        view["failures"],
        view["ts"],
    )
    parts = [
        f"<!doctype html><html><head><meta charset='utf-8'><title>Report {e(h['run_id'])}</title><style>{CSS}</style></head><body>"
    ]
    # Cover
    parts.append(
        f"""<section class="cover"><div class="brand"><img src="{_logo_uri()}" alt="{BRAND_FAMILY}"><div class="product">{BRAND_PRODUCT} · run report</div></div><h1>{e(h["name"])}</h1>
<p>{e(h["run_id"])} · project {e(h["project"]["name"])} ({e(h["project"]["id"])}) · template {e(h["template"]["name"])} v{e(h["template"]["version"])} · {e(h.get("scoring") or ("pass mark " + str(h["template"]["pass_mark"])))}</p>
<div class="note">{e(h["note"])}</div>{cards(ov["cards"])}
<p>{e(h["cohort"])}</p>
<table><tbody>
<tr><th>Suite</th><td>{e(h["suite"]["name"])} v{e(h["suite"]["version"])} <span class="mono">{e(h["suite"]["suite_sha256"])}</span></td></tr>
<tr><th>Environment</th><td>{e(h["environment"])} · seed family {e(h["seed_family"])}</td></tr>
<tr><th>Evaluators</th><td>{e(h["evaluators"])} configurations · scoring pass {e(h["pass"]["number"])} ({e(h["pass"]["reason"])})</td></tr>
<tr><th>Manifest</th><td class="mono">{e(h["manifest_sha256"])}</td></tr>
<tr><th>SME review</th><td>{e(ov["review_sample"]["state"])}</td></tr>
<tr><th>Report</th><td>revision {e(appendix["revision"])} · view <span class="mono">{e(appendix["view_sha256"])}</span></td></tr>
</tbody></table>
<h3>Contents</h3><ol class="toc"><li>Overview</li><li>Task results</li><li>Agent performance</li><li>Failures &amp; evidence</li><li>Trust &amp; Safety</li>
<li>Appendix A Tasks · B Environment and data plan · C Rubric and evaluators · D Models · E Trust &amp; Safety prompts · F Provenance</li></ol></section>"""
    )
    # 1 Overview
    parts.append("<section><h2>1 Overview</h2>" + cards(ov["cards"]))
    parts.append(
        f"<h3>SME review sample</h3><p class='muted'>{e(ov['review_sample']['state'])}</p>"
        + (
            table(
                [
                    "Review item",
                    "Model",
                    "Automated",
                    "SME reviewed",
                    "SME decision",
                    "RL engineer",
                ],
                [
                    [
                        e(f"{r['task_id']} r{r['revision']} · {r['case_id']}"),
                        e(r["model"]),
                        e(r["automated"]),
                        e(r["reviewed"]),
                        e(f"{r['decision']} · {r['rationale'] or ''}"),
                        e(r["rl_engineer"]),
                    ]
                    for r in ov["review_sample"]["items"]
                ],
            )
            if ov["review_sample"]["items"]
            else ""
        )
    )
    parts.append("<h3>Scores by task</h3>")
    parts.append(
        table(
            ["Task", "Case class", *names],
            [
                [
                    e(f"{t['task_id']} r{t['revision']}"),
                    e(t["label"]),
                    *[e(t["per_model"].get(m["system_id"])) for m in models],
                ]
                for t in ov["scores_by_task"]
            ],
        )
    )
    parts.append("<h3>Capability profile</h3>" + radar(ov["capability_profile"], models))
    parts.append(
        table(
            ["Capability", *names],
            [
                [e(a["capability"]), *[e(a["per_model"].get(m["system_id"])) for m in models]]
                for a in ov["capability_profile"]
            ],
        )
        + "</section>"
    )
    # 2 Task results
    parts.append("<section><h2>2 Task results</h2>")
    parts.append(
        table(
            ["Task", "Case class", *[f"{n} (mean · failed cases)" for n in names]],
            [
                [e(f"{t['task_id']} r{t['revision']}"), e(t["label"])]
                + [
                    e(
                        f"{(t['per_model'].get(m['system_id']) or {}).get('mean')} · {(t['per_model'].get(m['system_id']) or {}).get('failed_cases', 0)}"
                    )
                    for m in models
                ]
                for t in tk["tasks"]
            ],
        )
    )
    parts.append("<h3>Results by stratum</h3>")
    parts.append(
        table(
            ["Stratum", "Episodes", *[f"{n} passed" for n in names]],
            [
                [
                    e(f"{s['dimension']} · {s['value']}")
                    + (" <span class='muted'>small sample</span>" if s["small_sample"] else ""),
                    e(s["episodes"]),
                ]
                + [pct(s["per_model"].get(m["system_id"])) for m in models]
                for s in tk["strata"]
            ],
        )
    )
    parts.append("<h3>Per criterion</h3>")
    parts.append(
        table(
            ["Criterion", "Capability", *names, "Blocked", "Evaluator"],
            [
                [
                    e(c["criterion_id"]),
                    e(c["capability"]),
                    *[pct(c["per_model"].get(m["system_id"])) for m in models],
                    e(c["blocked"]),
                    e(c["evaluator"]),
                ]
                for c in tk["criteria"]
            ],
        )
        + "</section>"
    )
    # 3 Agent performance
    parts.append(
        "<section><h2>3 Agent performance</h2>"
        + cards(ag["cards"])
        + "<h3>Capability comparison</h3>"
    )
    for a in ag["capabilities"]:
        parts.append(
            f"<div style='margin:4px 0'><b>{e(a['capability'])}</b>{bars(a['per_model'], models)}</div>"
        )
    parts.append(radar(ag["capabilities"], models))
    case = ag.get("case")
    if case:
        parts.append(
            f"<h3>Same-case outcome and evidence · {e(case['case_id'])} ({e(case['task']['task_id'])})</h3>"
        )
        parts.append(
            table(
                ["Capability", *names],
                [
                    [e(h2["capability"]), *[e(h2["per_model"].get(m["system_id"])) for m in models]]
                    for h2 in case["heatmap"]
                ],
            )
        )
        rows = []
        for pm in case["per_model"]:
            for ep in pm["episodes"]:
                strip = " → ".join(
                    f"{w['label']}{' ✕' if w['state'] == 'failed' else ' (skipped)' if w['state'] == 'skipped' else ''}"
                    for w in ep["workflow"]
                )
                rows.append(
                    [
                        e(pm["name"]),
                        e(ep["verdict"]),
                        e(ep["outcome"]),
                        e(ep["likely_cause"]),
                        e(", ".join(ep["failed_criteria"])),
                        e(strip),
                        f"<span class='mono'>{e(ep['episode_id'])}</span>",
                    ]
                )
        parts.append(
            table(
                [
                    "Model",
                    "Verdict",
                    "Outcome",
                    "Likely cause",
                    "Failed criteria",
                    "Workflow",
                    "Evidence",
                ],
                rows,
            )
        )
    else:
        parts.append("<p class='muted'>No case where the models disagree.</p>")
    parts.append("</section>")
    # 4 Failures
    parts.append("<section><h2>4 Failures &amp; evidence</h2>")
    parts.append(
        table(
            ["Model", "Failed of scored", "Errored", "Timed out"],
            [
                [
                    e(p["name"]),
                    e(f"{p['failed']} of {p['scored']}"),
                    e(p["errored"]),
                    e(p["timed_out"]),
                ]
                for p in fl["per_model"]
            ],
        )
    )
    parts.append(f"<h3>Failures by likely cause</h3><p class='muted'>{e(fl['cause_note'])}</p>")
    parts.append(
        table(
            ["Likely cause", *names, "Example case"],
            [
                [
                    e(r["cause"]),
                    *[e(r["per_model"].get(m["system_id"], 0)) for m in models],
                    e(r["example_case"]),
                ]
                for r in fl["by_cause"]
            ],
        )
    )
    parts.append(f"<h3>Failed episodes ({len(fl['episodes'])})</h3>")
    parts.append(
        table(
            ["Episode", "Model", "Score", "Likely cause", "Failed criteria", "SME"],
            [
                [
                    e(f"{x['task_id']} · {x['case_id']} · a{x['attempt']}"),
                    e(x["model"]),
                    e(x["score"] if x["score"] is not None else x["state"]),
                    e(x["likely_cause"]),
                    e(", ".join(x["failed_criteria"])),
                    e(x["sme"]),
                ]
                for x in fl["episodes"]
            ],
        )
        + "</section>"
    )
    # 5 Trust & Safety
    parts.append("<section><h2>5 Trust &amp; Safety</h2>")
    if not ts["enabled"]:
        parts.append(f"<p>{e(ts['message'])}</p></section>")
    else:
        parts.append(f"<div class='note'>{e(ts['note'])}</div><div class='cards'>")
        for c in ts["cards"]:
            parts.append(
                f"<div class='card'><span class='gate {e(c['gate'])}'>{e(c['gate'])}</span><b>{e(c['name'])}</b><div>Attacks acted on {e(c['acted_on'])} of {e(c['attacks'])}</div>"
                f"<div class='muted'>{e(c['blocked'])} blocked by the environment · {e(c['critical'])} critical · {e(c['resisted'])} resisted · {e(c['unscored'])} unscored</div></div>"
            )
        parts.append("</div><h3>Critical incidents</h3>")
        parts.append(
            table(
                ["Episode", "Model", "Category", "What happened"],
                [
                    [
                        f"<span class='mono'>{e(i['episode_id'])}</span>",
                        e(i["model"]),
                        e(i["category"]),
                        e(i["what_happened"]),
                    ]
                    for i in ts["critical_incidents"]
                ],
            )
            if ts["critical_incidents"]
            else "<p class='muted'>None.</p>"
        )
        parts.append("<h3>By category</h3>")
        parts.append(
            table(
                ["Category", "Boundary", *names],
                [
                    [e(c["name"]), e(c["boundary"])]
                    + [
                        e(
                            f"{(c['per_model'].get(m['system_id']) or {}).get('acted_blocked', 0) + (c['per_model'].get(m['system_id']) or {}).get('acted_not_blocked', 0)} of {(c['per_model'].get(m['system_id']) or {}).get('attempts', 0)} · "
                            f"{(c['per_model'].get(m['system_id']) or {}).get('acted_blocked', 0)} blocked · {(c['per_model'].get(m['system_id']) or {}).get('acted_not_blocked', 0)} not blocked"
                        )
                        for m in models
                    ]
                    for c in ts["by_category"]
                ],
            )
        )
        parts.append("<h3>Refusal rate by attack style</h3>")
        parts.append(
            table(
                ["Strategy", *names],
                [
                    [
                        e(s["strategy"]),
                        *[pct(s["refusal_rate"].get(m["system_id"])) for m in models],
                    ]
                    for s in ts["by_style"]
                ],
            )
            + "</section>"
        )
    # Appendices
    a = appendix
    parts.append("<section><h2>Appendix A · Tasks</h2>")
    parts.append(
        table(
            ["Task", "Revision", "Case selector", "Packet hash", *names],
            [
                [
                    e(t["task_id"]),
                    e(t["revision"]),
                    e(t["selector"]),
                    f"<span class='mono'>{e(t['package_sha256'])}</span>",
                    *[e(t["per_model"].get(m["system_id"])) for m in models],
                ]
                for t in a["tasks"]
            ],
        )
    )
    env = a["environment"]
    parts.append("<h2 style='margin-top:14px'>Appendix B · Environment and data plan</h2>")
    parts.append(
        table(
            ["Field", "Value"],
            [
                [
                    e(k),
                    f"<span class='mono'>{e(v)}</span>"
                    if "sha" in k or "digest" in k or "image" in k
                    else e(v),
                ]
                for k, v in env.items()
            ],
        )
    )
    parts.append(
        table(
            ["Cell", "Quota", "Available", "Selected"],
            [
                [e(c["cell_key"]), e(c["quota"]), e(c["available"]), e(c["selected"])]
                for c in a["cells"]
            ],
        )
    )
    parts.append("</section><section><h2>Appendix C · Rubric and evaluators</h2>")
    parts.append(
        table(
            ["Criterion", "Capability", "Weight", "Gate", "Evaluator", "Framework", "Evidence"],
            [
                [
                    e(r["criterion_id"]),
                    e(r["capability"]),
                    e(r["weight"]),
                    "yes" if r["is_gate"] else "no",
                    e(r["evaluator"]),
                    e(r["framework"]),
                    e(r["evidence"]),
                ]
                for r in a["rubric"]
            ],
        )
    )
    parts.append("<h2 style='margin-top:14px'>Appendix D · Models</h2>")
    parts.append(
        table(
            ["Model", "Version", "Kind", "Provider", "Model ID", "Limits", "Config hash"],
            [
                [
                    e(m["name"]),
                    e(m["version"]),
                    e(m["kind"]),
                    e(m["provider"]),
                    e(m["model_id"]),
                    e(m["limits"]),
                    f"<span class='mono'>{e(m['config_sha256'])}</span>",
                ]
                for m in a["models"]
            ],
        )
    )
    parts.append("</section><section><h2>Appendix E · Trust &amp; Safety prompts</h2>")
    parts.append(
        table(
            ["Prompt", "Category", "Strategy", "Severity", "Text"],
            [
                [e(p["id"]), e(p["category_key"]), e(p["strategy"]), e(p["severity"]), e(p["text"])]
                for p in a["prompts"]
            ],
        )
        if a["prompts"]
        else "<p class='muted'>Trust &amp; Safety was off for this run.</p>"
    )
    parts.append("<h2 style='margin-top:14px'>Appendix F · Provenance</h2>")
    parts.append(
        table(
            ["Field", "Value"],
            [
                [e(k), f"<span class='mono'>{e(v)}</span>" if "sha" in k else e(v)]
                for k, v in a["provenance"].items()
            ],
        )
    )
    parts.append("</section></body></html>")
    return "".join(parts)
