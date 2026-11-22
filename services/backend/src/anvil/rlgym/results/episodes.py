"""Episode viewer (SPEC 07.7; SCREENS 3.38): read-only, from the sealed evidence only.

Path graph: the template workflow with the path the agent took (nodes in the order their tools were called, how many
times, the edges between them), the node where the episode failed (first failed criterion's node, else the first
denied tool call, else the last node reached on a timeout) and nodes not reached. Timeline: every tool call with its
arguments, result status and node. Criteria: verdict, points, evaluator version, evidence and the nodes each one
concerns. Output: final output against the output contract and, audited, the expected answer. Suspected cause is a
suggestion until a person sets it. Compare: two episodes of the same task and case side by side with the first step
where their paths diverge.
"""

from anvil.rlgym.common import GymError, audit, require
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
CAUSES = (
    "agent_failure",
    "task_defect",
    "rubric_defect",
    "grader_defect",
    "environment_defect",
    "infrastructure",
)
WRITERS = ("admin", "rl_engineer")


def _episode(c, ws, episode_id):
    row = c.execute(
        """SELECT e.*, r.name run_name, r.state run_state, r.project_id, p.name project_name, m.manifest, m.manifest_sha256,
                  x.bundle_ref, x.sealed_sha256, x.timings, x.tokens_in, x.tokens_out, x.cost_usd
           FROM runs.episodes e JOIN runs.runs r ON r.id=e.run_id JOIN projects.projects p ON p.workspace_id=r.workspace_id AND p.project_id=r.project_id
           JOIN runs.run_manifests m ON m.run_id=e.run_id LEFT JOIN runs.sealed_evidence x ON x.episode_id=e.id
           WHERE e.workspace_id=%s AND e.id=%s""",
        (ws, episode_id),
    ).fetchone()
    if not row:
        raise GymError("NOT_FOUND", "Episode not found")
    return row


def _workflow(c, ws, manifest):
    act = c.execute(
        "SELECT workflow FROM catalog.template_activations WHERE workspace_id=%s AND template_id=%s AND version=%s",
        (ws, manifest["template"]["id"], manifest["template"]["version"]),
    ).fetchone()
    return act["workflow"] if act else {"nodes": [], "edges": []}


def _node_of(workflow):
    out = {}
    for n in workflow["nodes"]:
        for t in n["tools"]:
            out[t] = n["id"]
    return out


def _status(obs):
    if obs.get("blocked"):
        return "denied"
    if obs.get("ok", False):
        return "completed"
    return "error"


def view(c, ws, actor, episode_id):
    e = _episode(c, ws, episode_id)
    m = e["manifest"]
    wf = _workflow(c, ws, m)
    node_of = _node_of(wf)
    bundle = (
        scoring.read_sealed({"bundle_ref": e["bundle_ref"], "sealed_sha256": e["sealed_sha256"]})
        if e["bundle_ref"]
        else None
    )
    timeline, path = [], []
    for step in (bundle or {}).get("transcript") or []:
        if "tool" not in step:
            continue
        node = node_of.get(step["tool"])
        obs = step.get("observation") or {}
        timeline.append(
            {
                "step": step["step"],
                "tool": step["tool"],
                "args": step.get("args") or {},
                "status": _status(obs),
                "observation": obs,
                "node": node,
            }
        )
        if node and (not path or path[-1] != node):
            path.append(node)
    latest = scoring.latest_pass(c, e["run_id"])
    receipts = c.execute(
        "SELECT * FROM scoring.criterion_receipts WHERE episode_id=%s AND pass_id=%s ORDER BY criterion_id",
        (episode_id, latest["id"]),
    ).fetchall()
    evs = {ev["criterion_id"]: ev for ev in latest["evaluator_versions"]}
    criteria = []
    for r in receipts:
        ev = evs.get(r["criterion_id"], {})
        cfg = c.execute(
            "SELECT config FROM catalog.evaluator_configurations WHERE workspace_id=%s AND id=%s AND version=%s",
            (ws, r["configuration_id"], r["configuration_version"]),
        ).fetchone()
        nodes = {SKILL_NODE.get(ev.get("skill_group"))}
        for rule in (cfg or {}).get("config", {}).get("rules", []):
            if rule.get("tool") in node_of:
                nodes.add(node_of[rule["tool"]])
        nodes.discard(None)
        criteria.append(
            {
                "criterion_id": r["criterion_id"],
                "verdict": r["verdict"],
                "points": r["points"],
                "weight": r["weight"],
                "evaluator": f"{r['configuration_id']} v{r['configuration_version']}",
                "evidence_refs": r["evidence_refs"],
                "detail": r["detail"],
                "nodes": sorted(nodes),
                "steps": [t["step"] for t in timeline if t["node"] in nodes],
                "gate": bool(ev.get("is_gate")),
            }
        )
    failed_node, failed_why = None, None
    first_fail = next((cr for cr in criteria if cr["verdict"] in ("fail", "partial")), None)
    if first_fail and first_fail["nodes"]:
        failed_node, failed_why = (
            first_fail["nodes"][0],
            f"criterion {first_fail['criterion_id']} {first_fail['verdict']}",
        )
    elif any(t["status"] == "denied" for t in timeline):
        t = next(t for t in timeline if t["status"] == "denied")
        failed_node, failed_why = t["node"], f"{t['tool']} was refused"
    elif e["state"] == "timed_out" and path:
        failed_node, failed_why = path[-1], "timed out"
    counts = {}
    for t in timeline:
        if t["node"]:
            counts[t["node"]] = counts.get(t["node"], 0) + 1
    taken_edges = sorted({(a, b) for a, b in zip(path, path[1:], strict=False)})
    nodes = [
        {
            "id": n["id"],
            "label": n["label"],
            "taken": n["id"] in counts,
            "calls": counts.get(n["id"], 0),
            "failed": n["id"] == failed_node,
        }
        for n in wf["nodes"]
    ]
    score = c.execute(
        "SELECT * FROM scoring.episode_scores WHERE episode_id=%s AND pass_id=%s",
        (episode_id, latest["id"]),
    ).fetchone()
    safety = c.execute(
        "SELECT * FROM scoring.safety_outcomes WHERE episode_id=%s AND pass_id=%s",
        (episode_id, latest["id"]),
    ).fetchone()
    ref = c.execute(
        "SELECT reference FROM scoring.case_references WHERE workspace_id=%s AND environment_version_id=%s AND case_id=%s",
        (ws, m["environment"]["version_id"], e["case_id"]),
    ).fetchone()
    audit(c, ws, actor, "episode.viewed", episode_id, details={"expected_shown": bool(ref)})
    actor_task = c.execute(
        """SELECT p.content FROM projects.task_imports t JOIN projects.task_payloads p
           ON p.workspace_id=t.workspace_id AND p.package_sha256=t.package_sha256 AND p.part='actor' WHERE t.id=%s""",
        (e["task_import_id"],),
    ).fetchone()
    contract = (actor_task or {}).get("content", {}).get("output_contract") or []
    final = (bundle or {}).get("final_output")
    expected = ref and ref["reference"]
    attempts = c.execute(
        "SELECT try, started_at, ended_at, outcome, note FROM runs.episode_attempts WHERE episode_id=%s ORDER BY try",
        (episode_id,),
    ).fetchall()
    sme = c.execute(
        """SELECT i.id, i.batch_id, i.decision, i.rationale, i.decided_by, b.state batch_state FROM results.sme_review_items i
           JOIN results.sme_review_batches b ON b.id=i.batch_id WHERE i.episode_id=%s ORDER BY b.created_at DESC LIMIT 1""",
        (episode_id,),
    ).fetchone()
    return {
        "episode": {
            k: e[k]
            for k in (
                "id",
                "run_id",
                "run_name",
                "run_state",
                "project_id",
                "project_name",
                "kind",
                "task_id",
                "task_revision",
                "case_id",
                "application_type",
                "completeness",
                "edge_cases",
                "ts_prompt_id",
                "ts_category",
                "system_id",
                "system_version",
                "attempt",
                "state",
                "tries",
                "last_error",
                "likely_cause",
                "likely_cause_source",
            )
        },
        "model": next(
            (x["name"] for x in m["models"] if x["system_id"] == e["system_id"]), e["system_id"]
        ),
        "sealed_sha256": e["sealed_sha256"],
        "manifest_sha256": e["manifest_sha256"],
        "score": score
        and {
            "score": score["score"],
            "passed": score["passed"],
            "failed_criteria": score["failed_criteria"],
        },
        "safety": safety
        and {
            k: safety[k]
            for k in (
                "category_key",
                "outcome",
                "attempted",
                "blocked",
                "critical",
                "grader",
                "evidence",
            )
        },
        "pass": {"number": latest["pass"], "reason": latest["reason"]},
        "path": {
            "nodes": nodes,
            "edges": [{"from": a, "to": b, "taken": (a, b) in taken_edges} for a, b in wf["edges"]],
            "order": path,
            "failed_node": failed_node,
            "failed_why": failed_why,
            "summary": (
                f"Took {len(path)} of {len(wf['nodes'])} steps"
                + (f"; failed at {failed_node} ({failed_why})" if failed_node else "")
                + (
                    f"; not reached: {', '.join(n['id'] for n in nodes if not n['taken'])}"
                    if any(not n["taken"] for n in nodes)
                    else ""
                )
            ),
        },
        "timeline": timeline,
        "criteria": criteria,
        "output": {
            "final": final,
            "contract": contract,
            "fields": [
                {
                    "field": f,
                    "value": (final or {}).get(f),
                    "expected": (expected or {}).get(f) if expected else None,
                    "matches": expected is not None
                    and f in (expected or {})
                    and _same((final or {}).get(f), expected[f]),
                    "in_expected": bool(expected) and f in expected,
                }
                for f in contract
            ],
            "expected": expected,
            "expected_note": "Reviewer only: from the private reference; never shown to the system under test; this view is audited.",
        },
        "environment_state": (bundle or {}).get("environment_state"),
        "timings": e["timings"],
        "tokens": {"in": e["tokens_in"], "out": e["tokens_out"]},
        "attempts": attempts,
        "sme": sme,
        "causes": list(CAUSES),
        "note": m["note"],
    }


def _same(a, b):
    if isinstance(a, list) and isinstance(b, list):
        return sorted(map(str, a)) == sorted(map(str, b))
    return a == b


def set_cause(c, ws, actor, episode_id, body):
    actor.require_person()
    require(actor.profile in WRITERS, "FORBIDDEN", "Viewers cannot change a suspected cause")
    cause = body.get("cause")
    require(
        cause in CAUSES,
        "VALIDATION_FAILED",
        f"cause must be one of {', '.join(CAUSES)}",
        field="cause",
    )
    _episode(c, ws, episode_id)
    c.execute(
        "UPDATE runs.episodes SET likely_cause=%s, likely_cause_source='rl_engineer' WHERE id=%s",
        (cause.replace("_", " "), episode_id),
    )
    audit(c, ws, actor, "episode.cause_set", episode_id, details={"cause": cause})
    return {
        "episode_id": episode_id,
        "likely_cause": cause.replace("_", " "),
        "likely_cause_source": "rl_engineer",
    }


def compare(c, ws, actor, a_id, b_id):
    require(a_id != b_id, "VALIDATION_FAILED", "Pick two different episodes")
    a, b = view(c, ws, actor, a_id), view(c, ws, actor, b_id)
    require(
        (a["episode"]["task_id"], a["episode"]["case_id"])
        == (b["episode"]["task_id"], b["episode"]["case_id"]),
        "VALIDATION_FAILED",
        "Compare attempts of the same task and case",
    )
    ta, tb = a["timeline"], b["timeline"]
    diverge = next(
        (
            i
            for i in range(min(len(ta), len(tb)))
            if (ta[i]["tool"], ta[i]["args"]) != (tb[i]["tool"], tb[i]["args"])
        ),
        None if len(ta) == len(tb) else min(len(ta), len(tb)),
    )
    return {
        "a": a,
        "b": b,
        "first_divergence": None
        if diverge is None
        else {
            "index": diverge,
            "a": ta[diverge] if diverge < len(ta) else None,
            "b": tb[diverge] if diverge < len(tb) else None,
        },
    }
