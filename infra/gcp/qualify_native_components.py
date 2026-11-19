"""Root-only QA evidence aggregation; never spending or policy qualification.

Inputs are curated, root-owned raw execution packets and an independent review.
Missing, old-image, partial or unknown evidence fails closed. This is not an API
for uploaded status booleans, legal approvals or authored-task publication.
"""

import argparse
import hashlib
import json
import os
import re
import stat
from datetime import datetime, timedelta, timezone
from importlib import metadata
from pathlib import Path
from uuid import UUID

import rfc8785


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(rfc8785.dumps(value))


def owned(path, limit=2 * 1024**2):
    require(path.is_absolute() and path.resolve() == path, "Canonical root evidence required")
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022
                and info.st_nlink == 1 and info.st_size <= limit, "Private bounded root evidence required")
        return stream.read(limit + 1)


def framework(value, *, mediated):
    UUID(value["framework_trial_id"])
    require(value["harness"] == "harbor-0.25.0-host-mediated-components-v1"
        and value["mediated_candidate"] is mediated and value["native_container_isolation"] is True
        and value["cleanup"] == {"complete": True, "retained": True}
        and value["collection"]["complete"] is True and value["model_performance"] is False
        and value["framework_result"]["trial_id"] == value["framework_trial_id"], "Actual retained isolated Trial required")
    sealed = json.dumps(value["trusted_receipt"], sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    require(sha(sealed) == value["separate_verifier_bytes_sha256"], "Actual separate verifier custody required")


def mounts(info):
    values = info["Mounts"]
    require(all(item["Type"] == "bind" for item in values), "Only exact reviewed binds permitted")
    result = {item["Destination"]: (item["Source"], item["RW"]) for item in values}
    require(len(result) == len(values), "Duplicate mount destinations refused")
    return result


def environment(values):
    result = {}
    for item in values:
        key, value = item.split("=", 1)
        require(key not in result, "Duplicate environment keys refused")
        result[key] = value
    return result


def static_sdk_profile(info, expected_caps):
    from anvil.golden_native_peer import capabilities

    host, config = info["HostConfig"], info["Config"]
    require(config["User"] == "0:0" and capabilities(host.get("CapDrop") or []) == {"ALL"}
        and capabilities(host.get("CapAdd") or []) == set(expected_caps)
        and all(host[key] == "host" for key in ("PidMode", "UTSMode", "UsernsMode", "CgroupnsMode")),
        "Exact actual SDK capability and namespace profile required")
    security = host["SecurityOpt"]
    require(set(security) in ({"no-new-privileges", "apparmor=unconfined"},
        {"no-new-privileges", "apparmor=unconfined", "label=disable"}) and len(set(security)) == len(security),
        "Exact actual SDK security options required")
    mounts(info)
    return {"schema_version": "anvil.owned-sdk-profile.v1", "image": config["Image"], "image_id": info["Image"],
        "mounts": sorted(({key: item[key] for key in ("Type", "Source", "Destination", "RW")} for item in info["Mounts"]), key=lambda item: item["Destination"]),
        "capabilities": sorted(expected_caps), "security_options": sorted(security), "tmpfs": host.get("Tmpfs"),
        "memory": host["Memory"], "pids": host["PidsLimit"], "cpu": host["NanoCpus"]}


def main(input_path, output_path, *, verify_only=False):
    require(os.geteuid() == 0 and os.uname().nodename == "anvil-qa-v1", "Existing QA root operator required")
    root = input_path.parent
    body = json.loads(owned(input_path))
    require(body["schema_version"] == "anvil.component-evidence-bundle.v1", "Exact curated evidence schema required")
    release = body["release"]
    from anvil.golden_kyc_anvil import source_hash
    from anvil.harbor_agents import code_digest

    require(release["schema"] == 133 and release["source_sha256"] == source_hash()
        and release["images"]["kyc-runtime"].rsplit("sha256:", 1)[1] == os.environ.get("ANVIL_RUNTIME_IMAGE_DIGEST"),
        "Current installed source and runtime image required")
    observed = {}
    raw_hashes = {}
    for name, ref in body["packets"].items():
        path = root / ref["path"]
        require(path.is_relative_to(root) and ".." not in Path(ref["path"]).parts, "Curated evidence cannot escape bundle")
        raw = owned(path)
        require(sha(raw) == ref["sha256"], "Raw evidence bytes changed")
        observed[name], raw_hashes[name] = json.loads(raw), sha(raw)
    required = {"native", "transport", "private", "sql", "registry", "components", "sdk_profile", "role_isolation", "review"}
    require(set(observed) == required, "All exact component packets and independent review required")
    for name in ("transport", "private", "sql", "registry", "components"):
        require(observed[name]["release"]["revision"] == release["revision"]
            and observed[name]["release"]["source_sha256"] == release["source_sha256"]
            and observed[name]["release"]["images"]["kyc-runtime"] == release["images"]["kyc-runtime"], "Cross-release evidence refused")

    native, transport = observed["native"], observed["transport"]
    require(native["schema_version"] == "anvil.kyc-native-probe-evidence.v1" and native["qualification_granted"] is False,
        "Actual nonspending SQL Trial packet required")
    framework(native["result"], mediated=False)
    require(native["result"]["trusted_receipt"]["model_performance"] is False, "A control is not model performance")
    framework(transport["framework"], mediated=True)
    require(transport["framework"]["worker_bridge_purpose"] == "native_transport_control_only", "No-effect transport purpose required")

    private = observed["private"]
    require(private["schema_version"] == "anvil.physical-private-scoring-controls.v1" and len(private["cases"]) == 6,
        "Actual six-case private queue/executor evidence required")
    expected = {"exact": "pass", "near": "partial", "wrong": "fail", "missing": "unscored", "boolean": "unscored", "exception": "error"}
    require({item["control_case"]: item["observed_status"] for item in private["cases"]} == expected, "Reviewed arithmetic outcomes required")
    require(len({item["job_id"] for item in private["cases"]}) == 6 and all(item["status"] == "passed"
        and item["qualification_granted"] is False and item["review_sha256"] == "186be4ec9729428b91ad95fb7c85562167643bd09822db9845d46b07d3333c20"
        for item in private["cases"]), "Independent technical fixture review and distinct actual jobs required")

    def controls(name, schema):
        wrapper = observed[name]
        require(wrapper["schema_version"] == "anvil.installed-qualification-control-execution.v1" and wrapper["kind"] == name,
            "Actual installed operator execution required")
        packet = wrapper["packet"]
        require(packet["schema_version"] == schema and packet["controls"]
            and all(item["status"] == "passed" for item in packet["controls"].values()), "Incomplete actual controls refused")
        measured_source = packet.get("golden_source_sha256", packet.get("source_sha256"))
        require(measured_source == release["source_sha256"], "Actual installed control source mismatch")
        if name in {"sql", "registry"}:
            require(packet["runtime_image_sha256"] == os.environ["ANVIL_RUNTIME_IMAGE_DIGEST"], "Actual installed control image mismatch")
        script = {"sql": "kyc_sql_component_controls.py", "registry": "kyc_policy_registry_controls.py", "components": "component_controls.py"}[name]
        expected_script = release["operational_files"]["runtime-checks/" + script]
        measured_script = packet.get("script_sha256", packet.get("source_hashes", {}).get("script_sha256"))
        require(measured_script == expected_script, "Exact reviewed installed control script required")
        if name == "registry":
            require(packet["helper_sha256"] == release["operational_files"]["runtime-checks/kyc_policy_registry_fixture.py"], "Exact registry helper required")
        if name == "components":
            import importlib

            for module_name in ("anvil.golden_mcp_client", "anvil.golden_mcp_server", "anvil.policy_rules"):
                module = importlib.import_module(module_name)
                require(packet["source_hashes"][module_name] == sha(Path(module.__file__).read_bytes()), "Actual installed component module differs")
        for item in packet["controls"].values():
            if "observation_sha256" in item:
                require(digest(item["observation"]) == item["observation_sha256"], "Raw control observation changed")
        return packet["controls"]

    sql = controls("sql", "anvil.synthetic-sql-component-observations.v2")
    require(sql["restricted_logins_private_and_project_isolation"]["observation"] == {
        "actual_disjoint_login_private_select_denials": 4, "foreign_project_rows": 0}, "Actual SQL isolation denials required")
    mcp = sql["actual_openenv_mcp_sql_reset"]["observation"]
    require(mcp["stale_sql_token"] == "denied" and mcp["reset_generation"] > 0
        and mcp["transport"]["sdk_version"] == "1.30.0" and mcp["transport"]["provider_credentials_to_server"] is False
        and mcp["transport"]["database_credentials_to_server"] is False, "Actual authenticated MCP/OpenEnv reset required")
    product = sql["actual_four_product_registration_conservation_bindings"]["observation"]
    require(product["synthetic_rows"] == 200 and product["products"] == 4 and product["one_exact_assignment_per_row"] is True
        and product["shared_evaluator_configurations"] == 50 and product["rubric_criteria_per_task"] == 20
        and product["wrong_assignment_foreign_project_revocation"] == "denied", "Actual conservation/shared bindings required")
    require(sql["actual_sql_checkpoint_interruption_no_replay"]["observation"] == {
        "committed_before_effect": True, "fresh_saver_replay_denied": True, "synthetic_effect_count": 1}, "Actual durable no-replay control required")
    registry = controls("registry", "anvil.synthetic-policy-registry-observations.v1")
    matrix = registry["twenty_product_state_software_candidates"]["observation"]
    require(matrix["manufactured_prerequisites"] is True and matrix["actual_legal_review"] is False,
        "Synthetic prerequisites cannot become real policy approval")
    require(len(matrix["cells"]) == 20 and len({item["qualification_record_ids"][0] for item in matrix["cells"]}) == 20
        and {(item["product"], item["state"]) for item in matrix["cells"]} == {
        (product, state) for product in ("individual", "adult_joint", "teen_joint", "custodial") for state in ("CA", "NY", "TX", "FL", "IL")}
        and all(item["run_authority"] == "not_granted" and len(item["qualification_record_ids"]) == len(item["policy_set_sha256s"]) == 1
        for item in matrix["cells"]), "Exact twenty-cell software selection required")
    components = controls("components", "anvil.synthetic-component-controls.v1")
    for key in ("opa_pass_fail_missing", "zen_pass_fail_missing"):
        require(components[key]["observation"]["outcomes"] == ["pass", "fail", "unknown"], "Actual policy engine outcomes required")

    roles = observed["role_isolation"]
    require(roles["schema_version"] == "anvil.actual-role-isolation-review.v1" and roles["source_sha256"] == release["source_sha256"]
        and roles["runtime_image"] == release["images"]["kyc-runtime"] and roles["verified"] is True,
        "Independent raw role/SQL/executor cross-check required")
    require(roles["related_files"] and all(re.fullmatch("[a-f0-9]{64}", value) for value in roles["related_files"].values()),
        "Actual role inspection artifacts required")
    related = {}
    for name, expected_sha in roles["related_files"].items():
        path = root / name
        require(".." not in Path(name).parts and path.is_relative_to(root), "Related evidence escaped curated bundle")
        raw = owned(path)
        require(sha(raw) == expected_sha, "Related actual role evidence changed")
        related[name] = json.loads(raw)
    runtime_image = related[roles["runtime_image_inspect"]]
    require(release["images"]["kyc-runtime"] in runtime_image["RepoDigests"]
        and runtime_image["Config"]["Labels"]["org.opencontainers.image.revision"] == release["revision"], "Actual immutable runtime image inspection required")
    runtime_env = environment(runtime_image["Config"]["Env"])
    common_env = {"ANVIL_ENV": "local", "WEB_ORIGIN": "http://127.0.0.1:3202",
        "ANVIL_LIVE_PROVIDERS_ENABLED": "false", "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED": "false", "ANVIL_REAL_EMAIL_ENABLED": "false"}
    for name in ("sql", "registry", "components"):
        refs = roles["installed_controls"][name]
        info = related[refs["inspect"]]
        require(info["Config"]["Image"] == release["images"]["kyc-runtime"] and info["Image"] == runtime_image["Id"]
            and info["State"]["ExitCode"] == 0 and not info["State"]["Running"] and info["RestartCount"] == 0
            and info["HostConfig"]["NetworkMode"] == "none" and info["HostConfig"]["ReadonlyRootfs"], "Actual exact installed control execution required")
        from anvil.golden_native_peer import capabilities

        host, config = info["HostConfig"], info["Config"]
        match = re.fullmatch("/forge-qualification-" + name + r"-([a-f0-9]{8})-runtime", info["Name"])
        require(match is not None, "Exact isolated control identity required")
        fixture_root = Path("/var/lib/anvil-qa-v1/runtime-functional") / ("qualification-" + name + "-" + match[1])
        expected_mounts = {"/controls": (roles["installed_control_bundles"][name] + "/runtime-checks", False)}
        arguments = ["-I", "-B", "/controls/" + {"sql": "kyc_sql_component_controls.py", "registry": "kyc_policy_registry_controls.py", "components": "component_controls.py"}[name]]
        if name != "components":
            expected_mounts.update({str(fixture_root / part): (str(fixture_root / part), False) for part in ("socket", "control")})
            configuration = fixture_root / "control/control.json"
            if name == "registry":
                expected_mounts[str(fixture_root / "owner")] = (str(fixture_root / "owner"), False)
                configuration = fixture_root / "owner/registry-driver.json"
            arguments += ["--config", str(configuration)]
        require(mounts(info) == expected_mounts and info["Path"] == "/opt/anvil-runtime/bin/python" and info["Args"] == arguments,
            "Installed control command or credential mount exposure changed")
        require(config["User"] == ("10001:10001" if name == "components" else "0:0")
            and capabilities(host.get("CapDrop") or []) == {"ALL"} and not host.get("CapAdd") and not host["Privileged"]
            and host.get("PidMode", "") == "" and host.get("UTSMode", "") == ""
            and "no-new-privileges" in host["SecurityOpt"] and host["Memory"] == 1610612736
            and host["PidsLimit"] == 128 and host["NanoCpus"] == 2000000000
            and set(host.get("Tmpfs") or {}) == {"/tmp"}
            and not info["State"].get("OOMKilled") and not info["State"].get("Error") and info["State"]["Pid"] == 0
            and config["Labels"]["io.adi.forge.scope"] == "isolated-qualification-controls",
            "Installed control role privilege/resource boundary changed")
        require(environment(config["Env"]) == runtime_env | common_env | {"ANVIL_RUNTIME_IMAGE_DIGEST": os.environ["ANVIL_RUNTIME_IMAGE_DIGEST"]},
            "Installed control received unreviewed environment credentials")
        scripts = {"runtime-checks/" + {"sql": "kyc_sql_component_controls.py", "registry": "kyc_policy_registry_controls.py", "components": "component_controls.py"}[name]}
        if name != "components":
            scripts.add("runtime-checks/kyc_sql_fixture_setup.py")
        if name == "registry":
            scripts.add("runtime-checks/kyc_policy_registry_fixture.py")
        require(set(roles["installed_control_sources"][name]) == scripts, "Complete original control source inventory required")
        for relative, source_ref in roles["installed_control_sources"][name].items():
            require(source_ref.startswith("control-sources/") and ".." not in Path(source_ref).parts
                and sha(owned(root / source_ref)) == (release["control_files"] | release["operational_files"])[relative],
                "Actual mounted control source bytes changed")
        stdout = owned(root / refs["stdout"])
        require(sha(stdout) == observed[name]["packet_stdout_sha256"] and json.loads(stdout) == observed[name]["packet"], "Control output does not match retained actual stdout")
    from anvil.custom_python_executor import source_hash as executor_source
    from anvil.custom_python_grading import source_hash as grading_source

    require(set(roles["private_jobs"]) == {item["job_id"] for item in private["cases"]}, "Exact private job evidence crosslinks required")
    audit = private["sql_audit"]
    require(set(audit["production_qualification_rows"]) == {"project_binding_qualifications", "praxis_template_qualifications", "praxis_template_publications"}
        and audit["schema_version"] == "anvil.private-scoring-readonly-sql-audit.v1" and audit["read_only"] is True
        and not any(audit["production_qualification_rows"].values()), "Actual read-only terminal SQL audit required")
    sql_jobs = {item["id"]: item for item in audit["jobs"]}
    require(len(audit["jobs"]) == len(sql_jobs) == 6 and set(sql_jobs) == set(roles["private_jobs"]), "SQL/private job identities differ")
    for case in private["cases"]:
        refs = roles["private_jobs"][case["job_id"]]
        request, result = related[refs["request"]], related[refs["result"]]
        sql_job = sql_jobs[case["job_id"]]
        require(sql_job["state"] == ("error" if case["observed_status"] == "error" else "completed")
            and sql_job["request_schema"] == sql_job["result_schema"] == "anvil.private-python-control-grade.v1", "Exact terminal technical SQL purpose required")
        require(digest(request["request"]) == request["request_sha256"] == case["request_sha256"] == sql_jobs[case["job_id"]]["request_sha256"],
            "Actual private request/SQL hashes differ")
        require(digest(result["result"]) == result["result_sha256"] == case["result_sha256"] == sql_jobs[case["job_id"]]["result_sha256"],
            "Actual private result/SQL hashes differ")
        require(request["request"]["schema_version"] == result["result"]["schema_version"] == "anvil.private-python-control-grade.v1"
            and result["result"]["status"] == case["observed_status"] == sql_jobs[case["job_id"]]["result_status"]
            and request["request"]["source_sha256"] == result["result"]["source_sha256"] == grading_source(), "Current disjoint scoring purpose/source required")
        execution = result["result"]["execution_observation"]
        executor_ref = roles["containers"]["executor-" + case["control_case"]]
        executor_info = related[executor_ref]
        require(executor_info["Name"].removeprefix("/") == case["executor_container"] == execution["container_name"], "Actual executor inspect must belong to this exact scoring case")
        require(digest(execution) == result["result"]["execution_sha256"] == case["execution_sha256"]
            and execution["source_sha256"] == executor_source() and execution["container_retained_stopped"] is True
            and execution["network"] == "none" and execution["readonly_root"] is True
            and execution["cases"][0]["actual_status"] == case["observed_status"], "Actual isolated executor outcome required")
        require(sha(request["request"]["code"].encode()) == "7e0785d67fab37b8e1c7d339000cd3190b667961cbd2af2a79712fdb02780dc7", "Exact independently reviewed code required")
        if case["control_case"] == "exception":
            require((execution["cases"][0].get("error_type"), execution["cases"][0].get("line")) == ("ValueError", 14), "Infrastructure errors cannot pass the exception control")
    require(set(roles["containers"]) == {"worker", "sdk", "native_sdk", "actor", "verifier"}
        | {"executor-" + name for name in expected} | {"grader-" + name for name in expected}
        | {"private_coordinator-" + name for name in expected},
        "Every actual isolated role inspection required")
    from anvil.native_image_profile import IMAGE, IMAGE_ID

    for role, path in roles["containers"].items():
        require(path in related, "Unhashed role inspection refused")
        info = related[path]
        host, config = info["HostConfig"], info["Config"]
        stopped_service = role in {"actor", "verifier"}
        require(not info["State"]["Running"] and info["State"]["ExitCode"] in ({0, 137, 143} if stopped_service else {0})
            and not info["State"].get("OOMKilled") and not info["State"].get("Dead") and not info["State"].get("Error")
            and info["State"]["Pid"] == 0 and info["RestartCount"] == 0
            and host["NetworkMode"] == "none" and host["ReadonlyRootfs"] and not host["Privileged"]
            and "no-new-privileges" in host["SecurityOpt"], "Actual terminal isolated role required")
        if role in {"sdk", "native_sdk"} or role.startswith("private_coordinator-"):
            require(config["User"] == "0:0", "Trusted coordinator root identity required")
        else:
            require(config["User"] == "10001:10001" and not host.get("CapAdd") and set(host["CapDrop"]) == {"ALL"},
                "Unprivileged worker/grader/actor/executor required")
        if role in {"sdk", "native_sdk", "worker"} or role.startswith(("grader-", "private_coordinator-")):
            require(config["Image"] == release["images"]["kyc-runtime"]
                and info["Image"] == runtime_image["Id"]
                and config["Labels"]["org.opencontainers.image.revision"] == release["revision"], "Exact actual role image required")
            overrides = dict(common_env)
            if role != "native_sdk":
                overrides["ANVIL_RUNTIME_IMAGE_DIGEST"] = os.environ["ANVIL_RUNTIME_IMAGE_DIGEST"]
            if role == "sdk":
                base = "/var/lib/anvil-qa-v1/runtime-functional"
                overrides.update(ANVIL_GOLDEN_NATIVE_COORDINATOR_ENABLED="true", ANVIL_NATIVE_BRIDGE_ROOT=base + "/native-control-bridge",
                    ANVIL_GOLDEN_NATIVE_WORK_ROOT=base + "/harbor-proof/native-control-work", ANVIL_HARBOR_DOCKER_HOST="unix:///run/docker.sock",
                    ANVIL_HARBOR_PYTHON="/opt/anvil-runtime/bin/python")
            require(environment(config["Env"]) == runtime_env | overrides, "Actual runtime role has unreviewed environment variables")
        else:
            require(config["Image"] == IMAGE and info["Image"] == IMAGE_ID, "Exact actual isolated fixture image required")
        destinations = {mount["Destination"] for mount in info["Mounts"]}
        if role in {"worker", "actor", "verifier"} or role.startswith("grader-"):
            require("/run/docker.sock" not in destinations and "/var/run/docker.sock" not in destinations, "Docker reached unprivileged role")
        if role == "worker":
            bridge = "/var/lib/anvil-qa-v1/runtime-functional/native-control-bridge"
            require(host.get("PidMode", "") == "" and mounts(info) == {bridge: (bridge, True)}, "Actual private-PID fixed control worker required")
            require(info["Name"].removeprefix("/") == next(item["container"] for item in transport["network_observations"] if item["role"] == "worker"), "Worker observation identity mismatch")
        if role.startswith(("grader-", "private_coordinator-")):
            from anvil.golden_native_peer import capabilities

            case_name = role.split("-", 1)[1]
            case = next(item for item in private["cases"] if item["control_case"] == case_name)
            # The audit job request path is under this exact one-shot fixture.
            fixture = Path(roles["private_fixture_root"])
            require(re.fullmatch(r"/var/lib/anvil-qa-v1/runtime-functional/private-score-[a-f0-9]{8}", str(fixture)), "Exact fresh private fixture root required")
            bundle = str(Path(roles["control_bundle"]) / "runtime-checks")
            binds = {"/controls": (bundle, False), str(fixture / "bridge"): (str(fixture / "bridge"), True)}
            coordinator = role.startswith("private_coordinator-")
            if coordinator:
                binds.update({"/run/docker.sock": ("/run/docker.sock", False), "/usr/bin/docker": ("/usr/bin/docker", False)})
            else:
                binds.update({str(fixture / name): (str(fixture / name), False) for name in ("socket", "grader")})
            require(mounts(info) == binds and host.get("PidMode", "") == ""
                and capabilities(host.get("CapDrop") or []) == {"ALL"}
                and capabilities(host.get("CapAdd") or []) == ({"CHOWN", "DAC_OVERRIDE"} if coordinator else set()), "Exact private coordinator/grader mount and capability boundary required")
            index = next(index for index, item in enumerate(private["cases"]) if item["job_id"] == case["job_id"])
            require(info["Name"].removeprefix("/") == "forge-private-" + fixture.name.removeprefix("private-score-") + ("-coordinator-" if coordinator else "-grader-") + str(index), "Private role belongs to another case")
        if role.startswith("executor-"):
            require(not info["Mounts"] and host["Memory"] == host["MemorySwap"] == 134217728
                and host["PidsLimit"] == 32 and host["NanoCpus"] == 500000000, "Actual secret-free bounded executor required")
    native_plan_ref = roles["native_plan"]
    native_host_ref = roles["native_host_custody"]
    require(native_plan_ref in related and native_host_ref in related, "Actual original native plan/assets required")
    plan, native_host = related[native_plan_ref], related[native_host_ref]
    require(related[roles["native_cleanup"]] == {"complete": True, "failures": [], "retained": True}, "Actual owned native actor/verifier stop receipt required")
    require(plan["schema_version"] == "anvil.kyc-technical-probe-plan.v1" and plan["authorization_scope"] == "fixed_two_read_software_control_only"
        and roles["related_files"][native_plan_ref] == native["plan_sha256"] and plan["job_id"] == native["job_id"]
        and plan["asset_sha256s"]["host_image_custody"] == roles["related_files"][native_host_ref]
        and native_host["sdk_profile"]["image"] == release["images"]["kyc-runtime"], "Actual native source/image custody required")
    from anvil import environment_harbor as native_module
    from anvil.config import ROOT
    from anvil.qualification_resources import qualification_path

    proof_module = native_module.operator_proof_module()
    require(set(plan["dependency_source_sha256s"]) == proof_module.REQUIRED_DEPENDENCIES | {
        "services/harbor/src/anvil_harbor/operator_proof.py", "services/backend/src/anvil/golden_kyc_probe_prepare.py"}, "Exact complete original native dependency closure required")
    for name, expected_sha in plan["dependency_source_sha256s"].items():
        require(sha(qualification_path(ROOT, name).read_bytes()) == expected_sha, "Native packet belongs to another installed source")
    require(set(roles["native_assets"]) == set(plan["asset_sha256s"]), "Every original source-bound native asset required")
    assets = {}
    for name, ref in roles["native_assets"].items():
        require(roles["related_files"][ref] == plan["asset_sha256s"][name], "Native asset byte identity mismatch")
        assets[name] = related[ref]
    require(assets["host_image_custody"] == native_host, "Native host asset crosslink mismatch")
    store = proof_module.TechnicalProbeStore(ROOT)
    store.validate_runtime_seal(assets["runtime_seal"])
    require(plan["limits"] == store.LIMITS, "Original bounded native limits required")
    folder = Path(native_host["folder"])
    projection = native_module.layout_projection(folder, plan["request_capsule"]["actor"], actor_seconds=store.LIMITS["wall_seconds"])
    require(assets["task_package"] == {"schema_version": "anvil.fixed-native-task.v1", "files": {
        key: sha(value.encode()) for key, value in projection.items()}}, "Exact native task package source projection required")
    actor_info = related[roles["containers"]["actor"]]
    verifier_info = related[roles["containers"]["verifier"]]
    fixture_image = related[roles["fixture_image_inspect"]]
    require(fixture_image["Id"] == IMAGE_ID and IMAGE in fixture_image["RepoDigests"], "Actual isolated fixture image required")
    baseline = environment(fixture_image["Config"]["Env"])
    for role, info in (("environment", actor_info), ("tests", verifier_info)):
        service = assets[role + "_service"]
        require(sha(json.dumps(service, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()) == plan["service_projection_sha256s"][role], "Exact native service byte projection required")
        expected_mounts = {item["target"]: (item["source"], not item.get("read_only", False)) for item in service["volumes"]}
        require(mounts(info) == expected_mounts, "Actual actor/verifier mounts differ from source-bound native service")
        effective_env = dict(baseline)
        for key, value in service.get("environment", {}).items():
            if value is None:
                effective_env.pop(key, None)
            else:
                effective_env[key] = str(value)
        require(environment(info["Config"]["Env"]) == effective_env, "Unreviewed actor/verifier environment variable")
        require(info["HostConfig"].get("PidMode", "") == "" and info["HostConfig"]["Memory"] == info["HostConfig"]["MemorySwap"] == 536870912
            and info["HostConfig"]["NanoCpus"] == 1000000000 and info["HostConfig"]["PidsLimit"] == 64,
            "Actual actor/verifier resource and PID boundary required")
        require(info["Config"]["Labels"]["com.docker.compose.project"] == "anvil-bm-" + plan["operation_nonce"][:20] + ("__env" if role == "environment" else "__verifier__trial"), "Actor/verifier belongs to another native Trial")
    native_sdk = related[roles["containers"]["native_sdk"]]
    require(static_sdk_profile(native_sdk, {"SYS_PTRACE"}) == native_host["sdk_profile"], "Native SDK profile differs from actual retained container")
    from anvil.golden_native_peer import validate_control_mounts

    validate_control_mounts(native_host["sdk_profile"], proof_root=proof_module.ROOT, provider_path=native_host["database_provider"]["path"], docker="/usr/bin/docker", compose="/usr/libexec/docker/cli-plugins/docker-compose")
    for index, peer_ref in enumerate(roles["native_peers"]):
        peer = related[peer_ref]
        original_process = related[roles["native_framework_process"]]
        require(peer["schema_version"] == "anvil.owned-sdk-peer-observation.v1" and peer["job_id"] == native["job_id"]
            and peer["uid"] == peer["gid"] == 0 and peer["entry"] == index
            and peer["purpose"] == "technical_control_only" and peer["image"] == release["images"]["kyc-runtime"]
            and peer["container_id"] == native_sdk["Id"] and peer["pid"] == original_process["pid"]
            and peer["identity"] == original_process["identity"] and original_process["host_domain"] == plan["host_domain"],
            "Actual retained original native SDK peer required")
    require(len(roles["native_peers"]) == 2, "Both actual SDK actor/verifier peer entries required")
    networks = transport["network_observations"]
    require(len(networks) == 2 and {item["role"] for item in networks} == {"worker", "sdk"}, "Both original process-tree observations required")
    for item in networks:
        filtered = item.get("observer_mode") == "pinned_launch_seccomp"
        if filtered:
            require(item["role"] == "sdk" and item["observed_from_pre_entry_pause"] is False
                and item["observed_before_application_exec"] is True and item["observer_exit_code"] is None
                and item["observer_completion"] == "original_sdk_and_tracer_pidfds_exited_all_tracees_terminal"
                and item["seccomp_filters"] >= 2 and item["tracer_pid"] > 1 and item["observer_stderr_clean"] is True,
                "Complete original kernel-filtered SDK trace required")
        else:
            require(item["observed_from_pre_entry_pause"] is True and item["observer_exit_code"] == 0, "Complete original attached process trace required")
        require(
            item["scope"] == "transport_worker_and_sdk_descendants" and item["internet_connect_events"] == 0
            and item["unix_connect_events"] > 0 and item["unknown_unix_peers"] == 0
            and item["global_actual_model_calls"] is None and item["traces"], "Positive independent scoped network evidence required")
        import importlib.util

        observer_path = Path("/controls/network_observer.py")
        require(sha(owned(observer_path)) == release["operational_files"]["runtime-checks/network_observer.py"], "Exact observer classifier required")
        spec = importlib.util.spec_from_file_location("qa_network_observer", observer_path)
        observer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(observer)

        require(item["observer_binary_sha256"] == observer.BINARY_SHA256 and item["observer_source_sha256"] == release["operational_files"]["runtime-checks/network_observer.py"], "Exact independently reviewed observer required")
        require(item["role"] + ".syscalls." + str(item["host_pid"]) in item["traces"], "Original observed root process trace required")
        trace_bytes = b""
        for filename, expected_sha in item["traces"].items():
            require(Path(filename).name == filename and re.fullmatch(r"(?:sdk|worker)\.syscalls\.[0-9]+", filename), "Exact original trace member required")
            raw = owned(root / "traces" / filename, limit=16*1024**2)
            require(sha(raw) == expected_sha, "Actual kernel trace changed")
            observer.complete_trace(raw)
            trace_bytes += raw
            require(len(trace_bytes) <= 16*1024**2, "Bounded kernel trace required")
        counters = observer.classify(trace_bytes, Path("/var/lib/anvil-qa-v1/runtime-functional/native-control-bridge"))
        require(all(item[key] == value for key, value in counters.items()), "Original trace counters differ")
    profile = observed["sdk_profile"]
    require(profile["image"] == release["images"]["kyc-runtime"] and profile["capabilities"] == ["CHOWN", "DAC_OVERRIDE", "SYS_PTRACE"]
        and len(profile["mounts"]) == 6, "Exact tested mediated SDK profile required")
    sdk_info = related[roles["containers"]["sdk"]]
    require(static_sdk_profile(sdk_info, {"CHOWN", "DAC_OVERRIDE", "SYS_PTRACE"}) == profile, "Mediated SDK profile differs from actual retained container")
    require(sdk_info["Name"].removeprefix("/") == next(item["container"] for item in networks if item["role"] == "sdk"), "SDK observation identity mismatch")
    from anvil.golden_native_mediated import validate_transport_profile

    bridge = Path("/var/lib/anvil-qa-v1/runtime-functional/native-control-bridge")
    validate_transport_profile(profile, proof_module.ROOT / "native-control-work", {"gateway_socket": str(bridge / ".bm-gw-evidence/gateway.sock")})

    review = observed["review"]
    require(review["schema_version"] == "anvil.independent-component-evidence-review.v1" and review["origin"] == "independent_agent_read_only_review"
        and review["scope"] == "synthetic_nonspending_components_only" and review["findings"] == []
        and review["source_sha256"] == release["source_sha256"] and review["runtime_image"] == release["images"]["kyc-runtime"]
        and review["human_legal_rights_approval"] is False and review["raw_packet_sha256s"] == {k: v for k, v in raw_hashes.items() if k != "review"},
        "Actual independent complete evidence review required")
    expiry = datetime.fromisoformat(review["expires_at"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    require(expiry.tzinfo is not None and now < expiry <= min(now + timedelta(days=7), proof_module.STOP), "Current bounded independent review required")
    from anvil.golden_component_qualification import CHECKS

    mapping = {"actual_harbor_trial": "native", "openenv_sql_isolation": "sql", "actual_mcp_auth_schema_reset": "sql",
        "durable_checkpoint_recovery": "sql", "actor_grader_isolation": "role_isolation", "role_mount_isolation": "role_isolation",
        "opa_allow_deny_controls": "components", "zen_positive_negative_missing_controls": "components",
        "private_python_scoring_controls": "private", "no_model_requests": "transport",
        "kyc_product_routing": "sql", "all_original_rows_conserved": "sql", "per_application_policy_registry": "registry", "shared_task_evaluator_binding": "sql"}
    require(set(CHECKS) <= set(mapping), "Every required control must have concrete evidence")
    receipt = {"schema_version": "anvil.golden-component-installed-qualification.v1", "origin": "independent_qa", "qualified": True,
        "scope": "technical_components_only", "spending_authority": False, "expires_at": expiry.isoformat(),
        "golden_source_sha256": source_hash(), "broker_source_sha256": code_digest(), "runtime_image_sha256": os.environ["ANVIL_RUNTIME_IMAGE_DIGEST"],
        "review_receipt_sha256": raw_hashes["review"], "mediated_sdk_profile_sha256": digest(profile),
        "checks": {name: {"status": "passed", "evidence_sha256": raw_hashes[source]} for name, source in mapping.items()},
        "model_performance": False, "human_legal_rights_approval": False, "global_actual_model_calls": None,
        "no_model_observation_scope": "transport_worker_and_sdk_descendants"}
    for name, version in (("openenv_version", "openenv"), ("harbor_version", "harbor"), ("mcp_sdk_version", "mcp")):
        receipt[name] = metadata.version(version)
    expected = Path("/var/lib/anvil-qa-v1/runtime-functional/harbor-proof/component-qualification/current.json")
    require(output_path == expected and output_path.parent.stat().st_uid == 0 and not output_path.parent.stat().st_mode & 0o022,
        "Only the fixed root-controlled QA receipt destination is permitted")
    raw = rfc8785.dumps(receipt)
    if verify_only:
        print(json.dumps({"status": "verified_not_published", "receipt_sha256": sha(raw), "spending_authority": False}))
        return
    temporary = output_path.with_name("pending-" + sha(raw) + ".json")
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644), "wb") as stream:
        os.fchmod(stream.fileno(), 0o644)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    if output_path.exists():
        require(owned(output_path) == raw, "Existing receipt differs; explicit reconciliation required")
        temporary.unlink()
    else:
        os.link(temporary, output_path, follow_symlinks=False)
        temporary.unlink()
    directory = os.open(output_path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    print(json.dumps({"status": "technical_components_qualified_not_spend_authorized", "receipt_sha256": sha(raw), "spending_authority": False}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    main(args.input, args.output, verify_only=args.verify_only)
