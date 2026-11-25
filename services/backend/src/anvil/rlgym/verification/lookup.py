"""G4 (E-011 §3; KYC Judgment v1 §10a.1): the no-AI lookup baseline for a suite version.

A fixed decision table over the case's records (no model, no reasoning) decides each case. Its decision is played
through the task's own procedure by the reference agent (the same tools, hidden IDs and steps a model gets) on one fresh
local instance of the bound environment, and the episode is scored by the project's graders against the case's TRUE
reference answers. If the lookup scores above the gate (default 60% of points, set per lookup run), the cases don't
need reasoning: a correct answer shows the model followed a rule. The verification row G-01 reports it (shadow mode).

Lookups are per environment (`LOOKUPS`, keyed by the version id without "@n"). An environment without one is not
measured (never a pass). Golden KYC's lookup is the literal table of @12's seven published rules, first match wins.
"""

import json
import time
import uuid

from psycopg.types.json import Jsonb

from anvil.rlgym import integrations
from anvil.rlgym.common import GymError, require, sha
from anvil.rlgym.runs import images, openenv

DEFAULT_THRESHOLD = 60
ID_KINDS = ("government_id", "passport")


def _golden_kyc(case_id, snap):
    """@12 KYC-01/GB-02 (identity), KYC-02/GB-02 (proof of address), GB-03 (minor's TIN), KYC-03/GB-05 (screening hit),
    KYC-04 (ready), read literally from the records; first match wins."""
    app = next(
        (a for a in snap.get("applications") or [] if a.get("application_id") == case_id), {}
    )
    parties = [p for p in snap.get("parties") or [] if p.get("application_id") == case_id]
    ids = {p.get("party_id") for p in parties}
    docs = [d for d in snap.get("documents") or [] if d.get("party_id") in ids]
    submitted = str(app.get("submitted_at") or "")[:10]

    def mine(p, kinds):
        return [
            d for d in docs if d.get("party_id") == p.get("party_id") and d.get("kind") in kinds
        ]

    def out(rt, rec, referral="none", issue="none", why=""):
        return {
            "request_type": rt,
            "recommendation": rec,
            "referral": referral,
            "screening_issue": issue,
            "reason_keyword": why,
        }

    for p in parties:
        idd = mine(p, ID_KINDS)
        if not idd or any(
            str((d.get("content") or {}).get("expires_on") or "9999")[:10] < submitted
            or (d.get("content") or {}).get("name_on_document") != p.get("full_name")
            for d in idd
        ):
            return out("id_document", "request_information", why="KYC-01: valid identity document")
    if not [d for d in docs if d.get("kind") == "proof_of_address"] or any(
        mine(p, ("passport",)) and not mine(p, ("proof_of_address",)) for p in parties
    ):
        return out("proof_of_address", "request_information", why="KYC-02: proof of address")
    for p in parties:
        if p.get("role") == "minor" and any(
            (d.get("content") or {}).get("tin") == "missing" for d in mine(p, ("government_id",))
        ):
            return out("tin", "request_information", why="GB-03: TIN")
    if [d for d in docs if d.get("kind") == "screening_result"]:
        return out(
            "none",
            "specialist_review",
            "sanctions",
            "sanctions_near_match",
            "DOB mismatch on sanctions hit",
        )
    return out("none", "ready_for_approval", why="KYC-04: all checks clear")


def _judgment_v2(case_id, snap):
    """KYC Judgment v1 (reference.v2 shape): the same literal table, first match wins, its one outcome given to the
    first party (or every party clear). It never reads a rule's conditions, a bulletin, citizenship or a risk factor:
    what a fixed lookup over one field would do."""
    d = _golden_kyc(case_id, snap)
    parties = [p for p in snap.get("parties") or [] if p.get("application_id") == case_id]
    outcome = "clear" if d["recommendation"] == "ready_for_approval" else d["recommendation"]
    target = parties[0]["party_id"] if parties else None
    return {
        "recommendation": d["recommendation"],
        "officer_verification": False,
        "risk_rating": {"required": False},
        "parties": [
            {
                "party_id": p["party_id"],
                "outcome": outcome if p["party_id"] == target else "clear",
                "requests": [d["request_type"]]
                if d["request_type"] != "none" and p["party_id"] == target
                else [],
                "referral": d["referral"]
                if d["referral"] != "none" and p["party_id"] == target
                else None,
            }
            for p in parties
        ],
        "rules_applied": [],
    }


LOOKUPS = {"golden-kyc-openenv": _golden_kyc, "kyc-judgment-openenv": _judgment_v2}
KEYS_V1 = ("request_type", "recommendation", "referral")


def _decision(d):
    """The comparable decision: v1 keys, or (reference.v2) the recommendation and each party's outcome, requests and
    referral."""
    if isinstance(d.get("parties"), list):
        return {
            "recommendation": d.get("recommendation"),
            "parties": sorted(
                [
                    p.get("party_id"),
                    p.get("outcome"),
                    sorted(p.get("requests") or []),
                    p.get("referral") or None,
                ]
                for p in d["parties"]
            ),
        }
    return {k: d.get(k) for k in KEYS_V1}


def lookup_for(environment_version_id):
    return LOOKUPS.get(str(environment_version_id or "").split("@")[0])


def threshold(body):
    v = (body or {}).get("threshold_percent", DEFAULT_THRESHOLD)
    require(
        isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 100,
        "VALIDATION_FAILED",
        "The lookup gate is a percentage from 0 to 100",
        field="threshold_percent",
    )
    return v


def _points(p):
    a, b = str(p).split("/")
    return float(a), float(b)


def summarize(rows, gate):
    got = sum(_points(r["points"])[0] for r in rows)
    top = sum(_points(r["points"])[1] for r in rows)
    pct = round(100 * got / top, 1) if top else None
    return {
        "cases": len(rows),
        "points_percent": pct,
        "full_marks": sum(1 for r in rows if r["full_marks"]),
        "decisions_right": sum(1 for r in rows if r["decision_right"]),
        "gate": {"threshold_percent": gate, "passed": pct is not None and pct <= gate},
    }


def run(c, ws, sv_id, requested_by, body=None):
    from anvil.rlgym.scoring import judgment
    from anvil.rlgym.verification import reference_run

    gate = threshold(body)
    sv, project, env, tasks = reference_run._context(c, ws, sv_id)
    decide = lookup_for(env["id"])
    require(
        decide,
        "CONFLICT",
        f"There is no lookup baseline for {env['id']} yet (it comes with the environment's lookup data)",
    )
    rec = openenv.recipe(env)
    image = openenv.check_image(env, rec)  # identity-checked local image: nothing built or pulled
    evaluators = reference_run._evaluators(c, ws, project)
    chosen = reference_run._cases(c, ws, sv_id, env, tasks)
    ids = sorted({cid for v in chosen.values() for cid in v})
    refs = {}
    for i in range(0, len(ids), 50):
        refs.update(
            integrations.registry_get(
                f"/versions/{env['id']}/references",
                params={"ids": ",".join(ids[i : i + 50])},
                audience="scorer",
                timeout=30,
                base=env.get("registry"),
            )["references"]
        )
    container, _ = openenv.start_instance(f"lookup-{uuid.uuid4().hex[:6]}", env, image)
    rows = []
    try:
        session = openenv.OpenEnvSession(container, rec, time.monotonic() + 3000)

        def snapshot():
            return session.request({"op": "snapshot"})["collections"]

        for t in tasks:
            for cid in chosen.get((t["task_id"], t["revision"]), []):
                truth = (refs.get(cid) or {}).get("reference")
                if not truth:
                    rows.append(
                        {"case_id": cid, "task_id": t["task_id"], "skipped": "no reference"}
                    )
                    continue
                wait = judgment.awaiting(truth, placeholder_ok=bool(project.get("test_only")))
                if wait:
                    rows.append({"case_id": cid, "task_id": t["task_id"], "skipped": wait[0]})
                    continue
                session.request({"op": "reset", "case_id": cid, "inject": None})
                said = decide(cid, snapshot())
                # The lookup's decision drives the procedure; the score is always against the true reference.
                ep = reference_run._episode(session, t["actor"], {**truth, **said}, cid, snapshot)
                score = reference_run._score(c, ws, project, evaluators, t, ep, truth)
                lookup_d, truth_d = _decision(said), _decision(truth)
                rows.append(
                    {
                        "case_id": cid,
                        "task_id": t["task_id"],
                        "lookup": lookup_d,
                        "truth": truth_d,
                        "decision_right": lookup_d == truth_d,
                        "points": score["points"],
                        "full_marks": score["full_marks"],
                        "not_passed": sorted(
                            k for k, v in score["verdicts"].items() if v["verdict"] != "pass"
                        ),
                    }
                )
        session.close()
    finally:
        images.stop_instance(container)
    scored = [r for r in rows if "skipped" not in r]
    if not scored:
        raise GymError(
            "CONFLICT", "No case of the suite's case set has a reference to score against"
        )
    report = {
        "suite_version_id": str(sv_id),
        "environment": env["id"],
        "lookup": f"{env['id'].split('@')[0]} decision table (no model)",
        "evaluators": [f"{e['configuration_id']} v{e['version']}" for e in evaluators],
        "judge": f"{reference_run.MOCK_JUDGE} (no live call)",
        "summary": summarize(scored, gate),
        "cases": rows,
    }
    lid = "lb-" + uuid.uuid4().hex[:12]
    c.execute(
        "INSERT INTO verification.lookup_runs(id,workspace_id,suite_version_id,report,report_sha256,requested_by) VALUES(%s,%s,%s,%s,%s,%s)",
        (
            lid,
            ws,
            sv_id,
            Jsonb(json.loads(json.dumps(report, default=str))),
            sha(report),
            requested_by,
        ),
    )
    return {"id": lid, **report}


def latest(c, ws, sv_id):
    r = c.execute(
        "SELECT * FROM verification.lookup_runs WHERE workspace_id=%s AND suite_version_id=%s ORDER BY created_at DESC LIMIT 1",
        (ws, sv_id),
    ).fetchone()
    return r and {"id": r["id"], "created_at": r["created_at"], **r["report"]}
