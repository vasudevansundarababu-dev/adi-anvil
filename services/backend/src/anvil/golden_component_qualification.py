"""Independent technical qualification without spending/benchmark authority.

Template/dataset provisioning must precede actual AI recommendations. Requiring
the completed paid benchmark gate for provisioning creates a circular dependency.
This reader admits only non-spending component work; paid admission still calls
golden_kyc_paid_qualification.installed(), with all existing gates intact.
"""

import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path

from anvil.config import ROOT
from anvil.praxis_generic_contract import load

CHECKS = (
    "actual_harbor_trial",
    "openenv_sql_isolation",
    "actual_mcp_auth_schema_reset",
    "durable_checkpoint_recovery",
    "actor_grader_isolation",
    "role_mount_isolation",
    "opa_allow_deny_controls",
    "zen_positive_negative_missing_controls",
    "private_python_scoring_controls",
    "no_model_requests",
)


def sha(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def installed():
    """Read operator evidence; never create, seed or promote qualification."""
    configured = os.environ.get("ANVIL_GOLDEN_COMPONENT_QUALIFICATION_FILE")
    if not configured:
        # Existing full qualification also proves its component subset, without
        # granting any new paid authority. Never reverse this implication.
        from anvil.golden_kyc_paid_qualification import installed as full

        result = full()
        return result | {"scope": "technical_components_only", "spending_authority": False}
    try:
        path = Path(configured)
        if (
            not path.is_absolute()
            or not path.is_relative_to(ROOT)
            or path.resolve() != path
            or path.is_symlink()
        ):
            raise ValueError("Invalid component qualification location")
        for parent in path.parents:
            if parent.is_symlink():
                raise ValueError("Symlink component qualification path")
            if parent == ROOT:
                break
        for variable, default in (
            ("ARTIFACT_ROOT", ".data/artifacts"),
            ("ANVIL_BENCHMARK_VAULT_ROOT", ".data/benchmark-vault"),
        ):
            storage = Path(os.environ.get(variable, default))
            if not storage.is_absolute():
                storage = ROOT / storage
            if path.resolve().is_relative_to(storage.resolve()):
                raise ValueError("Uploaded source cannot qualify runtime")
        info = path.stat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_mode & 0o022
            or info.st_size > 65536
            or info.st_uid not in {0, os.geteuid()}
        ):
            raise ValueError("Bounded operator-owned component receipt required")
        body = load(path.read_bytes())
        from anvil.golden_kyc_anvil import source_hash
        from anvil.harbor_agents import code_digest

        if not isinstance(body, dict) or type(body.get("expires_at")) is not str:
            raise ValueError("Explicit component expiry required")
        expires = datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
        checks = body.get("checks", {})
        if (
            body.get("schema_version") != "anvil.golden-component-installed-qualification.v1"
            or body.get("origin") != "independent_qa"
            or body.get("qualified") is not True
            or body.get("scope") != "technical_components_only"
            or body.get("spending_authority") is not False
            or expires.tzinfo is None
            or expires <= datetime.now(timezone.utc)
            or body.get("golden_source_sha256") != source_hash()
            or body.get("broker_source_sha256") != code_digest()
            or not sha(body.get("runtime_image_sha256"))
            or body["runtime_image_sha256"] != os.environ.get("ANVIL_RUNTIME_IMAGE_DIGEST")
            or not sha(body.get("review_receipt_sha256"))
            or body.get("openenv_version") != "0.12.0"
            or body.get("harbor_version") != "0.25.0"
            or body.get("mcp_sdk_version") != "1.30.0"
            or not isinstance(checks, dict)
            or any(
                not isinstance(checks.get(key), dict)
                or checks[key].get("status") != "passed"
                or not sha(checks[key].get("evidence_sha256"))
                for key in CHECKS
            )
        ):
            raise ValueError("Exact independent technical controls required")
        return {
            "ready": True,
            "evidence": body,
            "missing": [],
            "scope": "technical_components_only",
            "spending_authority": False,
        }
    except (OSError, ValueError, UnicodeError, TypeError, KeyError):
        return {
            "ready": False,
            "missing": ["independent_component_qualification_invalid_or_stale"],
            "scope": "technical_components_only",
            "spending_authority": False,
        }
