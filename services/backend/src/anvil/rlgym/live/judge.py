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

# Room for the verdict after the model's own reasoning: thinking models (Gemini 3.8 Flash, Claude 5.5) count reasoning
# tokens against the output limit, and at 200 half of the Gemini judge's answers were cut off before the JSON.
MAX_OUT = 1024
# D-037: the judge gives a score from 0 to 1, so the block's threshold (e.g. 0.7) decides pass or fail; a pass/fail
# answer gave only 1 or 0 and made any threshold meaningless.
JUDGE = (
    "You are a strict grader. Judge only the rubric below against the agent's output. Score how fully the output meets "
    "the rubric, from 0 (not at all) to 1 (completely), using two decimals. Reply with one JSON object and nothing "
    'else: {"score": <number from 0 to 1>, "reason": "<one sentence>"}.'
)
DEFAULT_THRESHOLD = 0.7


def score_of(answer):
    """The judge's score in [0, 1], or None when the answer has none. An old-style {"verdict": "pass"|"fail"} answer
    counts as 1 or 0 (recorded answers and known cases from before D-037)."""
    raw = answer.get("score")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool) and 0 <= raw <= 1:
        return float(raw)
    if isinstance(raw, str):
        try:
            v = float(raw)
        except ValueError:
            v = None
        if v is not None and 0 <= v <= 1:
            return v
    if answer.get("verdict") in ("pass", "fail"):
        return 1.0 if answer["verdict"] == "pass" else 0.0
    return None


def _texts(evidence):
    out = evidence.get("final_output") or {}
    parts = [json.dumps(out, default=str)[:4000]]
    for e in evidence.get("tool_events") or []:
        args = e.get("args") or {}
        parts += [str(args[k]) for k in ("text", "issue", "reason", "question") if args.get(k)]
    return "\n".join(parts)[:8000]


def record(prompt, done=None, note=None):
    """What the judge was asked and what it answered (D-008): kept with the block line's receipt, so a verdict can be
    checked against the exact prompt and the raw answer. The prompt holds the rubric and the agent's text only."""
    out = {"system": JUDGE, "prompt": prompt}
    if done is not None:
        out.update(
            raw=done.text,
            finish_reason=done.finish_reason,
            tokens_in=done.tokens_in,
            tokens_out=done.tokens_out,
            request_id=done.request_id,
        )
    if note:
        out["note"] = note
    return out


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
            out[b["id"]] = {
                "verdict": "blocked",
                "reason": "judge call not answered; not retried",
                "record": record(prompt, note="not answered"),
            }
            continue
        except GymError as exc:
            approvals.record(
                c, ws, a, "judge", "error", run_id=run_id, episode_id=episode_id, note=exc.message
            )
            out[b["id"]] = {
                "verdict": "blocked",
                "reason": exc.message,
                "record": record(prompt, note=exc.message),
            }
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
        score = score_of(answer)
        threshold = float(b.get("threshold", DEFAULT_THRESHOLD))
        verdict = "blocked" if score is None else ("pass" if score >= threshold else "fail")
        out[b["id"]] = {
            "verdict": verdict,
            "score": score,
            "threshold": threshold,
            "reason": str(answer.get("reason") or "unreadable judge answer")[:300],
            "judge": f"{judge['provider']}:{judge['model_id']}",
            "record": record(prompt, done),
        }
    return out


def answer_rubric(
    c,
    ws,
    model_id,
    rubric,
    text,
    *,
    run_id=None,
    episode_id=None,
    gateway_factory=None,
    threshold=DEFAULT_THRESHOLD,
):
    """One judge answer {pass, score, reason, judge} from the model named `model_id`, through the gateway, under an
    active approval for that model with use `judge`. None when live calls are off or no approval names the model (the
    plug-in then uses its mock judge and labels the line `mock`). When the approved judge was asked but gave no usable
    verdict (cap, unanswered, provider error, unreadable answer) → {"blocked": reason}: the line is blocked, never a
    fail and never silently re-judged by the mock."""
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
        return {"blocked": "the judge approval's cap would be crossed; not judged"}
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
        return {
            "blocked": "judge call not answered; not retried",
            "record": record(prompt, note="not answered"),
        }
    except GymError as exc:
        approvals.record(
            c, ws, a, "judge", "error", run_id=run_id, episode_id=episode_id, note=exc.message
        )
        return {
            "blocked": f"judge error: {exc.message}",
            "record": record(prompt, note=exc.message),
        }
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
    score = score_of(answer)
    if score is None:
        return {
            "blocked": f"unreadable judge answer (finish {done.finish_reason}, {done.tokens_out} output tokens)",
            "record": record(prompt, done),
        }
    # D-037: pass at the block's threshold; Promptfoo applies the same threshold to the same score.
    return {
        "pass": score >= float(threshold),
        "score": score,
        "threshold": float(threshold),
        "reason": str(answer.get("reason") or "unreadable judge answer")[:300],
        "judge": f"{a['provider']}:{a['model_id']}",
        "record": record(prompt, done),
    }
