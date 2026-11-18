from uuid import uuid4

import pytest

from anvil import cloud_secrets, open_weight_catalog, providers, workspace_credentials
from anvil import workspace_models as models
from anvil.workspace_preparation import model_snapshot


def profile(**changes):
    return models.ModelProfile(
        **{
            "name": "Workbook model",
            "provider": "huggingface",
            "model_id": "owner/model",
            "open_weight_catalog_id": "ow-r2-v1",
            "hub_revision": "a" * 40,
            **changes,
        }
    )


def test_catalog_preserves_every_row_and_separates_only_display_alternatives():
    catalog = open_weight_catalog.catalog()
    assert len(open_weight_catalog.ROWS) == 17
    assert len(catalog["items"]) == 24
    assert len({i["id"] for i in catalog["items"]}) == 24
    assert {i["source_row"] for i in catalog["items"]} == set(range(2, 19))
    assert catalog["items"][0]["label"] == "Qwen/Qwen3.6-35B-A3B"
    assert all(i["repository_state"] == "public_metadata_observed" for i in catalog["items"])
    assert sum(len(i["repositories"]) for i in catalog["items"]) == 32
    assert all(
        len(repo["revision"]) == 40 and repo["access_state"] == "not_checked"
        for item in catalog["items"]
        for repo in item["repositories"]
    )
    assert not catalog["live_available"]


@pytest.mark.parametrize(
    "changes",
    [
        {"hub_revision": None},
        {"hub_revision": "main"},
        {"hub_revision": "a" * 39},
        {"model_id": "Alias"},
        {"model_id": "owner/model@main"},
        {"open_weight_catalog_id": "not-in-workbook"},
        {"provider": "openai"},
    ],
)
def test_unresolved_repository_or_revision_cannot_become_a_model_binding(changes):
    with pytest.raises(ValueError):
        profile(**changes)


def test_hf_token_uses_existing_binding_without_enabling_dispatch_adapter():
    credential = workspace_credentials.Credential(
        name="Shared Hub token", provider="huggingface", secret="test-only-token"
    )
    assert credential.provider == "huggingface"
    cloud_secrets.validate_binding(
        {k: str(uuid4()) for k in ("project_id", "credential_id", "version_id")}
        | {"provider": "huggingface"}
    )
    assert "huggingface" not in providers.PROVIDERS
    first = profile(credential_id=uuid4(), credential_version_id=uuid4())
    second = profile(
        model_id="another/model",
        credential_id=first.credential_id,
        credential_version_id=first.credential_version_id,
    )
    assert first.credential_id == second.credential_id


def test_snapshot_keeps_exact_hub_revision_separate_from_configuration_version():
    hub = {"catalog_id": "ow-r2-v1", "repository": "owner/model", "revision": "a" * 40}
    row = {
        "id": str(uuid4()),
        "provider_key": "huggingface",
        "model_id": "owner/model",
        "destination": models.WORKSPACE_PROVIDERS["huggingface"][2],
        "config_hash": "f" * 64,
        "config": {"workspace_hub": hub, "workspace_model_revision": 3},
    }
    frozen = model_snapshot(row)
    row["config"]["workspace_hub"]["revision"] = "b" * 40
    assert frozen["hub"]["revision"] == "a" * 40
    assert frozen["group"] == "open-weight-models"


def test_bulk_registration_rejects_unknown_pins_duplicates_and_partial_token_binding():
    item = open_weight_catalog.catalog()["items"][0]
    repo = item["repositories"][0]
    selection = {
        "catalog_id": item["id"],
        "repository": repo["repository"],
        "revision": repo["revision"],
    }
    assert models.CatalogRegistration(models=[selection]).credential_id is None
    for body in [
        {"models": [selection, selection]},
        {"models": [selection | {"revision": "0" * 40}]},
        {"models": [selection | {"repository": "unknown/unknown"}]},
        {"models": [selection], "credential_id": str(uuid4())},
    ]:
        with pytest.raises(ValueError):
            models.CatalogRegistration(**body)
