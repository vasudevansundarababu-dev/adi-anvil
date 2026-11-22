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
    actual = rows[-1].get(col)  # the latest write wins
    if op == "equals":
        ok = actual == expected
    elif op == "in":
        ok = actual in (expected or [])
    else:  # contains
        ok = expected in actual if isinstance(actual, (str, list)) else False
    return ("pass" if ok else "fail"), actual, expected


def _args_ok(event, wanted, ctx):
    args = event.get("args") or {}
    for name, spec in (wanted or {}).items():
        expected = ctx["case_id"] if spec == "$case" else _resolve(spec, ctx)
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


def run_blocks(job):
    evidence = job.get("evidence") or {}
    blocks = job.get("blocks") or []
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
    for b in blocks:
        kind = b["kind"]
        if kind == "state":
            verdict, actual, expected = _state(b, ctx)
        elif kind == "process":
            verdict, actual, expected = _process(b, ctx)
        elif kind == "rubric":
            verdict, actual, expected = _rubric(b, ctx)
            share = float(b.get("share_percent") or 0)
            share_total += share
            if verdict == "pass":
                earned_share += share
        else:
            raise ValueError(f"unknown block kind {kind}")
        if verdict == "blocked":
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
    if any(line["verdict"] == "fail" and line["kind"] != "rubric" for line in lines):
        return {"verdict": "fail", "points": 0.0, "detail": detail, "block_lines": lines}
    points = round((100 - share_total + earned_share) / 100, 4) if share_total <= 100 else 0.0
    verdict = "pass" if points >= 1 else "partial"
    return {"verdict": verdict, "points": points, "detail": detail, "block_lines": lines}


def evaluate(job):
    if (job.get("config") or {}).get("runner") == "verifier_blocks":
        if job["config"].get("runner_version", 1) != 1:
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
