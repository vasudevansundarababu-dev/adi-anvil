"""D-034 (E-004 §3.1): how each criterion is scored, in plain words, from the records the scorer itself runs on.

One function describes the effective grader of a criterion: the evaluator configuration version (its runner and any
RL Gym checks, D-041), the template's verifier blocks for that criterion, the plug-in versions bound to them (GoRules
ZEN, Promptfoo), the judge (model, approval, exact prompt, threshold, share of the criterion) and, when the task has
one, S7's points (D-036). `grader_sha256` hashes exactly those inputs, so a run's manifest freezes which grader scored
it, and a later draft grader (E-004 §3.2) can never pass for an approved one.

- Project page: the versions that bind now (`for_project`).
- Run page and report: what the run used (`for_run`): the scoring pass's configuration versions, the manifest's
  template version and its frozen plug-in bindings, never the project's current binding.
Nothing is guessed: what can't be read is shown as "Unknown scorer".
"""

from anvil.rlgym.common import sha

UNKNOWN = "Unknown scorer"
PLUGINS = {"gorules-zen": "GoRules ZEN decision rules", "promptfoo": "Promptfoo"}
RUNTIMES = {
    "zen": "GoRules ZEN decision rules",
    "gorules-zen": "GoRules ZEN decision rules",
    "promptfoo": "Promptfoo",
    "pramaana": "Pramaana",
}
EVIDENCE = {
    "snapshots": "the environment's state at the start and end of the episode",
    "tool_events": "the agent's tool-call log",
    "final_output": "the agent's final answer",
    "plugin": "what the plug-in is given (state, tool log, answer)",
}
SOURCES = {
    "case_reference": "this case's reference answers (hidden from the agent)",
    "sme": "values an SME set in the task's private part",
}
STATE_OPS = {
    "equals": "equals",
    "in": "is one of",
    "contains": "contains",
    "exists_where": "has a row where it equals",
    "not_exists": "has no row where it equals",
    "count": "row count equals",
    "changed": "changed",
    "unchanged": "is unchanged",
    "nothing_else_changed": "nothing else changed",
}


JUDGMENT_CHECKS = {
    "consistency": "the recommendation follows from the party assessments and risk",
    "consistency_5e": "the recommendation follows from the party assessments and risk (§5e: missing information first)",
    "decision": "the recommendation and each party's outcome, requests and referral match the reference",
    "risk_rating": "the risk rating and what its level requires",
    "rules_applied": "the rules cited are the ones that apply, at the version in force",
    "rule_in_force": "after a bulletin, the new rule version is cited",
    "tool_calls": "every required check, request and referral was made; nothing wrong was",
    "procedure_output": "the answer has every required field and a valid decision",
    "evidence_judgment": "issues raised only where the evidence shows them; screening read right",
    "rationale": "the rationale names the recommendation and cites a rule",
    "process_adherence": "every mandatory SOP step is done, in order",
    "missing_facts": "the missing facts the reference lists are stated",
    "audit_faithfulness": "the audit trail cites only data the environment returned (invented evidence is critical)",
}


def _judgment_criterion(config):
    from anvil.rlgym.catalog import judgment_configs

    return judgment_configs.grader_of(config)


def _src(value):
    if isinstance(value, dict):
        if value.get("case_reference"):
            return (
                f"the reference answer {value['case_reference'].replace('reference_answers.', '')}"
            )
        if value.get("slot") is not None:
            return "an SME value"
        if "fixed" in value:
            return repr(value["fixed"])
    return None


def _rule_check(r):
    kind = r.get("kind")
    what, reads = {
        "tool_called": (f"the agent called {r.get('tool')}", "tool_events"),
        "tool_not_called": (f"the agent did not call {r.get('tool')}", "tool_events"),
        "output_equals": (
            f"answer field {r.get('field')} equals the reference {r.get('reference') or r.get('field')}",
            "final_output",
        ),
        "output_set_equals": (
            f"answer field {r.get('field')} has the same items as the reference {r.get('reference') or r.get('field')}",
            "final_output",
        ),
        "output_nonempty": (f"answer field {r.get('field')} is not empty", "final_output"),
    }.get(kind, (f"{kind or 'unnamed'} rule", None))
    return {"id": kind or "rule", "kind": "rule", "what": what, "reads": reads}


def _judge(settings, approvals):
    model = settings.get("judge")
    if not model:
        return None
    from anvil.rlgym.live import judge as lj

    approval = (approvals or {}).get(model)
    threshold = float(settings.get("threshold", lj.DEFAULT_THRESHOLD))
    return {
        "model": model,
        "approval": approval,
        "live": bool(approval) and model != "mock-judge",
        "system_prompt": lj.JUDGE,
        "prompt": f"Rubric: {settings.get('rubric', '')}\n\nText to grade:\n<{settings.get('target') or 'output'}>",
        "rubric": settings.get("rubric"),
        "target": settings.get("target"),
        "threshold": threshold,
        "assertion": settings.get("assertion"),
    }


def _block_check(b, plugin_version, approvals):
    name = b.get("name") or b.get("id")
    if b.get("plugin"):
        pid = b["plugin"].get("id")
        settings = b.get("settings") or {}
        judge = _judge(settings, approvals)
        bits = [PLUGINS.get(pid, f"{pid} plug-in")]
        if plugin_version:
            bits.append(plugin_version)
        if settings.get("mode"):
            bits.append(f"mode {settings['mode']}")
        if (settings.get("rules") or {}).get("sha256"):
            bits.append(f"rules file {settings['rules']['sha256'][:12]}")
        if judge:
            bits.append(f"LLM judge {judge['model']}, pass at score ≥ {judge['threshold']:g}")
        out = {
            "id": b.get("id"),
            "kind": "plugin",
            "plugin": pid,
            "what": f"{name}: {' · '.join(bits)}",
            "reads": "plugin",
        }
        if judge:
            out["judge"] = judge
        if b.get("share_percent"):
            out["share_percent"] = float(b["share_percent"])
        return out
    kind = b.get("kind")
    if kind == "state":
        target = b.get("table") or "*"
        if b.get("column"):
            target += f".{b['column']}"
        src = _src(b.get("value"))
        what = f"{name}: end state {target} {STATE_OPS.get(b.get('op'), b.get('op'))}" + (
            f" {src}" if src else ""
        )
        return {"id": b.get("id"), "kind": "state", "what": what, "reads": "snapshots"}
    if kind == "process":
        order = (f", before {b['before']}" if b.get("before") else "") + (
            f", after {b['after']}" if b.get("after") else ""
        )
        return {
            "id": b.get("id"),
            "kind": "process",
            "what": f"{name}: the tool log shows {b.get('must_call')}{order}",
            "reads": "tool_events",
        }
    if kind == "rubric":
        return {
            "id": b.get("id"),
            "kind": "rubric",
            "what": f"{name}: rubric {b.get('rubric_id')}",
            "reads": "final_output",
        }
    if kind == "recommended":
        return {
            "id": b.get("id"),
            "kind": "recommended",
            "what": f"{name}: a recommend call succeeded or a recommendation is recorded (RL Gym check, D-042)",
            "reads": "tool_events",
        }
    if kind == "request_party":
        return {
            "id": b.get("id"),
            "kind": "request_party",
            "what": f"{name}: the request names the party whose start-state record lacks the item (RL Gym check, D-041)",
            "reads": "snapshots",
        }
    return {
        "id": b.get("id"),
        "kind": kind or "unknown",
        "what": f"{name}: {kind or 'unknown'} check",
        "reads": None,
    }


def describe(
    config,
    runtime_id,
    blocks=None,
    expected_values_from=None,
    plugin_versions=None,
    approvals=None,
    s7=None,
):
    """{"scored_by", "checks", "evidence", "expected_values", "judges", "points"}."""
    config = config or {}
    plugin_versions = plugin_versions or {}
    out = {"checks": [], "evidence": [], "expected_values": None, "judges": [], "points": None}
    if config.get("runner") == "verifier_blocks":
        mine = list(blocks or [])
        if config.get("runner_version", 1) >= 2:
            mine += config.get("extra_blocks") or []
        if not blocks:
            return {
                **out,
                "scored_by": f"{UNKNOWN}: the template has no verifier blocks for this criterion",
            }
        checks = [_block_check(b, plugin_versions.get(b.get("id")), approvals) for b in mine]
        parts = [f"Python checks (verifier blocks, runner v{config.get('runner_version', 1)})"]
        for pid in dict.fromkeys(c["plugin"] for c in checks if c["kind"] == "plugin"):
            judges = [
                c["judge"]["model"] for c in checks if c.get("plugin") == pid and c.get("judge")
            ]
            parts.append(
                PLUGINS.get(pid, f"{pid} plug-in")
                + (f" with LLM judge {', '.join(judges)}" if judges else "")
            )
        if any(c["kind"] == "rubric" for c in checks):
            parts.append(
                f"LLM judge {config['judge'].get('model_id')}"
                if config.get("judge")
                else "local mock judge"
            )
        if any(c["kind"] == "request_party" for c in checks):
            parts.append("RL Gym party check")
        if any(c["kind"] == "recommended" for c in checks):
            parts.append("RL Gym recommendation check")
        uses_reference = any(_src(b.get("value")) for b in mine) or any(
            c["kind"] in ("plugin", "request_party") for c in checks
        )
        out["expected_values"] = (
            SOURCES.get(expected_values_from or "case_reference") if uses_reference else None
        )
    elif _judgment_criterion(config):
        # KYC Judgment v1 activation bridge (config.grader kyc-judgment.g2.<criterion>): RL Gym's judgment checks, run
        # outside the sandbox against the run's frozen policy library and the case's reference.
        from anvil.rlgym.catalog import judgment_configs

        crit = _judgment_criterion(config)
        reads = config.get("evidence") if config.get("evidence") in EVIDENCE else "final_output"
        if crit == "tool_calls":
            reads = "tool_events"
        checks = [
            {
                "id": f"{crit}.{name}",
                "kind": "judgment",
                "what": JUDGMENT_CHECKS.get(name, name.replace("_", " ")),
                "reads": reads,
            }
            for name in judgment_configs.checks_for(crit, config)
        ]
        parts = [f"KYC Judgment checks ({crit})"]
        out["expected_values"] = SOURCES["case_reference"]
    elif config.get("rules"):
        checks = [_rule_check(r) for r in config["rules"]]
        parts = ["Python rule checks"]
        if any(r.get("kind") in ("output_equals", "output_set_equals") for r in config["rules"]):
            out["expected_values"] = SOURCES["case_reference"]
    elif runtime_id in RUNTIMES:
        return {**out, "scored_by": RUNTIMES[runtime_id]}
    else:
        return {**out, "scored_by": UNKNOWN}
    reads = [c["reads"] for c in checks if c.get("reads") in EVIDENCE]
    if not reads and config.get("evidence") in EVIDENCE:
        reads = [config["evidence"]]
    out.update(
        scored_by=" + ".join(parts),
        checks=checks,
        evidence=[EVIDENCE[r] for r in dict.fromkeys(reads)],
        judges=[
            {**c["judge"], "block_id": c["id"], "share_percent": c.get("share_percent")}
            for c in checks
            if c.get("judge")
        ],
    )
    if s7:
        out["points"] = s7
    return out


def grader_sha256(config, blocks, plugin_versions):
    """What scored the criterion, as one hash: configuration, blocks and bound plug-in versions."""
    return sha({"config": config or {}, "blocks": blocks or [], "plugins": plugin_versions or {}})


def _config(c, ws, configuration_id, version):
    return c.execute(
        """SELECT e.config, f.runtime_id FROM catalog.evaluator_configurations e
           JOIN catalog.framework_versions f ON f.id=e.framework_version_id
           WHERE e.workspace_id=%s AND e.id=%s AND e.version=%s""",
        (ws, configuration_id, version),
    ).fetchone()


def _template(c, ws, template_id, version):
    blocks = {
        r["criterion_id"]: r["verifier_blocks"]
        for r in c.execute(
            "SELECT criterion_id, verifier_blocks FROM catalog.template_criteria WHERE workspace_id=%s AND template_id=%s AND version=%s",
            (ws, template_id, version),
        ).fetchall()
    }
    act = c.execute(
        "SELECT expected_values_from FROM catalog.template_activations WHERE workspace_id=%s AND template_id=%s AND version=%s",
        (ws, template_id, version),
    ).fetchone()
    return blocks, (act or {}).get("expected_values_from")


def _judge_approvals(c, ws):
    """model_id → the active live approval that lets it judge (id), for showing which approval a judge runs under."""
    return {
        r["model_id"]: r["id"]
        for r in c.execute(
            """SELECT id, model_id FROM systems.live_approvals WHERE workspace_id=%s AND 'judge' = ANY(uses)
               AND revoked_at IS NULL AND expires_at > now() ORDER BY approved_at""",
            (ws,),
        ).fetchall()
    }


def for_project(c, ws, project, criteria):
    """criterion_id → description, for the configuration versions that bind now and the plug-ins that would bind."""
    from anvil.rlgym.plugins import service as plugins

    blocks, source = _template(c, ws, project["template_id"], project["template_version"])
    approvals = _judge_approvals(c, ws)
    out = {}
    for cr in criteria:
        row = cr.get("binds_now") and _config(c, ws, cr["configuration_id"], cr["binds_now"])
        if not row:
            out[cr["criterion_id"]] = {
                **describe(None, None),
                "scored_by": f"{UNKNOWN}: no version binds now",
            }
            continue
        mine = blocks.get(cr["criterion_id"]) or []
        versions = {}
        for b in mine:
            if b.get("plugin"):
                p = plugins.resolve(c, b["plugin"])
                versions[b["id"]] = p["version"] if p else None
        desc = describe(
            row["config"],
            row["runtime_id"],
            mine,
            source,
            {k: v and f"v{v} (binds now)" for k, v in versions.items()},
            approvals,
        )
        desc["grader_sha256"] = grader_sha256(row["config"], mine, versions)
        out[cr["criterion_id"]] = desc
    return out


def for_admission(c, ws, project, evaluator_versions, bound_plugins):
    """criterion_id → {"grader_sha256", "scored_by"}: frozen in the manifest (D-034), from what admission bound."""
    blocks, source = _template(c, ws, project["template_id"], project["template_version"])
    out = {}
    for ev in evaluator_versions or []:
        row = _config(c, ws, ev["configuration_id"], ev["version"])
        mine = blocks.get(ev["criterion_id"]) or []
        versions = {
            b["id"]: (bound_plugins or {}).get(b["id"], {}).get("version")
            for b in mine
            if b.get("plugin")
        }
        desc = describe(row and row["config"], row and row["runtime_id"], mine, source, versions)
        out[ev["criterion_id"]] = {
            "grader_sha256": grader_sha256(row and row["config"], mine, versions),
            "scored_by": desc["scored_by"],
        }
    return out


def for_run(c, ws, manifest, evaluator_versions):
    """criterion_id → description, from what the run used (never the project's current binding)."""
    t = manifest.get("template") or {}
    blocks, source = _template(c, ws, t.get("id"), t.get("version"))
    frozen = {k: f"v{v['version']}" for k, v in (manifest.get("plugins") or {}).items()}
    s7 = next((tk["scoring"] for tk in manifest.get("tasks") or [] if tk.get("scoring")), None)
    approvals = _judge_approvals(c, ws)
    out = {}
    for ev in evaluator_versions or []:
        row = _config(c, ws, ev["configuration_id"], ev["version"])
        if not row:
            out[ev["criterion_id"]] = describe(None, None)
            continue
        pts = (
            {
                "weight": s7["weights"].get(ev["criterion_id"]),
                "anchors": s7["anchors"],
                "critical": ev["criterion_id"] in s7["critical"],
            }
            if s7
            else None
        )
        out[ev["criterion_id"]] = describe(
            row["config"],
            row["runtime_id"],
            blocks.get(ev["criterion_id"]) or [],
            source,
            frozen,
            approvals,
            pts,
        )
        out[ev["criterion_id"]]["frozen"] = (manifest.get("graders") or {}).get(ev["criterion_id"])
    return out
