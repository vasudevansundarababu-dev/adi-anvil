"""E-007 §7.2: the reference agent. A deterministic agent built from a task's S5 steps (and follow-ups) and the case's
hidden reference answers. It acts through the task's offered tools (S3) and the same opaque IDs a model sees, so if it
can't do something, a model can't either: every such place is a named failure ("S5 step 3 documents.list needs a
party id; no offered tool lists parties").

`summary(actor)` is the plain-language approach (what it does, step by step) a person confirms once per task revision;
`agent(...)` is the generator the runner drives (it yields {"tool", "args"} or {"final": ...} and receives the
observation, like the live and mock agents).
"""

import hashlib
import json

CHECKS = ("identity.check", "document.check", "address.check", "screening.check", "authority.check")
CONDITIONAL = {
    "information.request": "If the case needs information: request the missing item from the party who lacks it",
    "specialist.refer": "If the case needs a specialist: refer it to the reference specialty",
    "finding.write": "If there is a discrepancy, missing item or screening issue: record a finding",
    "finding.resolve": "Resolve findings only when the evidence clears them (the reference agent never does)",
}
PLAIN = {
    "application.read": "Read the assigned application",
    "parties.list": "List the application's parties",
    "policy.read": "Read the published policy rules",
    "documents.list": "List each party's documents",
    "document.read": "Read each document",
    "document.compare": "Compare a party's documents",
    "operation.read": "Read the result of each pending check",
    "operation.lookup": "Look up pending checks",
    "information.read": "Read answers to information requests",
    "specialist.read": "Read specialist answers",
    "search": "Search the policy sources",
    "search.read": "Read a search result",
    "recommend": "Record the reference recommendation with its reason and evidence",
}


def _sections(actor):
    s = (actor or {}).get("sections")
    return s if isinstance(s, dict) else {}


def offered(actor):
    s3 = _sections(actor).get("S3") if isinstance(_sections(actor).get("S3"), dict) else {}
    return set(s3.get("tools") or []) | set((actor or {}).get("tools") or [])


def steps(actor):
    s5 = _sections(actor).get("S5") if isinstance(_sections(actor).get("S5"), dict) else {}
    out = []
    for i, st in enumerate(s5.get("steps") or [], 1):
        if isinstance(st, dict) and st.get("tool"):
            out.append(
                {
                    "n": i,
                    "tool": st["tool"],
                    "follow_ups": [
                        t
                        for f in st.get("followUps") or []
                        if isinstance(f, dict)
                        for t in f.get("tools") or []
                    ],
                }
            )
    return out


def summary(actor):
    """The reference approach in plain words, and its hash (what a confirmation is bound to)."""
    lines = []
    for st in steps(actor):
        tool = st["tool"]
        text = CONDITIONAL.get(tool) or (
            f"Run {tool} for each party with that party's documents"
            if tool in CHECKS
            else PLAIN.get(tool, f"Use {tool}")
        )
        lines.append(f"S5 step {st['n']}: {text} ({tool}).")
        for t in st["follow_ups"]:
            lines.append(f"   then: {CONDITIONAL.get(t) or PLAIN.get(t, f'use {t}')} ({t}).")
    lines.append(
        "Decisions come from the case's hidden reference answers (recommendation, request type, referral); "
        "the agent never sees them as text."
    )
    text = "\n".join(lines)
    return {"text": text, "sha256": hashlib.sha256(text.encode()).hexdigest()}


def _records(obs):
    return ((obs or {}).get("output") or {}).get("records") or []


def _const(operations, op, field, default):
    for o in operations or []:
        if isinstance(o, dict) and o.get("operation_id") == op:
            prop = ((o.get("input_schema") or {}).get("properties") or {}).get(field) or {}
            if "const" in prop:
                return prop["const"]
            if prop.get("enum"):
                return prop["enum"][0]
    return default


def agent(actor, reference, application_id, failures, operations=None):
    """The generator. `application_id` is what the agent was told (an alias when IDs are hidden). `failures` collects
    {"step", "tool", "reason"} wherever the task can't be followed as written."""
    from anvil.rlgym.verification import assertions

    have = offered(actor)
    parties, docs, evidence, revision, pending = [], [], [], 1, []
    application = {"application_id": application_id}
    seen_tools = set()

    def fail(st, reason):
        failures.append({"step": st["n"], "tool": st["tool"], "reason": reason})

    def need(st, tool):
        if tool not in have:
            fail(st, f"S5 step {st['n']} uses {tool}, which S3 does not offer")
            return False
        return True

    plan = []
    for st in steps(actor):
        plan.append(st)
        # D-016 follow-ups run right after their step, when the case calls for them (decided from the reference).
        plan += [{"n": st["n"], "tool": t, "follow_up": True} for t in st["follow_ups"]]
    if not plan:
        failures.append(
            {"step": None, "tool": None, "reason": "the task has no S5 steps with tools"}
        )
    request_type = reference.get("request_type")
    referral = reference.get("referral")
    issue = reference.get("screening_issue")
    # Does S5 read pending checks itself (an operation.read step after the checks)?
    reads_later = any(x["tool"] == "operation.read" for x in plan)
    for st in plan:
        tool = st["tool"]
        if tool in CONDITIONAL:
            wanted = {
                "information.request": request_type not in (None, "", "none"),
                "specialist.refer": referral not in (None, "", "none"),
                "finding.write": any(
                    v not in (None, "", "none") for v in (request_type, referral, issue)
                ),
                "finding.resolve": False,
            }[tool]
            if not wanted:
                continue
        if st.get("follow_up") and tool in seen_tools and tool in CONDITIONAL:
            continue  # once per case is enough for a conditional action
        if not need(st, tool):
            continue
        seen_tools.add(tool)
        if tool == "application.read":
            obs = yield {"tool": tool, "args": {"application_id": application_id}}
            recs = _records(obs)
            revision = int((recs[0] if recs else {}).get("revision") or 1)
            if recs:
                application = {**recs[0], "application_id": application_id}
            if not obs.get("ok"):
                fail(st, f"application.read was refused: {obs.get('error')}")
        elif tool == "parties.list":
            obs = yield {"tool": tool, "args": {"application_id": application_id}}
            parties = [r for r in _records(obs) if r.get("party_id")]
        elif tool == "policy.read":
            yield {"tool": tool, "args": {}}
        elif tool == "documents.list":
            if not parties and "parties.list" not in have:
                fail(
                    st,
                    "S5 step {} documents.list needs a party id; no offered tool lists parties "
                    "(parties.list isn't in S3)".format(st["n"]),
                )
                continue
            if not parties:
                obs = yield {"tool": "parties.list", "args": {"application_id": application_id}}
                parties = [r for r in _records(obs) if r.get("party_id")]
            for p in parties:
                obs = yield {"tool": tool, "args": {"party_id": p["party_id"]}}
                docs += [d for d in _records(obs) if d.get("document_id") and d not in docs]
        elif tool == "document.read":
            if not docs:
                fail(
                    st,
                    f"S5 step {st['n']} document.read has no documents to read (none were listed)",
                )
                continue
            for d in docs:
                obs = yield {"tool": tool, "args": {"id": d["document_id"]}}
                if obs.get("ok"):
                    evidence.append(d["document_id"])
        elif tool == "document.compare":
            for p in parties:
                mine = [d["document_id"] for d in docs if d.get("party_id") == p["party_id"]]
                if len(mine) >= 2:
                    yield {"tool": tool, "args": {"document_ids": mine}}
        elif tool in CHECKS:
            if not parties:
                fail(st, f"S5 step {st['n']} {tool} needs a party id, which no earlier step found")
                continue
            for p in parties:
                ids = [d["document_id"] for d in docs if d.get("party_id") == p["party_id"]][:5]
                args = {
                    "party_id": p["party_id"],
                    "document_ids": ids,
                    "input_revision": revision,
                    "idempotency_key": f"ref:{tool}:{p['party_id']}",
                }
                obs = yield {"tool": tool, "args": args}
                if obs.get("state") == "pending" and reads_later:
                    # S5 reads pending checks in a later step (operation.read): leave it to that step, as written.
                    pending.append(((obs.get("pending") or {}).get("pending_id"), tool, args))
                    continue
                # Otherwise a pending check completes when the same call is made again.
                tries = 0
                while obs.get("state") == "pending" and tries < 3:
                    obs = yield {"tool": tool, "args": args}
                    tries += 1
                if obs.get("state") == "pending":
                    fail(st, f"{tool} stayed pending after {tries} repeats")
                elif not obs.get("ok"):
                    fail(st, f"{tool} for a party was refused: {obs.get('error')}")
        elif tool == "operation.read":
            # S5: read each pending check's status by its id (operation.read is itself pending once).
            for pid, ctool, cargs in list(pending):
                obs = yield {"tool": tool, "args": {"id": pid}}
                tries = 0
                while obs.get("state") == "pending" and tries < 3:
                    obs = yield {"tool": tool, "args": {"id": pid}}
                    tries += 1
                out = obs.get("output") or {}
                if out.get("status") != "completed":
                    fail(
                        st,
                        f"S5 step {st['n']} operation.read can't read a pending check's id "
                        f"({out.get('reason') or out.get('status') or obs.get('error')}); the check was called again instead",
                    )
                    again = yield {"tool": ctool, "args": cargs}
                    while again.get("state") == "pending" and tries < 6:
                        again = yield {"tool": ctool, "args": cargs}
                        tries += 1
            pending.clear()
        elif tool == "operation.lookup":
            yield {"tool": tool, "args": {"idempotency_key": "ref:lookup"}}
        elif tool == "information.request":
            # The parties the agent listed are this application's (the records may not repeat its id).
            start = {
                "applications": [application],
                "documents": docs,
                "parties": [{**p, "application_id": application_id} for p in parties],
            }
            who = assertions.party_lacking(
                request_type, {"case_id": application_id, "snapshots": {"start": start}}
            )
            party = sorted(who)[0] if who else (parties[0]["party_id"] if parties else None)
            if not party:
                fail(
                    st,
                    f"S5 step {st['n']} information.request needs the party who lacks {request_type}; none is known",
                )
                continue
            if who is not None and not who:
                fail(st, f"the documents read don't show which party lacks {request_type}")
            yield {
                "tool": tool,
                "args": {
                    "party_id": party,
                    "type": request_type,
                    "items": [request_type],
                    "reason": f"{reference.get('reason_keyword') or request_type}: please provide it",
                },
            }
        elif tool == "finding.write":
            # In plain words, as a reviewer writes it: a screening hit is named as such; other findings are not.
            if issue not in (None, "", "none"):
                text = f"Screening returned a possible match ({issue.replace('_', ' ')}): {reference.get('reason_keyword') or 'needs review'}"
            else:
                text = f"Missing or invalid {str(request_type).replace('_', ' ')}: {reference.get('reason_keyword') or 'see documents'}"
            yield {"tool": tool, "args": {"issue": text, "evidence_ids": evidence[:10]}}
        elif tool == "specialist.refer":
            yield {
                "tool": tool,
                "args": {
                    "specialty": referral,
                    "question": f"Please review: {issue or referral}",
                    "evidence_ids": evidence[:10],
                },
            }
        elif tool == "recommend":
            obs = yield {
                "tool": tool,
                "args": {
                    "decision": reference.get("recommendation"),
                    "reason": (
                        f"Recommendation {str(reference.get('recommendation')).replace('_', ' ')} because of the evidence: "
                        f"{reference.get('reason_keyword') or 'all checks clear'}"
                    ),
                    "assessed_revision": revision,
                    "evidence_ids": evidence[:100] or ["none"],
                    "party_assessments": [
                        {
                            "party_id": p["party_id"],
                            "role": p.get("role") or "party",
                            "status": "assessed",
                        }
                        for p in parties
                    ]
                    or [{"party_id": application_id, "role": "applicant", "status": "assessed"}],
                    "policy_bundle": _const(
                        operations, "recommend", "policy_bundle", "project rules"
                    ),
                },
            }
            if not obs.get("ok"):
                fail(
                    st,
                    f"recommend was refused: {obs.get('error')} {obs.get('message') or ''}".strip(),
                )
        else:
            continue  # search, information.read, specialist.read: nothing to look up in a reference run
    if "recommend" not in seen_tools:
        failures.append(
            {"step": None, "tool": "recommend", "reason": "no S5 step records the recommendation"}
        )
    yield {"final": {"decision": reference.get("recommendation"), "summary": "reference agent"}}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()
