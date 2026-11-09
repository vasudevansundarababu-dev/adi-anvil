"""Capability catalog: discoverable does not mean installed or safe to execute."""

from importlib.metadata import version

from anvil.evaluator_runtimes import runtime_version


def catalog():
    rows = []
    for adapter, name, capability in [
        ("builtin", "Anvil structured verifier", "Typed deterministic facts"),
        ("zen", "GoRules ZEN", "Deterministic decision graphs"),
        ("opa-local", "Open Policy Agent", "Pinned generated Rego rules"),
        ("nemo", "NeMo Guardrails", "Literal policy detection only; no model rails"),
        ("promptfoo", "Promptfoo", "Literal assertions only; no model graders"),
    ]:
        try:
            installed = (
                "anvil-evaluator-v1"
                if adapter == "builtin"
                else version("zen-engine")
                if adapter == "zen"
                else runtime_version(adapter)
            )
            status, reason = (
                "installed",
                "Save and pass known allowed/forbidden/missing-evidence cases before Run selection",
            )
        except Exception:
            installed, status, reason = (
                None,
                "unavailable",
                "Pinned runtime missing or incompatible",
            )
        rows.append(
            {
                "id": adapter,
                "name": name,
                "version": installed,
                "status": status,
                "capability": capability,
                "reason": reason,
                "custom_policy": True,
            }
        )
    rows += [
        {
            "id": "arthur",
            "name": "Arthur Engine / Arthur AI",
            "status": "connection_required",
            "capability": "Prompt validation API contract",
            "reason": "API connection can be saved; live authentication and known-case tests remain off",
            "custom_policy": False,
        },
        {
            "id": "openlayer",
            "name": "Openlayer",
            "status": "connection_required",
            "capability": "Existing test evaluation API contract",
            "reason": "API connection can be saved; queued evaluation is never a Pass; live tests remain off",
            "custom_policy": False,
        },
        {
            "id": "opa",
            "name": "OPA API",
            "status": "connection_required",
            "capability": "Deterministic Data API",
            "reason": "Operator-restricted origin and known-case validation required; live calls off",
            "custom_policy": True,
        },
        {
            "id": "trulens",
            "name": "TruEra / TruLens",
            "status": "metric_only",
            "capability": "Pinned 2.16.0 precision metric",
            "reason": "Independent metric harness; not a deterministic custom-policy verifier",
            "custom_policy": False,
        },
        {
            "id": "phoenix",
            "name": "Arize / Phoenix",
            "status": "unavailable",
            "capability": "Observability and evaluation",
            "reason": "No qualified production adapter; selected package licensing/contract requires review",
            "custom_policy": False,
        },
        {
            "id": "fiddler",
            "name": "Fiddler Auditor / Fiddler AI",
            "status": "unavailable",
            "capability": "Audit and monitoring",
            "reason": "Auditor dependency compatibility and licensing unresolved; no safe installed adapter",
            "custom_policy": False,
        },
        {
            "id": "pramaana",
            "name": "Pramaana",
            "status": "unavailable",
            "capability": "Proposed formal verification",
            "reason": "Vendor interface, executable rule format and proof contract not supplied",
            "custom_policy": False,
        },
        {
            "id": "protect-ai",
            "name": "Protect AI / LLM Guard",
            "status": "unavailable",
            "capability": "Archived scanner package",
            "reason": "Archived upstream is not offered as a supported new runtime",
            "custom_policy": False,
        },
    ]
    return rows
