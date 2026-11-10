"""Project-scoped, append-only evaluator configuration; no live dispatch here."""

from importlib.metadata import version
from typing import Literal

from fastapi import HTTPException
from pydantic import Field, SecretStr, model_validator

from anvil import workspace_secrets
from anvil.config import ROOT
from anvil.db import Jsonb, audit, digest, one, uid
from anvil.policy_rules import Rule, evaluate, evaluate_opa, evaluate_zen
from anvil.praxis_contract import Model

ADAPTER_VERSION = "anvil-evaluator-v1"
LOCAL_ADAPTERS = {"builtin", "zen", "opa-local", "nemo", "promptfoo"}


def adapter_source_sha256(adapter):
    import hashlib

    paths = [
        "services/backend/src/anvil/policy_rules.py",
        "services/backend/src/anvil/evaluator_configurations.py",
        "services/backend/uv.lock",
    ]
    if adapter in {"nemo", "promptfoo", "opa-local"}:
        paths += ["services/backend/src/anvil/evaluator_runtimes.py"]
    if adapter in {"nemo", "promptfoo"}:
        paths += (
            ["integrations/evaluators/local_worker.py", "integrations/evaluators/nemo/uv.lock"]
            if adapter == "nemo"
            else [
                "integrations/evaluators/promptfoo/worker.mjs",
                "integrations/evaluators/promptfoo/package-lock.json",
            ]
        )
    return digest({path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths})


class Configure(Model):
    name: str = Field(min_length=1, max_length=160)
    adapter: Literal[
        "builtin", "zen", "opa-local", "nemo", "promptfoo", "opa", "arthur", "openlayer"
    ]
    rule: Rule | None = None
    endpoint: str | None = Field(default=None, max_length=300)
    resource_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_/-]{1,100}$")
    secret: SecretStr | None = Field(default=None, min_length=1, max_length=4096)

    @model_validator(mode="after")
    def shape(self):
        if self.adapter in LOCAL_ADAPTERS:
            if self.rule is None or self.endpoint or self.resource_id or self.secret:
                raise ValueError("Local deterministic adapter needs only a structured rule")
            if self.adapter == "nemo" and self.rule.kind != "forbidden_text":
                raise ValueError("NeMo requires a forbidden literal rule")
            if self.adapter == "promptfoo" and (
                self.rule.kind not in {"forbidden_text", "equals"}
                or not isinstance(self.rule.value, str)
            ):
                raise ValueError("Promptfoo requires a literal text rule")
            if self.adapter in {"zen", "opa-local"} and self.rule.kind == "forbidden_text":
                raise ValueError("This adapter does not support forbidden text")
        elif self.rule is not None or not self.endpoint or not self.resource_id or not self.secret:
            raise ValueError("API adapter requires endpoint, resource and key; no local rule")
        if self.secret and any(ord(c) < 33 or ord(c) > 126 for c in self.secret.get_secret_value()):
            raise ValueError("API credential must contain printable non-whitespace ASCII")
        return self


class Case(Model):
    facts: dict
    expected: Literal["pass", "fail", "unknown"]


class TestCases(Model):
    cases: list[Case] = Field(min_length=3, max_length=30)

    @model_validator(mode="after")
    def coverage(self):
        if {c.expected for c in self.cases} != {"pass", "fail", "unknown"}:
            raise ValueError("Known Pass, Fail and Unknown cases are required")
        if len(str(self.model_dump())) > 100000:
            raise ValueError("Known-case data exceeds configuration bound")
        return self


def create(c, project, user, body):
    identifier = uid()
    configuration = body.model_dump(exclude={"secret", "name", "adapter"}, exclude_none=True)
    reference = None
    if body.secret:
        # API endpoint permission comes from operator configuration, never an imported document.
        import os

        from anvil.evaluator_http import EvaluatorError, endpoint

        allowed = frozenset(
            filter(None, os.environ.get("ANVIL_EVALUATOR_ALLOWED_ORIGINS", "").split(","))
        )
        if body.adapter == "openlayer" and body.endpoint != "https://api.openlayer.com":
            raise HTTPException(422, "Openlayer requires its documented API origin")
        try:
            endpoint(body.endpoint, allowed)
        except EvaluatorError:
            raise HTTPException(422, "Endpoint is not provisioned for evaluator egress") from None
        try:
            reference = workspace_secrets.save(
                body.secret.get_secret_value(),
                {"project_id": str(project), "evaluator_id": identifier, "adapter": body.adapter},
            )
        except workspace_secrets.StoreUnavailable:
            raise HTTPException(503, "Encrypted evaluator credential store unavailable") from None
    binding = {
        "adapter": body.adapter,
        "adapter_version": ADAPTER_VERSION,
        "configuration": configuration,
    }
    c.execute(
        "INSERT INTO anvil.evaluator_configurations(id,project_id,name,adapter,adapter_version,configuration,configuration_sha256,secret_ref,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            identifier,
            project,
            body.name,
            body.adapter,
            ADAPTER_VERSION,
            Jsonb(configuration),
            digest(binding),
            reference,
            user,
        ),
    )
    audit(c, project, user, "evaluator.configured", identifier, {"adapter": body.adapter})
    return get(c, identifier)


def get(c, identifier):
    row = one(
        c,
        "SELECT id,project_id,name,adapter,adapter_version,configuration,configuration_sha256,created_at FROM anvil.evaluator_configurations WHERE id=%s",
        (identifier,),
    )
    if not row:
        raise HTTPException(404, "Evaluator configuration not found")
    revoked = one(
        c, "SELECT 1 FROM anvil.evaluator_revocations WHERE configuration_id=%s", (identifier,)
    )
    receipt = one(
        c,
        "SELECT id,evidence,evidence_sha256,created_at FROM anvil.evaluator_validation_receipts WHERE configuration_id=%s ORDER BY created_at DESC,id DESC LIMIT 1",
        (identifier,),
    )
    row["validation"] = receipt
    local = row["adapter"] in LOCAL_ADAPTERS
    try:
        if row["adapter"] in {"nemo", "promptfoo", "opa-local"}:
            from anvil.evaluator_runtimes import runtime_version

            runtime = runtime_version(row["adapter"])
        else:
            runtime = version("zen-engine") if row["adapter"] == "zen" else ADAPTER_VERSION
    except Exception:
        runtime = None
    try:
        source_hash = adapter_source_sha256(row["adapter"]) if local else None
    except (OSError, ValueError):
        source_hash = None
        runtime = None
    current_receipt = (
        receipt
        and runtime is not None
        and receipt["evidence"].get("runtime_version") == runtime
        and row["adapter_version"] == ADAPTER_VERSION
        and (row["adapter"] != "zen" or runtime == "2.1.3")
        and receipt["evidence"].get("adapter_source_sha256") == source_hash
    )
    row["status"] = (
        "revoked"
        if revoked
        else "ready"
        if local and current_receipt and receipt["evidence"].get("passed") is True
        else "needs_runtime"
        if local and runtime is None
        else "needs_testing"
        if local
        else "needs_live_validation"
    )
    return row


def test(c, project, user, identifier, body):
    row = get(c, identifier)
    if row["status"] == "revoked":
        raise HTTPException(409, "Revoked evaluator cannot be tested")
    if row["adapter"] not in LOCAL_ADAPTERS:
        raise HTTPException(
            409, "Live API validation requires separate bounded dispatch configuration"
        )
    rule = Rule.model_validate(row["configuration"]["rule"])
    if row["adapter"] in {"nemo", "promptfoo", "opa-local"}:
        import os
        from functools import partial

        from anvil.evaluator_runtimes import evaluate_library, runtime_version

        execute = (
            partial(
                evaluate_opa,
                binary=os.environ.get("ANVIL_OPA_BINARY", ""),
                expected_sha256=os.environ.get("ANVIL_OPA_SHA256", ""),
            )
            if row["adapter"] == "opa-local"
            else partial(evaluate_library, row["adapter"])
        )
    else:
        execute = evaluate_zen if row["adapter"] == "zen" else evaluate
    results = []
    try:
        for case in body.cases:
            actual = execute(rule, case.facts)["outcome"]
            results.append(
                {
                    "expected": case.expected,
                    "actual": actual,
                    "matched": actual == case.expected,
                    "facts_sha256": digest(case.facts),
                }
            )
        runtime = (
            runtime_version(row["adapter"])
            if row["adapter"] in {"nemo", "promptfoo", "opa-local"}
            else version("zen-engine")
            if row["adapter"] == "zen"
            else ADAPTER_VERSION
        )
    except Exception:
        raise HTTPException(503, "Evaluator runtime failed; no Ready receipt was created") from None
    evidence = {
        "passed": all(r["matched"] for r in results),
        "cases": results,
        "runtime_version": runtime,
        "kind": "local_known_cases",
        "provider_calls": 0,
        "adapter_source_sha256": adapter_source_sha256(row["adapter"]),
    }
    receipt = uid()
    c.execute(
        "INSERT INTO anvil.evaluator_validation_receipts(id,project_id,configuration_id,configuration_sha256,evidence,evidence_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (
            receipt,
            project,
            identifier,
            row["configuration_sha256"],
            Jsonb(evidence),
            digest(evidence),
            user,
        ),
    )
    audit(
        c,
        project,
        user,
        "evaluator.tested",
        identifier,
        {"receipt_id": receipt, "passed": evidence["passed"]},
    )
    return get(c, identifier)
