"""G3 (part; E-011 §2): automatic tool-calling metrics, from an episode's trajectory (sealed tool events), its start
records and the case's reference answers. Read-only: served as a report drill-down, so it works on past runs and never
changes a stored report, a score or a pass.

Per episode:
- valid: calls that succeeded and were not blocked;
- required calls (KYC @12 rules): identity.check and screening.check for every party before the recommendation
  (KYC-01, KYC-03); the requested item from each party who lacks it (party rules 2, D-062; one party for proof of
  address; any party when the records can't show whose it is); the referral of the reference's specialty; one
  recommendation;
- wrong calls: a request the case doesn't need or of another type, a request to a party who has the item, a referral
  the case doesn't need or to another specialty, a second recommendation;
- polls: operation.read calls plus identical repeats of a call; a loop: the same call 4 or more times in a row;
- decision-bearing calls: finding.write, information.request, specialist.refer, recommend.
"""

import json

from anvil.rlgym.scoring.sandbox_runner import _case_parties, lacking

LOOP = 4
DECISION = ("finding.write", "information.request", "specialist.refer", "recommend")


def _none(v):
    return v in (None, "", "none")


def _key(e):
    return (e.get("tool"), json.dumps(e.get("args") or {}, sort_keys=True, default=str))


def episode_metrics(events, start, case_id, ref):
    events = [e for e in events or [] if isinstance(e, dict)]
    ref = ref or {}
    parties, docs, app = _case_parties(start or {}, case_id)
    pids = [p.get("party_id") for p in parties]
    ok = [e for e in events if e.get("ok", True) and not e.get("blocked")]
    first_rec = next(
        (i for i, e in enumerate(events) if e.get("tool") == "recommend" and e in ok), None
    )
    before = events[:first_rec] if first_rec is not None else events

    def made(tool, **want):
        return any(
            e.get("tool") == tool
            and e in ok
            and all((e.get("args") or {}).get(k) == v for k, v in want.items())
            for e in before
        )

    required, missed = 0, []
    for check in ("identity.check", "screening.check"):
        for pid in pids:
            required += 1
            if not made(check, party_id=pid):
                missed.append(f"{check} for {pid} before recommend")
    rt, referral = ref.get("request_type"), ref.get("referral")
    should = None
    requests = [e for e in events if e.get("tool") == "information.request" and e in ok]
    if not _none(rt):
        should = lacking(rt, parties, docs, app, rules=2)
        targets = sorted(should) if should else []
        if rt == "proof_of_address" and targets:
            required += 1
            if not any(made("information.request", type=rt, party_id=p) for p in targets):
                missed.append(f"information.request {rt} to one of {targets}")
        elif targets:
            for p in targets:
                required += 1
                if not made("information.request", type=rt, party_id=p):
                    missed.append(f"information.request {rt} to {p}")
        else:
            required += 1
            if not made("information.request", type=rt):
                missed.append(f"information.request {rt}")
    if not _none(referral):
        required += 1
        if not made("specialist.refer", specialty=referral):
            missed.append(f"specialist.refer {referral}")
    required += 1
    if first_rec is None:
        missed.append("recommend")

    wrong = []
    for e in requests:
        a = e.get("args") or {}
        if _none(rt) or a.get("type") != rt:
            wrong.append({"kind": "unneeded_request", "args": a})
        elif should and a.get("party_id") not in should:
            wrong.append({"kind": "request_to_party_with_item", "args": a})
    for e in (e for e in events if e.get("tool") == "specialist.refer" and e in ok):
        a = e.get("args") or {}
        if _none(referral):
            wrong.append({"kind": "unneeded_referral", "args": a})
        elif a.get("specialty") != referral:
            wrong.append({"kind": "wrong_specialty", "args": a})
    recs = [e for e in events if e.get("tool") == "recommend" and e in ok]
    wrong += [{"kind": "second_recommendation", "args": e.get("args") or {}} for e in recs[1:]]

    seen, polls, run, loop, last = set(), 0, 0, False, None
    for e in events:
        k = _key(e)
        if e.get("tool") == "operation.read" or k in seen:
            polls += 1
        seen.add(k)
        run = run + 1 if k == last else 1
        last = k
        loop = loop or run >= LOOP
    return {
        "calls": len(events),
        "valid": len(ok),
        "required": required,
        "required_made": required - len(missed),
        "missed": missed,
        "wrong": wrong,
        "polls": polls,
        "loop": loop,
        "decision_bearing": sum(1 for e in events if e.get("tool") in DECISION),
        "party_determinable": None if should is None else bool(should),
    }


def summarize(rows):
    out = {}
    for r in rows:
        s = out.setdefault(
            r["system_id"],
            {
                "episodes": 0,
                "calls": 0,
                "valid": 0,
                "required": 0,
                "required_made": 0,
                "wrong_calls": 0,
                "episodes_with_wrong_call": 0,
                "polls": 0,
                "episodes_with_loop": 0,
                "decision_bearing": 0,
            },
        )
        s["episodes"] += 1
        for k in ("calls", "valid", "required", "required_made", "polls", "decision_bearing"):
            s[k] += r[k]
        s["wrong_calls"] += len(r["wrong"])
        s["episodes_with_wrong_call"] += 1 if r["wrong"] else 0
        s["episodes_with_loop"] += 1 if r["loop"] else 0
    for s in out.values():
        s["valid_rate"] = round(s["valid"] / s["calls"], 4) if s["calls"] else None
        s["required_made_rate"] = (
            round(s["required_made"] / s["required"], 4) if s["required"] else None
        )
        s["decision_bearing_share"] = (
            round(s["decision_bearing"] / s["calls"], 4) if s["calls"] else None
        )
        s["calls_per_episode"] = round(s["calls"] / s["episodes"], 2)
        s["polls_per_episode"] = round(s["polls"] / s["episodes"], 2)
    return out


def tool_calling(d):
    """The drill-down for a run report: per model, the metrics over its case episodes, and each episode's misses and
    wrong calls. References are read for counting only; nothing reaches an agent."""
    env = (d.manifest.get("environment") or {}).get("version_id")
    refs = {
        r["case_id"]: r["reference"]
        for r in d.c.execute(
            "SELECT case_id, reference FROM scoring.case_references WHERE workspace_id=%s AND environment_version_id=%s",
            (d.ws, env),
        ).fetchall()
    }
    rows, episodes = [], []
    for e in d.cases:
        bundle = d.bundle(e)
        if not bundle or e["case_id"] not in refs:
            continue
        m = episode_metrics(
            bundle.get("tool_events"),
            (bundle.get("snapshots") or {}).get("start"),
            e["case_id"],
            refs[e["case_id"]],
        )
        rows.append({"system_id": e["system_id"], **m})
        if m["missed"] or m["wrong"] or m["loop"]:
            episodes.append(
                {
                    "episode_id": e["id"],
                    "model": d.name(e["system_id"]),
                    "case_id": e["case_id"],
                    "missed": m["missed"],
                    "wrong": m["wrong"],
                    "loop": m["loop"],
                    "polls": m["polls"],
                }
            )
    per_model = summarize(rows)
    return {
        "note": (
            "Tool-calling metrics from the sealed trajectories (E-011 §2), read-only. Required calls: identity and "
            "screening checks for every party before the recommendation, the request to each party lacking the item "
            "(party rules 2), the reference's referral, one recommendation."
        ),
        "models": [
            {"system_id": sid, "name": d.name(sid), **vals} for sid, vals in per_model.items()
        ],
        "episodes": episodes,
        "measured": len(rows),
        "not_measured": len(d.cases) - len(rows),
    }
