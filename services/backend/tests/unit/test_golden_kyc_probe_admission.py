"""Manufactured plan controls: local test custody never authorizes QA execution."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from anvil.environment_harbor import operator_proof_module


@pytest.fixture
def probe(tmp_path, monkeypatch):
    module = operator_proof_module()
    root, repository = tmp_path / "operator", tmp_path / "repository"
    root.mkdir(mode=0o700)
    repository.mkdir()
    for folder in (*module.TechnicalProbeStore.DIRECTORIES, "operation-assets"):
        (root / folder).mkdir(mode=0o700)
    dependencies = {}
    for path in module.REQUIRED_DEPENDENCIES | {
        "services/harbor/src/anvil_harbor/operator_proof.py"
    }:
        file = repository / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"synthetic source control")
        file.chmod(0o600)
        dependencies[path] = module.sha(file.read_bytes())
    assets = {}
    for name in module.TechnicalProbeStore.ASSETS:
        raw = module.canonical({"synthetic_asset": name})
        pin = module.sha(raw)
        path = root / "operation-assets" / (pin + ".json")
        path.write_bytes(raw)
        path.chmod(0o600)
        assets[name] = pin
    now = datetime(2026, 11, 18, 14, tzinfo=timezone.utc)
    context = {
        "kind": "golden_kyc_software_v1",
        "project_id": str(uuid4()),
        "user_id": str(uuid4()),
        "paid_calls": False,
        "pack_id": "synthetic-pack",
        "application_id": "synthetic-case",
        "environment_version": "synthetic-v1",
        "snapshot_sha256": "a" * 64,
        "script_sha256": module.sha(module.canonical(module.TechnicalProbeStore.SCRIPT)),
    }
    actor = {
        key: context[key]
        for key in (
            "paid_calls",
            "application_id",
            "environment_version",
            "snapshot_sha256",
            "script_sha256",
        )
    }
    job = str(uuid4())
    plan = {
        "schema_version": "anvil.kyc-technical-probe-plan.v1",
        "job_id": job,
        "operation_nonce": "b" * 64,
        "authorization_scope": "fixed_two_read_software_control_only",
        "request_reference": "Synthetic regression fixture; not human approval",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=5)).isoformat(),
        "host_domain": {"synthetic": "host"},
        "request_capsule": {"actor": actor, "business_context": context},
        "dependency_source_sha256s": dependencies,
        "asset_sha256s": assets,
        "service_projection_sha256s": {
            "environment": assets["environment_service"],
            "tests": assets["tests_service"],
        },
        "limits": dict(module.TechnicalProbeStore.LIMITS),
    }
    store = module.TechnicalProbeStore.for_owned_local_test(root, repository, clock=lambda: now)
    monkeypatch.setattr(store, "_domain", lambda: {"synthetic": "host"})

    def save():
        path = root / "technical-probe-plans" / (job + ".json")
        path.write_bytes(module.canonical(plan))
        path.chmod(0o600)

    save()
    yield module, store, plan, save
    store.close()


def test_local_plan_never_creates_qualification_or_business_authority(probe):
    _, store, plan, _ = probe
    result = store.load_probe(plan["job_id"])
    assert result["custody_scope"] == "owned_test_NOT_QA"
    for key in (
        "technical_probe_authorized",
        "qualification_granted",
        "business_operation_authorized",
        "dispatch_authorized",
        "native_trial_qualified",
    ):
        assert result[key] is False
    with pytest.raises(RuntimeError, match="actual_QA_operator_probe_custody_required"):
        store.enter_probe(plan["job_id"])


@pytest.mark.parametrize(
    "change",
    ["future", "expired", "paid", "extra_action", "host", "source", "asset", "expanded_scope"],
)
def test_wrong_or_stale_probe_plan_cannot_authorize_attempt(probe, change):
    _, store, plan, save = probe
    if change == "future":
        plan["created_at"] = "2026-11-19T00:00:00+00:00"
    elif change == "expired":
        plan["expires_at"] = plan["created_at"]
    elif change == "paid":
        plan["request_capsule"]["business_context"]["paid_calls"] = True
    elif change == "extra_action":
        plan["limits"]["actions"] = 3
    elif change == "host":
        plan["host_domain"] = {"synthetic": "other"}
    elif change == "source":
        next(iter(plan["dependency_source_sha256s"]))
        plan["dependency_source_sha256s"][next(iter(plan["dependency_source_sha256s"]))] = "0" * 64
    elif change == "asset":
        plan["asset_sha256s"]["task_package"] = "0" * 64
    else:
        plan["authorization_scope"] = "business_dispatch"
    save()
    with pytest.raises((RuntimeError, OSError)):
        store.load_probe(plan["job_id"])


def test_probe_plan_cannot_carry_predeclared_qualification(probe):
    _, store, plan, save = probe
    plan["native_trial_qualified"] = True
    save()
    with pytest.raises(RuntimeError, match="exact_technical_probe_plan_required"):
        store.load_probe(plan["job_id"])


def test_framework_dictionary_is_not_an_entry_argument(probe):
    _, store, plan, _ = probe
    with pytest.raises(TypeError):
        store.enter_probe(plan["job_id"], {"framework_trial_id": str(uuid4())})


def test_local_scope_label_cannot_substitute_for_physical_qa_custody(probe):
    _, store, plan, _ = probe
    store.scope = "root_owned_prestart_binding_only"
    assert store.load_probe(plan["job_id"])["technical_probe_authorized"] is False


def test_unknown_outcome_preserves_unknown_actual_calls_and_never_replays(probe):
    module, store, plan, _ = probe
    job = plan["job_id"]
    # Manufactured local ledger data only: owned_test_NOT_QA cannot enter effects.
    intent = {
        "schema_version": "anvil.kyc-technical-probe-intent.v1",
        "job_id": job,
        "operation_nonce": plan["operation_nonce"],
        "plan_sha256": "a" * 64,
        "request_sha256": "b" * 64,
        "entered_at": plan["created_at"],
        "framework_identity": {},
        "framework_observation": {},
        "custody_scope": "owned_test_NOT_QA",
        "no_replay": True,
        "model_calls_authorized": 0,
        "qualification_granted": False,
    }
    pin = store._write_once("technical-probe-intents", job + ".json", intent)
    store._clock = lambda: datetime(2026, 12, 12, tzinfo=timezone.utc)
    store.finish_probe(job, pin, state="unknown", evidence_sha256="c" * 64)
    body = module.parse(store._read("technical-probe-outcomes", job + ".json"))
    assert body["actual_model_calls"] is None and body["model_calls_authorized"] == 0
    assert body["custody_scope"] == "owned_test_NOT_QA"
    assert body["evidence_reference_verified"] is False and body["qualification_granted"] is False
    with pytest.raises(FileExistsError):
        store.finish_probe(job, pin, state="observed", evidence_sha256="c" * 64)
    with pytest.raises(FileExistsError):
        store._write_once("technical-probe-intents", job + ".json", intent)


@pytest.mark.parametrize("namespace", ["pid", "user"])
def test_framework_uses_actual_target_kernel_namespaces(probe, tmp_path, monkeypatch, namespace):
    module, store, plan, save = probe
    domain = {"boot_id": "synthetic-boot", "pid_namespace": "pid:[1]", "user_namespace": "user:[1]"}
    plan["host_domain"] = domain
    monkeypatch.setattr(store, "_domain", lambda: domain)
    attempt = store.root / "technical-probe-attempts" / plan["operation_nonce"]
    attempt.mkdir(mode=0o700)
    host_raw = module.canonical({"folder": str(attempt), "python": "/synthetic/python"})
    host_pin = module.sha(host_raw)
    host = store.root / "operation-assets" / (host_pin + ".json")
    host.write_bytes(host_raw)
    host.chmod(0o600)
    plan["asset_sha256s"]["host_image_custody"] = host_pin
    save()
    for filename, record in [
        ("framework-entry.json", {}),
        (
            "framework-process.json",
            {"pid": 12345, "identity": "linux:synthetic-boot:12345:99", "host_domain": domain},
        ),
    ]:
        p = attempt / filename
        p.write_bytes(module.canonical(record))
        p.chmod(0o600)
    permission = store.load_probe(plan["job_id"])
    proc = tmp_path / "proc" / "12345"
    (proc / "ns").mkdir(parents=True)
    (proc / "stat").write_text("12345 (python) " + " ".join(["S"] + ["0"] * 18 + ["99"]))
    (proc / "ns/pid").symlink_to("pid:[2]" if namespace == "pid" else "pid:[1]")
    (proc / "ns/user").symlink_to("user:[2]" if namespace == "user" else "user:[1]")
    original = module.Path
    monkeypatch.setattr(
        module,
        "Path",
        lambda value: tmp_path / "proc" if str(value) == "/proc" else original(value),
    )
    with pytest.raises(RuntimeError, match="kernel_namespace_changed"):
        store._framework_entry(permission)
