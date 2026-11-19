"""Pure QA service wiring: separate actor and private-scoring coordinators.

No credentials, activation, deployment, approval or qualification producer.
The operator creates and verifies host directories before using this result.
"""

import copy

BASE = "/var/lib/anvil-qa-v1/runtime-functional"
PROOF = BASE + "/harbor-proof"
BRIDGE = BASE + "/native-control-bridge"
PRIVATE = BASE + "/private-grading-bridge"
QUALIFICATION = PROOF + "/component-qualification"
NATIVE_QUALIFICATION = "/opt/anvil-runtime-source/.data/component-qualification"


def mount(source, target=None, readonly=False):
    return {"type": "bind", "source": source, "target": target or source, "read_only": readonly}


def append_mount(service, value):
    volumes = service.setdefault("volumes", [])
    for item in volumes:
        target = item.get("target") if isinstance(item, dict) else item.split(":")[1] if isinstance(item, str) and ":" in item else None
        if target is None or target == value["target"]:
            raise ValueError("Existing runtime mount requires explicit reconciliation")
    volumes.append(value)


def apply(config, image, image_digest):
    config = copy.deepcopy(config)
    services = config["services"]
    for name in ("api", "business-worker", "golden-scheduler", "golden-grader"):
        service = services[name]
        environment = service.setdefault("environment", {})
        if any(environment.get(key, "false") != "false" for key in (
            "ANVIL_LIVE_PROVIDERS_ENABLED", "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED", "ANVIL_PRAXIS_TEMPLATE_CALLS_ENABLED")):
            raise ValueError("Wiring does not authorize live activation")
        destination = NATIVE_QUALIFICATION if name.startswith("golden-") else "/app/.data/component-qualification"
        environment["ANVIL_GOLDEN_COMPONENT_QUALIFICATION_FILE"] = destination + "/current.json"
        append_mount(service, mount(QUALIFICATION, destination, True))
    scheduler = services["golden-scheduler"]
    scheduler["environment"]["ANVIL_NATIVE_BRIDGE_ROOT"] = BRIDGE
    append_mount(scheduler, mount(BRIDGE))
    grader = services["golden-grader"]
    grader["environment"]["ANVIL_PRIVATE_PYTHON_GRADING_ROOT"] = PRIVATE
    # Execution still requires current SQL qualification/author/revocation gates.
    grader["environment"]["ANVIL_CUSTOM_PYTHON_SCORING_ENABLED"] = "true"
    append_mount(grader, mount(PRIVATE))
    common = {"image": image, "read_only": True, "user": "0:0", "network_mode": "none", "restart": "no",
        "cap_drop": ["ALL"], "security_opt": ["no-new-privileges"], "mem_limit": "1536m", "pids_limit": 256,
        "cpus": 2, "tmpfs": ["/tmp:rw,nosuid,nodev,noexec,size=128m"], "entrypoint": ["/opt/anvil-runtime/bin/python"],
        "environment": {"ANVIL_ENV": "local", "WEB_ORIGIN": "http://127.0.0.1:3202", "ANVIL_RUNTIME_IMAGE_DIGEST": image_digest,
            "ANVIL_LIVE_PROVIDERS_ENABLED": "false", "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED": "false", "ANVIL_REAL_EMAIL_ENABLED": "false"}}
    docker_mounts = [mount("/run/docker.sock", readonly=True), mount("/usr/bin/docker", readonly=True)]
    actor = copy.deepcopy(common)
    actor.update(pid="host", uts="host", userns_mode="host", cgroup="host", cap_add=["SYS_PTRACE", "DAC_OVERRIDE", "CHOWN"],
        security_opt=["no-new-privileges", "apparmor=unconfined"], command=["-I", "-B", "-m", "anvil.golden_native_bridge"])
    actor["environment"].update(ANVIL_GOLDEN_NATIVE_COORDINATOR_ENABLED="true", ANVIL_NATIVE_BRIDGE_ROOT=BRIDGE,
        ANVIL_GOLDEN_NATIVE_WORK_ROOT=PROOF + "/native-control-work", ANVIL_HARBOR_DOCKER_HOST="unix:///run/docker.sock",
        ANVIL_HARBOR_PYTHON="/opt/anvil-runtime/bin/python", ANVIL_GOLDEN_COMPONENT_QUALIFICATION_FILE=NATIVE_QUALIFICATION + "/current.json")
    actor["volumes"] = docker_mounts + [mount("/usr/libexec/docker/cli-plugins/docker-compose", readonly=True),
        mount(PROOF), mount(BRIDGE), mount(QUALIFICATION, NATIVE_QUALIFICATION, True)]
    private = copy.deepcopy(common)
    private["cap_add"] = ["DAC_OVERRIDE", "CHOWN"]
    private["command"] = ["-I", "-B", "-m", "anvil.custom_python_grading", "--coordinator", "--root", PRIVATE]
    private["volumes"] = docker_mounts + [mount(PRIVATE)]
    for name, service in (("native-coordinator", actor), ("private-scoring-coordinator", private)):
        if name in services:
            raise ValueError("Existing coordinator requires reconciliation, never overwrite")
        services[name] = service
    return config
