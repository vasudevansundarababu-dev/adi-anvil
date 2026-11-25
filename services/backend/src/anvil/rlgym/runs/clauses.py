"""Policy clauses: applicability, setup coverage and clause receipts (E-002 §3a, §4.3, §9; E-001 §3.6).

Contracts (Studio drafts d27063d / a957322 / 2f4e9bf, 23 Nov 2026, not yet final):
- clause-condition.v1: null, or a predicate over logical facts: {all|any|not} and
  {fact, op: eq|ne|in|not_in|lt|lte|gt|gte|between|present|absent, value, label?}. Three-valued.
- clause-receipt.v1: the receipt written per episode × clause. It allows no extra properties, so the compiled ZEN
  expression and the plug-in's replay go to `clause_engine` beside the receipts in the sealed bundle.
- registry-case.v1: case rows carry `facts` (environment fact id → value); absent means missing.
- The RL Gym template document's `policy_bindings` (embedded at release): {fact_catalog, facts: [{fact,
  environment_fact}], clauses: [{clause_id, clause_version?, needs: {tools, evidence, checks: [{criterion_id,
  block_ids}]}}]}; the template.v1 form with `obligation_checks` is read too.

A task's selected clauses come from Authoring's export: approved-task-export.v1 `policy_clauses` on the exported
task (Studio ef06119), stored with the task at import and frozen in the run manifest:
{clause_id, version, title?, obligation?, required_actor?, source: {document_id, document_version, sha256, locator?,
 quote?}, approval: {approval_id, project_id, approved_by?, approved_at?}, condition, exceptions?: [{text, condition?}]}.
Also read: S4 `policyBindings` / actor `policy_clauses` in the same shape, the nested {clause: {...}} form, and the
flat provisional form used before the drafts (clause_version, approval_id, source_sha256, obligation{tools, evidence},
criteria, facts). An exception with only text (no condition) is shown to the agent but never evaluated.

Outcomes (the owner's rule, E-002 §9.2):
- setup_gap: a tool the obligation needs is not offered, a table a check reads is not captured, or a fact the condition
  needs has no binding. Found at admission it BLOCKS the run; found after an episode it is reported, never scored.
- unresolved: the case has no value for a fact the condition needs. Excluded from the score and reported.
- applies: the condition holds; the consuming criteria score normally (pass or fail).
- skipped: the condition fails or an exception holds; the consuming criteria are not scored.
A decided false wins over a missing fact (three-valued logic). Every decided condition is replayed on the qualified
GoRules ZEN plug-in; a disagreement becomes a setup gap. Nothing here calls an agent, a model or Studio.
"""

import hashlib
import json
import re

from anvil.rlgym.common import GymError

SCHEMA = "adi.utility.clause-receipt.v1"
OPS = ("eq", "ne", "in", "not_in", "lt", "lte", "gt", "gte", "between", "present", "absent")
OUTCOMES = ("applies", "skipped", "unresolved", "setup_gap")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_ZEN_OP = {"eq": "==", "ne": "!=", "lt": "<", "lte": "<=", "gt": ">", "gte": ">="}
_WORDS = {
    "eq": "is",
    "ne": "is not",
    "in": "is one of",
    "not_in": "is not one of",
    "lt": "is below",
    "lte": "is at most",
    "gt": "is above",
    "gte": "is at least",
    "between": "is between",
    "present": "is present",
    "absent": "is absent",
}


# --- predicates ---------------------------------------------------------------------------------------------


def validate(pred, where="condition"):
    """Raise CLAUSE_INVALID for a predicate outside clause-condition.v1."""
    if pred is None:
        return
    if not isinstance(pred, dict) or not pred:
        raise GymError("CLAUSE_INVALID", f"{where}: a predicate must be an object")
    if "all" in pred or "any" in pred:
        key = "all" if "all" in pred else "any"
        items = pred[key]
        if not isinstance(items, list) or not items:
            raise GymError("CLAUSE_INVALID", f"{where}: '{key}' needs a non-empty list")
        for i, p in enumerate(items):
            validate(p, f"{where}.{key}[{i}]")
        return
    if "not" in pred:
        validate(pred["not"], f"{where}.not")
        return
    if not isinstance(pred.get("fact"), str) or not pred["fact"]:
        raise GymError("CLAUSE_INVALID", f"{where}: 'fact' is required")
    op = pred.get("op")
    if op not in OPS:
        raise GymError("CLAUSE_INVALID", f"{where}: unknown operator {op!r}")
    if op in ("in", "not_in") and not isinstance(pred.get("value"), list):
        raise GymError("CLAUSE_INVALID", f"{where}: '{op}' needs a list value")
    if op == "between" and not (isinstance(pred.get("value"), list) and len(pred["value"]) == 2):
        raise GymError("CLAUSE_INVALID", f"{where}: 'between' needs [low, high]")


def facts_in(pred):
    if not pred:
        return set()
    if "all" in pred or "any" in pred:
        return set().union(*(facts_in(p) for p in pred.get("all") or pred.get("any")))
    if "not" in pred:
        return facts_in(pred["not"])
    return {pred["fact"]}


def _zen_cmp(f, op, v):
    lit = json.dumps(v, ensure_ascii=False)
    if isinstance(v, str) and _ISO_DATE.match(v):
        # ZEN orders dates, not strings: an ISO date compares as date(...) on both sides.
        return f"date({f}) {_ZEN_OP[op]} date({lit})"
    return f"{f} {_ZEN_OP[op]} {lit}"


def compile_zen(pred):
    """The predicate as a ZEN expression over the facts object (`true` for no condition)."""
    if not pred:
        return "true"
    if "all" in pred:
        return "(" + " and ".join(compile_zen(p) for p in pred["all"]) + ")"
    if "any" in pred:
        return "(" + " or ".join(compile_zen(p) for p in pred["any"]) + ")"
    if "not" in pred:
        return f"not ({compile_zen(pred['not'])})"
    f, op, v = pred["fact"], pred["op"], pred.get("value")
    if op == "present":
        return f"{f} != null"
    if op == "absent":
        return f"{f} == null"
    if op == "in":
        return f"{f} in {json.dumps(v, ensure_ascii=False)}"
    if op == "not_in":
        return f"not ({f} in {json.dumps(v, ensure_ascii=False)})"
    if op == "between":
        return f"({_zen_cmp(f, 'gte', v[0])} and {_zen_cmp(f, 'lte', v[1])})"
    if op in ("eq", "ne"):
        return f"{f} {_ZEN_OP[op]} {json.dumps(v, ensure_ascii=False)}"
    return _zen_cmp(f, op, v)


def _leaf(pred, facts):
    f, op, v = pred["fact"], pred["op"], pred.get("value")
    known = f in facts and facts[f] is not None
    x = facts.get(f)
    if isinstance(x, list):
        # KYC Judgment C1 §8: a multi-valued fact (citizenship, document_kinds). eq/in hold when any value matches,
        # ne/not_in when none does; [] is a decided "none" (present is false), never a missing value.
        if op == "present":
            return bool(x)
        if op == "absent":
            return not x
        if op == "eq":
            return v in x
        if op == "ne":
            return v not in x
        if op == "in":
            return any(i in v for i in x)
        if op == "not_in":
            return not any(i in v for i in x)
        return False  # an ordering over a set of values never holds
    if op == "present":
        return known
    if op == "absent":
        return not known
    if not known:
        return None
    try:
        return {
            "eq": lambda: x == v,
            "ne": lambda: x != v,
            "in": lambda: x in v,
            "not_in": lambda: x not in v,
            "lt": lambda: x < v,
            "lte": lambda: x <= v,
            "gt": lambda: x > v,
            "gte": lambda: x >= v,
            "between": lambda: v[0] <= x <= v[1],
        }[op]()
    except TypeError:
        return False  # a value of the wrong type never satisfies an ordering


def plain(pred, actual=None):
    """A comparison in plain language: its label, or 'fact is value', with the case's value when given."""
    if pred.get("label"):
        text = pred["label"]
    else:
        v = pred.get("value")
        if pred["op"] == "between":
            shown = f" {v[0]} and {v[1]}"
        elif pred["op"] in ("present", "absent"):
            shown = ""
        else:
            shown = " " + (", ".join(map(str, v)) if isinstance(v, list) else str(v))
        text = f"{pred['fact']} {_WORDS[pred['op']]}{shown}"
    return text + (f" (it is {actual})" if actual is not None else "")


def evaluate(pred, facts):
    """→ (True | False | None, trace). The trace names the leaves that decided: matched, failed, missing."""
    trace = {"matched": {}, "failed": [], "missing": set()}

    def go(p):
        if not p:
            return True
        if "all" in p:
            vals = [go(q) for q in p["all"]]
            return False if False in vals else None if None in vals else True
        if "any" in p:
            vals = [go(q) for q in p["any"]]
            return True if True in vals else None if None in vals else False
        if "not" in p:
            v = go(p["not"])
            return None if v is None else not v
        r = _leaf(p, facts)
        if r is None:
            trace["missing"].add(p["fact"])
        elif r:
            trace["matched"][p["fact"]] = facts.get(p["fact"])
        else:
            trace["failed"].append(plain(p, facts.get(p["fact"])))
        return r

    out = go(pred)
    trace["missing"] = sorted(trace["missing"])
    return out, trace


# --- task clauses, bindings and facts -----------------------------------------------------------------------


def task_clauses(actor, task=None):
    """The clause versions a task selected (empty list: no clauses, the run behaves exactly as before). The export's
    task-level `policy_clauses` win; then S4 policyBindings, then actor policy_clauses."""
    if task and isinstance(task.get("policy_clauses"), list) and task["policy_clauses"]:
        return [c for c in task["policy_clauses"] if isinstance(c, dict)]
    actor = actor or {}
    sections = actor.get("sections") if isinstance(actor.get("sections"), dict) else {}
    s4 = sections.get("S4") if isinstance(sections.get("S4"), dict) else {}
    found = s4.get("policyBindings") or actor.get("policy_clauses")
    return [c for c in (found or []) if isinstance(c, dict)]


def normal(cl):
    """(clause, approval) identities of a selected clause, from the contract form or the provisional flat form."""
    if isinstance(cl.get("clause"), dict):
        clause = dict(cl["clause"])
    else:
        src = cl.get("source") if isinstance(cl.get("source"), dict) else None
        clause = {
            "clause_id": cl.get("clause_id"),
            "version": cl.get("version") or cl.get("clause_version"),
            **({"title": cl["title"]} if cl.get("title") else {}),
            # The receipt's source identity: the document and its hash, never the quoted text.
            "source": {k: v for k, v in src.items() if k != "quote"}
            if src
            else {"sha256": cl.get("source_sha256")},
        }
    approval = (
        dict(cl["approval"])
        if isinstance(cl.get("approval"), dict)
        else {"approval_id": cl.get("approval_id")}
    )
    return clause, approval


def exception_conditions(cl):
    """The exceptions that can be evaluated: a predicate, or {text, condition} with a condition."""
    out = []
    for e in cl.get("exceptions") or []:
        if isinstance(e, dict) and ("text" in e or "condition" in e):
            if e.get("condition"):
                out.append(e["condition"])
        elif isinstance(e, dict):
            out.append(e)
    return out


def label(cl):
    clause, _ = normal(cl)
    return f"{clause.get('clause_id')}@{clause.get('version')}"


def check_clause(cl):
    clause, _ = normal(cl)
    for key in ("clause_id", "version"):
        if not clause.get(key):
            raise GymError("CLAUSE_INVALID", f"A selected clause has no {key}")
    validate(cl.get("condition"))
    for i, e in enumerate(exception_conditions(cl)):
        validate(e, f"exceptions[{i}]")


def needs(cl, bindings):
    """{tools, evidence, checks}: from the template's embedded policy_bindings, else the provisional clause fields."""
    clause, _ = normal(cl)
    for entry in (bindings or {}).get("clauses") or []:
        if entry.get("clause_id") == clause["clause_id"] and entry.get("clause_version") in (
            None,
            clause.get("version"),
        ):
            n = entry.get("needs") or {}
            return {
                "tools": list(n.get("tools") or []),
                "evidence": list(n.get("evidence") or []),
                "checks": list(n.get("checks") or []),
            }
    if bindings and bindings.get("obligation_checks") is not None:
        checks = [
            {"criterion_id": o["criterion_id"], "block_ids": list(o.get("block_ids") or [])}
            for o in bindings["obligation_checks"]
            if o.get("clause_id") == clause["clause_id"]
        ]
        return {"tools": [], "evidence": [], "checks": checks}
    ob = cl.get("obligation") if isinstance(cl.get("obligation"), dict) else {}
    return {
        "tools": list(ob.get("tools") or []),
        "evidence": list(ob.get("evidence") or []),
        "checks": [{"criterion_id": c, "block_ids": []} for c in cl.get("criteria") or []],
    }


def _env_catalog(env):
    cat = (env or {}).get("facts")
    items = cat.get("facts") if isinstance(cat, dict) else cat
    return {f["id"]: f for f in items or [] if isinstance(f, dict) and f.get("id")}


def _path(root, path):
    cur = root
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None, False
    return cur, True


def _fact(cl, name, case, env, bindings, evidence):
    """(value, available, source). The logical fact is read through the template's binding to the environment's
    fact: case_data facts from the case row, episode_evidence facts from the sealed evidence (after the episode)."""
    if bindings and bindings.get("facts") is not None:
        env_fact = next(
            (b["environment_fact"] for b in bindings["facts"] if b.get("fact") == name), None
        )
        if env_fact is None:
            return None, False, None  # a binding gap: coverage() reports it as a setup gap
        spec = _env_catalog(env).get(env_fact) or {}
        src = spec.get("source") or {}
        if spec.get("availability") == "episode_evidence":
            if evidence is None:
                return None, False, None
            path = src.get("path") or f"facts.{env_fact}"
            v, ok = _path(evidence, path)
            return v, ok and v is not None, path
        where = (
            f"case_data:{src['collection']}.{src['field']}"
            if src.get("collection") and src.get("field")
            else f"case_data:facts.{env_fact}"
        )
        v, ok = _path((case or {}).get("facts") or {}, env_fact)
        return v, ok and v is not None, where
    # Provisional binding on the clause, or the logical name itself on the case row.
    b = (cl.get("facts") or {}).get(name) or {"source": "case", "path": name}
    if b.get("source") == "evidence":
        if evidence is None:
            return None, False, None
        v, ok = _path(evidence, b["path"])
        return v, ok and v is not None, b["path"]
    v, ok = _path((case or {}).get("facts") or {}, b["path"])
    return v, ok and v is not None, f"case_data:facts.{b['path']}"


def _tables(env):
    env = env or {}
    schema = env.get("schema") if isinstance(env.get("schema"), dict) else {}
    cols = schema.get("collections")
    if isinstance(cols, dict):
        tables = set(cols)
    else:
        tables = {c.get("name") if isinstance(c, dict) else c for c in cols or []}
    return tables | set(env.get("schema_tables") or [])


def coverage(cl, env, bindings=None):
    """Setup gaps for one clause on the bound environment version, in clause-receipt.v1 form: obligation tools it does
    not offer, tables it does not capture, and condition facts the template does not bind."""
    env = env or {}
    ops = {o.get("operation_id") if isinstance(o, dict) else o for o in env.get("operations") or []}
    if isinstance(env.get("tools"), list):
        ops |= {t.get("name") if isinstance(t, dict) else t for t in env["tools"]}
    n = needs(cl, bindings)
    gaps = [
        {"kind": "tool", "ref": t, "message": f"The environment offers no operation {t}"}
        for t in n["tools"]
        if t not in ops
    ]
    tables = _tables(env)
    gaps += [
        {"kind": "evidence", "ref": t, "message": f"The environment does not capture {t}"}
        for t in n["evidence"]
        if t not in tables
    ]
    if bindings and bindings.get("facts") is not None:
        bound = {b.get("fact") for b in bindings["facts"]}
        names = facts_in(cl.get("condition")).union(
            *(facts_in(e) for e in exception_conditions(cl))
        )
        gaps += [
            {
                "kind": "fact_binding",
                "ref": f,
                "message": f"The template binds no environment fact to {f}",
            }
            for f in sorted(names - bound)
        ]
    return gaps


def _scenario(outcome, clause, detail):
    name = clause.get("title") or clause.get("clause_id")
    return {
        "applies": f"{name} applies ({detail}); its checks are scored.",
        "skipped": f"{name} does not apply ({detail}); its checks are not scored.",
        "unresolved": f"{name} cannot be resolved ({detail}); excluded from the score.",
        "setup_gap": f"{name} cannot be evaluated ({detail}); never scored.",
    }[outcome]


def _receipt_id(r):
    body = json.dumps({**r, "receipt_id": ""}, sort_keys=True, default=str).encode()
    return "cr-" + hashlib.sha256(body).hexdigest()[:16]


def resolve(cl, case, env, evidence=None, bindings=None, context=None):
    """→ (receipt per clause-receipt.v1, engine note). Before the episode pass evidence=None (static facts only);
    after the episode pass the sealed evidence. `context`: run_id, episode_id, task, binding identity."""
    check_clause(cl)
    context = context or {}
    clause, approval = normal(cl)
    cond, exceptions = cl.get("condition"), exception_conditions(cl)
    names = sorted(facts_in(cond).union(*(facts_in(e) for e in exceptions)))
    facts, used, dynamic = {}, [], False
    for n in names:
        v, ok, source = _fact(cl, n, case, env, bindings, evidence)
        if source and not source.startswith("case_data:"):
            dynamic = True
        if ok:
            facts[n] = v
            used.append(
                {"fact": n, "value": None if isinstance(v, (dict, list)) else v, "source": source}
            )
    binding = {
        k: v
        for k, v in {
            **(context.get("binding") or {}),
            "fact_catalog": (bindings or {}).get("fact_catalog"),
            "binding_revision": (bindings or {}).get("binding_revision"),
        }.items()
        if v is not None
    }
    n = needs(cl, bindings)
    receipt = {
        "schema_version": SCHEMA,
        "receipt_id": "",
        "run_id": context.get("run_id") or "",
        "episode_id": context.get("episode_id") or "",
        "case_id": (case or {}).get("case_id") or "",
        **({"task": context["task"]} if context.get("task") else {}),
        "clause": clause,
        "approval": approval,
        "binding": binding,
        "condition": cond,
        "phase": "dynamic" if dynamic or (evidence is not None and n["evidence"]) else "static",
        "facts_used": used,
        "consumed_by": [
            {"criterion_id": c["criterion_id"], "block_ids": list(c.get("block_ids") or [])}
            for c in n["checks"]
        ],
    }
    engine = {"zen_expression": compile_zen(cond)}

    def done(outcome, detail, **extra):
        r = {**receipt, **extra, "outcome": outcome, "scored": outcome == "applies"}
        r["scenario"] = _scenario(outcome, clause, detail)
        r["receipt_id"] = _receipt_id(r)
        return r, engine

    gaps = coverage(cl, env, bindings)
    if gaps:
        return done("setup_gap", "; ".join(g["message"] for g in gaps), setup_gaps=gaps)
    ok, trace = evaluate(cond, facts)
    if ok is None:
        return done(
            "unresolved",
            "no value for " + ", ".join(trace["missing"]),
            missing_facts=trace["missing"],
        )
    if ok is False:
        return done("skipped", "; ".join(trace["failed"]), failed_conditions=trace["failed"])
    for e in exceptions:
        hit, etrace = evaluate(e, facts)
        if hit is None:
            return done(
                "unresolved",
                "no value for " + ", ".join(etrace["missing"]),
                missing_facts=etrace["missing"],
            )
        if hit:
            text = "exception holds: " + (plain(e) if "fact" in e else compile_zen(e))
            engine["exception"] = True
            return done("skipped", text, failed_conditions=[text])
    matched = ", ".join(f"{k} = {v}" for k, v in trace["matched"].items()) or "no condition"
    if evidence is not None:
        # A check that reads a table the episode did not capture cannot tell a failure from missing evidence.
        missing = [t for t in n["evidence"] if not _path(evidence, f"snapshots.end.{t}")[1]]
        if missing:
            gaps = [
                {"kind": "evidence", "ref": t, "message": f"{t} was not captured in this episode"}
                for t in missing
            ]
            return done("setup_gap", "; ".join(g["message"] for g in gaps), setup_gaps=gaps)
    return done("applies", matched)


def receipts(clauses, case, env, evidence=None, bindings=None, context=None, zen=None, invoke=None):
    """→ (receipts, engine notes). With `zen` (the qualified ZEN plug-in's manifest) each decided condition is
    replayed on it; receipt ids are computed after that, so a changed outcome changes the id."""
    pairs = [resolve(cl, case, env, evidence, bindings, context) for cl in clauses]
    out, notes = [r for r, _ in pairs], [e for _, e in pairs]
    if zen:
        zen_confirm(out, notes, zen, invoke=invoke)
    for r, note in zip(out, notes, strict=True):
        r["receipt_id"] = _receipt_id(r)
        note["receipt_id"] = r["receipt_id"]
    return out, notes


# --- admission and scoring -----------------------------------------------------------------------------------


def problems(selected):
    """None if every exported clause is valid (or there are none), else the first reason (import check)."""
    for cl in selected or []:
        if not isinstance(cl, dict):
            return "a policy clause must be an object"
        try:
            check_clause(cl)
        except GymError as exc:
            return f"{label(cl)}: {exc.message}"
    return None


def admission_gaps(tasks, env, bindings=None):
    """Per task, invalid clauses and the clauses whose tools, evidence or fact bindings the bound environment and
    template lack. Any entry blocks the run (E-002 §9.2): a setup gap is fixed before the run, never scored."""
    problems = []
    for t in tasks:
        for cl in task_clauses(t.get("actor"), t):
            try:
                check_clause(cl)
            except GymError as exc:
                problems.append(
                    {"task_id": t.get("task_id"), "clause": label(cl), "detail": exc.message}
                )
                continue
            for g in coverage(cl, env, bindings):
                problems.append(
                    {"task_id": t.get("task_id"), "clause": label(cl), "detail": g["message"]}
                )
    return problems


def edge_holds(tasks, case_list, env_id):
    """Tasks focused on an edge case the bound version has no cases for: held, not failed mid-run (E-001 §3.6).
    Counted from the version's case rows (their tags), not its summary."""
    have = {}
    for c in case_list or []:
        for tag in c.get("edge_cases") or []:
            have[tag] = have.get(tag, 0) + 1
    holds = []
    for t in tasks:
        for tag in (t.get("case_selector") or {}).get("edge_cases") or []:
            if not have.get(tag):
                holds.append(
                    {
                        "task_id": t.get("task_id"),
                        "edge_case": tag,
                        "detail": f"waiting for a version of {env_id.split('@')[0]} with {tag} cases",
                    }
                )
    return holds


def criterion_effects(receipts_):
    """criterion_id → how its clause receipts change scoring:
    - absent: at least one consuming clause applies (or none consumes it) → scored normally;
    - "not_applicable": every consuming clause was skipped → not scored (not a pass, not a fail);
    - "unresolved" / "setup_gap": excluded from the score and reported."""
    by = {}
    for r in receipts_ or []:
        for c in r.get("consumed_by") or []:
            by.setdefault(c["criterion_id"], []).append(r["outcome"])
    effects = {}
    for cid, outs in by.items():
        if "applies" in outs:
            continue
        effects[cid] = (
            "setup_gap"
            if "setup_gap" in outs
            else "unresolved"
            if "unresolved" in outs
            else "not_applicable"
        )
    return effects


# --- the decision on the qualified GoRules ZEN plug-in -----------------------------------------------------------

ZEN_PLUGIN = "gorules-zen"


def zen_rules(expression):
    """A one-node JDM: the clause's compiled condition as a ZEN expression, returned as `pass` (rule_check mode)."""
    return {
        "nodes": [
            {"id": "in", "type": "inputNode", "name": "Facts", "position": {"x": 0, "y": 0}},
            {
                "id": "x",
                "type": "expressionNode",
                "name": "Applies",
                "position": {"x": 240, "y": 0},
                "content": {"expressions": [{"id": "e1", "key": "pass", "value": expression}]},
            },
            {"id": "out", "type": "outputNode", "name": "Result", "position": {"x": 480, "y": 0}},
        ],
        "edges": [
            {"id": "a", "sourceId": "in", "targetId": "x", "type": "edge"},
            {"id": "b", "sourceId": "x", "targetId": "out", "type": "edge"},
        ],
    }


def zen_confirm(receipts_, notes, manifest, invoke=None):
    """Replay every decided condition (Applies, or Skipped on the condition) on the qualified ZEN plug-in; the
    engine's answer goes to the note. A disagreement turns the receipt into a Setup gap (never scored); a plug-in that
    cannot run leaves the resolver's answer, marked not_run. Unresolved, setup-gap, unconditional and exception-skipped
    clauses are not sent."""
    from anvil.rlgym.plugins import contract, runner

    todo = [
        i
        for i, r in enumerate(receipts_)
        if r.get("condition")
        and r["outcome"] in ("applies", "skipped")
        and not notes[i].get("exception")
    ]
    if not todo:
        return
    name = f"{manifest.get('id')} {manifest.get('version')}"
    files, blocks, facts = {}, [], {}
    for i in todo:
        r = receipts_[i]
        rules = zen_rules(notes[i]["zen_expression"])
        digest = contract.jcs_sha256(rules)
        files[digest] = rules
        known = {u["fact"]: u["value"] for u in r["facts_used"]}
        facts[str(i)] = known
        blocks.append(
            {
                "id": f"clause-{i}",
                "settings": {
                    "mode": "rule_check",
                    "rules": {"ref": f"clause:{r['clause']['clause_id']}", "sha256": digest},
                    "inputs": {f: f"clause_facts.{i}.{f}" for f in known},
                },
            }
        )
    job = {
        "schema": contract.JOB,
        "blocks": blocks,
        "files": files,
        "evidence": {"clause_facts": facts},
    }
    lines, why = {}, "no result"
    try:
        out = runner.run(manifest, job, invoke=invoke)
        lines = {x["block_id"]: x for x in out["results"]}
    except Exception as exc:  # noqa: BLE001 - the plug-in is a cross-check; its absence never blocks a receipt
        why = type(exc).__name__
    for i in todo:
        r, note = receipts_[i], notes[i]
        line = lines.get(f"clause-{i}")
        if not line or line["verdict"] == "blocked":
            note["engine"] = {
                "plugin": name,
                "result": "not_run",
                "detail": str((line or {}).get("detail") or why)[:200],
            }
            continue
        zen_applies = line["verdict"] == "pass"
        agrees = zen_applies == (r["outcome"] == "applies")
        note["engine"] = {"plugin": name, "result": "agrees" if agrees else "disagrees"}
        if not agrees:
            note["outcome_before_engine"] = r["outcome"]
            r.pop("failed_conditions", None)
            r["outcome"], r["scored"] = "setup_gap", False
            msg = (
                f"the ZEN plug-in says the clause {'applies' if zen_applies else 'does not apply'}, "
                f"the resolver said {note['outcome_before_engine']}"
            )
            r["setup_gaps"] = [{"kind": "fact_binding", "ref": ZEN_PLUGIN, "message": msg}]
            r["scenario"] = _scenario("setup_gap", r["clause"], msg)
