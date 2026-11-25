"""G2 (KYC Judgment v1 §6, §15.2): graders as pure functions.

- `rules_applied`: the output's `rules_applied` against the rules whose conditions the case's facts trigger (from the
  whole library, the version in force at the recommend call). Exact set → pass; one rule missing or extra, or one wrong
  "governs" mark, with the decision right → partial; otherwise fail. A cited version older than the one in force is
  "stale" (after a bulletin, the new version is used).
- `expected_rules`: those rules, as of the recommend call's sequence (the episode clock is the call sequence, C3).
- `audit_faithfulness`: every `data_seen` id was returned to the agent by a successful call (anything else is invented
  evidence: critical); every `facts_learnt` value is in the cited record; every cited rule was read through policy.read
  and applies.
Precedence waits for the reference shape (RL Gym review B2). Nothing here reads the database or changes a score; a new
evaluator version wires it in.
"""

from anvil.rlgym.runs import library


def _entries(transcript):
    """Each call as (tool, sequence, ok, ids returned, records returned), from RL Gym's sealed transcript
    ({tool, observation}) or Studio's runtime transcript ({operation_id, sequence, state, record_ids}). A call
    rejected before it ran has no sequence; ids count only from calls that returned data."""
    out = []
    for t in transcript or []:
        if not isinstance(t, dict):
            continue
        if "observation" in t or "tool" in t:
            obs = t.get("observation") or {}
            seq = obs.get("sequence") if obs.get("sequence") is not None else t.get("sequence")
            recs = ((obs.get("output") or {}).get("records") or []) if obs.get("ok") else []
            ids = []
            _ids_into(recs, ids)
            out.append((t.get("tool"), seq, bool(obs.get("ok")), ids, recs))
        else:
            ok = t.get("state") in ("completed", "pending")
            ids = list(t.get("record_ids") or []) if ok else []
            out.append((t.get("operation_id"), t.get("sequence"), ok, ids, []))
    return out


def _ids_into(value, out):
    if isinstance(value, dict):
        for k, v in value.items():
            if (k == "id" or k.endswith("_id")) and isinstance(v, str):
                out.append(v)
            _ids_into(v, out)
    elif isinstance(value, list):
        for v in value:
            _ids_into(v, out)


def _events(events):
    """Tool events as (tool, args, reached): RL Gym's ({tool, args, ok, blocked}) or Studio's ({tool, arguments, ok}).
    A call counts as made when it reached the operation (a pending check is ok: false but ran); a blocked one didn't."""
    return [
        (
            e.get("tool"),
            e.get("args") if e.get("args") is not None else (e.get("arguments") or {}),
            not e.get("blocked"),
        )
        for e in events or []
        if isinstance(e, dict)
    ]


def _key(r):
    return (r.get("rule_id"), int(r.get("version") or 0))


def recommend_sequence(transcript):
    """The sequence of the first successful recommend call, else one past the last call. Studio's clock: only calls
    that reached an operation carry a sequence; calls rejected before running (schema, undeclared tool, past the limit)
    never count. Never the transcript index."""
    last = 0
    for tool, raw, ok, _ids, _recs in _entries(transcript):
        if raw is None:
            continue
        seq = int(raw)
        last = max(last, seq)
        if tool == "recommend" and ok:
            return seq
    return last + 1


def expected_rules(lib, case, fired, transcript, submitted_at=None):
    return library.applicable(
        lib,
        case,
        fired=fired,
        as_of_sequence=recommend_sequence(transcript),
        submitted_at=submitted_at,
    )["applies"]


def rules_applied(expected, got, governs_truth, decision_right):
    exp = {_key(e) for e in expected or []}
    have = {_key(g) for g in got or [] if isinstance(g, dict)}
    missing = sorted(exp - have)
    extra = sorted(have - exp)
    exp_ids = {r for r, _ in exp}
    stale = [{"rule_id": r, "version": n} for r, n in extra if r in exp_ids]
    governs_wrong, governs_note = [], None
    if governs_truth is None:
        governs_note = "not graded: no reference for which rule governs"
    else:
        marks = {_key(g): bool(g.get("governs")) for g in got or [] if isinstance(g, dict)}
        for t in governs_truth:
            k = _key(t)
            if k in marks and marks[k] != bool(t.get("governs")):
                governs_wrong.append(
                    {"rule_id": k[0], "version": k[1], "expected": bool(t.get("governs"))}
                )
    off = len(missing) + len(extra) + len(governs_wrong)
    verdict = "pass" if off == 0 else "partial" if off == 1 and decision_right else "fail"
    return {
        "verdict": verdict,
        "missing": [{"rule_id": r, "version": n} for r, n in missing],
        "extra": [{"rule_id": r, "version": n} for r, n in extra],
        "stale": stale,
        "governs_wrong": governs_wrong,
        **({"governs": governs_note} if governs_note else {}),
    }


def _ids(value, out):
    if isinstance(value, dict):
        for k, v in value.items():
            if (k == "id" or k.endswith("_id")) and isinstance(v, str):
                out.add(v)
            _ids(v, out)
    elif isinstance(value, list):
        for v in value:
            _ids(v, out)


def _scalars(value, out):
    if isinstance(value, dict):
        for v in value.values():
            _scalars(v, out)
    elif isinstance(value, list):
        for v in value:
            _scalars(v, out)
    elif value is not None:
        out.add(str(value))


def audit_faithfulness(trail, transcript, aliases, expected):
    """Checks the final output's audit trail against what the agent was actually given (RL Gym's sealed transcript:
    real ids; the agent writes the ids it saw, mapped back through the episode's aliases)."""
    back = {alias: real for real, alias in (aliases or {}).items()}
    seen, records, read, read_ids = set(), {}, set(), set()
    for tool, _seq, ok, ids, recs in _entries(transcript):
        if not ok:
            continue
        seen.update(ids)
        for r in recs:
            if not isinstance(r, dict):
                continue
            for k, v in r.items():
                if (k == "id" or k.endswith("_id")) and isinstance(v, str):
                    records.setdefault(v, r)
            if tool == "policy.read" and r.get("rule_id"):
                read.add(_key(r))
        if tool == "policy.read":
            # Studio's transcript names the rule ids returned (no versions): a rule read is read at its version.
            read_ids.update(i for i in ids if isinstance(i, str))
    applies = {_key(e) for e in expected or []}
    out = {"invented": [], "fact_mismatches": [], "rules_not_read": [], "rules_not_applicable": []}
    for e in trail or []:
        step = e.get("sop_step")
        for d in e.get("data_seen") or []:
            if isinstance(d, dict):
                if _key(d) not in read and d.get("rule_id") not in read_ids:
                    out["invented"].append(
                        {"sop_step": step, "id": f"{d.get('rule_id')}@v{d.get('version')}"}
                    )
            elif back.get(d, d) not in seen:
                out["invented"].append({"sop_step": step, "id": d})
        for f in e.get("facts_learnt") or []:
            ev = back.get(f.get("evidence"), f.get("evidence"))
            rec = records.get(ev)
            if rec is None and ev in seen:
                continue  # returned, but its content isn't in this transcript: the id is what's checkable
            vals = set()
            _scalars(rec, vals)
            if rec is None or str(f.get("value")) not in vals:
                out["fact_mismatches"].append(
                    {
                        "sop_step": step,
                        "fact": f.get("fact"),
                        "value": f.get("value"),
                        "evidence": f.get("evidence"),
                    }
                )
        for r in e.get("rules_applied") or []:
            k = _key(r)
            if k not in read and k[0] not in read_ids:
                out["rules_not_read"].append({"sop_step": step, "rule_id": k[0], "version": k[1]})
            if k not in applies:
                out["rules_not_applicable"].append(
                    {"sop_step": step, "rule_id": k[0], "version": k[1]}
                )
    out["critical"] = bool(out["invented"])
    return out


# --- one check per verifier line (computed by the scoring service outside the sandbox, like a plug-in) -----------------


# reference.v2 statuses that mean "not graded yet": the SME decides, or the reference rests on a placeholder rule the PM
# hasn't approved.
AWAITING = ("awaiting_sme", "awaiting_pm")


def awaiting(ref, placeholder_ok=False):
    """(status, reasons) when the reference isn't gradable, else None. Studio ab1f684: a reference with gradable=false
    (its rules' conditions aren't PM-approved) is never graded in a real project. `placeholder_ok` (a test-only
    project's run, manifest placeholder_graded) grades it as if the placeholders were approved; awaiting_sme never is."""
    ref = ref or {}
    sme = ref.get("status") == "awaiting_sme" or ref.get("awaiting_sme") is True
    if sme:
        reasons = ref.get("awaiting_sme") if isinstance(ref.get("awaiting_sme"), list) else []
        return "awaiting_sme", reasons or ["awaiting sme"]
    if placeholder_ok:
        return None
    for status in AWAITING:
        if ref.get("status") == status or ref.get(status) is True:
            reasons = ref.get(status) if isinstance(ref.get(status), list) else []
            return status, reasons or [status.replace("_", " ")]
    if ref.get("gradable") is False:
        return "awaiting_pm", ["the rules' conditions aren't PM-approved yet (gradable: false)"]
    return None


def _line(verdict, actual=None, expected=None, critical=False):
    return {"verdict": verdict, "actual": actual, "expected": expected, "critical": critical}


def _real(aliases, value):
    back = {alias: real for real, alias in (aliases or {}).items()}
    return back.get(value, value)


def evaluate(check, x):
    """One KYC Judgment check. x: {library, case, fired, transcript, aliases, final, reference (v2)}. Verdicts: pass,
    partial, fail, not_applicable (excluded from points and maximum), blocked (evidence or truth missing; never a
    pass). `critical`: invented evidence fails the task whatever its total (§15.4)."""
    ref, final = x.get("reference"), x.get("final") or {}
    if ref is None:
        return _line("blocked", expected="the case's reference answers (reference.v2)")
    if check == "tool_calls" and x.get("tool_events") is None:
        return _line("blocked", expected="the episode's tool calls")
    if check != "tool_calls" and x.get("final") is None:
        return _line("blocked", expected="the agent's final output")
    wait = awaiting(ref, x.get("placeholder_ok"))
    if wait:
        return _line("not_applicable", expected={wait[0]: wait[1]})
    fired = [
        f
        for f in x.get("fired") or []
        if (f.get("published_at_sequence") or 0) < recommend_sequence(x.get("transcript"))
    ]
    if not fired and isinstance(ref.get("reference_if_not_fired"), dict):
        # A rule-change case whose bulletin never fired before the decision: the answer without the change.
        ref = ref["reference_if_not_fired"]
    if check == "rules_applied":
        if ref.get("rules_applied") is not None:
            # Studio's reference (computed from the same conditions, with the bulletin's version when it fired).
            exp = [r for r in ref["rules_applied"] if isinstance(r, dict)]
        elif x.get("library") and x.get("case"):
            exp = expected_rules(x["library"], x["case"], x.get("fired"), x.get("transcript"))
        else:
            return _line("blocked", expected="the reference's rules or the pinned policy library")
        # governs comes only from the SME's outcome; null (no overlap decided yet) is not graded.
        truth = [r for r in ref.get("rules_applied") or [] if r.get("governs") is not None]
        out = rules_applied(
            exp,
            final.get("rules_applied"),
            truth or None,
            final.get("recommendation") == ref.get("recommendation"),
        )
        return _line(
            out["verdict"],
            {k: out[k] for k in ("missing", "extra", "stale", "governs_wrong")},
            [{"rule_id": e["rule_id"], "version": e["version"]} for e in exp],
        )
    if check == "rule_in_force":
        if not fired:
            return _line("not_applicable", expected="no bulletin was published in this episode")
        cited = {
            g.get("rule_id"): int(g.get("version") or 0)
            for g in final.get("rules_applied") or []
            if isinstance(g, dict)
        }
        stale = [
            {"rule_id": f["rule_id"], "cited": cited[f["rule_id"]], "in_force": f["to_version"]}
            for f in fired
            if f["rule_id"] in cited and cited[f["rule_id"]] != f["to_version"]
        ]
        considered = set(final.get("notices_considered") or [])
        missed = [
            f["notice_id"] for f in fired if f.get("notice_id") and f["notice_id"] not in considered
        ]
        ok = not stale and not missed
        return _line(
            "pass" if ok else "fail",
            {"stale": stale, "notices_missed": missed},
            {
                "in_force": {f["rule_id"]: f["to_version"] for f in fired},
                "notices": [f.get("notice_id") for f in fired],
            },
        )
    if check == "audit_faithfulness":
        trail = final.get("audit_trail")
        if not isinstance(trail, list) or not trail:
            return _line("fail", {"audit_trail": None}, "an audit trail, one entry per SOP step")
        exp = (
            expected_rules(x["library"], x["case"], x.get("fired"), x.get("transcript"))
            if x.get("library") and x.get("case")
            else []
        )
        out = audit_faithfulness(trail, x.get("transcript"), x.get("aliases"), exp)
        bad = out["invented"] or out["fact_mismatches"] or out["rules_not_read"]
        return _line(
            "fail" if bad else "pass",
            {k: v for k, v in out.items() if k != "critical" and v},
            "every id seen, every fact as recorded, every rule read",
            critical=out["critical"],
        )
    if check == "risk_rating":
        rr = ref.get("risk_rating")
        if rr is None:
            return _line("blocked", expected="the reference's risk rating")
        given = final.get("risk_rating") if isinstance(final.get("risk_rating"), dict) else None
        if not rr.get("required"):
            if given and given.get("level"):
                return _line(
                    "fail", {"risk_rating": given}, "no risk rating (not required for this account)"
                )
            return _line("not_applicable", expected="no risk rating required for this account")
        level = (given or {}).get("level")
        problems = []
        if level != rr.get("level"):
            problems.append(f"level {level!r}, expected {rr.get('level')!r}")
        if rr.get("level") == "medium" and not (
            final.get("recommendation") == "ready_for_approval"
            and final.get("officer_verification") is True
        ):
            problems.append("medium risk: ready_for_approval with the officer verification flag")
        if rr.get("level") == "high":
            referrals = {
                a.get("referral") for a in final.get("assessments") or [] if isinstance(a, dict)
            }
            if final.get("recommendation") != "specialist_review" or "edd" not in referrals:
                problems.append("high risk: an edd referral and specialist_review, no approval")
        return _line(
            "fail" if problems else "pass", {"risk_rating": given, "problems": problems}, rr
        )
    if check == "decision":
        if final.get("recommendation") != ref.get("recommendation"):
            return _line(
                "fail",
                {"recommendation": final.get("recommendation")},
                {"recommendation": ref.get("recommendation")},
            )
        got = {
            _real(x.get("aliases"), a.get("party_id")): a
            for a in final.get("assessments") or []
            if isinstance(a, dict)
        }
        off = []
        if bool(final.get("officer_verification")) != bool(ref.get("officer_verification")):
            off.append("officer_verification")
        for p in ref.get("parties") or []:
            a = got.get(p["party_id"]) or {}
            if a.get("outcome") != p.get("outcome"):
                off.append(f"{p['party_id']}: outcome")
            if set(a.get("requests") or []) != set(p.get("requests") or []):
                off.append(f"{p['party_id']}: requests")
            if (a.get("referral") or None) != (p.get("referral") or None):
                off.append(f"{p['party_id']}: referral")
        verdict = "pass" if not off else "partial" if len(off) == 1 else "fail"
        return _line(
            verdict,
            {"off": off},
            {
                "parties": ref.get("parties"),
                "officer_verification": ref.get("officer_verification"),
            },
        )
    parties = {
        _real(x.get("aliases"), a.get("party_id")): a
        for a in final.get("assessments") or []
        if isinstance(a, dict)
    }
    if check == "tool_calls":
        ran = [(t, a) for t, a, reached in _events(x["tool_events"]) if reached]
        rec_i = next((i for i, (t, _a) in enumerate(ran) if t == "recommend"), None)
        before = ran if rec_i is None else ran[:rec_i]

        def match(a, k, v):
            got = _real(x.get("aliases"), a.get(k))
            # documentary is identity.check's default method
            return got == v or (k == "method" and v == "documentary" and got is None)

        def made(tool, **want):
            return any(
                t == tool and all(match(a, k, v) for k, v in want.items()) for t, a in before
            )

        methods = ref.get("identity_methods") or {}
        missed, wrong = [], []
        for p in ref.get("parties") or []:
            pid = p["party_id"]
            want = {"party_id": pid, **({"method": methods[pid]} if methods.get(pid) else {})}
            if not made("identity.check", **want):
                missed.append(
                    f"identity.check {pid}" + (f" ({methods[pid]})" if methods.get(pid) else "")
                )
            if not made("screening.check", party_id=pid):
                missed.append(f"screening.check {pid}")
            for item in p.get("requests") or []:
                if not made("information.request", party_id=pid, type=item):
                    missed.append(f"information.request {item} to {pid}")
            if p.get("referral") and not made("specialist.refer", specialty=p["referral"]):
                missed.append(f"specialist.refer {p['referral']}")
        if rec_i is None:
            missed.append("recommend")
        asked = {
            (p["party_id"], r) for p in ref.get("parties") or [] for r in p.get("requests") or []
        }
        referrals = {p.get("referral") for p in ref.get("parties") or [] if p.get("referral")}
        for tool, a in ran:
            if (
                tool == "information.request"
                and (_real(x.get("aliases"), a.get("party_id")), a.get("type")) not in asked
            ):
                wrong.append(f"information.request {a.get('type')} to {a.get('party_id')}")
            if tool == "specialist.refer" and a.get("specialty") not in referrals:
                wrong.append(f"specialist.refer {a.get('specialty')}")
        wrong += ["a second recommend"] * max(0, sum(1 for t, _a in ran if t == "recommend") - 1)
        # Rubric: every required check for every party is a pass condition, so a missed required call fails; one
        # wrong or unneeded call (nothing missed) is partial.
        verdict = "fail" if missed or len(wrong) > 1 else "partial" if wrong else "pass"
        return _line(verdict, {"missed": missed, "wrong": wrong})
    if check == "procedure_output":
        problems = []
        if final.get("recommendation") not in (
            "ready_for_approval",
            "request_information",
            "specialist_review",
        ):
            problems.append("recommendation is not one of the three decision values")
        if not (isinstance(final.get("rules_applied"), list) and final["rules_applied"]):
            problems.append("rules_applied is empty")
        missing_parties = [
            p["party_id"] for p in ref.get("parties") or [] if p["party_id"] not in parties
        ]
        if missing_parties:
            problems.append(f"no assessment for {', '.join(missing_parties)}")
        for key, kind in (
            ("notices_considered", list),
            ("audit_trail", list),
            ("officer_verification", bool),
            ("risk_rating", dict),
            ("rationale", str),
        ):
            if not isinstance(final.get(key), kind):
                problems.append(f"{key} is missing")
        return _line("fail" if problems else "pass", {"problems": problems}, "the output contract")
    if check == "evidence_judgment":
        off = []
        for p in ref.get("parties") or []:
            a = parties.get(p["party_id"]) or {}
            # Attributed to the party by an issue, a non-clear outcome, a request or a referral.
            has = bool(a.get("issues") or a.get("requests") or a.get("referral")) or (
                a.get("outcome") not in (None, "clear")
            )
            should = p.get("outcome") != "clear"
            if has != should:
                off.append(
                    f"{p['party_id']}: {'issue not found' if should else 'issue on a clear party'}"
                )
        return _line("pass" if not off else "partial" if len(off) == 1 else "fail", {"off": off})
    if check == "consistency":
        outcomes = [a.get("outcome") for a in parties.values()]
        rated_high = ((final.get("risk_rating") or {}).get("level")) == "high"
        if (
            "specialist_review" in outcomes
            or any(a.get("referral") for a in parties.values())
            or rated_high
        ):
            implied = "specialist_review"
        elif "request_information" in outcomes or any(a.get("requests") for a in parties.values()):
            implied = "request_information"
        else:
            implied = "ready_for_approval"
        ok = final.get("recommendation") == implied
        return _line(
            "pass" if ok else "fail",
            {"recommendation": final.get("recommendation")},
            {"implied_by_assessments": implied},
        )
    if check == "rationale":
        text = str(final.get("rationale") or "")
        rec = str(final.get("recommendation") or "")
        names = bool(rec) and (rec in text or rec.replace("_", " ") in text.lower())
        cites = any(
            str(r.get("rule_id")) in text
            for r in final.get("rules_applied") or []
            if isinstance(r, dict)
        )
        n = int(names) + int(cites)
        return _line(
            "pass" if n == 2 else "partial" if n == 1 else "fail",
            {
                "names_the_recommendation": names,
                "cites_a_rule": cites,
                "judge": "deterministic local judge (no model)",
            },
        )
    if check == "process_adherence":
        mandatory = ref.get("mandatory_steps") or x.get("mandatory_steps")
        if not mandatory:
            return _line(
                "not_applicable",
                expected="the case's mandatory SOP steps aren't known (reference.v2 mandatory_steps)",
            )
        mandatory = [str(s) for s in mandatory]
        entries = [e for e in final.get("audit_trail") or [] if isinstance(e, dict)]
        done = [str(e.get("sop_step")) for e in entries if e.get("status") == "done"]
        missing = [s for s in mandatory if s not in done]
        seen = [s for s in done if s in mandatory]
        order = [mandatory.index(s) for s in seen]
        out_of_order = order != sorted(order)
        return _line(
            "fail" if missing or out_of_order else "pass",
            {"missing": missing, "out_of_order": out_of_order},
            {"mandatory_steps": mandatory},
        )
    if check == "missing_facts":
        truth = ref.get("facts_missing")
        if truth is None:
            return _line(
                "not_applicable", expected="the reference doesn't list the case's missing facts yet"
            )
        stated = {
            (_real(x.get("aliases"), m.get("party") or m.get("party_id")), m.get("fact"))
            for e in final.get("audit_trail") or []
            if isinstance(e, dict)
            for m in e.get("facts_missing") or []
            if isinstance(m, dict)
        }
        want = {(m.get("party_id"), m.get("fact")) for m in truth}
        lacking = sorted(want - stated)
        return _line("fail" if lacking else "pass", {"not_stated": lacking}, sorted(want))
    raise ValueError(f"unknown judgment check {check}")


def combine(lines):
    """A criterion's verdict from its lines (the runner applies the same rule): all not applicable → not applicable;
    any blocked → blocked; a critical fail → fail (critical); any fail → fail; any partial → partial; else pass."""
    vs = [ln["verdict"] for ln in lines.values()]
    critical = any(ln.get("critical") and ln["verdict"] == "fail" for ln in lines.values())
    if vs and all(v == "not_applicable" for v in vs):
        verdict = "not_applicable"
    elif "blocked" in vs:
        verdict = "blocked"
    elif "fail" in vs:
        verdict = "fail"
    elif "partial" in vs:
        verdict = "partial"
    else:
        verdict = "pass"
    return {"verdict": verdict, "critical": critical, "lines": lines}


def grade(criterion, x):
    """One rubric criterion of the activation bridge (grader kyc-judgment.g2.<criterion>)."""
    from anvil.rlgym.catalog import judgment_configs

    return combine(
        {f"{criterion}.{c}": evaluate(c, x) for c in judgment_configs.GRADERS[criterion]}
    )
