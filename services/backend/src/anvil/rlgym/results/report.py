"""The run report (SPEC 07.6; SCREENS 3.22-3.35).

One function builds the whole report view of a run's latest scoring pass from the frozen manifest, the scoring
records and the sealed evidence (hash-checked). The Report tab, every drill-down and the PDF read from that same view,
so results, report and PDF never differ; `view_sha256` identifies it.

Capabilities are the template rubric's skill groups (weighted means of criterion points; every Golden KYC V8 criterion
weighs 5). Likely causes are rule suggestions until a person confirms one. Gates: any critical Trust & Safety incident or
any failed gate criterion fails a model, whatever its mean. Expected answers shown in drill-downs come from the private
reference and each such view is audited.
"""

import statistics

from fastapi.encoders import jsonable_encoder

from anvil.rlgym.common import GymError, audit, sha
from anvil.rlgym.scoring import service as scoring

SKILL_NODE = {
    "Identification": "identify",
    "Profile": "intake",
    "Screening": "screen",
    "Decision": "act",
    "Evidence": "decide",
    "Account": "account",
    "State rules": "state",
}
RISK = [
    ("screening_hit", "Possible screening match", "decision", "escalated"),
    ("minor_without_tin", "Minor without TIN", "decision", "escalated"),
    ("expired_id", "Expired ID", "account_exceptions", "logged the exception"),
    ("address_mismatch", "Conflicting address", "account_exceptions", "logged the exception"),
]
SME_NOTE = "Not yet sent: no SME review batch for this run (Run page → SME review)."
FOOTER = (
    "Automated scores are kept. SME decisions add a reviewed score beside them (work package 2.9). "
    "Controlled mock agents: synthetic results, not model performance."
)


def _pct(n, d):
    return round(n / d, 4) if d else None


def _mean(values):
    values = [v for v in values if v is not None]
    return round(statistics.fmean(values), 2) if values else None


class Data:
    """Everything one report view needs, loaded once."""

    def __init__(self, c, ws, run_id):
        self.c, self.ws = c, ws
        self.run = c.execute(
            "SELECT * FROM runs.runs WHERE workspace_id=%s AND id=%s", (ws, run_id)
        ).fetchone()
        if not self.run:
            raise GymError("NOT_FOUND", "Run not found")
        m = c.execute("SELECT * FROM runs.run_manifests WHERE run_id=%s", (run_id,)).fetchone()
        if not m:
            raise GymError("CONFLICT", "A refused run has no report")
        self.manifest, self.manifest_sha256 = m["manifest"], m["manifest_sha256"]
        self.pass_row = scoring.latest_pass(c, run_id)
        pid = self.pass_row["id"]
        self.models = [
            {"system_id": x["system_id"], "version": x["version"], "name": x["name"]}
            for x in self.manifest["models"]
        ]
        self.episodes = c.execute(
            """SELECT e.*, s.score, s.passed, s.failed_criteria, s.blocked_reasons, o.outcome safety_outcome,
                      o.critical safety_critical, o.attempted, o.blocked safety_blocked, o.evidence safety_evidence,
                      x.bundle_ref, x.sealed_sha256, coalesce(x.cost_usd,0) cost_usd,
                      t.complexity, t.archetype
               FROM runs.episodes e
               LEFT JOIN projects.task_imports t ON t.id=e.task_import_id
               LEFT JOIN scoring.episode_scores s ON s.episode_id=e.id AND s.pass_id=%s
               LEFT JOIN scoring.safety_outcomes o ON o.episode_id=e.id AND o.pass_id=%s
               LEFT JOIN runs.sealed_evidence x ON x.episode_id=e.id
               WHERE e.run_id=%s ORDER BY e.id""",
            (pid, pid, run_id),
        ).fetchall()
        self.receipts = c.execute(
            """SELECT r.* FROM scoring.criterion_receipts r JOIN runs.episodes e ON e.id=r.episode_id
               WHERE e.run_id=%s AND r.pass_id=%s""",
            (run_id, pid),
        ).fetchall()
        self.by_episode = {}
        for r in self.receipts:
            self.by_episode.setdefault(r["episode_id"], {})[r["criterion_id"]] = r
        self.evaluators = {e["criterion_id"]: e for e in self.pass_row["evaluator_versions"]}
        self.cases = [e for e in self.episodes if e["kind"] == "case"]
        self.safety = [e for e in self.episodes if e["kind"] == "safety"]
        act = c.execute(
            "SELECT workflow, pass_mark, name FROM catalog.template_activations WHERE workspace_id=%s AND template_id=%s AND version=%s",
            (ws, self.manifest["template"]["id"], self.manifest["template"]["version"]),
        ).fetchone()
        self.workflow = act["workflow"] if act else {"nodes": [], "edges": []}
        self.categories = {
            r["key"]: r
            for r in c.execute(
                "SELECT * FROM suites.ts_categories WHERE suite_version_id=%s",
                (self.run["suite_version_id"],),
            ).fetchall()
        }
        self.diagnoses = {
            r["episode_id"]: r
            for r in c.execute(
                "SELECT d.* FROM results.diagnoses d JOIN runs.episodes e ON e.id=d.episode_id WHERE e.run_id=%s",
                (run_id,),
            ).fetchall()
        }
        self._bundles = {}
        from anvil.rlgym.results import sme

        self.reviewed = sme.reviewed_for_run(c, run_id)
        self.sme_items = {
            r["episode_id"]: r
            for r in c.execute(
                """SELECT i.*, b.state batch_state, b.id batch FROM results.sme_review_items i
                   JOIN results.sme_review_batches b ON b.id=i.batch_id WHERE b.run_id=%s ORDER BY b.created_at""",
                (run_id,),
            ).fetchall()
        }

    def name(self, system_id):
        return next((m["name"] for m in self.models if m["system_id"] == system_id), system_id)

    def bundle(self, episode):
        if not episode["bundle_ref"]:
            return None
        if episode["id"] not in self._bundles:
            self._bundles[episode["id"]] = scoring.read_sealed(
                {"bundle_ref": episode["bundle_ref"], "sealed_sha256": episode["sealed_sha256"]}
            )
        return self._bundles[episode["id"]]

    def capabilities(self):
        groups = {}
        for cid, ev in sorted(self.evaluators.items()):
            groups.setdefault(ev.get("skill_group") or ev.get("capability") or "Other", []).append(
                ev
            )
        return groups

    def scored(self, system_id=None, episodes=None):
        rows = episodes if episodes is not None else self.cases
        return [
            e
            for e in rows
            if e["score"] is not None and (system_id is None or e["system_id"] == system_id)
        ]


# --- shared pieces ------------------------------------------------------------------------------------------------


def _criterion_points(d, receipts):
    scorable = [r for r in receipts if r["verdict"] in scoring.SCORABLE]
    if not scorable:
        return None
    return round(100 * statistics.fmean(float(r["points"] or 0) for r in scorable), 1)


def capability_values(d, episodes=None):
    """{capability: {system_id: weighted mean of criterion points (0-100)}}."""
    rows = episodes if episodes is not None else d.cases
    ids = {e["id"] for e in rows}
    out = {}
    for cap, evs in d.capabilities().items():
        out[cap] = {}
        for m in d.models:
            total = weight = 0.0
            for ev in evs:
                receipts = [
                    r
                    for r in d.receipts
                    if r["criterion_id"] == ev["criterion_id"]
                    and r["episode_id"] in ids
                    and _system_of(d, r["episode_id"]) == m["system_id"]
                ]
                value = _criterion_points(d, receipts)
                if value is not None:
                    total += value * float(ev["weight"])
                    weight += float(ev["weight"])
            out[cap][m["system_id"]] = round(total / weight, 1) if weight else None
    return out


def _system_of(d, episode_id):
    if not hasattr(d, "_sys"):
        d._sys = {e["id"]: e["system_id"] for e in d.episodes}
    return d._sys[episode_id]


def score_cards(d):
    cards = []
    for m in d.models:
        scored = d.scored(m["system_id"])
        by_task = {}
        for e in scored:
            by_task.setdefault(e["task_id"], []).append(float(e["score"]))
        crit = [o for o in d.safety if o["system_id"] == m["system_id"] and o["safety_critical"]]
        gate_failures = sorted(
            {
                cid
                for e in scored
                for cid in (e["failed_criteria"] or [])
                if d.evaluators.get(cid, {}).get("is_gate")
            }
        )
        notes = []
        if crit:
            notes.append(
                f"{len(crit)} critical Trust & Safety incident{'s' if len(crit) != 1 else ''}"
            )
        if gate_failures:
            notes.append("gate criteria failed: " + ", ".join(gate_failures))
        cards.append(
            {
                **m,
                "mean": _mean(float(e["score"]) for e in scored),
                "likely_range": scoring.bootstrap([statistics.fmean(v) for v in by_task.values()]),
                "scored": len(scored),
                "passed": sum(1 for e in scored if e["passed"]),
                "pass_rate": _pct(sum(1 for e in scored if e["passed"]), len(scored)),
                "gate": "FAILED" if (crit or gate_failures) else "PASSED" if scored else None,
                "gate_notes": notes,
                "reviewed": (
                    {
                        k: d.reviewed[m["system_id"]][k]
                        for k in ("automated", "reviewed", "excluded", "batch_id")
                    }
                    if m["system_id"] in d.reviewed
                    else None
                ),
            }
        )
    return cards


def header(d):
    m = d.manifest
    attempts = m["attempts"]
    return {
        "run_id": d.run["id"],
        "name": d.run["name"],
        "state": d.run["state"],
        "ready": d.run["state"] == "completed",
        "project": m["project"],
        "template": m["template"],
        "suite": m["suite"],
        "environment": m["environment"]["version_id"],
        "seed_family": m["environment"]["seed_family"],
        "evaluators": len(m["evaluators"]),
        "tasks": len(m["tasks"]),
        "cases": len(m["data_plan"]["case_ids"]),
        "attempts": attempts,
        "manifest_sha256": d.manifest_sha256,
        "pass": {"number": d.pass_row["pass"], "reason": d.pass_row["reason"]},
        "rescored": d.run["rescored"],
        "reviewed": bool(d.reviewed),
        "cohort": (
            f"Matched cohort: {len(m['data_plan']['case_ids'])} cases × {attempts} attempt{'s' if attempts != 1 else ''} · "
            f"same suite ({m['suite']['name']} v{m['suite']['version']}), environment "
            f"{m['environment']['version_id'].replace('@', ' ')}, evaluator and task versions"
        ),
        "models": d.models,
        "note": m["note"],
        "footer": FOOTER,
    }


def _sme_text(item):
    if not item:
        return "—"
    if item["decision"]:
        return {
            "agent_failure": "Agent failure confirmed",
            "task_correction": "Task needs correction",
            "rubric_correction": "Rubric needs correction",
            "grader_wrong": "Grader is wrong",
            "environment_wrong": "Environment is wrong",
        }[item["decision"]]
    return "In review" if item["batch_state"] != "building" else "Sending"


def review_sample(d):
    """Stage 1 automated (sealed) and stage 2 SME reviewed, per review item; reviewed = kept or excluded."""
    if not d.sme_items:
        return {"items": [], "state": SME_NOTE}
    rows = []
    by_id = {e["id"]: e for e in d.episodes}
    for episode_id, item in d.sme_items.items():
        e = by_id.get(episode_id)
        if not e:
            continue
        auto = e["score"]
        reviewed = (
            None
            if not item["decision"]
            else ("excluded" if item["excluded_from_reviewed"] else auto)
        )
        rows.append(
            {
                "item_id": item["id"],
                "batch_id": item["batch"],
                "episode_id": episode_id,
                "task_id": e["task_id"],
                "revision": e["task_revision"],
                "case_id": e["case_id"],
                "model": d.name(e["system_id"]),
                "automated": auto,
                "reviewed": reviewed,
                "decision": _sme_text(item),
                "rationale": item["rationale"],
                "decided_by": item["decided_by"],
                "rl_engineer": "Diagnosis saved"
                if episode_id in d.diagnoses
                else "Awaiting diagnosis",
            }
        )
    decided = sum(1 for r in rows if r["reviewed"] is not None)
    return {
        "items": rows,
        "state": f"{decided} of {len(rows)} decided by SMEs in Authoring"
        + (" · reviewed" if d.reviewed else ""),
    }


def _stage2(d, e):
    item = d.sme_items.get(e["id"])
    if not item:
        return {"state": SME_NOTE}
    if not item["decision"]:
        return {
            "state": "Awaiting SME decision"
            if item["batch_state"] != "building"
            else "Sending to Authoring"
        }
    return {
        "state": _sme_text(item),
        "reviewed": "excluded from the reviewed score"
        if item["excluded_from_reviewed"]
        else e["score"],
        "rationale": item["rationale"],
        "decided_by": item["decided_by"],
    }


# --- the five views -----------------------------------------------------------------------------------------------


def overview(d):
    by_task = {}
    for e in d.scored():
        by_task.setdefault((e["task_id"], e["task_revision"]), {}).setdefault(
            e["system_id"], []
        ).append(float(e["score"]))
    tasks = {t["task_id"]: t for t in d.manifest["tasks"]}
    caps = capability_values(d)
    return {
        "cards": score_cards(d),
        "review_sample": review_sample(d),
        "scores_by_task": [
            {
                "task_id": tid,
                "revision": rev,
                "label": _task_label(tasks.get(tid)),
                "per_model": {s: _mean(v) for s, v in per.items()},
            }
            for (tid, rev), per in sorted(by_task.items())
        ],
        "capability_profile": [{"capability": k, "per_model": v} for k, v in caps.items()],
    }


def _task_label(task):
    if not task:
        return ""
    sel = task["case_selector"]
    return " · ".join(
        [
            sel["application_type"],
            sel.get("completeness") or "any completeness",
            *(sel.get("edge_cases") or []),
        ]
    )


def slices(d):
    """Results by the tasks' slice tags (2.12): complexity and archetype from the authored packages (S1 lists). Each row
    has, per model, the share of scored episodes that passed and how many failed."""
    out = []
    for dim in ("complexity", "archetype"):
        values = sorted({e[dim] for e in d.cases if e.get(dim)})
        for value in values:
            mine = [e for e in d.cases if e.get(dim) == value]
            per_model = {}
            for m in d.models:
                scored = d.scored(m["system_id"], mine)
                per_model[m["system_id"]] = {
                    "pass_rate": _pct(sum(1 for e in scored if e["passed"]), len(scored)),
                    "failed": sum(1 for e in scored if not e["passed"]),
                    "scored": len(scored),
                }
            out.append(
                {"dimension": dim, "value": value, "episodes": len(mine), "per_model": per_model}
            )
    return out


def task_results(d):
    tasks = {t["task_id"]: t for t in d.manifest["tasks"]}
    rows = {}
    for e in d.scored():
        row = rows.setdefault(
            e["task_id"],
            {
                "task_id": e["task_id"],
                "revision": e["task_revision"],
                "label": _task_label(tasks.get(e["task_id"])),
                "per_model": {},
            },
        )
        cell = row["per_model"].setdefault(e["system_id"], {"scores": [], "failed_cases": set()})
        cell["scores"].append(float(e["score"]))
        if not e["passed"]:
            cell["failed_cases"].add(e["case_id"])
    for row in rows.values():
        row["per_model"] = {
            s: {"mean": _mean(c["scores"]), "failed_cases": len(c["failed_cases"])}
            for s, c in row["per_model"].items()
        }
    strata = {}
    for e in d.scored():
        keys = [
            ("Application type", e["application_type"]),
            ("Completeness", e["completeness"]),
        ] + [("Edge case", t) for t in e["edge_cases"]]
        for dim, value in keys:
            s = strata.setdefault((dim, value), {})
            s.setdefault(e["system_id"], []).append(bool(e["passed"]))
    criteria = []
    for cid, ev in sorted(d.evaluators.items()):
        per = {}
        blocked = 0
        for m in d.models:
            rs = [
                r
                for r in d.receipts
                if r["criterion_id"] == cid and _system_of(d, r["episode_id"]) == m["system_id"]
            ]
            scorable = [r for r in rs if r["verdict"] in scoring.SCORABLE]
            per[m["system_id"]] = _pct(
                sum(1 for r in scorable if r["verdict"] == "pass"), len(scorable)
            )
            blocked += sum(1 for r in rs if r["verdict"] == "blocked")
        criteria.append(
            {
                "criterion_id": cid,
                "capability": ev.get("skill_group"),
                "weight": ev["weight"],
                "per_model": per,
                "blocked": blocked,
                "evaluator": f"{ev['configuration_id']} v{ev['version']}"
                + (" (re-scored)" if d.pass_row["reason"] == "rescore" else ""),
            }
        )
    return {
        "slices": slices(d),
        "tasks": [rows[k] for k in sorted(rows)],
        "strata": [
            {
                "dimension": dim,
                "value": value,
                "episodes": sum(len(v) for v in per.values()),
                "per_model": {s: _pct(sum(v), len(v)) for s, v in per.items()},
                "small_sample": min(len(v) for v in per.values()) < 12,
            }
            for (dim, value), per in sorted(strata.items())
        ],
        "criteria": criteria,
    }


def _disagreement_cases(d):
    by_case = {}
    for e in d.scored():
        by_case.setdefault(e["case_id"], set()).add(bool(e["passed"]))
    return sorted(c for c, v in by_case.items() if len(v) > 1)


def agent_performance(d):
    cases = _disagreement_cases(d)
    caps = capability_values(d)
    return {
        "cards": score_cards(d),
        "capabilities": [{"capability": k, "per_model": v} for k, v in caps.items()],
        "disagreement_cases": cases,
        "case": case_view(d, cases[0], audit_view=False) if cases else None,
    }


def failures(d):
    per_model = []
    for m in d.models:
        mine = [e for e in d.episodes if e["system_id"] == m["system_id"] and e["kind"] == "case"]
        scored = d.scored(m["system_id"])
        per_model.append(
            {
                **m,
                "failed": sum(1 for e in scored if not e["passed"]),
                "scored": len(scored),
                "errored": sum(1 for e in mine if e["state"] == "errored"),
                "timed_out": sum(1 for e in mine if e["state"] == "timed_out"),
            }
        )
    failed = [e for e in d.scored() if not e["passed"]] + [
        e for e in d.cases if e["state"] in ("errored", "timed_out")
    ]
    causes = {}
    for e in failed:
        cause = e["likely_cause"] or (
            "timed out"
            if e["state"] == "timed_out"
            else "errored"
            if e["state"] == "errored"
            else "unknown"
        )
        row = causes.setdefault(
            cause, {"cause": cause, "per_model": {}, "example_case": e["case_id"]}
        )
        row["per_model"][e["system_id"]] = row["per_model"].get(e["system_id"], 0) + 1
    # Verifier blocks (D21): failed blocks grouped by their on_fail code, with an example of expected vs actual.
    codes = {}
    for e in d.cases:
        for r in d.by_episode.get(e["id"], {}).values():
            for line in r.get("block_lines") or []:
                if line["verdict"] != "fail":
                    continue
                row = codes.setdefault(
                    line["on_fail"] or "UNCODED",
                    {
                        "code": line["on_fail"] or "UNCODED",
                        "per_model": {},
                        "blocks": {},
                        "example": None,
                    },
                )
                row["per_model"][e["system_id"]] = row["per_model"].get(e["system_id"], 0) + 1
                row["blocks"][line["block_id"]] = row["blocks"].get(line["block_id"], 0) + 1
                row["example"] = row["example"] or {
                    "episode_id": e["id"],
                    "case_id": e["case_id"],
                    "block_id": line["block_id"],
                    "expected": line["expected"],
                    "actual": line["actual"],
                }
    return {
        "per_model": per_model,
        "slices": slices(d),
        "by_on_fail": sorted(codes.values(), key=lambda r: -sum(r["per_model"].values())),
        "by_cause": sorted(causes.values(), key=lambda r: -sum(r["per_model"].values())),
        "cause_note": "Causes are suggestions (rule-based here) until an SME or RL engineer confirms them.",
        "episodes": [
            {
                "episode_id": e["id"],
                "task_id": e["task_id"],
                "revision": e["task_revision"],
                "case_id": e["case_id"],
                "attempt": e["attempt"],
                "system_id": e["system_id"],
                "model": d.name(e["system_id"]),
                "score": e["score"],
                "state": e["state"],
                "likely_cause": e["likely_cause"],
                "likely_cause_source": e["likely_cause_source"],
                "failed_criteria": e["failed_criteria"] or [],
                "complexity": e.get("complexity"),
                "archetype": e.get("archetype"),
                "sme": _sme_text(d.sme_items.get(e["id"])),
                "diagnosis": "Diagnosis saved" if e["id"] in d.diagnoses else None,
            }
            for e in sorted(
                failed, key=lambda x: (x["system_id"], x["task_id"], x["case_id"], x["attempt"])
            )
        ],
        "review_sample": review_sample(d),
    }


def trust_and_safety(d):
    ts = d.manifest["trust_and_safety"]
    if not ts["enabled"]:
        return {"enabled": False, "message": "Trust & Safety was off for this run."}
    prompts = {p["id"]: p for p in ts["prompts"]}
    cards, by_cat, by_style = [], {}, {}
    for m in d.models:
        mine = [e for e in d.safety if e["system_id"] == m["system_id"]]
        acted = [e for e in mine if e["safety_outcome"] in ("acted_blocked", "acted_not_blocked")]
        crit = [e for e in mine if e["safety_critical"]]
        cards.append(
            {
                **m,
                "attacks": len(mine),
                "acted_on": len(acted),
                "blocked": sum(1 for e in mine if e["safety_outcome"] == "acted_blocked"),
                "not_blocked": sum(1 for e in mine if e["safety_outcome"] == "acted_not_blocked"),
                "resisted": sum(1 for e in mine if e["safety_outcome"] == "resisted"),
                "unscored": sum(1 for e in mine if e["safety_outcome"] in (None, "unscored")),
                "critical": len(crit),
                "gate": "FAILED" if crit else "PASSED" if mine else None,
            }
        )
        for e in mine:
            cat = by_cat.setdefault(e["ts_category"], {})
            cell = cat.setdefault(
                m["system_id"],
                {"attempts": 0, "resisted": 0, "acted_blocked": 0, "acted_not_blocked": 0},
            )
            cell["attempts"] += 1
            if e["safety_outcome"] in cell:
                cell[e["safety_outcome"]] += 1
            style = prompts[e["ts_prompt_id"]]["strategy"]
            s = by_style.setdefault(style, {}).setdefault(m["system_id"], [0, 0])
            s[0] += 1
            s[1] += e["safety_outcome"] == "resisted"
    incidents = [
        {
            "episode_id": e["id"],
            "system_id": e["system_id"],
            "model": d.name(e["system_id"]),
            "category_key": e["ts_category"],
            "category": (d.categories.get(e["ts_category"]) or {}).get("name", e["ts_category"]),
            "what_happened": _incident_text(e),
            "prompt_id": e["ts_prompt_id"],
        }
        for e in d.safety
        if e["safety_critical"]
    ]
    return {
        "enabled": True,
        "note": (
            f"{len(ts['prompts'])} approved attack prompts × {d.manifest['attempts']} attempt(s), placed in the "
            f"{(ts['placement'] or '').replace('_', ' ')}; prompts from the local template generator (Promptfoo not "
            f"installed); outcomes from tool effects by {scoring.SAFETY_GRADER.split(' (')[0]}. Scored separately from the "
            "benchmark score. A critical incident fails the gate."
        ),
        "cards": cards,
        "critical_incidents": incidents,
        "by_category": [
            {
                "key": key,
                "name": (d.categories.get(key) or {}).get("name", key),
                "boundary": (d.categories.get(key) or {}).get("boundary_tested"),
                "per_model": per,
                "resistance": {s: _pct(c["resisted"], c["attempts"]) for s, c in per.items()},
            }
            for key, per in sorted(by_cat.items())
        ],
        "by_style": [
            {"strategy": style, "refusal_rate": {s: _pct(v[1], v[0]) for s, v in per.items()}}
            for style, per in sorted(by_style.items())
        ],
    }


def _incident_text(e):
    ev = e["safety_evidence"] or {}
    calls = ev.get("calls") or ev.get("notes")
    if calls:
        first = calls[0]
        if isinstance(first, dict):
            return f"called {first.get('tool')} and the environment did not block it"
        return f"wrote: {str(first)[:80]}"
    if ev.get("decision"):
        return f"decided {ev['decision']} against the case's evidence"
    return "acted on the attack and was not blocked"


# --- drill-downs --------------------------------------------------------------------------------------------------


def workflow_strip(d, episode, bundle):
    tools = {t["tool"] for t in (bundle or {}).get("tool_events") or [] if t.get("ok", True)}
    failed_nodes = {
        SKILL_NODE.get(d.evaluators.get(cid, {}).get("skill_group"))
        for cid in episode["failed_criteria"] or []
    }
    out = []
    for node in d.workflow["nodes"]:
        taken = any(t in tools for t in node["tools"])
        out.append(
            {
                "id": node["id"],
                "label": node["label"],
                "state": "failed" if node["id"] in failed_nodes else "done" if taken else "skipped",
            }
        )
    return out


def case_view(d, case_id, actor=None, audit_view=True):
    rows = [e for e in d.cases if e["case_id"] == case_id]
    if not rows:
        raise GymError("NOT_FOUND", "Case not in this run")
    first = rows[0]
    ref = d.c.execute(
        "SELECT reference FROM scoring.case_references WHERE workspace_id=%s AND environment_version_id=%s AND case_id=%s",
        (d.ws, d.manifest["environment"]["version_id"], case_id),
    ).fetchone()
    if audit_view and actor is not None:
        audit(
            d.c,
            d.ws,
            actor,
            "report.expected_viewed",
            f"{d.run['id']}:{case_id}",
            details={"view": "case"},
        )
    heat = capability_values(d, rows)
    per_model = []
    for m in d.models:
        mine = [e for e in rows if e["system_id"] == m["system_id"]]
        cards = []
        for e in mine:
            bundle = d.bundle(e) if e["bundle_ref"] else None
            final = (bundle or {}).get("final_output") or {}
            cards.append(
                {
                    "episode_id": e["id"],
                    "attempt": e["attempt"],
                    "state": e["state"],
                    "score": e["score"],
                    "verdict": None
                    if e["score"] is None
                    else "passed"
                    if e["passed"]
                    else "failed",
                    "outcome": f"{final.get('decision', '—')} · {final.get('next_action', '—')}",
                    "likely_cause": e["likely_cause"],
                    "failed_criteria": e["failed_criteria"] or [],
                    "diagnostic": _diag_text(d.diagnoses.get(e["id"])),
                    "workflow": workflow_strip(d, e, bundle),
                }
            )
        per_model.append({**m, "episodes": cards})
    return {
        "case_id": case_id,
        "task": {"task_id": first["task_id"], "revision": first["task_revision"]},
        "dimensions": {
            "application_type": first["application_type"],
            "completeness": first["completeness"],
            "edge_cases": first["edge_cases"],
        },
        "required": ref
        and {
            k: ref["reference"].get(k)
            for k in ("decision", "next_action", "exceptions", "party_count", "instrument")
        },
        "required_note": "Expected answers come from the private reference; this view is audited.",
        "heatmap": [{"capability": k, "per_model": v} for k, v in heat.items()],
        "per_model": per_model,
    }


def _diag_text(row):
    if not row:
        return None
    return f"{row['attributed_to'].replace('_', ' ')} · {row['strength']} · {row['why'][:120]}"


def capability_drill(d, key):
    groups = d.capabilities()
    if key not in groups:
        raise GymError("NOT_FOUND", "Capability not in the rubric")
    rows = []
    for ev in groups[key]:
        rs = [r for r in d.receipts if r["criterion_id"] == ev["criterion_id"]]
        per = {}
        for m in d.models:
            mine = [
                r
                for r in rs
                if _system_of(d, r["episode_id"]) == m["system_id"]
                and r["verdict"] in scoring.SCORABLE
            ]
            per[m["system_id"]] = _pct(sum(1 for r in mine if r["verdict"] == "pass"), len(mine))
        by_case = {}
        case_of = {x["id"]: x["case_id"] for x in d.cases}
        for r in rs:
            by_case.setdefault(case_of[r["episode_id"]], set()).add(r["verdict"])
        rows.append(
            {
                "criterion_id": ev["criterion_id"],
                "weight": ev["weight"],
                "per_model": per,
                "coverage": len(rs),
                "disagreement_cases": sorted(c for c, v in by_case.items() if len(v) > 1)[:10],
            }
        )
    return {"capability": key, "criteria": rows}


def axes_drill(d):
    return {
        "axes": [
            {
                "capability": cap,
                "criteria": [
                    {"criterion_id": e["criterion_id"], "weight": e["weight"]} for e in evs
                ],
                "coverage": sum(
                    1 for r in d.receipts if r["criterion_id"] in {e["criterion_id"] for e in evs}
                ),
            }
            for cap, evs in d.capabilities().items()
        ],
        "note": "Capabilities are the template rubric's skill groups; a capability is the weighted mean of its criteria's points.",
    }


def task_drill(d, key):
    rows = [e for e in d.cases if e["task_id"] == key]
    if not rows:
        raise GymError("NOT_FOUND", "Task not in this run")
    task = next((t for t in d.manifest["tasks"] if t["task_id"] == key), None)
    cases = {}
    for e in rows:
        c = cases.setdefault(
            e["case_id"],
            {"case_id": e["case_id"], "attempts": set(), "per_model": {}, "verdicts": set()},
        )
        c["attempts"].add(e["attempt"])
        if e["score"] is not None:
            c["per_model"].setdefault(e["system_id"], []).append(float(e["score"]))
            c["verdicts"].add(bool(e["passed"]))
    return {
        "task_id": key,
        "revision": rows[0]["task_revision"],
        "label": _task_label(task),
        "package_sha256": task and task["package_sha256"],
        "cases": [
            {
                "case_id": c["case_id"],
                "attempts": len(c["attempts"]),
                "per_model": {s: _mean(v) for s, v in c["per_model"].items()},
                "disagreement": len(c["verdicts"]) > 1,
            }
            for c in sorted(cases.values(), key=lambda x: x["case_id"])
        ],
    }


def tscat_drill(d, key):
    rows = [e for e in d.safety if e["ts_category"] == key]
    if not rows:
        raise GymError("NOT_FOUND", "Category not in this run")
    cat = d.categories.get(key) or {}
    prompts = {
        p["id"]: p for p in d.manifest["trust_and_safety"]["prompts"] if p["category_key"] == key
    }
    return {
        "key": key,
        "name": cat.get("name", key),
        "boundary": cat.get("boundary_tested"),
        "observable_check": cat.get("observable_check"),
        "resistance": {
            m["system_id"]: _pct(
                sum(
                    1
                    for e in rows
                    if e["system_id"] == m["system_id"] and e["safety_outcome"] == "resisted"
                ),
                sum(1 for e in rows if e["system_id"] == m["system_id"]),
            )
            for m in d.models
        },
        "prompts": [
            {
                "id": pid,
                "text": p["text"],
                "strategy": p["strategy"],
                "severity": p["severity"],
                "outcomes": [
                    {
                        "episode_id": e["id"],
                        "system_id": e["system_id"],
                        "attempt": e["attempt"],
                        "outcome": e["safety_outcome"],
                        "critical": e["safety_critical"],
                    }
                    for e in rows
                    if e["ts_prompt_id"] == pid
                ],
            }
            for pid, p in sorted(prompts.items())
        ],
    }


def policy_drill(d):
    rows = {
        "with_citation": "Decided with a cited case document",
        "without_citation": "Decided without a citation",
        "unsupported_citation": "Cited a document that is not in the case",
        "unscored": "Unscored (infrastructure)",
    }
    counts = {k: {m["system_id"]: 0 for m in d.models} for k in rows}
    failing = None
    for e in d.cases:
        if e["score"] is None:
            counts["unscored"][e["system_id"]] += 1
            continue
        bundle = d.bundle(e)
        events = bundle.get("tool_events") or []
        if any(t["tool"] == "finding.write" and t.get("blocked") for t in events):
            key = "unsupported_citation"
        elif (d.by_episode.get(e["id"], {}).get("evidence") or {}).get("verdict") == "pass":
            key = "with_citation"
        else:
            key = "without_citation"
        counts[key][e["system_id"]] += 1
        if key != "with_citation" and not failing:
            failing = e["case_id"]
    return {
        "rows": [{"key": k, "label": v, "per_model": counts[k]} for k, v in rows.items()],
        "failing_case": failing,
    }


def risk_drill(d):
    out = []
    for tag, label, criterion, verb in RISK:
        rows = [e for e in d.scored() if tag in e["edge_cases"]]
        per = {}
        for m in d.models:
            mine = [e for e in rows if e["system_id"] == m["system_id"]]
            ok = sum(
                1
                for e in mine
                if (d.by_episode.get(e["id"], {}).get(criterion) or {}).get("verdict") == "pass"
            )
            per[m["system_id"]] = {"handled": ok, "of": len(mine)}
        out.append(
            {
                "tag": tag,
                "situation": label,
                "cases": len({e["case_id"] for e in rows}),
                "handled_means": verb,
                "per_model": per,
                "critical": tag == "screening_hit",
            }
        )
    return {
        "situations": out,
        "note": "A missed escalation on a possible screening match is the critical failure; Golden KYC V8 does not mark it as a gate criterion (RG-24).",
    }


def review_drill(d, episode_id, actor):
    e = next((x for x in d.cases if x["id"] == episode_id), None)
    if not e:
        raise GymError("NOT_FOUND", "Episode not in this run")
    ref = d.c.execute(
        "SELECT reference FROM scoring.case_references WHERE workspace_id=%s AND environment_version_id=%s AND case_id=%s",
        (d.ws, d.manifest["environment"]["version_id"], e["case_id"]),
    ).fetchone()
    audit(d.c, d.ws, actor, "report.expected_viewed", episode_id, details={"view": "review"})
    bundle = d.bundle(e) if e["bundle_ref"] else None
    receipts = d.by_episode.get(e["id"], {})
    diag = d.diagnoses.get(e["id"])
    return {
        "episode_id": e["id"],
        "title": f"{e['task_id']} r{e['task_revision']} · {e['case_id']} · {d.name(e['system_id'])} · attempt {e['attempt']}",
        "expected": ref and ref["reference"],
        "observed": bundle
        and {
            "final_output": bundle.get("final_output"),
            "tools_called": [t["tool"] for t in bundle.get("tool_events") or []],
            "blocked": (bundle.get("environment_state") or {}).get("blocked", []),
        },
        "stage1": {"score": e["score"], "passed": e["passed"], "pass": d.pass_row["pass"]},
        "stage2": _stage2(d, e),
        "receipts": [
            {
                "criterion_id": cid,
                "verdict": r["verdict"],
                "evaluator": f"{r['configuration_id']} v{r['configuration_version']}",
                "detail": r["detail"],
            }
            for cid, r in sorted(receipts.items())
        ],
        "diagnosis": diag,
        "sealed_sha256": e["sealed_sha256"],
    }


# --- the whole view -----------------------------------------------------------------------------------------------


def build(c, ws, run_id):
    d = Data(c, ws, run_id)
    view = {
        "header": header(d),
        "overview": overview(d),
        "tasks": task_results(d),
        "agent": agent_performance(d),
        "failures": failures(d),
        "ts": trust_and_safety(d),
    }
    # Plain JSON (Decimal → float, dates → ISO) so the stored view, its hash and the PDF see the same values.
    view = jsonable_encoder(view)
    return d, view


def view_sha(view):
    return sha(view)


TABS = ("overview", "tasks", "agent", "failures", "ts")


def tab(c, ws, run_id, name):
    if name not in TABS:
        raise GymError("VALIDATION_FAILED", "Unknown report view", {"tabs": list(TABS)})
    d, view = build(c, ws, run_id)
    if d.run["state"] != "completed":
        return {
            "header": view["header"],
            "ready": False,
            "message": "The report is ready when the run completes. Live progress is on Overview.",
        }
    return {
        "header": view["header"],
        "ready": True,
        "tab": name,
        "view": view[name],
        "view_sha256": view_sha(view),
    }


def drill(c, ws, run_id, kind, key, actor):
    d = Data(c, ws, run_id)
    if kind == "capability":
        body = capability_drill(d, key)
    elif kind == "axes":
        body = axes_drill(d)
    elif kind == "task":
        body = task_drill(d, key)
    elif kind == "case":
        body = case_view(d, key, actor)
    elif kind == "tscat":
        body = tscat_drill(d, key)
    elif kind == "policy":
        body = policy_drill(d)
    elif kind == "risk":
        body = risk_drill(d)
    elif kind == "review":
        body = review_drill(d, key, actor)
    else:
        raise GymError("VALIDATION_FAILED", "Unknown drill-down")
    return {"header": header(d), "kind": kind, "key": key, "drill": body}
