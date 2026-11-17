"""Read operator-installed independent qualification evidence; never create it.

Actual release qualification supplies this read-only record AFTER real gates pass.
An actor, uploaded task or Admin authoring payload cannot qualify installed code.
"""

import os
import re
import stat
from pathlib import Path

from anvil.praxis_generic_contract import load

ROOT = Path(os.environ.get("ANVIL_ROOT",Path(__file__).resolve().parents[4]))


def installed():
    configured = os.environ.get("ANVIL_GOLDEN_PAID_QUALIFICATION_FILE")
    if not configured:
        return {"ready": False, "missing": ["independent_paid_runtime_qualification_required"]}
    try:
        path = Path(configured)
        for variable, default in (
            ("ARTIFACT_ROOT", ".data/artifacts"),
            ("ANVIL_BENCHMARK_VAULT_ROOT", ".data/benchmark-vault"),
        ):
            storage = Path(os.environ.get(variable, default))
            if not storage.is_absolute():
                storage = ROOT / storage
            if path.resolve().is_relative_to(storage.resolve()):
                raise ValueError(
                    "Uploaded actor/private artifacts cannot qualify installed runtime"
                )
        if (
            not path.is_absolute()
            or not path.is_relative_to(ROOT)
            or path.resolve() != path
            or path.is_symlink()
        ):
            raise ValueError("Invalid installed qualification location")
        for parent in path.parents:
            if parent.is_symlink():
                raise ValueError("Symlink qualification path")
            if parent == ROOT:
                break
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or info.st_size > 65536:
            raise ValueError("Qualification must be bounded and not writable by other identities")
        if info.st_uid not in {0, os.geteuid()}:
            raise ValueError("Operator-owned qualification required")
        body = load(path.read_bytes())
        from anvil.golden_kyc_source import source_hash
        from anvil.harbor_agent_source import code_digest

        if (
            body.get("schema_version") != "anvil.golden-paid-installed-qualification.v2"
            or body.get("qualified") is not True
            or body.get("origin") != "independent_qa"
            or body.get("golden_source_sha256") != source_hash()
            or body.get("broker_source_sha256") != code_digest()
            or body.get("runtime_image_sha256") != os.environ.get("ANVIL_RUNTIME_IMAGE_DIGEST")
            or not isinstance(body.get("runtime_image_sha256"), str)
            or re.fullmatch(r"[a-f0-9]{64}", body["runtime_image_sha256"]) is None
            or not isinstance(body.get("review_receipt_sha256"), str)
            or len(body["review_receipt_sha256"]) != 64
            or re.fullmatch(r"[a-f0-9]{64}", body["review_receipt_sha256"]) is None
            or body.get("openenv_version") != "0.12.0"
            or body.get("shared_sql071_budget_tests_passed") is not True
            or body.get("private_actor_grader_isolation_passed") is not True
            or body.get("harbor_version") != "0.25.0"
            or body.get("actual_candidate_harbor_trial_passed") is not True
            or body.get("native_bridge_isolation_and_no_replay_passed") is not True
            or body.get("collection_and_owned_cleanup_passed") is not True
            or body.get("durable_langgraph_phase_checkpoint_tests_passed") is not True
            or body.get("task_aware_catalogue_runtime_qualification_passed") is not True
            or body.get("actual_governed_ai_recommendations_passed") is not True
            or body.get("immutable_task_evaluator_method_bindings_passed") is not True
            or body.get("recommendation_cost_invariance_and_revocation_races_passed") is not True
            or body.get("mcp_sdk_version") != "1.30.0"
            or body.get("actual_mcp_transport_auth_scope_schema_tests_passed") is not True
            or body.get("custom_python_isolation_and_limits_passed") is not True
            or body.get("custom_python_durable_queue_no_replay_passed") is not True
            or body.get("private_python_scoring_binding_and_veto_controls_passed") is not True
            or body.get("kyc_whole_dispatch_deadline_controls_passed") is not True
            or body.get("kyc_cursor_commit_cancel_and_unknown_controls_passed") is not True
            or body.get("kyc_numeric_https_tls_and_credential_deadline_controls_passed") is not True
            or body.get("kyc_private_route_lease_scope_and_no_replay_controls_passed") is not True
            or not re.fullmatch(r"[a-f0-9]{64}",os.environ.get("ANVIL_KYC_RUNTIME_DATABASE_TARGET_SHA256",""))
            or body.get("kyc_runtime_database_target_sha256") != os.environ.get("ANVIL_KYC_RUNTIME_DATABASE_TARGET_SHA256")
            or not re.fullmatch(r"[a-f0-9]{64}",os.environ.get("ANVIL_KYC_RUNTIME_HTTPS_TARGETS_SHA256",""))
            or body.get("kyc_runtime_https_targets_sha256") != os.environ.get("ANVIL_KYC_RUNTIME_HTTPS_TARGETS_SHA256")
            or not re.fullmatch(r"[a-f0-9]{64}",os.environ.get("ANVIL_KYC_BROKER_TARGET_SHA256",""))
            or body.get("kyc_broker_target_sha256") != os.environ.get("ANVIL_KYC_BROKER_TARGET_SHA256")
        ):
            raise ValueError("Qualification does not bind this exact installed code/image")
        return {"ready": True, "evidence": body, "missing": []}
    except (OSError, ValueError, UnicodeError, TypeError):
        return {
            "ready": False,
            "missing": ["installed_paid_runtime_qualification_invalid_or_stale"],
        }
