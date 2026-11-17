"""Private named-tool evidence; no actor-supplied success flags.

Store custody uses RFC8785; normalized logical views use sorted-JSON hashes.
Reads establish observed replies and declared state facts, not understanding or
proof that every state field was unchanged. Private source arrays stay private.
"""

from copy import deepcopy

from anvil.db import digest
from anvil.marketing_task2_contract import WIRE_ROLES
from anvil.marketing_task2_tools import READS, WRITES
from anvil.praxis_generic_contract import digest as custody_digest

SUPPORTED = set(READS) | set(WRITES) | {"context.read", "handoffs.assigned.read"}
SCOPE = "verified_named_tool_arguments_responses_and_declared_post_state_facts_not_semantics"
STATE_FIELDS = ("clock", "budget_minor", "committed", "settled")


def load(c, project, episode, generation):
    if not c.execute(
        "SELECT to_regclass('campaign_private.tool_effect_states') AS relation"
    ).fetchone()["relation"]:
        return {}
    rows = c.execute(
        "SELECT i.project_id,i.request_id,i.operation AS intent_operation,i.arguments,i.arguments_sha256,"
        "t.role AS intent_role,t.job_id AS intent_job,t.lease_sha256 AS intent_lease,"
        "l.job_id AS linked_job,l.lease_sha256 AS linked_lease,l.episode_id,l.generation,"
        "v.episode_id AS capture_episode,v.generation AS capture_generation,"
        "v.post_state,v.post_state_sha256,v.full_state_sha256 "
        "FROM marketing_runtime.paid_tool_action_intents i "
        "JOIN marketing_runtime.paid_turn_intents t ON t.project_id=i.project_id AND t.plan_id=i.plan_id AND t.stage_index=i.stage_index "
        "JOIN marketing_runtime.paid_episode_links l ON l.project_id=t.project_id AND l.plan_id=t.plan_id "
        "LEFT JOIN campaign_private.tool_effect_states v ON v.project_id=i.project_id AND v.request_id=i.request_id AND v.episode_id=l.episode_id AND v.generation=l.generation "
        "WHERE l.project_id=%s AND l.episode_id=%s AND l.generation=%s",
        (project, episode, generation),
    ).fetchall()
    result = {}
    for row in rows:
        key = str(row["request_id"])
        if key in result:
            raise ValueError("Ambiguous private campaign tool custody")
        result[key] = row
    return result


def observations(receipts, views, role, reference):
    """Every selected role call is accounted for; unavailable evidence is a gap."""
    if not isinstance(reference, dict):
        return [], False
    obligations = reference.get("obligations", [])
    if not isinstance(obligations, list):
        return [], False
    for item in obligations:
        if not isinstance(item, dict) or item.get("operation") not in SUPPORTED:
            return [], False
        if item["operation"] not in WRITES:
            persisted_match = item.get("persisted_match")
            if not isinstance(persisted_match, dict):
                return [], False
            pattern = persisted_match.get("response", {})
            if (
                not isinstance(pattern, dict)
                or pattern.get("status") not in {"completed", "pending", "denied"}
                or not isinstance(pattern.get("result"), dict)
                or not pattern["result"]
            ):
                return [], False
    invocations = []
    try:
        # An intent whose transport/capture never completed cannot disappear
        # from the population merely because no receipt was written for it.
        selected_receipts = {
            str(receipt["id"])
            for receipt in receipts
            if receipt["role"] in WIRE_ROLES and WIRE_ROLES[receipt["role"]] == role
        }
        selected_intents = set()
        for key, view in views.items():
            if not isinstance(view, dict) or view.get("intent_role") not in WIRE_ROLES:
                return [], False
            if WIRE_ROLES[view["intent_role"]] == role:
                selected_intents.add(str(key))
        if selected_intents != selected_receipts:
            return [], False
        for receipt in receipts:
            if receipt["role"] not in WIRE_ROLES:
                return [], False
            if WIRE_ROLES[receipt["role"]] != role:
                continue
            operation = receipt["operation"]
            if operation not in SUPPORTED:
                return [], False
            view = views.get(str(receipt["id"]))
            if (
                not view
                or view["intent_role"] != receipt["role"]
                or view["intent_operation"] != operation
                or str(view["project_id"]) != str(receipt["project_id"])
                or str(view["episode_id"]) != str(receipt["episode_id"])
                or str(view["capture_episode"]) != str(receipt["episode_id"])
                or view["generation"] != receipt["generation"]
                or view["capture_generation"] != receipt["generation"]
                or not view["intent_job"]
                or not view["intent_lease"]
                or str(view["intent_job"]) != str(view["linked_job"])
                or view["intent_lease"] != view["linked_lease"]
            ):
                return [], False
            arguments, state, response = view["arguments"], view["post_state"], receipt["result"]
            if (
                not isinstance(arguments, dict)
                or not isinstance(state, dict)
                or not isinstance(response, dict)
                or state.get("schema_version") != "anvil.marketing-tool-post-state.v1"
                or custody_digest(arguments) != view["arguments_sha256"]
                or view["arguments_sha256"] != receipt["arguments_sha256"]
                or custody_digest(response) != receipt["result_sha256"]
                or custody_digest(state) != view["post_state_sha256"]
                or view["full_state_sha256"] != receipt["state_sha256"]
                or response.get("status") not in {"completed", "pending", "denied"}
            ):
                return [], False
            persisted = {
                "response": deepcopy(response),
                "post_state": {key: deepcopy(state[key]) for key in STATE_FIELDS if key in state},
            }
            if operation in WRITES and response["status"] in {"completed", "pending"}:
                record = response.get("result", {}).get("record")
                stored = state.get("objects", {}).get(arguments.get("id"))
                if (
                    not isinstance(record, dict)
                    or record.get("id") != arguments.get("id")
                    or record.get("kind") != WRITES[operation]
                    or record.get("created_by_role") != WIRE_ROLES[receipt["role"]]
                    or type(arguments.get("expected_version")) is not int
                    or record.get("version") != arguments["expected_version"] + 1
                    or custody_digest(record.get("content"))
                    != custody_digest(arguments.get("content"))
                    or custody_digest(stored) != custody_digest(record)
                ):
                    return [], False
                persisted["record"] = deepcopy(record)
            elif operation in WRITES:
                persisted["no_completed_effect"] = True
            subject = (
                arguments.get("id")
                or arguments.get("resource_ref")
                or "episode:" + str(receipt["episode_id"])
            )
            if not isinstance(subject, str) or not subject:
                return [], False
            invocations.append(
                {
                    "invocation_id": str(receipt["id"]),
                    "operation": operation,
                    "subject_id": subject,
                    "role": role,
                    "arguments": deepcopy(arguments),
                    "arguments_sha256": digest(arguments),
                    "response": deepcopy(response),
                    "response_sha256": digest(response),
                    "persisted_state": persisted,
                    "persisted_state_sha256": digest(persisted),
                    "effect_verified": True,
                }
            )
    except (KeyError, TypeError, ValueError, AttributeError):
        return [], False
    return invocations, True
