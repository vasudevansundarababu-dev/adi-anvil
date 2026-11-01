"""Exact paid scope for the one user-selected marketing integration."""

from datetime import datetime, timezone

from fastapi import HTTPException

from anvil import domain
from anvil.db import digest, one
from anvil.marketing_pack import verify_protocol
from anvil.providers import PROVIDERS, secret_presence

AUTHORITY = "user-2026-09-28-openai-gpt-6-sol-marketing-100-usd"
PRICING = "openai-gpt-6-sol-2026-09-28-standard-text-v1"
PRICE_EXPIRES = datetime(2026, 10, 5, tzinfo=timezone.utc)
CAP = 100_000_000
CALL_BOUND = 1_000_000
RUN_BOUND = 13 * CALL_BOUND
GRAPH_VERSION = "marketing-interactive-review-v1"


def config_valid(connection):
    cfg = connection["config"]
    if cfg.get("workspace_profile_version"):
        return False
    return (
        connection["provider_key"] == "openai"
        and connection["model_id"] == "gpt-6-sol"
        and connection["destination"] == PROVIDERS["openai"][2]
        and connection["status"] != "revoked"
        and cfg.get("pricing_revision") == PRICING
        and cfg.get("bound_micro_usd") == CALL_BOUND
        and cfg.get("max_output_tokens") == 8192
        and cfg.get("processing_terms_reviewed") is True
        and datetime.now(timezone.utc) < PRICE_EXPIRES
    )


def real_admin(c, project, user):
    if not one(
        c,
        "SELECT 1 FROM anvil.users u JOIN anvil.memberships m ON m.user_id=u.id WHERE u.id=%s AND u.active AND NOT u.is_synthetic AND m.project_id=%s AND m.role='admin' AND m.active",
        (user, project),
    ):
        raise HTTPException(
            403, "A real active Admin is required; seeded identities cannot approve paid execution"
        )


def quorum(c, connection, purpose, subject):
    return (
        one(
            c,
            """SELECT count(DISTINCT a.approver_id) n FROM anvil.provider_approvals a
      JOIN anvil.users u ON u.id=a.approver_id
      JOIN anvil.memberships m ON m.user_id=u.id AND m.project_id=a.project_id AND m.role='admin'
      WHERE a.connection_id=%s AND a.purpose=%s AND a.subject_hash=%s
      AND a.cap_micro_usd=%s AND a.expires_at>now() AND u.active AND NOT u.is_synthetic AND m.active""",
            (connection["id"], purpose, subject, CAP),
        )["n"]
        >= 1
    )


def scope(run, protocol, connection):
    from anvil.marketing_runtime import harness_digest

    return digest(
        {
            "authority": AUTHORITY,
            "run": str(run["id"]),
            "protocol_hash": protocol["content_hash"],
            "connection_hash": connection["config_hash"],
            "cap_micro_usd": CAP,
            "run_bound_micro_usd": RUN_BOUND,
            "harness": GRAPH_VERSION,
            "harness_sha256": harness_digest(),
            "max_responses": 13,
        }
    )


def binding(c, run):
    protocol = domain.get_revision(c, run["protocol_revision_id"], "protocol", ["approved"])
    p = protocol["content"]
    if p["mode"] != "marketing_interactive_v1" or run["dataset_version_id"]:
        raise HTTPException(409, "Run does not bind the registered interactive marketing task")
    domain.get_revision(c, p["objective_revision_id"], "objective", ["approved"])
    suite = domain.get_revision(c, p["suite_revision_id"], "suite", ["frozen"])["content"]
    verify_protocol(c, p, suite)
    task = domain.get_revision(c, suite["task_revision_ids"][0], "task", ["published"])
    domain.current_source(c, task["content"]["source_revision_id"])
    # Worker cannot read rubric contents; only its current qualification metadata.
    if not one(
        c,
        "SELECT 1 FROM anvil.resources WHERE current_revision_id=%s AND kind='rubric' AND lifecycle='approved'",
        (task["content"]["rubric_revision_id"],),
    ):
        raise HTTPException(409, "Rubric is not currently approved")
    connection = one(c, "SELECT * FROM anvil.connections WHERE id=%s", (p["connection_id"],))
    return protocol, task, connection


def readiness(c, run):
    protocol, task, connection = binding(c, run)
    missing = []
    subject = scope(run, protocol, connection)
    if not config_valid(connection):
        missing.append("reviewed_exact_provider_configuration_and_current_pricing")
    present, error = secret_presence("openai")
    if not present:
        missing.append(error or "secret_missing")
    for operation, destination in [
        ("managed_evaluation", "local_fixture"),
        ("external_processing", "openai"),
    ]:
        if not domain.rights_ok(c, task["content"]["source_revision_id"], operation, destination):
            missing.append("rights_" + operation)
    if not quorum(c, connection, "activation", connection["config_hash"]):
        missing.append("admin_provider_authorization")
    if not quorum(c, connection, "paid_scope", subject):
        missing.append("admin_run_authorization")
    if not one(
        c,
        "SELECT 1 FROM anvil.users u JOIN anvil.memberships m ON m.user_id=u.id WHERE u.id=%s AND u.active AND m.project_id=%s AND m.role IN ('admin','rl-engineer') AND m.active",
        (run["created_by"], run["project_id"]),
    ):
        missing.append("active_run_author")
    window = one(
        c, "SELECT * FROM anvil.evaluation_spend_windows WHERE authority_reference=%s", (AUTHORITY,)
    )
    if window and (
        window["status"] != "active"
        or window["end_at"] <= datetime.now(timezone.utc)
        or window["reserved_micro_usd"]
        + window["settled_micro_usd"]
        + (RUN_BOUND if run["state"] == "draft" else CALL_BOUND)
        > CAP
    ):
        missing.append("spend_window_closed_or_insufficient")
    return {
        "ready": not missing,
        "missing_gates": missing,
        "subject_hash": subject,
        "connection_id": str(connection["id"]),
        "connection_hash": connection["config_hash"],
        "model": "gpt-6-sol",
        "cap_micro_usd": CAP,
        "run_bound_micro_usd": RUN_BOUND,
        "max_responses": 13,
        "pricing_revision": PRICING,
        "pricing_expires_at": PRICE_EXPIRES,
        "secret_present": present,
        "window": window,
    }


def require_ready(c, run):
    result = readiness(c, run)
    if result["missing_gates"]:
        raise HTTPException(409, "Live execution blocked: " + ", ".join(result["missing_gates"]))
    return result
