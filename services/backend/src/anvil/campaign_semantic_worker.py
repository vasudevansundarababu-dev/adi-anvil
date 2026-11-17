"""Scheduler carries only one leased capability; private grading stays on API."""

import os

import httpx

from anvil import pilot_environment
from anvil.campaign_semantic_contract import Claim
from anvil.config import harbor_live_enabled


def forward(claim, *, transport=None):
    if (
        pilot_environment.current() != "qa"
        or os.environ.get("ANVIL_WORKER_BROKER_ROLE") != "worker"
        or os.environ.get("ANVIL_WORKER_BROKER_ENABLED") != "true"
        or not harbor_live_enabled()
        or os.environ.get("ANVIL_CAMPAIGN_JUDGE_ENABLED") != "true"
        or os.environ.get("ANVIL_WORKER_BROKER_URL")
        != "http://api:8200/internal/v1/worker-dispatch"
    ):
        raise RuntimeError("private_semantic_worker_disabled_or_endpoint_invalid")
    if transport is not None and type(transport) is not httpx.MockTransport:
        raise ValueError("Only explicit MockTransport is supported")
    claim = Claim.model_validate(claim)
    try:
        with httpx.Client(
            transport=transport, trust_env=False, follow_redirects=False, timeout=150
        ) as client:
            response = client.post(
                os.environ["ANVIL_WORKER_BROKER_URL"] + "/judge", json=claim.model_dump(mode="json")
            )
            response.raise_for_status()
            if len(response.content) > 2048:
                raise ValueError()
            result = response.json()
            if (
                set(result) != {"status", "result_sha256", "private_result"}
                or result["private_result"] is not True
            ):
                raise ValueError()
            return result
    except Exception:
        raise RuntimeError(
            "private_semantic_broker_unavailable_or_outcome_unknown_no_retry"
        ) from None


def process_one(connections, *, dispatch=forward):
    # No reclaim or heartbeat extension for an uncertain judge request.
    with connections() as c:
        claim = c.execute("SELECT marketing_runtime.claim_semantic_job() AS job").fetchone()["job"]
    if claim is None:
        return None
    return dispatch(claim)
