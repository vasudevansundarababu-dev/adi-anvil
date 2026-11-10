"""Additive exact-source cloud QA admission for fictional, paid-off controls only."""

import os

from fastapi import HTTPException

from anvil.benchmark_rehearsal import PAID_FLAGS
from anvil.benchmark_rehearsal import enabled as local_enabled


def enabled():
    if os.environ.get("ANVIL_ENV") == "local":
        return local_enabled()
    if (
        os.environ.get("ANVIL_ENV") != "cloud"
        or os.environ.get("ANVIL_BUSINESS_QA_ENABLED") != "true"
        or os.environ.get("ANVIL_QA_ACCEPTANCE_CONTROLS_ENABLED") != "true"
    ):
        raise HTTPException(503, "Fictional business QA execution is disabled")
    if any(os.environ.get(k, "false") != "false" for k in (*PAID_FLAGS, "ANVIL_IMPORT_GENERATION_ENABLED", "ANVIL_GENERATION_ENABLED")):
        raise HTTPException(409, "Business QA requires all paid/provider/generation/email paths off")
    from anvil.benchmark_runs import source_hash

    if os.environ.get("ANVIL_BUSINESS_QA_SOURCE_SHA256") != source_hash():
        raise HTTPException(409, "Business QA requires its exact configured execution source")
