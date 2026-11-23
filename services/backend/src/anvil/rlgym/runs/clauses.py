"""Policy clauses: applicability, setup coverage and clause receipts (E-002 §3a, §4.3, §9; E-001 §3.6).

PROVISIONAL SHAPES. Studio's contract drafts (fact-catalog.v1, clause-receipt.v1, template S4 `policyBindings`, case-row
`facts`) had not arrived when this was written (23 Nov 2026). The field names below follow E-002 and are read in one
place (`task_clauses`, `_fact_value`), so they can be renamed to the approved contract without touching the logic.

A task selects clause versions (S4 `policyBindings`, or `policy_clauses` on the actor payload). Each clause:

    {"clause_id", "clause_version", "approval_id", "binding_revision", "source_sha256", "text",
     "condition": <predicate> | null,          # null: the clause always applies
     "exceptions": [<predicate>, ...],         # any exception true: Skipped
     "obligation": {"tools": [...], "evidence": [...]},   # tools the agent needs; collections a check reads
     "criteria": [criterion_id, ...],          # the criteria that consume this receipt
     "facts": {logical_fact: {"source": "case" | "evidence", "path": "..."}}}   # the template's fact binding

A predicate is over logical facts only, never template field names:
    {"fact": name, "op": eq|ne|in|not_in|lt|lte|gt|gte|exists, "value": v} | {"all": [...]} | {"any": [...]} | {"not": p}

Outcomes per episode × clause (the owner's rule, E-002 §9.2):
- setup_gap: a tool the obligation needs is not offered, or a collection a check reads is not captured. Found at
  admission it BLOCKS the run; found in an episode's evidence it is reported, never scored.
- unresolved: the case has no value for a fact the condition needs. Excluded from the score and reported.
- applies: the condition holds (matched facts recorded); the consuming criteria score normally.
- skipped: the condition fails or an exception holds (the failed part recorded); the consuming criteria are not scored.

Evaluation is three-valued (true / false / unknown), so a missing fact makes a clause Unresolved only when the answer
depends on it: `state == "CA" and product == "x"` with product "y" and no state is Skipped, not Unresolved.
The predicate is also compiled to a GoRules ZEN expression (`zen_expression`), recorded in every receipt, so the same
decision can be replayed on the qualified ZEN plug-in. Nothing here calls an agent, a model or an external service.
"""

import hashlib
import json
import re

from anvil.rlgym.common import GymError

SCHEMA = "clause-receipt.v1-draft"
OPS = ("eq", "ne", "in", "not_in", "lt", "lte", "gt", "gte", "exists")
OUTCOMES = ("applies", "skipped", "unresolved", "setup_gap")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_ZEN_OP = {"eq": "==", "ne": "!=", "lt": "<", "lte": "<=", "gt": ">", "gte": ">="}


# --- predicates ---------------------------------------------------------------------------------------------


def validate(pred, where="condition"):
    """Raise CLAUSE_INVALID for a predicate outside the schema (unknown operator, missing fact, bad shape)."""
    if pred is None:
        return
    if not isinstance(pred, dict) or len(pred) == 0:
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
    if pred.get("op") not in OPS:
        raise GymError("CLAUSE_INVALID", f"{where}: unknown operator {pred.get('op')!r}")
    if pred["op"] in ("in", "not_in") and not isinstance(pred.get("value"), list):
        raise GymError("CLAUSE_INVALID", f"{where}: '{pred['op']}' needs a list value")


def facts_in(pred):
    if not pred:
        return set()
    if "all" in pred or "any" in pred:
        return set().union(*(facts_in(p) for p in pred.get("all") or pred.get("any")))
    if "not" in pred:
        return facts_in(pred["not"])
    return {pred["fact"]}


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
    lit = json.dumps(v, ensure_ascii=False)
    if op == "exists":
        return f"{f} != null"
    if op == "in":
        return f"{f} in {lit}"
    if op == "not_in":
        return f"not ({f} in {lit})"
    if op in ("lt", "lte", "gt", "gte") and isinstance(v, str) and _ISO_DATE.match(v):
        # ZEN orders dates, not strings: an ISO date (or date-time) compares as date(...) on both sides.
        return f"date({f}) {_ZEN_OP[op]} date({lit})"
    return f"{f} {_ZEN_OP[op]} {lit}"


def _leaf(pred, facts):
    f, op, v = pred["fact"], pred["op"], pred.get("value")
    if op == "exists":
        return f in facts and facts[f] is not None
    if f not in facts or facts[f] is None:
        return None
    x = facts[f]
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
        }[op]()
    except TypeError:
        return False  # a value of the wrong type never satisfies an ordering


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
            trace["failed"].append(
                {
                    "fact": p["fact"],
                    "op": p["op"],
                    "value": p.get("value"),
                    "actual": facts.get(p["fact"]),
                }
            )
        return r

    out = go(pred)
    trace["missing"] = sorted(trace["missing"])
    return out, trace


# --- task clauses and facts ---------------------------------------------------------------------------------


def task_clauses(actor):
    """The clause versions a task selected (empty list: no clauses, the run behaves exactly as before)."""
    actor = actor or {}
    s4 = (
        ((actor.get("sections") or {}).get("S4") or {})
        if isinstance(actor.get("sections"), dict)
        else {}
    )
    found = (s4.get("policyBindings") if isinstance(s4, dict) else None) or actor.get(
        "policy_clauses"
    )
    return [c for c in (found or []) if isinstance(c, dict)]


def check_clause(clause):
    for key in ("clause_id", "clause_version"):
        if not clause.get(key):
            raise GymError("CLAUSE_INVALID", f"A selected clause has no {key}")
    validate(clause.get("condition"))
    for i, e in enumerate(clause.get("exceptions") or []):
        validate(e, f"exceptions[{i}]")


def _path(root, path):
    cur = root
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None, False
    return cur, True


def _fact_value(clause, name, case, evidence):
    """(value, available). A fact is read through the template's binding; unbound facts are read from the case
    row's `facts` by their logical name. `evidence` is None before the episode (static facts only)."""
    binding = (clause.get("facts") or {}).get(name) or {"source": "case", "path": name}
    if binding.get("source") == "evidence":
        if evidence is None:
            return None, False
        return _path(evidence, binding["path"])
    facts = (case or {}).get("facts") or {}
    v, ok = _path(facts, binding["path"])
    return (v, ok and v is not None)


def coverage(clause, env):
    """Setup gaps for one clause on the bound environment version: obligation tools it does not offer and evidence
    collections it does not capture. An empty list means the clause can be evaluated."""
    env = env or {}
    ops = {o.get("operation_id") if isinstance(o, dict) else o for o in env.get("operations") or []}
    if isinstance(env.get("tools"), list):
        ops |= {t.get("name") if isinstance(t, dict) else t for t in env["tools"]}
    # Declared collections: Studio's schema is {"collections": [{"name": ...}]}; older records list table names.
    cols = (
        (env.get("schema") or {}).get("collections")
        if isinstance(env.get("schema"), dict)
        else None
    )
    if isinstance(cols, dict):
        tables = set(cols)
    else:
        tables = {c.get("name") if isinstance(c, dict) else c for c in cols or []}
    tables |= set(env.get("schema_tables") or [])
    ob = clause.get("obligation") or {}
    gaps = [
        {"kind": "tool", "name": t, "detail": f"The environment offers no operation {t}"}
        for t in ob.get("tools") or []
        if t not in ops
    ]
    gaps += [
        {"kind": "evidence", "name": t, "detail": f"The environment does not capture {t}"}
        for t in ob.get("evidence") or []
        if t not in tables
    ]
    return gaps


def identity(clause):
    return {
        "clause": {"id": clause.get("clause_id"), "version": clause.get("clause_version")},
        "approval_id": clause.get("approval_id"),
        "binding_revision": clause.get("binding_revision"),
        "source_sha256": clause.get("source_sha256"),
    }


def resolve(clause, case, env, evidence=None):
    """One receipt for one clause on one case. Before the episode pass evidence=None (static facts only); after the
    episode pass the sealed evidence, so facts bound to evidence and captured collections are read."""
    check_clause(clause)
    cond, exceptions = clause.get("condition"), clause.get("exceptions") or []
    names = sorted(
        facts_in(cond).union(*(facts_in(e) for e in exceptions)) if exceptions else facts_in(cond)
    )
    facts, unavailable = {}, []
    for n in names:
        v, ok = _fact_value(clause, n, case, evidence)
        if ok:
            facts[n] = v
        else:
            unavailable.append(n)
    receipt = {
        "schema": SCHEMA,
        **identity(clause),
        "case_id": (case or {}).get("case_id"),
        "condition": cond,
        "exceptions": exceptions,
        "zen_expression": compile_zen(cond),
        "facts_used": facts,
        "consumed_by": list(clause.get("criteria") or []),
    }
    gaps = coverage(clause, env)
    if gaps:
        return {**receipt, "outcome": "setup_gap", "setup_gaps": gaps}
    ok, trace = evaluate(cond, facts)
    if ok is None:
        return {**receipt, "outcome": "unresolved", "missing_facts": trace["missing"]}
    if ok is False:
        return {**receipt, "outcome": "skipped", "failed": trace["failed"]}
    for i, e in enumerate(exceptions):
        hit, etrace = evaluate(e, facts)
        if hit is None:
            return {**receipt, "outcome": "unresolved", "missing_facts": etrace["missing"]}
        if hit:
            return {
                **receipt,
                "outcome": "skipped",
                "exception": {"index": i, "matched": etrace["matched"]},
            }
    out = {**receipt, "outcome": "applies", "matched": trace["matched"]}
    if evidence is not None:
        # A check that reads a collection the episode did not capture cannot tell a failure from missing evidence.
        missing = [
            t
            for t in (clause.get("obligation") or {}).get("evidence") or []
            if not _path(evidence, f"snapshots.end.{t}")[1]
        ]
        if missing:
            return {
                **out,
                "outcome": "setup_gap",
                "setup_gaps": [
                    {
                        "kind": "evidence",
                        "name": t,
                        "detail": f"{t} was not captured in this episode",
                    }
                    for t in missing
                ],
            }
    return out


def receipts(clauses, case, env, evidence=None, episode_id=None, zen=None, invoke=None):
    """One receipt per clause; with `zen` (the qualified ZEN plug-in's manifest) each decided condition is replayed on
    it before the receipts are hashed."""
    out = [resolve(cl, case, env, evidence) for cl in clauses]
    if zen:
        zen_confirm(out, zen, invoke=invoke)
    for r in out:
        if episode_id:
            r["episode_id"] = episode_id
        r["receipt_sha256"] = hashlib.sha256(
            json.dumps(r, sort_keys=True, default=str).encode()
        ).hexdigest()
    return out


# --- admission and scoring -----------------------------------------------------------------------------------


def admission_gaps(tasks, env):
    """Per task, the clauses whose tools or evidence the bound environment lacks, plus invalid clauses.
    Any entry blocks the run (E-002 §9.2): a setup gap is fixed before the run, never scored."""
    problems = []
    for t in tasks:
        for cl in task_clauses(t.get("actor")):
            try:
                check_clause(cl)
            except GymError as exc:
                problems.append(
                    {
                        "task_id": t.get("task_id"),
                        "clause": cl.get("clause_id"),
                        "detail": exc.message,
                    }
                )
                continue
            for g in coverage(cl, env):
                problems.append(
                    {
                        "task_id": t.get("task_id"),
                        "clause": f"{cl['clause_id']}@{cl['clause_version']}",
                        "detail": g["detail"],
                    }
                )
    return problems


def edge_holds(tasks, case_list, env_id):
    """Tasks focused on an edge case the bound version has no cases for: held, not failed mid-run (E-001 §3.6).
    Counted from the version's case list (the per-case tags), not its summary."""
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
    - None: at least one consuming clause applies (or none consumes it) → scored normally;
    - "not_applicable": every consuming clause was skipped → not scored (not a pass, not a fail);
    - "unresolved" / "setup_gap": excluded from the score and reported."""
    by = {}
    for r in receipts_ or []:
        for cid in r.get("consumed_by") or []:
            by.setdefault(cid, []).append(r["outcome"])
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


def zen_confirm(receipts_, manifest, invoke=None):
    """Replay every decided condition (Applies or Skipped on the condition, all its facts known) on the qualified ZEN
    plug-in and record the engine's answer on the receipt. If the plug-in and the resolver disagree, the clause becomes
    a Setup gap (never scored) and says so; if the plug-in cannot run, the resolver's answer stands and the receipt
    says the engine was not run. Receipts without a condition, or Unresolved / Setup gap ones, are left as they are."""
    from anvil.rlgym.plugins import contract, runner

    todo = [
        r
        for r in receipts_
        if r.get("condition")
        and (r["outcome"] == "applies" or (r["outcome"] == "skipped" and "failed" in r))
    ]
    if not todo:
        return receipts_
    label = f"{manifest.get('id')} {manifest.get('version')}"
    files, blocks = {}, []
    for i, r in enumerate(todo):
        rules = zen_rules(r["zen_expression"])
        digest = contract.jcs_sha256(rules)
        files[digest] = rules
        blocks.append(
            {
                "id": f"clause-{i}",
                "settings": {
                    "mode": "rule_check",
                    "rules": {
                        "ref": f"clause:{r['clause']['id']}@{r['clause']['version']}",
                        "sha256": digest,
                    },
                    "inputs": {name: f"clause_facts.{i}.{name}" for name in r["facts_used"]},
                },
            }
        )
    job = {
        "schema": contract.JOB,
        "blocks": blocks,
        "files": files,
        "evidence": {"clause_facts": {str(i): r["facts_used"] for i, r in enumerate(todo)}},
    }
    lines, why = {}, "no result"
    try:
        out = runner.run(manifest, job, invoke=invoke)
        lines = {x["block_id"]: x for x in out["results"]}
    except Exception as exc:  # noqa: BLE001 - the plug-in is a cross-check; its absence never blocks a receipt
        why = type(exc).__name__
    for i, r in enumerate(todo):
        line = lines.get(f"clause-{i}")
        if not line or line["verdict"] == "blocked":
            reason = (line or {}).get("detail") or why
            r["engine"] = {"plugin": label, "result": "not_run", "detail": str(reason)[:200]}
            continue
        zen_applies = line["verdict"] == "pass"
        agrees = zen_applies == (r["outcome"] == "applies")
        r["engine"] = {"plugin": label, "result": "agrees" if agrees else "disagrees"}
        if not agrees:
            r["outcome_before_engine"] = r["outcome"]
            r["outcome"] = "setup_gap"
            r["setup_gaps"] = [
                {
                    "kind": "engine",
                    "name": ZEN_PLUGIN,
                    "detail": f"The ZEN plug-in says {'applies' if zen_applies else 'does not apply'}; "
                    f"the resolver said {r['outcome_before_engine']}",
                }
            ]
    return receipts_
