"""Curate root-owned synthetic QA evidence; never copy provider/SQL configs.

This records raw observations and exact retained container identities. It grants
no qualification. The separate validator and independent reviewer must accept
the entire exact-source bundle before any technical receipt can be produced.
"""

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
from pathlib import Path
from uuid import UUID

BASE = Path("/var/lib/anvil-qa-v1/runtime-functional")
PROOF = BASE / "harbor-proof"


def sealed_plan_binding(raw):
    """Hash exact already-canonical seal bytes, without host reserialization.

    The installed reader admitted the canonical root-owned plan. Hashing its
    embedded token bytes preserves JCS Unicode/number ordering on this host,
    whose operator intentionally needs no backend dependency installation.
    """
    text = raw.decode("utf-8")
    marker = '"runtime_seal":'
    if text.count(marker) != 1:
        raise ValueError("One original embedded runtime seal required")
    start = text.index(marker) + len(marker)
    seal, length = json.JSONDecoder().raw_decode(text[start:])
    plan = json.loads(raw)
    if seal != plan["assets"]["runtime_seal"]:
        raise ValueError("Original embedded runtime seal mismatch")
    return {"plan_sha256": hashlib.sha256(raw).hexdigest(),
            "seal_sha256": hashlib.sha256(text[start:start + length].encode("utf-8")).hexdigest(),
            "original_deadline_monotonic": plan["request"]["original_deadline_monotonic"]}


def read(path, *, claim=False):
    path = Path(path)
    info = path.lstat()
    if claim:
        link = (path.parent / "claimed.json").lstat()
        if path.name != "request.json" or info.st_uid != 10001 or info.st_mode & 0o077 or info.st_nlink != 2 or link.st_nlink != 2 or (info.st_dev, info.st_ino) != (link.st_dev, link.st_ino):
            raise ValueError("Exact immutable two-link synthetic private claim required")
    if path.resolve() != path or not path.is_file() or info.st_nlink != (2 if claim else 1) or info.st_size > 16 * 1024**2:
        raise ValueError("Bounded canonical original evidence required")
    return path.read_bytes()


def main(args):
    if os.geteuid() != 0 or os.uname().nodename != "anvil-qa-v1":
        raise ValueError("Existing QA root only")
    release = json.loads(read(args.manifest))
    UUID(args.native_job)
    root = BASE / ("component-evidence-" + release["revision"][:7] + "-" + secrets.token_hex(4))
    root.mkdir(mode=0o700)
    related, packets = {}, {}

    def write(name, raw, *, relation=True):
        target = root / name
        if not target.is_relative_to(root) or ".." in Path(name).parts:
            raise ValueError("Curated file escaped root")
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        pin = hashlib.sha256(raw).hexdigest()
        if relation:
            related[name] = pin
        return {"path": name, "sha256": pin}

    def copy(name, path, *, claim=False, **kw):
        return write(name, read(path, claim=claim), **kw)

    def document(name, value, **kw):
        return write(name, json.dumps(value, sort_keys=True, allow_nan=False).encode(), **kw)

    def inspect(name, identifier, *, image=False):
        result = subprocess.run(["docker", "image" if image else "container", "inspect", identifier], capture_output=True, timeout=10, check=True)
        values = json.loads(result.stdout)
        if len(values) != 1:
            raise ValueError("Exactly one original inspection required")
        document(name, values[0])
        return values[0]

    plan_path = PROOF / "technical-probe-plans" / (args.native_job + ".json")
    plan = json.loads(read(plan_path))
    native_root = PROOF / "technical-probe-attempts" / plan["operation_nonce"]
    packets["native"] = copy("native.json", native_root / "observed-evidence.json", relation=False)
    native_packet = json.loads(read(native_root / "observed-evidence.json"))
    assets = {}
    for name, pin in plan["asset_sha256s"].items():
        ref = "native-assets/" + name + ".json"
        copy(ref, PROOF / "operation-assets" / (pin + ".json"))
        assets[name] = ref
    copy("native-plan.json", plan_path)
    copy("native-cleanup.json", native_root / "cleanup.json")
    copy("native-framework-process.json", native_root / "framework-process.json")
    peers = []
    for index in range(2):
        name = "native-peer-" + str(index) + ".json"
        copy(name, native_root / ("sdk-peer-" + str(index) + ".json"))
        peers.append(name)
    transport_root = Path(args.transport)
    private_root = Path(args.private)
    for path in (transport_root, private_root, Path(args.sql), Path(args.registry), Path(args.components)):
        if path.parent != BASE or path.resolve() != path:
            raise ValueError("Only original fixed QA control roots permitted")
    transport = json.loads(read(transport_root / "evidence.json"))
    private = json.loads(read(private_root / "evidence.json"))
    for name, folder in (("transport", transport_root), ("private", private_root), ("sql", Path(args.sql)),
                         ("registry", Path(args.registry)), ("components", Path(args.components))):
        packets[name] = copy(name + ".json", folder / "evidence.json", relation=False)
    containers = {}

    def container(role, identifier):
        path = "containers/" + role + ".json"
        inspect(path, identifier)
        containers[role] = path

    for item in transport["network_observations"]:
        container(item["role"], item["container"])
        for name, pin in item["traces"].items():
            ref = copy("traces/" + name, transport_root / name, relation=False)
            if ref["sha256"] != pin:
                raise ValueError("Original trace bytes changed")
    mediated_path = PROOF / "native-control-work/.mediated-plans" / (Path(transport["attempt"]).name + ".json")
    mediated = json.loads(read(mediated_path))
    # Do not copy the plan: request.gateway_token is worker-private material.
    integrity_binding = document("mediated-integrity-binding.json", sealed_plan_binding(read(mediated_path)))
    packets["sdk_profile"] = document("sdk-profile.json", mediated["assets"]["host_image_custody"]["sdk_profile"], relation=False)
    native_peer = json.loads(read(native_root / "sdk-peer-0.json"))
    container("native_sdk", native_peer["container_id"])
    trial_name = native_packet["result"]["owned_trial_name"]
    for role, suffix in (("actor", "__env"), ("verifier", "__verifier__trial")):
        result = subprocess.run(["docker", "container", "ls", "-a", "--no-trunc", "--filter",
            "label=com.docker.compose.project=" + trial_name + suffix, "--format", "{{.ID}}"], capture_output=True, timeout=10, check=True)
        values = result.stdout.decode().splitlines()
        if len(values) != 1 or not re.fullmatch("[a-f0-9]{64}", values[0]):
            raise ValueError("Exact owned native actor/verifier inspection required")
        container(role, values[0])
    jobs = {}
    for index, case in enumerate(private["cases"]):
        role = case["control_case"]
        container("executor-" + role, case["executor_container"])
        prefix = "forge-private-" + private_root.name.removeprefix("private-score-")
        container("grader-" + role, prefix + "-grader-" + str(index))
        container("private_coordinator-" + role, prefix + "-coordinator-" + str(index))
        original = private_root / "bridge" / case["job_id"].replace("-", "")
        jobs[case["job_id"]] = {}
        for kind in ("request", "result"):
            name = "private-jobs/" + case["job_id"] + "-" + kind + ".json"
            copy(name, original / (kind + ".json"), claim=kind == "request")
            jobs[case["job_id"]][kind] = name
    installed = {}
    installed_bundles = {}
    installed_sources = {}
    for kind in ("sql", "registry", "components"):
        folder = Path(getattr(args, kind))
        inspect_ref, stdout_ref = "installed/" + kind + ".inspect.json", "installed/" + kind + ".stdout.json"
        copy(inspect_ref, folder / "runtime.inspect.json")
        copy(stdout_ref, folder / "runtime.stdout")
        installed[kind] = {"inspect": inspect_ref, "stdout": stdout_ref}
        raw_inspect = json.loads(read(folder / "runtime.inspect.json"))
        control_mount = [item for item in raw_inspect["Mounts"] if item["Destination"] == "/controls"]
        if len(control_mount) != 1 or not control_mount[0]["Source"].endswith("/runtime-checks"):
            raise ValueError("Exact original control bundle mount required")
        installed_bundles[kind] = str(Path(control_mount[0]["Source"]).parent)
        scripts = [{"sql": "kyc_sql_component_controls.py", "registry": "kyc_policy_registry_controls.py", "components": "component_controls.py"}[kind]]
        if kind != "components":
            scripts.append("kyc_sql_fixture_setup.py")
        if kind == "registry":
            scripts.append("kyc_policy_registry_fixture.py")
        installed_sources[kind] = {}
        for script in scripts:
            relative = "runtime-checks/" + script
            source_path = Path(control_mount[0]["Source"]) / script
            info = source_path.lstat()
            raw = read(source_path)
            if info.st_uid != 0 or info.st_mode & 0o022 or hashlib.sha256(raw).hexdigest() != (release["control_files"] | release["operational_files"])[relative]:
                raise ValueError("Actual root-mounted control source differs from exact release")
            ref = "control-sources/" + kind + "-" + script
            write(ref, raw, relation=False)
            installed_sources[kind][relative] = ref
    runtime = inspect("runtime-image.json", release["images"]["kyc-runtime"], image=True)
    if runtime["Config"]["Labels"]["org.opencontainers.image.revision"] != release["revision"]:
        raise ValueError("Current runtime image required")
    fixture_image = "us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil-qa-v1/native-fixture-security@sha256:72b8eaacefaa82ffdec3ee632375df24057962d8c14cc327f1990113f7c2b951"
    inspect("fixture-image.json", fixture_image, image=True)
    roles = {"schema_version": "anvil.actual-role-isolation-review.v1", "source_sha256": release["source_sha256"],
        "runtime_image": release["images"]["kyc-runtime"], "verified": True, "related_files": related, "containers": containers,
        "private_jobs": jobs, "private_fixture_root": str(private_root), "control_bundle": args.private_bundle,
        "native_plan": "native-plan.json", "native_host_custody": assets["host_image_custody"], "native_assets": assets,
        "native_cleanup": "native-cleanup.json", "native_peers": peers, "runtime_image_inspect": "runtime-image.json",
        "native_framework_process": "native-framework-process.json",
        "mediated_integrity_binding": integrity_binding["path"],
        "fixture_image_inspect": "fixture-image.json", "installed_controls": installed, "installed_control_bundles": installed_bundles,
        "installed_control_sources": installed_sources,
        "qualification_granted": False, "review_scope": "raw_artifacts_curated_not_independent_acceptance"}
    packets["role_isolation"] = document("roles.json", roles, relation=False)
    document("input-without-review.json", {"schema_version": "anvil.component-evidence-bundle.v1", "release": release, "packets": packets}, relation=False)
    print(json.dumps({"root": str(root), "status": "curated_requires_independent_review", "packets": packets, "qualification_granted": False}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "native-job", "transport", "private", "private-bundle", "sql", "registry", "components"):
        parser.add_argument("--" + name, required=True)
    main(parser.parse_args())
