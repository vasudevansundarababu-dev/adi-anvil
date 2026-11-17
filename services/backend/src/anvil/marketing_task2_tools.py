"""Published Task2 tool operations over the real persisted campaign controller.

Only released public records cross this boundary. Missing Anvil collections are
unavailable, never fabricated vendor responses. Task3 returns are fixture
descriptors, not generated media or real human approval.
"""

from copy import deepcopy

from anvil.import_sandbox import schema_check
from anvil.marketing_task2_contract import WIRE_ROLES
from anvil.marketing_task2_runtime import timestamp
from anvil.praxis_generic_contract import canonical, digest
from anvil.praxis_marketing_contract import MarketingExecution

READS = {
    "campaigns.read": "campaigns",
    "products.read": "products",
    "offers.read": "offers",
    "capabilities.read": "capabilities",
    "policies.read": "policies",
    "source_documents.read": "documents",
    "budget_summaries.read": "budget-snapshots",
    "operations.status.read": "operations",
    "questions.read": "questions",
    "observations.read": "observation-windows",
    "reports.query": "reports",
    "ledger.read": "ledger",
    "budget.read": "budget-envelopes",
    "delivery_manifests.read": "task3-deliveries",
    "asset_refs.read": "content",
    "evidence.read": "claim-evidence",
}
WRITES = {
    "plans.write": "plans",
    "handoffs.assign": "handoffs",
    "disagreements.record": "disagreements",
    "readiness.request": "readiness-requests",
    "approval_requests.submit": "approval-requests",
    "intent.write": "intent-assessments",
    "investigations.write": "investigations",
    "experiments.propose": "experiments",
    "budget_proposals.write": "budget-proposals",
    "forecasts.request": "forecast-requests",
    "briefs.write": "creative-briefs",
    "production_requests.submit": "production-requests",
    "campaign_findings.write": "campaign-findings",
    "review_assessments.write": "readiness-assessments",
}


def execute(controller, role, operation, arguments, execution):
    contract = MarketingExecution.model_validate(execution)
    if role not in WIRE_ROLES:
        raise ValueError("Host-bound canonical Marketing role required")
    tool = next((t for t in contract.tools if t.id == operation), None)
    runtime_role = WIRE_ROLES[role]

    def result(status, body, refs=None):
        value = {"status": status, "result": body, "evidence_refs": refs or []}
        controller._event("tool:" + str(operation), runtime_role, status)
        if tool:
            schema_check(value, tool.output_schema)
        if len(canonical(value)) > 49152:
            raise ValueError("Marketing tool observation exceeds the sealed MCP response bound")
        return value

    if tool is None or role not in tool.role_ids:
        return result("denied", {"code": "role_tool_scope"})
    schema_check(arguments, tool.input_schema)
    if len(canonical(arguments)) > 20000:
        return result("denied", {"code": "bounded_tool_arguments_required"})
    if operation == "context.read":
        context = controller.call(
            controller.credential(runtime_role), controller.generation, "context", {}
        )
        return result(
            "completed",
            context
            | {
                "wire_role": role,
                "workflow_graph_sha256": contract.workflow_graph_sha256,
                "integration": "implemented_simulator_subset",
            },
        )
    if operation == "handoffs.assigned.read":
        handoffs = [
            deepcopy(value)
            for value in controller._objects.values()
            if value["kind"] == "handoffs" and value["content"].get("recipient_role") == role
        ]
        if arguments.get("resource_ref"):
            reference = arguments["resource_ref"]
            handoffs = [h for h in handoffs if h["id"] == reference
                        or any(r.get("id") == reference for r in h["content"].get("artifact_refs", []))]
        assigned = {}
        for handoff in handoffs:
            for ref in handoff["content"].get("artifact_refs", []):
                if (arguments.get("resource_ref") and arguments["resource_ref"] not in {handoff["id"], ref.get("id")}):
                    continue
                record = controller._objects.get(ref.get("id"))
                if (type(record) is not dict or type(ref.get("version")) is not int
                        or record["version"] != ref["version"] or digest(record) != ref.get("sha256")):
                    return result("unavailable", {"code": "assigned_handoff_version_changed", "records": handoffs})
                assigned[(record["id"], record["version"])] = {
                    "record": deepcopy(record), "record_sha256": digest(record),
                    "handoff_ref": {"id": handoff["id"], "version": handoff["version"], "sha256": digest(handoff)},
                }
        if len(assigned) > 100:
            return result("unavailable", {"code": "explicit_narrower_handoff_query_required"})
        body = {"records": handoffs, "assigned_artifacts": list(assigned.values())}
        if len(canonical({"status": "completed", "result": body, "evidence_refs": []})) > 49152:
            return result("unavailable", {"code": "explicit_narrower_handoff_query_required",
                                          "maximum_response_bytes": 49152, "records_silently_truncated": False})
        return result("completed", body)
    if operation == "operations.status.read":
        # Actual persisted requests take precedence over static fixture records.
        requests = [
            record
            for record in controller._objects.values()
            if record["kind"] in {"forecast-requests", "approval-requests"}
            and record["created_by_role"] == runtime_role
            and (not arguments.get("resource_ref") or arguments["resource_ref"] == record["id"])
        ]
        if requests:
            records = []
            for request in requests:
                if request["kind"] == "approval-requests":
                    key = (request["id"], request["version"])
                    decided = key in controller._approvals
                    records.append(
                        {
                            "request_id": request["id"],
                            "request_version": request["version"],
                            "request_sha256": digest(request),
                            "status": "completed" if decided else "pending",
                            "decision": ("approved" if controller._approvals[key] else "rejected")
                            if decided
                            else "pending",
                            "amount_bound_minor": controller._approval_bounds.get(key),
                            "simulation_only": True,
                        }
                    )
                    continue
                key = "anvil-forecast-result:" + digest(
                    {"id": request["id"], "version": request["version"]}
                )
                completed = controller._objects.get(key)
                valid = bool(
                    completed and completed["content"]["request_sha256"] == digest(request)
                )
                records.append(
                    {
                        "request_id": request["id"],
                        "request_version": request["version"],
                        "request_sha256": digest(request),
                        "status": "completed" if valid else "pending",
                        "completion": deepcopy(completed["content"]) if valid else None,
                        "simulation_only": True,
                    }
                )
            return result(
                "completed" if all(r["status"] == "completed" for r in records) else "pending",
                {"records": records},
                [r["request_id"] for r in records],
            )
    if operation in READS:
        collection = READS[operation]
        if collection not in controller._initial:
            return result(
                "unavailable",
                {
                    "code": "anvil_dataset_collection_unavailable",
                    "collection": collection,
                    "owner": "anvil",
                },
            )
        records = []
        unreleased = False
        for entry in controller._initial[collection]:
            if entry.get("actor_visible") is not True or entry.get("outcome_binding") not in (
                None,
                controller._outcome,
            ):
                continue
            if timestamp(entry["released_at"]) > timestamp(controller._clock):
                unreleased = True
                continue
            public = deepcopy(entry["public"])
            identifier = public.get("id") or "anvil-source-record:" + digest(public)
            if arguments.get("resource_ref") and arguments["resource_ref"] != identifier:
                continue
            if arguments.get("window") is not None and public.get("week") != arguments["window"]:
                continue
            if any(public.get(key) != value for key, value in arguments.get("filters", {}).items()):
                continue
            records.append({"source_record_ref": identifier, "source_record_sha256": digest(public), "content": public})
        if len(records) > 250:
            return result(
                "unavailable",
                {
                    "code": "explicit_narrower_query_required",
                    "maximum_records": 250,
                    "records_silently_truncated": False,
                },
            )
        body = {"records": records, "collection": collection}
        refs = [x["source_record_ref"] for x in records]
        status = "pending" if not records and unreleased else "completed"
        if len(canonical({"status": status, "result": body, "evidence_refs": refs})) > 49152:
            return result("unavailable", {"code": "explicit_narrower_query_required",
                                          "maximum_response_bytes": 49152, "records_silently_truncated": False})
        return result(
            status, body, refs,
        )
    if operation in WRITES:
        if operation == "handoffs.assign":
            content = arguments["content"]
            if (
                content.get("recipient_role") not in WIRE_ROLES
                or not isinstance(content.get("artifact_refs"), list)
                or not content["artifact_refs"]
            ):
                return result(
                    "denied", {"code": "explicit_recipient_and_versioned_artifacts_required"}
                )
            for reference in content["artifact_refs"]:
                if not isinstance(reference, dict) or set(reference) != {"id", "version", "sha256"}:
                    return result("denied", {"code": "exact_handoff_reference_required"})
                artifact = controller._objects.get(reference["id"])
                if (
                    artifact is None
                    or artifact["version"] != reference["version"]
                    or digest(artifact) != reference["sha256"]
                ):
                    return result("denied", {"code": "handoff_artifact_version_mismatch"})
        record = controller.call(
            controller.credential(runtime_role), controller.generation, WRITES[operation], arguments
        )
        if record.get("status") == "denied":
            return result("denied", {"code": record["code"]})
        if operation == "forecasts.request":
            return result(
                "pending",
                {
                    "record": record,
                    "record_sha256": digest(record),
                    "operation_id": record["id"],
                    "request_version": record["version"],
                    "service": "controlled_forecast_fixture",
                    "completion_not_observed": True,
                },
                [record["id"] + "@" + str(record["version"])],
            )
        return result(
            "completed",
            {"record": record, "record_sha256": digest(record)},
            [record["id"] + "@" + str(record["version"])],
        )
    return result("unavailable", {"code": "anvil_tool_adapter_unavailable", "owner": "anvil"})
