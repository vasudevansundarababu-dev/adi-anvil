"""Pure API-only capture qualification wiring. No secrets/probes/deployment."""

import copy
import re

from infra.gcp.qa_native_wiring import append_mount, mount

BASE = "/var/lib/anvil-qa-v1"
TRUST = BASE + "/runtime-functional/capture-database-trust"
RECEIPTS = BASE + "/runtime-functional/capture-database-qualification"
PRIVATE_ENV = BASE + "/config/capture-runtime.env"


def apply(config, backend_image, target_sha256):
    if (not re.fullmatch(r"us-west1-docker\.pkg\.dev/adi-anvil-mvp-2026/anvil-qa-v1/backend@sha256:[a-f0-9]{64}", backend_image)
            or not re.fullmatch(r"[a-f0-9]{64}", target_sha256)):
        raise ValueError("Exact installed capture image and target required")
    result = copy.deepcopy(config)
    api = result["services"]["api"]
    if api["image"] != backend_image:
        raise ValueError("Capture receipt must bind the actual API image")
    environment = api.setdefault("environment", {})
    if any(environment.get(name, "false") != "false" for name in (
            "ANVIL_LIVE_PROVIDERS_ENABLED", "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED",
            "ANVIL_PRAXIS_TEMPLATE_CALLS_ENABLED", "ANVIL_REAL_EMAIL_ENABLED")):
        raise ValueError("Capture wiring cannot activate live integrations")
    if "DATABASE_URL" in environment:
        raise ValueError("Reconcile an existing explicit database override before capture wiring")
    files = api.setdefault("env_file", [])
    if (not isinstance(files, list) or any(type(item) is not str or not item.startswith("/") for item in files)
            or PRIVATE_ENV in files):
        raise ValueError("Explicit unreplayed private environment file required")
    files.append(PRIVATE_ENV)
    environment.update(
        ANVIL_CAPTURE_DATABASE_TARGET_SHA256=target_sha256,
        ANVIL_CAPTURE_DATABASE_IMAGE_DIGEST=backend_image.rsplit("sha256:", 1)[1],
        ANVIL_CAPTURE_DATABASE_QUALIFICATION_FILE="/app/.data/runtime-qualification/capture-database/current.json",
    )
    append_mount(api, mount(TRUST, "/app/.data/capture-database-trust", True))
    append_mount(api, mount(RECEIPTS, "/app/.data/runtime-qualification/capture-database", True))
    return result
