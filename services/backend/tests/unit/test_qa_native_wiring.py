"""Service isolation and activation boundaries in the pure QA config generator."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("qa_native_wiring", Path(__file__).resolve().parents[4] / "infra/gcp/qa_native_wiring.py")
wiring = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wiring)


def config():
    return {"services": {name: {"environment": {"DATABASE_URL": "synthetic-role-only"}, "volumes": []}
        for name in ("api", "worker", "business-worker", "golden-scheduler", "golden-grader")}}


def test_coordinators_do_not_inherit_sql_or_each_others_private_mounts():
    original = config()
    result = wiring.apply(original, "synthetic-exact-image", "a" * 64)
    assert set(original["services"]) == {"api", "worker", "business-worker", "golden-scheduler", "golden-grader"}
    assert all(result["services"][name]["environment"]["ANVIL_RUNTIME_IMAGE_DIGEST"] == "a" * 64 for name in original["services"])
    actor, private = (result["services"][name] for name in ("native-coordinator", "private-scoring-coordinator"))
    assert "DATABASE_URL" not in actor["environment"] and "DATABASE_URL" not in private["environment"]
    actor_sources = {item["source"] for item in actor["volumes"]}
    private_sources = {item["source"] for item in private["volumes"]}
    assert wiring.PRIVATE not in actor_sources
    assert wiring.BRIDGE not in private_sources and wiring.PROOF not in private_sources
    assert "pid" not in private
    assert set(private["cap_add"]) == {"DAC_OVERRIDE", "CHOWN"}
    assert actor["environment"]["ANVIL_LIVE_PROVIDERS_ENABLED"] == "false"
    scheduler_sources = {item["source"] for item in result["services"]["golden-scheduler"]["volumes"]}
    grader_sources = {item["source"] for item in result["services"]["golden-grader"]["volumes"]}
    assert "/run/docker.sock" not in scheduler_sources | grader_sources
    assert wiring.PRIVATE not in scheduler_sources and wiring.BRIDGE not in grader_sources


def test_wiring_cannot_silently_activate_live_or_overwrite_existing_bridge():
    value = config()
    value["services"]["api"]["environment"]["ANVIL_LIVE_PROVIDERS_ENABLED"] = "true"
    with pytest.raises(ValueError, match="live activation"):
        wiring.apply(value, "synthetic-image", "a" * 64)


def test_api_scratch_is_bounded_without_changing_other_role_limits_or_input():
    original = config()
    original["services"]["api"].update(mem_limit="2g", pids_limit=256, tmpfs=["/run:rw,size=16m", "/tmpfs:rw,size=16m"])
    generated = wiring.apply(original, "synthetic-image", "a" * 64)
    assert generated["services"]["api"]["tmpfs"] == ["/run:rw,size=16m", "/tmpfs:rw,size=16m", wiring.SCRATCH]
    assert generated["services"]["api"]["mem_limit"] == "2g"
    assert generated["services"]["api"]["pids_limit"] == 256
    assert original["services"]["api"]["tmpfs"] == ["/run:rw,size=16m", "/tmpfs:rw,size=16m"]
    assert all("tmpfs" not in generated["services"][role] for role in ("worker", "business-worker", "golden-scheduler", "golden-grader"))


@pytest.mark.parametrize("entries", [["/tmp:rw,exec,size=128m"], ["/tmp:rw,size=1g"],
    [wiring.SCRATCH, wiring.SCRATCH], ["/tmp/nested:rw"], {"/tmp": "rw"},
    ["/:rw"], ["//tmp:rw"], ["/other/../tmp:rw"], ["/./tmp:rw"], ["relative:rw"]])
def test_conflicting_api_scratch_is_rejected_without_overwriting(entries):
    value = config()
    value["services"]["api"]["tmpfs"] = entries
    with pytest.raises(ValueError, match="scratch mount"):
        wiring.apply(value, "synthetic-image", "a" * 64)
    assert value["services"]["api"]["tmpfs"] == entries


@pytest.mark.parametrize("target", ["/", "//tmp", "/other/../tmp", "/./tmp", "/tmp/", "relative", None])
def test_api_scratch_rejects_ambiguous_or_overlapping_bind_destinations(target):
    value = config()
    value["services"]["api"]["volumes"] = [wiring.mount("/synthetic", target)] if target is not None else [{"type": "bind", "source": "/synthetic"}]
    with pytest.raises(ValueError, match="scratch mount"):
        wiring.apply(value, "synthetic-image", "a" * 64)


def test_existing_exact_api_scratch_is_not_duplicated_or_overlaid_by_bind():
    value = config()
    value["services"]["api"]["tmpfs"] = [wiring.SCRATCH]
    assert wiring.apply(value, "synthetic-image", "a" * 64)["services"]["api"]["tmpfs"] == [wiring.SCRATCH]
    value["services"]["api"]["volumes"] = [wiring.mount("/synthetic", "/tmp")]
    with pytest.raises(ValueError, match="scratch mount"):
        wiring.apply(value, "synthetic-image", "a" * 64)


def test_software_grader_wiring_passes_actual_dispatch_flag_validator():
    from anvil.golden_kyc_service import validate_environment

    value = config()
    value["services"]["golden-grader"]["environment"] = {
        "ANVIL_GOLDEN_KYC_ENABLED": "true",
        "ANVIL_GOLDEN_GRADER_DATABASE_URL": "synthetic-disjoint-login-no-connection",
        "ANVIL_LIVE_PROVIDERS_ENABLED": "false",
    }
    generated = wiring.apply(value, "synthetic-image", "a" * 64)
    environment = generated["services"]["golden-grader"]["environment"]
    assert environment["ANVIL_CUSTOM_PYTHON_SCORING_ENABLED"] == "false"
    validate_environment("grader", environment)
    value = config()
    value["services"]["golden-scheduler"]["volumes"] = [wiring.mount(wiring.BRIDGE)]
    with pytest.raises(ValueError, match="reconciliation"):
        wiring.apply(value, "synthetic-image", "a" * 64)
