"""Owned QA SecretManager identity provisioning. Never reads secret versions.

No production resources, operator credential mounts, service-account keys,
project-level role grants, source approval or model activation.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from overnight_qa_lifecycle import DELETE, NAME, PROJECT
from overnight_qa_provision import call

ACCOUNT = "anvil-qa-20261110"
EMAIL = ACCOUNT + "@" + PROJECT + ".iam.gserviceaccount.com"
SECRET = "anvil-qa-model-credentials"
ROLES = {"roles/secretmanager.secretAccessor", "roles/secretmanager.secretVersionAdder"}
ROOT = Path("/private/tmp/anvil-overnight-qa-20261110-operator")


def verify_policy(policy):
    bindings = policy.get("bindings", [])
    if len(bindings) != 2 or {b.get("role") for b in bindings} != ROLES:
        raise ValueError("Only the two exact secret-scoped roles are permitted")
    if any(b.get("members") != ["serviceAccount:" + EMAIL] or b.get("condition") for b in bindings):
        raise ValueError("Unexpected credential-secret policy principal")


def identity(account, secret, policy, project_policy, project_number):
    if (
        account.get("email") != EMAIL
        or not str(account.get("uniqueId", "")).isdecimal()
        or account.get("disabled")
    ):
        raise ValueError("Unexpected QA credential identity")
    if (
        not str(project_number).isdecimal()
        or secret.get("name") != f"projects/{project_number}/secrets/{SECRET}"
        or not secret.get("createTime")
        or secret.get("labels", {}).get("purpose") != "overnight-qa"
        or secret.get("replication") != {"userManaged": {"replicas": [{"location": "us-west1"}]}}
    ):
        raise ValueError("Unexpected QA credential secret")
    verify_policy(policy)
    if any(
        "serviceAccount:" + EMAIL in b.get("members", [])
        for b in project_policy.get("bindings", [])
    ):
        raise ValueError("QA credential identity must have no project-level roles")
    return {
        "email": EMAIL,
        "uniqueId": str(account["uniqueId"]),
        "secret": secret["name"],
        "secret_create_time": secret["createTime"],
        "secret_only_policy_verified": True,
        "delete_not_before": DELETE.isoformat(),
    }


def append(event, **data):
    with (ROOT / "credential-resources.jsonl").open("a") as out:
        out.write(
            json.dumps({"at": datetime.now(timezone.utc).isoformat(), "event": event, **data})
            + "\n"
        )
        out.flush()
        import os

        os.fsync(out.fileno())


def readback():
    return identity(
        call(["iam", "service-accounts", "describe", EMAIL, "--format=json"]),
        call(["secrets", "describe", SECRET, "--format=json"]),
        call(["secrets", "get-iam-policy", SECRET, "--format=json"]),
        call(["projects", "get-iam-policy", PROJECT, "--format=json"]),
        call(["projects", "describe", PROJECT, "--format=json"])["projectNumber"],
    )


def provision():
    if datetime.now(timezone.utc) >= datetime(2026, 11, 10, 14, tzinfo=timezone.utc):
        raise ValueError("No new credential provisioning after handoff")
    if (ROOT / "credential-resources.jsonl").exists():
        raise ValueError("Existing credential journal requires explicit reconciliation")
    accounts = call(["iam", "service-accounts", "list", "--filter=email=" + EMAIL, "--format=json"])
    secrets = call(["secrets", "list", "--filter=name:" + SECRET, "--format=json"])
    if accounts or any(s["name"].endswith("/secrets/" + SECRET) for s in secrets):
        raise ValueError("Refuse adopting pre-existing identity or secret")
    append("before_create", kind="service_account", name=EMAIL)
    call(
        [
            "iam",
            "service-accounts",
            "create",
            ACCOUNT,
            "--display-name=Anvil overnight QA credentials only",
            "--description=Owned isolated overnight QA 20261110; no project roles",
            "--format=json",
        ]
    )
    account = call(["iam", "service-accounts", "describe", EMAIL, "--format=json"])
    append("created", kind="service_account", resource=account)
    append("before_create", kind="secret", name=SECRET)
    call(
        [
            "secrets",
            "create",
            SECRET,
            "--replication-policy=user-managed",
            "--locations=us-west1",
            "--labels=purpose=overnight-qa,qa-date=20261110",
            "--format=json",
        ]
    )
    secret = call(["secrets", "describe", SECRET, "--format=json"])
    append("created", kind="secret", resource=secret)
    for role in sorted(ROLES):
        call(
            [
                "secrets",
                "add-iam-policy-binding",
                SECRET,
                "--member=serviceAccount:" + EMAIL,
                "--role=" + role,
                "--format=json",
            ]
        )
    result = readback()
    append("qualified_metadata", identity=result)
    (ROOT / "credential-identity-public.json").write_text(json.dumps(result))
    print(json.dumps(result))


def cleanup():
    if datetime.now(timezone.utc) < DELETE:
        raise ValueError("Credential retention deadline not reached")
    original = json.loads((ROOT / "credential-identity-public.json").read_text())
    if call(["compute", "instances", "list", "--filter=name=" + NAME, "--format=json"]):
        raise ValueError("Delete owned QA VM before its credential identity")
    accounts = call(["iam", "service-accounts", "list", "--filter=email=" + EMAIL, "--format=json"])
    secrets = call(["secrets", "list", "--filter=name:" + SECRET, "--format=json"])
    secrets = [s for s in secrets if s["name"].endswith("/secrets/" + SECRET)]
    if len(accounts) > 1 or len(secrets) > 1:
        raise ValueError("Ambiguous credential resource inventory")
    if secrets:
        if not accounts or readback() != original:
            raise ValueError("Credential resource identity/policy changed; refuse deletion")
    elif accounts:
        # Resume only our dependency order after secret deletion succeeded.
        # Never adopt a replacement service account with the same email.
        if (
            accounts[0].get("email") != original["email"]
            or str(accounts[0].get("uniqueId")) != original["uniqueId"]
        ):
            raise ValueError("Credential identity replaced after partial cleanup")
        policy = call(["projects", "get-iam-policy", PROJECT, "--format=json"])
        if any(
            "serviceAccount:" + EMAIL in b.get("members", []) for b in policy.get("bindings", [])
        ):
            raise ValueError("Credential identity acquired project roles")
    append("before_delete", identity=original)
    if secrets:
        call(["secrets", "delete", SECRET])
    if accounts:
        call(["iam", "service-accounts", "delete", EMAIL])
    accounts = call(["iam", "service-accounts", "list", "--filter=email=" + EMAIL, "--format=json"])
    secrets = call(["secrets", "list", "--filter=name:" + SECRET, "--format=json"])
    if accounts or any(s["name"].endswith("/secrets/" + SECRET) for s in secrets):
        raise ValueError("Credential cleanup absence not verified")
    append("verified_absent", identity=original)
    print("Exact owned QA credential resources verified absent")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("provision", "readback", "cleanup"))
    action = parser.parse_args().action
    if action == "readback":
        print(json.dumps(readback()))
    elif action == "cleanup":
        cleanup()
    else:
        provision()
