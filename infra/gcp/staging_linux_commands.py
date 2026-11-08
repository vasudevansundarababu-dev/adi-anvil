"""Print prospective native QA creation argv only; never execute commands.

Review output is available before approval; this module has no executor.
"""
import argparse
import json
import re
from pathlib import Path


def commands(plan):
    b = plan["bindings"]
    for key, size in (("source_sha", 40), ("source_archive_sha256", 64)):
        if b.get(key) is not None and not re.fullmatch(r"[0-9a-f]{%s}" % size, b[key]):
            raise ValueError("Malformed source binding")
    r = plan["resources"]
    project, region, zone = plan["project"], plan["region"], plan["zone"]
    if project != "adi-anvil-mvp-2026" or region != "us-west1" or zone != "us-west1-a" or r["vm"] != "anvil-staging-native":
        raise ValueError("Unapproved target")
    base = ["env", "CLOUDSDK_CONFIG=/Users/vasudevansundarababu/Documents/Codex/anvil-tools/cloud-config", "CLOUDSDK_CORE_DISABLE_USAGE_REPORTING=true", "/Users/vasudevansundarababu/Documents/Codex/anvil-tools/google-cloud-sdk/bin/gcloud", f"--project={project}", "--account=vasudevan.sundarababu@adi-labs.ai"]
    return [
        base + ["compute", "networks", "create", r["network"], "--subnet-mode=custom"],
        base + ["compute", "networks", "subnets", "create", r["subnet"], f"--network={r['network']}", f"--range={r['candidate_subnet_cidr']}", f"--region={region}"],
        base + ["compute", "addresses", "create", r["nat_ip"], f"--region={region}"],
        base + ["compute", "routers", "create", r["router"], f"--network={r['network']}", f"--region={region}"],
        base + ["compute", "routers", "nats", "create", r["nat"], f"--router={r['router']}", f"--region={region}", f"--nat-custom-subnet-ip-ranges={r['subnet']}", f"--nat-external-ip-pool={r['nat_ip']}"],
        base + ["compute", "firewall-rules", "create", r["iap_ssh_firewall"], f"--network={r['network']}", "--direction=INGRESS", "--allow=tcp:22", "--source-ranges=35.235.240.0/20", "--target-tags=anvil-staging-native-iap"],
        base + ["compute", "instances", "create", r["vm"], f"--zone={zone}", "--machine-type=e2-standard-4", f"--subnet={r['subnet']}", "--no-address", "--no-service-account", "--no-scopes", "--create-disk=name=anvil-staging-native-boot,boot=yes,auto-delete=yes,size=30GB,type=pd-balanced,image=debian-12-bookworm-v20261102,image-project=debian-cloud", "--no-restart-on-failure", "--instance-termination-action=STOP", "--termination-time=2026-11-15T19:30:00Z", "--metadata=block-project-ssh-keys=TRUE", "--metadata-from-file=ssh-keys=.local/native-qa/instance-ssh-public-key", "--tags=anvil-staging-native-iap", "--labels=application=anvil,purpose=native-qa,expiry=2026-11-15"],
        base + ["compute", "instances", "describe", r["vm"], f"--zone={zone}", "--format=json(id,disks,networkInterfaces,serviceAccounts,scheduling,metadata)"],
        base + ["compute", "ssh", "anvilqa@anvil-staging-native", f"--zone={zone}", "--tunnel-through-iap", "--ssh-key-file=.local/native-qa/id_ed25519", "--ssh-flag=-oUserKnownHostsFile=.local/native-qa/known_hosts"],
    ]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan", type=Path, default=Path(__file__).with_name("staging-linux-test-host-plan.json"))
    args = p.parse_args()
    try:
        plan = json.loads(args.plan.read_text())
        result = commands(plan)
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"ready": False, "error": "Invalid proposal; no commands executed"}))
        return 2
    blockers = [key for key in ("source_sha", "source_archive_sha256") if not plan["bindings"].get(key)]
    print(json.dumps({"executed": False, "requires_approval": True, "provisioning_ready": False, "unresolved_bindings": blockers, "not_before": "2026-11-08T19:30:00Z", "requires_fresh_inventory_and_review": True, "prospective_argv": result, "setup_review": [
        "Verify exact OS image ID, no cloud serviceAccounts/scopes, private interface and absolute STOP metadata",
        "Create repo-local SSH key/known_hosts only; instance public key metadata only; stop if global changes needed",
        "Transfer source-e4bb2d5.tar by IAP with local key; verify SHA256 from approved plan before extracting",
        "Verify Debian signed package metadata; install only pinned Docker/sudo and pinned Compose deb after exact SHA256/size checks",
        "Install independently locked backend/Harbor dependencies; capture resolver versions/hashes before any extra dependency transaction",
        "Create dedicated isolated Docker daemon/socket/data root and trusted operator root-equivalent capability only on this host",
        "Preload only exact approved Python fixture and PostgreSQL OCI digests; verify Linux architecture and RepoDigests",
        "Create fresh loopback/Unix PostgreSQL database; apply migrations through058; scoped app/evaluator SQL identities, evaluator staysNOLOGIN",
        "Create owner-only non-symlink vault/work roots; no cloud/provider/source private keys in host or actor environments",
        "Run reviewed bounded native QA commands, collect exact hashes/results; no paid calls or application deployment"
    ], "cleanup_review": [
        "Export and hash sanitized evidence before deletion; retain no private input archive without review",
        "Read back exact created resource IDs; stop/delete only anvil-staging-native VM and its anvil-staging-native-boot disk",
        "Delete exact created staging-native NAT, address, router, IAP firewall, subnet and network in dependency order",
        "Remove repo-local temporary SSH private key and approved retained evidence snapshot after retention review",
        "Verify no enumerated test resources remain and report residual charges; never broad prefix deletion"
    ]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
