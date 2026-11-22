"""Verifier blocks (adi.verifier-blocks.v1, D21; work package 2.11): validation at activation, the rubric registry, and
the synthetic known cases a verifier-blocks configuration is tested on.

Studio's template owns each criterion's blocks (State, Process, Rubric) and where their open values come from
(`case_reference` or `sme`). The environment version owns the collections State blocks read. The RL Gym owns the code
that runs the blocks: an evaluator configuration `{"runner": "verifier_blocks", "runner_version": 1}` per criterion, in
the Python scoring sandbox (`scoring/sandbox_runner.py`). A runner bug is fixed as a new configuration version (D20).
"""

import copy

RUNNER = "verifier_blocks"
KINDS = ("state", "process", "rubric")
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
NEEDS_COLUMN = ("equals", "in", "contains")
SOURCES = ("case_reference", "sme")
CASE = "kc-case-001"

# The RL Gym's rubric registry. Locally every rubric uses the mock judge (deterministic, no model); a Promptfoo judge
# replaces it when that framework is installed and a live judge is approved.
RUBRICS = [
    {
        "rubric_id": "customer_tone_polite",
        "version": 1,
        "title": "Customer tone is polite",
        "description": "No impolite or dismissive wording in what the agent writes.",
        "judge": "mock (local, no model)",
    },
    {
        "rubric_id": "reason_is_specific",
        "version": 1,
        "title": "Reason is specific",
        "description": "The agent states a specific reason (at least a short sentence), not a bare label.",
        "judge": "mock (local, no model)",
    },
    {
        "rubric_id": "evidence_cited",
        "version": 1,
        "title": "Evidence is cited",
        "description": "At least one finding or write cites the evidence it relies on.",
        "judge": "mock (local, no model)",
    },
]
RUBRIC_IDS = {r["rubric_id"] for r in RUBRICS}


def is_blocks_config(config):
    return isinstance(config, dict) and config.get("runner") == RUNNER


def collections(env):
    """{name: {fields}} declared by the environment version (`schema.collections`), and the reference fields."""
    schema = (env or {}).get("schema") or {}
    out, reference = {}, set()
    for col in schema.get("collections") or []:
        fields = {f["name"] if isinstance(f, dict) else f for f in col.get("fields") or []}
        if col["name"] == "reference_answers":
            reference = fields
        else:
            out[col["name"]] = fields
    return out, reference


def enums(env):
    """{(collection, field): allowed values} for fields the version declares as enums."""
    out = {}
    for col in ((env or {}).get("schema") or {}).get("collections") or []:
        for f in col.get("fields") or []:
            if isinstance(f, dict) and f.get("enum"):
                out[(col["name"], f["name"])] = list(f["enum"])
    return out


def operations(env):
    ops = (env or {}).get("operations") or []
    return {o["operation_id"] if isinstance(o, dict) else o for o in ops}


def check_blocks(blocks, env, expected_values_from, failure_taxonomy):
    """Reasons a criterion's blocks cannot run on `env` (empty when they can)."""
    cols, ref_fields = collections(env)
    allowed_values = enums(env)
    ops = operations(env)
    reasons = []
    if expected_values_from not in SOURCES:
        reasons.append("expected_values_from must be case_reference or sme")
    share = 0.0
    seen = set()
    for b in blocks or []:
        bid = b.get("id") or "?"
        if b.get("plugin"):
            seen.add(bid)
            continue  # checked against the plug-in's settings schema (plugin_reasons)
        if bid in seen:
            reasons.append(f"{bid}: duplicate block id")
        seen.add(bid)
        kind = b.get("kind")
        if kind not in KINDS:
            reasons.append(f"{bid}: unknown kind {kind!r}")
            continue
        if b.get("on_fail") not in (failure_taxonomy or []):
            reasons.append(
                f"{bid}: on_fail {b.get('on_fail')!r} is not in the template's failure_taxonomy"
            )
        if kind == "state" and b.get("op") == "nothing_else_changed":
            # Compares every declared collection, so it names no table (omitted or "*"); `allow` lists extra ones.
            if b.get("table") not in (None, "", "*") and b["table"] not in cols:
                reasons.append(f"{bid}: collection {b['table']!r} is not declared by {env['id']}")
            for name in b.get("allow") or []:
                if name not in cols:
                    reasons.append(f"{bid}: allowed collection {name!r} is not declared")
            continue
        if kind == "state":
            table, col, op = b.get("table"), b.get("column"), b.get("op")
            if table not in cols:
                reasons.append(f"{bid}: collection {table!r} is not declared by {env['id']}")
            elif col and col not in cols[table]:
                reasons.append(f"{bid}: field {table}.{col} is not declared by {env['id']}")
            if op not in STATE_OPS:
                reasons.append(f"{bid}: unknown op {op!r}")
            elif op in NEEDS_COLUMN and not col:
                reasons.append(f"{bid}: op {op} needs a column")
            value = b.get("value")
            choices = allowed_values.get((table, col))
            if choices and isinstance(value, dict) and "fixed" in value:
                fixed = value["fixed"] if isinstance(value["fixed"], list) else [value["fixed"]]
                wrong = [v for v in fixed if v not in choices and v not in (None, "none")]
                if wrong:
                    reasons.append(f"{bid}: {wrong} not in {table}.{col}'s values {choices}")
            if b.get("row", "case") not in ("case", "any"):
                reasons.append(f"{bid}: row must be case or any")
            elif (
                b.get("row", "case") == "case"
                and table in cols
                and "application_id" not in cols[table]
            ):
                reasons.append(f"{bid}: row case needs {table}.application_id")
            for name in b.get("allow") or []:
                if name not in cols:
                    reasons.append(f"{bid}: allowed collection {name!r} is not declared")
            reasons += _value_reasons(bid, b.get("value"), expected_values_from, ref_fields)
        elif kind == "process":
            for key in ("must_call", "before", "after"):
                if b.get(key) and b[key] not in ops:
                    reasons.append(
                        f"{bid}: {key} {b[key]!r} is not a declared operation of {env['id']}"
                    )
            if not b.get("must_call"):
                reasons.append(f"{bid}: process block needs must_call")
            for name, spec in (b.get("args_match") or {}).items():
                if spec != "$case":
                    reasons += _value_reasons(
                        f"{bid}.args_match.{name}", spec, expected_values_from, ref_fields
                    )
        else:
            if b.get("rubric_id") not in RUBRIC_IDS:
                reasons.append(
                    f"{bid}: rubric {b.get('rubric_id')!r} is not in the RL Gym's rubric registry"
                )
            try:
                share += float(b.get("share_percent") or 0)
            except (TypeError, ValueError):
                reasons.append(f"{bid}: share_percent must be a number")
    if share > 100:
        reasons.append(f"rubric shares add up to {share:g}%, above 100%")
    return reasons


def _value_reasons(bid, value, source, ref_fields):
    if value is None or not isinstance(value, dict) or "fixed" in value:
        return []
    if source == "case_reference":
        path = value.get("case_reference")
        if not path:
            return [
                f"{bid}: value needs case_reference (expected_values_from is case_reference) or fixed"
            ]
        field = path.split(".", 1)[1] if path.startswith("reference_answers.") else None
        if not field or field not in ref_fields:
            return [f"{bid}: {path!r} is not a declared reference_answers field"]
        return []
    if source == "sme" and value.get("slot") is None:
        return [f"{bid}: value needs slot (expected_values_from is sme) or fixed"]
    return []


# --- synthetic known cases (A-06 with blocks) ---------------------------------------------------------------------


def _expected(value, source):
    """A synthetic expected value and where it is stored (reference field or slot id)."""
    if value is None:
        return None, None, None
    if not isinstance(value, dict):
        return value, None, None
    if "fixed" in value:
        return value["fixed"], None, None
    if source == "case_reference" and value.get("case_reference"):
        field = value["case_reference"].split(".", 1)[-1]
        return f"expected-{field}", "reference", field
    slot = value.get("slot")
    if isinstance(slot, dict):
        sid = slot.get("id")
        choices = slot.get("choices") or []
        return (choices[0] if choices else f"expected-{sid}"), "slot", sid
    return f"expected-{slot}", "slot", slot


def plugin_reasons(c, blocks, failure_taxonomy, files):
    """Plug-in blocks (D22): a qualified version binds now, the settings are valid against its settings_schema, the
    evidence paths start with what it reads, on_fail is a template failure code, and a rules file is in the release."""
    from anvil.rlgym.plugins import contract
    from anvil.rlgym.plugins import service as plugins

    reasons = []
    for b in blocks or []:
        if not b.get("plugin"):
            continue
        bid = b.get("id") or "?"
        p = b["plugin"]
        row = plugins.resolve(c, p) if isinstance(p, dict) and p.get("id") else None
        if not row:
            reasons.append(
                f"{bid}: no qualified version of plug-in {p.get('id') if isinstance(p, dict) else p!r}"
            )
            continue
        settings = b.get("settings") or {}
        reasons += [
            f"{bid}: {e}" for e in contract.schema_errors(row["settings_schema"] or {}, settings)
        ]
        if b.get("on_fail") not in (failure_taxonomy or []):
            reasons.append(
                f"{bid}: on_fail {b.get('on_fail')!r} is not in the template's failure_taxonomy"
            )
        reads = set(row["reads"] or [])
        paths = list((settings.get("inputs") or {}).values()) + [
            x.get("agent_path") for x in settings.get("compare") or [] if isinstance(x, dict)
        ]
        for path in filter(None, paths):
            if str(path).split(".", 1)[0].split("[", 1)[0] not in reads:
                reasons.append(f"{bid}: {path} reads evidence the plug-in does not read")
        sha = (
            (settings.get("rules") or {}).get("sha256")
            if isinstance(settings.get("rules"), dict)
            else None
        )
        if sha and sha not in (files or {}):
            reasons.append(f"{bid}: rules file {sha[:12]}… is not in the release's verifier_files")
    return reasons


def legacy(blocks):
    return [b for b in blocks or [] if not b.get("plugin")]


def known_cases(blocks, expected_values_from="case_reference"):
    """Allowed (every block holds), disallowed (the first State block, else the first Process block, broken) and
    missing evidence (no snapshot, or no tool log when there is no State block). Each carries the evidence, reference,
    slots and the block whose on_fail the disallowed case must report. Plug-in blocks are left out: each plug-in
    version is qualified by its own known cases."""
    blocks = legacy(blocks)
    reference, slots = {}, {}
    start, end = {}, {}
    rows_by_table = {}
    counts = {}
    unchanged = set()

    def value_of(b):
        v, where, key = _expected(b.get("value"), expected_values_from)
        if where == "reference":
            reference[key] = v if b.get("op") != "count" else 1
            v = reference[key]
        elif where == "slot":
            slots[key] = v if b.get("op") != "count" else 1
            v = slots[key]
        return v

    for b in blocks:
        if b["kind"] != "state":
            continue
        table, op, col = b.get("table"), b["op"], b.get("column")
        if op == "nothing_else_changed":
            continue  # names no table; checked against the others below
        start.setdefault(table, [])
        end.setdefault(table, [])
        if op == "not_exists":
            value_of(b)
            continue
        if op in ("changed", "nothing_else_changed"):
            continue
        if op == "unchanged":
            unchanged.add(table)
            continue
        v = value_of(b)
        row = rows_by_table.setdefault(table, {"application_id": CASE})
        if op == "count":
            counts[table] = int(v if v is not None else 1)
        elif col:
            row[col] = v[0] if op == "in" and isinstance(v, list) and v else v
            if op == "contains":
                row[col] = [v] if not isinstance(v, str) else f"... {v} ..."
    for table, row in rows_by_table.items():
        end[table] = [dict(row) for _ in range(counts.get(table, 1))]
    for b in blocks:
        if b["kind"] == "state" and b["op"] == "changed" and not end[b["table"]]:
            end[b["table"]] = [{"application_id": CASE, "id": "row-1"}]
    for table in unchanged:
        start[table] = copy.deepcopy(end.get(table) or [{"application_id": CASE, "id": "seed-1"}])
        end[table] = copy.deepcopy(start[table])
    events = []
    procs = [b for b in blocks if b["kind"] == "process"]
    for b in procs:
        if b.get("after"):
            events.append({"tool": b["after"], "args": {}, "ok": True})
    for b in procs:
        args = {}
        for name, spec in (b.get("args_match") or {}).items():
            args[name] = CASE if spec == "$case" else value_of({"value": spec, "op": "equals"})
        events.append({"tool": b["must_call"], "args": args, "ok": True})
    for b in procs:
        if b.get("before"):
            events.append({"tool": b["before"], "args": {}, "ok": True})
    final = {
        "findings": [
            {"text": "Specific synthetic reason for the known case", "evidence_ref": "doc-1"}
        ]
    }
    allowed = {
        "snapshots": {"start": start, "end": end},
        "tool_events": events,
        "final_output": final,
    }
    disallowed = copy.deepcopy(allowed)
    broken = next((b for b in blocks if b["kind"] == "state"), None) or next(iter(procs), None)
    if broken and broken["kind"] == "state":
        _break_state(broken, disallowed["snapshots"])
    elif broken:
        disallowed["tool_events"] = [
            e for e in disallowed["tool_events"] if e["tool"] != broken["must_call"]
        ]
    missing = copy.deepcopy(allowed)
    if any(b["kind"] == "state" for b in blocks):
        missing.pop("snapshots")
    else:
        missing.pop("tool_events")
        missing.pop("final_output")
    common = {"case_id": CASE, "reference": reference, "slots": slots}
    return {
        "allowed": {**common, "evidence": allowed, "expect": "pass"},
        "disallowed": {
            **common,
            "evidence": disallowed,
            "expect": "fail",
            "expect_block": broken and broken["id"],
            "expect_on_fail": broken and broken.get("on_fail"),
        },
        "missing_evidence": {**common, "evidence": missing, "expect": "blocked"},
    }


def _break_state(b, snaps):
    table, op, col = b.get("table"), b["op"], b.get("column")
    end = snaps["end"]
    if op == "nothing_else_changed":
        end["unexpected_table"] = [{"id": "unexpected"}]
        snaps["start"].setdefault("unexpected_table", [])
        return
    rows = end.setdefault(table, [])
    if op in ("equals", "in", "contains"):
        for r in rows:
            r[col] = f"not-{r.get(col)}"
    elif op == "count":
        rows.append(dict(rows[0]) if rows else {"application_id": CASE})
    elif op == "exists_where":
        end[table] = []
    elif op == "not_exists":
        rows.append({"application_id": CASE, **({col: "present"} if col else {})})
    elif op == "changed":
        snaps["start"][table] = copy.deepcopy(rows)
    elif op == "unchanged":
        rows.append({"application_id": CASE, "id": "unexpected"})
    elif op == "nothing_else_changed":
        end["unexpected_table"] = [{"id": "unexpected"}]
        snaps["start"].setdefault("unexpected_table", [])
