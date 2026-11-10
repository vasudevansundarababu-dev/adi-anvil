"""Exact approved overnight QA host creation with append-only public receipts.

No production mutation, provider credential handling or application deployment.
Existing names are refused; failed/uncertain creates must be reconciled manually.
"""

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from overnight_qa_lifecycle import NAME, PROJECT, STOP, validate_vm

CLI = "/Users/vasudevansundarababu/Documents/Codex/anvil-tools/google-cloud-sdk/bin/gcloud"
CONFIG = "/Users/vasudevansundarababu/Documents/Codex/anvil-tools/cloud-config"


def call(args):
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(Path.home()),
        "CLOUDSDK_CONFIG": CONFIG,
        "CLOUDSDK_CORE_DISABLE_USAGE_REPORTING": "true",
        "CLOUDSDK_PYTHON": "/private/tmp/anvil-evaluators-20261109-venv/bin/python",
    }
    completed = subprocess.run(
        [
            CLI,
            "--project=" + PROJECT,
            "--account=vasudevan.sundarababu@adi-labs.ai",
            "--quiet",
            *args,
        ],
        env=env,
        capture_output=True,
        timeout=180,
    )
    if completed.returncode:
        raise RuntimeError(
            "GCP operation failed: "
            + " ".join(args[:4])
            + ": "
            + completed.stderr.decode(errors="replace")[-2000:]
        )
    return json.loads(completed.stdout) if completed.stdout.strip() else None


def resources():
    return [
        ("network", ["compute", "networks"], NAME + "-net", []),
        ("subnet", ["compute", "networks", "subnets"], NAME + "-subnet", ["--region=us-west1"]),
        ("router", ["compute", "routers"], NAME + "-router", ["--region=us-west1"]),
        ("firewall", ["compute", "firewall-rules"], NAME + "-iap", []),
        ("vm", ["compute", "instances"], NAME, ["--zone=us-west1-a"]),
    ]


def create_commands(public_key_file):
    return [
        ["compute", "networks", "create", NAME + "-net", "--subnet-mode=custom"],
        [
            "compute",
            "networks",
            "subnets",
            "create",
            NAME + "-subnet",
            "--network=" + NAME + "-net",
            "--range=10.198.40.0/24",
            "--region=us-west1",
            "--enable-private-ip-google-access",
        ],
        [
            "compute",
            "routers",
            "create",
            NAME + "-router",
            "--network=" + NAME + "-net",
            "--region=us-west1",
        ],
        [
            "compute",
            "routers",
            "nats",
            "create",
            NAME + "-nat",
            "--router=" + NAME + "-router",
            "--region=us-west1",
            "--nat-custom-subnet-ip-ranges=" + NAME + "-subnet",
            "--auto-allocate-nat-external-ips",
        ],
        [
            "compute",
            "firewall-rules",
            "create",
            NAME + "-iap",
            "--network=" + NAME + "-net",
            "--direction=INGRESS",
            "--allow=tcp:22",
            "--source-ranges=35.235.240.0/20",
            "--target-tags=" + NAME,
        ],
        [
            "compute",
            "instances",
            "create",
            NAME,
            "--zone=us-west1-a",
            "--machine-type=e2-standard-8",
            "--subnet=" + NAME + "-subnet",
            "--no-address",
            "--no-service-account",
            "--no-scopes",
            "--create-disk=name="
            + NAME
            + "-boot,boot=yes,auto-delete=yes,size=150GB,type=pd-standard,image=debian-12-bookworm-v20261109,image-project=debian-cloud",
            "--no-restart-on-failure",
            "--instance-termination-action=STOP",
            "--termination-time=2026-11-10T18:00:00Z",
            "--metadata=block-project-ssh-keys=TRUE,enable-oslogin=TRUE",
            "--tags=" + NAME,
            "--labels=application=anvil,purpose=overnight-qa,expiry=2026-11-10",
        ],
    ]


def provision(root):
    if datetime.now(timezone.utc) >= STOP:
        raise ValueError("Approved execution window expired")
    root = Path(root)
    if not root.is_absolute() or root.exists():
        raise ValueError("Fresh private QA operator root required")
    root.mkdir(mode=0o700)
    ledger = root / "resources.jsonl"
    # Fresh project-wide name inventory excludes all existing production resources.
    for kind, command, name, scope in resources():
        existing = call(command + ["list", "--filter=name=" + name, "--format=json(name,id)"])
        if existing:
            raise ValueError("Existing QA name refused: " + name)
    key = root / "operator-key"
    subprocess.run(
        [
            "/usr/bin/ssh-keygen",
            "-t",
            "ed25519",
            "-N",
            "",
            "-C",
            "anvil-overnight-qa",
            "-f",
            str(key),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    public = root / "instance-ssh-public-key"
    public.write_text("anvilqa:" + key.with_suffix(".pub").read_text().strip() + "\n")
    commands = create_commands(public)
    with ledger.open("x") as receipts:
        os.chmod(ledger, 0o600)
        for index, command in enumerate(commands):
            receipts.write(
                json.dumps({"stage": "before_create", "index": index, "command": command}) + "\n"
            )
            receipts.flush()
            os.fsync(receipts.fileno())
            call(command + ["--format=json"])
            if index == 3:
                descriptor = resources()[2]
            else:
                descriptor = resources()[index if index < 3 else index - 1]
            kind, prefix, name, scope = descriptor
            readback = call(prefix + ["describe", name, *scope, "--format=json"])
            receipts.write(
                json.dumps({"stage": "readback", "kind": kind, "resource": readback}) + "\n"
            )
            receipts.flush()
            os.fsync(receipts.fileno())
            if kind == "vm":
                proof = validate_vm(readback, now=datetime.now(timezone.utc))
                disk = call(
                    [
                        "compute",
                        "disks",
                        "describe",
                        NAME + "-boot",
                        "--zone=us-west1-a",
                        "--format=json",
                    ]
                )
                if str(disk.get("sizeGb")) != "150":
                    raise ValueError("Unexpected QA disk size")
                receipts.write(
                    json.dumps({"stage": "readback", "kind": "disk", "resource": disk}) + "\n"
                )
                receipts.flush()
                os.fsync(receipts.fileno())
                (root / "public.json").write_text(
                    json.dumps(
                        {
                            **proof,
                            "root": str(root),
                            "application_deployed": False,
                            "provider_calls": 0,
                        }
                    )
                )
    return proof
