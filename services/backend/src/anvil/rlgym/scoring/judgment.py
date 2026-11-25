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


# --- sanctions screening (expert, BANK-OPERATING-RULES-DRAFT §5c) ------------------------------------------------------


def _name(n):
    parts = str(n or "").lower().split()
    return (parts[0], parts[-1]) if parts else ("", "")


def screening_differs(party, listed):
    """The identifiers (name, date_of_birth, country) on which a list record differs from the party's records."""
    out = set()
    if _name(listed.get("listed_name")) != _name(party.get("full_name")):
        out.add("name")
    if listed.get("listed_date_of_birth") not in (None, party.get("date_of_birth")):
        out.add("date_of_birth")
    if listed.get("listed_country") not in (None, *(party.get("citizenships") or [])):
        out.add("country")
    return out


def is_possible_match(differs):
    """2 of 3 identifiers match and the name is one of them: refer to a sanctions analyst."""
    return "name" not in differs and len(differs) <= 1


def screening_truth(ref):
    """{party_id: "possible_match" | "false_positive"} from reference.v2 (parties[].screening.result, or the issues)."""
    out = {}
    for p in (ref or {}).get("parties") or []:
        scr = p.get("screening") if isinstance(p.get("screening"), dict) else {}
        if scr.get("result") in ("possible_match", "false_positive"):
            out[p["party_id"]] = scr["result"]
    for i in (ref or {}).get("issues") or []:
        if not isinstance(i, dict) or i.get("party_id") in out:
            continue
        if i.get("issue") == "possible_match":
            out[i["party_id"]] = "possible_match"
        elif i.get("issue") in ("false_positive", "screening_false_positive", "cleared_near_match"):
            out[i["party_id"]] = "false_positive"
    return out


def _agent_screen(a):
    s = a.get("screening") if isinstance(a.get("screening"), dict) else {}
    if s.get("result") == "false_positive":
        return "false_positive"
    if a.get("referral") == "sanctions" or s.get("result") == "possible_match":
        return "possible_match"
    return None


def _dismissal_problems(final, transcript, aliases):
    """Each false-positive dismissal must name the identifiers that differ, and each must differ in the records the
    agent was given. Records without content (Studio's runtime transcript) can't be checked: skipped."""
    people, lists = {}, {}
    for _tool, _seq, ok, _ids, recs in _entries(transcript):
        for r in recs if ok else []:
            if not isinstance(r, dict):
                continue
            if r.get("party_id") and r.get("full_name"):
                people[r["party_id"]] = r
            if r.get("kind") == "screening_result" and r.get("party_id"):
                lists.setdefault(r["party_id"], []).append(r.get("content") or {})
    problems = []
    for a in final.get("assessments") or []:
        if not isinstance(a, dict):
            continue
        s = a.get("screening") if isinstance(a.get("screening"), dict) else {}
        if s.get("result") != "false_positive":
            continue
        pid = _real(aliases, a.get("party_id"))
        claimed = set(s.get("identifiers_differ") or [])
        if not claimed:
            problems.append(
                {"party_id": pid, "problem": "a dismissal must name the identifiers that differ"}
            )
            continue
        if pid not in people or pid not in lists:
            continue
        actual = set().union(*(screening_differs(people[pid], ln) for ln in lists[pid]))
        wrong = sorted(claimed - actual)
        if wrong:
            problems.append(
                {
                    "party_id": pid,
                    "problem": f"these don't differ in the records: {', '.join(wrong)}",
                }
            )
    return problems


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


# The decision values (spec §13: not_eligible added 25 Nov 2026).
NOT_ELIGIBLE = "not_eligible"
DECISIONS = ("ready_for_approval", "request_information", "specialist_review", NOT_ELIGIBLE)


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
    # Owner, 25 Nov 2026: a rule-change case is always graded against its fired (post-bulletin) truth; the trigger is
    # the first documents.list, so an agent that never reaches it has failed the work. reference_if_not_fired is
    # diagnostics only (G-02).
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
        # §5c: a false-positive dismissal names the identifiers that differ, each as in the records.
        out["dismissals_unfaithful"] = _dismissal_problems(
            final, x.get("transcript"), x.get("aliases")
        )
        bad = (
            out["invented"]
            or out["fact_mismatches"]
            or out["rules_not_read"]
            or out["dismissals_unfaithful"]
        )
        return _line(
            "fail" if bad else "pass",
            {k: v for k, v in out.items() if k != "critical" and v},
            "every id seen, every fact as recorded, every rule read",
            critical=out["critical"],
        )
    if check in ("risk_rating", "risk_rating_5e"):
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
        # Spec §13: an ineligible account is not opened, so the approval / referral path a risk level asks for doesn't
        # apply when the reference and the agent both say not_eligible (the level itself is still graded).
        ineligible = final.get("recommendation") == ref.get("recommendation") == NOT_ELIGIBLE
        assessed = [a for a in final.get("assessments") or [] if isinstance(a, dict)]
        referrals = {a.get("referral") for a in assessed}
        # BANK-OPERATING-RULES-DRAFT §5e.2/5e.4 (fix version 3, "rule": "5e"): missing information takes precedence:
        # with a request outstanding the recommendation is request_information (an EDD referral is still made).
        asking = check == "risk_rating_5e" and any(
            a.get("outcome") == "request_information" or a.get("requests") for a in assessed
        )
        if asking and not ineligible:
            if final.get("recommendation") != "request_information":
                problems.append("a request is outstanding: request_information comes first (§5e)")
            if rr.get("level") == "high" and "edd" not in referrals:
                problems.append("high risk: the edd referral is made (§5e.4)")
        elif (
            not ineligible
            and rr.get("level") == "medium"
            and not (
                final.get("recommendation") == "ready_for_approval"
                and final.get("officer_verification") is True
            )
        ):
            problems.append("medium risk: ready_for_approval with the officer verification flag")
        if not ineligible and not asking and rr.get("level") == "high":
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
        truth_screen = screening_truth(ref)
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
            elif (
                tool == "specialist.refer"
                and a.get("specialty") == "sanctions"
                and truth_screen.get(_real(x.get("aliases"), a.get("party_id"))) == "false_positive"
            ):
                wrong.append(
                    f"specialist.refer sanctions on a false positive ({a.get('party_id')})"
                )
        wrong += ["a second recommend"] * max(0, sum(1 for t, _a in ran if t == "recommend") - 1)
        # Rubric: every required check for every party is a pass condition, so a missed required call fails; one
        # wrong or unneeded call (nothing missed) is partial.
        verdict = "fail" if missed or len(wrong) > 1 else "partial" if wrong else "pass"
        return _line(verdict, {"missed": missed, "wrong": wrong})
    if check == "procedure_output":
        problems = []
        if final.get("recommendation") not in DECISIONS:
            problems.append("recommendation is not one of the four decision values")
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
        # §5c: a near miss read as a match, or a match read as a false positive, fails outright.
        misread = []
        for pid, truth in screening_truth(ref).items():
            got = _agent_screen(parties.get(pid) or {})
            if (truth == "possible_match") != (got == "possible_match"):
                misread.append(
                    f"{pid}: {truth.replace('_', ' ')} read as {(got or 'nothing').replace('_', ' ')}"
                )
        verdict = (
            "fail" if misread else "pass" if not off else "partial" if len(off) == 1 else "fail"
        )
        return _line(verdict, {"off": off, "screening_misread": misread})
    if check in ("consistency", "consistency_5e") and NOT_ELIGIBLE in (
        final.get("recommendation"),
        ref.get("recommendation"),
    ):
        # Spec §13: not_eligible is consistent exactly when the reference says not_eligible.
        ok = final.get("recommendation") == ref.get("recommendation") == NOT_ELIGIBLE
        return _line(
            "pass" if ok else "fail",
            {"recommendation": final.get("recommendation")},
            {"reference": ref.get("recommendation")},
        )
    if check in ("consistency", "consistency_5e"):
        outcomes = [a.get("outcome") for a in parties.values()]
        rated_high = ((final.get("risk_rating") or {}).get("level")) == "high"
        escalate = (
            "specialist_review" in outcomes
            or any(a.get("referral") for a in parties.values())
            or rated_high
        )
        asking = "request_information" in outcomes or any(
            a.get("requests") for a in parties.values()
        )
        if check == "consistency_5e" and asking:
            # BANK-OPERATING-RULES-DRAFT §5e.2/5e.4: missing information takes precedence; a referral stays made.
            implied = "request_information"
        elif escalate:
            implied = "specialist_review"
        elif asking:
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
