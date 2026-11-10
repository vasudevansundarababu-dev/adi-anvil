"""Bounded upstream API contracts. No retries, redirects or implicit paid dispatch.

Secrets and captured evidence are supplied by the authorized worker, never documents.
An endpoint must also be provisioned in the operator's egress allowlist. This module
does not implement spending authorization or claim a contract test is live readiness.
"""

import json
import re
from urllib.parse import urlsplit
from uuid import UUID

import httpx

MAX_BYTES = 1024 * 1024


class EvaluatorError(Exception):
    """Public error codes only; never propagate provider bodies, keys or URLs."""


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate upstream JSON key")
            result[key] = value
        return result

    def invalid(_):
        raise ValueError("Non-finite upstream JSON number")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def endpoint(value: str, allowed_origins: frozenset[str], *, local=False):
    parsed = urlsplit(value)
    loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if (
        value not in allowed_origins
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path
        or not parsed.hostname
        or parsed.scheme != "https"
        and not (local and loopback and parsed.scheme == "http")
    ):
        raise EvaluatorError("endpoint_not_allowed")
    return value


def post(origin, path, payload, key, *, allowed_origins, transport=None, local=False):
    endpoint(origin, allowed_origins, local=local)
    if not key or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise EvaluatorError("invalid_credential")
    data = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode()
    if len(data) > MAX_BYTES:
        raise EvaluatorError("input_too_large")
    try:
        with httpx.Client(
            transport=transport, timeout=20, follow_redirects=False, trust_env=False
        ) as client:
            with client.stream(
                "POST",
                origin + path,
                content=data,
                headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
            ) as response:
                if response.status_code != 200:
                    raise EvaluatorError("upstream_status_" + str(response.status_code))
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_BYTES:
                        raise EvaluatorError("response_too_large")
                value = strict_json(content)
                if not isinstance(value, dict):
                    raise EvaluatorError("invalid_response_schema")
                return value
    except (httpx.HTTPError, ValueError, UnicodeError):
        raise EvaluatorError("upstream_transport_or_schema_error") from None


def arthur_prompt(origin, task_id, prompt, key, *, allowed_origins, transport=None, local=False):
    """Arthur Engine API v2. Mixed/model guardrails remain separate from deterministic rules."""
    identifier = str(UUID(task_id))
    value = post(
        origin,
        f"/api/v2/tasks/{identifier}/validate_prompt",
        {"prompt": prompt},
        key,
        allowed_origins=allowed_origins,
        transport=transport,
        local=local,
    )
    try:
        inference = str(UUID(value["inference_id"]))
        rows = value["rule_results"]
        if not isinstance(rows, list) or not 1 <= len(rows) <= 500:
            raise ValueError()
        results = []
        for row in rows:
            outcome = {"Pass": "pass", "Fail": "fail", "Skipped": "unknown"}[row["result"]]
            rule_id = str(UUID(row["id"]))
            rule_type = row["rule_type"]
            if not isinstance(rule_type, str) or len(rule_type) > 100:
                raise ValueError()
            # No brand-wide claim: only the documented literal keyword rule is deterministic.
            results.append(
                {
                    "rule_id": rule_id,
                    "outcome": outcome,
                    "deterministic": rule_type == "KeywordRule",
                    "rule_type": rule_type,
                }
            )
        if len({r["rule_id"] for r in results}) != len(results):
            raise ValueError()
        return {"inference_id": inference, "results": results}
    except (KeyError, TypeError, ValueError):
        raise EvaluatorError("invalid_arthur_result") from None


def openlayer_evaluate(test_id, pipeline_id, start, end, key, *, transport=None):
    """Queue one exact existing pipeline/window. Queued != evaluated or Pass.

    Uses the vendor's published REST SDK contract. No overwrite and no all-pipeline
    default, no invented model findings; a later result must bind this task/window.
    """
    if (
        not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", test_id)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", pipeline_id)
        or type(start) is not int
        or type(end) is not int
        or not 0 <= start < end
    ):
        raise EvaluatorError("invalid_evaluation_scope")
    value = post(
        "https://api.openlayer.com",
        f"/v1/tests/{test_id}/evaluate",
        {
            "inference_pipeline_id": pipeline_id,
            "start_timestamp": start,
            "end_timestamp": end,
            "overwrite_results": False,
        },
        key,
        allowed_origins=frozenset({"https://api.openlayer.com"}),
        transport=transport,
    )
    try:
        if (
            type(value["pipelineCount"]) is not int
            or value["pipelineCount"] != 1
            or value["requestedStartTimestamp"] != start
            or value["requestedEndTimestamp"] != end
            or len(value["tasks"]) != 1
        ):
            raise ValueError()
        task = value["tasks"][0]
        if task["pipelineId"] != pipeline_id or not isinstance(task["taskResultId"], str):
            raise ValueError()
        # Never follow a returned URL: vendor result locations are not egress authority.
        return {
            "state": "queued",
            "task_result_id": task["taskResultId"],
            "outcome": "not_evaluated",
            "pipeline_id": pipeline_id,
            "start_timestamp": start,
            "end_timestamp": end,
        }
    except (KeyError, TypeError, ValueError):
        raise EvaluatorError("invalid_openlayer_result") from None


def opa_decision(
    origin, decision_path, facts, key, *, allowed_origins, transport=None, local=False
):
    """Exact OPA Data API, bool decision only; undefined is Unknown, never Fail."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:/[A-Za-z_][A-Za-z0-9_]*)*", decision_path):
        raise EvaluatorError("invalid_decision_path")
    value = post(
        origin,
        "/v1/data/" + decision_path,
        {"input": facts},
        key,
        allowed_origins=allowed_origins,
        transport=transport,
        local=local,
    )
    if "result" not in value:
        return {"outcome": "unknown", "reason": "OPA decision is undefined"}
    if type(value["result"]) is not bool:
        raise EvaluatorError("invalid_opa_decision")
    return {"outcome": "pass" if value["result"] else "fail", "reason": "OPA boolean decision"}
