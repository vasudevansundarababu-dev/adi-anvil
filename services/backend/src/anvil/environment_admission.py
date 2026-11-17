"""Explicit exact-source admission for paid-off environment QA, never model authority."""

import os

from fastapi import HTTPException

from anvil.benchmark_rehearsal import PAID_FLAGS
from anvil.benchmark_rehearsal import enabled as local_enabled


def enabled():
    if os.environ.get("ANVIL_ENV") == "local":
        return local_enabled()
    if (
        os.environ.get("ANVIL_ENV") != "cloud"
        or os.environ.get("ANVIL_ENVIRONMENT_QA_ENABLED") != "true"
    ):
        raise HTTPException(503, "Environment QA execution is disabled")
    if any(
        os.environ.get(flag, "false") != "false"
        for flag in (*PAID_FLAGS, "ANVIL_IMPORT_GENERATION_ENABLED", "ANVIL_GENERATION_ENABLED")
    ):
        raise HTTPException(
            409, "Environment QA requires all paid/provider/generation/email paths off"
        )
    from anvil.environment_execution import source_hash

    if os.environ.get("ANVIL_ENVIRONMENT_QA_SOURCE_SHA256") != source_hash():
        raise HTTPException(409, "Environment QA requires the exact configured execution source")
