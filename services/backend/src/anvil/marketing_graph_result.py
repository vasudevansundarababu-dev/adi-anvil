"""Graph return consistency, never physical capture or successful finish proof."""

import re

from anvil.marketing_paid_contract import check_schema
from anvil.praxis_generic_contract import canonical, digest
from anvil.praxis_marketing_contract import MarketingExecution

FIELDS = {
    "schema_version", "project_id", "job_id", "plan_id", "trial_id", "generation",
    "execution_sha256", "workflow_state_sha256", "output_sha256", "turns", "closed",
    "completed_weeks", "model_performance_validated",
}
EFFECT_REF = r"marketing-effect:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:[0-9a-f]{64}"


def validate_graph_result(result, *, job, prepared, world, workflow_state=None):
    """Validate a fixed runner's result before retaining its private bytes.

    Without independently observed workflow_state this checks only its hash
    shape, not its truth. Effect references/turn counts still need exact SQL
    reconciliation after actual capture; this function grants no run authority.
    """
    from anvil.marketing_paid_world import QualifiedWorld

    if (type(world) is not QualifiedWorld or type(result) is not tuple
            or len(result) != 2 or any(type(item) is not dict for item in result)):
        raise ValueError("Exact original-world graph result required")
    output, receipt = result
    opening = receipt.get("schema_version") == "anvil.marketing-paid-graph-receipt.v2"
    fields = FIELDS | {"opening_completed", "opening_effect_refs", "opening_release_ref"} if opening else FIELDS
    if (len(canonical(output)) > 1048576 or len(canonical(receipt)) > 1048576
            or set(receipt) != fields
            or receipt["schema_version"] not in {"anvil.marketing-paid-graph-receipt.v1", "anvil.marketing-paid-graph-receipt.v2"}
            or receipt["model_performance_validated"] is not False):
        raise ValueError("Exact bounded unqualified graph receipt required")
    execution = MarketingExecution.model_validate(prepared["execution"])
    execution_sha = digest(prepared["execution"])
    if (execution_sha != prepared["native_binding"]["execution_sha256"]
            or receipt["execution_sha256"] != execution_sha
            or execution_sha != world._bound.execution_sha256
            or receipt["output_sha256"] != digest(output)
            or type(receipt["workflow_state_sha256"]) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", receipt["workflow_state_sha256"])):
        raise ValueError("Graph execution or returned-byte hash mismatch")
    assignment = prepared["native_binding"]["case_assignment"]
    if (assignment["case_id"] != world.case_id
            or assignment["snapshot_sha256"] != world._bound.case_snapshot_sha256
            or str(job["actor_id"]) != str(world._bound.actor_id)):
        raise ValueError("Graph case, snapshot or original actor mismatch")
    for receipt_key, job_key, world_key in (
        ("project_id", "project_id", "project_id"),
        ("job_id", "id", "job_id"),
        ("plan_id", "plan_id", "plan_id"),
    ):
        if not (receipt[receipt_key] == str(job[job_key]) == str(getattr(world._bound, world_key))):
            raise ValueError("Graph result belongs to another original attempt")
    if (receipt["trial_id"] != world.episode_id
            or type(receipt["generation"]) is not int
            or receipt["generation"] != world.generation
            or type(receipt["closed"]) is not bool
            or type(receipt["turns"]) is not int
            or type(prepared["max_calls"]) is not int
            or not 0 <= receipt["turns"] <= prepared["max_calls"]):
        raise ValueError("Graph episode, generation or bounded turn count mismatch")
    weeks = receipt["completed_weeks"]
    if (type(weeks) is not list or len(weeks) > 12
            or any(type(week) is not int for week in weeks)
            or weeks != list(range(1, len(weeks) + 1))):
        raise ValueError("Graph completed windows must be an actual ordered prefix")
    check_schema(output, execution.output_schema)
    if (output.get("outcome") not in {"campaign_closed", "awaiting_authority"}
            or receipt["closed"] != (output["outcome"] == "campaign_closed")
            or (receipt["closed"] and weeks != list(range(1, 13)))):
        raise ValueError("Graph closed/hold disposition mismatch")
    evidence, weekly = output["evidence_refs"], output["weekly_review_refs"]
    if opening:
        refs = receipt["opening_effect_refs"]
        if (type(receipt["opening_completed"]) is not bool
                or type(receipt["opening_release_ref"]) is not str
                or not re.fullmatch(r"[0-9a-f-]{36}:[0-9a-f]{64}", receipt["opening_release_ref"])
                or type(refs) is not list or len(refs) != len(set(refs))
                or any(type(ref) is not str or not re.fullmatch(EFFECT_REF, ref) for ref in refs)
                or not set(refs) <= set(evidence) or set(refs) & set(weekly)
                or receipt["closed"] and (not receipt["opening_completed"] or not refs)):
            raise ValueError("Separate recorded opening receipt/effects required")
    for refs in (evidence, weekly):
        if (type(refs) is not list or any(type(ref) is not str or not re.fullmatch(EFFECT_REF, ref) for ref in refs)
                or len(refs) != len(set(refs))):
            raise ValueError("Exact distinct recorded graph effect references required")
    closeout = output.get("closeout_report_ref")
    if (not set(weekly) <= set(evidence) or len(weekly) < len(weeks)
            or (closeout is not None and closeout not in evidence)
            or (receipt["closed"] and closeout is None)):
        raise ValueError("Graph output references differ from retained effect set")
    if workflow_state is not None:
        if (type(workflow_state) is not dict or digest(workflow_state) != receipt["workflow_state_sha256"]
                or workflow_state.get("terminal") not in {"done", "awaiting_authority"}
                or (workflow_state["terminal"] == "done") != receipt["closed"]
                or ([week for week in workflow_state.get("completed", {}).get("weekly", []) if week > 0]
                    if opening else workflow_state.get("completed", {}).get("weekly", [])) != weeks
                or opening and ((0 in workflow_state.get("completed", {}).get("weekly", [])) != receipt["opening_completed"])):
            raise ValueError("Actual graph state differs from result receipt")
