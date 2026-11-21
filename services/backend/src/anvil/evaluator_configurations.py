"""Project-scoped, append-only evaluator configuration; no live dispatch here."""

from importlib.metadata import version
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field, SecretStr, model_validator

from anvil import workspace_secrets
from anvil.db import Jsonb, audit, digest, one, uid
from anvil.golden_kyc_native_program import Program as KycProgram
from anvil.native_diagnostic import Program as DiagnosticProgram
from anvil.native_ordinal import Award, Program
from anvil.native_semantic import SavedProgram as SemanticProgram
from anvil.policy_rules import Rule, evaluate, evaluate_opa, evaluate_zen
from anvil.praxis_contract import Model
from anvil.qualification_resources import qualification_path, qualification_root
from anvil.schemas import Strict

ADAPTER_VERSION = "anvil-evaluator-v1"
LOCAL_ADAPTERS = {"builtin", "zen", "opa-local", "nemo", "promptfoo"}


def _source_paths(adapter):
    paths = [
        "services/backend/src/anvil/qualification_resources.py",
        "services/backend/src/anvil/software_resource_proof.py",
        "services/backend/src/anvil/policy_rules.py",
        "services/backend/src/anvil/evaluator_configurations.py",
        "services/backend/uv.lock",
    ]
    if adapter == "builtin":
        paths.append("services/backend/src/anvil/native_ordinal.py")
        paths.append("services/backend/src/anvil/native_semantic.py")
        paths.append("services/backend/src/anvil/campaign_semantic_contract.py")
        paths.append("services/backend/src/anvil/native_semantic_validation.py")
        paths.append("services/backend/src/anvil/native_diagnostic.py")
        from anvil.golden_kyc_native_program import SOURCE_PATHS

        paths.extend(SOURCE_PATHS)
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
    return paths


def adapter_source_sha256(adapter, *, _resource_proof=None):
    import hashlib

    from anvil.software_resource_proof import checked_root, checked_sha256

    paths = _source_paths(adapter)
    root = qualification_root() if _resource_proof is None else checked_root(_resource_proof)
    return digest(
        {
            path: hashlib.sha256(qualification_path(root, path).read_bytes()).hexdigest()
            if _resource_proof is None else checked_sha256(_resource_proof, path)
            for path in paths
        }
    )


class Configure(Model):
    name: str = Field(min_length=1, max_length=160)
    adapter: Literal[
        "builtin", "zen", "opa-local", "nemo", "promptfoo", "opa", "arthur", "openlayer"
    ]
    rule: Rule | None = None
    native_ordinal: Program | None = None
    native_semantic: SemanticProgram | None = None
    native_diagnostic: DiagnosticProgram | None = None
    native_kyc: KycProgram | None = None
    endpoint: str | None = Field(default=None, max_length=300)
    resource_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_/-]{1,100}$")
    secret: SecretStr | None = Field(default=None, min_length=1, max_length=4096)

    @model_validator(mode="after")
    def shape(self):
        programs = (self.native_ordinal, self.native_semantic, self.native_diagnostic, self.native_kyc)
        if sum(program is not None for program in programs) > 1:
            raise ValueError("Choose exactly one native evaluator program")
        if any(program is not None for program in programs):
            if (
                self.adapter != "builtin"
                or self.rule is not None
                or self.endpoint
                or self.resource_id
                or self.secret
            ):
                raise ValueError(
                    "Native evaluation requires only the builtin adapter and one native program"
                )
            return self
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
    expected: Literal["pass", "fail", "unknown"] | Award | None


class TestCases(Model):
    cases: list[Case] = Field(min_length=3, max_length=30)

    @model_validator(mode="after")
    def coverage(self):
        values = [c.expected for c in self.cases]
        native = any(type(value) is int or value is None for value in values)
        if native and (
            any(value is not None and type(value) is not int for value in values)
            or set(values) != {0, 1, 2, 3, 4, None}
        ):
            raise ValueError("Native ordinal known cases require all five awards and unscored")
        if not native and set(values) != {"pass", "fail", "unknown"}:
            raise ValueError("Known Pass, Fail and Unknown cases are required")
        if len(str(self.model_dump())) > 100000:
            raise ValueError("Known-case data exceeds configuration bound")
        return self


class SemanticRuntimeTest(Strict):
    model_profile_ids: list[UUID] = Field(min_length=1, max_length=8, strict=True)


class DiagnosticRuntimeTest(Strict):
    pass


def test_kyc_runtime(c, project, user, identifier, *, _resource_proof=None):
    from anvil.golden_kyc_native_program import controls

    row = get(c, identifier, _resource_proof=_resource_proof)
    program = row["configuration"].get("native_kyc")
    if row["status"] == "revoked" or program is None or str(row["project_id"]) != str(project):
        raise HTTPException(409, "Select a current project sealed KYC evaluator")
    try:
        evidence = controls(program, _resource_proof=_resource_proof) | {
            "runtime_version": ADAPTER_VERSION,
            "adapter_source_sha256": adapter_source_sha256("builtin", _resource_proof=_resource_proof),
        }
    except (ValueError, TypeError, KeyError, ImportError, OSError, RuntimeError):
        raise HTTPException(503, "Sealed KYC software controls failed; no receipt was created") from None
    receipt = uid()
    c.execute(
        "INSERT INTO anvil.evaluator_validation_receipts(id,project_id,configuration_id,configuration_sha256,evidence,evidence_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (receipt, project, identifier, row["configuration_sha256"], Jsonb(evidence), digest(evidence), user),
    )
    audit(c, project, user, "evaluator.kyc_software_tested", identifier,
          {"receipt_id": receipt, "case_review_granted": False, "provider_calls": 0})
    return get(c, identifier, _resource_proof=_resource_proof)


def test_diagnostic_runtime(c, project, user, identifier, body):
    from anvil.native_diagnostic import validate

    row = get(c, identifier)
    program = row["configuration"].get("native_diagnostic")
    if row["status"] == "revoked" or program is None:
        raise HTTPException(409, "Select a current typed diagnostic evaluator")
    try:
        evidence = validate(program)
    except (ValueError, TypeError, KeyError, ImportError, OSError, RuntimeError):
        raise HTTPException(
            503, "Diagnostic software controls failed; no receipt was created"
        ) from None
    evidence["adapter_source_sha256"] = adapter_source_sha256(row["adapter"])
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
        "evaluator.diagnostic_software_tested",
        identifier,
        {"receipt_id": str(receipt), "passed": evidence["passed"], "provider_calls": 0},
    )
    return get(c, identifier)


def test_semantic_runtime(c, project, user, identifier, body):
    from anvil.native_semantic_validation import validate
    from anvil.workspace_preparation import model

    row = get(c, identifier)
    program = row["configuration"].get("native_semantic")
    if row["status"] == "revoked" or program is None:
        raise HTTPException(409, "Select a current semantic judge profile")
    if len(set(body.model_profile_ids)) != len(body.model_profile_ids):
        raise HTTPException(422, "Select each saved model protocol binding only once")
    models = [model(c, identifier) for identifier in body.model_profile_ids]
    if program.get("model_selection") == "fixed":
        from anvil.native_semantic import fixed_model

        if len(models) != 1:
            raise HTTPException(422, "Validate only the saved independent judge model")
        try:
            fixed_model(program, row["configuration"], models[0])
        except ValueError as error:
            raise HTTPException(409, str(error)) from None
    try:
        evidence = validate(program, models)
    except Exception:
        raise HTTPException(
            503, "Software protocol validation failed; no validation receipt was created"
        ) from None
    evidence["adapter_source_sha256"] = adapter_source_sha256(row["adapter"])
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
        "evaluator.semantic_software_protocol_tested",
        identifier,
        {"receipt_id": str(receipt), "passed": evidence["passed"], "provider_calls": 0},
    )
    return get(c, identifier)


def create(c, project, user, body, *, _resource_proof=None):
    if _resource_proof is not None:
        from anvil.software_resource_proof import check_connection

        check_connection(_resource_proof, c)
    identifier = uid()
    configuration = body.model_dump(exclude={"secret", "name", "adapter"}, exclude_none=True)
    if body.native_ordinal is not None:
        configuration["native_ordinal"] = body.native_ordinal.model_dump(mode="json")
    if body.native_diagnostic is not None:
        configuration["native_diagnostic"] = body.native_diagnostic.model_dump(mode="json")
    if body.native_semantic is not None:
        configuration["native_semantic"] = body.native_semantic.model_dump(mode="json")
        if body.native_semantic.model_selection == "fixed":
            from anvil.workspace_preparation import model

            configuration["semantic_judge_model"] = model(
                c, body.native_semantic.judge_model_profile_id
            )
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
    return get(c, identifier, _resource_proof=_resource_proof)


def get(c, identifier, *, _resource_proof=None):
    if _resource_proof is not None:
        from anvil.software_resource_proof import check_connection

        check_connection(_resource_proof, c)
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
        source_hash = adapter_source_sha256(row["adapter"], _resource_proof=_resource_proof) if local else None
    except (OSError, ValueError, RuntimeError):
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
    semantic = row["configuration"].get("native_semantic")
    row["evaluation_mode"] = (
        "native_kyc"
        if row["configuration"].get("native_kyc") is not None
        else
        "native_diagnostic"
        if row["configuration"].get("native_diagnostic") is not None
        else "native_semantic"
        if semantic is not None
        else "native_ordinal"
        if row["configuration"].get("native_ordinal") is not None
        else "deterministic"
    )
    diagnostic = row["configuration"].get("native_diagnostic")
    native_kyc = row["configuration"].get("native_kyc")
    if native_kyc is not None:
        from anvil.golden_kyc_native_program import qualified

        if not revoked:
            row["status"] = "ready" if current_receipt and qualified(
                native_kyc, receipt, _resource_proof=_resource_proof
            ) else "needs_testing"
        row["native_kyc_requirements"] = {
            "evidence": "private_sealed_trace", "criterion": native_kyc.get("criterion"),
            "case_expectation_review_required": True, "legal_review_for_state_criteria_required": True,
            "software_validation_only": True, "model_performance": False,
        }
    if diagnostic is not None:
        from anvil.native_diagnostic import VERSION, qualified_receipt

        if not revoked:
            row["status"] = (
                "ready"
                if current_receipt and qualified_receipt(diagnostic, receipt)
                else "needs_testing"
            )
        row["native_diagnostic_requirements"] = {
            "runtime": VERSION,
            "program_sha256": digest(diagnostic),
            "official_points": 0,
            "software_validation_only": True,
            "qualification": "Exact saved target/source/role/reference/runtime qualification required before diagnostic measurement",
        }
    if semantic is not None:
        from anvil.native_semantic import VERSION, qualified_receipt

        if not revoked:
            row["status"] = (
                "ready"
                if current_receipt and qualified_receipt(semantic, receipt)
                else "needs_judge_qualification"
            )
        row["native_semantic_requirements"] = {
            "runtime": VERSION,
            "program_sha256": digest(semantic),
            "native_scale": [0, 1, 2, 3, 4],
            "model_selection": semantic["model_selection"],
            "private_judge_purpose_required": True,
            "shared_candidate_and_judge_budget_required": True,
            "human_calibration_established": False,
        }
    if row["configuration"].get("native_ordinal") is not None:
        from anvil.campaign_ordinal import source_hash as dispatcher_source_hash
        from anvil.native_ordinal import VERSION

        row["native_ordinal_requirements"] = {
            "runtime": VERSION,
            "program_sha256": digest(row["configuration"]["native_ordinal"]),
            "dispatcher_source_sha256": dispatcher_source_hash(),
            "native_scale": [0, 1, 2, 3, 4],
            "human_calibration_established": False,
            "qualification": "Exact source, role, criterion, reference, reviewed calibration and current deployment required before scoring",
        }
    return row


def test(c, project, user, identifier, body, *, _resource_proof=None):
    row = get(c, identifier, _resource_proof=_resource_proof)
    if row["configuration"].get("native_kyc") is not None:
        raise HTTPException(409, "Caller facts cannot qualify sealed KYC grading; use KYC software controls")
    if _resource_proof is not None and row["configuration"].get("native_ordinal") is not None:
        raise RuntimeError("Software resource proof supports deterministic Golden controls only")
    if row["status"] == "revoked":
        raise HTTPException(409, "Revoked evaluator cannot be tested")
    if row["configuration"].get("native_semantic") is not None:
        raise HTTPException(
            409,
            {
                "code": "qualified_private_judge_validation_required",
                "message": "Local known cases cannot qualify a semantic judge; use the private judge-purpose runtime with exact calibration, source rights and shared budget.",
            },
        )
    if row["configuration"].get("native_diagnostic") is not None:
        raise HTTPException(
            409,
            "Boolean examples cannot validate typed diagnostic measurements; use diagnostic software validation",
        )
    if row["adapter"] not in LOCAL_ADAPTERS:
        raise HTTPException(
            409, "Live API validation requires separate bounded dispatch configuration"
        )
    ordinal = row["configuration"].get("native_ordinal")
    if ordinal is not None:
        return test_ordinal(c, project, user, row, body)
    if any(type(case.expected) is int or case.expected is None for case in body.cases):
        raise HTTPException(422, "This evaluator uses Pass, Fail and Unknown cases")
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
        "adapter_source_sha256": adapter_source_sha256(row["adapter"], _resource_proof=_resource_proof),
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
    return get(c, identifier, _resource_proof=_resource_proof)


def test_ordinal(c, project, user, row, body):
    from anvil.native_ordinal import VERSION, evaluate

    if {case.expected for case in body.cases} != {0, 1, 2, 3, 4, None}:
        raise HTTPException(422, "Supply the five native awards and an unscored control")
    results = []
    try:
        for case in body.cases:
            actual = evaluate(row["configuration"]["native_ordinal"], case.facts)
            results.append(
                {
                    "expected": case.expected,
                    "actual": actual["award"],
                    "status": actual["status"],
                    "matched": actual["award"] == case.expected,
                    "facts_sha256": digest(case.facts),
                }
            )
    except (ValueError, TypeError, RecursionError):
        raise HTTPException(
            422, "Native ordinal test evidence is invalid or exceeds its bound"
        ) from None
    evidence = {
        "passed": all(result["matched"] for result in results),
        "cases": results,
        "runtime_version": ADAPTER_VERSION,
        "native_ordinal_version": VERSION,
        "native_program_sha256": digest(row["configuration"]["native_ordinal"]),
        "kind": "local_native_ordinal_known_cases",
        "provider_calls": 0,
        "human_calibration_established": False,
        "adapter_source_sha256": adapter_source_sha256(row["adapter"]),
    }
    identifier = uid()
    c.execute(
        "INSERT INTO anvil.evaluator_validation_receipts(id,project_id,configuration_id,configuration_sha256,evidence,evidence_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (
            identifier,
            project,
            row["id"],
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
        row["id"],
        {"receipt_id": identifier, "passed": evidence["passed"]},
    )
    return get(c, row["id"])
