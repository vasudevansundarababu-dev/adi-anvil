"""Capture API wiring must not spread credentials or qualification scope."""

from copy import deepcopy

import pytest
from infra.gcp import qa_capture_database_wiring as wiring

IMAGE = "us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil-qa-v1/backend@sha256:" + "a" * 64


def config():
    return {"services": {"api": {"image": IMAGE, "environment": {}, "env_file": ["/private/app.env"]},
                         "worker": {"image": IMAGE}, "golden-scheduler": {"image": "other"}}}


def test_only_api_gets_exact_image_target_and_readonly_trust_and_receipt():
    before = config()
    result = wiring.apply(before, IMAGE, "b" * 64)
    assert before == config()
    assert result["services"]["worker"] == before["services"]["worker"]
    assert result["services"]["golden-scheduler"] == before["services"]["golden-scheduler"]
    api = result["services"]["api"]
    assert api["environment"]["ANVIL_CAPTURE_DATABASE_IMAGE_DIGEST"] == "a" * 64
    assert all(item["read_only"] is True for item in api["volumes"])
    assert api["env_file"][-1] == wiring.PRIVATE_ENV
    assert "DATABASE_URL" not in api["environment"]


@pytest.mark.parametrize("change", ["image", "override", "live", "replay", "mount"])
def test_wrong_image_live_override_replay_and_existing_mount_are_denied(change):
    body = deepcopy(config())
    api = body["services"]["api"]
    if change == "image":
        api["image"] = "unbound"
    elif change == "override":
        api["environment"]["DATABASE_URL"] = "private"
    elif change == "live":
        api["environment"]["ANVIL_LIVE_PROVIDERS_ENABLED"] = "true"
    elif change == "replay":
        api["env_file"].append(wiring.PRIVATE_ENV)
    else:
        api["volumes"] = [wiring.mount(wiring.TRUST, "/app/.data/capture-database-trust", False)]
    with pytest.raises(ValueError):
        wiring.apply(body, IMAGE, "b" * 64)
