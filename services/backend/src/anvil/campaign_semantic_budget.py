"""Pure conservative sizing, never spending authority or a qualification receipt.

Every selected case/model/repetition keeps all of its candidate and judge slots.
Oversized runs fail together; this code never drops cases, roles or evidence.
"""

from copy import deepcopy

from anvil import workspace_costs
from anvil.campaign_semantic_contract import (
    FixedBlueprint,
    FixedTemplate,
    bounded_json,
    parse_blueprint,
    parse_template,
)
from anvil.db import digest


def physical_bound(price, input_bytes, output_tokens):
    # Native providers bound input conservatively by bytes, plus protocol framing.
    return max(
        1,
        (
            (input_bytes + 1024) * workspace_costs.input_bound(price)
            + output_tokens * price["output_micro_usd_per_million_tokens"]
            + 999999
        )
        // 1000000,
    )


def quote(candidates, judge_blueprints, aggregate_cap_micro_usd, *, fixed_judges=None, now=None):
    """Input candidates are server-resolved plans, not user-supplied rates/models.

    v1 retains the saved candidate judge. Version2 takes separately resolved
    fixed judge snapshots/prices; neither path substitutes another model.
    The caller must verify current rights/calibration/qualification independently.
    """
    if type(aggregate_cap_micro_usd) is not int or not 0 < aggregate_cap_micro_usd <= 2000000:
        raise ValueError("The single QA aggregate envelope must remain within the approved cap")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 1000:
        raise ValueError("Exact nonempty bounded candidate population required")
    if not isinstance(judge_blueprints, dict):
        raise ValueError("Server-derived per-plan judge blueprints required")
    fixed_judges = {} if fixed_judges is None else fixed_judges
    if not isinstance(fixed_judges, dict) or len(fixed_judges) > 23:
        raise ValueError("Bounded separately frozen judge model and price map required")
    ids = [row["plan_id"] for row in candidates]
    if len(set(ids)) != len(ids) or not set(judge_blueprints) <= set(ids):
        raise ValueError("Judge quote cannot reference duplicate or foreign plans")
    reservations, slots, total = [], 0, 0
    used_judges, comparison_controls, comparison_modes = set(), {}, {}
    for row in candidates:
        calls, output = row["max_calls"], row["max_output_tokens"]
        if (
            type(calls) is not int
            or not 1 <= calls <= 1000
            or type(output) is not int
            or not 1 <= output <= 2048
        ):
            raise ValueError("Explicit physical candidate bounds required")
        model, price = row["model_binding"], row["pricing"]
        if not workspace_costs.current(price, now=now) or any(
            price.get(key) != model.get(key) for key in ("provider", "model_id")
        ):
            raise ValueError("Exact current model pricing required")
        slots += calls
        total += calls * physical_bound(price, 32768, output)
        specs = judge_blueprints.get(row["plan_id"], [])
        if not isinstance(specs, list) or len(specs) > 23:
            raise ValueError("Bounded exact judge batch list required")
        seen = set()
        for index, raw in enumerate(specs):
            spec = parse_blueprint(raw)
            judge_model, judge_price = model, price
            if isinstance(spec, FixedBlueprint):
                saved = fixed_judges.get(spec.model_binding_sha256)
                if (
                    spec.candidate_model_binding_sha256 != digest(model)
                    or not isinstance(saved, dict)
                    or not isinstance(saved.get("model_binding"), dict)
                    or not isinstance(saved.get("pricing"), dict)
                ):
                    raise ValueError("Exact separate judge and candidate quote snapshots required")
                judge_model, judge_price = saved["model_binding"], saved["pricing"]
                bounded_json(saved, 32768)
                if (
                    spec.model_binding_sha256 != digest(judge_model)
                    or str(spec.judge_model_profile_id) != judge_model.get("id")
                    or not workspace_costs.current(judge_price, now=now)
                    or any(
                        judge_price.get(key) != judge_model.get(key)
                        for key in ("provider", "model_id")
                    )
                ):
                    raise ValueError("Exact current independent judge model and pricing required")
                used_judges.add(spec.model_binding_sha256)
                # Matched candidates for one case/criterion cannot select
                # different evaluators or calibrations under a common label.
                for criterion in spec.criterion_ids:
                    key = (
                        spec.task_id,
                        spec.task_version,
                        spec.payload_sha256,
                        spec.case_id,
                        spec.case_snapshot_sha256,
                        criterion,
                    )
                    control = (
                        spec.configuration_sha256,
                        spec.calibration_sha256,
                        spec.source_reference_binding_sha256,
                        spec.evaluator_source_sha256,
                        spec.evaluator_version,
                        spec.model_binding_sha256,
                    )
                    if comparison_controls.setdefault(key, control) != control:
                        raise ValueError(
                            "Compared candidates require the same fixed judge controls"
                        )
            elif spec.model_binding_sha256 != digest(model):
                raise ValueError("Judge cannot upgrade or replace the saved model")
            for criterion in spec.criterion_ids:
                key = (
                    spec.task_id,
                    spec.task_version,
                    spec.payload_sha256,
                    spec.case_id,
                    spec.case_snapshot_sha256,
                    criterion,
                )
                mode = "fixed" if isinstance(spec, FixedBlueprint) else "candidate"
                if comparison_modes.setdefault(key, mode) != mode:
                    raise ValueError("Fixed and candidate judge designs cannot be silently mixed")
            overlap = seen.intersection(spec.criterion_ids)
            if overlap:
                raise ValueError("A criterion cannot consume multiple hidden judge attempts")
            seen.update(spec.criterion_ids)
            bound = physical_bound(judge_price, spec.max_input_bytes, spec.max_output_tokens)
            reservation = {
                "plan_id": row["plan_id"],
                "batch_index": index,
                "blueprint": spec.model_dump(mode="json"),
                "blueprint_sha256": digest(spec.model_dump(mode="json")),
                "model_binding_sha256": digest(judge_model),
                "pricing_sha256": digest(judge_price),
                "bound_micro_usd": bound,
                "physical_calls": 1,
            }
            if isinstance(spec, FixedBlueprint):
                reservation.update(
                    model_binding=deepcopy(judge_model), pricing=deepcopy(judge_price)
                )
            reservations.append(reservation)
            slots += 1
            total += bound
    if used_judges != set(fixed_judges):
        raise ValueError("Judge quote contains unused or foreign fixed model snapshots")
    if slots > 1000:
        raise ValueError(
            "Candidate and judge calls together exceed1000 physical slots; no population was reduced"
        )
    if total > aggregate_cap_micro_usd:
        raise ValueError(
            "Candidate and judge conservative cost exceeds the single aggregate cap; no population was reduced"
        )
    result = {
        "schema_version": "anvil.campaign-shared-call-quote.v2"
        if used_judges
        else "anvil.campaign-shared-call-quote.v1",
        "candidate_plan_ids": ids,
        "physical_call_slots": slots,
        "required_micro_usd": total,
        "aggregate_cap_micro_usd": aggregate_cap_micro_usd,
        "judge_reservations": reservations,
    }
    return result | {"sha256": digest(result)}


def plan_blueprints(prepared, native, model):
    """Exact case and independently qualified saved model, with no fallback."""
    from anvil.campaign_semantic_contract import bind_blueprint, fixed_blueprint

    templates = prepared.get("semantic_judge_templates", [])
    assignment = native.get("case_assignment") or {}
    matching = [
        item
        for item in templates
        if item["task_id"] == native.get("task_id")
        and item["task_version"] == native.get("revision_id")
        and item["payload_sha256"] == native.get("payload_sha256")
        and item["case_id"] == assignment.get("case_id")
        and item["case_snapshot_sha256"] == assignment.get("snapshot_sha256")
    ]
    if not matching:
        raise ValueError("Every selected plan needs an exact frozen semantic template")
    support = prepared.get("semantic_judge_model_support") or {}
    if not isinstance(support, dict):
        raise ValueError("Exact model-purpose support map required")
    groups = {}
    for item in matching:
        key = (item["configuration_id"], tuple(item["criterion_ids"]))
        groups.setdefault(key, []).append(item)
    selected = []
    for variants in groups.values():
        eligible = []
        for item in variants:
            template = parse_template(item)
            supported = support.get(digest(item))
            expected = (
                template.judge_model_binding_sha256
                if isinstance(template, FixedTemplate)
                else digest(model)
            )
            if isinstance(supported, list) and expected in supported:
                if isinstance(template, FixedTemplate) and supported != [expected]:
                    raise ValueError("Fixed judge qualification cannot inherit candidate support")
                eligible.append(item)
        if len(eligible) != 1:
            raise ValueError(
                "Selected model is not uniquely judge-purpose qualified for every requested case and criterion"
            )
        selected.append(eligible[0])
    result = []
    for item in selected:
        template = parse_template(item)
        if isinstance(template, FixedTemplate):
            models = prepared.get("semantic_judge_models")
            saved = (
                models.get(template.judge_model_binding_sha256)
                if isinstance(models, dict)
                else None
            )
            if not isinstance(saved, dict):
                raise ValueError("Exact frozen independent judge snapshot required")
            result.append(fixed_blueprint(item, prepared["project_binding"], model, saved))
        else:
            result.append(bind_blueprint(item, prepared["project_binding"], model))
    return result


def fixed_judge_snapshots(prepared):
    """Join separately frozen server models/prices; no lookup or rate fallback."""
    models = prepared.get("semantic_judge_models", {})
    prices = prepared.get("semantic_judge_pricing", {})
    if not isinstance(models, dict) or not isinstance(prices, dict) or set(models) != set(prices):
        raise ValueError("Exact frozen independent judge model and pricing sets required")
    return {key: {"model_binding": model, "pricing": prices[key]} for key, model in models.items()}


def frozen_quote(prepared, plans, *, now=None):
    """Recompute the complete upfront envelope from immutable server plans."""
    if prepared.get("semantic_judge_gaps"):
        raise ValueError("Independent Anvil semantic qualification is incomplete")
    if not prepared.get("semantic_judge_templates"):
        return None
    candidates, blueprints = [], {}
    for plan in plans:
        config, pid = plan["config"], str(plan["id"])
        native = config.get("marketing_native_binding") or {}
        if config.get("marketing_paid") is not True:
            raise ValueError("Every semantic-quoted plan requires the exact Marketing purpose")
        candidates.append(
            {
                "plan_id": pid,
                "max_calls": config["max_calls"],
                "max_output_tokens": config["max_output_tokens"],
                "model_binding": config["workspace_model"],
                "pricing": config["pricing"],
            }
        )
        blueprints[pid] = plan_blueprints(prepared, native, config["workspace_model"])
    return quote(
        candidates,
        blueprints,
        prepared["aggregate_cap_micro_usd"],
        fixed_judges=fixed_judge_snapshots(prepared),
        now=now,
    )


def issues(c, group, plans):
    try:
        expected = frozen_quote(group["snapshot"]["preparation"], plans)
        if expected != group["snapshot"].get("shared_call_quote"):
            return ["semantic_upfront_shared_quote_changed"]
        if expected is None:
            return []
        fields = "plan_id,batch_index,blueprint,blueprint_sha256,model_binding_sha256,pricing_sha256,bound_micro_usd,physical_calls"
        if expected["schema_version"] == "anvil.campaign-shared-call-quote.v2":
            fields += ",model_binding,pricing"
        rows = c.execute(
            "SELECT "
            + fields
            + " FROM marketing_runtime.semantic_quotes WHERE group_id=%s ORDER BY plan_id,batch_index",
            (group["id"],),
        ).fetchall()
        actual = [{**dict(row), "plan_id": str(row["plan_id"])} for row in rows]
        for row in actual:
            if row["blueprint"]["schema_version"] == "anvil.campaign-semantic-judge-blueprint.v1":
                if row.get("model_binding") is None and row.get("pricing") is None:
                    row.pop("model_binding", None)
                    row.pop("pricing", None)
        wanted = sorted(
            expected["judge_reservations"], key=lambda row: (row["plan_id"], row["batch_index"])
        )
        return [] if actual == wanted else ["semantic_exact_upfront_reservations_required"]
    except (ValueError, KeyError, TypeError):
        return ["semantic_upfront_model_price_or_population_changed"]
