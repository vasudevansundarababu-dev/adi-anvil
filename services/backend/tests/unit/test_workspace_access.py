import pytest

from anvil.workspace_access import access_projection, capabilities_for, profile_for


@pytest.mark.parametrize(
    ("roles", "profile"),
    [
        ({"admin"}, "admin"),
        ({"researcher"}, "rl_engineer"),
        ({"data-engineer"}, "rl_engineer"),
        ({"advisor"}, None),
        ({"product-owner"}, None),
        ({"reviewer"}, None),
    ],
)
def test_product_profiles_do_not_promote_preserved_review_duties(roles, profile):
    assert profile_for(roles) == profile
    assert access_projection(roles)["grants_changed"] is False


def test_admin_safe_capabilities_include_engineering_without_private_or_paid_roles():
    admin = set(capabilities_for({"admin"}))
    for roles in ({"researcher"}, {"data-engineer"}):
        assert set(capabilities_for(roles)) <= admin
    assert not {"review.approve", "references.read", "paid.activate", "people.manage"} & admin
    assert "harbor.prepare" not in capabilities_for({"data-engineer"})
    assert "models.manage" not in capabilities_for({"researcher"})


def test_historical_mapping_never_overrides_current_grants():
    mapping = {
        "profile": "admin",
        "legacy_roles": ["admin"],
        "mapping_policy": "existing-grants-v1",
        "recorded_at": None,
    }
    result = access_projection({"researcher"}, mapping)
    assert result["profile"] == "rl_engineer"
    assert result["mapping_state"] == "current_grants_changed"
    assert "models.manage" not in result["capabilities"]
    assert access_projection({"admin"}, mapping)["mapping_state"] == "recorded"
