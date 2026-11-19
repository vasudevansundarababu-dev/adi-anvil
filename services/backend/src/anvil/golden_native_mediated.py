"""Owned mediated worker collection, disjoint from fixed software admissions.

Runtime qualification admits physical collection only. The worker's fixed guard
and existing broker retain all current job/model/key/rights/budget authority.
No source supplied by Authoring is imported or executed by this protocol.
"""

import hashlib
import json
import os
import re
import stat
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from anvil.praxis_generic_contract import canonical, digest

SCHEMA = "anvil.owned-mediated-trial-plan.v1"
PURPOSE = "kyc_worker_collection_only"


def control(value):
    return value.get("schema_version") == "anvil.native-control-bridge-request.v2"


def purpose(value):
    return "native_transport_control_only" if control(value) else PURPOSE


def operation_nonce(path, value):
    return digest({"attempt": Path(path).stem, "binding": value["binding_sha256"], "request": digest(value)})


def read_owned(path, owner):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError("Canonical private mediated record required")
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != owner or info.st_mode & 0o077
                or info.st_nlink != 1 or info.st_size > 262144):
            raise ValueError("Owned bounded mediated record required")
        raw = stream.read(262145)
    value = json.loads(raw)
    if canonical(value) != raw:
        raise ValueError("Canonical immutable mediated bytes required")
    return value


def request(value):
    from anvil.golden_native_bridge import validate_binding

    keys = {"schema_version", "binding", "binding_sha256", "public_actor", "gateway_socket", "gateway_token", "deadline", "actor_seconds",
            "handler", "preparation_sha256", "original_deadline_monotonic"}
    if (set(value) != keys or value["schema_version"] not in {"anvil.native-bridge-request.v2", "anvil.native-control-bridge-request.v2"}
            or value["handler"] != ("fixed_custody_ping_v2" if control(value) else "kyc_worker_candidate_v2") or type(value["actor_seconds"]) is not int
            or not 1 <= value["actor_seconds"] <= 300 or digest(value["binding"]) != value["binding_sha256"]
            or not re.fullmatch("[a-f0-9]{64}", value["preparation_sha256"])
            or not re.fullmatch("[a-f0-9]{64}", value["gateway_token"])
            or type(value["deadline"]) not in (int, float) or not 0 < value["deadline"] - time.time() <= 300
            or type(value["original_deadline_monotonic"]) not in (int, float)
            or not 0 < value["original_deadline_monotonic"] - time.monotonic() <= 300):
        raise ValueError("Exact unexpired fixed worker bridge request required")
    validate_binding(value["binding"], value["public_actor"])
    if control(value):
        from anvil.golden_native_control import PREPARATION, PUBLIC

        if value["public_actor"] != PUBLIC or value["preparation_sha256"] != PREPARATION:
            raise ValueError("Fixed no-effect transport control required")
    return value


@dataclass(frozen=True, slots=True)
class MediatedPlan:
    path: Path
    sha256: str

    def body(self):
        from anvil.golden_component_qualification import installed
        from anvil.golden_native_peer import inspect_sdk

        body = read_owned(self.path, 0)
        if digest(body) != self.sha256 or set(body) != {"schema_version", "purpose", "request", "folder", "assets", "qualification_sha256"}:
            raise ValueError("Exact immutable mediated plan required")
        if body["schema_version"] != SCHEMA or body["purpose"] != purpose(body["request"]):
            raise ValueError("Mediated collection cannot use technical or legacy business authority")
        value = request(body["request"])
        qualified = installed() if not control(value) else None
        if qualified is not None and (not qualified["ready"] or digest(qualified["evidence"]) != body["qualification_sha256"]):
            raise ValueError("Current independent component qualification required")
        assets = body["assets"]
        profile = inspect_sdk(assets["host_image_custody"]["docker_host"])
        if (profile != assets["host_image_custody"]["sdk_profile"]
                or qualified is not None and digest(profile) != qualified["evidence"].get("mediated_sdk_profile_sha256")
                or profile["image"].rsplit("sha256:", 1)[1] != (qualified["evidence"]["runtime_image_sha256"] if qualified is not None else os.environ["ANVIL_RUNTIME_IMAGE_DIGEST"])
                or assets["trial_config"]["task"]["path"] != str(Path(body["folder"]) / "task")
                or assets["trial_config"]["trial_name"] != "anvil-bm-" + self.path.stem[:20]
                or len(canonical(value["public_actor"])) > 49152):
            raise ValueError("Exact qualified SDK image and owned task paths required")
        if control(value):
            validate_transport_profile(profile, self.path.parent.parent, value)
            if body["qualification_sha256"] is not None:
                raise ValueError("A transport control cannot carry qualification authority")
        request(body["request"])
        return body

    def framework(self, child, *, verify_runtime=True):
        from anvil import environment_harbor as native
        from anvil.harbor_worker import process_identity

        body = self.body()
        folder, assets = Path(body["folder"]), body["assets"]
        value = native.owned_json(folder, "framework-entry.json")
        record = native.owned_json(folder, "framework-process.json")
        if (record["pid"] != child.pid or record["identity"] != child._anvil_start_identity
                or process_identity(child.pid) != record["identity"] or value["job_id"] != body["request"]["binding"]["job_id"]
                or value["operation_nonce"] != operation_nonce(self.path, body["request"]) or value["request_sha256"] != digest(body["request"])
                or value["trial_name"] != assets["trial_config"]["trial_name"]
                or time.monotonic_ns() >= record["deadline_monotonic_ns"]):
            raise ValueError("Actual original mediated framework entry required")
        UUID(value["framework_trial_id"])
        raw = (Path("/proc") / str(child.pid) / "cmdline").read_bytes()
        expected = [assets["host_image_custody"]["python"], "-I", "-B", "-m", "anvil_harbor.environment", str(folder / "trial.json")]
        if raw != b"\0".join(item.encode() for item in expected) + b"\0":
            raise ValueError("Fixed installed SDK command required")
        if verify_runtime:
            module = native.operator_proof_module()
            with module.OperatorProofStore(native.ROOT) as store:
                store.validate_runtime_seal(assets["runtime_seal"])


def load_plan(path):
    value = read_owned(path, 0)
    plan = MediatedPlan(Path(path), digest(value))
    plan.body()
    return plan


class MediatedCallback:
    def __init__(self, plan, attempt=None):
        if type(plan) is not MediatedPlan:
            raise ValueError("Exact installed mediated callback required")
        self.plan, self.result = plan, {}
        self.holder = None
        self.attempt = attempt

    def __call__(self):
        from anvil.golden_native_bridge import rpc

        body = self.plan.body()
        value = body["request"]
        from anvil.golden_native_guardian import GuardianServer

        if self.holder is None or self.holder.get("_sdk_peer_lease") is None:
            raise ValueError("Held actual SDK peer required before worker callback")
        if self.attempt is None or self.attempt.name != self.plan.path.stem:
            raise ValueError("Exact original worker attempt required")
        guardian = GuardianServer(self.attempt, value, self.holder, self.plan)
        active = self.holder.setdefault("_mediated_callback_active", threading.Event())
        active.set()
        try:
            guard = rpc(value, "/guard")
            if guard != {"ready": True, "binding_sha256": value["binding_sha256"], "preparation_sha256": value["preparation_sha256"]}:
                raise ValueError("Current leased worker guard required")
            result = rpc(value, "/actor")
        finally:
            try:
                guardian.close()
            finally:
                active.clear()
        if set(result) != {"output", "receipt"} or len(canonical(result)) > 65536:
            raise ValueError("Exact bounded worker capture required")
        self.plan.body()
        self.result.update(result)
        return result["output"], result["receipt"]


def prepare(attempt, work_root, value, *, host, python):
    from anvil import environment_harbor as native
    from anvil.golden_component_qualification import installed
    from anvil.golden_kyc_probe_prepare import compose_services, measured, runtime_seal
    from anvil.golden_native_peer import inspect_sdk

    request(value)
    qualified = installed() if not control(value) else None
    if (qualified is not None and not qualified["ready"]) or os.geteuid() != 0 or str(python) != "/opt/anvil-runtime/bin/python":
        raise ValueError("Qualified root coordinator and exact installed runtime required")
    folder = work_root / attempt.name
    if folder.exists() or not re.fullmatch("[a-f0-9]{32}", attempt.name):
        raise ValueError("Fresh mediated work directory required")
    sdk = inspect_sdk(host)
    if sdk["image"].rsplit("sha256:", 1)[1] != (qualified["evidence"]["runtime_image_sha256"] if qualified is not None else os.environ["ANVIL_RUNTIME_IMAGE_DIGEST"]):
        raise ValueError("Qualified actual SDK image required")
    if qualified is not None and digest(sdk) != qualified["evidence"].get("mediated_sdk_profile_sha256"):
        raise ValueError("Independently reviewed exact mediated SDK profile required")
    if control(value):
        validate_transport_profile(sdk, work_root, value)
    binaries = {"docker": "/usr/bin/docker", "compose": "/usr/libexec/docker/cli-plugins/docker-compose", "opa": "/opt/anvil/opa"}
    module = native.operator_proof_module()
    with module.TechnicalProbeStore(native.ROOT) as store:
        if not store._qa_custody():
            raise ValueError("Actual operator deployment custody required")
        seal = runtime_seal(store)
        actor = value["public_actor"]
        projection = native.layout_projection(folder, actor, mediated_candidate=True, actor_seconds=value["actor_seconds"])
        name = "anvil-bm-" + attempt.name[:20]
        services = compose_services(store, {"binaries": binaries, "docker_host": host}, projection, folder=folder, name=name)
    config = {"task": {"path": str(folder / "task")}, "trial_name": name, "trials_dir": str(folder / "trials"),
              "agent": {"import_path": "anvil_harbor.sme:SMEAgent"},
              "environment": {"import_path": "anvil_harbor.environment:LocalComponentsDocker", "delete": False},
              "verifier": {"import_path": "anvil_harbor.sme:SMEVerifier"}}
    assets = {"runtime_seal": seal, "trial_config": config, "host_image_custody": {"docker_host": host, "python": str(python), "sdk_profile": sdk,
              "binaries": {key: {"path": path, "sha256": measured(path)} for key, path in binaries.items()}},
              "environment_service": services["environment"], "tests_service": services["tests"],
              "validated_limits": {"lifecycle_seconds": min(420, value["actor_seconds"] + 90), "cleanup_seconds": 6}}
    for role in ("environment", "tests"):
        native.prestart_guards().validate_effective_service(services[role], role=role,
            reviewed_service_sha256=hashlib.sha256(canonical(services[role])).hexdigest())
    home = work_root / ".mediated-plans"
    home.mkdir(mode=0o700, exist_ok=True)
    if home.resolve() != home or home.stat().st_uid != 0 or home.stat().st_mode & 0o077:
        raise ValueError("Separate root-owned mediated plan directory required")
    path = home / (attempt.name + ".json")
    body = {"schema_version": SCHEMA, "purpose": purpose(value), "request": value, "folder": str(folder), "assets": assets,
            "qualification_sha256": digest(qualified["evidence"]) if qualified is not None else None}
    native.private_json(path, body)
    return load_plan(path)


def execute(attempt, work_root, value, *, host, python):
    from anvil import environment_harbor as native

    plan = prepare(attempt, work_root, value, host=host, python=python)
    body = plan.body()
    assets = body["assets"]
    bindings = {"job_id": value["binding"]["job_id"], "operation_nonce": operation_nonce(plan.path, value),
                "host_domain": native.process_domain(),
                "request_sha256": digest(value), "callback_manifest_sha256": digest({"handler": value["handler"], "plan_sha256": plan.sha256}),
                "service_projection_sha256s": {role: hashlib.sha256(canonical(assets[role + "_service"])).hexdigest() for role in ("environment", "tests")}}
    callback = MediatedCallback(plan, attempt)
    result = native._execute_lifecycle(Path(body["folder"]), value["public_actor"], callback, host=host, python=Path(python),
        mediated_candidate=True, actor_seconds=value["actor_seconds"], bindings=bindings, fixed_assets=assets, mediated_plan=plan)
    result["worker_bridge_purpose"] = purpose(value)
    return result, callback.result


def validate_transport_profile(profile, work_root, value):
    """Fixed six mounts; the only receipt mount is root-owned/read-only."""
    from anvil import environment_harbor as native

    bridge = Path(value["gateway_socket"]).parent.parent
    # Proof/work root and worker bridge must be disjoint, exact operator paths.
    proof = native.operator_proof_module().ROOT
    if work_root != proof / "native-control-work" or bridge != proof.parent / "native-control-bridge":
        raise ValueError("Fixed disjoint QA transport control roots required")
    expected = {str(proof): (str(proof), True), str(bridge): (str(bridge), True),
                str(native.ROOT / ".data/component-qualification"): (str(proof / "component-qualification"), False),
                "/run/docker.sock": ("/run/docker.sock", False), "/usr/bin/docker": ("/usr/bin/docker", False),
                "/usr/libexec/docker/cli-plugins/docker-compose": ("/usr/libexec/docker/cli-plugins/docker-compose", False)}
    actual = {mount["Destination"]: (mount["Source"], mount["RW"]) for mount in profile["mounts"]}
    if len(profile["mounts"]) != 6 or actual != expected or profile["capabilities"] != ["CHOWN", "DAC_OVERRIDE", "SYS_PTRACE"]:
        raise ValueError("Secret-free exact transport control mount layout required")
