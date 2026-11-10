"""Native SDK-tool mediation for component environments, with no live entry point.

The installed provider loop is deliberately MockTransport-only. It exercises the
same typed tools against actual component state without resolving any model key.
Live dispatch continues to require the existing separate broker admission gates.
"""

import json

from anvil import benchmark_project_import as projects
from anvil import environment_runtime as runtime
from anvil.benchmark_conversation import Tool, run_contract
from anvil.benchmark_rehearsal import enabled
from anvil.environment_api import Operation

FIELDS = {
    "list_records": (("collection",), ()),
    "read_file": (("path",), ()),
    "query_statements": (("company_id", "period_id"), ("line_item",)),
    "calculate_financial": (("line_ids", "operator"), ()),
    "save_analysis": (("text", "source_ids"), ()),
    "create_campaign": (("objective", "copy", "audience_ids"), ()),
    "allocate_budget": (("campaign_id", "amount", "currency"), ()),
    "request_approval": (("target_id",), ()),
    "schedule_placement": (("target_id",), ("channel",)),
    "submit_variant": (("target_id",), ("channel",)),
    "render_variant": (("channel", "locale", "caption", "disclosure"), ()),
    "inspect_asset": (("path",), ()),
    "screen_case": (("case_id",), ()),
    "request_information": (("case_id", "reason"), ()),
    "record_decision": (("case_id", "decision", "rationale", "evidence_ids"), ()),
    "ownership_paths": (("entity_id",), ()),
    "query_transactions": (("account_id", "start", "end"), ()),
    "record_step": (("case_id", "note", "transaction_ids"), ()),
    "link_case": (("case_id", "related_case_id"), ()),
    "record_disposition": (("case_id", "disposition", "rationale"), ()),
}
ARRAYS = {"line_ids", "source_ids", "audience_ids", "evidence_ids", "transaction_ids"}


def tools(version):
    declared = []
    for name in version["manifest"]["tools"]:
        if name not in FIELDS:
            raise ValueError("Tool schema is not implemented; no guessed schema")
        required, optional = FIELDS[name]
        properties = {
            field: (
                {"type": "array", "items": {"type": "string", "maxLength": 5000}, "maxItems": 100}
                if field in ARRAYS
                else {"type": "string", "maxLength": 5000}
            )
            for field in (*required, *optional)
        }
        declared.append(
            Tool(
                name=name,
                description="Operate on this exact isolated component instance: " + name,
                parameters={
                    "type": "object",
                    "properties": properties,
                    "required": list(required),
                    "additionalProperties": False,
                },
            )
        )
    return declared


class Mediator:
    def __init__(self, c, user, instance):
        self.c, self.user, self.instance = c, user, instance
        self.row = runtime.get(c, "environment_instances", instance)
        version = runtime.get(c, "environment_versions", self.row["environment_id"])
        runtime.current_runtime(version)
        self.declared = {t.name for t in tools(version)}

    def call(self, name, arguments, *, timeout):
        if name not in self.declared or not 0 < timeout <= 60:
            raise ValueError("Undeclared or unbounded component call")
        parsed = Operation(
            operation=name, arguments=arguments, expected_generation=self.row["generation"]
        )
        return runtime.execute(
            self.c,
            self.user,
            self.instance,
            parsed.operation,
            parsed.arguments,
            parsed.expected_generation,
        )


def sdk_contract(c, user, group_id, task_id, instance, binding, transport):
    import httpx

    if type(transport) is not httpx.MockTransport:
        raise ValueError("Only explicit offline MockTransport is supported; no paid calls")
    enabled()
    group = projects.get(c, group_id)
    task = next((t for t in group["content"]["tasks"] if t["task_id"] == task_id), None)
    if not task:
        raise ValueError("Task is not in the frozen Project")
    row = runtime.get(c, "environment_instances", instance)
    version = runtime.get(c, "environment_versions", row["environment_id"])
    # Public actor projection only: no task_source, rubric, fixtures or reference_output.
    prompt = json.dumps(
        {
            "actor": task["actor"],
            "environment": {
                "template": version["manifest"]["template_id"],
                "scenario": version["manifest"]["scenario_id"],
                "clock": version["manifest"]["clock"],
            },
            "origin": "offline_sdk_contract_not_model_performance",
        },
        allow_nan=False,
    )
    result = run_contract(binding, prompt, tools(version), Mediator(c, user, instance), transport)
    return {
        "status": result.status,
        "terminal_code": result.error_code,
        "final_text": result.text,
        "turns": [
            {
                "model_returned": t.model_returned,
                "calls": [call.model_dump() for call in t.calls],
                "observations": [o.model_dump() for o in t.observations],
            }
            for t in result.turns
        ],
        "task_payload_sha256": task["payload_sha256"],
        "environment_manifest_sha256": version["manifest_sha256"],
        "origin": "offline_sdk_contract",
        "provider_calls": 0,
        "model_performance": False,
    }
