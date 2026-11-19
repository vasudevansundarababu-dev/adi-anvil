"""Service isolation and activation boundaries in the pure QA config generator."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("qa_native_wiring", Path(__file__).resolve().parents[4] / "infra/gcp/qa_native_wiring.py")
wiring = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wiring)


def config():
    return {"services": {name: {"environment": {"DATABASE_URL": "synthetic-role-only"}, "volumes": []}
        for name in ("api", "business-worker", "golden-scheduler", "golden-grader")}}


def test_coordinators_do_not_inherit_sql_or_each_others_private_mounts():
    original = config()
    result = wiring.apply(original, "synthetic-exact-image", "a" * 64)
    assert set(original["services"]) == {"api", "business-worker", "golden-scheduler", "golden-grader"}
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
    value = config()
    value["services"]["golden-scheduler"]["volumes"] = [wiring.mount(wiring.BRIDGE)]
    with pytest.raises(ValueError, match="reconciliation"):
        wiring.apply(value, "synthetic-image", "a" * 64)
