"""Separate Marketing custody inside the existing shared/pilot group envelope.

No key resolution, provider call, separate budget or manual manifest ceremony.
"""

import os

from anvil import pilot_environment
from anvil.db import Jsonb, digest, one
from anvil.marketing_paid_qualification import installed
from anvil.marketing_paid_session import require_frozen
from anvil.praxis_generic_contract import digest as wire_digest


def bind(c, plan):
    if plan["config"].get("marketing_paid") is not True:
        raise RuntimeError("marketing_native_plan_required")
    native = plan["config"].get("marketing_native_binding") or {}
    assignment = native.get("case_assignment") or {}
    context = require_frozen(c, plan["project_id"], native, case_id=assignment.get("case_id"))
    expected = {
        "project_id": str(plan["project_id"]),
        "plan_id": str(plan["id"]),
        "group_id": plan["config"]["workspace_execution_group"],
        "task_group_id": native["task_group_id"],
        "resolved_task_id": native["resolved_task_id"],
        "dataset_id": native["dataset_import_id"],
        "case_id": assignment["case_id"],
        "native_binding": native,
        "native_binding_sha256": digest(native),
        "execution": context["execution"],
        "execution_sha256": wire_digest(context["execution"]),
        "max_calls": plan["config"]["max_calls"],
        "created_by": str(plan["created_by"]),
    }
    old = one(
        c,
        "SELECT * FROM marketing_runtime.paid_agent_bindings WHERE project_id=%s AND plan_id=%s",
        (plan["project_id"], plan["id"]),
    )
    if old:
        if any(
            (str(old[key]) if key.endswith("_id") or key == "created_by" else old[key]) != value
            for key, value in expected.items()
        ):
            raise RuntimeError("marketing_paid_binding_immutable_conflict")
        return old
    return c.execute(
        "INSERT INTO marketing_runtime.paid_agent_bindings(project_id,plan_id,group_id,task_group_id,resolved_task_id,dataset_id,case_id,native_binding,native_binding_sha256,execution,execution_sha256,max_calls,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (
            expected["project_id"],
            expected["plan_id"],
            expected["group_id"],
            expected["task_group_id"],
            expected["resolved_task_id"],
            expected["dataset_id"],
            expected["case_id"],
            Jsonb(native),
            digest(native),
            Jsonb(context["execution"]),
            wire_digest(context["execution"]),
            expected["max_calls"],
            expected["created_by"],
        ),
    ).fetchone()


def issues(c, plan):
    if plan["config"].get("marketing_paid") is not True:
        return []
    missing = []
    if os.environ.get("ANVIL_MARKETING_PAID_ENABLED") != "true":
        missing.append("marketing_paid_admission_disabled")
    try:
        environment = pilot_environment.current()
    except ValueError:
        environment = None
    if environment != "qa":
        missing.append("marketing_paid_qa_only")
    native = plan["config"].get("marketing_native_binding") or {}
    missing.extend(installed(native.get("workflow_graph_sha256"))["missing"])
    try:
        require_frozen(c, plan["project_id"], native, case_id=native["case_assignment"]["case_id"])
        row = one(
            c,
            "SELECT * FROM marketing_runtime.paid_agent_bindings WHERE project_id=%s AND plan_id=%s",
            (plan["project_id"], plan["id"]),
        )
        if (
            not row
            or row["native_binding"] != native
            or row["native_binding_sha256"] != digest(native)
            or row["max_calls"] != plan["config"]["max_calls"]
            or row["execution_sha256"] != native["execution_sha256"]
            or wire_digest(row["execution"]) != row["execution_sha256"]
        ):
            missing.append("marketing_paid_source_or_role_binding_changed")
    except (ValueError, RuntimeError, KeyError, TypeError):
        missing.append("marketing_current_source_qualification_required")
    return sorted(set(missing))


def claim(c, group, plan, invocation, binding, request):
    """Last one-way SDK fence; cost/key/run/rights gates remain in the broker."""
    if plan["config"].get("marketing_paid") is not True or issues(c, plan):
        return False
    if (
        binding != plan["config"]["workspace_model"]
        or request.model != binding["model_id"]
        or request.max_output_tokens != plan["config"]["max_output_tokens"]
        or not 1 <= request.timeout_seconds <= plan["config"]["request_timeout_seconds"]
        or not 1 <= len(request.actor_text.encode()) <= 32768
    ):
        return False
    return one(
        c,
        "SELECT marketing_runtime.claim_paid_call(%s,%s,%s,%s) AS allowed",
        (group["id"], plan["id"], invocation["id"], invocation["reserved_micro_usd"]),
    )["allowed"]
