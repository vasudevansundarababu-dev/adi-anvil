"""Explicit successor SDK verifier; no legacy collection reward conversion.

The successor runtime must bind private_verifier in its immutable context and
admit a host collect_private handler that independently observes the fixed
tests-container exit, output bytes, graph/API quiescence and actor-environment
stop acknowledgment. The original SDK necessarily lives during this reply;
whole SDK/graph/helper-root stop follows SDK exit and remains a separate final
acceptance gate. This adapter does not start/exec, seal or grant admission.
"""

import asyncio
import hashlib
import json
import re
from fractions import Fraction

from harbor.models.verifier.result import VerifierResult
from harbor.verifier.base import BaseVerifier

from anvil_harbor.marketing import _remaining, component_gate
from anvil_harbor.marketing_private_verifier import (
    CRITICAL, CRITERION_WEIGHTS, GROUPS, IDENTITY, INPUT_FILES, PROFILE, SCORING_CONTRACT,
    SCORING_SOURCE_PINS, _exact, _identity, _parse, _pin, _scope,
)

RESULT_FIELDS = frozenset({
    "schema_version", "profile", "scoring_contract", "scoring_source_pins", "identity", "scope", "source_sha256", "input_sha256", "input_files",
    "rubric_id", "rubric_version", "scale", "levels", "groups", "total", "result", "output_gate",
    "unscored_criteria", "unknown_critical_rules", "critical_failures", "human_legal_acceptance",
    "model_performance_validated", "native_qualification_granted", "paid_calls",
})


def validate_result(raw, binding):
    """Check producer semantics against the independently pinned private profile."""
    _exact(binding, {"schema_version", "scoring_contract", "scoring_source_pins", "identity", "scope", "source_sha256", "input_sha256", "input_files",
                     "rubric_id", "rubric_version", "criterion_weights"})
    if (binding["schema_version"] != "anvil.marketing-private-sdk-binding.v1"
            or binding["scoring_contract"] != SCORING_CONTRACT
            or binding["scoring_source_pins"] != SCORING_SOURCE_PINS):
        raise ValueError("marketing_private_exact_sdk_binding_required")
    _identity(binding["identity"])
    _scope(binding["scope"])
    if binding["identity"]["job_id"] != binding["scope"]["job_id"]:
        raise ValueError("marketing_private_sdk_job_scope_changed")
    for key in ("source_sha256", "input_sha256"):
        _pin(binding[key])
    _exact(binding["input_files"], INPUT_FILES)
    for pin in binding["input_files"].values():
        _pin(pin)
    value = _parse(raw)
    _exact(value, RESULT_FIELDS)
    _identity(value["identity"])
    _scope(value["scope"])
    if (value["schema_version"] != "anvil.marketing-private-result.v1" or value["profile"] != PROFILE
            or value["scoring_contract"] != SCORING_CONTRACT
            or value["scoring_source_pins"] != SCORING_SOURCE_PINS
            or any(value[k] != binding[k] for k in ("identity", "scope", "source_sha256", "input_sha256",
                                                   "input_files", "rubric_id", "rubric_version"))
            or value["scale"] != "zero_to_four" or value["human_legal_acceptance"] != "not_established"
            or any(value[k] is not False for k in ("model_performance_validated", "native_qualification_granted", "paid_calls"))):
        raise ValueError("marketing_private_exact_result_binding_required")
    weights, levels = binding["criterion_weights"], value["levels"]
    if type(weights) is not dict or weights != CRITERION_WEIGHTS:
        raise ValueError("marketing_private_pinned_criterion_weights_required")
    _exact(levels, weights)
    denominator, totals = dict.fromkeys(GROUPS, 0), dict.fromkeys(GROUPS, Fraction(0))
    for key, weight in weights.items():
        if (key not in CRITERION_WEIGHTS
                or type(weight) is not int or not 1 <= weight <= GROUPS[key[0]]):
            raise ValueError("marketing_private_original_criterion_weights_required")
        group, level = key[0], levels[key]
        denominator[group] += weight
        if level is not None:
            if type(level) is not int or not 0 <= level <= 4:
                raise ValueError("marketing_private_original_ordinal_scale_required")
            totals[group] += Fraction(weight * level, 4)
    if denominator != GROUPS:
        raise ValueError("marketing_private_original_rubric_denominator_required")
    exact = lambda n: {"numerator": n.numerator, "denominator": n.denominator}
    _exact(value["groups"], GROUPS)
    for rational in [value["total"], *value["groups"].values()]:
        _exact(rational, {"numerator", "denominator"})
        if (type(rational["numerator"]) is not int or type(rational["denominator"]) is not int
                or rational["numerator"] < 0 or rational["denominator"] <= 0):
            raise ValueError("marketing_private_exact_rational_score_required")
    if (value["groups"] != {k: exact(v) for k, v in totals.items()}
            or value["total"] != exact(sum(totals.values(), Fraction(0)))
            or value["unscored_criteria"] != sorted(k for k, v in levels.items() if v is None)):
        raise ValueError("marketing_private_result_arithmetic_changed")
    for key in ("critical_failures", "unknown_critical_rules"):
        rows = value[key]
        if (type(rows) is not list or any(type(row) is not str or row not in CRITICAL for row in rows)
                or rows != sorted(set(rows))):
            raise ValueError("marketing_private_exact_critical_rules_required")
    if set(value["critical_failures"]) & set(value["unknown_critical_rules"]):
        raise ValueError("marketing_private_conflicting_critical_evidence")
    gate = value["output_gate"]
    if gate is not None and type(gate) is not bool:
        raise ValueError("marketing_private_explicit_output_gate_required")
    total = sum(totals.values(), Fraction(0))
    status = ("failed" if value["critical_failures"] or gate is False else "unscored"
              if value["unscored_criteria"] or value["unknown_critical_rules"] or gate is None else "passed"
              if total >= 80 and totals["B"] >= 12 else "failed")
    if value["result"] != status:
        raise ValueError("marketing_private_result_status_changed")
    return value


async def _collect(environment):
    context = environment._context
    binding = context.get("private_verifier")
    # Legacy contexts have no private_verifier and cannot select this adapter.
    if type(binding) is not dict or environment.role != "tests":
        raise ValueError("marketing_private_explicit_successor_context_required")
    identity = binding["identity"]
    _identity(identity)
    if (any(identity[k] != context[k] for k in IDENTITY - {"framework_trial_id"})
            or identity["framework_trial_id"] != str(environment.context_id)
            or environment.session_id != context["trial_name"] + "__verifier__trial"):
        raise ValueError("marketing_private_actual_framework_identity_required")
    payload = {"schema_version": "anvil.marketing-private-component-event.v1", "event": "collect_private",
               **identity, "scope": binding["scope"], "role": "tests", "session_id": environment.session_id,
               "input_sha256": binding["input_sha256"], "source_sha256": binding["source_sha256"],
               "profile_sha256": binding["input_files"]["evaluation-profile.json"]}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(raw) > 8192:
        raise ValueError("marketing_private_event_capacity")
    reader, writer = await asyncio.open_unix_connection(context["control_socket"], limit=8192)
    try:
        header = ("POST /marketing/component/collect_private HTTP/1.1\r\nHost: localhost\r\n"
                  "Authorization: Bearer " + context["control_token"] + "\r\n"
                  "Content-Type: application/json\r\nConnection: close\r\nContent-Length: " + str(len(raw)) + "\r\n\r\n").encode("ascii")
        writer.write(header + raw)
        await writer.drain()
        header = await reader.readuntil(b"\r\n\r\n")
        if len(header) > 8192:
            raise ValueError("marketing_private_reply_header_capacity")
        lines = header.split(b"\r\n")
        if lines[0] != b"HTTP/1.1 200 OK":
            raise RuntimeError("marketing_private_collection_denied_no_retry")
        headers = {}
        for line in lines[1:-2]:
            key, val = line.split(b":", 1)
            key = key.lower()
            if key in headers:
                raise ValueError("marketing_private_duplicate_HTTP_header")
            headers[key] = val.strip()
        length = headers.get(b"content-length", b"")
        if b"transfer-encoding" in headers or not re.fullmatch(rb"[0-9]{1,7}", length):
            raise ValueError("marketing_private_fixed_HTTP_framing_required")
        size = int(length)
        if not 0 < size <= 1048576:
            raise ValueError("marketing_private_reply_capacity")
        reply = _parse(await reader.readexactly(size))
    finally:
        writer.close()  # No unbounded close or replay after ambiguous dispatch.
    _exact(reply, {"schema_version", "event", "identity", "scope", "session_id", "status", "result",
                   "result_sha256", "result_bytes", "container_id", "container_exit_code", "process_receipt_sha256"})
    if (reply["schema_version"] != "anvil.marketing-private-component-reply.v1"
            or reply["event"] != "collect_private" or reply["identity"] != identity
            or reply["scope"] != binding["scope"] or reply["session_id"] != environment.session_id
            or reply["status"] != "private_process_completed"
            or type(reply["container_exit_code"]) is not int or reply["container_exit_code"] != 0
            or type(reply["container_id"]) is not str or not re.fullmatch(r"[a-f0-9]{64}", reply["container_id"])):
        raise ValueError("marketing_private_actual_completed_container_required")
    _pin(reply["process_receipt_sha256"])
    # Exact original bytes, not reserialized JSON, preserve the producer hash.
    if type(reply["result"]) is not str:
        raise ValueError("marketing_private_original_result_bytes_required")
    result_raw = reply["result"].encode("utf-8")
    if (type(reply["result_bytes"]) is not int or len(result_raw) != reply["result_bytes"]
            or hashlib.sha256(result_raw).hexdigest() != _pin(reply["result_sha256"])):
        raise ValueError("marketing_private_result_bytes_changed")
    return validate_result(result_raw, binding), result_raw


class MarketingPrivateVerifier(BaseVerifier):
    def __init__(self, *args, **kwargs):
        component_gate()
        super().__init__(*args, **kwargs)

    async def verify(self):
        component_gate()
        context = self.environment._context
        value, raw = await asyncio.wait_for(_collect(self.environment), timeout=_remaining(context))
        _remaining(context)
        self.private_result = value
        self.private_result_raw = raw
        self.private_result_sha256 = hashlib.sha256(raw).hexdigest()
        # Partial denominators are never presented as a completed rubric score.
        # A failed critical/output gate may coexist with missing rubric evidence.
        if value["unscored_criteria"] or value["unknown_critical_rules"] or value["output_gate"] is None:
            return VerifierResult(rewards=None)
        total = value["total"]
        return VerifierResult(rewards={"rubric_score": total["numerator"] / total["denominator"],
                                       "task_pass": float(value["result"] == "passed")})
