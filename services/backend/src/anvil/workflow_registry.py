"""Graph-specific testing registration; existing Task approval is insufficient."""

from anvil import artifacts, auth
from anvil.db import Jsonb, audit, digest, one, uid
from anvil.environment_structured_agent import source_task
from anvil.task_parser import json_value
from anvil.workflow_native import Definition, validate


def check_review(raw, definition):
    expected = {
        "schema": "anvil.workflow-testing-review.v1",
        "task_id": definition.binding.task_id,
        "task_version": definition.binding.task_version,
        "revision_id": definition.binding.revision_id,
        "payload_sha256": definition.binding.payload_sha256,
        "graph_sha256": definition.binding.graph_sha256,
        "disposition": "approved_for_software_testing",
    }
    if len(raw) > 65536 or json_value(raw) != expected:
        raise ValueError("exact_graph_testing_review_required")


def current(c, identifier, package=None):
    row = one(c, "SELECT * FROM anvil.workflow_definitions WHERE id=%s", (identifier,))
    if (
        not row
        or row["revoked_at"] is not None
        or (package is not None and str(row["package_id"]) != str(package))
    ):
        raise ValueError("workflow_testing_definition_unavailable")
    definition = Definition.model_validate(row["definition"])
    if digest(definition.model_dump(mode="json")) != row["subject_hash"]:
        raise ValueError("workflow_definition_hash_changed")
    if not one(
        c,
        "SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id WHERE m.project_id=%s AND m.user_id=%s AND m.active AND m.role='admin' AND u.active AND NOT u.is_synthetic",
        (row["project_id"], row["approved_by"]),
    ):
        raise ValueError("workflow_testing_authority_revoked")
    check_review(artifacts.read(c, row["review_artifact_id"]), definition)
    return row, definition


def register(c, project, actor, definition):
    if not one(
        c, "SELECT 1 FROM anvil.users WHERE id=%s AND active AND NOT is_synthetic", (actor,)
    ):
        raise ValueError("real_admin_testing_registration_required")
    auth.require(auth.project_roles(c, project, actor), "admin")
    package = one(c, "SELECT * FROM anvil.harbor_packages WHERE id=%s", (definition.package_id,))
    if not package:
        raise ValueError("workflow_package_unavailable")
    source = one(c, "SELECT * FROM anvil.praxis_sources WHERE id=%s", (package["source_id"],))
    task = source_task(artifacts.read(c, source["source_artifact_id"]), package["manifest"])
    subject = validate(task, package["manifest"], definition)
    check_review(artifacts.read(c, definition.review_artifact_id), definition)
    if (
        definition.binding.graph.bounds.calls > 100
        or definition.binding.graph.bounds.cost_micro_usd <= 0
        or definition.binding.graph.bounds.tokens <= 0
    ):
        raise ValueError("native_graph_budget_bounds_required")
    identifier = uid()
    c.execute(
        "INSERT INTO anvil.workflow_definitions(id,project_id,package_id,definition,subject_hash,approved_by,review_artifact_id) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (
            identifier,
            project,
            definition.package_id,
            Jsonb(definition.model_dump(mode="json")),
            subject,
            actor,
            definition.review_artifact_id,
        ),
    )
    audit(
        c,
        project,
        actor,
        "workflow.testing_definition_registered",
        identifier,
        {
            "subject_hash": subject,
            "graph_sha256": definition.binding.graph_sha256,
            "rights_confirmed": True,
            "paid_activation": False,
            "business_correctness_certified": False,
        },
    )
    return {
        "id": identifier,
        "subject_hash": subject,
        "graph_sha256": definition.binding.graph_sha256,
        "status": "registered_for_testing",
        "paid_activation": False,
    }


def preparation(c, identifier, package, assignments):
    row, definition = current(c, identifier, package)
    roles = {n.role for n in definition.binding.graph.nodes if n.human_mode == "actual"}
    if set(assignments) != roles:
        raise ValueError("exact_human_role_assignments_required")
    for actor in assignments.values():
        if not one(
            c,
            "SELECT 1 FROM anvil.users u JOIN anvil.memberships m ON m.user_id=u.id WHERE u.id=%s AND u.active AND NOT u.is_synthetic AND m.project_id=%s AND m.active AND m.role IN ('admin','rl-engineer')",
            (actor, row["project_id"]),
        ):
            raise ValueError("active_real_human_assignment_required")
    return {
        "id": str(row["id"]),
        "subject_hash": row["subject_hash"],
        "graph_sha256": definition.binding.graph_sha256,
        "assignments": {k: str(v) for k, v in assignments.items()},
        "bounds": definition.binding.graph.bounds.model_dump(),
    }
