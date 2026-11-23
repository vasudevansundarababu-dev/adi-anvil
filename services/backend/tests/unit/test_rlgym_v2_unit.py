"""RL Gym v2 unit tests: evaluator sandbox, signatures, local-only integrations, hashing contracts. No DB, no network."""

import sys
import time

import pytest

from anvil.config import ROOT
from anvil.rlgym import common, integrations
from anvil.rlgym.catalog import selection
from anvil.rlgym.scoring import sandbox, sandbox_runner

sys.path.insert(0, str(ROOT / "services/stubs"))
import golden_kyc as g  # noqa: E402

PYTHON_FW = {
    "id": "fw-python-1.0.0",
    "runtime_id": "python",
    "installed_locally": True,
    "state": "qualified",
}


@pytest.mark.parametrize("binding", g.evaluator_bindings(), ids=lambda b: b["id"])
def test_every_golden_kyc_known_case_gets_its_distinct_verdict(binding):
    verdicts = {}
    for name, case in binding["known_cases"].items():
        out = sandbox_runner.evaluate(
            {
                "config": binding["config"],
                "evidence": case["evidence"],
                "reference": case["reference"],
            }
        )
        assert out["verdict"] == case["expect"], (name, out)
        verdicts[name] = out["verdict"]
    assert verdicts == {"allowed": "pass", "disallowed": "fail", "missing_evidence": "blocked"}


def test_sandbox_subprocess_matches_in_process_and_is_deterministic():
    binding = g.evaluator_bindings()[4]  # decision
    case = binding["known_cases"]["disallowed"]
    first = sandbox.run(PYTHON_FW, binding["config"], case["evidence"], case["reference"])
    second = sandbox.run(PYTHON_FW, binding["config"], case["evidence"], case["reference"])
    assert first == second
    assert first["verdict"] == "fail"


def test_sandbox_refuses_frameworks_not_installed_locally():
    zen = {
        "id": "fw-zen-2.4.1",
        "runtime_id": "zen",
        "installed_locally": False,
        "state": "registered",
        "install_note": "no image",
    }
    with pytest.raises(common.GymError) as err:
        sandbox.run(zen, {"rules": []}, {}, {})
    assert err.value.code == "VALIDATION_FAILED"


def test_sandbox_runner_reports_broken_configuration_as_error_not_pass():
    out = sandbox.run(
        PYTHON_FW,
        {"evidence": "final_output", "rules": [{"kind": "no_such_rule"}]},
        {"final_output": {}},
        {},
    )
    assert out["verdict"] == "error"


def test_sandbox_runs_isolated_with_empty_environment_and_limits(monkeypatch):
    seen = {}
    real = sandbox.subprocess.run

    def spy(args, **kwargs):
        seen.update(kwargs, args=args)
        return real(args, **kwargs)

    monkeypatch.setattr(sandbox.subprocess, "run", spy)
    sandbox.run(PYTHON_FW, {"evidence": "final_output", "rules": []}, {"final_output": {}}, {})
    assert (
        seen["env"] == {} and "-I" in seen["args"] and seen["timeout"] <= 10 and seen["preexec_fn"]
    )


def test_webhook_signature_valid_stale_and_tampered(monkeypatch):
    monkeypatch.setenv("RLGYM_REGISTRY_WEBHOOK_SECRET", "s3cret-for-unit-test")
    body = b'{"type":"version.qualified"}'
    ts = str(int(time.time()))
    good = {"x-adi-timestamp": ts, "x-adi-signature": common.sign("s3cret-for-unit-test", ts, body)}
    common.verify_signature(good, body)
    with pytest.raises(common.GymError):
        common.verify_signature(good, body + b" ")
    old = str(int(time.time()) - 600)
    with pytest.raises(common.GymError):
        common.verify_signature(
            {
                "x-adi-timestamp": old,
                "x-adi-signature": common.sign("s3cret-for-unit-test", old, body),
            },
            body,
        )


def test_integrations_refuse_non_loopback_targets(monkeypatch):
    monkeypatch.setenv("RLGYM_STUDIO_URL", "https://studio.example.com")
    with pytest.raises(RuntimeError):
        integrations.studio_url()
    monkeypatch.setenv("RLGYM_STUDIO_URL", "http://127.0.0.1:8211")
    assert integrations.studio_url() == "http://127.0.0.1:8211"


def test_package_refs_must_be_forge_stub_refs():
    with pytest.raises(common.GymError):
        integrations.forge_package(
            {"task_id": "t", "package_ref": "file:///etc/passwd", "package_sha256": "0" * 64}
        )
    with pytest.raises(common.GymError):
        integrations.forge_package(
            {
                "task_id": "t",
                "package_ref": "https://evil.example/p.zip",
                "package_sha256": "0" * 64,
            }
        )


def test_stub_and_gym_hash_the_same_way():
    body, packages = g.project_export("exp-0001", "unit")
    assert body["export_sha256"] == common.sha(
        {k: v for k, v in body.items() if k != "export_sha256"}
    )
    for sha, package in packages.items():
        assert common.sha(package) == sha
    t = g.template()
    stripped = {
        k: v
        for k, v in t.items()
        if k not in ("forge_template_id", "forge_version", "spec_sha256", "template_sha256")
    }
    assert t["spec_sha256"] == common.sha(stripped)


def test_seed_matches_the_reference_counts():
    versions = g.environment_versions()
    assert versions["golden-kyc-openenv@v2"]["case_catalog"]["cases"] == 20
    v3 = versions["golden-kyc-openenv@v3"]["case_catalog"]
    assert v3["cases"] == 400
    assert v3["dimensions"]["application_type"] == {p: 100 for p in g.PRODUCTS}
    assert (
        versions["golden-kyc-openenv@v2"]["seed_family"]
        == versions["golden-kyc-openenv@v3"]["seed_family"]
    )
    v2_ids = [c["case_id"] for c in versions["golden-kyc-openenv@v2"]["_cases"]]
    v3_ids = {c["case_id"] for c in versions["golden-kyc-openenv@v3"]["_cases"]}
    assert set(v2_ids) <= v3_ids  # the original 20 are kept in v3
    assert len(g.CRITERIA) == 20 and all(
        w == 5 for w in [b["weight"] for b in g.evaluator_bindings()]
    )
    assert len(g.forge_tasks("exp-0001")) == 40


def test_actor_package_never_contains_reference_answers():
    for task in g.forge_tasks("exp-0001"):
        actor = task["package"]["actor"]
        text = str(actor)
        for secret_field in ("reference", "expected", 'decision": "approve'):
            assert secret_field not in text


def test_rule_labels():
    assert (
        selection.rule_label({"kind": "same_data", "seed_family": "kyc_cases-20261119"})
        == "Same data · kyc_cases-20261119"
    )
    assert (
        selection.rule_label({"kind": "pinned", "pinned_version_id": "golden-kyc-openenv@v2"})
        == "Pinned · golden-kyc-openenv v2"
    )
    assert selection.rule_label({"kind": "latest"}) == "Latest"
    assert selection.rule_label({"kind": "latest_qualified"}) == "Latest qualified"


def test_an_export_names_the_activation_by_either_fingerprint():
    # Studio Golden KYC v4: the RL Gym document's spec_sha256 and Authoring's joint template-version hash.
    from anvil.rlgym.projects.service import template_hash_matches

    act = {
        "spec_sha256": "a583d2e7" + "0" * 56,
        "forge_template_version_hash": "ecf6a72b" + "0" * 56,
    }
    assert template_hash_matches(act, {"spec_sha256": act["spec_sha256"]})
    assert template_hash_matches(act, {"spec_sha256": act["forge_template_version_hash"]})
    assert template_hash_matches(act, {"template_version_hash": act["forge_template_version_hash"]})
    assert not template_hash_matches(act, {"spec_sha256": "f" * 64})
    assert not template_hash_matches(act, {})
    # An activation without Authoring's hash accepts only its own spec_sha256.
    old = {"spec_sha256": act["spec_sha256"], "forge_template_version_hash": None}
    assert not template_hash_matches(old, {"spec_sha256": act["forge_template_version_hash"]})
    assert not template_hash_matches(old, {"spec_sha256": None})


def test_a_package_hash_is_checked_over_the_exact_bytes_adi_forge_served():
    import hashlib
    import json

    from anvil.rlgym.projects.service import package_bytes_match

    # RFC 8785 bytes with decimal weights; a parse and re-dump would write 0.5 and 1e-07, a different hash.
    raw = b'{"actor":{},"criteria":[{"weight":0.50},{"weight":1e-7}],"private":{}}'
    digest = hashlib.sha256(raw).hexdigest()
    assert package_bytes_match(raw, digest)
    redumped = json.dumps(json.loads(raw), sort_keys=True, separators=(",", ":")).encode()
    assert redumped != raw
    assert not package_bytes_match(raw, hashlib.sha256(redumped).hexdigest())
    assert not package_bytes_match(raw + b" ", digest)


def test_package_ref_must_be_forge_packages_with_the_same_hash(monkeypatch):
    import httpx

    from anvil.rlgym import integrations
    from anvil.rlgym.common import GymError

    seen = []

    class Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, headers=None):
            seen.append(url)
            return httpx.Response(200, content=b"{}")

    monkeypatch.setattr(integrations.httpx, "Client", Client)
    h = "a" * 64
    assert (
        integrations.forge_package(
            {"task_id": "t", "package_sha256": h, "package_ref": f"forge://packages/{h}"}
        )
        == b"{}"
    )
    assert seen[-1].endswith(f"/api/v1/packages/{h}")
    for ref in (f"forge://packages/{'b' * 64}", "https://evil.example/p", f"forge://other/{h}", ""):
        with pytest.raises(GymError):
            integrations.forge_package({"task_id": "t", "package_sha256": h, "package_ref": ref})
    assert len(seen) == 1  # a refused reference is never fetched
