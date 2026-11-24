"""E-004 §3.2-3.3: the grader workbench.

- Drafts (one person, recorded, no approval): per criterion, change a plug-in or rubric block's judge model (approved
  judges only), prompt (rubric), threshold and share of the criterion, or turn the judge block off. Every save is a new
  draft row (who, when, what).
- Re-score instead of re-run: apply drafts to a finished run's sealed evidence as a new *draft* scoring pass. No agent
  is called; judge blocks call the judge (approval and caps as always). A draft pass is never the run's latest pass,
  so reports, the leaderboard and SME review never show draft scores.
- Side by side: per episode and criterion, the real pass's verdict, the draft pass's verdict, and any SME Benchmark
  review decision on that episode.
- Promote ("Ready for leaderboard"): a person proposes a draft; a different RL Engineer or Admin approves (owner
  default). Approval creates an evaluator configuration fix version carrying the draft's overrides; it is qualified by
  its known-case tests and the project's "Latest qualified" rule then follows it. Studio is told (as for every fix).
"""

import uuid

from psycopg.types.json import Jsonb

from anvil.rlgym.common import GymError, audit, require

APPROVERS = ("rl_engineer", "admin")


def _template_blocks(c, ws, project, criterion_id):
    row = c.execute(
        "SELECT verifier_blocks FROM catalog.template_criteria WHERE workspace_id=%s AND template_id=%s AND version=%s AND criterion_id=%s",
        (ws, project["template_id"], project["template_version"], criterion_id),
    ).fetchone()
    return (row or {}).get("verifier_blocks") or []


def _project(c, ws, pid):
    p = c.execute(
        "SELECT * FROM projects.projects WHERE workspace_id=%s AND project_id=%s", (ws, pid)
    ).fetchone()
    if not p:
        raise GymError("NOT_FOUND", "Project not found")
    return p


def validate(c, ws, project, criterion_id, settings):
    from anvil.rlgym.plugins import service as plugins

    blocks = {b.get("id"): b for b in _template_blocks(c, ws, project, criterion_id)}
    editable = {k for k, b in blocks.items() if b.get("plugin") or b.get("kind") == "rubric"}
    judges = set(
        plugins.judge_choices(c, ws)
    )  # mock-judge plus models with an active "judge" approval
    over = settings.get("block_overrides") or {}
    off = settings.get("disabled_blocks") or []
    require(over or off, "VALIDATION_FAILED", "A draft changes at least one judge or rubric block")
    for bid in [*over, *off]:
        require(
            bid in editable,
            "VALIDATION_FAILED",
            f"{bid} is not a judge or rubric block of {criterion_id}",
        )
    for bid, o in over.items():
        st = o.get("settings") or {}
        if "judge" in st:
            require(
                st["judge"] in judges,
                "VALIDATION_FAILED",
                f"{st['judge']} is not an approved judge (approved: {', '.join(sorted(judges)) or 'none'})",
            )
        if "threshold" in st:
            require(
                isinstance(st["threshold"], (int, float)) and 0 <= st["threshold"] <= 1,
                "VALIDATION_FAILED",
                "A threshold is between 0 and 1",
            )
        if "rubric" in st:
            require(
                isinstance(st["rubric"], str) and st["rubric"].strip(),
                "VALIDATION_FAILED",
                "The prompt is empty",
            )
        if "share_percent" in o:
            require(
                isinstance(o["share_percent"], (int, float)) and 0 <= o["share_percent"] <= 100,
                "VALIDATION_FAILED",
                "A share is 0 to 100 percent",
            )
        unknown = set(st) - {"judge", "rubric", "threshold", "target", "assertion"}
        require(
            not unknown, "VALIDATION_FAILED", f"Not editable here: {', '.join(sorted(unknown))}"
        )


def save_draft(ctx, pid, body):
    ctx.actor.require_person()
    project = _project(ctx.c, ctx.ws, pid)
    criterion = body.get("criterion_id")
    rule = ctx.c.execute(
        """SELECT * FROM projects.evaluator_selection_rules WHERE workspace_id=%s AND project_id=%s AND criterion_id=%s
           AND valid_to IS NULL""",
        (ctx.ws, pid, criterion),
    ).fetchone()
    require(rule, "NOT_FOUND", "Unknown criterion for this project")
    settings = {k: body.get(k) for k in ("block_overrides", "disabled_blocks") if body.get(k)}
    validate(ctx.c, ctx.ws, project, criterion, settings)
    did = "gd-" + uuid.uuid4().hex[:10]
    ctx.c.execute(
        """INSERT INTO catalog.grader_drafts(id,workspace_id,project_id,criterion_id,configuration_id,base_version,settings,note,created_by)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            did,
            ctx.ws,
            pid,
            criterion,
            rule["configuration_id"],
            rule["resolved_version"],
            Jsonb(settings),
            (body.get("note") or "").strip() or None,
            str(ctx.actor.id),
        ),
    )
    audit(
        ctx.c,
        ctx.ws,
        ctx.actor,
        "grader.draft_saved",
        did,
        body.get("note"),
        {"criterion": criterion, "settings": settings},
    )
    return get_draft(ctx.c, ctx.ws, did)


def get_draft(c, ws, did):
    d = c.execute(
        "SELECT * FROM catalog.grader_drafts WHERE workspace_id=%s AND id=%s", (ws, did)
    ).fetchone()
    if not d:
        raise GymError("NOT_FOUND", "Draft not found")
    return d


def list_drafts(c, ws, pid):
    from anvil.rlgym.plugins import service as plugins

    return {
        "judges": plugins.judge_choices(c, ws),
        "drafts": c.execute(
            "SELECT * FROM catalog.grader_drafts WHERE workspace_id=%s AND project_id=%s ORDER BY created_at DESC",
            (ws, pid),
        ).fetchall(),
        "promotions": c.execute(
            "SELECT * FROM catalog.grader_promotions WHERE workspace_id=%s AND project_id=%s ORDER BY proposed_at DESC",
            (ws, pid),
        ).fetchall(),
    }


def rescore_with_drafts(ctx, run_id, draft_ids):
    """A new draft scoring pass of a finished run, with these drafts applied (one per criterion at most)."""
    from anvil.rlgym.runs import service as runs
    from anvil.rlgym.scoring import service as scoring

    ctx.actor.require_person()
    run = runs._run(ctx, run_id)
    require(
        run["state"] in ("completed", "cancelled"),
        "CONFLICT",
        "Only a finished run can be re-scored",
    )
    require(draft_ids, "VALIDATION_FAILED", "Choose at least one draft")
    drafts = [get_draft(ctx.c, ctx.ws, d) for d in draft_ids]
    require(
        all(d["project_id"] == run["project_id"] for d in drafts),
        "VALIDATION_FAILED",
        "Drafts must belong to the run's project",
    )
    by = {}
    for d in drafts:
        require(
            d["criterion_id"] not in by, "VALIDATION_FAILED", f"Two drafts for {d['criterion_id']}"
        )
        by[d["criterion_id"]] = {**d["settings"], "draft_id": d["id"]}
    base = scoring.latest_pass(ctx.c, run_id)
    require(base, "CONFLICT", "The run has no scoring pass to compare with")
    manifest = runs._manifest_row(ctx, run_id)["manifest"]
    pass_row = scoring.create_pass(
        ctx.c, ctx.ws, run_id, "draft", base["evaluator_versions"], str(ctx.actor.id), draft=by
    )
    episodes = ctx.c.execute(
        "SELECT e.* FROM runs.episodes e JOIN runs.sealed_evidence s ON s.episode_id=e.id WHERE e.run_id=%s AND e.kind='case' ORDER BY e.id",
        (run_id,),
    ).fetchall()
    for e in episodes:
        scoring.score_episode(ctx.c, ctx.ws, e, pass_row, manifest)
    ctx.c.execute(
        "UPDATE scoring.scoring_passes SET finished_at=now() WHERE id=%s", (pass_row["id"],)
    )
    audit(
        ctx.c,
        ctx.ws,
        ctx.actor,
        "run.draft_rescored",
        run_id,
        None,
        {"pass": pass_row["pass"], "drafts": draft_ids, "base_pass": base["pass"]},
    )
    return compare(ctx.c, ctx.ws, run_id, pass_row["id"])


def compare(c, ws, run_id, draft_pass_id):
    """Side by side: the run's real latest pass vs a draft pass, per episode and criterion, with SME decisions."""
    from anvil.rlgym.scoring import service as scoring

    base = scoring.latest_pass(c, run_id)
    draft = c.execute(
        "SELECT * FROM scoring.scoring_passes WHERE id=%s AND run_id=%s AND reason='draft'",
        (draft_pass_id, run_id),
    ).fetchone()
    require(draft, "NOT_FOUND", "Draft pass not found")

    def verdicts(pass_id):
        out = {}
        for r in c.execute(
            "SELECT episode_id, criterion_id, verdict, points FROM scoring.criterion_receipts WHERE pass_id=%s",
            (pass_id,),
        ).fetchall():
            out[(r["episode_id"], r["criterion_id"])] = r
        return out

    a, b = verdicts(base["id"]), verdicts(draft["id"])
    scores = {}
    for pid, key in ((base["id"], "base"), (draft["id"], "draft")):
        for r in c.execute(
            "SELECT episode_id, score, passed FROM scoring.episode_scores WHERE pass_id=%s", (pid,)
        ).fetchall():
            scores.setdefault(r["episode_id"], {})[key] = {
                "score": r["score"],
                "passed": r["passed"],
            }
    sme = {}
    for r in c.execute(
        """SELECT i.episode_id, i.decision, i.criterion_id, i.review_verdict, i.rationale FROM results.sme_review_items i
           JOIN results.sme_review_batches b ON b.id=i.batch_id WHERE b.run_id=%s AND i.decision IS NOT NULL""",
        (run_id,),
    ).fetchall():
        sme.setdefault(r["episode_id"], []).append(r)
    criteria = sorted((draft.get("draft") or {}).keys())
    rows = []
    for (ep, cid), r in sorted(b.items()):
        if cid not in criteria:
            continue
        old = a.get((ep, cid))
        rows.append(
            {
                "episode_id": ep,
                "criterion_id": cid,
                "base": old and old["verdict"],
                "draft": r["verdict"],
                "changed": (old and old["verdict"]) != r["verdict"],
                "sme": [
                    {k: x[k] for k in ("decision", "criterion_id", "review_verdict", "rationale")}
                    for x in sme.get(ep, [])
                ],
            }
        )
    return {
        "run_id": run_id,
        "base_pass": base["pass"],
        "draft_pass": draft["pass"],
        "draft": draft.get("draft"),
        "criteria": criteria,
        "changed": sum(1 for r in rows if r["changed"]),
        "rows": rows,
        "scores": scores,
        "note": "A draft pass is an experiment: it never changes the run's reported score, the leaderboard or SME review.",
    }


def propose(ctx, draft_id, reason):
    ctx.actor.require_person()
    d = get_draft(ctx.c, ctx.ws, draft_id)
    require((reason or "").strip(), "VALIDATION_FAILED", "Give a reason")
    pid = "gp-" + uuid.uuid4().hex[:10]
    ctx.c.execute(
        """INSERT INTO catalog.grader_promotions(id,workspace_id,project_id,draft_id,configuration_id,criterion_id,proposed_by,reason)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            pid,
            ctx.ws,
            d["project_id"],
            draft_id,
            d["configuration_id"],
            d["criterion_id"],
            str(ctx.actor.id),
            reason.strip(),
        ),
    )
    audit(ctx.c, ctx.ws, ctx.actor, "grader.promotion_proposed", pid, reason, {"draft": draft_id})
    return ctx.c.execute(
        "SELECT * FROM catalog.grader_promotions WHERE workspace_id=%s AND id=%s", (ctx.ws, pid)
    ).fetchone()


def decide(ctx, promotion_id, approve, reason):
    """The second person (another RL Engineer or Admin; never the proposer) approves or rejects. Approval creates the
    fix version (qualified by its known-case tests) that carries the draft's overrides."""
    from anvil.rlgym.catalog import evaluators

    ctx.actor.require_person()
    require(
        ctx.actor.profile in APPROVERS,
        "FORBIDDEN",
        "Only an RL Engineer or Admin approves a grader",
    )
    p = ctx.c.execute(
        "SELECT * FROM catalog.grader_promotions WHERE workspace_id=%s AND id=%s",
        (ctx.ws, promotion_id),
    ).fetchone()
    require(p, "NOT_FOUND", "Proposal not found")
    require(p["state"] == "proposed", "CONFLICT", f"The proposal is {p['state']}")
    require(
        str(ctx.actor.id) != p["proposed_by"],
        "FORBIDDEN",
        "A different person approves (two-person rule)",
    )
    fix_version = None
    if approve:
        d = get_draft(ctx.c, ctx.ws, p["draft_id"])
        base = evaluators.get_version(ctx.c, ctx.ws, d["configuration_id"], d["base_version"])
        config = {k: v for k, v in (base["config"] or {}).items()}
        config["block_overrides"] = d["settings"].get("block_overrides") or {}
        if d["settings"].get("disabled_blocks"):
            config["disabled_blocks"] = d["settings"]["disabled_blocks"]
        out = evaluators.create_fix_version(
            ctx.c,
            ctx.ws,
            ctx.actor,
            d["configuration_id"],
            {
                "fix_of": d["base_version"],
                "config": config,
                "source": f"rlgym:E-004:{p['draft_id']}",
                "reason": f"E-004 grader draft {p['draft_id']} approved: {p['reason']}",
            },
        )
        fix_version = out["configuration"]["version"]
    ctx.c.execute(
        """UPDATE catalog.grader_promotions SET state=%s, decided_by=%s, decided_at=now(), decision_reason=%s, fix_version=%s
           WHERE workspace_id=%s AND id=%s""",
        (
            "approved" if approve else "rejected",
            str(ctx.actor.id),
            (reason or "").strip() or None,
            fix_version,
            ctx.ws,
            promotion_id,
        ),
    )
    audit(
        ctx.c,
        ctx.ws,
        ctx.actor,
        "grader.promotion_" + ("approved" if approve else "rejected"),
        promotion_id,
        reason,
        {"fix_version": fix_version},
    )
    return ctx.c.execute(
        "SELECT * FROM catalog.grader_promotions WHERE workspace_id=%s AND id=%s",
        (ctx.ws, promotion_id),
    ).fetchone()
