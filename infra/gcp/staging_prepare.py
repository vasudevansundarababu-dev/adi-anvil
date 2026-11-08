"""Validate and render a non-secret staging contract; never deploy or read credentials."""
import argparse
import hashlib
import ipaddress
import json
import re
from pathlib import Path
from urllib.parse import urlsplit


PROJECT = "adi-anvil-mvp-2026"
PREFIX = "anvil-staging"


def scalars(value):
    """Exact values, never substring matching against serialized JSON."""
    if isinstance(value, dict):
        for item in value.values():
            yield from scalars(item)
    elif isinstance(value, list):
        for item in value:
            yield from scalars(item)
    elif isinstance(value, str):
        yield value


def validate(plan, existing, inventory=None):
    """Return clean errors for malformed or unsafe contracts. No filesystem inspection."""
    try:
        return _validate(plan, existing, inventory)
    except (KeyError, TypeError, ValueError, AttributeError):
        return ["Malformed or missing staging plan, deployment manifest or inventory fields"]


def _validate(plan, existing, inventory):
    errors = []
    required_keys = {"schema", "status", "source_checkpoint", "authorization", "target", "proposed_resources", "application_isolation", "secret_reference_proposals", "disabled_features", "native_test_host_proposal", "release", "unresolved"}
    if not isinstance(plan, dict) or not required_keys.issubset(plan):
        return ["Malformed or missing required staging plan fields"]
    if plan["schema"] != "anvil.gcp.staging.proposal.v1" or plan["status"] != "proposal_not_executable":
        errors.append("Unexpected staging schema or executable status")
    target = plan["target"]
    resources = plan["proposed_resources"]
    native = plan["native_test_host_proposal"]
    if native.get("name") != "anvil-staging-native" or native.get("service_account") != f"anvil-staging-native@{PROJECT}.iam.gserviceaccount.com" or native.get("public_ip") is not False or native.get("provider_credentials") is not False or native.get("source_keys") is not False:
        errors.append("Native host proposal escaped dedicated private staging identity")
    if native.get("status") != "not_authorized_for_provisioning":
        errors.append("Native host remains a separate unapproved provisioning proposal")
    isolation = plan["application_isolation"]
    if target["project_id"] != PROJECT or target["region"] != "us-west1" or target["zone"] != "us-west1-a" or target["resource_prefix"] != PREFIX:
        errors.append("Target must be the approved Anvil project and location")
    if plan["authorization"].get("incremental_budget_usd") != 500:
        errors.append("Expected approved additional monthly budget of USD 500")
    for key in ("web_hostname", "auth_hostname", "oidc_issuer", "allocated_public_ip"):
        if not target.get(key):
            errors.append(f"Unresolved target.{key}")
    hosts = [target.get("web_hostname"), target.get("auth_hostname")]
    if any(host and not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host) for host in hosts):
        errors.append("Hostnames must be bare DNS names")
    if all(hosts) and hosts[0] == hosts[1]:
        errors.append("Application and identity hostnames must differ")
    if target.get("auth_hostname") and target.get("oidc_issuer") != f"https://{target['auth_hostname']}/realms/anvil-staging":
        errors.append("OIDC issuer must bind the distinct staging realm and hostname")
    if target.get("allocated_public_ip"):
        try:
            address = ipaddress.ip_address(target["allocated_public_ip"])
            if address.version != 4 or not address.is_global:
                errors.append("Load-balancer address must be globally routable IPv4")
        except ValueError:
            errors.append("Allocated public IP is invalid")
    if not resources.get("deployment_principal"):
        errors.append("Deployment principal not reviewed")
    try:
        subnet = ipaddress.ip_network(resources["subnet"]["cidr"], strict=True)
        if subnet.version != 4 or not subnet.is_private:
            errors.append("Staging subnet must be private IPv4")
    except (ValueError, TypeError):
        errors.append("Subnet CIDR unresolved or invalid")
    names = [resources["vm"]["name"], resources["data_disk"]["name"], resources["network"],
             resources["subnet"]["name"], resources["router"], resources["nat"],
             resources["artifact_registry_repository"], resources["snapshot_policy"]["name"]]
    names += resources["firewall_rules"]
    lb = resources["load_balancer"]
    lb_keys = {"address_name", "instance_group", "health_check", "backend_service", "url_map", "https_proxy", "certificate", "forwarding_rule"}
    if set(lb) != lb_keys:
        errors.append("Load-balancer resource inventory is incomplete or unexpected")
    names += list(lb.values())
    if any(not re.fullmatch(r"anvil-staging(?:-[a-z0-9]+)*", name) for name in names):
        errors.append("Resource name escaped staging prefix or contains unsafe characters")
    if resources["vm"]["public_ip"] is not False or resources["data_disk"]["reuse_existing"] is not False:
        errors.append("VM public IP or existing disk reuse is forbidden")
    for key, expected in (("runtime_service_account", "anvil-staging-vm"), ("build_service_account", "anvil-staging-build")):
        if resources[key] != f"{expected}@{PROJECT}.iam.gserviceaccount.com":
            errors.append(f"{key} must be its dedicated staging identity")
    names += [resources["runtime_service_account"], resources["build_service_account"]]
    old = set(scalars(existing))
    old |= {urlsplit(value).hostname for value in old if value.startswith("https://")}
    if any(name in old for name in names):
        errors.append("Prospective resource collides with existing manifest")
    for value in (target.get("allocated_public_ip"), target.get("oidc_issuer")):
        if value and value in old:
            errors.append("Target collides with existing application endpoint")
    for host in hosts:
        if host and host in old:
            errors.append("Hostname collides with existing application")
    if isolation.get("host_data_root") != "/var/lib/anvil-staging" or isolation.get("reuse_current_database_disk_secrets_or_identity") is not False:
        errors.append("Staging data isolation is not explicit")
    artifact = Path(isolation["artifact_root"])
    vault = Path(isolation["benchmark_vault_root"])
    root = Path("/var/lib/anvil-staging")
    for key in ("artifact_root", "benchmark_vault_root", "qualification_work_root"):
        path = Path(isolation[key])
        if ".." in path.parts or not path.is_absolute() or root not in path.parents:
            errors.append(f"{key} must be a strict normalized child of the staging data root")
    if isolation.get("private_root_policy") != "fresh_owner_only_0700_no_symlinks_verify_at_runtime":
        errors.append("Owner-only no-symlink runtime root verification must be explicit")
    if artifact == vault or artifact in vault.parents or vault in artifact.parents:
        errors.append("Private vault and generic artifacts must be disjoint")
    expected_identity = {"compose_project": "adi-anvil-staging", "postgres_database": "anvil_staging", "identity_database": "anvil_staging_identity", "keycloak_realm": "anvil-staging", "data_origin": "fresh_fictional_only"}
    if any(isolation.get(key) != value for key, value in expected_identity.items()):
        errors.append("Staging database, realm, Compose or fixture isolation changed")
    expected_roles = {"anvil_staging_migration", "anvil_staging_app", "anvil_staging_worker", "anvil_staging_identity"}
    if set(isolation["database_roles"]) != expected_roles:
        errors.append("Dedicated staging database roles required")
    secrets = plan["secret_reference_proposals"]
    if len(secrets) != 8 or len(set(secrets)) != 8 or any(not re.fullmatch(rf"projects/{PROJECT}/secrets/anvil-staging-[a-z0-9-]+", value) for value in secrets):
        errors.append("Exactly eight distinct staging-only secret references required")
    if any(value in old for value in secrets):
        errors.append("Secret reference reuses current application secret")
    if not isinstance(inventory, dict) or inventory.get("project_id") != PROJECT or inventory.get("complete") is not True:
        errors.append("Complete reviewed project resource/subnet inventory is required")
    else:
        if not inventory.get("observed_at_utc") or inventory.get("reviewed_plan_sha256") != hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest():
            errors.append("Inventory must be dated and bound to this exact plan")
        occupied = set(inventory["resource_names"])
        if any(name in occupied for name in names + secrets):
            errors.append("Prospective resource already exists in discovered inventory")
        for cidr in inventory["subnet_cidrs"]:
            if ipaddress.ip_network(resources["subnet"]["cidr"]).overlaps(ipaddress.ip_network(cidr)):
                errors.append("Proposed subnet overlaps discovered subnet inventory")
        if target["allocated_public_ip"] not in inventory["reserved_staging_ipv4"]:
            errors.append("Address is not independently reserved for staging")
    required = {"candidate_dispatch", "judge_dispatch", "import_generation", "vertex_support", "other_paid_support", "outbound_email"}
    if not required.issubset(set(plan.get("disabled_features", []))):
        errors.append("A paid or email route is not explicitly disabled")
    release = plan["release"]
    if not re.fullmatch(r"[0-9a-f]{40}", release.get("source_sha") or ""):
        errors.append("Exact release source SHA unresolved")
    if not release.get("image_digests") or any(not re.fullmatch(r".+@sha256:[0-9a-f]{64}", image) for image in release.get("image_digests", {}).values()):
        errors.append("Immutable release image digests unresolved")
    if plan.get("unresolved"):
        errors.append("Unresolved release/inventory decisions remain")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=Path(__file__).with_name("staging-plan.json"))
    parser.add_argument("--existing", type=Path, default=Path(__file__).with_name("deployment.json"))
    parser.add_argument("--inventory", type=Path, help="Sanitized reviewed metadata only; no credentials")
    args = parser.parse_args()
    try:
        plan = json.loads(args.plan.read_text())
        existing = json.loads(args.existing.read_text())
        inventory = json.loads(args.inventory.read_text()) if args.inventory else None
    except (OSError, ValueError):
        print(json.dumps({"ready": False, "errors": ["Cannot read valid non-secret plan/manifests"]}))
        return 2
    errors = validate(plan, existing, inventory)
    if errors:
        print(json.dumps({"ready": False, "errors": errors}, indent=2))
        return 2
    digest = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    print(json.dumps({"ready": True, "deploy_authorized": False, "plan_sha256": digest,
                      "target": plan["target"], "release": plan["release"],
                      "disabled_features": plan["disabled_features"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
