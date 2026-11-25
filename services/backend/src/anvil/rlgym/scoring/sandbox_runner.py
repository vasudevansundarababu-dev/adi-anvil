"""Sandboxed Python evaluator runtime (framework `python` 1.0.0). Standalone: imports nothing from Anvil.

Reads one JSON job on stdin: {"config": {...}, "evidence": {...}, "reference": {...}} and writes one JSON verdict on
stdout. It runs in an isolated interpreter (python -I) with an empty environment, CPU and time limits. The reference
(private) is visible here, in the scoring sandbox, and never to the candidate.

Verdicts: pass, partial, fail, blocked (required evidence missing).
"""

import json
import sys


def _missing(evidence, section):
    return section not in evidence or evidence[section] is None


def _tool_count(events, tool):
    return sum(
        1 for e in events if isinstance(e, dict) and e.get("tool") == tool and e.get("ok", True)
    )


def check(rule, evidence, reference):
    kind = rule.get("kind")
    out = evidence.get("final_output") or {}
    events = evidence.get("tool_events") or []
    if kind == "tool_called":
        need = (
            int(reference.get(rule["min_count_reference"], 1))
            if rule.get("min_count_reference")
            else int(rule.get("min_count", 1))
        )
        have = _tool_count(events, rule["tool"])
        return have >= need, f"{rule['tool']} called {have} of {need} times"
    if kind == "tool_not_called":
        have = _tool_count(events, rule["tool"])
        return have == 0, f"{rule['tool']} called {have} times (must be 0)"
    if kind == "output_equals":
        if rule["field"] not in out:
            return None, f"final output has no {rule['field']}"
        expected = reference.get(rule["reference"])
        return out[rule["field"]] == expected, f"{rule['field']} = {out[rule['field']]!r}"
    if kind == "output_set_equals":
        if rule["field"] not in out or not isinstance(out[rule["field"]], list):
            return None, f"final output has no list {rule['field']}"
        expected = set(map(str, reference.get(rule["reference"], [])))
        return set(
            map(str, out[rule["field"]])
        ) == expected, f"{rule['field']} = {sorted(map(str, out[rule['field']]))}"
    if kind == "output_nonempty":
        if rule["field"] not in out:
            return None, f"final output has no {rule['field']}"
        return bool(
            out[rule["field"]]
        ), f"{rule['field']} has {len(out[rule['field']] or [])} entries"
    raise ValueError(f"unknown rule kind {kind}")


# --- verifier blocks (adi.verifier-blocks.v1, runner_version 1) ------------------------------------------------------

MISSING = object()
STATE_OPS = (
    "equals",
    "in",
    "contains",
    "exists_where",
    "not_exists",
    "count",
    "changed",
    "unchanged",
    "nothing_else_changed",
)
NEEDS_START = ("changed", "unchanged", "nothing_else_changed")
NEEDS_VALUE = ("equals", "in", "contains", "count")
RUDE = ("stupid", "idiot", "shut up", "worthless")


def _resolve(value, ctx):
    """An open value: fixed, from the case's private reference_answers, or from an SME slot (decided by the template's
    expected_values_from). Returns MISSING when it is not available; that block is then blocked, never passed."""
    if value is None:
        return None
    if not isinstance(value, dict):
        return value
    if "fixed" in value:
        return value["fixed"]
    if ctx["expected_values_from"] == "case_reference" and value.get("case_reference"):
        path = value["case_reference"]
        field = path.split(".", 1)[1] if path.startswith("reference_answers.") else path
        ref = ctx["reference"].get("reference_answers") or ctx["reference"]
        return ref.get(field, MISSING)
    if ctx["expected_values_from"] == "sme" and value.get("slot") is not None:
        slot = value["slot"]
        sid = slot.get("id") if isinstance(slot, dict) else slot
        return (ctx["slots"] or {}).get(sid, MISSING)
    return MISSING


def _rows(snapshot, block, ctx):
    rows = (snapshot or {}).get(block["table"]) or []
    if block.get("row", "case") == "case":
        rows = [
            r for r in rows if isinstance(r, dict) and r.get("application_id") == ctx["case_id"]
        ]
    return rows


def _state(block, ctx):
    snaps = ctx["snapshots"]
    end, start = snaps.get("end"), snaps.get("start")
    op = block["op"]
    if end is None or (op in NEEDS_START and start is None):
        return "blocked", None, "no snapshot"
    expected = _resolve(block.get("value"), ctx)
    if expected is MISSING or (op in NEEDS_VALUE and expected is None):
        return "blocked", None, "expected value missing"
    col = block.get("column")
    if op == "nothing_else_changed":
        allowed = set(block.get("allow") or []) | set(ctx["criterion_tables"])
        names = sorted(set(start) | set(end))
        changed = [t for t in names if t not in allowed and start.get(t) != end.get(t)]
        return ("pass" if not changed else "fail"), {"changed_tables": changed}, expected
    rows = _rows(end, block, ctx)
    if op in ("changed", "unchanged"):
        same = _rows(start, block, ctx) == rows
        ok = (not same) if op == "changed" else same
        return ("pass" if ok else "fail"), {"rows": len(rows), "same_as_start": same}, expected
    if op == "count":
        return ("pass" if len(rows) == int(expected) else "fail"), len(rows), expected
    if op == "exists_where":
        if col and expected in (None, "none"):
            # The reference says nothing of this kind is expected for this case (Studio writes "none"): pass only
            # when no row has a value in the column.
            present = [r.get(col) for r in rows if r.get(col) not in (None, "")]
            return ("pass" if not present else "fail"), present, expected
        ok = bool(rows) if not col else any(r.get(col) == expected for r in rows)
        return (
            ("pass" if ok else "fail"),
            [r.get(col) for r in rows] if col else len(rows),
            expected,
        )
    if op == "not_exists":
        if not col:
            ok = not rows
        elif expected is None:
            ok = not any(r.get(col) not in (None, "") for r in rows)
        else:
            ok = not any(r.get(col) == expected for r in rows)
        return (
            ("pass" if ok else "fail"),
            [r.get(col) for r in rows] if col else len(rows),
            expected,
        )
    if not rows:
        return "fail", None, expected
    if op == "contains":
        # Any in-scope row matches (Studio's preview: `col ILIKE '%' || :value || '%'`): a text value contains the
        # expected text ignoring case; a list value holds it as a member.
        values = [r.get(col) for r in rows]
        return ("pass" if any(_contains(v, expected) for v in values) else "fail"), values, expected
    actual = rows[-1].get(col)  # the latest write wins
    if op == "equals":
        ok = actual == expected
    else:  # in
        ok = actual in (expected or [])
    return ("pass" if ok else "fail"), actual, expected


def _contains(actual, expected):
    if isinstance(actual, str):
        return str(expected).casefold() in actual.casefold()
    if isinstance(actual, list):
        return expected in actual
    return False


def _args_ok(event, wanted, ctx):
    args = event.get("args") or {}
    for name, spec in (wanted or {}).items():
        # "$case" or the evidence path "case.application_id" both mean the episode's case.
        expected = (
            ctx["case_id"] if spec in ("$case", "case.application_id") else _resolve(spec, ctx)
        )
        if expected is MISSING or args.get(name) != expected:
            return False
    return True


def _process(block, ctx):
    events = ctx["events"]
    if events is None:
        return "blocked", None, "no tool log"
    tool = block["must_call"]
    calls = [
        i
        for i, e in enumerate(events)
        if e.get("tool") == tool and e.get("ok", True) and _args_ok(e, block.get("args_match"), ctx)
    ]
    ok = bool(calls)

    def first(name):
        return next((i for i, e in enumerate(events) if e.get("tool") == name), None)

    before = first(block["before"]) if block.get("before") else None
    after = first(block["after"]) if block.get("after") else None
    if ok and block.get("before") and before is not None:
        ok = calls[0] < before
    if ok and block.get("after"):
        ok = after is not None and any(i > after for i in calls)
    actual = {"calls": len(calls), "first_call": calls[0] if calls else None}
    if block.get("before"):
        actual["first_" + block["before"]] = before
    if block.get("after"):
        actual["first_" + block["after"]] = after
    expected = {
        "must_call": tool,
        **{k: block[k] for k in ("before", "after", "args_match") if block.get(k)},
    }
    return ("pass" if ok else "fail"), actual, expected


def _texts(ctx):
    out = ctx["final_output"] or {}
    texts = [str(v) for v in out.values() if isinstance(v, str)]
    for f in out.get("findings") or []:
        if isinstance(f, dict):
            texts.append(str(f.get("text") or f.get("issue") or ""))
    for e in ctx["events"] or []:
        args = e.get("args") or {}
        texts += [str(args[k]) for k in ("text", "issue", "reason", "question") if args.get(k)]
    return texts


def _rubric(block, ctx):
    """The local mock judge (no model is called). Deterministic per rubric id; a real Promptfoo judge replaces it."""
    rid = block["rubric_id"]
    given = (ctx.get("rubric_verdicts") or {}).get(block["id"])
    if (
        given is not None
    ):  # a live judge's verdict, computed outside the sandbox (behind an approval)
        return given["verdict"], {"reason": given.get("reason"), "judge": given.get("judge")}, rid
    if ctx["final_output"] is None and ctx["events"] is None:
        return "blocked", None, "no output"
    texts = _texts(ctx)
    if rid == "customer_tone_polite":
        bad = [t for t in texts if any(w in t.lower() for w in RUDE)]
        return ("pass" if not bad else "fail"), {"impolite": bad[:3]}, "no impolite wording"
    if rid == "reason_is_specific":
        best = max((len(t) for t in texts), default=0)
        return (
            ("pass" if best >= 12 else "fail"),
            {"longest_reason": best},
            "a reason of 12+ characters",
        )
    if rid == "evidence_cited":
        cited = [
            f
            for f in (ctx["final_output"] or {}).get("findings") or []
            if isinstance(f, dict) and (f.get("evidence_ref") or f.get("evidence_ids"))
        ] + [
            e
            for e in ctx["events"] or []
            if (e.get("args") or {}).get("evidence_ref")
            or (e.get("args") or {}).get("evidence_ids")
        ]
        return (
            ("pass" if cited else "fail"),
            {"citations": len(cited)},
            "at least one cited evidence item",
        )
    raise ValueError(f"unknown rubric {rid}")


# --- RL Gym-owned checks (runner_version 2: the template's blocks plus `config.extra_blocks`) ---------------------
# D-041: an information request must go to the party whose record lacks the item. Which party lacks it is read from
# the case's start state, with the rules Studio's generator uses for each edge case (golden-kyc edge-case recipes):
# a TIN marked missing on a party's document, a government ID that expired before the application was submitted, a
# party whose only documents are passports (no proof of address). A request type with no rule here is not checked.
ADDRESS_KINDS = ("proof_of_address", "utility_bill", "bank_statement", "lease", "council_tax_bill")
ID_KINDS = ("government_id", "passport", "drivers_licence", "drivers_license", "driver_license")


def _case_parties(snapshot, case_id):
    parties = [
        p
        for p in (snapshot or {}).get("parties") or []
        if isinstance(p, dict) and p.get("application_id") == case_id
    ]
    ids = {p.get("party_id") for p in parties}
    docs = [
        d
        for d in (snapshot or {}).get("documents") or []
        if isinstance(d, dict) and d.get("party_id") in ids
    ]
    app = next(
        (
            a
            for a in (snapshot or {}).get("applications") or []
            if isinstance(a, dict) and a.get("application_id") == case_id
        ),
        {},
    )
    return parties, docs, app


def lacking(request_type, parties, docs, app, rules=1):
    """The party ids whose record lacks what `request_type` asks for, or None when no rule covers the type.
    `rules` 2 (D-062) reads id_document as @12's KYC-01 and GB-02 state it: a party whose identity document shows a
    different name or expired before submission, or who has no identity document. Rules 1 is D-041 as written."""

    def content(d):
        return d.get("content") if isinstance(d.get("content"), dict) else {}

    by_party = {
        p.get("party_id"): [d for d in docs if d.get("party_id") == p.get("party_id")]
        for p in parties
    }
    if request_type == "tin":
        marked = {
            pid
            for pid, ds in by_party.items()
            if any(
                "tin" in content(d) and content(d).get("tin") in (None, "", "missing") for d in ds
            )
        }
        if marked:
            return marked
        # No document marks it: the minors with no TIN on any document.
        return {
            p.get("party_id")
            for p in parties
            if p.get("role") == "minor"
            and not any(
                content(d).get("tin") not in (None, "", "missing")
                for d in by_party[p.get("party_id")]
            )
        }
    if request_type == "id_document" and rules >= 2:
        submitted = str(app.get("submitted_at") or "")[:10]
        names = {p.get("party_id"): p.get("full_name") for p in parties}
        out = set()
        for pid, ds in by_party.items():
            ids_ = [d for d in ds if d.get("kind") in ID_KINDS]
            if not ids_:
                out.add(pid)
            for d in ids_:
                c = content(d)
                expired = bool(
                    c.get("expires_on") and submitted and str(c["expires_on"])[:10] < submitted
                )
                other_name = bool(
                    c.get("name_on_document")
                    and names.get(pid)
                    and c["name_on_document"] != names[pid]
                )
                if expired or other_name:
                    out.add(pid)
        return out
    if request_type == "id_document":
        submitted = str(app.get("submitted_at") or "")[:10]
        expired = {
            pid
            for pid, ds in by_party.items()
            if any(
                d.get("kind") in ID_KINDS
                and content(d).get("expires_on")
                and submitted
                and str(content(d)["expires_on"])[:10] < submitted
                for d in ds
            )
        }
        if expired:
            return expired
        return {
            pid for pid, ds in by_party.items() if not any(d.get("kind") in ID_KINDS for d in ds)
        }
    if request_type == "proof_of_address":
        return {
            pid
            for pid, ds in by_party.items()
            # A party with documents but no proof of address (@8: only a passport; @9: also a screening result).
            if ds and not any(d.get("kind") in ADDRESS_KINDS for d in ds)
        }
    return None


def _request_party(block, ctx):
    ref = ctx["reference"].get("reference_answers") or ctx["reference"]
    wanted = ref.get("request_type", MISSING)
    if wanted is MISSING:
        return "blocked", None, "expected request type missing"
    if wanted in (None, "", "none"):
        return "pass", "no request expected", None
    snaps = ctx["snapshots"]
    if snaps.get("start") is None or snaps.get("end") is None:
        return "blocked", None, "no snapshot"
    parties, docs, app = _case_parties(snaps["start"], ctx["case_id"])
    rules = int(block.get("party_rules") or 1)
    should = lacking(wanted, parties, docs, app, rules)
    if should is None:
        return "pass", f"no party rule for request type {wanted}", None
    asked = [
        r.get("party_id")
        for r in (snaps["end"].get("information_requests") or [])
        if isinstance(r, dict) and r.get("type") == wanted
    ]
    if not should:
        if rules >= 2:
            # D-062: the records don't show whose item it is; the party is never guessed, the type check decides.
            return (
                "pass",
                {"requested_for": asked},
                f"party not determinable from the start records for {wanted} (type checked only)",
            )
        return "blocked", None, f"the case's start state shows no party lacking {wanted}"
    if rules >= 2:
        # D-062: every party lacking an ID or a TIN is asked (per-party rules); proof of address is per application,
        # so one lacking party is enough. A request of that type to a party who has the item is a wrong call.
        wrong = sorted({p for p in asked if p not in should})
        if wanted == "proof_of_address":
            ok = any(p in should for p in asked)
        else:
            ok = should <= set(asked)
        actual = {"requested_for": asked, **({"wrong_party": wrong} if wrong else {})}
        return ("pass" if ok and not wrong else "fail"), actual, {"party_lacking": sorted(should)}
    ok = any(pid in should for pid in asked)
    return ("pass" if ok else "fail"), {"requested_for": asked}, {"party_lacking": sorted(should)}


def _recommended(block, ctx):
    """D-042: a check ordered "before recommend" must not pass when the agent never recommended. Passes when a
    recommend call succeeded or the end state holds a recommendation."""
    events, end = ctx["events"], (ctx["snapshots"] or {}).get("end")
    if events is None and end is None:
        return "blocked", None, "no tool log and no end state"
    called = any(e.get("tool") == "recommend" and e.get("ok", True) for e in events or [])
    recorded = bool([r for r in (end or {}).get("recommendations") or [] if isinstance(r, dict)])
    return (
        ("pass" if called or recorded else "fail"),
        {"recommend_called": called, "recorded": recorded},
        "a recommendation",
    )


def run_blocks(job):
    evidence = job.get("evidence") or {}
    blocks = job.get("blocks") or []
    if (job.get("config") or {}).get("runner_version", 1) >= 2:
        blocks = [*blocks, *((job.get("config") or {}).get("extra_blocks") or [])]
    if not blocks:
        return {
            "verdict": "error",
            "points": None,
            "detail": ["no verifier blocks"],
            "block_lines": [],
        }
    snapshots = evidence.get("snapshots") or {}
    ctx = {
        "case_id": job.get("case_id"),
        "reference": job.get("reference") or {},
        "slots": job.get("slots") or {},
        "expected_values_from": job.get("expected_values_from") or "case_reference",
        "snapshots": {"start": snapshots.get("start"), "end": snapshots.get("end")},
        "events": evidence.get("tool_events"),
        "final_output": evidence.get("final_output"),
        "rubric_verdicts": job.get("rubric_verdicts") or {},
        "criterion_tables": sorted(
            {
                b["table"]
                for b in blocks
                if b.get("kind") == "state" and b.get("table") not in (None, "", "*")
            }
        ),
    }
    lines, detail = [], []
    share_total, earned_share = 0.0, 0.0
    given = None
    for b in blocks:
        kind = b.get("kind") or ("plugin" if b.get("plugin") else None)
        if kind == "plugin":
            # A verifier plug-in's result line (run outside this sandbox by the generic plug-in runner, D22).
            given = (job.get("plugin_results") or {}).get(b["id"])
            if given is None:
                verdict, actual, expected = "blocked", None, "plug-in did not run"
            else:
                verdict, actual, expected = (
                    given["verdict"],
                    given.get("actual"),
                    given.get("expected"),
                )
            if b.get("share_percent"):
                share = float(b["share_percent"])
                share_total += share
                if verdict == "pass":
                    earned_share += share
        elif kind == "state":
            verdict, actual, expected = _state(b, ctx)
        elif kind == "process":
            verdict, actual, expected = _process(b, ctx)
        elif kind == "request_party":
            verdict, actual, expected = _request_party(b, ctx)
        elif kind == "recommended":
            verdict, actual, expected = _recommended(b, ctx)
        elif kind == "rubric":
            verdict, actual, expected = _rubric(b, ctx)
            share = float(b.get("share_percent") or 0)
            share_total += share
            if verdict == "pass":
                earned_share += share
        else:
            raise ValueError(f"unknown block kind {kind}")
        if verdict == "blocked" and kind != "plugin":
            actual, expected = {"missing": expected}, None
        elif verdict == "blocked" and given is None:
            actual, expected = {"missing": expected}, None
        lines.append(
            {
                "block_id": b["id"],
                "kind": kind,
                "expected": expected,
                "actual": actual,
                "verdict": verdict,
                "on_fail": b.get("on_fail"),
            }
        )
        mark = {"pass": "✓", "fail": "✕", "blocked": "…"}[verdict]
        detail.append(f"{mark} {b['id']}: expected {expected!r}, actual {actual!r}")
    if any(line["verdict"] == "blocked" for line in lines):
        return {"verdict": "blocked", "points": None, "detail": detail, "block_lines": lines}
    shared = {
        b["id"]
        for b in blocks
        if b.get("kind") == "rubric" or (b.get("plugin") and b.get("share_percent"))
    }
    if any(line["verdict"] == "fail" and line["block_id"] not in shared for line in lines):
        return {"verdict": "fail", "points": 0.0, "detail": detail, "block_lines": lines}
    points = round((100 - share_total + earned_share) / 100, 4) if share_total <= 100 else 0.0
    verdict = "pass" if points >= 1 else "partial"
    return {"verdict": verdict, "points": points, "detail": detail, "block_lines": lines}


def evaluate(job):
    if (job.get("config") or {}).get("runner") == "verifier_blocks":
        if job["config"].get("runner_version", 1) not in (1, 2):
            raise ValueError(
                f"unknown verifier-blocks runner version {job['config'].get('runner_version')}"
            )
        return run_blocks(job)
    config, evidence, reference = (
        job["config"],
        job.get("evidence") or {},
        job.get("reference") or {},
    )
    section = config.get("evidence")
    if section and _missing(evidence, section):
        return {
            "verdict": "blocked",
            "points": None,
            "detail": [f"required evidence '{section}' is missing"],
        }
    results, detail = [], []
    for rule in config.get("rules", []):
        ok, note = check(rule, evidence, reference)
        if ok is None:
            return {"verdict": "blocked", "points": None, "detail": [note]}
        results.append(ok)
        detail.append(("✓ " if ok else "✕ ") + note)
    if all(results):
        verdict = "pass"
    elif any(results) and config.get("allow_partial"):
        verdict = "partial"
    else:
        verdict = "fail"
    fraction = sum(results) / len(results) if results else 0
    return {"verdict": verdict, "points": round(fraction, 4), "detail": detail}


def _safe(job):
    try:
        return evaluate(job)
    except Exception as exc:  # a broken configuration is an evaluator defect, never a pass
        return {"verdict": "error", "points": None, "detail": [f"{type(exc).__name__}: {exc}"]}


def main():
    job = json.loads(sys.stdin.read())
    # A batch is several configurations of the same framework version over one episode's evidence; each gets its own
    # verdict, and one configuration's error never changes another's.
    if "jobs" in job:
        sys.stdout.write(json.dumps([_safe(j) for j in job["jobs"]]))
        return
    sys.stdout.write(json.dumps(_safe(job)))


if __name__ == "__main__":
    main()
