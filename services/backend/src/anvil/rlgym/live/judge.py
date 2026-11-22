"""Live judge models for Rubric verifier blocks (behind an approval; the mock judge stays the default).

A verifier-blocks configuration may name a judge, `config.judge = {"provider", "model_id", "hf_revision"?,
"serving"?}`. The scorer then asks that model for each Rubric block's verdict, outside the sandbox (the sandbox has
no network), and passes the verdicts in. Without the live flag or a matching approval (use `judge`), the block is
`blocked`, never silently judged by the mock. Every judge call is recorded against the approval and stops at its caps.
"""

import json

from anvil.rlgym.catalog.verifier import RUBRICS
from anvil.rlgym.common import GymError
from anvil.rlgym.live import approvals
from anvil.rlgym.live.gateway import Ambiguous, live_enabled, parse_json

MAX_OUT = 200
JUDGE = (
    "You are a strict grader. Judge only the rubric below against the agent's output. Reply with one JSON object and "
    'nothing else: {"verdict": "pass" or "fail", "reason": "<one sentence>"}.'
)


def _texts(evidence):
    out = evidence.get("final_output") or {}
    parts = [json.dumps(out, default=str)[:4000]]
    for e in evidence.get("tool_events") or []:
        args = e.get("args") or {}
        parts += [str(args[k]) for k in ("text", "issue", "reason", "question") if args.get(k)]
    return "\n".join(parts)[:8000]


def rubric_verdicts(
    c, ws, judge, blocks, evidence, *, run_id=None, episode_id=None, gateway_factory=None
):
    rubrics = [b for b in blocks if b.get("kind") == "rubric"]
    if not rubrics:
        return {}

    def blocked(reason):
        return {b["id"]: {"verdict": "blocked", "reason": reason} for b in rubrics}

    if not live_enabled() and gateway_factory is None:
        return blocked("live judge not enabled (ANVIL_LIVE_PROVIDERS_ENABLED)")
    a = approvals.find(
        c, ws, judge["provider"], judge["model_id"], "judge", judge.get("hf_revision")
    )
    if not a:
        return blocked(f"no active live approval for judge {judge['provider']} {judge['model_id']}")
    if gateway_factory is None:
        from anvil.rlgym.live.gateway import Gateway

        gateway_factory = Gateway
    gw = gateway_factory()
    described = {r["rubric_id"]: r for r in RUBRICS}
    out = {}
    for b in rubrics:
        rubric = described.get(b["rubric_id"], {"title": b["rubric_id"], "description": ""})
        prompt = f"Rubric: {rubric['title']}. {rubric['description']}\n\nAgent output:\n{_texts(evidence)}"
        worst = approvals.max_cost(a, len(prompt) // 3 + 100, MAX_OUT)
        if not approvals.room(c, ws, a, run_id, worst):
            out[b["id"]] = {
                "verdict": "blocked",
                "reason": "the judge approval's cap would be crossed",
            }
            continue
        try:
            done = gw.complete(
                judge["provider"],
                judge["model_id"],
                [{"role": "system", "content": JUDGE}, {"role": "user", "content": prompt}],
                max_output_tokens=MAX_OUT,
                temperature=0,
                serving=judge.get("serving"),
                hf_revision=judge.get("hf_revision"),
            )
        except Ambiguous as exc:
            approvals.record(
                c,
                ws,
                a,
                "judge",
                "ambiguous",
                cost=worst,
                run_id=run_id,
                episode_id=episode_id,
                note=exc.message,
            )
            out[b["id"]] = {"verdict": "blocked", "reason": "judge call not answered; not retried"}
            continue
        except GymError as exc:
            approvals.record(
                c, ws, a, "judge", "error", run_id=run_id, episode_id=episode_id, note=exc.message
            )
            out[b["id"]] = {"verdict": "blocked", "reason": exc.message}
            continue
        cost = done.cost(a["price_in_per_mtok_usd"], a["price_out_per_mtok_usd"])
        approvals.record(
            c,
            ws,
            a,
            "judge",
            "ok",
            completion=done,
            cost=cost,
            run_id=run_id,
            episode_id=episode_id,
        )
        answer = parse_json(done.text) or {}
        verdict = answer.get("verdict") if answer.get("verdict") in ("pass", "fail") else "blocked"
        out[b["id"]] = {
            "verdict": verdict,
            "reason": str(answer.get("reason") or "unreadable judge answer")[:300],
            "judge": f"{judge['provider']}:{judge['model_id']}",
        }
    return out


def answer_rubric(
    c, ws, model_id, rubric, text, *, run_id=None, episode_id=None, gateway_factory=None
):
    """One judge answer {pass, score, reason, judge} from the model named `model_id`, through the gateway, under an
    active approval for that model with use `judge`; None when there is none (the plug-in then uses its mock judge
    and labels the line `mock`)."""
    if not live_enabled() and gateway_factory is None:
        return None
    a = c.execute(
        """SELECT * FROM systems.live_approvals WHERE workspace_id=%s AND model_id=%s AND 'judge' = ANY(uses)
             AND revoked_at IS NULL AND expires_at > now() ORDER BY approved_at DESC LIMIT 1""",
        (ws, model_id),
    ).fetchone()
    if not a:
        return None
    prompt = f"Rubric: {rubric}\n\nText to grade:\n{str(text)[:8000]}"
    worst = approvals.max_cost(a, len(prompt) // 3 + 100, MAX_OUT)
    if not approvals.room(c, ws, a, run_id, worst):
        return {
            "pass": False,
            "score": 0,
            "reason": "judge cap would be crossed; not judged",
            "judge": "none",
        }
    if gateway_factory is None:
        from anvil.rlgym.live.gateway import Gateway

        gateway_factory = Gateway
    try:
        done = gateway_factory().complete(
            a["provider"],
            a["model_id"],
            [{"role": "system", "content": JUDGE}, {"role": "user", "content": prompt}],
            max_output_tokens=MAX_OUT,
            temperature=0,
        )
    except Ambiguous as exc:
        approvals.record(
            c,
            ws,
            a,
            "judge",
            "ambiguous",
            cost=worst,
            run_id=run_id,
            episode_id=episode_id,
            note=exc.message,
        )
        return None
    except GymError as exc:
        approvals.record(
            c, ws, a, "judge", "error", run_id=run_id, episode_id=episode_id, note=exc.message
        )
        return None
    approvals.record(
        c,
        ws,
        a,
        "judge",
        "ok",
        completion=done,
        cost=done.cost(a["price_in_per_mtok_usd"], a["price_out_per_mtok_usd"]),
        run_id=run_id,
        episode_id=episode_id,
    )
    answer = parse_json(done.text) or {}
    verdict = answer.get("verdict")
    return {
        "pass": verdict == "pass",
        "score": 1 if verdict == "pass" else 0,
        "reason": str(answer.get("reason") or "unreadable judge answer")[:300],
        "judge": f"{a['provider']}:{a['model_id']}",
    }
